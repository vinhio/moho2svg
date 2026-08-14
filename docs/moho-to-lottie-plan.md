# Moho to Lottie Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `moho2lottie.py`, a second exporter that writes a whole Moho document to one animated Lottie JSON file that plays in lottie-web.

**Architecture:** Reuse `moho2svg.py`'s geometry pipeline unchanged. Two small additions to it — a Bezier path builder beside `build_path_d`, and one shared tree walk both exporters consume — then a new writer that bakes every deformation into canvas-pixel vertex positions, so every Lottie layer keeps an identity transform.

**Tech Stack:** Python 3, standard library only. `jsonschema` and Pillow are optional and must never become required. No test framework: verification is check scripts under `tools/` driven by `make`, matching how this repository already verifies itself.

**Spec:** [`moho-to-lottie-design.md`](moho-to-lottie-design.md) — read it before Task 1. This plan implements that design and does not restate its reasoning.

---

## Progress

This table is the single place to read overall status. Each task's own steps
carry `- [ ]` checkboxes further down.

**How to update it.** A task becomes `DONE` only when its **final commit has
landed** and its stated check passed — not when the code is written. Tick the
task's step checkboxes as you go, then flip the row and record the commit.
Anything that is started but unfinished is `IN PROGRESS`, and its row says
which step it stopped at, so a reader knows where to resume.

| # | Work item | Status | Commit |
|---|---|---|---|
| P1 | Feasibility probes — path vertex stability, motion split, feature counts | **DONE** | *(throwaway scripts, not committed)* |
| P2 | Fix: load `1021`-format curve points that omit weight and offset | **DONE** | `be27b10` |
| P3 | Fix: reset the `Channel` cache when a document is parsed | **DONE** | `5c4b8c3` |
| P4 | Design document | **DONE** | `87abe40` |
| P5 | This plan | **DONE** | `496f35c` |
| 1 | A Bezier path builder beside the SVG one | **DONE** | `a91df9f` |
| 2 | One shared tree walk | **DONE** | `a81a6cb` |
| 3 | A Lottie file with one static frame | **DONE** | `4189275` |
| 4 | Path keyframes across the frame range | **DONE** | (pending commit) |
| 5 | Gradients | TODO | — |
| 6 | Masking | TODO | — |
| 7 | Switch layers | TODO | — |
| 8 | Warnings, make targets and optional schema validation | TODO | — |

Two items cannot be closed by any task above, because both need a real Lottie
player. They are described at the end of this document and stay open until
someone loads the output in lottie-web:

| # | Open question | Status |
|---|---|---|
| Q1 | Is Lottie's `op` exclusive? Task 3 assumes `end_frame + 1` | OPEN |
| Q2 | Does lottie-web apply a style to the shapes the writer intends? | OPEN |

---

## Global Constraints

- **English only** in every file, comment, docstring, commit message and printed string. See `.claude/ai/AGENTS.md`.
- **No new required third-party dependency.** `jsonschema` is optional in the same way Pillow already is: try to import, skip with a printed note if absent.
- **Standard library only** in `moho2lottie.py` and every script under `tools/`.
- **Commit style:** plain imperative sentences, matching `git log`. Not Conventional Commits. No tool attribution, no AI co-author trailer.
- **Every document must carry a docstring.** New file, new class, new function, including private helpers. Match the density and tone of `moho2svg.py`, which explains *why* a constant is what it is.
- **`make gen` must keep the five tracked SVGs byte-identical** after every task. This is the regression gate for the whole plan, not just for Task 2.
- **Never silently skip a feature.** Anything not exported increments a counter that is printed to stderr at the end of an export.
- Coordinates are written with 3 decimal places, matching `build_path_d`'s `f"{x:.3f}"`.

---

## File structure

| File | Responsibility |
|---|---|
| `moho2svg.py` (modify) | Gains `build_path_bezier()` and `walk_render_tree()`. Nothing else changes; its own output must not move by a byte. |
| `moho2lottie.py` (create) | The Lottie writer and its CLI. One file with `# ==== SECTION ====` banners, mirroring how `moho2svg.py` is organised. |
| `tools/check_bezier_roundtrip.py` (create) | Proves `build_path_bezier()` describes the same curve as `build_path_d()`. |
| `tools/check_lottie_geometry.py` (create) | Proves an emitted Lottie file draws the same coordinates, in the same order, as the SVG writer at the same frame. |
| `Makefile` (modify) | Adds `gen-lottie`, `check-lottie`. |
| `.gitignore` (modify) | Adds `lottie-out/`. |

---

## Task 1: A Bezier path builder beside the SVG one

**Status:** DONE — `check_bezier_roundtrip.py` passes on all 19 sample documents; `make gen` leaves the five reference SVGs byte-identical.

**Files:**
- Modify: `moho2svg.py` — add `build_path_bezier()` directly after `build_path_d()`
- Create: `tools/check_bezier_roundtrip.py`

**Interfaces:**
- Consumes: `PathTracer.trace(geometries, edges) -> list[TracedSegment]`, where `TracedSegment` has `p0, c1, c2, p1, is_new_subpath, reversed, curve, segment`; `Vec2` has `.x`, `.y`, `.distance_to(other)`.
- Produces: `build_path_bezier(geometries, edges, to_px, visible_only=False) -> list[dict]` — **one dict per subpath**, each `{"v": [[x, y], ...], "i": [[dx, dy], ...], "o": [[dx, dy], ...], "c": bool}`. A shape with two disconnected outlines returns two dicts, and the writer emits one Lottie `sh` element per dict.

- [x] **Step 1: Write the failing check script**

Create `tools/check_bezier_roundtrip.py`:

