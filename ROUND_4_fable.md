# Round 4 (Fable seat) — attack on v4, ruling on round 3, and v5

[confirmed] **Verdict: CHANGES REQUIRED — but the changes are narrow, and the loop is converging,
not churning.** I attacked
`docs/plans/active/spectral_program_operating_model_v4_2026_08_02.md`, verified every Round 3 cure
claim against current files instead of accepting it, and found three enforcement holes — no
critical, no direction defect. All three sit on the same surface: the mechanisms that govern how
progress claims reach the operator. The next design is
`docs/plans/active/spectral_program_operating_model_v5_2026_08_02.md`.

[confirmed] This was design work only. I changed no code, config, runtime, `local/` artifact, tmux
seat, git state, or hardware. The only files written this round are this record and the v5 design.

[confirmed] Evidence opened and re-verified this round: v4 in full; `ROUND_3_sol.md`,
`ROUND_2_fable.md`, `REVISION_ROUND_1.md`, and `COMBINED_DESTROY_review.md` in full; the failure
dossier in full; `smart_phrasing.py:714-797` (fail-open `select_true_drops` and zero-runway
`runway_beats` are exactly as v4 states); `combined1_runner.py:1127-1175` (fail-closed
skip-with-reason, verbatim); `KNOWNSCORE_scorecard.md:1-9` (partial-key caveat verbatim);
`DEVGRADE1_scorecard.md:15-25` ("phantom-or-plausible, never phantom");
`LOWKEY1_scorecard.md:1-18` (all seven key rows printed); `DEVSPLIT_2026_08_01.md:34-55` (Lowkey
"B0 program-exposed", fresh-blind class standing); `PROGRAM_STATE_2026_07_31.md:44-64` (track
energy, drop energy, accents all OPEN ROW / never built); `RBPALL5_report.md:100-112` (5.71 h and
5.49 h single-model phases); v3 lines 525-560 (sender genuinely started at step 3 — v4's step-1
one-switch cure answers a real defect); the acceptance-format hash, recomputed:
`80084cba17d49cb4fed4b8ecf0add0caa8f02bda5a60d57a43382238e97bb910` (matches). A current-tree
search found `spectral_listen` only in design documents and round records — nothing implemented —
and 33 files under `local/` and `docs/` carrying a Lowkey key timestamp, which confirms Round 3's
F1 basis: that key is unprotectable.

---

## Findings, worst first

### G1. MEDIUM-HIGH — the sender governs lists but not evaluation reports, and the Lowkey label has no enforcing component

[confirmed] **Location:** v4 lines 150-152 (§2: sender accepts "a published run id and a body
whose hash matches"), 451-454 (§11: sender requires "correct full-list or development header" —
only two body types named), 326-328 (§6 pins evaluation chat rendering but binds it to nothing),
and 49-51 (§1: "every Lowkey report carries `EXPOSED COMPLETE REGRESSION — not a blind result`" —
no component named that refuses a report lacking it).

[confirmed] **What is wrong:** v4's sender contract enumerates exactly two governed body types:
full list and development sheet. An evaluation report — the body where improvement, regression,
and Lowkey claims live — is neither. Two builders read that differently: one makes the sender
reject all evaluation output (driving every progress claim into ungoverned prose permanently), the
other lets evaluation output bypass the sender entirely. Either way, the run-id/hash binding does
not cover the one surface where the original program actually died: a progress claim reaching the
operator that the machinery never checked. The Lowkey exposure label has the same gap — v4 asserts
the label exists but names no printer or sender rule that refuses a Lowkey report without it, so
it is enforced by someone remembering.

[confirmed] **Why it matters:** the dossier's §2 failure is a fictional scoreboard steering
decisions, and its §4 record shows a package whose own spec contradicted its claim surviving seven
review rounds. The claim surface is exactly where enforcement must sit. v4 put its enforcement on
list rows and left the claim surface open.

[assumed] **Concrete six-week failure:** a builder tunes against the exposed Lowkey rows, runs the
evaluator, and pastes a summary in chat: "all seven Lowkey growls now pair." No run id, no scope
line — and nothing requires either, because evaluation bodies are outside the sender contract. The
operator reads it as progress. A fresh track fails six weeks later, and the record shows the claim
never passed through any governed path — legally, under v4's own text.

