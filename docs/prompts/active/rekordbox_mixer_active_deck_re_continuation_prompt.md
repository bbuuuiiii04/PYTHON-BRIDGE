---
doc_status: active-research-prompt
truth_level: static-and-passive-live-re-instructions
last_verified_commit: c14bff1
last_verified_date: 2026-06-28
validation_scope: continuation prompt for Rekordbox mixer active-deck reverse engineering; static/offline work allowed; passive live sampling requires explicit current-turn operator approval; no runtime implementation or hardware authority
---

# Codex Task - Continue Rekordbox Mixer Active-Deck RE

You are continuing reverse engineering for `/Users/bbui/rb_ss_bridge_v2`.
This is RE and documentation work, not runtime implementation.

Work on local `main`. Do not create a branch or worktree. Do not restart the
bridge. Do not open MIDI, serial, DMX, Enttec, Govee, SoundSwitch output,
lasers, LEDs, or lighting hardware. Do not implement active-deck runtime code
unless the operator explicitly changes scope in the current turn.

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

## Hard Boundaries

- Static repository inspection, static Ghidra/GhidraMCP reads, and offline
  decompilation are allowed.
- Process-memory reads, live Rekordbox sampling, physical control movement, or
  relaunch/survival checks require explicit operator approval in that same turn.
- If GhidraMCP is unavailable, say so and use static headless dumps or local
  decompilation only. Do not imply MCP evidence.
- Do not treat `rekordcrate` or `DJMMYSETTING.DAT` preferences as live mixer
  fader/EQ/filter state.
- Do not make support claims beyond the local Rekordbox 7.2.11 proof unless you
  have new evidence.

## GhidraMCP Ready State

Do not rediscover or reinstall GhidraMCP. It was verified on 2026-06-28 with:

- Ghidra 11.3.2: `/Users/bbui/Desktop/ghidra_11.3.2_PUBLIC`
- project: `/Users/bbui/Desktop/Ghidra Projects/Rekordbox Mixer RE.gpr`
- program: `rekordbox_7_2_11_arm64`
- HTTP backend: `127.0.0.1:8080`
- plugin class persisted in CodeBrowser tool config:
  `com.lauriewired.GhidraMCPPlugin`

Start with these checks:

```bash
curl -fsS --max-time 5 http://127.0.0.1:8080/segments | sed -n '1,20p'
```

Then use:

```json
mcp__ghidra.list_segments({"limit":5,"offset":0})
mcp__ghidra.decompile_function_by_address({"address":"0x10219e9b8"})
```

Expected proof for the decompile check: `DjUnitAudioGraph::getMixerControl`
loads `*(param_1 + 0x458)`, bounds with `*(param_1 + 0x464)`, and returns the
selected element plus `0x180`.

If the Codex session does not expose the `mcp__ghidra` namespace, use tool
discovery for Ghidra MCP tools; do not debug the plugin first.

If `curl` says connection refused, use this exact recovery path:

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
Ghidra asks to analyze. Re-run the `curl` and MCP checks above.

Do not use `ghidraRun ghidra:/Users/...?/rekordbox_7_2_11_arm64`; it is the
wrong launch form and produces "Invalid Project".

Local artifacts from the previous pass may exist:

- `/tmp/rbss_re/ghidra_candidate_dump.txt`
- `/tmp/rbss_re/ghidra_singleton_dump.txt`
- `/tmp/rbss_re/ghidra_input_channel_dump.txt`
- `/tmp/rbss_re/ghidra_mixer_xrefs.txt`
- `/tmp/rbss_re/ghidra_mixer_index_dump.txt`
- `/tmp/rbss_re/mixer_proof_snapshots.jsonl`
- `/tmp/rbss_re/rekordbox_7_2_11_arm64`

Treat them as local artifacts to inspect or regenerate, not committed proof by
themselves.

## Goals

Resolve as many of these as possible, in order:

1. Static reconciliation: explain exactly how
   `DjUnitAudioGraph::getMixerControl(0)` returning a view derived from
   `*(graph + 0x458)` relates to the passive-verified chain
   `mixer_vector -> mixer_base -> channel_vector`. Do not change candidate
   chain semantics unless passive proof validates the alternate endpoint.
2. Deck 1 intermediate/audible upfader proof: if operator approval is granted,
   capture a Deck 1 mid/audible sample with one-control-at-a-time movement.
3. Filter candidate: use static RE first. Only run passive filter sampling after
   explicit approval. Keep filter out of active-deck authority.
4. Survival checks: if approved, test whether proven fader/LOW chains survive
   play/stop, master changes, and Rekordbox relaunch. Each case must state
   whether PID/base changed and whether the chain was reacquired.
5. Missing/unreadable detection: define the fail-closed conditions a runtime
   reader must expose for both-deck mixer authority.

## Passive Sampling Rules

If, and only if, the operator approves passive live sampling:

- Ask for one physical action at a time in plain language.
- Own the passive read mechanics yourself.
- Do not touch the bridge, SoundSwitch, or hardware outputs.
- Capture repeated samples for each physical position.
- Record PID, base address, full chain endpoints, raw values, normalized values,
  and which single control moved.
- Fail closed on missing or ambiguous evidence. Do not infer from labels alone.

Minimum useful passive actions:

- Deck 1 upfader at a clearly audible middle position.
- Deck 1 filter neutral and moved, only if static RE has a credible candidate.
- Deck 2 filter neutral and moved, only if static RE has a credible candidate.
- Optional survival checks: play/stop, master change, and relaunch, each with
  explicit operator approval.

## Implementation-Handoff Constraints To Preserve

- `rb_offsets.py` currently has a fixed parser layout. Future implementation
  must add named mixer fields and tests; appending anonymous extra lines is not
  enough.
- `RBStateReader._follow_float()` rejects valid mixer values `0.0` and
  `1023.0`. Future implementation needs a mixer-specific finite f32 helper with
  per-signal ranges.
- Upfader range is `0.0..1023.0`; LOW/BASS range is `0.0..255.0`.
- One missing or invalid deck invalidates mixer authority for both decks.
- The 200 Hz `StateManager` push loop must not gain Ghidra, process-memory
  scanning, filesystem, subprocess, network, MIDI, serial, or hardware I/O.

## Deliverable

Update docs only if you collected or verified new evidence:

- `docs/research/rekordbox_mixer_active_deck_re_evidence.md`
- `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md`
- `docs/status/active_work_registry.md` if status/unknowns changed materially

If no new evidence was collected, return a concise report instead of editing.

Run, as applicable:

```bash
git status --short --branch
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

If implementation code was not changed, do not run hardware tests and do not
claim hardware validation.

## Finish

Report:

- changed files, if any
- exact static artifacts and passive artifacts used
- commands run and results
- confirmed, contradicted, and still-unknown RE claims
- whether any live sampling happened and what approval covered it
- whether any bridge restart, SoundSwitch action, or hardware action happened

Plain-language operator summary must include:

- what the future bridge behavior is still expected to do live
- what remains unchanged today
- how healthy future mixer authority should look in status/logs
- what to watch for in SoundSwitch, lasers, LEDs/Govee, Rekordbox reader state,
  and bridge logs
- what was software/static/passive-RE verified
- what remains hardware-unvalidated
- exact approval gates before any restart, relaunch, capture, toggle, or
  hardware-adjacent check
