#!/usr/bin/env python3
"""Export Moho vector artwork (.mohoproj / .animeproj) to a Lottie JSON
animation.

Reuses moho2svg.py's geometry pipeline in full: the same document model, the
same Bezier reconstruction, the same path tracing, the same bone
deformation, the same layer tree walk (walk_render_tree). Only the output
stage differs - where moho2svg.py formats SVG strings, this module formats
Lottie's JSON shape/property dicts.

Every deformation is BAKED into canvas-pixel vertex positions, so every
Lottie layer carries an identity transform and no affine matrix is ever
decomposed into Lottie's anchor/position/scale/rotation/skew form. See
docs/moho-to-lottie-design.md for why, and for what that costs in file size.

Deliberately out of scope for this exporter (see docs/moho-to-lottie-design.md
section 2.2, and the corresponding counted warnings on stderr at the end of
an export): brush-textured strokes (drawn as a plain uniform stroke
instead), ImageLayer, Smart Warp, and layers driven by Moho's own
rigid-body physics simulation (rendered at their rest pose on every frame).

Boolean shape combination (`combo_mode`) IS implemented, EXACTLY, for every
case observed in this repository's corpus (see
LottieExporter._split_boolean_groups/_split_into_chunks):

  - combo_mode==3 (intersect): split into its own Lottie layer, clipped
    with `masksProperties` to the union of its own group's combo_mode 0/1
    (base) members' geometry - the Lottie counterpart of
    ShapeGroupRenderer._mask_union in moho2svg.py. When that base union
    needs more than one shape AND the layer ALSO carries a cross-layer
    mask (Moho's `masking`/`group_mask`), a flat sequential masksProperties
    list cannot express "intersect with a union of several shapes" at all -
    see _combined_mask_properties's own docstring - so
    _nested_group_mask_layer composes the two constraints exactly instead,
    via a precomposition (two independent masking passes, nested, rather
    than one flat list trying to express both).
  - combo_mode==1 (union): a member's FILL needs no special handling
    (moho2svg.py's own _render_shape does not clip a union member's fill
    either). Its STROKE is excluded from redrawing the boundary shared
    with every OTHER base member in its group - the Lottie counterpart of
    ShapeGroupRenderer._mask_subtraction - via its own masked chunk (see
    _combo_mode_union_mask_properties); the exclusion band that avoids a
    notch right at the seam is built once per qualifying shape in
    _accumulate_frame/_prepare_union_band_widths.

The one remaining approximation is on the CROSS-layer masking side, not
combo_mode: Exporter._mask_source_shapes_bezier's own exclusion band
(_finalize_mask, item 3 in the same body of work) is skipped, with a
counted warning, only if TaperedStrokeOutliner.build_bezier itself returns
nothing for a non-degenerate source outline - not expected to ever fire.

Every animated (`"a": 1`) property this writer emits - shape paths, stroke
widths, gradient points, mask paths - carries linear `i`/`o` keyframe
easing (see LottieExporter._keyframes). Confirmed the hard way, outside
this codebase, that lottie-web renders NOTHING for an animated property
whose keyframes omit it (not merely the wrong interpolation - no value at
any frame), even though the schema marks both fields optional. See
_keyframes's own docstring for the reproduction and why linear is the
exact right choice here, not just a safe default.
"""

import argparse
import json
import math
import os
import sys
from collections import Counter

from moho2svg import (Color, Exporter, RenderSettings, build_path_bezier,
                       load_document, walk_render_tree)

try:
    # Optional, exactly like Pillow in moho2svg.py: only used by --validate,
    # so this tool still runs with zero third-party dependencies otherwise.
    import jsonschema
except ImportError:
    jsonschema = None

LOTTIE_VERSION = "5.7.0"
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "lottie", "lottie.schema.json")

# Printed per warning key at the end of an export - see the module
# docstring's "deliberately out of scope" paragraph for the reasoning behind
# each one.
WARNING_EXPLANATIONS = {
    "combo_mode_unknown": "shape(s) with an unrecognised combo_mode (not "
                          "0/1/3) drawn as a plain replace shape instead - "
                          "matches moho2svg.py's own ShapeGroupRenderer."
                          "_render_shape fallback",
    "brush": "shape(s) with a textured brush outline drawn as a plain "
             "uniform stroke instead",
    "gradient_too_few_stops": "gradient fill(s) with fewer than 2 stops drawn "
                              "as a flat colour instead (matches "
                              "Exporter._build_gradient's own SVG fallback)",
    "mask_stroke_exclusion": "mask source(s) with a nonzero exclude-width whose "
                             "exclusion band came back empty from "
                             "TaperedStrokeOutliner.build_bezier - unexpected "
                             "for a non-degenerate, non-tapered, non-brush "
                             "outline; that source's own stroke may paint over "
                             "by whatever it masks instead of staying carved out "
                             "(see LottieExporter._finalize_mask)",
    "timing_offset": "layer(s) carrying a non-zero timing_offset, which shifts "
                     "their animation in time - not applied, because nothing in "
                     "the sample corpus animates such a layer, so the sign and "
                     "scope cannot be verified (see Layer.timing_offset)",
    "physics": "layer(s) driven by Moho's own rigid-body physics simulation "
               "(gravity/velocity/forces), which this exporter does not run - "
               "each renders at its rest pose on every sampled frame instead "
               "of the simulated motion Moho itself would show",
}

# Lottie's line-cap constant (shapes/base-stroke.json's "lc"), keyed by the
# SAME string ResolvedStyle.line_cap_name() already returns for the SVG
# writer's own stroke-linecap - deriving it from that string, not from the
# raw line_caps int, means the two exporters cannot drift apart.
LINE_CAPS = {"butt": 1, "round": 2, "square": 3}

# Lottie's `constants/fill-rule` (schema: 1 = "Non Zero", 2 = "Even Odd").
# Moho is ALWAYS even-odd - confirmed from Moho's own SVG export, which sets
# style="fill-rule:evenodd" once for the whole document, and reproduced by
# moho2svg.py writing fill-rule="evenodd" on every shape fill it emits.
# This writer used to send 1 (non-zero) for shape fills and gradient fills,
# which silently plugged every hole built from counter-wound subpaths: the
# skull inside `SketchBone.animeproj`'s "rozet1" badge lost its eye sockets,
# and any ring-shaped fill would fill in solid the same way.
FILL_RULE_EVEN_ODD = 2

# Linear (no-ease) keyframe easing, in Lottie's normalised time/value space
# (properties/easing-handle: x runs 0->1 across the segment's own time span,
# y runs 0->1 across its own value span) - see LottieExporter._keyframes for
# why every animated property this writer emits needs this on every
# non-final keyframe, not just an optional nicety.
LINEAR_EASE_OUT = {"x": [0], "y": [0]}
LINEAR_EASE_IN = {"x": [1], "y": [1]}


def identity_transform() -> dict:
    """Lottie's neutral transform: no anchor, no move, no rotation, full
    size and full opacity.  A function, not a module constant, so no two
    layers/groups ever share one mutable dict."""
    return {"a": {"a": 0, "k": [0, 0]}, "p": {"a": 0, "k": [0, 0]},
            "s": {"a": 0, "k": [100, 100]}, "r": {"a": 0, "k": 0},
            "o": {"a": 0, "k": 100}}


