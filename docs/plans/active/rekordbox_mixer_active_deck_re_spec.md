---
doc_status: current
truth_level: static-and-passive-live-verified planning spec
last_verified_commit: ab2bc15
last_verified_date: 2026-06-28
validation_scope: static RE plus operator-approved passive process-memory proof for Rekordbox 7.2.11 Deck 1/2 upfader, LOW/BASS EQ, CFX FILTER param0/param1, Deck 1 mid fader, relaunch reacquire, and mixer-chain readability after operator-labeled master-button actions; runtime implementation, software behavior, and hardware behavior unvalidated
---

# Codex Implementation Spec - Rekordbox Mixer Active-Deck Authority

Status: ACTIVE SPEC. This is a plan plus RE evidence handoff, not proof of
runtime implementation.

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
- [confirmed] `_do_resume()` can also correct an empty-deck mismatch by writing
  `self._os.active_deck = mirror` directly.
- [confirmed] `_update_lighting()` derives scripted/autoloop/idle from the
  active deck's playing/scripted state.
- [confirmed] `_drive_pack_output()` reads `self._os.active_deck` and renders
  the pack from that deck.
- [confirmed] `SoundSwitchEngine.deck_route(active)` uses active deck plus
  mirror plus decks 3/4 for canonical fanout.
- [confirmed] `runtime_status._heartbeat_payload()` currently reports
  `"master": active_deck`.
- [confirmed] `rb_offsets.py` currently parses a fixed legacy layout of one
  master chain plus four chains per deck. Mixer chains cannot be made available
  by merely appending extra chain lines; the offset model/parser/tests must grow
  explicit mixer fields.
- [confirmed] `RBStateReader._follow_float()` currently filters float reads to
  `0.0 < v < 1000.0`, which is correct enough for live BPM but wrong for mixer
  values. Valid mixer proof includes `0.0`, `255.0`, and `1023.0`, so mixer
  reads need their own finite float helper/range validation.
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
- [confirmed] The first RE pass did not have callable GhidraMCP, but the
  2026-06-28 continuation pass had GhidraMCP available for loaded mixer
  functions. CFX addresses were not loaded as decompilable MCP functions and
  required a temporary no-analysis headless dump at
  `/tmp/rbss_re/ghidra_cfx_dump.txt`.
- [confirmed] Current proof is summarized in
  `docs/research/rekordbox_mixer_active_deck_re_evidence.md`. The local raw
  live snapshot artifacts are `/tmp/rbss_re/mixer_proof_snapshots.jsonl` and
  `/tmp/rbss_re/cfx_mixer_samples.jsonl`.
- [confirmed] `ChannelFaderComp::eventAbsoluteValueChanged` validates the
  incoming device object against a stored component pointer near
  `this + 0x238`, converts the incoming integer to a normalized double with
  scale `6.103888176768602e-05`, stores a cached double near `this + 0x250`,
  and passes the value plus an id near `this + 0x248` toward a `DjEngine`
  singleton call target at `0x1007b4b08`. This static function alone does not
  prove Deck 1 vs Deck 2; the passive proof below does.
- [confirmed] `EqControlComp::eventAbsoluteValueChanged` checks three stored
  device-object pointers near `this + 600`, `this + 0x260`, and `this + 0x268`,
  maps them to band indexes `0`, `1`, and `2`, applies the same
  `6.103888176768602e-05` scale, stores cached per-band doubles near
  `this + 0x290 + band * 8`, and passes value, id near `this + 0x288`, and
  band index toward a `DjEngine` singleton call target at `0x1007b51cc`.
  This static function alone does not prove low/mid/high order; the passive
  proof below maps band index `2` to LOW/BASS.
- [confirmed] `MixerControlComp::eventAbsoluteValueChanged` has the same
  normalized-value shape, with a device pointer near `this + 0x268`, id near
  `this + 0x278`, cached double near `this + 0x280`, and call target
  `0x1007b4bfc`; GhidraMCP decompilation shows that target resolves to
  `DjEngineIF::setDigitalTrim()`. This is not the CFX filter path and is not
  active-deck authority proof.
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
- [confirmed] Static CFX GUI evidence exists:
  `effectGui::RbxCFXDeviceComponent::eventOnChanged()` /
  `eventAbsoluteValueChanged()` route CFX events to
  `RbxCfxControlBehavior::setCfxKnobValue()`,
  `setCfxParameterKnobValue()`, `setCfxButtonState()`, `startEffect()`, and
  `selectFx()`. The knob path clamps `0..1` values and stores GUI/effect-state
  fields including `+0xfc`, per-index `+0xe8 + index * 4`, parameter `+0x100`,
  and remembered parameter `+0x70 + index * 4`. The CFX component stores its
  behavior pointer near `this + 0x168`; knob device-object slots near
  `this + 0x1d8` through `this + 0x200` route to CFX knob indexes `0..5`.
  Rekordbox strings also expose CFX/FILTER commands and
  `CFXParameterCH1` through `CFXParameterCH4`. This is GUI/effect-state
  contrast evidence; the bridge-readable FILTER endpoint is the audio chain
  below.
