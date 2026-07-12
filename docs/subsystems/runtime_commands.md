---
doc_status: current
truth_level: code-verified
last_verified_commit: HEAD-2026-07-12-usb-worktree
last_verified_date: 2026-07-12
validation_scope: software-only; runtime command rail and slim source/frozen menubar inventory tested; frozen app and hardware behavior unvalidated
---

# Runtime Commands Subsystem

Status:
- implementation: alpha
- software-tested: partial / test inventory pending
- hardware-validated: no
- compatibility: local setup only

Purpose:
- Own local status snapshots, the throttled `[BEAT]` operator heartbeat, and append-only JSONL runtime command handling.

Reason-carrying LED blackout clear (AWR-154, 2026-07-08; implemented, software-tested, hardware-unvalidated):
- `led_clear_blackout` accepts an optional `reason` string. `parse_command()` validates it as
  non-empty when present and rejects any other unknown field; `CommandReader.handle_command()`
  parses it and passes it to the callback (present or `None`) instead of invoking a zero-arg
  callback. Absent `reason` resolves to `None` end to end, and `__main__.py`'s `_led_clear_blackout`
  only adds `"reason"` to the `BridgeEvent` payload when it is truthy — a bare clear is byte-identical
  to before this change.
- Fixes a real defect: the LED Pad's `OwnershipGate.release()` sent a bare `led_clear_blackout`
  after taking ownership with `reason=led_pad`, so the pad's own blackout-owner claim in
  `led_dispatch_policy.py`'s `_led_blackout_owners` set could never be discarded (that discard line
  was already correct — `ev.payload.get("reason") or "legacy"` — it just never received the reason).
  `led_dispatch_policy.py` itself is unchanged by this fix.
- Superseded by AWR-155 below: bare-clear semantics changed from "clears only `legacy`" to
  "clears every owner" (operator-authority fail-open). The reason-threading plumbing described
  above (`parse_command`, `CommandReader`, `_led_clear_blackout`) is unchanged.

Fail-open bare LED blackout clear (AWR-155, 2026-07-08; implemented, software-tested, hardware-unvalidated):
- Executive-approved: a bare `led_clear_blackout` (no `reason`) is operator authority and now
  clears every blackout owner in `led_dispatch_policy.py`'s `_led_blackout_owners` set at once, not
  just `legacy`. A reasoned clear is unchanged — it still discards only the named owner, so machine
  surfaces (LED Pad, drop presentation, smart-drop) keep their own scoped clears (AWR-154's
  pattern).
- On the no-reason path, the handler snapshots the owner set, clears it, and emits one INFO outcome
  log (`[RGB] blackout-clear-all owners=...`) naming what was cleared — not a per-tick log, only on
  an actual bare-clear command. The reasoned path's discard line is byte-identical to before AWR-155.
- Accepted, not guarded against: a bare operator clear during a lasers-only solo window also clears
  the `drop_spotlight` owner and lights the LEDs mid-solo. That is the intended override — operator
  authority outranks the presentation window's hold. The window's own later release discard becomes
  a no-op on an already-empty set (`set.discard` on a missing element is always safe).
- This is a code change, not a runtime action: it takes effect at the next bridge start after the
  one it was written during. No restart, live-config edit, or strip-touching action was performed
  while implementing it.

Audit P1 (2026-07-03):
- `toggle_smart_drop` and `toggle_smart_breakdown` callbacks now report queue-full failures through
  the same explicit `False` path used by the laser/LED runtime callbacks.

Stream Deck palette control (Package 2, 2026-07-04):
- The `streamdeck_palette` contract adds LED palette debug/runtime commands that mirror the Stream
  Deck pad rail: `led_palette_queue`, `led_palette_override`, `led_palette_lock`,
  `led_palette_unlock`, and `led_rainbow_toggle`. They are software command surfaces only; accepted
  commands do not prove MIDI pad wiring, Govee output, or hardware-visible behavior.
- AWR-121 changes only the physical Stream Deck palette-pad gesture: tap toggles queue/unqueue and
  long-press takes-and-locks. The runtime commands remain explicit debug/control intents:
  `led_palette_override` still performs the one-track override path, `led_palette_lock` and
  `led_palette_unlock` stay separate commands, and the no-beat fallback for runtime override does
  not implicitly lock.
- LIGHTING ENGINE v2 F1 adds explicit command rails for the live engine latch and correction
  helpers: `led_engine`, `led_manual_override`, `led_manual_clear`, and
  `led_max_energy_toggle`. `led_palette_queue` / `led_palette_override` can also carry a v2 zone
  name (`GLACIER`, `DEEP_POOL`, `TWILIGHT`, `ION`, `VOLT`, `EMBERCORE`, or `NEUTRAL`) when the
  bridge is latched to v2. These are software control surfaces only; they do not prove Stream Deck
  hardware, Govee output, or room-visible behavior.