### G2. MEDIUM-HIGH — comparability is only pinned inside experiments, so a post-hoc panel passes the manifest check

[confirmed] **Location:** v4 lines 295-299 (§6: "An experiment pins its evaluation panel before
builder work… Baseline and candidate manifests must match that panel exactly") and 430-433 (§10:
"A worker cannot swap in easy tracks… because §6 checks the pinned panel against both manifests").

[confirmed] **What is wrong:** nothing in v4 requires a run to belong to an experiment, and
`evaluate --baseline --candidate` is defined over two run ids, not over an experiment. When
neither run references a preregistered panel, the design does not say what `evaluate` checks the
manifests against. One builder refuses; another compares the two manifests against each other —
and two mutually matching manifests are trivial to manufacture after the fact: run old code and
new code over the same 20 tracks chosen because the new code looks good on them. The manifests
match, `NOT_COMPARABLE` never fires, and Round 3's F3 gaming returns through the ad-hoc door. v4's
§10 sentence presumes a pinned panel always exists; its §6 never forces one.

[confirmed] **Why it matters:** easy-track selection is a named attack surface in the convergence
brief, and this is the exact hole Round 3 rated HIGH — cured for experiments, silently reopened
for every comparison made outside one.

[assumed] **Concrete six-week failure:** exploratory runs show which 20 tracks flatter a change.
The worker declares no experiment, reruns baseline and candidate on those 20, and evaluates. Both
manifests match each other; the report is `comparable` under one legal reading of v4. The cleaner
cells attract the next slot while the 14 hard tracks vanish from view.

### G3. MEDIUM — during a checker quota wall, the governed door stalls with no labelled degraded path, which drives work back to side scripts

