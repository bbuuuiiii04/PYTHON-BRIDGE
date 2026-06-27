---
doc_status: active-implementation-spec
truth_level: code-grounded
last_verified_commit: 291203b
last_verified_date: 2026-06-27
validation_scope: hardening spec derived from the adversarial edge-case sweep of the SoundSwitch
  RE -> pack -> runtime -> live-DMX pipeline; every fix is fail-loud-at-export or report-only and
  must not change DMX output for the current valid project; SOFTWARE-ONLY, HARDWARE-UNVALIDATED.
  REVISED 2026-06-27 after a second adversarial (Opus) line-by-line verifier/loader audit: Task 1
  expanded from F3+F5 to a TRUE superset (adds Gap A/C/D + anti-drift fuzz test), Task 11 (F12)
  fix corrected (the "refresh on inbound message" approach does not hold a silent blackout), and
  F1/F2/F15 guidance tightened. All verifier/loader file:line re-checked against 291203b.
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
On enable/reload the pack ends with **no DMX output** when `load_pack` rejects a pack that
`verify_pack` accepted: `_swap_to_started` builds+verifies the new runtime via `prepare()` (which
calls `load_pack`) BEFORE touching the live one, and on the raise returns `(False, sanitized_error)`
keeping the OLD (already-disabled, on a first enable) runtime — `soundswitch_pack_controller.py:90-93`;
on a `reload` of an enabled pack the same `prepare()` failure surfaces, and the explicit-disable path
publishes a disabled (no-output) bundle (`:81-85`). "Pack failure never falls back to MIDI" (`:17`).
Net for the operator: the pack refuses to enable / silently produces zero DMX, with only a class-name
error string — at the gig.

**The fix class is not "patch F3 and F5"; it is "make `verify_pack` reject every pack `load_pack`
would reject."** A second adversarial audit (2026-06-27) walked every `_fail` in `load_pack` /
`_runtime_metadata` against `verify_pack` and found **five** reverse gaps (verify accepts → load
rejects), not two. All five are below; Task 1 closes them and adds a fuzz test so the two checkers
cannot silently drift apart again.

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
- **[confirmed] Gap A — duplicate active learned-controller EVENT.** `load_pack` rejects two ACTIVE
  controls sharing `(device_name, message_type, channel_zero_based, data_byte)`
  (`soundswitch_pack_loader.py:270-274`, "duplicate active learned controller event"). `verify_pack`
  has **no** such check — `iac_note_by_event` (`soundswitch_pack_verifier.py:629-634`) is a dict
  comprehension that silently collapses duplicate `(channel, data_byte)` keys, and the DDJ/active
  lists never dedupe by event. Reachable by mapping ONE MIDI note to two SoundSwitch buttons (a
  mis-learn). Same severity as F3/F5.
- **[confirmed] Gap C — non-DDJ Static Override target index unvalidated.** `load_pack` validates
  `target_index ∈ [0,32)` for EVERY active `static_override` regardless of device
  (`soundswitch_pack_loader.py:279-282`). `verify_pack` only validates `target_index` for rows whose
  `device_name == "DDJ-800"` (`soundswitch_pack_verifier.py:622-625`); a `static_look` learned on any
  OTHER controller is in `active_render` but its slot is never range-checked. Latent today (setup is
  DDJ-800 + IAC only) but the producer does not prevent a third controller, so it is a real
  asymmetry, not dead code.
- **[confirmed] Gap D — active IAC selection / bridge crosswalk references a missing Autoloop.**
  `load_pack` rejects `not active_loops.issubset(loops)` (`soundswitch_pack_loader.py:626-627`) and
  `not set(crosswalk.values()).issubset(loops)` (`:666-667`). `verify_pack` computes refs with
  `refs_by_source.get(path, set())` (`soundswitch_pack_verifier.py:663-664`) — a selection pointing
  at a non-existent autoloop silently yields an empty set and PASSES. Reachable via a producer bug or
  a tampered pack — exactly the class an independent verifier exists to catch.
