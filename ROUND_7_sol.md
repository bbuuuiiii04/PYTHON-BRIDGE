CHANGES REQUIRED

# Round 7 (SOL seat) — verification attack on v7 and ruling on all earlier rounds

[confirmed] I attacked
docs/plans/active/spectral_program_operating_model_v7_2026_08_02.md as the verification round,
checked Round 6's three changes instead of accepting its record, and found one mechanism worth
changing. Round 6 was right that the hearing-capacity promise had to be removed and that baseline
choice is a visible human limit. It was not right that a database row by itself turned checker
unavailability into a fact or that its same-builder priority forced the whole unchecked backlog to
be checked oldest first.

[confirmed] The complete next design is
docs/plans/active/spectral_program_operating_model_v8_2026_08_02.md. This round changed only that
design and this record. It changed no code, config, runtime, local artifact, earlier round record,
tmux seat, bridge process, or hardware.

[confirmed] I opened v7, ROUND_6_fable.md, ROUND_5_sol.md, ROUND_4_fable.md, ROUND_3_sol.md,
ROUND_2_fable.md, REVISION_ROUND_1.md, COMBINED_DESTROY_review.md, and the failure dossier in full.
I also re-read smart_phrasing.py:700-815, combined1_runner.py:1120-1185, the cited scorecard
caveats, Lowkey's printed key, DEVSPLIT's evidence classes, the four-lane program state, the
5.49/5.71-hour run evidence, and the current command tree. [confirmed] The acceptance-format
SHA-256 recomputes to 80084cba17d49cb4fed4b8ecf0add0caa8f02bda5a60d57a43382238e97bb910.

[confirmed] Nothing named tools.spectral_listen exists. The convergence prompt's broader sentence
that nothing named score exists is not current-tree true:
tools/spectral_pilot/__main__.py:463-473 defines the older offline pilot score command, and the
active-work registry records that it ran. That older command is not the proposed evaluator and
cannot produce one of v7's sanctioned result bodies. v8 says that precisely instead of repeating
the stale broad claim.

---

## Finding, worst first

### H1. MEDIUM-HIGH — the failed checker attempt is still a caller's assertion, and the backlog can be jumped by changing builders

[confirmed] **Location:** v7:449-463. Lines 453-457 require a run-record row saying acquisition
failed and call that a stored fact. Lines 460-461 require old unchecked runs before new work only
when the new work comes from the same builder. The step-1 tests at v7:560-569 test a missing
acquisition row, but not who created it, whether every eligible checker was offered the run,
whether the same row is reused, or whether builder B can jump builder A's unchecked run.

[confirmed] **What is wrong:** the sender checks that a row exists, but v7 names no component that
must perform the acquisition or own that row. It records no eligible-checker snapshot, provider
outcomes, timeout, or registry hash. Two builders can legally produce different behavior: one can
actually offer the run to every eligible checker; another can insert a failed-attempt row and send
immediately. The second satisfies v7's sender contract without any checker being sought.

[confirmed] The backlog rule has a second concrete hole. A waiting unchecked run from builder A
blocks new work from A, but v7 permits the same checker to take newer work from builder B. Builder
identity is replaceable in v7 §8, so rotating the worker can displace the backlog forever while
every individual queue decision follows the sentence.

[confirmed] **Why it matters:** this is dossier §8.7 again: delegated output reaches the operator
without independent verification while a record claims the independent path was tried. The sheet
is visibly labelled unchecked, so this is not as severe as the original silent consumption, but
v7 overclaims that the label's supporting fact and deferred check are mechanically bound.

[assumed] **Concrete six-week failure:** builder A ships an unchecked laser sheet after writing a
failed-attempt row. No provider was contacted. The next run uses replacement builder B, then C, so
the returned checker keeps taking newer work without violating the same-builder clause. The old
sheet remains unchecked for six weeks; its growing since-time is visible, but the promised
oldest-first check never occurs.

---

## Outcome in v8

