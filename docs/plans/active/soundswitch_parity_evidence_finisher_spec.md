---
doc_status: active-spec
truth_level: capture-grounded (parity_20260701T185231Z) + current-code-verified at commit 74cbf15
last_verified_commit: 74cbf15
last_verified_date: 2026-07-02
validation_scope: Codex implementation spec for the REMAINING SoundSwitch perfect-parity work after
  the capture-proven cue-resolution + saved-order-selection fix landed in 74cbf15. Scripted
  mechanism questions are CLOSED (see Part A evidence tables); what remains is fixture repair with
  provenance, the parity-lane evidence registry, autoloop/static lane promotion, and the ship gate.
  Supersedes the C1-C8 execution plan of soundswitch_perfect_parity_finisher_spec.md WHERE THEY
  CONFLICT (that spec's §0.4 Finding 2 wording "exact-key, no raw-1" is reconciled below — the
  lookup is exact in SoundSwitch's internal 1-based reference space, which equals stored_key R-1
  in the bridge's decoded label space; capture-proven at 100.0% dwell).
supersedes_conclusions_of: docs/plans/active/soundswitch_perfect_parity_finisher_spec.md Task C4's
  "resolve raw_reference by exact stored_key equality" reading (refuted by U0 dwell evidence);
  tests that encoded exact-R semantics (already flipped in 74cbf15)
---

# Codex Implementation Spec — SoundSwitch Parity Evidence Finisher

**One-line:** the scripted render algorithm is now capture-proven and committed (74cbf15); this
spec finishes the job — rebuild the reduced U0 witness fixture from the capture with honest
provenance and a divergence ledger, feed real oracle evidence into the parity lanes so supported
documents leave `unverified_parity`, promote autoloop + static lanes from capture evidence, and
drive the full software ship gate green.

> **Roles:** Claude authored this spec from a live evidence pass; **Codex implements.** Work on
> `main`, commit after each task. No new branches. No secrets/live-config/canonical-pack contents
> committed. No hardware, no bridge restart, no SoundSwitch clicks, no new capture.

---

## Part A — Context & root cause (verified; read, do not implement)

### A.0 Where the work stands (all [confirmed] at HEAD 74cbf15)

- Commit `74cbf15` landed the mechanism fix. Full suite green: **2615 tests OK** (4 skipped,
  1 expected failure) via `python3 -m unittest discover rb_ss_bridge_v2/tests` from the parent dir.
- `soundswitch_scripted_resolution.py` — `resolve_scripted_reference(R, key_to_guid)` returns the
  dictionary record with `stored_key == R - 1`; `R == 0` is the OFF/clear sentinel
  (`clear_control`); a miss keeps `resolved_stored_key = R - 1` with `resolved_cue_guid = None`
  (renderer skip-holds). Module docstring carries the evidence citation.
- `soundswitch_laser_player.py` — `render_scripted_frame` boundary path selects the **last event in
  serialized (saved) order whose `time <= elapsed_ms`**, never re-sorted by timestamp, never
  early-breaking (saved order is not time-monotonic). `_apply_events` iterates `document.events`
  in saved order too. Exporter `render_document_boundaries` (`soundswitch_pack.py:91`) already
  composed in saved order — unchanged.
- `soundswitch_pack_verifier.py:350` — timeline invariant is now `stored == raw - 1`.
- Old-assumption tests flipped in `tests/test_soundswitch_scripted_resolution.py`,
  `tests/test_soundswitch_project_decoder.py` (synthetic `_ssfile` now writes real-world 0-based
  writer keys), `tests/test_soundswitch_laser_player.py` (CurrentPackGolden values recomputed from
  the corrected export).
- A fresh export now passes the committed reduced fixture on **5 of 8 rows** — 528e8b22 both rows
  and every `lit-region-match` row byte-exactly. The 3 failing rows are proven capture
  contamination (A.3), NOT algorithm error.

### A.1 The proven mechanism (do not re-litigate)

[confirmed, capture `tools/ssfmt/captures/parity/parity_20260701T185231Z/`]:

1. **Resolution:** serialized timeline reference `R` → the file's own cue-dictionary record with
   `stored_key == R - 1`. `R == 0` → clear-control (zero all channels except CH8/9/11 — proven
   directly by fc10's 14.79 s clear-hold run `[0×7, 255@8, 241@9, 0×10]`). Miss → skip-hold.
2. **Composition:** cache frames are cumulative in **serialized order** (all-zero seed,
   previous + this cue's channel writes); playback shows the last serialized entry whose time has
   arrived. Proven by {528E8B22}'s saved-order inversion (60065 serialized before 60064): U0 at
   60082 shows the 60064 event's full frame, and at 60425 the 60416 re-application — byte-exact
   only under saved-order selection.
3. **Dwell evidence** (deduped U0 frame-run comparison across each witness's full alignment
   window): 528e8b22 **100.0%** byte-exact dwell under R-1 (0.0% under exact-R); 9947c65e
   **100.0%** (0.0%); fc10fc02 pitch-locks 11 consecutive events to <20 ms at p=0.98428
   (t0=315404.23 s mono) for refs 209/0; ae9e3c61 matches every boundary whose cue set exists in
   the file on disk (75.6% of dwell; the remainder is A.4's stale-edit divergence).
4. **Reconciliation with the Ghidra packet** (`docs/research/soundswitch/
   soundswitch_perfect_parity_ghidra_evidence.md` Q2): the binary's lookup IS exact — in
   SoundSwitch's internal reference space, which is 1-based with 0 reserved. The bridge's decoded
   `stored_key` label is the file's 0-based writer index, one below that space. "raw−1 is a bridge
   label" (the packet's own caveat) is literally correct.

**Rejected hypotheses — each killed by a specific datapoint; never revisit:**

| Hypothesis | Killing datapoint |
| --- | --- |
| exact `stored_key == R` (the pre-74cbf15 code) | 0.0% U0 dwell on 528e8b22 and 9947c65e; TURQOISE(key 25)/GREEN(key 26) swap on 528e ref 26 |
| resolve against current venue stored index | ae9e ref 33 → BREAKDOWN CHILL 2 has venue idx 36 (delta −3) while 528e ref 26 → venue idx 26 (delta 0) |
| resolve by venue serialization position (0- or 1-based) | position 26 = 'GREEN', want TURQOISE; fc10 positions all wrong |
| resolve by dictionary list position | ae9e dict is a 104/104 permutation; BC2 at position 47, key 32, ref 33 |
| shifted (guid,key) byte-pairings (key with next/prev guid) | byte-parse of 528e map verified guid a21326f0↔key 25 exactly as decoder reads it |
| one global library map | K(BC3TC) = 33 in 528e but 4 in ae9e — no single map can do both |
| SS reads a second per-file map in the prefix | whole-file scan: the only venue-GUID array in ae9e is the known cue map at cue_map_offset |

### A.2 Fixture state (the 3 remaining failures are contamination — [confirmed])

`tests/fixtures/soundswitch/parity_oracle/scripted_reduced.json` (capture_id
`parity_20260701T185231Z`) — 8 rows, 4 witnesses:

| Row | Verdict at 74cbf15 | Finding |
| --- | --- | --- |
| 528e8b22 @60082 `first-event-diff` | **MATCH** | valid |
| 528e8b22 @60425 `lit-region-match` | **MATCH** | valid |
| ae9e3c61 @375 `lit-region-match` | **MATCH** | valid |
| 9947c65e @51864 `lit-region-match` | **MATCH** | valid |
| fc10fc02 @127380 `lit-region-match` | **MATCH** | valid |
| ae9e3c61 @239 `wrong-cue-value` | VALUE_DIFF | **cross-deck bleed**: U0 frame `[0×7,172,255,0,231,0×8]` is only CH8/9/11 residue; not producible by any composition of ae9e's own cues (whole-dictionary reachability check); SS was still rendering the outgoing deck 239 ms into the track |
| 9947c65e @51811 `first-event-diff` | VALUE_DIFF | **cross-deck bleed**: U0 frame equals venue cue 'RAINBOW LASER (pl strobe)' whose GUID is **not in 9947's dictionary**; SS switched decks between 51811 and 51864 |
| fc10fc02 @97239 `late-incomplete-export` | VALUE_DIFF | **mis-join**: U0 was fully dark at that elapsed (a 113.68 s all-zero run covers it — mono 315386.225→315499.906); the row's frame is fc10's own saved-order boundary from **t≈133955** ('SLOW ZOOM OUT copy') stamped with the wrong elapsed |

### A.3 Capture-vs-disk divergence (unsaved in-SoundSwitch edits — [confirmed])

Two witnesses contain capture regions that the **files on disk cannot produce under any rule**:

- **ae9e3c61** (file mtime Mar 31; venue file Jun 25; capture Jul 1): the captured strobe cycle
  contains a WHITE DOT STROBE state (`ch10=0, ch11=227, ch17=0` applied over the base). WDS's GUID
  appears in almost every other file's dictionary and in SoundSwitchVenues.bin, but is **absent
  from ae9e's ssfile entirely** (whole-project byte scan). Also raw−1 predicts MASTER STROBE
  `(255,255)` on CH10/11 at those events and U0 never once emits it. Class:
  `stale_source_edit` — the operator re-pointed cues in SS after the file's last save.
- **fc10fc02** (mtime Jun 4): event t=97232 (ref 208) played 'SLOW ZOOM OUT copy' (file key 211)
  and events ref 211 played the `(17:219, 19:0)` strobe (file key 207), while disk raw−1 says keys
  207/210. Its refs 209 and 0 are byte-exact under raw−1 in the same playback. Same class.
- **Convergence note (load-bearing for row selection):** divergence does not poison everything
  downstream. fc10's clear at 128766 zeroes the divergent channels, and the ref-209 cue (RAINBOW
  COVERAGE, full-set on the channels that differ) overwrites the rest — so U0 rows at ≥127376 in
  the RC/clear cycle **are disk-consistent** (the committed @127380 row already MATCHES).
  ae9e's base states BC3TC (ch15=155) / BTrev (ch15=191) are full-frame overwrites, so rows in
  those holds are disk-consistent even after a divergent strobe state.

### A.4 Lane state and why everything is still `unverified_parity` ([confirmed])

- `soundswitch_pack.py:135-139` (`_look`) and `:180-184` (`_document`) call
  `classify_parity_lane(structural_supported=…, oracle_report=None, generalized_witness_passed=False)`
  — **no evidence ever reaches the classifier**, so every document/look computes
  `unverified_parity` and the manifest summary is `{'unverified_parity': 118}`.
- The plumbing downstream of the lane already exists and is tested: verifier `_validate_parity`
  (`soundswitch_pack_verifier.py:287`), loader `_parity_lane`/`_parity_evidence` passthrough
  (`soundswitch_pack_loader.py:541-542`), `LoadedPack.parity_summary` +
  `unverified_documents`, `PackRuntime.sanitized_status()` exposure
  (`tests/test_soundswitch_scripted_parity.py:56-73`), and the C8 live gate
  (`parity_live_blocks_document`, `soundswitch_laser_player.py:78`).
- `tools/export_soundswitch_pack.py::_assert_publishable_parity` (`:459-474`) already fails
  publication when `manifest.parity_lanes.unverified_parity > 0` — it just never had a chance to
  pass. **Scope defect to fix in Task 3:** `compile_pack_artifacts` counts lanes for every decoded
  document including inactive ones (`soundswitch_pack.py:428-437`), so deactivated scripts would
  block publication forever. The gate must count **active supported** documents only.
- `tests/test_soundswitch_parity_oracle.py::ReducedCaptureFixtureTests` (`:72-99`) is skip-gated on
  `local/soundswitch/rbss_canonical_pack/manifest.json` **relative to CWD** — it only runs from the
  repo root (CI/discover runs from the parent dir → it currently SKIPS), and it still asserts the
  pre-74cbf15 world (ae9e/fc10 failing). It also load_packs the stale local canonical pack, which
  the current loader **rejects** ("malformed Static Look primitive/field schema") because the C6
  schema grew. Task 2 rewrites it against a fresh temp export.

### A.5 Capture geometry you will need ([confirmed])

- Capture dir: `tools/ssfmt/captures/parity/parity_20260701T185231Z/` — `artdmx_packets.jsonl`
  (1.38 GB; per-packet rows `{ts, mono_ns, universe, sequence, dmx_sha256, ch1_32, payload_hex}`),
  `rbss_artnet_truth_frames.slice.jsonl` (363 MB sidecar; rows carry `sequence`, `dmx_sha256`,
  `elapsed_ms`, `soundswitch_id`, `transport`, `frame_index`, `native_autoloop{…}` — **no
  mono_ns**), `alignment_index.jsonl` (per-surface windows with `t_start_mono`/`t_end_mono` in
  seconds), `actions.jsonl`, `status_samples.jsonl`.
- Scripted alignment windows (mono seconds): 528e8b22 314819.65→314909.56; ae9e3c61
  315100.01→315188.58; 9947c65e 315343.27→315386.23 (plus one earlier recovered window without
  mono anchors); fc10fc02 315406.08→315494.60 and 315442.41→315530.88 (capture ends mid-track).
  Autoloop windows exist with labels `autoloop_SSAutoLoopN.ssfile` and phase_tick notes.
- The elapsed→U0 join is the one documented in
  `docs/plans/active/soundswitch_perfect_parity_finisher_spec.md` §B.1: sidecar row →(sequence,
  dmx_sha256, **in file order**)→ U1 packet → that packet's `mono_ns` → nearest U0 packet(s).
  ArtDMX `sequence` wraps 0-255 and all-zero frames share one sha
  (`076a27c7…f36560`), so the join MUST advance monotonically (two-pointer; first match at or
  after the previous match position) — never a global dict lookup.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Do not touch** `state_manager.py`, `native_autoloop_resolver.py` render/suppression semantics,
  `soundswitch_pack_runtime.py`, `soundswitch_pack_controller.py`, the 200 Hz tick, OS2L, MIDI,
  LED/Govee, or laser executor paths. This spec is exporter/oracle/fixture/lane work only.
- **Do not** re-litigate resolution or ordering (A.1 table). Do not add interpolation. Do not use
  U1 or self-render as truth. Do not require or take a new capture.
- **Do not** hardcode SSIDs/GUIDs/counts as behavior. Witness SSIDs appear ONLY in fixtures,
  registries (as evidence records), and tests that read those fixtures.
- The capture directory is **read-only**. Fixture/registry builders write only into
  `tests/fixtures/…` and temp dirs.
- The stale `local/soundswitch/rbss_canonical_pack` must NOT be loaded by any test (schema-stale;
  gitignored; machine-local). Tests that need a pack export a fresh temp one (pattern:
  `tests/test_soundswitch_laser_player.py::CurrentPackGoldenTests.setUpClass`, `:571-577`).
- Fixture provenance comes from the sidecar join only — never from fitted (t0, pitch) alignments
  (those were diagnostic instruments; they don't belong in committed evidence).
- Commit after each task; run `python3 -m unittest discover rb_ss_bridge_v2/tests` from the parent
  dir before each commit.

### Task 1 — `tools/ssfmt/build_parity_fixture.py` (NEW): capture→fixture builder with provenance

Offline CLI (same import-path bootstrap as `tools/ssfmt/parity_oracle.py:10-13`). Pure core
functions; I/O only in `main()`. Inputs: `--capture <dir>` (default the parity capture),
`--pack <fresh export dir>`, `--out <fixture.json>`. Steps:

1. **U0 run log.** Stream `artdmx_packets.jsonl`; keep `universe == 0` rows (cheap pre-filter:
   `b'"universe":0,' in raw_line`); collapse consecutive rows with equal `dmx_sha256` into runs
   `{s: first mono_ns, e: last mono_ns, n: count, f: ch1_32[:19]}`. (~2582 runs expected.)
2. **Sidecar→mono join (pure seam `join_sidecar_to_mono(sidecar_rows, u1_rows)`).** Stream both
   files once, in order. For each sidecar row whose `soundswitch_id` is a witness SSID: advance a
   U1 cursor (universe==1 packets only) until `(sequence, dmx_sha256)` matches at-or-after the
   cursor; record `(ssid, elapsed_ms, mono_ns)`; move the cursor past the match. If no match within
   a bounded lookahead (10,000 packets), drop the row (count it). Sanity gate: within each witness
   window the joined `(elapsed_ms, mono_ns)` pairs must be jointly monotone (Kendall-tau style
   spot check is overkill — assert elapsed differences and mono differences have the same sign for
   ≥99% of consecutive pairs); abort loudly otherwise.
3. **Row selection (pure seam `select_rows(joined, runs, events)`).** Candidate sample points per
   witness: for each timeline event `t` of the document (from the pack JSON), the joined sidecar
   row nearest to `t + 150 ms` (post-boundary state) and, for holds longer than 2 s, one mid-hold
   point. Keep a candidate only if its mono lands inside a U0 run with ≥120 ms margin to both run
   edges (steady state — U0 cadence is ~25-40 ms) and inside a scripted alignment window for that
   SSID. `u0_frame` = that run's 19-channel frame; `elapsed_ms` = the joined sidecar elapsed
   (never a model-derived time).
4. **Disk-consistency screen + divergence ledger (pure seam `screen_rows(rows, document,
   venue_values)`).** Render the pack model at each candidate's elapsed via
   `rb_ss_bridge_v2.soundswitch_laser_player.render_scripted_frame`. Split candidates:
   - model == u0 → **witness row** (these go in `scripted{ssid}` and must pass forever);
   - model != u0 → **divergence candidate** → it must be *classified with evidence*, never
     silently dropped:
     - `cross_deck_bleed`: the u0 frame is not reachable from the document's own dictionary — no
       subset of its cues' venue values (plus clear semantics) can produce the lit channel values
       (implement the cheap per-channel value-set reachability check: every nonzero channel value
       in u0 must appear in some dictionary cue's venue values for that channel, else unreachable);
       expected for ae9e@239-class and 9947@51811-class rows near track edges;
     - `stale_source_edit`: reachable values but wrong event association, at an event whose
       neighbors byte-match (fc10 refs 208/211; ae9e strobe cycle) — record the event time, ref,
       expected disk frame, observed U0 frame, and channel diffs;
     - `join_ambiguity`: everything else (report; investigate before shipping if count > 0 in a
       lit region).
   Emit ledger entries under a top-level `capture_source_divergence: {ssid: [entries…]}` key.
5. **Output.** Fixture JSON shape stays back-compatible: top-level `capture_id`, `scripted:
   {ssid: [{elapsed_ms, label, u0_frame, mono_ns, run_ms}…]}` (extra keys are ignored by
   `tools/ssfmt/parity_oracle.py:22-30` — [confirmed]) plus `capture_source_divergence` and a
   `builder: {tool, join_stats}` block. Target ≥4 witness rows per SSID including: both existing
   528e rows, ae9e@375, 9947@51864, fc10@127380 (all byte-stable anchors), plus for each formerly
   contaminated witness at least: one clear-state row (fc10 ~128.8 s: `[0×7,255,255,0×10]`),
   one re-applied-cue row (fc10 ~129.4 s RC cycle), one long-hold row (9947 NEON hold 52.5-54.2 s;
   ae9e post-clear B-pointy hold near 14.9-15.2 s keeps `ch8=90, ch9=115`), and one first-lit row
   per witness where the window covers it. Exact elapsed values come from the join.

Also delete nothing: the old fixture is replaced in Task 2, and DD42028C's permutation regression
fixtures (wherever they live in `tests/`) stay untouched.

### Task 2 — Replace the fixture; rewrite `ReducedCaptureFixtureTests`

- Run the Task-1 builder against a fresh export (temp dir) and commit the new
  `tests/fixtures/soundswitch/parity_oracle/scripted_reduced.json`.
- Rewrite `tests/test_soundswitch_parity_oracle.py::ReducedCaptureFixtureTests`:
  - `setUpClass` exports a fresh temp pack via `export_pack(Path.home() / "Music/SoundSwitch/
    default.ssproj", …)` guarded by `@unittest.skipUnless(Path.home().joinpath("Music/SoundSwitch/
    default.ssproj/.ssproj").is_file(), …)` (machine-local test, like CurrentPackGoldenTests; it
    must NOT depend on CWD or the stale canonical pack).
  - Assert every fixture row classifies **MATCH** (whole-report `passed` per SSID).
  - Assert the divergence ledger is present for ae9e3c61 and fc10fc02 with class
    `stale_source_edit`/`cross_deck_bleed` entries, and that ledger SSIDs still pass their witness
    rows (divergence is documented, not excused into the pass set).
  - **Negative control (must-fail-then-pass pin):** re-classify the same fixture rows against a
    renderer fed a deliberately mis-resolved document — rebuild each witness's events with
    `key_to_guid` shifted by +1 (i.e., the pre-74cbf15 exact-R behavior) via the pure resolver, and
    assert the report FAILS. This pins the regression class without any whitelist.
- Keep `PureParityOracleTests` as-is.

### Task 3 — Evidence registry + evidence-driven lanes (scripted)

1. **Registry fixture** `tests/fixtures/soundswitch/scripted_parity_registry.json` (committed),
   written by a new offline CLI `tools/ssfmt/update_parity_registry.py` (same bootstrap; inputs
   `--pack`, `--fixture`, `--out`). Per witness SSID:
   `{source_sha256, venue_source_sha256, capture_id, verdict, oracle_report_sha256, rows_passed,
   rows_total, layout, divergence: [ledger entries]}` where `venue_source_sha256` is the
   `SoundSwitchVenues.bin` sha from the pack manifest's `source_inventory` ([confirmed] present —
   `soundswitch_pack.py:456-457`). `oracle_report_sha256` = sha256 of the canonical JSON of the
   oracle report. **Both hashes pin the evidence**: cue values live in the venue file, so a venue
   edit must void scripted evidence even when the ssfile is untouched.
2. **Pure lane inputs** in `soundswitch_parity_registry.py`: add
   `generalized_witness_passed(registry_docs, layout, document_fully_resolved: bool) -> bool` —
   True iff ≥1 registry entry of the same `layout` has `verdict == "PASS"` (with truth source U0)
   AND the candidate document resolved every positive reference (no `resolved_cue_guid is None`
   among its cue events) — that is B.1's (a)+(b) generalization rule made executable. Unit-test it
   pure.
3. **Compiler plumbing** (`soundswitch_pack.py`): `compile_pack_artifacts(project, *,
   generator_commit, parity_registry: Mapping[str, Any] | None = None)`. `_document(…)` receives
   the registry + the per-document facts and computes:
   - `oracle_proven` iff registry entry exists for this SSID with `verdict == "PASS"`,
     `source_sha256` equal to the document's, and `venue_source_sha256` equal to the current
     venue file sha (thread it in from `project.source_inventory`);
   - else `algorithm_generalized` iff `structural_supported` and the Task-3.2 helper says yes;
   - else `unverified_parity`.
   `parity_evidence` already carries `capture_id`/`oracle_report_sha256` fields
   ([confirmed] `soundswitch_parity_registry.py:25-39`) — populate them from the registry entry
   for `oracle_proven` docs. The implemented generalized lane reason is
   `"generalized_supported_layout_family_<layout>"`, reflecting that the supported loaded-layout
   family shares one renderer path and still fails closed on unresolved or stale cue references.
   - **Lane-count scoping fix:** manifest `parity_lanes` counts ONLY active supported documents
     (scripted docs where `path in active_scripts` and doc parsed; autoloops where the loop is in
     the active/enabled set already computed for `_active_union`; every static slot). Add
     `parity_lanes_inactive` for the rest so nothing is hidden. Update
     `_assert_publishable_parity` in `tools/export_soundswitch_pack.py` only if the manifest key
     names change (they should not — keep `parity_lanes` as the active-scope summary).
4. **Export tool** (`tools/export_soundswitch_pack.py`): both `export_pack` and `publish_pack`
   load the registry fixtures from `REPO_ROOT / "tests/fixtures/soundswitch/"` when present (all
   three: scripted/autoloop/static; missing file → empty registry → fail-closed lanes) and pass
   them to `compile_pack_artifacts`.
5. **Verifier** (`soundswitch_pack_verifier.py`): extend `_validate_parity` — a document whose
   `parity_lane == "oracle_proven"` must carry non-empty `capture_id` and `oracle_report_sha256`
   in its `parity_evidence`; `truth_source` must be `"SoundSwitch U0"`. (Schema keys are already
   sanitized-checked.) Do NOT verify against the registry file itself — the pack must stay
   self-describing; the hashes in the evidence are the audit trail.
6. **Expected outcome on a fresh export** ([assumed] — verify, don't force): 4 scripted witnesses
   `oracle_proven`; every other active `shared_441_dictionary_timeline` scripted doc
   `algorithm_generalized`; any scripted doc with an unresolved positive reference stays
   `unverified_parity` and must be listed + investigated (a miss inside a healthy supported file
   usually means a decoder misparse — surface, don't absorb).

### Task 4 — Autoloop lanes from capture evidence

1. Extend `tools/ssfmt/build_parity_fixture.py` with an autoloop mode: for each
   `alignment_index.jsonl` window labeled `autoloop_SSAutoLoopN.ssfile`, join sidecar rows (rows
   where `native_autoloop.target_identity == "SSAutoLoopN.ssfile"` and
   `native_autoloop.phase_tick` is an integer) to mono via the same Task-1 join, then to the
   steady U0 run at that mono. Emit `autoloop: {identity: [{phase_tick, u0_frame, mono_ns}…]}`
   rows into `tests/fixtures/soundswitch/parity_oracle/autoloop_reduced.json` (≥6 spread phases
   per covered loop where available; include phase 0 and a wrap-adjacent phase when present).
2. Classify with the existing `classify_autoloop` against the fresh pack
   (`render_autoloop_frame(document, phase_tick)`), extend `tools/ssfmt/parity_oracle.py` to run
   the autoloop fixture too (`--fixture` gains the autoloop file or a second flag — mirror the
   scripted code path).
3. **[unknown — resolve empirically, in this order]:** whether current autoloop rendering matches
   U0 at the sampled phases. If a loop FAILS: produce the same per-boundary diagnostic table as
   scripted (expected vs U0 vs differing channels, the loop's serialized events, cycle_ticks) and
   fix ONLY what the evidence implicates (candidate defect classes, most-likely first: pre-roll
   (negative-time) handling order after the saved-order change; `cycle_ticks` metadata vs the
   document's own beat count; a resolution defect shared with scripted — already fixed — so
   re-export first). Do not touch the bridge's live anchor/selection code paths
   (`native_autoloop_resolver.py`) — phase_tick here comes from the sidecar; render parity is the
   only claim being promoted.
4. Near-empty loops SSAutoLoop5/18/3: oracle-check their windows. U0 dark during the window ⇒
   the dark render is **correct** ⇒ eligible for `oracle_proven` with the dark evidence recorded.
   U0 lit ⇒ exporter under-render ⇒ keep `unverified_parity`, record the failing window, and STOP
   (report as a blocker; do not guess a fix).
5. `tools/ssfmt/update_parity_registry.py` writes
   `tests/fixtures/soundswitch/autoloop_parity_registry.json`; `_document` lane logic for
   autoloops consumes it identically (source hash + venue hash pinning). Generalization for
   autoloops: same helper, keyed on layout, and require the loop document fully-resolved.

### Task 5 — Static lanes from capture evidence + the C6 assertion

1. Builder static mode: recover the 3 attempted look windows from `actions.jsonl`
   (`static_slot_*` action rows — the finisher spec §B.1 static assertion describes this recovery)
   and record each look's held U0 frame → `tests/fixtures/soundswitch/parity_oracle/
   static_reduced.json` `{slot_index: {u0_frame, window}}`. Classify with `classify_static`
   against `render_static_look_frame(look)` output from the fresh pack.
2. Registry `static_parity_registry.json`: per slot `{look_source_evidence: venue_source_sha256 +
   static-look source offsets/sha inputs available in the pack, verdict}`. Lanes in `_look`
   (`soundswitch_pack.py:134-157`):
   - `oracle_proven` for slots with a passing U0 record (expected: the 3 captured looks);
   - `algorithm_generalized` for slots whose `non_generic_assertion.passed` is True AND ≥1 slot is
     `oracle_proven` (the generic-only pipeline witnessed against U0 + per-slot inertness proof =
     byte-exact by construction — finisher spec Task C6 acceptance);
   - `unverified_parity` + surfaced for any slot failing the assertion (none expected — if one
     fails, STOP and report; dedicated-path composition is out of this spec's scope).
3. If `actions.jsonl` does not contain recoverable static windows ([unknown]), fall back to the
   documented static byte-match evidence in the finisher spec §A.2 ONLY as a pointer — do NOT
   fabricate rows; instead leave the 3 looks `algorithm_generalized` via the assertion route and
   record `static_capture_windows: unavailable` in the registry with the reason. Zero static slots
   may end `unverified_parity` unless an assertion genuinely fails.

### Task 6 — Ship-gate wiring, canonical republish, docs

1. Re-export a fresh temp pack; confirm manifest `parity_lanes` (active scope) shows
   `unverified_parity: 0` — every deviation is a named blocker to report, not to suppress.
2. Republish the canonical pack via the normal publish path (offline command:
   `python3 tools/export_soundswitch_pack.py --publish-canonical --result-json /tmp/rbss_publish.json`)
   so the machine-local pack regains schema-currency. This writes only under `local/` (gitignored)
   — [confirmed] the publish path never touches hardware or the bridge.
3. Docs per the anti-drift contract: read `docs/agents/change_contracts.yml`, find the
   `soundswitch_output` contract (and `tests` if fixture layout is listed), update every doc in its
   `docs_update` list to reflect: 1-based reference resolution (with the label-space
   reconciliation), saved-order selection, the evidence registry + lane computation, and the
   divergence-ledger concept. Patch `docs/plans/active/soundswitch_perfect_parity_finisher_spec.md`
   with a short dated note at §0.4 Finding 2 and Task C4 pointing at this spec's Part A (do not
   rewrite history; add the reconciliation). Update
   `docs/research/soundswitch/soundswitch_perfect_parity_ghidra_evidence.md` ONLY by appending a
   dated addendum note (it is a recorded evidence packet — never edit recorded findings).
4. Run the full gate (Part E) and produce the final report (below).

---

## Part C — Invariants that MUST still hold (live safety)

- The 200 Hz push loop gains no blocking/socket/MIDI/serial/filesystem/subprocess work — none of
  these tasks touch `state_manager.py`'s tick (`_push_tick`/`_drive_pack_output`).
- Stop/unload/track-change/discontinuity still emit ZERO (driver semantics untouched); the C8
  parity-live gate (`parity_live_blocks_document`) semantics unchanged — lanes feeding it get
  *better*, the gate itself does not move.
- SS-present suppression intact; blackout/emergency precedence above everything; held manual
  static behavior unchanged (`docs/architecture/runtime_invariants.md`).
- Source SoundSwitch project stays read-only; only verified packs load; publish/export never
  enables output, changes backend, or starts the bridge.
- Status/log surfaces stay sanitized: no filesystem paths, port names, device names, or raw frames
  in any new status/evidence string (registry entries live in fixtures, not status).
- Nothing under `local/`, no capture bytes, and no venue/project bytes are committed.

## Part D — Tests

- Task 1: pure-seam unit tests (new `tests/test_build_parity_fixture.py`) for
  `join_sidecar_to_mono` (synthetic streams incl. sequence wrap + duplicate all-zero shas +
  a dropped row), `select_rows` (margin/window filters), `screen_rows` (reachability →
  `cross_deck_bleed`; wrong-event → `stale_source_edit`), all without touching the real capture.
- Task 2: rewritten `ReducedCaptureFixtureTests` (machine-local skip guard) — all rows MATCH; the
  +1-shifted negative control FAILS; ledger entries present and classified.
- Task 3: pure tests for `generalized_witness_passed`; compiler tests asserting lane outcomes for:
  registry hit + hash match → `oracle_proven` with populated evidence; registry hit + stale
  source hash → `unverified_parity`; registry hit + stale venue hash → `unverified_parity`;
  same-layout generalization; unresolved-reference doc stays unverified. Extend
  `tests/test_soundswitch_scripted_parity.py` (keep its pure style — synthetic registries, no
  disk). Export-tool test: registry files loaded from fixtures path and threaded through
  (`tests/test_prove_soundswitch_pack_generation.py` / pack tests already exercise
  `compile_pack_artifacts` — extend, don't fork).
- Task 4: autoloop fixture classify tests (machine-local guard); pure diagnostic-table helper test.
- Task 5: static lane tests — assertion-pass + proven-witness ⇒ generalized; synthetic failing
  assertion ⇒ unverified + surfaced (extend `tests/test_static_looks.py`).
- Task 6: a manifest-scope test — inactive decoded documents do not count into `parity_lanes`
  (active scope) but appear under `parity_lanes_inactive`; `_assert_publishable_parity` passes on
  a lane-complete pack and still fails when an ACTIVE supported doc is unverified.

## Part E — Acceptance (definition of done)

- [ ] Task-1 builder committed with pure seams + unit tests; regenerating the fixture from the
      capture is a one-command, deterministic operation.
- [ ] New reduced fixture committed: every witness row MATCHes on a fresh export at HEAD;
      divergence ledger entries recorded for ae9e3c61 + fc10fc02 with byte evidence; the
      +1-shift negative control fails.
- [ ] Scripted registry committed; fresh-export lanes: 4 witnesses `oracle_proven`, remaining
      active scripted docs `algorithm_generalized` (or each exception named with its defect);
      evidence hashes pin both ssfile and venue bytes.
- [ ] Autoloop fixture + registry committed; covered loops `oracle_proven` or each failure
      reported with its per-boundary diagnostic table (blocker, not silence); near-empty loops
      resolved dark-correct or reported.
- [ ] Static: 3 captured looks `oracle_proven` (or the documented fallback), remaining slots
      `algorithm_generalized` via the passing C6 assertion; zero static `unverified_parity`.
- [ ] Fresh-export manifest: ACTIVE-scope `parity_lanes.unverified_parity == 0`; publication gate
      passes; inactive documents reported separately.
- [ ] Canonical pack republished locally (machine-local step; nothing committed).
- [ ] Full software gate green, run from the repo parent dir:
      `python3 -m unittest rb_ss_bridge_v2.tests.test_soundswitch_parity_oracle
      rb_ss_bridge_v2.tests.test_soundswitch_scripted_parity
      rb_ss_bridge_v2.tests.test_soundswitch_scripted_resolution
      rb_ss_bridge_v2.tests.test_soundswitch_scripted_first_event
      rb_ss_bridge_v2.tests.test_static_looks rb_ss_bridge_v2.tests.test_soundswitch_midi_input
      rb_ss_bridge_v2.tests.test_native_autoloop_resolver
      rb_ss_bridge_v2.tests.test_state_manager_pack_driver
      rb_ss_bridge_v2.tests.test_runtime_status` then
      `python3 -m unittest discover rb_ss_bridge_v2/tests`, and from the repo root:
      `python3 tools/check_docs_metadata.py && python3 tools/check_agent_contracts.py &&
      python3 tools/check_docs_drift.py`; `python3 tools/check_docs_staleness.py --report`
      (advisory); `git diff --check`.
- [ ] Docs updated per the `soundswitch_output` change contract; finisher-spec reconciliation note
      added; evidence packet addendum appended (never edited in place).
- [ ] Worktree clean or every remaining change explicitly explained.

## When you finish (report back)

Commit style: one commit per task, imperative subject (match `git log` tone). Report: (1) files
changed per task; (2) fixture row table before/after with per-row verdicts; (3) the divergence
ledger contents; (4) lane summary before (`{'unverified_parity': 118}`) and after, split
active/inactive; (5) autoloop per-loop verdicts + any diagnostic tables; (6) static per-slot
outcomes; (7) full gate output; (8) anything still `unverified_parity` with its named defect —
plainly stated, no "should work".
