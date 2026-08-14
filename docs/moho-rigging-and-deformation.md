# Moho Rigging and Deformation

Bones, Smart Warp, and the mesh-level fields that constrain how artwork is
deformed.

Moho has three different ways to bend artwork, and they are easy to confuse:

1. **Bones** — a skeleton deforms the points of a mesh (or moves a whole
   layer rigidly). This is the main rigging system and the only one
   `moho2svg.py` implements.
2. **Smart Warp** — a separate deformation mesh laid over a layer or a group.
   No file in the sample set uses it, so this document can only describe the
   hooks the format leaves for it.
3. **Mesh-level fields** — per-point, per-curve and per-layer settings that
   restrict or reshape what the other two do (bone subsets, point groups,
   curve profiles, curve trimming, deformer flags).

Companion documents:

- [`moho-project-file-format.md`](moho-project-file-format.md) — the full
  field reference. § 9 is the short version of bones; this document is the
  long version.
- [`moho-animation-and-transform.md`](moho-animation-and-transform.md) — how
  channels store motion, and how the transform stack composes.
- [`moho-export-pipeline.md`](moho-export-pipeline.md) — how `moho2svg.py` walks a
  document and emits SVG.

This document does not repeat those. It goes deeper on the rig itself, and it
says clearly which parts are read from real files and which parts are not.

---

## 1. Scope and evidence base

Every count here was measured from the 19 project files in the (gitignored)
`moho/` directory: 17 `.animeproj` and 2 `.mohoproj`, in three format
generations — `1021` (1 file), `1038` (17 files) and `1045` (1 file).

The sample contains:

| Item | Count |
|---|---|
| Layers of all types (the `layers` tree) | 842 |
| `BoneLayer` | 47 |
| `skeleton` objects (on `BoneLayer` **and** `SwitchLayer`) | 64 |
| `skeleton` objects with a non-empty `bones` list | 42 |
| Bones | 850 |
| Bones per skeleton | 1 – 157 |

Every layer count in this document walks the `layers` tree only, so it stops
at 842. `moho-project-file-format.md` § 6.2 sometimes reports 876 instead,
because it also counts the `MeshLayer` nested inside each of the 34
`TextLayer`s. Both are right; check which population a number refers to
before comparing two documents.

The 22 skeletons with an empty `bones` list are the 17 `SwitchLayer`
skeletons plus 5 `BoneLayer` skeletons. A `SwitchLayer` always carries a
`skeleton` object; it is empty in every sample, so do not treat "has a
`skeleton` key" as "is a bone layer".

Claims are labelled the same way as the animation document:

- **Confirmed** — read directly from the files, with counts.
- **Inference** — the best reading of the evidence, with the evidence given.
- **Not decoded** — observed, but the meaning is unknown. Not guessed.
- **Not in the sample** — the feature exists in Moho, but no file here uses
  it, so nothing about its storage is documented.

