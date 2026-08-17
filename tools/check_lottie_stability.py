#!/usr/bin/env python3
"""Check that an emitted Lottie file's animated shapes are INTERPOLABLE.

WHY THIS EXISTS, given `check_lottie_geometry.py` already checks geometry.
That script compares the writer against the same pipeline that fed it, so a
wrong decision the two sides SHARE is invisible to it - and three such defects
shipped past it in one sitting: a clip region read with the wrong fill rule, a
mask band whose two loops were both unioned, and the one this script is about, a
resampled loop whose vertex 0 wandered around the outline from frame to frame.

That last class needs no reference render to catch, only the emitted file.
Lottie interpolates vertex k of one keyframe straight to vertex k of the next,
with no notion of "the same physical point", so consecutive keyframes of one
shape have to keep their vertices in correspondence. When they do not, every
frame still looks correct ON ITS OWN and the shape spins or swims in between -
which is how it was reported: by eye, from a player, long after the file was
written and after `make check-lottie` had passed.

WHAT IT MEASURES.  For each consecutive keyframe pair of each animated `sh`:

  1. STRUCTURE - same vertex count and same open/closed flag on every keyframe.
     The writer already enforces this internally (LottieExporter._assert_stable);
     re-checking the emitted file catches a path that bypasses it.
  2. REALIGNMENT GAIN - both keyframes are moved to their own centroid (so bulk
     motion cannot mask or fake anything), then the script finds the cyclic
     shift that best aligns their vertex rings and reports how much the rms
     vertex distance IMPROVES at that shift, as a percentage of the shape's own
     bounding diagonal.  A shape in correspondence gains nothing: shifting can
     only make it worse.  A shape whose ring has slipped gains a lot - the gain
     IS the distance its vertices are out of correspondence, which is what a
     player smears across the gap between the two keyframes.

     Gain, not raw slip: a slip of 10 vertices means something quite different
     on a round fill (the silhouette rotates) than on a long thin band (points
     slide along the contour and land almost where they were).  The gain
     separates those automatically.

TWO FENCES, because those two cases really are different, and both are set where
this repository's own corpus sits rather than at an ideal:

  - A "blob" shape (compactness area/perimeter^2 >= --thin, i.e. anything not
    much thinner than a disc, whose 4*pi*compactness is 1.0) must stay under
    --max-blob.  Bandit's own pre-clipped intersect FILLS sit at 9.2% after
    being fixed; before the fix they were at 47.2%.  The 20% default sits
    between, with room either side.
  - A thin shape - in practice a pre-clipped stroke BAND - must stay under
    --max-thin.  Bandit's worst band is at 28.0% (was 51.4%), and this is a
    KNOWN GAP, not a clean pass: a clipped band's arc-length resample slides
    along its own length whenever the clip cuts it in a different place.
    Sliding along a uniform band is nearly invisible, which is why it survived
    review, and fixing it properly means building the band from a clipped
    CENTRELINE instead of polygon-clipping the band - see
    docs/moho-to-lottie-plan.md.  The 35% default fences it where it is.

One more number worth knowing before moving either fence: `SketchBone`'s worst
blob is 14.6%, on a 10-vertex shape (`ayak-sol`) at frames 43->44 - which is that
document's own confirmed BONE FLIP frame (see Skeleton.world_matrices' NOTE ON
FLIP PROPAGATION).  A shape that genuinely reverses there does move a long way
between two keyframes, and on only 10 vertices this metric is coarse, so that
14.6% is expected rather than a defect.  It is also why --max-blob is 20 and not
12: the fence has to clear a real flip as well as ordinary motion.

VALIDATED BOTH WAYS, which is the only reason to trust a fence at all: the build
from before the 2026-08 clipping fixes FAILS this check on 54 keyframe pairs,
naming `Leg_F#1`, `Leg_F 2#1`, `Arm_F#1` and `Arm_B#1` - the exact layers a human
reported as "spinning" - while the fixed build passes with the headroom above.

Usage: check_lottie_stability.py <lottie.json> [...] [--max-blob PCT]
       [--max-thin PCT] [--thin COMPACTNESS] [--verbose]
Exit status is 0 when every animated shape in every file passes.
"""

import json
import math
import sys

DEFAULT_MAX_BLOB = 20.0      # percent of the shape's own bounding diagonal
DEFAULT_MAX_THIN = 35.0
DEFAULT_THIN = 0.02          # area / perimeter^2; a disc is 1/(4*pi) = 0.0796


def _keyframes(prop):
    """[(time, bezier), ...] for an animated shape property, or [] if static."""
    k = prop.get("k")
    if not isinstance(k, list) or not k or not isinstance(k[0], dict) or "s" not in k[0]:
        return []
    out = []
    for kf in k:
        value = kf.get("s")
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, dict) and value.get("v"):
            out.append((kf.get("t", 0), value))
    return out


def _iter_shape_props(node, path=""):
    """Every `sh` element in a layer's shape tree, with a readable path."""
    if isinstance(node, dict):
        if node.get("ty") == "sh" and isinstance(node.get("ks"), dict):
            yield path + "/sh", node["ks"]
        for key in ("it", "shapes"):
            for i, child in enumerate(node.get(key) or []):
                yield from _iter_shape_props(child, f"{path}/{key}[{i}]")
    elif isinstance(node, list):
        for i, child in enumerate(node):
            yield from _iter_shape_props(child, f"{path}[{i}]")


