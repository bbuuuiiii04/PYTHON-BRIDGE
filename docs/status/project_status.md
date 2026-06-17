---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: c678788
last_verified_date: 2026-06-17
validation_scope: software-validated only; hardware-unvalidated in repo evidence
---


# Project Status

## Current public status

**Extreme early alpha.**

This bridge works in my current local setup, but this repository must not present it as production-ready, show-ready, plug-and-play, broadly compatible, or generally supported.

Accepted repo validation label:

> **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**

That does not mean nothing works. It means the repo does not yet contain enough repeatable hardware-validation evidence to make broader claims.

## What is implemented at a high level

- Central runtime startup in `__main__.py`.
- Central state/event ownership in `StateManager`.
- Rekordbox memory/state/live-BPM reader paths.
- SoundSwitch OS2L output path.
- Optional laser config, policy, executor, and MIDI output path.
- Optional LED/Govee look director, color engine, cloud scene adapter, realtime runner, and dispatch coordinator.
- Local runtime status JSON and JSONL command reader.
- Software tests across core math, readers, laser, LED/Govee, runtime status, replay, and frontend tooling.

## What is not yet proven

- broad Rekordbox version compatibility
- Windows or Linux compatibility
- broad macOS version compatibility
- broad SoundSwitch version compatibility
- broad laser fixture compatibility
- broad Govee device compatibility
- repeatable hardware validation from repo artifacts
- plug-and-play setup for other users

## Required wording

Use these phrases:

- “my current local setup”
- “early alpha”
- “software-validated only”
- “hardware-unvalidated in repo evidence”
- “not broadly validated”
- “unknown” when evidence is missing

Avoid these phrases unless future validation proves them:

- production-ready
- show-ready
- stable
- broadly compatible
- plug-and-play
- generally supported
