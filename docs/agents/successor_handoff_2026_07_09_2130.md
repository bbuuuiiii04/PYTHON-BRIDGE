---
doc_status: current
truth_level: handoff-brief
last_verified_date: 2026-07-09 (evening; FINAL-STATE section patched ~21:00, verify anything newer via git log)
validation_scope: >
  Executive-seat handoff brief written by superman4 (Claude Fable 5, the last Fable
  seat) for the successor executive seat (GPT 5.6 SOL ULTRA or any frontier CLI) at
  the operator's 21:30 hard deadline on 2026-07-09. Everything a successor needs is
  IN THE REPO — the Claude project-memory store does NOT load for non-Claude CLIs
  and nothing below depends on it.
---

# Successor executive handoff — 2026-07-09 21:30 (Fable → GPT 5.6 SOL ULTRA)

**You are the new EXECUTIVE seat, running in the codex harness. The operator
(Brandon) talks only to you.**

## ⛔ APPROVAL GATE (operator-ordered, absolute)

Complete the boot ladder below — read everything, verify everything, take stock —
then **STOP and post one plain-language readiness summary to the operator. Do NOT
dispatch lanes, edit files, touch the bridge, or resume ANY workstream until he
explicitly approves.** Verification reads (tmux capture, pgrep, git log, test
status) are allowed during boot; mutations are not.

## Codex-harness specifics (same org, codex agents)

- The whole workflow is unchanged (org doc §10 verified these mechanics on
  codex-cli 0.142.5): tmux seats, signal files, `dispatch_lane.sh SESSION MODEL
  EFFORT MSGFILE TAG codex` for worker lanes, review chain, named-baseline
  discipline.
- You read `AGENTS.md` natively; repo `.claude/skills/*/SKILL.md` files are plain
  docs — read them when a task's routing points there (spec authoring especially).
- Footgun-guard plugin (`rbss-agent-hooks@rbss`) is registered + trusted on this
  machine; until the Jul-11 pre_tool_use firing retest passes, AGENTS.md rules +
  your `approval_policy`/sandbox settings are the real enforcement — behave as if
  no hook will save you.
- The Claude memory store does not exist for you; THIS file + the resume doc +
  the registry are the state. If a doc and `git log` disagree, git wins.

## Boot ladder (do these in order, fully, before acting)

1. Read `AGENTS.md` end to end — §0 communication mode is non-negotiable (plain
   language, no status blocks, chat is his only surface, label claims
   confirmed/assumed/unknown, evidence class with every "done").
2. Read `docs/agents/multi_agent_org_workflow.md` — the org doctrine. §10 covers
   non-Claude CLI mechanics (tmux seats + signal files + dispatch/watch scripts are
   CLI-agnostic; only the Claude skill-autoload is Claude-specific).
