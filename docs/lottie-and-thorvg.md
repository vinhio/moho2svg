# Lottie and ThorVG

Lottie is a JSON file format for animated vector graphics. ThorVG is a C++
engine that can read such a file and draw it. This document describes both,
and the relationship between them, as background for a planned feature:
**exporting one specific frame out of a Lottie file**.

Unlike the Moho format, Lottie is **documented and machine-readable**. This
repository carries a copy of that documentation as a JSON Schema, so almost
nothing here needs to be reverse-engineered. Where a statement below comes
from the schema, it is a fact you can re-check with a one-line script. Where
it comes from an external website or from a source file downloaded from
GitHub, it is labelled as such.

Companion documents (Moho side, not modified by this one):

- [`moho-project-file-format.md`](moho-project-file-format.md) — the Moho
  field reference.
- [`moho-animation-and-transform.md`](moho-animation-and-transform.md) — how
  Moho stores motion and composes transforms.
- [`moho-rigging-and-deformation.md`](moho-rigging-and-deformation.md) —
  bones, skinning, Smart Warp.
- [`moho-export-pipeline.md`](moho-export-pipeline.md) — how `moho2svg.py`
  walks a document and emits SVG.
- [`moho-exporting-svg.md`](moho-exporting-svg.md) — the CLI usage guide.

Section 14 is the only place where the two worlds meet. Sections 1 to 8 are
pure Lottie, sections 9 to 13 are pure ThorVG and integration.

---

## 1. Scope and evidence base

### 1.1 What was measured

Every Lottie field name, type, default, and enum value in sections 2 to 8 was
read out of the schema files stored in this repository:

| Path | What it is | Size |
|---|---|---|
| `lottie/lottie.schema.json` | One bundled JSON Schema file, self-contained | 12 modules, 159 definitions |
| `lottie/schema/**` | The same schema split into one file per definition | 160 files (159 definitions + `root.json`) |
| `lottie/examples/` | Two sample Lottie documents | not used as a source in this document |

**Both schema forms are tracked in git; `lottie/examples/` is not.** So a
fresh clone can re-run every script in § 16, including the bundle-versus-split
comparison. Nothing in this document depends on the example files.

The two schema forms were compared programmatically. After normalising `$ref`
targets and dropping the per-file `$schema` / `$id` keys, **157 of 159
definitions are byte-identical**. The two that differ are
`layers/unknown-layer` and `shapes/unknown-shape`; see § 2.4 for why, because
the difference matters if you plan to validate files.

### 1.2 What was not measured

- **No Lottie file was rendered** while writing this document. Nothing here
  claims a visual result.
- **ThorVG was not built, installed, or run.** Sections 9, 10 and 12 describe
  the API as published in the ThorVG source code and website; they are not
  observations of a working build in this repository.
- **The `lottie/examples/` files were deliberately not used.** A sample file
  only shows what one exporter happened to emit. The schema shows what the
  format allows.

### 1.3 External sources

| Source | Used for |
|---|---|
| `https://lottiefiles.github.io/lottie-docs/` | Human-readable Lottie documentation; it is the origin of the schema in this repository (§ 2.1) |
| `https://lottie.github.io/lottie-spec/` | The other Lottie documentation lineage (§ 11.1) |
| `https://www.thorvg.org/` | ThorVG identity, formats, backends, platforms |
| `thorvg/thorvg` on GitHub (`src/bindings/capi/thorvg_capi.h`, `meson_options.txt`, `tools/`) | Exact C API signatures, build options, bundled tools |
| `thorvg/thorvg.example` on GitHub (`src/Lottie.cpp`) | Canonical C++ usage of the animation API |
| `laggykiller/thorvg-python` (GitHub + PyPI metadata) | The Python binding evaluated in § 13 |

Confidence marks used below: **[confirmed]** means read directly from a file
in this repository or from a source file quoted above; **[reported]** means
stated by a website and not independently checked; **[inferred]** means a
conclusion drawn from those, not a quotation.

---

## 2. How to read the Lottie schema

### 2.1 Which schema this is

`lottie/lottie.schema.json` declares:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://lottiefiles.github.io/lottie-docs/schema/lottie.schema.json",
  "$ref": "#/$defs/composition/animation"
}
```

[confirmed] So this is the **lottie-docs** schema, published by LottieFiles.
It is written in **JSON Schema draft 2020-12**, and the whole document is
just a `$ref` to one definition: `composition/animation`. Everything else
hangs off that.

`lottie/schema/root.json` is the same three lines in the split tree.
[confirmed]

This is *not* the only Lottie schema in the world. See § 11.1 for the
distinction between lottie-docs and lottie-spec, which matters when you need
to decide what "valid Lottie" means.

### 2.2 The `$defs` layout

All definitions live under `$defs`, grouped into 12 modules. The counts are
exact. [confirmed]

| Module | Definitions | What it holds |
|---|---:|---|
| `composition` | 5 | the document root, metadata, motion blur |
| `layers` | 14 | the 9 concrete layer types plus shared bases |
| `shapes` | 29 | everything that can appear inside a shape layer |
| `properties` | 17 | the animatable-property and keyframe machinery |
| `values` | 7 | leaf value types (color, vector, bezier, …) |
| `helpers` | 6 | transform, mask, marker, slot, visual object |
| `assets` | 7 | precompositions, images, sounds, data sources |
| `constants` | 20 | the enumerations |
| `effects` | 18 | After Effects style layer effects |
| `effect-values` | 11 | the parameter types those effects take |
| `styles` | 11 | Photoshop style layer styles |
| `text` | 14 | text documents, fonts, text animators |

A reference inside the bundled file looks like `#/$defs/shapes/fill`. In the
split tree the same reference is a relative file path. That is the only
systematic difference between the two forms.

### 2.3 The composition pattern

Lottie definitions are built by composition, not by repetition. Almost every
object is an `allOf` of a shared base plus its own fields. The chain for a
solid fill is:

```
shapes/fill
  allOf[0] -> shapes/shape-style      (adds: o = opacity)
                allOf[0] -> shapes/graphic-element   (adds: nm, mn, hd, ty, bm, ix, cl, ln)
                              allOf[0] -> helpers/visual-object  (adds: nm, mn)
  allOf[1] -> own fields              (ty = "fl", c = color, r = fill rule)
```

[confirmed] Practical consequence: **you cannot read one definition and know
all the fields an object accepts.** You must follow the `allOf` chain to the
root. A reader that only handles `shapes/fill`'s own two fields will silently
drop `hd` (hidden) and `bm` (blend mode), which change what is drawn.

### 2.4 The type discriminator, and the escape hatch

Polymorphic lists are modelled as `oneOf` over concrete types, discriminated
by a `ty` field:

- `layers/all-layers` — `oneOf` of 10 entries, the last being
  `layers/unknown-layer`.
- `shapes/all-graphic-elements` — `oneOf` of 20 entries, the last being
  `shapes/unknown-shape`.
- `assets/all-assets` — `oneOf` of 4 entries, no unknown fallback.

[confirmed] The `unknown-*` entries exist so that a file using a `ty` value
the schema does not know still validates. They are written as a negation:

```json
"ty": { "not": { "$comment": "enum list is dynamically generated",
                 "enum": [0, 1, 2, 3, 4, 5, 6, 15, 13] } }
```

[confirmed] **This is the one place where the bundled file and the split tree
disagree.** In the split tree those `enum` arrays are empty; the bundle has
them filled in. An empty `enum` inside `not` matches nothing, so in the split
tree `unknown-layer` would accept *every* `ty`, including known ones, and the
`oneOf` would then match two branches at once and fail.

**Use `lottie/lottie.schema.json` for validation.** The split tree is the
authoring source; the bundle is the build output. [inferred, but the empty vs
filled `enum` is directly confirmed]

### 2.5 A caution about the word "required"

The schema marks very few things as required. For example
`layers/layer` requires only `ty`, `ip`, `op`; `helpers/transform` requires
nothing at all. [confirmed] That is a statement about *validation*, not about
*rendering*. A renderer still has to supply a default for every absent
property, and the schema records those defaults only sometimes (`sr` default
`1`, `st` default `0`, `bm` default `0`, mask `o` default `100`). Where the
schema gives no default you have to take it from a player's behaviour, not
from the schema.

---

## 3. The document root

The whole file is one `composition/animation` object. It is an `allOf` of
`helpers/visual-object` (giving `nm` and `mn`) plus these fields. [confirmed]

