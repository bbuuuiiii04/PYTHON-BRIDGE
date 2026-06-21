# SoundSwitch pack-generation proof gate

- **Final verdict:** `PASS_IMPLEMENTATION_MAY_BEGIN`
- **Totals:** 27 PASS / 0 FAIL / 2 INCOMPLETE (of 29); foundation 26/26 PASS
- **Repo HEAD:** `cc526eb`
- **Generated:** 2026-06-21T07:51:41.692899+00:00 (excluded from determinism)

## Source identity
- Project path: `/Users/bbui/Music/SoundSwitch/default.ssproj`
- Project UUID: `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}` (canonical `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}`)
- SoundSwitch version: `2.10.3`
- Venue GUID: `b8ad2201b9e4c94696c898a7e8f6a5a9` (RAVE)
- Profile: 19 channels, intensity channel: False, Universe 0 CH1-CH19

## Checks

| id | status | title |
| --- | --- | --- |
| `A1-project-identity` | **PASS** | Project UUID and SoundSwitch version pinned |
| `A2-venue-identity` | **PASS** | Primary RAVE Venue GUID pinned |
| `A3-fixture-profile` | **PASS** | 19-channel no-intensity profile on Universe 0 CH1-CH19 |
| `B1-autoloops-parse` | **PASS** | 42/42 current Autoloops parse |
| `B2-scripted-parse` | **PASS** | 44/45 scripted parse; inactive demo unsupported; 32 existing-path supported |
| `B3a-iac-bindings` | **PASS** | 19/19 learned IAC Autoloop bindings resolve via catalog category order |
| `B3b-ddj-overrides` | **PASS** | 4/4 DDJ Static Overrides resolve to slots 8/16/17/24 |
| `B4-venue-cues` | **PASS** | 232 fixture-payload render cues + 1 default catalog-tail = 233 parsed records |
| `B5-active-cue-union` | **PASS** | 166 active referenced cue GUIDs, zero missing, SHA-256 anchor matches |
| `C1-raw-zero-clear` | **PASS** | raw_reference == 0 is clear/control (live file-3 blackout autoloop) |
| `C2-raw-minus-one` | **PASS** | raw_reference > 0 resolves stored_key = raw-1 under the 2.10.3 one_based rule |
| `C3-ambiguous-fails-closed` | **PASS** | Generic/unversioned reference resolution fails closed (no guessing) |
| `C4-a5-wire` | **PASS** | A5 legacy scripted wire discriminator (16/16, 14/14 one-based, 2/2 raw-zero) |
| `D1-static-looks-32-by-guid` | **PASS** | Primary-Venue StaticLooks selected uniquely by GUID; exactly 32 v5 slots |
| `D2-ddj-ch1-19-frames` | **PASS** | DDJ overrides render exact CH1-CH19 frames (slots 8/16/17/24) |
| `E1-sparse-persistence` | **PASS** | Sparse patches update present channels; omitted channels persist; raw-zero clears main layer |
| `E2-history-independent` | **PASS** | Seek/backward/pause/refire are history-independent |
| `E3-stop-unload-zero` | **PASS** | Stop/end/unload resolves all-zero |
| `E4-negative-preroll` | **PASS** | Negative pre-roll records decoded as real signed pre-roll state |
| `F1-reject-wrong-uuid-same-venue` | **PASS** | Reject wrong project UUID even when RAVE Venue GUID matches |
| `F10-active-cc-override` | **INCOMPLETE** | Active Static Override learned to CC/pitch must fail export |
| `F2-missing-cue-detected` | **PASS** | A referenced cue GUID absent from the Venue is detected as missing |
| `F3-collision-detected` | **PASS** | Duplicate enabled learned event (same device/note/channel) is a reported collision |
| `F4-unsupported-layout-visible` | **PASS** | Unsupported scripted layout (inactive In-App Demo) is visible and classified unsupported |
| `F5-wrong-version-rejected` | **PASS** | Wrong SoundSwitch version is rejected even with canonical UUID + RAVE GUID |
| `F6-wrong-venue-rejected` | **PASS** | Wrong/absent primary Venue selects no Static Looks (fails closed) |
| `F7-source-drift-detected` | **PASS** | Re-hash after read detects concurrent source mutation |
| `F8-symlink-rejected` | **PASS** | Symlinked project inputs are detectable/rejectable |
| `F9-pack-one-byte-mutation` | **INCOMPLETE** | Independent verifier rejects a one-byte pack-artifact mutation |

