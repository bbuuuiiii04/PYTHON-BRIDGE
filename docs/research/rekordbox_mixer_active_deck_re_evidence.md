---
doc_status: research-current
truth_level: static-and-passive-live-verified
last_verified_commit: 1775a5a
last_verified_date: 2026-06-28
validation_scope: Rekordbox 7.2.11 arm64 static Ghidra/GhidraMCP evidence plus operator-approved passive process-memory proof for upfader/LOW; CFX/filter static candidate located but not passively proven; bridge/runtime/hardware output unmodified and unvalidated
---

# Rekordbox Mixer Active-Deck RE Evidence

This note records the current proof for Rekordbox 7.2.11 Deck 1/2 upfader and
LOW/BASS EQ memory. It is reverse-engineering evidence, not runtime
implementation. The bridge was not restarted, runtime commands were not sent,
and MIDI, serial, DMX, Enttec, Govee, SoundSwitch output, lasers, and LEDs were
not opened or mutated during this proof.

## Scope

- Rekordbox binary:
  `/Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox`.
- Thin arm64 RE artifact: `/tmp/rbss_re/rekordbox_7_2_11_arm64`.
- Thin-binary MD5: `f87084a7261547c0fe0c725291fa8c3e`.
- Thin-binary SHA-256:
  `bfd71965fb23fb6dc88461de9bd39e371b34a6455faea89fd1e353ba1d03efbd`.
- Static tool path: Ghidra 11.3.2 headless, no-analysis import, plus
  GhidraMCP for loaded mixer symbols.
- GhidraMCP status: available for loaded mixer functions in the 2026-06-28
  continuation pass; CFX addresses still required a temporary headless dump.
- CFX static artifact: `/tmp/rbss_re/ghidra_cfx_dump.txt`.
- Live process proof: Rekordbox PID `35122`, Mach-O base `0x102bf4000`.
- Live proof artifact: `/tmp/rbss_re/mixer_proof_snapshots.jsonl`.

## Confirmed Chain

The static symbol `djengine::DjEngineIF::singletonHolder` is at preferred VA
`0x104e16ea8`, so the runtime base-relative holder offset is `0x4e16ea8`.
`SingletonHolder::get()` returns the engine pointer stored at holder `+0x40`.
`DjEngineIF::getAudioGraph()` returns `*(engine + 0xa8)`.
`DjUnitAudioGraph::getMixerControl(0)` uses the mixer vector at graph `+0x458`.

Static `getMixerControl(0)` returns a mixer-control view derived from the object
stored in the graph mixer vector. The bridge-readable proof below intentionally
uses the passive-verified object chain, not the decompiler's return adjustment.
If a future pass wants to use the static return endpoint directly, it must prove
that alternate endpoint with passive reads before changing implementation
chains.

Live proof used this chain:

```text
singleton_holder = base + 0x4e16ea8
engine           = u64(singleton_holder + 0x40)
audio_graph      = u64(engine + 0xa8)
mixer_vector     = u64(audio_graph + 0x458)
mixer_base       = u64(mixer_vector + 0x0)
channel_vector   = u64(mixer_base + 0x2c8)
channel_graph[n] = u64(channel_vector + n * 8)
```

Observed live values:

```text
base             = 0x102bf4000
singleton_holder = 0x107a0aea8
engine           = 0x600002af97a0
audio_graph      = 0x157a83e00
mixer_base       = 0x157b25a00
channel_vector   = 0x60000145e880
channel_graph[0] = 0x158133200
channel_graph[1] = 0x158139000
```

## Confirmed Values

For Rekordbox 7.2.11 in this live session:

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

Using the existing `rb_offsets.py` chain semantics, the corresponding
Rekordbox 7.2.11 implementation-candidate chains are:

```text
Deck 1 upfader raw: 04E16EE8 A8 458 0 2C8 0 470 30
Deck 2 upfader raw: 04E16EE8 A8 458 0 2C8 8 470 30
Deck 1 LOW raw:     04E16EE8 A8 458 0 2C8 0 460 30 38
Deck 2 LOW raw:     04E16EE8 A8 458 0 2C8 8 460 30 38
```

