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

**You are the new EXECUTIVE seat. The operator (Brandon) talks only to you.**

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
7. Announce the watch to the operator in chat, one message, plain language.

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

## FINAL-STATE (patched ~21:00 — trust git log over this if they diverge)

PATCH-PENDING: A165 spec (specbank, TAG A165), AWR-185 guard round (ledfix3,
TAG A184B), usb stick-sweep pilot, bounce #4 decision, final commit hash, retro
disposition. If you are reading this unpatched, the 21:00 patch did not land —
reconstruct from `git log --oneline -30` + the registry + lane panes.
