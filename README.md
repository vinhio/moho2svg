# moho2svg

A single-file Python 3 command-line tool that exports vector artwork from a
Moho project file (`.mohoproj` for Moho Pro, `.animeproj` for Moho Debut) to
SVG.

Moho's project format is JSON, but undocumented. This tool's behavior was
reverse-engineered by empirically comparing its output against SVG files
Moho itself exported ("File > Export Animation"), across several rigs and
two Moho versions. See [`moho2svg.py`](moho2svg.py)'s module docstring for
the full reasoning and evidence behind every formula and constant, and
[`docs/`](docs/) for a shorter, human-oriented guide.

## Features

- Export one named layer, every vector layer, or the whole document as one
  layered SVG.
- Correct handling of Moho's coordinate system, Bezier curve reconstruction,
  stroke width, tapered (variable-width) strokes, boolean shape combination,
  masking, bone deformation (rigid and flexible/region binding), and Smart
  Bones (dial-driven poses).
- Approximates Moho's textured "brush" line styles (stamped dabs with
  rotation jitter) instead of falling back to a plain uniform stroke, with
  a choice of render strategies trading off file size/render speed against
  texture fidelity and vector scalability.
- No required third-party dependencies (stdlib only); Pillow is an optional
  dependency that unlocks faster brush-texture rendering.

## Requirements

- Python 3, no required third-party packages (stdlib only).
- **Pillow, optional but recommended** (`pip install Pillow`) — without it,
  a document with textured brush styles still exports correctly, but the
  result can be very slow (or fail) to open in a browser/SVG viewer. See
  [`docs/exporting-svg.md` § 7](docs/exporting-svg.md#7-brush-textures).

## Quick start

```bash
# List every layer in the document
python3 moho2svg.py Project.mohoproj --list

# Export one named vector layer
python3 moho2svg.py Project.mohoproj --layer Arm_B --out Arm_B.svg

# Export every vector layer, one file per layer
python3 moho2svg.py Project.mohoproj --all --outdir svg/

# Export the whole document as one layered SVG
python3 moho2svg.py Project.mohoproj --combined Character.svg
```

See [`docs/exporting-svg.md`](docs/exporting-svg.md) for the full flag
reference, typical workflows, and the brush-texture render options
(`--brush-dir`, `--brush-spacing-mul`, `--brush-raster`,
`--brush-raster-supersample`).

## Documentation

- [`docs/exporting-svg.md`](docs/exporting-svg.md) — usage guide: every CLI
  flag, typical workflows, masking quirks, and the brush-texture
  performance/quality trade-offs.
- [`docs/moho-project-file-format.md`](docs/moho-project-file-format.md) —
  a readable summary of the reverse-engineered `.mohoproj`/`.animeproj`
  file format.
- The module docstring at the top of [`moho2svg.py`](moho2svg.py) — the
  authoritative, evidence-by-evidence source both documents above are
  distilled from.

## Repository layout

- `moho2svg.py` — the tool itself; a single file, no build system.
- `docs/` — usage guide and file-format reference (see above).
- `Makefile` — `make gen` regenerates the tracked reference SVGs in `svg/`
  from the project files in `moho/`; `make gen-fast`/`gen-med`/`gen-raster`
  produce alternative brush-performance previews (see
  [`docs/exporting-svg.md` § 7](docs/exporting-svg.md#7-brush-textures));
  `make styles.brushes` symlinks `styles/Brushes/` to Moho's own installed
  brush textures.
- `moho/`, `styles/Brushes/`, `svg-fast/`, `svg-med/`, `svg-raster/`,
  `tmp/` — gitignored local/generated content (source project files, a
  symlink into a local Moho install, and various preview/scratch output);
  not part of the tool itself.
- `svg/` — exported SVGs tracked in git as reference output.

## Known limitations

This is a best-effort reconstruction of an undocumented file format. Some
formulas are confirmed exact against hundreds of reference samples; others
are best-fit heuristics. See the module docstring's KNOWN GAPS section for
the current list — notably: one boolean shape-combination mode
(`combo_mode == 2`) is not reverse-engineered, gradient placement is
approximate, the flexible bone-binding weight falloff is unvalidated for
overlapping-influence cases, `PatchLayer` is not modelled, and textured
brush strokes are an approximation with several further simplifications.

## Development

There is no automated test suite. The only way to verify a change is to run
an export against a real `.mohoproj`/`.animeproj` file and compare against a
reference SVG Moho itself exported — see
[`CLAUDE.md`](CLAUDE.md) for more on the codebase's architecture and
conventions.
