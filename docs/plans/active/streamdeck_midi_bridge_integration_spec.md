# Codex Implementation Spec — Stream Deck MIDI controller: robustness + bridge autostart

Status: **Phase 1 ready for Codex** — robustness fixes from the 2026-06-25 adversarial review are
folded in (flock fd-retention, anchored `pgrep`/`pkill`, broadened device-error catch, callback-wrap
shown in pseudocode). **Phase 2 (Part F) is revised and remains plan-first and GATED on Phase 1
execution + operator approval** — do not hand **Task 5 (the layered compositor)** to Codex until
Phase 1 has landed and the operator signs off on the open decisions named at the end of Part F. The
earlier "no remaining unknowns" claim was wrong and is retracted.

The Stream Deck script already exists and works as a MIDI controller (15 pads → notes 36–50 on
MIDI channel 3). Phase 1 hardens it for unattended live use and makes the bridge own its lifecycle.
Phase 2 adds a **generic layered DMX compositor** so pads mapped to static looks stack as overlay
layers (toggle = persistent, press = transient) over the live autoloop, following each look's
press/toggle mode — with **no Stream-Deck-specific code in the bridge** and the pad LEDs handled
locally by the controller. SoundSwitch is being retired to an authoring tool; the bridge is the
live runtime.

---

## Part A — Context & root cause (verified; read, do not implement)

- [confirmed] The controller lives at `rb_ss_bridge_v2/streamdeck/streamdeck_midi.py` (moved into the
  repo this session). `python3 streamdeck_midi.py --selftest` passes. Pads send `note_on` (vel 127)
  on press / `note_off` on release, **MIDI channel 3** (`CHANNEL = 2`), notes `NOTE_BASE=36`..50.
  Icons load from `streamdeck/icons/<padnum>.png` (path is `__file__`-relative).
- [confirmed] It creates its **own** virtual MIDI port named `"Stream Deck"` via
  `mido.open_output(PORT_NAME, virtual=True)`. The lasers use a different port (`IAC Driver Bus 1`,
  per `config/laser_director.json`) on MIDI channels 1–2. Channel 3 cannot collide with the lasers.
- [confirmed] The Stream Deck is a separate USB-HID device + separate MIDI port; it shares **no**
  resource with the bridge process. Launching it does **not** touch the bridge's 200 Hz push loop.
- [confirmed] `/opt/homebrew/bin/python3` (the `$PYTHON` the watcher uses) has `StreamDeck`, `mido`,
  `python-rtmidi`, and `Pillow` installed. The native `hidapi` lib is installed via Homebrew.
- [confirmed] **Robustness gaps in the current script:**
  - Only `signal.SIGINT` is handled. The watcher tears down with `pkill`/`kill` = **SIGTERM**, whose
    default action terminates Python **without** running the `deck.reset()/close()` + `port.close()`
    cleanup → deck left with stale images and the HID device may not be cleanly released, so the next
    launch can fail to grab it.
  - `main()` does `sys.exit(...)` if no deck is found. No retry → if the deck is unplugged at bridge
    start, or Elgato's app is holding it, the script dies and never recovers on hot-plug.
  - No mid-run disconnect detection: if the deck is unplugged while running, the library reader
    thread dies silently; the main thread blocks in `stop.wait()` forever (deck appears frozen).
  - No single-instance guard. Once the watcher launches it every loop iteration (Phase 1), a launch
    race or a stray manual run could open the device twice.
- [confirmed] Watcher `/Users/bbui/ss_bridge_watcher.sh`: `$PYTHON` line 11, `$BRIDGE_DIR` line 9.
  Two launch paths — `start_bridge()` (auto, line 52) and `start_manual_terminal_bridge()` (manual,
  line 86). Teardown: `stop_bridge()` (189), `kill_bridge_processes()` (43), and `cleanup()` (207)
  wired to `trap ... EXIT/INT/TERM` (211–212) so **every** exit path runs `cleanup`. Main loop:
  manual branch 215–230, auto branch 232–246, both `sleep 3`.
- [assumed] The operator runs the bridge in **manual mode** (menubar) per project notes, but this
  spec wires both modes so "starting the bridge" always runs the controller regardless of mode.