3. Read `docs/agents/codex_resume_state_2026_07_09.md` — per-workstream state,
   standing operator rulings (DO NOT re-ask decided items), the named suite
   baseline, and the final-evening section (superman4's watch).
4. Read the FINAL-STATE section at the bottom of THIS file, then
   `docs/status/active_work_registry.md` + `git log --oneline -30` to catch
   anything newer than any doc.
5. Verify EVERY lane fresh against reality (`tmux list-sessions`; capture panes
   read-only BEFORE any send-keys; dim `\033[2m` prompt text = autosuggest ghost,
   not typed input). Never trust notes over reality.
6. Verify the bridge stack yourself: `pgrep -f 'rb_ss_bridge_v2$' | wc -l` must be
   1 (plus frame-engine child + watcher + streamdeck; see AGENTS.md §6 and
   `scripts/ss_bridge_watcher.sh` header). SoundSwitch won't autorotate without it.
7. Announce readiness to the operator in chat, one message, plain language — then
   HOLD at the approval gate above. He approves; only then do you take actions.
8. Note: superman4 killed every other tmux session at handoff (operator's order) —
   the lane map below describes what EXISTED and what their on-disk state briefs
   say; you re-create lanes as codex agents when work resumes, you do not look for
   live panes.

## Hard rules that bit people this very day (do not relearn them)

- Bounce procedure (operator-delegated to the executive THIS session): SIGTERM the
  bridge PID ONLY (group-kill takes the watcher down — 17:48 incident), relaunch
  `RBSS_BRIDGE_MANUAL=1 scripts/ss_bridge_watcher.sh`, verify 1 bridge + child +
  watcher + 0 log ERRORs. The session-recording toggle DIES at every restart —
  re-arm `toggle_record_session` with a NEW part-N path (the recorder opens mode
  "w": reusing a path TRUNCATES the prior dataset).
- Suite reconciliation is BY NAME against the named baseline (five env reds from
  repo root, +1 from parent dir — names in the resume doc). Load-flakes: isolate ×8
  before blaming a round. Config-tripwire reds after approved config changes get
  RE-PINNED as explicit literals, never left red.
- Commits by EXPLICIT PATHS only; auto-sync sweeps anything dirty into other
  lanes' commits (misattribution is normal — verify content at HEAD, note it,
  never rewrite pushed history). Never `git clean -fd`. Work on `main`, no
  branches without the operator's word.
- Nobody certifies their own work. Compressed chains are allowed under clock
  pressure but the gate evidence must be at YOUR desk (re-run tests yourself,
  read the diff yourself).
- Model/effort pins: launch flags for non-interactive CLIs; verify by eyeball.
  Top-tier model never below the manager seat.
- Operator-attended lanes (he types into them directly) are HANDS OFF without
  capture-first + his standing OK. Proactive /clear of idle lanes is BANNED.

## The seats as handed over (verify fresh — see boot ladder step 5)

- Attended (his): `labels` (track-label corpus, AWR-182 protocol: every ~10-track
  batch becomes a tuning round NOW, post-cutoff batches bank as ready specs),
  `stems`, `filter`, `haze`, `ledtune` (LED manager, parked with state),
  `usb` (Saturday readiness; stick pre-warm tool round tonight), `career` (his,
  never touch).
- Workers (parked with written state): `qaminors`, `legacy` (Jul-11 quota-gated
  retests), `f3design`, `specbank`, `p1impl`, `claude6`, `claude11`, `ledfix1-3`
  (Opus build lanes; ledfix3 ran tonight's AWR-184/185 rounds).
- Dispatch/watch: `tools/agents/dispatch_lane.sh` + `watch_lane.sh` + signal files
  under `/tmp/rbss_lane_signals/` (`<session>.<TAG>.done|.blocked`, consumed on
  read, ONE watcher per TAG).

## Undecided operator items (surface once at natural moments; never re-litigate)

- 17:48 bridge stop: reconstructed-probable as his menubar click — unconfirmed,
  one-line confirm still open.
- `rebuild_stick.sh` wrapper offer (usb lane): yes/no still open.
- D1-F1 phantom-load fix: OPERATOR-DEFERRED (his word stands; offered twice).
- Pre-drop tease: no verdict ever given.
- Full veto list + parked items: resume doc "Undecided operator items" row.

## FINAL-STATE (patched ~21:05, the last superman4 write — git log wins on divergence)

**Bridge: OFF, by the operator's own hand** ("MIX DONE, bridge OFF" ~20:15). Do NOT
start it — his menubar owns starts. **STAGED, loads automatically at next start:**
AWR-185 stop-precedence guard (gated PASS) + the filter lane's two-leg AWR-173
re-bloom fix (sequential release + fired-latch preservation on inert paths; 211
targeted green; its own full-suite proof was finishing at handoff with
flag-on-deviation promised — check the filter state brief). His ride-home CFX test
= first attended item next session.

**Suite board at handoff:** 3889 tests, 4F+1E — same signature as the by-name
reconcile earlier tonight (the named five environmental, repo-root run); every
round since verified green at file scope at the executive desk. patch_f equality
re-pin (1bdf18d) holds.

**Tonight's landed rounds (all executive-gated, software-tested only):** AWR-179
CLOSED PASS; AWR-183 verified (DMG 17:59, app adhoc-signed); AWR-184 rung LIVE
since the 19:05:52 bounce (operator ear-check pending); AWR-185 staged (see
above); AWR-175 F3 spec banked; AWR-165 Codex spec banked (39713f1 — note: it
swept the filter lane's led_dispatch_policy.py leg-1 diff, misattribution
recorded, content verified); AWR-182 labels corpus + blast-radius sweep (104
drops/80 tracks; both suspect classes CLEARED by operator ear ~21:05 — intro
firings benign because ANLZ intro drop MARKERS aren't real drops to his ear
(marker quality, not rule defect), and breakdown-tail bo16 is "fine, could even
warrant a 32-beat blackout" — a possible cap-raise taste datum, the rung currently
caps at 16. NO void-threshold round needed. The successor's first labels batch
instead: (1) first true tier misread — Scary Monsters (Levex) plans T3 WALL, his
ear says ~T1/bass-house (F2 tier-scorer evidence, AWR-163 territory); (2) REWIND
(Ray Volpe/Sullivan King) — he fixed a 2-beat rekordbox beatgrid misalignment
mid-review, orphaning its grid-keyed v4 entry; his ear-truth: "one of the most
aggressive tracks in my library, wall tier 3, 4 bar blackout" — check whether the
post-fix re-extraction alone recovers that read. Corpus entries committed by the
labels lane).

**Overnight compute running at handoff (nohup, survives everything):** P1 backfill
sweep PID 78394/78396, log `local/sweep_p1_20260709.log` (acceptance when done:
Sexy 3:38 separates from its 7 siblings; capochino 1:01.7; Girl$ 1:16.1/2:25.6 —
commands in the resume doc). **Stick pre-warm sweep: deliberately KILLED 5 min in**
— the operator is RENAMING the stick; a /Volumes/USB-keyed run would write 567
dead-path entries (the 4 it wrote were scrubbed; library cache untouched).
RE-FIRE after his rename, from the repo root:
`nohup caffeinate -i nice -n 10 python3 tools/spectral_stick_sweep.py "/Volumes/<NEW-NAME>" --jobs 2 > local/sweep_stick_20260709.log 2>&1 &`

**usb M2 program (operator directive, captured verbatim at
`docs/plans/active/usb_launcher_m2_operator_directive_2026_07_09.md`):** M2 spec =
spec-tonight-bank-for-Jul-11 (authoring at the 21:00 cut — check its registry row
for the honest-marker state); install.command/purge.command stick helpers approved
as the labeled Saturday interim (purge REQUIRES typed confirmation, only removes
installer-created paths); R5 (read stick inside the RX3 slot) re-answered
IMPOSSIBLE per the settled AWR-167 dual-confirmed verdict — do not re-open.
M2 spec must carry the secrets-on-stick security line; his default YES stands,
veto open.

**Open operator items at close:** M2 secrets veto; ride-home CFX test; AWR-184
Utopia ear-check (1:27 + 3:00 must read as blackouts); blast-radius verdicts;
D1-F1 phantom-load (still operator-DEFERRED); pre-drop tease (still no verdict);
17:48 bridge stop (closed-probable: his own menubar pattern — he stopped the
bridge himself at mix end the same way).

**Environment notes:** codex-cli v0.144.0 (org-doc hook mechanics were verified on
0.142.5 — retest pre_tool_use firing Jul 11, see org doc §10); a `ghidra` MCP
server fails to start in the codex session (unrelated tooling, ignore); Codex
session runs YOLO permissions by the operator's choice. Retro: skipped-by-clock
tonight; next session's /retro takes this evening in scope (raw material lives in
these docs).

**Session purge:** superman4's last act was killing every tmux session except
`codex` (operator order) — career, superman3/4, all attended + worker lanes. Lane
state = on-disk briefs (`docs/prompts/active/*_state_*.md`) + the registry, not
panes. Claude-side transcripts persist on disk and are resumable, but treat repo
docs as the only current truth.
