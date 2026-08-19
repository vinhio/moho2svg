#!/usr/bin/env python3
"""Editing side of the Moho document format: container I/O, save, integrity.

`moho2svg.py` reads a document to draw it; this module reads one to CHANGE it.
The split is deliberate. The reading model there is calibrated against Moho's
own renders and must not be duplicated, while renumbering, validation and
saving are new responsibilities -- and `moho2svg.py` is already over 9,500
lines.

A `.moho` file is a plain ZIP holding `Project.mohoproj` and optionally
`preview.jpg` -- confirmed against all 30 archives in the corpus, and
documented in Moho's own manual, Appendix F. `.mohoproj` / `.animeproj` are
the same JSON, bare. Both are read here and written back in the same shape,
because handing a user a bare .mohoproj when they gave you a .moho makes them
re-zip it by hand.
"""

import dataclasses
import json
import os
import sys
import typing
import zipfile

PROJECT_MEMBER_SUFFIX = ".mohoproj"

# The three extensions a corpus document can carry -- a bare project
# (`.mohoproj`/`.animeproj`) or a zipped one (`.moho`, see `read_document`).
CORPUS_EXTENSIONS = (".mohoproj", ".animeproj", ".moho")

# This file's own directory is the repository root (mohoedit.py lives there,
# not under tools/), so `moho/` sits right beside it -- the same path every
# caller of `iter_documents` used to compute by hand as
# `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` from
# tools/whatever.py.
_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def iter_documents(moho_dir: typing.Optional[str] = None) -> typing.Iterator[str]:
    """Yield every corpus document under `moho_dir` (default: this repo's own
    gitignored `moho/`), in a fully sorted, deterministic order.

    Sorted by the complete joined path (`sorted(...)` over every match found
    anywhere in the tree), not merely within each directory -- `os.walk`
    itself makes no promise about the ORDER it visits sibling directories in
    (it follows whatever the OS's directory listing returns, which is not
    guaranteed alphabetical), and every one of the four call sites this
    replaces used to wrap its own copy in `sorted(...)` for exactly that
    reason. Matching that here, inside the helper, means a caller no longer
    has to remember to re-sort -- and every one of them still produces
    byte-identical output/ordering to before this consolidation.

    This walk -- `os.walk` plus the three-extension filter above -- used to
    be copy-pasted near-identically into four places: `tools/trace_fields.py`,
    `tools/check_integrity.py`, `tools/check_roundtrip.py`, and inlined a
    fourth time inside `tools/check_field_coverage.py`'s census builder. All
    four agreed on every corpus this repository has ever tested against, so
    this was not a correctness bug -- but this whole suite of gates has
    exactly one purpose, several independent checks agreeing that the corpus
    is sound, and that purpose depends on "the corpus" meaning the same 76
    documents to every one of them. Four copies is four places the next
    change to what counts as "the corpus" (a new extension, a new excluded
    subdirectory) has to be made identically, silently, with nothing to
    notice a missed one -- exactly the situation `trace_fields.py` was
    already in once: an earlier revision of ITS OWN copy excluded
    `moho/track/` (Moho's own reference frame sets, see
    `tools/check_reference_frames.py`), which cost it real evidence before
    the filter was deliberately removed. `moho/track/` holds no
    `.mohoproj`/`.animeproj`/`.moho` files of its own (only rendered
    `.svg`/`.png` reference frames), so the extension filter here already
    excludes everything in it without a second, separate directory-name
    rule to keep in sync -- adding one back would only recreate the same
    trap for no documents actually excluded.

    Every one of this function's four callers asserts, separately, that it
    walked at least 76 documents (`EXPECTED_DOCUMENTS` in `check_integrity.py`/
    `check_roundtrip.py`, the census/trace document counts in
    `check_field_coverage.py`/`trace_fields.py`) -- consolidating the WALK
    here does not consolidate that assertion, on purpose: each gate's own
    "did I verify anything real" check stays next to its own reporting, so a
    future gate added on top of this helper does not silently inherit an
    exemption from that doctrine by omission.

    DOT-PREFIXED FILENAMES ARE EXCLUDED (M1.4a fix round 1). No legitimate
    corpus document is ever dot-prefixed. This guard exists because
    `tools/probe_field.py`'s `make_twin()` deliberately writes its temp twin
    document BESIDE the real one it is probing (`.probe_<tag>_<random>...`,
    see that function's own docstring for why -- relative `ImageLayer`
    filerefs need to resolve against the real document's directory), cleaned
    up in a `finally` block on every normal exit path. A hard kill
    (`SIGKILL`) of that process skips the `finally` block entirely, so a
    stray `.probe_*.mohoproj` can survive in `moho/` and would otherwise be
    silently walked here as if it were a real corpus document -- exactly
    what happened once already (a killed orchestration run left two such
    files behind, inflating this function's own count from 76 to 78 and
    corrupting one `make check-lottie`/`check-roundtrip` pass before it was
    caught by eye, not by any gate). The same guard incidentally also
    excludes macOS AppleDouble shadow files (`._Name.mohoproj`), a second,
    independent reason to exclude anything dot-prefixed.
    """
    if moho_dir is None:
        moho_dir = os.path.join(_REPO_ROOT, "moho")
    found = []
    for dirpath, _dirnames, filenames in os.walk(moho_dir):
        for fn in filenames:
            if fn.startswith("."):
                continue
            if fn.endswith(CORPUS_EXTENSIONS):
                found.append(os.path.join(dirpath, fn))
    yield from sorted(found)


