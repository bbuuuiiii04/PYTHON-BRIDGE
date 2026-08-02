# ATTACK_AUTONOMY_SOL — v8 as an autonomous agent organization

**Design attacked:** `docs/plans/active/spectral_program_operating_model_v8_2026_08_02.md`

**Fixed goal:** an organization of agents that keeps building better spectral ears and brain
without the operator having to steer, remind, or catch it doing the wrong work. The four-part list
and his ear remain the acceptance gate. This attack does not change either.

**Mode:** attack only. I did not revise v8, propose a v9, change code, touch `local/`, operate tmux,
or touch the running bridge.

I read v8, the failure dossier, the existing organization doctrine, the build-seat harness,
`PROGRAM_STATE_2026_07_31.md`, sampled the month-long program trail at executive handoffs,
operator interventions, learning turns, stalls, and the latest state, and read all three prior
attacks. Those attacks already cover the operator's daily experience, evidence and machine
failure, musical breadth and cost, and the gap from a passed list to the live instrument. This
attack looks at a different object: the control loop that is supposed to make the ears improve
while he is away.

## Overall ruling

[confirmed] V8 is not an operating model for an autonomous agent organization. It is a careful
run, checking, evidence, refusal, and publication protocol for a list-producing tool. Those are
useful parts, but they begin after somebody has already chosen the right question, the right
experiment, the right evidence, the right panel, and the right next move. V8 assigns those choices
to a `front desk` and records them. It does not tell the organization how to make them, test them,
or replace the chooser when it goes wrong.

[confirmed] That is the exact level where the recorded program failed. The dossier says every
executive filed a realization and rebuilt the process while exact cold recognition stayed at 2 of
34 (`spectral_program_failure_dossier_2026_08_02.md:29-33`). Seven hostile reviews approved a
package that measured drop entrances instead of growls (`:89-95`). V8 adds stronger checks around
the package. It does not add a mechanism that notices the organization picked the wrong package.

## PASS 1 — AUTONOMY

### 1.1 WORST — v8 starts after the autonomous decision has already been made

**What is wrong:** [confirmed] The proposed public verbs are `listen`, `develop`, `evaluate`,
`reproduce`, and `resume`. The stored states begin at `QUEUED` and end at `PUBLISHED`
(`spectral_program_operating_model_v8_2026_08_02.md:78-176,322-385,440-441,491-520`). None answers:
What hearing weakness matters most now? Which lane owns it? Which experiment is cheapest and most
likely to teach something? What should run after it fails? Who opens the next question when no run
is queued?

The one sentence that reaches this level says the front desk chooses which paused idea gets the
next slot (`:540-541`). That is a person-like judgment hidden behind a role name, not autonomous
selection.

**Why it matters to an autonomous org building the ears:** A run system can execute forever only
if someone keeps feeding it good work. The operator's complaint was not that jobs lacked states.
It was that every time he looked, the organization had confidently chosen bullshit. V8 makes the
chosen job cleaner; it does not make the choice better.

**Evidence checked:** [confirmed] V8's full command surface, experiment fields, run states, and
adoption order; the existing org doctrine, where the executive explicitly owns design, sequencing,
and authorization (`docs/agents/multi_agent_org_workflow.md:23-30`); and the prior human attack,
which already noticed that v8's three duties are not mapped onto that org
(`ATTACK_HUMAN_ANGLES.md:346-351`). [unknown] No separate scheduler or current-work policy is named
in the reviewed sources that would fill this gap for the proposed model.

**Concrete failure scenario:** [assumed] The current laser experiment finishes at 2 a.m. The result
is reproducible and honestly worse. No run is queued. The front-desk seat is dead, out of context,
or merely waiting. All workers are healthy and all evidence is safe, but the company does nothing
until the operator appears and asks why it stopped.

### 1.2 The design has replaceable run duties, not a replaceable executive

**What is wrong:** [confirmed] V8 makes three duties replaceable: front desk, builder, and checker.
A replacement resumes from a duty and run id (`spectral_program_operating_model_v8_2026_08_02.md:416-420`).
That is enough to continue a known run. It does not preserve or transfer the executive's current
understanding of why this question matters, which approaches are dead, what result would change
direction, or what should be dispatched next.

