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

A single-file Python 3 CLI (`moho2svg.py`, ~9,300 lines, a third of it the
module docstring's evidence notes) that exports Moho vector artwork
(`.mohoproj` / `.animeproj`, which are JSON) to SVG. There is no build
system or package manifest, and no automated test suite — verification means
running an export against a real project file and comparing against a
reference SVG (see below).

**`moho2lottie.py`** is a second exporter, sharing `moho2svg.py`'s document
model and geometry pipeline (`walk_render_tree`, `build_path_bezier`), that
writes a Moho document to a Lottie JSON animation instead of SVG. Every
deformation is baked into canvas-pixel vertex positions, so every Lottie
layer keeps an identity transform. See
[`docs/moho-to-lottie-plan.md`](docs/moho-to-lottie-plan.md) for what is
implemented (all 8 planned tasks plus the post-plan additions — `combo_mode`
boolean combination, missing keyframe easing, `pyclipper`-based combo_mode==3
pre-clipping, and layer blend modes as Lottie `bm` — verified against all 19
sample documents) and what is
deliberately out of scope: shape effects other than gradients, and a
*container's* blend mode (both counted warnings — a container becomes no
Lottie layer of its own in this writer's flat model, so there is nothing left
to carry the blend); brush textures (a counted warning); layers with
particle/audio/note/3D-Poser types, and Smart Warp (a per-layer stderr
warning, shared code between both exporters via `walk_render_tree` —
`Exporter._warned_unsupported_layers`/`_warned_smart_warp_layers` — not
`moho2lottie.py`'s own counted-`Counter` mechanism) — all produce a stderr
warning rather than a silent gap.
An `ImageLayer` renders through the shared exporter when the optional
`psd-tools` package is installed (`--image-dir`), and is skipped with a
counted warning otherwise. A combo_mode==3 (intersect) shape's own fill/
outline is pre-clipped against its group's base union at export time when
the optional `pyclipper` package is installed, instead of via a Lottie
masksProperties mode "i" entry — confirmed that mode is silently ignored
(not merely imprecise) by both lottie-web's canvas renderer and LottieFiles'
own preview player, while an "a"/"s" entry on the exact same layer works
correctly in both — see `moho2lottie.py`'s own `_clip_polygon_loops`
docstring for the full evidence trail and why a hand-rolled polygon clipper
was rejected in favour of this well-tested library. Falls back to the
masksProperties "i" approximation, with a counted warning, when `pyclipper`
is absent OR when a shape's clipped topology changes across the animation
(confirmed on Bandit's own `Leg_F`/`Leg_F 2`: some combo_mode==3 members
clip stably, at least one does not, split into a different number of
disjoint pieces partway through — Lottie's own fixed-vertex-count
keyframing cannot represent that, so it is left on the older path rather
than guessed at).

The script has no *required* third-party dependencies — only the stdlib
(`argparse`, `base64`, `io`, `json`, `math`, `os`, `random`, `re`, `struct`,
`sys`, `zipfile`, `dataclasses`, `enum`, `typing`). **Pillow is an optional
dependency** (`try: from PIL import Image...`, gracefully absent otherwise)
that enables a much faster brush-texture render path — see the performance
note below. **`psd-tools` is a second optional dependency** (`try:
from psd_tools import PSDImage...`, gracefully absent otherwise) — only
needed when an `ImageLayer` references a PSD (`--image-dir`); it also
requires Pillow. **`pyclipper` is a third optional dependency** (`try:
import pyclipper`, gracefully absent otherwise), used only by
`moho2lottie.py` for the combo_mode==3 pre-clipping described above.
`jsonschema` is optional too, used only by `moho2lottie.py --validate`. All
of them install in one step with `make venv` (see Commands below).

Repository layout:

- `moho2svg.py` — the SVG exporter.
- `moho2lottie.py` — the Lottie exporter (see above); reuses `moho2svg.py`
  as a library. Two of its own optional dependencies beyond what
  `moho2svg.py` already needs: `pyclipper` (combo_mode==3 pre-clipping,
  described above) and `jsonschema` (its own `--validate` flag); `psd-tools`
  is optional too, via the shared exporter, for `ImageLayer`.
- `tools/` — verification scripts. `check_bezier_roundtrip.py` (the Lottie
  path builder agrees with the SVG one) and `check_lottie_geometry.py` (an
  emitted Lottie file agrees with what the pipeline computes directly, at any
  given frame — also accepts `--require-gradients`/`--require-masks` to assert
  a feature was actually exercised, not just silently skipped) both check this
  repository against **itself**.

  **Know what that cannot see.** Both compare the writer against the same
  pipeline that fed it, so any wrong decision the two sides *share* is
  invisible to them — a clip region read with the wrong fill rule, a mask
  band's loop ordering, the vertex ordering of a resampled loop. Three defects
  of exactly that shape once shipped past a green `make check-lottie` and were
  found by eye, in a player, much later. Two scripts exist for that blind spot,
  both reading the emitted file alone:
  `check_lottie_stability.py` (part of `make check-lottie`) asks whether each
  animated shape's keyframes can be *interpolated* — it centres consecutive
  keyframes and measures how much realigning their vertex rings would improve
  them, which is what a player smears between keyframes when correspondence
  breaks; and `diff_lottie_visible.py` (a tool, not a check) reports each
  layer's visible region — own geometry ∩ accumulated mask, by polygon algebra
  — between two Lottie files, which is how to tell a cosmetic change from one a
  viewer would notice. Reach for the second whenever a change *might* have
  moved something, or when a rendering report needs confirming or dismissing:
  it settles in a second what took a long investigation by hand.

  `check_reference_frames.py` (`make
  check-reference`) is the only one that checks it against an **outside
  authority**: real frames Moho 14.4 itself exported, under `moho/track/`
  (three documents' worth — see the script's own `CHECKS`/`WINDING_CHECKS`
  tables for exactly which). Two measurements: per-group centroid travel
  (position/shape drift) and per-shape *winding* (the sign of its enclosed
  area, which only a mirror/reflection flips). Reach for this whenever a
  change touches how time, transforms or bone flips are read — it is what
  caught the channel-cycle, Smart Bone and bone-flip-propagation regressions
  that every self-consistent (SVG-only or Lottie-only) check had passed.
  None of the three scripts needs a Lottie player or a third-party package.
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
  used for development/regression-checking. `moho/track/` holds the reference
  frame sets Moho itself exported (see `tools/check_reference_frames.py`).
- **Three further gitignored reference corpora, none of them obvious from the
  tree, and each one has already settled questions this repository could not
  answer from its own samples:**
  - `docs/moho14/` — Moho 14's own user manual, converted to per-chapter
    Markdown (35 files) by `tmp/pdf2md.py`, which needs `pymupdf`. One sentence
    of ch. 12.05 decoded both mask checkboxes; appendix G documents the render
    CLI. **Search it before measuring anything.**
  - `mohoscripts/` — 197 third-party Moho Lua scripts (121 unique). They call
    Moho's own API, so they are a second opinion on behaviour — they
    corroborated the asymmetric bone scale, flip propagation and the
    control-bone model, and supplied the cycle formula. Evidence only: do not
    copy code, and check any claim, since one of them carries an arithmetic
    slip and another a model that is only right at the default camera zoom.
    See `docs/moho-mohoscripts-plan.md` for the full analysis and its
    remaining TODO steps.
  - Moho's own scripting header, inside the app rather than this repo:
    `/Applications/Moho.app/Contents/Resources/Support/Pro/Extra Files/Lua
    Interfaces/pkg_moho.lua_pkg`. This is the highest-value source in the whole
    project and the cheapest to consult: it declares the C++ struct members in
    the order the JSON writes them, which decoded the whole `interp` entry
    (`im/v1/v2/in/h/s/t`) outright, named `s` as `stagger`, and showed the
    additive-cycle flag lives in an unserialised `flags` byte. It also settles
    every `MOHO.*` enum. Read it before inferring any field's meaning.
- `out/` — gitignored export output, regenerable by the Makefile pattern
  rules: `out/svg/ori/` (original full-texture exports), `out/svg/med/`,
  `out/svg/fast/` and `out/svg/raster/` (alternative brush-performance
  previews — see the performance note below), and `out/lottie/` (Lottie
  export output). Nothing under `out/` is tracked.
- `styles/Brushes/` — copy of Moho's own installed brush textures, tracked
  in this repository
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

**`PatchLayer` is rendered, and its own transform is a CLIP REGION.** It
carries no mesh of its own, only a `target_layer_uuid` naming another layer
whose mesh it reuses, redrawn at the patch's own point in the draw order.
Its own transform/parent_bone are **wrong for that artwork** (using them
renders a squashed sliver, confirmed) and **right for its clip**: the manual
(ch. 11.15) describes a patch as "a new CIRCLE ... position and scale [it] so
that the lines are covered", and measurement against Moho's own renders pins
the disc down exactly - radius 0.1 Moho units times the patch's own scale,
centred on its own translation, and following its own bone binding. See
`Exporter._patch_clip_path` for the three experiments and
`docs/moho-project-file-format.md` § 12.1.

## Commands

One-time setup — a local virtualenv with the optional packages (Pillow,
psd-tools, pyclipper; see Dependencies above). Nothing here is required to
run the scripts, but the brush-texture, ImageLayer and combo_mode==3
pre-clipping paths want it:

```bash
make venv                                   # creates .venv, installs Pillow + psd-tools + pyclipper
source .venv/bin/activate                   # once per shell, before the commands below
```

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
builds the three sample projects' Lottie exports and runs three scripts under
`tools/` (`check_bezier_roundtrip.py`, `check_lottie_geometry.py`,
`check_lottie_stability.py`) — see `docs/moho-to-lottie-plan.md` Task 8 for what
the first two assert, and the `tools/` entry above for the blind spot the third
exists to cover. `make` with no target prints every target with examples.

Both use one variable, **`LOTTIE_EXPORT_FLAGS`** (default
`--wind-dynamics --point-bones`), and they must: those flags change geometry,
so `check_lottie_geometry.py` has to recompute with the same ones. It once did
not — the export carried the flags and the check ran with defaults — and
`make check-lottie` reported ~100 "geometry differs" lines that were purely
the mismatch. Change the variable, never one call site
(`make check-lottie LOTTIE_EXPORT_FLAGS=` runs both sides plain).

Two more Makefile variables trade file size for a bounded amount of visual
approximation rather than changing what "correct" geometry means, so they
stay separate from `LOTTIE_EXPORT_FLAGS`: **`LOTTIE_DECIMATE_TOLERANCE`**
(default **2.0**, i.e. on by default — `moho2lottie.py --decimate-tolerance`,
`LottieExporter._decimate_frames`) drops a keyframe wherever LINEAR
interpolation between its kept neighbours already reproduces it within that
many pixels; **`LOTTIE_RIGID_TOLERANCE`** (default empty/off —
`--rigid-transform-tolerance`, `LottieExporter._rigid_ks_for_acc`) writes a
shape as a static path plus an animated layer transform instead, whenever
one shared affine matrix reproduces its whole fill+outline at every frame.
Measured on `DarkMan.mohoproj` (a user-supplied, gitignored, heavily
bone-skinned rig — see `docs/moho-to-lottie-design.md` § 4 for the numbers):
decimation alone took it from 4.14 MB to 1.94 MB; the rigid-transform flag
found almost nothing to do there (~20% of shapes qualify, none of the large
ones — a real, flexibly-skinned character rig, not a gap in the detection),
so it stays opt-in rather than a second default. `check-lottie`'s own
`check_tolerance_flag` mirrors `LOTTIE_DECIMATE_TOLERANCE` into
`check_lottie_geometry.py --tolerance=`, the same reason
`LOTTIE_EXPORT_FLAGS` has to be threaded through both sides — set
`LOTTIE_DECIMATE_TOLERANCE=` (empty) for a byte-exact export and an exact
(3e-3px) check together.

There is no test suite, linter, or formatter configured. The only way to verify
a change is to run an export against a real `.mohoproj`/`.animeproj` file and
compare against a reference SVG Moho itself exported ("File > Export
Animation") — that empirical-comparison process is how nearly every constant
and formula in this file was originally derived (see the module docstring).

### Running one check instead of all of them

Every script under `tools/` runs standalone, which is how to iterate on one
document without rebuilding everything:

```bash
# geometry of one emitted Lottie at chosen frames - PASS THE EXPORT FLAGS (see above)
python3 tools/check_lottie_geometry.py moho/Bandit.mohoproj out/lottie/Bandit.json \
        25 60 --require-masks --point-bones --wind-dynamics
# keyframe interpolability of one emitted Lottie, from the file alone
python3 tools/check_lottie_stability.py out/lottie/Bandit.json --verbose
# what visibly changed between two Lottie builds (needs pyclipper)
python3 tools/diff_lottie_visible.py old.json new.json --layer Eye_ --frames 25,60
# the outside-authority check; no per-document flag, it reads moho/track/ itself
python3 tools/check_reference_frames.py
```

`make` will not rebuild an export whose sources are untouched, so force one
with `rm -f out/lottie/Bandit.json && make out/lottie/Bandit.json`. Comparing a
STALE artifact against a fresh pipeline is a real trap — it once produced a
convincing but entirely false failure report.

### Getting ground truth out of Moho itself

Moho renders headlessly, and this is the authority every hard question in this
repository was eventually settled against (appendix G of the manual documents
the full flag set):

```bash
/Applications/Moho.app/Contents/MacOS/Moho -r FILE -f PNG -start N -end N -o OUT.png
/Applications/Moho.app/Contents/MacOS/Moho -r FILE -f SVG -start N -end N -o OUT.svg
```

`-f SVG` is how the reference frame sets under `moho/track/` were made; `-f PNG`
is required for anything Moho's own SVG export drops (blend modes, halos,
shadows — see SHAPE EFFECTS). `-shapefx no -layerfx no` turns off exactly the
effects this exporter does not implement, which makes a much fairer comparison
target. Rendering one frame of a large rig takes ~2 seconds.

**The technique worth reusing: render the same document TWICE with one field
flipped.** The difference between those two renders is that field's effect,
measured by Moho, with every unrelated modelling error in this exporter
cancelled out. Editing the JSON by hand is fine — Moho reads it back happily,
including fields hand-written into it. That is how `fixed_angle`,
`mask_expansion`, stroke exposure and the Vitruvian-bone selector were each
settled, and how a suspected regression was cleared; a plain "our render versus
Moho's" comparison is far weaker, because this exporter's own baseline error is
often larger than the effect being measured.

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
docstring's KNOWN GAPS section for what is genuinely unresolved (gradient
placement precision, bone-weight-falloff shape, brush stroke approximations,
unrendered shape effects, and the `PatchLayer` heuristic
below).

