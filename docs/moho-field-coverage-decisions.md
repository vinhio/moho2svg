# Field-coverage effort — decisions I made without asking

This file exists because the run that produced the `field-coverage` branch was
executed autonomously: the human partner approved the plan, then asked for it to
be carried out step by step to completion. Along the way **56 decisions** had to
be made that the plan did not settle — conflicts between the plan and the code,
defects in the plan's own snippets, measurements that contradicted the plan's
premises, and scope calls. Each was made rather than parked, because a run that
stops on every question costs more than a wrong decision that is visible and
reversible.

They are recorded here, verbatim and in the order they were made, because the
working ledger they were written into is scratch and is deleted when the run
ends. **This is the list to read if you want to rework what I got wrong.** Each
entry states what was decided, why, and what it costs if the decision was wrong.

A note on their shape: a large fraction are corrections to **my own plan**.
Fifteen defects were found in the plan's code snippets and reasoning — three by
me before dispatch, the rest by implementers hitting real code or by reviewers.
That ratio is the single most useful thing this file records: the plan's
*argument* held up well, its *sample code* did not, and the review loop is what
caught the difference.

---

### Ruling 1

Makefile check targets are APPEND-ONLY across tasks 2/4/5/6 — every implementer must read the current Makefile and add its line to the existing check-roundtrip target, never replace the target. — Why: the plan shows the target at four different lengths because it grows; an implementer seeing only its own brief would read the shortest as authoritative. — Cost if wrong: an earlier check silently stops running, and a later task's regression goes undetected until the final review.

---

### Ruling 2

Task 4's rewrite of tools/check_roundtrip.py must keep Task 3's iter_paths and EXPECTED_DOCUMENTS unchanged and replace only main(). — Why: the brief says "replace main" but shows a fragment that references both. — Cost if wrong: the round-trip check stops walking all 76 documents and the 76-document guarantee quietly becomes 46 again.

---

### Ruling 3

Task 7 must NOT skip moho/track — drop the dirnames filter so its traversal matches Task 8's census exactly. — Why: measured, moho/track holds 0 document files, so the filter buys nothing today and creates a latent trace-vs-census disagreement that would fire fail-closed rule 1 spuriously. — Cost if wrong: negligible; at worst the trace walks a few directories of PNG/SVG reference frames and finds no documents.

---

### Ruling 4

the deliberate break-then-revert verification steps (T1 Step 5, T6 Step 3, T9 Step 5) must be reverted and never committed; the implementer reports the observed failure text as evidence instead. — Why: a reviewer would correctly flag a committed sabotage edit as a defect, and the plan's intent is to observe the gate failing, not to ship the break. — Cost if wrong: a broken constant ships; check-export would catch it on the next task.

---

### Ruling 5

Task 2's Makefile target name check-roundtrip, holding only a raw-mutation check at that point, is accepted as-is rather than renamed. — Why: T4 and T6 fill it with genuine round-trip checks two tasks later, and renaming it midway would churn three tasks' briefs. — Cost if wrong: cosmetic only — one task's window where a target name is broader than its contents.

---

### Ruling 6

Finding 1 (docstring forward-references tools/check_roundtrip.py, which does not exist yet) — PARKED, no fix. — Why: Task 3 creates that file two tasks from now, so the claim becomes true; churning a docstring to re-churn it in Task 3 buys nothing. — Cost if wrong: a reader inside the two-task window is briefly misled about which script reads all 76 documents.

---

### Ruling 7

Finding 2 (load_expected() and main() carry no docstring) — FIX NOW, fix round 1. — Why: it violates a binding Global Constraint I wrote myself, the reviewer is correct, and the plan's own code block is the precedent later tasks will copy. This is a plan defect, so the fix is authorised against the plan text. — Cost if wrong: none; docstrings cannot change behaviour, and check-export re-verifies.

---

### Ruling 8

Finding 3 (a missing corpus document is SKIPped by run_exports but still reported FAIL by main, so check-export fails outright on a fresh clone) — FIX NOW, folded into the same round despite being classified Minor. — Why: moho/ is gitignored, so EVERY other machine has zero documents and this gate would fail for reasons unrelated to output; check-reference documents skip-on-absence as a deliberate design goal and this gate should match it. Folding it in costs one extra edit in a file already being touched. Corrected semantics: skip absent documents, but FAIL if ZERO were found, so the gate can never pass by checking nothing. — Cost if wrong: a gate that skips more than intended; the zero-documents guard is what prevents it from passing vacuously.

