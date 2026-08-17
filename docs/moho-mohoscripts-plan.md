# Moho scripts (`mohoscripts/`) — analysis and work plan

This document is the working plan for mining the third-party Moho script
collection under `mohoscripts/` for two things this repository needs:

1. **Behaviour evidence.** A Lua script runs *inside* Moho and calls Moho's own
   API. When a script computes a Bezier handle, a bone world matrix or a cycled
   channel value, it is telling us what Moho itself does — a second opinion next
   to the empirical measurement this repository was built from.
2. **Field and channel names.** The scripts name fields that the JSON file
   format also carries, often with a version comment (`-- AS 7.0`,
   `-- MOHO 14`). That is a ready-made checklist of what a reader of the format
   could decode.

`mohoscripts/` is **gitignored**, like `moho/` and `docs/moho14/`. Paths below
point at local material that is not part of this repository.

## Status

| | |
|---|---|
| Corpus read | 2026-08-17 |
| Files | 197 `*.lua`, 161,409 lines, 5.7 MB — **121 unique by content**, 88,494 lines |
| Plan steps | 14 — Steps 1–7 and 13 done (7 partly), 0 and 8–12 open |

---

## 1. How the corpus was read

**Deduplication first.** 76 of the 197 files are byte-identical copies of a
shared utility that ships inside several script bundles: `FO_Utilities.lua`
(2,422 lines) appears in 21 `LK_*` bundles, and there are further 20x, 19x, 5x,
4x and 2x duplicate groups. Every count in this document is over the **121
unique** files.

**Two reading depths.** Every one of the 121 unique files was inventoried and
mechanically analysed (see the extraction tables in § 3 and the file list in
Appendix A). A subset was then read line by line, chosen by how densely each
file uses format-relevant API:

| Depth | Count | Files |
|---|---|---|
| Read in full | 12 | `ae_utilities.lua`, `ae_curvature.lua`, `FO_Channels.lua`, `mr_bake_bone_dynamics.lua`, `LK_MaskSettings.lua`, `ss_cycle_keys.lua`, `ss_ae_camera_export.lua`, `ss_curve_exposure.lua`, `ae_mix_smartbones.lua`, `ae_smart_granchildren.lua`, `ae_seamless_rotation_smart_maker.lua`, `ae_fixedangle.lua` |
| Read in part (targeted functions) | 5 | `ae_keytools.lua` (cycles), `mr_utilities.lua` + `mr_tween_machine.lua` (`GetFadeFactor`), `mr_continue_animation.lua` (`ContinueAnimationChannel`), `LK_Curvature.lua` (handles) |
| Inventoried + symbol-mapped only | 104 | Appendix A |

Step 0 of the plan finishes the full reads for the files that the symbol map
marks as format-relevant. Nothing found so far depends on that step; it is
there to catch what a mechanical scan cannot.

**What the scripts are not.** They are third-party work, not an authority:

- A script can be **wrong**, or right only for the cases its author tested.
  § 2.10 records one arithmetic slip and one deliberately approximate model.