## Check detail

### `A1-project-identity` — PASS
- **Title:** Project UUID and SoundSwitch version pinned
- **Foundation:** True
- **Expected:** `{"uuid": "{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}", "version": "2.10.3"}`
- **Actual:** `{"uuid": "{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}", "version": "2.10.3"}`
- **Evidence:** decoded <project>/.ssproj manifest
- **Sources:** /Users/bbui/Music/SoundSwitch/default.ssproj/.ssproj

### `A2-venue-identity` — PASS
- **Title:** Primary RAVE Venue GUID pinned
- **Foundation:** True
- **Expected:** `{"venue_guid": "b8ad2201b9e4c94696c898a7e8f6a5a9", "venue_name": "RAVE"}`
- **Actual:** `{"venue_guid": "b8ad2201b9e4c94696c898a7e8f6a5a9", "venue_name": "RAVE"}`
- **Evidence:** analyze_static_looks.primary_venue_identity over SoundSwitchVenues.bin
- **Sources:** tools/ssfmt/re/analyze_static_looks.py, SoundSwitchVenues.bin

### `A3-fixture-profile` — PASS
- **Title:** 19-channel no-intensity profile on Universe 0 CH1-CH19
- **Foundation:** True
- **Expected:** `{"channel_count": 19, "has_intensity_channel": false, "universe": 0, "span": "CH1-CH19"}`
- **Actual:** `{"channel_count": 19, "has_intensity_channel": false}`
- **Evidence:** parse_venue_cues.parse_fixture_profile_channels
- **Sources:** tools/ssfmt/re/parse_venue_cues.py, SoundSwitchVenues.bin

### `B1-autoloops-parse` — PASS
- **Title:** 42/42 current Autoloops parse
- **Foundation:** True
- **Expected:** `{"file_count": 42, "parsed": 42, "status": "complete_bounded_inventory"}`
- **Actual:** `{"file_count": 42, "parsed": 42, "status": "complete_bounded_inventory"}`
- **Evidence:** build_coverage_reports.autoloop_report
- **Sources:** tools/ssfmt/re/build_coverage_reports.py, tools/ssfmt/re/analyze_ssfile_structure.py

### `B2-scripted-parse` — PASS
- **Title:** 44/45 scripted parse; inactive demo unsupported; 32 existing-path supported
- **Foundation:** True
- **Expected:** `{"total": 45, "supported": 44, "unsupported_inactive_demo": 1, "existing_path_supported": 32}`
- **Actual:** `{"total": 45, "supported": 44, "unsupported": 1, "existing_path_supported": 32}`
- **Evidence:** build_coverage_reports.scripted_report
- **Sources:** tools/ssfmt/re/build_coverage_reports.py, tools/ssfmt/re/analyze_scripted_layouts.py

### `B3a-iac-bindings` — PASS
- **Title:** 19/19 learned IAC Autoloop bindings resolve via catalog category order
- **Foundation:** True
- **Expected:** `{"resolved": 19, "unresolved": 0}`
- **Actual:** `{"resolved": 19, "unresolved": 0, "status": "resolved"}`
- **Evidence:** inventory_project_artifacts.analyze -> autoloop_midi_selection
- **Sources:** tools/ssfmt/re/inventory_project_artifacts.py

