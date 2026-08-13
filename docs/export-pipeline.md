# How a Moho Document Becomes SVG

This document explains the **processing logic** of `moho2svg.py`: which stage
consumes which field, in what order decisions are made, and how the pieces of
a Moho document combine into SVG output.

It is the companion to two other documents, and deliberately does not repeat
either:

| Document | Answers |
|---|---|
| `docs/moho-project-file-format.md` | *What* is in the file — every field, its values, whether it is used. |
| **this file** | *How* those fields are consumed, and in what order. |
| The module docstring in `moho2svg.py` | *Why* each formula/constant is what it is, and what evidence supports it. |

Every class, function, and attribute named below exists in `moho2svg.py`. When
a formula is only summarised here, the module docstring section that derives it
is named so you can go straight there.

---

## 1. Overview: the data flow

Two entry points exist, and they share every stage below them:

- `Exporter.export_layer(...)` — one vector layer to a standalone SVG
  (CLI `--layer`, `--all`).
- `Exporter.export_document(...)` — the whole layer tree to one SVG
  (CLI `--combined`).

```
                      .mohoproj / .animeproj  (plain JSON)
                                  |
                        load_document(path)                    [CLI]
                                  |
                        Document.from_raw(raw)                 LOAD TIME
                                  |                            (frame-independent)
              +-------------------+-------------------+
              |                                       |
      StyleTable.build(raw["styles"])          Layer._build  (recursive)
              |                                       |
              |                           +-----------+-----------+
              |                           |                       |
              |                     Mesh._build             Skeleton._build
              |                           |
              |              +------------+------------+
              |              |            |            |
              |       MeshPoint._build  Curve._build  Shape._build
              |                                         |
              +---------> ResolvedStyle.resolve <-------+
                          (style inheritance is
                           resolved ONCE, here)
                                  |
                    Document._resolve_patch_layers()
                    (PatchLayer borrows its target's mesh)
                                  |
        ==========================|==========================  frame boundary
                                  |
                        Exporter.export_document(frame)         RENDER TIME
                                  |                             (per frame)
                        emit()  -- walks the tree
                                  |
        +-------------------------+-------------------------+
        |                         |                         |
  _active_smart_bones      build_deform_chain          _mask_sources
  (which dials are on)     (MatrixStep / SkinStep)     (masking==2 siblings)
        |                         |                         |
        |                 _deformed_pixel_mapper            |
        |                 (uses Skinner.deform)             |
        |                         |                         |
        +----------> _render_mesh(mesh, to_px, frame) <-----+
                                  |
                    _curve_geometries(mesh, frame)
                    (BezierReconstructor -> CurveGeometry)
                                  |
                    ShapeGroupRenderer.render()
                                  |
                    per shape: build_path_d
                               (PathTracer re-traces edges)
                               + TaperedStrokeOutliner
                               | or BrushStampOutliner
                                  |
                    _flush()  -- boolean groups close here
                                  |
                          Exporter._wrap()
                       (<svg>, viewBox, <defs>)
                                  |
                              SVG text
```

The **frame boundary** in the middle is the single most useful thing to
remember. Everything above it happens once per file load and never depends on
a frame number. Everything below it is redone for every `--frame N`.

What is *not* in the pipeline is equally important: there is no z-sorting
stage, no layer-effect stage, and no camera stage. Draw order is simply
document order, and the ignored fields listed in
`moho-project-file-format.md` § 13 are ignored by *omission* — no code reads
them.

---

## 2. The object graph: what points at what

The document model is a set of **thin accessors over the raw parsed JSON**.
Almost every property is a one-line `self._raw.get(...)`; nothing is copied.
This matters for two reasons: memory (a 55 MB document is not duplicated), and
`Channel.of()`'s identity cache (see [§ 5.1](#51-channelof-and-the-identity-cache)).

### 2.1 Structural containment

```
Document
  .styles ....... StyleTable  (indexed by BOTH uuid and name)
  .layers ....... [Layer]                     <- root layers, draw order
                    |
                    +-- .children ... [Layer]   <- recursive
                    +-- .mesh ....... Mesh?
                    |                   +-- .points .. [MeshPoint]
                    |                   +-- .curves .. [Curve]
                    |                   |                +-- .points .. [CurvePoint]
                    |                   +-- .shapes .. [Shape]
                    |                                    +-- .edges ... [Edge]
                    |                                    +-- .style ... ResolvedStyle
                    +-- .skeleton ... Skeleton?
                                        +-- .bones .. [Bone]
```

### 2.2 Reference keys ("foreign keys")

These are the cross-references that make the format a graph rather than a
tree. Getting them wrong is the most common source of silently wrong output.

| From | Field | To | Resolved by |
|---|---|---|---|
| `Edge` | `curve` | index into `mesh.curves` | `PathTracer.trace`, `_point_widths` |
| `Edge` | `segment` | index into `curve.points` / that curve's segment list | same |
| `CurvePoint` | `point` (`point_index`) | index into `mesh.points` | `CurveGeometry.build`, `_point_widths` |
| `MeshPoint` | `curves` | indices back into `mesh.curves` | **not used** — the reverse mapping is rebuilt from `curves` instead |
| shape / shape's style | `inherited_style_uuid` / `_name`, `inherited_style2_*` | an entry of `doc.styles` | `ResolvedStyle.resolve` via `StyleTable.get` |
| `Layer` | `parent_bone` | index into the enclosing `BoneLayer`'s `skeleton.bones` | `build_deform_chain` → `SkinStep.bound_bone_index` |
| `Layer` | `flexi_bone_subset` | `"\|"`-joined **indices** into `skeleton.bones` | `Layer.flexi_bone_subset` → `Skinner.deform` |
| `Bone` | `parent` | index into the same `skeleton.bones` | `Skeleton.world_matrices` |
| `PatchLayer` | `target_layer_uuid` | another `Layer.uuid`, anywhere in the document | `Document._resolve_patch_layers` |
| `SwitchLayer` | `switch_keys` (value) | a **child layer name** (a string, not an index) | `Layer.switch_active_child` |
| channel | `actions[].name` | an action name in some ancestor `BoneLayer`'s `actions` registry | `Channel.eval` ↔ `Exporter._active_smart_bones` |

Two of these deserve a warning.

