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
unclipped outline), ImageLayer, Smart Warp. Gradient fills are drawn as a
flat colour for now - a real Lottie "gf" gradient fill is Task 3 of the
Lottie exporter's own implementation plan, not yet done.
"""

import argparse
import json
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
    "gradient": "shape(s) with a gradient fill drawn as a flat colour "
                "instead (not yet implemented)",
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

        Moho draws its layer list back to front, which is the order
        walk_render_tree yields "mesh" events in.  Lottie draws the FIRST
        layer in its own list on top, so the finished list is reversed -
        the single easiest thing in this writer to get wrong without
        noticing: the artwork would still look right, just with the wrong
        parts in front.
        """
        collected = []
        for item in walk_render_tree(self.exporter, frames[0], include_hidden):
            if item.event != "mesh":
                continue
            shapes = self._build_shapes(item, frames)
            if shapes:
                collected.append(self._shape_layer(item.layer.name, shapes))
        collected.reverse()                  # Moho back-to-front -> Lottie front-to-back
        for index, layer in enumerate(collected, start=1):
            layer["ind"] = index
        return collected

    def _shape_layer(self, name: str, shapes: list) -> dict:
        """A Lottie shape layer with an identity transform.

        Identity is correct because the geometry is already baked into
        canvas pixels, which is also Lottie's own coordinate system: pixels,
        y down, origin at the top left - no conversion needed.
        """
        return {
            "ty": 4, "nm": name, "ks": identity_transform(),
            "ao": 0, "shapes": shapes,
            "ip": float(self.document.start_frame),
            "op": float(self.document.end_frame + 1),
            "st": 0.0,
        }

    def _point_widths(self, mesh, edges, frame: float) -> list:
        """The interpolated width at every point touched by `edges`, at
        `frame` - the same lookup ShapeGroupRenderer._point_widths performs,
        reproduced here since that method needs a ShapeGroupRenderer
        instance this writer never builds (it never renders SVG strings)."""
        point_indices = {mesh.curves[e.curve].points[e.segment].point_index
                          for e in edges}
        return [self.exporter.eval(mesh.points[i].width, frame) for i in point_indices]

    def _build_shapes(self, item, frames) -> list:
        """Every Moho shape of one layer, as Lottie shape-group elements.

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
        exp, frame = self.exporter, frames[0]
        style_names_used = set()
        out = []
        for shape in item.layer.mesh.shapes:
            if not shape.edges:
                continue
            if shape.combo_mode != 0:
                self.warnings["combo_mode"] += 1

            # Built unconditionally, even for an outline-only shape, purely
            # as the SVG writer's own "does this shape have any geometry at
            # all" gate - mirrors build_path_d()'s use in _render_shape.
            fill_beziers = build_path_bezier(item.geometries, shape.edges, item.to_px)
            if not fill_beziers:
                continue

            style = shape.style
            name = shape.name or ""
            if name in style_names_used:
                name = f"{name}_{len(style_names_used)}"
            style_names_used.add(name)

            outline_group = self._build_outline_group(item, shape, style, frame, name)
            if outline_group is not None:
                out.append(outline_group)

            if shape.has_fill:
                # A gradient fill (style.fill_style["type"] == "SS_Gradient2")
                # is drawn as this same flat fill_color for now - Task 5 adds
                # a real Lottie "gf" gradient fill.  Counted, not silent: a
                # gradient-filled shape drawn flat is a real, visible gap
                # until then.
                if isinstance(style.fill_style, dict) and \
                        style.fill_style.get("type") == "SS_Gradient2":
                    self.warnings["gradient"] += 1
                color = Color.from_raw(exp.eval(style.fill_color, frame))
                elements = [{"ty": "sh", "ks": {"a": 0, "k": b}} for b in fill_beziers]
                elements.append({"ty": "fl", "r": 1,
                                  "c": {"a": 0, "k": [color.r, color.g, color.b]},
                                  "o": {"a": 0, "k": color.a * 100}})
                elements.append({"ty": "tr", **identity_transform()})
                out.append({"ty": "gr", "nm": f"{name}_fill", "it": elements})
        return out

    def _build_outline_group(self, item, shape, style, frame: float, name: str):
        """One Moho shape's outline as a Lottie group, or None if the shape
        has no outline to draw.

        Mirrors _render_shape's own branching (brush -> tapered -> plain),
        simplified for this exporter's v1 scope: a brush-styled outline
        counts a warning and falls back to a plain uniform stroke (the same
        fallback Exporter._mask_source_shapes already uses when a mask
        source's own outline is brush-styled or tapered, for the same
        reason - the real geometry is unconfirmed) instead of the textured
        dabs the SVG writer can produce.
        """
        if not shape.has_outline:
            return None
        exp = self.exporter
        line_width = exp.eval(style.line_width, frame)
        color = Color.from_raw(exp.eval(style.line_color, frame))
        widths = self._point_widths(item.layer.mesh, shape.edges, frame)
        tapered = (max(widths) - min(widths) > 1e-6) if widths else False

        if style.brush_name:
            self.warnings["brush"] += 1

        if tapered and not style.brush_name:
            width_px = exp._stroke_width_px(line_width, 1.0)
            beziers = exp.tapered_outliner.build_bezier(
                item.geometries, shape.edges, item.to_px, width_px)
            if not beziers:
                return None
            elements = [{"ty": "sh", "ks": {"a": 0, "k": b}} for b in beziers]
            # A closed ring comes back as two counter-wound loops (see
            # TaperedStrokeOutliner.build_bezier) that need an evenodd fill
            # to leave the hole between them; an open "capsule" polygon is
            # a single loop and needs the ordinary nonzero rule.
            fill_rule = 2 if len(beziers) > 1 else 1
            elements.append({"ty": "fl", "r": fill_rule,
                              "c": {"a": 0, "k": [color.r, color.g, color.b]},
                              "o": {"a": 0, "k": color.a * 100}})
        else:
            point_width = widths[0] if (widths and not tapered) else 1.0
            width_px = exp._stroke_width_px(line_width, point_width)
            # visible_only=True + close=False, NEVER close=True, matching
            # build_path_d()'s own stroke_path call in _render_shape - see
            # build_path_bezier()'s docstring for why an open path renders a
            # genuinely different stroke join at the seam than a closed one.
            beziers = build_path_bezier(item.geometries, shape.edges, item.to_px,
                                         visible_only=True, close=False)
            if not beziers:
                return None
            elements = [{"ty": "sh", "ks": {"a": 0, "k": b}} for b in beziers]
            elements.append({"ty": "st",
                              "c": {"a": 0, "k": [color.r, color.g, color.b]},
                              "o": {"a": 0, "k": color.a * 100},
                              "w": {"a": 0, "k": width_px},
                              "lc": LINE_CAPS.get(style.line_cap_name(), 2),
                              "lj": 2})

        elements.append({"ty": "tr", **identity_transform()})
        return {"ty": "gr", "nm": f"{name}_line", "it": elements}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Moho vector artwork (.mohoproj / .animeproj) to a "
                    "Lottie JSON animation.")
    parser.add_argument("project")
    parser.add_argument("--out", required=True)
    parser.add_argument("--frame", type=float, default=0,
                        help="frame to export (single-frame still, for now)")
    parser.add_argument("--include-hidden", action="store_true")
    args = parser.parse_args()

    document = load_document(args.project)
    exporter = LottieExporter(document, RenderSettings())
    lottie = exporter.export([args.frame], include_hidden=args.include_hidden)

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
