---
doc_status: research-current
truth_level: static-and-passive-live-verified
last_verified_commit: 77395af
last_verified_date: 2026-06-28
validation_scope: Rekordbox 7.2.11 arm64 static Ghidra/GhidraMCP evidence plus operator-approved passive process-memory proof for Deck 1/2 upfader, LOW/BASS EQ, CFX FILTER param0/param1, Deck 1 mid fader, relaunch reacquire, and master-change survival; bridge/runtime/hardware output unmodified and unvalidated
---

# Rekordbox Mixer Active-Deck RE Evidence

This note records the current proof for Rekordbox 7.2.11 Deck 1/2 mixer
memory. It proves the local pointer/value mapping for upfader, LOW/BASS EQ, and
CFX FILTER parameters. It is reverse-engineering evidence, not runtime
implementation. The bridge was not restarted, bridge commands were not sent,
and MIDI, serial, DMX, Enttec, Govee, SoundSwitch output, lasers, and LEDs were
not opened or mutated during this proof.

## Scope

- Rekordbox binary:
  `/Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox`.
- Installed bundle version: `7.2.11.0342`.
- Thin arm64 RE artifact: `/tmp/rbss_re/rekordbox_7_2_11_arm64`.
- Thin-binary MD5: `f87084a7261547c0fe0c725291fa8c3e`.
- Thin-binary SHA-256:
  `bfd71965fb23fb6dc88461de9bd39e371b34a6455faea89fd1e353ba1d03efbd`.
- Static tool path: Ghidra 11.3.2 headless, no-analysis import, plus
  GhidraMCP for loaded mixer symbols.
- GhidraMCP status: available for loaded mixer functions in the 2026-06-28
  continuation pass. The required `DjUnitAudioGraph::getMixerControl` check at
  `0x10219e9b8` decompiled successfully and showed `*(graph + 0x458)` as the
  mixer vector, bounded by `*(graph + 0x464)`, with the selected element
  returned plus `0x180`.
- Static artifacts:
  `/tmp/rbss_re/ghidra_candidate_dump.txt`,
  `/tmp/rbss_re/ghidra_singleton_dump.txt`,
  `/tmp/rbss_re/ghidra_input_channel_dump.txt`,
  `/tmp/rbss_re/ghidra_mixer_index_dump.txt`,
  `/tmp/rbss_re/ghidra_cfx_dump.txt`,
  `/tmp/rbss_re/ghidra_filter_audio_dump.txt`,
  `/tmp/rbss_re/ghidra_colorfx_unit_dump.txt`,
  `/tmp/rbss_re/ghidra_djsystem_fx_dump.txt`,
  `/tmp/rbss_re/ghidra_fx_processor_dump.txt`, and
  `/tmp/rbss_re/ghidra_colorfx_deep_dump.txt`.
- Passive proof artifacts:
  `/tmp/rbss_re/mixer_proof_snapshots.jsonl` and
  `/tmp/rbss_re/cfx_mixer_samples.jsonl`.
- Passive proof processes:
  - Original fader/EQ PID `35122`, Mach-O base `0x102bf4000`.
  - CFX/filter and Deck 1 mid-fader PID `86137`, Mach-O base `0x102b58000`.
  - Relaunch and survival PID `87290`, Mach-O base `0x102ae4000`.

## Confirmed Mixer Root

The static symbol `djengine::DjEngineIF::singletonHolder` is at preferred VA
`0x104e16ea8`, so the runtime base-relative holder offset is `0x4e16ea8`.
`SingletonHolder::get()` returns the engine pointer stored at holder `+0x40`.
`DjEngineIF::getAudioGraph()` returns `*(engine + 0xa8)`.
`DjUnitAudioGraph::getMixerControl(0)` uses the mixer vector at graph `+0x458`.

Static `getMixerControl(0)` returns a mixer-control view derived from the object
stored in the graph mixer vector. The bridge-readable proof below intentionally
uses the passive-verified object chain, not the decompiler's return adjustment.
Do not replace this chain with the static return endpoint unless a new passive
proof validates that alternate endpoint.

Live proof used this root:

