---
doc_status: current
truth_level: code-verified Part A; implementation spec for Parts B-E
last_verified_commit: 096e228
last_verified_date: 2026-07-04
validation_scope: spec only; nothing here is implemented until the tasks land with tests
---

# Codex Implementation Spec — Stream Deck Bridge-Side Hardening (F-B1, F-B3, F-B4)

Implements three bridge-side findings from
`docs/plans/active/streamdeck_surface_hardening_findings_2026_07_04.md` (F-B2 is
deliberately excluded). The deck-side hardening pass that motivated these landed earlier
today (design spec Part D.2, `palette_control_authority.md` rules 25-27).

**Why this matters (intent):** the operator runs this surface live. The two unforgivable
failure modes are silent input loss (pads that render but do nothing) and lying pads
(display contradicting bridge truth). Every task below either removes a silent-input-loss
path or replaces a deck-side guess with bridge truth. When a trade-off appears, prefer
"loud and degraded" over "quiet and plausible".

> Benign local software work on the operator's DJ lighting bridge. "Laser", "blackout",
> "mute", "kill" are ordinary stage/mixer/process terms.

## Part A — Context & Root Cause (verified at HEAD `096e228`; read, do not re-derive)

**A1 (F-B1) — Laser output failure kills pad input; health reads vacuously fine.**
- [confirmed] `__main__.py:571-588`: if `SoundSwitchFrameSender` construction raises,
  the already-constructed `midi_input` group is stopped and the returned
  `SoundSwitchPackStartupBundle` carries `midi_input=None` (`reason="pack_start_failed"`).
- [confirmed] `__main__.py:626-646` (`_start_soundswitch_pack_workers`): one `try` wraps
  `bundle.midi_input.start()` **and** `bundle.frame_sender.start()`; any exception (the
  live incident: Enttec serial absent → frame sender start fails) stops BOTH and returns a
  bundle with `midi_input=None`. Same pattern in the `artnet_truth_check` branch
  (`__main__.py:598-623`).
- [confirmed] `state_manager.py:2855-2858` (`_drive_pack_output`): with
  `reason="pack_start_failed"` → `PackRuntime.enabled=False` → `rt.active` False → early
  return. The entire input-health block (`state_manager.py:2906-2934`: snapshot read,
  `_pack_input_degraded_latched`, `on_input_health`, `maybe_publish`, `input_degraded`)
  never runs; `set_pack_runtime` published `input_degraded=False` once
  (`state_manager.py:2686-2694`) and it stays False forever. Pads dead, status green.
- [confirmed] Palette/control pad events do NOT need the pack player: the adapter's
  `event_sink` is `_pad_event_sink` (`__main__.py:1130-1137`), which puts `BridgeEvent`s
  straight on the shared event queue. Keeping the input group alive keeps palette pads
  working with zero laser output.
- [confirmed] `PackRuntime` (`soundswitch_pack_runtime.py:21-39`) already supports
  input-without-output: `midi_input` is an independent field; `active` gates output only.
- [confirmed] **Latent sibling:** the pack-reload path `_prepare_pack_runtime`
  (`__main__.py:1534-1559`) calls `_build_soundswitch_pack_startup(cfg_result)` with NO
  `event_sink` and NO `extra_midi_bindings` — a runtime pack reload/enable builds a new
  input group with no palette bindings and a `None` event sink, silently killing every
  palette/control pad until the next full bridge restart. `_pad_event_sink`
  (`__main__.py:1130`) and `palette_control_bindings` (`__main__.py:1114`) are both in
  scope at the definition site.
- [confirmed] Shutdown safety for a kept-alive group: `pack_output_owners["midi_input"]`
  is refreshed after worker start (`__main__.py:1150-1152`) and
  `_shutdown_zero_pack_outputs` stops both the live runtime's `midi_input` and the
  startup-owned slot (`__main__.py:1031-1057`).

**A2 (F-B3) — Static-look truth is not in the feedback file.**
- [confirmed] Held static layers live in `SoundSwitchMidiInputAdapter._layers` as
  `LayerEntry(slot, kind, seq)` (`soundswitch_midi_input.py:48-53`); the deck-side toggle
  latch is display-only double-tracking. The deck now persists latches across USB
  reconnects and clears them on feedback `seq` regression (deck pass, 2026-07-04), which
  closes the observed drift windows — but the deck still cannot *display* bridge truth.
