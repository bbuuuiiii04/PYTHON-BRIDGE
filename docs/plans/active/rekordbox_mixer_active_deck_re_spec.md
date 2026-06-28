---
doc_status: current
truth_level: code-verified planning spec
last_verified_commit: b1e5fd6
last_verified_date: 2026-06-28
validation_scope: static RE candidate scan plus implementation plan; raw offsets, decoded values, software behavior, and hardware behavior unvalidated
---

# Codex Implementation Spec - Rekordbox Mixer Active-Deck Authority

Status: ACTIVE SPEC. This is a plan and RE handoff, not proof of
implementation.

This project is separate from the SoundSwitch exporter / bridge-native DMX
runtime work. It must remain compatible with that work by preserving the rule
that SoundSwitch follows the bridge-selected `active_deck`. Do not redesign the
SoundSwitch exporter or direct-DMX runtime while implementing this project.

## Part A - Context & Root Cause (verified; read, do not implement)

- [confirmed] `DeckState` is the per-deck runtime state written by
  `StateManager`; it currently stores playing, elapsed, scripted id, and load
  generation, but no mixer fields.
- [confirmed] `OutputState.active_deck` currently exists as the push-loop
  active deck field.
- [confirmed] `Ev.MASTER_CHANGED` currently means "deck = new master (1 or 2)".
- [confirmed] `StateManager._handle_event()` sends `Ev.MASTER_CHANGED` directly
  to `_on_master_changed()`.
- [confirmed] `_on_master_changed()` writes `self._os.active_deck = new_deck`
  and resets lighting state.
- [confirmed] `RBStateReader._tick()` follows `offs.master_deck` and emits
  `Ev.MASTER_CHANGED` when the direct master byte changes.
- [confirmed] `__main__.py` makes direct master authoritative when
  `RBSS_MASTER_DIRECT=1` by adding `Ev.MASTER_CHANGED` to
  `authoritative_kinds`.
- [confirmed] OSC `/bridge/active_deck` and `/bridge/bridge_deck` still enqueue
  `Ev.MASTER_CHANGED` when direct master is not ready.
- [confirmed] `_push_tick_inner()` reads `active = os.active_deck` and uses that
  deck for timing, lighting, mirror routing, LED/laser context, and downstream
  output.
- [confirmed] Current playing-only auto-switch paths enqueue
  `Ev.MASTER_CHANGED` for the mirror deck when the active deck is stopped/idle
  and the mirror deck is playing.
- [confirmed] `_update_lighting()` derives scripted/autoloop/idle from the
  active deck's playing/scripted state.
- [confirmed] `_drive_pack_output()` reads `self._os.active_deck` and renders
  the pack from that deck.
- [confirmed] `SoundSwitchEngine.deck_route(active)` uses active deck plus
  mirror plus decks 3/4 for canonical fanout.
- [confirmed] `runtime_status._heartbeat_payload()` currently reports
  `"master": active_deck`.
- [confirmed] Rekordbox 7.2.11 is installed at
  `/Applications/rekordbox 7/rekordbox.app`.
- [confirmed] Static Ghidra import requires a thin architecture binary; Ghidra
  11.3.2 did not load the universal wrapper directly.
- [confirmed] A temporary arm64 thin binary was produced at
  `/tmp/rbss_re/rekordbox_7_2_11_arm64` from
  `/Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox`.
  Evidence: MD5 `f87084a7261547c0fe0c725291fa8c3e`, SHA-256
  `bfd71965fb23fb6dc88461de9bd39e371b34a6455faea89fd1e353ba1d03efbd`.
- [confirmed] Static symbols in the arm64 Rekordbox binary include likely
  mixer UI/input candidates:
  `ChannelFaderComp::eventAbsoluteValueChanged(djplay::DeviceObject*, int)` at
  `0x1000b5a90`,
  `EqControlComp::eventAbsoluteValueChanged(djplay::DeviceObject*, int)` at
  `0x1000b1a74`,
  `MixerControlComp::eventAbsoluteValueChanged(djplay::DeviceObject*, int)` at
  `0x1000b3ed8`, and
  `CrossFaderComp::eventAbsoluteValueChanged(djplay::DeviceObject*, int)` at
  `0x1000ba498`.
