#!/usr/bin/env python3
"""Ground-truth data extractor for the moho-rig-report skill.

Walks a .mohoproj/.animeproj document with moho2svg.py's own document model
(Channel, Skeleton, Bone, Layer) and emits one JSON object on stdout:

  - project: canvas size, frame range, fps (read from the raw JSON's
    project_data, since the Document model itself doesn't wrap that block)
  - counts: total layer nodes, vector (mesh-carrying) layers, rigs
    (BoneLayers whose skeleton actually has bones), total bone count
  - tree_html_panel_order / tree_html_draw_order: TWO <ul class="tree">...
    </ul> fragments, one <li> per layer, nested to match the real
    parent/child structure, each node tagged rig/mesh/switch/image/other
    and flagged data-wind="1" when Layer.physics_dynamic is true for that
    layer. `draw_order` is the raw file order (`layers`, recursively) -
    this is Moho's real paint order, back to front. `panel_order` reverses
    the child list at every level independently - this is what Moho's own
    Layer Pool panel actually shows (confirmed in
    docs/moho-project-file-format.md: "the panel's top row is the array's
    *last* element, and vice versa" - a real per-container UI reversal, NOT
    evidence the file order is backwards for rendering; reversing the whole
    array for paint order was tested directly and produces visibly wrong
    masking). A report MUST show both, clearly labeled, never just one -
    see build_tree_html's own docstring for the full evidence trail.
  - rigs_html: one <details class="rig">...</details> block per
    skeleton-bearing layer, each containing a <table> of its bones (parent,
    rest length, angle/pos/scale keyframe counts, and a notes column for
    IK/auto-stretch/flip/angle-spring/wind)
  - shapes_html: one <details class="rig">...</details> block per vector
    (mesh-carrying) layer, listing its shapes in real draw order with each
    shape's boolean combination mode (combo_mode), fill/outline presence and
    a style note (brush / gradient / second effect). Empty string when no
    vector layer carries shapes - the caller then drops the whole shapes
    section from the assembled page (see SKILL.md step 4).
  - flags: every "special configuration" this pass can detect, pre-grouped
    so the caller does not need to re-derive them from tree_html/rigs_html:
    smart_bone_dials, ik_bones, angle_spring_bones, flip_bones, wind_rigs,
    gravity_rigs, cycle_channels, switch_layers, masking_layers,
    patch_layers, image_layers, smart_warp_layers,
    unrigged_bone_containers (a BoneLayer with skeleton == None, i.e. used
    purely as an organizational group), animated_transform_groups (any
    layer with no skeleton whose OWN Transform - translate/scale/rotate -
    is keyframed, since that is how those groups actually move)

This script only reads the document and prints JSON - it does not touch
the network, does not write any file, and does not import Pillow/
psd-tools/pyclipper (none of that is needed just to read bone/channel
data). Run it as:

    python3 analyze_rig.py /path/to/Project.mohoproj > /tmp/rig.json

See SKILL.md in this same directory for how the moho-rig-report skill
turns this JSON into the published artifact.
"""
import html
import json
import os
import sys


def _find_repo_root(start: str) -> str:
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, "moho2svg.py")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit("could not locate moho2svg.py above " + start)
        d = parent


sys.path.insert(0, _find_repo_root(os.path.dirname(__file__)))
from moho2svg import load_document, Channel, _channel_ever_true  # noqa: E402


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def chan_len(raw) -> int:
    return len(Channel.of(raw).when)


def chan_frames(raw) -> list:
    ch = Channel.of(raw)
    return list(ch.when) if len(ch.when) > 1 else []


def chan_cell_html(raw) -> str:
    ch = Channel.of(raw)
    n = len(ch.when)
    if n <= 1:
        return '<span class="static">tĩnh</span>'
    frames = ",".join(str(int(w)) for w in ch.when)
    return f'{n} <span class="frames">@{frames}</span>'


def layer_kind_badge(layer) -> str:
    kind = layer.kind.name
    return {
        "BONE": "rig",
        "MESH": "mesh",
        "SWITCH": "switch",
        "IMAGE": "image",
        "PATCH": "patch",
        "GROUP": "group",
    }.get(kind, kind.lower())