[confirmed] **Location:** v4 lines 388-390 (§8: no second provider family means the run "stays
`WAITING_FOR_CHECKER`") and line 101 (the refusal row gives no since-when). [confirmed] Provider
walls are documented current reality, not a hypothetical: `PROGRAM_STATE_2026_07_31.md` records
all three reviewer seats quota-dead until August 5, and `COMBINED_DESTROY_review.md` finding 10
verified it.

[confirmed] **What is wrong:** v4's only sanctioned behavior during checker unavailability is
indefinite stall. The operator asks where the growls are; the governed answer is "no result" for
however long the quota wall lasts — days, on the current record. Every earlier round agreed the
side-script window opens exactly when the governed door refuses (Round 2 F1, Round 3 F2). A stall
with no bound and no degraded mode recreates that pressure, and the design's own principle —
recorded in Round 2's kill shot, "ungoverned output is labelled ungoverned rather than pretended
governed" — exists only as a remembered sentence, not a mechanism.

[confirmed] **Why the cure is safe:** the protections that enforce operator law on a laser sheet —
the §4 fail-closed buildup proof, the §3 printer, the run record, the hash-bound sender — all run
builder-side, before the checker. What the checker adds is failure injection and full-path reads.
A development sheet shown with a mandatory `UNCHECKED` line loses the checker's marginal
protection visibly; a side-script sheet loses all of it invisibly. The first is strictly better
than the second, which is what actually happens under pressure.

[assumed] **Concrete six-week failure under v4:** week two of a checker outage. The operator asks
for a sheet; the governed path says `WAITING_FOR_CHECKER` with no since-when and no alternative. A
seat, not wanting to hand him nothing for days, pastes side-script output with no proof and no
header. It contains a buildup row. Dossier §4 recurs through the pressure valve the design left
shut instead of labelled.

---

## Outcomes in v5

| # | Outcome | Mechanism in v5 |
|---:|---|---|
| G1 | **CURED** | [assumed] §2/§11: the sender accepts exactly three governed body types — full list, development sheet, evaluation report — each requiring run id + matching hash + its mandatory first line. §1 fixes three evidence-scope first lines; §3's printer refuses an evaluation body whose scope line is missing or mismatched against the manifest's recorded evidence shape; §6 makes every evaluation a run with a manifest, reaching chat only through the sender. |
| G2 | **CURED** | [assumed] §6: `evaluate` refuses comparative output unless both manifests match one panel whose stored registration time precedes the candidate's first builder change; with no preregistered panel it prints only single-run descriptions labelled `NO PREREGISTERED PANEL — differences not assessed` and never emits an improvement or regression sentence. §8 manifests store the panel id; §10 and §12 step 2 updated to match. Panel membership remains printed human judgment — visible, not certified. |
| G3 | **CURED as a labelled degraded path, with the trade stated** | [assumed] §8: while `WAITING_FOR_CHECKER`, a development sheet only — never a full list, never a comparative claim — may be shown through the sender with a mandatory `UNCHECKED — independent check unavailable since <time>` line; the shown-unchecked fact is stored in the run record; a later `CHECK_FAILED` forces a correction naming that exact sheet before any newer result. §2's refusal row now carries the since-when. §13 states plainly that the label is visibility, not prevention. §12 step 1 tests the unchecked line and refuses a full list attempted unchecked. |

---

## Ruling on Round 3's cure claims — verified, not accepted

| Round 3 finding | Round 4 verdict |
|---|---|
| F1 — Lowkey reclassified as exposed | [confirmed] **Direction stands; enforcement was incomplete.** The reclassification is correct — I re-verified the seven rows in `LOWKEY1_scorecard.md:3-18`, the dossier, and 33 worker-readable files; no custody story could be true. But v4's label was a sentence with no refusing component (my G1). v5 wires it to the printer and sender. |
| F2 — lane dependency matrix | [confirmed] **Holds.** v4 §2's matrix names per-lane prerequisites and forbidden blockers; `LANE_INCOMPLETE` for another lane cannot refuse `develop`; `LANE_INPUT_MISSING` names missing inputs. The contract is tight enough for two builders to converge. Carried into v5 unchanged. |
| F3 — pinned comparison panel | [confirmed] **Holds inside experiments; a legal path around it existed.** The panel pin and `NOT_COMPARABLE` are real in v4 §6, but nothing forced a comparison to reference a preregistered panel (my G2). v5 closes the ad-hoc door. |
| F4 — one-switch governed slice | [confirmed] **Holds.** I verified v3:538-548 really did start the sender at step 3; v4 §12 step 1 lands proof, printer, run record, checker, header, and sender as one switch and forbids the governed-surface claim before the sender is active. Carried into v5 with two added test cases. |
| F5 — all five evidence-use classes printed | [confirmed] **Holds.** v4 §5's public line prints all five classes, requires the union to account for every active judgment or publication stops, and exposes overlap via `M`. Carried unchanged. |
| F6 — census renamed to substrate census | [confirmed] **Holds.** v4 §12 step 4's four buckets, the ban on "can print" without an exact checked run, and the explicit not-the-refusal-rate sentence are all present. Carried unchanged. |
| F7 — ten-minute progress line | [confirmed] **Holds.** v4 §2 requires a deterministic no-model-call line at least every ten minutes with stage, elapsed, checkpoint, and count-or-say-so, and a death notice by the same deadline against the verified 5.5-5.7 h phase evidence. Carried unchanged. |
| F8 — capture-gap accepted limit restated honestly | [confirmed] **Holds.** v4 §§5 and 13 claim detection only on a later governed publish plus the operator's memory; no within-day claim anywhere. Carried unchanged, plus v5 moves the wrapper-feasibility unknown into §13 where it belongs. |

[confirmed] Round 3 also correctly refuted Round 2 on five points; I spot-verified the two
load-bearing refutations. The Lowkey custody refutation is right (33 files on disk). The v3
sender-at-step-3 refutation is right (read at v3:538-548). Round 3's work stands.

---

## Audit of all prior findings after v5

Original fourteen (`COMBINED_DESTROY_review.md`), condensed to what I verified:

| # | Round 4 ruling |
|---:|---|
| 1 — partial keys call unknown rows wrong | [confirmed cured by contract] Partial-key unmatched output is `unjudged` throughout §§1, 6; the source caveats re-read at their lines. |
| 2 — one number undefined/gameable | [confirmed cured by removal] No scalar, no within-a-beat bucket, pinned one-to-one matcher with deterministic ties. G2 closed the last comparison-gaming door. |
| 3 — key boundary contradicts itself | [confirmed cured] Blind custody one-way (§7); Lowkey honestly exposed (§1); the label now machine-enforced (G1). |
| 4 — buildup guard fails open | [confirmed cured by contract] §4 never consults `select_true_drops`, refuses on absent phrase data, and names the test built from the current fail-open case — which I re-read in code this round. |
| 5 — `listen` a slogan over prerequisites | [assumed cured by contract, unbuilt] Named refusals, builders, lane prerequisites, ten-minute progress. Nothing exists yet; the design says so. |
| 6 — evidence drift | [assumed cured inside the wrapper; accepted limit outside] Unchanged from Round 3; wrapper feasibility remains the open question. |
| 7 — optimizing the scoreboard | [assumed contained, not solved] Teacher-set movement cannot be called generalization; scope lines now enforced (G1); panels preregistered (G2); only a future blind adds evidence. |
| 8 — checker verifies repetition only | [assumed cured as an overclaim] Full changed-path reads plus injection; repeatability explicitly not musical truth; the new §8 degraded path never skips the check, it defers and forces a named correction. |
| 9 — old program renamed | [confirmed the mapping holds] I verified Round 3's replaces-table anchors (runner, scorecards, fail-open code, program state). The behavior changes are real if built; none exists today. |
| 10 — seats die, quota walls | [assumed cured by build contract, unmeasured] Leases, atomic publish, resume, launchd watcher. G3 adds the missing quota-wall surface behavior. |
| 11 — history cannot reproduce | [assumed cured by manifest contract] §8's list now also pins evidence shape, panel id, and shown-unchecked. |
| 12 — automatic work kill | [assumed cured] Budgets pause; rejection only on falsifier, regression floor, compiled law, isolation failure, or operator veto. |
| 13 — communication remains discipline | [assumed partly cured, partly accepted] Sender and fences enforce shape on all three body types now; free prose and hand-paste stay named limits. |
| 14 — size/cost unsupported | [assumed partly cured, partly accepted] Measurement before claims; scratch bounded; permanent evidence growth explicit. |

[confirmed] Round 2's eight findings: F1-F8 all remain cured or accepted-limit in v5 in the same
places Round 3 verified, with F1 (development door) and F3 (custody) carrying the Round 3
corrections. No Round 2 cure was undone by v4 or v5.

---

## Is the loop converging or churning? (asked directly this round)

[confirmed] Converging, on three measurable trends:

1. **Severity is falling in kind, not just count.** Round 1 answered three direction-level
   criticals (invalid referee, self-contradicting key boundary, refuted buildup guard). Round 2's
   critical was governance (the door nobody could use). Round 3's critical was a false custody
   claim — an honesty defect, not a direction defect. This round found zero criticals and zero
   direction defects: all three findings are enforcement edges on mechanisms whose direction every
   round has upheld.
2. **Reversals have been evidence-driven, not oscillation.** The only cure any round undid is
   Round 3 reversing Round 2's Lowkey custody store — and I re-verified the evidence that forced
   it (33 worker-readable files carrying the key). Nothing else has flip-flopped across four
   rounds; v5 carries v4's structure intact with three additions.
3. **The stable core has survived four independent attacks unchanged:** no scalar score,
   unjudged-not-wrong, fail-closed buildup proof, refusal over partial output, surface-first
   adoption, hearing-slot reservation, and the honest statement that hearing itself is unsolved.

[assumed] If the next seat verifies G1-G3's cures and attacks with the same lenses, an earned
`AGREED` is now plausible. The one thing that would properly reopen the loop is evidence-driven,
not design-driven: the census or first governed slice measuring something (refusal rate, quota
reality) that breaks an assumption all five documents share.

---

## Progress-gaming audit under v5

1. [confirmed] Fitting marked tracks: legal on teacher material, never callable generalization;
   the scope line that says so is now machine-enforced.
2. [assumed] Easy-track selection: refused both inside experiments (panel match) and outside them
   (no preregistered panel means no comparative sentence at all).
3. [confirmed] Unmatched rows on partial keys: never wrong; deletion cannot be rewarded as fewer
   errors.
4. [assumed] Degenerate long output: pairs with at most one mark, full length and difference
   print, never rendered as pass. Musical wrongness still waits for his ear — stated, not hidden.
5. [assumed] Refusal hiding: a newly refused panel track is `NOT_COMPARABLE` plus the regression
   floor.
6. [assumed] A fake scalar: impossible through the sender (evaluation bodies are hash-bound and
   scope-lined); still possible in hand-pasted prose, where its missing run id and scope line are
   the tells. That residual is typing, which no design stops.

---

## What v5 gives up, and what that leaves uncaught

Unchanged from Round 3's six (one progress number; Lowkey as held-out; point-at-anything success;
complete conversational capture; automatic judgment of musical duration; small permanent storage —
all verified still stated in v5 §13), plus one new trade this round made deliberately:

