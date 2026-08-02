AGREED

# Round 8 (Fable seat) — verification attack on v8, ruling on Round 7, and the floor verdict

[confirmed] I attacked
`docs/plans/active/spectral_program_operating_model_v8_2026_08_02.md` as a stranger's design, with
one narrow assignment: Round 7 found that v7's unchecked-send path let a builder assert a failed
checker search nobody performed, and let the waiting-to-be-checked backlog be jumped by rotating
builder identity; v8 answers with a dispatcher that owns those records. I verified that the v7 hole
was real, that the v8 cure exists and closes it, and I hunted for new holes the cure could have
opened. I found nothing worth a new design version. This record proves that verdict with my own
audit of every critical and high finding from all seven earlier rounds, checked against current
files, not inherited.

[confirmed] This round wrote exactly one file: this record. No new design version exists — v8
stands. I changed no code, config, runtime, `local/` content, earlier round record, tmux seat,
bridge process, git state, or hardware, and ran no git mutation command.

[confirmed] Evidence opened and checked myself this round: v8 in full; v7 at the exact lines
Round 7 attacked (v7:445-473, 555-574); `ROUND_7_sol.md`, `ROUND_6_fable.md`, `ROUND_5_sol.md`,
`ROUND_4_fable.md`, `ROUND_3_sol.md`, `ROUND_2_fable.md`, `REVISION_ROUND_1.md`, and
`COMBINED_DESTROY_review.md` in full; the failure dossier in full; `smart_phrasing.py:705-805`
(zero-runway `runway_beats` at 714-739, fail-open `select_true_drops` at 782-797, verbatim as v8
§4 states); `local/spectral_v5_2026_07_17/combined1_runner.py:1120-1176` (skip-with-reason on
missing drop/cid/frames/grid/audio, verbatim); `KNOWNSCORE_scorecard.md:1-15` (line 9's
partial-key caveat); `DEVGRADE1_scorecard.md:14-25` ("phantom-or-plausible, never phantom");
`LOWKEY1_scorecard.md:1-20` (all seven key rows and lengths printed, so no custody story can be
true); `DEVSPLIT_2026_08_01.md:34-53` (Lowkey B0 program-exposed; fresh-blind is a standing
class); `PROGRAM_STATE_2026_07_31.md:44-64` (track energy, drop energy, accents all OPEN ROW);
`RBPALL5_report.md:100-112` (5.71 h and 5.49 h single-model phases). [confirmed] The
acceptance-format SHA-256 recomputes to
`80084cba17d49cb4fed4b8ecf0add0caa8f02bda5a60d57a43382238e97bb910`, matching v8 §3.
[confirmed] Nothing named `tools/spectral_listen` exists in the tree. [confirmed] The older
offline pilot command `python3 -m tools.spectral_pilot score` does exist, at
`tools/spectral_pilot/__main__.py:463-473`; v8:324-327 identifies it correctly as legacy, outside
the proposed interface, and unable to pass the sender as a governed body. The earlier broad
"nothing named score exists" sentence is stale and v8 no longer repeats it.

---

## 1. The assigned verification: was Round 7's finding real, and does v8's cure hold?

**The v7 hole was real.** [confirmed] v7:453-456 required only that "the run record also contains
a checker-acquisition attempt ... whose recorded outcome is failure" — no component owns that
record, so the builder who benefits from it can write it, and nothing records which checkers were
offered the run or how each answered. [confirmed] v7:460-461 ordered deferred checks oldest-first
only "before that checker accepts any new run from the same builder" — so replacing the builder
identity between runs legally starves the old unchecked run forever. [confirmed] v7's step-1 test
list (v7:560-569) tested a missing acquisition record but never who created it, whether every
eligible checker was offered the run, record reuse, or the cross-builder jump. Round 7's finding
stands exactly as written.

**The v8 cure exists and closes both halves.** [confirmed as design text; assumed as build
contract until built]