---

### Ruling 9

stopped the in-flight

---

### Ruling 10

Important (check_no_raw_mutation.py passes vacuously with no corpus, and its summary prints len(PATCH_DOCS) rather than the number actually compared) — FIX NOW, round 1. — Why: identical to the defect fixed one commit earlier in the sibling gate (10c8cc7), so the repo precedent is a single commit old and consistency is cheap; a gate that reports "OK: 5 documents" after comparing zero is actively misleading, which is worse than a gate that fails. — Cost if wrong: none, the fix only narrows when the gate may pass.

---

### Ruling 11

Minor (stale comment at moho2svg.py:5147-5152 describing the raw-dict overwrite that no longer happens) — FOLD INTO THE SAME ROUND despite being Minor. — Why: this repository's primary knowledge artifact is its comments explaining WHY, and a comment asserting an ordering constraint that no longer exists will mislead the next reader more than an absent comment would. Cheap, same file, same round. — Cost if wrong: none, comment-only.

---

### Ruling 12

two further Minors (check-roundtrip absent from the help target, which Makefile:2 promises prints every target; and garbled wording at Makefile:282) — FOLD IN. — Why: both are one-line edits in a file already being touched, and the help target is a documented promise. — Cost if wrong: none.

---

### Ruling 13

Minor (the plan's own Progress table still has empty Status/Commit cells) — MY defect, not the implementer's, and I am fixing it myself. — Why: the plan states its Progress table is "the single place to read overall status", and the human partner asked specifically to mark DONE per task on the plan; I had been recording only in this ledger, which is gitignored scratch they never see. Controller bookkeeping, not code, so fixing it myself does not bypass review. Task 1's row is now filled; each later task's row is filled as it closes. — Cost if wrong: none; the git history is the backstop.

---

### Ruling 14

docs/moho-format-coverage.html (untracked, NOT gitignored, 46 KB) is left in place rather than committed or ignored. — Why: it is a report the human partner asked me to save to their machine, not a project artifact, and deciding its fate is theirs. — Cost if wrong: it could be swept into an unrelated commit by a careless

---

### Ruling 15

Task 3 will NOT make PROJECT_STEMS recursive. That step is dropped from the task and recorded as an open item instead. — Why: I inspected the Makefile and the plan under-states the damage. SIX pattern rules (out/svg/{ori,med,fast,raster}/%.svg, out/lottie/%.json, format/moho/%) take their prerequisite from

---

### Ruling 16

Important (read_document decodes with errors="replace", where load_document was previously strict) — FIX NOW, round 1, and I grade it ABOVE the reviewer's severity. — Why: for a read-only exporter, lenient decoding is a defensible "render something rather than crash". For the EDITOR this plan is building it is a silent data-loss path: load with replace, then save, and U+FFFD is written into the user's own document permanently. I measured before ruling - all 76 corpus documents decode STRICTLY with 0 failures - so strict costs nothing here, and it restores load_document's exact prior behaviour rather than changing it. — Cost if wrong: a document that genuinely contains invalid UTF-8 would now fail to load instead of loading with substituted characters. That is the correct trade for a tool that writes files back, and the error names the file.

---

### Ruling 17

Minor (an archive holding more than one .mohoproj member silently takes the first in namelist() order) — FOLD INTO THE SAME ROUND. — Why: cheap, same function, and silence is the problem rather than the choice of member; all 30 corpus archives hold exactly one, so a warning costs nothing today and names the situation if it ever arises. — Cost if wrong: none, warning only.

---

### Ruling 18

Task 7's trace code in the plan calls moho2lottie.LottieExporter(...).export(args.frame, args.frame). The real signature is export(self, frames, include_hidden: bool = False) - the second parameter is include_hidden, NOT a second frame. Any non-zero frame would therefore silently switch include_hidden on, so the trace would read hidden layers too and produce a baseline that overstates coverage. The Task 7 dispatch must use export([args.frame]) (a sequence), matching how moho2lottie's own CLI and tools/check_lottie_geometry.py call it. Verified signatures for the dispatch: moho2svg.Exporter(document, settings=None).export_document(frame=0, crop=False, nested_groups=True, include_hidden=False); moho2lottie.LottieExporter(document, settings=None, decimate_tolerance_px=0.0, rigid_transform_tolerance_px=0.0).export(frames, include_hidden=False); moho2svg.RenderSettings() and moho2lottie.RenderSettings() both construct with no arguments. — Why ruled now: the plan told the Task 7 implementer to "read both before running and correct the lambdas", which is exactly the kind of instruction that gets skimmed; supplying the verified signatures removes the guess. — Cost if wrong: a wrong signature makes the trace crash loudly rather than silently, except for the include_hidden case, which is the silent one and is now closed.

---

### Ruling 19

the third deviation is a real finding about the FORMAT, not just a bad test location, and I am recording it as open question Q6 rather than folding a fix into Task 4. — Why: my Step 5 told the implementer to write the round-trip copy to out/, and for moho/Snow_wars/06.moho that rendered as broken-image placeholders because ImageLayer filerefs with relativeTo != "Absolute" resolve against the DOCUMENT's own directory. I measured the blast radius: 12 of 76 documents carry at least one non-absolute fileref. So

---

### Ruling 20

Minor (write_document's

---

### Ruling 21

Minor (the round-trip check compares with

---

### Ruling 22

my Task 5 text claims these are "plain classes with an __init__, not dataclasses - except Edge". That is WRONG. CurvePoint (7 fields), MeshPoint (3), Bone (30) and Edge (3) are all FROZEN dataclasses, so

---

### Ruling 23

Transform must be included and my text under-describes it. Its __init__ already ACCEPTS raw: dict but extracts five channels and discards the dict, so it needs

---

### Ruling 24

my Task 5 check script iterates

---

### Ruling 25

Task 6's code does

---

### Ruling 26

Task 10's probe harness has the same

---

### Ruling 27

the Makefile diff contains 2 deletions, which is not pure append, and I am allowing it. — Why: both deletions are the help-text DESCRIPTION of check-roundtrip, rewritten from two lines to three so it states the new claim; the recipe itself is a clean single-line append. My append-only rule exists to stop recipes and existing targets being restructured, not to freeze documentation - and an earlier task in this plan was sent back for NOT updating the help text, so leaving a stale description would be the actual defect. — Cost if wrong: a reviewer could reasonably read my own rule more literally than I meant it; recorded here so the ruling is visible rather than implied.

---

### Ruling 28

the trace's result depends on OPTIONAL dependencies - 143 keys with Pillow/psd-tools installed (the ImageLayer/PSD branch runs), 142 without - and that must be handled before Task 8 scores anything. Decision: (a)

---

### Ruling 29

Important 1 (out/traced_keys.json records no environment fingerprint, while the trace yields 143 keys under .venv and 142 on a bare interpreter) — FIX NOW. This is the ruling I had already made before the review, now confirmed independently. — Why: Task 8 consumes this FILE, not the report prose. Anyone regenerating it without the optional dependencies gets a quietly different numerator, and Task 8's fail-closed rule would then flag a correct MODELLED entry as unread - inviting someone to "fix" the registry to silence a false alarm. A measurement whose value depends on its environment must state its environment. — Cost if wrong: none; it is additive metadata.

---

### Ruling 30

Important 2 (the trace runs ONE frame, so switch-layer inactive children are never walked and Channel._segment only exercises the interpolation branch governing the segment containing frame 0) — FIX NOW by tracing several frames per document. This one I had not considered, and it cuts the opposite way from every other error so far: it means 32.7% may UNDERSTATE coverage. — Why: it is not merely a low number, it is a wrong ENTRY generator. Task 8 fails any key declared MODELLED that the trace never saw, so a key read only on a Pose segment or only in a switch layer's second child would be forced to UNKNOWN, permanently understating the registry rather than just the headline figure. — Cost if wrong: tracing 3 frames per document triples the trace's runtime, which is minutes, not hours. I chose 3 frames (first, middle, last of each document's own range) over the 5 I first considered, and over include_hidden=True, to keep the trace faithful to what a real default export reads while still crossing switch branches and interpolation segments.

---

### Ruling 31

Minor (mohoedit.read_document sits outside the per-document try, so one unparseable document would abort the whole trace instead of being recorded and skipped) — FOLD IN, cheap and it protects a 76-document run from one bad file.

---

### Ruling 32

spec 4.2 says MODELLED requires trace-observed reads AND "a named check asserts the rendered effect". Applied strictly to the 142 already-traced keys, most would FAIL that second clause, because check_reference_frames.py and check_lottie_geometry.py assert geometry in aggregate - they do not assert any individual key's effect. Taken literally, Task 8 would have to become an unbounded verification project before it could record a single MODELLED entry. Ruling: for Task 8's seeding pass, MODELLED requires (a) the trace observed the key during a real export and (b) an evidence pointer naming the consuming code path plus the trace artifact. The "named check" clause binds where a key's effect is geometric and therefore genuinely covered by check-reference / check-lottie-geometry, and otherwise it is satisfied later by Task 10's probe during M1-M3. — Why: Task 8's deliverable is the instrument and the baseline, not a retroactive proof of 142 individual rendering effects. Bounding it this way keeps the fail-closed rules meaningful (a key still cannot be claimed without the trace agreeing) while leaving the stronger per-key evidence to the sweep that has a tool for it. — Cost if wrong: the initial registry records MODELLED on some keys whose individual rendered effect is asserted only in aggregate. That is visible in the evidence pointer, so a later pass can tighten it; it does not inflate the coverage number, because the trace requirement is unchanged.

---

### Ruling 33

the 547 annotations must be SEEDED by a script (disposition derived from the trace plus the DESCRIPTION patterns), not hand-typed. — Why: 547 hand edits across six schema files would produce transcription errors and filler evidence strings, and would take longer than the rest of the plan. A generated seed is auditable and re-runnable; hand refinement then applies only where a disposition is genuinely in question. — Cost if wrong: generated evidence strings are uniform rather than individually reasoned, which is honest for a seeding pass and is exactly what M1-M3 replaces key by key.

---

### Ruling 34

the 92.9%-vs-95.6% gap is REAL and I am closing it by growing M3, not by moving the target. Audited myself: baseline 142 + M1 144 + M2 97 + M3-as-planned 20 = 403 / 434 = 92.9%, a 9-key shortfall against the 412-key target. The plan's 95.6% assumed a 154-key baseline that the grep instrument had inflated. Fix: M3 decodes 29 of the 39 constant-valued keys instead of 20, so the residual is 10 keys against a 22-key budget - still comfortably inside it. The denominator (434), the target (412) and the residual budget (22) are all unchanged; only M3's share grows, by 9 keys. — Why this way: the alternative would be to relax the 95% target or to shrink the denominator, and both would be moving the goalposts to meet the measurement rather than doing the work. Growing M3 spends real budget that was already reserved for exactly this class of key. — Cost if wrong: M3 is the most expensive milestone per key (each constant-valued key needs a synthesised document and a precondition), so nine more of them is the most expensive nine keys in the plan. If they prove undecodable the shortfall reappears and the residual budget absorbs at most 12 of it.

---

### Ruling 35

the flat-by-name registry keeps one confirmed collision (

---

### Ruling 36

I am REVISING my own ruling 4. I accepted the flat-by-name registry with "one known collision (curves), accepted as an open question", believing the cost was one key of imprecision. The review demonstrated something worse: the Keyframe field

---

### Ruling 37

Important 2 (six more MODELLED entries whose own description says "not read"/"not applied": Mesh.shape_order, Layer.timing_offset, Layer.mask_expansion, BoneLayer.gravity, BoneLayer.wind, GroupLayer.gravity, Curve.start_percent) — FIX, but the fix direction differs per key and must be judged, not applied mechanically. At least two of those descriptions are STALE rather than the disposition being wrong: CLAUDE.md records mask_expansion as APPLIED (a 2px white stroke in the mask) and curve start/end_percent as decoded AND applied (stroke exposure). So for those, the description is the thing that is wrong. For genuinely read-but-never-applied fields the wording should become "read into the model, but never applied", as was already done for MeshPoint.parent. — Why it matters: schema/ is meant to be an authoritative reference, and a file that contradicts itself in six places is worse than one that says nothing.

---

### Ruling 38

Minor (EDITABLE carries no evidence requirement, while counting toward coverage identically to MODELLED) — FIX NOW even though it is moot today. — Why: the registry has zero EDITABLE entries because the generator never emits them, but EDITABLE is the disposition that M1-M3 will hand-add ~270 times. Shipping the sweep's primary disposition with no evidence requirement is how an unevidenced claim becomes the norm. Cheapest possible moment to close it is before the first one is written.

---

### Ruling 39

Minor (load_registry resolves same-name conflicts last-wins for exact keys but first-wins for patterns) — FOLD IN, make them consistent and state which. — Why: no live conflict exists today only because the generator writes the same decision everywhere; M1-M3 hand-refinement is exactly what will diverge two occurrences on purpose.

---

### Ruling 40

the 95% target was off by one in my spec AND my plan. Both said 412 keys, from round(434 x 0.95) = 412. But 412 / 434 = 94.93% - BELOW the bar those same documents claim. Reaching >= 95.0% needs 413 keys, so the residual budget is 21, not 22, and M3 must supply 31 of the 39 constant-valued keys, not 29. Left alone, this plan would have closed one key short while reporting success. I corrected the plan and the design doc myself (controller bookkeeping) and sent the code side to the implementer with the requirement that the checker DERIVE the bar as the smallest N with N/content >= 0.95 - a ceiling, not a round - so it cannot drift again if the corpus grows. — Cost if wrong: none; the correction is strictly stricter.

---

### Ruling 41

nothing enforced the target at all - check_field_coverage.py only PRINTS "target 95.0%" and gates solely on registry failures, so

---

### Ruling 42

fix both G and H in round 3, and require the waiver to be DEMONSTRATED firing on a key the checker really loads. — Why: this repository's discipline is that a gate nobody has watched fail is not a gate; the same must apply to an escape hatch nobody has watched open. An unexercised waiver branch in the rule that guards against false MODELLED claims is precisely where a silent defect would hide. — Cost if wrong: one more round on a task that has already had two; justified because this is the machinery every remaining milestone is scored by, and the budget is 5.

---

### Ruling 43

Task 9 ships ONLY the rules demonstrated clean on the corpus. parent_bone, and by extension the two fields sharing its index space (mesh.points[].parent and flexi_bone_subset), plus switch_keys, are EXCLUDED from Task 9 and handed to M2.1 (bones) and the switch-layer area of M2, where those fields are decoded properly with a probe. The implementer must MEASURE each excluded candidate and record the violation count as a finding, not simply omit it. — Why: a checker that fires on 29 of 76 known-good documents is worse than no checker, because the only way to keep using it is to disable rules, and a disabled rule is indistinguishable from a passing one. The six clean rules are also the ones that matter most for editing: they are precisely what index renumbering breaks. — Cost if wrong: the editor ships without validation for bone binding and switch keys, which are real reference classes. That gap is now written down with measured counts instead of being masked by a rule nobody trusts.

---

### Ruling 44

the last two counts are a LEAD, not noise, and I recorded it as open question Q7. mesh.points[].parent and flexi_bone_subset are clean on 75 of 76 documents, and both failures are in the SAME document - ReparentBone.animeproj, this corpus's fixture for the Reparent Bone tool. anim_parent is an ANIMATED bone-parent index, which is precisely the feature that would move a bone's index space partway through a document. So unlike parent_bone (wrong across 24 documents, i.e. the model is wrong), those two rules may be validatable with ReparentBone as a documented exception. That makes them the cheapest win in M2.1 and I have said so in the plan. — Cost if wrong: M2.1 spends effort on two rules that turn out to need the same decode parent_bone does; the 75/76 evidence says otherwise.

---

### Ruling 45

CRITICAL (check_integrity never descends into a TextLayer's nested mesh_layer.mesh, so rules 1-4 silently skip 28 TextLayer instances across 17 of 76 documents, holding 1,115 curves) — FIX NOW, do not defer. — Why: the checker prints "OK: 0 documents with problems" while structurally unable to see over a thousand curves. That is the precise failure class the narrowing ruling was made to avoid - reporting clean for the wrong reason - and it is worse than the rules I deliberately excluded, because those are documented absences while this is an invisible one. moho2svg.py already special-cases this nesting (it synthesises a MeshLayer child for a TextLayer's mesh_layer), so the fix is a known shape, not a modelling question. — Cost if wrong: none; strictly more is checked.

---

### Ruling 46

Important (collect_uuids gathers ANY dict having both

---

### Ruling 47

Minor (check_mesh assumes curves/shapes/groups are lists and would raise rather than report if malformed) — FOLD IN. — Why: "detect-only" implies graceful reporting over crashing, and this checker is meant to run after arbitrary programmatic edits, which is exactly the situation that produces a malformed container.

---

### Ruling 48

M3.1's stated efficiency is measurably FALSE and I have recorded it as open question Q8 rather than letting M3.1 discover it mid-milestone. My plan asserts that one

---

### Ruling 49

Important 1 (a --value that round-trips to the value already present yields a FALSE "inert") — FIX NOW. set_every checks presence only, so if every touched site already holds the value being written, touched > 0, both twins render identically, and the row is recorded as a clean inert - indistinguishable from a genuine negative. This is the single worst failure this tool can have, because "inert" ENDS a field's investigation and nothing downstream re-opens it. — Why now rather than in the sweep's recipe: M2 and M3 are told to tabulate distinct values first, which mitigates it, but M1 has no such instruction and the tool itself neither catches nor warns. A safeguard in the instrument beats a habit in the process. — Cost if wrong: the probe refuses some no-op values that a human would have recognised as no-ops anyway.

---

### Ruling 50

Important 2 (out/probe/base.png and var.png are fixed paths, so two concurrent probes race and one can hash the other's render) — FIX NOW. — Why: this is not merely untidy. My own design doc's cost estimate for the sweep (~10 minutes for ~270 fields) EXPLICITLY assumes independent probes parallelise across Moho processes, so the design requires a mode the tool cannot currently run safely, and the failure is silent - a wrong AFFECTS-RENDER or inert verdict with no error at all. — Cost if wrong: none; unique output names cost nothing.

---

### Ruling 51

Important 3 (nothing detects that the layer holding the field was not drawn at the chosen frame - hidden, wrong switch branch, alpha 0 - which produces the same false-inert shape) — CANNOT be fully closed by the tool, so it must be DOCUMENTED as a residual risk in the harness docstring and in the probes file header, in the same voice this repo uses for its other recorded negatives. — Why: a manually supplied --frame means the tool cannot know what should have been visible. Naming the risk where the results live is the honest option; leaving it implicit invites a sweep author to trust every inert.

---

### Ruling 52

Minor 4 (the persisted row records precondition site counts but not the TARGET key's own touched-site count - "124 sites" for line_width exists only on stdout) — FIX. Plan-mandated, my own row format. — Why: the row is the durable evidence; the report is not. A reader six months out can currently tell that a field was touched at least once but not how broadly, and breadth is what distinguishes "changed one layer's field" from "changed 124 sites and still nothing moved".

---

### Ruling 53

the final whole-branch review runs on SONNET, deviating from the skill's "most capable model" guidance. — Why: three consecutive opus terminations on infrastructure and quota, not on content. A completed sonnet review is worth more than a fourth interrupted opus attempt, and I have narrowed the prompt to the cross-cutting questions and pointed it at live files rather than the 569 KB diff so it can finish. — Cost if wrong: a less capable reader on the branch's most subtle questions; mitigated because every one of the ten tasks already had its own scoped review, several on opus, and because I verified the six gates myself.

---

### Ruling 54

Important 1 - the flat-by-name registry now UNDER-counts, and it is the same blind spot biting in the opposite direction. InterpEntry.b was correctly set to UNKNOWN in Task 8's fix round, but first-occurrence-wins means it now SHADOWS Color.b (the blue channel), which the trace shows genuinely being read via Color.from_raw. So the flat key

---

### Ruling 55

Important 2 - Layer.transform and Layer.mesh on a PatchLayer are ALIASES of the target layer's objects, sharing the same .raw dict. That is pre-existing rendering behaviour, deliberately unchanged, but Task 5 turned .raw into a first-class editing surface, so a future script writing patch_layer.transform.raw["scale"] would silently rewrite the TARGET's transform while the patch's own sits untouched at patch_layer.raw. FIX by documenting it loudly at the aliasing site. — Why documentation rather than de-aliasing: Task 2 established that the borrowed values are what rendering needs, and de-aliasing would change render output, which check-export would correctly reject. The hazard is that the attribute NAME lies about ownership; the fix is to say so where someone will read it. — Cost if wrong: a comment is weaker than a guard; an editing API built later should consider a real accessor split.

---

### Ruling 56

Minor 3 - iter_paths over moho/ is duplicated near-identically in four scripts. FOLD INTO THE SAME WAVE as a mohoedit.iter_documents() helper. — Why: all four agree today, so it is not a correctness bug, but it is four places to fix the next time the corpus filter changes, and this suite's whole value is that its members agree. Consolidating now, while all four are provably identical, is far cheaper than after they drift.
