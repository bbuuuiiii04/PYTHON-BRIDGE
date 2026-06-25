---
doc_status: in-progress-run-record
truth_level: operator-evidence-run
last_verified_commit: 3b7469a
last_verified_date: 2026-06-24
validation_scope: one local non-Autoloop SoundSwitch pack run; SOFTWARE/WIRE PREFLIGHT ONLY — energizing run NOT performed (DMX lasers not connected); SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# SoundSwitch Local Hardware Run — pre-staged (software preflight only)

> **State:** the offline software/wire gate below is complete and PASS. The energizing
> run (§4–§7 of the procedure) was **NOT performed**: the DMX lasers were not connected
> at pre-stage time. Every physical/observation row is `PENDING`. This record carries no
> hardware evidence and the repository status stays `HARDWARE-UNVALIDATED`. Resume from
> "Operator setup gate" when the rig is connected with the physical kill in reach.

## Run identity

| Field | Value |
| --- | --- |
| Commit / date / local time zone | `3b7469a1d4e18450a15509983aab9baaf7073f2b` / `2026-06-24` / `<HH:MM TZ — operator>` |
| Operator initials | `<initials — operator>` |
| macOS / Rekordbox / SoundSwitch | `macOS Darwin 24.3.0` / `<RB version — operator>` / `2.10.3` |
| Fixture model categories | `DMX lasers — NOT CONNECTED at pre-stage` |
| Interface category | `<category only — operator>` |
| Redacted live-config SHA-256 | `<operator to fill: sha256:<first12>...>` |
| Physical-kill description | `<operator to fill; no identifier>` |
| Fixture-safe test look | `<operator to fill; no device name>` |

## Offline preflight

| Check | Result | Timestamp / bounded evidence |
| --- | --- | --- |
| HEAD recorded | `PASS` | `3b7469a1d4e18450a15509983aab9baaf7073f2b` |
| Focused tests | `PASS` | 7 named suites — Ran 210, OK |
| Full discovery | `PASS` | Ran 2355, OK (skipped=3, expected failures=1) |
| Current-project proof | `PASS` | `final_verdict: PASS_IMPLEMENTATION_MAY_BEGIN` — 29 PASS / 0 FAIL / 0 INCOMPLETE (foundation 27/27) |
| Hard docs checks / diff check | `PASS` | metadata + agent-contracts + drift passed; staleness all fresh; `git diff --check` range clean |
| Exact bridge count before config edit | `0` | read-only §3 detector — `0` processes (no live bridge) |
| Canonical pack / ignored config present | `PASS` | canonical project present (proof read it read-only and PASSED) |
| Physical fixture map confirmed | `PENDING` | DMX not connected |
| Exclusive Enttec ownership confirmed | `PENDING` | DMX not connected |
| Controller mapping confirmed | `PENDING` | not started |
| Physical kill reachable | `PENDING` | not started |
| Exact bridge count after approved start | `PENDING` | energizing run not performed |
| Status fresh / pack enabled / backend pack | `PENDING` | energizing run not performed |
| Idle fixture darkness | `PENDING` | DMX not connected |

## Per-fixture map

| Fixture label | Logical CH range | Redacted DMX range | Stimulus | Expected | Observed | Pass/fail | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `(none)` | — | — | — | — | `PENDING — no fixtures connected` | `PENDING` | — |

## Required sequence

All rows `PENDING` — energizing run not performed (DMX lasers not connected).

| Step | Operator action | Observed | Pass/fail |
| --- | --- | --- | --- |
| Safe zero | idle baseline | `PENDING` | `PENDING` |
| Static hold | hold known Static Look | `PENDING` | `PENDING` |
| Static release | release Static Look | `PENDING` | `PENDING` |
| Scripted play | play one known scripted track | `PENDING` | `PENDING` |
| Healthy blackout | hold controller blackout | `PENDING` | `PENDING` |
| Blackout release | release blackout | `PENDING` | `PENDING` |
| Degraded overlay release | pre-agreed controller degradation while Static held | `PENDING` | `PENDING` |
| Scripted stop | stop Rekordbox transport | `PENDING` | `PENDING` |
| Physical emergency kill | engage physical kill on low-risk non-zero look | `PENDING` | `PENDING` |
| Graceful stop zero | keep kill engaged, stop bridge gracefully | `PENDING` | `PENDING` |
| Default-off closeout | with kill engaged, restore default-off config | `PENDING` | `PENDING` |
| Known-dark reset | reset/power-cycle Enttec/DMX if zero failed/unknown | `PENDING` | `PENDING` |
| Physical-path restore | restore only after known-dark proof | `PENDING` | `PENDING` |

## Sanitized watchpoints

`PENDING` — no energizing run; nothing observed.

## Closeout

| Field | Result |
| --- | --- |
| Ignored config restored to default-off | `N/A — never changed from default-off` |
| Final exact bridge count | `0 (stopped — never started for a live run)` |
| Final fixture darkness | `N/A — no fixtures connected` |
| Physical path / kill state | `N/A — DMX not connected` |
| Rollback/restore result | `N/A — no live changes made` |
| Deviations | `Energizing run not attempted: DMX lasers not connected` |
| Remaining unknowns | `Entire hardware run §4–§7: physical output, serial send success, Enttec acceptance, fixture darkness, emergency kill, known-dark restore` |
| Verdict | `INCOMPLETE` |

`PASS_LOCAL_SETUP` is **not** earned. The software/wire gate passed; no hardware was exercised.
Repository status remains `SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED`.