- **[unknown — design decision, NOT auto-mirrored] Gap B — empty bridge-scene crosswalk.** `load_pack`
  rejects a pack with zero `project_target` bridge scenes ("bridge scene crosswalk has no project
  targets", `soundswitch_pack_loader.py:243-244`); `verify_pack` does not require ≥1. A degenerate
  static-looks-only pack (no IAC→autoloop selections) would verify green and fail load. **Do NOT
  blindly mirror this** — it may mean the LOADER is too strict (a static-only pack could be
  legitimate), not that the verifier is too lax. See Part B Task 1f: this needs an operator/design
  call before either side changes. The live pack has a non-empty crosswalk, so nothing fires today.

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
  Static Override learned to IAC Driver Bus 1 / ch0 / note0 becomes a `blackout_mask` binding
  (`target_kind` is hard-set to `"blackout_mask"` at loader `:307`). On note-on it holds a FULL
  zero via `_blackout_held` (`soundswitch_midi_input.py:285-289`) — **independent of what static slot
  31 renders**; the blackout does not read slot 31's frame at all.
- **[confirmed] Inert today, in BOTH directions.** The input group opens only devices that carry a
  `static_look` binding (`soundswitch_midi_input.py:522-526`); IAC's only binding is this
  `blackout_mask`, so **IAC is never opened** and the BLACK OUT pad does nothing in pack-DMX mode.
  Consequence the earlier draft missed: today the pack would *also not honour* the operator's
  press-and-hold blackout (it never reads the pad). The pad becomes live — and then mis-expires per
  F12 — only if IAC ever gains a SEPARATE `static_look` binding (any non-blackout slot learned on
  IAC), which forces the group to open IAC and load the blackout binding alongside it. The earlier
  "recolour slot 31 → pad blacks out the rig" claim is **wrong** (recolouring slot 31 changes neither
  the classification on ch0/note0 nor whether IAC is opened). Repro: `work/repro_1_blackout_collision.py`.
- **[decision — operator]** Pre-go-live, blackout routing for the pack is unresolved (it is both
  not-firing and, if fired, mis-expiring — F12). Do not silently change runtime. The safe fix now is
  a **visible diagnostic** (Task 4) so a future edit can't break silently. Rejecting the learn at
  export would break the operator's current StaticOverride31 setup — **do not do that without operator
  sign-off.** Decide pack blackout routing together with F12 (Task 11) before go-live.

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

### Task 1 — `soundswitch_pack_verifier.py`: make `verify_pack` a TRUE superset of the `load_pack` runtime invariants (fixes F3 + F5 + Gap A + Gap C + Gap D)
Goal: fail at **export/verify** instead of at runtime load, for EVERY reverse gap, not just F3/F5.
Each sub-check below mirrors a specific `load_pack` rejection one-for-one; cite the mirrored loader
line in a comment. Use the verifier's existing `_fail(...)` helper (raises
`SoundSwitchPackVerificationError`). All checks operate on `controls` / `scenes` / `iac` /
`autoloop_paths`, which are already validated/built earlier in `verify_pack`.

**1a + 1c — active Static Override slot: range + uniqueness (mirror loader `:279-288`).** This single
loop fixes BOTH F3 (dup slot) and Gap C (non-DDJ slot range). Place it after the active_render / ddj
reconciliation block (current `:616-627`). Key on `control_classification == "static_override"` (NOT
`target_kind == "static_look"`) so the IAC ch0/note0 row — classified `blackout_mask`, not
`static_override` — is correctly excluded, exactly as the loader excludes it:
```python
    seen_static_slots: set[tuple[Any, Any]] = set()
    for row in controls:
        if not row.get("active") or row.get("control_classification") != "static_override":
            continue
        slot = row.get("target_index")
        # Gap C — mirror loader soundswitch_pack_loader.py:279-282 (every device, not just DDJ-800):
        if row.get("target_kind") != "static_look" or type(slot) is not int or not 0 <= slot <= 31:
            _fail("invalid static_override controller target")
        owner = (row.get("device_name"), slot)
        # F3 — mirror loader soundswitch_pack_loader.py:285-288:
        if owner in seen_static_slots:
            _fail("duplicate active static_override slot ownership")
        seen_static_slots.add(owner)
```
Leave the existing DDJ `ddj` list and `selection.get("ddj_static_overrides") != ddj` reconciliation
(`:622-627`) UNTOUCHED — it still pins the explicit DDJ crosswalk; the new loop adds the
device-agnostic range + uniqueness the loader enforces. (DDJ rows are range-checked twice now;
harmless.)

