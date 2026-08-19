# Moho Field Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise this repository's coverage of Moho document-content fields from a
measured 35.5% to 95% of the 434 content keys, so a script can change anything a
person could change in the Moho application.

**Architecture:** Add a measuring instrument first (runtime key trace + a
disposition registry embedded in `schema/`), then an editing foundation
(`mohoedit.py`: ZIP container I/O, save, integrity checks; plus `_raw` retention
on `moho2svg.py`'s document model), then sweep the remaining fields with one
repeatable triage probe that renders the same document twice with one field
changed.

**Tech Stack:** Python 3, standard library only. No test framework exists in this
repository — verification means check scripts under `tools/` driven by `make`,
and the outside authority is Moho 14.4's own headless renderer. `jsonschema`,
Pillow, `psd-tools` and `pyclipper` stay optional.

**Spec:** [`superpowers/specs/2026-08-18-moho-field-coverage-design.md`](superpowers/specs/2026-08-18-moho-field-coverage-design.md)
— read it before Task 1. This plan implements that design and does not restate
its reasoning.

## Global Constraints

- **English only** in every file, comment, docstring, commit message and printed
  string, per `.claude/ai/AGENTS.md`. The narrowing in `CLAUDE.md` covers only
  `docs/localization/**` and `tmp/**`.
- **No new required third-party dependency.** `mohoedit.py` and everything under
  `tools/` is standard library only.
- **Every new file, class and function carries a docstring** explaining *why* a
  constant is what it is, matching `moho2svg.py`'s density.
- **Commit style:** plain imperative sentences, matching `git log`. Not
  Conventional Commits. No tool attribution, no AI co-author trailer.
- **Regression gate for every task:** `make check-export`, `make check-lottie`
  and `make check-reference` all pass, re-run regardless of what the task
  touched.
- **Measurement provenance:** every recorded number states the corpus it ran
  against and the command that produced it.
- **Corpus is 76 documents**, at any nesting depth under `moho/`, `.moho`
  archives included. Any measurement over 46 files is wrong — see the spec § 1.

---

## Progress

This table is the single place to read overall status. Each task's own steps
carry `- [ ]` checkboxes further down.

**How to update it.** A task becomes `DONE` only when its **final commit has
landed** and its stated check passed — not when the code is written. Tick the
task's step checkboxes as you go, then flip the row and record the commit.
Anything started but unfinished is `IN PROGRESS`, and its row says which step it
stopped at.

**Read this before trusting any percentage below.** Every coverage figure in
this plan derives from the string-literal baseline, which the spec § 1 shows is
wrong in both directions. **Task 8 produces the first real number.** When it
lands, recompute this table's percentages from `make check-coverage` and record
the correction in Task 8's row. Do not treat the numbers below as measured until
then.

| # | Work item | Coverage after | Status | Commit |
|---|---|---|---|---|
| P1 | Full 76-document census, content/description split, difficulty triage | — | **DONE** | *(scripts in `tmp/`, gitignored)* |
| P2 | Design document | — | **DONE** | `a258574` |
| P3 | This plan | — | | |
| 1 | Export-stability gate (`check-export`) | — | **DONE** | `f3c91e8`, `10c8cc7` |
| 2 | Fix the `PatchLayer` load-time mutation | — | **DONE** | `5140b7f`, `5d173df` |
| 3 | Read `.moho` archives (the `PROJECT_STEMS` step is dropped — see Q5) | — | **DONE** | `9908e65`, `b269139` |
| 4 | `mohoedit.py`: save, including `.moho` archives | — | **DONE** | `1ab84f9`, `5ea84ca` |
| 5 | Retain `_raw` on the lossy document-model classes | — | **DONE** | `8941e8f` |
| 6 | Round-trip check over all 76 documents | — | **DONE** | `f691cc4` |
| 7 | Runtime field trace | *measured 32.7%* | **DONE** | `0c61804`, `83899ce` |
| 8 | Disposition registry + `check-coverage` + **real baseline** | *32.5% measured (corrected from 32.7% in fix round 1 — see task-8-report.md)* | **DONE** | `2c208e0`, + fix round 1 |
| 9 | Integrity checker, detect-only (**scope narrowed** — see ruling) | — | **DONE** | `d223b72`, `5e46232` |
| 10 | Field probe harness | — | **DONE** | `df487e1`, `0df5114` |
| M1.1 | Template: camera / project / transforms + shared (72 keys) | 49.3% | | |
| M1.2 | Template: image / PSD (21) | 54.1% | | |
| M1.3 | Template: style / shape effects (15) | 57.6% | | |
| M1.4 | Template: mesh / point + compositing (22) | 62.7% | | |
| M1.5 | Template: remainder (14) | 65.9% | | |
| M2.1 | Bone IK + constraints + physics (27) | 72.1% | | |
| M2.2 | Particle (16) | 75.8% | | |
| M2.3 | Text + balloon (12) | 78.6% | | |
| M2.4 | Sketchy / noise / textures (8) | 80.4% | | |
| M2.5 | Image, mesh, audio, layer order, compositing, channel, style (34) | 88.2% | | |
| M3.1 | 3D extrude, via one `3d_mode = 1` precondition (10) | 90.6% | | |
| M3.2 | Bone physics, via `enable_physics` precondition (5) | 91.7% | | |
| M3.3 | Sketchy + mesh remainder, **grown to 31 of the 39 constant-valued keys** (see ruling below) | **95.16%** | | |

**Measured baseline (Task 8, 2026-08-18, corrected 2026-08-19 in fix round 1).**
`make check-coverage` (census `out/census_keys.json`: 76 documents, 547 keys;
trace `out/traced_keys.json`: 76 documents, 143 keys, 0 export errors,
Pillow/psd-tools/pyclipper all importable) now scores **141 / 434 = 32.5%** —
the number printed by `tools/check_field_coverage.py`, with
`registry failures 0`. (First recorded as 142/32.7%; fix round 1 corrected
`channel.InterpEntry.b`, the Bezier-handle array, from a false `MODELLED`
claim to `UNKNOWN` — its evidence had pointed at `Color.from_raw`, which
reads an unrelated `b` field, the blue channel, that merely shares the name;
see task-8-report.md's Finding A. One content key, no more.) This supersedes
the 35.5% (154/434) grep-based figure this table's percentages were
originally computed from.

**Ripple effect on the "Ruling closing the shortfall" note below, flagged but
not yet re-applied**: that ruling's arithmetic (403/434, the 29-of-39 M3
growth, 95.2%) was computed against the 142 baseline, one day before this
correction landed. Substituting 141: baseline 141 + M1 144 + M2 97 + M3-as-
originally-scoped 20 = 402/434 = 92.6%, ten keys short of 412 (not nine), so
closing the gap the same way now needs M3 to decode 30 of the 39
constant-valued keys, not 29, landing at 412/434 = 94.93% (still short of an
exact 95.00%, which no integer numerator over 434 hits exactly — 413/434 =
95.16% is the nearest at-or-above value, one key past the stated 412-key
target). Left for whoever next revisits that ruling to re-apply, rather than
rewritten here, since it is not this round's mandate.

**The `Coverage after` column above is now recomputed from 32.7%**, using
the exact same per-milestone key counts § 7 already committed to (`(142 +
running total) / 434`) — those counts describe how much UNDONE work each
milestone closes, which the trace does not change, only the measured
STARTING point does.

**M1 does not need splitting on volume — but the plan's own arithmetic no
longer reaches 95%, and that must be fixed before M3 is considered done.**
The grep baseline overcounted "already modelled" by exactly 12 keys (154 vs
the trace-verified 142), and § 7's milestone table was built by partitioning
that 154-key surplus and a 280-key remainder (434 − 154) into M1–M3 (261
keys) plus a 19-key residual (154 + 261 + 19 = 434, exact). Substituting the
real baseline without changing anything else leaves 142 + 261 + 19 = 422,
twelve short of 434 — those 12 keys were never fictional, the grep count
just miscounted them as already done, so nothing in M1–M3 as currently
scoped closes them. The practical effect: completing every M1–M3 task
exactly as specified now lands at 403/434 = **92.9%**, not 95.6%, missing the
95% target by 9 keys even with zero execution slippage. **Action required
before M3 is scored as complete:** widen the residual-budget accounting or
fold roughly a dozen additional keys into M1's template pass (the cheapest
milestone per key) once Task 10's probe identifies which 12 the grep method
had wrongly marked modelled — this is bookkeeping, not new investigation,
since a `MODELLED` claim now needs the trace's confirmation and any of the
12 the grep overcounted will show up as `UNKNOWN` in the registry the moment
someone looks. Re-run this recomputation once that placement is decided;
do not let M3.3 close against the stale 95.6% figure above.

**Ruling closing the shortfall (controller, 2026-08-18).** The 9-key gap is real
and is closed by **growing M3, not by moving the target**. Audited: baseline 142
+ M1 144 + M2 97 + M3-as-originally-scoped 20 = 403 / 434 = 92.9%, nine keys
short of the 412-key target. The plan's original 95.6% assumed a 154-key
baseline that the string-literal instrument had inflated.

**M3 therefore decodes 31 of the 39 constant-valued keys, not 20.** That lands
at 413 / 434 = 95.16%, leaving a residual of **8 keys against the 21-key
budget** — comfortably inside it.

**Two corrections to this ruling, made after Task 8's fix round (2026-08-19).**
First, the baseline is **141**, not 142: Task 8's fix round withdrew a false
`MODELLED` claim on the Keyframe field `b`, whose evidence pointed at
`Color.from_raw` — a function that reads the unrelated blue-channel `b`. Second,
and separately, **the target itself was off by one**: `434 x 0.95 = 412.3`, so
412 keys is **94.93%**, *below* the bar. Reaching >= 95.0% needs **413** keys, and
the residual budget is therefore **21**, not 22. Both corrections are folded into
the numbers above. The denominator (434), the target (412) and
the residual budget (22) are all unchanged; only M3's share grows.

The alternative — relaxing the 95% target or shrinking the denominator — would
be moving the goalposts to meet the measurement instead of doing the work.
Growing M3 spends budget that was already reserved for exactly this class of
key. The cost is that these are the **most expensive nine keys in the plan**:
every constant-valued key needs a synthesised document and a working
precondition, because no corpus document exercises it.

Tasks 1–10 are specified in full below. M1–M3 are specified as a **repeatable
recipe** (see "The sweep recipe") rather than as per-key steps, because the steps
of a decode task depend on what the probe finds. Writing per-key steps now would
mean writing placeholders, which this plan forbids.

