# Round 3 (SOL seat) — attack on v3, ruling on round 2, and v4

[confirmed] **Verdict: CHANGES REQUIRED.** I attacked
`docs/plans/active/spectral_program_operating_model_v3_2026_08_02.md`, verified Round 2's cures
against current files, and found seven failed or incomplete cures plus one overstated accepted
limit. The next design is
`docs/plans/active/spectral_program_operating_model_v4_2026_08_02.md`.

[confirmed] This was design work only. I changed no code, config, runtime, `local/` artifact, tmux
seat, git state, or hardware. The only files written this round are this record and the v4 design.

[confirmed] Evidence opened: v3 in full; `ROUND_2_fable.md`, `REVISION_ROUND_1.md`, and
`COMBINED_DESTROY_review.md` in full; the failure dossier in full; `smart_phrasing.py:700-810`;
`combined1_runner.py:1120-1185`; `KNOWNSCORE_scorecard.md:1-30`;
`DEVGRADE1_scorecard.md:15-28`; `PROBE13_report.md:15-24`; `DEVSPLIT_2026_08_01.md:34-55`;
`PROGRAM_STATE_2026_07_31.md:40-72`; `RBPALL5_report.md:100-114`; the current file tree; and the
pinned acceptance-format hash. The hash remains
`80084cba17d49cb4fed4b8ecf0add0caa8f02bda5a60d57a43382238e97bb910`.

---

## Findings, worst first

### F1. CRITICAL — the Lowkey custody cure protects a key that is already printed everywhere

[confirmed] **Location:** v3 lines 47-63 and 370-380; Round 2 F3 and its outcome.

[confirmed] **What is wrong:** v3 correctly says Lowkey is program-exposed at lines 47-52, then
says its row-level content will live only outside the builder environment and builders will never
read it at lines 54-63. That cannot be made true. The current failure dossier itself prints all
seven timestamps and their seven-beat length at lines 97-98. The same rows are in
`LOWKEY1_scorecard.md:3-18`, `OPERATOR_SOUND_DESCRIPTIONS_VERBATIM.md:752-764`, many COMBINED1
specs, program state, and the trail. A targeted current-tree search found dozens of worker-readable
copies.

[confirmed] **Why it matters:** the only complete current key can still grade known Lowkey output,
but it cannot catch quiet fitting by a builder who already knows every answer. Round 2's sentence
that it can detect regression forever "because no builder can quietly fit code" is refuted by the
current files.

[assumed] **Concrete six-week failure:** Lowkey moves behind a separate account. A builder reads the
same seven rows from the dossier or scorecard, tunes until the evaluator cells improve, and reports
the protected regression as independent evidence. Access tests pass because the protected copy was
never opened. A fresh track then fails.

### F2. HIGH — `develop` can inherit the full-list refusal and defeat the cure it was added to provide

[confirmed] **Location:** v3 lines 129-146. It says a single-lane run uses the same sealed grid and
buildup proof as `listen`, and that everything refusing `listen` refuses `develop` identically.

[confirmed] **What is wrong:** `listen` refuses with `LANE_INCOMPLETE` when any of four lanes is
missing. If that refusal is identical, every single-lane run still refuses until all four lanes
exist. The shared buildup proof also makes track energy depend on phrase and drop evidence it does
not use. Two builders can read the text differently, so Round 2's F1 cure is not a build contract
that forces the same behavior.

[confirmed] **Why it matters:** the design can return to the exact v2 failure: the governed
development door refuses, interim work returns to side scripts, and a forbidden laser row reaches
the operator outside the claimed controls.

[assumed] **Concrete six-week failure:** track-energy code lands first. `develop --lane
track_energy` sees missing accent implementation or sparse phrase data and inherits
`LANE_INCOMPLETE` or `DROP_PROOF_MISSING`. The team bypasses it to inspect output, so the same
months-long ungoverned window remains.

### F3. HIGH — the evaluator does not mechanically enforce its phrase “with the same inputs”

