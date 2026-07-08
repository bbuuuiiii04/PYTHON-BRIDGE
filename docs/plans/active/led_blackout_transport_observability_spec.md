---
doc_status: active-spec
truth_level: implementation-spec, code-grounded (verified at working tree HEAD 63c52e0 + AWR-140 staged, 2026-07-07)
last_verified_commit: 63c52e0
last_verified_date: 2026-07-07
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec — smart-drop blackout transport + runway observability (AWR-142 / RC5)

Contract key: `led_govee` (`led_dispatch_policy.py`). **Observability only — no behavior change.**
This is the diagnostic prerequisite for RC4/RC5's real fix: it makes the live log show which
transport carried each pre-drop blackout and how much runway it had, so a future live session can
prove whether cloud-transport blackouts land late against the ~4-beat pre-drop window.

## Part A — Context & Root Cause (verified; read, do not implement)

- The pre-drop "room blackout" is dispatched by `_dispatch_led_smart_drop_blackout`
  (`led_dispatch_policy.py:550-690`). It forks on the committed drop look's backend: if
  `str(getattr(drop_preview, "backend", "")) == "realtime_razer"` and the adapter exposes
  `tactical_blackout`, it sends via the **realtime** LAN path; otherwise it falls through to the
  **cloud** `pre_drop` `LEDContext` path (`:612-627`) and `_led_send_decision`. [confirmed]
- The two paths log **asymmetrically**: the realtime accept logs
  `[RGB] tactical-blackout-accepted phase=… next_drop=… role_key=… trigger_count=… active_deck=…`
  (`:601-608`), but the cloud accept just sets `self._led_smart_drop_blackout_key` and returns with
  **no accepted log line** (`:677-679`). So a cloud-carried blackout is invisible in the log, and
  neither path records the **runway** (beats remaining to the drop when the blackout was sent).
  [confirmed]
- Why it matters (RC5 finding, 2026-07-07 session): the cloud path has ~1–2 s of command latency
  against a fixed ~4-beat (`led_predark_beats: 4`, ~1.8 s at 130 BPM) pre-dark window, so a
  cloud-carried blackout can land *after* the drop — read live as "blackout didn't fire." The log
  today cannot distinguish "didn't arm" from "armed but landed late on the slow transport." This
  spec closes that blind spot. It does NOT change which transport is chosen or any timing. [confirmed]
- `sp_state` (a `SmartPhrasingState`) is a parameter of `_dispatch_led_smart_drop_blackout` and
  exposes `beats_to_next_drop` and `next_smart_drop_beat` — the runway signal to log. [confirmed —
  `sp_state.beats_to_next_drop` read elsewhere in this module and in `_drop_presentation_tick`]

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `led_dispatch_policy.py` (the `_dispatch_led_smart_drop_blackout` method), Part E docs.
  Do NOT touch the transport-selection logic, `_led_send_decision`, `tactical_blackout`, the WI-1
  clamp, `state_manager.py`, `drop_presentation.py`, or any config.
- **No behavior change.** Do not alter which branch is taken, the order of sends, the return points,
  `_led_smart_drop_blackout_key` assignment, or any masking/gating. The ONLY additions are log lines
  and the values they read. Logging already happens on this path, so no new hot-path I/O class is
  introduced.
- Expected error handling: none added. The values logged (`sp_state.beats_to_next_drop`,
  `next_smart_drop_beat`, the backend string) are already-resolved fields; format them defensively
  with existing helpers/`"-"` fallbacks exactly as the surrounding log lines do. No try/except.
- Do NOT change log level of, or remove, any existing line. Add, don't rewrite.

### Task 1 — `led_dispatch_policy.py`: tag the realtime accept with transport + runway
On the existing realtime accepted log (`:601-608`, `[RGB] tactical-blackout-accepted …`), add two
fields to the SAME line: `transport=realtime` and `runway_beats=<sp_state.beats_to_next_drop>`
(format as `%.1f` when not None, else `-`). Keep every existing field and the message prefix
byte-identical otherwise so existing greps still match.

### Task 2 — `led_dispatch_policy.py`: log the cloud accept (currently silent)
On the cloud path's accepted outcome (`:677-679`, immediately before/after setting
`self._led_smart_drop_blackout_key = blackout_key`), add a new INFO line mirroring the realtime one:
`[RGB] smart-drop-blackout-accepted transport=cloud phase=%s next_drop=%s runway_beats=%s role_key=%s active_deck=%d`
using `next_smart_drop_beat` (or the same `marker`/anchor value the method already computed) for
`next_drop`, `sp_state.beats_to_next_drop` for `runway_beats` (`%.1f` or `-`), and the existing
`blackout_key` / `active` locals. Do not change the return or the key assignment; the log is
additive.

### Task 3 — consistency check (no code)
Confirm by reading that both accepted paths now emit exactly one line carrying `transport=` and
`runway_beats=`, and that the error/rejected paths (`:663-690`) are unchanged. No new test asserts
log text (the repo does not unit-test log strings); correctness here is "no behavior change,"
covered by the existing suite staying green.

## Part C — Invariants That MUST Still Hold (live safety)
- Zero behavior change: identical transport selection, identical sends, identical returns, identical
  `_led_smart_drop_blackout_key` lifecycle. A diff that alters any control-flow line fails this spec.
- No new blocking I/O on the push/dispatch path beyond the existing logging calls; the 200 Hz push
  loop and the dispatch hot path are untouched (AGENTS.md §6).
- Existing log consumers keep working: the `[RGB] tactical-blackout-accepted` prefix and its current
  fields are preserved (fields appended, none removed/reordered before the existing ones).

## Part D — Tests
- No new behavioral test (log-only change). Run the full `led_govee` contract suite + `discover
  tests` to prove nothing regressed at the known ~3-red baseline. If any existing test asserts the
  exact `tactical-blackout-accepted` line text, update it to match the appended fields (do not weaken
  the assertion).

## Part E — Acceptance (definition of done)
- [ ] Tasks 1–2 exact; Task 3 verified by reading. No control-flow change.
- [ ] `python3 -m unittest discover tests` at the known ~3-red baseline; `led_govee` contract suite
      green.
- [ ] Hard checks pass: `check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`.
- [ ] `led_govee` `docs_update`: note the transport/runway observability line in
      `docs/subsystems/led_govee.md`; add an AWR-142 row to `docs/status/active_work_registry.md`
      (implemented / software-tested; HARDWARE-UNVALIDATED); no matrix status upgrade.
- [ ] Status language §10 only.

## When You Finish
Report changed files and the checks run. Operator summary: "The pre-drop room blackout can go out on
two different paths — the fast local one or the slower cloud one. Until now the log only showed the
fast one, so a blackout that went out slow and landed late looked identical to one that never fired.
Now every pre-drop blackout logs which path it took and how many beats of runway it had, so next live
set we can see whether the slow path is landing late. Nothing about the lighting itself changes."
Rollback = remove the added log fields/line. End with the literal line CODEX-RC5-DONE.