- [confirmed] `LayerEntry` carries no binding identity (no channel/note), so the deck (which
  knows rows by channel+note) cannot map slots today. `_process_note_on/_process_note_off`
  have the full `PackMidiBinding` (fields: `device_name`, `message_type`,
  `channel_zero_based`, `data_byte`, `target_kind`, `target_slot`, `interaction`, …) in
  scope at layer creation (`soundswitch_midi_input.py:258-336`).
- [confirmed] `LedPaletteControl` already uses the pull-getter pattern for exactly this
  shape of fact (`get_laser_blackout`, `get_laser_solo` — `led_palette_control.py`
  constructor); `state_manager.py:~520` wires those lambdas at construction.
- [confirmed] `MidiInputSnapshot` is immutable and safe to read from any thread
  (`soundswitch_midi_input.py:56-67`, `snapshot()` at `:128-130`).
- [assumed] Propagation latency bridge→deck ≈ ≤1 s (event → publish → 0.1 s writer
  debounce → ≤0.5 s deck poll). The deck-side reconcile therefore needs a short local-echo
  grace window so a fresh local toggle isn't visibly reverted before bridge truth arrives.

**A3 (F-B4) — Watcher leaves the deck unsupervised and its kills look like USB faults.**
- [confirmed] `scripts/ss_bridge_watcher.sh:285-304` manual mode: `start_streamdeck` runs
  only in the `else` branch when `bridge_pids` is non-empty — during a bridge gap the deck
  script is never respawned; when the manual terminal closes, the watcher exits entirely
  after `stop_streamdeck` (observed 12-minute deck outage 2026-07-04 16:24→16:36).
- [confirmed] `stop_streamdeck` (`scripts/ss_bridge_watcher.sh:65-69`) pkills with no trace
  in `/tmp/streamdeck.log`; SIGTERM landing mid-`hid_write` produced the two
  `Failed to write out report (-1)` lines that masqueraded as USB flakiness (same-second
  `shutdown` lines prove intentional teardown).
- [confirmed] The script's `while true` main loop is top-level (`:285`), so it cannot be
  sourced by a test as-is.

**Concurrency warning (read first):** AWR-121 (palette gesture v2) is being implemented in
a parallel Codex session TODAY, touching `led_palette_control.py`,
`soundswitch_midi_input.py`, `state_manager.py`, `led_config.py`, and (later tasks)
`streamdeck/streamdeck_midi.py` + tests. The worktree may be dirty with its in-flight
changes, and `origin/main` may advance mid-run. This spec's task ORDER exists to keep you
out of its way: watcher first (zero overlap), F-B1 second (disjoint regions of shared
files), F-B3 last behind an explicit gate.

## Part B — Tasks (implement in order; commit after each task by pathspec)

### Absolute Rules
- Work directly on `main`. No branches, no worktrees, no PRs, never `git clean`, never
  force-push, never `git add -A`/`git add .` — **commit only the exact files you changed,
  by pathspec**. The worktree may contain other sessions' changes: never revert, stage, or
  "fix" files you did not change. If `origin/main` advances, rebase your own unpushed
  commits only.
- NEVER restart, kill, signal, or send input to any running process. The bridge and deck
  script are LIVE. No `pkill`, no bridge restarts, no MIDI/DMX/serial opens, no hardware
  probes. Software implementation + tests only; the operator does live verification.
- Do not touch: `laser_director.py`, `laser_executor.py`, `soundswitch_laser_player.py`
  rendering internals, `drop_presentation.py`, anything under `tools/ssfmt/`, any
  gesture-v2 (AWR-121) behavior you find mid-flight.
- Behavior that must not change: pack output rendering/values/timing on the happy path;
  RW-3/RW-4 overlay-trust semantics; blackout/emergency mask precedence; the 200 Hz push
  loop gains no blocking I/O; `Ev.*` event shapes already consumed elsewhere.
- Error handling: fail closed and loud. No broad try/except that converts failure into
  silence; no success-shaped fallbacks. In the push-loop path, exceptions must not escape
  (existing invariant) — degraded health on error, never healthy-by-default.
