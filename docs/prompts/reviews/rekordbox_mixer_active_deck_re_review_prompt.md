---
doc_status: active-review-prompt
truth_level: reverse-engineering-review-instructions
last_verified_commit: 77395af
last_verified_date: 2026-06-28
validation_scope: adversarial review of Rekordbox mixer active-deck static/passive-live RE reasoning after local 7.2.11 fader/LOW/FILTER closure and implementation handoff; review-only; no live sampling/hardware authority
---

# ChatGPT adversarial review - Rekordbox mixer active-deck RE

You are the independent adversarial reviewer for `rb_ss_bridge_v2`. Review the
reverse-engineering process and reasoning for Rekordbox 7.2.11 mixer
active-deck authority. Do not implement fixes.

Repo: `/Users/bbui/rb_ss_bridge_v2`
Branch: `main`
Evidence base before this review-prompt update:
`77395af`

## Hard Boundary

This is review-only. Do not edit, commit, push, or mutate external state. Do
not restart the bridge. Do not start, stop, signal, or inspect live bridge
processes. Do not open MIDI, serial, Enttec, DMX, Govee, or lighting hardware.
Do not run live Rekordbox process-memory sampling or capture unless the operator
explicitly approves it in that review turn.

Static repository inspection, static Ghidra/GhidraMCP reads, and offline
decompilation are allowed. If GhidraMCP is unavailable, report that as a review
limitation instead of inventing RE evidence.

If present, the local static dump from the planning pass is:

- `/tmp/rbss_re/ghidra_candidate_dump.txt`
- `/tmp/rbss_re/ghidra_singleton_dump.txt`
- `/tmp/rbss_re/ghidra_input_channel_dump.txt`
- `/tmp/rbss_re/ghidra_mixer_xrefs.txt`
- `/tmp/rbss_re/ghidra_mixer_index_dump.txt`
- `/tmp/rbss_re/ghidra_cfx_dump.txt`
- `/tmp/rbss_re/ghidra_filter_audio_dump.txt`
- `/tmp/rbss_re/ghidra_colorfx_unit_dump.txt`
- `/tmp/rbss_re/ghidra_djsystem_fx_dump.txt`
- `/tmp/rbss_re/ghidra_fx_processor_dump.txt`
- `/tmp/rbss_re/ghidra_colorfx_deep_dump.txt`
- `/tmp/rbss_re/mixer_proof_snapshots.jsonl`
- `/tmp/rbss_re/cfx_mixer_samples.jsonl`

Treat it as a local artifact to inspect or regenerate, not as committed proof.
The committed proof summary is:

- `docs/research/rekordbox_mixer_active_deck_re_evidence.md`

## Required Reads

Read these first:

- `AGENTS.md`
- `docs/architecture/active_deck_authority.md`
- `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md`
- `docs/research/rekordbox_mixer_active_deck_re_evidence.md`
- `docs/subsystems/rekordbox_readers.md`
- `rb_offsets.py`
- `rb_state_reader.py`
- `state_manager.py`
- `runtime_status.py`
- `models.py`

Use executable code over docs when they conflict.

## Review Surface A - Target Behavior

Try to disprove:

1. `active_deck` is defined as the playing audible show deck, not Rekordbox
   master.
2. `rb_master_deck` remains available only for tie/fallback behavior.
3. Decks 3/4, crossfader, trim, gain, mid/high EQ, real loudness, FX, and filter
   are not active-deck authority inputs for the first implementation.
4. Filter is scoped to a later LED/Govee overlay only.
5. Invalid or missing mixer authority visibly falls back to old RB-master
   behavior and recovers when valid mixer authority returns.

## Review Surface B - Static And Passive-Live RE Reasoning

Treat every RE claim as suspect until the static and passive-live evidence both
support it. Try to disprove:

1. The Ghidra import evidence matches the Rekordbox 7.2.11 arm64 binary, not a
   stale or wrong-architecture artifact.