[confirmed] **Location:** v3 lines 309-361 and 480-493. The command evaluates one run id. The
automatic regression definition says “with the same inputs,” but no command or comparison contract
binds a baseline and candidate to one frozen track panel.

[confirmed] **What is wrong:** manifests record what each run requested, but the evaluator does not
require two runs to contain the same ordered tracks, audio hashes, evidence snapshot, substrate, or
refusals. A worker can run the candidate on easy tracks or omit a newly refused track. Every
individual run remains exact and reproducible while the comparison is false.

[confirmed] **Why it matters:** easy-track selection and refusal hiding are named attack surfaces.
They let a development result look safer without the machine hearing better, recreating metric
gaming without needing a scalar score.

[assumed] **Concrete six-week failure:** the baseline includes 34 hard tracks. The candidate report
uses 20 easy tracks and omits codec failures. Its visible cells improve. Nothing in v3's evaluator
returns `NOT_COMPARABLE`, and the cleaner report attracts the next resource slot.

### F4. HIGH — the “surface first” order starts surface enforcement two steps late

[confirmed] **Location:** v3 lines 527-576. Step 1 claims no sheet reaching the operator can carry a
buildup laser, but the run-id sender does not start until step 3 at lines 547-548.

[confirmed] **What is wrong:** a printer bound to one existing runner controls only calls that use
it. Before the sender and run record are active, side scripts and old delivery paths remain able to
send sheets. The design claims a surface result before the surface enforcement exists. “Hearing
work never pauses” at lines 533 and 575 is also an instruction, not a resource reservation.

[confirmed] **Why it matters:** the adoption order was Round 2's answer to its kill shot. If its
first visible promise is not enforced, the redesign can spend weeks on machinery and still ship the
same bad interim sheet.

[assumed] **Concrete six-week failure:** step 1's tests pass in isolation. A current side script,
which has no run id because that requirement is step 3, supplies the next operator answer and prints
a buildup row. The program calls step 1 adopted even though the only surface he reads was never
switched.

### F5. MEDIUM-HIGH — `not_applicable` is the new invisible “used six of 54” escape valve

[confirmed] **Location:** v3 lines 250-252 allow five evidence-use classes, including
`not_applicable`; lines 278-282 print only four counts and omit it.

[confirmed] **What is wrong:** a seat can classify most judgments `not_applicable`, keep a written
reason, and publish a header whose visible categories do not add to the claimed total. Round 2 F5
specifically claimed it cured invisible non-use at the operator surface, but one of the two escape
classes remains invisible.

[confirmed] **Why it matters:** recorded neglect is still neglect if the only surface the operator
reads omits its count.

[assumed] **Concrete six-week failure:** 48 of 54 judgments become `not_applicable`; six appear in
the four printed buckets. The header still says 54 total, but no mechanism rejects the missing 48.
The program again uses six while its receipt appears complete.

### F6. MEDIUM — the refusal census measures current files, not the refusal behavior it claims

[confirmed] **Location:** v3 lines 549-554 and 591-593. The census treats missing grids and frames
as reasons a track cannot print, while v3 lines 115-119 promise that `listen` builds missing grids,
frames, and lane data.

[confirmed] **What is wrong:** “missing but buildable,” “terminal refusal,” and “unknown until a
full decode/model run” are different states. The proposed no-heavy-compute census collapses them
into “can print” versus refusal. It can overstate refusal for buildable tracks and understate codec
or model failures that appear only during real work.

[confirmed] **Why it matters:** Round 2 F6 called this a cure for the unknown library refusal rate.
It is a useful prerequisite inventory, but it is not that rate and would hand the operator another
confident number whose meaning is not what its sentence says.

[assumed] **Concrete six-week failure:** 400 tracks lack frames but have readable audio. The census
says they cannot print; `listen` was designed to build frames. Another 20 pass file checks and fail
only during decode. The headline is wrong in both directions.

### F7. MEDIUM — “one line per stage” still permits 5.7 hours of silence

