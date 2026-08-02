CHANGES REQUIRED

# Round 5 (SOL seat) — attack on v5, ruling on Round 4, and v6

[confirmed] I attacked
`docs/plans/active/spectral_program_operating_model_v5_2026_08_02.md` as a stranger's design,
verified Round 4's three cure claims against the actual v5 text, and found three defects worth
changing. They are enforcement edges, not a return to the direction failures in Rounds 1–3. The
next complete design is
`docs/plans/active/spectral_program_operating_model_v6_2026_08_02.md`.

[confirmed] This round changed only that v6 design and this record. I did not change code, config,
runtime, `local/`, existing round records, tmux seats, or hardware. I ran no git mutation command;
the workspace's automatic sync committed the earlier-round files during this audit and staged these
two new outputs.

[confirmed] Evidence opened and checked this round: v5, `ROUND_4_fable.md`, `ROUND_3_sol.md`,
`ROUND_2_fable.md`, `REVISION_ROUND_1.md`, `COMBINED_DESTROY_review.md`, and the failure dossier in
full; `smart_phrasing.py:700-810`; `combined1_runner.py:1120-1182`;
`KNOWNSCORE_scorecard.md:1-30`; `DEVGRADE1_scorecard.md:15-28`; `PROBE13_report.md:15-24`;
`LOWKEY1_scorecard.md:1-22`; `DEVSPLIT_2026_08_01.md:34-58`;
`PROGRAM_STATE_2026_07_31.md:44-72`; `RBPALL5_report.md:98-114`; the current command tree; and the
acceptance-format file. [confirmed] The acceptance-format SHA-256 still computes to
`80084cba17d49cb4fed4b8ecf0add0caa8f02bda5a60d57a43382238e97bb910`. [confirmed] No
`tools.spectral_listen` implementation exists.

---

## Findings, worst first

### F1. HIGH — Round 4's checker-outage cure uses a sender that v5 requires to reject it

[confirmed] **Location:** v5 lines 163-167 require every governed body to have a **published** run
id; lines 425-433 say an unchecked development sheet may be sent while its run stays
`WAITING_FOR_CHECKER`; lines 439-446 place `PUBLISHED` after `VERIFIED`; lines 496-500 repeat the
published-run-id requirement. v5 line 203 also describes an unchecked evaluation report even though
§8 permits only development sheets unchecked.

[confirmed] **What is wrong:** `WAITING_FOR_CHECKER` and `PUBLISHED` are different states in v5.
The degraded path cannot both remain waiting and satisfy a sender that accepts only a published run
id. One builder must reject the unchecked sheet; another must weaken the sender. The later
`CHECK_FAILED` correction is also only a sentence saying it “must be posted”; no component creates,
delivers, records, or blocks newer results on that correction.

[confirmed] **Why it matters:** Round 4 added this path specifically because real provider quota
walls otherwise drive useful laser work back to side scripts. The contradiction makes the claimed
pressure valve unusable at exactly that moment.

[assumed] **Concrete six-week failure:** the checker provider is unavailable for two weeks. The
laser development run reaches `WAITING_FOR_CHECKER`. The sender rejects it because it is not
`PUBLISHED`. A seat pastes the sheet manually so the operator gets an answer. The sheet has no
machine-enforced unchecked line or later correction, and the old ungoverned-window failure returns.

### F2. HIGH — v5's full-list template permits the partial list that its front door forbids

[confirmed] **Location:** v5 lines 93-100 define only two `listen` outcomes: all four lanes are
ready, or no list. v5 lines 179-194 then allow `Track energy` and `Drops` to contain “an explicit
refusal.” Its printer at lines 210-214 refuses a list that *lacks* a lane, but a refusal string can
make the field present.

[confirmed] **What is wrong:** two builders can implement opposite legal readings. One withholds
the list when track energy refuses. Another prints lasers and accents beside `Track energy:
refused`, because every named field exists. The second is a four-heading partial result dressed as
the acceptance list.