```python
#!/usr/bin/env python3
"""Check that build_path_bezier() describes the same curve as build_path_d().

Both are built from the same PathTracer output, so they must agree exactly.
This converts each emitted Lottie bezier back to absolute cubic control
points and compares them against the traced segments the SVG writer uses.

Exit status is 0 when every shape agrees, 1 otherwise.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moho2svg import (Channel, Exporter, PathTracer, build_deform_chain,
                      build_path_bezier, load_document)

MOHO_DIR = "moho"
FRAMES = [0.0, 7.0, 23.0]

# build_path_bezier() rounds to 3 decimals, matching build_path_d()'s
# f"{x:.3f}", and its tangents are DIFFERENCES of two rounded values, so a
# rebuilt control point can be off by up to two half-ulps of 0.001.  The
# tolerance has to sit above that, or a correct implementation fails this
# check.  It is still tight enough to catch any real geometry mistake, which
# would be off by pixels, not by a thousandth of one.
TOLERANCE = 3e-3


def absolute_segments(bezier):
    """Rebuild absolute (p0, c1, c2, p1) tuples from one Lottie bezier dict.

    Lottie stores `i` and `o` relative to their own vertex, so a segment
    running from vertex k to vertex k+1 has control points v[k] + o[k] and
    v[k+1] + i[k+1].
    """
    v, tin, tout, closed = bezier["v"], bezier["i"], bezier["o"], bezier["c"]
    count = len(v) if closed else len(v) - 1
    out = []
    for k in range(count):
        nxt = (k + 1) % len(v)
        out.append((
            (v[k][0], v[k][1]),
            (v[k][0] + tout[k][0], v[k][1] + tout[k][1]),
            (v[nxt][0] + tin[nxt][0], v[nxt][1] + tin[nxt][1]),
            (v[nxt][0], v[nxt][1]),
        ))
    return out


def traced_segments(geometries, edges, to_px):
    """The same segments the SVG writer walks, mapped to pixels."""
    out = []
    for seg in PathTracer.trace(geometries, edges):
        pts = [to_px(p) for p in (seg.p0, seg.c1, seg.c2, seg.p1)]
        out.append(tuple((p.x, p.y) for p in pts))
    return out


def check_document(path):
    """Compare both builders over one document. Returns the failure count."""
    Channel.reset_cache()
    doc = load_document(path)
    failures = 0
    for frame in FRAMES:
        exp = Exporter(doc)
        for ancestors, layer in doc.vector_layers():
            exp._active_actions = exp._active_actions_along(ancestors, frame)
            exp._layer_scale = exp._full_chain_matrix(ancestors, layer, frame).uniform_scale() or 1.0
            geometries = exp._curve_geometries(layer.mesh, frame)
            chain = build_deform_chain(ancestors, layer, frame, exp)
            to_px = exp._deformed_pixel_mapper(chain, frame, layer)
            exp._active_actions = []
            for index, shape in enumerate(layer.mesh.shapes):
                if not shape.edges:
                    continue
                expected = traced_segments(geometries, shape.edges, to_px)
                got = []
                for bezier in build_path_bezier(geometries, shape.edges, to_px):
                    got.extend(absolute_segments(bezier))
                if len(got) != len(expected):
                    print(f"  {os.path.basename(path)} {layer.name} shape[{index}] "
                          f"frame {frame}: {len(got)} segments, expected {len(expected)}")
                    failures += 1
                    continue
                for a, b in zip(got, expected):
                    if any(abs(x - y) > TOLERANCE for pa, pb in zip(a, b)
                           for x, y in zip(pa, pb)):
                        print(f"  {os.path.basename(path)} {layer.name} "
                              f"shape[{index}] frame {frame}: coordinates differ")
                        failures += 1
                        break
    return failures


def main():
    targets = sys.argv[1:] or sorted(
        os.path.join(MOHO_DIR, f) for f in os.listdir(MOHO_DIR)
        if f.endswith((".mohoproj", ".animeproj"))
    )
    failures = 0
    for path in targets:
        failures += check_document(path)
        print(f"checked {os.path.basename(path)}")
    if failures:
        print(f"\nFAIL: {failures} shape(s) disagree")
        return 1
    print(f"\nOK: both path builders agree on every shape in {len(targets)} document(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 2: Run it to verify it fails**

Run: `python3 tools/check_bezier_roundtrip.py moho/Bandit.mohoproj`
Expected: FAIL with `ImportError: cannot import name 'build_path_bezier' from 'moho2svg'`

- [x] **Step 3: Implement `build_path_bezier()`**

Add to `moho2svg.py` directly after `build_path_d()`:

```python
def build_path_bezier(geometries: list[CurveGeometry], edges: Sequence[Edge],
                       to_px: Callable[[Vec2], Vec2],
                       visible_only: bool = False) -> list[dict]:
    """Build one shape's outline as Lottie bezier dicts - the Lottie
    counterpart of build_path_d().

    Returns ONE dict per subpath, because Lottie's `sh` shape element holds
    exactly one bezier: a shape whose outline falls into two disconnected
    runs becomes two `sh` elements in the same group.  build_path_d() writes
    the same break as a second "M" inside one `d` string.

    Lottie's `i` and `o` are the in/out tangents *relative to their own
    vertex*, so a segment leaving vertex k contributes `o[k] = c1 - p0` and
    the vertex it arrives at gets `i[k+1] = c2 - p1`.  A vertex shared by two
    segments therefore takes `o` from the outgoing segment and `i` from the
    incoming one.

    `visible_only` skips segments currently hidden by CurvePoint.segments_on,
    exactly as build_path_d() does, starting a fresh subpath after each gap.
    """
    traced = PathTracer.trace(geometries, edges)
    out: list[dict] = []
    current: Optional[dict] = None
    first: Optional[Vec2] = None
    last: Optional[Vec2] = None

    def close_current() -> None:
        """Finish the subpath being built, marking it closed when it returns
        to its own start.

        A closed Lottie bezier does not repeat the first vertex, so the
        duplicate endpoint is dropped - but its incoming tangent is the
        wrap-around segment's control point and must be carried onto the
        surviving first vertex before the drop, or the last curve of a closed
        shape flattens into a straight line.
        """
        nonlocal current
        if current is None:
            return
        if len(current["v"]) > 1 and first is not None and last is not None \
                and last.distance_to(first) < 1e-9:
            current["c"] = True
            current["i"][0] = current["i"][-1]     # carry the wrap-around tangent
            current["v"].pop()
            current["i"].pop()
            current["o"].pop()
        out.append(current)
        current = None

    for seg in traced:
        if visible_only and not geometries[seg.curve].segments[seg.segment].on:
            close_current()
            last = None
            continue
        if current is None or last is None or last.distance_to(seg.p0) > 1e-9:
            close_current()
            p0 = to_px(seg.p0)
            current = {"v": [[round(p0.x, 3), round(p0.y, 3)]],
                        "i": [[0.0, 0.0]], "o": [[0.0, 0.0]], "c": False}
            first = seg.p0
        p0, c1, c2, p1 = (to_px(seg.p0), to_px(seg.c1),
                           to_px(seg.c2), to_px(seg.p1))
        current["o"][-1] = [round(c1.x - p0.x, 3), round(c1.y - p0.y, 3)]
        current["v"].append([round(p1.x, 3), round(p1.y, 3)])
        current["i"].append([round(c2.x - p1.x, 3), round(c2.y - p1.y, 3)])
        current["o"].append([0.0, 0.0])
        last = seg.p1
    close_current()
    return out