```text
singleton_holder = base + 0x4e16ea8
engine           = u64(singleton_holder + 0x40)
audio_graph      = u64(engine + 0xa8)
mixer_vector     = u64(audio_graph + 0x458)
mixer_base       = u64(mixer_vector + 0x0)
channel_vector   = u64(mixer_base + 0x2c8)
channel_graph[n] = u64(channel_vector + n * 8)
```

## Confirmed Upfader and LOW/BASS EQ

For Rekordbox 7.2.11 in the passive proof sessions:

- Deck 1 maps to mixer channel index `0`.
- Deck 2 maps to mixer channel index `1`.
- Upfader raw state is a float in the `0..1023` range.
- Upfader normalized state is `raw / 1023`.
- LOW/BASS EQ raw state is a float in the `0..255` range.
- LOW/BASS EQ normalized state is `raw / 255`.
- EQ band index `2` is physical LOW/BASS for Deck 1 and Deck 2.
- EQ band indexes `0` and `1` stayed neutral during this proof and are not
  physically mapped here.

Upfader read path:

```text
fader_module = u64(channel_graph[n] + 0x470)
fader_raw    = f32(fader_module + 0x30)
fader_norm   = fader_raw / 1023.0
```

LOW/BASS EQ read path:

```text
eqiso        = u64(channel_graph[n] + 0x460)
eq_child     = u64(eqiso + 0x30)
eq_band0_raw = f32(eq_child + 0x20)
eq_band1_raw = f32(eq_child + 0x2c)
eq_band2_raw = f32(eq_child + 0x38)  # physical LOW/BASS
eq_low_norm  = eq_band2_raw / 255.0
```

Using the existing `rb_offsets.py` chain semantics, the Rekordbox 7.2.11
implementation-candidate chains are:

```text
Deck 1 upfader raw: 04E16EE8 A8 458 0 2C8 0 470 30
Deck 2 upfader raw: 04E16EE8 A8 458 0 2C8 8 470 30
Deck 1 LOW raw:     04E16EE8 A8 458 0 2C8 0 460 30 38
Deck 2 LOW raw:     04E16EE8 A8 458 0 2C8 8 460 30 38
```

`04E16EE8` is `singletonHolder + 0x40` folded into the current chain format.
These chains are not yet implemented in `rb_offsets.py`.

Post-restore passive verification of those exact chain lines against the first
live process produced:

```text
pid=35122 base=0x102bf4000
d1_fader addr=0x6000009eabb0 raw=1023.00 norm=1.000
d2_fader addr=0x6000009ec070 raw=1023.00 norm=1.000
d1_low   addr=0x600003db0138 raw=127.50 norm=0.500
d2_low   addr=0x600003db0338 raw=127.50 norm=0.500
```

## Passive Upfader and LOW/BASS EQ Proof

The operator moved one physical control at a time while a passive watcher polled
the live Rekordbox process.

| Label | Time | Deck 1 fader | Deck 1 low | Deck 2 fader | Deck 2 low | Proof |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `baseline_d1_top_eq_neutral_d2_fader_half_low_down` | 2026-06-28 03:46:32 EDT | 1.000 | 0.500 | 0.510 | 0.000 | Operator-stated baseline mapped Deck 1 top/neutral and Deck 2 half/down. |
| `d2_fader_down` | 2026-06-28 03:47:32 EDT | 1.000 | 0.500 | 0.000 | 0.000 | Moving only Deck 2 upfader down changed channel 1 fader only. |
| `d2_fader_top` | 2026-06-28 03:48:29 EDT | 1.000 | 0.500 | 1.000 | 0.000 | Moving only Deck 2 upfader up changed channel 1 fader only. |
| `d2_low_neutral` | 2026-06-28 03:50:53 EDT | 1.000 | 0.500 | 1.000 | 0.500 | Moving Deck 2 LOW/BASS to center changed channel 1 band 2 only. |
| `d2_low_top` | 2026-06-28 03:51:52 EDT | 1.000 | 0.500 | 1.000 | 1.000 | Moving Deck 2 LOW/BASS up changed channel 1 band 2 only. |
| `d1_fader_down` | 2026-06-28 03:52:24 EDT | 0.000 | 0.500 | 1.000 | 1.000 | Moving only Deck 1 upfader down changed channel 0 fader only. |
| `d1_fader_top_restore` | 2026-06-28 03:52:49 EDT | 1.000 | 0.500 | 1.000 | 1.000 | Moving only Deck 1 upfader up changed channel 0 fader only. |
| `d1_low_down` | 2026-06-28 03:53:15 EDT | 1.000 | 0.000 | 1.000 | 1.000 | Moving only Deck 1 LOW/BASS down changed channel 0 band 2 only. |
| `d1_low_top` | 2026-06-28 03:53:49 EDT | 1.000 | 1.000 | 1.000 | 1.000 | Moving only Deck 1 LOW/BASS up changed channel 0 band 2 only. |
| `d1_d2_low_neutral_restore` | 2026-06-28 03:54:12 EDT | 1.000 | 0.500 | 1.000 | 0.500 | Both LOW/BASS knobs restored to center; faders stayed top. |

