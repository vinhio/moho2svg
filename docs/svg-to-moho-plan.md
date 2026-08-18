# SVG → Moho: implementation plan

Task-by-task plan for `svg2moho.py`, following the design in
[svg-to-moho-design.md](svg-to-moho-design.md).  Each task ends with a
verification gate; every gate is runnable without opening the GUI (Moho's
headless CLI is the authority — see the repo root `CLAUDE.md` "Getting
ground truth out of Moho itself").

**Reuse over rewriting.**  `lottie2moho.py` already contains, validated
against Moho 14.4's own loader, nearly every output-side piece this
converter needs.  The plan copies those helpers (self-contained, the same
"vendored copy" policy as lottie2moho's own docstring) rather than
re-deriving them: `pixel_to_moho`, `compose_matrix`, `_static_channel`,
`_IDENTITY_TRANSFORMS`, `_document_scaffold`, the layer/mesh/curve/shape/
point/style dict builders, `fit_curve_point`, the winding reversal, and
the WarningCounter convention.

---

| Task | What | State |
|---|---|---|
| 1 | CLI, SVG parser, scaffolding, M/L/Z paths | done |
| 2 | Full path command set (C/S/Q/T/H/V/A) | done |
| 3 | Primitives | done |
| 4 | Transforms | done |
| 5 | Styles | done |
| 6 | Gradients | done — placement approximate (design 5.1) |
| 7 | Holes, fill rule, defs/use | done |
| 8 | Verification harness + corpus | done |

All gates measured 2026-08: 9-file corpus converts with zero exceptions and
loads in Moho 14.4 headless (9/9 with retry); bbox gates match independent
expectations within 6 px on every file; the donut hole is pixel-verified
(94% of the true ring area, cardinal points within ~1 px); gradients render
(colour-sampled); a real-world 166-layer SVG converts and renders.

## Task 1 — CLI, minimal parser, document scaffolding, straight-line paths

- `svg2moho.py <file.svg> --out <file.mohoproj>`; stdlib only
  (`xml.etree.ElementTree`, no third-party XML library).
- Parse the `<svg>` root: `viewBox`, `width`/`height` → canvas size.
- Walk elements in document order; handle `<g>` recursion and `<path>`
  with only `M`/`L`/`Z` commands (absolute and relative).
- Build the output with the **complete Moho-validity contract**
  (design section 7) — document scaffolding, channel-shaped
  `project_data`/`animated_values`/transforms, full layer/mesh/curve/
  shape/point/style dicts.  Do NOT skip the "boring" fields: every
  omission here was measured as an Error 108 or "Type mismatch" in the
  Lottie work.
- One MeshLayer per path, flat-baked points, winding reversal applied,
  identity transforms, reversed paint order.

**Gate:** `svg2moho.py` converts a hand-written triangle + a 10-segment
polyline SVG; both outputs render headless in Moho with the expected
bboxes; `moho2svg.py` loads both.

## Task 2 — the full path command set

- `C`/`c` (direct cubics → the handle-fit path), `S`/`s` (reflection),
  `Q`/`q`/`T`/`t` (quadratic → cubic), `H`/`h`, `V`/`v`, `A`/`a`
  (endpoint-to-center arc → cubic, split at ≥π/2), multiple subpaths,
  open and closed curves.
- Relative-to-absolute conversion and implicit command repetition per
  the SVG spec.
- Curve points as full channels (smoothness/weight/offset), the
  `curves` back-reference patched after the curve index is known.

**Gate:** one SVG per command family converts and renders; bbox centre of
each rendered layer matches the input's computed bbox within 2 px
(computed independently with the repo's `tools/check_reference_frames.py`
extraction helpers).

## Task 3 — primitives

- `rect` (with `rx`/`ry`), `circle`, `ellipse`, `line`, `polyline`,
  `polygon` → equivalent path `d` strings, then the shared converter.
  No separate geometry code.

**Gate:** the five primitive SVGs render with the same bboxes as the
input (Moho render vs independent computation).

## Task 4 — transforms

- `transform` attributes: `matrix`, `translate`, `scale`, `rotate`
  (including rotate-around-a-point), `skewX`, `skewY`, and their
  combinations, on any element and nested in `<g>`s.
- viewBox x/y offset and user-unit→pixel scaling in the root matrix.
- All composed by the existing `compose_matrix` into the bake matrix.

**Gate:** a transform-torture SVG (every transform type, 3 levels of
nesting) renders within 2 px of the independently computed pixel
positions; a skew case included — the only genuinely new matrix shape.

## Task 5 — styles

- `fill`, `stroke`, `stroke-width` (→ `line_width` via the inverse
  stroke formula), `stroke-linecap` → `line_caps`,
  `stroke-linejoin` (mapped or warned), `opacity`/`fill-opacity`/
  `stroke-opacity` folded into alpha, `fill="none"`/`stroke="none"`.
- Presentation attributes AND inline `style="..."` strings (the style
  string is parsed for the same keys; attributes win on conflict, per
  SVG's own precedence).
- Full 27-key Style dict per shape (Moho rejects abbreviated styles).
- Unknown/unsupported values → counted warnings, safe fallbacks
  (`currentColor` → warning + black).

**Gate:** a style-matrix SVG (all caps × fills vs strokes × opacities)
renders; spot-check one colour by reading the render's RGB pixel.

## Task 6 — gradients

- `linearGradient`/`radialGradient` in `<defs>`, `fill="url(#id)"`,
  gradient stops with colours and offsets, `gradientTransform`.
- Emit Moho's `SS_Gradient2` in the style's `fill_style` slot, the same
  structure `lottie2moho.py` already writes, with the documented
  placement approximation.
- `spreadMethod` ≠ pad and non-objectBoundingBox units → counted warnings.

**Gate:** linear + radial gradient SVGs render with non-uniform colour
coverage (pixel-sampled: corner colours differ); the placement caveat is
documented, not silently "fixed".

## Task 7 — holes, fill rule, defs/use

- Consecutive subpaths of one path element group into ONE shape
  (outer + holes) — the `lottie2moho.py` `current`-shape pattern.
- `fill-rule="evenodd"` → same grouping + counted warning (Moho has no
  evenodd; nonzero is the faithful default).
- `use` with an id reference into `<defs>` (symbols/other shapes):
  resolve, apply the use element's transform; v1 warns on `x`/`y`.
- Nested `<defs>` scoping handled by the XML tree walk.

**Gate:** a donut SVG (one path, two counter-wound subpaths) renders with
the hole actually cut (compare the render's filled area against the
independent computation); `fill-rule="evenodd"` converts with the warning.

## Task 8 — verification harness and corpus

- A `tmp/scripts/convert_svg_tree.py` batch converter (the
  `convert_lottie_tree.py` pattern): walk a directory tree, convert every
  `.svg`, log warnings and failures per file.
- A load-test loop through Moho's headless CLI with ONE retry per file
  (Moho invocations are ~1–2% flaky — measured during the Lottie batch).
- A corpus folder covering: every command, every primitive, every
  transform type, nested groups, gradients, holes/evenodd, open paths,
  stroke-only shapes, degenerate paths (empty `d`, single-point
  subpaths), huge viewBoxes, unit-less width/height.
- Every counted warning exercised at least once; every failure triaged
  down to a fix in the writer or a documented out-of-scope warning.

**Gate:** the whole corpus converts with zero exceptions, every output
renders headless in Moho, and zero outputs are empty.

---

## Cross-cutting rules (carried from the Lottie work)

1. **Moho's loader is the only authority.**  A file that this repo's
   `moho2svg.py` reads but Moho rejects is still a bug — the scaffolding
   contract (design section 7) exists because of exactly those.
2. **Warnings are counted and specific.**  Every dropped feature has a
   counter name and a one-line explanation, printed once per run.
3. **Self-containment.**  Vendored copies of shared formulas, marked
   "copied from ...", never imports from `moho2svg.py`/`lottie2moho.py`.
4. **The winding reversal is not optional.**  It is invisible on
   single-loop shapes and catastrophic on any shape with a hole — the
   exact failure mode that cost a day in the Lottie work.
5. **Measurement beats guessing.**  Every bbox/pixel comparison in the
   gates is computed independently of the writer (extraction helpers in
   `tools/`), never self-consistent checks.
