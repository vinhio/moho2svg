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