7. [assumed] **It gives up "nothing reaches him unchecked."** During a checker outage, a
   development sheet can now reach the operator with a mandatory unchecked line instead of not at
   all. What that leaves uncaught: a defect only the checker's injection or full-path read would
   have found, live on his surface until the deferred check lands. The alternative was the
   side-script window, which the whole record says is worse.

---

## THE KILL SHOT

[confirmed] Unchanged in substance from Rounds 2 and 3, because no design can remove it: the most
likely death is still that the redesign itself becomes the next over-built object while the
hearing result stays at 2 of 34. The mechanisms bound it — one governed slice first, a reserved
hearing slot, adoption quota, budgets that pause instead of verdict — and this round added nothing
to that machinery, deliberately. What the four rounds cannot do is make the next hearing
experiment attack the right idea. If six weeks from now the program has a beautiful sender, three
governed lanes, a census — and the ear result has not moved — the operator will say what he said
on 08-01, and he will be right. The design's only honest answer is that it now fails visibly and
cheaply instead of invisibly and expensively.

---

## Dossier §8 failure-mode table under v5

| # | Failure mode | Verdict | Scenario where it recurs anyway |
|---:|---|---|---|
| 1 | Confident output dies on his ear or eyes | `UNCHANGED` | [assumed] Structural lies refuse; a well-formed, checked, honestly-labelled list can still be musically wrong until his ear rules. An unchecked-labelled sheet widens this by exactly the checker's margin, visibly. |
| 2 | Rigor spent on the wrong object | `UNCHANGED` | [assumed] Bounded by the slice-first order and reserved hearing slot; no mechanism chooses the right experiment. |
| 3 | Evidence unread or lost | `UNCHANGED` | [assumed] Wrapped input is accounted for; an unwrapped session still loses words until a later publish; wrapper feasibility itself is still unproven. |
| 4 | Over-rotation on corrections | `VISIBLE WITHIN A DAY` on governed output | [assumed] Printer fields and append-only supersessions expose surface loss; a semantic over-rotation waits for a covering mark or his ear. |
| 5 | Settled laws re-broken | `VISIBLE WITHIN A DAY` on governed output | [assumed] Compiled buildup law refuses; taste laws and hand-pasted output can still recur. |
| 6 | Communication violations | `UNCHANGED` | [assumed] All three body types now shape-enforced, but free prose around them remains human/model behavior. |
| 7 | Delegated output consumed without verification | `VISIBLE WITHIN A DAY` | [assumed] Nothing publishes unchecked silently; the §8 degraded path is loud, stored, and forces a named correction on a failed later check. Hand-paste still bypasses everything. |
| 8 | Seat/process mismanagement | `VISIBLE WITHIN A DAY` | [assumed] Leases, ten-minute lines, resume, local notices; total provider loss still silences chat. |
| 9 | Building on missing/unvalidated deliverables | `VISIBLE WITHIN A DAY` | [assumed] Lane input refusals and the four-bucket census expose absence; an existing-but-wrong artifact survives until injection, a mark, or his ear. |

