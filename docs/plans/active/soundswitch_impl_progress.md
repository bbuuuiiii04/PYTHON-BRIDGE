# SoundSwitch implementation — progress ledger

last_updated: 2026-06-21T23:55:00Z   last_session_model: claude-opus-4-8

## Proof gate

- HEAD: `07581ca`
- Verdict: `PASS_IMPLEMENTATION_MAY_BEGIN` (exit 0; last proven at `601d8db`)
- Checks: 29 PASS / 0 FAIL / 0 INCOMPLETE (F10 promoted in Task 4)
- Foundation: 27/27 PASS
- Note: T7.0 (`07581ca`) is signal-handler/shutdown wiring only — introduces NO
  SoundSwitch-semantics change, so the proof gate is unaffected. Rerun at the T7
  checkpoint and whenever SS decode/export/render changes (T8).

## Orchestration

- Operator (2026-06-21) put a Claude session in charge of T7+T8+T9-handoff per
  `soundswitch_t7_t8_orchestration.md`; chose **Claude-subagents-per-effort-table**
  as the implementer path (sanctioned failover for THIS workstream only — does not
  generalize). Before-T7 operator milestone is satisfied; auto-advance T7→T8.
- Running PR for the series: **#116** (`soundswitch/impl` → `main`).
- Carry-forward to T7 author: in `__main__._shutdown`, place the real
  `soundswitch_frame_sender.stop()` EARLY (not last) so DMX blackout is prompt.

## Next action

> T7.1 IN PROGRESS (PR #116): LaserSceneExecutor single-backend injection +
> port-level MIDI/DMX mutual exclusivity + scene_name on the trigger path.
> Then complete Task 7, auto-advance to T8, run after-T8 opus-max review, author
> + review T9 handoff, then AWAITING OPERATOR hardware gate.

## Task status (0–9)

| task | title | impl | review | gates | PR | notes |
| ---- | ----- | ---- | ------ | ----- | -- | ----- |
| 0 | change contract | done | done | green | #115 | Review approved; hard checks green; full suite `Ran 1881`, `OK` (3 skipped, 1 expected failure). |
| 1 | project decoder | done | done | green | #115 | Review approved; 17 targeted tests; proof 27/0/2 PASS; full suite `Ran 1898`, `OK` (3 skipped, 1 expected failure). |
| 2 | exporter and verifier | done | done | green | #115 | Review approved; 31 targeted tests; F9 PASS; full suite `Ran 1914`, `OK` (3 skipped, 1 expected failure). |
| 3 | pure renderer/player | done | done | green | #115 | Loader+player+verifier parity at `94cee81`. Opus review APPROVE (nits only). 43 targeted OK; full suite `Ran 1942`, `OK` (3 skipped, 1 expected failure); proof 28/0/1; twice-export byte-identical; F9 mutation rejected; identity gate rejects wrong-UUID scratch corpus. |
| 4 | MIDI input adapter | done | done | green | #115 | 32 tests; F10 CC export-fail check; proof 29/0/0; device-name dispatch + error-preservation + zombie-worker fixes post-review. HEAD `6a8ecf2`. |
| 5 | output backend | done | done | green | #115 | MidiOutputBackend/NoneBackend/PackOutputBackend; priority signature fix; PackOutputBackend unlearned→False; stale attr removed. 70+170 tests pass. HEAD `db7eac2`. |
| 6 | Enttec sender | done | done | green | #115 | 518-byte VLN-identical framing; bounded non-blocking deque; zero-on-stop; kill-9 hazard documented. 35 new tests; 2009 total. T7 note: remove _install_signal_handlers before wiring into __main__. HEAD `601d8db`. |
| 7 | runtime integration | wip | — | — | #116 | T7.0 done (`07581ca`): signal handlers removed, __main__ single signal authority; review APPROVE (fresh opus). Next: T7.1 backend mutual-exclusivity, then Task 7 proper. |
| 8 | offline/shadow gates | todo | — | — | — | |
| 9 | hardware handoff | todo | — | — | — | operator-only; never auto-execute |
