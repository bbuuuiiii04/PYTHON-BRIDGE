# Fable 5 (high) — redesign how the spectral program is RUN

## Mission

Design the replacement operating model for Brandon's spectral analysis program. The **goal does not
change**. Everything about **how the program is run** does — what counts as progress, who may
invent a measurement, what a gate checks, how his words get into the machine, how work is killed,
and what reaches him.

You are not fixing a lane. You are replacing the management of a company that has burned a month
and moved its one real number from 2 of 34 to 2 of 34.

## Why this exists

Brandon ordered a full overhaul after reading, in his own transcripts, that the program had been
grading itself on a metric he never asked for. He is the operator and sole user, not a software
engineer. He mixes live. He refuses to open documents — chat is the surface. He has said the
current remedy for every complaint ("we'll write it down as standing law") has stopped working, and
he is measurably right.

Your design will be handed to an independent reviewer (Codex Sol, xhigh) whose only instruction is
to try to destroy it. Assume that reviewer will attack the parts you were least sure about.

## The goal — fixed, do not redesign

His acceptance gate, his words, 2026-07-25:

> "WHEN THE LIST WITH LASER WARRANTING MOMENTS, TRACK ENERGY, AND DROP ENERGY, AND ACCENTED
> MOMENTS PASS MY STANDARDS, THAT IS WHEN I DEEM THE BRIDGE IS SUCCESSFUL AND READY FOR LIVE
> WIRING."

One per-track list. Laser moments with **position and length** (length matters as much as where —
lasers ride the moment). Track energy. Drop energy. Accented moments. It passes when his ear says
it passes, cold, on tracks he picks — including I Cannot, Palm of My Hands, and every track he has
marked. Everything downstream of that (wiring, cues, consumers) is after the greenlight.

Two properties of the goal that constrain any design: the machine must **locate**, not rank; and it
must generalize across his 700–800 track library, not be tuned to example tracks.

## Evidence packet

**Read first, in full:** `docs/plans/active/spectral_program_failure_dossier_2026_08_02.md` — the
verified failure record from a full retrospective sweep of every session transcript 2026-07-01 →
2026-08-02 (546 files, 3,754 operator messages, seven independent miners, every quote re-verified at
its exact line). §8 is the ranked list of failure modes; §9 is what he says the program must be.
Treat it as the requirement set. It is evidence, not a design.

**Also authoritative:**
- `AGENTS.md` §0 (how to talk to him), §1 (source-of-truth order), §10 (status language).
- `docs/agents/multi_agent_org_workflow.md` and `docs/agents/opus_seat_harness.md` — the current
  operating model you are replacing. Read them to know what exists, not as constraints to preserve.
- `local/spectral_v5_2026_07_17/PROGRAM_STATE_2026_07_31.md` — current program state.
- The memory store at `~/.claude/projects/-Users-bbui-rb-ss-bridge-v2/memory/`, in particular
  `user_acceptance_gate_the_list.md`, `user_lasers_only_on_drops.md`, `user_true_drop_definition.md`,
  `user_final_vision_energy_fabric.md`, `user_transcription_vision_authoritative.md`,
  `user_accent_layer_vision.md`, `feedback_no_labeling_sessions_ever.md`,
  `feedback_never_hand_work_back.md`, `feedback_measure_dont_estimate.md`,
  `feedback_his_observation_outranks_code.md`.

**Measured facts about the current program (verified 2026-08-02, not reported by any seat):**
`local/` is 32 GB / 87,008 files. `local/spectral_v5_2026_07_17/` is 28 GB with **1,483 loose files
in its root, 912 of them `.md`** — about 100 documents per day. The program's own memory file is
481,630 bytes / 6,444 lines and **cannot be read whole by the tool that is supposed to load it**;
it holds 11 executive watch blocks and reads as an append-only log. Two live memories currently
contradict each other on whether energy work is paused or running.

**Known-stale / do not trust:** anything in `docs/prompts/**`, `docs/plans/**`, `docs/history/**`
without a current status header; any spec version number in the program log; any claim that a lane
is "sealed", "frozen", or "READY" — several such artifacts failed on first contact with his ear.

## What the design must do

