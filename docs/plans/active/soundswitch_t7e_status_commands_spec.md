# Implementation Spec — T7e SoundSwitch pack sanitized status + validate-first runtime commands

status: planned — **REVISION 2 (ChatGPT review corrections applied); ready to implement**
last_updated: 2026-06-22
implementer: Claude (Opus 4.8) — per operator override for this task (NOT Codex)
target branch/PR: `soundswitch/impl` / #116 (current head `212cb50`, CI green)

> Live-critical: T7e adds the operator's only hot path to reload/enable/swap the pack runtime, so a
> bad swap can blackout or double-open the Enttec serial port mid-show.
>
> **Revision 2** folds in the ChatGPT review of `212cb50`:
> 1. head metadata → `212cb50`;
> 2. **runtime `backend=midi` deferred** — `parse_command` accepts it syntactically but the callback
>    rejects it with a sanitized `unsupported_action`; no runtime command opens IAC/MidiOutput; pack
>    failure still falls back to NoneBackend only;
> 3. **callback-error sanitization** — pack-command failures must store only a sanitized class/category
>    in `CommandReader._last_error` (the generic `_invoke_callback` returns `f"{type}: {exc}"`
>    (`runtime_status.py:516`) which leaks paths/ports);
> 4. **physical zeroing** — `NoneBackend.submit_frame` is a no-op, so disabling/swapping must
>    explicitly `frame_sender.zero_and_stop()` the OLD sender, not merely publish NoneBackend;
> 5. T7c manual-static policy preserved verbatim.

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
- `backend` action requires `backend` ∈ {`pack`,`none`,`midi`}; else reject. (`midi` is accepted
  syntactically but **deferred at runtime** — see below.)
- `enable` action requires `enabled` is a real `bool`; else reject.
- unknown extra keys ⇒ reject (strict).
Dispatch in `handle_command`: `set_soundswitch_pack` → a single injected
`pack_command_callback(action, **kwargs)` returning `(ok, sanitized_detail)`.

**Runtime `backend=midi` is DEFERRED (C-mutual-exclusion):** the callback rejects it with a sanitized
`"set_soundswitch_pack: unsupported_action"` (no raw detail) and changes NO state. Runtime MIDI would
require a full MidiOutput/IAC-open + live `LaserSceneExecutor` backend-replacement lifecycle that T7e
does not implement. `midi` stays startup-config-only. **No T7e runtime command ever opens
IAC/MidiOutput**, and pack failure falls back to NoneBackend only (C4).

## C. Safety invariants (Part C)
- C1 **No implicit hot-enable.** `reload` and `backend` actions NEVER enable pack mode if it was
  disabled; they only prepare/replace state. Output stays off until an explicit
  `enable enabled=true`. Conversely `enable enabled=false` immediately resolves output to ZERO/none.
- C2 **Validate-first / no partial swap.** Build + `verify_pack` the new pack and construct the new
  (unstarted) backend BEFORE touching the live one. Any failure ⇒ keep the OLD verified pack/backend
  (or, if none, force safe no-output / NoneBackend) and record `last_error`. Never a half-swapped
  state visible to the driver.
- C3 **Stop-before-start on the shared serial port + physical zero.** The Enttec port can be opened
  only once, so a reload/backend swap that rebuilds the sender MUST stop the old sender (and old
  input) before starting the new ones. Order: validate/build new (unstarted) → publish a
  disabled/no-output bundle so the driver stops submitting to the old sender → **`old_sender
  .zero_and_stop()`** (physical CH1–CH19 zero THEN port release; `soundswitch_frame_sender.py:182`)
  and stop old input → start new (input first, sender second) → publish the new bundle.
  **`NoneBackend.submit_frame` is a no-op — publishing NoneBackend alone does NOT send a DMX zero;
  the explicit `zero_and_stop()` on the OLD sender is what darkens the rig.**
- C10 **Sanitized callback errors.** `set_soundswitch_pack` failures must NOT store the generic
  `_invoke_callback` detail (`f"{type(exc).__name__}: {exc}"`, `runtime_status.py:516`) — `{exc}` can
  contain paths/ports/aliases/verifier text. The pack dispatch stores only a sanitized
  class/category, e.g. `"set_soundswitch_pack callback failed: SoundSwitchPackVerificationError"` or
  `"...: pack_reload_failed"`, into `CommandReader._last_error`. No raw message reaches
  `CommandReader.status()`, `RuntimeStatusWriter`, or pack status.
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
Pure/seam tests; NO real MIDI/serial/Enttec/network. Fake sender records `submit`/`zero_and_stop`/
`stop` calls + order; fake backends record submit/shutdown. (ChatGPT minimum set, 1–14.)
1. `parse_command` accepts `reload`, `backend pack`, `backend none`, `enable true`, `enable false`.
2. `parse_command` rejects bad `action`, bad `backend`, non-bool `enabled`, extra keys ⇒ `ValueError`
   (and `backend midi` is accepted by parse but rejected at the callback — see 13).
