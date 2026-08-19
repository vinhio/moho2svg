# Moho Field Coverage — Design

**Status:** approved in conversation 2026-08-18. Implementation plan:
[`../../moho-field-coverage-plan.md`](../../moho-field-coverage-plan.md) (written after this spec).

**Goal.** Raise this repository's understanding of the `.mohoproj` /
`.animeproj` / `.moho` format from a measured **35.5%** to **95%** of the keys
that carry document *content*, so that a script can change anything a person
could change in the Moho application. Editing coverage first; render coverage
second.

**Non-goal.** Rendering fidelity for every field. That is Phase 2, scoped after
Phase 1 closes, and it is a different and much larger body of work — a text
layer's `font` needs one line to *edit* and a font rasteriser plus mesh
generator to *render*.

---

## 1. Why the measurement had to change first

The 29% figure this work started from was produced by searching each corpus key
as a quoted string literal across the four Python entry points. That method is
wrong in both directions:

- **Over-counts.** A literal can sit in a comment or a docstring while nothing
  reads the value.
- **Under-counts.** Channel keys (`when`, `val`, `interp`, `actions`) are
  consumed generically through variables, so they never appear as literals at
  the point of use.

A target of 95% cannot rest on an instrument with unquantified error in both
directions. The first deliverable is therefore a **new instrument**, not new
decoding — see § 4.

A second, larger measurement error was found while scoping this work: the
original census read only the 46 bare-JSON documents under `moho/` and skipped
the **30 `.moho` archives** entirely, because `.moho` is a ZIP container. Those
30 files changed several conclusions:

| | 46-document census | 76-document census |
|---|---|---|
| Distinct keys | 536 | **547** |
| `AudioLayer` instances | 0 — believed absent, samples were requested | **7 — already present** |
| `ParticleLayer` instances | 2 — too few to decode | **39** |
| `NoteLayer` instances | 1 | 5 |
| Largest unrendered shape effect | `SS_Halo` (198) | **`SS_Shaded` (775)** |
| Format versions | 1021, 1038, 1039, 1045 | + **1040** |

The lesson is recorded here because it generalises: **every measurement in this
plan must state which corpus it ran against**, and the corpus is all 76
documents at any nesting depth, archives included.

---

## 2. The corpus

All files under `moho/`, recursively, at any depth:

- **76 documents**, 0 parse failures — 46 bare `.mohoproj`/`.animeproj` plus 30
  `.moho` ZIP archives (each holding one `Project.mohoproj`, optionally a
  `preview.jpg`).
- Format versions: 1021 ×2, 1038 ×17, 1039 ×46, 1040 ×1, 1045 ×10.
- **547 distinct JSON keys**, 40,991,416 key occurrences.
- Layer types present, of the 12 Moho declares: `MeshLayer` 4,969,
  `GroupLayer` 615, `ImageLayer` 332, `BoneLayer` 321, `SwitchLayer` 251,
  `TextLayer` 46, `ParticleLayer` 39, `PatchLayer` 12, `AudioLayer` 7,
  `NoteLayer` 5. Absent: `Mesh3DLayer`, `LT_UNKNOWN`.
- Shape effects: `SS_Gradient2` 1,593, `SS_Shaded` 775, `SS_Soft` 258,
  `SS_Halo` 198, `SS_Crayon` 26, `SS_Texture2` 12, `SS_Shadow` 3.

