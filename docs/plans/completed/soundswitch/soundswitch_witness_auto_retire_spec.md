---
doc_status: active-plan
truth_level: code-verified
last_verified_commit: 87d5ed6
last_verified_date: 2026-07-02
validation_scope: Codex implementation spec for auto-retiring stale parity capture evidence when a witnessed SoundSwitch document's SOURCE was edited; software-only, no live/hardware action.
---

# Codex Implementation Spec — Edited-Witness Auto-Retire of Stale Parity Capture Evidence

## Part A — Context & root cause (verified; read, do not implement)

Operator decision (2026-07-02): editing a capture-witnessed document must not block
the export. Today it does:

- The canonical export recomputes parity registries from the committed capture
  fixtures against the pack being staged
  (`tools/export_soundswitch_pack.py:96` `_recomputed_parity_registries`, called
  from `_compile_and_stage_with_self_healed_parity` at `:120`). [confirmed]
- A witnessed document whose render no longer matches its own capture rows gets a
  `verdict: "FAIL"` registry record (`tools/ssfmt/update_parity_registry.py:204`
  `_autoloop_registry_record` docstring states the pin-don't-generalize rule;
  scripted analog at `:136` `build_scripted_registry`). The compiler maps a FAIL
  record to `unverified_parity`. [confirmed]
- `publish_pack` then refuses: `_assert_publishable_parity`
  (`tools/export_soundswitch_pack.py:551`) raises
  `UnverifiedParityPublishError` when active `unverified_parity > 0`; verdict
  string `"unverified_parity"` (`:656`). Prior pack preserved. [confirmed]

Why the pin exists: a FAIL must not silently fall back to `algorithm_generalized`,
because the mismatch might be a REAL render/exporter regression. That protection
must survive this change.

**The discriminator that lets us tell the two cases apart** [confirmed against
current code]:

- Fixture rows carry NO source pins
  (`tests/fixtures/soundswitch/parity_oracle/scripted_reduced.json` rows are
  `{elapsed_ms,label,mono_ns,run_ms,u0_frame}` only). [confirmed]
