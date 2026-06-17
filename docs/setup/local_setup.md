---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: c678788
last_verified_date: 2026-06-17
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---


# Local Setup Notes

This setup document is intentionally conservative. It describes the current local project shape, not a general installation guide.

## Basic development install

```bash
pip install -e ".[dev]"
```

## Run the bridge

```bash
python -m rb_ss_bridge_v2
```

## Local-only assumptions

- macOS is the only current practical target.
- Rekordbox must be locally installed and readable by the direct reader paths.
- SoundSwitch must be reachable through OS2L for output behavior.
- Laser and Govee behavior depends on local config that may be intentionally ignored by git.
- Secrets and device IDs must remain out of the repo.

## Not covered yet

- clean setup for another user
- Windows/Linux setup
- broad Rekordbox version setup
- broad device onboarding
