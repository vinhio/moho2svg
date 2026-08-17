# Lottie to Moho Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `lottie2moho.py`, a stdlib-only CLI that reads one animated Lottie JSON file and writes one `.mohoproj` file (version `1045`) that Moho 14 can open, with artwork and animation reconstructed as a **flat, unrigged, densely-keyframed** document — no bone recovery, every animated vertex becomes a point-animation channel.

**Architecture:** A new writer that builds raw Moho JSON dicts directly (the existing document model in `moho2svg.py` is read-only wrappers and cannot be written through). It imports only the *constants and tables* `moho2svg.py` already documents — coordinate conversion, the `SS_Gradient2` ↔ Lottie table, `BLEND_MODE_LOTTIE`, line cap/join tables — inverted where needed. Nothing in `moho2svg.py` or `moho2lottie.py` changes; their byte-identical exports are the regression gate.

**Spec:** [`lottie-to-moho-design.md`](lottie-to-moho-design.md) — read it before Task 1. This plan implements that design and does not restate its reasoning. The forward plan's conventions ([`moho-to-lottie-plan.md`](moho-to-lottie-plan.md)) apply here too: same commit style, same verification philosophy.

---

## Progress

This table is the single place to read overall status. Each task's own steps
carry `- [ ]` checkboxes further down.

**How to update it.** A task becomes `DONE` only when its **final commit has
landed** and its stated check passed — not when the code is written. Tick the
task's step checkboxes as you go, then flip the row and record the commit.
Anything that is started but unfinished is `IN PROGRESS`, and its row says
which step it stopped at, so a reader knows where to resume.

| # | Work item | Status | Commit |
|---|---|---|---|
| 1 | CLI, root document and the one root GroupLayer | OPEN | |
| 2 | Static artwork: curves, points, the smoothness fit, styles, gradients | OPEN | |
| 3 | Layer kinds: null, solid, image, precomp, parent flattening, ordering | OPEN | |
| 4 | Transform channels: p/a/s/r/o, split position, static and animated | OPEN | |
| 5 | Path animation: point channels, topology split, easing mapping, frame rounding | OPEN | |
| 6 | Masks and combo-mode heuristics | OPEN | |
| 7 | Warnings, `--validate`, make targets, the roundtrip check script, docs | OPEN | |

---

## Global Constraints

- **English only** in every file, comment, docstring, commit message and printed string. See `.claude/ai/AGENTS.md`.
- **No new required third-party dependency.** `jsonschema` is optional in the same way the forward writer's already is: try to import, skip with a printed note if absent.
- **Standard library only** in `lottie2moho.py` and every script under `tools/`.
- **Commit style:** plain imperative sentences, matching `git log`. Not Conventional Commits. No tool attribution, no AI co-author trailer.
- **Every document must carry a docstring.** New file, new class, new function, including private helpers. Match the density and tone of `moho2svg.py`, which explains *why* a constant is what it is.
- **`make check-reference` and `make check-lottie` must keep passing** after every task. Neither writer is modified, so this gate should never move — but it is run anyway, exactly because "should never move" is what every regression said before it happened.
- **Never silently skip a feature.** Anything not exported increments a counter that is printed to stderr at the end of an export.
- Coordinates are written with 3 decimal places, matching `build_path_d`'s `f"{x:.3f}"`.

---

## File structure

| File | Responsibility |
|---|---|
| `lottie2moho.py` (create) | The writer and its CLI. One file with `# ==== SECTION ====` banners, mirroring how `moho2svg.py` is organised. Imports only constants/tables from `moho2svg.py`. |
| `tools/check_lottie_roundtrip.py` (create) | Proves the roundtrip: Moho → Lottie (existing) → Moho (new) → Lottie (existing) preserves per-shape centroid and winding, at keyframe frames exactly and between them within tolerance. |
| `Makefile` (modify) | Adds `out/moho/%.mohoproj` and `check-roundtrip`. |
| `CLAUDE.md` (modify) | Documents the new tool, its make targets, and its unrigged-import contract. |

---

## Task 1: CLI, root document and the one root GroupLayer

**Status:** OPEN

**Files:**
- Create: `lottie2moho.py`