3. rejected command invokes NO callback and mutates NO state.
4. `CommandReader` stores only a sanitized pack-command failure detail (class/category), never a raw
   `{exc}` message (C10) — assert no path/port/alias substrings in `CommandReader.status()`.
5. `RuntimeStatusWriter` pack status contains none of the forbidden substrings: `"/"`, `"tty"`,
   `"cu."`, `"COM"`, `"enttec"`, `"port"`, `"alias"`, `"device"`, `"fixture_map"`, `"pack_path"`, a
   raw UUID-like identity, or a raw exception fragment — across enabled/disabled/none/dry-run/error.
6. `enable=false` publishes a disabled/no-output runtime AND actively `zero_and_stop()`s the old
   sender/backend (assert the old sender received zero/stop before being discarded).
7. reload success: new pack built + `verify_pack`'d BEFORE the old runtime is touched, then published
   atomically; driver sees the new pack.
8. reload failure (verify raises): old verified runtime retained; if none exists, publishes safe
   no-output; never half-swapped; sanitized error only.
9. backend `pack→none`: old sender `zero_and_stop()`'d; opens NO MIDI/serial.
10. backend `none→pack`: follows stop-before-start; no partial swap.
11. driver tick during a swap sees either old-complete or new-complete bundle — never mixed
    player/backend/input (atomic single-reference publish).
12. no blocking I/O in `_push_tick` during swaps (swap runs on the command thread; monkeypatch
    open/socket/serial to fail; a driver tick must not hit them).
13. `backend midi` ⇒ callback rejects with sanitized `unsupported_action`; opens no IAC/MidiOutput;
    state unchanged.
14. default-off neutrality intact: no pack runtime ⇒ `set_soundswitch_pack` inert; existing behavior
    byte/order-identical. (Plus: no `select_autoloop` under any T7e command/status/backend — C8.)

## E. Acceptance criteria
- [ ] Frozen `_pack_runtime` bundle introduced; StateManager reads exactly one reference per tick;
      command thread publishes by assigning one new bundle.
- [ ] Status provider + `_safe_pack_status` wired; D4/D5 prove zero sensitive leakage (incl. errors).
- [ ] `parse_command` validate-first; D2/D3 prove reject-without-side-effect; `backend midi` deferred.
- [ ] reload/backend/enable implemented with C1–C10 held; D1–D14 green on **3.11 and 3.14**.
- [ ] No blocking fs/serial/MIDI/network/subprocess/sleep in `_push_tick`; old sender physically
      `zero_and_stop()`'d on disable/swap/failed-reload (not merely NoneBackend).
- [ ] Hard checks pass; update `soundswitch_output.md`, `docs/setup/runtime_commands.md`,
      `docs/subsystems/runtime_commands.md`, `feature_status_matrix.md`/validation docs as needed,
      and `change_contracts.yml`; proof gate PASS; CI `unit` green; ledger updated.
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
- "Status leaks the serial port / live config path" — prevented by C7 + D5 forbidden-token asserts;
  note `enttec_port` and `midi_input_aliases` are the highest-risk fields.
- "Status leaks via a callback error message" — prevented by C10 + D4; the generic `_invoke_callback`
  format `f"{type}: {exc}"` is NOT used for pack commands.
- "Publishing NoneBackend = dark rig" — FALSE: `NoneBackend.submit_frame` is a no-op, so the last
  physical frame stays lit until the OLD sender is `zero_and_stop()`'d. C3/C6 + D6/D9 require the
  explicit `zero_and_stop()` on disable/swap/failed-reload; the bundle swap alone is not enough.
- "Runtime backend=midi opens IAC and double-drives lasers" — prevented by deferring `backend=midi`
  (callback rejects, sanitized `unsupported_action`); no T7e command opens IAC/MidiOutput (D13, C4).
- "Blocking load_pack stalls the 200 Hz loop" — prevented by C5 (all blocking work on the command
  thread); D12 asserts no fs/serial in a driver tick.
