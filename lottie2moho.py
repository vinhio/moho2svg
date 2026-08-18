#!/usr/bin/env python3
r"""Lottie to Moho: reconstruct a .mohoproj from an animated Lottie JSON file.

The inverse of moho2lottie.py, under one overriding constraint stated in
docs/lottie-to-moho-design.md: Moho->Lottie BAKES a rig into per-frame
vertex positions, and no amount of reading can unbake it.  What this tool
writes is therefore a FLAT, UNRIGGED, DENSELY-KEYFRAMED Moho document -
valid and openable, playing identically, but with every frame of motion
stored as point-animation and layer-transform channels instead of bones.
That contract, the layer/geometry/animation mappings, and the verification
roundtrip are all in docs/lottie-to-moho-design.md; the task-by-task plan
is docs/lottie-to-moho-plan.md.

Stdlib only.  SELF-CONTAINED BY DESIGN: the constants and formulas the
conversion needs are vendored here (each marked "copied from ...") rather
than imported from moho2svg.py/moho2lottie.py, so this file's behaviour
cannot drift when those writers change - the plan's Task 2 originally
imported them; the author asked for a copy instead.

Usage:
    python3 lottie2moho.py input.json [--out OUT.mohoproj] [--assets-dir DIR]
"""

# ============================================================================
# ==== LOTTIE READING  (the input side: JSON as AE/lottie-web writes it)  ====
# ============================================================================

import argparse
import json
import math
import os
import sys
import uuid


def load_lottie(path: str) -> dict:
    """Read and parse a Lottie JSON file.  Kept separate from the builders
    below so the conversion logic itself never does file I/O."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def static_prop(prop: dict, name: str, warnings: "WarningCounter"):
    """The static value of an animated-or-static Lottie property.

    Returns the value and a bool `animated`.  An ANIMATED property here
    means its keyframe list has more than one entry - Task 5 gives those
    their channels; until then the FIRST keyframe's value is used and the
    frame(s) after it are wrong, so it is counted, never silent."""
    if not isinstance(prop, dict) or not prop.get("a"):
        return prop.get("k"), False
    frames = prop.get("k") or []
    if len(frames) > 1:
        warnings.count("animated_property_first_frame_only")
    return frames[0]["s"][0], True


# ============================================================================
# ==== MOHO WRITING  (the output side: raw .mohoproj JSON dicts)         ====
# ============================================================================

MOHO_FORMAT_VERSION = 1045

_DEFAULT_INTERP = {"im": 0, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0,
                   "s": False, "t": 0}


def _static_channel(kind: str, value) -> dict:
    """One Moho channel holding a single constant `value` - the shape every
    unanimated field is written as (copied from a real 1045 file)."""
    return {"type": kind, "ref": False, "mute": False, "when": [0],
            "val": [value], "interp": [_DEFAULT_INTERP]}
MOHO_MIME_TYPE = "application/x-vnd.lm_mohodoc"

# Copied from moho2svg.py's RenderSettings: the empirically-fit chord-
# length-weighted tangent-direction blend exponent (module docstring,
# BEZIER CURVES section - p10/p90 of 1.000 on the handle-length formula,
# 0.19 fit against real Moho exports for the direction).
TANGENT_BIAS = 0.19

# Copied from moho2svg.py's LINE_CAP_NAMES: Moho's line_caps numbering
# (0 butt, 1 round, 2 square) vs Lottie's lc (1 butt, 2 round, 3 square).
LOTTIE_TO_MOHO_CAP = {1: 0, 2: 1, 3: 2}

# A static, identity transform for a layer whose transforms are never
# animated.  Every field is a full CHANNEL, the way Moho itself writes
# them: the bare-scalar shorthand Channel.of() accepts on this repo's read
# side is NOT something Moho's own loader tolerates (measured 2026-08 -
# a layer whose transforms used it made Moho fail with "Type mismatch:
# got OBJECT expected DOUBLE" while the channel form loads).
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
    """A minimal 2D vector - the handful of operations the conversion
    needs.  Deliberately NOT imported from moho2svg.py (self-containment,
    see the module docstring); the forward handle model below is copied
    from there and operates on this class."""

    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

    def sub(self, other: "V2") -> "V2":
        return V2(self.x - other.x, self.y - other.y)

    def add(self, other: "V2") -> "V2":
        return V2(self.x + other.x, self.y + other.y)

    def __add__(self, other: "V2") -> "V2":
        return self.add(other)

    def __sub__(self, other: "V2") -> "V2":
        return self.sub(other)

    def scaled(self, k: float) -> "V2":
        return V2(self.x * k, self.y * k)

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "V2":
        n = self.length()
        return V2(self.x / n, self.y / n) if n > 1e-12 else V2(0.0, 0.0)

    def rotated(self, radians: float) -> "V2":
        """Rotate by `radians` - the same convention as moho2svg.py's
        Vec2.rotated."""
        co, si = math.cos(radians), math.sin(radians)
        return V2(self.x * co - self.y * si, self.x * si + self.y * co)

    def angle_to(self, other: "V2") -> float:
        """The signed angle (radians) to rotate `self` onto `other`, in
        the same convention as rotated()."""
        return math.atan2(self.x * other.y - self.y * other.x,
                          self.x * other.x + self.y * other.y)


def _new_layer_uuid() -> str:
    """A fresh UUID string in Moho's own uppercase form."""
    return str(uuid.uuid4()).upper()