| Finding | Outcome | Mechanism |
|---|---|---|
| H1 | **CURED as a build contract, with the real outside limit stated** | [assumed] v8:459-468 makes the checker dispatcher, not the builder or front desk, own acquisition rows. It snapshots every registered eligible adapter, offers the exact run to each, records per-adapter outcomes and the registry/config hash in one transaction, and rejects caller-created, incomplete, early, or reused rounds. v8:470-478 makes one global oldest-unchecked queue across all builders, with atomic selection and lease. v8:575-587 makes the dispatcher part of the first governed switch and tests forged rows, incomplete offers, reuse, and builder-A versus builder-B queue jumping. v8:660-667 says the honest residue: this proves only what registered adapters did; it cannot prove unregistered provider capacity does not exist. |

[confirmed] v8 also corrects one source claim without changing direction: v8 §6 identifies the
existing tools.spectral_pilot score command as legacy and keeps it outside the proposed
tools.spectral_listen interface and sanctioned sender.

---

## Verification of Round 6's three changes

| Round 6 change | Round 7 verdict |
|---|---|
| H1 — remove the false promise that a lease protects hearing capacity | [confirmed] **HOLDS as an accepted limit.** v7:598-610 limits machine enforcement to hearing-first priority inside the launcher's own queue. It explicitly says ordinary design/build/review seats, provider allowance, and self-declared purpose labels are outside that reach. v7:650-653 and 688-692 repeat the same boundary in the uncertainty and operator sections. No sentence promises capacity the launcher cannot see. v8 carries this unchanged. |
| H2 — require a failed acquisition record per unchecked send and oldest-first deferred checking | [confirmed] **DOES NOT HOLD as claimed.** The sender row requirement exists at v7:170-172 and 453-457, but no acquisition owner makes it more than a caller-created claim. The queue priority at v7:460-461 is only same-builder, and step 1 has no cross-builder backlog test. H1 above cures both in v8. |
| H3 — make baseline choice a named accepted limit | [confirmed] **HOLDS.** v7:352-355 prints baseline/candidate identities and the baseline chooser, says a weak baseline disarms much of the floor, and calls that a visible human limit. v7:519-523, 658-660, and 680-685 carry the same claim. v8 leaves it unchanged. |

[confirmed] Round 6's judgment that one verification round could legitimately earn AGREED was
conditional on all three changes holding. Two hold; one does not. Writing AGREED would therefore
accept the exact enforcement-point overclaim that Round 6 said this loop had learned to stop.

---

## Full prior-findings audit across all six earlier rounds

### Round 1 — the original fourteen findings from COMBINED DESTROY

[confirmed] REVISION_ROUND_1.md claimed twelve cures and two accepted limits. I did not inherit
those rulings; the table below tests the current v8 contract against every original finding.

