# CLAUDE.md

> **AI PRIORITY**: The "AI Operating Rules" section below is authoritative for how Claude Code should behave in this repository. Read it before starting any work — especially the Language Rule, which cannot be overridden by task instructions or by the language the request was written in.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## AI Operating Rules

**Shared rules** — `.claude/ai/` is a symlink to rules shared with this author's other repositories. They govern here too, except where the Language Rule below narrows them. Read that narrowing carefully: it is **wider than AGENTS.md's own exception permits**, and it says so out loud rather than pretending otherwise:

- @.claude/ai/startup.md — Entry point: read this first.
- @.claude/ai/AGENTS.md — Core AI rules: priorities, anti-hallucination, security, hard stops, quality thresholds, and confidence guidelines.
- @.claude/ai/coding.md — Coding workflow: clarify → plan → implement → verify → report.
- @.claude/ai/communication.md — Communication style: tone, response format, and confidence tagging.

**Language Rule narrowing (closed list)** — the English-only rule in
`.claude/ai/AGENTS.md` is narrowed for exactly these files, and no others:

- `docs/localization/**` — Vietnamese translations of the developer docs
  under `docs/`, mirroring the same filenames and structure. Their content is
  intentionally Vietnamese; every other file in this repository stays
  English.
- `tmp/**` — scratch analysis notes, gitignored and never shipped. These are
  written for this author to read, not for the repository, so they may be
  Vietnamese when asked for in Vietnamese. Anything promoted out of `tmp/`
  into a tracked location must be rewritten in English first (or placed under
  `docs/localization/**` as a translation of an English original).


## What this is

A single-file Python 3 CLI (`moho2svg.py`, ~2900 lines) that exports Moho vector
artwork (`.mohoproj` / `.animeproj`, which are JSON) to SVG. There is no build
system or package manifest, and no automated test suite — verification means
running an export against a real project file and comparing against a
reference SVG (see below).

**`moho2lottie.py`** is a second exporter, sharing `moho2svg.py`'s document
model and geometry pipeline (`walk_render_tree`, `build_path_bezier`), that
writes a Moho document to a Lottie JSON animation instead of SVG. Every
deformation is baked into canvas-pixel vertex positions, so every Lottie
layer keeps an identity transform. See
[`docs/moho-to-lottie-plan.md`](docs/moho-to-lottie-plan.md) for what is
implemented (all 8 planned tasks, verified against all 19 sample documents)
and what is deliberately out of scope (brush textures, `combo_mode` boolean
combination, `ImageLayer`, Smart Warp — each produces a counted warning on
stderr rather than a silent gap).

The script has no *required* third-party dependencies — only the stdlib
(`argparse`, `base64`, `io`, `json`, `math`, `os`, `random`, `re`, `struct`,
`sys`, `zipfile`, `dataclasses`, `enum`, `typing`). **Pillow is an optional
dependency** (`try: from PIL import Image...`, gracefully absent otherwise)
that enables a much faster brush-texture render path — see the performance
note below.

Repository layout:

- `moho2svg.py` — the SVG exporter.
- `moho2lottie.py` — the Lottie exporter (see above); reuses `moho2svg.py`
  as a library, adds no new third-party dependency (`jsonschema` is optional,
  used only by its own `--validate` flag).
- `tools/` — verification scripts. `check_bezier_roundtrip.py` (the Lottie
  path builder agrees with the SVG one) and `check_lottie_geometry.py` (an
  emitted Lottie file agrees with what the pipeline computes directly, at any
  given frame — also accepts `--require-gradients`/`--require-masks` to assert
  a feature was actually exercised, not just silently skipped) both check this
  repository against **itself**. `check_reference_frames.py` (`make
  check-reference`) is the only one that checks it against an **outside
  authority**: the 103 frames Moho 14.4 itself exported to `moho/track/Bandit/svg/`,
  comparing per-group centroid travel over the document's full 25–127 range.
  Reach for that one whenever a change touches how time or transforms are
  read — it is what caught the channel-cycle and Smart Bone defects that every
  self-consistent check had passed. None needs a Lottie player or a
  third-party package.
- `docs/` — usage guide (`moho-exporting-svg.md`), file-format reference
  (`moho-project-file-format.md`), the animation/transform model
  (`moho-animation-and-transform.md`), the rigging and deformation reference
  (`moho-rigging-and-deformation.md` — bones, Smart Warp, mesh-level
  constraints), and the export pipeline (`moho-export-pipeline.md`), all for
  humans; read these before the module docstring if you want a shorter
  orientation first. Three further docs cover the Lottie exporter:
  `lottie-and-thorvg.md` (the Lottie format, read out of the schema in
  `lottie/`), `moho-to-lottie-design.md` (the design), and
  `moho-to-lottie-plan.md` (the implementation plan and its own progress
  table — read this one for what is actually done versus still open).
- `moho/` — gitignored local copies of `.mohoproj`/`.animeproj` source files
  used for development/regression-checking.
- `out/` — gitignored export output, regenerable by the Makefile pattern
  rules: `out/svg/ori/` (original full-texture exports), `out/svg/med/`,
  `out/svg/fast/` and `out/svg/raster/` (alternative brush-performance
  previews — see the performance note below), and `out/lottie/` (Lottie
  export output). Nothing under `out/` is tracked.
