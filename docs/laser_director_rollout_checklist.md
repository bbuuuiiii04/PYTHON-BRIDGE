# Laser Director Rollout Checklist

Status: rollout and validation checklist for final Laser Director go-live.

Use this with the canonical design in `docs/laser_director_design.md` and the SoundSwitch mapping workflow in `docs/laser_director_midi_mapping_workflow.md`.

## Preconditions

- Confirm `config/laser_director.json` exists and validates.
- Keep `enabled=false` and `dry_run=true` for the first pass.
- Confirm operator MIDI port is set to `IAC Driver Bus 1` (or a deliberate override in config).
- Confirm SoundSwitch is listening on the same configured MIDI input.

## Safe Rollout Order

1. Start with missing config and verify startup is healthy (`reason=not_configured` in status/validation paths).
2. Start with intentionally invalid config and verify startup is still healthy (`reason=invalid_config` without bridge failure).
3. Start with valid config, `enabled=false`, `dry_run=true`; verify status JSON includes `laser_director`.
4. Enable Laser Director while staying in `dry_run=true`; validate automatic selection is subordinate to existing autoloop readiness.
5. Verify idle/no-output contract:
   - no playing track => `current_scene=""`
   - no loaded active track => `current_scene=""`
   - stale position => `current_scene=""`
6. Verify automatic musical scene selection only when all are true:
   - active deck is playing
   - active deck has loaded track metadata
   - autoloop state is ready (`lighting_mode=autoloop`, no pending arm/re-arm, and matching `last_armed_filepath`)
7. Verify scripted context (`lighting_mode=scripted` or `scripted_id>0`) returns idle/no-output (`scene=""`, `reason="scripted"`).
8. Validate Smart Drop/Smart Breakdown behavior remains unchanged.
9. Validate OS2L behavior remains unchanged throughout rollout.
10. Test only safe mappings first (`safe_static`, gentle phrase movement).
11. After safe mappings are confirmed, test higher-impact mappings (drop/strobe/aggressive looks) in controlled conditions.
12. Only after all dry-run checks pass, set `dry_run=false` for live MIDI output and re-run the same validation sequence.

## Live Workflow Guidance

- Laser Director is intended for automatic music-aware scene selection, subordinate to existing autoloop readiness.
- Laser Director does not arm SoundSwitch; SoundSwitch must already be in the correct autoloop/show context.
- Bridge runtime commands like `laser_scene` and `laser_blackout` remain compatibility/dev/test controls.
- Do not treat bridge manual override or bridge blackout commands as the recommended live performer workflow.
- Live creative overrides and blackout should be handled directly in SoundSwitch or through the normal external safety path.

## Rollback

Apply one or more of these in order of speed:

1. Set `enabled=false`.
2. Set `dry_run=true`.
3. Remove or rename `config/laser_director.json`.

No OS2L rollback is required.

## Exit Criteria

- Validation marks missing/disabled Laser Director checks as `not_applicable` where applicable.
- Status JSON always includes top-level `laser_director`.
- Idle/no-track/stale/scripted/autoloop-not-ready paths return `scene=""` (send-nothing semantics for future executor).
- Automatic scenes are emitted only when autoloop readiness is true.
