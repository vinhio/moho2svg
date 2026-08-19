#!/usr/bin/env python3
"""Score field coverage from the schema registry and the runtime trace.

Coverage = (MODELLED + EDITABLE) / <content keys> and must reach 95%. See
docs/superpowers/specs/2026-08-18-moho-field-coverage-design.md for the four
dispositions and why DESCRIPTION keys are excluded from the denominator but
still required to survive a round-trip.

Five rules fail closed, so the figure cannot rise by omission, by assertion,
by an unrepresentative measurement, by a self-contradictory claim, or by a
silently shadowed disagreement between two occurrences of the same name:

  1. a corpus key with no registry entry fails -- a key cannot be forgotten;
  2. a key declared MODELLED that the trace never observed fails -- a key
     cannot be claimed;
  3. a trace taken without Pillow/psd-tools/pyclipper importable fails --
     that environment cannot reach the ImageLayer/PSD or combo_mode==3
     branches, so it would report keys as "never observed" that a full
     environment's trace correctly finds, and the tempting (wrong) fix is to
     water down the registry entry that rule 2 then flags. See
     tools/trace_fields.py's own module docstring for the one key
     (`image_fileref`) this actually changes.
  4. a key declared MODELLED whose own `description` asserts it is not read
     / never read / not consumed / not used fails -- caught on `channel.b`
     (the Bezier-handle array), whose evidence pointed at `Color.from_raw`
     reading an UNRELATED `b` field (the blue channel) that merely shares
     the name, while `b`'s own description said "Not read by moho2svg.py."
     Rule 2 alone cannot catch this class: the NAME `b` genuinely was
     traced, just not for this field. This is the general form of the
     flat-by-name registry's one known blind spot (see `load_registry`'s own
     docstring) -- a name reused for two different fields can borrow a true
     claim about one of them for the other. A key legitimately in that
     situation (confirmed by hand, not guessed) is not disposition-flipped
     to escape the rule -- that would make the flat registry order-dependent
     for that key's score -- but is recorded with `x-moho-contradiction-waived`
     carrying the specific collision, so the failure count stays a true
     count of undiagnosed contradictions rather than a free-text escape
     hatch or a rule-wide flag. See `CONTRADICTION_PATTERNS` for exactly
     which phrasing trips this -- scoped to phrases asserting NO consumption
     at all, not to the many accurate "read into the model but never applied
     to rendering" descriptions elsewhere in this schema
     (distortion_layer_uuid, timing_offset, Mesh.shape_order, ...), which are
     not a contradiction of MODELLED at all -- MODELLED's bar for this
     seeding pass is "the trace observed a read," not "the value changes
     rendered output."

     Two annotated-but-INERT examples, kept in the schema for a human reader
     but never actually evaluated by this checker: `mesh.MeshPoint.curves`
     (its own array is never read; the NAME `curves` is, via the unrelated
     top-level `Mesh.curves`) and `layer.GroupLayer.gravity` (its own object
     is never reached -- `Layer.physics_dynamic` returns early whenever
     `self.skeleton is None`, always true for a `GroupLayer` -- while
     `BoneLayer.gravity`, the same key name, genuinely is read).
     `load_registry` resolves same-name conflicts first-occurrence-wins, and
     both `Mesh.curves` and `BoneLayer.gravity` are declared EARLIER in
     their file than the collision they shadow, so the checker's registry
     never loads the MeshPoint/GroupLayer occurrence at all -- their
     `x-moho-contradiction-waived` annotations are documentation for the
     next reader of the raw schema, not something this script's rule 4 ever
     exercises today. Verified the waiver mechanism ITSELF fires correctly
     on a key the checker genuinely does load (Task 8 fix round 3's
     report records the two observed outputs; the test edit was reverted,
     not left in the schema, since manufacturing a permanent fake collision
     just to keep a live example would be exactly the "escape hatch nobody
     watches" failure this note exists to rule out).
  5. a key name whose registry occurrences carry CONFLICTING dispositions
     (not merely a contradictory description on one of them -- rule 4's
     job) fails, unless the divergence carries an explicit
     `x-moho-registry-conflict-waived` annotation -- caught, again, on `b`:
     fixing round 1's `channel.b` mistake (above) by re-annotating
     `InterpEntry.b` as the UNKNOWN it genuinely is left it declared FIRST
     in `channel.schema.json`, still shadowing the genuinely-MODELLED
     `ColorValue.b` (and a third, also-MODELLED `b` in `layer.schema.json`)
     under first-occurrence-wins -- so the flat key `b` flipped from a
     false MODELLED claim to a false UNCOVERED one, understating coverage
     by exactly the one key rule 4's own fix had just corrected. Same root
     cause as rule 4 (the flat-by-name registry has no way to tell two
     unrelated fields called `b` apart), opposite failure direction, and
     -- this is the point the instance is standing in for -- NEITHER rule
     1-4 would ever have noticed: rule 2 only inspects the WINNING entry
     per key, rule 4 only inspects a MODELLED entry's own text. M1-M3 will
     hand-refine hundreds of properties, which is exactly the situation
     that turns "occurrences of a name usually agree" into "usually,
     until one is deliberately re-annotated" -- this rule exists so the
     next such flip fails the build instead of quietly changing the
     percentage.

     This is deliberately a FAIL, not a warning: `--require-target` is
     off during M1-M3 specifically so a real, expected shortfall does not
     train anyone to ignore red output, but a registry INTERNAL
     contradiction is a different kind of finding -- like rule 4, it means
     the annotations disagree with each other about a fact of the codebase
     (whether a name is read), which is always fixable in the moment
     (either the annotations are wrong, or the collision is real and gets
     a waiver) and never something to defer to a later phase. A loud
     warning is exactly the shape of thing this suite's own doctrine
     warns against: nothing enforces that anyone reads it, so a change
     that reintroduces a shadowed disposition would sail through the same
     way `b`'s did until this task looked for it by hand. See
     `find_disposition_conflicts` and `effective_disposition` for the
     mechanism: scoring now takes the most favourable (COUNTED) disposition
     across ALL of a name's occurrences rather than only the first, which
     is what actually fixes `b`'s coverage -- but only once this rule
     confirms a human looked at the specific divergence, recorded in
     `schema/channel.schema.json`'s `ColorValue.b` entry.

The five rules above govern whether the REGISTRY is trustworthy; they say
nothing about whether coverage has actually REACHED the 95% target -- this
script used to just print the percentage, so `make check-coverage` exited 0
at 32.5% with nobody able to point at a line that would fail once Phase 1 is
supposed to be done. `--require-target` (off by default, since M1-M3 have
not run yet and defaulting it on would fail every invocation for the whole
sweep) makes that assertion machine-checked instead of claimed. The bar
itself is `required_coverage_keys(content)`, a CEILING of `content * 0.95` --
not `round()`, which is how an earlier revision of this plan and its design
spec both stated the bar as 412 keys while 412/434 is actually 94.93%,
one key short of 95.00%.

The registry lives as `x-moho-disposition` (`MODELLED` / `EDITABLE` /
`PRESERVE` / `UNKNOWN`) annotations on individual property definitions across
schema/*.schema.json, generated in bulk by tools/gen_field_dispositions.py and
hand-refined for the handful of properties called out in
docs/moho-field-coverage-plan.md Task 8 Step 1. A property may live inside a
`patternProperties` entry (e.g. the `DocState_*`/`g_<number>` families) rather
than a plain `properties` entry -- `load_registry` resolves both, matching a
corpus key against a pattern's own regex when there is no exact name match,
which is what lets a whole key family be registered once instead of key by
key.
"""