[confirmed] **Why it matters:** the original review's finding 5 was that a one-command slogan could
hide missing lanes and prerequisites. v5's strongest public promise is “complete list or one plain
reason.” Its own template reopens the partial-success path.

[assumed] **Concrete six-week failure:** laser and accent rows work on a track, but track energy
cannot be built. The printer accepts an explicit refusal in the track-energy field and sends the
rest as the full list. The operator reasonably reads the acceptance shape as a delivered four-part
answer even though one required part never existed.

### F3. MEDIUM-HIGH — preregistration freezes one comparison, but v5 overclaims that it prevents easy-panel gaming

[confirmed] **Location:** v5 lines 322-331 say a panel registered before the candidate's first
builder change prevents easy-track selection from becoming an improvement. Lines 473-477 repeat
that claim. Lines 588-590 correctly admit panel membership remains human judgment, but the short
operator version at lines 604-609 again says easy-track swaps cannot pose as improvement.

[confirmed] **What is wrong:** registration time can prove only that the named panel did not change
inside the named comparison. It cannot erase knowledge from earlier exploratory runs. A worker can
inspect a change on many tracks, learn which tracks flatter it, then register those tracks before a
formal candidate change. v5 prints the panel, which is useful visibility, but still allows its
evaluator to imply a positive verdict. That is not an anti-gaming mechanism.

[confirmed] **Why it matters:** easy-track selection is an explicit attack surface. The design must
not turn a visible but convenient panel into another machine-authored progress claim.

[assumed] **Concrete six-week failure:** exploratory work identifies 20 easy tracks out of 100. A
new experiment preregisters those 20 before its formal edit. Baseline and candidate match the panel,
so the comparison is legal. A generated “improved” sentence steers the next slot while the 80 hard
tracks are absent. The timestamp is true and the conclusion is still misleading.

---

## Outcomes in v6

| # | Outcome | Mechanism in v6 |
|---:|---|---|
| F1 | **CURED** | [assumed] v6:163-176 makes the sender state-aware and uses a sealed run id rather than pretending an unchecked run is published. Full lists and evaluations require `VERIFIED`; an unchecked development sheet alone may send from `WAITING_FOR_CHECKER`, records delivery, and stays waiting. v6:451-458 makes `CHECK_FAILED` create a fixed pending correction; the sender blocks every newer governed result until that exact notice is delivered. v6:473-478 separates delivery from analysis state. v6:546-559 names the failure tests. |
| F2 | **CURED** | [assumed] v6:188-207 removes refusal values from the full-list body and states that any lane refusal takes the no-list path. The printer cannot count a refusal string as a completed lane. v6:550 adds the partial-body refusal test. |
| F3 | **ACCEPTED LIMIT, made visible** | [assumed] v6:335-350 freezes membership inside one comparison but admits that prior exploratory knowledge can shape the initial panel. Every report names the chooser and every track and says the panel is not library-wide evidence. v6:344-350 bans generated positive verdicts; v6:505-509 and 647-654 repeat the real boundary. Panel wisdom remains human judgment. |

---

## Ruling on Round 4's cure claims — verified, not accepted

| Round 4 finding | Round 5 verdict |
|---|---|
| G1 — govern evaluation reports and Lowkey's label | [confirmed] **HOLDS as a build contract.** v5:43-52 fixes the three evidence-scope lines; v5:162-167 includes evaluation as one of the sender's three result bodies; v5:203-214 makes the printer refuse a missing or mismatched scope line; v5:317-320 makes evaluation a run bound to its body hash. The unchecked-evaluation sentence was contradictory but not needed by G1; v6:216-217 removes it. |
| G2 — require a preregistered comparison panel | [confirmed] **HOLDS only for membership inside the named comparison; Round 4's absolute anti-gaming claim was overstated.** Manifests and registration time close the ad-hoc no-panel door. They do not prove the initial panel was chosen without earlier exploratory knowledge (F3). v6 keeps the mechanical freeze and reclassifies representativeness as an accepted limit. |
| G3 — labelled degraded path through a checker quota wall | [confirmed] **REFUTED in v5.** The sender's published-id rule rejected the waiting state the path required, and the later correction had no enforcing component (F1). [assumed] v6 cures both with state-aware delivery and a pending-correction block. |

