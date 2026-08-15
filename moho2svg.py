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
    in mesh.shapes.  There is a separate `mesh.shape_order` String channel
    (plus an `anim_shape_order` bool) holding a "1|0|3"-style list of shape
    IDs.  An earlier note here called it "only an ascending id registry" -
    that description is WRONG (SketchBone's "rozet1" holds "1|0|3", and its
    shapes carry ids [1, 0, 3] in that same order, neither ascending), but
    the conclusion it supported still holds for a better reason: re-checked
    across SketchBone's meshes, `shape_order` lists exactly the ids of
    `mesh.shapes` in exactly their file order, every time.  It is the
    authoritative draw order AND it is redundant with file order, so reading
    it changes nothing today.  It would start to matter if a document ever
    set `anim_shape_order` true (false everywhere here), i.e. animated the
    z-order - which nothing in this corpus does.
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
    span because that direction was never posed).  Those TWO names are the only
    candidates: a dial bone is an ordinary bone, so a plain stored animation
    that poses the whole rig records its angle too, and treating every action
    registered on that angle as a candidate lets an unrelated animation
    masquerade as a dial - see _active_smart_bones for the Bandit case that
    found this and the 144 px -> 0.73 px it was worth.
  - Resolving a dial's own *current* angle deliberately bypasses this same
    override mechanism (Channel.eval_raw, not Channel.eval) - a dial's position
    always means its literal position on the main timeline, not a value that
    depends recursively on other active dials.
  - An active pose is applied as an OFFSET from its own first keyframe, added
    to the channel's ordinary main-timeline value - NOT as a replacement of it
    (see Channel.eval and _pose_offset).  This only matters for a channel that
    is animated on the main timeline AND registered in an action, but there it
    decides everything: `SketchBone.animeproj`'s `govde-don` ("body turn") dial
    carries a FLAT pose `[160.7, 160.7]` on bone `B16`, sitting exactly at that
    bone's rest angle, while B16 itself swings 126.3 -> 222.4 degrees on the
    main timeline.  Replacing pinned the whole `kol-sag-ust` arm at a constant
    160.7 degrees for the entire animation; offsetting makes a flat pose the
    no-op it evidently is.  Measured against Moho's own arms-only render in
    `moho/SketchBone/hand/`: arm mask IoU over 120 frames 11.5% -> 16.1%, and
    the full-frame pixel difference across the animation improved 6.4%.  Frame
    0 is unaffected (every dial sits at its rest angle there, so the offset is
    zero), which is why the tracked reference SVGs stay byte-identical.

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
    (Skinner.deform, RenderSettings.bone_weight_falloff) is a HEURISTIC, and
    the four candidates are now DISTINGUISHABLE - which they were not until
    Moho's own reference frames arrived.  Scored with `make check-reference`
    (sum of mean positional error over the layers each document can address):

        falloff    SketchBone (10 layers)   Bandit: TailBase dx / Belly dy
        inv_d2            34.15  <- best         8.25 px      3.02 px
        cut_d2            35.54                  6.38 px      3.02 px
        hermite           41.53                  2.02 px      1.62 px
        linear            43.58                  1.89 px      1.59 px

    The two documents DISAGREE, and not marginally: the bounded-support
    shapes (linear, hermite) win every Bandit layer that blends many bones,
    and lose every comparable SketchBone layer (`kuyruk` 2.37 -> 6.24 px,
    `golge` 6.48 -> 10.47 px).  So none of the four is Moho's actual
    function; `inv_d2` stays the default because it wins on the broader
    reference (10 layers against 3, and the newer format).  Layers where one
    bone dominates - `Bandit`'s `Tip`, bound to just two - score IDENTICALLY
    under all four, which is why nothing distinguished them before.

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
  - Channel._segment's monotone-cubic curve is a stand-in for Moho's own
    undecoded easing (no explicit Bezier handle exists for the vast majority
    of channels - see § 3.5 of moho-animation-and-transform.md).  Usually
    sub-pixel.  Quantified as NOT always sub-pixel on `SketchBone.mohoproj`'s
    `B23.anim_angle` (bone 22, cat_boy skeleton): a 178->216.4->130->159.8deg
    swing reversing direction twice in 14 frames produces up to 50.91px of
    per-vertex error on `ayak-sol` (the flexible-bound foot two bones down
    the chain) at the worst between-keyframe frame, confirmed by its own
    per-vertex error reading ~0 exactly AT each of that channel's own
    keyframes and rising only between them - see Skeleton.world_matrices'
    "NOTE ON FLIP PROPAGATION" point (c) for the full evidence trail (that
    investigation first misattributed this to a skinning-blend bug on only
    4 sampled frames; the 120-frame comparison against
    moho/track/SketchBone/foot/ that corrected it is the reason to trust
    this entry over a quick visual check next time too).
  - PatchLayer (see PATCH LAYERS) reuses its target's mesh AND transform - the
    heuristic part is specifically ignoring the patch's own transform/
    parent_bone/flexi_bone_subset/origin, which is confirmed necessary (using
    them renders a wrongly-positioned sliver) but not confirmed as the
    complete picture - there is no independent Moho SVG export of a
    PatchLayer-using document to verify pixel-for-pixel against.  (Fill-only,
    no-outline duplication IS confirmed directly against the Moho app - see
    PATCH LAYERS - so this remaining gap is narrower than it used to be:
    transform/position only, not appearance.)
  - Physics (wind/gravity) and layer_effects/layer_shadow are ignored; a
    single static frame rarely shows either, but an animated Lottie export
    can - see moho2lottie.py's own "physics" warning.  Nothing in this
    corpus actually trips that warning any more: Layer.physics_dynamic now
    requires a bone to subscribe via `wind_dynamics` on top of the two
    fields Moho defaults on for every layer, and the one document it used to
    flag turned out to be explained by the channels after all (see
    Channel._cycle_value).
  - Bone dynamics (Skeleton.dynamic_angles) now drives the spring from the
    PARENT's world rotation, so a bone whose own angle never moves still
    swings - which is how every rig in the corpus actually uses the feature.
    It responds on 3 of the 6 documents that use it, up from 1.  The three
    that stay inert have dynamic bones hanging off a parent that only
    TRANSLATES; making those move needs a pivot-acceleration term, tried and
    rejected on evidence (see dynamic_angles).  Force units are fitted, not
    decoded.  `torque_force`, `angle_weight` and the
    `*_control_delay`/`pos_`/`scale_`/`wind_` dynamics families are read or
    skipped but never applied.
  - `Bandit.mohoproj`'s whole TAIL sits ~18 px (base) to ~32 px (tip) off
    vertically against Moho's own render, where every other layer in the
    document manages 0.3-2.8 px.  DIAGNOSED as the bone-dynamics gap above,
    not a binding defect: the reference's tail bob is a copy of the body's
    own bob, lagged 4 frames (cross-correlation 0.93 at that lag, -0.91 at
    zero) and amplified down the chain (6.7 px at the muzzle, 10.0 at the
    tail base, 15.1 at the tip) - lag plus gain is a resonant oscillator,
    and the tail bones are the document's only two with dynamics on.  Ruled
    out by measurement: all 28 rigid bindings, 5 subsets and all 4 falloffs
    leave the vertical error within ~2 px of each other.  See `make
    check-reference`.
  - A channel's cycle marker IS applied (see Channel._parse_cycles), but its
    REPEAT COUNT is not decoded - nothing in the corpus separates "repeat
    forever" from "repeat N times", so a cycle runs until the channel's next
    keyframe, or forever when the marker sits on the last one.  Moho's own
    interp EASING curve is still not decoded either (see Channel._segment).
  - Moho's 2-bone "Target" IK (`Bone.target_bone`) IS solved - see
    Skeleton._solve_ik_pair - but ONLY the exact 2-bone (bone + its own
    parent) case confirmed on this corpus (`SketchBone.animeproj`'s legs).
    A longer IK chain, or a target_bone relationship spanning more than one
    generation, is not something any sample document exercises and is not
    handled specially - it would currently still only solve the immediate
    2-bone pair, silently ignoring any further ancestors an artist might
    have expected an N-bone solve to reach through.
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


# Vector channels whose components are positions/angles and so can carry a
# meaningful Smart Bone OFFSET.  A Color's {r,g,b,a} is deliberately absent:
# see _pose_offset.
_OFFSETTABLE_VECTOR_KEYS = frozenset("xyz")


def _pose_offset(base: Any, here: Any, rest: Any) -> Any:
    """Apply a Smart Bone pose as a difference from its own rest value.

    Returns `base + (here - rest)` for a float, and the same componentwise
    for an {x, y[, z]} vector.  Anything else - a colour, a bool, a string -
    has no useful notion of "difference", so `here` replaces `base` outright
    for those, which is what the pose curve of such a channel means anyway.
    See Channel.eval for the evidence that offsetting is the right reading.
    """
    if isinstance(base, bool) or isinstance(here, bool):
        return here
    if isinstance(base, (int, float)) and isinstance(here, (int, float)) \
            and isinstance(rest, (int, float)):
        return base + (here - rest)
    if isinstance(base, dict) and isinstance(here, dict) and isinstance(rest, dict) \
            and set(base) <= _OFFSETTABLE_VECTOR_KEYS:
        return {k: base[k] + (here.get(k, 0.0) - rest.get(k, 0.0)) for k in base}
    return here


def _channel_ever_true(raw: Any) -> bool:
    """True when a Bool field is on at ANY point - on its own timeline or
    inside any Smart Bone action pose registered on it.

    Used as a cheap prefilter for switches that are cheap to test once and
    expensive to test per frame (Skeleton.dynamic_angles).  The action poses
    have to be included: `BoneDynamics.animeproj` registers a "JumpCycle"
    pose on the `bone_dynamics` of all six of its rabbit-ear bones, so a
    Smart Bone can turn the feature on for a bone whose own timeline never
    does.

    Args:
      raw: a raw Bool channel, or a plain bool for a field Moho left
        unanimated.

    Returns:
      True if any keyframe of the field or of one of its poses is truthy.
    """
    channel = Channel.of(raw)
    if any(channel.val or []):
        return True
    return any(any(action.pose.val or []) for action in channel.actions)


@dataclass(frozen=True)
class CycleSpec:
    """One "cycle" setting read off a channel's `interp` list.

    Moho lets an animator mark a keyframe as *cycling*: past that keyframe the
    channel does not hold its last value, it jumps back and replays an earlier
    stretch of its own timeline.  `docs/moho-animation-and-transform.md` § 3.4
    documents where the setting lives in the file; `Channel._parse_cycles`
    documents how the numbers were decoded.

    Fields:
      end     the frame of the keyframe carrying the marker.  The cycle only
              affects frames strictly AFTER this one.
      resume  the frame the channel jumps back to at `end + 1`.  Always
              `<= end`, so the replayed stretch is `[resume, end]` and the
              period is `end - resume + 1` frames.
      limit   the next keyframe after `end`, if the channel has one - the
              cycle stops there and normal evaluation takes over.  None means
              the marker is on the last keyframe, so the cycle never stops.
    """
    end: float
    resume: float
    limit: Optional[float]


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

    __slots__ = ("when", "val", "actions", "cycles")

    _cache: dict[int, "Channel"] = {}

    def __init__(self, when: list[float], val: list[Any], actions: list[ActionRef],
                 cycles: Sequence[CycleSpec] = ()):
        self.when = when
        self.val = val
        self.actions = actions
        self.cycles = tuple(cycles)

    @staticmethod
    def reset_cache() -> None:
        """Drop every cached Channel.

        Called by Document.from_raw before a document is parsed, because the
        cache key (see `of`) is only valid while the raw dicts it was built
        from are still alive.  Safe to call at any time: the cache is a pure
        performance aid and refills on demand.
        """
        Channel._cache.clear()

    @staticmethod
    def of(raw: Any) -> "Channel":
        """Build (or reuse) a Channel for `raw`.

        Every wrapper class in the document model (MeshPoint, CurvePoint, Bone,
        ...) stores its channel fields as direct references into the parsed
        JSON, never copies - so the same logical channel is always the same
        Python dict object across every call, for the life of one Document.
        Caching by id() is therefore safe *within* one Document: it cannot
        conflate two of its channels, and the cached Channel is immutable.
        This turns repeated evaluation of the same channel (every curve
        point's smoothness/weight/offset gets looked at more than once per
        frame) from rebuilding a small object tree each time into a dict
        lookup - purely a performance detail, with no effect on behaviour.

        ACROSS documents it is not safe on its own: id() is only unique among
        objects alive at the same moment, so a dropped document's ids come
        back for the next one's dicts.  Document.from_raw calls reset_cache()
        for exactly that reason - keep that call if you add another entry
        point that parses a document.
        """
        if isinstance(raw, dict) and "when" in raw and "val" in raw:
            key = id(raw)
            cached = Channel._cache.get(key)
            if cached is not None:
                return cached
            actions = [ActionRef(a.get("name"),
                                 Channel.of(a.get("pose")).without_cycles())
                       for a in (raw.get("actions") or [])]
            channel = Channel(raw["when"], raw["val"], actions,
                              Channel._parse_cycles(raw["when"], raw.get("interp")))
            Channel._cache[key] = channel
            return channel
        return Channel([0], [raw], [])

    @staticmethod
    def _parse_cycles(when: list[float], interp: Any) -> tuple["CycleSpec", ...]:
        """Read the cycle markers out of a channel's `interp` list.

        Moho stores the setting on the keyframe it belongs to, using two
        general-purpose slots (`v1`, `v2`) whose meaning depends on a flag
        bit in `im`:

        - `im & 4` marks "this keyframe carries a cycle setting".  Without
          the bit the slots hold the untouched default `(0.1, 0.5)` or the
          worked-on-but-not-cycling `(-1, -1)`, so the bit has to be checked
          first.
        - `v1 >= 0` means the setting was entered as a RELATIVE frame count,
          and the channel resumes at `when[i] - v1`.
        - otherwise `v2 >= 0` means it was entered as an ABSOLUTE frame, and
          the channel resumes at `v2`.
        - both negative (`-1`, or the `-1000000` sentinel Moho writes for the
          unused slot) means no usable setting; the marker is ignored.

        How this was decoded (INFERENCE, not a documented format): the five
        sample documents that use cycles carry only four distinct
        `(v1, v2, keyframe)` combinations, and for each one the resumed-at
        frame `A` was found empirically, by looking for the earlier frame
        whose value equals the value at the marked keyframe - which is what a
        seamless loop makes true, and what animators build.  Scoring every
        candidate frame over every cycling channel of each document gives a
        single clear winner per document:

            document                v1     v2      keyframe   winner
            Bandit.mohoproj         15    -1e6        41      25 (92/94)
            TransformBoneTool       23    -1          25       1 (8/10)
            WhatIsBone              -1     2          28       1 (212/217)
            OffsetBoneTool          -1     2          24       1 (32/32)
            BoneStrengthTool        -1     1          24       0 (too few
                                                        numeric channels to
                                                        discriminate; follows
                                                        the same formula)

        Both readings then land one frame LATER than that winner
        (`41 - 15 = 26` vs `A = 25`; `v2 = 2` vs `A = 1`), consistently, in
        every document.  That off-by-one is the point: the stored number is
        not the loop's start, it is the frame the channel RESUMES at - the
        one that follows the marked keyframe.  Because `value(A) ==
        value(end)` on a seamless loop, resuming at `A + 1` and looping over
        `[A + 1, end]` gives exactly the same motion as looping over
        `[A, end]`, which is why both descriptions fit the data and the
        stored one is used here directly.

        `limit` is set to the next keyframe when the marker is not on the
        last one.  17 channels in `WhatIsBone.animeproj` are like that (a
        cycle on frame 28 with a further keyframe at 227).  Cycling only up
        to that keyframe is an INFERENCE - the alternative, ignoring the
        marker entirely, would leave those 17 bones frozen while the other
        227 channels of the same rig cycle, which is plainly not what the
        animator built.

        Args:
          when: the channel's keyframe times.
          interp: the channel's raw `interp` list, or None when absent.

        Returns:
          A tuple of CycleSpec, in keyframe order.  Empty when the channel
          does not cycle, which is the overwhelmingly common case (520
          markers across all 19 sample documents).
        """
        if not interp or len(when) < 2:
            return ()
        specs = []
        for i, entry in enumerate(interp[:len(when)]):
            if not isinstance(entry, dict) or not (entry.get("im", 0) & 4):
                continue
            v1, v2 = entry.get("v1", -1.0), entry.get("v2", -1.0)
            if v1 >= 0:
                resume = when[i] - v1
            elif v2 >= 0:
                resume = v2
            else:
                continue
            # A resume point outside the channel's own past would give an
            # empty or backwards period; treat such a marker as unusable
            # rather than guessing.
            if not (when[0] <= resume <= when[i]):
                continue
            limit = when[i + 1] if i + 1 < len(when) else None
            specs.append(CycleSpec(when[i], resume, limit))
        return tuple(specs)

    def without_cycles(self) -> "Channel":
        """This channel with every cycle marker dropped, recursively.

        Used for Smart Bone action POSES.  An action is a pose library
        indexed by a dial's current angle (see Channel.frame_for_value), not
        a timeline that plays; "repeat forever past the last keyframe" has no
        meaning there, and applying it is actively wrong because a pose is
        read as an OFFSET (see _pose_offset) so an accumulating cycle adds a
        drift that never comes back.

        Moho stores the marker on the pose anyway - `Bandit.mohoproj` carries
        the very same `(v1=15, end=41)` cycle on
        `bones[0].anim_pos.actions[0].pose` as on `bones[0].anim_pos` itself,
        with the same `+0.710093` per-repeat delta - so the marker has to be
        ignored here rather than assumed absent.  Honouring it moved that
        document's head and muzzle by a spurious 590 px across frames 44-80
        while the root bone's own position stayed perfectly smooth, which is
        how this was found.
        """
        if not self.cycles and not any(a.pose.cycles for a in self.actions):
            return self
        return Channel(self.when, self.val,
                       [ActionRef(a.name, a.pose.without_cycles())
                        for a in self.actions],
                       ())

    def action_pose(self, name: str) -> Optional["Channel"]:
        for a in self.actions:
            if a.name == name:
                return a.pose
        return None

    def _cycle_value(self, cycle: "CycleSpec", frame: float, period: float) -> Any:
        """The value at `frame` inside `cycle`, replaying the cycled stretch
        and ACCUMULATING one period's worth of change per repeat.

        Moho's cycle does not replay the same numbers.  It replays the same
        *motion*, carried forward from wherever the previous repeat ended, so
        a walk cycle walks somewhere instead of walking on the spot.  Each
        repeat adds

            delta = value(cycle.end) - value(cycle.resume - 1)

        which is zero for a seamless loop - the overwhelmingly common case -
        and so leaves those channels behaving exactly like a plain replay.

        CONFIRMED against Moho's own render, and it is the strongest
        validation in this file.  `Bandit.mohoproj`'s root bone `B1` carries
        `anim_pos` keyed over frames 25-41 with a cycle marker on frame 41,
        and its x gains `+0.710093` document units - 383.45 px - every
        16-frame repeat.  Predicting the character's centroid from that,
        against the 103 frames Moho itself exported to
        `moho/Bandit/svg/Bandit_000*.svg`:

            model       mean |error|    max |error|
            additive         3.3 px         8.4 px      <- this
            plain replay  1025.7 px      2299.4 px

        over a march of 2437 px.  A plain replay leaves the character walking
        on the spot; the reference walks it clean across the frame.

        This also closes an old mystery.  Layer.physics_dynamic was written
        around "Bandit's keyframed channels do not account for the
        screen-spanning motion Moho's own render shows", and treated that as
        evidence of an unsimulated rigid-body physics run.  The channels do
        account for it - the cycle reading was simply wrong.

        Only numeric and `{x, y[, z]}` vector values accumulate.  A colour, a
        bool or a string has no meaningful "one period's worth of change", so
        those replay unchanged - the same split `_pose_offset` makes for
        Smart Bone poses, and for the same reason.

        Args:
          cycle: the marker being applied.
          frame: a frame strictly after `cycle.end`.
          period: `cycle.end - cycle.resume + 1`, precomputed by the caller.

        Returns:
          The accumulated value at `frame`.
        """
        past = frame - cycle.end - 1          # 0 on the first frame past `end`
        repeats = int(past // period) + 1
        # The mapped frame is always <= cycle.end, so it can only be caught by
        # an EARLIER cycle on the same channel (a nested region, which is
        # correct) - the recursion cannot loop.
        base = self.eval_raw(cycle.resume + (past - (repeats - 1) * period))
        if isinstance(base, bool) or not isinstance(base, (int, float, dict)):
            return base
        end_value = self.eval_raw(cycle.end)
        start_value = self.eval_raw(cycle.resume - 1)
        if isinstance(base, (int, float)):
            return base + repeats * (end_value - start_value)
        if set(base) <= _OFFSETTABLE_VECTOR_KEYS:
            return {k: base[k] + repeats * (end_value.get(k, 0.0)
                                            - start_value.get(k, 0.0))
                    for k in base}
        return base

    def eval_raw(self, frame: float) -> Any:
        """The plain piecewise-linear value at `frame`, ignoring any Smart Bone
        action override.  Used directly (rather than via .eval()) exactly once
        in this codebase: resolving a dial bone's *own* current angle must not
        recurse into the action-override machinery it is itself part of - see
        the module docstring's SMART BONES section.

        A cycle marker (see CycleSpec) is honoured first, by mapping `frame`
        back into the stretch the cycle replays and evaluating that instead.
        Without it a cycled channel simply holds its last value, which is how
        `WhatIsBone.animeproj`'s 240-frame walk used to stop dead at frame 28.

        The cycle ACCUMULATES rather than replaying the same values - see
        _cycle_value.
        """
        when, val = self.when, self.val
        if len(when) == 1 or frame <= when[0]:
            return val[0]
        for cycle in self.cycles:
            if frame > cycle.end and (cycle.limit is None or frame < cycle.limit):
                period = cycle.end - cycle.resume + 1
                if period <= 0:
                    break
                return self._cycle_value(cycle, frame, period)
        if frame >= when[-1]:
            return val[-1]
        for i in range(len(when) - 1):
            if when[i] <= frame <= when[i + 1]:
                t = (frame - when[i]) / (when[i + 1] - when[i])
                a, b = val[i], val[i + 1]
                if isinstance(a, dict):
                    return {k: self._segment(i, k, t) for k in a}
                if isinstance(a, (int, float)) and not isinstance(a, bool):
                    return self._segment(i, None, t)
                # Strings and bools do not interpolate - they step, holding
                # the left keyframe's value until the next one arrives.  ON
                # the next keyframe, though, the value is that keyframe's:
                # the segment scan reaches `when[i] <= frame <= when[i+1]`
                # from the left first, so without this the change lands one
                # frame late.  `BoneDynamics.animeproj`'s `Main` bone has
                # `bone_dynamics` keyed [0, 1, 29] = [False, True, False],
                # and read frame 1 as False.
                return val[i + 1] if frame == when[i + 1] else a
        return val[-1]

    def _segment(self, i: int, key: Optional[str], t: float) -> float:
        """One numeric component of the segment leaving keyframe `i`,
        evaluated at normalised position `t`, as a MONOTONE cubic.

        Moho's own default easing curve is not in the file - `interp.t` is 0
        on 602,784 of 604,139 entries and its enum is undecoded, and the
        explicit Bezier timing handles (`interp.b`) exist on only 182 - so
        the shape has to be inferred from rendered output.  Measured against
        Moho's own arms-only render of `SketchBone.animeproj`
        (`moho/SketchBone/hand/`, 120 frames), scoring arm-mask IoU:

            interpolation      all frames    frames 44-54
            linear                84.55%          60.88%
            smoothstep ease       79.50%          65.67%
            Catmull-Rom           82.20%          78.59%
            monotone cubic        85.76%          81.84%   <- this

        Frames 44-54 are the discriminating window: they sit BETWEEN this
        rig's arm keyframes (43, 49, 55), and linear scored ~89% AT each of
        those keyframes while collapsing to 45-65% between them - the
        signature of the right poses joined by the wrong curve.  Plain
        Catmull-Rom fixes most of that but overshoots, costing accuracy
        elsewhere; clamping the tangents so a segment can never leave the
        range of its own endpoints (Fritsch-Carlson style) beats linear on
        BOTH windows, which is why it is the one adopted.

        Still an inferred curve, not a decoded one: it is the best of four
        candidates on one rig, not proof that Moho computes exactly this.
        Frame 0 is untouched (`frame <= when[0]` returns `val[0]` before any
        of this), so the tracked reference SVGs are unaffected.
        """
        when, val = self.when, self.val
        span = when[i + 1] - when[i]
        get = (lambda j: val[j][key]) if key is not None else (lambda j: val[j])
        a, b = get(i), get(i + 1)
        delta = b - a
        if delta == 0:
            return a
        # Catmull-Rom tangents, expressed over this segment's own duration.
        prev_t = when[i - 1] if i > 0 else when[i] - span
        prev_v = get(i - 1) if i > 0 else a
        next_t = when[i + 2] if i + 2 < len(when) else when[i + 1] + span
        next_v = get(i + 2) if i + 2 < len(val) else b
        m0 = (b - prev_v) / max(when[i + 1] - prev_t, 1e-9) * span
        m1 = (next_v - a) / max(next_t - when[i], 1e-9) * span
        # Monotone clamp: never let the curve leave [a, b].  A tangent that
        # points against the segment is flattened (this is what keeps a held
        # value held, instead of bulging before a repeat), and one steeper
        # than 3x the segment's own slope is capped.
        if m0 * delta < 0:
            m0 = 0.0
        if m1 * delta < 0:
            m1 = 0.0
        if abs(m0) > 3 * abs(delta):
            m0 = 3 * delta
        if abs(m1) > 3 * abs(delta):
            m1 = 3 * delta
        t2 = t * t
        t3 = t2 * t
        return ((2 * t3 - 3 * t2 + 1) * a + (t3 - 2 * t2 + t) * m0
                + (-2 * t3 + 3 * t2) * b + (t3 - t2) * m1)

    def eval(self, frame: float, active_actions: Sequence[ActiveAction]) -> Any:
        """The value at `frame`, honouring Smart Bone overrides.

        EVERY currently-active dial with a matching entry in this channel's
        own `actions` contributes; their offsets ACCUMULATE.  One channel
        really is driven by two dials at once in practice: inside
        `SketchBone.animeproj`'s `kafasi` head rig, bones `B6`-`B10` - which
        the eyes (`goz-sol`/`goz-sag`), the mouth (`agiz`) and the whiskers
        (`biyiklar-*`) are each rigidly parented to - carry `anim_pos`
        entries for BOTH `kafa-sag-sol` (head turning left/right) and
        `kafa-yukari-asagi` (head tilting up/down).  Applying only the first
        match, as this used to, dropped one of the two axes, so those parts
        drifted out of step with the head while `agiz-cevresi` - bound to
        bone 0, which carries no action at all - stayed correct.  That
        contrast is what identified this.

        (A dial's two direction variants, "X" and "X 2", are never active
        together - Exporter._active_smart_bones picks one per dial - so a
        channel registering both cannot double-count.)

        A colour/bool/string pose has no meaningful offset, so for those the
        first match still replaces outright and wins.

        The pose is applied as an OFFSET from its own first keyframe, added on
        top of this channel's ordinary main-timeline value, NOT as a
        replacement for it.  That distinction only shows on a channel that is
        animated on the main timeline AND registered in an action, but there
        it is the whole story: replacing throws the main animation away.

        Confirmed on `SketchBone.animeproj`'s `govde-don` ("body turn") dial.
        Bone `B16`, the bone `kol-sag-ust` is bound to, swings 126.3 -> 222.4
        degrees across its 16 main-timeline keyframes, and also carries a
        `govde-don` pose of `[160.7, 160.7]` - a FLAT curve sitting exactly at
        its own rest angle.  Read as a replacement that pins the whole arm at
        a constant 160.7 degrees for the entire animation, destroying the
        swing; read as an offset it contributes zero, which is plainly what a
        flat pose recorded at the rest value is for.  (`B16`'s other pose,
        `govde-don 2` = `[160.7, 160.7, 167.4]`, then contributes a real
        +6.7 degrees at full dial rather than snapping the arm to 167.4.)
        Measured against `moho/SketchBone/hand/`, Moho's own isolated render
        of just the arms: mask IoU over the whole 120-frame range rises from
        11.5% to 16.1%, and on the frames where this dial is partly engaged
        it roughly doubles (frame 5: 42% -> 81%, frame 9: 39% -> 75%).

        Only numeric and x/y/z vector channels are offset.  A colour, bool or
        string pose has no meaningful "difference", so those still replace.
        """
        value = self.eval_raw(frame)
        for active in active_actions:
            pose = self.action_pose(active.name)
            if pose is None:
                continue
            here = pose.eval_raw(active.frame)
            if not pose.when:
                return here
            rest = pose.eval_raw(pose.when[0])
            offset = _pose_offset(value, here, rest)
            if offset is here:          # colour/bool/string: replace, first wins
                return here
            value = offset
        return value

    def frame_for_value(self, target: float) -> float:
        """Invert this channel: the frame whose value equals `target`
        (clamped to the channel's own value range, and picking the nearest
        keyframe if the range is degenerate).  Used to turn "the dial's
        current angle" into "the corresponding frame within its pose action" -
        see the module docstring's SMART BONES section.

        The inversion must undo exactly the curve `eval_raw` produces, and
        that curve is a monotone cubic, not a straight line - so the segment
        is inverted by bisection on `_segment` rather than by the linear
        `t = (target - a) / (b - a)` this used to do.

        That mismatch was a real defect, not a rounding detail.  Every Smart
        Bone dial pose curve in `SketchBone.animeproj` has exactly two
        keyframes, and a two-keyframe monotone cubic is an S-curve
        (`a + d(1.5t^2 - t^3 + 0.5t)`), so it departs from the straight line
        most in mid-travel and not at all at the ends.  The head-turn dial
        driving that rig's ears therefore resolved to the wrong pose frame by
        a growing amount as the head turned - ear silhouette IoU against
        Moho's own `moho/SketchBone/ears/` render fell from 91.7% with the
        dial at rest (frame 1) to 52.8% with it mid-travel (frame 55).

        Bisection is safe here precisely because `_segment` is monotone
        within a segment by construction (its tangents are clamped so the
        curve cannot leave its own endpoints), so the value is strictly
        ordered and there is exactly one crossing.
        """
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
                # A dial resting exactly on one of its own pose keyframes is
                # the common case (every dial at frame 0), and bisection would
                # answer it as "t = 1e-13" rather than "t = 0".  Answer those
                # exactly, both because it is right and because the alternative
                # perturbs otherwise-unchanged output in the last decimal.
                if target == a:
                    return when[i]
                if target == b:
                    return when[i + 1]
                low, high = 0.0, 1.0
                rising = b > a
                for _ in range(40):          # 1e-12 of the segment; cheap and exact enough
                    mid = (low + high) / 2.0
                    if (self._segment(i, None, mid) < target) == rising:
                        low = mid
                    else:
                        high = mid
                t = (low + high) / 2.0
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


# Bone.scaling_mode's value for Moho's per-bone "Squash and stretch scaling"
# option - see Skeleton.world_matrices' NOTE ON SCALE.  The only other value
# observed is 0 (ordinary uniform scaling): 264 bones vs 586 across the 19
# sample documents.
SQUASH_STRETCH_SCALING_MODE = 2


@dataclass(frozen=True)
class Bone:
    """One bone of a Skeleton.  `parent` is an index into that same skeleton's
    bone list, or -1 for a root bone.  `length` and `strength` are plain
    (never-animated) floats; anim_pos/anim_angle/anim_scale/target_bone are
    channels - see Skeleton.world_matrices for how they combine into a
    transform.

    `target_bone` (a "Val" channel, -1 when unused) is Moho's 2-bone IK
    ("Target") feature: when it names another bone (by index into the SAME
    skeleton), THIS bone and its own `parent` are solved as a 2-bone chain
    reaching for that target bone's position, instead of using their own
    `anim_angle` for the reach - see Skeleton._solve_ik_pair.

    **CORRECTION to an earlier reading of this field.** This docstring used
    to claim an IK-driven bone's `anim_angle` is "PERFECTLY CONSTANT" and
    therefore "meaningless for rendering". That is wrong, and checking only
    one leg is what made it look true: `SketchBone.animeproj`'s RIGHT shin
    (`B27`) is indeed 5.1 degrees at all 15 keyframes, but its LEFT shin
    (`B22`) steps 351.2 -> 449.4 degrees (-8.8 -> +89.4 normalised) between
    frames 43 and 49. The angle is not the reach - the IK solve still
    overrides that - but it IS the animator's record of WHICH WAY the joint
    folds, so it must be read per frame. See Skeleton._solve_ik_bend.

    `scaling_mode` (`0` normal/fixed-length, `2` "auto stretch") and
    `max_auto_scaling` (how many times its rest length a `2` bone may
    stretch) matter specifically for an IK-driven bone: confirmed on
    `SketchBone.animeproj`'s legs (`scaling_mode == 2`,
    `max_auto_scaling == 3.0` on both the thigh and shin) that the IK
    target sometimes sits FARTHER than the two bones' combined rest length
    can reach (up to ~1.9x at some frames) - a plain rotate-only 2-bone
    solve leaves the chain fully extended but visibly short of the target
    (confirmed: the foot ends up floating, detached from the leg, at
    frame 50). See Skeleton._solve_ik_pair for the auto-stretch this
    triggers.

    `flip_h`/`flip_v` are Bool channels mirroring everything this bone
    drives - the bone-level twin of `Layer.transform`'s own flip_h/flip_v,
    and applied the same way (see Skeleton.world_matrices). An animator
    uses this to turn a hand or foot around mid-walk without re-drawing it.
    RARE but real: exactly ONE bone across all 19 sample documents ever
    sets either - `SketchBone.animeproj`'s "B23" (the left ankle, which
    drives the `ayak-sol` foot layer via its flexi_bone_subset), keyframed
    `flip_h` False at frame 0 -> True at frame 44. Ignoring it left that
    foot pointing backwards against its own direction of travel for the
    whole second half of the walk, which is what the field was found
    from.

    B23's own two children in that same subset, B24 and B25, are what
    regressed this once already, in a way that is easy to reintroduce again
    if `Skeleton.world_matrices` is ever touched without re-running its own
    verification: see that method's "NOTE ON FLIP PROPAGATION"."""
    name: str
    parent: int
    length: float
    strength: float
    anim_pos: Any
    anim_angle: Any
    anim_scale: Any
    target_bone: Any
    scaling_mode: int
    squash_stretch_scaling: float
    max_auto_scaling: float
    flip_h: Any
    flip_v: Any
    bone_dynamics: Any
    angle_dynamics: Any                 # None when the file predates the field
    wind_dynamics: Any                  # None when the file predates the field
    spring_force: float
    damping_force: float
    torque_force: float

    def dynamics_on(self, frame: float, exporter: "Exporter") -> bool:
        """Whether this bone's ANGLE dynamics is switched on at `frame`.

        Newer Moho splits the setting in two, and BOTH parts must be on:

        - `bone_dynamics` - the per-bone master switch.  Present in every
          format version, a keyframed Bool channel, and Smart-Bone
          overridable.
        - `angle_dynamics` - "the angle channel takes part", one of a family
          (`pos_dynamics`, `scale_dynamics`, `wind_dynamics`, each with its
          own `*_spring_force`/`*_damping_force`/`*_torque_force`/`*_weight`/
          `*_control_delay`) that only exists from format 1045.  Absent means
          an older file, which is read as "on", so old documents behave
          exactly as before.

        EVIDENCE for the AND, and against reading either field alone.
        `SketchBone` exists in this corpus twice: the 2016 original
        (`.animeproj`, format 1038) and a re-save from Moho Pro 14.4
        (`.mohoproj`, format 1045) of the SAME document.

        | field | 1038 original | 1045 re-save |
        |---|---|---|
        | `bone_dynamics` | false on all 94 bones | false on all 94 bones |
        | `angle_dynamics` | field does not exist | **true on all 94 bones** |

        So `angle_dynamics` alone cannot be the switch: Moho's own upgrade
        path sets it true on every bone of a document that uses no dynamics
        at all.  It is simply the default for the new field.

        `bone_dynamics` alone cannot be it either, on the new format:
        `Bandit.mohoproj` (also 1045) has it true on **all 28 bones**,
        including the Smart Bone dials `EyeBlink`, `HeadTurn`,
        `SquashStretch` and `EyeMovement`, which plainly must not wobble -
        while `angle_dynamics` is true on only 2 of them.

        The AND fits both files and changes nothing on the four old-format
        documents that use the feature (`WhatIsBone` 52 bones, `AddBone` 21,
        `BoneDynamics` 7, `Rabbit` 7, `ControlBones` 2 - all unchanged,
        since they have no `angle_dynamics` to fail).

        INFERENCE, not confirmed against Moho itself: no reference render
        exercises bone dynamics cleanly (see Skeleton.dynamic_angles).  Only
        `--bone-dynamics` is affected, and that is off by default.

        Args:
          frame: the frame to test the switch at.
          exporter: used to evaluate the channels with the active Smart Bone
            context.

        Returns:
          True when this bone's angle should be spring-simulated at `frame`.
        """
        if not exporter.eval(self.bone_dynamics, frame):
            return False
        return self.angle_dynamics is None or bool(
            exporter.eval(self.angle_dynamics, frame))

    @property
    def dynamics_ever_on(self) -> bool:
        """True when dynamics_on() could be true at SOME frame.

        A frame-independent prefilter, so the per-frame test is only paid for
        bones that could ever need it.  Both halves of the switch are
        keyframed Bool channels that a Smart Bone action can also drive, so
        both are tested with _channel_ever_true rather than by reading one
        value."""
        if not _channel_ever_true(self.bone_dynamics):
            return False
        return self.angle_dynamics is None or _channel_ever_true(self.angle_dynamics)

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
            target_bone=raw.get("target_bone", -1),
            scaling_mode=raw.get("scaling_mode", 0),
            squash_stretch_scaling=raw.get("squash_stretch_scaling", 1.0),
            max_auto_scaling=raw.get("max_auto_scaling", 1.0),
            flip_h=raw.get("flip_h", False),
            flip_v=raw.get("flip_v", False),
            bone_dynamics=raw.get("bone_dynamics", False),
            angle_dynamics=raw.get("angle_dynamics"),   # None = field absent
            wind_dynamics=raw.get("wind_dynamics"),     # None = field absent
            spring_force=raw.get("spring_force", 2.0),
            damping_force=raw.get("damping_force", 1.0),
            torque_force=raw.get("torque_force", 2.0),
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

        NOTE ON SCALE: two separate rules, both measured against Moho's own
        renders.

        (1) `anim_scale` is applied to the matrix's first column alone -
        stretching the bone along its own axis without widening it across -
        for a bone whose `scaling_mode` is 2, and to BOTH columns (an
        ordinary uniform scale) otherwise.

        (2) SCALE DOES NOT ACCUMULATE DOWN THE CHAIN.  A child's origin is
        placed with the parent's full, scaled matrix - so a squashing torso
        does drag its head down - but the child's own axes are rebuilt from
        the accumulated ROTATION and the child's OWN scale.  A parent that
        squashes therefore moves its children without shrinking them.

        Rule (2) was decoded from `BoneDynamics.animeproj`, where `TorsoA`
        squashes to `anim_scale = 0.61` at frame 1.  Composing normally
        collapsed the rabbit's ear from 130 px tall (its rest height, and
        Moho's) to 83.5 px - almost exactly 130 x 0.61 - while Moho's own
        export keeps it at 130.  Fixing it improved every other reference
        too, which is why it is rule and not special-casing:

            layer (vertical error, mean / max px)   before        after
            Bandit  Muzzle                        2.65 / 5.92   0.85 / 2.05
            Bandit  BellyTexture                  2.84 / 6.26   0.68 / 1.66
            SketchBone  kafasi                    2.35 / 10.94  1.53 / 2.08
            SketchBone  kulak-sol                 4.47 / 20.20  3.20 / 6.68
            SketchBone  cizgiler-sag              2.20 / 9.51   1.64 / 3.49

        `squash_stretch_scaling` (0.61 on `TorsoA`, 0.41 on `TorsoB`, 1.0 on
        831 of 850 bones) is still NOT used.  Four cross-axis formulas were
        fitted for it against the same reference - `1/s`, `s**-q`, a blend,
        and a linear one - and none won across layers: `1/s` improved that
        document's body from 30.3 to 24.5 px while making its tail and one
        ear worse.  Left out rather than guessed.

        NOTE ON FLIP PROPAGATION - REGRESSION, FOUND AND FIXED ONCE ALREADY.
        `flip_h`/`flip_v` were first implemented in commit "Fix bone
        deformation, Smart Bone and channel interpolation defects", which
        composed each bone with `parent_matrix.compose(local)` - full 2x2
        matrix multiplication, which propagates a reflection
        (`det < 0`) through a chain automatically, the way matrix composition
        always does.  Implementing rule (2) above REPLACED that composition,
        for any non-root bone, with `rot[i] = rot[parent] + angle` - a bare
        SCALAR angle sum - because only the rotation needed to keep
        accumulating once scale was decoupled from it.  That is wrong: a
        scalar angle cannot represent a reflection, so a parent's flip
        stopped reaching its children. `SketchBone.mohoproj`'s ankle chain
        `B23 -> B24 -> B25` (bones 22/23/24, exactly the
        `flexi_bone_subset` that deforms the `ayak-sol` foot mesh - the LEFT
        ankle driving the layer named, confusingly, "right foot"; see this
        class's own Bone docstring) makes the break exact: `B23.flip_h` goes
        `False -> True` at frame 44, so `det(world(B23))` correctly flips
        from `+1` to `-1` there, but `det(world(B24))` and `det(world(B25))`
        stayed at `+1` on every frame with the scalar-angle version - the
        mirror never reached them. The leg (a different, unflipped bone
        group) still looked right, which is what made this read as
        "the foot is backwards, the leg is fine" rather than "rotation is
        broken everywhere" - exactly the symptom the ORIGINAL flip_h fix's
        own commit message describes ("a foot pointing backwards ... for
        half the walk"), which is why it was mistaken for the same bug come
        back rather than a new one.

        THE FIX is to decouple magnitude from the chain (rule 2) while still
        propagating ORIENTATION - rotation AND reflection together - by
        composing actual 2x2 matrices, not by summing angles.  `orient[i]`
        tracks each bone's accumulated rotation-and-flip with NO scale and
        NO translation (`local_orient` below); `orient[parent].compose(
        local_orient)` is exactly `Mat2D.compose`, so `det` multiplies
        correctly through the chain (`det(A.compose(B)) == det(A) * det(B)`
        for the same reason two mirrors make a rotation).  The bone's own
        scale is then applied on top of `orient[i]` only when building
        `out[i]`, never accumulated into `orient` itself, which is what still
        gets rule (2) right.

        VERIFY THIS STAYS FIXED - TWO INDEPENDENT WAYS, BOTH CHEAP.

        (a) `det(world_matrices(f)[i])` must be negative for every bone at or
        after a flip and for every one of its descendants, never just the
        flipped bone itself:

            python3 -c "
            import sys; sys.path.insert(0, '.')
            from moho2svg import Channel, Exporter, load_document
            Channel.reset_cache()
            doc = load_document('moho/SketchBone.mohoproj')
            cat_boy = next(l for l in doc.layers[0].children if l.name == 'cat_boy')
            exp = Exporter(doc)
            for f in (0, 44, 45, 120):
                w = cat_boy.skeleton.world_matrices(float(f), exp)
                print(f, [round(w[i].a*w[i].d - w[i].b*w[i].c) for i in (22, 23, 24)])
            "
            # expect [1, 1, 1] at f=0, [-1, -1, -1] at f=44/45/120 - never a mix.

        (b) `make check-reference` (`tools/check_reference_frames.py`,
        `run_winding_check`) scores the ACTUAL mesh this bug shipped wrong -
        `ayak-sol`, against Moho's own render, now tracked under
        `moho/track/SketchBone/new/` - by the sign of its shoelace area,
        which a mirror flips.  Confirmed on this exact regression: every one
        of 8 sampled frames from 1 to 120 mismatched sign in the broken
        build (bounding-box WIDTH barely moved - 43.4px broken vs 41.9px
        correct at frame 44 - which is why the bbox-centre checks in the
        same file did not catch this the first time); none mismatch after
        the fix in this commit. Rerun both (a) and (b) after ANY change to
        this method, not just ones that mention flip_h - (a) is instant and
        catches the mechanism directly, (b) is the one with a real
        consequence attached.

        (c) VISUAL + WHOLE-DOCUMENT VERTEX ERROR, against
        `moho/track/SketchBone/foot/` - 120 frames covering BOTH legs
        (`bacak-sag`/`ayak-sag`, which never flips, alongside
        `bacak-sol`/`ayak-sol`, which does), supplied specifically to
        arbitrate this fix after an initial 4-frame visual check
        (`moho/track/SketchBone/parts/ayak-sol-{43,44,45,46}.jpg`, still
        useful for a quick look) was not enough evidence on its own and led
        to a wrong first diagnosis - recorded here because the correction is
        the useful part.

        Per-vertex error (mean of point-to-point distance against the
        reference) across ALL 120 frames, propagated vs not:

            layer               flip propagated          flip NOT propagated
            ayak-sag (control)  max 5.88px anywhere       (unaffected either way)
            ayak-sol            max 50.91px at f45,        24-67px from f44
                                 decays to <0.5px by f57    ONWARD, forever

        Not-propagating is unambiguously worse and never recovers - confirms
        (a) and (b) again, more strongly.

        THE FLIP EVENT ITSELF IS THE ROOT CAUSE OF THE TRANSIENT ERROR - not
        an incidental trigger for an unrelated curve-approximation issue (an
        earlier revision of this note said exactly that, and it undersold
        the flip's own role; corrected here after the person who supplied
        this reference frame set rechecked the Moho app and confirmed the
        target bone's own reorientation at frame 43->44 is instant there
        too, which is the fact that prompted re-deriving this). Printing
        `B24`'s WORLD angle (`B24` carries no flip of its own - this is
        pure composition through its flipped parent `B23`) frame by frame:

            f=43: -8.23deg   f=44: -146.56deg   (a -138.34deg jump in ONE frame)
            f=45..49: -138.86, -130.01, -121.65, -115.43, -112.99  (smooth, ~7-9deg/frame after)

        That -138.34deg discontinuity, not any curve-shape detail, is what
        the 44-46 transient error actually is. It is the mathematically
        CORRECT consequence of composing a rotation through a reflection:
        `B23` itself swings from a local angle of 182.87deg to a world
        angle of 2.87deg the instant `flip_h` goes true (negating one
        column reflects direction theta to theta+180, confirmed exactly:
        182.87+180 = 362.87 = 2.87mod360) - a ~175deg reorientation of `B23`
        alone, on top of which `B24`'s own small, real, authored
        -24.38deg local-angle keyframe (also timed at frame 44) composes
        through the now-mirrored parent frame, which is what a reflected
        coordinate system does to a subsequent local rotation: it reverses
        its apparent handedness in world space. Two alternative composition
        formulas were tried against this exact 120-frame reference and
        BOTH came out equal-or-worse, which is why the model above is kept
        rather than adjusted further:
          - Reordering the flip to apply in the parent's frame before this
            bone's own rotation (`Diag(fh,fv).R(theta)` instead of
            `R(theta).Diag(fh,fv)`) - identical result here, because `B24`
            itself never flips (`Diag(1,1)` is the identity either order),
            so this distinction cannot matter for this particular chain.
          - Propagating a separate boolean "mirrored" flag by XOR down the
            chain while summing local angles as plain scalars (no
            handedness reversal), applying the mirror once at the end -
            mathematically the "intuitive" alternative, and MUCH worse: it
            no longer converges to the correct steady state at all (16.70px
            mean / 33.08px max at frame 90, versus this method's ~0.3px).

        So the -138deg jump is real, large, and directly, unavoidably
        caused by the flip event composing correctly through the chain -
        not a symptom to be explained away. What IS still an open,
        secondary detail is that the error does not stay at its peak: it
        decays smoothly back toward zero by frame 57, and reads ~0 exactly
        at `B23.anim_angle`'s own later keyframes (49: 2.26px, 53: 2.71px,
        57: 0.46px) while peaking BETWEEN them (28px mean at 45, 12px mean
        at 52) - `B23.anim_angle` swings 178deg -> 216.4deg -> 130deg ->
        159.8deg across exactly those keyframes (reversing direction twice
        in 14 frames) with no explicit Bezier handle (`interp[i].im & 8`
        unset throughout, confirmed), i.e. Moho's own undecoded default
        easing curve, approximated by `Channel._segment`'s monotone cubic
        (see that method's own docstring) - a KNOWN, pre-existing
        imprecision elsewhere levered large here by the chain's length and
        by sitting right on top of the flip's own real discontinuity.  NOT
        a `Skinner.deform` skinning-blend artifact (an earlier revision of
        this note wrongly guessed that too, on only 4 sampled frames) - a
        wrong blend weight would not zero out exactly at `B23`'s own
        keyframes the way this does.

        CONFIRMED AGAINST LIVE MOHO PLAYBACK, not just its exported frames:
        the person who supplied this reference set watched `ayak-sol` scrub
        frame by frame in the Moho app itself from 44 through 49 and
        confirmed it keeps visibly changing shape/size across that whole
        span before settling - not a clean single-frame snap immediately
        followed by stillness. That directly validates
        `moho/track/SketchBone/foot/` as trustworthy ground truth (its own
        numbers already showed the same multi-frame settling) and settles
        what would otherwise be a recurring question: the FLIP toggle is
        instant (43->44, confirmed both ways), but "the shape keeps changing
        for several more frames after" is Moho's own real behaviour, not an
        artifact of this method. The open gap is narrower than that: only
        the PRECISE shape during frames 44-48 doesn't yet match, which is
        the interpolation-curve imprecision above, not the mere fact that
        settling takes a few frames.

        That asymmetry was carried for a long time as an unexplained quirk,
        applied to every bone and flagged in the module docstring's KNOWN
        GAPS as possibly an old transcription slip, because nothing in the
        corpus distinguished it.  `scaling_mode` is what distinguishes it:
        it is Moho's per-bone "Squash and stretch scaling" switch, and
        scaling one axis only is exactly what squash-and-stretch means.

        Decoded from the rig rather than guessed.  In `SketchBone.animeproj`'s
        `kafasi` head skeleton the two bones carrying each ear - `B2`/`B3` for
        one, `B4`/`B5` for the other - have `scaling_mode == 2`, while the
        third bone in each ear's own `flexi_bone_subset` - `B20` and `B19` -
        has `scaling_mode == 0`.  That split is visible in Moho's own bone
        constraints panel as squash-and-stretch being ticked on the first two
        and not the third, which is how it was spotted.  Corpus-wide the field
        is 2 on 264 bones and 0 on 586.

        (`squash_stretch_scaling` is a separate float - a magnitude, 1.0 on
        831 of 850 bones - not the on/off switch.)

        A bone with `target_bone` set (Moho's 2-bone "Target" IK) is solved
        together with its own parent as a 2-bone chain reaching for the
        target bone's position - see _solve_ik_pair - instead of using
        either bone's own `anim_angle` (which is not a per-frame FK value at
        all for such a bone; see Bone's own docstring). The topological
        order (`add`) is extended so a target bone always resolves before
        the bone1/bone2 pair that depends on it, exactly the way a normal
        parent already does.
        """
        return self._world_matrices(frame, exporter,
                                     self.dynamic_angles(frame, exporter))

    def _world_matrices(self, frame: float, exporter: "Exporter",
                         dynamic: dict[int, float]) -> list[Mat2D]:
        """world_matrices' body, with the simulated angles passed in rather
        than fetched.

        Split out so Skeleton.dynamic_angles can build the KEYED pose - the
        pose with no dynamics applied, `dynamic = {}` - without recursing
        back into itself through world_matrices.  Every other caller wants
        world_matrices, which supplies the simulated angles for them.

        Args:
          frame: the frame to evaluate at.
          exporter: channel-evaluation context.
          dynamic: {bone index: local angle in radians} overriding
            `anim_angle` for those bones; empty for the plain keyed pose.
        """
        n = len(self.bones)
        out: list[Optional[Mat2D]] = [None] * n
        # Accumulated ROTATION-AND-FLIP only, no scale, no translation - see
        # the NOTE ON SCALE / NOTE ON FLIP PROPAGATION below for why this has
        # to be a composed matrix and not a scalar angle.
        orient: list[Optional[Mat2D]] = [None] * n
        seen: set[int] = set()
        order: list[int] = []
        ik_pairs = self._ik_pairs(frame, exporter)   # bone1 index -> (bone2 index, target index)

        def add(i: int) -> None:
            if i in seen:
                return
            seen.add(i)
            parent = self.bones[i].parent
            if parent >= 0:
                add(parent)
            pair = ik_pairs.get(i)
            if pair is not None:
                add(pair[1])          # the IK target must resolve before bone1 does
            order.append(i)

        for i in range(n):
            add(i)

        for i in order:
            if out[i] is not None:
                continue              # already solved below, as the bone2 half of a pair
            bone = self.bones[i]
            pos = Vec2.of(exporter.eval(bone.anim_pos, frame))
            scale = exporter.eval(bone.anim_scale, frame)
            parent = bone.parent
            parent_matrix = out[parent] if parent >= 0 else None
            solved = self._solve_ik_pair(i, ik_pairs, out, pos, scale, parent_matrix, frame, exporter)
            if solved is not None:
                out[i], orient[i], (bone2_index, bone2_matrix, bone2_orient) = solved
                out[bone2_index] = bone2_matrix
                orient[bone2_index] = bone2_orient
                continue
            angle = dynamic.get(i, exporter.eval(bone.anim_angle, frame))
            c, s = math.cos(angle), math.sin(angle)
            # flip_h/flip_v negate one column each, exactly as
            # Layer.local_matrix does for a layer's own flips - column 1 is
            # the bone's own direction axis (the one anim_scale already
            # scales), column 2 the perpendicular.  See Bone's docstring for
            # the single real occurrence this was derived from.
            fh = -1.0 if exporter.eval(bone.flip_h, frame) else 1.0
            fv = -1.0 if exporter.eval(bone.flip_v, frame) else 1.0
            # Squash-and-stretch scales along the bone only; every other bone
            # scales uniformly - see this method's NOTE ON SCALE.
            across = 1.0 if bone.scaling_mode == SQUASH_STRETCH_SCALING_MODE else scale
            local = Mat2D(c * scale * fh, s * scale * fh,
                           -s * across * fv, c * across * fv, pos.x, pos.y)
            # The same local rotation/flip, but with UNIT magnitude - no
            # scale baked in.  Composing these (not the angle-only versions
            # below) is what keeps a parent's flip_h/flip_v propagating
            # through a REFLECTION rather than being lost - see NOTE ON FLIP
            # PROPAGATION.
            local_orient = Mat2D(c * fh, s * fh, -s * fv, c * fv, 0.0, 0.0)
            if parent_matrix is None:
                out[i] = local
                orient[i] = local_orient
            else:
                # SCALE DOES NOT ACCUMULATE DOWN THE CHAIN.  The child's
                # ORIGIN follows the parent's scaled frame - a squashing torso
                # does drag its head down - but the child's own axes are
                # rebuilt from the accumulated ORIENTATION and its OWN scale,
                # so the squash does not shrink the child as well.  See this
                # method's NOTE ON SCALE.
                origin = parent_matrix.apply(pos)
                o = orient[parent].compose(local_orient)
                orient[i] = o
                out[i] = Mat2D(o.a * scale, o.b * scale, o.c * across, o.d * across,
                                origin.x, origin.y)
        return out  # type: ignore[return-value]

    def dynamic_angles(self, frame: float, exporter: "Exporter") -> dict[int, float]:
        """Simulated angle for every bone whose dynamics switch is on AT
        `frame`, or {} when the feature is disabled or no bone uses it.

        The switch is `bone_dynamics` AND `angle_dynamics` - see
        Bone.dynamics_on for why both, and for what changed between format
        versions.  It is made of keyframed Bool channels, not constants, and
        it is asked per frame: `BoneDynamics.animeproj`'s `Main` bone turns
        dynamics ON at frame 1 and OFF again at frame 29.  Smart Bone action
        poses on it are honoured too (via Exporter.eval), because that same
        document registers a "JumpCycle" pose on the `bone_dynamics` of all
        six of its rabbit-ear bones.

        UNVERIFIED INFERENCE, off unless `--bone-dynamics` is passed.  Moho
        gives three numbers per bone (`spring_force`, `damping_force`,
        `torque_force`) and nothing else: not the equation, not the units of
        those numbers, not the integrator, not the initial conditions.

        THE MODEL.  A bone with dynamics is a pendulum hanging off its
        parent, with inertia in WORLD space.  Writing `pw` for the parent's
        world angle and `x` for this bone's own local angle, the bone's world
        angle is `pw + x`, and a damped spring pulling that world angle back
        to where the keyframes say it should be expands to

            x'' = spring * (keyed - x) - damping * (x' + pw') - pw''

        Each term earns its place:

          - `spring * (keyed - x)` and `-damping * x'` are the original
            model, and are all that survives when the parent holds still.
          - `-damping * pw'` and `-pw''` are what make the feature work at
            all.  They are the parent's own world rotation arriving as a
            driving force, so a bone whose OWN angle never changes still
            swings when its parent turns.

        UNITS are per FRAME, not per second.  Read as per-second, a spring of
        2 and a damping of 1 make an oscillator so slack that the parent's
        rotation drags a bone 200 degrees off its keyed angle and holds it
        there; read per frame the same rig gives a smooth 3 / 13 / 27 degree
        gradient from ear base to ear tip.  This is a fit, not a decoding -
        but Moho is a frame-based program and the per-second reading is not
        merely less accurate, it is unusable.

        `torque_force` is still read and still NOT used, and this time it was
        tried properly rather than assumed unusable.  A pendulum whose
        suspension point accelerates sideways does swing, so the obvious
        reading is a pivot-acceleration term
        `- torque * (pivot_acceleration . across) / length`, which is also
        the only candidate that would make a bone react to a parent that
        merely TRANSLATES.  Two independent checks rejected it:

          - On `BoneDynamics.animeproj` it spiked the ear tip to 81 degrees
            off its keyed angle on one frame with neighbours at 40 and -21,
            against a smooth 3 / 13 / 27 degree base-to-tip gradient without
            it.
          - Swept against Moho's own render of `Bandit.mohoproj` in BOTH
            signs - +0.001 to +1.0 and -0.01 to -3.0 - it never improved the
            match at any scale, and got monotonically worse away from zero
            (tail base vertical error 18.06 px at 0, 20.68 px at -1.0,
            25.71 px at -3.0).  The sign was worth testing because the
            reference's tail lags the body by half a period, which reads as
            anti-phase; it is not a sign error.

        So it stays out, and the consequence is stated plainly rather than
        hidden: a bone whose parent only translates still does not move.
        That is exactly `Bandit.mohoproj`, whose root bone never rotates, so
        `--bone-dynamics` remains a no-op there.

        WHY THE REWRITE.  The previous model pulled the bone toward its own
        keyed angle and nothing else, so a bone whose `anim_angle` never
        moves could never move.  Measured across the corpus, that is exactly
        what real rigs do with the feature:

            document                dynamic bones   own anim_angle moves
            BoneDynamics.animeproj        7                 0
            Rabbit.animeproj              7                 0
            AddBone.animeproj            21                 0
            ControlBones.animeproj        2                 0
            WhatIsBone.animeproj         52                16
            Bandit.mohoproj               2                 0

        In `BoneDynamics.animeproj` - the tutorial file for this very
        feature - all six ear bones hold a constant `anim_angle`, `anim_pos`
        and `anim_scale`; what moves is their grandparent `Main` (`anim_pos`
        x -1.56..1.10, y -0.32..1.43, the jump) and `TorsoA` (angle 250..307
        degrees, scale 0.61..1.16).  The ears flop because they lag the
        parent's world motion.  Under the old model `--bone-dynamics` was a
        measured no-op on five of the six documents that use the feature.

        WHAT IS STILL GUESSED.  The units of all three forces, the
        integrator, and the initial conditions.  `pw` is
        taken from the KEYED pose, not from the parent's own simulated
        angle, so a chain lags its parent's keyframes rather than its
        parent's lag - one order short of a full chain solve, chosen because
        it keeps the cost at one extra world-matrix build per frame instead
        of one per bone per sub-step.

        HOW FAR IT IS CHECKED - AND IT FAILS.  `BoneDynamics.animeproj` now
        has a Moho render (`moho/BoneDynamics/`, 29 frames, scored by `make
        check-reference`), and it is the one document that can test this: 6
        of its 7 dynamic bones are the two rabbit ears, no dynamic bone's own
        angle moves, and no bone subscribes to wind.  Turning the feature on
        makes the ears WORSE, not better - mean positional error 60.6 px ->
        62.6 px on the right ear, 65.2 -> 66.0 on the left.  So the model is
        not merely unverified, it is measurably not an improvement.

        Read that with care, though, because the baseline is bad too: with
        dynamics OFF those ears are already ~60 px out, against 0.3-3.5 px
        for every layer of the other two reference documents.  Something
        else in that rig is wrong as well, and until it is found the dynamics
        signal is swamped.  Ruled out so far: scale inheritance (fixed
        separately, and it did improve the ears from ~78 px to ~60 px),
        the four `squash_stretch_scaling` cross-axis formulas, the four
        falloffs, and control bones (its three control drivers barely move).
        The skin weights themselves were checked point by point and are
        sane - each ear point is 95%+ dominated by its nearest bone.

        Cost note: the state at frame F depends on every frame before it, so
        this simulates start_frame..F on each call, now with one keyed
        world-matrix build per frame on top.  Results are cached per
        (skeleton, frame, Smart Bone context) by the caller's own
        Exporter._skin_data, which is what keeps that from being quadratic in
        practice.

        Args:
          frame: the frame to report angles for.
          exporter: supplies the settings flag, the document (start frame,
            fps) and the active Smart Bone context for channel evaluation.

        Returns:
          {bone index: angle in radians} for the bones simulated at `frame`.
          Callers fall back to the keyed `anim_angle` for any bone absent
          from the mapping.
        """
        if not exporter.settings.bone_dynamics:
            return {}
        # Candidates: every bone whose switch is EVER on, on the main timeline
        # or inside a Smart Bone action pose.  This is only a cheap prefilter -
        # whether the switch is on at any given frame is asked again below,
        # per frame, because it is a keyframed Bool channel and not a constant.
        candidates = [i for i, b in enumerate(self.bones) if b.dynamics_ever_on]
        if not candidates:
            return {}
        document = exporter.document
        start = float(document.start_frame)
        stop = float(frame)
        on_at_stop = [i for i in candidates
                      if self.bones[i].dynamics_on(stop, exporter)]
        if not on_at_stop:
            return {}
        if stop <= start:
            return {i: exporter.eval(self.bones[i].anim_angle, start) for i in on_at_stop}
        fps = float(document.fps) or 24.0
        x = {i: exporter.eval(self.bones[i].anim_angle, start) for i in candidates}
        v = {i: 0.0 for i in candidates}
        parents = {i: self.bones[i].parent for i in candidates}
        # Sub-stepping keeps the explicit integrator stable for a stiff spring;
        # 4 steps a frame is comfortably inside the stability limit for every
        # spring/damping pair present in the corpus.
        substeps = 4
        h = 1.0 / substeps
        # Three consecutive keyed poses are kept so the parent's world angular
        # velocity and acceleration, and the bone's own pivot acceleration,
        # are available as plain second differences.
        previous = self._keyed_world_state(start - 1.0, exporter, candidates, parents)
        current = self._keyed_world_state(start, exporter, candidates, parents)
        f = start
        while f < stop - 1e-9:
            f = min(f + 1.0, stop)
            following = self._keyed_world_state(f, exporter, candidates, parents)
            step = f - (f - 1.0)                      # always 1.0; kept for clarity
            # The switch is asked once per frame, not once per sub-step: it is
            # keyframed at whole frames, so sub-stepping it would only cost
            # time.  A bone whose dynamics is OFF this frame is pinned to its
            # keyed angle with zero velocity, so it follows the keys exactly
            # and re-enters the simulation from rest when it turns back on.
            for i in candidates:
                bone = self.bones[i]
                target = exporter.eval(bone.anim_angle, f)
                if not bone.dynamics_on(f, exporter):
                    x[i], v[i] = target, 0.0
                    continue
                # Parent world rotation, as a velocity and an acceleration in
                # radians per second.  Zero for a root bone, and zero whenever
                # the parent holds still - which is what makes this a strict
                # superset of the old own-angle-only model.
                # Differences are wrapped into (-pi, pi] before use: atan2
                # jumps by 2*pi at the branch cut, and an unwrapped jump would
                # read as an enormous angular acceleration and fling the bone.
                back = _wrap_angle(current.angle[i] - previous.angle[i])
                forward = _wrap_angle(following.angle[i] - current.angle[i])
                parent_rate = (forward + back) / (2.0 * step)
                parent_accel = (forward - back) / (step * step)
                for _ in range(substeps):
                    accel = (bone.spring_force * (target - x[i])
                             - bone.damping_force * (v[i] + parent_rate)
                             - parent_accel)
                    v[i] += accel * h
                    x[i] += v[i] * h
            previous, current = current, following
        return {i: x[i] for i in on_at_stop}

    def _keyed_world_state(self, frame: float, exporter: "Exporter",
                            candidates: Sequence[int],
                            parents: dict[int, int]) -> "KeyedWorldState":
        """The keyed (no-dynamics) world angle of each candidate's PARENT, the
        candidate's own world angle, and its pivot, at `frame`.

        "Keyed" is the point: this is the pose the animator actually drew, so
        it can be built without knowing any simulated angle and therefore
        without recursing into dynamic_angles.  See that method's WHAT IS
        STILL GUESSED note for what taking the parent's keyed rotation rather
        than its simulated one costs.

        A root bone (`parent < 0`) reports a parent angle of 0: there is
        nothing above it to be dragged by.
        """
        matrices = self._world_matrices(frame, exporter, {})
        angle: dict[int, float] = {}
        world: dict[int, float] = {}
        pivot: dict[int, tuple[float, float]] = {}
        for i in candidates:
            parent = parents[i]
            angle[i] = (math.atan2(matrices[parent].b, matrices[parent].a)
                        if parent >= 0 else 0.0)
            world[i] = math.atan2(matrices[i].b, matrices[i].a)
            pivot[i] = (matrices[i].e, matrices[i].f)
        return KeyedWorldState(angle, world, pivot)

    def _ik_pairs(self, frame: float, exporter: "Exporter") -> dict[int, tuple[int, int]]:
        """bone1 index -> (bone2 index, target index) for every bone2 whose
        `target_bone` currently names another bone in this same skeleton -
        bone1 is bone2's own parent, the other half of Moho's 2-bone chain.
        A bone2 with no parent (nothing to bend alongside it) or a
        self-referencing/out-of-range target is skipped rather than raising,
        since a stray/legacy `target_bone` value should degrade to plain FK,
        not break the export."""
        n = len(self.bones)
        pairs: dict[int, tuple[int, int]] = {}
        for bone2_index, bone2 in enumerate(self.bones):
            target = int(exporter.eval(bone2.target_bone, frame))
            if not (0 <= target < n) or target == bone2_index:
                continue
            bone1_index = bone2.parent
            if bone1_index < 0:
                continue
            pairs[bone1_index] = (bone2_index, target)
        return pairs

    @staticmethod
    def _solve_ik_bend(bend_reference: float, p0: Vec2, length1: float,
                        length2: float, target: Vec2) -> Optional[tuple[float, float]]:
        """Solve this 2-bone IK pair, picking whichever of the two
        mirror-image elbow/knee solutions bends toward `bend_reference` -
        returns (bone1's world angle, bone2's local angle), or None if
        neither candidate reaches (a degenerate chain; see
        _solve_two_bone_ik).

        `bend_reference` is bone2's OWN stored angle evaluated AT THE
        CURRENT FRAME (not at frame 0 - see below). Solves for both
        `sign = +1` and `sign = -1`, then keeps whichever gives bone2's LOCAL
        angle (relative to bone1) closest to it: the animator records which
        way the joint should fold, and the solve follows that side.

        **`bend_reference` must be per-frame.** An earlier version used
        `Channel.of(bone2.anim_angle).val[0]` - the frame-0 keyframe - on the
        stated assumption that an IK-driven bone's own `anim_angle` is frozen
        and therefore meaningless except as a rest-pose hint. **That
        assumption was wrong**, and only half the corpus looked like it held:
        `SketchBone.animeproj`'s RIGHT shin (`B27`) really is constant at
        5.1 degrees across all 15 of its keyframes, but its LEFT shin (`B22`)
        steps from 351.2 to 449.4 degrees (i.e. -8.8 -> +89.4 once
        normalised - a SIGN CHANGE, so a bend-side change) between its
        keyframes at frames 43 and 49, alongside that leg's ankle bone
        flipping on the same frame (`B23.flip_h`, see Bone's docstring).
        Interpolated, that reference crosses zero between frames 43 and 44,
        so the chosen side switches exactly there and then holds for the
        rest of the walk - confirmed by measuring the solved knee angle on
        all 120 frames (one clean A->B transition at 43->44; the only other
        sign changes are 0.008-0.16 degree noise on an auto-stretched, i.e.
        perfectly straight, leg around frames 18-20). The switch only
        becomes VISIBLE around frames 46-47, once the knee has folded far
        enough to see (0 degrees at 44, 36 degrees by 46). Pinning the
        reference to frame 0 instead kept that knee folding the original
        standing-still way for the whole second half of the walk.

        Comparing the SOLVED local angle (rather than using the sign of
        `bend_reference` directly as the law-of-cosines `sign` parameter,
        tried first and found wrong) is also required: the naive version
        picked the WRONG side for both legs at frame 7 (an exact keyframe,
        so not an interpolation artifact) - both thighs swung 50-56 degrees
        TOWARD the centre line before the knee bent back out to the correct
        foot position, crossing the legs into a pretzel instead of the
        reference's plain outward stance. The sign of a bone's own local
        angle and the sign of the `sign` parameter that reproduces it are
        related but NOT identical; solving both and comparing outcomes
        sidesteps deriving that relationship algebraically."""
        rest_angle2 = ((bend_reference + math.pi) % (2.0 * math.pi)) - math.pi
        candidates = [s for s in (_solve_two_bone_ik(p0, length1, length2, target, sign)
                                   for sign in (1.0, -1.0)) if s is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda s: abs(((s[1] - rest_angle2 + math.pi)
                                                    % (2.0 * math.pi)) - math.pi))

    def _solve_ik_pair(self, bone1_index: int, ik_pairs: dict[int, tuple[int, int]],
                        out: list[Optional[Mat2D]], pos1: Vec2, scale1: float,
                        parent_matrix: Optional[Mat2D], frame: float,
                        exporter: "Exporter"
                        ) -> Optional[tuple[Mat2D, Mat2D, tuple[int, Mat2D, Mat2D]]]:
        """If `bone1_index` is the base of a 2-bone IK pair, return
        (bone1's world matrix, bone1's orientation,
        (bone2 index, bone2's world matrix, bone2's orientation));
        otherwise None (the caller falls back to plain FK for this bone).
        "Orientation" is the matching entry for `_world_matrices`'s `orient[]`
        chain - rotation only, no scale or translation - see that method's
        NOTE ON FLIP PROPAGATION for why it has to be a composed matrix and
        not a scalar angle, and this method's own note at the return
        statement for why IK's orientation never carries a flip.
        Needs `out[target_index]` already resolved - guaranteed by `add`'s
        extended topological order."""
        pair = ik_pairs.get(bone1_index)
        if pair is None or parent_matrix is None:
            return None
        bone1 = self.bones[bone1_index]
        bone2_index, target_index = pair
        bone2 = self.bones[bone2_index]
        pos2 = Vec2.of(exporter.eval(bone2.anim_pos, frame))
        scale2 = exporter.eval(bone2.anim_scale, frame)
        p0 = parent_matrix.apply(pos1)
        target = out[target_index].apply(Vec2(0.0, 0.0))
        # The law-of-cosines solve needs how far bone2's origin ACTUALLY sits
        # from bone1's - bone2.anim_pos's own magnitude, NOT bone1.length.
        # Confirmed these two differ for real bones (SketchBone.animeproj's
        # right leg: bone1.length == 0.162607, but bone2.anim_pos.length()
        # == 0.183273 - a ~13% gap that briefly looked negligible but, once
        # multiplied by an auto-stretch factor of ~1.86x, threw bone2's tip
        # roughly a third of a unit away from the IK target it was meant to
        # reach - confirmed by comparing this solve's own elbow position
        # against bone1_matrix.compose(...)'s ACTUAL resulting origin below;
        # they only coincide once this uses pos2's real length.
        base_length1 = pos2.length() * scale1
        base_length2 = bone2.length * scale2
        stretch = self._ik_auto_stretch(bone1, bone2, base_length1, base_length2,
                                         p0.distance_to(target))
        length1 = base_length1 * stretch
        length2 = base_length2 * stretch
        # Evaluated at THIS frame, not frame 0 - see _solve_ik_bend's docstring
        # for the confirmed case where the two differ and frame 0 is wrong.
        bend_reference = exporter.eval(bone2.anim_angle, frame)
        solved = self._solve_ik_bend(bend_reference, p0, length1, length2, target)
        if solved is None:
            return None
        world_angle1, local_angle2 = solved
        parent_origin = parent_matrix.apply(Vec2(0.0, 0.0))
        parent_x_axis = parent_matrix.apply(Vec2(1.0, 0.0)).minus(parent_origin)
        local_angle1 = world_angle1 - math.atan2(parent_x_axis.y, parent_x_axis.x)
        c1, s1 = math.cos(local_angle1), math.sin(local_angle1)
        bone1_matrix = parent_matrix.compose(
            Mat2D(c1 * scale1 * stretch, s1 * scale1 * stretch, -s1, c1, pos1.x, pos1.y))
        # bone2_matrix is built directly in WORLD space (elbow + world_angle2)
        # rather than via bone1_matrix.compose(...) - composing a ROTATED
        # child through bone1_matrix's own ANISOTROPIC scale (see the module
        # docstring's NOTE ON SCALE - only the first column is stretched)
        # shears the result: confirmed directly on this same leg at frame 49
        # - bone2's tip came out 0.569 units from the elbow instead of the
        # 0.324 the law-of-cosines solve above actually calls for (a factor
        # of ~3.08, not the intended ~1.76x stretch), because compose() mixes
        # bone1's two differently-scaled columns in proportion to bone2's OWN
        # local angle. World-space construction sidesteps that entirely:
        # nothing downstream depends on bone2_matrix being reachable by
        # composing FROM bone1_matrix, only on what `out[]` holds.
        elbow = p0.plus(Vec2(math.cos(world_angle1), math.sin(world_angle1)).scaled(length1))
        world_angle2 = world_angle1 + local_angle2
        c2, s2 = math.cos(world_angle2), math.sin(world_angle2)
        bone2_matrix = Mat2D(c2 * scale2 * stretch, s2 * scale2 * stretch, -s2, c2,
                              elbow.x, elbow.y)
        # Orientation (rotation only, no scale/translation) for the caller's
        # `orient[]` chain - see world_matrices' NOTE ON FLIP PROPAGATION.
        # col2 of each matrix above is ALREADY unit magnitude with no flip
        # baked in (`(-s1, c1)` / `(-s2, c2)`), which is what makes lifting it
        # straight out safe here: this solve has never applied `flip_h`/
        # `flip_v` to either bone (KNOWN GAP, unrelated to and pre-existing
        # this method's fix - an IK-solved bone cannot currently be flipped).
        # A future descendant of one of these two bones still needs SOME
        # orientation to compose against, so this returns the identity-flip
        # rotation both bones actually have today rather than leaving it None
        # (which crashed `_world_matrices` outright the first time this was
        # exercised - `SketchBone.animeproj`'s own leg IK).
        orient1 = Mat2D(c1, s1, -s1, c1, 0.0, 0.0)
        orient2 = Mat2D(c2, s2, -s2, c2, 0.0, 0.0)
        return bone1_matrix, orient1, (bone2_index, bone2_matrix, orient2)

    @staticmethod
    def _ik_auto_stretch(bone1: "Bone", bone2: "Bone", length1: float, length2: float,
                          distance: float) -> float:
        """How much to stretch BOTH bones of a 2-bone IK pair (a uniform
        factor applied to each) so the chain can reach a `distance` beyond
        its combined rest length `length1 + length2` - Moho's "auto stretch"
        (`Bone.scaling_mode == 2`, capped by `Bone.max_auto_scaling`).

        Returns 1.0 (no stretch) whenever the target is already in reach, or
        when NEITHER bone has auto-stretch enabled (a scaling_mode != 2 bone
        keeps its fixed length even if that leaves the chain short of the
        target - matching a non-stretchy limb).  When only one of the two
        bones is stretchy, that one bone alone cannot generally reach an
        arbitrary target angle on its own without also changing bone1's
        world angle - i.e. the two bones stretch TOGETHER (a real,
        confirmed 2-bone gap, not a rare edge case: `SketchBone.animeproj`'s
        leg bones both carry `scaling_mode == 2` with the SAME
        `max_auto_scaling`, and a stretched kicking pose - the target
        sitting up to ~1.9x the chain's rest reach - could not otherwise be
        reached at all, leaving the foot visibly detached from the leg."""
        reach = length1 + length2
        if distance <= reach or reach <= 1e-9:
            return 1.0
        max1 = (bone1.max_auto_scaling
                if bone1.scaling_mode == SQUASH_STRETCH_SCALING_MODE else 1.0)
        max2 = (bone2.max_auto_scaling
                if bone2.scaling_mode == SQUASH_STRETCH_SCALING_MODE else 1.0)
        return min(distance / reach, max1, max2)


def _solve_two_bone_ik(p0: Vec2, length1: float, length2: float, target: Vec2,
                        sign: float) -> Optional[tuple[float, float]]:
    """Analytic 2-bone IK (law of cosines): given bone1 originates at `p0`
    (world space) with length `length1`, followed by bone2 with length
    `length2`, return (bone1's WORLD-space angle, bone2's LOCAL angle
    relative to bone1) so that bone2's tip reaches `target`.

    `sign` (+1.0/-1.0) picks which of the two mirror-image elbow positions
    to use - the other root of the same law-of-cosines equation would bend
    the joint the wrong way. Returns None for a degenerate chain (a
    near-zero length, or `target` coinciding with `p0`), letting the caller
    fall back to plain FK rather than divide by zero.

    An unreachable target (too far or, with unequal lengths, too close) is
    clamped to the nearest reachable distance, matching the usual behaviour
    of a 2-bone IK rig (the limb fully extends/folds rather than the solve
    failing outright).
    """
    if length1 <= 1e-9 or length2 <= 1e-9:
        return None
    delta = target.minus(p0)
    distance = delta.length()
    if distance <= 1e-9:
        return None
    reach_min = abs(length1 - length2) + 1e-9
    reach_max = length1 + length2 - 1e-9
    distance = max(reach_min, min(distance, reach_max))
    base_angle = math.atan2(delta.y, delta.x)
    cos_beta = (length1 * length1 + distance * distance - length2 * length2) \
        / (2.0 * length1 * distance)
    beta = math.acos(max(-1.0, min(1.0, cos_beta)))
    world_angle1 = base_angle + sign * beta
    elbow = p0.plus(Vec2(math.cos(world_angle1), math.sin(world_angle1)).scaled(length1))
    to_target = target.minus(elbow)
    world_angle2 = math.atan2(to_target.y, to_target.x)
    return world_angle1, world_angle2 - world_angle1


@dataclass(frozen=True)
class CurvePoint:
    """One point along a Curve, with the data needed to reconstruct the two
    Bezier handles either side of it - see BezierReconstructor and the module
    docstring's BEZIER CURVES section.  `point_index` indexes into the owning
    Mesh's `points` list (a curve does not store its own coordinates - point
    *position* is shared with every curve/shape that references it).

    In the older `1021` format generation a curve point carries only
    `point`, `smoothness` and `segments_on`; the four weight/offset fields do
    not exist at all - see _build for how they are defaulted."""
    point_index: int
    smoothness: Any
    weight_in: Any
    weight_out: Any
    offset_in: Any
    offset_out: Any
    segments_on: bool

    # Neutral handle shape, used when the `1021` format omits these fields.
    # weight 1.0 makes handle_length collapse to distance * smoothness, and
    # offset 0.0 leaves the handle direction unrotated (see
    # BezierReconstructor.handle).  Both are also the single most common
    # stored value in the documents that DO carry the fields: 1.0 on 23.4% of
    # 52,722 weight values, 0.0 on 26.5% of 52,738 offset values, each the
    # clear mode of its distribution.  See docs/moho-project-file-format.md
    # § 7.3 - this is a reasoned default, NOT a value confirmed against a Moho
    # export of a `1021` document.
    DEFAULT_WEIGHT = 1.0
    DEFAULT_OFFSET = 0.0

    @staticmethod
    def _build(raw: dict) -> "CurvePoint":
        """Build one curve point, tolerating the `1021` format's shorter form.

        `weight_in`/`weight_out`/`offset_in`/`offset_out` are read with
        .get(): every `1038`/`1045` curve point has all seven fields, but
        every `1021` one has exactly three, and plain indexing turned that
        into a hard KeyError that made such a document impossible to load.
        """
        return CurvePoint(
            point_index=raw["point"],
            smoothness=raw["smoothness"],
            weight_in=raw.get("weight_in", CurvePoint.DEFAULT_WEIGHT),
            weight_out=raw.get("weight_out", CurvePoint.DEFAULT_WEIGHT),
            offset_in=raw.get("offset_in", CurvePoint.DEFAULT_OFFSET),
            offset_out=raw.get("offset_out", CurvePoint.DEFAULT_OFFSET),
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
    STROKES sections for what a non-1.0 or varying width means.

    `parent` is Moho's per-POINT bone binding ("link points to bone"): a bone
    index this single point follows rigidly, overriding whatever binding its
    LAYER has.  `-2` means "no per-point binding, use the layer's" and is by
    far the common case (7,365 of ~12,400 points across the 19 sample
    documents); `-1` also occurs (551 points) and is treated the same way.
    A real bone index appears on roughly 4,000 points spread over 119
    meshes, so this is a mainstream feature rather than a curiosity -
    `Bandit.mohoproj`'s `Leg_F` pins 9 of its 28 points to bone 11, and its
    `Ears` pins all 20 across five different bones.  See
    Exporter._deformed_point_mapper.
    """
    position: Any
    width: Any
    parent: int = -2

    @staticmethod
    def _build(raw: dict) -> "MeshPoint":
        return MeshPoint(position=raw["position"], width=raw["width"],
                          parent=raw.get("parent", -2))


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

    def __init__(self, points: list[MeshPoint], curves: list[Curve], shapes: list[Shape],
                 shape_order: Any = None):
        self.points = points
        self.curves = curves
        self.shapes = shapes
        # Raw `mesh.shape_order` channel (a String of "|"-separated shape IDs)
        # or None when the field is absent - see draw_order().
        self.shape_order = shape_order
        self._has_point_bones: Optional[bool] = None   # see has_point_bones

    @property
    def has_point_bones(self) -> bool:
        """True when at least one point carries its own bone binding
        (`MeshPoint.parent >= 0`).

        This gates which geometry order the exporter uses, so it decides
        whether a mesh's output can move at all - see
        Exporter._geometry_and_mapper.
        """
        if self._has_point_bones is None:
            self._has_point_bones = any(p.parent >= 0 for p in self.points)
        return self._has_point_bones

    def draw_order(self) -> list[Shape]:
        """`shapes` in Moho's own back-to-front draw order.

        Moho stores that order twice: implicitly as the order of `shapes`,
        and explicitly in the `shape_order` channel, a "|"-separated list of
        shape IDs. They agree on 565 of the 614 meshes in this repository's
        19 sample documents, and where they agree this returns `shapes`
        unchanged.

        Where they DISAGREE (49 meshes across 6 documents), `shape_order` is
        NOT the authority and is deliberately ignored, on three independent
        pieces of evidence:

        1. In **47 of those 49** the ID list is strictly ASCENDING while the
           file order is not - the signature of an ID registry, not of an
           artist-chosen z-order. `Bandit.mohoproj`'s `Arm_B` stores
           "1|6|7|9|10" while its shapes sit in file order 10, 9, 6, 1, 7,
           close to the exact reverse. (The 2 exceptions are Bandit's
           `Leg_F`/`Leg_F 2`, both "0|1|4|2|3|7" - still near-ascending,
           differing only in where id 7 sits.)
        2. Reordering the shapes by it **breaks `combo_mode` grouping**,
           which ShapeGroupRenderer builds from ADJACENCY in file order: a
           boolean-combination run stops being contiguous, and rendering
           Bandit that way aborts outright rather than producing a picture.
        3. It reproduces the conclusion an earlier note in this module's
           docstring already recorded from its own experiment - that
           trusting the field "draws almost everything back-to-front".

        So file order wins, always, and this method changes no output. It
        exists to put that rule in one named place, because the field looks
        authoritative enough that it has now been investigated twice.

        NOT handled: a mesh with `anim_shape_order` true, i.e. a z-order the
        animator ANIMATED. It is false on all 614 meshes here, so nothing
        exercises it and no guess is made about which frame's order to use.
        """
        return self.shapes

    @staticmethod
    def _build(raw: dict, styles: StyleTable) -> "Mesh":
        return Mesh(
            points=[MeshPoint._build(p) for p in raw["points"]],
            curves=[Curve._build(c) for c in raw["curves"]],
            shapes=[Shape._build(s, styles) for s in raw["shapes"]],
            shape_order=raw.get("shape_order"),
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

    @property
    def timing_offset(self) -> int:
        """Frames by which Moho shifts this layer's own animation in time.

        NOT applied - and deliberately so.  Zero on 839 of the 842 layers in
        the sample; the only three that set it (`Rabbit.animeproj`'s
        `ProsBox`, `PROS` and `T I  PS`, all 45) have **no animated channel
        anywhere in their subtree**, verified by re-evaluating their geometry
        at frames 1/10/20/29 and getting identical output, and 45 is past the
        end of that document's own 1-29 frame range anyway.

        So nothing here exercises it, which means the sign (does a positive
        offset delay the animation or advance it?), the scope (the layer
        alone, or its descendants too?) and the interaction with an animated
        ANCESTOR are all unverifiable against this corpus.  Implementing it
        would be three guesses at once with no test that could fail, so it is
        read and counted (see moho2lottie.py's "timing_offset" warning)
        rather than guessed at.
        """
        return self._raw.get("timing_offset", 0) or 0

    @property
    def physics_dynamic(self) -> bool:
        """True when Moho moves this BoneLayer's whole rig with its own
        rigid-body physics simulation (wind/gravity) rather than any
        keyframed channel this tool can read - see the module docstring's
        KNOWN GAPS entry on physics. A layer where this is true can only
        ever render at its rest pose here, however many frames are sampled,
        since neither this module nor moho2lottie.py runs a physics
        simulation.

        THREE things have to line up, because the first two are defaults Moho
        writes everywhere and mean nothing on their own:

        1. `physics.enabled` and not `.static`.  True on EVERY layer of every
           sample document (902 layers checked directly), so this only rules
           out a layer that has been explicitly switched off.
        2. A non-zero `wind`/`gravity` *strength* on the owning `BoneLayer`
           (only that layer kind carries either field).  Also a default: a
           format-1045 re-save of `SketchBone.animeproj` from Moho Pro 14.4 -
           a document that uses no physics whatsoever - writes
           `wind.strength = 100.0` on ALL FIVE of its `BoneLayer`s.
        3. At least one bone that actually SUBSCRIBES, via `wind_dynamics`.
           This is the part that discriminates, and it is false on all 28
           bones of `Bandit.mohoproj` and all 94 of `SketchBone`.

        The result is that nothing in this corpus is physics-driven, which is
        a correction, not a gap.  This property used to fire for
        `Bandit.mohoproj`'s top-level "Bandit" layer on the strength of
        condition 2 plus an observation - "its keyframed bone channels do not
        account for the screen-spanning motion Moho's own render shows across
        frames 25-127".  They do account for it.  The channels were being
        read wrongly: Moho's cycle ACCUMULATES (see Channel._cycle_value),
        and once it does, this exporter tracks Moho's own 103 exported frames
        to within 0.73 px of horizontal travel over a 2430 px march.  There
        is no unexplained motion left to attribute to physics.

        `wind_dynamics` exists only from format 1045, so on an older file
        condition 3 can never be met.  That is the safe direction: those
        files predate the field, and nothing in them shows unexplained
        motion either.
        """
        if self.skeleton is None:
            return False
        physics = self._raw.get("physics") or {}
        if not physics.get("enabled") or physics.get("static", False):
            return False

        def _any_nonzero(field: str) -> bool:
            vals = (self._raw.get(field) or {}).get("strength", {}).get("val") or []
            return any(v != 0 for v in vals)

        if not (_any_nonzero("wind") or _any_nonzero("gravity")):
            return False
        return any(_channel_ever_true(b.wind_dynamics) for b in self.skeleton.bones)

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
                 styles: StyleTable, format_version: Any,
                 fps: float = 24.0, start_frame: int = 0, end_frame: int = 0):
        self.width = width
        self.height = height
        self.layers = layers            # top-level (root) layers
        self.styles = styles
        self.format_version = format_version
        self.fps = fps                  # project_data.fps - playback rate
        # project_data.start_frame/end_frame: the document's own render
        # range, in absolute frame numbers, BOTH ENDS INCLUSIVE on the Moho
        # side (used by a Lottie writer to convert into Lottie's ip/op).
        self.start_frame = start_frame
        self.end_frame = end_frame

    @classmethod
    def from_raw(cls, raw: dict) -> "Document":
        # Channel._cache is keyed by id() of the raw channel dict, which is
        # only unique among dicts that are alive at the same time.  Once a
        # Document is dropped, CPython reuses those ids for the next parsed
        # document, so a process that loads more than one document in turn
        # (a batch export, a comparison harness) would read a previous
        # document's cached Channel for an unrelated field - producing wrong
        # values or a TypeError, not an obvious failure.  Dropping the cache
        # at every load makes that impossible; entries for a document that is
        # still alive simply get rebuilt on next use.
        Channel.reset_cache()
        styles = StyleTable.build(raw.get("styles") or [])
        layers = [Layer._build(item, styles) for item in raw["layers"]]
        pd = raw["project_data"]
        doc = cls(pd["width"], pd["height"], layers, styles, raw.get("version"),
                  fps=pd.get("fps", 24.0),
                  start_frame=pd.get("start_frame", 0),
                  end_frame=pd.get("end_frame", 0))
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


def build_path_bezier(geometries: list[CurveGeometry], edges: Sequence[Edge],
                       to_px: Callable[[Vec2], Vec2],
                       visible_only: bool = False, close: bool = True) -> list[dict]:
    """Build one shape's outline as Lottie bezier dicts - the Lottie
    counterpart of build_path_d().

    Returns ONE dict per subpath, because Lottie's "sh" shape element holds
    exactly one bezier: a shape whose outline falls into two disconnected
    runs becomes two "sh" elements in the same group.  build_path_d() writes
    the same break as a second "M" inside one `d` string.

    Each dict has the shape Lottie expects for a bezier value:
    {"v": [[x, y], ...], "i": [[dx, dy], ...], "o": [[dx, dy], ...], "c": bool}.
    Lottie's `i`/`o` are the in/out tangents *relative to their own vertex*,
    unlike build_path_d()'s absolute SVG control points - so a segment
    leaving vertex k contributes `o[k] = c1 - p0`, and the vertex it arrives
    at gets `i[k+1] = c2 - p1`.  A vertex shared by two segments therefore
    takes its `o` from the outgoing segment and its `i` from the incoming
    one.

    `visible_only` mirrors build_path_d(): it skips any segment currently
    hidden (CurvePoint.segments_on / SegmentGeometry.on) and starts a fresh
    subpath after each such gap.

    `close` mirrors build_path_d()'s own `close` parameter: when True (the
    default), a subpath whose end coincides with its start is marked "c":
    True and its duplicate closing vertex is dropped (see close_current()
    below). When False, that duplicate vertex is kept and "c" stays False -
    a genuinely different bezier, not just a formatting choice: an open path
    gets line-cap ends at the seam when stroked, a closed one gets a
    seamless join there. Pass close=True for a fill; NEVER for a plain
    (non-tapered) stroke - see build_path_d()'s own docstring for why Moho's
    own exporter never closes a stroke path either.

    Coordinates are rounded to 3 decimals, matching build_path_d()'s
    f"{x:.3f}", so the two builders describe the same curve to the same
    precision.
    """
    traced = PathTracer.trace(geometries, edges)
    out: list[dict] = []
    current: Optional[dict] = None
    first: Optional[Vec2] = None
    last: Optional[Vec2] = None

    def close_current() -> None:
        """Finish the subpath being built, marking it closed when `close` is
        set and it returns to its own start.

        A closed Lottie bezier does not repeat the first vertex, so the
        duplicate endpoint is dropped - but its incoming tangent is the
        wrap-around segment's control point and must be carried onto the
        surviving first vertex before the drop, or the last curve of a
        closed shape flattens into a straight line.
        """
        nonlocal current
        if current is None:
            return
        if close and len(current["v"]) > 1 and first is not None and last is not None \
                and last.distance_to(first) < 1e-9:
            current["c"] = True
            current["i"][0] = current["i"][-1]     # carry the wrap-around tangent
            current["v"].pop()
            current["i"].pop()
            current["o"].pop()
        out.append(current)
        current = None

    for seg in traced:
        if visible_only and not geometries[seg.curve].segments[seg.segment].on:
            close_current()
            last = None
            continue
        if current is None or last is None or last.distance_to(seg.p0) > 1e-9:
            close_current()
            m = to_px(seg.p0)
            current = {"v": [[round(m.x, 3), round(m.y, 3)]],
                       "i": [[0.0, 0.0]], "o": [[0.0, 0.0]], "c": False}
            first = seg.p0
        p0, c1, c2, p1 = to_px(seg.p0), to_px(seg.c1), to_px(seg.c2), to_px(seg.p1)
        current["o"][-1] = [round(c1.x - p0.x, 3), round(c1.y - p0.y, 3)]
        current["v"].append([round(p1.x, 3), round(p1.y, 3)])
        current["i"].append([round(c2.x - p1.x, 3), round(c2.y - p1.y, 3)])
        current["o"].append([0.0, 0.0])
        last = seg.p1
    close_current()
    return out


class TaperedStrokeOutliner:
    """Builds the *filled outline* of a stroke whose width varies along its
    length, since SVG's own <path stroke-width> cannot - see the module
    docstring's TAPERED STROKES section.
    """

    def __init__(self, samples_per_segment: int = 10):
        self.samples_per_segment = samples_per_segment

    def build(self, geometries: list[CurveGeometry], edges: Sequence[Edge],
              to_px: Callable[[Vec2], Vec2], stroke_width_px: float) -> str:
        pieces = [self._outline_one_run(run, to_px, stroke_width_px)
                  for run in self._traced_runs(geometries, edges)]
        return " ".join(p for p in pieces if p)

    def _traced_runs(self, geometries: list[CurveGeometry], edges: Sequence[Edge]):
        """Group a shape's traced outline into contiguous runs of
        (p0, c1, c2, p1, w0, w1), split at any segments_on==False gap.

        Shared by build() (SVG) and build_bezier() (Lottie) - pure data
        preparation, no output-format-specific formatting, so extracting it
        cannot change either writer's behaviour.
        """
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
        return runs

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

    def build_bezier(self, geometries: list[CurveGeometry], edges: Sequence[Edge],
                      to_px: Callable[[Vec2], Vec2], stroke_width_px: float,
                      cap_segments: int = 8) -> list[dict]:
        """Lottie counterpart of build() - the filled outline of a stroke
        whose width varies along its length, as Lottie bezier dicts.

        Returns one dict per RUN, exactly like build_path_bezier(): a CLOSED
        run (a ring, e.g. a circle's outline) returns TWO dicts (an outer and
        an inner counter-wound loop, matching build()'s own two-loop
        SVG output) meant to be painted together with an evenodd fill rule so
        the hole survives; an OPEN run returns ONE dict (a single closed
        "capsule" polygon).

        The outline itself is a SAMPLED POLYGON, matching build()'s own
        approach of stepping self.samples_per_segment times per Bezier
        segment and connecting the samples with straight lines - so every
        vertex here is written with ZERO tangents (i=o=[0,0]): a Lottie
        bezier with all-zero tangents renders as a polyline, exactly what
        build() already produces via SVG "L" commands. This is intentionally
        NOT a smooth curve fit; it is exactly as faceted as build()'s own SVG
        output, at the same sample density.

        Rounded end caps are the one place this cannot match build() bit for
        bit: build() emits a single SVG elliptical arc ("A"), which has no
        Lottie/cubic-bezier equivalent. This approximates the same half-turn
        with `cap_segments` straight segments instead - visibly a small
        polygon rather than a perfect arc, most noticeable at a large stroke
        width sampled with few segments. Not confirmed against a real Lottie
        player; only confirmed to close the outline correctly by
        construction (see the docstring's TAPERED STROKES section in the
        module header for the underlying offset-curve technique itself).
        """
        out: list[dict] = []
        for run in self._traced_runs(geometries, edges):
            out.extend(self._outline_one_run_bezier(run, to_px, stroke_width_px, cap_segments))
        return out

    def _sample_offsets(self, run, to_px: Callable[[Vec2], Vec2], stroke_width_px: float):
        """Sample `run` and compute its left/right offset curves, in pixel
        space, at each sample's own interpolated width.

        Deliberately a FRESH implementation rather than a refactor of
        _outline_one_run's own sampling loop: the two must produce the same
        polygon, but sharing the code would mean touching the one method
        this module's byte-identical SVG regression check exercises through
        two of the five gated reference documents (Bandit, ReparentBone) -
        not worth the regression risk for what is otherwise a handful of
        duplicated lines.  Returns None for a run too short to offset (fewer
        than 2 samples), matching _outline_one_run's own "" / no-output case.
        """
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
            return None

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
        start_radius = stroke_width_px * pixels[0][1] / 2.0
        end_radius = stroke_width_px * pixels[-1][1] / 2.0
        return left, right, closed, start_radius, end_radius

    @staticmethod
    def _polygon_bezier(points: Sequence[Vec2], closed: bool) -> dict:
        """One Lottie bezier dict from a plain polygon: all tangents zero, so
        it renders as straight lines between the given points."""
        v = [[round(p.x, 3), round(p.y, 3)] for p in points]
        zero = [[0.0, 0.0]] * len(v)
        return {"v": v, "i": list(zero), "o": list(zero), "c": closed}

    @staticmethod
    def _arc_points(center: Vec2, start: Vec2, end: Vec2, segments: int) -> list[Vec2]:
        """`segments` points approximating the half-turn arc from `start` to
        `end` around `center`, going the short way - see build_bezier()'s
        own docstring for why this is a polygon approximation, not a true
        arc, and endpoints are EXCLUDED (the caller already has them from the
        left/right offset curves, so including them here would duplicate a
        vertex)."""
        r = (start - center).length()
        if r < 1e-9 or segments < 1:
            return []
        a0 = math.atan2(start.y - center.y, start.x - center.x)
        a1 = math.atan2(end.y - center.y, end.x - center.x)
        # Sweep the SHORT way around - a stroke's end cap is a half-turn, so
        # the two candidate sweeps differ by roughly pi either direction;
        # picking the smaller keeps the cap on the outside of the stroke,
        # matching build()'s own "A ... 0 0 1" sweep-flag choice.
        delta = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        return [Vec2(center.x + r * math.cos(a0 + delta * (i + 1) / (segments + 1)),
                     center.y + r * math.sin(a0 + delta * (i + 1) / (segments + 1)))
                for i in range(segments)]

    def _outline_one_run_bezier(self, run, to_px: Callable[[Vec2], Vec2],
                                 stroke_width_px: float, cap_segments: int) -> list[dict]:
        offsets = self._sample_offsets(run, to_px, stroke_width_px)
        if offsets is None:
            return []
        left, right, closed, start_radius, end_radius = offsets

        if closed:
            return [self._polygon_bezier(left, True),
                    self._polygon_bezier(list(reversed(right)), True)]

        points = list(left)
        if end_radius > 0.05:
            mid = left[-1].scaled(0.5) + right[-1].scaled(0.5)
            points += self._arc_points(mid, left[-1], right[-1], cap_segments)
        points += list(reversed(right))
        if start_radius > 0.05:
            mid = right[0].scaled(0.5) + left[0].scaled(0.5)
            points += self._arc_points(mid, right[0], left[0], cap_segments)
        return [self._polygon_bezier(points, True)]


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
    # Each takes (distance_to_bone_segment, bone.strength).  "inv_d2" is the
    # default (RenderSettings.bone_weight_falloff).  The four are no longer
    # indistinguishable: scored against Moho's own reference frames they
    # separate clearly, and they DISAGREE between the two documents that have
    # one - inv_d2 wins SketchBone (34.15 total against linear's 43.58) while
    # linear wins Bandit's many-bone layers.  So none of them is Moho's real
    # function and the default is the best of four, not a decoding.  See the
    # module docstring's BONE DEFORMATION section for the table.
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
        # The BIND pose must be the rig as modelled - frame 0 with NO Smart
        # Bone dial applied.  world_matrices() evaluates through
        # exporter.eval(), which honours exporter._active_actions, so without
        # clearing them first the "rest" matrices come back as frame 0 PLUS
        # whatever pose the current frame's dials are driving, and
        # rest_to_pose then silently cancels part of the very deformation it
        # is meant to express.  Harmless on this corpus only because every
        # active pose here is flat (see Channel.eval), i.e. contributes a
        # zero offset - a non-flat pose would corrupt every bone downstream
        # of it, since each bone's world matrix composes its parents'.
        saved = exporter._active_actions
        exporter._active_actions = []
        try:
            rest = skeleton.world_matrices(0.0, exporter)
        finally:
            exporter._active_actions = saved
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


def _wrap_angle(radians: float) -> float:
    """`radians` mapped into (-pi, pi].

    Used on DIFFERENCES between two angles read out of a matrix with atan2.
    Two poses a degree apart can straddle the branch cut and read as 2*pi
    apart, which as an angular acceleration would be enormous - see
    Skeleton.dynamic_angles.
    """
    return (radians + math.pi) % (2.0 * math.pi) - math.pi


@dataclass(frozen=True)
class KeyedWorldState:
    """One frame of the keyed (no-dynamics) pose, as Skeleton.dynamic_angles
    needs it: per candidate bone, its PARENT's world angle, its own world
    angle, and its own world pivot.  See Skeleton._keyed_world_state."""
    angle: dict[int, float]                    # parent's world angle, radians
    world: dict[int, float]                    # this bone's world angle, radians
    pivot: dict[int, tuple[float, float]]      # this bone's world origin


@dataclass(frozen=True)
class MatrixStep:
    """One step of a DeformChain: apply a plain affine transform."""
    matrix: Mat2D


@dataclass(frozen=True)
class SkinStep:
    """One step of a DeformChain: cross into `bone_layer`'s own coordinate
    space, deforming the point by its skeleton.

    `bound_bone_index` >= 0 means whatever is bound into this skeleton
    (the render target itself, or - for a BoneLayer nested inside another
    BoneLayer - the whole inner BoneLayer, see below) is *rigidly* bound to
    that one bone (Layer.parent_bone); -1 means flexible ("region") binding,
    blended across every bone in `subset` (every bone in the skeleton if
    `subset` is empty) - see Exporter._deformed_pixel_mapper, which is where
    that distinction is actually consumed.
    """
    bone_layer: Layer
    bound_bone_index: int
    subset: tuple[int, ...] = ()


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

    A BoneLayer nested inside another BoneLayer (e.g. a hand rig's own
    skeleton, nested inside the whole character's skeleton) closes out TWO
    SkinSteps, not one: the inner one binds `target` into the nested
    BoneLayer's own skeleton, exactly as for a plain (non-nested) mesh; the
    outer one must bind the *nested BoneLayer itself* into the outer
    skeleton, using THAT layer's own `parent_bone`/`flexi_bone_subset` -
    NOT the target's, and NOT left unbound. `bound_bone`/`bound_subset`
    below are captured from whichever layer was most recently walked (reset
    to that layer's own binding immediately after any SkinStep it closes),
    so this generalises to any nesting depth without special-casing two
    levels specifically. Confirmed as a real, previously-uncaught bug: with
    `bound` always reset to -1 (unbound) across an outer skin step and never
    re-derived from the inner BoneLayer's own fields, every child of a
    nested BoneLayer fell back to a fully flexible blend across the WRONG
    subset of the OUTER skeleton's bones (the target's own, unrelated,
    flexi_bone_subset indices, reinterpreted against the outer skeleton) -
    invisible at frame 0 (every bone's rest_to_pose is identity there
    regardless of which bones are blended) but visibly wrong at any other
    frame, confirmed on `SketchBone.animeproj`'s "el-sol" hand rig.
    """
    steps: list[DeformStep] = []
    pending = IDENTITY_MATRIX          # matrix steps not yet flushed, composed outer-most-last
    chain = list(ancestors) + [target]
    bound_bone = -1
    bound_subset: tuple[int, ...] = ()
    for layer in reversed(chain):
        is_deforming_bone_layer = (layer is not target and layer.skeleton is not None
                                    and layer.kind is LayerKind.BONE)
        if is_deforming_bone_layer:
            steps.append(MatrixStep(pending))
            steps.append(SkinStep(layer, bound_bone, bound_subset))
            pending = layer.local_matrix(frame, exporter)
            bound_bone, bound_subset = -1, ()
        else:
            pending = layer.local_matrix(frame, exporter).compose(pending)
        if layer.parent_bone >= 0:
            bound_bone, bound_subset = layer.parent_bone, ()
        elif layer.flexi_bone_subset:
            bound_subset = tuple(layer.flexi_bone_subset)
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
    smooth_bone_joints: bool = False    # --smooth-joints; Exporter._effective_subset
    point_bone_binding: bool = False    # --point-bones; Exporter._geometry_and_mapper
    bone_dynamics: bool = False         # --bone-dynamics; Skeleton.dynamic_angles
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


@dataclass
class RenderItem:
    """One step of walk_render_tree()'s depth-first walk over the layer
    tree, in Moho's own draw order (back to front, matching
    Document.walk()).  export_document and any other writer (e.g. a Lottie
    exporter) consume the SAME sequence, so neither can make a different
    masking, visibility, active-child, or deformation decision than the
    other.

    `event` is one of:

    - "enter": `layer` (a container, or None for the document's own virtual
      root) is about to have its children walked.  `mask_sources` is that
      container's OWN contribution to clipping ITS children, via its
      group_mask - computed once, here, at the exact point the
      pre-extraction code computed it, because the value depends on
      self._active_actions being empty at the moment of the call (see
      Exporter._mask_sources's own docstring for why).  `exempt` says
      whether `layer` itself ignores ITS OWN parent's mask (always False,
      and irrelevant, for the virtual root).  A consumer that reconstructs
      Moho's nested structure opens a masking scope here and closes it at
      the matching "exit" - see Exporter.export_document for a worked
      example.
    - "mesh": one mesh layer to draw.  `geometries`/`to_px` are already
      built for `frame`, under the correct Smart Bone context - see the
      warning below about self._active_actions.
    - "exit": the scope opened by the last unmatched "enter" is finished.

    Every layer that is itself a container is wrapped in its own
    "enter"/"exit" pair when the walk recurses into it, even one with zero
    drawable children - Moho itself still draws such a container as an empty
    group (confirmed: 8 of 201 containers across this repository's sample
    documents are exactly that), so a consumer that skipped empty
    "enter"/"exit" pairs would produce different output for those.

    WARNING about self._active_actions: it is set to the correct Smart Bone
    context for a "mesh" item's own layer and is left set ACROSS the yield,
    so a consumer may safely evaluate that layer's own animated style
    channels (fill/line colour, gradients, ...) while handling this item.
    It is only cleared once the consumer asks walk_render_tree for the NEXT
    item - do not hold onto a "mesh" RenderItem and evaluate a DIFFERENT
    layer's channels before doing so.

    `depth` is the true ancestor-chain length (`len(ancestors)`), NOT
    necessarily an SVG indentation depth - see export_document's own
    `render_scope` for why those two numbers can differ under `--flat`.
    """
    event: str
    layer: Optional["Layer"]
    ancestors: tuple
    depth: int
    exempt: bool = False
    mask_sources: Sequence[tuple[str, float]] = ()
    geometries: Optional[list] = None
    to_px: Optional[Callable[["Vec2"], "Vec2"]] = None


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
        pose-frame - see the module docstring's SMART BONES section.

        A dial only ever drives ITS OWN action - the one named after the bone,
        or that action's "X 2" opposite-direction variant.  The candidate scan
        below is restricted to those two names, which matters because a dial
        bone's `anim_angle` is routinely registered in OTHER actions as well:
        it is an ordinary bone that ordinary animation can move, so an action
        that poses the whole rig records it like any other bone.

        `Bandit.mohoproj` is where that shows.  It has four dial bones
        (`EyeBlink`, `SquashStretch`, `EyeMovement`, `HeadTurn`) and a plain
        stored animation called `Walk` - no bone is named `Walk`, so it is not
        a dial at all - and all four dials carry a `Walk` pose on their own
        `anim_angle` alongside their own.  Scanning every registered action
        and keeping whichever pose best bracketed the dial's current angle
        picked `Walk` whenever its span happened to be wider (e.g.
        `EyeMovement` at frame 60: own span 0.7854, `Walk` span 1.6183, and
        the angle sits inside both), so a phantom `Walk` action went active
        with a pose frame that lurched between 25, 44, 46, 15.9 and 6.07 and
        then pinned at 50 for thirty straight frames.

        Measured against the 103 frames Moho itself exported to
        `moho/Bandit/svg/`, on the muzzle's horizontal travel (2430 px over
        the range): mean error 144.38 px before, 5.27 px after.

        Bandit is the only document in the corpus where this changes
        anything - checked directly, no dial bone in `SketchBone`,
        `WhatIsBone`, `AddBone` or `ControlBones` registers a foreign action
        on its own angle - so the Smart Bone behaviour verified against
        `moho/SketchBone/ears/` and `moho/SketchBone/hand/` is untouched.
        """
        names = bone_layer.action_names
        skeleton = bone_layer.skeleton
        out: list[ActiveAction] = []
        if skeleton is None:
            return out
        for bone in skeleton.bones:
            if bone.name not in names:
                continue
            own = (bone.name, bone.name + " 2")
            angle_channel = Channel.of(bone.anim_angle)
            current = angle_channel.eval_raw(frame)      # deliberately NOT eval() - see module docstring
            best_action: Optional[ActionRef] = None
            best_key: Optional[tuple[float, float]] = None
            for action in angle_channel.actions:
                if action.name not in own or action.name not in names:
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

    def _curve_geometries(self, mesh: Mesh, frame: float,
                           deform: Optional[Callable[[Vec2, int], Vec2]] = None
                           ) -> list[CurveGeometry]:
        """Every curve of `mesh`, evaluated at `frame`.

        When `deform` is given, each mesh POINT is pushed through it - along
        with that point's own `MeshPoint.parent` bone - BEFORE any Bezier
        handle is reconstructed, so the returned geometry already sits in
        document space and its caller's `to_px` is only the pixel
        projection.

        Deforming points first, rather than deforming each finished control
        point afterwards, is what makes per-point bone binding expressible
        at all: a Bezier handle is derived from its neighbours and does not
        correspond to any single mesh point, so it has no bone of its own to
        follow.  It also matches how Moho describes the operation - bones
        move points, the curve follows the points.

        For a rigid or purely affine deformation the two orders are
        mathematically identical (an affine map carries Bezier control
        points to the Bezier of the mapped curve), so this is not a
        behaviour change for most layers.  In particular EVERY bone's
        rest_to_pose is the identity at frame 0 - `Skinner.build` derives it
        from `world_matrices(0)` against `world_matrices(frame)` - which is
        why the tracked reference SVGs, all rendered at frame 0, are
        unaffected.  The orders diverge only where the blend is genuinely
        non-affine, i.e. exactly where a point straddles two bones.
        """
        positions = [Vec2.of(self.eval(p.position, frame)) for p in mesh.points]
        if deform is not None:
            positions = [deform(pos, mesh.points[i].parent)
                          for i, pos in enumerate(positions)]
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

    def _effective_subset(self, step: "SkinStep") -> tuple[int, ...]:
        """The bone indices a flexible SkinStep should actually blend over.

        Normally exactly `step.subset` (the layer's own
        `flexi_bone_subset`).  With `RenderSettings.smooth_bone_joints` on,
        a subset naming exactly ONE bone is widened to include that bone's
        parent and its direct children - Moho's "Smooth Joint for Bone Pair"
        approximated with machinery already here.

        Why one bone is the case worth widening: `Skinner.deform` normalises
        by the total weight, so a single-bone subset makes the falloff
        cancel out completely and the layer becomes RIGID.  Two halves of a
        limb bound that way rotate about different pivots and tear apart at
        the joint - measured on `SketchBone.animeproj`, whose
        `kol-sol-ust`/`kol-sol-alt` (bones 13/14) pull 40 px apart from
        frame 56, exactly tracking bone 14's own 41.5 degree swing, while
        its LEGS - bound to TWO bones each (`bacak-sol` = "20|21") - never
        tear at all.  That contrast is the evidence for the shape of this
        fix: give the arm the same two-bone neighbourhood the leg already
        has, and let the existing inverse-square falloff do the blending.
        It needs no new formula, and it degrades correctly - 1/d^2 is steep,
        so a point out at the wrist is ~99% its own bone, while a point at
        the joint itself sits equidistant and blends about half and half.

        HEURISTIC, and off by default.  No field in any of the 19 sample
        documents records whether Moho's smooth-joint option is on (audited:
        `flexi_bone_elbow` is false everywhere, `binding_mode` is constant,
        no bone carries a control parent), so which layers Moho actually
        smooths cannot be read from the file - only that this rig plainly
        does not tear the way an unsmoothed rigid bind must.  Widening a
        subset also cannot be right for a layer deliberately pinned to one
        bone, which is why it is opt-in rather than assumed.
        """
        subset = step.subset
        if not self.settings.smooth_bone_joints or len(subset) != 1:
            return subset
        skeleton = step.bone_layer.skeleton
        if skeleton is None:
            return subset
        bones = skeleton.bones
        index = subset[0]
        if not 0 <= index < len(bones):
            return subset
        widened = {index}
        parent = bones[index].parent
        if 0 <= parent < len(bones):
            widened.add(parent)
        widened.update(j for j, b in enumerate(bones) if b.parent == index)
        return tuple(sorted(widened))

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

    def _deformed_pixel_mapper(self, chain: list[DeformStep],
                                frame: float) -> Callable[[Vec2], Vec2]:
        """A point-mapper that walks a full DeformChain (ordinary transforms
        plus bone skinning) before projecting to pixel space.

        Each SkinStep carries its OWN `subset` (see SkinStep and
        build_deform_chain) rather than this reading one fixed subset off
        the render target - required for a BoneLayer nested inside another
        BoneLayer, where the OUTER SkinStep's subset (if it is flexible at
        all) belongs to the nested BoneLayer itself, not to whatever mesh
        is ultimately being rendered."""
        deform = self._deformed_point_mapper(chain, frame)
        return lambda p: self._to_pixel(deform(p, -2))

    def _geometry_and_mapper(self, mesh: Mesh, chain: list[DeformStep], frame: float):
        """(geometries, to_px) for one mesh, picking the geometry order that
        mesh needs.

        Two orders exist because per-point bone binding cannot be expressed
        in the original one, and the original one cannot be abandoned
        wholesale:

        - **Points deformed first** (`MeshPoint.parent` honoured), Bezier
          handles reconstructed from the deformed points, `to_px` reduced to
          the pixel projection.  Required whenever any point carries its own
          bone, since a handle belongs to no single point and so has no bone
          to follow.
        - **Control points deformed last** - the original order - for every
          other mesh.

        The two are NOT interchangeable: handle reconstruction derives
        lengths from inter-point distances, so it commutes with a similarity
        transform but not with the non-uniform scale a layer transform or
        `Skeleton.world_matrices`'s deliberately asymmetric bone scale can
        carry.  Switching every mesh to the point-first order was measured to
        move all five tracked reference SVGs (36,119 changed lines in
        `SketchBone.svg` alone) with nothing to say the new geometry was
        better, so the order is only ever switched for a mesh that actually
        uses per-point binding - 119 of them across the 19 sample documents.

        AND EVEN THEN IT IS OFF BY DEFAULT (`--point-bones`), because
        treating `MeshPoint.parent` as "follow this bone rigidly" measured
        much WORSE, not better.  On `SketchBone.animeproj`'s two ear meshes,
        the only ones there that use the field (5 points each, all naming
        bone 0), error against Moho's own frames rose from 16.0% to 48.4%
        and from 13.8% to 38.5%, taking the whole-frame difference 78.9% the
        wrong way.  So the field is real and widely used - roughly 4,000
        points over those 119 meshes - but this reading of it is wrong.
        Resolving the index against the OUTERMOST skeleton instead was then
        tested and is WORSE still - 49.4% ear error against 40.7% for the
        innermost and 14.5% for ignoring the field entirely - so it is not a
        skeleton mix-up.  The value genuinely is a bone index (123 of the
        4,400 bound points exceed their own mesh's point count, so it cannot
        be a point index); it is the RIGID reading that is wrong.  Untested:
        a bound point may still blend with its neighbours with that bone
        merely forced into the weighting, or the behaviour may be gated by
        `skeleton.binding_mode`.  Left wired up but disabled so the next
        attempt starts from these measurements instead of a guess.
        """
        if mesh.has_point_bones and self.settings.point_bone_binding:
            return (self._curve_geometries(mesh, frame,
                                            self._deformed_point_mapper(chain, frame)),
                     self._to_pixel)
        return self._curve_geometries(mesh, frame), self._deformed_pixel_mapper(chain, frame)

    def _deformed_point_mapper(self, chain: list[DeformStep],
                                frame: float) -> Callable[[Vec2, int], Vec2]:
        """Walk a full DeformChain, returning `f(point, point_bone)` in
        document space (NOT pixels - the caller projects).

        `point_bone` is that mesh point's own `MeshPoint.parent`: a bone
        index makes the point follow that ONE bone rigidly, overriding the
        layer's binding for the INNERMOST skin step only (the bone index is
        into that bone layer's own skeleton, which is the skeleton the
        points are bound to).  `-2`/`-1` mean "no per-point binding" and
        fall through to the layer's own rigid or flexible binding exactly as
        before.

        Each SkinStep carries its OWN `subset` (see SkinStep and
        build_deform_chain) rather than this reading one fixed subset off
        the render target - required for a BoneLayer nested inside another
        BoneLayer, where the OUTER SkinStep's subset (if it is flexible at
        all) belongs to the nested BoneLayer itself, not to whatever mesh is
        ultimately being rendered.
        """
        weight_fn = BONE_WEIGHT_FALLOFFS[self.settings.bone_weight_falloff]
        # Resolved once per step, not once per point - _effective_subset walks
        # the whole bone list looking for children, and a mesh can be
        # thousands of points.
        subsets = [self._effective_subset(s) if isinstance(s, SkinStep) else ()
                   for s in chain]
        # The innermost skin step is the one whose skeleton the mesh points
        # are actually bound to, so it is the only one a per-point bone
        # index can refer to.
        innermost = next((i for i, s in enumerate(chain) if isinstance(s, SkinStep)), None)

        def deform(p: Vec2, point_bone: int = -2) -> Vec2:
            for index, (step, subset) in enumerate(zip(chain, subsets)):
                if isinstance(step, MatrixStep):
                    p = step.matrix.apply(p)
                    continue
                skinner = self._skin_data(step.bone_layer, frame)
                bone = step.bound_bone_index
                if index == innermost and point_bone >= 0:
                    bone = point_bone if point_bone < len(skinner.bones) else bone
                if bone >= 0:
                    p = skinner.bones[bone].rest_to_pose.apply(p)
                else:
                    p = skinner.deform(p, subset, weight_fn)
            return p

        return deform

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
        contribution to masking its sibling Head_DarkBlue.

        Smart Bone context: set to whatever would be active for `layer` if
        it were rendered as an ordinary "mesh" item (see
        Exporter._active_actions_along), NOT left empty - see the fix note
        on _mask_sources for why this used to be a real bug, confirmed
        against `SketchBone.mp4`."""
        paths: list[tuple[str, float]] = []
        if layer.mesh is not None:
            self._active_actions = self._active_actions_along(ancestors, frame)
            try:
                deform = build_deform_chain(ancestors, layer, frame, self)
                geometries, to_px = self._geometry_and_mapper(layer.mesh, deform, frame)
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
            finally:
                self._active_actions = []
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

        NOTE ON SMART BONE CONTEXT: `self._active_actions` is empty when this
        method itself is entered (export_layer/export_document always call it
        *between* two clears - see both methods), but each mask source's OWN
        geometry is evaluated under ITS OWN correct Smart Bone context, set
        inside `_mask_source_shapes` - NOT left empty.  This used to be a
        real, confirmed bug: `SketchBone.animeproj`'s "goz" (eye) shape is a
        `masking == 2` source whose own fill correctly closes for a blink
        (driven by the `goz-sol-ac-kapa`/`goz-sag-ac-kapa` Smart Bone dials),
        but the mask built from its geometry stayed permanently open-eye-
        shaped while that context was left empty here - confirmed against
        `SketchBone.mp4`: the masked "goz-bebegi" (pupil) visibly failed to
        disappear during a blink, though the eye's own visible fill did.
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

    def _mask_source_shapes_bezier(self, layer: Layer, ancestors: Sequence[Layer],
                                    frame: float) -> list[tuple[list[dict], float]]:
        """Bezier counterpart of _mask_source_shapes(), for a Lottie writer -
        same recursion, same (per-shape geometry, exclude_width) pairing,
        `build_path_bezier()` in place of `build_path_d()`, same per-source
        Smart Bone context fix (see _mask_source_shapes's own docstring).
        See _mask_source_shapes's own docstring for what `exclude_width`
        means; a Lottie consumer is not required to use it (a plain
        per-source union, dropping the exclude-width carve-out, is a
        documented, counted simplification - see moho2lottie.py's own
        notes)."""
        paths: list[tuple[list[dict], float]] = []
        if layer.mesh is not None:
            self._active_actions = self._active_actions_along(ancestors, frame)
            try:
                deform = build_deform_chain(ancestors, layer, frame, self)
                geometries, to_px = self._geometry_and_mapper(layer.mesh, deform, frame)
                for shape in layer.mesh.shapes:
                    beziers = build_path_bezier(geometries, shape.edges, to_px)
                    if not beziers:
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
                    paths.append((beziers, exclude_width))
            finally:
                self._active_actions = []
        for child in layer.children:
            if child.masking == 2:
                paths += self._mask_source_shapes_bezier(child, ancestors + (layer,), frame)
        return paths

    def _mask_sources_bezier(self, container: Optional[Layer],
                              chain_through_container: Sequence[Layer],
                              frame: float) -> list[tuple[list[dict], float]]:
        """Bezier counterpart of _mask_sources(), for a Lottie writer - same
        group_mask/masking rules, same per-source Smart Bone context fix
        (see _mask_sources's own docstring), `_mask_source_shapes_bezier`
        in place of `_mask_source_shapes`."""
        if container is None:
            return []
        forced = container.name in self.settings.forced_mask_containers
        if not forced and not container.group_mask:
            return []
        paths = []
        for child in container.children:
            if child.masking == 2:
                paths += self._mask_source_shapes_bezier(child, chain_through_container, frame)
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
                      indent: str, suppress_outline: bool = False,
                      geometries: Optional[list[CurveGeometry]] = None
                      ) -> tuple[list[str], list[Vec2]]:
        if geometries is None:
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
            geometries = None
            to_px = self._plain_pixel_mapper(IDENTITY_MATRIX)
        else:
            self._active_actions = self._active_actions_along(ancestors, frame)
            self._layer_scale = self._full_chain_matrix(ancestors, layer, frame).uniform_scale() or 1.0
            chain = build_deform_chain(ancestors, layer, frame, self)
            geometries, to_px = self._geometry_and_mapper(layer.mesh, chain, frame)

        body, pixel_points = self._render_mesh(layer.mesh, to_px, frame, indent="    ",
                                               suppress_outline=layer.kind is LayerKind.PATCH,
                                               geometries=geometries)
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
        --combined mode.

        Consumes walk_render_tree(): everything about WHAT to draw
        (visibility, masking, deformation, switch-layer active children)
        lives there, shared with any other writer that walks the same tree.
        Everything in this method is purely about HOW to format that as
        nested SVG <g>/<mask> elements, including the nested_groups/--flat
        choice, which walk_render_tree has no opinion about at all.

        NOTE (investigation in progress, see the module docstring's MASKING
        section): confirmed against the Moho app that a masking==2 sibling's
        own stroke stays fully visible on top of whatever it masks (Bandit's
        Head_DarkBlue/BellyTexture pair) - this tool still draws it at its
        plain list position, which is KNOWN WRONG for that specific pair. A
        naive "move masking==2 to render after every masking==0 sibling" fix
        was tried and reverted: on this same container most siblings
        (Arm_B, Tail, Ears, Muzzle, Nose, EyeBrow, Arm_F, ...) are
        masking==1 ("exempt"), and BellyTexture originally precedes some of
        them (e.g. Muzzle) - forcing "masking==2 after masking==0" broke
        that untouched relationship too, dragging BellyTexture's opaque fill
        on top of the character's eyes/muzzle/nose, which is visibly worse
        than the bug it was meant to fix. There is no single global reorder
        of a layer list that satisfies both "every masking==2 after every
        masking==0" and "never change relative order against any masking==1
        sibling" for this document - the two constraints conflict for
        BellyTexture specifically. Not fixed pending more evidence on how
        masking==1 siblings should interact with this - see KNOWN GAPS.
        """
        inner: list[str] = []
        pixel_points: list[Vec2] = []
        it = iter(walk_render_tree(self, frame, include_hidden))

        def render_scope(enter_item: RenderItem, pad_depth: int) -> None:
            """Consume everything up to and including the "exit" matching
            `enter_item` (already pulled from `it` by the caller), appending
            to `inner` exactly as the pre-extraction recursive `emit()` did.

            `pad_depth` is the indentation depth to use for `enter_item`'s
            own <mask> and for its direct children - deliberately NOT
            `enter_item.depth`: whether recursing into a nested container
            actually increases indentation depends on nested_groups/
            member_clip, a presentation choice only this function makes.
            """
            pad = "  " * (pad_depth + 1)
            clip = ""
            if enter_item.mask_sources:
                mask_id = f"mask_{self._next_def_id()}"
                inner.append(self._mask_element(enter_item.mask_sources, mask_id, pad))
                clip = f' mask="url(#{mask_id})"'

            for item in it:
                if item.event == "exit":
                    return
                # the mask source itself, and anything exempt, draws unclipped
                member_clip = "" if item.exempt else clip
                name = svg_escape(item.layer.name)

                if item.event == "mesh":
                    body, pts = self._render_mesh(
                        item.layer.mesh, item.to_px, frame, pad + "  ",
                        suppress_outline=item.layer.kind is LayerKind.PATCH)
                    pixel_points.extend(pts)
                    if body:
                        if nested_groups or member_clip:
                            inner.append(f'{pad}<g id="{name}" '
                                         f'data-moho-mask="{item.layer.masking}"{member_clip}>')
                            inner.extend(body)
                            inner.append(f"{pad}</g>")
                        else:
                            inner.extend(body)
                else:  # "enter" - a container child; recurse into its own scope
                    # A GroupLayer/BoneLayer/SwitchLayer (or a TextLayer with
                    # no mesh_layer to synthesise a child from) - its own
                    # children may be an empty list, which still draws an
                    # empty <g>, matching Moho.
                    if nested_groups or member_clip:
                        inner.append(f'{pad}<g id="{name}" '
                                     f'data-moho-type="{item.layer.type_name}"{member_clip}>')
                        render_scope(item, pad_depth + 1)
                        inner.append(f"{pad}</g>")
                    else:
                        render_scope(item, pad_depth)

        render_scope(next(it), 0)          # the document's own virtual root
        return self._wrap(self._viewbox(pixel_points, crop), inner)


def walk_render_tree(exporter: "Exporter", frame: float,
                      include_hidden: bool = False) -> Iterator[RenderItem]:
    """Depth-first walk of a document's layer tree, yielding every decision
    a renderer needs to draw it: visibility, edit_only, a switch layer's
    active child, masking exemption, the deform chain, and the resulting
    per-mesh pixel mapper.  Exporter.export_document and any other writer
    (e.g. a Lottie exporter) both consume this, so neither can make a
    different decision than the other.

    This is exactly what used to be export_document's own `emit` closure,
    with its SVG string-building removed - see Exporter.export_document for
    the consumer that adds that back for SVG.  The one thing preserved
    byte-for-byte from the original is the timing of
    exporter._active_actions: it is set immediately before building a mesh
    layer's geometry, left SET across the "mesh" RenderItem's yield (so a
    consumer may evaluate that layer's own style channels under the correct
    Smart Bone context), and cleared only once the consumer asks for the
    next item - see moho-export-pipeline.md section 9.3, "the empty Smart
    Bone context quirk", for why this ordering is load-bearing rather than
    incidental: Exporter._mask_sources must see an EMPTY context, and it is
    always called immediately after the previous item's clear (or before
    any mesh item has run at all).
    """
    document = exporter.document

    def walk(layers: Sequence[Layer], container: Optional[Layer],
             ancestors: tuple[Layer, ...], world: Mat2D,
             exempt: bool) -> Iterator[RenderItem]:
        mask_sources = exporter._mask_sources(container, ancestors, frame)
        yield RenderItem("enter", container, ancestors, len(ancestors),
                          exempt=exempt, mask_sources=mask_sources)

        active_child: Optional[Layer] = None
        if container is not None and container.kind is LayerKind.SWITCH:
            active_child = container.switch_active_child(frame, exporter)

        for layer in layers:
            if not layer.visible and not include_hidden:
                continue
            if layer.edit_only and not include_hidden:
                continue
            if active_child is not None and layer is not active_child:
                continue                  # switch layer: only its active child draws
            world_here = world.compose(layer.local_matrix(frame, exporter))
            child_exempt = layer.masking in (1, 2)

            if layer.mesh is not None:
                exporter._active_actions = exporter._active_actions_along(ancestors, frame)
                exporter._layer_scale = world_here.uniform_scale() or 1.0
                chain = build_deform_chain(ancestors, layer, frame, exporter)
                geometries, to_px = exporter._geometry_and_mapper(layer.mesh, chain, frame)
                yield RenderItem("mesh", layer, ancestors, len(ancestors),
                                  exempt=child_exempt, geometries=geometries, to_px=to_px)
                exporter._active_actions = []
            elif layer.is_container:
                # A GroupLayer/BoneLayer/SwitchLayer (or a TextLayer with no
                # mesh_layer to synthesise a child from) - recurse into its
                # children, which may be an empty list; that still yields an
                # "enter"/"exit" pair with nothing in between, matching
                # Moho's own still-draws-an-empty-<g> behaviour.
                yield from walk(layer.children, layer, ancestors + (layer,),
                                 world_here, child_exempt)
            # else: neither a mesh nor a container - e.g. an unresolved
            # PatchLayer (see PATCH LAYERS) whose target never got a mesh -
            # draws nothing at all, not even an empty "enter"/"exit" pair.

        yield RenderItem("exit", container, ancestors, len(ancestors))

    yield from walk(document.layers, None, (), IDENTITY_MATRIX, False)


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
        for shape in self.mesh.draw_order():
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
    parser.add_argument("--smooth-joints", action="store_true",
                        help="approximate Moho's \"Smooth Joint for Bone Pair\": a layer bound "
                             "to exactly ONE bone deforms rigidly and tears away from the next "
                             "limb segment at a bent joint, so blend it across that bone's "
                             "parent and children instead - see Exporter._effective_subset. "
                             "A heuristic (no sample document records whether Moho's own option "
                             "is on), hence off by default")
    parser.add_argument("--bone-dynamics", action="store_true",
                        help="simulate Moho's per-bone spring/damping secondary "
                             "motion (bone_dynamics). UNVERIFIED: the file gives the "
                             "force numbers but not the equation, units or "
                             "integrator, and no reference render in this repo "
                             "exercises it cleanly - see Skeleton.dynamic_angles. "
                             "Off by default")
    parser.add_argument("--point-bones", action="store_true",
                        help="honour Moho's per-POINT bone binding "
                             "(mesh.points[].parent). Measured MUCH worse than "
                             "ignoring it - see Exporter._geometry_and_mapper - "
                             "so it is off by default and kept only for further "
                             "investigation")
    args = parser.parse_args()

    if args.brush_raster and Image is None:
        sys.stderr.write("warning: --brush-raster requires Pillow (not installed) - "
                         "falling back to the normal per-dab brush render path\n")

    settings = RenderSettings(stroke_width_scale=args.stroke_mul,
                              forced_mask_containers=frozenset(args.mask_container),
                              brush_dir=args.brush_dir,
                              brush_spacing_mul=args.brush_spacing_mul,
                              brush_raster=args.brush_raster,
                              brush_raster_supersample=args.brush_raster_supersample,
                              smooth_bone_joints=args.smooth_joints,
                              point_bone_binding=args.point_bones,
                              bone_dynamics=args.bone_dynamics)
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
