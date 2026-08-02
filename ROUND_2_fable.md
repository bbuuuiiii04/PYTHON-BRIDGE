# Round 2 (Fable seat) — attack on v2, ruling on round 1, and v3

**Status:** round record for
`docs/plans/active/spectral_program_operating_model_v2_2026_08_02.md`. I attacked v2, verified
round 1's cure claims against the actual files instead of accepting them, and found real holes.
The next version is `docs/plans/active/spectral_program_operating_model_v3_2026_08_02.md`.
Everything here is design work; nothing was implemented, run live, or changed outside the two
files this round is allowed to write.

**Evidence base actually opened this round:** [confirmed] `smart_phrasing.py:700-810` (the
fail-open `select_true_drops` and `runway_beats` are exactly as v2 describes),
`local/spectral_v5_2026_07_17/combined1_runner.py:1120-1180` (fail-closed skip-with-reason),
`KNOWNSCORE_scorecard.md:1-30` (line 9 partial-key caveat verbatim), `DEVGRADE1_scorecard.md:15-25`
("phantom-or-plausible, never phantom"), `PROBE13_report.md:15-21` (same),
`DEVSPLIT_2026_08_01.md:1-60` (held-out thinness, Lowkey program-exposed, fresh-blind class),
`PROGRAM_STATE_2026_07_31.md:40-70` (track/drop energy open rows, accents designed-not-built), the
SHA-256 of `acceptance_list_format_v3.md` (matches v2's pinned hash exactly), and a tree search
proving nothing named `spectral_listen`, `listen`, or `score` exists outside design documents.
Every file:line v2 leans on is real and says what v2 says it says. The holes are in what v2 built
on top, not in its citations.

---

## Findings, worst first

### F1. CRITICAL — v2's guarantees govern a door nobody can use for months, so the real work runs ungoverned beside it

[confirmed] **Location:** v2 §2 (`LANE_INCOMPLETE`), §6 (`evaluate --run <run-id>`), §12 step 2
("Until accented moments and the open energy rows are real, `listen` must return `LANE_INCOMPLETE`
and no list").

**What is wrong:** Two of the four lanes are unbuilt and one is unintegrated
([confirmed] `PROGRAM_STATE_2026_07_31.md:48-61`). Under v2's own rule, `listen` therefore refuses
every track on the honest path until the last lane lands. `evaluate` scores runs, and a refusal
run has no rows to score. v2 defines no other sanctioned way to produce or evaluate lane output.
So for the entire build period — months, on current evidence — every laser sheet the operator
actually reads has to come from side scripts, exactly like today's `combined1_runner.py`. None of
v2's machinery touches those: no pinned printer, no fail-closed buildup proof, no run record, no
checker, no evidence reconciliation. v2 built a clean refusing door on a house whose residents
use the window.

**Why it matters to the operator's goal:** The dossier's worst repeating failure is confident
output dying on his ear (§8.1), and the 2026-08-02 buildup-laser violation shipped on exactly such
an interim sheet. v2's cures for that failure only fire on the governed path. If the governed path
produces nothing he wants during the whole build, the cures protect nobody during the very months
the program is most active.

**Concrete failure scenario:** Week 3 of adoption. The intake database works, `listen` correctly
says `LANE_INCOMPLETE` on everything. The operator asks "where does the machine think the growls
are in track X." The only way to answer is a side script. The side sheet has no buildup proof; it
prints a row at 2:24 in a buildup; he catches it by ear; dossier §4 has recurred while every v2
mechanism reports green, because none of them were in the loop.

### F2. HIGH — the intake wrapper's dominant bypass is an unwrapped session on the same surface, and round 1's "CURED" on finding 6 overstates the cure

[confirmed] **Location:** v2 §5, especially the boundary paragraph ("Messages in a different app,
an old unavailable transcript, or spoken aloud remain outside its reach") and
`REVISION_ROUND_1.md` row 6 ("CURED").

**What is wrong:** The SQLite machinery genuinely makes loss *inside* the wrapper visible
(transactions, dispositions, `EVIDENCE_NOT_RECONCILED`, backups). But the historically dominant
loss path was never a different app — it was ordinary sessions on the same chat surface that
simply weren't recording ([confirmed] dossier §5: his Gemini descriptions unread, three
measurements existing only in chat; dossier §8.5: fresh sessions re-breaking settled laws). v2's
rule "the only allowed operator-facing session is behind an intake wrapper" is enforced by nothing:
a fresh seat spun up in chat — the norm today — has no wrapper, captures nothing, and nothing
detects it. The boundary paragraph doesn't even name this path. Round 1 marked the finding CURED;
the cure covers the wrapped path only, and the unwrapped-same-surface path is both uncovered and
the most likely one.

**Why it matters:** "don't lose information. i don't want to have to repeat myself for ANYTHING"
is a standing order (dossier §5). A capture system whose completeness depends on every future
session remembering to be the wrapped kind will silently lose exactly the way the program already
lost.

**Concrete failure scenario:** A provider hiccup kills the front desk; whoever restarts it opens a
plain session. The operator gives two corrections that afternoon. The plain session nods, applies
one in-conversation, and records neither. Weeks later a governed publish is consistent with its
database — which is missing both corrections — and he repeats himself, again.

### F3. HIGH — Lowkey's key has no custody class: "released" and "never teacher material" with no mechanism between builders and the only complete key

[confirmed] **Location:** v2 §1 ("It remains held-out and must never become worker training
material; 'released' means it can catch a regression, not teach a fix") against §7 ("Released
development marks are teacher material. A worker may use them, and every use is recorded") and §7's
blind-key custody, which covers *blind* keys only.

**What is wrong:** v2 resolved the original finding-3 contradiction for blind keys (separate store,
negative read test — real cure). But Lowkey stopped being a blind key and became "released
regression evidence," which places it database-side where released material is readable. The only
thing standing between a builder and the row-level content of the program's single complete key is
the remembered sentence "must never become worker training material." No access mechanism
distinguishes the evaluator reading Lowkey (necessary) from a builder reading Lowkey (fatal). The
checker's source scan catches literal hardcoded timestamps; it cannot catch a builder hand-tuning
thresholds until Lowkey passes, and after that the program owns zero complete keys that can still
catch a regression.

**Why it matters:** Lowkey is the only track where "unmatched = wrong" is ever valid
([confirmed] `KNOWNSCORE_scorecard.md:9`). Burn it and the extra/phantom concept has no ground
truth anywhere until the operator hand-builds another complete key — which the standing
no-labeling-sessions rule makes unlikely.

**Concrete failure scenario:** Review walkthrough 2, moved one level up: the analyzer never sees
the key (filename invariance holds, isolation checks pass), but the builder reads the seven
timestamps from the evidence store and nudges band thresholds until all seven pair. Every
mechanical check in v2 passes. The regression instrument is now a mirror.

### F4. MEDIUM-HIGH — "breaks an existing released example" is undefined, reopening the judgment the killed number used to hide

[confirmed] **Location:** v2 §10 ("An approach is rejected only when… it breaks an existing
released example…") against §6, which deliberately prints cells "without deciding which trade is
better" and bans invented tolerances.

**What is wrong:** The evaluator's whole design refuses to say "worse." The rejection rule then
uses "breaks" with no definition in the evaluator's vocabulary. Paired-but-start-drifted-0.3s: a
break? Overlap shrank from 90% to 60%: a break? Whoever answers is doing exactly the hidden
judgment call that the removed one-number referee was killed for — now at the point where
approaches live or die, with no stated rule, so two seats will answer differently.

**Why it matters:** Dossier §2 is the operator discovering the program had quietly invented its
own definition of success. An undefined "breaks" is a slot for the next invented definition.

**Concrete failure scenario:** A worker's favored approach drifts three released marks by half a
second each. The worker rules "still paired, nothing broke." A later seat rules the same evidence
a triple regression. Both are defensible under v2; the experiment record now depends on who was
on shift.

### F5. MEDIUM — evidence-use receipts have escape valves that recreate "it used six of them" invisibly at his surface

[confirmed] **Location:** v2 §5/§6: `human_only` and `not_applicable` are legal dispositions for
any judgment; the checker's receipt test covers only `analysis_input` rows; the operator reads
chat, not receipts (dossier §8.6, "i refuse to open a document and look").

**What is wrong:** A seat can classify 48 of 54 judgments `human_only` with a written reason and
publish cleanly. The receipt makes the neglect *recorded*; nothing makes it *seen*. That is the
dossier §5 failure ("You gave this program a corpus of 54 judgements. It used six of them") with
better paperwork.

**Why it matters / scenario:** Six weeks in, his descriptions are again decorating a database
instead of steering analysis, and the only place that fact lives is a table he will never open.

### F6. MEDIUM — the fail-closed buildup proof may honestly refuse a large share of the library, and v2 never measures the rate before adopting

[confirmed] **Location:** v2 §4 step 2 (requires non-empty phrase segments) and §12 step 8
(measures one refused track and one 30–50 batch — not the library).
[confirmed] The runtime fail-open in `smart_phrasing.py:782-797` exists precisely because sparse
or absent phrase data is common enough that failing closed would strip tracks of their drop
identity.

**What is wrong:** Fail-closed is the right call for lasers — but nobody knows whether it refuses
5% of ~750 tracks or 50%. v2 adopts before anyone finds out.

**Why it matters / scenario:** The design ships, honest to a fault, and the operator's first week
of `listen` calls returns `DROP_PROOF_MISSING` on half the tracks he cares about. "why doesn't
this work on ANY of my tracks" — dossier §9's generality demand, failed by silence about a
measurable number.

### F7. MEDIUM — the long path has no in-progress behavior, so "hello??? nothings happening" recurs at the one command he types

[confirmed] **Location:** v2 §2 ("this same command builds the missing grid, frames, and lane
data… No time promise is made until measured"). [confirmed] Prior full-library analysis runs took
~5.5-5.7 hours per model (`archive_probe_ladder/RBPALL5_report.md:102-110`); the dossier records
him watching a live run in silence ("hello???", "nothings happening", §4).

**What is wrong:** Refusing to promise minutes is honest; saying nothing about what the operator
sees *during* a possibly hours-long build is a designed silence at his only surface.

### F8. LOW — evaluation output shape in chat is unspecified

[confirmed] **Location:** v2 §6 prints cells; nothing pins how they render in chat. Dossier §8.6
records raw glyph timelines and jargon walls as a named failure mode. A table of
`paired/overlap/tenths` cells pasted raw is that failure.

---

## Outcomes

| # | Finding | Outcome | Where the cure lives in v3 |
|---:|---|---|---|
| F1 | Guarantees govern a door nobody can use; real work runs ungoverned | **CURED** (build contract) | §2 "The development door": `develop --lane <name> --track <t>` runs through the same resolver, proof, printer, run record, evaluator, checker; mandatory `Development output — <lane> only` header; the sender refuses any output without a published run id whose stored hash matches the body (§§2, 11); adoption re-cut so this lands at step 3 (§12) |
| F2 | Unwrapped same-surface session bypasses capture | **ACCEPTED LIMIT** (downgraded from round 1's CURED) | §5: every publish carries "Last thing I have recorded from you: <time> — '<first words>'" so he can see the gap against his own memory; the bypass path is named plainly in §5 and §13 instead of hidden behind "different app" |
| F3 | Lowkey has no custody class | **CURED** (build contract) | §§1, 7: complete-scope keys live in the same custody store as blind keys — separate account/machine, negative read test, no "recorded read" path for builders; development side receives evaluator cells only; separation unavailable ⇒ `KEY EXPOSED`, no regression claim |
| F4 | "Breaks a released example" undefined | **CURED** (definition) | §6: automatic regression = same inputs, `paired` → `not overlapped`/`not evaluated`, or `READY` → refused; everything else prints as a difference for judgment, never an automatic verdict; §10 cites this definition |
| F5 | Receipt escape valves invisible in chat | **CURED** (visibility, not prevention) | §5: publish header states "Your recorded judgments: N total — X compared, Y enforced as checks, Z analysis input, W human-only" — mass-`human_only` shows up in chat on every publish; §6 repeats it |
| F6 | Library refusal rate unmeasured | **CURED** (measurement, not a promise) | §12 step 4: substrate-only refusal census across the full library, result reported in chat as a fact for him, before adoption; §13 carries the honest unknown |
| F7 | Long-path silence | **CURED** (contract) | §2: first reply before long work starts states what is being built; one short line per completed stage (the same stages the run record stores); silence longer than a stage is a defect |
| F8 | Chat rendering of evaluations | **CURED** (contract) | §6: one line per released example, his mark first, plain words, no symbol grids; batch evaluations lead with the sentence that answers the question |

---

## Ruling on round 1's fourteen claims — verified, not accepted

I checked each mechanism against v2's actual text and the cited files. "Stands" means the cure is
a coherent build contract that would prevent or self-announce the named failure if built as
specified — [assumed] until built, like everything in this design.

| # | Round 1 said | My verdict |
|---:|---|---|
| 1 | CURED — unjudged, not wrong | **Stands.** [confirmed] v2 §§1, 6 match the KNOWNSCORE/DEVGRADE1/PROBE13 caveats, which I re-read at their lines. Unmatched-on-partial-key never counts either way. |
| 2 | CURED — one number removed, pinned matcher | **Stands, with a leak fixed in v3.** The matcher, tie rules, and no-trade-deciding are real and complete in §6. But the removed judgment resurfaced undefined inside §10's "breaks a released example" (my F4). The replacement still answers the dossier: his own ask is "compare my description and timestamp windows and see if the models get it right" (§9), which is exactly the per-mark cell output — the removal did not leave the failure dossier unanswered, it left one edge undefined. |
| 3 | CURED — separate stores, negative read test | **Overstated.** Blind-key custody is genuinely cured. The Lowkey half of the original leak is not: released-but-never-teacher had no mechanism (my F3). v3 puts complete keys behind the same custody. |
| 4 | CURED — refusal, never fail-open | **Stands.** [confirmed] I read `select_true_drops` and `runway_beats` in current code; the fail-open is exactly as described, v2's seven-step proof never consults it, and the required test targets the fail-open case by name. |
| 5 | CURED — `listen` labelled nonexistent + exact contract | **Stands as a contract, but see F1/F7.** The refusal table is complete and two-shaped; [confirmed] nothing named `listen` exists in the tree. The contract was honest about the door and silent about the months before the door opens and the hours inside a build. |
| 6 | CURED — intake wrapper + SQLite battery | **Overstated → accepted limit** (my F2). The battery is sound for what passes through it; the claim "makes omission visible" is false for the dominant omission path. |
| 7 | CURED — no answer store/track name to analyzer, filename invariance | **Stands** for the analyzer. The builder-side gap is my F3, cured separately. |
| 8 | CURED — whole-path checker + failure injection | **Stands.** §8's three-part check names the full path including track resolution and cache choice, which answers the review's resolver scenario. |
| 9 | CURED — old safeguards stay until replacements pass | **Stands, at a price v2 didn't name.** Keeping both worlds alive while building the entire battery is a load the program must carry with quota-limited seats; v2's adoption order made that price maximal by front-loading plumbing. v3 re-cuts the order (§12) — the safeguard-retirement rule itself is right. |
| 10 | CURED — leases, single writer, resume, provider families | **Stands as a contract.** The pieces (lease with expiry + stored last stage, all-or-nothing rename, no-model-call watcher, `WAITING_FOR_CHECKER` as a state) are specified tightly enough for two builders to converge. |
| 11 | CURED — manifest hashes every input | **Stands.** The manifest list in §8 covers the review's named gaps (evidence revision, audio identity, model, cache, config, denominator, checker identity), and `reproduce` refuses on any missing byte. |
| 12 | CURED — automatic metric killing removed | **Stands, with one screw tightened.** The parent's question was whether the replacement still answers the dossier. It does: the invented-metric failure (§2 of the dossier) was a *machine-made* verdict steering builds; v2 replaces verdicts with four falsifiable rejection triggers plus budget *pauses*, and names slot allocation as recorded judgment instead of disguising it as arithmetic — which is the honest shape, since any automatic "flat = dead" rule on 34 partial marks recreates the invented metric. Two residues: an unrunnable falsifier could make the falsifier trigger vacuous (v3 §10 requires the falsifier be a test the checker can execute), and one trigger was undefined (F4, cured). What nothing automatic now kills, budgets starve — bounded cost, recorded choice. |
| 13 | ACCEPTED LIMIT — communication remains partly discipline | **Stands.** Correctly labelled; v3 narrows it further (run-id-bound sender) without claiming prose understanding is provable. |
| 14 | ACCEPTED LIMIT — measured costs, permanent evidence grows | **Stands.** [confirmed] `STORAGE_LIMIT_UNSET`/`STORAGE_LIMIT_REACHED` and the no-projection rule are in v2 §§11-13; the permanent-growth admission is honest. |

**Net on round 1:** twelve of fourteen hold up under verification; two (3 and 6) claimed CURED
where the mechanism covers only part of the failure. Both are re-classed and cured or limited
properly in v3. Round 1 removed the auto-kill rule and the single number for the right reasons,
and in both cases what replaced them still answers the dossier — the replacements' edges, not
their direction, needed repair.

---

## THE KILL SHOT

The most likely death is not a leak or a lie — it is that this design spends its first six weeks
building the honesty machine while the hearing stays at 2 of 34. Under v2's own adoption order,
the operator's first month of "progress" is an intake database, a lease table, and a command that
correctly refuses everything — while the sheets he actually looks at keep coming from ungoverned
side scripts (F1), one of which prints one more buildup laser. He peeks, sees seats drilling
process-death recovery instead of hearing growls, and says what he already said on 08-01: "WHY THE
FUCK DO U KEEP OVER ENGINEERING BULLSHIT AND DANCING AROUND THE FUCKING GOAL." The program dies of
dossier §8.2 — rigor spent on the wrong object — recurring at the level of the redesign itself.
v3's §12 re-cut (his-surface-first: buildup proof and printer on the existing runner in week one,
evaluator next, plumbing behind) is aimed square at this, and hearing work is ordered never to
pause. The residual risk: even re-cut, this is a real build program competing for quota with the
hearing work it protects. If both cannot be afforded at once, the honest move recorded here is:
the hearing work wins the slot, and ungoverned output is labelled ungoverned rather than pretended
governed.

---

## Dossier §8 failure-mode table (under v3)

| # | Failure mode | Verdict | Where it recurs anyway |
|---:|---|---|---|
| 1 | Confident output dies on his ear/eyes | `VISIBLE WITHIN A DAY` on the governed path (fail-closed proof, whole-list refusal, labelled unjudged rows) | Hand-pasted ungoverned text (§13); and hearing itself is unsolved — a governed, honest, checked list can still just be wrong, which only his ear catches |
| 2 | Rigor spent on the wrong object | `UNCHANGED` in kind, bounded in cost | Budgets and recorded slot choices bound spend, and the §12 re-cut points the first rigor at his surface — but no mechanism can prove the next experiment is the right object; that stays judgment |
| 3 | His evidence unread or lost | `VISIBLE WITHIN A DAY` for the wrapped path and for use-classification (capture-gap line + judgment-use counts in every publish header) | The unwrapped session (F2, accepted limit): a judgment given to a seat with no wrapper is lost with only the header line to expose it after the fact |
| 4 | Over-rotation on corrections | `VISIBLE WITHIN A DAY` at the format boundary (pinned printer refuses attribute-stripping and timestamp loss; supersessions are append-only, so the overwritten rule is still on record) | Semantic over-rotation inside analysis code — a cure that breaks an unwritten expectation — is caught only by the §6 regression definition if a released mark happens to cover it |
| 5 | Settled laws re-broken by fresh sessions | `IMPOSSIBLE` on the governed path for compilable laws (buildup proof and printer refuse; a fresh session cannot un-refuse them without a diff the checker reads) | Non-compilable laws (taste, phrasing, "not every drop") remain `human_only` checks; and ungoverned paste bypasses everything |
| 6 | Communication violations at his surface | `VISIBLE WITHIN A DAY` for shape (sender requires body + run id, rejects internals; §6 pins plain rendering) | Free prose around the list — relevance, jargon, answering the actual question — remains discipline (accepted limit, §13) |
| 7 | Delegated output consumed without verification | `VISIBLE WITHIN A DAY` on the governed path (nothing publishes unchecked; `WAITING_FOR_CHECKER` is a public state) | Front-desk judgment calls (slot allocation, disposition choices) are recorded but not independently verified |
| 8 | Seat/process mismanagement | `VISIBLE WITHIN A DAY` (leases expire into `RECOVERY_NEEDED` + local notice; resume from stored stage; no heartbeat prompts by design) | A dead front desk with all providers down: stored state is safe but chat is silent until a human notices the local notice |
| 9 | Building on missing/unvalidated deliverables | `VISIBLE WITHIN A DAY` (`LANE_INCOMPLETE` names the missing lane; `develop` header names what a sheet is not; refusal census names what the library lacks) | A deliverable that exists-but-is-wrong (bad phrase data passed as valid) survives until a released mark or his ear contradicts it |

No mode is fully `IMPOSSIBLE`. The design's honest claim is: on the governed path, every listed
mode either refuses loudly or prints its own tell within one publish; off the governed path, the
tells (missing run id, missing headers) make ungoverned output recognizable but not preventable.

---

## Enforced-by-nothing list (v3, honest)

Everything in the design is [assumed] build contract until built; this list is what stays
unenforced even after the build:

1. Every operator-facing session actually being the wrapped kind (F2 — the largest one; header
   tells expose, cannot prevent).
2. A seat hand-pasting ungoverned text into chat (sender bypass by typing; the missing headers are
   the only tell).
3. An unwrapped session announcing "I cannot record that here" (a remembered duty by definition —
   the wrapper cannot police sessions it isn't in).
4. Front-desk slot allocation between paused experiments being wise (deliberately judgment;
   recorded, bounded by budgets, not enforced).
5. The quality of a falsifier beyond checker-runnability (a runnable-but-weak falsifier passes;
   budgets bound the damage).
6. `human_only` classifications being *correct* (the count is now visible in chat; the judgment
   behind each row is not checked).
7. The operator's own patience with honest refusals (a design choice, not an enforcement gap —
   but nothing makes `DROP_PROOF_MISSING` on a beloved track acceptable to him except the census
   having warned him first).

---

## Three six-week walkthroughs I ran against v3

1. **The over-build death (kill shot).** Cured only partially by the §12 re-cut; if quota cannot
   carry governed-machinery build *and* hearing work, v3 says hearing wins and ungoverned output
   gets labelled, not laundered. This is the walkthrough that still worries me most.
2. **The refusal-heavy library.** Census at step 4 runs, reports "412 of 750 tracks cannot print
   laser rows — phrase evidence missing." Operator learns the real state in one chat line in week
   two, instead of discovering it refusal-by-refusal in month two. The program then faces a real
   decision (build phrase evidence, or accept the boundary) with him — which is where a real
   limit should land. Survives.
3. **The quiet capture hole.** Front desk dies; replacement session runs unwrapped for a week;
   two corrections lost. Next governed publish says "Last thing I have recorded from you: Tuesday
   — 'the drop at…'" and he said the corrections Thursday. He sees the hole in one line and
   re-gives two corrections instead of losing them for six weeks. Degraded, visible, survivable —
   the accepted limit behaving as designed.

---

## Open questions and assumptions

1. [unknown] The true library-wide refusal rate under the fail-closed proof (§12 step 4 exists to
   answer this; nothing should be promised before it runs).
2. [unknown] Whether phrase evidence can be *built* for tracks that lack it, or whether those
   tracks are permanently refused for laser rows — this decides how much of the library the
   acceptance gate can ever cover, and belongs to the operator once the census gives him the
   number.
3. [unknown] Whether quota reality (provider families, current GPT-seat outage recorded in program
   state) can carry shadow-mode double-running plus the checker-independence rule at once; v3
   keeps `WAITING_FOR_CHECKER` as the honest stall rather than relaxing independence.
4. [assumed] An intake wrapper is technically feasible on the operator's actual chat surface
   (a wrapper process that commits before the model sees the message). If it is not, §5's capture
   claims degrade to the header tells alone, and that must be said the day it is discovered — the
   design's capture story would then be limit, not mechanism.
5. [assumed] The three-attempt limit and the existing operator rulings carried from program state
   (steering charter, DEVSPLIT immutability) remain operator law; nothing in this round touches
   them.
6. [assumed] `develop` output reaching the operator is *pull* (he asks) or front-desk-judged
   *push*; v3 deliberately does not automate pushing development sheets at him, because unasked
   walls of interim output are dossier §8.6.