- `ValidationRunner._check_singleton()` derives the singleton result from one process count.

SoundSwitch pack-player boundary (T7c/T7e):
- T7c wires the pack player into `StateManager` (`_drive_pack_output`); T7e adds the
  `set_soundswitch_pack` runtime command (`action` = `reload`|`backend`|`enable`) and a sanitized
  `soundswitch_pack` status block. `parse_command()` validates the command (validate-first);
  dispatch routes to a `pack_command_callback` backed by `SoundSwitchPackController` on the command
  thread (all blocking load_pack/serial work off the push loop).
- **Sanitized only:** the `soundswitch_pack` status and any `set_soundswitch_pack` failure detail
  expose no paths, ports, aliases, device names, fixture maps, UUIDs, or raw exception messages.
- RW-5 makes the base runtime facts provider-free and has `StateManager` own the copied operational
  snapshot. `get_pack_status()` copies only that dict. `operational_state` is a display-priority enum;
  the companion booleans remain authoritative. `software_zero_frame` and `frame_count` mean rendered
  software zero and attempted normal software frames only, never confirmed serial/Enttec output or
  physical fixture darkness.
- The `soundswitch_pack.truth_check` diagnostic block is present for the temporary Art-Net
  retirement gate. When enabled it exposes run ID, universe, targets, sidecar path, U1 sequence,
  queue overflow/drop counts, send errors, sidecar errors, pack SHA, and CH1 fixture-map address.
  It is not a runtime command surface and does not imply physical output authority.
- The copied `soundswitch_pack.overlay_suppressed` diagnostic object is additive and stable. It
  explains SoundSwitch-connected ZERO suppression when held static, blackout, or degraded input was
  present; it does not change the ZERO output fields.
- Runtime `backend=midi` is **deferred** (callback returns sanitized `unsupported_action`); no
  runtime command opens IAC/MidiOutput; pack failure falls back to disabled/none, never MIDI.
- The menubar `Export from SS` workflow adds no command. After verified disk publication it reuses
  only `{"cmd":"set_soundswitch_pack","action":"reload"}` when the bridge is running and pack
  output is enabled, then waits for a fresh `soundswitch_pack.pack_sha12` match. That export/reload
  path never sends `enable`/`backend`, and a stopped bridge or disabled pack receives no reload
  command. The SoundSwitch-connection auto-switch (`_auto_set_soundswitch_pack()`) does send
  `set_soundswitch_pack action=enable`, with one bounded retry after a fresh disconnected
  `pack_start_failed`; there is still no implicit hot-enable without a real pack backend + Enttec
  port and no manual pack button.
- The menubar bridge toggle launches the canonical repo watcher at
  `scripts/ss_bridge_watcher.sh`. Menubar UI state is only a control surface; it
  does not prove watcher or bridge process health.
- The current menubar is intentionally small. `MENU_BLUEPRINT` is pure data and
  one walker builds it. Both editions have the Bridge On/Off control, **Open
  Live Log**, a **Status** submenu with exactly four disabled rows (Bridge,
  Rekordbox, Lasers, LEDs), and a **Laser Safety** submenu containing
  **EMERGENCY: Stop All Lasers** and **Resume Lasers**. The safety actions keep
  their existing `laser_blackout` / `laser_clear_blackout` command behavior.
- The source/main-Mac edition additionally has exactly four operator tools:
  **Laser Pad…**, **LED Pad…**, **SoundSwitch Export…**, and **Rebuild USB
  Bridge…**. The first two live under **Tools**. The frozen/foreign-Mac edition
  hides all four. SoundSwitch status, deck rows, check status, smart-phrasing
  status/menu, Laser Director menu, Record Session, Test the Lights, normal
  Health Check, and the Rekordbox target-patch action/status are absent from
  both editions. The detailed facts remain available in the live log and
  status JSON; removing menu items does not remove their runtime commands.
- **Restart Menubar** replaces Quit everywhere. It launches a fresh menubar
  after a short delay and closes only the old menubar process; it does not stop
  or restart the bridge. There is no ordinary Quit item. Child start failures
  are captured under the normal bridge log directory and surfaced through a
  native alert instead of failing silently.
- A DMG/translocated frozen copy inserts one primary native action at the top:
  **Install on This Mac…**, **Update This Mac…**, or **Retry Installation…**,
  selected from the complete/incomplete install records. A DMG-run copy cannot
  start the bridge; it says to install or update first. A complete installed
  frozen copy offers **Purge RBSS Bridge…**. Install, update, retry, purge, and
  source **Rebuild USB Bridge…** all refuse while any owned or adopted bridge
  process is still running. Install/update copies the app and managed payload
  to `~/Applications` and Application Support, then opens the installed menu;
  it never starts the bridge automatically. Purge is confirm-gated and removes
  only its recorded/allowlisted installed files plus the bridge's App Support
  and log roots before closing the removed app.