| Key | Type | Title | Notes from the schema |
|---|---|---|---|
| `v` | string | Bodymovin version | "on very old versions some things might be slightly different from what is explained here" |
| `ver` | integer | Specification Version | 6 digits, `MMmmpp`; minimum 10000 |
| `fr` | number | Framerate | frames per second, exclusive minimum 0 |
| `ip` | number | In Point | "Frame the animation starts at (usually 0)" |
| `op` | number | Out Point | "Frame the animation stops/loops at, which makes this the duration in frames when `ip` is 0" |
| `w` | integer | Width | minimum 0 |
| `h` | integer | Height | minimum 0 |
| `ddd` | int-boolean | Threedimensional | default 0; whether the animation has 3D layers |
| `assets` | array | Assets | list of `assets/all-assets` |
| `comps` | array | Extra Compositions | precompositions not referenced by anything |
| `fonts` | `text/font-list` | Fonts | |
| `chars` | array | Characters | "If present a player might only render characters defined here and nothing else" |
| `meta` | `composition/metadata` | Metadata | author, description, theme colour, generator, keywords |
| `metadata` | `composition/user-metadata` | User Metadata | filename, custom properties |
| `mb` | `composition/motion-blur` | Motion blur | shutter angle/phase, samples per frame, adaptive sample limit |
| `slots` | object | Slots | see § 7.4 |
| `markers` | array | Markers | see § 8.4 |

Note the two different version fields. `v` is the **Bodymovin exporter**
version (a string like `"5.7.0"`); `ver` is a **specification** version
encoded as an integer. They answer different questions, and a file can carry
one, both, or neither. [confirmed]

`composition/composition` is a separate, tiny definition: an object with a
required `layers` array. The animation root and every precomposition asset
both include it. [confirmed]

---

## 4. Properties and keyframes

This is the part of Lottie that matters most for the frame-export feature,
because "give me frame N" means "evaluate every property at N".

### 4.1 The property envelope

`properties/property` is the shared base: [confirmed]

| Key | Meaning |
|---|---|
| `a` | Animated flag, an int-boolean, default 0 |
| `k` | The value — a static value when `a == 0`, an array of keyframes when `a == 1` |
| `ix` | Property index, used by expressions |
| `x` | Expression, a string |
| `sid` | Slot id — if present, the value comes from the document's `slots` |

The base carries a conditional: `if` the object has `sid`, nothing else is
required; `else` both `a` and `k` are required. [confirmed] So a property can
legitimately have **no value of its own** and defer to a slot.

Each concrete property type is an `allOf` of that base plus a `oneOf` of two
shapes — the not-animated shape (`a` const 0, `k` is a value) and the
animated shape (`a` const 1, `k` is an array of keyframes). The types:

| Definition | Static `k` | Animated `k` items |
|---|---|---|
| `scalar-property` | `number` | `vector-keyframe` |
| `vector-property` | `values/vector` | `vector-keyframe` |
| `position-property` | `values/vector` | `position-keyframe` |
| `color-property` | `values/color` | `color-keyframe` |
| `bezier-property` | `values/bezier` | `bezier-keyframe` |
| `gradient-stops` | `values/gradient` | `gradient-keyframe` |

[confirmed] Two oddities worth noting. `scalar-property` holds a plain
`number` when static but its keyframes are **vector** keyframes, so an
animated scalar's `s` is an array such as `[42]`, not the bare number `42`.
And `vector-property` / `position-property` accept an extra `l` field
("Length"), the number of components, used only when expressions read the
value. [confirmed]

### 4.2 Keyframes

`properties/base-keyframe` requires only `t`: [confirmed]

| Key | Meaning |
|---|---|
| `t` | Time, a **frame number** (not seconds), default 0 |
| `h` | Hold flag, int-boolean, default 0 |
| `i` | In tangent — easing going *into the next* keyframe, an `easing-handle` |
| `o` | Out tangent — easing *leaving the current* keyframe, an `easing-handle` |

Every concrete keyframe adds `s`, the value at this keyframe, and a
**deprecated** `e`, the value at the end of the segment. The schema states the
rule plainly: "note that this is deprecated and you should use `s` from the
next keyframe to get this value". [confirmed] A reader should therefore treat
`e` as a fallback for old files only.

`position-keyframe` extends `vector-keyframe` with `ti` and `to`, tangents in
*value* space — "Tangent for values (eg: moving position around a curved
path)". [confirmed] These are what make a position animate along a curve
instead of a straight line, and they are separate from the `i` / `o` easing,
which acts on time.

`bezier-keyframe` has an unusual constraint: its `s` is an **array of exactly
one** `values/bezier` (`minItems: 1, maxItems: 1`). [confirmed] A shape
keyframe is a one-element array wrapping the path, not the path itself.

### 4.3 Easing

`properties/easing-handle` requires `x` and `y`, each of which is *either* a
number *or* an array of numbers. [confirmed] The schema's own wording:

- `x` — "Time component: 0 means start time of the keyframe, 1 means time of
  the next keyframe." Constrained to `[0, 1]`.
- `y` — "Value interpolation component: 0 means start value of the keyframe,
  1 means value at the next keyframe." Not constrained to `[0, 1]`, so
  overshoot is legal.

So a segment's interpolation is a cubic Bezier in normalised
(time, value) space with control points `(o.x, o.y)` from the earlier
keyframe and `(i.x, i.y)` from the later one. The array form exists so each
component of a multi-component value can ease differently. [inferred from the
type definition; the schema does not spell out the per-component semantics]

When `h` (hold) is 1 on a keyframe, the value stays constant until the next
keyframe. [inferred from the field name and its int-boolean type; the schema
gives no description text for `h`]

### 4.4 Leaf value types

`values/*` are the concrete leaves. [confirmed]

| Definition | Shape |
|---|---|
| `vector` | array of numbers, no length constraint |
| `color` | array of 3 or 4 numbers, **each in `[0, 1]`** |
| `gradient` | flat array of numbers in `[0, 1]`: colour stops `[offset, r, g, b]` first, then optional transparency stops `[offset, alpha]` |
| `bezier` | object with `c` (closed, default false), `v` (vertices), `i` (in tangents), `o` (out tangents); `i`, `v`, `o` all required |
| `int-boolean` | integer, enum `[0, 1]` |
| `hexcolor` | string matching `^#([a-fA-F0-9]{6})$` |
| `data-url` | string matching `^data:([\w/]+)(;base64)?,(.+)$` |

Two things here are easy to get wrong.

**Colours are 0..1 floats, not 0..255** — except `layers/solid-layer.sc`,
which is a `hexcolor` string. [confirmed] Lottie is inconsistent about this
in exactly one place.

**Bezier tangents are relative.** The schema says the `i` and `o` points "are
along the `in`/`out` tangents **relative to** the corresponding `v`".
[confirmed] So an absolute cubic control point is `v[n] + o[n]`, not `o[n]`.
This is the same convention Moho uses after `BezierReconstructor` has run, and
different from SVG path data, which is absolute.

**The gradient array is untagged.** Nothing in `values/gradient` says where
the colour stops end and the transparency stops begin. That count comes from
`properties/gradient-property.p` ("Color stop count") — a sibling field, not
part of the array. [confirmed] A reader that ignores `p` cannot parse a
gradient with transparency stops correctly.

---

## 5. Layers

### 5.1 The shared base

`layers/layer` — required `ty`, `ip`, `op`. [confirmed]

| Key | Type | Meaning |
|---|---|---|
| `ty` | integer | Layer type (the discriminator) |
| `nm`, `mn` | string | Name, match name (from `helpers/visual-object`) |
| `ind` | integer | Index, used for parenting and by expressions |
| `parent` | integer | The `ind` of the parent layer |
| `ip` | number | In point — frame when the layer becomes visible |
| `op` | number | Out point — frame when the layer becomes invisible |
| `st` | number | Start time, default 0 |
| `sr` | number | Time stretch, default 1 |
| `ddd` | int-boolean | Whether the layer is three-dimensional, default 0 |
| `hd` | boolean | Hidden |

`layers/visual-layer` adds everything to do with appearance. Required `ks`.
[confirmed]

| Key | Type | Meaning |
|---|---|---|
| `ks` | `helpers/transform` | The layer transform |
| `ao` | int-boolean | Auto-orient: rotate to match the animated position path, default 0 |
| `tt` | `constants/matte-mode` | Track matte mode |
| `tp` | integer | Matte parent layer index; "if omitted assume the layer above the current one" |
| `td` | int-boolean | Set to 1 on a layer that is *used as* a matte |
| `hasMask` | boolean | Whether masks are applied |
| `masksProperties` | array of `helpers/mask` | The masks |
| `ef` | array of `effects/all-effects` | Layer effects |
| `sy` | array of `styles/all-layer-styles` | Layer styles |
| `bm` | `constants/blend-mode` | Blend mode, default 0 |
| `mb` | boolean | Motion blur enabled |
| `ct` | int-boolean | Collapse transform — "Marks that transforms should be applied before masks", default 0 |
| `cp` | boolean | **Deprecated**, superseded by `ct` |
| `cl`, `ln`, `tg` | string | CSS class, XML `id`, XML tag name — hints for an SVG-based renderer |

