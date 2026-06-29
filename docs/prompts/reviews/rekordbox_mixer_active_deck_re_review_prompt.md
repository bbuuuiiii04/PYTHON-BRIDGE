---
doc_status: active-review-prompt
truth_level: reverse-engineering-review-instructions
last_verified_commit: a82cf16
last_verified_date: 2026-06-29
validation_scope: strict adversarial review of Rekordbox mixer active-deck static/passive-live RE reasoning and implementation readiness, including implementation-precision findings addressed in the active spec; review-only; no live sampling, restart, or hardware authority
---

# Strict Adversarial Review - Rekordbox Mixer Active-Deck RE

You are an independent adversarial reviewer for `rb_ss_bridge_v2`.

Goal: deeply review the Rekordbox mixer active-deck reverse-engineering work and
validate every finding against current executable code, current architecture
docs, RE evidence, and repo status docs. Fight assumptions aggressively. Do not
implement fixes.

Repo: `/Users/bbui/rb_ss_bridge_v2`
Branch: `main`
Prompt-generation observed HEAD: `918c0a1`, but verify current HEAD yourself
before reviewing.

## Hard Boundary

Review-only. Do not edit files, commit, push, restart the bridge, signal
processes, run live process-memory sampling, or touch MIDI, serial, Enttec, DMX,
Govee, SoundSwitch, lasers, LEDs, or hardware-adjacent outputs.

Static repo inspection is allowed. Static Ghidra/GhidraMCP reads are allowed.
Offline `/tmp/rbss_re/*` artifact inspection is allowed if present, but treat
local tmp artifacts as supporting evidence, not repo authority. If GhidraMCP is
unavailable, say so and do not invent RE confidence.

## Source Order

Use this authority order:

1. Current executable code and tests.
2. Config/status/runtime command surfaces.
3. Current architecture/subsystem docs.
4. Committed RE evidence docs.
5. Local `/tmp/rbss_re/*` artifacts.
6. Memory/old prompts/history, as context only.

Code beats docs. Current files beat old prompt text.

## Required Reads

Read these before forming a verdict:

- `AGENTS.md`
- `docs/architecture/current_architecture.md`
- `docs/architecture/runtime_invariants.md`
- `docs/architecture/active_deck_authority.md`
- `docs/subsystems/rekordbox_readers.md`
- `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md`
- `docs/research/rekordbox_mixer_active_deck_re_evidence.md`
- `docs/prompts/reviews/rekordbox_mixer_active_deck_re_review_prompt.md`
- `docs/status/active_work_registry.md`
- `docs/status/feature_status_matrix.md`
- `docs/status/validation_matrix.md`
- `rb_offsets.py`
- `rb_state_reader.py`
- `state_manager.py`
- `runtime_status.py`
- `models.py`
- relevant tests under `tests/`

## Critical Clarification To Preserve

Do not frame basic play/stop as an unresolved RE problem.

The bridge already has play/stop authority from Rekordbox offset live-position
movement via `RBStateReader`. Verify that in current code. The active-deck work
is about adding mixer authority: Deck 1/2 upfader plus LOW/BASS freshness,
invalidation, thresholds, hysteresis, resolver behavior, status, and heartbeat.
Do not frame direct master as missing or unreliable either; direct master is
current bridge code behavior when configured and currently ready. The mixer RE
evidence should not overclaim that its JSONL artifacts prove raw direct-master
bytes unless those fields are actually present.

Other Rekordbox versions are future validation work. They are not a blocker for
the local Rekordbox `7.2.11.0342` spec, but the spec must not overclaim support
beyond that local target.

## Review Surface A - Current Runtime Truth

Try to disprove every current-code claim:

1. `RBStateReader` already infers play/pause from `live_pos_per_deck` offset
   movement.
2. `Ev.MASTER_CHANGED` still writes or causes writes to
   `OutputState.active_deck` today.
3. Playing-only mirror auto-switch paths still exist today.
4. `runtime_status` heartbeat still conflates `master` and `active_deck` today,
   unless current code changed.
5. `rb_offsets.py` currently has legacy deck offset chains and no implemented
   named mixer fields unless current code changed.
6. Existing architecture forbids blocking work in the 200 Hz `StateManager`
   push loop.

For each, cite current `file:line`.

## Review Surface B - RE Evidence

Treat every RE claim as guilty until proven. Try to disprove:

1. The binary/version identity: Rekordbox `7.2.11.0342`, arm64 thin artifact,
   hashes, and Ghidra project/dumps match the stated target.
2. The static symbols actually support live mixer state, not UI-only or
   settings-only paths.
3. The bridge-readable root chain is supported:
   `base + 0x4e16ea8` -> holder `+0x40` -> engine -> graph `+0xa8` -> mixer
   vector `+0x458` -> mixer base -> channel vector `+0x2c8` -> channel graph.
4. The proposed `rb_offsets.py` chain semantics are correct: hops vs final
   offset, no missing dereference, no extra dereference.