[confirmed] Round 4's convergence diagnosis was directionally right: this round found no return to
the invalid scalar, false negative keys, fake Lowkey custody, or fail-open laser proof. [confirmed]
It was still too early to say an earned agreement was plausible: one of its three new cures was
unimplementable as written, another was overstated, and an older all-or-nothing output rule still
contradicted its template.

---

## Full audit of the original fourteen findings

| # | Round 5 verdict after v6 |
|---:|---|
| 1 — partial keys call unknown rows wrong | [confirmed] **CURED by contract.** v6:25-39 and 364-366 call unmatched output unjudged on released examples; only an exposed complete lane/class scope may call it extra. This matches the current scorecard caveats re-read at `KNOWNSCORE:9`, `DEVGRADE1:20-22`, and `PROBE13:17-19`. |
| 2 — four cells pose as one undefined number | [confirmed] **CURED by removal.** v6:322-373 has no scalar, no within-a-beat bucket, deterministic one-to-one matching, and no positive verdict. [assumed] The automatic regression floor is limited to loss of an existing overlap or a new refusal on identical inputs. |
| 3 — the answer store leaks or contradicts the exam store | [confirmed] **CURED for future blind keys; Lowkey honestly conceded.** v6:54-70 records Lowkey as exposed; `LOWKEY1_scorecard.md:3-18` and the dossier already print every row. [assumed] v6:381-398 gives only future keys one-way custody. |
| 4 — the buildup guard rests on fail-open runtime truth | [confirmed] **CURED by contract.** Current `select_true_drops` still fails open at `smart_phrasing.py:782-797`, and missing phrases still yield zero runway at `:714-739`. [assumed] v6:231-253 forbids using that selector as the safety decision and refuses absent phrase/drop proof. |
| 5 — `listen` is a slogan over missing prerequisites | [confirmed] **CURED as a build contract, still unbuilt.** The current runner really skips missing drop/grid/frame/audio at `combined1_runner.py:1127-1175`, and three lanes remain open or unintegrated in `PROGRAM_STATE:48-61`. [assumed] v6:80-157 names resolution, buildable inputs, lane-specific refusals, no stale identity, and progress. F2 closes the last partial-list ambiguity. |
| 6 — evidence can drift while looking current | [confirmed] **PARTLY CURED, PARTLY ACCEPTED LIMIT.** [assumed] v6:250-318 gives wrapped messages ids, dispositions, immutable corrections, reconciliation, backups, and all-class public counts. [confirmed] v6:302-305 and 606-614 admit an ordinary unwrapped session can still lose words until a later publish. |
| 7 — optimizing the development scoreboard can make hearing worse | [confirmed] **CONTAINED, NOT SOLVED.** v6 removes the scoreboard, labels released material as teacher material, bans generated positive verdicts, and reserves generalization language for a fresh blind. [assumed] F3 remains: convenient panel choice and weak falsifiers are visible human judgments, not prevented facts. |
| 8 — the checker proves repetition, not truth | [confirmed] **CURED as an overclaim.** [assumed] v6:402-458 requires full-path reads, clean-bundle rerun, and failure injection while saying repetition is not musical truth. The unchecked development exception is labelled, stored, and corrected; it is not described as checked. |
| 9 — the old program is merely renamed with fewer checks | [confirmed] **CURED only if staged adoption passes.** The behavior mapping below shows real changes, while v6:538-581 keeps current safeguards until each replacement is independently verified. [confirmed] Nothing earns present-tense credit today. |
| 10 — seat death and provider quota break the three-seat model | [confirmed] **CURED as a build contract, unmeasured.** [assumed] v6:462-491 specifies atomic states, leases, resume, local notices, and total-provider-loss limits. F1 repairs the checker-outage surface. [unknown] Provider-family capacity remains unmeasured. |
| 11 — history cannot reproduce its displayed result | [confirmed] **CURED by contract.** [assumed] v6:408-432 pins source, patch, command, environment, evidence, audio, every derived input, implementation versions, refusals, outputs, panel, and delivery state; reproduction refuses missing bytes. |
| 12 — automatic work killing serves a fake metric | [confirmed] **CURED.** [assumed] v6:495-512 rejects only on a runnable falsifier, identical-panel regression floor, compiled law, isolation failure, or operator veto; budget exhaustion pauses. |
| 13 — communication and paper-growth promises remain discipline | [confirmed] **PARTLY CURED, PARTLY ACCEPTED LIMIT.** [assumed] The printer, sender, mandatory first lines, state rules, and storage refusals enforce governed bodies. [confirmed] v6:616-633 admits hand-paste, free prose, classifications, panel choice, and slot choice remain judgment. |
| 14 — time/cost claims are unsupported and permanent storage grows | [confirmed] **PARTLY CURED, PARTLY ACCEPTED LIMIT.** v6 makes no unmeasured speed promise; v6:522-526 blocks adoption until storage is measured and bounds scratch. [assumed] Exact evidence grows for the program's life and can stop work at the protected limit. |

