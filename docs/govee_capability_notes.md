# Govee Capability Notes

Status: CURRENT SUPPORTING

These notes summarize the Govee capability and safety boundaries used by the
LED Look Director integration. Raw Govee responses live only in private `/tmp`
artifacts and should not be pasted into prompts, docs, tests, or status output.

## Discovery Policy

Capabilities must be discovered or operator-confirmed. Do not assume that a
Govee device supports scene, off, brightness, DIY, music mode, or any other
control just because another Govee model does.

The standalone capability capture phase found an H612D target named
`Strip Light` and confirmed dynamic scene query support. The full device ID is
private and must remain out of committed files.

## Supported Routes

Current known routes for the mapped H612D target:

- dynamic scene control for mapped scene looks
- off/blackout via power switch capability

The adapter must capability-gate actions:

- scene actions require a scene-capable target
- off/basic blackout requires off or power-switch capability
- unsupported capability paths fail soft and remain visible in status

## Secrets

`GOVEE_API_KEY` is environment-only:

```text
GOVEE_API_KEY=...
```

Never store or print:

- API keys
- authorization headers
- full device IDs
- raw Govee request/response bodies

Config validation rejects secret-like keys such as `api_key`, `token`,
`secret`, `authorization`, `auth_header`, `bearer`, and `password`.

## Dry-Run And Live Boundaries

`dry_run=true` is the safe rehearsal mode. It exercises policy, queueing, status,
dedupe, capability checks, and failure visibility without physical output.

`dry_run=false` is live-capable and must be treated as physical output. Any live
Govee command requires the exact phase-specific Supervisor live approval phrase.
Any claimed physical scene, blackout, or clear-blackout behavior requires human
visual confirmation.

Phase 8 automatic role-entry is approved only for dry-run/config-gated behavior.
Live automatic Govee automation remains closed until a later explicit gate.

## Failure And Degraded Status

Expected fail-soft cases include:

- queue full
- unsupported capability
- request timeout
- send exception
- malformed Govee response
- status provider failure
- circuit breaker open after repeated send failures

These failures must not block `StateManager._push_tick` or disrupt SoundSwitch
or laser behavior. They should be visible through sanitized status fields such
as queue depth, queue max, degraded reason, last error, dry-run state, accepted
count, rejected count, and dropped count.

## Latency Expectations

Govee is suitable for section-level room cues, not frame-accurate or beat-locked
fixture movement. Automation must trigger on meaningful role-entry transitions
and must not emit commands every tick or every beat.
