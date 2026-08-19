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

`anim_scale` **does not accumulate down the bone chain** — decoded from
`BoneDynamics.animeproj` against Moho's own render. A child's origin is placed
with the parent's full, scaled matrix, so a squashing torso does drag its head
down; but the child's own axes are rebuilt from the accumulated rotation and
the child's *own* scale, so the squash does not shrink the child too.

That document squashes `TorsoA` to `anim_scale = 0.61` at frame 1. Composing
normally collapsed the rabbit's ear from 130 px tall — its rest height, and
Moho's — to 83.5 px, almost exactly 130 × 0.61, while Moho keeps it at 130.
Fixing it improved every other reference as well (vertical error, mean / max):

| Layer | Before | After |
|---|---|---|
| `Bandit` `Muzzle` | 2.65 / 5.92 px | **0.85 / 2.05 px** |
| `Bandit` `BellyTexture` | 2.84 / 6.26 px | **0.68 / 1.66 px** |
| `SketchBone` `kafasi` | 2.35 / 10.94 px | **1.53 / 2.08 px** |
| `SketchBone` `kulak-sol` | 4.47 / 20.20 px | **3.20 / 6.68 px** |
| `SketchBone` `cizgiler-sag` | 2.20 / 9.51 px | **1.64 / 3.49 px** |