---

## Audit of Round 2's eight findings

| Round 2 finding | Round 5 verdict after v6 |
|---|---|
| F1 — governed door unusable until all four lanes land | [confirmed] **CURED by contract.** v6:135-176 gives `develop` only its selected lane's gates and the same sender. [assumed] Another lane cannot refuse it. |
| F2 — unwrapped same-surface session bypasses capture | [confirmed] **ACCEPTED LIMIT remains honest.** v6:302-305 and 606-614 name the bypass and no within-day guarantee. |
| F3 — Lowkey had no real custody class | [confirmed] **Round 2's cure was wrong; Round 3's reclassification remains correct.** Current files expose all seven rows. v6:54-70 never calls Lowkey hidden. |
| F4 — “breaks a released example” was undefined | [confirmed] **CURED.** v6:368-373 defines only lost overlap/not-evaluated/new-refusal as an automatic regression floor; every other difference waits for judgment. |
| F5 — evidence-use escape classes were invisible | [confirmed] **CURED for visibility.** [assumed] v6:277-293 prints all five classes, accounts for their union, and exposes overlap; classification correctness remains human. |
| F6 — fail-closed proof may refuse much of the library | [confirmed] **CURED only as honest measurement.** [assumed] v6:563-568 calls the four-bucket pass a prerequisite census, not an end-to-end refusal rate. [unknown] The real rate remains unknown. |
| F7 — long stages can leave hours of silence | [confirmed] **CURED by contract.** v6:126-133 caps silence at ten minutes without a model call, against the re-read 5.49/5.71-hour phase evidence. |
| F8 — evaluation chat shape was unspecified | [confirmed] **CURED by contract.** v6:359-377 prints the operator's mark first in plain rows and bans glyph grids and internal columns. |

---

## Audit of Round 3's eight findings

| Round 3 finding | Round 5 verdict after v6 |
|---|---|
| F1 — Lowkey custody protects already-published answers | [confirmed] **CURED by truthful reclassification.** v6:54-70 calls it exposed complete regression, never blind. |
| F2 — `develop` can inherit unrelated full-list refusals | [confirmed] **CURED by contract.** v6:141-157 gives an explicit dependency matrix and forbids unrelated lane gates. |
| F3 — “same inputs” did not bind baseline and candidate | [confirmed] **CURED for comparison membership.** v6:335-350 binds both manifests to one panel and returns `NOT_COMPARABLE` on any change. [confirmed] F3 in this round limits the claim to that real boundary. |
| F4 — surface enforcement began after the claimed switch | [confirmed] **CURED for the output surface.** v6:546-554 lands proof, printer, run record, checker, header, sender, and state tests as one switch. [confirmed] The pre-database hearing-slot rule at v6:583-587 is still enforced by someone remembering; v6 does not pretend otherwise. |
| F5 — `not_applicable` hid recorded non-use | [confirmed] **CURED for visibility.** v6:277-293 includes it in the public total and blocks an incomplete union. |
| F6 — the “refusal census” measured files, not refusal behavior | [confirmed] **CURED by reclassification.** v6:563-568 separates ready, build-required, refused-now, and unknown and forbids an end-to-end claim. |
| F7 — stage updates could still be 5.7 hours apart | [confirmed] **CURED by the ten-minute local line.** v6:126-133. |
| F8 — capture-gap visibility was overstated as within a day | [confirmed] **ACCEPTED LIMIT remains honest.** v6:606-614 says only a later governed publish plus operator recognition may expose it. |