1. **Ownership.** v8:459-468: the checker dispatcher — not the builder or front desk — creates
   acquisition records. Per request it snapshots every registered checker adapter with its
   provider/model family, removes the ones the builder/checker separation rule forbids, offers the
   exact run to every remaining adapter, and stores the registry and config hash, offer time, and
   each adapter's outcome (explicit decline/quota error, or ten minutes without acceptance) in one
   transaction. The sender accepts an unchecked send only when that completed round was created
   after the run entered `WAITING_FOR_CHECKER`, and rejects a caller-created, incomplete, earlier,
   or reused round; every unchecked send needs a new completed round. A builder inserting its own
   failed-attempt row no longer satisfies the sender's contract.
2. **One queue.** v8:470-478: delivered-unchecked runs form one backlog across all builders. The
   dispatcher may lease a checker only the oldest such run, rejects leases for any newer governed
   run until it leaves the backlog, breaks ties by delivery time then run id, and does selection
   and lease in one transaction — so rotating the builder cannot jump the line. That is a
   behavior rule tied to stored order, not to who produced the work.
3. **Tests land with the switch.** v8:575-587: step 1 now includes the dispatcher in the single
   switch, forbids calling the operator surface governed before both dispatcher and sender are
   active, and names the exact failure tests: a caller-created acquisition row, a round made
   before the wait state, a round omitting an eligible adapter, reuse of a completed round for a
   second send, and — with an older unchecked run from builder A — a checker request for newer
   builder-B work that must be refused while A's run is leased first. Two builders implementing
   this must produce the same observable behavior on every one of those cases, including the
   failure paths. That meets the convergence brief's bar for a cure specified before code exists.
4. **The honest residue is stated, not hidden.** v8:466-468 and 660-667: a completed round proves
   only what the registered adapters did. It cannot see unregistered provider capacity, cannot
   force a checker to exist, and total chat loss delays both the correction and every newer
   governed result. The manifest keeps the request id, registry hash, per-adapter outcomes, and
   queue lease (v8:437-439), so a later audit can see exactly what was offered and to whom.

**New-hole hunt on the changed mechanism — what I tried and what I found.**

- **An emptied or thin adapter registry.** If the registered adapter list is empty, or every
  registered adapter shares the builder's provider family, the eligible set is empty and a round
  completes with zero offers, opening the unchecked path with a technically true line. [confirmed]
  This is inside v8's stated limit, not outside it: v8:466-468 says the round proves only what
  registered adapters did, v8:449-451 requires two provider families before adoption, and the
  stored registry hash makes a shrunken registry visible in every run record. Keeping the registry
  honest is a remembered duty, and I list it as such below. Not a new hole — the same admitted
  boundary, with its tracks recorded.
- **A forged dispatcher round.** The sender must reject caller-created rounds; the design does not
  say how the sender tells them apart, but step 1's forged-row test forces every builder to
  implement some distinguishing mechanism with the same observable outcome, and a code change that
  fakes the dispatcher lands in the manifest's source commit and dirty patch, which the checker
  reads on its first return — while every sheet shipped in the meantime carried the UNCHECKED
  line. Caught at the first check, visibly degraded before it. Consistent with the design's own
  claim that the label is visibility, not prevention.
- **The race where a checker accepts mid-round.** A round completes as failed only when every
  eligible adapter declined or timed out; one acceptance means no completed failed round, so the
  sender refuses the unchecked send and the run is simply being checked. No hole.
- **Reusing one round across runs or sends.** The round is bound to the exact run offered and each
  send needs a new completed round; reuse is a named rejection and a named test. Closed.
- **The stuck first-in-line run.** The strict oldest-first rule has a real cost I could not design
  away without reopening the jump: if the oldest unchecked run's check never finishes (a checker
  that keeps dying mid-check), or the only returning checker is ineligible for that particular run
  under the separation rule, newer runs' checks wait behind it. Everything about that state is
  fail-closed and visible — the check lease expires into `RECOVERY_NEEDED` with a local notice
  (v8:513-517), newer full lists refuse with a growing since-time, and no wrong output reaches the
  operator — but the chat refusal wording attributes the wait to checker unavailability rather
  than to a stuck queue head, so a person has to read the local notices to see the real cause.
  I weighed making this a finding and judged it below the bar: it is a conservative stall during
  an already-degraded state, it lets nothing false through, v8 makes no claim it contradicts, and
  every automatic escape I could construct (skip the head after N failed leases) reintroduces a
  path around the oldest-first promise. It is my residual-risk entry, not a defect.

