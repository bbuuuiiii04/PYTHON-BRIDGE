---
doc_status: active-implementation-prompt
truth_level: static-and-passive-live-re-closed-handoff
last_verified_commit: a82cf16
last_verified_date: 2026-06-29
validation_scope: handoff after Rekordbox 7.2.11 local RE closure for Deck 1/2 upfader, LOW/BASS EQ, CFX FILTER param0/param1, Deck 1 mid fader, relaunch reacquire, and mixer-chain readability after operator-labeled master-button actions; implementation-precision review findings folded into active spec/prompt; runtime implementation and hardware output unvalidated
---

# Codex Task - Implement Rekordbox Mixer Active-Deck Authority

You are continuing `/Users/bbui/rb_ss_bridge_v2` from a completed local
Rekordbox 7.2.11 mixer RE pass. This handoff is for implementation and
software verification unless the operator explicitly reopens RE scope in the
current turn.

Work on local `main`. Do not create a branch or worktree. Do not restart the
bridge, SoundSwitch, or any hardware-adjacent runtime unless the operator
explicitly approves that live action in the current turn. Do not open MIDI,
serial, DMX, Enttec, Govee, SoundSwitch output, lasers, LEDs, or lighting
hardware unless explicitly approved in the current turn.

## Read First

1. `AGENTS.md`
2. `PRIVATE_OPERATOR_PROFILE.md` if present, but do not quote or commit private
   content.
3. `docs/architecture/active_deck_authority.md`
4. `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md`
5. `docs/research/rekordbox_mixer_active_deck_re_evidence.md`
6. Current code, re-resolving line numbers yourself:
   - `rb_offsets.py`
   - `rb_state_reader.py`
   - `rb_memory.py`
   - `models.py`
   - `state_manager.py`
   - `runtime_status.py`

Use executable code over docs when they conflict.

## Current Code Truth

- Runtime code still treats Rekordbox master and playing-only mirror switching
  as active-deck authority.
- `rb_offsets.py` still parses a fixed legacy layout:
  `master_deck`, `bpm_per_deck`, `live_pos_per_deck`,
  `track_info_per_deck`, and `anlz_path_per_deck`.
- Mixer chains cannot be exposed by appending anonymous trailing lines. Add
  named optional fields and parser/model tests.
- `RBStateReader._follow_float()` rejects valid mixer edge values with
  `0.0 < v < 1000.0`. Mixer reads need a separate finite-f32 helper with
  signal-specific ranges.
- `RBStateReader` currently maps raw Rekordbox Deck A/C to bridge Deck 1 and raw
  Deck B/D to bridge Deck 2, then loops all four raw decks. Under mixer authority,
  resolver-support `PLAY`, `PAUSE`, and direct `MASTER_CHANGED` must be raw Deck
  A/B only; raw Deck C/D must not update Deck 1/2 eligibility or
  `rb_master_deck`.
- `StateManager._on_master_changed()` still writes
  `self._os.active_deck = new_deck` directly.
- `OutputState` does not yet carry `rb_master_deck` validity/freshness/source.
  Do not default Deck 1 as proven Rekordbox master truth.
- Current `StateManager` PLAY/PAUSE handling only mutates `DeckState.playing`.
  The implementation must rerun/apply the active-deck resolver immediately after
  those mutations.
- `StateManager._do_resume()` can also correct an empty-deck mismatch by
  writing `self._os.active_deck = mirror` directly.
- OSC `/bridge/track_loaded` currently falls back to `get_active_deck()` when no
  last-loaded deck exists. After `active_deck=0` exists, scripted arm/clear must
  reject/defer when both last-loaded deck and active deck are non-1/2.
- `runtime_status._heartbeat_payload()` still reports
  `"master": active_deck`.

## RE Evidence Now Closed For Local 7.2.11

No local Rekordbox 7.2.11 Deck 1/2 pointer/value-mapping unknown remains for
upfader, LOW/BASS EQ, CFX FILTER param0/param1, Deck 1 midpoint, local relaunch
reacquisition, or mixer-chain readability after operator-labeled master-button
actions. Direct-master byte authority is existing bridge code behavior, not a
field proven by the mixer JSONL artifact.