Reference material that outranks inference, in order: Moho's own scripting
header (`pkg_moho.lua_pkg` — 43 classes, 396 data members, 128 enum constants
in 22 families, declared in the order the JSON writes them), Moho's headless
CLI for twin renders, `docs/moho14/` (Appendix F is the only official format
documentation, and it states outright that layer properties are "too many to
name in this document" — **no complete official field reference exists**), and
`mohoscripts/` as corroboration only.

---

## 3. The denominator: content versus description

Not every key can be "understood" in a way that serves an editor.
`DocState_gridSize` records the editor's grid spacing; decoding it teaches
nothing about the artwork. Keys are therefore split once, conservatively — a key
goes to DESCRIPTION only when there is a positive reason, so the split cannot
flatter the coverage figure.

**DESCRIPTION — 113 keys, excluded from the metric:**

| Group | Keys | Why |
|---|---|---|
| View state | 49 | `documentviewstate`, `DocState_*` — editor grid/zoom/safe zones. Optional per Appendix F; defaults apply when absent. |
| Foreign script blobs | 24 | 16 `g_<number>` flags, `NewLayerScript`, `LM_GrandpaBones`, six `*_sec` tokens. |
| Editor selection / panel state | 14 | `expanded`, `selected`, `shown_in_timeline`, `label_col`, `shy`, `hidden`, `previewAlignment`, … |
| Onion skin | 14 | `onions_*` — editor overlay. |
| Document identity / provenance | 12 | `mime_type`, `version`, `doc_uuid`, `created_date`, `comment`, `thumbnail`, … |

`random_num` is deliberately kept in CONTENT despite looking like editor state:
it seeds brush jitter, so it changes the rendered stroke.

**CONTENT — 434 keys, the denominator:**

| Bucket | Keys | Nature of the work |
|---|---|---|
| **A** modelled today | 154 | — |
| **B** writer-template only | 144 | Writers already emit real-file-correct values; mechanical to adopt. |
| **C** untouched | 136 | Needs measurement. |

Bucket C by how it can be measured:

| Sub-bucket | Keys | Route |
|---|---|---|
| Value varies across the corpus | 63 | Observable from the 76 documents we already hold. |
| Object- or channel-valued | 34 | Container shape already understood (Channel / Color / FileRef); only the semantic label is missing. |
| **One constant value in all 76 documents** | 39 | Not observable. Requires a synthesised document — see § 6. |

**Target: 413 of 434 keys (95.16%). Residual budget: 21 keys.**

*(Corrected 2026-08-19. This section first said 412 keys / 22 residual, taking
`round(434 x 0.95) = 412`. But `412 / 434 = 94.93%`, which is below the bar the
section claims — reaching >= 95.0% requires 413. The plan would otherwise have
closed one key short while reporting success.)*

The 16 `g_*` flags deserve a note, because they consumed the whole residual
budget under the previous denominator. They appear in **49 of 76 documents**,
yet they are absent from Moho's Lua header, absent from the whole
`Moho.app/Contents/Resources/Support/` tree, and absent from all 197 scripts in
`mohoscripts/`. Their origin is unknown and they are only decodable by a *GUI
twin-save* — save the same document twice from the Moho application with one
setting changed and diff the JSON — which no headless method can perform. They
now sit in DESCRIPTION, so they cost the metric nothing.

---

## 4. The registry, and a machine-checkable definition of "covered"

### 4.1 Measured by runtime trace, not by grep

Every raw dict is wrapped in a tracing mapping that records each key actually
read. The exporters then run over all 76 documents. A key never read during any
export is **provably** unconsumed; a key read at least once is provably
consumed. This replaces the string-literal search entirely.

### 4.2 Four dispositions

Every one of the 547 keys carries exactly one disposition. Excluding a key from
the *metric* never excludes it from the *code*: an editor that drops
`documentviewstate` on save has changed the file even though it changed no
artwork.

| Disposition | Machine-checked acceptance | Counted in the 434? |
|---|---|---|
| `EDITABLE` | The § 6 probe has run and recorded its result (positive **or** negative); a typed accessor exists; a test sets the value, saves, Moho loads the result, and the value reads back unchanged | yes |
| `MODELLED` | Everything `EDITABLE` requires, **and** the trace observes a real read during an export, **and** a named check asserts the rendered effect — `check_reference_frames.py`, `check_lottie_geometry.py`, or the probe's own recorded pixel diff | yes |
| `PRESERVE` | The round-trip test proves the key survives load→save unchanged | no — but mandatory |
| `UNKNOWN` | None of the above. **Must record what was tried and why it failed.** | no — counts against the 5% |

Coverage = (`MODELLED` + `EDITABLE`) / 434 ≥ 95%, reported by
`make check-coverage`.

**`EDITABLE` is the Phase 1 target for every content key; `MODELLED` is the
Phase 2 target.** The two are a ladder, not alternatives — `MODELLED` is
`EDITABLE` plus a renderer. This is what keeps Phase 1's 95% an *editing*
milestone: a key that provably affects rendering still counts once its semantics
are decoded, an accessor exists and it round-trips, even though nothing draws it
yet. The probe's positive result is then recorded in the registry as
`x-moho-render: pending`, which becomes the Phase 2 backlog — generated from the
registry rather than written by hand.

The 154 keys already at `MODELLED` keep that disposition; they are not
downgraded.

The `UNKNOWN` reason requirement is what keeps the 22-key residual auditable
rather than a dumping ground for unfinished work.

### 4.3 Where the registry lives

As an `x-moho-disposition` annotation on each property in the existing
`schema/*.schema.json` tree. JSON Schema ignores unknown keywords, so
`moho2lottie.py --validate` keeps working unchanged.

Rationale: `schema/` already declares 471 keys with prose `description`s and is
already validated against the corpus. A second registry file would duplicate
that and drift from it. Embedding also forces the schema to reach all 547 keys
— it currently misses 24 (13 previously known, plus the 11 found only in the
`.moho` archives: `audio_path`, `audio_level`, `audio_fileref`, `audio_jump`,
`audio_text`, `spatial_positioning`, `image_cropping_min`,
`image_cropping_max`, `audio_file_sec`, `image_sec`, `images`).

The checker still **prints a Markdown table** grouped by feature area, so the
state stays readable without opening JSON.

### 4.4 Two fail-closed rules

- A corpus key with no registry entry → **fail**. A key cannot be forgotten.
- A key declared `MODELLED` that the trace never observes → **fail**. A key
  cannot be claimed.

---

## 5. M0 — the foundation

M0 deliberately moves the coverage number very little. Its purpose is to make
every later number verifiable. **Its order is load-bearing.**

**M0.1 — Fix the `PatchLayer` load-time mutation.**
`Document._resolve_patch_layers` overwrites every `PatchLayer`'s own
`parent_bone`, `flexi_bone_subset` and `origin` with its target's, mutating the
raw dict during construction. A patch's own transform *is* its clip region, so
loading such a document and saving it loses data. This must be fixed before any
write path exists. 12 patch layers in the corpus.

**M0.2 — Read and write `.moho` ZIP containers.**
Must precede M0.4: 30 of the 76 documents are archives, and running the trace
first would produce a baseline from 46 files — repeating the exact error § 1
describes. `preview.jpg` is preserved byte-for-byte when present, with a
warning that it is now stale relative to the content, plus a flag to drop it so
Moho regenerates it on its next save.

**M0.3 — Round-trip test over all 76 documents.**
`tools/check_roundtrip.py`: load → save → compare structurally, standard
library only. Plus a Moho render diff on three representative documents, kept
small so it stays runnable. This test is what protects the 113 `PRESERVE` keys.

**M0.4 — Trace, registry scaffolding, `make check-coverage`.**
Produces the **real baseline**. Both fail-closed rules from § 4.4 land here.

**M0.5 — Integrity checker, detect-only.**
Reports violations of the 14 index-based reference classes and the three
name-based couplings. Automatic renumbering is explicitly **not** in M0; it
belongs to the first structural-edit operation that needs it.

### Code placement

- **In place in `moho2svg.py`:** retain `_raw` on `Mesh`, `Shape`, `Curve`,
  `CurvePoint`, `MeshPoint`, `Bone`, `Skeleton`, `Transform`, and give
  `Document` its root dict back. **The retained dict must be the very object in
  the parsed tree, never a copy** — an invariant this section originally failed
  to state. A copy satisfies every check the task defines while making editing
  through the model silently do nothing, so it is the one way this task could
  pass and still be worthless. Verified after the fact: an edit written through
  `shape.raw` reaches the saved file. Purely additive; no read behaviour changes. The
  document model is *not* duplicated — a second copy would drift from Moho.
- **New module for editing** (`mohoedit.py`): index renumbering, integrity
  checks, save, ZIP support. These are genuinely new responsibilities, and
  `moho2svg.py` is already 9,576 lines — `CLAUDE.md` notes that a file growing
  large is a signal it does too much.

### Regression gate, every task

`make check-lottie` passes, and `make check-reference` is re-run **regardless of
what the task touched** — `CLAUDE.md` requires this, and it is what caught the
channel-cycle, Smart Bone and bone-flip regressions that every self-consistent
check passed. Verified green at the time of writing.

**Correction to an earlier draft of this section:** it required "the five tracked
SVGs stay byte-identical", carried over from `moho-to-lottie-plan.md`. That gate
no longer exists — `git ls-files '*.svg'` returns nothing, because the Makefile
restructure moved every export under the gitignored `out/`. Nothing currently
detects a byte-level change in SVG output. The first task of M0 therefore
*builds* that gate (`tools/check_export_stability.py` plus a tracked hash file),
because every later task needs it and M0.1 in particular is a refactor whose
whole claim is that output does not change.

A second Makefile gap found while scoping: `PROJECT_STEMS` globs only
`moho/*.animeproj` and `moho/*.mohoproj`, so every `make` aggregate target sees
46 documents, not 76 — no subdirectories, no archives. M0.2 fixes this alongside
ZIP support.

---

## 6. How a key is proven understood

One uniform triage probe, then two branches. Without this, 258 keys would be
258 separate investigations and the plan would not be feasible.

**The probe.** For a key: take a corpus document carrying it; produce two
variants, one at the observed value and one at a plausible alternative; render
both with Moho headless; diff the pixels.

- **Pixels change** → the key affects rendering, and the diff *is* the
  measurement of its effect. In Phase 1 it reaches `EDITABLE` and is stamped
  `x-moho-render: pending`; rendering it is Phase 2 work. This is the
  established method in this repository — it decoded `fixed_angle`,
  `mask_expansion`, stroke exposure and both masking enums.
- **Zero change** → the key is inert for rendering. It reaches `EDITABLE` and is
  **finished** — there is no Phase 2 work for it at all. **The negative result is
  recorded as evidence**, following the precedent of the wind-dynamics
  measurement (0.0000° difference).

Either way the probe must run: `EDITABLE` is not reachable by declaring a key
uninteresting. What the two branches decide is the size of Phase 2, not whether
Phase 1 can close.

**Cost.** The baseline render is shared across every key probed in the same
document, so the whole sweep is roughly one baseline plus one render per key —
about 270 renders, ~10 minutes of machine time. Analysis and synthesis dominate,
not rendering. Independent probes parallelise across Moho processes.

**Why the 39 constant-valued keys are expensive.** Many are meaningless without
a precondition: `physics_torque` does nothing while `enable_physics` is off;
`3d_shading_density` does nothing while `3d_mode == 0`. The probe harness must
accept **per-key preconditions** — enable the prerequisite, then vary the key
under test. This is the cost, not the rendering.

**Keys that cannot be synthesised at all.** `switch_data` is `""` in all 45
documents that carry it; `layercomps` and `action_refs` are empty in all 76. A
value cannot be invented for a grammar that has never been observed. These are
the natural residents of the 22-key residual — after the manual and the Lua
header have been tried.

**Tooling.** `tools/probe_field.py --key NAME` runs the triage and records the
result to a file, so every probe is repeatable and no claim rests on narration.

---

## 7. Task decomposition

Percentages below are computed from the grep baseline and **must be recomputed
at M0.4**, when the trace produces the real one. The plan document carries this
warning at the top of its progress table.

| Milestone | Content | Keys | Cumulative |
|---|---|---|---|
| M0 | Foundation (§ 5) | 0 | *real baseline* |
| M1.1 | Template: camera / project / transforms + shared | 72 | 52.1% |
| M1.2 | Template: image / PSD | 21 | 56.9% |
| M1.3 | Template: style / shape effects | 15 | 60.4% |
| M1.4 | Template: mesh / point + compositing | 22 | 65.4% |
| M1.5 | Template: remainder | 14 | **68.7%** |
| M2.1 | Bone IK + constraints + physics — 72/76 documents | 27 | 74.9% |
| M2.2 | Particle — 39 layer instances | 16 | 78.6% |
| M2.3 | Text + balloon | 12 | 81.3% |
| M2.4 | Sketchy / noise / textures | 8 | 83.2% |
| M2.5–2.9 | Image, mesh, audio, layer order, compositing, channel, style | 34 | **91.0%** |
| M3.1 | 3D extrude — one `3d_mode = 1` precondition unlocks all | 10 | 93.3% |
| M3.2 | Bone physics — `enable_physics` precondition | 5 | 94.5% |
| M3.3 | Sketchy + mesh remainder | 5 | **95.6%** ✅ |

Residual: **19 keys** (budget 22) — text 9, particle 6, and one each from style,
compositing, switch and audio. All are constant-valued; each needs a recorded
failure reason.

Three properties of this ordering are deliberate:

1. **M1 is 144 of the 258 keys and needs almost no measurement.** It carries the
   figure from 35% to 69% at the lowest risk, and it matures the registry and
   the checker before the hard work begins.
2. **M2.1 is the most valuable single task.** Bone IK, constraints and physics
   appear in 72 of 76 documents and are at 0% today; they are also what a rig
   editing script needs most.
3. **M3.1 is unusually efficient.** All 12 `3d_*` keys are inert because
   `3d_mode == 0` everywhere, so one synthesised document unlocks the group.
   `enable_physics` does the same for five bone keys.

---

## 8. Risks

- **The trace baseline may be lower than 35.5%.** If so, the milestone
  percentages shift and M1 may need to be split further. This is a measurement
  correction, not a scope change, and it is why § 7's numbers are provisional.
- **A probe can be confounded by a missing precondition** and record a false
  negative: a key marked "no Phase 2 work" that really does affect rendering.
  Because both probe branches reach `EDITABLE`, this cannot corrupt the Phase 1
  figure — it can only *under-size Phase 2*. Mitigation: every zero-delta result
  records the precondition set it ran under, so it can be re-run once a related
  key is understood.
- **`make check-reference` fences three documents only.** Areas outside those
  documents have no outside-authority gate, so a decode there is verified by its
  own probe alone.
- **Phase 2 is not sized.** Render coverage for `SS_Shaded` (775 shapes),
  `SS_Soft` (258), `SS_Halo` (198), text-to-mesh and particles is deliberately
  out of scope here and will be scoped after Phase 1 closes.

---

## 9. Global constraints

- **English only** in every file, comment, docstring, commit message and printed
  string, per `.claude/ai/AGENTS.md`. The narrowing in `CLAUDE.md` covers only
  `docs/localization/**` and `tmp/**`.
- **No new required third-party dependency.** `mohoedit.py` and everything under
  `tools/` is standard library only; `pyclipper`, `jsonschema`, Pillow and
  `psd-tools` stay optional.
- **Every new file, class and function carries a docstring** explaining *why* a
  constant is what it is, matching `moho2svg.py`'s density.
- **Commit style:** plain imperative sentences, matching `git log`. Not
  Conventional Commits. No tool attribution, no AI co-author trailer.
- **Measurement provenance:** every recorded number states the corpus it ran
  against and the command that produced it.
