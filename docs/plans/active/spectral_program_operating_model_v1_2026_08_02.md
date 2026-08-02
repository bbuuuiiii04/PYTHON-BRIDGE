# Spectral program operating model v1 (2026-08-02)

**Status:** design proposal — `planned`, not adopted, nothing implemented. Written by a Fable 5
session against the verified failure dossier
(`docs/plans/active/spectral_program_failure_dossier_2026_08_02.md`), the current org docs
(`docs/agents/multi_agent_org_workflow.md`, `docs/agents/opus_seat_harness.md`), the program state
file (`local/spectral_v5_2026_07_17/PROGRAM_STATE_2026_07_31.md`, read in full), and the ten
operator-law memory files the brief names (all read in full). Claim labels used throughout:
**confirmed** = I read or measured it this session; **assumed** = my estimate or judgment;
**unknown** = nobody has measured it.

The goal does not change. The acceptance gate does not change. Everything about how the program is
run does.

---

## 1. What the program is trying to do

Produce, for any track Brandon picks, one list: laser moments (where AND how long — the lasers
ride the moment), track energy, drop energy, and accented moments, with timestamps. The list
passes when his ear says it passes, cold, on tracks he chooses — including I Cannot, Palm of My
Hands, and every track he has marked. The machine must locate sounds, not rank them, and it must
work across his whole 700–800 track library, not just the examples. His greenlight on that list is
what authorizes live wiring; everything else is downstream. [confirmed — acceptance gate memory +
dossier §3]

## 2. What is wrong with how it is run now

The short version: the program's work product became paper about the program, and the paper was
graded by more paper.

