---
doc_status: current
truth_level: code-verified
last_verified_commit: c678788
last_verified_date: 2026-06-17
validation_scope: software-only
---

# Configuration Setup

This repo uses tracked example configs plus local ignored configs. Do not commit local device secrets, local IPs, API keys, or backup files.

## Tracked examples

- `config/laser_director.example.json`
- `config/led_look_director.example.json`

## Local configs

Expected local files may include:

- `config/laser_director.json`
- `config/led_look_director.json`

These are local setup files, not public support evidence.

## Known backup warning

Do not commit:

```text
config/led_look_director.json.backup_1781599611
```

## Schema changes

Use `docs/agents/task_playbooks/update_config_schema.md` before changing config schema or examples.
