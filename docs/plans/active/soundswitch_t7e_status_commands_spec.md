# Implementation Spec — T7e SoundSwitch pack sanitized status + validate-first runtime commands

status: planned — **PENDING REVIEW (ChatGPT), NOT YET IMPLEMENTED**
last_updated: 2026-06-22
implementer: Claude (Opus 4.8) — per operator override for this task (NOT Codex)
target branch/PR: `soundswitch/impl` / #116 (current head `6178795`, CI green)

> **Review gate:** author + commit this spec, then PAUSE for ChatGPT review before any code.
> Live-critical: T7e adds the operator's only hot path to reload/enable/swap the pack runtime, so a
> bad swap can blackout or double-open the Enttec serial port mid-show.

## A. Current code surfaces to inspect (verified; read, do not implement)

- [confirmed] **Status writer**: `runtime_status.py` `RuntimeStatusWriter` builds the heartbeat/status
  dict. It already has `_safe_laser_status()` (`:142`) and `_safe_led_status()` (`:169`), each using
  `_safe_provider_snapshot(provider, provider_name, throttle_key, default)` — a provider callable
  returning a dict, guarded against exceptions/throttled logging. **T7e mirrors this with a
  `_safe_pack_status()` backed by a `pack_status_provider`.**
- [confirmed] **Command reader**: `runtime_status.py` `CommandReader(threading.Thread)` (`:178`) reads
  `/tmp/rb_ss_bridge_v2_commands.jsonl` line-by-line on its OWN thread (`run()` `:228`), `handle_line`
  → `parse_command` (validate) → `handle_command` (dispatch via injected callbacks). It records
  `last_command`/`last_error` (`:221`). Existing commands follow `if cmd == "...": <callback>; return`
  with per-command callbacks passed to `__init__`. `parse_command` (`:385`) raises `ValueError` on
  bad input; `handle_line` catches it into `last_error` WITHOUT mutating state. **This is the
  validate-first seam: validation lives in `parse_command`; a rejected command never reaches a
  callback.**
- [confirmed] **Command thread ≠ push thread.** `CommandReader` runs on `runtime-command-reader`;
  `StateManager._push_tick` runs on the 200 Hz push thread. Any reload/backend swap therefore crosses
  threads → see C5 (atomic publish).
- [confirmed] **Sensitive config fields** (`soundswitch_pack_player_config.py:30-51`): `pack_path`,
  `fixture_map`, `fixture_map_path`, `midi_input_aliases`, `enttec_port` (a **serial port path**).
  None of these may appear in status.
- [confirmed] **Backend status** (`laser_output_backend.py`): `PackOutputBackend.status()` →
  `{backend, available, trigger_count, no_op_count, frame_count, has_frame_sender,
  last_accepted_identity}`. `last_accepted_identity` is a pack scene UUID (a render target, not a
  device) — borderline; T7e excludes it (or exposes only `has_active_identity: bool`).
  `NoneBackend.status()` → `{backend:"none", available, dry_run}`.
- [confirmed] **Pack lifecycle (startup)** in `__main__.py`: `load_soundswitch_pack_player_config()`
  → `_build_soundswitch_pack_startup(cfg)` (builds `LaserPackPlayer`, `SoundSwitchMidiInputGroup`,
  `SoundSwitchFrameSender`, `PackOutputBackend`; returns a `SoundSwitchPackStartupBundle` with
  `.laser_backend/.player/.midi_input/.frame_sender/.reason`) → `_start_soundswitch_pack_workers`
  (starts **input first, sender second**; `:533-539`). On any build/start failure it returns a
  `NoneBackend()` bundle with a `*_failed` reason — i.e. **pack failure already falls back to
  NoneBackend, never to MIDI.** `pack_output_owners` dict (`__main__`) holds sender+input for
  `_shutdown`.
- [confirmed] **T7c driver** (`state_manager.py` `_drive_pack_output`): reads `self._pack_player`,
  `self._pack_input`, `self._pack_backend`, `self._pack_enabled` each tick; sole `submit_frame`
  caller; autoloop safe-zero. These 3 separate attrs are what T7e must hot-swap (see C5).
