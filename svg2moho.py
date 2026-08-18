#!/usr/bin/env python3
r"""SVG to Moho: reconstruct a .mohoproj from a static SVG file.

The SVG counterpart of lottie2moho.py, under the same flat-bake contract
(see docs/svg-to-moho-design.md): the output is a FLAT, UNRIGGED, STATIC
Moho document - one root GroupLayer, one MeshLayer per SVG geometry
element, every transform baked into point coordinates, every layer
transform identity.  The contract, the feature subset, the mappings and
the verification gates are all in docs/svg-to-moho-design.md; the
task-by-task plan is docs/svg-to-moho-plan.md.

Stdlib only (xml.etree.ElementTree - no third-party XML library).
SELF-CONTAINED BY DESIGN: the Moho-side helpers are vendored copies of
the already-validated lottie2moho.py implementations (each marked
"copied from ..."), so this file's behaviour cannot drift when that
writer changes.

Usage:
    python3 svg2moho.py input.svg [--out OUT.mohoproj] [--validate]
"""

# ============================================================================
# ==== SVG READING  (the input side: the XML tree)                       ====
# ============================================================================

import argparse
import json
import math
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "{http://www.w3.org/1999/xlink}"

# ============================================================================
# ==== MOHO WRITING  (the output side: raw .mohoproj JSON dicts)         ====
# ============================================================================

MOHO_FORMAT_VERSION = 1045
MOHO_MIME_TYPE = "application/x-vnd.lm_mohodoc"

_DEFAULT_INTERP = {"im": 0, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0,
                   "s": False, "t": 0}


def _static_channel(kind: str, value) -> dict:
    """One Moho channel holding a single constant `value` (copied from
    lottie2moho.py, which measured the shape against Moho's own loader)."""
    return {"type": kind, "ref": False, "mute": False, "when": [0],
            "val": [value], "interp": [_DEFAULT_INTERP]}


# Copied from lottie2moho.py (which copied it from moho2svg.py's
# RenderSettings): the empirically-fit chord-length-weighted tangent blend
# exponent.
TANGENT_BIAS = 0.19

# A static, identity transform for a layer whose transforms are never
# animated.  Every field is a full CHANNEL (copied from lottie2moho.py:
# the bare-scalar shorthand is rejected by Moho's own loader - measured
# 2026-08, "Type mismatch: got OBJECT expected DOUBLE").
_IDENTITY_TRANSFORMS = {
    "translation": _static_channel("Vec3", {"x": 0.0, "y": 0.0, "z": 0.0}),
    "scale": _static_channel("Vec3", {"x": 1.0, "y": 1.0, "z": 1.0}),
    "rotation_x": _static_channel("Val", 0.0),
    "rotation_y": _static_channel("Val", 0.0),
    "rotation_z": _static_channel("Val", 0.0),
    "flip_h": _static_channel("Bool", False),
    "flip_v": _static_channel("Bool", False),
    "shear": _static_channel("Vec3", {"x": 0.0, "y": 0.0, "z": 0.0}),
    "following": _static_channel("Val", 0.0),
    "physics_nudge": _static_channel("Vec2", {"x": 0.0, "y": 0.0}),
}


class V2:
    """A minimal 2D vector (copied from lottie2moho.py's own copy -
    self-containment)."""

    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

    def sub(self, other: "V2") -> "V2":
        return V2(self.x - other.x, self.y - other.y)

    def add(self, other: "V2") -> "V2":
        return V2(self.x + other.x, self.y + other.y)

    def scaled(self, k: float) -> "V2":
        return V2(self.x * k, self.y * k)

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "V2":
        n = self.length()
        return V2(self.x / n, self.y / n) if n > 1e-12 else V2(0.0, 0.0)

    def angle_to(self, other: "V2") -> float:
        """The signed angle (radians) to rotate `self` onto `other`
        (copied from lottie2moho.py / moho2svg.py Vec2.angle_to)."""
        return math.atan2(self.x * other.y - self.y * other.x,
                          self.x * other.x + self.y * other.y)


def _new_layer_uuid() -> str:
    """A fresh UUID string in Moho's own uppercase form."""
    return str(uuid.uuid4()).upper()


def forward_blend_direction(u: V2, v: V2) -> V2:
    """The forward handle model's blended tangent direction at a point
    whose neighbours sit at `u` (toward prev) and `v` (toward next).

    This is moho2svg.py's BezierReconstructor.handle formula VERBATIM
    (chord-length-weighted blend, u scaled by dv^bias/du and v by
    du^bias/dv).  NOTE: lottie2moho.py carries an EARLIER, DIFFERENT
    variant of this formula under the same name (a normalized-unit blend
    with a |du-dv| bias); the two disagree on asymmetric chords, which
    makes curves fitted with one and reconstructed with the other bulge
    - measured 2026-08 on the donut gate: the ring's re-exported handles
    came out rotated ~90 deg off until this file switched to the real
    formula."""
    du, dv = u.length(), v.length()
    if du < 1e-12 or dv < 1e-12:
        return u.add(v).normalized()
    return u.scaled(dv ** TANGENT_BIAS / du) \
        .add(v.scaled(du ** TANGENT_BIAS / dv)).normalized()


def fit_curve_point(p: V2, prev: V2, nxt: V2,
                    h_in: V2, h_out: V2) -> dict:
    """Invert the forward handle model for one point, exactly (copied
    verbatim from lottie2moho.py - the inverse is closed-form, not a
    numeric fit).

    smoothness 0 (Moho's sharp corner) is reproduced exactly when both
    handles collapse onto the point (zero length).
    """
    u, v = p.sub(prev), nxt.sub(p)
    d_in = h_in.sub(p)       # points toward prev
    d_out = h_out.sub(p)     # points toward nxt
    len_in, len_out = d_in.length(), d_out.length()

    ratio_in = len_in / u.length() if u.length() > 1e-12 else 0.0
    ratio_out = len_out / v.length() if v.length() > 1e-12 else 0.0

    if len_in < 1e-9 and len_out < 1e-9:
        return {"smoothness": 0.0, "weight_in": 0.0, "weight_out": 0.0,
                "offset_in": 0.0, "offset_out": 0.0}

    model_dir = forward_blend_direction(u, v)
    offset_out = model_dir.angle_to(d_out.normalized()) if len_out > 1e-9 else 0.0
    offset_in = (model_dir.scaled(-1.0)).angle_to(d_in.normalized()) if len_in > 1e-9 else 0.0

    smoothness = min(1.0, max(ratio_in, ratio_out))
    weight_in = max(0.0, min(1.0, ratio_in / smoothness if smoothness > 0 else 0.0))
    weight_out = max(0.0, min(1.0, ratio_out / smoothness if smoothness > 0 else 0.0))
    return {"smoothness": round(smoothness, 6), "weight_in": round(weight_in, 6),
            "weight_out": round(weight_out, 6), "offset_in": round(offset_in, 6),
            "offset_out": round(offset_out, 6)}


def compose_matrix(m1: tuple, m2: tuple) -> tuple:
    """m1 o m2 - apply m2 first, then m1 (column vectors).  A 2x3 affine
    (a, b, c, d, e, f) as SVG does: x' = a x + c y + e.
    (copied from lottie2moho.py)"""
    a, b, c, d, e, f = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a * a2 + c * b2, b * a2 + d * b2,
            a * c2 + c * d2, b * c2 + d * d2,
            a * e2 + c * f2 + e, b * e2 + d * f2 + f)