**Verdict on the assignment: the change holds, and I found no new hole worth a v9.**

---

## 2. Ruling on Round 7's record — verified, not accepted

| Round 7 claim | Round 8 verdict |
|---|---|
| v7's failed-attempt record was a caller's assertion and the backlog was jumpable by builder rotation | [confirmed] **Real.** Read at v7:453-456 and 460-461; the step-1 list at v7:560-569 lacks the owner, offer-coverage, reuse, and cross-builder tests. |
| v8:459-468, 470-478, 575-587, 660-667 carry the cure and its residue | [confirmed] **Accurate.** All four passages exist at those lines and say what Round 7 says they say. |
| Round 6's H1 (hearing-capacity limit) and H3 (baseline visibility) hold in v8 unchanged | [confirmed] v8:616-628 claims only lease-queue priority and names seat spend, label honesty, and provider allowance as out of reach; v8:355-358 prints baseline and chooser and says what a weak baseline disarms. |
| The legacy `spectral_pilot score` correction | [confirmed] The command exists at `tools/spectral_pilot/__main__.py:463-473`; v8:324-327 states it precisely. |
| No earlier cure reopened by v8 | [confirmed] by my own pass over v8 §§1-14 against the Round 2-6 cure locations — every mechanism is present (details in §3 below). |

Round 7's work stands in full. Its refusal to write AGREED was correct: writing it over a
caller-asserted safety record would have repeated the exact overclaim class this loop exists to
cut.

---

## 3. My own audit of every critical and high finding, rounds 1-7, against v8

I re-verified each cure's mechanism in the v8 text I read this round and in the current files
named; "[assumed]" marks build contracts that do not exist as code yet — v8 itself claims no
present-tense credit (v8:3-6).

### Round 1 — COMBINED_DESTROY criticals and highs

| # | Finding | My verdict under v8 |
|---:|---|---|
| 1 CRITICAL | The only referee calls unknown output wrong | **CURED by contract.** [confirmed] `KNOWNSCORE_scorecard.md:9` and `DEVGRADE1_scorecard.md:20-22` re-read: outside Lowkey he marked examples, never everything. v8:25-41 makes unmatched rows unjudged except inside an exposed complete lane/class scope; v8:372-374 repeats it at the evaluator. No count of "invented" rows exists anywhere in v8. |
| 2 CRITICAL | The one number is undefined and gameable | **CURED by removal.** [confirmed] v8 §6 has no scalar, no "within a beat" bucket (v8:370-371 says so by name), one-to-one pairing with deterministic ties (v8:363-365), and an automatic floor limited to lost overlap or a new refusal on an identical panel (v8:376-377). |
| 3 CRITICAL | The answer file leaks the exam or is not truth | **CURED for future keys; Lowkey honestly conceded.** [confirmed] LOWKEY1 prints all seven rows and lengths; the dossier prints them at its lines 97-98; v8:54-63 calls Lowkey exposed and unprotectable, v8:65-71 and 403-413 give only future keys one-way custody with a negative read test and `NOT BLIND` on failed separation. |
| 4 CRITICAL | The buildup guard relies on fail-open truth | **CURED by contract.** [confirmed] `select_true_drops` still fails open at `smart_phrasing.py:794-796` and missing phrases still yield zero runway at 724-725 — re-read this round. v8:233-250 forbids that selector as the safety decision, requires the seven-item proof per row, and demands a test built from the current fail-open case (v8:250). |
| 5 HIGH | `listen` is a slogan over missing prerequisites | **CURED as a contract, still unbuilt.** [confirmed] `combined1_runner.py:1127-1175` still skips on missing drop/frames/grid/audio; `PROGRAM_STATE:48-61` still shows three open lanes. v8:86-124 names the refusal table, builders, and the two public shapes; v8:608-609 keeps `listen` refusing `LANE_INCOMPLETE` until all four lanes exist. |
| 6 HIGH | Evidence can drift while looking current | **PARTLY CURED, PARTLY ACCEPTED LIMIT.** [assumed] v8:263-313: commit-before-model intake, dispositions, append-only corrections, reconciliation blocks, integrity checks, checked backups, replay. [confirmed] v8:315-318 and 654-655 admit the unwrapped-session path stays open with only the header tell. |
| 7 HIGH | Optimizing the scoreboard can make hearing worse | **CONTAINED, NOT SOLVED — stated.** [assumed] No scoreboard, no positive verdicts, teacher-material labels, frozen panel membership, named panel/baseline choosers (v8:347-358); generalization reserved for fresh blind work (v8:72-74). Convenient choices remain visible human limits, said plainly. |
| 8 HIGH | The checker verifies repetition, not truth | **CURED as an overclaim.** [assumed] v8:443-447: clean-bundle rerun, every changed path, failure injection, and the sentence that repetition is not musical truth. The dispatcher change closes the last way to route around it while claiming otherwise. |
| 9 HIGH | The old program renamed with fewer checks | **CURED only through staged adoption.** [confirmed] v8:573 keeps existing safeguards authoritative until each replacement passes; the replaces-mapping Rounds 3-7 verified still matches the current files I re-read (runner, scorecards, fail-open code, program state). Nothing earns present-tense credit. |
| 10 HIGH | Three seats do not contain death, quota, concurrent writes | **CURED as a build contract, unmeasured.** [assumed] v8:493-521: atomic states, single writer, leases with expiry and resume, a no-model-call watcher, separate delivery state, provider-family separation; the dispatcher and global queue now cover the checker-outage corner. [unknown] Real provider capacity is unmeasured. |
| 11-14 MEDIUM/LOW | reproduction, work-kill, communication, storage | **As Rounds 3-7 ruled; re-checked present in v8** §8 manifests (421-439), §10 falsifier/budget rules (524-541), §11 sender/storage (545-563), §13 admissions (674-687). No change this round. |