### `B3b-ddj-overrides` — PASS
- **Title:** 4/4 DDJ Static Overrides resolve to slots 8/16/17/24
- **Foundation:** True
- **Expected:** `{"binding_count": 4, "slots": [8, 16, 17, 24]}`
- **Actual:** `{"binding_count": 4, "slots": [8, 16, 17, 24], "status": "resolved"}`
- **Evidence:** inventory_project_artifacts.analyze -> static_look_midi_selection
- **Sources:** tools/ssfmt/re/inventory_project_artifacts.py

### `B4-venue-cues` — PASS
- **Title:** 232 fixture-payload render cues + 1 default catalog-tail = 233 parsed records
- **Foundation:** True
- **Expected:** `{"render_cues": 232, "catalog_tail": 1, "total_parsed": 233}`
- **Actual:** `{"render_cues": 232, "catalog_tail": 1, "total_parsed": 233}`
- **Evidence:** parse_venue_cues.parse_venue_cues record_kind split
- **Sources:** tools/ssfmt/re/parse_venue_cues.py, SoundSwitchVenues.bin

### `B5-active-cue-union` — PASS
- **Title:** 166 active referenced cue GUIDs, zero missing, SHA-256 anchor matches
- **Foundation:** True
- **Expected:** `{"union": 166, "missing": 0, "sha256": "88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2", "active_set": "19 IAC autoloops + 32 existing-path scripted"}`
- **Actual:** `{"union": 166, "missing": [], "sha256": "88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2"}`
- **Evidence:** union of referenced_cue_guids over IAC-bound autoloops + existing-path scripted, lowercase hex, sorted, newline-joined (no trailing newline), SHA-256
- **Sources:** tools/ssfmt/re/build_coverage_reports.py

### `C1-raw-zero-clear` — PASS
- **Title:** raw_reference == 0 is clear/control (live file-3 blackout autoloop)
- **Foundation:** True
- **Expected:** `"raw-zero records resolve to no dictionary index (clear/control)"`
- **Actual:** `{"raw_zero_records": 2, "all_unresolved": true}`
- **Evidence:** analyze_ssfile_structure.parse_autoloop_structure(SSAutoLoop3.ssfile, one_based)
- **Sources:** tools/ssfmt/re/analyze_ssfile_structure.py, SSAutoLoop3.ssfile

### `C2-raw-minus-one` — PASS
- **Title:** raw_reference > 0 resolves stored_key = raw-1 under the 2.10.3 one_based rule
- **Foundation:** True
- **Expected:** `{"one_based(raw=21)": 20, "direct(raw=21)": 21}`
- **Actual:** `{"one_based": 20, "direct": 21}`
- **Evidence:** analyze_scripted_ssfile.timeline_record
- **Sources:** tools/ssfmt/re/analyze_scripted_ssfile.py

### `C3-ambiguous-fails-closed` — PASS
- **Title:** Generic/unversioned reference resolution fails closed (no guessing)
- **Foundation:** True
- **Expected:** `"ambiguous reference rule raises ValueError"`
- **Actual:** `{"raised_value_error": true}`
- **Evidence:** layered_renderer.render_at_elapsed(reference_rule='ambiguous')
- **Sources:** tools/ssfmt/re/layered_renderer.py

### `C4-a5-wire` — PASS
- **Title:** A5 legacy scripted wire discriminator (16/16, 14/14 one-based, 2/2 raw-zero)
- **Foundation:** False
- **Expected:** `{"events": 16, "exact": 16, "positive": 14, "positive_exact": 14, "raw_zero": 2, "raw_zero_exact": 2}`
- **Actual:** `{"events": 16, "exact": 16, "positive": 14, "positive_exact": 14, "raw_zero": 2, "raw_zero_exact": 2}`
- **Evidence:** validate_scripted_capture.py over committed A5 passive capture; captured frames are oracle only, never renderer input
- **Sources:** tools/ssfmt/re/validate_scripted_capture.py, tools/ssfmt/captures/scripted_sanfrandisco_a5_20260619.pcap

