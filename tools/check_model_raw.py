#!/usr/bin/env python3
"""Every document-model object exposes the dict it was built from.

Without this an editor cannot reach anything below Layer: Shape keeps 9 of
its 17 JSON keys, MeshPoint 3 of 11, Bone about 35 of 61, and Document kept
no root dict at all. The reading model stays as it is -- this only stops it
throwing the source away.

Runs against a single fixed document, `moho/Bandit.mohoproj` -- `moho/` is
gitignored, so this is the local development corpus, not something every
checkout is guaranteed to have. Unlike the other gates under `tools/`, there
is nothing to skip-and-continue over here: one document is enough to prove
every class in DOCUMENT_MODEL_CLASSES kept its `raw`, so an absent document
means the whole gate verified nothing and must fail loudly rather than
report a hollow "OK" -- the same policy `check_export_stability.py` and
`check_no_raw_mutation.py` already follow for the same reason.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import moho2svg  # noqa: E402
import mohoedit  # noqa: E402

DOCUMENT = "moho/Bandit.mohoproj"


def run_checks(raw: dict) -> list:
    """Build a Document from `raw` and check `.raw` on every class this task
    added it to, plus `Document.raw` itself.

    Returns a list of (label, passed) pairs. `Edge` is deliberately absent
    from this list: it is a frozen dataclass built by zipping three parallel
    arrays (`shape.raw["edges"]["curve"/"segment"/"flag"]`), so it has no
    single source dict of its own to keep -- once `Shape.raw` is confirmed,
    those arrays are already reachable through it.

    `Document.walk()` yields `(ancestor_chain, layer)` pairs, ancestor_chain
    root-first and excluding the layer itself -- NOT bare layers -- so the
    loop unpacks that tuple rather than treating each yielded item as a
    layer directly.
    """
    doc = moho2svg.Document.from_raw(raw)
    checks = [("Document.raw is the root dict", doc.raw is raw)]
    found_mesh = found_bone = found_transform = False
    for _ancestors, layer in doc.walk():
        mesh = getattr(layer, "mesh", None)
        if mesh is not None and not found_mesh:
            found_mesh = True
            checks.append(("Mesh.raw", isinstance(mesh.raw, dict)))
            checks.append(("Shape.raw", isinstance(mesh.shapes[0].raw, dict)))
            checks.append(("Curve.raw", isinstance(mesh.curves[0].raw, dict)))
            checks.append(("CurvePoint.raw", isinstance(mesh.curves[0].points[0].raw, dict)))
            checks.append(("MeshPoint.raw", isinstance(mesh.points[0].raw, dict)))
        transform = getattr(layer, "transform", None)
        if transform is not None and not found_transform:
            found_transform = True
            checks.append(("Transform.raw", isinstance(transform.raw, dict)))
        skel = getattr(layer, "skeleton", None)
        if skel is not None and getattr(skel, "bones", None) and not found_bone:
            found_bone = True
            checks.append(("Skeleton.raw", isinstance(skel.raw, dict)))
            checks.append(("Bone.raw", isinstance(skel.bones[0].raw, dict)))
    if not (found_mesh and found_bone and found_transform):
        checks.append(("reached a mesh, a skeleton and a transform", False))
    return checks


def main():
    """Run `run_checks` against DOCUMENT and turn the result into a
    pass/fail verdict.

    An absent DOCUMENT fails loudly rather than being skipped: this gate
    checks one fixed document by design (there is nothing per-document to
    aggregate, unlike `check_export_stability.py`'s five or
    `check_no_raw_mutation.py`'s five), so "the document is missing" and
    "the gate verified nothing" are the same event here -- reporting that
    as a skip would hide it behind a misleadingly quiet exit code.
    """
    path = os.path.join(ROOT, DOCUMENT)
    if not os.path.exists(path):
        print("FAIL: %s is absent. moho/ is gitignored, so populate it with "
              "the sample corpus before running this check -- a gate that "
              "passes because it checked nothing is worse than one that "
              "fails." % DOCUMENT)
        return 1

    raw, _container = mohoedit.read_document(path)
    checks = run_checks(raw)
    bad = 0
    for label, passed in checks:
        print("%s %s" % ("ok  " if passed else "FAIL", label))
        bad += 0 if passed else 1
    print("\n%s: %d checks, %d failed" % ("FAIL" if bad else "OK", len(checks), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
