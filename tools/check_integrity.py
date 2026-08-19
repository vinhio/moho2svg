#!/usr/bin/env python3
"""Every corpus document passes the reference-integrity checks.

A Moho mesh is held together by positional indices with no allocator and no
generation counter: shape.edges.curve indexes mesh.curves, curve.points[].point
indexes mesh.points, and bone.parent indexes its own skeleton's bone list.
Deleting one entry silently invalidates every reference above it. This asserts
the 76 documents we hold are internally consistent, which is what makes
mohoedit.check_integrity trustworthy as a gate on later structural edits (see
that function's own docstring for the four reference classes it deliberately
does NOT check yet, and why).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mohoedit  # noqa: E402

EXPECTED_DOCUMENTS = 76


def main():
    """Run check_integrity over every corpus document and fail on any hit.

    The `bad + ok < EXPECTED_DOCUMENTS` guard matches check_roundtrip.py and
    every other gate here: `moho/` is gitignored, so on a checkout without the
    corpus `mohoedit.iter_documents` would silently yield zero files and this
    script would otherwise print a cheerful "OK: 0 documents with problems"
    having checked nothing at all. A gate that passes having verified nothing
    is worse than one that fails, so that case fails loudly instead.
    """
    bad = ok = 0
    for path in mohoedit.iter_documents():
        rel = os.path.relpath(path, ROOT)
        raw, _ = mohoedit.read_document(path)
        problems = mohoedit.check_integrity(raw)
        if problems:
            print("FAIL %-52s %d problems, first: %s" % (rel, len(problems), problems[0]))
            bad += 1
        else:
            ok += 1
    print("\n%s: %d documents with problems" % ("FAIL" if bad else "OK", bad))
    if ok + bad < EXPECTED_DOCUMENTS:
        print("FAIL: expected at least %d documents, walked %d" % (EXPECTED_DOCUMENTS, ok + bad))
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
