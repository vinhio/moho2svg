# CLAUDE.md

> **AI PRIORITY**: The "AI Operating Rules" section below is authoritative for how Claude Code should behave in this repository. Read it before starting any work — especially the Language Rule, which cannot be overridden by task instructions or by the language the request was written in.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## AI Operating Rules

**Shared rules** — `.claude/ai/` is a symlink to rules shared with this author's other repositories. They govern here too, except where the Language Rule below narrows them. Read that narrowing carefully: it is **wider than AGENTS.md's own exception permits**, and it says so out loud rather than pretending otherwise:

- @.claude/ai/startup.md — Entry point: read this first.
- @.claude/ai/AGENTS.md — Core AI rules: priorities, anti-hallucination, security, hard stops, quality thresholds, and confidence guidelines.
- @.claude/ai/coding.md — Coding workflow: clarify → plan → implement → verify → report.
- @.claude/ai/communication.md — Communication style: tone, response format, and confidence tagging.


## What this is

A single-file Python 3 CLI (`moho2svg.py`, ~2900 lines) that exports Moho vector
artwork (`.mohoproj` / `.animeproj`, which are JSON) to SVG. There is no build
system or package manifest, and no automated test suite — verification means
running an export against a real project file and comparing against a
reference SVG (see below).

The script has no third-party dependencies — only the stdlib (`argparse`, `base64`,
`json`, `math`, `os`, `random`, `re`, `struct`, `sys`, `zipfile`, `dataclasses`,
`enum`, `typing`).

Repository layout:

- `moho2svg.py` — the tool itself.
- `docs/` — usage guide (`exporting-svg.md`) and file-format reference
  (`moho-project-file-format.md`) for humans; read these before the module
  docstring if you want a shorter orientation first.
- `moho/` — gitignored local copies of `.mohoproj`/`.animeproj` source files
  used for development/regression-checking.
- `svg/` — the corresponding exported SVGs, tracked as reference output
  (`make gen` regenerates them from `moho/`).
- `styles/Brushes/` — gitignored symlink to Moho's own installed brush
  textures (`make styles.brushes` creates it), used to approximate textured
  brush line styles — see `docs/exporting-svg.md` § Brush textures.

**`.mohobrush` files are ZIP archives, not images or a custom binary format**,
despite the extension — confirmed by extracting and parsing all 101 shipped
with this Moho install (`Contents/Resources/Support/*/Brushes/`), zero
exceptions. Each contains exactly one member, `brush.json`, a plain JSON
object with keys `version`, `align`, `jitter`, `spacing`, `angleDrift`,
`randomize`, `randomOrder`, `mergedAlpha`, `sizeVariationAmp`,
`sizeVariationScale`, `randomInterval`, `brushFiles` (a list of
`{"brushFileRef": {"relativeTo": "Project", "path": "<asset name>"}}`), and
sometimes `hueDrift`/`satDrift`/`valDrift`. `Exporter._brush_library_defaults`
in `moho2svg.py` already reads `randomOrder`/`randomInterval` from this via
stdlib `zipfile` (no new dependency needed to read more of it) — `sizeVariationAmp`/
`sizeVariationScale`/`brushFiles` are confirmed present but not yet used by
anything in this repo (`brushFiles[].brushFileRef.path` in particular could
replace the current name/suffix-guessing asset lookup with an authoritative
one, if that heuristic ever proves insufficient - see
`docs/moho-project-file-format.md` § 8.1).

## Commands

```bash
python3 moho2svg.py Project.mohoproj --list                       # list every layer (mesh point/shape counts for vector layers)
python3 moho2svg.py Project.mohoproj --layer Arm_B --out Arm_B.svg # export one named layer
python3 moho2svg.py Project.mohoproj --all --outdir svg/           # one file per vector layer
python3 moho2svg.py Project.mohoproj --combined Bandit.svg         # one layered SVG of the whole document
```