2. The candidate symbols are relevant to live mixer control state:
   `ChannelFaderComp::eventAbsoluteValueChanged`,
   `EqControlComp::eventAbsoluteValueChanged`,
   `MixerControlComp::eventAbsoluteValueChanged`,
   `DjMixerUnit::setChannelFaderPosition`,
   `DjMixerUnit::setEqPosition`,
   `ChannelFader::setParameter`, and `EqualizerNXS2::setParameter`.
3. The decompiler evidence actually supports the stated value flow:
   raw device integer -> normalized value -> deck/channel or band id -> engine
   sink, instead of a UI-only or preference-only path.
4. The spec does not jump from symbol names, UI component offsets, or inactive
   `DjMixerUnit + 0x2b0` child-state offsets to bridge-readable memory offsets.
5. The claimed bridge-readable chain through `DjEngineIF::singletonHolder`,
   engine `+0x40`, graph `+0xa8`, mixer vector `+0x458`, channel vector
   `+0x2c8`, channel graph `+0x470` fader, and `+0x460` EQ is actually
   supported by decompilation and passive memory reads.
6. The proposed `rb_offsets.py` chain lines match the existing chain semantics
   instead of being off by one dereference or final offset.
7. Deck 1 = channel index `0` and Deck 2 = channel index `1` are proven by
   one-control-at-a-time passive samples, not assumed from UI labels.
8. EQ band index `2` = LOW/BASS is proven for Deck 1 and Deck 2 by passive
   samples, while band indexes `0` and `1` are not overclaimed as high/mid.
9. Raw ranges and normalization are supported: upfader `0..1023`, LOW/BASS
   `0..255`, and non-authority FILTER param0/param1 `0.0..1.0`.
10. The FILTER chain is supported by static CFX audio/container evidence and
   passive one-control-at-a-time samples, including Deck 1/2 min/neutral/max,
   selected effect id `0`, `unit_channel`, and smoother raw `0/128/255`.
11. Local relaunch reacquire and direct-master-change survival are supported by
   passive samples after PID/base change and after raw master `0`/`1` changes.
12. Other Rekordbox versions, actual play/stop survival with loaded tracks,
   missing-value detection, thresholds, and runtime freshness remain explicit
   validation gaps.
13. `rekordcrate` / `DJMMYSETTING.DAT` preference settings are not mistaken for
   live upfader/EQ/filter state.

## Review Surface C - Implementation Handoff Safety

Try to disprove:

1. The future reader path reuses the existing `RBStateReader` / `rb_offsets.py`
   fail-closed model instead of inventing an unrelated runtime reader.
2. The 200 Hz `StateManager` push loop gains no blocking I/O, Ghidra work,
   filesystem reads, subprocess calls, locks, MIDI, serial, or network work.
3. The resolver is pure and directly testable.
4. `MASTER_CHANGED` no longer writes `active_deck` directly while mixer
   authority is valid.
5. Playing-only mirror auto-switch cannot promote a fader-down playing deck
   while mixer authority is valid.
6. Status/heartbeat stops conflating `master` and `active_deck`.
7. Missing one deck's mixer state makes mixer authority invalid; no one-sided
   guessing.
8. SoundSwitch, lasers, LEDs/Govee, scripted/autoloop mode, beat/BPM/elapsed,
   and pack output continue to follow the selected `active_deck`.

## Minimum Verification

Run only software/read-only commands unless explicitly approved otherwise:

```bash
git status --short --branch
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

If implementation code exists by the time you review, also run the narrow tests
named by the implementation spec plus:

```bash
python3 -m unittest discover tests
```

If a command cannot run, mark it unverified. These checks do not prove live
Rekordbox mixer behavior or hardware output.

## Required Response

Return one verdict: `APPROVE`, `REVISE`, or `REJECT`.

Then provide:

1. findings first, ordered BLOCKER/HIGH/MEDIUM/LOW, each with current
   `file:line`, evidence, impact, and the smallest required correction;
2. a requirement-by-requirement audit of surfaces A-C marked confirmed,
   contradicted, or unverified;
3. exact commands run and results;
4. explicit uncertainty labels for all RE claims;
5. a necessity/overreach verdict: what must exist for active-deck authority, and
   what the spec should delete or defer.
