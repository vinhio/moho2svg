---
name: moho-rig-report
description: Analyzes the layer/bone structure and special motion configurations (Smart Bone, IK, dynamics, wind/gravity physics, flip, switch, masking, cycle...) of a .mohoproj/.animeproj file, then publishes an HTML "rig map" Artifact (hierarchy tree + bone tables + per-layer shape order with combo_mode boolean combination + notes) in the same style as the DarkMan.mohoproj report. Triggers when the user asks to analyze the rig/bones/layers of a Moho file, wants to see its "bone structure" or "how the parts move", or asks for "the same report/artifact as before" for a different Moho file.
allowed-tools: Read, Bash, Write, Artifact
user-invocable: true
argument-hint: "<path to a .mohoproj/.animeproj file, or a filename under moho/>"
---

# moho-rig-report — Rig/bone map for a Moho file

## Goal

Reproduce the **exact style** of the "DarkMan Rig Map" artifact for any
`.mohoproj`/`.animeproj` file in this repo: layer hierarchy tree, a detailed
bone table per rig (parent, rest length, angle/pos/scale keyframe counts),
a per-vector-layer shape table (each shape in real draw order, with its
`combo_mode` boolean combination — a layer draws MANY shapes and they
combine and overlap in that order, so the report must show it), and special
motion configurations (Smart Bone, IK/Target Bone, bone angle-spring
dynamics, flip_h/flip_v, wind/gravity physics, cycle, SwitchLayer, masking,
PatchLayer, ImageLayer, Smart Warp) — published as an HTML Artifact.

**The report's own text stays in Vietnamese, exactly as the DarkMan and
Bandit reports already are** — only this skill's own instructions
(SKILL.md, code comments) are in English. Don't translate the generated
report content when following these instructions.

Content must be **ground truth read directly from the file**, never
guessed. Two assets bundled with this skill do that work:

- `analyze_rig.py` — runs `moho2svg.py`'s real document model (Channel,
  Skeleton, Bone, Layer) against the target file and prints one JSON
  object with every number/flag needed, plus pre-built
  `tree_html_panel_order`/`tree_html_draw_order`/`rigs_html` (HTML
  strings) so the hierarchy tree and bone tables never have to be
  hand-typed.
- `template.html` — the exact CSS/layout shell already used for DarkMan
  (light+dark tokens, same palette, same type scale), with `{{...}}`
  markers to fill in. Its own visible text (section headings, table
  headers, pill labels, etc.) is Vietnamese by design — that's report
  output, not skill instructions, so leave it as-is.

**⚠ Layer order in the file is NOT the order Moho App displays — always
know both, never print just one.** The file stores `layers` in real paint
order (back→front). Moho App's Layer Pool panel displays that order
**reversed**, at EVERY level (recursively) — the panel's top row is the
**last** element of the array at that level, not just a top-level flip.
This is an ordinary UI convention (like Photoshop/After Effects: the
front-most layer sits at the top of the panel), **not** evidence the file
order is "stored backwards" — the file order is still the real paint
order, confirmed directly (reversing the whole array before painting
produces wrong masking output on `Bandit.mohoproj`). See
`docs/moho-project-file-format.md`, the section starting "The Moho app's
own Layer Pool panel...", for the full evidence trail if needed.
`analyze_rig.py` already builds both trees (`tree_html_panel_order`
reverses children at every level, `tree_html_draw_order` keeps the raw
file order) — **always paste both into the report**, never pick just one,
and never hand-reverse any list the script hasn't already reversed.

## Process

### 1. Identify the target file

If the user only gives a name (e.g. "Bandit"), look under `moho/*.mohoproj`
/ `moho/*.animeproj`. If it's ambiguous, ask instead of guessing.

### 2. Run analyze_rig.py

```bash
python3 .claude/skills/moho-rig-report/analyze_rig.py moho/<Project>.mohoproj > /tmp/<slug>-rig.json
```

This script needs **no** Pillow/psd-tools/pyclipper — it only reads the
document model, it doesn't render. If it errors (KeyError, an unfamiliar
layer type...), read the traceback and open `moho2svg.py` to understand the
field involved before patching anything (don't guess field names) — tell
the user which field/layer the script couldn't handle instead of silently
skipping it.

Read the resulting JSON file (`Read`, or `python3 -c "import json; ..."`
via Bash). The important blocks:

- `project` — width/height/start_frame/end_frame/fps → for the "stat" row.
- `counts` — total_layers, vector_layers, rig_count, total_bones → for the
  "stat" row and the opening sentence.
- `tree_html_panel_order` — paste verbatim into the `{{TREE_PANEL}}`
  marker, don't edit it (this is the primary, prominently displayed tree —
  matches Moho App's own Layer Pool order).
- `tree_html_draw_order` — paste verbatim into the `{{TREE_DRAW}}` marker,
  don't edit it (the secondary tree, inside a collapsed `<details>` in the
  template — the real paint order).