class LottieExporter:
    """Builds a Lottie document from a Moho Document.

    Stateful in the same way Exporter is: it holds a per-export warning
    counter and reuses one Exporter for geometry.  Construct one per export
    call, never share across concurrent exports - see Exporter's own
    docstring for why (per-call def-id counter, Smart Bone scratch state).
    """

    def __init__(self, document, settings: "RenderSettings" = None):
        self.document = document
        self.exporter = Exporter(document, settings)
        self.warnings: Counter = Counter()
        # Precomposition assets - see _nested_group_mask_layer for the one
        # case that needs one (a combo_mode==3 group mask that itself needs
        # more than one shape, on a layer that ALSO carries a cross-layer
        # mask). Empty for every document that never hits that case, which
        # is every sample document in this repository except Bandit.mohoproj.
        self._assets: list = []
        self._asset_counter: int = 0

    def _next_asset_id(self) -> int:
        self._asset_counter += 1
        return self._asset_counter

    def export(self, frames, include_hidden: bool = False) -> dict:
        """Return the Lottie document as a plain dict.

        `frames` is every frame to sample, in ascending order.  A single
        frame produces static paths; several (Task 4) produce path
        keyframes.
        """
        self._count_physics_layers()
        layers = self._build_layers(frames, include_hidden)
        return {
            "v": LOTTIE_VERSION,
            "fr": float(self.document.fps),
            "ip": float(self.document.start_frame),
            # Moho's end_frame is inclusive; Lottie's "op" is documented as
            # the first frame NOT shown, so the exclusive upper bound is
            # end_frame + 1 - an INFERENCE, not confirmed against a player.
            # See docs/moho-to-lottie-design.md section 9, item 1.
            "op": float(self.document.end_frame + 1),
            "w": int(self.document.width),
            "h": int(self.document.height),
            "assets": self._assets,
            "layers": layers,
        }

    def _count_physics_layers(self) -> None:
        """Count every layer Moho would animate via its own rigid-body
        physics simulation instead of a keyframed channel - see
        Layer.physics_dynamic.

        Checked once, independent of `frames`: `physics.enabled`/`.static`
        are plain (never-animated) booleans on the layer itself, so whether
        a layer is physics-driven cannot change frame to frame the way a
        SwitchLayer's active child can. `Document.walk()` visits every
        layer, containers included, since a physics body is as likely to be
        the `BoneLayer` wrapping a whole rig (as in `Bandit.mohoproj`) as a
        single mesh layer.
        """
        for _ancestors, layer in self.document.walk():
            if layer.physics_dynamic:
                self.warnings["physics"] += 1
            if layer.timing_offset:
                self.warnings["timing_offset"] += 1

    def _build_layers(self, frames, include_hidden: bool = False) -> list:
        """One Lottie shape layer per Moho mesh layer, in Lottie draw order.

        walk_render_tree yields an EVENT STREAM ("enter"/"mesh"/"exit"), not
        one item per mesh layer - "enter"/"exit" exist so a consumer that
        needs Moho's nested <g> structure (Exporter.export_document) can
        reconstruct it, including empty containers.  This writer flattens
        everything anyway (every layer gets an identity transform), so it
        keeps only "mesh" events.

        Walks the tree ONCE PER FRAME and, for each "mesh" item,
        IMMEDIATELY extracts that frame's geometry/style into per-shape
        accumulators (_accumulate_frame) - it does NOT collect RenderItems
        first and process them afterwards.  That distinction is load-
        bearing, not stylistic: Exporter.to_px's underlying skin cache reads
        exporter._active_actions (and stroke width reads
        exporter._layer_scale) LAZILY, at CALL time, not at closure-creation
        time - both are "sticky" scratch state that walk_render_tree only
        guarantees correct WHILE an item is the current one being yielded
        (see walk_render_tree's own docstring). An earlier version of this
        method collected every frame's RenderItem into a dict keyed by
        layer identity and only called `.to_px()` on them afterwards, once
        all frames had already been walked - by then `_active_actions` held
        whatever the LAST-walked layer's context was, so every geometry
        call silently used the WRONG Smart Bone context. Caught by
        tools/check_lottie_geometry.py, which showed coordinates off by
        hundreds of pixels, not a rounding-sized discrepancy.

        A mesh layer's SET of shapes and their has_fill/has_outline/
        combo_mode never varies by frame (only their geometry does) - but
        the layer's own PRESENCE can: a SwitchLayer's active child changes
        across the range, so a child is only a "mesh" event on the frames
        it is actually the active one. `active_frames` tracks exactly which
        frame values each layer was seen on; `_windows` groups those into
        maximal CONTIGUOUS runs, and each run becomes its own emitted Lottie
        layer with its own `ip`/`op` (a child active twice, non-
        consecutively, is emitted twice - see `_windows`'s own docstring).
        A layer present for the whole range simply gets one window equal to
        the whole range, so this subsumes the pre-Task-7 behaviour rather
        than special-casing it.

        Moho draws its layer list back to front, which is the order
        walk_render_tree yields "mesh" events in.  Lottie draws the FIRST
        layer in its own list on top, so the finished list is reversed -
        the single easiest thing in this writer to get wrong without
        noticing: the artwork would still look right, just with the wrong
        parts in front.

        Also handles "enter"/"exit" now (Task 4 skipped both, keeping only
        "mesh"): a small `mask_stack`, rebuilt fresh every frame, mirrors
        exactly what Exporter.export_document's own `render_scope` does with
        `clip` - push this container's own mask sources (or None) on
        "enter", pop on "exit", and a "mesh" item picks up ONLY
        `mask_stack[-1]` (never a grandparent's mask - see Task 6's plan
        notes for why that matches `emit`'s own scoping). Mask source
        geometry is measured to vary significantly across frames (17 of 17
        masked containers in SketchBone.animeproj alone), so it is collected
        per frame here, exactly like shape geometry, not evaluated once.
        """
        # The CANONICAL draw order comes from the document's own static
        # structure, not from "the order layers were first seen while
        # walking frames" - a SwitchLayer child that only becomes active
        # partway through the range (e.g. a lip-sync mouth shape) would
        # otherwise be appended to `order` far later than its structural
        # sibling position, scrambling its draw order relative to every
        # ALWAYS-present layer once collected.reverse() runs. vector_layers()
        # walks every mesh layer in file order regardless of which
        # SwitchLayer child happens to be active at any one frame, so it
        # is the right source of truth for relative order; a layer that
        # turns out to never actually be active in ANY frame (e.g. a
        # SwitchLayer alternative nothing ever selects) is dropped later,
        # once it is clear no accumulator was ever built for it.
        order: list = [layer for _ancestors, layer in self.document.vector_layers()]
        accumulators: dict = {}               # id(layer) -> list of per-shape accumulators
        mask_data: dict = {}                  # id(layer) -> {"has_mask": bool|None, "per_frame": [...]}
        active_frames: dict = {}              # id(layer) -> frame VALUES it was a "mesh" event on
        union_band_widths: dict = {}          # id(layer) -> {id(shape): stroke_width_px}
        for frame in frames:
            mask_stack: list = []
            for item in walk_render_tree(self.exporter, frame, include_hidden):
                if item.event == "enter":
                    sources = None
                    if item.layer is not None:        # None only for the virtual root
                        raw = self.exporter._mask_sources_bezier(item.layer, item.ancestors, frame)
                        sources = raw if raw else None
                    mask_stack.append(sources)
                    continue
                if item.event == "exit":
                    mask_stack.pop()
                    continue

                # "mesh"
                lid = id(item.layer)
                first_time = lid not in accumulators
                if first_time:
                    accumulators[lid] = []
                    mask_data[lid] = {"has_mask": None, "per_frame": []}
                    active_frames[lid] = []
                    union_band_widths[lid] = self._prepare_union_band_widths(item.layer.mesh, frame)
                active_frames[lid].append(frame)
                self._accumulate_frame(item, frame, accumulators[lid], first_time,
                                       union_band_widths[lid])

                active_mask = mask_stack[-1] if mask_stack else None
                applies = (not item.exempt) and active_mask is not None
                info = mask_data[lid]
                if info["has_mask"] is None:
                    info["has_mask"] = applies
                elif info["has_mask"] != applies:
                    raise ValueError(
                        f"{item.layer.name!r}: whether it is masked changed "
                        f"at frame {frame} - masking configuration appears "
                        f"to be animated, which this exporter does not yet "
                        f"handle")
                if applies:
                    info["per_frame"].append(active_mask)

        collected = []
        for layer in order:
            lid = id(layer)
            if lid not in active_frames:
                # In vector_layers()'s structural order but never actually
                # the active child of its SwitchLayer (or otherwise never
                # visible) in any sampled frame - nothing to draw, ever.
                continue
            layer_frames = active_frames[lid]
            info = mask_data[lid]
            for start, end in self._windows(layer_frames):
                window_frames = layer_frames[start:end]
                window_accs = self._slice_accumulators(accumulators[lid], start, end)
                cross_mask = None
                if info["has_mask"]:
                    cross_mask = self._finalize_mask(
                        layer, info["per_frame"][start:end], window_frames)
                # A single-frame preview export (`--frame N`, len(frames) ==
                # 1) is a still, not a window: it should hold for the whole
                # document range, exactly like Task 3's original behaviour,
                # not collapse to a one-frame-long span just because only
                # one frame was ever sampled. Real windowing (from a
                # SwitchLayer's active child changing) only means something
                # when the full frame range was actually walked.
                if len(frames) == 1:
                    ip, op = self.document.start_frame, self.document.end_frame + 1
                else:
                    ip, op = window_frames[0], window_frames[-1] + 1

                # One Moho mesh layer normally becomes one Lottie layer, but
                # a combo_mode==3 (intersect) group, or a combo_mode 0/1
                # (union) group with more than one member, each split it
                # into several - see _split_boolean_groups/_split_into_
                # chunks for the three chunk kinds this produces. The
                # common case (no combo_mode anywhere in this mesh)
                # produces exactly one "plain" chunk covering the whole
                # layer, same as before this split existed.
                groups = self._split_boolean_groups(window_accs)
                chunks = self._split_into_chunks(groups)
                multi = len(chunks) > 1
                for chunk_index, chunk in enumerate(chunks):
                    kind = chunk["kind"]
                    if kind == "union_exclude":
                        member = chunk["member"]
                        name0 = member["name"]
                        shapes = [self._finalize_outline_group(layer, member, window_frames, name0)]
                        mask_properties = self._combo_mode_union_mask_properties(
                            layer, member, chunk["others"], window_frames, cross_mask)
                    else:
                        shapes = self._finalize_shapes(
                            layer, chunk["accs"], window_frames,
                            skip_outline=chunk.get("skip_outline", frozenset()))
                        if not shapes:
                            continue
                        if kind == "clip":
                            mask_properties = self._combined_mask_properties(
                                layer, cross_mask, chunk["base"], window_frames)
                        else:                                  # "plain"
                            mask_properties = cross_mask
                    # "#N" rather than " N" - a space-separated digit suffix
                    # could collide with another Moho layer's own name (e.g.
                    # this mesh's own combo_mode split of "Leg_F" landing on
                    # chunk index 2 must not produce the string "Leg_F 2",
                    # which is a DIFFERENT layer's actual name in this same
                    # document).
                    name = f"{layer.name}#{chunk_index}" if multi else layer.name
                    if kind == "clip" and mask_properties is None:
                        # _combined_mask_properties's own "needs nesting"
                        # signal - see _nested_group_mask_layer.
                        group_entries = self._group_mask_entries(
                            layer, chunk["base"], window_frames)
                        collected.append(self._nested_group_mask_layer(
                            shapes, group_entries, cross_mask, ip, op, name))
                        continue
                    collected.append(self._shape_layer(name, shapes, ip, op, mask_properties))
        collected.reverse()                  # Moho back-to-front -> Lottie front-to-back
        for index, layer in enumerate(collected, start=1):
            layer["ind"] = index
        return collected

    @staticmethod
    def _windows(active_frames: list) -> list:
        """Split `active_frames` (the frame VALUES one layer was seen on, in
        ascending order - not necessarily every frame in the document, and
        not necessarily contiguous) into (start_index, end_index) slices,
        one per maximal run of CONSECUTIVE integer frames.

        A layer present for the whole document range gets exactly one
        window spanning it. A SwitchLayer child active in two separate
        stretches of time (Moho's key channels snap to the left keyframe
        with no interpolation, so "active" is discrete, and a run of
        consecutive frames is unambiguous) gets two windows - each becomes
        its own emitted Lottie layer with its own `ip`/`op`, since Lottie
        has no way to give one layer two disjoint visibility spans.
        """
        windows = []
        start = 0
        for i in range(1, len(active_frames) + 1):
            if i == len(active_frames) or active_frames[i] != active_frames[i - 1] + 1:
                windows.append((start, i))
                start = i
        return windows

    @staticmethod
    def _slice_accumulators(accs: list, start: int, end: int) -> list:
        """A copy of `accs` (one layer's per-shape accumulators) with every
        per-frame list cut down to `[start:end]` - the frame-invariant
        fields (name, colours, outline_kind, ...) are shared, not copied,
        since _finalize_shapes/_finalize_outline_group never mutate them."""
        sliced = []
        for acc in accs:
            copy = dict(acc)
            copy["fill_per_frame"] = acc["fill_per_frame"][start:end]
            copy["outline_per_frame"] = acc["outline_per_frame"][start:end]
            copy["outline_width_per_frame"] = acc["outline_width_per_frame"][start:end]
            sliced.append(copy)
        return sliced

    def _shape_layer(self, name: str, shapes: list, ip: float, op: float,
                      mask_properties: list = None) -> dict:
        """A Lottie shape layer with an identity transform.

        Identity is correct because the geometry is already baked into
        canvas pixels, which is also Lottie's own coordinate system: pixels,
        y down, origin at the top left - no conversion needed.

        `ip`/`op` are the layer's OWN visibility window - the whole document
        range for an always-present layer, a narrower one for a SwitchLayer
        child (see _windows) - not necessarily `self.document.start_frame`/
        `end_frame + 1`.
        """
        layer = {
            "ty": 4, "nm": name, "ks": identity_transform(),
            "ao": 0, "shapes": shapes,
            "ip": float(ip),
            "op": float(op),
            "st": 0.0,
        }
        if mask_properties:
            layer["hasMask"] = True
            layer["masksProperties"] = mask_properties
        return layer

    def _finalize_mask(self, layer, per_frame_sources: list, frames) -> list:
        """Every mask-source shape's subpaths, flattened and keyframed, as
        Lottie masksProperties entries - one entry per subpath, mode "a"
        (union), matching how build_path_bezier's own multiple subpaths
        become multiple "sh" elements elsewhere in this file. `_assert_stable`
        applies here too: mask-source vertex/subpath counts must not change
        across frames, for the same reason shape geometry can't.

        The exclude-width carve-out Exporter._mask_element applies on the
        SVG side (a mask source's own stroke band is cut back OUT of the
        mask so it stays visible on top of whatever the mask clips - see
        Exporter._mask_source_shapes's own docstring) IS reproduced here:
        Exporter._mask_source_shapes_bezier already built each source's
        exclusion band as filled Lottie geometry (self.tapered_outliner.
        build_bezier at that source's own uniform stroke width), since
        Lottie's mask model has only filled shapes, no "stroke this path
        as a mask" primitive the way an SVG <mask> does. Every source's own
        FILL entries (mode "a", union) come first, exactly matching the SVG
        writer's own paint order ("each source shape's fill is painted
        white... then... painted AFTER, so it wins" - Exporter._mask_element),
        then every source's own exclusion band is appended (mode "s",
        subtract), carving that band back OUT of the accumulated union
        regardless of layer order - the same "independent of paint order"
        property _mask_element gets from painting the band ON TOP in SVG.
        """
        n_sources = len(per_frame_sources[0])
        # per_frame_sources[f] is a list of (beziers, exclude_width,
        # exclude_band) - one per mask-source SHAPE, all captured while
        # walking `layer`'s ancestor chain (see _build_layers).  Flatten
        # every source's FILL beziers to one list of subpath dicts per
        # frame first, exactly as before this fix - the union region a
        # source's exclusion band later carves into is unchanged.
        fill_per_frame = [[subpath for beziers, _ew, _eb in sources for subpath in beziers]
                           for sources in per_frame_sources]
        self._assert_stable(layer, "<mask>", "mask", fill_per_frame)
        entries = self._mask_entries(fill_per_frame, frames)

        for i in range(n_sources):
            _beziers0, exclude_width0, band0 = per_frame_sources[0][i]
            if exclude_width0 <= 0:
                continue
            if not band0:
                # Only reachable if TaperedStrokeOutliner.build_bezier
                # itself returned nothing for a non-degenerate, non-tapered,
                # non-brush outline - not expected, but a silently-dropped
                # exclusion would be worse than a counted one; see
                # WARNING_EXPLANATIONS.
                self.warnings["mask_stroke_exclusion"] += 1
                continue
            band_per_frame = [sources[i][2] or [] for sources in per_frame_sources]
            self._assert_stable(layer, f"<mask exclusion {i}>", "mask exclusion band",
                                band_per_frame)
            entries += self._mask_entries(band_per_frame, frames, mode="s")
        return entries

    def _mask_entries(self, per_frame_flat: list, frames, mode: str = "a") -> list:
        """One Lottie masksProperties entry per subpath in `per_frame_flat`
        (one flattened subpath list per frame - see _finalize_mask and
        _group_mask_entries, its two callers), all sharing `mode`."""
        return [{"inv": False, "mode": mode, "pt": self._path_property(list(per_subpath), frames),
                 "o": {"a": 0, "k": 100}, "x": {"a": 0, "k": 0}}
                for per_subpath in zip(*per_frame_flat)]

    def _group_mask_entries(self, layer, base_accs: list, frames) -> list:
        """masksProperties entries (mode "a", i.e. union) built from
        `base_accs`' own already-collected fill geometry - the Lottie
        counterpart of ShapeGroupRenderer._mask_union in moho2svg.py: a
        combo_mode==3 shape is clipped to the union of its OWN group's
        combo_mode 0/1 (base) members, not to the whole mesh or to any
        cross-layer mask (see _split_boolean_groups/_split_into_chunks for
        how a mesh's shapes are partitioned into these groups, and
        _combined_mask_properties for combining this with an ALSO-active
        cross-layer mask, if any).
        """
        per_frame_flat = [
            [subpath for acc in base_accs for subpath in acc["fill_per_frame"][f]]
            for f in range(len(frames))]
        self._assert_stable(layer, "<combo_mode group>", "group mask", per_frame_flat)
        return self._mask_entries(per_frame_flat, frames)

    def _prepare_union_band_widths(self, mesh, frame0) -> dict:
        """{id(shape): stroke_width_px} for every raw `Shape` (moho2svg.py's
        Shape, not an accumulator dict - accumulators do not exist yet the
        first time this runs) that is a combo_mode 0/1 (base) member of a
        boolean-combination group with MORE THAN ONE base member.

        `_accumulate_frame` consults this to decide which shapes need an
        extra `union_band_per_frame` entry (that shape's own outline as
        FILLED band geometry, at the width computed here) alongside their
        ordinary fill/outline geometry - material `_combo_mode_union_mask_
        properties` later uses to exclude ONE base member's stroke from
        redrawing the boundary shared with ANOTHER, matching
        ShapeGroupRenderer._flush's own combo_mode 0/1 handling in
        moho2svg.py (a union member's outline is clipped to exclude every
        other base member's fill, using the GROUP's style - not each
        member's own - since Moho renders every union member's outline
        with the base member's line style; see moho2svg.py's BOOLEAN SHAPE
        COMBINATIONS section, "the *combined* outline is stroked using the
        styling of the group's first (base) member, not its own"). Hence
        one width per GROUP here, taken from the group's first/base member
        and applied to every member's own band, not each member's
        individual line_width.

        Computed directly from `mesh.shapes`' own STATIC combo_mode (never
        varies by frame - see _accumulate_frame's docstring) and evaluated
        once at `frame0` (style never animates in this corpus - the same
        assumption _new_accumulator itself already makes for every other
        style field), ahead of any per-frame accumulation - mirrors
        _split_boolean_groups' own grouping rule, just on raw Shape objects
        instead of already-built accumulator dicts.
        """
        exp = self.exporter
        result: dict = {}
        base: list = []
        clip: list = []

        def flush():
            if len(base) > 1:
                base_shape = base[0]
                widths = self._point_widths(mesh, base_shape.edges, frame0)
                point_width = widths[0] if widths else 1.0
                line_width = exp.eval(base_shape.style.line_width, frame0)
                width_px = exp._stroke_width_px(line_width, point_width)
                for shape in base:
                    result[id(shape)] = width_px

        for shape in mesh.shapes:
            if not shape.edges:
                continue
            combo_mode = shape.combo_mode if shape.combo_mode in (0, 1, 3) else 0
            if combo_mode == 0 and (base or clip):
                flush()
                base, clip = [], []
            (clip if combo_mode == 3 else base).append(shape)
        flush()
        return result

    def _split_boolean_groups(self, accs: list) -> list:
        """Partition one mesh's shape accumulators (in file order) into
        contiguous boolean-combination groups, exactly like
        ShapeGroupRenderer's own grouping in moho2svg.py: a combo_mode==0
        shape starts a new group, combo_mode 1/3 shapes join the group in
        progress (see _new_accumulator for why combo_mode is guaranteed to
        already be one of 0/1/3 here). Returns [(base_accs, clip_accs), ...]
        per group - base_accs are combo_mode 0/1 members (drawn plainly,
        never clipped), clip_accs are combo_mode==3 members (drawn clipped
        to base_accs' own union - see _group_mask_entries).
        """
        groups: list = []
        base: list = []
        clip: list = []
        for acc in accs:
            if acc["combo_mode"] == 0 and (base or clip):
                groups.append((base, clip))
                base, clip = [], []
            if acc["combo_mode"] == 3:
                clip.append(acc)
            else:
                base.append(acc)
        if base or clip:
            groups.append((base, clip))
        return groups

    @staticmethod
    def _split_into_chunks(groups: list) -> list:
        """A list of chunk dicts, in file order, from `_split_boolean_groups`'
        own output - one of:

          {"kind": "plain", "accs": [...], "skip_outline": frozenset(...)}
          {"kind": "clip", "accs": [...], "base": [...]}
          {"kind": "union_exclude", "member": acc, "others": [...]}

        Each chunk becomes one Lottie layer - see _build_layers, which
        appends these in this same file order so the existing
        Moho-back-to-front -> Lottie-front-to-back `collected.reverse()`
        still produces the right z-order between them, exactly as it
        already did back when one Moho layer was always exactly one Lottie
        layer.

        Consecutive groups with no combo_mode==3 member and no multi-member
        base merge into one "plain" chunk (no masking needed at all). A
        group WITH a combo_mode==3 member gets its own "clip" chunk for
        those members (needing a group mask built from the base - see
        _group_mask_entries/_combined_mask_properties); a base's FILL is
        never clipped by this, only a combo_mode==3 member's is, matching
        moho2svg.py's own _render_shape.

        A group whose base has MORE THAN ONE member additionally gets one
        "union_exclude" chunk per base member that has its own outline -
        see _combo_mode_union_mask_properties for what it excludes and
        why. `skip_outline` on the surrounding "plain" chunk names exactly
        those members, so _finalize_shapes still emits their FILL there
        (never clipped) while their OUTLINE moves to its own masked chunk.
        Both a "clip" and any "union_exclude" chunks for the SAME group are
        placed together, right after that group's own contribution to the
        current "plain" chunk (which is flushed first) - approximating
        ShapeGroupRenderer._flush's own SVG timing (every group's fills
        painted immediately, in file order, then that SAME group's
        outlines - base and combo_mode==3 members alike - painted together
        once the group closes) without tracking file order at finer grain
        than "this group's own contribution" for either kind.
        """
        chunks: list = []
        plain_run: list = []
        skip_outline: set = set()

        def flush_plain():
            nonlocal plain_run, skip_outline
            if plain_run:
                chunks.append({"kind": "plain", "accs": plain_run,
                               "skip_outline": frozenset(skip_outline)})
            plain_run, skip_outline = [], set()

        for base, clip in groups:
            plain_run.extend(base)
            group_exclusions: list = []
            if len(base) > 1:
                for member in base:
                    if member["outline_kind"] is not None:
                        skip_outline.add(id(member))
                        others = [m for m in base if m is not member]
                        group_exclusions.append((member, others))
            if clip or group_exclusions:
                flush_plain()
            if clip:
                chunks.append({"kind": "clip", "accs": clip, "base": base})
            for member, others in group_exclusions:
                chunks.append({"kind": "union_exclude", "member": member, "others": others})
        flush_plain()
        return chunks

    def _combo_mode_union_mask_properties(self, layer, member_acc: dict, other_accs: list,
                                          frames, cross_mask) -> list:
        """masksProperties excluding a combo_mode 0/1 (union) member's own
        stroke from redrawing the boundary it shares with its group's
        OTHER base members - the Lottie counterpart of ShapeGroupRenderer.
        _mask_subtraction in moho2svg.py.

        Same recipe as that SVG method, built from data _accumulate_frame/
        _prepare_union_band_widths already collected:
          1. A padded bounding box covering `member_acc`'s own fill and
             every one of `other_accs`' fills, as the starting region -
             mode "a" normally, or "i" to narrow `cross_mask`'s own already-
             accumulated region if this layer ALSO carries a cross-layer
             mask (see _combined_mask_properties for the same "i"-after-"a"
             technique - exact here regardless of how many cross_mask
             entries there are, since the box is always a SINGLE shape, not
             a union of several like the case that method has to fall back
             on).
          2. Each other member's own fill subtracted out of it (mode "s") -
             punches a hole whose edge exactly follows each other member's
             boundary.
          3. Each other member's own outline, already built as filled band
             geometry at the group's stroke width in its own accumulator's
             `union_band_per_frame` (see _prepare_union_band_widths), added
             back on top (mode "a") - restores a stroke-width-wide band
             right at the hole's edge, so `member_acc`'s own stroke meets
             the neighbour's instead of stopping one stroke-width short
             at the crossing - see _mask_subtraction's own docstring for
             why that band exists at all.
        """
        padding = self.exporter.settings.mask_padding
        box_per_frame_flat = []
        for f in range(len(frames)):
            subpaths = list(member_acc["fill_per_frame"][f])
            for acc in other_accs:
                subpaths += acc["fill_per_frame"][f]
            xs = [v[0] for b in subpaths for v in b["v"]]
            ys = [v[1] for b in subpaths for v in b["v"]]
            x0, y0 = min(xs) - padding, min(ys) - padding
            x1, y1 = max(xs) + padding, max(ys) + padding
            box_per_frame_flat.append([{"v": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                                         "i": [[0, 0], [0, 0], [0, 0], [0, 0]],
                                         "o": [[0, 0], [0, 0], [0, 0], [0, 0]], "c": True}])

        entries = list(cross_mask) if cross_mask else []
        box_mode = "i" if cross_mask else "a"
        entries += self._mask_entries(box_per_frame_flat, frames, mode=box_mode)
        for acc in other_accs:
            fill_flat = [acc["fill_per_frame"][f] for f in range(len(frames))]
            entries += self._mask_entries(fill_flat, frames, mode="s")
        for acc in other_accs:
            band_flat = [acc["union_band_per_frame"][f] for f in range(len(frames))]
            self._assert_stable(layer, acc["name"], "union exclusion band", band_flat)
            entries += self._mask_entries(band_flat, frames, mode="a")
        return entries

    def _combined_mask_properties(self, layer, cross_mask, base_accs: list, frames):
        """masksProperties for one combo_mode==3 chunk: its own group's
        base union (_group_mask_entries), intersected against `cross_mask`
        (this layer's own cross-layer mask, from Moho's masking/group_mask
        system - None if this layer carries none) when both apply at once.

        Lottie evaluates masksProperties SEQUENTIALLY, each entry combining
        with the region accumulated so far via its own mode: "a" unions,
        "i" intersects. `cross_mask`'s own entries already union together
        (mode "a" - see _finalize_mask) into one region U. Appending the
        group's own base union with mode "i" narrows U down to U ∩ base
        exactly - but only when that base union is itself a SINGLE subpath:
        a lone "i" entry can only narrow the running region once, and any
        entry appended after it can only union more area back in (mode
        "a") or cut more out (mode "s") - neither reconstructs "intersect
        with the union of several separate shapes" from inside a sequential
        chain.

        Returns None - not a fallback, a signal - when the base union needs
        more than one subpath AND `cross_mask` is set: that combination
        cannot be expressed with a flat sequential list at all. The caller
        (_build_layers) then reaches for _nested_group_mask_layer instead,
        which composes the same two constraints EXACTLY via a
        precomposition (two independent masking passes, nested, rather
        than one flat list trying to express both at once) - so nothing
        this exporter produces is ever less than exact here; this is a
        dispatch point, not an approximation.
        """
        group_entries = self._group_mask_entries(layer, base_accs, frames)
        if not cross_mask:
            return group_entries
        if len(group_entries) != 1:
            return None
        return cross_mask + [{**group_entries[0], "mode": "i"}]

    def _nested_group_mask_layer(self, shapes: list, group_entries: list, cross_mask: list,
                                 ip: float, op: float, name: str) -> dict:
        """The exact fallback _combined_mask_properties itself cannot
        express: `shapes` (a combo_mode==3 chunk's own already-finalized
        Lottie groups) masked by its OWN group union (`group_entries`,
        exact and unconditional - _group_mask_entries always works
        regardless of how many subpaths it needs, since nothing else has
        to combine with it INSIDE the same flat list here), wrapped in a
        precomposition so `cross_mask` can be applied to the OUTER layer
        that references it - two independent masking passes, composed by
        nesting rather than by trying to sequence both into one list.

        A precomp-referencing layer ("ty": 0) renders its target precomp's
        content exactly like an ordinary visual layer renders its own -
        offscreen, then composited as one unit - so a mask on THIS layer
        clips that already-masked result precisely the same way a mask
        clips a plain shape layer's content elsewhere in this file. This
        is a standard, well-supported Lottie/After Effects composition
        technique (precomp + mask), unlike the `mm` merge-path operator
        the design doc's own § 2.2 rejected combo_mode support over in the
        first place - a completely different Lottie primitive, not a
        retry of that same rejected idea.
        """
        inner = self._shape_layer(name, shapes, ip, op, group_entries)
        inner["ind"] = 1
        asset_id = f"nested_mask_{self._next_asset_id()}"
        self._assets.append({"id": asset_id, "layers": [inner]})
        outer = {
            "ty": 0, "nm": name, "refId": asset_id,
            "ks": identity_transform(), "ao": 0,
            "w": int(self.document.width), "h": int(self.document.height),
            "ip": float(ip), "op": float(op), "st": 0.0,
            "hasMask": True, "masksProperties": cross_mask,
        }
        return outer

    def _point_widths(self, mesh, edges, frame: float) -> list:
        """The interpolated width at every point touched by `edges`, at
        `frame` - the same lookup ShapeGroupRenderer._point_widths performs,
        reproduced here since that method needs a ShapeGroupRenderer
        instance this writer never builds (it never renders SVG strings)."""
        point_indices = {mesh.curves[e.curve].points[e.segment].point_index
                          for e in edges}
        return [self.exporter.eval(mesh.points[i].width, frame) for i in point_indices]

    def _keyframes(self, frames, s_values: list) -> list:
        """Build a Lottie keyframe list from parallel `frames`/`s_values`
        (`s_values[i]` already shaped as that keyframe's own "s" - a one-
        element list wrapping a bezier value, or a plain list of numbers -
        see this method's three callers), with LINEAR "i"/"o" easing added
        to every keyframe but the last.

        Confirmed empirically (outside this codebase, with a hand-built
        two-keyframe rectangle) that lottie-web's SVG renderer (5.13.0)
        does not merely interpolate an "a": 1 property incorrectly when its
        keyframes omit "i"/"o" - it renders NOTHING for that property, at
        any frame, even though `properties/base-keyframe` in
        lottie.schema.json marks both fields optional and this writer's
        own --validate already passed without them. This is therefore a
        genuine gap in every animated property this writer has ever
        emitted (path, scalar, point - masksProperties included, since
        _finalize_mask/_group_mask_entries both build their entries
        through _path_property), not something specific to combo_mode or
        cross-layer masking.

        Linear easing ("x"/"y" both running 0->1 in a straight line, i.e.
        no curve at all) is the correct choice here, not merely a safe
        default: every keyframe this writer emits already sits at its own
        EXACT sampled value, one per integer frame in the export range -
        there is no curve to approximate between two already-frame-exact
        points, only a straight interpolation.
        """
        keyframes = [{"t": float(f), "s": s} for f, s in zip(frames, s_values)]
        for kf in keyframes[:-1]:
            kf["o"] = LINEAR_EASE_OUT
            kf["i"] = LINEAR_EASE_IN
        return keyframes

    def _path_property(self, per_frame: list, frames) -> dict:
        """A Lottie path property: static when the geometry never moves,
        keyframed otherwise.

        Writing an unmoving shape once instead of once per frame is what
        keeps the file in single-digit megabytes rather than hundreds -
        measured at roughly 293 MB versus about 10 MB across this
        repository's sample documents.
        """
        if all(b == per_frame[0] for b in per_frame[1:]):
            return {"a": 0, "k": per_frame[0]}
        return {"a": 1, "k": self._keyframes(frames, [[b] for b in per_frame])}

    def _scalar_property(self, per_frame: list, frames) -> dict:
        """A Lottie scalar property (e.g. stroke width): static when the
        value never changes across frames, keyframed otherwise.

        Stroke width depends on exporter._layer_scale, which is a per-frame
        value in principle (an animated bone scale would change it) - this
        exists so that case degrades to a correct keyframed "w" instead of a
        wrong static one, if it ever occurs.

        It does NOT currently occur anywhere in this repository's sample
        corpus: a first attempt to measure it grouped scale samples by
        layer.name, which conflated distinct layers that happen to share a
        name (WhatIsBone.animeproj has three separately-modelled layers all
        named "goz-sol", each with its own CONSTANT scale of 1.0, 0.79 and
        1.0) into what looked like one layer whose scale varies by 21% over
        time. Re-measured keyed by layer IDENTITY instead: 0 of 103 layers
        in WhatIsBone.animeproj, 0 of 21 in Bandit.mohoproj, 0 of 86 in
        SketchBone.animeproj actually vary across their own full frame
        range. So this method's keyframed branch is exercised by no
        document tested so far - kept anyway, since a genuinely
        scale-animated bone is a real Moho capability, not a fabricated
        edge case, and the static branch already covers everything actually
        observed.
        """
        if all(abs(v - per_frame[0]) < 1e-9 for v in per_frame[1:]):
            return {"a": 0, "k": per_frame[0]}
        return {"a": 1, "k": self._keyframes(frames, [[v] for v in per_frame])}

    def _point_property(self, per_frame_points: list, frames) -> dict:
        """A Lottie 2D point property (e.g. a gradient's start/end point):
        static when it never changes across frames, keyframed otherwise -
        the 2D-point counterpart of _scalar_property.  `per_frame_points` is
        one (x, y) tuple per frame.

        A keyframe's own "s" must be a FLAT array of numbers here - Lottie's
        position/vector-property keyframes (schema: vector-keyframe, used by
        both position-property and, via its "s" field being values/vector,
        every plain vector) store "s": [x, y] directly, NOT "s": [[x, y]].
        That extra wrapping level is correct for a BEZIER keyframe's own "s"
        (schema: bezier-keyframe, which explicitly wants an array containing
        exactly one bezier value - see _sh_elements/_path_property) but
        wrong here; conflating the two produced files that failed schema
        validation (caught by adding --validate in this same task) even
        though every geometry check up to that point had already passed,
        since none of them parse "s" against the schema, only against each
        other's own output.
        """
        if all(p == per_frame_points[0] for p in per_frame_points[1:]):
            return {"a": 0, "k": list(per_frame_points[0])}
        return {"a": 1,
                "k": self._keyframes(frames, [list(p) for p in per_frame_points])}

    def _sh_elements(self, per_frame_subpaths: list, frames) -> list:
        """One Lottie "sh" element per subpath, each a (possibly keyframed)
        _path_property built across `frames`.

        `per_frame_subpaths` is one list-of-bezier-dicts PER FRAME (i.e.
        build_path_bezier()'s own return value, accumulated once per
        frame); this transposes it into one list-of-per-frame-values PER
        SUBPATH, which is what _path_property expects.  Every frame is
        asserted (by the caller, before this runs) to agree on subpath
        count - see _assert_stable.
        """
        return [{"ty": "sh", "ks": self._path_property(list(per_subpath), frames)}
                for per_subpath in zip(*per_frame_subpaths)]

    def _assert_stable(self, layer, shape_name, kind: str, per_frame: list) -> None:
        """Raise if a shape's traced outline changes structure - subpath
        count, vertex count per subpath, or open/closed - across `frames`,
        which would make Lottie's own keyframe interpolation undefined
        (mismatched vertex counts between two path keyframes).

        Measured never to happen for real Moho documents: 0 unstable of
        2,659 shapes, sampled at 12 frames each across 18 documents (see
        docs/moho-to-lottie-design.md section 5.3). A failure here means a
        document exercises something genuinely new, not that this check is
        noise, so it is not silently tolerated.
        """
        base = [(len(b["v"]), b["c"]) for b in per_frame[0]]
        for frame_index, subpaths in enumerate(per_frame[1:], start=1):
            got = [(len(b["v"]), b["c"]) for b in subpaths]
            if got != base:
                raise ValueError(
                    f"{layer.name!r} shape {shape_name!r} ({kind}): outline "
                    f"structure changed between frame index 0 and "
                    f"{frame_index} ({base} -> {got}) - Lottie cannot "
                    f"keyframe this; see moho-to-lottie-design.md section 5.3")

    def _accumulate_frame(self, item, frame: float, accs: list, first_time: bool,
                          union_band_widths: dict) -> None:
        """Extract ONE frame's worth of data for every shape of `item`'s
        layer, appending to `accs` (one accumulator dict per shape, created
        on `first_time` and reused - by matching POSITION, not identity -
        on every later frame, since a Mesh's own shape list/order never
        changes across frames).

        Everything that reads exporter.eval()/to_px()/_layer_scale happens
        HERE, synchronously, while `item` is the current RenderItem - see
        _build_layers's own docstring for why that is load-bearing.  Style
        (colour, line width, brush/taper classification) is captured only
        ONCE, inside _new_accumulator, on `first_time`.

        `union_band_widths` is `{id(shape): group_stroke_width_px}` from
        `_prepare_union_band_widths`, for every shape that is a combo_mode
        0/1 (base) member of a boolean group with more than one base
        member - see that method's own docstring. A qualifying shape gets
        an EXTRA `union_band_per_frame` entry alongside its ordinary fill/
        outline geometry: its own outline as FILLED band geometry at the
        group's stroke width, needed (whether or not this particular shape
        itself has an outline) as material for EXCLUDING it from another
        group member's own stroke - see _combo_mode_union_mask_properties.
        """
        exp = self.exporter
        mesh = item.layer.mesh
        shape_index = 0
        for shape in mesh.shapes:
            if not shape.edges:
                continue
            if first_time:
                accs.append(self._new_accumulator(item.layer, shape, frame))
            acc = accs[shape_index]
            shape_index += 1

            acc["fill_per_frame"].append(
                build_path_bezier(item.geometries, shape.edges, item.to_px))

            band_width = union_band_widths.get(id(shape))
            if band_width is not None:
                acc["union_band_per_frame"].append(exp.tapered_outliner.build_bezier(
                    item.geometries, shape.edges, item.to_px, band_width))

            if acc["outline_kind"] == "taper":
                width_px = exp._stroke_width_px(acc["line_width"], 1.0)
                acc["outline_per_frame"].append(exp.tapered_outliner.build_bezier(
                    item.geometries, shape.edges, item.to_px, width_px))
            elif acc["outline_kind"] == "stroke":
                widths = self._point_widths(mesh, shape.edges, frame)
                # Compare against the STORED tapered flag (from frame0), not
                # against outline_kind == "stroke" - a brush-styled shape's
                # outline_kind is ALWAYS "stroke" (the brush fallback, see
                # _new_accumulator) even when it is genuinely tapered, so
                # checking outline_kind here would flag every brush+tapered
                # shape as "changed" on its very first frame.  This bug was
                # caught immediately: 12 of 19 sample documents raised on
                # their second frame the first time this check was written.
                other_tapered = (max(widths) - min(widths) > 1e-6) if widths else False
                if other_tapered != acc["tapered"]:
                    raise ValueError(
                        f"{item.layer.name!r} shape {acc['name']!r}: tapered-ness "
                        f"of the outline changes at frame {frame} - point width "
                        f"appears to be animated, which this exporter does not "
                        f"yet handle")
                point_width = widths[0] if (widths and not other_tapered) else 1.0
                width_px = exp._stroke_width_px(acc["line_width"], point_width)
                acc["outline_width_per_frame"].append(width_px)
                # visible_only=True + close=False, NEVER close=True, matching
                # build_path_d()'s own stroke_path call in _render_shape -
                # see build_path_bezier()'s docstring for why an open path
                # renders a genuinely different stroke join at the seam than
                # a closed one.
                acc["outline_per_frame"].append(build_path_bezier(
                    item.geometries, shape.edges, item.to_px,
                    visible_only=True, close=False))

    def _new_accumulator(self, layer, shape, frame0: float) -> dict:
        """Build shape's per-frame accumulator, capturing everything that is
        NOT frame-dependent in this corpus (style, brush/taper
        classification - see _accumulate_frame's own docstring) exactly
        once, synchronously, while frame0's RenderItem is current.
        """
        exp = self.exporter
        combo_mode = shape.combo_mode
        if combo_mode not in (0, 1, 3):
            # Matches ShapeGroupRenderer._render_shape's own fallback in
            # moho2svg.py: an unrecognised value is drawn as a plain
            # replace shape rather than aborting the export.
            self.warnings["combo_mode_unknown"] += 1
            combo_mode = 0
        style = shape.style

        outline_kind = None
        line_width = None
        outline_color = None
        outline_cap = None
        tapered = False
        if shape.has_outline:
            line_width = exp.eval(style.line_width, frame0)
            outline_color = Color.from_raw(exp.eval(style.line_color, frame0))
            widths0 = self._point_widths(layer.mesh, shape.edges, frame0)
            tapered = (max(widths0) - min(widths0) > 1e-6) if widths0 else False
            if style.brush_name:
                self.warnings["brush"] += 1
            # A brush-styled shape's outline_kind is ALWAYS "stroke" (the
            # brush fallback), even when it is genuinely tapered - `tapered`
            # itself is stored separately below and is what
            # _accumulate_frame actually checks for cross-frame stability,
            # since outline_kind alone conflates two different questions.
            outline_kind = "taper" if (tapered and not style.brush_name) else "stroke"
            outline_cap = LINE_CAPS.get(style.line_cap_name(), 2)

        fill_color = None
        gradient = None
        if shape.has_fill:
            if isinstance(style.fill_style, dict) and \
                    style.fill_style.get("type") == "SS_Gradient2":
                gradient = self._eval_gradient(shape, style.fill_style, frame0)
            if gradient is None:
                # No gradient, or fewer than 2 stops - Exporter._build_gradient
                # falls back to the shape's own flat fill_color in exactly
                # this case (see _render_shape: `paint = fill_hex` is the
                # default, only overridden when the gradient def succeeds),
                # so this reproduces that fallback rather than a different one.
                if isinstance(style.fill_style, dict) and \
                        style.fill_style.get("type") == "SS_Gradient2":
                    self.warnings["gradient_too_few_stops"] += 1
                fill_color = Color.from_raw(exp.eval(style.fill_color, frame0))

        return {
            "name": shape.name or "",
            "combo_mode": combo_mode,
            "has_fill": shape.has_fill,
            "fill_color": fill_color,
            "gradient": gradient,
            "fill_per_frame": [],
            "outline_kind": outline_kind,
            "tapered": tapered,
            "line_width": line_width,
            "outline_color": outline_color,
            "outline_cap": outline_cap,
            "outline_per_frame": [],
            "outline_width_per_frame": [],
            "union_band_per_frame": [],
        }

    def _eval_gradient(self, shape, fill_style: dict, frame0: float):
        """The frame-invariant part of a gradient fill - stop colours/
        locations, type, effect scale/rotation - evaluated once, since none
        of these fields is ever animated across this repository's sample
        documents (0 instances checked directly). Returns None when there
        are fewer than 2 stops, mirroring Exporter._build_gradient's own
        "not enough stops to be a gradient at all" fallback to a flat fill.

        Placement (the "s"/"e" points, which depend on the shape's own
        bounding box) is NOT computed here - the box moves frame to frame
        for a deforming shape, so it is computed per frame in
        _finalize_shapes from the already-collected fill_per_frame data,
        no extra exporter calls needed.
        """
        exp = self.exporter
        stops = []
        for stop in fill_style.get("gradients") or []:
            location = exp.eval(stop["location"], frame0)
            color = Color.from_raw(exp.eval(stop["color"], frame0))
            stops.extend([location, color.r, color.g, color.b])
        if len(stops) < 8:                     # fewer than 2 stops (4 numbers each)
            return None
        return {
            "stops": stops,
            "stop_count": len(stops) // 4,
            # Moho's gradient_type is 0 linear / 1 radial; Lottie's own "t"
            # is 1 linear / 2 radial - not the same numbering, so this is
            # written out rather than derived by adding 1.
            "lottie_type": 2 if fill_style.get("gradient_type") == 1 else 1,
            "scale": exp.eval(shape.effect_scale, frame0),
            "rotation": exp.eval(shape.effect_rotation, frame0),
        }

    def _finalize_shapes(self, layer, accs: list, frames, skip_outline: frozenset = frozenset()) -> list:
        """Turn every shape's already-collected per-frame data into Lottie
        shape-group elements.  Pure data transformation - no exp.eval()/
        to_px() calls here, which is exactly why _accumulate_frame had to
        do all of that eagerly (see its own docstring).

        `skip_outline` is a set of `id(acc)` values whose outline is NOT
        emitted here even though `acc["outline_kind"]` is set - used when a
        combo_mode 0/1 (union) member's own outline needs its own masked
        chunk instead (see _split_into_chunks's own "needs_exclusion"
        entries and _combo_mode_union_mask_properties) - its FILL still
        belongs in this call's ordinary, unmasked output.

        Each Moho shape becomes up to TWO Lottie groups - one for its fill,
        one for its outline - rather than one group holding both a "fl" and
        an "st"/second "fl".  Lottie's own shape-element ordering rules
        (which "sh" siblings a paint operator picks up) are not defined by
        the schema (see docs/lottie-and-thorvg.md section 6.4) and are
        UNVERIFIED here; a paint operator scoped to its own group's `it`
        list has no such ambiguity, so this sidesteps the open question
        entirely instead of guessing at it.

        A group holding the outline is listed BEFORE the fill group, since
        Lottie (like Moho/SVG) paints EARLIER shape entries on top - this
        reproduces _render_shape's own paint order (fill drawn first/under,
        the outline drawn after/on top).

        For the SAME reason the whole SHAPE sequence is emitted back to
        front - `reversed` below - exactly as _build_layers reverses the
        layer list.  Moho draws mesh.shapes in file order, so shapes[0] is
        the BACKMOST; under "earlier entries paint on top" it must therefore
        come LAST.  Emitting them in plain file order (what this method used
        to do) inverted every multi-shape layer's internal z-order while
        leaving single-shape layers correct - an inconsistency provable from
        this writer alone, since it already relies on "earlier = on top"
        both for outline-over-fill above and for _build_layers' own
        `collected.reverse()`.  Confirmed against `SketchBone.animeproj`:
        `kalca` draws a light hip fill (shape 0) then a darker belt band
        (shape 1) on top of it - moho2svg.py emits them in that order and
        the reference frames show the belt - while this writer buried the
        belt under the hip fill, so only one of the two colours was ever
        visible.  `ara-cizgi`, the one layer nearby with a SINGLE shape,
        stayed correct throughout, which is the signature of an intra-layer
        ordering fault rather than a geometry or colour one.

        Only the paint order is reversed; the `nm` suffixes are still
        allocated in file order, so a group's name keeps matching the shape
        index moho2svg.py would give it.
        """
        style_names_used: set = set()
        blocks: list = []
        for acc in accs:
            out: list = []
            blocks.append(out)
            # Built unconditionally, even for an outline-only shape, purely
            # as the SVG writer's own "does this shape have any geometry at
            # all" gate - mirrors build_path_d()'s use in _render_shape.
            if not acc["fill_per_frame"][0]:
                continue
            if len(acc["fill_per_frame"]) != len(frames):
                raise ValueError(
                    f"{layer.name!r} shape {acc['name']!r}: only "
                    f"{len(acc['fill_per_frame'])}/{len(frames)} frames were "
                    f"captured for it - its own visibility appears to be "
                    f"animated, which this exporter does not yet handle")
            self._assert_stable(layer, acc["name"], "fill", acc["fill_per_frame"])

            name = acc["name"]
            if name in style_names_used:
                name = f"{name}_{len(style_names_used)}"
            style_names_used.add(name)

            if (acc["outline_kind"] is not None and acc["outline_per_frame"][0]
                    and id(acc) not in skip_outline):
                out.append(self._finalize_outline_group(layer, acc, frames, name))

            if acc["has_fill"]:
                elements = self._sh_elements(acc["fill_per_frame"], frames)
                if acc["gradient"] is not None:
                    elements.append(self._gradient_fill(acc, frames))
                else:
                    color = acc["fill_color"]
                    elements.append({"ty": "fl", "r": FILL_RULE_EVEN_ODD,
                                      "c": {"a": 0, "k": [color.r, color.g, color.b]},
                                      "o": {"a": 0, "k": color.a * 100}})
                elements.append({"ty": "tr", **identity_transform()})
                out.append({"ty": "gr", "nm": f"{name}_fill", "it": elements})
        return [group for block in reversed(blocks) for group in block]

    def _gradient_fill(self, acc: dict, frames) -> dict:
        """A Lottie "gf" gradient fill element from `acc["gradient"]" (the
        frame-invariant stop/type/scale/rotation data - see _eval_gradient)
        plus a PER-FRAME start/end point derived from the shape's own
        already-collected fill geometry.

        Placement reuses the same bounding-box formula
        Exporter._build_gradient uses for its SVG objectBoundingBox percent
        coordinates, converted to this shape's absolute pixel bounding box
        (SVG's percentages are relative to that same box, in the same pixel
        space build_path_bezier() already writes vertices in) - so both
        exporters are wrong in the same way rather than differently.
        Gradient placement precision is an existing KNOWN GAP in
        moho2svg.py, not something this method fixes.
        """
        grad = acc["gradient"]
        starts, ends = [], []
        for subpaths in acc["fill_per_frame"]:
            bbox = self._bbox_of_beziers(subpaths)
            start, end = self._gradient_endpoints(
                bbox, grad["lottie_type"], grad["scale"], grad["rotation"])
            starts.append(start)
            ends.append(end)
        return {"ty": "gf", "r": FILL_RULE_EVEN_ODD, "t": grad["lottie_type"],
                "g": {"p": grad["stop_count"], "k": {"a": 0, "k": grad["stops"]}},
                "s": self._point_property(starts, frames),
                "e": self._point_property(ends, frames),
                "o": {"a": 0, "k": 100}}

    @staticmethod
    def _bbox_of_beziers(subpaths: list) -> tuple:
        """(x0, y0, x1, y1) covering every vertex of every subpath - the
        pixel-space equivalent of an SVG shape's own bounding box, which is
        what `objectBoundingBox` gradient percentages are relative to."""
        xs = [v[0] for b in subpaths for v in b["v"]]
        ys = [v[1] for b in subpaths for v in b["v"]]
        return min(xs), min(ys), max(xs), max(ys)

    @staticmethod
    def _gradient_endpoints(bbox: tuple, lottie_type: int, scale: float,
                             rotation: float) -> tuple:
        """The Lottie "s"/"e" points for one frame, from `bbox` and the same
        scale/rotation/cx=cy=50% formula Exporter._build_gradient uses.

        SVG's objectBoundingBox scales x and y percentages INDEPENDENTLY by
        the box's own width/height, so a non-square box turns a "circular"
        percentage radius elliptical - Lottie's own radial gradient has no
        such independent-axis control (only a single centre-to-edge
        distance), so the radial case here averages half-width and
        half-height into one effective radius rather than picking one axis
        arbitrarily - a documented approximation, not a spec-exact port.
        """
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        half_w, half_h = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        if lottie_type == 2:                       # radial
            r = max(1.0, 50.0 * scale) / 100.0 * (half_w + half_h)
            return (cx, cy), (cx + r, cy)
        dx = math.cos(rotation) * scale * half_w
        dy = -math.sin(rotation) * scale * half_h
        return (cx - dx, cy - dy), (cx + dx, cy + dy)

    def _finalize_outline_group(self, layer, acc: dict, frames, name: str) -> dict:
        """One shape's outline as a Lottie group - the pure-data half of
        what used to be _build_outline_group, split out once geometry
        collection became eager (see _accumulate_frame)."""
        self._assert_stable(layer, acc["name"], f"outline({acc['outline_kind']})",
                             acc["outline_per_frame"])
        color = acc["outline_color"]
        elements = self._sh_elements(acc["outline_per_frame"], frames)
        if acc["outline_kind"] == "taper":
            # Even-odd unconditionally, matching the SVG writer, which puts
            # fill-rule="evenodd" on a tapered outline whether it came back
            # as two counter-wound loops (a closed ring, needing the rule to
            # leave its hole) or one loop (an open "capsule").  This used to
            # pick non-zero for the single-loop case on the grounds that the
            # two rules agree there - true only while the loop does not
            # cross itself, which an offset curve round a tight bend can do.
            elements.append({"ty": "fl", "r": FILL_RULE_EVEN_ODD,
                              "c": {"a": 0, "k": [color.r, color.g, color.b]},
                              "o": {"a": 0, "k": color.a * 100}})
        else:
            elements.append({"ty": "st",
                              "c": {"a": 0, "k": [color.r, color.g, color.b]},
                              "o": {"a": 0, "k": color.a * 100},
                              "w": self._scalar_property(acc["outline_width_per_frame"], frames),
                              "lc": acc["outline_cap"],
                              "lj": 2})
        elements.append({"ty": "tr", **identity_transform()})
        return {"ty": "gr", "nm": f"{name}_line", "it": elements}