[confirmed] No whole mode is `IMPOSSIBLE`, same as every prior round. The three `UNCHANGED` rows
persist through admitted paths; the stronger label would be dishonest.

---

## Enforcement audit

[confirmed] **Today:** every v5 mechanism is a design contract only. Nothing named
`spectral_listen`, `listen`, `develop`, `evaluate`, the sender, the intake wrapper, leases, or
custody exists in the tree — re-searched this round.

[assumed] **Enforced by code after the specified build:** the three-body-type sender with
mandatory first lines; evidence-scope lines matched against manifests; preregistered-panel
comparability with registration-time ordering; selected-lane dependency checks; fail-closed
buildup proof; all-class evidence counts and reconciliation blocks; one-to-one evaluation with the
regression floor; manifests including panel id and shown-unchecked; atomic publish, leases,
resume; unchecked-line requirement and the forced correction after `CHECK_FAILED`; storage
refusals; write fences.

[assumed] **Enforced by someone remembering even after the build:** starting operator-facing
sessions through the wrapper; an unwrapped seat admitting it cannot record; not hand-pasting
ungoverned text; choosing useful falsifiers; classifying `human_only`/`not_applicable` honestly;
choosing panel membership and the next slot wisely; keeping free prose plain and responsive;
blind tests only on the operator's initiative; honoring the hearing slot before the experiment
database exists; posting the `CHECK_FAILED` correction promptly rather than eventually.

