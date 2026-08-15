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
  [`docs/moho-exporting-svg.md` § 7](docs/moho-exporting-svg.md#7-brush-textures).
- **Moho's brush textures, optional** (only needed for documents that use
  textured brush strokes) — copy them from a local Moho install:

  ```bash
  cp -R /Applications/Moho.app/Contents/Resources/Support/Common/Brushes styles/
  ```

  The exporter reads them from `styles/Brushes/` by default (`--brush-dir`
  overrides). `-R` is required: plain `cp` refuses to copy a directory on
  macOS.

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

See [`docs/moho-exporting-svg.md`](docs/moho-exporting-svg.md) for the full flag
reference, typical workflows, and the brush-texture render options
(`--brush-dir`, `--brush-spacing-mul`, `--brush-raster`,
`--brush-raster-supersample`).

## Documentation

- [`docs/moho-exporting-svg.md`](docs/moho-exporting-svg.md) — usage guide: every CLI
  flag, typical workflows, masking quirks, and the brush-texture
  performance/quality trade-offs.
- [`docs/moho-project-file-format.md`](docs/moho-project-file-format.md) —
  a readable summary of the reverse-engineered `.mohoproj`/`.animeproj`
  file format.
- [`docs/moho-animation-and-transform.md`](docs/moho-animation-and-transform.md)
  — how Moho stores motion (keyframed channels, tweening, actions/Smart Bones)
  and how the transform stack composes layers, bones and skinning.
- [`docs/moho-rigging-and-deformation.md`](docs/moho-rigging-and-deformation.md)
  — the bone system in depth (skinning math, binding modes, angle
  constraints, control bones, IK/target bones, bone dynamics), what Smart
  Warp leaves behind in the format, and the mesh-level fields that constrain
  deformation.
- The module docstring at the top of [`moho2svg.py`](moho2svg.py) — the
  authoritative, evidence-by-evidence source both documents above are
  distilled from.

## Repository layout

- `moho2svg.py` — the tool itself; a single file, no build system.
- `docs/` — usage guide and file-format reference (see above).
- `Makefile` — pattern rules build any export by name from the command
  line, e.g. `make out/svg/ori/Bandit.svg`; `make svg-all`/`make lottie-all`
  build every project under `moho/` in every export form; `make check-lottie`
  and `make check-reference` verify the exporters; `make format/moho/Bandit`
  pretty-prints one project to `moho/Bandit.json`. Run `make` with no target
  for the full list with examples.
- `moho/`, `out/`, `tmp/` — gitignored local content (source project files,
  all svg/lottie export output, scratch notes); not part of the tool itself.
- `styles/Brushes/` — Moho's brush textures, copied in locally (see
  Requirements); tracked with the repository, not part of the tool itself.

## Known limitations

This is a best-effort reconstruction of an undocumented file format. Some
formulas are confirmed exact against hundreds of reference samples; others
are best-fit heuristics. See the module docstring's KNOWN GAPS section for
the current list — notably: one boolean shape-combination mode
(`combo_mode == 2`) is not reverse-engineered, gradient placement is
approximate, the flexible bone-binding weight falloff is unvalidated for
overlapping-influence cases, and textured brush strokes are an approximation
with several further simplifications. `PatchLayer` **is** rendered (it
redraws its target layer's mesh at the patch's own point in the draw order),
but by a heuristic that reuses the target's transform instead of the patch's
own — no reference export of a `PatchLayer` document was available to confirm
it pixel-for-pixel.

Two rigging features are missing rather than approximate: **Smart Warp**
(distortion-mesh layers — not implemented and not even detected, so the
artwork exports undeformed) and the **playback-time bone features**
(bone dynamics/spring physics, control bones, IK against a moving target),
whose results are never written into the file's channels. See
[`docs/moho-rigging-and-deformation.md` § 8](docs/moho-rigging-and-deformation.md#8-gaps-ranked-by-how-likely-they-are-to-show).

## Development

There is no automated test suite. The only way to verify a change is to run
an export against a real `.mohoproj`/`.animeproj` file and compare against a
reference SVG Moho itself exported — see
[`CLAUDE.md`](CLAUDE.md) for more on the codebase's architecture and
conventions.