### Round 2 — critical and highs against v2

| Finding | My verdict under v8 |
|---|---|
| F1 CRITICAL | The governed door unusable until all lanes land | **CURED.** [assumed] v8:135-157: `develop` per lane with only that lane's prerequisites and a matrix forbidding other lanes' gates from blocking it; v8:593-595 proves it by test at step 3. The first governed slice is the laser development door itself (v8:574). |
| F2 HIGH | An unwrapped same-surface session bypasses capture | **ACCEPTED LIMIT, honestly held.** [confirmed] v8:315-318, 647-649, 654-655: the database cannot see a message it never received; detection is a later header tell, with no within-a-day promise. |
| F3 HIGH | Lowkey has no real custody class | **Round 2's custody cure stays refuted; Round 3's reclassification stays correct.** [confirmed] The seven rows are printed in LOWKEY1 and the dossier — I re-read both — so v8:54-63 calling Lowkey exposed regression is the only true position. |

### Round 3 — critical and highs against v3

| Finding | My verdict under v8 |
|---|---|
| F1 CRITICAL | Custody protects already-published answers | **CURED by truthful reclassification.** Same evidence as Round 2 F3 above; v8:69-71 adds that access control cannot unpublish an old key. |
| F2 HIGH | `develop` inherits unrelated full-list refusals | **CURED.** [assumed] The v8:146-152 matrix names, per lane, what must not block it; `LANE_INCOMPLETE` for another lane can never refuse a `develop` run (v8:143). |
| F3 HIGH | "Same inputs" does not bind baseline and candidate | **CURED for membership; the rest is a named limit.** [assumed] v8:340-345: both manifests must match one panel registered before the candidate's first builder change, else `NOT_COMPARABLE` or a no-panel description; v8:347-358 says preregistration cannot erase prior knowledge or make the panel wise. |
| F4 HIGH | Surface enforcement starts after the claimed switch | **CURED.** [confirmed] v7 had the sender in step 1 already; v8:574-587 adds the dispatcher to the same single switch and forbids the governed-surface claim until both are active — the exact one-switch shape Round 3 demanded, now covering the new component too. |

### Round 4 — its three findings (none higher than medium-high)