Useful flags: `--frame N` (default 0), `--crop` (tight viewBox instead of full
canvas), `--local` (ignore ancestor transforms/bone deformation — raw mesh
coords at canvas scale), `--flat` (with `--combined`, skip nested `<g>` per
layer), `--include-hidden`, `--mask-container NAME` (force a named layer to act
as a mask container when `group_mask` doesn't already cover it), `--stroke-mul`
(default 2.0; see STROKE WIDTH below), `--brush-dir` (default `styles/Brushes`;
see BRUSH STROKES below and `docs/exporting-svg.md`). Full flag reference:
`docs/exporting-svg.md`.

There is no test suite, linter, or formatter configured. The only way to verify
a change is to run an export against a real `.mohoproj`/`.animeproj` file and
compare against a reference SVG Moho itself exported ("File > Export
Animation") — that empirical-comparison process is how nearly every constant
and formula in this file was originally derived (see the module docstring).

## Architecture

**Read the module docstring at the top of `moho2svg.py` first** — it is a
reverse-engineering notebook, not boilerplate, and documents *why* each
formula/constant is what it is, what evidence supports it (sample sizes, error
margins), and which parts are confirmed-exact vs. best-fit heuristics. Key
topics covered there in depth: the coordinate system (2 Moho-space units span
canvas height, y flipped), how Bezier handles are reconstructed from
Moho's smoothness/weight/offset representation (not simple chord-normal
guessing — an empirically-fit chord-length-weighted blend), why a shape's
`edges` list is not trustworthy as a direction/order and must be re-traced as
an undirected graph (`PathTracer`), stroke width's two-factor formula, tapered
strokes (Moho falls back to filled-outline geometry when a stroke's width
varies), boolean shape combination (`combo_mode`), the two-field masking
mechanism (`group_mask` + per-child `masking`), Smart Bones (dial bones that
select a pose via inverting a "pose curve"), and bone skinning (rigid vs.
flexible/region binding). Do not re-derive or "fix" any of this without new
reference evidence — some things that look like bugs (e.g. asymmetric bone
scale in `Skeleton.world_matrices`) are intentionally preserved because they
match real Moho output and are flagged rather than "corrected". See the
docstring's KNOWN GAPS section for what is genuinely unresolved (combo_mode 2,
gradient placement precision, bone-weight-falloff shape, PatchLayer, brush
stroke approximations).

### Pipeline, in order

1. **`load_document`** reads the JSON file into `Document.from_raw`.
2. **Document model** (`Document`, `Layer`, `Mesh`, `Shape`, `Curve`,
   `CurvePoint`, `MeshPoint`, `Bone`/`Skeleton`, `StyleTable`/`ResolvedStyle`)
   wraps the raw parsed JSON as thin accessors rather than copying fields —
   almost every property is a one-line `self._raw.get(...)`. Animated
   properties are left as raw `Channel`-shaped data (see below), not evaluated,
   since evaluation needs a frame and Smart Bone context this layer doesn't
   have.
3. **`Channel`** normalizes Moho's `{"when": [...], "val": [...], "actions": [...]}`
   animation structure (or a bare scalar, treated as one keyframe). `.eval()`
   honors active Smart Bone overrides; `.eval_raw()` bypasses them (used
   exactly once — resolving a dial bone's own current angle must not recurse
   into the override machinery it's part of).
4. **`BezierReconstructor`** turns each `CurvePoint`'s smoothness/weight/offset
   into explicit cubic Bezier control points (`CurveGeometry`/`SegmentGeometry`),
   evaluated at a specific frame.
5. **`PathTracer`** rebuilds the actual walk order of a shape's `edges` (an
   unordered set of curve segments) by tracing connected loops/chains in an
   undirected graph keyed by rounded endpoint coordinates.
6. **`build_deform_chain`** walks a layer's ancestor chain and produces an
   ordered list of `MatrixStep`/`SkinStep`, correctly crossing into a
   `BoneLayer`'s own coordinate space at the right point for skinning
   (`Skinner.deform`, rigid vs. flexible binding).
7. **`ShapeGroupRenderer`** draws each `Mesh`'s shapes in file order into SVG
   `<path>` elements, buffering shapes into boolean-combination groups
   (`combo_mode`) since a union member's outline can't be finished until later
   group members are known.
8. **`Exporter`** is the only stateful class (per-call Skinner cache and def-id
   counter — construct one per export call, never share across concurrent
   exports) and drives `export_layer` (one layer standalone) or
   `export_document` (the whole tree, walking masking/switch-layer active
   child/visibility as it goes).
9. **CLI** (`main`) is argument parsing and file I/O only.

### Porting to Go

The module docstring's PORTING NOTES section maps each `# ==== SECTION ====`
banner to an intended Go file (`geometry.go`, `channel.go`, `style.go`,
`document.go`, `curve.go`, `pathtrace.go`, `skin.go`, `render.go`,
`main.go`/`cmd/`). If asked to port or mirror logic to Go, follow that mapping
and preserve the "thin accessor over raw data" pattern for the document model,
and the "one `Exporter` per export call" statefulness constraint.
