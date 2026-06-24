---
doc_status: active-spec
truth_level: code-grounded-design-spec
last_verified_commit: ab4d293
last_verified_date: 2026-06-24
validation_scope: RW-5 sanitized copied-state status and menubar visibility only; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no restart, config, output, device, or hardware action authorized
---

# Codex Implementation Spec - RW-5 Operational Status and Menubar Visibility

## Part A - Context & root cause (verified; read, do not implement)

- [confirmed] `PackRuntime.sanitized_status()` currently calls `backend.status()` and exposes only
  availability, enablement, backend, pack load/hash, frame count, accepted-identity presence, and a
  reason (`soundswitch_pack_runtime.py:35-58`). It cannot describe the frame decision the pack
  driver just made.
- [confirmed] `StateManager.get_pack_status()` delegates directly to that runtime method
  (`state_manager.py:3271-3274`). The status writer invokes it every 0.5 seconds and writes the
  result under `soundswitch_pack` (`runtime_status.py:92-99`, `runtime_status.py:123-139`).
- [confirmed] The driver already has every minimum RW-5 decision in one tick: runtime active,
  controller degradation, held static, held blackout, scripted transport, bridge lighting mode,
  and final rendered frame (`state_manager.py:3283-3426`). No second authority source is needed.
- [confirmed] RW-4 intentionally allows `input_degraded=true` and `scripted_active=true` at the same
  time: degradation drops the manual overlay only (`state_manager.py:3293-3345`). A single enum
  cannot represent that truth without companion booleans.
- [confirmed] Native Autoloop DMX is intentionally absent. The driver selects scripted output or
  clears the base and submits one frame; it never calls `select_autoloop`
  (`state_manager.py:3389-3419`). Reporting `autoloop_phase_blocked` is status only.
- [confirmed] The menubar already reads a copied JSON file, marks it stale after three seconds, and
  never reaches into bridge runtime objects (`scripts/bridge_menubar.py:275-285`). It has an export
  action plus one disabled export-status row (`scripts/bridge_menubar.py:625-630`), with only a
  coarse `Exporting…` button state and terminal result text (`scripts/bridge_menubar.py:375-390`,
  `scripts/bridge_menubar.py:786-792`).
- [assumed] Operator-facing wording should stay one concise row. No new submenu or dashboard is
  needed to meet the kickoff.

**Root cause [confirmed].** Operational truth is computed in `_drive_pack_output` but discarded
after frame submission. The later status surface re-queries a backend object that does not know
scripted/controller/mask decisions. Capture a sanitized immutable dict at the decision point and
have every surface copy it.

## Part B - Tasks (implement exactly, in order)

### Absolute rules

- Touch only `soundswitch_pack_runtime.py`, `state_manager.py`, `runtime_status.py`,
  `scripts/bridge_menubar.py`, the corresponding focused tests, and contract-required docs.
- Do not add a status thread, lock, queue, timer, provider call, filesystem read, subprocess, MIDI
  call, serial call, or worker-status poll to `_push_tick` / `_drive_pack_output`.
- Do not expose paths, ports, aliases, device/fixture names, IDs, raw frames, frame hashes, UUIDs,
  elapsed position, or raw error text.
- Do not add pack enable/backend/restart controls to the menubar. Export still sends only the
  existing `set_soundswitch_pack reload` command under its existing conservative gate.
- Do not wire `select_autoloop`, phase math, origin selection, holdout logic, or T7d capture state.
- Do not add `sender_degraded` in RW-5. Current sender health is not a copied pack-decision field;
  instrument it only in a later spec if a concrete operator need justifies worker changes.

### Task 1 - `soundswitch_pack_runtime.py`: make base status provider-free

Change `PackRuntime.sanitized_status()` so it never calls `backend.status()` or any other object
method. It returns only immutable bundle facts:

```python
{
    "available": self.player is not None or self.backend is not None,
    "enabled": bool(self.enabled),
    "backend": "pack" if self.active else "disabled",
    "pack_loaded": self.player is not None,
    "pack_sha12": self.pack_sha12 or "",
    "reason": self.reason,
}
```

Keep `reason` constrained to the existing sanitized categories. `frame_count`,
`has_active_identity`, and operational fields move to the StateManager-owned copied snapshot.

### Task 2 - `state_manager.py`: publish one bounded operational snapshot

Add one module-level pure helper:

```python
def _pack_operational_state(*, enabled, blackout, input_degraded, static_held,
                            scripted_active, autoloop_phase_blocked, zero_safe) -> str:
```

Return the first true state in this precedence:

```text
disabled -> blackout -> input_degraded -> static_held -> scripted_active
-> autoloop_phase_blocked -> zero_safe
```

The fallback is `zero_safe`; no free-form value is allowed.

In `StateManager.__init__`, initialize `_pack_status_snapshot` from the current immutable runtime
plus these bounded fields:

```text
operational_state: disabled|blackout|input_degraded|static_held|scripted_active|
                   autoloop_phase_blocked|zero_safe
scripted_active: bool
input_degraded: bool
static_held: bool
blackout: bool
autoloop_phase_blocked: bool
zero_safe: bool
frame_count: non-negative int
has_active_identity: bool
```

Requirements:

- Build a fresh dict, then publish it with one attribute assignment. Never mutate the published dict.
- `get_pack_status()` returns `dict(self._pack_status_snapshot)` only. It must not call the runtime,
  player, input, backend, sender, or any provider.
- `set_pack_runtime()` preserves its atomic runtime assignment and RW-4 static-slot reset, then
  publishes a disabled/initial snapshot from `runtime.sanitized_status()`. It performs no I/O.
- In `_drive_pack_output()`, reuse the already-computed `input_healthy`, `slot`, `blackout`,
  `transport`, current `self._os.lighting_mode`, and rendered frame. Render once into a local,
  publish the copied status, then submit that same frame.
- `scripted_active = transport is not None`.
- `input_degraded = midi_input is not None and not input_healthy`.
- `static_held = slot is not None`; `blackout = bool(blackout)`.
- `autoloop_phase_blocked = rt.active and self._os.lighting_mode == "autoloop"`; this is an honest
  status flag only and does not select output.
- `zero_safe = frame == _PACK_ZERO_FRAME`.
- Increment one StateManager-owned frame counter for each attempted normal frame submission. Preserve
  it across ordinary ticks; reset it when a new runtime bundle is published.
- Derive `has_active_identity` only from the in-memory `backend.last_accepted_identity` property if
  present; never call `backend.status()`.
- On the existing outer exception path, publish a bounded `zero_safe` snapshot with all activity/
  overlay flags false before attempting the existing zero submit. Do not include the exception.

The booleans are authoritative; `operational_state` is only the concise display priority. Thus a
degraded controller can truthfully report both `input_degraded=true` and
`scripted_active=true`, while the row reads `Input degraded`.

### Task 3 - `runtime_status.py`: extend the copied default only

Add the exact bounded operational keys to `_DEFAULT_PACK_STATUS` with disabled-safe values. Keep
`StatusWriter` on `sm.get_pack_status`; do not add another provider or call any pack object from the
writer. Schema version remains `1` because this is an additive nested-object change.

### Task 4 - `scripts/bridge_menubar.py`: one pack/export row and two export phases

Reuse `export_status_item`; do not add menu rows. Add a pure function that accepts only the copied
`soundswitch_pack` dict plus export UI state and returns one bounded line. Allowlist labels:

| `operational_state` | Label |
| --- | --- |
| `disabled` | `Disabled` |
| `blackout` | `Blackout` |
| `input_degraded` | `Input degraded` |
| `static_held` | `Static held` |
| `scripted_active` | `Scripted active` |
| `autoloop_phase_blocked` | `Autoloop blocked` |
| `zero_safe` | `Zero` |
| anything else | `Unknown` |

Render `Pack: <label> · <export label>` using only allowlisted export labels:

- `Ready to export`
- `Exported`
- `Exporting…`
- `Reloading…`
- `Saved; pack disabled`
- `Live now`
- `Saved; reload unconfirmed`
- `Export failed (<sanitized category>)`

Keep the existing export button titles and conservative reload acknowledgement unchanged. Add one
coarse `_export_phase` (`idle`, `exporting`, `reloading`) and marshal the transition to `reloading`
onto the AppKit main thread after publication succeeds and before reload precheck/polling. This is
progress visibility, not a new exporter protocol. Terminal completion returns the phase to `idle`.

When the whole status file is stale, render `Pack: Unknown`; never display an old active state as
current. Cap the complete row at 80 characters after sanitization.

### Task 5 - Contract docs

Update the status description in `docs/subsystems/soundswitch_output.md`,
`docs/subsystems/runtime_commands.md`, `docs/setup/runtime_commands.md`, and the relevant status/
validation docs required by `soundswitch_pack_player` in `docs/agents/change_contracts.yml:233-309`.
Do not close hardware validation or native Autoloop DMX.

## Part C - Invariants that MUST still hold (live safety)

