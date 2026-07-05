---
doc_status: current
truth_level: evidence-grounded design analysis
last_verified_date: 2026-07-04
validation_scope: AI-workflow design analysis only; transcript/memory evidence verified as individually labeled; no bridge behavior, runtime action, code change, or hardware validation
---

# Self-Learning Workflow — Design Analysis & Challenge

**Task:** design and adversarially challenge a system that turns past AI-agent mistakes into durable
workflow improvements, without depending on Brandon to notice and hand-correct each failure.
**Authored 2026-07-04 as analysis only. Operator approved the build the same day ("go ahead and
build it"); Phase 1 was built and its first-run digest applied 2026-07-04 — current state lives in
§3's checklists and the AWR-127 registry row.**

---

## Verdict: BUILD SMALLER

A full self-learning system — scheduled transcript mining, automatic rule writing, autonomous
maintenance — is not justified by the evidence. Measured correction volume is roughly one to two
real corrections per day of heavy use; keyword-based mining is unusable (75–90% false positives,
measured on this exact corpus); and an autonomous rule-writer would multiply the workflow's actual
worst debt, which is wrong or stale lessons silently mis-teaching future sessions. Eleven of the
61 bridge memory files (and both home-store files) already carry "this was corrected later"
markers, and I found three live
contradictions in the store today — including one where the written lesson for a twice-repeated
mistake now points at a script path that no longer exists.

But doing nothing also has evidenced costs. The same scope mistake happened twice in one evening
before its lesson was captured. A launch-method mistake recurred across at least 26 days before it
became a rule. Stale memories currently get fixed only when a session happens to collide with them.

The right-sized build is a **retrospective skill Brandon invokes every few weeks** — read-only
subagents sweep the transcripts written since the last run, verify each candidate correction against
the actual session text, cross-check it against the rules that already exist, and produce one short
approval digest (at most ~5 proposals) of memory/rule additions, edits, merges, and deletions —
plus **one or two deterministic guard hooks** for the mechanically-checkable repeat offenders.
No cron by default, no auto-apply ever, no machine-learning classifier, no new lesson store.

### Plain-language summary

I swept all 260 Claude sessions from the last month (about 420 MB of transcripts across the bridge
project and the home directory), audited all 63 memory files, and verified the important citations
by hand. Agents really do repeat mistakes, and Brandon really is the only detector — but the numbers
matter: about 43 genuine corrections happened in a month, and most of them were violations of rules
that *already existed*, not missing lessons. So a system that only writes *more* lessons attacks the
smaller half of the problem. The bigger half is that the lesson base itself is getting stale and
bloated, which makes agents comply worse. The design that survives adversarial challenge is a
periodic, Brandon-triggered "retrospective" that batches the noticing work he currently does one
interruption at a time into one short review every few weeks — and that treats *deleting and
consolidating* lessons as equal in value to adding them. Everything the retrospective proposes shows
its transcript evidence, and nothing is applied without Brandon's approval. Two narrow hooks handle
the two mistakes that a five-line mechanical check can prevent outright.

---

## 1. Evidence base

### 1.1 What was swept, and how much to trust it

| Source | Volume | Method |
|---|---|---|
| Bridge-project transcripts (`~/.claude/projects/-Users-bbui-rb-ss-bridge-v2/*.jsonl`) | 81 sessions, ~138 MB, 2026-06-07 → 2026-07-04 | read-only subagent sweep; 378 genuine human messages isolated; 19 confirmed corrections |
| Home-dir transcripts (`~/.claude/projects/-Users-bbui/*.jsonl`) | 179 sessions, ~281 MB, 2026-06-04 → 2026-07-02 | read-only subagent sweep; 1,128 genuine human messages; ~24 confirmed corrections |
| Bridge memory store | 61 files + `MEMORY.md` | read in full by a subagent; key files re-read by me |
| Home memory store | 2 files + `MEMORY.md` | read directly |
| Global rules, settings, hooks | `~/.claude/CLAUDE.md`, `~/.claude/settings.json` | read directly |
| Repo prior art | `docs/agents/lessons/`, `docs/status/active_work_registry.md` | read directly |

Claim discipline used throughout: **[confirmed]** = I read the exact file/line myself, or the quote
was re-verified at its cited line after a subagent reported it. **[assumed]** = subagent-reported
with plausible corroboration, not independently re-traced. **[unknown]** = stated as such.

I personally re-verified, at their exact cited lines: the two 2026-07-04 scope failures, the
2026-07-04 "why so many mistakes" exchange, both launch-method corrections (2026-06-04 and
2026-06-30), and the three memory-store contradictions. All matched the subagent reports verbatim.

### 1.2 The failure classes, with instances

Counts are confirmed corrections across both corpora (bridge + home), June 2026 → July 4 2026.
Quotes are Brandon's own words, ≤25 words each.

**Overconfident-wrong — ~13–15 instances, the largest class.** [confirmed]
An agent asserts a claim confidently; evidence or Brandon falsifies it.
- 2026-07-04, `d4c62914…jsonl:1723` and onward: a six-report cascade in one session — palette
  override not taking effect, queue regression, missing indicators — after the agent had described
  the feature as working. Same feature area again that night in `6c513794…jsonl:908`: "none of the
  buttons do anything. killing led/laser/laser solo doesnt work." (The same-night hardening response
  is already tracked under AWR-119; the fixes take effect at next bridge start.)
