---
doc_status: current
truth_level: software-tested
last_verified_commit: 5db991f
last_verified_date: 2026-07-03
validation_scope: Phase 1 LED Pad MVP only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# LED Pad

LED Pad is a local browser UI for editing and dry-running Govee realtime LED looks through the
production renderer/runner path. It is software-tested only. It does not prove room-visible
Govee behavior, strip restore behavior, or show readiness.

## Launch

```bash
python3 -m rb_ss_bridge_v2.scripts.led_pad --port 8766 --dry-run
```

Open `http://127.0.0.1:8766/`.

Options:
- `--host` / `--bind`: bind address, default `127.0.0.1`.
- `--port`: default `8766`.
- `--config`: explicit LED config path. Otherwise `RBSS_LED_CONFIG` or `config/led_look_director.json`.
- `--dry-run`: use the realtime dry-run transport. This is the safe local software smoke path.

## What It Can Do

- Show banks first: Drafts, Ambient, Groove, Buildup, Drop, Post-Drop, Breakdown, Utility, plus
  a read-only Other chip for `pre_drop` or unknown memberships.
- Duplicate, move, delete, save, discard, and commit LED looks through
  `config/led_look_director.draft.json`.
- Preview realtime-razer looks with synthetic BPM, Test Palette, and Loop settings. Cloud scenes
  are shown but not previewed.
- Derive renderer controls from `REALTIME_EFFECT_PARAM_KEYS` and validate the full draft before
  writing live config.
- Commit the draft to `config/led_look_director.json` with a `.bak-*` backup.

## Ownership And Recovery

If the bridge is not live, LED Pad can play directly. If the bridge status file is fresh, the
pad treats the bridge as owning the LEDs until the operator explicitly takes over. Takeover
appends this JSONL command to the runtime command file:

```json
{"cmd":"led_blackout","reason":"led_pad"}
```

Release appends:

```json
{"cmd":"led_clear_blackout"}
```

Recovery one-liner if the bridge side remains blacked out after a pad session:

```bash
printf '%s\n' '{"cmd":"led_clear_blackout"}' >> /tmp/rb_ss_bridge_v2_commands.jsonl
```

## Commit Behavior

Commit writes the draft to the live config only after
`load_led_look_director_config_from_dict()` accepts the full draft. A committed config affects
the running bridge only after a bridge restart. Restarting the bridge remains a live-operation
approval gate; do the existing single-process check before any restart:

```bash
pgrep -f rb_ss_bridge_v2 | wc -l
```

Expected value is `1`.

## Status

Phase 1 is implemented/software-tested. Template Lab, Locked Palette, and renderer param unlocks
remain pending phases. All LED Pad playback and UI claims are SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED.
