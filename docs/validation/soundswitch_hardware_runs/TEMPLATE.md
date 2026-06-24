---
doc_status: template
truth_level: operator-evidence-template
last_verified_commit: 4138c61
last_verified_date: 2026-06-24
validation_scope: one local non-Autoloop SoundSwitch pack hardware run; no result until copied and completed
---

# SoundSwitch Local Hardware Run

Copy to `docs/validation/soundswitch_hardware_runs/YYYY-MM-DD_<sha7>_<short-slug>.md`.
Do not paste raw status/config files, paths, ports, aliases, device names, fixture serials, project
UUIDs, secrets, raw frames/hashes, or raw exceptions.

## Run identity

| Field | Value |
| --- | --- |
| Commit / date / local time zone | `<sha40>` / `YYYY-MM-DD` / `HH:MM TZ` |
| Operator initials | `<initials>` |
| macOS / Rekordbox / SoundSwitch | `<versions>` |
| Fixture model categories | `<category only>` |
| Interface category | `<category only>` |
| Redacted live-config SHA-256 | `sha256:<first12>...` |
| Physical-kill description | `<useful generic description; no identifier>` |
| Fixture-safe test look | `<bounded description; no device name>` |

## Offline preflight

| Check | Result | Timestamp / bounded evidence |
| --- | --- | --- |
| HEAD recorded | `PASS` / `FAIL` | `<sha40>; HH:MM:SS` |
| Focused tests | `PASS` / `FAIL` | `<count/summary>` |
| Current-project proof | `PASS` / `FAIL` / `INCOMPLETE` | `<verdict and counts only>` |
| Hard docs checks / diff check | `PASS` / `FAIL` | `<summary>` |
| Exact bridge count before config edit | `<integer; require 0>` | `<HH:MM:SS>` |
| Canonical pack / ignored config present | `PASS` / `FAIL` | `<presence only>` |
| Physical fixture map confirmed | `PASS` / `FAIL` | `<operator observation>` |
| Exclusive Enttec ownership confirmed | `PASS` / `FAIL` | `<operator observation>` |
| Controller mapping confirmed | `PASS` / `FAIL` | `<operator observation>` |
| Physical kill reachable | `PASS` / `FAIL` | `<operator observation>` |
| Exact bridge count after approved start | `<integer; require 1>` | `<HH:MM:SS>` |
| Status fresh / pack enabled / backend pack | `PASS` / `FAIL` | `<bounded fields only>` |
| Idle fixture darkness | `PASS` / `FAIL` | `<operator observation>` |

## Per-fixture map

| Fixture label | Logical CH range | Redacted DMX range | Stimulus | Expected | Observed | Pass/fail | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `F1` | `<CH range>` | `<redacted range>` | `<safe stimulus>` | `<expected>` | `<operator observation>` | `<PASS/FAIL>` | `<timestamp/category>` |

## Required sequence