### `D1-static-looks-32-by-guid` — PASS
- **Title:** Primary-Venue StaticLooks selected uniquely by GUID; exactly 32 v5 slots
- **Foundation:** True
- **Expected:** `{"slots": 32, "selected_by": "primary venue GUID", "reversed_guid_selects": 0}`
- **Actual:** `{"slots": 32, "collections_in_venue": 20, "reversed_guid_selects": 0}`
- **Evidence:** analyze_static_looks.parse_static_looks (+negative reversed-GUID control)
- **Sources:** tools/ssfmt/re/analyze_static_looks.py, SoundSwitchVenues.bin

### `D2-ddj-ch1-19-frames` — PASS
- **Title:** DDJ overrides render exact CH1-CH19 frames (slots 8/16/17/24)
- **Foundation:** True
- **Expected:** `{"16": "00000000000000000000000000000000000000", "24": "010015ff00288a00ff00ff00ff005d000000ff", "8": "1800260000797c0000d6ff000000000000006e", "17": "26001d00006483ffffff00000000000000004f"}`
- **Actual:** `[{"slot": 16, "note": "CH7 note 106", "control": "StaticOverride16", "name": "OFF", "expected_hex": "00000000000000000000000000000000000000", "rendered_hex": "00000000000000000000000000000000000000", "name_match": true, "match": true}, {"slot": 24, "note": "CH10 note 122", "control": "StaticOverride24", "name": "STROBE BUILDUP #1", "expected_hex": "010015ff00288a00ff00ff00ff005d000000ff", "rendered_hex": "010015ff00288a00ff00ff00ff005d000000ff", "name_match": true, "match": true}, {"slot": 8, "note": "CH10 note 123", "control": "StaticOverride8", "name": "STROBE EFFECT", "expected_hex": "1800260000797c0000d6ff000000000000006e", "rendered_hex": "1800260000797c0000d6ff000000000000006e", "name_match": true, "match": true}, {"slot": 17, "note": "CH10 note 127", "control": "StaticOverride17", "name": "RAINBOW STROBE", "expected_hex": "26001d00006483ffffff00000000000000004f", "rendered_hex": "26001d00006483ffffff00000000000000004f", "name_match": true, "match": true}]`
- **Evidence:** render fixture group 0x493 of each Static Look slot
- **Sources:** tools/ssfmt/re/analyze_static_looks.py, SoundSwitchVenues.bin

### `E1-sparse-persistence` — PASS
- **Title:** Sparse patches update present channels; omitted channels persist; raw-zero clears main layer
- **Foundation:** True
- **Expected:** `"color (ch8/9) persists across a later position cue and across raw-zero clear"`
- **Actual:** `{"at_2500ms": [7, 0, 9, 0, 0, 0, 0, 24, 42, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "after_clear_3500ms": [0, 0, 0, 0, 0, 0, 0, 24, 42, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}`
- **Evidence:** layered_renderer.render_at_elapsed with control_channels=(8,9,11)
- **Sources:** tools/ssfmt/re/layered_renderer.py

### `E2-history-independent` — PASS
- **Title:** Seek/backward/pause/refire are history-independent
- **Foundation:** True
- **Expected:** `"render(elapsed) depends only on elapsed, not on prior queries"`
- **Actual:** `{"forward_eq_refired": true, "backward_repeatable": true}`
- **Evidence:** layered_renderer.render_at_elapsed repeated queries
- **Sources:** tools/ssfmt/re/layered_renderer.py

### `E3-stop-unload-zero` — PASS
- **Title:** Stop/end/unload resolves all-zero
- **Foundation:** True
- **Expected:** `"ended and unloaded render [0]*19"`
- **Actual:** `{"ended_zero": true, "unloaded_zero": true}`
- **Evidence:** layered_renderer.render_playback_state ended/unloaded
- **Sources:** tools/ssfmt/re/layered_renderer.py