| # | Original finding | Round 7 ruling under v8 |
|---:|---|---|
| 1 CRITICAL | Partial keys call unknown output wrong | [confirmed] **CURED by contract.** Current KNOWNSCORE:9 and DEVGRADE1:20-22 say unmatched output outside Lowkey is unjudged. [assumed] v8:25-41 and 372-381 preserve that boundary and permit extra/wrong only inside an exposed complete lane/class scope. |
| 2 CRITICAL | The one number is undefined and gameable | [assumed] **CURED by removal.** v8 §6 has no combined score or positive verdict, uses one-to-one pairing with deterministic ties, prints each start/length difference, and limits the automatic floor to lost overlap or a new refusal on identical inputs. |
| 3 CRITICAL | The answer file leaks the exam or is not truth | [confirmed] **CURED for future keys; Lowkey honestly exposed.** Lowkey's seven rows are printed in current files. v8:54-74 never calls it hidden; v8:404-412 gives only future keys one-way custody and permanently reclassifies released keys. |
| 4 CRITICAL | The buildup guard relies on fail-open truth | [confirmed] **CURED by build contract.** smart_phrasing.py:714-739 returns zero runway on absent phrases and :782-797 fails open. [assumed] v8:233-250 forbids that selector as safety authority and withholds laser output on absent or ambiguous proof. |
| 5 HIGH | listen is a slogan over missing prerequisites | [confirmed] **CURED as a contract, still unbuilt.** combined1_runner.py:1127-1175 still skips missing drop/grid/frame/audio, and PROGRAM_STATE:54-60 still shows incomplete lanes. [assumed] v8:80-176 names resolution, builders, lane-specific refusals, all-or-nothing output, development access, and the exact refusal surface. |
| 6 HIGH | Evidence can drift while looking current | [assumed] **PARTLY CURED, PARTLY ACCEPTED LIMIT.** v8:263-313 gives wrapped messages identities, dispositions, append-only corrections, reconciliation, integrity checks, checked backups, and replay. v8:315-318 admits an unwrapped session remains invisible until a later tell. |
| 7 HIGH | Optimizing the scoreboard can make hearing worse | [assumed] **CONTAINED, NOT SOLVED.** v8 removes the scoreboard and generated positive verdicts, labels released material as teacher evidence, freezes membership inside comparisons, names panel and baseline choosers, and reserves generalization for fresh blind work. Convenient choices remain visible human limits. |
| 8 HIGH | The checker verifies repetition, not truth | [assumed] **CURED as an overclaim.** v8:399-447 requires clean-bundle rerun, every changed path, and failure injection while saying repetition is not musical truth. H1 closes the checker-dispatch hole; unchecked development remains explicitly less protected. |
| 9 HIGH | The old program is renamed with fewer checks | [assumed] **CURED only after staged adoption passes.** v8:567-628 keeps current safeguards until each replacement and its failure tests pass, begins with one complete governed slice, and grants no present-tense credit. The behavior mapping below names the replacements. |
| 10 HIGH | Three seats do not contain death, quota, or concurrent writes | [assumed] **CURED as a build contract, unmeasured.** v8:416-511 gives atomic run state, one writer, leases, resume, local notices, provider-family separation, the dispatcher-owned degraded path, and global backlog. Total provider loss remains visible but unsolved. |
| 11 MEDIUM | History cannot reproduce its displayed result | [assumed] **CURED by contract.** v8:422-441 pins source, patch, command, environment, evidence, audio, every derived input, versions, refusals, output, dispatcher attempt, and queue lease; reproduction refuses missing bytes. |
| 12 MEDIUM | Automatic work killing serves a fake metric | [assumed] **CURED.** v8:524-541 rejects only on a runnable falsifier, identical-panel regression floor, compiled law, isolation failure, or operator veto. Budget exhaustion pauses. Baseline weakness is named, not hidden. |
| 13 MEDIUM | Communication and paper-growth promises remain discipline | [assumed] **PARTLY CURED, PARTLY ACCEPTED LIMIT.** v8:545-563 makes body shape, run id, hash, state, correction, and storage refusals mechanical. v8:635-679 admits free prose, hand-paste, and judgment classifications still depend on people. |
| 14 LOW | Time/cost claims lack evidence and permanent storage grows | [assumed] **PARTLY CURED, PARTLY ACCEPTED LIMIT.** v8 makes no speed projection, requires measured cached/unseen/refused/batch runs, bounds scratch, and stops loudly at protected storage. Exact permanent evidence still grows for the program's life. |

### Round 2 — eight findings against v2

| Finding | Round 7 ruling under v8 |
|---|---|
| F1 CRITICAL — the governed door is unusable until all lanes land | [assumed] **CURED.** v8:135-176 gives each development lane only its own prerequisites and the same governed sender; v8:575-587 makes the laser development door the first complete switch. |
| F2 HIGH — an unwrapped same-surface session bypasses capture | [confirmed] **ACCEPTED LIMIT remains honest.** v8:315-318 and 647-658 say the database cannot see a message it never received and promise no one-day detection. |
| F3 HIGH — Lowkey has no real custody class | [confirmed] **Round 2's proposed custody cure remains refuted; Round 3's truthful reclassification holds.** Current files expose every row; v8 calls Lowkey exposed complete regression, never blind. |
| F4 MEDIUM-HIGH — breaks a released example is undefined | [assumed] **CURED.** v8:376-381 defines only lost overlap/not-evaluated or a new refusal on the identical panel as the automatic floor. Other differences wait for judgment. |
| F5 MEDIUM — evidence-use escape classes are invisible | [assumed] **CURED for visibility.** v8:290-302 prints all five classes, requires their union to cover every active judgment, and exposes overlap. Classification truth remains human. |
| F6 MEDIUM — fail-closed proof may refuse much of the library | [unknown] **CURED only as honest measurement.** v8:596-601 separates ready, build-required, refused-now, and unknown and forbids calling that census the end-to-end refusal rate. The real rate is still unknown. |
| F7 MEDIUM — long work can be silent for hours | [assumed] **CURED by contract.** v8:126-133 caps silence at ten minutes without a model call, grounded in the confirmed 5.49/5.71-hour phases. |
| F8 LOW — evaluation chat shape is unspecified | [assumed] **CURED.** v8:383-385 puts the operator's mark first, one plain line per mark, and bans glyph grids/internal columns. |