- [confirmed] Static symbols also include likely audio-engine sink candidates:
  `DjMixerUnit::setChannelFaderPosition(EMixerChannelLine_t, float)` at
  `0x1023e0a64`,
  `DjMixerUnit::setEqPosition(EMixerChannelLine_t, EEq_Iso_Band_t, float)` at
  `0x1023e0580`,
  `DjMixerUnit::setCrossFaderPosition(float)` at `0x1023e0d64`,
  `ChannelFader::setParameter(unsigned int, float)` at `0x1023ee5e0`, and
  `EqualizerNXS2::setParameter(unsigned int, float)` at `0x1023ebc3c`.
- [confirmed] The current static RE pass created a no-analysis Ghidra 11.3.2
  project at `/Users/bbui/Desktop/Ghidra Projects/Rekordbox Mixer RE` and a
  generated local decompiler dump at
  `/tmp/rbss_re/ghidra_candidate_dump.txt`. These are local RE artifacts, not
  committed repo evidence.
- [confirmed] GhidraMCP was not available as a callable Codex tool or running
  HTTP bridge in this session. Static Ghidra headless scripting was available
  and produced the candidate decompilation below. Any future MCP-assisted pass
  must report MCP availability separately instead of implying it was used.
- [confirmed] `ChannelFaderComp::eventAbsoluteValueChanged` validates the
  incoming device object against a stored component pointer near
  `this + 0x238`, converts the incoming integer to a normalized double with
  scale `6.103888176768602e-05`, stores a cached double near `this + 0x250`,
  and passes the value plus an id near `this + 0x248` toward a `DjEngine`
  singleton call target at `0x1007b4b08`. The id is a deck/channel candidate,
  not yet proven as Deck 1 vs Deck 2.
- [confirmed] `EqControlComp::eventAbsoluteValueChanged` checks three stored
  device-object pointers near `this + 600`, `this + 0x260`, and `this + 0x268`,
  maps them to band indexes `0`, `1`, and `2`, applies the same
  `6.103888176768602e-05` scale, stores cached per-band doubles near
  `this + 0x290 + band * 8`, and passes value, id near `this + 0x288`, and
  band index toward a `DjEngine` singleton call target at `0x1007b51cc`.
  Band index order is not yet proven to be low/mid/high.
- [confirmed] `MixerControlComp::eventAbsoluteValueChanged` has the same
  normalized-value shape, with a device pointer near `this + 0x268`, id near
  `this + 0x278`, cached double near `this + 0x280`, and call target
  `0x1007b4bfc`. This is a filter/mixer-control candidate, not active-deck
  authority proof.
- [confirmed] `DjMixerUnit::setChannelFaderPosition` bounds a channel index
  against an object vector near `this + 0x2c8..0x2d0`. When an active flag near
  `this + 0x2c0` is set, it dispatches through the selected channel object.
  Otherwise it stores the incoming float-like value into a per-channel state
  object from a pointer array near `this + 0x2b0`, at child offset `+0x1c`.
- [confirmed] `DjMixerUnit::setEqPosition` uses the same channel vector and
  active flag shape. Its inactive/pre-engine store writes band index `0` to a
  per-channel child offset `+0x8`, band index `1` to `+0xc`, and band index `2`
  to `+0x10`; other band indexes return an error. This supports a per-channel
  EQ state candidate but still does not prove low/mid/high order.
- [confirmed] `ChannelFader::setParameter` and
  `EqualizerNXS2::setParameter` identify downstream parameter slots and curve
  handling. They are useful contrast evidence, but they are not by themselves a
  bridge-readable live mixer pointer chain.
- [confirmed] `rekordcrate` is useful background for Rekordbox export/settings
  formats, but its `DJMMYSETTING.DAT` parser covers mixer preference settings
  such as channel-fader curve and crossfader curve, not live per-deck fader/EQ
  positions.