import argparse
import glob
import json
import math
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

# The three optional dependencies that gate a real branch of the exporters
# (see tools/trace_fields.py's environment_fingerprint). Rule 3 checks all
# three were importable when the trace being scored was produced.
REQUIRED_TRACE_DEPS = ("pillow", "psd_tools", "pyclipper")

# Rule 4's trigger phrases: a description asserting the field is NOT
# consumed at all. Deliberately narrow -- matching on "applied" as well
# (which the flat-name collision this rule exists for could equally be
# phrased with) would flag dozens of accurate, intentional descriptions of
# real MODELLED fields that ARE read but do not change rendered output
# (distortion_layer_uuid, timing_offset, Mesh.shape_order, the whole
# constraint/IK/physics family on Bone -- see moho2svg.py's own module
# docstring, "read... but NOT applied when rendering"). MODELLED's bar for
# this seeding pass is "the trace observed a read" (see ruling 2 in
# docs/moho-field-coverage-plan.md Task 8), so "read but not applied" is not
# a contradiction of it; "not read at all" is.
CONTRADICTION_PATTERNS = [
    re.compile(r"\bnot\s+read\b", re.IGNORECASE),
    re.compile(r"\bnever\s+read\b", re.IGNORECASE),
    re.compile(r"\bnot\s+consumed\b", re.IGNORECASE),
    re.compile(r"\bnothing\s+reads\b", re.IGNORECASE),
    re.compile(r"\bnot\s+used\b", re.IGNORECASE),
]


