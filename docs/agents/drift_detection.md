---
doc_status: current
truth_level: code-verified
last_verified_commit: c678788
last_verified_date: 2026-06-17
validation_scope: software-only
---

# Drift Detection

Drift means documentation no longer matches code. This repo is agent-built, so drift is not a hypothetical risk. It is the default weather.

## What is checked automatically

Run:

```bash
python tools/check_docs_metadata.py
python tools/check_agent_contracts.py
python tools/check_docs_drift.py
```

The drift checker is intentionally lightweight. It currently verifies:

- runtime command docs include every command accepted by `runtime_status.py`
- runtime command docs include the actual status and command JSONL paths
- machine-readable change contracts exist and include required sections
- current docs preserve `SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED`
- AGENTS links to the context budget, change contracts, task playbooks, and subsystem map

## What must still be checked by agents

Automatic checks do not prove:

- hardware behavior
- device compatibility
- Rekordbox version compatibility
- SoundSwitch version compatibility
- visual correctness of LEDs/lasers
- that old prompts/plans match current code

For those, inspect code/tests/config first and update matrices only with evidence.

## When drift is suspected

Stop and report uncertainty if:

- code changed but matching subsystem card did not
- command parser changed but runtime command docs did not
- config schema changed but setup/config docs did not
- support matrix claims support without validation evidence
- old prompts/plans disagree with current code