def _centred(v):
    cx = sum(p[0] for p in v) / len(v)
    cy = sum(p[1] for p in v) / len(v)
    return [(p[0] - cx, p[1] - cy) for p in v]


def _rms(a, b, m):
    n = len(a)
    total = 0.0
    for k in range(n):
        dx = a[k][0] - b[(k + m) % n][0]
        dy = a[k][1] - b[(k + m) % n][1]
        total += dx * dx + dy * dy
    return (total / n) ** 0.5


def best_cyclic_shift(a, b, coarse_stride: int = 4):
    """The shift m minimising sum |a[k] - b[k+m]|^2 over the vertex ring.

    Coarse-to-fine, because the search is O(n^2) and one document holds tens of
    thousands of consecutive-keyframe pairs: it scans a subsampled ring first,
    then refines around the winner.  Checked against an exhaustive search on
    every pair it flagged; turns minutes into about a second.
    """
    n = len(a)
    if n < 8:
        return 0

    def cost(m, stride):
        total = 0.0
        for k in range(0, n, stride):
            dx = a[k][0] - b[(k + m) % n][0]
            dy = a[k][1] - b[(k + m) % n][1]
            total += dx * dx + dy * dy
        return total

    coarse = min(range(0, n, coarse_stride), key=lambda m: cost(m, coarse_stride))
    window = range(coarse - coarse_stride, coarse + coarse_stride + 1)
    return min(window, key=lambda m: cost(m % n, 1)) % n


def _shape_metrics(v):
    """(compactness, bounding diagonal) - compactness is area/perimeter^2, which
    is 1/(4*pi) for a disc and tends to 0 for a long thin band."""
    n = len(v)
    area = abs(sum(v[i][0] * v[(i + 1) % n][1] - v[(i + 1) % n][0] * v[i][1]
                   for i in range(n))) / 2.0
    perim = sum(math.dist(v[i], v[(i + 1) % n]) for i in range(n)) or 1.0
    xs = [p[0] for p in v]
    ys = [p[1] for p in v]
    return area / (perim * perim), (math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0)


def check_file(path, max_blob, max_thin, thin, verbose) -> int:
    doc = json.load(open(path))
    failures = 0
    pairs = 0
    worst = {"blob": (0.0, None), "thin": (0.0, None)}
    for layer in doc.get("layers") or []:
        name = layer.get("nm", "?")
        for where, prop in _iter_shape_props(layer.get("shapes") or []):
            frames = _keyframes(prop)
            if len(frames) < 2:
                continue
            counts = {len(bez["v"]) for _t, bez in frames}
            closed = {bool(bez.get("c")) for _t, bez in frames}
            if len(counts) > 1 or len(closed) > 1:
                print(f"  {name}{where}: keyframes disagree on structure - "
                      f"vertex counts {sorted(counts)}, closed {sorted(closed)}")
                failures += 1
                continue
            n = next(iter(counts))
            if n < 8:
                continue
            for i in range(1, len(frames)):
                (t0, a), (t1, b) = frames[i - 1], frames[i]
                A, B = _centred(a["v"]), _centred(b["v"])
                pairs += 1
                m = best_cyclic_shift(A, B)
                if m == 0:
                    continue
                compact, diag = _shape_metrics(b["v"])
                gain = 100.0 * (_rms(A, B, 0) - _rms(A, B, m)) / diag
                kind = "thin" if compact < thin else "blob"
                if gain > worst[kind][0]:
                    worst[kind] = (gain, f"{name}{where} frames {t0}->{t1}, "
                                         f"slip {min(m, n - m)} of {n}")
                limit = max_thin if kind == "thin" else max_blob
                if gain > limit:
                    print(f"  {name}{where}: vertices are {gain:.1f}% of the shape out of "
                          f"correspondence between frames {t0} and {t1} "
                          f"(slip {min(m, n - m)} of {n}, {kind} shape, limit {limit:.0f}%)"
                          f" - it will rotate or swim between them")
                    failures += 1
    label = path.rsplit("/", 1)[-1]
    if verbose or failures:
        for kind in ("blob", "thin"):
            g, where = worst[kind]
            print(f"  {label}: worst {kind} realignment gain {g:.1f}%"
                  + (f" at {where}" if where else ""))
        print(f"  {label}: {pairs} consecutive keyframe pair(s) compared")
    if not failures:
        print(f"OK: {label} - animated shapes stay in correspondence "
              f"(worst gain: blob {worst['blob'][0]:.1f}% of {max_blob:.0f}%, "
              f"thin {worst['thin'][0]:.1f}% of {max_thin:.0f}%)")
    return failures


def main() -> int:
    args = sys.argv[1:]

    def pop(flag, default):
        if flag in args:
            i = args.index(flag)
            value = float(args[i + 1])
            del args[i:i + 2]
            return value
        return default

    max_blob = pop("--max-blob", DEFAULT_MAX_BLOB)
    max_thin = pop("--max-thin", DEFAULT_MAX_THIN)
    thin = pop("--thin", DEFAULT_THIN)
    verbose = "--verbose" in args
    paths = [a for a in args if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 2
    failures = sum(check_file(p, max_blob, max_thin, thin, verbose) for p in paths)
    if failures:
        print(f"\nFAIL: {failures} keyframe pair(s) would not interpolate cleanly")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