@dataclasses.dataclass
class Container:
    """How a document was packaged, so it can be written back the same way.

    `extras` holds every archive member that is not the project JSON -- in
    practice `preview.jpg`, the thumbnail Windows Explorer and macOS QuickLook
    show. It is carried verbatim rather than regenerated: regenerating needs a
    render, and a wrong thumbnail is worse than a stale one. Appendix F states
    Moho recreates it on its next save anyway.
    """

    kind: str                                  # "json" or "zip"
    member: typing.Optional[str] = None        # archive member holding the JSON
    extras: typing.Dict[str, bytes] = dataclasses.field(default_factory=dict)


def read_document(path: str) -> typing.Tuple[dict, Container]:
    """Parse a Moho document, bare or archived, and report its packaging.

    Dispatch is on the file extension rather than sniffing the bytes (e.g. a
    leading ZIP magic number): a `.moho` file that somehow held bare JSON, or
    a `.mohoproj` that somehow held a ZIP, would be a corrupt file either way,
    and the extension is what both Moho itself and this repo's own corpus
    layout use to distinguish the two packagings -- see
    `docs/moho-project-file-format.md`.

    Decoding is STRICT UTF-8 in both branches (no `errors="replace"`), and
    this is a deliberate policy specific to THIS module, not merely a match
    to `moho2svg.load_document`'s old default. `moho2svg.py` only ever reads
    a document to draw it once and discard the in-memory copy, so a
    substituted character there is a cosmetic risk at worst. This module
    reads a document to change and SAVE it -- a `write_document` (Task 4)
    call downstream would write any substituted U+FFFD right back into the
    user's file, turning one lenient read into permanent, silent data loss.
    There is also no accuracy trade-off to weigh here: all 76 corpus
    documents (46 bare, 30 archived) were measured to decode under strict
    UTF-8 with zero failures, so strictness costs nothing on real data and
    only ever fires on a document that was already corrupt.
    """
    if path.endswith(".moho"):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            candidates = [n for n in names if n.endswith(PROJECT_MEMBER_SUFFIX)]
            if not candidates:
                raise ValueError("no %s member in %s (has %s)"
                                 % (PROJECT_MEMBER_SUFFIX, path, names))
            member = candidates[0]
            if len(candidates) > 1:
                # Every one of the 30 corpus archives holds exactly one
                # member, so silently picking `namelist()` order is untested
                # against a real multi-member archive -- warn rather than
                # guess quietly, matching how moho2svg.py flags every other
                # under-evidenced fallback (e.g. its combo_mode/blend_mode
                # "unknown value, drawn/handled as-is" warnings).
                sys.stderr.write(
                    "  ! archive %s: %d %s members found, using %r, "
                    "ignoring %s\n"
                    % (path, len(candidates), PROJECT_MEMBER_SUFFIX, member,
                       [n for n in candidates if n != member]))
            raw = json.loads(archive.read(member).decode("utf-8"))
            extras = {n: archive.read(n) for n in names if n != member}
        return raw, Container(kind="zip", member=member, extras=extras)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle), Container(kind="json")


