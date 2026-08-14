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
instead), boolean shape combination via combo_mode (drawn as a plain,
unclipped outline), ImageLayer, Smart Warp.
"""

import argparse
import json
import math
import os
import sys
from collections import Counter

from moho2svg import (Color, Exporter, RenderSettings, build_path_bezier,
                       load_document, walk_render_tree)

LOTTIE_VERSION = "5.7.0"

# Printed per warning key at the end of an export - see the module
# docstring's "deliberately out of scope" paragraph for the reasoning behind
# each one.
WARNING_EXPLANATIONS = {
    "combo_mode": "shape(s) with boolean combination (combo_mode != 0) drawn "
                  "as a plain, unclipped outline",
    "brush": "shape(s) with a textured brush outline drawn as a plain "
             "uniform stroke instead",
    "gradient_too_few_stops": "gradient fill(s) with fewer than 2 stops drawn "
                              "as a flat colour instead (matches "
                              "Exporter._build_gradient's own SVG fallback)",
    "mask_stroke_exclusion": "masked layer(s) whose mask source has its own "
                             "outline - the SVG writer carves that source's "
                             "stroke band back out of the mask so it stays "
                             "visible on top; this writer draws a plain "
                             "union mask instead, without that carve-out",
}

# Lottie's line-cap constant (shapes/base-stroke.json's "lc"), keyed by the
# SAME string ResolvedStyle.line_cap_name() already returns for the SVG
# writer's own stroke-linecap - deriving it from that string, not from the
# raw line_caps int, means the two exporters cannot drift apart.
LINE_CAPS = {"butt": 1, "round": 2, "square": 3}


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

    def export(self, frames, include_hidden: bool = False) -> dict:
        """Return the Lottie document as a plain dict.

        `frames` is every frame to sample, in ascending order.  A single
        frame produces static paths; several (Task 4) produce path
        keyframes.
        """
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
            "assets": [],
            "layers": layers,
        }

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
        combo_mode never varies by frame (only their geometry does), so
        which layers/shapes exist at all is decided from frame[0]'s walk
        alone; a layer present there but missing from a later frame's walk
        would mean its visibility itself is animated - not something any
        document in this repository's sample corpus does, and not yet
        handled here (a SwitchLayer's active child changing across the
        range is Task 7's job specifically). Raises rather than guessing if
        that assumption ever breaks.

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
        order: list = []                      # Layer objects, frame[0]'s draw order
        accumulators: dict = {}               # id(layer) -> list of per-shape accumulators
        mask_data: dict = {}                  # id(layer) -> {"has_mask": bool|None, "per_frame": [...]}
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
                    order.append(item.layer)
                    accumulators[lid] = []
                    mask_data[lid] = {"has_mask": None, "per_frame": []}
                self._accumulate_frame(item, frame, accumulators[lid], first_time)

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
            shapes = self._finalize_shapes(layer, accumulators[id(layer)], frames)
            if not shapes:
                continue
            info = mask_data[id(layer)]
            mask_properties = (self._finalize_mask(layer, info["per_frame"], frames)
                                if info["has_mask"] else None)
            collected.append(self._shape_layer(layer.name, shapes, mask_properties))
        collected.reverse()                  # Moho back-to-front -> Lottie front-to-back
        for index, layer in enumerate(collected, start=1):
            layer["ind"] = index
        return collected

    def _shape_layer(self, name: str, shapes: list, mask_properties: list = None) -> dict:
        """A Lottie shape layer with an identity transform.

        Identity is correct because the geometry is already baked into
        canvas pixels, which is also Lottie's own coordinate system: pixels,
        y down, origin at the top left - no conversion needed.
        """
        layer = {
            "ty": 4, "nm": name, "ks": identity_transform(),
            "ao": 0, "shapes": shapes,
            "ip": float(self.document.start_frame),
            "op": float(self.document.end_frame + 1),
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
        Exporter._mask_source_shapes's own docstring) is NOT reproduced
        here. Lottie's mask model has only filled shapes, no "stroke this
        path as a mask" primitive, so replicating it would mean building a
        uniform-width stroke-band polygon per masked source - a project of
        its own for a narrow effect, measured at 16 of 180 mask source
        shapes (9%) across this repository's sample documents. Counted
        (mask_stroke_exclusion), not silently dropped.
        """
        for beziers, exclude_width in per_frame_sources[0]:
            if exclude_width > 0:
                self.warnings["mask_stroke_exclusion"] += 1

        # per_frame_sources[f] is a list of (beziers, exclude_width) - one
        # per mask-source SHAPE.  Flatten to one list of subpath dicts per
        # frame, dropping exclude_width (already counted above).
        per_frame_flat = [[subpath for beziers, _exclude in sources for subpath in beziers]
                           for sources in per_frame_sources]
        self._assert_stable(layer, "<mask>", "mask", per_frame_flat)

        return [{"inv": False, "mode": "a", "pt": self._path_property(list(per_subpath), frames),
                 "o": {"a": 0, "k": 100}, "x": {"a": 0, "k": 0}}
                for per_subpath in zip(*per_frame_flat)]

    def _point_widths(self, mesh, edges, frame: float) -> list:
        """The interpolated width at every point touched by `edges`, at
        `frame` - the same lookup ShapeGroupRenderer._point_widths performs,
        reproduced here since that method needs a ShapeGroupRenderer
        instance this writer never builds (it never renders SVG strings)."""
        point_indices = {mesh.curves[e.curve].points[e.segment].point_index
                          for e in edges}
        return [self.exporter.eval(mesh.points[i].width, frame) for i in point_indices]

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
        return {"a": 1,
                "k": [{"t": float(f), "s": [b]} for f, b in zip(frames, per_frame)]}

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
        return {"a": 1,
                "k": [{"t": float(f), "s": [v]} for f, v in zip(frames, per_frame)]}

    def _point_property(self, per_frame_points: list, frames) -> dict:
        """A Lottie 2D point property (e.g. a gradient's start/end point):
        static when it never changes across frames, keyframed otherwise -
        the 2D-point counterpart of _scalar_property.  `per_frame_points` is
        one (x, y) tuple per frame."""
        if all(p == per_frame_points[0] for p in per_frame_points[1:]):
            return {"a": 0, "k": list(per_frame_points[0])}
        return {"a": 1,
                "k": [{"t": float(f), "s": [list(p)]}
                      for f, p in zip(frames, per_frame_points)]}

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

    def _accumulate_frame(self, item, frame: float, accs: list, first_time: bool) -> None:
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
        if shape.combo_mode != 0:
            self.warnings["combo_mode"] += 1
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

    def _finalize_shapes(self, layer, accs: list, frames) -> list:
        """Turn every shape's already-collected per-frame data into Lottie
        shape-group elements.  Pure data transformation - no exp.eval()/
        to_px() calls here, which is exactly why _accumulate_frame had to
        do all of that eagerly (see its own docstring).

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
        """
        style_names_used: set = set()
        out = []
        for acc in accs:
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

            if acc["outline_kind"] is not None and acc["outline_per_frame"][0]:
                out.append(self._finalize_outline_group(layer, acc, frames, name))

            if acc["has_fill"]:
                elements = self._sh_elements(acc["fill_per_frame"], frames)
                if acc["gradient"] is not None:
                    elements.append(self._gradient_fill(acc, frames))
                else:
                    color = acc["fill_color"]
                    elements.append({"ty": "fl", "r": 1,
                                      "c": {"a": 0, "k": [color.r, color.g, color.b]},
                                      "o": {"a": 0, "k": color.a * 100}})
                elements.append({"ty": "tr", **identity_transform()})
                out.append({"ty": "gr", "nm": f"{name}_fill", "it": elements})
        return out

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
        return {"ty": "gf", "r": 1, "t": grad["lottie_type"],
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
            # A closed ring comes back as two counter-wound loops (see
            # TaperedStrokeOutliner.build_bezier) that need an evenodd fill
            # to leave the hole between them; an open "capsule" polygon is
            # a single loop and needs the ordinary nonzero rule.  Subpath
            # count is asserted stable above, so checking frame 0 suffices.
            fill_rule = 2 if len(acc["outline_per_frame"][0]) > 1 else 1
            elements.append({"ty": "fl", "r": fill_rule,
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
    exporter = LottieExporter(document, RenderSettings())
    lottie = exporter.export(frames, include_hidden=args.include_hidden)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(lottie, f, separators=(",", ":"))

    size = os.path.getsize(args.out)
    print(f"wrote {args.out} ({size:,} bytes, {len(lottie['layers'])} layers)")
    for key, count in sorted(exporter.warnings.items()):
        explanation = WARNING_EXPLANATIONS.get(key, f"{key} not fully supported")
        print(f"moho2lottie: {count} {explanation} "
              f"- see docs/moho-to-lottie-design.md section 2.2", file=sys.stderr)


if __name__ == "__main__":
    main()