- [unknown] Rekordbox mixer memory locations for Deck 1/2 upfader, bass EQ, and
  filter are not decoded in current bridge code.
- [unknown] The static symbol candidates above are not yet proven to expose a
  stable heap object or pointer chain readable from the bridge.
- [unknown] The `DjMixerUnit + 0x2b0` child-state candidate has not been tied to
  a static base, object lifetime owner, or Mach-readable pointer path.
- [unknown] The UI component ids near `ChannelFaderComp + 0x248`,
  `EqControlComp + 0x288`, and `MixerControlComp + 0x278` have not been proven
  as Deck 1/Deck 2 ownership.
- [unknown] EQ band index order is not proven. Treat indexes `0`, `1`, and `2`
  as candidates only until passive proof maps one index to physical bass/low.
- [unknown] Exact raw values and stability behavior for physical fader/EQ/filter
  positions are not known until RE evidence exists.

Root cause: current bridge authority conflates Rekordbox master with the
show-driving active deck. The target behavior in
`docs/architecture/active_deck_authority.md` requires `active_deck` to mean the
audible/show deck selected by playing state, upfader position, bass EQ, and
Rekordbox-master tie/fallback behavior.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules

- Read `AGENTS.md` first in every implementation session.
- Treat `docs/architecture/active_deck_authority.md` as the authoritative target
  behavior contract.
- Do not restart the bridge without explicit live-operation approval in that
  implementation turn.
- Do not open MIDI, serial, DMX, Enttec, Govee, or lighting hardware during RE
  or software implementation.
- Do not run process-memory sampling or live capture without explicit approval
  in that implementation turn.
- Do not add a runtime feature flag. Fader/bass dominance is the default once
  implemented.
- Do not add a config/calibration file unless live evidence proves it is needed.
- Do not use real audio loudness, crossfader, trim/gain, channel mute, mid/high
  EQ, unrelated FX, or Decks 3/4 as authority inputs.
- Do not expand SoundSwitch exporter/direct-DMX runtime behavior except to
  preserve compatibility with the selected `active_deck`.
- The 200 Hz `StateManager` push loop must not gain blocking I/O.

### Task 1 - Static RE: Locate Mixer State Candidates

Use Ghidra + Ghidra MCP when available. If Ghidra MCP is unavailable, report
that directly before extending the RE work beyond the current static headless
Ghidra evidence.

Read current code first:

- `rb_offsets.py`
- `rb_state_reader.py`
- `rb_memory.py`
- `models.py`
- `state_manager.py`
- `runtime_status.py`
- `docs/subsystems/rekordbox_readers.md`
- `docs/architecture/active_deck_authority.md`

Static RE goals:

- locate Deck 1 and Deck 2 upfader state.
- locate Deck 1 and Deck 2 bass EQ state.
- locate Deck 1 and Deck 2 filter knob state if practical.
- decode mid/high EQ only after upfader, bass, and filter candidates are found.

Evidence rules:

- Do not assume mixer values are near existing deck transport values unless
  proven.
- Do not treat one coincidental candidate as proof.
- Record candidate chain/path, owning structure/function evidence, deck
  ownership evidence, and expected physical labels.
- Preserve unknowns explicitly.

Start from the current static candidate set:

- UI/control input side:
  `ChannelFaderComp::eventAbsoluteValueChanged`,
  `EqControlComp::eventAbsoluteValueChanged`,
  `MixerControlComp::eventAbsoluteValueChanged`, and
  `CrossFaderComp::eventAbsoluteValueChanged`.
- Audio-engine sink side:
  `DjMixerUnit::setChannelFaderPosition`,
  `DjMixerUnit::setEqPosition`,
  `ChannelFader::setParameter`, and `EqualizerNXS2::setParameter`.
- Current local static artifact, if still present:
  `/tmp/rbss_re/ghidra_candidate_dump.txt`.

For each candidate, decompile and answer:

- where the physical/control integer is converted to float or labeled state;
- how the owning deck/channel index is carried;
- whether Deck 1 and Deck 2 share one object array, two global slots, or a
  per-deck child object;