---

## File structure

| File | Responsibility |
|---|---|
| `mohoedit.py` (new) | Owns the raw JSON tree for editing: container I/O (`.moho` ZIP and bare JSON), save, integrity checks, index renumbering. Standard library only. |
| `tools/check_export_stability.py` (new) | Byte-level regression gate: re-export a fixed document set, compare against tracked hashes. |
| `tools/check_roundtrip.py` (new) | load → save → structural compare over all 76 documents. |
| `tools/trace_fields.py` (new) | Tracing mapping + export driver; emits the set of keys actually read. |
| `tools/check_field_coverage.py` (new) | Registry ∩ trace → coverage figure, per-area Markdown table, two fail-closed rules. |
| `tools/probe_field.py` (new) | One-field triage probe: synthesise a twin, render both with Moho, diff. |
| `tools/export_hashes.txt` (new, tracked) | The hashes `check_export_stability.py` compares against. |
| `moho2svg.py` (modify) | Retain `_raw` on the lossy model classes; stop mutating `PatchLayer` raw dicts. |
| `schema/*.schema.json` (modify) | Carry `x-moho-disposition` and `x-moho-render` per property; reach all 547 keys. |
| `Makefile` (modify) | `check-export`, `check-roundtrip`, `check-coverage` targets; `PROJECT_STEMS` sees all 76 documents. |
| `docs/moho-project-file-format.md` (modify) | Record each field's decoded meaning as it lands. |

---

## Task 1: Export-stability gate

Nothing in this repository currently detects a byte-level change in SVG output —
the "five tracked SVGs" gate referenced by `moho-to-lottie-plan.md` no longer
exists, because every export moved under the gitignored `out/`. Task 2 is a
refactor whose entire claim is "output does not change", so that gate must exist
first.

**Files:**
- Create: `tools/check_export_stability.py`
- Create: `tools/export_hashes.txt`
- Modify: `Makefile`

**Interfaces:**
- Produces: `make check-export`, which exits non-zero if any export's SHA-256
  differs from `tools/export_hashes.txt`. Every later task's regression gate
  calls it. `--update` rewrites the hash file, for the rare task that changes
  output deliberately.

- [ ] **Step 1: Write the check script**

```python
#!/usr/bin/env python3
"""Byte-level export regression gate.

Re-exports a fixed set of documents and compares each output's SHA-256 against
`tools/export_hashes.txt`. This is the gate that `moho-to-lottie-plan.md` used
to get from five SVGs tracked in git; those moved under the gitignored `out/`,
so the hashes are tracked instead of the files -- 64 hex characters per export
rather than megabytes of XML.

Deliberately a fixed, small document set rather than all 76: this runs after
every task, so it has to stay fast. Coverage of exotic layer types is the job
of `check_roundtrip.py`, which does read all 76.
"""

import argparse
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HASH_FILE = os.path.join(ROOT, "tools", "export_hashes.txt")

# One document per feature cluster that has bitten this repository before:
# Bandit (masking, combo_mode, Smart Bones), SketchBone (brushes, patches,
# gradients), WhatIsBone (masks and gradients together), DonkeyAndMan
# (patch layers with a real bone chain), TransformBoneTool (fixed_angle).
EXPORTS = [
    ("moho/Bandit.mohoproj", ["--combined", "{out}", "--frame", "25"]),
    ("moho/SketchBone.animeproj", ["--combined", "{out}", "--frame", "1"]),
    ("moho/WhatIsBone.animeproj", ["--combined", "{out}", "--frame", "120"]),
    ("moho/DonkeyAndMan.mohoproj", ["--combined", "{out}", "--frame", "0"]),
    ("moho/TransformBoneTool.animeproj", ["--combined", "{out}", "--frame", "12"]),
]


def run_exports(outdir):
    """Return {label: sha256} for every export in EXPORTS."""
    os.makedirs(outdir, exist_ok=True)
    digests = {}
    for src, args in EXPORTS:
        if not os.path.exists(os.path.join(ROOT, src)):
            print("SKIP %s (absent)" % src)
            continue
        label = os.path.basename(src)
        out = os.path.join(outdir, label + ".svg")
        cmd = [sys.executable, os.path.join(ROOT, "moho2svg.py"),
               os.path.join(ROOT, src)] + [a.format(out=out) for a in args]
        subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        with open(out, "rb") as fh:
            digests[label] = hashlib.sha256(fh.read()).hexdigest()
    return digests


def load_expected():
    if not os.path.exists(HASH_FILE):
        return {}
    out = {}
    with open(HASH_FILE) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                digest, label = line.split(None, 1)
                out[label] = digest
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true",
                    help="rewrite the hash file instead of comparing")
    ap.add_argument("--outdir", default=os.path.join(ROOT, "out", "stability"))
    args = ap.parse_args()

    got = run_exports(args.outdir)
    if args.update:
        with open(HASH_FILE, "w") as fh:
            fh.write("# SHA-256 of each export produced by tools/check_export_stability.py.\n")
            fh.write("# Regenerate with --update ONLY when output changes deliberately.\n")
            for label in sorted(got):
                fh.write("%s  %s\n" % (got[label], label))
        print("wrote %d hashes to %s" % (len(got), HASH_FILE))
        return 0

    expected = load_expected()
    if not expected:
        print("FAIL: %s is missing. Create it with --update." % HASH_FILE)
        return 1
    bad = 0
    for label in sorted(got):
        if label not in expected:
            print("FAIL %-34s not in hash file" % label)
            bad += 1
        elif expected[label] != got[label]:
            print("FAIL %-34s expected %s got %s" % (label, expected[label][:12], got[label][:12]))
            bad += 1
        else:
            print("ok   %-34s %s" % (label, got[label][:12]))
    for label in sorted(set(expected) - set(got)):
        print("FAIL %-34s expected but not produced" % label)
        bad += 1
    print("\n%s: %d exports, %d mismatched" % ("FAIL" if bad else "OK", len(got), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it and confirm it fails, because no hash file exists yet**

Run: `python3 tools/check_export_stability.py`
Expected: `FAIL: tools/export_hashes.txt is missing. Create it with --update.`, exit 1

- [ ] **Step 3: Record the current output as the baseline**

Run: `python3 tools/check_export_stability.py --update`
Expected: `wrote 5 hashes to .../tools/export_hashes.txt`

- [ ] **Step 4: Run again and confirm it now passes**

Run: `python3 tools/check_export_stability.py`
Expected: five `ok` lines, then `OK: 5 exports, 0 mismatched`, exit 0

- [ ] **Step 5: Prove the gate actually catches a change**

Temporarily change one emitted number in `moho2svg.py` — for example add `+ 1`
to the stroke-width result in `Exporter._stroke_width_px` — then run the check.

Run: `python3 tools/check_export_stability.py`
Expected: at least one `FAIL` line and exit 1. **Revert the edit** and confirm
the check passes again. A gate never observed failing is not a gate.

- [ ] **Step 6: Add the Makefile target**

```makefile
# Byte-level export regression gate. Re-exports five documents and compares
# their SHA-256 against tools/export_hashes.txt. Runs after every task in
# docs/moho-field-coverage-plan.md, so it stays deliberately small and fast.
# Regenerate the hashes with `make check-export-update` ONLY when an output
# change is intended.
check-export:
	$(PYTHON) tools/check_export_stability.py

check-export-update:
	$(PYTHON) tools/check_export_stability.py --update
```

- [ ] **Step 7: Commit**

```bash
git add tools/check_export_stability.py tools/export_hashes.txt Makefile
git commit -m "Add a byte-level export regression gate

Nothing detected a change in SVG output after the Makefile restructure moved
every export under the gitignored out/. Tracks a SHA-256 per export instead of
the files themselves, and is confirmed to fail on a deliberately altered stroke
width."
```

---

## Task 2: Fix the `PatchLayer` load-time mutation

`Document._resolve_patch_layers` writes the target layer's rigging into the
patch's **raw dict** (`moho2svg.py:5135-5137`). A patch's own transform *is* its
clip region, so any editor that loads a document and saves it loses that data.
Five documents in the corpus carry 12 patch layers: `DonkeyAndMan.mohoproj`,
`SketchBone.animeproj`, `SketchBone.mohoproj`, `Others/AddBone.animeproj`,
`Others/ReparentBone.animeproj`.

This is a **render-neutral refactor**: the substituted values move from the raw
dict onto the `Layer` object, so rendering must not change at all. Task 1's gate
is what proves that.

**Files:**
- Modify: `moho2svg.py:5076-5140` (`Document._resolve_patch_layers`) and the
  `Layer` properties that read `parent_bone` / `flexi_bone_subset` / `origin`
  (`moho2svg.py:4520-4560`)
- Create: `tools/check_no_raw_mutation.py`

**Interfaces:**
- Consumes: `make check-export` from Task 1.
- Produces: `Layer._patch_substitute`, a dict or `None`, holding the three
  substituted values; the `parent_bone`, `flexi_bone_subset` and `origin`
  properties prefer it over `self._raw`. Task 5 and Task 6 rely on the raw tree
  being unmodified by document construction.

- [ ] **Step 1: Write the failing check**

```python
#!/usr/bin/env python3
"""Assert that constructing a Document does not modify the raw JSON tree.

Document construction used to overwrite every PatchLayer's own parent_bone,
flexi_bone_subset and origin with its target layer's values, in the raw dict
(moho2svg.py:5135-5137 before this check existed). A patch's own transform is
its clip region -- see docs/moho-project-file-format.md 12.1 -- so an editor
that loaded and saved a document silently destroyed it.

Runs over the five corpus documents that carry PatchLayers.
"""

import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import moho2svg  # noqa: E402

PATCH_DOCS = [
    "moho/DonkeyAndMan.mohoproj",
    "moho/SketchBone.animeproj",
    "moho/SketchBone.mohoproj",
    "moho/Others/AddBone.animeproj",
    "moho/Others/ReparentBone.animeproj",
]