The presence of `cl` / `ln` / `tg` is a small but telling detail: Lottie
expects some players to be SVG DOM renderers and lets an author name the
elements. [confirmed]

### 5.2 The concrete layer types

| `ty` | Definition | Required beyond the base | Purpose |
|---:|---|---|---|
| 0 | `precomposition-layer` | `refId` | draws a precomposition asset; also `w`, `h` (clip rect), `st`, `tm` (time remap) |
| 1 | `solid-layer` | `sw`, `sh`, `sc` | a solid rectangle; `sc` is a `#RRGGBB` string |
| 2 | `image-layer` | `refId` | draws an image asset |
| 3 | `null-layer` | — | no content; exists to be a parent |
| 4 | `shape-layer` | `shapes` | vector content |
| 5 | `text-layer` | `t` | text, see § 7.3 |
| 6 | `audio-layer` | `au` | sound; extends `layer`, not `visual-layer` |
| 13 | `camera-layer` | `ks`, `pe` | 3D camera; extends `layer` and adds its own `ks` and `pe` (perspective) |
| 15 | `data-layer` | — | references a data source asset via `refId` |

[confirmed] Note the gaps in the numbering, and note that `camera-layer` and
`audio-layer` are **not** visual layers — they extend `layers/layer`
directly, so they have no masks, effects, or blend mode.

For a frame exporter, only types 0, 1, 2, 3, 4, 5 can produce pixels.
[inferred]

### 5.3 Parenting

Parenting is by `ind`, not by nesting: a layer's `parent` holds the `ind` of
another layer in the **same** composition. [confirmed] The layer array is
therefore a flat list with a transform graph laid over it. Two consequences:

- Draw order and transform order are independent. A child can be drawn far
  from its parent in the list.
- A precomposition is a separate `ind` namespace. A layer cannot parent to a
  layer inside a precomp. [inferred from `parent`'s description, "Must be the
  `ind` property of another layer", combined with precomps being separate
  compositions]

### 5.4 Masks and mattes

Lottie has **two** unrelated occlusion mechanisms, and a file can use both on
the same layer.

**Masks** (`masksProperties`) are per-layer shapes. `helpers/mask` requires
`pt`: [confirmed]

| Key | Meaning |
|---|---|
| `pt` | The mask shape, a `bezier-property` |
| `mode` | `constants/mask-mode`, default `"i"` |
| `o` | Opacity 0..100, default 100 |
| `x` | Expand |
| `inv` | Inverted, default false |

Mask modes are single characters: `"n"` none, `"a"` add, `"s"` subtract,
`"i"` intersect, `"l"` lighten, `"d"` darken, `"f"` difference. [confirmed]
The schema describes the mode as how a mask "interacts (blends) with the
**preceding masks in the stack**", so the mask list is evaluated in order,
each combining with the accumulated result.

**Track mattes** (`tt` / `tp` / `td`) use one *layer* to mask another.
`constants/matte-mode`: 0 normal, 1 alpha, 2 inverted alpha, 3 luma, 4
inverted luma. [confirmed] The matte source layer carries `td: 1`; the masked
layer carries `tt`, and `tp` names the source by index — defaulting, when
absent, to "the layer above the current one".

This is structurally similar to Moho's own two-field masking (`group_mask` on
the container plus `masking` on each child) described in
[`moho-project-file-format.md`](moho-project-file-format.md) § 10 — two
independent fields that must be read together — but the mechanisms are not
equivalent. Lottie's mask is a shape list per layer; Moho's is a role flag on
a sibling.

---

## 6. Shape elements

A shape layer's `shapes` array holds `shapes/all-graphic-elements`, a `oneOf`
over 19 concrete types plus the unknown fallback. Every one of them extends
`shapes/graphic-element`, which supplies `ty`, `nm`, `mn`, `hd`, `bm`, `ix`,
`cl`, `ln`. [confirmed]

### 6.1 The full element table

| `ty` | Definition | Category | Required own fields |
|---|---|---|---|
| `gr` | `group` | container | — (`it` holds the children, `np`/`cix` are indices) |
| `sh` | `path` | geometry | `ks` (a `bezier-property`) |
| `rc` | `rectangle` | geometry | `s` (size), `p` (centre); `r` = corner radius |
| `el` | `ellipse` | geometry | `s`, `p` |
| `sr` | `polystar` | geometry | `or`, `os`, `pt`, `p`, `r`; `sy` star/polygon, `ir`, `is` |
| `fl` | `fill` | style | `c` (colour); `r` = fill rule |
| `st` | `stroke` | style | `c`; plus all of `base-stroke` |
| `gf` | `gradient-fill` | style | all of `base-gradient`; `r` = fill rule |
| `gs` | `gradient-stroke` | style | `base-stroke` + `base-gradient` |
| `no` | `no-style` | style | — ("a style for shapes without fill or stroke") |
| `tr` | `transform` | transform | all of `helpers/transform` |
| `tm` | `trim-path` | modifier | `o`, `s`, `e`; `m` = parallel or sequential |
| `rp` | `repeater` | modifier | `c` (copies), `tr` (a `repeater-transform`); `o`, `m` |
| `rd` | `rounded-corners` | modifier | `r` (radius) |
| `mm` | `merge` | modifier | `mm` = merge mode |
| `op` | `offset-path` | modifier | `a` (amount), `lj`, `ml` |
| `pb` | `pucker-bloat` | modifier | `a` (amount, a percentage) |
| `tw` | `twist` | modifier | `a` (angle), `c` (centre) |
| `zz` | `zig-zag` | modifier | `r` (frequency), `s` (amplitude), `pt` (point type) |

[confirmed]

### 6.2 The three intermediate bases

- `shapes/shape` — geometry base. Adds only `d`, a
  `constants/shape-direction` (1 normal, 3 reversed), "mostly relevant when
  using trim path". Extended by `path`, `rectangle`, `ellipse`, `polystar`.
- `shapes/shape-style` — style base. Adds `o`, opacity, required. Extended by
  `fill`, `stroke`, `gradient-fill`, `gradient-stroke`, `no-style`.
- `shapes/modifier` — modifier base. Adds nothing at all; it exists purely to
  express intent: "Modifiers change the bezier curves of neighbouring
  shapes."

[confirmed]

### 6.3 Stroke and gradient details

`shapes/base-stroke` requires `w`: [confirmed]

| Key | Meaning |
|---|---|
| `w` | Width (a scalar property) |
| `lc` | Line cap, default 2 — 1 butt, 2 round, 3 square |
| `lj` | Line join, default 2 — 1 miter, 2 round, 3 bevel |
| `ml` | Miter limit, a plain number, default 0 |
| `ml2` | Miter limit, "animatable alternative to `ml`" |
| `d` | Array of `shapes/stroke-dash` |

A dash item has `n`, a `stroke-dash-type` of `"d"` dash, `"g"` gap, or `"o"`
offset, and `v`, the length. [confirmed] So the SVG `stroke-dasharray` and
`stroke-dashoffset` are encoded as a tagged list, not as two separate fields.

`shapes/base-gradient` requires `s`, `e`, `g`, `t`: [confirmed] start point,
end point, colours, and `constants/gradient-type` (1 linear, 2 radial,
3 conic). `h` (highlight length, a percentage between `s` and `e`) and `a`
(highlight angle) exist for radial gradients.

### 6.4 The ordering rule

Lottie's shape list is not a plain draw list. Style elements apply to
"neighbouring shapes" and modifiers change "the bezier curves of neighbouring
shapes" — both phrases are from the schema descriptions. [confirmed] The
schema does **not** define what "neighbouring" means precisely, nor whether
styles apply to elements before or after them in the array. That rule lives
in the player and in the prose documentation, not in the machine-readable
schema. [confirmed by absence]

This is a real gap for anyone writing a Lottie **writer**: producing an array
whose order a player interprets as intended cannot be verified against the
schema alone. It must be checked against a renderer.

---

## 7. Assets, text, effects, styles, slots

### 7.1 Assets

`assets/asset` requires `id`, a "unique identifier used by layers when
referencing this asset". `assets/file-asset` adds `p` (file name or data
URL), `u` (path), and `e` (embedded — "If `1`, `p` is a Data URL").
[confirmed]

