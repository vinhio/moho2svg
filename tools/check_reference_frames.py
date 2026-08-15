"""Check this exporter's geometry against frames MOHO ITSELF exported.

Everything else in this repository is checked against its own output - the
tracked SVGs under `out/svg/ori/` are this tool's own work, and
`check_lottie_geometry`
compares the Lottie writer against the same pipeline that fed it.  This script
is the only one that compares against an outside authority, and it has three
reference sets, all exported by Moho 14.4 and all kept under `moho/track/`:

  - `moho/track/Bandit/svg/`   103 frames, the document's whole 25-127 range.
                               Groups only, so it can address three of them.
  - `moho/track/SketchBone/new/`  120 frames of `SketchBone.mohoproj`
                               (format 1045).  Every LAYER is its own `<g id>`
                               here, so individual meshes can be addressed.
  - `moho/track/BoneDynamics/` 29 frames, and the only document that can
                               test bone dynamics.  The exporter FAILS it -
                               see the CHECKS table.

WHAT IT MEASURES

Per named group, the displacement of its bounding-box centre from the first
sampled frame, compared against the same displacement on our side.  Comparing
displacement rather than absolute position ignores any constant offset between
the two renderers and measures whether the MOTION agrees, which is the part
that channel, transform and rig bugs break.

Two details matter and both were found the hard way:

  - Use the bounding-box centre, not the centroid.  Moho splits one shape into
    several paths (fill and outline separately, and a brush-textured stroke
    into many), so the two sides weight a centroid differently even when the
    geometry agrees exactly.  A bbox centre is immune to that.
  - Take only on-curve points.  Moho writes `M x y` then `C x1 y1 x2 y2 x y`,
    so every third point after the first is on-curve.  Our own builder returns
    Lottie-style beziers whose `i`/`o` are RELATIVE to `v`; mixing those into
    a position silently divides it by three.

WHAT IT CAUGHT

Written after three defects that all passed every other check in the repo:

  - Channel cycling read as a value replay instead of an accumulation.  The
    character walked on the spot; travel error 1026 px mean.
  - A phantom Smart Bone: a dial's candidate actions were not restricted to
    the dial's own name, so Bandit's plain `Walk` animation was picked as a
    dial.  Muzzle travel error 144 px mean.
  - Both fixed, the same measurement reads 0.73 px mean.

TOLERANCES sit a little above the measured residual, not at it, so an ordinary
rounding change does not fail the build but a real regression does.

`Tail` is deliberately loose, and it is loose for ONE reason rather than the
two it first appeared to be: the bone dynamics this exporter cannot reproduce
(see Skeleton.dynamic_angles).  `Tip` is bound to the document's only two
bones with dynamics on, and `TailBase` - which has no binding at all - picks
the same motion up through its all-bone blend.

That both tail layers share one cause is measured, not assumed.  In Moho's own
render the tail's vertical bob is a copy of the body's, lagged 4 frames
(cross-correlation 0.93 there against -0.91 at zero lag) and amplified down
the chain: 6.7 px standard deviation at the muzzle, 10.0 at the tail base,
15.1 at the tip.  Lag plus gain is a resonant oscillator.  Binding was ruled
out separately - all 28 rigid bindings, 5 subsets and all 4 falloffs leave the
vertical error within about 2 px of each other.

So `Tail` failing means the dynamics gap moved.  The tight checks are the ones
that guard the pipeline.

Exit code 0 if every group is inside tolerance, 1 otherwise.  A missing
reference directory is skipped, not failed - both are gitignored.

WINDING CHECKS (`run_winding_check`, `WINDING_CHECKS`) are a second,
independent measurement added after the bbox-centre check above proved too
weak to catch a real regression: `Skeleton.world_matrices` briefly lost the
ability to propagate a bone's `flip_h`/`flip_v` mirror to its own children
(see that method's "NOTE ON FLIP PROPAGATION"), which flips a shape's
winding direction while barely moving its bounding box - `ayak-sol`'s width
was 43.4px broken vs 41.9px correct at the exact frame that broke, a gap
`run_check`'s tolerances would never catch. Winding (the sign of the
shoelace formula, `signed_area`) catches it directly: every sampled frame of
`ayak-sol` mismatched sign in the broken build, none did after the fix. Add
a layer to `WINDING_CHECKS` whenever a bone's `flip_h`/`flip_v` is a real,
keyframed change - that is the one signal this check exists for.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moho2svg import (Channel, Exporter, build_path_bezier, load_document,
                      walk_render_tree)

NUMBER = re.compile(r'-?\d+\.?\d*(?:[eE][-+]?\d+)?')
TOKEN = re.compile(r'<g\b([^>]*)>|</g>|<path\b([^>]*)>')
GROUP_ID = re.compile(r'\bid="([^"]*)"')
PATH_D = re.compile(r'\bd="([^"]+)"')

# (project, reference glob, frames, [(group, our layer names, dx limits, dy limits)])
CHECKS = [
    ('moho/Bandit.mohoproj', 'moho/track/Bandit/svg/Bandit_%05d.svg', range(25, 128), [
        ('Muzzle', {'Muzzle', 'Mouth Stroke', 'Whiskers'}, (3.0, 10.0), (6.0, 12.0)),
        ('BellyTexture', {'Body', 'BlueSpot', 'YellowSpot', 'Back_Texture',
                          'HairTexture'}, (3.0, 10.0), (6.0, 12.0)),
        ('Tail', {'TailBase', 'Tip'}, (10.0, 25.0), (35.0, 75.0)),
    ]),
    # THESE TOLERANCES ARE A FENCE, NOT AN ACCEPTANCE CRITERION.  This is the
    # one document that can test bone dynamics, and the model FAILS it: the
    # ears sit ~55 px out with dynamics off and get worse with it on (see
    # Skeleton.dynamic_angles).  The numbers below are where the exporter
    # actually is, recorded so the gap cannot silently widen; they are not a
    # claim that it is close.
    ('moho/BoneDynamics.animeproj', 'moho/track/BoneDynamics/BoneDynamics_%05d.svg',
     range(1, 30), [
        ('Right Ear', {'Right Ear'}, (30.0, 65.0), (58.0, 100.0)),
        ('Left Ear', {'Left Ear'}, (30.0, 85.0), (58.0, 100.0)),
        ('Body', {'Body'}, (15.0, 25.0), (32.0, 46.0)),
        ('Tail', {'Tail'}, (8.0, 20.0), (10.0, 30.0)),
    ]),
    ('moho/SketchBone.mohoproj', 'moho/track/SketchBone/new/SketchBone_%05d.svg',
     range(1, 121, 10), [
        ('kafasi', {'kafasi'}, (5.0, 14.0), (6.0, 16.0)),
        ('ayasi', {'ayasi'}, (4.0, 10.0), (4.0, 10.0)),
        ('kuyruk', {'kuyruk'}, (4.0, 8.0), (5.0, 8.0)),
        ('kulak-sol', {'kulak-sol'}, (6.0, 16.0), (9.0, 26.0)),
        ('goz-bebegi', {'goz-bebegi'}, (6.0, 12.0), (6.0, 14.0)),
        ('ayak-sag', {'ayak-sag'}, (2.0, 4.0), (2.0, 6.0)),
        ('cizgiler-sag', {'cizgiler-sag'}, (10.0, 28.0), (6.0, 15.0)),
    ]),
]


def reference_groups(path):
    """{group id: [on-curve points]} for every <g id> in one Moho SVG.

    Points land in the INNERMOST enclosing group, which is what makes the
    per-layer reference addressable; Bandit's export only nests groups, so
    there the innermost group is the GroupLayer.
    """
    svg = open(path).read()
    stack, out = [], {}
    for match in TOKEN.finditer(svg):
        token = match.group(0)
        if token.startswith('</g'):
            if stack:
                stack.pop()
        elif token.startswith('<g'):
            found = GROUP_ID.search(match.group(1))
            # Moho writes spaces in a layer name as underscores in the id.
            stack.append((found.group(1) if found else '').replace('_', ' '))
        else:
            data = PATH_D.search(match.group(2) or '')
            if not data:
                continue
            flat = [float(n) for n in NUMBER.findall(data.group(1))]
            pairs = list(zip(flat[0::2], flat[1::2]))
            if pairs and stack:
                out.setdefault(stack[-1], []).extend([pairs[0]] + pairs[3::3])
    return out


def our_layers(exporter, frame):
    """{layer name: [on-curve points]} at `frame`, straight from the pipeline."""
    out = {}
    for item in walk_render_tree(exporter, float(frame)):
        if item.event != 'mesh':
            continue
        points = []
        for shape in item.layer.mesh.shapes:
            if not shape.edges:
                continue
            for bezier in build_path_bezier(item.geometries, shape.edges,
                                            item.to_px) or []:
                points += [tuple(v) for v in bezier.get('v', [])]
        if points:
            out.setdefault(item.layer.name, []).extend(points)
    return out


def bbox_centre(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def run_check(project, pattern, frames, groups):
    frames = list(frames)
    if not os.path.isfile(pattern % frames[0]):
        print('skipped %s: %s not present (gitignored reference frames)\n'
              % (os.path.basename(project), os.path.dirname(pattern)))
        return []
    Channel.reset_cache()
    exporter = Exporter(load_document(project))
    errors = {name: [] for name, _, _, _ in groups}
    base = None
    for frame in frames:
        reference = reference_groups(pattern % frame)
        ours = our_layers(exporter, frame)
        current = {}
        for name, layers, _, _ in groups:
            if name not in reference:
                continue
            mine = [p for layer, pts in ours.items() if layer in layers for p in pts]
            if not mine:
                continue
            current[name] = (bbox_centre(reference[name]), bbox_centre(mine))
        if base is None:
            base = current
        for name, (ref, mine) in current.items():
            errors[name].append(
                (abs((ref[0] - base[name][0][0]) - (mine[0] - base[name][1][0])),
                 abs((ref[1] - base[name][0][1]) - (mine[1] - base[name][1][1]))))

    print('%s vs %d frames Moho exported itself' % (os.path.basename(project),
                                                     len(frames)))
    print('%-16s %9s %9s %9s %9s' % ('group', 'mean dx', 'max dx',
                                      'mean dy', 'max dy'))
    failures = []
    for name, _, dx_limit, dy_limit in groups:
        rows = errors[name]
        if not rows:
            failures.append('%s: never matched in the reference' % name)
            continue
        dx = [a for a, _ in rows]
        dy = [b for _, b in rows]
        print('%-16s %9.2f %9.2f %9.2f %9.2f'
              % (name, sum(dx) / len(dx), max(dx), sum(dy) / len(dy), max(dy)))
        for label, values, (mean_limit, max_limit) in (
                ('dx', dx, dx_limit), ('dy', dy, dy_limit)):
            mean_value, worst = sum(values) / len(values), max(values)
            if mean_value > mean_limit or worst > max_limit:
                failures.append(
                    '%s %s %s: mean %.2f px (limit %.2f), max %.2f px (limit %.2f)'
                    % (os.path.basename(project), name, label, mean_value,
                       mean_limit, worst, max_limit))
    print()
    return failures


def reference_group_paths(path, name):
    """[[on-curve points], ...] - one list PER `<path>` inside the innermost
    `<g id=name>` of one Moho SVG, kept separate rather than merged.

    `reference_groups` above flattens every path in a group into one point
    list, which is fine for a bounding-box centre but destroys the very
    thing `run_winding_check` needs: a shape's own signed area, and
    therefore its winding direction.
    """
    svg = open(path).read()
    stack, out = [], []
    for match in TOKEN.finditer(svg):
        token = match.group(0)
        if token.startswith('</g'):
            if stack:
                stack.pop()
        elif token.startswith('<g'):
            found = GROUP_ID.search(match.group(1))
            stack.append((found.group(1) if found else '').replace('_', ' '))
        else:
            data = PATH_D.search(match.group(2) or '')
            if not data or not stack or stack[-1] != name:
                continue
            flat = [float(n) for n in NUMBER.findall(data.group(1))]
            pairs = list(zip(flat[0::2], flat[1::2]))
            if pairs:
                out.append([pairs[0]] + pairs[3::3])
    return out


def our_layer_paths(exporter, frame, name):
    """[[on-curve points], ...] for ONE layer, one list per shape, straight
    from the pipeline - the per-shape counterpart of `our_layers`."""
    out = []
    for item in walk_render_tree(exporter, float(frame)):
        if item.event != 'mesh' or item.layer.name != name:
            continue
        for shape in item.layer.mesh.shapes:
            if not shape.edges:
                continue
            for bezier in build_path_bezier(item.geometries, shape.edges,
                                            item.to_px) or []:
                points = [tuple(p) for p in bezier.get('v', [])]
                if points:
                    out.append(points)
    return out


def signed_area(polygon):
    """The shoelace formula.  Its MAGNITUDE is the enclosed area; its SIGN is
    the winding direction, and that sign is exactly what a `flip_h`/`flip_v`
    mirror reverses.  See `run_winding_check`."""
    total = 0.0
    for i in range(len(polygon)):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % len(polygon)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


# (project, reference pattern, frames to sample, [layer names to check])
#
# A WINDING check, not a position check: it asks only "does this layer's
# winding direction (see signed_area) agree with Moho's own render", which
# `run_check`'s bounding-box-centre-displacement metric is a WEAK detector
# for - a mirrored shape can keep almost the same bounding box while its
# outline winds the wrong way.  Add a layer here whenever a bone's
# flip_h/flip_v channel is a real, keyframed change (not just a stray
# default), since that is precisely the failure mode this check exists to
# catch - see moho2svg.py's `Skeleton.world_matrices`, "NOTE ON FLIP
# PROPAGATION" for the regression this was written against.
WINDING_CHECKS = [
    ('moho/SketchBone.mohoproj', 'moho/track/SketchBone/new/SketchBone_%05d.svg',
     [1, 30, 44, 45, 50, 60, 90, 120], ['ayak-sol']),
]


def run_winding_check(project, pattern, frames, layers):
    if not os.path.isfile(pattern % frames[0]):
        print('skipped %s winding check: %s not present\n'
              % (os.path.basename(project), os.path.dirname(pattern)))
        return []
    Channel.reset_cache()
    exporter = Exporter(load_document(project))
    failures = []
    print('%s winding check (a mirrored bone losing its own mirror downstream)'
          % os.path.basename(project))
    for name in layers:
        mismatches = []
        for frame in frames:
            ref_area = sum(signed_area(p)
                           for p in reference_group_paths(pattern % frame, name))
            our_area = sum(signed_area(p) for p in our_layer_paths(exporter, frame, name))
            if (ref_area < 0) != (our_area < 0):
                mismatches.append(frame)
        status = 'OK' if not mismatches else ('MISMATCH at frames %s' % mismatches)
        print('  %-16s %s' % (name, status))
        if mismatches:
            failures.append('%s winding %s: sign disagrees with Moho at frames %s'
                             % (os.path.basename(project), name, mismatches))
    print()
    return failures


def main() -> int:
    failures = []
    for project, pattern, frames, groups in CHECKS:
        failures += run_check(project, pattern, frames, groups)
    for project, pattern, frames, layers in WINDING_CHECKS:
        failures += run_winding_check(project, pattern, frames, layers)
    if failures:
        print('FAIL')
        for failure in failures:
            print('  ' + failure)
        return 1
    print("OK: every group tracks Moho's own render within tolerance")
    return 0


if __name__ == '__main__':
    sys.exit(main())