**The document camera** (`animated_values.camera_track`/`camera_zoom`) is
applied, and has its own docstring section (CAMERA) plus
`moho-animation-and-transform.md` § 9. The half vertical FOV is exactly
`30 / camera_zoom` degrees — measured against Moho's own renders, not
guessed. Moho's default camera (`z = 2 + sqrt(3)`, `zoom = 2`) satisfies
`(2 + sqrt(3)) · tan(15°) = 1` exactly, so it *is* the plain `height/2`
mapping this file used before the camera existed; `CameraView.at` snaps a
default camera back to that exact arithmetic so the ~34 documents that never
touch the camera keep byte-identical output. 12 of the 46 sample documents
animate it; ignoring it put 91% of the canvas wrong on one checked frame.
A `camera_immune` layer (and its descendants) projects through the default
camera instead. Not modelled: per-layer parallax, `camera_roll`,
`camera_pan_tilt`.

**`layer_effects.visibility`** — the animated show/hide from the General tab
— is also applied now (`Layer.visible_at`). The manual is explicit that it is
independent of the static `visible` flag; a layer draws only when both are
true. 190 layers across 14 sample documents use it.

**`layer_effects.alpha`** — the layer's own opacity, from that same
Compositing Effects group — is applied now too (`Layer.alpha_at`), on LEAF
layers. Measured as a plain linear blend (a layer at 0.5 lands on the exact
midpoint of its 1.0/0.0 renders, mean error 0.13/255), so it maps straight
onto SVG `opacity` and Lottie's transform `o`. 139 leaf layers across 15
documents set it, 11 of them animated. A **container's** own alpha is
deliberately *not* applied: three models were measured against Moho and the
best of them still scored worse than ignoring it, so it warns instead (5
layers corpus-wide) — see `Layer.alpha_at` for the table. Two knock-on
rules, both measured: a layer faded to nothing contributes nothing to a
mask, and neither does one hidden by either visibility mechanism.

