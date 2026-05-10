# Laser Director Design Spec

Status: PROPOSED DESIGN — REFINED AGAINST CURRENT CODEBASE — CORRECTED FOR IMPLEMENTATION READINESS

Audience: AI coding agents, future maintainers, and implementation reviewers.

This document defines a proposed `Laser Director` subsystem for `rb_ss_bridge_v2`. It is written against the current architecture: `StateManager` is the single authority for deck/output policy state, consumes immutable `BridgeEvent`s, samples `PositionCache`, uses `LiveBPMService`, and drives SoundSwitch through `OS2LOutput`.

Laser Director adds a second output lane: MIDI commands mapped inside SoundSwitch to specific laser static looks and autoloops. MIDI does not replace OS2L. OS2L remains responsible for deck identity, BPM, elapsed time, beat position, play/loop state, scripted/autoloop activation, and normal SoundSwitch timing. MIDI is only the explicit laser-scene selection channel.

Implementation must treat code as the source of truth. If this document and current code conflict, update this document before implementing code.

---

## 1. Current Architecture Facts

The current bridge is a local macOS realtime daemon. It:

- Reads guarded direct Rekordbox state where available.
- Falls back to TimecodeLink and MTC where direct state is unsupported, stale, or not ready.
- Uses `StateManager` as the central authority thread.
- Publishes immutable `BridgeEvent`s into a queue.
- Samples direct position through `PositionCache`.
- Uses `LiveBPMService` where available.
- Sends VirtualDJ-shaped OS2L to SoundSwitch through `OS2LOutput`.
- Exposes operator status and commands through `/tmp/rb_ss_bridge_v2_status.json` and `/tmp/rb_ss_bridge_v2_commands.jsonl`.

Relevant current files:

- `__main__.py` wires startup, event queues, readers, `StateManager`, `OS2LConnection`, `OS2LOutput`, command/status helpers, validation, MTC, OSC, and direct readers.
- `state_manager.py` owns the 200 Hz event/push loop, `DeckState`, most `OutputState`, lighting mode decisions, Smart Drop, Smart Breakdown, Phrase Anchor, and SoundSwitch output calls.
- `models.py` defines `BridgeEvent`, `Ev`, `DeckState`, `TrackMetadata`, `PositionSnapshot`, `OutputState`, and related runtime models.
- `osl_output.py` owns OS2L TCP transport and VirtualDJ-shaped output helpers.
- `runtime_status.py` writes status JSON and tails the command JSONL file with a hardcoded command allowlist.
- `validation_runner.py` runs diagnostics against the bridge process, SoundSwitch connection, memory freshness, live BPM, autoloop/scripted state, and OS2L queue.
- `config.py` currently uses constants and environment flags; there is no existing general YAML config loader pattern.

---

## 2. Product Goal

Laser Director turns the bridge from broad scripted/autoloop arming into a realtime laser scene director.

```text
Rekordbox state + beat/phrase/drop/breakdown/transition context
    -> StateManager-owned LaserDirector policy
    -> MidiOutput bounded queue/thread
    -> IAC or MIDI port
    -> SoundSwitch MIDI mapping
    -> specific static laser look or laser autoloop
```

OS2L and MIDI have separate responsibilities:

```text
OS2L = deck/timing/playback identity and normal SoundSwitch timing
MIDI = explicit laser scene selection
```

---

## 3. MVP Goals

Laser Director MVP should:

1. Load and validate a laser scene mapping config at startup.
2. Start disabled by default unless explicitly enabled.
3. Support dry-run mode.
4. Support manual scene trigger by name.
5. Support latched emergency blackout and explicit blackout clear.
6. Support idle/no-output on stop, stale position, no loaded active track, scripted context, or autoloop-not-ready state.
7. Support simple automatic phrase/default scene changes.
8. Add Smart Drop / Smart Breakdown integration only after manual and phrase behavior are validated.
9. Publish Laser Director status to the existing runtime status JSON.
10. Add validation checks for config and MIDI transport.
11. Preserve all existing OS2L behavior when disabled or degraded.

### Scene banks (v1 live executor)

Per-personality role banks are optional and reference existing scene keys:

- `phrase_bank`
- `buildup_bank`
- `drop_bank`
- `post_drop_bank`
- `breakdown_bank`

Selection is deterministic round-robin per role (no random choice).
Missing/empty banks fall back to the existing single-scene role field.

Bank rotation happens only on role-entry / eligible trigger events:

- buildup: pick once at buildup entry; hold through countdown
- drop: rotate on each drop crossing
- post_drop: pick once per post-drop hold
- breakdown: pick once on breakdown entry
- phrase: trigger only on phrase/autoloop-eligible edges (not every tick)

Phrase MIDI must not fire immediately when post-drop expires. Returning to
phrase/default internally is allowed, but phrase-trigger MIDI waits for a real
phrase/autoloop boundary edge.

### Live execution path

Production path:

```text
LaserDirector -> LaserSceneExecutor -> MidiOutput -> IAC Driver Bus -> SoundSwitch
```

- `LaserDirector` remains policy-only (scene/reason/role decisions).
- `LaserSceneExecutor` owns bank rotation, scene lookup, execution gates, and
  `MidiOutput.trigger(...)`.
- `MidiOutput` is the only bridge MIDI sender path.

---

## 4. Non-Goals

MVP must not:

- Output DMX, Art-Net, or sACN directly.
- Replace SoundSwitch.
- Replace OS2L.
- Mutate `DeckState` outside `StateManager`.
- Block inside `StateManager._push_tick`.
- Perform MIDI I/O from `StateManager`.
- Perform file/config/status-dict work inside `StateManager._push_tick`.
- Require AI/audio classification.
- Require network access.
- Depend on Wireshark for local MIDI debugging.
- Add genre-tag personality resolution unless metadata ingestion is explicitly extended.

Use a MIDI monitor for local macOS IAC/USB MIDI debugging. Wireshark is useful for OS2L TCP inspection, not local MIDI.

---

## 5. Architectural Invariants

Implementation agents must preserve these invariants:

1. `StateManager` owns `DeckState` and output policy state.
2. Other threads publish immutable `BridgeEvent`s or snapshots; they do not mutate deck/output state.
3. `_push_tick` is a 200 Hz hot path. It must not perform file I/O, MIDI I/O, socket I/O, subprocess calls, blocking queue operations, status-dict construction, config loading, port scanning, or unbounded work.
4. Output transports own their own I/O threads and bounded queues.
5. Runtime commands that affect bridge state must enqueue `BridgeEvent`s.
6. Status JSON must be generated from snapshots/status methods, not live mutable objects.
7. MIDI failure must not crash or block OS2L behavior.
8. Config failure must disable Laser Director unless a future strict mode is explicitly added.
9. `LaserDirector.tick()` may mutate only Laser Director policy state and enqueue MIDI. It must not mutate `DeckState`, existing OS2L `OutputState`, or call `OS2LOutput`.
10. Laser Director disabled, unavailable, or degraded must preserve existing OS2L behavior except for additional status/logging.

---

## 6. High-Level Architecture

```mermaid
flowchart TD
    A[Rekordbox Direct Memory / TL / MTC] --> B[BridgeEvent Queue]
    B --> C[StateManager]
    D[PositionCache] --> C
    E[LiveBPMService] --> C
    C --> F[Existing Lighting State Machine / OS2L]
    C --> G[LaserDirector Policy]
    G --> H[MidiOutput Queue]
    H --> I[MIDI Sender Thread]
    I --> J[IAC / MIDI Port]
    J --> K[SoundSwitch MIDI Mapping]
    F --> L[OS2LOutput]
    L --> M[SoundSwitch OS2L]
    K --> N[SoundSwitch Static Looks / Autoloops]
    M --> N
    N --> O[Attribute Cues / DMX Lasers]
```

MVP module set:

```text
laser_models.py       -> frozen dataclasses/enums for scenes, MIDI messages, decisions, context, status
laser_config.py       -> load and validate Laser Director JSON config
laser_director.py     -> policy, timing gates, cooldowns, safety, manual override state
midi_output.py        -> non-blocking MIDI output queue/thread
```

Do not split `laser_safety.py`, `laser_cooldown.py`, or `laser_midi_router.py` until MVP complexity justifies it.

---

## 7. Data Models

Add Laser Director models in `laser_models.py`.

```python
@dataclass(frozen=True)
class LaserMidiMessage:
    kind: str  # "note_pulse", "note_on", "note_off", "cc"
    channel: int = 1
    note: int = 0
    velocity: int = 127
    cc: int = 0
    value: int = 0
    duration_ms: int = 80


@dataclass(frozen=True)
class LaserScene:
    name: str
    scene_type: str  # "static", "autoloop", "utility"
    safety_class: str  # "safe", "movement_low", "movement_medium", "movement_high", "high_impact", "strobe", "blackout"
    midi: LaserMidiMessage
    fallback_scene: str = "safe_static"
    cooldown_beats: float = 0.0
    immediate: bool = False


@dataclass(frozen=True)
class LaserPersonality:
    name: str
    safe_scene: str
    default_scene: str
    phrase_scene: str
    buildup_scene: str
    pre_drop_scene: str
    drop_scene: str
    post_drop_scene: str
    breakdown_scene: str
    transition_scene: str
    allow_high_impact: bool = False
    phrase_interval_beats: int = 32


@dataclass(frozen=True)
class LaserContext:
    active_deck: int
    playing: bool
    elapsed_ms: int
    bpm: float
    beatpos: float
    abs_beat: float
    phrase_beat_32: int
    phrase_beat_64: int
    position_stale: bool
    lighting_mode: str
    scripted_id: int
    filepath: str
    soundswitch_id: str
    personality: str
    smart_drops: tuple[int, ...]
    smart_breakdowns: tuple[int, ...]
    anlz_buildups: tuple[int, ...]
    current_phrase_is_up: bool
    current_phrase_is_chorus: bool
    next_drop_beat: int | None
    beats_to_next_drop: float | None
    in_breakdown: bool
    transitioning: bool
    master_recently_changed: bool
    manual_override_scene: str | None
    emergency: bool
    os2l_connected: bool


@dataclass(frozen=True)
class LaserSceneDecision:
    scene: str
    reason: str
    priority: int
    source: str
    allow_immediate: bool = False
    target_abs_beat: int | None = None
    blocked: bool = False
    blocked_reason: str = ""
```