The repo's existing org doctrine already knows that executive continuity is different from run
continuity: it requires a live seat-state file with the scoreboard, open gates, exact directives,
and fallback clocks, followed by a fresh check of reality at handoff
(`docs/agents/multi_agent_org_workflow.md:149-165`). V8 does not adopt or replace that mechanism.

**Why it matters:** The trail is dominated by executive handoffs. A builder dying is recoverable if
the task is known. An executive dying is different: the organization can resume the last command
and still lose the reason it was doing that command. That is how a fresh seat repeats a killed
approach with perfect run records.

**Evidence checked:** [confirmed] The v8 replacement clause, the org continuity clauses, and the
program trail's repeated executive handoffs from `exec2` through `exec13`. The program state also
places the open hearing problems and all four list lanes under one owner called “the executive
seat” (`PROGRAM_STATE_2026_07_31.md:54-63`). [unknown] V8 does not say whether that executive even
exists in its front-desk/builder/checker model.

**Concrete failure scenario:** [assumed] A new front-desk seat sees a clean failed run and the same
open capability gap. It does not know that two earlier seats already tried the same underlying
question under different names. It writes a new falsifier, chooses a new panel, and spends another
six hours rediscovering the same limit.

### 1.3 Honest stop states stop the job; nothing keeps the company moving

**What is wrong:** [confirmed] V8 handles a dead process, a missing checker, budget exhaustion,
storage exhaustion, missing inputs, and an unresolved message by recording or reporting the block
(`spectral_program_operating_model_v8_2026_08_02.md:93-124,449-487,509-520,526-532,551-555`). It
does not say that the organization must immediately move an available seat to a different useful
hearing question while the blocked item waits.

The global oldest-first checker rule can also leave every later governed publication behind one old
unchecked result (`:470-478`). That may be honest queue discipline, but it is not a plan for using
the builders, other lanes, or other evidence while checking is unavailable.

**Why it matters:** Autonomy is not pretending a hard block disappeared. It is keeping the rest of
the program useful. A company with four hearing lanes and hundreds of tracks should not become idle
because one provider, one codec, or one storage path is blocked.

**Evidence checked:** [confirmed] Every v8 refusal and pause state, the checker queue, and the
recorded standing instruction after the operator asked why work had stopped: reversible work should
continue without waiting for permission
(`PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md:2522-2527`). [unknown] V8 has no work-conservation rule
outside the narrow adoption-versus-hearing lease priority.

**Concrete failure scenario:** [assumed] The laser lane reaches `WAITING_FOR_CHECKER` for three
days. Track energy, drop energy, accents, codec coverage, and cheap dev probes all have runnable
work. V8 faithfully preserves the laser result and its queue place. No rule dispatches any of the
other work, so the operator returns to a perfectly recorded three-day stall.

### 1.4 The adoption order is a build checklist, not a week-away operating loop

**What is wrong:** [confirmed] V8 gives ten adoption steps, ending with measurement, shadowing, and
an operator-approved switch (`spectral_program_operating_model_v8_2026_08_02.md:567-614`). It does
not define normal operation after adoption: no daily or per-result cycle chooses a new hearing gap,
runs a probe, checks the result, promotes or rejects a capability, and feeds the next question back
into the queue.

**Why it matters:** A checklist can build the factory once. His proof of autonomy is the ears getting
smarter unattended. That needs a repeated loop. Without one, the organization becomes a tool he can
ask to run, not a company that advances the ears while he is absent.

**Evidence checked:** [confirmed] All ten adoption steps and the short operator version at v8
`:691-717`. Both begin with him naming a track or later initiating the blind presentation. The final
acceptance remains his fixed right; the missing part is what the agents do between his appearances.

**Concrete failure scenario:** [assumed] He is gone for a week. On day one, the current experiment
finishes. The remaining six days are undefined. Nothing in v8 requires another question to be
selected, another lane to advance, or a sealed blind-ready package to be prepared for when he
returns.

## PASS 2 — COMPOUNDING

### 2.1 WORST — the permanent store remembers runs, not better ears