**Masking is a pair of ENUMs, and the mask is built INCREMENTALLY.**
`group_mask` on the container is 0 = off, 1 = "Reveal all" (mask starts
full), 2 = "Hide all" (starts empty); each child's `masking` is one of eight
modes (clip / don't mask / add / subtract / add-invisibly /
subtract-invisibly / clear-then-add / clear-then-add-invisibly). Decoded
twice over and in agreement — Moho's own scripting header's `MM_*`
declaration order, and rendering every value with Moho itself. Three rules
that are easy to get wrong, all measured: every non-zero mode draws
*unclipped*; `masking` is completely *inert* when `group_mask == 0` (even
the invisible modes do not hide the layer then); and a layer that does not
render contributes nothing to the mask. `Exporter._mask_plan` returns one
mask state **per child**, not one per container — ten containers in the
corpus have a masked child sitting below a later "clear", and collapsing
those would clip it with a mask built out of a layer drawn after it. See the
module docstring's MASKING section and
`moho-project-file-format.md` § 10 for the measurement tables.

**Shape effects and layer blend modes** have their own two docstring sections
(SHAPE EFFECTS, LAYER BLEND MODES). Two things there are worth knowing before
touching either:

- A shape's effect can sit in any of three slots (`fill_style`, `fill_style2`,
  `line_style`) and be any of seven kinds; **only `SS_Gradient2` is
  rendered**, and everything else warns per shape. `SS_Halo` alone covers 198
  drawn shapes across 10 documents, which makes it the biggest remaining
  appearance gap. Each slot's parallel `<slot>_id` integer is now decoded — it
  is just the effect kind, agreeing with the `type` string in all 2,003
  instances.