Do not pass mutable `DeckState` into Laser Director except transiently inside the `StateManager` thread. Prefer building a frozen `LaserContext`.

### Context derivation requirements

Do not invent a second transition state machine. Derive context from current `DeckState`, `OutputState`, `TrackMetadata`, fresh position, and cached cheap status only.

Required initial derivations:

```text
in_breakdown = os.breakdown_active
transitioning = os.autoloop_arm_after_master_change or os.pending_autoloop_arm_meta is not None
master_recently_changed = now - os.last_arm_mono < ARM_GUARD_S and bool(os.autoloop_master_change_source)
smart_drops = tuple(active_deck.meta.smart_drops)
smart_breakdowns = tuple(active_deck.meta.smart_breakdowns)
anlz_buildups = tuple(active_deck.meta.anlz_buildups)
current_phrase_is_up/current_phrase_is_chorus are derived from the latest
semantic marker at or before `abs_beat` across:
  - UP markers: `active_deck.meta.anlz_buildups`
  - CHORUS markers: `active_deck.meta.anlz_drops`
  - LOW markers: `active_deck.meta.anlz_breakdowns`
If latest marker is LOW (or no marker exists), both booleans are false.
```

`_build_laser_context()` must not call `conn.status()` or any method that builds dictionaries, performs I/O, scans MIDI ports, reads files, or can grow in cost. If OS2L connectivity is needed in `_push_tick`, use a cached boolean or a dedicated constant-time `is_connected()` method.

---

## 8. Configuration

MVP uses JSON only. Do not add YAML or PyYAML in MVP.

Config path resolution:

1. If `RBSS_LASER_CONFIG` is set, read that path.
2. Otherwise read `<repo>/config/laser_director.json`.
3. Provide `config/laser_director.example.json` as the disabled-by-default sample.

`laser_config.py` should expose a result object similar to:

```python
@dataclass(frozen=True)
class LaserConfigResult:
    available: bool
    reason: str  # "ok", "not_configured", "invalid_config", "dependency_missing"
    config: LaserConfig | None = None
    errors: tuple[str, ...] = ()
```

Missing config is not an error: `available=False, reason="not_configured"`. Malformed config disables Laser Director and records validation errors; the bridge still starts.

MIDI dependency is an explicit Phase 0 decision. Recommended path: `mido` plus `python-rtmidi`, imported lazily inside `MidiOutput` so missing MIDI dependencies disable live MIDI without breaking dry-run/status/validation. If maintainers choose a different library, update this section before implementation.

Required validation:

- `enabled` and `dry_run` must be booleans; `dry_run` defaults to `true`.
- `midi_output_port` must be a non-empty string when live MIDI is enabled.
- Every scene must define a valid MIDI mapping.
- `note_pulse.duration_ms` must be clamped to a safe bounded range, recommended `10 <= duration_ms <= 250`.
- MIDI channel/note/CC/value ranges must be valid.
- Every personality scene reference must point to an existing scene.
- Startup, stop, stale, emergency, and fallback scenes must exist.
- Default personality must exist.

---

## 9. MIDI Output Design

Add `midi_output.py`, modeled after `OS2LConnection`.

Required API:

```python
class MidiOutput:
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def trigger(self, msg: LaserMidiMessage, *, priority: str = "normal") -> bool: ...
    def panic(self) -> None: ...
    def status(self) -> dict: ...
```

Rules:

1. Own MIDI I/O on a dedicated sender thread.
2. Use a bounded queue.
3. `trigger()` must use `put_nowait()` and return `False` if the queue is full.
4. Queue full increments `drop_count` and logs a summary warning.
5. MIDI library or port failure marks output degraded and returns `False`.
6. Dry-run accepts triggers and updates counters/status without sending MIDI.
7. `MidiOutput` never chooses scenes and never owns policy state.
8. Long note pulses must not delay emergency blackout. Either use a priority path for emergency/panic messages or schedule note-off events without blocking reads of higher-priority queue items.
9. Clamp `note_pulse.duration_ms` during config validation; do not allow arbitrary sleeps in the MIDI sender thread.

Status shape:

```json
{
  "enabled": true,
  "dry_run": true,
  "connected": false,
  "port": "IAC Driver Bus 1",
  "queue_size": 0,
  "queue_max": 256,
  "sent_count": 0,
  "drop_count": 0,
  "send_error_count": 0,
  "last_error": ""
}
```

---

## 10. LaserDirector Policy

Add `LaserDirector` in `laser_director.py`.

Responsibilities:

- Own Laser Director policy state.
- Evaluate `LaserContext`.
- Apply priority, safety, cooldown, manual override, and timing gates.
- Map selected scene to `LaserMidiMessage`.
- Enqueue MIDI through `MidiOutput`.
- Expose `status()`.

Priority order:

1. Emergency blackout.
2. Manual override.
3. Idle/no-output gate: not playing, no loaded active track, stale position, scripted context, or autoloop-not-ready.
4. Breakdown scene.
5. Drop crossing scene.
6. Post-drop hold scene.
7. Buildup countdown scene (Smart-Drop lookahead window).
8. Phrase-boundary scene.
9. Default scene.

Timing gates:

- Emergency blackout bypasses all timing/cooldown gates.
- Manual override bypasses normal timing gates.
- Idle/no-output uses `scene=""` and does not emit a visible scene selection.
- Automatic musical selection requires existing autoloop readiness from `StateManager` (`lighting_mode=="autoloop"`, no pending arm/re-arm, and matching armed filepath).
- Phrase/default timing must be subordinate to the existing autoloop tick/rearm lifecycle. Phrase-boundary decisions are emitted only when a real autoloop tick/rearm edge fires from `StateManager` (not from standalone continuous beat math).
- Scripted context (`scripted_id>0` or `lighting_mode=="scripted"`) must return idle/no-output.
- Normal scene changes respect `minimum_scene_hold_beats`.
- Normal scene changes occur only at configured phrase boundaries when `normal_changes_only_on_phrase_boundary=true`.
- Drop scenes may be immediate only when configured and position is fresh.
- `buildup_scene` is anchored to the next curated Smart Drop and is active only
  when all are true:
  - `0 < beats_to_next_drop <= buildup_lookahead_beats` (default 32)
  - current phrase context is UP (`current_phrase_is_up`)
  - current phrase context is not CHORUS (`not current_phrase_is_chorus`)
  unless a higher-priority gate wins.
- `anlz_buildups` contributes to phrase context derivation in `StateManager`;
  `LaserDirector` must not use raw `anlz_buildups` as a direct trigger.
- Multiple Smart Drop anchors inside one CHORUS section must not cause repeated
  buildup triggers.
- `pre_drop_scene` is intentionally inactive in policy. Smart Drop already
  handles final pre-drop autoloop cut/rearm behavior.

Cooldown state is updated only after `MidiOutput.trigger()` accepts the message. If a desired scene is blocked by cooldown or safety, choose the configured fallback scene and record the blocked reason in status/logs.

---

## 11. StateManager Integration

Modify `StateManager.__init__` minimally:

```python
def __init__(..., live_bpm=None, live_bpm_follow=None, laser_director=None, os2l_connected_provider=None):
    self._laser_director = laser_director
    self._os2l_connected_provider = os2l_connected_provider
```

`os2l_connected_provider`, if supplied, must be constant-time and must not build a status dict. Prefer adding `OS2LConnection.is_connected()` over calling `conn.status()` from `_push_tick`.

`LaserDirector` policy state can live inside `LaserDirector`, but it must only be mutated from the `StateManager` thread after startup. Do not mutate it from command/status/MIDI threads.

Add event handling in `_handle_event`:

```python
elif ev.kind == Ev.LASER_TOGGLE:
    self._laser_director.toggle_enabled()
elif ev.kind == Ev.LASER_SET_ENABLED:
    self._laser_director.set_enabled(bool(ev.payload["enabled"]))
elif ev.kind == Ev.LASER_SCENE:
    self._laser_director.set_manual_override(
        str(ev.payload["scene"]),
        float(ev.payload.get("ttl_s", 4.0)),
    )
elif ev.kind == Ev.LASER_BLACKOUT:
    self._laser_director.set_emergency_blackout(True)
elif ev.kind == Ev.LASER_CLEAR_BLACKOUT:
    self._laser_director.clear_emergency_blackout()
elif ev.kind == Ev.LASER_CLEAR_SCENE_OVERRIDE:
    self._laser_director.clear_manual_override()
elif ev.kind == Ev.LASER_SET_PERSONALITY:
    self._laser_director.set_personality(str(ev.payload["personality"]))
```

The no-payload `LASER_TOGGLE` must be a true toggle. It must not default to `enabled=True`. Use `LASER_SET_ENABLED` for explicit state.

Add `LaserContext` construction in `_push_tick` after active deck, play state, elapsed, BPM, beat position, absolute beat, lighting mode, Smart Drop, and Smart Breakdown state are known.

```python
if self._laser_director is not None:
    ctx = self._build_laser_context(...)
    self._laser_director.tick(ctx, now=time.monotonic())
```