def contradicts_modelled(description):
    """True when `description` asserts zero consumption (rule 4's trigger).

    See CONTRADICTION_PATTERNS for exactly what counts and why the net is
    deliberately narrower than "any negative-sounding word".
    """
    return isinstance(description, str) and any(p.search(description) for p in CONTRADICTION_PATTERNS)


def is_description(key):
    """A key is DESCRIPTION only for a documented, positive reason (spec §3)."""
    return any(re.search(p, key) for p in DESCRIPTION_PATTERNS)


def required_coverage_keys(content_count):
    """The smallest integer N with N / content_count >= 0.95 -- Phase 1's
    machine-checked completion bar (docs/moho-field-coverage-plan.md's
    "Definition of done").

    A CEILING, not `round()`. The plan and the design spec both originally
    stated the bar as 412 keys, from `round(434 * 0.95)` -- but
    412 / 434 = 94.93%, BELOW the 95.00% those documents claimed it meets.
    413 is the smallest key count that actually clears 95.00%
    (413 / 434 = 95.16%). Both documents were corrected 2026-08-19 (the
    residual budget moved from 22 to 21 keys accordingly); this function is
    what keeps the number from drifting the same way again if the corpus
    grows and `content_count` (the denominator) changes -- the bar is always
    RECOMPUTED from the live denominator, never hard-coded as 413.
    """
    if content_count <= 0:
        return 0
    return math.ceil(content_count * 0.95)


def load_registry():
    """Return (exact, patterns, occurrences) read from every schema file.

    `exact` is {key_name: Entry}. `patterns` is a list of
    (compiled_regex, Entry) drawn from every `patternProperties` block
    carrying an annotation -- needed because a whole key family
    (`DocState_zoom[0-3]`, `g_[0-9]+`) is registered once as a pattern rather
    than once per observed instance, and a corpus key that only matches by
    pattern must not be reported as unregistered (rule 1). `Entry` is
    `(disposition, evidence, area, description, waiver, conflict_waiver)`:
    `description` is that occurrence's own prose (rule 4 reads it); `waiver`
    is the value of `x-moho-contradiction-waived` when present, else `""`
    (rule 4's escape hatch, for a single occurrence whose own description
    contradicts its own disposition); `conflict_waiver` is
    `x-moho-registry-conflict-waived` (rule 5's escape hatch, for a NAME
    whose occurrences disagree with EACH OTHER -- see
    find_disposition_conflicts).

    Both `exact` and `patterns` are flat by KEY NAME, matching the trace's
    own flat key-name set (see trace_fields.py) -- the same field name
    declared in two `$defs` (e.g. `name` on both a Bone and a Style)
    collapses to one entry. This is a deliberate simplification:
    gen_field_dispositions.py always writes the SAME disposition/evidence
    text to every occurrence of a given name, so which occurrence "wins"
    here does not normally change the answer -- except when hand-refinement
    deliberately diverges two occurrences (exactly what M1-M3 will do),
    which is why both the exact map and the pattern list now resolve
    conflicts the SAME way: **first occurrence encountered wins** (files
    walked alphabetically, each file's own tree walked depth-first in
    declaration order), and a later occurrence of the same name is silently
    ignored rather than overwriting it. An earlier revision let the exact
    map be last-wins (plain dict assignment) while the pattern list was
    already first-wins (list-order iteration in `resolve`) -- harmless
    while every occurrence of a name carried identical text, but exactly the
    kind of order-dependent surprise that would bite the moment two
    occurrences disagree on purpose.
    `area` records the schema file the WINNING entry was found in, used only
    to group the printed per-area table -- it has no effect on scoring.

    `occurrences` is the third structure this function now returns:
    {key_name: [Entry, ...]}, EVERY exact-name occurrence in declaration
    order, not just the winner -- `exact`/`resolve()` still answer "which
    occurrence's evidence/description/area do we quote", but scoring
    ("is this key covered at all") needs to see every occurrence, which is
    what `effective_disposition` and `find_disposition_conflicts` (rule 5)
    both read this for. Deliberately scoped to exact-name properties only,
    not `patternProperties` families -- a pattern already names a whole key
    FAMILY on purpose (`DocState_*`, `g_<n>`), so two patterns matching the
    same literal key would be a schema authoring bug of a different kind,
    not the same-name-different-field collision this exists to catch; none
    is observed in this schema today.
    """
    exact = {}
    patterns = []
    occurrences = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "schema", "*.schema.json"))):
        area = os.path.basename(path).replace(".schema.json", "")
        doc = json.load(open(path))

        def entry_for(sub):
            return (sub["x-moho-disposition"],
                    sub.get("x-moho-evidence", sub.get("x-moho-unknown-reason", "")),
                    area,
                    sub.get("description", ""),
                    sub.get("x-moho-contradiction-waived", ""),
                    sub.get("x-moho-registry-conflict-waived", ""))

        def walk(node):
            if isinstance(node, dict):
                props = node.get("properties")
                if isinstance(props, dict):
                    for name, sub in props.items():
                        if isinstance(sub, dict) and "x-moho-disposition" in sub:
                            entry = entry_for(sub)
                            occurrences.setdefault(name, []).append(entry)
                            if name not in exact:
                                exact[name] = entry
                pprops = node.get("patternProperties")
                if isinstance(pprops, dict):
                    for pat, sub in pprops.items():
                        if isinstance(sub, dict) and "x-moho-disposition" in sub:
                            patterns.append((re.compile(pat), entry_for(sub)))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(doc)
    return exact, patterns, occurrences


