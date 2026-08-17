# Moho Project File — JSON Schema

This directory is a **JSON Schema** ([draft 2020-12](https://json-schema.org/))
description of the `.mohoproj` / `.animeproj` file format — the same role an
XSD plays for an XML format. It is the *structural, machine-validatable*
counterpart to `docs/moho-project-file-format.md`, which is the *semantic,
evidence-based* companion document. Read both; neither replaces the other
(see [§ 6](#6-what-this-schema-cannot-tell-you)).

Built from, and validated against, all **46** real project files under `moho/`
(gitignored — see the repository's own `CLAUDE.md`), spanning format version
**1021** through **1045**. (It was originally built against 19 of them; the
46-file pass added the `ParticleLayer` and `NoteLayer` types, the `Halo` and
`Shaded` style effects, and decoded `blend_mode` and `fill_style_id`/
`line_style_id`/`fill_style2_id`.)

---

## 1. File layout

| File | Defines |
|---|---|
| `channel.schema.json` | `Channel` — the single most-repeated structure in the format (500,000+ instances across the sample set): `ValChannel`, `ColorChannel`, `Vec2Channel`, `Vec3Channel`, `BoolChannel`, `StringChannel`, plus `InterpEntry` and `ActionRef` (Smart Bone overrides). |
| `style.schema.json` | `Style` (a document-wide named style, and — same shape — a shape's own inline style) plus the **seven** styled-fill/stroke effect variants a `fill_style`/`fill_style2`/`line_style` slot can hold: `Gradient` (`SS_Gradient2`), `Halo` (`SS_Halo`), `Shaded` (`SS_Shaded`), `SoftStyle` (`SS_Soft`), `Crayon` (`SS_Crayon`), `Texture2` (`SS_Texture2`), `ShadowStyle` (`SS_Shadow`). |
| `mesh.schema.json` | `Mesh`, `MeshPoint`, `Curve`, `CurvePoint`, `Edges`, `Shape`, `PointGroup`. |
| `skeleton.schema.json` | `Skeleton` and `Bone`. |
| `layer.schema.json` | `LayerCommon` and `LayerContainer` (the two composition bases), the discriminated union `Layer` = `MeshLayer` \| `BoneLayer` \| `GroupLayer` \| `SwitchLayer` \| `PatchLayer` \| `TextLayer` \| `ImageLayer` \| `ParticleLayer` \| `NoteLayer`, the shared per-layer effect blocks (`LayerEffects`, `LayerShadow`, `LayerShading`, `PerspectiveShadow`, `MotionBlur`, `Physics`, `Transforms`, `LayerOutline`, `LayerColor`, `FileRef`, `PlainRGBA`), and `Mesh3DOptions`, `LayerMetadata`, `ScriptData`, `ActionRegistryEntry`. |
| `project.schema.json` | The **root** document schema — `$ref`s all of the above — plus `ProjectData`, `AnimatedValues`, `DocumentViewState`, `DocumentMetadata`, `PlainVec2`/`PlainVec3`. Validate a whole `.mohoproj`/`.animeproj` file against **this** file. |

Each file's own `$defs` are self-contained; cross-file references use plain
relative `$ref`s (e.g. `"channel.schema.json#/$defs/ValChannel"`), so the
directory works as-is with any standard JSON Schema validator — no bundling
step required.

---

## 2. How to validate a file

Any draft-2020-12-compatible validator works. Two quick options:

**Python (`jsonschema` + `referencing`):**
```bash
pip install jsonschema referencing
python3 -c "
import json
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

files = ['channel','style','mesh','skeleton','layer','project']
resources = []
for f in files:
    doc = json.load(open(f'schema/{f}.schema.json'))
    resources.append((f'{f}.schema.json', Resource.from_contents(doc, default_specification=DRAFT202012)))
    resources.append((doc['\$id'], Resource.from_contents(doc, default_specification=DRAFT202012)))
registry = Registry().with_resources(resources)
project_schema = json.load(open('schema/project.schema.json'))
validator = Draft202012Validator(project_schema, registry=registry)

doc = json.load(open('moho/YourFile.mohoproj'))
errors = list(validator.iter_errors(doc))
print(f'{len(errors)} error(s)')
for e in errors[:20]:
    print(' at', '/'.join(str(p) for p in e.path), '-', e.message)
"
```

**Node (`ajv`):**
```bash
npm install ajv
node -e "
const Ajv = require('ajv');
const fs = require('fs');
const ajv = new Ajv({allowUnionTypes: true});
for (const f of ['channel','style','mesh','skeleton','layer']) {
  ajv.addSchema(JSON.parse(fs.readFileSync(\`schema/\${f}.schema.json\`)));
}
const validate = ajv.compile(JSON.parse(fs.readFileSync('schema/project.schema.json')));
const doc = JSON.parse(fs.readFileSync('moho/YourFile.mohoproj'));
console.log(validate(doc) ? 'valid' : validate.errors);
"
```

Validation performance note: across the 19 sampled documents a pure-Python
validator takes **0.6 s to 85 s per file**, and about 3.5 minutes for the whole
set — most files land under 12 s, with the two heaviest rigs
(`WhatIsBone` 85 s, `AddBone` 49 s) dominating. Every layer is checked against
a 7-way discriminated union and every animated field against its channel shape,
so cost tracks channel count more than raw file size. This is a one-off
documentation/CI check, not something to run per-export. If a mid-size file
starts taking *minutes*, something in the schema is re-walking the layer tree —
see the `layers` note in § 4.

---

## 3. How completeness was checked (and why validation alone does not prove it)

A clean validation run proves only that **the fields the schema already knows
about** have the expected shape. Because every object here is
`additionalProperties: true` (see [§ 4](#4-design-decisions-read-this-before-extending-the-schema)),
a field the schema has never heard of passes **silently**. All 19 documents
validated with zero errors while the schema was still completely missing
`Mesh3DOptions` (648 instances), `fill_style2` and `layer_ordering`.

So completeness is checked by a second, separate pass: walk each real document
*alongside* the schema, resolving `$ref`/`allOf`/`oneOf` to work out which
`$def` each object is being validated against, and report every key that was
accepted **only** by `additionalProperties`. That audit is what found the gaps
listed in [§ 5](#5-findings-from-the-19-file-sample).

Both passes are green as of this writing:

| Check | Result |
|---|---|
| Structural validation, 19/19 documents | 0 errors |
| Undeclared-key audit | 0 keys reachable only via `additionalProperties` |
| Multi-form audit (a declared field observed as two different value shapes) | 0 conflicts |
| `oneOf` discrimination audit (an object matching no branch's `type`) | 0 ambiguities |

So every single key present in all 19 documents is now explicitly described,
including the four bags that stay *open* by design — `documentviewstate`, the
document-level `metadata`, and each layer's own `metadata` and `script_data`.
Their observed keys are enumerated (`DocumentViewState`, `DocumentMetadata`,
`LayerMetadata`, `ScriptData`), but `additionalProperties` stays permissive
there because their key sets come from editor state and user scripts rather
than from the format itself. Two of them lean on `patternProperties` for a
whole key family: `LayerMetadata`'s `g_<number>` toggles, and
`DocumentViewState`'s nine per-quadrant `0`–`3` families.

**If you extend the schema, re-run both passes**, not just validation. A gap
audit is the only thing that catches "the schema silently does not describe
this."

---

## 4. Design decisions (read this before extending the schema)

**Permissive, not restrictive.** Every object in this schema uses
`"additionalProperties": true`. This is a *reverse-engineered* spec of a
closed, proprietary format sampled from only 19 real documents — treating an
unrecognised field as an error would fail on the very next real-world file
that uses a feature outside this sample. The schema's job is to confirm that
the fields it *does* recognise have the right shape, not to reject fields it
doesn't yet know about.

**Enums are typed as `integer`/`string` with observed values in
`description`, not a JSON Schema `enum`, unless the value set is provably
closed.** Most of Moho's small-integer "mode" fields (`masking`,
`combo_mode`, `blend_mode`, `scaling_mode`, `binding_mode`, ...) have only a
*partially* decoded meaning, and this sample is 19 documents, not Moho's
entire installed base. A strict `enum` would reject a legitimate file that
happens to use a value this sample never exercised. The handful of fields
that genuinely use a closed, well-understood set (`Channel.type`,
`Gradient.gradient_type`, `Style.line_caps`) do use `enum` or `const`.

**A named `Style` object is reused as both the document-wide named style and
a shape's own inline style** — they are, byte for byte, the same shape (see
`docs/moho-project-file-format.md` § 8). One `$def`, one source of truth.

**`LayerCommon` + `allOf` stands in for XSD's `xs:extension`.** JSON Schema
has no native "inheritance" keyword; the idiomatic equivalent is `"allOf":
[{"$ref": ".../LayerCommon"}, {"type": "object", "properties": {...the
type-specific fields...}}]`, used for every one of the seven layer types.
There are **two** such bases, and the split is deliberate: `LayerCommon` holds
what every layer has, `LayerContainer` holds what only a layer that *holds
other layers* has (`layers`, `group_mask`, `expanded`, `depth_sort`,
`distance_sort`, `layer_ordering`, `animated_layer_order`). `BoneLayer`,
`GroupLayer` and `SwitchLayer` compose both; the four leaf types compose only
`LayerCommon`. Before this split those seven fields were duplicated across
branches and, as a direct consequence, several were simply missing from
`GroupLayer` and `BoneLayer`.

**Cross-file `$ref`s are mutually recursive, by design.** `layer` → `mesh` →
`style` → `layer` (the last hop being `Texture2`'s `SS_Texture2FileRef`
reusing `layer.schema.json#/$defs/FileRef` rather than duplicating that
two-field shape). This is legal JSON Schema and every registry-based validator
handles it — but it does mean **no single file is standalone**: load all six
into the validator before compiling, as both examples in § 2 do.

**The one place duplication beat reuse: the `layers` array.** `LayerContainer`
holds the six *cheap* container fields, but each of `BoneLayer`, `GroupLayer`
and `SwitchLayer` declares its own `layers` property. That is deliberate and
measured, not an oversight. Reaching the recursive `{"$ref": "Layer"}` through
one extra `$ref` hop — inside an `allOf`, inside the recursive `Layer` `oneOf`
— cost **11x** in wall-clock validation for byte-identical semantics:

| `layers` declared in | `SketchBone.animeproj` | `OffsetBoneTool.animeproj` |
|---|---|---|
| `LayerContainer` (one shared copy) | 182.8 s | 8.7 s |
| each container type (three copies) | 16.6 s | 4.2 s |

Every other container field stays shared, so the drift that originally left
`layer_ordering`/`depth_sort`/`distance_sort` undeclared on `GroupLayer`
cannot recur. Do not "tidy" `layers` back into `LayerContainer` — there is a
note in the `$def` itself saying so.

**Channel vs. plain value is NOT modelled as `oneOf` everywhere it could
theoretically occur.** `docs/moho-project-file-format.md` notes that Moho
*can* store a never-animated field as a bare scalar instead of a full
`{type, when, val, interp}` channel. Across all 19 sampled documents, this
schema's channel-typed fields (`anim_pos`, `fill_color`, `position`, ...)
were **always** the full channel form — never once a bare scalar. Fields
that were *consistently* observed as plain values (`line_width`,
`brush_jitter`, `origin`, bone `offset`/`pos_control_scale`, ...) are typed
as plain here, matching what every sample actually contains. **This is a
known gap, not an oversight**: a hand-authored or differently-exported file
that uses the bare-scalar shorthand on a field this schema expects as a full
channel will fail validation here. Widening the affected field to `oneOf`
[channel, plain] is the fix, the moment a real example turns up. The audit in
§ 3 reports any field seen in two different value shapes, so such a case shows
up as a "multi-form" hit rather than needing to be spotted by hand — it
reports 0 across this sample.

---

## 5. Findings from the 19-file sample

Broadening the sample from 5 files to 19 (adding Moho's own bundled
bone-tool tutorial documents — `AnglePositionScale`, `BoneDynamics`,
`BoneParenting`, `BoneStrengthTool`, `ControlBones`, `IK-FK`,
`IndependentAngle`, `MaximumIKStrethching`, `OffsetBoneTool`, `Rabbit`,
`SelectandReparentBoneTool`, `TargetBone`, `TransformBoneTool`, plus
`SlickObjectTransition`) surfaced structure this schema captures but the
prose format doc does not yet describe:

- **A seventh layer type: `ImageLayer`.** A raster image/movie/PSD-import
  layer (15 instances, in `BoneStrengthTool.animeproj`'s "dude side.psd"
  cutout-puppet rig — one `ImageLayer` per PSD layer, each bound to a bone
  subset). Not handled by `moho2svg.py` at all (a vector-only exporter) — a
  document using `ImageLayer` silently loses that artwork on export. See
  `layer.schema.json`'s `ImageLayer` `$def` for the full field list
  (`image_path`, `psd_layer_bounds`, `toon_*` effect fields, movie-specific
  fields like `avi_alpha`/`movie_looping`, ...).
- **`parent_bone` can be `-3`.** Previously only `-1` (flexible) and `>= 0`
  (rigid) were documented. `-3` appears *exclusively* on `ImageLayer`
  instances, always alongside a real `flexi_bone_subset` — presumably a
  bone-mesh-warp deformation mode specific to raster images, distinct from a
  vector mesh's rigid/flexible binding. Not reverse-engineered; not handled
  by `moho2svg.py`.
- **`masking` can be `5` or `6`**, not just `0`/`1`/`2`. Observed on a
  handful of `MeshLayer` instances across two documents
  (`ControlBones.animeproj`, `OffsetBoneTool.animeproj`,
  `SlickObjectTransition.mohoproj`). Meaning not decoded;
  `moho2svg.py` treats any value other than `1`/`2` as "clipped", so these
  currently behave as ordinary masked children.
- **Format version `1021`** (`Rabbit.animeproj`) is older than the
  previously-documented `1038`/`1045` pair, and is missing `doc_uuid`,
  `action_refs`, and `modified_date` **entirely** (not empty — the keys are
  absent). `styles` can also legitimately be an empty list (`Rabbit`,
  `SlickObjectTransition`) — a document can carry zero named styles at all.
- **`line_style_id` and `fill_style_id`** take more values than previously
  sampled (`2`, `11`, `12` in addition to `9`) — reinforcing that these are
  arbitrary internal reference ids, not a small closed enum.
- **`fill_style`/`line_style` hold four different effect types, not just
  gradients.** The previous 5-file sample only ever contained `SS_Gradient2`,
  which made "`fill_style` means a gradient" look like a safe rule. It is
  not. Full counts across the 19 files:

  | Effect type | As `fill_style` | As `line_style` | Fields |
  |---|---|---|---|
  | `SS_Gradient2` | 1196 (17 files) | 116 (16 files) | `gradient_type`, `gradients[]`, `through_alpha` |
  | `SS_Crayon` | 19 (1 file) | — | `line_width`, `density`, `clear_background`, `reduce_randomization`, `rand_seed` |
  | `SS_Soft` | — | 9 (3 files) | `blur_radius`, `threshold` |
  | `SS_Shadow` | — | 3 (3 files) | `angle`, `offset`, `blur`, `color`, `threshold` |

  The fill and line variant sets are **disjoint** apart from `SS_Gradient2`.
  `moho2svg.py` reads only `SS_Gradient2` (and only as a fill) — the other
  three are silently dropped, so a shape styled with `SS_Crayon` renders as a
  flat fill and one with `SS_Soft`/`SS_Shadow` renders a plain flat stroke.
  Also note `SS_Crayon` was found **inline on a shape's own style object**
  (`OffsetBoneTool.animeproj`, layer "pant-shades"), disproving the earlier
  assumption that `fill_style` only ever lives on a document-wide named style.
- **`BoneLayer.gravity` / `BoneLayer.wind` wrap their sub-fields in
  channels**, while `GroupLayer.gravity` uses plain floats — the two `gravity`
  fields differ in *both* key names and value type (`{direction, strength}` as
  `ValChannel`s vs. `{x, y}` as bare numbers). Bone physics is rare (one
  `BoneLayer` in the whole sample, `Bandit.mohoproj`, version 1045); group
  gravity is common (16 `GroupLayer`s, all three format generations). Neither
  is read by `moho2svg.py`.
- **Every `MeshLayer` carries a full `Mesh3DOptions` block** (`3d_options`,
  648 instances — one per sampled `MeshLayer`, including the one nested inside
  each `TextLayer`). It holds ten 3D-extrusion settings (shading mode/density/
  colour, silhouette / material / crease edge toggles, crease angle, edge
  extension, backface removal, Z reset). In every sample the values are
  identical defaults and the gating `3d_mode` field is `0`, so the block is
  inert everywhere — but it is a large, completely undocumented structure, and
  a document that switched `3d_mode` on would export with no extrusion or 3D
  shading at all.
- **A style has a `fill_style2` slot as well as `fill_style`**, holding a
  *fifth* effect type, `SS_Texture2` (an image-texture fill: `path`,
  `SS_Texture2FileRef`, `fill_mode`, `through_alpha`). 12 occurrences across 3
  files, version 1038. In all 12 both path fields are empty, so no sampled
  document actually resolves a texture file — the populated shape is inferred
  from field names, not confirmed. Not read by `moho2svg.py`.
- **Container layers carry an animated child-draw-order channel,
  `layer_ordering`** (a `StringChannel`), present on ~150 containers —
  effectively every `BoneLayer` and `GroupLayer`. Its value is an **empty
  string in every single instance**, and the paired `animated_layer_order`
  boolean is `true` on only 2 containers (`ControlBones`, `SketchBone`) where
  the channel is still empty. So no sampled document reorders children over
  time, and `moho2svg.py` — which always uses the raw `layers` array order —
  is correct for this corpus but would stack layers wrongly for a document
  that does use the feature.
- **`TextLayer.mesh_layer` is a complete `MeshLayer`**, not a stripped-down
  `{type, mesh}` pair: it carries the whole `MeshLayer` field set (all the
  noise/sketchy fields, `3d_mode`, `3d_options`, texture paths and filerefs).
  The schema now `$ref`s `MeshLayer` directly rather than re-declaring a
  partial copy.
- **`metadata` appears on `MeshLayer` too**, not just on container layers, and
  `script_data` on `BoneLayer`. Both are now on `LayerCommon` with their
  observed key sets enumerated (`LayerMetadata`, `ScriptData`) — including a
  `g_<number>` boolean-toggle family matched by `patternProperties`, and a
  `psd_layers` key on the `BoneLayer` wrapping a PSD cutout-puppet import that
  records which PSD layers became `ImageLayer` children.
- **`documentviewstate` is exactly 48 keys in all 19 documents**: 12
  document-global (grid, playback range, viewport split) plus nine per-quadrant
  families suffixed `0`–`3`, one set per pane of Moho's four-way viewport
  split. Only quadrant `0` ever has a non-zero zoom. All of it is editor UI
  state with no effect on exported geometry.
- **`layer_effects.alpha` and `blend_mode`'s ignored-value differences**
  (see `docs/moho-project-file-format.md` § 13.2) are corroborated, not
  contradicted, by this broader sample.

**Update: all of the above is now folded into `docs/moho-project-file-format.md`**,
each finding marked **(19-file finding)** inline so it stays clear which
claims rest on the original 5-file evidence and which needed the broader
sample. That pass also caught several things beyond this list, while
re-deriving every count in the prose doc against all 19 files:

- **`Rabbit.animeproj` (the `1021` generation) cannot be loaded by
  `moho2svg.py` at all** — `CurvePoint._build` reads `weight_in`/`weight_out`/
  `offset_in`/`offset_out` via plain dict indexing, and this generation omits
  those four fields entirely, so `python3 moho2svg.py moho/Rabbit.animeproj
  --list` raises `KeyError: 'weight_in'`. Confirmed by running it. This is a
  hard load failure, not a rendering-accuracy gap, and is not yet fixed in
  `moho2svg.py` — only documented (`docs/moho-project-file-format.md`
  § 7.3, § 13.2 item 1).
- **Three pre-existing claims in the prose doc were simply wrong**, caught
  by re-checking the ORIGINAL 5 files' raw JSON directly (not new-file
  findings, corrections): `project_data.global_render_style_*` is the
  integer `0` in every sample, not an empty string; `animated_values.camera_zoom`
  is `2.0` in every sample, not `0.0`; and `channel.mute`/`channel.ref` are not
  "false everywhere" — one channel has `mute: true` and 207 have `ref: true`
  (both with no visible effect on current output, since every occurrence
  sampled has only one keyframe).
- Several other aggregate counts changed materially once measured across all
  19 files rather than 5 — e.g. `bone.strength`'s observed range widened from
  `0.0–0.6` to `0.0–7.654676`, and `shape.fill_allowed: false` from 229 to 859
  occurrences. These are corrected in place in the prose doc rather than
  listed here individually.

Folding future schema findings into the prose doc the same way (confirmed
counts, `(19-file finding)` tagging, and re-verifying old claims rather than
assuming they still hold) remains the right process going forward.

---

## 6. What this schema *cannot* tell you

A JSON Schema validates **structure**: does a field exist, is it the right
type, does an enum value fall in the expected set. It cannot express, and
does not attempt to express:

- **Cross-field behaviour.** E.g. that a `masking == 2` sibling paints on top
  of whatever it masks *regardless of list order* (achieved by excluding the
  source's own stroke band from the mask geometry, not by z-order); that
  `combo_mode == 1`'s combined outline is styled using the *group's first
  member*, not its own; that a `PatchLayer`'s own `transforms` must be
  **ignored** in favour of its target's. A schema has no place to put "if X
  then render behaviour Y."
- **Evidence and confidence.** Which fields are confirmed exact (e.g. the
  Bezier handle-length formula, checked against 209 reference handles) versus
  which are best-effort heuristics (e.g. the `PatchLayer` transform
  substitution, the bone-weight-falloff shape) versus which are simply
  unread by `moho2svg.py`. A `description` string can *mention* this (and
  this schema's descriptions do, liberally), but it cannot be validated or
  queried the way a type or enum can.
- **Version-generation semantics.** That a `1038`-era document keeps real
  style values in a named style while a `1045`-era document puts them
  directly on the shape (`docs/moho-project-file-format.md` § 8.2) is a
  *content* pattern across two valid-per-schema documents, not a structural
  rule a schema can enforce.
- **Whether a field is exhaustively sampled.** An `enum` or a fixed set of
  observed values in a `description` reflects 19 files, not Moho's entire
  possible output space (see § 3's permissive-enum design decision above).

For all of this, use `docs/moho-project-file-format.md` (structure +
semantics + evidence) and `docs/moho-export-pipeline.md` (how `moho2svg.py`
actually consumes each field, in what order). This schema is the fast,
automatable check that a file's *shape* matches expectations — a first line
of defense, not a substitute for reading the prose.