### Round 3 — eight findings against v3

| Finding | Round 7 ruling under v8 |
|---|---|
| F1 CRITICAL — Lowkey custody protects already-published answers | [confirmed] **CURED by truthful reclassification.** v8:54-70 says access control cannot unpublish Lowkey and only a future key can be blind. |
| F2 HIGH — develop can inherit unrelated full-list refusals | [assumed] **CURED.** v8:141-157 supplies a lane matrix and explicitly forbids other lanes and irrelevant laser proof from blocking the selected lane. |
| F3 HIGH — same inputs does not bind baseline and candidate | [assumed] **CURED for comparison membership.** v8:338-358 requires both manifests to match one preregistered panel and returns NOT_COMPARABLE on changes; panel and baseline wisdom are named limits. |
| F4 HIGH — surface enforcement starts after the claimed switch | [assumed] **CURED.** v8:575-587 lands proof, printer, run record, independent checker, dispatcher, header, and sender together and forbids the governed-surface claim before both dispatcher and sender are active. |
| F5 MEDIUM-HIGH — not_applicable hides non-use | [assumed] **CURED for visibility.** v8:290-302 includes it in the public total and blocks an incomplete union. |
| F6 MEDIUM — the refusal census measures files, not behavior | [assumed] **CURED by reclassification.** v8:596-601 calls it a prerequisite census and keeps the end-to-end rate unknown. |
| F7 MEDIUM — stage updates can still be 5.7 hours apart | [assumed] **CURED.** v8:126-133 adds a deterministic ten-minute clock line and death notice. |
| F8 MEDIUM — capture-gap visibility is overstated as within a day | [confirmed] **ACCEPTED LIMIT remains honest.** v8:654-655 says only a later governed publish and operator recognition may expose it. |

### Round 4 — three findings against v4

| Finding | Round 7 ruling under v8 |
|---|---|
| G1 MEDIUM-HIGH — evaluation and Lowkey labels bypass the sender | [assumed] **CURED.** v8:43-52 fixes the scope lines; v8:163-176 governs exactly three body types; v8:216-227 refuses missing/mismatched evaluation scope; v8:333-336 binds evaluation to a run/body hash. |
| G2 MEDIUM-HIGH — an ad-hoc comparison has no preregistered panel | [assumed] **CURED.** v8:338-353 refuses comparative output without a panel registered before candidate work and emits no positive verdict. Earlier exploratory knowledge remains a printed limit. |
| G3 MEDIUM — checker quota stalls the governed door and reopens side scripts | [assumed] **CURED as a labelled degraded path after H1.** v8:453-487 allows only a development sheet, requires dispatcher-owned acquisition, global backlog priority, stored delivery, and automatic correction after a failed later check. The original unchecked error remains possible and labelled. |

### Round 5 — three findings against v5

| Finding | Round 7 ruling under v8 |
|---|---|
| F1 HIGH — WAITING_FOR_CHECKER cannot satisfy a PUBLISHED-only sender | [assumed] **CURED.** v8:163-176 is state-aware; v8:502-507 separates delivery from analysis state; v8:480-487 creates and enforces the correction block. |
| F2 HIGH — the full-list template allows refusal values inside a partial list | [assumed] **CURED.** v8:188-207 removes refusal placeholders and makes any lane refusal take the no-list path; step 1 tests a refusal embedded in the body. |
| F3 MEDIUM-HIGH — preregistration overclaims protection from easy panels | [assumed] **ACCEPTED LIMIT, made visible.** v8:347-358 freezes only the named comparison, prints panel/baseline choosers, bans positive verdicts, and admits prior knowledge and weak choices. |

### Round 6 — three findings against v6

