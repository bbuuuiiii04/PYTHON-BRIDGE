---
doc_status: current
truth_level: handoff-report
last_verified_commit: e46c66c
last_verified_date: 2026-07-09
validation_scope: >
  Workflow-transfer snapshot written on the last Fable-access day (2026-07-09) so the
  operator can resume every workstream in Codex (or any agent CLI) without
  re-explaining anything. Pairs with docs/agents/multi_agent_org_workflow.md (how to
  run the org) and docs/agents/opus_seat_harness.md (build-seat rails). State below
  verified at e46c66c; re-verify against the work registry + git log at pickup —
  lanes were still landing work the same day.
---

# Codex resume state — 2026-07-09 (the Fable → Codex transfer)

**How to boot a Codex executive seat** (mechanics verified vs codex-cli 0.142.5,
2026-07-09): new tmux session in the repo → `codex -m <model> -c
model_reasoning_effort="xhigh"` (the operator's config.toml already defaults to
xhigh + full trust for this repo) → kickstart: "Read AGENTS.md fully, then
docs/agents/multi_agent_org_workflow.md (§10 = your stack's mechanics), then this
doc, then `git log --oneline -30` + docs/status/active_work_registry.md to catch
anything newer, then take the executive watch. The operator talks only to you."
Worker lanes: `tools/agents/dispatch_lane.sh SESSION MODEL EFFORT MSGFILE TAG codex`;
`watch_lane.sh` unchanged. Footgun guard for Codex: `tools/agents/
claude-codex-hooks.json` (Claude-schema hooks, which codex 0.142.5 consumes —
registration + PreToolUse support pending the legacy lane's verification; AGENTS.md
rules are the enforcement meanwhile). IMPORTANT: the Claude project-memory store
does NOT load for Codex — everything transferable lives in repo docs; this doc is
the state pointer. Codex quota window resumes **Jul 11 18:28**.

## The night before this handoff (context in one paragraph)
2026-07-08/09 overnight: F2 (per-drop family/tier/darkness plans, AWR-163), F4
(texture seasoning, AWR-164), AWR-170 (per-tier laser chases + 4-beat pre-chorus
laser blackout), AWR-171 (idle-path blackout-owner leak — QA-found ship-blocker,
fixed same night), the live-config mirror APPLIED (activation = operator menubar
start), USB launcher M1 built (app + DMG real), stems pilot run (separation clean,
scorecard failed on proxy limits → full sweep called off), showcase QA program
(AWR-172). Suite baseline: 3745+ tests, five NAMED environmental reds from repo
root (see the AWR-172 registry row for names). Everything is software-tested only;
the operator's mixes are the live gate.

## Workstream state (verify each against the registry at pickup)

| Workstream | State at e46c66c | Codex pickup |
|---|---|---|
| **AWR-173 CFX filter sweep** | Spec authored (`docs/plans/active/cfx_filter_sweep_spec.md`, Part A–F incl. desk-calibration runbook); operator authorized a Claude implementation round same day — check git log/registry for whether it landed | If unimplemented: implement per spec (probe → CFX read → LED overlay → desk session). If landed: the desk-calibration session (spec Part F) may still be open |
| **D1-F1 phantom-load re-fire** (MAJOR, AWR-172) | Fix **OPERATOR-DEFERRED** — do not implement without his word | Fix shape ready in the AWR-172 row: None-vs-empty distinction at `rb_state_reader.py:405-409` (None = transient unreadable → preserve `_last_track`; "" = real eject → clear) |
| **LED × spectral tuning** | Session brief `docs/prompts/active/led_spectral_tuning_kickoff_2026_07_09.md`; Track A = taste knobs (F4 sparkle grain 0.2–0.6, `led_dispatch_policy.py`), B = white-share LED consumer (computed, zero consumers), C = P1 growl-band centroid (audit rec, `docs/research/spectral_upgrade_audit_2026_07_09.md`), D = queued P2/P3 | Builds gate on the operator's next mix confirming the overnight work live; specs may proceed anytime |
| **Stems** | Pilot report `docs/research/stems_pilot_run_2026_07_09.md`; 33 envelope JSONs kept (re-score in seconds); 4-phase plan in `docs/prompts/active/stems_tuning_session_brief_2026_07_09.md` | Phase 1 = operator labeling round (needs him); full sweep ~27 h CPU, NEVER against a mix |
| **Haze audition** | Checklist brief `docs/prompts/active/haze_audition_session_brief_2026_07_09.md`; burn-down ENABLED in live config 2026-07-09 | Operator-attended; outcomes become tuning rounds |
| **USB launcher** | M1 shipped (app + DMG, ad-hoc signed — Xcode CANCELLED by operator, stays ad-hoc); runbook `docs/setup/usb_launcher_runbook.md` | Only gate = the operator's parity-run table (his Mac, test session); memory-read STOP rule in force |
| **XDJ** | RX3 confirmed → P0 STOP fired; `docs/plans/active/xdj_link_reader_feasibility.md` = SHELVED-WITH-TRIGGER | Reopen only on link-capable gear |
| **QA minors backlog** (AWR-172) | 6 confirmed MINOR, all polish, operator's word gates each | Row has file:line + refuter verdict per item |
| **Undecided operator items** | Pre-drop tease (8-beat chase crawl → snap at impact — no verdict ever given); veto list (strobe_red_white side B, groove width 2.5, NEUTRAL→small laser silence, balloon gray-zone 0.30–0.35); drop-echo theme-and-variation (the one surviving creative proposal) | Surface once each when relevant; never re-litigate decided items |
| **Parked** | F3 blend (needs his one recorded practice session), SS-MIDI port-gone spam (Jul-7 regression), AWR-158 flaky-test hygiene, cloud-look retirement campaign, music library (his re-raise only) | Leave parked until he raises them |

## Standing operator rulings that survive the transfer (his words, do not re-ask)
- Filter feature: LOW-TO-HIGH sweeps only; counterclockwise does NOTHING (final).
- Root-cause fixes only; interim mitigations only when labeled with root-cause work
  scheduled in the same breath.
- Features must generalize across the whole EDM library; per-track tuning gets cut.
- Bridge starts via HIS menubar only; after any start verify exactly one process.
- Frozen gates are not overridden on the implementing lane's own nuance.
- Communication: AGENTS.md §0 (plain language, mechanism kept, no status blocks,
  chat is his only surface — never "see the doc"; label claims
  confirmed/assumed/unknown; state evidence class with every "done").
- Suite claims reconcile BY NAME against the named baseline (AWR-172 row).

## What made this org fast (preserve these, they are the transfer's point)
1. One executive surface; parallel manager lanes; written-artifact hops.
2. Independent verification at every hop (org doc §3) — speed came FROM the gates,
   not despite them: zero rework rounds reached the operator.
3. The dispatch/watch tooling (`tools/agents/`) — tmux + signal files, works for
   any agent CLI unchanged.
4. On-disk state briefs everywhere — seats are disposable, state is not.
5. The seat harness rails for build-tier models (`opus_seat_harness.md`) — the
   failure modes are model-family-agnostic; expect them from GPT seats too.