**What is wrong:** [confirmed] V8 stores enough bytes to reproduce a result: code, patch, audio,
models, frames, evidence, output, timings, builder, and checker
(`spectral_program_operating_model_v8_2026_08_02.md:422-441`). It never defines a current best
analyzer for a lane, how a candidate becomes that analyzer, how an older one is restored after a
regression, or which exact learned artifact the next experiment must begin from.

**Why it matters:** Reproduction proves the organization can make the same ears say the same thing
again. Compounding means tomorrow's ears contain something they did not contain yesterday. A pile
of perfectly reproducible candidates can grow while the active analyzer stays unchanged or changes
by whoever happened to edit it last.

**Evidence checked:** [confirmed] The manifest, evaluator, adoption order, and storage clauses.
Searches of v8 found no current champion, promotion, rollback, or capability registry. The month
record shows why the distinction matters: many process artifacts accumulated while exact cold
recognition did not (`spectral_program_failure_dossier_2026_08_02.md:16-33`).

**Concrete failure scenario:** [assumed] Three candidates each improve a different set of dev
moments. All runs are sealed and checked. Seat A edits the analyzer to candidate 3, which silently
loses candidate 1's gain. A successor sees three valid run ids but no authoritative current ears and
starts from whichever checkout is present.

### 2.2 The evaluator describes change but cannot cause learning to carry forward

**What is wrong:** [confirmed] V8 deliberately prevents the evaluator from saying `improved`,
`progress`, or `better`; outside its narrow regression floor it only describes differences
(`spectral_program_operating_model_v8_2026_08_02.md:338-381`). That honesty is useful. But no other
component consumes those differences and decides whether to keep, combine, revert, or branch the
candidate.

V8 also accepts that the panel, baseline, and falsifier can be weak choices (`:347-358,526-538`).
It records who chose them, but the next round has no rule for distrusting or replacing a weak choice.

**Why it matters:** A report is not a learning step. If every conclusion waits for a fresh seat to
read many rows and exercise undocumented judgment, the program restarts at each handoff. That is
the recorded pattern the new model was supposed to stop.

**Evidence checked:** [confirmed] The entire evaluator contract and the front-desk slot decision.
The only automatic musical regression catches a previously paired mark becoming unpaired or a
previously ready track refusing. Start drift, length change, and shrinking overlap can remain
musically wrong until the operator vetoes them (`:376-381`).

**Concrete failure scenario:** [assumed] A candidate finds two new marks but moves five starts one
beat early. The report shows every change. Nothing selects a verdict. One seat calls the coverage
gain worth it, the next calls the timing loss fatal, and a third reruns the experiment under a new
baseline. The ears do not accumulate a stable decision.

### 2.3 Evidence accounting proves that his words were touched, not that the analyzer learned from them

**What is wrong:** [confirmed] V8 can prove that every active judgment was compared, compiled,
supplied as analysis input, held for human use, or marked not applicable. For `analysis_input`, it
only proves that changing the converted input changes the hash received by a named code path
(`spectral_program_operating_model_v8_2026_08_02.md:263-306`). The design openly says this does not
prove understanding.

There is no required step that turns a correction into training data, changes a feature or model,
tests the changed ears, and records what capability survived. “Teacher material” is a permission
to use the marks, not a teaching method (`:389-393`).

**Why it matters:** The month record says the first meaningful turn came when the program finally
trained on his marks after spending weeks comparing and guarding them
(`PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md:134-143`). V8 can account for every word and still use
all of them only as comparisons. The custody system gets smarter; the ears do not.

**Evidence checked:** [confirmed] V8's evidence schema and use proof, the trail's teacher turn, and
the failure dossier's record that 54 judgments existed while only six were used
(`spectral_program_failure_dossier_2026_08_02.md:110-128`).

**Concrete failure scenario:** [assumed] Every growl correction is imported, reconciled, and listed
as `compared`. The published accounting line says all judgments are accounted for. The analyzer's
weights, feature set, and decision rule never change. The organization passes evidence custody and
learns nothing.

### 2.4 Negative knowledge is not a first-class thing a successor must inherit

