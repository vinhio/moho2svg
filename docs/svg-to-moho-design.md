# SVG → Moho: design

Design for `svg2moho.py`, the SVG counterpart of `lottie2moho.py`: read a
static SVG file and write a `.mohoproj` that Moho (and this repo's own
`moho2svg.py`) can open and that renders the same picture.  Every decision
below either copies a decision `lottie2moho.py` already validated against
Moho 14.4's own loader, or names the measurement that will validate it.

---

## 1. The contract

The same flat-bake contract as `lottie2moho.py` (its module docstring):

- The output is a **flat, unrigged, static** Moho document: one root
  `GroupLayer`, one `MeshLayer` per converted SVG element, no bones, no
  animation channels.  Every transform is **baked into the point
  coordinates**; every layer transform stays identity.
- Static is fine here because the input is static: SVG has no keyframe
  timeline.  (SMIL/CSS animation is out of scope, see section 9.)
- Paint order: SVG paints in document order, later on top; Moho paints the
  LATER layer on top.  The layer list is therefore reversed, exactly like
  `lottie2moho.py`'s shape list.

## 2. Input model

The supported subset, chosen so that every common vector asset converts:

| SVG feature | Handling |
|---|---|
| `<svg>` root | `viewBox` (or `width`/`height`) → Moho canvas size |
| `<g>` | transform composition level; no layer of its own |
| `<path>` | the main geometry path (section 4.1) |
| `<rect>`, `<circle>`, `<ellipse>`, `<line>`, `<polyline>`, `<polygon>` | converted to a path first (section 4.2) |
| presentation attributes (`fill`, `stroke`, `stroke-width`, `opacity`, `fill-opacity`, `stroke-opacity`, `stroke-linecap`, `stroke-linejoin`, `fill-rule`, `transform`) | section 5 |
| `style="..."` attribute | parsed for the same properties as presentation attributes |
| `<defs>`, `<linearGradient>`, `<radialGradient>` | section 5.4 |
| `<use>` | resolved by id reference, transformed; v1 without `x`/`y` on the use element (warning) |
| `<text>` | **out of scope** — counted warning (no vector outline; Moho has a TextLayer but mapping fonts is a different project) |
| `<image>` | **out of scope** in v1 — counted warning (the ImageLayer machinery exists in `lottie2moho.py` and can be copied in a later task) |
| `<style>` element / external CSS | **out of scope** — only presentation attributes and inline `style` strings |
| filters, masks, clip-paths, markers | **out of scope** — counted warning |

Each out-of-scope feature increments a `WarningCounter` entry, never silent —
the same convention `lottie2moho.py` uses.

## 3. Coordinate mapping

Copied verbatim from `lottie2moho.py`'s `pixel_to_moho`, because it is
already measured correct against Moho's own renderer:

```
pixel_x = moho_x * (h / 2) + w / 2
pixel_y = h / 2 - moho_y * (h / 2)          (y is flipped)
```

Consequences, each one measured during the Lottie work and each one now a
hard rule:

1. **Canvas size** = the viewBox (or width/height) in pixels.  The default
   camera must be written (`camera_zoom = 2.0`, `camera_track z = 2 + √3`);
   any other zoom scales and shifts everything — measured: zoom 1.0 renders
   the whole document at ~0.46×.
2. **The y-flip REVERSES every closed loop's winding.**  Moho's fill rule
   reads outer as hole and hole as outer after a naive bake.  The writer
   must reverse each loop's vertex order (and swap the in/out handle
   offsets with it) to restore the winding.  Measured on a +17,393 px²
   outer loop, which baked to −0.27 units² before the reversal.
3. SVG itself is y-down like the pixel space, so no extra SVG-side flip
   exists — the viewBox's own y runs downward and lands in `pixel_to_moho`
   unchanged.

## 4. Geometry mapping

### 4.1 Path commands → Moho curves

