# Moho Animation and Transform Model

Moho does not animate frame by frame. It stores a small number of **keyframes**
per property and lets the program compute every frame in between. Most of the
motion in a real Moho document does not even live on the artwork: it lives on a
**skeleton**, and the artwork follows the bones through a transform stack.

This document explains that model: how time is stored, how a value at an
arbitrary frame is produced, where motion actually comes from in real files,
and how the transform stack turns all of it into a point on the canvas.

Companion documents:

- `moho-project-file-format.md` — the full field reference for the file format.
- `moho-rigging-and-deformation.md` — the bone system in depth (constraints,
  control bones, IK, dynamics), Smart Warp, and the mesh-level fields that
  constrain deformation.
- `moho-export-pipeline.md` — how `moho2svg.py` walks a document and emits SVG.
- `moho-exporting-svg.md` — command-line usage.

This document does not repeat those. It focuses only on time and transforms,
and it adds decoding work that the other documents mark as unknown.

---

## 1. Scope and evidence base

Every number here was measured from the 19 project files in the (gitignored)
`moho/` directory: 17 `.animeproj` files (format versions 1021 and 1038) and 2
`.mohoproj` files (1038 and 1045). Nothing is quoted from Moho's own
documentation.

The measuring method matters, because it changes the counts:

- Every JSON object that carries all four of `type`, `when`, `val` and `interp`
  is treated as a channel.
- The walk **descends into nested channels**: `actions[].pose` (Smart Bone
  poses) and `split[]` (per-axis curves) are separate channels and are counted
  separately from the channel that owns them.

That yields **584,616 channels** and **604,139 `interp` entries** across the 19
files. The channel total matches `moho-project-file-format.md` § 5, so the two
documents count channels the same way. The `interp` totals differ (that
document reports about 210,000 entries), so treat the `interp` statistics below
as the newer measurement.

Claims are labelled:

- **Confirmed** — read directly from the files, with counts.
- **Inference** — the best reading of the evidence, with the evidence given.
- **Not decoded** — observed, but the meaning is unknown. Not guessed.

---

## 2. The core idea: sparse keyframes on independent channels

### 2.1 One channel per property

Almost every property in Moho — a point position, a bone angle, a fill colour,
a layer's rotation, even the name of the visible child of a switch layer — is
stored as the same channel object:

```jsonc
{
  "type": "Val",              // value kind: Val, Vec2, Vec3, Color, Bool, String
  "when": [0, 25, 33, 41],    // keyframe times, in frames
  "val":  [3.14, 3.20, 2.84, 3.20],
  "interp": [ {...}, {...}, {...}, {...} ]   // one entry per keyframe
}
```

There is no document-wide list of frames and no per-frame snapshot of the
scene. A frame is not stored at all; it is **computed** by asking every channel
what its value is at that time. This is what makes Moho files small relative to
their length, and it is why `moho2svg.py` can export any frame without a
"playback" concept: exporting frame `N` means evaluating channels at `N`.

### 2.2 Most channels never move

**Confirmed.** Of the 584,616 channels, **571,915 have exactly one keyframe**
(97.8%) and only **12,701 have two or more** (2.2%). A single-keyframe channel
is a constant; it exists only because Moho stores every property in the same
shape.

Keyframe counts per channel:

| Keyframes | Channels |
|---|---|
| 1 | 571,915 |
| 2 | 10,669 |
| 3 | 943 |
| 4 | 385 |
| 5–9 | 350 |
| 10–19 | 342 |
| 20+ | 12 |

The busiest channel in the whole sample has 20 or more keyframes, and there are
only 12 of those. Real Moho animation is built from very few keys.

### 2.3 Frame numbering, and what frame 0 means

**Confirmed.** All 19 documents use `fps: 24.0`. The authored range is
`project_data.start_frame` … `end_frame`, and `start_frame` is **1** in 18
documents and **25** in `Bandit.mohoproj`. It is never 0.

Frame **0** is the rest / setup frame, not the first frame of the animation:

- Keyframes at frame 0 hold the rig's neutral state.
- `moho2svg.py` computes every bone's rest pose at **frame 0.0** exactly
  (`Skinner.build`), and the deformation of a mesh is defined relative to it.
- `--frame` defaults to `0`, so the tool's default output is the **rest pose**,
  which in every sample document is outside the authored range.