- **A reference SVG cannot validate any of this.** Moho's own SVG export drops
  the blurred/composited effects (confirmed: its export of a document with 108
  halo shapes and 13 blend-mode layers has zero `filter`/`feGaussianBlur` and
  zero `mix-blend-mode`, while its PNG render of the same frame shows both —
  note this is specific to those effects, since that same exporter does emit
  gradients for other documents). Verify that class of change against a **raster**
  render instead — `/Applications/Moho.app/Contents/MacOS/Moho -r FILE -f PNG
  -start N -end N -o OUT.png` renders headlessly and is how the blend-mode
  mapping here was confirmed. (`-f SVG` works headlessly too, and is the way
  to produce new `moho/track/` reference frames for geometry work.)

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

### Subsystems worth extra care before touching

These have each caused a real regression once already — read the cited
docstring before changing anything nearby, and re-run `make check-reference`
afterward regardless of what you touched:

- **`Skeleton.world_matrices`** composes a bone chain's rotation, flip
  (`flip_h`/`flip_v`) and scale together. A parent's reflection (`det < 0`)
  must propagate to descendants by composing actual 2x2 matrices
  (`orient[]`); reducing that to a scalar angle sum breaks the moment any
  bone in a document flips (silently correct on every document without one).
  See that method's own "NOTE ON SCALE" and "NOTE ON FLIP PROPAGATION" for
  the full evidence trail, including the exact regression this caused and
  the verification commands to rerun. It also applies **`fixed_angle`**
  ("Independent angle", 65 bones / 11 documents): a flagged bone keeps its
  parent's position but not the parent's *departure from its own rest
  rotation*. Measured by rendering `TransformBoneTool.animeproj` with Moho
  twice, flag on and forced off, so the flag's own effect is isolated —
  worth up to 16 px. The 2026-08 re-measurement (three selective twins, see
  the note's RESIDUAL section) retires the old "~1/3 recovery" claim: under
  a clean per-axis delta metric "rest" recovers LegL at ~82%/76% and
  overshoots LegR (152%/118%), the weak spot is the nested flagged pair
  B12/B16 (48-216% of Moho's selective effect), and the remaining mismatch
  is entangled with the binding model — recorded, not tuned. See that
  method's "NOTE ON INDEPENDENT ANGLE" and `RenderSettings.fixed_angle_mode`
  (which keeps the two rejected models available so the measurement can be
  re-run).
- **The `offset` field (Offset Bone tool) is now applied** (2026-08 decode —
  see `Skeleton._solve`'s NOTE ON OFFSET and
  `docs/moho-rigging-and-deformation.md` § 3.7): the POSE carries it while
  the BIND transform basis does not, so `rest_to_pose` keeps the offset —
  a gross (100-200 px) per-layer displacement on
  `OffsetBoneTool.animeproj`, measured by Moho's own twin diff. `Skinner.build`
  now makes TWO rest calls (`bind_rest=True` for the transform basis, plain
  for the weight segments); do not collapse them back into one. The knob
  `RenderSettings.offset_mode` ("on"/"off") keeps the pre-decode behaviour
  one setting away so the measurement can be re-run. What the decode does
  NOT close: this document's per-mesh rigid-follow binding model (Moho
  moves every point of a mesh by the SAME vector) vs the exporter's
  whole-skeleton distance blend — recorded as the binding-model gap,
  fenced in `make check-reference`'s OffsetBoneTool row.
- **`interp[].im` is the interpolation method**, and it is an ENUM, not a
  bitfield — decoded twice over, by rendering each value with Moho's own CLI
  and by Moho's own scripting header (`pkg_moho.lua_pkg`), which agree on all
  twelve. `Channel._segment` dispatches on it: Linear, Smooth, Step and Pose
  each have an exactly-measured curve (99.4% of all keyframes); the other
  seven fall back to the older inferred cubic. **`Channel._smooth` is the one
  to read before touching easing** — it carries the measured tables and, just
  as importantly, a rejected variant that scores better on one rig while
  being provably not what Moho computes.
- **`Channel._parse_cycles` / `_cycle_value`** — a channel's "cycle" marker
  (`interp[i].im == 5`) makes it *replay* an earlier stretch after its last
  keyframe, but the replay **accumulates** the per-cycle delta rather than
  repeating the same values (a walk cycle walks somewhere, it doesn't walk
  in place). The test used to be `im & 4`, which also swept up `im = 6`
  (`INTERP_POSE`) and produced 1,495 zero-length phantom cycles across the
  corpus; see `moho-animation-and-transform.md` § 3.4 and § 3.6.
- **`Skeleton._control_offset`** (control bones — one bone driving another's
  angle/position/scale, `*_control_parent`/`_scale`/`_delay`) applies the
  controller's **departure from its own rest pose**, not its absolute value:
  `own_keyed(t) + control_scale × (ctrl_local(t − delay) − ctrl_local(0))`.
  Measured against Moho's own renders on `Clay_Crocodile.mohoproj` (8 frames,
  ratio 0.95–1.07 against departure, 1.3–4.4 against the raw value, so the
  rest subtraction is not a detail); the world-angle variant is ruled out by
  the same data. The delay's **sign** (earlier, not later) is measured
  separately on `Whale.mohoproj`. Chains resolve recursively with cycle
  protection. **This currently changes no exported pixel** on the corpus —
  every document using it drives ImageLayers or `strength = 0` bones — so
  `make check-reference` cannot catch a regression here; see
  `moho-rigging-and-deformation.md` § 3.3 for the reproduction commands.
