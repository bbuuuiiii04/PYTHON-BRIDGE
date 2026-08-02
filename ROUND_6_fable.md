CHANGES REQUIRED

# Round 6 (Fable seat) — attack on v6, ruling on Round 5, and v7

[confirmed] I attacked
`docs/plans/active/spectral_program_operating_model_v6_2026_08_02.md` as a stranger's design,
verified all three of Round 5's cure claims against the actual v5 and v6 texts, and found three
defects worth changing — none critical, none a direction defect. All three are the same failure
class this loop has been cutting since Round 3: a claimed mechanism whose enforcement point does
not reach the behavior it claims to govern. The next complete design is
`docs/plans/active/spectral_program_operating_model_v7_2026_08_02.md`.

[confirmed] This round changed only that v7 design and this record. I changed no code, config,
runtime, `local/` content, tmux seat, or hardware, and ran no git mutation command.

[confirmed] Evidence opened and re-verified myself this round, not inherited: v6 in full; v5 at
the exact lines Round 5 cited; `ROUND_5_sol.md`, `ROUND_4_fable.md`, `ROUND_3_sol.md`,
`ROUND_2_fable.md`, `REVISION_ROUND_1.md`, `COMBINED_DESTROY_review.md`, and the failure dossier
in full; `smart_phrasing.py:700-810` (fail-open `select_true_drops` at 782-797 and zero-runway
`runway_beats` at 714-739, verbatim as v6 states); `combined1_runner.py:1120-1176` (fail-closed
skip-with-reason, verbatim); `KNOWNSCORE_scorecard.md:9` (partial-key caveat);
`DEVGRADE1_scorecard.md:20-22` and `PROBE13_report.md:17-19` (phantom-or-plausible, never
phantom); `LOWKEY1_scorecard.md:1-20` (all seven key rows printed, so no custody story can be
true); `DEVSPLIT_2026_08_01.md:36-51` (Lowkey B0 program-exposed);
`PROGRAM_STATE_2026_07_31.md:46-63` (track energy, drop energy, accents all open rows);
`RBPALL5_report.md:100-112` (5.71 h and 5.49 h single-model phases). [confirmed] The
acceptance-format SHA-256 recomputes to
`80084cba17d49cb4fed4b8ecf0add0caa8f02bda5a60d57a43382238e97bb910`. [confirmed] Nothing named
`tools/spectral_listen` exists in the tree.

---

## Ruling on Round 5's cure claims — verified against both texts, not accepted

| Round 5 finding | Round 6 verdict |
|---|---|
| F1 — v5's sender required `PUBLISHED` while the degraded path required `WAITING_FOR_CHECKER` | [confirmed] **The finding was real and the cure HOLDS.** v5:163-167 really did demand a published run id for every governed body while v5:425-433 kept the unchecked sheet waiting — a contradiction one builder had to resolve by weakening something. v6:163-177 makes the sender state-aware per body type; v6:473-481 separates delivery from analysis state with the single named exception; v6:453-458 gives `CHECK_FAILED` an enforcing component (pending correction that blocks every newer governed body); v6:546-554 names the failure tests. The stray unchecked-evaluation sentence at v5:203-204 is gone — v6:216-217 forbids evaluation reports from the unchecked path. Internally consistent now; I checked §2, §8, §9, and §11 against each other. |
| F2 — v5's full-list template permitted `Track energy: <…or an explicit refusal>` | [confirmed] **The finding was real and the cure HOLDS.** v5:182-185 contains the refusal placeholders verbatim. v6:189-203 removes them; v6:205-207 says a lane refusal never appears inside the body and a refusal string cannot satisfy the completeness check; the §12 step-1 test list includes a lane refusal placed inside a full-list body. The all-or-nothing front-door promise and the template now agree. |
| F3 — v5 overclaimed that preregistration prevents easy-panel gaming | [confirmed] **The finding was real and the reclassification HOLDS.** v5:327 said "easy-track selection cannot become an improvement," which registration time cannot deliver. v6:344-350 keeps the mechanical membership freeze, admits prior exploratory knowledge shapes the initial panel, prints the chooser, bans generated positive verdicts, and calls the rest an accepted limit — consistently repeated at v6:505-509, 630-634, and in the operator version at 650-652. |

[confirmed] Round 5 did not undo any earlier cure; I spot-checked that v6 still carries the
Round 2-4 mechanisms in the places Round 5's audit tables claim (development-door lane matrix,
evidence-scope lines, all-class evidence counts, ten-minute line, one-switch step 1, fail-closed
laser proof). Its convergence read was honest.