def build_tree_html(doc, panel_order: bool) -> str:
    """Render the layer tree as an HTML <ul>.

    `panel_order=False` walks `layers` (and each container's own `children`)
    in raw file order - this is Moho's actual paint order, back to front
    (Document.walk's own docstring; docs/moho-export-pipeline.md's DRAW
    ORDER section).

    `panel_order=True` reverses the child list at EVERY level of the
    recursion independently (not just the top level, and not a flatten-then-
    reverse of the whole walk) - this is what Moho's own Layer Pool panel
    shows: "the panel's top row is the array's *last* element, and vice
    versa", confirmed per-container in
    docs/moho-project-file-format.md ("The Moho app's own Layer Pool panel
    displays a container's children in the *reverse* of this `layers` array
    order"). That doc also confirms, by testing it directly against
    Bandit.mohoproj, that reversing the array for RENDERING (not just
    display) produces visibly wrong output - so panel_order is for
    human-readable display only, never for reasoning about paint/z-order.
    """
    out = ['<ul class="tree">']

    def rec(layers):
        ordered = list(reversed(layers)) if panel_order else layers
        for layer in ordered:
            badge = layer_kind_badge(layer)
            wind_attr = ' data-wind="1"' if layer.physics_dynamic else ""
            out.append(
                f'<li><span class="node {badge}"{wind_attr}>'
                f'<span class="tag">{badge}</span>{esc(layer.name)}</span>'
            )
            if layer.children:
                out.append("<ul>")
                rec(layer.children)
                out.append("</ul>")
            out.append("</li>")

    rec(doc.layers)
    out.append("</ul>")
    return "\n".join(out)


def build_shapes_html(doc) -> str:
    """One <details class="rig"> block per vector layer, shape by shape.

    A MeshLayer paints MANY shapes, and each shape's position in the draw
    order plus its boolean combination mode decide what the layer actually
    looks like - two facts a rig report must not leave out. Ground truth,
    read from the same model the exporter uses:

    - Order: `mesh.draw_order()` - which today returns the `shapes` array
      itself (the `shape_order` channel is deliberately ignored where the
      two disagree - see Mesh.draw_order's own docstring for the three
      independent pieces of evidence). A mesh whose raw
      `anim_shape_order` is true (z-order animated by the animator - false
      in every mesh of the 19-sample corpus) gets a warn pill instead of a
      guess about which frame's order to print.
    - combo_mode (Shape.combo_mode): 0/None = plain shape, 1 = union
      member (same-group mode-1 shapes merge into one boolean union),
      3 = intersect (clipped against its group's base union), 2 = not
      decoded by the exporter (warn pill).
    - Style note: brush stamp name, gradient fill, a second stacked fill
      effect, or a gradient outline - the model's own ResolvedStyle.

    Reuses the template's existing details/table/pill CSS - no new
    stylesheet entries are needed for this section.
    """
    out = []
    mesh_idx = 0
    for parents, layer in doc.vector_layers():
        mesh = layer.mesh
        if not mesh.shapes:
            continue
        mesh_idx += 1
        full_path = " ▸ ".join([p.name for p in parents] + [layer.name])
        anim_order = bool((layer._raw.get("mesh") or {}).get("anim_shape_order"))
        anim_pill = ' <span class="pill warn">anim shape order</span>' if anim_order else ""
        out.append(f'<details class="rig" id="mesh-{mesh_idx}">')
        out.append(
            f'<summary>{esc(full_path)}{anim_pill} '
            f'<span class="count">{len(mesh.draw_order())} shapes</span></summary>'
        )
        out.append('<div class="table-wrap"><table>')
        out.append(
            "<thead><tr><th>#</th><th>Shape</th><th>Fill</th><th>Outline</th>"
            "<th>Kết hợp (combo_mode)</th><th>Style</th></tr></thead><tbody>"
        )
        for i, shape in enumerate(mesh.draw_order(), start=1):
            combo = shape.combo_mode or 0
            if combo == 1:
                combo_html = '<span class="pill">union</span>'
            elif combo == 3:
                combo_html = '<span class="pill warn">intersect</span>'
            elif combo == 2:
                combo_html = '<span class="pill warn">combo 2 (chưa giải mã)</span>'
            else:
                combo_html = "—"
            notes = []
            if shape.style.brush_name:
                notes.append(f"brush={shape.style.brush_name}")
            if shape.style.fill_style:
                notes.append("gradient fill")
            if shape.style.fill_style2:
                notes.append("+fill effect 2")
            if shape.style.line_style:
                notes.append("gradient line")
            style_html = ", ".join(esc(n) for n in notes) if notes else "—"
            out.append(
                f'<tr><td class="num">{i}</td><td class="mono">{esc(shape.name)}</td>'
                f"<td>{'✓' if shape.has_fill else '—'}</td>"
                f"<td>{'✓' if shape.has_outline else '—'}</td>"
                f"<td>{combo_html}</td><td>{style_html}</td></tr>"
            )
        out.append("</tbody></table></div>")
        out.append("</details>")
    return "\n".join(out)