| Finding | Round 7 ruling under v8 |
|---|---|
| H1 MEDIUM-HIGH — a lease cannot protect the provider allowance spent by ordinary seats | [confirmed] **ACCEPTED LIMIT, correctly stated.** v8:616-628 keeps only queue priority and says seat dispatch, purpose-label honesty, and provider capacity stay outside it. |
| H2 MEDIUM — checker unavailable is a claim and deferred checks can disappear | [confirmed] **Round 6's v7 cure was incomplete; v8 cures the mechanical part and states the residue.** Dispatcher-owned acquisition and global cross-builder priority now have exact failure tests. Unregistered provider capacity and total absence of checkers remain limits. |
| H3 LOW-MEDIUM — baseline choice can disarm the regression floor invisibly | [assumed] **ACCEPTED LIMIT, made visible.** v8:355-358 prints the baseline and chooser and explains what a weak baseline removes from the floor. |

[confirmed] No earlier critical or high finding is reopened by v8. H1 changes only checker
acquisition and queue ownership; it does not alter evidence scope, pairing, laser proof, full-list
completeness, capture, custody, run states, or the hearing-capacity limit.

---

## Is it the old program renamed?

| v8 element | What it replaces | Behavior change if built |
|---|---|---|
| listen | [confirmed] Manifest-driven combined1_runner.py plus separate lane tools | [assumed] Resolves/builds or returns one named no-list reason; never silently skips or emits a partial acceptance list. |
| develop | [confirmed] Interim side scripts and one-off sheets | [assumed] Uses selected-lane-only prerequisites, a mandatory development header, run record, checking, and state-aware hash-bound delivery. |
| evaluator | [confirmed] KNOWNSCORE/DEVGRADE arithmetic and the legacy spectral_pilot score surface | [assumed] Prints one-to-one row differences with honest evidence scope, no scalar, no positive verdict, frozen panel membership, and named panel/baseline choosers. |
| evidence database | [confirmed] Chat plus prose evidence files and manual migration | [assumed] Commit-before-model capture, dispositions, immutable corrections, public all-class use counts, backups, and replay. It still cannot capture a bypassed session. |
| laser proof | [confirmed] Fail-open select_true_drops plus current offline skips | [assumed] Requires row-level phrase/drop proof and returns an exact refusal instead of restoring unproven drops. |
| checker | [confirmed] Long review chains, same-output reruns, and manual seat dispatch | [assumed] Reads the whole changed path, injects failures, uses dispatcher-owned acquisition, and drains one global unchecked backlog. It still cannot certify musical truth. |
| run state | [confirmed] Seat-owned chat state, heartbeats, loose reports | [assumed] Atomic states, one writer, leases, resume, no-model watcher, separate delivery state, and correction blocks. |
| storage | [confirmed] Loose dated growth | [assumed] Bounded scratch and loud protected-storage refusal; exact evidence still grows permanently. |

[confirmed] These are behavior changes, not renamed labels. [confirmed] None of the proposed
tools.spectral_listen, sender, dispatcher, intake wrapper, registry, or custody components exists
today, so v8 remains planned and earns no operational credit.

---

## Progress-gaming audit under v8

1. [confirmed] Fitting released marks or Lowkey remains possible; v8 labels that teacher/exposed
   work and forbids calling it fresh or general hearing.
2. [assumed] Swapping tracks, audio, evidence, substrate, or refusals inside a comparison returns
   NOT_COMPARABLE.
3. [assumed] Choosing a flattering panel or weak baseline before formal work remains possible; the
   report names both choosers and every track and emits no positive verdict.
4. [confirmed] Deleting unmatched output on partial keys cannot improve an error count because
   those rows are unjudged and no such count exists.
5. [assumed] One huge span can pair with only one mark and prints its full length/difference; it
   can still be musically wrong until the operator rules.
6. [assumed] A refusal cannot hide inside a READY body, and changing a ready panel track to refusal
   fires the floor.
7. [assumed] A caller-created checker failure cannot open the unchecked sender in v8; the
   dispatcher must complete the registered-adapter round. [confirmed] A person can still hand-paste
   output, and unregistered provider capacity remains unknowable.
8. [confirmed] The legacy spectral_pilot score can still run outside the new interface. [assumed]
   Its output cannot pass the v8 sender as an evaluation body without the required run id, body
   hash, evidence scope, and state.

---

## What v8 gives up, and what remains uncaught

