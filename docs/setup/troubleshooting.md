---
doc_status: current
truth_level: code-verified
last_verified_commit: c678788
last_verified_date: 2026-06-17
validation_scope: software-only
---

# Troubleshooting

This is early-alpha local tooling. Start by checking whether the failure is repo software, local config, app version drift, or hardware/device behavior.

## First checks

```bash
git status -sb
python tools/check_docs_metadata.py
python tools/check_agent_contracts.py
python -m unittest discover tests
```

## Runtime status

```bash
cat /tmp/rb_ss_bridge_v2_status.json
```

## Commands file

```bash
tail -f /tmp/rb_ss_bridge_v2_commands.jsonl
```

## Common failure classes

| Symptom | Likely area | Start with |
| --- | --- | --- |
| no Rekordbox state | direct reader/permissions/version drift | `docs/subsystems/rekordbox_readers.md` |
| SoundSwitch not responding | OS2L connection/setup | `docs/subsystems/soundswitch_output.md` |
| laser output wrong | config/MIDI/executor | `docs/subsystems/laser.md` |
| LED/Govee wrong/choppy | look director/realtime runner/transport | `docs/subsystems/led_govee.md` |
| command rejected | command parser | `docs/subsystems/runtime_commands.md` |

Do not convert troubleshooting observations into support claims unless logged in validation docs.