[confirmed] **Location:** v3 lines 121-127. The current large-run evidence at
`RBPALL5_report.md:102-110` records single model phases of 5.49 and 5.71 hours.

[confirmed] **What is wrong:** if a stage is the model phase, v3 allows the exact hours-long silence
it claims to cure. “Silence longer than a stage is a defect” has no useful upper bound.

[confirmed] **Why it matters:** the operator's “hello???” failure happens during a long stage, not
only between stages. Round 2 F7's cure therefore does not hold.

[assumed] **Concrete six-week failure:** the wrapper announces “building frames,” enters one
five-hour phase, and says nothing until completion. The process dies after hour four. Nobody knows
whether it is slow or dead until the lease expires or a person checks.

### F8. MEDIUM — the accepted capture limit is honest, but “visible within a day” is not

[confirmed] **Location:** Round 2 F2 correctly downgraded unwrapped same-surface capture to an
accepted limit. Its §8 table then calls the failure `VISIBLE WITHIN A DAY`; v3 lines 260-266 and
295-303 expose it only on the next governed publish, and only if the operator remembers a later
message than the header.

[confirmed] **What is wrong:** no daily publish is required, and the database cannot know an
unwrapped message exists. The header is a useful tell, not a detection clock.

[confirmed] **Why it matters:** a quiet week of unwrapped corrections can still remain invisible
for six weeks if no governed output arrives or the stale first words are not recognized.

[assumed] **Concrete six-week failure:** an unwrapped seat records nothing for a week; the next
governed publish is a month later. The header exposes a gap then, not within a day. The lost words
still have to be repeated.

---

## Outcomes in v4

| # | Outcome | Mechanism in v4 |
|---:|---|---|
| F1 | **CURED** | [assumed] §1 reclassifies Lowkey as exposed complete regression, forbids hidden/generalization claims, and makes future custody one-way: diagnostic release turns a key exposed. |
| F2 | **CURED** | [assumed] §2 gives every lane a prerequisite matrix; other lanes and irrelevant laser proof cannot refuse a selected-lane run; missing selected inputs return `LANE_INPUT_MISSING`. |
| F3 | **CURED** | [assumed] §§6 and 10 pin the ordered evaluation panel, evidence and substrate before work; baseline/candidate mismatch returns `NOT_COMPARABLE`; refusals cannot disappear. |
| F4 | **CURED** | [assumed] §12 step 1 switches proof, printer, minimal run record, checker, header, and run-id sender together before claiming a governed surface. Hand-pasted text remains a separate accepted limit. Adoption cannot consume the last hearing slot. |
| F5 | **CURED** | [assumed] §5 prints all five evidence-use classes, requires their union to account for every active judgment, and exposes overlapping uses or blocks publication. |
| F6 | **CURED** | [assumed] §12 step 4 reports `ready now / build required / refused now / unknown until full run`, calls itself a prerequisite census, and bans “can print” without an exact checked run. The actual rate remains unknown. |
| F7 | **CURED** | [assumed] §2 requires a local, no-model-call progress line at least every ten minutes and a death notice by the same deadline. |
| F8 | **ACCEPTED LIMIT** | [assumed] §§5 and 13 say detection is only on a later governed publish and may still require the operator's memory; no within-day claim remains. |

---

## Ruling on Round 2's cure claims