| Finding | My verdict under v8 |
|---|---|
| G1 | Evaluation bodies and the Lowkey label bypassed the sender | **CURED.** [assumed] Three governed body types, each state-aware and hash-bound with a mandatory first line the printer enforces against the manifest (v8:163-176, 223-227, 43-52). |
| G2 | Ad-hoc comparisons dodge the panel check | **CURED.** [assumed] No preregistered panel means single-run descriptions labelled `NO PREREGISTERED PANEL — differences not assessed` (v8:344-345); comparative output requires the registration-time ordering. |
| G3 | Checker quota walls stall the door and reopen side scripts | **CURED as a labelled degraded path** — now with the dispatcher-owned round, global backlog, stored delivery, and automatic correction block (v8:453-487). The original error a checker would have caught remains possible and labelled; v8:660-667 says so. |

### Round 5 — highs against v5

| Finding | My verdict under v8 |
|---|---|
| F1 HIGH | `WAITING_FOR_CHECKER` cannot satisfy a `PUBLISHED`-only sender | **CURED.** [assumed] The sender is state-aware per body type (v8:163-176); delivery is recorded separately from analysis state with the unchecked development sheet as the sole exception (v8:502-507); `CHECK_FAILED` creates a pending correction that blocks every newer governed body until the exact notice is delivered (v8:480-487). Internally consistent — I checked §2, §8, §9, §11 against each other in the v8 text. |
| F2 HIGH | The full-list template permits a partial list via refusal strings | **CURED.** [assumed] v8:204-207: a lane refusal never appears inside the body, a present refusal string cannot satisfy the completeness check, and the no-list path is the entire response; step 1 tests a refusal placed inside a full-list body (v8:579). |
| F3 MEDIUM-HIGH | Preregistration overclaims anti-gaming | **ACCEPTED LIMIT, correctly stated.** v8:347-358 as verified under Round 3 F3 above. |

### Round 6 — its three findings

| Finding | My verdict under v8 |
|---|---|
| H1 | A lease cannot protect provider allowance spent by ordinary seats | **ACCEPTED LIMIT, correctly stated.** [confirmed] v8:616-628 claims only the launcher's own queue priority and names everything else — seat dispatch, label honesty, provider allowance — as a human duty before and after the build; v8:669-672 and 709-713 repeat it, including to the operator. |
| H2 | "Checker unavailable" is a claim; deferred checks can vanish | **The v7 cure was incomplete exactly as Round 7 found; v8 cures the mechanical part.** §1 of this record is the full verification. The stated residue (unregistered capacity, no checker existing at all) is honest. |
| H3 | Baseline choice can disarm the floor invisibly | **ACCEPTED LIMIT, made visible.** [confirmed] v8:355-358: the report prints baseline, candidate, and `BASELINE CHOSEN BY <identity>`, and says a weak baseline protects little. |

### Round 7 — its one finding

Verified as the assignment; see §1. **CURED in v8 as a build contract, residue stated.**

[confirmed] No critical or high finding from any round is unanswered, wrongly claimed cured, or
reopened by v8. The three findings ever downgraded from CURED to ACCEPTED LIMIT (capture bypass,
panel representativeness, hearing capacity) are all carried as visible limits with their exact
boundaries stated, which is the honest shape for all three.

---

## 4. The floor verdict, asked for directly

[confirmed] **This design has reached its floor. Further design rounds stop reducing real risk.**
The evidence, not the fatigue:

1. **The findings trajectory is 14, 8, 3, 3, 3, 1, 0** — and the kinds fell faster than the
   counts: direction defects and false claims (rounds 1-3), then enforcement points not reaching
   their claims (rounds 4-6), then one ownership gap in a single mechanism (round 7), now nothing
   I could honestly call a defect. My hardest remaining attack produced a conservative stall that
   lets nothing false through.
2. **The stable core has survived eight independent attacks unchanged:** no scalar score,
   unjudged-not-wrong, fail-closed laser proof, refusal over partial output, state-aware
   hash-bound sender, one-switch adoption, honest limits over solved-sounding sentences, and the
   plain statement that hearing is unsolved.
