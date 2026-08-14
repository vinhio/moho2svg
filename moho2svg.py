#!/usr/bin/env python3
"""
moho2svg - Export Moho vector artwork (.mohoproj / .animeproj) to SVG.

    python3 moho2svg.py Project.mohoproj --list
    python3 moho2svg.py Project.mohoproj --layer Arm_B --out Arm_B.svg
    python3 moho2svg.py Project.mohoproj --all --outdir svg/          # one file per layer
    python3 moho2svg.py Project.mohoproj --combined Bandit.svg        # one layered file

Run with no export flag (or --help) to see every option.

--------------------------------------------------------------------------------
WHY THIS FILE IS LONG: A REVERSE-ENGINEERING NOTEBOOK, NOT JUST A CONVERTER
--------------------------------------------------------------------------------
Moho's project format (.mohoproj / .animeproj) is JSON, but it is *undocumented*
JSON: field names are stable across versions, but their meaning, units, and the
formulas that turn them into pixels were worked out here by empirically comparing
this exporter's output against SVG files Moho itself exported (its "File > Export
Animation" feature), for several different rigs and two Moho versions (14.3 and
14.4). Every non-obvious constant and formula below is annotated with *how* it was
derived and *what evidence* supports it, specifically so a reimplementation (e.g.
in Go) can trust the numbers without having access to Moho or to that process.

Reliability varies by section - some formulas are exact matches confirmed to
±0.02 degrees / whole pixels across hundreds of samples; others (noted "HEURISTIC")
are the best fit found against a handful of examples and may not generalize.

--------------------------------------------------------------------------------
THE MOHO DOCUMENT MODEL, IN BRIEF
--------------------------------------------------------------------------------
A project is one JSON object.  The parts this tool cares about:

  project_data.width / .height   Canvas size in pixels (e.g. 1920x1080).
  styles                         A document-wide list of *named* brush/line
                                  styles.  A shape can inherit its colours and
                                  line width from one of these instead of (or on
                                  top of) its own values - see ResolvedStyle.
  layers                         A tree.  Each layer has a "type":
                                    MeshLayer    vector artwork (points/curves/
                                                 shapes) - the only thing that
                                                 actually draws pixels.
                                    BoneLayer    a skeleton (list of bones) plus
                                                 child layers deformed by it.
                                    GroupLayer   children with no skeleton.
                                    SwitchLayer  children are alternatives; only
                                                 one is shown at a time.
                                    TextLayer    a caption; Moho keeps its
                                                 rasterised-to-vector glyphs in a
                                                 nested "mesh_layer" field, which
                                                 this tool exposes as a normal
                                                 MeshLayer child (see
                                                 Layer._build).
                                    PatchLayer   carries no mesh of its own -
                                                 reuses another layer's mesh,
                                                 redrawn at this layer's spot in
                                                 the draw order - see PATCH
                                                 LAYERS below.

  animated value ("channel")     Almost every numeric/colour/string property in
                                  Moho is stored the same way:
                                    {"when": [f0, f1, ...],      keyframe numbers
                                     "val":  [v0, v1, ...],      one value per key
                                     "interp": [...],            (unused here -
                                                                   only linear
                                                                   interpolation
                                                                   is implemented)
                                     "actions": [{"name": ..., "pose": <channel>}]}
                                  See Channel and "SMART BONES" below for what
                                  "actions" means.  A field that is never animated
                                  is sometimes stored as a bare scalar/dict instead
                                  of this structure; Channel.of() normalises both.

--------------------------------------------------------------------------------
COORDINATES
--------------------------------------------------------------------------------
Points, translations, bone positions etc. are stored in a document-space unit
where **2 units span the canvas height** - i.e. y=+1 is the top edge, y=-1 the
bottom edge, regardless of the pixel resolution.  So:

    pixel_x = moho_x * (height / 2) + width / 2
    pixel_y = height / 2 - moho_y * (height / 2)        (y is flipped)

This is implemented once, in Exporter._to_pixels.

--------------------------------------------------------------------------------
BEZIER CURVES: WHAT MOHO STORES VS. WHAT SVG NEEDS
--------------------------------------------------------------------------------
An SVG cubic Bezier needs two explicit control points per segment.  Moho does not
store control points - each curve point instead stores:

    smoothness    curvature, 0 = sharp corner (both handles collapse onto the
                  point), typically ~0.2-0.7 for a rounded point
    weight_in/out how far the handle reaches towards the neighbour, as a
                  fraction of the distance to that neighbour
    offset_in/out a small rotation (radians) applied to the handle direction,
                  used for asymmetric curves

Reconstructing the control point (BezierReconstructor) requires two formulas:

  1. Handle length = distance-to-that-neighbour * smoothness * weight.
     Confirmed by regression against 209 handles in Moho's own SVG export:
     the ratio handle_length / (neighbour_distance * smoothness * weight) had
     a median of 1.0000 with p10/p90 also 1.000 - i.e. exact.

  2. Handle *direction* is the surprising part.  It is NOT simply
     normalize(next_point - prev_point) (a natural guess, and the formula
     given by a public Moho scripting snippet) - that is off by a median of
     3.4 degrees, sometimes tens of degrees.  The direction that matches is a
     blend of the two unit chord vectors (P-prev) and (next-P), each weighted
     by the *other* segment's length raised to a small power:

         weight_towards_prev_side = |next - P] ** BIAS
         weight_towards_next_side = |P - prev| ** BIAS
         direction = normalize(unit(P-prev) * weight_towards_next_side
                              + unit(next-P) * weight_towards_prev_side)

     BIAS = 0.19 was found by a 1D search over [0.10, 0.44] minimising the mean
     angular error against those same 209 reference handles; at 0.19 the median
     error is 0.02 degrees (i.e. exact to the 3-decimal precision Moho itself
     writes) and the mean is 0.09 degrees.  This is almost certainly a
     Catmull-Rom-style "centripetal/chord-length" tangent (whose textbook
     exponent is 0.5 on the *same*-side length, which is a different but related
     formula) that Moho's actual implementation approximates or truncates
     somehow; 0.19 is an empirical fit, not a derived closed form.  It has only
     been validated on non-degenerate interior points (both neighbours farther
     than a few pixels away); see BezierReconstructor for the degenerate cases.

--------------------------------------------------------------------------------
SHAPES, EDGES, AND WHY A "DIRECTION FLAG" IN THE FILE IS NOT TRUSTWORTHY
--------------------------------------------------------------------------------
A shape's outline is a list of *edges*: (curve_index, segment_index, flag), i.e.
"segment `segment_index` of curve `curve_index`, walked forwards or backwards".
Two things about this list turned out not to hold in real files:

  - `flag` is not reliably a direction bit: shapes exist whose segment order is
    strictly descending (e.g. 13,12,11,...,7) with `flag` 0 throughout, and the
    direction that actually makes the outline continuous is implied by *which
    endpoint touches the previous edge*, not by the flag.
  - The edge list is not always given as a walk: one real umbrella-panel shape
    lists a single curve's segments as 3, 0, 1, 2 - consecutive in the outline,
    but not in list order.

So edges are not "the direction to draw them in" but simply "the unordered set of
segments belonging to this shape".  PathTracer rebuilds the actual walk order by
treating every segment as an edge in an undirected graph (keyed by rounded
endpoint coordinates) and tracing connected loops/chains - see PathTracer.trace.

--------------------------------------------------------------------------------
FILL RULE, DRAW ORDER, AND WHY STROKE PATHS ARE NEVER CLOSED
--------------------------------------------------------------------------------
  - fill-rule is always evenodd (confirmed: Moho's SVG root sets
    style="fill-rule:evenodd" once for the whole document).
  - Shape draw order (back to front) is simply the order shapes already appear
    in mesh.shapes.  There is a separate `shape_order` string field that looks
    like a natural place to find this, but it is only an ascending id registry,
    not a z-order; trusting it draws almost everything back-to-front.
  - A *filled* path is closed with "Z" when its last point coincides with its
    first (this also lets fills built from several stitched curves work).
  - A *stroked* path is never closed, even when the outline is a closed loop:
    checked across 445 stroke paths in two of Moho's own SVG exports, zero of
    them contain "Z".  This matters visually on a thick stroke around a small
    closed shape: relying on round line-joins/caps to meet at the seam (as an
    unclosed path does) fills the middle solidly, whereas an explicit Z leaves a
    visible hole down the seam because the two ends overlap instead of meeting.

--------------------------------------------------------------------------------
STROKE WIDTH
--------------------------------------------------------------------------------
Two independent quantities both scale a stroke, and neither is expressed in
pixels directly:

  line_width    a per-shape/style channel, one of a handful of quantised values
                per document (e.g. 0.0028, 0.0035, 0.0042 for a 1080-tall canvas).
  point width   a per-*point* channel, normally 1.0, but can vary continuously
                (a point can be "thin" or "thick") - see TAPERED STROKES below.

The pixel width is:

    stroke_px = line_width * point_width * canvas_height * layer_chain_scale

`layer_chain_scale` is the uniform-scale component of the accumulated layer
transform (product of every ancestor's scale, EXCLUDING any bone deformation -
confirmed separately: measuring through deformed points on a walk cycle inflated
the apparent scale by ~11%, i.e. bone deformation must NOT be included).

This was derived from a 720-tall document where several shapes had a non-1.0
point width: the ratio (exported stroke-width px) / (line_width * point_width)
converged on 720 (=canvas height) with p10/median/p90 all equal.  A *second*,
1080-tall document with all point widths equal to 1.0 could not by itself
distinguish "* height" from "* height * 4/3" (both round to the same whole
pixels after Moho's own rounding) - the 720-tall document is what broke the tie.

Note Moho's own SVG *exporter* rounds this to the nearest integer pixel before
writing it (a computed 4.5 comes out as "5"); this tool does not round, to stay
exact for further vector editing.  `RenderSettings.stroke_width_scale` is a
user-facing fudge *on top of* this formula (default 2.0, folded together with an
internal /2 so that the default reproduces the base formula unchanged - see
Exporter._stroke_width_px) for cases where a document's own calibration is off.

--------------------------------------------------------------------------------
TAPERED STROKES (VARYING POINT WIDTH)
--------------------------------------------------------------------------------
SVG cannot vary a <path> stroke's width along its length.  Where a shape's
outline points do not all share one width (fur, whiskers, tapered claws), Moho's
own exporter does not use <path stroke-width>: it walks the stroke and emits the
literal filled outline instead (visible as e.g. 90 tiny filled paths for one bushy
tail, versus a handful of <path stroke> elements for uniform-width outlines).
TaperedStrokeOutliner reproduces this: sample each segment, offset left/right by
half the locally-interpolated width along the estimated normal, and fill the
resulting ribbon.  Where a point's width reaches 0 the ribbon pinches to nothing,
which is how fur/claw tips vanish to a point.  A closed loop is emitted as two
counter-wound rings combined with fill-rule=evenodd (drawing it as one continuous
outline would self-overlap at the seam).

A tapered outline that ALSO carries a resolvable brush style (see BRUSH
STROKES) does not go through TaperedStrokeOutliner at all - brush takes
priority, since a flat filled ribbon would silently drop the texture, and
real hand-drawn linework very often is both tapered and brush-styled at once
(confirmed on the SketchBone rig: e.g. "cizgiler"'s scarf-pattern strokes are
5/8 tapered, and every one of them is also styled with a real Moho brush).
BrushStampOutliner scales each dab's own diameter by the same locally-
interpolated width instead, so a tapered+brushed shape still visibly tapers,
just via varying dab size along the path rather than a continuous ribbon
edge.

--------------------------------------------------------------------------------
BRUSH STROKES (TEXTURED/DAB LINE STYLES)
--------------------------------------------------------------------------------
A named style's line can be a textured "brush" (e.g. "Wet Ink", "CK Ink DIFF
SMASHER") instead of a plain, uniform-width line: Moho stamps a small greyscale
texture image repeatedly along the path (jittered in rotation, spaced as a
fraction of its own size) rather than stroking it - visible in Moho itself as a
soft, grainy, hand-painted look (e.g. a cheek "blush" or an ink-smear shadow),
which a plain SVG <path stroke> cannot reproduce (it is always a hard-edged,
perfectly uniform band).

This tool approximates it, but ONLY for a style whose `brush_name` can be
resolved to a brush asset in `--brush-dir` (default `styles/Brushes/` - not
shipped in this repo; `make styles.brushes` symlinks it straight to Moho's
own installed brush folder, e.g. `.../Moho.app/Contents/Resources/Support/
Common/Brushes/`, so every brush Moho itself ships is available with no
copying).  Any brush that cannot be resolved - which, with no
`styles/Brushes/` at all, is every brush - falls back to the plain uniform
stroke exactly as before this existed, so nothing regresses for
documents/styles nobody has supplied textures for.

A brush asset lives in the brush directory in one of three shapes:

  - a single PNG named exactly after the style's brush_name
    ("Brush502.png");
  - a multi-frame brush: a *folder* named after the brush, full of PNG
    frames, with a sibling "<name>.mohobrush" file (a ZIP containing
    brush.json) that records the library defaults - randomOrder /
    randomInterval, i.e. whether each dab picks a random frame or cycles
    through the folder in file order;
  - a preset image stored one folder deep in the brush directory
    ("Brush567_0_20_50.png" exists only as Brush005/Brush567_0_20_50.png)
    - found by a recursive search.

Brush names with a trailing "_N_N_..." numeric suffix are older Moho
versions' way of baking preset parameters into the name: the second and
third numbers match the style's own brush_jitter in degrees and
brush_spacing as a percent (confirmed across every suffixed style in the
reference documents, e.g. Brush567_0_20_50.png = jitter 20 deg, spacing
50%); the first differs by brush family - it is the align flag for the
Brush5xx presets but something else (possibly a size scale: "CK Ink
Natural_2..." has align=true) for the CK Ink pack.  Rendering does not
decode the suffix: the style's own brush_align/brush_jitter/brush_spacing
fields are the effective settings, and the suffix is used only to FIND the
asset - if no file matches the full name, trailing numeric segments are
stripped one at a time until a file/folder with the base name is found
("CK Ink Natural_2_1_0_0_0_0_0_0_0" -> the folder "CK Ink Natural").
See Exporter._resolve_brush_asset for the exact resolution order.

BrushStampOutliner samples the traced path at even arc-length intervals and
emits one dab per sample: each dab's diameter is a BASE (the ordinary
computed stroke width at point_width=1.0, i.e. ignoring this shape's own
per-point width channel) scaled by the width channel interpolated at that
dab's position - the same value TaperedStrokeOutliner uses to taper its
ribbon (see TAPERED STROKES for why this, not TaperedStrokeOutliner, handles
a tapered+brushed shape).  Spacing (`brush_spacing` * dab diameter) is
recomputed from each dab's own *local* diameter, not the BASE - a point-width
channel is sometimes used to swing a stroke's width by an order of
magnitude on purpose (a soft shadow drawn as one thick brushed line rather
than a filled shape - confirmed on the SketchBone rig's "golge" shadow
strokes, ~12x-19x), and spacing computed once from the unscaled base would
leave huge dabs spaced as if they were tiny, overlapping dozens deep and
rendering far denser than Moho's own output.  A multi-frame brush stamps one
frame per dab: randomOrder=true (the majority of Moho's shipped brushes)
draws a uniform-random frame each dab, from the same per-shape seeded RNG as
the rotation jitter; randomOrder=false cycles through the folder's frames in
sorted file-name order, advancing one frame every randomInterval dabs.

Each dab needs to end up as a *coloured* stamp of the (greyscale/alpha)
brush texture - the resolved line_color/opacity, i.e. the tint Moho itself
applies when a style's `brush_tint` is true (the only case implemented - a
brush with brush_tint false, meaning "use the texture's own multi-colour
pixels as-is", is not attempted here and simply falls back to a plain
stroke too).  There are two ways to render that tint, and this tool picks
whichever is available at import time (see the `try: from PIL import
Image...` near the top of this file):

  - PREFERRED, when Pillow is installed: Exporter._bake_tinted_frame
    pre-renders each (brush, frame, colour, alpha) combination actually used
    into a plain solid-colour PNG ONCE (ink density - the same dark-pixel-
    is-opaque inversion described below, whichever render path computes it -
    becomes that PNG's own alpha channel), registered once as an `<image>`
    in `<defs>` (Exporter._brush_tinted_ref).  Every dab is then just a
    `<use href="#tint_N" transform="...">` of that already-coloured image -
    no per-dab compositing beyond an ordinary scaled/rotated image blit.
  - FALLBACK, when Pillow is not installed (this tool has zero required
    dependencies; Pillow is optional and only for this faster path): each
    dab is a `<g transform="...">` containing a colour-filled rect, MASKED
    by the brush texture - the texture's own RGB is irrelevant
    (Exporter._brush_mask_refs inverts it with a shared <feColorMatrix>
    filter so the texture's dark "ink" pixels become the *visible* part of
    an SVG luminance mask, and light/transparent background pixels stay
    invisible), so any texture works as a stamp regardless of whether it
    happens to be a dark blob on white (Brush502.png) or a dark splatter on
    transparent (CK Ink DIFF SMASHER.png).

Both paths produce the same dab positions/rotations/sizes (BrushStampOutliner
does not know or care which one will render its output) and are visually
equivalent - see the performance paragraph below for why the Pillow path is
strongly preferred whenever it is available.

Rotation per dab is `(tangent angle if brush_align else 0) + a uniform-random
value in [-brush_jitter/2, +brush_jitter/2]`, seeded deterministically per
shape (so re-running the exporter on the same document reproduces the same
jitter instead of a different random result every time) rather than from
Moho's own actual per-dab randomisation, which is not recoverable from the
saved document.  `brush_angle_drift`, `brush_randomize` (per-dab size
variance), `brush_merged_alpha` (whether overlapping dabs should cap combined
opacity instead of compounding it) and `brush_rand_order` are read from the
style but not implemented - overlapping semi-transparent dabs simply compound
via ordinary SVG alpha blending in file order, which is the `brush_merged_alpha
= false` behaviour by construction, but coincidental for the other three.
There is no reference Moho SVG export of a brushed stroke to calibrate dab
size/density against (Moho's own SVG exporter does not reproduce brush
texture either, as far as this tool's development has observed - see KNOWN
GAPS), so this is a best-effort approximation, not a confirmed-exact formula
like the rest of this file aims for.

A document whose linework is broadly brush-styled can produce tens of
thousands of dabs (confirmed: 17,822 on the SketchBone rig).  The FALLBACK
path's `mask`+`feColorMatrix` pairing is expensive for a viewer to render (a
spec-compliant renderer allocates and rasterises an offscreen buffer per
masked element) - unlike file size, THIS is what actually made a heavily-
brushed export slow or unopenable in some viewers even though `moho2svg.py`
itself still exported it in under a second.  Switching to the PREFERRED
(Pillow) path removes that cost - confirmed at the same 600px preview width
with rsvg-convert, mask/filter vs pre-tinted `<use>`:

    SketchBone   15.97s -> 2.46s  (3.89 -> 2.86 MB, both dab count and
                                    file size happen to drop here)
    AddBone      25.83s -> 8.90s  (6.16 -> 9.00 MB - MORE bytes despite
                                    being much faster to render: many
                                    distinct (brush, colour) combinations
                                    baked at their source texture's native
                                    resolution, which for this rig is
                                    sometimes as large as 512x512, outweigh
                                    the mask/filter defs they replace)
    WhatIsBone    6.13s -> 1.84s  (4.11 -> 9.62 MB, same reason as AddBone)

i.e. the Pillow path is not a strict improvement on file size, only on
render time - which is what was actually reported as broken.  A THIRD path,
`--brush-raster` (Exporter._raster_brush_shape, also Pillow-only), fixes
that too: it composites an entire shape's dabs into ONE raster <image> at
export time instead of one <use> per dab, so file size scales with shape
count rather than with (brush, colour) combinations sourced from a
potentially large native texture:

    SketchBone   <use>: 2.86 MB / 2.46s   -> raster(1x): 0.93 MB / 0.15s
    AddBone      <use>: 9.00 MB / 8.90s   -> raster(1x): 0.44 MB / 0.07s
    WhatIsBone   <use>: 9.62 MB / 1.84s   -> raster(1x): 0.32 MB / 0.09s

This is the most aggressive option: that stroke is no longer vector at all
(not rescalable/editable as a path afterwards), and - confirmed on the
SketchBone rig's "golge" shadow strokes specifically (very fine, sparse,
high-contrast detail under ~30-50x dab overlap) - resampling each dab
(resize + rotate) into one shared canvas at 1:1 (`brush_raster_supersample`
= 1.0) visibly softens/blurs fine texture that the per-dab <use> path
preserves; a softer texture like "yanak"'s cheek blush showed no visible
difference either way.  RenderSettings.brush_raster_supersample (default
2.0, i.e. `--brush-raster-supersample 2`) substantially recovers this - the
"@2x asset" trick: composite at Nx the shape's own pixel size, declare it
at 1x size in the emitted <image>, so a downsampling viewer has more source
detail to work with.  Confirmed on "golge": 1x reads as a near-flat blob,
2x recovers a visible (if still slightly softened) grainy edge, 3x reads as
close to the per-dab <use> version's wispy strands - at a file-size cost
that scales roughly with N^2 (SketchBone: 0.93/2.74/5.42 MB at N=1/2/3) while
render time barely moves (0.13s/0.18s/0.24s) since it is still one image
blit per shape regardless of N.  2.0 is the default because it recovers
most of the visible softening while staying smaller AND much faster than
the per-dab <use> path on every document tested here; past N~3 the file
size approaches or exceeds that path's own, at which point <use> (no fine-
detail loss at all) is arguably the better choice instead.  Downscaling a
source texture before baking into either Pillow path (dabs are typically
drawn far smaller than a 512x512 source) would recover the `<use>` path's
file-size regression too but is not implemented.

Two further settings manage dab volume itself, independent of which render
path is active: `--brush-spacing-mul` (RenderSettings.brush_spacing_mul,
plumbed into BrushStampOutliner.build as `spacing_scale`) uniformly
multiplies dab spacing to thin out density (confirmed on the fallback path:
mul=4 cut SketchBone to 4,502 dabs, ~8s render, vs 17,822 dabs/~31s at the
default 1.0 at 900px width, with byte-identical output at 1.0 to before this
knob existed); passing `--brush-dir ""` (or `make gen-fast`) disables brush
stamping entirely, which is nearly free for any viewer on any of the three
render paths since it falls back to the exact same plain-stroke/
TaperedStrokeOutliner path used when no brush asset resolves at all.  See
docs/moho-exporting-svg.md § 7 for the full write-up.

--------------------------------------------------------------------------------
BOOLEAN SHAPE COMBINATIONS (combo_mode)
--------------------------------------------------------------------------------
A shape's `combo_mode` says how it combines with the shape(s) drawn immediately
before it in the same layer:

    0   normal - starts a new independent shape ("boolean group")
    1   union - merged into the current group; the shared boundary between this
        shape and the rest of the group disappears, and the *combined* outline
        is stroked using the styling of the group's first (base) member, not its
        own.  (Confirmed: a union member's own line_width was completely absent
        from Moho's export; the base shape's line_width appeared instead.)
    3   intersect - this shape's fill/stroke is clipped to the union of the
        group's solid (mode 0 or 1) members so far.

combo_mode 2 has been observed in real files (Leg_F/S2 in the Bandit rig) but its
effect has not been reverse-engineered; ShapeGroupRenderer draws it unclipped and
prints a warning, rather than guessing.

FIXED: a combo_mode==3 (intersect) member's own outline no longer shows a
gap that Moho itself does not draw.  Confirmed on Bandit's Eye_Upper/S3 (the
upper eyelid shape, combo_mode==3 against S1's fill): one of its curve
segments has segments_on==false, and that segment's endpoints do NOT
coincide with any segment of S1's own boundary (checked directly - S1's
curve spans x=-0.18..-0.003, y=0.20..0.45; the hidden S3 segment spans
x=-0.094..0.026, y=0.367..0.392 - clearly a different piece of geometry, not
a duplicate of S1's edge).  So unlike the union case above (where a
segments_on==false segment IS the shared boundary that legitimately
disappears because the other group member already draws it), this one had
nothing else to cover it: build_path_d(visible_only=True) simply omitted it,
leaving the stroke as two open subpaths with round caps rather than one
closed loop - visible as a small notch where the two ends of the shape's
outline didn't meet.  Confirmed this was unrelated to the PatchLayer or
MASKING fixes above (re-rendering Eye_Upper with the pre-fix mask code
produced a byte-for-byte identical result before this fix).

This tool approximates `combo_mode` with SVG masking (clip the member's own
stroke to the base's fill), not a true geometric path intersection.  Real
Moho most likely computes an actual new boundary edge where S3's curve
crosses S1's, and marks the ORIGINAL S3 segment segments_on==false because
it has been *replaced* by that computed edge.  Rather than reconstructing
that edge (real Bezier-Bezier intersection - finding the crossing point(s)
and building a new segment there - a substantially different algorithm from
anything else in this file), the fix sidesteps the need for it: for a
combo_mode==3 member specifically, `_render_shape` now builds the stroke
path with `visible_only=False` - i.e. it does NOT drop the segments_on==false
segment, drawing the member's full original closed outline instead of two
open subpaths.  The existing `_mask_union` intersect-clip (unchanged) then
cuts that full outline down to within the base shape's fill exactly as it
already did for the visible segments - and since SVG's own clipping
correctly computes the true geometric crossing point when it rasterises the
mask, the visible result comes out right without this tool ever computing a
Bezier intersection itself.  Confirmed: re-rendering Eye_Upper now produces
one continuous `S3_line` subpath (previously two, split by an "M"), and the
visual gap is gone with nothing else in the shape changed.  This only
touches shapes that are BOTH combo_mode==3 AND have a segments_on==false
segment - checked across all five reference documents, Eye_Upper/S3 is the
ONLY one, so there is no other combo_mode==3 shape this could have
regressed.  Whether an intersect member can ever legitimately want an
artist-drawn gap of its own (which this fix would now incorrectly restore)
remains unconfirmed - no such example has been found, but only one
combo_mode==3-with-a-gap reference exists in total, so this is a small
sample to generalise from.

--------------------------------------------------------------------------------
MASKING
--------------------------------------------------------------------------------
Two *separate* fields are involved - reading only one of them (an earlier,
wrong, version of this rule) gets several real documents backwards:

    group_mask   on a *container* (GroupLayer OR BoneLayer - the layer type
                 does not matter).  0/falsy = "this container does not mask its
                 children at all"; non-zero = masking is active.
    masking      on each *child* of a masking container:
                    2  this child's geometry defines the mask (it is still
                       drawn normally, i.e. being the mask source does not hide
                       it)
                    1  "don't mask this layer" - drawn normally, ignoring the
                       mask
                    anything else (typically 0) - clipped to the union of all
                       masking==2 siblings

A masking==2 child does not always carry its own mesh: a GroupLayer can be
masking==2 purely to act as a masking container (e.g. "BellyTexture" in the
Bandit rig, a GroupLayer whose own `mesh` is None).  Its silhouette is then,
recursively, whatever ITS OWN masking==2 child/children define - the same
shapes that already act as *that* container's internal group_mask source
(see Layer.group_mask), reused as the container's contribution to its
*parent's* mask.  See Exporter._mask_source_shapes.

An earlier version of this tool special-cased (and unconditionally disabled)
masking whenever the masking *container* was the document's own top-level
layer, based on a document (the Bandit rig) where masking appeared not to
apply there.  That was the wrong fix for the bug above: the specific
masking==2 sibling being tested (BellyTexture) is a mesh-less GroupLayer, so
the un-recursed code silently contributed zero mask geometry regardless of
nesting depth - nothing to do with being at the top level.  Confirmed against
the Bandit rig's own Head_DarkBlue (masking==0) / BellyTexture (masking==2)
pair - both direct children of the document's root BoneLayer - masking now
applies there the same as at any other depth.  `--mask-container` remains
available to force masking on a specific layer by name regardless of what
group_mask says, for any future document that contradicts this.

FIXED: a masking==2 sibling's own rendered stroke stays fully visible on top
of whatever it masks - confirmed directly against the Moho app on the Bandit
rig's Head_DarkBlue (masking==0) / BellyTexture (masking==2) pair
(BellyTexture's stroke shows unbroken everywhere it overlaps Head_DarkBlue).
Before this fix, Head_DarkBlue (drawn after BellyTexture in file order)
painted over roughly the inner two-thirds of BellyTexture's own stroke
wherever their un-masked geometry happened to overlap - confirmed by
rasterising both independently and diffing pixel colour along BellyTexture's
stroke centreline (~65% of sampled stroke pixels showed something else's
colour instead of BellyTexture's own).

A z-order fix (reordering `layers` so every masking==2 sibling paints after
every masking==0 sibling within the same container) was tried FIRST and
reverted: most of Bandit's own children (Arm_B, Tail, Ears, Muzzle, Nose,
EyeBrow, Arm_F) are masking==1 ("exempt"), and BellyTexture originally
precedes some of them (e.g. Muzzle) in file order - forcing masking==2 after
masking==0 dragged BellyTexture's opaque fill on top of the character's
eyes/muzzle/nose too (confirmed wrong: those stayed visibly unaffected by
BellyTexture in the Moho app, exactly as this tool already rendered them
before any fix).  There is no single reordering of one container's children
that satisfies both "every masking==2 after every masking==0 sibling" and
"never change relative order against any masking==1 sibling" for this
document - the two constraints conflict for BellyTexture specifically (it
must come both before Muzzle, to preserve the untouched exempt ordering, and
after Head_DarkBlue, per the confirmed stroke behaviour).

(A stronger version of this same idea - reversing the WHOLE `layers` array,
prompted by the observation that Moho's own Layer Pool panel displays a
container's children in the reverse of this array's order - was also tested
directly against Bandit's root container and produces the same Muzzle
regression, for the same reason.  The panel's display order is a UI
convention, not evidence about paint order: `layers` order already IS
back-to-front paint order, confirmed by the many already-correct
non-masking relationships across every reference document - see
`moho-project-file-format.md` § 2.)

The actual fix does not touch paint order at all: `_mask_source_shapes`
additionally returns each source shape's own (plain, non-tapered,
non-brushed) stroke width, and `_mask_element` paints that shape's path a
second time - AFTER its white fill, so it wins - as a BLACK stroke that
width wide.  This carves the source's own stroke band back OUT of the mask,
so whatever the mask clips can never paint over it, regardless of z-order.
Masking==1 siblings are untouched by this (they were never part of the mask
computation), so nothing about them can regress.  Confirmed: re-measuring the
same stroke-centreline pixels afterward, 62% show BellyTexture's own colour
(up from 35%), a further 22% are legitimately covered by OTHER, unrelated
masking==1 siblings (Muzzle/Mouth Stroke/Nose/EyeBrow, whose own normal
z-order relationship to BellyTexture this fix correctly leaves alone), and
the small remainder matches almost exactly (1063 vs 1126 px) what remains
even with Head_DarkBlue/Eye_Back/Head_DarkBlue 2/Eye_Upper removed from the
render entirely - i.e. not attributable to this fix's target layers at all,
most likely residual anti-aliasing at the mask boundary.  Tapered and
brush-styled source outlines are NOT covered by this fix (see
`_mask_source_shapes`) - unconfirmed geometry for those, so they still fall
back to the old fill-only mask contribution.

--------------------------------------------------------------------------------
SMART BONES
--------------------------------------------------------------------------------
A "Smart Bone" is an ordinary bone used as a *dial*: its own rotation angle
selects a pose (an "action") for the rest of the rig, the way a slider selects a
frame.  Structurally:

  - The bone layer has an `actions` list at its own level: just a name registry,
    e.g. [{"name": "EyeBlink"}, ...].
  - A bone counts as a dial if its own *name* matches one of those action names.
  - Any channel anywhere under that bone layer (another bone's angle, a mesh
    point's position, a shape's line width, ...) can carry its own nested
    `actions: [{"name": "EyeBlink", "pose": <channel>}]`.  When dial "EyeBlink"
    is active, a channel that has an "EyeBlink" entry is read from that entry's
    `pose` sub-channel instead of from its own `when`/`val` - at a *frame value*
    found by inverting the pose curve (ActiveAction, Channel.frame_for_value):
    the pose channel's own `val` array records what the dial's *own* angle was
    at each of the pose's keyframes, so "the pose frame whose recorded angle
    matches the dial's current actual angle" is well-defined by interpolation.
  - Moho stores *two* actions per dial, one per rotation direction (plotted
    against the same base name, the second suffixed " 2"), because a pose curve
    must be single-valued/monotonic-ish to invert; Exporter._active_smart_bones
    picks whichever of the two brackets the dial's current angle (falling back
    to whichever is closer if neither does, e.g. the paired action has near-zero
    span because that direction was never posed).
  - Resolving a dial's own *current* angle deliberately bypasses this same
    override mechanism (Channel.eval_raw, not Channel.eval) - a dial's position
    always means its literal position on the main timeline, not a value that
    depends recursively on other active dials.

--------------------------------------------------------------------------------
BONE DEFORMATION ("SKINNING")
--------------------------------------------------------------------------------
A mesh layer's points are transformed in one of two ways, decided per *layer*
(Moho does not support a layer split between the two modes):

  - Rigid: layer.parent_bone is a bone index.  Every point moves exactly as that
    one bone does (rest_to_pose transform of that bone alone).
  - Flexible ("region"/"flexi" binding): every point is a distance-weighted
    blend of *every* bone's rest_to_pose transform (optionally restricted to a
    named subset, layer.flexi_bone_subset).  The weight function
    (Skinner.deform, RenderSettings.bone_weight_falloff) is a HEURISTIC: this
    tool's regression tests happened to only ever exercise layers where exactly
    one bone has non-negligible weight near any given point, so several very
    different falloff shapes (inverse-distance-squared, linear, Hermite, a hard
    cutoff at `strength`) all reproduce the same reference output. The default,
    inverse-distance-squared with no cutoff, is Moho's commonly-cited scheme for
    this binding mode, but it has not been distinguished from the alternatives
    by evidence the way (for example) the stroke-width formula has.

Deformation for a given mesh layer is a *chain* of steps (Exporter._deform_chain
builds a Layer's full ancestor chain into this before any point is touched):
ordinary group/layer transforms compose normally, but crossing into a bone
layer's own local space inserts a skinning step, because a mesh several groups
deep inside a bone layer is deformed in *that bone layer's* coordinate space,
not in its immediate parent's.

--------------------------------------------------------------------------------
PATCH LAYERS
--------------------------------------------------------------------------------
A PatchLayer has no "mesh" field of its own in the raw JSON - it carries a
`target_layer_uuid` naming another layer elsewhere in the document (in every
reference example found, a sibling within the same group) whose *mesh* it
reuses, redrawn at the PATCH layer's own position in the draw order.  This is
how a rig patches a seam that would otherwise show between two overlapping
body parts: e.g. "ayasi-Patch" (a hand's palm patch) reuses the palm mesh
"ayasi", but sits between two of the finger layers in the stack rather than
below all of them, so it covers the gap that appears there as the fingers
move.  Document._resolve_patch_layers finds the target (by uuid, across the
whole document, after the whole tree is built) and copies its `mesh` onto the
PatchLayer.

The PatchLayer's OWN transform/parent_bone/flexi_bone_subset/origin are
deliberately NOT used, even though they exist in the raw JSON and look like
they ought to matter - confirmed wrong empirically: every PatchLayer found
across this tool's reference documents carries some bizarre, unrelated-looking
own transform (a 0.147x non-uniform Y squash plus an 8.9 degree rotation on
"ayasi-Patch"; a uniform ~0.49x scale on "Leg_L-Patch"/"Leg_R-Patch" in the
AddBone rig), while its *target* consistently has the identity transform
(scale 1, translation 0).  Rendering with the patch's own transform (this
tool's first attempt) reproduced exactly that: a squashed sliver floating
away from where the target actually renders, visibly wrong compared to the
target's own rendered position.  Copying the target's transform/parent_bone/
flexi_bone_subset/origin onto the patch instead - so it renders as a
duplicate of the target, just at a different point in the draw order - fixed
that.  This is a HEURISTIC, not a confirmed-exact reverse-engineering: there
is no independent Moho SVG export of a document using PatchLayer available to
verify pixel-for-pixel (Moho's own SVG exporter's behaviour for PatchLayer is
itself unconfirmed here) - see KNOWN GAPS.  A patch whose target never
resolves (missing/dangling uuid, or the target itself never gets a mesh) is
left exactly as before this feature existed: `mesh = None`, drawing nothing.

A resolved patch duplicates its target's FILL only, never its OUTLINE -
confirmed directly against the Moho app itself (not just this tool's own
output) on two independent points that vary the one field that could have
been a confound: "ayasi-Patch" (masking==2, a mask source) and "Left
Bicep-Patch" (masking==0, not a mask source) - both PatchLayers, both with a
target whose shape has has_outline=True and a defined stroke, and BOTH show
no stroke in Moho's own canvas while their respective targets do.  Since
`masking` differs between the two but the result does not, the suppression is
keyed on being a PatchLayer, not on masking (which is independently confirmed
elsewhere to still draw its mask-source layers normally - see MASKING).  This
is handled by ShapeGroupRenderer.suppress_outline, set from
`layer.kind is LayerKind.PATCH` at both export_layer and export_document's
call sites, rather than by mutating Shape.has_outline itself - the patch and
its target share the exact same Shape/Mesh objects (see above), so flipping
the shared has_outline would incorrectly silence the target's own outline
wherever it is rendered independently elsewhere in the tree.

--------------------------------------------------------------------------------
GRADIENTS
--------------------------------------------------------------------------------
A gradient lives on a *named style* (StyleTable), never inline on a shape; a
shape opts in by leaving `define_fill_color` false and inheriting a style whose
fill_style.type == "SS_Gradient2".  gradient_type 0 is linear, 1 is radial;
GradientBuilder places both in objectBoundingBox-style percentages centred on
the shape and sized/rotated by the shape's own effect_scale/effect_rotation.
This placement is approximate - it reproduces the correct colours and general
orientation but has not been matched pixel-for-pixel against Moho's own
(differently-parameterised) gradient placement.

--------------------------------------------------------------------------------
KNOWN GAPS
--------------------------------------------------------------------------------
  - combo_mode 2 (see BOOLEAN SHAPE COMBINATIONS).
  - Whether a combo_mode==3 member can ever legitimately want its OWN
    artist-drawn gap (segments_on==false unrelated to the intersect) is
    unconfirmed - see BOOLEAN SHAPE COMBINATIONS for the fix that now always
    draws such a member's full outline and relies on the intersect-clip to
    cut it correctly; only one combo_mode==3-with-a-gap reference exists.
  - A masking==2 sibling's own TAPERED or BRUSH-styled outline still only
    contributes its bare fill silhouette to the mask, unlike a plain stroke
    (see MASKING) - the exclusion-band fix only handles a uniform stroke
    width; no reference confirms the right geometry for the other two.
  - Gradient centre/radius placement is approximate (see GRADIENTS).
  - The flexible-binding weight falloff is unvalidated for overlapping-influence
    cases (see BONE DEFORMATION).
  - PatchLayer (see PATCH LAYERS) reuses its target's mesh AND transform - the
    heuristic part is specifically ignoring the patch's own transform/
    parent_bone/flexi_bone_subset/origin, which is confirmed necessary (using
    them renders a wrongly-positioned sliver) but not confirmed as the
    complete picture - there is no independent Moho SVG export of a
    PatchLayer-using document to verify pixel-for-pixel against.  (Fill-only,
    no-outline duplication IS confirmed directly against the Moho app - see
    PATCH LAYERS - so this remaining gap is narrower than it used to be:
    transform/position only, not appearance.)
  - Physics (wind/gravity/dynamics), IK, and layer_effects/layer_shadow are
    ignored; none of them affect a flat vector export of a single frame.
  - Textured "brush" line styles (see BRUSH STROKES) are only approximated,
    and only for a brush whose asset (PNG or frame folder) resolves via
    --brush-dir - dab size/density is not calibrated against any real Moho
    reference, a brush_tint=false (native multi-colour texture, not tinted)
    style is not attempted at all, brush_angle_drift/brush_randomize/
    brush_rand_order/sizeVariationAmp are read but not implemented, and the
    first number of a suffixed brush name is not decoded (see BRUSH STROKES
    for the part that is).  The Pillow ("pre-tinted") render path bakes each
    used texture at its native resolution, so it can produce a LARGER file
    than the mask/filter fallback for a document with many distinct
    (brush, colour) combinations sourced from a large texture, despite
    rendering much faster - not implemented: downscaling a source texture
    before baking, which would fix this too.

--------------------------------------------------------------------------------
PORTING NOTES (E.G. TO GO)
--------------------------------------------------------------------------------
This file is organised so each `# ==== SECTION ====` banner below corresponds to
roughly one Go file/package:

    geometry     -> geometry.go       Vec2, Mat2D: plain structs + free functions
                                       (Go has no operator overloading, so
                                       Vec2.__sub__ etc. below become e.g.
                                       Vec2Sub(a, b) or a method Sub(b)).
    animation    -> channel.go        Channel: give it a custom UnmarshalJSON
                                       that accepts either the {when,val,...}
                                       shape or a bare scalar, matching
                                       Channel.of() below.
    style        -> style.go          Color, ResolvedStyle, StyleTable.
    document     -> document.go       LayerKind, Bone, Skeleton, Mesh and
                                       friends, Layer, Document.  These are
                                       intentionally thin: each property is a
                                       one-line accessor over the parsed JSON
                                       (`self._raw.get(...)`) rather than a
                                       fully-normalised copy, specifically so
                                       the mapping to `json:"..."`-tagged Go
                                       structs is mechanical.
    curves       -> curve.go          BezierReconstructor, CurveGeometry.
    pathtrace    -> pathtrace.go       PathTracer, path-string building.  Go has
                                       no tuple-identity trick (this file
                                       explicitly avoids relying on one - see
                                       TracedSegment.reversed); a Go port should
                                       use the same explicit boolean.
    skin         -> skin.go           Skinner, DeformStep (a Go "sum type" via
                                       an interface + two concrete structs, or a
                                       tagged union).
    render       -> render.go          Exporter: the only stateful piece.  It is
                                       deliberately NOT safe to reuse
                                       concurrently for multiple exports (it
                                       caches per-frame skin data and a
                                       def-id counter as instance fields) - a Go
                                       port wanting concurrency should construct
                                       one Exporter per goroutine/export call
                                       rather than share one, exactly as this
                                       Python version expects one Exporter per
                                       call to export_layer/export_document.
    cli          -> main.go / cmd/     Argument parsing and file I/O only.

Deliberately NOT class-per-concept: a few algorithms here (PathTracer, the SVG
path-string builders) are plain functions rather than objects with methods,
because they hold no state of their own between calls - forcing a stateless
algorithm into a class for its own sake is a Java-ism that Go idiom does not
reward either; a Go port should feel free to keep these as plain functions too.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import random
import re
import struct
import sys
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Iterator, Optional, Sequence, Union

try:
    # Optional: only used to pre-tint brush textures once per (brush, colour)
    # at export time instead of masking+filtering every dab at render time -
    # see the module docstring's BRUSH STROKES section.  Absent, brush
    # rendering falls back to the mask/filter path (the only path that ever
    # existed before this), so this tool still runs with zero third-party
    # dependencies if Pillow is not installed.
    from PIL import Image, ImageChops, ImageOps
except ImportError:
    Image = ImageChops = ImageOps = None


# ============================================================================
# ==== GEOMETRY  (-> geometry.go: plain structs, free functions)         ====
# ============================================================================

@dataclass(frozen=True)
class Vec2:
    """A 2D point or vector.  Used for both Moho-space coordinates (2 units =
    canvas height, see module docstring) and pixel-space coordinates - which
    space a given Vec2 is in is a matter of context, not of the type.

    Operators are provided for readability (`a - b`, `k * v`); a Go port has no
    operator overloading, so implement these as ordinary functions instead,
    e.g. Sub(a, b Vec2) Vec2 - the method names below (`minus`, `scaled`, ...)
    are the canonical names to give those functions.
    """
    x: float
    y: float

    def plus(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def minus(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def scaled(self, k: float) -> "Vec2":
        return Vec2(self.x * k, self.y * k)

    def dot(self, other: "Vec2") -> float:
        return self.x * other.x + self.y * other.y

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def distance_to(self, other: "Vec2") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def normalized(self) -> "Vec2":
        L = self.length()
        return Vec2(self.x / L, self.y / L) if L else Vec2(0.0, 0.0)

    def rotated(self, radians: float) -> "Vec2":
        """Rotate this vector (treated as relative to the origin) by `radians`."""
        co, si = math.cos(radians), math.sin(radians)
        return Vec2(self.x * co - self.y * si, self.x * si + self.y * co)

    def rounded_key(self, decimals: int = 9) -> tuple[float, float]:
        """A hashable key for "same point" comparisons that tolerates the tiny
        floating-point noise introduced by the transform pipeline.  Used by
        PathTracer to recognise that two segment endpoints are the same point
        even if they were computed via slightly different arithmetic paths."""
        return (round(self.x, decimals), round(self.y, decimals))

    @classmethod
    def of(cls, raw: dict) -> "Vec2":
        """Build from Moho's {"x": ..., "y": ...} representation (ignores any
        "z", which Moho keeps around for a handful of 3-vector fields but which
        nothing in a flat vector export ever uses)."""
        return cls(float(raw["x"]), float(raw["y"]))

    def __sub__(self, other: "Vec2") -> "Vec2":
        return self.minus(other)

    def __add__(self, other: "Vec2") -> "Vec2":
        return self.plus(other)

    def __mul__(self, k: float) -> "Vec2":
        return self.scaled(k)

    __rmul__ = __mul__


IDENTITY_MATRIX: "Mat2D"  # forward reference; assigned right after the class


@dataclass(frozen=True)
class Mat2D:
    """A 2D affine transform, stored as Moho/SVG do: `[[a, c, e], [b, d, f]]`
    acting on a column vector, i.e.

        x' = a*x + c*y + e
        y' = b*x + d*y + f

    Go: a struct of six float64 fields (A, B, C, D, E, F); implement Compose,
    Apply, Inverse and UniformScale as functions or methods on that struct.
    """
    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    def apply(self, p: Vec2) -> Vec2:
        return Vec2(self.a * p.x + self.c * p.y + self.e,
                     self.b * p.x + self.d * p.y + self.f)

    def compose(self, inner: "Mat2D") -> "Mat2D":
        """Returns the transform equivalent to applying `inner` first and then
        `self` - i.e. `self.compose(inner).apply(p) == self.apply(inner.apply(p))`.
        (Function-composition order: self ∘ inner.)  Layer chains are built by
        repeatedly composing the *outer* (already-accumulated, closer to the
        document root) transform with each child's *local* transform as the
        inner argument, so that a point expressed in the innermost child's own
        coordinates ends up mapped all the way out to document space."""
        m, n = self, inner
        return Mat2D(
            m.a * n.a + m.c * n.b, m.b * n.a + m.d * n.b,
            m.a * n.c + m.c * n.d, m.b * n.c + m.d * n.d,
            m.a * n.e + m.c * n.f + m.e, m.b * n.e + m.d * n.f + m.f,
        )

    def inverse(self) -> "Mat2D":
        det = self.a * self.d - self.b * self.c
        a, b, c, d = self.d / det, -self.b / det, -self.c / det, self.a / det
        return Mat2D(a, b, c, d, -(a * self.e + c * self.f), -(b * self.e + d * self.f))

    def uniform_scale(self) -> float:
        """sqrt(|determinant|) - the scale factor for a transform that is a
        pure rotation+uniform-scale+translation (which every Moho layer
        transform is, by construction: see Layer.local_matrix).  Used for
        scaling stroke width by the accumulated *layer* scale - see the module
        docstring's STROKE WIDTH section for why bone deformation must be
        excluded from this figure."""
        return math.sqrt(abs(self.a * self.d - self.b * self.c))


IDENTITY_MATRIX = Mat2D(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


# ============================================================================
# ==== ANIMATION  (-> channel.go: Channel with a custom UnmarshalJSON)   ====
# ============================================================================

@dataclass(frozen=True)
class ActionRef:
    """One entry of a Channel's `actions` list: this channel has a different
    value while Smart Bone dial `name` is active, given by `pose` (itself a
    full Channel, keyed by "action frame" rather than by document frame - see
    the module docstring's SMART BONES section)."""
    name: str
    pose: "Channel"


@dataclass(frozen=True)
class ActiveAction:
    """One active Smart Bone dial, as resolved for the current render: `name`
    identifies the action, `frame` is the position *within that action's own
    pose curve* (found by Channel.frame_for_value), not a document frame."""
    name: str
    frame: float


class Channel:
    """A Moho animated value.

    Wraps the {"when": [...], "val": [...], "actions": [...]} structure that
    almost every property in a Moho document is stored as.  Use Channel.of() to
    build one, which also accepts a bare, never-animated value (a plain float,
    a plain {"x":..,"y":..} dict, etc.) transparently as a one-keyframe
    constant, since Moho itself stores some fields that way.

    Values themselves are left untyped (`Any`): depending on which field a
    channel came from, `val[i]` is a float, a {"x","y"[,"z"]} dict, an
    {"r","g","b","a"} colour dict, a bool, or a string (SwitchLayer's
    switch_keys).  Go: give Channel's Val field type `[]interface{}` (or
    `json.RawMessage` per element, decoded lazily by the caller who knows what
    shape to expect for that particular field), since the shape genuinely
    depends on context the way it does here.
    """

    __slots__ = ("when", "val", "actions")

    _cache: dict[int, "Channel"] = {}

    def __init__(self, when: list[float], val: list[Any], actions: list[ActionRef]):
        self.when = when
        self.val = val
        self.actions = actions

    @staticmethod
    def of(raw: Any) -> "Channel":
        """Build (or reuse) a Channel for `raw`.

        Every wrapper class in the document model (MeshPoint, CurvePoint, Bone,
        ...) stores its channel fields as direct references into the parsed
        JSON, never copies - so the same logical channel is always the same
        Python dict object across every call, for the life of one Document.
        Caching by id() is therefore safe (not just "probably fine"): it
        cannot conflate two different channels, and the cached Channel is
        immutable. This turns repeated evaluation of the same channel (every
        curve point's smoothness/weight/offset gets looked at more than once
        per frame) from rebuilding a small object tree each time into a dict
        lookup - purely a performance detail, with no effect on behaviour.
        """
        if isinstance(raw, dict) and "when" in raw and "val" in raw:
            key = id(raw)
            cached = Channel._cache.get(key)
            if cached is not None:
                return cached
            actions = [ActionRef(a.get("name"), Channel.of(a.get("pose")))
                       for a in (raw.get("actions") or [])]
            channel = Channel(raw["when"], raw["val"], actions)
            Channel._cache[key] = channel
            return channel
        return Channel([0], [raw], [])

    def action_pose(self, name: str) -> Optional["Channel"]:
        for a in self.actions:
            if a.name == name:
                return a.pose
        return None

    def eval_raw(self, frame: float) -> Any:
        """The plain piecewise-linear value at `frame`, ignoring any Smart Bone
        action override.  Used directly (rather than via .eval()) exactly once
        in this codebase: resolving a dial bone's *own* current angle must not
        recurse into the action-override machinery it is itself part of - see
        the module docstring's SMART BONES section."""
        when, val = self.when, self.val
        if len(when) == 1 or frame <= when[0]:
            return val[0]
        if frame >= when[-1]:
            return val[-1]
        for i in range(len(when) - 1):
            if when[i] <= frame <= when[i + 1]:
                t = (frame - when[i]) / (when[i + 1] - when[i])
                a, b = val[i], val[i + 1]
                if isinstance(a, dict):
                    return {k: a[k] + (b[k] - a[k]) * t for k in a}
                if isinstance(a, (int, float)) and not isinstance(a, bool):
                    return a + (b - a) * t
                return a          # strings / bools: snap to the left keyframe
        return val[-1]

    def eval(self, frame: float, active_actions: Sequence[ActiveAction]) -> Any:
        """The value at `frame`, honouring Smart Bone overrides.

        If any currently-active dial has a matching entry in this channel's own
        `actions`, the value comes from that entry's pose curve at the dial's
        resolved action-frame - the *first* match wins, and `active_actions`
        must therefore already be in priority order (outermost/root bone layer
        first - see Exporter._active_smart_bones)."""
        for active in active_actions:
            pose = self.action_pose(active.name)
            if pose is not None:
                return pose.eval_raw(active.frame)
        return self.eval_raw(frame)

    def frame_for_value(self, target: float) -> float:
        """Invert a piecewise-linear channel: the frame whose value equals
        `target` (clamped to the channel's own value range, and picking the
        nearest keyframe if the range is degenerate).  Used to turn "the dial's
        current angle" into "the corresponding frame within its pose action" -
        see the module docstring's SMART BONES section."""
        when, val = self.when, self.val
        if len(when) < 2:
            return when[0] if when else 0.0
        lo, hi = min(val), max(val)
        target = max(lo, min(hi, target))
        for i in range(len(when) - 1):
            a, b = val[i], val[i + 1]
            if (a <= target <= b) or (b <= target <= a):
                if abs(b - a) < 1e-12:
                    return when[i]
                t = (target - a) / (b - a)
                return when[i] + t * (when[i + 1] - when[i])
        return when[-1] if abs(target - val[-1]) < abs(target - val[0]) else when[0]


# ============================================================================
# ==== STYLE  (-> style.go: Color, ResolvedStyle, StyleTable)            ====
# ============================================================================

@dataclass(frozen=True)
class Color:
    """An RGBA colour, normalised to 0..1 regardless of how Moho encoded it.

    Moho writes colours as 0..1 floats almost everywhere, but as 0..255
    integers in a couple of older/legacy fields (observed on a TextLayer's own
    colour fields in a format-1038 document).  from_raw() detects which by
    checking whether every component is an int and/or any component exceeds
    1.0 - a genuine 0..1 float channel never does, so this is unambiguous in
    practice."""
    r: float
    g: float
    b: float
    a: float

    @classmethod
    def from_raw(cls, raw: dict) -> "Color":
        v = [raw.get(k, 0) for k in "rgb"]
        a = raw.get("a", 1.0)
        looks_like_bytes = (all(isinstance(x, int) and not isinstance(x, bool)
                                 for x in v + [a])
                             or max(v + [a]) > 1.0)
        if looks_like_bytes:
            v = [x / 255.0 for x in v]
            a = a / 255.0 if a > 1.0 else a
        return cls(v[0], v[1], v[2], a)

    def hex(self) -> str:
        r, g, b = (max(0, min(255, round(x * 255))) for x in (self.r, self.g, self.b))
        return f"#{r:02x}{g:02x}{b:02x}"

    def to_svg(self) -> tuple[str, float]:
        """Convenience matching the common `hex, alpha = color.to_svg()` call
        pattern used throughout ShapeGroupRenderer."""
        return self.hex(), self.a


LINE_CAP_NAMES = {0: "butt", 1: "round", 2: "square"}


@dataclass
class ResolvedStyle:
    """A shape's styling *after* resolving inheritance from the document's
    named style list (StyleTable) - see ResolvedStyle.resolve.

    Fields still hold raw channels (or, for line_caps, a plain int - Moho never
    animates line caps) rather than evaluated values: evaluating a channel
    needs a frame and the current Smart Bone context (Exporter.eval), which
    this structural merge does not have and does not need, since inheritance
    itself never varies by frame.
    """
    fill_color: Any
    line_color: Any
    line_width: Any
    line_caps: int
    fill_style: Optional[dict]      # gradient spec, or None for a flat fill
    brush_name: Optional[str]       # texture brush stamp name, or None for a plain stroke
    brush_jitter: float             # random rotation spread (radians) per dab
    brush_spacing: float            # dab spacing, as a fraction of the dab's own diameter
    brush_align: bool               # rotate each dab to the local path tangent
    brush_tint: bool                # recolour the (greyscale) texture to line_color

    @staticmethod
    def resolve(shape_raw: dict, styles: "StyleTable") -> "ResolvedStyle":
        """Merge a shape's own style with the named style(s) it inherits from.

        Older documents (format 1038 and similar) leave every `define_*` flag
        false on the shape itself and keep the real colours in a named style
        referenced by uuid or name; newer documents put real values directly on
        the shape and leave the `inherited_style*` fields empty.  A shape can
        reference the inherited-style *uuid or name on either itself or inside
        its own style dict* - both have been observed in real files, so both
        are checked.  Style 1 is applied before style 2, so style 2 wins where
        both define the same attribute (observed as the mechanism for e.g. an
        outline-only "line style" layered on top of a base fill style)."""
        own = shape_raw["style"]
        out = dict(own)
        for key in ("inherited_style_uuid", "inherited_style_name",
                    "inherited_style2_uuid", "inherited_style2_name"):
            ref = shape_raw.get(key) or own.get(key)
            named = styles.get(ref) if ref else None
            if not named:
                continue
            for flag, field_name in (("define_fill_color", "fill_color"),
                                      ("define_line_col", "line_color"),
                                      ("define_line_width", "line_width")):
                if named.get(flag) and not own.get(flag):
                    out[field_name] = named[field_name]
            # The gradient itself lives only on the named style, never inline.
            if isinstance(named.get("fill_style"), dict) and not own.get("define_fill_color"):
                out["fill_style"] = named["fill_style"]
            if not own.get("define_line_width") and "line_caps" in named:
                out["line_caps"] = named["line_caps"]
            # Brush texture parameters live only on named styles, never
            # inline on a shape (mirroring fill_style/gradients above) - see
            # the module docstring's BRUSH STROKES section.  Piggybacks on
            # the same define_line_width flag as line_width/line_caps, since
            # a brush only ever styles the line.
            if named.get("define_line_width") and not own.get("define_line_width") and named.get("brush_name"):
                for brush_field in ("brush_name", "brush_jitter", "brush_spacing",
                                    "brush_align", "brush_tint"):
                    out[brush_field] = named.get(brush_field)
        return ResolvedStyle(
            fill_color=out.get("fill_color"),
            line_color=out.get("line_color"),
            line_width=out.get("line_width"),
            line_caps=out.get("line_caps", 1),
            fill_style=out.get("fill_style") if isinstance(out.get("fill_style"), dict) else None,
            brush_name=out.get("brush_name") or None,
            brush_jitter=out.get("brush_jitter") or 0.0,
            brush_spacing=out.get("brush_spacing") or 0.0,
            brush_align=bool(out.get("brush_align")),
            brush_tint=bool(out.get("brush_tint", True)),
        )

    def line_cap_name(self) -> str:
        return LINE_CAP_NAMES.get(self.line_caps, "round")


class StyleTable:
    """The document's named-style list (`doc["styles"]`), indexed for lookup by
    either uuid or name - a shape's `inherited_style*` fields may use either."""

    def __init__(self, by_key: dict[str, dict]):
        self._by_key = by_key

    @classmethod
    def build(cls, raw_styles: Iterable[dict]) -> "StyleTable":
        by_key: dict[str, dict] = {}
        for st in raw_styles:
            if st.get("uuid"):
                by_key[st["uuid"]] = st
            if st.get("name"):
                by_key.setdefault(st["name"], st)
        return cls(by_key)

    def get(self, key: Optional[str]) -> Optional[dict]:
        return self._by_key.get(key) if key else None


# ============================================================================
# ==== DOCUMENT MODEL  (-> document.go: mostly thin, mechanical wrappers)====
# ============================================================================
#
# Every class below wraps a raw parsed-JSON dict/list rather than copying its
# fields into new attributes: each property is a one-line accessor over that
# raw data.  This is deliberate - see the module docstring's PORTING NOTES -
# and it means a property here maps directly onto a `json:"..."`-tagged field
# of the same name on a Go struct.  The exceptions are the handful of fields
# that get *parsed* once into a more convenient shape (e.g. Layer.flexi_
# bone_subset turns Moho's "27|28|29" string into [27, 28, 29]) because no
# caller ever wants the raw string form.
#
# Fields whose value is itself a Channel (animatable) are exposed as the raw
# channel object, unevaluated: see Exporter.eval / Exporter.eval_raw.  A field
# that Moho never animates (line_caps, combo_mode, has_fill/has_outline,
# masking, group_mask, a curve-point's segments_on, ...) is exposed as its
# plain evaluated type directly.

class LayerKind(str, Enum):
    MESH = "MeshLayer"
    BONE = "BoneLayer"
    GROUP = "GroupLayer"
    SWITCH = "SwitchLayer"
    TEXT = "TextLayer"
    PATCH = "PatchLayer"      # carries no mesh of its own - see the module
                               # docstring's PATCH LAYERS section and
                               # Document._resolve_patch_layers.
    OTHER = "__other__"       # anything else Moho might define.


_LAYER_KIND_BY_TYPE_NAME = {k.value: k for k in LayerKind if k is not LayerKind.OTHER}


@dataclass(frozen=True)
class Bone:
    """One bone of a Skeleton.  `parent` is an index into that same skeleton's
    bone list, or -1 for a root bone.  `length` and `strength` are plain
    (never-animated) floats; anim_pos/anim_angle/anim_scale are channels - see
    Skeleton.world_matrices for how they combine into a transform."""
    name: str
    parent: int
    length: float
    strength: float
    anim_pos: Any
    anim_angle: Any
    anim_scale: Any

    @staticmethod
    def _build(raw: dict) -> "Bone":
        return Bone(
            name=raw.get("name", ""),
            parent=raw.get("parent", -1),
            length=raw.get("length", 0.0),
            strength=raw.get("strength", 0.0),
            anim_pos=raw["anim_pos"],
            anim_angle=raw["anim_angle"],
            anim_scale=raw["anim_scale"],
        )


class Skeleton:
    """The `skeleton` of a BoneLayer: just a flat list of Bone, each pointing
    at its parent by index.  A bone's *world* transform is only meaningful
    relative to a frame, hence world_matrices() rather than a precomputed
    property."""

    def __init__(self, bones: list[Bone]):
        self.bones = bones

    @staticmethod
    def _build(raw: Optional[dict]) -> Optional["Skeleton"]:
        if not raw or not raw.get("bones"):
            return None
        return Skeleton([Bone._build(b) for b in raw["bones"]])

    def world_matrices(self, frame: float, exporter: "Exporter") -> list[Mat2D]:
        """One world-space matrix per bone, parents resolved before children
        regardless of list order (parents are not guaranteed to appear earlier
        in `bones` than their children - this walks each bone's parent chain
        on demand, memoising visited bones, rather than assuming any order).

        NOTE ON SCALE: only the matrix's first column is scaled by the bone's
        own `anim_scale`; the second is not (see the `local` line below). That
        asymmetry is preserved exactly as found during development, because it
        passed every regression test available - but no test in this tool's
        corpus actually exercises a bone with anim_scale far from 1.0 in a way
        that would tell an asymmetric scale apart from a symmetric (uniform)
        one, so this has NOT been independently confirmed as intentional Moho
        behaviour versus an earlier transcription slip.  Flagged rather than
        "corrected" - see the module docstring's KNOWN GAPS.
        """
        n = len(self.bones)
        out: list[Optional[Mat2D]] = [None] * n
        seen: set[int] = set()
        order: list[int] = []

        def add(i: int) -> None:
            if i in seen:
                return
            seen.add(i)
            parent = self.bones[i].parent
            if parent >= 0:
                add(parent)
            order.append(i)

        for i in range(n):
            add(i)

        for i in order:
            bone = self.bones[i]
            pos = Vec2.of(exporter.eval(bone.anim_pos, frame))
            angle = exporter.eval(bone.anim_angle, frame)
            scale = exporter.eval(bone.anim_scale, frame)
            c, s = math.cos(angle), math.sin(angle)
            local = Mat2D(c * scale, s * scale, -s, c, pos.x, pos.y)
            parent = bone.parent
            out[i] = out[parent].compose(local) if parent >= 0 else local
        return out  # type: ignore[return-value]


@dataclass(frozen=True)
class CurvePoint:
    """One point along a Curve, with the data needed to reconstruct the two
    Bezier handles either side of it - see BezierReconstructor and the module
    docstring's BEZIER CURVES section.  `point_index` indexes into the owning
    Mesh's `points` list (a curve does not store its own coordinates - point
    *position* is shared with every curve/shape that references it)."""
    point_index: int
    smoothness: Any
    weight_in: Any
    weight_out: Any
    offset_in: Any
    offset_out: Any
    segments_on: bool

    @staticmethod
    def _build(raw: dict) -> "CurvePoint":
        return CurvePoint(
            point_index=raw["point"],
            smoothness=raw["smoothness"],
            weight_in=raw["weight_in"],
            weight_out=raw["weight_out"],
            offset_in=raw["offset_in"],
            offset_out=raw["offset_out"],
            segments_on=bool(raw["segments_on"]),
        )


class Curve:
    """A sequence of CurvePoint.  If `closed`, there is one segment per point
    (the last wraps back to the first); otherwise one fewer segment than
    points."""

    def __init__(self, closed: bool, points: list[CurvePoint]):
        self.closed = closed
        self.points = points

    @staticmethod
    def _build(raw: dict) -> "Curve":
        return Curve(bool(raw["closed"]), [CurvePoint._build(p) for p in raw["points"]])

    def segment_count(self) -> int:
        n = len(self.points)
        return n if self.closed else max(0, n - 1)


@dataclass(frozen=True)
class MeshPoint:
    """One point of a Mesh.  `position` is a Vec2 channel; `width` is a float
    channel, normally 1.0 - see the module docstring's STROKE WIDTH and TAPERED
    STROKES sections for what a non-1.0 or varying width means."""
    position: Any
    width: Any

    @staticmethod
    def _build(raw: dict) -> "MeshPoint":
        return MeshPoint(position=raw["position"], width=raw["width"])


@dataclass(frozen=True)
class Edge:
    """One segment referenced by a Shape's outline: segment `segment` of
    `curve` (both indices into the owning Mesh).  `flag` is stored in the file
    but is NOT a trustworthy direction bit - see the module docstring's SHAPES,
    EDGES... section and PathTracer, which ignores it."""
    curve: int
    segment: int
    flag: int


class Shape:
    """One filled/stroked region of a Mesh.  A shape's *style* is resolved
    once at load time (ResolvedStyle.resolve), since inheritance from the
    document's named styles never depends on frame."""

    def __init__(self, shape_id: int, name: str, has_fill: bool, has_outline: bool,
                 combo_mode: int, edges: list[Edge], style: ResolvedStyle,
                 effect_scale: Any, effect_rotation: Any):
        self.id = shape_id
        self.name = name
        self.has_fill = has_fill
        self.has_outline = has_outline
        self.combo_mode = combo_mode
        self.edges = edges
        self.style = style
        self.effect_scale = effect_scale       # channel; gradient scale, default 1.0
        self.effect_rotation = effect_rotation  # channel; gradient rotation, default 0.0

    @staticmethod
    def _build(raw: dict, styles: StyleTable) -> "Shape":
        e = raw["edges"]
        edges = [Edge(c, s, f) for c, s, f in zip(e["curve"], e["segment"], e["flag"])]
        return Shape(
            shape_id=raw["id"],
            # NOTE: fall back to "S<id>" only when the *key is absent*, not
            # when it is present-but-empty ("" is a real, if unhelpful, name
            # Moho itself writes for a TextLayer glyph's synthesised shapes) -
            # matching dict.get(key, default) exactly, deliberately not `or`.
            name=str(raw.get("name", f"S{raw['id']}")),
            has_fill=bool(raw.get("has_fill")),
            has_outline=bool(raw.get("has_outline")),
            combo_mode=raw.get("combo_mode", 0),
            edges=edges,
            style=ResolvedStyle.resolve(raw, styles),
            effect_scale=raw.get("effect_scale", 1.0),
            effect_rotation=raw.get("effect_rotation", 0.0),
        )


class Mesh:
    """The vector artwork of a MeshLayer: shared points, curves built from
    those points, and shapes built from curve segments.  See the module
    docstring for how curves/shapes relate."""

    def __init__(self, points: list[MeshPoint], curves: list[Curve], shapes: list[Shape]):
        self.points = points
        self.curves = curves
        self.shapes = shapes

    @staticmethod
    def _build(raw: dict, styles: StyleTable) -> "Mesh":
        return Mesh(
            points=[MeshPoint._build(p) for p in raw["points"]],
            curves=[Curve._build(c) for c in raw["curves"]],
            shapes=[Shape._build(s, styles) for s in raw["shapes"]],
        )


class Transform:
    """The five animatable channels that make up a layer's local transform.
    See Layer.local_matrix for how they, plus the layer's `origin`, combine."""

    def __init__(self, raw: dict):
        self.translation = raw["translation"]
        self.scale = raw["scale"]
        self.rotation_z = raw["rotation_z"]
        self.flip_h = raw["flip_h"]
        self.flip_v = raw["flip_v"]


class Layer:
    """One node of the document's layer tree.  See the module docstring's
    MOHO DOCUMENT MODEL section for what each `kind` means.

    `children` is already resolved at load time (Layer._build) - including
    synthesising a MeshLayer child for a TextLayer's nested `mesh_layer` - so
    nothing downstream needs to special-case TextLayer at all.
    """

    def __init__(self, raw: dict, kind: LayerKind, type_name: str,
                 children: list["Layer"], mesh: Optional[Mesh],
                 skeleton: Optional[Skeleton], is_container: bool):
        self._raw = raw
        self.kind = kind
        self.type_name = type_name      # the raw JSON string, for display/`--list`
        self.children = children
        # A PatchLayer's `mesh` starts out None here (it carries none of its
        # own in the raw JSON) and is filled in afterward, once the whole
        # tree exists, by Document._resolve_patch_layers - see the module
        # docstring's PATCH LAYERS section.  `mesh` is a plain attribute
        # (not read-only) specifically so that late assignment works.
        self.mesh = mesh
        self.skeleton = skeleton
        # Whether the raw JSON has a "layers" key AT ALL (even as an empty
        # list) is distinct from `children` being empty: a PatchLayer has no
        # "layers" key and (before Document._resolve_patch_layers runs) no
        # mesh either, so it would draw nothing and recurse into nothing -
        # which is what `is_container` distinguishes, and remains correct
        # for a PatchLayer whose target never resolves to real geometry.
        self.is_container = is_container
        self.transform = Transform(raw["transforms"])

    @property
    def name(self) -> str:
        return self._raw.get("name", "")

    @property
    def uuid(self) -> str:
        return self._raw.get("uuid", "")

    @property
    def target_layer_uuid(self) -> str:
        """Only meaningful when kind is PATCH: the uuid of the layer whose
        mesh this patch reuses - see Document._resolve_patch_layers and the
        module docstring's PATCH LAYERS section."""
        return self._raw.get("target_layer_uuid", "")

    @property
    def visible(self) -> bool:
        return self._raw.get("visible", True)

    @property
    def edit_only(self) -> bool:
        """Layers Moho keeps for editing convenience but never renders (e.g. a
        SwitchLayer alternative kept as reference).  Confirmed against a real
        document: Moho's own SVG export defines an empty `<g>` for such a
        layer rather than drawing its shapes."""
        return bool(self._raw.get("edit_only"))

    @property
    def masking(self) -> int:
        """This layer's role within its parent's mask (if the parent is
        masking at all - see Layer.group_mask and the module docstring's
        MASKING section): 2 = mask source, 1 = exempt from masking, else
        clipped."""
        return self._raw.get("masking", 0)

    @property
    def group_mask(self) -> int:
        """Non-zero if this layer (as a *container*) masks its children at
        all.  See the module docstring's MASKING section."""
        return self._raw.get("group_mask") or 0

    @property
    def parent_bone(self) -> int:
        """Bone index this layer is *rigidly* bound to, or -1 for flexible
        ("region") binding across its skeleton (or its flexi_bone_subset, if
        narrower).  See the module docstring's BONE DEFORMATION section."""
        return self._raw.get("parent_bone", -1)

    @property
    def origin(self) -> Vec2:
        o = self._raw.get("origin") or {}
        return Vec2(o.get("x", 0.0), o.get("y", 0.0))

    @property
    def action_names(self) -> frozenset[str]:
        """Names registered in this (bone) layer's own `actions` list.  This is
        only a name registry - it does not itself carry any pose data, and a
        bone counts as a Smart Bone dial if its own *name* appears here.  See
        the module docstring's SMART BONES section."""
        return frozenset(a.get("name") for a in (self._raw.get("actions") or []))

    @property
    def flexi_bone_subset(self) -> list[int]:
        raw = self._raw.get("flexi_bone_subset") or ""
        return [int(i) for i in str(raw).split("|") if i != ""]

    @property
    def switch_keys(self) -> Any:
        """Only meaningful when kind is SWITCH: an animated string channel
        naming the currently-active child."""
        return self._raw.get("switch_keys")

    def local_matrix(self, frame: float, exporter: "Exporter") -> Mat2D:
        """This layer's own transform, mapping a point in ITS OWN local
        coordinate space into its parent's coordinate space.

        Rotation and scale pivot on `origin`, not on (0, 0):

            p' = origin + translation + R * S * (p - origin)

        (Bones use a related but distinct formula - non-uniform scale here is
        genuinely per-axis (flip_h/flip_v aside, x and y have independent
        scale channels), whereas a bone has a single, uniform anim_scale -
        see Skeleton.world_matrices.)
        """
        t = self.transform
        tr = Vec2.of(exporter.eval(t.translation, frame))
        sc = Vec2.of(exporter.eval(t.scale, frame))
        rz = exporter.eval(t.rotation_z, frame)
        sx = sc.x * (-1 if exporter.eval(t.flip_h, frame) else 1)
        sy = sc.y * (-1 if exporter.eval(t.flip_v, frame) else 1)
        cos, sin = math.cos(rz), math.sin(rz)
        a, b, c, d = cos * sx, sin * sx, -sin * sy, cos * sy
        o = self.origin
        e = o.x + tr.x - (a * o.x + c * o.y)
        f = o.y + tr.y - (b * o.x + d * o.y)
        return Mat2D(a, b, c, d, e, f)

    def switch_active_child(self, frame: float, exporter: "Exporter") -> Optional["Layer"]:
        """Only meaningful when kind is SWITCH: resolves which child is shown.

        The recorded active-child name can go stale if that sub-layer was
        later renamed (observed in a real document: a "Mouth" switch layer
        recorded "Layer 2" as active while its only child was named "Closed").
        Moho's own renderer falls back to the *first* child rather than
        drawing nothing, which is replicated here."""
        if not self.children:
            return None
        active = str(exporter.eval(self.switch_keys, frame) or "")
        for child in self.children:
            if child.name == active:
                return child
        return self.children[0]

    @staticmethod
    def _build(raw: dict, styles: StyleTable) -> "Layer":
        type_name = raw.get("type", "")
        kind = _LAYER_KIND_BY_TYPE_NAME.get(type_name, LayerKind.OTHER)

        children_raw = raw.get("layers")
        if kind == LayerKind.TEXT and not children_raw:
            nested = raw.get("mesh_layer")
            if isinstance(nested, dict) and "mesh" in nested:
                if not nested.get("name"):
                    nested = dict(nested, name=f"{raw.get('name') or 'Text'}_text")
                children_raw = [nested]

        is_container = isinstance(children_raw, list) or kind == LayerKind.TEXT
        children = [Layer._build(c, styles) for c in (children_raw or [])]
        mesh = Mesh._build(raw["mesh"], styles) if "mesh" in raw else None
        skeleton = Skeleton._build(raw.get("skeleton"))
        return Layer(raw, kind, type_name, children, mesh, skeleton, is_container)


class Document:
    """A parsed Moho project.  Build with `load_document(path)` (in the CLI
    section below) or Document.from_raw() if you already have the parsed JSON."""

    def __init__(self, width: float, height: float, layers: list[Layer],
                 styles: StyleTable, format_version: Any):
        self.width = width
        self.height = height
        self.layers = layers            # top-level (root) layers
        self.styles = styles
        self.format_version = format_version

    @classmethod
    def from_raw(cls, raw: dict) -> "Document":
        styles = StyleTable.build(raw.get("styles") or [])
        layers = [Layer._build(item, styles) for item in raw["layers"]]
        pd = raw["project_data"]
        doc = cls(pd["width"], pd["height"], layers, styles, raw.get("version"))
        doc._resolve_patch_layers()
        return doc

    def _resolve_patch_layers(self) -> None:
        """A PatchLayer carries no mesh of its own in the raw JSON - it
        reuses another layer's mesh (named by that other layer's `uuid`, in
        the patch's own `target_layer_uuid`), redrawn at the patch's OWN
        position in the layer stack (and its own masking/visibility) - a way
        to patch a visible seam a later-drawn layer would otherwise leave
        (e.g. "ayasi-Patch" reusing the palm mesh "ayasi", positioned in
        front of some finger layers and behind others - see the module
        docstring's PATCH LAYERS section).

        A PatchLayer's OWN transform/parent_bone/flexi_bone_subset/origin are
        NOT used for this, deliberately - every PatchLayer found across this
        tool's reference documents carries a bizarre, seemingly-unrelated own
        transform (e.g. a 0.147x non-uniform Y squash plus rotation on
        "ayasi-Patch"; a uniform ~0.49x scale on "Leg_L-Patch"/"Leg_R-Patch"),
        while its target consistently has the IDENTITY transform (scale 1,
        translation 0). Rendering with the patch's own transform (this
        tool's first attempt) reproduces exactly that: a squashed, wrongly-
        positioned sliver floating away from where the target actually is -
        confirmed wrong by comparing against the target's own rendered
        position. Copying the target's transform/parent_bone/
        flexi_bone_subset/origin onto the patch instead - i.e. the patch
        renders as a duplicate of the target, in the same place, just at a
        different point in the draw order - is a heuristic fix for that,
        not a confirmed-exact reverse-engineering: there is no independent
        Moho SVG export of a document using PatchLayer to verify the result
        pixel-for-pixel against (see the module docstring's KNOWN GAPS).

        Resolved here, after the whole tree is built (a target can be
        anywhere in the document, including a layer not yet constructed at
        the point its PatchLayer sibling was built) - a target that is a
        PatchLayer itself, though not observed in any reference document, is
        handled by iterating until nothing new resolves rather than assuming
        a single pass suffices. A patch whose target never resolves (missing
        uuid, or the target itself never gets a mesh) is left with
        `mesh = None`, which existing code already treats as "draws nothing"
        - the pre-this-feature behaviour for every PatchLayer, preserved
        exactly as a fallback.
        """
        by_uuid = {layer.uuid: layer for _, layer in self.walk() if layer.uuid}
        patches = [layer for _, layer in self.walk() if layer.kind is LayerKind.PATCH]
        resolved_any = True
        while resolved_any:
            resolved_any = False
            for layer in patches:
                if layer.mesh is None:
                    target = by_uuid.get(layer.target_layer_uuid)
                    if target is not None and target.mesh is not None:
                        layer.mesh = target.mesh
                        layer.transform = target.transform
                        layer._raw["parent_bone"] = target._raw.get("parent_bone", -1)
                        layer._raw["flexi_bone_subset"] = target._raw.get("flexi_bone_subset", "")
                        layer._raw["origin"] = target._raw.get("origin")
                        resolved_any = True

    def walk(self) -> Iterator[tuple[tuple[Layer, ...], Layer]]:
        """Depth-first, file order (back to front - Moho's own draw order).
        Yields (ancestor_chain, layer); ancestor_chain is root-first and does
        not include `layer` itself."""
        def _walk(layers: list[Layer], path: tuple[Layer, ...]):
            for layer in layers:
                yield path, layer
                if layer.children:
                    yield from _walk(layer.children, path + (layer,))
        yield from _walk(self.layers, ())

    def vector_layers(self) -> list[tuple[tuple[Layer, ...], Layer]]:
        """Every layer that carries a Mesh (i.e. can actually be exported)."""
        return [(parents, layer) for parents, layer in self.walk() if layer.mesh is not None]

    def find_vector_layer(self, name: str) -> Optional[tuple[tuple[Layer, ...], Layer]]:
        for parents, layer in self.vector_layers():
            if layer.name == name:
                return parents, layer
        return None


# ============================================================================
# ==== CURVE RECONSTRUCTION  (-> curve.go)                               ====
# ============================================================================

@dataclass(frozen=True)
class SegmentGeometry:
    """One cubic Bezier segment, fully evaluated at some frame: an SVG "C"
    command's worth of data, plus whether Moho currently hides this specific
    segment (`on` - see CurvePoint.segments_on)."""
    p0: Vec2
    c1: Vec2
    c2: Vec2
    p1: Vec2
    on: bool


class CurveGeometry:
    """The evaluated geometry of one Curve at one frame: every segment as a
    ready-to-draw SegmentGeometry, plus that curve's own points' widths (for
    TaperedStrokeOutliner) - self-contained, with no further need to consult
    the raw document."""

    def __init__(self, closed: bool, segments: list[SegmentGeometry], point_widths: list[float]):
        self.closed = closed
        self.segments = segments
        self.point_widths = point_widths   # parallel to the curve's OWN point
                                             # list (curve.points), not the
                                             # mesh's - index accordingly.

    def segment_count(self) -> int:
        return len(self.segments)

    @staticmethod
    def build(curve: Curve, positions: list[Vec2], reconstructor: "BezierReconstructor",
              frame: float, exporter: "Exporter", point_widths: list[float]) -> "CurveGeometry":
        n = len(curve.points)
        segments = []
        for s in range(curve.segment_count()):
            i, j = s, (s + 1) % n
            segments.append(SegmentGeometry(
                p0=positions[curve.points[i].point_index],
                p1=positions[curve.points[j].point_index],
                c1=reconstructor.handle(curve, positions, i, False, frame, exporter),
                c2=reconstructor.handle(curve, positions, j, True, frame, exporter),
                on=curve.points[i].segments_on,
            ))
        return CurveGeometry(curve.closed, segments, point_widths)


class BezierReconstructor:
    """Turns Moho's curvature/weight/offset representation of a curve point
    into the explicit Bezier control point either side of it.  See the module
    docstring's BEZIER CURVES section for the formulas and how `tangent_bias`
    was derived; the confirmed handle-length formula and the empirically-fit
    tangent-direction formula are both implemented in `handle` below.
    """

    def __init__(self, tangent_bias: float):
        self.tangent_bias = tangent_bias

    def handle(self, curve: Curve, positions: list[Vec2], index: int, incoming: bool,
               frame: float, exporter: "Exporter") -> Vec2:
        n = len(curve.points)
        cp = curve.points[index]
        p = positions[cp.point_index]

        clamp = (lambda k: (k + n) % n) if curve.closed else (lambda k: max(0, min(n - 1, k)))
        nxt, prv = clamp(index + 1), clamp(index - 1)
        second = prv if incoming else nxt
        if second == index:
            return p          # open-curve endpoint: no far side, handle collapses onto the point

        curvature = exporter.eval(cp.smoothness, frame)
        weight = exporter.eval(cp.weight_in if incoming else cp.weight_out, frame)
        offset = exporter.eval(cp.offset_in if incoming else cp.offset_out, frame)
        a = positions[curve.points[nxt].point_index]
        b = positions[curve.points[prv].point_index]

        # Tangent direction: chord-length-weighted blend of the two unit chord
        # vectors, NOT plain normalize(a - b) - see the module docstring.
        u, v = p - b, a - p
        du, dv = u.length(), v.length()
        if du < 1e-12 or dv < 1e-12:
            direction = (a - b).normalized()
        else:
            direction = (u.scaled(dv ** self.tangent_bias / du)
                         + v.scaled(du ** self.tangent_bias / dv)).normalized()
        if incoming:
            direction = direction.scaled(-1.0)

        # Handle length: confirmed exact (median ratio 1.0000 against 209
        # reference handles) - see the module docstring.
        neighbour = positions[curve.points[second].point_index]
        handle_length = p.distance_to(neighbour) * curvature * weight
        return p + direction.scaled(handle_length).rotated(offset)


# ============================================================================
# ==== PATH TRACING & SVG PATH BUILDING  (-> pathtrace.go)               ====
# ============================================================================

@dataclass(frozen=True)
class TracedSegment:
    """One segment of a shape's outline, in walk order, as PathTracer produces
    it.  `reversed` records whether this segment's points were swapped
    relative to how they are stored in its CurveGeometry - callers that need
    to know which original endpoint is which (TaperedStrokeOutliner, to swap
    its start/end width) use this explicit flag rather than comparing point
    values or identities, so the result stays correct however coordinates were
    computed and translates directly to a language without Python's tuple
    identity semantics."""
    p0: Vec2
    c1: Vec2
    c2: Vec2
    p1: Vec2
    is_new_subpath: bool
    reversed: bool
    curve: int
    segment: int


class PathTracer:
    """Rebuilds the walk order of a shape's outline from its edge list.

    A shape's `edges` are not reliably a walk in list order, and the stored
    per-edge `flag` is not a reliable direction bit either - see the module
    docstring's SHAPES, EDGES... section.  So: treat every segment as an edge
    of an undirected graph keyed by its (rounded) endpoint coordinates, and
    trace connected runs.  Traces are seeded preferring an endpoint that only
    touches one segment (a true open end) over one that touches several (a
    junction), so junctions get absorbed naturally mid-trace rather than
    becoming an arbitrary new subpath boundary.
    """

    @staticmethod
    def trace(geometries: list[CurveGeometry], edges: Sequence[Edge]) -> list[TracedSegment]:
        segs = [(geometries[e.curve].segments[e.segment], e.curve, e.segment) for e in edges]

        adjacency: dict[tuple[float, float], list[int]] = {}
        for i, (sg, _c, _s) in enumerate(segs):
            adjacency.setdefault(sg.p0.rounded_key(), []).append(i)
            adjacency.setdefault(sg.p1.rounded_key(), []).append(i)
        used = [False] * len(segs)

        def take(i: int, at: tuple[float, float]):
            used[i] = True
            sg, c, s = segs[i]
            if sg.p0.rounded_key() == at:
                return (sg.p0, sg.c1, sg.c2, sg.p1, False, c, s), sg.p1.rounded_key()
            return (sg.p1, sg.c2, sg.c1, sg.p0, True, c, s), sg.p0.rounded_key()

        out: list[TracedSegment] = []
        order = sorted(range(len(segs)),
                        key=lambda i: (len(adjacency[segs[i][0].p0.rounded_key()]) > 1, i))
        for seed in order:
            if used[seed]:
                continue
            (p0, c1, c2, p1, rev, c, s), at = take(seed, segs[seed][0].p0.rounded_key())
            out.append(TracedSegment(p0, c1, c2, p1, True, rev, c, s))
            while True:
                nxt = next((j for j in adjacency.get(at, []) if not used[j]), None)
                if nxt is None:
                    break
                (p0, c1, c2, p1, rev, c, s), at = take(nxt, at)
                out.append(TracedSegment(p0, c1, c2, p1, False, rev, c, s))
        return out


def cubic_bezier_point(p0: Vec2, c1: Vec2, c2: Vec2, p1: Vec2, t: float) -> Vec2:
    u = 1.0 - t
    return Vec2(
        u*u*u*p0.x + 3*u*u*t*c1.x + 3*u*t*t*c2.x + t*t*t*p1.x,
        u*u*u*p0.y + 3*u*u*t*c1.y + 3*u*t*t*c2.y + t*t*t*p1.y,
    )


def build_path_d(geometries: list[CurveGeometry], edges: Sequence[Edge],
                  to_px: Callable[[Vec2], Vec2], visible_only: bool = False,
                  close: bool = True) -> str:
    """Build one shape's SVG path data ("d" attribute) from its (unordered)
    edge list.

    `visible_only`, when set, skips any segment currently hidden (see
    CurvePoint.segments_on / SegmentGeometry.on) and starts a fresh subpath
    after each such gap, which is what produces a visibly dashed/gapped
    outline for a shape like an umbrella panel that only shows part of its
    boundary as a drawn line.

    `close` appends "Z" to close a finished subpath whose end coincides with
    its start.  Pass close=True for fills; NEVER for a plain (non-tapered)
    stroke - see the module docstring's FILL RULE... section for why Moho's
    own exporter never closes a stroke path either.
    """
    traced = PathTracer.trace(geometries, edges)
    d: list[str] = []
    first: Optional[Vec2] = None
    last: Optional[Vec2] = None
    for seg in traced:
        if visible_only and not geometries[seg.curve].segments[seg.segment].on:
            last = None
            continue
        if last is None or last.distance_to(seg.p0) > 1e-9:
            if close and first is not None and last is not None and last.distance_to(first) < 1e-9:
                d.append("Z")
            m = to_px(seg.p0)
            d.append(f"M {m.x:.3f} {m.y:.3f}")
            first = seg.p0
        c1, c2, p1 = to_px(seg.c1), to_px(seg.c2), to_px(seg.p1)
        d.append(f"C {c1.x:.3f} {c1.y:.3f} {c2.x:.3f} {c2.y:.3f} {p1.x:.3f} {p1.y:.3f}")
        last = seg.p1
    if close and first is not None and last is not None and last.distance_to(first) < 1e-9:
        d.append("Z")
    return " ".join(d)


class TaperedStrokeOutliner:
    """Builds the *filled outline* of a stroke whose width varies along its
    length, since SVG's own <path stroke-width> cannot - see the module
    docstring's TAPERED STROKES section.
    """

    def __init__(self, samples_per_segment: int = 10):
        self.samples_per_segment = samples_per_segment

    def build(self, geometries: list[CurveGeometry], edges: Sequence[Edge],
              to_px: Callable[[Vec2], Vec2], stroke_width_px: float) -> str:
        traced = PathTracer.trace(geometries, edges)

        Run = list[tuple[Vec2, Vec2, Vec2, Vec2, float, float]]
        runs: list[Run] = []
        current: Run = []
        for seg in traced:
            cg = geometries[seg.curve]
            if not cg.segments[seg.segment].on:
                if current:
                    runs.append(current)
                    current = []
                continue
            widths = cg.point_widths
            w0, w1 = widths[seg.segment], widths[(seg.segment + 1) % len(widths)]
            if seg.reversed:
                w0, w1 = w1, w0
            if current and current[-1][3].distance_to(seg.p0) > 1e-9:
                runs.append(current)
                current = []
            current.append((seg.p0, seg.c1, seg.c2, seg.p1, w0, w1))
        if current:
            runs.append(current)

        pieces = [self._outline_one_run(run, to_px, stroke_width_px) for run in runs]
        return " ".join(p for p in pieces if p)

    def _outline_one_run(self, run, to_px: Callable[[Vec2], Vec2],
                          stroke_width_px: float) -> str:
        steps = self.samples_per_segment
        samples: list[tuple[Vec2, float]] = []
        for p0, c1, c2, p1, w0, w1 in run:
            for i in range(steps + 1):
                t = i / steps
                point = cubic_bezier_point(p0, c1, c2, p1, t)
                if i == 0 and samples and samples[-1][0].distance_to(point) < 1e-12:
                    continue
                samples.append((point, w0 + (w1 - w0) * t))
        pixels = [(to_px(p), w) for p, w in samples]
        n = len(pixels)
        if n < 2:
            return ""

        left: list[Vec2] = []
        right: list[Vec2] = []
        for i, (p, w) in enumerate(pixels):
            a = pixels[max(0, i - 1)][0]
            b = pixels[min(n - 1, i + 1)][0]
            tangent = b - a
            length = tangent.length() or 1.0
            normal = Vec2(-tangent.y / length, tangent.x / length)
            half = stroke_width_px * w / 2.0
            left.append(p + normal.scaled(half))
            right.append(p - normal.scaled(half))

        closed = run[0][0].distance_to(run[-1][3]) < 1e-9 and len(run) > 1
        if closed:
            # A ring: two counter-wound loops combined with fill-rule=evenodd.
            # A single continuous outline would self-overlap at the seam
            # instead of leaving the expected hole down the middle.
            left_loop = "M " + " L ".join(f"{p.x:.2f} {p.y:.2f}" for p in left) + " Z"
            right_loop = "M " + " L ".join(f"{p.x:.2f} {p.y:.2f}" for p in reversed(right)) + " Z"
            return f"{left_loop} {right_loop}"

        d = [f"M {left[0].x:.2f} {left[0].y:.2f}"]
        d += [f"L {p.x:.2f} {p.y:.2f}" for p in left[1:]]
        end_radius = stroke_width_px * pixels[-1][1] / 2.0
        if end_radius > 0.05:
            d.append(f"A {end_radius:.2f} {end_radius:.2f} 0 0 1 "
                     f"{right[-1].x:.2f} {right[-1].y:.2f}")
        d += [f"L {p.x:.2f} {p.y:.2f}" for p in reversed(right[:-1])]
        start_radius = stroke_width_px * pixels[0][1] / 2.0
        if start_radius > 0.05:
            d.append(f"A {start_radius:.2f} {start_radius:.2f} 0 0 1 "
                     f"{left[0].x:.2f} {left[0].y:.2f}")
        d.append("Z")
        return " ".join(d)


@dataclass(frozen=True)
class BrushDab:
    """One stamp of a textured brush stroke: a dab of `diameter_px` centred at
    `pos` (pixel space), rotated by `angle` radians, using `frame`-th image
    of the brush's frame list (0 for a single-image brush).  See the module
    docstring's BRUSH STROKES section and BrushStampOutliner.build."""
    pos: Vec2
    angle: float
    diameter_px: float
    frame: int = 0


@dataclass(frozen=True)
class BrushTexture:
    """One dab image of a brush: the raw PNG bytes plus its pixel size.  A
    single-image brush has exactly one frame; a multi-frame brush has one per
    PNG in its folder - see the module docstring's BRUSH STROKES section."""
    data: bytes
    width: int
    height: int


@dataclass(frozen=True)
class Brush:
    """A brush asset resolved from `--brush-dir` for one style's brush_name:
    `frames` are its dab images, `random_order`/`random_interval` are the
    library defaults read from the brush's ".mohobrush" sidecar and control
    which frame each dab stamps - see the module docstring's BRUSH STROKES
    section and Exporter._resolve_brush_asset."""
    frames: tuple[BrushTexture, ...]
    random_order: bool
    random_interval: int


@dataclass(frozen=True)
class RegisteredBrush:
    """A Brush plus the SVG <mask> defs registered for each of its frames:
    `mask_refs[i]` is (mask_id, width_px, height_px) for `frames[i]` - see
    Exporter._brush_mask_refs."""
    mask_refs: tuple[tuple[str, int, int], ...]
    random_order: bool
    random_interval: int


class BrushStampOutliner:
    """Samples a traced path into a series of BrushDab, approximating Moho's
    own textured/dab brush strokes - see the module docstring's BRUSH STROKES
    section for the algorithm and its known simplifications.
    """

    def __init__(self, samples_per_segment: int = 12):
        self.samples_per_segment = samples_per_segment

    def build(self, geometries: list[CurveGeometry], edges: Sequence[Edge],
              to_px: Callable[[Vec2], Vec2], diameter_px: float, spacing_frac: float,
              align: bool, jitter: float, seed: Any, frame_count: int = 1,
              random_order: bool = True, random_interval: int = 1,
              spacing_scale: float = 1.0) -> list[BrushDab]:
        """Sample the traced path into dabs.  `frame_count` > 1 makes each dab
        carry the index of the frame to stamp (see BrushDab.frame): with
        `random_order` a uniform-random frame is picked per dab (from the same
        seeded RNG as the rotation jitter, so re-running the exporter
        reproduces the same output); without it, frames cycle in order,
        advancing every `random_interval` dabs across the whole shape.

        `spacing_scale` (--brush-spacing-mul) multiplies the computed spacing
        uniformly - a document-wide performance knob, not something read from
        the project file: a real document's own `brush_spacing` is very
        often already the dominant term (0.25-0.5 in every rig this tool has
        been tested against, i.e. already well above the "no smaller than 5%
        of diameter" safety floor below), so it is what actually needs
        scaling to meaningfully cut dab count on a document with heavy brush
        usage - raising just the internal floor would do nothing for those
        (confirmed: every brush-styled shape in the SketchBone rig has
        brush_spacing >= 0.25, nowhere near the floor). Default 1.0
        reproduces the exact previous dab count/placement.

        Each dab's actual diameter is `diameter_px` scaled by the *locally
        interpolated* per-point width (CurveGeometry.point_widths) at that
        dab's position - exactly the same width channel TaperedStrokeOutliner
        uses to taper its ribbon, applied here per-dab instead.  `diameter_px`
        must therefore be the width-1.0 base (Exporter._stroke_width_px with
        point_width=1.0), not a shape's own already-baked-in uniform width -
        see the module docstring's BRUSH STROKES section for why a tapered,
        brush-styled shape needs this rather than falling back to
        TaperedStrokeOutliner's flat, untextured ribbon."""
        traced = PathTracer.trace(geometries, edges)

        runs: list[list[tuple[Vec2, Vec2, Vec2, Vec2, float, float]]] = []
        current: list[tuple[Vec2, Vec2, Vec2, Vec2, float, float]] = []
        for seg in traced:
            cg = geometries[seg.curve]
            if not cg.segments[seg.segment].on:
                if current:
                    runs.append(current)
                    current = []
                continue
            widths = cg.point_widths
            w0, w1 = widths[seg.segment], widths[(seg.segment + 1) % len(widths)]
            if seg.reversed:
                w0, w1 = w1, w0
            if current and current[-1][3].distance_to(seg.p0) > 1e-9:
                runs.append(current)
                current = []
            current.append((seg.p0, seg.c1, seg.c2, seg.p1, w0, w1))
        if current:
            runs.append(current)

        # random.Random(str) hashes deterministically (unlike builtin hash(),
        # which is salted per-process) - re-running on the same document must
        # reproduce the same jitter, not a new one every time.
        rng = random.Random(str(seed))
        # Frame picking per dab (see the build() docstring).  The cycle
        # counter is shared across the whole path (all runs), not reset per
        # run, so a long outline moves through the whole frame sequence.
        dab_index = 0

        def next_frame() -> int:
            nonlocal dab_index
            if frame_count <= 1:
                return 0
            if random_order:
                return rng.randrange(frame_count)
            frame = (dab_index // max(1, random_interval)) % frame_count
            dab_index += 1
            return frame

        # Clamp: a brush_spacing of 0 (or a tiny fraction) would otherwise mean
        # "infinite dabs" - not a real Moho setting, just defensive.  Spacing
        # IS re-scaled per-step by the local width (same as each dab's own
        # diameter): a point-width channel is not always a mild near-1.0
        # taper - some shapes (e.g. the "golge" shadow strokes in the
        # SketchBone rig) use it to swing a stroke's width by an order of
        # magnitude (~12x-19x) on purpose, to draw a soft shadow band as one
        # thick brushed line rather than a filled shape.  Spacing computed
        # once from the width-1.0 base (as an earlier version of this method
        # did) does not scale with that - dabs 12-19x the intended size would
        # still be spaced as if they were tiny, overlapping 30-50 deep and
        # rendering far denser/thicker than Moho's own output.  Recomputing
        # spacing from each dab's own local diameter keeps the same
        # brush_spacing *ratio* (gap as a fraction of dab size) everywhere
        # along the path, however extreme the taper.
        half_jitter = jitter / 2.0
        dabs: list[BrushDab] = []
        for run in runs:
            samples: list[tuple[Vec2, float]] = []
            for p0, c1, c2, p1, w0, w1 in run:
                for i in range(self.samples_per_segment + 1):
                    t = i / self.samples_per_segment
                    point = cubic_bezier_point(p0, c1, c2, p1, t)
                    if i == 0 and samples and samples[-1][0].distance_to(point) < 1e-12:
                        continue
                    samples.append((point, w0 + (w1 - w0) * t))
            pixels = [(to_px(p), w) for p, w in samples]
            n = len(pixels)
            if n < 2:
                if n == 1:
                    p, w = pixels[0]
                    dabs.append(BrushDab(p, rng.uniform(-half_jitter, half_jitter),
                                         diameter_px * w, next_frame()))
                continue
            carry = 0.0
            for i in range(n - 1):
                (a, wa), (b, wb) = pixels[i], pixels[i + 1]
                seg_len = a.distance_to(b)
                if seg_len <= 1e-9:
                    continue
                tangent_angle = math.atan2(b.y - a.y, b.x - a.x) if align else 0.0
                dist = carry
                while dist < seg_len:
                    t = dist / seg_len
                    pos = a + (b - a).scaled(t)
                    w = wa + (wb - wa) * t
                    local_diameter = diameter_px * w
                    spacing = max(local_diameter * spacing_frac,
                                 local_diameter * 0.05, 0.5) * spacing_scale
                    angle = tangent_angle + rng.uniform(-half_jitter, half_jitter)
                    dabs.append(BrushDab(pos, angle, local_diameter, next_frame()))
                    dist += spacing
                carry = dist - seg_len
        return dabs


# ============================================================================
# ==== BONE DEFORMATION ("SKINNING")  (-> skin.go)                       ====
# ============================================================================

BoneWeightFalloff = Callable[[float, float], float]

BONE_WEIGHT_FALLOFFS: dict[str, BoneWeightFalloff] = {
    # Each takes (distance_to_bone_segment, bone.strength).  See the module
    # docstring's BONE DEFORMATION section: "inv_d2" is the one actually used
    # (RenderSettings.bone_weight_falloff default); the others are recorded
    # because they were tried during development and could not be told apart
    # from "inv_d2" by any available reference - not because they are known to
    # be equally valid.
    "inv_d2":  lambda d, strength: 1.0 / max(d, 1e-6) ** 2,
    "linear":  lambda d, strength: max(0.0, 1.0 - d / strength) if strength > 0 else 0.0,
    "cut_d2":  lambda d, strength: (1.0 / max(d, 1e-6) ** 2
                                     if strength > 0 and d < strength else 0.0),
    "hermite": lambda d, strength: ((lambda u: (1 - u) ** 2 * (1 + 2 * u))(min(1.0, d / strength))
                                     if strength > 0 else 0.0),
}


@dataclass(frozen=True)
class SkinBone:
    """One bone's precomputed contribution to Skinner.deform: its rest-pose
    segment endpoints (for measuring distance) and the transform that carries
    a point from rest-pose world space to posed world space."""
    rest_p0: Vec2
    rest_p1: Vec2
    strength: float
    rest_to_pose: Mat2D


class Skinner:
    """Precomputed per-bone rest/pose data for one Skeleton at one frame (and
    Smart Bone action context - see Exporter._skin_data, which is what
    actually calls Skinner.build and caches the result, since the same
    Skinner is reused for every point of a mesh)."""

    def __init__(self, bones: list[SkinBone]):
        self.bones = bones

    @staticmethod
    def build(skeleton: Skeleton, frame: float, exporter: "Exporter") -> "Skinner":
        rest = skeleton.world_matrices(0.0, exporter)
        pose = skeleton.world_matrices(frame, exporter)
        bones = []
        for i, bone in enumerate(skeleton.bones):
            rest_p0 = rest[i].apply(Vec2(0.0, 0.0))
            rest_p1 = rest[i].apply(Vec2(bone.length, 0.0))
            rest_to_pose = pose[i].compose(rest[i].inverse())
            bones.append(SkinBone(rest_p0, rest_p1, bone.strength, rest_to_pose))
        return Skinner(bones)

    @staticmethod
    def _distance_to_segment(p: Vec2, a: Vec2, b: Vec2) -> float:
        ab = b - a
        span = ab.dot(ab)
        t = 0.0 if span == 0 else max(0.0, min(1.0, (p - a).dot(ab) / span))
        return p.distance_to(a + ab.scaled(t))

    def deform(self, p: Vec2, subset: Sequence[int], weight_fn: BoneWeightFalloff) -> Vec2:
        """Blend the rest_to_pose transform of every (subset-restricted, if
        `subset` is non-empty) bone, weighted by `weight_fn`.  A bone with
        strength <= 0 never contributes at all, regardless of weight_fn or
        distance - this is Moho's own "this bone does not deform this mesh"
        gate, and is checked first."""
        indices: Iterable[int] = subset if subset else range(len(self.bones))
        total = 0.0
        acc = Vec2(0.0, 0.0)
        for i in indices:
            bone = self.bones[i]
            if bone.strength <= 0:
                continue
            w = weight_fn(self._distance_to_segment(p, bone.rest_p0, bone.rest_p1), bone.strength)
            if w <= 0:
                continue
            acc = acc + bone.rest_to_pose.apply(p).scaled(w)
            total += w
        return acc.scaled(1.0 / total) if total > 0 else p


@dataclass(frozen=True)
class MatrixStep:
    """One step of a DeformChain: apply a plain affine transform."""
    matrix: Mat2D


@dataclass(frozen=True)
class SkinStep:
    """One step of a DeformChain: cross into `bone_layer`'s own coordinate
    space, deforming the point by its skeleton.

    `bound_bone_index` >= 0 means the layer ultimately being rendered is
    *rigidly* bound to that one bone (Layer.parent_bone); -1 means flexible
    ("region") binding, blended across every bone (or the layer's own
    flexi_bone_subset, if narrower) - see Exporter._deformed_pixel_mapper,
    which is where that distinction is actually consumed.
    """
    bone_layer: Layer
    bound_bone_index: int


DeformStep = Union[MatrixStep, SkinStep]


def build_deform_chain(ancestors: Sequence[Layer], target: Layer, frame: float,
                        exporter: "Exporter") -> list[DeformStep]:
    """Build the ordered list of steps that maps a point in `target`'s own
    local coordinates all the way out to document space, INCLUDING bone
    deformation - i.e. the deformation-aware counterpart of composing
    Layer.local_matrix up the ancestor chain.

    Steps are built innermost-first conceptually but returned in APPLICATION
    order (apply steps[0] to the raw point, then steps[1], and so on).  A mesh
    several groups deep inside a BoneLayer is deformed in *that bone layer's*
    coordinate space - i.e. after the local transforms of everything between
    it and the bone layer, but before the bone layer's own transform - because
    that is the space its skeleton's rest/pose matrices are expressed in.
    """
    steps: list[DeformStep] = []
    pending = IDENTITY_MATRIX          # matrix steps not yet flushed, composed outer-most-last
    chain = list(ancestors) + [target]
    bound = -1
    for layer in reversed(chain):
        is_deforming_bone_layer = (layer is not target and layer.skeleton is not None
                                    and layer.kind is LayerKind.BONE)
        if is_deforming_bone_layer:
            steps.append(MatrixStep(pending))
            steps.append(SkinStep(layer, bound))
            pending = layer.local_matrix(frame, exporter)
            bound = -1
        else:
            if layer.parent_bone >= 0:
                bound = layer.parent_bone
            pending = layer.local_matrix(frame, exporter).compose(pending)
    steps.append(MatrixStep(pending))
    return steps


# ============================================================================
# ==== SMALL SVG UTILITIES  (-> shared helpers in whichever Go file    ) ====
# ============================================================================

_XML_ESCAPE_TABLE = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})