5. Deck 1 = channel index `0` and Deck 2 = channel index `1` are proven by
   one-control-at-a-time passive samples.
6. Upfader raw range `0..1023` and normalization `raw / 1023.0` are proven.
7. LOW/BASS raw range `0..255`, normalization `raw / 255.0`, and EQ band index
   `2` = LOW/BASS are proven.
8. Band indexes `0` and `1` are not overclaimed.
9. CFX FILTER param0/param1 are proven only as tracking/non-authority data.
10. Filter validation requirements are explicit: vector bounds, selected effect
    id `0`, `unit_channel`, finite values, both-deck readability.
11. Relaunch reacquire and mixer-chain readability after operator-labeled
    master-button actions are supported by samples after PID/base/master
    actions. Raw direct-master byte behavior must come from current code/tests
    or an artifact that actually records those fields, not from mixer JSONL
    labels alone.
12. Local 7.2.11 pointer/value mapping has no remaining known Deck 1/2 gap for
    upfader, LOW/BASS, FILTER, Deck 1 midpoint, relaunch reacquire, or
    mixer-chain readability after operator-labeled master actions.
13. Runtime mixer freshness/invalidation/thresholds/hysteresis are not falsely
    claimed as implemented.

## Review Surface C - Spec And Architecture Fit

Try to disprove that the implementation handoff is safe:

1. It reuses `RBStateReader` / `rb_offsets.py` instead of inventing a second
   reader.
2. It adds named mixer chains, not anonymous trailing chain lines ignored by the
   parser.
3. It avoids reusing `_follow_float()` if that helper still rejects valid mixer
   values like `0.0` or `1023.0`.
4. Missing/unreadable mixer state on either deck invalidates mixer authority for
   both decks.
5. `MASTER_CHANGED` becomes `rb_master_deck` only while mixer authority is valid.
6. `active_deck` is selected only through a pure resolver while mixer authority
   is valid.
7. Raw Rekordbox Deck C/D direct-reader `PLAY`, `PAUSE`, and
   `MASTER_CHANGED` cannot be aliased into Deck 1/2 resolver eligibility or
   `rb_master_deck`.
8. `rb_master_deck` has validity/freshness/source semantics; startup defaults,
   sentinel/no-master, unreadable, unsupported, stale, or OSC fallback inputs
   cannot silently become Deck 1 master truth.
9. Neutral/equal tie and invalid-mixer fallback behavior is defined when
   `rb_master_deck` is unavailable/stale.
10. StateManager reruns/applies the resolver after `PLAY` and `PAUSE` mutate
    playing state, so a paused/non-eligible active deck cannot keep driving until
    an unrelated mixer snapshot.
11. OSC scripted arm/clear fallback cannot enqueue or process deck `0`, and
    `SCRIPTED_ARM`/`SCRIPTED_CLEAR` reject non-1/2 decks before `_deck[0]`
    indexing or `_arm_unscripted(0)`.
12. Playing-only mirror auto-switch and resume-time direct `active_deck`
   correction cannot bypass valid mixer authority.
13. Filter cannot affect `active_deck`.
14. Decks 3/4, crossfader, trim/gain, mid/high EQ, real audio loudness, mute, and
   unrelated FX are still non-authority inputs.
15. Status and heartbeat must expose `active_deck/show_deck`, `rb_master_deck`,
    mixer validity, decoded Deck 1/2 fader/bass, and authority reason.

## Assumption-Fighting Rules

For every claim, label it:

- `confirmed-current-code`
- `confirmed-committed-evidence`
- `confirmed-local-artifact`
- `contradicted`
- `unverified`
- `overclaimed`

Do not accept "the doc says so." Require a code line, evidence-doc line, static
dump symbol/function, or passive sample label.

If a claim depends on `/tmp/rbss_re/*`, state whether the artifact existed and
what exact file was inspected.

## Minimum Commands

Run read-only checks unless impossible:

```bash
git status --short --branch
git rev-parse --short HEAD
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

If implementation code exists by the time of review, also run:

```bash
python3 -m unittest discover tests
```

If a command cannot run, mark it unverified. These commands do not prove live
mixer or hardware behavior.

## Required Output

Return one verdict: `APPROVE`, `REVISE`, or `REJECT`.

Then provide:

1. Findings first, ordered `BLOCKER`, `HIGH`, `MEDIUM`, `LOW`.
2. For each finding: `file:line`, evidence, impact, smallest correction.
3. Requirement-by-requirement audit of Review Surfaces A-C.
4. Explicit list of assumptions you rejected.
5. Explicit list of assumptions still present in the docs/spec.
6. Exact commands run and results.
7. Final implementation-readiness statement:
   - what is ready for local Rekordbox 7.2.11 implementation;
   - what is future-version validation only;
   - what remains runtime implementation work;
   - what must not be claimed as hardware validated.

Keep the review severe. Prefer rejecting an overclaim to approving a vague
statement.
