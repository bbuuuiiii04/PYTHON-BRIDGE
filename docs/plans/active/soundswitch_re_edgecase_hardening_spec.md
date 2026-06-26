---
doc_status: active-implementation-spec
truth_level: code-grounded
last_verified_commit: b0e5e47
last_verified_date: 2026-06-26
validation_scope: hardening spec derived from the adversarial edge-case sweep of the SoundSwitch
  RE -> pack -> runtime -> live-DMX pipeline; every fix is fail-loud-at-export or report-only and
  must not change DMX output for the current valid project; SOFTWARE-ONLY, HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — SoundSwitch RE-pipeline edge-case hardening

Derived from the adversarial sweep (read-only on `~/Music`). Every finding below was reproduced
with a runnable script under the session scratchpad (`work/repro_*.py`, `fuzz_decode.py`,
`re_sweep.py`); the repro names are cited per task. Baseline before any change: proof gate
**29 PASS / 0 / 0**, SoundSwitch unit suite **262 OK**, prove suite **16 OK**, clean oracle export
**verified=True / 95 artifacts**.

The unifying root cause across the two worst bugs: **`verify_pack` does not enforce every invariant
`load_pack` enforces**, so the exporter ships packs that pass its own verifier and then the runtime
loader refuses them — turning a catch-at-export into a silent whole-pack disable at the gig.

---

## Part A — Context & root cause (verified; read, do not implement)

### A1 — `verify_pack` is not a superset of `load_pack`'s invariants → green export, dead show
On `load_pack` failure the controller publishes a **disabled (no-output) bundle**
(`soundswitch_pack_controller.py:11-17`, "pack failure never falls back to MIDI") — every authored
static look and autoloop selection goes to zero DMX until the operator notices. Two reachable
authoring actions produce a pack that `verify_pack` accepts but `load_pack` rejects:

- **[confirmed] F3 — duplicate Static Override slot ownership.** A real operator can learn two pads
  to one Static Override button (same `control_path`, different note). The decoder
  (`soundswitch_project_decoder.py:_resolve_controls`, no slot-uniqueness check) and `verify_pack`
  allow it; `load_pack` rejects it at `soundswitch_pack_loader.py:285-288`
  ("duplicate active static_override slot ownership"). Repro: `work/repro_3_dup_slot.py` →
  `verify_pack: VERIFIED=TRUE`, `load_pack: FAILED`.
- **[confirmed] F5 — control mapped to a bridge-reserved scene event.** The producer force-classifies
  `house_post_drop_1` (IAC ch0 / note41) `inactive_report_only` while still reporting
  `resolution=project_target` (`soundswitch_pack.py:229-230`); `verify_pack` mirrors that and passes
  (`soundswitch_pack_verifier.py:638-648`); `load_pack` rejects any `project_target` scene whose
  classification isn't `pack_selection` (`soundswitch_pack_loader.py:237-240`). Repro:
  `work/repro_5_postdrop_event.py` → `verify_pack: VERIFIED=TRUE`, `load_pack: FAILED: project-target
  bridge scene is not pack_selection: house_post_drop_1`.

### A2 — `decode_catalog` leaks `struct.error` on a truncated catalog (contract violation)
- **[confirmed] F4.** `soundswitch_project_decoder.py:644`
  `record_type, app_index, bars, enabled = struct.unpack_from("<IIII", data, offset)` is the one
  unguarded `unpack_from` in the decoder; every sibling uses `_u32`/`_i32` or an explicit
  `offset + N <= len` check. A truncated `SoundSwitchAutoLoops.bin` / `SoundSwitchAutoLoopsEx.bin`
  raises `struct.error`, which **escapes `decode_project`**, violating the module's documented
  "fail closed with `SoundSwitchDecodeError`" contract. Repro: `fuzz_decode.py` (511 hits, all at
  `:644`); every other binary fails closed on ~900 truncations each. The RE toolkit's own
  `tools/ssfmt/re/parse_autoloop_catalogs.parse_catalog` handles the same truncations gracefully
  (`re_sweep.py`), so a correct reference exists next door.