| Round 2 finding | Round 3 verdict |
|---|---|
| F1 — development door | [confirmed] **Refuted in v3.** The door exists as a proposed name, but identical full-list refusals and irrelevant gates can make it refusal-only; sender enforcement starts two adoption steps late. v4 F2/F4 cure it. |
| F2 — unwrapped session | [confirmed] **Accepted-limit downgrade stands; timing claim does not.** The header can help on a later publish, not guarantee visibility within a day. v4 F8 states the real bound. |
| F3 — Lowkey custody | [confirmed] **Refuted.** Current worker-readable files contain every row. v4 F1 reclassifies rather than pretending to unpublish. |
| F4 — defined released-example regression | [confirmed] **Definition stands, comparison enforcement was incomplete.** v3 defines the floor, but one-run evaluation does not pin equal inputs. v4 F3 adds the two-manifest check. |
| F5 — visible evidence use | [confirmed] **Refuted in part.** `not_applicable` is legal but absent from the public counts. v4 F5 closes it. |
| F6 — refusal-rate measurement | [confirmed] **Refuted.** The proposed inventory is not an end-to-end refusal rate. v4 F6 renames and separates its states. |
| F7 — long-path silence | [confirmed] **Refuted.** A stage can last 5.7 hours. v4 F7 adds a clock bound without model heartbeats. |
| F8 — plain evaluation rendering | [confirmed] **Stands.** v3 pins his mark first, one plain line, no symbol grid. v4 preserves it. |

[confirmed] Round 2's accepted-limit downgrade for capture was directionally correct. Its
develop-lane and surface-first additions were also the right direction, but their enforcement did
not yet match their claims. v4 keeps both and changes the mechanics.

---

## Audit of the original fourteen findings

| Original finding | Round 3 ruling after v4 |
|---:|---|
| 1. Partial keys call unknown rows wrong | [assumed] **CURED by contract.** Partial-key unmatched output is always unjudged. |
| 2. One number undefined/gameable | [assumed] **CURED by removal.** Separate cells remain; no combined ordering or progress claim exists. |
| 3. Key boundary contradicts itself | [confirmed] **Blind future keys are cured; Lowkey was not.** v4 F1 removes the false Lowkey custody claim. |
| 4. Buildup guard fails open | [assumed] **CURED by contract.** §4 refuses independently of fail-open runtime selection and names the absent-phrase test. |
| 5. `listen` hides prerequisites | [assumed] **CURED by contract, unbuilt.** Named refusals, build paths, lane-specific prerequisites, and visible progress exist in v4. |
| 6. Evidence can drift unseen | [assumed] **CURED only inside the wrapper; outside is an accepted limit.** Transactions/replay protect captured input; the unwrapped path remains. |
| 7. Development optimization can fake hearing | [assumed] **Contained, not solved.** Teacher-set movement cannot certify generalization; panels cannot swap; Lowkey is labelled exposed; only future blind evidence generalizes. |
| 8. Checker verifies repetition only | [assumed] **CURED as an overclaim.** The checker reads the full changed path and injects failures, while the design explicitly says repeatability is not musical truth. |
| 9. Old program merely renamed | [assumed] **CURED only after staged adoption.** Old checks retire one replacement at a time; the mapping below names real behavior changes. |
| 10. Seats die or share quota | [assumed] **CURED by build contract, unmeasured.** Leases, atomic publish, resume, local notices, and provider-family separation refuse rather than guess. |
| 11. History cannot reproduce | [assumed] **CURED by manifest contract.** Every input byte/version and refusal denominator is retained or reproduction refuses. |
| 12. Automatic work kill serves a fake metric | [assumed] **CURED.** Budgets pause; only a runnable falsifier, identical-panel regression floor, compiled law, isolation failure, or operator veto rejects. |
| 13. Communication/paper growth remains discipline | [assumed] **Partly cured, partly accepted.** Sender and write fences enforce shape; free prose and hand-paste remain limits. |
| 14. Unsupported size/cost and permanent growth | [assumed] **Partly cured, partly accepted.** Measurements precede claims; scratch is bounded; permanent evidence growth remains explicit. |

---

## Is it the old program renamed?