- If a task's Part A anchor has moved (AWR-121 landed something), re-locate by symbol
  name and adapt; if the SEMANTICS underneath changed (not just line numbers), STOP that
  task and report BLOCKED with what you found instead of guessing.

### Task 1 — `scripts/ss_bridge_watcher.sh`: attributable deck stops (F-B4)
Change `stop_streamdeck` to take a reason argument and write one line into the deck's own
log before killing, so an intentional stop can never masquerade as a device fault:
```bash
stop_streamdeck() {
    streamdeck_running || return 0
    printf '%s [watcher] stopping streamdeck reason=%s\n' \
        "$(date +%Y-%m-%dT%H:%M:%S)" "${1:-unspecified}" >> "$STREAMDECK_LOG"
    pkill -f "$STREAMDECK_PAT" 2>/dev/null
    log_watcher "stopped streamdeck reason=${1:-unspecified}"
}
```
Update every call site with a concrete reason: `manual_terminal_closed`, `bridge_stop`,
`watcher_exit` (the `cleanup` trap), matching the surrounding branch.

### Task 2 — `scripts/ss_bridge_watcher.sh`: respawn the deck during bridge gaps (F-B4)
In the manual-mode branch (`:286-304`), move `start_streamdeck` so it runs on every
iteration that is not about to `exit` — including when `bridge_pids` is empty (the bridge
gap is exactly when the deck script most needs supervision; the deck script itself renders
the degraded state loudly since today's deck pass). Do not change the exit conditions
themselves (deck still stops when the watcher exits — operator-overridable decision,
keeps the device released for the Elgato app).

Also wrap the top-level main loop in a testability guard so the file can be sourced:
```bash
if [ -z "${WATCHER_NO_LOOP:-}" ]; then
while true; do
    ...existing loop unchanged...
done
fi
```
Default behavior identical (`WATCHER_NO_LOOP` unset in production).

### Task 3 — `tests/test_ss_bridge_watcher.py`: first coverage for the watcher (F-B4)
New test file. Source the script with `WATCHER_NO_LOOP=1` under `bash -c`, with a temp
dir prepended to `PATH` containing stub `pgrep`/`pkill`/`osascript`/`date` executables and
`STREAMDECK_LOG` pointed at a temp file (override via env or `sed` the constant — prefer
making `STREAMDECK_LOG="${STREAMDECK_LOG:-/tmp/streamdeck.log}"` overridable in Task 1's
edit). Assert at minimum:
1. `stop_streamdeck some_reason` writes a `[watcher] stopping streamdeck reason=some_reason`
   line into the log file when the stub `pgrep` reports the deck running.
2. `start_streamdeck` is a no-op when the stub reports it running, and spawns (records the
   command) when not.
Keep it to function-level checks; do not simulate the loop.

### Task 4 — `__main__.py`: output construction failure keeps the input group (F-B1)
In `_build_soundswitch_pack_startup`'s except block (`:571-588`): stop only
`frame_sender`; KEEP the constructed (never-started) `midi_input` in the returned bundle:
```python
return SoundSwitchPackStartupBundle(
    None, pack, player, midi_input, None, "pack_start_failed",
)
```
(If the `midi_input_factory` call itself raised, `midi_input` is still `None` here and the
bundle correctly carries `None`.) Log line stays, same reason string.

### Task 5 — `__main__.py`: start input and output independently (F-B1)
Rewrite the `reason == "pack"` start block of `_start_soundswitch_pack_workers`
(`:626-646`) as two independent try blocks:
- `midi_input.start()` fails → stop midi_input, continue with `midi_input=None`; still
  attempt `frame_sender.start()`; if the sender starts, return a bundle with
  `reason="pack"` and `midi_input=None` (output without manual input is the existing
  degraded-controller mode; the group already logs its own unavailability).
- `frame_sender.start()` fails → stop frame_sender only; return
  `SoundSwitchPackStartupBundle(None, bundle.pack, bundle.player, <the live midi_input>,
  None, "pack_start_failed")`. **Do not stop midi_input.**
Apply the same input-survives change to the `artnet_truth_check` branch (`:598-623`):
`truth_sink.start()` failure stops the truth sink but keeps a successfully started
`midi_input` in the returned bundle.
Keep the existing `worker_start_failed` log lines on every failure path.

### Task 6 — `__main__.py`: pack reload keeps palette pads alive (F-B1, latent sibling)
`_prepare_pack_runtime` (`:1534-1559`): pass the same wiring startup uses —
```python
bundle = _build_soundswitch_pack_startup(
    cfg_result,
    event_sink=_pad_event_sink,
    extra_midi_bindings=palette_control_bindings,
)
```
Both names are in scope (defined `:1130` / `:1114`). Without this, a runtime pack
reload rebuilds the input group with no palette bindings and a None event sink.

### Task 7 — `state_manager.py`: input health runs even when output is disabled (F-B1)
Extract the input-health portion of `_drive_pack_output`'s midi block
(`:2906-2934` — snapshot read, `worker_alive`/`err`/`drops`, the
`_pack_input_degraded_latched` latch update, `input_healthy`, the
`self._led_palette_control.on_input_health(...)` + `maybe_publish()` calls, and the
`input_degraded` computation) into a helper, e.g.
`_update_pack_input_health(midi_input) -> bool` returning `input_healthy`. The ACTIVE path
calls it and then applies masks/layers exactly as today (zero behavior change in active
mode — the mask/layer application lines stay in `_drive_pack_output`).

Change the early return (`:2855-2858`) to:
```python
rt = self._pack_runtime
if rt is None or not rt.active:
    self._drop_presentation_base_live = False
    if rt is not None and rt.midi_input is not None:
        self._drive_pack_input_health_inactive(rt)
    return
```
where the inactive helper: calls `_update_pack_input_health(rt.midi_input)`; and when the
resulting `input_degraded` VALUE CHANGES from the last published pack status, republishes
pack status with the real value (reuse `_publish_pack_status` with
`runtime=rt, scripted_active=False, static_held=False, blackout=False,
autoloop_phase_blocked=False, software_zero_frame=True, input_degraded=<computed>`).
Publish only on change — the inactive path must not rebuild the status dict at the push
rate. Any exception inside the inactive helper: catch at the helper boundary, log once via
the existing `_pack_logged_error`-style latch pattern, and treat input as DEGRADED
(fail closed, never healthy-by-default). No new blocking I/O — `snapshot()` is an
immutable in-memory read; `maybe_publish` already runs on this thread in active mode.

### Task 8 — tests for F-B1
Extend `tests/test_state_manager_pack_driver.py` (or sibling test module if pack-driver
tests live elsewhere — reuse existing harness/fakes):
1. Bundle test (`__main__` seam): `_start_soundswitch_pack_workers` with a fake
   frame_sender whose `start()` raises → returned bundle has `reason="pack_start_failed"`
   AND the fake midi_input still present, `stop()` NOT called on it.
2. `_build_soundswitch_pack_startup` with a `frame_sender_factory` that raises →
   bundle keeps the constructed midi_input.
3. `_prepare_pack_runtime`-equivalent: assert `_build_soundswitch_pack_startup` is called
   with `event_sink`/`extra_midi_bindings` from the reload path (patch and inspect kwargs).
4. StateManager: runtime with `enabled=False` (`active` False) but a fake `midi_input`
   whose snapshot reports worker dead → after a tick, `get_pack_status()["input_degraded"]`
   is True and `LedPaletteControl.on_input_health` saw `False`; flip the fake back to
   healthy+quiet → status returns to False. Also: inactive helper exception → degraded,
   no raise into the tick.

### Task 9 — GATE, then `soundswitch_midi_input.py`: layers carry binding identity (F-B3)
**Gate before touching any F-B3 file:** run `git log --oneline -10` and `git status`.
If AWR-121 commits are still appearing (new commits touching `led_palette_control.py` /
`streamdeck/streamdeck_midi.py` within the last ~30 minutes) or those files are dirty in
the worktree, STOP here: commit Tasks 1-8, report Tasks 9-12 as BLOCKED-on-AWR-121, and
finish. Otherwise proceed.

Extend `LayerEntry` (`soundswitch_midi_input.py:48-53`) with defaulted identity fields so
existing positional constructions stay valid:
```python
@dataclass(frozen=True, slots=True)
class LayerEntry:
    slot: int
    kind: Literal["toggle", "press"]
    seq: int
    channel: int = -1   # zero-based MIDI channel of the binding that holds this layer
    note: int = -1      # data byte (note) of that binding
```
Populate both in `_process_note_on` (toggle and press branches) from
`binding.channel_zero_based` / `binding.data_byte`. `_process_note_off`'s press-release
match stays on `(slot, kind)` — unchanged semantics. Group `snapshot()` merge needs no
change (layers pass through).

### Task 10 — `led_palette_control.py` + `state_manager.py`: publish static-held truth (F-B3)
- `LedPaletteControl.__init__` gains `get_static_held: Callable[[], tuple] | None = None`
  (same pull pattern and placement as `get_laser_solo`). In `_publish_feedback`'s body
  dict add:
  ```python
  "static_held": [
      {"channel": int(c), "note": int(n), "kind": str(k)}
      for (c, n, k) in (self._get_static_held() if self._get_static_held else ())
  ],
  ```
  sorted by `(channel, note)` so body equality (the change-gate) is stable.
- `state_manager.py` at the `LedPaletteControl(` construction site (~`:520`; anchor:
  `get_laser_solo=lambda: self._drop_presentation_solo_feedback`): add
  ```python
  get_static_held=self._palette_static_held,
  ```
  with a new small method:
  ```python
  def _palette_static_held(self) -> tuple:
      rt = self._pack_runtime
      midi_input = getattr(rt, "midi_input", None) if rt is not None else None
      if midi_input is None:
          return ()
      try:
          layers = midi_input.snapshot().held_layers
      except Exception:
          return ()
      return tuple(
          (layer.channel, layer.note, layer.kind)
          for layer in layers
          if getattr(layer, "note", -1) >= 0
      )
  ```
  (Immutable snapshot read — safe from the publish path; empty on any doubt.)

### Task 11 — `streamdeck/streamdeck_midi.py`: render static latches from bridge truth (F-B3)
In the supervision loop (anchor: the `watch.observe(...)` call inside `main()`'s
`while not stop.is_set() and deck.connected()` loop), when the loaded feedback dict
contains `"static_held"`, reconcile the deck-local latch set:
- Build `bridge_held = {(int(r["channel"]), int(r["note"])) for r in feedback["static_held"]
  if isinstance(r, dict)}`.
- For every static-look row in the current layout whose `(channel, note)` disagrees with
  `active_keys` membership: adopt bridge truth (add/discard), EXCEPT keys the operator
  touched locally within the last 2.0 s (local-echo grace window — keep a small
  `dict[(channel, note) -> monotonic]` updated in `on_key`, passed into `make_on_key` the
  same way `active_keys` is). Feedback lacking the key (old bridge) → keep today's
  deck-local behavior unchanged.
- A reconcile that changes any latch adds those keys to the redraw set for that tick and
  logs one line (`"static latch reconciled from bridge: +N/-M"`) — transitions only, never
  per-tick.
Keep the seq-regression latch clear from the deck pass — it is the fallback when
`static_held` is absent; when `static_held` IS present, bridge truth simply repopulates on
the next tick (both mechanisms compose).

### Task 12 — tests for F-B3
1. `tests/test_soundswitch_midi_input.py` (extend): note-on toggle → snapshot layer
   carries `channel`/`note` of the binding; press layer likewise; note-off pops the press
   layer regardless of the new fields.
2. `tests/test_led_palette_control.py` (extend existing harness): construct
   `LedPaletteControl` with `get_static_held=lambda: ((2, 36, "toggle"),)` → payload
   contains `static_held == [{"channel": 2, "note": 36, "kind": "toggle"}]`; getter absent
   → `static_held == []`; payload change-gate fires when held set changes.
3. `tests/test_streamdeck_midi.py` (extend, reuse `FakeDeck`/`FakePort` real-caller
   harness): feedback with `static_held` containing a static row's note → after one
   supervision-style reconcile call the latch is set without any press and the key is in
   the redraw set; feedback flips to empty → latch cleared; a locally-pressed key inside
   the grace window is NOT reverted by a contradicting feedback tick; feedback without
   the `static_held` key → latches untouched. Factor the reconcile into a pure helper
   (e.g. `_reconcile_static_latches(layout, feedback, active_keys, recent_local, now) ->
   (changed_keys, messages)`) so these tests need no thread/loop.

### Task 13 — docs + contracts
- Contracts touched: `streamdeck_palette` (Tasks 4-12) and `bridge_menubar` (Tasks 1-3).
  Update every `docs_update` doc that is actually affected:
  - `docs/architecture/palette_control_authority.md`: extend rule 26/27 block with the
    static-held-truth rule (deck renders static latches from the feedback file when
    present; deck-local latch is echo + fallback only) — keep §10 status language.
  - `docs/plans/active/streamdeck_palette_control_design_spec.md`: short Part D.3 note
    (bridge-side hardening landed; what changed).
  - `docs/plans/active/streamdeck_surface_hardening_findings_2026_07_04.md`: mark F-B1,
    F-B3, F-B4 implemented (software-tested), F-B2 still open.
  - `docs/subsystems/led_govee.md` (streamdeck section), `docs/subsystems/runtime_commands.md`
    (only if a status string/command surface changed — `input_degraded` semantics note),
    `docs/status/active_work_registry.md` (AWR-119 row note),
    `docs/validation/software_test_inventory.md` (new watcher test file).
- Do NOT reprint or restate hardware claims: SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Part C — Invariants that MUST still hold (live safety)

1. The 200 Hz push loop gains NO file, HID, network, MIDI, or subprocess I/O; the inactive
   input-health path is in-memory snapshot reads + change-gated status publish only.
2. `_drive_pack_output` never raises into the tick; on any input-health exception the
   verdict is DEGRADED (fail closed), never healthy.
3. Active-mode pack behavior is byte-identical: masks, RW-3/RW-4 overlay trust, held
   Static Override semantics, blackout/emergency precedence, ZERO-on-error all unchanged.
4. An unhealthy controller still drops its manual overlay only; the scripted base stays up
   (operator policy 2026-06-24).
5. Events remain immutable after creation; reader/worker threads never mutate `DeckState`.
6. The deck script never blocks its supervision loop on the reconcile (pure in-memory set
   ops); the watchdog/reader-liveness guarantees from the deck pass stay intact.
7. Secrets/live config are never committed; watcher edits keep `RBSS_*` launch env
   byte-identical.

## Part D — Tests (summary)

Tasks 3, 8, 12 above. Every fix ships with the test that would have caught it. The F-B3
reconcile and the F-B1 health latch both get pure-function seams (no threads, files, or
devices). Suite baseline: establish it YOURSELF first (`python3 -m unittest discover tests`)
— parallel AWR-121 work may have moved it from 2916; record the number before your first
change and require net growth with zero new failures after.

## Part E — Acceptance (definition of done)

- [ ] All tasks 1-13 done, or 9-12 explicitly reported BLOCKED-on-AWR-121 per the gate.
- [ ] Full suite: no new failures vs your own recorded baseline; count grew.
- [ ] `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
      `python3 tools/check_docs_drift.py` — pass, EXCEPT any pre-existing failure you can
      show existed before your changes (name it in the report; do not fix other sessions'
      docs).
- [ ] `shellcheck scripts/ss_bridge_watcher.sh` no new warnings vs pre-change run (run it
      before and after; if shellcheck is not installed, note that and skip).
- [ ] Each task committed by pathspec with a message naming the finding
      (e.g. `F-B1: output start failure keeps MIDI input group alive`). No pushes beyond
      normal `git push origin main` after the suite is green; if origin advanced, rebase
      your own commits only.
- [ ] No process was restarted, killed, or signaled; no MIDI/DMX/serial port opened.

## When You Finish

Report: changed files per task; suite baseline → final counts; the three check results;
which docs were updated; anything BLOCKED and exactly why. Then a plain-language operator
summary: what now survives an Enttec failure, what a pack reload no longer breaks, what
the deck now displays for static looks, what he should press/watch to verify live
(bridge restart + pull the Enttec is HIS action, not yours), and the rollback note (all
changes are ordinary commits on main; no config or launch-env changes).