### Design decision (rationale)
Launch the controller from the **watcher (shell)**, not from inside the bridge Python. This keeps the
bridge process and its 200 Hz push loop free of any HID/MIDI/subprocess I/O (AGENTS §6 invariant),
reuses the watcher's existing process-lifecycle patterns, and lets the script self-heal device
flakiness independently. The script becomes a self-supervising long-lived process; the watcher only
ensures one instance exists while the bridge is up and kills it when the bridge stops.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Do **not** add any Stream Deck / HID / MIDI code to the bridge Python package (`rb_ss_bridge_v2/*.py`).
  The only files this phase touches: `streamdeck/streamdeck_midi.py` and `ss_bridge_watcher.sh`
  (root copy `/Users/bbui/ss_bridge_watcher.sh` is the live one).
- No behavior change to the bridge, lasers, LEDs, or SoundSwitch output.
- Keep `CHANNEL = 2` (MIDI channel 3). Do not change the note mapping or the laser channels.

### Task 1 — `streamdeck/streamdeck_midi.py`: handle SIGTERM and make shutdown clean
- Register the **same** stop handler for both `signal.SIGINT` and `signal.SIGTERM` so the watcher's
  `kill`/`pkill` triggers a graceful shutdown (deck reset + device released + port closed).
- Make every sleep/wait interruptible by the stop event (use `stop.wait(timeout=...)`, never
  `time.sleep`), so SIGTERM exits promptly instead of after a full retry interval.

### Task 2 — `streamdeck/streamdeck_midi.py`: single-instance guard
- At startup acquire a non-blocking `fcntl.flock` on `/tmp/streamdeck_midi.lock`
  (`fcntl.flock` confirmed available on macOS). If it's already held, log
  `"streamdeck_midi: another instance is running, exiting"` and `return` (exit 0). Hold the lock for
  the process lifetime. This makes the script idempotent regardless of how often the watcher calls it.
- **Retain the lock file object for the whole process lifetime** in a module-level global (e.g.
  `_LOCK_FILE = None`, then assign the `open(LOCK_PATH, "w")` handle to it). The lock lives on the open
  fd — if the handle is garbage-collected the kernel releases the lock while the process is still
  running, so a watcher relaunch could open the deck twice. Do **not** acquire on a throwaway
  `open(...)`; keep the object referenced. flock auto-releases on process death (crash included), so a
  crashed instance never permanently blocks the next launch — no stale-lock cleanup is needed.

### Task 3 — `streamdeck/streamdeck_midi.py`: supervisor loop (acquire / run / reconnect)
Replace the one-shot `main()` body with a supervisor loop so the controller survives "deck not present
yet", "Elgato app holds the device", and mid-run unplug/replug without crash-looping or spinning CPU.

```
def acquire_deck():
    # enumerate; for each handle try open()+reset()+set_brightness(60); return the first that
    # opens cleanly, else None. Wrap BOTH enumeration and open() in try/except Exception (broader
    # than TransportError/OSError): a busy device (Elgato app), an absent device, OR any USB-scan
    # error (e.g. a RuntimeError/HID error raised inside enumerate()) must return None, not raise.
    # Enumeration must never crash the supervisor loop.

def run():
    if not _acquire_singleton_lock():   # Task 2
        return
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    RETRY_SECONDS = 3
    while not stop.is_set():
        deck = acquire_deck()
        if deck is None:
            log("waiting for Stream Deck (absent or held by Elgato app)…")
            stop.wait(RETRY_SECONDS)
            continue
        port = None
        try:
            port = mido.open_output(PORT_NAME, virtual=True)
            for k in range(deck.key_count()):
                deck.set_key_image(k, render_key(deck, k, False))
            deck.set_key_callback(make_on_key(deck, port))   # callback wrapped in try/except
            log(f'"{PORT_NAME}" live — notes {NOTE_BASE}-{NOTE_BASE+deck.key_count()-1}, ch {CHANNEL+1}')
            while not stop.is_set() and deck.connected():     # deck.connected() confirmed to exist
                stop.wait(1.0)
        except (TransportError, OSError) as e:
            log(f"device error: {e} — will reconnect")
        finally:
            try: deck.reset(); deck.close()
            except Exception: pass
            if port is not None:
                try: port.close()
                except Exception: pass
        if not stop.is_set():
            log("Stream Deck disconnected — waiting for it to come back")
    log("streamdeck_midi: shutdown")
```
- The key callback (`make_on_key`) must wrap its **entire** body in `try/except (TransportError,
  OSError)`; on a transport error it logs and does nothing (the `deck.connected()` poll will catch the
  disconnect and drive reconnect). It must never raise out of the library's reader thread. Show it
  explicitly so it can't be missed:
  ```
  def make_on_key(deck, port):
      def on_key(_deck, key, pressed):
          try:
              port.send(key_to_message(key, pressed))
              deck.set_key_image(key, render_key(deck, key, pressed))
          except (TransportError, OSError) as e:
              log(f"key callback error: {e}")
      return on_key
  ```
