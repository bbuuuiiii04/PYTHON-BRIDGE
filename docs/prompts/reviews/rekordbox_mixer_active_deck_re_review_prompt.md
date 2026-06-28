---
doc_status: active-review-prompt
truth_level: reverse-engineering-review-instructions
last_verified_commit: b1e5fd6
last_verified_date: 2026-06-28
validation_scope: adversarial review of Rekordbox mixer active-deck RE reasoning and implementation handoff; review-only; no live sampling/hardware authority
---

# ChatGPT adversarial review - Rekordbox mixer active-deck RE

You are the independent adversarial reviewer for `rb_ss_bridge_v2`. Review the
reverse-engineering process and reasoning for Rekordbox 7.2.11 mixer
active-deck authority. Do not implement fixes.

Repo: `/Users/bbui/rb_ss_bridge_v2`
Branch: `main`
Planning head: `b1e5fd63ea5a87432160d5ab78da07333dda60b3`

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

Treat it as a local artifact to inspect or regenerate, not as committed proof.

## Required Reads

Read these first:

- `AGENTS.md`
- `docs/architecture/active_deck_authority.md`
- `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md`
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

## Review Surface B - Static RE Reasoning

Treat static candidates as suspects, not proof. Try to disprove:

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
4. The spec does not jump from symbol names, UI component offsets, or
   `DjMixerUnit` child-state offsets to stable bridge-readable memory offsets.
5. The `DjMixerUnit + 0x2b0` per-channel child-state candidate is not treated
   as a valid read target until a stable root pointer, object lifetime, and
   Deck 1/Deck 2 ownership are proven.
6. Candidate ids near `ChannelFaderComp + 0x248`,
   `EqControlComp + 0x288`, and `MixerControlComp + 0x278` are not assumed to
   be Deck 1/Deck 2 without independent evidence.
7. EQ band indexes `0`, `1`, and `2` are not assumed to be low/mid/high until
   passive proof maps them to physical controls.
8. Deck/channel ownership must be proven independently and cannot be assumed
   from UI labels or function names.
9. Raw values, neutral points, top/down labels, bass ordering, and stability
   timing remain unknown until passive proof exists.
10. `rekordcrate` / `DJMMYSETTING.DAT` preference settings are not mistaken for
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