Artifacts:

- Static binary: `/tmp/rbss_re/rekordbox_7_2_11_arm64`
- Static dumps:
  `/tmp/rbss_re/ghidra_candidate_dump.txt`,
  `/tmp/rbss_re/ghidra_singleton_dump.txt`,
  `/tmp/rbss_re/ghidra_input_channel_dump.txt`,
  `/tmp/rbss_re/ghidra_mixer_index_dump.txt`,
  `/tmp/rbss_re/ghidra_cfx_dump.txt`,
  `/tmp/rbss_re/ghidra_filter_audio_dump.txt`,
  `/tmp/rbss_re/ghidra_colorfx_unit_dump.txt`,
  `/tmp/rbss_re/ghidra_djsystem_fx_dump.txt`,
  `/tmp/rbss_re/ghidra_fx_processor_dump.txt`,
  `/tmp/rbss_re/ghidra_colorfx_deep_dump.txt`
- Passive samples:
  `/tmp/rbss_re/mixer_proof_snapshots.jsonl`,
  `/tmp/rbss_re/cfx_mixer_samples.jsonl`

Use these chains exactly for Rekordbox `7.2.11` offset records:

```text
Deck 1 upfader raw:       04E16EE8 A8 458 0 2C8 0 470 30
Deck 2 upfader raw:       04E16EE8 A8 458 0 2C8 8 470 30
Deck 1 LOW/BASS raw:      04E16EE8 A8 458 0 2C8 0 460 30 38
Deck 2 LOW/BASS raw:      04E16EE8 A8 458 0 2C8 8 460 30 38
Deck 1 FILTER param0:     04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 E8
Deck 2 FILTER param0:     04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 E8
Deck 1 FILTER param1:     04E16EE8 A8 458 0 2C8 0 480 0 1E0 0 88 0 EC
Deck 2 FILTER param1:     04E16EE8 A8 458 0 2C8 8 480 0 1E0 0 88 0 EC
```

Ranges:

- Upfader raw: `0.0..1023.0`, normalize `raw / 1023.0`.
- LOW/BASS raw: `0.0..255.0`, normalize `raw / 255.0`.
- FILTER param0/param1: already normalized `0.0..1.0`.
- FILTER smoother raw: `0..255`, neutral `128`, for proof/debug only.

Filter rules:

- CFX FILTER is proven enough for optional reader/status tracking.
- FILTER must not affect active-deck authority.
- If implemented, validate vector bounds, selected effect id `0`,
  `unit_channel`, both-deck finite values, and freshness.
- Missing/ambiguous FILTER invalidates filter tracking only, not active-deck
  authority.

## GhidraMCP Reference

Do not rediscover or reinstall GhidraMCP. It was verified on 2026-06-28 with:

- Ghidra 11.3.2: `/Users/bbui/Desktop/ghidra_11.3.2_PUBLIC`
- project: `/Users/bbui/Desktop/Ghidra Projects/Rekordbox Mixer RE.gpr`
- program: `rekordbox_7_2_11_arm64`
- HTTP backend: `127.0.0.1:8080`
- plugin class persisted in CodeBrowser tool config:
  `com.lauriewired.GhidraMCPPlugin`

If an implementation review needs to recheck static evidence, start with:

```bash
curl -fsS --max-time 5 http://127.0.0.1:8080/segments | sed -n '1,20p'
```

Then use:

```json
mcp__ghidra.list_segments({"limit":5,"offset":0})
mcp__ghidra.decompile_function_by_address({"address":"0x10219e9b8"})
```

Expected proof: `DjUnitAudioGraph::getMixerControl` loads
`*(param_1 + 0x458)`, bounds with `*(param_1 + 0x464)`, and returns the
selected element plus `0x180`.

If `curl` says connection refused, use this recovery path only if static RE is
actually needed in that turn:

```bash
osascript <<'APPLESCRIPT'
tell application "Terminal"
  do script "cd /Users/bbui && '/Users/bbui/Desktop/ghidra_11.3.2_PUBLIC/support/launch.sh' fg jdk Ghidra \"\" \"\" ghidra.GhidraRun '/Users/bbui/Desktop/Ghidra Projects/Rekordbox Mixer RE.gpr'"
end tell
APPLESCRIPT
```