- 2026-07-01, `97fee54c…jsonl:446` (home corpus): agent called a CH11 strobe toggle-count mismatch
  (7 vs 10) "basically identical"; Brandon: "this is not basically identical. Why are you settling
  for less?" [confirmed by subagent read; consistent with the later 2026-07-02 parity root-cause work]
- The reverse-engineering record shows the same shape repeatedly: the 32-beat-grid anchor shipped
  from a Ghidra implication and disproven the same day by live capture; the "double off-by-one"
  model that was two cancelling errors (`project_native_autoloop_review.md`,
  `project_ss_double_off_by_one.md`). [confirmed from memory files]

**Scope-decay — ~9 instances.** [confirmed]
The agent delivers less than the asked-or-answered scope, or stops early.
- 2026-07-04 22:18, `7264ea4c…jsonl:196`: "you did not creatively expand on it. All you did was
  review." [confirmed at line]
- 2026-07-04 23:32, `a138c344…jsonl:225`: "You were supposed to work with me on how i want the
  template lab to function." [confirmed at line]
- 2026-07-04 23:54, `3a4e2603…jsonl:42`: Brandon reports the answered-scope failure ("i told it all
  3, and then it only generated a spec doc for round 1"). The lesson file
  `feedback_answered_scope_is_the_scope.md` was written in that session — i.e., **after the second
  same-evening occurrence**. [confirmed at line]

**Stale-asserted — ~6 instances.** [confirmed]
Old plans/memories asserted as current truth.
- 2026-07-04, `5037310b…jsonl:45`: "this design document is outdated. We now have a soundswitch
  exporter / bridge lighting pack that outputs dmx itself."
- 2026-06-30, `1b60233b…jsonl:93` (home): agent proposed a superseded milestone (T7d) as the live
  goal; Brandon: "T7D is superceded."
- 2026-06-10, `80f856c9…jsonl:57` (home): "that memory is stale."

**Context-loss — ~5 instances.** [confirmed]
Established facts forgotten within or across sessions.
- 2026-06-20, `6d2a22d4…jsonl:1012`: "ch8 is color/color effects and ch9 is color speed. this was
  all communicated before."
- 2026-07-04, `386b0f8e…jsonl:184`: third attempt at conveying the same phase-boundary instruction
  in one short exchange.

**Process-violation — ~4 instances.** [confirmed]
Standing operating rules broken.
- 2026-06-21, `af6d647c…jsonl:416`: Claude was mid-`Write` of `laser_output_backend.py` when Brandon
  interrupted: "You are supposed to orchestrate, not implement" — the Claude/Codex role split,
  violated while it was a standing expectation.
- 2026-06-04 → 2026-06-30, the launch-method pair (details in 1.3).
- (Historical maximum: the Gemini `git clean -fd` data-loss event, 2026-06-20 — already memorialized
  and defended by a standing ban.)

### 1.3 Structural findings that drive the design

**Finding 1 — Repeats-before-capture are real, but small in number.** [confirmed]
Two clean documented cases: (a) the scope failure recurred at 22:18 and 23:32 the same evening
before its lesson was written at ~23:54; (b) the launch-method mistake at `d8a3de20…jsonl:260`
(2026-06-04, "why cant i just launch it through the menubar like normal") recurred at
`8f31e462…jsonl:612` (2026-06-30, "why do you keep launching the bridge without the menu bar
script?") — "keep" implying more occurrences in between. Capture latency costs Brandon roughly one
to two extra correction loops per lesson. That is the true, bounded value of faster/automated
capture.

**Finding 2 — Compliance, not capture, is the binding constraint.** [confirmed]
Many corrections are violations of rules that already existed: the role split (2026-06-21), the
menubar rule's second occurrence, and the answered-scope failure — which happened with the full
current rule stack (global CLAUDE.md, AGENTS.md, skills, memory index) loaded in context. The
home-corpus miner independently observed that the genuine corrections "cluster around exactly the
standing rules and memories this project already tracks." **A learner that only adds rules attacks
the smaller problem and can worsen the bigger one**, because every added line taxes the attention
agents give to the rest.

**Finding 3 — Staleness debt is the store's live disease, and today it is only cured by collision.**
[confirmed] 11 of 61 bridge memory files — plus both home-store files — carry explicit
later-correction markers (falsified hypotheses, retracted findings, "prior HIGH rejected").
Three contradictions are live right now:
1. `project_bridge_v2.md:12` and `feedback_bridge_launch_via_menubar_only.md:10` both point at
   `/Users/bbui/ss_bridge_watcher.sh` — deleted 2026-07-03 per `project_bridge_watcher_home_vs_repo.md`
   (canonical watcher is now `scripts/ss_bridge_watcher.sh`). The second file is the *lesson for the
   repeated launch mistake*: an agent obeying it today would run a nonexistent script. Verified by me.
2. `project_bridge_v2.md:32` lists `RBSS_SPECTRAL_ENABLE=1` as live; `project_bridge_watcher_home_vs_repo.md:29`
   says it was still undecided/off in the launcher env. Direct value conflict on a runtime flag. Verified by me.
3. `project_led_laser_color_design.md:77` says gesture v2 is "NOT YET IMPLEMENTED" while the git log
   and registry record the AWR-121 mirror landing. [assumed — subagent-reported, consistent with registry]
No memory has a structured status/expiry field; closed workstreams sit in the index at the same tier
as active ones. The harness does inject age-based staleness warnings on read (observed live this
session), but age is a weak proxy — the wrong watcher path is in a file whose *content* was
re-confirmed recently.

**Finding 4 — The manual loop works well when it fires.** [confirmed]
15 feedback memories exist, each traceable to a real correction. At least two lessons were promoted
into stronger enforcement tiers: the plan-review-gaps memory became the codex-spec skill's 9-point
checklist, and the repo grew its own `docs/agents/lessons/` store (AWR-115, seeded 2026-07-03,
7 evidence-cited lessons). Prevention demonstrably works when the lesson is loaded: the smart-drop
ceiling memory has successfully blocked re-attempts of six failed approaches. The pipeline
correction → memory → (sometimes) skill/checklist exists and functions; it is capture *trigger* and
lesson *maintenance* that are weak.

**Finding 5 — Automated mining is measurably hard; agent-run triage is measurably cheap.** [confirmed]
Both miners independently found keyword/regex sweeps produce 75–90% false positives on this corpus
(review-prompt boilerplate reuses "wrong/stale/incorrect"; task-notifications masquerade as user
messages; genuine hits open with unanticipated phrasing — one flagship correction opened "no." and
was invisible to a "no," pattern). A useful sweep needs an LLM judgment pass over each candidate
plus harness-noise exclusions. At current volume (~1,500 human messages/month) that triage cost a
few hundred thousand subagent tokens for a full month — cheap enough to run periodically, far too
noisy to run as a dumb always-on detector.

**Finding 6 — Passive process artifacts do not self-execute.** [confirmed]
Registry items AWR-004/005/006 have sat "not yet exercised despite qualifying feature PRs" since
creation. Any design whose steps rely on agents remembering to do them each session is dead on
arrival; triggers must be either Brandon-invoked or mechanical (hooks). The auto-sync Stop hook and
the vibeyard hook suite prove per-event mechanical hooks work here; the same hook history also shows
their cost (the Stop hook has swept half-finished agent work into pushed commits).

### 1.4 What this evidence cannot show

- **Mistakes Brandon never noticed** leave no correction text. Transcript mining can only ever learn
  from Brandon-labeled moments; the labels shrink exactly when the system succeeds. Catching
  *unnoticed* defects is the job of adversarial review of work products (already standard practice
  here), not retrospective mining. Any design claiming otherwise is overpromising. [confirmed by
  construction]
- **Codex-side sessions** are not in `~/.claude/projects/` — Codex mistakes appear only refracted
  through Brandon's corrections in Claude sessions and review docs. Coverage of the implementer's
  own failure patterns is partial. [unknown — no Codex transcript store was inspected]
- Subagent sidechains were excluded from mining; failures corrected agent-to-agent (orchestrator
  catching a subagent) are underrepresented. [assumed]

---

## 2. The design space

Five credible options, minimal → ambitious. Costs are stated for Brandon's actual economics: his
attention is the scarce resource; tokens are cheap but not free; standing infrastructure is a
liability he has explicitly rejected for this hobby setup (`feedback_solo_hobby_dial_back_safety.md`).

### Option A — Status quo plus hygiene edits (the null option)
Fix the three live contradictions, add a status field to memory frontmatter, archive closed
workstreams, write a one-paragraph placement rule (what goes in CLAUDE.md vs project memory vs repo
lessons vs a skill). No new process.
- **Catches:** the currently-known staleness debt, once.
- **Misses:** everything future — capture latency stays, staleness re-accumulates at the same rate,
  nobody ever looks for cross-session patterns.
- **Costs:** one short session; near-zero Brandon attention.
- **How it goes wrong:** it doesn't, but it also doesn't learn — it is a cleanup, not a system. The
  same debt audit would be true again in two months.

### Option B — Retrospective skill, Brandon-triggered (recommended core)
A global skill (e.g. `/retro`) encoding exactly the method used for this document: read-only
subagents sweep transcripts *since the last run's recorded high-water mark*; every candidate
correction is verified at its cited line; each verified correction is classified **novel-lesson**
(no rule existed → propose a memory), **compliance-failure** (rule existed → propose sharpening,
consolidation, or a mechanical guard — never a duplicate rule), or **already-captured** (drop);
plus a staleness pass that spot-checks the most load-bearing memories against current reality.
Output: **one digest, at most ~5 proposals**, each with its transcript/file citation, covering adds,
edits, merges, and *deletions* with equal standing. Brandon approves or rejects per item; the agent
applies approved items in the same session; the high-water mark is recorded (as a small memory file
per store — no new infrastructure class).
- **Catches:** capture gaps (Finding 1), staleness debt before collision (Finding 3), cross-session
  repeats, rule-base bloat (via consolidation proposals).
- **Misses:** real-time capture (a lesson still waits until the next retro if same-session capture
  failed); unnoticed mistakes (see 1.4 — out of scope by construction).
- **Costs:** per run, roughly this analysis's cost (a few hundred thousand subagent tokens + one
  high-tier session) at monthly cadence; Brandon's attention: one ~5-minute batched review per run,
  *replacing* interrupt-driven correction loops — a trade he has explicitly said he prefers
  (batched decisions, one-way handoffs, external structure).
- **How it goes wrong:** proposal fatigue if uncapped (hence the hard cap); miner false positives
  becoming lessons (hence mandatory line-level verification and Brandon's quote shown in the
  digest); the retro itself misjudging "compliance vs capture" (hence each proposal must name the
  pre-existing rule or state that none exists — checkable in the digest); nobody runs it (acceptable
  failure: an unused skill is inert text with zero standing cost — unlike cron or hooks, nothing
  rots or fires wrongly).

### Option C — Real-time capture nudges (heuristic hooks)
A UserPromptSubmit or Stop hook pattern-matches correction-shaped messages ("no", "I said", "again",
all-caps) and injects "this looks like a correction — capture the lesson before turn end."
- **Catches:** in-session capture misses, at the freshest moment.
- **Misses:** everything retrospective (staleness, clustering, consolidation).
- **Costs:** near-zero runtime tokens; one-time hook authoring (Codex).
- **How it goes wrong:** fatally, per Finding 5 — the measured 75–90% false-positive rate means the
  hook injects noise into most turns that contain the word "no", taxing exactly the context
  attention that compliance depends on. The same-session capture duty already exists as a CLAUDE.md
  rule and demonstrably fires (answered-scope was captured same-session). **Rejected.**

### Option D — Deterministic guard hooks for mechanically-checkable rules
Not a learning system — the *output* of learning, promoted to the strongest enforcement tier.
Candidates found in evidence:
1. **Raw-launch guard** [strong]: a PreToolUse hook (bridge project scope) that denies a Bash
   command matching a raw `python3 -m rb_ss_bridge_v2` launch and echoes the watcher-script rule.
   Kills a twice-repeated (Finding 1) mistake class permanently, deterministically, with zero
   false-positive surface beyond the exact pattern. ~5 lines. Codex implements.
2. **Role-split guard** [weak]: warn on Claude editing bridge `*.py`. **Recommended against:**
   operator-granted exceptions are now routine (Sonnet fallback lanes, the logging-overhaul
   Fable-implements exception), so the hook would fire wrongly during sanctioned work — a noise
   source, not a guard. The rule stays prose.
- **Catches:** 100% of its exact pattern, forever, at zero attention cost.
- **Misses:** anything fuzzy — scope-decay and overconfidence are judgment failures no regex can gate.
- **How it goes wrong:** over-extension. Each new guard is a standing behavior modifier that future
  sessions must live with (the auto-sync hook's history shows hooks have side effects). Guards
  should be added only from the retro's compliance-failure findings, one at a time, with evidence.

### Option E — Scheduled autonomous learner (the ambitious end)
A cron/scheduled agent periodically mines new transcripts, clusters failures, and writes/updates
memories and rules autonomously (auto-apply, possibly with an async report).
- **Catches:** in principle, everything Option B catches, without Brandon triggering it.
- **Misses:** the same things Option B misses — automation does not extend the ceiling, it only
  removes the trigger.
- **Costs:** recurring token burn on mostly-empty windows (~1–2 genuine corrections/day, most
  already captured same-session); new standing infrastructure to maintain, monitor, and debug — for
  an operator who has explicitly rejected ceremony and infrastructure for this project.
- **How it goes wrong:** three compounding ways. (1) **Wrong-lesson amplification:** with a measured
  false-positive-prone signal, an auto-writer will eventually write a wrong lesson; a wrong memory
  is worse than no memory because it teaches every future session with authority (the store's own
  history proves wrong lessons persist until collision — Finding 3). (2) **Audit displacement:**
  Brandon must now notice bad *rules* instead of bad *behaviors* — strictly harder, because rules
  act invisibly and diffusely. The "Brandon must notice" problem is not solved; it is moved up a
  level and made less observable. (3) **Silent death:** a scheduler that stops running is invisible
  precisely because its job was to be invisible (Finding 6's failure mode, automated). **Rejected
  in full form.** The only salvageable piece: *scheduling Option B's skill unchanged* (digest +
  approval, never auto-apply) if Brandon finds he never remembers to trigger it — held as a
  conditional Phase 3, not a default.

---

## 3. Recommendation

**Build Option B, plus Option D's single strong guard, folding Option A's cleanup into the first
retro run.** Claude designs and runs retros and authors the skill text (a prompt artifact, like the
existing prompt-writer skills); Codex implements the hook (code). Nothing is applied to any memory,
rule file, hook, or setting without Brandon approving the digest line that proposes it.

### Phase 1 — The retro skill + first-run backlog clear (smallest useful unit)

Deliverables:
- [x] A global skill file (`/retro`, live at `~/.claude/skills/retro/SKILL.md`, 2026-07-04)
      specifying: sweep scope (transcripts + memory stores since high-water mark), the measured
      mining recipe (harness-noise exclusions, short-message priority, LLM judgment pass, mandatory
      line-level verification of every citation), the three-way classification (novel-lesson /
      compliance-failure / already-captured), the staleness spot-check, the ≤5-proposal digest
      format with per-item citations and explicit DELETE/MERGE proposals, provenance labeling for
      anything mined, and the high-water-mark update.
- [x] First run executed (2026-07-04 — this document's evidence sweep WAS the first run's mining;
      the digest was the five items below). Applied: the three live contradictions from Finding 3
      (watcher path ×2 memory files, `RBSS_SPECTRAL_ENABLE` env-flag correction, AWR-121 status);
      the closed-workstream split in `MEMORY.md`; the lesson-placement rule added to
      `~/.claude/CLAUDE.md` (universal → CLAUDE.md; repo workflow → `docs/agents/lessons/`; project
      state → project memory; agent procedure → the matching skill).
- [x] Brandon approved the build ("go ahead and build it", 2026-07-04); recommended defaults
      adopted; all five digest items applied. High-water marks recorded in each store's
      `memory/retro_state.md`.

Completion marker: the second retro run (a few weeks later) can measure the first — did any lesson
captured in run 1 get violated again? That number is the system's honest effectiveness metric.

### Phase 2 — One deterministic guard (Codex)

- [x] Codex spec authored 2026-07-04: `docs/plans/active/retro_launch_guard_spec.md`. Scope changed
      from the original bridge-project registration to GLOBAL `~/.claude/settings.json` — both
      historical violations happened in home-directory sessions, outside bridge-repo hook scope.
      Exact-pattern deny + pointer to `scripts/ss_bridge_watcher.sh` with `RBSS_BRIDGE_MANUAL=1`;
      must not match the watcher script itself, `pgrep`/`ps` checks, or submodule runs. AWAITING
      CODEX implementation.
- [ ] Codex implements (script + tests + settings registration per the spec).
- [ ] Verified by attempting a raw launch in a fresh session and seeing the deny message.

Gate satisfied: Phase 1's first run applied the corrected watcher path before this spec was
authored, so the guard's deny message points at the repo script, not the deleted home-dir copy.

### Phase 3 — Conditional scheduling (default: not built)

Only if, after two manual cycles, Brandon finds retros valuable but never remembers to trigger them:
schedule the identical skill (monthly, digest + approval, never auto-apply) via a scheduled routine.
Explicit entry criteria: ≥6 weeks since last retro AND either Brandon requests it or a repeat-class
correction has occurred in the interval. If the criteria never fire, Phase 3 never exists.

### Division of labor (unchanged from standing rules)
Claude: skill authoring, retro execution, digest writing, memory/docs edits after approval.
Codex: any hook/script code. Brandon: digest approval, cadence, and the open decisions in §5.

---

## 4. Challenge — trying to kill the recommendation

**"Does this need to exist at all? Isn't stricter hygiene plus a few hooks sufficient?"**
Nearly — and that pressure reshaped the design. Hygiene-only (Option A) fixes today's known debt but
leaves staleness to re-accumulate with no scheduled discovery mechanism; the three live
contradictions were found *only because this analysis swept the store*, and one of them corrupts the
lesson for a known repeated mistake. Hooks-only (Option D) covers exactly one of the five failure
classes (mechanically-checkable process violations). What tips the balance to a retro process is
Finding 3's dynamics: wrong lessons currently persist until a session collides with them, and
collisions are exactly the expensive Brandon-interrupt events this mission is trying to remove. The
retro survives — but only as a *process Brandon invokes*, not a system that runs itself. If unused,
its cost is zero; that asymmetry is why it survives the YAGNI test where cron does not.

**"Can a system that learns from its own transcripts amplify wrong lessons?"**
Yes — this killed auto-apply outright, and it is not hypothetical: the stores already contain 13
later-corrected files, and the measured false-positive rate says an automated writer would add more.
Surviving mitigations, now hard requirements: lessons may only be mined from *Brandon-labeled*
moments (his correction text is the ground truth, quoted in the digest); every proposal carries its
transcript citation, verified at the line; mined lessons carry provenance labels; deletion proposals
have equal standing with additions. Residual risk — misreading Brandon's correction — is bounded by
him seeing his own quoted words at approval time.

**"Who audits the learner? Doesn't this just move 'Brandon must notice' up a level?"**
In the autonomous version, yes, and that is why it died (§2, Option E: audit displacement). In the
surviving version, Brandon audits a ≤5-item cited digest at a moment he chooses, instead of noticing
failures mid-flow at moments he doesn't. The noticing burden is not eliminated — it is *batched,
relocated, and evidence-assisted*, which is precisely the trade his own stated working preferences
ask for. Honest ceiling, stated in the doc and the skill: this system reduces the repeat cost of
*caught* mistakes and pays down lesson debt; it cannot catch mistakes nobody caught. Adversarial
review of work products remains the only defense there, and it already exists in this workflow.

**"Does the maintenance cost exceed the cost of the mistakes prevented, for a solo hobby operator?"**
For every autonomous variant: yes, and they were cut. For the surviving core: the standing cost is
one skill file (inert text) plus one ~5-line hook. Per-use cost is a few hundred thousand subagent
tokens and five minutes of Brandon's attention per month, against roughly 30–45 correction loops a
month, of which the retro plausibly prevents the repeat fraction (Finding 1: one to two loops per
lesson) and the staleness collisions (Finding 3: three live instances found in one month's
accumulation). Token cost is not the scarce resource; Brandon's interrupts are. The math holds only
because the standing infrastructure is ~zero — which is the design's central constraint, not an
accident.

**What the challenge changed, concretely:** killed auto-apply and cron-by-default (Option E) and
heuristic capture hooks (Option C); shrank "self-learning system" to "batched retrospective + one
guard"; added the hard digest cap, mandatory line-level citation verification, provenance labels,
compliance-vs-capture classification (so the retro sharpens or consolidates instead of duplicating
rules), deletions-as-first-class output, and the rule that guards are only ever promoted from retro
findings one at a time. The role-split warn-hook was cut after checking that sanctioned exceptions
would make it fire wrongly.

---

## 5. Verdict and open decisions

**BUILD SMALLER.** The evidence supports a periodic, Brandon-triggered retrospective skill with an
approval digest, one deterministic launch-guard hook, and a first-run cleanup of the memory store's
verified staleness debt — and it affirmatively rejects scheduled autonomous learning, auto-applied
lessons, and heuristic real-time correction detectors on measured false-positive rates,
wrong-lesson amplification risk, and standing-infrastructure cost that a solo hobby workflow cannot
justify. The first phase is one skill file and one retro run, shippable and evaluable on its own;
its success metric (lessons from run N violated again before run N+1) is checkable at run N+1.

> **2026-07-04 resolution:** Brandon approved the build ("go ahead and build it"). Recommended
> defaults adopted for 1, 2, 3, 4, 6, 7: on-demand cadence, cap 5, bridge-focus after the first
> run (the first run's sweep included the home-dir backlog — its ~24 corrections all matched
> already-captured lessons or dead workstreams, so no new memories were needed from it), launch
> guard now (spec authored, awaiting Codex), no role-split hook, chat-only digests, Claude applies
> memory/docs + Codex implements hooks. Decision 5 (frontmatter status field across ~61 files)
> DEFERRED — no mechanical consumer exists yet; the `MEMORY.md` closed-workstream split covers the
> at-a-glance need. The list below is preserved for the record.

### Decisions only Brandon can make

1. **Cadence:** on-demand only (my recommendation), or also calendar-scheduled from the start?
2. **Digest cap:** is ~5 proposals per run the right review load?
3. **Sweep scope:** first run includes the home-dir corpus backlog; subsequent runs bridge-only
   (recommendation) — or always both?
4. **Launch guard (Phase 2):** build now via Codex, or wait until it recurs once more?
5. **One-time store cleanup:** approve the mechanical pass adding a status field to memory
   frontmatter and splitting closed workstreams in `MEMORY.md` (touches ~61 files once, reviewed as
   one diff)?
6. **Digest persistence:** chat-only (recommendation — applied changes are the durable record), or
   a saved digest file per run?
7. **Confirmation of the role boundary:** retro applies approved *memory/docs* edits itself
   (Claude-side, as with all memory hygiene today); anything that is code — hooks, scripts — goes to
   Codex. Confirm this matches your intent.

### Side findings surfaced by the sweep (not design items — flagged for awareness)

- The 2026-07-04 23:44 report "killing led/laser/laser solo doesnt work" (`6c513794…jsonl:908`) is
  the incident behind the same-night AWR-119 deck-surface hardening; those fixes take effect at the
  next bridge/deck start and F-B2 (retry log spam) remains open. Worth a functional check at next
  start. [confirmed via registry + memory]
- Two memory files still direct agents to the deleted home-dir watcher path (Finding 3, item 1);
  until the first retro run applies the fix, any agent following
  `feedback_bridge_launch_via_menubar_only.md` verbatim will fail to launch the bridge. This is the
  single most urgent digest item. [confirmed]