3. **Every remaining big risk sits where no design text can move it:** [unknown] the library
   refusal rate, [unknown] whether phrase evidence is buildable, [unknown] wrapper feasibility on
   his real chat surface, [unknown] provider capacity for two families, [unknown] whether any
   model hears his sound classes. Those move only when the step-1 slice and the census run —
   after the operator chooses to adopt, which nothing in this loop authorizes.
4. **Round 6 predicted this point and named the trap:** another design round after the
   verification round would itself be dossier §8.2 — rigor spent polishing the honesty machine
   while cold hearing stands at 2 of 34. Writing a v9 to restate an already-admitted limit in new
   words would be exactly that.

---

## THE KILL SHOT

[confirmed] Unchanged since Round 2, because no design can remove it: the operating model becomes
the next polished object while the machine's hearing stays at the dossier's 2 of 34. Eight
adversarial rounds have now been spent on this design — about as much rigor as the old program
spent on any package it shipped, and that parallel is the kill shot's shape appearing in this very
loop, which is the strongest reason this round writes AGREED instead of a ninth version.
[assumed] If the operator adopts and six weeks produce a working dispatcher, sender, census, and
recovery drills but no better cold listening result, the design has still failed his actual goal —
visibly and cheaply instead of invisibly and expensively, which is all it ever claimed. What it
cannot do: choose the right hearing idea, or stop ordinary seats from spending the allowance
hearing work needs. Both are human duties the design now states instead of pretending to solve.

**The residual risk that worries me most:** the honesty machine wins while hearing loses — every
mechanism lands, every label is true, every refusal is exact, and the operator's ear result never
moves, because no part of this design hears music. Second, and the only mechanical one: the strict
oldest-first checker queue can idle behind one stuck or ineligible-for-its-checker run during a
degraded stretch, and the operator-facing wording attributes that wait to checker unavailability;
a person reading the local notices sees the true cause, the chat surface alone does not.

---

## Dossier §8 failure-mode table under v8

| # | Failure mode | Verdict | Scenario where it recurs anyway |
|---:|---|---|---|
| 1 | Confident output dies on his ear or eyes | UNCHANGED | [assumed] A verified, well-formed, honestly labelled list can still be musically wrong; only his ear rules. An unchecked sheet is visibly less protected. |
| 2 | Rigor spent on the wrong object | UNCHANGED | [assumed] Slice-first order and budgets bound cost; nothing chooses the right hearing idea, and machinery-seat spend is outside every enforcement point (stated, not solved). |
| 3 | Evidence unread or lost | UNCHANGED | [assumed] Wrapped input is reconciled; an unwrapped session can lose words until a later publish or forever; wrapper feasibility is [unknown]. |
| 4 | Over-rotation on corrections | VISIBLE WITHIN A DAY on governed output | [assumed] Required fields and append-only supersessions expose surface loss; semantic over-rotation outside a covered mark waits for his ear. |
| 5 | Settled laws re-broken | VISIBLE WITHIN A DAY on governed output | [assumed] The compiled buildup law refuses; taste laws and hand-paste can still recur. |
| 6 | Communication violations | UNCHANGED | [assumed] Bodies are shape-enforced; free prose can still be irrelevant, unclear, or answer around the question. |
| 7 | Delegated output consumed without verification | VISIBLE WITHIN A DAY | [assumed] Verified bodies require a checker; unchecked sheets require a dispatcher-completed round, carry the label, join the global oldest-first backlog, and trigger a named correction on a later failure. Hand-paste remains outside. |
| 8 | Seat/process mismanagement | VISIBLE WITHIN A DAY | [assumed] Ten-minute lines, leases, resume, dispatcher records, local notices; total provider/chat loss still silences the surface, and a stuck queue head is visible locally before it is legible in chat. |
| 9 | Building on missing or unvalidated deliverables | VISIBLE WITHIN A DAY | [assumed] Named lane refusals and the four-bucket census expose absence; an existing-but-wrong artifact survives until injection, a mark, or his ear. |

[confirmed] No whole mode is IMPOSSIBLE — the same verdict every round has reached, and any
stronger claim would be false.

---

## Enforced-by-nothing list