**What is wrong:** [confirmed] An experiment stores a question, allowed files, falsifier, panel,
budget, and evidence (`spectral_program_operating_model_v8_2026_08_02.md:524-528`). A run stores
inputs and outputs. V8 does not require one durable statement of what the result killed, what
remains unknown, why the next question follows, or which apparently different proposals are the
same failed idea.

The current program state already contains an effective anti-circle rule — three work orders asking
the same musical question mean the program is circling (`PROGRAM_STATE_2026_07_31.md:290-300`) —
and the later trail used a question-level attempt counter (`PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md:152-155`).
Neither appears in v8.

**Why it matters:** Failed approaches are part of capability. If they are not carried forward in a
form that blocks repeats, each fresh seat can spend the same allowance learning the same lesson.
That is restarting with more paperwork, not compounding.

**Evidence checked:** [confirmed] V8's experiment and handoff fields, the state file's anti-circle
rule, the trail's attempt counter, and the dossier's “every exec seat filed its realization” record.

**Concrete failure scenario:** [assumed] One experiment kills “loudest local attack identifies the
sound.” The next seat proposes “strongest onset inside the region.” The names differ, but the
musical question and failure are the same. No stored equivalence or attempt count fires, so the
program pays again.

### 2.5 V8 has no shared capability view across the four required ears

**What is wrong:** [confirmed] V8 correctly keeps lane dependencies separate and builds the other
lanes one at a time (`spectral_program_operating_model_v8_2026_08_02.md:145-157,593-595`). It does
not keep a living view of each lane's present capability, weakest sound classes, coverage holes,
current best artifact, next test, and last movement.

The real state file shows the consequence: lasers owned the whole program while track energy, drop
energy, and accents remained open rows; three of the four list parts had to be restored explicitly
because they had vanished from boot files (`PROGRAM_STATE_2026_07_31.md:48-61`).

**Why it matters:** One hard lane can consume the company indefinitely. A real organization must be
able to tell that laser timing is flat while accent implementation or energy hearing can advance,
then assign work without losing the laser question.

**Evidence checked:** [confirmed] The lane matrix, adoption order, and current four-lane state.
[unknown] No common capability record is named in v8.

**Concrete failure scenario:** [assumed] The laser lane spends a week on its third timing idea while
accented moments remain unimplemented. Every laser run is well governed. The full list stays
impossible because no mechanism notices that the company's best next gain is another lane.

## PASS 3 — SELF-CORRECTION

### 3.1 WORST — the checker can disprove a bad run and still approve a bad program

**What is wrong:** [confirmed] V8's checker reruns the bundle, reads changed files, and injects wrong
identity, missing audio, missing lane inputs, absent phrase data, corrupted cache, unresolved
evidence, forbidden blind-key access, and process death
(`spectral_program_operating_model_v8_2026_08_02.md:443-447`). These are checks on whether the
artifact and its claimed process are real.

The checker is not required to ask whether the experiment answers the operator's musical question,
whether the lane is optimizing the wrong thing, or whether this is the third repackaging of a dead
idea. The failure dossier says the old gates all asked whether work was internally consistent and
never asked whether it was what he requested (`spectral_program_failure_dossier_2026_08_02.md:132-149`).

**Why it matters:** The worst July package was not corrupt. It was the wrong object, reviewed seven
times. V8 is strongest against corruption and weakest against a clean wrong object. That lets the
same class of bullshit receive a more credible `VERIFIED` label.

**Evidence checked:** [confirmed] The full checker injection list, the evaluator limits, and the
seven-review failure record. The current steering charter created a separate operator-frame check
for exactly this reason (`PROGRAM_STATE_2026_07_31.md:290-300`); v8 does not include it.

**Concrete failure scenario:** [assumed] A builder creates a perfectly deterministic score for
whether a marked moment outranks other moments in its track. The checker reproduces every value,
proves no key leaked, tests crashes, and approves the run. The program spends a week improving that
score. The operator later asks why anything is being ranked at all.

### 3.2 A live-but-circling lane looks healthy to every v8 monitor

**What is wrong:** [confirmed] V8 detects a dead process through lease expiry and
`RECOVERY_NEEDED`; it limits an individual experiment with a cost budget; and it can stop a run when
its declared falsifier fires (`spectral_program_operating_model_v8_2026_08_02.md:509-532`). None
detects a healthy process repeatedly asking the same question with new wording while the actual ears
stay flat.