- [confirmed] Static and passive Color FX audio/container evidence ties CFX
  FILTER to the same `DjSystem` / `DjUnitAudioGraph` family as the
  passive-verified mixer chain. `DjEngineIF::getDjSystem()` returns
  `*(engine + 0xa0)`. `RekordboxDjColorFxUnitContainer` creates one
  `RekordboxDjColorFxUnit` per player index, stores first-layer pointers in its
  container vector at `+0x68..+0x78`, stores unit pointers in its vector at
  `+0xf0..+0x100`, and attaches each unit with
  `DjSystem::setChannelFx(unit, player_index, 4)`. `DjSystem::setChannelFx()`
  dispatches through the audio graph; `DjMixerUnit::setChannelFx()` indexes the
  mixer channel vector at `+0x2c8..+0x2d0`; `InputChannelGraph::setEffectUnit()`
  iterates the processor vector at `channel_graph + 0x480..+0x488`; and
  `FxUnitProcessor::addFxUnit()` stores the `AbstractFxUnit*` in a per-slot
  vector when `slot < 7`. For CFX attach slot `4`, that processor vector triple
  is `+0x1e0`, `+0x1e8`, and `+0x1f0`.
- [confirmed] Inside `RekordboxDjColorFxUnit`, the layer vector is
  `+0x88..+0x98`. `+0x68` is not the unit layer vector; it belongs to the
  container's first-layer pointer vector.
- [confirmed] Static Color FX parameter evidence shows
  `RekordboxDjColorFxUnitContainer::setParameter()` / `getParameter()` using the
  unit vector at `container + 0xf0` by channel/deck argument, and
  `RekordboxDjColorFxLayer::setParameter()` storing normalized parameter values
  at `layer + 0xe8` and `layer + 0xec`. `ColorFxFilterDjm900NXS2` scales filter
  parameters to a `0..255` audio raw domain, with smoother pointers at
  `filter + 0x360` and `filter + 0x368`; passive proof confirmed neutral raw
  `128`, min raw `0`, and max raw `255`.
- [confirmed] Static and live proof tie the readable Rekordbox 7.2.11 mixer
  root to `djengine::DjEngineIF::singletonHolder` at preferred VA
  `0x104e16ea8`, runtime base-relative holder offset `0x4e16ea8`.
  `SingletonHolder::get()` returns `*(holder + 0x40)`, and
  `DjEngineIF::getAudioGraph()` returns `*(engine + 0xa8)`.
- [confirmed] Static `DjUnitAudioGraph::getMixerControl(0)` returns a mixer
  control view at an offset from the object stored in the graph mixer vector,
  while the passive bridge-readable proof starts from the vector object itself.
  Do not replace the passive-verified chain with the static `getMixerControl`
  return offset unless a new passive proof validates that alternate endpoint.
- [confirmed] The live bridge-readable chain is:
  holder `base + 0x4e16ea8`, engine `*(holder + 0x40)`, audio graph
  `*(engine + 0xa8)`, mixer vector `*(graph + 0x458)`, mixer base
  `*(mixer_vector + 0)`, channel vector `*(mixer_base + 0x2c8)`, and
  `channel_graph[n] = *(channel_vector + n * 8)`.
- [confirmed] Deck 1 maps to mixer channel index `0` and Deck 2 maps to mixer
  channel index `1` in the current Rekordbox 7.2.11 proof session.
- [confirmed] Upfader raw state is a float in `0..1023` at
  `*(channel_graph + 0x470) + 0x30`. Normalize with `raw / 1023.0`.
- [confirmed] LOW/BASS EQ raw state is a float in `0..255` at
  `eq_child + 0x38`, where `eqiso = *(channel_graph + 0x460)` and
  `eq_child = *(eqiso + 0x30)`. Normalize with `raw / 255.0`.
- [confirmed] EQ band index `2` is physical LOW/BASS for Deck 1 and Deck 2.
  Band indexes `0` and `1` remained neutral during this pass and are not
  physically mapped here.
- [confirmed] Using existing `rb_offsets.py` chain semantics, the Rekordbox
  7.2.11 implementation-candidate chains are:
  Deck 1 upfader `04E16EE8 A8 458 0 2C8 0 470 30`,
  Deck 2 upfader `04E16EE8 A8 458 0 2C8 8 470 30`,
  Deck 1 LOW/BASS `04E16EE8 A8 458 0 2C8 0 460 30 38`, and
  Deck 2 LOW/BASS `04E16EE8 A8 458 0 2C8 8 460 30 38`.