---

## Is it the old program renamed?

| v6 element | What it replaces | Behavior change if built |
|---|---|---|
| `listen` | [confirmed] Manifest-driven `combined1_runner.py` plus separate lane tools | [assumed] Resolves/builds or returns one named no-list reason; never skips or returns a four-lane partial body. |
| `develop` | [confirmed] Interim side scripts and one-off sheets | [assumed] Selected-lane-only prerequisites, mandatory development header, run record, checking, and state-aware hash-bound delivery. |
| Evaluator | [confirmed] KNOWNSCORE/DEVGRADE scorecards and per-seat arithmetic | [assumed] One-to-one row differences, partial-key unjudged output, no scalar, no positive verdict, fixed panel membership, named chooser. |
| Evidence database | [confirmed] Chat plus prose evidence files and manual migration | [assumed] Commit-before-model intake, dispositions, immutable corrections, public use counts, backup and replay. It still cannot capture a bypassed session. |
| Laser proof | [confirmed] Fail-open `select_true_drops` plus current offline skips | [assumed] Row-level fail-closed proof with exact refusal and stored inputs. |
| Checker | [confirmed] Long review chains and same-output reruns | [assumed] Clean retained bundle, every changed path, injected failures, explicit no-musical-truth claim, and a labelled unchecked development exception. |
| Run state | [confirmed] Seat-owned chat state, heartbeat prompts, and loose reports | [assumed] Atomic run ids, leases, resume, no-model watcher, separate analysis/delivery state, and correction blocks. |
| Storage | [confirmed] Loose dated growth | [assumed] Content-addressed bounded scratch and loud protected-storage refusal; permanent evidence still grows. |

[confirmed] These are behavior changes rather than new labels. [confirmed] None exists under the
named interface today, so v6 remains `planned` and hardware-unvalidated.

---

## Progress-gaming audit under v6

1. [confirmed] **Fitting released marks or Lowkey:** allowed and visible as teacher-set work; it
   cannot be called fresh or general hearing.
2. [assumed] **Changing tracks inside one comparison:** refused by panel/manifests, including new
   refusals and changed audio identity.
3. [assumed] **Choosing a flattering panel before formal work:** still possible. v6 names the
   chooser and every track and bans a generated positive verdict. That makes the judgment visible;
   it does not make the panel representative.
4. [confirmed] **Deleting unmatched output on partial keys:** cannot improve an error count because
   those rows are unjudged and no such count exists.
5. [assumed] **One huge output span:** it can pair with only one mark, and its full length and
   difference print. It may remain musically wrong until the operator rules.
6. [assumed] **Hiding refusals:** a changed refusal makes the panel not comparable and fires the
   regression floor; a refusal cannot appear inside a READY full-list body after F2.
7. [assumed] **Inventing a progress scalar or positive sentence:** the governed evaluator and sender
   reject it. [confirmed] A person can still type one in free prose; missing run id and scope line
   are tells, not a physical block.

---

## What v6 gives up, and what remains uncaught

1. [assumed] It gives up a machine-authored positive progress verdict. Work selection remains
   recorded judgment; a genuinely better change may wait for the operator or a fresh blind.
2. [assumed] It gives up claiming preregistration makes the chosen panel representative. Earlier
   exploratory knowledge and convenient panel choice remain uncaught.