- Licences vary and are often unstated (`ss_cycle_keys.lua` says "Use and Abuse
  freely"; most say nothing). **Use them as evidence for behaviour; do not copy
  code into this repository.** Every change below must be re-derived and
  re-verified against Moho's own output the way the rest of this repository was.
- The verification bar does not move: `make check-reference` for anything that
  touches time, transforms or bone flips, and a Moho raster/SVG render for
  anything else (see `CLAUDE.md`).

**Script families.** Prefixes are authors, which matters when weighing
evidence: `ae_*` (Alexandra Evseeva — the deepest rig/curve work),
`mr_*` (Eugene Babich), `LK_*` + `FO_*` (Lukas Krepel), `ss_*`/`SS_*` (Sam
Cogheil / SimplSam), `sz_*`, `am_*`, `hs_*`/`HS_*`, `ms*` (MinimalScript),
`lm_*`/`LM_*` (Lost Marble's own shipped scripts, modified).

---

## 2. Headline findings

Each entry states what the script shows, what this repository currently does,
and which plan step follows from it.

### 2.1 An exact Bezier handle formula → Step 2

`ae_utilities.lua:10` (`AE_Utilities:GetBezierValue`) reconstructs a control
handle from curvature/weight/offset:

```
N = normalize(P[i+1].anim_pos − P[i−1].anim_pos)     -- chord between the two NEIGHBOURS
if pre-handle: N = −N
L = |P[second].anim_pos − P[i].anim_pos| × curvature × weight
                                          -- second = i+1 for the post handle, i−1 for the pre
vec = rotate(N × L, offset)               -- offset is an angle in radians
handle = P[i].anim_pos + vec
```

Endpoints of an open curve get the point itself (no handle); closed curves wrap
the index, open curves clamp. `ae_curvature.lua:202` inverts the same relation
(`|handle| = length × curvature × weight`) and `ae_curvature.lua:339` confirms
`offset` is an added rotation.

This repository reconstructs handles with an empirically fitted,
chord-length-weighted blend (`BezierReconstructor`, module docstring).

**Resolved in Step 2, and the answer is "already known".** The direction part of
this formula is the "public Moho scripting snippet" the module docstring already
rejects — now identified by name — and it is exactly this repository's own
formula at `tangent_bias = -1`. The fitted `0.19` wins against Moho's own SVG
export (0.02° vs 3.4° median error). The handle *length* half, however, matches
this repository exactly and stands as independent corroboration.

### 2.2 `fixed_angle` is applied when composing world matrices → Step 1

The repository documents `fixed_angle` ("Independent Angle", `true` on 65 bones
across 22 corpus documents) as an **open risk, effect unverified**
(`docs/moho-rigging-and-deformation.md` § 3.2, confidence 4/10 that ignoring it
is safe). Two independent scripts settle the direction:

- `ae_utilities.lua:397` (`GetBoneMatrix`): subtract the accumulated parent
  angles walking up the chain, stopping at the next `fFixedAngle` ancestor.
- `ae_utilities.lua:466` (`GetGlobalBonePRS`): subtract the parent's *departure
  from its own rest angle* — `angle −= (parentWorldAngle − parentRestAngle)`.
- `ae_fixedangle.lua` exists only to flip the flag and then **re-key every
  angle so the pose does not move**, sampling `bone.fAngle` before and after.
  That tool would be pointless if the flag did not change what Moho renders.

**Resolved in Step 1: the first formulation wins**, and the flag is now applied
by default. Measured by rendering `TransformBoneTool.animeproj` with Moho twice
(flag on, flag off) to isolate the effect — see Step 1 for the table.

### 2.3 A cycle formula, and a possible additive-cycle flag → Step 3

`ae_keytools.lua:1245` (`GetCycledValue`) evaluates a cycled channel:

```
absCycle      = interp.val2 > 0 ? interp.val2 : keyTime − interp.val1
period        = keyTime − absCycle + 1
referenceTime = (frame − keyTime) mod period + absCycle − 1
value         = channel(referenceTime)
if interp:IsAdditiveCycle():
    offset = channel(keyTime) − channel(absCycle − 1)
    value += offset × (floor((frame − keyTime − 1) / period) + 1)
```

`ss_cycle_keys.lua` writes such a key: `val1 = cycleFrom − cycleTo − 1`
(relative length), `val2 = −1` (absolute start unused).

Two consequences:

- **`val1`/`val2` are a relative/absolute pair with sentinels.** The corpus
  agrees: `im == 5` entries carry `v1`/`v2` combinations including `-1.0` and
  `-1000000.0` as "unused" markers (1,923 cycle entries across the corpus).
- **Accumulation may be conditional.** `MOHO.InterpSetting` has
  `IsAdditiveCycle()` / `SetAdditiveCycle()`, so "the cycle accumulates its
  per-cycle delta" — which this repository does unconditionally
  (`Channel._cycle_value`, "a walk cycle walks somewhere") — is a flag in
  Moho's own model. **Resolved in Step 3, and the hypothesis was wrong**: `s` is
  `stagger`, the additive bit lives in an unserialised `uint8 flags` member, and
  writing `s: true` into `Bandit.mohoproj` changed nothing in Moho's own render.
  Unconditional accumulation stays correct. Moho's own scripting header, not the
  scripts, is what settled this.

### 2.4 Interp entry field names, decoded by name → Step 10

`MOHO.InterpSetting` exposes exactly six fields plus the additive-cycle pair,
and the JSON interp entry has exactly seven keys. The mapping falls out:

| Lua (`MOHO.InterpSetting`) | JSON key | Meaning |
|---|---|---|
| `interpMode` | `im` | interpolation method enum (already decoded) |
| `val1` | `v1` | cycle: relative length; noisy: amplitude (see below) |
| `val2` | `v2` | cycle: absolute start frame |
| `interval` | `in` | step/noise interval |
| `hold` | `h` | hold frames after the key |
| `tags` | `t` | key label colour (`layer:LabelColor()` is written into it in `FO_Channels.lua:873`) |
| `IsAdditiveCycle()` | `s`? | additive cycle — hypothesis, see § 2.3 |

`sz_recolor_layer.lua` calls `SetKeyInterp(1, MOHO.INTERP_NOISY, arnd, 1/srnd)`
— the two trailing arguments are noise amplitude and scale, i.e. `v1`/`v2`
carry the noise parameters for `INTERP_NOISY`, not only cycle data.

### 2.5 The per-point curve channel layout is 5 sub-channels per (point, curve) → Step 10

`ae_utilities.lua:604-634` and `ae_curvature.lua:188-194` compute a sub-channel
index into the `CHANNEL_CURVE` group:

```
base(point p) = Σ over q < p of  Point(q):CountCurves() × 5
              + 5 per earlier curve running through p
base + 0 → curvature
base + 1 → weight (pre)     base + 2 → weight (post)
base + 3 → offset (pre)     base + 4 → offset (post)
```

This is the same five numbers per point-curve pair that `BezierReconstructor`
reads out of the mesh, seen from the animation side. It also pins down which of
the two weights/offsets is the "pre" one, and confirms a point that belongs to
two curves carries two independent sets.

### 2.6 A complete, version-tagged animated-channel inventory → Step 10

`FO_Channels.lua:543-847` enumerates every channel Moho can animate, with the
release each was added in, and ends with the comment *"MOHO 14.4: Layer
channels appear complete in `pkg_moho.lua_pkg`"*. Highlights this repository
does not currently read:

| Owner | Channels | Corpus |
|---|---|---|
| Bone layer | `wind` = `{direction, strength, turbulence_amplitude, turbulence_frequency}` (13.5) | 51 instances |
| Bone layer | `gravity` = `{direction, strength}` (**Moho 14**) | 51 instances — and a *different* `gravity` = `{x, y}` shape appears 193 times (particle layers) |
| Skeleton group | `active_bone` (13.5, Vitruvian bones) | 1 document, **animated** (2 keys) |
| Curve | `start_percent` / `end_percent` (AS 7.0) | 24 genuinely trimmed curves in `FoxAndGhost.animeproj` |
| Curve | `profile_offset` (Moho 14) | 5,309 instances, all default |
| Point | `opacity`, `color_drift` (Moho 14) | 15,173 instances each, all default |
| Shape | `combo_blend` (Moho 14) | not present in the corpus |
| Layer | the whole shadow / shading / motion-blur / perspective / outline / noise / pixelation / threshold family | mostly documented, not rendered |

### 2.7 Bone dynamics is a sequential integrator, not a per-frame function → Step 9

`mr_bake_bone_dynamics.lua` is a *baker*, and the way it works is the finding:
it cannot compute dynamics at all. It asks the user to hold the right-arrow key
so Moho steps frame by frame, samples `bone.fAngle` / `fPos` / `fScale` at each
frame, and writes the samples back as keys. Two other scripts call
`moho:SetCurFrame(f + 10)` and then `SetCurFrame(f)` with the comment
"Dynamics bug" (`FO_Channels.lua:1045`, `:966`).

So Moho's dynamics state depends on playback history. This is direct support
for what `Skeleton.dynamic_angles` already suspects, and it means a *stateless*
per-frame model (which is what `--bone-dynamics` and `--wind-dynamics` are)
cannot be expected to match. It also identifies the practical reference path:
bake in Moho, export the baked document, diff.

Also worth recording: `bone.fBoneDynamics` is an **animatable Bool channel**
(dynamics on/off over time), while `fAngleDynamics` / `fPosDynamics` /
`fScaleDynamics` are plain booleans selecting which aspects the spring drives.

### 2.8 Masking has two extra switches this repository ignores → Step 5

`LK_MaskSettings.lua` is a mask-settings panel, and it manipulates two fields
beyond the `group_mask` / `masking` pair that `Exporter._mask_plan` already
models:

- `vectorLayer.fExcludeLinesFromMask` — "Exclude strokes": the layer's outlines
  do not contribute to the mask, only its fills. Valid only for the add modes.
  **`true` on 67 layers** in the corpus; read by neither exporter.
- `layer:MaskExpansion()` / `SetMaskExpansion()` — "Expand by a pixel". Valid
  only for `MM_ADD_MASK` / `MM_CLEAR_ADD_MASK`. **`true` on 48 layers**; read
  by neither exporter.

The script also corroborates three things this repository measured
independently: `GROUP_MASK_NONE/SHOW_ALL/HIDE_ALL = 0/1/2`, `MM_NOTMASKED = 1`,
and masking being inert when the parent group's mask is off (it force-resets
children to `MM_NOTMASKED` in that case). It adds one rule: a switch or
particle parent does not mask at all.

### 2.9 The camera, from a working exporter → Step 8

`ss_ae_camera_export.lua` exports the Moho camera to After Effects, which makes
it a second implementation of the projection this repository derived by
measurement:

- Camera translation to pixels: `x = (val.x + 1)·(h/2) + (w−h)/2`,
  `y = (−val.y + 1)·(h/2)`, `z = −val.z·(h/2)` when `AspectRatio() > 0` (the
  `w`/`h` roles swap otherwise). Same "2 Moho units span the canvas height,
  y flipped" convention this repository uses.
- `fCameraRoll` maps to AE's Z rotation; `fCameraPanTilt` is a vector whose
  `x`/`y` are AE's X and Y rotation, in radians. Neither is modelled here
  (`CAMERA` section) — and neither is non-default anywhere in the corpus, so
  this stays documentation.
- **Its zoom model is wrong away from the default**, which is useful: it uses
  `AE zoom = camera_zoom × (h/2)/tan(15°)`, i.e. treats zoom as a linear
  distance multiplier. This repository's measured law is a half vertical FOV of
  `30/camera_zoom` degrees. The two agree **only at `camera_zoom == 2`** (the
  default), which is exactly the kind of coincidence that makes a wrong model
  survive. Cite it as a counter-example, do not adopt it.

### 2.10 Corroborations, and two cautions

Corroborations worth citing in the existing docs (Step 11) — each is a third
party independently arriving at what this repository documents:

| This repository | Script evidence |
|---|---|
| Asymmetric bone scale in `Skeleton.world_matrices` ("NOTE ON SCALE") | `ae_utilities.lua:368-425`: scale is `(s, 1)` for a normal bone and `(s, s)` only when `fLength == 0` |
| Flip must propagate as matrices, not as a scalar angle sum | `ae_utilities.lua:472-476`: four explicit cases combining parent `fFlipH`/`fFlipV` with the child angle |
| Control bones apply the controller's *departure from rest* (`_control_offset`) | `ae_utilities.lua:391-395`: `angle += (ctrl(frame) − ctrl(0)) × fAngleControlScale` |
| Per-point rigid binding via `MeshPoint.parent` (`--point-bones`) | `ae_utilities.lua:664` (`GetPointBoneTransformedPos`) does exactly rest⁻¹ · moved for `point.fParent` |
| Smart bone actions come in pairs, `<bone>` and `<bone> 2` | `ae_utilities.lua:80`, `ae_mix_smartbones.lua:259`, `mr_bake_bone_dynamics.lua:803` all strip/append the `" 2"` suffix |
| Flip detection by comparing the two axis angles (`det < 0`) | `ae_utilities.lua:283` (`Matrix2transform`) |

Two cautions found while reading:

- **A bug in a helper.** `ae_utilities.lua:632` returns `numberBase + 5` for the
  post-handle *offset* channel, which collides with the next point-curve pair's
  curvature (the stride is 5). `numberBase + 4` is what the layout in § 2.5
  implies. Do not mirror it.
- **`GetFadeFactor` is a red herring.** It appears in `mr_utilities.lua` and
  `mr_tween_machine.lua` and looks like a bone-weight falloff, but it is that
  author's own keyframe easing helper. It says nothing about the
  bone-weight-falloff shape that is a real KNOWN GAP here.

---

## 3. Extraction tables (evidence base)

Produced mechanically over all 121 unique files; they are the raw material for
the steps below.

- **API surface**: 1,199 distinct `:Method(` names, 148 distinct `.fField`
  names, 69 distinct `MOHO.*` constants, 34 distinct `CHANNEL_*` channel-group
  ids.
- **Channel-group ids seen**: `CHANNEL_POINT`, `CHANNEL_CURVE`,
  `CHANNEL_CURVEEXP`, `CHANNEL_WIDTH`, `CHANNEL_FILL`, `CHANNEL_LINE`,
  `CHANNEL_SHAPE_ORDER`, `CHANNEL_FXXFORM`, `CHANNEL_BONE`, `CHANNEL_BONE_T`,
  `CHANNEL_BONE_S`, `CHANNEL_BONE_PARENT`, `CHANNEL_BONE_FLIPH`,
  `CHANNEL_BONE_FLIPV`, `CHANNEL_LAYER_T`, `CHANNEL_LAYER_S`,
  `CHANNEL_LAYER_ROT_X/Y/Z`, `CHANNEL_LAYER_FLIP_H/V`, `CHANNEL_LAYER_VIS`,
  `CHANNEL_LAYER_BLUR`, `CHANNEL_LAYER_ALPHA`, `CHANNEL_LAYER_ORDER`,
  `CHANNEL_LAYER_ALL`, `CHANNEL_LAYER_MARKERS`, `CHANNEL_DOC_MARKERS`.
- **Channel type enum** (`FO_Channels:ChannelAsType`): 2 = Vec2, 3 = Color,
  4 = Bool, 5 = String, 6 = Vec3, else Val. Vec2/Vec3 channels can be split per
  dimension (`AreDimensionsSplit()` / `DimensionChannel(i)`), which the JSON
  format also allows.
- **Fields present in the scripts but in neither exporter** (naive
  camel→snake mapping, to be verified against real JSON keys in Step 10):
  `fExcludeLinesFromMask`, `fStartPercent`, `fEndPercent`, `fFixedAngle`,
  `fMinConstraint`, `fMaxConstraint`, `fIKLock`, `fIKGlobalAngle`,
  `fIKParentTarget`, `fIgnoredByIK`, `fActiveBone`, `fProfileOffset`,
  `fColorDrift`, `fComboBlend`, `fWind*`, `fGravity*`, `fShading*`,
  `fShadow*`, `fPerspective*`, `fMotionBlur*`, `fLayerColor`, `fNoise*`,
  `fPixelation`, `fThreshold`, `fAmbientOcclusionRadius`, `fJumpToFrame`,
  `fAudioLevel`.

---

## 4. Work plan

Steps are ordered by expected value, not by dependency; only Step 0 feeds the
others. Every step ends with the repository's normal bar: an export against a
real document plus `make check-reference` where it applies.

### Step 0 — Finish the line-by-line reads
**Status:** not started

Read in full the files that the symbol map (Appendix A) marks as
format-relevant and that were only skimmed, in this order:
`ae_transform_points.lua`, `ae_transform_bone.lua`, `ae_bone_magnet.lua`,
`mr_smartbone_fixer.lua`, `ae_merge_skeletons.lua`, `am_bone_constrains_helper.lua`,
`ae_meshinstance.lua` + `ae_meshinstance_tool.lua`, `ss_virtual_bones.lua`,
`mr_move_targeted_joint.lua`, `mr_track_bone.lua`, `am_create_limb.lua` +
`am_create_limb_2.lua`, `ss_make_bones.lua`, `ae_create_joint_helper.lua`,
`LK_Curvature.lua`, `ae_recolor.lua`, `sz_adjust_line_width.lua`,
`sz_copy_layer_parameters.lua`, `am_paint_bucket.lua`, `ss_eraser.lua`,
`hs_shape.lua`, `mr_path.lua`, `ae_action_tools.lua`, `mr_utilities.lua`,
`FO_Utilities.lua`, `mr_animate_points.lua`, `mr_overlay.lua`,
`mr_tween_machine.lua`, `mr_key_motion.lua`, `ss_multi_layer_transform_points.lua`,
`lm_transform_layer_modified.lua`, `lm_bind_points_ae.lua`.

**Output:** append any new finding to § 2, and add rows to the "not in either
exporter" list in § 3. **Skip** the pure data blobs (`hv_font.lua`,
`HS_CardSuits.lua`) and the GUI-only hotkey stubs (`sz_layer_hotkey_*.lua`,
`LK_Dummy.lua`) beyond a glance.