def write_document(path: str, raw: dict, container: Container,
                    keep_preview: bool = True) -> None:
    """Write a document back in the packaging described by `container`.

    `container` is the value `read_document` returned for this document (or
    an equivalent one an editing task built itself): `kind == "json"` writes
    a bare `.mohoproj`/`.animeproj`; `kind == "zip"` rebuilds a `.moho`
    archive holding the project member plus, unless `keep_preview=False`,
    every entry of `container.extras` byte-for-byte -- so an edit that never
    touches `preview.jpg` does not perturb it, and the caller does not need
    to know that member's name or content to preserve it.

    Byte-identical text is deliberately NOT a goal, and must not become one:
    no stdlib `json.dumps` preset reproduces Moho's own formatting -- Moho
    itself writes `indent=2` in format 1045 and fully minified JSON in 1038,
    and its float formatting differs from Python's either way -- so matching
    it exactly is not achievable without hand-rolling Moho's own serializer.
    What matters instead is that MOHO RE-READS THE RESULT: an unedited
    load-and-save of `TransformBoneTool.animeproj` was confirmed to open in
    Moho 14.4 and render frame 12 pixel-identically to the original (0 of
    921,600 pixels changed). `indent=2` is chosen over a minified dump
    because it makes a diff between two saved revisions readable, which
    matters far more here than matching Moho's own whitespace.

    Encoding is strict UTF-8 with `ensure_ascii=False`, matching
    `read_document`'s own strict-UTF-8 policy: a document read strictly is
    written back with every non-ASCII layer/document name intact rather than
    escaped to `\\uXXXX` (which Moho itself does not write and which would
    make every such name unrecognizable in a plain-text diff).

    `keep_preview=False` omits `container.extras` entirely, so a saved
    archive carries no stale thumbnail rather than a misleading one -- Moho
    regenerates `preview.jpg` on its own next save (Appendix F).
    """
    text = json.dumps(raw, indent=2, ensure_ascii=False)
    if container.kind == "json":
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return
    member = container.member or "Project" + PROJECT_MEMBER_SUFFIX
    # ZIP_DEFLATED, not ZIP_STORED: Appendix F notes the compression is the
    # whole point of the container ("250 MB down to about 4 MB"), and Moho's
    # own manual asks third-party tools for the most portable zip form.
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, text.encode("utf-8"))
        if keep_preview:
            for name, blob in container.extras.items():
                archive.writestr(name, blob)


