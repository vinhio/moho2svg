# Moho to Lottie — design

Design for `moho2lottie.py`, a second exporter that writes a Moho document to
a Lottie JSON animation, reusing the geometry pipeline that already powers
`moho2svg.py`.

**This design is now implemented.** All 8 tasks in
[`moho-to-lottie-plan.md`](moho-to-lottie-plan.md) are done, and
`moho2lottie.py` exports every one of this repository's 19 sample documents
successfully (verified: schema-valid, geometry-checked against the SVG
pipeline at multiple frames per document, byte-identical SVG output
unaffected). This document is kept as the ORIGINAL design record, not
updated line-by-line to match the final implementation in every
detail — where the two differ, the plan document's own per-task notes
explain what changed and why (several real bugs and a few wrong
measurements were found only once code existed to test against real
documents). Read the plan for current, verified facts; read this document
for the reasoning that shaped the design before any of it was built. Where
a statement below is a measurement, it says so and gives the sample size;
where it is a decision, it says what was decided and why; where it was
unverified at design time, it is listed in [§ 9](#9-open-questions) — most
of those are now settled, and the plan document says how.

Companion documents:

- [`moho-to-lottie-plan.md`](moho-to-lottie-plan.md) — the implementation
  plan, its own progress table, and what actually happened task by task
  (including corrections to this document's own design).
- [`lottie-and-thorvg.md`](lottie-and-thorvg.md) — the Lottie format itself,
  read out of the JSON Schema stored in `lottie/`.
- [`moho-export-pipeline.md`](moho-export-pipeline.md) — how `moho2svg.py`
  walks a document today.
- [`moho-project-file-format.md`](moho-project-file-format.md) — the Moho
  field reference.
- [`moho-rigging-and-deformation.md`](moho-rigging-and-deformation.md) —
  bones and skinning, which is the part Lottie cannot represent.

---

## 1. Goal and success criteria

Export a whole Moho document as **one animated Lottie file** that plays in
lottie-web.

Success means all of the following:

1. For every frame in the document's range, the Lottie file draws the same
   artwork that `python3 moho2svg.py --combined --frame N` draws today.
   "Same" is checked numerically, not by eye — see [§ 8](#8-verification).
2. The five tracked reference SVGs in `svg/` still regenerate byte-identical
   after the shared refactor in [§ 3](#3-changes-to-moho2svgpy).
3. The output validates against `lottie/lottie.schema.json`.
4. No new required third-party dependency.

Non-goals are listed in [§ 2.2](#22-out-of-scope-for-v1).

---

## 2. Scope

### 2.1 In scope for v1

| Feature | Why it is cheap or necessary |
|---|---|
| `MeshLayer`, `GroupLayer`, `BoneLayer` | The core of every document. |
| Fill, stroke, opacity | Direct Lottie equivalents (`fl`, `st`, `ks.o`). |
| Bone deformation, Smart Bones | Baked into vertex positions; see [§ 4](#4-the-flat-bake-decision). |
| Tapered strokes | `moho2svg.py` already converts these to a filled outline, so they arrive as ordinary geometry. |
| `PatchLayer` | Already resolved into a duplicate mesh at load time by `Document._resolve_patch_layers`. Nothing extra to do. |
| Gradients | `SS_Gradient2` appears 1,196 times across 17 of the 19 sample documents. Lottie has `gf` / `gs`. |
| Masking | 162 layers carry a non-zero `masking`, and 70 containers carry `group_mask == 2`. Dropping it would let hidden artwork show through, which is the most visible possible failure. |
| `SwitchLayer` | 17 layers. Cheap under the flat-bake model — see [§ 6.3](#63-switch-layers). |

### 2.2 Out of scope for v1

| Feature | Reason |
|---|---|
| Brush textures | Explicitly excluded. Lottie has no textured stroke; the only mapping is a raster image asset, which is the most expensive part of `moho2svg.py`. |
| `ImageLayer` | 15 layers in one document. `moho2svg.py` already drops them because it is a vector-only exporter. Adding them means a raster asset pipeline, the same work that brush textures were excluded for. |
| Boolean shape combination (`combo_mode`) | Only **16 shapes in all 19 documents** use a non-zero value (14 intersect, 2 union), all in `Bandit.mohoproj`. lottie-web's support for the `mm` merge element is poor. v1 draws these shapes with their plain outline and logs a warning naming each one. |
| Smart Warp | Not decoded anywhere in this repository, and no sample document uses it. |
| Cycle markers, `interp` easing | `moho2svg.py` itself ignores both (linear interpolation, no cycling). v1 inherits that behaviour rather than diverging from the renderer it is verified against. |

Every exclusion must produce a **counted warning on stderr**, not silence. A
silently dropped feature reads as "supported" to the next reader.

---

## 3. Changes to `moho2svg.py`

Two changes, both small, both verified by the reference SVGs staying
byte-identical.

### 3.1 A second path builder

`build_path_d()` turns traced geometry into an SVG `d` string. Add
`build_path_bezier()` beside it, taking the same arguments and returning a
Lottie bezier instead:

```python
{"v": [[x, y], ...], "i": [[dx, dy], ...], "o": [[dx, dy], ...], "c": bool}
```

Both call the same `PathTracer.trace(geometries, edges)`, so the two writers
cannot disagree about walk order or subpath boundaries.

Lottie's `i` and `o` are **relative to their own vertex**, so for a traced
segment the conversion is `o = c1 - p0` on the segment's start vertex and
`i = c2 - p1` on its end vertex. A vertex shared by two segments takes its
`o` from the outgoing segment and its `i` from the incoming one.

### 3.2 One shared tree walk

`Exporter.export_document` currently walks the layer tree and builds SVG
strings in the same loop. That walk holds real decisions — visibility,
`edit_only`, the active child of a switch layer, mask sources, when to
recurse — and a second exporter must make every one of them identically.

Extract the walk into a generator that yields what to draw, and let both
writers consume it:

```python
def walk_render_tree(exporter, frame, include_hidden=False) -> Iterator[RenderItem]
```

`RenderItem` describes one drawable: the layer, its ancestors, its
`geometries`, its `to_px` mapper, its `masking` value, its mask sources, and
its depth. `export_document` becomes a consumer that formats SVG; the Lottie
writer becomes a second consumer.

**The one delicate point.** The exact set and clear points of
`Exporter._active_actions` are load-bearing — see
[`moho-export-pipeline.md`](moho-export-pipeline.md) § 9.3, "the empty Smart
Bone context quirk". The generator must set and clear it at exactly the same
moments the current loop does. This is why the byte-identical check in
[§ 8.1](#81-the-svg-regression-gate) is a gate and not a nicety.

---

## 4. The flat-bake decision

Lottie has no skeleton. Every deformation Moho applies — bone skinning, Smart
Bone poses, ancestor transforms — must be resolved before the geometry is
written.

v1 resolves **all of it**: each shape's points are written in final canvas
pixels, exactly as `to_px` produces them for the SVG writer.

The consequences are all simplifications:

- Every Lottie layer has an **identity transform** (`ks` with default anchor,
  position `[0, 0]`, scale `[100, 100]`, rotation `0`).
- No `parent` links between layers, so no layer index bookkeeping.
- No matrix decomposition into Lottie's anchor / position / scale / rotation /
  skew form, which is the fiddliest part of any transform-preserving design.
- `to_px` already yields pixels with y pointing down and the origin at the top
  left, which is **exactly Lottie's coordinate system**. No conversion step,
  so no place for a sign error to hide.

The cost is file size, and it was measured rather than guessed. Sampling every
project in `moho/` at 8 frames with the real deform chain:

| Document | Frames | Shapes | Shapes that move | Estimated size |
|---|---|---|---|---|
| `WhatIsBone.animeproj` | 227 | 203 | 150 | ~21.6 MB |
| `SketchBone.animeproj` | 124 | 192 | 139 | ~7.5 MB |
| `Bandit.mohoproj` | 87 | 112 | 112 | ~1.8 MB |

Sizes are raw JSON at roughly 60 bytes per vertex, before gzip. Lottie is
normally served gzipped, which typically cuts JSON of this shape by three to
five times.

A shape whose points never move is written **once** as a static path
(`"a": 0`) instead of once per frame. That single rule is what keeps the
numbers above in single-digit or low-double-digit megabytes: baking every
shape at every frame regardless would total about 293 MB across the corpus.

A later optimisation can keep pure-transform layers as Lottie transform
keyframes and bake only skinned geometry, which measured roughly three to nine
times smaller across the corpus.
That is a change to the same writer, not a rewrite, and it is deliberately not
in v1.

---

## 5. Document and layer mapping

### 5.1 The root object

`project_data` carries everything the Lottie root needs:

| Lottie field | Source | Example (`Bandit.mohoproj`) |
|---|---|---|
| `fr` | `project_data.fps` | `24.0` |
| `ip` | `project_data.start_frame` | `25` |
| `op` | `project_data.end_frame + 1` | `128` |
| `w` / `h` | `project_data.width` / `.height` | `1920` / `1080` |
| `v` | a fixed schema version string | — |

Moho frame numbers are absolute and so are Lottie's, so a document that starts
at frame 25 writes its first keyframe at `t = 25`. Nothing is rebased, which
removes a whole class of off-by-one errors.

Whether `op` is exclusive is an inference, not a confirmed fact — see
[§ 9](#9-open-questions).

### 5.2 Layers

Each Moho mesh layer becomes one Lottie shape layer (`"ty": 4`) with an
identity `ks`, a sequential `ind`, and no `parent`.

**Draw order is reversed.** Moho draws its layer list back to front, the order
`Document.walk()` yields. Lottie draws the **first layer in the list on top**.
The emitted list is therefore the reverse of the walk order.

This is the single most likely silent bug in the whole design: the output
still looks like the right artwork, just with the wrong things in front. It
gets its own named step in the writer and its own check in
[§ 8.2](#82-the-geometry-equivalence-check).

### 5.3 Shapes

Each Moho shape becomes one group (`"ty": "gr"`) in the layer's `shapes` list,
holding, in order:

1. `"ty": "sh"` — the path, from `build_path_bezier()`.
2. A fill: `"ty": "fl"` for a solid colour, `"ty": "gf"` for a gradient.
3. A stroke: `"ty": "st"`, with `w` taken from the same
   `stroke_width_px` the SVG writer uses, and `lc` / `lj` from the resolved
   style.
4. `"ty": "tr"` — the group transform, identity.

A shape with no fill omits step 2; a shape with no outline omits step 3.

Static and animated paths differ only in the property envelope:

```json
"ks": {"a": 0, "k": {"v": [], "i": [], "o": [], "c": true}}
"ks": {"a": 1, "k": [{"t": 25, "s": [{"v": [], "i": [], "o": [], "c": true}]},
                      {"t": 26, "s": [{"v": [], "i": [], "o": [], "c": true}]}]}
```

Path keyframes can only be interpolated when every keyframe has the same
vertex count and subpath structure. **This was measured and holds**: across
2,659 shapes in 18 loadable documents, sampled at 12 frames each, **zero**
shapes changed structure. Two independent reasons support it:

- `combo_mode` never alters geometry. Boolean combination is implemented as
  SVG masks over untouched per-shape paths (`ShapeGroupRenderer._flush`), not
  as a geometric boolean, so no vertices are created or removed.
- `segments_on`, the only field that can split a path into more subpaths, is
  **never animated**: 53,027 instances across all 19 documents, none with more
  than one keyframe.

The writer must still assert this per shape and fail loudly if a document ever
breaks it, rather than emitting a file that a player will render as garbage.

---

## 6. The three feature areas

### 6.1 Masking

Moho expresses masking with two fields: a container's `group_mask`, and each
child's own `masking`. `moho2svg.py` resolves them in
`Exporter._mask_sources`, which returns the paths that make up the mask, and
treats `masking in (1, 2)` as exempt (drawn unclipped).

Lottie offers two mechanisms. v1 uses the simpler one:

**Chosen: per-layer `masksProperties`.** Every masked layer carries its own
copy of the mask, as a list of mask entries with `mode: "a"` (add, so several
sources union) or `mode: "s"` (subtract). Because the geometry is already
flat-baked into canvas pixels and every layer transform is identity, the mask
paths need no adjustment at all — they are the same coordinates the SVG
`<mask>` uses.

**Rejected: track mattes plus precompositions.** A Lottie track matte applies
to exactly one layer, so masking a group of siblings means moving them into a
precomposition asset and applying the matte to the precomp layer. That is more
structure, more index bookkeeping, and more that can go wrong, for no gain at
v1's scope. It stays documented here as the fallback if per-layer masks turn
out to render incorrectly.

The cost of the chosen option is duplication: N masked siblings carry N copies
of the mask geometry. Mask paths are typically small, and the size measurement
in [§ 4](#4-the-flat-bake-decision) is dominated by shape geometry, not masks.

**Inherited defect.** `moho2svg.py` has a known-wrong case for `masking == 2`
siblings, documented at length in `Exporter.export_document` and in the module
docstring's MASKING section: such a sibling's stroke should stay visible on top
of what it masks, and currently draws at its plain list position. v1
reproduces the current behaviour rather than diverging. Fixing it belongs in
the SVG writer first, where a reference export exists to check against.

### 6.2 Gradients

`SS_Gradient2` maps to Lottie's `gf` (gradient fill) and `gs` (gradient
stroke):

| Lottie | Moho |
|---|---|
| `t: 1` linear / `t: 2` radial | `fill_style.gradient_type` 0 / 1 |
| `g.p` | number of stops |
| `g.k` | stops flattened as `[offset, r, g, b, ...]` from `gradients[].location` and `.color` |
| `s` / `e` | start and end point, taken from the same geometry the SVG writer computes for `<linearGradient>` / `<radialGradient>` |

Gradient placement precision is an existing KNOWN GAP in `moho2svg.py`
(`effect_scale` / `effect_rotation`). v1 reuses whatever the SVG writer
computes, so both exporters are wrong in the same way rather than differently.
Improving placement is a separate task against SVG reference output.

### 6.3 Switch layers

A `SwitchLayer` shows exactly one child at a time, chosen by
`Layer.switch_active_child(frame, exporter)`. The channel holds strings, which
snap to the left keyframe with no interpolation, so the active child changes at
discrete frames and each child is active over one or more **contiguous frame
windows**.

Each window becomes one emitted layer with `ip` and `op` set to that window. A
child active in two separate windows is emitted twice. No opacity trickery, no
per-frame switching logic in the player.

---

## 7. Warnings and honesty at runtime

The writer keeps a counter per skipped feature and prints a summary to stderr
at the end of an export:

```
moho2lottie: N shapes with combo_mode != 0 drawn without boolean combination
moho2lottie: N ImageLayer layers skipped (vector-only exporter)
moho2lottie: N styles naming a brush drawn as plain strokes
```

Each `N` is counted in the document being exported. The corpus-wide figures
quoted elsewhere in this document are not what a single export reports.

---

## 8. Verification

There is no test suite in this repository, and no Lottie player is installed.
The plan therefore leans on checks that need neither.

### 8.1 The SVG regression gate

After the `walk_render_tree` extraction in [§ 3.2](#32-one-shared-tree-walk),
`make gen` must regenerate all five tracked SVGs **byte-identical**. This is a
strong gate: it exercises the full walk, including the Smart Bone context
ordering, across five real documents.

### 8.2 The geometry equivalence check

The primary correctness check needs no player and no dependency.

For a document and a frame, the exporter can produce both outputs from the
same traced geometry. A checker then:

1. reads every path keyframe at frame N out of the emitted Lottie file;
2. converts each back to absolute control points (`c1 = v + o`, `c2 = v_next +
   i_next`);
3. renders the same document at frame N through `build_path_d()`;
4. compares the two coordinate sequences within a small tolerance.

Any disagreement is a real bug in the writer, found without rendering
anything. This also catches the reversed-draw-order mistake from
[§ 5.2](#52-layers), because the check walks shapes in emitted order.

### 8.3 Schema validation

Validate the output against `lottie/lottie.schema.json`. This needs the
`jsonschema` package, which is **optional** in the same way Pillow already is:
if it imports, validate; if not, print a note and skip. No required dependency
is added.

Note the caveat from [`lottie-and-thorvg.md`](lottie-and-thorvg.md) § 2.5:
passing the schema is not proof of a correct file, because the schema marks
very little as required.

### 8.4 Visual confirmation

The one thing the checks above cannot do is prove that lottie-web *renders*
the file as intended — particularly the shape-element ordering rule, which
[`lottie-and-thorvg.md`](lottie-and-thorvg.md) § 6.4 notes is not expressible
in the schema at all.

A small preview page loading a locally vendored `lottie-web` build, showing
the animation beside `moho2svg.py`'s SVG at the same frame, closes that gap.
The vendored player is gitignored, like `styles/Brushes/`.

### 8.5 Make targets

- `make gen-lottie` — export all tracked projects to `lottie-out/`
  (gitignored at first; promoted to tracked reference output once the geometry
  check passes consistently).
- `make check-lottie` — run the geometry equivalence check of
  [§ 8.2](#82-the-geometry-equivalence-check) over a sample of frames.

---

## 9. Open questions

Ordered by how much they could change the work. Status added post-
implementation; see `moho-to-lottie-plan.md` for the task that settled each
one, where one exists.

1. **Is Lottie's `op` exclusive?** [§ 5.1](#51-the-root-object) assumes
   `end_frame + 1`. If it is inclusive, every export is one frame long. Cheap
   to settle against a player, and cheap to fix. **Still open** — no Lottie
   player has been used anywhere in this project; `moho2lottie.py`'s own
   `end_frame + 1` choice is unverified. Listed as open in the plan's own
   "After the plan" section too.
2. **Shape element ordering inside a group.** "A style applies to neighbouring
   shapes" is not a machine-checkable rule and is not in the schema. The order
   in [§ 5.3](#53-shapes) is the conventional one, unverified here.
   **Sidestepped, not settled**: Task 3 gives each shape up to two SEPARATE
   Lottie groups (one for fill, one for outline) instead of one group mixing
   both paint operators, specifically so this ambiguity cannot affect the
   result either way. Still open for anyone building a writer that needs
   fewer, more complex groups.
3. **Do per-layer `masksProperties` reproduce Moho's masking?** The fallback
   (track matte plus precomposition) is designed but not detailed.
   **Implemented per-layer, geometry-checked, visual correctness still
   open**: Task 6 built it (with mask geometry keyframed per frame, a real
   gap this design did not anticipate - masks move as much as any other
   shape) and confirmed the emitted geometry matches the pipeline directly;
   whether it clips correctly in an actual Lottie player is unverified,
   same root cause as item 1. One deliberate, counted simplification: the
   SVG side's stroke-exclusion carve-out (a mask source's own outline stays
   visible on top of what it clips) is not reproduced - Lottie's mask model
   has no "stroke as mask" primitive, and it is a narrow effect (16 of 180
   mask source shapes, 9%, measured directly).
4. **Is `Bandit.mohoproj`'s `masking == 2` defect worse in Lottie than in
   SVG?** The SVG writer's known-wrong ordering is inherited deliberately; how
   visible it is in a Lottie player is unknown. **Still open** — same root
   cause as item 1.
5. **Gzipped size of the largest output.** `WhatIsBone.animeproj` at ~21.6 MB
   raw is the worst case measured. If gzip does not bring it into an
   acceptable range for web delivery, the transform-preserving optimisation
   from [§ 4](#4-the-flat-bake-decision) moves from "later" to "required".
   **Settled: gzip is enough, no further work needed.** The finished
   exporter's actual output for `WhatIsBone.animeproj` is 23.9 MB raw (higher
   than this estimate, since it includes working masking and gradients this
   estimate did not model) but only **2.4 MB gzipped** (~10x) — comfortably
   web-deliverable. The transform-preserving optimisation remains a possible
   LATER improvement, not a required one.
6. **A Vietnamese mirror of this document** under `docs/localization/` is not
   written yet. It is deliberately deferred: this is a design that will change
   during implementation, and translating a moving target twice is waste.
   **Still deferred.** The design is no longer a moving target now that
   implementation is done, so this could be picked up, but doing so was out
   of scope for the implementation work itself and was not requested.

---

## 10. What was measured for this document

Every figure quoted above comes from a script run against the files in
`moho/`, not from an estimate. The four probes were:

| Measurement | Result | Sample |
|---|---|---|
| Path vertex-count stability across frames | 0 unstable | 2,659 shapes, 18 documents, 12 frames each |
| `segments_on` ever animated | never | 53,027 instances, 19 documents |
| Shapes that move, with the real deform chain | 0% to 100% per document | 19 documents, 8 frames each |
| `combo_mode`, `masking`, `group_mask`, gradient and layer-type counts | see [§ 2](#2-scope) | 19 documents |

One document, `Rabbit.animeproj`, could not be loaded at all while these were
run; that has since been fixed, and it was excluded from the stability figure
above rather than silently counted as passing.