Section [9](#9-reproducing-the-numbers) shows how to recompute the numbers.

---

## 2. The bone system

### 2.1 Where a skeleton lives

A skeleton belongs to a `BoneLayer`:

```
BoneLayer
  skeleton: { type, binding_mode, bones: [ ... ], bones_groups? }
  layers:   [ the layers this skeleton can deform ]
```

The bones deform the layers **nested inside** that `BoneLayer`. A layer
outside it is never touched by that skeleton. Nesting can be deep: a mesh
several groups below the bone layer is still deformed, and it is deformed in
the *bone layer's own coordinate space* — after the local matrices between the
mesh and the bone layer, and before the bone layer's own matrix. See
[`moho-animation-and-transform.md` § 5.2](moho-animation-and-transform.md#52-the-chain-and-why-skinning-is-not-just-another-matrix).

`bones` is a **flat list**, not a tree. `bone.parent` is an index into that
same list, or `-1` for a root bone. Parents are **not** guaranteed to appear
before their children, so any code that computes world matrices must resolve
each bone's parent chain on demand instead of walking the list in order
(`Skeleton.world_matrices` in `moho2svg.py` does this, memoising visited
bones).

### 2.2 The bone record

All 40+ bone fields, grouped by what they are for. "Used" means
`moho2svg.py` reads it when rendering.

**Shape and identity (used)**

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Bone name. Also the key that matches a Smart Bone dial to an action ([§ 4](#4-smart-bones-in-one-page)). |
| `parent` | int | Index into the same `bones` list, `-1` for a root. |
| `length` | float | Bone length in document units. Observed `0.003117` – `0.981441`. |
| `strength` | float | Influence radius for flexible binding. Observed `0.0` – `7.654676`; **`0.0` on 241 of 850 bones**, which means "this bone does not deform the mesh at all". |

**Pose (used)**

| Field | Type | Meaning |
|---|---|---|
| `anim_pos` | `Vec2` channel | Position relative to the parent bone. |
| `anim_angle` | `Val` channel | Angle in radians. The most keyframed bone channel: 383 of 850 bones have more than one key. |
| `anim_scale` | `Val` channel | A single scalar scale along the bone. Note this is **one number**, unlike a layer's per-axis scale. First value is `1.0` on all 850 bones. |

**Constraints and rig helpers (not used — [§ 3](#3-bone-constraints-and-rig-helpers))**

`constraints`, `min_constraint`, `max_constraint`, `fixed_angle`,
`angle_control_parent` / `_scale` / `_delay`, `pos_control_parent` / `_scale`
/ `_delay`, `scale_control_parent` / `_scale` / `_delay`, `target_bone`,
`ik_lock`, `ik_global_angle`, `ik_parent_target`, `ignored_by_ik`,
`bone_enable_arc_solver`, `anim_parent`.

**Scaling behaviour**

`scaling_mode` — **used**, and decoded as the "Squash and stretch scaling"
switch (see [§ 2.3](#23-from-bones-to-matrices)). `max_auto_scaling` — used,
as the IK auto-stretch cap. `squash_stretch_scaling` — a magnitude (`1.0` on
831 of 850 bones), still unused.

**Physics / dynamics (not used)**

`bone_dynamics`, `angle_dynamics`, `pos_dynamics`, `scale_dynamics`,
`wind_dynamics`, `torque_force`, `spring_force`, `damping_force`, and the
`pos_` / `scale_` variants of the three force fields, plus `physics_radius`,
`physics_return_to_zero`, `physics_motor_speed`, `physics_torque`,
`physics_lock_tip`.

**Editor state (not used)**

`selected`, `hidden`, `shy`, `bone_label_showing`, `bone_tags`,
`angle_weight`, `pos_weight`, `scale_weight`.

**`flip_h` / `flip_v` — used (correcting an earlier "editor state" claim)**

Bool channels that mirror everything the bone drives, applied by
`Skeleton.world_matrices` exactly the way `Layer.local_matrix` applies a
*layer's* own flips: `flip_h` negates the matrix's first column (the bone's
own direction axis, the one `anim_scale` scales), `flip_v` the second.

Rare but real: exactly **one** bone across all 19 sample documents ever sets
either — `SketchBone.animeproj`'s `B23`, the left ankle that drives the
`ayak-sol` foot layer through its `flexi_bone_subset`, keyframed `flip_h`
`False` at frame 0 → `True` at frame 44 (an animator turning the foot around
mid-walk rather than re-drawing it). While this was classed as editor state
and ignored, that foot rendered pointing backwards against its own direction
of travel for the whole second half of the walk. Fixing it cut the foot's
pixel error against the reference frames by **51.9%** (measured over all 120
frames of `moho/SketchBone/`).

**Special case: `offset`** — see [§ 3.7](#37-offset-the-offset-bone-tool). It
is listed under "editor state" in
[`moho-project-file-format.md` § 9](moho-project-file-format.md#9-bones-and-skinning),
but it is **not** at its default in every file, so it deserves its own entry.

### 2.3 From bones to matrices

Each bone has a local matrix built from its own pose channels, then composed
with its parent's world matrix:

```
local = | cos(angle)·scale   -sin(angle)   pos.x |
        | sin(angle)·scale    cos(angle)   pos.y |

world(i) = world(parent) · local(i)      (world(i) = local(i) if parent < 0)
```

Two things about this are worth knowing:

- **Only the first column is scaled.** This asymmetry is deliberate in
  `moho2svg.py`: it matched every available reference render, and no sample
  exercises a bone whose `anim_scale` is far from `1.0` in a way that could
  tell asymmetric from uniform scaling apart. `scaling_mode` (values `0` and
  `2`) is a plausible explanation and is **not decoded**. Do not "fix" it
  without new reference evidence.
- **The rest pose is frame 0.0**, not the first keyframe. See
  [`moho-animation-and-transform.md` § 2.3](moho-animation-and-transform.md#23-frame-numbering-and-what-frame-0-means).

### 2.4 How a point is actually deformed

For one skeleton at one frame, the deformation is built once and reused for
every point:

```
rest(i)         = world matrix of bone i at frame 0.0
pose(i)         = world matrix of bone i at the requested frame
rest_to_pose(i) = pose(i) · rest(i)⁻¹
rest_p0(i)      = rest(i) applied to (0, 0)          # bone base, rest pose
rest_p1(i)      = rest(i) applied to (length, 0)     # bone tip, rest pose
```

Then, for a point `p` (flexible binding):

```
for each candidate bone i:
    if strength(i) <= 0: skip                       # hard gate, checked first
    d = distance from p to the segment rest_p0(i)–rest_p1(i)
    w = falloff(d, strength(i))                     # default: 1 / d²
    accumulate rest_to_pose(i)·p, weighted by w
p' = weighted average, or p unchanged if no bone contributed
```

The **falloff shape is a heuristic**. `moho2svg.py` ships four
(`inv_d2`, `linear`, `cut_d2`, `hermite`) and uses inverse-distance-squared;
no available reference could separate them, and the case where two bones both
have strong influence near one point is the unvalidated one.

Note what `strength` does *not* do in the default falloff: `1/d²` ignores its
value entirely, so `strength` acts only as an on/off gate there. The
`linear`, `cut_d2` and `hermite` falloffs do use it as a radius.

### 2.5 How a layer attaches to the skeleton

This is decided **per layer**, by `parent_bone` on the layer (not by anything
on the bone):

| `parent_bone` | Meaning | Count (842 layers) |
|---|---|---|
| `>= 0` | **Rigid**: every point follows that one bone exactly. | 54 |
| `-1` | **Flexible / region**: distance-weighted blend of many bones. | 779 |
| `-3` | Observed only on `ImageLayer`, always together with a non-empty `flexi_bone_subset`. **Not decoded** — likely a raster-specific bone-warp mode. `moho2svg.py` falls through to flexible handling, which is unconfirmed. | 9 |

Flexible binding can be narrowed by `flexi_bone_subset` on the layer: a
**string** of `"|"`-joined bone **indices**, e.g. `"4|5|11"`. Non-empty on
**319 of 842 layers**, with 1 – 24 indices (mean 2.4). When it is empty, every
bone in the skeleton is a candidate.

Common mistake: `flexi_bone_subset` holds *bone* indices, while
`mesh.groups` holds *point* indices ([§ 6.1](#61-point-groups-meshgroups)).
They are different namespaces and never refer to each other.

### 2.6 Skeleton-level and bone-layer-level fields

| Field | Where | Observed | Used? |
|---|---|---|---|
| `binding_mode` | `skeleton` | `1` on 41 skeletons, **`2` on 1** (`OffsetBoneTool.animeproj`, layer `Happy Dance`). **Not decoded.** | no |
| `bones_groups` | `skeleton` | Present only in the `1045` document, and empty there. Presumably a bone-grouping/selection aid. | no |
| `grandpa_bone` | `BoneLayer` | `true` on all 47 bone layers. Lets bones bind layers nested deeper than direct children. | no (the deform chain already crosses arbitrary nesting) |
| `flexi_bone_elbow` | `BoneLayer` | `false` on all 47. **Not decoded.** | no |
| `gravity`, `wind` | `BoneLayer` | Bone-physics environment; on exactly one bone layer in the sample. | no |

> **Correction.** An earlier revision of
> [`moho-project-file-format.md` § 6.4](moho-project-file-format.md#64-type-specific-fields)
> said `binding_mode` is `1` on every sampled skeleton. That is wrong: one
> skeleton uses `2`. Since nothing branches on the field, no output changed,
> but the claim was too strong.

### 2.7 What each format generation added

The bone record grew over time. Fields present in **only** the `1045`
document (`Bandit.mohoproj`, 28 bones):

`angle_control_delay`, `pos_control_delay`, `scale_control_delay`,
`angle_dynamics`, `pos_dynamics`, `scale_dynamics`, `wind_dynamics`,
`pos_torque_force`, `pos_spring_force`, `pos_damping_force`,
`scale_torque_force`, `scale_spring_force`, `scale_damping_force`,
`angle_weight`, `pos_weight`, `scale_weight`, `bone_tags`,
`bone_label_showing`, `bone_enable_arc_solver`.

Fields missing from the `1021` document only: `ignored_by_ik`.

Practical consequence: a reader must treat every bone field as optional and
supply a default. Do not assume a field exists because a newer file has it.

---

## 3. Bone constraints and rig helpers

Everything in this section is **read but not applied** by `moho2svg.py`. The
important question for an exporter is not "is it implemented?" but "does
ignoring it change the picture?" — and the answer differs per feature.

The dividing line: a feature that Moho **bakes into `anim_angle` / `anim_pos`
when the artist poses** is safe to ignore. A feature that Moho **evaluates at
playback time** is not, because nothing in the file contains its result.

### 3.1 Angle constraints

`constraints` (bool), `min_constraint`, `max_constraint` (radians).

- **Confirmed**: `constraints: true` on **158 of 850 bones**, across 11
  documents. The default pair is `±1.2217` rad (±70°) — present on 735 bones
  whether or not constraints are enabled. Other observed pairs are narrower
  (`±0.4363` = ±25°, `±0.1745` = ±10°, `±0.5236` = ±30°).
- **Effect of ignoring**: none for a still frame. Constraints limit what the
  artist could dial in; the angle that survived the limit is what was written
  to `anim_angle`.
- **Where it would matter**: an editor, or an IK solve done by the reader.

### 3.2 Independent angle (`fixed_angle`)

- **Confirmed**: `true` on **45 of 850 bones**, across 10 documents.
- **Meaning (inference)**: the bone keeps a fixed angle in the skeleton's
  space instead of inheriting its parent's rotation. This is Moho's
  "Independent Angle" flag; `IndependentAngle.animeproj` is the tutorial file
  for it and sets it on 9 bones.
- **Effect of ignoring**: **unverified, and potentially visible.** If Moho
  applies it while composing world matrices, then a rig whose parent bone
  rotates will place the child at the wrong angle here. If instead the artist's
  keys already encode the result, ignoring it is free. No reference render of
  a `fixed_angle` rig was available to settle this. Treat as an open risk
  [🟠 4/10 that it is safe to ignore in general].

### 3.3 Control bones

Nine fields, three groups of three:
`angle_control_parent` / `angle_control_scale` / `angle_control_delay`, and
the same for `pos_` and `scale_`.

- **Confirmed**: `angle_control_parent >= 0` on **4 bones**,
  `pos_control_parent >= 0` on **5**, `scale_control_parent >= 0` on **4** —
  in `ControlBones.animeproj` (2 bones driven on all three channels),
  `BoneDynamics.animeproj`, `Rabbit.animeproj`, `AddBone.animeproj`.
- Scales are `1.0` everywhere except one bone in `BoneDynamics.animeproj`
  whose `pos_control_scale` is `{x: -2.0, y: -2.0}` (a doubled, mirrored
  follow). Delays are `0` everywhere except `scale_control_delay: 8` on one
  bone in `Bandit.mohoproj`.
- **Meaning**: bone A's angle/position/scale is driven by bone B's, times a
  scale, optionally delayed by N frames.
- **Effect of ignoring**: **real, and evaluated at playback time.** The driven
  bone's own `anim_*` channel does not contain the driven value, so a
  controlled bone renders unmoved. Small in this sample (13 driven channels in
  total), but it is a true miss, not a theoretical one.

### 3.4 IK and target bones

`target_bone` (a `Val` channel holding a bone index), `ik_lock`,
`ik_global_angle`, `ik_parent_target`, `ignored_by_ik`,
`bone_enable_arc_solver`.

- **Confirmed**: `target_bone` is set (not `-1`) on **41 of 850 bones**,
  across **14 of 19 documents** — so this is the most widely used rig helper
  in the sample. `ik_lock` is `false` and `ik_global_angle` is `0.0` on all
  850 bones; every `target_bone` channel has exactly one keyframe.
- **Effect of ignoring**: **usually none, sometimes real.** When the artist
  posed the limb with IK in the editor, the solved angles were written to
  `anim_angle`, so replaying the channels reproduces the pose. It becomes a
  miss when the target itself moves and the solve is expected to happen at
  playback — e.g. a foot pinned to a moving target bone.
- `MaximumIKStrethching.animeproj` and `TargetBone.animeproj` are the
  tutorial files for this behaviour, and are the right place to test a future
  IK implementation.

### 3.5 Bone dynamics (spring physics)

- **Confirmed**: `bone_dynamics` is `true` on **115 of 850 bones**, across 6
  documents — `WhatIsBone` (52), `Bandit` (28, i.e. every bone in the file),
  `AddBone` (21), `BoneDynamics` (6), `Rabbit` (6), `ControlBones` (2). It is
  a `Bool` **channel** and is keyframed in `BoneDynamics.animeproj` (14
  channels have more than one key across the sample).
  `angle_dynamics` is `true` on 2 bones in `Bandit.mohoproj`; `pos_`,
  `scale_` and `wind_` dynamics are `false` everywhere.
- **Effect of ignoring**: **exercised and visible.** Moho adds the spring
  motion on top of the keyed pose at playback time. A channel-only exporter
  renders the keyed pose with no follow-through or overlap, and the error
  grows with distance from a keyframe.
- The forces that shape it: `spring_force`, `damping_force`, `torque_force`
  (22 of Bandit's bones share `2.0 / 1.0 / 2.0`, 6 are tuned individually).

### 3.6 Scaling behaviour

| Field | Observed | Note |
|---|---|---|
| `scaling_mode` | `0` on 586 bones, `2` on 264 | **Decoded: this is Moho's per-bone "Squash and stretch scaling" switch.** `2` = on (scale along the bone only), `0` = off (ordinary uniform scale). Spotted in `SketchBone.animeproj`'s `kafasi` rig, where the two bones carrying each ear (`B2`/`B3`, `B4`/`B5`) are `2` and the third bone in the same `flexi_bone_subset` (`B20`, `B19`) is `0` — matching what Moho's own bone constraints panel shows. `Skeleton.world_matrices` now applies the asymmetry only for `2`. |
| `squash_stretch_scaling` | `1.0` on 831 bones; also `0.41`, `0.61`, `0.7`, `2.0`, `10.0` | How much a scaled bone squashes across its length. |
| `max_auto_scaling` | `1.0` on 804 bones; up to `10.0` | Caps automatic stretching (IK stretch). |

Ignoring all three is safe only while `anim_scale` stays at `1.0`, which is
true for the first keyframe of every bone in the sample but **not** across
time: 3 documents keyframe `anim_scale` on many bones (`Bandit` 25,
`BoneStrengthTool` 22, `SketchBone` 55).

### 3.7 `offset` (the Offset Bone tool)

`offset` is a plain `Vec2` (not a channel).

- **Confirmed**: non-zero on **5 bones**, all in `OffsetBoneTool.animeproj` —
  the tutorial file for Moho's Offset Bone tool. Zero on the other 845.
- **Observation**: on those 5 bones, `offset` is close to the negative of
  `anim_pos` (for example `anim_pos = {0.074, 0.667}` with
  `offset = {0.0, -0.596}`). That is consistent with the tool's purpose:
  move where a bone *sits* without re-binding the artwork that already
  follows it.
- **Two readings, both consistent with the data** —
  (a) `offset` shifts only how the bone is drawn/edited, and deformation uses
  `anim_pos` alone (then ignoring it is exactly right); or
  (b) `offset` shifts the bone's actual base, and the binding distances were
  captured before the shift (then ignoring it changes flexible-binding
  weights, because `rest_p0` / `rest_p1` move).
  **Not decoded** — a Moho reference render of `OffsetBoneTool.animeproj`
  would settle it in one comparison [🟡 5/10 that ignoring it is correct].
- Note that a constant `offset` would cancel out of `rest_to_pose`
  (`pose · rest⁻¹`) even under reading (b). Only the *distance weighting*
  would change, so any error would be a soft weighting error, not a gross
  displacement.

### 3.8 Summary: what ignoring each feature costs

| Feature | Baked into channels? | Cost of ignoring | Exercised in the sample? |
|---|---|---|---|
| Angle constraints | yes | none | 158 bones, 11 docs |
| Bone dynamics | **no** | missing secondary motion, grows off-key | 115 bones, 6 docs |
| Control bones | **no** | driven bone does not move | 13 channels, 4 docs |
| IK / `target_bone` | usually | wrong limb when the target moves | 41 bones, 14 docs |
| Independent angle | unknown | possibly wrong child angle | 45 bones, 10 docs |
| `offset` | unknown | possibly shifted binding weights | 5 bones, 1 doc |
| `anim_parent` (reparenting) | n/a | none — 850/850 match static `parent` | never keyframed |
| `squash_stretch_scaling`, `max_auto_scaling` magnitudes | n/a | scale magnitude detail | `scaling_mode` itself is now decoded and used |

---

## 4. Smart Bones in one page

Smart Bones are part of the bone system, but their storage is the *action*
system, so the details live elsewhere:
[`moho-project-file-format.md` § 11](moho-project-file-format.md#11-actions-and-smart-bones)
and
[`moho-animation-and-transform.md` § 7](moho-animation-and-transform.md#7-actions-and-smart-bones).

The one-paragraph version, because a bone-system document is incomplete
without it:

A **dial bone** is a bone whose *name* matches an action name on the same
bone layer. Turning that bone does not deform anything by itself — instead,
its current angle is looked up **backwards** through the action's own pose
curve for that bone (`Channel.frame_for_value`), producing a frame number
inside the action. Every channel in the document that carries a pose for that
action is then evaluated at that frame, overriding its normal value. That is
how "rotate this dial 30°" becomes "the mouth is half open".

Two consequences that catch people out:

- A dial bone's own angle must be read with the **raw** evaluator, bypassing
  the override machinery it is part of — otherwise the lookup recurses into
  itself.
- Smart Bone state is part of the skinning cache key: the same skeleton at the
  same frame can deform differently under different active actions.

---

## 5. Smart Warp

### 5.1 What it is — background, not evidence

> **Not in the sample.** No file in `moho/` uses Smart Warp: a search for any
> JSON key containing "warp" across all 19 files returns **zero hits**. The
> paragraphs in this sub-section come from general knowledge of Moho as an
> application, not from any file examined here. They are orientation only —
> do **not** implement against them. [🟠 4/10]

Smart Warp is a deformation feature added in the Moho 13 generation. Instead
of bending artwork with bones, the artist puts a **warp mesh** over a layer or
a group: a grid of quads (optionally subdivided, optionally triangulated)
that surrounds the artwork. Dragging a warp-mesh point bends everything under
it. Because the warp mesh is independent of the artwork's own points, it can
deform things bones handle badly — a whole group at once, raster/image layers,
cloth-like bends, squash and stretch of a complete character.

The warp mesh is itself animatable, so it can be keyframed like any other
Moho property, and can be driven from an action (and therefore from a Smart
Bone dial).

The practical difference from bones, for anyone building an exporter: bone
deformation is *sparse* (a handful of matrices blended per point), while a
warp mesh is *dense* (a piecewise mapping defined by a grid). They are not
interchangeable, and a bone-only implementation cannot approximate one with
the other.

### 5.2 What the files actually show

These are **confirmed** observations. Whether they belong to Smart Warp is
inference, and is marked as such.

| Field | Where | Observed | Reading |
|---|---|---|---|
| `distortion_layer_uuid` | every layer in the `1038` and `1045` files (827 layers); **absent** in the `1021` file | `""` in all 827 | A layer pointing at *another layer* used as a distortion mesh. The name is a strong match for a warp-mesh reference. **Inference** [🟡 6/10]. |
| `triangulated` | every `MeshLayer` in the `1045` file (21); absent in `1038` and `1021` | `false` on all 21 | A mesh can be triangulated — which is what a deformation mesh needs and a drawing mesh does not. |
| `squashable_deformer` | same 21 layers | `false` on all 21 | The word *deformer* implies a mesh can act as one. |
| `frame_zero_deformer` | same 21 layers | `true` on all 21 | Presumably "this deformer is defined at frame 0", matching the rest-pose-at-frame-0 convention bones already use. |

The generation pattern is the useful part: **all three deformer flags appear
only in the newest format generation in this sample (`1045`)**, and none of
them exists in `1038` or `1021`. That is consistent with a
deformation-mesh feature arriving in the same release family as those files,
and it means an older reader will never see them.

Related but separate: `parent_bone == -3` on 9 `ImageLayer` instances, always
with a non-empty `flexi_bone_subset` ([§ 2.5](#25-how-a-layer-attaches-to-the-skeleton)).
That is a raster deformation mode, not Smart Warp, and is equally undecoded.

### 5.3 What to do today

- **Do not guess the format.** No structure, no field names, no point layout
  for a warp mesh can be stated from this sample.
- **Do detect it.** A reader can cheaply flag a document as "possibly
  unsupported" when any layer has a non-empty `distortion_layer_uuid`, or when
  a mesh layer has `squashable_deformer: true`. `moho2svg.py` does neither
  today; it would silently export the undeformed artwork.
- **To document it properly**, one file is enough: save any Moho project that
  uses a Smart Warp mesh into `moho/`, then re-run the census in
  [§ 9](#9-reproducing-the-numbers). The new keys will stand out immediately,
  because the current key set is fully enumerated.

---

## 6. Mesh-level constraints

These are the fields that restrict or reshape deformation at the mesh, curve
and point level — as opposed to at the bone. Most are inert in the sample,
but each one changes the picture when it is not.

### 6.1 Point groups (`mesh.groups`)

`[{"type": "PointGroup", "name": "...", "points": [indices into mesh.points]}]`

- **Confirmed**: non-empty on **10 meshes** (of 648 in the sample), holding
  **14 point-group objects** in total, all in the two nearly
  identical tutorial rigs `ReparentBone.animeproj` and
  `SelectandReparentBoneTool.animeproj`. Names observed: `Right Hand`
  (twice), `Left Laces`, `Right Laces`, `top lip`, `bottom lip`,
  `bottom Teeth`.
- Nothing else in those files references a group by name.
- **Reading**: an editor convenience for selecting a set of points (and the
  natural target for point-level operations such as binding a group of points
  to a bone). Ignoring it costs nothing here.
- Do not confuse the index space with `flexi_bone_subset`
  ([§ 2.5](#25-how-a-layer-attaches-to-the-skeleton)): these are **point**
  indices.

### 6.2 Curve profiles

`curve.profile_layer_uuid`, `profile_curve_id`, `profile_repeat`,
`profile_offset`.

- **Confirmed**: unset in every curve — `""`, `-1`, `16`, `0.0`. That is
  1,932 curves in the `layers` tree, or 3,045 counting the meshes nested
  inside `TextLayer`s (the population
  [`moho-project-file-format.md` § 7.3](moho-project-file-format.md#73-curves-and-curve-points)
  uses).
- **Reading**: a profile repeats another curve's shape along this one (a
  decorative/ornamental stroke). It constrains the drawn geometry, not the
  deformation.
- Ignoring it is free here, and would produce a plain curve instead of a
  profiled one in a document that uses it.

### 6.3 Curve trimming (`start_percent` / `end_percent`)

- **Confirmed**: `start_percent` is `-0.1` on all 3,045 curves;
  `end_percent` is `1.1` on all but 3 (which are `1.008296`, the same "nose"
  curve shared across three sibling tutorial files). Both are `Val`
  **channels**, and none is keyframed.
- The defaults deliberately extend slightly past both ends of the curve.
- **Why it matters**: a keyframed `end_percent` is how Moho animates a line
  drawing itself on. A reader that ignores the channel draws the whole line
  from frame 0. Not exercised here, but it is a common animation technique,
  so treat it as a likely gap for real production files rather than a rare
  one.

### 6.4 Deformer flags on a mesh layer

`triangulated`, `squashable_deformer`, `frame_zero_deformer` — see
[§ 5.2](#52-what-the-files-actually-show). They exist only in the `1045`
generation and are all at their defaults there.

### 6.5 Per-layer deformation inputs, in one place

When answering "why did this layer move like that?", these are the fields to
check, in the order they apply:

1. `parent_bone` — rigid to one bone, flexible, or the undecoded `-3`.
2. `flexi_bone_subset` — which bones are even candidates.
3. `strength` on each candidate bone — `0.0` removes the bone entirely.
4. `transforms` on the layer and every ancestor — the ordinary matrix stack.
5. `origin` — the pivot for the layer's own rotation and scale.
6. Active Smart Bone actions — they can override any channel above.

Only after all six does the mesh's own geometry (curves, Bezier
reconstruction) come into play.

---

## 7. What `moho2svg.py` implements

Confirmed by reading the code (`Bone._build`, `Skeleton.world_matrices`,
`Skinner`, `build_deform_chain`, `Layer.parent_bone`,
`Layer.flexi_bone_subset`).

| Area | Status |
|---|---|
| Bone hierarchy, world matrices, out-of-order parents | implemented |
| Rigid binding (`parent_bone >= 0`) | implemented |
| Flexible binding + `flexi_bone_subset` + `strength` gate | implemented, falloff is a heuristic |
| Deforming in the bone layer's own space, at any nesting depth | implemented |
| Smart Bone dials driving actions | implemented |
| 2-bone Target IK (`target_bone`) + auto-stretch (`scaling_mode`/`max_auto_scaling`) | implemented — see `Skeleton._solve_ik_pair` |
| Bone `flip_h` / `flip_v` | implemented — see `Skeleton.world_matrices` |
| Bone constraints, control bones, dynamics, `offset`, `anim_parent` | read into the model, **never applied** |
| `binding_mode`, `grandpa_bone`, `flexi_bone_elbow`, `bones_groups` | ignored |

### 7.1 Audit: which unread fields could still matter

Every field below was checked against all 19 sample documents, to separate
"unread and harmless here" from "unread and a real gap". Recording the
negative results matters as much as the positive ones: it stops the same
field being re-investigated later.

| Field | Where | Finding |
|---|---|---|
| `anim_parent` | bone | **Redundant here.** Never animated, and never differs from the static `parent`, on any bone in any of the 19 documents — including `ReparentBone.animeproj`, whose whole subject is re-parenting. |
| `angle_/pos_/scale_control_parent` | bone | Not set on any bone of `SketchBone.animeproj`. Real elsewhere (`ControlBones.animeproj`), still unapplied. |
| `flexi_bone_elbow` | layer | `False` on all 101 layers that carry it. Name suggests the joint-smoothing this tool lacks, but no sample turns it on, so its effect cannot be observed. |
| `binding_mode` | skeleton | Effectively constant: `1` on 63 of 64 skeletons, `2` on one (`OffsetBoneTool.animeproj`'s "Happy Dance"). Not a per-layer switch. |
| `mesh.points[].parent` | mesh point | **Per-point bone binding — a real, unimplemented feature.** See below. |
| `mesh.groups` | mesh | Point groups. Empty on all but 10 meshes (`ReparentBone` / `SelectandReparentBoneTool` hands and feet, `Closed`). Still unread. |
| `layer.timing_offset` | layer | Shifts a layer's whole animation in time. `0` on 839 layers, **`45` on 3** — `Rabbit.animeproj`'s `ProsBox`, `PROS` and `T I  PS`. Those three are therefore 45 frames out of step in any animated export. Unread. |

**Per-point bone binding (`mesh.points[].parent`) is used far more widely
than an earlier revision of this table claimed.** `MeshPoint._build` reads
only `position` and `width`, so the field is dropped entirely. Corpus-wide
distribution of the value: `-2` on 7,365 points (use the layer's own
binding), `-1` on 551, and **a specific bone index on roughly 4,000 points
spread over 119 meshes**. `Bandit.mohoproj` leans on it heavily — `Leg_F`
binds 9 of its 28 points to bone 11, `Ears` binds all 20 across bones
2/20/21/22/23, and `Body`, `BlueSpot`, `YellowSpot`, `Back_Texture` each
pin part of themselves. Those meshes currently deform by layer binding
instead of the artist's explicit per-point assignment.

It is **not** what tore `SketchBone.animeproj`'s arms apart: every point of
`kol-sol-ust`/`kol-sol-alt`/`kol-sag-ust`/`kol-sag-alt` is `-2`, and that
document uses point binding on only 2 meshes (both ears, 5 points each to
bone 0). The arm tear comes from single-bone `flexi_bone_subset` binding
being rigid — see `Exporter._effective_subset`.

**Implemented, measured, and left DISABLED** (`--point-bones`,
`RenderSettings.point_bone_binding`). Honouring a per-point bone requires
deforming `mesh.points` *before* `CurveGeometry.build` rather than deforming
finished control points after, because a Bezier handle belongs to no single
point and so has no bone to follow. `Exporter._geometry_and_mapper` picks
that order only for a mesh that actually uses the field, since the two orders
are not interchangeable — handle reconstruction commutes with a similarity
transform but not with the non-uniform scale layer transforms and
`Skeleton.world_matrices`'s asymmetric bone scale carry. (Switching *every*
mesh moved all five tracked SVGs, 36,119 lines in `SketchBone.svg` alone.)

Reading the field as "this point follows that bone rigidly" then measured
**much worse**, so it is not enabled:

| mesh (SketchBone ears) | err% ignoring the field | err% honouring it |
|---|---|---|
| `kulak-sol/kulak-sol` | 16.0% | **48.4%** |
| `kulak-sag/kulak-sol` | 13.8% | **38.5%** |

Whole-frame difference went **78.9% the wrong way**.

The "wrong skeleton" theory was then tested and **disproved**. Only
`SketchBone.animeproj` can distinguish the two — its ears sit under `kafasi`
(21 bones) inside `cat_boy` (42), whereas `Bandit.mohoproj` has a single bone
layer so both readings coincide there. Scored on the same ear region across
30 frames:

| where the index is resolved | ear-region error | whole-frame difference |
|---|---|---|
| field ignored | **14.5%** | **851,143** |
| innermost skeleton (`kafasi`) | 40.7% | 1,522,999 |
| outermost skeleton (`cat_boy`) | 49.4% | 1,587,490 |

So it is not a skeleton mix-up: **both** rigid readings are much worse than
ignoring the field. The value *is* a bone index — 123 of the 4,400 bound
points hold a number larger than their own mesh's point count (Bandit's
`Ears` stores 20–23 for a 20-point mesh), which rules out a point index — so
what is wrong is the *rigid* reading, not the index space.

What remains untested: a bound point may still blend with its neighbours,
with the named bone merely forced into the weighting rather than taking the
point over; or the behaviour may be gated by `skeleton.binding_mode`. The
machinery stays wired up behind `--point-bones` but disabled, so a third
attempt starts from these measurements rather than from a guess.
| `mesh.shape_order` / `anim_shape_order` | mesh | Investigated twice; **correctly ignored** — see below. |

**`shape_order` is an ID registry, not a z-order — confirmed, correcting an
earlier revision of this section.** It is a `String` channel of shape *IDs*.
It equals `mesh.shapes` file order in 565 of 614 meshes, and **differs in
49** — `Bandit.mohoproj` (5/21), `IndependentAngle` /
`MaximumIKStrethching` / `TargetBone` (12/28 each), `OffsetBoneTool` (6/19),
`BoneDynamics` / `Rabbit` (1 each). An earlier revision read that as "49
meshes drawn in the wrong z-order". **That was wrong.** In **47 of the 49**
the ID list is strictly ascending while the file order is not, which is what
a registry looks like and not what an artist-chosen z-order looks like
(`Arm_B`: `"1|6|7|9|10"` stored, file order `10|9|6|1|7`, near-reverse); the
2 exceptions, Bandit's `Leg_F`/`Leg_F 2`, are near-ascending too. Reordering
by it also breaks `combo_mode` grouping, which is built from adjacency in
file order — rendering Bandit that way aborts rather than drawing. Both
findings match the independent experiment recorded in `moho2svg.py`'s own
docstring. `Mesh.draw_order()` now states the rule in one place.
`SketchBone.animeproj` is unaffected either way (0/82), and
`anim_shape_order` is `false` on all 614 meshes, so no sampled document
animates its z-order.

**Joint tearing between two rigidly-bound halves is NOT explained by any
unread field.** A layer whose `flexi_bone_subset` names exactly one bone
deforms rigidly (`Skinner.deform` normalises by the single weight, so the
falloff cancels out). `SketchBone.animeproj` binds each arm half that way -
`kol-sol-ust`→bone 13, `kol-sol-alt`→bone 14, `kol-sag-ust`→15,
`kol-sag-alt`→16 - so when the elbow bends the two halves rotate about
different pivots and pull apart. Measured on the rendered outlines: the gap
between `kol-sol-ust` and `kol-sol-alt` holds at 1-9 px up to frame 51, then
jumps to 40 px at frame 56 and settles near 26 px, exactly tracking bone 14's
own 41.5 degree swing between its keyframes at frames 49 and 55. The
skeleton itself stays sound throughout (bone 13's tip to bone 14's origin is
a constant 7.8 px), and neither half is point-animated, layer-transform
animated, or non-rigidly scaled - so this is the binding model, not the
bones. Moho's own "Smooth Joint for Bone Pair" is the feature that would
blend across such a joint, and **no stored field for it was found**: the
audit above rules out every candidate. Closing this would mean inventing a
blend, which the falloff is already flagged as unvalidated for
([§ 2.4](#24-flexible-region-binding)).
| `parent_bone == -3` | falls through to flexible binding, unconfirmed |
| Smart Warp / distortion layers | **not implemented, not detected** |
| Point groups, curve profiles, `start_percent` / `end_percent` | ignored |

---

## 8. Gaps, ranked by how likely they are to show

1. **Bone dynamics** — on in 6 of 19 documents, evaluated at playback,
   affects every frame away from a key. The largest real gap in this sample.
2. **Smart Warp** — invisible here (0 files), but a document that uses it
   loses the whole deformation silently. Detection is cheap; support is not.
3. **`end_percent` animation** — not exercised here, common in production.
4. **Control bones** — small in this sample, but a total miss where used.
5. **IK with a moving target** — usually baked, occasionally not.
6. **Independent angle (`fixed_angle`)** — 45 bones; effect unverified.
7. **Flexible-binding falloff shape** — affects every flexible layer a
   little; only visible where two bones overlap strongly.
8. **`offset`, `binding_mode == 2`, `parent_bone == -3`, `scaling_mode`** —
   undecoded, each observed in exactly one narrow place.

---

## 9. Reproducing the numbers

Every count above comes from a plain walk of the JSON. The pattern:

```python
import json, glob, collections

files = sorted(glob.glob('moho/*.mohoproj') + glob.glob('moho/*.animeproj'))
stats = collections.Counter()

def walk(layer):
    skel = layer.get('skeleton')
    if isinstance(skel, dict) and skel.get('bones'):
        for bone in skel['bones']:
            stats[bone.get('constraints')] += 1        # swap in any field
    for child in layer.get('layers') or []:
        walk(child)

for path in files:
    for layer in json.load(open(path)).get('layers') or []:
        walk(layer)

print(stats)
```

Useful variants:

- Bone-field census per format generation: key the counter by the document's
  top-level `version` (`1021` / `1038` / `1045`) as well as the field.
- Finding a feature that is absent: grep the raw text for a key name, e.g.
  `grep -o '"[a-z_0-9]*warp[a-z_0-9]*"' moho/*.animeproj | sort -u` — this is
  how the "zero Smart Warp hits" claim in [§ 5.1](#51-what-it-is--background-not-evidence)
  was checked.
- A channel's value: read `val[0]` for the first keyframe and `len(when)` for
  the number of keys. A field like `bone_dynamics` is a channel, not a bool,
  and counting it as a bool gives the wrong answer.
