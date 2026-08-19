#!/usr/bin/env python3
"""An edited document survives a save, and Moho renders the edit differently.

The weaker claim -- an untouched document round-trips -- is check_roundtrip.py.
This one changes a value, saves, reloads, confirms the change is still there,
then (when Moho is installed) renders with Moho twice and requires the pixels
to DIFFER. A save that silently dropped the edit would pass a structural
check and fail here.

This is deliberately TWO independent checks, not one:

1. "the edit survives the save" needs nothing but this repository's own code
   and always runs. It is the one that catches a writer silently discarding
   an edit -- the exact failure this whole gate exists to detect -- so it
   must never be skipped, on any machine, for any reason.
2. "Moho renders the edit differently" needs Moho.app itself and may be
   skipped when it is absent, matching every other gate under tools/ that
   depends on something a checkout is not guaranteed to have (moho/ itself,
   in check_export_stability.py and check_no_raw_mutation.py).

A gate that passes because it checked nothing is worse than one that fails,
so skipping check 2 must never turn into a bare "OK": the summary line always
says how many of the two checks ran and how many were skipped, and the exit
code is decided by check 1 alone whenever check 2 is skipped.

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
    """Depth-first search for the first dict carrying a non-empty "bones" list.

    TransformBoneTool.animeproj is small enough that a plain recursive walk
    over the raw JSON is simplest here; this check only needs one bone's own
    anim_angle channel, not a whole moho2svg.Document, so it does not need
    that module's own layer-tree walk.
    """
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
    """Render frame FRAME of `path` with Moho and return the PNG it actually wrote.

    `-o OUT.png` is a stem, not a literal filename: even a `-start N -end N`
    range of length one is written as `OUT_NNNNN.png`, zero-padded to five
    digits with the frame number -- confirmed empirically, not assumed from
    the brief this check was drafted from. Falling back to the literal `out`
    path if that naming guess is wrong (rather than raising here) lets a
    genuinely missing file surface as a plain "file not found" from the
    caller instead of masking a real Moho failure inside this helper.
    """
    subprocess.run([MOHO, "-r", path, "-f", "PNG",
                    "-start", str(FRAME), "-end", str(FRAME), "-o", out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stem, ext = os.path.splitext(out)
    produced = "%s_%05d%s" % (stem, FRAME, ext)
    return produced if os.path.exists(produced) else out


def check_edit_survives_save():
    """Rotate a bone's anim_angle by DELTA, save, reload, and confirm it stuck.

    Needs no Moho and must always run -- see the module docstring. Returns
    (passed, message, base_path, edited_path): the two paths are handed to
    check_moho_renders_edit so that function never has to redo the edit
    itself, and are still returned even on failure so a caller that chooses
    to attempt the render half anyway (as main() does, for evidence) can.
    """
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
        return False, "edit did not survive the save: %s" % got, base, edited
    return True, "edit survives the save", base, edited


def check_moho_renders_edit(base, edited):
    """Render `base` and `edited` with Moho and require the PNG bytes to differ.

    Byte equality (not a pixel/perceptual diff) is enough here: this check
    only ever needs to claim "these two renders differ", never to measure by
    how much, and comparing raw bytes needs no new dependency (Pillow stays
    optional for the whole project). Assumes Moho is present -- the
    presence check itself lives in main(), since whether to skip this
    function is a policy decision, not this function's own job.
    """
    outdir = os.path.dirname(base)
    base_png = render(base, os.path.join(outdir, "base.png"))
    edit_png = render(edited, os.path.join(outdir, "edited.png"))
    with open(base_png, "rb") as a, open(edit_png, "rb") as b:
        same = a.read() == b.read()
    if same:
        return False, "Moho rendered the edited document identically - the edit had no effect"
    return True, "Moho renders the edit differently"


def main():
    """Run both checks and turn the results into a pass/fail verdict.

    Check 1 always runs. Check 2 runs whenever Moho is installed, regardless
    of whether check 1 passed -- there is no special-casing to skip it on a
    check-1 failure, because a broken writer that discards the edit produces
    its own honest evidence here too (base and edited render identically,
    since "edited" is really an unedited copy), which is a useful thing to
    show rather than a reason to suppress the attempt.

    The exit code is 0 only if every check that actually ran passed. A
    skipped check never masks a real failure and never manufactures a bare
    "OK": the summary line always states how many of the 2 checks ran,
    passed, and were skipped, because a gate that passes having verified
    nothing is worse than one that fails.
    """
    total = 2
    passed = 0
    skipped = 0

    ok1, message1, base, edited = check_edit_survives_save()
    print("%s %s" % ("ok  " if ok1 else "FAIL", message1))
    if ok1:
        passed += 1

    if not os.path.exists(MOHO):
        skipped += 1
        print("SKIP Moho renders the edit differently (Moho is not installed at %s)" % MOHO)
    else:
        ok2, message2 = check_moho_renders_edit(base, edited)
        print("%s %s" % ("ok  " if ok2 else "FAIL", message2))
        if ok2:
            passed += 1

    failed = total - passed - skipped
    verdict = "FAIL" if failed else "OK"
    suffix = ", %d skipped (Moho not installed)" % skipped if skipped else ""
    print("\n%s: %d of %d checks passed%s" % (verdict, passed, total, suffix))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