def build_root_group() -> dict:
    """The one root GroupLayer every document's layers live under.

    `layers: []` must be PRESENT (not absent): Document's walk treats a
    missing "layers" key as a non-container, which would make the root
    group disappear from the tree.  `transforms` must also be present with
    all five keys - Layer._build indexes them directly.
    """
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
    content (`project_data`/`styles`/`layers`/`animated_values`).

    MOHO's own loader rejects a document without them ("Unable to load
    document (corrupt)", error 108) even though this repo's Document model
    loads such a file happily - measured 2026-08 on the first end-to-end
    conversion.  The values are copied from a real 1045 document (dates are
    fixed so the output stays deterministic for roundtrip checks)."""
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


def pixel_to_moho(p: V2, canvas_w: float, canvas_h: float) -> V2:
    """Canvas pixels -> Moho local units, the inverse of the default-camera
    mapping copied from moho2svg.py's module docstring (COORDINATES):

        pixel_x = moho_x * (height / 2) + width / 2
        pixel_y = height / 2 - moho_y * (height / 2)        (y is flipped)

    The written points therefore render back to the same pixels under an
    identity transform chain - the flat-bake contract.
    """
    h2 = canvas_h / 2.0
    return V2((p.x - canvas_w / 2.0) / h2, -(p.y - canvas_h / 2.0) / h2)


def forward_blend_direction(u: V2, v: V2) -> V2:
    """The tangent direction of the forward handle model, copied from
    moho2svg.py's BezierReconstructor.handle: the chord-length-weighted
    blend of the two unit chord vectors (P-prev) and (next-P), each
    weighted by the OTHER chord's length raised to TANGENT_BIAS - NOT
    plain normalize(next - prev), which is off by a median 3.4 degrees."""
    du, dv = u.length(), v.length()
    if du < 1e-12 or dv < 1e-12:
        return (u.add(v)).normalized()
    return (u.scaled(dv ** TANGENT_BIAS / du)
            + v.scaled(du ** TANGENT_BIAS / dv)).normalized()


def fit_curve_point(p: V2, prev: V2, nxt: V2,
                    h_in: V2, h_out: V2) -> dict:
    """Invert the forward handle model for one point, exactly.

    Copied-model inverse (moho2svg.py's BezierReconstructor.handle):
        handle = p + direction * (neighbour_distance * smoothness * weight)
                 rotated by offset
    where `direction` is forward_blend_direction above and `incoming`
    negates it.  Given the point, its two neighbours and the two Lottie
    handles, the inverse is CLOSED-FORM, not a numeric fit:

    - direction: the offset is the signed angle from the model's blended
      direction to the handle's own direction (exact for any handle).
    - length: smoothness * weight = handle_length / neighbour_distance.
      Moho's smoothness is per-POINT (shared by both handles) and weight
      per side, so smoothness = min(1, max(ratio_in, ratio_out)) and each
      weight = its ratio / smoothness.  Exact when both ratios <= 1 (a
      handle never longer than its chord); a longer handle is clamped and
      counted (degenerate artwork - Lottie handles longer than their chord
      loop over themselves).

    smoothness 0 (Moho's sharp corner) is reproduced exactly when both
    Lottie handles collapse onto the point (zero length).
    """
    u, v = p.sub(prev), nxt.sub(p)
    d_in = h_in.sub(p)       # points toward prev (Lottie's i[k] is relative to v[k])
    d_out = h_out.sub(p)     # points toward nxt
    len_in, len_out = d_in.length(), d_out.length()

    ratio_in = len_in / u.length() if u.length() > 1e-12 else 0.0
    ratio_out = len_out / v.length() if v.length() > 1e-12 else 0.0

    if len_in < 1e-9 and len_out < 1e-9:
        # Sharp corner: the forward model collapses BOTH handles onto the
        # point when smoothness is 0.
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


def loop_to_curve(loop_v: list, loop_i: list, loop_o: list,
                  canvas_w: float, canvas_h: float, closed: bool) -> tuple[list, dict]:
    """One Lottie loop -> Moho mesh points (static positions) and one
    Curve (`closed` mirrors the Lottie item's own "c").

    Returns (mesh_points, curve) where mesh_points is the list to extend
    the layer's shared `mesh.points` with (positions only - Task 5 turns
    these into animated channels) and `curve` references them by index
    into that shared list (the caller patches the indices).  The loop's
    winding is preserved exactly: vertex order is written through
    unchanged (design section 5.5 - holes depend on it).

    An OPEN loop stays an open Curve (Moho supports open curves; a
    stroke-only Lottie shape is exactly that - closing it would add a
    phantom segment and rotate the re-emitted trace seed).  At an open
    endpoint the missing neighbour is the point itself, which makes the
    fit collapse that side's handle exactly like the forward model does
    (BezierReconstructor.handle: open-curve endpoint, handle collapses
    onto the point)."""
    n = len(loop_v)
    pts_moho = [pixel_to_moho(V2(x, y), canvas_w, canvas_h) for x, y in loop_v]
    # Handles arrive as PIXEL offsets; the fit needs them in the same
    # Moho units as the points.  pixel_to_moho's linear part maps an
    # offset (dx, dy) -> (dx / h2, -dy / h2) - y flipped, same as points.
    h2 = canvas_h / 2.0
    hi = [V2(dx / h2, -dy / h2) for dx, dy in (loop_i or [[0.0, 0.0]] * n)]
    ho = [V2(dx / h2, -dy / h2) for dx, dy in (loop_o or [[0.0, 0.0]] * n)]

    def neighbour(k: int, side: int) -> V2:
        if closed:
            return pts_moho[(k + side) % n]
        j = k + side
        return pts_moho[j] if 0 <= j < n else pts_moho[k]

    curve_points = []
    for k in range(n):
        p, prev, nxt = pts_moho[k], neighbour(k, -1), neighbour(k, +1)
        # Lottie handles are offsets RELATIVE to their vertex; the fit
        # wants absolute points in Moho units.
        h_in = p.add(hi[k])
        h_out = p.add(ho[k])
        params = fit_curve_point(p, prev, nxt, h_in, h_out)
        # Curve points store each parameter as a CHANNEL in a real file
        # (bare doubles are this repo's reader-side shorthand only - Moho's
        # own loader rejects them, measured 2026-08).
        curve_points.append({
            "point": k,
            "segments_on": True,
            **{name: _static_channel("Val", value)
               for name, value in params.items()},
        })

    curve = {
        "type": "Curve",
        "num_points": n,
        "closed": closed,
        "profile_layer_uuid": "",
        "profile_curve_id": -1,
        "profile_repeat": 16,
        "points": curve_points,
        # Trims default to the untrimmed sentinels Moho writes (-0.1 /
        # 1.1); the exporter treats anything outside [0, 1] as untrimmed.
        "start_percent": _static_channel("Val", -0.1),
        "end_percent": _static_channel("Val", 1.1),
        "profile_offset": _static_channel("Val", 0.0),
    }
    return pts_moho, curve


def _moho_color(rgb: list, opacity: float) -> dict:
    """Lottie's 0..1 floats -> a Moho Color CHANNEL holding 0..1 floats,
    opacity folded into alpha.  Moho's own loader expects the channel
    form with float components (the 0..255 int dict this wrote before is
    accepted by this repo's Color.from_raw but rejected by Moho itself -
    measured 2026-08 while making the output openable)."""
    r, g, b = (rgb + [1.0])[:3]
    a = (rgb[3] if len(rgb) > 3 else 1.0) * opacity
    return _static_channel("Color", {
        "r": round(max(0.0, min(1.0, r)), 6),
        "g": round(max(0.0, min(1.0, g)), 6),
        "b": round(max(0.0, min(1.0, b)), 6),
        "a": round(max(0.0, min(1.0, a)), 6),
    })


def _image_layer_template() -> dict:
    """A full ImageLayer dict, the VALUES of a real 1045 file's image
    layer (copied verbatim from BoneStrengthTool.animeproj - Moho's loader
    rejects abbreviated layers AND zeroed fields, both measured 2026-08).
    The per-instance fields (name/uuid/width/height/image_fileref/
    image_path/transforms/psd_layer/psd_layerid/image_cropped) are set by
    the caller."""
    return {
        'type': 'ImageLayer',
        'image_fileref': {
            'relativeTo': '',
            'path': '',
        },
        'image_path': '',
        'psd_layer': 1,
        'psd_layerid': 12,
        'quality_level': 1,
        'interpreted_fps': -1.0,
        'avi_alpha': False,
        'movie_looping': False,
        'reverse_movie': False,
        'persist_first_frame': False,
        'persist_last_frame': False,
        'toon_effect': False,
        'toon_min_edge_threshold': 216,
        'toon_max_edge_threshold': 220,
        'toon_gray_threshold': 96,
        'toon_black_threshold': 32,
        'toon_saturation': 60,
        'toon_lightness': 0,
        'toon_quantize': 6,
        'sampling_mode': 1,
        'premultiplied_movie': False,
        'psd_layer_bounds': {
            'top': 1342,
            'left': 744,
            'right': 821,
            'bottom': 1801,
        },
        'width': 0.0,
        'height': 0.0,
        'image_cropped': False,
        'name': '',
        'uuid': '',
        'label_col': 0,
        'quality_flags': 4094,
        'animated_layer_effects': False,
        'origin': {
            'x': 0.0,
            'y': 0.0,
        },
        'parent_bone': -3,
        'visible': True,
        'shown_in_timeline': False,
        'consolidated_channels': False,
        'render_only': False,
        'edit_only': False,
        'scale_compensation': True,
        'scale_normalization': 1.0,
        'rotate_to_follow': False,
        'face_camera': False,
        'face_camera_mode': 2,
        'masking': 0,
        'mask_expansion': False,
        'blend_mode': 0,
        'camera_immune': False,
        'dof_immune': False,
        'layer_ref_uuid': '',
        'layer_ref_fileref': {
            'relativeTo': 'Absolute',
            'path': '',
        },
        'layer_ref_path': '',
        'layer_ref_same_doc': False,
        'layer_ref_mod_date': 0,
        'flexi_bone_subset': '',
        'flexi_bone_elbow': False,
        'timing_offset': 0,
        'follow_layer_uuid': '',
        'follow_curve': -1,
        'follow_bending': False,
        'distortion_layer_uuid': '',
        'random_num': 452582260,
        'transforms': {
            'translation': {
                'type': 'Vec3',
                'ref': True,
                'mute': False,
                'when': [0],
                'val': [{'x': 0.0, 'y': 0.0, 'z': 0.0}],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'scale': {
                'type': 'Vec3',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [{'x': 1.0, 'y': 1.0, 'z': 1.0}],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'rotation_x': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'rotation_y': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'rotation_z': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'flip_h': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'flip_v': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'shear': {
                'type': 'Vec3',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [{'x': 0.0, 'y': 0.0, 'z': 0.0}],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'following': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'physics_nudge': {
                'type': 'Vec2',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [{'x': 0.0, 'y': 0.0}],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
        },
        'layer_effects': {
            'visibility': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [True],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'blur': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'alpha': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [1.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'ambient_occlusion': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'threshold': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'noise': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 1, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'pixelation': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 1, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
        },
        'layer_shadow': {
            'on': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'angle': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [5.497787],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'offset': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.033333],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'blur': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.016667],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'expansion': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'color': {
                'type': 'Color',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [{'r': 0.0, 'g': 0.0, 'b': 0.0, 'a': 0.501961}],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'noise_amp': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'noise_scale': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [64.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'threshold': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'clip_to_group': False,
        },
        'layer_shading': {
            'on': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'angle': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [5.497787],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'offset': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.033333],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'blur': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.066667],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'contraction': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'color': {
                'type': 'Color',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [{'r': 0.0, 'g': 0.0, 'b': 0.0, 'a': 0.501961}],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'noise_amp': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'noise_scale': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [64.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'threshold': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
        },
        'perspective_shadow': {
            'on': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'blur': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.012346],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'scale': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [1.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'shear': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'color': {
                'type': 'Color',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [{'r': 0.0, 'g': 0.0, 'b': 0.0, 'a': 0.501961}],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'threshold': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
        },
        'motion_blur': {
            'on': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'sub_frames': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 1, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'frames': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [2.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'skip': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [1.0],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'alpha_start': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.3],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'alpha_end': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.1],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'radius': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.008333],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'frame_percentage': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [1.0],
                'interp': [{'im': 1, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'extended_frames': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.0],
                'interp': [{'im': 1, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
        },
        'layer_outline': {
            'on': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'width': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [0.004115],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'color': {
                'type': 'Color',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [{'r': 0.0, 'g': 0.0, 'b': 0.0, 'a': 1.0}],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
        },
        'layer_color': {
            'on': {
                'type': 'Bool',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [False],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'color': {
                'type': 'Color',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [{'r': 0.388235, 'g': 0.709804, 'b': 0.87451, 'a': 0.501961}],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
        },
        'timeline_markers': {
            'type': 'String',
            'ref': False,
            'mute': False,
            'when': [-1000000],
            'val': [''],
            'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
        },
        'physics': {
            'enabled': True,
            'static': False,
            'sleeping': False,
            'respawn': 0,
            'velocity': {
                'x': 0.0,
                'y': 0.0,
            },
            'density': 1.0,
            'friction': 0.3,
            'restitution': 0.5,
            'pivot': False,
            'enable_motor': False,
            'motor_speed': {
                'type': 'Val',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [3.141593],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
            'motor_torque': 10000.0,
            'force_field': False,
            'force_field_vector': {
                'type': 'Vec2',
                'ref': False,
                'mute': False,
                'when': [0],
                'val': [{'x': 0.0, 'y': 1.0}],
                'interp': [{'im': 2, 'v1': 0.1, 'v2': 0.5, 'in': 1, 'h': 0, 's': False, 't': 0}],
            },
        },
        'layer_user_comments': '',
        'layer_user_tags': '',
    }

def _style_dict() -> dict:
    """A full shape Style object with default (empty) values - the key set
    of a real 1045 file's style, including the brush fields, so Moho's
    loader finds everything it expects.  `fill_color`/`line_color` are
    replaced by the style items as they attach."""
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


def gradient_fill_style(gf: dict, loop_v: list, frame: float = None) -> tuple[dict, float, float]:
    """A Lottie "gf"/"gs" -> (Moho SS_Gradient2 style dict, effect_scale,
    effect_rotation).

    Stop colours/locations map directly (copied from moho2lottie.py's
    _eval_gradient, which reads `gradients`/`gradient_type` and the
    t <-> gradient_type table).  Placement: the forward writer does NOT
    read Moho's start/end - it derives Lottie s/e per frame from the
    shape's own bbox and effect_scale/effect_rotation (its
    _gradient_endpoints, copied below and inverted).  So the inverse
    SOLVES effect_scale/effect_rotation from the Lottie s/e against the
    bbox of the vertices being written, and leaves start/end unset (None),
    which is what the bbox-derived placement reads anyway:
      linear: dx = cos(rot)*scale*half_w, dy = -sin(rot)*scale*half_h
      radial: r  = 50*scale/100 * (half_w + half_h)
    Returns scale/rotation defaults (1.0, 0.0) when s/e are absent or the
    bbox is degenerate.
    """
    k = gf.get("g", {}).get("k")
    stops_data = k.get("k") if isinstance(k, dict) else k
    stops = []
    for i in range(0, len(stops_data) - 3, 4):
        loc = stops_data[i]
        r, g, b = stops_data[i + 1:i + 4]
        stops.append({"location": loc,
                      "color": {"r": r, "g": g, "b": b, "a": 1.0}})
    if len(stops) < 2:
        return None, 1.0, 0.0

    # bbox of the shape's loops' vertices, in pixels (the same bbox the
    # forward writer computes from the emitted beziers - one shape may
    # have several loops: outer boundary plus holes).
    all_v = loop_v if (loop_v and isinstance(loop_v[0][0], (int, float))) \
        else [pt for loop in loop_v for pt in loop]
    xs = [v[0] for v in all_v]
    ys = [v[1] for v in all_v]
    half_w, half_h = (max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0
    s, e = _plain(gf.get("s"), frame), _plain(gf.get("e"), frame)
    base = {"type": "SS_Gradient2", "through_alpha": False,
            "gradients": stops, "start": None, "end": None}
    if not (s and e and half_w > 1e-9 and half_h > 1e-9):
        return {**base, "gradient_type": 0}, 1.0, 0.0

    if gf.get("t") == 2:                                   # radial
        r_px = math.hypot(e[0] - s[0], e[1] - s[1])
        scale = r_px * 2.0 / (half_w + half_h)
        return {**base, "gradient_type": 1}, scale, 0.0
    dx = (e[0] - s[0]) / 2.0
    dy = (e[1] - s[1]) / 2.0
    scale = math.hypot(dx / half_w, dy / half_h)
    rotation = math.atan2(-dy / half_h, dx / half_w)
    return {**base, "gradient_type": 0}, scale, rotation


def _ellipse_loop(cx, cy, rx, ry) -> tuple[list, list, list]:
    """Four-point cubic approximation of an ellipse (kappa = 0.5522847) -
    the same constant every vector tool uses."""
    k = 0.5522847498307936
    v = [[cx + rx, cy], [cx, cy + ry], [cx - rx, cy], [cx, cy - ry]]
    i = [[0.0, -k * ry], [-k * rx, 0.0], [0.0, k * ry], [k * rx, 0.0]]
    o = [[0.0, k * ry], [k * rx, 0.0], [0.0, -k * ry], [-k * rx, 0.0]]
    return v, i, o


def primitive_loop(item: dict, frame: float = None) -> tuple[list, list, list]:
    """A Lottie rc/el/sr primitive -> one closed bezier loop (v, i, o).
    Moho has no primitive shapes - everything is curves (design 5.4)."""
    ty = item.get("ty")
    p = _plain(item.get("p"), frame) or [0.0, 0.0]
    s = _plain(item.get("s"), frame) or [100.0, 100.0]
    if ty == "el":
        rx, ry = abs(s[0]) / 2.0, abs(s[1]) / 2.0
        return _ellipse_loop(p[0], p[1], rx, ry)
    if ty == "rc":
        w, h = abs(s[0]), abs(s[1])
        rd = _scalar(item.get("r"), 0.0, frame)
        x0, y0 = p[0] - w / 2.0, p[1] - h / 2.0
        x1, y1 = p[0] + w / 2.0, p[1] + h / 2.0
        if rd <= 0:
            v = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            i = [[0.0, 0.0]] * 4
            o = [[0.0, 0.0]] * 4
            return v, i, o
        r = min(rd, w / 2.0, h / 2.0)
        k = 0.5522847498307936 * r
        v = [[x0 + r, y0], [x1 - r, y0], [x1, y0 + r], [x1, y1 - r],
             [x1 - r, y1], [x0 + r, y1], [x0, y1 - r], [x0, y0 + r]]
        i = [[0.0, -k], [0.0, 0.0], [-k, 0.0], [0.0, 0.0],
             [0.0, k], [0.0, 0.0], [k, 0.0], [0.0, 0.0]]
        o = [[0.0, k], [0.0, 0.0], [k, 0.0], [0.0, 0.0],
             [0.0, -k], [0.0, 0.0], [-k, 0.0], [0.0, 0.0]]
        return v, i, o
    # ty == "sr" (star/polygon): straight segments between the points
    # (Moho renders them as beziers with zero handles, which the fit
    # maps to smoothness 0 corners).
    pt = int(_scalar(item.get("pt"), 5, frame))
    or_ = math.radians(_scalar(item.get("r"), 0.0, frame))
    ir = _scalar(item.get("ir"), 0.0, frame) / 100.0
    outer = abs(s[0]) / 2.0
    inner = outer * ir
    v = []
    for j in range(pt * 2):
        ang = or_ + math.pi * j / pt - math.pi / 2.0
        rad = outer if j % 2 == 0 else inner
        v.append([p[0] + rad * math.cos(ang), p[1] + rad * math.sin(ang)])
    n = len(v)
    i = [[0.0, 0.0]] * n
    o = [[0.0, 0.0]] * n
    return v, i, o


def compose_matrix(m1: tuple, m2: tuple) -> tuple:
    """m1 ∘ m2 - apply m2 first, then m1 (column vectors).  A 2x3 affine
    (a, b, c, d, e, f) as SVG does: x' = a x + c y + e."""
    a, b, c, d, e, f = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a * a2 + c * b2, b * a2 + d * b2,
            a * c2 + c * d2, b * c2 + d * d2,
            a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def _plain(v, frame: float = None):
    """Normalize a tr field to its plain value.  The Lottie SPEC stores tr
    fields plain, but moho2lottie.py (and other writers) emit them as
    {"a","k"} property objects - accept both, since the roundtrip check
    feeds this tool its own repo's output.  An ANIMATED property returns
    one keyframe's whole `s` value: a LIST for vector fields
    (p/a/s/gradient endpoints), a one-element list for scalar ones
    (r/w/o) - callers unwrap scalars with _scalar.

    `frame` selects WHICH keyframe: the last one at or before `frame`
    (the value a player would show), or the FIRST keyframe when frame is
    None (the static-first-frame policy Task 5 replaces with real
    channels).  Precomp instances pass their mapped asset frame."""
    if isinstance(v, dict) and v.get("s") and "x" in v and "y" in v:
        # SPLIT position: {"s": true, "x": {...}, "y": {...}} - two
        # independent channels that must be reassembled into [x, y].
        # Each sub-property may itself be animated, in which case _plain
        # returns a one-element list that must be unwrapped.
        xv = _plain(v["x"], frame)
        yv = _plain(v["y"], frame)
        if isinstance(xv, list) and len(xv) == 1:
            xv = xv[0]
        if isinstance(yv, list) and len(yv) == 1:
            yv = yv[0]
        return [xv, yv]
    if isinstance(v, dict) and "k" in v:
        k = v.get("k")
        if isinstance(k, list) and k and isinstance(k[0], dict) and "s" in k[0]:
            chosen = k[0]
            if frame is not None:
                for kf in k:
                    # some writers terminate the list with a bare {"t": N}
                    # marker - skip it, it has no value
                    if "s" in kf and kf.get("t", 0) <= frame:
                        chosen = kf
            return chosen["s"]    # animated property: the chosen keyframe
        return k
    return v


def _scalar(v, default, frame: float = None):
    """_plain()'s scalar counterpart: unwrap a one-element animated value,
    then fall back to `default` on falsy (0.0 / empty) values."""
    plain = _plain(v, frame)
    if isinstance(plain, list):
        plain = plain[0] if plain else default
    return plain if plain else default


def tr_matrix(tr: dict, frame: float = None) -> tuple:
    """A Lottie tr item -> a 2x3 affine matrix: T(p) R(r) S(s) T(-a).

    `frame` picks the keyframe for animated fields - see _plain."""
    a = _plain(tr.get("a"), frame) or [0.0, 0.0]
    p = _plain(tr.get("p"), frame) or [0.0, 0.0]
    s = _plain(tr.get("s"), frame) or [100.0, 100.0]
    r = _scalar(tr.get("r"), 0.0, frame)
    sx, sy = s[0] / 100.0, s[1] / 100.0
    co, si = math.cos(math.radians(r)), math.sin(math.radians(r))
    # R(r) S(s)
    m = (co * sx, si * sx, -si * sy, co * sy, 0.0, 0.0)
    # then T(-a), then T(p)
    return (m[0], m[1], m[2], m[3],
            -a[0] * m[0] - a[1] * m[2] + p[0],
            -a[0] * m[1] - a[1] * m[3] + p[1])


_IDENTITY_MATRIX = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class _MeshBuilder:
    """Accumulates one MeshLayer's points/curves/shapes while walking the
    Lottie shape items, applying nested gr/tr matrices to every
    coordinate (flat-bake: the layer's own transform stays identity)."""

    def __init__(self, canvas_w: float, canvas_h: float, warnings: "WarningCounter",
                 frame: float = 0.0):
        self.canvas_w = canvas_w
        self.canvas_h = canvas_h
        self.warnings = warnings
        self.frame = frame
        self.points: list = []
        self.curves: list = []
        self.shapes: list = []
        # Untransformed vertex sequences of every CLOSED loop written so
        # far, for the outline-duplicate test in walk().
        self._closed_loops: list = []

    @staticmethod
    def _apply(v: list, m: tuple) -> list:
        a, b, c, d, e, f = m
        return [a * v[0] + c * v[1] + e, b * v[0] + d * v[1] + f]

    def _new_shape(self) -> dict:
        """A fresh, edge-less shape dict - style items attach to it, loops
        append their edges to it.  Every field is written the way a real
        1045 file writes it (channels, not bare values), because Moho's
        own loader rejects the shorthand this repo's reader accepts."""
        shape = {
            "type": "Shape",
            "name": f"S{len(self.shapes) + 1}",
            "id": len(self.shapes) + 1,
            "selected": False,
            "has_fill": False,
            "has_outline": False,
            "fill_allowed": True,
            "combo_mode": 0,
            "combo_blend_anim": _static_channel("Val", 0.0),
            # Shape._build reads the edge list as THREE PARALLEL ARRAYS
            # (e["curve"], e["segment"], e["flag"]), not a list of objects.
            "edges": {"curve": [], "segment": [], "flag": []},
            # Style always carries the full set: _render_shape evaluates
            # line_color/line_width unconditionally, whatever has_* say.
            "style": _style_dict(),
            "effect_scale": _static_channel("Val", 1.0),
            "effect_rotation": _static_channel("Val", 0.0),
            "effect_offset": _static_channel("Vec2", {"x": 0.0, "y": 0.0}),
            "3d_thickness": _static_channel("Val", 0.125),
            "inherited_style_name": "",
            "inherited_style2_name": "",
        }
        self.shapes.append(shape)
        return shape

    def _add_loop(self, shape: dict, v: list, i_off: list, o_off: list,
                  closed: bool) -> None:
        """Convert one transformed loop to a curve and append its edges to
        `shape` - one Lottie sh item is one loop, but ONE Moho shape holds
        ALL of a fill's loops (outer boundary plus each hole), so several
        consecutive sh items may feed the same shape.  An open curve has
        one fewer segment than points (Curve's own docstring in
        moho2svg.py)."""
        pts_moho, curve = loop_to_curve(v, i_off, o_off,
                                        self.canvas_w, self.canvas_h, closed)
        base_index = len(self.points)
        for cp, pt in zip(curve["points"], pts_moho):
            cp["point"] = base_index
            # Real points carry `type`, CHANNEL-shaped position/width (the
            # bare {"x","y"} form this repo's reader tolerates is rejected
            # by Moho's own loader - "Type mismatch: got OBJECT expected
            # DOUBLE", measured 2026-08), the full field set, and `parent`
            # -2 ("no per-point binding").  The `curves` back-reference
            # names the curve being built - unknown until the curve index
            # is taken below, so it is patched after the loop.
            self.points.append({
                "type": "Point",
                "position": _static_channel(
                    "Vec2", {"x": round(pt.x, 6), "y": round(pt.y, 6)}),
                "width": _static_channel("Val", 1.0),
                "opacity": _static_channel("Val", 1.0),
                "color_drift": _static_channel("Val", 0.0),
                "parent": -2,
                "selected": False,
                "colored": False,
                "color": _static_channel("Color", {"r": 1.0, "g": 1.0,
                                                    "b": 1.0, "a": 1.0}),
                "color_strength": _static_channel("Val", 1.0),
                "curves": [{"curve": 0, "curve_points": base_index}],
            })
            base_index += 1
        curve_index = len(self.curves)
        for i in range(len(curve["points"])):
            self.points[len(self.points) - len(curve["points"]) + i] \
                ["curves"][0]["curve"] = curve_index
        self.curves.append(curve)
        n_segments = (len(curve["points"]) if closed
                      else max(0, len(curve["points"]) - 1))
        shape["edges"]["curve"].extend([curve_index] * n_segments)
        shape["edges"]["segment"].extend(range(n_segments))
        shape["edges"]["flag"].extend([0] * n_segments)

    def _apply_style_item(self, item: dict, shape: dict, loops: list) -> None:
        """Attach a fl/st/gf/gs item to the shape that preceded it in the
        item stream (Lottie's own convention: style items follow their
        geometry)."""
        style = shape["style"]
        ty = item.get("ty")
        opacity = _scalar(item.get("o"), 100.0, self.frame) / 100.0
        if ty == "fl":
            rgb = _plain(item.get("c"), self.frame)
            if isinstance(rgb, list) and rgb:
                shape["has_fill"] = True
                style["fill_color"] = _moho_color(rgb, opacity)
        elif ty == "st":
            rgb = _plain(item.get("c"), self.frame)
            if isinstance(rgb, list) and rgb:
                shape["has_outline"] = True
                style["line_color"] = _moho_color(rgb, opacity)
                # stroke_px = line_width * canvas_height (copied formula:
                # line_width * point_width * canvas_height * stroke_mul / 2
                # with point_width 1 and the default stroke_mul 2) - so
                # the inverse is line_width = w_px / canvas_height.
                style["line_width"] = round(_scalar(item.get("w"), 1.0)
                                            / self.canvas_h, 6)
                style["line_caps"] = LOTTIE_TO_MOHO_CAP.get(item.get("lc", 1), 1)
        elif ty in ("gf", "gs"):
            fill_style, scale, rotation = gradient_fill_style(
                item, loops, self.frame)
            if fill_style is not None:
                shape["effect_scale"]["val"] = [round(scale, 6)]
                shape["effect_rotation"]["val"] = [round(rotation, 6)]
                if ty == "gf":
                    shape["has_fill"] = True
                    style["fill_style"] = fill_style
                else:
                    shape["has_outline"] = True
                    style["line_style"] = fill_style
        else:
            self.warnings.count("shape_item_skipped")

    def walk(self, items: list, matrix: tuple) -> None:
        """Recurse one group level.

        A group's tr applies to the WHOLE group (AE semantics) - it is
        conventionally the LAST item, so positional scoping would miss it;
        the matrix is composed once up front.  gr items recurse with that
        composed matrix, and their own tr composes on top inside their own
        walk call."""
        for item in items:
            if item.get("ty") == "tr":
                matrix = compose_matrix(matrix, tr_matrix(item, self.frame))

        # The forward writer emits ONE gr per Moho shape.  Within that gr:
        #   - every CLOSED sh item is one loop of the shape's fill
        #     (outer boundary + one sh item per hole - Lottie has no
        #     multi-loop sh),
        #   - an OPEN sh item is the same shape's OUTLINE redrawn as an
        #     open path (build_path_d close=False); it is NOT second
        #     geometry and must be skipped - UNLESS the gr has no closed
        #     sh at all, in which case the open sh IS the geometry (a
        #     stroke-only shape, which Moho stores as an open curve).
        has_closed_sh = False
        has_stroke = any(it.get("ty") == "st" for it in items)
        for item in items:
            if item.get("ty") == "sh":
                k = item.get("ks") or {}
                kv = k.get("k")
                if isinstance(kv, dict):
                    if kv.get("c"):
                        has_closed_sh = True
                elif kv:
                    if kv[0]["s"][0].get("c"):
                        has_closed_sh = True

        current = None   # (shape, [v per loop]) the next style items attach to
        for item in items:
            ty = item.get("ty")
            if ty == "tr":
                continue
            if ty == "gr":
                self.walk(item.get("it") or [], matrix)
                continue
            if ty in ("fl", "st", "gf", "gs"):
                if current is not None:
                    self._apply_style_item(item, current[0], current[1])
                continue
            if ty == "sh":
                ks = item.get("ks") or {}
                k = ks.get("k")
                if isinstance(k, dict):
                    loop_v, loop_i, loop_o = k.get("v"), k.get("i"), k.get("o")
                    closed = bool(k.get("c"))
                else:
                    # animated path: the keyframe a player would show at
                    # the bake frame (Task 5 turns these into channels)
                    self.warnings.count("animated_path_first_frame_only")
                    chosen = k[0]
                    for kf in k:
                        # skip bare {"t": N} terminators - no value in them
                        if "s" in kf and kf.get("t", 0) <= self.frame:
                            chosen = kf
                    frame0 = chosen["s"][0]
                    loop_v, loop_i, loop_o = (frame0.get("v"), frame0.get("i"),
                                              frame0.get("o"))
                    closed = bool(frame0.get("c"))
                if not loop_v:
                    current = None
                    continue
                if not closed:
                    # Two kinds of c:false paths exist in the wild.  The
                    # forward writer (moho2lottie) redraws a shape's
                    # OUTLINE as an open duplicate of its closed loop; but
                    # AE exports also draw REAL holes as open paths (a
                    # fill applies to the implicitly-closed region -
                    # lottie-web closes them for the fill).  Distinguish
                    # by the points: a duplicate repeats an
                    # already-written closed loop (possibly reversed, with
                    # or without a trailing repeat of the first vertex);
                    # anything else is real geometry and must be CLOSED so
                    # it participates as a region.  Measured 2026-08 on
                    # this file: head's hole is a c:false 5-point path
                    # with no closed twin, and skipping it as an outline
                    # duplicate left the head rendered without its hole.
                    pts = [tuple(p) for p in loop_v]
                    if len(pts) >= 2 and pts[0] == pts[-1]:
                        pts = pts[:-1]
                    duplicate = any(
                        pts == rec or list(reversed(pts)) == rec
                        for rec in self._closed_loops)
                    if duplicate and has_closed_sh and has_stroke:
                        continue
                    closed = True          # implicit fill closure
                if current is not None:
                    # next loop of the SAME shape: holes follow the outer
                    # boundary as consecutive closed sh items, and a
                    # stroke-only shape's outline spans consecutive open
                    # sh items (one per disconnected curve)
                    shape = current[0]
                else:
                    shape = self._new_shape()
                    current = (shape, [])
            elif ty in ("rc", "el", "sr"):
                loop_v, loop_i, loop_o = primitive_loop(item, self.frame)
                closed = True
                shape = self._new_shape()
                current = (shape, [])
            else:
                self.warnings.count("shape_item_skipped")
                current = None
                continue

            if closed:
                # remember this loop's vertex sequence so a later open
                # outline duplicate of it can be recognised and skipped
                pts = [tuple(p) for p in loop_v]
                if len(pts) >= 2 and pts[0] == pts[-1]:
                    pts = pts[:-1]
                if pts not in self._closed_loops:
                    self._closed_loops.append(pts)
            v = [self._apply(pt, matrix) for pt in loop_v]
            # handles are OFFSETS: only the linear part of the matrix
            lin = (matrix[0], matrix[1], matrix[2], matrix[3], 0.0, 0.0)
            i_off = [self._apply(pt, lin) for pt in loop_i] if loop_i else []
            o_off = [self._apply(pt, lin) for pt in loop_o] if loop_o else []
            # WINDING: pixel_to_moho's y-flip REVERSES every loop's winding
            # (measured: a +17,393 px^2 outer loop bakes to -0.27 units^2).
            # Moho's fill rule then reads outer as hole and hole as outer,
            # so every shape WITH holes renders inside-out while simple
            # single-loop shapes look right - exactly the observed split.
            # Reversing the vertex order undoes the flip; the handle
            # offsets swap sides with it (vertex k's new in-handle IS the
            # old vertex's out-handle).
            self._add_loop(shape, list(reversed(v)),
                           list(reversed(o_off)) if i_off else [],
                           list(reversed(i_off)) if o_off else [], closed)
            current[1].append(v)


def build_mesh_layer(layer: dict, canvas_w: float, canvas_h: float,
                     warnings: "WarningCounter",
                     initial: tuple = _IDENTITY_MATRIX,
                     frame: float = 0.0) -> dict:
    """One Lottie ty-4 layer -> one Moho MeshLayer (static geometry only).

    Walks the layer's shape items with a running affine for nested gr/tr
    groups, bakes every coordinate through it into Moho local units
    (flat-bake, design section 3), and finally REVERSES the shape list:
    Lottie paints the EARLIER shape on top, Moho the LATER (design
    section 4.4).  Style items attach to their preceding geometry in the
    original stream, so the walk runs in original order and only the
    finished shapes list is reversed - curve/point indices are untouched
    by that, which is exactly why the reversal is safe here.

    The walk STARTS from `initial` - the caller's FULL layer matrix
    (parent chain o this layer's own `ks`, see build_document's LAYER
    PARENTING note): every transform must be baked into the points, or
    the layer renders at the wrong x/y in Moho (measured 2026-08 - 27 of
    this file's 29 layers carry a non-default ks, and skipping it left
    them all at origin)."""
    builder = _MeshBuilder(canvas_w, canvas_h, warnings, frame)
    builder.walk(layer.get("shapes") or [], initial)
    builder.shapes.reverse()
    # The full mesh wrapper a real 1045 file carries; shape_order is the
    # "id|id|..." string channel, next_shape_id the next id to hand out.
    # anim_shape_order is a PLAIN bool in the file (not a channel) -
    # measured: the channel form makes Moho's loader fail.
    return {
        "type": "Mesh",
        "curve_interpretation": 1,
        "next_shape_id": len(builder.shapes) + 1,
        "anim_shape_order": False,
        "shape_order": _static_channel(
            "String", "|".join(str(s["id"]) for s in builder.shapes)),
        "points": builder.points,
        "curves": builder.curves,
        "shapes": builder.shapes,
        "groups": [],
    }


# ============================================================================
# ==== WARNINGS  (one counted stderr line per dropped/approximated thing) ====
# ============================================================================


class WarningCounter:
    """Counted warnings, printed once at the end of a run - the same
    convention moho2lottie.py uses.  Every dropped or approximated feature
    increments a counter, never silence."""

    EXPLANATIONS = {
        "animated_property_first_frame_only":
            "animated property converted from its FIRST keyframe only "
            "(channels arrive in plan Task 4/5)",
        "animated_path_first_frame_only":
            "animated path converted from its FIRST keyframe only "
            "(point channels arrive in plan Task 5)",
        "open_path_closed":
            "open path closed by joining its ends",
        "shape_item_skipped":
            "Lottie shape item kind with no Moho equivalent, skipped",
        "text_layer":
            "text layer (ty 5) dropped - no Moho equivalent",
        "precomp_missing":
            "precomp layer (ty 0) references an asset id that is not in the "
            "assets list - dropped",
        "image_missing":
            "image layer (ty 2) without a resolvable image asset - dropped",
        "solid_no_color":
            "solid layer (ty 1) without a usable #rrggbb colour - dropped",
        "other_layer_kind":
            "layer kind without a mapping yet, dropped",
        "mask_dropped":
            "masksProperties dropped (plan Task 6)",
    }

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def count(self, name: str) -> None:
        """Increment the counter `name` by one."""
        self.counts[name] = self.counts.get(name, 0) + 1

    def report(self) -> None:
        """Print one stderr line per non-zero counter."""
        for name in sorted(self.counts):
            sys.stderr.write(f"  ! {name}: {self.counts[name]} - "
                             f"{self.EXPLANATIONS.get(name, '')}\n")


# ============================================================================
# ==== DOCUMENT ASSEMBLY                                                  ====
# ============================================================================


def _write_embedded_image(payload: str, asset_id, out_dir: str):
    """Decode a base64 image payload (plain or data: URI) to an image file
    under `out_dir`, returning the absolute path, or None when the payload
    is neither a real file nor decodable image data.

    The extension follows the URI's declared type (Moho's own FreeImage
    loader takes webp/jpeg/png alike - measured 2026-08 with a real webp
    asset); an extensionless payload must carry the PNG or JPEG magic.
    """
    if not out_dir:
        return None
    import base64
    import re as _re
    data = payload
    ext = "png"
    m = _re.match(r"^data:image/(\w+);base64,(.*)$", payload, _re.S)
    if m:
        ext = m.group(1).lower().replace("jpeg", "jpg")
        data = m.group(2)
    try:
        raw = base64.b64decode(data)
    except Exception:  # noqa: BLE001 - not base64: keep the path treatment
        return None
    if not m:                      # extensionless: sniff the magic
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            ext = "png"
        elif raw[:2] == b"\xff\xd8":
            ext = "jpg"
        else:
            return None
    os.makedirs(out_dir, exist_ok=True)
    safe = _re.sub(r"[^A-Za-z0-9_-]+", "_", str(asset_id))[:60]
    path = os.path.join(out_dir, safe + "." + ext)
    with open(path, "wb") as f:
        f.write(raw)
    return os.path.abspath(path)


def build_document(lottie: dict, warnings: WarningCounter,
                 image_dir: str = None,
                 image_out_dir: str = None) -> dict:
    """Build the .mohoproj root object from a parsed Lottie document.

    Frame mapping: Lottie's `ip`/`op` bound the content (op is exclusive,
    the frame after the last one - moho2lottie.py writes end_frame + 1),
    so the Moho range is `ip` .. `op - 1`, rounded to the integer frame
    grid Moho keyframes live on.  Canvas size maps directly: both formats
    measure the canvas in pixels; pixel->Moho units happens per point via
    pixel_to_moho.

    Layer order: Lottie paints the EARLIER layer on top, Moho the LATER -
    the layer list is reversed (design section 4.4)."""
    ip = float(lottie.get("ip", 0))
    op = float(lottie.get("op", ip + 1))
    canvas_w = float(lottie.get("w", 0))
    canvas_h = float(lottie.get("h", 0))

    # LAYER PARENTING.  A layer's `ks` is relative to its PARENT layer's
    # transformed space, not to the comp: `parent` is the parent's index
    # (AE writes a layer's OWN index when unparented - a self-parent means
    # "no parent").  Flat-baking must therefore compose the whole parent
    # chain: M = M_parent o T(p) R(r) S(s) T(-a).  Measured 2026-08: this
    # file parents head/legs/wings/tail to wing_R (which itself swings
    # +-68 deg), and ignoring the chain left exactly those layers at the
    # wrong y - while the unparented foot_L/foot_R were correct, which is
    # why they read as the only right layers.
    layers = lottie.get("layers") or []
    # Precomposition: ty-0 layers instance an asset comp (refId -> assets[i]).
    # Their content is converted recursively, with the instance's matrix
    # composed as the BASE for the asset's own layer transforms, and with
    # the bake frame mapped into the asset's timeline (st = asset frame at
    # the instance's first visible parent frame; sr stretch is honoured in
    # that mapping - Task 5's channels will need the full time remap).
    # `image_dir` resolves image-layer asset paths ("p", optionally
    # under "u") against the source JSON's own directory.
    assets = {a.get("id"): a for a in lottie.get("assets") or []
              if isinstance(a, dict)}

    root = build_root_group()

    def convert_list(layer_list: list, base_matrix: tuple,
                     base_frame: float) -> None:
        """Append mesh layers for `layer_list` (in reverse = top-first paint
        order) to `root`.  `base_matrix` is the transform of the enclosing
        precomp instance (identity for the top comp); `base_frame` is the
        asset timeline frame the instance shows at the parent's first
        visible frame."""
        chain_cache: dict[int, tuple] = {}
        visiting: set = set()

        def chain_matrix(index: int) -> tuple:
            """The FULL matrix for `layer_list[index]` inside this comp:
            the parent chain (LAYER PARENTING, below) composed onto
            `base_matrix`."""
            if index in chain_cache:
                return chain_cache[index]
            if index in visiting or index < 0 or index >= len(layer_list):
                return base_matrix      # cycle / bad ref: treat as unparented
            visiting.add(index)
            layer = layer_list[index]
            parent = layer.get("parent")
            parent_matrix = base_matrix
            if parent is not None and parent != index:
                parent_matrix = chain_matrix(parent)
            visiting.discard(index)
            matrix = compose_matrix(parent_matrix,
                                    tr_matrix(layer.get("ks") or {}))
            chain_cache[index] = matrix
            return matrix

        def append_mesh(name: str, mesh: dict, visible: bool) -> None:
            if not mesh["shapes"]:
                return
            root["layers"].append({
                "type": "MeshLayer",
                "name": name or "Layer",
                "uuid": _new_layer_uuid(),
                "visible": visible,
                "origin": {"x": 0.0, "y": 0.0},
                "transforms": dict(_IDENTITY_TRANSFORMS),
                "mesh": mesh,
            })

        for index in range(len(layer_list) - 1, -1, -1):
            layer = layer_list[index]
            ty = layer.get("ty")
            if ty == 4:
                if layer.get("masksProperties"):
                    warnings.count("mask_dropped")
                mesh = build_mesh_layer(layer, canvas_w, canvas_h, warnings,
                                        chain_matrix(index), base_frame)
                append_mesh(layer.get("nm"), mesh,
                            not layer.get("hd", False))
            elif ty == 1:
                # SOLID layer: one filled rectangle, colour from "sc"
                # (#rrggbb).  Rendered as a synthetic rc primitive through
                # the ordinary mesh path - no special geometry code needed.
                sc = layer.get("sc") or "#000000"
                if sc.startswith("#") and len(sc) == 7:
                    sw = float(layer.get("sw", 100.0) or 100.0)
                    sh = float(layer.get("sh", 100.0) or 100.0)
                    synthetic = {
                        "shapes": [
                            {"ty": "rc",
                             "p": {"a": 0, "k": [sw / 2.0, sh / 2.0]},
                             "s": {"a": 0, "k": [sw, sh]}},
                            {"ty": "fl",
                             "c": {"a": 0, "k": [int(sc[1:3], 16) / 255.0,
                                                   int(sc[3:5], 16) / 255.0,
                                                   int(sc[5:7], 16) / 255.0]},
                             "o": {"a": 0, "k": 100.0}},
                        ],
                    }
                    mesh = build_mesh_layer(synthetic, canvas_w, canvas_h,
                                            warnings, chain_matrix(index),
                                            base_frame)
                    append_mesh(layer.get("nm"), mesh,
                                not layer.get("hd", False))
                else:
                    warnings.count("solid_no_color")
            elif ty == 2:
                # IMAGE layer: a real Moho ImageLayer.  The chain matrix is
                # NOT baked into points - it is decomposed into the layer's
                # own transform channels (translation in Moho units via
                # pixel_to_moho on the image CENTER; rotation negated by
                # the y-flip conjugation F R F^-1 = R(-theta); scale as the
                # column norms, one axis negated for a mirror).  The image
                # file is referenced by absolute path (relativeTo
                # "Absolute" - the only form confirmed against Moho's own
                # loader together with "Project"/"Library", measured
                # 2026-08).
                asset = assets.get(layer.get("refId"))
                image_path = asset.get("p") if asset else None
                if not image_path:
                    warnings.count("image_missing")
                    continue
                if image_dir and not os.path.isabs(image_path) \
                        and "/" not in image_path and "\\" not in image_path \
                        and len(image_path) < 512:
                    joined = os.path.normpath(os.path.join(
                        image_dir, asset.get("u") or "", image_path))
                    if os.path.isfile(joined):
                        image_path = joined
                if not os.path.isfile(image_path):
                    # Not a file on disk: try embedded base64 image data
                    # ("p" carries the payload inline, sometimes as a
                    # data: URI).  Write it next to the outputs so the
                    # reference stays real and local.
                    written = _write_embedded_image(
                        image_path, asset.get("id"), image_out_dir)
                    if written is None:
                        warnings.count("image_missing")
                        continue
                    image_path = written
                w_img = float(asset.get("w", 0) or 0)
                h_img = float(asset.get("h", 0) or 0)
                if w_img <= 0 or h_img <= 0:
                    warnings.count("image_missing")
                    continue
                a, b, c, d, e, f = chain_matrix(index)
                theta = math.atan2(b, a)
                sx = math.hypot(a, b)
                sy = math.hypot(c, d)
                if a * d - b * c < 0:
                    sy = -sy                  # mirrored: one axis flipped
                center = pixel_to_moho(V2(e, f), canvas_w, canvas_h)
                tpl = _image_layer_template()
                tpl["name"] = layer.get("nm") or "Layer"
                tpl["uuid"] = _new_layer_uuid()
                tpl["visible"] = not layer.get("hd", False)
                # image size in Moho units: px * 2 / canvas_height, so the
                # image renders at its native pixel size under the default
                # camera (the import-time 540 convention real files store
                # is irrelevant here - WE write the fields).
                tpl["width"] = w_img * 2.0 / canvas_h
                tpl["height"] = h_img * 2.0 / canvas_h
                tpl["image_fileref"] = {"relativeTo": "Absolute",
                                        "path": image_path}
                tpl["image_path"] = image_path
                tpl["transforms"]["translation"]["val"] = [
                    {"x": round(center.x, 6), "y": round(center.y, 6),
                     "z": 0.0}]
                tpl["transforms"]["scale"]["val"] = [
                    {"x": round(sx, 6), "y": round(sy, 6), "z": 1.0}]
                tpl["transforms"]["rotation_z"]["val"] = [
                    round(-math.degrees(theta), 6)]
                root["layers"].append(tpl)
            elif ty == 0:
                asset = assets.get(layer.get("refId"))
                if asset is None:
                    warnings.count("precomp_missing")
                    continue
                # asset frame at this instance's first visible parent frame:
                # asset_time = st + (parent_time - ip) / sr at parent_time=ip
                # -> asset_time = st.  sr < 0/absent reads as 1.
                sr = layer.get("sr") or 1.0
                asset_frame = float(layer.get("st", 0))
                convert_list(asset.get("layers") or [], chain_matrix(index),
                             asset_frame)
            elif ty == 5:
                warnings.count("text_layer")
            else:
                warnings.count("other_layer_kind")

    convert_list(layers, _IDENTITY_MATRIX, float(lottie.get("ip", 0)))

    return {
        "mime_type": MOHO_MIME_TYPE,
        "version": MOHO_FORMAT_VERSION,
        "major_version": 1,
        "rev_version": 0,
        **_document_scaffold(),
        "project_data": {
            "width": int(round(canvas_w)),
            "height": int(round(canvas_h)),
            "start_frame": int(round(ip)),
            "end_frame": int(round(op - 1)),
            "fps": float(lottie.get("fr", 24.0)),
            "back_color": {"r": 255, "g": 255, "b": 255, "a": 255},
            "display_quality": 45054,
            # These two are INTs in the format, not bools - Moho's loader
            # rejects JSON `false` here with the same Error 108 as a
            # missing block (measured 2026-08 by per-key swap into a real
            # 1045 document).
            "noise_grain": 0,
            "pixelation": 0,
            "antialiasing": True,
            "depth_sort": False,
            "distance_sort": False,
            "depth_of_field": False,
            "focus_distance": 1.0,
            "focus_range": 0.0,
            "focus_blur": 0.01,
            "global_render_style_fill_style": -1,
            "global_render_style_line_style": -1,
            "global_render_style_layer_style": -1,
            "global_render_style_minimize_randomness": False,
            "stereo_mode": 0,
            "stereo_separation": 0.0,
            "extra_swf_frame": False,
            "color_palette": "Current",
            "soundtrack": "",
        },
        "styles": [],
        "animated_values": {
            # All five are CHANNELS in a real 1045 file (Moho's loader
            # rejects plain values here - measured 2026-08 by swapping this
            # block into a real document).  camera_track's z is the default
            # camera distance 2 + sqrt(3) from moho2svg.py's CAMERA section
            # (copied from there), so the flat-baked artwork projects back
            # through the default camera unchanged.
            "camera_track": {
                "type": "Vec3", "ref": False, "mute": False, "when": [0],
                "val": [{"x": 0.0, "y": 0.0, "z": 2.0 + math.sqrt(3.0)}],
                "interp": [_DEFAULT_INTERP],
            },
            # zoom MUST be 2.0 - the default camera.  pixel_to_moho's
            # inverse mapping holds only under it (zoom 2 with
            # z = 2 + sqrt(3) satisfies z * tan(30/2 degrees) = 1, the
            # plain height/2 projection the flat-bake is written for);
            # any other zoom scales AND shifts every layer (measured
            # 2026-08: zoom 1.0 renders the whole document at ~0.46x in
            # Moho App).
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
# ==== CLI  (argument parsing and file I/O only)                          ====
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a Lottie JSON animation to a Moho .mohoproj file.")
    parser.add_argument("input", help="path to the Lottie JSON file")
    parser.add_argument("--out", default=None, metavar="FILE",
                        help="output .mohoproj path (default: <input-stem>.mohoproj)")
    parser.add_argument("--assets-dir", default=None, metavar="DIR",
                        help="directory for embedded images extracted from the "
                             "Lottie file (default: <output>.assets/, created "
                             "only when the file has image layers - Task 3)")
    parser.add_argument("--validate", action="store_true",
                        help="schema-validate the emitted .mohoproj against the "
                             "fragment schemas under schema/ - Task 7, not "
                             "implemented yet")
    args = parser.parse_args()

    warnings = WarningCounter()
    if args.validate:
        sys.stderr.write("note: --validate is not implemented yet (plan Task 7)\n")
    if args.assets_dir is not None:
        sys.stderr.write("note: --assets-dir is accepted but unused until "
                         "image layers land (plan Task 3)\n")

    out_path = args.out or os.path.splitext(args.input)[0] + ".mohoproj"
    lottie = load_lottie(args.input)
    image_out = os.path.join(os.path.dirname(os.path.abspath(args.out or "")),
                             "images") if args.out else None
    document = build_document(
        lottie, warnings,
        image_dir=os.path.dirname(os.path.abspath(args.input)),
        image_out_dir=image_out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(document, f, ensure_ascii=False)
    warnings.report()
    n_layers = len(document["layers"][0]["layers"])
    print(f"wrote {out_path} ({len(lottie.get('layers', []))} lottie layers, "
          f"{n_layers} converted)")


if __name__ == "__main__":
    main()
