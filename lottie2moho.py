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

Stdlib only (like every exporter here): argparse, json, math, os, uuid.
Nothing in moho2svg.py/moho2lottie.py changes - their byte-identical
exports are this tool's regression gate (make check-reference /
make check-lottie).

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


# ============================================================================
# ==== MOHO WRITING  (the output side: raw .mohoproj JSON dicts)         ====
# ============================================================================

MOHO_FORMAT_VERSION = 1045
MOHO_MIME_TYPE = "application/x-vnd.lm_mohodoc"

# A static, identity transform for a layer whose transforms are never
# animated.  Bare scalars are a legal Moho encoding for a never-animated
# value - Channel.of() reads them as one-keyframe constants (its own
# docstring), so no channel-shaped {"when"/"val"/"interp"} machinery is
# needed until Task 4 adds animation.
_IDENTITY_TRANSFORMS = {
    "translation": {"x": 0.0, "y": 0.0},
    "scale": {"x": 1.0, "y": 1.0},
    "rotation_z": 0.0,
    "flip_h": False,
    "flip_v": False,
}


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


def build_document(lottie: dict) -> dict:
    """Build the .mohoproj root object from a parsed Lottie document.

    Frame mapping: Lottie's `ip`/`op` bound the content (op is exclusive,
    the frame after the last one - moho2lottie.py writes end_frame + 1),
    so the Moho range is `ip` .. `op - 1`, rounded to the integer frame
    grid Moho keyframes live on.  Canvas size maps directly: both formats
    measure the canvas in pixels, and the 2-units-per-canvas-height Moho
    convention only enters once geometry exists (Task 2).
    """
    ip = float(lottie.get("ip", 0))
    op = float(lottie.get("op", ip + 1))
    return {
        "mime_type": MOHO_MIME_TYPE,
        "version": MOHO_FORMAT_VERSION,
        "major_version": 1,
        "rev_version": 0,
        "project_data": {
            "width": float(lottie.get("w", 0)),
            "height": float(lottie.get("h", 0)),
            "start_frame": int(round(ip)),
            "end_frame": int(round(op - 1)),
            "fps": float(lottie.get("fr", 24.0)),
        },
        "styles": [],
        "animated_values": {},
        "layers": [build_root_group()],
    }


# ============================================================================
# ==== WARNINGS  (one counted stderr line per dropped/approximated thing) ====
# ============================================================================


class WarningCounter:
    """Counted warnings, printed once at the end of a run.

    The same convention moho2lottie.py uses: every dropped or approximated
    feature increments a counter, never silence.  Task 7 fills the
    explanation table; until then the counters exist but nothing writes to
    them.
    """

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def count(self, name: str) -> None:
        """Increment the counter `name` by one."""
        self.counts[name] = self.counts.get(name, 0) + 1

    def report(self) -> None:
        """Print one stderr line per non-zero counter."""
        for name in sorted(self.counts):
            sys.stderr.write(f"  ! {name}: {self.counts[name]}\n")


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

    if args.validate:
        sys.stderr.write("note: --validate is not implemented yet (plan Task 7)\n")
    if args.assets_dir is not None:
        sys.stderr.write("note: --assets-dir is accepted but unused until "
                         "image layers land (plan Task 3)\n")

    out_path = args.out or os.path.splitext(args.input)[0] + ".mohoproj"
    lottie = load_lottie(args.input)
    document = build_document(lottie)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(document, f, ensure_ascii=False)
    print(f"wrote {out_path} ({len(lottie.get('layers', []))} lottie layers, "
          f"0 converted so far)")


if __name__ == "__main__":
    main()