| Step | Operator action | Expected direct-DMX result | Expected unchanged behavior | Observed | Pass/fail | Timestamp/evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Safe zero | `OPERATOR OBSERVATION — idle baseline` | Software zero and physically dark | OS2L, lasers, LEDs/Govee, and readers unchanged | `<observation>` | `<PASS/FAIL>` | `<HH:MM:SS>` |
| Static hold | `OPERATOR ACTION — hold known Static Look` | Known low-risk static look appears | Scripted base/other subsystems unchanged | `<observation>` | `<PASS/FAIL>` | `<HH:MM:SS>` |
| Static release | `OPERATOR ACTION — release Static Look` | Manual overlay releases | Other subsystems unchanged | `<observation>` | `<PASS/FAIL>` | `<HH:MM:SS>` |
| Scripted play | `OPERATOR ACTION — play one known scripted track` | Scripted direct-DMX frame follows track | OS2L continues; lasers/LEDs/readers unchanged | `<observation>` | `<PASS/FAIL>` | `<HH:MM:SS + OS2L deltas>` |
| Healthy blackout | `OPERATOR ACTION — hold controller blackout` | Pack frame software-zero; fixtures dark by observation | Other subsystems unchanged | `<observation>` | `<PASS/FAIL>` | `<HH:MM:SS>` |
| Blackout release | `OPERATOR ACTION — release blackout` | Prior eligible base returns | Other subsystems unchanged | `<observation>` | `<PASS/FAIL>` | `<HH:MM:SS>` |
| Degraded overlay release | `OPERATOR ACTION — pre-agreed controller degradation while Static is held` | Static overlay releases; scripted base continues | OS2L, lasers, LEDs/Govee, readers unchanged | `<observation>` | `<PASS/FAIL>` | `<HH:MM:SS>` |
| Scripted stop | `OPERATOR ACTION — stop Rekordbox transport` | Scripted base resolves software-zero after existing stop behavior | Other subsystems unchanged | `<observation>` | `<PASS/FAIL>` | `<HH:MM:SS + OS2L deltas>` |
| Physical emergency kill | `OPERATOR ACTION — engage physical kill on low-risk non-zero look` | All affected fixtures physically dark | Status is not used as physical proof | `<observation>` | `<PASS/FAIL>` | `<HH:MM:SS>` |
| Graceful stop zero | `OPERATOR ACTION — keep kill engaged and stop bridge gracefully` | Sender attempts zero before close | No claim that Enttec accepted zero | `<observation>` | `<PASS/FAIL/UNKNOWN>` | `<HH:MM:SS>` |
| Default-off closeout | `OPERATOR ACTION — with kill engaged, restore default-off config` | Pack output disabled | Existing OS2L/laser/LED/reader defaults unchanged | `<observation>` | `<PASS/FAIL>` | `<HH:MM:SS>` |
| Known-dark reset | `OPERATOR ACTION — reset/power-cycle Enttec/DMX path if zero is failed/unknown` | Operator-confirmed known-dark baseline | Physical kill stays engaged | `<observation>` | `<PASS/FAIL/INCOMPLETE>` | `<HH:MM:SS>` |
| Physical-path restore | `OPERATOR APPROVAL + ACTION — restore only after known-dark proof` | Physical path returns without stale output | Bridge remains default-off unless separately approved | `<observation>` | `<PASS/FAIL/INCOMPLETE>` | `<HH:MM:SS>` |

## Sanitized watchpoints

| Watchpoint | Before | After | Interpretation |
| --- | --- | --- | --- |
| Menubar pack/export line | `<allowlisted text>` | `<allowlisted text>` | `<software state only>` |
| Software `frame_count` | `<integer>` | `<integer>` | `<attempted frames, not confirmed serial sends>` |
| OS2L connected | `<true/false>` | `<true/false>` | `<no endpoint>` |
| OS2L sent delta | `<integer>` | `<integer>` | `<bounded delta>` |
| OS2L send-error delta | `<integer>` | `<integer>` | `<bounded delta>` |
| OS2L drop delta | `<integer>` | `<integer>` | `<bounded delta>` |
| Bridge log category | `<category>` | `<category>` | `<no raw exception>` |
| Lasers | `<bounded observation>` | `<bounded observation>` | `<unchanged/variance>` |
| LEDs/Govee | `<bounded observation>` | `<bounded observation>` | `<unchanged/variance>` |
| Rekordbox reader state | `<bounded state>` | `<bounded state>` | `<status is not room transport proof>` |
| Controller holds physically released | `<operator observation>` | `<operator observation>` | `<not status-derived>` |
| Fixture darkness | `<operator observation>` | `<operator observation>` | `<not status-derived>` |
| Enttec/DMX known-dark baseline | `<operator observation>` | `<operator observation>` | `<not status-derived>` |

## Closeout

| Field | Result |
| --- | --- |
| Ignored config restored to default-off | `<PASS/FAIL>` |
| Final exact bridge count | `<integer and intended stopped/running state>` |
| Final fixture darkness | `<operator observation>` |
| Physical path / kill state | `<operator observation>` |
| Rollback/restore result | `<complete/failed/incomplete>` |
| Deviations | `<none or bounded description>` |
| Remaining unknowns | `<list>` |
| Verdict | `PASS_LOCAL_SETUP` / `FAIL` / `INCOMPLETE` |

`PASS_LOCAL_SETUP` applies only to this exact local setup. It does not validate another computer,
SoundSwitch version/profile, fixture map, laser, LED/Govee device, or native Autoloop DMX.