def resolve(key, exact, patterns):
    """The registry entry for `key`, preferring an exact name match.

    Falls back to the first pattern whose regex matches -- `re.search`, not
    `fullmatch`, but every pattern in this schema is itself `^...$`-anchored
    (matching JSON Schema's own patternProperties semantics), so the two
    coincide in practice. Returns None when nothing registers the key at
    all, which is rule 1's failure condition. Both `exact` and `patterns`
    are already first-occurrence-wins (see load_registry), so this function
    itself has no further conflict to resolve.
    """
    if key in exact:
        return exact[key]
    for regex, entry in patterns:
        if regex.search(key):
            return entry
    return None


def find_disposition_conflicts(content, occurrences):
    """Rule 5: fail on a content key whose registry occurrences DISAGREE.

    `resolve()`/`exact` silently pick the first-declared occurrence and
    move on -- exactly the mechanism that let `channel.b`'s fix (rule 4,
    round 1: re-annotating `InterpEntry.b` from a false MODELLED to the
    UNKNOWN it actually is) turn into a fresh under-count, because
    `InterpEntry.b` is still declared before the genuinely-MODELLED
    `ColorValue.b`/`layer.schema.json`'s own `b`. Rule 4 could not have
    caught this: it only inspects a MODELLED entry's OWN description, and
    `InterpEntry.b` is UNKNOWN with an accurate reason, no contradiction to
    find. This rule instead compares occurrences of the SAME key name
    against EACH OTHER, restricted to `content` (an unregistered or
    description-only key is a different rule's problem, and a conflict on a
    name that never appears in the corpus does not affect any score yet, so
    it is not worth failing the build over until it does).

    A found conflict fails unless at least one of the conflicting
    occurrences carries `x-moho-registry-conflict-waived` -- deliberately a
    per-NAME waiver (present on any one occurrence in the group), not a
    per-occurrence one like rule 4's `x-moho-contradiction-waived`, since
    the thing being attested is a fact about the whole group ("these
    occurrences are known to be unrelated fields that happen to share a
    name, and scoring the flat key by the best of them is intentional"),
    not about any single entry's own text. See `effective_disposition` for
    what the waiver then unlocks; this rule does not use the waiver text for
    anything besides "is there one at all" -- a future reader inspects the
    text by hand, the same trust model as rule 4's waiver.
    """
    failures = []
    for key in sorted(content):
        entries = occurrences.get(key)
        if not entries or len(entries) < 2:
            continue
        dispositions = {e[0] for e in entries}
        if len(dispositions) < 2:
            continue
        if any(e[5] for e in entries):
            continue
        areas = sorted({e[2] for e in entries})
        failures.append(
            "conflicting dispositions for key '%s': %s across %d schema "
            "occurrences in %s -- a flat-by-name registry collision (see "
            "load_registry) that first-occurrence-wins would silently "
            "under- or over-count; add x-moho-registry-conflict-waived to "
            "one of the occurrences once hand-confirmed to be unrelated "
            "fields sharing a name (see find_disposition_conflicts)"
            % (key, sorted(dispositions), len(entries), areas))
    return failures