`tick()` must be bounded and non-blocking. It must not call `OS2LOutput`, mutate current lighting state, or suppress/replace Smart Drop, Smart Breakdown, Phrase Anchor, scripted, autoloop, BPM, beat, elapsed, or idle OS2L sends.

Cross-transport ordering note: OS2L and MIDI use separate queues/threads, so enqueueing MIDI before an OS2L beat is best-effort only. If strict alignment is required later, add measured lead/offset configuration.

---

## 12. Event Model

Add to `models.py`:

```python
LASER_TOGGLE = "laser_toggle"
LASER_SET_ENABLED = "laser_set_enabled"
LASER_SCENE = "laser_scene"
LASER_BLACKOUT = "laser_blackout"
LASER_CLEAR_BLACKOUT = "laser_clear_blackout"
LASER_CLEAR_SCENE_OVERRIDE = "laser_clear_scene_override"
LASER_SET_PERSONALITY = "laser_set_personality"
```

Manual commands must flow through `BridgeEvent`s, matching the existing Smart Drop / Smart Breakdown command pattern.

---

## 13. Runtime Commands

Extend `runtime_status.py`. Add `Callable` to its imports before adding more callbacks:

```python
from typing import Any, Callable, Optional
```

Allowed commands:

```text
toggle_laser_director
set_laser_director
laser_blackout
laser_clear_blackout
laser_scene
laser_clear_scene_override
laser_set_personality
```

These command paths are retained for compatibility, diagnostics, and controlled
testing. They are not the recommended live performer workflow.

Examples:

```json
{"cmd":"toggle_laser_director"}
{"cmd":"set_laser_director","enabled":false}
{"cmd":"laser_blackout"}
{"cmd":"laser_clear_blackout"}
{"cmd":"laser_scene","scene":"drop_hit","ttl_s":4}
{"cmd":"laser_clear_scene_override"}
{"cmd":"laser_set_personality","personality":"dubstep"}
```

Parser rules:

- `toggle_laser_director` accepts no implicit `enabled`; it toggles current state in `StateManager`.
- `set_laser_director.enabled` is required and must be boolean.
- `laser_scene.scene` must be a non-empty string.
- `laser_scene.ttl_s` must be finite numeric and clamped to `[0, 30]`; missing defaults to `4.0`.
- `laser_set_personality.personality` must be non-empty.
- Unknown keys may be ignored only if documented in tests.
- Actual scene/personality existence validation belongs in `LaserDirector`.

Live performer overrides and blackout should be handled directly in
SoundSwitch or through the normal external safety path. Keep bridge-side
`laser_scene`/`laser_blackout` compatibility behavior unchanged unless a
separate cleanup PR explicitly removes it.

`CommandReader` should not mutate `LaserDirector` directly. Add optional callbacks supplied by `__main__.py`; those callbacks enqueue `BridgeEvent`s. Callbacks should return `True` on enqueue success and `False` on queue-full/error so `CommandReader.status().last_error` can report failures.

---

## 14. Startup Wiring

Modify `__main__.py` near OS2L setup.

```python
laser_director = None
midi_output = None
laser_config_result = load_laser_director_config()

if laser_config_result.available:
    midi_output = MidiOutput(
        port=laser_config_result.config.midi_output_port,
        dry_run=laser_config_result.config.dry_run,
    )
    midi_output.start()
    laser_director = LaserDirector(
        config=laser_config_result.config,
        midi_output=midi_output,
    )

sm = StateManager(
    event_queue,
    pos_cache,
    output,
    live_bpm=live_bpm,
    laser_director=laser_director,
    os2l_connected_provider=conn.is_connected,  # add constant-time helper
)
```

Pass `laser_config_result`, optional `laser_director`, and optional `midi_output` to `StatusWriter` and `ValidationRunner`. On shutdown, stop `midi_output` if it exists. Missing config, invalid config, missing MIDI dependency, or missing MIDI port must not prevent OS2L startup.

---

## 15. Status JSON

Keep `schema: 1` unless maintainers intentionally bump the runtime status schema.

Always add top-level `laser_director` status. If absent or not configured:

```json
"laser_director": {
  "available": false,
  "enabled": false,
  "reason": "not_configured"
}
```

If invalid config:

```json
"laser_director": {
  "available": false,
  "enabled": false,
  "reason": "invalid_config",
  "errors": ["..."]
}
```

If available:

```json
"laser_director": {
  "available": true,
  "enabled": false,
  "dry_run": true,
  "current_scene": "safe_static",
  "last_scene": "",
  "last_reason": "",
  "last_trigger_abs_beat": 0,
  "personality": "house",
  "manual_override": null,
  "emergency": false,
  "cooldowns": {},
  "midi": {
    "connected": false,
    "port": "IAC Driver Bus 1",
    "queue_size": 0,
    "sent_count": 0,
    "drop_count": 0
  },
  "last_error": ""
}
```