- whether the value is stored in readable object state before being applied;
- whether the value is UI-only, audio-engine-only, or a bridge-readable state
  owner.
- whether the candidate can be tied to a stable root pointer or must remain an
  internal-only clue.

If GhidraMCP is running, use only read/decompile/xref tools for this task:
`search_functions_by_name`, `decompile_function`, `get_function_xrefs`,
`get_xrefs_to`, `get_xrefs_from`, and `list_strings`. Do not rename symbols or
write comments unless explicitly requested in that RE turn.

### Task 2 - Passive Dynamic Proof Plan (operator-gated)

Do not execute this task without explicit current-turn approval for passive
process-memory proof.

The operator gives one physical action at a time. Codex owns passive recording
mechanics and asks only for concrete physical actions.

Required proof:

Initial approved physical setup, if the operator has not moved controls before
proof starts:

- Deck 1 loaded, all EQs at 12 o'clock, upfader all the way up.
- Deck 2 loaded, high/mid EQ at 12 o'clock, low EQ all the way down, upfader
  approximately 50%.

Treat that only as a baseline instruction from the operator. It is not proof
until passive samples are captured under current-turn approval.

- Deck 1 fader: down, audible, top.
- Deck 2 fader: down, audible, top.
- Deck 1 bass: below neutral, neutral/12 o'clock, above neutral.
- Deck 2 bass: below neutral, neutral/12 o'clock, above neutral.
- Deck 1 and Deck 2 filter neutral and movement, if filter is included.
- repeated samples per physical position.
- evidence that Deck 1 and Deck 2 are not swapped.
- evidence that values survive play/stop/master changes.
- evidence that missing/unreadable values are detectable as invalid authority.

Deliverable:

- a short RE evidence note in `docs/research/` or a task-local proof artifact
  named by the implementation closeout.
- no hardware/light output claims.

### Task 3 - Reader/Model Seam

After RE proof exists, add the smallest reader/model seam that can publish
decoded mixer state without blocking the push loop.

Expected shape:

- per-deck decoded upfader labels.
- per-deck decoded bass labels.
- optional per-deck decoded filter labels.
- validity/freshness for both decks.
- no one-sided guessing when one deck is missing.

Keep decoded mappings with the RE/offset layer first. Add config only if
evidence proves code-side labels cannot be stable enough.

### Task 4 - Pure Active-Deck Resolver

Add a pure resolver seam so the behavior contract can be tested without
Rekordbox or hardware.

Inputs should include:

- current `active_deck`.
- current `rb_master_deck`.
- Deck 1 playing state and decoded mixer labels.
- Deck 2 playing state and decoded mixer labels.
- mixer authority validity.
- stability/pending-candidate state as needed.

Outputs should include:

- selected `active_deck` or idle/no active deck.
- authority reason.
- mixer validity/degraded state.
- whether a switch is pending/stable.

The resolver must implement `docs/architecture/active_deck_authority.md`
exactly.

### Task 5 - StateManager Authority Integration

Integrate without changing unrelated output behavior.

Required changes:

- preserve `rb_master_deck` separately from `active_deck`.
- make `MASTER_CHANGED` update `rb_master_deck` when mixer authority is valid.
- route all valid active-deck changes through the resolver.
- remove/suppress playing-only mirror auto-switch as an independent authority
  while mixer authority is valid.
- allow old RB-master behavior while mixer authority is invalid.
- recover automatically when mixer authority becomes valid.
- avoid per-tick log spam.
- keep current downstream output paths using `active_deck` where practical.

### Task 6 - Status and Heartbeat

Expose:

- `active_deck` or `show_deck`.
- `rb_master_deck`.
- mixer authority validity.
- decoded fader/bass positions for both decks.
- authority reason.

Heartbeat must stop reporting `master = active_deck`. If a `master` field
remains for compatibility, it must represent `rb_master_deck` or be renamed
clearly.

### Task 7 - Filter Overlay Tracking Only