3. [assumed] It gives up pretending an unchecked sheet is published or verified. Its delivery is a
   separate fact and can still contain a defect the checker later finds.
4. [assumed] It gives up partial full-list success. One missing lane means no acceptance list.
5. [assumed] It keeps the earlier concessions: Lowkey is exposed; arbitrary tracks may refuse;
   unwrapped chat may lose evidence; musical length needs his ear or a compiled law; exact permanent
   evidence grows.

---

## THE KILL SHOT

[confirmed] The most likely death is still that the operating-model build becomes the next polished
object while the machine's hearing remains at the dossier's 2 of 34. v6 stops three misleading
surface claims, but it still proposes a sender, evaluator, intake database, checker isolation,
leases, recovery, custody, and storage controls. [assumed] If six weeks produce those controls and
no better cold hearing result, the redesign has repeated dossier §8.2 even if every mechanism works.
The one-slice-first order and reserved hearing intent bound the damage; they do not choose the right
hearing experiment, and the hearing-slot reservation is still remembered rather than enforced
before the database exists.

---

## Dossier §8 failure-mode table under v6

| # | Failure mode | Verdict | Scenario where it recurs anyway |
|---:|---|---|---|
| 1 | Confident output dies on his ear or eyes | `UNCHANGED` | [assumed] Structural lies refuse, but a verified and well-formed list can still be musically wrong; an unchecked development sheet adds the checker's missing margin visibly. |
| 2 | Rigor spent on the wrong object | `UNCHANGED` | [assumed] Slice-first order, budgets, and hearing-slot intent limit cost; no mechanism chooses the right hearing idea. |
| 3 | Evidence unread or lost | `UNCHANGED` | [assumed] Wrapped input is reconciled; an unwrapped session can lose exact words until a later publish, or longer. |
| 4 | Over-rotation on corrections | `VISIBLE WITHIN A DAY` on governed output | [assumed] Required fields and immutable supersessions expose surface loss; semantic over-rotation outside a covered mark still waits for his ear. |
| 5 | Settled laws re-broken | `VISIBLE WITHIN A DAY` on governed output | [assumed] The compiled laser buildup law refuses; non-compilable taste laws and hand-paste can still recur. |
| 6 | Communication violations | `UNCHANGED` | [assumed] Result bodies are shape-enforced; free prose can still be irrelevant, unclear, or fail to answer the question. |
| 7 | Delegated output consumed without verification | `VISIBLE WITHIN A DAY` | [assumed] Verified bodies require an independent checker; unchecked development is labelled immediately and a later failure blocks newer governed output until correction. Hand-paste remains outside. |
| 8 | Seat/process mismanagement | `VISIBLE WITHIN A DAY` | [assumed] Ten-minute notices, leases, resume, and local recovery expose governed death; total provider/chat loss still delays the surface. |
| 9 | Building on missing or unvalidated deliverables | `VISIBLE WITHIN A DAY` | [assumed] Named lane refusals and the four-bucket census expose absence; an artifact that exists but is wrong can survive until checker injection, a mark, or the operator's ear. |

[confirmed] No whole dossier mode is `IMPOSSIBLE`. The three `UNCHANGED` modes have admitted paths
that can last six weeks, so a stronger verdict would be false.

---

## Enforcement audit

[confirmed] **Today:** every v6 mechanism is a design contract. Nothing named
`tools.spectral_listen`, its state-aware sender, intake wrapper, experiment registry, lease watcher,
or blind custody store exists in the current tree.

[assumed] **Enforced by code after the specified build:** exact full-list/development/evaluation body
types; mandatory headers and evidence-scope lines; sealed run ids and body hashes; body-to-state
rules; the unchecked-development exception; pending failed-sheet corrections and newer-result
block; all-or-nothing full-list completeness; selected-lane prerequisites; fail-closed laser proof;
message dispositions and all-class use totals; one-to-one matching; no generated positive verdict;
panel membership equality; refusal regression floor; manifests and reproduction refusal; atomic run
state; leases/resume; storage limits; write fences; blind-attempt counter and key-access negative
test.