**`Edge` is a set, not a sequence.** `edges` (the parallel `curve` / `segment`
/ `flag` arrays) is *not* a walk in list order, and `flag` is *not* a reliable
direction bit. `PathTracer` therefore ignores both order and `flag`, and
re-traces the outline as an undirected graph keyed by rounded endpoint
coordinates. See [§ 6.2](#62-pathtracer-rebuilding-the-walk-order).

**`switch_keys` can be stale.** It stores a *name*, so renaming a child breaks
the reference. `Layer.switch_active_child` falls back to the **first** child
rather than drawing nothing, which matches what Moho itself does (confirmed
against a real document where a "Mouth" switch named `"Layer 2"` as active
while its only child was named `"Closed"`).

### 2.3 Two load-time rewrites

`Document.from_raw` does not hand the tree over unchanged. Two normalisations
happen first, and both exist so that no later stage needs a special case:

1. **`TextLayer` gets a synthesised child.** `Layer._build` turns a
   `TextLayer`'s nested `mesh_layer` object into an ordinary `MeshLayer`
   child (named `<layer>_text` if it has no name of its own). After this,
   nothing downstream special-cases `TextLayer` at all.
2. **`PatchLayer` borrows its target's mesh.** `Document._resolve_patch_layers`
   runs *after* the whole tree exists, because a target can be anywhere in the
   document. It copies four things from target to patch — `mesh`, `transform`,
   `parent_bone`, `flexi_bone_subset`, and `origin` — and deliberately
   **discards the patch's own** transform/binding. The loop repeats until
   nothing new resolves, so a patch whose target is itself a patch also works.
   A patch that never resolves keeps `mesh = None`, which every later stage
   already treats as "draws nothing".

   The patch and its target end up sharing the exact same `Mesh`/`Shape`
   Python objects (not copies) — `layer.mesh = target.mesh`. That matters at
   render time: a patch draws only its target's **fill**, never its outline,
   confirmed directly against the Moho app on two points chosen to rule out a
   confound (`masking == 2` and `masking == 0`, both patches, neither shows a
   stroke while their targets do — see
   [§ 7.6](#76-patchlayer-suppresses-its-outline-not-just-its-transform)).
   Because the objects are shared, this cannot be done by flipping
   `Shape.has_outline` (that would also silence the target's own,
   independent, render pass) — it is a render-time flag instead.

`Layer.is_container` is tracked separately from `children` being empty,
precisely to keep these two cases apart:

| Case | `mesh` | `is_container` | Result |
|---|---|---|---|
| `GroupLayer` with no children | `None` | `True` | an **empty `<g>`** is emitted (matches Moho) |
| unresolved `PatchLayer` | `None` | `False` | **nothing** is emitted, not even a `<g>` |

---

## 3. Walking the layer tree: the decision order

`Exporter.export_document` contains a nested `emit()` function that recurses
over the tree. The order of its checks is behaviour, not style — several
decisions depend on happening exactly where they do.

```
emit(layers, world, depth, container, ancestors):

  (A) MASK FIRST, once per container
      sources = _mask_sources(container, ancestors, frame)
      if sources: emit <mask id=...>, remember clip="mask=url(#...)"
      |
      NOTE: this runs while _active_actions is EMPTY. See § 9.3.

  (B) SwitchLayer: resolve the one active child, once
      if container is a SWITCH: active_child = container.switch_active_child(frame)

  (C) for each layer in layers:          <- file order == draw order
        |
        +-- skip if not layer.visible          and not --include-hidden
        +-- skip if layer.edit_only            and not --include-hidden
        +-- skip if active_child is set and layer is not active_child
        |
        +-- world_here = world x layer.local_matrix(frame)
        |                (accumulated for STROKE WIDTH only - see § 4.3)
        |
        +-- member_clip = "" if layer.masking in (1, 2) else clip
        |                 (mask sources and exempt layers draw unclipped)
        |
        +-- if layer.mesh is not None:      ---> DRAW  (§ 3.1)
        |
        +-- elif layer.is_container:        ---> RECURSE
        |        emit(layer.children, world_here, depth+1, layer, ancestors+(layer,))
        |
        +-- else:                          ---> nothing at all
```

Three things to note about this order:

- **The mask is built before any child is examined**, and it is built once for
  the whole container, not once per child. `clip` is then applied selectively
  per child via `member_clip`.
- **A layer is either a mesh or a container, never both.** The `if / elif`
  means a hypothetical layer carrying both would render its mesh and never
  recurse. No such layer exists in any sample.
- **`visible` and `edit_only` are checked before anything expensive.** Both are
  overridden by `--include-hidden` together.

### 3.1 The per-mesh-layer sequence

When `emit()` decides to draw, this exact sequence runs — and the two
assignments to `self._active_actions` bracket it:

```
self._active_actions = _active_actions_along(ancestors, frame)   # set
self._layer_scale    = world_here.uniform_scale() or 1.0
chain                = build_deform_chain(ancestors, layer, frame, self)
to_px                = _deformed_pixel_mapper(chain, frame, layer)
body, pts            = _render_mesh(layer.mesh, to_px, frame, indent)
self._active_actions = []                                        # clear
```

`export_layer` does the same thing for a single layer, with two differences:
`--local` replaces the whole deform chain with `_plain_pixel_mapper(IDENTITY)`,
and the mask is computed *after* `_active_actions` is cleared (which is where
the quirk in [§ 9.3](#93-the-empty-smart-bone-context-quirk) comes from).

### 3.2 `--flat` (`nested_groups=False`)

`--flat` suppresses the per-layer `<g>` wrapper — but **only when there is no
mask to attach**. The condition is `if nested_groups or member_clip`. A masked
layer always keeps its `<g>`, because that is what carries the `mask=` attribute.

---

## 4. Transforms and coordinate spaces

This is where most of the subtlety lives. There are **two independent
traversals** of the same ancestor chain, computing two different things, and
they deliberately do not agree.

### 4.1 A layer's own local matrix

`Layer.local_matrix(frame, exporter)` maps a point from the layer's own space
into its parent's space. Rotation and scale pivot on `origin`, not on `(0,0)`:

```
p' = origin + translation + R(rotation_z) * S(scale_x, scale_y) * (p - origin)
```

`flip_h` / `flip_v` negate `scale_x` / `scale_y`. Note that layer scale is
genuinely **per-axis**, whereas a bone's `anim_scale` is a single scalar — see
[§ 4.4](#44-bone-world-matrices).

### 4.2 The deform chain (geometry)

`build_deform_chain(ancestors, target, frame, exporter)` returns an ordered
list of steps in **application order**: apply `steps[0]` to the raw mesh
point, then `steps[1]`, and so on. Two step kinds exist:

- `MatrixStep(matrix)` — apply a plain affine transform.
- `SkinStep(bone_layer, bound_bone_index)` — deform by that bone layer's
  skeleton.

The chain is built by walking the ancestor chain **in reverse** (innermost
first), accumulating plain matrices into `pending` and flushing them whenever a
deforming `BoneLayer` is crossed:

```
raw mesh point (target's own local space)
      |
      | MatrixStep: every local_matrix between the mesh and the bone layer,
      |             composed together
      v
  BoneLayer's OWN coordinate space          <-- the skeleton's rest/pose
      |                                         matrices live in THIS space
      | SkinStep(bone_layer, bound_bone_index)
      |     bound >= 0 -> rigid:    skinner.bones[bound].rest_to_pose.apply(p)
      |     bound == -1 -> flexible: skinner.deform(p, subset, weight_fn)
      v
  still the BoneLayer's own space (now posed)
      |
      | MatrixStep: the bone layer's own local_matrix, plus everything
      |             above it (repeat for each outer BoneLayer crossed)
      v
  document space
      |
      | Exporter._to_pixel
      v
  pixel space
```

The key insight — and the reason a naive "compose all the matrices" approach
gives wrong results — is that **skinning happens in the bone layer's own
space**: after the local transforms of everything between the mesh and the
bone layer, but *before* the bone layer's own transform. That is the space the
skeleton's matrices are expressed in.

`bound` is carried *up* the reversed walk: as `build_deform_chain` moves
outward, any layer with `parent_bone >= 0` sets `bound`, which is then consumed
by the next `SkinStep` and reset to `-1`. So rigid binding is a property of the
layer chain below a bone layer, not of the bone layer itself.

`Exporter._to_pixel` closes the loop (see `moho-project-file-format.md` § 4):

```
pixel_x = moho_x * (height/2) + width/2
pixel_y = height/2 - moho_y * (height/2)        # y flipped
```

### 4.3 The scale chain (stroke width), and why it differs

Stroke width uses a **completely separate** traversal:
`_full_chain_matrix(ancestors, layer, frame)` in `export_layer`, or the
accumulated `world_here` in `export_document`. Both compose every
`local_matrix` in the chain **including the layer's own**, and both **exclude
bone deformation entirely**.

```
_stroke_width_px(line_width, point_width) =
      line_width
    * point_width
    * settings.stroke_width_scale        # --stroke-mul, default 2.0
    * document.height / 2.0
    * self._layer_scale                  # uniform_scale() of the matrix chain
```

At the default `--stroke-mul 2.0`, `stroke_width_scale * height/2` collapses to
`height`, which is the simplified formula quoted in
`moho-project-file-format.md` § 7.6.

Excluding bone deformation is **deliberate and measured**: including it
inflated the apparent scale by ~11% on a walk-cycle test. See the module
docstring's STROKE WIDTH section.

| | Geometry | Stroke width |
|---|---|---|
| Built by | `build_deform_chain` | `_full_chain_matrix` / `world_here` |
| Includes bone deformation | **yes** | **no** |
| Includes the layer's own transform | yes | yes |
| Output | a list of steps, applied per point | one scalar, `uniform_scale()` |

### 4.4 Bone world matrices

`Skeleton.world_matrices(frame, exporter)` returns one matrix per bone.
Parents are resolved **before** children regardless of list order — the bones
list is not guaranteed to be topologically sorted, so each bone's parent chain
is walked on demand with memoisation.

Each bone's local matrix is:

```
local = Mat2D(cos*scale, sin*scale, -sin, cos, pos.x, pos.y)
                ^^^^^^^  ^^^^^^^^   ^^^^  ^^^
                first column scaled   second column NOT scaled
```

That asymmetry is **preserved on purpose, and flagged rather than fixed**: it
passed every available regression test, but no sample exercises a bone with
`anim_scale` far from `1.0` in a way that could tell asymmetric from uniform
scale apart. Do not "correct" it without new reference evidence. See the
module docstring's KNOWN GAPS.

### 4.5 Skinning: rigid vs flexible

`Skinner.build(skeleton, frame, exporter)` precomputes, per bone, the rest-pose
segment endpoints and `rest_to_pose = pose[i] * rest[i]⁻¹`, where rest is
always evaluated at **frame 0.0**.

`Skinner.deform(p, subset, weight_fn)` then blends:

```
for each bone i in (subset if subset else all bones):
    if bone.strength <= 0:  skip        <- Moho's "this bone does not deform
                                           this mesh" gate, checked FIRST
    w = weight_fn(distance_to_segment(p, rest_p0, rest_p1), bone.strength)
    if w <= 0: skip
    acc   += rest_to_pose.apply(p) * w
    total += w
result = acc / total   (or p unchanged if total == 0)
```

The default falloff is `inv_d2` (`1/d²`), selected by
`RenderSettings.bone_weight_falloff`. Three alternatives (`linear`, `cut_d2`,
`hermite`) are kept in `BONE_WEIGHT_FALLOFFS` because they were tried during
development and **could not be told apart from `inv_d2` by any available
reference** — not because they are known to be equally valid.

---

## 5. Channel evaluation and Smart Bone overrides

### 5.1 `Channel.of` and the identity cache

Every animated field passes through `Channel.of(raw)`, which accepts either a
real channel object or a bare scalar (treated as a single keyframe). Results
are cached **by `id(raw)`**.

That is safe rather than merely lucky, and it depends on the thin-accessor
design: because the document model never copies channel dicts, the same
logical channel is always the same Python object for the life of one
`Document`. Two different channels can never collide, and the cached `Channel`
is immutable. If a future change starts copying raw dicts, this cache becomes
unsound.

### 5.2 The two evaluation entry points

```
Exporter.eval(raw, frame)      -> Channel.of(raw).eval(frame, self._active_actions)
Exporter.eval_raw(raw, frame)  -> Channel.of(raw).eval_raw(frame)
```

`eval_raw` is plain piecewise-linear interpolation, clamped at both ends:

- numbers → linear interpolation
- `{x,y}` / `{x,y,z}` / `{r,g,b,a}` dicts → per-key linear interpolation
- **strings and bools → snap to the left keyframe** (no interpolation)

`interp` is never consulted. So the result is exact *at* keyframes and
approximate between them — see `moho-project-file-format.md` § 5.3.

`eval` first checks the active Smart Bone dials:

```
for active in active_actions:            # priority order, root-first
    pose = channel.action_pose(active.name)
    if pose is not None:
        return pose.eval_raw(active.frame)     # <- action frame, NOT document frame
return channel.eval_raw(frame)
```

**The first match wins**, which is why `active_actions` must already be in
priority order.

### 5.3 How a dial becomes active

`_active_actions_along(ancestors, frame)` calls `_active_smart_bones` for every
`BoneLayer` ancestor, **root-first** — so an outer bone layer's dial outranks
an inner one's if both happen to affect the same channel.

For one bone layer, `_active_smart_bones(bone_layer, frame)` does:

```
names = bone_layer.action_names            # the layer's own actions[] registry
for bone in bone_layer.skeleton.bones:
    if bone.name not in names:  continue   # <- THIS is what makes it a "dial"
    current = Channel.of(bone.anim_angle).eval_raw(frame)   # NOT eval()
    for action in that channel's own actions:
        if action.name not in names: continue
        lo, hi = min(action.pose.val), max(action.pose.val)
        if hi - lo < 1e-9: continue                  # degenerate, unusable
        inside   = lo <= current <= hi
        distance = 0 if inside else min(|current-lo|, |current-hi|)
        key      = (distance, -span)                 # closest first, then widest
    best -> ActiveAction(name, action.pose.frame_for_value(current))
```

Three points that are easy to get wrong:

1. **A bone is a dial only if its own `name` appears in the layer's `actions`
   registry.** Action names that match no bone are plain timeline actions and
   are never activated — see `moho-project-file-format.md` § 11.3.
2. **`eval_raw` is mandatory here.** This is the *only* place in the codebase
   that needs it: resolving a dial's own current angle must not recurse into
   the override machinery the dial is itself part of. Using `eval` would be
   infinite recursion, or at best wrong.
3. **The pose curve is inverted, not sampled.** `frame_for_value(current)`
   asks "which frame of this pose has the dial angle the dial is *actually* at
   now?" — the pose channel's `val` array records the dial's own angle at each
   pose keyframe. This is why Moho stores two actions per dial (the second
   suffixed `" 2"`): a curve must be roughly monotonic to be invertible.

### 5.4 The skinner cache key

`Exporter._skin_data` caches by `(bone_layer, frame, tuple(self._active_actions))`.
The Smart Bone context **must** be part of the key, because an active dial
changes the bones' own `anim_angle` values and therefore the whole pose. Two
mesh layers under the same bone layer at the same frame share a `Skinner` only
if their dial context is identical.

---

## 6. From mesh to path data

### 6.1 Evaluating curve geometry

`Exporter._curve_geometries(mesh, frame)` runs once per mesh layer, before any
shape is drawn:

```
positions = [eval(p.position, frame) for p in mesh.points]     # once for the whole mesh
for each curve:
    widths = [eval(mesh.points[cp.point_index].width, frame) for cp in curve.points]
    CurveGeometry.build(curve, positions, bezier, frame, exporter, widths)
```

`CurveGeometry.build` produces one `SegmentGeometry` per segment, each holding
an explicit cubic Bezier (`p0, c1, c2, p1`) plus `on`:

| `SegmentGeometry` field | Comes from |
|---|---|
| `p0` | `positions[curve.points[i].point_index]` |
| `p1` | `positions[curve.points[(i+1) % n].point_index]` — wraps for a closed curve |
| `c1` | `BezierReconstructor.handle(curve, positions, i, False, ...)` |
| `c2` | `BezierReconstructor.handle(curve, positions, j, True, ...)` |
| `on` | `curve.points[i].segments_on` — **the segment *leaving* point `i`** |

Handle **length** is `distance_to_neighbour * smoothness * weight` (confirmed
exact against 209 reference handles). Handle **direction** is *not*
`normalize(next - prev)`; it is a chord-length-weighted blend of the two
neighbouring chord vectors. See the module docstring's BEZIER CURVES section.

Note `CurveGeometry.point_widths` is parallel to **the curve's own** point
list, not the mesh's. Index it accordingly.

### 6.2 `PathTracer`: rebuilding the walk order

`build_path_d` cannot simply concatenate `edges` in list order. `PathTracer.trace`:

1. Builds an undirected adjacency map keyed by **rounded** endpoint
   coordinates (`Vec2.rounded_key()`), so segments that share a point are
   recognised despite float noise.
2. Seeds traces **preferring an endpoint that touches only one segment** (a
   true open end) over a junction, so junctions get absorbed mid-trace instead
   of becoming an arbitrary subpath boundary.
3. Walks each connected run, reversing a segment's control points when it is
   entered from its `p1` end.

`build_path_d` then emits `M`/`C` commands, starting a fresh subpath whenever
the next segment does not continue from the previous endpoint.

### 6.3 The two flags that change the output

```
build_path_d(geometries, edges, to_px, visible_only=False, close=True)
```

| Flag | Fill path | Stroke path |
|---|---|---|
| `visible_only` | `False` — a hidden segment still bounds the fill | `True` — skips `segments_on == False` segments and breaks the subpath |
| `close` | `True` — appends `Z` when the subpath returns to its start | **`False` — never closes a stroke** |

Never closing a stroke path is not an oversight: Moho's own exporter does not
close them either. See the module docstring's FILL RULE, DRAW ORDER, AND WHY
STROKE PATHS ARE NEVER CLOSED section.

---

## 7. From shape to SVG element

`ShapeGroupRenderer` draws every shape of one mesh, in `mesh.shapes` order
(which *is* the z-order, back to front).

### 7.1 Why shapes must be buffered

A union member's outline must be clipped against the *other* members of its
boolean group — and those may not have been rendered yet. So:

- **Fills are emitted immediately**, into `self.body`.
- **Outlines are buffered** into `self._group` as `_GroupMember` records, and
  only become `<path>` elements in `_flush()`.

`_flush()` is called from exactly two places: at the start of `_render_shape`
when a `combo_mode == 0` shape begins a new group, and once at the end of
`render()` for the final group.

```
render():
  for shape in mesh.shapes:
      _render_shape(shape)      --> fill emitted now; outline queued
  _flush()                      --> last group's outlines emitted
  return self.defs + self.body
         ^^^^^^^^^^   ^^^^^^^^^
         ALL defs come before ALL body elements
```

### 7.2 Inside `_render_shape`

```
skip if not shape.edges
resolve colours/width:  eval(style.line_width), eval(style.fill_color),
                        eval(style.line_color), style.line_cap_name()
fill_path = build_path_d(..., close=True)     # skip the shape entirely if empty

paint = fill_hex
if shape.has_fill and style.fill_style is a dict:
    if type == "SS_Gradient2": build a gradient def, paint = url(#grad_N)
    else:                      warn to stderr, keep the flat colour

widths      = _point_widths(shape.edges)      # distinct mesh points of this shape
tapered     = (max(widths) - min(widths) > 1e-6)
point_width = widths[0] if (widths and not tapered) else 1.0

combo_mode = shape.combo_mode
if combo_mode not in (0, 1, 3):  warn, treat as 0     # <- this is where 2 lands
if combo_mode == 0 or group is empty:  _flush()

if combo_mode == 3:  clip = union of the group's solid members SO FAR

if shape.has_fill:  emit <path ..._fill> now
if shape.has_outline:  pick exactly ONE outline strategy (below), queue it
```

Note that `combo_mode == 3` is clipped **twice**: once here against the group's
solid members known so far, and again in `_flush()` against the group's final
solid set.

### 7.3 The three outline strategies

Exactly one applies per shape, chosen in this order:

```
if brush asset resolved (style.brush_name AND style.brush_tint AND file found):
        BrushStampOutliner.build(...)  -> brush_dabs
        diameter comes from _stroke_width_px(line_width, 1.0)
        NOT ...(line_width, point_width) - each dab scales itself by the
        point width interpolated at that dab, so baking it in twice is wrong
elif tapered:
        TaperedStrokeOutliner.build(...)  -> taper_path  (a filled outline)
else:
        build_path_d(..., visible_only=True, close=False)  -> stroke_path
```

A brush stroke wins over tapering — a varying-width brushed shape still gets
brush treatment, with the taper folded into each dab's diameter.

### 7.4 What `_flush()` emits

```
base  = self._group[0]                                    # the group's styling source
solid = [m.fill_path for m in group if m.combo_mode in (0, 1)]

for member in group:
    skip if it has no outline of any kind
    style_source = base if member.combo_mode in (0,1) else member
                   ^^^^ a union member is stroked with the BASE's style,
                        not its own - this is Moho's behaviour
    clip:
      combo_mode in (0,1) and len(solid) > 1 -> _mask_subtraction(others, own, ...)
      combo_mode == 3                        -> _mask_union(solid, ...)

    then emit ONE of:
      brush_dabs -> <g id="NAME_line" clip>  ... dabs ...  </g>
      taper_path -> <path id="NAME_line" fill=LINE fill-rule="evenodd" stroke="none">
      stroke_path-> <path id="NAME_line" fill="none" stroke=LINE
                          stroke-width stroke-linecap stroke-linejoin="round">
```

`_mask_subtraction` is worth understanding, because it encodes two separate
bug fixes:

1. It punches holes with **a single even-odd path** (padded bbox minus every
   other member), not a white rect behind black shapes. The latter renders
   wrong in `cairosvg`, which treats mask content as alpha rather than
   luminance.
2. It then paints **a one-stroke-width band back on top** along every
   subtracted path. Without it, two crossing outlines each stop exactly on the
   other's edge, one stroke-width short of meeting, leaving a visible notch.

There is a known limitation here, flagged rather than patched: the "own" shape
passed to size the mask is `member.stroke_path`, which is `""` for a tapered or
brush-stamped member. Such a member relies solely on the *other* members'
bounds. No sample exercises it as a non-base union member.

**A second limitation, now fixed: `combo_mode == 3`'s `_mask_union` clip is an
SVG-masking *approximation* of intersection, not a true geometric path
intersection — which used to leave a real gap in the member's own outline
that Moho does not show.** Confirmed on `Bandit`'s `Eye_Upper`/`S3` (a
`combo_mode == 3` shape): one of its curve segments has `segments_on ==
false`, but that segment's own endpoints do not coincide with any segment of
the base shape's boundary — unlike the `combo_mode == 1` case above, where a
hidden segment is legitimately a shared edge the *other* member already
draws, this one is unique geometry with nothing to replace it. `build_path_d`
(§ 6.3) with `visible_only=True` simply omitted it, leaving two open
subpaths with round end caps instead of one closed loop — visible as a small
notch. Real Moho most likely computes an actual new boundary edge where the
two curves cross, and marks the original segment `segments_on == false`
because a *computed* edge has replaced it.

Rather than reconstructing that edge (real Bezier–Bezier intersection —
finding the crossing point and building a new segment there, a different
class of algorithm from `_mask_union`'s clip-the-existing-stroke approach),
`_render_shape`'s plain-stroke branch (§ 7.2) now passes
`visible_only=(combo_mode != 3)` to `build_path_d` instead of always `True`.
For a `combo_mode == 3` member this draws the **full** original closed
outline — segments_on==false segment included — and lets the *existing*
`_mask_union` clip (unchanged) cut it down to within the base shape's fill,
exactly as it already did for the visible segments. Because SVG's own
clipping computes the true geometric crossing point when the mask is
rasterised, the result comes out correct without this tool ever computing a
Bezier intersection itself. Confirmed: `Eye_Upper`'s `S3_line` changed from
two subpaths (split by an `M`) to one continuous path, closing the visual
gap, and — checked across all five reference documents — `Eye_Upper`/`S3` is
the **only** shape that is both `combo_mode == 3` and has a
`segments_on == false` segment, so nothing else could have regressed. See the
module docstring's BOOLEAN SHAPE COMBINATIONS section and KNOWN GAPS for the
one remaining open question (whether an intersect member could ever
legitimately want its own artist-drawn gap, which this fix would now
restore instead of hiding).

### 7.5 The three brush render paths

Chosen inside `_flush()`, per shape:

| Condition | Path | Element per dab |
|---|---|---|
| `--brush-raster` and Pillow available | `_raster_brush_shape` composites the whole stroke into **one** `<image>` | none — one image per shape |
| Pillow available (default) | `_brush_tinted_ref` bakes colour once per `(brush, frame, colour, alpha)` | `<use>` of a pre-tinted `<image>` |
| Pillow **not** available | `_brush_mask_refs` | `<mask>` + `<filter>` per dab — the slow fallback |

The fallback is slow to *view*, not merely to write: `<mask>` and `<filter>`
each force an offscreen buffer per element. See `docs/exporting-svg.md` § 7 for
the measured numbers.

### 7.6 `PatchLayer` suppresses its outline, not just its transform

`ShapeGroupRenderer` takes a `suppress_outline` flag, set by both call sites
(`Exporter.export_layer` and `export_document`'s `emit()`) whenever the layer
currently being rendered has `layer.kind is LayerKind.PATCH`:

```
outline_enabled = shape.has_outline and not self.suppress_outline
```

`outline_enabled` replaces `shape.has_outline` in both places that decide
whether to build a stroke: the brush-asset lookup and the
`stroke_path` / `taper_path` / `brush_dabs` branch. The **fill** path is
untouched — `shape.has_fill` still drives it directly.

This exists because a resolved patch shares its target's `Shape` objects
verbatim ([§ 2.3](#23-two-load-time-rewrites)): `shape.has_outline` on a
patch's shapes is really the *target's* `has_outline`, and the target has a
real outline of its own that must still render wherever the target itself
draws in the tree. Mutating `Shape.has_outline` would silence that too, so
the suppression has to be a render-time flag, checked once per render call,
not a property of the shared shape.

Why suppress the outline at all: confirmed directly in the Moho app (not
just by comparing this tool's own SVG output against itself) on two points
chosen specifically to separate this from the masking behaviour documented in
[§ 9](#9-masking-two-fields-one-svg-construct):

| Layer | `masking` | Is a `PatchLayer` | Target has a real stroke | Stroke visible in Moho |
|---|---|---|---|---|
| `ayasi-Patch` (SketchBone) | `2` (mask source) | yes | yes | **no** |
| `Left Bicep-Patch` (ReparentBone) | `0` (not a mask source) | yes | yes | **no** |

`masking` is the one field that differs between the two, and the result does
not change — so the suppression is keyed on `layer.kind is LayerKind.PATCH`,
not on `masking`. This also means it does *not* contradict
[§ 9](#9-masking-two-fields-one-svg-construct)'s confirmed "a `masking == 2`
layer is still drawn normally" — that rule is about visibility, not about
which parts of a normal mesh layer's own styling apply, and it was never
tested against a `PatchLayer` specifically.

---

## 8. Style resolution and the SVG attribute mapping

### 8.1 When resolution happens

`ResolvedStyle.resolve(shape_raw, styles)` is called **once per shape at load
time**, from `Shape._build` — never per frame. Inheritance never depends on a
frame, so there is nothing to redo.

What it produces is *still channels*, not values: `fill_color`, `line_color`,
and `line_width` stay raw so that they can be evaluated per frame with the
right Smart Bone context. Only `line_caps` is stored as a plain `int` (Moho
never animates it).

### 8.2 The merge rule, precisely

```
own = shape_raw["style"]
out = dict(own)                                  # <- the shape's own values are the BASE
for key in (inherited_style_uuid, inherited_style_name,
            inherited_style2_uuid, inherited_style2_name):
    ref   = shape_raw.get(key) or own.get(key)   # BOTH locations are checked
    named = styles.get(ref)                      # by uuid OR name
    if not named: continue
    for (flag, field) in [(define_fill_color, fill_color),
                          (define_line_col,   line_color),
                          (define_line_width, line_width)]:
        if named[flag] and not own[flag]:  out[field] = named[field]
    if named.fill_style is a dict and not own.define_fill_color:
        out.fill_style = named.fill_style        # gradients live ONLY on named styles
    if not own.define_line_width and "line_caps" in named:
        out.line_caps = named.line_caps
    if named.define_line_width and not own.define_line_width and named.brush_name:
        copy brush_name, brush_jitter, brush_spacing, brush_align, brush_tint
```

Two consequences that surprise people:

- **A `define_X` flag that is false on the shape does not blank the shape's own
  value.** It only makes the shape *overridable*. This is why the newer
  document generation works at all — every one of its shapes has all flags
  false and no inherited style, so its own values are used verbatim.
- **Style 2 is applied after style 1**, so style 2 wins where both define the
  same attribute. That is the mechanism behind layering an outline-only "line
  style" on top of a base fill style.
- **`fill_style`, `line_caps`, and the brush fields ride on the same three
  flags.** In particular a brush is gated on `define_line_width`, since a
  brush only ever styles the line.

### 8.3 Field → SVG attribute

| Resolved field | Emitted as | Notes |
|---|---|---|
| `fill_color` | `fill="#RRGGBB"` + `fill-opacity` | omitted when alpha ≥ 1 |
| `fill_style` (`SS_Gradient2`) | `fill="url(#grad_N)"` + a gradient def | `gradient_type` 1 → `<radialGradient>`, anything else → `<linearGradient>`. See the note below. |
| `line_color` | `stroke="#RRGGBB"` + `stroke-opacity` — **or** `fill=` on a tapered/brush outline | a tapered outline is a *filled* path, so the line colour becomes a fill |
| `line_width` × point `width` | `stroke-width` | via `_stroke_width_px`; see [§ 4.3](#43-the-scale-chain-stroke-width-and-why-it-differs) |
| `line_caps` | `stroke-linecap` | `LINE_CAP_NAMES = {0: butt, 1: round, 2: square}`, default `round` |
| — | `stroke-linejoin="round"` | hardcoded, not from the document |
| fills | `fill-rule="evenodd"` | on shape fills and tapered outlines |
| mask contents | `fill-rule="nonzero"` | **deliberately different** from fills |
| `brush_*` | `<image>` / `<use>` / `<mask>`+`<filter>` | see [§ 7.5](#75-the-three-brush-render-paths) |
| `shape.effect_scale` / `effect_rotation` | gradient placement only | not a geometric transform |

The `evenodd` (fills) versus `nonzero` (masks) split is intentional. A mask
built with `evenodd` would cancel itself out wherever two mask sources overlap.

Three details about gradients in `_build_gradient` that are easy to miss:

- **Fewer than two stops → no gradient at all.** It returns `(None, None)` and
  the shape keeps its flat `fill_color`, silently.
- **Placement is in percentages, centred at `50% / 50%`**, i.e. relative to
  each path's own bounding box (SVG's default `objectBoundingBox` units). This
  is why the placement is approximate rather than pixel-matched to Moho's own
  differently-parameterised placement.
- **`effect_rotation` only affects the linear case.** The radial branch uses
  `effect_scale` for `r` and ignores rotation entirely — a rotated radial
  gradient is a no-op. A shape-level centre offset is supported by the formula
  but nothing supplies one, so it stays at `(0, 0)`.

---

## 9. Masking: two fields, one SVG construct

### 9.1 The rule

Two separate fields cooperate (full semantics in
`moho-project-file-format.md` § 10):

- `group_mask` on the **container** — non-zero means "this container masks its
  children". `Exporter._mask_sources` returns early when it is falsy, unless
  `--mask-container NAME` forces it.
- `masking` on each **child** — `2` = mask source (still drawn normally),
  `1` = exempt, anything else = clipped.

### 9.2 Collecting the silhouette, recursively

`_mask_source_shapes(layer, ancestors, frame)` gathers the mask geometry for
one `masking == 2` layer, as `(fill_path, own_stroke_width_px)` pairs — the
second element is `0.0` unless the shape has a plain (non-tapered,
non-brush) outline, in which case it is that outline's own resolved stroke
width, computed the same way as `_render_shape`'s `stroke_width_px`:

```
paths = []
if layer.mesh is not None:
    build its own deform chain
    for each shape: append (fill_path, own_stroke_width_px_or_0.0)
for child in layer.children:
    if child.masking == 2:
        paths += _mask_source_shapes(child, ancestors + (layer,), frame)   # recurse
return paths
```

`_mask_element` (§ 9.5) uses the second element of each pair to carve the
source's own stroke band back out of the mask, so it can never be painted
over by whatever the mask clips.

The recursion is not theoretical. A mask source is **not always a mesh
layer**: a `GroupLayer` can be `masking == 2` purely as a masking *container*,
in which case its silhouette is whatever its own `masking == 2` children
define. Confirmed against the `Bandit` rig's `BellyTexture`, whose own `mesh`
is `None` and whose single `masking == 2` child `Body` is exactly the shape
Moho's own export uses both as `BellyTexture`'s internal clip and as its
contribution to masking its sibling.

Masking applies **uniformly at every depth, including the document root**.
An earlier version special-cased top-level masking away; that turned out to be
the wrong fix for an unrelated bug.

### 9.3 The empty-Smart-Bone-context quirk

`_mask_sources` is always evaluated with `self._active_actions` **empty** —
never with the dials that are active for the mesh being clipped.

This is not a design decision. It falls out of *when* `export_layer` /
`export_document` call it relative to where they set and clear
`_active_actions`: by construction it always lands between two clears. It has
been **carefully preserved rather than fixed**, because there is no reference
export to confirm what should happen instead. If you reorder those
assignments, you change mask geometry for any rig whose mask source is driven
by a Smart Bone. See the module docstring's KNOWN GAPS.

### 9.4 The SVG that comes out

```
<svg viewBox="...">
  <defs>                          <- brush defs only (see § 10)
    <image id="brush_.."/>  ...
  </defs>
  <mask id="mask_1" maskUnits="userSpaceOnUse" x=".." y=".." width=".." height="..">
    <path d="<source silhouette>" fill="white" fill-rule="nonzero"/>
    ...                                                     one per mask source
  </mask>
  <g id="ContainerName" data-moho-type="GroupLayer">
    <g id="MaskSourceChild" data-moho-mask="2">              <- NOT clipped
      <path id="S1_fill" .../>
    </g>
    <g id="ClippedChild" data-moho-mask="0" mask="url(#mask_1)">
      <path id="S2_fill" .../>
      <path id="S2_line" .../>
    </g>
    <g id="ExemptChild" data-moho-mask="1">                  <- NOT clipped
      ...
    </g>
  </g>
</svg>
```

Points worth noting:

- The `<mask>` is emitted **inline**, immediately before the container's
  children — not inside `<defs>`. Only brush defs go in `<defs>`.
- Every mask gets an explicit `maskUnits="userSpaceOnUse"` plus a bbox
  computed by `parse_path_bbox(paths, settings.mask_padding)`. Without the
  explicit box, the default `objectBoundingBox` region clips the mask itself.
- `data-moho-mask` and `data-moho-type` are debugging aids this tool adds; they
  carry no rendering meaning.
- A `<mask>` is used rather than a multi-child `<clipPath>` because a
  `<clipPath>` with several children does not union them the way needed here.

### 9.5 A mask source's own stroke must never be painted over

A `masking == 2` sibling's own rendered stroke stays fully visible on top of
anything it masks — verified directly against the Moho app on
`Bandit.mohoproj`'s `Head_DarkBlue` (`masking == 0`) / `BellyTexture`
(`masking == 2`) pair: `BellyTexture`'s stroke shows unbroken in Moho
everywhere it overlaps `Head_DarkBlue`. Before this was fixed, since
`BellyTexture` is listed *before* `Head_DarkBlue` in `layers`, this tool let
`Head_DarkBlue` paint over roughly the inner two-thirds of `BellyTexture`'s
stroke wherever their un-masked geometry overlapped — confirmed by
rasterising both independently (`rsvg-convert`) and diffing pixel colour
along `BellyTexture`'s stroke centreline: ~65% of sampled stroke pixels
showed the wrong colour.

**The obvious fix (reorder paint order) was tried first and reverted.**
Making `emit()` paint every `masking == 2` sibling after every `masking == 0`
sibling in the same container fixes this specific pair, but breaks a
different, untouched relationship on the *same* container: most of
`Bandit`'s own children (`Arm_B`, `Tail`, `Ears`, `Muzzle`, `Nose`,
`EyeBrow`, `Arm_F`) are `masking == 1` ("exempt"), and `BellyTexture`
originally precedes some of them (e.g. `Muzzle`) in file order. Forcing
"every masking==2 after every masking==0" drags `BellyTexture` past those
exempt siblings too, painting its opaque fill over the character's
eyes/muzzle/nose — confirmed wrong in the Moho app (`Muzzle`/`Nose`/
`EyeBrow` stay unaffected there). Concretely: `BellyTexture` would need to
paint both *before* `Muzzle` (preserve the untouched exempt ordering) and
*after* `Head_DarkBlue 2` (the new masking==2-after-masking==0 rule) — but
`Muzzle` already precedes `Head_DarkBlue 2` in file order, so those two
requirements are mutually exclusive. There is no single reordering of one
container's children that satisfies both constraints for this document — a
paint-order fix was the wrong category of fix entirely.

**The actual fix changes mask *geometry*, not paint order.**
`_mask_source_shapes` (§ 9.2) now returns, per source shape, not just its
fill path but also its own stroke width in pixels — computed the same way
`_render_shape` computes `stroke_width_px` (§ 7), and left at `0.0` (no
exclusion) whenever the shape is tapered or brush-styled, since a uniform
stroke-width band wouldn't match either of those outlines' real geometry.
`_mask_element` then paints each such path a **second** time, after its
white fill (so it wins), as a **black stroke** that exact width — carving
the source's own stroke band back *out* of the mask:

```python
def _mask_element(self, paths, mask_id, indent):
    fills = "".join(f'<path d="{d}" fill="white" fill-rule="nonzero"/>' for d, _ in paths)
    exclusions = "".join(
        f'<path d="{d}" fill="none" stroke="black" stroke-width="{w:.3f}"/>'
        for d, w in paths if w > 0)
    ...  # fills, THEN exclusions, in that order inside the same <mask>
```

Whatever this mask clips can now never paint into that excluded band, **no
matter what z-order it's at** — which is why this fix cannot regress
`masking == 1` siblings: they were never part of the mask computation to
begin with, so nothing about them changes. Re-measured after the fix: 62% of
the sampled stroke pixels show `BellyTexture`'s own colour (up from 35%), a
further 22% are legitimately covered by *other*, unrelated `masking == 1`
siblings (whose own z-order relationship to `BellyTexture` this fix
correctly leaves alone — confirmed by re-rendering with `Head_DarkBlue`/
`Eye_Back`/`Head_DarkBlue 2`/`Eye_Upper` removed from the tree entirely: the
remaining "covered" count barely changes, 1063 px vs 1126 px, so it isn't
coming from this fix's target layers at all), and the small residual is
consistent with anti-aliasing at the mask boundary rather than a real gap.

A tapered or brush-styled source outline still contributes only its bare
fill silhouette to the mask, same as before this fix — unconfirmed geometry
for those two cases. See the module docstring's MASKING section and KNOWN
GAPS.

---

## 10. `Exporter` state and why one instance per export

`Exporter` is deliberately the **only stateful class** in the file. Its state
splits into three lifetimes:

| Lifetime | Fields | Notes |
|---|---|---|
| **Per export call** | `_skin_cache`, `_next_id` | `_next_id` names `<mask>`/`<linearGradient>`/`<filter>` defs. Sharing one Exporter across concurrent exports would interleave ids and produce cross-referenced defs. |
| **Per mesh layer** (set then cleared) | `_active_actions`, `_layer_scale` | Set immediately before rendering a layer's shapes, cleared immediately after. The exact clear point is load-bearing — see [§ 9.3](#93-the-empty-smart-bone-context-quirk). |
| **Per export, append-only** | `_brush_asset_cache`, `_brush_defs`, `_brush_refs`, `_brush_tinted_defs`, `_brush_tinted_ids` | Populated lazily *while* the body is being rendered, which is why `_wrap()` can only prepend `<defs>` at the very end. |

**Construct one `Exporter` per export call** — or per goroutine in a Go port.
This is stated in the class docstring and is a real constraint, not a
suggestion.

One subtlety about `<defs>`: `<mask>` and `<filter>` never paint on their own,
but a bare `<image>` does. So the pre-tinted brush images **must** be wrapped
in `<defs>`, or each one paints itself once at its own local `(x, y)` on top of
the document, in addition to every `<use>` of it.

---

## 11. Cross-reference: field → consuming stage

Use this to jump from a field in `moho-project-file-format.md` to the code that
reads it.

| Field | Read by | Stage |
|---|---|---|
| `project_data.width` / `.height` | `Document.from_raw`, `_to_pixel`, `_viewbox` | load / pixel projection |
| `styles[]` | `StyleTable.build` | load |
| `version` | `Document.format_version` | load (stored, never branched on) |
| `layers[]` order | `Document.walk`, `emit` | draw order |
| `layer.visible`, `.edit_only` | `emit` | tree walk, step (C) |
| `layer.name` | `emit`, `--layer`, `--mask-container` | tree walk / CLI |
| `layer.uuid` | `_resolve_patch_layers` | load |
| `layer.type` (→ `.kind`) | `emit`, `export_layer` (→ `suppress_outline`); `build_deform_chain` (→ bone-layer check); `emit` (→ switch-layer check) | load (kind classification) + render (multiple branch points) |
| `layer.transforms.*` (5 of 10) | `Layer.local_matrix` | transform |
| `layer.origin` | `Layer.local_matrix` | transform (pivot) |
| `layer.parent_bone` | `build_deform_chain` → `SkinStep` | skinning |
| `layer.flexi_bone_subset` | `_deformed_pixel_mapper` → `Skinner.deform` | skinning |
| `layer.group_mask` | `_mask_sources` | masking, step (A) |
| `layer.masking` | `_mask_sources`, `_mask_source_shapes`, `member_clip` | masking |
| `layer.actions[].name` | `Layer.action_names` → `_active_smart_bones` | Smart Bones |
| `switch_keys` | `Layer.switch_active_child` | tree walk, step (B) |
| `target_layer_uuid` | `_resolve_patch_layers` | load |
| `mesh_layer` | `Layer._build` | load (synthesised child) |
| `mesh.points[].position` | `_curve_geometries` | geometry |
| `mesh.points[].width` | `_curve_geometries`, `_point_widths` | geometry + stroke width |
| `mesh.curves[].closed` | `CurveGeometry.build` | geometry |
| `curve_points[].point` | `CurveGeometry.build`, `_point_widths` | geometry |
| `curve_points[].smoothness`, `weight_*`, `offset_*` | `BezierReconstructor.handle` | geometry |
| `curve_points[].segments_on` | `SegmentGeometry.on` → `build_path_d(visible_only=True)` | stroke path only |
| `shapes[]` order | `ShapeGroupRenderer.render` | z-order within a mesh |
| `shape.edges` | `PathTracer.trace`, `_point_widths` | path tracing |
| `shape.has_fill` / `.has_outline` | `_render_shape` | element choice — `.has_outline` overridden to `False` when the enclosing layer is a `PatchLayer` (`suppress_outline`, § 7.6) |
| `shape.combo_mode` | `_render_shape`, `_flush` | boolean groups |
| `shape.id`, `.name` | `_render_shape` (element ids, brush seed) | output naming |
| `shape.effect_scale` / `.effect_rotation` | `_build_gradient` | gradient placement |
| `shape.style` + `inherited_style*` | `ResolvedStyle.resolve` | load |
| `style.fill_color` / `line_color` | `_render_shape` | paint |
| `style.line_width` | `_stroke_width_px` | stroke width |
| `style.line_caps` | `ResolvedStyle.line_cap_name` | `stroke-linecap` |
| `style.fill_style.*` | `_build_gradient` | gradient def |
| `style.brush_name` / `_jitter` / `_spacing` / `_align` / `_tint` | `_get_brush_asset`, `BrushStampOutliner.build` | brush stamping |
| `bone.name` | `_active_smart_bones` | Smart Bone matching |
| `bone.parent` | `Skeleton.world_matrices` | bone hierarchy |
| `bone.length` | `Skinner.build` (`rest_p1`) | skinning distance |
| `bone.strength` | `Skinner.deform` (gate + falloff) | skinning weight |
| `bone.anim_pos` / `anim_angle` / `anim_scale` | `Skeleton.world_matrices` | bone pose |
| channel `when` / `val` | `Channel.eval_raw` | every evaluation |
| channel `actions[].pose` | `Channel.eval`, `frame_for_value` | Smart Bones |

Fields **absent from this table are not read at all.** See
`moho-project-file-format.md` § 13.2 for the ones whose absence measurably
changes the output, and § 13.3 for the untested gaps.

---

## 12. Reading order for a newcomer

If you are about to change this code, or port it:

1. This document's [§ 1](#1-overview-the-data-flow) and
   [§ 3](#3-walking-the-layer-tree-the-decision-order) — the shape of the thing.
2. `moho-project-file-format.md` § 5–8 — what the data actually is.
3. The module docstring's COORDINATES and STROKE WIDTH sections — the two
   formulas everything else sits on.
4. This document's [§ 4](#4-transforms-and-coordinate-spaces) — the part that
   is genuinely hard, and where a plausible-looking simplification is wrong.
5. The module docstring's KNOWN GAPS — before you "fix" anything.

For a Go port specifically, the module docstring's PORTING NOTES section maps
each `# ==== SECTION ====` banner in `moho2svg.py` to an intended Go file. Two
constraints carry over and are easy to miss: **one `Exporter` per export call**
([§ 10](#10-exporter-state-and-why-one-instance-per-export)), and the
thin-accessor design that makes `Channel.of`'s identity cache sound
([§ 5.1](#51-channelof-and-the-identity-cache)).