These chains are not yet implemented in `rb_offsets.py`.

`rb_offsets.py` currently parses a fixed one-master plus four-chains-per-deck
layout. Implementing these chains requires explicit mixer fields/parser tests;
merely appending lines to the existing table would not expose them to the
reader.

Post-restore passive verification of those exact chain lines against the live
process produced:

```text
pid=35122 base=0x102bf4000
d1_fader addr=0x6000009eabb0 raw=1023.00 norm=1.000
d2_fader addr=0x6000009ec070 raw=1023.00 norm=1.000
d1_low   addr=0x600003db0138 raw=127.50 norm=0.500
d2_low   addr=0x600003db0338 raw=127.50 norm=0.500
```

## Passive Live Proof

The operator moved one physical control at a time while a passive watcher polled
the live Rekordbox process and appended only threshold-matched snapshots. The
proof rows below use the same PID, base address, and pointer chain.

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
- Static CFX evidence is separate from the mixer graph proof:
  `effectGui::RbxCFXDeviceComponent::eventOnChanged()` /
  `eventAbsoluteValueChanged()` route CFX events to
  `RbxCfxControlBehavior::setCfxKnobValue()`,
  `setCfxParameterKnobValue()`, `setCfxButtonState()`, `startEffect()`, and
  `selectFx()`.
- In the 2026-06-28 static continuation pass, GhidraMCP remained usable for
  loaded mixer functions, but the CFX addresses `0x100211170`
  (`RbxCFXDeviceComponent::eventAbsoluteValueChanged`) and `0x1009f59bc`
  (`RbxCfxControlBehavior::setCfxKnobValue`) returned no MCP-loaded function.
  CFX details below therefore come from `/tmp/rbss_re/ghidra_cfx_dump.txt`.
- `RbxCFXDeviceComponent` stores the CFX behavior pointer near `this + 0x168`.
  Knob device-object slots near `this + 0x1d8` through `this + 0x200` route to
  CFX knob indexes `0..5`, with incoming absolute values normalized by the same
  `6.103888e-05` scale seen in other Rekordbox controller handlers.
- `RbxCfxControlBehavior::setCfxKnobValue()` clamps knob values to `0..1` and
  stores them in GUI/effect-state fields including `+0xfc` and per-index
  `+0xe8 + index * 4`. `setCfxParameterKnobValue()` stores a parameter value at
  `+0x100`, and `memoryParamKnob()` can copy that value to `+0x70 + index * 4`.
  This identifies likely CFX state, but not a bridge-readable Deck 1/2 filter
  memory chain.
- User-facing strings in the Rekordbox binary confirm CFX/FILTER labels,
  `CFXParameterCH1` through `CFXParameterCH4`, center commands, and the
  "Filter is set as default" path. This is UI/command evidence only; it does not
  establish a stable process-memory chain or Deck 1/2 mapping for bridge reads.

## Remaining Unknowns

- CFX/filter GUI/effect-state handling is statically located, but Deck 1/2
  filter knob memory is not decoded or passively proven. No stable pointer root,
  deck mapping, or raw/normalized range is established for bridge use.
- This proves the local Rekordbox 7.2.11 live process, not other Rekordbox
  versions or post-relaunch stability.
- Play/stop/master-change survival was not proven; implementation must retain
  fail-closed validity and freshness checks.
- Missing/unreadable mixer values are not implemented yet and must invalidate
  mixer authority rather than guessing from one deck.
- Deck 1 intermediate/audible upfader was not separately sampled; Deck 1
  down/top and Deck 2 down/half/top were sampled.
- The existing live-BPM float reader rejects valid mixer values `0.0` and
  `1023.0`; implementation needs a mixer-specific finite-f32 range check.
- Runtime threshold, hysteresis, and stability timing remain resolver work.
- No SoundSwitch, laser, LED/Govee, DMX, MIDI, serial, Enttec, or bridge-output
  behavior is validated by this RE proof.