1. [assumed] It gives up a machine-authored positive progress verdict. A truly better change can
   wait for operator judgment or a fresh blind.
2. [assumed] It gives up calling Lowkey held out. Fitting to it remains uncaught.
3. [assumed] It gives up arbitrary-track success promises. New codecs, classes, or missing phrase
   evidence can refuse.
4. [assumed] It gives up complete chat-capture claims. Unwrapped words can still be lost.
5. [assumed] It gives up automatic musical-length judgment. Visible absurd length may still wait
   for the operator's ear.
6. [assumed] It gives up claiming small permanent storage. Exact evidence can eventually stop work.
7. [assumed] It gives up claiming the dispatcher knows global provider capacity. It proves only
   which registered eligible adapters were offered the run and how they answered.
8. [assumed] It gives up letting newer governed work bypass an acknowledged unchecked backlog,
   even when the newer work comes from another builder.

---

## THE KILL SHOT

[confirmed] The single most likely death is still the operating-model build becoming the next
polished object while cold hearing remains at the dossier's 2 of 34. v8 adds one dispatcher seam
to the already-required checker path because without it Round 6's safety claim was false; it does
not add another program phase or move the hearing goal.

[assumed] If six weeks produce a clean sender, queue, database, census, and recovery drills but no
better fresh listening result, dossier §8.2 has recurred even if every mechanism works. v8 can make
that failure cheaper and more visible. It cannot choose the right hearing idea or reserve provider
capacity used by ordinary seats. That remains the residual risk that worries me most.

---

## Dossier §8 failure-mode table under v8

| # | Failure mode | Verdict | Scenario where it recurs anyway |
|---:|---|---|---|
| 1 | Confident output dies on his ear or eyes | UNCHANGED | [assumed] A verified, well-formed, honestly labelled list can still be musically wrong; only his ear rules. An unchecked sheet is visibly less protected. |
| 2 | Rigor spent on the wrong object | UNCHANGED | [assumed] Slice-first order and budgets bound cost; no mechanism chooses the right hearing idea, and ordinary seat spend remains outside the hearing queue. |
| 3 | Evidence unread or lost | UNCHANGED | [assumed] Wrapped input is reconciled; an unwrapped session can lose words until a later publish or forever. Wrapper feasibility is unknown. |
| 4 | Over-rotation on corrections | VISIBLE WITHIN A DAY on governed output | [assumed] Required fields and append-only supersessions expose surface loss; semantic over-rotation outside a covered mark still waits for his ear. |
| 5 | Settled laws re-broken | VISIBLE WITHIN A DAY on governed output | [assumed] The compiled buildup law refuses; taste laws and hand-paste can still recur. |
| 6 | Communication violations | UNCHANGED | [assumed] Bodies are shape-enforced; free prose can still be irrelevant, unclear, or answer around the question. |
| 7 | Delegated output consumed without verification | VISIBLE WITHIN A DAY | [assumed] Verified bodies require a checker; unchecked development requires dispatcher evidence, is labelled, enters the global oldest backlog, and triggers a named correction if it later fails. Hand-paste remains outside. |
| 8 | Seat/process mismanagement | VISIBLE WITHIN A DAY | [assumed] Ten-minute lines, leases, resume, dispatcher state, and local notices expose governed death; total provider/chat loss still silences the surface. |
| 9 | Building on missing or unvalidated deliverables | VISIBLE WITHIN A DAY | [assumed] Named lane refusals and the four-bucket census expose absence; an existing-but-wrong artifact survives until injection, a mark, or his ear. |

[confirmed] No whole mode is IMPOSSIBLE. The three UNCHANGED modes still have admitted six-week
paths, so a stronger verdict would be false.

---

## Enforcement audit

[confirmed] **Today:** every v8 mechanism is a design contract. tools.spectral_listen, its sender,
checker dispatcher, intake wrapper, experiment registry, lease launcher, and blind custody store
do not exist.

[assumed] **Enforced by code after the specified build:** the three body types and state-aware
hash-bound sender; mandatory headers and evidence-scope lines; all-or-nothing full-list
completeness; selected-lane dependencies; fail-closed laser proof; message dispositions and
all-class counts; one-to-one evaluation; no generated positive verdict; preregistered panel
membership; regression floor; dispatcher-owned acquisition rounds; global cross-builder
oldest-unchecked leasing; correction block; manifests and reproduction refusal; atomic state,
leases, resume, storage refusals, write fences, and future blind-key negative tests.