Policy fields come from `LaserDirector.status()`. Transport fields come from `MidiOutput.status()`. Status collection is allowed in `StatusWriter`, not in `_push_tick`.

---

## 16. Validation

Extend `ValidationRunner` with optional Laser Director dependencies:

- `laser_config_result`
- `laser_director`
- `midi_output`

Checks:

- `laser_config`: pass/warn/fail/not_applicable.
- `laser_safe_scene`: pass/fail/not_applicable.
- `laser_emergency_scene`: pass/fail/not_applicable.
- `laser_personality_refs`: pass/fail/not_applicable.
- `laser_midi_dependency`: pass/warn/not_applicable.
- `laser_midi_port`: pass/warn/not_applicable.
- `laser_midi_queue`: pass/warn/not_applicable.

Missing config should be `not_applicable`, not failure. Disabled config should be `not_applicable`, not failure. Invalid config should be reported by `laser_config` but must not fail bridge startup. Live MIDI unavailable should warn/degrade Laser Director only; OS2L checks remain independent.

---

## 17. Safety Rules

Defaults:

- Startup: dry-run unless explicitly configured live.
- Stopped deck: idle/no output.
- Stale position: idle/no output.
- Unknown active deck: idle/no output.
- RB restart: clear manual override/cooldowns and trigger safe scene if live enabled.
- Transition/master switch: block high-impact/strobe scenes.
- OS2L disconnected: idle/no output unless explicitly allowed.
- MIDI unavailable: mark degraded; do not affect OS2L.
- No track playing: idle/no output (`scene=""`).
- No loaded active track: idle/no output (`scene=""`).
- Scripted context (`scripted_id>0` or `lighting_mode=="scripted"`): idle/no output (`scene=""`).
- Automatic musical selection requires autoloop readiness from existing bridge state.

Emergency blackout remains latched for compatibility with existing runtime commands. `laser_blackout` sets `emergency=True` and immediately triggers the configured emergency scene. `laser_clear_blackout` sets `emergency=False`, clears any manual scene override, and triggers the configured safe scene before returning to automatic policy. `laser_clear_scene_override` clears only the manual scene override and must not clear emergency blackout.

Emergency blackout bypasses all timing and cooldown gates. TTL-based emergency blackout is out of scope for MVP unless this section is updated first.

---

## 18. Personality Resolution

MVP deterministic priority:

1. Runtime personality override.
2. Track profile by SoundSwitch ID.
3. Track profile by exact filepath.
4. Folder/path contains rules.
5. Default personality.

Do not implement genre-tag resolution in MVP because current `TrackMetadata` does not contain genre or laser personality fields. Add genre/tag support only if metadata ingestion is extended.

---

## 19. SoundSwitch Setup Workflow

1. Enable IAC Driver on macOS.
2. Create or select a dedicated IAC bus, for example `IAC Driver Bus 1`.
3. Configure SoundSwitch to listen to that MIDI input.
4. Map MIDI notes to static looks/autoloops.
5. Mirror those mappings in `config/laser_director.json`.
6. Use a MIDI monitor app to verify note pulses.
7. Use bridge logs/status JSON to confirm scene decisions.
8. Keep `dry_run=true` until command, status, and validation behavior are verified.

Examples only — actual scene names are arbitrary config keys.

Example mapping table:

| Scene | MIDI | SoundSwitch Mapping |
|---|---:|---|
| `safe_static` | note 36 | Laser static safe look |
| `house_phrase_1` | note 37 | House phrase autoloop |
| `house_buildup_1` | note 38 | House buildup autoloop |
| `house_pre_drop_1` | note 39 | House pre-drop tension/static look |
| `house_drop_1` | note 40 | House drop impact look |
| `house_drop_sustain_1` | note 41 | House drop sustain autoloop |
| `house_breakdown_1` | note 42 | House breakdown autoloop |
| `transition_safe_1` | note 43 | Safe transition look |
| `emergency_blackout` | note 44 | Emergency laser blackout |

---

## 20. Logging

Use summary-centric logs. Avoid per-tick spam.

Recommended log lines:

```text
[LASER] enabled  dry_run=true  midi_port="IAC Driver Bus 1"  scenes=9  personalities=2
[LASER] scene  safe_static→build_tunnel  reason=phrase_boundary_32  beat=96  deck=1
[LASER] scene  build_tunnel→drop_hit  reason=drop  beat=128  deck=1
[LASER] blocked  scene=drop_hit  reason=cooldown  fallback=drop_sustain  remaining_beats=32
[LASER] safe  scene=safe_static  reason=position_stale
[LASER] midi-send  scene=drop_hit  note=40  channel=1
[LASER] midi-unavailable  port="IAC Driver Bus 1"  action=degrade
```

Never log every tick. Scene/blocked/safe logs should be emitted on state transitions or rate-limited summaries only.