`scaling_mode` — **used**, and decoded as the "Squash and stretch scaling"
switch (see [§ 2.3](#23-from-bones-to-matrices)). `max_auto_scaling` — used,
as the IK auto-stretch cap. `squash_stretch_scaling` — a magnitude (`1.0` on
831 of 850 bones), still unused.

**Physics / dynamics**

`bone_dynamics` and `angle_dynamics` — **used** together as the on/off switch
behind `--bone-dynamics`, along with `spring_force` and `damping_force` (see
[§ 3.5](#35-bone-dynamics-spring-physics)).

Not used: `torque_force` (now measured NOT to couple translation — see
`Skeleton.dynamic_angles`' EVIDENCE section), `pos_dynamics`,
`scale_dynamics`, `wind_dynamics`, the `pos_` / `scale_` variants of the
three force fields, the three `*_control_delay` fields, plus
`physics_radius`, `physics_return_to_zero`, `physics_motor_speed`,
`physics_torque`, `physics_lock_tip`.  Note: `pos_dynamics` /
`scale_dynamics` are NOT inert in the corpus — 22 bones across 4 documents
set them (`Whale` 2, `Lute` 1+1, `Cocon` 16, `Night_Boy` 3) — they are
simply unread, and none of those documents has a reference render yet.

**M1.5 batch 2 (2026-08-20)** confirmed by direct Moho render probe (not by
inference from the corpus alone) that every field in this "not used" list
DOES change Moho's own rendered output once its real precondition is met:
the `pos_`/`scale_` force triples and weights, probed on `Cocon.mohoproj`
with `bone_dynamics` and the matching `pos_dynamics`/`scale_dynamics`
switch forced true; the `physics_*` per-bone family (a further, different
subsystem — the Bone Physics tool, manual ch. 5.11 — not the spring
dynamics family at all), probed on `WhatIsBone.animeproj` with the
containing `GroupLayer`'s `enable_physics` forced true (`physics_torque`
and `physics_return_to_zero` additionally needed a non-zero
`physics_motor_speed` precondition to stop being inert, exactly as the
manual's own wording implies). See `schema/skeleton.schema.json`'s own
entries for the full per-field evidence; this remains a "not used" list for
THIS EXPORTER's own reading model, not a claim that Moho ignores these
fields.

Everything from `angle_dynamics` onwards exists only from **format 1045**;
files at 1021/1038 carry a single force triple and a single switch.

**Editor state (not used)**

`selected`, `hidden`, `shy`, `bone_label_showing`, `bone_tags`,
`angle_weight`.

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

**This regressed once already, silently, and is easy to reintroduce.**
`B23` is a root bone, but its own children in the same `flexi_bone_subset`
(`B24`, `B25`) compose off it. A later, otherwise-correct fix (bone scale no
longer accumulating down the chain — see [§ 2.3](#23-from-bones-to-matrices))
replaced full 2x2 matrix composition with a scalar rotation-angle sum for
every non-root bone, and a scalar angle cannot represent a mirror: `B23`'s
own matrix kept flipping correctly (`det` still negative from frame 44), but
`B24`'s and `B25`'s stopped — the reflection never reached them, so
`ayak-sol` tore relative to its own ankle from frame 44 on, while the leg
(driven by an unrelated, unflipped bone group) still looked fine. That
"leg right, foot wrong" split is exactly why it read as the same bug back
rather than a new one. The fix (`Skeleton.world_matrices`'s own "NOTE ON
FLIP PROPAGATION") composes a *matrix* for accumulated rotation-and-flip,
not a scalar angle, so `det` multiplies correctly through the chain again.
Both of the checks below must be rerun after ANY change to
`Skeleton.world_matrices` or `Skeleton._solve_ik_pair`, not only ones that
mention `flip_h` — this is the second time a scale/composition change broke
it without touching the flip code itself:

- **Instant, no reference needed** — every bone at or after a flip, and
  every one of its descendants, must have `det(world_matrices(f)[i]) < 0`:
  see the exact command in `world_matrices`'s docstring.
- **Against Moho's own render** — `make check-reference` now runs a
  *winding* check (`tools/check_reference_frames.py`, `run_winding_check`,
  `WINDING_CHECKS`) on `ayak-sol` specifically, because the existing
  bounding-box-centre check was too weak to catch this: the box barely
  moved (43.4 px wide broken vs 41.9 px correct at frame 44) while the
  outline's winding flipped. Add a layer to `WINDING_CHECKS` for any other
  bone whose `flip_h`/`flip_v` is a real, keyframed change.
- **Against real Moho renders, whole document, both legs** —
  `moho/track/SketchBone/foot/` (120 frames covering `bacak-sag`/`ayak-sag`,
  which never flips, alongside `bacak-sol`/`ayak-sol`, which does) and
  `moho/track/SketchBone/parts/ayak-sol-{43,44,45,46}.jpg` (four screenshot
  crops), both supplied specifically to arbitrate this fix. The screenshots
  alone were not enough evidence and led to a WRONG first diagnosis, worth
  recording because the correction is the useful part.

  Per-vertex error (mean point-to-point distance vs. the reference) across
  all 120 frames: `ayak-sag` (the control — same rig shape, never flips)
  never exceeds 5.88 px anywhere. `ayak-sol` peaks at 50.91 px at frame 45,
  then decays to under 0.5 px by frame 57 — a real, large, but **transient**
  error, not a permanent one. Disabling propagation instead (the
  alternative this fix replaced) is unambiguously worse: 24–67 px from
  frame 44 onward and *never* recovering.

  **The flip event itself is the root cause of the transient error** — not
  an incidental trigger for an unrelated curve-approximation issue (an
  earlier draft of this note said exactly that, and undersold the flip's
  own role; corrected after the person who supplied this reference frame
  set rechecked the Moho app and confirmed the target bone's own
  reorientation at frame 43→44 is instant there too). Printing `B24`'s
  WORLD angle — `B24` carries no flip of its own; this is pure composition
  through its flipped parent `B23` — frame by frame:

  | Frame | 43 | 44 | 45 | 46 | 47 |
  |---|---|---|---|---|---|
  | `B24` world angle | −8.23° | **−146.56°** | −138.86° | −130.01° | −121.65° |

  A **−138.34° jump in one frame**, then smooth ~7–9°/frame change
  afterward. That discontinuity — not any curve-shape detail — is what the
  44–46 transient error actually is, and it is the mathematically CORRECT
  consequence of composing a rotation through a reflection: `B23` itself
  swings from a local angle of 182.87° to a world angle of 2.87° the
  instant `flip_h` goes true (182.87+180 = 362.87 = 2.87° mod 360, exactly
  as reflecting one column of a rotation matrix predicts), and `B24`'s own
  small, real, authored −24.38° local-angle keyframe (also timed at frame
  44) then composes through that now-mirrored parent frame — which is what
  a reflected coordinate system does to a subsequent local rotation: it
  reverses its apparent handedness in world space.

  Two alternative composition formulas were tried against this exact
  120-frame reference and both came out equal-or-worse:
  - Reordering the flip to apply in the parent's frame before this bone's
    own rotation — identical result here, because `B24` itself never flips
    (the reordering is a no-op when there is nothing to reorder).
  - Propagating a separate boolean "mirrored" flag by XOR down the chain
    while summing local angles as plain scalars (no handedness reversal),
    applying the mirror once at the end — the "intuitive" alternative, and
    much worse: it no longer converges to the correct steady state at all
    (16.70 px mean / 33.08 px max at frame 90, versus ~0.3 px here).

  So the jump is real, large, and directly, unavoidably caused by the flip
  event composing correctly through the chain — not a symptom to explain
  away. What remains an open, secondary detail is why the error does not
  stay at its peak: it decays smoothly to near-zero by frame 57, reading
  ~0 exactly at `B23.anim_angle`'s own later keyframes (49: 2.26 px, 53:
  2.71 px, 57: 0.46 px) while peaking BETWEEN them (28 px mean at 45,
  12 px mean at 52). `B23.anim_angle` swings 178° → 216.4° → 130° → 159.8°
  across exactly those keyframes — reversing direction twice in 14 frames —
  with no explicit Bézier handle (confirmed: `im & 8` unset throughout),
  i.e. Moho's own undecoded default easing curve, approximated by
  `Channel._segment`'s monotone cubic (see [`moho-animation-and-transform.md`
  § 3.6](moho-animation-and-transform.md#36-what-mohosvgpy-does-instead)) —
  a known, pre-existing imprecision elsewhere, levered large here by the
  chain's length and by sitting right on top of the flip's own real
  discontinuity.

  **Not a `Skinner.deform` skinning-blend artifact** (an earlier draft of
  this note wrongly guessed that too, on only 4 sampled frames) — a wrong
  blend weight would not zero out exactly at `B23`'s own keyframes the way
  this does. Left unfixed, since Moho's real easing curve is undecoded —
  see the module docstring's KNOWN GAPS.

  **Confirmed against live Moho playback**, not just its exported frames:
  the person who supplied this reference set watched `ayak-sol` scrub frame
  by frame in the Moho app from 44 through 49 and confirmed it keeps
  visibly changing shape/size across that whole span before settling — not
  a clean single-frame snap. That validates `moho/track/SketchBone/foot/`
  as trustworthy ground truth and settles what would otherwise be a
  recurring question: the *flip* is instant (43→44), but "the shape keeps
  changing for several more frames after" is Moho's own real behaviour, not
  an artifact of this fix. The open gap is only the *precise* shape during
  frames 44–48, not the fact that settling takes a few frames.

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

**Before any of this, one point can opt out entirely.** `MeshPoint.parent` -
a bone index carried on the POINT, not the layer - overrides the layer's
own binding for that single point: `-2`/`-1` mean "no override, use the
layer's own binding" (the common case, ~89% of the 19-file corpus' points);
a real index (~4,000 points over 119 meshes) means "this point should
follow that one bone rigidly", skipping the weighted blend below entirely
for it. The field is read by `moho2svg.py`, but applying it is **off by
default** (`--point-bones`) - see [§ 3.8](#38-summary-what-ignoring-each-feature-costs)
for the current, unresolved evidence on whether ignoring it is actually
safe.

Then, for a point `p` with no per-point override (flexible binding):

```
for each candidate bone i:
    if strength(i) <= 0: skip                       # hard gate, checked first
    d = distance from p to the segment rest_p0(i)–rest_p1(i)
    w = falloff(d, strength(i))                     # default: 1 / d²
    accumulate rest_to_pose(i)·p, weighted by w
p' = weighted average, or p unchanged if no bone contributed
```

The **falloff shape is a heuristic**. `moho2svg.py` ships four
(`inv_d2`, `linear`, `cut_d2`, `hermite`). An earlier revision of this
section said no available reference could separate them - that is now
corrected: scored against Moho's own reference frames they separate
clearly and **disagree between the two documents that have more than one
bone**, `inv_d2` winning `SketchBone.mohoproj` while `linear` wins
`Bandit.mohoproj`'s many-bone layers. So the default is the best fit for
one document, not a decoded formula, and the case of two bones both having
strong influence near one point - the scenario this whole falloff exists
for - is where the four candidates disagree most, not where they agree.
`DarkMan.mohoproj`'s `hat -> right_part`/`left_part` is a concrete instance
of exactly that scenario found outside this corpus: see
[§ 3.8](#38-summary-what-ignoring-each-feature-costs).

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
| `binding_mode` | `skeleton` | `1` on 41 skeletons, **`2` on 1** (`OffsetBoneTool.animeproj`, layer `Happy Dance`). Measured, still not decoded: see the note below. | no |
| `bones_groups` | `skeleton` | Present only in the `1045` document, and empty there. Presumably a bone-grouping/selection aid. | no |
| `grandpa_bone` | `BoneLayer` | `true` on all 47 bone layers. Lets bones bind layers nested deeper than direct children. | no (the deform chain already crosses arbitrary nesting) |
| `flexi_bone_elbow` | `BoneLayer` | `false` on all 47. **Not decoded.** | no |
| `gravity`, `wind` | `BoneLayer` | Bone-physics environment; on exactly one bone layer in the sample. | no |

> **Correction.** An earlier revision of
> [`moho-project-file-format.md` § 6.4](moho-project-file-format.md#64-type-specific-fields)
> said `binding_mode` is `1` on every sampled skeleton. That is wrong: one
> skeleton uses `2`. Since nothing branches on the field, no output changed,
> but the claim was too strong.

> **2026-08 measurement, still not decoded.** `OffsetBoneTool.animeproj` was
> rendered by Moho 14.4 four times - `binding_mode` 2 vs 1, crossed with the
> five non-zero `offset`s kept vs zeroed (sets under
> `moho/track/_tmp_bm1/` and `_tmp_bm1_zero/`).  With offsets absent,
> `binding_mode` 2 vs 1 moves layers by only 3-19 px (legs ~3-9, head ~14-19,
> arms ~6-11) - real but small.  With offsets present the twin diffs are
> 100-200 px, but that is the offset mechanism (§ 3.7), not `binding_mode`
> itself.  No clean rule for what mode 2 changes emerged from bbox-level
> data, and the per-layer residual of this document is dominated by the
> whole-skeleton binding gap § 3.7 records.  The four renders stay in
> `moho/track/` for whoever next takes this on with per-point ground truth.

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

- **Confirmed**: `true` on **45 of 850 bones**, across 10 documents (65 bones
  across 11 documents in the wider corpus this was re-measured on).
- **Meaning — now measured and applied.** The bone keeps its parent's
  **position** but not the parent's **rotation**:

  ```
  angle -= parent_world_angle(frame) - parent_world_angle(0)
  ```

  The parent's *departure from its own rest rotation* is removed — the same
  shape control bones use ([§ 3.3](#33-control-bones)), and with the same
  consequence that frame 0 is untouched, so a rig's rest pose cannot break.
  See `Skeleton._world_matrices`' NOTE ON INDEPENDENT ANGLE.
- **Effect of ignoring: visible, up to 16 px** on a 1280×720 canvas.
  `TransformBoneTool.animeproj` was rendered by Moho **twice** — as authored,
  and with every `fixed_angle` forced `false` — which isolates the flag's own
  effect using Moho as the authority, cancelling every unrelated error here.
  Only the two leg layers move; arms, body and head differ by exactly 0.00 px,
  which is also the check that the experiment isolates what it claims:

  | layer | Moho's own effect (mean / max px) | error `off` | error `rest` | error `absolute` |
  |---|---|---|---|---|
  | LegL | 7.17 / 15.46 | 7.17 / 15.46 | **4.93 / 8.17** | 6.62 / 12.03 |
  | LegR | 5.82 / 16.17 | 5.82 / 16.17 | **3.43 / 7.16** | 4.32 / 8.15 |
  | overall | — | 2.17 / 16.17 | **1.39 / 8.17** | 1.82 / 12.03 |

  `absolute` is the other candidate reading — subtract the parent's whole world
  angle, making the bone's world rotation its own local angle outright. It beats
  ignoring the flag and loses to `rest` on every layer and both statistics.
- **Residual, 2026-08 re-measurement.** The "~1/3 recovery" line above was
  computed with a statistic that is not recorded; a clean per-axis delta
  metric (mean \|bbox-centre delta\| per layer, frames 1-120, all three twins
  rendered with Moho 14.4 — `moho/track/_tmp_tbt_{noflag,outer,inner}/`)
  changes the picture:

  | effect (Moho twin diff, dx, dy px) | ours `rest` − `off` | ours `absolute` − `off` |
  |---|---|---|
  | total, LegL (4.10, 4.79) | (3.37, 3.65) | (6.04, 3.96) |
  | total, LegR (3.36, 3.96) | **(5.10, 4.69)** | (5.41, 4.59) |

  `rest` recovers LegL at ~82%/76% and *overshoots* LegR (152%/118%) — the old
  "~1/3" is retired. The selective decomposition (selective twin minus the
  no-flag twin, Moho vs ours):

  | effect | LegL Moho / ours | LegR Moho / ours |
  |---|---|---|
  | outer (`B11`/`B15`) | (3.54, 4.13) / (3.06, 2.95) | (2.32, 4.17) / (3.39, 2.47) |
  | inner (`B12`/`B16`) | (1.78, 2.08) / (0.86, 1.32) | (1.58, 1.66) / **(3.42, 4.03)** |

  The weak spot IS the inner (parent-flagged) pair (48–216% of Moho's effect
  against the outer pair's 71–146%), but the three candidate corrections
  (uncorrected source, sum of ancestors' departures, recursive rest) all
  **collapse into the current formula** at this nesting depth — the
  correction sources are unflagged parents, and the parent's world departure
  already sums its whole ancestor chain. What is left is entangled with the
  binding model (see § 3.7's note: this region blend distributes weight where
  Moho follows one bone rigidly), and separating the two needs per-bone
  world-angle ground truth. Recorded, not tuned away; the twins and the
  decomposition numbers are the next attempt's starting point.
  [🟢 8/10 that the direction and shape of the formula are right,
  🟠 5/10 that it is complete — unchanged.]
- `make check-reference` is unchanged by this: Bandit's two flagged bones move
  its `Tail` group by 0.01–0.09 px and leave every other number identical.
  The new `TransformBoneTool` CHECKS row fences the current position
  (LegL mean dx 32 px on the displacement metric).

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
- **Meaning — now decoded and applied.** Bone A's angle/position/scale gets
  bone B's own **departure from its rest (frame 0) value**, times the scale,
  sampled `delay` frames earlier:

  ```
  value(A, t) = own_keyed(A, t) + control_scale * (B_local(t - delay) - B_local(0))
  ```

  The manual supplies the wording (ch. 5.01 "Angle/Position/Scale control
  bone"; ch. 23.03's Delayed Constraints script: *"if it's 100%, the bone will
  rotate, translate or scale exactly in the same way the previous bone does
  it… Frame delay sets with how many frames of delay the bone is going to
  move"*; ch. 21.12 *"their animation is 'automatic' through the control
  feature"*), and two independent measurements against Moho's own renders
  supply the numbers.

  **`Clay_Crocodile.mohoproj`** has one angle constraint (scale 1.0) with a
  genuinely animated controller. Exporting with and without it and reading the
  rotation straight out of Moho's `<image transform="… rotate(…)">`
  attributes:

  | frame | departure | raw value | measured | measured ÷ departure |
  |---|---|---|---|---|
  | 1 | −8.77° | −5.13° | 8.48° | 0.967 |
  | 3 | −20.32° | −16.67° | 21.70° | 1.068 |
  | 9 | −8.77° | −5.13° | 8.48° | 0.967 |
  | 24 | −4.64° | −1.00° | 4.43° | 0.954 |
  | 29 | −15.79° | −12.14° | 15.93° | 1.009 |

  The ratio against the **departure** sits at 1.0 within a few percent; against
  the raw value it scatters between 1.30 and 4.44. The few percent is the
  measurement (the images read are flexibly bound, so each picks up a blend).

  Using the controller's **world** angle is ruled out: that document's
  controller has animated ancestors, and the world departure at frame 1 is
  −1.15° against a measured 8.48°.

  **`Whale.mohoproj`** carries the corpus' one live *delayed* constraint (bone
  26 ← bone 25, scale 1.28, delay 4). Fitting the rotation between Moho's
  with/without exports over frames 30–50:

  | controller sampled at | rms error |
  |---|---|
  | `t − delay` (this model) | **0.598°** |
  | `t` (no delay) | 6.272° |
  | `t + delay` (opposite sign) | 9.524° |

  That pins the sign — the controlled bone repeats what the controller did
  `delay` frames *earlier* — and re-confirms the scale and the
  departure-from-rest reading on a second document.

- **What it changes today: no exported pixel.** The constraint demonstrably
  moves the bones (on `Gathered-02Wire2.mohoproj` at frame 40 it swings bone
  51's world angle from −2.53 to −1.79 rad), but in every corpus document the
  controlled bones reach artwork by a route this exporter does not follow to
  the end — `Clay_Crocodile` drives `ImageLayer`s, and the Gathered/Snow-girl
  rigs use `strength = 0` bones whose only influence is per-point binding
  (`--point-bones`, off by default, and still not moving those points when it
  is on: a separate, pre-existing gap). `Whale.mohoproj` — the document the
  delay was measured on — is image-based too, and its `whale_layers.psd` is
  not present locally, so even there the change is currently invisible in this
  exporter's own output. The formula and its plumbing into the skeleton are
  verified; the last hop from bone to artwork is what is missing, and it is
  missing for reasons that predate this change.

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

**The switch is two fields, and both must be on**

**Confirmed.** Newer Moho splits the setting: `bone_dynamics` is the per-bone
master switch, and `angle_dynamics` says the angle channel takes part. The
second one only exists from format 1045, together with `pos_dynamics`,
`scale_dynamics`, `wind_dynamics` and their own
`*_spring_force` / `*_damping_force` / `*_torque_force` / `*_weight` /
`*_control_delay` fields.

Neither field alone is the switch. `SketchBone` is in this corpus **twice** —
the 2016 original (`.animeproj`, format 1038) and a re-save from Moho Pro
14.4 (`.mohoproj`, format 1045) of the same document:

| Field | 1038 original | 1045 re-save |
|---|---|---|
| `bone_dynamics` | false on all 94 bones | false on all 94 bones |
| `angle_dynamics` | field does not exist | **true on all 94 bones** |

So `angle_dynamics` is just the default value of the new field: Moho's own
upgrade path sets it true on every bone of a document that uses no dynamics
at all. And `bone_dynamics` alone fails on the new format the other way —
`Bandit.mohoproj` has it true on **all 28 bones**, including the Smart Bone
dials `EyeBlink`, `HeadTurn`, `SquashStretch` and `EyeMovement`, while
`angle_dynamics` is true on only 2.

`moho2svg.py` therefore reads the switch as `bone_dynamics AND
angle_dynamics`, treating a missing `angle_dynamics` as true — see
`Bone.dynamics_on`. Bone counts under that reading:

| Document | Format | Bones | Dynamics on |
|---|---|---|---|
| `WhatIsBone.animeproj` | 1038 | 216 | 52 |
| `AddBone.animeproj` | 1038 | 188 | 21 |
| `BoneDynamics.animeproj` | 1038 | 17 | 7 |
| `Rabbit.animeproj` | 1021 | 15 | 7 |
| `ControlBones.animeproj` | 1038 | 29 | 2 |
| `Bandit.mohoproj` | 1045 | 28 | 2 |
| `SketchBone` (both versions) | 1038 / 1045 | 94 | 0 |

**It is a keyframed channel, and Smart Bones can drive it**

**Confirmed.** `bone_dynamics` is a `Bool` **channel**, not a flag.
`BoneDynamics.animeproj`'s `Main` bone has `when = [0, 1, 29]`,
`val = [False, True, False]` — dynamics runs only over frames 1–28. The same
document registers a `JumpCycle` **action pose** on the `bone_dynamics` of
all six of its rabbit-ear bones, so a Smart Bone dial can switch the feature
on and off as well.

**The forces**

`spring_force`, `damping_force`, `torque_force`. The default triple is
`2.0 / 1.0 / 2.0`. `BoneDynamics.animeproj`'s ear chain is graded from base
to tip, and `torque_force` — the one field the exporter does not use — varies
most of all:

| Bone | `spring_force` | `damping_force` | `torque_force` |
|---|---|---|---|
| `RearA` / `LEarA` (base) | 2.0 | 1.0 | 0.1 |
| `REarB` / `LEarB` (middle) | 1.95 | 3.0 | 0.45 |
| `REarC` / `LEarC` (tip) | 0.8 | 4.4 | 1.9 |

**Effect of ignoring, and of the current approximation**

**Exercised and visible.** Moho adds the spring motion on top of the keyed
pose at playback time. A channel-only exporter renders the keyed pose with no
follow-through or overlap.

`--bone-dynamics` (off by default) implements a damped spring pulling each
bone toward its own keyed angle, with the parent's own world rotation arriving
as a driving force. The spring itself is **now decoded, not fitted** —
measured 2026-08 on synthetic two-bone rigs rendered by Moho 14.4 with one
rigidly-bound marker mesh per bone, whose rendered rotation is the driven
bone's world angle read directly (rigs and harness in `tmp/dynamics/`,
untracked; the residual is fenced by a `make check-reference` row on rig `r1`):

- **Per-second units**, one semi-implicit Euler step per frame (`h = 1/fps`).
  The same step-response document rendered at 12/24/48 fps gives first-frame
  displacements of 39.79/9.95/2.49 degrees — constant × (1/fps)² to 0.6%.
  The old "per frame" reading in this file was wrong.
- **Spring scaled ×96, damping ×0.85** against the stored values — the best
  fit over four step-response sets (spring 2/damp 1 and spring 1/damp 4.4,
  each at 12/24/48 fps; mean error 1.6 deg/frame on a 55-degree swing).
  100/1.0 is cleaner but fits worse (4.1); the two scales are correlated.
- **`torque_force` does NOT couple translation**: a translating parent
  rotates the child 0.0000 degrees at torque 0.1 and 6.0 alike, so the
  pivot-acceleration reading is dead for good (it changes the rotational
  response by ~1 degree — plausibly inertia — but that is not fitted).
- **`angle_weight` is live but unfitted**: a step response differs visibly
  at weight 1.0 vs the −1.0/0.0 baseline, non-monotonically across
  {0.5, 1.0, 2.0}. It stays unread.
- **Wind is still a negative result**: a minimal wind rig (physics on,
  `wind.strength` 100, turbulence 0.8/2.0, `wind_dynamics` true, DarkMan's
  own B3 keyframes) renders identically with wind on and off — 0.0000
  degrees difference at every keyframe — so the DarkMan B3 damping
  observation must come from something other than those fields alone.
- **Unresolved**: the units of the parent-coupling terms (per-second rates
  matched a gentle 0.5 rad/s ramp exactly but flung the BoneDynamics ears
  30 px further off on TorsoA's ~12 rad/s swings; per-frame rates leave that
  document at baseline — the code keeps per-frame, recorded not tuned); the
  chain solve (a dynamic parent's simulated lag is not fed to its children,
  only its keyed pose); and initial conditions across a mid-run switch.
  BoneDynamics' ears still sit ~55 px off with dynamics on and off alike —
  a baseline defect elsewhere, not the spring.

See `Skeleton.dynamic_angles`' EVIDENCE section for the full tables.

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

### 3.7 `offset` (the Offset Bone tool) — DECODED 2026-08

`offset` is a plain `Vec2` (not a channel).

- **Confirmed**: non-zero on **5 bones**, all in `OffsetBoneTool.animeproj` —
  the tutorial file for Moho's Offset Bone tool. Zero on the other 845.
- **Observation**: on those 5 bones, `offset` is close to the negative of
  `anim_pos` (for example `anim_pos = {0.074, 0.667}` with
  `offset = {0.0, -0.596}`). That is consistent with the tool's purpose:
  move where a bone *sits* without re-binding the artwork that already
  follows it.
- **Decoded by Moho's own double render.** `OffsetBoneTool.animeproj` was
  rendered by Moho 14.4 twice — as authored, and with the five non-zero
  offsets forced to 0 — and diffed per layer (frames 1-120, 1280×720):

  | layer | mean (dx, dy) px | note |
  |---|---|---|
  | arm R | (132, 131) | every point moves by the SAME vector (spread 0.00 px) |
  | leg R | (197, 64) | |
  | head group | (49, 155) | |

  Three findings, each contradicting an earlier guess:

  1. The effect is a **GROSS displacement** (100-200 px, the full offset
     magnitude times the canvas scale), visible from frame 1 — reading (a)
     "display-only, ignoring is exactly right" is **wrong**, and so is this
     section's old claim that any error would be "a soft weighting error,
     not a gross displacement".
  2. The per-point deltas are **perfectly uniform** per mesh (0.00 px spread
     across all 10 on-curve points of arm R): Moho's render of these meshes
     is an effective rigid follow of one bone, not a distance blend.
  3. The mechanism is the asymmetry: the **pose** carries the offset while
     the **bind transform basis** does not (the artwork was bound before the
     bone was moved), so `rest_to_pose = pose(shifted) · rest⁻¹(unshifted)`
     KEEPS the offset instead of cancelling it — which is why the old
     "cancels out of `rest_to_pose`" note was wrong in the other direction
     too. Implemented exactly so (see `Skeleton._solve`'s NOTE ON OFFSET
     and `Skinner.build`'s `bind_rest` calls).
- **What the decode does NOT yet buy here — recorded, not tuned away.**
  This exporter's delta (offset applied vs suppressed) matches the direction
  of Moho's twin diff but only a fraction of its magnitude on the affected
  layers, and the absolute per-frame error against Moho's as-authored render
  stays at 35-120 px. The dilution is the **binding model**, not the offset:
  every mesh in this document binds `parent_bone = -1` with an empty
  `flexi_bone_subset` under `binding_mode = 2`, which this exporter blends
  across all 26 bones by distance falloff (the offset bones get ~7-13% of an
  arm point's blend) while Moho's own twin diff shows per-mesh rigid follow.
  Decoding that binding rule is a separate question (see § 6); the offset
  mechanism above stands on the twin diff alone, which is Moho-vs-Moho and
  does not depend on it.

### 3.8 Summary: what ignoring each feature costs

| Feature | Baked into channels? | Cost of ignoring | Exercised in the sample? |
|---|---|---|---|
| Angle constraints | yes | none | 158 bones, 11 docs |
| Bone dynamics | **no** | missing secondary motion, grows off-key | 115 bones, 6 docs — spring now decoded (per-second, ×96/×0.85), still behind `--bone-dynamics`; parent-term units and the Bandit tail gap remain (§ 3.5, § 8.1) |
| Control bones | **no** | driven bone does not move | 13 channels, 4 docs |
| IK / `target_bone` | usually | wrong limb when the target moves | 41 bones, 14 docs |
| Independent angle | unknown | possibly wrong child angle | 45 bones, 10 docs |
| `offset` | unknown | possibly shifted binding weights | 5 bones, 1 doc |
| `anim_parent` (reparenting) | n/a | none — 850/850 match static `parent` | never keyframed |
| `squash_stretch_scaling`, `max_auto_scaling` magnitudes | n/a | scale magnitude detail | `scaling_mode` itself is now decoded and used |

### The falloff shape is not the lever — measured

The flexible-binding weight falloff has been flagged since the beginning as
an unvalidated heuristic, on the grounds that the corpus never exercised a
point genuinely straddling two bones. `moho/SketchBone/ears/` — Moho's own
isolated render of the two ears, whose meshes each blend three bones — is the
first reference that does. Scoring silhouette IoU over 40 frames across a
parameterised family `strength^a / d^p`, plus a region-style Hermite falloff:

| falloff | ears | arms |
|---|---|---|
| `1 / d` | 74.38% | 85.88% |
| `1 / d²` (the default) | 74.32% | 85.88% |
| `1 / d³` | 74.32% | 85.88% |
| `strength² / d` | 74.51% | 85.88% |
| `hermite(d / strength)` | **74.67%** | 85.88% |

The whole family spans **0.4%** on the ears and is **bit-identical on the
arms** — each arm layer names a single bone, so `Skinner.deform` normalises
the weight away entirely and no falloff can matter there. So the residual ear
error is **not** in the weight function, and tuning it would be fitting
noise. This confirms the original suspicion quantitatively rather than
removing it: the falloff remains unvalidated, but it is now known not to be
where the remaining error lives.

The ear's residual error is now identified as **linear-blend-skinning volume
collapse**, from comparing silhouette AREA rather than position. Over frames
74-80 of `moho/SketchBone/ears/` Moho's ear area is essentially constant
(27,065 / 27,100 / 27,087 / 27,625 px, within 2%) while ours swings by 10%
(22,709 / 21,411 / 24,485 / 26,296) and is smaller throughout. That is the
signature of averaging blended *positions*: when two bones rotate apart the
weighted mean of their images falls inside the arc, so the mesh contracts by
an amount that varies with the inter-bone angle. It also explains why no
weight function helped — the artifact is in the blend method, not the
weights.

Two area-preserving blends were tried and **neither is adoptable**, both
trading position accuracy for area accuracy:

| blend | ears IoU | ear area ratio | arms IoU |
|---|---|---|---|
| linear blend (current) | **75.97%** | 0.965 | **88.21%** |
| circular-mean rotation + mean translation | 75.72% | 0.977 | — |
| centre-of-rotation blend | 70.62% | 0.980 | 86.88% |

Both move the area ratio toward 1.0, confirming the diagnosis, and both score
worse overall, so the linear blend stays. Closing this properly means finding
the scheme Moho actually uses (its behaviour is area-preserving *and*
positionally correct, which neither of these is).

What is still unexplained is the ear's lower edge swinging further than
Moho's. Ruled out by measurement so far: falloff shape (above), every bone
constraint field (all at defaults on the six ear bones — no control parents,
no angle limits, no dynamics, `anim_parent` merely mirrors `parent`),
`scaling_mode` (decoded, but those bones never scale), per-point bone binding
(two readings, both far worse), and `flexi_bone_subset` semantics (dropping
the subset scores 72.27%, worse than honouring it at 74.32%).

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

**Where the raw evaluator is not enough — a measured gap.** "Raw" means the
dial's own *keyed* angle. A dial that is itself **driven** — by a control bone,
by bone dynamics, or by another dial's action — resolves to a different angle,
and Moho looks the pose up from the resolved one. A third-party tool
(`AE_Utilities:SumActionInfluences`, see
[moho-mohoscripts-plan.md](moho-mohoscripts-plan.md) § 2.10) uses the resolved
`bone.fAngle` for exactly this reason; its own comment calls the keyed value
"bad for nested smartbones".

Measured over the corpus: **108 dial bones**, none driven by another dial's
action, and exactly **two** driven by a control bone — `HeadTilt` in
`Rabbit.animeproj` and in `BoneDynamics.animeproj`, both
`angle_control_scale = 1.0`, `angle_control_delay = 0`. In both documents the
*controller* never leaves its own rest angle, so the control offset is `0.0` at
every frame and the selected pose frame is identical either way (checked frames
0–60). Left unimplemented deliberately: nothing here can verify a fix, and
feeding a resolved angle back into the machinery that resolves it needs the
same cycle protection `Skeleton._control_offset` already carries. A document
that turns a control bone which drives a dial would settle it
[🟠 5/10 that ignoring this is safe in general].

---

## 4b. Vitruvian Bones — background, not evidence

> **Correction (2026-08).** This used to say `bones_groups` is "empty in every
> one of this repository's 19 sample documents". That is no longer true:
> `Night_Boy.mohoproj` carries one group, and its `active_bone` is
> **animated**. The storage is now decoded and confirmed; what "active" *does*
> is still not, and an implementation attempt was measured and rejected — see
> § 4b.1 below. Still **do not implement against this** without new evidence.
> [🟠 3/10 on the semantics; 🟢 9/10 on the field shape]
>
> **M1.5 registry note (2026-08-19).** The 2,840px measurement below is now
> also registered formally: `BoneGroup.active_bone` is `x-moho-disposition:
> EDITABLE` in `schema/skeleton.schema.json` (`tools/probe_field.py` against
> `Night_Boy.mohoproj`, independent of the hand-authored `TransformBoneTool`
> group described here, also shows `AFFECTS RENDER`). `EDITABLE` records only
> that varying the field moves rendered pixels — it is not a claim that the
> semantics below are resolved.

**What it is.** Vitruvian Bones is a Moho Pro 13.5 feature
(`mono-changelogs.md`): "you can have different sets of heads, each with its
own controllers. Or the same limb in different perspectives... group and
animate them on the fly just by switching from one to the next." It reads
like a SwitchLayer, but for a SUBSET OF BONES within one skeleton instead of
a subset of layers.

**The mechanism, from the API.** `M_Skeleton` (the scripting-API counterpart
of this project's own `Skeleton`) exposes `CountGroups()`/`Group(id)`,
returning `M_BoneGroup` objects:

```
class M_BoneGroup {
    const char *Name();
    int32 CountBones();
    M_Bone *Bone(int32 id);
    M_Bone *ActiveBone();
    bool ContainsBoneID(int32 boneID);
    ...
    AnimVal   fActiveBone;   // ANIMATED - which member bone is "active" now
    bool      fEnabled;
};
```

A bone group is a NAMED subset of a skeleton's own bones, with an
**animatable** `fActiveBone` channel selecting which one member is active at
a given frame - structurally the same idea as `SwitchLayer.switch_active_child`
already implemented in this project (`Layer.switch_active_child`), just
scoped to bones inside one skeleton rather than child layers. `Strings.EN.txt`
corroborates the UI surface: `/Menus/Bone/EnableAllVitruvianBones`,
`/Menus/Bone/DisableAllVitruvianBones`, `/Scripts/Tool/BoneGroups/
AddToVitruvianGroup`, and channel names `VitruvianBones`/
`VitruvianBonesConsolidated` under `/Animation/Channels/`.

### 4b.1 The storage, decoded — and the semantics, still not

**The storage is confirmed**, and no longer an inference.
`Night_Boy.mohoproj`'s bone layer carries exactly one group:

```json
{"type": "BoneGroup", "enabled": true, "name": "Group 5",
 "bones": [101, 102, 103],
 "active_bone": {"type": "Val", "when": [0, 1], "val": [2.0, 0.0], ...}}
```

`bones` holds **bone indices into that same skeleton** — here `B136`/`B137`/
`B138`, three bones sharing parent 51 at rest angles 90°/124.6°/41.8°: one limb,
three poses, exactly what the feature is for. `active_bone` is a **channel**, and
this one **animates** (2.0 at frame 0, 0.0 at frame 1).

Confirmed by **writing such a group by hand** into
`TransformBoneTool.animeproj` (grouping bones 4 and 6) and rendering with Moho:
it honours the hand-authored group, changing 2,862 px. So the key names and
shapes above are right, not merely plausible.

`active_bone` is **0-based into the group's own `bones` list**, and an
out-of-range value falls back to the **first** member. Measured on that 2-member
probe, all against a no-group baseline of the same document:

| `active_bone` | Moho's render vs no-group baseline |
|---|---|
| 0 | 22 px (i.e. identical, that being anti-alias noise) |
| 1 | **2,840 px** |
| 2 | 22 px |
| 3 | 22 px |

**What "active" does is still unknown, and the obvious model is wrong.** The
natural reading — only the active member deforms the mesh, its siblings go inert
— was implemented here (strength 0 for an inactive member, which routes through
the "this bone does not deform this mesh" gate `Skinner.deform` already has) and
then **rejected on measurement**:

- With the first member active, Moho changes 22 px against the no-group
  baseline while that model changes **568 px**. Moho is telling us an inactive
  sibling is *not* switched off.
- Where both do change (second member active), the model covers only **33%** of
  Moho's changed pixels, median distance 3.6 px, p90 36 px.

Freezing an inactive member at its rest pose does not fit either: both probe
bones are animated through frame 25, so that model would predict a visible
change in both directions, and Moho shows one only.

So the honest state is: shape known, selector semantics known, **effect
unknown**. A rig that switches a limb visibly, plus its Moho render, would settle
it; the probe recipe above is the cheap way to make one.

**What to do today.**
- **Do not guess the effect** — same posture as Smart Warp. The rejected
  attempt above is recorded so it is not re-tried blind.
- **Do detect it.** `moho2svg.py` now does: `walk_render_tree` warns once per
  `BoneLayer` whose `skeleton.bones_groups` is non-empty (`Skeleton.
  bones_groups`, a raw passthrough — see its own docstring), the same
  dedup mechanism as the Smart Warp detector right above it in the source.
  Before this, a Vitruvian-Bones-using document would silently pose only
  the skeleton's OWN keyed angles, ignoring whichever bone the group's
  `fActiveBone` selector actually meant to be showing.
- ~~**To document it properly**, one file is enough~~ — **done**:
  `Night_Boy.mohoproj` supplied it, and § 4b.1 above records the shape plus
  what the selector does. What remains is a rig whose limb visibly switches,
  to settle the *effect*.

**Pin Bones (Anime Studio 12) — an unresolved lead, not a finding.**
`mono-changelogs.md` also names "Pin Bones": "Add one point bones to alter,
move and reshape assets in fun new ways... Works with both vectors and
images!" Unlike Vitruvian Bones and Smart Warp, this pass found **no
corroborating evidence at all** for it — no `Pin`-named class or method in
`pkg_moho.lua_pkg`, no `Pin Bone` string in `Strings.EN.txt`, and no
zero-length `Bone` (the cheapest guess for what a "one point bone" might
serialize as — a bone whose `length` is 0, since an ordinary bone is a
two-point segment) anywhere in this repository's 531-bone, 19-document
corpus. Left here only as a flagged, unconfirmed lead for a future session
with either a newer/different Moho install or a real Pin-Bone-using file —
not worth a detector given zero grounding for what field to even check.

---

## 5. Smart Warp

### 5.1 What it is — background, not evidence

> **Not in the sample.** No file in `moho/` uses Smart Warp: a search for any
> JSON key containing "warp" across all 19 files returns **zero hits** - now
> re-run also for "curver", "quad" and "compressible" (see § 5.1b), still
> **zero hits** across all three. The paragraphs in this sub-section come
> from general knowledge of Moho as an application (§ 5.1) or from Moho's own
> shipped Lua scripting API headers (§ 5.1b, a real file on this machine, but
> still not a real Moho *document* - no exported project has ever put these
> fields under a microscope). They are orientation only — do **not**
> implement against them. [🟠 4/10]

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

### 5.1b The mechanism, from Moho's own scripting API — still not a file finding

Moho ships its C++ scripting interface as plain-text header files under the
application bundle itself: `/Applications/Moho.app/Contents/Resources/
Support/Pro/Extra Files/Lua Interfaces/pkg_moho.lua_pkg` (class/method
signatures) and `/Applications/Moho.app/Contents/Resources/Strings/
Strings.EN.txt` (menu-label strings) — both read directly for this section,
not third-party documentation. This confirms the *mechanism* precisely,
narrowing (but not replacing) § 5.2's `distortion_layer_uuid` inference:

- **A warp/Curver layer is NOT a distinct document layer type.** There is no
  `WarpLayer`/`CurverLayer`/`QuadMeshLayer` C++ class in `pkg_moho.lua_pkg` -
  the full layer class hierarchy it defines is exactly the set this project
  already knows: `MohoLayer` -> `MeshLayer`, `AudioLayer` -> `ImageLayer`,
  `GroupLayer` -> `BoneLayer`/`SwitchLayer`/`ParticleLayer`, `Mesh3DLayer`,
  `NoteLayer`. An ordinary `MeshLayer` instance carries the warp/Curver
  behaviour as STATE, not type:
  ```
  class MeshLayer : public MohoLayer {
      bool IsWarpLayerCandidate(bool curverOnly = false);
      void MarkAsWarpLayer(bool b, MohoLayer *target);
      bool IsWarpLayer();
      void MarkAsCurver(bool b);
      bool IsCurver();
      ...
  };
  class MohoLayer {
      ...
      void SetWarpLayer(MohoLayer *layer);
      MohoLayer *GetWarpLayer();
      ...
  };
  ```
  `MarkAsWarpLayer(bool, target)` / `GetWarpLayer()` on `MohoLayer` (the
  common base every layer kind inherits) is the API-level match for
  `distortion_layer_uuid` in § 5.2's table below: a plain `MeshLayer`,
  marked as a warp layer, pointing at the OTHER layer it deforms. This is
  the strongest evidence yet for that inference, but it is evidence about
  the *application's* internal model, not about how `distortion_layer_uuid`
  (or a boolean twin of `IsWarpLayer()`/`IsCurver()`) is actually spelled in
  the serialized JSON - neither `IsWarpLayer` nor `IsCurver`'s own stored
  field name is confirmed; a search for "curver" as a JSON key substring
  across all 19 sample documents (same method as the existing "warp" search)
  returns zero hits too, same as `distortion_layer_uuid` itself: present but
  always empty/inert.
- **"Curver" (not "Curve") is the correct spelling** - confirmed by
  `MarkAsCurver`/`IsCurver` in the API above, and independently by
  `Strings.EN.txt`'s own UI menu labels:
  `/Menus/Draw/CreateCurverLayer=Create Curver Layer` and
  `/Menus/Draw/CreateCompressibleCurverLayer=Create Compressible Curver
  Layer` (alongside the ordinary `/Menus/Draw/CreateMeshLayer=Create Mesh
  Layer`). A "Curver" is presumably a `MeshLayer` created with `IsCurver()`
  already true - a 1-D warp mesh (a strip/curve an artist bends artwork
  along) rather than the general 2-D quad-grid warp mesh described in
  § 5.1, though that distinction is this project's own reading of the name,
  not confirmed by either source file.
- **"Quad Mesh" IS a real, confirmed Moho feature - update: found in
  `mono-changelogs.md`**, just not under a distinct layer-type name. Moho Pro
  13.5's own release notes: "Meshes are now even more powerful and easier to
  use with the new Quads! Animate your artwork in true perspective by simply
  attaching a four points shape to it. Or create grids for your characters -
  combining triangles and quads- and make them move like 3D." This resolves
  the "not confirmed" status below to "confirmed real, still not a distinct
  JSON type": a Quad mesh is a plain `MeshLayer` (matching § 5.1b's own
  finding that no `QuadMesh`-named class exists in the scripting API) whose
  warp behaviour is a genuine PERSPECTIVE transform ("true perspective"),
  not just the affine bend a bone/ordinary-mesh-warp produces - the sharpest
  concrete difference from a `Curver` (a 1-D bend along a line, per its own
  name) found so far. Introduced in the 13.5 generation specifically, one
  point release after Smart Warp itself (13.0) and Wind dynamics (also
  13.5) - all three shipped in the same release.
- **Practical implication for this project, regardless of the above:**
  because a warp/Curver layer is an ordinary `MeshLayer`, `moho2svg.py`
  ALREADY renders its own mesh geometry correctly today - nothing about
  parsing or drawing that layer's own shapes is missing. The unimplemented
  part is strictly the DEFORMATION EFFECT it would apply to whatever layer
  `GetWarpLayer()`/`distortion_layer_uuid` names, exactly the gap § 5.3
  already describes - this sub-section renames and sharpens that gap, it
  does not add a new one.

### 5.2 What the files actually show

These are **confirmed** observations. Whether they belong to Smart Warp is
inference, and is marked as such.

| Field | Where | Observed | Reading |
|---|---|---|---|
| `distortion_layer_uuid` | every layer in the `1038` and `1045` files (827 layers); **absent** in the `1021` file | `""` in all 827 | A layer pointing at *another layer* used as a distortion mesh. The name is a strong match for a warp-mesh reference, and now also matches `MohoLayer::GetWarpLayer()`/`SetWarpLayer(MohoLayer*)` in Moho's own scripting API ([§ 5.1b](#51b-the-mechanism-from-mohos-own-scripting-api--still-not-a-file-finding)) at the MECHANISM level - still not confirmed as the same field at the SERIALIZATION level. **Inference** [🟡 6/10]. |
| `triangulated` | every `MeshLayer` in the `1045` file (21); absent in `1038` and `1021` | `false` on all 21 | A mesh can be triangulated — which is what a deformation mesh needs and a drawing mesh does not. |
| `squashable_deformer` | same 21 layers | `false` on all 21 | The word *deformer* implies a mesh can act as one. |
| `frame_zero_deformer` | same 21 layers | `true` on all 21 | Presumably "this deformer is defined at frame 0", matching the rest-pose-at-frame-0 convention bones already use. |

The generation pattern is the useful part: **all three deformer flags appear
only in the newest format generation in this sample (`1045`)**, and none of
them exists in `1038` or `1021`. That is consistent with a
deformation-mesh feature arriving in the same release family as those files,
and it means an older reader will never see them.

**M1.5 batch 5 (2026-08):** the table above's `false`/`true` "on all 21"
values are specific to that single sample file (`Bandit.mohoproj`), not
universal. A 76-document corpus scan of every `1045` document found
`triangulated` true on 16 of 297 sites across 5 documents (`Boar.mohoproj`,
`Lute.mohoproj`, `Night_Boy.mohoproj`, `Spacewoman.mohoproj`,
`Whale.mohoproj`) and `frame_zero_deformer` false on 140 of 248 sites across
all 10 `1045` documents (Bandit's own 21 sites do hold the values shown
above). `squashable_deformer` remains false in every sample checked so
far. Direct Moho-render probes (forcing each field to its minority value on
a document where the OTHER value is genuinely authored) found both
`triangulated` and `frame_zero_deformer` inert on the frames tested — see
`schema/layer.schema.json`'s `MeshLayer` $def and
`docs/moho-project-file-format.md` § 6.4 for the exact fixtures.

Related but separate: `parent_bone == -3` on 9 `ImageLayer` instances, always
with a non-empty `flexi_bone_subset` ([§ 2.5](#25-how-a-layer-attaches-to-the-skeleton)).
That is a raster deformation mode, not Smart Warp, and is equally undecoded.

### 5.3 What to do today

- **Do not guess the format.** No structure, no field names, no point layout
  for a warp mesh can be stated from this sample - § 5.1b confirms the
  MECHANISM (an ordinary `MeshLayer`, marked as a warp/Curver layer,
  pointing at a target layer it deforms) from Moho's own API, but not the
  JSON key names or point layout that mechanism is actually serialized as.
- **A warp/Curver layer's OWN geometry already exports correctly** - see
  § 5.1b's last point. Nothing needs to change there; the gap is narrower
  than "this layer type is unsupported" - it is specifically "the
  DEFORMATION EFFECT on the target layer is not applied".
- **Do detect it.** A reader can cheaply flag a document as "possibly
  unsupported" when any layer has a non-empty `distortion_layer_uuid`, or when
  a mesh layer has `squashable_deformer: true`. `moho2svg.py` does both today
  (a deduplicated per-layer stderr warning from `walk_render_tree`, around
  moho2svg.py:8657-8677); the artwork is still exported undeformed, but it
  is no longer silent.
- **To document it properly**, one file is enough: save any Moho project that
  uses a Smart Warp mesh into `moho/`, then re-run the census in
  [§ 9](#9-reproducing-the-numbers). The new keys will stand out immediately,
  because the current key set is fully enumerated. Also grep that new file
  directly for `"curver"` (case-insensitive) - § 5.1b's `IsCurver()` finding
  means that substring, not just "warp", is now worth checking too.

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

**Now implemented for a plain stroke** (`Exporter._stroke_trims`,
`CurveGeometry.trim_ranges`, `split_cubic`). Moho calls it **Stroke Exposure**;
the channel id is `CHANNEL_CURVEEXP`.

- **Confirmed**: `start_percent` is `-0.1` on all 3,045 curves; `end_percent`
  is `1.1` on all but 3 (which are `1.008296`) in the 19-file set. In the wider
  corpus **24 curves in `FoxAndGhost.animeproj` carry `end_percent = 0.9721`**.
  Both are `Val` channels; none is keyframed anywhere here.
- **A value outside `[0, 1]` means "not trimmed."** Moho's own bundled
  `SS_CurveExposure` tool clamps its drag to `[-0.01, 1.01]` and writes those
  as the untrimmed ends, while these documents carry `-0.1` / `1.1`. Both read
  the same way: clamp into `[0, 1]`, and a full range means no trim.
- **What it trims — measured, because the name does not settle it.** The
  **outline only**; the shape's fill stays whole. Confirmed by forcing
  `end_percent` to 0.5 and 0.75 on `TransformBoneTool.animeproj`'s `Body`
  curve (5 points, closed, carrying both a fill and an outline) and rendering
  with Moho: the purple body fill is untouched in both, the dark outline loses
  its tail.
- **The fraction is of ARC LENGTH, not segment-parameter space.** Both models
  were implemented and scored against those Moho renders by changed-pixel IoU:
  arc length **0.739 / 0.723** (at 50% / 75%) against segment-parameter
  0.648 / 0.683. A one-segment curve cannot tell them apart, which is why the
  purpose-made multi-segment probe was needed.
- **Corpus reach is zero, and that is measured too**: re-rendering
  `FoxAndGhost.animeproj` with Moho with those 24 curves forced back to
  untrimmed changes **0 pixels** at 8 frames sampled across its 450-frame
  range — the `Lazer Beam` / `Light Blade` / `Glow` layers holding them are
  never drawn. So this exporter's own output is byte-identical on that
  document, and the feature rests on the purpose-made probe.
- **Not applied to a brush-textured or tapered outline**, which are built as a
  stamped dab run or a filled band instead of a strokeable path. Moho *does*
  trim those (the probe above is itself brush-styled), so this warns once per
  mesh and kind rather than failing silently.
- **Why it matters**: a keyframed `end_percent` is how Moho animates a line
  drawing itself on. Nothing here keyframes it, but the machinery now honours
  a keyframed value because the trim is evaluated per frame.

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
| Control bones (`*_control_parent`/`_scale`/`_delay`) | **applied** — see § 3.3 for the decoded formula and its verification |
| `offset` (Offset Bone tool) | **applied** — see § 3.7 for the 2026-08 decode |
| Bone dynamics (angle family) | simulated behind `--bone-dynamics`, off by default — see § 3.5; pos/scale/wind families **not implemented** |
| `anim_parent`, other constraints | not read (matching `parent` everywhere in the corpus) |
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
| `layer.timing_offset` | layer | Shifts a layer's whole animation in time. `0` on 839 layers, `45` on 3 — `Rabbit.animeproj`'s `ProsBox`, `PROS` and `T I  PS`. **Correcting an earlier claim here that those three are "45 frames out of step":** they are not, because all three are entirely static — zero animated channels in their whole subtree, confirmed by re-evaluating their geometry at frames 1/10/20/29 and getting identical output — and 45 is past that document's own 1–29 range. Read and counted, deliberately not applied: with nothing that animates such a layer, the sign (delay or advance?), the scope (subtree or not?) and the behaviour under an animated ancestor are all unverifiable, so applying it would be three simultaneous guesses with no test that could fail. |

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
mesh moved all five sample documents' exported SVGs, 36,119 lines in `SketchBone.svg` alone.)

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
| `parent_bone == -3` | falls through to flexible binding, tiled into small pieces (each still flexibly bound, not snapped to one bone) so the one affine map per piece stays close to exact (confirmed the right call for ImageLayer motion against real per-frame reference PNGs - see moho2svg.py's IMAGE LAYERS section) |
| Smart Warp / distortion layers | **not implemented, not detected** |
| Point groups, curve profiles | ignored |
| `start_percent` / `end_percent` (stroke exposure) | applied on a plain stroke ([§ 6.3](#63-curve-trimming-start_percent--end_percent)); warned on a brush/tapered outline |

---

## 8. Gaps, ranked by how likely they are to show

1. **Bone dynamics** — on in 6 of 19 documents, evaluated at playback,
   affects every frame away from a key. **Implemented behind
   `--bone-dynamics`, off by default — and the spring itself is now
   DECODED, not fitted** (2026-08, synthetic rigs + Moho 14.4, see § 3.5
   for the summary and `Skeleton.dynamic_angles`' EVIDENCE section for the
   tables): per-second units, semi-implicit Euler at `h = 1/fps`, spring
   ×96, damping ×0.85.  The old "per frame" claim in this section was
   wrong, and so was the "per-second is unusable" argument that went with
   it — the same document at 12/24/48 fps gave first-frame displacements
   scaling exactly with (1/fps)².

   The bone is modelled as a pendulum with inertia in **world** space. With
   `pw` for the parent's world angle and `x` for the bone's own local angle:

   ```
   x'' = 96·spring·(keyed − x) − 0.85·damping·(x' + pw') − pw''
   ```

   The `pw` terms are the point. An earlier version pulled the bone toward
   its own keyed angle and nothing else, so a bone whose `anim_angle` never
   moves could never move — and across the corpus that is the normal case,
   not the exception.  `BoneDynamics.animeproj` shows why the rewrite was
   needed: all six ear bones hold constant channels; what moves is their
   grandparent `Main` (the jump) and `TorsoA` (angle 250°…307°).  **The
   ears flop because they lag the parent's world motion.**

   **`torque_force` is now measured dead**: a translating parent rotates
   the child 0.0000 degrees at torque 0.1 and 6.0 alike, so the
   pivot-acceleration reading (rejected twice before on weaker evidence) is
   closed for good, and Bandit's tail — whose parent only translates — is
   not reachable through it.  `angle_weight` is measured live (the step
   response differs visibly at weight 1.0 vs the −1.0/0.0 baseline,
   non-monotonically across {0.5, 1.0, 2.0}) but unfitted, and stays
   unread.  Wind is still a negative result even on a purpose-built rig
   (physics on, strength 100, turbulence 0.8/2.0, `wind_dynamics` true,
   DarkMan's own B3 keys: 0.0000 degrees difference between wind on and
   off) — the DarkMan B3 observation must come from something other than
   those fields alone.  Unresolved: the units of the parent-coupling terms
   (per-second rates fit a gentle 0.5 rad/s ramp exactly but flung the
   BoneDynamics ears 30 px further off on TorsoA's ~12 rad/s swings;
   per-frame rates leave that document at baseline — kept, recorded not
   tuned), the chain solve (children see the parent's keyed pose, not its
   simulated lag), and mid-run switch initial conditions.

   **Bandit's tail is what the gap looks like.** Every layer of that document
   tracks Moho's own render to 0.3–2.8 px except the two in the tail, which
   sit 18 px (base) to 32 px (tip) off vertically — and the tail bones are
   its only two with dynamics on. In the reference the tail's bob is a copy
   of the body's, **lagged 4 frames** (cross-correlation 0.93 there against
   −0.91 at zero lag) and **amplified down the chain** (6.7 px standard
   deviation at the muzzle, 10.0 at the tail base, 15.1 at the tip). Lag plus
   gain is a resonant oscillator. Binding was ruled out separately: all 28
   rigid bindings, 5 subsets and all 4 falloffs leave that vertical error
   within about 2 px of each other — and the decoded spring does not close
   it, because Bandit's root never rotates and torque is measured not to
   couple translation, so the tail's ~18–32 px must come from a mechanism
   this model still does not contain.

   **It has a test, and the dynamics part of it no longer makes things
   worse.** `moho/track/BoneDynamics/` (29 frames, Moho's own export) is the
   clean case: 6 of its 7 dynamic bones are the two rabbit ears, no dynamic
   bone's own angle moves, no bone subscribes to wind.  With the decoded
   spring, turning `--bone-dynamics` on leaves the ears at their baseline
   (24.7/55.2 → 24.7/55.4 px dx right ear, mean/max) instead of worsening
   them as the old model did (60.6 px → 62.6 px).  Read that with care: the
   baseline is bad too — with dynamics off those ears are already ~55 px
   out, against 0.3–3.5 px for every layer of the other two reference
   documents, so something else in that rig is wrong as well and the
   dynamics signal is swamped. Ruled out so far: scale inheritance (fixed
   separately — it did bring the ears from ~78 px to ~60 px), the four
   `squash_stretch_scaling` cross-axis formulas, the four falloffs, control
   bones (its three drivers barely move), and the skin weights themselves
   (checked point by point — each ear point is 95 %+ dominated by its
   nearest bone).

   Cost: the state at frame F depends on every frame before it, so each call
   simulates from the start frame. Measured end-to-end on a full Lottie
   export — `Bandit` 6s → 9s, `WhatIsBone` ~35s → 1m45s. Moho adds
   spring/damped secondary motion on top of the keyed pose, so ignoring it
   makes motion read as *more* abrupt than Moho's, not less. Control bones
   (`angle_/pos_/scale_control_parent`) are set on 9 bones across 4 of those
   documents. **Neither is used anywhere in `SketchBone.animeproj`** — all
   five of its skeletons (`cat_boy` 42 bones, `kafasi` 21, `el-sol` 11,
   `el-sag` 11, `Sketch` 9) have zero of each, so neither can explain that
   rig's ear behaviour.
2. **Flexible-binding falloff shape** — the four candidate shapes are now
   **distinguishable**, and they disagree. Scored with `make check-reference`
   (sum of mean positional error over the layers each document can address):

   | Falloff | SketchBone, 10 layers | Bandit `TailBase` dx | Bandit `Belly` dy |
   |---|---|---|---|
   | `inv_d2` (default) | **34.15** | 8.25 px | 3.02 px |
   | `cut_d2` | 35.54 | 6.38 px | 3.02 px |
   | `hermite` | 41.53 | 2.02 px | 1.62 px |
   | `linear` | 43.58 | **1.89 px** | **1.59 px** |

   The bounded-support shapes win every Bandit layer that blends many bones
   and lose every comparable SketchBone layer (`kuyruk` 2.37 → 6.24 px,
   `golge` 6.48 → 10.47 px). **So none of the four is Moho's actual
   function.** `inv_d2` stays the default because it wins the broader
   reference — 10 layers against 3, and the newer format.

   This also explains why nothing distinguished them before: a layer where
   one bone dominates scores *identically* under all four. `Bandit`'s `Tip`,
   bound to just two bones, does exactly that.

3. **Smart Warp** — invisible here (0 files), but a document that uses it
   loses the whole deformation silently. Detection is cheap; support is not.
4. ~~**`end_percent` animation** — not exercised here, common in production.~~
   **Implemented** for a plain stroke, per frame, measured against a
   purpose-made Moho render ([§ 6.3](#63-curve-trimming-start_percent--end_percent));
   still unapplied on brush/tapered outlines, which warn.
5. **Control bones** — small in this sample, but a total miss where used.
6. **IK with a moving target** — usually baked, occasionally not.
7. ~~**Independent angle (`fixed_angle`)** — 45 bones; effect unverified.~~
   **Measured and applied** — worth up to 16 px where used, and about a third
   of that still unexplained ([§ 3.2](#32-independent-angle-fixed_angle)).
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
  was checked. Also try `curver` (not just `warp`) since
  [§ 5.1b](#51b-the-mechanism-from-mohos-own-scripting-api--still-not-a-file-finding)
  found that spelling in Moho's own API for the same feature — zero hits
  for that one too, in every sample document checked so far.
- A channel's value: read `val[0]` for the first keyframe and `len(when)` for
  the number of keys. A field like `bone_dynamics` is a channel, not a bool,
  and counting it as a bool gives the wrong answer.