SVG cubics arrive as **absolute handle points** (after relative→absolute
conversion and transform composition); Moho stores, per curve point,
`smoothness` / `weight_in` / `weight_out` / `offset_in` / `offset_out`.
The conversion is exactly the inverse fit `lottie2moho.py`'s
`fit_curve_point` already implements (copied there from the forward
exporter's model): given the vertex and its two neighbour handles, fit the
chord-length-weighted handle model.  The same function is reused — SVG
`C`/`c` commands produce the identical (vertex, in-handle, out-handle)
triples the Lottie path reader fed it.

Command coverage:

| Command | Handling |
|---|---|
| `M`/`m` | move-to: starts a new subpath; closes the previous one only implicitly |
| `L`/`l`, `H`/`h`, `V`/`v` | line segments (zero handles) |
| `C`/`c` | cubic — the direct case |
| `S`/`s` | reflected cubic: reflect the previous handle; at a path start the control point equals the current point |
| `Q`/`q`, `T`/`t` | quadratics: converted to cubic (`C1 = P0 + 2/3 (Q − P0)`, `C2 = P1 + 2/3 (Q − P1)`) |
| `A`/`a` | elliptical arc: converted to cubic per the SVG spec's endpoint-to-center parameterization, split at ≥π/2 sweeps |
| `Z`/`z` | close: joins to the subpath's first point |

One Moho curve per subpath, points in the subpath's own order.  A closed
subpath becomes `closed: true`; an open one stays an open Curve (Moho
supports open curves — a stroke-only path is exactly that).

### 4.2 Primitives

`rect`/`circle`/`ellipse`/`line`/`polyline`/`polygon` are converted to an
equivalent `<path>` `d` string (standard SVG geometry) before entering the
shared path converter — no separate geometry code.  `rect`/`ellipse` honour
`rx`/`ry`.

### 4.3 Holes and the fill rule

Moho's fill uses winding; SVG's default is `fill-rule="nonzero"` with
`evenodd` as the alternative.

- `nonzero`: holes are simply opposite-wound loops of the SAME shape —
  consecutive subpaths after the outer boundary become more loops of one
  shape, exactly as `lottie2moho.py` does (its `current` shape logic).
- `evenodd`: same shape grouping (consecutive subpaths = one shape) —
  Moho cannot express evenodd directly, so the approximation is the same
  grouping, with a counted warning.  Most real assets that use `evenodd`
  were authored as nonzero anyway.
- An SVG path may also **paint** each subpath separately (no grouping
  guarantee).  The writer groups consecutive subpaths of one path element
  into one shape — the same decision `lottie2moho.py` made for Lottie's
  per-shape loops.

## 5. Style mapping

One Moho `Style` dict per shape, the full 27-key form `lottie2moho.py`'s
`_style_dict` already writes (Moho's loader rejects abbreviated styles).

| SVG | Moho |
|---|---|
| `fill="#rrggbb"` / `rgb()` / `url(#grad)` | `fill_color` Color channel (0..1 floats), `has_fill` |
| `fill="none"` | no fill |
| `stroke="#..."`, `stroke-width` | `line_color` channel, `line_width` = `stroke-width / canvas_h` (the inverse of the forward writer's stroke formula) |
| `stroke="none"` or width 0 | no outline |
| `stroke-linecap` butt/round/square | `line_caps` 0/1/2 |
| `stroke-linejoin` | accepted, mapped where Moho has an equivalent, warning otherwise |
| `opacity`, `fill-opacity`, `stroke-opacity` | folded into the alpha of the Color channel |
| `fill="currentColor"` etc. | counted warning, black fallback |

### 5.1 Gradients

`linearGradient`/`radialGradient` map to Moho's `SS_Gradient2` effect in
the style (`fill_style` slot), the same shape `lottie2moho.py`'s
`gradient_fill_style` already emits — including its known limitation that
placement is approximate (carried over from the forward exporter, see its
GRADIENTS notes).  `gradientTransform` composes into the placement.
`spreadMethod` and gradient units other than objectBoundingBox are counted
warnings.

## 6. Transform mapping

Every SVG transform is composed into one 2×3 affine per element, then
baked.  The composition order and matrix form are the existing
`compose_matrix`/`tr_matrix` pair from `lottie2moho.py`.

SVG extras beyond that pair:

- `transform="matrix(a b c d e f)"` → the 2×3 directly.
- `rotate(a [cx cy])` → translate(cx,cy) · rotate(a) · translate(−cx,−cy).
- `skewX(a)`/`skewY(a)` → the shear matrices — the only genuinely new
  transform shape; `compose_matrix` already handles arbitrary affines so
  no new machinery is needed, only the matrix constructor.
- Nested `<g>`s compose in document order (outermost first) — the same
  recursion `lottie2moho.py`'s `walk` uses for Lottie groups.
- The root viewBox offset (x/y of the viewBox) is a translation applied
  once, before anything else.
- SVG user units vs pixels: `viewBox` scaling maps user units to pixels
  (`width / viewBox-width` etc.) — a uniform scale in the root matrix;
  non-uniform viewBox scales are legitimate SVG and fall out of the affine
  for free.

## 7. Document scaffolding — the Moho-validity contract

Everything here was measured the hard way during the Lottie work: Moho's
own loader rejects documents this repo's reader accepts.  The SVG writer
must reuse the exact helpers `lottie2moho.py` now has, or re-encode the
same rules:

1. Document-level keys (`doc_uuid`, dates, `layercomps`, onions, `action_refs`,
   `metadata`, `documentviewstate`) — `_document_scaffold`.
2. `project_data` with the full 25-key set, and **`noise_grain`/
   `pixelation` as ints 0, not booleans** (Moho rejects JSON `false` there).
3. `animated_values` as CHANNELS — camera zoom **2.0**, track z = 2 + √3.
4. Layer `transforms` as full channel dicts (Vec3 translation/scale, the
   ten-key set) — the bare-scalar shorthand is rejected.
5. Full `MeshLayer` (71 keys), `Shape`, `Curve`, `Point` (11 keys incl.
   the `curves` back-reference), `Style` dicts — channel-shaped values.
6. `shape_order` as a String channel, `anim_shape_order` as a plain bool.

These rules are the single largest source of "loads in our reader, corrupt
in Moho" bugs; the plan's tasks cite them per task.

## 8. Verification

Three layers, mirroring the Lottie work:

1. **Moho's own loader** is the authority: every output must render
   headless (`Moho -r out.mohoproj -f SVG -start 1 -end 1`).  Flaky
   invocations happen (~1–2%): the batch harness retries once.
2. **Roundtrip**: `moho2svg.py` must load the output; and a per-layer
   comparison of the re-exported SVG against the input (bbox/point
   distances, per the `diff_reference_sets.py` machinery in `tmp/`) catches
   coordinate errors.
3. **Corpus**: a test folder of SVGs covering every command, primitive,
   transform shape, gradient, hole layout, and fill rule, converted in a
   batch — each counted warning and each failure triaged.

## 9. Out of scope, stated plainly

Text, images, SMIL/CSS animation, filters, masks, clip-paths, markers,
external CSS, `currentColor`-style keywords, gradient spread modes.  Each
is a counted warning in v1.  Text and images are the two most likely to
show up in real assets — both have a natural follow-up task (ImageLayer
machinery exists in `lottie2moho.py`; TextLayer is a Moho-native type).
