---
name: moho-relationship-trace
description: A 4-level investigation checklist for "why does this bone/layer/point move (or look) wrong" questions in this repo — self, parent, siblings/peers, then shared/global config. Use it BEFORE proposing a fix for any motion, position, or rendering discrepancy involving a bone, layer, or mesh point, especially when the first hypothesis (the object's own animation channel) doesn't fully explain what's observed. Distilled from the DarkMan.mohoproj `hat -> right_part`/`left_part` investigation, where the real cause (per-point bone binding being ignored) was only found by checking sibling/peer and config-level information, not the bone's own channels.
allowed-tools: Read, Bash
user-invocable: true
argument-hint: "<bone/layer/point name> in <file>, plus what looks wrong"
---

# moho-relationship-trace — trace relationships before proposing a fix

## Why this exists

On `DarkMan.mohoproj`, a bone (`right_part`'s `B1`) appeared to move far more
than its own keyframed angle should produce. The first hypothesis - a
missing physics/damping simulation (`wind_dynamics`) - was plausible,
carefully evidenced, and **wrong**: implementing it and testing against the
concrete symptom showed it made things the same or worse (see
`moho2svg.py`'s `Skeleton.dynamic_angles` WIND EVIDENCE section for the full
negative result). The real cause was found only by asking a different kind
of question: not "what drives this bone's own angle" but "what ELSE
references this bone, and what does the mesh actually bind to" -
`MeshPoint.parent` (a per-point rigid bone binding) existed on the affected
meshes and was being silently ignored by the default region-blend path.

**The lesson worth keeping**: an object's own animation channel is only one
of several places a discrepancy can hide. Before committing to a fix, walk
outward through four levels, in order, and don't stop at the first
plausible-looking cause - the DarkMan case had a plausible cause at level 0
(the bone's own `wind_dynamics`/`bone_dynamics` flags) and the real cause at
level 2 (a peer mesh's own `MeshPoint.parent` binding data, which is level 0
FOR THAT MESH but only surfaces as "check what else references this bone"
- i.e. level 2 - from the bone's own point of view).

## The four levels

Apply this whenever investigating why a bone, layer, or mesh point moves,
sits, or renders unexpectedly. Skip a level only after actually checking it
returns nothing relevant - not because it seems unlikely.

### Level 0 — the object itself

Its own fields, read directly, values not just presence/absence:

- **A `Bone`**: `anim_angle`/`anim_pos`/`anim_scale` (print the actual
  keyframe VALUES, not just the count - a channel that reverses direction
  every keyframe looks very different from one that eases smoothly, and
  that shape is often the clue), `scaling_mode`, `target_bone`,
  `flip_h`/`flip_v`, `bone_dynamics`/`angle_dynamics`/`wind_dynamics` +
  `spring_force`/`damping_force`/`torque_force`, `constraints`/
  `min_constraint`/`max_constraint`, `fixed_angle`, `length`, `strength`.
- **A `Layer`**: its own `transform` (translate/scale/rotate/flip),
  `parent_bone`, `flexi_bone_subset`, `origin`, `masking`/`group_mask`,
  `action_names`, `visible`/`edit_only`.
- **A `MeshPoint`**: `position` (channel), `width`, and critically
  `.parent` - a per-POINT rigid bone override that the default render path
  can silently ignore (see `RenderSettings.point_bone_binding`/
  `--point-bones`). Check `mesh.has_point_bones` and dump
  `{pt.parent for pt in mesh.points}` early, not as an afterthought - this
  is exactly what level 0 missed in the DarkMan case because the question
  was framed as "what's wrong with the bone", not "what does the mesh
  actually bind to".

### Level 1 — the parent

- **A `Bone`**: its `parent` index, and THAT bone's own world motion -
  rotation composes down a chain (`Skeleton.world_matrices`), so a modest
  child angle can still produce a large WORLD swing if the parent itself
  swings, and vice versa. Compute `world_matrices` and extract the actual
  world angle/origin per frame - don't reason from local angle alone (see
  the DarkMan investigation: B1/B2/B3's local angles didn't by themselves
  explain the observed on-screen motion; their WORLD angles, and the
  mesh's per-point BINDING to them, did).
- **A `Layer`**: its ancestor chain's own `Transform` (an ancestor
  `BoneLayer`'s own translate/scale/rotate is a real, separate source of
  motion, independent of any skeleton) and `parent_bone`/
  `flexi_bone_subset` (is this layer even skinned to an ancestor's
  skeleton, or just riding its plain Transform? A `BoneLayer`-kind layer's
  own `parent_bone` is a sentinel, not a real bone index - see
  `docs/moho-project-file-format.md`'s NOTE on this - don't mistake a `-2`
  there for "unbound", check whether it CARRIES ITS OWN skeleton instead).

### Level 2 — siblings and peers

Anything else at the same tree level, or anything that CROSS-REFERENCES
the object under investigation by index rather than by tree position:

- **Sibling bones** in the same skeleton (same `parent` index) - do they
  move very differently? A big gradient between siblings (as with
  `right_part`'s B1/B2/B3) is itself a clue about where blending/weighting
  might be smearing one bone's motion into territory that should belong to
  another. Also check whether their OWN channels reverse direction at
  DIFFERENT keyframes than the object under investigation - a chain's
  world rotation sums each ancestor's local angle (see level 1), and
  summing several independently-alternating signals with staggered
  keyframe timing can create more apparent oscillation in the composed
  result than any single signal has on its own.
- **Cross-references by bone index, not tree position**: `target_bone`
  (IK - does another bone in the SAME skeleton name this one, or does this
  one name another?), `angle_control_parent`/`pos_control_parent`/
  `scale_control_parent` (control bones - one bone's channel driven by
  ANOTHER bone's, not necessarily its parent; **not applied by this
  exporter at all**, so a real subscription here is a genuine, silent gap,
  not just a modelling approximation), `anim_parent` (an animatable
  version of the static `parent` field - check it actually matches the
  static one before assuming it's inert).
- **Other layers bound into the SAME skeleton**: everything sharing a
  `flexi_bone_subset`/`parent_bone` with the object, or (for a mesh) every
  OTHER mesh under the same `BoneLayer` - do they show the same symptom?
  If only one does, the cause is more likely in that mesh's own binding
  data (level 0/2) than in the skeleton's shared math (level 3).

### Level 3 — shared / global configuration

Nothing object-specific left to check at this level - it's what the WHOLE
skeleton, layer, or export run shares:

- **`BoneLayer`-level fields**: `wind`/`gravity` (`direction`/`strength`/
  `turbulence_*`) and `physics` (`enabled`/`static`/...) apply to every
  bone in that one skeleton, not just the one under investigation - check
  whether OTHER bones in the same skeleton show a related symptom before
  concluding it's local to one bone.
- **`RenderSettings`/CLI flags**: `bone_weight_falloff` (the region-blend
  shape - a KNOWN approximation, see `BONE_WEIGHT_FALLOFFS`),
  `point_bone_binding`/`--point-bones`, `bone_dynamics`/`--bone-dynamics`,
  `wind_dynamics`/`--wind-dynamics`, `smooth_bone_joints`/
  `--smooth-joints`. These change behaviour for the WHOLE export, silently,
  from their off-by-default state - always state which flags were active
  when reporting a measurement.
- **Masking** (`group_mask`/`masking`): can make a sibling layer's own
  shape irrelevant to what's visible, or clip an otherwise-correct
  deformation.
- **Smart Bone actions** (`Layer.action_names`, `Channel.actions`): a pose
  registered on the object's OWN channel is level 0; a pose that some OTHER
  active dial elsewhere in the document happens to also touch this
  channel is a level-2/3 concern - check `exporter._active_actions` at the
  frame in question.

## How to actually check each level

Use the real document model, not guesswork - this repo's whole culture is
built on reading real field values rather than inferring from symptoms
alone. A typical investigation is a short Python one-liner sequence:

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0, '.')
from moho2svg import load_document, Exporter, RenderSettings, Channel, _channel_ever_true

doc = load_document('moho/<Project>.mohoproj')
# Level 0: find the object, dump its own raw fields
# Level 1: walk `path`/`.parent` to the ancestor(s), check their own motion
# Level 2: enumerate skeleton.bones / layer.children for siblings, check
#          target_bone / *_control_parent / anim_parent for cross-refs
# Level 3: check layer._raw['physics']/['wind']/['gravity'], and try the
#          relevant RenderSettings flag(s) with an Exporter to compare
EOF
```

Prefer computing REAL numbers (world angle/position via
`Skeleton.world_matrices`, actual weight shares via a temporarily
monkey-patched `Skinner.deform`, before/after pixel measurements from a real
`export_layer`/`Exporter._geometry_and_mapper` call) over reasoning from
field names alone - the DarkMan investigation's breakthrough was measuring
per-point weight shares and before/after pixel travel, not just noticing
`MeshPoint.parent` existed.

## When you find the real cause

- If it's a **rendering/approximation choice** in this exporter (a weight
  falloff shape, a missing per-point binding path, an off-by-default flag)
  - state the concrete before/after numbers, and check whether flipping a
  default would affect other tracked documents (`make check-reference`)
  before recommending it. Prefer an opt-in flag over a silent default
  change unless the evidence is unambiguous across every tracked case.
- If it's a **genuinely unmodelled Moho feature** (control bones, animated
  layer ordering, Smart Warp) - say so plainly rather than approximating
  it silently; these are real, documented gaps, not bugs to paper over.
- Update the relevant docstring's evidence trail either way, including
  hypotheses that were tested and DISPROVEN (see `Skeleton.dynamic_angles`'
  WIND EVIDENCE section for the pattern) - a documented negative result
  saves the next investigation from repeating it.