### Step 1 — Settle `fixed_angle` (highest value)
**Status:** ✅ **done — decoded, implemented, applied by default.**
`RenderSettings.fixed_angle_mode = "rest"`.

`IndependentAngle.animeproj` is no longer in `moho/`, so the reference was built
from `TransformBoneTool.animeproj` instead (4 flagged bones, one under a chain
that swings 145°, pure vector, and every layer is its own `<g id>` in Moho's SVG
export). New gitignored reference set: `moho/track/TransformBoneTool/svg/`,
120 frames.

**The measurement that settled it.** Rather than compare our render against
Moho's and hope the flag dominates, Moho rendered the document **twice** — as
authored and with every `fixed_angle` forced `false`. The difference between
those two renders is the flag's effect measured *by Moho*, with every unrelated
modelling error cancelled. Only the two leg layers move; arms, body and head
differ by exactly 0.00 px, which is the check that the experiment isolates what
it claims.

| layer | Moho's own effect, mean / max px | error `off` | error `rest` | error `absolute` |
|---|---|---|---|---|
| LegL | 7.17 / 15.46 | 7.17 / 15.46 | **4.93 / 8.17** | 6.62 / 12.03 |
| LegR | 5.82 / 16.17 | 5.82 / 16.17 | **3.43 / 7.16** | 4.32 / 8.15 |
| overall | — | 2.17 / 16.17 | **1.39 / 8.17** | 1.82 / 12.03 |