- [confirmed] Using existing `rb_offsets.py` chain semantics, the local
  Rekordbox 7.2.11 CFX FILTER implementation-candidate chains are:
  Deck 1 FILTER param0 `04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 E8`,
  Deck 2 FILTER param0 `04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 E8`,
  Deck 1 FILTER param1 `04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 EC`, and
  Deck 2 FILTER param1 `04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 EC`.
  A future reader must validate vector bounds, `unit_channel`, selected effect
  id `0`, finite values, and readable both-deck state before using filter
  values for any tracking or status.
- [confirmed] Operator-approved passive process-memory proof captured the same
  live PID/base while moving one physical control at a time: Deck 2 upfader
  down/top, Deck 2 LOW/BASS down/center/top, Deck 1 upfader down/top, Deck 1
  LOW/BASS down/top, and final LOW/BASS neutral restore.
- [confirmed] Operator-approved passive process-memory proof also captured
  Deck 1 mid-fader (`raw=511.5`, `norm=0.5`), Deck 1/2 CFX FILTER min/neutral
  /max endpoints, CFX PARAM/resonance movement, relaunch reacquisition
  (`86137` -> `87290` with base change), and mixer-chain readability after
  operator-labeled Deck 1/2 MASTER actions. Direct-master byte reliability is
  current bridge code truth, not a field carried by the mixer JSONL artifacts.
- [confirmed] `rekordcrate` is useful background for Rekordbox export/settings
  formats, but its `DJMMYSETTING.DAT` parser covers mixer preference settings
  such as channel-fader curve and crossfader curve, not live per-deck fader/EQ
  positions.
- [confirmed] No local Rekordbox 7.2.11 Deck 1/2 pointer/value-mapping unknown
  remains for upfader, LOW/BASS EQ, CFX FILTER param0/param1, Deck 1 midpoint,
  local relaunch reacquisition, or mixer-chain readability after
  operator-labeled master-button actions.
- [unknown] The chains are proven for local Rekordbox `7.2.11.0342` only; other
  Rekordbox versions still require explicit validation.
- [unknown] Actual play/stop survival with loaded tracks was not proven. After
  relaunch, Deck 1/2 had no loaded tracks, so the play/pause probe did not
  create transport movement. Implementation must retain fail-closed validity
  and freshness checks.
- [unknown] Missing/unreadable mixer values are not implemented yet and must
  invalidate mixer authority rather than guessing from one deck.
- [unknown] Runtime thresholds, hysteresis, and stability timing remain
  resolver implementation work.

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

Current status: completed for Deck 1/2 upfader and LOW/BASS EQ on
2026-06-28. The continuation pass also completed Deck 1 mid-fader, Deck 1/2
CFX FILTER param0/param1, relaunch reacquire, and mixer-chain readability after
operator-labeled master-button actions. Direct-master byte authority remains
current bridge code truth. See
`docs/research/rekordbox_mixer_active_deck_re_evidence.md`.

Initial approved physical setup, if the operator has not moved controls before
proof starts:

- Deck 1 loaded, all EQs at 12 o'clock, upfader all the way up.
- Deck 2 loaded, high/mid EQ at 12 o'clock, low EQ all the way down, upfader
  approximately 50%.

Treat that only as a baseline instruction from the operator. It is not proof
until passive samples are captured under current-turn approval.

- Already captured: Deck 1 fader down/mid/top, Deck 2 fader down/half/top,
  Deck 1 bass below/neutral/above, Deck 2 bass below/neutral/above, Deck 1/2
  FILTER neutral/min/max, repeated samples per physical position, evidence that
  Deck 1 and Deck 2 are not swapped, relaunch reacquire, and mixer-chain
  readability after operator-labeled master-button actions.
- Still not captured: actual play/stop survival with loaded tracks. The
  relaunch session had no loaded tracks, so the play/pause button probe did not
  advance live-position counters.
- Runtime implementation must still prove missing/unreadable values are
  detectable as invalid authority.

Deliverable:

- a short RE evidence note in `docs/research/` or a task-local proof artifact
  named by the implementation closeout.
- no hardware/light output claims.

### Task 3 - Reader/Model Seam

After RE proof exists, add the smallest reader/model seam that can publish
decoded mixer state without blocking the push loop.

Required offset/parser changes:

- Extend `RBOffsetVersion` with explicit optional mixer chains for Deck 1 and
  Deck 2 upfader raw and LOW/BASS raw. Do not append anonymous extra chain
  lines to the existing fixed `1 + 4*deck_count` parser layout.