| v4 element | What it replaces | Behavior change, if built |
|---|---|---|
| `listen` | [confirmed] Manifest-driven `combined1_runner.py` plus separate lane tools | [assumed] Resolves/builds or returns one named refusal; never skips or prints a four-lane partial list. |
| `develop` | [confirmed] Interim side scripts and one-off sheets | [assumed] Single-lane governed output with only that lane's inputs, mandatory header, run record, checker, and hash-bound sender. |
| Evaluator | [confirmed] KNOWNSCORE/DEVGRADE scorecards and per-seat arithmetic | [assumed] One-to-one differences, partial-key unjudged rows, no scalar, fixed baseline/candidate panel. |
| SQLite intake | [confirmed] Chat, prose evidence files, and manual migration | [assumed] Commit-before-model capture, dispositions, append-only corrections, full visible use counts, checked backups and replay. It cannot capture bypassed sessions. |
| Buildup proof | [confirmed] Fail-open `select_true_drops` label and current offline skips | [assumed] Row-level fail-closed proof with exact refusal and saved inputs. |
| Full-path checker | [confirmed] Long review chains and same-output reruns | [assumed] Clean-bundle rerun plus all changed path files and injected identity/substrate/evidence/death failures; no claim of musical truth. |
| Leases/run records | [confirmed] Seat-owned chat state, heartbeat prompts, loose reports | [assumed] Atomic publish, expiry, resume token, no-model watcher, reproducible manifest. |
| Content-hash store | [confirmed] Loose dated output growth | [assumed] Bounded scratch and loud protected-storage exhaustion; permanent evidence still grows. |

[confirmed] These are behavioral changes, not only names. [assumed] None exists today, so the
design earns no present-tense operational credit for them.

---

## Progress-gaming audit

1. [confirmed] **Fitting marked tracks:** allowed on released examples and Lowkey because they are
   teacher material. [assumed] It cannot be called generalization, and only a future first-run blind
   can add that evidence.
2. [assumed] **Easy-track selection:** v4 blocks comparative claims unless baseline and candidate
   match one predeclared panel byte-for-byte in identity/evidence/substrate. Mismatch is
   `NOT_COMPARABLE`.
3. [confirmed] **Unmatched rows on partial keys:** cannot be called wrong. [assumed] They remain
   unjudged, so the evaluator cannot reward output deletion as fewer errors.
4. [assumed] **Degenerate long output:** one row can pair with only one mark, and its full length and
   difference print. It is never called pass or progress. [assumed] No automatic musical-length
   verdict exists without an operator law; that residual remains visible rather than hidden.
5. [assumed] **Refusal hiding:** every pinned panel row and refusal must exist in both manifests;
   new refusal makes the pair not comparable and also fires the regression floor.
6. [assumed] **A fake scalar:** impossible on the sanctioned evaluator because it emits no combined
   ordering. [confirmed] A person can still invent a number in free prose; that is outside the
   sender's structured output and remains a process violation.

---

## What v4 gives up, and what that leaves uncaught

1. [assumed] **It gives up one automatic progress number.** Subtle start/length tradeoffs no longer
   choose work mechanically. [unknown] A genuinely better approach can therefore wait for operator
   judgment or a future blind instead of being promoted automatically.
2. [assumed] **It gives up calling Lowkey held out.** Lowkey remains a precise regression example,
   but fitting to it is uncaught and its success says nothing about a new track.
3. [assumed] **It gives up “point it at anything” success.** Fail-closed proof and exact substrate
   identity create honest refusals. [unknown] The actual share of the library refused remains
   uncaught until real runs measure it.
4. [assumed] **It gives up claims of complete conversational capture.** The wrapper protects only
   messages it receives. Unwrapped words may remain missing until the operator recognizes a stale
   header on a later publish.
5. [assumed] **It gives up automatic judgment of musical duration.** A wildly long span is exposed
   in plain differences but is not mechanically wrong without a compiled law or the operator's ear.
6. [assumed] **It gives up small permanent storage.** Exact evidence and decision-bearing bundles
   remain, so their lifetime growth is uncaught by the scratch-data limit.

---

## THE KILL SHOT

[confirmed] The most likely death remains the redesign becoming the next object of over-building
while hearing stays at 2 of 34. v3's surface-first idea was meant to prevent that, but its first
step did not activate the sender and its “hearing never pauses” promise reserved no capacity.