- `log()` = timestamped line to stdout with `flush=True` (the watcher redirects stdout to a logfile).
- `import` `TransportError` from `StreamDeck.Transport.Transport` (confirmed import path), `fcntl`.
- Keep `note_for`, `key_to_message`, `render_key`, `_font`, and `selftest()` unchanged except as
  needed to pass `deck`/`port` into the callback. `# ponytail:` note the reconnect ceiling
  (poll-based detect at 1 Hz; event-based if a frozen-deck gap is ever observed).

### Task 4 — `/Users/bbui/ss_bridge_watcher.sh`: own the controller's lifecycle
Add near the config block (after line ~18):
```
STREAMDECK_SCRIPT="/Users/bbui/rb_ss_bridge_v2/streamdeck/streamdeck_midi.py"
STREAMDECK_LOG="/tmp/streamdeck.log"

# Anchor the match to the python interpreter so a bare `pgrep -f streamdeck_midi.py`
# can't match an editor with the file open, the watcher's own grep, or any other process
# that merely mentions the path. The [p] bracket also keeps the pattern from matching itself.
STREAMDECK_PAT="[p]ython3?.*streamdeck_midi\.py"

streamdeck_running() { pgrep -f "$STREAMDECK_PAT" > /dev/null 2>&1; }

start_streamdeck() {
    streamdeck_running && return 0
    "$PYTHON" "$STREAMDECK_SCRIPT" >> "$STREAMDECK_LOG" 2>&1 &
    log_watcher "started streamdeck pid=$!"
}

stop_streamdeck() {
    streamdeck_running || return 0
    pkill -f "$STREAMDECK_PAT" 2>/dev/null
    log_watcher "stopped streamdeck"
}
# ponytail: the backgrounded child becomes a transient zombie until bash reaps it on the next
# loop iteration — harmless here. Add an explicit `wait` only if accumulation is ever observed.
```
Wire-up (idempotent — `start_streamdeck` no-ops when already running, relaunches if the process died):
- **Start:** in the main loop, call `start_streamdeck` on every iteration where the bridge is
  confirmed up — i.e. in the manual branch when `bridge_pids` exists, and in the auto branch right
  after `ensure_bridge` when `ss_running` and `bridge_alive`.
