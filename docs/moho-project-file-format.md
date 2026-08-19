# Moho Project File Format

A Moho project file (`.mohoproj` for Moho Pro, `.animeproj` for Moho Debut)
is plain JSON, despite the extension. The format is **not officially
documented** by Smith Micro / Lost Marble; everything below was
reverse-engineered by `moho2svg.py`'s author, by empirically comparing this
tool's output against SVG files Moho itself exported ("File > Export
Animation"), across several rigs and two Moho versions (14.3 and 14.4).

This document is a readable summary of that reverse-engineering. **The
authoritative source for the rendering formulas is the module docstring at the
top of `moho2svg.py`**, which additionally records, for each formula and
constant, *how* it was derived and *what evidence* supports it (sample sizes,
error margins, which parts are confirmed-exact versus best-fit heuristics).
Read that docstring before changing any of the logic this document describes —
several things that look like bugs are intentionally preserved because they
match real Moho output.

This document describes **what is in the file**. For **how these fields are
consumed at export time** — the processing order, the relationships between
layers, transforms, bones, masking and styles, and which stage reads which
field — see `docs/moho-export-pipeline.md`.

---

## 1. Scope and evidence base

Every field list, value set, and count in this document was measured by
walking the project files in the (gitignored) `moho/` folder. That sample is
small, so treat "the only values observed" as *evidence*, not as *the complete
set the format allows*.

The sample was broadened partway through this document's life from an
original 5 files to **19**, adding Moho's own bundled bone-tool tutorial
documents (`AnglePositionScale`, `BoneDynamics`, `BoneParenting`,
`BoneStrengthTool`, `ControlBones`, `IK-FK`, `IndependentAngle`,
`MaximumIKStrethching`, `OffsetBoneTool`, `Rabbit`,
`SelectandReparentBoneTool`, `TargetBone`, `TransformBoneTool`, plus
`SlickObjectTransition`). Findings that only the broader 19-file pass
surfaced are marked **(19-file finding)** below so it stays clear which
claims rest on the original 5-file evidence and which needed the larger
sample. A machine-checkable counterpart to this document — a JSON Schema
validated against all 19 files, with its own gap-coverage audit — lives in
`schema/`; see `schema/README.md`.

| Document | `version` | Canvas | Frames | Layers | Named styles |
|---|---|---|---|---|---|
| `AddBone.animeproj` | 1038 | 1280×720 | 1–25 | 229 | 201 |
| `ReparentBone.animeproj` | 1038 | 1280×720 | 1–120 | 42 | 201 |
| `SketchBone.animeproj` | 1038 | 1280×720 | 1–120 | 108 | 239 |
| `WhatIsBone.animeproj` | 1038 | 1280×720 | 1–240 | 140 | 118 |
| `Bandit.mohoproj` | 1045 | 1920×1080 | 25–127 | 25 | 12 |
| `AnglePositionScale.animeproj` | 1038 | 1280×720 | 1–120 | 10 | 273 |
| `BoneDynamics.animeproj` | 1038 | 1280×720 | 1–29 | 14 | 273 |
| `BoneParenting.animeproj` | 1038 | 1280×720 | 1–120 | 10 | 273 |
| `BoneStrengthTool.animeproj` | 1038 | 1280×720 | 1–25 | 22 | 201 |
| `ControlBones.animeproj` | 1038 | 1280×720 | 1–120 | 25 | 240 |
| `IK-FK.animeproj` | 1038 | 1280×720 | 1–120 | 10 | 273 |
| `IndependentAngle.animeproj` | 1038 | 1280×720 | 1–120 | 45 | 273 |
| `MaximumIKStrethching.animeproj` | 1038 | 1280×720 | 1–120 | 45 | 273 |
| `OffsetBoneTool.animeproj` | 1038 | 1280×720 | 1–120 | 25 | 201 |
| `Rabbit.animeproj` | **1021** | 1920×1080 | 1–29 | 17 | 0 |
| `SelectandReparentBoneTool.animeproj` | 1038 | 1280×720 | 1–120 | 42 | 201 |
| `SlickObjectTransition.mohoproj` | 1038 | 1280×720 | 1–96 | 7 | 0 |
| `TargetBone.animeproj` | 1038 | 1280×720 | 1–120 | 45 | 273 |
| `TransformBoneTool.animeproj` | 1038 | 1280×720 | 1–120 | 15 | 239 |

(Layer counts include the `MeshLayer` nested inside each `TextLayer`. `fps` is
`24.0` in every sample, so it is dropped from this table.)