Measured this session (2026-08-02, my own commands, not any seat's report): `local/` is 32 GB and
87,009 files; the program directory is 28 GB; its root holds 411 loose files today (194 of them
.md) with three `archive_*` directories holding more — the dossier measured 1,483 loose / 912 .md
before that archiving, roughly 100 documents per day at peak. The program's own memory file is
483,576 bytes and cannot be loaded whole by the tool meant to read it. [confirmed]

Against that machinery, the one number that matches the goal — his marked moments recognized
exactly, cold — went from 2 of 34 to 2 of 34 over the whole month. [confirmed — dossier §1, the
exec seat's own admission]

The dossier's nine failure modes (§8) share one root: **nothing in the program's daily loop ever
touched his ear or his recorded judgements.** Specs were reviewed against specs. Gates checked
whether work was internally consistent, never whether it was what he asked for. The scoreboard
that steered decisions (ranking his moment against other candidates in the same track) was
invented internally because it was easy to compute — he never asked for it, and it counted real
finds as failures. His 54-record judgement corpus was consulted six times; his sound descriptions
were never written to disk at all. And every remedy was a new rule written into a new document —
which he has correctly observed does nothing, because rules live in documents and sessions boot
without them. [confirmed — dossier §2, §5, §6, §7]

The current model already tried to fix itself twice from inside: the steering charter compressed
the law pile to eight inviolables and added a proxy seat; the six-clause addition added a retry
budget and a coverage probe. Both are better rules — but they are still rules, held in prose, and
the 2:24-in-a-buildup row shipped anyway nine days after "lasers only on drops" became law.
[confirmed — dossier §4, §7; PROGRAM_STATE §2–3]

## 3. The new operating model

The idea in one sentence: **move his words out of prose and into data, move the laws out of
documents and into the one code path every output flows through, and make the only measure of
progress a number computed by comparing the machine's list to his recorded judgements — so a
session with zero memory of the program still cannot ship a violation, and a week of non-progress
is visible as a flat number, not discoverable three weeks later in a transcript.**

Five pieces.

### 3.1 The answer file — his evidence as data, one door in

One structured file (rows, not prose — e.g. JSON lines): every judgement he has ever given. Each
row: track, timestamp, length, his exact words, the kind of statement (mark / veto / description /
ruling), the date, and the transcript or file line it came from. His 54-record corpus, the Lowkey
key, his Gemini sound descriptions, his definitions of growl and sustain, the blind-test verdicts,
the Losing It and Palm timestamps — all of it, one place, machine-readable.

Why this is structural and not another document: **the scorer (3.3) reads this file and nothing
else as ground truth.** Evidence that is in the file cannot be ignored, because the scorer
consumes every row mechanically on every run. Evidence that is missing is visible, because every
surface he sees prints the row count and the date of the last-added row at the top — a lost week
of his words shows up as a stale date in the very message he is reading. His question "are my
sound descriptions being taken into account" stops being a trust question and becomes a lookup.

The exam keys (Lowkey, I Cannot, Palm of My Hands, the fresh blind track — the held-out set
already fixed in `DEVSPLIT_2026_08_01.md` [confirmed, file exists]) live in a **separate file**
that the building seat never opens. Key hygiene stops being a rule a seat must remember and
becomes a property of which file a seat is pointed at.

New evidence enters through one door: whichever session hears him say something appends a row with
its cite in the same turn. I cannot make writing the row automatic — that part stays human
(section 6). What is structural is that omission is visible within hours, not weeks, because the
row count and last-entry date ride on every scoreboard he sees.

The file stays small by nature — it is bounded by what one person actually says. It does not
become the next 483 KB memory file because it is data a script reads, never prose a session loads.

### 3.2 One command against a track

`listen <track>` prints the per-track list — laser moments with start and length, track energy,
drop energy, accented moments — in the exact format he already accepted, in minutes, from cached
analysis. `score` runs `listen` over every track in the answer file and prints the scoreboard.
That is the whole machine.

He asked for exactly this, twice, in plain words: *"why did u have to build a whole thing just to
run it. why cant u just run it against the track"* and *"why can't u just compare my description
and timestamp windows of the growl and see if the models get it right? it's not that hard."*
[confirmed — dossier §9]

Why this is structural: a capability that is not reachable through `listen` **does not exist** —
no spec chain can be "READY" while the command errors, which closes the built-on-nothing failure
(§8.9). Blind tests need zero setup: he names a track, the front desk runs one command, the list
lands in chat, his clock stops. And the check that killed the 07-25 package — scoring his known
moments against the machine's own output — was run once, manually, during the blind test; here it
IS the daily loop, run on every build automatically.

### 3.3 The scoreboard — computed, never written

One frozen scoring script compares `listen`'s output to the answer file's rows and prints, per
track and in total: **found exactly (his tenth, his length) / found but off (with the actual
difference shown) / missed / invented (phantoms).** The headline is one sentence he can check
himself by playing any track: *"Of the N moments you've marked, run cold, the list has X exactly,
Y within a beat, misses Z, and invents W extra."*

Rules that make it un-fakeable:

- The scoreboard is **generated**. Nobody writes progress prose. Every run appends one history row
  (date, code fingerprint, the numbers), so the number's movement — or its flatness — is a public
  fact with a date on it.
- **Nobody may invent a measurement.** The only measurement in the program is agreement with his
  rows. Internal diagnostics are fine for debugging but may never appear on the scoreboard or in
  his chat. Ranking anything is impossible here by construction — there is nothing in the schema
  to rank, only his row and the machine's row and the difference.
- **No invented pass/fail thresholds.** The scoreboard reports differences (machine 3:10.2, his
  mark 3:10.0, −0.2 s), not verdicts against a tolerance nobody authorized. His marks stay guides;
  exactness stays the goal (the final bar is his tenths); he stays the only judge of "close
  enough." This is how "It's just a guide dude" and "I need PRECISE timestamps" coexist without a
  seat choosing between them.
- Machinery does not move the number. Producing specs, reviews, probes, or documents changes
  nothing on the scoreboard, which is the point: the failure mode where the org's output was the
  org (§8.2) starves, because there is no surface left on which process can register as progress.
- Held-out runs are a separate command that **writes its own exposure-ledger row before printing
  results and refuses a fourth graded attempt per track in code** — his existing retry-budget law
  (six-clause ruling, clause 1) becomes tool behavior instead of prose. [confirmed the law —
  PROGRAM_STATE §2 ruling 47]

### 3.4 His laws, compiled into the output path

Every output the program can show him flows through one printer, and the printer enforces his
standing rulings as code, not as memory:

- A laser row whose timestamp sits in a buildup **cannot be printed** — the row schema requires a
  detected true-drop anchor, and the bridge already computes sections and buildup runways
  (`smart_phrasing.py:714 runway_beats`, `_RUNWAY_LABELS` at `:20` — confirmed at HEAD this
  session). The 2:24 row that violated a 9-day-old law would have been rejected by the printer,
  not caught by his eyes.
- A moment row **without a length cannot exist** — length is a required field, because "how long
  is literally AS important as where." [confirmed — acceptance-gate memory]
- Timestamps print as m:ss.t from the sealed grid; model attribution stays on every claim row;
  fragmented seconds-apart duplicates merge into passages — each of his form rulings from 07-31
  becomes a rendering test that must pass before anything prints.
- **Every past correction becomes a permanent test case.** When he corrects something, the fix is
  a change to the printer or scorer plus a test that pins the corrected behavior. This is the
  structural answer to over-rotation (§8.4): a cure that breaks an earlier ruling fails that
  earlier ruling's test the moment it is written, in the same hour, at the desk of whoever wrote
  it — instead of on his screen days later. And it is the structural answer to fresh-session
  amnesia (§8.5): a session that has never heard of "lasers only on drops" still cannot ship a
  buildup laser, because the session runs the same printer everyone runs.

Honest limit: rulings about **meaning and frame** (was this rendered as hearing-evidence when he
asked for the laser list? is this explanation jargon?) do not compile to checks. Those still need
a person (section 6).

### 3.5 Three seats, three files

- **Worker** (Opus, per the routing law: build tier is Opus) — changes the analysis code, runs
  `score`, iterates. Decides alone: anything reversible inside the program directory. Never talks
  to Brandon, never opens the exam-key file, never touches bridge runtime code or config (that
  stays Codex's per the standing roles).
- **Checker** (fresh-context Opus, never the author) — re-runs `score` at its own desk from the
  sealed bytes before any number is believed (the reproduce-before-believe inviolable, now a
  10-minute mechanical act instead of a review round), reads code diffs to the scorer/printer
  (small surface — this is the one place review still exists), and **cold-reads every list bound
  for Brandon exactly as he would see it** — the read-through gate kept, because it caught real
  garbage and cannot be automated.
- **Front desk** (Fable, the hardest-judgment seat) — the only voice in his chat. Keeps the answer
  file, holds the exam keys, runs blind tests when he asks, posts the scoreboard sentence and the
  lists, appends his new words to the answer file same-turn. Escalation rule: anything touching
  his surface, his evidence, bridge code, or money goes through this seat; nothing ever queues on
  him — open questions become recorded rows, and work continues.

Program state is **three files at fixed paths**: the answer file, the scoreboard (with its
history), and a short append-only journal (one line when an approach starts — naming which
scoreboard cells it aims to move and its budget — and one line when it ends). A fresh seat boots
by reading three files totaling a few hundred lines, not an 1,142-line state file plus a 6,444-line
memory log. Handoffs stop being a program-threatening event because there is almost nothing to
lose.

Everything else the current org maintains — spec version chains, review-round records,
adjudication batches, organizer state files, the proxy seat, the auditor seat, heartbeat
re-pokers — **is abolished, because the artifacts they existed to manage no longer exist.** This
is the difference between cutting seats (a rule someone can quietly break by spawning more) and
removing the work that made the seats necessary. New prose documents have no role in the loop;
`score` prints a warning when the program root grows beyond the fixed file set, so regression
toward paper is visible on the surface everyone reads. Run outputs land in dated subdirectories,
never loose in the root.

### How work gets killed

Every approach starts with one journal line: the scoreboard cells it intends to move and its
budget in runs or days (worker sets it; front desk can veto). When the budget is spent and the
history rows show the number flat, the approach is dead — the closing journal line records it, and
the flat history rows are the evidence. Nobody has to decide to kill it against sunk-cost
pressure; the dated history already did. Nothing in the old program was ever stopped for failing
to move the number because the number was never the referee; now it is the only referee there is.

### What reaches him, and when

- A short chat message when something real changes: the number moved, an approach died, a blind
  test is ready. The scoreboard sentence, current, whenever he checks in at any hour.
- Lists always rendered in the accepted format, pasted in chat, never "see the doc."
- Blind tests only when he initiates or accepts a veto-only offer; no labeling sessions, ever —
  the answer file grows only from what he volunteers.
- During active work the front desk never lets hours pass silently (the never-go-quiet standing
  rule) — but updates are one or two sentences, not walls.

## 4. What each dossier §8 failure mode now runs into

1. **Confident output that dies on his ear.** Nothing reaches him that `score` has not already
   graded against every recorded judgement — the Losing It miss (in his corpus, ignored) would
   have been a red cell on the scoreboard before shipping, not a discovery during a blind test.
   The checker cold-reads the exact artifact he will see. Certifying runtime from logs is out of
   scope here entirely (this program ships lists, not runtime), and his observation still outranks
   everything by standing law.
2. **Rigor on the wrong object.** There is no other object. Specs, review chains, and process
   records no longer exist to absorb effort; effort that does not change `listen`'s output cannot
   move the scoreboard, and a flat scoreboard with a spent budget kills the approach on a date.
3. **His evidence unread or lost.** The scorer consumes every answer-file row every run —
   "used six of 54" becomes mechanically impossible for anything in the file. What is not yet in
   the file is visible as a stale last-entry date on every surface. Handoffs cannot lose evidence
   because evidence lives in the file, not in any session's context.
4. **Over-rotation on corrections.** Each correction lands as one schema/printer change plus a
   pinned test; every earlier ruling's test still has to pass, so a cure that breaks a prior rule
   fails at the author's desk the same hour. The v1→v9-plus-fourteen-addenda oscillation cannot
   recur as document churn because there are no addenda — there is one printer and its tests.
5. **Settled laws re-broken by fresh sessions.** The laws that compile (drop anchoring, mandatory
   length, timestamp format, passage merging, models visible) live in the one code path every
   output crosses; a session with zero memory inherits them by running the code. The laws that do
   not compile are named honestly in section 6.
6. **Communication violations.** The deliverable surfaces are generated from the accepted formats,
   so glyph walls and jargon cannot appear in a list. Free chat is one seat (Fable, the strongest
   judgment available) with the smallest possible reporting job: a sentence and a list. Partly
   structural, partly still behavior — section 6.
7. **Delegated output consumed without verification.** Every number that reaches anyone comes from
   the frozen scorer, re-runnable by the checker in minutes from sealed bytes. A claim without a
   scoreboard row behind it has nowhere to stand. Subagent fan-out shrinks to almost nothing
   because the org is three seats with narrow jobs.
8. **Seat/process mismanagement.** Three seats instead of ~10-20 sessions; boot cost is minutes,
   so a botched handoff or dead seat costs minutes; watchers watch one lane; there is no exec to
   re-poke, so the heartbeat that annoyed him is gone. Tweak-never-purge and resume-not-respawn
   remain behavioral rules — but the damage a violation can do is now capped by how little state a
   seat holds.
9. **Building on deliverables that never arrived.** If `listen` does not run, nothing exists —
   capability claims are one command from falsification, and the scoreboard header pins the exact
   code fingerprint it measured.

## 5. What it costs

- **Build cost** [assumed]: migrating his evidence into the answer file — every record, key,
  description, and ruling row, each verified at its transcript cite by the checker — is the
  riskiest single step; estimate one to two seat-days plus a verification pass. Wiring the
  existing compute (sealed embeddings, the probe-ladder start rule, the section data) into
  `listen`/`score`/printer with the compiled-law tests: a few seat-days of Opus work. These are
  estimates, not measurements.
- **Quota** [assumed]: materially lower steady-state burn — three seats replace the current
  roster, and the document-review economy (eight hostile rounds on one spec, reviews of reviews)
  disappears. The checker's re-runs are compute-cheap because embeddings are cached.
- **Wall-clock** [assumed]: a `score` pass over the ~30–50 corpus tracks in minutes from cache;
  whole-library runs stay hours and stay operator-authorized, as now.
- **Capability given up, honestly:**
  - *Layered hostile document review.* The old chain caught real defects — key leaks into
    computing seats, a count leaked into a work order, an audit run on the wrong bytes. The
    replacements are narrower: file-level key separation, the checker's re-run-from-sealed-bytes,
    and his blind tests as the unfakeable outer check. Some defect classes those eight-round
    reviews would have caught will now be caught later or not at all. I judge the trade worth it —
    seven rounds also passed the package whose own spec said it measured the wrong thing — but it
    is a real trade, not a free upgrade.
  - *Parallel breadth.* One or two approaches at a time instead of a probe ladder of eleven in a
    night. Slower exploration, deliberately: shelved-same-hour breadth was a disease symptom.
  - *Forensic narrative.* The adjudication trail and organizer record die. If something goes
    wrong, the record is git history plus a thin journal. Less to reconstruct from; also far less
    to drown in.
- **What it does not buy:** the unsolved hearing problems — the end rule, phantom discrimination,
  requirement zero — stay unsolved. This model makes non-progress visible in a day and violations
  unprintable; it does not make the science succeed. Anyone who claims an operating model alone
  will move 2-of-34 is selling something.

## 6. Where nothing structural exists — a human still has to remember

Saying this plainly, as the brief requires:

- **Getting his words into the answer file.** A session must append the row. Structure makes
  omission *visible fast* (row count + last-entry date on every surface) but cannot make capture
  automatic. This is the front desk's first duty and the checker spot-checks it — but it is a
  duty, not a mechanism.
- **Frame and meaning.** Whether a surface answers the question he actually asked, whether an
  explanation is plain, whether a correction was understood as principle rather than example —
  no check catches these. The design narrows the exposure to one seat on the strongest model with
  the smallest reporting job, and keeps the checker's cold-read. That is containment, not
  prevention.
- **Free-chat conduct** (jargon, walls, answering around the question). Same containment, same
  honesty: one seat, small job, no structure that can force good prose.

## 7. What I am unsure about

- **Whether the compiled laws can keep pace with his rulings.** Most of the 07-31 form rulings
  compile cleanly to schema and rendering tests; some future ruling may not, and a seat may be
  tempted to fake it with a bad proxy check. The rule of thumb I would hold: if a ruling does not
  compile, it goes in the answer file as a row and in the checker's cold-read notes — never into a
  half-check that gives false comfort. [assumed]
- **Migration fidelity.** If the answer file is seeded wrong — a mis-transcribed tenth, a dropped
  record — the whole program calibrates against a corrupted ear. Row-by-row verification at cites
  is the mitigation; the residual risk is real. [unknown until done]
- **The guides-versus-gates line.** I resolved it as "report differences, never verdicts; he is
  the only judge." He may instead want the machine to commit to close-enough calls so he can veto
  them. Ship the differences version first; one veto from him settles it. [assumed]
- **Whether three seats are enough throughput** for the remaining science. If the worker stalls,
  the model allows a second worker on a non-conflicting approach — but I have deliberately not
  designed a re-growth path beyond that, because org growth is how the last model died. If this
  model fails, it should fail visibly small rather than succeed at becoming large. [assumed]
- **Requirement zero** (point-and-recognize any sound he names, anywhere) may be an open research
  problem that no operating model can schedule into existence. Under this model it is an approach
  row with a budget like everything else, which means it can die by flat-number like everything
  else — and then it needs his word, because it is half of a ruling. [unknown]
- **One tension I am required to flag once:** the autonomy order ("my input is not required for
  anything") and the acceptance gate ("his ear is the only judge") pull against each other — the
  only measurement that finally matters is periodically unavailable by design. The answer file is
  the stand-in for his ear between contacts, and a stand-in can drift from the real thing. The
  design lives with this: dev-set numbers steer, his blind tests correct the steering, and no
  internal number is ever called a pass. But the gap is real and permanent, and it is where I
  would attack this design if I were the reviewer.

## 8. Adoption order (so this is not another document)

1. Operator reads the chat version; vetoes or amends.
2. Seed the answer file (worker builds, checker verifies every row at its cite). Nothing else
   starts until this is done — everything downstream calibrates against it.
3. Build `listen` + `score` + the printer with the compiled-law tests, wiring in the already-built
   compute. First scoreboard run establishes the baseline number publicly.
4. Retire the old org: running seats wind down at their next natural stop; the state files are
   archived, not deleted; the program memory file shrinks to a pointer at the three fixed paths.
5. From then on the loop is: change code → `score` → number moves or budget burns → short message
   to Brandon when something real happens → his blind tests whenever he feels like calling one.