### A3 — Reserved-event classification collision (blackout vs static look)
- **[confirmed] F1.** The blackout branch fires before the static-look branch in producer
  (`soundswitch_pack.py:205-207`), verifier (`soundswitch_pack_verifier.py:600-604`) and loader
  (`soundswitch_pack_loader.py:275-309`, keyed on `control_classification`, not `target_kind`). A
  Static Override learned to IAC Driver Bus 1 / ch0 / note0 becomes a momentary `blackout_mask`; the
  runtime never opens IAC as a static input (`soundswitch_midi_input.py:522-526`) and holds a full
  blackout on note-on (`:285-289`); press/toggle is discarded. **This is live now:**
  `StaticOverride31` ("BLACK OUT", all-zero) is mapped there. Harmless only because slot 31 renders
  all-zero — recolour slot 31 or map a non-zero / toggle-intent look there and the pad blacks out the
  rig with no surfaced warning. Repro: `work/repro_1_blackout_collision.py`.
- **[decision — operator]** The current all-zero mapping is *intended* (the pad IS the blackout).
  Do not silently change runtime. The safe fix is a **visible diagnostic** so a future edit can't
  break silently. A harder option (reject the learn at export) would break the operator's current
  StaticOverride31 setup — **do not do that without operator sign-off.**

### A4 — Scripted "active" gate keys on the EXPORT host's filesystem (silent dark shows)
- **[confirmed] F2.** "Active" is decided by whether the audio file exists on the machine running the
  export (`soundswitch_pack.py:180-184`, `_active_script_paths` → `Path(filepath).is_file()`); that
  flag is baked into the pack and gates rendering at `soundswitch_laser_player.py:338-339`. On the
  live project 38 scripts are `supported_mapped_primary` but only **32 are active** — 6 real authored
  tracks (e.g. "PICK UP DA PACE! (Extended)", "kohta x Bafu - STARsound (pt3)") have SoundSwitch
  filepaths under `~/Downloads` / `~/Desktop/isoxo + more/` that no longer resolve, so their per-track
  shows silently won't render and **no error is surfaced**. The bridge plays by `soundswitch_id`, so
  the track still plays — only its lights vanish. Repro: inline probe in the session report.
- **[decision — operator]** Whether to *also* stop gating activity on file existence is a design
  change. The safe minimum is a **visible diagnostic** naming each deactivated track.

### A5 — Lower-severity / cosmetic (verified)
- **[confirmed] F7 — proof gate `D2-ddj-ch1-19-frames` is a latent content pin.**
  `tools/prove_soundswitch_pack_generation.py:92-101` hardcodes today's CH1-19 frames of static slots
  8/16/17/24; `:595-612` fails on any mismatch. Re-colouring any of those four looks (a routine edit)
  flips the proof to `FAIL_DO_NOT_IMPLEMENT` even though export/verify/load stay green. It is the lone
  content pin among the now-structural checks (B1/B2/B4/B5/D1).
- **[confirmed] F6 — "DDJ" mislabel.** `tools/ssfmt/re/inventory_project_artifacts` →
  `static_look_midi_selection` (the proof's `B3b-ddj-overrides`,
  `tools/prove_soundswitch_pack_generation.py:380-393`) lumps IAC bindings under a "DDJ" name: on the
  live project it contains `{DDJ-800: 4, IAC Driver Bus 1: 1}`, the lone IAC entry being the same
  StaticOverride31 from F1 (RE calls it a DDJ override; production reclassifies it `blackout_mask`).
  Repro: `re_sweep.py`. Production `soundswitch_pack.py` is correctly device-filtered — only the RE
  inventory + proof naming mislead.