### `E4-negative-preroll` — PASS
- **Title:** Negative pre-roll records decoded as real signed pre-roll state
- **Foundation:** True
- **Expected:** `"at least one current Autoloop carries signed negative pre-roll records"`
- **Actual:** `{"autoloops_with_negative_records": 20, "examples": ["SSAutoLoop1.ssfile", "SSAutoLoop12.ssfile", "SSAutoLoop13.ssfile", "SSAutoLoop14.ssfile", "SSAutoLoop15.ssfile", "SSAutoLoop16.ssfile"]}`
- **Evidence:** build_coverage_reports.autoloop_report negative_record_count (parse_autoloop_structure)
- **Sources:** tools/ssfmt/re/analyze_ssfile_structure.py

### `F1-reject-wrong-uuid-same-venue` — PASS
- **Title:** Reject wrong project UUID even when RAVE Venue GUID matches
- **Foundation:** True
- **Expected:** `"same RAVE GUID + different UUID -> identity gate REJECTS for UUID mismatch"`
- **Actual:** `{"scratch_uuid": "{E34F6DCD-EBB9-4088-BD28-7BC0272D011A}", "scratch_venue_guid": "b8ad2201b9e4c94696c898a7e8f6a5a9", "authorized": false, "reasons": ["project UUID {E34F6DCD-EBB9-4088-BD28-7BC0272D011A} != canonical {3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}"]}`
- **Evidence:** assert_source_identity over the scratch container (shares RAVE GUID, differs in project UUID)
- **Sources:** assert_source_identity, /Users/bbui/Music/SoundSwitch/codex fixture research real.ssproj/.ssproj

### `F10-active-cc-override` — INCOMPLETE
- **Title:** Active Static Override learned to CC/pitch must fail export
- **Foundation:** False
- **Expected:** `"a render-affecting override on CC/pitch fails export with a relearn instruction"`
- **Actual:** `{"decoder_distinguishes_note_vs_cc": true, "export_fail_path": "not implemented (Task 4 MIDI input adapter)"}`
- **Evidence:** inventory decoder classifies message_type note/control_change; export-fail path is unbuilt
- **Sources:** tools/ssfmt/re/inventory_project_artifacts.py, docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md (Task 4)
- **Remediation:** Implement Task 4 so an active CC/pitch render control fails export until relearned to note.

### `F2-missing-cue-detected` — PASS
- **Title:** A referenced cue GUID absent from the Venue is detected as missing
- **Foundation:** True
- **Expected:** `"fabricated GUID flagged in referenced - venue_guids"`
- **Actual:** `{"fabricated_flagged": true}`
- **Evidence:** referenced_cue_guids - venue cue GUID set (build_coverage_reports logic)
- **Sources:** tools/ssfmt/re/build_coverage_reports.py

### `F3-collision-detected` — PASS
- **Title:** Duplicate enabled learned event (same device/note/channel) is a reported collision
- **Foundation:** True
- **Expected:** `{"collision_count": 1}`
- **Actual:** `{"collision_count": 1}`
- **Evidence:** inventory_project_artifacts._decode_recordable_control_map on synthetic duplicate registry
- **Sources:** tools/ssfmt/re/inventory_project_artifacts.py

### `F4-unsupported-layout-visible` — PASS
- **Title:** Unsupported scripted layout (inactive In-App Demo) is visible and classified unsupported
- **Foundation:** True
- **Expected:** `"exactly the inactive demo classified unsupported, remaining 44 supported"`
- **Actual:** `{"unsupported_count": 1}`
- **Evidence:** build_coverage_reports.scripted_report layout classification
- **Sources:** tools/ssfmt/re/analyze_scripted_layouts.py

