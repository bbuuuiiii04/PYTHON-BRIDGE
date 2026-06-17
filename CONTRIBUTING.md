# Contributing

This is my early-alpha local lighting bridge. Contributions must optimize for truth, safety, and maintainability before polish.

## Non-negotiable rules

- Do not change runtime behavior in documentation-only work.
- Do not claim broad compatibility without support-matrix evidence.
- Do not claim hardware validation without an entry in `docs/validation/hardware_validation_log.md`.
- Do not treat old prompts, plans, or reports as current truth.
- Do not commit local secrets, live config, device IDs, or backup files.
- Do not commit `config/led_look_director.json.backup_1781599611`.

## Before opening a PR

Run, when practical:

```bash
python tools/check_docs_metadata.py
python -m unittest discover tests
```

If a command cannot run locally, document the exact reason.

## Required docs review

Every behavior-changing PR must review:

- `docs/status/feature_status_matrix.md`
- `docs/status/support_matrix.md`
- `docs/status/validation_matrix.md`
- `docs/status/active_work_registry.md`
- the relevant subsystem docs

If none of those need changes, say why in the PR.
