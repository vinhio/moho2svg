#!/usr/bin/env python3
"""Record which JSON keys the exporters actually read.

Coverage was previously estimated by searching each key as a quoted string
literal in the Python sources. That miscounts in both directions: a literal can
sit in a comment while nothing reads the value, and channel keys (`when`,
`val`, `interp`, `actions`) are consumed through variables so they never appear
as literals at the point of use. A target of 95% cannot rest on an instrument
with unquantified error in both directions.

This wraps every dict in the parsed tree in a mapping that records each key
lookup, then runs both exporters over all 76 documents at each document's own
start/mid/end frame (see `frames_for`). A key never recorded is provably
unread.

Deliberately records key NAMES, not paths: the registry in schema/ is keyed by
property name, and a path-keyed trace could not be joined to it.

Also records `call_sites`: {key: "file.py:LINE in function"}, the FIRST real
call frame that read each key (see `_record`). Task 8's registry requires a
MODELLED key's evidence to name "the consuming code path plus the trace
artifact" - this is what supplies the code-path half automatically and
verifiably, instead of a hand-typed guess at which line probably reads a
given field.

The output also records the environment the trace ran in (optional
dependencies importable, interpreter path) and the settings/frames used per
document, because this measurement's VALUE depends on that environment - the
ImageLayer/PSD branch is only reached when Pillow and psd-tools are
importable, so a trace re-run without them legitimately finds one fewer key
(`image_fileref`). A consumer that does not know which environment produced a
given `out/traced_keys.json` cannot tell that apart from a real regression,
and the natural (wrong) response to the false alarm is to "fix" the registry
entry that triggered it, corrupting the very measurement this script exists
to make trustworthy.
"""

import argparse
import dataclasses
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import mohoedit  # noqa: E402

SEEN = set()

# One representative call site per key: {key: "path.py:LINE in function"}.
# Task 8's checker (tools/check_field_coverage.py) needs a MODELLED key's
# evidence to name "the consuming code path plus the trace artifact" -- doing
# that by hand for 140+ keys would mean either skipping the pointer (weak
# evidence, the exact failure mode the rule exists to catch) or writing one
# description per key from memory (unverifiable, and this repository does not
# trust unverified narration - see AGENTS.md). Recording the real call frame
# the first time a key is read is strictly stronger than either: it names the
# ACTUAL line that consumed the key, on THIS run, not a guess about which line
# probably did.
CALL_SITES: dict = {}


def _record(key) -> None:
    """Note that `key` was read, and (the first time) where from.

    Only the FIRST call site is kept: the call site is a property of the
    CODE, not of which document happened to be open when it first fired, so a
    later sighting of the same key adds no new information. `sys._getframe(2)`
    skips this function's own frame and the TracingDict method that called it
    (__getitem__/get/__contains__), landing on the real caller inside
    moho2svg.py or moho2lottie.py.
    """
    SEEN.add(key)
    if key not in CALL_SITES:
        frame = sys._getframe(2)
        code = frame.f_code
        name = getattr(code, "co_qualname", code.co_name)  # co_qualname needs 3.11+
        CALL_SITES[key] = "%s:%d in %s" % (os.path.relpath(code.co_filename, ROOT), frame.f_lineno, name)