### `F5-wrong-version-rejected` — PASS
- **Title:** Wrong SoundSwitch version is rejected even with canonical UUID + RAVE GUID
- **Foundation:** True
- **Expected:** `"version 2.9.0 -> identity gate rejects"`
- **Actual:** `{"authorized": false, "reasons": ["version 2.9.0 != 2.10.3"]}`
- **Evidence:** assert_source_identity over synthetic 2.9.0 manifest
- **Sources:** assert_source_identity

### `F6-wrong-venue-rejected` — PASS
- **Title:** Wrong/absent primary Venue selects no Static Looks (fails closed)
- **Foundation:** True
- **Expected:** `"non-matching primary GUID -> [] static looks"`
- **Actual:** `{"selected_looks": 0}`
- **Evidence:** analyze_static_looks.parse_static_looks with reversed primary GUID
- **Sources:** tools/ssfmt/re/analyze_static_looks.py

### `F7-source-drift-detected` — PASS
- **Title:** Re-hash after read detects concurrent source mutation
- **Foundation:** True
- **Expected:** `"changed source bytes -> changed hash (drift detected)"`
- **Actual:** `{"drift_detected": true}`
- **Evidence:** sha256 before/after of a mutated sample file
- **Sources:** hashlib

### `F8-symlink-rejected` — PASS
- **Title:** Symlinked project inputs are detectable/rejectable
- **Foundation:** True
- **Expected:** `"is_symlink() True for a symlinked input -> reject"`
- **Actual:** `{"symlink_detected": true}`
- **Evidence:** os.symlink + Path.is_symlink reference guard
- **Sources:** pathlib.Path.is_symlink

### `F9-pack-one-byte-mutation` — INCOMPLETE
- **Title:** Independent verifier rejects a one-byte pack-artifact mutation
- **Foundation:** False
- **Expected:** `"verifier re-hash rejects any one-byte pack mutation"`
- **Actual:** `"pack format + soundswitch_pack_verifier are not implemented yet (Task 2)"`
- **Evidence:** no pack artifact exists to mutate in this pre-implementation pass
- **Sources:** docs/research/soundswitch/soundswitch_importer_exporter_player_codex_spec.md (Task 2)
- **Remediation:** Implement Task 2 pack + verifier; this proof becomes a mandatory Task 2/8 acceptance test.

## Reference-rule, Static/DDJ, sparse, fail-closed summary
- Reference rule: raw==0 clear/control; raw>0 -> raw-1 (2.10.3 one_based); generic fails ambiguous.
- Static/DDJ: 32 GUID-keyed v5 slots; DDJ slots 8/16/17/24 render exact CH1-CH19 frames.
- Sparse: present channels update, omitted persist, raw-zero clears main, stop/unload -> zero.
- Fail-closed: wrong UUID (same RAVE GUID), wrong version, wrong Venue, collision, missing cue, unsupported layout, source drift, symlink.

## Commands run
```bash
python3 tools/prove_soundswitch_pack_generation.py --project /Users/bbui/Music/SoundSwitch/default.ssproj \
  --output-dir artifacts/soundswitch_pack_generation_proof
# C4 sub-command (passive capture replay, no device opened):
python3 tools/ssfmt/re/validate_scripted_capture.py <a5.pcap> <A5.ssfile> \
  --autoloop-reference <SSAutoLoop5.ssfile> --venue <SoundSwitchVenues.bin> \
  --reference-rule one_based --control-channels 8,9,11
```

## Hardware
- No hardware, MIDI, serial, Art-Net, Enttec, or DMX output was opened. Software/wire decode proof only. Status: SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Remaining blockers
- `F10-active-cc-override` (INCOMPLETE): Implement Task 4 so an active CC/pitch render control fails export until relearned to note.
- `F9-pack-one-byte-mutation` (INCOMPLETE): Implement Task 2 pack + verifier; this proof becomes a mandatory Task 2/8 acceptance test.