def main():
    bad = 0
    for rel in PATCH_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print("SKIP %s (absent)" % rel)
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw = json.load(fh)
        before = copy.deepcopy(raw)
        moho2svg.Document.from_raw(raw)
        if raw == before:
            print("ok   %-40s raw tree unchanged" % rel)
        else:
            print("FAIL %-40s raw tree MUTATED by construction" % rel)
            bad += 1
    print("\n%s: %d documents, %d mutated" % ("FAIL" if bad else "OK", len(PATCH_DOCS), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 tools/check_no_raw_mutation.py`
Expected: `FAIL` on all five documents, exit 1. This is the bug reproducing.

- [ ] **Step 3: Move the substitution off the raw dict**

In `Document._resolve_patch_layers`, replace the three assignments at
`moho2svg.py:5135-5137` with one attribute:

```python
                        # A patch reuses its target's MESH, so it must also
                        # borrow the target's binding to draw that mesh in the
                        # right place -- but its OWN transform is its clip
                        # region (docs/moho-project-file-format.md 12.1), so
                        # the borrowed values must never be written back into
                        # the raw tree. Keeping them beside it lets an editor
                        # load, change and save a document without destroying
                        # the patch's own rigging.
                        layer._patch_substitute = {
                            "parent_bone": target._raw.get("parent_bone", -1),
                            "flexi_bone_subset": target._raw.get("flexi_bone_subset", ""),
                            "origin": target._raw.get("origin"),
                        }
```

Initialise `self._patch_substitute = None` in `Layer.__init__` beside
`self._raw = raw`, and make the three properties prefer it:

```python
    @property
    def parent_bone(self) -> int:
        if self._patch_substitute is not None:
            return self._patch_substitute["parent_bone"]
        return self._raw.get("parent_bone", -1)
```

Apply the same two-line pattern to `flexi_bone_subset` and `origin`, keeping
each property's existing default and return type exactly as they are.

- [ ] **Step 4: Run the check and confirm it passes**

Run: `python3 tools/check_no_raw_mutation.py`
Expected: five `ok` lines, `OK: 5 documents, 0 mutated`, exit 0

- [ ] **Step 5: Prove rendering did not change**

Run: `make check-export && make check-lottie && make check-reference`
Expected: all three pass. `check-export` passing is the whole claim of this
task — the refactor is render-neutral. If it fails, a property was missed;
find it before continuing, and do **not** run `check-export-update`.

- [ ] **Step 6: Add the check to the Makefile and commit**

```makefile
check-roundtrip:
	$(PYTHON) tools/check_no_raw_mutation.py
```

```bash
git add moho2svg.py tools/check_no_raw_mutation.py Makefile
git commit -m "Stop overwriting a PatchLayer's own rigging when a document loads

_resolve_patch_layers wrote the target layer's parent_bone, flexi_bone_subset
and origin into the patch's raw dict, so loading and saving a document
destroyed the patch's own transform - which is its clip region, not decoration.
The borrowed values now live on the Layer as _patch_substitute and the three
properties prefer them, leaving the raw tree untouched. Render-neutral:
check-export, check-lottie and check-reference all unchanged."
```

---

## Task 3: Read `.moho` archives, and make `make` see all 76 documents

30 of the 76 corpus documents are `.moho` ZIP archives holding one
`Project.mohoproj`. No script reads them today, and `PROJECT_STEMS` globs only
`moho/*.animeproj moho/*.mohoproj` — top level, bare JSON only. Both gaps must
close before Task 7's trace runs, or the trace measures 46 files and repeats the
census error the spec § 1 describes.

**Files:**
- Create: `mohoedit.py`
- Modify: `moho2svg.py` (`load_document`, around `moho2svg.py:9384-9392`)
- Modify: `Makefile:153` (`PROJECT_STEMS`)

**Interfaces:**
- Produces:
  - `mohoedit.read_document(path) -> (raw: dict, container: Container)` — parses
    bare JSON or an archive. `Container` records what is needed to write the same
    shape back: `Container.kind` is `"json"` or `"zip"`, `Container.member` is the
    archive member name, `Container.extras` is `{name: bytes}` for every other
    archive member (i.e. `preview.jpg`).
  - `mohoedit.Container` — a dataclass; Task 4 writes through it.
- Consumes: nothing from earlier tasks.

- [ ] **Step 1: Write the failing check**

Append to `tools/check_roundtrip.py` — create the file with this content:

```python
#!/usr/bin/env python3
"""Every document under moho/ parses, at any depth, archives included.

Task 6 grows this into a full load -> save -> compare round-trip. At Task 3 it
asserts only that all 76 documents can be read, which is what the trace in
Task 7 depends on.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mohoedit  # noqa: E402

EXPECTED_DOCUMENTS = 76


def iter_paths():
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "moho")):
        for fn in sorted(filenames):
            if fn.endswith((".mohoproj", ".animeproj", ".moho")):
                yield os.path.join(dirpath, fn)


def main():
    ok = bad = 0
    for path in sorted(iter_paths()):
        rel = os.path.relpath(path, ROOT)
        try:
            raw, container = mohoedit.read_document(path)
            assert isinstance(raw, dict) and "layers" in raw, "no layers key"
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print("FAIL %-52s %s" % (rel, repr(exc)[:70]))
            bad += 1
    print("read %d documents, %d failed" % (ok, bad))
    if ok + bad < EXPECTED_DOCUMENTS:
        print("FAIL: expected at least %d documents, walked %d" % (EXPECTED_DOCUMENTS, ok + bad))
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 tools/check_roundtrip.py`
Expected: `ModuleNotFoundError: No module named 'mohoedit'`

- [ ] **Step 3: Write the reader**

Create `mohoedit.py`:

```python
#!/usr/bin/env python3
"""Editing side of the Moho document format: container I/O, save, integrity.

`moho2svg.py` reads a document to draw it; this module reads one to CHANGE it.
The split is deliberate. The reading model there is calibrated against Moho's
own renders and must not be duplicated, while renumbering, validation and
saving are new responsibilities -- and `moho2svg.py` is already 9,576 lines.

A `.moho` file is a plain ZIP holding `Project.mohoproj` and optionally
`preview.jpg` -- confirmed against all 30 archives in the corpus, and
documented in Moho's own manual, Appendix F. `.mohoproj` / `.animeproj` are
the same JSON, bare. Both are read here and written back in the same shape,
because handing a user a bare .mohoproj when they gave you a .moho makes them
re-zip it by hand.
"""

import dataclasses
import json
import os
import typing
import zipfile

PROJECT_MEMBER_SUFFIX = ".mohoproj"


@dataclasses.dataclass
class Container:
    """How a document was packaged, so it can be written back the same way.

    `extras` holds every archive member that is not the project JSON -- in
    practice `preview.jpg`, the thumbnail Windows Explorer and macOS QuickLook
    show. It is carried verbatim rather than regenerated: regenerating needs a
    render, and a wrong thumbnail is worse than a stale one. Appendix F states
    Moho recreates it on its next save anyway.
    """

    kind: str                                  # "json" or "zip"
    member: typing.Optional[str] = None        # archive member holding the JSON
    extras: typing.Dict[str, bytes] = dataclasses.field(default_factory=dict)


def read_document(path: str) -> typing.Tuple[dict, Container]:
    """Parse a Moho document, bare or archived, and report its packaging."""
    if path.endswith(".moho"):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            member = next((n for n in names if n.endswith(PROJECT_MEMBER_SUFFIX)), None)
            if member is None:
                raise ValueError("no %s member in %s (has %s)"
                                 % (PROJECT_MEMBER_SUFFIX, path, names))
            raw = json.loads(archive.read(member).decode("utf-8", "replace"))
            extras = {n: archive.read(n) for n in names if n != member}
        return raw, Container(kind="zip", member=member, extras=extras)
    with open(path, encoding="utf-8", errors="replace") as handle:
        return json.load(handle), Container(kind="json")
```

- [ ] **Step 4: Run the check and confirm it passes**

Run: `python3 tools/check_roundtrip.py`
Expected: `read 76 documents, 0 failed`, exit 0

- [ ] **Step 5: Route `moho2svg.py` through the reader, so `--list` works on an archive**

In `load_document` (`moho2svg.py:9384-9392`) replace the direct `json.load`
with `mohoedit.read_document(path)[0]`, importing `mohoedit` at the top of the
file beside the other local imports. Then confirm an archive exports:

Run: `python3 moho2svg.py "moho/Snow_wars/06.moho" --list | head -5`
Expected: a layer listing, not a JSON decode error.

- [ ] **Step 6: Make `PROJECT_STEMS` see all 76 documents**

`Makefile:153` currently reads only the top level. Replace it with a recursive
search that includes archives:

```makefile
# Every Moho document under moho/, at any depth, archives included. The old
# form globbed moho/*.animeproj moho/*.mohoproj only, so every aggregate
# target saw 46 of the 76 documents - see docs/moho-field-coverage-plan.md
# Task 3. Stems keep their subdirectory so two documents with the same
# basename in different folders do not collide.
PROJECT_FILES := $(shell find moho -type f \( -name '*.animeproj' -o -name '*.mohoproj' -o -name '*.moho' \) -not -path 'moho/track/*')
PROJECT_STEMS := $(sort $(basename $(patsubst moho/%,%,$(PROJECT_FILES))))
```

Run: `make -n svg-all | wc -l`
Expected: substantially more lines than before the change; confirm with
`make -n svg-all | grep -c 'Snow_wars'` that subdirectory documents now appear.

- [ ] **Step 7: Run the full gate and commit**

Run: `make check-export && make check-lottie && make check-reference`
Expected: all pass — this task adds a reader and changes no geometry.

```bash
git add mohoedit.py tools/check_roundtrip.py moho2svg.py Makefile
git commit -m "Read .moho archives, and let make see all 76 documents

A .moho file is a ZIP holding Project.mohoproj plus an optional preview.jpg -
30 of the 76 corpus documents are archives and nothing could read them. Adds
mohoedit.read_document for both packagings and carries the other archive
members verbatim so a save can rebuild the same shape. PROJECT_STEMS globbed
only the top level, so every aggregate make target saw 46 documents."
```

---

## Task 4: `mohoedit.py` save, including archives

**Files:**
- Modify: `mohoedit.py`
- Modify: `tools/check_roundtrip.py`

**Interfaces:**
- Consumes: `mohoedit.read_document`, `mohoedit.Container` from Task 3.
- Produces: `mohoedit.write_document(path, raw, container, keep_preview=True)`.
  Task 6 and every later editing task call it.

- [ ] **Step 1: Extend the check to a real round-trip**

Replace `tools/check_roundtrip.py`'s `main` with:

```python
def main():
    import json
    import tempfile
    ok = bad = 0
    for path in sorted(iter_paths()):
        rel = os.path.relpath(path, ROOT)
        try:
            raw, container = mohoedit.read_document(path)
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, os.path.basename(path))
                mohoedit.write_document(out, raw, container)
                again, container2 = mohoedit.read_document(out)
            assert again == raw, "structure changed"
            assert container2.kind == container.kind, "packaging changed"
            assert set(container2.extras) == set(container.extras), "archive members lost"
            for name, blob in container.extras.items():
                assert container2.extras[name] == blob, "member %s altered" % name
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print("FAIL %-52s %s" % (rel, repr(exc)[:70]))
            bad += 1
    print("round-tripped %d documents, %d failed" % (ok, bad))
    if ok + bad < EXPECTED_DOCUMENTS:
        print("FAIL: expected at least %d documents, walked %d" % (EXPECTED_DOCUMENTS, ok + bad))
        return 1
    return 1 if bad else 0
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 tools/check_roundtrip.py`
Expected: 76 `FAIL` lines reporting `AttributeError: module 'mohoedit' has no attribute 'write_document'`

- [ ] **Step 3: Write the writer**

Append to `mohoedit.py`:

```python
def write_document(path: str, raw: dict, container: Container,
                   keep_preview: bool = True) -> None:
    """Write a document back in the packaging it came in.

    Formatting is deliberately not matched byte-for-byte. Moho writes
    `indent=2` in format 1045 and fully minified JSON in 1038, and its float
    formatting differs from Python's either way, so no stdlib preset reproduces
    an input exactly. What matters is that Moho re-reads the result: an
    unedited load-and-save was confirmed to render pixel-identically (0 of
    921,600 pixels changed on TransformBoneTool.animeproj frame 12). `indent=2`
    is chosen because it makes a diff between two saves readable, which matters
    far more here than matching Moho's own whitespace.

    `keep_preview=False` drops non-project archive members, so a stale
    thumbnail is absent rather than misleading; Moho regenerates it on its next
    save.
    """
    text = json.dumps(raw, indent=2, ensure_ascii=False)
    if container.kind == "json":
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return
    member = container.member or "Project" + PROJECT_MEMBER_SUFFIX
    # ZIP_DEFLATED, not ZIP_STORED: Appendix F notes the compression is the
    # whole point of the container ("250 MB down to about 4 MB"), and Moho's
    # own manual asks third-party tools for the most portable zip form.
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, text)
        if keep_preview:
            for name, blob in container.extras.items():
                archive.writestr(name, blob)
```

- [ ] **Step 4: Run the check and confirm it passes**

Run: `python3 tools/check_roundtrip.py`
Expected: `round-tripped 76 documents, 0 failed`, exit 0

- [ ] **Step 5: Prove Moho itself still opens a saved archive**

```bash
python3 - <<'PY'
import mohoedit
raw, c = mohoedit.read_document("moho/Snow_wars/06.moho")
mohoedit.write_document("out/rt-06.moho", raw, c)
PY
/Applications/Moho.app/Contents/MacOS/Moho -r out/rt-06.moho -f PNG -start 1 -end 1 -o out/rt-06.png
```

Expected: a PNG is produced. Compare it against the same render of the original
document; they must be identical. A structural round-trip that Moho rejects is
not a round-trip.

- [ ] **Step 6: Wire the target and commit**

```makefile
check-roundtrip:
	$(PYTHON) tools/check_no_raw_mutation.py
	$(PYTHON) tools/check_roundtrip.py
```

```bash
git add mohoedit.py tools/check_roundtrip.py Makefile
git commit -m "Save Moho documents, archives included

write_document rebuilds the packaging it was given, carrying every non-project
archive member verbatim. Byte-identical text is explicitly not a goal - no
stdlib json preset reproduces Moho's own formatting, and Moho re-reads indent=2
output and renders it pixel-identically. All 76 documents round-trip
structurally, and a saved archive still opens in Moho 14.4."
```

---

## Task 5: Retain `_raw` on the lossy document-model classes

`Mesh`, `Shape`, `Curve`, `CurvePoint`, `MeshPoint`, `Edge`, `Bone`, `Skeleton`
and `Transform` each extract a subset of their source dict and discard it —
`Shape` keeps 9 of 17 keys, `MeshPoint` 3 of 11, `Bone` roughly 35 of 61 — and
`Document` keeps no root dict at all. Editing below `Layer` is therefore
impossible through the model. This task is purely additive: keep the source dict
beside the extracted fields.

**Files:**
- Modify: `moho2svg.py` — each class's `_build` classmethod, and `Document.from_raw`

**Interfaces:**
- Produces: `.raw` on `Mesh`, `Shape`, `Curve`, `CurvePoint`, `MeshPoint`,
  `Bone`, `Skeleton`, `Transform`, and `Document.raw` for the root dict. Task 9's
  integrity checker and every M1 task read these.

- [ ] **Step 1: Write the failing check**

Create `tools/check_model_raw.py`:

```python
#!/usr/bin/env python3
"""Every document-model object exposes the dict it was built from.

Without this an editor cannot reach anything below Layer: Shape keeps 9 of its
17 JSON keys, MeshPoint 3 of 11, Bone about 35 of 61, and Document kept no root
dict at all. The reading model stays as it is -- this only stops it throwing
the source away.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import moho2svg  # noqa: E402
import mohoedit  # noqa: E402


def main():
    raw, _ = mohoedit.read_document(os.path.join(ROOT, "moho/Bandit.mohoproj"))
    doc = moho2svg.Document.from_raw(raw)
    checks = []
    checks.append(("Document.raw is the root dict", doc.raw is raw))
    found_mesh = found_bone = False
    for layer in doc.walk() if hasattr(doc, "walk") else doc.all_layers():
        mesh = getattr(layer, "mesh", None)
        if mesh is not None and not found_mesh:
            found_mesh = True
            checks.append(("Mesh.raw", isinstance(mesh.raw, dict)))
            checks.append(("Shape.raw", isinstance(mesh.shapes[0].raw, dict)))
            checks.append(("Curve.raw", isinstance(mesh.curves[0].raw, dict)))
            checks.append(("CurvePoint.raw", isinstance(mesh.curves[0].points[0].raw, dict)))
            checks.append(("MeshPoint.raw", isinstance(mesh.points[0].raw, dict)))
        skel = getattr(layer, "skeleton", None)
        if skel is not None and getattr(skel, "bones", None) and not found_bone:
            found_bone = True
            checks.append(("Skeleton.raw", isinstance(skel.raw, dict)))
            checks.append(("Bone.raw", isinstance(skel.bones[0].raw, dict)))
    bad = 0
    for label, passed in checks:
        print("%s %s" % ("ok  " if passed else "FAIL", label))
        bad += 0 if passed else 1
    if not (found_mesh and found_bone):
        print("FAIL: did not reach both a mesh and a skeleton")
        bad += 1
    print("\n%s: %d checks, %d failed" % ("FAIL" if bad else "OK", len(checks), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
```

If `Document` exposes neither `walk()` nor `all_layers()`, read the tree with
the same recursion `Exporter.export_document` uses and adjust the loop; do not
add a new traversal API in this task.

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 tools/check_model_raw.py`
Expected: `FAIL Document.raw is the root dict` and an `AttributeError` on the
first `.raw` access.

- [ ] **Step 3: Keep the source dict in each `_build`**

These are **plain classes with an `__init__`**, not dataclasses — except `Edge`,
which is a frozen dataclass built by zipping three parallel arrays and therefore
has no single source dict to keep. `Edge` is excluded from this task for that
reason; the arrays live on `shape.raw["edges"]`, which is reachable once `Shape`
keeps its dict.

For each of `Mesh`, `Shape`, `Curve`, `CurvePoint`, `MeshPoint`, `Bone`,
`Skeleton` and `Transform`: add a `raw` parameter to `__init__`, assign it, and
pass it from `_build`. `Shape._build` is a `@staticmethod` at
`moho2svg.py:4393` that constructs with all-keyword arguments, so `raw=raw` goes
**last**, after the existing ones:

```python
    def __init__(self, shape_id, name, has_fill, has_outline, combo_mode,
                 edges, style, effect_scale, effect_rotation, raw=None):
        # ... every existing assignment stays exactly as it is ...
        self.effect_rotation = effect_rotation
        # The dict this Shape was built from. Kept because the extraction above
        # drops eight of the seventeen keys a real shape carries - selected,
        # fill_allowed, combo_blend_anim, effect_offset, 3d_thickness and the
        # inherited_style pair - and an editor has to reach them.
        self.raw = raw

    @staticmethod
    def _build(raw: dict, styles: StyleTable) -> "Shape":
        e = raw["edges"]
        edges = [Edge(c, s, f) for c, s, f in zip(e["curve"], e["segment"], e["flag"])]
        return Shape(
            # ... every existing keyword argument stays exactly as it is ...
            effect_rotation=raw.get("effect_rotation", 0.0),
            raw=raw,
        )
```

`raw=None` defaults rather than being required, so any other construction site
in `moho2svg.py` or `moho2lottie.py` keeps working untouched. In
`Document.from_raw`, store the root the same way: `doc.raw = raw`.

Do not change any existing field, default or return type — a change there is a
rendering change, and `check-export` will catch it.

- [ ] **Step 4: Run the check and confirm it passes**

Run: `python3 tools/check_model_raw.py`
Expected: every line `ok`, `OK: 8 checks, 0 failed`, exit 0

- [ ] **Step 5: Prove nothing rendered differently**

Run: `make check-export && make check-lottie && make check-reference && make check-roundtrip`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add moho2svg.py tools/check_model_raw.py Makefile
git commit -m "Keep the source dict on every document-model object

Mesh, Shape, Curve, CurvePoint, MeshPoint, Bone, Skeleton and Transform each
extracted a subset of their JSON and discarded the rest - Shape kept 9 of 17
keys, MeshPoint 3 of 11 - so nothing below Layer could be edited through the
model. Purely additive: the extracted fields are unchanged and every export is
byte-identical."
```

Add `tools/check_model_raw.py` to the `check-roundtrip` target in the same
commit.

---

## Task 6: Round-trip an edit, not just a load

Task 4 proved an untouched document survives. An editor needs the stronger
claim: a **changed** document survives, and Moho agrees the change happened.

**Files:**
- Create: `tools/check_edit_roundtrip.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: `mohoedit.read_document`, `mohoedit.write_document`.
- Produces: `make check-roundtrip` also covering an edit. Task 10's probe
  harness reuses the same edit-then-render shape.

- [ ] **Step 1: Write the check**

```python
#!/usr/bin/env python3
"""An edited document survives a save, and Moho renders the edit.

The weaker claim -- an untouched document round-trips -- is check_roundtrip.py.
This one changes a value, saves, reloads, confirms the change is still there,
then renders with Moho twice and requires the pixels to DIFFER. A save that
silently dropped the edit would pass a structural check and fail here.

Uses TransformBoneTool.animeproj because it is small, has a bone whose angle
visibly moves the artwork, and is already a check-reference fixture.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mohoedit  # noqa: E402

MOHO = "/Applications/Moho.app/Contents/MacOS/Moho"
SOURCE = os.path.join(ROOT, "moho/TransformBoneTool.animeproj")
FRAME = 12
DELTA = 0.6          # radians; large enough that antialiasing cannot explain it


def first_skeleton(node):
    if isinstance(node, dict):
        if isinstance(node.get("bones"), list) and node["bones"]:
            return node
        for value in node.values():
            found = first_skeleton(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = first_skeleton(value)
            if found is not None:
                return found
    return None


def render(path, out):
    subprocess.run([MOHO, "-r", path, "-f", "PNG",
                    "-start", str(FRAME), "-end", str(FRAME), "-o", out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stem, ext = os.path.splitext(out)
    produced = "%s_%05d%s" % (stem, FRAME, ext)
    return produced if os.path.exists(produced) else out


def main():
    if not os.path.exists(MOHO):
        print("SKIP: Moho is not installed at %s" % MOHO)
        return 0
    outdir = os.path.join(ROOT, "out", "editrt")
    os.makedirs(outdir, exist_ok=True)

    raw, container = mohoedit.read_document(SOURCE)
    base = os.path.join(outdir, "base.animeproj")
    mohoedit.write_document(base, raw, container)

    raw2, container2 = mohoedit.read_document(SOURCE)
    bone = first_skeleton(raw2)["bones"][0]
    channel = bone["anim_angle"]
    before = list(channel["val"])
    channel["val"] = [v + DELTA for v in before]
    edited = os.path.join(outdir, "edited.animeproj")
    mohoedit.write_document(edited, raw2, container2)

    reloaded, _ = mohoedit.read_document(edited)
    got = first_skeleton(reloaded)["bones"][0]["anim_angle"]["val"]
    if got != [v + DELTA for v in before]:
        print("FAIL: edit did not survive the save: %s" % got)
        return 1
    print("ok   edit survives the save")

    base_png = render(base, os.path.join(outdir, "base.png"))
    edit_png = render(edited, os.path.join(outdir, "edited.png"))
    with open(base_png, "rb") as a, open(edit_png, "rb") as b:
        same = a.read() == b.read()
    if same:
        print("FAIL: Moho rendered the edited document identically - the edit had no effect")
        return 1
    print("ok   Moho renders the edit differently")
    print("\nOK: edit round-trip verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it and confirm it passes**

Run: `python3 tools/check_edit_roundtrip.py`
Expected: two `ok` lines and `OK: edit round-trip verified`. This check is
expected to pass immediately — Tasks 3–5 built what it needs. If it fails, the
save path is wrong and Task 4 is not actually done.

- [ ] **Step 3: Confirm it can fail, by breaking the writer on purpose**

Temporarily make `write_document` write the *original* `raw` regardless of
argument. Run the check.
Expected: `FAIL: edit did not survive the save`. **Revert.**

- [ ] **Step 4: Wire it in and commit**

```makefile
check-roundtrip:
	$(PYTHON) tools/check_no_raw_mutation.py
	$(PYTHON) tools/check_roundtrip.py
	$(PYTHON) tools/check_model_raw.py
	$(PYTHON) tools/check_edit_roundtrip.py
```

```bash
git add tools/check_edit_roundtrip.py Makefile
git commit -m "Verify an edited document survives a save and Moho renders the edit

A structural round-trip cannot tell a working save from one that silently
discards the change. This rotates a bone by 0.6 rad, saves, reloads to confirm
the value persisted, then requires Moho's own renders of the two files to
differ. Confirmed to fail when the writer is made to ignore its argument."
```

---

## Task 7: Runtime field trace

**Files:**
- Create: `tools/trace_fields.py`

**Interfaces:**
- Produces: `tools/trace_fields.py --out out/traced_keys.json`, writing
  `{"keys": [...], "documents": N, "errors": [...]}` — the set of key names read
  at least once during a real export. Task 8 consumes this file.

- [ ] **Step 1: Write the tracer**

```python
#!/usr/bin/env python3
"""Record which JSON keys the exporters actually read.

Coverage was previously estimated by searching each key as a quoted string
literal in the Python sources. That miscounts in both directions: a literal can
sit in a comment while nothing reads the value, and channel keys (`when`,
`val`, `interp`, `actions`) are consumed through variables so they never appear
as literals at the point of use. A target of 95% cannot rest on an instrument
with unquantified error in both directions.

This wraps every dict in the parsed tree in a mapping that records each key
lookup, then runs both exporters over all 76 documents. A key never recorded is
provably unread.

Deliberately records key NAMES, not paths: the registry in schema/ is keyed by
property name, and a path-keyed trace could not be joined to it.
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mohoedit  # noqa: E402

SEEN = set()


class TracingDict(dict):
    """A dict that records every key looked up, including failed lookups.

    Failed lookups count: `raw.get("fixed_angle", False)` on a document that
    omits the key still proves the exporter consumes that field. Subclassing
    dict rather than wrapping keeps `isinstance(x, dict)` true throughout
    moho2svg.py, which tests for it in many places.
    """

    def __getitem__(self, key):
        SEEN.add(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        SEEN.add(key)
        return super().get(key, default)

    def __contains__(self, key):
        SEEN.add(key)
        return super().__contains__(key)


def instrument(node):
    """Rebuild the tree with every dict replaced by a TracingDict."""
    if isinstance(node, dict):
        return TracingDict((k, instrument(v)) for k, v in node.items())
    if isinstance(node, list):
        return [instrument(v) for v in node]
    return node


def iter_paths():
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "moho")):
        dirnames[:] = [d for d in dirnames if d != "track"]
        for fn in sorted(filenames):
            if fn.endswith((".mohoproj", ".animeproj", ".moho")):
                yield os.path.join(dirpath, fn)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "traced_keys.json"))
    ap.add_argument("--frame", type=int, default=0)
    args = ap.parse_args()

    import moho2svg
    import moho2lottie

    docs = 0
    errors = []
    for path in sorted(iter_paths()):
        rel = os.path.relpath(path, ROOT)
        raw, _ = mohoedit.read_document(path)
        for label, run in (
            ("svg", lambda d: moho2svg.Exporter(
                d, moho2svg.RenderSettings()).export_document(args.frame)),
            ("lottie", lambda d: moho2lottie.LottieExporter(
                d, moho2lottie.RenderSettings()).export(args.frame, args.frame)),
        ):
            try:
                run(moho2svg.Document.from_raw(instrument(raw)))
            except Exception as exc:  # noqa: BLE001
                errors.append("%s [%s] %s" % (rel, label, repr(exc)[:90]))
        docs += 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"keys": sorted(SEEN), "documents": docs, "errors": errors}, fh, indent=1)
    print("traced %d documents, %d keys read, %d export errors"
          % (docs, len(SEEN), len(errors)))
    for line in errors[:10]:
        print("   ERROR %s" % line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

The two constructor calls must match the real signatures of
`moho2svg.Exporter` / `export_document` and `moho2lottie.LottieExporter` /
`export`. Read both before running and correct the lambdas — do not guess.

- [ ] **Step 2: Run it**

Run: `python3 tools/trace_fields.py`
Expected: `traced 76 documents, N keys read, 0 export errors`. Any export error
means the tracing dict broke a code path; fix the tracer, not the exporter.

- [ ] **Step 3: Sanity-check the result against the grep estimate**

Run:
```bash
python3 - <<'PY'
import json
traced = set(json.load(open("out/traced_keys.json"))["keys"])
print("traced:", len(traced))
print("generic channel keys present:", sorted(traced & {"when","val","interp","actions","ref","mute"}))
PY
```
Expected: the channel keys appear — they are the ones a literal search missed.
If `when`/`val`/`interp` are absent, the tracer is not reaching `Channel`.

- [ ] **Step 4: Commit**

```bash
git add tools/trace_fields.py
git commit -m "Trace which JSON keys the exporters actually read

Replaces the string-literal estimate, which over-counted keys named only in
comments and under-counted the channel keys consumed through variables. Wraps
every dict in the parsed tree and runs both exporters over all 76 documents; a
key never recorded is provably unread."
```

---

## Task 8: Disposition registry, `check-coverage`, and the real baseline

**Files:**
- Modify: `schema/channel.schema.json`, `schema/style.schema.json`,
  `schema/mesh.schema.json`, `schema/skeleton.schema.json`,
  `schema/layer.schema.json`, `schema/project.schema.json`
- Create: `tools/check_field_coverage.py`
- Modify: `Makefile`, `schema/README.md`
- Modify: this plan's Progress table

**Interfaces:**
- Consumes: `out/traced_keys.json` from Task 7.
- Produces: `make check-coverage`, printing the coverage figure and a per-area
  Markdown table, and failing on either rule in the spec § 4.4. Every M1–M3 task
  is scored by it.

- [ ] **Step 1: Add the annotation to a handful of properties by hand**

Pick five properties already known to be modelled — `smoothness` in
`mesh.schema.json`, `parent_bone` and `masking` in `layer.schema.json`,
`fixed_angle` in `skeleton.schema.json`, `im` in `channel.schema.json` — and add
beside each `description`:

```json
      "x-moho-disposition": "MODELLED",
      "x-moho-evidence": "moho2svg.py BezierReconstructor; 209 reference handles, median ratio 1.0000"
```

Then confirm validation still works, because JSON Schema must ignore the
unknown keyword:

Run: `python3 moho2lottie.py moho/Bandit.mohoproj --out out/lottie/Bandit.json --validate --frame 25`
Expected: the same output as before, no schema error.

- [ ] **Step 2: Write the checker**

```python
#!/usr/bin/env python3
"""Score field coverage from the schema registry and the runtime trace.

Coverage = (MODELLED + EDITABLE) / <content keys> and must reach 95%. See
docs/superpowers/specs/2026-08-18-moho-field-coverage-design.md for the four
dispositions and why DESCRIPTION keys are excluded from the denominator but
still required to survive a round-trip.

Two rules fail closed, so the figure cannot rise by omission or by assertion:
  1. a corpus key with no registry entry fails -- a key cannot be forgotten;
  2. a key declared MODELLED that the trace never observed fails -- a key
     cannot be claimed.
"""

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VALID = {"MODELLED", "EDITABLE", "PRESERVE", "UNKNOWN"}
COUNTED = {"MODELLED", "EDITABLE"}

# Keys excluded from the denominator: editor view state, onion-skin overlay,
# document identity, editor selection, and foreign script blobs. The reasons
# are recorded in the spec section 3; the patterns are the machine-readable
# form of that table. `random_num` is NOT here: it seeds brush jitter, so it
# changes the rendered stroke.
DESCRIPTION_PATTERNS = [
    r"^documentviewstate$", r"^DocState_", r"^onions_",
    r"^(mime_type|version|major_version|rev_version|doc_uuid)$",
    r"^(created_date|modified_date|comment|thumbnail)$",
    r"^(what|save_time|layerwnd_searchcontext)$",
    r"^(expanded|selected|shown_in_timeline|label_col|shy|hidden)$",
    r"^(ignored_by_layer_picker|previewAlignment|modification_date)$",
    r"^(layer_user_tags|layer_user_comments|consolidated_channels)$",
    r"^(bone_label_showing|bone_tags|prev_selected)$",
    r"^g_1\d+$", r"^(NewLayerScript|LM_GrandpaBones)$", r"_sec$",
]


def is_description(key):
    return any(re.search(p, key) for p in DESCRIPTION_PATTERNS)


def load_registry():
    """Return {key: (disposition, evidence)} from every schema file."""
    reg = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "schema", "*.schema.json"))):
        doc = json.load(open(path))

        def walk(node):
            if isinstance(node, dict):
                props = node.get("properties")
                if isinstance(props, dict):
                    for name, sub in props.items():
                        if isinstance(sub, dict) and "x-moho-disposition" in sub:
                            reg[name] = (sub["x-moho-disposition"],
                                         sub.get("x-moho-evidence", ""))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(doc)
    return reg


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--census", default=os.path.join(ROOT, "out", "census_keys.json"),
                    help="JSON list of every corpus key; produced by --census-build")
    ap.add_argument("--trace", default=os.path.join(ROOT, "out", "traced_keys.json"))
    ap.add_argument("--census-build", action="store_true",
                    help="walk moho/ and write the census file, then exit")
    args = ap.parse_args()

    if args.census_build:
        sys.path.insert(0, ROOT)
        import mohoedit
        keys = set()

        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    keys.add(k)
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        n = 0
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "moho")):
            for fn in sorted(filenames):
                if fn.endswith((".mohoproj", ".animeproj", ".moho")):
                    walk(mohoedit.read_document(os.path.join(dirpath, fn))[0])
                    n += 1
        os.makedirs(os.path.dirname(args.census), exist_ok=True)
        json.dump({"keys": sorted(keys), "documents": n}, open(args.census, "w"), indent=1)
        print("census: %d documents, %d distinct keys" % (n, len(keys)))
        return 0

    census = set(json.load(open(args.census))["keys"])
    traced = set(json.load(open(args.trace))["keys"])
    registry = load_registry()

    failures = []
    for key in sorted(census):
        if key not in registry:
            failures.append("unregistered key: %s" % key)
        elif registry[key][0] not in VALID:
            failures.append("bad disposition %r on %s" % (registry[key][0], key))
        elif registry[key][0] == "MODELLED":
            if key not in traced:
                failures.append("declared MODELLED but never read: %s" % key)
            elif not registry[key][1]:
                failures.append("declared MODELLED with no evidence: %s" % key)

    content = {k for k in census if not is_description(k)}
    covered = {k for k in content if registry.get(k, ("", ""))[0] in COUNTED}
    pct = 100.0 * len(covered) / len(content) if content else 0.0

    print("corpus keys        %d" % len(census))
    print("  description      %d (excluded)" % (len(census) - len(content)))
    print("  content          %d (the denominator)" % len(content))
    print("covered            %d = %.1f%%   target 95.0%%" % (len(covered), pct))
    print("registry failures  %d" % len(failures))
    for line in failures[:40]:
        print("   FAIL %s" % line)
    if len(failures) > 40:
        print("   ... %d more" % (len(failures) - 40))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Build the census and run the checker**

Run:
```bash
python3 tools/check_field_coverage.py --census-build
python3 tools/trace_fields.py
python3 tools/check_field_coverage.py
```
Expected: `census: 76 documents, 547 distinct keys`, then a large
`registry failures` count — almost every key is unregistered. That failure is
correct: rule 1 is doing its job.

- [ ] **Step 4: Annotate every key the trace observed**

For each key in `out/traced_keys.json` that is not `DESCRIPTION`, add
`x-moho-disposition: "MODELLED"` and a one-line `x-moho-evidence` pointing at
the code or document section that establishes it. For `DESCRIPTION` keys add
`"PRESERVE"`. For everything else add `"UNKNOWN"` with
`x-moho-unknown-reason: "not yet investigated"`. Extend the schema to the 24
keys it does not yet declare, including the 11 found only in archives:
`audio_path`, `audio_level`, `audio_fileref`, `audio_jump`, `audio_text`,
`spatial_positioning`, `image_cropping_min`, `image_cropping_max`,
`audio_file_sec`, `image_sec`, `images`.

- [ ] **Step 5: Run the checker and read the real baseline**

Run: `python3 tools/check_field_coverage.py`
Expected: `registry failures 0`, and a coverage percentage. **Record that
number.** It is the first measured figure in this effort and it supersedes
35.5%.

- [ ] **Step 6: Recompute this plan's Progress table**

Using the measured denominator and baseline, recalculate every `Coverage after`
cell for M1.1 onward from the per-area key counts, and add a line under the
Progress table stating the measured baseline, the date, and the command that
produced it. If the baseline is materially lower than 35.5%, note in the table
whether M1 needs splitting.

- [ ] **Step 7: Wire the target and commit**

```makefile
# Field coverage against the disposition registry embedded in schema/.
# Rebuild the inputs first: the census walks moho/, the trace runs both
# exporters over it. See docs/moho-field-coverage-plan.md Task 8.
check-coverage:
	$(PYTHON) tools/check_field_coverage.py --census-build
	$(PYTHON) tools/trace_fields.py
	$(PYTHON) tools/check_field_coverage.py
```

```bash
git add schema/ tools/check_field_coverage.py Makefile docs/moho-field-coverage-plan.md
git commit -m "Score field coverage from a registry embedded in the schema

Every corpus key now carries an x-moho-disposition in schema/, and
check-coverage joins it against the runtime trace. Two rules fail closed: an
unregistered key fails, and a key declared MODELLED that the trace never
observed fails, so the figure can rise neither by omission nor by assertion.
Records the first measured baseline, replacing the string-literal estimate."
```

---

## Task 9: Integrity checker, detect-only

**Files:**
- Modify: `mohoedit.py`
- Create: `tools/check_integrity.py`
- Modify: `Makefile`

**Interfaces:**
- Produces: `mohoedit.check_integrity(raw) -> list[str]`, one message per
  violation, empty when clean. Later structural-edit work calls it after every
  mutation.

- [ ] **Step 1: Write the failing check**

```python
#!/usr/bin/env python3
"""Every corpus document passes the reference-integrity checks.

A Moho mesh is held together by positional indices with no allocator and no
generation counter: shape.edges.curve indexes mesh.curves, curve.points[].point
indexes mesh.points, mesh.points[].parent indexes the ancestor skeleton's
bones, and bone.parent indexes its own skeleton. Deleting one entry silently
invalidates every reference above it. This asserts the 76 documents we hold are
internally consistent, which makes the checker trustworthy as a gate on edits.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mohoedit  # noqa: E402


def iter_paths():
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "moho")):
        for fn in sorted(filenames):
            if fn.endswith((".mohoproj", ".animeproj", ".moho")):
                yield os.path.join(dirpath, fn)


def main():
    bad = 0
    for path in sorted(iter_paths()):
        rel = os.path.relpath(path, ROOT)
        raw, _ = mohoedit.read_document(path)
        problems = mohoedit.check_integrity(raw)
        if problems:
            print("FAIL %-52s %d problems, first: %s" % (rel, len(problems), problems[0]))
            bad += 1
    print("\n%s: %d documents with problems" % ("FAIL" if bad else "OK", bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 tools/check_integrity.py`
Expected: `AttributeError: module 'mohoedit' has no attribute 'check_integrity'`

- [ ] **Step 3: Implement the checker**

Append to `mohoedit.py`:

```python
def check_integrity(raw: dict) -> typing.List[str]:
    """Report every broken cross-reference in a document, one message each.

    A Moho mesh is held together almost entirely by POSITIONAL INDICES, and the
    format has exactly one allocator (`mesh.next_shape_id`, for shape ids only)
    and no generation counter anywhere. Removing one entry from `mesh.points`
    invalidates every `curve.points[].point` above it and every
    `mesh.groups[].points` entry, with nothing to detect the staleness -- so an
    editor that renumbers wrongly produces a file that still loads and is
    quietly wrong. This function is the gate against that.

    Names are the other reference class, and they fail even more quietly: a
    renamed switch child leaves `switch_keys` pointing at nothing and Moho
    silently falls back to the first child, while a renamed bone silently
    de-activates its Smart Bone.
    """
    problems: typing.List[str] = []
    uuids = set()

    def collect_uuids(node):
        if isinstance(node, dict):
            if "uuid" in node and "type" in node:
                uuids.add(node["uuid"])
            for value in node.values():
                collect_uuids(value)
        elif isinstance(node, list):
            for value in node:
                collect_uuids(value)

    collect_uuids(raw)

    def check_mesh(mesh, where):
        points, curves = mesh.get("points", []), mesh.get("curves", [])
        for ci, curve in enumerate(curves):
            for pi, cp in enumerate(curve.get("points", [])):
                index = cp.get("point")
                if not isinstance(index, int) or not 0 <= index < len(points):
                    problems.append("%s curves[%d].points[%d].point = %r, valid 0..%d"
                                    % (where, ci, pi, index, len(points) - 1))
        for si, shape in enumerate(mesh.get("shapes", [])):
            edges = shape.get("edges", {})
            for ei, ci in enumerate(edges.get("curve", [])):
                if not 0 <= ci < len(curves):
                    problems.append("%s shapes[%d].edges.curve[%d] = %r, valid 0..%d"
                                    % (where, si, ei, ci, len(curves) - 1))
                    continue
                curve = curves[ci]
                n = len(curve.get("points", []))
                limit = n if curve.get("closed") else max(0, n - 1)
                seg = edges.get("segment", [])[ei] if ei < len(edges.get("segment", [])) else None
                if seg is None or not 0 <= seg < limit:
                    problems.append("%s shapes[%d].edges.segment[%d] = %r, valid 0..%d"
                                    % (where, si, ei, seg, limit - 1))
        for gi, group in enumerate(mesh.get("groups", [])):
            for index in group.get("points", []):
                if not 0 <= index < len(points):
                    problems.append("%s groups[%d] point %r, valid 0..%d"
                                    % (where, gi, index, len(points) - 1))
        return points

    def check_layer(layer, where, bones):
        """`bones` is the nearest ancestor BoneLayer's bone list, or []."""
        own = layer.get("skeleton", {}).get("bones")
        if isinstance(own, list) and own:
            for bi, bone in enumerate(own):
                parent = bone.get("parent", -1)
                if parent != -1 and not 0 <= parent < len(own):
                    problems.append("%s skeleton.bones[%d].parent = %r, valid -1 or 0..%d"
                                    % (where, bi, parent, len(own) - 1))
            bones = own

        parent_bone = layer.get("parent_bone", -1)
        if parent_bone not in (-1, -2, -3) and not 0 <= parent_bone < len(bones):
            problems.append("%s parent_bone = %r, valid -1/-2/-3 or 0..%d"
                            % (where, parent_bone, len(bones) - 1))

        subset = layer.get("flexi_bone_subset", "")
        for token in [t for t in str(subset).split("|") if t.strip()]:
            if not token.isdigit() or not 0 <= int(token) < len(bones):
                problems.append("%s flexi_bone_subset entry %r, valid 0..%d"
                                % (where, token, len(bones) - 1))

        mesh = layer.get("mesh")
        if isinstance(mesh, dict):
            points = check_mesh(mesh, where + " mesh")
            for pi, point in enumerate(points):
                bound = point.get("parent", -1)
                if bound not in (-1, -2) and not 0 <= bound < len(bones):
                    problems.append("%s mesh.points[%d].parent = %r, valid -1/-2 or 0..%d"
                                    % (where, pi, bound, len(bones) - 1))

        for field in ("target_layer_uuid", "follow_layer_uuid", "distortion_layer_uuid"):
            ref = layer.get(field)
            if ref and ref not in uuids:
                problems.append("%s %s = %r names no layer in this document"
                                % (where, field, ref))

        children = layer.get("layers")
        if isinstance(children, list):
            names = {c.get("name") for c in children if isinstance(c, dict)}
            keys = layer.get("switch_keys")
            if isinstance(keys, dict):
                for value in keys.get("val", []):
                    if value and value not in names:
                        problems.append("%s switch_keys value %r names no child (has %s)"
                                        % (where, value, sorted(n for n in names if n)))
            for ci, child in enumerate(children):
                if isinstance(child, dict):
                    check_layer(child, "%s/%s" % (where, child.get("name", "[%d]" % ci)), bones)

    for index, layer in enumerate(raw.get("layers", [])):
        if isinstance(layer, dict):
            check_layer(layer, layer.get("name", "[%d]" % index), [])
    return problems
```

The channel-level `actions[].name` coupling — every pose name must exist in some
layer's `actions` registry — is deliberately **left out of this task**. It needs
a full-tree name registry collected before the walk, and the walk above is
already the largest function in the module. Add it in M2.1, where Smart Bone
fields are being decoded anyway, and record it as a step there.

- [ ] **Step 4: Run the check and confirm it passes**

Run: `python3 tools/check_integrity.py`
Expected: `OK: 0 documents with problems`.

If a real corpus document reports a violation, that is a **finding, not a bug in
the checker** — investigate before relaxing any rule, and record the outcome in
`docs/moho-project-file-format.md`. `switch_keys` naming a renamed child and
`parent_bone == -3` are the two most likely genuine hits.

- [ ] **Step 5: Prove the checker catches a real break**

```bash
python3 - <<'PY'
import mohoedit
raw, c = mohoedit.read_document("moho/Bandit.mohoproj")
def first_mesh(n):
    if isinstance(n, dict):
        if isinstance(n.get("curves"), list) and n.get("shapes"):
            return n
        for v in n.values():
            m = first_mesh(v)
            if m: return m
    elif isinstance(n, list):
        for v in n:
            m = first_mesh(v)
            if m: return m
mesh = first_mesh(raw)
mesh["curves"].pop()                      # invalidate every edge above it
print(mohoedit.check_integrity(raw)[:3])
PY
```
Expected: at least one message about an out-of-range `shape.edges.curve`.

- [ ] **Step 6: Wire it in and commit**

```makefile
check-integrity:
	$(PYTHON) tools/check_integrity.py
```

```bash
git add mohoedit.py tools/check_integrity.py Makefile
git commit -m "Check reference integrity across a Moho document

A mesh is held together by positional indices with no allocator and no
generation counter, so deleting one point or curve silently invalidates every
reference above it. check_integrity reports violations of the index-based and
name-based reference classes; it does not renumber anything yet. All 76 corpus
documents pass, and it is confirmed to catch a deliberately removed curve."
```

---

## Task 10: Field probe harness

**Files:**
- Create: `tools/probe_field.py`
- Create: `docs/moho-field-probes.md`

**Interfaces:**
- Consumes: `mohoedit.read_document`, `mohoedit.write_document`.
- Produces: `python3 tools/probe_field.py --key NAME --value JSON
  [--precondition KEY=JSON]...`, appending one record per probe to
  `docs/moho-field-probes.md`. Every M2 and M3 task runs this.

- [ ] **Step 1: Write the harness**

```python
#!/usr/bin/env python3
"""Decide whether one JSON field affects what Moho renders.

The method is this repository's established one -- render the same document
twice with a single field changed, so every unrelated modelling error cancels
out. It decoded fixed_angle, mask_expansion, stroke exposure and both masking
enums. What is new here is only that it is driven from the command line, so a
sweep of a few hundred fields is a loop rather than a few hundred
investigations.

Outcome, recorded either way:
  pixels differ -> the field affects rendering. EDITABLE now, and stamped
                   x-moho-render: pending for Phase 2.
  pixels equal  -> the field is inert for rendering. EDITABLE and finished.

A negative result is only as good as its preconditions: physics_torque does
nothing while enable_physics is off, and 3d_shading_density does nothing while
3d_mode is 0. Pass those with --precondition, and the record keeps them, so a
result can be re-read later knowing what it ran under.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mohoedit  # noqa: E402

MOHO = "/Applications/Moho.app/Contents/MacOS/Moho"
RECORD = os.path.join(ROOT, "docs", "moho-field-probes.md")


def set_every(node, key, value, count=None):
    """Set `key` to `value` on every dict that already has it. Returns the count."""
    if count is None:
        count = [0]
    if isinstance(node, dict):
        if key in node:
            node[key] = value
            count[0] += 1
        for sub in node.values():
            set_every(sub, key, value, count)
    elif isinstance(node, list):
        for sub in node:
            set_every(sub, key, value, count)
    return count[0]


def render(path, frame, out):
    subprocess.run([MOHO, "-r", path, "-f", "PNG",
                    "-start", str(frame), "-end", str(frame), "-o", out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stem, ext = os.path.splitext(out)
    produced = "%s_%05d%s" % (stem, frame, ext)
    target = produced if os.path.exists(produced) else out
    with open(target, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest(), target


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", required=True, help="new value as JSON, e.g. 1 or true or '\"x\"'")
    ap.add_argument("--document", required=True)
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--precondition", action="append", default=[],
                    metavar="KEY=JSON", help="set first; repeatable")
    args = ap.parse_args()

    if not os.path.exists(MOHO):
        print("SKIP: Moho is not installed at %s" % MOHO)
        return 0
    outdir = os.path.join(ROOT, "out", "probe")
    os.makedirs(outdir, exist_ok=True)
    src = os.path.join(ROOT, args.document)

    pre = [p.split("=", 1) for p in args.precondition]

    raw, container = mohoedit.read_document(src)
    pre_counts = {k: set_every(raw, k, json.loads(v)) for k, v in pre}
    base = os.path.join(outdir, "base" + os.path.splitext(src)[1])
    mohoedit.write_document(base, raw, container)

    raw2, container2 = mohoedit.read_document(src)
    for k, v in pre:
        set_every(raw2, k, json.loads(v))
    touched = set_every(raw2, args.key, json.loads(args.value))
    if touched == 0:
        print("FAIL: %s is not present in %s - pick another document"
              % (args.key, args.document))
        return 1
    var = os.path.join(outdir, "var" + os.path.splitext(src)[1])
    mohoedit.write_document(var, raw2, container2)

    base_hash, _ = render(base, args.frame, os.path.join(outdir, "base.png"))
    var_hash, _ = render(var, args.frame, os.path.join(outdir, "var.png"))
    affects = base_hash != var_hash

    line = ("| `%s` | `%s` | %s | %d | %s | %s |\n"
            % (args.key, args.value, os.path.basename(args.document), args.frame,
               ", ".join("`%s=%s` x%d" % (k, v, pre_counts[k]) for k, v in pre) or "none",
               "**AFFECTS RENDER**" if affects else "inert"))
    if not os.path.exists(RECORD):
        with open(RECORD, "w") as fh:
            fh.write("# Moho field probes\n\n"
                     "One row per field, produced by `tools/probe_field.py`. A row says whether\n"
                     "changing that field alone changed what Moho itself rendered. See\n"
                     "`docs/superpowers/specs/2026-08-18-moho-field-coverage-design.md` section 6.\n\n"
                     "| Field | Value tried | Document | Frame | Preconditions | Result |\n"
                     "|---|---|---|---|---|---|\n")
    with open(RECORD, "a") as fh:
        fh.write(line)
    print("%s: %s (%d sites changed)" % (args.key,
                                         "AFFECTS RENDER" if affects else "inert", touched))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Prove the harness on a field known to affect rendering**

Run:
```bash
python3 tools/probe_field.py --key line_width --value 0.05 \
        --document moho/Bandit.mohoproj --frame 25
```
Expected: `line_width: AFFECTS RENDER`. A harness that cannot detect a stroke
width change detects nothing.

- [ ] **Step 3: Prove it on a field known to be inert**

Run:
```bash
python3 tools/probe_field.py --key DocState_gridSize --value 40 \
        --document moho/Bandit.mohoproj --frame 25
```
Expected: `DocState_gridSize: inert`. Both branches must be observed working
before the sweep relies on them.

- [ ] **Step 4: Prove a precondition works**

Run:
```bash
python3 tools/probe_field.py --key 3d_shading_density --value 90 \
        --document moho/Bandit.mohoproj --frame 25
python3 tools/probe_field.py --key 3d_shading_density --value 90 \
        --precondition 3d_mode=1 --document moho/Bandit.mohoproj --frame 25
```
Expected: `inert` without the precondition. With `3d_mode=1` the result may be
either — record what happens. If `3d_mode=1` alone does not change the render,
that is itself a finding: note it in `docs/moho-field-probes.md` and treat
`3d_mode` as needing more investigation in M3.1.

- [ ] **Step 5: Commit**

```bash
git add tools/probe_field.py docs/moho-field-probes.md
git commit -m "Add a one-field probe harness driven from the command line

Renders the same document twice with a single field changed, so unrelated
modelling error cancels out - the method that decoded fixed_angle,
mask_expansion and both masking enums. Supports preconditions, because a field
like physics_torque is inert until enable_physics is on, and records them with
each result so a negative can be re-read later. Confirmed to report
AFFECTS RENDER for line_width and inert for DocState_gridSize."
```

---

## The sweep recipe — M1, M2 and M3

Every remaining milestone applies the same recipe to one group of keys. The
group memberships are in the spec § 7; the exact key lists come from
`make check-coverage`, which is authoritative once Task 8 has landed.

Per-key steps are deliberately **not** written out here. A decode task's steps
depend on what the probe finds, so writing them now would mean writing
placeholders — which this plan forbids. The recipe below is complete: it names
every command and every acceptance condition.

### M1 — adopt the template keys

These 144 keys are already emitted by `svg2moho.py` / `lottie2moho.py` at
real-file-correct values, so their **shape** is settled and only their status is
missing.

- [ ] For each key in the milestone's group: find where the writer emits it,
      and record the value it uses.
- [ ] Probe it (`tools/probe_field.py`) to learn whether it affects rendering.
- [ ] Add a typed accessor on the owning `mohoedit` object, or confirm the
      existing `_raw` access is sufficient and record which.
- [ ] Set `x-moho-disposition` to `EDITABLE`, with `x-moho-evidence` naming the
      probe row, and `x-moho-render: pending` when the probe said it affects
      rendering.
- [ ] Document the field's meaning in `docs/moho-project-file-format.md`.
- [ ] Run `make check-coverage check-export check-lottie check-reference check-roundtrip check-integrity`.
- [ ] Commit, and flip the Progress row with the coverage figure the checker
      printed — not the figure this plan predicted.

### M2 — decode the observable keys

97 keys: 63 whose value varies across the corpus, 34 whose container shape is
already understood (Channel, Color, FileRef) and which need only a semantic
label.

Same as M1, with one addition before the probe:

- [ ] Tabulate every distinct value the corpus holds for the key, and which
      documents hold each. A key with two values across 72 documents is an enum
      or a flag; the distribution usually names it before any render is run.
- [ ] For an enum, probe **each** value, not just one. `binding_mode` has two
      observed values and one of them appears on a single skeleton — probing only
      the common one proves nothing about the other.

### M3 — synthesise the constant-valued keys

39 keys hold one value in all 76 documents, so nothing can be learned by
observation. Same as M2, with:

- [ ] Choose the alternative value from Moho's own scripting header
      (`pkg_moho.lua_pkg`) or the manual, never by guessing. For an enum, use a
      declared constant; for a bool, the other bool; for a float, a value large
      enough that antialiasing cannot explain the difference.
- [ ] Identify the precondition and pass it with `--precondition`. **M3.1's
      whole efficiency is that `3d_mode=1` unlocks ten keys at once, and M3.2's
      that `enable_physics` unlocks five.** Establish the precondition works —
      i.e. that it alone changes the render — before probing anything behind it.
- [ ] If no plausible value can be established, set the disposition to
      `UNKNOWN` **with `x-moho-unknown-reason` recording what was tried and why
      it failed**. The residual budget is 22 keys; spend it here, deliberately,
      and never on a key that was simply not attempted.

### Definition of done for Phase 1

- [ ] `make check-coverage` reports **≥ 95.0%** with **0 registry failures**.
- [ ] `make check-export check-lottie check-reference check-roundtrip check-integrity` all pass.
- [ ] Every `UNKNOWN` key carries a reason, and the count is within the residual
      budget the checker prints.
- [ ] `docs/moho-project-file-format.md` describes every newly decoded field.
- [ ] The Phase 2 backlog is generated from the registry's `x-moho-render:
      pending` entries, not written by hand.

---

## Open questions

Recorded here rather than guessed at, in the style of
`moho-to-lottie-plan.md`'s own open-questions table.

| # | Question | Status |
|---|---|---|
| Q1 | The 16 `g_<number>` flags appear in 49 of 76 documents but are absent from Moho's Lua header, from all of `Moho.app/Contents/Resources/Support/`, and from all 197 scripts in `mohoscripts/`. Only a GUI twin-save can decode them, which no headless method can perform. They sit in DESCRIPTION so they cost the metric nothing — but their origin is genuinely unexplained. | OPEN |
| Q2 | `layercomps` and `action_refs` are empty in all 76 documents and `switch_data` is `""` in all 45 that carry it. Their element grammar cannot be observed or synthesised. Manual Appendix F documents `layercomps` as `{name, uuid, layer_ids[]}`; the other two are undocumented. | OPEN |
| Q3 | `Mesh3DLayer` has no instance in the corpus and no `type` string in Appendix F's list, though the old `.anme` format numbered a Poser/3D layer 8. Whether a Moho 14 document can contain one is unknown. | OPEN |
| Q4 | Does `make check-reference` need extending? It fences three documents. Any field decoded in an area those three do not exercise is verified by its own probe alone, with no outside-authority gate. | OPEN |
| Q9 | **Rule 5 does not cover `patternProperties` collisions, and a future one would pass silently rather than warn.** The final fix wave added rule 5, which fails the build when one flat key name carries conflicting dispositions across its occurrences (the defect that made `b` score uncovered). But `load_registry` populates its `occurrences` map only from `properties` blocks, so a future `patternProperties`-vs-`patternProperties` or pattern-vs-exact conflict on the same content key is invisible to it. The scoping is documented as deliberate — no such collision exists today, and both pattern families (`DocState_*`, `g_<number>`) are 100% `PRESERVE` — but the failure mode for a future violation is a silent pass, not a warning. Adjudicated as parked rather than fixed: there is no second fix wave, and nothing in M1–M3 is scheduled to add a pattern family. Close it if a milestone ever annotates one. | OPEN |
| Q8 | **M3.1's efficiency premise is measurably false, and this changes the plan's arithmetic.** The plan claims "one `3d_mode = 1` precondition unlocks all ten `3d_*` keys". Task 10's probe measured it on `Bandit.mohoproj` frame 25 and I re-ran it independently: `3d_mode = 1` alone **does** change the render (21 sites, AFFECTS RENDER), so the precondition is genuinely live — but `3d_shading_density = 90` behind that same precondition is still **inert**. The precondition works and does not unlock the target key. So the ten `3d_*` keys need individual, possibly **compound** preconditions (`3d_shading_mode`, a non-zero `3d_thickness`, or a mesh that actually extrudes), not one shared switch. Consequence for the target: M3 must supply 31 of the 39 constant-valued keys, and 10 of those 31 were budgeted as this cheap group. If they resist, the 8-key residual cannot absorb a 10-key loss, and the 95% target would miss. **M3.1 must therefore begin by finding a working compound precondition for the `3d_*` family and reporting whether one exists, before any of its ten keys is scheduled.** | OPEN |
| Q7 | **`mesh.points[].parent` and `flexi_bone_subset` are clean on 75 of 76 documents.** Task 9 measured all four excluded reference classes with the naive rule: `switch_keys` 1167 violations / 9 documents, `parent_bone` 73 / 24, but `mesh.points[].parent` only **17 / 1** and `flexi_bone_subset` only **1 / 1** — and both of those single documents are the same one, `ReparentBone.animeproj`. That is a lead, not noise: that document is this corpus's fixture for the **Reparent Bone tool**, and `anim_parent` (an animated bone-parent index) is exactly the feature that would move a bone's index space partway through a document. So those two rules may well be validatable with `ReparentBone.animeproj` as a documented exception, unlike `parent_bone`, whose 24-document spread means the model itself is wrong. Worth attacking first in M2.1. | OPEN |
| Q6 | **Saving a document to a different directory silently breaks its assets.** Found during Task 4: `mohoedit.write_document` writes wherever it is told, but an `ImageLayer`'s `image_fileref` with `relativeTo` other than `"Absolute"` resolves against the document's own location, so a round-trip copy written to `out/` rendered as broken-image placeholders until it was written beside the original instead. Measured: **12 of the 76 documents carry at least one non-absolute fileref.** Nothing warns. An editing tool that offers "save as" therefore has a data-integrity hazard, and the fix is a design decision — warn, rewrite the filerefs, or copy the assets — not a bug fix. `Container` would need to carry the source path for `write_document` to detect it. | OPEN |
| Q5 | `make svg-all` and `lottie-all` still cover only the 46 top-level documents, so no `.moho` archive and no subdirectory document has an aggregate build target. Task 3 was going to fix this by making `PROJECT_STEMS` recursive; that was dropped during execution because six pattern rules (`out/svg/{ori,med,fast,raster}/%.svg`, `out/lottie/%.json`, `format/moho/%`) take their prerequisite from `$$(wildcard moho/$$*.animeproj moho/$$*.mohoproj)` — a stem like `Snow_wars/06` matches no prerequisite, needs a nested output directory nothing creates, and reaches a recipe that `ls`es only the two bare extensions. Closing it means extending all six recipes, not one variable. Nothing in this plan depends on it: the three checks that must see all 76 documents walk `moho/` themselves and never read `PROJECT_STEMS`. | OPEN |
