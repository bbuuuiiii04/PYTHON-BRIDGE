# Codex Implementation Spec — SoundSwitch Tasks 7–9 (runtime integration · offline/shadow gates · hardware handoff)

> **Status:** planned / spec-only. Repo status stays **SOFTWARE/WIRE-VALIDATED ONLY /
> HARDWARE-UNVALIDATED**. This document specifies the remaining SoundSwitch pack-player work
> (T7→T8→T9). **No implementation is authorized by this doc** — it is the implementer brief.
> Authoring model: Opus 4.8. Tasks 0–6 are merged (PR #115); T7.0 + T7.1 are implemented and
> review-approved on PR #116 (see §A.2).
>
> **One blocker is unresolved and gates only the autoloop-DMX path (T7d):** the autoloop
> `phase_tick` beat→tick scaling + phase origin (§A.5 / §B.T7d). It needs a capture-evidence
> pass before T7d can be implemented. Everything else is determinable from current code.

## Doc group — the SoundSwitch planning/spec set (read in this order)

1. **Implementation authority (the only active impl spec):**
   `docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md` — Part B
   Task 7 (`:534`), Task 8 (`:574`), Task 9 (`:605`); Part C invariants (`:699`).
2. **This combined T7–T9 spec** (the implementer brief; decomposes + pins the integration).
3. **Generic orchestration protocol:** `docs/plans/active/soundswitch_orchestration_prompt.md`.
4. **T7+T8 orchestration prompt:** `docs/plans/active/soundswitch_t7_t8_orchestration.md`.
5. **Adversarial review gates:** `docs/plans/active/soundswitch_review_pack.md` (Gate before-T7
   `:168`, Gate T8 `:195`, Gate T9 `:217`).
6. **Resume ledger:** `docs/plans/active/soundswitch_impl_progress.md`.
7. **Change contract:** `docs/agents/change_contracts.yml` → `soundswitch_pack_player` (`:233`).

If a doc conflicts with code, **code wins**. Every claim below is labeled
**[confirmed]** (read in current code at HEAD `f7ae38d`), **[assumed]**, or **[unknown]**.

---

## Part A — Context & root cause (verified; read, do not implement)

### A.1 What exists after T0–T6 (the pure pieces)
- [confirmed] `soundswitch_laser_player.py` — `LaserPackPlayer` (class `:183`). Pure, I/O-free
  player. Methods: `reload(pack)` `:203`; `select_scripted(soundswitch_id, elapsed_ms, *,
  transport, metadata_ready, authority, source_errored, elapsed_discontinuous, track_changed)`
  `:213`; `select_autoloop(identity, phase_tick, *, authority)` `:227`; `hold_static(slot)`
  `:234`; `release_static(slot)` `:240`; `set_blackout(held)` `:247`; `set_emergency(held)`
  `:251`; `set_masks(*, blackout, emergency)` `:253`; `render() -> PlayerResult` `:334`.
  `PlayerResult(frame: tuple[int,...], diagnostic: PlayerDiagnostic | None)` `:41`.
  `ZERO_FRAME = (0,)*19` `:30`. Every error/stale/missing/unsupported path returns `ZERO_FRAME`
  + a structured diagnostic — **fail-to-zero is built in**.
- [confirmed] Pure render functions: `render_scripted_frame(document, elapsed_ms)` `:103`
  (events with `0 <= time <= elapsed_ms`); `render_autoloop_frame(loop, phase_tick)` `:118`
  (wraps `phase_tick % loop.cycle_ticks`, `cycle_ticks` pinned to `AUTOLOOP_CYCLE_TICKS=19_200`
  in the loader); `render_static_look_frame` `:143`; `resolve_frame(base, static_override,
  blackout, emergency)` `:153` — precedence **emergency/blackout > held static > base > zero**.
- [confirmed] `soundswitch_pack_loader.py` — `load_pack(pack) -> LoadedPack` `:287`; calls
  `verify_pack(root)` internally `:296`. **Blocking filesystem I/O** (rglob + hashing). Raises
  `SoundSwitchPackLoadError(ValueError)` `:22` on any failure. Startup-only.
  `AUTOLOOP_CYCLE_TICKS = 19_200` `:19`.
- [confirmed] `soundswitch_midi_input.py` — `SoundSwitchMidiInputAdapter` `:74`. `start(port_name,
  *, device_name, _message_source)` `:130` spawns one daemon thread (`"ss-midi-input"`) that
  polls rtmidi with a 250 ms blocking `getMessage()` `:307`. `stop()` `:167` (joins, clears
  held). `panic()` `:182`. `on_pack_reload()` `:186`. `snapshot() -> MidiInputSnapshot` `:115`
  — **lock-protected, non-blocking** (`held_static_slot`, `blackout_held`, `worker_alive`,
  `error`, `mail_drop_count`). Hot-path safe. `start()` raises `RuntimeError("already started")`
  `:151` if called twice — hot-reload must `stop()` first.
- [confirmed] `laser_output_backend.py` — `LaserOutputBackend` protocol `:42`
  (`trigger/submit_frame/status/reset/shutdown`). `MidiOutputBackend` `:70` (forwards to
  MidiOutput; byte/order-identical). `NoneBackend` `:103` (no output; `trigger` returns True).
  `PackOutputBackend` `:132` — `__init__(*, scene_to_identity, frame_sender)` `:151`;
  `trigger(msg)` `:163` resolves `msg.scene_name` → identity via `scene_to_identity`, returns
  False (no-op) for unlearned, True for learned; `submit_frame(frame)` `:171` calls
  `frame_sender.submit(frame)`; `shutdown()` `:189` calls `frame_sender.stop()`.
- [confirmed] `soundswitch_frame_sender.py` — `SoundSwitchFrameSender`; `submit(frame_19,
  fixture_map)` `:139` → `expand_ch1_ch19_to_512(frame_19, fixture_map)` `:37` →
  `_worker.put_frame(...)` (non-blocking deque). `fixture_map: dict[int,int]` maps 1-based CH
  (1..19) → 1-based DMX address (1..512). `stop()`/`zero_and_stop()` push a zero packet
  (owner-driven, post T7.0). `enttec_dmx_pro.SoundSwitchDmxWorker` owns the serial port.

### A.2 What T7.0 + T7.1 already landed (PR #116, open)
- [confirmed] **T7.0** (`07581ca`): removed the Enttec worker's module-owned signal handlers;
  `__main__._shutdown` (`:1288`) is the single signal authority and drives a guarded
  `soundswitch_frame_sender.stop()`; `soundswitch_frame_sender = None` placeholder at
  `__main__.py:720`. Review APPROVE. (Carry-forward: place that `stop()` EARLY in `_shutdown`,
  not last, so DMX blackout is prompt once a real sender exists.)
- [confirmed] **T7.1** (`f7ae38d`): `LaserSceneExecutor.__init__(*, config, backend:
  LaserOutputBackend, personality, …)` `laser_executor.py:35` — single injected backend
  (mutual exclusivity at the object); `self._backend = backend` `:45`. `LaserMidiMessage`
  gained `scene_name: str = ""` (`laser_models.py:53`); the executor populates
  `scene_name=selected_scene` via `_materialize_midi` `:515`/`:233`. MIDI byte/order-identical.
  `__main__` still builds+starts `MidiOutput` and wraps it in `MidiOutputBackend` `:381`.
  Review APPROVE. **The `output_backend` config-driven PORT selection was deferred to T7
  (this spec, T7b).**

### A.3 The runtime owner (where T7 integrates)
- [confirmed] `StateManager` runs the 200 Hz loop; `_TICK_INTERVAL = 1.0/200` (`state_manager.py
  :307`); `_run()` `:841` drains events → `_push_tick()` `:3149`. `start()` `:582` spawns one
  daemon thread; **StateManager is the only `DeckState` writer**.
- [confirmed] Mode authority: `_update_lighting` `:3035` sets `os.lighting_mode ∈
  {scripted, autoloop, idle}` each tick — `d.scripted_id and is_playing` → scripted; else
  playing → autoloop; else idle (debounced). Fully state-derived; `os.lighting_mode` written
  `:3084`.
- [confirmed] Laser path: `_build_laser_context(...)` `:3644` → `decision =
  laser_director.tick(ctx)` `:3668` → `laser_executor.on_tick(ctx)` + `on_decision(decision,
  ctx)` `:3672-3674`. In pack mode `on_decision → backend.trigger` advances the autoloop
  selection.
- [confirmed, LIVE-SAFETY] `_build_laser_context` docstring (`:3896`) forbids ALL I/O ("Must
  not call conn.status(), read files, build dicts, scan MIDI ports, or perform any I/O").
  `load_pack()`/config parse are blocking fs — **startup only, never tick**.
- [confirmed] Startup ordering in `__main__.main()`: laser cfg `:715` →
  `_build_laser_startup_wiring` `:716` → `midi_output=laser_bundle.midi_output` `:719` →
  `soundswitch_frame_sender = None` placeholder `:720` (the T7 construction slot) →
  `StateManager(...)` `:794` (executor/backend injected) → readers/injector start `:1170-1173`
  → `sm.start()` `:1175`.
- [confirmed] `laser_executor` is **injected** into `StateManager.__init__` (`:317`/`:333`),
  built in `_build_laser_startup_wiring` `:381`, passed to SM `:800`.

### A.4 The integration design (operator-confirmed 2026-06-21: "StateManager owns it")
Per tick, in pack mode, StateManager DRIVES the pure `LaserPackPlayer` from authoritative state
and submits frames non-blocking — reusing `os.lighting_mode` + deck state + executor-accepted
selection, adding **no second deck/transport authority**:
```
mode = os.lighting_mode
  scripted → player.select_scripted(soundswitch_id=d.meta.soundswitch_id, elapsed_ms, <flags>)
  autoloop → player.select_autoloop(identity=<executor-accepted>, phase_tick, authority)
  idle / not-playing / stop / stale → ZERO frame (player resolves zero; clear held)
controller (SoundSwitchMidiInputAdapter.snapshot(), lock-protected non-blocking):
  player.set_masks(blackout=snap.blackout_held, emergency=<...>) ; hold_static(snap.held_static_slot)
submit: backend.submit_frame(player.render().frame)   # non-blocking deque → DMX worker
```
- [confirmed] `PackOutputBackend.submit_frame` currently has **no caller**. StateManager becomes
  the caller — this is the spec's "nonblocking frame submission". The pure `render()` is
  tick-safe; `submit_frame` is non-blocking.

### A.5 Verified mechanism gaps T7 must close
1. **[BLOCKER — autoloop `phase_tick`]** `render_autoloop_frame` wants `phase_tick` in
   SoundSwitch internal ANIMATION-TICK units (cycle = 19_200), wrapped `% 19_200`, applying
   events with `time < 0 or 0 <= time <= wrapped`. The beat→tick scaling (`TICKS_PER_BEAT`) AND
   the phase ORIGIN (tick-0 must align to the autoloop **arm-sync beat**
   `os.autoloop_arm_sync_beat`, set `autoloop_controller.py:571`, NOT track start) are
   SoundSwitch-internal conventions **absent from code**. `AUTOLOOP_CYCLE_TICKS=19_200` /
   `AUTOLOOP_ARM_PHRASE_BEATS=32` (`config.py:8`) = 600 ticks/beat is **[unknown] — a plausible
   but UNPROVEN guess**; the arm phrase need not equal the animation cycle. In the existing OS2L
   path SoundSwitch advances the animation itself; pack/DMX mode must replicate it. **Wrong value
   = wrong live autoloop animation. DO NOT GUESS.** → see T7d; gated on a capture-evidence pass.
2. **[bug — T5/T6 stub]** `PackOutputBackend.submit_frame(frame)` (`laser_output_backend.py:171`)
   calls `self._frame_sender.submit(frame)` but `SoundSwitchFrameSender.submit` requires
   `(frame_19, fixture_map)`. **Arg mismatch** — `fixture_map` must be baked into the sender (or
   the backend) at construction. Live-safety: a wrong/missing map = wrong DMX addresses.
3. **[design — scripted flags]** `select_scripted`'s `transport / metadata_ready / authority /
   source_errored / elapsed_discontinuous / track_changed` have NO direct DeckState source. Each
   must be derived per-tick (each gates render-vs-ZERO). Allowed string values (from the player
   tests, the usage contract): `transport ∈ {playing, paused, stopped, ended, unloaded}`;
   `authority ∈ {fresh, stale, ambiguous}`. Diagnostics: `metadata_ready=False →
   "metadata_not_ready"`; `elapsed_discontinuous=True → "elapsed_discontinuity"`;
   `track_changed=True → "track_change"` (each suppresses render → zero).
4. **[glue — `scene_to_identity`]** Not exposed by `LoadedPack`. The `policy_name →
   target_identity` crosswalk lives only in `selection_map.json` `bridge_scenes[]` (filter
   `resolution == "project_target"`, `control_classification == "pack_selection"`).
   `LaserMidiMessage.scene_name` carries the `LaserConfig` scene name = the `policy_name` key.
   T7 must either extend `load_pack()` to expose a `bridge_scene_crosswalk: dict[str,str]` or
   read `selection_map.json` at startup and build `scene_to_identity` there.
5. **[glue — executor-accepted identity routing]** Neither `PackOutputBackend` nor the executor
   exposes the last-accepted autoloop identity. `PackOutputBackend.trigger` resolves it but does
   not store it; `LaserSceneExecutor._last_triggered_scene` (`laser_executor.py:50`/`:249`,
   exposed via `status()["last_scene"]` `:360`) is the scene NAME, not the identity. T7 adds a
   nonblocking `last_accepted_identity` getter on `PackOutputBackend` (single source of truth)
   that StateManager reads to drive `select_autoloop`.
6. **[glue — `fixture_map`]** No loader exists. T7 adds a `fixture_map` config field
   (`{"1":1,…,"19":19}`, string keys parsed to `dict[int,int]`) + loader, baked into the sender.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Pack mode is **default-off / dry-run**; **no implicit hot enable**. With pack disabled, OS2L /
  MIDI-laser / Rekordbox / LED-Govee / command / status behavior must be **byte- and
  order-unchanged**.
- The 200 Hz `_push_tick` (and `_build_laser_context`) gain **no** blocking fs/MIDI/serial/
  network/subprocess/lock-contended/sleep work. Pack + config are **loaded and verified before
  worker threads start**.
- `StateManager` remains the only `DeckState` writer; it creates **no second deck/transport
  authority** (reuse `active_deck`, `DeckState.scripted_id`, `TrackMetadata.soundswitch_id`,
  `elapsed_ms`/`playing`, `os.lighting_mode`, beat/phrase, executor-accepted selection).
- Physical MIDI-laser and direct DMX are **mutually exclusive** — enforced at the executor
  object (done, T7.1) **and at the port** (T7b: never open the IAC port when
  `output_backend=pack`).
- Do NOT import `tools/ssfmt/re/` into production modules. Do NOT mutate the SoundSwitch project
  (decode/export read-only). Do NOT open any MIDI/serial/Art-Net/Enttec/DMX device in unit
  tests. Commit no secrets / absolute paths / device IDs / live config / captures / project bytes.
- Out of scope: any change to OS2L, the Rekordbox readers, LED/Govee, or the laser MIDI wire
  format. Do not modify `laser_output_backend.py`'s `MidiOutputBackend`/`NoneBackend` behavior.

### Task 7a — config + validated loader + tracked example  *(no unknowns)*
- New `config/soundswitch_pack_player.example.json` (house style: top-level `_comment`,
  `enabled:false`, all keys with safe defaults, no trailing commas). Fields (spec `:539`):
  `enabled:false`, `dry_run:true`, `output_backend:"none"`, `pack_path:""`,
  `fixture_map:{"1":1,…,"19":19}`, `fixture_map_path:""` (optional alt to inline map),
  `midi_input_aliases:{}`, `enttec_port:""`, `frame_stale_timeout_ms:250`,
  `controller_hold_timeout_ms:2000`.
- New `soundswitch_pack_player_config.py` mirroring `laser_config.load_laser_director_config`
  (`laser_config.py:138`): `load_soundswitch_pack_player_config(path: Optional[str]=None) ->
  SoundSwitchPackPlayerConfigResult`. **Never raises.** Path order: arg → env
  `RBSS_SOUNDSWITCH_PACK_PLAYER_CONFIG` → `<repo>/config/soundswitch_pack_player.json` → absent
  → `available=False, reason="not_configured"`. Invalid → `available=False,
  reason="invalid_config", errors=(...)`. Valid → `available=True, reason="ok", config=...`.
  Frozen `SoundSwitchPackPlayerConfig` (validate: `output_backend ∈ {none,midi,pack}`;
  `fixture_map` keys 1..19 → values 1..512; timeouts positive ints; `enttec_port` string).
- `SoundSwitchPackPlayerConfigResult(available, reason, config, errors)` frozen dataclass.

### Task 7b — startup wiring + backend port selection + fix the submit_frame/fixture_map bug
- In `__main__.main()` at the `soundswitch_frame_sender = None` slot (`:720`), BEFORE
  `StateManager(...)`: load config (7a). If `available` and `enabled`:
  - `pack = load_pack(cfg.pack_path)` (blocking fs — here, startup only). On
    `SoundSwitchPackLoadError`: log WARNING, leave pack disabled, do NOT start any worker
    (never partial). Build `scene_to_identity` (gap #4).
  - **`output_backend` PORT selection (mutual exclusivity at the port):**
    - `midi` / pack disabled / default: build + `start()` `MidiOutput` exactly as today →
      `MidiOutputBackend`. Behavior-neutral. (already wired by T7.1)
    - `pack`: do **not** build/start `MidiOutput` (do not open IAC). Build
      `SoundSwitchFrameSender(enttec_port, fixture_map=cfg.fixture_map)` (default-off/dry-run
      keeps serial closed) → `PackOutputBackend(scene_to_identity=…, frame_sender=…)`. Build
      `LaserPackPlayer(pack)` + `SoundSwitchMidiInputAdapter(bindings, …).start(...)`. Set the
      module-level `soundswitch_frame_sender` (activates the T7.0 `_shutdown` stop wiring; also
      apply the T7.0 carry-forward: move `sender.stop()` early in `_shutdown`).
    - `none` / dry-run / disabled: `NoneBackend`; open neither MIDI nor serial.
  - Inject the chosen backend into `LaserSceneExecutor` (single slot, T7.1) and pass the
    player + midi-input adapter to `StateManager` (new ctor params, default `None`).
- **Fix gap #2:** bake `fixture_map` into `SoundSwitchFrameSender.__init__` (store as
  `self._fixture_map`); `submit_frame(frame)` → `frame_sender.submit(frame, self._fixture_map)`,
  OR have `PackOutputBackend` hold `fixture_map` and pass it. Pick ONE; add a test that
  `submit_frame` reaches the worker with the correct expanded 512-frame.
- **Gap #4 / #6:** extend `load_pack`/`LoadedPack` with `bridge_scene_crosswalk: dict[str,str]`
  (cleaner; needs a `change_contracts` note) OR read `selection_map.json` at startup; build
  `scene_to_identity`. Add `fixture_map` loader (inline map or `fixture_map_path`).

### Task 7c — StateManager SCRIPTED-mode integration  *(no phase_tick dependency)*
- Add `_soundswitch_player` + `_soundswitch_input` (+ the chosen `PackOutputBackend`) as
  injected `StateManager` fields (default `None` → all pack logic inert when absent: preserves
  default-off neutrality).
- In `_push_tick`, AFTER the existing laser path, **only when pack mode active**, drive the
  player for `os.lighting_mode == "scripted"`:
  - `player.select_scripted(soundswitch_id=d.meta.soundswitch_id, elapsed_ms=elapsed_ms,
    transport=<derive>, metadata_ready=bool(d.meta.soundswitch_id), authority=<derive from
    position staleness — map `position_stale`/`snap.is_stale(MEM_STALE_S)` `:3932` → fresh|stale|
    ambiguous>, source_errored=<derive>, elapsed_discontinuous=<derive: seek/TC jump vs prior
    tick elapsed>, track_changed=<derive: `d.load_gen` flip vs prior tick `models.py:86`>)`.
    Pin each derivation against the EXISTING scripted prior art (`_arm_scripted` `:3105`,
    staleness handling, `load_gen`). Each suppressing flag → player returns zero + diagnostic.
- Controller masks (when a `_soundswitch_input` exists): read `snapshot()` (non-blocking),
  `player.set_masks(blackout=snap.blackout_held, emergency=False)` and
  `player.hold_static(snap.held_static_slot)` / `release_static(...)` on change.
- Submit: `backend.submit_frame(player.render().frame)` (non-blocking).
- **Transitions → safe frame:** on every mode/transition path (scripted→autoloop→idle, deck
  change, track load, stop/stale, config disable, pack reload, worker error, shutdown), clear
  the player's held/pending state and resolve ZERO. Mirror the existing `_apply_lighting`
  transition cleanup (`:3087`). Cover ALL paths (checklist #4), not just the scripted one.

### Task 7d — StateManager AUTOLOOP-mode integration  **[BLOCKED — phase_tick evidence]**
- DESIGN (implementable once the blocker is resolved): for `os.lighting_mode == "autoloop"`,
  read the executor-accepted identity (gap #5 getter) and
  `player.select_autoloop(identity=<accepted>, phase_tick=<computed>, authority=<derive>)`.
- **BLOCKER:** `phase_tick = int((abs_beat_pos - arm_sync_beat) * TICKS_PER_BEAT)` where BOTH
  `TICKS_PER_BEAT` and the `arm_sync_beat` origin convention must be **proven from capture
  evidence** (autoloop DMX wire output vs beat position for the captured bank-4 / IAC autoloops;
  see memories `project_ss_dmx_runtime`, `project_ss_autoloop_banks`). Until proven, **do not
  implement T7d**; pack mode supports scripted + static + controller + blackout, with autoloop
  DMX deferred. Add a guard so autoloop mode in pack output resolves to a safe/zero (or held
  static) frame rather than a guessed animation.
- **Evidence pass required first** (Claude evidence/analysis role): derive + verify
  `TICKS_PER_BEAT` and the phase origin against the capture corpus; record the proof in the
  ledger and a short evidence note before this task is unblocked.

### Task 7e — sanitized status + no-implicit-hot-enable commands
- Status: add a sanitized pack-player snapshot to `StatusWriter.snapshot()` (`runtime_status.py
  :86`), nested under `laser_director` or a new top-level key, via a provider — mirror the LED
  allowlist sanitizer (`state_manager.py:_sanitize_led_adapter_status` `:724`,
  `_sanitize_led_scene_ref` `:783`). Expose: availability, enabled/dry-run, pack schema/hash,
  source-project hash, supported boundary, current source identity, elapsed/phase, held static
  slot, blackout owners, last-frame hash, mailbox drops, MIDI-input health, stale/error state.
  **Never** expose audio paths, device names, or serial details.
- Commands: add `set_soundswitch_pack` enable / `reload` / `backend` commands via the
  runtime-command change contract — parse-validate first (`runtime_status.parse_command` `:385`
  allowed-set + per-command validation), dispatch in `CommandReader.handle_command` `:247`,
  callback param `:179`, wired in `__main__` `CommandReader(...)` `:1008`. Template:
  `set_laser_director` `:276`. **No implicit hot enable:** validate first; require explicit
  operator action; an invalid reload keeps the old verified pack disabled or forces zero —
  **never a partial swap** (`stop()` the old midi-input before any `start()`; never hold two
  backends).

### Task 8 — offline + shadow verification gates (spec `:574`; Gate-T8 `:195`)
0. Re-run the proof gate; require `final_verdict: PASS_IMPLEMENTATION_MAY_BEGIN`; confirm pinned
   UUID `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}` + active-cue union SHA-256
   `88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2`.
1. **F9** (one-byte pack mutation rejected) + **F10** (active CC/pitch-bend override
   export-fail) COMPLETE and passing. [assumed — the current proof gate already shows
   `0 INCOMPLETE` with "F10 promoted in Task 4"; T8 must CONFIRM both directly and add any
   runtime-context coverage Gate-T8 requires, not credit a prior pass blindly.]
2. Export the frozen current-project corpus **twice → byte-identical** (no timestamps in hashed
   content; canonical JSON + stable ordering); diff the trees.
3. Independent verifier **rejects every adversarial mutation** (one-byte flip, missing/extra
   artifact, count mismatch, reordered, wrong UUID even with the RAVE GUID, drifted union SHA).
4. **Totals all hold:** 42/42 Autoloops; 44/45 scripted (inactive demo visible/unsupported);
   19/19 IAC; 32/32 existing-path scripted; **232 render + 1 catalog-tail = 233**; 166 active
   cues, 0 missing; 32 Static Looks; 4 DDJ overrides; **0 learned-event collisions**.
5. **Oracles without contamination:** A5 16/16; cold new-track 3/3 one-based vs 0 direct;
   legacy Autoloop discriminator; file-5/file-18 exact cases — replay WITHOUT capture-seeded
   production state (captures are oracles only).
6. Add static tests for slots 8/16/17/24 and controlled slot-7 create/edit.
7. **Shadow mode:** run the pack backend with physical backend `none`; log ONLY frame hashes;
   compare to independent expected output. **No hardware claim anywhere.** Single-process
   verification + rollback plan documented.
- Note: T8 must NOT require T7d (autoloop DMX). Shadow-mode frame-hash coverage of autoloop
  output is itself **gated on the phase_tick proof** — if T7d is still blocked, T8 shadow
  covers scripted/static/blackout frames and explicitly logs autoloop coverage as deferred
  (no silent gap).

### Task 9 — operator hardware-gate handoff DOCUMENT (author only; NEVER execute; spec `:605`)
Author `docs/plans/active/soundswitch_t9_hardware_handoff.md` (a document, not code; open no
device, send no output, do not restart the bridge). To be approvable against Gate-T9 (`:217`)
it MUST:
- name whether fixtures are connected/disconnected, the selected `output_backend` +
  **sanitized** port alias, the zero-frame preflight, and the physical kill method;
- give exact bridge stop/start + rollback commands and single-process verification
  (`rbss-bridge-verify` / `pgrep -f rb_ss_bridge_v2 | wc -l == 1`) after any restart;
- specify the test order: safe OFF/static → one controlled Autoloop → scripted track → DDJ
  press/release → blackout press/release → disconnect → shutdown, each with explicit
  logs/status/physical pass/fail criteria;
- state plainly that DMX and MIDI-laser output are **mutually exclusive** and exactly one bridge
  process is required;
- surface the **`kill -9` Enttec last-frame hazard** (firmware repeats the last frame; physical
  kill/power is the true failsafe) — software must not claim fail-safe `kill -9`;
- require **explicit operator approval**; state that implementation completion is NOT approval
  and NOT hardware validation; status stays HARDWARE-UNVALIDATED.
- Flag as a blocker any handoff that auto-enables output, infers approval from completion, omits
  the kill path, or claims hardware/show readiness.

---

## Part C — Invariants that MUST still hold (live safety)
- `StateManager` is the only `DeckState` writer; reader threads publish events, never mutate.
- `_push_tick` / `_build_laser_context` gain NO blocking fs/MIDI/serial/network/subprocess/
  lock/sleep work. Pack I/O is worker-owned + non-blocking mailbox; pack/config loaded+verified
  before workers start.
- Laser **policy** (Director) and **execution** (Executor) stay separate; MIDI-laser output is
  byte/order-identical under `MidiOutputBackend`; OS2L/LED/Govee/Rekordbox unchanged when pack
  mode is off.
- Pack mode default-off / dry-run; no implicit hot enable; DMX and MIDI-laser mutually exclusive
  at the executor object AND at the port.
- Production modules do NOT import `tools/ssfmt/re/`; captures are oracles only, never pack input
  or seeded production state.
- Every stop / stale / error / reload / disconnect / shutdown / mode-transition path resolves
  **zero**, never a retained nonzero frame. New player/controller state is cleaned up on EVERY
  transition path (idle/scripted/autoloop/deck-change/track-load/disable/reload/error/shutdown).
- No secrets / absolute paths / device IDs / live config / captures / project bytes / proof
  reports committed. Sanitized status only.

## Part D — Tests (pure-function seam required for every algorithm)
- 7a: config loader — valid/invalid/absent → correct `Result`; `output_backend` + `fixture_map`
  validation; never raises. Pure, no fs dependency beyond a tmp file.
- 7b: `output_backend=pack` opens NO MIDI port; default/disabled opens MIDI exactly as today and
  emits IDENTICAL MIDI; `submit_frame` reaches the worker with the correctly expanded 512-frame
  (fixes gap #2); `scene_to_identity` built correctly from `bridge_scenes`; load failure leaves
  pack disabled (no partial). No serial/MIDI device opened.
- 7c: scripted-mode drive — each `select_scripted` flag derivation is unit-tested against the
  player's diagnostic contract (metadata_not_ready / elapsed_discontinuity / track_change →
  zero); every transition path resolves zero; default-off (player=None) is byte/order-neutral
  (existing tests pass unchanged). Pure: feed synthetic deck snapshots, assert frames.
- 7d: BLOCKED — add the phase_tick scaling+origin proof test ONLY after the evidence pass pins
  the value (assert against captured oracle frames). Until then, autoloop-pack resolves
  safe/zero (tested).
- 7e: status sanitization (no audio paths/device names/serial); commands validate-first, reject
  invalid, never partial-swap; reload `stop()`s before `start()`.
- 8: as Part B Task 8 — proof gate, F9+F10, twice-export byte-identical, all totals + union SHA,
  adversarial mutations rejected, oracles uncontaminated, shadow frame-hash (no hardware).

## Part E — Acceptance (definition of done)
- [ ] 7a config + loader land; example tracked; all loader tests pass; hard checks green.
- [ ] 7b: pack path opens no IAC; default path MIDI-identical; submit_frame/fixture_map bug
      fixed + tested; scene_to_identity correct; no partial swap on load failure.
- [ ] 7c: scripted-mode frames correct; every transition → zero; default-off neutral (full suite
      OK; the 2 known pre-existing failures unchanged, no new ones).
- [ ] 7d: stays BLOCKED until the phase_tick evidence pass pins scaling+origin (proof in ledger);
      autoloop-pack resolves safe/zero until then. NO guessed value committed.
- [ ] 7e: sanitized status; no-implicit-hot-enable enable/reload/backend commands; change
      contract `docs_update` docs updated.
- [ ] 8: proof gate PASS; F9+F10 confirmed complete; twice-export byte-identical; all totals +
      union SHA; oracles uncontaminated; shadow backend none, frame-hash only; no hardware claim.
- [ ] 9: handoff DOCUMENT authored + Gate-T9-approvable; never executed.
- [ ] Proof gate `PASS_IMPLEMENTATION_MAY_BEGIN` at the T7/T8 HEAD; hard checks green; ledger +
      `change_contracts.yml` (`soundswitch_pack_player`) `docs_update` updated; commit per task.

## Open evidence items (must be resolved before the gated work)
1. **autoloop `phase_tick` scaling + origin** — capture-evidence pass to prove `TICKS_PER_BEAT`
   and the `arm_sync_beat` phase origin (gates T7d and autoloop shadow coverage in T8).
2. **F9/F10 status** — confirm whether the proof gate's current `0 INCOMPLETE` already satisfies
   the spec's "complete F9+F10 in T8", or whether runtime-context coverage is still owed.

## When you finish (per-task, once implementation is authorized)
- Commit on `soundswitch/impl` (PR #116 or its successor); record exact gate/test output in the
  commit/PR + the ledger; run an opus-tier fresh-context adversarial review against the matching
  review-pack gate (before-T7 / T8 / T9) before advancing.