---

## Findings, worst first

### H1. MEDIUM-HIGH — the reserved hearing slot claims a launcher mechanism that cannot see the spend that actually starves hearing

[confirmed] **Location:** v6:583-587 — "after §5 it is stored and the launcher refuses an
adoption lease that would consume the reserved slot."

[confirmed] **What is wrong:** three gaps sit between that sentence and reality. First, the
launcher can refuse only work that asks it for a lease, and §9 defines leases for analysis runs;
nothing anywhere in v6 forces adoption **build** work — the seats designing, coding, reviewing,
and checking this machinery — to request a lease before spending. Second, the recorded program's
hearing starvation was exactly that kind of spend: `PROGRAM_STATE_2026_07_31.md` records all
GPT reviewer seats quota-dead until August 5 and the dossier's §1-§2 record 912 markdown files
and seat-days of machinery work while hearing sat at 2 of 34 — none of it would ever have passed
through a run-lease launcher. Third, "if only one usable builder/provider slot remains" is not
machine-measurable: provider allowance is external and shared across all seats; local code
discovers a quota wall by hitting it, and cannot partition what it cannot see. A fourth, smaller
gap: the adoption-versus-hearing label on a lease is declared by whoever requests it.

[confirmed] **Why it matters:** this is the kill-shot surface. Every round since 2 has said the
most likely death is the redesign over-building while hearing stays flat, and Round 5 explicitly
flagged that the reservation "is still something a person must remember, not a mechanism." v6's
answer was to promise a mechanism whose enforcement point does not reach the behavior — the
identical overclaim shape Round 5 itself cut out of preregistration. An operator told "after the
database exists, the machine protects hearing capacity" would be told something false.

[assumed] **Concrete six-week failure:** the database and launcher land at step 5-6. For the next
month, adoption builder and checker seats burn the provider allowance on wrapper tests and
recovery drills, in ordinary sessions. No adoption lease is ever refused because hearing runs are
rarely queued — there is no hearing capacity left to queue them with. The slot ledger shows the
reserved slot honored; the operator peeks, sees seats drilling SQLite recovery, and says exactly
what he said on 08-01. The mechanism reported green through the whole starvation.

**Direct answer to the standing question — can this be mechanised, or is it a true limit?**
[confirmed] It is mostly a true limit, and the honest design says so. The mechanisable fraction
is small and real: a stored priority rule over the launcher's own queue — never grant an
adoption-purpose lease while a hearing-purpose request waits — is buildable and deterministic,
and v7 keeps exactly that. Everything else is structurally out of reach from inside this design:
seat dispatch has no software chokepoint (seats are started by people over tmux), provider
allowance is invisible and unpartitionable from local code, and the purpose label on any lease is
self-declared. This is the same limit class as hand-pasting past the sender: code can only govern
work that enters it. The one honest strengthening available — dispatch tooling consulting the
stored rule if dispatch is ever routed through tooling — is named in v7 as a possibility, not
claimed. Any future round that "solves" this with more machinery should be treated as the
kill shot arriving, not as a cure.

### H2. MEDIUM — "checker unavailable" is a claim, not a recorded fact, so the degraded path can silently become the routine path

[confirmed] **Location:** v6:444-451 (the unchecked send requires only the state, the stored wait
start, and the line) and v6:466-471 (no path forces a waiting run to ever be checked).

[confirmed] **What is wrong:** nothing in v6 requires that a checker was ever actually sought. A
run enters `WAITING_FOR_CHECKER` the moment it finishes; one minute later the sender will accept
an unchecked sheet whose line truthfully says "unavailable since one minute ago." Nothing
distinguishes a real quota wall from a builder who simply never dispatches a checker, and nothing
schedules the deferred check, so the `CHECK_FAILED` correction backstop — the safety story the
whole path rests on — may never engage. The degraded path was added (Round 4 G3) for genuine
outages; as written, it is equally available as a permanent way to route around independent
checking, with only the `UNCHECKED` label as friction.

[confirmed] **Why it matters:** dossier §8.7 — delegated output consumed without verification —
is a top-ranked repeating mode, and the checker is the design's only independent eyes on a
changed data path. A labelled hole that is always open is better than an unlabelled one, but the
design can close most of it mechanically and currently does not.