def effective_disposition(key, exact, patterns, occurrences):
    """The disposition used for SCORING `key` -- the most favourable one
    across ALL of its registry occurrences, not just the first-declared.

    `resolve()` picks one occurrence to quote (evidence text, area,
    description) and that is still right for messages that must point at a
    single piece of prose. Scoring is a different question: the census and
    the trace are ALSO flat by key name (see build_census / trace_fields.py
    -- neither records WHICH occurrence a key belongs to), so the only
    question this script can actually answer is "is at least one meaning of
    this name modelled", not "does the first-declared meaning happen to be
    modelled". Promoting a key to COUNTED the moment ANY occurrence is
    MODELLED/EDITABLE is what fixes `b` (`InterpEntry.b` is UNKNOWN and
    declared first; `ColorValue.b` and `layer.schema.json`'s `b` are both
    MODELLED with real evidence) without hand-patching that one pair --
    ANY future same-name collision resolves the same way automatically.

    This optimism is safe specifically because `find_disposition_conflicts`
    (rule 5) fails the build on every such divergence that lacks an
    `x-moho-registry-conflict-waived` annotation -- so a name only reaches
    this favourable reading after a human has confirmed the divergence is a
    genuine same-name/different-field collision, not a mistaken MODELLED
    claim on one occurrence (which is what rule 4 catches at the single-
    entry level, and what an unreviewed conflict could otherwise smuggle
    through: without rule 5, this function would just as happily launder a
    WRONG MODELLED occurrence into a covered key).
    """
    entry = resolve(key, exact, patterns)
    if entry is None:
        return None
    best = entry[0]
    for occ in occurrences.get(key, ()):
        if occ[0] in COUNTED:
            best = occ[0]
            break
    return best


def build_census(census_path):
    """Walk every document under moho/ and record its distinct JSON keys.

    Uses mohoedit.read_document, not a bare json.load, so the 30 `.moho` ZIP
    archives are actually opened -- reading only the top-level *.mohoproj/
    *.animeproj would silently repeat the exact 46-vs-76-document census
    error docs/moho-field-coverage-plan.md's spec §1 describes. The walk
    itself is `mohoedit.iter_documents` (shared with tools/trace_fields.py,
    tools/check_integrity.py and tools/check_roundtrip.py -- see that
    function's own docstring for why a single shared walk matters more than
    any one of its four callers individually).
    """
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
    for path in mohoedit.iter_documents():
        raw, _container = mohoedit.read_document(path)
        walk(raw)
        n += 1
    os.makedirs(os.path.dirname(census_path), exist_ok=True)
    json.dump({"keys": sorted(keys), "documents": n}, open(census_path, "w"), indent=1)
    print("census: %d documents, %d distinct keys" % (n, len(keys)))


def check_environment(trace, allow_degraded):
    """Rule 3: refuse to trust a trace taken with an optional dependency missing.

    Returns a list of failure strings (empty when the environment is clean).
    `allow_degraded` exists only for a deliberate, informed look at what a
    degraded trace would score -- `make check-coverage` never passes it, and
    passing it does not silence the loud banner, only the exit code.
    """
    env = trace.get("environment")
    if not isinstance(env, dict):
        return ["trace has no 'environment' block -- it predates this check; "
                "re-run tools/trace_fields.py"]
    missing = [dep for dep in REQUIRED_TRACE_DEPS if not env.get(dep)]
    if not missing:
        return []
    print("=" * 78)
    print("ENVIRONMENT WARNING: this trace was taken WITHOUT %s importable."
          % " / ".join(missing))
    print("That environment cannot reach the ImageLayer/PSD or combo_mode==3")
    print("pre-clipping branches, so it under-reports which keys are read --")
    print("known to cost exactly one key (image_fileref) per")
    print("tools/trace_fields.py's own module docstring. Trusting rule 2's")
    print("'declared MODELLED but never read' failures from a trace like this")
    print("invites 'fixing' a correct registry entry instead of the trace.")
    print("Re-run with the repository's .venv interpreter (`make check-coverage`")
    print("already does): %s tools/trace_fields.py" % os.path.join(ROOT, ".venv", "bin", "python3"))
    print("=" * 78)
    if allow_degraded:
        return []
    return ["trace environment missing: %s (see banner above; rerun tools/trace_fields.py "
            "inside .venv, or pass --allow-degraded-environment to score it anyway)"
            % ", ".join(missing)]