- `rest` = subtract the parent's **departure from its own rest rotation**
  (§ 2.2's `GetGlobalBonePRS` reading) — wins on every layer and both statistics.
- `absolute` = subtract the parent's whole world angle (§ 2.2's `GetBoneMatrix`
  reading) — better than ignoring the flag, clearly worse than `rest`.
- Ignoring it costs up to **16 px** on a 1280×720 canvas.

**Residual, not tuned away:** `rest` recovers about a third of the effect. Either
this document's own baseline skinning error (≈2× the effect size on those layers,
so the delta comparison is contaminated at second order) or an incompleteness for
**nested** flagged bones (`B11`/`B12`, `B15`/`B16` — a flagged bone whose parent
is also flagged). Recorded with a reproduction recipe.

**Verification:** `make check-reference` unchanged (Bandit's `Tail` moves
0.01–0.09 px, every other number identical). `tools/check_lottie_geometry.py`
agrees before and after when both sides use the same settings.

**Knock-on, worth recording:** this step's geometry change flipped one of
Bandit's `Leg_F 2` intersect shapes from the masksProperties fallback onto the
`pyclipper` pre-clip path, which **exposed three pre-existing defects in the
Lottie writer** — an even-odd clip region cancelling two overlapping base
members, a stroke band's two loops both unioned into a mask, and a vertex
correspondence anchored to the loop's topmost point (so a rotating intersect
shape appeared to spin in a player). None was caused here, none affected the SVG
writer, and `make check-lottie` could not see any of them because both sides of
that check share the same code. All three are fixed — see
`docs/moho-to-lottie-plan.md`'s "Two fill-rule defects found later in this same
machinery" and the section following it. A fourth, unrelated latent bug turned up
in the same probing: `Channel._cycle_value` recursed forever on a FRACTIONAL
frame inside a cycle (unreachable from either exporter, now guarded).

**Delivered:** `Bone.fixed_angle`, `RenderSettings.fixed_angle_mode`,
`Skeleton._solve` / `_rest_orient_angles` (the frame-0 rest solve),
`Skeleton._world_matrices`' NOTE ON INDEPENDENT ANGLE,
`docs/moho-rigging-and-deformation.md` § 3.2 (rewritten, with the table) and its
open-risk list, and `docs/moho-project-file-format.md`'s "not used" list.

### Step 2 — Test the closed-form Bezier handle formula
**Status:** ✅ **done — no code change needed.** The formula was already tested
and rejected; what was missing was its provenance and a corpus-wide number.

What the measurement found (255,568 handles, all 23 documents, frames 0 and 12):

- **The Lua closed form is exactly this repository's formula at
  `tangent_bias = -1`.** At that bias the two blend weights become equal and the
  blend collapses to `normalize(next − prev)`. Verified numerically: 0
  mismatches over every closed curve in `Bandit.mohoproj`.
- The module docstring's BEZIER CURVES § already rejected
  `normalize(next − prev)` — it is the "public Moho scripting snippet" it names,
  measured at a median 3.4° error against 209 handles in Moho's **own** SVG
  export, versus 0.02° for the fitted `BIAS = 0.19`. That reference beats
  anything a corpus-only comparison could say, so the fitted value stands.
- Switching to the Lua form would move the median handle by **1.10°**, the mean
  by 7.23°, p90 by 23.0°, and would move **51.3%** of all handles by more than
  1°. On `Bandit.mohoproj` alone the median is **3.40°**, independently
  reproducing the docstring's "3.4 degrees".
- Kept as corroboration: the snippet computes the handle *length* exactly as
  this repository does (`distance × curvature × weight`), from an author with
  Moho's own API in hand.

**Delivered:** the docstring's BEZIER CURVES § now names the snippet, records
the `BIAS = -1` equivalence and carries the corpus numbers. Measurement script:
session scratchpad (`handle_compare.py`) — not promoted to `tools/`, since it
answers a settled question rather than guarding a regression.

### Step 3 — Re-check cycle evaluation and hunt the additive flag
**Status:** ✅ **done — no code change needed; `s` decoded.** No user-made test
document was required after all: the flag could be written into the JSON and
rendered by Moho headlessly, and Moho's own scripting header settled the rest.

1. **`s` is `stagger`.** `pkg_moho.lua_pkg` declares `InterpSetting`'s members
   in exactly the order the JSON writes them — `interpMode, val1, val2,
   interval, hold, stagger, tags` → `im, v1, v2, in, h, s, t` — followed by a
   `uint8 flags` member that **no interp entry serialises**. The additive-cycle
   bit that `IsAdditiveCycle()` / `SetAdditiveCycle()` read lives in `flags`, so
   a file reader never sees it, and unconditional accumulation is correct.
   Verified: all **948,873** interp entries in the corpus carry exactly those
   seven keys, plus `b` on the 257 `INTERP_BEZIER` ones, and nothing else.
2. **Tested rather than assumed.** Setting `s: true` on all 142 cycle markers in
   `Bandit.mohoproj` and re-rendering frame 80 with Moho itself changed **0 of
   518,400 pixels**; the control (`v1` 15 → 8) changed **9.34%** and moved the
   centroid ~10 px. The experiment was sensitive, so `s` really is inert here.
3. **The formula agrees, with one exception that is the script's bug.** Period,
   repeat count and delta base are all identical to `_cycle_value` — genuine
   third-party corroboration of what `_parse_cycles` calls an inference. The one
   difference: the script maps frames where `(frame − end) mod period == 0` back
   to `resume − 1` instead of `end`, landing one delta short. Measured on
   Bandit: that would drop frames 57/73/89 back by **383.5 px** for a single
   frame, while Moho's own exported frames 55–59 march 497 → 535 → 557 → 574 →
   602 px with no dip.
