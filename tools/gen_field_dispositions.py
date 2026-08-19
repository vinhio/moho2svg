#!/usr/bin/env python3
"""Seed `x-moho-disposition` onto every schema property that lacks one.

Hand-typing 547 annotations across six schema files was rejected outright
(see docs/moho-field-coverage-plan.md Task 8's rulings): at this scale
hand-editing produces transcription errors and filler faster than it produces
real content, and it would take longer than the rest of the plan. This script
computes the disposition mechanically from two artifacts that already exist
-- the corpus census (`out/census_keys.json`) and the runtime trace
(`out/traced_keys.json`) -- and writes the annotation in place.

SEEDING RULE for this pass (do not re-derive; a later probe, Task 10, is what
earns a key a stronger claim):
  - a DESCRIPTION key (tools/check_field_coverage.is_description) -> PRESERVE
  - a CONTENT key the trace observed reading -> MODELLED
  - a CONTENT key the trace never observed -> UNKNOWN, reason "not yet
    investigated"

MODELLED evidence is DELIBERATELY THIN here. The design spec's full
definition of MODELLED also asks for "a named check asserting the rendered
effect" -- applied literally to the 142 keys the trace already observes,
almost none would qualify, because check_reference_frames.py and
check_lottie_geometry.py assert geometry in aggregate, not per key, and
proving each key individually would turn this seeding pass into an unbounded
verification project on its own. So for THIS PASS, MODELLED evidence is: the
trace observed the key, PLUS a pointer at the exact code location that
observation came from (tools/trace_fields.py's own `call_sites`, the first
real call frame that read the key during a real export) plus the trace
artifact itself. The stronger per-key rendered-effect evidence is Task 10's
probe (M1-M3); when a probe records a result for a key, that is what should
overwrite the evidence text this script writes, not the other way round.

Mechanics: rather than reparsing and reserializing the schema as JSON (which
would flatten this hand-formatted, one-object-per-line schema into one key
per line, and turn every future review into a wall of formatting noise), this
locates each `"name": { ... }` span with a brace-respecting scanner
(`find_matching_close`, which skips over content inside JSON string literals)
and inserts the two new keys just before that object's closing brace. The
SAME decision is applied to every occurrence of a given property name across
every schema file, since a name like `type` or `name` is declared once per
`$def` -- dozens of times -- and the checker's registry is a flat map by name
anyway (see check_field_coverage.load_registry), so there is nothing to gain
from picking just one "canonical" spot and every reason to keep every
occurrence's own displayed status accurate. `patternProperties` families
(`DocState_*`, `g_<number>`) are annotated once, on the PATTERN entry itself,
using the classification of whichever matching census key is found first --
the two existing families are each internally homogeneous (all DESCRIPTION),
and a family that turned out NOT to be would print a loud warning below
rather than being silently annotated wrong.

Idempotent: an occurrence that already carries `x-moho-disposition` (the five
hand-picked in Task 8 Step 1, or a second run of this script) is left
untouched, so hand-refinement always survives a re-run.

Usage:
    tools/gen_field_dispositions.py --check    # report only, write nothing
    tools/gen_field_dispositions.py            # write the annotations
Always follow with tools/check_field_coverage.py -- this script SEEDS the
registry, it does not verify it.
"""

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIR = os.path.join(ROOT, "schema")

sys.path.insert(0, os.path.join(ROOT, "tools"))
import check_field_coverage as cfc  # noqa: E402  (reuses DESCRIPTION_PATTERNS/load_registry)


def find_matching_close(text, open_idx):
    """Return the index of the `}` matching the `{` at `text[open_idx]`.

    A plain bracket counter is not enough: several descriptions in this
    schema quote literal JSON fragments in prose (e.g. Channel's own
    docstring-style description mentions `{"x":..,"y":..}`), and those braces
    sit inside a JSON string, not the document structure. This walks the text
    respecting string boundaries and backslash escapes so only STRUCTURAL
    braces are counted.
    """
    assert text[open_idx] == "{"
    depth = 0
    in_string = False
    escape = False
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    raise ValueError("unterminated object starting at offset %d" % open_idx)


def decide(key, traced, call_sites):
    """The seeding rule above, as code. Returns (disposition, extra_field, value)."""
    if cfc.is_description(key):
        return ("PRESERVE", "x-moho-evidence",
                "Editor/view/provenance state matched by DESCRIPTION_PATTERNS; "
                "excluded from the content metric but still required to survive "
                "an unedited load->save (tools/check_roundtrip.py).")
    if key in traced:
        site = call_sites.get(key, "call site not recorded (trace predates call_sites)")
        return ("MODELLED", "x-moho-evidence",
                "%s (trace: out/traced_keys.json, see tools/trace_fields.py)" % site)
    return ("UNKNOWN", "x-moho-unknown-reason", "not yet investigated")


