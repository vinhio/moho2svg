#!/usr/bin/env python3
"""Assert that constructing a Document does not modify the raw JSON tree.

Document construction used to overwrite every PatchLayer's own parent_bone,
flexi_bone_subset and origin with its target layer's values, in the raw dict
(moho2svg.py:5135-5137 before this check existed). A patch's own transform is
its clip region -- see docs/moho-project-file-format.md 12.1 -- so an editor
that loaded and saved a document silently destroyed it.

Runs over the five corpus documents that carry PatchLayers. `moho/` is
gitignored -- this is the local development corpus, not something every
checkout is guaranteed to have -- so the skip/fail policy mirrors
`tools/check_export_stability.py`'s `run_exports`/`main` exactly: an absent
document is skipped, not a failure, but a run that finds NONE of the five is
not a lesser-coverage pass, it is a gate that verified nothing, so that case
fails loudly instead of printing a hollow "OK".
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


def check_documents():
    """Load each document in PATCH_DOCS that exists on disk, deep-copy its
    raw JSON before construction, and diff that snapshot against the same
    dict after `Document.from_raw` returns.

    Returns (compared, skipped, mutated): the count actually checked, the
    count skipped because the source file is absent, and the count that
    failed the diff. Comparing against a deep copy, rather than trusting `==`
    to work the other way round, is deliberate: `raw == before` is only
    meaningful if `before` was captured BEFORE `Document.from_raw` ever
    touched `raw`.
    """
    compared = 0
    skipped = 0
    mutated = 0
    for rel in PATCH_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            print("SKIP %s (absent)" % rel)
            skipped += 1
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw = json.load(fh)
        before = copy.deepcopy(raw)
        moho2svg.Document.from_raw(raw)
        compared += 1
        if raw == before:
            print("ok   %-40s raw tree unchanged" % rel)
        else:
            print("FAIL %-40s raw tree MUTATED by construction" % rel)
            mutated += 1
    return compared, skipped, mutated


def main():
    """Run `check_documents` and turn its (compared, skipped, mutated) counts
    into a pass/fail verdict.

    Skip-on-absence alone is not enough of a policy: it must not be possible
    for every document in PATCH_DOCS to be absent (e.g. `moho/` altogether
    missing on a checkout with no local corpus) and still see a green "OK" --
    that would be a gate reporting success having verified nothing, which is
    more dangerous than reporting a failure, since nothing downstream would
    know coverage was actually zero. So a run that compares zero documents
    fails loudly instead, exactly like `check_export_stability.py --update`'s
    sibling check does for the same reason.
    """
    compared, skipped, mutated = check_documents()
    if compared == 0:
        print("\nFAIL: no PATCH_DOCS were found (%d skipped, all absent). "
              "moho/ is gitignored, so populate it with the sample corpus "
              "before running this check -- a gate that passes because it "
              "checked nothing is worse than one that fails." % skipped)
        return 1
    print("\n%s: %d compared, %d skipped, %d mutated"
          % ("FAIL" if mutated else "OK", compared, skipped, mutated))
    return 1 if mutated else 0


if __name__ == "__main__":
    sys.exit(main())