[assumed] **Enforced by someone remembering even after the build:** starting operator-facing
sessions through the wrapper; admitting an unwrapped session cannot record; not hand-pasting
governed-looking text; keeping the registered checker-adapter list complete; not starting
unregistered seats around the dispatcher; protecting hearing from ordinary seat spend; labelling
lease purpose honestly; choosing useful falsifiers, representative panels, and fair baselines;
classifying human_only/not_applicable honestly; keeping free prose plain; and initiating blind
tests only on the operator's word.

[unknown] **Enforced by nothing:** that a model hears the operator's sound classes; that Lowkey has
not been fitted; that a panel or baseline represents the library; that an unregistered provider has
capacity; that a future codec or sound class works before being tried; that an unwrapped message is
detected before a later publish; that the operator recognizes a stale capture line; that a
well-formed but musically wrong span is rejected without his ear or a compiled law; that permanent
evidence stays under a fixed size; that he remains willing to tolerate honest refusals; or that his
real chat surface can sit behind commit-before-model capture.

---

## Three six-week walkthroughs

1. **The manufactured checker failure.** [assumed] Under v7, the builder writes a fresh failed row
   before every send but never contacts a checker. Every sheet says unchecked; nothing falsifies the
   supporting claim. Under v8 only the dispatcher can create the round, every registered eligible
   adapter gets the exact run, and the operator line names the request. A missing or partial round
   cannot open the sender. Unregistered capacity remains an admitted limit.
2. **The builder-rotation queue jump.** [assumed] Under v7, builder A has the oldest unchecked run
   while replacement builder B keeps producing newer runs; the same checker takes B's work without
   violating the same-builder rule. Under v8 the dispatcher rejects B's lease and atomically gives
   the checker A's oldest delivered-unchecked run. Builder identity cannot jump the queue.
3. **The honesty machine wins while hearing loses.** [assumed] Step 1 lands and correctly governs
   one laser lane. The next month goes to SQLite, recovery, custody, and storage while no fresh
   hearing result improves. v8 reports every mechanism honestly and still fails the real goal.
   Nothing in this design can prevent that except the human duty to stop adoption spend and give
   hearing work the seat.

---

## Open questions and assumptions

1. [unknown] The full-library end-to-end refusal rate; the census cannot answer it.
2. [unknown] Whether missing phrase/drop evidence is buildable for most tracks.
3. [unknown] Whether the actual chat surface can sit behind commit-before-model intake.
4. [unknown] Whether two provider families can sustain builder/checker separation under real quota.
5. [unknown] Which registered provider adapters can actually perform automatic checker offers; v8
   specifies their contract but does not claim they exist.
6. [unknown] The accent lane's exact inputs.
7. [unknown] End-to-end time and storage for cached, unseen, refused, and 30-50-track runs.
8. [assumed] Ten minutes remains both the maximum silent progress interval and the checker-adapter
   acceptance timeout. It is a design choice grounded in the measured hours-long phases, not an
   operator-measured preference.
9. [assumed] The three-attempt blind limit, acceptance gate, and dossier operator laws remain fixed.
10. [assumed] Existing safeguards remain authoritative until each replacement passes and the
    operator approves a switch.

---

## Verification run this round

1. [confirmed] python3 tools/check_docs_metadata.py passed.
2. [confirmed] python3 tools/check_docs_drift.py passed.
3. [confirmed] python3 tools/check_ui_jargon.py passed for 13 files.
4. [confirmed] python3 tools/check_agent_contracts.py reports exactly one unclassified active doc:
   the new v8. The required classification write is outside this prompt's two-file boundary, so I
   did not change the doc index or registry.
5. [confirmed] python3 tools/check_docs_staleness.py --report completed with the same 12 unrelated
   stale contracts; this round changed no implementation file.
6. [confirmed] git diff --check passes for v8 and this record.
7. [confirmed] No unit suite was run because no executable code or tests changed. No bridge
   process, SoundSwitch, laser, LED/Govee, Rekordbox reader, runtime, or hardware check was
   attempted. Nothing here upgrades SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