[assumed] **Concrete six-week failure:** a builder under time pressure stops dispatching checkers
in week two. Every sheet ships with an `UNCHECKED` line; the operator habituates to the label the
way he habituated to green gates in July. In week five a corrupted cache — exactly what checker
injection tests catch — produces a plausible sheet with rows from the wrong audio. No check was
ever coming, so no correction ever fires. His ear is again the first and only detector.

### H3. LOW-MEDIUM — baseline choice is an unnamed judgment with a real gaming path through the regression floor

[confirmed] **Location:** v6:335-350 and 368-373. The panel chooser prints; the baseline chooser
does not. v6:627-629 lists panel membership and slot choice as remaining judgments; baseline
choice is absent.

[confirmed] **What is wrong:** the automatic regression floor fires when a baseline `paired` row
degrades or a baseline-ready track refuses. Pick an old, weak baseline with few paired rows and
few ready tracks, and the floor protects almost nothing in that comparison — the only automatic
rejection trigger tied to evaluation is quietly disarmed while the report stays formally legal.
Panel preregistration does not help; it freezes membership, not the baseline.

[assumed] **Concrete six-week failure:** a favored approach is always compared against the oldest
baseline on record. Nothing regresses because almost nothing was paired in that baseline. Work
that should have tripped the floor survives its budget, and the record never shows who kept
choosing that baseline.

---

## Outcomes in v7

| # | Outcome | Mechanism in v7 |
|---:|---|---|
| H1 | **ACCEPTED LIMIT, correctly restated** — the overclaim is removed and the real mechanical fraction kept | [assumed] v7:598-610 rewrites the reservation: the launcher's queue-priority rule (no adoption-purpose lease while a hearing-purpose request waits) is the entire machine-enforced part; seat spend, label honesty, and provider allowance are named as out of reach before **and** after the build; dispatch-tooling consultation is named as possible, not claimed. v7:650-653 carries it in §13; v7:688-692 says it plainly in the operator version. |
| H2 | **CURED as a build contract** | [assumed] v7:449-458 — the sender accepts an unchecked send only when the run record contains a checker-acquisition attempt, made at or after entering `WAITING_FOR_CHECKER`, whose recorded outcome is failure; each unchecked send needs its own fresh recorded failed attempt, so "unavailable" is a stored fact. v7:460-463 — when a checker returns, delivered-unchecked runs are checked oldest first, before that checker takes new work from the same builder, so the deferred check cannot be indefinitely displaced by new work. v7:171 mirrors the requirement in the sender's §2 state rules; v7:565-567 adds the missing-acquisition-attempt failure test to step 1; v7:639-645 states the residue: nothing can force a check while no checker exists anywhere. |
| H3 | **ACCEPTED LIMIT, made visible** | [assumed] v7:352-355 — the report prints baseline and candidate run identities and `BASELINE CHOSEN BY <identity>`, and states that a weak baseline disarms the floor for that comparison; v7:520-523 names baseline choice beside panel choice in §10; v7:655-657 adds it to §13's judgment list; v7:683-685 tells the operator both choosers by name. Visibility, not wisdom — same class as the panel limit. |

---

## Is the loop converged, still reducing severity, or churning? (direct verdict)

[confirmed] **Still converging, close to the design floor — not churn, and not yet an earned
AGREED.** The evidence:

1. **Severity keeps falling in kind.** Rounds 1-3 killed direction defects and false claims
   (invalid referee, fake custody). Round 4 found enforcement holes on the claim surface. Round 5
   found internal contradictions. This round found zero contradictions and zero direction
   defects — all three findings are overclaim/enforcement edges, and the worst one (H1) is a
   sentence promising more than its mechanism delivers, not a broken mechanism.
2. **No oscillation.** Nothing in v7 reverses any prior cure; I verified Round 5's three cures
   hold and v7 only narrows claims and adds tests. Across six rounds the only reversal remains
   Round 3's evidence-forced Lowkey correction.
3. **The stable core has now survived six independent attacks unchanged:** no scalar score,
   unjudged-not-wrong, fail-closed laser proof, refusal over partial output, state-aware
   hash-bound sender, one-switch adoption step 1, and the plain statement that hearing is
   unsolved.