def validate_lottie(lottie: dict) -> None:
    """Validate `lottie` against the bundled `lottie/lottie.schema.json`,
    printing one PASS/FAIL-style line either way.

    Passing is weak evidence, not proof of a correct file: the schema marks
    very little as `required` (see docs/lottie-and-thorvg.md section 2.5),
    so a structurally-broken-but-technically-permitted document can still
    validate. It is still worth running, since a SCHEMA VIOLATION is
    unambiguous proof of a bug - this tool has produced zero of those across
    all 19 sample documents, checked directly while writing this function.

    Does nothing (prints a one-line note instead) when the optional
    `jsonschema` package is not installed - exactly like Pillow's absence in
    moho2svg.py, this must never become a required dependency.
    """
    if jsonschema is None:
        print("moho2lottie: --validate requested but the optional 'jsonschema' "
              "package is not installed - run `pip install jsonschema` to "
              "enable schema validation", file=sys.stderr)
        return
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    try:
        jsonschema.validate(lottie, schema)
    except jsonschema.ValidationError as exc:
        print(f"moho2lottie: SCHEMA VALIDATION FAILED at "
              f"{'.'.join(str(p) for p in exc.absolute_path) or '<root>'}: "
              f"{exc.message}", file=sys.stderr)
        return
    print("moho2lottie: schema validation passed "
          "(weak evidence only - see validate_lottie's own docstring)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Moho vector artwork (.mohoproj / .animeproj) to a "
                    "Lottie JSON animation.")
    parser.add_argument("project")
    parser.add_argument("--out", required=True)
    parser.add_argument("--frame", type=float,
                        help="export a single still frame instead of the document's "
                             "own [start_frame, end_frame] range")
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--smooth-joints", action="store_true",
                        help="approximate Moho's \"Smooth Joint for Bone Pair\" - see "
                             "moho2svg.py's Exporter._effective_subset. Closes the tear "
                             "between two limb halves that are each bound to a single bone, "
                             "but measured slightly WORSE against the reference frames "
                             "overall, so it is off by default")
    parser.add_argument("--bone-dynamics", action="store_true",
                        help="simulate Moho's per-bone spring/damping secondary motion. "
                             "UNVERIFIED - see moho2svg.py's Skeleton.dynamic_angles. "
                             "Off by default")
    parser.add_argument("--validate", action="store_true",
                        help="validate the output against lottie/lottie.schema.json "
                             "(needs the optional 'jsonschema' package)")
    args = parser.parse_args()

    document = load_document(args.project)
    if args.frame is not None:
        frames = [args.frame]
    else:
        # Every INTEGER frame in the document's own declared range, both
        # ends inclusive - matches Document.start_frame/.end_frame's own
        # Moho-side inclusivity.  Real (non-integer) frame numbers exist in
        # Lottie's data model, but Moho's own channels are keyframed at
        # integer frames, so sampling anything finer would not add fidelity.
        frames = list(range(document.start_frame, document.end_frame + 1))
    exporter = LottieExporter(document,
                               RenderSettings(smooth_bone_joints=args.smooth_joints,
                                               bone_dynamics=args.bone_dynamics))
    lottie = exporter.export(frames, include_hidden=args.include_hidden)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(lottie, f, separators=(",", ":"))

    size = os.path.getsize(args.out)
    print(f"wrote {args.out} ({size:,} bytes, {len(lottie['layers'])} layers)")
    for key, count in sorted(exporter.warnings.items()):
        explanation = WARNING_EXPLANATIONS.get(key, f"{key} not fully supported")
        print(f"moho2lottie: {count} {explanation} "
              f"- see docs/moho-to-lottie-design.md section 2.2", file=sys.stderr)

    if args.validate:
        validate_lottie(lottie)


if __name__ == "__main__":
    main()
