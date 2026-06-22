# SoundSwitch implementation — progress ledger

last_updated: 2026-06-22T00:35:04Z   last_session_model: gpt-5.5-codex

## Proof gate

- HEAD: `b7e0e66` plus the reviewed T7a worktree
- Verdict: `PASS_IMPLEMENTATION_MAY_BEGIN` (exit 0; proven at `b7e0e66`)
- Checks: 29 PASS / 0 FAIL / 0 INCOMPLETE (F10 promoted in Task 4)
- Foundation: 27/27 PASS
- Note: T7.0 (`07581ca`) and T7.1 (`f7ae38d`) introduce NO SoundSwitch-semantics
  change (signal/shutdown wiring; executor backend injection + scene_name), so the
  proof gate is unaffected. Rerun at the T7 checkpoint and whenever SS
  decode/export/render changes (T8).

## Orchestration

- Operator (2026-06-21) selected Codex orchestration with effort-tiered subagents for
  T7+T8+T9 and separately authorized controlled Enttec/MIDI/bridge validation after
  the required offline/shadow/review and rollback gates. Before-T7 design review is
  satisfied; auto-advance T7→T8.
- Running PR for the series: **#116** (`soundswitch/impl` → `main`).
- Carry-forwards to T7 author:
  1. In `__main__._shutdown`, place the real `soundswitch_frame_sender.stop()`
     EARLY (not last) so DMX blackout is prompt.
  2. T7 owns the `output_backend` config + the __main__ PORT-level selection
     (don't open IAC when `output_backend=pack`; build SoundSwitchFrameSender →
     PackOutputBackend; `none`→NoneBackend). T7.1 delivered only the executor-OBJECT
     half. opus-xhigh T7 reviewer must verify port-level mutual exclusivity.

## Task 7 design (verified through HEAD `b7e0e66`; for the implementer spec)

Surfaces mapped (read-only triage). Integration design direction — StateManager
is the runtime owner; per tick in pack mode it DRIVES the pure `LaserPackPlayer`
from authoritative state and submits frames nonblocking:
- mode authority = `os.lighting_mode` (`state_manager.py:3084`; scripted if
  `d.scripted_id and is_playing`, else autoloop if playing, else idle/debounced).
- scripted → `player.select_scripted(soundswitch_id=d.meta.soundswitch_id,
  elapsed_ms=d.elapsed_ms, …)`; autoloop → `player.select_autoloop(identity=
  <executor-accepted>, phase_tick, …)`; idle/stop/stale → safe/ZERO frame;
  controller (MIDI-input `snapshot()`, lock-protected nonblocking) →
  `set_masks(blackout, emergency)` + `hold_static(slot)`.