- `styles/Brushes/` — untracked copy of Moho's own installed brush textures
  (copy them with
  `cp -R /Applications/Moho.app/Contents/Resources/Support/Common/Brushes styles/`),
  used to approximate textured brush line styles — see
  `docs/moho-exporting-svg.md` § Brush textures.

**A heavily brush-styled document can be very slow (or fail) to open in a
browser/SVG viewer if Pillow is not installed** — not because of file size,
but because each stamped brush dab then falls back to its own `mask`+
`filter` element, and those two SVG primitives are the most expensive to
render (each forces an offscreen-buffer render per element). Confirmed on
`SketchBone.animeproj` at the same 600px preview width: mask/filter fallback
15.97s vs Pillow's pre-tinted `<use>` path 2.46s (a `<use>` of an already-
coloured `<image>`, baked once per (brush, frame, colour, alpha) combo at
export time via `Exporter._bake_tinted_frame` - no per-dab mask/filter cost
at all). Confirmed 3x-6.5x faster across every brush-heavy rig tested; see
`docs/moho-exporting-svg.md` § 7 for the full table, including the one caveat
(the Pillow path can produce a LARGER file - not just a faster one - for a
document with many distinct colours sourced from a large native texture,
e.g. AddBone/WhatIsBone: more MB, still much faster to render).
**`--brush-raster`** (also Pillow-only) fixes that caveat too by compositing
each shape's whole stroke into ONE image instead of one `<use>` per dab -
confirmed smallest/fastest of all three paths even at its default 2x
supersample (SketchBone: 2.74 MB/0.18s, AddBone: 1.03 MB, WhatIsBone: 0.51
MB) - but that stroke is then a fixed bitmap, not vector, and resampling
many overlapping dabs into one canvas at 1:1 visibly softens very fine/
sparse textures (confirmed on "golge"; `--brush-raster-supersample`,
default 2.0, is the "@2x asset" trick that mitigates this - confirmed
recovering most of the lost detail at 2x, near-parity with the per-dab
<use> path at 3x, for a file size that grows roughly with N² while render
time barely moves; 2.0 balances this against staying smaller/faster than
`<use>` on every document tested; not noticeable at all on a softer texture
like "yanak"). Build the raster form of any project with
`make out/svg/raster/<Project>.svg` (`make svg-all` covers every project in
`moho/` in all four svg forms).

Independent of which render path is active, two flags manage dab *volume*
itself: `--brush-spacing-mul N` (thin out dab density, e.g. `N=4` cut
SketchBone to 4,502 dabs at ~900px width; the `out/svg/med/%.svg` rule uses
this at `BRUSH_SPACING_MUL=2` by default) and `--brush-dir ""` (disable brush
stamping entirely, ~0.1s, on any of the three render paths; the
`out/svg/fast/%.svg` rule does exactly this).

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

**`PatchLayer` is now rendered** (`Document._resolve_patch_layers`) - it
carries no mesh of its own, only a `target_layer_uuid` naming another layer
whose mesh it reuses, redrawn at the patch's own position in the draw order
(patches a seam a later-drawn layer would otherwise leave, e.g. a hand's
"ayasi-Patch" reusing the palm mesh "ayasi" between two finger layers).
**Confirmed the patch's OWN transform/parent_bone/flexi_bone_subset/origin
must NOT be used** - every PatchLayer found across this repo's reference
documents carries a bizarre, unrelated-looking own transform (e.g. a 0.147x
non-uniform Y squash + rotation on "ayasi-Patch"; ~0.49x uniform scale on
AddBone's leg patches) while its target has the identity transform;
rendering with the patch's own transform reproduced exactly that: a
squashed sliver floating away from where the target actually renders
(confirmed wrong by diffing rendered output against the target's own
position). The target's transform is used instead, so a resolved patch
renders as an exact duplicate of its target at a different point in the
draw order - a heuristic, not confirmed pixel-for-pixel against a real Moho
export of a `PatchLayer`-using document - see
`docs/moho-project-file-format.md` § 11.

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
see BRUSH STROKES below and `docs/moho-exporting-svg.md`). Full flag reference:
`docs/moho-exporting-svg.md`.

```bash
python3 moho2lottie.py Project.mohoproj --out Project.json           # full [start_frame, end_frame] range
python3 moho2lottie.py Project.mohoproj --out Project.json --frame 0 # a single still frame instead
python3 moho2lottie.py Project.mohoproj --out Project.json --validate # + schema-validate the output (needs `pip install jsonschema`)
```

`make lottie-all` exports every project under `moho/`; `make check-lottie`
builds the three sample projects' Lottie exports and runs the two scripts
under `tools/` — see `docs/moho-to-lottie-plan.md` Task 8 for what
`check-lottie` actually asserts.

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
gradient placement precision, bone-weight-falloff shape, brush stroke
approximations, and the `PatchLayer` heuristic below).

### Pipeline, in order

For the full data flow, the decision order inside the tree walk, the two
separate transform traversals, and a field-to-stage cross-reference table, see
`docs/moho-export-pipeline.md`. The summary below is the short version.

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