4. **Bonus decode.** The `b` block on `im == 9` entries is one dict per
   component, `{"ao", "ai", "po", "pi"}` = `BezierOutAngle`, `BezierInAngle`,
   `BezierOutPercentage`, `BezierInPercentage`, from the same header. Key names
   are solid; the units are not yet measured.

**Delivered:** `Channel._cycle_value`'s docstring and
`docs/moho-animation-and-transform.md` § 3.4 (a full interp-field table) and
§ 3.6 (the `b` block). This also covers most of Step 10's item 1.

### Step 4 — Smart-bone pose-curve inversion details
**Status:** ✅ **done — three details matched, one real gap found and recorded**
(no code change: the gap is unverifiable on this corpus).

| Detail | Script | This repository | Verdict |
|---|---|---|---|
| Sub-frame interpolation | samples every integer frame, then interpolates **linearly** inside that 1-frame span; callers mostly snap back to the integer | bisects the true monotone cubic between keyframes | repo better, with render evidence already on file (ears IoU 91.7% → 52.8% when treated as linear) |
| Scan starts at frame **2** when the action is longer than 1 frame | skips the `[0, 1]` span | handles it via the `abs(b − a) < 1e-12` branch | equivalent — and the *reason* is now clear: actions are commonly keyed at **both** 0 and 1 with the same value (`Rabbit.animeproj`'s `HeadTilt` pose is keyed `[0, 1, 51, 101]`), which makes the sub-frame ambiguous |
| No-crossing fallback | compares only the last two samples, snaps to the nearer | clamps the target into the channel's value range first, plus an explicit nearest-keyframe fallback | equivalent, applied to both ends |
| Angle used for the lookup | the **resolved** `bone.fAngle` ("bad for nested smartbones") | the dial's own **keyed** angle (`eval_raw`) | **genuine gap — recorded, not fixed** |

On the last row, measured: **108 dial bones** in the corpus, none driven by
another dial's action, exactly **two** driven by a control bone (`HeadTilt` in
`Rabbit.animeproj` and `BoneDynamics.animeproj`, scale 1.0, delay 0). In both,
the controller never leaves its rest angle, so the offset is `0.0` at every
frame and the selected pose frame is identical either way (frames 0–60 checked).
A fix cannot be verified here, and feeding a resolved angle back into the
machinery that resolves it needs cycle protection — so it is documented with the
reproduction instead.

**Delivered:** `Channel.frame_for_value`'s docstring (the three matched
details), `Exporter._active_smart_bones`' docstring and
`docs/moho-rigging-and-deformation.md` § 4 (the gap, with numbers and a
confidence marker).

### Step 5 — Mask extras: `exclude_lines_from_mask` and `mask_expansion`
**Status:** ✅ **done — one applied, one deliberately not**, both decoded and
measured against Moho's own render. The manual settled both meanings in one
sentence each (ch. 12.05), which is why this step did not need guessing.

**`mask_expansion` — applied.** *"Adds an additional pixel around a layer
mask."* `true` on 48 layers. SVG: a 2 px white stroke along the contributing
op's own path inside the `<mask>`, painted after the fills and before the
existing black carve strokes. Lottie: the mask entry's own **native `x`
("Expand")** property set to 1 — no approximation needed, the format has this
exact feature (30 of SketchBone's 85 mask entries now carry it, schema
validation passes).

Verified by the two-pole method: Moho rendered `SketchBone.mohoproj` twice, flag
on and forced off, which moves **650 px** at frame 1. Our own change moves 329 px
in the same bounding box, a **median of 0 px** (p90 1 px) from Moho's nearest
changed pixel. Half the count, right edges — the rest is anti-aliasing, which the
two renderers do differently regardless.

**`exclude_lines_from_mask` — decoded, deliberately not applied.** *"Check this
option to exclude outlines from the mask."* `true` on 67 layers. The obvious
wiring is wrong, and this is the useful finding: this exporter **already** carves
a band along a mask source's outline out of the mask, but that models a
*different* Moho behaviour ("the source's own stroke stays visible on top of what
it masks", confirmed long ago against the Moho app on Bandit's
BellyTexture/Head_DarkBlue pair). Gating that carve-out on this flag was tried
and reverted:

| | Moho's own effect | our gated version |
|---|---|---|
| pixels changed | 336 | 2,412 |
| region | y 309–421 | y 225–590 |
| overlap | — | **0 px** |

(`Spacewoman.mohoproj` frame 27.) Excluding outlines leaves the inner half of the
stroke band *inside* the mask; carving the band removes it. Doing it properly
needs the mask to be `fill ∪ stroke band` when the flag is false — a redesign of
the mask model, not a conditional. Effect sizes if it is ever worth it: 26–56 px
per frame on plain outlines (`OffsetBoneTool`, `WhatIsBone`, `Spacewoman`, 48
frames each), and 2,191 px on the one SketchBone frame where the flagged outlines
are **brush** strokes — which this exporter excludes from mask exclusion anyway,
putting the larger case doubly out of reach.

**Verification:** `make check-lottie` and `make check-reference` both pass; 7
masking-heavy documents export cleanly.

**Delivered:** `Layer.mask_expansion` and `Layer.exclude_lines_from_mask` (the
latter documenting why it is unused), the per-op `expand` flag through
`_mask_plan`/`_mask_element` and `_mask_sources_bezier`/`_finalize_mask`,
`_mask_entries(expand=...)`, and
`docs/moho-project-file-format.md` § 10.5 (new), which also corrects two stale
"not used / false throughout" claims.

### Step 6 — Stroke exposure (`start_percent` / `end_percent`)
**Status:** ✅ **done — implemented for a plain stroke, warned elsewhere.**

The corpus turned out unable to verify this, so a probe was built instead:

- **`FoxAndGhost.animeproj`'s 24 trimmed curves are never drawn.** All 24 are
  the same case (`end_percent = 0.9721` on a 2-point `Lazer Beam` /
  `Light Blade` / `Glow` curve), and re-rendering the document with Moho with
  those values forced back to untrimmed changes **0 pixels** at 8 frames
  sampled across its 450-frame range. Our own output on that document is
  byte-identical before and after this step.
- **So a probe was authored**: `TransformBoneTool.animeproj`'s `Body` curve (5
  points, closed, both a fill and an outline) with `end_percent` forced to 0.5
  and 0.75, rendered by Moho. Two things fell out of it, neither guessable:
  Moho trims the **outline only** and leaves the fill whole, and the fraction
  is of **arc length**, not segment-parameter space.
- Both parameterisations were implemented and scored by changed-pixel IoU
  against those renders: arc length **0.739 / 0.723** (at 50% / 75%) versus
  segment-parameter 0.648 / 0.683. Our trimmed region sits a **median of 0 px**
  from Moho's, with 84% / 79% of Moho's changed pixels covered.
- **Sentinel confirmed** from `ss_curve_exposure.lua` and the data: outside
  `[0, 1]` means untrimmed (`-0.01`/`1.01` from Moho's own tool, `-0.1`/`1.1`
  in these files).