There is no question identity, development attempt count, no-movement clock, or automatic “kill
this line and choose another” state. The three-attempt counter exists only for presentations on one
blind key (`:409-412`), not for ordinary development questions.

**Why it matters:** A stuck lane is more dangerous than a crashed one because it keeps consuming
allowance and producing plausible evidence. The trail's biggest waste was active, reviewed work,
not dead processes.

**Evidence checked:** [confirmed] V8's lease, budget, falsifier, and blind-attempt rules; the state
file's three-same-question circling test; and the trail's later mechanical attempt counter.

**Concrete failure scenario:** [assumed] Three six-hour experiments alter attack windows but leave
exact location and length unchanged. Each uses a distinct runnable falsifier and finishes under
budget. Every process and run is healthy. V8 never declares the line stuck, so a fourth variant is
legal and the company keeps circling unattended.

### 3.3 The design records weak scientific choices but does not challenge them

**What is wrong:** [confirmed] V8 admits a worker can choose a convenient panel, weak baseline, or
weak but runnable falsifier. It prints the chooser and refuses to call the result progress
(`spectral_program_operating_model_v8_2026_08_02.md:347-358,526-538`). That protects the wording.
It does not protect the program's work queue, because the same front desk that chose or accepted the
experiment also chooses what gets the next slot (`:540-541`).

No independent seat attacks the question and measurement before compute. The checker attacks the
finished run, after the costly choice is already made.

**Why it matters:** Wrong targets can be fully predeclared. The invented ranking metric would have
become more honest under v8 — named panel, named baseline, no `improved` word — but it still could
have directed the month's work.

**Evidence checked:** [confirmed] The accepted evaluator limits, experiment fields, slot choice,
and the dossier's invented-metric record (`spectral_program_failure_dossier_2026_08_02.md:35-53`).

**Concrete failure scenario:** [assumed] A worker registers a panel where a rank metric is easy to
move, chooses an old baseline, and writes a falsifier that only asks whether rank changes. The run
is honest. The report names every limitation. The front desk reads the change as useful and orders
another rank experiment. No machine objects because every machine is checking the declared game.

### 3.4 The operator-frame critic that existed in the real program disappears from v8

**What is wrong:** [confirmed] After repeated failures, the current program added an operator proxy
that reads his words and marks rather than the process record and asks one question: is this what he
asked for, or would he kill it on sight? It can veto work before dispatch
(`PROGRAM_STATE_2026_07_31.md:290-300,323-327`). The later trail added a keeper that judged every
executive dispatch as aligned or bullshit (`PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md:134-150`).

V8 names only front desk, builder, checker, and dispatcher. It has no separate direction check and
no required press-play reading before an experiment consumes time.

**Why it matters:** The proxy and keeper were imperfect and still depended on agent judgment, but
they at least aimed a separate lens at the failure the ordinary review chain missed. Removing that
job while expanding the ordinary checker's power moves the design back toward the seven-review
failure shape.

**Evidence checked:** [confirmed] V8's complete duty list, the steering-charter job split, the
keeper record, and the existing org doctrine's artifact-focused review chain. [unknown] V8 never
states that the front desk implicitly performs this independent check; if it did, it would be
self-review, not independence.

**Concrete failure scenario:** [assumed] The front desk dispatches a large run that improves
manifest coverage but cannot change a single musical answer. The builder and checker do their jobs
correctly. The missing direction critic would have killed it before compute; in v8, the operator is
the first person likely to ask why it exists.

### 3.5 V8 explicitly leaves musical nonsense for the operator to catch

**What is wrong:** [confirmed] A 513-beat span may pair with one mark and remain in the comparison;
v8 says degenerate output can stay musically wrong until the operator vetoes it
(`spectral_program_operating_model_v8_2026_08_02.md:376-381`). More broadly, only a future track
chosen and judged by him adds fresh generalization evidence (`:72-74`).

This is honest about the limits of automatic musical judgment. It is also proof that v8 is not the
self-correction system requested. It has no substitute dev-side check that treats obvious musical
nonsense as a reason to stop a lane before he looks.

