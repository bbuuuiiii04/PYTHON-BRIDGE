# ATTACK_AUTONOMY — is v8 an operating model for an autonomous org, or for a vending machine?

**Written 2026-08-02 by a fresh adversarial seat with no history in this work. Attack only —
no revision, no design version, nothing changed except this file.**

**The goal judged against:** an organization of AI agents that works AUTONOMOUSLY toward his
north star — and the thing it must autonomously build is the spectral "ears and brain" behind
lighting cues, lasers, energy, and accented moments. One goal: the org exists to build the ears,
and the ears getting smarter unattended is the proof the org works. His words: *"This is supposed
to be autonomous, but everytime I take a peek at the program I immediately see you doing some
bullshit."*

**What I read:** v8 in full (`docs/plans/active/spectral_program_operating_model_v8_2026_08_02.md`);
the failure dossier in full; `docs/agents/multi_agent_org_workflow.md` and
`docs/agents/opus_seat_harness.md` in full; `local/spectral_v5_2026_07_17/PROGRAM_STATE_2026_07_31.md`
in full (1,143 lines); the trail (`PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md`, 6,535 lines) sampled
at the head, the 07-24/07-25 windows, the 07-27 pause, and the full 08-01 tail; and all three prior
attacks (`ATTACK_HUMAN_ANGLES.md`, `ATTACK_SYSTEM_ANGLES.md`, `ATTACK_NORTH_STAR.md`) so I would
not repeat them. Where a prior attack already holds a finding, I cite it and push only the new angle.

**The one-sentence verdict up front:** [confirmed] v8 is a rulebook for how a single result may
travel from a run to his chat. It contains no mechanism for choosing work, no mechanism for
getting smarter between rounds, no mechanism for noticing a lane aimed at the wrong thing, and no
definition of what the program does when he is absent — which means it is not an operating model
for the thing he says he is building. Detail and evidence below, worst first in each pass.

---

## PASS 1 — AUTONOMY: can the org decide what to do next without him?

### 1.1 WORST — every verb in v8 waits for a human to type it. Nothing in the design ever starts work.

**What is wrong:** [confirmed] v8's entire surface is five reactive commands — `listen`,
`develop`, `evaluate`, `reproduce`, `resume` (§2, §6, §8, §9) — plus a `launchd` job that only
checks leases (§9). Every one of them runs when someone invokes it. There is no scheduler, no
work queue, no "when idle, do X," no standing loop. §14 says it plainly: *"you name a track"* —
the operator is the trigger for the flagship command. The only sentence in the whole document
about choosing work is one line: *"The front desk chooses which paused idea gets the next slot;
that is recorded judgment, not arithmetic"* (v8:540-541) — a human-shaped judgment with no
charter, no inputs, no rule, and no obligation to choose anything at all.

**Why it matters:** an autonomous org's first property is that work continues when nobody is
typing. His autonomy order is on the record verbatim: *"don't stop until this fully passes … my
input is not required for anything, i have given u everything u need … if you reach a wall,
assign fresh sessions"* (PROGRAM_STATE §2 ruling 39, V:891-898), and before that: *"yes go. why
are we stopped??? we should never stop for anything"* (trail:2522-2525, 07-24), and *"whyd u
stop"* (trail:3117, typed at the exec5 pane after the program parked itself as "program WAITS ON
BRANDON," trail:3110-3111). The month's record shows the org repeatedly idling on him. v8's
answer to that record is a design in which idling is the default state: with no human at a
keyboard, v8's machinery does exactly nothing except expire leases.

**Does v8 fix the month's stopping problem or codify it?** Codifies it. Worse than codifies it —
v8 adds new mandatory stops the old program didn't have: `WAITING_FOR_CHECKER` halts every full
list until a second provider family accepts (§8), and the record shows that famine is real, not
hypothetical (all GPT reviewer seats quota-dead until Aug 5 — PROGRAM_STATE §8, seat map);
`EVIDENCE_NOT_RECONCILED` halts all publication until someone files paperwork on his own casual
chat messages (§5 — ATTACK_HUMAN 1.6 holds the operator-experience half; the autonomy half is
that the halt has no owner and no clock, so it is an indefinite stop that no agent is charged
with clearing). [confirmed]