- output path: `submit_frame(player.render().frame)` → `frame_sender.submit(...)`
  (nonblocking deque). `PackOutputBackend.submit_frame` currently has NO caller —
  StateManager becomes the caller (the spec's "nonblocking frame submission").
- load/verify ordering: build `SoundSwitchPackPlayerConfig` + `load_pack()` (blocking
  fs I/O — startup ONLY) + `LaserPackPlayer` + `SoundSwitchMidiInputAdapter` +
  `PackOutputBackend(scene_to_identity, frame_sender)` at `__main__.py:722`
  (the `soundswitch_frame_sender = None` placeholder), BEFORE `StateManager(...)`
  (~794) and `sm.start()` (~1175).

### T7d phase evidence result (verified 2026-06-21; still blocked)

- Controlled authoring evidence stores the next beat at tick 601 and a three-beat move at
  tick 1800. An independent rate sweep over captured `SSAutoLoop13.ssfile` segment 49 uniquely
  favored 600 ticks/beat (445/453 matching frames; 599→407, 601→420).
- The universal origin is **not proven**. `autoloop_arm_sync_beat` is transient and clears
  after arm lock, while captured phrase-marker output aligns near tick zero at the latest
  accepted MIDI/refire beat (`midi_refire_origin_beat`). Existing captures do not cover every
  initial-arm, master-switch, drop-hold, buildup, phrase-anchor, and correction path.
- Decision: T7d and T8 autoloop shadow parity stay blocked. Runtime integration must resolve
  autoloop pack mode to safe zero (or a held static override) until a universal origin is proven.

### BLOCKER found during mechanism extraction (originally verified at `f7ae38d`)
Task 7 is NOT thin glue. Determinable-from-code: config+loader, startup wiring,
scripted-mode integration, status, commands, scene_to_identity, fixture_map. But:
- **[BLOCKER — autoloop phase_tick]** `render_autoloop_frame(loop, phase_tick)`
  (`soundswitch_laser_player.py:118`) needs `phase_tick` in SoundSwitch internal
  ANIMATION-TICK units (cycle = `AUTOLOOP_CYCLE_TICKS=19_200`, loader:19), wrapped
  `% 19200`. The beat→tick scaling (`TICKS_PER_BEAT`) AND the phase ORIGIN (must
  align tick-0 to `os.autoloop_arm_sync_beat`, not track start) are SS-internal
  conventions ABSENT from code. 19200/`AUTOLOOP_ARM_PHRASE_BEATS`(=32, config.py:8)
  = 600 is a plausible but UNPROVEN guess; the arm-phrase ≠ proven animation cycle.
  In the existing OS2L path SS advances the animation itself — pack/DMX mode must
  replicate it. Pinning needs CAPTURE-CORPUS evidence (autoloop DMX vs beat pos).
  DO NOT GUESS (live rig). → autoloop-DMX integration gated on an evidence pass.
- **[bug — T5/T6 stub]** `PackOutputBackend.submit_frame(frame)` calls
  `frame_sender.submit(frame)` but `SoundSwitchFrameSender.submit` needs
  `(frame_19, fixture_map)` — arg mismatch. fixture_map must be baked into the
  sender/backend at construction. Live-safety (wrong map = wrong DMX addresses).
- **[design]** `select_scripted` flags transport/authority/metadata_ready/
  source_errored/elapsed_discontinuous/track_changed have NO direct DeckState
  source — derive each per-tick from existing scripted prior art (each gates
  render-vs-ZERO). Player test = usage contract (`tests/test_soundswitch_laser_player.py`).
- **[glue]** `scene_to_identity` not exposed by LoadedPack — join
  `selection_map.json` `bridge_scenes[].policy_name → target_identity`
  (resolution=project_target, classification=pack_selection); extend loader or read raw.

Mechanisms to PIN during spec authoring (verify against current code, no guessing):
1. `phase_tick` source for `select_autoloop` (beat/autoloop-tick authority var —
   check the autoloop controller + `abs_beat_pos`/`autoloop_tick_just_fired`).
2. Routing the executor-accepted autoloop IDENTITY to StateManager (PackOutputBackend
   exposes last-accepted identity, vs StateManager maps `_last_triggered_scene` via
   `scene_to_identity`). Decide one; single source of truth.
3. `select_scripted` arg authority vars: transport / metadata_ready / authority /
   source_errored / elapsed_discontinuous / track_changed — map from deck state +
   the player's own tests (`tests/test_soundswitch_laser_player.py` = usage contract).
4. `scene_to_identity` built from the pack's 19 IAC bindings (loader output).
5. `fixture_map` (CH1-CH19→512) from `fixture_map_path`; passed to `frame_sender.submit`.
Live-safety: `_build_laser_context` forbids ALL I/O (`state_manager.py:3896`);
`load_pack`/config parse are blocking fs — startup only, never tick. Every transition
path (scripted/autoloop/idle, deck change, track load, stop/stale, config disable,
pack reload, worker error, shutdown) must clear held/pending state and resolve ZERO.

## Next action

> Task 7b: implement startup/backend port selection, verified-pack crosswalk/bindings,
> baked fixture-map submission, early sender shutdown, and no-partial-start behavior.
> Preserve existing MIDI startup exactly when pack config is absent/disabled. An enabled
> `none`/dry-run config opens neither MIDI nor serial. Keep T7d autoloop output safe/zero.

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
| 7 | runtime integration | wip | partial | partial | #116 | T7.0 + T7.1 review APPROVE. T7a config/loader: 17 tests OK, hard docs gates pass, fresh review APPROVE. T7d: 600 ticks/beat proven but universal origin not proven; safe-zero remains required. Next: T7b startup/backend wiring. |
| 8 | offline/shadow gates | todo | — | — | — | |
| 9 | hardware handoff | todo | — | — | — | operator-only; never auto-execute |
