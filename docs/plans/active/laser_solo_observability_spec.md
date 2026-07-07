---
doc_status: current
truth_level: code-verified
last_verified_commit: d5cdcd4
last_verified_date: 2026-07-06
validation_scope: Codex implementation spec for laser-solo and pad-arrival observability logging; software tests only; no lighting behavior change
---

# Codex Implementation Spec - Laser Solo observability (logging only)

> You are an autonomous senior engineer: proactively gather context, plan, implement, test, and refine without waiting for additional prompts. Persist end-to-end within the turn. Bias to action.

> You may be in a dirty git worktree. NEVER revert existing changes you did not make. If you notice unexpected changes you didn't make, STOP and ask how to proceed. NEVER use destructive commands like `git reset --hard` or `git checkout --`.

## Part A - Context & Root Cause (verified; read, do not implement)

Live-run problem (operator, 2026-07-06 evening set, ~20:18): a laser-solo action left no trace — `grep -c "solo"` over the whole session log = 0 of 12,639 lines. The bridge acted on every pad tap sub-millisecond (log-verified), so the perceived "pad delay" is upstream of the bridge (Stream Deck process / CoreMIDI hop), which the bridge cannot observe. This spec adds observability only; zero lighting-behavior change.

**[confirmed]** at HEAD d5cdcd4:
- `Ev.LASER_SOLO_PAD` (`models.py:281`) routes `soundswitch_midi_input.py:384` `_emit_pad_event(binding, phase="down")` → dispatch at `state_manager.py:1583-1584` `_drop_presentation_solo_pad_pressed()` → arm/disarm/veto (`state_manager.py:2729-2768`) — no log call anywhere on this path. Sibling laser events (`LASER_TOGGLE` etc., `state_manager.py:1598-1609`) use `bridge_log.perf("override", msg, *args, data={...})`.
- `_drop_presentation_update_solo_feedback` (`state_manager.py:2716-2727`) is the single edge-triggered choke point: every solo transition (off/armed/active) passes its `if state != self._drop_presentation_solo_feedback:` block (`:2724`).
- The veto branch (`state_manager.py:2750-2765`) silently un-arms a non-manual pending solo and may also un-learn a learned solo — a materially different action worth its own line; it can run WITHOUT changing feedback state (`last_pending[0]` stays `LASERS_ONLY` until the next presentation tick), so the choke-point line alone would miss it.
- Generic pad kinds (`palette_pad`, `laser_solo_pad`, `zone_pad`, …) all ride `_emit_pad_event` (`soundswitch_midi_input.py:307-310, 384`) with no arrival breadcrumb, while dedicated branches (blackout, static) have `log.debug` lines (`:274-305`). One debug line in the shared function covers every pad kind's arrival.
- Separate over-redaction bug **[confirmed]**: `_redact` (`bridge_log.py:41-54`) masks any dict key whose lowercased name merely CONTAINS `"key"`, so structural fields like `role_key` log as `<redacted>` — this blinded tonight's incident analysis (the LED role marker was unreadable). Real secret posture (e.g. `GOVEE_API_KEY`) must not weaken.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Touch only: `soundswitch_midi_input.py`, `state_manager.py`, `bridge_log.py` (Task 4 only), tests under `tests/`, Part E docs.
- Zero behavior change: no lighting, arming, veto, learned-store, or feedback logic may change; logging lines only. Do not add MIDI-receipt latency stamps or any new event payload fields.
- Logging discipline: pad-arrival breadcrumb at DEBUG (matches `[SS-MIDI]` siblings); solo state transitions and vetoes at the `bridge_log.perf` level used by `LASER_TOGGLE` (edge-triggered outcomes, human-tap frequency — no per-tick spam). No blocking I/O added to the 200 Hz path (`bridge_log.perf` is the established hot-path-safe helper; use it exactly as the sibling does).