def print_area_table(census, content, exact, patterns, occurrences):
    """Print a Markdown table of disposition counts, one row per schema file.

    Grouping by schema FILE (channel/style/mesh/skeleton/layer/project)
    rather than by Moho "feature area" is a deliberate simplification: the
    registry only records which file FIRST annotated a key (see
    load_registry), and the six schema files already correspond to the
    subsystems docs/moho-project-file-format.md and schema/README.md
    describe (channels, styles, meshes, skeletons, layers, project-level).
    A future task can subdivide `layer` further if that granularity stops
    being useful; nothing here depends on it staying this coarse.

    The bucketed DISPOSITION per key is `effective_disposition`, the same
    one the headline `covered` count uses -- not the first-occurrence one
    `resolve()` alone would give. Using a different view here would make
    this table's own MODELLED+EDITABLE column sums silently disagree with
    the headline `covered` figure printed just above it (exactly the `b`
    case: first-occurrence is UNKNOWN, effective is MODELLED) -- a
    mismatch that undermines trust in the report even though neither
    number would technically be "wrong" in isolation. The AREA a key is
    filed under, though, still comes from `resolve()`'s first-declared
    occurrence -- that is only a grouping label, unaffected by which
    occurrence's disposition wins the count.
    """
    rows = {}
    for key in content:
        entry = resolve(key, exact, patterns)  # (disposition, evidence, area, description, waiver, conflict_waiver)
        area = entry[2] if entry else "(unregistered)"
        disposition = effective_disposition(key, exact, patterns, occurrences) if entry else "MISSING"
        row = rows.setdefault(area, {"MODELLED": 0, "EDITABLE": 0, "PRESERVE": 0, "UNKNOWN": 0, "MISSING": 0})
        row[disposition] = row.get(disposition, 0) + 1

    print()
    print("| Area | MODELLED | EDITABLE | PRESERVE | UNKNOWN | content keys | covered % |")
    print("|---|---|---|---|---|---|---|")
    for area in sorted(rows):
        row = rows[area]
        total = sum(row.values())
        covered = row["MODELLED"] + row["EDITABLE"]
        pct = 100.0 * covered / total if total else 0.0
        print("| %s | %d | %d | %d | %d | %d | %.1f%% |"
              % (area, row["MODELLED"], row["EDITABLE"], row["PRESERVE"], row["UNKNOWN"], total, pct))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--census", default=os.path.join(ROOT, "out", "census_keys.json"),
                     help="JSON list of every corpus key; produced by --census-build")
    ap.add_argument("--trace", default=os.path.join(ROOT, "out", "traced_keys.json"))
    ap.add_argument("--census-build", action="store_true",
                     help="walk moho/ and write the census file, then exit")
    ap.add_argument("--allow-degraded-environment", action="store_true",
                     help="score a trace even if it was taken without Pillow/psd-tools/"
                          "pyclipper -- for a deliberate look only, never for make check-coverage")
    ap.add_argument("--require-target", action="store_true",
                     help="exit non-zero when coverage is below the 95%% bar (see "
                          "required_coverage_keys). OFF by default: the sweep (M1-M3) has not "
                          "happened yet, and defaulting this on would fail every run for its "
                          "whole duration, which trains people to ignore the gate rather than "
                          "read it. Pass this once Phase 1 is expected to be complete.")
    args = ap.parse_args()

    if args.census_build:
        build_census(args.census)
        return 0

    if not os.path.exists(args.census):
        print("FAIL: %s is missing. Build it with --census-build." % args.census)
        return 1
    if not os.path.exists(args.trace):
        print("FAIL: %s is missing. Build it with tools/trace_fields.py." % args.trace)
        return 1

    census = set(json.load(open(args.census))["keys"])
    trace_data = json.load(open(args.trace))
    traced = set(trace_data["keys"])
    exact, patterns, occurrences = load_registry()

    failures = check_environment(trace_data, args.allow_degraded_environment)

    for key in sorted(census):
        entry = resolve(key, exact, patterns)
        if entry is None:
            failures.append("unregistered key: %s" % key)
            continue
        disposition, evidence, _area, description, waiver, _conflict_waiver = entry
        if disposition not in VALID:
            failures.append("bad disposition %r on %s" % (disposition, key))
        elif disposition == "MODELLED":
            if key not in traced:
                failures.append("declared MODELLED but never read: %s" % key)
            elif not evidence:
                failures.append("declared MODELLED with no evidence: %s" % key)
            # Rule 4: a MODELLED key whose own description asserts it is
            # never consumed at all contradicts the disposition it carries.
            # `waiver` (x-moho-contradiction-waived) is the one legitimate
            # escape: a NAMED, evidenced flat-registry collision (see the
            # module docstring), not a blanket opt-out.
            elif contradicts_modelled(description) and not waiver:
                failures.append(
                    "MODELLED key contradicts its own description: %s "
                    "(description asserts no read at all; fix the disposition/description, "
                    "or add x-moho-contradiction-waived with a reason if this is a "
                    "diagnosed flat-name collision)" % key)
        elif disposition == "EDITABLE" and not evidence:
            # Finding C: EDITABLE counts toward coverage exactly like
            # MODELLED and currently has no producer (the generator never
            # emits it), which is exactly why this is the cheap moment to
            # close the gap -- M1-M3 will hand-add roughly 270 of these.
            failures.append("declared EDITABLE with no evidence: %s" % key)
        elif disposition == "UNKNOWN" and not evidence:
            failures.append("declared UNKNOWN with no x-moho-unknown-reason: %s" % key)

    content = {k for k in census if not is_description(k)}
    # Rule 5: a content key whose registry occurrences disagree fails the
    # build unless a human has already reviewed and waived it (see
    # find_disposition_conflicts). Run BEFORE computing `covered` so that a
    # freshly-introduced, unreviewed conflict is visible as a FAIL line in
    # the same run whose headline percentage it would otherwise silently
    # move.
    failures.extend(find_disposition_conflicts(content, occurrences))
    covered = {k for k in content
               if effective_disposition(k, exact, patterns, occurrences) in COUNTED}
    pct = 100.0 * len(covered) / len(content) if content else 0.0
    required = required_coverage_keys(len(content))

    print("corpus keys        %d" % len(census))
    print("  description      %d (excluded)" % (len(census) - len(content)))
    print("  content          %d (the denominator)" % len(content))
    print("covered            %d = %.1f%%   target >= 95.0%% (%d/%d keys)"
          % (len(covered), pct, required, len(content)))
    # Kept SEPARATE from `failures` (Finding G): the four numbered rules,
    # the EDITABLE-evidence rule and the UNKNOWN-reason rule all answer "is
    # the REGISTRY trustworthy" -- a shortfall against the 95% target answers
    # a different question, "has the WORK finished", and conflating the two
    # under one "registry failures" count makes it impossible to tell "the
    # registry is broken" from "the sweep just hasn't happened yet" without
    # reading every FAIL line. The two lists are only OR'd together for the
    # exit code, which is unchanged from before this split.
    target_failures = []
    if len(covered) >= required:
        print("shortfall          0 keys -- target met")
    else:
        print("shortfall          %d keys short of the %d required"
              % (required - len(covered), required))
        if args.require_target:
            target_failures.append(
                "coverage %d/%d (%.1f%%) is %d keys short of the %d required for the "
                "95%% target (pass without --require-target during M1-M3)"
                % (len(covered), len(content), pct, required - len(covered), required))
    print_area_table(census, content, exact, patterns, occurrences)
    print()
    print("registry failures  %d" % len(failures))
    for line in failures[:40]:
        print("   FAIL %s" % line)
    if len(failures) > 40:
        print("   ... %d more" % (len(failures) - 40))
    print("target failures    %d" % len(target_failures))
    for line in target_failures:
        print("   FAIL %s" % line)
    return 1 if (failures or target_failures) else 0


if __name__ == "__main__":
    sys.exit(main())
