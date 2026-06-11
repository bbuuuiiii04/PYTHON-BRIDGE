# Codex Handoff — SoundSwitch Catalog Importer + Per-Personality Enforcement Gate

## What you're building

Three PRs against `/Users/bbui/rb_ss_bridge_v2/` that let the bridge:
1. Read SoundSwitch's project files to know what laser looks exist
2. Let the operator tag each bridge scene with the actual SS look name (purely informational UI)
3. Optionally enforce per-personality that the executor never fires a scene outside the currently-active role's bank

**Full plan with rationale, design invariants, file map, and verification steps:**
`/Users/bbui/.claude/plans/lets-plan-out-this-gleaming-marble.md`

**Read the plan first.** It contains the full context including the seven design invariants. The rest of this document is the additional ground truth you need that's NOT in the plan.

---

## Ground truth that's NOT in the plan

### File format facts (verified by inspection — do not re-discover)

**`~/Music/SoundSwitch/default.ssproj/SoundSwitchAutoLoops.bin`** (918 bytes, magic `aa aa 09 55 03 00 00 00`)
- Encoding: UTF-16LE, **aligned at offset 0**
- Structure not fully decoded, but `re.findall(r'[\x20-\x7e]{3,}', data.decode('utf-16-le', errors='replace'))` extracts exactly 16 ordered strings: 4 bank headers followed by 12 look names
- Bank headers (always first 4): `'BREAKDOWN'`, `'GROOVE // MID ENERGY'`, `'BUILDUP // RISING'`, `'DROP // HIGH ENERGY'`
- Look names (remainder): `'RED  // AG1'`, `'RAINBOW  // AG'`, `'BLACKOUT'`, `'LAGGY 1/4 W '`, `'WHITE  // AG1'`, `'RAINBOW LAGGY'`, `'GREEN  // AG'`, `'New Autoloop'`, `'CYAN // AG1'`, `'PURPLE // AG1'`, `'GREEN  // AG1'`, `'BLUE // AG1'`

**`~/Music/SoundSwitch/default.ssproj/SoundSwitchAutoLoopsEx.bin`** (934 bytes, same magic)
- Same encoding (UTF-16LE, **offset 0**)
- 16 strings: same 4 bank headers + 12 different look names: `'NEON'`, `'NEON STUTTER'`, `'GREEN IN/OUT'`, `'GREEN'`, `'BLUE WAVING'`, `'BLUE FANNING'`, `'BLUE FANNING 2'`, `'CONVERGING'`, `'WHITE STATIC'`, `'RED STATIC'`, `'GREEN STATIC'`, `'CYAN STATIC'`

**`~/Music/SoundSwitch/default.ssproj/SoundSwitchVenues.bin`** (220886 bytes, same magic)
- Encoding: UTF-16LE **at offset +1** (this is the load-bearing quirk — `data.decode('utf-16-le')` at offset 0 returns only 23 strings; at offset 1 it returns 292)
- Use exactly: `text = data[1:].decode('utf-16-le', errors='replace')` then `re.findall(r'[\x20-\x7e]{3,}', text)`
- Contains: fixture parameter names, positions, all static look names, bank headers, per-BPM groove variants, track-specific cues
- Bank headers inside Venues.bin include: `'INTRO'`, `'BREAKDOWN'`, `'BUILDUP'`, `'DROP'`, `'STATIC LASERS'`, `'TRACK SPECIFIC CUES'`, `'AUTOLOOPS'`, `'FLOWER'`, `'COLOR'`, `'GREEN LASER SIZES'`, plus `'FOUNDATION - GROOVE 124/128/134/139/149 bpm'` per-BPM sets
- Static look needles that MUST be findable: `'STROBE EFFECT'`, `'BLACK OUT'`, `'RAINBOW STROBE'`, `'SHUTTER'`, `'STROBE ONLY'`, `'NEON'`, `'FOUNDATION - GROOVE 128 bpm'`, `'FKDASPKR (cutout)'`
- Caveat: needles whose names appear in BOTH AutoLoopsEx.bin and Venues.bin (e.g. `'NEON'`) will appear in both catalog records — dedupe by `(source_file, name)`, not by `name` alone

### Pcap-confirmed protocol facts

- `~/Desktop/VDJ AND SOUNDSWITCH AUTOLOOP COMMUNICATION.pcapng` was decoded: ~60,000 OS2L messages, only event types `subscribe` (1), `subscribed` (59,105), `beat` (555)
- **Zero `cmd` events.** OS2L's `cmd` field is controller→host only; you cannot use OS2L to trigger SS buttons by name. **MIDI is the only host→SS named-trigger path.** Do not attempt to add a `cmd`-based trigger.

### Bridge restart safety (load-bearing)

After every restart during testing:
```
pgrep -f rb_ss_bridge_v2 | wc -l
```
Must return `1`. Multiple instances fight each other and clear each other's SS shows. The user has lost work to this. Use the menu-bar toggle (`com.bbui.bridge-menubar`) to stop/start, not manual `kill` + relaunch.

### Existing code reuse map (line numbers from inspection)

