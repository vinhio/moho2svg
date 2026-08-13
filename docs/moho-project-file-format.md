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
field — see `docs/export-pipeline.md`.

---

## 1. Scope and evidence base

Every field list, value set, and count in this document was measured by
walking the project files in the (gitignored) `moho/` folder. That sample is
small, so treat "the only values observed" as *evidence*, not as *the complete
set the format allows*.

| Document | `version` | Canvas | `fps` | Frames | Layers | Named styles | Shapes | Points | Bones |
|---|---|---|---|---|---|---|---|---|---|
| `AddBone.animeproj` | 1038 | 1280×720 | 24 | 1–25 | 229 | 201 | 310 | 4,663 | 188 |
| `ReparentBone.animeproj` | 1038 | 1280×720 | 24 | 1–120 | 42 | 201 | 144 | 3,436 | 24 |
| `SketchBone.animeproj` | 1038 | 1280×720 | 24 | 1–120 | 108 | 239 | 190 | 3,556 | 94 |
| `WhatIsBone.animeproj` | 1038 | 1280×720 | 24 | 1–240 | 140 | 118 | 203 | 4,176 | 216 |
| `Bandit.mohoproj` | 1045 | 1920×1080 | 24 | 25–127 | 25 | 12 | 112 | 396 | 28 |

(The layer counts include the `MeshLayer` nested inside each `TextLayer`.)

Totals across the five documents: 544 layers, 771 named styles, 959 shapes,
1,088 curves, 16,227 mesh points, 16,378 curve points, 550 bones, and 201,185
animation channels.