_IDENTITY_MATRIX = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def pixel_to_moho(p: V2, canvas_w: float, canvas_h: float) -> V2:
    """Canvas pixels -> Moho local units (copied from lottie2moho.py):
    the inverse of the default-camera mapping
    pixel_x = moho_x * (h/2) + w/2,  pixel_y = h/2 - moho_y * (h/2)."""
    h2 = canvas_h / 2.0
    return V2((p.x - canvas_w / 2.0) / h2, -(p.y - canvas_h / 2.0) / h2)


def build_root_group() -> dict:
    """The one root GroupLayer every document's layers live under
    (copied from lottie2moho.py)."""
    return {
        "type": "GroupLayer",
        "name": "Root",
        "uuid": _new_layer_uuid(),
        "visible": True,
        "origin": {"x": 0.0, "y": 0.0},
        "transforms": dict(_IDENTITY_TRANSFORMS),
        "layers": [],
    }


def _document_scaffold() -> dict:
    """The document-level keys a real 1045 .mohoproj carries besides the
    content (copied from lottie2moho.py - measured: Moho's loader rejects
    a document without them, error 108)."""
    return {
        "doc_uuid": _new_layer_uuid(),
        "created_date": "Thu Jan  1 00:00:00 1970",
        "modified_date": "Thu Jan  1 00:00:00 1970",
        "layercomps": [],
        "onions_enabled": False,
        "onions_sellayer": True,
        "onions_filled": False,
        "onions_colored": True,
        "onions_relative": False,
        "onions_behind": False,
        "onions_frame0": -100000,
        "onions_frame1": -100000,
        "onions_frame2": -100000,
        "onions_frame3": -100000,
        "onions_frame4": -100000,
        "onions_frame5": -100000,
        "onions_frame6": -100000,
        "onions_frame7": -100000,
        "action_refs": [],
        "metadata": {"what": 0, "layerwnd_searchcontext": 0, "save_time": 0},
        "documentviewstate": {
            "DocState_viewportSetting": 1,
            "DocState_gridOn": False,
            "DocState_gridStyle": 0,
            "DocState_smartMeshOn": False,
            "DocState_shyBonesOn": False,
            "DocState_followPathOn": False,
            "DocState_drawPathOn": False,
        },
    }


def _moho_color(rgb: list, opacity: float) -> dict:
    """0..1 floats -> a Moho Color CHANNEL holding 0..1 floats, opacity
    folded into alpha (copied from lottie2moho.py)."""
    r, g, b = (rgb + [1.0])[:3]
    a = (rgb[3] if len(rgb) > 3 else 1.0) * opacity
    return _static_channel("Color", {
        "r": round(max(0.0, min(1.0, r)), 6),
        "g": round(max(0.0, min(1.0, g)), 6),
        "b": round(max(0.0, min(1.0, b)), 6),
        "a": round(max(0.0, min(1.0, a)), 6),
    })


def _style_dict() -> dict:
    """A full shape Style object with default (empty) values (copied from
    lottie2moho.py - Moho's loader rejects abbreviated styles)."""
    return {
        "type": "Style",
        "name": "",
        "uuid": _new_layer_uuid(),
        "define_fill_color": False,
        "fill_color": _static_channel("Color", {"r": 0.0, "g": 0.0,
                                                 "b": 0.0, "a": 1.0}),
        "define_line_width": False,
        "line_width": 0.0,
        "define_line_col": False,
        "line_color": _static_channel("Color", {"r": 0.0, "g": 0.0,
                                                 "b": 0.0, "a": 1.0}),
        "line_caps": 1,
        "brush_name": "",
        "brush_align": True,
        "brush_jitter": 0.0,
        "brush_spacing": 0.43,
        "brush_angle_drift": 0.0,
        "brush_randomize": False,
        "brush_merged_alpha": False,
        "brush_tint": True,
        "brush_rand_order": False,
        "brush_size_amp": 0.14,
        "brush_size_scale": 0.03,
        "brush_random_interval": 1,
        "brush_hue_drift": 0.0,
        "brush_sat_drift": 0.0,
        "brush_val_drift": 0.0,
    }


# ============================================================================
# ==== SVG READING  (parsers for paths, colours, styles, transforms)     ====
# ============================================================================

_NUMBER_RE = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")
_TOKEN_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")

_CAP_NAMES = {"butt": 0, "round": 1, "square": 2}


def parse_color(value: str, warnings: "WarningCounter"):
    """An SVG colour -> [r, g, b, a] floats 0..1, or None for 'none' and
    other non-colours.  Named colours and unsupported forms fall back to
    black with a counted warning."""
    if value is None:
        return None
    value = value.strip()
    if not value or value == "none":
        return None
    if value.startswith("#"):
        h = value[1:]
        if len(h) == 3:
            h = "".join(c + c for c in h)
        if len(h) == 6:
            try:
                return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)] + [1.0]
            except ValueError:
                pass
        warnings.count("unknown_color")
        return [0.0, 0.0, 0.0, 1.0]
    m = re.match(r"rgba?\(\s*([\d.]+%?)\s*,\s*([\d.]+%?)\s*,\s*([\d.]+%?)"
                 r"(?:\s*,\s*([\d.]+%?))?\s*\)$", value)
    if m:
        def comp(s):
            if s.endswith("%"):
                return max(0.0, min(1.0, float(s[:-1]) / 100.0))
            f = float(s)
            return f / 255.0 if f > 1.0 else f
        return [comp(m.group(1)), comp(m.group(2)), comp(m.group(3)),
                comp(m.group(4)) if m.group(4) else 1.0]
    if value.startswith("url("):
        return value              # gradient reference, resolved by the caller
    warnings.count("unknown_color")
    return [0.0, 0.0, 0.0, 1.0]


def parse_style(style_str: str) -> dict:
    """An inline style="k:v; k:v" string -> {k: v}.  Invalid pairs are
    skipped (the SVG spec's own error handling)."""
    out = {}
    if not style_str:
        return out
    for part in style_str.split(";"):
        if ":" not in part:
            continue
        k, _, v = part.partition(":")
        out[k.strip()] = v.strip()
    return out


def _parse_number_list(s: str) -> list:
    return [float(m) for m in _NUMBER_RE.findall(s or "")]