def collect_pattern_defs():
    """Every `patternProperties` regex string declared anywhere in schema/,
    regardless of whether it already carries an annotation -- unlike
    check_field_coverage.load_registry, which only returns ANNOTATED
    patterns. Needed so a key belonging to an existing but not-yet-annotated
    family (e.g. `DocState_zoom0` before this script has run) is recognised
    as pattern-covered rather than mistaken for a plain, individually
    declared property that simply does not exist in the text.
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            pprops = node.get("patternProperties")
            if isinstance(pprops, dict):
                for pat in pprops:
                    found.append(re.compile(pat))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for path in sorted(glob.glob(os.path.join(SCHEMA_DIR, "*.schema.json"))):
        walk(json.load(open(path)))
    return found


def annotate_spans(text, name_pattern_pairs):
    """Insert an annotation before the closing brace of every occurrence of
    each `"literal-json-key": { ... }` span named in `name_pattern_pairs`.

    `name_pattern_pairs` is {json_key_text: (disposition, field, value)} --
    `json_key_text` is the exact text that appears between the quotes in the
    file (a plain property name, or a patternProperties regex string). Edits
    are collected first and applied back-to-front so earlier offsets in
    `text` stay valid while later ones are being rewritten.
    """
    edits = []
    for json_key_text, (disposition, field, value) in name_pattern_pairs.items():
        search = re.compile(r'"' + re.escape(json_key_text) + r'"\s*:\s*\{')
        for m in search.finditer(text):
            open_idx = m.end() - 1
            try:
                close_idx = find_matching_close(text, open_idx)
            except ValueError:
                continue
            span = text[open_idx:close_idx + 1]
            if '"x-moho-disposition"' in span:
                continue  # already annotated -- Step 1's hand-picked five, or a re-run
            inner = text[open_idx + 1:close_idx].strip()
            prefix = "" if inner == "" else ", "
            insertion = "%s\"x-moho-disposition\": %s, \"%s\": %s" % (
                prefix, json.dumps(disposition), field, json.dumps(value))
            edits.append((close_idx, insertion))
    edits.sort(key=lambda e: -e[0])
    for close_idx, insertion in edits:
        text = text[:close_idx] + insertion + text[close_idx:]
    return text, len(edits)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report what would change; write nothing")
    ap.add_argument("--census", default=os.path.join(ROOT, "out", "census_keys.json"))
    ap.add_argument("--trace", default=os.path.join(ROOT, "out", "traced_keys.json"))
    args = ap.parse_args()

    census = json.load(open(args.census))["keys"]
    trace = json.load(open(args.trace))
    traced = set(trace["keys"])
    call_sites = trace.get("call_sites", {})

    exact, annotated_patterns = cfc.load_registry()
    all_patterns = collect_pattern_defs()

    # Plain property names needing a fresh decision: content/description
    # split by name, skipping anything already registered (hand-annotated,
    # or covered by an already-annotated pattern) and anything covered by a
    # STRUCTURAL pattern that simply has not been annotated yet (handled
    # below, once per pattern instead of once per matching key).
    name_decisions = {}
    pattern_members = {p.pattern: [] for p in all_patterns}
    for key in census:
        if key in exact:
            continue
        if any(p.search(key) for p, *_ in annotated_patterns):
            continue
        matched_pattern = next((p for p in all_patterns if p.search(key)), None)
        if matched_pattern is not None:
            pattern_members[matched_pattern.pattern].append(key)
            continue
        name_decisions[key] = decide(key, traced, call_sites)

    # One decision per still-unannotated pattern family, from its first
    # matching census key -- and a loud warning if the family turns out not
    # to be homogeneous, so a mixed family gets hand-reviewed rather than
    # silently mis-tagged.
    for pattern_text, members in pattern_members.items():
        if not members:
            continue
        decisions = {decide(k, traced, call_sites)[0] for k in members}
        if len(decisions) > 1:
            print("WARNING: pattern %r covers keys with different classifications: %s"
                  % (pattern_text, sorted(members)))
        name_decisions[pattern_text] = decide(members[0], traced, call_sites)

    total = 0
    for path in sorted(glob.glob(os.path.join(SCHEMA_DIR, "*.schema.json"))):
        text = open(path, encoding="utf-8").read()
        new_text, n = annotate_spans(text, name_decisions)
        if n:
            print("%s%-28s %d occurrence(s) annotated"
                  % ("[dry-run] " if args.check else "", os.path.basename(path), n))
            if not args.check:
                open(path, "w", encoding="utf-8").write(new_text)
                json.load(open(path, encoding="utf-8"))  # fail loudly now, not at the next tool run
        total += n

    print("\n%d distinct key/pattern decision(s), %d occurrence(s) %s"
          % (len(name_decisions), total, "would be annotated" if args.check else "annotated"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
