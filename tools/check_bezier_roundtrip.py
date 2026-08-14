#!/usr/bin/env python3
"""Check that build_path_bezier() describes the same curve as build_path_d().

Both are built from the same PathTracer output, so they must agree exactly.
This converts each emitted Lottie bezier back to absolute cubic control
points and compares them against the traced segments the SVG writer uses.

Exit status is 0 when every shape agrees, 1 otherwise.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moho2svg import (Channel, Exporter, PathTracer, build_deform_chain,
                       build_path_bezier, load_document)

MOHO_DIR = "moho"
FRAMES = [0.0, 7.0, 23.0]

# build_path_bezier() rounds to 3 decimals, matching build_path_d()'s
# f"{x:.3f}", and its tangents are DIFFERENCES of two rounded values, so a
# rebuilt control point can be off by up to two half-ulps of 0.001.  The
# tolerance has to sit above that, or a correct implementation fails this
# check.  It is still tight enough to catch any real geometry mistake, which
# would be off by pixels, not by a thousandth of one.
TOLERANCE = 3e-3


def absolute_segments(bezier):
    """Rebuild absolute (p0, c1, c2, p1) tuples from one Lottie bezier dict.

    Lottie stores `i` and `o` relative to their own vertex, so a segment
    running from vertex k to vertex k+1 has control points v[k] + o[k] and
    v[k+1] + i[k+1].
    """
    v, tin, tout, closed = bezier["v"], bezier["i"], bezier["o"], bezier["c"]
    count = len(v) if closed else len(v) - 1
    out = []
    for k in range(count):
        nxt = (k + 1) % len(v)
        out.append((
            (v[k][0], v[k][1]),
            (v[k][0] + tout[k][0], v[k][1] + tout[k][1]),
            (v[nxt][0] + tin[nxt][0], v[nxt][1] + tin[nxt][1]),
            (v[nxt][0], v[nxt][1]),
        ))
    return out


def traced_segments(geometries, edges, to_px):
    """The same segments the SVG writer walks, mapped to pixels and rounded
    the same way build_path_d()'s f"{x:.3f}" does, so both sides are
    compared at the same precision."""
    out = []
    for seg in PathTracer.trace(geometries, edges):
        pts = [to_px(p) for p in (seg.p0, seg.c1, seg.c2, seg.p1)]
        out.append(tuple((round(p.x, 3), round(p.y, 3)) for p in pts))
    return out


def check_document(path):
    """Compare both builders over one document. Returns the failure count."""
    Channel.reset_cache()
    doc = load_document(path)
    failures = 0
    for frame in FRAMES:
        exp = Exporter(doc)
        for ancestors, layer in doc.vector_layers():
            exp._active_actions = exp._active_actions_along(ancestors, frame)
            exp._layer_scale = exp._full_chain_matrix(ancestors, layer, frame).uniform_scale() or 1.0
            chain = build_deform_chain(ancestors, layer, frame, exp)
            geometries, to_px = exp._geometry_and_mapper(layer.mesh, chain, frame)
            exp._active_actions = []
            for index, shape in enumerate(layer.mesh.shapes):
                if not shape.edges:
                    continue
                expected = traced_segments(geometries, shape.edges, to_px)
                got = []
                for bezier in build_path_bezier(geometries, shape.edges, to_px):
                    got.extend(absolute_segments(bezier))
                if len(got) != len(expected):
                    print(f"  {os.path.basename(path)} {layer.name} shape[{index}] "
                          f"frame {frame}: {len(got)} segments, expected {len(expected)}")
                    failures += 1
                    continue
                for a, b in zip(got, expected):
                    if any(abs(x - y) > TOLERANCE for pa, pb in zip(a, b)
                           for x, y in zip(pa, pb)):
                        print(f"  {os.path.basename(path)} {layer.name} "
                              f"shape[{index}] frame {frame}: coordinates differ "
                              f"(got {a} expected {b})")
                        failures += 1
                        break
    return failures


def main():
    targets = sys.argv[1:] or sorted(
        os.path.join(MOHO_DIR, f) for f in os.listdir(MOHO_DIR)
        if f.endswith((".mohoproj", ".animeproj"))
    )
    failures = 0
    for path in targets:
        failures += check_document(path)
        print(f"checked {os.path.basename(path)}")
    if failures:
        print(f"\nFAIL: {failures} shape(s) disagree")
        return 1
    print(f"\nOK: both path builders agree on every shape in {len(targets)} document(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