[assumed] v4 makes the first adoption unit one complete governed laser slice and prevents adoption
from taking the last hearing slot. That makes the failure visible and bounded; it does not prove
the hearing work will find a successful approach. If the program spends six weeks perfecting
SQLite, leases, custody, and storage after the first slice while the ear result does not move, the
operator will correctly conclude that rigor again displaced the goal.

---

## Dossier §8 failure-mode table under v4

| # | Failure mode | Verdict | Scenario where it recurs anyway |
|---:|---|---|---|
| 1 | Confident output dies on his ear or eyes | `UNCHANGED` | [assumed] Structural lies refuse, but a checked, well-formed list can still be musically wrong until his ear hears it. |
| 2 | Rigor spent on the wrong object | `UNCHANGED` | [assumed] Surface-first order and a reserved hearing slot bound the redesign cost; no mechanism proves the next hearing experiment attacks the right idea. |
| 3 | Evidence unread or lost | `UNCHANGED` | [assumed] Wrapped input is accounted for, but an unwrapped session can lose words until a later publish, with no one-day bound. |
| 4 | Over-rotation on corrections | `VISIBLE WITHIN A DAY` | [assumed] On governed output, printer fields and append-only supersessions expose surface loss; a semantic cure that breaks an uncovered expectation still waits for his ear. |
| 5 | Settled laws re-broken | `VISIBLE WITHIN A DAY` | [assumed] On governed output, compiled buildup law refuses; non-compilable taste laws and hand-pasted output can still recur. |
| 6 | Communication violations | `UNCHANGED` | [assumed] Sender enforces body and headers, but irrelevant free prose, jargon, or failure to answer remains human/model behavior. |
| 7 | Delegated output consumed without verification | `VISIBLE WITHIN A DAY` | [assumed] Governed output cannot publish without a checker; hand-pasted or front-desk judgment can bypass independent verification. |
| 8 | Seat/process mismanagement | `VISIBLE WITHIN A DAY` | [assumed] Leases, ten-minute progress, resume, and local notice expose death; total provider loss still prevents chat. |
| 9 | Building on missing/unvalidated deliverables | `VISIBLE WITHIN A DAY` | [assumed] Lane input refusals and four-bucket census expose absence; an existing-but-wrong artifact survives until checker injection, a released mark, or his ear catches it. |

[confirmed] No whole dossier mode is `IMPOSSIBLE`. The three `UNCHANGED` verdicts are not claims
that v4 does nothing; they mean the failure can still persist for six weeks through an admitted
path, so the stronger label would be dishonest.

---

## Enforcement audit

[confirmed] **Today:** every new v4 mechanism is only a design contract. None of `listen`,
`develop`, the evaluator, intake database, sender, run lease, or custody store exists under the
named interface.

[assumed] **Enforced by code after the specified build:** command/refusal shapes; selected-lane
dependency checks; list/header fields; buildup proof; run-id/body hash sender; dispositions and
all-class evidence counts; fixed-panel comparability; one-to-one evaluation; manifests; atomic
publish; leases/resume; provider-family publish block; write fence; storage refusal.

[assumed] **Enforced by someone remembering even after the build:**

1. starting every operator-facing session through the wrapper;
2. an unwrapped seat admitting it cannot record evidence;
3. not hand-pasting an ungoverned sheet;
4. choosing a useful falsifier rather than a merely runnable weak one;
5. classifying `human_only` and `not_applicable` honestly;
6. choosing the next resource slot wisely;
7. keeping free prose brief, relevant, plain, and responsive;
8. initiating blind tests only with the operator's approval;
9. honoring the reserved hearing slot before the experiment/lease launcher exists;
10. not inventing a new score in prose outside the evaluator.

[unknown] **Enforced by nothing:**