**Why it matters:** His ear must remain the final acceptance gate; that does not mean his attention
must remain the first detector of absurdity. If every novel nonsense class waits for him, the
organization's autonomy still depends on peeking.

**Evidence checked:** [confirmed] The evaluator's explicit accepted limit, fresh-blind boundary,
and the dossier's record that shipped rows were musically impossible even while all gates were
green (`spectral_program_failure_dossier_2026_08_02.md:87-106,185-205`).

**Concrete failure scenario:** [assumed] A candidate produces one 300-beat laser ride, improves
several ordinary rows, and stays inside its registered comparison. The checker verifies it. No
automatic rule rejects the musical absurdity. The operator sees it on his next check-in and again
becomes the program's bullshit detector.

## PASS 4 — WHAT AN ORG BUILT FOR THIS WOULD HAVE THAT v8 LACKS

This pass does not offer a replacement design. It names the concrete organization functions that
must exist for the autonomy claim and shows that v8 has no place where they happen.

### 4.1 No machine-readable north-star work queue

**What is wrong:** [confirmed] V8 has run queues and a checker queue. It has no queue of capability
gaps tied to the four required list lanes, no evidence-backed priority, and no rule that turns the
latest result into the next runnable question. “The front desk chooses” is the entire selection
mechanism.

**Why it matters:** Work choice cannot survive a dead or confused executive if it exists only in
that seat's judgment.

**Evidence checked:** [confirmed] V8's stored tables, states, adoption order, and front-desk clause;
the state file's current open-row table is the nearest existing artifact, but it names owners and
facts, not automatic selection (`PROGRAM_STATE_2026_07_31.md:48-65`).

**Concrete failure scenario:** [assumed] Two lanes are runnable: a cheap accent implementation and
a fourth laser timing variant. The last executive preferred lasers. With no priority record the new
seat repeats that preference, although the accent lane is the only work that can make the four-part
list more complete this week.

### 4.2 No question-level stuck detector and automatic reassignment

**What is wrong:** [confirmed] V8 can expire a process lease but cannot expire an idea. An org built
for unattended work would need a stable question identity, counted attempts, a stated movement
measure, and a mechanical action when the count or flatline fires: stop that line, preserve the
evidence, and assign the next different question. Those exact ideas appeared late in the real
program, but v8 did not carry them in.

**Why it matters:** Process health without question health is how weeks disappear while every pane
looks busy.

**Evidence checked:** [confirmed] V8's absence of development attempt or flatline states, compared
with `PROGRAM_STATE_2026_07_31.md:327-332` and
`PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md:152-155`.

**Concrete failure scenario:** [assumed] The third attempt at the same location question finishes
flat. A real stuck detector would retire the question and release the seats. V8 records another run
and waits for a person to notice the pattern.

### 4.3 No versioned capability that is promoted, inherited, and reversible

**What is wrong:** [confirmed] V8 stores candidate run bundles but no authoritative “these are the
current ears” record per lane and sound class. It has no checked promotion and no automatic return
to the prior ears when the next candidate breaks a retained capability.

**Why it matters:** Capability cannot compound if a handoff cannot name the exact analyzer/model
artifact it inherits and why that artifact won.

**Evidence checked:** [confirmed] The run manifest, evaluator, regression floor, and adoption
steps. None names promotion, current champion, or rollback.

**Concrete failure scenario:** [assumed] A candidate improves growl recall and breaks sustain
lengths. The raw report contains both facts. One seat keeps it; the next reverts part of it by hand;
the third cannot reproduce the combined state. The organization has more evidence but no stronger
shared ears.

### 4.4 No continuous ears-progress record that the work chooser must obey

**What is wrong:** [confirmed] V8 rightly rejects one fake summary score. It replaces it with
detailed per-mark differences, but does not define a small stable set of capability facts the
organization must update and use after every change: exact location and length on known dev marks,
misses, unjudged output, refusals, and coverage split by lane and sound class. It also has no
flatline rule over those facts.

**Why it matters:** Refusing one number does not remove the need to know whether the ears moved. If
the work chooser can ignore the evidence or choose a new panel each time, process activity becomes
the real scoreboard again.