Totals across the 19 documents: 876 layers (of which 648 are `MeshLayer`, 103
`GroupLayer`, 47 `BoneLayer`, 34 `TextLayer`, 17 `SwitchLayer`, 15
`ImageLayer` **(19-file finding — [§ 6.1](#61-layer-types))**, 12
`PatchLayer`), 3,764 named styles, 2,660 shapes, 3,045 curves, 52,748 mesh
points, 53,027 curve points, 850 bones, and 584,616 animation channels
(423,642 `Val`, 72,646 `Color`, 68,903 `Vec2`, 14,896 `Bool`, 2,812 `Vec3`,
1,717 `String`). A document can also carry **zero** named styles at all
(`Rabbit`, `SlickObjectTransition` **(19-file finding)**).

Three `version` values are now sampled, and they behave differently in
several places (styles, per-point fields, `combo_mode`). Throughout this
document, **"oldest"** means `Rabbit.animeproj`'s `1021` **(19-file
finding)**, **"older"** means the `1038` documents (17 of the 19), and
**"newer"** means the single `1045` document (`Bandit.mohoproj`) — still one
file, so a conclusion drawn from it alone rests on that one file.

---

## 2. Top-level structure

```jsonc
{
  "version": 1045,
  "project_data":    { "width": 1920, "height": 1080, ... },
  "styles":          [ { "type": "Style", "name": "...", "uuid": "...", ... } ],
  "layers":          [ { "type": "BoneLayer", "name": "...", "layers": [...] } ],
  "animated_values": { "camera_zoom": { ...channel... }, ... },
  "layercomps":      [],
  "action_refs":     []
}
```

Every top-level key observed, and whether `moho2svg.py` reads it:

| Key | Type | Meaning | Used? |
|---|---|---|---|
| `layers` | list | The document's layer tree ([§ 6](#6-layers)). 1–4 root layers observed. | **yes** |
| `styles` | list | Document-wide named style list ([§ 8](#8-styles)). | **yes** |
| `project_data` | obj | Canvas and render settings ([§ 3](#3-project_data)). | partly — `width`/`height` only |
| `version` | int | Format revision: `1021` (oldest sampled), `1038` (majority), or `1045` (newest sampled) **(1021 is a 19-file finding)**. | **yes** — read, but no branch depends on it |
| `animated_values` | obj | Document-level channels: camera + timeline markers ([§ 5.5](#55-document-level-animated_values)). | no |
| `layercomps` | list | Layer comps (saved show/hide sets). **Empty in all 19 documents**, so its element shape is unknown. | no |
| `action_refs` | list | **Empty in every document that has the key at all**, so its element shape is unknown. Presumably references to actions in external/linked documents; see [§ 11.4](#114-action_refs-and-layercomps). Absent entirely in the `1021` document — see the row below. | no |
| `major_version` / `rev_version` | int | Always `1` / `0`. | no |
| `mime_type` | str | Always `"application/x-vnd.lm_mohodoc"`. | no |
| `doc_uuid` | str | Document identity. | no |
| `created_date` / `modified_date` | str | Human-readable timestamps, e.g. `"Wed Aug 31 16:17:24 2016"`. | no |
| `comment` | str | Only in newer-generation files: `"Created in Moho version 14.3, ..."`. | no |
| `thumbnail` | str | Only in newer-generation files: base64 JPEG preview. | no |
| `documentviewstate` | obj | Exactly 48 `DocState_*` editor keys in every one of the 19 documents (zoom, grid, playback range, viewport split, per-quadrant outside-view camera) **(the full 48-key enumeration is a 19-file finding — see `schema/project.schema.json`'s `DocumentViewState`)**. Pure UI state, no effect on exported geometry. | no |
| `metadata` | obj | Small key/value bag: `what` (`0`), `save_time` (`1` — not a timestamp despite the name), `layerwnd_searchcontext` **(the latter two are a 19-file finding)**. | no |
| `onions_*` (14 keys) | mixed | Onion-skin editor settings. Unset frame slots are `-100000`. | no |

**The `1021` format generation (`Rabbit.animeproj`) omits `doc_uuid`,
`action_refs`, and `modified_date` entirely — not as empty values, the keys
are absent from the JSON altogether (19-file finding).** It also has zero
named styles (`styles: []`), which the `1038`/`1045` generations never show.
Anything in this document that says a field is "always present" implicitly
excludes this one generation unless stated otherwise.

**Nothing in the document is a z-order index.** The draw order (back to
front) is simply the order layers appear in `layers`, recursively, and the
order shapes appear in `mesh.shapes`.

**The Moho app's own Layer Pool panel displays a container's children in the
*reverse* of this `layers` array order** — the panel's top row is the array's
*last* element, and vice versa. This is a real, confirmed UI-display fact,
but it is **not** evidence that the `layers` array's own order is "backwards"
for rendering: a layers panel showing front-most-on-top while the underlying
array is stored back-to-front is an ordinary UI convention, unrelated to
paint order. Tested directly: reversing the *entire* `layers` array before
painting was tried against `Bandit.mohoproj`'s `Bandit` root container and
produces visibly wrong output — it flips the already-correct relationship
where `Muzzle`/`Nose`/`EyeBrow` (`masking == 1`) draw normally on top of
`BellyTexture`, dragging `BellyTexture`'s opaque fill over the character's
eyes/muzzle/nose instead (confirmed wrong against the Moho app itself: those
three stay unaffected there). So: `layers` order **is** back-to-front paint
order, exactly as this tool already assumes — only the *panel's own display*
runs the other way. See the module docstring's MASKING section for the full
investigation this came out of (a real, separate masking bug, now fixed).

---

## 3. `project_data`

Only `width` and `height` are used. The rest is recorded here so it is clear
what is being skipped.

| Field | Observed values | Meaning |
|---|---|---|
| `width` / `height` | `1280×720`, `1920×1080` | Canvas size in pixels. **Used** — see [§ 4](#4-coordinate-system). |
| `fps` | `24.0` | Frame rate. Not used: `--frame N` takes a frame number, not a time. |
| `start_frame` / `end_frame` | `1`/`25`, `25`/`127`, `1`/`120`, `1`/`240` | Animation range. Note `start_frame` is not always `0`, while this tool's `--frame` default *is* `0`. |
| `back_color` | `{r:234, g:234, b:234, a:255}` | Canvas background. **0–255 integers**, unlike style colours ([§ 5.2](#52-channel-types-and-val-element-shapes)). Not drawn — the exported SVG has a transparent background. Probed inert (`docs/moho-field-probes.md`). |
| `antialiasing` | `true` | Project-wide render-quality flag. Shares its flat name with the **per-layer** `MeshLayer.antialiasing` ([§ 6.4](#64-type-specific-fields)) — the two were probed TOGETHER (`tools/probe_field.py` matches by literal key name, not JSON path) and found inert combined; a null result cannot be attributed to one owner alone, see `schema/project.schema.json`'s own note. |
| `depth_sort` / `distance_sort` | `false` | 3D sorting of layers. |
| `depth_of_field`, `focus_distance`, `focus_range`, `focus_blur` | `false`, numbers | Camera depth-of-field. `depth_of_field` alone is inert on Bandit.mohoproj's own stored blur/distance/range values, but `focus_blur`/`focus_distance` each affect rendering once `depth_of_field=true` is set as a precondition; `focus_range` stayed inert even then (docs/moho-field-probes.md). |
| `noise_grain`, `pixelation` | `0.0` | Global render effects. `noise_grain` must be written as an **integer** — a float value made Moho's headless render silently produce no output at all. `noise_grain=5` affects rendering. `pixelation` shares its flat name with the **per-layer** `LayerEffects.pixelation` ([§ 6.4](#64-type-specific-fields)); isolated from it (the two cannot be varied together — a value valid for one is the wrong JSON shape for the other and the combined document fails to render), this project-wide owner is inert while the per-layer owner affects rendering. |
| `stereo_mode`, `stereo_separation` | `0`, number | Stereoscopic output. `stereo_mode` alone is inert; `stereo_separation` affects rendering once `stereo_mode=1` is set as a precondition. |
| `global_render_style_fill_style`, `..._line_style`, `..._layer_style` | int (`0` in every one of the 19 sampled documents) | A document-wide style override applied at render time. **Correction:** an earlier revision of this document reported these as an empty string in the 5-file sample; direct inspection of the raw JSON shows the true value is the **integer `0`**, in the original 5 files too, not `""`. `schema/project.schema.json` types the field as `["string", "integer"]` precisely because the *value set this format allows* is not yet known to be closed to `0` — if a document ever sets a non-zero value, this tool would ignore it and could produce visibly wrong colours. Probed: `fill_style` and `line_style` are individually inert; `layer_style` affects rendering (docs/moho-field-probes.md). | 
| `global_render_style_minimize_randomness` | bool | Same override family. `true` throughout. **Correction (fix round 2):** an earlier revision of this row (a pre-existing claim already present before this milestone) said `false` throughout — that is backwards. A direct scan of all 76 corpus documents found this key is `true` on every one. Forcing it to `false` on Bandit.mohoproj was probed inert. |
| `color_palette` | `"Basic Colors.png"` | Editor swatch palette. Probed inert. |
| `soundtrack` | str | Audio file reference. |
| `extra_swf_frame`, `display_quality` | bool, int | Legacy export options. Both probed inert. |

---

## 4. Coordinate system

Points, translations, bone positions, and bone lengths are all stored in one
document-space unit where **2 units span the canvas height** — i.e. `y = +1`
is the top edge and `y = -1` is the bottom edge, regardless of the pixel
resolution. Width is *not* normalised, so the visible x range depends on the
aspect ratio.

```
pixel_x = moho_x * (height / 2) + width / 2
pixel_y = height / 2 - moho_y * (height / 2)        # y is flipped
```

Angles are in **radians** everywhere (bone angles, `rotation_z`,
`brush_jitter`, `offset_in`/`offset_out`). Colour components are floats in
`0.0–1.0` inside channels, but `0–255` integers in a few plain (non-channel)
colour fields such as `project_data.back_color` and the `TextLayer` colours.

---

## 5. Animated values (channels)

Almost every numeric, colour, boolean, or string property in Moho is stored
as the same "channel" object. This is the single most repeated structure in
the format: 584,616 instances across the 19-file sample.

### 5.1 Channel object fields

```jsonc
{
  "type": "Val",                 // value kind - see § 5.2
  "when": [0, 12, 24],           // keyframe frame numbers (ints), ascending
  "val":  [0.0, 1.0, 0.5],       // one value per keyframe
  "interp": [ {...}, {...}, {...} ],   // one entry per keyframe - see § 5.3
  "mute": false,                 // channel disabled?
  "ref":  false,                 // meaning not decoded
  "actions": [ { "name": "EyeBlink", "pose": {...} } ],   // optional - see § 11
  "split":  [ {...}, {...} ]     // optional, Vec2/Vec3 only - see § 5.4
}
```

- `when`, `val`, and `interp` are **always exactly the same length** — verified
  on all 584,616 channels (19-file total), zero exceptions. `interp[i]`
  describes the segment leaving keyframe `i`.
- `mute` is `false` on all but **one** channel across the 19-file sample:
  `Bandit.mohoproj`'s root `BoneLayer`'s own `transforms.translation` is
  `mute: true` **(correction — this is in the original 5-file sample, an
  earlier revision of this document reported `mute` as false everywhere)**.
  That channel has a single keyframe at the default `{0,0,0}`, so muting it
  has no visible effect either way — the gap remains untested for a document
  where a *multi-keyframe* channel is muted. `ref` is `true` on 207 channels
  across 3 documents (mostly single-keyframe `transforms.translation`
  channels in `BoneStrengthTool.animeproj`'s PSD-import rig and
  `OffsetBoneTool.animeproj`, plus one `timeline_markers` channel in
  `Bandit.mohoproj`) **(19-file finding, also correcting the same "false
  everywhere" claim)** — its meaning is still not decoded, and every
  occurrence sampled happens to be a single, non-conflicting keyframe, so
  nothing about current output is known to be wrong. `moho2svg.py` does not
  read either field. **A `mute: true` channel with more than one keyframe
  would be silently animated by this tool where Moho would freeze it** — an
  untested gap, not a confirmed bug, since no sample exercises that
  combination.
- A field that is never animated is sometimes stored as a bare scalar or a
  plain dict instead of a channel object. Both forms are accepted
  transparently (`Channel` treats a bare scalar as a single keyframe).

`moho2svg.py` evaluates a channel with a **monotone cubic between the two
bracketing keyframes**, clamped at both ends, ignoring `interp` entirely. That
is exact at keyframes and approximate between them. The curve shape was
inferred by scoring rendered output against Moho's own frames, not decoded
from the file — see
[`moho-animation-and-transform.md`](moho-animation-and-transform.md) § 3.6.

### 5.2 Channel types and `val` element shapes

`type` names the value kind. The `val` array's element shape follows from it,
consistently, with no exceptions observed:

| `type` | `val[]` element | Count | Example fields |
|---|---|---|---|
| `Val` | float | 143,724 | `width`, `smoothness`, `weight_in`/`weight_out`, `offset_in`/`offset_out`, `color_strength`, `anim_angle`, `anim_scale`, `rotation_z`, `blur` |
| `Color` | `{r, g, b, a}`, floats `0.0–1.0` | 22,969 | `fill_color`, `line_color`, point `color` |
| `Vec2` | `{x, y}` | 22,311 | mesh point `position`, `anim_pos`, `effect_offset`, `ik_parent_target` |
| `Bool` | bool | 9,341 | `flip_h`, `flip_v`, `layer_effects.visibility`, `ik_lock`, `bone_dynamics` |
| `Vec3` | `{x, y, z}` | 1,757 | `transforms.translation`, `transforms.scale`, `transforms.shear` |
| `String` | str | 1,083 | `switch_keys`, `shape_order`, `layer_ordering`, `timeline_markers` |

Note that `transforms.translation` and `transforms.scale` are **`Vec3`, not
`Vec2`** — the `z` component is present and this tool ignores it (a 2D
exporter, so this is deliberate, but it does mean layer depth is dropped).

### 5.3 The `interp` entries

Each `interp[i]` is a fixed-shape object. This tool ignores all of it; it is
documented here because it is what makes interpolation between keyframes
inexact.

| Field | Observed values | Notes |
|---|---|---|
| `t` | `0` (208,858), `4` (757), `2` (540), `6` (3), `1` (2) | Interpolation type. **The enum mapping is not decoded.** `0` is the overwhelming default. Non-`0` values appear almost exclusively on `pose`, `anim_pos`, `anim_angle`, `anim_scale`, and `physics_motor_speed`. |
| `v1`, `v2` | `(0.1, 0.5)` on 208,079 entries; also `(-1, -1)`, `(-1, 2)`, `(15, -1000000)` | Two type-dependent parameters. `(0.1, 0.5)` looks like an unused default carried on plain keyframes. |
| `im` | `1`, `3`, `5`, `9`, `0` | Not decoded. Possibly a bit field. |
| `in` | `1`, `0` | Not decoded. |
| `s` | `false` everywhere | Not decoded. |
| `h` | `0` everywhere | Not decoded. |
| `b` | absent on all but 16 entries | When present: a list of `{ao, ai, po, pi}` objects — plausibly explicit Bezier handles for the timing curve (angle/position, out/in). Only ever seen alongside `t == 4`, but most `t == 4` entries have no `b`, so `t == 4` is not simply "Bezier". |

A later pass that also descends into `actions[].pose` and `split[]` channels
counts 604,139 `interp` entries rather than the ~210,000 behind the table above
(the non-zero `t` counts agree exactly; the `t == 0` total does not), and
decodes part of the table: `b` is present on 182 entries, always exactly the
ones with `im == 9`, and its length equals the number of components in the
channel's value (1 for `Val`, 2 for `Vec2`, 3 for `Vec3`). See
[`moho-animation-and-transform.md`](moho-animation-and-transform.md) § 3 for
that analysis, including the cycle marker carried in `im`/`v1`/`v2`.

### 5.4 `split` — per-axis keyframes

A `Vec2` or `Vec3` channel may carry a `split` list holding one **independent
`Val` channel per axis**, with its own `when`/`val`/`interp`. This is Moho's
"separate the x and y curves" feature.

Observed exactly once, on a `Vec2` `anim_pos` in the `1045` document, where
the split X channel's keyframes matched the parent's. `moho2svg.py` does not
read `split`; it reads the parent `Vec2`/`Vec3` arrays. **If a document ever
splits a channel and then keyframes the axes differently, this tool would use
the stale parent values** — an untested gap.

### 5.5 Document-level `animated_values`

`doc.animated_values` is an object of five channels, all with exactly one
keyframe at frame `0` in all 19 documents:

| Key | `type` | Value seen | Meaning |
|---|---|---|---|
| `camera_track` | `Vec3` | `{0, 0, 3.732051}` in 18 of 19; `{0.232877, 0.481034, 3.732051}` in `Rabbit.animeproj` **(19-file finding — a real x/y camera pan, not the default)** | Camera position. The `z` value is the default camera distance. |
| `camera_pan_tilt` | `Vec2` | `{0, 0}` in every document | Camera pan/tilt. Forcing it to `{0.3, 0.3}` on Bandit.mohoproj affects rendering (docs/moho-field-probes.md) — a real, currently-unapplied camera field. |
| `camera_zoom` | `Val` | `2.0` in 18 of 19; `1.413848` in `Rabbit.animeproj` | Camera zoom. **Correction:** an earlier revision of this document reported `0.0` from the 5-file sample; direct inspection shows the true value is `2.0` in every one of the original 5 files too, not `0.0`. Whether `2.0` is itself Moho's neutral/no-op zoom value, or a real non-default zoom this tool should be applying, is not decoded. |
| `camera_roll` | `Val` | `0.0` in 73 of 76 | Camera roll. **Correction (fix round 2):** an earlier revision of this row (and the paragraph below, which repeated the claim) said `0.0` "in every document" — that is false. A direct scan of all 76 corpus documents (not just the original 19-file sample this table predates) found `camera_roll` nonzero in three: `Snow_wars/05 Snow angle.moho`, `Snow_wars/14 speed.moho`, `Snow_wars/23 Snow angle.moho`. Forcing it to `0.6` on Bandit.mohoproj (one of the 73 where it genuinely is `0.0`) affects rendering (docs/moho-field-probes.md) — a real, currently-unapplied camera field. |
| `timeline_markers` | `String` | `""` in every document | Editor timeline annotations. |

None of these are read by `moho2svg.py` (confirmed: no reference to
`animated_values` or any `camera_*` key anywhere in the source). This tool
renders with an implicit fixed camera. **A document with a moved or zoomed
camera would export with the wrong framing.** Given the corrected
`camera_zoom` value above, `Rabbit.animeproj`'s real pan, and (fix round 2)
`camera_roll`'s three nonzero documents above, this is **less settled than
previously stated** — it is not confirmed that "every sample sits at the
default" for ANY of these five channels: `camera_pan_tilt` is `{0,0}` in
all 76 corpus documents (confirmed by a direct scan), but `camera_roll` is
not, and `camera_zoom`'s uniform non-zero value across the 19-file sample
might itself be the neutral default rather than a real zoom. Until that is
resolved, treat this as an open risk rather than an invisible one.

---

## 6. Layers

### 6.1 Layer types

Each layer is a JSON object with a `type` field naming its kind:

Counts below are across all 19 sampled documents.

| `type` | Count | Meaning | Rendered? |
|---|---|---|---|
| `MeshLayer` | 648 | Vector artwork (points/curves/shapes) — the only layer kind that actually draws pixels. | **yes** |
| `GroupLayer` | 103 | Children with no skeleton. | **yes** (container) |
| `BoneLayer` | 47 | A skeleton (`skeleton.bones`) plus child layers deformed by it. | **yes** (container + skinning) |
| `TextLayer` | 34 | A caption. Moho keeps the laid-out glyph outlines in a nested `mesh_layer` field, which is a **complete** `MeshLayer` object — not a stripped-down `{type, mesh}` pair, it carries the full `MeshLayer` field set (noise/sketchy fields, `3d_mode`, `3d_options`, texture paths/filerefs) **(the full-field-set confirmation is a 19-file finding)**. | **yes**, via `mesh_layer` |
| `SwitchLayer` | 17 | Children are alternatives; only one shows at a time. | **yes** |
| `ImageLayer` | 15 | **(19-file finding, not in the original 5-file sample.)** A raster image/movie/PSD-import layer — see [§ 6.5](#65-imagelayer-19-file-finding). | **no** — silently dropped |
| `PatchLayer` | 12 | No mesh of its own — reuses another layer's mesh ([§ 12](#12-patch-layers)). | **yes**, resolved |
| anything else | 0 in these 19 files | Audio, particle, note, 3D layers etc. are not modelled. | no |

### 6.2 Common fields that affect rendering and **are** used

Present on every layer type unless noted.

- `name` — layer name. Used by `--layer` and `--mask-container`.
- `visible` (bool) — hidden layers are skipped unless `--include-hidden`.
- `edit_only` (bool) — kept for editing convenience, never rendered.
- `layers` — child layers, on container types only. A layer can have no mesh
  **and** no `layers` key at all; Moho draws nothing for it, not even an empty
  group. A `PatchLayer` is exactly this case *before* its target is resolved.
- `transforms` — the layer's own local transform. Ten channels, of which
  five are used: `translation` (`Vec3`), `scale` (`Vec3`), `rotation_z`
  (`Val`), `flip_h`, `flip_v` (`Bool`). Rotation and scale pivot on `origin`,
  not on local `(0, 0)`.
- `origin` — `{"x":.., "y":..}`, plain (not a channel), the pivot for the
  transform above.
- `parent_bone` — index into an ancestor `BoneLayer`'s `skeleton.bones`, or
  `-1`. `-1` means *flexible* ("region") binding; a non-negative index means
  *rigid* binding to that one bone. See [§ 9](#9-bones-and-skinning).
  Observed across the 19-file sample: `-1` on 813 of 876 layers, 54 layers
  rigidly bound to a non-negative index, and **`-3` on 9 layers — all of them
  `ImageLayer` instances that also carry a non-trivial `flexi_bone_subset`
  (19-file finding, not decoded — see [§ 6.5](#65-imagelayer-19-file-finding))**.
  `moho2svg.py` only distinguishes `-1` from `>= 0`, so `-3` is currently
  handled the same as any other negative value (i.e. as flexible binding),
  which is unconfirmed against real Moho output for this value.
- `flexi_bone_subset` — a `"|"`-separated list of **bone indices as a
  string**, e.g. `""` (all bones), `"0"`, `"1|2"`, `"30|31|32|33|34|35"`.
  Restricts flexible binding to those bones. These are indices into
  `skeleton.bones`, *not* names, and are unrelated to `mesh.groups`
  ([§ 7.10](#710-point-groups-meshgroups)).
- `masking` / `group_mask` — see [§ 10](#10-masking).
- `actions` — an action-name registry; see [§ 11](#11-actions-and-smart-bones).
- `uuid` — layer identity, referenced by `PatchLayer.target_layer_uuid` and
  by the various `*_layer_uuid` fields below.

### 6.3 Common fields that affect rendering and are **not** used

This is the important gap list: every field here changes what Moho draws.

| Field | Shape | Observed values | Consequence of ignoring it |
|---|---|---|---|
| ~~`layer_effects.alpha`~~ | `Val` channel | non-trivial on **139 leaf layers across 15 files** (11 of them animated) | **No longer in this list — decoded and applied.** The layer's own opacity. MEASURED as a plain linear blend: at 0.5 a layer lands on the exact midpoint of its 1.0 and 0.0 renders (mean error 0.13/255 over its own pixels), so it maps directly onto SVG `opacity` and Lottie's transform `o`. A *container's* own alpha is still **not** applied — three models were measured and the best still scored worse than ignoring it; 5 layers corpus-wide, each warned about. See [§ 6.3a](#63a-layer-opacity). |
| ~~`blend_mode`~~ | int | `0` on 3,794 layers; `1` on 117, `2` on 49, `3` on 2 | **No longer in this list — decoded and applied.** See [§ 6.6](#66-blend_mode). |
| ~~`layer_effects.visibility`~~ | `Bool` channel | non-trivial on **190 layers across 14 files** | **No longer in this list — decoded and applied.** The animated show/hide from the General tab's Compositing Effects group (manual ch. 12.02), which the manual states outright is "totally independent of the visibility box displayed in the layer list". A layer draws only when both are true — see `Layer.visible_at`. The earlier "`true` everywhere" reading was a 19-file artefact. |
| `layer_effects.blur`, `.noise`, `.pixelation`, `.threshold`, `.ambient_occlusion` | `Val` channels | mostly `0.0`, but not everywhere | Per-layer image effects. **Correction (fix round 2):** an earlier revision of this row (a pre-existing claim already present before this milestone) said `0.0` "everywhere"/"All off in the samples" — that is false for `.blur`: a direct scan of all 76 corpus documents found `.blur` nonzero in 79 occurrences across 25 documents. `.noise`/`.pixelation`/`.threshold`/`.ambient_occlusion` genuinely are `0.0` in all 6,597 occurrences checked. `.pixelation` shares its flat name with the project-wide `project_data.pixelation` ([§ 3](#3-project_data)); isolated from it, THIS (per-layer) occurrence affects rendering — probed AFFECTS RENDER on Bandit.mohoproj (docs/moho-field-probes.md). **M1.4a:** `.ambient_occlusion` was probed — forcing it to `5.0` on every one of Bandit.mohoproj's 25 occurrences left frame 25 byte-identical; unlike `.blur`, no corpus document sets it non-zero at all (universal `0.0`, not merely unsampled), so there is no real-usage document to retry it against. Now `EDITABLE`. **M1.4b:** `.blur` and `.threshold` are also each declared under three OTHER schema owners at the same flat name (`layer_shadow`/`layer_shading`/`perspective_shadow` below, plus a shape-level `Shaded`/`ShadowStyle`/`SoftStyle` pair with no writer — see `schema/layer.schema.json`'s `LayerEffects.blur`/`.threshold` for the full owner table). Isolated from those three (a hand-edited copy of Bandit.mohoproj with the other owners' occurrences of the same key deleted, since `tools/probe_field.py` matches by flat name across the whole tree): THIS owner's `.blur` (which, unlike the other three, has no `on`/off gate of its own) is AFFECTS RENDER; `.threshold` here is a `Val` (numeric) channel, unlike the Bool `threshold` the other three owners use, and is inert. Both now `EDITABLE`. `.noise` was not probed. |
| `layer_outline` | `{on, color, width}` | `on: true` on real occurrences in 2 of 76 documents (`DonkeyAndMan.mohoproj`, `Gathered-00intro.mohoproj`) | An extra outline stroked around the whole layer. **Correction (M1.4a):** an earlier revision of this row said `on: false` "everywhere" — a 76-document scan found the 2 documents above. Now `EDITABLE`: probed as a whole block, forced `on: true` on Bandit.mohoproj (with that document's own stored color/width), AFFECTS RENDER at frame 25 (docs/moho-field-probes.md). |
| `layer_shadow` | `{on, angle, blur, color, expansion, offset, threshold, noise_amp, noise_scale, clip_to_group}` | `on: true` on real occurrences in 36 of 76 documents (22 of 23 `Snow_wars/*.moho` episodes - all but `16 Distance.moho` - plus `DonkeyAndMan.mohoproj`, `Gathered-02Wire2.mohoproj`, `Scene 2.moho` and 11 `Snow-girl-cut*.mohoproj` files) | Drop shadow. **Correction (M1.4a):** an earlier revision of this row said `on: false` "everywhere" — a 76-document scan found the 36 documents above. Now `EDITABLE`: probed as a whole block, forced `on: true` on Bandit.mohoproj (with that document's own stored angle/blur/offset/color), AFFECTS RENDER at frame 25 (docs/moho-field-probes.md). **M1.4b:** `.blur` and `.threshold` (a plain Bool channel here, unlike `layer_effects.threshold`'s Val channel) were each isolated from their three sibling owners (see `layer_effects.blur` row above) on a hand-edited copy of Bandit.mohoproj with `on` forced true and the other owners' occurrences of the same key deleted; both AFFECTS RENDER and are now `EDITABLE`. **M1.4b completion (2026-08-19):** `.noise_amp`/`.noise_scale` were isolated the same way (LayerShading's own occurrence of each deleted, `on` forced true) — forcing the stored `0.0`/`64.0` to `0.5`/`8.0` left frame 25 byte-identical for both; now `EDITABLE`, inert. Neither `moho2svg.py` nor `moho2lottie.py` reads any of `.blur`/`.threshold`/`.noise_amp`/`.noise_scale` at all (confirmed by direct grep, zero hits in both files — `moho2svg.py`'s own module docstring already says as much: "Physics (wind/gravity) and layer_effects/layer_shadow are ignored by default"); the earlier "writer-backed by lottie2moho.py" phrasing in this milestone's prose cited the wrong tool (`lottie2moho.py`/`svg2moho.py` are a separate, newer, reverse-direction SVG/Lottie-to-Moho pair, unrelated to this plan) — EDITABLE here has always rested on `tools/probe_field.py`'s own direct Moho-render probes, not on either exporter's reading model. |
| `layer_shading` | `{on, angle, blur, color, contraction, offset, threshold, noise_amp, noise_scale}` | `on: true` on real occurrences in 14 of 76 documents (`Gathered-01Intro2.mohoproj`, `Gathered-02Wire2.mohoproj`, `The Nutcracker Ballet.moho` and 11 `Snow-girl-cut*.mohoproj` files) | Inner shading. **Correction (M1.4a):** an earlier revision of this row said `on: false` "everywhere" — a 76-document scan found the 14 documents above. Now `EDITABLE`: probed as a whole block, forced `on: true` on Bandit.mohoproj (a document where the effect is NOT naturally used) — inert there at frame 25 (docs/moho-field-probes.md); not retested on one of the 14 documents where it genuinely is on. **M1.4b completion (2026-08-19):** `.blur`/`.threshold`/`.noise_amp`/`.noise_scale` were each isolated on a hand-edited copy of Bandit.mohoproj (the three other owners' occurrences of the same key deleted, this block's own `on` forced true at all 25 sites) — all four came back inert (`.blur` `0.066667`→`0.5`, `.threshold` `false`→`true`, `.noise_amp` `0.0`→`0.5`, `.noise_scale` `64.0`→`8.0`, all byte-identical at frame 25). All four now `EDITABLE`. See `layer_shadow`'s own row above for the corrected writer-location finding (neither real exporter reads any of these four fields, under any owner). |
| `perspective_shadow` | `{on, blur, color, scale, shear, threshold}` | `on: false` on Bandit.mohoproj | Perspective shadow. **Correction (fix round 2):** an earlier revision of this row (following a pre-existing claim already present elsewhere in this document before this milestone) said `on: false` "everywhere" — that is false. A direct scan of all 76 documents found `on` is `true` on 21 of 6,597 occurrences, across 14 documents (`Clay_Crocodile.mohoproj` and 13 `Snow_wars/*.moho` episodes). Its own `shear` (a `Val` channel, NOT the same field as `transforms.shear` below despite the shared name) was probed on Bandit.mohoproj specifically, where the effect genuinely is off, and came back inert there — a real effect on one of the 14 documents where it is actually on was not tested. **M1.4a:** the compound key ITSELF (the whole block, distinct from its `shear` sub-field above) is now `EDITABLE` — forcing every one of Bandit.mohoproj's 25 occurrences to `on: true` (with the document's own stored blur/scale/shear/color) AFFECTS RENDER at frame 25 (docs/moho-field-probes.md). **M1.4b completion (2026-08-19):** `.blur`/`.threshold` were each isolated the same way (the other three owners' occurrences deleted, `on` forced true) — both AFFECTS RENDER (`.blur` `0.012346`→`0.5`, `.threshold` `false`→`true`, both changing frame 25's bytes), now `EDITABLE`. See `layer_shadow`'s own row above for the corrected writer-location finding. |
| `layer_color` | `{on, color}` | `on: true` on real occurrences in 19 of 76 documents (`Gathered-01Intro2.mohoproj`, `Gathered-02Wire2.mohoproj`, `Rabbit.animeproj`, `Scene 2.moho`, 14 `Snow-girl-cut*.mohoproj` files, `The Nutcracker Ballet.moho`) | A flat colour override for the whole layer. **Correction (M1.4a):** an earlier revision of this row said `on: false` "everywhere" — a 76-document scan found the 19 documents above. Now `EDITABLE`: probed as a whole block, forced `on: true` (opaque black) on Bandit.mohoproj (a document where the effect is NOT naturally used) — inert there at frame 25 (docs/moho-field-probes.md); not retested on one of the 19 documents where it genuinely is on. |
| `transforms.rotation_x`, `.rotation_y` | `Val` channels | `0.0` everywhere | 3D rotation. A 2D exporter cannot express these. Both probed AFFECTS RENDER on Bandit.mohoproj (docs/moho-field-probes.md) — real, currently-unapplied fields. |
| `transforms.shear` | `Vec3` channel | `0` everywhere | Shear. Could be expressed in an SVG matrix, but is not. Shares its flat name with `perspective_shadow.shear` above; isolated from it, THIS occurrence probed AFFECTS RENDER (docs/moho-field-probes.md). |
| `transforms.translation.z`, `.scale.z` | float | defaults | Layer depth. |
| `transforms.following`, `.physics_nudge` | channels | defaults | Path-following offset and physics displacement. Both probed inert on Bandit.mohoproj — `following` is confounded by `follow_curve = -1` on that document (see below; this is NOT the corpus-wide value, see the correction there). `physics_nudge` is a **stronger** negative than an earlier revision of this row claimed: **correction (fix round 2)** — `physics.enabled` is `true` on every one of 6,597 occurrences across all 76 corpus documents (not `false`, as previously written here), including every site on Bandit.mohoproj, so physics was genuinely active throughout the probed document and the field still moved no pixel; neither `moho2svg.py` nor `moho2lottie.py` reads `physics_nudge` at all, which is the more direct reason it has no effect in this tool's own output. |
| `motion_blur` | `{on, frames, radius, skip, alpha_start, alpha_end, frame_percentage, extended_frames, sub_frames}` | `on: true` on real occurrences in 2 of 76 documents (`SlickObjectTransition.mohoproj`, `Snow-girl-cut51.mohoproj`) | Motion blur. **Correction (M1.4a):** an earlier revision of this row claimed both "`on: false`" everywhere and "not meaningful for a single-frame export anyway" — BOTH are false. Flipping Snow-girl-cut51.mohoproj's own genuinely-active block (`on: true`, layer 6/7) to off at frame 175 (inside the animated `[169, 187)` window) AFFECTS RENDER — motion blur DOES change Moho's own single-frame headless PNG output. Its own `alpha_start`/`alpha_end` sub-fields, probed the same non-confounded way (real `on: true`, only the sub-field's value changed), came back inert — see their own entries in `schema/layer.schema.json`'s `MotionBlur`. Now `EDITABLE` for the compound key itself (docs/moho-field-probes.md). |
| `distortion_layer_uuid` | str | `""` in all 827 layers that have it; **absent in the `1021` file** | Points at another layer used as a distortion mesh — the most likely storage hook for Smart Warp. See [`moho-rigging-and-deformation.md` § 5](moho-rigging-and-deformation.md#5-smart-warp). |
| `follow_layer_uuid`, `follow_curve`, `follow_bending`, `rotate_to_follow` | str/int/bool | `""`, `-1`/`0`, defaults | "Follow path" rigging. **Correction (fix round 1):** an earlier revision of this document claimed `follow_curve` is `-1` in every sampled document with no exception — that is wrong. A direct scan of all 76 corpus documents found `follow_curve` takes **two** values, `{-1, 0}`, not one: it is `0` on layers in `Gathered-00intro.mohoproj`, `Gathered-01Intro2.mohoproj`, `Gathered-02Wire2.mohoproj` and four `metamorphosis/Scene *.moho` files. In particular, the layer in `Gathered-01Intro2.mohoproj` that actually carries a real `follow_layer_uuid` (`layers[7]/layers[1]`, name `Butter`, uuid `b9d35e03-0404-4672-9719-d213e82fad57`, targeting `870b500e-c8f6-45b9-ab17-38db1de3b6b9`) has `follow_curve = 0`, NOT `-1` — so this is not confirmed to be an inert/feature-disabled configuration; whether `0` is a real curve selection or a different "unset" sentinel is unresolved, not ruled out. The `follow_layer_uuid`/`follow_bending`/`following` probes in this milestone were run on `Bandit.mohoproj`, where `follow_curve` genuinely is `-1` on every layer, so those specific inert results stand on their own terms — but the broader claim that no corpus document could exercise the feature does not hold, and `Gathered-01Intro2.mohoproj` remains an open candidate for a follow-up probe. `rotate_to_follow` was not probed. |
| `physics`, `gravity`, `wind`, `enable_physics`, `use_baked_physics` | objs/channels | disabled | 2D physics simulation. |
| `scale_compensation`, `scale_normalization` | bool/float | defaults | How a layer's stroke width reacts to scaling. Relevant to [§ 7.6](#76-stroke-width) if ever non-default. Both probed inert on Bandit.mohoproj, whose ancestor scale is 1.0 throughout — neither was retested under an actual non-1.0 ancestor scale. |
| `layer_ordering` | `String` channel | `""` | Animated child reordering (with `animated_layer_order` on `BoneLayer`). Would change draw order per frame. |
| `timing_offset` | int | `0` everywhere | Shifts this layer's whole timeline. Non-zero would desync the frame this tool evaluates. |
| `layer_ref_*` (`uuid`, `path`, `fileref`, `mod_date`, `same_doc`) | mixed | empty on most layers, but not all | Linked/referenced external layer. A document using these would be missing artwork here. **Correction (fix round 2):** see [§ 11.4](#114-action_refs-and-layercomps) — several corpus documents DO set non-default values here, contrary to an earlier revision of this row. All five probed inert on Bandit.mohoproj, one of the documents where they genuinely sit at their defaults. |
| `camera_immune` | bool | `true` on 6 layers in 3 files | **Now applied** — the layer projects through the DEFAULT camera, so it stays put on screen while the camera moves (manual ch. 12.02, "Immune to camera movements"). Inherited by descendants. See [§ 9](moho-animation-and-transform.md#9-camera-animation) of the animation doc. |
| `dof_immune`, `face_camera`, `face_camera_mode`, `3d_mode` | mixed | defaults, `face_camera_mode: 2` | 3D / depth-of-field behaviour. Not used. `dof_immune` probed inert (depth_of_field is itself off in the probed document). `face_camera` probed AFFECTS RENDER; `face_camera_mode` is inert with `face_camera` left off but AFFECTS RENDER once `face_camera=true` is set as a precondition. `3d_mode` was not probed here (see the 3d_mode/3d_shading_density finding in docs/moho-field-probes.md from an earlier task). |
| `3d_options` (`Mesh3DOptions`) | obj | see [§ 6.4](#64-type-specific-fields) — present on every `MeshLayer` (648 instances), always at identical defaults | 3D-extrusion rendering settings, entirely inert in every sample because `3d_mode` is `0` everywhere. |
| `quality_flags` | int | `4092`, `4094`, `45052`, `45054`, `2044` | A bit field of per-layer render toggles. Not decoded. Probed inert on Bandit.mohoproj. |
| `label_col`, `expanded`, `shown_in_timeline`, `selected`, `random_num`, `layer_user_tags`, `layer_user_comments`, `ignored_by_layer_picker`, `consolidated_channels`, `render_only`, `modification_date` | mixed | — | Editor state, or (for `random_num`/`render_only`) an undecoded render toggle. Both probed inert on Bandit.mohoproj under this file's default probe settings. `mask_expansion` moved out of this list — decoded and applied, see [§ 10.5](#105-mask_expansion-and-exclude_lines_from_mask--the-two-checkboxes). |
| `metadata`, `script_data` | obj | see [§ 6.4](#64-type-specific-fields) | Editor/script bookkeeping bags, key sets now enumerated. |

### 6.3a Layer opacity

`layer_effects.alpha` sits in the same General-tab Compositing Effects group
as the animated `visibility` above, and is keyframeable the same way. It was
silently ignored until it was measured, which left artwork on screen that
Moho fades out entirely.

**The measurement.** On `SlickObjectTransition.mohoproj`'s "Sun" layer at
frame 36: setting alpha to 0.5 produces an image whose mean distance from the
midpoint of the 1.0 and 0.0 renders is **0.13/255** over the layer's own
pixels. A plain linear blend, with no gamma or premultiplication surprise.

**The clearest case in the corpus.** `Snow-girl-cut14.mohoproj`'s
`/Layer 11/Layer 2` keys alpha `1 → 0 → 0 → 1` over frames 0..9. Rendered
alone by Moho it covers **0** pixels at frame 1 and **45,671** at frame 30.
Before this was applied, that layer drew a white quad at frame 1 — invisible
against the white card above it, but it also (once masking modes 3/5 were
implemented) punched a subtract-hole through that card. Applying alpha fixed
both at once.

**Containers are excluded, deliberately.** Three models for a group's own
alpha were measured against Moho on a non-masking group
(`SlickObjectTransition.mohoproj`'s "Frame Mask" with `group_mask` forced to
0, the group at 0.5, scored over the group's own pixels):

| model | mean \|err\| |
|---|---|
| ignore it entirely | **21.6** |
| flatten the group, then composite at 0.5 | 30.2 |
| push 0.5 onto every child | 24.0 |

Ignoring it scored best of the three, which means none of them is what Moho
computes. Guessing would make the render worse, so `moho2svg.py` warns
instead — 5 layers corpus-wide (4 `GroupLayer`, 1 `SwitchLayer`) against 139
leaf layers this is exact for.

**Two knock-on rules**, both measured (see [§ 10.3](#103-three-further-rules-each-measured)):
a layer faded to nothing contributes nothing to a mask, and neither does one
hidden by either visibility mechanism.

### 6.4 Type-specific fields

**`MeshLayer`** — `mesh` is the only field used ([§ 7](#7-mesh-model)). Not used:

- `fill_texture_path` / `fill_texture_fileref`, `line_texture_path` /
  `line_texture_fileref` — image textures for fills and lines. Empty in
  every mesh layer.
- `noisy_lines`, `noisy_shapes`, `extra_sketchy`, `extra_lines`, `noise_amp`,
  `noise_scale`, `noise_interval`, `animated_noise` — the "sketchy lines"
  look. `extra_sketchy: true` with `extra_lines: 5` on **2 layers** (in
  `SketchBone`), so those two layers should render with repeated jittered
  strokes and do not. **M1.4b:** this `noise_amp`/`noise_scale` pair sits
  directly on the `MeshLayer` object itself — a completely different owner
  from the same-named channel inside `layer_shadow`/`layer_shading`
  ([§ 6.3](#63-layer-fields-shared-by-every-kind), the two rows above this
  section), despite both being direct children of a Layer dict at the same
  JSON depth. Neither `svg2moho.py` nor `lottie2moho.py` writes this
  MeshLayer-level pair at all — `lottie2moho.py`'s own `noise_amp`/
  `noise_scale` template writer only builds the `layer_shadow`/`layer_shading`
  occurrences — so it has no writer-backed value to probe and stays
  `UNKNOWN`, unlike its `layer_shadow`/`layer_shading` namesakes.
- `gap_filling`, `antialiasing` (`exclude_lines_from_mask` is decoded but
  deliberately not applied — see [§ 10.5](#105-mask_expansion-and-exclude_lines_from_mask--the-two-checkboxes)).
  `antialiasing` here shares its flat name with the project-wide
  `project_data.antialiasing` ([§ 3](#3-project_data)) — see that entry for
  the combined-probe result and its caveat.
- `triangulated`, `squashable_deformer`, `frame_zero_deformer` — three
  deformer flags that exist **only in the `1045` format generation** (all 21
  `MeshLayer`s of `Bandit.mohoproj`; absent from every `1038` and `1021`
  layer), at `false`/`false`/`true` throughout. They are the clearest sign in
  this sample that a mesh can act as a deformation mesh — see
  [`moho-rigging-and-deformation.md` § 5.2](moho-rigging-and-deformation.md#52-what-the-files-actually-show).
- `3d_mode` (always `0`) and `3d_options` — see `Mesh3DOptions` below.
- `metadata` — see below.

**`Mesh3DOptions`** (`MeshLayer.3d_options`) — **(19-file finding.)** Ten
3D-extrusion settings gated by `3d_mode`, present on **every single sampled
`MeshLayer`** (648 instances, including the one nested inside each
`TextLayer`), always at identical default values:
`3d_shading_mode: 1`, `3d_shading_density: 50`,
`3d_shading_color: {64,64,64,255}` (plain 0–255 RGBA), `3d_silhouette_edges`
/ `3d_material_edges` / `3d_crease_edges: true`,
`3d_crease_angle: 1.047198` (π/3), `3d_edge_extension: 0.0`,
`3d_backface_removal` / `3d_reset_z: false`. Because `3d_mode` is `0` in
every sample, the whole block is currently inert — but it is large and was
completely undocumented before this pass; a document that actually enables
3D extrusion would export as flat 2D geometry with no extrusion or 3D
shading at all. Full field list in `schema/layer.schema.json`'s
`Mesh3DOptions`.

**`BoneLayer`** — `skeleton` and `actions` are used. `skeleton` is
`{type, binding_mode, bones}`, plus `bones_groups` in the `1045` documents —
empty in most, and **populated in `Night_Boy.mohoproj`**, whose one entry is
`{type: "BoneGroup", enabled, name, bones: [101, 102, 103], active_bone:
<Val channel>}`: Vitruvian Bones, decoded down to the selector but not to its
effect (see
[`moho-rigging-and-deformation.md` § 4b.1](moho-rigging-and-deformation.md#4b1-the-storage-decoded--and-the-semantics-still-not)).
`binding_mode` is `1` on 41 of the 42 skeletons
that actually hold bones, and **`2` on one** (`OffsetBoneTool.animeproj`,
layer `Happy Dance`) — an earlier revision of this document claimed `1`
everywhere, which was too strong. Its meaning is not decoded, and this tool
never branches on it. Also
carries `grandpa_bone` (lets bones bind layers nested deeper than direct
children), `flexi_bone_elbow`, `animated_layer_effects` — none used.
`flexi_bone_elbow` probed inert on Bandit.mohoproj (docs/moho-field-probes.md).
See
`layer_ordering`/`animated_layer_order` and `gravity`/`wind` below, both
shared with `GroupLayer` but shaped differently.

**`GroupLayer`** — no extra rendering fields beyond the common set, but see
`gravity` below.

**Container `layer_ordering` / `animated_layer_order` (`BoneLayer` and
`GroupLayer`) — (19-file finding).** `layer_ordering` is a `String` channel
meant to animate child draw order over time; `animated_layer_order` is the
bool that gates whether it is active. Present on ~150 containers across the
sample (effectively every `BoneLayer`/`GroupLayer`) — but `layer_ordering`'s
value is an **empty string in every single instance**, and
`animated_layer_order` is `true` on only 2 containers in the whole sample
(`ControlBones.animeproj`, `SketchBone.animeproj`), where the paired channel
is still empty. So no sampled document actually reorders its children over
time, and `moho2svg.py` — which always uses the raw `layers` array order — is
correct for every file here, but would stack layers wrongly for a document
that does use this feature.

**`gravity` / `wind` (bone and group physics) — (19-file finding.)** Two
unrelated fields share the name `gravity` with **different shapes**:
`BoneLayer.gravity` is `{direction, strength}` as **`Val` channels**
(radians / magnitude — observed `direction: 4.712389` = 3π/2, i.e. straight
down); `GroupLayer.gravity` is `{x, y}` as **plain floats**. `BoneLayer` also
has a `wind` field (`{direction, strength, turbulence_amplitude,
turbulence_frequency}`, also channels).

**Both fields only exist from format 1045**, which is why they looked rare:
`Bandit.mohoproj` was the only 1045 document when they were first counted. A
1045 re-save of `SketchBone.animeproj` from Moho Pro 14.4 — a document using
no physics at all — carries `wind.strength = 100.0` on **all five** of its
`BoneLayer`s and `gravity = {x: 0, y: -10}` on every `GroupLayer`. So these
are per-layer defaults Moho always writes, not a sign that anything is being
simulated. The per-bone `wind_dynamics` flag is the real subscription switch
(`Layer.physics_dynamic`, false on every bone of both 1045 documents above)
— confirmed genuinely load-bearing outside this 19-file corpus:
`DarkMan.mohoproj` (gitignored, user-supplied) sets it `true` on all 91 of
its bones, with real secondary motion observed in Moho App that plain
keyframe playback does not reproduce. `moho2svg.py`/`moho2lottie.py` now
read `wind_dynamics` (`Layer.physics_dynamic` for detection/warnings, and an
opt-in `--wind-dynamics` flag reusing `Skeleton.dynamic_angles`' spring for
an actual attempt at simulating it) — but that attempt is **confirmed NOT to
reproduce Moho's own damping** on the one bone tested (see
`Skeleton.dynamic_angles`' WIND EVIDENCE section), so "read" here means
detected and experimented with, not decoded. `gravity` itself is only ever
read as part of that same detection (`_any_nonzero("gravity")`) — no
gravity-specific force is simulated separately from wind.

**`SwitchLayer`** — `switch_keys` (a `String` channel whose `val` entries are
**child layer names**) selects the active child; used. Not used:
`switch_interpolation`, `switch_data` (`""` in every sample),
`frame_by_frame`, `previewAlignment`. A `SwitchLayer` also carries its own
`skeleton` object (with an empty `bones` list in every sample) — do not
mistake it for a `BoneLayer`.

**`PatchLayer`** — `target_layer_uuid` and `target_layer_id`; see
[§ 12](#12-patch-layers).

**`TextLayer`** — the nested `mesh_layer` is what gets rendered, so the text
metadata is informational only: `text` (the literal string, `\n` for line
breaks), `font` (e.g. `"Tamales Regular Normal Upright"`), `textsize`,
`justification` (`0`, `1`), `leading`, `kerning`, `fill`, `stroke`,
`fillcolor` / `linecolor` (plain `0–255` RGBA, not channels), `linewidth`,
`textinheritedstyle1` / `textinheritedstyle2`, and eleven `balloon*` fields
for speech balloons (all off in the samples). Because the glyph outlines are
already baked into `mesh_layer`, ignoring the font fields costs nothing —
**unless** a viewer needs to re-layout the text, which this tool never does.
`TextLayer` is the one layer type that never carries an `actions` list.
**`mesh_layer` is confirmed to be a complete `MeshLayer` object, not a
stripped-down `{type, mesh}` pair (19-file finding)** — it carries the whole
`MeshLayer` field set, including `Mesh3DOptions`, texture paths/filerefs, and
the "sketchy lines" fields, all likewise unused.

**Per-layer `metadata` / `script_data` bags — (19-file finding.)** Both are
small free-form key/value bags, distinct from the document-level `metadata`
in [§ 2](#2-top-level-structure). `metadata` appears on `MeshLayer`,
`BoneLayer`, and `SwitchLayer` instances; observed keys: `what` (`0`),
`NewLayerScript` (bool), `LM_GrandpaBones` (bool, `SwitchLayer` only,
presumably the same feature as `BoneLayer.grandpa_bone`), `psd_layers` (a
`"|"`-joined list of PSD layer indices, e.g. `"24|12|7|23|..."`, on the
`BoneLayer` wrapping a PSD cutout-puppet import — recording which PSD layers
became `ImageLayer` children), and a `g_<number>` boolean-toggle family
(`g_10000`, `g_10001`, `g_10002`, `g_10031`, `g_10033`, `g_10056`, `g_10069`,
`g_10082` observed). `script_data` (rare — 2 `BoneLayer` instances in
`WhatIsBone.animeproj`) has the shape `{NewLayerScript, what}`. Neither bag
is read by `moho2svg.py`.

### 6.5 `ImageLayer` (19-file finding)

A raster image/movie/PSD-import layer, absent from the original 5-file
sample — found in `BoneStrengthTool.animeproj`'s "dude side.psd" cutout-puppet
rig (one `ImageLayer` per PSD layer, 15 total, each bound to a bone subset).
**Not handled at all by `moho2svg.py`, a vector-only exporter — a document
using `ImageLayer` silently loses that artwork on export.**

It carries the same `LayerCommon` fields as any other layer (including the
`parent_bone == -3` value noted in [§ 6.2](#62-common-fields-that-affect-rendering-and-are-used),
observed only on `ImageLayer` instances, always alongside a real
`flexi_bone_subset` — presumably a bone-mesh-warp deformation mode specific
to raster images, not reverse-engineered), plus its own fields:

| Field | Meaning |
|---|---|
| `image_path` / `image_fileref` | The source image/movie file. |
| `width` / `height` | Plain (not channels) pixel dimensions. |
| `image_cropped` | Whether the image is cropped to a sub-region. |
| `psd_layer` / `psd_layerid` | Which PSD layer this instance came from. Present on most, not all, sampled instances (244/332 `ImageLayer` instances across the 76-document corpus, in 13 of the 76 documents). |
| `psd_layer_bounds` | `{top, left, right, bottom}` — the PSD layer's bounding box within the source PSD canvas. |
| `avi_alpha`, `movie_looping`, `interpreted_fps`, `persist_first_frame` / `_last_frame`, `premultiplied_movie`, `reverse_movie` | Embedded-movie playback settings. |
| `sampling_mode`, `quality_level` | Image resampling settings. |
| `toon_effect`, `toon_black_threshold`, `toon_gray_threshold`, `toon_lightness`, `toon_saturation`, `toon_quantize`, `toon_min_edge_threshold`, `toon_max_edge_threshold` | A cel-shading post-process filter over the raster image. |

None of the above is read by `moho2svg.py`, but `lottie2moho.py`'s
`_image_layer_template` already writes all of them (except `images`, below)
at real-file-correct values on every `ImageLayer` it emits, which is what let
M1.2 of `docs/moho-field-coverage-plan.md` register them `EDITABLE` without
decoding anything new. That milestone also probed each one for a render
effect with `tools/probe_field.py` — one document,
`moho/Snow_wars/04 snow man construction.moho` (28 `ImageLayer` instances, a
PNG-background + PSD-cutout snowman-building scene), since **the PSD/PNG
source assets `moho/Boar.mohoproj` and `moho/Clay_Crocodile.mohoproj`
reference are not present in this checkout** (`Images/` does not exist next
to either file) — both render every `ImageLayer` as Moho's own
broken-image placeholder, which produces a misleadingly clean "inert" result
for anything probed against them (see the stray `toon_effect`/`Boar.mohoproj`
row in `docs/moho-field-probes.md`, superseded by the same key's row against
the working Snow_wars document). Findings, all at frame 0 of that one
document, so read as "true there," not "true everywhere":

- **AFFECTS RENDER:** `psd_layer` (forced to an out-of-range value on every
  occurrence — not a purely cosmetic identifier, Moho reads it back to pick
  the source PSD layer's pixel data), `sampling_mode`, `quality_level`,
  `toon_effect`, and all seven `toon_*`/edge-threshold fields once
  `toon_effect=true` was forced as a precondition first.
- **Inert** on this document: the seven embedded-movie fields (`avi_alpha`,
  `movie_looping`, `interpreted_fps`, `persist_first_frame`,
  `persist_last_frame`, `premultiplied_movie`, `reverse_movie` — expected,
  since every image on this document is a still, not a movie), `image_cropped`
  (weakly — the 4 sites whose value actually changed all carried a
  degenerate all-zero `psd_layer_bounds`, so a non-degenerate crop was never
  exercised), and `psd_layer_bounds` itself (forced to a shared, non-degenerate
  rectangle on every occurrence — read as import-time metadata that Moho does
  not re-consult at render time, since actual on-canvas placement/size tracks
  `width`/`height`/`transforms`/`origin` instead).

A 21st field, `images` (a `FileRef` array for a movie imported as a numbered
image sequence rather than one file — see its own schema entry), is matched
by the same M1.2 classifier pattern but turned out **not to be written by
`lottie2moho.py` at all**: the plan's writer-location citation
(`lottie2moho.py:1914`) pointed at an unrelated local variable named
`"images"` (an output directory path), not a dict key. It stays `UNKNOWN` —
present in only 1 of the 76 corpus documents (`metamorphosis/Scene 3.moho`,
424 entries, `frame0000.png` .. `frame0423.png`) — pending the
observe-then-probe recipe a field with no writer needs.

See `schema/layer.schema.json`'s `ImageLayer` for the full field list with
per-field descriptions and probe evidence.

### 6.6 `blend_mode`

How a layer composites against what is drawn beneath it. Present on every
layer; `0` (Normal, a plain source-over paint) on 3,794 of the 3,962 layers in
the 46-file sample. The rest: **`1` on 117 layers, `2` on 49, `3` on 2** —
all but three of them `MeshLayer`s, the three being `GroupLayer`s.

The manual names the blend modes (12.02 *General Tab*, "Layer blending mode")
but never numbers them. The numbering below is the order the Moho 14.4
application binary itself uses when it builds that menu, where the modes'
localisation keys sit in one contiguous run:

| | | | |
|---|---|---|---|
| 0 Normal | 4 Add | 8 Color | 12 Color Burn |
| 1 Multiply | 5 Difference | 9 Luminosity | 13 PSD Linear Dodge (Add) |
| 2 Screen | 6 Hue | 10 Soft Light | |
| 3 Overlay | 7 Saturation | 11 Color Dodge | |

**Confirmed: 1, 2, 3 only** — and only those, because they are the only values
any sample document uses. The confirmation is a render comparison, not
inspection: exporting `Snow-girl-cut51.mohoproj` (13 blend-mode layers) with
these three mapped to CSS `multiply`/`screen`/`overlay` moved the output
measurably toward Moho's own PNG render of the same frame — mean absolute
difference 26.82 → 20.20 across the whole canvas, and 443,037 → 383,444 pixels
differing by more than 20. **Unverified: 4–13**, mapped on the strength of the
binary's menu order alone.

**Scope of the blend.** Moho renders each container layer into its own buffer
and composites that buffer into its parent, so a blending layer reaches its own
container's content and stops there. `moho2svg.py` reproduces this by putting
`isolation:isolate` on exactly those containers that *directly* hold a blending
layer. `moho2lottie.py` cannot: it flattens the tree into one flat Lottie layer
list, so a container's own blend mode has nowhere to land (counted warning
`blend_mode_container`, 3 layers corpus-wide) and a mesh layer's blend reaches
everything beneath it in the composition.

---

## 7. Mesh model

### 7.1 The `mesh` object

A `MeshLayer`'s `mesh` has three parallel structures plus metadata:

| Field | Meaning | Used? |
|---|---|---|
| `points` | Every point used by the mesh ([§ 7.2](#72-mesh-points)). | **yes** |
| `curves` | Sequences of curve points ([§ 7.3](#73-curves-and-curve-points)). | **yes** |
| `shapes` | Filled/stroked regions ([§ 7.4](#74-shapes-and-edges)). | **yes** |
| `groups` | Named point groups ([§ 7.10](#710-point-groups-meshgroups)). | no |
| `shape_order` | `String` channel; a `"\|"`-joined list of `shape.id` values, e.g. `"23\|24\|...\|33"`. | no — see [§ 7.9](#79-why-edges-and-shape_order-are-not-trustworthy) |
| `anim_shape_order` | bool. **Corrected (M1.4a):** an earlier revision of this row said "false on all 648 meshes (19-file total)" — a 76-document scan found `true` on 14 of 4,969 meshes, across 7 documents, all `Snow-girl/Snow-girl-cut*.mohoproj` (cut7, cut8, cut10, cut11, cut12, cut14, cut51). Presumably enables keyframing `shape_order` (itself never consulted — see [§ 7.9](#79-why-edges-and-shape_order-are-not-trustworthy)). Forcing it `true` on Bandit.mohoproj's 21 meshes left frame 25 byte-identical. `EDITABLE` (docs/moho-field-probes.md). | no |
| `next_shape_id` | int; the id allocator's next value. Forcing it to 999 on Bandit.mohoproj's 21 meshes left frame 25 byte-identical. `EDITABLE` (docs/moho-field-probes.md). | no |
| `curve_interpretation` | int: `1` on 4,912 of 4,969 corpus meshes (76-document scan), `0` on 57 — mostly `DarkMan.mohoproj` (52), plus one each in 4 `Others/*.animeproj` files. Meaning not decoded. Forcing it from 1 to 0 on Bandit.mohoproj's 21 meshes left frame 25 byte-identical. `EDITABLE` (docs/moho-field-probes.md). | no |

### 7.2 Mesh points

| Field | Shape | Observed | Used? |
|---|---|---|---|
| `position` | `Vec2` channel | animated on 14 points | **yes** |
| `width` | `Val` channel | `1.0` on 12,797 points; also `0.34`, `0.32`, `0.14`, `0.0`, `0.46`, `0.2`, `0.26`, … | **yes** — per-point stroke width ([§ 7.6](#76-stroke-width), [§ 7.7](#77-tapered-strokes)) |
| `curves` | list of ints | indices of the curves through this point | no (the reverse mapping is rebuilt from `curves`) |
| `parent` | int | point-level parenting — a bone index this ONE point follows rigidly, overriding the layer's own binding; `-2`/`-1` = no override (the common case). Real on ~4,000 points over 119 meshes across the 19-file corpus, e.g. `Bandit.mohoproj`'s `Leg_F` (9 of 28 points → bone 11) and `Ears` (all 20 → 5 different bones) | **detected, applied only behind `--point-bones` (off by default)** — see `Exporter._geometry_and_mapper`. Ignored by default: the point still goes through the layer's own flexible region blend as if unbound. An older measurement called honouring it much worse; re-measured against the same reference frames (two different metrics) it is an improvement or a wash, never worse — contradiction recorded, not resolved, in that method's own docstring |
| `colored` | bool | **Corrected (M1.4a):** an earlier revision of this row said "false on all 52,748 points (19-file total)" — a 76-document scan found `true` on 156 of 182,522 points, concentrated in the `Snow-girl/Snow-girl-cut*.mohoproj` files (27 of them in `-cut10.mohoproj` alone). | `EDITABLE`, and it matters: forcing it `false` on `Snow-girl-cut10.mohoproj`'s own 4,785 occurrences (its real true sites among them) AFFECTS RENDER at frame 0 (docs/moho-field-probes.md) |
| `color` | `Color` channel | per-point vertex colour | no — inert while `colored` is `false`, but genuinely live once it is not (see above) |
| `color_strength` | `Val` channel | **Corrected (M1.4a):** not "1.0 everywhere" — a 76-document scan of every stored `val` found 9 distinct values: `1.0` on 182,447 of 182,554 stored keyframe values (182,522 sites - a few animated with more than one keyframe), but also `1.061314` (46), `1.157664` (23), `0.5` (20), `0.2` (8) and four smaller counts. | `EDITABLE` — forcing it to `0.3` on Bandit.mohoproj's 396 occurrences (all stored 1.0) left frame 25 byte-identical (docs/moho-field-probes.md) |
| `opacity` | `Val` channel | present on 15,173 points across 10 of 76 corpus documents (`1045`-era only, Bandit.mohoproj among them), constant `1.0` in every one | `EDITABLE` — forcing it to `0.3` on Bandit.mohoproj's 396 occurrences left frame 25 byte-identical (docs/moho-field-probes.md); distinct from the unrelated SVG `opacity` presentation attribute svg2moho.py reads on input elements (a name collision only) |
| `color_drift` | `Val` channel | present on the same 15,173 points/10 documents as `opacity` above, constant `0.0` in every one | `EDITABLE` — forcing it to `0.5` on Bandit.mohoproj's 396 occurrences left frame 25 byte-identical (docs/moho-field-probes.md) |
| `selected` | bool | editor state | no |

Per-point colouring is therefore **present in the format and exercised by a
real corner of the corpus** — `colored` is true on 156 of 182,522 points
(13 documents, all `Snow-girl-cut*.mohoproj`), and forcing it off where it is
genuinely on changes the render, so ignoring `color`/`color_strength` costs
nothing on the other 63 documents but is a real, measured gap on this one
family of files. (An earlier revision of this section, based on the smaller
19-file sample, said `colored` was false everywhere — a sample-size artefact,
not a corpus-wide fact.)

### 7.3 Curves and curve points

A `curve` is a sequence of curve points, each referencing one mesh point by
index. A curve is `closed` (one segment per point, last wraps to first) or
open (one fewer segment than points).

| Curve field | Observed | Used? |
|---|---|---|
| `points` | list of curve points (below) | **yes** |
| `closed` | bool | **yes** |
| `num_points` | int, matches `len(points)` | no (redundant) |
| `start_percent` / `end_percent` | `Val` channels; `start_percent` is `-0.1` on all 3,045 curves (19-file total); `end_percent` is `1.1` on all but 3, which are `1.008296`; **24 curves in `FoxAndGhost.animeproj` carry `0.9721`** | **yes, for a plain stroke** — Moho's "Stroke Exposure", trimming the OUTLINE by a fraction of the curve's ARC LENGTH (the fill is never trimmed), with a value outside `[0, 1]` meaning untrimmed. Measured against a purpose-made Moho render — see [`moho-rigging-and-deformation.md` § 6.3](moho-rigging-and-deformation.md#63-curve-trimming-start_percent--end_percent). A brush-textured or tapered outline warns instead. |
| `profile_layer_uuid`, `profile_curve_id`, `profile_repeat`, `profile_offset` | mostly `""`, `-1`, `16`, `0.0` | a "curve profile" that repeats another curve's shape along this one. **Corrected (M1.4a):** an earlier revision of this row said "unset in all samples" — a 76-document scan found the feature genuinely active in `Gathered-01Intro2.mohoproj`/`Gathered-02Wire2.mohoproj`: a real UUID on 14 of 26,771 `profile_layer_uuid` occurrences (7 in each of the two documents) and `profile_curve_id = 0` (not `-1`) on 44 of 26,771 (22 in each) — of Gathered-01Intro2.mohoproj's 22 `profile_curve_id = 0` curves, exactly 7 also carry the real UUID (confirmed by a direct per-curve check), so the two fields overlap on part, not all, of that 22-curve set. `profile_repeat` stays constant `16` even there. Now all four `EDITABLE`: on `Gathered-01Intro2.mohoproj` (frame 0, feature genuinely active), clearing `profile_layer_uuid` to `""`, forcing `profile_curve_id` to `-1`, and forcing `profile_repeat` to `4` each AFFECTS RENDER (docs/moho-field-probes.md); `profile_offset` lives in a DIFFERENT set of 10 "newer-generation" documents that never co-occur with an active profile (Bandit.mohoproj is one) — forcing it to `0.5` there left frame 25 byte-identical, a precondition-gated negative like `transforms.following` elsewhere in this document, not a corpus-wide claim. |

Curve point fields — all seven, all used:

| Field | Shape | Meaning |
|---|---|---|
| `point` | int | Index into `mesh.points`. |
| `smoothness` | `Val` channel | Curvature; `0` = sharp corner (handles collapse onto the point). |
| `weight_in` / `weight_out` | `Val` channels | How far each handle reaches toward its neighbour, as a fraction of the distance to it. |
| `offset_in` / `offset_out` | `Val` channels | A small rotation (radians) producing asymmetric curves. |
| `segments_on` | bool | `false` on 583 of 53,027 curve points (19-file totals). `false` means the segment leaving this point is **not drawn** — the path breaks into a fresh subpath. |

**In the `1021` format generation, `weight_in`/`weight_out`/`offset_in`/
`offset_out` are absent entirely** (19-file finding). Every one of
`Rabbit.animeproj`'s 305 curve points has exactly
`{point, smoothness, segments_on}` and nothing else, while every `1038`/`1045`
curve point has all seven fields (12,500 curve points checked). This is
presumably a simpler, symmetric-handle-only curve representation predating the
asymmetric weight/offset feature.

This used to be a **hard failure to load**: `CurvePoint._build` read the four
fields with plain dict indexing, so `Rabbit.animeproj` raised
`KeyError: 'weight_in'` and no layer of it could be exported at all.
`CurvePoint._build` now reads them with `.get()` and falls back to
`CurvePoint.DEFAULT_WEIGHT` (`1.0`) and `CurvePoint.DEFAULT_OFFSET` (`0.0`).
Those two defaults are chosen on two grounds:

- They are **neutral** in `BezierReconstructor.handle`: weight `1.0` reduces
  the handle length to `distance * smoothness`, and offset `0.0` leaves the
  handle direction unrotated. So a `1021` point behaves exactly like the
  symmetric-handle curve it appears to be.
- They are the **mode of the stored data** in the documents that do carry the
  fields: `1.0` on 23.4% of 52,722 weight values and `0.0` on 26.5% of 52,738
  offset values, each the single most common value by a wide margin.

**Not confirmed against a Moho export of a `1021` document** — there is no
Moho-exported reference SVG for `Rabbit.animeproj` (the SVGs under
`out/svg/ori/` are this exporter's own output), so the handle shape this
produces is reasoned, not measured. Confirmed only that the document now
loads and exports every layer
(`python3 moho2svg.py moho/Rabbit.animeproj --list`), and that re-exporting
the sample documents leaves the SVGs byte-identical.

### 7.4 Shapes and `edges`

| Field | Shape | Observed | Used? |
|---|---|---|---|
| `edges` | `{curve: [...], segment: [...], flag: [...]}` | three parallel int arrays, always equal length | **yes** — see [§ 7.9](#79-why-edges-and-shape_order-are-not-trustworthy) |
| `has_fill` / `has_outline` | bool | `(true,true)` 408, `(true,false)` 315, `(false,true)` 236 | **yes** |
| `style` | obj | the shape's own style ([§ 8.2](#82-a-shapes-own-style-and-inheritance)) | **yes** |
| `inherited_style_uuid` / `_name`, `inherited_style2_uuid` / `_name` | str | see [§ 8.2](#82-a-shapes-own-style-and-inheritance) | **yes** |
| `id` | int | shape identity, referenced by `mesh.shape_order` | **yes** |
| `combo_mode` | int | **only present in the `1045` document** (112 shapes): `0`×96, `1`×2, `3`×14 | **yes** — see [§ 7.8](#78-boolean-shape-combination) |
| `effect_scale` / `effect_rotation` | `Val` channels | `1.0`/`0.0` on ~895 shapes, varying on the rest | **yes** — but only to place a gradient |
| `effect_offset` | `Vec2` channel | mostly `{0,0}`, but non-zero on 276 of 22,144 occurrences across 30 of the 76-document corpus (**corrected, M1.3** — an earlier revision of this row claimed nothing observed supplies a non-zero value) | not read by `moho2svg.py`, but confirmed to move pixels in real Moho — see [§ 8.4](#84-gradients) |
| `fill_allowed` | bool | `true` 1,801, `false` 859 (19-file totals) | no — presumably "this shape may be filled at all", distinct from `has_fill`; forcing it `false` everywhere on Bandit.mohoproj (a mix of stored `true`/`false`, not a no-op) left the render byte-identical, including on shapes with `has_fill = true` (M1.3 probe) |
| `combo_blend_anim` | `Val` channel | `0.0`, `1045` only | no — presumably animates a soft boolean blend; forcing it to `0.7` on Bandit.mohoproj was inert (M1.3 probe) |
| `3d_thickness` | `Val` channel | `0.125` on all 2,660 shapes (19-file total) | no |
| `name` | str | `""` or `"S1"`, `"S2"`, … | no |
| `selected` | bool | editor state | no |

### 7.5 Bezier reconstruction

A curve point does not store explicit Bezier control points; they are
reconstructed from `smoothness`, `weight_in`/`weight_out`, and
`offset_in`/`offset_out`.

Handle **length** is `distance_to_neighbour * smoothness * weight` (confirmed
exact against 209 reference handles). Handle **direction** is *not* simply
`normalize(next - prev)` — it is a chord-length-weighted blend of the two
neighbouring chord vectors (see the module docstring's BEZIER CURVES section
for the exact formula and its empirical derivation).

### 7.6 Stroke width

Two independent, non-pixel quantities scale a stroke:

- `line_width` — a per-shape/style value (a handful of quantised values per
  document; 33 distinct values across the 19-file sample, from `0.001389`
  to `0.092223` (widened from the original 5-file sample's 11 values,
  `0.002778`–`0.092223` — **19-file finding**). It is a **plain float, not a channel** — Moho does not
  animate it.
- point `width` — normally `1.0`, but can vary per point.

```
stroke_px = line_width * point_width * canvas_height * layer_chain_scale
```

`layer_chain_scale` is the accumulated ancestor scale, **excluding** bone
deformation (confirmed: including it inflates the apparent scale by ~11% on a
walk cycle).

### 7.7 Tapered strokes

Where a shape's points do not all share one `width`, Moho's own exporter does
not use a variable `<path stroke-width>` (SVG cannot express one) — it walks
the stroke and emits the literal filled outline instead, visible as dozens of
tiny filled paths for something like a bushy tail. The samples exercise this
heavily: 7,470 of 52,748 mesh points (19-file total) have a `width` other than `1.0`. See the
module docstring's TAPERED STROKES section.

### 7.8 Boolean shape combination

`combo_mode` says how a shape combines with the shape(s) immediately before
it in the same layer. It is **absent from all four `1038` documents** and
present on all 112 shapes of the `1045` one — treat a missing `combo_mode` as
`0`.

| `combo_mode` | Count here | Meaning |
|---|---|---|
| `0` | 96 | Normal — starts a new independent boolean group. |
| `1` | 2 | Union — merged into the current group; the shared boundary disappears, and the *combined* outline is stroked using the group's first (base) member's styling, not its own. |
| `3` | 14 | Intersect — clipped to the union of the group's solid members so far. |
| `2` | **0** | Subtract — the member draws nothing of its own; its fill region punches a hole through whatever is drawn BELOW it in the group (fill AND stroke), never a member drawn on top of it. Not present in any of these 19 documents — decoded from a direct observation in Moho App (2026-08-17); order-dependence was CONFIRMED the same way. Still implemented but UNVERIFIED against a machine-readable reference on one remaining question, edge exactness (see the module docstring's BOOLEAN SHAPE COMBINATIONS section). |

**A `combo_mode == 3` (intersect) member's own outline no longer shows a real
gap that Moho does not draw.** `moho2svg.py` implements `combo_mode` by
clipping a member's own stroke to the base member's fill via an SVG
`<mask>` — an approximation of the boolean operation, not a true geometric
path intersection (stated plainly in the module docstring). This used to
break down for a `segments_on == false` curve segment that is genuinely
*unique* geometry (not, as in the `combo_mode == 1` case, a boundary shared
with — and already drawn by — another group member). Confirmed on Bandit's
`Eye_Upper`/`S3` (a `combo_mode == 3` upper-eyelid shape): one segment of its
curve has `segments_on == false`, and that segment's own endpoints do not
coincide with any segment of the base shape `S1`'s boundary at all (checked
directly — the two curves occupy entirely different coordinates). Real Moho
most likely computes an actual new boundary edge at the point where `S3`'s
curve crosses `S1`'s, and marks that original `S3` segment
`segments_on == false` because a computed edge has *replaced* it.

Rather than reconstructing that edge (real Bezier–Bezier intersection — a
different class of algorithm from anything else in this tool), the fix
sidesteps needing it: for a `combo_mode == 3` member specifically,
`_render_shape` now builds the stroke with `visible_only=False` — i.e. it
draws the member's full original closed outline rather than dropping the
hidden segment. The existing intersect-clip (`_mask_union`, unchanged) then
cuts that full outline down to within the base shape's fill exactly as
before — and because SVG's own clipping computes the true geometric
crossing point when the mask is rasterised, the visible result comes out
correct without this tool ever computing a Bezier intersection itself.
Confirmed: `Eye_Upper`'s `S3_line` is now one continuous subpath (previously
two, split by an `M`), and the gap is gone. This only touches shapes that are
BOTH `combo_mode == 3` AND have a `segments_on == false` segment — checked
across all five reference documents, `Eye_Upper`/`S3` is the **only** one, so
nothing else could have regressed. Whether an intersect member can ever
legitimately want its own artist-drawn gap (which this fix would now
incorrectly restore) remains unconfirmed — no such example has been found,
but only one `combo_mode == 3`-with-a-gap reference exists in total. See the
module docstring's BOOLEAN SHAPE COMBINATIONS section.

### 7.9 Why `edges` and `shape_order` are not trustworthy

A shape's `edges` list is not reliably a walk in list order, and its `flag` is
not a reliable direction bit (observed: `flag` `0` on 15,477 edges, `1` on
872, with real files where segment order is strictly descending and `flag` is
`0` throughout, and where a curve's segments are listed out of walk order).
`edges` must be treated as an *unordered set* of segments and re-traced as an
undirected graph, which is what `PathTracer` does.

`mesh.shape_order` is similarly misleading: it is a `"|"`-joined ascending
registry of `shape.id` values, not a z-order. The real z-order (back to
front) is the order shapes already appear in `mesh.shapes`. `moho2svg.py`
does not read `shape_order` at all.

### 7.10 Point groups (`mesh.groups`)

`mesh.groups` is a list of `{"type": "PointGroup", "name": ..., "points":
[indices into mesh.points]}`. 14 point-group objects exist across the
19-file sample — the same 7-name set (`"Right Hand"` twice, `"Left Laces"`,
`"Right Laces"`, `"top lip"`, `"bottom lip"`, `"bottom Teeth"`), duplicated
identically across `ReparentBone.animeproj` and
`SelectandReparentBoneTool.animeproj` (two very similar tutorial rigs).

These are an editor convenience for selecting points. **They are not the same
namespace as `flexi_bone_subset`**, which holds bone indices
([§ 6.2](#62-common-fields-that-affect-rendering-and-are-used)). Nothing in
the samples references a point group, and this tool ignores them.

---

## 8. Styles

### 8.1 Named styles (`doc.styles`)

`doc.styles` is a flat list of named style objects, referenced by shapes via
uuid or name:

```jsonc
{
  "type": "Style", "name": "yanak", "uuid": "...",
  "define_fill_color": true,  "fill_color": { ...Color channel... },
  "define_line_col":   true,  "line_color": { ...Color channel... },
  "define_line_width": true,  "line_width": 0.005556,
  "line_caps": 1,
  "brush_name": "Brush502.png", "brush_jitter": 6.283185, "brush_spacing": 0.25,
  "brush_align": false, "brush_tint": true,
  "fill_style": { "type": "SS_Gradient2", "gradient_type": 1, "gradients": [...] }
}
```

Every field observed on a named style:

| Field | Type | Observed values | Used? |
|---|---|---|---|
| `type` | str | `"Style"` always | no |
| `name`, `uuid` | str | lookup keys | **yes** |
| `define_fill_color`, `define_line_col`, `define_line_width` | bool | true/false | **yes** — see [§ 8.2](#82-a-shapes-own-style-and-inheritance) |
| `fill_color`, `line_color` | `Color` channels | — | **yes** |
| `line_width` | float (not a channel) | 11 distinct values | **yes** |
| `line_caps` | int | `5,659`×`1` (round), `765`×`0` (butt) across 6,424 style objects (19-file totals) | **yes** — `0` butt, `1` round, `2` square (mapping from `LINE_CAP_NAMES`). The original 5-file sample saw only `1`; **`0` is a 19-file finding** (`IndependentAngle`, `MaximumIKStrethching`, `TargetBone` each have 255 styles with `line_caps: 0`) — confirmed exercised in the broader sample, so a butt-cap style now genuinely differs from what this tool draws if `LINE_CAP_NAMES`' `0` mapping is wrong (unverified against Moho for that value). |
| `fill_style` | obj | 1,812 across the 46-file sample: 1,401 `SS_Gradient2`, 198 `SS_Halo`, 96 `SS_Shaded`, 91 `SS_Soft`, 26 `SS_Crayon` | **partly** — gradient fill ([§ 8.4](#84-gradients)) only; every other variant warns and draws flat. See [§ 8.3](#83-style-effect-variants-46-file-finding): `fill_style` is not always a gradient. |
| `line_style` | obj | 177 across the 46-file sample: 116 `SS_Gradient2`, 40 `SS_Soft`, 18 `SS_Shaded`, 3 `SS_Shadow` | **partly** — the slot is now read (it used to be ignored outright). `SS_Gradient2` becomes a real paint server on the outline; the rest warn and draw a flat stroke. |
| `fill_style_id`, `line_style_id`, `fill_style2_id` | int | `0`, `2`, `4`, `9`, `10`, `11`, `12` | n/a — **decoded**: each is simply the effect KIND, agreeing with the sibling effect object's own `type` in all 2,003 instances. Not the "arbitrary internal reference id" earlier revisions assumed. ([§ 8.3](#83-style-effect-variants-46-file-finding)) |
| `fill_style2` | obj | 14 across the 46-file sample: 12 `SS_Texture2` (3 files), 2 `SS_Soft` (`DarkMan.mohoproj`) | no — a *second* fill-effect slot layered on top of `fill_style`; warns per shape. |
| `brush_name` | str | 20+ distinct values | **yes** ([§ 8.6](#86-resolving-a-brush_name-to-a-file)) |
| `brush_jitter` | float (radians) | `0.0`–`6.283185` | **yes** |
| `brush_spacing` | float (fraction of dab diameter) | `0.0`–`0.7` | **yes** |
| `brush_align` | bool | true/false | **yes** |
| `brush_tint` | bool | `true` on all 771 | **yes** |
| `brush_randomize` | bool | true/false | no |
| `brush_rand_order` | bool | true/false | no |
| `brush_merged_alpha` | bool | true/false | no |
| `brush_angle_drift` | float | `0.0`, `0.261799`, `0.349066`, `1.745329` | no |
| `brush_size_amp`, `brush_size_scale` | float | on 12 styles (`1045` only) | no |
| `brush_random_interval` | int | `1`, on 12 styles | no |
| `brush_hue_drift`, `brush_sat_drift`, `brush_val_drift` | float | `0.0`, on 12 styles | no |

> **Accuracy note.** The module docstring states that `brush_angle_drift`,
> `brush_randomize`, `brush_merged_alpha`, and `brush_rand_order` "are read
> from the style but not implemented". In the current code they are **not read
> at all** — `ResolvedStyle.resolve` copies only `brush_name`,
> `brush_jitter`, `brush_spacing`, `brush_align`, and `brush_tint`, and no
> other brush field name appears anywhere in `moho2svg.py`. The equivalent
> library-level defaults `randomOrder` / `randomInterval` *are* read, but from
> the `.mohobrush` archive ([§ 8.6](#86-resolving-a-brush_name-to-a-file)),
> not from the style. Effect on output is nil either way.

### 8.2 A shape's own `style` and inheritance

A shape's own `style` object has the same field set as a named style. The
inheritance references (`inherited_style_uuid` / `inherited_style_name` /
`inherited_style2_uuid` / `inherited_style2_name`) appear **either on the
shape itself or inside its own `style` object** — both are observed in real
files, so both are checked.

**Resolution rule.** The shape's own `style` values are the base. Then, for
each referenced named style, and for each of the three `define_X` flags that
is **true on the named style** and **false on the shape's own style**, the
named style's value overrides the base. Style 1 is applied before style 2, so
style 2 wins where both define the same attribute — this is how an
outline-only "line style" is layered on top of a base fill style. A gradient
(`fill_style`), `line_caps`, and the brush fields ride along on the same
flags.

Note the asymmetry: a `define_X` flag being **false on the shape** does not
blank the shape's own value — it only makes the shape *overridable*. That is
why the `1045` document works at all: all 112 of its shapes have every
`define_*` flag false and no inherited style, so their own values are used
verbatim.

The two generations use the mechanism very differently:

| | `1038` documents | `1045` document |
|---|---|---|
| Named styles that set `define_*` | 100% (all 759) | **0% (0 of 12)** |
| Shapes with an `inherited_style*` reference | 557 of 847 | 0 of 112 |
| Where the real values live | in the named style | on the shape's own `style` |
| Named styles carrying `fill_style` | 256 | 0 |

So: **older documents drive everything through the named style list; the
newer document barely uses it.** A tool that only handled one generation
would silently produce colourless output on the other.

### 8.3 Style effect variants (46-file finding)

`fill_style`, `fill_style2`, and `line_style` each hold an *effect object*
with its own `type`. The original 5-file sample only ever saw
`SS_Gradient2`, which made "these fields mean a gradient" look like a safe
rule — it is not. The 46-file sample shows **seven** distinct effect types.
Two of them (`SS_Halo`, `SS_Shaded`) were missing from this document and from
`schema/` entirely until the 46-file pass, and the earlier claim that the
fill and line variant sets are "disjoint except for `SS_Gradient2`" is also
withdrawn: `SS_Soft` and `SS_Shaded` each occur in both slots.

Counts below are **effect objects in the file** (a named style's effect is
counted once, however many shapes inherit it). The "drawn shapes" column
counts the shapes that actually reach the effect — i.e. that resolve to it
*and* have the corresponding `has_fill`/`has_outline` set — which is the
number that matters for how much of the picture is wrong.

| Effect `type` | `*_style_id` | Slot | Objects | Drawn shapes | Manual | Rendered? |
|---|---|---|---|---|---|---|
| `SS_Gradient2` | 9 | `fill_style` | 1,401 | 249 | Gradient Fill (13.02) | **yes** ([§ 8.4](#84-gradients)) |
| `SS_Gradient2` | 9 | `line_style` | 116 | 6 | — | **yes**, but every one of those 6 is a brush stroke, which the gradient cannot reach — see below |
| `SS_Halo` | 4 | `fill_style` | 198 | 198 | Halo Fill (13.02) | no — **the largest single appearance gap** |
| `SS_Shaded` | 0 | `fill_style` / `line_style` | 96 / 18 | 94 / 12 | Shaded Fill (13.02) | no |
| `SS_Soft` | 2 | `fill_style` / `line_style` / `fill_style2` | 91 / 40 / 2 | 91 / 31 / 2 | Soft Edge Fill (13.02) | no |
| `SS_Crayon` | 12 | `fill_style` | 26 | 7 | — | no — falls back to the shape's flat `fill_color` |
| `SS_Texture2` | 10 | `fill_style2` | 12 | 12 | — | no — in all 12 occurrences both path fields are empty, so no sampled document resolves a texture file |
| `SS_Shadow` | 11 | `line_style` | 3 | 3 | — | no — a per-shape drop shadow on the stroke, distinct from `SS_Shaded` and from the layer-level `layer_shadow` in [§ 6.3](#63-common-fields-that-affect-rendering-and-are-not-used) |

**`*_style_id` is decoded, and — for `fill_style_id` — confirmed NOT
redundant to Moho's own renderer (M1.3).** Each slot has a parallel integer
field (`fill_style_id`, `line_style_id`, `fill_style2_id`) whose value is
simply the effect *kind*, per the second column above. It agrees with the
effect object's own `type` string in **all 2,003 instances across the 46
files, with no exceptions**, so no sampled document ever has the two
disagree. But that is not the same as Moho *ignoring* this field: probing
`fill_style_id` on `SketchBone.animeproj` — forcing every occurrence from its
stored `9` (`SS_Gradient2`) to `4` (`SS_Halo`), with `type` and every other
style field left untouched — changed the frame-0 render. Moho reads this
integer separately from `type` to decide how to draw the effect, at least in
some circumstances; which one wins when a real (non-probe) document manages
to make them disagree is not established, since none does. `line_style_id`
and `fill_style2_id` were not probed (out of scope for M1.3 — see
`schema/style.schema.json`), so whether the same holds for those two slots is
untested.

**Where effects live.** Both on named styles and inline on a shape's own
`style` object — 1,160 vs 652 `fill_style` objects respectively. This was
already known for `SS_Crayon`; it holds for gradients too (241 of the inline
ones are `SS_Gradient2`), which retires the old "a gradient only ever lives on
a named style" rule for good. `line_style` is the exception that still holds:
all 116 sit on named styles, none inline.

**What is actually rendered now.** `line_style` used to be read by nothing at
all, so a gradient/soft/shaded outline painted flat with no warning. It is now
resolved, `SS_Gradient2` becomes a real SVG paint server on the outline, and
every other variant — in any of the three slots — emits a per-shape stderr
warning instead of failing silently. The one thing a gradient outline still
cannot do is style a *brush* stroke, which tints image pixels rather than
painting with a paint server; that also warns.

**A reference SVG cannot check any of this.** Moho's own SVG export drops the
blurred/composited effects. Its export of `Snow-girl-cut51.mohoproj` — a
document with **108 halo-filled shapes and 13 blend-mode layers** — contains
355 `<path>` elements and 106 `opacity` attributes but **zero
`filter`/`feGaussianBlur` and zero `mix-blend-mode`**; a halo is a blurred
coloured rim, which no arrangement of paths and opacity can express. Moho's
PNG render of the same frame shows both. (This is specific to the
blurred/composited effects — that same SVG exporter *does* emit gradients in
general: its export of `WhatIsBone.animeproj` contains 96 of them.) Any future
work on effects or blend modes has to be validated against a **raster** render,
e.g. `Moho -r FILE -f PNG -start N -end N -o OUT.png`.

Full per-field descriptions: `schema/style.schema.json`'s `Gradient`, `Crayon`,
`SoftStyle`, `Halo`, `Shaded`, `ShadowStyle`, `Texture2`.

### 8.4 Gradients

`fill_style` and `line_style` can both have this shape — `SS_Gradient2`, one
of the seven effect variants from
[§ 8.3](#83-style-effect-variants-46-file-finding), and the only one either
exporter renders:

```jsonc
{
  "type": "SS_Gradient2",
  "gradient_type": 1,          // 0 = linear (84 seen), 1 = radial (197 seen)
  "through_alpha": false,      // not used
  "gradients": [
    { "location": { ...Val channel... },   // stop position, 0.0-1.0
      "color":    { ...Color channel... } },
    ...
  ]
}
```

Both the stop position and the stop colour are full channels, so a gradient
can animate. `moho2svg.py` reads `gradient_type`, `gradients[].location`, and
`gradients[].color`; it ignores `through_alpha` and rejects any `type` other
than `"SS_Gradient2"` with a warning.

A shape opts into a gradient fill by leaving `define_fill_color` false and
inheriting a style that carries `fill_style`. Placement (centre and radius)
is derived from the shape's bounding box, scaled and rotated by the shape's
own `effect_scale` / `effect_rotation`, and offset by `effect_offset`, a
`Vec2` channel on the *shape* (`mesh.schema.json`, not this style object) —
**approximate, not pixel-matched** to Moho's own differently-parameterised
placement.

**`effect_offset` is a real, currently-unread gradient offset (M1.3
correction).** An earlier revision of this document claimed nothing observed
ever supplies a non-zero value; a 76-document corpus scan contradicts that —
30 of the 76 documents carry a non-zero `effect_offset` somewhere, 276 of
22,144 total occurrences, with the corpus-wide maximum `{x: 0.020666, y:
1.386204}` in `Snow-girl/Snow-girl-cut10.mohoproj` (a real animated `Vec2`
channel keyframe there — a different document from the one this milestone
probed). It is not one of the fields `Shape.__init__`
extracts by name (dropped along with `fill_allowed`/`combo_blend_anim`/
`selected`/`3d_thickness`/the inherited-style pair — see that class's own
docstring), so `moho2svg.py` never applies it, but forcing it to `{x: 0.3, y:
0.3}` on every occurrence in `SketchBone.animeproj` (a document with real
gradient fills to move, unlike `Bandit.mohoproj`, though not the corpus's
largest stored value — see above) visibly moved the gradient at frame 0 in
real Moho.

**`through_alpha` (this owner) is confirmed inert, at least on this
document.** Declared `false` on every one of `SketchBone.animeproj`'s 83
`SS_Gradient2` occurrences; forcing all of them to `true` left frame 0
byte-identical. `Texture2`'s own `through_alpha` (`schema/style.schema.json`)
shares the flat field name but is a genuinely different owner — real files
carry the key under both `SS_Gradient2` and `SS_Texture2` objects — and has
no writer in either exporter, so it was not probed and stays a separate,
unresolved question (M1.3; see that schema entry).

**`fill_allowed` and `combo_blend_anim` (Shape-level, [§ 7.4](#74-shapes-and-edges))
were also probed as part of this pass and found inert on `Bandit.mohoproj`** —
see that table's own notes.

### 8.5 Brush styles

A named style's line can be a textured "brush" — a small image stamped
repeatedly along the path (jittered in rotation, spaced as a fraction of its
own size) instead of a plain uniform-width line.

- `brush_name` — identifies the brush asset ([§ 8.6](#86-resolving-a-brush_name-to-a-file)).
- `brush_jitter` — random rotation spread, in **radians**, applied per dab.
- `brush_spacing` — dab spacing, as a **fraction of the dab's own diameter**.
- `brush_align` — whether each dab rotates to the local path tangent (in
  addition to the random jitter) or ignores path direction entirely.
- `brush_tint` — whether the (greyscale) texture is recoloured to the
  resolved `line_color`, or used with its own native multi-colour pixels
  as-is. `true` in every style in every sample.

Moho's own per-dab randomisation is not recoverable from the saved document,
so this tool seeds its jitter deterministically per shape instead. See the
module docstring's BRUSH STROKES section, and `docs/moho-exporting-svg.md` § 7 for
the three render paths and their performance.

**Ten more brush fields, all confirmed inert on the one document tested
(M1.3).** Alongside `brush_name`/`brush_jitter`/`brush_spacing`/
`brush_align`/`brush_tint` above, a real style also carries
`brush_randomize`, `brush_rand_order`, `brush_merged_alpha`,
`brush_angle_drift`, `brush_random_interval`, `brush_size_amp`,
`brush_size_scale`, `brush_hue_drift`, `brush_sat_drift`, and
`brush_val_drift` — plain values, never channels, same as the five above.
Each was forced to a differing value on all 124 occurrences in
`Bandit.mohoproj` (a document with real, non-empty `brush_name` textures on
the touched shapes, so this is not an untested no-brush frame) and rendered
frame 25 byte-identical to the original in every case, including
`brush_size_amp` retried with `brush_randomize=true` set as an explicit
precondition (in case the per-dab size variance it presumably scales is
gated behind that switch — still inert). None of these ten is read by either
`moho2svg.py` or `moho2lottie.py` (comment-only mentions in
`moho2svg.py`'s own module docstring and a size-variation note near
`Exporter._brush_library_defaults`, never an actual field access) — see
`schema/style.schema.json`'s own entries and `docs/moho-field-probes.md` for
the full probe rows. This result is document-scoped, not a corpus-wide claim
that Moho itself never applies these fields under any brush/configuration —
only that this one set of real brush strokes did not visibly react to any of
them.

### 8.6 Resolving a `brush_name` to a file

Moho ships its own brush assets as files installed alongside the application,
not inside any project file. A brush asset takes one of three shapes on disk:

1. **A single PNG** named exactly after the brush (`Brush502.png`).
2. **A multi-frame brush**: a *folder* named exactly after the brush (e.g.
   `CK Ink Painty Brush/Painty Brush_00001.png` … `_00012.png`), with a
   sibling `<name>.mohobrush` file.

   Despite the extension, a `.mohobrush` file is a **ZIP archive**, not an
   image or a bespoke binary format — confirmed by extracting and parsing all
   101 shipped with a real Moho install, zero exceptions. It contains exactly
   one member, `brush.json`, a plain JSON object with the brush library's own
   default parameters: `version`, `align`, `jitter`, `spacing`, `angleDrift`,
   `randomize`, `randomOrder`, `mergedAlpha`, `sizeVariationAmp`,
   `sizeVariationScale`, `randomInterval`, `brushFiles` (a list of
   `{"brushFileRef": {"relativeTo": "Project", "path": "<asset name>"}}` — an
   authoritative pointer to the actual PNG/folder asset, an alternative to
   guessing it from the name as this section does), and sometimes
   `hueDrift`/`satDrift`/`valDrift`. This tool reads only `randomOrder` and
   `randomInterval` from it (whether each dab picks a uniformly-random frame
   from the folder, or cycles through them in sorted-file-name order,
   advancing every `randomInterval` dabs) — see
   `Exporter._brush_library_defaults`.
3. **A preset image one folder deep** — some older documents' `brush_name`
   values only resolve to a file living inside another brush's own folder
   (e.g. `Brush549_1_50_50.png` exists on disk only as
   `Brush004/Brush549_1_50_50.png`).

Additionally, **older Moho versions bake preset parameters into the
`brush_name` string itself** as a trailing `_N_N_...` numeric suffix — the
literal file on disk does not include the suffix. For example
`Brush567_0_20_50.png` names the file `Brush567.png`; `CK Ink
Natural_2_1_0_0_0_0_0_0_0` names the folder `CK Ink Natural`. Some values also
carry the `.mohobrush` extension directly (`Brush503.mohobrush`). Resolving a
`brush_name` therefore means trying, in order: the exact name as a file, the
exact name as a folder, a recursive search for the exact filename one or more
folders deep, and then the same three searches again after stripping one
trailing `_<digits>` group at a time from the name (re-appending a stripped
`.png` extension where relevant) until something matches.

Across every suffixed style seen so far, the **second and third** numbers of
the suffix consistently match that style's own `brush_jitter` (in degrees) and
`brush_spacing` (as a percent) — i.e. they are redundant with fields the style
already carries explicitly, and this tool reads the explicit fields, not the
suffix, for actual rendering. The suffix is used only to *locate* the asset
file. The **first** number's meaning differs by brush family (it lines up with
the align flag for the `Brush5xx` preset family, but not consistently for
others) and is not decoded.

---

## 9. Bones and skinning

> This section is the short version. The full bone-field reference, the
> skinning math, the constraint/IK/control-bone/dynamics family, Smart Warp,
> and the mesh-level deformation fields are in
> [`moho-rigging-and-deformation.md`](moho-rigging-and-deformation.md).

A `BoneLayer`'s `skeleton.bones` is a flat list of 0–157 bones. A bone's
world transform composes with its parent's, with parents resolved regardless
of list order.

Fields used by this tool:

| Field | Shape | Meaning |
|---|---|---|
| `name` | str | Bone name. Also how a Smart Bone dial is matched ([§ 11](#11-actions-and-smart-bones)). |
| `parent` | int | Index into the same `bones` list, or `-1` for a root. |
| `length` | float | Bone length in document units (`0.003117`–`0.981441` observed, 19-file total; original 5-file sample saw `0.015`–`0.6`). |
| `strength` | float | Influence radius for flexible binding (`0.0`–`7.654676` observed, 19-file total — considerably wider than the original 5-file sample's `0.0`–`0.6`; `0.0` on some bones means no influence). |
| `anim_pos` | `Vec2` channel | Animated position, relative to the parent bone. |
| `anim_angle` | `Val` channel | Animated angle in radians. The most-animated channel in the samples after `pose` (383 of 850 bones keyframed, 19-file total). |
| `anim_scale` | `Val` channel | Animated scale along the bone. |

Deformation of a mesh layer is one of two modes, decided **per layer**:

- **Rigid** (`parent_bone >= 0`): every point moves exactly as that one bone
  does. 54 of 842 layers (19-file total).
- **Flexible / region** (`parent_bone == -1`): every point is a
  distance-weighted blend of every bone's transform, or of a named subset's
  (`flexi_bone_subset`, a `"|"`-joined list of bone indices). **779** of 842
  layers (19-file total). A further 9 layers use `parent_bone == -3` — see
  [§ 6.2](#62-common-fields-that-affect-rendering-and-are-used) — which this
  tool also falls through to flexible handling for, unconfirmed against real
  Moho output.

  **Two layer populations, two sets of counts.** The numbers here count the
  842 layers in the `layers` tree. [§ 6.2](#62-common-fields-that-affect-rendering-and-are-used)
  counts 876, because it also includes the `MeshLayer` nested inside each of
  the 34 `TextLayer`s; all 34 are `-1`, which is exactly the 813 − 779
  difference. Both counts are correct — check which population a number
  refers to before comparing. The weight falloff shape (inverse-distance-squared by default) is a
  heuristic, unvalidated for cases where more than one bone has significant
  influence near a given point.

A mesh several groups deep inside a `BoneLayer` is deformed in *that bone
layer's own coordinate space* — i.e. after the local transforms of everything
between it and the bone layer, but before the bone layer's own transform.

Bone fields **not** used, grouped by what they would change:

- **Reparenting over time**: `anim_parent`, a `Val` channel whose values are
  bone indices (or `-1`). This is the storage for Moho's Reparent Bone tool,
  which lets a bone change parent mid-animation. This tool uses the static
  `parent` index instead, so a frame after a reparent keyframe would attach
  the bone to the wrong parent.

  **Ignoring it is currently free, and measurably so.** All 850
  `anim_parent` channels (19-file total) have exactly **one** keyframe, and
  that single value equals the bone's own static `parent` in **850 of 850**
  cases — zero
  mismatches. That holds even in `ReparentBone.animeproj`, which demonstrates
  the *tool* without ever keyframing a reparent. So `anim_parent` is fully
  redundant with `parent` across this whole sample set, and the risk is
  theoretical until a document that actually keyframes it turns up.
- **Constraints and IK** (`fixed_angle` has since been decoded and applied —
  see [`moho-rigging-and-deformation.md` § 3.2](moho-rigging-and-deformation.md#32-independent-angle-fixed_angle)):
  `constraints`, `min_constraint`, `max_constraint`,
  `ik_lock`, `ik_global_angle`, `ik_parent_target`,
  `ignored_by_ik`, `bone_enable_arc_solver`, `target_bone`,
  `angle_control_parent` / `_scale` / `_delay`, `pos_control_parent` /
  `_scale` / `_delay`, `scale_control_parent` / `_scale` / `_delay`. All at
  defaults except `pos_control_parent` (`4`, `5` on a few bones) and the
  `min`/`max_constraint` pairs. Constraints only matter while posing in the
  editor; the resulting angles are already baked into `anim_angle`.
- **Scaling behaviour**: `scaling_mode` (`0` on 586 bones, `2` on 264 — 19-file totals),
  `squash_stretch_scaling` (`0.44` or `1.0`), `max_auto_scaling`. `scaling_mode`
  is not decoded and is a plausible explanation for the intentionally-preserved
  asymmetric bone scale in `Skeleton.world_matrices`.
- **Physics/dynamics**: `bone_dynamics`, `angle_dynamics`, `pos_dynamics`,
  `scale_dynamics`, `wind_dynamics`, `spring_force`, `damping_force`,
  `torque_force`, `physics_*`, and the `pos_`/`scale_` variants of each.
  **Correction: these are *not* all disabled in the samples**, as an earlier
  revision of this document stated. `bone_dynamics` is a `Bool` channel whose
  value is `true` on **115 of the 850 bones**, across 6 documents —
  `WhatIsBone` (52), `Bandit` (28, i.e. every bone in the file), `AddBone`
  (21), `BoneDynamics` (6), `Rabbit` (6), `ControlBones` (2) — and
  `BoneDynamics.animeproj` keyframes it (7 channels with more than one key).
  `angle_dynamics` is `true` on 2 bones in `Bandit.mohoproj`; the `pos_`,
  `scale_` and `wind_` variants are `false` everywhere **in this 19-file
  corpus**. Moho adds the resulting spring motion on top of the keyed pose
  at playback time, so ignoring these fields drops real secondary motion
  (follow-through, overlap) rather than nothing — an **exercised** gap. See
  [`moho-animation-and-transform.md`](moho-animation-and-transform.md) § 6.
  **Correction: `wind_dynamics` is not always false.** `DarkMan.mohoproj`
  (gitignored, user-supplied, outside this corpus) has it `true` on all 91
  of its bones while `bone_dynamics`/`angle_dynamics` stay `false` — the
  first real case of that combination. `moho2svg.py`/`moho2lottie.py` now
  detect this (`Layer.physics_dynamic`) and offer an opt-in `--wind-dynamics`
  attempt at simulating it, reusing `bone_dynamics`' own spring — but that
  attempt is confirmed NOT to reproduce Moho's own damping (see
  `Skeleton.dynamic_angles`' WIND EVIDENCE section), so this remains an
  exercised, still-open gap, not a closed one. A separate, unrelated finding
  from the same investigation: `MeshPoint.parent` (per-point rigid bone
  binding — [§ 7.2](#72-mesh-points)) is read but ignored by default too
  (`--point-bones`), and honouring it measurably helps the exact symptom
  `DarkMan.mohoproj` showed.
- **Editor state**: `hidden`, `shy`, `selected`, `bone_label_showing`,
  `bone_tags`, `angle_weight`, `pos_weight`, `scale_weight`.
- **`flip_h` / `flip_v`** — Bool channels, listed as editor state by an
  earlier revision of this document. **That was wrong**: they mirror
  everything the bone drives, and are now applied by
  `Skeleton.world_matrices` the same way a layer's own flips are (each
  negates one matrix column). Set on exactly one bone in the 19-file sample
  — `SketchBone.animeproj`'s `B23` ankle, `False` → `True` at frame 44 —
  where ignoring them left the `ayak-sol` foot pointing backwards for half
  the walk cycle. See
  [`moho-rigging-and-deformation.md`](moho-rigging-and-deformation.md) § 3.
- **`offset`** — a plain `Vec2`, listed as editor state by an earlier
  revision of this document. **That was wrong**: it is non-zero on 5 bones in
  `OffsetBoneTool.animeproj` (zero on the other 845), where it is roughly the
  negative of the bone's own `anim_pos`. Whether ignoring it is correct
  depends on whether Moho shifts only the bone's drawn position or its real
  base; a constant offset cancels out of `pose · rest⁻¹` either way, so the
  worst case is shifted flexible-binding weights, not a displaced limb. Not
  decoded — see
  [`moho-rigging-and-deformation.md` § 3.7](moho-rigging-and-deformation.md#37-offset-the-offset-bone-tool).

---

## 10. Masking

Two *separate* fields are involved, and both are ENUMs. Both were decoded
twice over and in agreement: by the declaration order of `GROUP_MASK_*` and
`MM_*` in Moho's own scripting header (`Contents/Resources/Support/Pro/Extra
Files/Lua Interfaces/pkg_moho.lua_pkg`), and **independently by rendering
every value with Moho itself** (`-r FILE -f PNG`) on
`SlickObjectTransition.mohoproj` at frame 36.

### 10.1 `group_mask` — on the container

| value | meaning | corpus (46 files) |
|---|---|---|
| `0` | no masking in this group | 304 layers, 42 files |
| `1` | "Reveal all" — masking on, the mask starts **full** | 5 layers, 4 files |
| `2` | "Hide all" — masking on, the mask starts **empty** | 301 layers, 34 files |

`MeshLayer`/`TextLayer`/`PatchLayer`/`SwitchLayer` do not carry the field.

Measured with the container's only contributor forced to draw nothing, so
only the base matters — diffed against the same document with masking
switched off entirely:

| `group_mask` | child mode | pixels changed | of those, inside the source |
|---|---|---|---|
| 1 | 0 (clipped) | 4,868 | 0 |
| 1 | 2 (add) | 4,868 | 0 |
| 1 | 3 (subtract) | 91,048 | 85,284 |
| 2 | 0 (clipped) | 199,667 | 85,284 |
| 2 | 2 (add) | 114,655 | 272 |
| 2 | 3 (subtract) | 140,348 | 25,965 |

So `1` leaves everything visible until something subtracts, and `2` hides
everything until something adds — exactly the header's own
`// 0=none, 1=all visible, 2=all invisible`.

### 10.2 `masking` — on each child

One value per entry of the manual's own Layer Masking menu (ch. 12.05). The
manual lists seven; the scripting header names **eight** (it also has
"subtract, invisibly"), and the corpus uses `0,1,2,4,5,6,7` — every value
except `3`.

| value | constant | meaning | drawn? |
|---|---|---|---|
| `0` | `MM_MASKED` | clipped to the mask **as it stands here** | clipped |
| `1` | `MM_NOTMASKED` | "don't mask this layer" | yes |
| `2` | `MM_ADD_MASK` | + add this layer to the mask | yes |
| `3` | `MM_SUB_MASK` | − subtract it from the mask | yes |
| `4` | `MM_ADD_MASK_INVIS` | + add, but keep invisible | **no** |
| `5` | `MM_SUB_MASK_INVIS` | − subtract, keep invisible | **no** |
| `6` | `MM_CLEAR_ADD_MASK` | + clear the mask, then add this layer | yes |
| `7` | `MM_CLEAR_ADD_MASK_INVIS` | + clear, add, keep invisible | **no** |

Corpus counts (46 files): `0` on 3,188 layers, `2` on 374, `1` on 365, `4`
on 14 (6 files), `6` on 13 (9 files), `5` on 6 (3 files), `7` on 2 (2 files).

**How the three groups were separated.** Probing the *topmost* child of a
masking group — nothing above it can consume its own contribution, so only
"is it drawn, and clipped?" is observable — split the eight values into
exactly three behaviours: `{0}` clipped, `{1,2,3,6}` drawn unclipped, and
`{4,5,7}` not drawn at all. Three invisible values, matching the three
`*_INVIS` constants.

**How each mask edit was identified.** Probing a *middle* child ("Sky",
85,284 px, entirely inside the earlier "Frame" contribution), and splitting
each diff by region:

| mode | diff vs mode 0 | inside Sky | outside Sky | inside Frame−Sky |
|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 |
| 1 | 434 | 0 | 434 | 0 |
| 2 | 434 | 0 | 434 | 0 |
| 3 | 26,296 | 25,696 | 600 | 166 |
| 4 | 62,543 | 61,583 | 960 | 526 |
| 5 | 86,471 | 85,284 | 1,187 | 753 |
| 6 | 41,933 | 1 | 41,932 | 41,932 |
| 7 | 104,039 | 61,583 | 42,456 | 42,456 |

Mode `3` changes only pixels *inside* Sky — it removes Sky from the mask; had
it been clear-then-add, the Frame-only region would have gone dark instead.
Mode `6` changes only pixels *outside* Sky, all of them in Frame−Sky — the
mask became Sky alone, discarding Frame's earlier contribution. Mode `5`
blanks all 85,284 px of Sky: subtract **and** not drawn.

Pairing each visible mode to an invisible one by smallest difference gives
the perfect matching `(2,4)`, `(3,5)`, `(6,7)` — each pair differing only by
the probe layer's own artwork:

|  | 4 | 5 | 7 |
|---|---|---|---|
| **2** | **62,109** | 86,037 | 104,473 |
| **3** | 85,976 | **85,811** | 128,174 |
| **6** | 104,473 | 128,066 | **62,479** |

### 10.3 Three further rules, each measured

- **Every non-zero mode draws unclipped**, including one that contributes to
  the mask. Checked with the mask deliberately empty when the probe is
  reached: modes `1`, `2`, `3` and `6` each drew the layer in full (272 px
  changed inside it, i.e. antialiasing only, against 85,284 for mode `0`).
- **`masking` is inert when `group_mask == 0`** — even the invisible modes,
  which do *not* hide the layer then. Setting the probe to `4`, `5` or `7`
  under `group_mask == 0` changed Moho's render by exactly **0** pixels each
  time. `moho2svg.py` used to skip those layers unconditionally, which
  wrongly blanked artwork in `Snow-girl-cut14.mohoproj`.
- **A layer that does not render contributes nothing to the mask.** Hiding
  the one mask source through the `visible` flag, or through
  `layer_effects.visibility`, or fading it out with `layer_effects.alpha`,
  each produced exactly the same render as having no source at all (199,667
  changed pixels, versus 114,655 with it showing).

### 10.4 The mask is built incrementally

A `masking == 0` child is clipped against the mask **as it stands when that
child is drawn**, not against one mask for the whole container. Ten
containers in the corpus depend on it — the run
`[2, 0, 6, 0, 0]` shared by `Snow-girl-cut3/6/7/8/12/13/51`, and
`OffsetBoneTool.animeproj`'s `[1,1,2,2,2,0,6,0,0,6,0,6,0,0,0,0]`. Collapsing
those to a single mask would clip the earlier masked child with a mask built
partly out of a layer drawn *after* it. `moho2svg.py` therefore computes one
mask state per child (`Exporter._mask_plan`) and emits one `<mask>` per
distinct state, which for the ordinary "sources at the bottom" layout is
still exactly one per container.

This applies uniformly at every nesting depth, **including the document's own
top-level layer** — masking is not special-cased away at the root. A
`masking == 2` sibling does not always carry its own mesh: a `GroupLayer` can
be `masking == 2` purely as a masking *container*, in which case its effective
silhouette is, recursively, whatever its own `masking == 2` child/children
define (the same shapes that already act as *that* container's internal
`group_mask` source).

### 10.5 `mask_expansion` and `exclude_lines_from_mask` — the two checkboxes

Both sit on a mask **source** and both are now decoded. The manual (ch. 12.05)
gives each one sentence, and Moho's own render was used to measure each in
isolation, by exporting the same document twice with the flag forced both ways.

| Field | Manual | Corpus | Moho's own effect | Status |
|---|---|---|---|---|
| `mask_expansion` | *"Adds an additional pixel around a layer mask."* | `true` on **48 layers** | 650 px on `SketchBone.mohoproj` frame 1 (0.07% of 1280×720), along the eye/mouth mask edges | **applied** |
| `exclude_lines_from_mask` | *"Check this option to exclude outlines from the mask."* | `true` on **67 layers** | 2,191 px on the same frame (0.24%); 26–56 px per frame where the outlines are plain rather than brush | decoded, **deliberately not applied** |

An earlier note here called `mask_expansion` "a bool on every layer, `false`
throughout … not used". That was a 19-file reading; it is `true` on 48 layers in
the wider corpus.

**`mask_expansion` is applied** as a 2 px white stroke along the contributing
op's own path inside the `<mask>` (growing the white silhouette by one pixel per
side), and in Lottie as the mask entry's own native `x` ("Expand") property set
to 1. Verified by the two-pole method: our changed pixels sit a **median of 0 px**
(p90 1 px) from Moho's own changed pixels, in the same bounding box, at about
half the count — the residual being anti-aliasing, which the two renderers do
differently anyway.

**`exclude_lines_from_mask` is not applied, and that is a decision, not an
oversight.** This exporter already carves a band along a mask source's own
outline OUT of the mask, but that models a different behaviour (the source's own
stroke staying visible on top — see below). Gating that carve-out on this flag
was tried and reverted: on `Spacewoman.mohoproj` frame 27, Moho's flag moves 336
px inside y 309–421 while the gated version moved 2,412 px across y 225–590,
with **zero overlap**. Excluding outlines leaves the inner half of the stroke
band inside the mask; carving the band removes it. Doing this properly needs the
mask to be `fill ∪ stroke band` when the flag is false, which the current
fill-silhouette-plus-carve model cannot express. One more wrinkle from the manual
(ch. 01): Moho only uses its improved mask anti-aliasing when **exactly one**
layer in a group has Exclude Strokes on, and falls back to an older method
otherwise — so Moho's own behaviour here is not a single algorithm either.

**M1.5:** the 336px figure above was Moho's own measured effect from an
earlier investigation, predating the disposition registry; this milestone
converts it into a formal `tools/probe_field.py` row (forcing all 38 of
`Spacewoman.mohoproj`'s occurrences of `exclude_lines_from_mask` from
`false` to `true` at frame 27, `AFFECTS RENDER` — docs/moho-field-probes.md)
so it is registered rather than only documented in prose. Read by
`moho2svg.py`'s own accessor but deliberately not applied (as above), so
`MODELLED` is unreachable by design; now `EDITABLE`.

**A `masking == 2` sibling's own stroke stays fully visible on top of
whatever it masks.** Confirmed directly against the Moho app on
`Bandit.mohoproj`'s `Head_DarkBlue` (`masking == 0`) / `BellyTexture`
(`masking == 2`) pair: `BellyTexture`'s own stroke shows unbroken everywhere
it overlaps `Head_DarkBlue` in Moho. Before this was fixed, this tool drew
every sibling at its plain file-order position regardless of `masking`, so
`Head_DarkBlue` (listed *after* `BellyTexture`) painted over roughly the
inner two-thirds of `BellyTexture`'s stroke wherever their (unmasked)
geometry overlapped — confirmed by rasterising both independently and
diffing pixel colour along `BellyTexture`'s stroke centreline (~65% of
sampled stroke pixels showed the wrong colour).

A z-order fix (mask sources always paint after masked siblings) was tried
**first** and reverted: most of `Bandit`'s own children are `masking == 1`
("exempt", e.g. `Muzzle`, `Nose`, `EyeBrow`), and `BellyTexture` originally
precedes some of them in file order — forcing "mask sources last" pulled
`BellyTexture`'s opaque fill on top of the character's eyes/muzzle/nose too,
confirmed wrong in the Moho app (they stay unaffected, exactly as this tool
already rendered them before any fix). There is no single reordering of one
container's children that satisfies both "every `masking == 2` after every
`masking == 0`" and "never change order relative to any `masking == 1`
sibling" for this document — the constraints conflict for `BellyTexture`
specifically.

**The actual fix touches mask *geometry*, not paint order.** For each mask
source shape with a plain (non-tapered, non-brush) outline, its own stroke
band is carved back *out* of the mask — painted as a black stroke, that
shape's own stroke width, on top of the mask's white fill silhouette.
Whatever the mask clips can then never paint into that band, regardless of
z-order, so the source's own stroke is never covered — and `masking == 1`
siblings are untouched (they were never part of the mask computation in the
first place), so nothing about the confirmed-correct `Muzzle`/`Nose`/
`EyeBrow` behaviour can regress. Re-measured after the fix: 62% of the
sampled stroke pixels show `BellyTexture`'s own colour (up from 35%), a
further 22% are legitimately covered by *other*, unrelated `masking == 1`
siblings (whose own z-order relationship to `BellyTexture` this fix
correctly leaves alone), and the remainder is statistically indistinguishable
from what's left over even with `Head_DarkBlue`/`Eye_Back`/`Head_DarkBlue 2`/
`Eye_Upper` removed from the render entirely — i.e. not attributable to this
fix's target layers, most likely anti-aliasing at the mask boundary. A
tapered or brush-styled source outline still only contributes its bare fill
to the mask (unconfirmed geometry for those two cases) — see the module
docstring's MASKING section and KNOWN GAPS.

---

## 11. Actions and Smart Bones

"Actions" in Moho are stored in two places, and the two look similar but do
different jobs.

### 11.1 The layer-level `actions` registry

Almost every layer carries an `actions` list whose elements are always exactly
`{"name": "<action name>", "pose": 0}` — 19,921 such entries across the
19-file sample, with `pose` an integer `0` in every single one. Present on
524 of 648 `MeshLayer`s, 90 of 103 `GroupLayer`s, 38 of 47 `BoneLayer`s, 11 of
17 `SwitchLayer`s, 4 of 12 `PatchLayer`s, never on a `TextLayer`, and never on
an `ImageLayer` **(the last is a 19-file finding — `ImageLayer` did not exist
in the original sample)**.

This is a **document-wide name registry, replicated on nearly every layer**,
not a per-layer list of that layer's own actions. Evidence: in `WhatIsBone`,
a `BoneLayer` named `kafasi` with **zero bones** carries the same 37 action
names as the 157-bone `girl` layer above it. So the registry says which
action names exist in the document, not which apply here.

### 11.2 Channel-level poses

The actual animation data lives on individual channels. Any channel anywhere
may carry its own `actions` list, and there the `pose` is a **full nested
channel**:

```jsonc
"actions": [
  { "name": "EyeBlink",
    "pose": { "type": "Vec2", "when": [0, 6, 12], "val": [...], "interp": [...] } }
]
```

11,816 such poses exist across the 19-file sample. Their `pose` channel types
are `Vec2` (10,024), `Val` (1,561), `Vec3` (165), `Color` (37), `Bool` (22),
and `String` (7) — i.e. an action can override any kind of property,
including colour, but in practice it is mostly mesh point positions and bone
transforms. `pose` is by far the most keyframed field in these documents,
well ahead of `anim_angle`'s 383 keyframed bones ([§ 9](#9-bones-and-skinning)).

### 11.3 Which actions are Smart Bones

A "Smart Bone" is an ordinary bone used as a *dial*: its own rotation angle
selects a pose for the rest of the rig.

- A registered action name becomes a **Smart Bone dial** when it matches the
  `name` of a bone in the enclosing `BoneLayer`'s own skeleton.
- Registered names that match no bone are **plain actions** — reusable
  timeline clips, triggered from Moho's Actions window, not driven by any
  bone. `Bandit`'s `"Walk"` is the clearest example: 5 registered actions, 4
  matching bone names, and `"Walk"` matching none. Per-BoneLayer counts of
  dial versus plain names: `Bandit` 4/1, `SketchBone`'s `kafasi` 9/13,
  `WhatIsBone`'s `girl` 14/23, `AddBone`'s `Head` 27/41.
- `moho2svg.py` only ever activates the dial kind, which is correct — a plain
  action is off unless the user runs it, and nothing in the file says it is
  running.

When dial `D` is active, a channel carrying `actions: [{"name": "D", "pose":
<channel>}]` is read from `pose` instead of its own `when`/`val`, at a frame
found by **inverting the pose curve**: the pose channel's own `val` array
records what the dial's *own* angle was at each of the pose's keyframes, so
"the pose frame whose recorded angle matches the dial's current actual angle"
is well-defined by interpolation.

Moho stores *two* actions per dial, one per rotation direction — the second
suffixed `" 2"` (e.g. `"BlinkL"` and `"BlinkL 2"`) — because a pose curve must
be roughly monotonic to be invertible. The samples are full of these pairs.

A dial's own *current* angle is always its literal position on the main
timeline. Resolving it must not recurse into the same override mechanism it is
itself part of; this is the one place `Channel.eval_raw()` is used.

### 11.4 `action_refs` and `layercomps`

`layercomps` is **empty in all 19 documents**, so its element shape cannot be
documented from this evidence — it is Moho's "layer comps" feature (named
show/hide sets of layers, used to export variants of one document).
`action_refs` is empty in every document that carries the key at all, and is
**absent entirely** (not just empty) in the `1021`-generation
`Rabbit.animeproj` **(19-file finding)** — see [§ 2](#2-top-level-structure).
It most plausibly holds references to actions defined outside this document,
matching the `layer_ref_*` fields on layers, but that is a guess, not a
finding. Neither is read by this tool.

Both were probed on `Bandit.mohoproj` with a single synthesised element (the
manual's Appendix F `{name, uuid, layer_ids[]}` shape for `layercomps`, a
generic placeholder object for `action_refs`, since no real document supplies
either): both **inert**. Editing either array is therefore safe even though
neither's real-world element grammar has ever been observed in the corpus
(docs/moho-field-probes.md).

The five `layer_ref_*` fields on every layer (`layer_ref_fileref`,
`layer_ref_path`, `layer_ref_uuid`, `layer_ref_same_doc`, `layer_ref_mod_date`)
are present everywhere with empty/zero defaults and are the plausible storage
hook for referencing another (possibly external) document's layer.
**Correction (fix round 2):** an earlier revision of this paragraph claimed no
sampled document uses them non-trivially — that is false. A direct scan of
all 76 corpus documents found real, non-default values: `layer_ref_fileref`
is `{relativeTo: "User Library", path: "Frog/Character/Character/Character.moho"}`
on 6 documents under `metamorphosis/`; `layer_ref_uuid` holds a real uuid on
443 layers across 22 documents (`FoxAndGhost.animeproj`,
`Gathered-02Wire2.mohoproj`, `OffsetBoneTool.animeproj`, 13 `Snow_wars/*.moho`
episodes and 6 `metamorphosis/Scene *.moho` files); `layer_ref_same_doc` is
`true` on 16 documents; `layer_ref_mod_date` is non-zero wherever the other
two are. All five were still probed inert on Bandit.mohoproj specifically,
which is one of the majority (74 of 76 for `layer_ref_fileref`) where these
fields genuinely sit at their empty/zero defaults (docs/moho-field-probes.md)
— but the broader "no sampled document uses these" claim does not hold, and
none of the documents that do use them non-trivially was probed.

---

## 12. Patch layers

A `PatchLayer` has no `mesh` field of its own — instead it carries
`target_layer_uuid`, naming another layer elsewhere in the document (in every
example found so far, a sibling within the same group) whose *mesh* it reuses,
redrawn at the patch layer's own position in the draw order. This is how a rig
patches a visible seam between two overlapping body parts: e.g. a hand's
`ayasi-Patch` reuses the palm mesh `ayasi`, but sits between two finger layers
in the stack rather than below all of them, so it covers the gap that appears
there as the fingers move.

`target_layer_id` is also present alongside `target_layer_uuid` on all 8 patch
layers, with values `0` (4×), `1`, `2`, `3`, and `7` — so it is not the
constant `0` an earlier revision of this document reported. Its purpose beyond
the uuid is still unknown, and this tool ignores it.

### 12.1 The patch's own transform is a CLIP REGION

The patch layer's own `transforms`/`parent_bone`/`flexi_bone_subset`/`origin`
are **wrong for its artwork and right for its clip**. Both halves are settled.

*Wrong for the artwork.* Every `PatchLayer` carries a bizarre,
seemingly-unrelated own transform (a `0.147` non-uniform Y scale on one hand's
`ayasi-Patch`; a uniform `~0.49` scale on `Leg_L-Patch`/`Leg_R-Patch`), while
its *target* has the identity transform. Rendering the mesh through the
patch's own transform reproduces exactly that: a squashed sliver floating away
from where the target renders. The target's transform (and
`parent_bone`/`flexi_bone_subset`/`origin`) is used for the artwork instead.

*Right for the clip.* The manual says what the transform is actually for
(ch. 11.15): creating a patch gives you **"a new CIRCLE in the project
window … Use the Transform Layer tool to POSITION AND SCALE the patch so that
the lines are covered."** The patch redraws its target **only inside that
disc** — which is what lets "part of a layer appear behind a layer, and
another part of the same layer in front of it".

Three experiments on Moho's own renders of `AddBone.animeproj`, each diffing
the document rendered with and without the patch:

| experiment | result | what it rules out |
|---|---|---|
| scale the patch ×5 | covered region grew from 80 to 1,287 px, x extent unchanged | the transform scaling the artwork |
| translate the patch away from its target | paints **nothing at all** | the transform moving the artwork |
| sweep scale 0.25 → 3.0 and solve for the growth | radius = **36 px per unit of scale** at 720p, i.e. **0.1 Moho units**, centred on the patch's own translation | a radius of 1, or a centre elsewhere |

The predicted centre for `Leg_L-Patch` lands **0.4 px** from the measured one.

The disc also follows the patch's **own bone binding**, not the target's:
`DonkeyAndMan.mohoproj`'s two patches are rigidly bound to bones 8 and 6, and
only running the patch's own rigging through the deform chain puts the
computed disc over the region Moho actually repaints (11.8 px from the centre
of a 16.8 px disc; ignoring the bone puts it 137 px away).

Measured effect of adding the clip, in isolation (mean |difference| against
Moho's own PNG render of the same frame): **0.702 → 0.682** on
`AddBone.animeproj` and **3.940 → 3.930** on `DonkeyAndMan.mohoproj`. Small,
because most of what the clip removes was repainting colours already
underneath — on `AddBone` it stops 6,081 px being painted, of which only ~400
were visibly wrong.

**A resolved patch duplicates its target's fill only, never its outline.**
This part *is* confirmed directly against the Moho app (not just against this
tool's own output), on two points chosen specifically to rule out a confound:
`ayasi-Patch` (`masking == 2`, a mask source) and `Left Bicep-Patch`
(`masking == 0`, not a mask source) — both are `PatchLayer`s whose target has
`has_outline: true` and a real stroke, and **both show no stroke in Moho's own
canvas** while their targets do. Since `masking` differs between the two but
the result does not, the suppression is tied to being a `PatchLayer`, not to
`masking` (which § 10 already confirms still draws its mask-source layers
normally). `moho2svg.py` implements this via `ShapeGroupRenderer.suppress_outline`,
set whenever the layer being rendered is a `PatchLayer` — not by changing
`Shape.has_outline` itself, since a patch and its target share the exact same
`Shape`/`Mesh` objects, and the target must still draw its own outline
wherever *it* renders in the tree.

---

## 13. Coverage summary

What this tool reads, at a glance. "Exercised" means at least one of the 19
sample documents has a non-default value for it, so ignoring it changes the
current reference output in `svg/`.

### 13.1 Read and applied

| Area | Fields |
|---|---|
| Document | `version`, `project_data.width`/`.height`, `styles`, `layers` |
| Layer | `type`, `name`, `visible`, `edit_only`, `layers`, `uuid`, `origin`, `parent_bone`, `flexi_bone_subset`, `masking`, `group_mask`, `actions`, `transforms.translation`/`.scale`/`.rotation_z`/`.flip_h`/`.flip_v` |
| Switch | `switch_keys` |
| Patch | `target_layer_uuid` |
| Text | `mesh_layer` |
| Mesh | `points[].position`/`.width`, `curves[].closed`/`.points[]` (`point`, `smoothness`, `weight_in`/`out`, `offset_in`/`out`, `segments_on`), `shapes[]` (`edges`, `has_fill`, `has_outline`, `style`, `inherited_style*`, `id`, `combo_mode`, `effect_scale`, `effect_rotation`) |
| Style | `name`, `uuid`, `define_fill_color`/`_line_col`/`_line_width`, `fill_color`, `line_color`, `line_width`, `line_caps`, `fill_style` (`gradient_type`, `gradients[].location`/`.color`), `brush_name`, `brush_jitter`, `brush_spacing`, `brush_align`, `brush_tint` |
| Bone | `name`, `parent`, `length`, `strength`, `anim_pos`, `anim_angle`, `anim_scale` |
| Channel | `when`, `val`, `actions[].name`/`.pose` |

### 13.2 Ignored **and exercised** by the samples — real output differences

Ranked by how visible the difference should be:

1. `Rabbit.animeproj` (the `1021` format generation) has no
   `weight_in`/`weight_out`/`offset_in`/`offset_out` on any curve point, so
   every handle is reconstructed from neutral defaults rather than stored
   values. ([§ 7.3](#73-curves-and-curve-points)) The document loads and
   exports; what is unverified is the handle *shape*, since no reference SVG
   exists for it. **(19-file finding.)** *(Until the `.get()` defaulting was
   added this was a hard failure to load — `KeyError: 'weight_in'` — not a
   rendering-accuracy gap.)*
2. ~~`layer_effects.alpha`~~ — **fixed for leaf layers.** 139 leaf layers
   across 15 files set a non-1 opacity (11 of them animated); both
   exporters now apply it, measured as a plain linear blend. A
   *container's* own alpha remains undecoded and is warned about rather
   than guessed — 5 layers corpus-wide. ([§ 6.3a](#63a-layer-opacity))
3. ~~`blend_mode`~~ — **fixed.** 168 layers across 18 files blend
   non-normally (`1` Multiply / `2` Screen / `3` Overlay); both exporters now
   apply it. ([§ 6.6](#66-blend_mode))
4. `ImageLayer` — 15 layers (one document) silently drop their raster
   artwork entirely, since this is a vector-only exporter. **(19-file
   finding.)** ([§ 6.5](#65-imagelayer-19-file-finding))
5. `style.fill_style` / `.line_style` / `.fill_style2` holding any effect
   other than `SS_Gradient2` — **486 effect objects reaching 450 drawn
   shapes**, across 21 files, render as a flat fill/stroke instead of Moho's
   halo, shading, soft edge, texture, shadow or crayon. `SS_Halo` is the
   single biggest contributor at 198 drawn shapes in 10 files. Each one now
   warns per shape rather than failing silently. **(46-file finding, which
   roughly *tenfolds* the earlier 19-file count of 43 — the two effect types
   it had missed entirely, `SS_Halo` and `SS_Shaded`, turned out to be the
   two most common after gradients.)** ([§ 8.3](#83-style-effect-variants-46-file-finding))
6. `extra_sketchy` / `extra_lines: 5` — 2 layers should draw repeated jittered strokes. ([§ 6.4](#64-type-specific-fields))
7. `channel.interp` — non-linear timing on `pose`/`anim_*`; exact at keyframes, off between them. Only matters for a `--frame N` that is not a keyframe. ([§ 5.3](#53-the-interp-entries))
8. `bone.scaling_mode: 2` — 242 bones; possibly related to the preserved asymmetric bone scale. ([§ 9](#9-bones-and-skinning))
9. `mesh.curve_interpretation: 0` — 2 meshes differ from the rest in the
   original 19-file sample; a 76-document scan (M1.4a) found 57 meshes across
   5 documents (mostly `DarkMan.mohoproj`, 52 of the 57). Forcing it to `0` on
   `Bandit.mohoproj` (all stored `1`) left frame 25 byte-identical. ([§ 7.1](#71-the-mesh-object))
10. `shape.fill_allowed: false` — 859 shapes (19-file total, up from 229 in the original sample). Interaction with `has_fill` undecoded — forcing it `false` everywhere on `Bandit.mohoproj` (M1.3 probe) did not visibly remove a fill there, but that is one document's negative result, not a settled interaction rule. ([§ 7.4](#74-shapes-and-edges))
11. `style.line_caps: 0` — 765 styles (3 documents) use butt caps instead of the round caps the original 5-file sample exclusively showed. **(19-file finding.)** Whether `LINE_CAP_NAMES`' `0` mapping is actually correct is unverified. ([§ 8.1](#81-named-styles-docstyles))

A masking==2 sibling's own stroke staying visible on top of whatever it masks
was also on this list until it was fixed (mask geometry now excludes each
source shape's own plain stroke band — see [§ 10](#10-masking)); a tapered
or brush-styled source outline is the one remaining gap there.

A `combo_mode == 3` member's own outline used to also show a real gap Moho
doesn't draw — confirmed on `Bandit`'s `Eye_Upper`/`S3` — because this tool
approximates the boolean operation with SVG masking rather than a true path
intersection. Now fixed by drawing such a member's full outline (instead of
dropping its hidden segment) and letting the existing intersect-clip cut it
correctly, sidestepping the need for real Bezier–Bezier intersection; see
[§ 7.8](#78-boolean-shape-combination) for the full finding.

Items 8–10 are *undecoded*, not *known-wrong*: the samples set them to a
non-default value, but nothing proves the current output is incorrect for
them.

### 13.3 Ignored and **not** exercised — untested gaps

Present in the format, but at default values throughout the (19-file) samples
this section describes, so ignoring them was invisible **there**. **Six items
in this paragraph are now known, corpus-wide (76 documents, M1.4a), to be
non-default and render-affecting in real files, contrary to the flat
"invisible" framing below** — `curve` profiles (`profile_layer_uuid`/
`profile_curve_id`/`profile_repeat` all AFFECTS RENDER on
`Gathered-01Intro2.mohoproj`), `point.colored` (AFFECTS RENDER on
`Snow-girl-cut10.mohoproj`), `layer_outline`, `layer_shadow`,
`perspective_shadow` and `motion_blur` (each AFFECTS RENDER as a whole block —
see [§ 6.3](#63-common-fields-that-affect-rendering-and-are-not-used) for each
one's own corrected row and probe). `point.color`/`.opacity`, `layer_shading`
and `layer_color` remain genuinely inert wherever probed so far (see the same
section). None of the six was fixed by this milestone — they are still
ignored by both exporters — only the "currently invisible" claim is retracted:
`channel.mute`, `channel.split`,
`bone.anim_parent` (redundant with `parent` on all 850 bones — see
[§ 9](#9-bones-and-skinning)),
`doc.animated_values` (camera), `curve.start_percent`/`end_percent`,
`layer_effects.visibility` and
the other five effect channels, `layer_shading`, `layer_color`,
`timing_offset`, fill/line textures, `layer_ref_*`,
`distortion_layer_uuid`, follow-path fields, all physics fields (including
`gravity`/`wind` — see [§ 6.4](#64-type-specific-fields)), all bone
constraint/IK fields, `project_data.global_render_style_*`, `mesh.groups`,
`mesh.shape_order`, `shape.3d_thickness`/`effect_offset`/`combo_blend_anim`,
`quality_flags`, `Mesh3DOptions`/`3d_mode`
**(19-file finding — see [§ 6.4](#64-type-specific-fields))**, `parent_bone
== -3` **(19-file finding, `ImageLayer` only)**, `masking == 5`/`6`
**(19-file finding)**, and the `TextLayer` font/balloon fields.

`layer_ordering`/`animated_layer_order` moved from "untested" to
**confirmed-inert-in-this-sample (19-file finding)**: the channel's value is
an empty string in all ~150 sampled instances, so this tool's fixed-order
rendering is verifiably correct for every document here, not merely
unexercised — see [§ 6.4](#64-type-specific-fields).

Two bone/rig fields that used to sit in this list have moved out of it,
because they are **not** at their defaults everywhere: `skeleton.binding_mode`
(`2` on one skeleton) and `bone.offset` (non-zero on 5 bones). Both are now
listed as known unknowns in [§ 14](#14-known-unknowns).

The riskiest of these are the ones a real production document would plausibly
use: **`layer_effects.visibility`** (animated show/hide),
**`curve.end_percent`** (a line drawing itself on), **`timing_offset`**,
**`project_data.global_render_style_*`**, and **the camera channels**.

---

## 14. Known unknowns

This is a living reverse-engineering effort, not a specification. Fields whose
*values* are observed but whose *meaning* is not decoded:

- `combo_mode: 2` — decoded as Subtract, order-dependence included, from a
  direct Moho App observation (2026-08-17), implemented in both exporters,
  but absent from all 19 sample documents so its edge-exactness stays
  unverified against a machine-readable reference. ([§ 7.8](#78-boolean-shape-combination))
- `channel.interp.t` / `.im` / `.in` / `.s` / `.h` / `.v1` / `.v2` / `.b` —
  the interpolation-type enum and its parameters. ([§ 5.3](#53-the-interp-entries))
- `channel.ref` — `true` on 207 channels across 3 documents; meaning not
  decoded. **(19-file finding, corrects an earlier "false everywhere" claim
  — see [§ 5.1](#51-channel-object-fields).)**
- `group_mask: 1` versus `2` — 2 containers use `1`. ([§ 10](#10-masking))
- `masking: 5` / `6` — 7 layers across 3 documents. **(19-file finding.)**
  ([§ 10](#10-masking))
- `parent_bone: -3` — 9 `ImageLayer` instances, always with a real
  `flexi_bone_subset`. **(19-file finding.)** ([§ 6.2](#62-common-fields-that-affect-rendering-and-are-used))
- The correct mask contribution of a `masking == 2` sibling whose own outline
  is tapered or brush-styled (a plain uniform stroke is handled — see
  [§ 10](#10-masking)).
- `blend_mode: 1` — 16 layers. ([§ 6.3](#63-common-fields-that-affect-rendering-and-are-not-used))
- `bone.scaling_mode` (`0`/`2`), `skeleton.binding_mode` (`1` on 41
  skeletons, `2` on one — **corrects an earlier "always `1`" claim**),
  `bone.offset` (non-zero on 5 bones — see [§ 9](#9-bones-and-skinning)),
  `mesh.curve_interpretation` (`0`/`1`), `quality_flags` (a bit field),
  `face_camera_mode` (always `2`), `shape.fill_allowed`,
  `PatchLayer.target_layer_id`, `fill_style_id`/`line_style_id`/
  `fill_style2_id` (mostly `9`; also `12`, `11`, `2`, `10` — **the non-9
  values are a 19-file finding**).
- `layercomps` and `action_refs` element shapes — both lists empty in every
  document that has the key at all. ([§ 11.4](#114-action_refs-and-layercomps))
- The first number of an old-style `brush_name` suffix.
  ([§ 8.6](#86-resolving-a-brush_name-to-a-file))
- `Mesh3DOptions`' own field meanings (`3d_shading_mode`, `3d_shading_density`,
  crease/edge toggles) — present on every `MeshLayer` but entirely inert
  since `3d_mode` is `0` everywhere. **(19-file finding.)**
  ([§ 6.4](#64-type-specific-fields))
- `ImageLayer`'s `toon_*` cel-shading fields, `sampling_mode`,
  `quality_level` — an entire layer type not modelled at all. **(19-file
  finding.)** ([§ 6.5](#65-imagelayer-19-file-finding))
- `SS_Crayon`/`SS_Soft`/`SS_Shadow`/`SS_Texture2` internals — `rand_seed`,
  `clear_background`, `reduce_randomization`, `fill_mode`, and the interplay
  between a shape's `fill_style` and `fill_style2` when both are present.
  **(19-file finding.)** ([§ 8.3](#83-style-effect-variants-46-file-finding))
- The `g_<number>` boolean toggles and `psd_layers` in a layer's own
  `metadata` bag. **(19-file finding.)** ([§ 6.4](#64-type-specific-fields))
- **Smart Warp** — a whole Moho deformation feature with **no representation
  at all in this sample**: a search for any JSON key containing "warp"
  returns zero hits across all 19 files. The only hooks visible are
  `distortion_layer_uuid` (empty everywhere) and the `1045`-only
  `triangulated` / `squashable_deformer` / `frame_zero_deformer` flags. A
  document that uses it would export with the deformation silently dropped.
  See [`moho-rigging-and-deformation.md` § 5](moho-rigging-and-deformation.md#5-smart-warp).

Plus the approximations already noted: gradient placement precision, the
flexible bone-weight falloff shape for overlapping influence, the
`PatchLayer` transform heuristic ([§ 12](#12-patch-layers)), and the brush
stroke simplifications ([§ 8.5](#85-brush-styles)).

See the module docstring's KNOWN GAPS section for the rendering-side list. If
you find a real document that contradicts something here, prefer the evidence
in the document over what is written in this file — and say so, since every
count above is measured from 19 files, not from Moho's entire possible
output space. A machine-checkable structural counterpart — a JSON Schema with
its own completeness audit — lives in `schema/`; see `schema/README.md` § 3
for how that audit works and what it additionally caught.