**Concrete failure scenario:** he goes to bed after saying "keep going." The current dev
iteration finishes at 3am. Under v8 there is nothing that decides what runs next — no rule says
the next probe dispatches, no rule says the phantom rate gets measured, no rule says anything.
The seats that would decide are exactly the seats v8 declines to govern (v8:616-628 explicitly
disclaims any authority over seat dispatch). The org is autonomous in precisely the sense a
parked car is.

### 1.2 The only progress meter the design accepts requires him personally, so the org cannot even know it is winning without him.

**What is wrong:** [confirmed] v8 §1: *"Only a first-run future track chosen and judged by the
operator can add fresh generalization evidence"* (v8:73-74). §12 step 10: *"Only the operator may
initiate or accept a fresh blind presentation"* (v8:613-614). And §6 forbids the evaluator from
ever emitting *"improved, progress, better, or a positive verdict"* (v8:347) even on a
preregistered panel. Put those three together: the machine may never say it is doing better, the
only evidence class that counts as real is one only he can create, and he must personally start
it. His ear as the final acceptance gate is right and fixed — that is not the attack. The attack
is that v8 provides **no internal progress currency at all** for the weeks between his ears: no
dev-set scoreboard, no cold-attempt discipline on development tracks, nothing an agent may use to
decide "this direction is working, continue" versus "this is dead, kill it."