def svg_escape(text: Any) -> str:
    return str(text).translate(_XML_ESCAPE_TABLE)


def sanitize_filename(name: Any) -> str:
    s = re.sub(r"[^\w.\- ]+", "_", str(name)).strip().replace(" ", "_")
    return s or "layer"


def parse_path_bbox(paths: Sequence[str], pad: float = 50.0) -> tuple[float, float, float, float]:
    """Parse the numbers out of one or more SVG path "d" strings and return a
    padded (x, y, width, height) bounding box.  Used only for sizing the small
    local <mask> elements built for masking (both the cross-layer kind in
    Exporter._mask_element and the within-layer boolean-combination kind in
    ShapeGroupRenderer) - at that point only rendered path *text* is on hand,
    not the original point list, so parsing it back out is simpler than
    re-deriving the same bounds from geometry a second time."""
    numbers = [float(v) for d in paths for v in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", d)]
    xs, ys = numbers[0::2], numbers[1::2]
    return (min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)


def png_dimensions(data: bytes) -> tuple[int, int]:
    """(width, height) of a PNG file's pixels, read directly from its IHDR
    chunk - avoids a Pillow/image-library dependency for the one thing
    BrushStampOutliner needs to know about a brush texture (see BRUSH
    STROKES).  The IHDR chunk is always the first chunk, immediately after
    the fixed 8-byte PNG signature: 4-byte length + 4-byte "IHDR" + 4-byte
    width + 4-byte height, both big-endian."""
    return struct.unpack(">II", data[16:24])


# ============================================================================
# ==== RENDER SETTINGS  (-> render.go: fields of an Exporter/Options)    ====
# ============================================================================

@dataclass
class RenderSettings:
    """Tunable constants controlling how a Document is rendered.  Everything
    here except `bone_weight_falloff`, `bezier_samples_per_segment`,
    `mask_padding` and `viewbox_padding` corresponds to a CLI flag (see
    main()); those four have never needed adjusting against a real reference
    document and so were never wired up to one."""
    stroke_width_scale: float = 2.0          # --stroke-mul; Exporter._stroke_width_px
    tangent_bias: float = 0.19                 # BezierReconstructor
    bone_weight_falloff: str = "inv_d2"          # key into BONE_WEIGHT_FALLOFFS
    forced_mask_containers: frozenset[str] = field(default_factory=frozenset)  # --mask-container
    bezier_samples_per_segment: int = 10           # TaperedStrokeOutliner
    mask_padding: float = 50.0
    viewbox_padding: float = 8.0
    brush_dir: Optional[str] = None          # --brush-dir; BrushStampOutliner / Exporter._brush_mask_refs
    brush_samples_per_segment: int = 12          # BrushStampOutliner
    brush_spacing_mul: float = 1.0          # --brush-spacing-mul; BrushStampOutliner.build's spacing_scale
    brush_raster: bool = False          # --brush-raster; Exporter._raster_brush_shape (requires Pillow)
    brush_raster_max_pixels: int = 16_000_000  # safety cap; falls back to per-dab <use> above this
    brush_raster_supersample: float = 2.0    # --brush-raster-supersample; canvas oversampling factor


# ============================================================================
# ==== EXPORTER  (-> render.go: the only stateful piece)                 ====
# ============================================================================

class Exporter:
    """Renders a Document to SVG.

    Exporter is deliberately the only stateful class in this file: it caches
    per-(bone layer, frame, active-Smart-Bone-context) Skinner objects
    (`_skin_cache`) and a monotonically increasing id counter for <mask>/
    <linearGradient>/... def elements (`_next_id`), both of which are scoped
    to *one call* to export_layer or export_document.  It is NOT safe to
    reuse concurrently for overlapping exports - construct one Exporter per
    export call (or per goroutine, in a Go port) instead of sharing one.
    `_active_actions` and `_layer_scale` are likewise per-call scratch state,
    set immediately before rendering a given layer's shapes and cleared
    immediately after - mirroring (deliberately) how the very first version
    of this tool managed the same information as plain module-level globals;
    see export_layer/export_document for exactly where each is set/cleared,
    since a couple of behaviours (see _mask_sources) depend on the exact
    ordering.
    """

    def __init__(self, document: Document, settings: Optional[RenderSettings] = None):
        self.document = document
        self.settings = settings or RenderSettings()
        self.bezier = BezierReconstructor(self.settings.tangent_bias)
        self.tapered_outliner = TaperedStrokeOutliner(self.settings.bezier_samples_per_segment)
        self.brush_outliner = BrushStampOutliner(self.settings.brush_samples_per_segment)
        self._skin_cache: dict[tuple[Layer, float, tuple[ActiveAction, ...]], Skinner] = {}
        self._next_id = 0
        self._active_actions: list[ActiveAction] = []
        self._layer_scale: float = 1.0
        self._brush_asset_cache: dict[str, Optional["Brush"]] = {}  # brush_name -> resolved asset (or None)
        self._brush_defs: list[str] = []             # <filter>/<mask> defs, emitted once per export (mask path)
        self._brush_refs: dict[str, Optional[RegisteredBrush]] = {}  # brush_name -> registered brush (or None)
        self._brush_tinted_defs: list[str] = []       # <image> defs, emitted once per export (tint path)
        self._brush_tinted_ids: dict[tuple, Optional[tuple[str, int, int]]] = {}  # see _brush_tinted_ref

    # -- channel evaluation --------------------------------------------------

    def eval(self, raw: Any, frame: float) -> Any:
        """The value of animated field `raw` at `frame`, honouring whichever
        Smart Bone dials are currently active (self._active_actions)."""
        return Channel.of(raw).eval(frame, self._active_actions)

    def eval_raw(self, raw: Any, frame: float) -> Any:
        """As eval(), but ignoring any active Smart Bone override - see
        Channel.eval_raw and the module docstring's SMART BONES section for
        the one place this distinction matters (a dial's own current angle)."""
        return Channel.of(raw).eval_raw(frame)

    # -- Smart Bones ----------------------------------------------------------

    def _active_smart_bones(self, bone_layer: Layer, frame: float) -> list[ActiveAction]:
        """Which of `bone_layer`'s own dial bones are active, and at what
        pose-frame - see the module docstring's SMART BONES section."""
        names = bone_layer.action_names
        skeleton = bone_layer.skeleton
        out: list[ActiveAction] = []
        if skeleton is None:
            return out
        for bone in skeleton.bones:
            if bone.name not in names:
                continue
            angle_channel = Channel.of(bone.anim_angle)
            current = angle_channel.eval_raw(frame)      # deliberately NOT eval() - see module docstring
            best_action: Optional[ActionRef] = None
            best_key: Optional[tuple[float, float]] = None
            for action in angle_channel.actions:
                if action.name not in names:
                    continue
                values = action.pose.val
                lo, hi = min(values), max(values)
                span = hi - lo
                if span < 1e-9:
                    continue
                inside = lo - 1e-9 <= current <= hi + 1e-9
                distance = 0.0 if inside else min(abs(current - lo), abs(current - hi))
                key = (distance, -span)          # closest first, then widest span
                if best_key is None or key < best_key:
                    best_key, best_action = key, action
            if best_action is not None:
                out.append(ActiveAction(best_action.name, best_action.pose.frame_for_value(current)))
        return out

    def _active_actions_along(self, ancestors: Sequence[Layer], frame: float) -> list[ActiveAction]:
        """Every active dial from every BoneLayer ancestor in `ancestors`
        (root-first - so an outer ancestor's dial takes priority over an
        inner one's, in the unlikely event two dials share a name and both
        happen to affect the same channel; see Channel.eval)."""
        actions: list[ActiveAction] = []
        for layer in ancestors:
            if layer.kind is LayerKind.BONE and layer.skeleton is not None:
                actions += self._active_smart_bones(layer, frame)
        return actions

    # -- curve geometry --------------------------------------------------------

    def _curve_geometries(self, mesh: Mesh, frame: float) -> list[CurveGeometry]:
        positions = [Vec2.of(self.eval(p.position, frame)) for p in mesh.points]
        out = []
        for curve in mesh.curves:
            widths = [self.eval(mesh.points[cp.point_index].width, frame) for cp in curve.points]
            out.append(CurveGeometry.build(curve, positions, self.bezier, frame, self, widths))
        return out

    # -- bone deformation --------------------------------------------------------

    def _skin_data(self, bone_layer: Layer, frame: float) -> Skinner:
        key = (bone_layer, frame, tuple(self._active_actions))
        cached = self._skin_cache.get(key)
        if cached is None:
            cached = Skinner.build(bone_layer.skeleton, frame, self)
            self._skin_cache[key] = cached
        return cached

    def _to_pixel(self, p: Vec2) -> Vec2:
        """Moho-space -> pixel-space: 2 units span the canvas height, and y is
        flipped (Moho's +y is up; SVG's is down).  See the module docstring's
        COORDINATES section."""
        s = self.document.height / 2.0
        return Vec2(p.x * s + self.document.width / 2.0, self.document.height / 2.0 - p.y * s)

    def _plain_pixel_mapper(self, matrix: Mat2D) -> Callable[[Vec2], Vec2]:
        """A point-mapper that applies one fixed matrix and no bone
        deformation at all - used for --local exports."""
        return lambda p: self._to_pixel(matrix.apply(p))

    def _deformed_pixel_mapper(self, chain: list[DeformStep], frame: float,
                                layer: Layer) -> Callable[[Vec2], Vec2]:
        """A point-mapper that walks a full DeformChain (ordinary transforms
        plus bone skinning) before projecting to pixel space."""
        subset = layer.flexi_bone_subset
        weight_fn = BONE_WEIGHT_FALLOFFS[self.settings.bone_weight_falloff]

        def to_px(p: Vec2) -> Vec2:
            for step in chain:
                if isinstance(step, MatrixStep):
                    p = step.matrix.apply(p)
                else:
                    skinner = self._skin_data(step.bone_layer, frame)
                    if step.bound_bone_index >= 0:
                        p = skinner.bones[step.bound_bone_index].rest_to_pose.apply(p)
                    else:
                        p = skinner.deform(p, subset, weight_fn)
            return self._to_pixel(p)

        return to_px

    def _full_chain_matrix(self, ancestors: Sequence[Layer], layer: Layer, frame: float) -> Mat2D:
        """The layer's full accumulated transform INCLUDING itself, ignoring
        bone deformation entirely - used only to measure the *layer* scale for
        stroke width (module docstring's STROKE WIDTH section: bone
        deformation must be excluded from that figure, confirmed separately
        by it inflating the apparent scale by ~11% on a walk-cycle test)."""
        m = IDENTITY_MATRIX
        for layer_in_chain in list(ancestors) + [layer]:
            m = m.compose(layer_in_chain.local_matrix(frame, self))
        return m

    def _stroke_width_px(self, line_width: float, point_width: float) -> float:
        """See the module docstring's STROKE WIDTH section."""
        return (line_width * point_width * self.settings.stroke_width_scale
                * self.document.height / 2.0 * self._layer_scale)

    # -- gradients ----------------------------------------------------------

    def _next_def_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _build_gradient(self, fill_style: dict, gradient_id: str, frame: float,
                         scale: float, rotation: float,
                         indent: str) -> tuple[Optional[str], Optional[str]]:
        """Build a <linearGradient>/<radialGradient> def from a named style's
        `fill_style` - see the module docstring's GRADIENTS section, including
        why the placement is only approximate."""
        stops = []
        for stop in fill_style.get("gradients") or []:
            location = self.eval(stop["location"], frame)
            color = Color.from_raw(self.eval(stop["color"], frame))
            stops.append(f'<stop offset="{location * 100:.2f}%" stop-color="{color.hex()}" '
                         f'stop-opacity="{color.a:.3f}"/>')
        if len(stops) < 2:
            return None, None
        # A shape-level centre offset is supported by the formula below but
        # nothing currently supplies a non-zero one (Shape carries no such
        # field) - kept at (0, 0) rather than removed, so a document that
        # does need it only requires threading the value in, not new math.
        cx, cy = 50.0, 50.0
        if fill_style.get("gradient_type") == 1:
            el = (f'{indent}<radialGradient id="{gradient_id}" cx="{cx:.2f}%" cy="{cy:.2f}%" '
                  f'r="{max(1.0, 50.0 * scale):.2f}%">{"".join(stops)}</radialGradient>')
        else:
            dx, dy = math.cos(rotation) * 50.0 * scale, -math.sin(rotation) * 50.0 * scale
            el = (f'{indent}<linearGradient id="{gradient_id}" x1="{cx - dx:.2f}%" '
                  f'y1="{cy - dy:.2f}%" x2="{cx + dx:.2f}%" y2="{cy + dy:.2f}%">'
                  f'{"".join(stops)}</linearGradient>')
        return el, f"url(#{gradient_id})"

    # -- brush textures -------------------------------------------------------

    def _get_brush_asset(self, brush_name: str) -> Optional["Brush"]:
        """`_resolve_brush_asset(brush_name)`, cached - shared by both render
        paths (mask/filter and pre-tinted) so a brush's file(s) are only ever
        read from disk once per export, however many styles/shapes use it."""
        if brush_name not in self._brush_asset_cache:
            self._brush_asset_cache[brush_name] = self._resolve_brush_asset(brush_name)
        return self._brush_asset_cache[brush_name]

    def _brush_mask_refs(self, brush_name: str) -> Optional[RegisteredBrush]:
        """The registered brush for a style's `brush_name` - its resolved
        asset PLUS one <mask> def per frame - or None when no asset can be
        resolved (the caller then falls back to a plain stroke).  See the
        module docstring's BRUSH STROKES section.

        This is the fallback render path, used only when Pillow is not
        installed (see _brush_tinted_ref for the preferred path when it is).
        The <mask>/<filter> defs are built at most once per brush per export
        (cached in self._brush_refs) and collected in self._brush_defs,
        which _wrap prepends to the document once rendering is done - shared
        by every shape/style that uses the same brush, however many that is.
        """
        if brush_name in self._brush_refs:
            return self._brush_refs[brush_name]
        result: Optional[RegisteredBrush] = None
        brush = self._get_brush_asset(brush_name)
        if brush is not None:
            refs: list[tuple[str, int, int]] = []
            for frame in brush.frames:
                b64 = base64.b64encode(frame.data).decode("ascii")
                if not self._brush_defs:
                    # Inverts RGB so a texture's dark "ink" pixels become the
                    # *visible* part of an SVG luminance mask (see BRUSH
                    # STROKES) - shared by every brush, defined once.
                    self._brush_defs.append(
                        '  <filter id="brush_ink_invert" x="0" y="0" width="1" height="1">\n'
                        '    <feColorMatrix type="matrix" values='
                        '"-1 0 0 0 1  0 -1 0 0 1  0 0 -1 0 1  0 0 0 1 0"/>\n'
                        '  </filter>')
                mask_id = f"brush_{self._next_def_id()}"
                width, height = frame.width, frame.height
                hw, hh = width / 2.0, height / 2.0
                self._brush_defs.append(
                    f'  <mask id="{mask_id}" maskUnits="userSpaceOnUse" '
                    f'x="{-hw:.1f}" y="{-hh:.1f}" width="{width}" height="{height}">\n'
                    f'    <image href="data:image/png;base64,{b64}" '
                    f'x="{-hw:.1f}" y="{-hh:.1f}" width="{width}" height="{height}" '
                    f'filter="url(#brush_ink_invert)"/>\n'
                    f'  </mask>')
                refs.append((mask_id, width, height))
            result = RegisteredBrush(tuple(refs), brush.random_order, brush.random_interval)
        self._brush_refs[brush_name] = result
        return result

    def _resolve_brush_asset(self, brush_name: str) -> Optional[Brush]:
        """Find the brush asset named by a style's `brush_name` under
        `--brush-dir`, trying, in order: an exact file, an exact folder, a
        recursive search for an exact file name (older documents name preset
        images that live one folder deep, e.g. Brush004/Brush549_1_50_50.png),
        and finally the same searches on the base name after stripping
        trailing "_<digits>" segments ("CK Ink Natural_2_1_0_0_0_0_0_0_0"
        names the folder "CK Ink Natural").  A folder brush's frames and
        library defaults come from the folder plus its ".mohobrush" sidecar
        (a ZIP containing brush.json) - see the module docstring's BRUSH
        STROKES section.  Returns None when the name resolves to nothing,
        and the caller falls back to a plain stroke.
        """
        brush_dir = self.settings.brush_dir
        if not brush_dir:
            return None
        for candidate in self._brush_name_candidates(brush_name):
            direct = os.path.join(brush_dir, candidate)
            if os.path.isfile(direct):
                with open(direct, "rb") as f:
                    raw = f.read()
                width, height = png_dimensions(raw)
                return Brush((BrushTexture(raw, width, height),), True, 1)
            if os.path.isdir(direct):
                frames = self._brush_folder_frames(direct)
                if frames:
                    random_order, interval = self._brush_library_defaults(brush_dir, candidate)
                    return Brush(frames, random_order, interval)
            hit = self._find_brush_file_recursive(brush_dir, candidate)
            if hit:
                with open(hit, "rb") as f:
                    raw = f.read()
                width, height = png_dimensions(raw)
                return Brush((BrushTexture(raw, width, height),), True, 1)
        return None

    @staticmethod
    def _brush_name_candidates(name: str) -> Iterator[str]:
        """`name` itself, then successive truncations stripping one trailing
        "_<digits>" segment at a time.  A trailing ".png" is split off first
        (and re-appended as a separate candidate after each strip) so suffix
        segments that sit *before* the extension are reachable too."""
        yield name
        stem = name[:-4] if name.lower().endswith(".png") else name
        while True:
            m = re.search(r"_\d+$", stem)
            if not m:
                return
            stem = stem[:m.start()]
            yield stem
            yield stem + ".png"

    @staticmethod
    def _find_brush_file_recursive(brush_dir: str, name: str) -> Optional[str]:
        """The first PNG file named exactly `name` anywhere under `brush_dir`.
        (The top level has already been checked by the caller, so this only
        matters for images one or more folders deep.)"""
        for root, _dirs, files in os.walk(brush_dir):
            if name in files and name.lower().endswith(".png"):
                return os.path.join(root, name)
        return None

    @staticmethod
    def _brush_folder_frames(folder: str) -> tuple[BrushTexture, ...]:
        """Every *.png in a multi-frame brush's folder, in sorted file-name
        order - the order a cycle-through-frames brush (randomOrder=false)
        stamps them in.  Non-PNG files in the folder are ignored."""
        frames: list[BrushTexture] = []
        for fname in sorted(os.listdir(folder)):
            if not fname.lower().endswith(".png"):
                continue
            with open(os.path.join(folder, fname), "rb") as f:
                raw = f.read()
            width, height = png_dimensions(raw)
            frames.append(BrushTexture(raw, width, height))
        return tuple(frames)

    @staticmethod
    def _brush_library_defaults(brush_dir: str, name: str) -> tuple[bool, int]:
        """(random_order, random_interval) - a folder brush's library
        defaults, read from its "<name>.mohobrush" sidecar (a ZIP whose
        brush.json holds them).  Falls back to (True, 1) - the behaviour of
        most of Moho's own shipped brushes - when the sidecar is absent or
        unreadable."""
        try:
            with zipfile.ZipFile(os.path.join(brush_dir, name + ".mohobrush")) as z:
                info = json.loads(z.read("brush.json"))
            return bool(info.get("randomOrder", True)), int(info.get("randomInterval", 1))
        except (OSError, zipfile.BadZipFile, KeyError, ValueError):
            return True, 1

    def _brush_dab_svg(self, dab: "BrushDab", mask_id: str, tex_w: int, tex_h: int,
                        hex_color: str, alpha: float, indent: str) -> str:
        """One dab's markup: a coloured rect the texture's own aspect ratio,
        scaled/rotated/positioned to `dab`, masked by the (already-registered)
        brush texture mask `mask_id`.  Fallback path - see _brush_use_svg for
        the preferred one, used whenever Pillow is available."""
        op = "" if alpha >= 1 else f' fill-opacity="{alpha:.3f}"'
        scale = dab.diameter_px / max(tex_w, tex_h)
        hw, hh = tex_w / 2.0, tex_h / 2.0
        return (f'{indent}<g transform="translate({dab.pos.x:.2f} {dab.pos.y:.2f}) '
                f'rotate({math.degrees(dab.angle):.2f}) scale({scale:.4f})" '
                f'mask="url(#{mask_id})">'
                f'<rect x="{-hw:.1f}" y="{-hh:.1f}" width="{tex_w}" height="{tex_h}" '
                f'fill="{hex_color}"{op}/></g>')

    def _brush_tinted_ref(self, brush_name: str, frame_index: int, hex_color: str,
                          alpha: float) -> Optional[tuple[str, int, int]]:
        """(image_id, width_px, height_px) for one frame of `brush_name`,
        pre-tinted to `hex_color`/`alpha` as a plain PNG - or None if Pillow
        is unavailable, the brush doesn't resolve, or `frame_index` is out of
        range.  This is the preferred render path (see BRUSH STROKES): baking
        colour into the pixels once per (brush, frame, colour, alpha)
        combination, cached in self._brush_tinted_ids and collected in
        self._brush_tinted_defs (which _wrap prepends to the document),
        means a dab is just a <use> referencing a plain <image> - no
        per-instance mask/filter compositing for a viewer to do."""
        if Image is None:
            return None
        key = (brush_name, frame_index, hex_color, round(alpha, 3))
        if key in self._brush_tinted_ids:
            return self._brush_tinted_ids[key]
        result: Optional[tuple[str, int, int]] = None
        brush = self._get_brush_asset(brush_name)
        if brush is not None and 0 <= frame_index < len(brush.frames):
            frame = brush.frames[frame_index]
            png_bytes = self._bake_tinted_frame(frame.data, hex_color, alpha)
            b64 = base64.b64encode(png_bytes).decode("ascii")
            image_id = f"tint_{self._next_def_id()}"
            width, height = frame.width, frame.height
            hw, hh = width / 2.0, height / 2.0
            self._brush_tinted_defs.append(
                f'  <image id="{image_id}" href="data:image/png;base64,{b64}" '
                f'x="{-hw:.1f}" y="{-hh:.1f}" width="{width}" height="{height}"/>')
            result = (image_id, width, height)
        self._brush_tinted_ids[key] = result
        return result

    @staticmethod
    def _bake_tinted_frame(raw_png: bytes, hex_color: str, alpha: float) -> bytes:
        """One brush texture frame, pre-rendered as a solid-`hex_color` PNG
        whose alpha channel is that frame's "ink density" (the same
        dark-pixel-is-opaque inversion the mask/filter path computes at
        render time via <feColorMatrix>, done once here instead) combined
        with the source image's own alpha channel (respects textures like
        "CK Ink DIFF SMASHER.png" that already carry transparency) and then
        `alpha`.  The result needs no mask or filter to render - a plain
        <image>/<use> already shows exactly the tinted, correctly-shaped
        dab."""
        im = Image.open(io.BytesIO(raw_png)).convert("RGBA")
        ink = ImageOps.invert(im.convert("RGB").convert("L"))
        combined_alpha = ImageChops.multiply(ink, im.getchannel("A"))
        if alpha < 0.999:
            combined_alpha = combined_alpha.point(lambda p: int(p * alpha))
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
        solid = Image.new("RGB", im.size, (r, g, b))
        solid.putalpha(combined_alpha)
        buf = io.BytesIO()
        solid.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    def _brush_use_svg(self, dab: "BrushDab", image_id: str, tex_w: int, tex_h: int,
                        indent: str) -> str:
        """One dab's markup for the pre-tinted render path: a <use> of the
        already-registered, already-coloured image `image_id`, scaled/rotated/
        positioned to `dab` - no mask or filter needed (see
        _brush_tinted_ref)."""
        scale = dab.diameter_px / max(tex_w, tex_h)
        return (f'{indent}<use href="#{image_id}" '
                f'transform="translate({dab.pos.x:.2f} {dab.pos.y:.2f}) '
                f'rotate({math.degrees(dab.angle):.2f}) scale({scale:.4f})"/>')

    def _raster_brush_shape(self, dabs: Sequence["BrushDab"], brush_name: str,
                            hex_color: str, alpha: float) -> Optional[str]:
        """One shape's entire brush stroke, composited into a SINGLE raster
        <image> at export time (--brush-raster) instead of one <use>/dab -
        see the module docstring's BRUSH STROKES section.  Requires Pillow;
        returns None (caller falls back to the per-dab tinted-<use> path) if
        Pillow is unavailable, the brush doesn't resolve, or the composited
        canvas would exceed `RenderSettings.brush_raster_max_pixels` (a
        pathologically long/wide stroke could otherwise demand an enormous
        bitmap - safety valve, not a real Moho limit).

        The canvas is rendered at `RenderSettings.brush_raster_supersample`
        times the shape's own logical pixel size (default 2x: e.g. a 100x40
        stroke is composited at 200x80) but the emitted <image> still
        declares its `width`/`height` at the logical 1x size - exactly the
        "@2x asset" trick used for high-DPI bitmaps: the extra source pixels
        let a downsampling viewer produce a visibly sharper result than
        compositing 1:1 does, since each dab's own resize/rotate has more
        source detail to draw from before everything gets scaled back down.
        Confirmed to measurably reduce (not eliminate) the fine-texture
        softening noted in the module docstring's BRUSH STROKES section for
        a very fine, sparse, high-contrast stroke like "golge" - see
        docs/moho-exporting-svg.md § 7.2 for a visual comparison and the file-size
        cost (roughly proportional to supersample^2).

        This is the most aggressive of this tool's brush-performance options:
        it collapses however many dabs a stroke has into exactly one image
        per shape, at the cost of that stroke no longer being editable/
        rescalable as vector geometry - see docs/moho-exporting-svg.md § 7 for the
        trade-off against --brush-spacing-mul and the default per-dab
        <use> path.
        """
        if Image is None or not dabs:
            return None
        brush = self._get_brush_asset(brush_name)
        if brush is None:
            return None

        # Each dab's square footprint, safely enlarged by its diagonal since
        # it may be rotated to any angle - cheaper than tracking each dab's
        # exact rotated corners for what is only a padding calculation.
        half_diag = [d.diameter_px * 0.7071 for d in dabs]
        pad = 2.0
        min_x = min(d.pos.x - h for d, h in zip(dabs, half_diag)) - pad
        min_y = min(d.pos.y - h for d, h in zip(dabs, half_diag)) - pad
        max_x = max(d.pos.x + h for d, h in zip(dabs, half_diag)) + pad
        max_y = max(d.pos.y + h for d, h in zip(dabs, half_diag)) + pad
        width = max(1, math.ceil(max_x - min_x))
        height = max(1, math.ceil(max_y - min_y))
        scale = max(1.0, self.settings.brush_raster_supersample)
        canvas_w = max(1, round(width * scale))
        canvas_h = max(1, round(height * scale))
        if canvas_w * canvas_h > self.settings.brush_raster_max_pixels:
            return None

        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        tinted_frames: dict[int, Any] = {}
        for dab in dabs:
            frame_index = dab.frame if dab.frame < len(brush.frames) else 0
            tinted = tinted_frames.get(frame_index)
            if tinted is None:
                png_bytes = self._bake_tinted_frame(brush.frames[frame_index].data, hex_color, alpha)
                tinted = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
                tinted_frames[frame_index] = tinted
            size = max(1, round(dab.diameter_px * scale))
            resized = tinted.resize((size, size), Image.Resampling.LANCZOS)
            # SVG's rotate(deg) is clockwise in its own (y-down) space; PIL's
            # rotate(deg) is counter-clockwise as *displayed* - negate to
            # match the same visual rotation the other two render paths use.
            rotated = resized.rotate(-math.degrees(dab.angle), expand=True,
                                     resample=Image.Resampling.BICUBIC)
            rx, ry = rotated.size
            px = round((dab.pos.x - min_x) * scale - rx / 2.0)
            py = round((dab.pos.y - min_y) * scale - ry / 2.0)
            canvas.alpha_composite(rotated, (px, py))

        buf = io.BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return (f'<image href="data:image/png;base64,{b64}" '
                f'x="{min_x:.2f}" y="{min_y:.2f}" width="{width}" height="{height}"/>')

    # -- masking --------------------------------------------------------------

    def _mask_source_shapes(self, layer: Layer, ancestors: Sequence[Layer],
                             frame: float) -> list[tuple[str, float]]:
        """Every shape contributed by a *mask-source* layer (masking == 2) as
        (filled silhouette path, own-stroke-width-to-exclude-in-px) pairs, in
        document pixel space.  `ancestors` is `layer`'s own ancestor chain,
        root-first, NOT including `layer` itself.

        The second element of each pair is what `_mask_element` carves OUT of
        the mask along that path - see the module docstring's MASKING
        section: a mask source's own stroke must stay visible on top of
        anything it masks, confirmed directly against the Moho app.  This is
        achieved by excluding the source's own stroke band from the mask,
        NOT by reordering paint order (which was tried and reverted - it
        conflicts with masking==1 siblings on the very document that
        confirmed the stroke behaviour; see MASKING).  `0.0` means "exclude
        nothing for this shape" - either it has no outline, or its outline is
        brush-styled or tapered (varying point width), where a uniform
        stroke-width band would not match the real (differently-shaped)
        outline - unconfirmed geometry, so this tool falls back to the old
        fill-only contribution for those rather than guessing.

        A mask-source layer does not always carry its own mesh: a GroupLayer
        can be marked masking == 2 purely to act as a masking container (seen
        in real files, e.g. "BellyTexture" in the Bandit rig, whose own
        `mesh` is None).  In that case its silhouette is, recursively,
        whatever ITS OWN masking == 2 child/children define - exactly the
        same shapes that already act as that container's *internal*
        group_mask source (see Layer.group_mask), simply reused here as the
        container's contribution to its *parent's* mask.  Confirmed against
        BellyTexture: its one masking==2 child ("Body") is precisely the
        shape Moho's own export uses both as BellyTexture's internal
        <clipPath> and (once this recursion is applied) as BellyTexture's
        contribution to masking its sibling Head_DarkBlue."""
        paths: list[tuple[str, float]] = []
        if layer.mesh is not None:
            deform = build_deform_chain(ancestors, layer, frame, self)
            geometries = self._curve_geometries(layer.mesh, frame)
            to_px = self._deformed_pixel_mapper(deform, frame, layer)
            for shape in layer.mesh.shapes:
                d = build_path_d(geometries, shape.edges, to_px)
                if not d:
                    continue
                exclude_width = 0.0
                if shape.has_outline and not shape.style.brush_name:
                    point_indices = {layer.mesh.curves[e.curve].points[e.segment].point_index
                                     for e in shape.edges}
                    widths = [self.eval(layer.mesh.points[i].width, frame)
                             for i in point_indices]
                    tapered = (max(widths) - min(widths) > 1e-6) if widths else False
                    if not tapered:
                        point_width = widths[0] if widths else 1.0
                        line_width = self.eval(shape.style.line_width, frame)
                        exclude_width = self._stroke_width_px(line_width, point_width)
                paths.append((d, exclude_width))
        for child in layer.children:
            if child.masking == 2:
                paths += self._mask_source_shapes(child, ancestors + (layer,), frame)
        return paths

    def _mask_sources(self, container: Optional[Layer],
                       chain_through_container: Sequence[Layer],
                       frame: float) -> list[tuple[str, float]]:
        """Mask geometry contributed by `container`'s masking==2 children, if
        `container` masks its children at all.  `chain_through_container` is
        `container`'s own ancestor chain, root-first, ending in `container`
        ITSELF (exactly the ancestor chain shared by `container`'s children -
        both call sites, export_layer and export_document, already have such
        a chain on hand).  See the module docstring's MASKING section for the
        group_mask/masking rules.  This applies uniformly regardless of
        `container`'s depth, including the document's top-level layer - see
        the module docstring for why an earlier version of this tool
        special-cased (and disabled) top-level masking entirely, and why that
        turned out to be the wrong fix for a different, unrelated bug.

        NOTE: this is always evaluated with an EMPTY Smart Bone context
        (self._active_actions), never whatever dials are active for the mesh
        layer(s) being clipped.  That is not a deliberate design choice - it
        falls out of exactly when export_layer/export_document happen to call
        this relative to when they set/clear self._active_actions (always
        *between* two clears, by construction - see both methods) - but it
        has been carefully preserved rather than "fixed", since there is no
        reference to confirm what SHOULD happen instead.  See the module
        docstring's KNOWN GAPS.
        """
        if container is None:
            return []
        forced = container.name in self.settings.forced_mask_containers
        if not forced and not container.group_mask:
            return []
        paths = []
        for child in container.children:
            if child.masking == 2:
                paths += self._mask_source_shapes(child, chain_through_container, frame)
        return paths

    def _mask_element(self, paths: Sequence[tuple[str, float]], mask_id: str,
                       indent: str) -> str:
        """Build a <mask> from `_mask_source_shapes`' (path, exclude_width)
        pairs: each source shape's fill is painted white (included), then -
        painted AFTER, so it wins wherever it overlaps - each shape that
        carries a nonzero exclude_width gets its own stroke, that width wide,
        painted BLACK on top.  That carves the source's own stroke band back
        OUT of the mask, so whatever this mask clips can never paint over it -
        the source's own stroke stays visible, without changing paint order
        at all.  See the module docstring's MASKING section."""
        fills = "".join(f'<path d="{d}" fill="white" fill-rule="nonzero"/>' for d, _ in paths)
        exclusions = "".join(
            f'<path d="{d}" fill="none" stroke="black" stroke-width="{w:.3f}"/>'
            for d, w in paths if w > 0)
        bbox_paths = [d for d, _ in paths]
        x0, y0, w, h = parse_path_bbox(bbox_paths, self.settings.mask_padding)
        return (f'{indent}<mask id="{mask_id}" maskUnits="userSpaceOnUse" x="{x0:.1f}" '
                f'y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}">{fills}{exclusions}</mask>')

    # -- shape rendering / SVG assembly --------------------------------------

    def _render_mesh(self, mesh: Mesh, to_px: Callable[[Vec2], Vec2], frame: float,
                      indent: str, suppress_outline: bool = False) -> tuple[list[str], list[Vec2]]:
        geometries = self._curve_geometries(mesh, frame)
        return ShapeGroupRenderer(self, mesh, geometries, to_px, frame, indent,
                                   suppress_outline).render()

    def _viewbox(self, pixel_points: Sequence[Vec2], crop: bool) -> tuple[float, float, float, float]:
        if crop and pixel_points:
            pad = self.settings.viewbox_padding
            xs = [p.x for p in pixel_points]
            ys = [p.y for p in pixel_points]
            return (min(xs) - pad, min(ys) - pad,
                    max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)
        return (0.0, 0.0, float(self.document.width), float(self.document.height))

    def _wrap(self, viewbox: tuple[float, float, float, float], inner: Sequence[str],
              title: str = "") -> str:
        x0, y0, vw, vh = viewbox
        title_el = f'  <title>{svg_escape(title)}</title>\n' if title else ""
        # self._brush_defs (mask/filter path) and self._brush_tinted_defs
        # (pre-tinted path - see BRUSH STROKES) are populated lazily while
        # `inner` is being rendered, so they can only be prepended here.
        # <mask>/<filter> never render directly, but a bare <image> does -
        # unlike everything else this tool emits, defs MUST live inside a
        # <defs> wrapper or it paints itself once at its own local (x, y) on
        # top of the document, in addition to every <use> of it.
        brush_defs = self._brush_defs + self._brush_tinted_defs
        defs_el = ["  <defs>"] + brush_defs + ["  </defs>"] if brush_defs else []
        body = defs_el + list(inner)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="{x0:.3f} {y0:.3f} {vw:.3f} {vh:.3f}" '
                f'width="{vw:.0f}" height="{vh:.0f}">\n{title_el}'
                + "\n".join(body) + "\n</svg>\n")

    # -- top-level exports ----------------------------------------------------

    def export_layer(self, ancestors: Sequence[Layer], layer: Layer, frame: float = 0,
                      crop: bool = False, local: bool = False) -> str:
        """Export ONE vector layer to a standalone SVG document.

        `ancestors` must be that layer's own ancestor chain, root-first (as
        yielded by Document.walk/vector_layers) - it supplies the transform
        (and, unless `local`, the bone deformation) needed to place the layer
        correctly.  `local` ignores all of that, mapping the mesh's own raw
        coordinates straight to canvas scale - the CLI's --local.
        """
        if local:
            to_px = self._plain_pixel_mapper(IDENTITY_MATRIX)
        else:
            self._active_actions = self._active_actions_along(ancestors, frame)
            self._layer_scale = self._full_chain_matrix(ancestors, layer, frame).uniform_scale() or 1.0
            chain = build_deform_chain(ancestors, layer, frame, self)
            to_px = self._deformed_pixel_mapper(chain, frame, layer)

        body, pixel_points = self._render_mesh(layer.mesh, to_px, frame, indent="    ",
                                               suppress_outline=layer.kind is LayerKind.PATCH)
        self._active_actions = []          # see the note in _mask_sources for why this
                                             # ordering (clear, THEN compute the mask) matters

        name = svg_escape(layer.name)
        head: list[str] = []
        clip = ""
        if not local and layer.masking not in (1, 2):
            container = ancestors[-1] if ancestors else None
            sources = self._mask_sources(container, ancestors, frame)
            if sources:
                mask_id = f"mask_{self._next_def_id()}"
                head.append(self._mask_element(sources, mask_id, "  "))
                clip = f' mask="url(#{mask_id})"'
        inner = head + [f'  <g id="{name}" data-moho-mask="{layer.masking}"{clip}>'] \
                + body + ["  </g>"]
        return self._wrap(self._viewbox(pixel_points, crop), inner, layer.name)

    def export_document(self, frame: float = 0, crop: bool = False,
                         nested_groups: bool = True, include_hidden: bool = False) -> str:
        """Export the whole document as one layered SVG - the CLI's
        --combined mode."""
        inner: list[str] = []
        pixel_points: list[Vec2] = []

        def emit(layers: Sequence[Layer], world: Mat2D, depth: int,
                 container: Optional[Layer], ancestors: tuple[Layer, ...]) -> None:
            pad = "  " * (depth + 1)
            clip = ""
            sources = self._mask_sources(container, ancestors, frame)
            if sources:
                mask_id = f"mask_{self._next_def_id()}"
                inner.append(self._mask_element(sources, mask_id, pad))
                clip = f' mask="url(#{mask_id})"'

            active_child: Optional[Layer] = None
            if container is not None and container.kind is LayerKind.SWITCH:
                active_child = container.switch_active_child(frame, self)

            # NOTE (investigation in progress, see the module docstring's
            # MASKING section): confirmed against the Moho app that a
            # masking==2 sibling's own stroke stays fully visible on top of
            # whatever it masks (Bandit's Head_DarkBlue/BellyTexture pair) -
            # this tool still draws it at its plain list position, which is
            # KNOWN WRONG for that specific pair.  A naive "move masking==2
            # to render after every masking==0 sibling" fix was tried and
            # reverted: on this same container most siblings (Arm_B, Tail,
            # Ears, Muzzle, Nose, EyeBrow, Arm_F, ...) are masking==1
            # ("exempt"), and BellyTexture originally precedes some of them
            # (e.g. Muzzle) - forcing "masking==2 after masking==0" broke
            # that untouched relationship too, dragging BellyTexture's
            # opaque fill on top of the character's eyes/muzzle/nose, which
            # is visibly worse than the bug it was meant to fix.  There is no
            # single global reorder of `layers` that satisfies both "every
            # masking==2 after every masking==0" and "never change relative
            # order against any masking==1 sibling" for this document - the
            # two constraints conflict for BellyTexture specifically.  Not
            # fixed pending more evidence on how masking==1 siblings should
            # interact with this - see KNOWN GAPS.
            for layer in layers:
                if not layer.visible and not include_hidden:
                    continue
                if layer.edit_only and not include_hidden:
                    continue
                if active_child is not None and layer is not active_child:
                    continue                  # switch layer: only its active child draws
                world_here = world.compose(layer.local_matrix(frame, self))
                name = svg_escape(layer.name)
                # the mask source itself, and anything exempt, draws unclipped
                member_clip = "" if layer.masking in (1, 2) else clip

                if layer.mesh is not None:
                    self._active_actions = self._active_actions_along(ancestors, frame)
                    self._layer_scale = world_here.uniform_scale() or 1.0
                    chain = build_deform_chain(ancestors, layer, frame, self)
                    to_px = self._deformed_pixel_mapper(chain, frame, layer)
                    body, pts = self._render_mesh(layer.mesh, to_px, frame, pad + "  ",
                                                  suppress_outline=layer.kind is LayerKind.PATCH)
                    self._active_actions = []
                    pixel_points.extend(pts)
                    if body:
                        if nested_groups or member_clip:
                            inner.append(f'{pad}<g id="{name}" '
                                         f'data-moho-mask="{layer.masking}"{member_clip}>')
                            inner.extend(body)
                            inner.append(f"{pad}</g>")
                        else:
                            inner.extend(body)
                elif layer.is_container:
                    # A GroupLayer/BoneLayer/SwitchLayer (or a TextLayer with
                    # no mesh_layer to synthesise a child from) - recurse into
                    # its children, which may be an empty list; that still
                    # draws an empty <g>, matching Moho.
                    if nested_groups or member_clip:
                        inner.append(f'{pad}<g id="{name}" '
                                     f'data-moho-type="{layer.type_name}"{member_clip}>')
                        emit(layer.children, world_here, depth + 1, layer, ancestors + (layer,))
                        inner.append(f"{pad}</g>")
                    else:
                        emit(layer.children, world_here, depth, layer, ancestors + (layer,))
                # else: neither a mesh nor a container - e.g. an unresolved
                # PatchLayer (see PATCH LAYERS) whose target never got a
                # mesh - draws nothing at all, not even an empty <g>.

        emit(self.document.layers, IDENTITY_MATRIX, 0, None, ())
        return self._wrap(self._viewbox(pixel_points, crop), inner)