- **`Skeleton.dynamic_angles`** (bone dynamics / spring physics, behind
  `--bone-dynamics`, off by default) drives the spring from the *parent's*
  world rotation, not the bone's own keyed angle — a bone with a constant
  local angle still needs to swing when its parent moves. The spring itself
  is now **decoded, not fitted** (2026-08, synthetic two-bone rigs rendered
  by Moho 14.4 with one rigidly-bound marker mesh per bone — see the
  method's EVIDENCE section and `docs/moho-rigging-and-deformation.md`
  § 3.5): per-second units, one semi-implicit Euler step per frame
  (`h = 1/fps`), spring ×96 and damping ×0.85 against the stored values;
  `torque_force` is measured NOT to couple translation (0.0000 degrees at
  torque 0.1 and 6.0 alike); `angle_weight` is live but unfitted and stays
  unread. Still unresolved (recorded, not tuned): the units of the
  parent-coupling terms, the chain solve (children see the parent's keyed
  pose, not its simulated lag), and the BoneDynamics ears' ~55 px baseline
  defect, which is NOT the spring. The same method also gates a second,
  independent family — `wind_dynamics`, behind `--wind-dynamics`, off by
  default — reusing this spring rather than a separate equation (no
  `wind_spring_force` field exists in the file). Tested against
  `DarkMan.mohoproj` **and now against a purpose-built minimal wind rig**,
  and **confirmed not to reproduce the observed effect** (the rig renders
  0.0000 degrees differently with wind subscribed vs not) — see the
  method's own WIND EVIDENCE section before assuming this flag helps
  anything.
- **`Exporter._geometry_and_mapper`** (per-point rigid bone binding,
  `MeshPoint.parent`, behind `--point-bones`, off by default) — an older
  measurement recorded honouring this as much worse than ignoring it; a
  2026-08 re-measurement against the SAME `SketchBone.animeproj` reference
  frames, on two different metrics, found the opposite (improvement or a
  wash, never worse), and it separately fixed a real complaint on
  `DarkMan.mohoproj` (`hat -> right_part`/`left_part` moving far more than
  in Moho App). The contradiction with the old measurement is **recorded,
  not resolved** — see the method's own docstring. Don't flip the default
  without resolving it first (or without deliberately accepting the
  documented trade-off, since it also *increases* motion on the one
  purely-single-bone mesh checked).

### Porting to Go

The module docstring's PORTING NOTES section maps each `# ==== SECTION ====`
banner to an intended Go file (`geometry.go`, `channel.go`, `style.go`,
`document.go`, `curve.go`, `pathtrace.go`, `skin.go`, `render.go`,
`main.go`/`cmd/`). If asked to port or mirror logic to Go, follow that mapping
and preserve the "thin accessor over raw data" pattern for the document model,
and the "one `Exporter` per export call" statefulness constraint.