Same-scene reason updates are status/debug-only and must not look like a new scene transition. INFO-level `scene` logs should represent only true scene-name changes.

---

## 21. Implementation Phases

### Phase 0: Config and dependency decision

- Use JSON for MVP.
- Add `laser_config.py`.
- Add `config/laser_director.example.json` with disabled-by-default and dry-run defaults.
- Add `RBSS_LASER_CONFIG` path override.
- Decide and document MIDI dependency.
- Add config validation tests.

### Phase 1: MIDI Output MVP

- Add `laser_models.py` and `midi_output.py`.
- Implement dry-run, bounded queue, status, logging, queue full handling, dependency-missing degradation, and note pulse.
- Validate unavailable MIDI does not affect OS2L.

### Phase 2: Manual Scene Trigger and Emergency

- Add Laser `Ev` constants.
- Extend `runtime_status.py` parser/allowlist.
- Add callbacks in `__main__.py` that enqueue `BridgeEvent`s.
- Handle Laser events in `StateManager._handle_event`.
- Implement true toggle, explicit set-enabled, manual scene override, latched emergency blackout, clear-blackout, and clear-scene-override.

### Phase 3: Automatic Phrase Scenes

- Add `LaserDirector.tick(ctx, now)`.
- Build `LaserContext` in `StateManager._push_tick` using only hot-path-safe values.
- Trigger default/phrase scenes with minimum hold and phrase gates.
- Use idle/no-output (`scene=""`) on stopped/stale/no-track/scripted/autoloop-not-ready state.

### Phase 4: Status and Validation

- Add Laser Director status to status JSON.
- Add validation checks.
- Add no-config, invalid-config, disabled, dry-run, dependency-missing, and MIDI-unavailable tests.

### Phase 5: Smart Drop / Smart Breakdown Observation

- Observe `TrackMetadata.smart_drops`, `TrackMetadata.smart_breakdowns`, `TrackMetadata.anlz_buildups`, and `OutputState.breakdown_active`.
- Do not mutate or replace existing Smart Drop / Smart Breakdown state machines.
- Compute next drop and beats-to-drop from current absolute beat.
- Initial windows:
  - `buildup_scene` when `0 < beats_to_next_drop <= buildup_lookahead_beats` (default 32).
  - `drop_scene` when absolute beat crosses the target smart-drop beat once.
  - `post_drop_scene` holds until minimum hold or next phrase boundary.
  - `breakdown_scene` follows `os.breakdown_active`.
- Add cooldown fallback behavior.
- Suppress high-impact scenes during transitions.

### Phase 6: Personality Profiles

- Add runtime personality override.
- Add profiles by SoundSwitch ID, filepath, and folder contains.
- Leave genre-tag resolution for a later metadata expansion.

---

## 22. Testing Plan

### Unit tests

- Config loading and validation.
- Missing config -> unavailable/not_configured.
- Invalid config -> unavailable/invalid_config without startup failure.
- Scene reference validation.
- Personality reference validation.
- MIDI value range and duration clamp validation.
- `MidiOutput` dry-run behavior.
- `MidiOutput` queue full/drop behavior.
- Emergency/panic priority or non-blocking note-off scheduling.
- Manual override TTL.
- Emergency blackout priority and latch.
- `laser_clear_blackout` clears emergency and returns safe.
- `laser_clear_scene_override` does not clear emergency.
- Stale/stopped/no-track/scripted idle-no-output selection.
- OS2L-disconnected safe gating.
- Cooldown fallback.
- Phrase-boundary gating.
- Runtime command parser acceptance/rejection, including queue-full callback failure.

### Integration tests

- Runtime command -> callback -> `BridgeEvent` -> `StateManager._handle_event` -> Laser Director state.
- `StateManager._push_tick` calls `LaserDirector.tick()` without blocking and without status-dict/config/MIDI I/O.
- Laser Director disabled leaves OS2L behavior unchanged.
- MIDI unavailable degrades Laser Director without crashing bridge.
- Status JSON always includes Laser Director status.
- Validation reports Laser checks as not applicable when disabled/not configured.

### Regression tests

- Existing Smart Drop toggle still works.
- Existing Smart Breakdown toggle still works.
- Existing OS2L queue/status behavior is unchanged.
- Existing status JSON keys remain present.
- Existing validation checks remain unchanged.
- Existing scripted/autoloop/idle OS2L sends are unchanged when Laser Director is disabled.

### Operational validation

1. Start with missing config; bridge should run normally.
2. Start with invalid config; bridge should run normally and mark Laser Director disabled/degraded.
3. Start with valid config and `dry_run=true`; decisions should log/status only.
4. Verify idle/no-output gating: not playing, no loaded active track, stale, scripted, and autoloop-not-ready all return `scene=""`.
5. Verify automatic musical branches run only when autoloop readiness is true.
6. Verify compatibility command paths (`laser_scene`, `laser_blackout`) only as internal/dev/test controls; do not treat them as the primary live workflow.
7. Enable MIDI monitor; switch `dry_run=false`; verify note pulse.
8. Confirm SoundSwitch mapping fires expected static/autoloop.
9. Disconnect OS2L; verify safe/degraded behavior.
10. Test queue pressure; verify drops log without blocking.

