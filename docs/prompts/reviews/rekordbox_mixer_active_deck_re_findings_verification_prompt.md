---
doc_status: active-review-prompt
truth_level: review-verification-instructions
last_verified_commit: 55e7b7c
last_verified_date: 2026-06-29
validation_scope: independent read-only verification of Codex implementation-precision findings for Rekordbox mixer active-deck authority spec
---

# Verify Codex Findings - Rekordbox Mixer Active-Deck Authority

You are an independent reviewer. Verify or refute the Codex findings below.
Do not implement fixes. Do not edit files. Do not commit. Do not restart the
bridge. Do not sample live process memory. Do not touch hardware, MIDI, serial,
DMX, Enttec, Govee, SoundSwitch, lasers, LEDs, or other live outputs.

Repository: `/Users/bbui/rb_ss_bridge_v2`
GitHub repository: `bbuuuiiii04/PYTHON-BRIDGE`
Branch: `main`

## Source Order

Use current repo evidence only:

1. Executable code and tests.
2. Runtime/status/config surfaces.
3. Architecture docs.
4. Committed RE evidence docs.
5. Old prompts/history only as context.

Code beats docs. Current files beat old prompt text.

## Required Reads

- `AGENTS.md`
- `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md`
- `docs/architecture/active_deck_authority.md`
- `docs/research/rekordbox_mixer_active_deck_re_evidence.md`
- `models.py`
- `rb_offsets.py`
- `rb_state_reader.py`
- `state_manager.py`
- `__main__.py` if the caller asks for `main.py` because this repo has no `main.py`
- `runtime_status.py`
- `mtc_reader.py`
- `sound_switch_engine.py`
- relevant tests under `tests/`

## Task

For each finding below, answer one of:

- `CONFIRMED`
- `PARTIALLY CONFIRMED`
- `REFUTED`
- `UNCLEAR`

For each answer, include concise file/line evidence and a short reason. If
refuted, explain exactly what current spec wording or tests already prevent the
risk.

## Findings To Verify

### 1. HIGH - Deck 3/4 direct-reader inputs may leak into Deck 1/2 authority

Claim: The architecture limits active-deck authority candidates to Deck 1/2, and
the implementation spec says mixer reads decode only Deck 1/2. But it also
requires routing `Ev.PLAY`, `Ev.PAUSE`, and direct `Ev.MASTER_CHANGED` from the
same `RBStateReader`. Current `RBStateReader` maps Rekordbox A/C to bridge deck
1 and B/D to bridge deck 2, loops all four Rekordbox decks, and emits
`MASTER_CHANGED` for any raw master byte in range. A literal implementation
could add Deck 1/2 mixer snapshots while leaving Deck 3/4 direct transport or
master state able to affect Deck 1/2 resolver inputs.

Verify whether the spec needs an explicit requirement and tests proving raw
Rekordbox deck indexes 2/3 cannot update Deck 1/2 eligibility or
`rb_master_deck` under mixer authority.

### 2. HIGH - `rb_master_deck` lacks current-valid/fresh semantics

Claim: The spec requires resolver input `rb_master_deck` as `1 or 2` and adds
`OutputState.rb_master_deck: int = 1`, while also saying direct readiness must
be currently true. This can let default Deck 1 act as Rekordbox master truth in
neutral/equal ties or invalid fallback when no current direct master has been
read, the direct master byte is unsupported/unreadable, or the value is stale.

Verify whether the spec needs `rb_master_deck_valid`, `rb_master_deck_source`,
and freshness/updated-at semantics, or an allowed `None` value, plus tests for
neutral ties and invalid fallback when direct master is unavailable/stale.

### 3. HIGH - Deck-0 OSC `SCRIPTED_ARM` path is not covered

Claim: The spec covers `active_deck=0`, `MTCReader`, `RB_RESTARTED`, pending
scripted arm phase 2, and deck-route hazards. But current OSC `/bridge/track_loaded`
falls back to `state_manager.get_active_deck()` when no last-loaded deck exists,
then enqueues `Ev.SCRIPTED_ARM` with that deck. If `active_deck=0`, StateManager
can index `self._deck[0]` while handling `SCRIPTED_ARM` before any phase-2 guard
matters.

Verify whether the spec needs an explicit requirement and test that OSC
scripted-arm input is rejected/deferred when both `last_loaded_deck` and
`active_deck` are invalid, and that StateManager ignores/rejects
`SCRIPTED_ARM`/`SCRIPTED_CLEAR` for non-1/2 decks.

### 4. MEDIUM - PLAY/PAUSE resolver reruns are under-specified in StateManager

Claim: The spec says in startup wiring that the resolver must rerun when mixer
state, play/pause state, or `rb_master_deck` changes. But the StateManager task
and integration tests focus on `Ev.MIXER_STATE` and `Ev.MASTER_CHANGED`; they do
not clearly require `PLAY`/`PAUSE` event handling itself to rerun/apply the
resolver. A literal implementation could leave a paused active deck driving
until the next mixer snapshot or another event.

Verify whether Task 5 and the StateManager integration tests need explicit
requirements for active `PAUSE` causing idle/switch through the resolver, and
non-active `PLAY` becoming eligible only through resolver/stability.

## Output Format

Return:

1. Severity-first verification results.
2. Any additional implementation-precision gaps you found, only if grounded in
   current file/line evidence.
3. Rejected/refuted concerns.
4. Final verdict:
   - `FINDINGS CONFIRMED`
   - `FINDINGS PARTIALLY CONFIRMED`
   - `FINDINGS REFUTED`
   - `SPEC NOT READY`
   - `SPEC READY WITH MINOR EDITS`
   - `SPEC READY`

Keep the review read-only and evidence-grounded.
