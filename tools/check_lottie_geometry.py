#!/usr/bin/env python3
"""Check that an emitted Lottie file holds the same geometry, in the same
order, that moho2svg.py's own pipeline produces at the same frame.

This needs no Lottie player and no third-party package: it walks the
document exactly as moho2lottie.py does (walk_render_tree, build_path_bezier,
TaperedStrokeOutliner.build_bezier), reversed into Lottie draw order, and
compares against what the emitted JSON actually holds at each checked frame.
It also catches a reversed layer order, because it compares shapes in
EMITTED order, not by searching for a name match.

Usage: check_lottie_geometry.py <project> <lottie.json> [frame ...]
       check_lottie_geometry.py <project> <lottie.json> [frame ...] --require-gradients
       check_lottie_geometry.py <project> <lottie.json> [frame ...] --require-masks
Exit status is 0 when every shape at every checked frame agrees.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moho2svg import Channel, Exporter, build_path_bezier, load_document, walk_render_tree
from moho2lottie import (_clip_polygon_loops, _flatten_bezier_dict, _loops_to_bezier_dicts,
                         pyclipper)

# Same tolerance as check_bezier_roundtrip.py, deliberately: both scripts
# compare build_path_bezier()-shaped data (rounded to 3 decimals, with
# tangents that are DIFFERENCES of two rounded values), so they must agree
# on what "equal" means or a document could pass one check and fail the
# other for no real reason.
TOLERANCE = 3e-3


def close_enough(a, b) -> bool:
    return all(abs(x - y) <= TOLERANCE for x, y in zip(a, b))


def bezier_close_enough(got: dict, expected: dict) -> bool:
    if got["c"] != expected["c"] or len(got["v"]) != len(expected["v"]):
        return False
    for key in ("v", "i", "o"):
        for a, b in zip(got[key], expected[key]):
            if not close_enough(a, b):
                return False
    return True


def split_boolean_groups(shapes_in_order: list) -> list:
    """The check-script counterpart of LottieExporter._split_boolean_groups
    in moho2lottie.py - same grouping rule (a combo_mode==0 shape starts a
    new group, combo_mode 1/3 shapes join the group in progress), applied
    to plain `Shape` objects instead of accumulator dicts. combo_mode
    values outside (0, 1, 3) are clamped to 0 first, matching
    moho2lottie.LottieExporter._new_accumulator's own fallback. Returns
    [(base_shapes, clip_shapes), ...] per group."""
    groups = []
    base, clip = [], []
    for shape in shapes_in_order:
        combo_mode = shape.combo_mode if shape.combo_mode in (0, 1, 3) else 0
        if combo_mode == 0 and (base or clip):
            groups.append((base, clip))
            base, clip = [], []
        (clip if combo_mode == 3 else base).append(shape)
    if base or clip:
        groups.append((base, clip))
    return groups


def split_into_chunks(groups: list) -> list:
    """The check-script counterpart of LottieExporter._split_into_chunks -
    same merge-adjacent-plain-groups, split-out-each-clip-group,
    split-out-each-union-member-needing-stroke-exclusion rules. Returns a
    list of chunk dicts in file order, one of:

      {"kind": "plain", "shapes": [...], "skip_outline": frozenset(...)}
      {"kind": "clip", "shapes": [...]}
      {"kind": "union_exclude", "shape": shape}

    The mask each kind gets is irrelevant to this script (it never builds
    one) - only the resulting PER-LAYER shape grouping/naming/fill-vs-
    outline split needs to match."""
    chunks = []
    plain_run = []
    skip_outline = set()

    def flush_plain():
        nonlocal plain_run, skip_outline
        if plain_run:
            chunks.append({"kind": "plain", "shapes": plain_run,
                           "skip_outline": frozenset(skip_outline)})
        plain_run, skip_outline = [], set()

    for base, clip in groups:
        plain_run.extend(base)
        group_exclusions = []
        if len(base) > 1:
            for member in base:
                if member.has_outline:
                    skip_outline.add(id(member))
                    group_exclusions.append(member)
        if clip or group_exclusions:
            flush_plain()
        if clip:
            chunks.append({"kind": "clip", "shapes": clip})
        for member in group_exclusions:
            chunks.append({"kind": "union_exclude", "shape": member})
    flush_plain()
    return chunks


def expected_layers(project_path: str, frame: float, include_hidden: bool = False):
    """Every mesh layer's expected shape geometry at `frame`, in LOTTIE draw
    order (front to back reversed from Moho's own back-to-front walk) - see
    moho2lottie.LottieExporter._build_layers for why the reversal happens.

    Returns a list of (layer_name, [(kind, [bezier, ...]), ...]) - `kind` is
    "fill" or "outline", matching moho2lottie's own two-groups-per-shape
    split (see docs/moho-to-lottie-plan.md Task 3's note on why fill and
    outline are never combined into one Lottie group).

    A mesh with any combo_mode==3 (intersect) shape is split into several
    named layers ("name", "name#1", "name#2", ...), one per boolean-
    combination chunk - see split_boolean_groups/split_into_chunks above,
    mirroring LottieExporter._split_boolean_groups/_split_into_chunks. The
    SHAPE sequence is reversed WITHIN EACH CHUNK, not across the whole
    original layer - see LottieExporter._finalize_shapes for why Moho's
    back-to-front mesh.shapes order becomes front-to-back in Lottie. This
    check shares that convention deliberately: while both sides emitted
    plain file order, the check passed on output whose multi-shape layers
    were internally z-inverted (the `kalca` belt buried under its own hip
    fill), because it only ever compared the two orderings against EACH
    OTHER. Geometry agreement is all it can prove; the ordering convention
    itself has to be argued from the writer's own rules and checked against
    reference frames.
    """
    Channel.reset_cache()
    doc = load_document(project_path)
    exp = Exporter(doc)
    out = []
    for item in walk_render_tree(exp, frame, include_hidden):
        if item.event != "mesh":
            continue
        shapes_in_order = []
        blocks_by_shape = {}
        # Flattened base-union loops for the CURRENT boolean group, exactly
        # mirroring moho2lottie.LottieExporter._accumulate_frame's own
        # `group_base_loops` - needed here because that writer, when
        # pyclipper is installed, pre-clips a combo_mode==3 member's own
        # fill/outline against this SAME running union instead of leaving
        # it raw (see _clip_polygon_loops's own docstring for why). This
        # checker cannot know, from a single frame alone, whether that
        # pre-clip attempt stayed topologically stable across the WHOLE
        # animation (the one thing that decides whether the real writer
        # actually used it - see LottieExporter._build_layers' own
        # "PRE-CLIP RESOLUTION" pass) - so a combo_mode==3 shape gets a
        # SECOND, alternate expected block (`block_clip`) here, and
        # check_frame accepts either one as a pass, rather than trying to
        # replicate the writer's cross-frame stability decision.
        group_base_loops: list = []
        for shape in item.layer.mesh.shapes:
            if not shape.edges:
                continue
            if shape.combo_mode == 0:
                group_base_loops = []
            fill_beziers = build_path_bezier(item.geometries, shape.edges, item.to_px)
            if not fill_beziers:
                continue
            can_clip = (shape.combo_mode == 3 and pyclipper is not None
                       and bool(group_base_loops))
            fill_clip = None
            if can_clip:
                fill_clip = _loops_to_bezier_dicts(_clip_polygon_loops(
                    [_flatten_bezier_dict(d) for d in fill_beziers], group_base_loops))
            block, block_clip = [], []
            if shape.has_outline:
                widths = [exp.eval(item.layer.mesh.points[i].width, frame)
                          for i in {item.layer.mesh.curves[e.curve].points[e.segment].point_index
                                    for e in shape.edges}]
                tapered = (max(widths) - min(widths) > 1e-6) if widths else False
                line_width = exp.eval(shape.style.line_width, frame)
                point_width = 1.0 if tapered else (widths[0] if widths else 1.0)
                width_px = exp._stroke_width_px(line_width, point_width)
                if tapered and not shape.style.brush_name:
                    outline = exp.tapered_outliner.build_bezier(
                        item.geometries, shape.edges, item.to_px, width_px)
                else:
                    # visible_only=(combo_mode != 3) - must match
                    # moho2lottie.py's own _accumulate_frame exactly (see
                    # its own comment, and moho2svg.py's BOOLEAN SHAPE
                    # COMBINATIONS section): a combo_mode==3 member's own
                    # segments_on==False segment is not a legitimate gap,
                    # it is a piece of curve the intersect clip resolves,
                    # so it must stay in the outline this checker expects
                    # too - otherwise this "reference" computation carries
                    # the same bug it exists to catch.
                    outline = build_path_bezier(item.geometries, shape.edges, item.to_px,
                                                 visible_only=(shape.combo_mode != 3), close=False)
                if outline:
                    block.append(("outline", outline))
                if can_clip:
                    # The pre-clip ATTEMPT always builds the outline as a
                    # filled band (TaperedStrokeOutliner), tapered or not -
                    # see moho2lottie.LottieExporter._accumulate_frame's own
                    # comment for why a native "st" stroke cannot itself be
                    # intersected against the base union.
                    band = exp.tapered_outliner.build_bezier(
                        item.geometries, shape.edges, item.to_px, width_px)
                    band_clip = _loops_to_bezier_dicts(_clip_polygon_loops(
                        [_flatten_bezier_dict(d) for d in band], group_base_loops))
                    if band_clip:
                        block_clip.append(("outline", band_clip))
            if shape.has_fill:
                block.append(("fill", fill_beziers))
                if can_clip and fill_clip:
                    block_clip.append(("fill", fill_clip))
            shapes_in_order.append(shape)
            blocks_by_shape[id(shape)] = (block, block_clip if can_clip else None)
            if shape.combo_mode in (0, 1):
                group_base_loops.extend(_flatten_bezier_dict(d) for d in fill_beziers)

        chunks = split_into_chunks(split_boolean_groups(shapes_in_order))
        multi = len(chunks) > 1
        for chunk_index, chunk in enumerate(chunks):
            # One entry per SHAPE (not flattened across the whole chunk):
            # `(block, block_clip_or_None)`, block_clip being the shape's
            # OWN pre-clip attempt when it has one. A chunk with more than
            # one combo_mode==3 member can have EACH pre-clip independently
            # (Bandit's own Leg_F/Leg_F 2 confirmed this: of two members in
            # the SAME "clip" chunk, one clipped stably, the other did not
            # - LottieExporter._build_layers' own "PRE-CLIP RESOLUTION"
            # pass decides per-SHAPE, so this checker must compare per-
            # shape too, not assume a whole chunk is all-or-nothing.
            if chunk["kind"] == "union_exclude":
                block, _clip = blocks_by_shape[id(chunk["shape"])]
                shape_blocks = [([entry for entry in block if entry[0] == "outline"], None)]
            else:
                skip_outline = chunk.get("skip_outline", frozenset())
                shape_blocks = []
                for shape in reversed(chunk["shapes"]):
                    block, clip = blocks_by_shape[id(shape)]
                    if id(shape) in skip_outline:
                        block = [entry for entry in block if entry[0] != "outline"]
                        clip = ([entry for entry in clip if entry[0] != "outline"]
                               if clip is not None else None)
                    shape_blocks.append((block, clip))
            name = f"{item.layer.name}#{chunk_index}" if multi else item.layer.name
            out.append((name, shape_blocks))
    out.reverse()          # Moho back-to-front -> Lottie front-to-back
    return out


def path_property_at(ks: dict, frame: float) -> dict:
    """The bezier value a Lottie path property (`{"a":0/1, "k":...}`) holds
    at `frame` - the static value, or the keyframe whose "t" equals `frame`
    exactly (this checker only ever asks for frames the exporter itself
    sampled, so an exact match is expected, not interpolation)."""
    if ks["a"] == 0:
        return ks["k"]
    for kf in ks["k"]:
        if abs(kf["t"] - frame) < 1e-6:
            return kf["s"][0]
    raise KeyError(f"no keyframe at frame {frame}")


def emitted_layers(lottie: dict, frame: float):
    """Every Lottie layer's actual shape geometry at `frame`, in emitted
    (already Lottie-ordered) order - the counterpart of expected_layers().

    Skips a layer whose own `ip`/`op` window excludes `frame` entirely: a
    SwitchLayer child only exists for its own visibility window (see
    moho2lottie.LottieExporter._windows), so it legitimately has no
    keyframe at a frame outside that window - that is not a mismatch to
    report, it is the layer correctly not being there.
    """
    out = []
    for layer in lottie["layers"]:
        if not (layer["ip"] <= frame < layer["op"]):
            continue
        shapes = []
        for grp in layer["shapes"]:
            beziers = [path_property_at(e["ks"], frame) for e in grp["it"] if e["ty"] == "sh"]
            if not beziers:
                continue
            kind = "outline" if grp["nm"].endswith("_line") else "fill"
            shapes.append((kind, beziers))
        out.append((layer["nm"], shapes))
    return out


def _shape_mismatches(name: str, frame: float, exp_shapes: list, got_shapes: list) -> list:
    """[(message), ...] describing every disagreement between one layer's
    expected and emitted shape-group geometry."""
    msgs = []
    if len(exp_shapes) != len(got_shapes):
        msgs.append(f"  frame {frame} {name!r}: {len(got_shapes)} shape-groups emitted, "
                    f"expected {len(exp_shapes)}")
        return msgs
    for (exp_kind, exp_beziers), (got_kind, got_beziers) in zip(exp_shapes, got_shapes):
        if exp_kind != got_kind or len(exp_beziers) != len(got_beziers):
            msgs.append(f"  frame {frame} {name!r}: expected {exp_kind} with "
                        f"{len(exp_beziers)} subpath(s), got {got_kind} with {len(got_beziers)}")
            continue
        for a, b in zip(got_beziers, exp_beziers):
            if not bezier_close_enough(a, b):
                msgs.append(f"  frame {frame} {name!r} ({exp_kind}): geometry differs")
    return msgs


def _layer_mismatches(name: str, frame: float, shape_blocks: list, got_shapes: list) -> list:
    """[(message), ...] for one LAYER, matching `got_shapes` (the emitted,
    already-flat list of (kind, beziers) shape-groups) against
    `shape_blocks` (expected_layers' own per-shape `(block, block_clip)`
    list) shape by shape, consuming `len(block)` entries of `got_shapes`
    per shape in turn.

    Tries `block` (the raw, unclipped expectation) first; only when it
    disagrees does it retry with `block_clip` (the alternative expectation
    for a shape LottieExporter's own pre-clip attempt MIGHT have replaced -
    see expected_layers' own docstring for why this checker cannot know,
    from a single frame alone, which of the two the real writer actually
    used for THIS shape). Two members of the very same "clip" chunk can
    each resolve differently - confirmed on Bandit's own Leg_F/Leg_F 2,
    where one combo_mode==3 member's clip stayed stable and the other did
    not - so this is decided per shape, not once for the whole layer.
    """
    msgs = []
    pos = 0
    for block, block_clip in shape_blocks:
        n = len(block)
        window = got_shapes[pos:pos + n]
        pos += n
        shape_msgs = _shape_mismatches(name, frame, block, window)
        if shape_msgs and block_clip is not None:
            clip_msgs = _shape_mismatches(name, frame, block_clip, window)
            if not clip_msgs:
                shape_msgs = []
        msgs.extend(shape_msgs)
    if pos != len(got_shapes):
        msgs.append(f"  frame {frame} {name!r}: {len(got_shapes)} shape-groups emitted, "
                    f"expected {pos}")
    return msgs


def check_frame(project_path: str, lottie: dict, frame: float,
                 include_hidden: bool = False) -> int:
    """Compare one frame. Returns the number of disagreements found."""
    expected = expected_layers(project_path, frame, include_hidden)
    got = emitted_layers(lottie, frame)
    failures = 0

    if len(expected) != len(got):
        print(f"  frame {frame}: {len(got)} layers emitted, expected {len(expected)}")
        return 1

    for (exp_name, shape_blocks), (got_name, got_shapes) in zip(expected, got):
        if exp_name != got_name:
            print(f"  frame {frame}: layer order mismatch - got {got_name!r}, "
                  f"expected {exp_name!r} (reversed layer order is the classic cause)")
            failures += 1
            continue
        msgs = _layer_mismatches(exp_name, frame, shape_blocks, got_shapes)
        for msg in msgs:
            print(msg)
        failures += len(msgs)
    return failures


def check_gradients_present(project_path: str, lottie: dict) -> int:
    """--require-gradients: fails if the source document has an
    SS_Gradient2 style but the emitted file has no "gf" element - a
    reminder this is still Task 5's job, not a claim it is done."""
    raw = json.load(open(project_path))

    def has_gradient(node) -> bool:
        if isinstance(node, dict):
            if node.get("type") == "SS_Gradient2":
                return True
            return any(has_gradient(v) for v in node.values())
        if isinstance(node, list):
            return any(has_gradient(v) for v in node)
        return False

    if not has_gradient(raw):
        return 0
    emitted_gf = any(e["ty"] == "gf" for layer in lottie["layers"]
                      for grp in layer["shapes"] for e in grp["it"])
    if not emitted_gf:
        print("  --require-gradients: source has SS_Gradient2 but no \"gf\" element was emitted")
        return 1
    return 0


def check_masks_present(project_path: str, lottie: dict) -> int:
    """--require-masks: fails if the source document has a group_mask==2
    container but no emitted layer carries hasMask - a reminder this is
    still Task 6's job."""
    raw = json.load(open(project_path))

    def has_group_mask(node) -> bool:
        if isinstance(node, dict):
            if node.get("group_mask") == 2:
                return True
            return any(has_group_mask(v) for v in node.values())
        if isinstance(node, list):
            return any(has_group_mask(v) for v in node)
        return False

    if not has_group_mask(raw):
        return 0
    if not any(layer.get("hasMask") for layer in lottie["layers"]):
        print("  --require-masks: source has group_mask == 2 but no layer has hasMask")
        return 1
    return 0


def main() -> int:
    args = sys.argv[1:]
    require_gradients = "--require-gradients" in args
    require_masks = "--require-masks" in args
    args = [a for a in args if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return 2
    project_path, lottie_path, *frame_args = args
    frames = [float(f) for f in frame_args] if frame_args else None

    lottie = json.load(open(lottie_path))
    if frames is None:
        frames = [lottie["ip"], (lottie["ip"] + lottie["op"] - 1) / 2, lottie["op"] - 1]

    failures = 0
    for frame in frames:
        failures += check_frame(project_path, lottie, frame)
    if require_gradients:
        failures += check_gradients_present(project_path, lottie)
    if require_masks:
        failures += check_masks_present(project_path, lottie)

    if failures:
        print(f"\nFAIL: {failures} disagreement(s)")
        return 1
    print(f"OK: {len(frames)} frame(s) agree with the reference geometry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