- The push loop does no new blocking work or I/O. Its only RW-5 write is a fresh-dict attribute
  assignment; the status reader copies that dict.
- One rendered frame feeds both status classification and the existing single backend submission.
  Status must never rerender or change output.
- RW-1 export/reload safety, RW-1A shutdown zero, RW-2 pause hold, RW-3 scripted authority, RW-4
  overlay degradation latch/Option B runtime swap, and manual Static Override precedence remain
  unchanged.
- `input_degraded` means the overlay is distrusted; it does not imply the scripted base is dark.
- `blackout` is healthy held pack blackout. Malformed input/status failures remain zero-safe.
- `autoloop_phase_blocked` is informational. Native Autoloop DMX remains safe-zero.
- Existing OS2L, lasers, LEDs/Govee, Rekordbox readers, and bridge commands are untouched.
- Menubar reads only `/tmp/rb_ss_bridge_v2_status.json`; it never imports bridge runtime objects.

## Part D - Tests

### Pure state resolver

Add table-driven tests for every precedence row and for the simultaneous
`input_degraded=true, scripted_active=true` case.

### StateManager/status tests

Extend `tests/test_state_manager_pack_driver.py` to prove:

- disabled runtime -> `disabled`, `zero_safe=true`;
- scripted frame -> `scripted_active`, non-zero;
- degraded input with a valid scripted base -> `input_degraded=true`,
  `scripted_active=true`, non-zero;
- healthy static -> `static_held`; healthy blackout -> `blackout`, zero;
- bridge `lighting_mode="autoloop"` without scripted ownership ->
  `autoloop_phase_blocked`, zero, and `select_autoloop` not called;
- driver exception -> copied `zero_safe`, sanitized, and zero submit attempted;
- `get_pack_status()` does not call backend/input/player/sender methods and returns a copy.

Replace the leaky-backend expectations in `tests/test_soundswitch_pack_commands.py`: use a backend
whose `status()` raises `AssertionError`, prove `PackRuntime.sanitized_status()` does not call it,
and prove the output contains none of `_FORBIDDEN`.

### Menubar tests

Extend `tests/test_bridge_menubar.py` with a pure truth table for all pack labels, stale/unknown,
all export labels, error sanitization, and the 80-character bound. Prove the background worker
marshals `exporting -> reloading -> idle` without changing the exact reload command or its existing
freshness gates.

### Gates

```bash
python3 -m unittest \
  tests.test_state_manager_pack_driver \
  tests.test_soundswitch_pack_commands \
  tests.test_runtime_status \
  tests.test_bridge_menubar
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

No test may open AppKit UI, MIDI, serial, Enttec, DMX, or hardware.

## Part E - Acceptance

- [ ] `get_pack_status()` returns copied state and calls no provider/runtime component.
- [ ] Status distinguishes `scripted_active`, `input_degraded`, `static_held`, `blackout`,
      `autoloop_phase_blocked`, `disabled`, and `zero_safe` with bounded booleans plus one enum.
- [ ] Simultaneous degraded-input/scripted-active truth is preserved.
- [ ] The menubar shows one concise pack/export row plus `Exporting…` and `Reloading…` phases.
- [ ] No private identifier, raw frame/hash/error, path, port, alias, or device/fixture name appears.
- [ ] Export/reload commands and all output behavior are unchanged.
- [ ] `select_autoloop` remains uncalled; no T7d/native-Autoloop work entered the diff.
- [ ] Focused and full tests pass; hard docs checks pass; staleness is reviewed; diff is clean.
- [ ] Status remains SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED.

## Pre-handoff checklist

1. All claims are labeled; `sender_degraded` is explicitly deferred rather than guessed.
2. File/line claims were checked at `ab4d293`.
3. Same-tick overlay/base combinations use booleans plus a display-priority enum.
4. Disabled, swap, normal, Autoloop-blocked, exception, and stale-UI transitions are covered.
5. Existing status/export methods and exact reload command are reused.
6. StateManager's existing authority variables remain the source; no duplicate owner is introduced.
7. `_pack_operational_state` and menubar formatting are pure test seams.
8. Hot-path purity, process safety, output neutrality, and hardware boundaries are explicit.
9. Adversarial case: RW-4 degradation while scripted output continues must not be mislabeled zero;
   companion booleans plus frame-derived `zero_safe` prevent that false claim.

## When you finish

Report changed files, the exact schema, transition tests, full/focused test counts, docs gates, and
the plain-language operator result: what the row now says, what output behavior stayed unchanged,
what healthy/degraded states look like, and that no restart or hardware validation occurred.