| Definition | Extends | Adds |
|---|---|---|
| `precomposition` | `asset` + `composition/composition` | `fr` (own framerate), `xt` (extra composition flag) |
| `image` | `file-asset` + `slottable-object` | `w`, `h`, `t` (const `"seq"` marks an image sequence) |
| `sound` | `file-asset` | — |
| `data-source` | `file-asset` | `t` const 3 |

[confirmed] A precomposition is therefore *both* an asset and a composition:
it has an `id` and its own `layers` array. That is how Lottie nests.

### 7.2 Effects and layer styles

Two separate systems, both on `visual-layer`.

**Effects** (`ef`) mirror After Effects effects. 16 concrete types plus a
base and an "all" union. [confirmed] `ty` values: 20 tint, 21 fill, 22
stroke, 23 tritone, 24 pro levels, 25 drop shadow, 26 radial wipe, 27
displacement map, 28 set matte, 29 gaussian blur, 30 twirl, 31 mesh warp, 32
wavy, 33 spherize, 34 puppet. There is also `custom-effect` with `ty` 5,
described as "Some lottie files use `ty` = 5 for many different effects" —
an honest admission that the field is not reliably discriminating.
[confirmed]

Effect parameters are `effect-values/*`, again discriminated by `ty`: 0
slider, 1 angle, 2 colour, 3 point, 4 checkbox, 6 ignored, 7 drop-down, 10
layer. [confirmed]

**Layer styles** (`sy`) mirror Photoshop layer styles: `ty` 0 stroke, 1 drop
shadow, 2 inner shadow, 3 outer glow, 4 inner glow, 5 bevel emboss, 6 satin,
7 colour overlay, 8 gradient overlay. [confirmed]

Most players implement few of these. Which ones is a per-player question, not
a schema question.

### 7.3 Text

14 definitions. The core is `text/text-data`, reachable from
`layers/text-layer.t`, holding the text document (`animated-text-document`,
whose keyframes are `text-document-keyframe`), the font list, ranges
(`text-range` with `text-range-selector` and `text-style`), alignment
options, and follow-path.

The document root can also carry `chars`, an array of `text/character-data`,
which defines glyph outlines as Lottie shapes (`character-shapes`) or as
precomps (`character-precomp`). The root's description is explicit about the
consequence: "If present a player might only render characters defined here
and nothing else." [confirmed]

That is the practical route to text without fonts: an exporter converts
glyphs to outlines up front. [inferred]

### 7.4 Slots

`helpers/slot` is an object with a required `p`, "Property Value".
`helpers/slottable-object` adds `sid`, "Identifier to look up the slot". The
property base's own `sid` field is described as "One of the ID in the file's
slots". [confirmed]

Slots are Lottie's theming mechanism: a property says "my value comes from
slot X" and the host swaps X at runtime without editing the layer tree.
ThorVG exposes this directly (§ 10.3).

---

## 8. The time model

This section matters most for the frame-export feature, so it states each
point with its evidence.

### 8.1 Frames, not seconds

Every time value in Lottie is a **frame number**. `properties/base-keyframe.t`
is titled "Time" and described as "Frame number". Layer `ip`/`op`/`st` are
frame numbers. Only `fr` converts to wall-clock. [confirmed]

```
time_in_seconds = frame / fr
```

### 8.2 Frames are real numbers, not integers

`fr`, `ip`, `op`, `st`, `sr`, and keyframe `t` are all declared `"type":
"number"`, not `"integer"`. Only `w`, `h`, `ind`, `parent`, and `ver` are
integers. [confirmed]

So **"frame 12.5" is a legal, meaningful request.** A frame exporter should
take a float, not an int. This also means `op - ip` is a frame count that need
not be a whole number.

### 8.3 Per-layer time

Three fields shift and scale a layer's own timeline relative to the
composition's:

| Field | Schema title | Default |
|---|---|---|
| `ip` | In Point — "Frame when the layer becomes visible" | required |
| `op` | Out Point — "Frame when the layer becomes invisible" | required |
| `st` | Start Time | 0 |
| `sr` | Time Stretch | 1 |

[confirmed] The schema gives `st` and `sr` titles but **no description text**,
so their exact composition order is not defined by the schema. The
conventional reading is that a layer's local time is
`(composition_frame - st) / sr`, and that `ip`/`op` are compared in
composition time. [inferred — this is *not* confirmed by the schema and should
be verified against a renderer before relying on it]

`precomposition-layer` additionally has `tm`, Time Remap, described as
"Timeline remap function (frame index -> time in seconds)". [confirmed] Note
the stated unit change: the remap output is in **seconds**, while everything
else is in frames. If that description is accurate, evaluating a precomp under
time remap requires multiplying by the precomp's `fr` again. This is worth
verifying against a player before implementing. [flagged as uncertain]

A precomposition asset carries its **own** `fr`. [confirmed] So a nested
composition can run at a different framerate than its parent.

### 8.4 Markers

`helpers/marker` has `cm` (comment), `tm` (time), `dr` (duration), and the
module description is "Defines named portions of the composition".
[confirmed] Markers give names to frame ranges. ThorVG can select a marker
and play only that range (§ 10.3).

### 8.5 What "export frame N" therefore means

Given the above, evaluating a Lottie document at frame `N` requires, per
layer, in order: [inferred, assembled from the confirmed field semantics]

1. Skip the layer if `N < ip` or `N >= op`, or if `hd` is true.
2. Map `N` into the layer's local time using `st` and `sr`.
3. Evaluate every animated property at that local time by locating the
   bracketing keyframes and applying the `h` / `i` / `o` easing.
4. Compose the transform chain by following `parent` to the root.
5. For a precomp layer, recurse with the precomp's own `fr` and `tm`.

Nothing in this list needs a rasteriser. That observation is what makes § 13's
"write our own evaluator" option viable at all.

---

## 9. What ThorVG is

### 9.1 Identity

ThorVG (Thor Vector Graphics) is an open-source vector graphics engine.
[reported, `thorvg.org`]

| Property | Value | Evidence |
|---|---|---|
| Language | C++ core, with C++, C and JavaScript APIs | [reported] |
| Licence | MIT | [reported] |
| Origin | created by Hermet Park in 2020 | [reported] |
| Latest release at time of writing | `v1.1.0`, published 2026-07-22 | [confirmed] via the GitHub releases API |
| Core size | approximately 170 KB | [reported] |
| Adopters named on the site | Canva, Godot, LVGL | [reported] |

### 9.2 What it reads and writes

From `meson_options.txt` in the ThorVG repository — this is the build's own
list of modules, so it is authoritative about capability, not marketing.
[confirmed]

```
loaders : '', svg, png, jpg, lottie, ttf, otf, webp, media, all
          (default: svg, lottie, ttf)
savers  : '', gif, all
          (default: '')
engines : cpu, gl, wg, all          (default: cpu)
bindings: '', capi                  (default: '')
tools   : '', svg2png, lottie2gif, all   (default: '')
extra   : '', opengl_es, lottie_exp, openmp   (default: lottie_exp, openmp)
```

Three facts follow, and all three matter for this repository.

**ThorVG's only saver is GIF.** There is exactly one directory under
`src/savers`, and it is `gif`. [confirmed] ThorVG can read SVG but **cannot
write SVG**, so it will never hand you a vector file. It can still hand you
vector *data* through the scene-reading API — see § 10.5, which is what makes
Option D in § 13.4 possible.

**The C API is opt-in.** `bindings` defaults to empty. A stock build has no
`libthorvg` C entry points unless it was configured with `-Dbindings=capi`.
[confirmed]

**Lottie expressions are on by default.** `extra` defaults include
`lottie_exp`. [confirmed]

### 9.3 Rendering backends

`engines` offers `cpu`, `gl` and `wg`. The C API exposes one canvas
constructor per backend: [confirmed, from `thorvg_capi.h`]

```c
TVG_API Tvg_Canvas tvg_swcanvas_create(Tvg_Engine_Option op);
TVG_API Tvg_Canvas tvg_glcanvas_create(Tvg_Engine_Option op);
TVG_API Tvg_Canvas tvg_wgcanvas_create(Tvg_Engine_Option op);
```

Only the software canvas can render into a plain memory buffer with no
windowing system:

```c
TVG_API Tvg_Result tvg_swcanvas_set_target(Tvg_Canvas canvas, uint32_t* buffer,
        uint32_t stride, uint32_t w, uint32_t h, Tvg_Colorspace cs);
```

[confirmed] The accepted colour spaces for that call are, per the header's own
note, `TVG_COLORSPACE_ABGR8888`, `ARGB8888`, `ABGR8888S` and `ARGB8888S`,
where the `S` suffix means **un-premultiplied** alpha and the plain names mean
**alpha-premultiplied**. [confirmed] Getting this wrong produces subtly wrong
edges on transparent artwork, so it is worth stating explicitly.