[assumed] The marginal value of further design rounds is now small. My three findings are
third-order instances of one rule the design already knows — claim only what the enforcement
point reaches — and the biggest remaining risks all sit in the [unknown] column no design round
can move: refusal rate, quota reality, wrapper feasibility, and whether any model hears his sound
classes. One more verification round on v7's three narrow changes could legitimately earn an
AGREED. After that, another design round would itself be the kill shot in miniature: rigor spent
polishing the honesty machine while 2 of 34 stands. The next real severity reduction can only
come from the step-1 governed slice and the census producing measurements — after the operator
chooses to adopt, which nothing in this loop authorizes.

---

## THE KILL SHOT

[confirmed] Unchanged in substance since Round 2, because no design can remove it: the redesign
becomes the next polished object while the machine's hearing stays at the dossier's 2 of 34. Six
rounds have now spent roughly as much adversarial rigor on the operating model as the old program
spent on any package it shipped — that observation is the kill shot's shape appearing in this
very loop. What is different from the July failures: the design now fails visibly and cheaply
(refusals, labels, one governed slice first) instead of invisibly and expensively, and after H1
it no longer tells the operator that a machine guards hearing capacity when only people can. The
honest residual: if six weeks of building produce a working sender, a census, and no better cold
hearing, the operator hears "I told you so" in his own voice — and the only thing this design
will have bought him is knowing it sooner.

---

## Dossier §8 failure-mode table under v7

| # | Failure mode | Verdict | Scenario where it recurs anyway |
|---:|---|---|---|
| 1 | Confident output dies on his ear or eyes | `UNCHANGED` | [assumed] A verified, well-formed, honestly-labelled list can still be musically wrong; only his ear rules. An unchecked sheet widens this by the checker's margin — now only behind a recorded failed acquisition attempt. |
| 2 | Rigor spent on the wrong object | `UNCHANGED` | [assumed] Slice-first order, budgets, and the queue-priority rule bound cost; no mechanism chooses the right hearing idea, and seat spend on machinery is invisible to every mechanism (H1, stated honestly now). |
| 3 | Evidence unread or lost | `UNCHANGED` | [assumed] Wrapped input is reconciled; an unwrapped session still loses words until a later publish, or longer; wrapper feasibility itself is [unknown]. |
| 4 | Over-rotation on corrections | `VISIBLE WITHIN A DAY` on governed output | [assumed] Required fields and append-only supersessions expose surface loss; semantic over-rotation outside a covered mark waits for his ear. |
| 5 | Settled laws re-broken | `VISIBLE WITHIN A DAY` on governed output | [assumed] The compiled buildup law refuses; taste laws and hand-paste can still recur. |
| 6 | Communication violations | `UNCHANGED` | [assumed] Bodies are shape-enforced; free prose around them can still be irrelevant or fail to answer the question asked. |
| 7 | Delegated output consumed without verification | `VISIBLE WITHIN A DAY` | [assumed] Verified bodies require an independent checker; the unchecked path now needs a recorded failed acquisition and is checked oldest-first when a checker returns. Hand-paste remains outside everything. |
| 8 | Seat/process mismanagement | `VISIBLE WITHIN A DAY` | [assumed] Ten-minute lines, leases, resume, local notices; total provider/chat loss still silences the surface. |
| 9 | Building on missing or unvalidated deliverables | `VISIBLE WITHIN A DAY` | [assumed] Named lane refusals and the four-bucket census expose absence; an existing-but-wrong artifact survives until injection, a mark, or his ear. |

[confirmed] No whole mode is `IMPOSSIBLE`, same as every prior round; the three `UNCHANGED` modes
persist through admitted paths.

---

## Enforcement audit

[confirmed] **Today:** every v7 mechanism is a design contract. Nothing named
`tools.spectral_listen`, its sender, intake wrapper, experiment registry, lease launcher, or
blind custody store exists in the current tree.

[assumed] **Enforced by code after the specified build:** the three governed body types with
state-aware, hash-bound delivery; mandatory first lines and evidence-scope lines matched against
manifests; all-or-nothing full-list completeness with no refusal strings inside the body;
selected-lane prerequisites; fail-closed laser proof; message dispositions and all-class evidence
counts; one-to-one matching with deterministic ties; no generated positive verdict; preregistered
panel membership; the regression floor; the recorded-failed-acquisition gate on unchecked sends
and oldest-first deferred checking; the `CHECK_FAILED` correction block; manifests and
reproduction refusal; atomic run state, leases, resume; storage refusals; write fences; the
lease-queue hearing-priority rule; blind-key negative tests and the attempt counter.