- [confirmed] **load_pack** (`soundswitch_pack_loader.load_pack`) runs `verify_pack` then parses —
  it is **blocking filesystem work** and MUST run on the command thread, never in `_push_tick`.

## B. Exact command / status schema

### B1. Status (sanitized) — `pack_status_provider()` → dict
```json
{
  "available": true,
  "enabled": true,
  "backend": "pack",            // "pack" | "none" | "midi" | "disabled"
  "dry_run": false,
  "pack_loaded": true,
  "pack_sha12": "88a2e9484869", // first 12 of the already-public manifest/union sha; "" if none
  "frame_count": 12345,         // monotonic submit_frame count (PackOutputBackend), else 0
  "has_active_identity": true,  // bool only; never the UUID
  "last_command": "reload",     // echoes CommandReader.last_command (already non-sensitive)
  "last_error_class": "SoundSwitchPackVerificationError"  // exception CLASS name only, no message
}
```
**Forbidden in status (assert in tests):** any value containing `/`, a serial/`tty`/`cu.`/`COM`
token, `enttec`, `port`, an alias/device name, `pack_path`, `fixture_map`, or a raw exception message.

### B2. Commands — single `cmd: "set_soundswitch_pack"` with an `action`
```json
{"cmd": "set_soundswitch_pack", "action": "reload"}
{"cmd": "set_soundswitch_pack", "action": "backend", "backend": "pack"}   // "pack"|"none"|"midi"
{"cmd": "set_soundswitch_pack", "action": "enable", "enabled": false}      // bool
```
`parse_command` validation (validate-FIRST; reject ⇒ `ValueError` ⇒ `last_error`, NO state change):
- `action` ∈ {`reload`,`backend`,`enable`}; else reject.
- `backend` action requires `backend` ∈ {`pack`,`none`,`midi`}; else reject.
- `enable` action requires `enabled` is a real `bool`; else reject.
- unknown extra keys ⇒ reject (strict).
Dispatch in `handle_command`: `set_soundswitch_pack` → a single injected
`pack_command_callback(action, **kwargs)` that returns `(ok, detail)` like the existing callbacks.

## C. Safety invariants (Part C)
- C1 **No implicit hot-enable.** `reload` and `backend` actions NEVER enable pack mode if it was
  disabled; they only prepare/replace state. Output stays off until an explicit
  `enable enabled=true`. Conversely `enable enabled=false` immediately resolves output to ZERO/none.
- C2 **Validate-first / no partial swap.** Build + `verify_pack` the new pack and construct the new
  (unstarted) backend BEFORE touching the live one. Any failure ⇒ keep the OLD verified pack/backend
  (or, if none, force safe no-output / NoneBackend) and record `last_error`. Never a half-swapped
  state visible to the driver.
- C3 **Stop-before-start on the shared serial port.** The Enttec port can be opened only once, so a
  reload/backend swap that rebuilds the sender MUST stop the old sender (and old input) before
  starting the new ones. To avoid a window where the driver submits to a stopped sender, publish a
  safe NoneBackend bundle FIRST (driver → ZERO), THEN stop old → build/start new → publish new.
- C4 **Pack failure never falls back to MIDI.** On any pack build/start/reload failure the safe
  fallback is NoneBackend (ZERO), never MidiOutput — preserves DMX/MIDI mutual exclusivity and never
  opens IAC after pack was selected.
- C5 **Atomic cross-thread publish, no blocking work in `_push_tick`.** All blocking work (load_pack
  fs read, sender serial open/close) runs on the CommandReader thread. The driver reads pack runtime
  state once per tick. **Refactor the three `self._pack_*` attrs + `_pack_enabled` into one immutable
  bundle object published via a single atomic attribute assignment** (`self._pack_runtime = new`), so
  the driver always sees a consistent (player,input,backend,enabled) snapshot — never a mix of old
  player + new backend. The command thread only ever assigns that one reference.
- C6 **disabled / none / dry_run opens no MIDI or serial.** `enable=false`, `backend=none`, and
  dry-run never construct a MidiOutput or open the Enttec port.
- C7 **Sanitized status only.** No raw paths, serial ports, device aliases, fixture maps, UUIDs, or
  raw exception messages cross the status surface (B1).