For headless, offline, one-frame export the software canvas is the only
sensible choice. [inferred]

### 9.4 Bundled tools

`tools/` contains exactly two programs. [confirmed]

**`tvg-svg2png`** — its own usage string:

```
tvg-svg2png [SVG file] or [SVG folder] [-r resolution] [-b bgColor]
```

It validates input with a literal extension check for `.svg` and rejects
anything else. It has no frame flag. [confirmed, from `tools/svg2png/svg2png.cpp`]

**`tvg-lottie2gif`** — its own usage string:

```
tvg-lottie2gif [Lottie file] or [Lottie folder] [-r resolution] [-f fps] [-b background color]
```

It validates input with a literal extension check for `.json`, and its whole
conversion body is: create an `Animation`, load the file into
`animation->picture()`, scale it, then `saver->save(animation, out, 100, fps)`.
It has no frame flag either. [confirmed, from `tools/lottie2gif/lottie2gif.cpp`]

**Neither bundled tool can export a single frame.** That is a confirmed
capability gap, not an opinion.

---

## 10. ThorVG's Lottie API

All signatures below are quoted verbatim from
`src/bindings/capi/thorvg_capi.h` at `main`. [confirmed]

### 10.1 The animation object

```c
TVG_API Tvg_Animation tvg_animation_new(void);
TVG_API Tvg_Paint     tvg_animation_get_picture(Tvg_Animation animation);
TVG_API Tvg_Result    tvg_animation_set_frame(Tvg_Animation animation, float no);
TVG_API Tvg_Result    tvg_animation_get_frame(Tvg_Animation animation, float* no);
TVG_API Tvg_Result    tvg_animation_get_total_frame(Tvg_Animation animation, float* cnt);
TVG_API Tvg_Result    tvg_animation_get_duration(Tvg_Animation animation, float* duration);
TVG_API Tvg_Result    tvg_animation_set_segment(Tvg_Animation animation, float begin, float end);
TVG_API Tvg_Result    tvg_animation_get_segment(Tvg_Animation animation, float* begin, float* end);
TVG_API Tvg_Result    tvg_animation_del(Tvg_Animation animation);
```

The frame parameter is a `float`, matching Lottie's own real-valued frame
model (§ 8.2). The header's documentation adds four constraints that a caller
must respect: [confirmed]

- `no` "should be less than the `tvg_animation_get_total_frame()`", and frame
  numbering "starts from 0", with the current frame "between 0 and
  totalFrame() - 1".
- Setting a frame that differs from the current one by **less than 0.001** is
  ignored, returning `TVG_RESULT_INSUFFICIENT_CONDITION`. This is documented
  as an efficiency measure. It means a caller cannot treat
  `INSUFFICIENT_CONDITION` as an error — it is the normal result of setting
  the frame you are already on.
- `tvg_animation_get_total_frame` returns 0 "if the Picture is not properly
  configured", so 0 is the failure signal as well as an empty result.
- The picture returned by `tvg_animation_get_picture` "is owned by Animation.
  It should not be deleted manually."

`tvg_animation_set_segment` (since 1.0) restricts playback to a frame range,
after which "the number of animation frames and the playback time are
calculated by mapping the playback segment as the entire range" — i.e. it
**renumbers** frames, so a segment changes what `set_frame(N)` means.
[confirmed]

### 10.2 Loading

There is no Lottie-specific loader call. A Lottie file is loaded through the
generic picture interface: [confirmed]

```c
TVG_API Tvg_Result tvg_picture_load(Tvg_Paint picture, const char* path);
TVG_API Tvg_Result tvg_picture_load_data(Tvg_Paint picture, const char* data, uint32_t size,
                                         const char* mimetype, const char* rpath, bool copy);
```

Format detection is by extension or MIME type. ThorVG's own example accepts
two Lottie extensions:

```cpp
//ignore if not lottie.
const char *ext = path + strlen(path) - 4;
if (strcmp(ext, "json") && strcmp(ext, "lot")) return;
```

[confirmed, from `thorvg.example/src/Lottie.cpp`] So `.json` and `.lot` are
both recognised.

`tvg_picture_load_data` matters for a Python integration: it takes a memory
buffer plus an `rpath` (root path for resolving the file's external
references), so a Lottie document can be rendered without ever touching disk.
[confirmed]

### 10.3 Lottie-specific calls

```c
TVG_API Tvg_Animation tvg_lottie_animation_new(void);
TVG_API uint32_t   tvg_lottie_animation_gen_slot(Tvg_Animation animation, const char* slot);
TVG_API Tvg_Result tvg_lottie_animation_apply_slot(Tvg_Animation animation, uint32_t id);
TVG_API Tvg_Result tvg_lottie_animation_del_slot(Tvg_Animation animation, uint32_t id);
TVG_API Tvg_Result tvg_lottie_animation_set_marker(Tvg_Animation animation, const char* marker);
TVG_API Tvg_Result tvg_lottie_animation_get_markers_cnt(Tvg_Animation animation, uint32_t* cnt);
TVG_API Tvg_Result tvg_lottie_animation_get_marker_info(Tvg_Animation animation, uint32_t idx,
                                                        const char** name, float* begin, float* end);
TVG_API Tvg_Result tvg_lottie_animation_tween(Tvg_Animation animation, float from, float to, float progress);
TVG_API Tvg_Result tvg_lottie_animation_tween_to(Tvg_Animation animation, float to);
TVG_API Tvg_Result tvg_lottie_animation_tween_go(Tvg_Animation animation, float progress);
TVG_API Tvg_Result tvg_lottie_animation_set_quality(Tvg_Animation animation, uint8_t value);
TVG_API Tvg_Result tvg_lottie_animation_set_audio_resolver(Tvg_Animation animation, Tvg_Audio_Resolver resolver, void* data);
```

[confirmed] These map one-to-one onto Lottie concepts described earlier:
slots (§ 7.4) and markers (§ 8.4). The `tween*` family blends between two
frames, which is a ThorVG feature, not a Lottie one.

Note that `tvg_lottie_animation_new` returns the same `Tvg_Animation` handle
type as `tvg_animation_new`, so the generic frame calls in § 10.1 apply to it
unchanged. [confirmed]

### 10.4 Canvas and saver

```c
TVG_API Tvg_Result tvg_engine_init(unsigned threads);
TVG_API Tvg_Result tvg_engine_term(void);
TVG_API Tvg_Result tvg_canvas_add(Tvg_Canvas canvas, Tvg_Paint paint);
TVG_API Tvg_Result tvg_canvas_update(Tvg_Canvas canvas);
TVG_API Tvg_Result tvg_canvas_draw(Tvg_Canvas canvas, bool clear);
TVG_API Tvg_Result tvg_canvas_sync(Tvg_Canvas canvas);
TVG_API Tvg_Result tvg_saver_save_animation(Tvg_Saver saver, Tvg_Animation animation,
                                            const char* path, uint32_t quality, uint32_t fps);
```

[confirmed] `tvg_canvas_sync` is mandatory before reading the target buffer,
because drawing may be asynchronous when the engine was initialised with
threads. The saver is likewise asynchronous and documents "To guarantee the
saving is done, call `tvg_saver_sync()` afterwards."

`tvg_saver_save_animation` writes a whole animation, and given `savers` only
offers `gif`, the only output format it can produce is GIF. [confirmed for the
saver list; inferred for the conclusion]

### 10.5 Reading the scene back

ThorVG cannot *write* SVG, but it can be *asked what it drew*. This changes
the options in § 13 considerably, so the evidence is laid out in full.

**Walking the tree.** The Accessor module, "a module for manipulation of the
scene tree": [confirmed]

```c
TVG_API Tvg_Accessor tvg_accessor_new(void);
TVG_API Tvg_Result tvg_accessor_set(Tvg_Accessor accessor, Tvg_Paint paint,
                                    bool (*func)(Tvg_Paint paint, void* data), void* data);
TVG_API Tvg_Result tvg_accessor_del(Tvg_Accessor accessor);
```

Its documentation: "Iterates through all descendents of the scene passed
through the paint argument while calling func on each... When func returns
false iteration stops." [confirmed]

**Identifying each node.** `tvg_paint_get_type` returns a `Tvg_Type`:
`TVG_TYPE_SHAPE`, `TVG_TYPE_SCENE`, `TVG_TYPE_PICTURE`, `TVG_TYPE_TEXT`, plus
`TVG_TYPE_LINEAR_GRAD` (10) and `TVG_TYPE_RADIAL_GRAD` (11). [confirmed]

**Reading geometry.** [confirmed]