# ============================================================================
# ==== SHAPE RENDERING  (-> render.go, alongside Exporter)               ====
# ============================================================================

@dataclass
class _GroupMember:
    """One shape currently buffered in the boolean-combination group being
    assembled by ShapeGroupRenderer._flush.  At most one of stroke_path /
    taper_path / brush_dabs is ever non-empty for a shape that has an outline
    at all - which one depends on whether its outline needs
    TaperedStrokeOutliner or (see the module docstring's BRUSH STROKES
    section) a textured brush style whose asset resolves via --brush-dir."""
    fill_path: str
    combo_mode: int
    name: str
    stroke_width_px: float
    line_hex: str
    line_alpha: float
    line_cap: str
    stroke_path: str
    taper_path: str
    brush_dabs: list = field(default_factory=list)
    brush_ref: Optional[RegisteredBrush] = None      # mask/filter path (Pillow unavailable)
    brush_name: Optional[str] = None                  # pre-tinted path (Pillow available)


class ShapeGroupRenderer:
    """Draws every shape of one Mesh, in file order, into SVG <path> elements
    plus supporting <mask>/<linearGradient>/<radialGradient> defs.

    Boolean shape combination (Shape.combo_mode) means a shape's *outline*
    sometimes cannot be finished until later shapes in the same group are
    known - a union member's outline must be clipped against the *other*
    members, which may not have been rendered yet.  So shapes are buffered
    into `self._group` and only turned into outline <path> elements once the
    group is known to be complete: either the next combo_mode-0 shape starts
    a new group, or the mesh runs out of shapes.  See the module docstring's
    BOOLEAN SHAPE COMBINATIONS section.
    """

    def __init__(self, exporter: Exporter, mesh: Mesh, geometries: list[CurveGeometry],
                 to_px: Callable[[Vec2], Vec2], frame: float, indent: str,
                 suppress_outline: bool = False):
        self.exporter = exporter
        self.mesh = mesh
        self.geometries = geometries
        self.to_px = to_px
        self.frame = frame
        self.indent = indent
        # A resolved PatchLayer shares its target's Mesh/Shape objects
        # verbatim (Document._resolve_patch_layers), so `shape.has_outline`
        # itself cannot be overridden without also affecting the target's own
        # separate render pass elsewhere in the tree.  Confirmed against real
        # Moho ("ayasi-Patch"/masking==2 and "Left Bicep-Patch"/masking==0,
        # both patches, neither shows a stroke in Moho's own canvas while
        # their respective targets do) that a PatchLayer redraws only its
        # target's FILL, never its outline - independent of masking, so this
        # is keyed on layer kind, not on any JSON field.  See the module
        # docstring's PATCH LAYERS section.
        self.suppress_outline = suppress_outline
        self.defs: list[str] = []
        self.body: list[str] = []
        self.pixel_points: list[Vec2] = []
        self._group: list[_GroupMember] = []

    def render(self) -> tuple[list[str], list[Vec2]]:
        for shape in self.mesh.shapes:
            self._render_shape(shape)
        self._flush()
        return self.defs + self.body, self.pixel_points

    # -- per-shape ------------------------------------------------------------

    def _point_widths(self, edges: Sequence[Edge]) -> list[float]:
        point_indices = {self.mesh.curves[e.curve].points[e.segment].point_index for e in edges}
        return [self.exporter.eval(self.mesh.points[i].width, self.frame) for i in point_indices]

    def _render_shape(self, shape: Shape) -> None:
        if not shape.edges:
            return
        exp, frame = self.exporter, self.frame
        style = shape.style
        line_width = exp.eval(style.line_width, frame)
        fill_hex, fill_alpha = Color.from_raw(exp.eval(style.fill_color, frame)).to_svg()
        line_hex, line_alpha = Color.from_raw(exp.eval(style.line_color, frame)).to_svg()
        cap = style.line_cap_name()
        name = svg_escape(shape.name)

        fill_path = build_path_d(self.geometries, shape.edges, self.to_px)
        if not fill_path:
            return

        paint = fill_hex
        if shape.has_fill and isinstance(style.fill_style, dict):
            if style.fill_style.get("type") == "SS_Gradient2":
                gradient_def, gradient_ref = exp._build_gradient(
                    style.fill_style, f"grad_{exp._next_def_id()}", frame,
                    scale=exp.eval(shape.effect_scale, frame),
                    rotation=exp.eval(shape.effect_rotation, frame), indent=self.indent)
                if gradient_def:
                    self.defs.append(gradient_def)
                    paint = gradient_ref
            else:
                sys.stderr.write(f"  ! shape {name}: fill effect "
                                 f"{style.fill_style.get('type')} not supported\n")

        widths = self._point_widths(shape.edges)
        tapered = (max(widths) - min(widths) > 1e-6) if widths else False
        point_width = widths[0] if (widths and not tapered) else 1.0

        combo_mode = shape.combo_mode
        if combo_mode not in (0, 1, 3):
            sys.stderr.write(f"  ! shape {name}: unknown combo_mode {combo_mode}, "
                             f"drawn as-is\n")
            combo_mode = 0
        if combo_mode == 0 or not self._group:
            self._flush()             # a plain shape starts a new boolean group

        clip = ""
        if combo_mode == 3:            # intersect with the group's union so far
            solid_so_far = [m.fill_path for m in self._group if m.combo_mode in (0, 1)]
            clip = self._mask_union(solid_so_far, f"in_{exp._next_def_id()}")

        stroke_width_px = exp._stroke_width_px(line_width, point_width)
        if shape.has_fill:
            op = "" if fill_alpha >= 1 else f' fill-opacity="{fill_alpha:.3f}"'
            self.body.append(f'{self.indent}<path id="{name}_fill" d="{fill_path}" '
                             f'fill="{paint}"{op} fill-rule="evenodd" stroke="none"{clip}/>')

        stroke_path, taper_path = "", ""
        brush_dabs: list = []
        brush_ref = None
        brush_asset_name = None
        brush_asset = None
        # A resolved PatchLayer's shapes are the shared target Shape objects
        # (has_outline is whatever the TARGET declares) - see
        # ShapeGroupRenderer.suppress_outline for why the target's own
        # outline must not be redrawn here.
        outline_enabled = shape.has_outline and not self.suppress_outline
        if outline_enabled and style.brush_name and style.brush_tint:
            brush_asset = exp._get_brush_asset(style.brush_name)
            if brush_asset is not None:
                brush_asset_name = style.brush_name
                # Pillow available -> pre-tinted <use> path (no per-dab mask/
                # filter cost - see BRUSH STROKES); otherwise the original
                # mask/filter path, which needs its <mask> defs built now.
                if Image is None:
                    brush_ref = exp._brush_mask_refs(style.brush_name)
        if outline_enabled:
            if brush_asset is not None:
                # A tapered (varying-width) shape gets brush treatment too,
                # not just a uniform one - BrushStampOutliner scales each
                # dab's own diameter from the width-1.0 base by the point
                # width interpolated at that dab (see its build() docstring),
                # so the base passed in here must NOT already have `widths`'
                # own (possibly-uniform) value baked in the way
                # `stroke_width_px` above does for the non-brush paths.
                diameter_px = exp._stroke_width_px(line_width, 1.0)
                diameter_px = diameter_px if diameter_px > 0 else 1.0
                spacing_frac = style.brush_spacing if style.brush_spacing > 0 else 0.25
                seed = (name, shape.id, len(self.mesh.points))
                brush_dabs = exp.brush_outliner.build(
                    self.geometries, shape.edges, self.to_px, diameter_px, spacing_frac,
                    style.brush_align, style.brush_jitter, seed,
                    frame_count=len(brush_asset.frames),
                    random_order=brush_asset.random_order,
                    random_interval=brush_asset.random_interval,
                    spacing_scale=exp.settings.brush_spacing_mul)
            elif tapered:
                taper_path = exp.tapered_outliner.build(self.geometries, shape.edges,
                                                         self.to_px, stroke_width_px)
            else:
                # combo_mode == 3 (intersect): do NOT drop segments_on==False
                # segments here.  For a plain shape, a hidden segment is a
                # deliberate gap the artist drew (see the module docstring's
                # FILL RULE... section).  For an intersect member, a hidden
                # segment instead very often marks a piece of curve that
                # crosses the base shape's own boundary - Moho's own boolean
                # solver replaces it with a NEW edge computed at that
                # crossing, which this tool cannot reconstruct (no
                # Bezier-Bezier intersection here) - but drawing the ORIGINAL
                # segment in full and letting `clip` (the mask_union below)
                # cut it at the true crossing point gets the same visual
                # result for free, via the SVG renderer's own clipping,
                # instead of the segment just vanishing outright.  Confirmed
                # against Bandit's Eye_Upper/S3: the hidden segment's
                # midpoint lies OUTSIDE the base shape's fill but one
                # endpoint lies INSIDE it - i.e. it genuinely crosses the
                # boundary, not a segment that's simply redundant (that
                # would be combo_mode == 1's case, where a hidden segment IS
                # the shared edge another group member already draws - see
                # BOOLEAN SHAPE COMBINATIONS).  Unconfirmed whether an
                # intersect member ever legitimately wants an artist-drawn
                # gap of its own; only one combo_mode == 3 reference example
                # exists so far.
                stroke_path = build_path_d(self.geometries, shape.edges, self.to_px,
                                           visible_only=(combo_mode != 3), close=False)

        self._group.append(_GroupMember(fill_path, combo_mode, name, stroke_width_px,
                                        line_hex, line_alpha, cap, stroke_path, taper_path,
                                        brush_dabs, brush_ref, brush_asset_name))
        for edge in shape.edges:
            seg = self.geometries[edge.curve].segments[edge.segment]
            self.pixel_points += [self.to_px(seg.p0), self.to_px(seg.c1),
                                  self.to_px(seg.c2), self.to_px(seg.p1)]

    # -- boolean-group outlines -------------------------------------------------

    def _flush(self) -> None:
        """Emit the outlines of the just-finished boolean-combination group.

        Moho merges a union (combo_mode 1) group into a single outline, so the
        shared boundary between members disappears, and the whole outline
        takes the group's FIRST (base) member's styling, not its own - see the
        module docstring.  Reproduced here by stroking (or tapered-outlining)
        every member with the base's style, each clipped against the group's
        other solid members.
        """
        if not self._group:
            return
        base = self._group[0]
        solid = [m.fill_path for m in self._group if m.combo_mode in (0, 1)]
        for member in self._group:
            if not member.stroke_path and not member.taper_path and not member.brush_dabs:
                continue
            style_source = base if member.combo_mode in (0, 1) else member
            clip = ""
            if member.combo_mode in (0, 1) and len(solid) > 1:
                others = [d for d in solid if d != member.fill_path]
                if others:
                    # NOTE: `member.stroke_path` (not taper_path/brush_dabs) is
                    # passed as the "own" shape to size the mask around - this
                    # matches every reference tested, but means a *tapered* or
                    # *brush-stamped* member combined into a union relies
                    # solely on the OTHER members' bounds to size its own clip
                    # mask, since stroke_path is "" for those.  Not currently
                    # known to cause a visible problem (no reference document
                    # exercises either as a non-base union member), but
                    # flagged rather than silently patched - see the module
                    # docstring's KNOWN GAPS.
                    clip = self._mask_subtraction(others, member.stroke_path,
                                                  f"out_{self.exporter._next_def_id()}",
                                                  style_source.stroke_width_px)
            elif member.combo_mode == 3:
                clip = self._mask_union(solid, f"in_{self.exporter._next_def_id()}")

            if member.brush_dabs:
                dab_indent = self.indent + "  "
                dabs_svg = None
                if self.exporter.settings.brush_raster and member.brush_ref is None:
                    # --brush-raster: collapse the whole stroke into one
                    # composited <image> instead of one element per dab -
                    # see _raster_brush_shape.  None (Pillow missing, or the
                    # canvas would be too large) falls through to the normal
                    # per-dab paths below, same as if --brush-raster had not
                    # been passed.
                    raster_el = self.exporter._raster_brush_shape(
                        member.brush_dabs, member.brush_name,
                        style_source.line_hex, style_source.line_alpha)
                    if raster_el is not None:
                        dabs_svg = [f"{dab_indent}{raster_el}"]
                if dabs_svg is None and member.brush_ref is not None:
                    # Fallback path (Pillow unavailable): mask/filter per dab.
                    refs = member.brush_ref.mask_refs
                    dabs_svg = [self.exporter._brush_dab_svg(dab, *refs[dab.frame],
                                                              style_source.line_hex,
                                                              style_source.line_alpha, dab_indent)
                                for dab in member.brush_dabs]
                elif dabs_svg is None:
                    # Preferred path: colour is baked into the image once per
                    # (brush, frame, colour, alpha) - each dab is just a <use>.
                    dabs_svg = []
                    for dab in member.brush_dabs:
                        ref = self.exporter._brush_tinted_ref(
                            member.brush_name, dab.frame,
                            style_source.line_hex, style_source.line_alpha)
                        if ref is not None:
                            dabs_svg.append(self.exporter._brush_use_svg(dab, *ref, dab_indent))
                self.body.append(f'{self.indent}<g id="{member.name}_line"{clip}>')
                self.body.extend(dabs_svg)
                self.body.append(f'{self.indent}</g>')
                continue

            if member.taper_path:
                op = ("" if style_source.line_alpha >= 1
                      else f' fill-opacity="{style_source.line_alpha:.3f}"')
                self.body.append(
                    f'{self.indent}<path id="{member.name}_line" d="{member.taper_path}" '
                    f'fill="{style_source.line_hex}"{op} fill-rule="evenodd" '
                    f'stroke="none"{clip}/>')
                continue

            op = ("" if style_source.line_alpha >= 1
                  else f' stroke-opacity="{style_source.line_alpha:.3f}"')
            self.body.append(
                f'{self.indent}<path id="{member.name}_line" d="{member.stroke_path}" '
                f'fill="none" stroke="{style_source.line_hex}" '
                f'stroke-width="{style_source.stroke_width_px:.3f}"{op} '
                f'stroke-linecap="{style_source.line_cap}" stroke-linejoin="round"{clip}/>')
        self._group.clear()

    def _mask_union(self, paths: Sequence[str], mask_id: str) -> str:
        """Keep only what the union of `paths` covers - see Exporter._mask_
        element's sibling docstring in the module docstring's MASKING section
        for why a <mask> is used rather than a multi-child <clipPath>."""
        children = "".join(f'<path d="{d}" fill="white" fill-rule="nonzero"/>' for d in paths)
        x0, y0, w, h = parse_path_bbox(paths, self.exporter.settings.mask_padding)
        self.defs.append(f'{self.indent}<mask id="{mask_id}" maskUnits="userSpaceOnUse" '
                         f'x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}">'
                         f'{children}</mask>')
        return f' mask="url(#{mask_id})"'

    def _mask_subtraction(self, paths: Sequence[str], own: str, mask_id: str,
                           stroke_width_px: float) -> str:
        """Hide everything covered by `paths`.

        A single even-odd path (the padded bbox, minus every path in `paths`)
        punches a real hole, which stays correct whether a renderer treats
        <mask> content as luminance or as alpha (confirmed to matter: an
        earlier "white rect behind black holes" version of this mask rendered
        wrong in cairosvg, which treats mask content as alpha).

        Cutting exactly at a neighbour's fill edge would also nick a notch out
        of both outlines wherever two boundaries cross (each stops exactly on
        the other's edge, one stroke-width short of actually meeting) - so a
        stroked copy of every path in `paths`, one stroke-width wide, is
        painted back in on top, letting the two ends meet instead.
        """
        x0, y0, w, h = parse_path_bbox(list(paths) + [own], self.exporter.settings.mask_padding)
        box = f"M {x0:.1f} {y0:.1f} H {x0 + w:.1f} V {y0 + h:.1f} H {x0:.1f} Z "
        band = "".join(f'<path d="{d}" fill="none" stroke="white" '
                       f'stroke-width="{stroke_width_px:.3f}" stroke-linejoin="round"/>'
                       for d in paths)
        self.defs.append(f'{self.indent}<mask id="{mask_id}" maskUnits="userSpaceOnUse" '
                         f'x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}">'
                         f'<path fill="white" fill-rule="evenodd" '
                         f'd="{box}{" ".join(paths)}"/>{band}</mask>')
        return f' mask="url(#{mask_id})"'