- `rigs_html` — paste verbatim into the `{{RIGS}}` marker, don't edit it.
- `shapes_html` — paste verbatim into the `{{SHAPES}}` marker, don't edit
  it. One collapsed `<details>` per vector layer, shapes listed in real
  draw order (`mesh.draw_order()` — today always the `shapes` array order;
  the `shape_order` channel is deliberately ignored, see
  `Mesh.draw_order`'s docstring) with fill/outline, the `combo_mode` pill
  (union / intersect / subtract) and a style note (brush,
  gradient fill, second effect, gradient line). If this string is EMPTY
  (a file with no mesh-carrying layer, e.g. a pure ImageLayer rig), drop
  the whole `<section id="shapes">...</section>` block when assembling in
  step 4 — don't leave an empty shell.
- `flags.*` — use these to **write** the callout/findings/notes (see step
  3); every entry already has a `path` like `parent ▸ child ▸ ...` for
  precise citation.

### 3. Write the dynamic text (in Vietnamese, matching the voice already used for DarkMan/Bandit)

This part requires **synthesis**, not just copying JSON — but every
number/bone name/layer name mentioned must match `flags` in the JSON;
don't invent anything.

**`{{MAIN_CALLOUT}}`** — ONE callout for the single most important finding:

- If `flags.wind_rigs` or `flags.gravity_rigs` is non-empty: this is
  almost always the most notable finding — but describe the mechanism
  precisely, don't undersell it as "just renders at a frozen pose". The
  exporter plays back the raw keyframed angle/pos/scale values exactly as
  written, with **no spring/damping simulation at all**; real Moho instead
  runs those bones through the spring-damper the `wind_dynamics` family
  implies (`spring_force`/`damping_force`/`torque_force`, non-default
  values are a stronger signal). For a bone whose keyframed angle changes
  direction quickly (check `flags.wind_rigs[].subscribed_bones` against
  the bone table's angle keyframes in `rigs_html` for a rapidly
  alternating sequence), that difference is NOT subtle: raw playback hits
  every keyframe's exact extreme, producing MORE oscillation cycles and
  LARGER amplitude than Moho's real damped result — confirmed directly on
  `DarkMan.mohoproj`'s `hat ▸ right_part` bone `B3` (8 keyframes zigzagging
  ±50-99° almost every frame → ~3 raw cycles in the export vs ~2 damped,
  smaller-amplitude cycles the user measured against Moho App/its own
  video export). So the honest framing is "this part may look MORE
  jittery/wobbly in the export than in Moho", not just "may be missing
  some secondary motion". Use the same `<div class="callout">` pattern as
  the DarkMan/Bandit reports, state how many rigs are affected, the wind
  strength, and this over-oscillation caveat — in Vietnamese, matching
  their wording. If a concrete rapidly-alternating bone is easy to spot in
  `rigs_html`, name it as an example the way the DarkMan report now does;
  otherwise keep the caveat general.
- If there's no wind/gravity but `smart_bone_dials`, `ik_bones`, or
  `switch_layers` is non-empty: that's the main finding (name the specific
  bone/layer, since these mechanisms directly affect how export/preview
  behaves).
- If **every** flag array is empty (a "clean" rig, no special mechanism):
  use the `callout calm` class instead of `callout` (a neutral cyan style
  already exists in the template, not the orange warning color), and note
  explicitly that this itself is worth pointing out — the rig only uses
  plain angle/pos/scale keyframes, no Smart Bone/IK/physics/switch.