- Add parser coverage proving the Rekordbox `7.2.11` record exposes exactly the
  four proven mixer chains and that older records without mixer chains remain
  supported/fail-closed.
- Use the passive-verified chain lines exactly:
  `04E16EE8 A8 458 0 2C8 0 470 30`,
  `04E16EE8 A8 458 0 2C8 8 470 30`,
  `04E16EE8 A8 458 0 2C8 0 460 30 38`,
  `04E16EE8 A8 458 0 2C8 8 460 30 38`.
- If exposing CFX FILTER tracking/status, extend the model with explicit
  optional filter fields and use the passive-verified chain lines exactly:
  `04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 E8`,
  `04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 E8`,
  `04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 EC`,
  `04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 EC`.
  Filter fields must not feed active-deck authority.

Required reader changes:

- Add a mixer-specific finite f32 read path; do not reuse `_follow_float()` as
  written because it rejects valid mixer values `0.0` and `1023.0`.
- Validate raw ranges per signal: upfader `0.0..1023.0`, LOW/BASS `0.0..255.0`.
  Any NaN, infinity, unreadable chain, null chain, or out-of-range value makes
  mixer authority invalid for both decks.
- Normalize only after range validation: fader `raw / 1023.0`, LOW/BASS
  `raw / 255.0`.
- If filter tracking/status is implemented, validate selected effect id `0`,
  `unit_channel`, vector bounds, and finite `0.0..1.0` param0/param1 for both
  decks. Missing or ambiguous filter state must invalidate filter tracking, not
  active-deck authority.

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
- remove/suppress resume-time direct `active_deck` correction as an independent
  authority while mixer authority is valid.
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

Filter is decoded for local Rekordbox 7.2.11. If implementation exposes filter
state, keep it as tracking/status data for a near-term LED/Govee overlay
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
- StateManager integration test proving resume-time empty-deck correction does
  not bypass the resolver when mixer authority is valid.
- runtime status/heartbeat test for `active_deck` plus `rb_master_deck`.
- Rekordbox reader tests for decoded mixer validity/freshness once reader code
  exists.
- `rb_offsets.py` parser/model tests proving the four Rekordbox `7.2.11` mixer
  chains are exposed by named fields, not ignored as trailing text.
- If filter fields are added, parser/model tests proving the four CFX FILTER
  chains are exposed by named optional fields and cannot affect authority.
- mixer f32 reader tests proving valid `0.0`, `255.0`, and `1023.0` are accepted
  while NaN, infinity, unreadable, null, and out-of-range values fail closed.
- If filter fields are added, filter reader tests proving valid `0.0`, `0.5`,
  and `1.0` are accepted only when effect id, unit channel, and vector bounds
  are valid.

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
- RE evidence proves Deck 1/2 upfader, bass, and non-authority FILTER decoded
  labels for local Rekordbox 7.2.11.
- both-deck mixer authority validity is implemented.
- filter data, if implemented, has no active-deck authority impact.
- `rb_master_deck` is separate from `active_deck`.
- old playing-only mirror auto-switch cannot bypass valid mixer authority.
- resume-time empty-deck correction cannot bypass valid mixer authority.
- invalid mixer authority visibly falls back to old RB-master behavior.
- recovery from invalid mixer authority returns to fader dominance.
- status/heartbeat exposes the required fields.
- required tests pass.
- no live restart/hardware action was performed without explicit approval.
- implementation proves the existing `_follow_float()` BPM filter was not reused
  for mixer raw values.

## Adversarial Self-Review Checklist

Before marking this ready, check these failure modes:

- A fader-down playing deck can still steal authority through a leftover
  auto-switch path.
- `MASTER_CHANGED` still writes `active_deck` directly during valid mixer
  authority.
- resume-time empty-deck correction still writes `active_deck` directly during
  valid mixer authority.
- `active_deck` and `rb_master_deck` are conflated in status/heartbeat.
- one deck's missing mixer state is treated as a valid comparison.
- raw memory thresholds are hardcoded without RE-labeled physical positions.
- a non-active scripted deck continues to drive outputs.
- the push loop gained blocking process-memory or Ghidra work.
- filter overlay scope expanded into active-deck authority.
- any new static Ghidra symbol candidate is treated as a memory offset without
  passive process proof.
- the CFX FILTER chain is used without validating vector bounds, selected
  effect id `0`, `unit_channel`, and both-deck finite values.
- the passive-verified mixer vector chain is accidentally replaced by the static
  `getMixerControl()` return offset without a new live proof.
- mixer chain lines are appended to `rb_offsets.py` but ignored by the fixed
  parser layout.
- `RBStateReader._follow_float()` rejects valid mixer bottom/top values.
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
