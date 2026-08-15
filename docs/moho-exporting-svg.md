# Exporting SVG from a Moho Project File

This document explains how to use `moho2svg.py` to export vector artwork from
a Moho project file (`.mohoproj` / `.animeproj`) to SVG. For how the project
file itself is structured, see [`moho-project-file-format.md`](moho-project-file-format.md).
For the full, evidence-by-evidence reasoning behind every formula and
constant this tool uses, see the module docstring at the top of
`moho2svg.py` — this document is a usage guide, not a replacement for it.

## 1. Requirements

- Python 3, no *required* third-party packages (stdlib only).
- **Pillow, optional but recommended** (`pip install Pillow`) — without it,
  exporting a document with textured brush styles still works, but the
  result can be very slow (or fail) to open in a browser/SVG viewer. See
  [§ 7](#7-brush-textures).
- A Moho project file: `.mohoproj` (Moho Pro) or `.animeproj` (Moho Debut).
  Both are plain JSON despite the extension.
- Optionally, an SVG viewer for spot-checking output — a browser works fine;
  `rsvg-convert` is convenient for scripted PNG previews.

## 2. Basic commands

```bash
# List every layer in the document (mesh point/shape counts for vector layers)
python3 moho2svg.py Project.mohoproj --list

# Export one named vector layer to its own SVG file
python3 moho2svg.py Project.mohoproj --layer Arm_B --out Arm_B.svg

# Export every vector layer, one file per layer
python3 moho2svg.py Project.mohoproj --all --outdir svg/

# Export the whole document as one layered SVG
python3 moho2svg.py Project.mohoproj --combined Bandit.svg
```

Exactly one export mode is required: `--layer`, `--all`, `--combined`, or
`--list`.

## 3. Full flag reference

| Flag | Default | Meaning |
|---|---|---|
| `project` (positional) | — | Path to the `.mohoproj`/`.animeproj` file. |
| `--list` | — | Print every layer (name, type, and mesh point/shape counts for vector layers), then exit. |
| `--layer NAME` | — | Export the single vector layer named `NAME`. |
| `--out FILE` | `<layer>.svg` | Output path for `--layer` mode. |
| `--all` | — | Export every visible vector layer, one file per layer. |
| `--outdir DIR` | `.` | Output directory for `--all` mode. |
| `--combined FILE` | — | Export the whole document as one layered SVG to `FILE`. |
| `--flat` | off | With `--combined`, skip nested `<g>` per layer (flatten the group structure). |
| `--frame N` | `0` | Which animation frame to evaluate (channels, bone poses, Smart Bone dials). |
| `--crop` | off | Use a tight viewBox around the exported content instead of the full canvas. |
| `--local` | off | Ignore ancestor transforms and bone deformation — export the mesh's raw point coordinates at canvas scale. Only valid with `--layer`/`--all`. |
| `--include-hidden` | off | Also export/traverse layers with `visible: false` or `edit_only: true`. |
| `--mask-container NAME` | (repeatable) | Force layer `NAME` to act as a masking container even if `group_mask` doesn't already mark it as one. See [Masking](#6-masking-quirks). |
| `--stroke-mul N` | `2.0` | Stroke width multiplier: `stroke_px = line_width * point_width * canvas_height * N / 2`. Use this if a document's own line-width calibration looks off compared to Moho's own render. |
| `--brush-dir DIR` | `styles/Brushes` | Directory of brush assets (texture PNGs and multi-frame brush folders) used to approximate textured "brush" line styles. Pass `""` to disable brush stamping entirely. See [Brush textures](#7-brush-textures). |
| `--brush-spacing-mul N` | `1.0` | Multiply brush dab spacing by `N` — raise it (e.g. `3`-`4`) to thin out dab density on a heavily brush-styled document, trading texture fidelity for a much lighter/faster-to-view SVG. See [Brush textures](#7-brush-textures). |
| `--brush-raster` | off | Composite each brush-styled shape's entire stroke into ONE raster `<image>` instead of one `<use>`/dab — smallest/fastest brush option, at the cost of that stroke no longer being vector. Requires Pillow. See [Brush textures § 7.2](#72-rasterizing-a-whole-stroke-into-one-image-per-shape). |
| `--brush-raster-supersample N` | `2.0` | With `--brush-raster`, composite at `N`x the shape's own pixel size before declaring it at 1x size in the SVG — sharper fine texture at a roughly `N²` file-size cost. See [§ 7.2](#72-rasterizing-a-whole-stroke-into-one-image-per-shape). |

## 4. Typical workflows

### Inspect a document before exporting anything

```bash
python3 moho2svg.py Project.mohoproj --list
```

This is the fastest way to find a layer's exact name (masking/animation bugs
are very often just a name mismatch) and to see which layers actually carry
a mesh (only those can be exported).

### Export one character/rig as a single reference image

```bash
python3 moho2svg.py Project.mohoproj --combined Character.svg --crop
```

### Export every part of a rig separately (e.g. for re-importing pieces elsewhere)

```bash
python3 moho2svg.py Project.mohoproj --all --outdir svg/ --crop
```

Files are numbered by draw order (`00_`, `01_`, ...) so re-importing them in
the same numeric order reproduces the original back-to-front stacking.

### Compare frames of an animation

```bash
python3 moho2svg.py Project.mohoproj --combined frame0.svg --frame 0
python3 moho2svg.py Project.mohoproj --combined frame30.svg --frame 30
```

## 5. This repository's own layout

This repository keeps three working directories that are not part of the
tool itself, only of how this checkout is organized:

- `moho/` — local copies of the `.mohoproj`/`.animeproj` source files used
  for development and regression-checking (gitignored — these are large
  binary-ish files that belong to the Moho projects being tested, not to the
  tool).
- `out/svg/ori/` — original exports (full brush texture); `out/svg/med/`,
  `out/svg/fast/`, `out/svg/raster/` — alternative brush-performance exports
  of the same projects (thinned-out dab density, no brush texture at all, and
  one raster image per shape, respectively). See [§ 7](#7-brush-textures).
- `out/lottie/` — Lottie exports (see `moho-to-lottie-plan.md`).
- `styles/Brushes/` — see [Brush textures](#7-brush-textures) below.

Everything under `out/` is gitignored. The Makefile builds any export from
the command line — the output file is the target, e.g.
`make out/svg/ori/Bandit.svg`; `make svg-all` builds every project under
`moho/` in all four svg forms and `make lottie-all` every project's Lottie
export. `out/svg/med/` thins out dab density (`BRUSH_SPACING_MUL`, default
2), `out/svg/fast/` disables brush stamping, `out/svg/raster/` bakes
per-shape raster brush strokes (see the `Makefile`).

## 6. Masking quirks

Moho's masking model uses two separate fields — a container's `group_mask`
and each child's own `masking` value — and it applies uniformly at every
nesting depth, including the document's own top-level layer. If a document's
masking does not seem to take effect where you expect it to, first confirm
in Moho itself which layer is the mask *source* (its `masking` should be 2,
shown in Moho as something like "Add to Mask") versus which layer should be
*clipped* (its `masking` is 0/unset, shown as "Mask This Layer" or similar) —
then re-check with `--list` that both live under the same container. If the
container's own `group_mask` genuinely isn't picked up, force it with
`--mask-container NAME`. See the module docstring's MASKING section for the
full rules and the reasoning behind them.

## 7. Brush textures

A named style's outline can be a textured "brush" (stamped repeatedly along
the path with rotation jitter) instead of a plain uniform-width line — think
a soft cheek blush, an ink-smear shadow, or hand-drawn hatching. A plain SVG
`<path stroke>` cannot reproduce that texture, so this tool approximates it
by stamping the brush's own image(s) along the path, but only for a brush
whose asset it can actually find.

To enable this, point `--brush-dir` at a folder containing the relevant
brush files (single PNGs and/or multi-frame brush folders, named to match a
style's `brush_name` — see [Moho project file format § 8.6](moho-project-file-format.md#86-resolving-a-brush_name-to-a-file)
for exactly how that name is resolved to a file). The simplest source for these is Moho's own
installation, which ships every brush it uses:

```bash
cp -R /Applications/Moho.app/Contents/Resources/Support/Common/Brushes styles/
```

(adjust the path if your installation lives elsewhere.) This copies Moho's
brush folder into `styles/Brushes` — plain `cp` refuses to copy a directory
on macOS, so the `-R` is required. `styles/` is untracked local content,
not part of the repository.

Any brush whose asset cannot be resolved (including when `styles/Brushes`
does not exist at all) falls back to a plain uniform stroke — nothing
regresses for a checkout that hasn't run the copy command.

### 7.1 Performance: install Pillow

A document whose linework broadly uses a textured brush (rather than just
one or two accent shapes) can end up with many thousands of individual
stamped dabs once every matching style picks it up. How expensive that is
*to view* (not to produce — `moho2svg.py` itself stays fast either way)
depends entirely on whether **Pillow** (`pip install Pillow`) is installed
where you run `moho2svg.py`:

- **Pillow installed (preferred)**: each *(brush, frame, colour, alpha)*
  combination actually used in the document is pre-rendered, once, into an
  already-coloured PNG at export time (`Exporter._bake_tinted_frame`). Every
  dab is then just a `<use>` of that image — a plain, cheap, hardware-
  accelerated image blit for any viewer.
- **Pillow absent (fallback, zero extra dependencies)**: every dab is a
  `<g>` masked by a shared `<mask>`+`<feColorMatrix>` filter that recolours
  the raw texture at render time (see [§ 7.3](#73-why-the-fallback-path-is-expensive-to-view)
  for why this specifically, not dab count or file size on their own, is
  what makes a viewer slow or unable to open the file at all).

Confirmed at the same 600px preview width (`rsvg-convert`), fallback vs
Pillow path:

| Document | Fallback (mask+filter) | Pillow (pre-tinted `<use>`) |
|---|---|---|
| SketchBone | 3.89 MB / 15.97s | 2.86 MB / **2.46s** |
| AddBone | 6.16 MB / 25.83s | 9.00 MB / **8.90s** |
| WhatIsBone | 4.11 MB / 6.13s | 9.62 MB / **1.84s** |

Installing Pillow is a 3x-6.5x render-time win across the board — but notice
it is not always a *smaller file*: AddBone and WhatIsBone actually grow,
because pre-tinting bakes each distinct colour at the source texture's own
native resolution (up to 512x512 for some of Moho's shipped brushes), and
this rig uses enough distinct (brush, colour) combinations that the baked
PNGs outweigh the mask/filter defs they replace. If file size specifically
matters more than render speed for such a document, the fallback path (no
Pillow, or run in an environment without it) may still be preferable, or
combine with `--brush-spacing-mul` below.

Two further flags manage dab *volume* itself, independent of which render
path is active:

- **`--brush-spacing-mul N`** (e.g. `3` or `4`) thins out dab density
  document-wide, multiplying the spacing between dabs while leaving
  everything else (including `--brush-dir` itself) unchanged. This cuts
  dab count roughly in proportion to `N` (confirmed on the fallback path at
  900px width: `N=4` took SketchBone from 17,822 dabs/~31s to 4,502
  dabs/~8s), at the cost of a visibly coarser, more "dotted" texture rather
  than a continuous one. `N=2`-`2.5` is a reasonable middle ground for most
  documents — still a large cut, with the texture still reading as
  continuous at normal viewing sizes.
- **`--brush-dir ""`** (or the `out/svg/fast/%.svg` pattern rule, which does
  exactly this for any project, writing to the gitignored `out/svg/fast/`
  instead of `out/svg/ori/`) disables brush stamping entirely for a quick,
  lightweight preview — every brush-styled stroke falls back to a plain
  stroke or (if tapered) TaperedStrokeOutliner's ribbon, both cheap for any
  viewer regardless of Pillow. Confirmed on SketchBone: 3.9 MB → 319 KB, and
  render time drops to under 0.1 seconds. Use this whenever you need a fast
  interactive look at a document and don't need the brush texture itself;
  switch back to a full `--brush-dir` export for the final/print output.

### 7.2 Rasterizing a whole stroke into one image per shape

`--brush-raster` goes further than the Pillow path above: instead of one
`<use>` per dab, `Exporter._raster_brush_shape` composites an ENTIRE
brush-styled shape's dabs into a single raster `<image>` at export time
(also via Pillow — falls back to the normal per-dab path, with a warning,
if Pillow is unavailable). This is this tool's most aggressive brush
option, trading away that stroke's vector-ness entirely (it becomes a fixed
bitmap — not rescalable or editable as a path afterwards) for the smallest,
fastest-to-view result of any option here:

| Document | Pillow, per-dab `<use>` | `--brush-raster` (1x) | `--brush-raster` (default, 2x) |
|---|---|---|---|
| SketchBone | 2.86 MB / 2.46s | 0.93 MB / 0.15s | **2.74 MB** / **0.18s** |
| AddBone | 9.00 MB / 8.90s | 0.44 MB / 0.07s | **1.03 MB** / — |
| WhatIsBone | 9.62 MB / 1.84s | 0.32 MB / 0.09s | **0.51 MB** / — |

Even at 2x, `--brush-raster` still comes out smaller than the per-dab `<use>`
path on every document tested (and far faster to render on all three) — this
specifically fixes the file-size regression the per-dab path had on
AddBone/WhatIsBone (§ 7.1), since one composited image per *shape* scales
with shape count, not with the number of distinct (brush, colour)
combinations sourced from a potentially large native texture.

**The trade-off found in testing, beyond losing vector editability**: at
1:1 (no supersampling), a stroke with very fine, sparse, high-contrast
detail under heavy dab overlap (confirmed on the SketchBone rig's "golge"
shadow — the same shape used throughout this document to illustrate brush
issues, ~30-50x dab overlap) visibly loses the wispy/hair-like fine texture
that the per-dab `<use>` path preserves, coming out softer/blurrier instead.

**`--brush-raster-supersample N` (default 2.0)** substantially recovers this:
the canvas is composited at N times the shape's own pixel size and then
declared at the normal 1x size in the SVG - the standard "@2x asset" trick
for high-DPI bitmaps, giving a downsampling viewer more source detail to
work with. Confirmed on "golge" at 500px preview width: 1x reads as a
near-flat soft blob, 2x recovers a visible (if slightly softened) grainy
edge, 3x reads as close to the per-dab `<use>` version's wispy strands.
Render time barely moves with N (it is still one image blit per shape
either way - 0.13s/0.18s/0.24s for SketchBone at N=1/2/3), but file size
scales roughly with N² (0.93/2.74/5.42 MB for the same document) - past
N≈3 you are approaching or exceeding the per-dab `<use>` path's own size
for a texture-heavy document, at which point that default path (which
does not lose fine detail at all) is arguably the better choice instead.
2.0 was picked as the default for a reason: it recovers most of the visible
softening while staying smaller and much faster than the per-dab path on
every document tested here; a softer, lower-contrast texture (the "yanak"
cheek blush) looked effectively identical at every N, including 1.0, so this
trade-off matters specifically for fine/wispy brushes like "golge", not
brush textures in general.

Reach for `--brush-raster` when file size/render speed matters more than
guaranteed pixel-perfect texture fidelity (a quick preview, a web embed);
prefer the default Pillow per-dab `<use>` path when the fine texture itself
is the point and you are not size/speed-constrained. This also affects how
the result holds up when zoomed in or printed at high DPI — see
[§ 7.4](#74-zoom--scalability-trade-off-across-the-three-render-paths).

The `out/svg/raster/%.svg` pattern rule does the same for any project
(e.g. `make out/svg/raster/Bandit.svg`), writing to the gitignored
`out/svg/raster/`.

### 7.3 Why the fallback path is expensive to *view*

Without Pillow, each stamped dab is a `<g transform="..."><rect .../></g>`
masked by a shared `<mask>` containing an `<image>` (the brush texture) plus
a `<feColorMatrix>` filter (see [Moho project file format § 8.5](moho-project-file-format.md#85-brush-styles)
for why the filter is there).
Every element that references a `mask` forces a spec-compliant renderer to
render the mask's own content into an offscreen buffer, apply the filter to
it, then use the result to composite that one element — three real steps,
repeated once per dab, regardless of how small the file's *text* is. This is
why render time on this path tracks dab count much more closely than it
tracks file size or output pixel resolution. It is also why some viewers
fail to open a heavily-brushed export at all on this path — many cap the
number of simultaneous filter/mask operations they'll attempt, or run out of
memory holding that many offscreen buffers at once. The Pillow path avoids
all of this by doing the recolouring once, in Python, instead of once per
dab in the viewer.

### 7.4 Zoom / scalability trade-off across the three render paths

Every render path keeps a shape's actual GEOMETRY (its path `d="..."`, i.e.
position and outline) as real vector data, at every zoom level, regardless
of brush settings. The trade-off discussed above (§ 7.1-7.3) is specifically
about how the brush *texture painted along that outline* is represented,
and that has real consequences for how the result holds up when zoomed in
far beyond the size it was exported/viewed at (a viewer window at high zoom,
a print at a much higher DPI than screen resolution, etc.):

| Render path | Brush texture is... | Zoom behaviour |
|---|---|---|
| `--brush-dir ""` (no brush) | Not present — plain stroke or TaperedStrokeOutliner ribbon | Stays perfectly sharp at any zoom — it is 100% vector, no raster involved at all. |
| Default (Pillow per-dab `<use>`) | A small raster image per *dab* (roughly the dab's own diameter, e.g. 10-80px), reused via `<use>` | Degrades much later / more gracefully: each dab is a small image already close to its displayed size, so ordinary zoom levels rarely exceed its native resolution. Zoom in enough on any ONE dab and it will eventually blur too — it is still a raster texture underneath — but the "unit" that blurs is small. |
| `--brush-raster` | ONE raster image for the *entire shape's* stroke, captured at `brush_raster_supersample`x its own pixel size (default 2x) at export time | Degrades sooner and more visibly: the whole stroke shares one fixed-resolution bitmap, so zooming the viewer/print beyond that captured resolution blurs/pixelates the whole stroke at once, not just fine detail within it. This is the direct, expected cost of collapsing many dabs into one image (§ 7.2) - not a bug. |

Raising `--brush-raster-supersample` raises the resolution ceiling before
this kicks in (§ 7.2), but it is still a ceiling, not scale-independence -
there is no value of it that makes `--brush-raster` behave like real vector
output under unbounded zoom. If a document needs to be viewed/printed at
significantly higher resolution than its own canvas size (not just viewed
quickly at roughly 1:1), prefer the default per-dab `<use>` path, or drop
brush texture entirely with `--brush-dir ""`, over `--brush-raster`.

## 8. Known limitations

This tool's export is a best-effort reconstruction from an undocumented file
format, empirically validated against real Moho renders where possible. Some
things are exact and confirmed; others are approximations. Before relying on
an unusual result, check the module docstring's KNOWN GAPS section, which
lists (with the reasoning behind each):

- Boolean shape combination mode `combo_mode == 2` is not reverse-engineered.
- Gradient centre/radius placement is approximate, not pixel-matched.
- The flexible bone-binding weight falloff is unvalidated for cases where
  more than one bone has significant influence at a point.
- `PatchLayer` is not modelled (observed to produce no visible geometry in
  every reference document so far).
- Physics, IK, and layer effects/shadows are ignored (a flat single-frame
  export is unaffected by any of them).
- Textured brush strokes are an approximation with several further
  simplifications — see [§ 7](#7-brush-textures) and the module docstring.
