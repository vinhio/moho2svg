#!/usr/bin/env python3
"""Every document under moho/ round-trips through read_document/write_document.

Task 3 asserted only that all 76 documents can be read. Task 4 grows this into
a full load -> save -> reload -> compare round-trip: it proves write_document
reproduces both the parsed structure and the exact packaging (bare file vs.
archive, and every archive member byte-for-byte) that read_document reported,
which is the guarantee every later editing task (6, 9, 10) builds on.
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mohoedit  # noqa: E402

EXPECTED_DOCUMENTS = 76


def _json_diff(a, b, path):
    """Report the first structural OR type difference between two JSON trees.

    Plain `==` is not enough for this gate: Python's numeric tower conflates
    types JSON keeps distinct (`1 == 1.0` and `True == 1` are both true), so a
    writer that silently turned an int into a float, or a bool into an int,
    would pass a plain `==` comparison of the reloaded structure against the
    original while writing back a genuinely different JSON value. This is not
    a hypothetical: this repository has measured, by rendering with Moho
    itself, that Moho rejects a document with "Unable to load document
    (corrupt)" (error 108) when `project_data.noise_grain` is JSON `false`
    instead of integer `0` -- exactly this class of difference. 113 of the
    format's keys are classified PRESERVE (not modelled, but guaranteed to
    survive a load and save unchanged), and this comparison is the only
    evidence behind that guarantee, so it has to be able to see a type
    change even where `==` cannot.

    Dict key order is immaterial to JSON semantics (a JSON object is an
    unordered set of members), so only the set of keys and their values are
    compared, never `dict` iteration order.

    Returns `None` when `a` and `b` agree, or a one-line string describing
    the first disagreement found -- as a JSON-ish path (e.g.
    `layers[0].mesh.points[3].width.val[0]`), both values and both Python
    type names -- when they do not. `path` is the JSON path accumulated so
    far; callers should pass `""` for the root.
    """
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return "%s: keys differ, only in first=%r only in second=%r" % (
                path or "$", sorted(set(a) - set(b)), sorted(set(b) - set(a)))
        for key in a:
            child = "%s.%s" % (path, key) if path else str(key)
            diff = _json_diff(a[key], b[key], child)
            if diff is not None:
                return diff
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return "%s: length %d != %d" % (path or "$", len(a), len(b))
        for i, (x, y) in enumerate(zip(a, b)):
            diff = _json_diff(x, y, "%s[%d]" % (path, i))
            if diff is not None:
                return diff
        return None
    # Scalar (or dict/list vs. something else, e.g. a widened/narrowed type):
    # `type(a) is not type(b)` catches bool-vs-int and int-vs-float, which
    # `isinstance` and `==` alone would both miss (bool is an int subclass,
    # and 1 == 1.0 is true across types).
    if type(a) is not type(b) or a != b:
        return "%s: %r (%s) != %r (%s)" % (
            path or "$", a, type(a).__name__, b, type(b).__name__)
    return None


def main():
    """Round-trip every document `mohoedit.iter_documents` finds through read/write/read.

    Reading alone (Task 3's version of this check) cannot catch a writer that
    silently drops an archive member, mis-serializes a value Python's `json`
    round-trips differently than it parsed, or writes a `.moho` back out as
    bare JSON. So each document is read, written to a throwaway temp file,
    and read back, and the second read's structure and packaging are compared
    against the first read's: the parsed dict must agree with `_json_diff`
    (structurally AND by type -- see that function's docstring for why plain
    `==` is not enough here), the packaging `kind` (bare file vs. archive)
    must be unchanged, and -- for an archive -- the exact set of non-project
    members and their bytes must survive untouched. A temp directory is used
    (rather than writing next to the source) so this check never risks
    touching a real corpus file.

    The `ok + bad < EXPECTED_DOCUMENTS` guard exists for the same reason
    `check_export_stability.py`/`check_no_raw_mutation.py` refuse to report a
    hollow "OK": on a checkout whose gitignored `moho/` corpus is thin or
    absent, `mohoedit.iter_documents` would silently yield fewer files and
    this script would otherwise print a cheerful "0 failed" having verified
    almost nothing. Round-tripping fewer than 76 documents fails loudly
    instead.
    """
    ok = bad = 0
    for path in mohoedit.iter_documents():
        rel = os.path.relpath(path, ROOT)
        try:
            raw, container = mohoedit.read_document(path)
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, os.path.basename(path))
                mohoedit.write_document(out, raw, container)
                again, container2 = mohoedit.read_document(out)
            diff = _json_diff(raw, again, "")
            assert diff is None, diff
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


if __name__ == "__main__":
    sys.exit(main())
