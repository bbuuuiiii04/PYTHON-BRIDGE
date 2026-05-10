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
4. Enable Laser Director while staying in `dry_run=true`; validate manual scene, clear scene, blackout, and clear blackout command paths.
5. Validate automatic policy precedence in dry-run (emergency > manual > safe conditions > smart observation/default behavior).
6. Validate Smart Drop/Smart Breakdown observation behavior remains unchanged.
7. Validate OS2L behavior remains unchanged throughout rollout.
8. Test only safe mappings first (`safe_static`, gentle phrase movement, emergency blackout).
9. After safe mappings are confirmed, test higher-impact mappings (drop/strobe/aggressive looks) in controlled conditions.
10. Only after all dry-run checks pass, set `dry_run=false` for live MIDI output and re-run the same validation sequence.

## Rollback

Apply one or more of these in order of speed:

1. Set `enabled=false`.
2. Set `dry_run=true`.
3. Remove or rename `config/laser_director.json`.

No OS2L rollback is required.

## Exit Criteria

- Validation marks missing/disabled Laser Director checks as `not_applicable` where applicable.
- Status JSON always includes top-level `laser_director`.
- Emergency blackout stays latched until explicitly cleared.
- Manual override and emergency precedence are verified against smart observation cases.