- **Open Live Log** uses frozen self-dispatch (`--run-log-viewer`) in a packaged
  app, so it does not require host Python. Frozen bridge start opens the same
  viewer automatically; the viewer has a stable Terminal marker and duplicate
  guard. This path is software-tested but the built, windowed PyInstaller app
  and Terminal interaction remain operator-unvalidated.
- A frozen installed menubar owns the packaged Stream Deck helper alongside the
  bridge. Starting the bridge starts or adopts exactly one helper through
  `/tmp/streamdeck_midi.lock`; stopping an owned or safely adopted bridge stops
  the helper first. **Restart Menubar** intentionally leaves both running, and
  the replacement menubar re-adopts them from their validated lock-file PIDs.
  A crashed helper is retried no faster than once every three seconds. Frozen
  bindings resolve as explicit `RBSS_STREAMDECK_BINDINGS` first, then
  `~/Library/Application Support/RBSS Bridge/streamdeck_midi_bindings.json`;
  source mode keeps the existing canonical-pack sibling sidecar. Helper output
  is appended to `~/Library/Logs/rb_ss_bridge/streamdeck.log`. These lifecycle
  paths are software-tested; physical Stream Deck behavior is unvalidated.

Authoritative code:
- `runtime_status.py`
- `validation_runner.py`
- callback wiring in `__main__.py`
- menubar caller in `scripts/bridge_menubar.py`
- watcher launcher in `scripts/ss_bridge_watcher.sh`

Key symbols:
- `STATUS_PATH`
- `COMMANDS_PATH`
- `StatusWriter`
- `CommandReader`
- `parse_command()`
- `CommandReader.handle_command()`

Runtime flow:
- `StatusWriter` periodically writes `/tmp/rb_ss_bridge_v2_status.json`.
- Each status snapshot includes a compact `heartbeat` block, and `StatusWriter` logs one throttled
  `[BEAT]` line with show deck, separate Rekordbox master deck, BPM, phrase, laser scene, LED look,
  color palette, and RGB health. Heartbeat/status must not report `master = active_deck`; `master`
  is present only when a current valid and non-stale `rb_master_deck` exists. A stale
  `rb_master_deck` can remain diagnostic in the StateManager snapshot with age/source, but heartbeat
  `master` is empty.
  This reads existing status/snapshot provider surfaces from the status thread; it does not run in
  the 200 Hz StateManager push loop.
- Optional status provider failures are fail-soft. The status JSON falls back to unavailable/provider
  error fields, and repeated provider-failure warnings are throttled so a persistent provider
  failure does not flood the live-watch stream.
- `CommandReader` creates/truncates `/tmp/rb_ss_bridge_v2_commands.jsonl` at startup with mode `0600`.
- Operators append one JSON object per line.
- `parse_command()` validates command shape and payloads.
- `CommandReader.handle_command()` invokes callbacks when wired.

Accepted commands:
- `run_validation`
- `toggle_smart_drop`
- `toggle_smart_breakdown`
- `toggle_laser_director`
- `set_laser_director`
- `laser_blackout`
- `laser_clear_blackout`
- `laser_scene`
- `laser_clear_scene_override`
- `toggle_record_session`
- `set_led_look_director`
- `led_scene`
- `led_blackout`
- `led_clear_blackout`
- `led_clear_scene_override`
- `led_palette_queue`
- `led_palette_override`
- `led_palette_lock`
- `led_palette_unlock`
- `led_rainbow_toggle`
- `led_engine`
- `led_manual_override`
- `led_manual_clear`
- `led_max_energy_toggle`
- `set_soundswitch_pack`

Detailed command table:
- `docs/setup/runtime_commands.md`

Tests:
- inspect `tests/` for runtime command parser/handler coverage
- `tests/test_runtime_status.py` covers the heartbeat payload, throttled log line, and fail-soft
  color-engine provider handling, including show-deck versus Rekordbox-master separation and the
  LIGHTING ENGINE v2 runtime command parser/callback rail.
- run `python -m unittest discover tests`
- run `python tools/check_docs_drift.py` after command changes

Change contract:
- If `parse_command()` changes, update this file and `docs/setup/runtime_commands.md`.
- If callback wiring changes, inspect `__main__.py` and update this file.
- If status/command paths change, update README, setup docs, and drift checks.

Known risks:
- Accepted command names do not prove callbacks are wired.
- Callback success does not prove hardware-visible behavior.
- A matching `pack_sha12` proves the running status snapshot references the published content; it
  does not prove fixture-visible output or hardware safety.
- `software_zero_frame=true` does not prove a zero packet was sent or accepted. Sender health is not
  part of RW-5, and a stale menubar status is shown as `Lighting: no status yet`.
- Runtime command docs are code-derived; if docs and `runtime_status.py` disagree, code wins.
