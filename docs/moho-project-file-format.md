# Moho Project File Format

A Moho project file (`.mohoproj` for Moho Pro, `.animeproj` for Moho Debut)
is plain JSON, despite the extension. The format is **not officially
documented** by Smith Micro; everything below was reverse-engineered by
`moho2svg.py`'s author, by empirically comparing this tool's output against
SVG files Moho itself exported ("File > Export Animation"), across several
rigs and two Moho versions (14.3 and 14.4).

This document is a readable summary of that reverse-engineering. **The
authoritative source is the module docstring at the top of `moho2svg.py`**,
which additionally records, for each formula and constant, *how* it was
derived and *what evidence* supports it (sample sizes, error margins, which
parts are confirmed-exact versus best-fit heuristics). Read that docstring
before changing any of the logic this document describes — several things
that look like bugs are intentionally preserved because they match real Moho
output.

## 1. Top-level structure

```jsonc
{
  "version": "...",
  "project_data": { "width": 1920, "height": 1080, ... },
  "styles": [ { "type": "Style", "name": "...", "uuid": "...", ... }, ... ],
  "layers": [ { "type": "BoneLayer", "name": "...", "layers": [...], ... }, ... ]
}
```

- `project_data.width` / `.height` — canvas size in pixels.
- `styles` — a document-wide list of *named* brush/line styles. A shape can
  inherit its colours, line width, and brush from one of these instead of
  (or layered on top of) its own values. See [§ 6](#6-styles-and-inheritance).
- `layers` — the document's layer tree (see [§ 2](#2-layers)).

## 2. Layers

Each layer is a JSON object with a `type` field naming its kind:

| `type` | Meaning |
|---|---|
| `MeshLayer` | Vector artwork (points/curves/shapes) — the only layer kind that actually draws pixels. |
| `BoneLayer` | A skeleton (list of bones) plus child layers deformed by it. |
| `GroupLayer` | Children with no skeleton. |
| `SwitchLayer` | Children are alternatives; only one is shown at a time (`switch_keys`, an animated string channel naming the active child). |
| `TextLayer` | A caption. Moho keeps its rasterised-to-vector glyphs in a nested `mesh_layer` field. |
| anything else | E.g. `PatchLayer`, seen in real files but not modelled — see the module docstring's KNOWN GAPS. |

Common fields on every layer:

- `name`, `visible` (bool), `edit_only` (bool — kept for editing convenience, never rendered).
- `layers` — child layers, if this layer is a container. A layer can have
  no mesh AND no `layers` key at all (e.g. `PatchLayer`) — Moho draws
  nothing at all for it, not even an empty group.
- `transforms` — the layer's own local transform: `translation`, `scale`,
  `rotation_z`, `flip_h`, `flip_v` (all channels — see
  [§ 4](#4-animated-values-channels)). Rotation and scale pivot on `origin`,
  not the layer's local `(0, 0)`.
- `origin` — `{"x":.., "y":..}`, the pivot point for the transform above.
- `parent_bone` — index into an ancestor `BoneLayer`'s `skeleton.bones`, or
  `-1`. `-1` means *flexible* ("region") binding across the whole skeleton
  (or a named subset, `flexi_bone_subset`); a non-negative index means
  *rigid* binding to that one bone. See [§ 7](#7-bones-and-skinning).
- `masking` / `group_mask` — see [§ 9](#9-masking).
- `actions` — only meaningful on a `BoneLayer`: a name registry for Smart
  Bone dials. See [§ 10](#10-smart-bones).

## 3. Coordinates

Points, translations, bone positions, etc. are stored in a document-space
unit where **2 units span the canvas height** — i.e. `y = +1` is the top
edge, `y = -1` is the bottom edge, regardless of the pixel resolution:

```
pixel_x = moho_x * (height / 2) + width / 2
pixel_y = height / 2 - moho_y * (height / 2)        # y is flipped
```

## 4. Animated values (channels)

Almost every numeric/colour/string property in Moho is stored the same way:

```jsonc
{
  "when": [0, 12, 24],           // keyframe frame numbers
  "val":  [0.0, 1.0, 0.5],       // one value per keyframe (linear interpolation)
  "interp": [...],               // present but unused by this tool
  "actions": [ { "name": "EyeBlink", "pose": { "when": [...], "val": [...] } } ]
}
```

A field that is never animated is sometimes stored as a bare scalar or plain
dict instead of this structure (both forms are accepted transparently). See
`actions` in [§ 10](#10-smart-bones) for what a channel-level `actions` entry
means.

## 5. Mesh model: points, curves, shapes

A `MeshLayer`'s `mesh` has three parallel structures:

- `points` — every point used by the mesh, each with an animated
  `position` (`{"x":.., "y":..}` channel) and an animated `width` channel
  (normally `1.0`; see [§ 5.2](#52-stroke-width) and
  [§ 5.3](#53-tapered-strokes)).
- `curves` — each a sequence of *curve points*, each referencing one mesh
  point by index (`"point"`) plus curvature data (below). A curve is
  `closed` (one segment per point, last wraps to first) or open (one fewer
  segment than points).
- `shapes` — each a filled/stroked region, referencing a set of curve
  segments via `edges` (parallel arrays `curve`/`segment`/`flag`), plus
  `has_fill`, `has_outline`, `combo_mode` (see
  [§ 5.4](#54-boolean-shape-combination)), and its own `style` (see
  [§ 6](#6-styles-and-inheritance)).

### 5.1 Bezier reconstruction

A curve point does not store explicit Bezier control points. Instead, each
stores:

- `smoothness` — curvature; `0` = sharp corner (handles collapse onto the
  point).
- `weight_in` / `weight_out` — how far each handle reaches toward its
  neighbour, as a fraction of the distance to that neighbour.
- `offset_in` / `offset_out` — a small rotation (radians) for asymmetric
  curves.

Handle **length** is `distance_to_neighbour * smoothness * weight` (confirmed
exact against 209 reference handles). Handle **direction** is *not* simply
`normalize(next - prev)` — it is a chord-length-weighted blend of the two
neighbouring chord vectors (see the module docstring's BEZIER CURVES section
for the exact formula and its empirical derivation).

### 5.2 Stroke width

Two independent, non-pixel quantities scale a stroke:

- `line_width` — a per-shape/style channel (a handful of quantised values
  per document).
- point `width` — normally `1.0`, but can vary (see § 5.3).

```
stroke_px = line_width * point_width * canvas_height * layer_chain_scale
```

`layer_chain_scale` is the accumulated ancestor scale, **excluding** bone
deformation (confirmed: including it inflates the apparent scale by ~11% on
a walk cycle).

### 5.3 Tapered strokes

Where a shape's points do not all share one `width`, Moho's own exporter
does not use a variable `<path stroke-width>` (SVG cannot express one) — it
walks the stroke and emits the literal filled outline instead (visible as
dozens of tiny filled paths for something like a bushy tail). See the module
docstring's TAPERED STROKES section.

### 5.4 Boolean shape combination

A shape's `combo_mode` says how it combines with the shape(s) immediately
before it in the same layer:

| `combo_mode` | Meaning |
|---|---|
| `0` | Normal — starts a new independent boolean group. |
| `1` | Union — merged into the current group; the shared boundary disappears, and the *combined* outline is stroked using the group's first (base) member's styling, not its own. |
| `3` | Intersect — clipped to the union of the group's solid members so far. |
| `2` | Observed in real files, effect not reverse-engineered. |

### 5.5 Why `edges`/`shape_order` are not trustworthy as-is

A shape's `edges` list is not reliably a walk in list order, and its `flag`
is not a reliable direction bit — real files exist where segment order is
strictly descending with `flag` 0 throughout, and where a curve's segments
are listed out of walk order. `edges` must be treated as an *unordered set*
of segments and re-traced as an undirected graph. The document-level
`shape_order` string field is similarly misleading — it is only an ascending
ID registry, not a z-order; the real z-order (back to front) is simply the
order shapes already appear in `mesh.shapes`.

## 6. Styles and inheritance

`styles` (top-level) is a list of named style objects:

```jsonc
{
  "type": "Style", "name": "yanak", "uuid": "...",
  "define_fill_color": true,  "fill_color": { ... channel ... },
  "define_line_width": true,  "line_width": 0.0056,
  "define_line_col": true,    "line_color": { ... channel ... },
  "line_caps": 1,
  "brush_name": "Brush502.png", "brush_jitter": 6.283185, "brush_spacing": 0.25,
  "brush_align": false, "brush_tint": true, ...,
  "fill_style": { "type": "SS_Gradient2", "gradient_type": 1, "gradients": [...] }
}
```

A shape's own `style` object has the same shape, plus (on either the shape
itself or inside its own `style` object — both are observed in real files)
`inherited_style_uuid` / `inherited_style_name` /
`inherited_style2_uuid` / `inherited_style2_name`, referencing an entry in
the document's `styles` list by UUID or name.

Resolution rule: for each `define_X` flag that is **true on the named style**
and **false on the shape's own style**, the named style's value for `X`
overrides the shape's own. Style 1 is applied before style 2, so style 2
wins where both define the same attribute (this is how an outline-only
"line style" can be layered on top of a base fill style). Two real-world
generations of documents differ in how they use this:

- **Older documents** (format 1038 and similar) leave every `define_*` flag
  false on the shape itself and keep the real values in a named style.
- **Newer documents** put real values directly on the shape and leave
  `inherited_style*` empty — in this case the "resolved" style is simply the
  shape's own values.

`fill_style` (a gradient spec) lives *only* on a named style, never inline
on a shape — a shape opts into a gradient fill by leaving
`define_fill_color` false and inheriting a style whose `fill_style.type`
is `"SS_Gradient2"`. `gradient_type` `0` is linear, `1` is radial. Gradient
placement (centre/radius) is approximate, not pixel-matched to Moho's own
(differently parameterised) placement.

## 7. Bones and skinning

A `BoneLayer`'s `skeleton.bones` is a flat list; each bone has `name`,
`parent` (index into the same list, or `-1` for root), `length`, `strength`,
and animated `anim_pos` / `anim_angle` / `anim_scale`.

A bone's world transform composes with its parent's (parents resolved
regardless of list order). Deformation of a mesh layer is one of two modes,
decided **per layer**:

- **Rigid** (`parent_bone >= 0`): every point moves exactly as that one bone
  does.
- **Flexible / region** (`parent_bone == -1`): every point is a
  distance-weighted blend of every bone's (or a named subset's,
  `flexi_bone_subset`) transform. The weight falloff shape (inverse-distance-
  squared by default) is a heuristic, unvalidated for cases where more than
  one bone has significant influence near a given point.

A mesh several groups deep inside a `BoneLayer` is deformed in *that bone
layer's own coordinate space* — i.e. after the local transforms of
everything between it and the bone layer, but before the bone layer's own
transform.

## 8. Brush styles

A named style's line can be a textured "brush" — a small image stamped
repeatedly along the path (jittered in rotation, spaced as a fraction of its
own size) instead of a plain uniform-width line. The relevant style fields:

- `brush_name` — identifies the brush asset (see [§ 8.1](#81-resolving-a-brush_name-to-a-file)).
- `brush_jitter` — random rotation spread, in **radians**, applied per dab.
- `brush_spacing` — dab spacing, as a **fraction of the dab's own diameter**.
- `brush_align` — whether each dab rotates to the local path tangent (in
  addition to the random jitter) or ignores path direction entirely.
- `brush_tint` — whether the (greyscale) texture is recoloured to the
  resolved `line_color`, or used with its own native multi-colour pixels
  as-is.
- `brush_randomize`, `brush_merged_alpha`, `brush_rand_order`,
  `brush_angle_drift` — read by this tool but not currently used when
  rendering (see the module docstring's KNOWN GAPS).

### 8.1 Resolving a `brush_name` to a file

Moho ships its own brush assets as files (installed alongside the
application, not inside any project file). A brush asset takes one of three
shapes on disk:

1. **A single PNG** named exactly after the brush (`Brush502.png`).
2. **A multi-frame brush**: a *folder* named exactly after the brush,
   containing several PNG frames (e.g. `CK Ink Painty Brush/Painty
   Brush_00001.png` … `_00012.png`), with a sibling `<name>.mohobrush` file.

   Despite the extension, a `.mohobrush` file is a **ZIP archive**, not an
   image or a bespoke binary format — confirmed by extracting and parsing
   all 101 shipped with a real Moho install, zero exceptions. It contains
   exactly one member, `brush.json`, a plain JSON object with the brush
   library's own default parameters: `version`, `align`, `jitter`,
   `spacing`, `angleDrift`, `randomize`, `randomOrder`, `mergedAlpha`,
   `sizeVariationAmp`, `sizeVariationScale`, `randomInterval`, `brushFiles`
   (a list of `{"brushFileRef": {"relativeTo": "Project", "path": "<asset
   name>"}}` — an authoritative pointer to the actual PNG/folder asset,
   an alternative to guessing it from the name as § 8.1 does), and
   sometimes `hueDrift`/`satDrift`/`valDrift`. This tool currently reads
   only `randomOrder`/`randomInterval` from it (whether each dab in a
   stroke picks a uniformly-random frame from the folder, or cycles
   through them in sorted-file-name order, advancing every
   `randomInterval` dabs) — see `Exporter._brush_library_defaults`.
3. **A preset image one folder deep** — some older documents' `brush_name`
   values only resolve to a file living inside another brush's own folder
   (e.g. `Brush549_1_50_50.png` exists on disk only as
   `Brush004/Brush549_1_50_50.png`).

Additionally, **older Moho versions bake preset parameters into the
`brush_name` string itself** as a trailing `_N_N_...` numeric suffix — the
literal file on disk does not include the suffix. For example
`Brush567_0_20_50.png` names the file `Brush567.png`; `CK Ink
Natural_2_1_0_0_0_0_0_0_0` names the folder `CK Ink Natural`. Resolving a
`brush_name` therefore means trying, in order: the exact name as a file,
the exact name as a folder, a recursive search for the exact filename one or
more folders deep, and then the same three searches again after stripping
one trailing `_<digits>` group at a time from the name (re-appending a
stripped `.png` extension where relevant) until something matches.

Across every suffixed style seen so far, the **second and third** numbers of
the suffix consistently match that style's own `brush_jitter` (in degrees)
and `brush_spacing` (as a percent) — i.e. they are redundant with fields the
style already carries explicitly, and this tool reads the explicit fields,
not the suffix, for actual rendering. The suffix is used only to *locate*
the asset file. The **first** number's meaning differs by brush family (it
lines up with the align flag for the `Brush5xx` preset family, but not
consistently for others) and is not decoded.

## 9. Masking

Two *separate* fields are involved:

- `group_mask` on a *container* (`GroupLayer` or `BoneLayer` — the layer
  type does not matter). `0`/falsy = this container does not mask its
  children at all; non-zero = masking is active.
- `masking` on each *child* of a masking container:
  - `2` — this child's geometry defines the mask (Moho's UI: something like
    "Add to Mask"). It is still drawn normally — being the mask source does
    not hide it.
  - `1` — "don't mask this layer" (Moho's UI: e.g. an exemption toggle) —
    drawn normally, ignoring the mask entirely.
  - anything else (typically `0`, Moho's UI default, e.g. "Mask This
    Layer") — clipped to the union of all `masking == 2` siblings in the
    same container.

This applies uniformly at every nesting depth, **including the document's
own top-level layer** — masking is not special-cased away at the root. A
`masking == 2` sibling does not always carry its own mesh: a `GroupLayer`
can be `masking == 2` purely as a masking *container*, in which case its
effective silhouette is, recursively, whatever its own `masking == 2`
child/children define (the same shapes that already act as *that*
container's internal `group_mask` source).

## 10. Smart Bones

A "Smart Bone" is an ordinary bone used as a *dial*: its own rotation angle
selects a pose (an "action") for the rest of the rig.

- The bone layer has an `actions` list at its own level — a name registry,
  e.g. `[{"name": "EyeBlink"}]`.
- A bone counts as a dial if its own *name* matches one of those action
  names.
- Any channel anywhere under that bone layer can carry its own nested
  `actions: [{"name": "EyeBlink", "pose": <channel>}]`. When dial
  `EyeBlink` is active, such a channel is read from the `pose` sub-channel
  instead of its own `when`/`val`, at a frame found by inverting the pose
  curve: the pose channel's own `val` array records what the dial's *own*
  angle was at each of the pose's keyframes, so "the pose frame whose
  recorded angle matches the dial's current actual angle" is well-defined by
  interpolation.
- Moho stores *two* actions per dial, one per rotation direction (the
  second suffixed `" 2"`), because a pose curve must be roughly monotonic to
  invert.
- A dial's own *current* angle is always its literal position on the main
  timeline — resolving it must not recurse into the same override mechanism
  it is itself part of.

## 11. Known unknowns

This is a living reverse-engineering effort, not a specification. See the
module docstring's KNOWN GAPS section for the current list, including:
`combo_mode 2`, precise gradient placement, the flexible bone-weight-falloff
shape for overlapping influence, `PatchLayer`, and the several brush-style
simplifications noted in [§ 8](#8-brush-styles). If you find a real document
that contradicts something in this document, prefer the evidence in the
document over what is written here.