```

The wrap-around tangent carry inside `close_current` is the only subtle line
in the whole function. Dropping the repeated final vertex without it makes the
last curve of every closed shape render as a straight line — a defect that is
easy to miss on a rounded shape and obvious on a circle.

- [x] **Step 4: Run the check to verify it passes**

Run: `python3 tools/check_bezier_roundtrip.py`
Expected: `OK: both path builders agree on every shape in 19 document(s)`

If a closed shape fails on its first or last segment, the wrap-around tangent
carry in `close_current` is wrong — that is the only place the two builders
can legitimately disagree.

- [x] **Step 5: Verify the SVG output did not move**

Run: `make gen && git diff --stat -- svg/`
Expected: empty output.

- [x] **Step 6: Commit**

```bash
git add moho2svg.py tools/check_bezier_roundtrip.py
git commit -m "Add a Lottie bezier path builder beside the SVG one"
```

---

## Task 2: One shared tree walk

**Status:** DONE — see the note below on why the shape changed from this
task's original sketch, and read it before starting Task 3.

**Files:**
- Modify: `moho2svg.py` — `Exporter.export_document` (the `emit` closure) and a new module-level `RenderItem` dataclass plus `walk_render_tree()`

**⚠ Interface changed from the original sketch below — read this first.**
While extracting the walk, a real correctness hazard turned up: 8 of the 201
containers across the sample corpus have **zero drawable descendants**
(visible, not `edit_only`, and — for a `SwitchLayer` — the active child), and
Moho still draws such a container as an **empty `<g></g>`**. Four of the five
byte-identical-gated documents contain one. A `RenderItem` stream that only
yielded actual mesh layers would have no way to signal "an empty container
was here", so `export_document` could not have reconstructed that empty
`<g>` — the gate would have failed on 4 of 5 documents, not passed silently.

The fix was to make `walk_render_tree` yield a small **event stream**
instead of a flat "one item per mesh layer" list — `"enter"` before a
container's children, `"mesh"` per drawable mesh layer, `"exit"` after —
mirroring the bracket structure `emit()` already had. `export_document`
reconstructs its `<g>` nesting (including empty ones) by consuming this
stream recursively, using a **single shared iterator**: a nested call reads
directly off the same iterator via `for item in it`, and returning from that
call leaves the iterator exactly where the caller's own loop resumes — the
standard way to consume a flattened bracket-matched sequence without
rebuilding a stack by hand.

**Consumers written after this task (Task 3 onward) must filter for
`item.event == "mesh"`** — the stream also contains `"enter"`/`"exit"`
events that carry no `geometries`/`to_px` at all.

**Interfaces:**
- Consumes: everything `export_document` already used — `Exporter._mask_sources`, `Layer.switch_active_child`, `Layer.local_matrix`, `build_deform_chain`, `Exporter._deformed_pixel_mapper`, `Exporter._curve_geometries`.
- Produces:
  ```python
  @dataclass
  class RenderItem:
      event: str                              # "enter" | "mesh" | "exit"
      layer: Optional[Layer]                  # None only for "enter"/"exit" of the virtual root
      ancestors: tuple                        # root-first, ending in the enclosing container
      depth: int                              # len(ancestors) — true tree depth, NOT an SVG indent
      exempt: bool = False                    # masking in (1, 2), relative to the PARENT's mask
      mask_sources: Sequence = ()             # only non-empty on "enter"; this container's OWN group_mask contribution
      geometries: Optional[list] = None       # only set on "mesh"
      to_px: Optional[Callable] = None        # only set on "mesh"

  def walk_render_tree(exporter, frame, include_hidden=False) -> Iterator[RenderItem]
  ```
  A `"mesh"` `RenderItem` is yielded with `exporter._active_actions` already
  set to the correct Smart Bone context, and that context is **left set
  across the yield** — cleared only when the consumer asks for the next
  item. A consumer must finish evaluating that layer's own style channels
  before advancing the iterator.

- [x] **Step 1: Capture the current output as the reference**

Actually run (this repository has no `git stash` in flight; copy instead of
stashing):
```bash
make gen && cp -R svg /tmp/svg-before
```
Confirmed: `/tmp/svg-before` held the five reference SVGs before this task's
edit.

- [x] **Step 2: Extract the walk**

Moved `emit`'s body into `walk_render_tree`'s nested `walk()`, changed to
yield `RenderItem` events instead of building SVG strings, exactly as
described in the "interface changed" note above. Every decision preserved in
place and in order:

- the `not layer.visible and not include_hidden` skip
- the `layer.edit_only and not include_hidden` skip
- the `active_child is not None and layer is not active_child` skip
- the `world.compose(layer.local_matrix(frame, self))` composition
- the recursion into `layer.is_container`

**The `_active_actions` set/clear ordering is preserved exactly, by
construction**: `exporter._active_actions = []` sits textually AFTER the
`yield RenderItem("mesh", ...)` line, so it only executes once the generator
is *resumed* — i.e., once the consumer has finished processing that item and
asks for the next one. This reproduces the original code's ordering (clear
happens right after `_render_mesh` finishes, before the next layer) without
the generator needing to know anything about what the consumer did with the
item. See `moho-export-pipeline.md` § 9.3 for why this ordering is
load-bearing rather than incidental.

- [x] **Step 3: Rewrite `export_document` as a consumer**

`export_document` keeps its `<g>` nesting, mask emission and `--flat`
handling, in a new `render_scope(enter_item, pad_depth)` closure that
recursively consumes the shared iterator. `pad_depth` is tracked separately
from `RenderItem.depth`, because whether a nested container's own recursion
actually increases SVG indentation depends on `nested_groups`/`member_clip`
— a presentation choice `walk_render_tree` has no opinion about.

- [x] **Step 4: Verify byte-identical output**

Ran: `make gen && git diff --stat -- svg/ && diff -r svg /tmp/svg-before`.
**Both produced no output** — confirmed byte-identical on all five gated
documents, including `AddBone`, `SketchBone` and `WhatIsBone`, three of the
four gated documents that contain an empty container.

Went further than the plan's own gate: exported all **19** sample documents
with `--combined` under both the pre-extraction code (checked out via a
throwaway `git worktree` at the Task 1 commit) and the post-extraction code,
and diffed the two output sets. **Byte-identical on all 19**, including the
5 additional non-gated documents that also contain an empty container
(`BoneStrengthTool.animeproj` ×2, `ReparentBone.animeproj`,
`SelectandReparentBoneTool.animeproj`, `SketchBone.animeproj`'s second
instance). This is stronger evidence than the plan asked for, specifically
because the empty-container hazard was not something the plan anticipated.

- [x] **Step 5: Verify every document still exports**

Ran:
```bash
for f in moho/*.mohoproj moho/*.animeproj; do
  python3 moho2svg.py "$f" --combined /tmp/out.svg --brush-dir "" >/dev/null || echo "FAILED $f"
done
```
No `FAILED` lines.

- [x] **Step 6: Commit**

```bash
git add moho2svg.py
git commit -m "Extract the layer tree walk so a second exporter can reuse it"
```

---

## Task 3: A Lottie file with one static frame

**Status:** DONE — with two scope expansions found necessary while
implementing, neither in the original sketch below. Read the note before
Step 3.

**⚠ Scope expanded beyond this task's original sketch — read this first.**
The plan's own code sketch for `_build_shapes` turned out to be wrong in a
way that would have mis-rendered the MAJORITY of stroked shapes, not an edge
case:

1. **Tapered strokes.** Measured: **1,065 of 1,615 outlined shapes (66%)**
   across the sample corpus have a varying width along their length. The
   design doc lists tapered strokes as in-scope for v1 ("already converts
   these to a filled outline, so they arrive as ordinary geometry"), but the
   sketch's `_mean_point_width` fallback (`widths[0] if untapered else 1.0`)
   would have drawn a plain uniform stroke at the WRONG width for two-thirds
   of all stroked shapes — silently, with no warning, contradicting this
   plan's own Global Constraint. Fixed by adding
   `TaperedStrokeOutliner.build_bezier()` (a Lottie-native sibling of the
   existing SVG-only `build()`), which reuses `build()`'s own offset-curve
   sampling technique but writes each vertex with ZERO tangents (a polyline,
   matching `build()`'s own straight-line SVG segments at the same sample
   density) and approximates `build()`'s rounded-cap SVG arc with
   `cap_segments` straight segments (Lottie's bezier format has no arc
   primitive). `TaperedStrokeOutliner.build()` and `_outline_one_run()`
   themselves are UNTOUCHED — only `_traced_runs()` was extracted from
   `build()` (a verbatim, behavior-preserving move: pure data grouping, no
   float formatting or SVG-specific logic) so both writers group runs
   identically without duplicating that part. Verified: `make gen` still
   byte-identical (`Bandit.svg`/`ReparentBone.svg` exercise 93/78 taper
   outline elements between them), and `build_bezier()` produces correct
   two-loop output for both a closed ring case and an open capsule case,
   checked directly against real shapes in `SketchBone.animeproj`.

2. **Shape-element ordering is a real open question, not a formatting
   choice.** The sketch put one shape's fill "sh" elements, an "fl", the
   outline's "sh" elements, and an "st"/second "fl" all in ONE Lottie group.
   Whether a paint operator in Lottie's `it` array applies only to
   IMMEDIATELY preceding "sh" siblings or to ALL of them is explicitly
   **unverified** — [`lottie-and-thorvg.md`](lottie-and-thorvg.md) section
   6.4 says this ordering rule is not in the schema. Guessing wrong here
   would mean a shape's fill and outline paint operators cross-contaminate
   (e.g. the outline's stroke also stroking the fill's own path). Sidestepped
   entirely by giving each shape up to TWO SEPARATE Lottie groups — one for
   fill, one for outline — since a paint operator is unambiguously scoped to
   its OWN group. The outline group is listed first (Lottie, like Moho/SVG,
   paints earlier entries on top), matching `_render_shape`'s own fill-under/
   outline-over paint order.

Also added, not in the original sketch: a `close: bool = True` parameter on
`build_path_bezier()` (Task 1), needed because a plain stroke must NOT close
its path the way a fill does — see `build_path_d()`'s own docstring for why
Moho's own exporter never closes a stroke path either — and a `"gradient"`
warning counter, since `SS_Gradient2` fills are drawn as a flat colour until
Task 5 and the plan's own Global Constraint forbids a silent, uncounted gap.

**Files:**
- Modify: `moho2svg.py` — `Document.__init__`/`.from_raw` (`fps`/`start_frame`/`end_frame`), `build_path_bezier` (new `close` parameter), `TaperedStrokeOutliner` (`_traced_runs` extracted, `build_bezier`/`_sample_offsets`/`_polygon_bezier`/`_arc_points`/`_outline_one_run_bezier` added)
- Create: `moho2lottie.py`

**Interfaces:**
- Consumes: `walk_render_tree` and `build_path_bezier` from Tasks 1 and 2; `Color.from_raw`, `ResolvedStyle.line_cap_name`, `Exporter._stroke_width_px`, `Exporter.tapered_outliner.build_bezier`, `Shape.has_fill`/`.has_outline`/`.combo_mode`/`.style`/`.edges`.
- Produces:
  ```python
  class LottieExporter:
      def __init__(self, document: Document, settings: RenderSettings = None)
      def export(self, frames: Sequence[float]) -> dict
  ```
  A one-element `frames` list produces a still; Task 4 passes the full range.

- [x] **Step 1: Add the three document accessors**

In `moho2svg.py`, `Document.__init__` and `Document.from_raw` currently keep
only `width`, `height`, `layers`, `styles`, `format_version`. Add `fps`,
`start_frame` and `end_frame`, read from the same `project_data` dict:

```python
        doc = cls(pd["width"], pd["height"], layers, styles, raw.get("version"),
                  fps=pd.get("fps", 24.0),
                  start_frame=pd.get("start_frame", 0),
                  end_frame=pd.get("end_frame", 0))
```

Document them: `fps` is the playback rate, `start_frame`/`end_frame` are the
document's own render range in absolute frame numbers, and both are inclusive
on the Moho side.

- [x] **Step 2: Write the failing check**

Run: `python3 moho2lottie.py moho/Bandit.mohoproj --out /tmp/bandit.json --frame 25`
Expected: FAIL with `No such file or directory: 'moho2lottie.py'`

- [x] **Step 3: Write `moho2lottie.py`**

Structure it with the same banner style `moho2svg.py` uses:

```python
#!/usr/bin/env python3
"""Export Moho vector artwork to a Lottie JSON animation.

Reuses moho2svg.py's geometry pipeline in full: the same document model, the
same Bezier reconstruction, the same path tracing, the same bone deformation.
Only the output stage differs.

Every deformation is BAKED into canvas-pixel vertex positions, so every Lottie
layer carries an identity transform and no affine matrix is ever decomposed
into Lottie's anchor/position/scale/rotation/skew form.  See
docs/moho-to-lottie-design.md for why, and for what that costs in file size.
"""
```

The writer, in order:

```python
LOTTIE_VERSION = "5.7.0"


class LottieExporter:
    """Builds a Lottie document from a Moho Document.

    Stateful in the same way Exporter is: it holds a per-export warning
    counter and reuses one Exporter for geometry.  Construct one per export
    call, never share across concurrent exports.
    """

    def __init__(self, document, settings=None):
        self.document = document
        self.exporter = Exporter(document, settings)
        self.warnings = Counter()

    def export(self, frames):
        """Return the Lottie document as a plain dict.

        `frames` is every frame to sample, in ascending order.  A single
        frame produces static paths; several produce path keyframes.
        """
        layers = self._build_layers(frames)
        return {
            "v": LOTTIE_VERSION,
            "fr": float(self.document.fps),
            "ip": float(self.document.start_frame),
            # Moho's end_frame is inclusive, Lottie's op is the first frame
            # NOT shown - see docs/moho-to-lottie-design.md section 9 item 1,
            # this is an inference and is on the list to confirm.
            "op": float(self.document.end_frame + 1),
            "w": int(self.document.width),
            "h": int(self.document.height),
            "assets": [],
            "layers": layers,
        }
```

Layer building, for this task, samples one frame and emits static paths:

```python
    def _build_layers(self, frames):
        """One Lottie shape layer per Moho mesh layer, in Lottie draw order.

        walk_render_tree yields an EVENT STREAM ("enter"/"mesh"/"exit"), not
        one item per mesh layer - see Task 2's note on why. Only "mesh"
        events carry geometries/to_px; "enter"/"exit" exist purely so a
        consumer that needs Moho's nested <g> structure (export_document)
        can reconstruct it, including empty containers. This writer flattens
        everything anyway (every layer gets an identity transform), so it
        simply ignores "enter"/"exit" and keeps only "mesh" events.

        Moho draws its layer list back to front, which is the order
        walk_render_tree yields "mesh" events in.  Lottie draws the FIRST
        layer in the list on top, so the finished list is reversed.  This is
        the single easiest thing in the whole writer to get wrong without
        noticing: the artwork still looks right, just with the wrong parts
        in front.
        """
        collected = []
        for item in walk_render_tree(self.exporter, frames[0]):
            if item.event != "mesh":
                continue
            shapes = self._build_shapes(item, frames)
            if shapes:
                collected.append(self._shape_layer(item.layer.name, shapes))
        collected.reverse()                  # Moho back-to-front -> Lottie front-to-back
        for index, layer in enumerate(collected, start=1):
            layer["ind"] = index
        return collected

    def _shape_layer(self, name, shapes):
        """A Lottie shape layer with an identity transform.

        Identity is correct because the geometry is already baked into canvas
        pixels, which is also Lottie's own coordinate system: pixels, y down,
        origin at the top left.
        """
        return {
            "ty": 4, "nm": name, "ks": identity_transform(),
            "ao": 0, "shapes": shapes,
            "ip": float(self.document.start_frame),
            "op": float(self.document.end_frame + 1),
            "st": 0.0,
        }
```

`identity_transform()` is a function, not a module constant, so no two layers
ever share one mutable dict:

```python
def identity_transform():
    """Lottie's neutral transform: no anchor, no move, no rotation, full size
    and full opacity."""
    return {"a": {"a": 0, "k": [0, 0]}, "p": {"a": 0, "k": [0, 0]},
            "s": {"a": 0, "k": [100, 100]}, "r": {"a": 0, "k": 0},
            "o": {"a": 0, "k": 100}}
```

Per-shape building resolves style the same way `ShapeGroupRenderer._render_shape`
does, so both exporters read colour and width identically:

```python
    def _build_shapes(self, item, frames):
        """Every Moho shape of one layer, as Lottie group elements."""
        out = []
        exp, frame = self.exporter, frames[0]
        for shape in item.layer.mesh.shapes:
            if not shape.edges:
                continue
            if shape.combo_mode not in (0, None):
                self.warnings["combo_mode"] += 1
            if shape.style.brush_name:
                self.warnings["brush"] += 1
            beziers = build_path_bezier(item.geometries, shape.edges, item.to_px)
            if not beziers:
                continue
            elements = [{"ty": "sh", "ks": {"a": 0, "k": b}} for b in beziers]
            if shape.has_fill:
                color = Color.from_raw(exp.eval(shape.style.fill_color, frame))
                elements.append({"ty": "fl",
                                  "c": {"a": 0, "k": [color.r, color.g, color.b]},
                                  "o": {"a": 0, "k": color.a * 100}})
            if shape.has_outline:
                width = exp._stroke_width_px(
                    exp.eval(shape.style.line_width, frame),
                    self._mean_point_width(item, shape, frame))
                color = Color.from_raw(exp.eval(shape.style.line_color, frame))
                elements.append({"ty": "st",
                                  "c": {"a": 0, "k": [color.r, color.g, color.b]},
                                  "o": {"a": 0, "k": color.a * 100},
                                  "w": {"a": 0, "k": width},
                                  "lc": LINE_CAPS.get(shape.style.line_caps, 2),
                                  "lj": 2})
            elements.append({"ty": "tr", **identity_transform()})
            out.append({"ty": "gr", "nm": shape.name or "", "it": elements})
        return out
```

`LINE_CAPS` maps the string `ResolvedStyle.line_cap_name()` already returns —
the same value the SVG writer puts in `stroke-linecap` — onto Lottie's `lc`
integer: `{"butt": 1, "round": 2, "square": 3}`. Deriving it from
`line_cap_name()` rather than from the raw `line_caps` int means the two
exporters cannot drift apart.

`_mean_point_width` mirrors the width lookup `ShapeGroupRenderer` performs for
the shape's own edge points, so the stroke width fed to `_stroke_width_px` is
the one the SVG writer would use.

Imports needed at the top of the file: `argparse`, `json`, `sys`, `Counter`
from `collections`, and from `moho2svg` — `Color`, `Exporter`, `RenderSettings`,
`build_path_bezier`, `load_document`, `walk_render_tree`.

The CLI takes `project`, `--out`, `--frame`, and `--include-hidden`, parsed with
`argparse`, and writes `json.dump(..., separators=(",", ":"))`.

- [x] **Step 4: Run it**

Run: `python3 moho2lottie.py moho/Bandit.mohoproj --out /tmp/bandit.json --frame 25`
Expected: writes the file and prints its size and the warning summary.

- [x] **Step 5: Sanity-check the structure**

Run:
```bash
python3 -c "
import json; d=json.load(open('/tmp/bandit.json'))
print('fr',d['fr'],'ip',d['ip'],'op',d['op'],'w',d['w'],'h',d['h'])
print('layers',len(d['layers']))
print('first layer name', d['layers'][0]['nm'])
"
```
Expected: `fr 24.0 ip 25.0 op 128.0 w 1920 h 1080`, a non-zero layer count, and
a first-layer name that is the **frontmost** layer in Moho, not the backmost.

- [x] **Step 6: Commit**

```bash
git add moho2lottie.py moho2svg.py
git commit -m "Write a static Lottie frame from a Moho document"
```

---

## Task 4: Path keyframes across the frame range

**Status:** DONE — two real bugs were found and fixed while implementing
this, plus one earlier measurement (from Task 3's own completion notes) was
found to be **wrong** and is corrected below. Read all three before touching
this code again.

**⚠ Bug 1 (real, serious): `to_px()` reads exporter state LAZILY, at call
time, not at closure-creation time.** The first implementation of
`_build_layers` walked every frame first, collecting a `RenderItem` per
(layer, frame) pair into a dict, and only afterwards looped back over them
calling `.to_px()`/`build_path_bezier()`. This is wrong:
`Exporter._skin_data`'s cache key is `(bone_layer, frame,
tuple(self._active_actions))`, read at the moment `to_px(p)` actually runs,
not baked into the closure when `walk_render_tree` builds it. By the time
the second pass ran, `exporter._active_actions` held whatever the LAST
frame/layer processed had left it as - every geometry call silently used the
WRONG Smart Bone context. `tools/check_lottie_geometry.py` caught this
immediately: coordinates off by hundreds of pixels (e.g. x=805.9 expected,
x=-287.5 got), not a rounding-sized discrepancy. **Fixed** by restructuring
so every `to_px()`/`exp.eval()` call happens synchronously, inside the same
`for item in walk_render_tree(...)` iteration that produced `item` - see
`_accumulate_frame`'s docstring. This is the single most important
correctness fact about this file: **never hold a `RenderItem` past asking
`walk_render_tree` for its successor.**

**⚠ Bug 2 (real, mine): conflating "is this shape tapered" with "is its
`outline_kind` == 'stroke'".** A brush-styled shape's `outline_kind` is
*always* `"stroke"` (the brush fallback - see `_new_accumulator`), even when
its width genuinely varies along its length. An early per-frame consistency
check compared each frame's *actual* tapered-ness against
`outline_kind == "stroke"` instead of against the *stored* tapered flag, so
it flagged every brush-and-tapered shape as "changed" on literally its
second frame. **12 of 19 sample documents raised on the first run** - AddBone,
AnglePositionScale, BoneParenting, ControlBones, IK-FK, IndependentAngle,
MaximumIKStrethching, OffsetBoneTool, SketchBone, TargetBone, WhatIsBone (one
more, mid-list, not re-listed to avoid transcription error - see the full
first-run output in the session transcript). **Fixed** by storing the raw
`tapered` boolean in the accumulator and comparing against *that*,
independent of `outline_kind`.

**⚠ Correction to Task 3's own completion notes: the "6 of 63 layers vary in
scale by 21%" measurement was WRONG.** It grouped scale samples by
`layer.name`, which conflated distinct layers sharing a name -
`WhatIsBone.animeproj` has three separately-modelled layers all named
"goz-sol", each with its OWN constant scale (1.0, 0.79, 1.0), which looked
like one layer whose scale changes over time. Re-measured keyed by layer
IDENTITY: **0 of 103 layers in `WhatIsBone.animeproj`, 0 of 21 in
`Bandit.mohoproj`, 0 of 86 in `SketchBone.animeproj` actually vary** across
their own full frame range. The `_scalar_property`/per-frame stroke-width
machinery this "finding" motivated is **kept anyway** - a genuinely
scale-animated bone is a real Moho capability, not a fabricated edge case,
and the static branch already covers everything actually observed in this
corpus - but the docstring's own claim is corrected to say so, not repeat
the wrong number.

**Also found, not a bug: `SketchBone.animeproj` cannot export its full frame
range yet.** Its `agiz` (mouth) layer is a `SwitchLayer` whose active child
changes across the animation (lip sync), so the SET of drawable layers
itself differs frame to frame - exactly the case `_build_layers`'s own
docstring already anticipated and named as **Task 7's job**. The exporter
correctly raises a clear `ValueError` naming the layer rather than silently
producing a wrong file. **18 of 19 sample documents export their full range
successfully; `SketchBone.animeproj` is expected to start working once Task
7 lands**, and was not force-fixed here.

**Files:**
- Modify: `moho2lottie.py` — `_build_layers` restructured around eager per-frame accumulation (`_accumulate_frame`, `_new_accumulator`, `_finalize_shapes`, `_finalize_outline_group`), plus `_path_property`, `_scalar_property`, `_sh_elements`, `_assert_stable`
- Create: `tools/check_lottie_geometry.py`

**Interfaces:**
- Produces: `LottieExporter.export(frames)` now emits `{"a": 1, "k": [...]}` for any path (or, for a plain stroke's width, any scalar) whose value moves, and keeps `{"a": 0, "k": ...}` for one that does not.
- The accumulator dict built by `_new_accumulator` (one per shape, keyed by position within `Mesh.shapes` — stable across frames) carries: `name`, `has_fill`, `fill_color`, `fill_per_frame`, `outline_kind` (`None`/`"taper"`/`"stroke"`), `tapered` (the RAW boolean — see Bug 2 above), `line_width`, `outline_color`, `outline_cap`, `outline_per_frame`, `outline_width_per_frame`.

- [x] **Step 1: Write the failing check script**

Create `tools/check_lottie_geometry.py`. It reads an emitted Lottie file, pulls
every path value at frame N, and compares it against `build_path_bezier` run
directly at frame N:

```python
#!/usr/bin/env python3
"""Check that an emitted Lottie file holds the same geometry, in the same
order, that the SVG writer draws at the same frame.

This needs no Lottie player and no third-party package.  It also catches a
reversed layer order, because it compares shapes in emitted order.

Usage: check_lottie_geometry.py <project> <lottie.json> [frame ...]
Exit status is 0 when every shape at every checked frame agrees.
"""
```

For each checked frame it must:

1. walk the document with `walk_render_tree(exporter, frame)`, collect every
   shape's beziers, and **reverse the layer order** the same way the writer
   does;
2. walk the emitted file's `layers[*].shapes[*].it[*]` picking `ty == "sh"`
   elements, taking the static `k` or the keyframe whose `t` equals the frame;
3. compare `v`, `i`, `o` and `c` element by element with a `3e-3` tolerance —
   both sides come from `build_path_bezier`, so they are rounded the same way,
   but keep the same tolerance as `check_bezier_roundtrip.py` so the two
   scripts cannot disagree about what "equal" means;
4. print the layer name, shape index and frame of every disagreement.

Built with `--require-gradients`/`--require-masks` flags too, ahead of
Tasks 5/6, since the script's own frame-walking machinery is identical -
they currently only check that the emitted file contains a `"gf"` element
or `hasMask`/`masksProperties` when the source document has one, i.e. they
are a REMINDER that those tasks are not done yet, not a claim that they are.

- [x] **Step 2: Run it to verify it fails**

Run against the Task 3 single-frame file: FAILED as expected, on every
moving shape - confirmed the check script itself works before Step 3 made
it pass for the right reason.

- [x] **Step 3: Emit keyframes**

In `_build_shapes`, build each shape's bezier list **once per frame** and
compare. Rewrite the path element as:

```python
    def _path_property(self, per_frame, frames):
        """A Lottie path property: static when the geometry never moves,
        keyframed otherwise.

        Writing an unmoving shape once instead of once per frame is what keeps
        the file in single-digit megabytes rather than hundreds - measured at
        293 MB versus about 10 MB across this repository's sample documents.
        """
        if all(b == per_frame[0] for b in per_frame[1:]):
            return {"a": 0, "k": per_frame[0]}
        return {"a": 1,
                "k": [{"t": float(f), "s": [b]} for f, b in zip(frames, per_frame)]}
```

`_build_layers` samples every frame in the range and **asserts structural
stability** via `_assert_stable`: if a shape's vertex count or `c` flag
changes between frames, it raises a clear error naming the layer, the shape
name and the two frames. Measurement says this never happens (0 unstable of
2,659 shapes) - confirmed still true after this task's own changes, since
`_assert_stable` never fired across any of the 18 documents that exported
successfully.

The frame list is every integer in `[start_frame, end_frame]` (see
`main()`'s own default, added this task: previously `--frame` was required).

- [x] **Step 4: Re-run the geometry check**

Ran against `Bandit.mohoproj` (frames 25/40/60/87/127) and, going further
than the plan asked, `WhatIsBone.animeproj` (frames 1/60/120/180/240) and
`OffsetBoneTool.animeproj` (frames 1/12/24) - `OK` on every frame of every
document checked.

Also ran a full-corpus smoke export (`--out` with no `--frame`, i.e. the
whole range) across all 19 sample documents: **18 succeed**;
`SketchBone.animeproj` raises the SwitchLayer-visibility `ValueError`
described above, which is expected and deferred to Task 7.

- [x] **Step 5: Check the size against the design's estimate**

`Bandit.mohoproj`: 932,584 bytes raw, 35,218 bytes gzipped - well inside the
design's ~1.8 MB estimate.
`WhatIsBone.animeproj` (the largest, most-animated document, 227 frames):
18,641,999 bytes raw, 1,774,737 bytes gzipped (~10.5x) - large in absolute
terms but the STATIC-path optimisation is confirmed firing (verified
directly: `AddBone.animeproj`, whose main timeline has no animation at all,
produces byte-IDENTICAL output whether exported at a single frame or its
full 175-frame range - 291,936 bytes either way, 0 keyframed `"sh"`
elements, all 336 static).

- [x] **Step 6: Commit**

```bash
git add moho2lottie.py tools/check_lottie_geometry.py
git commit -m "Bake Moho deformation into Lottie path keyframes"
```

---

## Task 5: Gradients

**Status:** TODO

**Files:**
- Modify: `moho2lottie.py` — `_build_shapes`

**Interfaces:**
- Produces: a `"ty": "gf"` element replacing `"ty": "fl"` when
  `shape.style.fill_style["type"] == "SS_Gradient2"`.

- [ ] **Step 1: Find a document that exercises it**

Run:
```bash
python3 -c "
import json
d=json.load(open('moho/Bandit.mohoproj'))
n=0
def w(x):
    global n
    if isinstance(x,dict):
        if x.get('type')=='SS_Gradient2': n+=1
        for v in x.values(): w(v)
    elif isinstance(x,list):
        for v in x: w(v)
w(d); print('SS_Gradient2 occurrences:', n)"
```
Expected: a non-zero count. If it is zero, pick another document from `moho/`
before writing the check.

- [ ] **Step 2: Write the failing assertion**

Add to `tools/check_lottie_geometry.py` a `--require-gradients` flag that
fails when the emitted file contains no `"ty": "gf"` element while the source
document contains an `SS_Gradient2` style.

Run: `python3 tools/check_lottie_geometry.py moho/Bandit.mohoproj /tmp/bandit.json 25 --require-gradients`
Expected: FAIL — no gradient elements are emitted yet.

- [ ] **Step 3: Emit `gf`**

```python
    def _gradient_fill(self, shape, frame, item):
        """A Lottie gradient fill from Moho's SS_Gradient2 fill_style.

        Placement reuses whatever geometry the SVG writer computes for its
        <linearGradient>/<radialGradient>, so both exporters are wrong in the
        same way rather than differently - gradient placement precision is an
        existing KNOWN GAP in moho2svg.py, not something this writer fixes.
        """
        fill_style = shape.style.fill_style
        stops = []
        for stop in fill_style.get("gradients") or []:
            location = self.exporter.eval(stop["location"], frame)
            color = Color.from_raw(self.exporter.eval(stop["color"], frame))
            stops.extend([location, color.r, color.g, color.b])
        start, end = self._gradient_endpoints(shape, frame, item)
        return {"ty": "gf",
                 "t": 2 if fill_style.get("gradient_type") == 1 else 1,
                 "g": {"p": len(stops) // 4, "k": {"a": 0, "k": stops}},
                 "s": {"a": 0, "k": [start.x, start.y]},
                 "e": {"a": 0, "k": [end.x, end.y]},
                 "o": {"a": 0, "k": 100}}
```

Moho's `gradient_type` is 0 linear / 1 radial; Lottie's `t` is 1 linear /
2 radial, so the mapping is not identity — write it out rather than adding 1.

`_gradient_endpoints` derives the two points from the shape's pixel bounding
box and its `effect_scale`/`effect_rotation`, matching
`Exporter._build_gradient`.

- [ ] **Step 4: Re-run both checks**

Run:
```bash
python3 moho2lottie.py moho/Bandit.mohoproj --out /tmp/bandit.json
python3 tools/check_lottie_geometry.py moho/Bandit.mohoproj /tmp/bandit.json 25 40 --require-gradients
```
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add moho2lottie.py tools/check_lottie_geometry.py
git commit -m "Write Moho gradients as Lottie gradient fills"
```

---

## Task 6: Masking

**Status:** TODO

**Files:**
- Modify: `moho2lottie.py` — `_build_layers`, plus a new `_mask_properties`

**Interfaces:**
- Produces: `"hasMask": True` and a `"masksProperties"` list on every "mesh"
  layer that is not `exempt` and sits inside an "enter" scope whose own
  `mask_sources` is non-empty.

**Note:** `mask_sources` lives on the `"enter"` `RenderItem` (the container),
not on the `"mesh"` item itself — see Task 2's interface. `_build_layers`
must track the CURRENT mask context itself while consuming the event stream
(a small stack, pushed on `"enter"` when `mask_sources` is non-empty, popped
on the matching `"exit"`), exactly the way `export_document`'s
`render_scope` tracks `clip` for the same reason.

- [ ] **Step 1: Find the layers that must change**

Run:
```bash
python3 -c "
import json,os
from collections import Counter
c=Counter()
for f in sorted(os.listdir('moho')):
    if not f.endswith(('.mohoproj','.animeproj')): continue
    raw=json.load(open('moho/'+f))
    def w(n):
        if isinstance(n,dict):
            if 'masking' in n and 'uuid' in n: c[n['masking']]+=1
            for v in n.values(): w(v)
        elif isinstance(n,list):
            for v in n: w(v)
    w(raw)
print(dict(c))"
```
Expected: `{0: 714, 2: 93, 1: 62, 6: 6, 5: 1}` — 162 layers carry a non-zero
value.

- [ ] **Step 2: Write the failing assertion**

Add `--require-masks` to `tools/check_lottie_geometry.py`: it fails when the
source document has a container with `group_mask == 2` but the emitted file
contains no layer with `hasMask` true.

Run: `python3 tools/check_lottie_geometry.py moho/Bandit.mohoproj /tmp/bandit.json 25 --require-masks`
Expected: FAIL.

- [ ] **Step 3: Emit `masksProperties`**

```python
    def _mask_properties(self, mask_sources):
        """Moho's mask, as per-layer Lottie masks.  `mask_sources` is the
        CURRENT enclosing "enter" scope's own value (see the stack note
        above) - the caller has already checked the mesh item is not exempt.

        A Lottie track matte applies to exactly one layer, so masking a group
        of siblings the way Moho does would need a precomposition per group.
        Per-layer masks avoid that entirely: the geometry is already baked
        into canvas pixels and every layer transform is identity, so the mask
        paths are the same coordinates the SVG <mask> uses, with no
        adjustment at all.

        The cost is duplication - N masked siblings each carry a copy - which
        is small next to the shape geometry itself.  If these ever render
        wrongly, the documented fallback is a track matte plus a
        precomposition; see docs/moho-to-lottie-design.md section 6.1.
        """
        out = []
        for bezier, alpha in mask_sources:
            out.append({"inv": False, "mode": "a", "pt": {"a": 0, "k": bezier},
                         "o": {"a": 0, "k": alpha * 100}, "x": {"a": 0, "k": 0}})
        return out
```

In `_build_layers`, maintain `mask_stack = []`: push `item.mask_sources` on
every `"enter"` whose `mask_sources` is non-empty (push `None` otherwise, as
a placeholder so `"exit"` always has something to pop), pop on `"exit"`. For
a `"mesh"` item, the active mask is `next((m for m in reversed(mask_stack) if
m is not None), None)` — but re-check against `emit`'s own scoping first:
only the DIRECTLY enclosing container's mask ever applies to a child, never
a grandparent's (see `moho2svg.py`'s `member_clip` — it is computed fresh
per scope, not accumulated), so in practice only `mask_stack[-1]` matters,
never an outer entry. Apply it only when `not item.exempt`.

`Exporter._mask_sources` currently returns SVG path strings. Change it to
return the traced geometry alongside, or add a sibling that returns
`build_path_bezier` output for the same sources — do **not** parse the `d`
string back. Whichever is chosen, `export_document` must keep producing
byte-identical SVG.

A layer with `masking in (1, 2)` is exempt and gets no mask, exactly as the SVG
writer treats it.

- [ ] **Step 4: Re-run every check**

Run:
```bash
python3 moho2lottie.py moho/Bandit.mohoproj --out /tmp/bandit.json
python3 tools/check_lottie_geometry.py moho/Bandit.mohoproj /tmp/bandit.json 25 40 --require-masks
make gen && git diff --stat -- svg/
```
Expected: `OK`, and an empty `git diff`.

- [ ] **Step 5: Commit**

```bash
git add moho2lottie.py moho2svg.py tools/check_lottie_geometry.py
git commit -m "Carry Moho masking into Lottie as per-layer masks"
```

---

## Task 7: Switch layers

**Status:** TODO

**Files:**
- Modify: `moho2lottie.py` — `_build_layers`

**Interfaces:**
- Produces: one emitted layer per contiguous window in which a switch child is
  active, with `ip`/`op` set to that window.

- [ ] **Step 1: Confirm a document exercises it**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from moho2svg import load_document, LayerKind
import os
for f in sorted(os.listdir('moho')):
    if not f.endswith(('.mohoproj','.animeproj')): continue
    d = load_document('moho/'+f)
    n = sum(1 for _, l in d.walk() if l.kind is LayerKind.SWITCH)
    if n: print(f, n, 'switch layers')"
```
Expected: at least one document with a non-zero count.

- [ ] **Step 2: Write the failing assertion**

Extend `tools/check_lottie_geometry.py` so that, when checking a frame, it
requires that a switch layer's **inactive** children contribute no visible
layer at that frame — a layer whose `ip <= frame < op` must be the active one.

Run the check at two frames where the switch selects different children.
Expected: FAIL — the current writer emits every child for the whole range.

- [ ] **Step 3: Emit windows**

Because `walk_render_tree` already yields only the active child at the frame it
is called with, collect per-frame membership and turn it into windows:

```python
    def _switch_windows(self, frames):
        """For each layer under a SwitchLayer, the contiguous frame windows in
        which it is the active child.

        A SwitchLayer's key channel holds strings, which snap to the left
        keyframe with no interpolation, so the active child changes at
        discrete frames and every window is contiguous.  A child that becomes
        active twice is emitted twice, once per window, rather than being
        faded in and out.
        """
```

Every emitted layer's `ip`/`op` come from its window instead of the document
range.

- [ ] **Step 4: Re-run the checks**

Run the geometry check at the two frames from Step 2.
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add moho2lottie.py tools/check_lottie_geometry.py
git commit -m "Emit switch layer children as Lottie visibility windows"
```

---

## Task 8: Warnings, make targets and optional schema validation

**Status:** TODO

**Files:**
- Modify: `moho2lottie.py`, `Makefile`, `.gitignore`

- [ ] **Step 1: Print the warning summary**

At the end of an export, print each non-zero counter to **stderr**, one line
each, naming the count and what was dropped:

```
moho2lottie: 16 shapes with combo_mode != 0 drawn without boolean combination
moho2lottie: 15 ImageLayer layers skipped (vector-only exporter)
moho2lottie: 3600 styles naming a brush drawn as plain strokes
```

Counts are from the document being exported.

- [ ] **Step 2: Add optional schema validation**

```python
try:
    import jsonschema
except ImportError:                     # optional, exactly like Pillow
    jsonschema = None
```

`--validate` validates against `lottie/lottie.schema.json` when `jsonschema`
imports, and otherwise prints one line saying validation was skipped and how
to enable it. Note in the docstring that passing the schema is weak evidence:
the schema marks very little as required (`lottie-and-thorvg.md` § 2.5).

- [ ] **Step 3: Add the make targets**

```make
gen-lottie:
	mkdir -p lottie-out
	python3 moho2lottie.py moho/Bandit.mohoproj --out lottie-out/Bandit.json
	python3 moho2lottie.py moho/SketchBone.animeproj --out lottie-out/SketchBone.json
	python3 moho2lottie.py moho/WhatIsBone.animeproj --out lottie-out/WhatIsBone.json

check-lottie: gen-lottie
	python3 tools/check_bezier_roundtrip.py
	python3 tools/check_lottie_geometry.py moho/Bandit.mohoproj lottie-out/Bandit.json 25 60 100 127
```

- [ ] **Step 4: Ignore the output directory**

Add `lottie-out/` to `.gitignore`, beside the existing `svg-fast/` entries.

- [ ] **Step 5: Run everything**

Run: `make check-lottie && make gen && git diff --stat -- svg/`
Expected: all checks `OK`, and an empty `git diff`.

- [ ] **Step 6: Update the documentation**

Update `CLAUDE.md`'s command list and repository layout with `moho2lottie.py`,
`tools/` and `lottie-out/`. Change `moho-to-lottie-design.md`'s opening line —
it currently says nothing is implemented — and move any open question that the
work settled into a stated fact with the evidence that settled it.

- [ ] **Step 7: Commit**

```bash
git add moho2lottie.py Makefile .gitignore CLAUDE.md docs/moho-to-lottie-design.md
git commit -m "Add make targets and warning output for the Lottie exporter"
```

---

## After the plan

Two open questions from the design cannot be closed by anything in this plan,
because both need a real player:

1. **Is Lottie's `op` exclusive?** Task 3 assumes `end_frame + 1`.
2. **Does lottie-web apply a style to the shapes the writer intends?** The
   element order inside a group is conventional, not schema-defined.

Both are settled by loading `lottie-out/Bandit.json` in lottie-web beside
`svg/Bandit.svg`. Until that happens, the exporter is verified to be
*self-consistent with the SVG writer*, which is a strong claim, but not the
same as *correct in a player*. Say so in any report of this work.