**1g — duplicate active learned-controller EVENT (Gap A; mirror loader `:270-274`).** Place
alongside 1a (after `:627`). The loader dedupes ALL active controls by event tuple, regardless of
classification:
```python
    seen_events: set[tuple[Any, Any, Any, Any]] = set()
    for row in controls:
        if not row.get("active"):
            continue
        event_key = (row.get("device_name"), row.get("message_type"),
                     row.get("channel_zero_based"), row.get("data_byte"))
        if event_key in seen_events:
            _fail("duplicate active learned controller event")
        seen_events.add(event_key)
```

**1b — reserved-scene project-target consistency (F5; mirror loader `:237-240`).** Immediately after
the `if scenes != expected_scenes: _fail(...)` check (current `:648-649`):
```python
    for scene in scenes:
        if scene.get("resolution") == "project_target" \
                and scene.get("control_classification") != "pack_selection":
            _fail("project-target bridge scene is not pack_selection: "
                  f"{scene.get('policy_name')}")
```

**1d — active IAC selection / bridge crosswalk references an existing Autoloop (Gap D; mirror loader
`:626-627` and `:666-667`).** Place after 1b (so non-`pack_selection` project-target scenes are
already rejected). `autoloop_paths` is built at current `:543`; `iac` at `:621`; the loader keys its
`loops` map by `SSAutoLoop{n}.ssfile`:
```python
    autoloop_identities = {f"SSAutoLoop{Path(path).stem}.ssfile" for path in autoloop_paths}
    if not {row.get("target_identity") for row in iac}.issubset(autoloop_identities):
        _fail("active IAC selection references a missing Autoloop")
    crosswalk_targets = {scene.get("target_identity") for scene in scenes
                         if scene.get("resolution") == "project_target"}
    if not crosswalk_targets.issubset(autoloop_identities):
        _fail("bridge scene crosswalk references a missing Autoloop")
```
(`Path` is already imported, `soundswitch_pack_verifier.py:12`.)

**1f — Gap B (empty crosswalk): DECISION, do NOT implement yet.** The loader rejects a zero-target
pack (`soundswitch_pack_loader.py:243-244`). Mirroring that into `verify_pack` would reject a
legitimate static-looks-only pack just as hard at export. Conversely, loosening the LOADER to accept
zero-target packs is a runtime-behaviour change. **Stop and get an operator/design call:** is a pack
with no IAC→autoloop selections a valid configuration? Only after that answer does this become a
verifier check (mirror loader) OR a loader relaxation. Do not guess. The live pack has a non-empty
crosswalk, so neither side fires today; this is not blocking F3/F5/A/C/D.

**Anti-drift guard (the real fix — see Part D).** One-off mirrors rot. Add the property/fuzz test in
Part D that asserts, over randomized selection maps, that **any pack `verify_pack` accepts,
`load_pack` also accepts** — so a future loader rejection added without a verifier mirror fails CI.

