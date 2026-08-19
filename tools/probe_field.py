#!/usr/bin/env python3
"""Decide whether one JSON field affects what Moho renders.

The method is this repository's established one -- render the same document
twice with a single field changed, so every unrelated modelling error cancels
out. It decoded fixed_angle, mask_expansion, stroke exposure and both masking
enums. What is new here is only that it is driven from the command line, so a
sweep of a few hundred fields is a loop rather than a few hundred
investigations. See docs/superpowers/specs/2026-08-18-moho-field-coverage-design.md
section 6 for the design this implements.

Outcome, recorded either way, ONE ROW PER SUCCESSFUL PROBE in
docs/moho-field-probes.md:
  pixels differ -> the field affects rendering. EDITABLE now, and stamped
                   x-moho-render: pending for Phase 2.
  pixels equal  -> the field is inert for rendering. EDITABLE and finished.

A negative result is only as good as its preconditions: physics_torque does
nothing while enable_physics is off, and 3d_shading_density does nothing while
3d_mode is 0. Pass those with --precondition, and the record keeps them, so a
result can be re-read later knowing what it ran under.

THIS PROBE IS FAIL-CLOSED, DELIBERATELY. A row in docs/moho-field-probes.md is
read downstream as a *fact* about the format -- a milestone checker scores a
registry entry against it without re-running anything. So this script never
writes a row unless it actually rendered both variants and compared them:

  - Moho not installed, the document missing, the target key or a
    precondition key not present anywhere in the document, or Moho itself
    failing to render -- ALL of these exit non-zero and write NOTHING to
    docs/moho-field-probes.md. "The probe could not run" and "the probe ran
    and found the field inert" are opposite claims (one says nothing was
    learned, the other says something was measured and it was zero) and must
    never be collapsed into the same "exit 0, no row" shape -- a driver loop
    that cannot run Moho would otherwise read as a stream of confirmed-inert
    fields, and that false census would be trusted precisely because nothing
    about it looks like a failure.
  - A successful measurement -- AFFECTS RENDER or inert -- exits 0 and
    appends exactly one row.

Exit codes: 0 = measured (either outcome); 1 = the key or a precondition is
not present in this document, so nothing was measured -- try another
document; 2 = infrastructure could not run at all (Moho missing/unreadable,
document missing, bad --value/--precondition JSON, Moho itself failed to
render); 3 = the key WAS present but --value is already what every touched
site holds, so the two twins are identical in the one respect the row would
claim they differ -- see the no-op guard below. All non-zero exits write no
row.

BARE-SCALAR TRAP FOR CHANNEL-TYPED FIELDS (M1.5 batch 5 finding). A
`--value` for a `ValChannel`/`BoolChannel`-typed field must be the FULL
`{type, ref, mute, when, val, interp}` channel object, never a bare scalar
(`0.05` in place of the channel dict) -- writing a bare scalar over
`halo_radius` (a `ValChannel`) corrupted the document, Moho's own loader
reporting "Error (108): Unable to load document (corrupt)" at LOAD time, not
a render difference, reproduced twice at two different magnitudes before
concluding it was the shape, not the value, that broke it. This is the same
class of loader intolerance `tools/check_roundtrip.py:32` documents for
`project_data.noise_grain` (a plain int silently written as a bool) --
Moho's own JSON reader is stricter about a field's exact shape than this
tool's --value flag lets a careless caller notice. Not every channel-shaped
field is this strict: a bare boolean and a bare `{r,g,b,a}` dict both loaded
and rendered fine in place of `halo_only`'s `BoolChannel`/`halo_color`'s
`ColorChannel`, so the tolerance is field-shape-specific, not universal --
when in doubt, always pass the full channel object rather than assuming a
bare value is safe.

NO-OP GUARD (fix round 1, Finding A). Presence is not enough: if every site
`--key` touches already holds the exact value being written -- the same JSON
value, or a numerically equal one of a different type, e.g. writing `5` where
`5.0` already sat -- the two twins are byte-identical documents in every way
that matters, both variants would render identically, and a naive harness
would record that as a clean `inert`, indistinguishable from a genuine
negative. Because `inert` PERMANENTLY CLOSES a field's investigation in the
downstream registry, this is the most serious way this tool could lie: a
silent false negative that nothing downstream ever re-opens. So `set_every`
below reports each touched site's PRIOR value, and `main` refuses to render
anything -- exits 3, writes no row -- when the new value is a no-op at every
site. (One differing site among several is a genuine, keepable result: only
a UNANIMOUS no-op is refused.)

CONCURRENCY IS A REQUIREMENT, NOT A NICETY (fix round 1, Finding B). The
design this script implements
(docs/superpowers/specs/2026-08-18-moho-field-coverage-design.md section 6)
prices the ~270-field sweep at "roughly one baseline plus one render per
key... independent probes parallelise across Moho processes" -- i.e. the
sweep's whole time budget assumes many `probe_field.py` invocations run at
once. Every render output path below is therefore unique PER INVOCATION
(pid + a random token), never a fixed `out/probe/base.png`/`var.png` -- two
concurrent probes writing the same literal path would let one process hash
the other's still-being-written or already-overwritten PNG and report a
wrong result with no error raised at all, which is a race, not a crash, and
would never be noticed by whoever ran the sweep.

RESIDUAL RISK THIS TOOL CANNOT CLOSE (fix round 1, Finding C). Nothing here
detects that the layer carrying `--key` was not actually drawn at the chosen
`--frame` -- hidden, `alpha` 0, or the untaken branch of a switch layer all
produce the exact same false-`inert` shape as Finding A: the field changed on
disk, but nothing that reached the canvas could have shown it. A manually
supplied `--frame`/`--document` gives this tool no way to know what SHOULD
have been visible, so this is recorded as a standing residual risk rather
than solved -- an `inert` row is only as trustworthy as the caller's own
choice of a frame where the touched layer(s) actually render. See the same
warning in docs/moho-field-probes.md's own header, where the results live.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mohoedit  # noqa: E402

MOHO = "/Applications/Moho.app/Contents/MacOS/Moho"
RECORD = os.path.join(ROOT, "docs", "moho-field-probes.md")

EXIT_MEASURED = 0
EXIT_CANNOT_APPLY = 1
EXIT_CANNOT_RUN = 2
EXIT_NOOP = 3


def set_every(node, key, value, count=None, old_values=None):
    """Set `key` to `value` on every dict that already has it. Returns the count.

    Only OVERWRITING an existing occurrence counts -- a key never inserted
    where absent, since inserting a field Moho never expected there is a
    different (and untested) experiment from varying one it already reads.
    The returned count is also the evidence a caller uses to tell "the field
    was not touched" from "the field was touched N times": zero must never be
    silently treated as a successful no-op.

    When `old_values` is a list, the PRIOR value at each touched site is
    appended to it before being overwritten -- this is what lets a caller
    distinguish "touched" from "changed": a value that already equals every
    prior value touched nothing meaningful, however many sites it visited.
    See the module docstring's NO-OP GUARD for why that distinction matters.
    """
    if count is None:
        count = [0]
    if isinstance(node, dict):
        if key in node:
            if old_values is not None:
                old_values.append(node[key])
            node[key] = value
            count[0] += 1
        for sub in node.values():
            set_every(sub, key, value, count, old_values)
    elif isinstance(node, list):
        for sub in node:
            set_every(sub, key, value, count, old_values)
    return count[0]


def unique_render_target(outdir, tag):
    """A render output path unique to THIS invocation, never a fixed name.

    See the module docstring's CONCURRENCY note: the sweep this tool serves
    is priced on many invocations running at once, so `out/probe/base.png`
    would let two concurrent probes race on the same file with no error --
    one silently hashes the other's PNG. `uuid4` gives a collision
    probability low enough to ignore without needing filesystem-level
    locking or a pre-created placeholder file (unlike the document twins in
    `make_twin`, nothing here needs to exist before Moho writes to it, so
    there is no analogous mkstemp reservation step).
    """
    token = "%d_%s" % (os.getpid(), uuid.uuid4().hex[:8])
    return os.path.join(outdir, "%s_%s.png" % (tag, token))


def make_twin(src, tag):
    """Reserve an empty temp document path BESIDE `src`, not under out/.

    Moho resolves an ImageLayer's `fileref` relative to the DOCUMENT's own
    directory -- 12 of the 76 corpus documents carry a non-absolute one, and
    an earlier task lost time to exactly this, seeing broken-image
    placeholders instead of a real render difference, after writing its twin
    under out/. Writing the twin next to the source keeps every relative
    asset reference resolvable exactly as it was for the original file. The
    alternative -- rewriting every relative fileref to absolute before
    writing the twin -- was rejected: it would touch a field this task is not
    scoped to decode, on every probed document, purely as a side effect of
    where the file happens to sit on disk. The transient file is removed by
    the caller's `finally` block, so nothing is left in the corpus directory
    after the probe finishes, success or failure.
    """
    ext = os.path.splitext(src)[1]
    srcdir = os.path.dirname(os.path.abspath(src)) or "."
    fd, path = tempfile.mkstemp(prefix=".probe_%s_" % tag, suffix=ext, dir=srcdir)
    os.close(fd)
    return path


def render(path, frame, out):
    """Render one frame of `path` to a PNG; return (sha256 of the bytes, actual path).

    Moho does not write to the exact name passed to `-o`: for `-o OUT.png` it
    writes `OUT_00025.png` (frame number, zero-padded to 5 digits, spliced in
    before the extension) -- confirmed empirically before this function was
    written, not assumed from the brief. Both the derived and the literal name
    are checked for, in that order, so a future Moho version that changes this
    convention fails loudly (`RuntimeError` below) instead of silently hashing
    a stale or missing file.

    Byte-for-byte SHA-256 comparison, not a fuzzy image diff, is sound
    evidence here because Moho's PNG output is deterministic across separate
    process invocations -- confirmed by rendering the same document/frame
    twice in independent processes and finding the two PNGs byte-identical
    (see docs/moho-field-probes.md's own header for the reproduction). That is
    what licenses treating any byte difference as a real render difference and
    zero difference as a real absence of one, with no perceptual-similarity
    threshold to tune and no dependency on Pillow (optional in this repo, and
    must stay optional) or any other image library.

    Raises `subprocess.CalledProcessError` (Moho exited non-zero) or
    `RuntimeError` (Moho exited zero but produced neither expected filename)
    on failure. Both are "could not measure", not "measured no difference",
    and the caller must treat them that way -- see the module docstring.
    """
    subprocess.run([MOHO, "-r", path, "-f", "PNG",
                    "-start", str(frame), "-end", str(frame), "-o", out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stem, ext = os.path.splitext(out)
    produced = "%s_%05d%s" % (stem, frame, ext)
    target = produced if os.path.exists(produced) else out
    if not os.path.exists(target):
        raise RuntimeError("Moho exited 0 but produced neither %s nor %s" % (produced, out))
    with open(target, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest(), target


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", required=True, help="new value as JSON, e.g. 1 or true or '\"x\"'")
    ap.add_argument("--document", required=True)
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--precondition", action="append", default=[],
                    metavar="KEY=JSON", help="set first; repeatable")
    args = ap.parse_args()

    # RULING: the brief this harness was drafted from exited 0 here ("SKIP:
    # Moho is not installed"). That is fabrication, not caution -- a driver
    # loop reading "exit 0, no row appended, no delta" cannot tell that from
    # "ran cleanly and found nothing", and would misfile an unmeasured field
    # as decoded-and-inert forever. See the module docstring's exit-code
    # table: this is EXIT_CANNOT_RUN, not EXIT_MEASURED, and no row follows.
    if not os.path.exists(MOHO):
        sys.stderr.write(
            "CANNOT-RUN: Moho is not installed at %s - no probe performed, "
            "no row written\n" % MOHO)
        return EXIT_CANNOT_RUN

    src = args.document if os.path.isabs(args.document) else os.path.join(ROOT, args.document)
    if not os.path.exists(src):
        sys.stderr.write("CANNOT-RUN: document not found: %s - no row written\n" % src)
        return EXIT_CANNOT_RUN

    pre = [p.split("=", 1) for p in args.precondition]
    try:
        value = json.loads(args.value)
        pre_values = [(k, json.loads(v)) for k, v in pre]
    except json.JSONDecodeError as exc:
        sys.stderr.write("CANNOT-RUN: --value/--precondition is not valid JSON (%s) - "
                          "no row written\n" % exc)
        return EXIT_CANNOT_RUN

    outdir = os.path.join(ROOT, "out", "probe")
    os.makedirs(outdir, exist_ok=True)

    cleanup = []  # every transient path this run creates, removed in `finally` below
    try:
        raw, container = mohoedit.read_document(src)
        pre_counts = {k: set_every(raw, k, v) for k, v in pre_values}
        missing_pre = [k for k, c in pre_counts.items() if c == 0]
        if missing_pre:
            # A precondition that touches nothing does not "hold vacuously" --
            # it means the variant below is not actually running under the
            # precondition the row would claim, so nothing is measured.
            sys.stderr.write(
                "FAIL: precondition key(s) %s not present in %s - no probe "
                "performed, no row written\n" % (", ".join(missing_pre), args.document))
            return EXIT_CANNOT_APPLY

        base = make_twin(src, "base")
        cleanup.append(base)
        mohoedit.write_document(base, raw, container)

        raw2, container2 = mohoedit.read_document(src)
        for k, v in pre_values:
            set_every(raw2, k, v)
        old_values = []
        touched = set_every(raw2, args.key, value, old_values=old_values)
        if touched == 0:
            sys.stderr.write(
                "FAIL: %s is not present in %s - pick another document, "
                "no row written\n" % (args.key, args.document))
            return EXIT_CANNOT_APPLY
        if all(old == value for old in old_values):
            # Finding A: presence alone proves nothing. Every site already
            # held this exact value (or one numerically equal to it), so the
            # two twins about to be rendered are identical in the one respect
            # the row would claim they differ -- rendering them would produce
            # a clean, silent, PERMANENT false `inert`. Refuse instead.
            sys.stderr.write(
                "NOOP: %s already equals %r at all %d site(s) in %s - the "
                "probe would measure nothing, no row written; pick a value "
                "that actually differs from what is already there\n"
                % (args.key, value, touched, args.document))
            return EXIT_NOOP

        var = make_twin(src, "var")
        cleanup.append(var)
        mohoedit.write_document(var, raw2, container2)

        base_png = unique_render_target(outdir, "base")
        var_png = unique_render_target(outdir, "var")
        try:
            base_hash, base_target = render(base, args.frame, base_png)
            cleanup.append(base_target)
            var_hash, var_target = render(var, args.frame, var_png)
            cleanup.append(var_target)
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            sys.stderr.write("CANNOT-RUN: Moho render failed (%s) - no row written\n" % exc)
            return EXIT_CANNOT_RUN
    finally:
        # Every twin document AND every rendered PNG this run produced is
        # removed unconditionally, on every exit path (including every
        # `return` above), so a failed OR successful probe never leaves a
        # stray file in the corpus directory, and out/probe/ does not grow
        # without bound across a few-hundred-key sweep.
        for path in cleanup:
            if path and os.path.exists(path):
                os.remove(path)

    affects = base_hash != var_hash

    line = ("| `%s` | `%s` | %d | %s | %d | %s | %s |\n"
            % (args.key, args.value, touched, os.path.basename(args.document), args.frame,
               ", ".join("`%s=%s` x%d" % (k, v, pre_counts[k]) for k, v in pre) or "none",
               "**AFFECTS RENDER**" if affects else "inert"))
    if not os.path.exists(RECORD):
        with open(RECORD, "w") as fh:
            fh.write(
                "# Moho field probes\n\n"
                "One row per FIELD THAT WAS ACTUALLY MEASURED, produced by\n"
                "`tools/probe_field.py`. See that script's own module docstring for the\n"
                "full method and its fail-closed exit codes; the summary that matters here:\n\n"
                "**What a row means.** The named document was rendered twice with `Moho -r\n"
                "... -f PNG` (headless, deterministic -- the same document/frame rendered in\n"
                "two separate Moho processes produced byte-identical PNGs, which is what\n"
                "licenses a plain SHA-256 comparison as sound evidence here, with no fuzzy\n"
                "image diff and no Pillow dependency): once unmodified, once with `Field`\n"
                "changed to `Value tried` at every place it occurs in the document (and any\n"
                "listed precondition applied to both first). `AFFECTS RENDER` means the PNG\n"
                "bytes differed; `inert` means they were byte-identical. Both are recorded --\n"
                "an inert result is exactly as final as a positive one; see\n"
                "`docs/superpowers/specs/2026-08-18-moho-field-coverage-design.md` section 6.\n\n"
                "**What a row does NOT mean.** It is not a claim about the field's semantics\n"
                "(what the value MEANS), only whether varying it changes pixels, at ONE frame\n"
                "of ONE document, under the stated preconditions (`none` means no precondition\n"
                "was applied -- a field gated behind one can still show `inert` here and be\n"
                "correctly editable, e.g. behind `enable_physics` or `3d_mode`). A row is not\n"
                "re-derived automatically if `moho2svg.py`'s reading model changes later --\n"
                "the field-coverage registry cites the row as evidence at the time it was\n"
                "written. No row is ever written for a probe that could not run, nor when the\n"
                "value tried is a no-op (already what every touched site held) -- see the\n"
                "script's own module docstring for the full exit-code table -- so every row\n"
                "below is a completed, meaningful measurement. `Sites` is the touched-site\n"
                "count for `Field` itself (mirroring the count already shown per precondition):\n"
                "an `inert` result over 124 sites is strong evidence, over 1 site much weaker,\n"
                "and this column is what lets a later reader tell those apart without re-running\n"
                "anything.\n\n"
                "**A residual risk no row here can rule out.** Nothing in this pipeline\n"
                "confirms that the layer carrying `Field` was actually DRAWN at `Frame` --\n"
                "hidden, `alpha` 0, or the untaken branch of a switch layer all produce the\n"
                "same false `inert` shape as a genuine negative, because the changed field\n"
                "never reached the canvas either way. Every `inert` row below is only as\n"
                "trustworthy as its `Document`/`Frame` choice having actually exercised the\n"
                "field -- this is recorded as a standing risk, not solved, since a manually\n"
                "chosen frame gives the tool no way to know what should have been visible.\n\n"
                "| Field | Value tried | Sites | Document | Frame | Preconditions | Result |\n"
                "|---|---|---|---|---|---|---|\n")
    with open(RECORD, "a") as fh:
        fh.write(line)
    print("%s: %s (%d site%s changed)" % (
        args.key, "AFFECTS RENDER" if affects else "inert", touched, "" if touched == 1 else "s"))
    return EXIT_MEASURED


if __name__ == "__main__":
    sys.exit(main())