**Evidence checked:** [confirmed] V8's separate-lane evaluator, panel-choice limit, and ban on
positive verdicts; the trail shows stable musical facts such as 12/31 both-exact and 25/32 located
were available late in the program (`PROGRAM_TRAIL_2026_07_01_to_2026_08_02.md:152-161`) but v8
does not make any such capability record part of organization state.

**Concrete failure scenario:** [assumed] Ten runs land in a week. Each has a different convenient
panel and a detailed difference report. There is no stable before-and-after view across the week,
so the company cannot tell whether the ears improved or merely moved errors around.

### 4.5 No lossless handoff of the learning argument

**What is wrong:** [confirmed] V8 says a replacement uses stored duty and run id. An autonomous org
needs the successor to receive, and verify, at least the current capability artifact, open gaps,
killed approaches, active questions and attempt counts, why each queued item follows from evidence,
and the exact next safe dispatch. V8 stores pieces of this across manifests and experiment rows but
does not require one boot view or an acknowledgment that the successor understood and took over.

**Why it matters:** File survival is not understanding survival. The trail proves thousands of
pages can survive while a new executive rebuilds the process and repeats a realization.

**Evidence checked:** [confirmed] V8's replacement line, the existing org's handoff rules, the
1,143-line state file, and the dossier's unchanged 2-of-34 statement. [assumed] More stored prose
would not by itself cure this; the missing part is a required, current, checked handoff of capability
and next-action state.

**Concrete failure scenario:** [assumed] A successor can reproduce yesterday's run exactly but
cannot answer why the next queued probe exists or what earlier result would make it redundant. It
runs it anyway because reproduction state survived while the learning argument did not.

### 4.6 No defined behavior for a full week without the operator

**What is wrong:** [confirmed] V8 defines what happens when he names a track and what only he may do
at the final blind and switch. It does not define unattended weekly behavior. There is no requirement
to keep at least one useful hearing question active, switch lanes on a real block, prepare a sealed
blind-ready package without exposing it, spend within a weekly allowance, or return one compact
account of capability gained, lost, and still unknown.

**Why it matters:** This is the direct test of the autonomy claim. The final ear verdict may
correctly wait for him. Work selection, development, checking, failure recovery, and preservation
of the next blind candidate should not.

**Evidence checked:** [confirmed] The full v8 operator version (`:691-717`), adoption order, pause
states, and the autonomy order in the current state file, which says his input is required for
nothing while development continues (`PROGRAM_STATE_2026_07_31.md:258-266`). V8 does not encode
that order as behavior.

**Concrete failure scenario:** [assumed] He leaves Sunday. Monday's candidate fails. Tuesday the
checker is quota-blocked. Wednesday storage reaches its limit. Other lanes and cheap probes remain
available, but no policy reassigns work. On Sunday he returns to a week of accurate notices and no
smarter ears.

## Combined verdict

**[confirmed] For the corrected goal, v8 is the wrong artifact entirely.** It is salvageable only
as a subordinate run-and-publication contract inside a different operating model. Its strong parts
answer: Can this exact result be reproduced? Was evidence accounted for? Did an independent checker
test the run? Can a bad or incomplete body be withheld honestly? Those questions matter.

They do not answer the autonomy questions: What should the company work on next? How does a result
change the active ears? How does a dead approach stay dead across executive handoffs? Who detects a
cleanly executed wrong objective? What keeps useful work moving for a week when the operator is not
there?

[confirmed] The single worst failure is that v8 makes the front desk choose the next idea while
providing no independent check or mechanical rule for that choice. Everything below that choice can
be sealed, reproduced, and verified. The choice can still be the ranking metric nobody requested,
the eighth review of the wrong package, or the fourth variation of a flat question. The system will
then produce exceptionally trustworthy evidence that the organization spent its time on the wrong
thing.

[assumed] Building v8 as the main operating model would therefore repeat the recorded month in a
cleaner form: more reliable runs, more honest refusals, and no guaranteed compounding of the ears.
The run-record, evidence, refusal, and checker pieces may be worth keeping as tools. They have not
earned the title “autonomous agent organization,” and they should not be mistaken for the mechanism
that makes the ears improve unattended.