class TracingDict(dict):
    """A dict that records every key looked up, including failed lookups.

    Failed lookups count: `raw.get("fixed_angle", False)` on a document that
    omits the key still proves the exporter consumes that field. Subclassing
    dict rather than wrapping keeps `isinstance(x, dict)` true throughout
    moho2svg.py, which tests for it in many places.
    """

    def __getitem__(self, key):
        _record(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        _record(key)
        return super().get(key, default)

    def __contains__(self, key):
        _record(key)
        return super().__contains__(key)


def instrument(node):
    """Rebuild the tree with every dict replaced by a TracingDict.

    Built ONCE per document and reused across every (frame, exporter) run for
    that document: the tree's own content never changes (both exporters are
    already checked, by check_no_raw_mutation.py, not to mutate the raw
    tree), so re-wrapping it for each run would only cost time, not accuracy.
    A fresh `Document.from_raw` is still built per run (see `main`), which is
    what actually resets per-document state (`Channel.reset_cache()`).
    """
    if isinstance(node, dict):
        return TracingDict((k, instrument(v)) for k, v in node.items())
    if isinstance(node, list):
        return [instrument(v) for v in node]
    return node


def frames_for(document) -> list:
    """Three frames to trace for `document`: its own start, midpoint and end
    frame, read from `project_data.start_frame`/`end_frame`.

    A single fixed frame (frame 0) under-counts in two ways that only
    surfaced once the trace was checked against a real field registry:

    - a SWITCH layer's inactive children are never walked at any one frame,
      so a key reached only through a branch that is not the active one at
      that frame goes unread;
    - `Channel._segment` dispatches per KEYFRAME SEGMENT (Linear/Smooth/Step/
      Pose/etc. each have their own decode path), so a field read only on a
      Pose or Step segment can go unseen simply because frame 0 happens to
      fall inside a Linear or Smooth segment instead.

    Spanning the document's own declared range does not guarantee hitting
    every branch or every segment kind, but every document in the corpus
    already animates across that range, so it is a large, close-to-free
    improvement over one arbitrary frame, and it stays anchored to frames the
    DOCUMENT ITSELF considers "in range" rather than a frame this script
    invented. `start`/`end` are read per document because the corpus's own
    ranges differ - assuming a fixed range (e.g. always 0..100) would silently
    under- or over-shoot on documents whose own range does not match it.
    """
    start = int(document.start_frame)
    end = int(document.end_frame)
    if start == end:
        return [start]
    lo, hi = (start, end) if start <= end else (end, start)
    mid = (lo + hi) // 2
    return sorted({start, mid, end})


def environment_fingerprint(moho2svg, moho2lottie) -> dict:
    """What this run's environment can and cannot exercise.

    `image_fileref` (and the whole ImageLayer/PSD branch) is only read when
    Pillow AND psd-tools are importable; pyclipper gates moho2lottie's
    combo_mode==3 pre-clipping branch. A trace's key COUNT is therefore a
    function of what was installed when it ran, not just of the corpus and
    the code - recording that here is what lets a consumer of
    `out/traced_keys.json` tell "this environment could not reach that
    branch" apart from "the exporter regressed and stopped reading this key".
    """
    return {
        "python": sys.executable,
        "pillow": moho2svg.Image is not None,
        "psd_tools": moho2svg.PSDImage is not None,
        "pyclipper": moho2lottie.pyclipper is not None,
    }


def _json_safe(value):
    """Convert a RenderSettings field to something json.dump can write.

    Only `forced_mask_containers` (a `frozenset[str]`) needs this; every
    other field is already a plain int/float/str/bool/None.
    """
    if isinstance(value, (frozenset, set)):
        return sorted(value)
    return value


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "traced_keys.json"))
    args = ap.parse_args()

    import moho2svg
    import moho2lottie

    started = time.perf_counter()
    docs = 0
    errors = []
    frames_by_document = {}
    for path in mohoedit.iter_documents():
        rel = os.path.relpath(path, ROOT)
        try:
            raw, _ = mohoedit.read_document(path)
        except Exception as exc:  # noqa: BLE001
            # A single unparseable document must cost this run 1 of 76
            # documents, not the whole trace - every other document's keys
            # are still real evidence even if this one cannot be read at all.
            errors.append("%s [read] %s" % (rel, repr(exc)[:90]))
            docs += 1
            continue

        instrumented = instrument(raw)
        try:
            frames = frames_for(moho2svg.Document.from_raw(instrumented))
        except Exception as exc:  # noqa: BLE001
            errors.append("%s [frames] %s" % (rel, repr(exc)[:90]))
            frames = [0]
        frames_by_document[rel] = frames

        for frame in frames:
            for label, run in (
                # export_document's 2nd/3rd/4th params are crop/nested_groups/
                # include_hidden, not a frame range -- a plain positional
                # frame is correct here.
                ("svg", lambda d, f=frame: moho2svg.Exporter(
                    d, moho2svg.RenderSettings()).export_document(f)),
                # LottieExporter.export takes (frames, include_hidden); its
                # 2nd positional parameter is NOT a second frame. `frames`
                # must be a sequence -- [f], matching moho2lottie.py's own
                # CLI and tools/check_lottie_geometry.py. include_hidden
                # stays at its default False: the trace must stay faithful
                # to what a DEFAULT export reads, and multi-frame already
                # crosses switch branches and interpolation segments without
                # needing to force hidden layers on too.
                ("lottie", lambda d, f=frame: moho2lottie.LottieExporter(
                    d, moho2lottie.RenderSettings()).export([f])),
            ):
                try:
                    run(moho2svg.Document.from_raw(instrumented))
                except Exception as exc:  # noqa: BLE001
                    errors.append("%s [%s @ frame %d] %s" % (rel, label, frame, repr(exc)[:90]))
        docs += 1

    elapsed = time.perf_counter() - started
    settings_dict = {k: _json_safe(v) for k, v in
                     dataclasses.asdict(moho2svg.RenderSettings()).items()}

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({
            "keys": sorted(SEEN),
            "documents": docs,
            "errors": errors,
            "environment": environment_fingerprint(moho2svg, moho2lottie),
            "settings": {"render_settings": settings_dict, "include_hidden": False},
            "frames_by_document": frames_by_document,
            "call_sites": CALL_SITES,
        }, fh, indent=1)
    print("traced %d documents, %d keys read, %d export errors, %.1fs"
          % (docs, len(SEEN), len(errors), elapsed))
    for line in errors[:10]:
        print("   ERROR %s" % line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
