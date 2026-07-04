# Implementation Spec - Audit 2026-07-03 Follow-ups F1/F2 + LED-slice Audit (Sonnet session)

status: planned
last_verified_commit: f1310fa (post-merge HEAD 85aac85)

Operator-sanctioned Sonnet implementation lane (Codex quota exhausted 2026-07-03; operator granted
this delegation explicitly). Execute tasks in order: A, B, C. One commit per task for A and B;
task C is strictly read-only.

Baseline [confirmed 2026-07-03]: suite `python3 -m unittest discover tests` → 2762 OK
(5 skipped, 1 expected failure); all three hard checks pass.

## Absolute rules
- Work directly on `main`. No branches, no worktrees, no force-push, no history rewrites, no
  `git clean`. Do not push; turn-end hooks may push on their own — keep the tree clean between
  tasks so a hook can never capture a half-done state. If `git commit` hits a concurrent index
  lock, wait 5 s and retry.
- **Do not touch `state_manager.py` or `docs/plans/active/led_dispatch_extraction_spec.md`** — a
  parallel session owns them right now. None of your tasks need them.
- Do not restart or touch the running bridge, Rekordbox, SoundSwitch, lasers, LEDs, Govee, or any
  hardware. Software changes + tests only.
- Contract-first (AGENTS.md §7): before each code task, find the matching contract in
  `docs/agents/change_contracts.yml` (extend it first if missing); update every `docs_update` doc;
  before each commit run the three hard checks (`python3 tools/check_docs_metadata.py`,
  `check_agent_contracts.py`, `check_docs_drift.py`) and the full suite — all green.
- Error handling in code you write: propagate or fail closed like the surrounding code; no broad
  try/except; no silent fallbacks.
- Claim discipline in your report: label claims confirmed / assumed / unknown.

## Task A — invert the probe_live_bpm dependency
[confirmed] `live_bpm.py:22-33` (re-verify at HEAD) imports underscore-private discovery
primitives from `probe_live_bpm.py` (`Hit`, `_collect_hits`, `_resolve_anchors`,
`_results_from_samples`, `_select_validation_hits`, and whatever else that import block names) —
the always-running BPM service depends on internals of a file whose docstring calls itself a
standalone probe.

Do: move the runtime-imported symbols (and any private helpers only they use) INTO `live_bpm.py`;
`probe_live_bpm.py` then imports them FROM `live_bpm` (keep public names/signatures identical so
the probe CLI behaves unchanged). Only if a genuine import cycle blocks this, create a single new
module for the shared primitives and have both import it — prefer no new module. Update
`probe_live_bpm.py`'s docstring to say it is a CLI over runtime-owned primitives. Keep the AGENTS
source-map rows accurate.

Verify: full suite; plus `python3 -c "import rb_ss_bridge_v2.live_bpm, rb_ss_bridge_v2.probe_live_bpm"`
from the parent directory succeeds.
Commit message: `Audit F1: runtime owns BPM discovery primitives (probe imports from live_bpm)`
Then print exactly: `SONNET_TASK_DONE A <short-sha>`

## Task B — relocate the parity oracle; fix the energy_model map row
[confirmed] `soundswitch_parity_oracle.py` sits at repo root but has no runtime importer — its
consumers are `tools/ssfmt/*` and tests. [confirmed] `energy_model.py` is listed in the AGENTS.md
§4 "Phrasing / autoloop / beat" runtime row but has zero runtime callers (only
`tools/analyze_anlz_energy_corpus.py` + its test).

Do: FIRST re-verify with `rg` that no root-level runtime module (anything imported transitively
from `__main__.py` — check `soundswitch_parity_registry.py` and the pack loader especially)
imports `soundswitch_parity_oracle`; if any does, STOP task B and report instead of moving.
Otherwise `git mv soundswitch_parity_oracle.py tools/ssfmt/` and update every importer
(`tools/ssfmt/*.py`, tests) plus every doc/source-map reference the hard checks flag. Move
`energy_model.py`'s AGENTS.md listing out of the runtime phrasing row into an offline-tooling
mention (smallest accurate edit; keep table structure valid). Update the relevant subsystem
cards/contracts the checks demand.

Verify: full suite; three hard checks; `rg -n "soundswitch_parity_oracle" --type py` shows only
tools/ssfmt + tests importers.
Commit message: `Audit F2: parity oracle to tools/ssfmt; energy_model listed as offline tooling`
Then print exactly: `SONNET_TASK_DONE B <short-sha>`

## Task C — read-only audit sweep of the LED slice (NO code changes, NO commit)
The 2026-07-03 audit declared these files unaudited (its LED agent was paused mid-sweep):
`led_config.py` (~1,484 lines), `beat_sync_engine.py`, `led_pad_controls.py`, `led_models.py`,
`tools/led_pad_web.py` + `tools/led_pad_assets/` (and any other `led_pad_*` tooling), plus their
tests.

Audit them with the same lens as the main audit, in priority order: (1) correctness — stale
state, race risks vs the 200 Hz StateManager loop, wrong live-output decisions, silent fallbacks
that fake a healthy state; (2) poorly written — broad exception swallowing, copy-paste, fragile
conditionals, misleading names, UI↔backend contract mismatches in the LED Pad; (3) dead/stale
code and config keys nothing reads (verify with rg across the WHOLE repo before claiming dead —
remember getattr-string call sites, and that `LEDColorEngine.lock/unlock/set_palette/
queue_palette/shift` are operator-reserved, never dead); (4) over-engineering; (5) test gaps.

Write the findings report to `/tmp/sonnet_led_slice_audit.md`: severity-ranked findings
(file:line, one-sentence issue, why it matters live, 1-3 lines evidence, confidence, smallest fix
direction), then a checked-and-rejected list, then any coverage you still could not complete. Max
~120 lines. Make no repo changes in this task.
Then print exactly: `SONNET_TASK_DONE C /tmp/sonnet_led_slice_audit.md`

## When you finish
Print exactly `SONNET_ALL_DONE`, then a short report: diff stats for A and B, test counts
before/after, hard-check results, and your top-3 findings from C. If blocked at any point, print
`SONNET_BLOCKED <task> <one-line reason>` and stop cleanly (tree clean, no half-done task).