# ============================================================================
# ==== CLI  (-> main.go / cmd/: argument parsing and file I/O only)      ====
# ============================================================================

def load_document(path: str) -> Document:
    """Read and parse a .mohoproj/.animeproj file.  Kept separate from
    Document.from_raw so the document model itself has no file I/O in it -
    handy for testing, and mirrors how a Go port would likely separate
    `os.ReadFile` + `json.Unmarshal` (main.go) from decoding into the typed
    model (document.go)."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return Document.from_raw(raw)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Moho vector artwork (.mohoproj / .animeproj) to SVG.")
    parser.add_argument("project")
    parser.add_argument("--layer")
    parser.add_argument("--out")
    parser.add_argument("--all", action="store_true", help="export every vector layer")
    parser.add_argument("--combined", metavar="FILE", help="one layered SVG of the whole doc")
    parser.add_argument("--outdir", default=".")
    parser.add_argument("--frame", type=int, default=0)
    parser.add_argument("--crop", action="store_true")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--flat", action="store_true", help="--combined without nested groups")
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--mask-container", action="append", default=[], metavar="NAME",
                        help="force this named layer to act as a mask container "
                             "(repeatable); use when a BoneLayer masks its children "
                             "and RenderSettings.forced_mask_containers/group_mask "
                             "does not already cover it - see the module docstring's "
                             "MASKING section")
    parser.add_argument("--stroke-mul", type=float, default=2.0,
                        help="stroke px = line_width * point_width * docHeight * mul/2")
    parser.add_argument("--brush-dir", default="styles/Brushes", metavar="DIR",
                        help="directory of brush assets (texture PNGs and multi-frame brush "
                             "folders), resolved against a style's brush_name - `make "
                             "styles.brushes` symlinks the default to Moho's own installed "
                             "brush folder; see the module docstring's BRUSH STROKES section; "
                             "a style whose brush resolves to nothing here falls back to a "
                             "plain stroke. Pass \"\" to disable brush stamping entirely "
                             "(fast/preview export - see docs/moho-exporting-svg.md)")
    parser.add_argument("--brush-spacing-mul", type=float, default=1.0, metavar="N",
                        help="multiply brush dab spacing by N (default 1.0 = exact document "
                             "value). A document whose linework is heavily brush-styled can "
                             "produce tens of thousands of dab elements, which is slow for an "
                             "SVG viewer to render (not this tool - export itself stays fast); "
                             "raise this (e.g. 3-4) to thin out dab density and speed up "
                             "viewing, at the cost of a coarser-looking texture - see "
                             "docs/moho-exporting-svg.md")
    parser.add_argument("--brush-raster", action="store_true",
                        help="composite each brush-styled shape's entire stroke into ONE "
                             "raster <image> instead of one <use>/dab - the most aggressive "
                             "size/speed option, at the cost of that stroke no longer being "
                             "vector (not rescalable/editable as a path). Requires Pillow; "
                             "falls back to the normal per-dab path (with a warning) if Pillow "
                             "is unavailable, or per-shape (silently) if that shape's stroke "
                             "would need an unreasonably large canvas - see docs/moho-exporting-svg.md")
    parser.add_argument("--brush-raster-supersample", type=float, default=2.0, metavar="N",
                        help="with --brush-raster, composite at N times the shape's own pixel "
                             "size (default 2.0) before declaring it at the normal 1x size in "
                             "the SVG - the standard \"@2x asset\" trick, noticeably sharper "
                             "for a fine/sparse brush texture at a roughly N^2 file-size cost "
                             "for that image. Pass 1.0 to composite at exact 1:1 size instead")
    args = parser.parse_args()

    if args.brush_raster and Image is None:
        sys.stderr.write("warning: --brush-raster requires Pillow (not installed) - "
                         "falling back to the normal per-dab brush render path\n")

    settings = RenderSettings(stroke_width_scale=args.stroke_mul,
                              forced_mask_containers=frozenset(args.mask_container),
                              brush_dir=args.brush_dir,
                              brush_spacing_mul=args.brush_spacing_mul,
                              brush_raster=args.brush_raster,
                              brush_raster_supersample=args.brush_raster_supersample)
    document = load_document(args.project)
    exporter = Exporter(document, settings)

    all_layers = list(document.walk())
    vector_layers = document.vector_layers()

    if args.list:
        for parents, layer in all_layers:
            extra = (f"  {len(layer.mesh.points)} pts, {len(layer.mesh.shapes)} shapes"
                     if layer.mesh is not None else "")
            print("  " * len(parents) + f"{layer.name} [{layer.type_name}]{extra}")
        print(f"\n{len(vector_layers)} vector layer(s) of {len(all_layers)} total")
        return

    if args.combined:
        os.makedirs(os.path.dirname(args.combined) or ".", exist_ok=True)
        with open(args.combined, "w", encoding="utf-8") as f:
            f.write(exporter.export_document(args.frame, args.crop, not args.flat,
                                             args.include_hidden))
        print(f"wrote {args.combined}")
        return

    if args.all:
        os.makedirs(args.outdir, exist_ok=True)
        used: dict[str, int] = {}
        written = 0
        for i, (parents, layer) in enumerate(vector_layers):
            if not layer.visible and not args.include_hidden:
                print(f"  skip (hidden) {layer.name}")
                continue
            stem = sanitize_filename(layer.name)
            used[stem] = used.get(stem, 0) + 1
            if used[stem] > 1:
                stem = f"{stem}_{used[stem]}"
            path = os.path.join(args.outdir, f"{i:02d}_{stem}.svg")
            with open(path, "w", encoding="utf-8") as f:
                f.write(exporter.export_layer(parents, layer, args.frame, args.crop, args.local))
            written += 1
            print(f"  {path}")
        print(f"{written} file(s) written to {args.outdir}/  (numbered back -> front)")
        return

    if not args.layer:
        parser.error("give --layer NAME, --all, --combined FILE, or --list")
    hit = next(((p, l) for p, l in vector_layers if l.name == args.layer), None)
    if hit is None:
        sys.exit(f"No vector layer named {args.layer!r}. Use --list.")
    parents, layer = hit
    out = args.out or f"{sanitize_filename(args.layer)}.svg"
    with open(out, "w", encoding="utf-8") as f:
        f.write(exporter.export_layer(parents, layer, args.frame, args.crop, args.local))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