**Interfaces:**
- Consumes: a Lottie JSON file (`v`, `fr`, `ip`, `op`, `w`, `h`, `layers`).
- Produces: a `.mohoproj` with `mime_type`, `version: 1045`, `major_version: 1`, `rev_version: 0`, `project_data` (width/height/start_frame/end_frame/fps mapped from `w`/`h`/`ip`/`op`/`fr`), an empty `styles` list, `animated_values: {}`, and ONE root `GroupLayer` whose `layers` is empty for now.

**Steps:**

- [ ] **Step 1: Write the failing acceptance probe**

`moho2svg.py` must be able to READ the output before any geometry exists. Probe: `lottie2moho.py <any-lottie> --out /tmp/t1.mohoproj`, then `python3 moho2svg.py /tmp/t1.mohoproj --list` — must print the root group and 0 vector layers, exit 0. If `--list` crashes on a field the writer omitted, that field is the next one to add — the probe drives the shape of the writer, not a guess.

- [ ] **Step 2: `main()` and argument parsing**

`lottie2moho.py <input.json> [--out FILE] [--validate] [--assets-dir DIR]`. Default output `<input-stem>.mohoproj`. `--assets-dir` controls where § 9 of the design writes embedded images (default: `<output>.assets/`, created only when needed).

- [ ] **Step 3: The root object builder**

One function building the JSON skeleton above. Frame range from `ip`/`op`; `start_frame`/`end_frame` inclusive of both ends (the forward writer samples `range(start, end + 1)` — so the inverse must set the same inclusive bounds or the roundtrip loses a frame).

- [ ] **Step 4: Run the gates**

`make check-reference` + `make check-lottie` still pass (nothing shared changed — proving that is the point).

---

## Task 2: Static artwork — curves, points, the smoothness fit, styles, gradients

**Status:** OPEN

**Files:**
- Modify: `lottie2moho.py`

**Interfaces:**
- Consumes: one `ty: 4` layer's `shapes` (`gr`, `sh`, `fl`, `st`, `gf`, `gs`, `rc`, `el`, `sr`) at their frame-0 values.
- Produces: one `MeshLayer` per `ty: 4` layer, with `mesh.points` / `mesh.curves` / `mesh.shapes` built per § 5 of the design, inline `style` dicts per shape, `SS_Gradient2` fills/outlines per § 7.

**Steps:**

- [ ] **Step 1: Loop → curve/points conversion**

One Lottie subpath → one closed Moho `Curve` (`closed: true`) with one point per vertex. Keep Lottie's winding exactly (design § 5.5): the subpath vertex order is written through unchanged.

- [ ] **Step 2: The smoothness/weight/offset fit**

Per design § 5.2: minimize handle error against `moho2svg.py`'s own `BezierReconstructor` output — a small numeric solver per point (evaluate the documented forward model, refine the two unknowns per handle direction). Write the fitted parameters into `weight_in`/`weight_out`/`offset_in`/`offset_out`/`smoothness`. The docstring records the measured error of the fit on the sample corpus — this number is the acceptance criterion for the whole task.

- [ ] **Step 3: Fills, strokes and gradients**

`fl`/`st` → `has_fill`/`has_outline` + inline style fields; `gf`/`gs` → `SS_Gradient2` using the inverse of `moho2lottie.py`'s own `t` ↔ `gradient_type` table. Line caps/joins reverse the forward tables. Unknown gradient types and shape effects: counted warning.

- [ ] **Step 4: Primitives**

`rc`/`el`/`sr` → closed curves (design § 5.4), `rd` applied for `rc`/`el`.

- [ ] **Step 5: The static roundtrip probe**

Moho (a static doc, e.g. `SlickObjectTransition.mohoproj`) → Lottie → Moho → `moho2svg --combined` on both, compare per-shape centroids/windings. This is the first real measurement of the fit — record the numbers in the check script's docstring and set the tolerance there.

- [ ] **Step 6: Run the gates**

`make check-reference` + `make check-lottie` still pass.

---

## Task 3: Layer kinds — null, solid, image, precomp, parent flattening, ordering

**Status:** OPEN

**Files:**
- Modify: `lottie2moho.py`

**Interfaces:**
- Consumes: the full Lottie `layers` list including `ty` 3/1/2/0, `parent` indices, `refId` assets.
- Produces: the corresponding Moho layer tree per design § 4.2, in Moho draw order (§ 4.4 both reversals).