Keyframe times may also lie **past** `end_frame`, because action timelines are
independent of the main timeline (see [§ 7](#7-actions-and-smart-bones)):

| Document | Authored range | Latest keyframe time |
|---|---|---|
| `AddBone.animeproj` | 1–25 | 175 |
| `ControlBones.animeproj` | 1–120 | 240 |
| `WhatIsBone.animeproj` | 1–240 | 227 |
| `Bandit.mohoproj` | 25–127 | 87 |
| `ReparentBone.animeproj` | 1–120 | 0 (nothing is animated) |

### 2.4 Negative keyframe times exist, and they are not animation

**Confirmed.** Negative `when` values appear in only two places:

- `timeline_markers` channels, always as the single value `-1000000`.
- Two `transforms.translation` channels in `SlickObjectTransition.mohoproj`,
  with times such as `-999916`, `-999971`, `-999970`, `-999919`.

**Inference:** `-1000000` is a sentinel base ("far before the timeline") rather
than a real time, and the near-sentinel translation keys are leftovers of the
same mechanism. Their values are the layer's defaults, so ignoring them is
harmless. The mechanism itself is **not decoded**.

Practical effect: a linear evaluator that clamps at the first keyframe returns
those leftover values for every frame before the next real key. In the two
observed channels the leftover value equals the frame-0 value, so nothing is
visibly wrong.

---

## 3. How a value between keyframes is produced

### 3.1 What the file stores

`when[i]`, `val[i]` and `interp[i]` are **always the same length** (confirmed on
all channels, no exceptions). `interp[i]` describes the segment **leaving**
keyframe `i`, so the last entry describes nothing — except when it carries the
cycle marker (see [§ 3.4](#34-v1--v2-and-the-cycle-marker)).

Each `interp` entry has a fixed shape:

```jsonc
{ "im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0,
  "b": [ {"ao": 0.000823, "ai": -0.00003, "po": 0.4375, "pi": 0.515625} ] }
```

`s` is `false` and `h` is `0` on all 604,139 entries. `in` is `1` except on
2,052 entries, all of them `fill_color`, `3d_thickness` or `line_color`. Both
are **not decoded** from file evidence - see [§ 3.2b](#32b-background-from-mohos-own-scripting-api--still-not-a-file-finding)
for what Moho's own API says these fields are (`stagger`/`interval`), still
not confirmed against any sample document that varies them.

### 3.2 `t` — NOT the interpolation type

> **Correction (46-file pass).** This section is kept for its counts, but its
> premise was wrong. `t` is **not** the interpolation type — `im` is, and it is
> now fully decoded in [§ 3.6](#36-im--the-interpolation-method-decoded).
> `t` is most likely the keyframe's **label colour** (`tags` in Moho's own
> scripting header, "used for keyframe color"). Looking for the easing enum in
> this field is why `moho2svg.py` carried an *inferred* easing curve for so
> long: `t` is 0 almost everywhere, so the enum looked undecodable.

**Confirmed** distribution over 604,139 entries:

| `t` | Count | Where it appears |
|---|---|---|
| `0` | 602,784 | everywhere; the default |
| `4` | 757 | `anim_pos`, `anim_scale`, `anim_angle`, action poses |
| `2` | 540 | the same fields |
| `256` | 33 | `physics_motor_speed` only |
| `3` | 16 | `physics_motor_speed` only |
| `1` | 4 | `physics_motor_speed` only |
| `6` | 3 | `physics_motor_speed` only |
| `5` | 2 | `physics_motor_speed` only |

**Confirmed and useful:** every entry with `t` outside `{0, 2, 4}` sits on a
channel with a **single keyframe**, where there is no segment to interpolate.
On channels that actually move, only three values are ever observed: `0`
(default), `2`, and `4`.

**Not decoded:** which Moho interpolation mode each number names. `t` cannot be
read as "4 = Bezier", because `t == 4` occurs in three different contexts: with
default parameters, with explicit Bezier handles, and with the cycle marker.
The value mixes freely inside one channel — a single walk-cycle `anim_angle` in
`Bandit.mohoproj` carries `t = [0, 4, 4, 2, 2, 2, 4, 4, 2, 2, 4]` — so it is a
per-keyframe choice made by the animator, not a channel-wide setting.

### 3.2b Background from Moho's own scripting API — still not a file finding

> Read directly from Moho's own shipped C++ scripting header,
> `/Applications/Moho.app/Contents/Resources/Support/Pro/Extra Files/Lua
> Interfaces/pkg_moho.lua_pkg` - a real file on this machine, but still not a
> real Moho *document*, so this is orientation only, exactly like
> [`moho-rigging-and-deformation.md` § 5.1b](moho-rigging-and-deformation.md#51b-the-mechanism-from-mohos-own-scripting-api--still-not-a-file-finding)
> for the same reason. **Do not change `Channel._segment`/`_parse_cycles`
> against this alone** - it names fields and enum members, not their numeric
> values or exact per-mode curve shapes, and § 3.2/3.3/3.4 above were each
> validated against real exported frames, which nothing below has been.

The API's `InterpSetting` class (one entry per `interp[i]`) has exactly this
field set:

```
class InterpSetting {
    int32   interpMode;   // one of the named constants below
    real    val1;
    real    val2;
    int32   interval;     // 1 = every frame, 2 = on 2's, 3 = on 3's, etc.
    int32   hold;         // frames to hold the previous value before interpolating
    bool    stagger;
    int32   tags;         // "used for keyframe color, and possibly other stuff"
    uint8   flags;
};
#define INTERP_LINEAR
#define INTERP_SMOOTH
#define INTERP_EASE
#define INTERP_STEP
#define INTERP_NOISY
#define INTERP_CYCLE
#define INTERP_POSE
#define INTERP_EASE_IN
#define INTERP_EASE_OUT
#define INTERP_BEZIER
#define INTERP_BOUNCE
#define INTERP_ELASTIC
```

The field NAMES line up one-to-one with this document's own JSON
abbreviations by both position and a documented per-mode meaning that
matches what § 3.4 already found independently:

| JSON key | API field | Corroboration |
|---|---|---|
| `im` | `interpMode` | See below - this is the one field whose READING this section actually revises. |
| `v1` | `val1` | The API comment reads "`INTERP_CYCLE` - val1 = relative starting frame" - an exact match for § 3.4's own independently-derived "`v1 >= 0`: resume at `when[i] - v1`". |
| `v2` | `val2` | Same comment: "val2 = absolute starting frame" - matches § 3.4's "`v2 >= 0`: resume at `v2`" exactly. |
| `in` | `interval` | "1 to interpolate every frame, 2 to animate on 2's, 3 on 3's" - gives §3.1's "not decoded" `in` field a concrete meaning: **stepped/held keyframe density**, not literally "interval between two specific frames". Still not tested against a document where `in` actually varies meaningfully (§3.1 found only 2,052 non-`1` entries, all on colour-ish channels). |
| `h` | `hold` | "how many frames to hold the previous value before interpolating" - a real field, not decoded further; `0` on every sample entry per §3.1. |
| `s` | `stagger` | A real boolean field (matching the Moho 13.5-era "Stagger" keyframe-interpolation-type UI language in the changelogs), not a flag on `im` - `false` on every sample entry per §3.1. |
| `t` | **possibly `tags`, not "the interpolation type"** | See below. |

**Reconsidering §3.2's own `t` framing.** The API has no field literally
named "type" or "mode" other than `interpMode` itself - the closest
positional/semantic match for `t` is `tags` ("used for keyframe colour, and
possibly other stuff in the future"), which is exactly the kind of
free-mixing, non-functional metadata that would explain §3.2's own confirmed
finding that `t` "mixes freely inside one channel" and cannot be read as a
clean mode selector (`t == 4` shows up in three unrelated contexts). If `t`
is `tags`, `im` is the far more likely home for the actual interpolation
MODE - which reframes §3.3 below.

**Reconsidering §3.3's own `im` framing.** §3.3 reads `im` as a **bit
field** (bits 1/2/4/8) because the observed values (`0,1,2,3,5,7,9`) are
consistent with that. They are EQUALLY consistent with `im` being
`interpMode` itself - a plain ~12-way enum, not independently combinable
flags - if the constants above are assigned sequentially in their declared
order (`LINEAR=0, SMOOTH=1, EASE=2, STEP=3, NOISY=4, CYCLE=5, POSE=6,
EASE_IN=7, EASE_OUT=8, BEZIER=9, BOUNCE=10, ELASTIC=11`, unconfirmed - the
header shows no numeric values, only declaration order). Under that reading:
- `im=1` (`SMOOTH`, 446,672 - the overwhelming default) matches ordinary
  Moho knowledge that smooth/TCB interpolation is its default keyframe type.
- `im=9` (`BEZIER`, 182) would mean the enum value ITSELF says "Bezier
  handles follow", not "bit 8 is a modifier flag on some other base mode" -
  and 182 is the EXACT count §3.3 already found for entries carrying the `b`
  array, either reading fits that correlation equally well.
- `im=5`/`im=7` (`CYCLE`/`EASE_IN`, 520 combined) would mean the cycle
  marker is its own discrete mode, not "flag bit 4 layered on top of mode
  1 or 3" - consistent with §3.3's own finding that cycle-marked entries
  never ALSO show `im=9` (Bezier) in this corpus, i.e. the two never
  co-occur, which a true independent-bit-flags model would allow but a
  plain-enum model would forbid by construction.
- `im=3` (`STEP`, 151,877 - "151,875 of those are on single-keyframe
  channels") fits a channel with nothing to interpolate being left at
  whatever Moho's own UI happened to default a fresh single-keyframe
  property to, rather than "bits 1+2 set, meaning unknown".

Both readings currently explain 100% of the observed corpus - a real file
using `BOUNCE`, `ELASTIC`, `NOISY`, `POSE`, or `EASE`/`EASE_OUT` explicitly
(none of which appear among `{0,1,2,3,5,7,9}`) would immediately discriminate
them, and is the concrete next step if this ever gets revisited. **Until
then this is a hypothesis, not a decode** - §3.3's own bit-flag framing
below is left as-is rather than rewritten against unverified enum numbers.

**`BOUNCE`/`ELASTIC`, named for the first time here**, are two of the
interpolation "curve shapes" the Anime Studio Pro 10 changelog
(`mono-changelogs.md`) advertises by the same names ("By applying the
Bounce keyframe type to the timeline, any object interpolated will appear
to bounce... Elastic provides a rubber band effect") - plausible candidates
for part of what §3.5/KNOWN GAPS already call "Moho's own undecoded easing
curve", alongside plain `EASE`/`EASE_IN`/`EASE_OUT`. None of the three
appear in this repository's own 604,139-entry census under the
`im`-as-plain-enum reading either (no `im` value beyond `9` is observed) -
so, real file evidence or not, this corpus still never exercises them.

### 3.3 `im` — a flag field, partly decoded

> See [§ 3.2b](#32b-background-from-mohos-own-scripting-api--still-not-a-file-finding)
> for an alternative reading of these same numbers - `im` as a plain
> ~12-way enum (Moho's own `interpMode`) rather than independent bit flags.
> Both fit every count below equally well; this section's own bit-flag
> framing is left as-is because it is the one actually checked against
> real exported frames.

**Confirmed** distribution: `1` (446,672), `3` (151,877), `0` (3,803), `2`
(1,085), `5` (493), `9` (182), `7` (27).

Those are exactly the values you get from a 4-bit field using bits 1, 2, 4 and
8, and two of the bits line up with observable data:

| Bit | Evidence | Reading |
|---|---|---|
| `8` | `im == 9` on **182** entries; the `b` array is present on **exactly the same 182** entries, and never elsewhere | **Inference (strong):** bit 8 means "explicit Bezier handles are stored in `b`" |
| `4` | `im` values `5` and `7` total 520 entries; **471** of them are the **last** entry of their channel, and they are the only entries carrying the unusual `v1`/`v2` pairs listed below | **Inference:** bit 4 means "this keyframe carries a cycle setting" |
| `1`, `2` | `im == 3` (bits 1+2) occurs 151,877 times, and 151,875 of those are on single-keyframe channels | **Not decoded** |

### 3.4 `v1` / `v2`, and the cycle marker

**Confirmed.** The pair `(0.1, 0.5)` appears on **601,344 of 604,139** entries —
it is the untouched default and carries no information. `(-1.0, -1.0)` appears
on channels the animator has actually worked on.

Everything else appears only together with `im == 5`, on a channel's final
keyframe:

> **Correction (46-file pass).** This used to say "the `im` bit-4 flag", and
> `Channel._parse_cycles` tested `im & 4`, i.e. it accepted `im` 4, 5, 6 and 7
> alike. `im` is an **enum** of interpolation methods, not a bitfield — see
> [§ 3.6](#36-im--the-interpolation-method) — and only `5` is Cycle. Over the
> 46-file corpus the bitmask produced **4,539** cycle specs where only
> **3,040** are real: 1,495 came from `im = 6` with `v1 = 0.0` (a zero-length
> cycle) and 4 from `im = 4` with `v1 = 0.5` (a half-frame one).

| `(v1, v2)` | Count |
|---|---|
| `(-1.0, 2.0)` | 278 |
| `(15.0, -1000000.0)` | 140 |
| `(-1.0, 1.0)` | 47 |
| `(23.0, -1.0)` | 26 |
| `(15.0, -1.0)` | 2 |

**Inference, now decoded well enough to use.** This is Moho's *cycle* setting:
past the marked keyframe the channel does not hold its last value, it jumps
back and replays an earlier stretch of its own timeline. `v1` and `v2` are the
same setting entered two different ways, and only one of them is ever in use —
the other holds a negative sentinel (`-1`, or `-1000000`):

| Slot | When used | Meaning |
|---|---|---|
| `v1 >= 0` | the animator entered a **relative** frame count | resume at `when[i] - v1` |
| `v2 >= 0` | the animator entered an **absolute** frame | resume at `v2` |

"Resume at `R`" means frame `end + 1` takes the value of frame `R`, so the
loop period is `end - R + 1` frames.

**The cycle ACCUMULATES — it replays the motion, not the numbers.** Each
repeat adds `value(end) - value(R - 1)` on top, so a walk cycle walks
somewhere instead of walking on the spot. That delta is zero for a seamless
loop, which is the common case and why the distinction is invisible on most
channels.

This is the best-validated inference in the whole repository, because it is
the only one measured against frames **Moho itself exported**.
`Bandit.mohoproj`'s root bone `B1` carries `anim_pos` keyed over frames 25–41
with the marker on 41, and its x gains `+0.710093` document units — 383.45 px
— every 16-frame repeat. Predicting the character's position from that and
comparing against the 103 frames in `moho/Bandit/svg/`:

| Model | mean \|error\| | max \|error\| |
|---|---|---|
| **accumulating** | **3.3 px** | **8.4 px** |
| plain replay | 1025.7 px | 2299.4 px |

over a march of 2437 px. A plain replay leaves the character walking on the
spot; the reference walks it clean across the frame. Only numeric and
`{x, y[, z]}` values accumulate — a colour, bool or string has no meaningful
"one period's worth of change" and replays unchanged.

**Why "accumulating" needs no flag, even though Moho has one.** Moho's own
scripting API carries `InterpSetting:IsAdditiveCycle()` /
`SetAdditiveCycle(bool)`, so accumulate-vs-replay *is* a per-keyframe switch
inside the application. It is not in the file. The scripting header
(`pkg_moho.lua_pkg`) declares InterpSetting's members in exactly the order the
JSON writes them:

| Header member | JSON key | Notes |
|---|---|---|
| `int32 interpMode` | `im` | the enum of [§ 3.6](#36-im--the-interpolation-method-decoded) |
| `real val1` | `v1` | cycle: relative frames back; `INTERP_NOISY`: noise amplitude; `INTERP_POSE`: pose index |
| `real val2` | `v2` | cycle: absolute frame; `INTERP_NOISY`: noise scale |
| `int32 interval` | `in` | 1 = every frame, 2 = animate on 2s, 3 = on 3s … |
| `int32 hold` | `h` | frames to hold the previous value before interpolating |
| `bool stagger` | `s` | **decoded here** — it is `stagger`, and nothing else |
| `int32 tags` | `t` | keyframe colour |
| `uint8 flags` | — | **not serialised**; this is where the additive-cycle bit lives |

Verified against the corpus: every one of **948,873** interp entries carries
exactly those seven keys — plus `b` on the 257 `INTERP_BEZIER` ones — and
nothing else. So a reader cannot see the flag, and the behaviour that matches
Moho's render is the accumulating one measured above, on a channel whose `s` is
`false`.

Checked directly rather than assumed: setting `s: true` on all 142 cycle
markers in `Bandit.mohoproj` and re-rendering frame 80 with Moho itself changed
**0 of 518,400 pixels**, while a control that changed `v1` from 15 to 8 moved
**9.34%** of them. The experiment was sensitive; `s` is simply inert for a
cycle.

**One third-party formula, one off-by-one.** `AE_KeyTools:GetCycledValue` (see
[docs/moho-mohoscripts-plan.md](moho-mohoscripts-plan.md)) computes this cycle
with an identical period, an identical repeat count and an identical delta base
— independent corroboration of the reading above, from someone with Moho's own
API in hand. It differs on one detail, and is wrong there: it maps the frames
where `(frame - end) mod period == 0` back to `R - 1` rather than to `end`,
landing one delta short. On Bandit that puts frames 57/73/89 back by 383.5 px
for a single frame, whereas Moho's own exported frames 55–59 march
497 → 535 → 557 → 574 → 602 px with no such dip.

**The marker must be ignored inside a Smart Bone action pose.** Moho writes it
there too — `Bandit.mohoproj` carries the same `(v1=15, end=41)` cycle on
`bones[0].anim_pos.actions[0].pose` as on the channel itself — but an action
is a pose library indexed by a dial, not a timeline that plays, and a pose is
read as an *offset*, so an accumulating cycle adds drift that never comes
back. Honouring it moved that document's head and muzzle by a spurious 590 px
across frames 44–80. See `Channel.without_cycles`.

**How this was checked.** Only five of the 19 sample documents use cycles, and
between them only four distinct `(v1, v2, keyframe)` combinations. For each
one, the frame the channel really loops back to was found empirically, by
looking for the earlier frame whose value **equals** the value at the marked
keyframe — which is what a seamless loop makes true, and what animators build.
Scored over every cycling channel of each document, one candidate wins clearly:

| Document | `v1` | `v2` | marked keyframe | winning frame `A` |
|---|---|---|---|---|
| `Bandit.mohoproj` | 15 | -1000000 | 41 | 25 (92 of 94 channels) |
| `TransformBoneTool.animeproj` | 23 | -1 | 25 | 1 (8 of 10) |
| `WhatIsBone.animeproj` | -1 | 2 | 28 | 1 (212 of 217) |
| `OffsetBoneTool.animeproj` | -1 | 2 | 24 | 1 (32 of 32) |
| `BoneStrengthTool.animeproj` | -1 | 1 | 24 | 0 (too few numeric channels to discriminate) |

Both readings land exactly **one frame later** than that winner
(`41 - 15 = 26` against `A = 25`; `v2 = 2` against `A = 1`), in every
document. That off-by-one is the point: the stored number is the frame the
channel *resumes at*, not the loop's first frame. Because `value(A) ==
value(end)` on a seamless loop, replaying `[A + 1, end]` and replaying
`[A, end]` give the same motion, which is why both descriptions fit — the
stored one is used directly.

A second check supports it: with the cycle applied, the value step across the
wrap (`end → end + 1`) is never the largest step in the channel, on any of the
four documents. A wrong resume frame would show up there as a jump.

**Not confirmed:** the repeat count. Nothing in the data distinguishes
"repeat forever" from "repeat N times" — the sentinel `-1000000` is a plausible
"forever", but `-1` is used in the same slot elsewhere, so both are read here
simply as "this slot is unused". Cycles are therefore treated as running
forever, or until the channel's next keyframe when the marker is not on the
last one (17 channels in `WhatIsBone.animeproj` are like that: a cycle on
frame 28 with a further keyframe at 227).

**Consequence for any tool that ignores `interp`:** a cycled channel is **not**
cycled. Past the marked keyframe the value is clamped instead of repeating —
`Bandit.mohoproj`'s walk stops at frame 41 and `WhatIsBone.animeproj`'s at
frame 28, both far short of their documents' own end frames.
`moho2svg.py`'s `Channel` reads the marker (see `Channel._parse_cycles`), so
that no longer applies to this repository's exporters.

### 3.5 `b` — the Bezier timing handles, decoded

The `b` array is present on 182 entries. Its **length equals the number of
components in the channel's value** — confirmed with no exceptions:

| Channel `type` | `len(b)` | Entries |
|---|---|---|
| `Val` | 1 | 101 |
| `Vec3` | 3 | 38 |
| `Vec2` | 2 | 19 |
| `Bool` | 1 | 17 |
| `Color` | 1 | 5 |
| `String` | 1 | 2 |

So `b[c]` holds the timing curve of component `c` — each axis of a `Vec2`/`Vec3`
has its own handles. (`Color` gets a single entry, not four.)

Each entry is `{"ao", "ai", "po", "pi"}` — "out" and "in" of a handle pair:

- `po` / `pi` are **time fractions of the segment**, defaulting to `0.333333`
  (one third), which is the classic Bezier handle length. Observed values stay
  within `0 … 1`. **Inference, strong.**
- `ao` / `ai` are the matching **value-side** components. Reading them as a
  *tangent* (value units per frame) is supported by a chain property: on 93 of
  153 consecutive handle pairs, `interp[i].b[c].ai` is bit-for-bit equal to
  `interp[i+1].b[c].ao`, across segments of **different durations**. Equal
  numbers across unequal segments fit a rate, not an absolute offset. The
  remaining 60 pairs differ, which is what a deliberately broken (non-smooth)
  handle would look like. **Inference, medium.**

This is the timing curve that makes Moho's motion ease in and out. Only a
handful of keyframes in these 19 documents use it explicitly; everything else
relies on the default (`t = 0`) curve, whose exact shape is **not decoded**.

### 3.6 `im` — the interpolation method, decoded

`im` is the interpolation method for the segment **leaving** keyframe `i`
(confirmed directly: a three-keyframe channel with `im = 0` on its first
keyframe and `im = 1` on its second renders a perfectly linear first segment
and a curved second one). It is an **enum**, not a bitfield.

Two fully independent routes agree on all twelve values.

**Route 1 — measurement.** One layer was given a two-keyframe translation,
`im` was set to each value in turn, and Moho's own CLI rendered the whole
frame range so the layer's per-frame centroid traced the curve directly.

**Route 2 — Moho's own scripting header.**
`Contents/Resources/Support/Pro/Extra Files/Lua Interfaces/pkg_moho.lua_pkg`
declares twelve `INTERP_*` constants. Read in declaration order they are
exactly the twelve values the corpus contains:

| `im` | Constant | Measured curve | Corpus entries |
|---|---|---|---|
| 0 | `INTERP_LINEAR` | exactly linear | 54,456 |
| 1 | `INTERP_SMOOTH` | Moho's default — see below | 1,656,205 |
| 2 | `INTERP_EASE` | a stronger S-curve than Smooth | 2,582 |
| 3 | `INTERP_STEP` | exactly step: holds, then jumps | 151,483 |
| 4 | `INTERP_NOISY` | non-monotone, overshoots ~7% | 7 |
| 5 | `INTERP_CYCLE` | the cycle marker ([§ 3.4](#34-v1--v2-and-the-cycle-marker)) | 3,136 |
| 6 | `INTERP_POSE` | exactly linear | 1,495 |
| 7 | `INTERP_EASE_IN` | S-curve weighted to the start | 27 |
| 8 | `INTERP_EASE_OUT` | S-curve weighted to the end | 34 |
| 9 | `INTERP_BEZIER` | needs its own `b` handles | 238 |
| 10 | `INTERP_BOUNCE` | oscillates about the path | 798 |
| 11 | `INTERP_ELASTIC` | overshoots ~27%, then settles | 2,916 |

Three of the header's own comments cross-check things this repository had
already derived, or had wrong:

- *"INTERP_CYCLE — val1 = relative starting frame … val2 = absolute starting
  frame, use -1 to ignore this field"* is exactly what
  [§ 3.4](#34-v1--v2-and-the-cycle-marker) derived from rendered output alone.
- *"INTERP_NOISY — val1 = noise amplitude, val2 = noise scale. good values:
  0.1, 0.5"* explains the `(0.1, 0.5)` pair sitting on 601,344 entries: it is
  the **noise default**, written whatever the mode. It never meant anything.
- *"INTERP_POSE — val1 = index to the pose"* explains `im = 6`'s own
  `v1 = 0.0`, and is why those 1,495 entries are **pose references**, not the
  cycles the old `im & 4` test took them for.

The same header also decodes the extra `b` block that only `im = 9`
(`INTERP_BEZIER`) entries carry — 257 of them in this corpus, and the reason
that method is still unimplemented. `InterpSetting` exposes exactly four
per-component Bezier accessors, `BezierOutAngle` / `BezierInAngle` /
`BezierOutPercentage` / `BezierInPercentage`, and `b` is a **list with one
entry per component**, each `{"ao", "ai", "po", "pi"}` in that same order —
e.g. `Bandit.mohoproj`'s `bones[3].anim_angle` carries
`[{"ao": 0.000823, "ai": -3e-05, "po": 0.4375, "pi": 0.515625}]`. What the two
units actually are is **not** decoded — the names say "angle" and "percentage",
and the observed percentages do sit in `(0, 1)` while the angles are tiny, but
no render has been measured against them yet. The key-name mapping is solid;
the semantics still need the usual treatment before the method can be
implemented.

#### What "Smooth" actually computes

`INTERP_SMOOTH` is a cubic Hermite spline with Catmull-Rom tangents — the
centred difference **in time** across a keyframe's two neighbours — subject to
two rules, both measured: the tangent is **zero at the channel's first and
last keyframes**, and **zero wherever either adjacent segment is flat** (which
is what keeps a held value held instead of bulging out of it). There is no
monotone clamp otherwise; a sign change between adjacent slopes does *not*
flatten the tangent, and Moho lets the curve overshoot there.

Mean |error| against Moho's own renders, in Moho units (1 unit = 360 px at
720p):

| keyframes / values | plain Catmull-Rom | this model | + a 3× clamp |
|---|---|---|---|
| 1, 9, 25 → −0.6, −0.3, +0.6 | 0.000013 | 0.000013 | 0.000013 |
| 1, 13, 25 → −0.6, +0.6, −0.6 | 0.000010 | 0.000010 | 0.000010 |
| 1, 9, 25 → −0.6, −0.6, +0.6 | 0.053008 | **0.000008** | 0.000008 |
| 1, 17, 25 → −0.6, +0.6, +0.6 | 0.052992 | **0.000008** | 0.000008 |
| 1, 9, 25 → −0.6, −0.55, +0.6 | 0.006567 | 0.006567 | 0.026559 |
| 1, 7, 15, 25 → −0.6, .1, −.2, +0.6 | 0.004265 | 0.004265 | 0.012502 |
| **total** | 0.116855 | **0.010871** | 0.030863 |

The last two rows are the ones this model does *not* reproduce exactly (~2 px
at 720p); whatever second-order rule Moho applies to a very lopsided pair of
slopes is still undecoded, and every clamp variant tried made things worse
elsewhere.

**A rejected variant, recorded because it looked better.** Additionally
flattening the tangent where adjacent slopes change sign scores *better* on
`SketchBone.mohoproj`'s reference frames (summed mean error 17.00 px vs 19.85
px, against the old inferred curve's 23.94 px) — but it is not what Moho
computes: solving the Hermite segment out of the fourth measured layout gives
a tangent of 0.0277/frame where that variant would use 0. A whole-rig centroid
comparison runs through bone skinning and everything else, so it can be
improved by a curve that happens to cancel an unrelated error. A direct
measurement of the curve cannot.

**Effect on the tracked reference frames**, replacing the old inferred cubic:

| document | change |
|---|---|
| `Bandit.mohoproj` (103 frames) | Muzzle max dx **4.80 → 0.79**, Belly max dx **3.65 → 0.91** |
| `SketchBone.mohoproj` (12) | mean dx/dy fell for 5 of 7 groups |
| `BoneDynamics.animeproj` (29) | mean dy fell for all 4 groups; several maxima rose, moving that document's fence (see `tools/check_reference_frames.py`) |

### 3.7 What `moho2svg.py` does instead

**Smart Bone poses are applied as an OFFSET, not a replacement** (added in
`Channel.eval` / `_pose_offset`). A pose contributes
`pose(action_frame) - pose(first_action_keyframe)` on top of the channel's own
main-timeline value. This only shows on a channel animated on the main
timeline *and* registered in an action, and `SketchBone.animeproj` has exactly
that: its `govde-don` dial stores a flat `[160.7, 160.7]` pose on bone `B16`,
equal to that bone's rest angle, while `B16` itself swings 126.3 -> 222.4
degrees. Replacing froze the whole `kol-sag-ust` arm at 160.7 degrees for the
entire animation; offsetting makes a flat pose the no-op it clearly is.
Verified against Moho's own arms-only render (`moho/SketchBone/hand/`): arm
mask IoU over 120 frames 11.5% -> 16.1%, whole-frame pixel difference -6.4%.
Frame 0 is unchanged (dials sit at rest, so the offset is zero), so the
exported SVGs stay byte-identical to the pre-change output. Only numeric and
`{x,y,z}` vector channels are offset; colour/bool/string poses still replace.

`Channel.eval_raw` now **reads `interp[].im`** and dispatches on it
([§ 3.6](#36-im--the-interpolation-method-decoded)): Linear, Smooth, Step and
Pose are each reproduced from a measured curve, and Cycle is handled by
`_parse_cycles`. Together those cover 99.4% of the corpus' keyframes.

The seven remaining methods (Ease, Noisy, Ease In, Ease Out, Bezier, Bounce,
Elastic — 0.4% of entries) still fall back to the **monotone cubic** described
below. That curve was chosen before `im` was decoded, when the easing enum was
believed to live in `interp.t` and therefore to be unrecoverable; the shape was
inferred by scoring rendered output against Moho's own arms-only render of
`SketchBone.animeproj` (`moho/SketchBone/hand/`, 120 frames):

| interpolation | all frames IoU | frames 44–54 IoU |
|---|---|---|
| linear | 84.55% | 60.88% |
| smoothstep ease | 79.50% | 65.67% |
| Catmull-Rom | 82.20% | 78.59% |
| **monotone cubic** | **85.76%** | **81.84%** |

Frames 44–54 are the discriminating window: they lie *between* that rig's arm
keyframes (43, 49, 55), where linear scored ~89% **at** each keyframe but
collapsed to 45–65% between them — right poses, wrong curve. Over the whole
animation this cut the full-frame pixel difference by **43.3%**. It remains an
inferred curve, not a decoded one. Frame 0 is untouched, so the tracked
reference SVGs stay byte-identical.

- numbers → monotone-cubic interpolation;
- `{x,y}`, `{x,y,z}`, `{r,g,b,a}` → linear per component;
- strings and booleans → snap to the left keyframe (no interpolation), which is
  the only correct choice for a switch-layer name or a visibility flag.

Consequences, in order of practical importance:

1. **Exact at every keyframe.** Any frame that is a keyframe of every relevant
   channel is reproduced exactly, apart from the rig features in
   [§ 6](#6-motion-that-is-not-keyframed).
2. **Approximate between keyframes.** Linear motion instead of eased motion.
   The visible size of the error depends on the segment, and it is largest on
   long segments with strong easing.
3. **Cycling is applied**, from the marker decoded in
   [§ 3.4](#34-v1--v2-and-the-cycle-marker). The repeat *count* is still not
   decoded, so a cycle runs until the channel's next keyframe, or forever when
   the marker sits on the last one.
4. **`split` is ignored** — the parent `Vec2`/`Vec3` arrays are read instead.
   Only one channel in the whole sample uses `split` (an `anim_pos` in
   `Bandit.mohoproj`), and its split curve matches the parent, so nothing is
   currently wrong.

To put a number on point 2: re-evaluating the 63 `Val` segments that carry
explicit handles, under the tangent reading of `ao`/`ai` from
[§ 3.5](#35-b--the-bezier-timing-handles-decoded), the largest gap between the
eased curve and the straight line is about **0.14 rad (8°)** mid-segment — on
the `anim_angle` pose of the `TorsoA` bone in `Rabbit.animeproj`'s `Jump`
action, whose two keys are only 0.22 rad apart. That number inherits the uncertainty of the tangent reading, so treat it
as an order of magnitude: **mid-segment error can be a large fraction of the
key-to-key change, while keyframes stay exact**.

---

## 4. Where the motion actually is

This is the part that explains why Moho files look the way they do. Counting
**multi-keyframe channels only** — that is, the properties an animator really
moved — over all 19 documents:

| Field | Multi-key channels | What it animates |
|---|---|---|
| `actions[].pose` | 11,816 | a stored pose curve (Smart Bones and actions) |
| `anim_angle` | 383 | bone rotation |
| `position` | 159 | a mesh point moving directly |
| `anim_scale` | 151 | bone scale |
| `anim_pos` | 146 | bone position |
| `bone_dynamics` | 14 | physics switched on/off over time |
| `translation` | 8 | a layer's own position |
| `scale` | 4 | a layer's own scale |
| `offset_in` / `offset_out` | 8 | Bezier handle shape of a curve point |
| `layer_effects.visibility` | 4 | animated show/hide |
| `rotation_z` | 3 | a layer's own rotation |
| `flip_h` | 2 | horizontal flip |
| `switch_keys` | 2 | which switch-layer child is visible |

Read that table as the summary of Moho's design: **motion is stored on the
rig, not on the drawing**. Direct point animation (159 channels) is rare;
layer-transform animation (15 channels) is rarer still; bone channels and
stored poses account for almost everything.

Per document, the motion source is easy to identify:

| Document | Primary motion source |
|---|---|
| `Bandit.mohoproj` | bones (`anim_pos`/`anim_angle`/`anim_scale`, 25 each) plus a `Walk` action |
| `WhatIsBone.animeproj` | bones (214 animated `anim_angle`) plus poses and a switch layer |
| `SketchBone.animeproj` | bones plus poses, a switch layer (mouth), and `flip_h` |
| `OffsetBoneTool.animeproj` | direct point animation (132 `position` channels) plus bones |
| `SlickObjectTransition.mohoproj` | **layer transforms only** — no skeleton at all |
| `AddBone`, `TargetBone`, `IK-FK`, `ControlBones`, … | stored poses only |
| `ReparentBone`, `SelectandReparentBoneTool` | nothing is animated (rig demos) |

`SlickObjectTransition.mohoproj` is the useful counter-example: a document that
animates `translation`, `scale`, `rotation_z`, `visibility` and even curve-point
handles (`offset_in`/`offset_out`) with no bones anywhere.

---

## 5. The transform stack

A drawn point travels through several spaces before it lands on the canvas.
The order is fixed, and getting it wrong is the classic way to produce output
that looks *almost* right.

### 5.1 A layer's own matrix

`transforms` holds ten channels; five of them define the 2D matrix:
`translation` (`Vec3`), `scale` (`Vec3`), `rotation_z` (`Val`), `flip_h` and
`flip_v` (`Bool`). Rotation and scale pivot on the layer's `origin` — a plain
(non-animated) point — not on local `(0, 0)`:

```
p' = origin + translation + R(rotation_z) · S(scale_x, scale_y) · (p - origin)
```

`flip_h` / `flip_v` negate `scale_x` / `scale_y`. Layer scale is genuinely
**per axis**; a bone's scale is a single scalar (see § 5.3).

The remaining transform channels — `rotation_x`, `rotation_y`, `shear`,
`following`, `physics_nudge`, and the `z` components — are **not used** by
`moho2svg.py`. All are at their defaults in the samples except the `z`
components, so nothing observed is currently wrong.

### 5.2 The chain, and why skinning is not just another matrix

The matrices of the ancestor chain compose in the usual way, **but bone
deformation is not a matrix and does not commute with them**. Skinning happens
in the bone layer's *own* coordinate space:

```
raw mesh point (the mesh layer's own space)
      |  every local matrix between the mesh and the bone layer, composed
      v
the BoneLayer's own space          <- the skeleton's matrices live here
      |  skinning (rigid or flexible)
      v
still the BoneLayer's own space, now posed
      |  the bone layer's own local matrix, then everything above it
      v
document space
      |  2 units span the canvas height, y flipped
      v
pixel space
```

So a mesh nested several groups deep inside a `BoneLayer` is deformed *after*
the local transforms between it and the bone layer, and *before* the bone
layer's own transform. `build_deform_chain` in `moho2svg.py` produces exactly
this ordered list of steps; `moho-export-pipeline.md` § 4.2 has the implementation
detail.

One deliberate inconsistency is worth knowing about: **stroke width uses a
different traversal** that composes every layer matrix but **excludes bone
deformation**. That is not an oversight — including bone deformation inflated
stroke width by about 11% on a walk-cycle test.

### 5.3 Bone transforms

Each bone carries `anim_pos` (`Vec2`, relative to the parent bone), `anim_angle`
(`Val`, radians) and `anim_scale` (`Val`, a single scalar). A bone's world
matrix is its parent's world matrix times its own local matrix, with parents
resolved before children regardless of list order — the `bones` array is not
guaranteed to be topologically sorted.

The local matrix as implemented scales only the first column:

```
local = Mat2D(cos·scale, sin·scale, -sin·across, cos·across, pos.x, pos.y)
```

`across` is `1` for a bone with `scaling_mode == 2` (scale along the bone
only) and `scale` for any other bone (ordinary uniform scale).

**`scaling_mode` is now decoded**, correcting an earlier revision that called
the asymmetry unexplained and warned against touching it. It is Moho's
per-bone **"Squash and stretch scaling"** switch, and scaling one axis only is
precisely what squash-and-stretch means. The evidence is
`SketchBone.animeproj`'s `kafasi` head rig: the two bones carrying each ear
(`B2`/`B3` and `B4`/`B5`) have `scaling_mode == 2`, while the third bone in
each ear's own `flexi_bone_subset` (`B20`, `B19`) has `0` — exactly the split
Moho's bone constraints panel shows for that rig. Corpus-wide: `2` on 264
bones, `0` on 586.

Only 28 bones in the whole sample ever move `anim_scale` off `1.0`, and 9 of
those are `scaling_mode == 0` (in `Rabbit`, `BoneDynamics`, `BoneStrengthTool`
and `OffsetBoneTool`), so those are the only places the correction is
observable. None of them appears in the sample documents whose exports are
checked byte-identical, which is why the exported SVGs do not change.

### 5.4 Rigid and flexible binding

Binding is decided **per layer** by `parent_bone`:

- `parent_bone >= 0` — **rigid**: every point follows that one bone exactly.
- `parent_bone == -1` — **flexible / region**: every point is a
  distance-weighted blend of all bones, or of the subset named by
  `flexi_bone_subset` (a `"|"`-joined list of bone **indices**, as a string).

A third value, `parent_bone == -3`, appears on 9 `ImageLayer` instances and is
not decoded.

Rest pose is evaluated at frame 0.0, and each bone contributes
`pose · rest⁻¹`. A bone with `strength <= 0` is skipped entirely before any
weighting — that is Moho's "this bone does not deform this mesh" gate (241 of
850 bones). The falloff shape used for the blend (inverse distance squared) is
a **heuristic** that no available reference could confirm against the
alternatives.

The step-by-step skinning math, the full bone-field reference, and the
per-feature cost of ignoring constraints/IK/control bones are in
[`moho-rigging-and-deformation.md` § 2](moho-rigging-and-deformation.md#2-the-bone-system).

---

## 6. Motion that is not keyframed

This is the largest gap between "the file says" and "Moho shows", and it is the
part most easily missed: several rig features **generate motion at render time**
without writing any keyframe. Nothing bakes them into `anim_angle`.

**Confirmed by direct field inspection of all 850 bones:**

| Feature | Fields | Where it is switched on |
|---|---|---|
| Bone dynamics (spring physics) | `bone_dynamics` (`Bool` channel), `spring_force`, `damping_force`, `torque_force` | **115 bones in 6 documents**: `WhatIsBone` (52), `Bandit` (28 — every bone), `AddBone` (21), `BoneDynamics` (6), `Rabbit` (6), `ControlBones` (2) |
| Angle dynamics | `angle_dynamics` | 2 bones in `Bandit.mohoproj` |
| Wind dynamics | `wind_dynamics` (plain `Bool`, no dedicated `wind_spring_force` etc. — shares the row above's fields), plus `BoneLayer.wind`/`.gravity` (`direction`/`strength`/`turbulence_*`) | **0 bones in this 19-document corpus** — `false` on every bone of the two format-1045 documents checked (`Bandit`, `SketchBone`'s re-save). `DarkMan.mohoproj` (outside this corpus, gitignored, user-supplied) is the first document found where it is `true` — on all 91 of its bones, with `bone_dynamics`/`angle_dynamics` `false` everywhere on the same file, a combination the six documents above never exercise. See `moho2svg.py`'s `Layer.physics_dynamic` and `Skeleton.dynamic_angles`' WIND EVIDENCE section |
| Angle constraints | `constraints`, `min_constraint`, `max_constraint` | **158 bones in 11 documents** |
| Control bones | `angle_control_parent`, `pos_control_parent`, `scale_control_parent` (+ `_scale`, `_delay`) | 4 documents: `ControlBones` (2 bones each for angle/pos/scale), `BoneDynamics`, `AddBone`, `Rabbit`. `Bandit` sets only `scale_control_delay` (8, on one bone) |
| IK targets | `target_bone`, `ik_lock`, `ik_global_angle`, `ignored_by_ik` | `target_bone` set on 41 bones across 14 documents (1–8 bones each) |
| Reparenting over time | `anim_parent` | never keyframed here — see below |

> **Correction.** `moho-project-file-format.md` § 9 states that the
> physics/dynamics fields are "all disabled in the samples". That is not
> correct: `bone_dynamics` is a `Bool` channel whose value is `true` on 115
> bones, and `BoneDynamics.animeproj` even keyframes it (7 channels with more
> than one key). The § 9 bullet has been corrected to match.

Why this matters for any exporter: `Bandit.mohoproj` has dynamics enabled on
all 28 of its bones — 22 of them with `spring_force: 2.0`,
`damping_force: 1.0`, `torque_force: 2.0`, and 6 tuned individually — while its
`anim_angle` channels hold only the animator's own keys. In Moho, the springy follow-through is added on top of those keys at
playback time. A tool that evaluates channels only — as `moho2svg.py` does —
renders the keyed pose **without** the secondary motion. So this is an
**exercised** gap, not a theoretical one: still frames are missing overlap and
follow-through that Moho would show, and the gap grows with distance from a
keyframe.

Two features in the table are safe to ignore, and this is measured rather than
assumed:

- **`anim_parent`** (bone reparenting over time): all 850 channels have exactly
  one keyframe, and that value equals the bone's static `parent` in 850 of 850
  cases. Even `ReparentBone.animeproj` demonstrates the *tool* without ever
  keyframing a reparent.
- **Constraints**: they limit what the animator could pose in the editor; the
  resulting angle is already stored in `anim_angle`.

Each of these features is covered field by field, with the cost of ignoring
it, in
[`moho-rigging-and-deformation.md` § 3](moho-rigging-and-deformation.md#3-bone-constraints-and-rig-helpers).
Two rig fields not listed in the table above also turned out to be non-default
somewhere in the sample: `bone.offset` (5 bones, the Offset Bone tool) and
`skeleton.binding_mode` (`2` on one skeleton). Neither is decoded.

---

## 7. Actions and Smart Bones

Actions are how Moho reuses motion. They live in two different places that look
alike.

### 7.1 The name registry

Nearly every layer carries `actions: [{"name": "...", "pose": 0}]` — 19,921
entries in the sample, with `pose` an integer `0` every time. This is a
**document-wide registry of action names, replicated on almost every layer**,
not a per-layer list. Evidence: a `BoneLayer` with **zero bones** in
`WhatIsBone.animeproj` carries the same 37 action names as the 157-bone layer
above it.

### 7.2 The pose curves

The real data is on individual channels. Any channel may carry its own
`actions` list, and there `pose` is a **complete nested channel** with its own
`when`/`val`/`interp`:

```jsonc
"actions": [
  { "name": "EyeBlink",
    "pose": { "type": "Vec2", "when": [0, 6, 12], "val": [...], "interp": [...] } }
]
```

There are 11,816 such poses — the single most keyframed thing in these
documents, far ahead of `anim_angle`'s 383 channels. **All 11,816 have two or
more keyframes**, without exception, which is what the dial inversion in
[§ 7.3](#73-dials-versus-plain-actions) needs: a curve with one point cannot be
inverted. Pose channel types are
`Vec2` (10,024), `Val` (1,561), `Vec3` (165), `Color` (37), `Bool` (22) and
`String` (7): an action can override any property, including colour.

An action's timeline is **its own**, which is why keyframe times can exceed the
document's `end_frame` ([§ 2.3](#23-frame-numbering-and-what-frame-0-means)).

### 7.3 Dials versus plain actions

A registered action name becomes a **Smart Bone dial** when it matches the
`name` of a bone in the enclosing `BoneLayer`'s skeleton. Names that match no
bone are **plain actions**: reusable clips the user triggers from Moho's
Actions window. Nothing in the file says a plain action is running, so a
renderer must leave it off — `Bandit.mohoproj`'s `"Walk"` is exactly this case.

When dial `D` is active, a channel carrying an entry named `D` reads from that
pose instead of its own keys, at a frame found by **inverting the pose curve**:
the pose's `val` array records what the dial's own angle was at each pose
keyframe, so "the pose frame whose recorded angle equals the dial's current
angle" is well defined. Because a curve must be roughly monotonic to be
invertible, Moho stores two actions per dial, one per rotation direction, the
second suffixed `" 2"` (`"BlinkL"` and `"BlinkL 2"`).

Resolving the dial's own current angle must **not** go through the override
machinery the dial is part of; it reads the raw channel.

---

## 8. Switch layers: discrete animation

A `SwitchLayer` shows exactly one child at a time, and which one is animated by
`switch_keys` — a `String` channel whose values are **child layer names**.
Because strings snap to the left keyframe, this is a step function, which is
exactly right for mouth shapes.

**Confirmed**, both animated instances in the sample:

- `SketchBone.animeproj`: `when = [0, 74, 76, 78, 80, 82, 84, 86]`,
  `val = ["agiz", "agiz", "agiz 2", "agiz 3", "agiz 4", "agiz 5", "agiz 6",
  "agiz"]` — a mouth cycling through six shapes on every second frame, i.e.
  lip sync.
- `WhatIsBone.animeproj`: `when = [0, 1]`, `val = ["agiz1", "agiz6"]`.

`moho2svg.py` implements this (`Layer.switch_active_child`), including a
fallback that Moho itself uses: if the recorded name matches no child — which
happens when a child was renamed after the key was set — the **first** child is
drawn rather than nothing.

---

## 9. Camera animation

`doc.animated_values` holds five channels: `camera_track` (`Vec3`),
`camera_pan_tilt` (`Vec2`), `camera_zoom` (`Val`), `camera_roll` (`Val`) and
`timeline_markers` (`String`).

> **Correction (46-file pass).** An earlier revision of this section said
> "All have exactly one keyframe at frame 0 in all 19 documents, so no sample
> animates the camera", and that `moho2svg.py` "reads none of them". Both
> statements were true of the 19-file corpus and are **false** now. Across the
> 46 files, **12 animate `camera_track` and 10 animate `camera_zoom`**.
> `camera_roll` and `camera_pan_tilt` are still never non-default anywhere.

### 9.1 The projection

The camera is a real perspective camera. For a point on the `z = 0` plane —
which is where 4,556 of the corpus' 4,590 layer-translation keyframes sit — it
reduces to a plain 2D scale-and-translate:

```
half_fov = (pi / 6) / camera_zoom          # 30 degrees at zoom 1
scale    = (height_px / 2) / (camera_z * tan(half_fov))
pixel_x  = (moho_x - camera_x) * scale + width_px / 2
pixel_y  = height_px / 2 - (moho_y - camera_y) * scale
```

Both halves of that were **measured**, not assumed. One small layer of
`Snow-girl-cut51.mohoproj` was rendered by Moho's own CLI at 7 combinations of
`(camera_zoom, camera_z)`, each at three pan values, and `scale` was read off
the centroid displacement between pan values:

| `camera_zoom` | `camera_z` | measured scale | model | error |
|---|---|---|---|---|
| 1 | 3.732051 | 167.049 | 167.077 | +0.017% |
| 2 | 3.732051 | 360.000 | 360.000 | 0.000% |
| 3 | 3.732051 | 547.069 | 547.062 | −0.001% |
| 4 | 3.732051 | 732.705 | 732.699 | −0.001% |
| 6 | 3.732051 | 1102.557 | 1102.562 | +0.000% |
| 2 | 1.7321 | 775.672 | 775.670 | −0.000% |
| 2 | 5.0 | 268.720 | 268.708 | −0.005% |

- **Pan is a pure translation.** The scale implied by a 0.25-unit pan and by a
  0.5-unit pan agreed to five significant figures at every setting, which
  rules out a look-at camera that would rotate as it pans.
- **Half-FOV is exactly `30 / zoom` degrees.** Solving the equation for
  `half_fov` at each measured scale gives 30.000, 15.000, 10.000, 7.500 and
  5.000 degrees at zoom 1, 2, 3, 4 and 6.

### 9.2 Why the default camera looks like no camera at all

Moho's default is `camera_track = {0, 0, 2 + sqrt(3)}` with `camera_zoom = 2`,
and `(2 + sqrt(3)) · tan(15°) = 1` **exactly**. So the default `scale` is
exactly `height/2` and the mapping collapses to the plain one in
[§ 4](#4-coordinate-system) of `moho-project-file-format.md`. That is why
ignoring the camera went unnoticed for so long — and why the exporters now
snap a default camera back to the exact legacy arithmetic, leaving output for
the ~34 documents that never touch the camera byte-for-byte unchanged.

### 9.3 What it cost to ignore

On `Snow-girl-cut51.mohoproj`, whose camera zooms from 2 to 13.5 by frame 100,
comparing this repository's own render against Moho's PNG of the same frame:

| | mean abs difference | pixels differing by >20 |
|---|---|---|
| frame 1 (camera still at default) | 20.20 | 383,444 / 921,600 |
| frame 100, camera ignored | 58.88 | **837,653 / 921,600 (91%)** |
| frame 100, camera applied | 16.65 | 357,991 / 921,600 |

The last row is *better* than the default-camera control frame, so what is
left is the pre-existing brush/shape-effect gap, not framing.

### 9.4 `camera_immune`, and what is still not modelled

A layer with `camera_immune` (manual ch. 12.02, "Immune to camera movements")
projects through the **default** camera instead, so it stays put on screen
while the camera moves — meant for backgrounds, titles and logos. The flag is
inherited by descendants. `--local` also bypasses the camera, since it means
"raw mesh coordinates at canvas scale".

Still not modelled: per-layer **parallax** (a layer translated in z should
divide by `camera_z − layer_z`, not `camera_z`), `camera_roll` and
`camera_pan_tilt`. The latter two are never non-default in the corpus; a
non-zero layer z occurs in 6 documents, 2 of which (`Gathered-01Intro2`,
`Snow-girl-cut2`) also animate the camera.

---

## 10. Rendering animation with `moho2svg.py`

The tool exports **one frame per run**. There is no built-in sequence mode.

```bash
# One frame (frame 0 = the rest pose, which is before the authored range)
python3 moho2svg.py moho/Bandit.mohoproj --combined out/frame_0025.svg --frame 25

# A whole range, one SVG per frame
for f in $(seq 25 127); do
  python3 moho2svg.py moho/Bandit.mohoproj \
      --combined "out/frame_$(printf '%04d' "$f").svg" --frame "$f"
done
```

Notes that come from actually running this:

- **Output is deterministic** for a given frame: exporting the same frame twice
  produced byte-identical files (verified on `Bandit.mohoproj` frame 41).
- **Frames differ as expected**: frames 0, 25, 33 and 41 of `Bandit.mohoproj`
  each produced different geometry.
- **Clamping is per channel, not per document.** Frame 200 is past the last
  bone key (41) but not past every channel in the file (the latest key is 87),
  so it is not identical to frame 41. Only a frame past *every* channel's last
  key is a true freeze.
- **`--frame` takes an integer.** The evaluator itself works in floating point,
  so sub-frame sampling is possible in code but not from the command line.
- Add `--brush-dir ""` while iterating: brush stamping dominates export time,
  and turning it off makes a per-frame loop practical.
- Use the **same flags for every frame**. Changing `--crop` between frames
  changes the viewBox and the sequence will jitter.

---

## 11. Gap summary for animation and transforms

Ordered by how likely it is to change what you see.

| Gap | Status | Effect |
|---|---|---|
| Bone dynamics (springs) ignored | **exercised** — 115 bones in 6 documents | missing follow-through / overlap; worst far from a keyframe |
| Easing (`interp`) ignored, linear used instead | **exercised** — every multi-key channel | exact at keyframes, approximate between them |
| Cycle setting ignored | **exercised** — ~470 channels carry the marker on their last key | motion stops at the last key instead of repeating |
| `layer_effects.visibility` ignored | **exercised** — 4 animated channels in `SlickObjectTransition` | a layer that should appear/disappear mid-animation does not |
| Control bones (`*_control_parent`) ignored | **exercised** — a handful of bones in 4 documents | driven bones do not follow their driver |
| IK (`target_bone`) ignored | partly exercised | the solved pose is usually already in `anim_angle`; a target-driven limb may not be |
| Camera channels ignored | not exercised (all static) | framing would be wrong in a document with a moving camera |
| `split` per-axis curves ignored | not exercised (1 channel, matching values) | wrong values if the axes are keyed differently |
| `mute: true` channel still animated | not exercised (the one muted channel has a single key) | a muted multi-key channel would move when Moho freezes it |
| `anim_parent` (reparenting) ignored | **not exercised** — 850/850 match the static parent | none, for these files |

---

## 12. Reproducing the numbers

Every count in this document comes from walking the raw JSON of the 19 files in
`moho/`, with these rules:

1. A dict holding all of `type`, `when`, `val`, `interp` is a channel.
2. Descend into `actions[].pose` and `split[]` and count those as channels of
   their own.
3. "Animated" means `len(when) > 1`.
4. For bone flags stored as channels (`bone_dynamics`, `target_bone`, …), take
   `val[0]` and compare against the field's default.

Rule 2 is the one that changes results the most: skipping nested poses hides
11,816 of the 12,701 animated channels — that is, it hides most of the
animation in a rigged Moho document.
