# Codex Implementation Spec — Stream Deck MIDI controller: robustness + bridge autostart

Status: **Phase 1 ready for Codex.** Phase 2 is **blocked** on 3 verifications (see Part F) — do not implement Phase 2 yet.

The Stream Deck script already exists and works as a MIDI controller (15 pads → notes 36–50 on
MIDI channel 3). This spec hardens it for unattended live use and makes the bridge own its
lifecycle. Phase 2 (toggle-mode sync to SoundSwitch static looks) is scoped but not yet handoff-ready.

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

### Task 3 — `streamdeck/streamdeck_midi.py`: supervisor loop (acquire / run / reconnect)
Replace the one-shot `main()` body with a supervisor loop so the controller survives "deck not present
yet", "Elgato app holds the device", and mid-run unplug/replug without crash-looping or spinning CPU.

```
def acquire_deck():
    # enumerate; for each handle try open()+reset()+set_brightness(60); return the first that
    # opens cleanly, else None. Catch StreamDeck.Transport.Transport.TransportError (and OSError)
    # — a busy device (Elgato app) or absent device must return None, not raise.

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
- The key callback (`make_on_key`) must wrap its body in `try/except (TransportError, OSError)`; on a
  transport error it logs and does nothing (the `deck.connected()` poll will catch the disconnect and
  drive reconnect). It must never raise out of the library's reader thread.
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

streamdeck_running() { pgrep -f "streamdeck_midi.py" > /dev/null 2>&1; }

start_streamdeck() {
    streamdeck_running && return 0
    "$PYTHON" "$STREAMDECK_SCRIPT" >> "$STREAMDECK_LOG" 2>&1 &
    log_watcher "started streamdeck pid=$!"
}

stop_streamdeck() {
    streamdeck_running || return 0
    pkill -f "streamdeck_midi.py" 2>/dev/null
    log_watcher "stopped streamdeck"
}
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

## Part F — Phase 2 (NOT ready — toggle-mode sync to SoundSwitch static looks)

**Requirement (operator):** If a Stream Deck pad is mapped to a SoundSwitch **static look**, the pad
must follow that look's SoundSwitch **press vs toggle** trigger mode. For a toggle-mode look, the pad
press must drive the toggled state (and the pad LED should reflect on/off). The SoundSwitch exporter
must make this mode available to the bridge/controller.

**What already exists [confirmed]:**
- The exporter/loader already models per-binding mode: `PackMidiBinding`
  (`soundswitch_pack_loader.py:39-53`) carries `message_type`, `channel_zero_based`, `data_byte`
  (the note), `target_kind` (incl. `"static_look"`), and `interaction: Literal["press","toggle"]`.
- `ResolvedControlBinding.interaction_mode` (`soundswitch_pack_models.py:260`) and
  `ControlLabelState.interaction_mode` (`:250`) carry the same. `DecodedSoundSwitchProject` exposes
  `static_looks` and `resolved_controls` (`:276`,`:283`). `MidiDevice.feedback_bytes` (`:231`) hints
  SoundSwitch may emit MIDI feedback (relevant to true state reflection — unconfirmed).

**Intended design (to be finalized after Part F verifications):**
- Keep the bridge out of the hot path: the exporter emits a small **binding table** artifact
  (per static-look binding: `channel`, `note`, `interaction`, look name/id) where the standalone
  controller can read it. The controller keys each pad by its own `(CHANNEL, note)`; if that matches a
  `target_kind="static_look"` binding with `interaction="toggle"`, the pad uses toggle behavior +
  on/off LED state; otherwise momentary (today's behavior). This adds **no** bridge-process code.

**Blocking unknowns — verify before writing the Phase 2 task list (analysis = Claude's job):**
1. [unknown] **SoundSwitch toggle MIDI semantics** — does a toggle-mode look flip on each `note_on`
   (ignoring `note_off`), or need a specific sequence? Determines exactly what the controller emits
   in toggle mode. Verify against SoundSwitch behavior/docs.
2. [unknown] **Is `PackMidiBinding.interaction` actually populated from the SS project**, or does it
   default to `"press"`? Trace the decode path that sets it; confirm a real toggle look decodes as
   `"toggle"`.
3. [unknown] **Consumable artifact** — does the exporter already emit these bindings to a file the
   controller can read, or only build the in-memory immutable model? If in-memory only, Phase 2 must
   add a tiny JSON emit (channel, note, target_kind, interaction, name) and define its path/refresh.

**Live-safety note for Phase 2:** toggle state in the controller is a local guess of SoundSwitch's
state; without SoundSwitch→controller MIDI feedback it can drift (e.g., the same look toggled by
another control). Decide explicitly whether to (a) accept local-only state, or (b) consume
`feedback_bytes`/SoundSwitch MIDI-out for true sync — do not silently assume sync. This is
SoundSwitch-exporter / live-critical work and must be designed against the existing pack pipeline
(PR #116 lineage), plan-first, not bolted on.