def parse_transform(value: str, warnings: "WarningCounter") -> tuple:
    """An SVG transform attribute -> one 2x3 affine matrix.  Multiple
    functions compose left-to-right (the SVG spec's own order)."""
    matrix = _IDENTITY_MATRIX
    if not value:
        return matrix
    for func, arg_str in re.findall(r"(\w+)\s*\(([^)]*)\)", value):
        args = _parse_number_list(arg_str)
        name = func.lower()
        if name == "matrix" and len(args) >= 6:
            m = tuple(args[:6])
        elif name == "translate":
            tx, ty = args[0], args[1] if len(args) > 1 else 0.0
            m = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif name == "scale":
            sx, sy = args[0], args[1] if len(args) > 1 else args[0]
            m = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "rotate":
            # SVG rotate(a) is clockwise on screen (y-down), the same
            # convention as the pixel-space matrices baked here.
            a = math.radians(args[0])
            co, si = math.cos(a), math.sin(a)
            m = (co, si, -si, co, 0.0, 0.0)
            if len(args) > 2:                      # rotate(a cx cy)
                cx, cy = args[1], args[2]
                m = compose_matrix((1.0, 0.0, 0.0, 1.0, cx, cy),
                                   compose_matrix(m,
                                                  (1.0, 0.0, 0.0, 1.0, -cx, -cy)))
        elif name == "skewx" and args:
            m = (1.0, 0.0, math.tan(math.radians(args[0])), 1.0, 0.0, 0.0)
        elif name == "skewy" and args:
            m = (1.0, math.tan(math.radians(args[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            warnings.count("unknown_transform")
            continue
        matrix = compose_matrix(matrix, m)
    return matrix


def _apply_matrix(m: tuple, x: float, y: float) -> tuple:
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def arc_to_cubics(x1: float, y1: float, rx: float, ry: float,
                  phi_deg: float, large_arc: bool, sweep: bool,
                  x2: float, y2: float) -> list:
    """One SVG elliptical arc -> a list of cubic segments
    [(cx1, cy1, cx2, cy2, x, y), ...] in user space.

    The endpoint-to-center parameterization and the radius-correction are
    the SVG 1.1 spec's own F.6.5/F.6.6, then each <= 90-degree piece is
    a cubic with the standard kappa' = 4/3 tan(theta/4).
    """
    if (x1, y1) == (x2, y2) or rx <= 0 or ry <= 0:
        return []                       # degenerate: no arc (a straight move)
    phi = math.radians(phi_deg % 360.0)
    co, si = math.cos(phi), math.sin(phi)
    # step 1: midpoint -> unit-circle space
    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = co * dx2 + si * dy2
    y1p = -si * dx2 + co * dy2
    # step 2: radius correction (Lambda) per F.6.6
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1.0:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    # step 3: center in the primed frame
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = 0.0 if den <= 0 else math.sqrt(max(0.0, num / den))
    if large_arc == sweep:
        coef = -coef
    cxp = coef * (rx * y1p / ry)
    cyp = coef * (-ry * x1p / rx)
    # step 4: center in user space
    cx = co * cxp - si * cyp + (x1 + x2) / 2.0
    cy = si * cxp + co * cyp + (y1 + y2) / 2.0
    # start/delta angles
    def angle(ux, uy):
        a = math.atan2(uy, ux)
        return a % (2.0 * math.pi)
    theta1 = angle((x1p - cxp) / rx, (y1p - cyp) / ry)
    theta2 = angle((-x1p - cxp) / rx, (-y1p - cyp) / ry)
    dtheta = theta2 - theta1
    # the SVG spec's own sweep handling (F.6.5): sweep=1 draws in the
    # positive-angle direction, sweep=0 in the negative one
    if not sweep and dtheta > 0:
        dtheta -= 2.0 * math.pi
    if sweep and dtheta < 0:
        dtheta += 2.0 * math.pi
    # split into <= 90 deg pieces, each a cubic
    segs = []
    # 45-degree pieces (not 90): the handle model's chord-weighted blend
    # is exact only for symmetric chords, and the reconstruction error on
    # a 90-degree arc bulges the circle ~17% off its true area (measured
    # 2026-08 on the donut gate) - 45 degrees keeps the ring within ~1px
    # on a 160px circle.
    n = max(1, int(math.ceil(abs(dtheta) / (math.pi / 4.0))))
    delta = dtheta / n
    t = theta1
    px, py = x1, y1
    for _ in range(n):
        t2 = t + delta
        k = 4.0 / 3.0 * math.tan(delta / 4.0)
        # unit-space endpoints/tangents for this piece
        u0 = (math.cos(t), math.sin(t))
        u1 = (math.cos(t2), math.sin(t2))
        d0 = (-math.sin(t), math.cos(t))
        d1 = (-math.sin(t2), math.cos(t2))
        c1u = (u0[0] + k * d0[0], u0[1] + k * d0[1])
        c2u = (u1[0] - k * d1[0], u1[1] - k * d1[1])
        # map through the ellipse frame T(c) R(phi) S(rx, ry)
        def to_user(u):
            ex = rx * u[0]
            ey = ry * u[1]
            return (cx + co * ex - si * ey, cy + si * ex + co * ey)
        p2 = to_user(u1)
        c1 = to_user(c1u)
        c2 = to_user(c2u)
        segs.append((c1[0], c1[1], c2[0], c2[1], p2[0], p2[1]))
        t = t2
    return segs


class _PathParser:
    """One path `d` string -> a list of subpaths, each
    [points, in_handles, out_handles, closed] in USER space, where the
    handles are ABSOLUTE control points (in_handles[k] points toward the
    previous vertex, out_handles[k] toward the next)."""

    def __init__(self, d: str, warnings: "WarningCounter"):
        self.warnings = warnings
        self.tokens = _TOKEN_RE.findall(d or "")

    def _numbers(self, n: int) -> list:
        out = []
        for _ in range(n):
            if self.tokens and _NUMBER_RE.fullmatch(self.tokens[0]):
                out.append(float(self.tokens.pop(0)))
            else:
                self.warnings.count("malformed_path")
                return []
        return out

    def parse(self) -> list:
        subpaths = []
        cur = None          # [points, i, o, closed]
        x = y = 0.0
        start = (0.0, 0.0)
        prev_cmd = ""
        prev_control = None  # last C2 (for S) or Q (for T)
        while self.tokens:
            tok = self.tokens.pop(0)
            if _NUMBER_RE.fullmatch(tok):
                # implicit repetition of the previous command (Lineto for
                # M's later pairs)
                self.tokens.insert(0, tok)
                tok = prev_cmd if prev_cmd not in ("m", "M", "") else "l"
                if prev_cmd in ("m", "M"):
                    tok = "l" if prev_cmd == "m" else "L"
            cmd = tok
            rel = cmd.islower()
            upper = cmd.upper()

            def pt():
                vals = self._numbers(2)
                if len(vals) < 2:
                    return None
                px, py = vals
                if rel:
                    px, py = x + px, y + py
                return px, py

            if upper == "M":
                vals = self._numbers(2)
                if len(vals) < 2:
                    break
                nx, ny = (x + vals[0], y + vals[1]) if rel else (vals[0], vals[1])
                cur = [[(nx, ny)], [(nx, ny)], [(nx, ny)], False]
                subpaths.append(cur)
                x, y, start = nx, ny, (nx, ny)
                prev_control = None
                continue
            if upper == "Z":
                if cur:
                    cur[3] = True
                    x, y = start
                prev_control = None
                continue
            if cur is None:
                self.warnings.count("malformed_path")
                continue

            if upper == "L":
                p = pt()
                if p is None:
                    break
                cur[0].append(p)
                cur[1].append(p)          # line: handles collapse on the vertex
                cur[2].append(p)
                x, y = p
                prev_control = None
            elif upper == "H":
                vals = self._numbers(1)
                if not vals:
                    break
                nx = x + vals[0] if rel else vals[0]
                p = (nx, y)
                cur[0].append(p)
                cur[1].append(p)
                cur[2].append(p)
                x = nx
                prev_control = None
            elif upper == "V":
                vals = self._numbers(1)
                if not vals:
                    break
                ny = y + vals[0] if rel else vals[0]
                p = (x, ny)
                cur[0].append(p)
                cur[1].append(p)
                cur[2].append(p)
                y = ny
                prev_control = None
            elif upper == "C":
                vals = self._numbers(6)
                if len(vals) < 6:
                    break
                c1x, c1y, c2x, c2y, ex, ey = vals
                if rel:
                    c1x, c1y = x + c1x, y + c1y
                    c2x, c2y = x + c2x, y + c2y
                    ex, ey = x + ex, y + ey
                p = (ex, ey)
                cur[0].append(p)
                cur[1].append((c2x, c2y))
                cur[2].append((c1x, c1y))
                # the PREVIOUS vertex's out-handle is this segment's c1
                cur[2][-2] = (c1x, c1y)
                x, y = p
                prev_control = (c2x, c2y)
            elif upper == "S":
                vals = self._numbers(4)
                if len(vals) < 4:
                    break
                c2x, c2y, ex, ey = vals
                if rel:
                    c2x, c2y = x + c2x, y + c2y
                    ex, ey = x + ex, y + ey
                if prev_cmd.upper() in ("C", "S"):
                    cx1, cy1 = x - (prev_control[0] - x), y - (prev_control[1] - y)
                else:
                    cx1, cy1 = x, y
                p = (ex, ey)
                cur[0].append(p)
                cur[1].append((c2x, c2y))
                cur[2].append((cx1, cy1))
                cur[2][-2] = (cx1, cy1)
                x, y = p
                prev_control = (c2x, c2y)
            elif upper == "Q":
                vals = self._numbers(4)
                if len(vals) < 4:
                    break
                qx, qy, ex, ey = vals
                if rel:
                    qx, qy = x + qx, y + qy
                    ex, ey = x + ex, y + ey
                c1x, c1y = x + 2.0 / 3.0 * (qx - x), y + 2.0 / 3.0 * (qy - y)
                c2x, c2y = ex + 2.0 / 3.0 * (qx - ex), ey + 2.0 / 3.0 * (qy - ey)
                p = (ex, ey)
                cur[0].append(p)
                cur[1].append((c2x, c2y))
                cur[2].append((c1x, c1y))
                cur[2][-2] = (c1x, c1y)
                x, y = p
                prev_control = (qx, qy)
            elif upper == "T":
                vals = self._numbers(2)
                if len(vals) < 2:
                    break
                ex, ey = vals
                if rel:
                    ex, ey = x + ex, y + ey
                if prev_cmd.upper() in ("Q", "T"):
                    qx, qy = x - (prev_control[0] - x), y - (prev_control[1] - y)
                else:
                    qx, qy = x, y
                c1x, c1y = x + 2.0 / 3.0 * (qx - x), y + 2.0 / 3.0 * (qy - y)
                c2x, c2y = ex + 2.0 / 3.0 * (qx - ex), ey + 2.0 / 3.0 * (qy - ey)
                p = (ex, ey)
                cur[0].append(p)
                cur[1].append((c2x, c2y))
                cur[2].append((c1x, c1y))
                cur[2][-2] = (c1x, c1y)
                x, y = p
                prev_control = (qx, qy)
            elif upper == "A":
                vals = self._numbers(7)
                if len(vals) < 7:
                    break
                rx, ry, phi, laf, sf, ex, ey = vals
                if rel:
                    ex, ey = x + ex, y + ey
                segs = arc_to_cubics(x, y, abs(rx), abs(ry), phi,
                                     bool(laf), bool(sf), ex, ey)
                if not segs:
                    p = (ex, ey)
                    cur[0].append(p)
                    cur[1].append(p)
                    cur[2].append(p)
                for c1x, c1y, c2x, c2y, sx, sy in segs:
                    p = (sx, sy)
                    cur[0].append(p)
                    cur[1].append((c2x, c2y))
                    cur[2].append((c1x, c1y))
                    cur[2][-2] = (c1x, c1y)
                x, y = ex, ey
                prev_control = None
            else:
                self.warnings.count("unknown_command")
                break
            prev_cmd = cmd

        # A subpath with a single point is degenerate; the caller drops it.
        return subpaths


def primitive_to_path(tag: str, attrs: dict, warnings: "WarningCounter") -> str:
    """A shape primitive -> an equivalent path `d` string (design 4.2 -
    no separate geometry code)."""
    def num(name, default):
        try:
            return float(attrs.get(name, default))
        except (TypeError, ValueError):
            warnings.count("malformed_primitive")
            return float(default)
    tag = tag.replace("{http://www.w3.org/2000/svg}", "")
    if tag == "rect":
        x, y = num("x", 0.0), num("y", 0.0)
        w, h = num("width", 0.0), num("height", 0.0)
        rx, ry = num("rx", 0.0), num("ry", 0.0)
        if "rx" in attrs and "ry" not in attrs:
            ry = rx
        if "ry" in attrs and "rx" not in attrs:
            rx = ry
        rx, ry = min(rx, w / 2.0), min(ry, h / 2.0)
        if rx <= 0 or ry <= 0:
            return "M %g %g H %g V %g H %g Z" % (x, y, x + w, y + h, x)
        # rounded corners: 4 arcs, each kappa-scaled to the corner radius
        k = 0.5522847498307936
        return ("M %g %g H %g "
                "C %g %g %g %g %g %g "
                "V %g C %g %g %g %g %g %g "
                "H %g C %g %g %g %g %g %g "
                "V %g C %g %g %g %g %g %g Z") % (
            x + rx, y, x + w - rx,
            x + w - rx + k * rx, y, x + w, y + k * ry, x + w, y + ry,
            y + h - ry, x + w, y + h - ry + k * ry, x + w - k * rx, y + h, x + w - rx, y + h,
            x + rx, x + rx + k * rx, y + h, x, y + h - k * ry, x, y + h - ry,
            y + ry, x, y + ry + k * ry, x + k * rx, y, x + rx, y)
    if tag in ("circle", "ellipse"):
        cx = num("cx", 0.0)
        cy = num("cy", 0.0)
        rx = num("r", 0.0) if tag == "circle" else num("rx", 0.0)
        ry = num("r", 0.0) if tag == "circle" else num("ry", 0.0)
        # 8 cubic pieces per ellipse (the same 45-degree reasoning as
        # arc_to_cubics)
        segs = 8
        d = ""
        for i in range(segs):
            t1 = 2.0 * math.pi * i / segs
            t2 = 2.0 * math.pi * (i + 1) / segs
            k = 4.0 / 3.0 * math.tan((t2 - t1) / 4.0)
            p1 = (cx + rx * math.cos(t1), cy + ry * math.sin(t1))
            p2 = (cx + rx * math.cos(t2), cy + ry * math.sin(t2))
            c1 = (p1[0] - k * rx * math.sin(t1), p1[1] + k * ry * math.cos(t1))
            c2 = (p2[0] + k * rx * math.sin(t2), p2[1] - k * ry * math.cos(t2))
            if i == 0:
                d = "M %g %g" % p1
            d += " C %g %g %g %g %g %g" % (c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
        return d + " Z"
    if tag == "line":
        return "M %g %g L %g %g" % (num("x1", 0.0), num("y1", 0.0),
                                    num("x2", 0.0), num("y2", 0.0))
    if tag in ("polyline", "polygon"):
        pts = _parse_number_list(attrs.get("points", ""))
        if len(pts) < 4:
            warnings.count("malformed_primitive")
            return ""
        d = "M %g %g" % (pts[0], pts[1])
        for i in range(2, len(pts) - 1, 2):
            d += " L %g %g" % (pts[i], pts[i + 1])
        if tag == "polygon":
            d += " Z"
        return d
    warnings.count("unknown_primitive")
    return ""


# ============================================================================
# ==== SVG -> MOHO  (the walk)                                            ====
# ============================================================================


class _SvgBuilder:
    """Walks the SVG element tree and accumulates Moho MeshLayers: one per
    geometry element, every transform baked into the point coordinates."""

    def __init__(self, canvas_w: float, canvas_h: float, warnings: "WarningCounter"):
        self.canvas_w = canvas_w
        self.canvas_h = canvas_h
        self.warnings = warnings
        self.root: ET.Element = None   # set by build_document (for <use>)
        self.meshes: list = []
        self.gradients: dict = {}      # id -> gradient element
        self.used_ids: set = set()     # cycle protection for <use>
        self._layer_counter = 0

    # -- styles --------------------------------------------------------------

    def _element_style(self, el: ET.Element) -> dict:
        """Merged style: presentation attributes + the inline style
        string; the style string wins on conflict (SVG's own precedence)."""
        attrs = {"fill", "stroke", "stroke-width", "stroke-linecap",
                 "stroke-linejoin", "opacity", "fill-opacity",
                 "stroke-opacity", "fill-rule", "visibility", "display"}
        out = {k: el.get(k) for k in attrs if el.get(k) is not None}
        for k, v in parse_style(el.get("style")).items():
            if k in attrs:
                out[k] = v
        return out

    def _resolve_paint(self, value, warnings) -> tuple:
        """A fill/stroke value -> ('color', rgba), ('gradient', id) or
        (None, None)."""
        if value is None:
            return None, None
        if value.startswith("url("):
            m = re.match(r"url\(\s*#?([^)\s]+)\s*\)", value)
            return ("gradient", m.group(1)) if m else (None, None)
        c = parse_color(value, warnings)
        if c is None:
            return None, None
        return ("color", c)

    def _collect_gradients(self, el: ET.Element) -> None:
        if el.tag in ("{%s}linearGradient" % SVG_NS, "{%s}radialGradient" % SVG_NS):
            grad_id = el.get("id")
            if grad_id:
                self.gradients[grad_id] = el
        for child in el:
            self._collect_gradients(child)

    def _gradient_fill_style(self, grad: ET.Element, loops_px: list) -> tuple:
        """An SVG gradient element + the shape's baked loops -> (Moho
        SS_Gradient2 dict, effect_scale, effect_rotation).

        Placement is an APPROXIMATION, carried over from the forward
        exporter's model (see lottie2moho.py's gradient_fill_style): the
        forward writer derives start/end from the shape's own bbox and
        effect_scale/effect_rotation, so the inverse solves those two
        from the SVG gradient's endpoints against the bbox - and leaves
        start/end unset, which is what the bbox-derived placement reads
        anyway.
        """
        stops = []
        for stop in grad.findall("{%s}stop" % SVG_NS):
            off = 0.0
            raw = stop.get("offset")
            if raw and raw.endswith("%"):
                off = max(0.0, min(1.0, float(raw[:-1]) / 100.0))
            elif raw:
                off = max(0.0, min(1.0, float(raw)))
            c = parse_color(stop.get("stop-color"), self.warnings)
            opacity = 1.0
            try:
                opacity = float(stop.get("stop-opacity", "1"))
            except ValueError:
                pass
            if c:
                c[3] = c[3] * opacity
                # stops are CHANNEL-shaped in a real file (measured on
                # SketchBone.mohoproj's 83 gradients), and start/end keys
                # do NOT exist there at all - plain values and None
                # endpoints made Moho render the gradient black (measured
                # 2026-08, t6 gate)
                stops.append({
                    "location": _static_channel("Val", round(off, 6)),
                    "color": _static_channel("Color", {
                        "r": round(c[0], 6), "g": round(c[1], 6),
                        "b": round(c[2], 6), "a": round(c[3], 6)}),
                })
        base = {"type": "SS_Gradient2", "through_alpha": False,
                "gradients": stops}
        if len(stops) < 2:
            self.warnings.count("gradient_too_few_stops")
            return None, 1.0, 0.0

        all_v = [pt for loop in loops_px for pt in loop]
        if not all_v:
            return None, 1.0, 0.0
        xs = [v[0] for v in all_v]
        ys = [v[1] for v in all_v]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        half_w, half_h = (max_x - min_x) / 2.0, (max_y - min_y) / 2.0
        if half_w <= 1e-9 or half_h <= 1e-9:
            return None, 1.0, 0.0

        units = grad.get("gradientUnits", "objectBoundingBox")
        if units not in ("objectBoundingBox", "userSpaceOnUse"):
            self.warnings.count("gradient_units")
        if grad.get("spreadMethod", "pad") != "pad":
            self.warnings.count("gradient_spread_method")

        def num(attr, default):
            try:
                return float(grad.get(attr, default))
            except (TypeError, ValueError):
                return float(default)

        is_radial = grad.tag == "{%s}radialGradient" % SVG_NS
        if units == "objectBoundingBox":
            x1, y1 = num("x1", 0.0), num("y1", 0.0)
            x2, y2 = num("x2", 1.0), num("y2", 0.0)
            s = (min_x + x1 * 2.0 * half_w, min_y + y1 * 2.0 * half_h)
            e = (min_x + x2 * 2.0 * half_w, min_y + y2 * 2.0 * half_h)
            cx, cy = num("cx", 0.5), num("cy", 0.5)
            r = num("r", 0.5)
            center = (min_x + cx * 2.0 * half_w, min_y + cy * 2.0 * half_h)
            r_px = r * (half_w + half_h)
        else:
            s = (num("x1", 0.0), num("y1", 0.0))
            e = (num("x2", 1.0), num("y2", 0.0))
            center = (num("cx", 0.5), num("cy", 0.5))
            r_px = num("r", 0.5)

        gx = grad.get("gradientTransform")
        if gx:
            gm = parse_transform(gx, self.warnings)
            s = _apply_matrix(gm, s[0], s[1])
            e = _apply_matrix(gm, e[0], e[1])
            center = _apply_matrix(gm, center[0], center[1])

        if is_radial:
            scale = r_px * 2.0 / (half_w + half_h)
            return {**base, "gradient_type": 1}, scale, 0.0
        dx = (e[0] - s[0]) / 2.0
        dy = (e[1] - s[1]) / 2.0
        scale = math.hypot(dx / half_w, dy / half_h)
        rotation = math.atan2(-dy / half_h, dx / half_w)
        # Moho's renderer has a measured DEAD ANGLE at exactly -45 deg
        # (rotation -pi/4): a gradient there renders FLAT at every
        # effect_scale, while -42 and -48 deg render fine (grid-mapped
        # 2026-08: scales 1.0/1.414/1.96/2.83 x angles -90..+90 step 15).
        # Nudging it 3 degrees off the dead spot is visually
        # indistinguishable and beats a flat fill.
        if abs(rotation - (-math.pi / 4.0)) < 0.01:
            rotation += math.radians(3.0)
        return {**base, "gradient_type": 0}, scale, rotation

    # -- geometry ------------------------------------------------------------

    def _build_mesh(self, el: ET.Element, name: str, matrix: tuple) -> None:
        """One geometry element -> one MeshLayer (appended to self.meshes)."""
        style = self._element_style(el)
        if style.get("display") == "none" or style.get("visibility") in ("hidden", "collapse"):
            return
        d = el.get("d", "")
        if el.tag not in ("{%s}path" % SVG_NS,):
            d = primitive_to_path(el.tag, el.attrib, self.warnings)
        if not d.strip():
            self.warnings.count("empty_path")
            return

        subpaths = _PathParser(d, self.warnings).parse()
        loops = []
        for points, i_handles, o_handles, closed in subpaths:
            if len(points) < 2 or (closed and len(points) < 3):
                continue
            # Bake through the element matrix: vertices fully, handle
            # OFFSETS through the linear part only (same rule as
            # lottie2moho.py's walk).
            v = [_apply_matrix(matrix, px, py) for px, py in points]
            lin = (matrix[0], matrix[1], matrix[2], matrix[3], 0.0, 0.0)
            # handle OFFSETS go through the linear part only:
            # lin(handle) - lin(vertex) (the translation must cancel)
            lv = [_apply_matrix(lin, px, py) for px, py in points]
            i_off = [(_apply_matrix(lin, hx, hy)[0] - lv[k][0],
                      _apply_matrix(lin, hx, hy)[1] - lv[k][1])
                     for k, (hx, hy) in enumerate(i_handles)]
            o_off = [(_apply_matrix(lin, hx, hy)[0] - lv[k][0],
                      _apply_matrix(lin, hx, hy)[1] - lv[k][1])
                     for k, (hx, hy) in enumerate(o_handles)]
            # WINDING: pixel_to_moho's y-flip REVERSES every loop's
            # winding; reversing the vertex order undoes it (design 3.2 -
            # measured during the Lottie work).  Handles swap sides with
            # the reversal: vertex k's new in-handle IS the old vertex's
            # out-handle.
            v = list(reversed(v))
            i_off = list(reversed(o_off))
            o_off = list(reversed(i_off))
            loops.append((v, i_off, o_off, closed))

        if not loops:
            self.warnings.count("empty_path")
            return

        # one shape; consecutive subpaths are its loops (design 4.3)
        mesh = {
            "type": "Mesh",
            "curve_interpretation": 1,
            "next_shape_id": 2,
            "anim_shape_order": False,
            "shape_order": _static_channel("String", "1"),
            "points": [],
            "curves": [],
            "shapes": [],
            "groups": [],
        }
        shape = {
            "type": "Shape",
            "name": "S1",
            "id": 1,
            "selected": False,
            "has_fill": False,
            "has_outline": False,
            "fill_allowed": True,
            "combo_mode": 0,
            "combo_blend_anim": _static_channel("Val", 0.0),
            "edges": {"curve": [], "segment": [], "flag": []},
            "style": _style_dict(),
            "effect_scale": _static_channel("Val", 1.0),
            "effect_rotation": _static_channel("Val", 0.0),
            "effect_offset": _static_channel("Vec2", {"x": 0.0, "y": 0.0}),
            "3d_thickness": _static_channel("Val", 0.125),
            "inherited_style_name": "",
            "inherited_style2_name": "",
        }

        # SVG's DEFAULT fill is black - an element without a fill
        # attribute is not an "unknown colour", so the default bypasses
        # the colour parser (which would warn on the named colour).
        fill_value = style.get("fill")
        fill_kind, fill_paint = (("color", [0.0, 0.0, 0.0, 1.0])
                                 if fill_value is None
                                 else self._resolve_paint(fill_value, self.warnings))
        stroke_kind, stroke_paint = self._resolve_paint(
            style.get("stroke"), self.warnings)

        # SVG fills open subpaths by implicitly closing them.  A shape
        # that keeps an open curve while has_fill is true does not
        # render at all in Moho (measured: the whole shape vanishes), so
        # every open loop is closed when the element carries a fill.
        if fill_kind is not None:
            loops = [(v, i_off, o_off, True) for v, i_off, o_off, closed in loops]

        opacity = 1.0
        fill_opacity = 1.0
        stroke_opacity = 1.0
        try:
            opacity = float(style.get("opacity", "1"))
        except ValueError:
            pass
        try:
            fill_opacity = float(style.get("fill-opacity", "1"))
        except ValueError:
            pass
        try:
            stroke_opacity = float(style.get("stroke-opacity", "1"))
        except ValueError:
            pass

        if fill_kind == "color":
            shape["has_fill"] = True
            shape["style"]["fill_color"] = _moho_color(fill_paint,
                                                       opacity * fill_opacity)
        elif fill_kind == "gradient":
            grad = self.gradients.get(fill_paint)
            if grad is None:
                self.warnings.count("gradient_missing")
            else:
                fill_style, scale, rotation = self._gradient_fill_style(
                    grad, [loop[0] for loop in loops])
                if fill_style is not None:
                    shape["has_fill"] = True
                    shape["style"]["fill_style"] = fill_style
                    # the parallel _id integer = the effect kind
                    # (SS_Gradient2 = 9, docs/moho-project-file-format.md
                    # section 8.3) - real files always carry it next to
                    # the slot, and Moho's renderer reads the gradient
                    # only when it is there (measured 2026-08: without it
                    # the shape renders the flat fill_color)
                    shape["style"]["fill_style_id"] = 9
                    # real gradient styles carry the FIRST stop's colour
                    # as their plain fill_color (measured on
                    # FoxAndGhost.animeproj)
                    first = fill_style["gradients"][0]["color"]
                    shape["style"]["fill_color"] = first
                    shape["effect_scale"]["val"] = [round(scale, 6)]
                    shape["effect_rotation"]["val"] = [round(rotation, 6)]

        if stroke_kind == "color":
            try:
                width = float(style.get("stroke-width", "1"))
            except ValueError:
                width = 1.0
            if width > 0:
                shape["has_outline"] = True
                shape["style"]["line_color"] = _moho_color(stroke_paint,
                                                           opacity * stroke_opacity)
                # the inverse of the forward writer's stroke formula:
                # stroke_px = line_width * canvas_height (default stroke_mul 2
                # and point_width 1 cancel out - see lottie2moho.py)
                shape["style"]["line_width"] = round(width / self.canvas_h, 6)
                shape["style"]["line_caps"] = _CAP_NAMES.get(
                    style.get("stroke-linecap", "butt"), 0)
                if style.get("stroke-linejoin", "miter") != "miter":
                    self.warnings.count("stroke_linejoin")
        elif stroke_kind == "gradient":
            self.warnings.count("stroke_gradient")

        if style.get("fill-rule", "nonzero") != "nonzero":
            self.warnings.count("evenodd_fill_rule")

        # loops -> points/curves/edges (the lottie2moho.py _add_loop shape)
        h2 = self.canvas_h / 2.0
        w2 = self.canvas_w / 2.0
        for v, i_off, o_off, closed in loops:
            base_index = len(mesh["points"])
            curve_points = []
            for k in range(len(v)):
                x, y = v[k]
                mx, my = (x - w2) / h2, -(y - h2) / h2
                # handles: offsets in pixel space -> Moho units, then
                # ABSOLUTE handle points for the fit
                hix, hiy = i_off[k][0] / h2, -i_off[k][1] / h2
                hox, hoy = o_off[k][0] / h2, -o_off[k][1] / h2
                mesh["points"].append({
                    "type": "Point",
                    "position": _static_channel(
                        "Vec2", {"x": round(mx, 6), "y": round(my, 6)}),
                    "width": _static_channel("Val", 1.0),
                    "opacity": _static_channel("Val", 1.0),
                    "color_drift": _static_channel("Val", 0.0),
                    "parent": -2,
                    "selected": False,
                    "colored": False,
                    "color": _static_channel("Color", {"r": 1.0, "g": 1.0,
                                                        "b": 1.0, "a": 1.0}),
                    "color_strength": _static_channel("Val", 1.0),
                    "curves": [{"curve": 0, "curve_points": base_index + k}],
                })
                curve_points.append({"point": k, "segments_on": True})

            def neighbour(kk: int, side: int):
                if closed:
                    return (len(v) + kk + side) % len(v)
                j = kk + side
                return j if 0 <= j < len(v) else kk

            for k in range(len(v)):
                p = V2(mesh["points"][base_index + k]["position"]["val"][0]["x"],
                       mesh["points"][base_index + k]["position"]["val"][0]["y"])
                pv = V2(mesh["points"][base_index + neighbour(k, -1)]["position"]["val"][0]["x"],
                        mesh["points"][base_index + neighbour(k, -1)]["position"]["val"][0]["y"])
                nx = V2(mesh["points"][base_index + neighbour(k, +1)]["position"]["val"][0]["x"],
                        mesh["points"][base_index + neighbour(k, +1)]["position"]["val"][0]["y"])
                h_in = p.add(V2(i_off[k][0] / h2, -i_off[k][1] / h2))
                h_out = p.add(V2(o_off[k][0] / h2, -o_off[k][1] / h2))
                params = fit_curve_point(p, pv, nx, h_in, h_out)
                curve_points[k].update(
                    {name: _static_channel("Val", value)
                     for name, value in params.items()})

            # the curve's "point" entries are ABSOLUTE indices into
            # mesh.points - the loop-local k must be offset (the hole
            # curve of a multi-loop shape references the OUTER loop's
            # points without this - measured 2026-08 on the donut gate)
            for k in range(len(v)):
                curve_points[k]["point"] = base_index + k
            curve_index = len(mesh["curves"])
            for k in range(len(v)):
                mesh["points"][base_index + k]["curves"][0]["curve"] = curve_index
            mesh["curves"].append({
                "type": "Curve",
                "num_points": len(v),
                "closed": closed,
                "profile_layer_uuid": "",
                "profile_curve_id": -1,
                "profile_repeat": 16,
                "points": curve_points,
                "start_percent": _static_channel("Val", -0.1),
                "end_percent": _static_channel("Val", 1.1),
                "profile_offset": _static_channel("Val", 0.0),
            })
            n_segments = len(v) if closed else max(0, len(v) - 1)
            shape["edges"]["curve"].extend([curve_index] * n_segments)
            shape["edges"]["segment"].extend(range(n_segments))
            shape["edges"]["flag"].extend([0] * n_segments)

        mesh["shapes"].append(shape)
        self.meshes.append((name, mesh))

    # -- the walk ------------------------------------------------------------

    def _element_name(self, el: ET.Element) -> str:
        if el.get("id"):
            return el.get("id")
        self._layer_counter += 1
        tag = el.tag.rsplit("}", 1)[-1]
        return "%s %d" % (tag, self._layer_counter)

    def walk(self, el: ET.Element, matrix: tuple) -> None:
        tag = el.tag
        if not isinstance(tag, str) or not tag.startswith("{"):
            return                      # comments / processing instructions
        local = tag.rsplit("}", 1)[-1]
        if local in ("path", "rect", "circle", "ellipse", "line",
                     "polyline", "polygon"):
            m = compose_matrix(matrix, parse_transform(el.get("transform"), self.warnings))
            self._build_mesh(el, self._element_name(el), m)
        elif local == "g" or local == "svg" or local == "a":
            m = compose_matrix(matrix, parse_transform(el.get("transform"), self.warnings))
            for child in el:
                self.walk(child, m)
        elif local == "use":
            href = el.get(XLINK_NS + "href") or el.get("href")
            ref_id = (href or "").lstrip("#")
            if not ref_id or ref_id in self.used_ids:
                if ref_id in self.used_ids:
                    self.warnings.count("use_cycle")
                return
            m = parse_transform(el.get("transform"), self.warnings)
            x, y = 0.0, 0.0
            if el.get("x") is not None or el.get("y") is not None:
                try:
                    x = float(el.get("x", "0"))
                    y = float(el.get("y", "0"))
                except ValueError:
                    pass
                m = compose_matrix((1.0, 0.0, 0.0, 1.0, x, y), m)
            target = None
            for cand in (self.root if self.root is not None else el).iter():
                if cand.get("id") == ref_id:
                    target = cand
                    break
            if target is None:
                self.warnings.count("use_missing")
                return
            self.used_ids.add(ref_id)
            self.walk(target, compose_matrix(matrix, m))
            self.used_ids.discard(ref_id)
        elif local in ("defs", "linearGradient", "radialGradient", "style",
                       "title", "desc", "metadata", "symbol", "clipPath",
                       "mask", "filter", "marker"):
            if local == "clipPath":
                self.warnings.count("clip_path_ignored")
            elif local == "mask":
                self.warnings.count("mask_ignored")
            elif local == "filter":
                self.warnings.count("filter_ignored")
            elif local == "marker":
                self.warnings.count("marker_ignored")
            elif local == "style":
                self.warnings.count("style_element_ignored")
            return                      # defs/gradients handled via self.gradients
        elif local == "text":
            self.warnings.count("text_element")
        elif local == "image":
            self.warnings.count("image_element")
        else:
            self.warnings.count("unsupported_element")
            for child in el:
                self.walk(child, matrix)


# ============================================================================
# ==== DOCUMENT ASSEMBLY                                                  ====
# ============================================================================


def build_document(svg_root: ET.Element, warnings: "WarningCounter") -> dict:
    """The .mohoproj root object for one parsed SVG document (design
    sections 1, 3 and 7)."""
    # canvas: the viewBox when present (design 3), else width/height
    vb = svg_root.get("viewBox")
    if vb:
        parts = _parse_number_list(vb)
        if len(parts) == 4:
            vb_x, vb_y, vb_w, vb_h = parts
            canvas_w, canvas_h = vb_w, vb_h
        else:
            warnings.count("malformed_viewbox")
            vb_x = vb_y = 0.0
            canvas_w = float(svg_root.get("width", "512").replace("px", "") or 512)
            canvas_h = float(svg_root.get("height", "512").replace("px", "") or 512)
    else:
        vb_x = vb_y = 0.0
        vb_w = float(svg_root.get("width", "512").replace("px", "") or 512)
        vb_h = float(svg_root.get("height", "512").replace("px", "") or 512)
        canvas_w, canvas_h = vb_w, vb_h

    builder = _SvgBuilder(canvas_w, canvas_h, warnings)
    builder.root = svg_root
    builder._collect_gradients(svg_root)

    # root matrix: viewBox origin + user-unit -> pixel scaling
    root_matrix = compose_matrix(
        (canvas_w / vb_w, 0.0, 0.0, canvas_h / vb_h, 0.0, 0.0),
        (1.0, 0.0, 0.0, 1.0, -vb_x, -vb_y))
    builder.walk(svg_root, root_matrix)

    root = build_root_group()
    # paint order: SVG paints later elements on top and so does Moho -
    # the SAME convention, so document order is kept (unlike Lottie,
    # whose earlier-on-top order lottie2moho.py had to reverse).
    # Measured 2026-08: reversing here put the later SVG rect UNDER the
    # earlier one.
    for name, mesh in builder.meshes:
        root["layers"].append({
            "type": "MeshLayer",
            "name": name,
            "uuid": _new_layer_uuid(),
            "visible": True,
            "origin": {"x": 0.0, "y": 0.0},
            "transforms": dict(_IDENTITY_TRANSFORMS),
            "mesh": mesh,
        })

    return {
        "mime_type": MOHO_MIME_TYPE,
        "version": MOHO_FORMAT_VERSION,
        "major_version": 1,
        "rev_version": 0,
        **_document_scaffold(),
        "project_data": {
            "width": int(round(canvas_w)),
            "height": int(round(canvas_h)),
            "start_frame": 1,
            "end_frame": 2,
            "fps": 24.0,
            "back_color": {"r": 255, "g": 255, "b": 255, "a": 255},
            "display_quality": 45054,
            # ints 0, not booleans - Moho's loader rejects JSON `false`
            # here (measured 2026-08, lottie2moho.py)
            "noise_grain": 0,
            "pixelation": 0,
            "antialiasing": True,
            "depth_sort": False,
            "distance_sort": False,
            "depth_of_field": False,
            "focus_distance": 1.0,
            "focus_range": 0.0,
            "focus_blur": 0.01,
            # 0 / True are the values real documents carry (Bandit and
            # FoxAndGhost agree across formats); -1 / False made Moho
            # render gradient fills FLAT (measured 2026-08, t6 gate)
            "global_render_style_fill_style": 0,
            "global_render_style_line_style": 0,
            "global_render_style_layer_style": 0,
            "global_render_style_minimize_randomness": True,
            "stereo_mode": 0,
            "stereo_separation": 0.0,
            "extra_swf_frame": False,
            "color_palette": "Current",
            "soundtrack": "",
        },
        "styles": [],
        "animated_values": {
            "camera_track": {
                "type": "Vec3", "ref": False, "mute": False, "when": [0],
                "val": [{"x": 0.0, "y": 0.0, "z": 2.0 + math.sqrt(3.0)}],
                "interp": [_DEFAULT_INTERP],
            },
            "camera_zoom": _static_channel("Val", 2.0),
            "camera_roll": _static_channel("Val", 0.0),
            "camera_pan_tilt": _static_channel("Vec2", {"x": 0.0, "y": 0.0}),
            "timeline_markers": {
                "type": "String", "ref": True, "mute": False,
                "when": [-1000000], "val": [""],
                "interp": [_DEFAULT_INTERP],
            },
        },
        "layers": [root],
    }


# ============================================================================
# ==== WARNINGS  (one counted stderr line per dropped/approximated thing) ====
# ============================================================================


class WarningCounter:
    """Counted warnings, printed once at the end of a run - the same
    convention lottie2moho.py uses.  Every dropped or approximated
    feature increments a counter, never silence."""

    EXPLANATIONS = {
        "text_element": "text element dropped - no vector outline in v1",
        "image_element": "image element dropped - no image support in v1",
        "filter_ignored": "filter on an element ignored",
        "mask_ignored": "mask ignored",
        "clip_path_ignored": "clip-path ignored",
        "marker_ignored": "markers ignored",
        "style_element_ignored": "<style> element / external CSS ignored - "
                                "only presentation attributes and inline "
                                "style strings are read",
        "use_missing": "use references an id that does not exist - skipped",
        "use_cycle": "use reference cycle - skipped",
        "unknown_color": "unrecognised colour - black fallback",
        "unknown_transform": "unrecognised transform function - ignored",
        "unknown_command": "unrecognised path command - path truncated",
        "unknown_primitive": "unrecognised shape primitive - dropped",
        "malformed_path": "malformed path data - path truncated",
        "malformed_primitive": "malformed primitive attributes - dropped",
        "malformed_viewbox": "malformed viewBox - width/height used instead",
        "empty_path": "path with no usable subpaths - dropped",
        "evenodd_fill_rule": "fill-rule=evenodd has no exact Moho equivalent "
                             "- subpaths grouped as nonzero",
        "gradient_too_few_stops": "gradient with fewer than 2 stops - dropped",
        "gradient_missing": "fill references a gradient id that is not defined",
        "gradient_units": "gradientUnits other than the two standard values "
                          "- treated as objectBoundingBox",
        "gradient_spread_method": "spreadMethod other than pad - ignored",
        "stroke_gradient": "stroke with a gradient - dropped (Moho strokes "
                           "carry no gradient slot in this writer's model)",
        "stroke_linejoin": "stroke-linejoin other than miter - ignored",
        "unsupported_element": "unsupported element - children still walked",
    }

    def __init__(self):
        self.counts: dict = {}

    def count(self, name: str) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1

    def report(self) -> None:
        for name in sorted(self.counts):
            sys.stderr.write("  ! %s: %d - %s\n"
                             % (name, self.counts[name],
                                self.EXPLANATIONS.get(name, "")))


# ============================================================================
# ==== CLI  (argument parsing and file I/O only)                          ====
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a static SVG file to a Moho .mohoproj file.")
    parser.add_argument("input", help="path to the SVG file")
    parser.add_argument("--out", default=None, metavar="FILE",
                        help="output .mohoproj path (default: <input-stem>.mohoproj)")
    parser.add_argument("--validate", action="store_true",
                        help="schema-validate the emitted .mohoproj against "
                             "schema/project.schema.json (needs the optional "
                             "jsonschema package)")
    args = parser.parse_args()

    warnings = WarningCounter()
    try:
        tree = ET.parse(args.input)
    except ET.ParseError as exc:
        sys.stderr.write("error: not parseable SVG: %s\n" % exc)
        sys.exit(1)
    document = build_document(tree.getroot(), warnings)
    warnings.report()

    out_path = args.out or os.path.splitext(args.input)[0] + ".mohoproj"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(document, f)
    print("wrote %s (%d mesh layers)"
          % (out_path, len(document["layers"][0]["layers"])))

    if args.validate:
        try:
            import jsonschema  # noqa: F401 - optional dependency
        except ImportError:
            sys.stderr.write("note: --validate needs `pip install jsonschema`\n")
            sys.exit(1)
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "schema", "project.schema.json")
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)
        errors = list(jsonschema.Draft202012Validator(schema).iter_errors(document))
        if errors:
            sys.stderr.write("validate: FAILED\n")
            for err in errors[:10]:
                sys.stderr.write("  %s: %s\n" % ("/".join(map(str, err.path)),
                                                 err.message))
            sys.exit(1)
        print("validate: OK")


if __name__ == "__main__":
    main()
