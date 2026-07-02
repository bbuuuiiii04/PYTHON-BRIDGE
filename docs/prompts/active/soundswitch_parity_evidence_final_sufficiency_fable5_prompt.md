---
doc_status: active-prompt
truth_level: current-commit-and-command-output-grounded
last_verified_commit: 8ce8a8d
last_verified_date: 2026-07-02
validation_scope: Fable 5 read-only final sufficiency review prompt for the SoundSwitch parity evidence gate; no implementation or runtime authority
---

# Fable 5 Prompt - SoundSwitch Parity Evidence Final Sufficiency

Target model: Claude Fable 5  
Effort: xhigh

Mission:
Perform a final sufficiency review of the SoundSwitch parity evidence closeout at commit
`8ce8a8dbdb8c92e395f3544573fc552e374868ec`. Decide whether the current repo evidence is sufficient
to treat the SoundSwitch pack publication software gate as passed. Do not implement changes.

Benign scope:
This is benign local software review for Brandon's DJ lighting bridge and agent workflow. It is not
a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences,
model-distillation, or hidden-reasoning extraction task. Review only normal software correctness,
tests, maintainability, runtime safety, evidence discipline, and operator behavior inside the named
scope.

Current goal:
Fable's handoff in `docs/plans/active/soundswitch_parity_evidence_finisher_spec.md` asked Codex to
finish the passive-capture parity evidence path: Autoloop fixture/registry, Static Look fallback,
fresh export with active `parity_lanes.unverified_parity == 0`, canonical local publish, docs, and
full software gates.

Proposed state at commit `8ce8a8d`:
- `tools/ssfmt/build_parity_fixture.py` splits Autoloop sidecar rows into contiguous mono-time
  segments, samples with a 10 ms steady-run margin, chooses a passing segment when present, and
  records non-PASS segments under `capture_source_divergence`.
- `tools/ssfmt/update_parity_registry.py` writes only PASS Autoloop rows to the positive promotion
  registry; capture-diverged rows remain in the fixture ledger.
- `soundswitch_parity_registry.py` generalizes across the three supported loaded-layout variants
  only when a current SoundSwitch U0 PASS witness exists and the target document is fully current.
- `soundswitch_pack.py` now requires positive cue references to resolve into the current venue cue
  set before algorithmic generalization.
- Regenerated fixtures:
  - `tests/fixtures/soundswitch/parity_oracle/autoloop_reduced.json`
  - `tests/fixtures/soundswitch/autoloop_parity_registry.json`
- Direct Autoloop oracle registry now has 10 PASS identities:
  `SSAutoLoop13`, `16`, `18`, `3`, `5`, `52`, `53`, `54`, `55`, `6`.
- Autoloop capture-divergence ledger records 8 non-promoted identities:
  `SSAutoLoop14`, `15`, `17`, `46`, `47`, `48`, `50`, `8`.
- Fresh software export at this commit reports active lanes:
  `{'algorithm_generalized': 69, 'oracle_proven': 14, 'unverified_parity': 0}`.
- Fresh software export reports inactive lanes:
  `{'algorithm_generalized': 29, 'oracle_proven': 0, 'unverified_parity': 6}`.
- Canonical local publish succeeded with manifest SHA:
  `21162a3b180798c5936632ddcbb6f1d031b50f92c3da59039617e7ce7a3f33c3`.

Already-run verification:
- `python3 -m unittest rb_ss_bridge_v2.tests.test_soundswitch_parity_oracle rb_ss_bridge_v2.tests.test_soundswitch_scripted_parity rb_ss_bridge_v2.tests.test_soundswitch_scripted_resolution rb_ss_bridge_v2.tests.test_soundswitch_scripted_first_event rb_ss_bridge_v2.tests.test_static_looks rb_ss_bridge_v2.tests.test_soundswitch_midi_input rb_ss_bridge_v2.tests.test_native_autoloop_resolver rb_ss_bridge_v2.tests.test_state_manager_pack_driver rb_ss_bridge_v2.tests.test_runtime_status`
  - result: 258 tests OK.