## Confirmed CFX FILTER Chain

Static `RekordboxDjColorFxLayer::createEffectBase()` maps effect id `0` to
`ColorFxFilterDjm900NXS2`:

- `ColorFxFilterDjm900NXS2` constructor: `0x10233bef4`.
- `__ZTV23ColorFxFilterDjm900NXS2` vtable: `0x104ab06a8`.
- Other statically mapped CFX ids are Jet `1`, Crush `2`, Noise `3`, Pitch
  `4`, Space `5`, Dub Echo `6`, Sweep `7`, Gate Comp `8`, Echo `9`, Reverb
  `10`, and Auto Tune `11`.

The passive-verified CFX path is:

```text
channel_graph[n]      = u64(channel_vector + n * 8)
processor_vector      = u64(channel_graph[n] + 0x480)
processor             = u64(processor_vector + i * 8)
cfx_slot4_vector      = u64(processor + 0x1e0)
cfx_unit              = u64(cfx_slot4_vector + j * 8)
unit_channel          = i32(cfx_unit + 0xd0)
layer_vector          = u64(cfx_unit + 0x88)
layer                 = u64(layer_vector)
selected_effect_id    = i32(layer + 0x70)
effect_vector         = u64(layer + 0x78)
filter_effect         = u64(effect_vector + 0 * 8)
param0/filter_color   = f32(layer + 0xe8)
param1/filter_param   = f32(layer + 0xec)
cutoff_smoother       = u64(filter_effect + 0x360)
resonance_smoother    = u64(filter_effect + 0x368)
cutoff_raw            = u32(cutoff_smoother + 0x10)
resonance_raw         = i32(resonance_smoother + 0x10)
```

`param0` and `param1` are already normalized `0..1` values. The
`ColorFxFilterDjm900NXS2` smoother raw values use `0..255`, with neutral at
`128`.

Using the existing `rb_offsets.py` chain semantics, the Rekordbox 7.2.11
implementation-candidate CFX chains are:

```text
Deck 1 CFX FILTER param0: 04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 E8
Deck 2 CFX FILTER param0: 04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 E8
Deck 1 CFX FILTER param1: 04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 EC
Deck 2 CFX FILTER param1: 04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 EC
```

The live proof showed all five processors per channel referenced the same CFX
unit for slot 4. A future reader must still validate vector bounds,
`unit_channel`, selected effect id, and readable finite values before treating a
CFX value as valid.

Accessibility/UI control mapping used during passive proof:

- CFX FILTER button: `app.0.1.103`.
- CFX PARAM knob: `app.0.1.111` -> all selected CFX channel layers'
  `param1`/resonance.
- CFX COLOR channel controls are ordered Sampler, Deck 3, Deck 1, Deck 2,
  Deck 4, Master in the visible CFX row.
- Deck 1 CFX COLOR knob: `app.0.1.114` -> channel index `0`.
- Deck 2 CFX COLOR knob: `app.0.1.115` -> channel index `1`.

## Passive CFX FILTER Proof