Answer every failure mode in dossier §8 with a **structural** change — something about how the
program is built that makes the failure impossible or immediately visible — not with a rule, a law,
a checklist item, or a document. Rules are what this program produced 912 of. He named this
directly: *"everytime i complain about something, you say some bullshit about 'standing law' and
'writing it down' but it seems like that genuinely doesnt fucking do anythign."*

For each failure mode, the honest question is: *what would have to be true about the way this
program is organized for that failure to be impossible, or to surface within one hour instead of
three weeks?* Where the honest answer is "nothing structural — this one really does need a human to
remember," say so plainly rather than inventing a mechanism that will not fire.

The design must at minimum settle:

- **What counts as progress**, in a number he can check himself, that cannot be satisfied by
  producing machinery. The current program's own scoreboard was invented internally and counted
  real finds as failures.
- **Who may invent a measurement, and what makes one legitimate.** Ranking-within-track was adopted
  because it was easy to compute, and steered a month of decisions.
- **What a gate checks.** Every existing gate asks "is this internally consistent?" Eight hostile
  rounds passed the package that burned six hours; seven passed the laser list whose own spec said
  it ranked drop entrances. Direction was never reviewed by anyone.
- **How his evidence enters the machine and cannot leave it.** He has a 54-record judgement corpus;
  the program used six records. His sound descriptions were never written to disk at all. His
  standing order: *"don't forget about any information, don't lose information."*
- **How work gets killed.** Nothing in this program has ever been stopped for failing to move the
  number; lanes were only ever superseded.
- **What reaches him, in what form, how often.** He reads chat, not documents. He wants plain
  English with the mechanism intact, not simplified to nothing and not jargon.
- **How seats are run** — model routing, context handoff, visibility, what a seat may decide alone
  versus escalate, and how the org stops itself from becoming the work. He has repeatedly had to do
  the org's own housekeeping (catching context percentages, catching a seat reviewing its own spec,
  catching unmade relays).
- **The disk and document discipline** that keeps 32 GB and 912 loose files from happening again.

Design for his actual behaviour, not an idealised operator: he will not run labeling sessions, will
not open documents, gives measurements and timestamps as **guides not gates** (*"It's just a guide
dude why do u take everything I saw so literally"*), checks in at random hours, and expects the
program to keep moving without him.

Say plainly what the new model **costs** — quota, wall-clock, and what capability is given up. A
design that claims to cost nothing will be treated as unexamined.

## Deliverable

One design document written to
`docs/plans/active/spectral_program_operating_model_v1_2026_08_02.md`, plus — as your returned text
— a version Brandon can read in chat without opening anything.

Both must be in plain conversational English. No jargon (the repo bans "blast radius",
"load-bearing", "seams" by name), no status blocks, no tables of process ceremony. Explain the
mechanism and why it works; do not dumb it out to nothing. Lead with what changes and what it buys.

Structure it as: what the program is trying to do → what is wrong with how it is run now → the new
operating model → what each failure mode from §8 now runs into → what it costs → what you are
unsure about. The last section is required and will be read.

Label load-bearing claims **confirmed / assumed / unknown**, tied to what you actually read. Do not
assert anything about current program state you have not opened.

## Boundaries

Read-only on the repo and the memory store, plus shell for inspection (`ls`, `du`, `rg`, `git log`).
Write exactly one file, the design document named above. No implementation, no edits to bridge code
or config, no runtime or hardware interaction, no git commits, no branches, no touching anything
under `local/` except reading, no killing or dispatching tmux seats, no changes to the memory store.

You may fan out read-only subagents for evidence gathering; **pin every one of them to Opus** and
say in your output what you delegated. Do not spawn Fable-tier subagents.

Do not re-litigate the goal, the acceptance gate, or any ruling recorded as operator law in the
dossier or the memory store. If you believe one of those is itself the problem, say so once, in the
"unsure about" section, and design to it anyway.

## What success looks like

The design is successful if an independent hostile reviewer, told to destroy it, cannot find a
failure mode from dossier §8 that the new model would let happen again unnoticed — and cannot
credibly claim that the model is the old one with new vocabulary.

It fails if: it answers any §8 failure mode with a rule, a law, a document, or a checklist; it adds
review rounds without changing what reviews check; it requires Brandon to remember, chase, or
supervise anything; it cannot state its own cost; or it moves the goalposts of the acceptance gate.