```c
TVG_API Tvg_Result tvg_shape_get_path(const Tvg_Paint paint,
        const Tvg_Path_Command** cmds, uint32_t* cmdsCnt,
        const Tvg_Point** pts, uint32_t* ptsCnt);
```

And `Tvg_Path_Command` is a `uint8_t` with four values whose documentation
states the mapping explicitly: [confirmed]

| Value | Constant | Header's own words |
|---:|---|---|
| 0 | `TVG_PATH_COMMAND_CLOSE` | "corresponds to Z command in the svg path commands" |
| 1 | `TVG_PATH_COMMAND_MOVE_TO` | "corresponds to M command in the svg path commands" |
| 2 | `TVG_PATH_COMMAND_LINE_TO` | "corresponds to L command in the svg path commands" |
| 3 | `TVG_PATH_COMMAND_CUBIC_TO` | "corresponds to C command in the svg path commands" |

**ThorVG's internal path model is SVG's path model.** That is not an
inference; the header says so four times.

**Reading appearance.** [confirmed]

```c
tvg_paint_get_transform(paint, &matrix)       tvg_paint_get_opacity(paint, &opacity)
tvg_paint_get_visible(paint)                  tvg_paint_get_parent(paint)
tvg_paint_get_clip(paint)                     tvg_paint_get_mask_method(paint, target, &method)
tvg_shape_get_fill_color(...)                 tvg_shape_get_fill_rule(paint, &rule)
tvg_shape_get_stroke_color(...)               tvg_shape_get_stroke_width(paint, &width)
tvg_shape_get_stroke_cap(paint, &cap)         tvg_shape_get_stroke_join(paint, &join)
tvg_shape_get_stroke_dash(paint, &pattern, &cnt, &offset)
tvg_shape_get_stroke_miterlimit(paint, &limit)
tvg_shape_get_gradient(paint, &grad)          tvg_shape_get_stroke_gradient(paint, &grad)
tvg_linear_gradient_get(grad, &x1, &y1, &x2, &y2)
tvg_radial_gradient_get(grad, &cx, &cy, &r, &fx, &fy, &fr)
tvg_gradient_get_color_stops(grad, &stops, &cnt)
tvg_gradient_get_spread(grad, &spread)        tvg_gradient_get_transform(grad, &m)
```

That set covers essentially every attribute an SVG `<path>` needs. [confirmed
that the functions exist; the completeness judgement is inferred]

**What is not readable this way.** There is no getter for glyph outlines on a
`TVG_TYPE_TEXT` paint, and raster effects such as blur or drop shadow have no
vector equivalent to read. Whatever ThorVG has already baked into the path
data — trim path, repeater, offset path, merge — comes back baked, which is
usually what an SVG writer wants anyway. [inferred]

**Not verified.** No code in this repository has walked a ThorVG scene. In
particular, it has not been checked whether a Lottie-loaded `Picture` exposes
its children to the Accessor, or whether the geometry read back is in local or
composed coordinates. `tvg_picture_get_paint(picture, id)` exists, which
suggests picture internals are reachable, but that is a hint, not a proof.
This is the single most valuable thing to test first.

---

## 11. How Lottie and ThorVG relate

### 11.1 Two documentation lineages

There are two distinct Lottie documentation efforts, and they are easy to
confuse because both publish a JSON Schema:

| | lottie-docs | lottie-spec |
|---|---|---|
| URL | `lottiefiles.github.io/lottie-docs` | `lottie.github.io/lottie-spec` |
| Maintainer | LottieFiles (Design Barn Inc.) [reported] | the Lottie Animation Community [reported] |
| Stated status | comprehensive format documentation | "a work in progress", covering "a subset of features that have been approved by the Lottie Animation Community" [reported] |
| Copy in this repository | **yes** — `lottie/lottie.schema.json`, `$id` confirms it | no |

[confirmed for the `$id`; reported for the rest]

The practical difference: **lottie-docs is descriptive, lottie-spec is
normative-in-progress.** lottie-docs documents what files in the wild actually
contain, including deprecated fields (`e` on keyframes), vendor quirks
(`custom-effect` with `ty` 5 "used for many different effects"), and Photoshop
layer styles. lottie-spec aims to standardise a subset.

For *reading* Lottie files, the descriptive schema in this repository is the
more useful of the two, because it covers more of what real files contain.
For *writing* Lottie files, targeting the approved subset is safer. [inferred]

### 11.2 Format, players, and where ThorVG sits

Lottie is a format with no reference implementation blessed as "the" renderer.
Several independent players exist — lottie-web (the browser player that
shipped alongside Bodymovin), rlottie, Skottie (inside Skia), and ThorVG among
them. Each implements its own subset. [inferred; this document did not audit
the other players]

The consequence is the single most important thing to understand about the
Lottie ecosystem: **"valid Lottie" and "renders correctly in player X" are
different questions.** The schema answers the first. Only running a player
answers the second. This repository has the schema, so it can answer the first
today; the second requires building or installing something.

ThorVG's position, stated by its own documentation, is that "Lottie is a
first-class citizen in ThorVG" with "extensive support for the Lottie
specification", while SVG support is limited to "the SVG Tiny Specification".
[reported] Read plainly, that is the reverse of this repository's priorities:
ThorVG is a strong Lottie *reader* and a weak SVG *reader*, and not an SVG
writer at all.

### 11.3 The asymmetry that matters here

| Direction | ThorVG | Notes |
|---|---|---|
| Lottie in → raster out | yes | render to a software-canvas buffer |
| Lottie in → GIF out | yes | `tvg_saver_save_animation`, whole animation |
| Lottie in → **SVG file out** | **no** | there is no SVG saver [confirmed] |
| Lottie in → **readable vector scene** | **yes** | Accessor + `tvg_shape_get_path`, whose commands map onto SVG's M/L/C/Z (§ 10.5) [confirmed] |
| SVG in → raster out | yes, SVG Tiny subset | `tvg-svg2png` |
| Anything → Lottie out | no | no Lottie saver [confirmed] |

`moho2svg.py` is an SVG writer. ThorVG is not, and never will be — but it does
not have to be. ThorVG can be the part that *understands Lottie*, handing back
an evaluated scene of paths, transforms, colours and gradients; the SVG
writing stays on our side, where it already lives. That split is the useful
one, and § 13 builds on it.

---

## 12. Exporting one specific frame

### 12.1 The pipeline, with ThorVG

Assembled from the confirmed API in § 10. This is the shape of the work, not
tested code.

1. `tvg_engine_init(threads)` — once per process.
2. `tvg_lottie_animation_new()` → an animation handle.
3. `tvg_animation_get_picture(animation)` → the picture it owns.
4. `tvg_picture_load(picture, path)` or `tvg_picture_load_data(...)` for an
   in-memory document.
5. `tvg_picture_set_size(picture, w, h)` to choose the output resolution.
6. `tvg_animation_get_total_frame(animation, &total)` — check for 0, which
   means "not properly configured".
7. `tvg_animation_set_frame(animation, n)` — `n` is a float in
   `[0, total - 1]`. Treat `TVG_RESULT_INSUFFICIENT_CONDITION` as success.
8. `tvg_swcanvas_create` + `tvg_swcanvas_set_target(buffer, stride, w, h, cs)`.
9. `tvg_canvas_add(canvas, picture)`.
10. `tvg_canvas_update` → `tvg_canvas_draw(canvas, true)` → `tvg_canvas_sync`.
11. Read the buffer. Encode it yourself — ThorVG has no PNG saver.
12. `tvg_animation_del`, `tvg_canvas_destroy`, `tvg_engine_term`.

Step 11 is the part people forget. `savers` offers GIF only (§ 9.2), so
producing a PNG means encoding the ABGR/ARGB buffer in your own code. The
`tvg-svg2png` tool solves this for itself by vendoring `lodepng.cpp` into its
own directory. [confirmed]

### 12.2 Frame number arithmetic

Three different numbers are easy to mix up:

| Quantity | Where it lives | Meaning |
|---|---|---|
| Lottie `ip` / `op` | the document | first and last frame of the composition, in the document's own numbering |
| ThorVG `totalFrame()` | the animation | a count; frame indices run 0 .. total-1 |
| ThorVG `duration()` | the animation | seconds |

ThorVG's frame index is 0-based regardless of the document's `ip`. [confirmed
from the header: "Frame numbering starts from 0"] If a Lottie file has
`ip: 30`, its own frame 30 is ThorVG's frame 0. **Any user-facing `--frame`
flag must state which numbering it uses.** [inferred]

`tvg_animation_set_segment` renumbers again (§ 10.1), as does selecting a
marker, so the two must not be combined casually — the header notes that when
a marker is set, a segment's range "will be disregarded". [confirmed]