**Steps:**

- [ ] **Step 1: `ty` 3 null and `ty` 1 solid**

Null → `GroupLayer`; solid → `MeshLayer` with one filled rectangle shape. Trivial; done first because Task 4 needs them to host transform channels.

- [ ] **Step 2: `ty` 2 image with asset writing**

Embedded PNG/JPEG → `<assets-dir>/<name>.<ext>` beside the output; `ImageLayer` with `image_path`/`image_width`/`image_height` from the asset's own `w`/`h` (the forward pipeline's IMAGE LAYERS section confirms the shape of data it reads back). Missing/unparseable asset data: counted warning, layer dropped.

- [ ] **Step 3: `ty` 0 precomp inlining**

Referenced asset layers copied inline as the group's children, `ip`/`op` windows clamped (design § 9). Recursion, with a depth guard against a self-referencing precomp.

- [ ] **Step 4: Parent flattening**

Compose a parented layer's transform per frame and store the absolute channels on the child (design § 4.2). Nested `ty: 0` content keeps real tree nesting; `parent` of a non-precomp layer is flattened.

- [ ] **Step 5: Both ordering reversals**

Layers reversed into Moho tree order; shape blocks reversed into `mesh.shapes` order (design § 4.4). Write the probe FIRST: a hand-built two-layer, two-shape Lottie must come out with the backmost shape first in both lists — the forward design's § 2.3 failure mode, reversed.

- [ ] **Step 6: Run the gates**

---

## Task 4: Transform channels — p/a/s/r/o, split position, static and animated

**Status:** OPEN

**Files:**
- Modify: `lottie2moho.py`

**Interfaces:**
- Consumes: `ks` of every layer kind.
- Produces: Moho `translation`/`scale`/`rotation_z`/`origin` channels and `layer_effects.alpha` per design § 4.3, bare scalars when static.

**Steps:**

- [ ] **Step 1: Channel builder**

One `LottieKeyframes → {"when", "val", "interp"}` helper. `when` = rounded integer frames; duplicate frames collapse (keep the later — design § 12.4). Animated → channel, single keyframe → bare scalar. `interp` values: linear → `im == 0`, hold → Step, else Smooth with the `easing_approximated` counted warning (design § 6.2).

- [ ] **Step 2: The five mappings**

`p` → `translation` (split position `x`/`y` merged onto one frame list); `a` → `origin`; `s` → `scale` (percent ÷ 100); `r` → `rotation_z`; `o` → `layer_effects.alpha` (percent ÷ 100). Static Lottie properties stay scalars.

- [ ] **Step 3: Animated roundtrip probe at keyframe frames**

Bandit's Lottie (built by `moho2lottie.py`) → Moho → `moho2lottie.py` again; compare `L2`'s per-layer `ks` against `L`'s **at every frame** — for repo-generated Lottie every frame is a keyframe, so this comparison must be exact, not tolerated (the design's § 6.4 note: easing approximation only shows on external Lottie files).

- [ ] **Step 4: Run the gates**

---

## Task 5: Path animation — point channels, topology split, frame rounding

**Status:** OPEN

**Files:**
- Modify: `lottie2moho.py`

**Interfaces:**
- Consumes: animated `sh.ks` (`"a": 1` with per-keyframe `v`/`i`/`o`), including vertex-count changes.
- Produces: `mesh.points[k].position` channels keyed at every sampled frame (design § 6.3); one shape per topology phase under a `SwitchLayer` when the count changes (§ 5.3); the fitted handle parameters stay static (Moho does not animate smoothness — it animates positions).

**Steps:**

- [ ] **Step 1: Per-vertex point channels**

The union of all keyframe times of the shape's path becomes the frame list; each vertex's position channel carries one value per frame. Handle fit from Task 2 stays per-shape static.

- [ ] **Step 2: Topology split**

Detect vertex/subpath-count change between keyframes. No change → one shape (the common case). Change → phase shapes under a `SwitchLayer` whose `switch_keys` selects the phase per frame window (design § 5.3), counted warning `vertex_count_changed`.

- [ ] **Step 3: Frame rounding and collapse**

Round keyframe times to Moho's integer grid; collapse duplicates keeping the later value (the design's open question 4 — record the behaviour chosen in the docstring).

- [ ] **Step 4: Animated roundtrip probe**