- **Stop:** call `stop_streamdeck` inside `stop_bridge()` (covers auto-mode stop) **and** inside
  `cleanup()` (covers every exit path — EXIT/INT/TERM traps and the manual-mode `exit 0` branches),
  **and** in the manual-mode "manual terminal closed" branch (line ~217) next to
  `kill_bridge_processes`. Net effect: the controller runs exactly while the bridge runs, and is
  killed (deck reset via Task 1's SIGTERM handler) on every teardown.

---

## Part C — Invariants that MUST still hold (live safety)
- **No bridge-process change.** Nothing is added to any `rb_ss_bridge_v2/*.py`; the 200 Hz push loop
  gains no HID/MIDI/subprocess I/O (AGENTS §6). `pgrep -f rb_ss_bridge_v2 | wc -l` stays `1`.
- **Channel-3 isolation.** The controller stays on MIDI channel 3; it can never emit on the lasers'
  channels 1–2. Guarded by the selftest (Part D).
- **Clean device release on stop.** Every bridge-stop / watcher-exit path kills the controller and
  the deck is reset, so the device is free for the next launch. No orphaned controller process.
- **Single controller instance** (mirrors the "one bridge process" invariant) — flock + watcher pgrep.
- **Bridge independence.** The controller's failure (no deck, Elgato app, unplug) must never affect
  the bridge: it is a separate backgrounded process the watcher does not wait on.

## Part D — Tests
- `python3 streamdeck/streamdeck_midi.py --selftest` must stay green and additionally assert the
  **channel-safety property**: `CHANNEL not in (0, 1)` (i.e. MIDI channel ∉ {1,2}, the laser
  channels). This is the pure-function seam protecting the live-safety property.
- `bash -n /Users/bbui/ss_bridge_watcher.sh` must pass (syntax) after the edits.
- The reconnect/signal/flock paths are integration-level (need the device); cover them with the
  manual smoke in Part E rather than a framework test.

## Part E — Acceptance (definition of done)
1. `--selftest` green incl. the channel-safety assertion; `bash -n` clean.
2. Start the bridge (manual mode): exactly one `streamdeck_midi.py` process; the deck lights up with
   the pad numbers; `pgrep -f rb_ss_bridge_v2 | wc -l` == 1.
3. Stop the bridge (and separately: close the monitor terminal; and: `kill` the watcher): **zero**
   `streamdeck_midi.py` processes, and the deck is reset (blank/off).
4. Unplug the deck while running → `/tmp/streamdeck.log` shows it waiting/reconnecting, CPU stays
   low, the bridge is unaffected; replug → pads relight within a few seconds.
5. Launch with Elgato's Stream Deck app open → log shows it waiting on the busy device, no crash-loop.
6. No secrets/IPs/device-IDs committed; only the two files changed.

## When you finish
- Commit Phase 1 (Tasks 1–4) — message e.g. `streamdeck: SIGTERM+supervisor+single-instance; watcher
  autostart`. Report: selftest output, `bash -n` result, and the Part E smoke results you observed.

---

## Part F — Phase 2 (layered static-look compositor — bridge stays generic)

> **Correction (supersedes earlier drafts of this section).** Phase 2 is **not** "wire the Stream
> Deck into the existing engine, zero new bridge logic." The bridge's current static path holds
> **one** look and **replaces the whole frame** — it cannot stack or overlay. The real feature is a
> **new, generic layered DMX compositor** in the render path. It is still device-agnostic: it is
> driven by MIDI notes from any surface, with **no Stream-Deck-specific code or string in the
> bridge.** SoundSwitch is being **retired** to an authoring tool — the bridge is the live runtime.

**Requirement (operator), locked model:**
- **Base layer = the live autoloop/scripted frame.** Static looks stack *above* it.
- A static look is a **sparse per-channel patch**: a channel it does not set is **transparent**
  (falls through to the layer below); a channel it sets — **including an explicit 0** — overrides.
- **Toggle pad = persistent layer** (press flips it in/out of the stack). **Press pad = transient
  layer** (added on `note_on`, removed on `note_off`, reverting to whatever is beneath).
- **Stack order = execution recency** — newest on top, toggle or press alike; re-pressing a pad moves
  its layer to the top. **Topmost wins each channel. Nothing is auto-untoggled** (a toggle only
  changes when its own pad is pressed).
- **emergency/blackout > the whole stack** → black.
- **Hold / recovery [DECISION — operator must pick before Task 5 builds]:** the locked model wants a
  held layer to last until `note_off`/disconnect with **no** 2 s cutoff. But removing the 2 s
  `controller_hold_timeout_ms` (`soundswitch_pack_player_config.py:53`) is **only safe with a
  replacement backstop** — today that timeout is the *only* mechanism that ever releases a stuck
  layer: input-disconnect detection does **not** exist (`_make_real_source` never notices a vanished
  port, `soundswitch_midi_input.py:361-372`), and the dropped-note counter is **inert**
  (`_mail_drop_count` is initialized and read but never incremented, `:89,125`; the latch at
  `state_manager.py:3416` can therefore never fire). With no backstop, a single dropped `note_off`
  or a controller crash mid-press pins a static look on the rig **forever**. Task 5 must ship **one
  of**: (a) a long **press-only** watchdog (e.g. 30–60 s) that auto-releases a *transient* layer while
  leaving toggles persistent; (b) real input-disconnect detection (periodic `get_ports()` re-check or
  a controller heartbeat) that triggers the stack-clear; or (c) actually wire `_mailbox`/drop-count so
  the existing degradation latch can fire. **Also note:** the 2 s timeout currently gates
  **blackout-hold** auto-release too (`:114-117`) — whatever replaces it must preserve blackout
  auto-release.
- **Clear-on-disconnect [DECISION]:** "input surface disconnects → bridge clears the static stack" is
  required by the model but has **no detection seam today**. It is satisfied only if Task 5 adds the
  seam (option (b) above); it cannot be assumed to work for free.
- Bridge restart (operator: "never will") → controller blanks all LEDs and resets.

**What's confirmed in code [confirmed] — the gap is the whole feature:**
- **Single slot, full-frame replace, opaque** today: `LaserPackPlayer._active_static_slot: int|None`
  (`soundswitch_laser_player.py:186`); `resolve_frame` returns the static frame *instead of* base
  (`:153-163`); `render_static_look_frame` fills `[0]*19` so unset channels render **black, not
  transparent** (`:143-150`). The MIDI engine is likewise single-slot: `_held_static_slot`
  (`soundswitch_midi_input.py:222-277`).
- **The data already supports layering** [confirmed]: a look's `generic_attributes`
  (`soundswitch_pack_loader.py:586`) is a **sparse** list of `LoadedAttribute` rows
  (`dmx_channel`, `value`, **and `fixture_group`**) — "unset" = absent, "set to 0" = present with
  value 0. So transparency needs **no exporter change**; the renderer just discards the sparseness
  today. **Caveat [confirmed]:** the per-channel apply must replicate `_apply_attribute`'s filter —
  rows whose `fixture_group != PRIMARY_FIXTURE_GROUP` are **skipped** (`soundswitch_laser_player.py:78`).
  A naive `(channel, value)` patch that ignores `fixture_group` would write channels the engine
  intentionally drops. The render rules in Task 5 carry this filter.
- `interaction` (press/toggle) is already decoded from the `.ssproj`
  (`soundswitch_project_decoder.py:883-889`, `0=press/1=toggle`) and carried to
  `PackMidiBinding.interaction` (`soundswitch_pack_loader.py:296`).
- Generic MIDI input already exists and names no device: `SoundSwitchMidiInputGroup`
  (`soundswitch_midi_input.py:418`), wired in `__main__.py:444,495,541`, bound from
  `cfg.midi_input_aliases` (currently `{}`), matched generically (`_match_port_index`, `:357`).

### Tasks
### Task 5 — bridge: generic layered static-look compositor (the core; live-critical, plan-first)
Replace the single-slot static path with an ordered **layer stack**, driven generically by MIDI notes.
Today everything in this path is single-slot; every seam below must be widened (exact symbols named so
Codex builds with no guessing).

**State — in the MIDI→state engine (`SoundSwitchMidiInputAdapter`, generic, no device strings):**
- Replace the scalar `_held_static_slot` (`soundswitch_midi_input.py:83`) with an ordered list of
  layer entries `{slot, kind: toggle|press}` in recency order (newest last). `note_on` toggle → if
  `slot` present remove it, else push on top. `note_on` press → push a transient entry on top.
  `note_off` press → remove that `(slot, press)` entry; `note_off` toggle → ignore. **Re-press of a
  present toggle removes it** (it does **not** move to top — only a fresh push lands on top, so
  remove-then-re-press is how a toggle returns to the top). On input-port disconnect → clear the list
  (gated on the disconnect-detection DECISION above). Remove the 2 s `controller_hold_timeout_ms`
  cutoff **only together with** the chosen backstop (DECISION above).
- **Snapshot:** widen `MidiInputSnapshot` (`soundswitch_midi_input.py:47`) — replace the scalar
  `held_static_slot: int|None` with `held_layers: tuple[LayerEntry, ...]`, an **immutable tuple**
  ordered bottom→top. Build it by copying the engine list into a tuple **under `_lock`**; never hand
  the push loop a live list (anti-tear). `snapshot()` must become a **pure read** — move the current
  stale-clear *writes* (`:110-119`) out of `snapshot()` into the worker/backstop path so the 200 Hz
  loop never mutates engine state.
- **Group merge:** `SoundSwitchMidiInputGroup.snapshot()` collapses adapters to a single slot and
  raises `conflicting_static_holds` when >1 (`soundswitch_midi_input.py:508-525`) — structurally
  incompatible with a stack. Redefine it to concatenate each adapter's `held_layers` into one
  recency-ordered tuple and drop the single-slot conflict flag. (For a single controller this is just
  that adapter's tuple; the cross-device ordering rule is a DECISION — see end of Part F.)
- **Player API:** `LaserPackPlayer` is single-slot (`_active_static_slot`,
  `soundswitch_laser_player.py:186`; `hold_static`/`release_static`, `:234-245`). Add
  `set_static_layers(layers)` storing the ordered tuple; `reload()` (`:203-209`) must reset it to
  empty (slot indices are not stable across pack reload — see Part C reload invariant).

**Render — replace `resolve_frame` + `render_static_look_frame` (`soundswitch_laser_player.py:143-163`)
with a single pure function `apply_layers(base, layers, blackout, emergency) -> frame`:**
1. if `emergency or blackout`: return `ZERO_FRAME` (precedence **emergency/blackout > stack > base**,
   unchanged from `:161`).
2. start from a **copy of the base** autoloop/scripted frame — **never `[0]*19`.** Seeding a per-layer
   full frame is the transparency bug: it would black every channel the layer doesn't set and clobber
   the autoloop beneath.
3. for each layer **bottom→top**, apply only its set channels onto the working frame, **replicating
   `_apply_attribute`'s filter**: skip rows where `fixture_group != PRIMARY_FIXTURE_GROUP` (`:78`);
   for the rest write `frame[dmx_channel-1] = value` (explicit 0 overrides; an absent channel falls
   through to whatever is beneath). The topmost layer wins each channel it sets.
- **Per-layer error isolation [DECISION]:** a malformed look raises in apply today and `render()`
  fail-closes the **whole** frame to ZERO (`:145,371-372`). In a stack, pick: skip the bad layer and
  log (recommended — one corrupt look can't black the stage) **or** keep fail-closed. Choose one and
  test it.
- The render stays a **pure function** of (base, ordered layers, blackout, emergency); the 200 Hz push
  loop reads the immutable snapshot and calls it — **no I/O, no locks on the loop** (AGENTS §6).

**Degradation latch [DECISION]:** the push loop drops the entire overlay (`slot=None`) on any
`error`, `worker_alive` flap, or `new_drop` (`state_manager.py:3418-3428`). With a stack this blinks
**all** held layers off/on on a transient glitch. Restrict the drop-all to true
worker-death/disconnect; do not drop the stack on a transient `error` string. (Tie this to the
backstop/disconnect DECISION above.)

- **No Stream-Deck specifics.** Layers are keyed by learned binding `(device_name, channel, note)`
  → `static_look` slot. Optional generic add: list available MIDI input port names in runtime status.

### Task 6 — exporter: device-agnostic binding sidecar (build-time)
- If the pack form is not externally readable, have the **exporter** write `<pack_path>/midi_bindings.json`:
  a list of `{channel, note, target_kind, interaction, name}` for the project's learned bindings.
  Exporter output (the project's own bindings), names no device. The compositor itself reads the
  look's channel patches from the pack it already loads — the sidecar is only for the controller's LEDs.

### Task 7 — controller: local LED state from the sidecar (cosmetic; may diverge)
- Read the sidecar at startup; key each pad by `(CHANNEL, note)`. Toggle pad → track **local** on/off,
  flip per press, light when on. Press pad → momentary (today's flash). Adopt bound notes from the
  sidecar so pads auto-match the project (fallback to fixed 36-50). **No compositor logic in the
  controller.** Blank all LEDs on its own (re)start.
- **LED state is cosmetic and can diverge from the bridge stack — the earlier "correct by
  construction" claim is [confirmed false] and is retracted.** The controller is a separate process
  that sees only its own presses, not bridge-side clears. After a bridge stack-clear (input
  disconnect, pack reload) or a dropped `note_on`/`note_off`, a toggle's pad LED and the bridge's
  actual layer state can invert, so the next press does the opposite of what the operator expects.
  Acceptable for a cosmetic LED on a personal rig; recovery is a double-press to re-sync. The LED
  must **never** drive lighting. (If exact sync is ever wanted, add a bridge→controller state feed —
  out of scope here.)

### Part C additions (Phase 2 invariants)
- **No Stream-Deck string, code, or file emit in `rb_ss_bridge_v2/*.py`.** The compositor and MIDI
  input are generic; all device-aware logic lives in the controller + the device-agnostic sidecar.
- Compositor render is a **pure function** (base + layers + flags → frame); **no I/O on the push
  loop**; stack mutation is worker-thread only, read via immutable snapshot.
- Base = live autoloop/scripted; transparency via sparse patches; recency stack; topmost wins;
  **emergency/blackout overrides the whole stack**. Held layers release on `note_off` or input
  disconnect — never stick past the surface going away.
- Controller LED is local/cosmetic, never drives lighting, never emits on the lasers' channels.
- **Pack reload clears the stack.** On `on_pack_reload`/controller swap the engine clears the layer
  list and the player resets via `set_static_layers([])` — `static_look` slot indices are keyed by
  position (`soundswitch_pack_loader.py:582`) and are **not** stable across reload, so a carried-over
  layer would point at the wrong look. The controller blanks its LEDs on (re)start to resync.

### Part D additions (Phase 2 tests)
- **Pure-function compositor seam** (the core): given a base frame + ordered sparse layers (+ flags),
  assert: transparency (absent channel shows base/lower), explicit-0 override, topmost-wins on
  overlap, two disjoint toggles compose (Lego), press layer reverts on removal, blackout → ZERO_FRAME.
- Stack lifecycle: toggle add/remove, press add-on-`note_on`/remove-on-`note_off`, recency ordering,
  clear-on-disconnect — testable without hardware (feed raw messages, no port).
- Controller LED mapping is a pure function of `(sidecar, pressed-set)` — testable.

### Acceptance (Phase 2)
- No `streamdeck`/`Stream Deck` token under `rb_ss_bridge_v2/*.py` runtime code; bridge `pgrep` == 1.
- Two disjoint toggles → both render simultaneously (Lego). Overlapping toggles → topmost wins the
  shared channel, older keeps its other channels and stays lit. Press over a toggle → temporary
  override, reverts to the toggle/autoloop on release. Hold > 2 s persists. Transparent channels show
  the live autoloop. Blackout blacks the whole stack.
- Existing autoloop/scripted/blackout behavior unchanged when no static layer is active.

**Open decisions before Task 5 builds (operator must resolve — this retracts the earlier "no
remaining unknowns" claim):**
1. **Stuck-layer backstop** — press watchdog vs disconnect detection vs wiring the drop counter (Hold/
   recovery DECISION above). Live-safety critical: without one, a dropped `note_off` or a controller
   crash mid-press pins a look on the rig forever.
2. **Per-layer render-error isolation** — skip the bad layer (recommended) vs fail-closed to ZERO.
3. **Degradation-latch scope** — restrict the drop-all to true worker-death/disconnect.
4. **Cross-device layer ordering** in the group merge (trivial for a single controller; name the rule).

The only mechanical item is the Task 6 exporter hook site, which Codex locates in the pack-build path
(`soundswitch_pack_loader`/`soundswitch_pack_runtime`). Task 5 is the live-critical one — it replaces
`resolve_frame`/`render_static_look_frame`/`_active_static_slot`/`_held_static_slot` — and stays
**plan-first and GATED on Phase 1 execution + operator approval**: it must not start until Phase 1 has
landed and the operator has signed off on decisions 1–4.