[assumed] **Enforced by someone remembering even after the build:** starting operator-facing
sessions through the wrapper; an unwrapped seat admitting it cannot record; not hand-pasting
governed-looking text; dispatching seats so machinery work does not starve hearing work (H1 —
the largest one, now stated as such); labelling a lease's purpose honestly; choosing useful
falsifiers, representative panels, and fair baselines; classifying `human_only`/`not_applicable`
honestly; keeping free prose plain and responsive; initiating blind tests only on the operator's
word.

[unknown] **Enforced by nothing:** that any model hears his sound classes; that Lowkey has not
already been fitted; that a chosen panel or baseline represents anything; that a future codec or
class works before it is tried; that an unwrapped message is detected before a later publish;
that he recognizes a stale last-message line; that a well-formed but musically wrong span is
rejected without his ear or a compiled law; that provider allowance exists when a checker or a
hearing seat needs it; that permanent evidence stays under any fixed size; that he stays willing
to tolerate honest refusals; that his real chat surface can sit behind commit-before-model
capture.

---

## Three six-week walkthroughs I ran against v7

1. **Machinery starves hearing while the ledger shows green (H1).** Under v6, the launcher rule
   reports the reserved slot honored while builder seats burn the allowance in sessions it never
   sees. Under v7 the same starvation is still possible — but no mechanism claims otherwise, the
   operator version tells him the protection is a human duty, and the record cannot later say
   "the machine was guarding it." The failure loses its false green light, which is all a design
   can take from it.
2. **The permanent unchecked lane (H2).** Under v6, a builder can ship `UNCHECKED` sheets forever
   without a checker ever being sought. Under v7 each unchecked send needs a fresh recorded failed
   acquisition attempt, and the first returning checker must work the backlog oldest-first before
   taking that builder's new work. A real quota wall behaves the same as before; a lazy or evasive
   builder now has to manufacture recorded failures, which the run record exposes to any later
   audit.
3. **The disarmed regression floor (H3).** A worker keeps comparing against a weak baseline. v7
   cannot make the choice wise, but every report now names the baseline and its chooser next to
   the panel chooser, so the pattern — same weak baseline, same chooser, week after week — is
   visible in the record the front desk and operator read, instead of living only in run ids.

---

## Open questions and assumptions

1. [unknown] The full-library end-to-end refusal rate; the census cannot answer it.
2. [unknown] Whether missing phrase/drop evidence is buildable for most tracks.
3. [unknown] Whether the operator's actual chat surface can sit behind commit-before-model intake.
4. [unknown] Whether two provider families can sustain builder/checker separation under real
   quota; the H2 gate records the answer per attempt instead of assuming it.
5. [unknown] The accent lane's exact inputs.
6. [unknown] End-to-end time and storage for cached, unseen, refused, and 30-50-track runs.
7. [assumed] Ten minutes remains the maximum silent interval — a design choice grounded in the
   measured 5.5-5.7 h phases, not an operator-measured preference.
8. [assumed] The three-attempt blind limit, the acceptance gate, and every dossier operator law
   remain fixed; nothing this round touched them.
9. [assumed] Existing safeguards stay authoritative until each replacement passes and the
   operator approves a switch.
10. [assumed] The hearing-capacity duty (H1) stays with whoever dispatches seats; v7 records it
    as a duty, and no future round should re-promise a mechanism there without a real new
    enforcement point.

---

## Verification run this round

1. [confirmed] `python3 tools/check_docs_metadata.py` passed.
2. [confirmed] `python3 tools/check_docs_drift.py` passed.
3. [confirmed] `python3 tools/check_ui_jargon.py` passed for 13 files.
4. [confirmed] `python3 tools/check_agent_contracts.py` reports the same class of boundary
   condition every round has reported — this run flags exactly two unclassified active docs: v6
   and the new v7. The cure is a doc-index or registry entry, which the convergence prompt's
   two-file write boundary forbids this round, exactly as it forbade it in Rounds 3-5.
5. [confirmed] `python3 tools/check_docs_staleness.py --report` completed with the same advisory
   staleness on 12 contracts outside this round's scope; this round changed no implementation
   file.
6. [confirmed] No unit suite was run because no executable code or tests changed. No runtime,
   bridge process, SoundSwitch, laser, LED/Govee, Rekordbox, or hardware validation was
   attempted, and nothing here upgrades the repo's SOFTWARE-VALIDATED ONLY /
   HARDWARE-UNVALIDATED status.