### 12.3 What "a frame" can be

| Output | Possible with ThorVG? | How |
|---|---|---|
| PNG / raster image | yes | render to buffer, encode yourself |
| GIF (single frame) | awkward | the saver takes an animation, not a frame |
| **SVG file, written by ThorVG** | **no** | no SVG saver exists [confirmed] |
| **SVG file, written by us from ThorVG's scene** | **yes, in principle** | walk the scene with the Accessor and serialise it (§ 10.5) — not yet tested |
| Vector data in memory | yes | `tvg_shape_get_path` returns commands and points [confirmed] |

So a **vector** snapshot of a Lottie frame is reachable by two different
routes: let ThorVG evaluate the document and serialise what it produced
(§ 13.4), or evaluate the Lottie document ourselves and emit SVG directly
(§ 13.5). Both end in the SVG-writing machinery `moho2svg.py` already has.

---

## 13. Integration options for this repository

Current constraints, from [`CLAUDE.md`](../CLAUDE.md) and the source:
`moho2svg.py` is a single file using only the standard library, with Pillow as
an *optional* dependency that is imported inside a `try` block. Its imports
are `argparse`, `base64`, `io`, `json`, `math`, `os`, `random`, `re`,
`struct`, `sys`, `zipfile`, plus `dataclasses`, `enum` and `typing`.
[confirmed] There is no `zlib` import today, and no test suite.

### 13.1 Option A — the `thorvg-python` package

A third-party ctypes binding. [confirmed from PyPI metadata and its README]

| Property | Value |
|---|---|
| Package | `thorvg-python`, version 1.1.3 |
| Repository | `github.com/laggykiller/thorvg-python` |
| Licence in PyPI metadata | LGPL-2.1 (note: ThorVG itself is MIT) |
| Requires | Python >= 3.7 |
| Wheels | macOS universal2 / x86_64 / arm64, manylinux x86_64 / aarch64 / i686 / ppc64le / s390x, Windows 32 / amd64 / arm64 |
| Bundled ThorVG | "Version bundled is the version available on Conan (Currently 1.0.4)" |
| Pillow | optional, required for `SwCanvas.get_pillow()` |

Its README shows the exact flow we need:

```python
import thorvg_python as tvg

engine = tvg.Engine(threads=4)
canvas = tvg.SwCanvas(engine)
canvas.set_target(512, 512)

animation = tvg.LottieAnimation(engine)
picture = animation.get_picture()
picture.load("tests/test.json")
picture.set_size(512, 512)
canvas.push(picture)

result, total_frame = animation.get_total_frame()
animation.set_frame(i)
canvas.update(); canvas.draw(True); canvas.sync()
im = canvas.get_pillow()
```

**For:** no compiler needed, wheels bundle the native library, prebuilt for
every platform this project is likely to run on, and it already returns a
Pillow image — which this repository optionally depends on anyway.

**Against:** it is a hard third-party dependency in a project that currently
has none; the bundled ThorVG (1.0.4) trails upstream (1.1.0); the PyPI licence
field says LGPL-2.1, which is a different obligation from ThorVG's MIT and
should be checked properly before adopting.

### 13.2 Option B — `ctypes` against a system `libthorvg`

Call the C API directly with the standard library's `ctypes`.

**For:** no new Python dependency; full and current API surface; matches the
"stdlib only, optional extras" style of the existing code.

**Against:** the user must install ThorVG themselves, **and it must have been
built with `-Dbindings=capi`**, which is *not* the default (§ 9.2). A stock
Homebrew or distribution build may have no C symbols at all. We would also
have to hand-write the `Tvg_*` type declarations and keep them in sync, and
find the shared library across three platforms. Diagnosing a user's broken
install would become our support burden.

### 13.3 Option C — shell out to a ThorVG tool

Rejected on evidence, not preference. Neither `tvg-svg2png` nor
`tvg-lottie2gif` accepts a frame argument, and both are off by default in the
build (`tools` defaults to `''`). [confirmed] This option would require
writing and shipping our own C++ tool, which is a much larger change than any
other option here.

### 13.4 Option D — ThorVG evaluates, we serialise the scene

Load the Lottie file with ThorVG, set the frame, then **do not rasterise**.
Walk the resulting scene with the Accessor (§ 10.5) and write SVG from the
paths, transforms, colours and gradients it hands back.

**For:** vector output *without* reimplementing Lottie. ThorVG does the hard
part — keyframe evaluation, easing, precomps, time remap, modifiers, mattes —
and the part we do is the part this repository is already good at. ThorVG's
path commands are literally SVG's M/L/C/Z [confirmed], so the geometry
conversion is close to a transcription. It also sidesteps every "the schema
does not define this" gap in § 6.4 and § 8.3, because ThorVG has already made
those decisions.

**Against:** it is unproven — see the "not verified" note in § 10.5. It also
inherits ThorVG's blind spots: text has no readable outline getter, and raster
effects have no vector form. And the output is *ThorVG's interpretation* of
the file, which is the right answer only if ThorVG is right.

### 13.5 Option E — evaluate Lottie ourselves, no ThorVG

Read the Lottie JSON, evaluate every property at frame N using § 4 and § 8,
and emit SVG through the machinery `moho2svg.py` already has.

**For:** vector output with **no new dependency at all**, and full control over
the result — including the ability to keep Lottie constructs that ThorVG would
have flattened. The schema in `lottie/` is a complete, machine-readable
specification of the input, which is a far better starting point than the Moho
format ever had. Conceptually it is the same job the existing code does: sparse
keyframes on independent channels, evaluated at a frame, composed through a
transform stack — compare
[`moho-animation-and-transform.md`](moho-animation-and-transform.md) § 2 and
§ 3.

**Against:** it is by far the most work, and correctness is only provable
against a real player. The hard parts are the ones the schema does not define:
shape modifier semantics and the "neighbouring shapes" ordering rule (§ 6.4),
`st`/`sr` composition order (§ 8.3), and precomp time remap units (§ 8.3).
Effects, layer styles and text are effectively unbounded scope.

### 13.6 Comparison

| | A: `thorvg-python` | B: raw `ctypes` | C: bundled tool | D: ThorVG + scene walk | E: own evaluator |
|---|---|---|---|---|---|
| Vector output | no | no | no | yes | yes |
| Raster output | yes | yes | no (no frame flag) | yes | no |
| New dependency | one, optional | none, but a system library | a C++ tool we must write | same as A or B | none |
| Lottie correctness | ThorVG's | ThorVG's | — | ThorVG's | ours to prove |
| Work involved | small | medium | large | medium | large |
| Proven here | API confirmed | API confirmed | ruled out on evidence | **unverified** | — |

### 13.7 Recommendation

The choice turns on one unanswered question: **is the wanted output raster or
vector?**

- If **raster** (a PNG of frame N): take **Option A**. Add `thorvg-python` as
  an *optional* dependency guarded by `try: import ...`, exactly like the
  existing Pillow handling, and fail with a clear message when it is absent.
  It is the smallest change that produces a correct, fully-featured result,
  because ThorVG implements Lottie far more completely than we ever would.
  Confidence: high.
- If **vector** (an SVG of frame N) — the likelier intent, given what this
  repository is — then **try Option D before committing to Option E**. Option
  D reuses ThorVG's Lottie implementation and leaves us writing SVG, which is
  what this codebase already does well. Option E is several times the work and
  its hardest parts are exactly the places where the schema stops short
  (§ 6.4, § 8.3). Confidence that D is worth trying first: medium — it rests
  on the untested assumption in § 10.5.

**The cheap next step is a spike, not a design.** Install `thorvg-python`,
load a Lottie file, set a frame, walk the scene with the Accessor, and print
what comes back. That single experiment settles § 10.5's open question and
decides between D and E. Until it is run, any further design work is
speculation.

Whichever direction wins, ThorVG keeps a second role worth having: a
**reference renderer**. Render frame N with ThorVG, render it with our own
code, compare. That is the same "compare against a reference export" method
the Moho side of this repository was built on — see
[`moho-project-file-format.md`](moho-project-file-format.md) § 1 — except that
here the reference is free and scriptable, instead of a manual export from a
GUI application.

❓ Raster or vector is a product decision. No evidence in this document
settles it.

---

## 14. Mapping between Moho and Lottie

This section is a concept-level comparison, to make later design decisions
concrete. It is **not** an implementation plan, and no mapping below has been
tested.

### 14.1 Where the two formats agree