- But the COMMITTED registry snapshots
  (`tests/fixtures/soundswitch/{scripted,autoloop,static}_parity_registry.json`,
  loaded at `tools/export_soundswitch_pack.py:78-92`) carry, per identity:
  `source_sha256` (the document's own source bytes), `venue_source_sha256`
  (the `SoundSwitchVenues.bin` sha), and `verdict`, all recorded when the
  evidence last passed. [confirmed — see record construction at
  `tools/ssfmt/update_parity_registry.py:150-163` and `:229-241`]

So, for a freshly-recomputed FAIL record whose committed counterpart was PASS:

- committed `source_sha256` ≠ fresh `source_sha256` → the operator edited the
  document itself → evidence is about content that no longer exists → retire.
- committed `venue_source_sha256` ≠ fresh `venue_source_sha256` → the operator
  edited the venue cue bank (a shared Attribute Cue's values reach the witness's
  render without touching the document's own bytes) → retire. [confirmed
  mechanism: venue values live in `SoundSwitchVenues.bin`, not the `.ssfile`]
- BOTH shas equal → same sources, different render → only the generator/render
  code can be responsible → genuine regression → KEEP the FAIL pin and keep
  refusing to publish. [confirmed logic — this is the case the pin exists for]

Retiring = removing that identity's record from the fresh registry for this
export. An absent record means "no capture evidence", and the compiler may then
classify the document `algorithm_generalized` through the existing
generalization path (supported layout family + resolvable references), exactly
like the ~40 never-captured documents. [confirmed — `_autoloop_registry_record`
returns `None` for empty rows and the docstring documents absence ⇒ compiler may
generalize]

The export does NOT write back to `tests/fixtures/` (registries are committed by
humans/tools separately) [confirmed — no write sites in
`tools/export_soundswitch_pack.py` touch `PARITY_REGISTRY_DIR` or the fixtures].
Keep it that way: retirement is recomputed in memory on every export
(idempotent, deterministic), and the committed PASS-at-old-sha record keeps
serving as the "last accepted evidence" baseline.

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Do NOT touch: `state_manager.py`, `soundswitch_laser_player.py`,
  `native_autoloop_resolver.py`, `soundswitch_pack_loader.py`,
  `soundswitch_pack_verifier.py`, the manifest schema, any `tests/fixtures/`
  file, or the live pack at `local/soundswitch/rbss_canonical_pack`.
- Do NOT change the manifest format (the verifier is a strict superset checker;
  a new manifest field ripples into it — out of scope).
- Do NOT make the export write into `tests/fixtures/`.
- The static surface is out of scope (its registry is a single fallback record
  re-asserted by C6 every export, not per-document point rows).

### Task 1 — `tools/ssfmt/update_parity_registry.py`: pure reconciliation seam

Add a pure function (dicts in, dicts out — no filesystem):

```python
def reconcile_edited_witnesses(
    fresh: dict[str, dict[str, object]],
    committed: dict[str, dict[str, object]],
) -> tuple[dict[str, dict[str, object]], list[dict[str, str]]]:
    """Drop FAIL records whose sources were edited since the evidence last passed.

    A fresh record is retired iff ALL hold:
      - fresh verdict == "FAIL";
      - committed record for the same identity exists with verdict == "PASS";
      - committed source_sha256 is non-empty; and
      - fresh source_sha256 != committed source_sha256
        OR fresh venue_source_sha256 != committed venue_source_sha256.

    Anything else passes through unchanged: FAIL with identical shas stays
    pinned (possible render regression); FAIL with no committed record or a
    committed FAIL stays pinned (never auto-clear evidence a human has not
    accepted as PASS); PASS records are never touched.
    """
```

Return the reconciled registry (retired identities REMOVED) plus one retirement
entry per removal:

```python
{
    "identity": identity,
    "reason": "witness_source_edited",
    "committed_source_sha256": ...,
    "fresh_source_sha256": ...,
    "committed_venue_source_sha256": ...,
    "fresh_venue_source_sha256": ...,
    "capture_id": str(fresh_record.get("capture_id") or ""),
}
```

Read sha fields with `.get(...) or ""` string coercion; missing/None never
matches "changed" (a missing fresh sha must NOT trigger retirement — treat as
equal/unknown and keep the pin). Sort retirements by identity. Export the
function in `__all__` if the module has one.

### Task 2 — `tools/export_soundswitch_pack.py`: apply reconciliation in pass 2

In `_compile_and_stage_with_self_healed_parity` (`:120`), after
`fresh_registries = _recomputed_parity_registries(staging, stale_registries)`:

```python
retirements: list[dict[str, str]] = []
for surface in ("scripted", "autoloop"):
    fresh_surface = fresh_registries.get(surface)
    stale_surface = stale_registries.get(surface)
    if isinstance(fresh_surface, dict) and isinstance(stale_surface, dict):
        reconciled, retired = reconcile_edited_witnesses(fresh_surface, stale_surface)
        fresh_registries[surface] = reconciled
        retirements.extend(retired)
```

- Import `reconcile_edited_witnesses` beside the existing
  `build_*_registry` imports (`:32-33`).
- The existing `if fresh_registries == stale_registries: return staging`
  comparison must run AFTER reconciliation (so a retirement triggers the
  recompile/re-stage just like any other registry change).
- Thread `retirements` out of the function: change its return to
  `tuple[Path, list[dict[str, str]]]`, update its one caller in `publish_pack`
  (`:587`), and include the list in the publish result dict as
  `"parity_evidence_retired": retirements` (additive key; `[]` when none).
  `_canonical_publish_result` (`:660`) copies it through when present, and the
  failure dict gains `"parity_evidence_retired": []`.
- Log one line per retirement at INFO:
  `[EXPORT] parity-evidence-retired identity=<identity> reason=witness_source_edited`
  (no paths, no shas in the log — shas stay in the result JSON).

### Task 3 — docs (change-contract `soundswitch_pack_player`)

- `docs/plans/active/soundswitch_exporter_remaining_work.md`: one short entry
  under the 2026-07-02 finalization section describing auto-retire semantics
  (edited sources retire their stale point evidence and fall back to the
  generalized lane; identical-source FAILs still block publication).
- `docs/subsystems/soundswitch_output.md`: extend the parity-lane bullet (line
  ~24) with the same two sentences.
- `docs/validation/software_test_inventory.md`: name the new tests.
- Run all four docs checks (Part E).

## Part C — Invariants that MUST still hold (live safety)

- A FAIL record with UNCHANGED `source_sha256` AND `venue_source_sha256` still
  blocks trusted publication (`UnverifiedParityPublishError`) — auto-retire must
  never mask a render/exporter regression.
- Export/publish never enables output, never changes backend, never starts or
  restarts the bridge, never opens hardware (unchanged surface).
- The export remains read-only w.r.t. `tests/fixtures/` and the source project.
- All-or-nothing publish is preserved: staging discarded on any failure; prior
  canonical pack untouched.
- Sanitized outputs: log lines carry identity + reason only (identities are
  `SSAutoLoopN.ssfile` / SSID strings already present in existing logs); no
  filesystem paths.
- No change to `_push_tick`/StateManager/200 Hz surfaces (this is command-side
  export tooling only).

## Part D — Tests

New tests in `tests/test_export_pack_parity_self_heal.py` (reuse its harness) or
a sibling `tests/test_witness_auto_retire.py`:

Pure-seam tests for `reconcile_edited_witnesses` (no filesystem):
1. FAIL + committed PASS + doc sha changed → retired (record removed, one
   retirement entry with both sha pairs).
2. FAIL + committed PASS + doc sha equal + venue sha changed → retired.
3. FAIL + committed PASS + BOTH shas equal → kept (regression pin).
4. FAIL + no committed record → kept.
5. FAIL + committed FAIL → kept.
6. PASS records → untouched, no retirement.
7. Missing/empty fresh sha fields → kept (never retire on unknown).

Export-level test (synthetic staging, mirroring the self-heal test style):
8. An edited witness (fixture rows contradict the document; committed registry
   holds PASS at a different `source_sha256`) publishes successfully, the
   document's lane in the staged manifest is NOT `unverified_parity`, and the
   result dict contains the retirement entry.
9. The same setup with identical shas raises `UnverifiedParityPublishError`
   (verdict `unverified_parity`) — proves the regression path did not regress.

## Part E — Acceptance (definition of done)

- [ ] All Part D tests written and passing; every pre-existing test unmodified
      and passing: `python3 -m unittest discover tests`.
- [ ] `python3 tools/prove_soundswitch_pack_generation.py` still reports
      29 PASS / 0 FAIL / 0 INCOMPLETE.
- [ ] `python3 tools/check_docs_metadata.py`, `check_agent_contracts.py`,
      `check_docs_drift.py` pass; `check_docs_staleness.py --report` reviewed.
- [ ] `git diff --check` clean; no `tests/fixtures/` or `local/` modifications.
- [ ] Commit message: `Auto-retire stale parity evidence for edited witnesses`.
- Report back: the reconcile function location, the two result-dict keys added,
  and the exact test names proving cases 1, 3, 8, and 9.

## Adversarial self-review (already applied to this spec)

Forced failure scenario checked: operator edits a shared Attribute Cue used by a
witness at a sampled point — the document's own `source_sha256` does NOT change,
only `venue_source_sha256` does; a doc-sha-only discriminator would misclassify
this as a regression and keep blocking. That is why the venue sha is part of the
retirement condition. Second forced scenario: a code regression flips a witness
to FAIL while the operator ALSO edited an unrelated venue cue in the same save —
venue sha changed, so the FAIL retires and the regression is masked for that
document. Accepted residual: the regression remains caught by every OTHER
witness (whose shas are unchanged), by the proof gate, and by the suite; a
per-cue-reference sha pin would close it fully but is not worth the schema churn
for a solo rig.