Wait for Ghidra to open the Rekordbox project. If the program is not loaded,
open CodeBrowser from the Project Manager Tool Chest, press `Cmd-O` in
CodeBrowser, select `rekordbox_7_2_11_arm64`, press OK, and choose `No` if
Ghidra asks to analyze.

## Implementation Tasks

1. Add named mixer offset fields for Deck 1/2 upfader and LOW/BASS. Add optional
   named FILTER fields only if exposing filter tracking/status in the same
   patch.
2. Add parser/model tests proving Rekordbox `7.2.11` exposes the named fields
   and older records without mixer fields fail closed.
3. Add a mixer-specific finite-f32 reader. Accept valid edge values and reject
   NaN, infinity, unreadable chains, null chains, and out-of-range values.
4. Publish decoded per-deck mixer labels and both-deck validity/freshness
   without blocking the 200 Hz push loop.
5. Suppress raw Deck C/D direct-reader `PLAY`, `PAUSE`, and direct
   `MASTER_CHANGED` as resolver-support inputs. Preserve SoundSwitch Deck 3/4
   fanout only as downstream routing after a resolved Deck 1/2 show deck exists.
6. Add a pure active-deck resolver matching
   `docs/architecture/active_deck_authority.md`.
7. Preserve `rb_master_deck` separately from `active_deck`, with explicit
   validity/freshness/source fields. Startup, unreadable, sentinel/no-master,
   unsupported, or stale direct master must not silently become Deck 1.
   `MASTER_CHANGED` must update `rb_master_deck` and must not directly overwrite
   `active_deck` while mixer authority is valid.
8. Specify and test neutral/equal tie behavior and invalid mixer fallback when
   `rb_master_deck` is unavailable/stale; never synthesize Deck 1 as master.
9. Rerun/apply the resolver after StateManager handles `PLAY` or `PAUSE`.
   Active `PAUSE` must idle/switch through the resolver; non-active `PLAY` must
   become eligible only through resolver/stability.
10. Reject/defer OSC scripted arm/clear when no valid last-loaded or active
    Deck 1/2 exists, and reject `SCRIPTED_ARM`/`SCRIPTED_CLEAR` deck `0` before
    any `_deck[0]` indexing.
11. Suppress old playing-only mirror auto-switch as an independent authority
   while mixer authority is valid.
12. Suppress resume-time direct `active_deck` correction as an independent
   authority while mixer authority is valid.
13. Update status/heartbeat so `master` no longer means `active_deck`. Expose
    `active_deck`, `rb_master_deck`, master validity/freshness/source, mixer
    validity, decoded fader/bass, and authority reason.
14. Keep SoundSwitch, laser, LED/Govee, scripted, and autoloop behavior unchanged
    after a selected `active_deck` is chosen.

## Remaining Validation Gaps

- Runtime implementation does not exist yet.
- Actual play/stop survival with loaded tracks was not proven. After relaunch,
  Deck 1/2 had no loaded tracks, so the play/pause probe did not advance
  live-position counters.
- Rekordbox versions other than local `7.2.11.0342` are unvalidated.
- Hardware-visible behavior is unvalidated.

## Required Checks

Run targeted tests for the files you change, and before closeout run:

```bash
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

Do not run hardware tests or claim hardware validation unless the operator
explicitly authorizes a hardware validation turn and the result is logged.

## Finish

Report:

- changed files
- RE evidence artifact paths used
- test/check commands and results
- exact remaining validation gaps
- whether any live sampling, relaunch, bridge restart, SoundSwitch action, or
  hardware action happened
- whether a bridge restart is needed for the running process to use the change

Plain-language operator summary must include:

- what the future bridge behavior should do differently live
- what remains unchanged today
- how to recognize healthy future mixer authority in status/logs
- what to watch for in SoundSwitch, lasers, LEDs/Govee, Rekordbox reader state,
  and bridge logs
- what was software/static/passive-RE verified
- what remains hardware-unvalidated
- exact approval gates before any restart, relaunch, capture, toggle, or
  hardware-adjacent check