- `python3 -m unittest discover rb_ss_bridge_v2/tests`
  - result: 2638 tests OK, skipped=3, expected failures=1.
- `python3 tools/check_docs_metadata.py`
  - result: passed.
- `python3 tools/check_agent_contracts.py`
  - result: passed.
- `python3 tools/check_docs_drift.py`
  - result: passed.
- `python3 tools/check_docs_staleness.py --report`
  - result: advisory report only; `soundswitch_output`, `tests`, `docs`, and `soundswitch_research`
    reported fresh, while broader pre-existing contract drift remains listed.
- `git diff --check`
  - result: passed.
- `python3 tools/ssfmt/parity_oracle.py --pack /tmp/rbss_after_parity.04lhZA/pack --fixture tests/fixtures/soundswitch/parity_oracle/autoloop_reduced.json`
  - result summary: 10 PASS, 8 SKIP.
- `python3 tools/export_soundswitch_pack.py --publish-canonical --result-json /tmp/rbss_publish.json`
  - result: `{"ok":true,"verdict":"published","artifact_count":95,"first_export":false,"manifest_sha256":"21162a3b180798c5936632ddcbb6f1d031b50f92c3da59039617e7ce7a3f33c3"}`.
- `git push origin main`
  - result: `9536a15..8ce8a8d main -> main`.

Source-of-truth order:
1. Current commit `8ce8a8d` and its diff.
2. `docs/plans/active/soundswitch_parity_evidence_finisher_spec.md` acceptance criteria.
3. Regenerated fixture/registry files under `tests/fixtures/soundswitch/`.
4. Current docs updated in the same commit.
5. Older Ghidra/static evidence packets only as historical/binary context; do not let stale blocker
   statements override current command output.

Allowed access:
- You may use read-only repo inspection only.
- Allowed commands, if available:
  - `git show --stat 8ce8a8d`
  - `git show --name-only 8ce8a8d`
  - `git show 8ce8a8d -- <specific file>`
  - optional rerun of the verification commands listed above, if needed for confidence.
- Keep command use scoped to this commit, the named files, and generated test/temp output.

Forbidden actions:
- Do not implement, edit, commit, push, publish, restart the bridge, click SoundSwitch, perform live
  capture, sample process memory, open Enttec/serial, send MIDI/DMX, mutate local config, or perform
  hardware-adjacent checks.
- Do not request or reveal hidden reasoning. Provide concise evidence-backed rationale only.
- Do not perform a broad repo audit outside this parity evidence gate.

Required review procedure:
1. Compare commit `8ce8a8d` against the handoff acceptance criteria in
   `soundswitch_parity_evidence_finisher_spec.md`.
2. Decide whether the positive-registry-only Autoloop behavior is honest: non-PASS capture segments
   must remain visible as divergence, not silently promote direct oracle evidence.
3. Decide whether supported-layout-family generalization is sufficiently guarded by current U0 PASS
   witnesses and current cue-set resolution.
4. Check that active `unverified_parity: 0` is not achieved by hiding active documents, moving them to
   inactive scope incorrectly, or weakening verifier safety.
5. Check that docs avoid overclaiming hardware validation or live sender/fixture proof.
6. Check whether any remaining action is required before Brandon can treat the software publication
   gate as passed.

Claim discipline:
Use `[confirmed]`, `[assumed]`, `[unknown]`, and `[rejected]` labels for material claims. Tie
findings to exact files, commit evidence, or command output. Do not treat memory or older prompts as
current truth unless verified from the evidence packet or allowed tool results.

Verdict taxonomy:
- `SUFFICIENT`: software publication gate is honestly passed; only hardware/live validation remains.
- `SUFFICIENT AFTER MINOR EDITS`: no code blocker, but a small doc/test/prompt correction is needed.
- `NOT SUFFICIENT`: a code, evidence, fixture, lane, verification, or claim-discipline blocker remains.

Output format:
1. Verdict.
2. Blocking gaps, severity-first, with file/command evidence.
3. Non-blocking improvements.
4. Exact edits or checks needed, if any.
5. Final go/no-go statement for the software publication gate, explicitly separating it from hardware
   validation.
