# Exporting SVG from a Moho Project File

This document explains how to use `moho2svg.py` to export vector artwork from
a Moho project file (`.mohoproj` / `.animeproj`) to SVG. For how the project
file itself is structured, see [`moho-project-file-format.md`](moho-project-file-format.md).
For the full, evidence-by-evidence reasoning behind every formula and
constant this tool uses, see the module docstring at the top of
`moho2svg.py` — this document is a usage guide, not a replacement for it.

## 1. Requirements

- Python 3, no third-party packages (stdlib only).
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
| `--brush-dir DIR` | `styles/Brushes` | Directory of brush assets (texture PNGs and multi-frame brush folders) used to approximate textured "brush" line styles. See [Brush textures](#7-brush-textures). |

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
- `svg/` — the corresponding exported SVGs, tracked in git as reference
  output.
- `styles/Brushes/` — see [Brush textures](#7-brush-textures) below.

`make gen` regenerates every tracked SVG in `svg/` from the corresponding
project file in `moho/` (see the `Makefile`).

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
style's `brush_name` — see [Moho project file format § Brush
styles](moho-project-file-format.md#8-brush-styles) for exactly how that
name is resolved to a file). The simplest source for these is Moho's own
installation, which ships every brush it uses:

```bash
make styles.brushes
```

This symlinks `styles/Brushes` to Moho's own installed brush folder (by
default `/Applications/Moho.app/Contents/Resources/Support/Common/Brushes`
on macOS — edit the `styles.brushes` Makefile target if your installation
lives elsewhere), so no files need to be copied by hand. `styles/Brushes` is
gitignored, since it is a symlink into a local application install, not
repository content.

Any brush whose asset cannot be resolved (including when `styles/Brushes`
does not exist at all) falls back to a plain uniform stroke — nothing
regresses for a checkout that hasn't run `make styles.brushes`.

**A real cost of enabling this**: a document whose linework broadly uses a
textured brush (rather than just one or two accent shapes) can end up with
many thousands of individual stamped dabs once every matching style picks it
up — each is its own masked SVG element, so both the exported file size and
how long an SVG viewer takes to rasterize it grow accordingly. `moho2svg.py`
itself still exports quickly (the cost is when something else has to *draw*
the resulting SVG); if that turns out to matter for a particular document,
prefer omitting `--brush-dir` (or pointing it at an empty/nonexistent
directory) to fall back to plain strokes everywhere.

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