1. that any current or future model truly hears the operator's sound class;
2. that Lowkey has not been fitted after its rows became public;
3. that a future codec or sound class is supported before it is tried;
4. that an unwrapped message is detected before a later governed publish;
5. that the operator recognizes the stale last-message header;
6. that a musically wrong but well-formed span is rejected without his ear or a compiled law;
7. that free prose answers the intended question;
8. that provider quota exists when a checker is needed;
9. that permanent exact evidence stays below any fixed storage size;
10. that the operator remains willing to tolerate honest refusals.

---

## Three six-week walkthroughs

### 1. The protected-key mirror

1. [confirmed] Lowkey rows already exist in builder-readable files.
2. [assumed] Under v3, a protected copy moves to a separate account and access tests pass.
3. [assumed] A builder reads the dossier copy, tunes Lowkey, and improves evaluator cells.
4. [assumed] Six weeks later a fresh track fails; “protected regression” had measured a mirror.
5. [assumed] Under v4, the same work is labelled exposed teacher-set movement from day one and
   cannot support a generalization claim. The failure can still happen, but its meaning is visible.

### 2. The single-lane door that refuses every lane

1. [confirmed] Track energy, drop energy, and accents are not all integrated today.
2. [assumed] Under v3, track energy inherits full-list `LANE_INCOMPLETE` and laser proof.
3. [assumed] The governed door refuses; workers inspect side-script output instead.
4. [assumed] Six weeks of development again occur outside run records and the sender.
5. [assumed] Under v4, only track-energy inputs may refuse that run, and missing other lanes are
   a test case. The side window is no longer required to see one lane.

### 3. The reassuring but false library headline

1. [confirmed] Current tracks can lack grids/frames that the proposed command says it will build,
   and codec failure can emerge during actual work.
2. [assumed] Under v3, the no-heavy-compute census labels missing material as unable to print and
   misses later failures.
3. [assumed] The operator plans around a confident `N of ~750` headline.
4. [assumed] Six weeks later many “refused” tracks were buildable and some “ready” tracks fail.
5. [assumed] Under v4, the chat line separates ready, build required, refused, and unknown; it
   cannot call substrate readiness an end-to-end refusal rate.

---

## Open questions and assumptions

1. [unknown] The real full-library end-to-end refusal rate remains unmeasured. A prerequisite
   census cannot answer it.
2. [unknown] Whether missing phrase/drop evidence is buildable for most tracks remains unknown.
3. [unknown] Whether the operator's actual chat surface can be placed behind a commit-before-model
   wrapper remains unproven. Without it, capture is only a visible-header limit.
4. [unknown] Whether two provider families can sustain builder/checker separation and shadow work
   under current quotas remains unmeasured.
5. [unknown] Which exact inputs the unfinished accent lane will require. v4 forbids borrowing
   unrelated gates and requires the lane contract before implementation.
6. [assumed] Ten minutes is the fixed maximum silent interval for a long local stage. It is a design
   choice based on the hours-long current evidence, not a measured operator preference.
7. [assumed] The existing three-attempt blind limit and fixed operator acceptance gate remain law.
8. [assumed] The current side processes remain authoritative until each v4 replacement passes its
   named failure tests and the operator approves the final switch.

---

## Verification run this round

1. [confirmed] `python3 tools/check_docs_metadata.py` passed.
2. [confirmed] `python3 tools/check_docs_drift.py` passed.
3. [confirmed] `python3 tools/check_ui_jargon.py` passed.
4. [confirmed] `python3 tools/check_agent_contracts.py` failed because the failure dossier and
   operating-model v1, v2, v3, and v4 are all unclassified active docs. The named cure is adding
   them to `docs/architecture/doc_index.md` or `docs/status/active_work_registry.md`, but this
   round's prompt permits writes only to v4 and this record, so I did not cross that boundary.
5. [confirmed] `python3 tools/check_docs_staleness.py --report` completed and reported twelve stale
   contracts from implementation changes since its baseline. It is advisory and was not caused or
   repaired by this docs-only round.
6. [confirmed] No software unit suite was run because this round changed no executable code or
   tests. No hardware validation was attempted.
