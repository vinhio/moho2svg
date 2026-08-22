#!/usr/bin/env python3
"""Surgical (JSON-path, not flat-key) render-diff probe.

`tools/probe_field.py` varies every occurrence of a literal key NAME across
the whole document tree (`set_every`). That is the right tool for a
single-owner field, but several M1.5 batch 7 keys are declared under TWO
schema owners that share one flat name (`depth_sort`/`distance_sort`
under both ProjectData and LayerContainer; `metadata` under both the
document root and LayerCommon; `timeline_markers` under both AnimatedValues
and LayerCommon) - set_every cannot vary one owner without also touching
the other, which would confound the two into one untrustworthy result.

This module implements the SAME evidence method `probe_field.py` uses -
render the same document twice with Moho's own headless CLI, byte-diff the
PNGs (Moho's PNG output is deterministic across separate process
invocations - see `probe_field.py`'s own docstring for the reproduction),
except the caller supplies an arbitrary `mutate_fn(raw_dict)` that edits
the raw JSON however precisely it needs to (by exact path, or by any
predicate finer than "every dict with this key"), instead of a flat
key/value pair. See `docs/moho-field-probes.md`'s own header for what a
measurement here does and does not mean - the same caveats apply.

Usage as a library (no CLI - every call site's mutate_fn is bespoke enough
that a generic command-line surface would not save anything over a short
inline script):

    import path_probe
    def mutate(raw):
        raw["project_data"]["depth_sort"] = True
    base_hash, var_hash = path_probe.probe("moho/Bandit.mohoproj", 25, mutate, "proj_depth")
    # base_hash != var_hash  ->  AFFECTS RENDER

Every temp document twin and rendered PNG this module creates is removed
unconditionally in a `finally` block, on every exit path - the same
no-stray-files guarantee `probe_field.py` gives, checked after each M1.5
batch by `find moho -name ".probe_*"` / `find out/probe -type f`.
"""
import hashlib
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mohoedit  # noqa: E402

MOHO = "/Applications/Moho.app/Contents/MacOS/Moho"


def render(path, frame, out):
    """Render one frame of `path` to a PNG; return (sha256 of the bytes, actual path).

    Same Moho-output-naming handling as probe_field.py's own `render`: Moho
    writes `OUT_00025.png` (zero-padded frame number spliced before the
    extension), not the literal `-o` argument.
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


def probe(document, frame, mutate_fn, tag):
    """Render `document` twice at `frame` - once unmodified, once after
    `mutate_fn(raw)` edits the parsed JSON in place - and return
    (base_sha256, var_sha256). Equal hashes mean inert; unequal means the
    mutation AFFECTS RENDER.

    The twin document is written BESIDE `document` (mohoedit's own
    `make_twin` docstring precedent - see probe_field.py), not under out/,
    so any relative asset reference in the source document keeps resolving
    exactly as it did for the original file.
    """
    src = document if os.path.isabs(document) else os.path.join(ROOT, document)
    srcdir = os.path.dirname(src)
    cleanup = []
    try:
        raw, container = mohoedit.read_document(src)
        fd, base_doc = tempfile.mkstemp(prefix=".probe_%s_base_" % tag,
                                         suffix=os.path.splitext(src)[1], dir=srcdir)
        os.close(fd)
        cleanup.append(base_doc)
        mohoedit.write_document(base_doc, raw, container)

        raw2, container2 = mohoedit.read_document(src)
        mutate_fn(raw2)
        fd, var_doc = tempfile.mkstemp(prefix=".probe_%s_var_" % tag,
                                        suffix=os.path.splitext(src)[1], dir=srcdir)
        os.close(fd)
        cleanup.append(var_doc)
        mohoedit.write_document(var_doc, raw2, container2)

        outdir = os.path.join(ROOT, "out", "probe")
        os.makedirs(outdir, exist_ok=True)
        base_png = os.path.join(outdir, "%s_base_%d.png" % (tag, os.getpid()))
        var_png = os.path.join(outdir, "%s_var_%d.png" % (tag, os.getpid()))
        base_hash, base_target = render(base_doc, frame, base_png)
        cleanup.append(base_target)
        var_hash, var_target = render(var_doc, frame, var_png)
        cleanup.append(var_target)
        return base_hash, var_hash
    finally:
        for p in cleanup:
            if p and os.path.exists(p):
                os.remove(p)