Bandit (the walk cycle — every frame baked, vertices move every frame) → Lottie → Moho → Lottie; compare `v`/`i`/`o` per shape per frame exactly. This is the hardest probe in the plan: if the fit's error propagates into visible drift here, the fit tolerance from Task 2 is the first suspect.

- [ ] **Step 5: Run the gates**

---

## Task 6: Masks and combo-mode heuristics

**Status:** OPEN

**Files:**
- Modify: `lottie2moho.py`

**Interfaces:**
- Consumes: `masksProperties` on any layer.
- Produces: the design § 8 mapping — first `a`-mask → mask-source `MeshLayer` + `GroupLayer` with `group_mask: 2` + `masking: 2`/`1` on members; foldable `s`/`i` chains onto `masking`/`combo_mode`; the rest counted warning `mask_chain_approximated`.

**Steps:**

- [ ] **Step 1: The single-`a`-mask container mapping**

The faithful common case, done exactly as the forward writer reads it back (its own `masking`/`group_mask` field semantics are the spec).

- [ ] **Step 2: Chain folding**

Leading `a` + trailing `s` chains → `combo_mode` 2/3 where the layer is a single shape (design § 8). Everything else: counted warning, drawn unmasked.

- [ ] **Step 3: Roundtrip probe on Bandit**

Bandit carries 4 mask containers and combo groups; its Lottie has both mask entries and pre-clipped shapes. Roundtrip and measure how much survives exactly vs. within tolerance — record the measured fidelity in the check script's docstring; do not silently loosen the tolerance to make it pass.

- [ ] **Step 4: Run the gates**

---

## Task 7: Warnings, `--validate`, make targets, the roundtrip check script, docs

**Status:** OPEN

**Files:**
- Modify: `lottie2moho.py`, `Makefile`, `CLAUDE.md`
- Create: `tools/check_lottie_roundtrip.py`

**Steps:**

- [ ] **Step 1: The warning table**

One `WARNING_EXPLANATIONS` dict, one counted stderr line each at end of run: `text_layer`, `expression`, `layer_3d`, `matte`, `trim_path`, `repeater`, `easing_approximated`, `mask_chain_approximated`, `blend_mode_unknown`, `vertex_count_changed` — the design § 10 list.

- [ ] **Step 2: `--validate`**

Validate the emitted `.mohoproj` against the repository's own fragment schemas under `schema/` (project, layer, mesh, shape, style) with the optional `jsonschema` package — same opt-in pattern as `moho2lottie.py --validate`.

- [ ] **Step 3: `tools/check_lottie_roundtrip.py`**

The § 11.2 pipeline as a standalone script: for each sample document, Moho → Lottie → Moho → Lottie, then per-shape centroid travel + winding sign comparison at every frame, keyframe frames exact and between-keyframe tolerance recorded from Tasks 2–6's measurements. Exit 0/1. No Lottie player, no third-party package.

- [ ] **Step 4: Make targets**

`make out/moho/%.mohoproj` (any `out/lottie/%.json` → `out/moho/%.mohoproj`) and `make check-roundtrip` (builds the three sample Lottie files, converts, runs the check script). `out/moho/` is already covered by the `out/` gitignore line.

- [ ] **Step 5: CLAUDE.md**

Document the new tool in "What this is" (one paragraph — the unrigged-import contract in one sentence), the Commands section, and the repository layout. Mention the roundtrip check beside the other `tools/` scripts.

- [ ] **Step 6: Full verification**

`make check-reference`, `make check-lottie`, `make check-roundtrip` all pass on the 19-document corpus; the three sample SVGs stay byte-identical.

---

## Open questions (from the design, restated as acceptance criteria)

1. **Fit quality** — Task 2 Step 5 measures it. If the roundtrip tolerance is unachievable, the fallback is dense handle-animation instead of the fitted parameters (design § 12.1). Decided by measurement, not by debate.
2. **Mask chain folding depth** — Task 6 Step 3 measures how much of Bandit's masking survives exactly. The folding aggressiveness is tuned from that number.
3. **Fractional-frame collapse** — Task 5 Step 3 records the chosen rule; a real external Lottie with half-frame keyframes may force revisiting it.
4. **Group opacity** — deliberately not written until the forward side decodes it (design § 12.2). Not a task in this plan.