If filter is decoded, expose its state for a near-term LED/Govee overlay
follow-up. Do not implement visual overlay behavior until the visual design is
specified.

Filter rules:

- current active-deck filter only.
- LEDs/Govee only.
- no authority impact.
- no laser/SoundSwitch/scripted/autoloop impact.

## Part C - Invariants That MUST Still Hold

- `StateManager` remains the only writer of `DeckState`.
- `StateManager` owns `OutputState` and copied snapshots.
- `BridgeEvent`s remain immutable once enqueued.
- The 200 Hz push loop must not gain blocking network, socket, MIDI,
  filesystem, subprocess, Ghidra, or process-memory scanning work.
- Memory play bits do not override `DeckState.playing`.
- Direct readiness must be currently true; a flag alone is not authority.
- `RBStateReader._tick_deck()` must still enqueue `ANLZ_PATH` before
  `TRACK_LOADED`.
- SoundSwitch Decks 3/4 remain routing/internal details, not authority
  candidates.
- Existing laser, LED/Govee, SoundSwitch, scripted, and autoloop behavior should
  remain unchanged after a selected `active_deck` is chosen.
- Invalid mixer authority must be visible and recoverable.
- Software tests do not prove hardware-visible behavior.

## Part D - Tests

Required tests:

- pure resolver scenario tests for the scenarios listed in
  `docs/architecture/active_deck_authority.md`.
- invalid/missing mixer authority fallback test.
- invalid -> valid recovery test.
- reason/status change behavior test if cheap.
- StateManager integration test proving `MASTER_CHANGED` updates
  `rb_master_deck` and does not bypass resolver when mixer authority is valid.
- StateManager integration test proving old mirror auto-switch does not promote
  a fader-down playing deck when mixer authority is valid.
- runtime status/heartbeat test for `active_deck` plus `rb_master_deck`.
- Rekordbox reader tests for decoded mixer validity/freshness once reader code
  exists.

Do not build a huge logging harness unless the implementation makes it cheap.

Suggested targeted checks after implementation:

```bash
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

## Part E - Acceptance

Implementation is not complete until:

- `docs/architecture/active_deck_authority.md` remains accurate.
- RE evidence proves Deck 1/2 upfader and bass decoded labels.
- both-deck mixer authority validity is implemented.
- `rb_master_deck` is separate from `active_deck`.
- old playing-only mirror auto-switch cannot bypass valid mixer authority.
- invalid mixer authority visibly falls back to old RB-master behavior.
- recovery from invalid mixer authority returns to fader dominance.
- status/heartbeat exposes the required fields.
- required tests pass.
- no live restart/hardware action was performed without explicit approval.

## Adversarial Self-Review Checklist

Before marking this ready, check these failure modes:

- A fader-down playing deck can still steal authority through a leftover
  auto-switch path.
- `MASTER_CHANGED` still writes `active_deck` directly during valid mixer
  authority.
- `active_deck` and `rb_master_deck` are conflated in status/heartbeat.
- one deck's missing mixer state is treated as a valid comparison.
- raw memory thresholds are hardcoded without RE-labeled physical positions.
- a non-active scripted deck continues to drive outputs.
- the push loop gained blocking process-memory or Ghidra work.
- filter overlay scope expanded into active-deck authority.
- a static Ghidra symbol candidate is treated as a memory offset without passive
  process proof.
- `DJMMYSETTING.DAT` / rekordcrate preference settings are mistaken for live
  mixer control state.

## When You Finish

Report:

- changed files.
- RE evidence artifact paths.
- test/check commands and results.
- exact remaining unknowns.
- whether any live/hardware validation was performed.
- whether a bridge restart is needed for the running process to use the change.

Plain-language operator summary must include:

- what the bridge should do differently live.
- what should remain unchanged.
- how to recognize healthy fader dominance.
- what to watch for in SoundSwitch, lasers, LEDs/Govee, Rekordbox reader state,
  and bridge logs.
- what was software-verified.
- what was not hardware-validated.
- exact commands or approval gates needed before restarts, captures, toggles, or
  hardware-adjacent checks.
