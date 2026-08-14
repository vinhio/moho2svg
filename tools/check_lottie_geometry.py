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


def expected_layers(project_path: str, frame: float, include_hidden: bool = False):
    """Every mesh layer's expected shape geometry at `frame`, in LOTTIE draw
    order (front to back reversed from Moho's own back-to-front walk) - see
    moho2lottie.LottieExporter._build_layers for why the reversal happens.

    Returns a list of (layer_name, [(kind, [bezier, ...]), ...]) - `kind` is
    "fill" or "outline", matching moho2lottie's own two-groups-per-shape
    split (see docs/moho-to-lottie-plan.md Task 3's note on why fill and
    outline are never combined into one Lottie group).
    """
    Channel.reset_cache()
    doc = load_document(project_path)
    exp = Exporter(doc)
    out = []
    for item in walk_render_tree(exp, frame, include_hidden):
        if item.event != "mesh":
            continue
        shapes = []
        for shape in item.layer.mesh.shapes:
            if not shape.edges:
                continue
            fill_beziers = build_path_bezier(item.geometries, shape.edges, item.to_px)
            if not fill_beziers:
                continue
            if shape.has_outline:
                widths = [exp.eval(item.layer.mesh.points[i].width, frame)
                          for i in {item.layer.mesh.curves[e.curve].points[e.segment].point_index
                                    for e in shape.edges}]
                tapered = (max(widths) - min(widths) > 1e-6) if widths else False
                if tapered and not shape.style.brush_name:
                    line_width = exp.eval(shape.style.line_width, frame)
                    width_px = exp._stroke_width_px(line_width, 1.0)
                    outline = exp.tapered_outliner.build_bezier(
                        item.geometries, shape.edges, item.to_px, width_px)
                else:
                    outline = build_path_bezier(item.geometries, shape.edges, item.to_px,
                                                 visible_only=True, close=False)
                if outline:
                    shapes.append(("outline", outline))
            if shape.has_fill:
                shapes.append(("fill", fill_beziers))
        out.append((item.layer.name, shapes))
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
    (already Lottie-ordered) order - the counterpart of expected_layers()."""
    out = []
    for layer in lottie["layers"]:
        shapes = []
        for grp in layer["shapes"]:
            beziers = [path_property_at(e["ks"], frame) for e in grp["it"] if e["ty"] == "sh"]
            if not beziers:
                continue
            kind = "outline" if grp["nm"].endswith("_line") else "fill"
            shapes.append((kind, beziers))
        out.append((layer["nm"], shapes))
    return out


def check_frame(project_path: str, lottie: dict, frame: float,
                 include_hidden: bool = False) -> int:
    """Compare one frame. Returns the number of disagreements found."""
    expected = expected_layers(project_path, frame, include_hidden)
    got = emitted_layers(lottie, frame)
    failures = 0

    if len(expected) != len(got):
        print(f"  frame {frame}: {len(got)} layers emitted, expected {len(expected)}")
        return 1

    for (exp_name, exp_shapes), (got_name, got_shapes) in zip(expected, got):
        if exp_name != got_name:
            print(f"  frame {frame}: layer order mismatch - got {got_name!r}, "
                  f"expected {exp_name!r} (reversed layer order is the classic cause)")
            failures += 1
            continue
        if len(exp_shapes) != len(got_shapes):
            print(f"  frame {frame} {exp_name!r}: {len(got_shapes)} shape-groups emitted, "
                  f"expected {len(exp_shapes)}")
            failures += 1
            continue
        for (exp_kind, exp_beziers), (got_kind, got_beziers) in zip(exp_shapes, got_shapes):
            if exp_kind != got_kind or len(exp_beziers) != len(got_beziers):
                print(f"  frame {frame} {exp_name!r}: expected {exp_kind} with "
                      f"{len(exp_beziers)} subpath(s), got {got_kind} with {len(got_beziers)}")
                failures += 1
                continue
            for a, b in zip(got_beziers, exp_beziers):
                if not bezier_close_enough(a, b):
                    print(f"  frame {frame} {exp_name!r} ({exp_kind}): geometry differs")
                    failures += 1
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