All `_fail` calls raise `SoundSwitchPackVerificationError`, so `export_pack`/`publish_pack` reject
these packs on the staged dir before the canonical swap — the operator sees a `verify_failed` verdict
at export, not a dead pad at the gig.

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
- **Field choice (sanitization):** emit `relative_path` ONLY (`{SSID}.ssfile`, host-independent).
  Do **NOT** add `row.filepath` / the source audio path — that leaks `~/Downloads`-style host paths
  into the pack and violates the sanitized-status policy. `title` is acceptable if the operator wants
  it AND it is taken from `track_map` (not a filesystem path); default to `relative_path` only.

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
- **Verified non-regression (Task 1, all sub-checks):** on the current live project the clean pack
  has (a) no duplicate `(device, slot)` static-override owner [F3], (b) no `project_target`
  non-`pack_selection` bridge scene — `house_post_drop_1` resolves `no_project_target` [F5], (c) no
  duplicate active event tuple [Gap A], (d) only DDJ-800 static looks, all slots in range [Gap C],
  (e) every IAC selection + crosswalk target resolves to an exported autoloop [Gap D], and (f) a
  non-empty crosswalk [Gap B]. So none of Task 1's new rejections fire on the clean pack — they only
  tighten. **Strongest guarantee:** each new verifier check mirrors a `load_pack` rejection one-for-one,
  and the clean live pack `load_pack`-succeeds today (the baseline loads it); therefore, by
  construction, none of those loader rejections fire on it — so none of the mirrors can either. Any
  mirror that DID fire on the clean pack would mean its loader twin also rejects the live pack today
  (a contradiction). Re-confirm with the baseline export (same `manifest_sha256`, 95 artifacts) before
  claiming done; if any new check fires on the clean live pack, STOP — that is a real regression.
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
- **Task 1 (F3/F5/Gap A/C/D) — `tests/test_soundswitch_pack_verifier.py`:** build a minimal in-memory
  pack (reuse the existing fixtures / `compile_pack_artifacts` on a synthetic
  `DecodedSoundSwitchProject`, as `tests/test_prove_soundswitch_pack_generation.py` and the proof's
  `_prove_cc_export_fail` already do). One case per gap, each asserting `verify_pack` raises
  `SoundSwitchPackVerificationError`:
  - (F3) two active `static_override` controls owning the same `(device, slot)` — mirror
    `work/repro_3_dup_slot.py`.
  - (F5) a bridge scene `resolution=project_target` + `control_classification != pack_selection` —
    mirror `work/repro_5_postdrop_event.py`.
  - (Gap A) two active controls sharing `(device_name, message_type, channel_zero_based, data_byte)`
    with different `control_path`.
  - (Gap C) an active `static_override` on a NON-`DDJ-800` device with `target_index` out of range
    (e.g. 99) — proves the check is device-agnostic, not DDJ-only.
  - (Gap D) an active IAC autoloop selection whose `target_identity` has no matching `autoloops/*`
    artifact.
  Each must FAIL on the unpatched verifier (write the test first, watch it pass-through, then patch)
  and must be rejected by `load_pack` too (sanity that the gap was real).
