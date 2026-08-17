# Lottie to Moho — design

> For agentic workers: this design precedes an implementation plan (the same
> order `moho-to-lottie-design.md` → `moho-to-lottie-plan.md` used). Read
> [`moho-to-lottie-design.md`](moho-to-lottie-design.md) first — this document
> is the *inverse* mapping and deliberately reuses its vocabulary.

**Goal:** add `lottie2moho.py`, a stdlib-only CLI that reads one animated
Lottie JSON file and writes one `.mohoproj` file Moho 14 can open, with the
artwork and the animation reconstructed as faithfully as the two formats
allow.

**The one sentence that defines this tool:** Moho→Lottie *bakes* a rig into
per-frame vertex positions; Lottie→Moho cannot *unbake* it, so what comes out
is a **flat, unrigged, densely-keyframed** Moho document — valid, openable,
playing correctly — but with every frame of motion stored as point-animation
and layer-transform channels instead of bones.

---

## 1. Goal and success criteria

Read a Lottie file and produce a Moho document. Success means all of the
following:

1. For a Lottie file produced by this repository's own `moho2lottie.py`, the
   reconstructed Moho document re-exports (via `moho2svg.py --combined`) to
   the **same artwork** the original Moho document exports — checked
   numerically, with a tolerance, not by eye — see [§ 11](#11-verification).
   This roundtrip is the tool's own ground truth, exactly the way
   `tools/check_lottie_geometry.py` is for the forward exporter.
2. The output is a structurally valid `.mohoproj` (version `1045`, the newer
   of the two formats this repository has reverse-engineered) that Moho
   itself opens without complaint — confirmed manually by the author, since
   this repository has never driven Moho's own UI.
3. Every existing export stays byte-identical — adding a new file changes
   nothing in `moho2svg.py` or `moho2lottie.py`.
4. No new required third-party dependency. `jsonschema` stays optional, for
   an optional `--validate` flag.

Non-goals: rig recovery, text layers, expressions, 3D, mattes — each listed
in [§ 2.2](#22-out-of-scope-for-v1).

---

## 2. Scope

### 2.1 In scope for v1

| Feature | Why it is cheap or necessary |
|---|---|
| `ty: 4` shape layers | The core of every Lottie file: paths, fills, strokes, gradients. |
| `ty: 3` null layers | A Moho `GroupLayer` carrying transform channels. |
| `ty: 1` solid layers | One filled rectangle shape on a `MeshLayer`. |
| `ty: 2` image layers | The embedded PNG/JPEG is written beside the `.mohoproj` and referenced by an `ImageLayer` (the forward pipeline already reads exactly this shape of data — `moho2svg.py`'s IMAGE LAYERS section). |
| `ty: 0` precomp layers | Inlined: the referenced asset's layers become children of a `GroupLayer` (no nested files). |
| Layer transforms (`ks.p/a/s/r/o`) | Direct channel equivalents — see [§ 4.3](#43-layer-transforms). |
| Per-frame path keyframes | The heart of the animation mapping — see [§ 6](#6-animation-channels). |
| `fl`, `st`, `gf`, `gs` | Direct equivalents; `gf`/`gs` reverse the same `SS_Gradient2` ↔ Lottie table the forward exporter uses. |
| Lottie masks (`masksProperties`) | Heuristic mapping to Moho's `group_mask` + `masking` container system — see [§ 8](#8-masks-and-combo-mode-heuristics). |
| Layer blend modes (`bm`) | The inverse of `BLEND_MODE_LOTTIE` in `moho2lottie.py`. |
| `rc`, `el`, `sr` primitives | Converted to ordinary closed curves (Moho has no primitive shapes — everything is curves). |

### 2.2 Out of scope for v1

| Feature | Reason |
|---|---|
| Rig recovery (bones, Smart Bones, IK, springs, binding) | **Impossible from Lottie**, not merely hard — Lottie stores only baked vertex positions. See [§ 3](#3-the-unrigged-import-decision). |
| `ty: 5` text layers | Lottie text layout and Moho's `TextLayer` share nothing but the name. Counted warning, layer dropped. |
| Expressions | No equivalent anywhere in the Moho format. Counted warning. |
| 3D layer flags (`dd`, `rz`, split-rotation) | Moho's canvas is 2D; `rz` has no target. Counted warning. |
| Mattes (`tt`) | Approximating a matte as masking is possible but visibly different in edge cases; v1 warns and drops the matte relationship rather than lying. |
| `tm` (trim paths), `rp` (repeaters), `rd` on arbitrary paths | No Moho equivalent; counted warning, drawn untrimmed/unrepeated. `rd` on `rc` is applied by the primitive conversion itself. |
| Lottie easing curves (`ks.k[].i/o`) | Kept approximately: linear keyframes map exactly to Moho's `INTERP_LINEAR`, everything else maps to Moho's Smooth (`im == 1`) with a counted warning — see [§ 6.2](#62-keyframe-and-easing-mapping). |

Every exclusion must produce a **counted warning on stderr**, never silence —
the same rule `moho2lottie.py` was built under.

---

## 3. The unrigged-import decision

`moho2lottie.py`'s flat-bake (§ 4 of its design) exists because Lottie cannot
store a rig: every deformation is baked into canvas-pixel vertex positions,
every Lottie layer keeps an identity transform. The inverse direction faces
the mirror image of that decision:

- **Given only per-frame vertex positions, recovering the bones that moved
  them is an inverse-skinning problem** — underdetermined (infinitely many
  skeletons produce the same vertex motion). No heuristic would earn the
  "confirmed against Moho" standard this repository requires.
- **So the tool does not try.** The output document has no `BoneLayer` at
  all. Every animated vertex becomes a `MeshPoint` whose `position` is a
  channel with a keyframe at every sampled frame; every animated layer
  property becomes that layer's own transform channel. Moho opens this,
  plays it, and re-exports it identically — it just looks like artwork
  imported from another vector editor, not like a rig built in Moho.

Two consequences worth writing down now, because they decide the rest of the
design:

1. **Point-animation channels, not point binding.** Moho mesh points can be
   animated directly (`mesh.points[].position` is a channel — the forward
   pipeline already reads it per frame). Nothing else in the Moho format
   needs to change.
2. **Every Lottie shape keeps its own private points.** Lottie never shares
   vertices between shapes (the forward exporter emits each shape's
   `v`/`i`/`o` independently). Moho *allows* shared mesh points but does not
   require them; the reconstruction simply gives each shape its own
   `curves`/`points`, one `MeshLayer` per Lottie layer. Slightly bigger
   files, zero semantic risk.

---

## 4. Document and layer mapping

### 4.1 The root object

```json
{
  "mime_type": "application/x-vnd.lm_mohodoc",
  "version": 1045,
  "major_version": 1,
  "rev_version": 0,
  "project_data": {"width": …, "height": …, "start_frame": …, "end_frame": …, "fps": …},
  "styles": [],
  "layers": [ …one GroupLayer root… ],
  "animated_values": {}
}
```

- `width`/`height` come from the Lottie root's `w`/`h` (pixels = canvas
  units; Moho's coordinate system is 2 units per canvas height, y flipped —
  the conversion constants already live in `moho2svg.py`'s COORDINATES
  section and are reused, inverted, here).
- `start_frame`/`end_frame`/`fps` come from the Lottie root's `ip`/`op`/`fr`.
- All Lottie layers live under one root `GroupLayer` (Moho does not require
  a BoneLayer root for a rig-less document).

### 4.2 Layer kinds by `ty`

| Lottie `ty` | Moho layer |
|---|---|
| `4` shape | `MeshLayer` with one `mesh` built from the layer's `shapes` (see § 5). |
| `3` null | `GroupLayer` carrying the layer's transform channels (a null's only job is to move its children). |
| `1` solid | `MeshLayer` with one filled rectangle shape (`sc` colour, `sw`/`sh` size). |
| `2` image | `ImageLayer` — see § 9. |
| `0` precomp | `GroupLayer` whose children are the referenced asset's layers, inlined. The precomp's own transform channels stay on this group. |
| `5` text | dropped, counted warning `text_layer`. |

Lottie nesting (via `ty: 0` or `parent` indices) becomes Moho tree nesting.
`parent` is otherwise **flattened**: the child's own channels are composed
with the parent's transform per frame and stored as the child's absolute
channels — the same flat-bake spirit as the forward writer, applied to
transforms instead of vertices. No dependency is lost, and Moho's own tree
has no "child of an unrelated layer" primitive to preserve it any other way.

### 4.3 Layer transforms

Moho's per-layer channels (`translation`, `scale`, `rotation_z`, plus
`layer_effects.alpha`) map onto Lottie's `ks`:

| Lottie | Moho channel | Note |
|---|---|---|
| `ks.p` (position) | `translation` (Vec2) | Split position (`"s": true` → separate `x`/`y` keyframes) maps onto the same `{x, y}` channel shape — Moho keyframes a whole Vec2 at once, so x- and y-keyframes are resampled onto one merged frame list. |
| `ks.a` (anchor) | `origin` | Moho's origin is the same concept (the point transforms rotate/scale around); the forward pipeline already maps Moho origin → Lottie anchor, so this is the inverse of a documented mapping. |
| `ks.s` (scale) | `scale` (Vec2) | Lottie scale is percent (100 = 1.0); divide by 100. |
| `ks.r` (rotation) | `rotation_z` (Val) | Same degrees, same clockwise convention — the forward writer copies `rotation_z` into `r` directly, so this inverts exactly. |
| `ks.o` (opacity) | `layer_effects.alpha` (Val) | Same 0..1 convention the forward writer already reads (`Layer.alpha_at`); Lottie percent divided by 100. |

### 4.4 Ordering — both levels, again

Lottie paints the **earlier** entry of a list on top; Moho paints the **later**
entry on top. The forward design's § 2.3 is applied in reverse:

1. **Layers** — the Lottie `layers` list is reversed into Moho's `layers`
   tree order (Moho back-to-front).
2. **Shapes within a layer** — the Lottie shape blocks of one `ty: 4` layer
   are reversed into `mesh.shapes` file order, for the same reason.

Getting either wrong is invisible to a self-consistency check — the forward
writer burned exactly this lesson; the roundtrip check (§ 11.2) must compare
*draw order*, not just presence.

---

## 5. Geometry conversion

### 5.1 Bezier loops become curves and points

One Lottie `sh` item is one or more closed loops: `{"v": [...], "i": [...],
"o": [...], "c": bool}`. Each loop becomes one Moho `Curve` (`closed: true`)
with one `MeshPoint` per vertex. The forward pipeline's `build_path_bezier`
already turns Moho curves into exactly this structure, so the inverse is a
straight inversion of documented data:

- vertex `k` → `MeshPoint` at position `(v[k].x, v[k].y)`;
- incoming handle `i[k]` (relative to `v[k]`, pointing toward `v[k-1]`) and
  outgoing handle `o[k]` (toward `v[k+1]`) → the point's
  `smoothness`/`weight_in`/`weight_out`/`offset_in`/`offset_out` via the fit
  in § 5.2;
- a shape with **no fill and no stroke but nonzero width** (a
  stroke-only outline) still becomes a curve — Moho strokes live on shapes,
  not on free-floating paths, same as the forward writer assumes.

An open path (`"c": false`) is closed by joining its ends — Moho curves are
the only primitive Moho has, and the forward writer never emits open shapes
except as stroke paths, so this is rare.

### 5.2 The smoothness/weight/offset fit

`moho2svg.py`'s `BezierReconstructor` turns Moho's
smoothness/weight/offset into cubic handles with an **empirically-fit
chord-length-weighted blend** — the module docstring says plainly it is not
algebraically invertible. The reverse direction therefore is a *fit*, not a
formula:

- For each point, solve for the Moho parameters that minimize the distance
  between the reconstructed handles and the Lottie handles (two unknowns per
  handle direction; the forward model is cheap enough to evaluate directly).
- Because the roundtrip is the acceptance test (§ 11.2), the fit only has to
  be good enough that `moho2svg.py` re-renders the same beziers within the
  check's tolerance — the same "fit against the model it will be read by"
  trick the forward writer used.

The fit's own quality is a measured number in § 12 (open until implemented).

### 5.3 Vertex-count changes and topology split

A Lottie animated path can change its **vertex count** between keyframes
(and, via masks, its subpath count) — Lottie's schema allows it. A Moho mesh
has a fixed point list, so one Moho shape cannot hold such a path. The
forward pipeline already met the mirror of this problem (a pre-clipped
combo_mode==3 shape whose topology changed mid-animation — see
`moho2lottie.py`'s `combo_mode3_clip_unstable`).

v1 resolves it the same way, structurally: the path is **split into phases**,
one Moho shape per distinct vertex/subpath count, each keyframed only over
its own contiguous frame window, all children of one `SwitchLayer` whose
`switch_keys` selects the right phase per frame. A Lottie path that never
changes count (the overwhelmingly common case) produces one shape and no
switch.

### 5.4 Fixed primitives

`rc`/`el`/`sr` have no Moho equivalent — they are converted to closed curves
at build time (rectangle → 4 points; ellipse → 4 points with the standard
0.5522847 circle factor; star/polygon → `N` points from `pt`/`sy`/`ir`/`or`).
`rd` (rounded corners) is applied during this conversion for `rc` and `el`;
on arbitrary paths it is out of scope (§ 2.2).

### 5.5 Fill rule

Both sides are even-odd: the forward writer hardcodes `"r": 2` for Moho's
own always-evenodd fills, and `moho2svg.py` writes `fill-rule="evenodd"` on
every fill. The reconstruction emits shapes whose holes come from
counter-wound loops and relies on Moho's own evenodd fill — no field to set,
but the subpath winding must be *preserved*, not normalized, or holes plug
solid (the forward design's § 2.3 records the same failure in reverse).

---

## 6. Animation channels

### 6.1 Channel shape

Moho animates via `{"when": [...], "val": [...], "interp": [...]}` (or a
bare scalar). One Lottie animated property becomes one such channel; a static
property stays a bare scalar. `when` holds integer frames — Lottie keyframe
times are rounded to the nearest frame, and keyframes closer than one frame
are collapsed onto one (kept: the later).

### 6.2 Keyframe and easing mapping

| Lottie | Moho `interp` | Fidelity |
|---|---|---|
| linear easing (equal `i`/`o`) | `INTERP_LINEAR` (`im == 0`) | exact |
| hold (`"h": 1`) | Step | exact |
| any other easing | Smooth (`im == 1`, Moho's default) | **approximate** — counted warning `easing_approximated`; keyframe values are exact, the path between them follows Moho's own measured Smooth curve instead of Lottie's bezier easing |

Cycle markers never appear: Lottie has no cycle concept; a looped animation
arrives as ordinary keyframes.

### 6.3 Point animation

Every animated vertex position becomes `mesh.points[k].position` as a
channel keyed at every sampled frame within its window — this is what
"densely-keyframed" means. The frame list is the union of all keyframe times
of that shape's path property; between them the channel interpolates with
the mode of the *path*'s own keyframes (§ 6.2). This is exactly how the
forward writer's per-frame vertex baking is undone: no information is added,
none lost.

### 6.4 What "the same artwork" means for animation

The roundtrip is not expected to be bit-identical *between* keyframes:
Lottie eased keyframes become Moho Smooth interpolation. The acceptance
check therefore compares at the **keyframe frames** exactly, and between
them within a tolerance — the same two-tier comparison
`tools/check_reference_frames.py` already uses for per-group centroid
travel.

---

## 7. Styles, gradients and blend modes

- **Fills and strokes.** `fl` → shape `has_fill: true` + `style.fill_color`;
  `st` → `has_outline: true` + `style.line_color`/`line_width` (Lottie
  stroke width is canvas units; Moho's `line_width` is the same two-units-
  per-canvas-height convention the forward writer already converts).
  Line caps/joins (`lc`/`lj`) reverse the forward tables.
- **Gradients.** `gf`/`gs` → `style.fill_style`/`line_style` of type
  `SS_Gradient2`, using the inverse of the forward writer's own table:
  Lottie `t: 1` (linear) → `gradient_type: 0`, `t: 2` (radial) →
  `gradient_type: 1`; stops, `s`/`e` and `highlight` map onto the same
  fields `moho2lottie.py` reads from Moho.
- **Styles are inline.** Lottie has no named-style inheritance; every shape
  carries its own full style dict (Moho supports exactly this — the format
  doc says newer documents put real values directly on the shape). The
  document's `styles` table stays empty.
- **Blend modes.** `bm` reverses `BLEND_MODE_LOTTIE`; unknown values are
  dropped with a counted warning (composited Normal), mirroring the forward
  writer.

---

## 8. Masks and combo-mode heuristics

Lottie expresses "see only part of this layer" as `masksProperties`; Moho
expresses it as a mask-source layer plus a container (`group_mask`) plus
per-child `masking`. The mapping is structural, not algebraic — and the
forward direction proves both systems can carry the same artwork:

- A layer's **first** mask (mode `a`) becomes a sibling `MeshLayer` holding
  the mask's own shapes, inside a new `GroupLayer` marked `group_mask: 2`,
  with the masked layer set `masking: 2` and any additional siblings
  `masking: 1` (exempt) — the same arrangement `moho2lottie.py` reads back.
- Further sequential masks (`s`, `i`, `a` chains) have no exact Moho
  equivalent. v1 folds what it can (a leading `a`-mask and a trailing
  `s`-mask chain map onto `masking` values and, where the layer is a single
  shape, onto `combo_mode` 2/3) and counts a warning `mask_chain_approximated`
  for the rest, drawing the layer unmasked rather than pretending.
- Mask opacity/expansion (`o`, `x`) are dropped with the same warning; Moho's
  own masking carries neither field.

The result is honest: simple masks import faithfully, complex chains warn.

---

## 9. Images and precomps

- **`ty: 2` image.** The `refId` asset's embedded data (`p` = base64 PNG/JPEG
  with a `u` directory prefix) is written as `<output>.assets/<name>.png`
  beside the `.mohoproj`; the `ImageLayer`'s `image_path` references it.
  The image's own size comes from the asset `w`/`h` — the forward pipeline's
  IMAGE LAYERS section confirms this is the same shape of data it reads back
  through `--image-dir`.
- **`ty: 0` precomp.** The referenced asset's layers are copied inline as the
  group's children, with their own `ip`/`op` windows mapped onto Moho's
  frame range (content outside the parent's window is clamped, matching how
  `moho2lottie.py` handles SwitchLayer windows in reverse). Nested precomps
  recurse.

---

## 10. Warnings and honesty at runtime

One counted stderr warning per dropped/approximated feature, one line each,
printed at the end of a run — the exact convention `moho2lottie.py` already
uses (`WARNING_EXPLANATIONS`). v1 warnings:

`text_layer`, `expression`, `layer_3d`, `matte`, `trim_path`, `repeater`,
`easing_approximated`, `mask_chain_approximated`, `blend_mode_unknown`,
`vertex_count_changed` (the SwitchLayer split case — counted so a user can
see how much of their file needed it).

---

## 11. Verification

### 11.1 The byte-identity gate

`moho2svg.py` and `moho2lottie.py` are not modified at all — this gate is
`make check-reference` + `make check-lottie` still passing, unchanged.

### 11.2 The roundtrip geometry check — the real gate

New `tools/check_lottie_roundtrip.py`, stdlib-only:

1. `moho2lottie.py M.mohoproj → L.json` (existing writer),
2. `lottie2moho.py L.json → M2.mohoproj` (the new writer),
3. `moho2lottie.py M2.mohoproj → L2.json` (existing writer again),
4. compare `L` vs `L2` numerically: per-layer shape presence in the right
   draw order, per-shape centroid and winding at the keyframe frames
   exactly and between them within a tolerance — the same two measurements
   `tools/check_reference_frames.py` trusts.

Run over the corpus in `make check-roundtrip`. A failure is a regression in
exactly one of the two writers; the diff says which side to look at.

### 11.3 Schema validation (optional)

`--validate` checks the emitted `.mohoproj` against this repository's own
fragment schemas under `schema/` (`project.schema.json`,
`layer.schema.json`, `mesh`/`shape`/`style` fragments) with the optional
`jsonschema` package — the same pattern as `moho2lottie.py --validate`.
The schemas were written from real files, so they are a structural (not
semantic) net.

### 11.4 Opening in Moho

The one check no script here can run: the author opens the emitted file in
Moho 14 and confirms it loads, plays, and re-exports — the same human step
every exporter in this repository has ultimately been validated by.

### 11.5 Make targets

```bash
make out/moho/%.mohoproj        # L.json -> out/moho/<name>.mohoproj
make check-roundtrip            # the § 11.2 pipeline over the sample docs
```

---

## 12. Open questions

1. **Smoothness fit quality.** How close the § 5.2 fit gets to Moho's own
   handles is unknown until implemented — the roundtrip check measures it,
   and if the tolerance is unachievable, the fallback is dense point
   animation on *handle* geometry (uglier files, same artwork).
2. **Group opacity.** The forward writer found that a Moho group's own
   alpha does something it could not decode (`Layer.alpha_at`'s docstring).
   A Lottie layer with animated `ks.o` under a group therefore maps opacity
   onto the layer itself; whether Moho's group-level alpha should ever be
   written instead is deliberately left alone until the forward side decodes
   it.
3. **Mask chain folding.** How much of § 8's `s`/`i` chain actually folds
   onto `combo_mode` versus warns depends on real Lottie files in the wild —
   the corpus for the *forward* writer says nothing about what AE exports
   look like. The first real-world Lottie file decides how aggressive the
   folding should be.
4. **Fractional-frame rounding.** Lottie keyframes can sit on half frames;
   rounding to Moho's integer frame grid can move two keyframes onto the
   same frame. The collapse rule (keep the later) is a guess until a real
   file exercises it.