def check_integrity(raw: dict) -> typing.List[str]:
    """Report every broken cross-reference in a document, one message each.

    A Moho mesh is held together almost entirely by POSITIONAL INDICES, and
    the format has exactly one allocator (`mesh.next_shape_id`, for shape ids
    only) and no generation counter anywhere. Removing one entry from
    `mesh.points` invalidates every `curve.points[].point` above it and every
    `mesh.groups[].points` entry, with nothing to detect the staleness -- so
    an editor that renumbers wrongly produces a file that still loads and is
    quietly wrong. This function is the gate against that, for the six
    reference classes measured clean across the full 76-document corpus:

    1. `curve.points[i].point` in `range(len(mesh.points))`.
    2. `shape.edges.curve[i]` in `range(len(mesh.curves))`.
    3. `shape.edges.segment[i]` in that curve's own segment count
       (`len(points)` when the curve is closed, else `len(points) - 1`).
    4. `mesh.groups[].points[i]` in `range(len(mesh.points))`.
    5. `bone.parent` in `range(len(bones))` of ITS OWN skeleton, or `-1`.
    6. `target_layer_uuid` / `follow_layer_uuid` / `distortion_layer_uuid`
       each naming an actual LAYER that exists somewhere in this document
       (not merely some uuid-bearing node -- see `collect_layer_uuids` below).

    Rules 1-4 also reach a `TextLayer`'s own glyph geometry, which does not
    live at that layer's own top level: `moho2svg.py`'s `Layer._build`
    documents that a `TextLayer`'s mesh is one level down, under its own
    `mesh_layer` field (a complete, nested `MeshLayer`-shaped object), and
    synthesises it as that layer's one child for exactly this reason. This
    function descends into the same `mesh_layer` field the same way, for the
    same reason -- 46 `TextLayer` instances across 26 of the 76 corpus
    documents carry one, together holding 1,711 curves that would otherwise
    be invisible to every rule here while the checker still reported clean.
    A violation inside one is reported at a path ending in
    `.../mesh_layer mesh ...`, so it is never mistaken for the parent
    TextLayer's own (nonexistent) top-level mesh.

    Four related reference classes are deliberately EXCLUDED, and the
    exclusion is a finding about this repository's own model of the format,
    not a claim that these fields don't matter:

    - `layer.parent_bone` and `mesh.points[].parent` are documented as
      indexing "the ancestor skeleton's bones", but measuring that rule
      naively (nearest-ancestor `BoneLayer`) across the corpus produces 73
      `parent_bone` violations across 24 documents, where the offending
      values are consistently and systematically LARGER than the found
      skeleton's own bone count (e.g. 17 vs. a skeleton of 0..9 bones) --
      that is the signature of indexing some OTHER space, not of real
      corruption. The companion field `mesh.points[].parent` shares that same
      index space and was measured too: 17 violations, but confined to a
      single document (`ReparentBone.animeproj`, which is exactly the sample
      built to exercise re-parenting bone tools) -- consistent with the same
      "wrong assumed space" explanation, not 17 independent breakages.
    - `flexi_bone_subset` also shares `parent_bone`'s index space (it names a
      subset of the same list); measured naively it produces exactly 1
      violation, confined to that same document.
    - `switch_keys` values are meant to name a switch layer's own children by
      `name`, but exact-string matching against immediate children measures
      1,167 violations across 9 documents -- far too concentrated and too
      large relative to those documents' own switch layers to be 1,167 real
      dangling references; the matching rule itself (case folding? matching
      by uuid instead of the current display name? a rename history Moho
      itself tolerates?) is not yet understood.

    All four are handed to milestone M2.1 (bones) and M2's switch-layer work,
    where they get decoded properly against Moho itself rather than guessed
    at here -- a checker that fires on 29 of 76 known-good documents is worse
    than no checker, because the only way to keep using it is to disable
    rules, and a disabled rule reads identically to a passing one to anyone
    downstream. The channel-level `actions[].name` coupling (every pose name
    a Smart Bone dial references must exist in some layer's `actions`
    registry) is excluded for a different reason: it needs a full-tree name
    registry collected before the walk, which is a second pass this already
    large function should not grow on top of, so it too is left to M2.1.

    Returns an empty list when `raw` is clean. Each message names the path
    within the document (a `/`-joined layer-name trail, since layers have no
    other identifier as reliable as their position in this list), the
    offending value, and the valid range -- "invalid reference" alone would
    cost whoever hits it an afternoon finding out what to check.
    """
    problems: typing.List[str] = []

    def layer_children(node):
        """This raw layer node's own child layer nodes, found structurally.

        A container (GroupLayer/BoneLayer/SwitchLayer/...) keeps its children
        under `layers`. A `TextLayer` with none of its own instead carries
        exactly one synthetic child one level down, its own `mesh_layer` (a
        complete `MeshLayer`-shaped object) -- mirroring `moho2svg.py`'s
        `Layer._build`, which synthesises that same child and documents why
        (see this function's own docstring). Keying on this SHAPE (a `layers`
        list, or a `mesh_layer` dict that itself has a `mesh` dict) rather
        than on an enumerated list of `type` strings means a layer kind this
        corpus has never seen (a `Mesh3DLayer`, say) is still walked
        correctly as long as it has one of these two shapes -- no whitelist
        to keep in sync with Moho's own kinds.
        """
        layers = node.get("layers")
        if isinstance(layers, list):
            return [c for c in layers if isinstance(c, dict)]
        mesh_layer = node.get("mesh_layer")
        if isinstance(mesh_layer, dict) and isinstance(mesh_layer.get("mesh"), dict):
            return [mesh_layer]
        return []

    def collect_layer_uuids(nodes, into):
        """Gather the uuid of every LAYER reachable from `nodes`, recursively.

        This walks the exact same shape `check_layer` below walks (via
        `layer_children`) rather than sweeping the whole raw document for any
        dict carrying `uuid` + `type` -- the raw document also holds several
        thousand `Style` objects shaped exactly like that (uuid and a `type`
        string), and a naive sweep would validate `target_layer_uuid` et al.
        against "some uuid-bearing node, layer or not" instead of "an actual
        layer", silently accepting a style's uuid written into a layer
        reference by a buggy edit. `target_layer_uuid` et al. can still name
        a layer anywhere in the tree, not just a sibling or ancestor, so this
        collection happens over the whole tree up front, before the walk
        below runs.
        """
        for node in nodes:
            uuid = node.get("uuid")
            if uuid:
                into.add(uuid)
            collect_layer_uuids(layer_children(node), into)

    layer_uuids: typing.Set[str] = set()
    collect_layer_uuids([layer for layer in raw.get("layers", []) if isinstance(layer, dict)], layer_uuids)

    def check_mesh(mesh, where):
        """Check the four mesh-local index classes (rules 1-4 above).

        Every container this reads (`points`/`curves`/`shapes`/`groups`, and
        the lists nested inside each) is confirmed to be the type it's
        documented as before it's indexed or iterated, and a wrong type is
        reported as its own violation rather than left to raise -- this
        checker runs after arbitrary programmatic edits, which is exactly the
        situation that produces a malformed container, and "detect-only"
        means reporting that, not crashing on it.
        """
        points = mesh.get("points", [])
        curves = mesh.get("curves", [])
        shapes = mesh.get("shapes", [])
        groups = mesh.get("groups", [])
        for name, value in (("points", points), ("curves", curves),
                            ("shapes", shapes), ("groups", groups)):
            if not isinstance(value, list):
                problems.append("%s %s is %r, not a list" % (where, name, type(value).__name__))
        if not isinstance(points, list):
            points = []
        if not isinstance(curves, list):
            curves = []
        if not isinstance(shapes, list):
            shapes = []
        if not isinstance(groups, list):
            groups = []

        for ci, curve in enumerate(curves):
            if not isinstance(curve, dict):
                problems.append("%s curves[%d] is %r, not an object" % (where, ci, type(curve).__name__))
                continue
            curve_points = curve.get("points", [])
            if not isinstance(curve_points, list):
                problems.append("%s curves[%d].points is %r, not a list"
                                % (where, ci, type(curve_points).__name__))
                continue
            for pi, cp in enumerate(curve_points):
                if not isinstance(cp, dict):
                    problems.append("%s curves[%d].points[%d] is %r, not an object"
                                    % (where, ci, pi, type(cp).__name__))
                    continue
                index = cp.get("point")
                if not isinstance(index, int) or not 0 <= index < len(points):
                    problems.append("%s curves[%d].points[%d].point = %r, valid 0..%d"
                                    % (where, ci, pi, index, len(points) - 1))

        for si, shape in enumerate(shapes):
            if not isinstance(shape, dict):
                problems.append("%s shapes[%d] is %r, not an object" % (where, si, type(shape).__name__))
                continue
            edges = shape.get("edges", {})
            if not isinstance(edges, dict):
                problems.append("%s shapes[%d].edges is %r, not an object" % (where, si, type(edges).__name__))
                continue
            curve_idx = edges.get("curve", [])
            segment_idx = edges.get("segment", [])
            if not isinstance(curve_idx, list):
                problems.append("%s shapes[%d].edges.curve is %r, not a list"
                                % (where, si, type(curve_idx).__name__))
                continue
            if not isinstance(segment_idx, list):
                problems.append("%s shapes[%d].edges.segment is %r, not a list"
                                % (where, si, type(segment_idx).__name__))
                continue
            for ei, ci in enumerate(curve_idx):
                if not isinstance(ci, int) or not 0 <= ci < len(curves):
                    problems.append("%s shapes[%d].edges.curve[%d] = %r, valid 0..%d"
                                    % (where, si, ei, ci, len(curves) - 1))
                    continue
                curve = curves[ci]
                curve_points = curve.get("points", []) if isinstance(curve, dict) else []
                n = len(curve_points) if isinstance(curve_points, list) else 0
                limit = n if isinstance(curve, dict) and curve.get("closed") else max(0, n - 1)
                seg = segment_idx[ei] if ei < len(segment_idx) else None
                if not isinstance(seg, int) or not 0 <= seg < limit:
                    problems.append("%s shapes[%d].edges.segment[%d] = %r, valid 0..%d"
                                    % (where, si, ei, seg, limit - 1))

        for gi, group in enumerate(groups):
            if not isinstance(group, dict):
                problems.append("%s groups[%d] is %r, not an object" % (where, gi, type(group).__name__))
                continue
            group_points = group.get("points", [])
            if not isinstance(group_points, list):
                problems.append("%s groups[%d].points is %r, not a list"
                                % (where, gi, type(group_points).__name__))
                continue
            for index in group_points:
                if not isinstance(index, int) or not 0 <= index < len(points):
                    problems.append("%s groups[%d] point %r, valid 0..%d"
                                    % (where, gi, index, len(points) - 1))

    def check_layer(layer, where):
        """Check one layer's own skeleton (rule 5) and uuid references (rule 6),
        its mesh if it has one, then recurse into its children -- including a
        `TextLayer`'s synthetic `mesh_layer` child (see `layer_children`).

        Only a layer's OWN `skeleton.bones` is checked -- `bone.parent`
        indexes the bone list it sits in, never an ancestor layer's, so no
        bone list needs to be threaded down through the recursion the way an
        inherited-skeleton model (the rejected `parent_bone` model above)
        would require.
        """
        skeleton = layer.get("skeleton")
        bones = skeleton.get("bones") if isinstance(skeleton, dict) else None
        if isinstance(bones, list):
            for bi, bone in enumerate(bones):
                if not isinstance(bone, dict):
                    problems.append("%s skeleton.bones[%d] is %r, not an object"
                                    % (where, bi, type(bone).__name__))
                    continue
                parent = bone.get("parent", -1)
                if parent != -1 and not (isinstance(parent, int) and 0 <= parent < len(bones)):
                    problems.append("%s skeleton.bones[%d].parent = %r, valid -1 or 0..%d"
                                    % (where, bi, parent, len(bones) - 1))

        mesh = layer.get("mesh")
        if isinstance(mesh, dict):
            check_mesh(mesh, where + " mesh")

        for field in ("target_layer_uuid", "follow_layer_uuid", "distortion_layer_uuid"):
            ref = layer.get(field)
            if ref and ref not in layer_uuids:
                problems.append("%s %s = %r names no layer in this document"
                                % (where, field, ref))

        children = layer.get("layers")
        if isinstance(children, list):
            for ci, child in enumerate(children):
                if isinstance(child, dict):
                    check_layer(child, "%s/%s" % (where, child.get("name", "[%d]" % ci)))
            return

        mesh_layer = layer.get("mesh_layer")
        if isinstance(mesh_layer, dict) and isinstance(mesh_layer.get("mesh"), dict):
            check_layer(mesh_layer, where + "/mesh_layer")

    for index, layer in enumerate(raw.get("layers", [])):
        if isinstance(layer, dict):
            check_layer(layer, layer.get("name", "[%d]" % index))
    return problems