- **Task 1 anti-drift property test — `tests/test_soundswitch_pack_verifier.py` (the durable guard):**
  generate randomized but schema-valid selection maps (vary device, channel, note, classification,
  target_kind, slot, duplicate/own-vs-missing autoloop) and assert the invariant
  **`verify_pack` accepts ⇒ `load_pack` accepts`** (i.e. there is no pack the verifier passes that the
  loader rejects). Pure-function seam: drive both off the same staged-dir bytes; no devices, no live
  project. This is what stops a future loader rejection from being added without a verifier mirror.
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
- [ ] `verify_pack` now rejects all five Task-1 gaps: F3 + F5 (re-run `work/repro_3_dup_slot.py` /
      `work/repro_5_postdrop_event.py` → both `verify_pack: REJECTED`), plus the Gap A / Gap C /
      Gap D unit cases. The anti-drift property test (`verify accepts ⇒ load accepts`) passes.
- [ ] Gap B left as an open decision (Task 1f) — NOT implemented; flagged for the operator.
- [ ] `decode_project` on a truncated `SoundSwitchAutoLoopsEx.bin` raises `SoundSwitchDecodeError`,
      not `struct.error` (re-run `fuzz_decode.py` → 0 crash findings).
- [ ] Hard checks pass: `python3 tools/check_docs_metadata.py`, `check_agent_contracts.py`,
      `check_docs_drift.py`.

## Part B' — LIVE-PATH fixes added after operator intent confirmation (2026-06-26)
These are confirmed against operator intent (see the findings register "OPERATOR INTENT — ANSWERED").
They touch the LIVE laser/phrasing path and the runtime loop — **live-critical, so plan-first review
before implementing** (per `feedback_plan_first_live_critical`). Keep them separate commits.

### Task 9 — `smart_phrasing.py`: fire a drop the operator cued straight onto (fixes F13) [confirmed]
- **Intent:** operator said a drop must ALWAYS fire, even cued exactly onto it.
- **Root cause:** `_compute_tick_state` drop-crossing needs `prev_abs_beat` (`:306`); on the first
  tick after any reset (`update()` sets `_previous_abs_beat=None`) a drop equal to that first beat is
  never crossed (S16 in `work/replay_phrasing.py`).
- **Fix direction:** on the first tick after a reset, fire a one-time crossing for any unfired
  `drop_beat == round(abs_beat)` (exact-landing case) — e.g. seed the crossing check so a drop at the
  resumed beat resolves once and is added to `_fired_drop_beats`. Do NOT seed `prev = abs-1` blindly
  (that would also fire drops just *behind* the cue point). Add a replay test mirroring S16.
- **Live safety:** must fire each drop at most once; must not re-fire on the next tick.

### Task 10 — `state_manager.py`: the 200Hz loop must survive an unexpected error, not freeze (fixes F15) [confirmed]
- **Intent:** operator said "just skip that instant" — keep the show running through a glitch.
- **Root cause:** `_run` (`:911-918`) has no per-tick catch and `_push_tick` re-raises after zeroing
  DMX (`:3274-3280`), so one unhandled error kills the lighting thread (frozen show, restart needed).
- **Fix direction:** keep the zero-DMX-on-error safety, but in `_run` wrap the tick so it logs and
  CONTINUES instead of dying — `try: self._push_tick() except Exception: <rate-limited log>; continue`
  (the pack DMX was already zeroed inside `_push_tick` `:3274-3280`). Catch **`Exception`, NOT
  `BaseException`** — `_push_tick` catches `BaseException` and re-raises (`:3274`), so a
  `KeyboardInterrupt`/`SystemExit` must pass THROUGH the `_run` wrapper to stop the thread; `except
  Exception` does that because those are not `Exception` subclasses. Add a rate-limited log + a
  persistent-error counter (mirror the existing `_pack_logged_error` latch at `:3514-3519`) so a
  recurring fault is visible instead of flooding the log at 200 Hz. Scope the wrap to the full
  per-iteration body — `_drain_events()` + `_push_tick()` + `_maybe_publish_snapshot()` (`:915-917`) —
  so a raise in ANY of the three skips the instant rather than only `_push_tick`. Caveat to surface:
  a failure mid-`_drain_events` may drop or partially apply that tick's events; that is acceptable
  under "skip that instant" (the next reader snapshot re-establishes state), but call it out so it is
  a known tradeoff, not a surprise.
- **Live safety — read before implementing.** "Skip that instant" zeros the **pack** DMX for the bad
  tick, but the laser-MIDI and LED/Govee senders are SEPARATE and **hold their last frame** — they do
  NOT blackout on a skipped tick. So skip-and-continue means "pack dark for one tick, other outputs
  hold," not "whole rig dark." That is the desirable behaviour (one glitch must not blackout the
  show), but the operator should know it: a *persistent* error means the pack stays dark while
  lasers/LEDs freeze on their last frame — hence the persistent-error counter/log so it is not
  silent. Verify the loop keeps running (and the pack recovers to live frames) after a forced
  one-shot exception, and that a forced *persistent* exception logs at a bounded rate.

### Task 11 — `soundswitch_midi_input.py`: a held blackout must stay dark for the whole hold (fixes F12) [pre-go-live, pack only; GATED on the blackout-routing decision]
- **Intent:** BLACK OUT is authored press-and-hold; it must stay black as long as held.
- **Root cause:** `_expire_blackout_if_needed` (`:246-255`) releases the blackout `stale_timeout_ms`
  after the note-on (`_blackout_held_at` set once at `:287`, never refreshed); MIDI sends no repeat
  note-ons during a hold, so a >2s hold un-blacks itself.
- **Why the obvious fix is WRONG (corrected 2026-06-27).** The earlier "refresh the hold timestamp on
  any inbound message from the bound device" does **not** fix the real case: during a genuine hold the
  operator presses nothing else, so there are NO inbound messages to refresh on (active-sense and
  clock are filtered out at `:396-398`), and the blackout still expires after 2s. A press-time timer
  and a controller-silence timer are *indistinguishable* here — a real silent hold and a lost note-off
  both look identical (port open, no traffic, blackout held). So no time-based expiry can both hold a
  silent press AND catch a lost note-off.
- **Fix direction (correct, live-safe).** The operator wants an indefinite hold, so **drop the
  press-time auto-expiry as the release mechanism** and rely on the clears that already exist and are
  unambiguous:
  - note-off releases it (`_process_note_off` blackout branch, `:313-317`);
  - input-port-gone clears it (`_mark_port_gone` `:257-258`, fired from the empty-poll port check
    `:458-461` and the end-of-source raise `:465-466`);
  - worker-death (`:488-490`), `stop`/`panic`/`on_pack_reload`/`mark_unavailable` all already clear
    held state.
  So a disconnected/dead controller still releases the blackout via the port/worker path — the 2s
  timer is **redundant** for the failure it was meant to cover, and harmful for a real hold.
  Optionally keep a *long* stuck-note insurance cap (e.g. 30s, a named constant separate from
  `stale_timeout_ms`) documented explicitly as "lost-note-off insurance, not a hold limit" — never a
  2s value. Confirm the port-check still runs while blackout is held: `:456-462` calls
  `_expire_blackout_if_needed()` AND the port check on every empty poll, so removing the expiry leaves
  the port-gone failsafe intact.
- **Gate:** F12 only bites once the blackout is actually reachable, which needs IAC opened (a
  `static_look` binding on IAC — see F1/A3). If the operator decides the pack's blackout routes
  elsewhere (or IAC is never opened), this task may be moot. **Resolve blackout routing (with Task 4 /
  A3) before implementing.** Not live today.
- **Test:** feed `_feed_raw_message(0x90,0,100)` (note-on, no note-off), advance the clock past the
  old 2s window with empty polls → assert `blackout_held` stays `True`; then drop the port (port
  checker returns absent) → assert `blackout_held` clears via `input_port_gone`. Asserts the hold no
  longer self-releases while the controller is alive, yet a dead port still clears it.

## When you finish
Commit each task separately (`fix(soundswitch): verify_pack is a true superset of load_pack runtime
invariants (F3/F5 + Gap A/C/D)`, etc.). Report back: which tasks landed, the before/after
`manifest_sha256` for the clean export, the `fuzz_decode.py` crash count (must be 0), and that the
anti-drift property test (`verify accepts ⇒ load accepts`) passes. Flag these **open operator/design
decisions** as still unresolved — this spec only makes them visible, it does not decide them:
- **Gap B (Task 1f):** is a static-looks-only pack with zero IAC→autoloop selections valid? Decides
  whether `verify_pack` mirrors the loader's "≥1 project target" rule, or the loader is loosened.
- **A3 / F1 + F12 blackout routing (Task 4, Task 11):** the pack currently neither honours nor safely
  holds the BLACK OUT pad (IAC isn't opened; if opened it mis-expires). Decide how the pack routes
  blackout before go-live; Task 11 is gated on this.
- **A4 / F2 (Task 3):** stop gating scripted activity on export-host file existence? Spec only adds
  the report-only diagnostic.