- **[confirmed] F8 — production export has no catalog-declared-count completeness oracle.** The Venue
  catalog tail declares 233 cues; dropping an *unreferenced* render cue (42 exist) still exports
  `verified=True` because nothing cross-checks parsed count against the declared count. The oracle
  exists in `tools/ssfmt/re/verify_export_completeness.py:96-102` (ORACLE 1) but is not wired into the
  production path. Live impact is bounded (unreferenced cues don't drive output); this is corruption
  hardening. Repro: inline probe. Same file over-claims in its docstring ("no silent miss of cue,
  track, or autoloop") while only verifying Venue cues.

**Out of scope / verified safe (no change needed):** content edits (cue/look value edits, rename,
slot remap) export clean; cross-ref integrity, F10 CC/pitch reject, identity/symlink/TOCTOU/output
guards, render correctness (proof E1-E4), and `freeze`/`compare` byte-exact drift detection all fail
closed correctly. The 32-static-look pin is by-design (`decode_static_looks:470,483` bakes 32 into
its marker). Do not "fix" any of these.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Do not change DMX output for the current valid live project.** Every task is either a new
  rejection of an already-broken (load-failing) pack, a report-only diagnostic, or a guard that only
  fires on malformed/corrupt input. Run the green baseline (Part E) before and after each task.
- Do **not** touch the runtime hot path, `state_manager.py`, laser/LED/Govee subsystems, MIDI/serial
  device code, or the live project under `~/Music`.
- Do **not** weaken any existing check to make a test pass. Add tests; never edit a test to hide a
  regression.

### Task 1 — `soundswitch_pack_verifier.py`: make `verify_pack` enforce the two `load_pack` invariants (fixes F3 + F5)
Goal: fail at **export/verify** instead of at runtime load. Add both checks inside `verify_pack`,
after the existing selection-map block (after the `ddj`/`iac` reconciliation around current
`:621-627`, and after the bridge-scene `expected_scenes` equality check at current `:648-649`). Use
the verifier's existing `_fail(...)` helper.

1a — duplicate active Static Override slot ownership (mirror loader `:285-288`). After the `ddj`
list is built (`:622`), add:
```python
    seen_static = set()
    for row in active_render:
        if row.get("target_kind") != "static_look":
            continue
        owner = (row.get("device_name"), row.get("target_index"))
        if owner in seen_static:
            _fail("duplicate active static_override slot ownership")
        seen_static.add(owner)
```
1b — reserved-scene project-target consistency (mirror loader `:237-240`). Immediately after the
`if scenes != expected_scenes: _fail(...)` check (current `:648-649`), add:
```python
    for scene in scenes:
        if scene.get("resolution") == "project_target" \
                and scene.get("control_classification") != "pack_selection":
            _fail("project-target bridge scene is not pack_selection: "
                  f"{scene.get('policy_name')}")
```
Both `_fail` calls must raise `SoundSwitchPackVerificationError` (they do, via `_fail`). This means
`export_pack`/`publish_pack` now reject these packs before the canonical swap (they call
`verify_pack` on the staged dir), so the operator sees a `verify_failed` verdict at export, not a
dead pad at the gig.

### Task 2 — `soundswitch_project_decoder.py:644`: bounds-guard the catalog entry header (fixes F4)
Replace the unguarded read so a truncated catalog raises `SoundSwitchDecodeError`, not `struct.error`.
Current line 644:
```python
        record_type, app_index, bars, enabled = struct.unpack_from("<IIII", data, offset)
```
Replace with a bounds check that reuses the module's failure path:
```python
        if offset + 16 > len(data):
            _fail("bounds", "catalog entry header is outside the source", path, offset)
        record_type, app_index, bars, enabled = struct.unpack_from("<IIII", data, offset)
```
(`_fail` is the module helper at `:89`; it raises `SoundSwitchDecodeError`.) Do not change any other
line — this is the only unguarded `unpack_from` in the decoder (verified by reading every
`struct.unpack_from` call site).

### Task 3 — `soundswitch_pack.py`: surface scripted tracks deactivated by missing audio files (fixes F2, report-only)
In `compile_pack_artifacts`, the `active_scripts` set (`union, ...` block, current `:289-290`) already
exists. Add a deactivation list to `import_report.json` so the operator sees which mapped-primary
tracks were dropped because their file was absent at export. Compute it from data already in hand:
```python
    deactivated_scripts = sorted(
        row.relative_path for row in project.scripted_track_classifications
        if row.status == "supported_mapped_primary" and row.relative_path not in active_scripts
    )
```
Add it as a new key on the existing `import_report.json` root (current `:333-336`), e.g.
`scripted_deactivated_missing_file=deactivated_scripts`. Do **not** change `active_scripts`, the
active-cue union, or any rendering — this is purely an added report field. Confirm `verify_pack` still
passes (it does not field-validate `import_report.json` beyond presence + hash, verified at
`soundswitch_pack_verifier.py:408-411`); the new field is canonical JSON so the manifest hash stays
consistent.

### Task 4 — `soundswitch_pack.py`: surface the blackout/static-look reclassification (fixes F1, report-only)
In `_selection_map` (`:198-263`), any control authored as `target_kind="static_look"` that lands on the
reserved IAC blackout event (IAC Driver Bus 1 / ch0 / note0) is reclassified `blackout_mask` (`:205-207`).
Record that collision so it is visible. While iterating `project.resolved_controls`, collect every row
where the computed `classification == "blackout_mask"` **and** `row.target_kind == "static_look"` as
`{control_path, target_index, note: "treated as momentary blackout, not a static look"}`.
**Emit it on `import_report.json`** (current `:333-336`), e.g. a new
`reserved_event_reclassifications=[...]` key — **not** on `selection_map.json`. Rationale (verified):
`verify_pack` does not field-validate `import_report.json` beyond presence + hash
(`soundswitch_pack_verifier.py:408-411`), so an added key is safe there; `selection_map.json` is read
with specific keys and is best left untouched. Report-only — do not change `classification`, the
binding, or runtime.

### Task 5 — `tools/prove_soundswitch_pack_generation.py`: make D2 structural, not a content pin (fixes F7)
Replace the golden-hex comparison in `check_static_looks` D2 (`:593-612`) so each slot is asserted to
render *its own recomputed frame* (the pattern the production verifier already uses at
`soundswitch_pack_verifier.py:490-496`), instead of comparing to `GOLDEN_DDJ` hardcoded hex. Keep D1
(GUID-keyed selection) and the slot/name accounting. Remove or repurpose the `GOLDEN_DDJ` constant
(`:92-101`); if you keep it, only as a non-blocking diagnostic, never as a pass/fail gate. Net effect:
recolouring slots 8/16/17/24 in SoundSwitch no longer fails the proof.

### Task 6 — (optional, cosmetic) de-mislabel the device-agnostic static-override selection (fixes F6)
In `tools/ssfmt/re/inventory_project_artifacts.py`, rename the `static_look_midi_selection` field /
internal label to be device-agnostic (it is not DDJ-only). In
`tools/prove_soundswitch_pack_generation.py:380-393`, rename the `B3b-ddj-overrides` check id/title to
`B3b-static-override-selection` and drop the "DDJ" assertion from its prose. Update any test that pins
the old id/title. Do not change the data, only the names. Low priority.

### Task 7 — (optional, hardening) wire the catalog-count oracle + fix the completeness docstring (fixes F8)
- In `verify_pack` (`soundswitch_pack_verifier.py`, Venue block ~`:449-465`), cross-check the parsed
  Venue total against SoundSwitch's catalog-tail-declared count if that count is available in the
  pack (the production `venue_cues.json` carries `total_record_count`; confirm whether the tail's
  declared count is retained — if not, this requires the decoder to surface it first, so mark this
  **[unknown — needs the declared count plumbed through]** and stop, do not invent it).
- In `tools/ssfmt/re/verify_export_completeness.py` docstring (`:1-25`), narrow the claim to "Venue
  cue completeness" — it does not verify tracks, autoloops, static looks, or MIDI maps.

---

## Part C — Invariants that MUST still hold (live safety)
- **No new runtime state fields.** Every task changes export-time code (verifier / compiler /
  decoder) or the proof gate, or adds a report-only artifact field. Nothing touches the 200 Hz hot
  path or adds a runtime state field, so there is no pending-state or mode-transition cleanup to
  guard (checklist items 3/4 are N/A by construction — keep it that way).
- **Verified non-regression:** on the current live project there is no duplicate `(device, slot)`
  static-override owner and no `project_target` non-`pack_selection` bridge scene
  (`house_post_drop_1` resolves `no_project_target`), so Task 1's new rejections do **not** fire on
  the clean pack. Re-confirm with the baseline export before claiming done.
- **No DMX change for the current valid project.** The clean oracle export
  (`export_pack('~/Music/SoundSwitch/default.ssproj', <new dir>)`) must still return `verified=True`
  with the **same 95 artifacts and the same `manifest_sha256`** as before Tasks 1–2/6/7 (Tasks 3–4
  add report-only fields and will legitimately change the manifest hash — that is the only allowed
  change, and only for those two tasks).
- **Fail-closed only tightens.** Tasks 1 and 2 may only *add* rejections of packs/inputs that already
  fail at load (Task 1) or already corrupt the parse (Task 2). No previously-accepted *valid* pack may
  start failing. Prove this with the baseline export still passing.
- The 200 Hz push loop, `StateManager` ownership, reader→event flow, and all
  laser/LED/MIDI/serial paths are untouched (`docs/architecture/runtime_invariants.md`).
- The decoder stays read-only on the source project; no new writes into `~/Music`.

## Part D — Tests
Add to `tests/` (pure-function seams; no live project, no devices, no subprocess):
- **Task 1a/1b — `tests/test_soundswitch_pack_verifier.py`:** build a minimal in-memory pack (reuse
  the existing fixtures / `compile_pack_artifacts` on a synthetic `DecodedSoundSwitchProject`, as
  `tests/test_prove_soundswitch_pack_generation.py` and the proof's `_prove_cc_export_fail` already
  do) for each case: (i) two active static_override controls owning the same `(device, slot)` →
  assert `verify_pack` raises `SoundSwitchPackVerificationError`; (ii) a bridge scene with
  `resolution=project_target` and `control_classification != pack_selection` → assert it raises.
  Mirror the scenarios in `work/repro_3_dup_slot.py` and `work/repro_5_postdrop_event.py`.
- **Task 2 — `tests/test_soundswitch_project_decoder.py`:** truncate a known-good catalog blob at the
  entry-loop boundary and assert `decode_catalog` raises `SoundSwitchDecodeError` (code `bounds`),
  not `struct.error`. A `for cut in range(...)` sweep mirroring `fuzz_decode.py` is ideal.
- **Tasks 3/4:** assert the new report fields appear for a project with a deactivated script /
  reserved-event reclassification, and are absent/empty for a clean one. Assert `verify_pack` still
  returns `verified=True` with the field present.
- **Task 5:** assert the proof's D2 passes after a synthetic recolour of a static-look slot (it must
  not depend on `GOLDEN_DDJ`).

## Part E — Acceptance (definition of done)
- [ ] `python3 -m unittest discover tests` green (run from the repo dir).
- [ ] `python3 tools/prove_soundswitch_pack_generation.py --project ~/Music/SoundSwitch/default.ssproj`
      → `PASS_IMPLEMENTATION_MAY_BEGIN` (29/29 foundation), including after a synthetic slot recolour
      for Task 5.
- [ ] Clean oracle export still `verified=True / 95 artifacts`; `manifest_sha256` unchanged for a tree
      with no deactivated scripts / no reserved-event collisions (Tasks 1,2,5–7), and changed *only*
      by the added report fields for Tasks 3–4.
- [ ] New tests added and passing; no existing test edited to pass.
- [ ] `verify_pack` now rejects the F3 and F5 packs (re-run `work/repro_3_dup_slot.py` /
      `work/repro_5_postdrop_event.py` against the patched tree → both should now show
      `verify_pack: REJECTED`).
- [ ] `decode_project` on a truncated `SoundSwitchAutoLoopsEx.bin` raises `SoundSwitchDecodeError`,
      not `struct.error` (re-run `fuzz_decode.py` → 0 crash findings).
- [ ] Hard checks pass: `python3 tools/check_docs_metadata.py`, `check_agent_contracts.py`,
      `check_docs_drift.py`.

## When you finish
Commit each task separately (`fix(soundswitch): verify_pack enforces load-pack slot-ownership +
reserved-scene invariants (F3/F5)`, etc.). Report back: which tasks landed, the before/after
`manifest_sha256` for the clean export, and the `fuzz_decode.py` crash count (must be 0). Flag the
two operator decisions (A3 "also reject blackout-event static learns?", A4 "stop gating activity on
file existence?") as still open — this spec only makes them visible, it does not decide them.