[confirmed] **Today:** every v8 mechanism is a design contract. Nothing named
`tools.spectral_listen`, its sender, checker dispatcher, intake wrapper, experiment registry,
lease launcher, or blind custody store exists in the tree — re-searched this round.

[assumed] **Enforced by code after the specified build:** the three state-aware hash-bound body
types with mandatory first lines; all-or-nothing full-list completeness with no refusal strings
inside a body; selected-lane prerequisites; fail-closed laser proof; dispositions and all-class
evidence counts; one-to-one evaluation with no positive verdict; preregistered panel membership
and the regression floor; dispatcher-owned acquisition rounds with per-adapter outcomes;
global cross-builder oldest-first check leasing in one transaction; the failed-sheet correction
block; manifests and reproduction refusal; atomic states, leases, resume, storage refusals, write
fences; blind-key negative tests and the attempt counter; the launcher's hearing-first queue rule.

[assumed] **Enforced by someone remembering even after the build:** starting operator-facing
sessions through the wrapper; an unwrapped seat admitting it cannot record; not hand-pasting
governed-looking text; keeping the registered checker-adapter list complete and honest; not
starting unregistered checker seats around the dispatcher; reading local notices when the checker
queue stalls; dispatching seats so machinery work does not starve hearing work; labelling lease
purpose honestly; choosing useful falsifiers, representative panels, and fair baselines;
classifying `human_only`/`not_applicable` honestly; keeping free prose plain and responsive;
initiating blind tests only on the operator's word.

[unknown] **Enforced by nothing:** that any model hears his sound classes; that Lowkey has not
been fitted; that a panel or baseline represents the library; that unregistered provider capacity
exists or does not; that a future codec or sound class works before it is tried; that an unwrapped
message is detected before a later publish; that he recognizes a stale last-recorded line; that a
well-formed but musically wrong span is rejected without his ear or a compiled law; that permanent
evidence stays under any fixed size; that he stays willing to tolerate honest refusals; that his
real chat surface can sit behind commit-before-model capture.

---

## Open questions and assumptions

1. [unknown] The full-library end-to-end refusal rate; the census cannot answer it.
2. [unknown] Whether missing phrase/drop evidence is buildable for most tracks.
3. [unknown] Whether the actual chat surface can sit behind commit-before-model intake.
4. [unknown] Whether two provider families can sustain builder/checker separation under real
   quota; the dispatcher records the answer per attempt instead of assuming it.
5. [unknown] Which registered checker adapters can actually perform automatic offers; v8 specifies
   their contract, not their existence.
6. [unknown] The accent lane's exact inputs.
7. [unknown] End-to-end time and storage for cached, unseen, refused, and 30-50-track runs.
8. [assumed] Ten minutes serves as both the silent-progress ceiling and the adapter acceptance
   timeout — a design choice grounded in the measured 5.5-5.7-hour phases, not an
   operator-measured preference.
9. [assumed] The three-attempt blind limit, the acceptance gate, and every dossier operator law
   remain fixed; nothing this round touched them.
10. [assumed] Existing safeguards stay authoritative until each replacement passes and the
    operator approves a switch; adoption itself is an operator decision this loop never made
    for him.
11. [assumed] If the stuck-queue-head stall ever proves common in practice, the honest fix is a
    recorded front-desk removal of the head run (with its own correction notice), decided then,
    on measured evidence — not designed now on none.

---

## Verification run this round

1. [confirmed] `python3 tools/check_docs_metadata.py` passed.
2. [confirmed] `python3 tools/check_docs_drift.py` passed.
3. [confirmed] `python3 tools/check_ui_jargon.py` passed for 13 files.
4. [confirmed] `python3 tools/check_agent_contracts.py` reports exactly the state Round 7 left:
   one unclassified active doc, v8. This round writes no design version, and the doc-index or
   registry entry remains outside the prompt's write boundary, as it was for Rounds 3-7.
5. [confirmed] The acceptance-format SHA-256 recomputes to the pinned value.
6. [confirmed] No unit suite was run because no executable code or tests changed. No runtime,
   bridge process, SoundSwitch, laser, LED/Govee, Rekordbox reader, or hardware check was
   attempted, and nothing here upgrades SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