**Why it matters:** the actual record proves the program needed exactly this and had to invent
it outside any operating model: the steering charter's dev/held-out split, predeclared kill
floors, retry budgets (3 graded attempts per held-out track for the life of the program —
PROGRAM_STATE ruling 47.1), and the circling test (*"numbers standing still = circling, numbers
moving = progress"* — ruling 47.5). The 08-01 tail of the trail shows that machinery working
autonomously all night: TEACH14 kill fired as predeclared, TEACH15 kill fired, the cheap finder
declared dead in writing, MODELS1 dispatched as the ordered next move — all without him
(trail:6494-6535). **None of that machinery exists in v8.** No retry budget, no kill-floor
scoreboard, no circling rule, no step-back rule, no fresh-sessions-at-walls rule. v8 supersedes
v7 and answers ROUND_7, but the one method in the entire month's record that actually moved the
number is in the charter, and v8 does not carry a line of it. [confirmed by search: "probe,"
"retry," "circling," "step back," and "dev split" concepts absent from v8 except the §7
teacher-material shadow]

**Concrete failure scenario:** the org runs unattended for a week under v8. Builders build,
checkers check, refusals are counted. At the end of the week nobody — not the seats, not him —
can say whether the ears hear better than last week, because the only mechanisms that could say
so are either forbidden (verdict words), unbuilt (no dev scoreboard), or waiting on him (fresh
blind). The honest weekly report is "we produced N governed artifacts," which is the July failure
restated with hashes.

### 1.3 The rows that genuinely need his word have no home, so they will either block or vanish.

**What is wrong:** [confirmed] The program's live state contains exactly the object an autonomous
org needs for operator dependencies: §1a open rows "pending his word, never blocks" (New Sky
3:32.8, Empire 3:50.4, TYNAN 1:15.6 — PROGRAM_STATE §1a), implementing his ruling *"write down
unsettleables, never queue him"* (six-clause governance ruling, clause 4). v8 has no such
concept. Its vocabulary for operator involvement is: a refusal (`EVIDENCE_NOT_RECONCILED`), a
rejection trigger (*"the operator refutes it,"* §10), and the blind-presentation monopoly (§12).
There is no pending-his-word row, no rule that a question for him is parked visibly and worked
around, no channel that batches his decisions for whenever he next appears.

**Why it matters:** those rows are where autonomy is won or lost. The month shows the two
failure directions: park everything on him ("program WAITS ON BRANDON," trail:3110) or silently
resolve his calls without him (the invented ranking metric, dossier §2). The open-row mechanism
was the org's hard-won middle path. v8 dropping it means the next implementation re-derives one
of the two failure directions from scratch.

---

## PASS 2 — COMPOUNDING: does round N+1 start from more capability than round N?

### 2.1 WORST — v8 has no place where anything learned lives. Its schema records what ran, never what was found out.

**What is wrong:** [confirmed] The complete stored-state inventory in v8 is: `inbound_message`,
`disposition`, `judgment`, `supersession`, `evidence_use`, `run`, `experiment`, `lease` (§5), plus
run manifests (§8). Every table is about provenance and custody. There is no findings table, no
lessons table, no killed-approaches ledger, no "what we now believe about his sounds and why"
store. §10's experiment row stores a question, falsifier, panel, and budget — and nothing
requires a new experiment to consult, cite, or avoid duplicating the experiments already run and
killed. A builder can lawfully re-register a question the program already answered at full cost.

**And v8 actively deletes the one compounding mechanism the program had:** §11 — *"Experiments do
not write progress essays or one-off state files"* (v8:547-548). The month's record shows that
those state files ARE how anything survived: `RESUME_2026_07_29.md` carried *"the ten ruled-out
hypotheses (three of them the exec's own)"* across a multi-day pause (trail:5607-5620);
`APPROACH_KILL_2026_08_01_cheap_finder.md` killed the finder in writing before replacement work
(trail tail); PROGRAM_STATE §4 is the standing "where the science stands" section that stops
re-litigating Phase 1. Those are the org's memory. v8's answer to "too many papers" (a real
problem — 912 loose markdown files, dossier §1) is to ban the genre instead of giving its
contents a durable home. The paperwork was the disease's symptom; the knowledge inside some of it
was the only asset. v8 throws out both. [confirmed]

**Concrete failure scenario:** iteration 12 under v8. A new builder seat wants to try
stem-restricted matching. The knowledge that a one-recipe stem restriction already failed its
gate (P2-2 FAIL, `full_run_gate = False`, PROGRAM_STATE §4) lives in a file v8's write-wrapper
would have refused to create and its schema has no row for. The builder registers a fresh
experiment with a fresh budget and burns days rediscovering July.

### 2.2 The record shows compounding-of-rules, not compounding-of-capability — and v8 doubles down on exactly that.

**What is wrong:** [confirmed] The trail is the experiment already run. At least eight named
executive seats appear in my samples (exec, exec5, exec7-exec13; 82 mentions), each booting by
re-reading an ever-growing rule corpus — exec13's boot alone: the charter, the verbatim file
*"read to EOF (1457 lines)"*, the dossier, DEVSPLIT, the §11 tail (trail:6479-6484). What grew
monotonically across those handoffs was law: 6 inviolables → 8, 48 numbered rulings, amendments
1-5, a 1,143-line state file. What the growth was for — the cold number — sat at *"2 of 34 to
2 of 34"* by the program's own exec statement (dossier §1) until the charter-method probes
finally moved dev both-exact to 12/31 in the last 24 hours (trail:6470, 6535), with Lowkey cold
still 7/7 found, **0 exact** (trail:6470). The dossier's §7 states the conclusion in his words
and the retro's: writing rules down stopped working; *"any refactor that answers this dossier
with more rule text has failed before it starts."*

v8 is ~700 lines of rule text with a compiler attached. Its compiled parts genuinely improve on
prose law (a printer that refuses beats a memory file nobody re-reads). But compiled or not, it
is all constraint and zero capability: nothing in v8 makes the analyzer better, teaches it from
his vetoes, or carries a solved sub-problem (the start rule, the end-rule gap, the
discrimination diagnosis) into the next round as a built thing rather than a re-readable claim.
ATTACK_HUMAN Lens 4 row 2 called v8 an instance of rigor on the wrong object; the compounding
angle is sharper: **v8 compounds the org's constraints while leaving its capability to start
from zero each round.** [confirmed]

### 2.3 Handoff under v8 loses more than the current practice loses.

**What is wrong:** [confirmed] v8's entire succession story is one sentence: *"A replacement uses
stored duty and run id rather than reconstructing from chat"* (§8, v8:419-420). Duty + run id
resumes a RUN. It does not transfer a program: which approaches are dead, which question is
open, what the current press-play sentence is, what he ruled last night. The current practice —
kickstart files, PROGRAM_STATE, the charter-first boot — is crude and expensive, but it
demonstrably let exec13 boot cold and dispatch correct work within half an hour
(trail:6479-6493). v8 bans the state-file genre (2.1) and specifies no replacement boot
artifact. A seat that dies under v8 is succeeded by a seat that knows its lease and nothing
else. [confirmed for the design as written; ATTACK_HUMAN 3.3 holds the adjacent cold-boot
ambiguity finding — this is the narrower point that even a warm handoff has no defined payload]

---

## PASS 3 — SELF-CORRECTION: what catches bullshit without him looking?

### 3.1 WORST — v8 deleted the one organ the program built to catch wrong-aim work: nobody in v8 asks "is this what he asked for?"

**What is wrong:** [confirmed] v8's role list is complete at three: *"front desk captures and
sends; builder changes the offline analyzer; independent checker tries to disprove the exact
run"* (§8, v8:418-419). The checker's mandate is reproduction and injected faults (§8) plus
scanning changed files for hardcoded answers (§7). Every duty is about whether the run is
internally honest. The month's worst failures were all runs that were internally honest and
aimed at the wrong thing: the invented within-track ranking metric that graded a month of work
and *"counted correct finds as failures"* (dossier §2); seven sealed hostile review rounds
passing a package whose own spec said it ranked drop entrances, not growls (dossier §4); rigor
spent on spec versions and probe ladders while *"is this what he asked for?" was never a gate*
(dossier §6, the program's own post-mortem words). The program's answer, ratified by him in the
steering charter, was a dedicated organ: the OPERATOR PROXY seat — boots only from his words,
asks only *"is this what he asked for, or would he kill it on sight?"*, holds a veto
(PROGRAM_STATE ruling 44 FIX 3, ruling 47.4; stood up and issuing on-disk verdicts —
`PROXY_verdicts.md`, PROGRAM_STATE §11 ORGANIZE10). **v8 contains no proxy, no frame check, no
role whose job is aim.** The word does not appear; the function does not exist.

**Would v8 have caught the month's three named failures unattended?** Walk them:
- *The invented metric.* No. It was an internal number; v8 bans verdict words and numbers on
  operator surfaces, but §10 explicitly accepts *"a weak but runnable falsifier"* as a human
  choice, and nothing reviews whether an experiment's question is one anybody asked. A builder
  under v8 can preregister "does his mark outrank all other candidates," pass every custody
  gate, and steer months of work with it — hash-bound. [confirmed]
- *Rigor on the wrong object.* No. v8 cannot see where seat effort goes at all (v8:616-628: seat
  spend is invisible and unrationed by design, a "duty held by whoever dispatches seats").
- *Drop-entrances-instead-of-growls surviving seven reviews.* No. v8's checker re-runs the
  bundle and injects faults — it would have confirmed, seven more times and with better
  stationery, that the package measured drop entrances reproducibly. The one check that killed
  it (score his 31 confirmed moments against the list's own cut) is a frame check, and v8 has no
  seat that runs frame checks. [confirmed]

### 3.2 v8 detects dead processes and blown budgets; it cannot detect a lane that is alive, funded, and going nowhere.

**What is wrong:** [confirmed] v8's stuck-detection inventory, complete: lease expiry →
`RECOVERY_NEEDED` (§9); budget exhaustion → `paused — budget used` (§10); falsifier fires →
rejected (§10); regression floor on an identical panel (§6). Every trigger needs the lane to
either die, run out of money, or get worse on paper. A lane that runs healthy experiments whose
numbers stand still — the precise shape of July, eleven execs and *"2 of 34 to 2 of 34"* — trips
nothing. The circling rule that names this failure (*"three same-sentence work orders =
circling"*; *"numbers standing still = circling"* — charter, ruling 47.5) has no v8 equivalent,
and since the evaluator may never compare rounds in verdict terms (§6) and progress essays are
banned (§11), v8's machinery cannot even represent the sentence "this lane has not moved in three
rounds."

**Concrete failure scenario:** a builder spends four weeks on refinements to a picker whose
both-exact number is flat. Every run is sealed, checked, and reproducible. Budget renews per
experiment. Under v8 the first entity to notice the flatness is him, on a peek — the exact
"every time I take a peek I immediately see bullshit" experience the redesign exists to end.

### 3.3 The surface his peeks actually land on stays ungoverned — conceded by v8, unsolved for the org.

[confirmed, held jointly with ATTACK_HUMAN 1.1/Lens 4 row 8 — recorded here only for the org
angle.] What he sees when he peeks is seat behavior: free prose, idling panes, over-engineering
in flight. v8 governs result bodies and admits free prose and hand-pasting are out of reach
(§11, §13) and that seat dispatch sits outside every enforcement point it has (v8:616-628). For
a *list pipeline* that is an accepted limit; for an *autonomous org* it means the entire org
layer — the thing he is actually building and the thing he actually peeks at — has no
self-correction in v8 at all. The doctrine that does govern seats
(`docs/agents/multi_agent_org_workflow.md`, `opus_seat_harness.md`) is real and field-proven,
but v8 neither uses it, extends it, nor tells a cold seat how the two structures relate
(ATTACK_HUMAN 3.3 holds that finding).

### 3.4 What v8 DOES catch, honestly credited.

[confirmed] Bad-artifact bullshit gets real, mechanical detection: malformed rows, missing
lengths, buildup laser rows, wrong-lane bodies, unhashed sends, silent trims, panel swaps,
fake "cold" claims on exposed tracks. Those map to genuine July wounds (the 2:24 buildup row,
the stripped timestamps) and the printer/proof/sender trio would have caught those specific
artifacts unattended. The distinction that decides this pass: v8 catches bad OUTPUTS; the month
died of bad AIMS; and every aim-checking mechanism the program invented under fire (proxy,
circling test, press-play sentence, vision-conformance dispatch gate) is absent from v8.

---

## PASS 4 — WHAT AN ORG BUILT FOR THIS GOAL WOULD HAVE THAT v8 LACKS

Concrete and mechanical, held against what the record proves the program needed. Each item names
the v8 gap and the already-proven seed it could grow from.

1. **A work chooser.** A standing, machine-readable queue derived from the open rows (§1a's four
   lanes + named gaps), ordered by distance-to-the-acceptance-list, with one rule: an idle
   builder takes the top item; nothing idles while the queue is non-empty. The compass law
   already exists in prose (*"dispatch nothing that does not move HIS LIST closer,"*
   PROGRAM_STATE §1). v8's entire treatment is "the front desk chooses the next slot"
   (v8:540-541). [confirmed gap]

2. **A continuous ears scoreboard.** The dev-set numbers the program already computes —
   both-exact / located / phantom rate per iteration, cold-first-attempt discipline, retry
   budgets on held-out tracks — kept as one append-only table that every round must write and
   every dispatch must read. This is the internal progress currency that is valid without him
   (his ear stays the only ACCEPTANCE gate; the scoreboard is only steering). v8 forbids verdict
   comparisons and provides no home for these numbers. [confirmed gap]

3. **A stuck-lane tripwire that fires on flatness, not death.** Mechanical form of the circling
   law: N consecutive completed experiments on one question with no scoreboard movement → the
   lane is automatically paused, its question and kill record posted to the queue for a
   different approach or a fresh seat. The charter states the rule; TEACH14→TEACH15→finder-kill
   →MODELS1 shows agents executing it unattended (trail tail). v8 has lease expiry and budgets
   only. [confirmed gap]

4. **An aim-checking seat with teeth.** The proxy — boots from his verbatim words only, vetoes
   any dispatch or artifact that would die on his sight, verdicts on disk same turn. Already
   ratified by him and running (ruling 47.4, `PROXY_verdicts.md`). v8 deleted the function
   (3.1). [confirmed gap]

5. **A memory that compounds capability.** Three durable stores with mandatory consultation:
   settled science (what is proven/refuted, one home — PROGRAM_STATE §4 is the prototype);
   killed approaches (consult-before-register, so no experiment re-runs a corpse); and a
   teacher loop — every veto, correction, and ruling he issues becomes a dev-set row or compiled
   check within one round, automatically, so his words become training material instead of law
   text. v8 stores messages and runs; it stores no conclusions and closes the essay genre
   without replacing it (2.1). [confirmed gap]

6. **A defined handoff payload.** A boot artifact per seat (kickstart + the scoreboard + the
   queue + the open rows), required at handoff, verified by the successor against reality —
   current practice made structural instead of heroic. v8: duty + run id (2.3). [confirmed gap]

7. **A defined unattended week.** The one-paragraph answer v8 never gives: while he is away, the
   org iterates on the DEV set only (open keys, teacher material), advances the queue, runs the
   scoreboard, kills flat lanes, accumulates pending-his-word rows and a one-page "since you
   last looked" digest; it never burns a held-out attempt, never presents a blind, never touches
   the bridge. Every element already exists somewhere in the charter or the 08-01 trail; none
   exists in v8. [confirmed gap]

8. **Progress measured at the ears, not at his check-ins.** Follows from 2+3: the org's own
   definition of a good week is scoreboard movement on dev plus zero burned held-out attempts —
   not artifact counts, not review rounds passed, not refusals accounted. v8's only countable
   outputs are governed artifacts and refusals, which is how a month of motion with a frozen
   number happened the first time. [confirmed gap]

---

## COMBINED VERDICT — salvageable for this goal, or the wrong artifact?

**[confirmed] v8 is the wrong artifact for the corrected goal, and it is not close.** It is a
serious, honest, well-attacked design for one thing: making a single result's journey to his
chat unfakeable. Judged as that — a custody layer — parts of it deserve to live (the fail-closed
laser proof, the refusal vocabulary, the printer's required fields, run records, the
unjudged-not-wrong evidence boundary; the same slice the prior attacks kept). Judged as the
operating model for an autonomous organization that builds the ears, it fails all four passes at
once: nothing in it starts work (Pass 1), nothing in it accumulates capability (Pass 2), nothing
in it notices wrong aim (Pass 3), and the functions an org needs are not present in reduced form
— they are absent, and in three cases the design deletes working prototypes the program already
paid for: the state-file memory (banned by §11), the operator-proxy aim check (no role for it),
and the charter's probe/kill/scoreboard method (no trace of it). [confirmed]

The sharpest way to say it: the month's record contains exactly one stretch where the org
behaved like the thing he says he is building — the 08-01 overnight, where seats chose work from
a queue of questions, killed two approaches on predeclared floors, declared a dead end in
writing, and dispatched the ordered next move, unattended, with the number moving from 2 to 12
both-exact on dev (trail:6494-6535). Every mechanism that produced that night lives in the
steering charter and PROGRAM_STATE. v8 — written after that night — carries none of it, and
answers the dossier's "why do I keep seeing bullshit when I peek" with governance over the one
surface his peeks never land on. [confirmed]

**What "salvage" honestly means here:** not revising v8 into an org model — the org model
already exists in three proven fragments (the repo org doctrine for seats and review, the
steering charter for method, PROGRAM_STATE §1a/§4 for memory and open rows), and the missing
piece is the small mechanical layer in Pass 4: a queue, a scoreboard, a flatness tripwire, the
proxy kept, a defined handoff payload, and a defined unattended week. v8's custody slice should
be adopted BY that org as its publishing rules — the org's output door, roughly one section of
its constitution — instead of being mistaken for the constitution. Building v8 as written,
first, would spend the program's remaining trust on ten adoption steps of machinery
(v8 §12) that leave the ears exactly as smart as they are today and the org exactly as
autonomous as it was the night he typed "why are we stopped???". [assumed — this is my
judgment; the operator's, as always, outranks it]

**Claim-label summary:** every trail/dossier/PROGRAM_STATE citation above was read at the quoted
line during this attack [confirmed]. v8 absences (no proxy, no queue, no scoreboard, no circling
rule, no handoff payload, no unattended-mode) were verified by full read plus keyword search of
v8 [confirmed]. The 82-mention exec-seat count and 6,535-line trail length are command output
[confirmed]. What a rebuilt org would achieve is projection [assumed]. Whether any model can
hear what he hears remains, as v8 itself says, [unknown] — no operating model, including the one
sketched in Pass 4, changes that; it only changes whether the org finds out faster.