| Concept | Moho | Lottie | Assessment |
|---|---|---|---|
| Container | JSON document | JSON document | direct |
| Sparse keyframes per property | `Channel` — `{"when": [...], "val": [...]}` | `property` — `{"a": 1, "k": [keyframes]}` | same idea, different layout: Moho holds parallel arrays, Lottie holds an array of objects |
| Frame-based time | frame numbers | frame numbers, real-valued | direct |
| Cubic Bezier paths | reconstructed by `BezierReconstructor` into explicit control points | `values/bezier` with `v` / `i` / `o` | close — see § 14.2 |
| Layer tree with transforms | nested layers | flat list plus `parent` by `ind` | same semantics, different encoding |
| Fill and stroke styles | `StyleTable` / `ResolvedStyle` | `fl` / `st` / `gf` / `gs` | direct for the common cases |
| Gradients | linear and radial | `gradient-type` 1/2/3 | Lottie also has conic |
| Layer opacity | channel | `ks.o` | direct |
| Masking, two fields | `group_mask` + per-child `masking` | `tt` / `tp` / `td`, plus `masksProperties` | analogous in spirit, different in mechanism |

### 14.2 The Bezier representation

Both formats end up describing cubic Beziers with **relative** tangents, which
is a genuine convenience. Lottie's schema says the `i` and `o` points are
"relative to the corresponding `v`" [confirmed]; `moho2svg.py`'s
`BezierReconstructor` produces explicit control points from Moho's
smoothness / weight / offset encoding.

The difference is where the work is. Moho stores an *implicit* curve that must
be reconstructed with an empirically-fitted formula — the module docstring in
`moho2svg.py` documents why. Lottie stores the control points directly. So
**Moho → Lottie is a lossy-but-computable direction** (reconstruct, then
write), while **Lottie → Moho would be the hard direction** (invert an
empirical fit). Only the first direction is relevant to this repository.

One structural difference to watch: Moho's shape `edges` list is an unordered
set that `PathTracer` must re-trace into loops (see
[`moho-export-pipeline.md`](moho-export-pipeline.md) § 6). Lottie's
`values/bezier` is already an ordered vertex list with a `c` closed flag. So
the tracing step produces exactly the ordering Lottie wants — that work is
already done. [inferred]

### 14.3 Where they diverge

| Moho concept | Nearest Lottie concept | Gap |
|---|---|---|
| Bones and skinning (rigid and flexible binding) | **none** | Lottie has no skeleton. Bone deformation must be **baked** into vertex positions per frame. See [`moho-rigging-and-deformation.md`](moho-rigging-and-deformation.md). |
| Smart Bones (a dial bone selecting a pose by inverting a pose curve) | none | must be evaluated and baked |
| `combo_mode` boolean shape combination | `shapes/merge` (`mm`: 1 normal, 2 add, 3 subtract, 4 intersect, 5 exclude) | the enums look comparable, but Moho's `combo_mode` 2 is [documented as unresolved](moho-project-file-format.md) and Lottie's merge support is famously uneven across players |
| Brush textures (stamped dabs, `.mohobrush` archives) | none | Lottie has no textured stroke. The existing raster paths would have to become image assets, or the detail is lost |
| Tapered strokes (Moho falls back to filled outline geometry) | none | same fallback would apply: emit the outline as a filled path |
| Switch layers (discrete choice of active child) | none directly | expressible as layer `ip`/`op` visibility windows [inferred] |
| `PatchLayer` (reuses another layer's mesh at a different draw position) | none | Lottie has no aliasing; the geometry would be duplicated |
| Coordinate system: 2 units span canvas height, y up | pixels, y down, origin top-left | a fixed linear map, already written out in [`moho-project-file-format.md`](moho-project-file-format.md) § 4 |
| Angles in radians | degrees (`r`, `sk`, `sa` are all "in degrees") | unit conversion |
| Colours 0..1 in channels, 0..255 in some plain fields | 0..1 arrays, except `solid-layer.sc` which is `#RRGGBB` | both formats are internally inconsistent, in different places |

### 14.4 The honest summary of Moho → Lottie

Everything Moho does that Lottie cannot express — bones, Smart Bones, brush
textures, patch layers — has the same workaround: **bake it at a chosen
frame**. That produces a correct still, and an animation only if you bake every
frame, which defeats the purpose of an animation format.

So a faithful Moho → Lottie *animation* export is a much larger project than a
Moho → Lottie *single frame* export, and the difference is not effort — it is
whether the rig survives the trip. It does not. [inferred, but it follows
directly from Lottie having no skeleton concept]

---

## 15. Known gaps and open questions

Ordered by how much they would affect the planned feature.

1. **Raster or vector output?** Unresolved, and it selects the entire
   architecture (§ 13.7). Everything else depends on this.
2. **Can a Lottie-loaded ThorVG scene be walked and read back?** (§ 10.5) If
   yes, Option D removes most of the work in Option E. This is untested, it is
   cheap to test, and it is the highest-value experiment named in this
   document. Sub-questions: does a `Picture` expose its children to the
   Accessor; is the geometry local or composed; what happens to text.
3. **Whose frame numbering does a `--frame` flag use** — the document's
   (`ip`-relative) or ThorVG's (0-based)? These differ whenever `ip != 0`
   (§ 12.2).
4. **`st` and `sr` composition order is not defined by the schema** (§ 8.3).
   The conventional formula is stated there as an inference and must be
   verified against a renderer before any evaluator relies on it.
5. **Precomp time remap units.** The schema says `tm` maps "frame index → time
   in seconds", which is a unit change from everything around it (§ 8.3). Worth
   confirming against a player.
6. **Shape element ordering rules are not in the schema** (§ 6.4). "Style
   applies to neighbouring shapes" is not a machine-checkable statement. Any
   Lottie writer we build needs a renderer to check against.
7. **`thorvg-python`'s licence.** PyPI metadata reports LGPL-2.1 while ThorVG
   is MIT (§ 13.1). Not verified against the repository's own LICENSE file.
   Must be settled before adopting it.
8. **ThorVG's actual Lottie coverage is unquantified here.** The claim of
   "extensive support" is the project's own [reported]. No feature-by-feature
   audit was done, and effects, layer styles, and text are the usual weak
   spots in every player.
9. **Nothing in this document was executed.** No Lottie file was rendered, no
   ThorVG build was made, no Python package was installed. Sections 2 to 8 are
   verifiable against files in this repository; sections 9 to 13 are
   verifiable against sources quoted by URL; section 14 is analysis.

---

## 16. Reproducing the schema figures

Every count and field table in sections 2 to 8 can be regenerated. The
following runs against the schema copy in this repository and needs no
third-party package.

Run each from the repository root. The heredoc form avoids shell escaping of
`$defs`.

```bash
# Module and definition counts (§ 2.2)
python3 - <<'EOF'
import json
d = json.load(open('lottie/lottie.schema.json'))['$defs']
print('modules:', len(d), 'defs:', sum(len(v) for v in d.values()))
for k, v in d.items():
    print(f'  {k:15} {len(v):3}')
EOF
```

```bash
# Enumeration values (§ 5, § 6)
python3 - <<'EOF'
import json
c = json.load(open('lottie/lottie.schema.json'))['$defs']['constants']
for k, v in c.items():
    vals = ', '.join(f"{o.get('const')!r}={o.get('title')}" for o in v.get('oneOf', []))
    print(f'{k}: {vals}')
EOF
```

```bash
# Bundled vs split equivalence (§ 1.1, § 2.4)
python3 - <<'EOF'
import json, re
b = json.load(open('lottie/lottie.schema.json'))['$defs']

def norm(o):
    """Drop per-file $schema/$id and rewrite split-tree $ref URLs to bundle form."""
    if isinstance(o, dict):
        return {k: (re.sub(r'^.*#/\$defs/', '#/$defs/', v)
                    if k == '$ref' and isinstance(v, str) else norm(v))
                for k, v in o.items() if k not in ('$schema', '$id')}
    if isinstance(o, list):
        return [norm(x) for x in o]
    return o

same = diff = 0
for mod, items in b.items():
    for name, node in items.items():
        s = json.load(open(f'lottie/schema/{mod}/{name}.json'))
        if norm(s) == norm(node):
            same += 1
        else:
            diff += 1
            print('differs:', mod, name)
print('identical:', same, 'differing:', diff)
EOF
```

Expected output of the last one: `differs: layers unknown-layer`,
`differs: shapes unknown-shape`, `identical: 157 differing: 2`. [confirmed —
this is the run the § 1.1 and § 2.4 figures come from]

The ThorVG figures in sections 9 and 10 can be re-checked by downloading the
files named in § 1.3 from the `thorvg/thorvg` repository at `main` and reading
them directly; every signature quoted here appears verbatim in
`src/bindings/capi/thorvg_capi.h`.