| Label | PID/base | Deck 1 CFX | Deck 2 CFX | Proof |
| --- | --- | --- | --- | --- |
| `after_filter_button_click` | `86137` / `0x102b58000` | selected id `0`, p0 `0.5`, p1 `0.5`, cutoff/res `128/128` | selected id `0`, p0 `0.5`, p1 `0.5`, cutoff/res `128/128` | FILTER selected and neutral for both decks. |
| `slider97_075` | `86137` / `0x102b58000` | p0 `0.75`, cutoff `191` | p0 `0.5`, cutoff `128` | Moving only Deck 1 CFX COLOR changed channel 0 only. |
| `slider98_0125` | `86137` / `0x102b58000` | p0 `0.75`, cutoff `191` | p0 `0.125`, cutoff `32` | Moving only Deck 2 CFX COLOR changed channel 1 only. |
| `param94_025` | `86137` / `0x102b58000` | p1 `0.25`, resonance `64` | p1 `0.25`, resonance `64` | CFX PARAM knob changed selected FILTER resonance for both decks. |
| `deck1_filter_min` | `86137` / `0x102b58000` | p0 `0.0`, cutoff `0` | p0 `0.125`, cutoff `32` | Deck 1 min edge proved valid zero and did not move Deck 2. |
| `deck1_filter_max` | `86137` / `0x102b58000` | p0 `1.0`, cutoff `255` | p0 `0.125`, cutoff `32` | Deck 1 max edge proved valid top. |
| `deck2_filter_min` | `86137` / `0x102b58000` | p0 `1.0`, cutoff `255` | p0 `0.0`, cutoff `0` | Deck 2 min edge proved valid zero and did not move Deck 1. |
| `deck2_filter_max` | `86137` / `0x102b58000` | p0 `1.0`, cutoff `255` | p0 `1.0`, cutoff `255` | Deck 2 max edge proved valid top. |
| `restored_neutral` | `86137` / `0x102b58000` | p0 `0.5`, p1 `0.5`, cutoff/res `128/128` | p0 `0.5`, p1 `0.5`, cutoff/res `128/128` | Deck 1/2 CFX restored to neutral. |

## Relaunch, Master-Change, and UI Survival Proof

- `fader124_50`: Deck 1 channel fader accessibility control was set to `50`.
  Passive read showed channel 0 fader raw `511.5`, normalized `0.5`; channel 1
  stayed raw `1023.0`, normalized `1.0`.
- `fader124_restored`: the same control was restored to `100`. Deck 1 and Deck
  2 both read raw `1023.0`, normalized `1.0`.
- `after_relaunch_reacquire`: Rekordbox was quit and relaunched. Old PID/base
  were `86137` / `0x102b58000`; new PID/base were `87290` / `0x102ae4000`.
  The same root chain reacquired engine, audio graph, mixer, channel vector,
  Deck 1/2 fader/EQ, and Deck 1/2 CFX FILTER neutral values.
- `after_deck1_master_press`: pressing Deck 1 MASTER (`app.0.1.195`) changed
  the direct master byte to raw `0` / bridge deck `1`; Deck 1/2 fader, EQ, CFX
  unit channel, selected FILTER id, and neutral FILTER params remained readable
  through the same reacquired chain.
- `after_deck2_master_press`: pressing Deck 2 MASTER (`app.0.1.217`) changed
  the direct master byte to raw `1` / bridge deck `2`; Deck 1/2 fader, EQ, CFX
  unit channel, selected FILTER id, and neutral FILTER params remained readable.
- `final_deck1_master_restore`: pressing Deck 1 MASTER (`app.0.1.195`) changed
  the direct master byte back to raw `0` / bridge deck `1`; Deck 1/2 fader,
  EQ, CFX unit channel, selected FILTER id, and neutral FILTER params remained
  readable. A Deck 2 MASTER re-press did not clear direct master back to
  `255/no_master`, so the final observed Rekordbox master state was Deck 1.
- `after_deck1_play_press` and `after_deck1_pause_restore`: pressing the Deck 1
  Play/Pause button did not advance direct live-position counters because Deck
  1 and Deck 2 had no loaded tracks after relaunch (`track_info` was empty and
  both live-position values stayed `0`). The mixer chain remained readable, but
  this is not actual play/stop survival proof.

## Static Function Evidence

- `djengine::DjEngineIF::setChannelFader()` gets `*(engine + 0xa8)`, calls
  `DjUnitAudioGraph::getMixerControl(0)`, then dispatches through the mixer
  vtable for the selected channel.
- `djengine::DjEngineIF::setEqualizer()` gets the same graph and mixer control
  and dispatches EQ value, channel index, and band index.
- `InputChannelGraph::setChannelFaderPosition()` uses
  `*(channel_graph + 0x470)` and writes through `ChannelFader::setParameter()`.