def build_rigs_html_and_flags(doc):
    out = []
    flags = {
        "smart_bone_dials": [],
        "ik_bones": [],
        "angle_spring_bones": [],
        "flip_bones": [],
        "wind_rigs": [],
        "gravity_rigs": [],
        "cycle_channels": [],
        "switch_layers": [],
        "masking_layers": [],
        "patch_layers": [],
        "image_layers": [],
        "smart_warp_layers": [],
        "unrigged_bone_containers": [],
        "animated_transform_groups": [],
    }
    rig_count = 0
    total_bones = 0

    for path, layer in doc.walk():
        full_path = " ▸ ".join([p.name for p in path] + [layer.name])

        if layer.action_names:
            flags["smart_bone_dials"].append(
                {"path": full_path, "actions": sorted(layer.action_names)}
            )
        if layer.kind.name == "SWITCH":
            flags["switch_layers"].append(
                {"path": full_path, "keyframes": chan_frames(layer.switch_keys)}
            )
        if layer.group_mask:
            flags["masking_layers"].append(
                {"path": full_path, "role": "container", "value": layer.group_mask}
            )
        if layer.masking:
            flags["masking_layers"].append(
                {"path": full_path, "role": "member", "value": layer.masking}
            )
        if layer.kind.name == "PATCH":
            flags["patch_layers"].append({"path": full_path})
        if layer.kind.name == "IMAGE":
            flags["image_layers"].append({"path": full_path})
        if layer.distortion_layer_uuid or layer.squashable_deformer:
            flags["smart_warp_layers"].append({"path": full_path})

        for field_name, raw in (
            ("translate", layer.transform.translation),
            ("scale", layer.transform.scale),
            ("rotate", layer.transform.rotation_z),
        ):
            ch = Channel.of(raw)
            if ch.cycles:
                flags["cycle_channels"].append(
                    {
                        "path": full_path,
                        "field": f"layer.{field_name}",
                        "cycles": len(ch.cycles),
                    }
                )

        if layer.kind.name == "BONE" and (layer.skeleton is None or not layer.skeleton.bones):
            has_transform_anim = any(
                chan_len(raw) > 1
                for raw in (
                    layer.transform.translation,
                    layer.transform.scale,
                    layer.transform.rotation_z,
                )
            )
            flags["unrigged_bone_containers"].append(
                {"path": full_path, "has_own_transform_animation": has_transform_anim}
            )
            if has_transform_anim:
                flags["animated_transform_groups"].append(
                    {
                        "path": full_path,
                        "translate": chan_frames(layer.transform.translation),
                        "scale": chan_frames(layer.transform.scale),
                        "rotate": chan_frames(layer.transform.rotation_z),
                    }
                )
            continue

        if not layer.skeleton or not layer.skeleton.bones:
            continue

        rig_count += 1
        skel = layer.skeleton
        total_bones += len(skel.bones)

        wind_on = layer.physics_dynamic
        raw = layer._raw
        wind_strength = 0.0
        gravity_strength = 0.0
        if raw.get("wind"):
            vals = (raw["wind"].get("strength") or {}).get("val") or [0.0]
            wind_strength = vals[0]
        if raw.get("gravity"):
            vals = (raw["gravity"].get("strength") or {}).get("val") or [0.0]
            gravity_strength = vals[0]

        names = {i: b.name for i, b in enumerate(skel.bones)}
        subscribed = [b.name for b in skel.bones if _channel_ever_true(b.wind_dynamics)]
        if wind_on and wind_strength:
            flags["wind_rigs"].append(
                {
                    "path": full_path,
                    "strength": wind_strength,
                    "bone_count": len(skel.bones),
                    "subscribed_bones": subscribed,
                }
            )
        if gravity_strength and any(
            _channel_ever_true(b.wind_dynamics) for b in skel.bones
        ):
            flags["gravity_rigs"].append(
                {"path": full_path, "strength": gravity_strength}
            )

        out.append(f'<details class="rig" id="rig-{rig_count}">')
        badge = ""
        if wind_on:
            badge = f' <span class="pill warn">Wind {wind_strength:g}</span>'
        out.append(
            f'<summary>{esc(full_path)}{badge} '
            f'<span class="count">{len(skel.bones)} bones</span></summary>'
        )
        out.append('<div class="table-wrap"><table>')
        out.append(
            "<thead><tr><th>Bone</th><th>Cha (parent)</th>"
            "<th>Độ dài nghỉ</th><th>Góc (angle)</th><th>Vị trí (pos)</th>"
            "<th>Tỉ lệ (scale)</th><th>Ghi chú</th></tr></thead><tbody>"
        )
        for i, b in enumerate(skel.bones):
            pname = names.get(b.parent, "ROOT") if b.parent != -1 else "ROOT"
            notes = []
            if wind_on and b.name in subscribed:
                notes.append('<span class="pill warn">wind</span>')
            tgt_ch = Channel.of(b.target_bone)
            if any(v != -1 for v in tgt_ch.val):
                notes.append('<span class="pill">IK target</span>')
                flags["ik_bones"].append(
                    {"path": full_path, "bone": b.name, "target_values": tgt_ch.val}
                )
            if b.scaling_mode == 2:
                notes.append(f'<span class="pill">auto-stretch x{b.max_auto_scaling:g}</span>')
            if _channel_ever_true(b.flip_h):
                notes.append('<span class="pill">flip_h</span>')
                flags["flip_bones"].append({"path": full_path, "bone": b.name, "axis": "h"})
            if _channel_ever_true(b.flip_v):
                notes.append('<span class="pill">flip_v</span>')
                flags["flip_bones"].append({"path": full_path, "bone": b.name, "axis": "v"})
            if b.dynamics_ever_on:
                notes.append(
                    f'<span class="pill">angle-spring (spring={b.spring_force:g}, '
                    f'damp={b.damping_force:g}, torque={b.torque_force:g})</span>'
                )
                flags["angle_spring_bones"].append({"path": full_path, "bone": b.name})
            for field_name, raw_ch in (
                ("angle", b.anim_angle),
                ("pos", b.anim_pos),
                ("scale", b.anim_scale),
            ):
                ch = Channel.of(raw_ch)
                if ch.cycles:
                    flags["cycle_channels"].append(
                        {
                            "path": full_path,
                            "field": f"bone[{b.name}].{field_name}",
                            "cycles": len(ch.cycles),
                        }
                    )
            note_html = " ".join(notes) if notes else "—"
            out.append(
                f'<tr><td class="mono">{esc(b.name)}</td>'
                f'<td class="mono">{esc(pname)}</td>'
                f'<td class="num">{b.length:.3f}</td>'
                f"<td>{chan_cell_html(b.anim_angle)}</td>"
                f"<td>{chan_cell_html(b.anim_pos)}</td>"
                f"<td>{chan_cell_html(b.anim_scale)}</td>"
                f"<td>{note_html}</td></tr>"
            )
        out.append("</tbody></table></div>")
        out.append("</details>")

    return "\n".join(out), flags, rig_count, total_bones


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: analyze_rig.py <path-to-.mohoproj-or-.animeproj>")
    path = sys.argv[1]

    with open(path, encoding="utf-8") as f:
        raw_doc = json.load(f)
    project_data = raw_doc.get("project_data") or {}

    doc = load_document(path)

    total_layers = len(list(doc.walk()))
    vector_layers = len(doc.vector_layers())

    tree_html_draw_order = build_tree_html(doc, panel_order=False)
    tree_html_panel_order = build_tree_html(doc, panel_order=True)
    rigs_html, flags, rig_count, total_bones = build_rigs_html_and_flags(doc)
    shapes_html = build_shapes_html(doc)

    result = {
        "source_path": path,
        "project": {
            "width": project_data.get("width"),
            "height": project_data.get("height"),
            "start_frame": project_data.get("start_frame"),
            "end_frame": project_data.get("end_frame"),
            "fps": project_data.get("fps"),
        },
        "counts": {
            "total_layers": total_layers,
            "vector_layers": vector_layers,
            "rig_count": rig_count,
            "total_bones": total_bones,
        },
        "top_level_layers_draw_order": [
            {"name": l.name, "kind": l.kind.name} for l in doc.layers
        ],
        "top_level_layers_panel_order": [
            {"name": l.name, "kind": l.kind.name} for l in reversed(doc.layers)
        ],
        # panel_order: what Moho's own Layer Pool panel shows (top row =
        # front-most) - reversed per container, NOT the true paint order.
        # draw_order: the real back-to-front paint order (`layers` file
        # order) - use this whenever reasoning about what's behind/in front
        # of what. See build_tree_html's docstring for the confirmed
        # evidence trail. Always show BOTH, clearly labeled, in the report -
        # never silently pick one.
        "tree_html_panel_order": tree_html_panel_order,
        "tree_html_draw_order": tree_html_draw_order,
        "rigs_html": rigs_html,
        "shapes_html": shapes_html,
        "flags": flags,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
