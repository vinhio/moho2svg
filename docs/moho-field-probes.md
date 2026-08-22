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

**This development environment's Moho install occasionally crashes on its
own, unrelated to any specific field.** `~/Library/Logs/DiagnosticReports/`
holds several Moho crash logs from sessions that touched none of this
project's probing code. This matters here because M1.5 batch 3's own report
originally described three `ParticleLayer` field/value combinations
(`num_particles=300`, `particle_lifetime=4`, `evenly_spaced=true`, all on
`Gathered-01Intro2.mohoproj`) as "reproducibly" crashing Moho with `SIGSEGV`
-- a later independent retry of the exact same three combinations rendered
cleanly every time, so that language overstated what a SINGLE observed crash
during one probing run actually established. Treat any one-off crash
observed while probing as a possible instance of this environment's own
background flakiness unless it is independently reproduced on retry -- see
the affected fields' own entries in `schema/layer.schema.json`'s
`ParticleLayer` for the corrected wording.

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
| `action_refs` | `[{"probe": true}]` | 1 | Bandit.mohoproj | 25 | none | inert |
| `antialiasing` | `false` | 22 | Bandit.mohoproj | 25 | none | inert |
| `back_color` | `{"r": 10, "g": 20, "b": 30, "a": 255}` | 1 | Bandit.mohoproj | 25 | none | inert |
| `camera_pan_tilt` | `{"type": "Vec2", "ref": false, "mute": false, "when": [0], "val": [{"x": 0.3, "y": 0.3}], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 1 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `camera_roll` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.6], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 1 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `depth_of_field` | `true` | 1 | Bandit.mohoproj | 25 | none | inert |
| `display_quality` | `0` | 1 | Bandit.mohoproj | 25 | none | inert |
| `extra_swf_frame` | `true` | 1 | Bandit.mohoproj | 25 | none | inert |
| `focus_blur` | `0.9` | 1 | Bandit.mohoproj | 25 | `depth_of_field=true` x1 | **AFFECTS RENDER** |
| `focus_distance` | `10.0` | 1 | Bandit.mohoproj | 25 | `depth_of_field=true` x1 | **AFFECTS RENDER** |
| `focus_range` | `5.0` | 1 | Bandit.mohoproj | 25 | `depth_of_field=true` x1 | inert |
| `global_render_style_fill_style` | `1` | 1 | Bandit.mohoproj | 25 | none | inert |
| `global_render_style_layer_style` | `1` | 1 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `global_render_style_minimize_randomness` | `false` | 1 | Bandit.mohoproj | 25 | none | inert |
| `layercomps` | `[{"name": "probe", "uuid": "11111111-1111-1111-1111-111111111111", "layer_ids": []}]` | 1 | Bandit.mohoproj | 25 | none | inert |
| `stereo_mode` | `1` | 1 | Bandit.mohoproj | 25 | none | inert |
| `stereo_separation` | `0.5` | 1 | Bandit.mohoproj | 25 | `stereo_mode=1` x1 | **AFFECTS RENDER** |
| `dof_immune` | `true` | 25 | Bandit.mohoproj | 25 | none | inert |
| `face_camera` | `true` | 25 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `face_camera_mode` | `0` | 25 | Bandit.mohoproj | 25 | none | inert |
| `flexi_bone_elbow` | `true` | 25 | Bandit.mohoproj | 25 | none | inert |
| `follow_bending` | `true` | 25 | Bandit.mohoproj | 25 | none | inert |
| `follow_curve` | `0` | 25 | Bandit.mohoproj | 25 | none | inert |
| `follow_layer_uuid` | `"99999999-9999-9999-9999-999999999999"` | 25 | Bandit.mohoproj | 25 | none | inert |
| `following` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.4], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | Bandit.mohoproj | 25 | none | inert |
| `layer_ref_fileref` | `{"relativeTo": "Absolute", "path": "/nonexistent/probe.png"}` | 25 | Bandit.mohoproj | 25 | none | inert |
| `layer_ref_mod_date` | `123456` | 25 | Bandit.mohoproj | 25 | none | inert |
| `layer_ref_path` | `"probe.png"` | 25 | Bandit.mohoproj | 25 | none | inert |
| `layer_ref_same_doc` | `true` | 25 | Bandit.mohoproj | 25 | none | inert |
| `layer_ref_uuid` | `"88888888-8888-8888-8888-888888888888"` | 25 | Bandit.mohoproj | 25 | none | inert |
| `physics_nudge` | `{"type": "Vec2", "ref": false, "mute": false, "when": [0], "val": [{"x": 0.3, "y": 0.3}], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | Bandit.mohoproj | 25 | none | inert |
| `quality_flags` | `0` | 25 | Bandit.mohoproj | 25 | none | inert |
| `random_num` | `999999` | 25 | Bandit.mohoproj | 25 | none | inert |
| `render_only` | `true` | 25 | Bandit.mohoproj | 25 | none | inert |
| `rotation_x` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [30.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `rotation_y` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [30.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `scale_compensation` | `false` | 25 | Bandit.mohoproj | 25 | none | inert |
| `scale_normalization` | `3.0` | 25 | Bandit.mohoproj | 25 | none | inert |
| `antialiasing` | `false` | 22 | Bandit.mohoproj | 25 | none | inert |
| `noise_grain` | `5` | 1 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `pixelation` | `20` | 1 | .probe_fixture_pixelation_projectonly.mohoproj | 25 | none | inert |
| `pixelation` | `{"type":"Val","ref":false,"mute":false,"when":[0],"val":[20.0],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 25 | .probe_fixture_pixelation_layeronly.mohoproj | 25 | none | **AFFECTS RENDER** |
| `shear` | `{"type":"Vec3","ref":false,"mute":false,"when":[0],"val":[{"x":0.4,"y":0.0,"z":0.0}],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 25 | .probe_fixture_shear_transformsonly.mohoproj | 25 | none | **AFFECTS RENDER** |
| `shear` | `{"type":"Val","ref":false,"mute":false,"when":[0],"val":[0.6],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 25 | .probe_fixture_shear_pshadowonly.mohoproj | 25 | none | inert |
| `color_palette` | `"Nonexistent Palette.png"` | 1 | Bandit.mohoproj | 25 | none | inert |
| `global_render_style_line_style` | `1` | 1 | Bandit.mohoproj | 25 | none | inert |
| `face_camera_mode` | `0` | 25 | Bandit.mohoproj | 25 | `face_camera=true` x25 | **AFFECTS RENDER** |
| `toon_effect` | `true` | 27 | Boar.mohoproj | 0 | none | inert |
| `toon_effect` | `true` | 28 | 04 snow man construction.moho | 0 | none | **AFFECTS RENDER** |
| `avi_alpha` | `true` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `movie_looping` | `true` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `interpreted_fps` | `12.0` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `persist_first_frame` | `true` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `persist_last_frame` | `true` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `premultiplied_movie` | `true` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `reverse_movie` | `true` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `image_cropped` | `false` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `quality_level` | `0` | 28 | 04 snow man construction.moho | 0 | none | **AFFECTS RENDER** |
| `sampling_mode` | `0` | 28 | 04 snow man construction.moho | 0 | none | **AFFECTS RENDER** |
| `psd_layer` | `999` | 24 | 04 snow man construction.moho | 0 | none | **AFFECTS RENDER** |
| `psd_layer_bounds` | `{"top": 0, "left": 0, "right": 200, "bottom": 200}` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `toon_black_threshold` | `200` | 28 | 04 snow man construction.moho | 0 | `toon_effect=true` x28 | **AFFECTS RENDER** |
| `toon_gray_threshold` | `200` | 28 | 04 snow man construction.moho | 0 | `toon_effect=true` x28 | **AFFECTS RENDER** |
| `toon_lightness` | `80` | 28 | 04 snow man construction.moho | 0 | `toon_effect=true` x28 | **AFFECTS RENDER** |
| `toon_max_edge_threshold` | `50` | 28 | 04 snow man construction.moho | 0 | `toon_effect=true` x28 | **AFFECTS RENDER** |
| `toon_min_edge_threshold` | `10` | 28 | 04 snow man construction.moho | 0 | `toon_effect=true` x28 | **AFFECTS RENDER** |
| `toon_quantize` | `2` | 28 | 04 snow man construction.moho | 0 | `toon_effect=true` x28 | **AFFECTS RENDER** |
| `toon_saturation` | `200` | 28 | 04 snow man construction.moho | 0 | `toon_effect=true` x28 | **AFFECTS RENDER** |

## Findings worth flagging to M1.2's own reader (fix round 1)

The `toon_effect` row against `Boar.mohoproj` (above, frame 0, `inert`) is
**superseded** — do not read it as a genuine negative. `Boar.mohoproj`
references PSD source assets (`Images/Boar_fox_01.psd`) that are not present
in this checkout, so every `ImageLayer` in it renders as Moho's own
broken-image placeholder glyph regardless of what field is varied; both the
base and variant twins of that probe rendered the identical placeholder, not
identical toon-shaded artwork. The very next row, same key and value against
`04 snow man construction.moho` (a document whose image assets ARE present
and confirmed to render real artwork), is the real measurement:
`AFFECTS RENDER`. This file stays append-only by design (see the header
above) — this note is added rather than editing or removing the misleading
row.
| `brush_angle_drift` | `1.0` | 124 | Bandit.mohoproj | 25 | none | inert |
| `brush_hue_drift` | `0.5` | 124 | Bandit.mohoproj | 25 | none | inert |
| `brush_merged_alpha` | `true` | 124 | Bandit.mohoproj | 25 | none | inert |
| `brush_rand_order` | `true` | 124 | Bandit.mohoproj | 25 | none | inert |
| `brush_random_interval` | `2` | 124 | Bandit.mohoproj | 25 | none | inert |
| `brush_randomize` | `true` | 124 | Bandit.mohoproj | 25 | none | inert |
| `brush_sat_drift` | `0.5` | 124 | Bandit.mohoproj | 25 | none | inert |
| `brush_size_amp` | `0.9` | 124 | Bandit.mohoproj | 25 | none | inert |
| `brush_size_scale` | `0.9` | 124 | Bandit.mohoproj | 25 | none | inert |
| `brush_val_drift` | `0.5` | 124 | Bandit.mohoproj | 25 | none | inert |
| `brush_size_amp` | `0.95` | 124 | Bandit.mohoproj | 25 | `brush_randomize=true` x124 | inert |
| `combo_blend_anim` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.7], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 112 | Bandit.mohoproj | 25 | none | inert |
| `fill_allowed` | `false` | 112 | Bandit.mohoproj | 25 | none | inert |
| `effect_offset` | `{"type": "Vec2", "ref": false, "mute": false, "when": [0], "val": [{"x": 0.3, "y": 0.3}], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 190 | SketchBone.animeproj | 0 | none | **AFFECTS RENDER** |
| `fill_style_id` | `4` | 76 | SketchBone.animeproj | 0 | none | **AFFECTS RENDER** |
| `through_alpha` | `true` | 83 | SketchBone.animeproj | 0 | none | inert |
| `anim_shape_order` | `true` | 21 | Bandit.mohoproj | 25 | none | inert |
| `curve_interpretation` | `0` | 21 | Bandit.mohoproj | 25 | none | inert |
| `next_shape_id` | `999` | 21 | Bandit.mohoproj | 25 | none | inert |
| `color_drift` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.5], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 396 | Bandit.mohoproj | 25 | none | inert |
| `color_strength` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.3], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 396 | Bandit.mohoproj | 25 | none | inert |
| `colored` | `true` | 396 | Bandit.mohoproj | 25 | none | inert |
| `opacity` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.3], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 396 | Bandit.mohoproj | 25 | none | inert |
| `colored` | `false` | 4785 | Snow-girl-cut10.mohoproj | 0 | none | **AFFECTS RENDER** |
| `profile_curve_id` | `-1` | 940 | Gathered-01Intro2.mohoproj | 0 | none | **AFFECTS RENDER** |
| `profile_layer_uuid` | `""` | 940 | Gathered-01Intro2.mohoproj | 0 | none | **AFFECTS RENDER** |
| `profile_repeat` | `4` | 940 | Gathered-01Intro2.mohoproj | 0 | none | **AFFECTS RENDER** |
| `profile_offset` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.5], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 114 | Bandit.mohoproj | 25 | none | inert |
| `layer_color` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0}], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 25 | Bandit.mohoproj | 25 | none | inert |
| `layer_outline` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "width": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.004115], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0}], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 25 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `layer_shading` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "angle": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [5.497787], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "offset": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.033333], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "blur": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.066667], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "contraction": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.501961}], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "noise_amp": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "noise_scale": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [64.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "threshold": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 25 | Bandit.mohoproj | 25 | none | inert |
| `layer_shadow` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "angle": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [5.497787], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "offset": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.033333], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "blur": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.016667], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "expansion": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.501961}], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "noise_amp": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "noise_scale": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [64.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "threshold": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "clip_to_group": false}` | 25 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `motion_blur` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "sub_frames": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "frames": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [50.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "skip": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [1.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "alpha_start": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.3], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "alpha_end": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.1], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "radius": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.008333], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "frame_percentage": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [1.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "extended_frames": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 25 | Bandit.mohoproj | 25 | none | inert |
| `perspective_shadow` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "blur": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.012346], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "scale": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [1.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "shear": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.501961}], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "threshold": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 25 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `layer_color` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0}], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 25 | Bandit.mohoproj | 25 | none | inert |
| `layer_outline` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "width": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.004115], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.0, "g": 0.0, "b": 0.0, "a": 1.0}], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 25 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `layer_shading` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "angle": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [5.497787], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "offset": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.033333], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "blur": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.066667], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "contraction": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.501961}], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "noise_amp": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "noise_scale": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [64.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "threshold": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 25 | Bandit.mohoproj | 25 | none | inert |
| `layer_shadow` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "angle": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [5.497787], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "offset": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.033333], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "blur": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.016667], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "expansion": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.501961}], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "noise_amp": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "noise_scale": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [64.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "threshold": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "clip_to_group": false}` | 25 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `motion_blur` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "sub_frames": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "frames": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [50.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "skip": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [1.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "alpha_start": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.3], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "alpha_end": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.1], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "radius": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.008333], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "frame_percentage": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [1.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "extended_frames": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 25 | Bandit.mohoproj | 25 | none | inert |
| `perspective_shadow` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "blur": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.012346], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "scale": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [1.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "shear": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.0, "g": 0.0, "b": 0.0, "a": 0.501961}], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "threshold": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 25 | Bandit.mohoproj | 25 | none | **AFFECTS RENDER** |
| `alpha_start` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.9], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 159 | Snow-girl-cut51.mohoproj | 175 | none | inert |
| `motion_blur` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}, "sub_frames": {"type": "Bool", "ref": false, "mute": false, "when": [0, 169], "val": [true, true], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}, {"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "frames": {"type": "Val", "ref": false, "mute": false, "when": [0, 169], "val": [20.0, 20.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}, {"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "skip": {"type": "Val", "ref": false, "mute": false, "when": [0, 169], "val": [1.0, 1.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}, {"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "alpha_start": {"type": "Val", "ref": false, "mute": false, "when": [0, 169], "val": [0.3, 0.3], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}, {"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "alpha_end": {"type": "Val", "ref": false, "mute": false, "when": [0, 169], "val": [0.1, 0.1], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}, {"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "radius": {"type": "Val", "ref": false, "mute": false, "when": [0, 169], "val": [0.008333, 0.008333], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}, {"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "frame_percentage": {"type": "Val", "ref": false, "mute": false, "when": [0, 169], "val": [1.0, 1.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}, {"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "extended_frames": {"type": "Val", "ref": false, "mute": false, "when": [0, 169], "val": [0.0, 0.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}, {"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 159 | Snow-girl-cut51.mohoproj | 175 | none | **AFFECTS RENDER** |
| `alpha_end` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.9], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 159 | Snow-girl-cut51.mohoproj | 175 | none | inert |
| `ambient_occlusion` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [5.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | Bandit.mohoproj | 25 | none | inert |
| `threshold` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [50.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_threshold_layereffects.mohoproj | 25 | none | inert |
| `threshold` | `{"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_threshold_layershadow.mohoproj | 25 | none | **AFFECTS RENDER** |
| `blur` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.5], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_blur_layershadow.mohoproj | 25 | none | **AFFECTS RENDER** |
| `blur` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.5], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_blur_layereffects.mohoproj | 25 | none | **AFFECTS RENDER** |
| `blur` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.5], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_blur_layershading.mohoproj | 25 | none | inert |
| `blur` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.5], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_blur_perspectiveshadow.mohoproj | 25 | none | **AFFECTS RENDER** |
| `threshold` | `{"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_threshold_layershading.mohoproj | 25 | none | inert |
| `threshold` | `{"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_threshold_perspectiveshadow.mohoproj | 25 | none | **AFFECTS RENDER** |
| `noise_amp` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.5], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_noise_amp_layershadow.mohoproj | 25 | none | inert |
| `noise_amp` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.5], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_noise_amp_layershading.mohoproj | 25 | none | inert |
| `noise_scale` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [8.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_noise_scale_layershadow.mohoproj | 25 | none | inert |
| `noise_scale` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [8.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_fixture_noise_scale_layershading.mohoproj | 25 | none | inert |
| `exclude_lines_from_mask` | `true` | 38 | Spacewoman.mohoproj | 27 | none | **AFFECTS RENDER** |
| `anim_parent` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [-1.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 1 | .probe_fixture_anim_parent.mohoproj | 90 | none | **AFFECTS RENDER** |
| `ik_lock` | `{"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [true], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 91 | DarkMan.mohoproj | 0 | none | inert |
| `ik_global_angle` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [2.845608], "interp": [{"im": 3, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}` | 91 | DarkMan.mohoproj | 0 | none | inert |
| `ik_parent_target` | `{"type": "Vec2", "ref": false, "mute": false, "when": [0], "val": [{"x": -0.022371, "y": 0.66081}], "interp": [{"im": 3, "v1": -1.0, "v2": -1.0, "in": 1, "h": 0, "s": false, "t": 0}]}` | 91 | DarkMan.mohoproj | 0 | none | inert |
| `bone_enable_arc_solver` | `true` | 91 | DarkMan.mohoproj | 0 | none | inert |
| `grandpa_bone` | `true` | 37 | DarkMan.mohoproj | 0 | none | inert |
| `constraints` | `true` | 64 | Boar.mohoproj | 0 | none | inert |
| `ignored_by_ik` | `true` | 44 | Cocon.mohoproj | 0 | none | inert |
| `min_constraint` | `-1.570796` | 64 | Boar.mohoproj | 0 | none | inert |
| `max_constraint` | `1.570796` | 64 | Boar.mohoproj | 0 | none | inert |
| `angle_weight` | `1.85` | 64 | Boar.mohoproj | 0 | none | inert |
| `active_bone` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [1.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 1 | Night_Boy.mohoproj | 0 | none | **AFFECTS RENDER** |
| `enable_physics` | `{"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 3 | Bandit.mohoproj | 90 | none | **AFFECTS RENDER** |
| `enable_physics` | `{"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 29 | WhatIsBone.animeproj | 60 | none | **AFFECTS RENDER** |
| `use_baked_physics` | `true` | 29 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | **AFFECTS RENDER** |
| `friction` | `1.0` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | inert |
| `restitution` | `1.0` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | inert |
| `respawn` | `5` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | inert |
| `sleeping` | `true` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | **AFFECTS RENDER** |
| `pivot` | `true` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | **AFFECTS RENDER** |
| `enable_motor` | `true` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | inert |
| `motor_speed` | `{"type":"Val","ref":false,"mute":false,"when":[0],"val":[20.0],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29, `enable_motor=true` x140 | inert |
| `motor_torque` | `0.0001` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29, `enable_motor=true` x140, `motor_speed={"type":"Val","ref":false,"mute":false,"when":[0],"val":[20.0],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x140 | inert |
| `force_field` | `true` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | **AFFECTS RENDER** |
| `force_field_vector` | `{"type":"Vec2","ref":false,"mute":false,"when":[0],"val":[{"x":1000.0,"y":0.0}],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29, `force_field=true` x140 | inert |
| `enable_motor` | `true` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29, `pivot=true` x140 | **AFFECTS RENDER** |
| `motor_speed` | `{"type":"Val","ref":false,"mute":false,"when":[0],"val":[20.0],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29, `enable_motor=true` x140, `pivot=true` x140 | **AFFECTS RENDER** |
| `motor_torque` | `0.0001` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29, `enable_motor=true` x140, `motor_speed={"type":"Val","ref":false,"mute":false,"when":[0],"val":[20.0],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x140, `pivot=true` x140 | **AFFECTS RENDER** |
| `force_field_vector` | `{"type":"Vec2","ref":false,"mute":false,"when":[0],"val":[{"x":0.0,"y":-1000.0}],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29, `force_field=true` x140 | inert |
| `physics_lock_tip` | `true` | 216 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | **AFFECTS RENDER** |
| `physics_return_to_zero` | `true` | 216 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | inert |
| `physics_radius` | `0.0` | 216 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | **AFFECTS RENDER** |
| `physics_motor_speed` | `{"type":"Val","ref":false,"mute":false,"when":[0],"val":[200.0],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 216 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | **AFFECTS RENDER** |
| `physics_torque` | `0.0001` | 216 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | inert |
| `physics_torque` | `0.0001` | 216 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29, `physics_motor_speed={"type":"Val","ref":false,"mute":false,"when":[0],"val":[200.0],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x216 | **AFFECTS RENDER** |
| `physics_return_to_zero` | `true` | 216 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29, `physics_motor_speed={"type":"Val","ref":false,"mute":false,"when":[0],"val":[200.0],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x216 | **AFFECTS RENDER** |
| `pos_dynamics` | `true` | 44 | Cocon.mohoproj | 60 | `bone_dynamics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x44 | **AFFECTS RENDER** |
| `scale_dynamics` | `true` | 44 | Cocon.mohoproj | 60 | `bone_dynamics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x44 | **AFFECTS RENDER** |
| `pos_spring_force` | `20.0` | 44 | Cocon.mohoproj | 60 | `bone_dynamics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x44, `pos_dynamics=true` x44 | **AFFECTS RENDER** |
| `pos_damping_force` | `20.0` | 44 | Cocon.mohoproj | 60 | `bone_dynamics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x44, `pos_dynamics=true` x44 | **AFFECTS RENDER** |
| `pos_torque_force` | `20.0` | 44 | Cocon.mohoproj | 60 | `bone_dynamics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x44, `pos_dynamics=true` x44 | **AFFECTS RENDER** |
| `pos_weight` | `5.0` | 44 | Cocon.mohoproj | 60 | `bone_dynamics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x44, `pos_dynamics=true` x44 | **AFFECTS RENDER** |
| `scale_spring_force` | `20.0` | 44 | Cocon.mohoproj | 60 | `bone_dynamics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x44, `scale_dynamics=true` x44 | **AFFECTS RENDER** |
| `scale_damping_force` | `20.0` | 44 | Cocon.mohoproj | 60 | `bone_dynamics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x44, `scale_dynamics=true` x44 | **AFFECTS RENDER** |
| `scale_torque_force` | `20.0` | 44 | Cocon.mohoproj | 60 | `bone_dynamics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x44, `scale_dynamics=true` x44 | **AFFECTS RENDER** |
| `scale_weight` | `5.0` | 44 | Cocon.mohoproj | 60 | `bone_dynamics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x44, `scale_dynamics=true` x44 | **AFFECTS RENDER** |
| `num_particles` | `50` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `accel_angle` | `0.0` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `accel_rate` | `0.0` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `damping` | `2.0` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `free_floating` | `false` | 1 | Gathered-01Intro2.mohoproj | 210 | none | inert |
| `orient_particles` | `false` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `evenly_spaced` | `true` | 1 | 01 opening.moho | 60 | none | **AFFECTS RENDER** |
| `preview_particles` | `50` | 1 | Gathered-01Intro2.mohoproj | 210 | none | inert |
| `random_start_time` | `true` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `seed` | `916190` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `start_dir` | `4.537856` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `start_full` | `false` | 1 | Gathered-01Intro2.mohoproj | 210 | none | inert |
| `particle_lifetime` | `24` | 1 | 01 opening.moho | 60 | none | **AFFECTS RENDER** |
| `source_shape` | `{"x":5.0,"y":0.1,"z":2.0}` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `start_spread` | `0.174533` | 1 | 01 opening.moho | 60 | none | **AFFECTS RENDER** |
| `use_base_as_source` | `true` | 1 | Gathered-01Intro2.mohoproj | 210 | none | inert |
| `velocity_spread` | `0.0` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `particle_activation` | `{"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 1 | Gathered-01Intro2.mohoproj | 210 | none | **AFFECTS RENDER** |
| `velocity` | `10.0` | 1 | .probe_isolate_particlevel.mohoproj | 210 | none | **AFFECTS RENDER** |
| `density` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.2], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 19 | .probe_isolate_crayondensity.animeproj | 60 | none | inert |
| `density` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.01], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 19 | .probe_isolate_crayondensity.animeproj | 60 | none | inert |
| `velocity` | `{"x":500.0,"y":-500.0}` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | **AFFECTS RENDER** |
| `density` | `1000.0` | 140 | WhatIsBone.animeproj | 60 | `enable_physics={"type":"Bool","ref":false,"mute":false,"when":[0],"val":[true],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` x29 | **AFFECTS RENDER** |
| `text` | `"ZZZ_CHANGED"` | 2 | Rabbit.animeproj | 0 | none | inert |
| `font` | `"Arial Black"` | 2 | Rabbit.animeproj | 0 | none | inert |
| `textsize` | `170` | 2 | Rabbit.animeproj | 0 | none | inert |
| `justification` | `0` | 2 | Rabbit.animeproj | 0 | none | inert |
| `leading` | `0` | 2 | Rabbit.animeproj | 0 | none | inert |
| `kerning` | `0` | 2 | Rabbit.animeproj | 0 | none | inert |
| `fill` | `false` | 2 | Rabbit.animeproj | 0 | none | inert |
| `stroke` | `true` | 2 | Rabbit.animeproj | 0 | none | inert |
| `fillcolor` | `{"r":0,"g":0,"b":0,"a":255}` | 2 | Rabbit.animeproj | 0 | none | inert |
| `linecolor` | `{"r":255,"g":255,"b":255,"a":255}` | 2 | Rabbit.animeproj | 0 | none | inert |
| `linewidth` | `0.004111` | 2 | Rabbit.animeproj | 0 | none | inert |
| `textinheritedstyle1` | `"SomeStyle"` | 2 | Rabbit.animeproj | 0 | none | inert |
| `textinheritedstyle2` | `"SomeStyle2"` | 2 | Rabbit.animeproj | 0 | none | inert |
| `text` | `"SECOND_CHECK"` | 4 | FoxAndGhost.animeproj | 0 | none | inert |
| `stroke` | `false` | 4 | FoxAndGhost.animeproj | 0 | none | inert |
| `fillcolor` | `{"r":0,"g":0,"b":0,"a":255}` | 4 | FoxAndGhost.animeproj | 0 | none | inert |
| `balloonstyle` | `"CK_Clean_Balloon"` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonfill` | `false` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonfillcolor` | `{"r":0,"g":0,"b":0,"a":255}` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonlinecolor` | `{"r":255,"g":0,"b":0,"a":255}` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonlinewidth` | `0.02` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonfliph` | `true` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonflipv` | `true` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonposes` | `"1.0 0.5"` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonsize` | `185` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonsizeproportional` | `false` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonstroke` | `false` | 2 | Rabbit.animeproj | 0 | none | inert |
| `balloonsize` | `105` | 1 | Gathered-00intro.mohoproj | 0 | none | inert |
| `balloonstyle` | `"Standard_01_Top_Bottom"` | 1 | Gathered-00intro.mohoproj | 0 | none | inert |
| `balloonfillcolor` | `{"r":255,"g":0,"b":0,"a":255}` | 2 | BoneDynamics.animeproj | 0 | none | inert |
| `text` | `"CHANGED_NOTE"` | 1 | Snow-girl-cut51.mohoproj | 0 | none | inert |
| `text` | `"CHANGED_NOTE2"` | 4 | 01 opening.moho | 60 | none | inert |
| `clear_background` | `true` | 1 | .probe_crayon_clear_background_eh28eghq.mohoproj | 0 | none | inert |
| `rand_seed` | `999999` | 1 | .probe_crayon_rand_seed_kumqskj5.mohoproj | 0 | none | inert |
| `reduce_randomization` | `false` | 1 | .probe_crayon_reduce_randomization_lm888wjo.mohoproj | 0 | none | inert |
| `halo_only` | `true` | 9 | .probe_halo_halo_only_t655lp7q.mohoproj | 0 | none | **AFFECTS RENDER** |
| `halo_color` | `{"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}` | 9 | .probe_halo_halo_color_rcq2opup.mohoproj | 0 | none | **AFFECTS RENDER** |
| `shadow_only` | `true` | 2 | .probe_shaded_shadow_only_euju1agi.mohoproj | 0 | none | **AFFECTS RENDER** |
| `halo_radius` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.05], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 9 | .probe_halo_halo_radius_v2_cq17bnmu.mohoproj | 0 | none | **AFFECTS RENDER** |
| `noise` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [5.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_layereffects_noise_ld25pgk9.mohoproj | 25 | none | inert |
| `animated_noise` | `true` | 21 | .probe_meshlayer_animated_noise_drzk2i_g.mohoproj | 25 | none | inert |
| `extra_lines` | `5` | 21 | .probe_meshlayer_extra_lines_pqmp_jc6.mohoproj | 25 | none | inert |
| `extra_sketchy` | `true` | 21 | .probe_meshlayer_extra_sketchy_4lc4amnb.mohoproj | 25 | none | inert |
| `gap_filling` | `true` | 21 | .probe_meshlayer_gap_filling_rzcjtyj8.mohoproj | 25 | none | inert |
| `noise_interval` | `2` | 21 | .probe_meshlayer_noise_interval_louvjghf.mohoproj | 25 | none | inert |
| `noisy_lines` | `true` | 21 | .probe_meshlayer_noisy_lines_fv0opje7.mohoproj | 25 | none | inert |
| `noisy_shapes` | `true` | 21 | .probe_meshlayer_noisy_shapes_0p351fl0.mohoproj | 25 | none | inert |
| `frame_zero_deformer` | `false` | 21 | .probe_meshlayer_frame_zero_deformer_7x8g2yws.mohoproj | 25 | none | inert |
| `triangulated` | `true` | 21 | .probe_meshlayer_triangulated_6hqpfors.mohoproj | 25 | none | inert |
| `contraction` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.02], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_layershading_contraction_7uwyrmy3.mohoproj | 25 | none | inert |
| `clip_to_group` | `true` | 25 | .probe_layershadow_clip_to_group_uqzt3e_2.mohoproj | 25 | none | **AFFECTS RENDER** |
| `expansion` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.02], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_layershadow_expansion_41yluue0.mohoproj | 25 | none | **AFFECTS RENDER** |
| `extended_frames` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [2.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 159 | .probe_motionblur_extended_frames_rrttpy4f.mohoproj | 175 | none | **AFFECTS RENDER** |
| `frame_percentage` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.3], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 159 | .probe_motionblur_frame_percentage_lq7mdzrg.mohoproj | 175 | none | **AFFECTS RENDER** |
| `frames` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [5.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 159 | .probe_motionblur_frames_kly2hfyi.mohoproj | 175 | none | **AFFECTS RENDER** |
| `radius` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.05], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 159 | .probe_motionblur_radius_skw5x596.mohoproj | 175 | none | inert |
| `skip` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [3.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 159 | .probe_motionblur_skip_k4t_ykzj.mohoproj | 175 | none | inert |
| `sub_frames` | `{"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 159 | .probe_motionblur_sub_frames_h5l_reks.mohoproj | 175 | none | **AFFECTS RENDER** |
| `blur_radius` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.05], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 9 | .probe_halo_blur_radius_yayeqnnd.mohoproj | 0 | none | **AFFECTS RENDER** |
| `blur_radius` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.05], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 6 | .probe_softstyle_blur_radius_q18x5oy_.mohoproj | 0 | none | inert |
| `angle` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_layershading_angle_dya2gx6d.mohoproj | 25 | none | inert |
| `angle` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 25 | .probe_layershadow_angle_16zcsw0l.mohoproj | 25 | none | **AFFECTS RENDER** |
| `angle` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 2 | .probe_shaded_angle_s4yhkyxm.mohoproj | 0 | none | **AFFECTS RENDER** |
| `angle` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 1 | .probe_shadowstyle_angle_ivrddgym.animeproj | 0 | none | **AFFECTS RENDER** |
| `direction` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [3.141593], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 1 | .probe_wind_direction_l0e2hlto.mohoproj | 25 | none | inert |
| `direction` | `{"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}` | 1 | .probe_gravity_direction_4m79r8uc.mohoproj | 25 | none | inert |
| `extra_sketchy` | `false` | 106 | .probe_meshlayer_extra_sketchy_real_wshovpca.mohoproj | 0 | none | inert |
| `noisy_lines` | `false` | 106 | .probe_meshlayer_noisy_lines_real_1raooflz.mohoproj | 0 | none | inert |
| `noisy_shapes` | `false` | 106 | .probe_meshlayer_noisy_shapes_real_urq30uyz.mohoproj | 0 | none | **AFFECTS RENDER** |
| `animated_noise` | `false` | 106 | .probe_meshlayer_animated_noise_real_h5ywupfq.mohoproj | 0 | none | **AFFECTS RENDER** |
| `noise_interval` | `1` | 30 | .probe_meshlayer_noise_interval_real_3sxvud2i.animeproj | 0 | none | **AFFECTS RENDER** |
| `extra_lines` | `0` | 191 | .probe_meshlayer_extra_lines_real_i2ds39b1.animeproj | 0 | none | inert |
| `triangulated` | `false` | 5 | .probe_meshlayer_triangulated_real_f37nmtsj.mohoproj | 0 | none | inert |
| `path` | `"Images/Sky.png"` | 284 | .probe_path_imagefileref_136rdqw3.moho | 0 | none | **AFFECTS RENDER** |
| `relativeTo` | `"Project"` | 284 | .probe_relto_imagefileref_8se475_o.moho | 0 | none | inert |
| `audio_path` | `"Audio/Changed.wav"` | 1 | The Nutcracker Ballet.moho | 0 | none | inert |
| `audio_fileref` | `{"relativeTo": "Absolute", "path": "Audio/Changed.wav"}` | 1 | The Nutcracker Ballet.moho | 0 | none | inert |
| `audio_level` | `{"type":"Val","ref":false,"mute":false,"when":[0],"val":[5.0],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 1 | The Nutcracker Ballet.moho | 0 | none | inert |
| `audio_jump` | `{"type":"Val","ref":false,"mute":false,"when":[0],"val":[5.0],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 1 | The Nutcracker Ballet.moho | 0 | none | inert |
| `audio_text` | `"CHANGED_AUDIO_TEXT"` | 1 | The Nutcracker Ballet.moho | 0 | none | inert |
| `spatial_positioning` | `true` | 1 | The Nutcracker Ballet.moho | 0 | none | inert |
| `image_cropping_min` | `{"x":0.3,"y":0.3,"z":0.0}` | 4 | 04 snow man construction.moho | 0 | none | inert |
| `image_cropping_max` | `{"x":0.7,"y":0.7,"z":0.0}` | 4 | 04 snow man construction.moho | 0 | none | inert |
| `top` | `999` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `left` | `999` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `right` | `999` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `bottom` | `999` | 28 | 04 snow man construction.moho | 0 | none | inert |
| `psd_layers` | `"0|999|CHANGED_LAYER_LIST"` | 1 | 04 snow man construction.moho | 0 | none | **AFFECTS RENDER** |
| `fill_texture_fileref` | `{"relativeTo":"Absolute","path":"/Users/vinh/Working/Moho2SVG/moho/Snow_wars/Images/BG 1.png"}` | 21 | Bandit.mohoproj | 25 | none | inert |
| `fill_texture_path` | `"/Users/vinh/Working/Moho2SVG/moho/Snow_wars/Images/BG 1.png"` | 21 | Bandit.mohoproj | 25 | none | inert |
| `line_texture_fileref` | `{"relativeTo":"Absolute","path":"/Users/vinh/Working/Moho2SVG/moho/Snow_wars/Images/BG 1.png"}` | 21 | Bandit.mohoproj | 25 | none | inert |
| `line_texture_path` | `"/Users/vinh/Working/Moho2SVG/moho/Snow_wars/Images/BG 1.png"` | 21 | Bandit.mohoproj | 25 | none | inert |
| `fill_texture_fileref` | `{"relativeTo":"Absolute","path":"/Users/vinh/Working/Moho2SVG/moho/Snow_wars/Images/BG 1.png"}` | 21 | Bandit.mohoproj | 25 | `fill_texture_path="/Users/vinh/Working/Moho2SVG/moho/Snow_wars/Images/BG 1.png"` x21 | inert |
| `path` | `"/Users/vinh/Working/Moho2SVG/moho/Snow_wars/Images/BG 1.png"` | 113 | .probe_texture2path_1mmsyqm_.animeproj | 0 | none | inert |
| `path` | `"/Users/vinh/Working/Moho2SVG/moho/Snow_wars/Images/BG 1.png"` | 113 | .probe_texture2path_fm1_9mphfjuz.animeproj | 0 | `fill_mode=1` x4 | inert |
| `layer_color` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.137255, "g": 0.066667, "b": 0.266667, "a": 0.129412}], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 164 | Gathered-01Intro2.mohoproj | 0 | none | **AFFECTS RENDER** |
| `layer_shading` | `{"on": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "angle": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.665969], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "offset": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.013889], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "blur": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.006944], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "contraction": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "color": {"type": "Color", "ref": false, "mute": false, "when": [0], "val": [{"r": 0.878431, "g": 0.87451, "b": 0.494118, "a": 0.501961}], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "noise_amp": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [0.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "noise_scale": {"type": "Val", "ref": false, "mute": false, "when": [0], "val": [64.0], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}, "threshold": {"type": "Bool", "ref": false, "mute": false, "when": [0], "val": [false], "interp": [{"im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0}]}}` | 164 | Gathered-01Intro2.mohoproj | 0 | none | **AFFECTS RENDER** |
| `h` | `10` | 10074 | Bandit.mohoproj | 28 | none | **AFFECTS RENDER** |
| `in` | `6` | 10074 | Bandit.mohoproj | 28 | none | **AFFECTS RENDER** |
| `t` | `999` | 10074 | Bandit.mohoproj | 28 | none | inert |
| `ai` | `5.0` | 16 | Bandit.mohoproj | 28 | none | inert |
| `ao` | `-5.0` | 16 | Bandit.mohoproj | 28 | none | **AFFECTS RENDER** |
| `pi` | `0.99` | 16 | Bandit.mohoproj | 28 | none | inert |
| `po` | `0.99` | 16 | Bandit.mohoproj | 28 | none | inert |
| `num_points` | `999` | 114 | Bandit.mohoproj | 25 | none | inert |
| `binding_mode` | `2` | 1 | Bandit.mohoproj | 25 | none | inert |
| `skia_scaling` | `2.5` | 3 | Boar.mohoproj | 0 | none | inert |
| `target_layer_id` | `999` | 2 | SketchBone.animeproj | 0 | none | inert |
| `curve_points` | `999` | 403 | Bandit.mohoproj | 25 | none | inert |
| `groups` | `[{"name":"probe","points":[0,1]}]` | 21 | Bandit.mohoproj | 25 | none | inert |
| `rotate_to_follow` | `true` | 25 | Bandit.mohoproj | 25 | none | inert |
| `animated_layer_effects` | `true` | 25 | Bandit.mohoproj | 25 | none | inert |
| `animated_layer_order` | `false` | 2 | SketchBone.animeproj | 0 | none | inert |
| `layer_ordering` | `{"type":"String","ref":false,"mute":false,"when":[0],"val":["999|1|2"],"interp":[{"im":1,"v1":-1.0,"v2":-1.0,"in":1,"h":0,"s":false,"t":0}]}` | 4 | Bandit.mohoproj | 25 | none | inert |
| `script_data` | `{"what":999,"NewLayerScript":true}` | 2 | WhatIsBone.animeproj | 0 | none | inert |
| `turbulence_amplitude` | `{"type":"Val","ref":false,"mute":false,"when":[0],"val":[5.0],"interp":[{"im":1,"v1":-1.0,"v2":-1.0,"in":1,"h":0,"s":false,"t":0}]}` | 1 | Bandit.mohoproj | 25 | none | inert |
| `turbulence_frequency` | `{"type":"Val","ref":false,"mute":false,"when":[0],"val":[5.0],"interp":[{"im":1,"v1":-1.0,"v2":-1.0,"in":1,"h":0,"s":false,"t":0}]}` | 1 | Bandit.mohoproj | 25 | none | inert |
| `frame_by_frame` | `true` | 2 | Boar.mohoproj | 0 | none | inert |
| `switch_data` | `"PROBE_SWITCH_DATA"` | 2 | Boar.mohoproj | 0 | none | inert |
| `switch_interpolation` | `true` | 2 | Boar.mohoproj | 0 | none | inert |
| `masking_points` | `[{"seed_point":{"x":0.0,"y":0.0},"tolerance":50,"reverse_mask":true}]` | 1 | Boar.mohoproj | 0 | none | inert |
| `reverse_mask` | `true` | 2 | Boar.mohoproj | 0 | none | inert |
| `seed_point` | `{"x":0.5,"y":0.5}` | 2 | Boar.mohoproj | 0 | none | inert |
| `tolerance` | `5` | 2 | Boar.mohoproj | 0 | none | inert |
| `soundtrack` | `"Audio/probe.wav"` | 1 | Bandit.mohoproj | 25 | none | inert |
| `mute` | `true` | 7898 | Bandit.mohoproj | 25 | none | inert |
| `ref` | `true` | 7898 | Bandit.mohoproj | 25 | none | inert |
| `groups` | `[{"name":"probe_group","points":[0,1,2]}]` | 67 | 01 opening.moho | 0 | none | inert |
| `switch_data` | `"PROBE_CHANGED"` | 6 | Scene 2.moho | 0 | none | inert |
| `split` | `[{"type":"Val","ref":false,"mute":false,"when":[0],"val":[5.0],"interp":[{"im":1,"v1":-1.0,"v2":-1.0,"in":1,"h":0,"s":false,"t":0}]},{"type":"Val","ref":false,"mute":false,"when":[0],"val":[5.0],"interp":[{"im":1,"v1":-1.0,"v2":-1.0,"in":1,"h":0,"s":false,"t":0}]}]` | 1 | Bandit.mohoproj | 30 | none | **AFFECTS RENDER** |
| `fill_style2_id` | `9` | 4 | IndependentAngle.animeproj | 0 | none | **AFFECTS RENDER** |
| `fill_mode` | `1` | 4 | IndependentAngle.animeproj | 0 | none | inert |
| `SS_Texture2FileRef` | `{"relativeTo":"Absolute","path":"Images/Sky.png"}` | 4 | IndependentAngle.animeproj | 0 | none | inert |
| `line_style_id` | `4` | 9 | 01 opening.moho | 0 | none | **AFFECTS RENDER** |
| `layer_ordering` | `{"type":"String","ref":false,"mute":false,"when":[0,12],"val":["","F8A20474-C414-4B10-8CB5-AFB33DD17A27|0F191C93-4EAC-4C91-894B-95339605665E|"],"interp":[{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0},{"im":1,"v1":0.1,"v2":0.5,"in":1,"h":0,"s":false,"t":0}]}` | 37 | DarkMan.mohoproj | 15 | none | inert |
