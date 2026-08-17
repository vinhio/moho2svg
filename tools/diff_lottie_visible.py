#!/usr/bin/env python3
"""Compare what two emitted Lottie files actually SHOW, layer by layer.

Not a pass/fail check - a comparison tool, for the question that keeps coming up
after a writer change: "did that move anything a viewer can see?"  It answers by
computing each layer's VISIBLE REGION with polygon algebra rather than pixels:

    visible = (union of the layer's own shape geometry)
              INTERSECT (its masksProperties accumulated in order)

and reporting each side's area plus the XOR between the two files.  A change that
only reorders vertices, or that alters a mask where the layer draws nothing, comes
out as 0.00 - which is exactly the distinction a rasterised diff cannot make and
a human eye cannot be asked to make reliably.

WHY THIS BEATS RASTERISING.  A hand-rolled "replay the Lottie as SVG" simulator
was tried first and actively misled: its approximate mask compositing showed a
dark ellipse across Bandit's ankle that no real player ever showed, and one whole
investigation went the wrong way behind it.  Polygon algebra has no such licence
- masksProperties modes "a" and "s" are exactly union and difference, so the
computed region either matches or it does not.

WHAT IT DOES NOT MODEL, deliberately: mask modes other than "a"/"s" (mode "i" is
ignored by real players anyway - see moho2lottie.py's own module docstring),
mask opacity and expansion, layer opacity/blend modes, gradients, and z-order
between layers.  It answers "which region of the canvas does this layer cover",
which is the question that separates a cosmetic change from a visible one.

Usage: diff_lottie_visible.py <a.json> <b.json> [--frames 25,60,100]
       [--layer SUBSTRING] [--quiet]

Needs `pyclipper` (the same optional dependency moho2lottie.py uses for
combo_mode==3 pre-clipping); exits 2 with a clear message if it is absent.
"""

import json
import sys

try:
    import pyclipper
except ImportError:
    pyclipper = None

SCALE = 1000            # pyclipper is integer-only; 1000x keeps sub-pixel detail


def _value(prop, frame):
    """A property's value at `frame` - the last keyframe at or before it."""
    k = prop.get("k")
    if isinstance(k, list) and k and isinstance(k[0], dict) and "s" in k[0]:
        best = k[0].get("s")
        for kf in k:
            if kf.get("t", 0) <= frame:
                best = kf.get("s")
        if isinstance(best, list):
            best = best[0] if best else None
        return best
    return k


def _to_paths(bez):
    v = (bez or {}).get("v") or []
    return [[(round(x * SCALE), round(y * SCALE)) for x, y in v]] if len(v) >= 3 else []


def _combine(acc, paths, union: bool):
    if not paths:
        return acc
    if not acc:
        return pyclipper.SimplifyPolygons(paths, pyclipper.PFT_NONZERO) if union else []
    pc = pyclipper.Pyclipper()
    pc.AddPaths(acc, pyclipper.PT_SUBJECT, True)
    pc.AddPaths(paths, pyclipper.PT_CLIP, True)
    return pc.Execute(pyclipper.CT_UNION if union else pyclipper.CT_DIFFERENCE,
                      pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)


def _intersect(a, b):
    if not a or not b:
        return []
    pc = pyclipper.Pyclipper()
    pc.AddPaths(a, pyclipper.PT_SUBJECT, True)
    pc.AddPaths(b, pyclipper.PT_CLIP, True)
    return pc.Execute(pyclipper.CT_INTERSECTION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)


def _area(paths):
    total = 0.0
    for p in paths:
        acc = 0.0
        for i in range(len(p)):
            x0, y0 = p[i]
            x1, y1 = p[(i + 1) % len(p)]
            acc += x0 * y1 - x1 * y0
        total += acc / 2.0
    return abs(total) / (SCALE * SCALE)


def _shape_paths(node, frame, out):
    if isinstance(node, dict):
        if node.get("ty") == "sh" and isinstance(node.get("ks"), dict):
            out.extend(_to_paths(_value(node["ks"], frame)))
        for key in ("it", "shapes"):
            for child in node.get(key) or []:
                _shape_paths(child, frame, out)
    elif isinstance(node, list):
        for child in node:
            _shape_paths(child, frame, out)


def visible_region(layer, frame):
    own = []
    raw = []
    _shape_paths(layer.get("shapes") or [], frame, raw)
    for path in raw:
        own = _combine(own, [path], union=True)
    mask = []
    for entry in layer.get("masksProperties") or []:
        paths = _to_paths(_value(entry.get("pt") or {}, frame))
        mode = entry.get("mode")
        if mode in ("a", "s"):
            mask = _combine(mask, paths, union=(mode == "a"))
    return _intersect(own, mask) if mask else own


def main() -> int:
    if pyclipper is None:
        print("diff_lottie_visible.py needs the optional 'pyclipper' package "
              "(pip install pyclipper, or use `make venv`)")
        return 2
    args = sys.argv[1:]
    frames = [25.0, 60.0, 100.0]
    if "--frames" in args:
        i = args.index("--frames")
        frames = [float(f) for f in args[i + 1].split(",")]
        del args[i:i + 2]
    needle = None
    if "--layer" in args:
        i = args.index("--layer")
        needle = args[i + 1]
        del args[i:i + 2]
    quiet = "--quiet" in args
    paths = [a for a in args if not a.startswith("--")]
    if len(paths) != 2:
        print(__doc__)
        return 2
    a_doc, b_doc = (json.load(open(p)) for p in paths)
    a_layers = {l.get("nm"): l for l in a_doc.get("layers") or []}
    b_layers = {l.get("nm"): l for l in b_doc.get("layers") or []}
    only_a = sorted(set(a_layers) - set(b_layers))
    only_b = sorted(set(b_layers) - set(a_layers))
    for name in only_a:
        print(f"  only in {paths[0].rsplit('/', 1)[-1]}: {name}")
    for name in only_b:
        print(f"  only in {paths[1].rsplit('/', 1)[-1]}: {name}")

    names = [n for n in a_layers if n in b_layers and (needle is None or needle in str(n))]
    print(f"{'frame':>6} {'layer':22s} {'A area':>11s} {'B area':>11s} {'XOR':>10s} {'XOR %':>7s}")
    worst = (0.0, None)
    for frame in frames:
        for name in names:
            va = visible_region(a_layers[name], frame)
            vb = visible_region(b_layers[name], frame)
            xor = _combine(_combine(va, vb, union=False), _combine(vb, va, union=False), union=True)
            aa, ab, ax = _area(va), _area(vb), _area(xor)
            rel = 100.0 * ax / max(aa, ab, 1e-9)
            if rel > worst[0]:
                worst = (rel, f"{name} at frame {frame:g}")
            if not quiet or rel > 1.0:
                print(f"{frame:6g} {str(name)[:22]:22s} {aa:11.1f} {ab:11.1f} {ax:10.2f} {rel:6.2f}%")
    print(f"\nworst visible difference: {worst[0]:.2f}%"
          + (f" ({worst[1]})" if worst[1] else "")
          + "\n(under ~0.1% is resampling noise on the boundary, not a visible change)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