- `InputChannelGraph::getChannelFaderPosition()` reads the same fader module
  and returns `raw * 0.0009775171`, matching `raw / 1023`.
- `ChannelFader::setParameter()` stores channel-fader parameter `0` at module
  `+0x30`.
- `InputChannelGraph::setEqPosition()` uses `*(channel_graph + 0x460)` and
  scales normalized values to `0..255`.
- `EqualizerNXS2::setParameter()` and `getParameter()` use `+0x20`, `+0x2c`,
  and `+0x38` for band indexes `0`, `1`, and `2`.
- `MixerControlComp::eventAbsoluteValueChanged()` routes to
  `DjEngineIF::setDigitalTrim()`, not the CFX filter path. It should no longer
  be treated as a filter candidate without contradictory new evidence.
- `RbxCFXDeviceComponent::eventOnChanged()` /
  `eventAbsoluteValueChanged()` route CFX events to
  `RbxCfxControlBehavior::setCfxKnobValue()`,
  `setCfxParameterKnobValue()`, `setCfxButtonState()`, `startEffect()`, and
  `selectFx()`.
- `RbxCFXDeviceComponent` stores the CFX behavior pointer near `this + 0x168`.
  Knob device-object slots near `this + 0x1d8` through `this + 0x200` route to
  CFX knob indexes `0..5`, with incoming absolute values normalized by the same
  `6.103888e-05` scale seen in other Rekordbox controller handlers.
- GUI behavior state includes fields such as `+0xfc`,
  `+0xe8 + index * 4`, parameter `+0x100`, and remembered parameter
  `+0x70 + index * 4`; this is GUI/effect-state contrast evidence, not the
  bridge-readable audio chain used above.
- `DjEngineIF::getDjSystem()` returns `*(engine + 0xa0)`, while
  `DjEngineIF::getAudioGraph()` returns `*(engine + 0xa8)`.
- `RekordboxDjColorFxUnitContainer` creates one `RekordboxDjColorFxUnit` per
  player index, stores first-layer pointers in its container vector at
  `+0x68..+0x78`, stores unit pointers in its vector at `+0xf0..+0x100`, and
  attaches each unit with `DjSystem::setChannelFx(unit, player_index, 4)`.
- `DjSystem::setChannelFx()` dispatches through the audio graph's mixer vector.
  `DjMixerUnit::setChannelFx()` indexes the mixer channel vector at
  `+0x2c8..+0x2d0`, gets `channel_graph[channel]`, and iterates the
  `InputChannelGraph` processor vector at `channel_graph + 0x480..+0x488`.
  `FxUnitProcessor::addFxUnit()` stores the `AbstractFxUnit*` in a per-slot
  vector when `slot < 7`; for the CFX attach slot `4`, that vector triple is
  `processor + 0x1e0`, `+0x1e8`, and `+0x1f0`.
- Inside `RekordboxDjColorFxUnit`, the layer vector is `+0x88..+0x98`.
  `+0x68` is not the unit layer vector; that offset belongs to the container's
  first-layer pointer vector.
- `RekordboxDjColorFxLayer::setParameter()` stores normalized parameter values
  at `layer + 0xe8` and `layer + 0xec`.
- `ColorFxFilterDjm900NXS2` statically confirms the audio-side raw domain:
  filter parameter values are scaled to `0..255`, smoothing pointers live at
  `filter + 0x360` and `filter + 0x368`, and coefficient update reads cutoff
  and resonance raw values from each smoother's `+0x10`.

## Out-of-Scope Validation Gaps

No local Rekordbox 7.2.11 Deck 1/2 pointer/value-mapping unknown remains for
upfader, LOW/BASS EQ, CFX FILTER param0/param1, Deck 1 midpoint, local relaunch
reacquisition, or direct-master-change survival.

The following are not proven by this RE evidence and remain implementation or
validation work:

- Rekordbox versions other than local `7.2.11.0342`.
- Actual play/stop survival with loaded tracks; after relaunch, Deck 1/2 had no
  loaded tracks, so the play/pause probe did not create transport movement.
- Bridge runtime implementation of mixer fields, finite-f32 validity,
  freshness, thresholds, hysteresis, invalidation, resolver behavior, status, or
  heartbeat.
- Any SoundSwitch, laser, LED/Govee, DMX, MIDI, serial, Enttec, or
  bridge-output behavior.
