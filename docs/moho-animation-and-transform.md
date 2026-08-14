# Moho Animation and Transform Model

Moho does not animate frame by frame. It stores a small number of **keyframes**
per property and lets the program compute every frame in between. Most of the
motion in a real Moho document does not even live on the artwork: it lives on a
**skeleton**, and the artwork follows the bones through a transform stack.

This document explains that model: how time is stored, how a value at an
arbitrary frame is produced, where motion actually comes from in real files,
and how the transform stack turns all of it into a point on the canvas.

Companion documents:

- `moho-project-file-format.md` — the full field reference for the file format.
- `moho-rigging-and-deformation.md` — the bone system in depth (constraints,
  control bones, IK, dynamics), Smart Warp, and the mesh-level fields that
  constrain deformation.
- `export-pipeline.md` — how `moho2svg.py` walks a document and emits SVG.
- `exporting-svg.md` — command-line usage.

This document does not repeat those. It focuses only on time and transforms,
and it adds decoding work that the other documents mark as unknown.

---

## 1. Scope and evidence base

Every number here was measured from the 19 project files in the (gitignored)
`moho/` directory: 17 `.animeproj` files (format versions 1021 and 1038) and 2
`.mohoproj` files (1038 and 1045). Nothing is quoted from Moho's own
documentation.

The measuring method matters, because it changes the counts:

- Every JSON object that carries all four of `type`, `when`, `val` and `interp`
  is treated as a channel.
- The walk **descends into nested channels**: `actions[].pose` (Smart Bone
  poses) and `split[]` (per-axis curves) are separate channels and are counted
  separately from the channel that owns them.

That yields **584,616 channels** and **604,139 `interp` entries** across the 19
files. The channel total matches `moho-project-file-format.md` § 5, so the two
documents count channels the same way. The `interp` totals differ (that
document reports about 210,000 entries), so treat the `interp` statistics below
as the newer measurement.

Claims are labelled:

- **Confirmed** — read directly from the files, with counts.
- **Inference** — the best reading of the evidence, with the evidence given.
- **Not decoded** — observed, but the meaning is unknown. Not guessed.

---

## 2. The core idea: sparse keyframes on independent channels

### 2.1 One channel per property

Almost every property in Moho — a point position, a bone angle, a fill colour,
a layer's rotation, even the name of the visible child of a switch layer — is
stored as the same channel object:

```jsonc
{
  "type": "Val",              // value kind: Val, Vec2, Vec3, Color, Bool, String
  "when": [0, 25, 33, 41],    // keyframe times, in frames
  "val":  [3.14, 3.20, 2.84, 3.20],
  "interp": [ {...}, {...}, {...}, {...} ]   // one entry per keyframe
}
```

There is no document-wide list of frames and no per-frame snapshot of the
scene. A frame is not stored at all; it is **computed** by asking every channel
what its value is at that time. This is what makes Moho files small relative to
their length, and it is why `moho2svg.py` can export any frame without a
"playback" concept: exporting frame `N` means evaluating channels at `N`.

### 2.2 Most channels never move

**Confirmed.** Of the 584,616 channels, **571,915 have exactly one keyframe**
(97.8%) and only **12,701 have two or more** (2.2%). A single-keyframe channel
is a constant; it exists only because Moho stores every property in the same
shape.

Keyframe counts per channel:

| Keyframes | Channels |
|---|---|
| 1 | 571,915 |
| 2 | 10,669 |
| 3 | 943 |
| 4 | 385 |
| 5–9 | 350 |
| 10–19 | 342 |
| 20+ | 12 |

The busiest channel in the whole sample has 20 or more keyframes, and there are
only 12 of those. Real Moho animation is built from very few keys.

### 2.3 Frame numbering, and what frame 0 means

**Confirmed.** All 19 documents use `fps: 24.0`. The authored range is
`project_data.start_frame` … `end_frame`, and `start_frame` is **1** in 18
documents and **25** in `Bandit.mohoproj`. It is never 0.