- **Brush-textured and tapered outlines warn instead.** They are built as a
  stamped dab run or a filled band, not a strokeable path, so trimming them
  needs the trim pushed into those builders. Moho does trim them — the probe's
  own outline is brush-styled — so this is the next thing to do if a real
  document depends on it.

**Verification:** `make check-reference` and `make check-lottie` pass; the only
corpus document with trimmed curves exports byte-identically.

**Delivered:** `split_cubic`, `CurveGeometry.segment_lengths` /
`trim_ranges`, `trimmed_segment`, `Exporter._stroke_trims`,
`Curve.start_percent` / `end_percent`, the `trims=` parameter on
`build_path_d` / `build_path_bezier` (SVG and Lottie outlines),
`ShapeGroupRenderer._warn_untrimmed_outline`, plus
`docs/moho-rigging-and-deformation.md` § 6.3 (rewritten) and the format doc's
own curve-field row.

### Step 7 — Vitruvian bones: `active_bone`
**Status:** ⚠️ **partly done — storage and selector decoded, effect not; no code
change.** The obvious implementation was written, measured against Moho, and
**rejected**. It stays detected-and-warned, which is what
`docs/moho-rigging-and-deformation.md` § 4b already asked for.

**Decoded, and confirmed rather than inferred.** `Night_Boy.mohoproj` carries one
group: `{type: "BoneGroup", enabled: true, name: "Group 5", bones: [101, 102,
103], active_bone: <Val channel keyed [0,1] -> [2.0, 0.0]>}`. `bones` are bone
indices in that skeleton (`B136`/`B137`/`B138`, three bones sharing parent 51 at
rest angles 90°/124.6°/41.8° — one limb, three poses), and `active_bone` is an
animated channel. Confirmed by **authoring such a group by hand** into
`TransformBoneTool.animeproj`: Moho honours it (2,862 px change), so the key
names and shapes are right.

`active_bone` is **0-based into the group's own list**, out-of-range falling back
to the first member — measured on a 2-member probe against a no-group baseline:
0 → 22 px (identical), **1 → 2,840 px**, 2 → 22 px, 3 → 22 px.

**Why no code change.** The natural model — only the active member deforms, its
siblings inert (strength 0) — contradicts Moho:

| | Moho | that model |
|---|---|---|
| first member active, vs no-group baseline | 22 px | **568 px** |
| second member active, overlap with Moho's changed pixels | — | **33%** (median 3.6 px, p90 36 px) |

Freezing an inactive member at rest does not fit either: both probe bones are
animated through frame 25, so it would predict a change in both directions while
Moho shows one. `Night_Boy.mohoproj` cannot arbitrate — its PSD asset is not in
`moho/`, so our own render of it is empty.

**Delivered:** the decode and both rejected models recorded in
`Skeleton`'s own comment block and in
`docs/moho-rigging-and-deformation.md` § 4b.1 (new), plus corrections to § 4b's
"empty in every sample" claim, its "to document it properly" to-do, and the
format doc's `bones_groups` line. Verified the revert leaves our render of a
Vitruvian document byte-identical to before.

**To finish it:** a rig whose limb visibly switches between members, exported
with Moho. The hand-authored probe recipe above is the cheap way to make one.

### Step 8 — Camera: document `camera_roll` / `camera_pan_tilt`
**Status:** not started · **Evidence:** § 2.9 · **Corpus:** never non-default

Documentation only, plus one caution. Add to
`docs/moho-animation-and-transform.md` § 9: the pixel mapping from
`ss_ae_camera_export.lua`, the meaning of `camera_pan_tilt.x/y` (X and Y
rotation, radians) and `camera_roll` (Z rotation), and the note that a
third-party exporter models zoom linearly and therefore agrees with this
repository's measured `30/camera_zoom` law only at the default zoom of 2.

### Step 9 — Bone/wind dynamics: record what the baker proves
**Status:** not started · **Evidence:** § 2.7

No code change. Add to `Skeleton.dynamic_angles`' docstring and
`docs/moho-rigging-and-deformation.md`: Moho's dynamics is a sequential
integrator (a third-party baker can only *sample* it while stepping frames, and
two scripts work around a stateful "dynamics bug"), so a stateless per-frame
spring is not expected to match; and the practical reference path is to bake in
Moho and diff the baked document. Also record that `bone_dynamics` is an
animatable Bool while the three `*_dynamics` flags are static.

### Step 10 — Documentation harvest
**Status:** not started · **Evidence:** § 2.4, § 2.5, § 2.6, § 3

Fold the mechanical findings into the reference docs:

1. `docs/moho-project-file-format.md`: the interp-entry field table
   (`im/v1/v2/in/h/s/t` ↔ `InterpSetting`), including `v1`/`v2` doubling as
   noise amplitude/scale for `INTERP_NOISY`; the `CHANNEL_*` channel-group id
   list; the Moho 14 `wind` and `gravity` object shapes (and the fact that
   `gravity` has a second, unrelated `{x, y}` shape); `active_bone`.
2. `docs/moho-animation-and-transform.md`: the version-tagged channel
   inventory from § 2.6, as a "what can be animated" table.
3. The module docstring: the § 2.5 sub-channel layout, next to the Bezier
   reconstruction section.
4. Verify each JSON key name against the corpus before writing it down — the
   camel→snake mapping in § 3 is a guess, not evidence (`fUUID`, `fIKLock` and
   friends will not map naively).

### Step 11 — Cite the corroborations
**Status:** not started · **Evidence:** § 2.10

Add a one-line "independently corroborated by third-party Moho scripts" note
(with file and line) to the five places in § 2.10 where a script reaches the
same conclusion this repository measured. These are the places most at risk of
being "fixed" by a future reader; a second witness is cheap insurance.

### Step 12 — Optional: an API-surface reference
**Status:** not started

If the extraction tables prove useful more than once, promote them into a small
`docs/moho-scripting-api.md`: the method/field/constant inventory with the
file:line where each is used, as a lookup table for future format questions.
Only worth doing if a later step actually needs it twice.

---

### Step 13 — Close the blind spot `make check-lottie` has
**Status:** ✅ **done.** Both tools built, wired and validated; the check found a
fourth defect on its first run (below).

Not from the scripts — from this session. Four Lottie defects surfaced while
working through Steps 1–7, and `make check-lottie` was blind to every one of
them, because it compares the writer against **the same pipeline that fed the
writer**. Anything wrong in a decision both sides share is invisible to it: the
clip region's fill rule, a mask band's loop ordering, the vertex ordering of a
resampled loop. Each took a hand-built probe to find and another to prove fixed.

Two of the three probes that worked are worth keeping. The third is not, and that
distinction matters more than the tools:

| Probe | Keep? | Why |
|---|---|---|
| **Frame-to-frame vertex slip** — for each animated `sh`, the cyclic shift that best aligns consecutive keyframes | **yes** | Found the "spinning shape" class outright (55/64 → 4/64). Needs only the emitted file, no player, no reference render. A pass/fail guard. |
| **Visible region** — per layer, `own geometry ∩ accumulated mask`, by polygon algebra | **yes** | Settled the `Eye_Upper`/`Eye_Back` report in one run (0.04–0.09% change, i.e. untouched). A *comparison* tool between two files, not a CI assertion. |
| **Player simulator** (`lottie_sim.py`) — replay layers/masks as SVG and rasterise | **no** | Not faithful enough: it showed an ankle ellipse that a real player never showed, which sent one whole investigation down the wrong path. Keeping it would keep inviting that mistake. |

Delivered:

1. **`tools/check_lottie_stability.py`**, now part of `make check-lottie`. Two
   assertions per animated `sh`: keyframes agree on vertex count and closedness,
   and consecutive keyframes stay in vertex *correspondence*.
   The metric took two attempts, and the rejected one is worth recording:
   - **Raw cyclic slip** discriminates well but means different things on
     different shapes — 10 vertices of slip rotates a round fill visibly while
     merely sliding points along a thin band.
   - **Second differences** (is keyframe k+1 near the midpoint of k and k+2?)
     was tried and **rejected**: it is dominated by genuine acceleration. A
     whisker moving sharply scores 111% of its own size, and the buggy build
     scored 6.55% median against the fixed build's 5.96% — no discrimination.
   - **Realignment gain**, the one kept: centre both keyframes on their own
     centroid, find the best cyclic shift, and report how much the rms vertex
     distance *improves* at that shift, as a percentage of the shape's own
     diagonal. A shape in correspondence gains nothing; a slipped ring gains
     exactly the distance it is out of correspondence. It separates the fill and
     band cases by itself, and shape compactness (`area/perimeter²`) is used to
     fence them apart: 20% for blobs, 35% for thin bands.

   Validated both ways: the pre-fix build **fails on 54 keyframe pairs**, naming
   `Leg_F#1`, `Leg_F 2#1`, `Arm_F#1`, `Arm_B#1` — the exact layers reported as
   "spinning" — while the fixed build passes at 9.2% (blob) and 28.0% (thin).
   Runtime ~2.7 s for all three sample documents, 32,000 keyframe pairs.

2. **`tools/diff_lottie_visible.py`** — per-layer visible region (own geometry ∩
   accumulated mask) between two Lottie files, by polygon algebra. It reproduces
   the whole `Eye_Upper`/`Eye_Back` investigation in **1.6 s**: worst visible
   difference 0.09%, i.e. untouched. The rasterising simulator that first
   suggested a problem there was deliberately **not** promoted — see the table
   above.

3. A `CLAUDE.md` note stating plainly what `check-lottie` can and cannot see,
   and which tool to reach for instead.

**A fourth defect, found by the new check on its first run.** Pre-clipped
outline **bands** slip up to 31 of 64 vertices frame to frame (28% realignment
gain on `Eye_Back#1` at frames 44 and 49). It is real but nearly invisible —
sliding samples along a thin uniform band barely changes its outline, which is
why no one reported it — and neither anchoring rule fixes it (nearest-point 31,
rotating-frame extremum 29), because it is a *distribution* problem: a clipped
band's arc-length resample slides whenever the clip cuts it in a different
place. Fixing it properly means building the band from a clipped **centreline**
instead of polygon-clipping the band. Fenced at 35% and recorded, not silently
tolerated.

---

## Appendix A — the 121 unique files

Sorted by size. **Topics** is a mechanical tag of which format areas each file
touches: `curve` (curvature/weights/handles), `bone`, `smart` (smart-bone
actions), `chan` (keys/interpolation), `style`, `mask`, `layer`, `camera`,
`shape` (creation/boolean/order), `warp`.