The two `version` values matter, because they behave differently in several
places (styles, per-point fields, `combo_mode`). Throughout this document,
**"older"** means the four `1038` documents and **"newer"** means the single
`1045` document. A conclusion drawn from `1045` alone rests on one file.

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
| `version` | int | Format revision: `1038` or `1045`. | **yes** — read, but no branch depends on it |
| `animated_values` | obj | Document-level channels: camera + timeline markers ([§ 5.5](#55-document-level-animated_values)). | no |
| `layercomps` | list | Layer comps (saved show/hide sets). **Empty in all five documents**, so its element shape is unknown. | no |
| `action_refs` | list | **Empty in all five documents**, so its element shape is unknown. Presumably references to actions in external/linked documents; see [§ 11.4](#114-action_refs-and-layercomps). | no |
| `major_version` / `rev_version` | int | Always `1` / `0`. | no |
| `mime_type` | str | Always `"application/x-vnd.lm_mohodoc"`. | no |
| `doc_uuid` | str | Document identity. | no |
| `created_date` / `modified_date` | str | Human-readable timestamps, e.g. `"Wed Aug 31 16:17:24 2016"`. | no |
| `comment` | str | Only in the `1045` file: `"Created in Moho version 14.3, ..."`. | no |
| `thumbnail` | str | Only in the `1045` file: base64 JPEG preview. | no |
| `documentviewstate` | obj | 48 `DocState_*` editor keys (zoom, grid, playback range, viewport split). Pure UI state. | no |
| `metadata` | obj | Small key/value bag; `{"what": 0}` plus tool-specific keys. | no |
| `onions_*` (14 keys) | mixed | Onion-skin editor settings. Unset frame slots are `-100000`. | no |

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
| `back_color` | `{r:234, g:234, b:234, a:255}` | Canvas background. **0–255 integers**, unlike style colours ([§ 5.2](#52-channel-types-and-val-element-shapes)). Not drawn — the exported SVG has a transparent background. |
| `antialiasing` | `true` | Render flag. |
| `depth_sort` / `distance_sort` | `false` | 3D sorting of layers. |
| `depth_of_field`, `focus_distance`, `focus_range`, `focus_blur` | `false`, numbers | Camera depth-of-field. |
| `noise_grain`, `pixelation` | `0.0` | Global render effects. |
| `stereo_mode`, `stereo_separation` | `0`, number | Stereoscopic output. |
| `global_render_style_fill_style`, `..._line_style`, `..._layer_style`, `..._minimize_randomness` | strings / bool | A document-wide style override applied at render time. **Empty in all five documents** — if a document ever sets these, this tool would ignore them and could produce visibly wrong colours. |
| `color_palette` | `"Basic Colors.png"` | Editor swatch palette. |
| `soundtrack` | str | Audio file reference. |
| `extra_swf_frame`, `display_quality` | bool, int | Legacy export options. |

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
the format: 201,185 instances across the five documents.

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
  on all 201,185 channels, zero exceptions. `interp[i]` describes the segment
  leaving keyframe `i`.
- `mute` and `ref` are `false` on every channel in all five documents.
  `moho2svg.py` does not read either. **A `mute: true` channel would be
  silently animated by this tool where Moho would freeze it** — an untested
  gap, not a confirmed bug, since no sample exercises it.
- A field that is never animated is sometimes stored as a bare scalar or a
  plain dict instead of a channel object. Both forms are accepted
  transparently (`Channel` treats a bare scalar as a single keyframe).

`moho2svg.py` evaluates a channel with **linear interpolation between the two
bracketing keyframes**, clamped at both ends, ignoring `interp` entirely. That
is exact at keyframes and approximate between them.

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
keyframe at frame `0` in all five documents:

| Key | `type` | Value seen | Meaning |
|---|---|---|---|
| `camera_track` | `Vec3` | `{0, 0, 3.732051}` | Camera position. The `z` value is the default camera distance. |
| `camera_pan_tilt` | `Vec2` | `{0, 0}` | Camera pan/tilt. |
| `camera_zoom` | `Val` | `0.0` | Camera zoom. |
| `camera_roll` | `Val` | `0.0` | Camera roll. |
| `timeline_markers` | `String` | `""` | Editor timeline annotations. |

None of these are used. This tool renders with an implicit fixed camera. **A
document with a moved or zoomed camera would export with the wrong framing**,
since nothing here is applied. Every sample happens to sit at the default, so
this gap is invisible in current output.

---

## 6. Layers

### 6.1 Layer types

Each layer is a JSON object with a `type` field naming its kind:

| `type` | Count | Meaning | Rendered? |
|---|---|---|---|
| `MeshLayer` | 428 | Vector artwork (points/curves/shapes) — the only layer kind that actually draws pixels. | **yes** |
| `GroupLayer` | 61 | Children with no skeleton. | **yes** (container) |
| `BoneLayer` | 31 | A skeleton (`skeleton.bones`) plus child layers deformed by it. | **yes** (container + skinning) |
| `TextLayer` | 8 | A caption. Moho keeps the laid-out glyph outlines in a nested `mesh_layer` field, which is an ordinary `MeshLayer` object. | **yes**, via `mesh_layer` |
| `SwitchLayer` | 8 | Children are alternatives; only one shows at a time. | **yes** |
| `PatchLayer` | 8 | No mesh of its own — reuses another layer's mesh ([§ 12](#12-patch-layers)). | **yes**, resolved |
| anything else | 0 in these files | Image, audio, particle, note, 3D layers etc. are not modelled. | no |

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
  Observed: `-1` on 513 of 544 layers, and 31 layers rigidly bound.
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
| `layer_effects.alpha` | `Val` channel | `1.0` on 535 layers, **`0.6` on 9 layers** | Layer opacity. **This one is actually exercised by the samples** — nine layers should render at 60% and instead render fully opaque. |
| `blend_mode` | int | `0` on 528 layers, **`1` on 16 layers** | Layer blend mode. `0` is presumably Normal; `1` is not decoded. 16 layers blend differently in Moho than in the SVG. |
| `layer_effects.visibility` | `Bool` channel | `true` everywhere | **Animated** show/hide, independent of the static `visible` flag. Would let a layer appear mid-animation. |
| `layer_effects.blur`, `.noise`, `.pixelation`, `.threshold`, `.ambient_occlusion` | `Val` channels | `0.0` everywhere | Per-layer image effects. All off in the samples. |
| `layer_outline` | `{on, color, width}` | `on: false` everywhere | An extra outline stroked around the whole layer. |
| `layer_shadow` | `{on, angle, blur, color, expansion, offset, threshold, noise_amp, noise_scale, clip_to_group}` | `on: false` everywhere | Drop shadow. |
| `layer_shading` | `{on, angle, blur, color, contraction, offset, threshold, noise_amp, noise_scale}` | `on: false` everywhere | Inner shading. |
| `perspective_shadow` | `{on, blur, color, scale, shear, threshold}` | `on: false` everywhere | Perspective shadow. |
| `layer_color` | `{on, color}` | `on: false` everywhere | A flat colour override for the whole layer. |
| `transforms.rotation_x`, `.rotation_y` | `Val` channels | `0.0` everywhere | 3D rotation. A 2D exporter cannot express these. |
| `transforms.shear` | `Vec3` channel | `0` everywhere | Shear. Could be expressed in an SVG matrix, but is not. |
| `transforms.translation.z`, `.scale.z` | float | defaults | Layer depth. |
| `transforms.following`, `.physics_nudge` | channels | defaults | Path-following offset and physics displacement. |
| `motion_blur` | `{on, frames, radius, skip, alpha_start, alpha_end, frame_percentage, extended_frames, sub_frames}` | `on: false` | Motion blur. Not meaningful for a single-frame export anyway. |
| `distortion_layer_uuid` | str | `""` everywhere | Points at another layer used as a distortion mesh. |
| `follow_layer_uuid`, `follow_curve`, `follow_bending`, `rotate_to_follow` | str/int/bool | `""`, `-1`, defaults | "Follow path" rigging. |
| `physics`, `gravity`, `wind`, `enable_physics`, `use_baked_physics` | objs/channels | disabled | 2D physics simulation. |
| `scale_compensation`, `scale_normalization` | bool/float | defaults | How a layer's stroke width reacts to scaling. Relevant to [§ 7.6](#76-stroke-width) if ever non-default. |
| `layer_ordering` | `String` channel | `""` | Animated child reordering (with `animated_layer_order` on `BoneLayer`). Would change draw order per frame. |
| `timing_offset` | int | `0` everywhere | Shifts this layer's whole timeline. Non-zero would desync the frame this tool evaluates. |
| `layer_ref_*` (`uuid`, `path`, `fileref`, `mod_date`, `same_doc`) | mixed | empty | Linked/referenced external layer. A document using these would be missing artwork here. |
| `camera_immune`, `dof_immune`, `face_camera`, `face_camera_mode`, `3d_mode`, `3d_options` | mixed | defaults, `face_camera_mode: 2` | 3D / camera behaviour. |
| `quality_flags` | int | `4092`, `4094`, `45052`, `45054`, `2044` | A bit field of per-layer render toggles. Not decoded. |
| `label_col`, `expanded`, `shown_in_timeline`, `selected`, `random_num`, `layer_user_tags`, `layer_user_comments`, `ignored_by_layer_picker`, `consolidated_channels`, `render_only`, `mask_expansion`, `script_data`, `metadata`, `modification_date` | mixed | — | Editor state, or (for `render_only` / `mask_expansion`) undecoded render toggles that are off in every sample. |

### 6.4 Type-specific fields

**`MeshLayer`** — `mesh` is the only field used ([§ 7](#7-mesh-model)). Not used:

- `fill_texture_path` / `fill_texture_fileref`, `line_texture_path` /
  `line_texture_fileref` — image textures for fills and lines. Empty in all
  428 mesh layers.
- `noisy_lines`, `noisy_shapes`, `extra_sketchy`, `extra_lines`, `noise_amp`,
  `noise_scale`, `noise_interval`, `animated_noise` — the "sketchy lines"
  look. `extra_sketchy: true` with `extra_lines: 5` on **2 layers** (in
  `SketchBone`), so those two layers should render with repeated jittered
  strokes and do not.
- `gap_filling`, `exclude_lines_from_mask`, `antialiasing`, `triangulated`,
  `squashable_deformer`, `frame_zero_deformer`.

**`BoneLayer`** — `skeleton` and `actions` are used. `skeleton` is
`{type, binding_mode, bones}`, plus `bones_groups` in the `1045` document
(present but empty there). `binding_mode` is `1` on all 39 skeletons; its
other values are unknown, and this tool never branches on it. Also carries
`grandpa_bone`, `flexi_bone_elbow`, `animated_layer_order`,
`animated_layer_effects` — none used.

**`GroupLayer`** — no extra rendering fields beyond the common set.

**`SwitchLayer`** — `switch_keys` (a `String` channel whose `val` entries are
**child layer names**) selects the active child; used. Not used:
`switch_interpolation`, `switch_data` (`""` in all 8), `frame_by_frame`,
`previewAlignment`. A `SwitchLayer` also carries its own `skeleton` object
(with an empty `bones` list in all 8 cases) — do not mistake it for a
`BoneLayer`.

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
| `anim_shape_order` | bool, `false` on all 428 meshes. Presumably enables keyframing `shape_order`. | no |
| `next_shape_id` | int; the id allocator's next value. | no |
| `curve_interpretation` | int: `1` on 426 meshes, `0` on 2. Meaning not decoded; both render the same way here. | no |

### 7.2 Mesh points

| Field | Shape | Observed | Used? |
|---|---|---|---|
| `position` | `Vec2` channel | animated on 14 points | **yes** |
| `width` | `Val` channel | `1.0` on 12,797 points; also `0.34`, `0.32`, `0.14`, `0.0`, `0.46`, `0.2`, `0.26`, … | **yes** — per-point stroke width ([§ 7.6](#76-stroke-width), [§ 7.7](#77-tapered-strokes)) |
| `curves` | list of ints | indices of the curves through this point | no (the reverse mapping is rebuilt from `curves`) |
| `parent` | int | point-level parenting | no |
| `colored` | bool | `false` on all 16,227 points | no |
| `color` | `Color` channel | per-point vertex colour | no — inert while `colored` is `false` |
| `color_strength` | `Val` channel | `1.0` everywhere | no |
| `opacity` | `Val` channel | present on 396 points (`1045` only), `1.0` | no |
| `color_drift` | `Val` channel | present on 396 points (`1045` only) | no |
| `selected` | bool | editor state | no |

Per-point colouring is therefore **present in the format but unexercised by
these samples** — `colored` is false everywhere, so ignoring `color` costs
nothing here, and would cost a lot in a document that uses it.

### 7.3 Curves and curve points

A `curve` is a sequence of curve points, each referencing one mesh point by
index. A curve is `closed` (one segment per point, last wraps to first) or
open (one fewer segment than points).

| Curve field | Observed | Used? |
|---|---|---|
| `points` | list of curve points (below) | **yes** |
| `closed` | bool | **yes** |
| `num_points` | int, matches `len(points)` | no (redundant) |
| `start_percent` / `end_percent` | `Val` channels, `-0.1` / `1.1` on all 1,088 curves | no — these trim the drawn portion of a line. The defaults extend slightly past both ends. **A keyframed `end_percent` is how Moho animates a line drawing itself on, and this tool would draw the whole line instead.** |
| `profile_layer_uuid`, `profile_curve_id`, `profile_repeat`, `profile_offset` | `""`, `-1`, `16`, `0.0` | no — a "curve profile" that repeats another curve's shape along this one. Unset in all samples. |

Curve point fields — all seven, all used:

| Field | Shape | Meaning |
|---|---|---|
| `point` | int | Index into `mesh.points`. |
| `smoothness` | `Val` channel | Curvature; `0` = sharp corner (handles collapse onto the point). |
| `weight_in` / `weight_out` | `Val` channels | How far each handle reaches toward its neighbour, as a fraction of the distance to it. |
| `offset_in` / `offset_out` | `Val` channels | A small rotation (radians) producing asymmetric curves. |
| `segments_on` | bool | `false` on 375 of 16,378 curve points. `false` means the segment leaving this point is **not drawn** — the path breaks into a fresh subpath. |

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
| `effect_offset` | `Vec2` channel | mostly `{0,0}` | no |
| `fill_allowed` | bool | `true` 730, `false` 229 | no — presumably "this shape may be filled at all", distinct from `has_fill` |
| `combo_blend_anim` | `Val` channel | `0.0`, `1045` only | no — presumably animates a soft boolean blend |
| `3d_thickness` | `Val` channel | `0.125` on all 959 shapes | no |
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
  document; 11 distinct values across the 771 named styles, from `0.002778`
  to `0.092223`). It is a **plain float, not a channel** — Moho does not
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
heavily: 3,430 of 16,227 mesh points have a `width` other than `1.0`. See the
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
| `2` | **0** | Not present in any of these five documents. The module docstring reports having seen it in a real file; there is no sample here to decode it from, and `moho2svg.py` falls through to normal handling for it. |

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
[indices into mesh.points]}`. Seven point-group objects exist across the samples, with six distinct
names: `"Right Hand"` (in two different meshes), `"Left Laces"`, `"Right
Laces"`, `"top lip"`, `"bottom lip"`, and `"bottom Teeth"`.

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
| `line_caps` | int | `1` on all 1,730 style objects | **yes** — `0` butt, `1` round, `2` square (mapping from `LINE_CAP_NAMES`; only `1` is exercised) |
| `fill_style` | obj | on 256 styles | **yes** — gradient fill ([§ 8.3](#83-gradients)) |
| `line_style` | obj | on **25** styles | **no** — a gradient on the *stroke*, same shape as `fill_style`. These 25 styles stroke with a gradient in Moho and a flat colour here. |
| `fill_style_id`, `line_style_id` | int | `9` whenever present | no |
| `brush_name` | str | 20+ distinct values | **yes** ([§ 8.5](#85-resolving-a-brush_name-to-a-file)) |
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
> the `.mohobrush` archive ([§ 8.5](#85-resolving-a-brush_name-to-a-file)),
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

### 8.3 Gradients

`fill_style` (and the unused `line_style`) have this shape:

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
own `effect_scale` / `effect_rotation` — **approximate, not pixel-matched** to
Moho's own differently-parameterised placement.

### 8.4 Brush styles

A named style's line can be a textured "brush" — a small image stamped
repeatedly along the path (jittered in rotation, spaced as a fraction of its
own size) instead of a plain uniform-width line.

- `brush_name` — identifies the brush asset ([§ 8.5](#85-resolving-a-brush_name-to-a-file)).
- `brush_jitter` — random rotation spread, in **radians**, applied per dab.
- `brush_spacing` — dab spacing, as a **fraction of the dab's own diameter**.
- `brush_align` — whether each dab rotates to the local path tangent (in
  addition to the random jitter) or ignores path direction entirely.
- `brush_tint` — whether the (greyscale) texture is recoloured to the
  resolved `line_color`, or used with its own native multi-colour pixels
  as-is. `true` in every style in every sample.

Moho's own per-dab randomisation is not recoverable from the saved document,
so this tool seeds its jitter deterministically per shape instead. See the
module docstring's BRUSH STROKES section, and `docs/exporting-svg.md` § 7 for
the three render paths and their performance.

### 8.5 Resolving a `brush_name` to a file

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

A `BoneLayer`'s `skeleton.bones` is a flat list of 0–157 bones. A bone's
world transform composes with its parent's, with parents resolved regardless
of list order.

Fields used by this tool:

| Field | Shape | Meaning |
|---|---|---|
| `name` | str | Bone name. Also how a Smart Bone dial is matched ([§ 11](#11-actions-and-smart-bones)). |
| `parent` | int | Index into the same `bones` list, or `-1` for a root. |
| `length` | float | Bone length in document units (`0.015`–`0.6` observed). |
| `strength` | float | Influence radius for flexible binding (`0.0`–`0.6` observed; `0.0` on some bones means no influence). |
| `anim_pos` | `Vec2` channel | Animated position, relative to the parent bone. |
| `anim_angle` | `Val` channel | Animated angle in radians. The most-animated channel in the samples after `pose` (302 bones keyframed). |
| `anim_scale` | `Val` channel | Animated scale along the bone. |

Deformation of a mesh layer is one of two modes, decided **per layer**:

- **Rigid** (`parent_bone >= 0`): every point moves exactly as that one bone
  does. 31 of 544 layers.
- **Flexible / region** (`parent_bone == -1`): every point is a
  distance-weighted blend of every bone's transform, or of a named subset's
  (`flexi_bone_subset`, a `"|"`-joined list of bone indices). 513 of 544
  layers. The weight falloff shape (inverse-distance-squared by default) is a
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

  **Ignoring it is currently free, and measurably so.** All 550
  `anim_parent` channels have exactly **one** keyframe, and that single value
  equals the bone's own static `parent` in **550 of 550** cases — zero
  mismatches. That holds even in `ReparentBone.animeproj`, which demonstrates
  the *tool* without ever keyframing a reparent. So `anim_parent` is fully
  redundant with `parent` across this whole sample set, and the risk is
  theoretical until a document that actually keyframes it turns up.
- **Constraints and IK**: `constraints`, `min_constraint`, `max_constraint`,
  `fixed_angle`, `ik_lock`, `ik_global_angle`, `ik_parent_target`,
  `ignored_by_ik`, `bone_enable_arc_solver`, `target_bone`,
  `angle_control_parent` / `_scale` / `_delay`, `pos_control_parent` /
  `_scale` / `_delay`, `scale_control_parent` / `_scale` / `_delay`. All at
  defaults except `pos_control_parent` (`4`, `5` on a few bones) and the
  `min`/`max_constraint` pairs. Constraints only matter while posing in the
  editor; the resulting angles are already baked into `anim_angle`.
- **Scaling behaviour**: `scaling_mode` (`0` on 308 bones, `2` on 242),
  `squash_stretch_scaling` (`0.44` or `1.0`), `max_auto_scaling`. `scaling_mode`
  is not decoded and is a plausible explanation for the intentionally-preserved
  asymmetric bone scale in `Skeleton.world_matrices`.
- **Physics/dynamics**: `bone_dynamics`, `angle_dynamics`, `pos_dynamics`,
  `scale_dynamics`, `wind_dynamics`, `spring_force`, `damping_force`,
  `torque_force`, `physics_*`, and the `pos_`/`scale_` variants of each. All
  disabled in the samples.
- **Editor state**: `hidden`, `shy`, `selected`, `bone_label_showing`,
  `bone_tags`, `offset`, `angle_weight`, `pos_weight`, `scale_weight`,
  `flip_h`, `flip_v`.

---

## 10. Masking

Two *separate* fields are involved:

- `group_mask` on a *container* (`GroupLayer` or `BoneLayer` — the layer type
  does not matter). Observed values: `0` (38 containers, no masking), `2` (53
  containers, masking active), and `1` (**exactly 1** container, a
  `GroupLayer`). This tool treats any non-zero value as "masking active", so
  `1` and `2` behave identically here; whether Moho distinguishes them is not
  decoded. `MeshLayer`/`TextLayer`/`PatchLayer`/`SwitchLayer` do not carry
  the field at all.
- `masking` on each *child* of a masking container:
  - `2` — this child's geometry defines the mask (Moho's UI: something like
    "Add to Mask"). It is still drawn normally — being the mask source does
    not hide it.
  - `1` — "don't mask this layer" — drawn normally, ignoring the mask.
  - anything else (typically `0`, Moho's UI default) — clipped to the union of
    all `masking == 2` siblings in the same container.

Across the samples, `masking` is `0` on 416 layers, `2` on 76, `1` on 52.
Note that a `masking` value is present on children of *non*-masking
containers too (256 such pairs), where it is inert.

This applies uniformly at every nesting depth, **including the document's own
top-level layer** — masking is not special-cased away at the root. A
`masking == 2` sibling does not always carry its own mesh: a `GroupLayer` can
be `masking == 2` purely as a masking *container*, in which case its effective
silhouette is, recursively, whatever its own `masking == 2` child/children
define (the same shapes that already act as *that* container's internal
`group_mask` source).

`mask_expansion` (a bool on every layer, `false` throughout) presumably grows
or shrinks the mask edge; it is not used.

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
`{"name": "<action name>", "pose": 0}` — 15,975 such entries across the
samples, with `pose` an integer `0` in every single one. Present on 393 of 428
`MeshLayer`s, 57 of 61 `GroupLayer`s, 26 of 31 `BoneLayer`s, 5 of 8
`SwitchLayer`s, 4 of 8 `PatchLayer`s, and never on a `TextLayer`.

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

3,999 such poses exist across the samples. Their `pose` channel types are
`Vec2` (2,932), `Val` (933), `Vec3` (120), `Bool` (8), and `String` (6) —
i.e. an action can override any kind of property, but in practice it is
mostly mesh point positions and bone transforms. `pose` is by far the most
keyframed field in these documents (3,999 channels with more than one
keyframe, versus 302 for `anim_angle`, the runner-up).

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

Both top-level lists are **empty in all five documents**, so their element
shape cannot be documented from this evidence. `layercomps` is Moho's
"layer comps" feature (named show/hide sets of layers, used to export
variants of one document). `action_refs` most plausibly holds references to
actions defined outside this document, matching the `layer_ref_*` fields on
layers, but that is a guess, not a finding. Neither is read by this tool.

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

**The patch layer's own `transforms`/`parent_bone`/`flexi_bone_subset`/
`origin` are not used when rendering it**, even though they are present and
look like they ought to matter. Confirmed empirically: every `PatchLayer`
found across the reference documents carries a bizarre, seemingly-unrelated
own transform (e.g. a `0.147` non-uniform Y scale plus an 8.9° rotation on one
hand's `ayasi-Patch`; a uniform `~0.49` scale on `Leg_L-Patch`/`Leg_R-Patch`
in another rig), while its *target* consistently has the identity transform
(`scale: 1`, `translation: 0`). Rendering with the patch's own transform
reproduces exactly that: a squashed sliver floating away from where the target
actually renders. The target's transform (and
`parent_bone`/`flexi_bone_subset`/`origin`) is used instead — i.e. a resolved
patch layer renders as a duplicate of its target, just at a different
point in the draw order. This is a **heuristic**, not a confirmed-exact
reverse-engineering — there is no independent Moho SVG export of a
`PatchLayer`-using document available to verify pixel-for-pixel against.

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

What this tool reads, at a glance. "Exercised" means at least one of the five
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

1. `layer_effects.alpha` — 9 layers should be 60% opaque. ([§ 6.3](#63-common-fields-that-affect-rendering-and-are-not-used))
2. `blend_mode: 1` — 16 layers blend non-normally. ([§ 6.3](#63-common-fields-that-affect-rendering-and-are-not-used))
3. `style.line_style` — 25 styles stroke with a gradient, rendered flat. ([§ 8.1](#81-named-styles-docstyles))
4. `extra_sketchy` / `extra_lines: 5` — 2 layers should draw repeated jittered strokes. ([§ 6.4](#64-type-specific-fields))
5. `channel.interp` — non-linear timing on `pose`/`anim_*`; exact at keyframes, off between them. Only matters for a `--frame N` that is not a keyframe. ([§ 5.3](#53-the-interp-entries))
6. `bone.scaling_mode: 2` — 242 bones; possibly related to the preserved asymmetric bone scale. ([§ 9](#9-bones-and-skinning))
7. `mesh.curve_interpretation: 0` — 2 meshes differ from the other 426. ([§ 7.1](#71-the-mesh-object))
8. `shape.fill_allowed: false` — 229 shapes. Interaction with `has_fill` undecoded. ([§ 7.4](#74-shapes-and-edges))

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

Items 6–8 are *undecoded*, not *known-wrong*: the samples set them to a
non-default value, but nothing proves the current output is incorrect for
them.

### 13.3 Ignored and **not** exercised — untested gaps

Present in the format, but at default values throughout the samples, so
ignoring them is currently invisible: `channel.mute`, `channel.split`,
`bone.anim_parent` (redundant with `parent` on all 550 bones — see
[§ 9](#9-bones-and-skinning)),
`doc.animated_values` (camera), `curve.start_percent`/`end_percent`, curve
profiles, `point.colored`/`color`/`opacity`, `layer_effects.visibility` and
the other five effect channels, `layer_outline`, `layer_shadow`,
`layer_shading`, `perspective_shadow`, `layer_color`, `motion_blur`,
`timing_offset`, `layer_ordering`, fill/line textures, `layer_ref_*`,
`distortion_layer_uuid`, follow-path fields, all physics fields, all bone
constraint/IK fields, `project_data.global_render_style_*`, `mesh.groups`,
`mesh.shape_order`, `shape.3d_thickness`/`effect_offset`/`combo_blend_anim`,
`skeleton.binding_mode`, `quality_flags`, and the `TextLayer` font/balloon
fields.

The riskiest of these are the ones a real production document would plausibly
use: **`layer_effects.visibility`** (animated show/hide),
**`curve.end_percent`** (a line drawing itself on), **`timing_offset`**,
**`project_data.global_render_style_*`**, and **the camera channels**.

---

## 14. Known unknowns

This is a living reverse-engineering effort, not a specification. Fields whose
*values* are observed but whose *meaning* is not decoded:

- `combo_mode: 2` — reported in the module docstring, absent from all five
  sample documents. ([§ 7.8](#78-boolean-shape-combination))
- `channel.interp.t` / `.im` / `.in` / `.s` / `.h` / `.v1` / `.v2` / `.b` —
  the interpolation-type enum and its parameters. ([§ 5.3](#53-the-interp-entries))
- `channel.ref` — `false` everywhere.
- `group_mask: 1` versus `2` — one container uses `1`. ([§ 10](#10-masking))
- The correct mask contribution of a `masking == 2` sibling whose own outline
  is tapered or brush-styled (a plain uniform stroke is handled — see
  [§ 10](#10-masking)).
- `blend_mode: 1` — 16 layers. ([§ 6.3](#63-common-fields-that-affect-rendering-and-are-not-used))
- `bone.scaling_mode` (`0`/`2`), `skeleton.binding_mode` (always `1`),
  `mesh.curve_interpretation` (`0`/`1`), `quality_flags` (a bit field),
  `face_camera_mode` (always `2`), `shape.fill_allowed`,
  `PatchLayer.target_layer_id`, `fill_style_id`/`line_style_id` (always `9`).
- `layercomps` and `action_refs` element shapes — both lists empty
  everywhere. ([§ 11.4](#114-action_refs-and-layercomps))
- The first number of an old-style `brush_name` suffix.
  ([§ 8.5](#85-resolving-a-brush_name-to-a-file))

Plus the approximations already noted: gradient placement precision, the
flexible bone-weight falloff shape for overlapping influence, the
`PatchLayer` transform heuristic ([§ 12](#12-patch-layers)), and the brush
stroke simplifications ([§ 8.4](#84-brush-styles)).

See the module docstring's KNOWN GAPS section for the rendering-side list. If
you find a real document that contradicts something here, prefer the evidence
in the document over what is written in this file — and say so, since every
count above is measured from five files only.