Reuse these — do not re-implement:
- `ss_library_scanner.py:35-39` `parse_trackmap_filepaths` — UTF-16LE bytes→strings pattern. Mirror this style for the new bin parsers.
- `ss_library_scanner.py:13` `_SS_TRACKMAP_ENV` — env-var override convention. Mirror as `RBSS_SS_PROJECT_DIR` for the importer.
- `laser_executor.py:324-338` `_bank_for_role(role)` — gate calls this directly.
- `laser_executor.py` near line 175 `_restore_role_state(role, cursor_before, active_before)` — gate MUST call this on block to roll back the `_role_cursors` round-robin cursor. Failure to do so causes the bank cursor to drift; the next decision picks the wrong slot. This is the bug you will ship if you skip this step.
- `laser_executor.py` `_record_gate("category_enforce_blocked")` — decision-log row.
- `laser_executor.py` `_resolve_pending_blackout(reason=...)` — call on block during drop crossing or pre-drop blackout will hang. Use reason `"drop_crossing_category_blocked"`.
- `tools/laser_config_ops.py:695-824` `apply_mapping` — already preserves unknown fields via deepcopy, so adding `ss_look_name` requires no changes to this function.
- `tools/laser_config_ops.py:1011-1046` `save_config_atomically` — atomic backup pattern; no new write infrastructure needed.
- `tools/laser_pad_web.py:704-732` `_POST_ROUTES` dict — mirror this pattern for `_GET_ROUTES` to add `/api/ss_catalog`.

### Live config caveats

- `/Users/bbui/rb_ss_bridge_v2/config/laser_director.json` is the production config: 39 scenes, 2 personalities (`house`, `dubstep`), `enabled=true`, `dry_run=false`. Atomic backups land alongside as `laser_director.json.bak-YYYYMMDD-HHMMSS-microseconds`. 15 backups already exist from today — file is hot.
- The schema additions (`ss_look_name` on `LaserScene`, `category_enforce` + `category_enforce_roles` on `LaserPersonality`) are additive only. Existing config must load unchanged; defaults preserve current behavior (`ss_look_name=""`, `category_enforce=False`).
- Live config has zero `ss_look_name` fields today. Migration is forward-compat: empty string is the safe default; gate is per-personality opt-in (off by default), so even if the user never opens the pad UI to tag looks, nothing changes.

### Phrase label trap

`smart_phrasing.py:13` defines `PhraseLabel = Literal["up", "chorus", "low", "other"]`. Do NOT add code that compares scenes against `current_phrase_label` strings like "groove" or "drop" — those values never appear. The director's `role` field is the right enforcement input. Bank membership is the right truth. Re-read invariant #1 of the plan before coding the gate.

### Importer failure must not crash boot

If `~/Music/SoundSwitch/default.ssproj/` is missing or any `.bin` file fails to parse:
- Log `[SS-CATALOG] parse-fail path=… err=…` at WARNING
- Return an empty `LookCatalog`
- Bridge boots normally; UI dropdown becomes a free-text fallback
- Enforcement gate is unaffected because it consults bridge-side personality banks, not the catalog

### Plist audit — read-only

`~/Library/Preferences/com.soundswitch.SoundSwitch.plist` is a binary plist. Use `plistlib.load(open(path,'rb'))`. Log keys `randomiseAutoLoops`, `autoloopRepeatMode`, `overrideScriptedTracks` once at INFO during bridge startup. **Do not modify the file.** SS owns it.

---

## Implementation order

Follow the plan's PR-A → PR-B → PR-C order. Do not interleave. Each PR must pass its own tests before the next begins.

For each PR:
1. Implement the change.
2. Run targeted tests (`pytest tests/test_<new_module>.py -v`).
3. Run the full test suite (`pytest -q`) to confirm no regression.
4. Run the bridge in dry-run mode and tail `/tmp/bridge.log` to confirm clean startup.
5. Update `docs/architecture/runtime_invariants.md` and `docs/architecture/current_architecture.md` as needed.

---

## Hard rules

- **Do not** modify any file under `~/Music/SoundSwitch/`. The importer is read-only.
- **Do not** modify `~/Library/Preferences/com.soundswitch.SoundSwitch.plist`. Read-only audit only.
- **Do not** add an `ss_category` field to `LaserScene`. The plan explicitly cuts this; bank membership is truth.
- **Do not** add a heartbeat re-assert. The plan explicitly cuts this; re-firing MIDI while SS plays a look causes stutter or toggle.
- **Do not** auto-derive any scene's role from SS metadata. The same SS look may legitimately back scenes in any role of any personality.
- **Do not** make manual or emergency role bypass conditional. Operator override is sacred.
- **Do not** skip `_restore_role_state` on gate block.
- **Do not** fall back to `scene_def.fallback_scene` on gate block — fall back to `personality.default_scene`. The Plan agent's reasoning: `scene_def.fallback_scene` is per-scene metadata that may itself reference a wrong-bank scene.
- **Do not** start the bridge manually during testing — use the menu-bar toggle. After any start, verify `pgrep -f rb_ss_bridge_v2 | wc -l` returns `1`.

---

## Verification (copy from plan, executed after PR-C lands)

Reproduce exactly the verification steps from the plan file's "Verification" section. Critical steps:

1. After landing PR-C, **bridge behavior must be unchanged** from before until a personality is explicitly toggled to `category_enforce=True`.
2. Toggle `house.category_enforce=True` only. Live-mix a house track and verify the decision log shows `category_enforce_blocked` rows when a wrong-bank scene was attempted, and that fallback fired cleanly.
3. Switch to dubstep personality mid-set; verify enforcement disengages.
4. Set per-role granularity (`house.category_enforce_roles=("drop",)`); verify only drops enforce.
5. Set `RBSS_CATEGORY_ENFORCE=0`; verify gate becomes pass-through globally.

If any verification step fails, do not commit. Roll back, diagnose, retry.