- C8 Autoloop stays safe-zero (T7d blocked) regardless of backend/enable.
- C9 Default-off neutrality preserved: absent/disabled pack config behaves exactly like the old MIDI
  path; `set_soundswitch_pack` is inert (callback None) when no pack runtime exists.

## D. Test plan (`tests/test_soundswitch_pack_commands.py` + status tests)
Pure/seam tests; NO real MIDI/serial/Enttec/network. Fake sender/backends record start/stop/submit.
1. status sanitization: provider output contains none of the forbidden tokens (B1) across enabled,
   disabled, none, dry-run, and post-error states (parametrized substring assertions).
2. `parse_command` accepts the three valid forms; rejects bad `action`, bad `backend`, non-bool
   `enabled`, extra keys ⇒ `ValueError`, and proves NO callback fires on reject.
3. enable: `enabled=false` ⇒ driver output ZERO/none; `enabled=true` on an already-built+verified
   runtime ⇒ output resumes. Reload/backend alone do NOT enable (C1).
4. reload success: new verified pack swapped in atomically; old workers stopped before new started
   (assert call order on the fakes); driver sees the new pack.
5. reload failure (verify raises): old verified pack retained; `last_error_class` set; output never
   half-swapped; if no old pack, output forced NoneBackend/ZERO.
6. backend swap pack→none ⇒ no MIDI/serial opened, output ZERO; none→pack rebuilds via stop-before-
   start; pack failure ⇒ NoneBackend fallback, NEVER MidiOutput (C4).
7. stop-before-start ordering + safe-gap: a NoneBackend is published before old stop; assert the
   driver never submits to a stopped sender.
8. atomic publish: concurrent-ish read (call driver between swap phases) only ever sees a consistent
   bundle (old-complete or new-complete), never mixed.
9. no blocking I/O in `_push_tick`: the swap path runs on the command thread; a driver tick during a
   swap performs no fs/serial/MIDI (monkeypatch open/socket/serial to fail).
10. autoloop still safe-zero under every backend/enable combination (no `select_autoloop`).
11. default-off neutrality: no pack runtime ⇒ `set_soundswitch_pack` is inert; existing behavior
    byte/order-identical.

## E. Acceptance criteria
- [ ] Status provider + `_safe_pack_status` wired; D1 proves zero sensitive leakage.
- [ ] `parse_command` validate-first for all three actions; D2 proves reject-without-side-effect.
- [ ] reload/backend/enable implemented with C1–C9 held; D3–D11 green on **3.11 and 3.14**.
- [ ] No new blocking I/O in `_push_tick`; pack runtime published as one atomic bundle.
- [ ] Hard checks pass; update `docs/subsystems/soundswitch_output.md` + `runtime_commands.md` +
      the relevant change-contracts; proof gate PASS; CI `unit` green; ledger updated.
- [ ] Status stays SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## F. Adversarial self-review
- "Reload mid-show double-opens the Enttec port" — prevented by C3 stop-before-start + publishing a
  NoneBackend during the gap. VERIFY `SoundSwitchFrameSender.stop()` fully releases the port before
  the new sender opens (check the sender's close/join semantics during impl).
- "Driver reads a half-swapped (old player + new backend) state" — prevented by C5 single-reference
  atomic bundle. The current 3-attr layout (shipped in T7c) MUST be migrated to the bundle, or the
  swap is unsafe; this migration is in-scope for T7e.
- "A failed reload silently enables a broken pack" — prevented by C1 (no implicit enable) + C2
  (validate-first, old retained).
- "Pack failure falls back to MIDI and double-drives lasers" — prevented by C4 (NoneBackend only).
- "Status leaks the serial port / live config path" — prevented by C7 + D1 forbidden-token asserts;
  note `enttec_port` and `midi_input_aliases` are the highest-risk fields.
- "enable=false leaves the last frame lit" — `enable=false` must publish a NoneBackend/disabled
  bundle so the driver submits ZERO (or stops submitting), not retain the last frame. Add to D3.
- "Blocking load_pack stalls the 200 Hz loop" — prevented by C5 (all blocking work on the command
  thread); D9 asserts no fs/serial in a driver tick.