| File | Lines | Purpose (from the script's own `Name()`/`UILabel()`) | Topics |
|---|---|---|---|
| `mr_animate_points.lua` | 11071 | MR Animate Points | curve,chan,layer,warp |
| `mr_overlay.lua` | 7122 | MR Overlay | curve,bone,smart,style,mask,layer,shape |
| `hs_shape.lua` | 6402 | Draw shapes and curves | curve,style,shape |
| `mr_tween_machine.lua` | 5145 | MR Tween Machine | curve,bone,chan,layer,camera,warp |
| `mr_path.lua` | 2818 | MR Path | curve,bone,style,layer,shape |
| `FO_Utilities.lua` | 2423 |  | bone,smart,chan,layer,camera |
| `ss_multi_layer_transform_points.lua` | 2258 | Multi-Layer Transform Points | curve,style,layer,shape |
| `mr_key_motion.lua` | 1941 | Key Motion 1.1 | curve,bone,chan,layer,camera |
| `ae_transform_bone.lua` | 1852 | Transform Bone | bone,smart,chan,layer |
| `ae_transform_points.lua` | 1848 | Transform Points | curve,smart,style,layer,shape |
| `LK_SelectPoints.lua` | 1654 | Select Points | curve,style,layer,shape |
| `lm_transform_layer_modified.lua` | 1578 | Transform Layer | chan,layer,camera |
| `sz_layer_copies.lua` | 1440 |  | layer |
| `ae_keytools.lua` | 1434 |  | chan,layer,camera |
| `mr_utilities.lua` | 1287 |  | curve,smart,chan,mask,layer |
| `am_create_limb_2.lua` | 1263 | Create Limb 2 | curve,bone,style,layer,shape |
| `ss_eraser.lua` | 1244 | Eraser | style,layer,shape |
| `FO_Channels.lua` | 1071 |  | curve,bone,smart,chan,style,layer,camera,shape |
| `LK_ColorBones.lua` | 1061 | Toggle Color Bones | smart,layer |
| `mr_smartbone_fixer.lua` | 1008 | Smart Bone Fixer | bone,smart,chan |
| `LK_Curvature.lua` | 974 | Curvature + | curve,layer |
| `mr_bake_bone_dynamics.lua` | 865 | Bake Bone Dynamics | bone,smart,chan,layer |
| `DV_TweenMachine.lua` | 844 |  | chan,layer |
| `mr_track_bone.lua` | 842 | Track Bone | bone,chan,layer |
| `hv_font.lua` | 842 |  | - |
| `sz_recolor_layer.lua` | 831 |  | chan,style |
| `HS_CardSuits.lua` | 815 | Card Suits | curve,style |
| `ae_lipsync.lua` | 810 | Lipsync tool | curve,smart,chan,layer |
| `ae_select_shape.lua` | 806 | Select Shape | style,layer,shape |
| `mr_continue_animation.lua` | 793 | Continue Animation 1.1 | curve,bone,chan,layer |
| `sz_bone_selection_buttons.lua` | 784 |  | bone,layer |
| `ae_utilities.lua` | 756 |  | curve,bone,smart,layer,camera |
| `LK_Render.lua` | 743 | Render Current Shot | - |
| `LK_NudgeKeys.lua` | 739 | Nudge Keys Toolset | chan,layer |
| `am_bone_constrains_helper.lua` | 734 | Bone Constraints Helper | bone,layer |
| `am_create_limb.lua` | 711 | Create Limb | curve,bone,style,layer,shape |
| `ae_curvature.lua` | 696 | Curvature | curve,smart,layer |
| `ae_hands_table.lua` | 686 | Hands table | layer,shape |
| `ss_virtual_bones.lua` | 658 | Virtual Bones | curve,bone,style,shape |
| `ae_merge_skeletons.lua` | 634 | Merge Skeletons | bone,smart,chan,layer |
| `am_paint_bucket.lua` | 626 | Paint Bucket + | curve,style,layer,shape |
| `mr_move_targeted_joint.lua` | 607 | Move Targeted Joint | bone |
| `ae_meshinstance_tool.lua` | 563 | Meshinstance Tool | curve,smart,chan |
| `ae_bone_magnet.lua` | 558 | Bone Magnet | bone,layer |
| `LK_TimelineNavigator.lua` | 524 | Timeline Navigator | chan |
| `sz_mark_points.lua` | 495 | Mark Points | curve,style,mask,shape |
| `ae_magnet.lua` | 491 | Magnet | layer |
| `ae_action_tools.lua` | 485 | AE Action Tools | curve,bone,smart,style,shape |
| `LK_ToggleColorBones.lua` | 476 | Toggle Color Bones | smart |
| `ss_make_bones.lua` | 456 | Make Bones | bone |
| `sz_timeline_markers_tool.lua` | 453 | Timeline Markers Tool | chan |
| `sz_copy_layer_parameters.lua` | 441 |  | layer |
| `ae_meshinstance.lua` | 432 |  | curve,bone,smart |
| `LK_MaskSettings.lua` | 380 | Quickly set up masks | mask |
| `LK_Tagger.lua` | 351 | Layer tagger | - |
| `ae_recolor.lua` | 345 | Recolor | style,layer |
| `sz_layer_selection_buttons.lua` | 331 |  | - |
| `ae_reset_layer_transform.lua` | 328 | Reset Layer Transform | curve,bone,smart,layer,camera |
| `LK_Set_Origin.lua` | 328 | Set Origin | layer |
| `sz_select_bones_by_name.lua` | 320 |  | - |
| `LK_LayerFinder.lua` | 313 | Layer Finder | - |
| `ss_curve_exposure.lua` | 303 | Stroke Exposure | curve,style,shape |
| `sz_adjust_line_width.lua` | 302 |  | style |
| `msLipSync.lua` | 286 | Lip Sync | bone,layer |
| `ae_mix_smartbones.lua` | 278 | Smartbone Correction | bone,smart,chan,layer |
| `msPhonemes.lua` | 274 |  | - |
| `LK_EmbedScript.lua` | 270 | Embed script | - |
| `lm_bind_points_ae.lua` | 258 | Bind Points | bone,layer |
| `ae_seamless_rotation_smart_maker.lua` | 249 | Seamlessly rotating smartbone on/off | bone,smart,chan |
| `HS_LuaCompatibility.lua` | 245 |  | - |
| `msDialog.lua` | 236 | msDialog | - |
| `ss_cycle_keys.lua` | 223 | Cycle Keyframes | chan |
| `LK_Storyboard.lua` | 222 | Storyboard Slider | - |
| `LK_LayerOpacity.lua` | 219 | LK_LayerOpacity | chan,layer |
| `sz_move_selected_to_coord.lua` | 218 |  | - |
| `ss_number_sequence.lua` | 214 | Number Sequence+ | - |
| `HS_Mosaic.lua` | 186 | Mosaic | - |
| `LK_DeleteOffLayers.lua` | 175 | Delete 'OFF' Layers | - |
| `ss_ae_camera_export.lua` | 165 | SS/DS Camera to AE+ | camera |
| `sz_add_keyframe.lua` | 165 | SZ_AddKeyframe | curve,bone,chan,style,layer |
| `ae_fixedangle.lua` | 157 | Independent angle on/off | bone,smart |
| `sz_add_keyframe_settings.lua` | 150 | SZ_AddKeyframe_Settings | - |
| `msReassignStyles.lua` | 138 | Reassign styles ... | style |
| `sz_rename_smart_bone.lua` | 138 |  | - |
| `ae_smart_granchildren.lua` | 138 | Apply smart to grandchildren | bone,smart,chan |
| `am_merge_vectors.lua` | 130 | Merge Vector Layers | - |
| `ae_place_layer_in_group.lua` | 130 | Place layer in/out group | layer |
| `DV_Backup.lua` | 127 | BackUp File | - |
| `sz_hide_points.lua` | 117 |  | - |
| `ae_walkcycle.lua` | 116 | Walk Cycle | bone,chan,layer |
| `LK_SelectedKeysToZero.lua` | 106 | Move selected keys to frame 0 | chan |
| `msRenameStyles.lua` | 99 | Renames all styles ... | - |
| `sz_swap_view_mode.lua` | 98 | Swap View Mode | - |
| `ae_create_joint_helper.lua` | 96 | Create Joint Helper | bone |
| `LK_LayerVisibility.lua` | 93 | Toggle Layer Visibility | chan,layer |
| `am_select_bonelayer.lua` | 92 | Select Bonelayer | - |
| `ae_reset_layer_origin.lua` | 90 | Reset Layer Origin | layer |
| `LK_CutToNewLayer.lua` | 86 | Cut to new Layer | - |
| `sz_current_frame_to_png.lua` | 85 | Current Frame to PNG | - |
| `sz_layer_copies_run.lua` | 84 |  | - |
| `ae_invert_layer_transform.lua` | 83 | Invert layer transform | layer,camera |
| `sz_collapse_all_groups.lua` | 83 | Collapse All Groups | - |
| `sz_layer_inspector.lua` | 82 | Layer Inspector | layer |
| `sz_point_inspector.lua` | 80 | Point Inspector | - |
| `sz_bone_inspector.lua` | 79 | Bone Inspector | bone |
| `mr_create_overlay.lua` | 78 | MR Create Overlay | - |
| `LK_Origin_Bone.lua` | 73 |  | - |
| `LK_ToggleKeysFilter.lua` | 71 | Toggle 'keys' filter | - |
| `LK_HideShowShyPoints.lua` | 69 | Hide/Show Shy Points | - |
| `LK_Origin_Switch.lua` | 69 |  | - |
| `mr_create_path.lua` | 68 | MR Create Path 1.0 | - |
| `sz_layer_hotkey_8.lua` | 55 | Layer Hotkey 8 | - |
| `sz_layer_hotkey_7.lua` | 55 | Layer Hotkey 7 | - |
| `sz_layer_hotkey_1.lua` | 55 | Layer Hotkey 1 | - |
| `sz_layer_hotkey_6.lua` | 55 | Layer Hotkey 6 | - |
| `sz_layer_hotkey_2.lua` | 55 | Layer Hotkey 2 | - |
| `sz_layer_hotkey_3.lua` | 55 | Layer Hotkey 3 | - |
| `sz_layer_hotkey_5.lua` | 55 | Layer Hotkey 5 | - |
| `sz_layer_hotkey_4.lua` | 55 | Layer Hotkey 4 | - |
| `msHelper.lua` | 23 |  | - |
| `LK_Dummy.lua` | 3 |  | - |

---

_Reading method, extraction scripts and raw notes for this pass live in the
session scratchpad; the tables above are their distilled form._