### Task 1 - `soundswitch_midi_input.py`: pad-arrival breadcrumb
In `_emit_pad_event` (definition near `:384`'s caller — locate the function body), add one line at entry:
```python
log.debug("[SS-MIDI] pad event kind=%s phase=%s", binding.kind, phase)
```
Match the exact attribute names used in the function (verify `binding.kind` is correct there; if the field differs, use the actual one).

### Task 2 - `state_manager.py`: solo feedback transition line
In `_drop_presentation_update_solo_feedback`, inside the existing `if state != self._drop_presentation_solo_feedback:` block (`:2724-2727`), capture `prev = self._drop_presentation_solo_feedback` before the assignment and emit:
```python
bridge_log.perf(
    "override",
    "laser solo %s (was %s)",
    state,
    prev,
    data={
        "surface": "laser",
        "action": "solo_feedback",
        "state": state,
        "prev": prev,
        "pending_reason": self._drop_presentation_last_pending[1] or "",
        "armed_manual": self._drop_presentation_armed_key is not None,
    },
)
```

### Task 3 - `state_manager.py`: veto line
In `_drop_presentation_solo_pad_pressed`'s veto branch (`:2750-2765`), after the un-learn attempt (so the outcome is known), emit:
```python
bridge_log.perf(
    "override",
    "laser solo veto (%s)",
    pending_reason,
    data={
        "surface": "laser",
        "action": "solo_veto",
        "pending_reason": pending_reason,
        "pending_beat": pending_beat,
        "unlearned": unlearned,
    },
)
```
where `unlearned` is True only when the `solo_learned` removal actually removed an entry (capture the existing `remove(...)` return; do not call it twice).

### Task 4 - `bridge_log.py`: stop redacting structural `*_key` fields (fail closed)
In `_redact` (`:41-54`), add an exact-name allowlist checked BEFORE the substring match — a module constant like:
```python
_REDACT_ALLOWED_KEYS = frozenset({"role_key", "track_key", "armed_key", "section_key", "cache_key"})
```
and in the loop: `if key_l in _REDACT_ALLOWED_KEYS: redacted[key] = _redact(item); continue` ahead of the token/secret/password/key substring check. First grep every `data=` call site (`bridge_log.perf`/`emit` callers) for field names containing `key` and put each confirmed-structural one in the allowlist; anything not explicitly allowlisted stays masked (deny by default — the secret-masking posture must not weaken). Do not change the token/secret/password behavior.

## Part C - Invariants That MUST Still Hold (live safety)

- Zero behavior change to drop presentation: a Laser Solo is never a dice roll; suppression is not blackout; scripted tracks get zero policy activity; learned-store writes stay on the background writer thread (Task 3 only reads the existing return value).
- 200 Hz push loop gains no blocking I/O.
- No per-tick log lines — all three emits are edge/tap-triggered only.

## Part D - Tests

Extend `tests/test_drop_presentation` (or the existing state-manager drop-presentation tests — grep for `_drop_presentation_solo_pad_pressed` usage) minimally:
1. Solo arm then disarm produces exactly two feedback transition emits (off→armed, armed→off) — assert via the repo's established log-capture pattern (`assertLogs` or the bridge_log test helper other perf tests use; follow prior art).
2. Veto of a pending `solo_learned` emits one veto line with `unlearned=True` and does not change arming behavior vs. today (existing veto assertions still pass unchanged).
3. No emit when feedback state does not change.
4. `_redact`: allowlisted names (`role_key`, …) pass through untouched including nested dicts; `api_key`, `token`, `secret`, `password`, and an unknown `foo_key` still mask; extend the existing redaction tests (grep `tests/` for `_redact` / redaction coverage — likely `tests.test_bridge_log`).
Run `python3 -m unittest tests.test_drop_presentation tests.test_soundswitch_midi_input tests.test_bridge_log`, then `python3 -m unittest discover tests`. Known pre-existing full-suite failures at this HEAD, NOT yours to fix and NOT acceptable to worsen: `tests.test_led_color_engine_m2_patch_d` (live-config dependent) and `tests.test_export_pack_parity_self_heal` (fixture-dependent).

## Part E - Acceptance (definition of done)

- [ ] Tasks 1-4 landed; behavior diffs limited to log lines and redaction of non-secret structural names.
- [ ] Task 4 rides the `logging_visibility` contract: also update `docs/subsystems/logging.md` if it describes redaction behavior.
- [ ] Full suite green: `python3 -m unittest discover tests`.
- [ ] Hard checks green: `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`.
- [ ] Docs: update `docs/subsystems/logging.md` only if it catalogs individual emit lines (inspect first); update `docs/architecture/drop_presentation_authority.md`'s observability notes if it has any; register this spec in `docs/status/active_work_registry.md`. Inspect the remaining `drop_presentation` contract docs (`docs/subsystems/led_govee.md`, `docs/subsystems/laser.md`, `docs/plans/active/streamdeck_palette_control_design_spec.md`) and update only if their described behavior changed (it should not — logging only); report which you checked and left unchanged.
- [ ] Do not commit; leave changes in the worktree for review.

## When You Finish

Report: changed files, test/check commands with pass counts. Plain-language operator summary: laser solo now leaves a visible trail — one line when it arms/activates/clears (saying whether it was your press or an automatic tier) and one line when a press vetoes an automatic solo; every pad tap now leaves a debug breadcrumb the moment the bridge receives it, so next time "the pads feel late" the log can prove whether the tap even reached the bridge; the log also stops blanking harmless bookkeeping fields whose names merely contain "key" (real secrets stay masked); nothing about how solo behaves changed.
