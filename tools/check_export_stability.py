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
    """Return ({label: sha256}, [skipped source paths]) for EXPORTS.

    `moho/` is gitignored -- this is the local development corpus, not
    something every checkout is guaranteed to have -- so a document that
    is not on disk is recorded as skipped rather than treated as an error
    here. Whether an entirely-skipped run should still pass is a policy
    decision that belongs to the caller (`main`), not to this function: this
    function's only job is to report what it actually found and built.
    """
    os.makedirs(outdir, exist_ok=True)
    digests = {}
    skipped = []
    for src, args in EXPORTS:
        if not os.path.exists(os.path.join(ROOT, src)):
            print("SKIP %s (absent)" % src)
            skipped.append(src)
            continue
        label = os.path.basename(src)
        out = os.path.join(outdir, label + ".svg")
        cmd = [sys.executable, os.path.join(ROOT, "moho2svg.py"),
               os.path.join(ROOT, src)] + [a.format(out=out) for a in args]
        subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        with open(out, "rb") as fh:
            digests[label] = hashlib.sha256(fh.read()).hexdigest()
    return digests, skipped


def load_expected():
    """Parse `tools/export_hashes.txt` into {label: sha256}.

    Each recorded line is `<sha256>  <label>`; splitting with
    `split(None, 1)` rather than a fixed-width slice or a single-space split
    is what makes the file tolerant of hand-editing (extra/odd whitespace
    between the two fields does not break parsing, only the LABEL, which
    must not itself contain whitespace, matters). Blank lines and lines
    starting with `#` are skipped so the explanatory header comment that
    `main`'s `--update` path writes round-trips without the parser choking
    on it. An absent file returns {} rather than raising, which `main`
    reads as "no baseline recorded yet" -- a distinct condition from "a
    baseline exists and it is empty", the latter being unreachable since
    `--update` never writes zero hashes without also failing to run.
    """
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
    """Compare this run's exports against `tools/export_hashes.txt`, or
    (with `--update`) write a new baseline instead of comparing.

    `--update` is a separate, explicitly-requested mode rather than an
    automatic fallback for "no baseline yet" or "the check failed", because
    a gate that silently re-baselines itself on failure has stopped being a
    gate -- it would let a real regression through disguised as a first run.
    Recording a baseline is a deliberate, reviewable act (the rewritten
    `tools/export_hashes.txt` is meant to show up in the diff of whatever
    commit intentionally changed output), never an implicit side effect of
    running the check.

    Skip-on-absence follows the same policy `check-reference` documents in
    its own Makefile comment, and for the same reason: `moho/` is
    gitignored, so a machine without the local corpus must not fail this
    gate for a reason unrelated to export correctness. But a run that finds
    NONE of the five documents is not a lesser-coverage pass, it is a gate
    that verified nothing -- reporting that as "OK" would be worse than
    reporting a failure, since a green check with no evidence behind it is
    the more dangerous of the two, so that case fails loudly instead.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true",
                    help="rewrite the hash file instead of comparing")
    ap.add_argument("--outdir", default=os.path.join(ROOT, "out", "stability"))
    args = ap.parse_args()

    got, skipped = run_exports(args.outdir)
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

    if not got:
        print("FAIL: no export documents were found (%d skipped, all of EXPORTS absent). "
              "moho/ is gitignored, so populate it with the sample corpus before running this "
              "check -- a gate that passes because it checked nothing is worse than one that "
              "fails." % len(skipped))
        return 1

    skipped_labels = {os.path.basename(src) for src in skipped}
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
    # A label present in the hash file but neither produced nor skipped this
    # run (e.g. removed from EXPORTS entirely) is a stale-baseline failure;
    # one that is missing because its source document was skipped as absent
    # is not -- that is exactly the "absence is not a failure" case above,
    # already reported via the SKIP line `run_exports` printed.
    for label in sorted(set(expected) - set(got) - skipped_labels):
        print("FAIL %-34s expected but not produced" % label)
        bad += 1
    print("\n%s: %d compared, %d skipped, %d mismatched"
          % ("FAIL" if bad else "OK", len(got), len(skipped), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