Frame **0** is the rest / setup frame, not the first frame of the animation:

- Keyframes at frame 0 hold the rig's neutral state.
- `moho2svg.py` computes every bone's rest pose at **frame 0.0** exactly
  (`Skinner.build`), and the deformation of a mesh is defined relative to it.
- `--frame` defaults to `0`, so the tool's default output is the **rest pose**,
  which in every sample document is outside the authored range.

Keyframe times may also lie **past** `end_frame`, because action timelines are
independent of the main timeline (see [§ 7](#7-actions-and-smart-bones)):

| Document | Authored range | Latest keyframe time |
|---|---|---|
| `AddBone.animeproj` | 1–25 | 175 |
| `ControlBones.animeproj` | 1–120 | 240 |
| `WhatIsBone.animeproj` | 1–240 | 227 |
| `Bandit.mohoproj` | 25–127 | 87 |
| `ReparentBone.animeproj` | 1–120 | 0 (nothing is animated) |

### 2.4 Negative keyframe times exist, and they are not animation

**Confirmed.** Negative `when` values appear in only two places:

- `timeline_markers` channels, always as the single value `-1000000`.
- Two `transforms.translation` channels in `SlickObjectTransition.mohoproj`,
  with times such as `-999916`, `-999971`, `-999970`, `-999919`.

**Inference:** `-1000000` is a sentinel base ("far before the timeline") rather
than a real time, and the near-sentinel translation keys are leftovers of the
same mechanism. Their values are the layer's defaults, so ignoring them is
harmless. The mechanism itself is **not decoded**.

Practical effect: a linear evaluator that clamps at the first keyframe returns
those leftover values for every frame before the next real key. In the two
observed channels the leftover value equals the frame-0 value, so nothing is
visibly wrong.

---

## 3. How a value between keyframes is produced

### 3.1 What the file stores

`when[i]`, `val[i]` and `interp[i]` are **always the same length** (confirmed on
all channels, no exceptions). `interp[i]` describes the segment **leaving**
keyframe `i`, so the last entry describes nothing — except when it carries the
cycle marker (see [§ 3.4](#34-v1--v2-and-the-cycle-marker-on-the-last-keyframe)).

Each `interp` entry has a fixed shape:

```jsonc
{ "im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0,
  "b": [ {"ao": 0.000823, "ai": -0.00003, "po": 0.4375, "pi": 0.515625} ] }
```

`s` is `false` and `h` is `0` on all 604,139 entries. `in` is `1` except on
2,052 entries, all of them `fill_color`, `3d_thickness` or `line_color`. Both
are **not decoded**.

### 3.2 `t` — the interpolation type

**Confirmed** distribution over 604,139 entries:

| `t` | Count | Where it appears |
|---|---|---|
| `0` | 602,784 | everywhere; the default |
| `4` | 757 | `anim_pos`, `anim_scale`, `anim_angle`, action poses |
| `2` | 540 | the same fields |
| `256` | 33 | `physics_motor_speed` only |
| `3` | 16 | `physics_motor_speed` only |
| `1` | 4 | `physics_motor_speed` only |
| `6` | 3 | `physics_motor_speed` only |
| `5` | 2 | `physics_motor_speed` only |

**Confirmed and useful:** every entry with `t` outside `{0, 2, 4}` sits on a
channel with a **single keyframe**, where there is no segment to interpolate.
On channels that actually move, only three values are ever observed: `0`
(default), `2`, and `4`.

**Not decoded:** which Moho interpolation mode each number names. `t` cannot be
read as "4 = Bezier", because `t == 4` occurs in three different contexts: with
default parameters, with explicit Bezier handles, and with the cycle marker.
The value mixes freely inside one channel — a single walk-cycle `anim_angle` in
`Bandit.mohoproj` carries `t = [0, 4, 4, 2, 2, 2, 4, 4, 2, 2, 4]` — so it is a
per-keyframe choice made by the animator, not a channel-wide setting.

### 3.3 `im` — a flag field, partly decoded

**Confirmed** distribution: `1` (446,672), `3` (151,877), `0` (3,803), `2`
(1,085), `5` (493), `9` (182), `7` (27).

Those are exactly the values you get from a 4-bit field using bits 1, 2, 4 and
8, and two of the bits line up with observable data:

| Bit | Evidence | Reading |
|---|---|---|
| `8` | `im == 9` on **182** entries; the `b` array is present on **exactly the same 182** entries, and never elsewhere | **Inference (strong):** bit 8 means "explicit Bezier handles are stored in `b`" |
| `4` | `im` values `5` and `7` total 520 entries; **471** of them are the **last** entry of their channel, and they are the only entries carrying the unusual `v1`/`v2` pairs listed below | **Inference:** bit 4 means "this keyframe carries a cycle setting" |
| `1`, `2` | `im == 3` (bits 1+2) occurs 151,877 times, and 151,875 of those are on single-keyframe channels | **Not decoded** |

### 3.4 `v1` / `v2`, and the cycle marker on the last keyframe

**Confirmed.** The pair `(0.1, 0.5)` appears on **601,344 of 604,139** entries —
it is the untouched default and carries no information. `(-1.0, -1.0)` appears
on channels the animator has actually worked on.

Everything else appears only together with the `im` bit-4 flag, on a channel's
final keyframe:

| `(v1, v2)` | Count |
|---|---|
| `(-1.0, 2.0)` | 278 |
| `(15.0, -1000000.0)` | 140 |
| `(-1.0, 1.0)` | 47 |
| `(23.0, -1.0)` | 26 |
| `(15.0, -1.0)` | 2 |

**Inference:** this is Moho's *cycle* setting, stored on the last key of a
cyclic channel — `v1` looks like an absolute frame to jump back to (`-1` when
unused) and `v2` like a repeat count (`-1000000` for "forever"). The evidence is
positional (last keyframe) and contextual (only on animated rig channels such as
`Bandit.mohoproj`'s walk cycle); the exact meaning of each number is **not
confirmed**.

Consequence for any tool that ignores `interp`: a cycled channel is **not**
cycled. Past the last keyframe the value is clamped instead of repeating. In
`Bandit.mohoproj` the walk cycle stops at frame 41 rather than looping.

### 3.5 `b` — the Bezier timing handles, decoded

The `b` array is present on 182 entries. Its **length equals the number of
components in the channel's value** — confirmed with no exceptions:

| Channel `type` | `len(b)` | Entries |
|---|---|---|
| `Val` | 1 | 101 |
| `Vec3` | 3 | 38 |
| `Vec2` | 2 | 19 |
| `Bool` | 1 | 17 |
| `Color` | 1 | 5 |
| `String` | 1 | 2 |

So `b[c]` holds the timing curve of component `c` — each axis of a `Vec2`/`Vec3`
has its own handles. (`Color` gets a single entry, not four.)

Each entry is `{"ao", "ai", "po", "pi"}` — "out" and "in" of a handle pair:

- `po` / `pi` are **time fractions of the segment**, defaulting to `0.333333`
  (one third), which is the classic Bezier handle length. Observed values stay
  within `0 … 1`. **Inference, strong.**
- `ao` / `ai` are the matching **value-side** components. Reading them as a
  *tangent* (value units per frame) is supported by a chain property: on 93 of
  153 consecutive handle pairs, `interp[i].b[c].ai` is bit-for-bit equal to
  `interp[i+1].b[c].ao`, across segments of **different durations**. Equal
  numbers across unequal segments fit a rate, not an absolute offset. The
  remaining 60 pairs differ, which is what a deliberately broken (non-smooth)
  handle would look like. **Inference, medium.**

This is the timing curve that makes Moho's motion ease in and out. Only a
handful of keyframes in these 19 documents use it explicitly; everything else
relies on the default (`t = 0`) curve, whose exact shape is **not decoded**.

### 3.6 What `moho2svg.py` does instead

`Channel.eval_raw` ignores `interp` completely and interpolates **linearly**
between the two bracketing keyframes, clamped at both ends:

- numbers → linear interpolation;
- `{x,y}`, `{x,y,z}`, `{r,g,b,a}` → linear per component;
- strings and booleans → snap to the left keyframe (no interpolation), which is
  the only correct choice for a switch-layer name or a visibility flag.

Consequences, in order of practical importance:

1. **Exact at every keyframe.** Any frame that is a keyframe of every relevant
   channel is reproduced exactly, apart from the rig features in
   [§ 6](#6-motion-that-is-not-keyframed).
2. **Approximate between keyframes.** Linear motion instead of eased motion.
   The visible size of the error depends on the segment, and it is largest on
   long segments with strong easing.
3. **No cycling.** See [§ 3.4](#34-v1--v2-and-the-cycle-marker-on-the-last-keyframe).
4. **`split` is ignored** — the parent `Vec2`/`Vec3` arrays are read instead.
   Only one channel in the whole sample uses `split` (an `anim_pos` in
   `Bandit.mohoproj`), and its split curve matches the parent, so nothing is
   currently wrong.

To put a number on point 2: re-evaluating the 63 `Val` segments that carry
explicit handles, under the tangent reading of `ao`/`ai` from
[§ 3.5](#35-b--the-bezier-timing-handles-decoded), the largest gap between the
eased curve and the straight line is about **0.14 rad (8°)** mid-segment — on
the `anim_angle` pose of the `TorsoA` bone in `Rabbit.animeproj`'s `Jump`
action, whose two keys are only 0.22 rad apart. That number inherits the uncertainty of the tangent reading, so treat it
as an order of magnitude: **mid-segment error can be a large fraction of the
key-to-key change, while keyframes stay exact**.

---

## 4. Where the motion actually is

This is the part that explains why Moho files look the way they do. Counting
**multi-keyframe channels only** — that is, the properties an animator really
moved — over all 19 documents:

| Field | Multi-key channels | What it animates |
|---|---|---|
| `actions[].pose` | 11,816 | a stored pose curve (Smart Bones and actions) |
| `anim_angle` | 383 | bone rotation |
| `position` | 159 | a mesh point moving directly |
| `anim_scale` | 151 | bone scale |
| `anim_pos` | 146 | bone position |
| `bone_dynamics` | 14 | physics switched on/off over time |
| `translation` | 8 | a layer's own position |
| `scale` | 4 | a layer's own scale |
| `offset_in` / `offset_out` | 8 | Bezier handle shape of a curve point |
| `layer_effects.visibility` | 4 | animated show/hide |
| `rotation_z` | 3 | a layer's own rotation |
| `flip_h` | 2 | horizontal flip |
| `switch_keys` | 2 | which switch-layer child is visible |

Read that table as the summary of Moho's design: **motion is stored on the
rig, not on the drawing**. Direct point animation (159 channels) is rare;
layer-transform animation (15 channels) is rarer still; bone channels and
stored poses account for almost everything.

Per document, the motion source is easy to identify:

| Document | Primary motion source |
|---|---|
| `Bandit.mohoproj` | bones (`anim_pos`/`anim_angle`/`anim_scale`, 25 each) plus a `Walk` action |
| `WhatIsBone.animeproj` | bones (214 animated `anim_angle`) plus poses and a switch layer |
| `SketchBone.animeproj` | bones plus poses, a switch layer (mouth), and `flip_h` |
| `OffsetBoneTool.animeproj` | direct point animation (132 `position` channels) plus bones |
| `SlickObjectTransition.mohoproj` | **layer transforms only** — no skeleton at all |
| `AddBone`, `TargetBone`, `IK-FK`, `ControlBones`, … | stored poses only |
| `ReparentBone`, `SelectandReparentBoneTool` | nothing is animated (rig demos) |

`SlickObjectTransition.mohoproj` is the useful counter-example: a document that
animates `translation`, `scale`, `rotation_z`, `visibility` and even curve-point
handles (`offset_in`/`offset_out`) with no bones anywhere.

---

## 5. The transform stack

A drawn point travels through several spaces before it lands on the canvas.
The order is fixed, and getting it wrong is the classic way to produce output
that looks *almost* right.

### 5.1 A layer's own matrix

`transforms` holds ten channels; five of them define the 2D matrix:
`translation` (`Vec3`), `scale` (`Vec3`), `rotation_z` (`Val`), `flip_h` and
`flip_v` (`Bool`). Rotation and scale pivot on the layer's `origin` — a plain
(non-animated) point — not on local `(0, 0)`:

```
p' = origin + translation + R(rotation_z) · S(scale_x, scale_y) · (p - origin)
```

`flip_h` / `flip_v` negate `scale_x` / `scale_y`. Layer scale is genuinely
**per axis**; a bone's scale is a single scalar (see § 5.3).

The remaining transform channels — `rotation_x`, `rotation_y`, `shear`,
`following`, `physics_nudge`, and the `z` components — are **not used** by
`moho2svg.py`. All are at their defaults in the samples except the `z`
components, so nothing observed is currently wrong.

### 5.2 The chain, and why skinning is not just another matrix

The matrices of the ancestor chain compose in the usual way, **but bone
deformation is not a matrix and does not commute with them**. Skinning happens
in the bone layer's *own* coordinate space:

```
raw mesh point (the mesh layer's own space)
      |  every local matrix between the mesh and the bone layer, composed
      v
the BoneLayer's own space          <- the skeleton's matrices live here
      |  skinning (rigid or flexible)
      v
still the BoneLayer's own space, now posed
      |  the bone layer's own local matrix, then everything above it
      v
document space
      |  2 units span the canvas height, y flipped
      v
pixel space
```

So a mesh nested several groups deep inside a `BoneLayer` is deformed *after*
the local transforms between it and the bone layer, and *before* the bone
layer's own transform. `build_deform_chain` in `moho2svg.py` produces exactly
this ordered list of steps; `export-pipeline.md` § 4.2 has the implementation
detail.

One deliberate inconsistency is worth knowing about: **stroke width uses a
different traversal** that composes every layer matrix but **excludes bone
deformation**. That is not an oversight — including bone deformation inflated
stroke width by about 11% on a walk-cycle test.

### 5.3 Bone transforms

Each bone carries `anim_pos` (`Vec2`, relative to the parent bone), `anim_angle`
(`Val`, radians) and `anim_scale` (`Val`, a single scalar). A bone's world
matrix is its parent's world matrix times its own local matrix, with parents
resolved before children regardless of list order — the `bones` array is not
guaranteed to be topologically sorted.

The local matrix as implemented scales only the first column:

```
local = Mat2D(cos·scale, sin·scale, -sin, cos, pos.x, pos.y)
```

That asymmetry is **kept on purpose**. It matches every available reference
render, and no sample exercises a bone whose `anim_scale` is far from `1.0` in
a way that could distinguish asymmetric from uniform scaling. `scaling_mode`
(observed `0` and `2`) is a plausible explanation and is **not decoded**. Do
not "fix" this without new reference evidence.

### 5.4 Rigid and flexible binding

Binding is decided **per layer** by `parent_bone`:

- `parent_bone >= 0` — **rigid**: every point follows that one bone exactly.
- `parent_bone == -1` — **flexible / region**: every point is a
  distance-weighted blend of all bones, or of the subset named by
  `flexi_bone_subset` (a `"|"`-joined list of bone **indices**, as a string).

A third value, `parent_bone == -3`, appears on 9 `ImageLayer` instances and is
not decoded.

Rest pose is evaluated at frame 0.0, and each bone contributes
`pose · rest⁻¹`. A bone with `strength <= 0` is skipped entirely before any
weighting — that is Moho's "this bone does not deform this mesh" gate (241 of
850 bones). The falloff shape used for the blend (inverse distance squared) is
a **heuristic** that no available reference could confirm against the
alternatives.

The step-by-step skinning math, the full bone-field reference, and the
per-feature cost of ignoring constraints/IK/control bones are in
[`moho-rigging-and-deformation.md` § 2](moho-rigging-and-deformation.md#2-the-bone-system).

---

## 6. Motion that is not keyframed

This is the largest gap between "the file says" and "Moho shows", and it is the
part most easily missed: several rig features **generate motion at render time**
without writing any keyframe. Nothing bakes them into `anim_angle`.

**Confirmed by direct field inspection of all 850 bones:**

| Feature | Fields | Where it is switched on |
|---|---|---|
| Bone dynamics (spring physics) | `bone_dynamics` (`Bool` channel), `spring_force`, `damping_force`, `torque_force` | **115 bones in 6 documents**: `WhatIsBone` (52), `Bandit` (28 — every bone), `AddBone` (21), `BoneDynamics` (6), `Rabbit` (6), `ControlBones` (2) |
| Angle dynamics | `angle_dynamics` | 2 bones in `Bandit.mohoproj` |
| Angle constraints | `constraints`, `min_constraint`, `max_constraint` | **158 bones in 11 documents** |
| Control bones | `angle_control_parent`, `pos_control_parent`, `scale_control_parent` (+ `_scale`, `_delay`) | 4 documents: `ControlBones` (2 bones each for angle/pos/scale), `BoneDynamics`, `AddBone`, `Rabbit`. `Bandit` sets only `scale_control_delay` (8, on one bone) |
| IK targets | `target_bone`, `ik_lock`, `ik_global_angle`, `ignored_by_ik` | `target_bone` set on 41 bones across 14 documents (1–8 bones each) |
| Reparenting over time | `anim_parent` | never keyframed here — see below |

> **Correction.** `moho-project-file-format.md` § 9 states that the
> physics/dynamics fields are "all disabled in the samples". That is not
> correct: `bone_dynamics` is a `Bool` channel whose value is `true` on 115
> bones, and `BoneDynamics.animeproj` even keyframes it (7 channels with more
> than one key). The § 9 bullet has been corrected to match.

Why this matters for any exporter: `Bandit.mohoproj` has dynamics enabled on
all 28 of its bones — 22 of them with `spring_force: 2.0`,
`damping_force: 1.0`, `torque_force: 2.0`, and 6 tuned individually — while its
`anim_angle` channels hold only the animator's own keys. In Moho, the springy follow-through is added on top of those keys at
playback time. A tool that evaluates channels only — as `moho2svg.py` does —
renders the keyed pose **without** the secondary motion. So this is an
**exercised** gap, not a theoretical one: still frames are missing overlap and
follow-through that Moho would show, and the gap grows with distance from a
keyframe.

Two features in the table are safe to ignore, and this is measured rather than
assumed:

- **`anim_parent`** (bone reparenting over time): all 850 channels have exactly
  one keyframe, and that value equals the bone's static `parent` in 850 of 850
  cases. Even `ReparentBone.animeproj` demonstrates the *tool* without ever
  keyframing a reparent.
- **Constraints**: they limit what the animator could pose in the editor; the
  resulting angle is already stored in `anim_angle`.

Each of these features is covered field by field, with the cost of ignoring
it, in
[`moho-rigging-and-deformation.md` § 3](moho-rigging-and-deformation.md#3-bone-constraints-and-rig-helpers).
Two rig fields not listed in the table above also turned out to be non-default
somewhere in the sample: `bone.offset` (5 bones, the Offset Bone tool) and
`skeleton.binding_mode` (`2` on one skeleton). Neither is decoded.

---

## 7. Actions and Smart Bones

Actions are how Moho reuses motion. They live in two different places that look
alike.

### 7.1 The name registry

Nearly every layer carries `actions: [{"name": "...", "pose": 0}]` — 19,921
entries in the sample, with `pose` an integer `0` every time. This is a
**document-wide registry of action names, replicated on almost every layer**,
not a per-layer list. Evidence: a `BoneLayer` with **zero bones** in
`WhatIsBone.animeproj` carries the same 37 action names as the 157-bone layer
above it.

### 7.2 The pose curves

The real data is on individual channels. Any channel may carry its own
`actions` list, and there `pose` is a **complete nested channel** with its own
`when`/`val`/`interp`:

```jsonc
"actions": [
  { "name": "EyeBlink",
    "pose": { "type": "Vec2", "when": [0, 6, 12], "val": [...], "interp": [...] } }
]
```

There are 11,816 such poses — the single most keyframed thing in these
documents, far ahead of `anim_angle`'s 383 channels. **All 11,816 have two or
more keyframes**, without exception, which is what the dial inversion in
[§ 7.3](#73-dials-versus-plain-actions) needs: a curve with one point cannot be
inverted. Pose channel types are
`Vec2` (10,024), `Val` (1,561), `Vec3` (165), `Color` (37), `Bool` (22) and
`String` (7): an action can override any property, including colour.

An action's timeline is **its own**, which is why keyframe times can exceed the
document's `end_frame` ([§ 2.3](#23-frame-numbering-and-what-frame-0-means)).

### 7.3 Dials versus plain actions

A registered action name becomes a **Smart Bone dial** when it matches the
`name` of a bone in the enclosing `BoneLayer`'s skeleton. Names that match no
bone are **plain actions**: reusable clips the user triggers from Moho's
Actions window. Nothing in the file says a plain action is running, so a
renderer must leave it off — `Bandit.mohoproj`'s `"Walk"` is exactly this case.

When dial `D` is active, a channel carrying an entry named `D` reads from that
pose instead of its own keys, at a frame found by **inverting the pose curve**:
the pose's `val` array records what the dial's own angle was at each pose
keyframe, so "the pose frame whose recorded angle equals the dial's current
angle" is well defined. Because a curve must be roughly monotonic to be
invertible, Moho stores two actions per dial, one per rotation direction, the
second suffixed `" 2"` (`"BlinkL"` and `"BlinkL 2"`).

Resolving the dial's own current angle must **not** go through the override
machinery the dial is part of; it reads the raw channel.

---

## 8. Switch layers: discrete animation

A `SwitchLayer` shows exactly one child at a time, and which one is animated by
`switch_keys` — a `String` channel whose values are **child layer names**.
Because strings snap to the left keyframe, this is a step function, which is
exactly right for mouth shapes.

**Confirmed**, both animated instances in the sample:

- `SketchBone.animeproj`: `when = [0, 74, 76, 78, 80, 82, 84, 86]`,
  `val = ["agiz", "agiz", "agiz 2", "agiz 3", "agiz 4", "agiz 5", "agiz 6",
  "agiz"]` — a mouth cycling through six shapes on every second frame, i.e.
  lip sync.
- `WhatIsBone.animeproj`: `when = [0, 1]`, `val = ["agiz1", "agiz6"]`.

`moho2svg.py` implements this (`Layer.switch_active_child`), including a
fallback that Moho itself uses: if the recorded name matches no child — which
happens when a child was renamed after the key was set — the **first** child is
drawn rather than nothing.

---

## 9. Camera animation

`doc.animated_values` holds five channels: `camera_track` (`Vec3`),
`camera_pan_tilt` (`Vec2`), `camera_zoom` (`Val`), `camera_roll` (`Val`) and
`timeline_markers` (`String`). All have exactly one keyframe at frame 0 in all
19 documents, so no sample animates the camera.

`moho2svg.py` reads none of them and renders with an implicit fixed camera.
`Rabbit.animeproj` has a genuinely non-default `camera_track` and
`camera_zoom`, so framing in that document is not guaranteed to match Moho's.

---

## 10. Rendering animation with `moho2svg.py`

The tool exports **one frame per run**. There is no built-in sequence mode.

```bash
# One frame (frame 0 = the rest pose, which is before the authored range)
python3 moho2svg.py moho/Bandit.mohoproj --combined out/frame_0025.svg --frame 25

# A whole range, one SVG per frame
for f in $(seq 25 127); do
  python3 moho2svg.py moho/Bandit.mohoproj \
      --combined "out/frame_$(printf '%04d' "$f").svg" --frame "$f"
done
```

Notes that come from actually running this:

- **Output is deterministic** for a given frame: exporting the same frame twice
  produced byte-identical files (verified on `Bandit.mohoproj` frame 41).
- **Frames differ as expected**: frames 0, 25, 33 and 41 of `Bandit.mohoproj`
  each produced different geometry.
- **Clamping is per channel, not per document.** Frame 200 is past the last
  bone key (41) but not past every channel in the file (the latest key is 87),
  so it is not identical to frame 41. Only a frame past *every* channel's last
  key is a true freeze.
- **`--frame` takes an integer.** The evaluator itself works in floating point,
  so sub-frame sampling is possible in code but not from the command line.
- Add `--brush-dir ""` while iterating: brush stamping dominates export time,
  and turning it off makes a per-frame loop practical.
- Use the **same flags for every frame**. Changing `--crop` between frames
  changes the viewBox and the sequence will jitter.

---

## 11. Gap summary for animation and transforms

Ordered by how likely it is to change what you see.

| Gap | Status | Effect |
|---|---|---|
| Bone dynamics (springs) ignored | **exercised** — 115 bones in 6 documents | missing follow-through / overlap; worst far from a keyframe |
| Easing (`interp`) ignored, linear used instead | **exercised** — every multi-key channel | exact at keyframes, approximate between them |
| Cycle setting ignored | **exercised** — ~470 channels carry the marker on their last key | motion stops at the last key instead of repeating |
| `layer_effects.visibility` ignored | **exercised** — 4 animated channels in `SlickObjectTransition` | a layer that should appear/disappear mid-animation does not |
| Control bones (`*_control_parent`) ignored | **exercised** — a handful of bones in 4 documents | driven bones do not follow their driver |
| IK (`target_bone`) ignored | partly exercised | the solved pose is usually already in `anim_angle`; a target-driven limb may not be |
| Camera channels ignored | not exercised (all static) | framing would be wrong in a document with a moving camera |
| `split` per-axis curves ignored | not exercised (1 channel, matching values) | wrong values if the axes are keyed differently |
| `mute: true` channel still animated | not exercised (the one muted channel has a single key) | a muted multi-key channel would move when Moho freezes it |
| `anim_parent` (reparenting) ignored | **not exercised** — 850/850 match the static parent | none, for these files |

---

## 12. Reproducing the numbers

Every count in this document comes from walking the raw JSON of the 19 files in
`moho/`, with these rules:

1. A dict holding all of `type`, `when`, `val`, `interp` is a channel.
2. Descend into `actions[].pose` and `split[]` and count those as channels of
   their own.
3. "Animated" means `len(when) > 1`.
4. For bone flags stored as channels (`bone_dynamics`, `target_bone`, …), take
   `val[0]` and compare against the field's default.

Rule 2 is the one that changes results the most: skipping nested poses hides
11,816 of the 12,701 animated channels — that is, it hides most of the
animation in a rigged Moho document.