[assumed] **Enforced by someone remembering after the build:** start operator-facing sessions
through the wrapper; admit an unwrapped session cannot capture; do not hand-paste governed-looking
text; choose useful falsifiers and representative panels; classify `human_only` and
`not_applicable` honestly; choose the next slot wisely; keep free prose plain and relevant; initiate
blind tests only with operator approval; preserve the hearing slot before the experiment database
and launcher exist.

[unknown] **Enforced by nothing:** that any model hears the operator's sound classes; that Lowkey
has not been fitted; that a chosen panel represents the library; that a future codec or class works
before it is tried; that an unwrapped message is detected before a later publish; that the operator
recognizes a stale last-message line; that a well-formed but musically wrong span is rejected without
his ear or a compiled law; that provider quota is available; that permanent evidence stays under a
fixed size; that the operator remains willing to tolerate honest refusals; that the real chat surface
can sit behind commit-before-model capture.

---

## Three six-week walkthroughs

1. **Checker outage.** [confirmed] Under v5, a waiting run could not satisfy the published-id sender.
   [assumed] Under v6, only the development sheet sends from `WAITING_FOR_CHECKER`, with its stored
   unchecked line. A later failed check creates the fixed correction and blocks newer governed
   results until delivery. Manual paste can still bypass, but the sanctioned door no longer forces
   that bypass.
2. **Partial acceptance list.** [confirmed] Under v5, `Track energy: explicit refusal` could coexist
   with laser/accent rows in the full-list template. [assumed] Under v6, the printer rejects that body
   and the operator gets one plain no-list reason. The acceptance shape cannot hide a missing lane.
3. **Convenient comparison panel.** [assumed] A worker uses prior exploratory knowledge to choose 20
   flattering tracks. v6 cannot unteach that knowledge. It prints all 20, names the chooser, and
   never emits “improved”; the front desk may still choose badly. Six weeks later a hard fresh track
   can fail, but the record contains no machine claim that the 20-track panel proved general hearing.

---

## Open questions and assumptions

1. [unknown] The full-library end-to-end refusal rate; the prerequisite census cannot answer it.
2. [unknown] Whether missing phrase/drop evidence is buildable for most tracks.
3. [unknown] Whether the actual chat surface can sit behind commit-before-model intake.
4. [unknown] Whether two provider families can sustain builder/checker separation under real quota.
5. [unknown] The accent lane's exact inputs.
6. [unknown] End-to-end time and storage for cached, unseen, refused, and 30–50-track runs.
7. [assumed] Ten minutes remains the maximum silent interval; it is a design choice grounded in the
   measured hours-long stages, not an operator-measured preference.
8. [assumed] The three-attempt blind limit, acceptance gate, and dossier operator laws remain fixed.
9. [assumed] Existing safeguards stay authoritative until each replacement passes and the operator
   approves a switch.
10. [assumed] Before the experiment database exists, the reserved hearing slot remains a remembered
    duty rather than a machine reservation; v6 lists it honestly instead of calling it enforced.

---

## Verification run this round

1. [confirmed] `python3 tools/check_docs_metadata.py` passed.
2. [confirmed] `python3 tools/check_docs_drift.py` passed.
3. [confirmed] `python3 tools/check_ui_jargon.py` passed for 13 files.
4. [confirmed] `python3 tools/check_agent_contracts.py` reports one new expected boundary failure:
   v6 is an unclassified active doc. The named cure is updating the doc index or active-work
   registry, but the convergence prompt permits writes only to v6 and this record, so I did not cross
   that boundary.
5. [confirmed] `python3 tools/check_docs_staleness.py --report` completed and reported the same class
   of advisory implementation/doc staleness outside this two-file design round: 12 contracts. This
   round changed no implementation file and did not attempt those unrelated re-verifications.
6. [confirmed] No unit suite was run because no executable code or tests changed. No runtime,
   bridge process, SoundSwitch, laser, LED/Govee, Rekordbox, or hardware validation was attempted.