**`{{FINDINGS}}`** — a grid of `.finding.on`/`.finding.off` cards, ONE card
per mechanism below (keep exactly these 6 for consistency across reports;
add extra cards only if the file has PatchLayer/ImageLayer/Smart Warp):

  Wind/gravity physics · Smart Bone (dial) · IK / Target Bone ·
  Bone angle-spring dynamics · Flip_h/Flip_v on a bone · SwitchLayer / masking

  `.finding.on` (status text "Có dùng", warn background) when the
  corresponding flag is non-empty, `.finding.off` (status text "Không
  dùng", cyan background) when empty. Copy the HTML structure exactly from
  the DarkMan/Bandit example (see either published report, or the
  "Example structure" note below).

**`{{NOTES}}`** — a list of `<li>` inside `<ul class="notes">`, ONE item
per **rig cluster that has its own meaning** (not one item per bone) —
group rigs that repeat the same structure (e.g. 4 identical arms → 1
shared item, don't write it 4 times). For each cluster, explain:

  - Which bones are "real joints" (animated) vs. which just sit still to
    shape a skinning region — read this from the angle/pos/scale columns
    in `rigs_html`/the bone table.
  - Which BoneLayer has **no skeleton at all**
    (`flags.unrigged_bone_containers`) — this is a purely organizational
    group; if it has `has_own_transform_animation: true` (check
    `flags.animated_transform_groups` for the exact keyframes/frames),
    explain that its motion comes from the layer's own transform
    (translate/scale/rotate), not bone deformation.
  - Any pair/group of rigs that looks deliberately duplicated (e.g. one
    "behind" and one "in front" copy of another layer in paint order —
    check `top_level_layers_draw_order` in the JSON, **not**
    `top_level_layers_panel_order`, since "behind/in front" here always
    means real paint order) — state it as an observation, not a certainty
    about artistic intent unless there's clear evidence (use "nhiều khả
    năng" the way the DarkMan report does).

**`{{STATS}}`** — the same 6 `.stat` cells as DarkMan: Canvas, Frame, FPS,
Layer (vector), Rig (BoneLayer), Total bones — taken straight from
`project`/`counts`.

**`{{SUBTITLE}}`** — one sentence, reuse the DarkMan template sentence
verbatim (only the filename changes, if at all): "Cấu trúc layer, khung
xương (bone) và các cấu hình chuyển động đặc biệt được đọc trực tiếp từ
file dự án bằng document model của `moho2svg.py`."

**`{{PAGE_TITLE}}`** — a 2-4 word artifact name specific to the
character/file (e.g. "Bandit Rig Map"), NOT a generic label.
**`{{DOC_NAME}}`** — the raw source filename (e.g. "Bandit.mohoproj").

### 4. Assemble the template and publish

```bash
python3 - <<'EOF'
import json
data = json.load(open('/tmp/<slug>-rig.json'))
template = open('.claude/skills/moho-rig-report/template.html').read()
# Replace each {{MARKER}} with the content written in step 3, and
# {{TREE_PANEL}}/{{TREE_DRAW}}/{{RIGS}}/{{SHAPES}} with
# data['tree_html_panel_order']/data['tree_html_draw_order']/
# data['rigs_html']/data['shapes_html']
# verbatim (don't re-reverse anything - the script already reversed what
# needed reversing). When data['shapes_html'] is empty, delete the whole
# <section id="shapes"> ... </section> block from the page (a rig with no
# vector layer has nothing to show there).
...
open('<scratchpad>/<slug>-rig.html', 'w').write(template)
EOF
```

Write the result into the current session's scratchpad directory (not into
the repo). Before publishing, sanity-check tag balance the same way it was
done for DarkMan/Bandit:

```bash
python3 -c "
c = open('<scratchpad>/<slug>-rig.html').read()
assert c.count('<details') == c.count('</details>')
assert c.count('<ul') == c.count('</ul>')
assert '{{' not in c, 'a marker was left unfilled'
print('ok')
"
```

Then call `Artifact` (`favicon` is required — reuse 🦴 to stay consistent
across rig reports unless the user asks for something else) with a
one-sentence `description` naming the character/file. This is a NEW
artifact for each different file — only pass `url` when the user asks to
revise the exact report already published for that same file.

## Notes

- Don't add any section/mechanism beyond what `analyze_rig.py` actually
  detects — if the user asks about something the script doesn't cover
  (e.g. mesh-point/curve-level animation, audio, particles), say plainly
  that this is a limitation of the current pass instead of guessing.
- On a very large file (hundreds of bones), `rigs_html` still produces one
  collapsed `<details>` per rig so the page doesn't break — no need to
  trim anything, but do mention in chat that the list is long and
  scrollable.
- Keep all of `template.html`'s CSS as-is — that IS what "identical to the
  one already made" means. Only add new CSS if a mechanism genuinely has
  no matching style yet (e.g. a new badge color), and when doing so follow
  the existing light/dark token structure rather than hardcoding a
  standalone color.