---

## 23. Migration, Rollout, and Rollback

Rollout:

1. Merge config/model/MIDI dry-run support first.
2. Validate status and command flow in dry-run, including idle/no-output and autoloop-readiness gating.
3. Validate automatic phrase/default selection while subordinate to existing autoloop readiness.
4. Add Smart Drop / Breakdown observation while preserving existing bridge behavior.
5. Keep compatibility command paths (`laser_scene`, `laser_blackout`) internal/dev/test only.
6. Enable live MIDI only after automatic policy readiness is validated.

Rollback:

- Send `set_laser_director enabled=false` or set `laser_director.enabled=false` in config.
- Restore `dry_run=true`.
- Remove/rename config file.
- Disable Laser Director wiring via an environment flag if one is added.

Rollback must not require OS2L changes.

---

## 24. Open Questions

1. Does SoundSwitch prefer note pulse, toggle, hold, or CC for each target mapping?
2. Can SoundSwitch mappings distinguish static looks and autoloops cleanly for all target scenes?
3. Which MIDI dependency will be used for live output: `mido` + `python-rtmidi`, or another library?
4. Should MIDI be allowed to send safe/blackout scenes while OS2L is disconnected?
5. What exact mapping table will be used in the operator's SoundSwitch show file?

Resolved MVP decisions:

- Config format is JSON for MVP.
- Emergency blackout latches until `laser_clear_blackout`.
- `toggle_laser_director` is a true toggle; `set_laser_director` handles explicit enabled state.

---

## 25. Documentation Cleanup Recommendation

This corrected document should become the canonical Laser Director feature design. Do not leave multiple equal implementation prompts.

Preferred cleanup:

1. Replace `docs/laser_director_design.md` with this corrected content.
2. Delete or stop using `docs/laser_director_design_refined.md` after replacement.
3. Update `docs/doc_index.md` to classify the canonical document as proposed feature design.

If both files are temporarily retained, add this banner to `docs/laser_director_design.md`:

```md
> Superseded: Do not implement from this file.
> Canonical Laser Director design is `docs/laser_director_design_refined_corrected.md`.
```

Add this to `docs/doc_index.md` if keeping all files temporarily:

```md
| `docs/laser_director_design_refined_corrected.md` | PROPOSED / CANONICAL FEATURE DESIGN | Corrected Laser Director implementation spec checked against current code. |
| `docs/laser_director_design_refined.md` | SUPERSEDED / DO NOT IMPLEMENT | Earlier refined spec; superseded by corrected command/safety/hot-path guidance. |
| `docs/laser_director_design.md` | SUPERSEDED / DO NOT IMPLEMENT | Older Laser Director proposal; retained only for history. Conflicts with refined config/module guidance. |
```

If replacing the original:

```md
| `docs/laser_director_design.md` | PROPOSED / CANONICAL FEATURE DESIGN | Laser Director implementation spec; not current runtime behavior until implemented. Must preserve `current_architecture.md`, `bridge_design.md`, and `runtime_invariants.md`. |
```

---

## 26. Reviewer Checklist

- [ ] Laser Director is disabled or dry-run by default.
- [ ] MVP config is JSON and has explicit path resolution.
- [ ] MIDI dependency is explicitly chosen and lazily imported.
- [ ] No MIDI/file/network/config/status-dict work occurs inside `StateManager._push_tick`.
- [ ] `MidiOutput` uses a bounded queue and sender thread.
- [ ] Long note pulses cannot delay emergency blackout.
- [ ] Runtime commands enqueue `BridgeEvent`s instead of mutating state directly.
- [ ] `toggle_laser_director` is a true toggle.
- [ ] `set_laser_director.enabled` is an explicit boolean set.
- [ ] Emergency blackout is latched until `laser_clear_blackout`.
- [ ] `laser_clear_scene_override` does not clear emergency blackout.
- [ ] New `Ev` constants are added in `models.py`.
- [ ] `runtime_status.parse_command()` accepts and validates Laser commands.
- [ ] Command callbacks report queue-full failure to `CommandReader.status().last_error`.
- [ ] Laser policy state mutates only on the `StateManager` thread.
- [ ] `LaserDirector.tick()` does not call `OS2LOutput` or alter existing OS2L state machines.
- [ ] Laser disabled/degraded leaves OS2L behavior unchanged.
- [ ] Status JSON always includes top-level `laser_director`.
- [ ] Validation reports missing/disabled Laser Director as `not_applicable`.
- [ ] Regression tests cover Smart Drop, Smart Breakdown, OS2L, status JSON, and validation.
- [ ] Documentation index marks exactly one canonical Laser Director design.