[unknown] **Enforced by nothing:** that any model truly hears his sound classes; that Lowkey has
not already been fitted; that a future codec or class is supported before tried; that an unwrapped
message is detected before a later publish; that he recognizes a stale last-message header; that a
musically wrong well-formed span is rejected without his ear or a compiled law; that provider
quota exists when a checker is needed; that permanent evidence stays under any fixed size; that he
stays willing to tolerate honest refusals; that a commit-before-model wrapper is even possible on
his real chat surface.

---

## Three six-week walkthroughs I ran against v5

1. **The pasted Lowkey victory (G1).** Builder fits the exposed rows, evaluator run pairs all
   seven, and the only sanctioned way to show it stamps `EXPOSED COMPLETE REGRESSION — not a blind
   result` on the first line with a run id. Pasting the claim without those is possible but now
   carries two missing tells instead of zero mechanism. The fitting itself remains uncaught — v5
   says so rather than pretending.
2. **The convenient 20-track comparison (G2).** No preregistered panel exists, so `evaluate`
   prints two single-run descriptions and no improvement sentence; a comparative claim requires a
   panel older than the candidate's first change, checked from stored times. The worker can still
   register a flattering panel for the *next* experiment — it prints, he can see it, and the hard
   tracks' absence is visible in the panel list. Degraded to visible judgment, not gameable
   arithmetic.
3. **The two-week checker outage (G3).** Under v4, the governed door stalls silently and the side
   window reopens. Under v5, the operator gets the development sheet with an unchecked first line
   and a since-when; the run record stores the fact; when the checker returns and fails it, the
   correction names the sheet he saw. The buildup law held the whole time because the proof runs
   before the checker. What he loses is the checker's margin — labelled, bounded, recoverable.

---

## Open questions and assumptions

1. [unknown] The real full-library end-to-end refusal rate. The census cannot answer it; only
   real runs will.
2. [unknown] Whether missing phrase/drop evidence is buildable for most tracks.
3. [unknown] Whether the operator's actual chat surface can sit behind a commit-before-model
   wrapper at all. If not, §5's capture story is a header tell only, and v5 §13 now requires
   saying so the day it is discovered.
4. [unknown] Whether two provider families can sustain builder/checker separation under current
   quotas. The G3 degraded path bounds the operator-facing cost of the answer being no; it does
   not create quota.
5. [unknown] The accent lane's exact inputs; the §2 matrix forbids borrowing until its contract
   lands in code.
6. [assumed] Ten minutes stays the maximum silent interval — a design choice against measured
   5.5-5.7 h phases, not an operator-stated preference.
7. [assumed] The three-attempt blind limit, the acceptance gate, and every ruling recorded as
   operator law in the dossier remain fixed; nothing this round touched them.
8. [assumed] Current side processes stay authoritative until each replacement passes its named
   failure tests and the operator approves the switch.

---

## Verification run this round

1. [confirmed] `python3 tools/check_docs_metadata.py` passed.
2. [confirmed] `python3 tools/check_docs_drift.py` passed.
3. [confirmed] `python3 tools/check_ui_jargon.py` passed (13 files).
4. [confirmed] `python3 tools/check_agent_contracts.py` reports the same pre-existing condition
   Round 3 reported — the dossier and operating-model versions are unclassified active docs, now
   including v5. The cure is a doc-index or registry entry, which is outside this round's
   two-file write boundary, exactly as it was outside Round 3's.
5. [confirmed] No unit suite was run: this round changed no executable code or tests. No hardware
   validation was attempted, and nothing here upgrades the repo's SOFTWARE-VALIDATED ONLY /
   HARDWARE-UNVALIDATED status.
