# Moho field probes

One row per FIELD THAT WAS ACTUALLY MEASURED, produced by
`tools/probe_field.py`. See that script's own module docstring for the
full method and its fail-closed exit codes; the summary that matters here:

**What a row means.** The named document was rendered twice with `Moho -r
... -f PNG` (headless, deterministic -- the same document/frame rendered in
two separate Moho processes produced byte-identical PNGs, which is what
licenses a plain SHA-256 comparison as sound evidence here, with no fuzzy
image diff and no Pillow dependency): once unmodified, once with `Field`
changed to `Value tried` at every place it occurs in the document (and any
listed precondition applied to both first). `AFFECTS RENDER` means the PNG
bytes differed; `inert` means they were byte-identical. Both are recorded --
an inert result is exactly as final as a positive one; see
`docs/superpowers/specs/2026-08-18-moho-field-coverage-design.md` section 6.

**What a row does NOT mean.** It is not a claim about the field's semantics
(what the value MEANS), only whether varying it changes pixels, at ONE frame
of ONE document, under the stated preconditions (`none` means no precondition
was applied -- a field gated behind one can still show `inert` here and be
correctly editable, e.g. behind `enable_physics` or `3d_mode`). A row is not
re-derived automatically if `moho2svg.py`'s reading model changes later --
the field-coverage registry cites the row as evidence at the time it was
written. No row is ever written for a probe that could not run, nor when the
value tried is a no-op (already what every touched site held) -- see the
script's own module docstring for the full exit-code table -- so every row
below is a completed, meaningful measurement. `Sites` is the touched-site
count for `Field` itself (mirroring the count already shown per precondition):
an `inert` result over 124 sites is strong evidence, over 1 site much weaker,
and this column is what lets a later reader tell those apart without re-running
anything.

**A residual risk no row here can rule out.** Nothing in this pipeline
confirms that the layer carrying `Field` was actually DRAWN at `Frame` --
hidden, `alpha` 0, or the untaken branch of a switch layer all produce the
same false `inert` shape as a genuine negative, because the changed field
never reached the canvas either way. Every `inert` row below is only as
trustworthy as its `Document`/`Frame` choice having actually exercised the
field -- this is recorded as a standing risk, not solved, since a manually
chosen frame gives the tool no way to know what should have been visible.

| Field | Value tried | Sites | Document | Frame | Preconditions | Result |
|---|---|---|---|---|---|---|
| `line_width` | `0.05` | 124 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `DocState_gridSize` | `40` | 1 | Bandit.mohoproj | 25 | none | inert |
| `3d_shading_density` | `90` | 21 | Bandit.mohoproj | 25 | none | inert |
| `3d_shading_density` | `90` | 21 | Bandit.mohoproj | 25 | `3d_mode=1` x21 | inert |
| `3d_mode` | `1` | 21 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `line_width` | `0.05` | 124 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `DocState_gridSize` | `40` | 1 | Bandit.mohoproj | 25 | none | inert |
| `line_width` | `0.05` | 124 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `line_width` | `0.06` | 124 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |

## Findings worth flagging to M3.1

`3d_mode=1` alone changes Bandit's render (see the `3d_mode` row above), so
the precondition itself is live, not a no-op -- ruling out the failure mode
task 10's brief specifically asked to watch for. But `3d_shading_density=90`
is STILL `inert` even with `3d_mode=1` set first (row 4 above), on the same
document/frame. That is itself a finding, not a wash: it means `3d_mode=1`
is necessary but evidently not SUFFICIENT to make `3d_shading_density`
observable -- Bandit's 21 `3d_options` layers likely need some further
condition (plausible candidates: a nonzero extrude/thickness value, a
camera angle where 3D shading would be visible at all, or a different
document with genuine 3D-mode content) before M3.1 spends its "one
precondition unlocks ten keys" budget on the other nine keys assumed to
sit behind this same flag. Investigate the actual precondition set before
probing the remaining nine.

The duplicate `line_width`/`DocState_gridSize` rows above are not curation
errors: they are genuine repeat probes run to demonstrate the concurrency
fix (fix round 1, Finding B) and to re-confirm the harness after fixing
Findings A-D — this file is an append-only log of every probe actually run,
not a deduplicated summary, matching `tools/probe_field.py`'s own append
behaviour.
| `DocState_gridSize` | `40` | 1 | Bandit.mohoproj | 25 | none | inert |
