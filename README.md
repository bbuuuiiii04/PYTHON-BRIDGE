# rb_ss_bridge_v2

Status: CURRENT AUTHORITATIVE

Audited against the current checkout on 2026-05-12.

`rb_ss_bridge_v2` is a realtime Rekordbox to SoundSwitch bridge. It reads
Rekordbox state, reconciles guarded direct-memory signals with TimecodeLink and
MTC fallbacks, and speaks VirtualDJ-shaped OS2L to SoundSwitch.

Start here:

1. `docs/current_architecture.md` - 15-minute current-state overview.
2. `docs/bridge_design.md` - detailed current design and invariants.
3. `docs/runtime_invariants.md` - rules that should not be broken during code
   changes.
4. `docs/doc_index.md` - classification of every markdown file.

Offline ANLZ energy tooling:

- `docs/anlz_energy_project.md` - canonical overview of the bridge-local ANLZ
  energy investigation toolkit, labels, limits, and validation framing.
- `docs/re/anlz_waveform_tag_inventory.md` - observed ANLZ waveform/beatgrid/tag
  inventory.
- `docs/validation/anlz_energy_evaluation_guide.md` - practical small-corpus
  human validation workflow.
## Subsystem map (one-line each)

- `SmartPhrasingEngine` - pure musical phrasing engine; emits smart-drop,
  smart-breakdown, and phrase-anchor intents.
- `LaserDirector` - laser role/scene policy from `LaserContext` and
  `SmartPhrasingState`.
- `LaserSceneExecutor` - laser MIDI output, blackout/cooldown gates, and
  transition-mask cleanup.
- `SoundSwitchEngine` - OS2L/SoundSwitch intent fanout helpers over canonical
  4-deck routing.
- `StateManager` - coordinator/event-loop owner; owns `DeckState`, most
  `OutputState`, runtime timing, and decision logs.

Historical rollout notes and investigation logs are preserved under
`docs/history/` and `docs/validation/`. They are evidence, not the primary
description of current behavior.

Run:

```bash
cd /Users/bbui
python3 -m rb_ss_bridge_v2
```

The local launcher scripts currently default to guarded direct B1-B6 paths with
TimecodeLink and MTC retained as fallbacks.

## Watcher Laser Director Config

The watcher launcher `scripts/ss_bridge_watcher.sh` now sets
`RBSS_LASER_CONFIG` automatically to:

`$REPO_ROOT/config/laser_director.json`

When that local file is missing, the watcher copies
`config/laser_director.example.json` to `config/laser_director.json` before
launching the bridge, then enforces:

- `enabled=true`
- `dry_run=true`

`config/laser_director.json` is local-only and ignored by git.
`config/laser_director.example.json` remains the tracked template.

Verify Laser Director status after launch:

```bash
cat /tmp/rb_ss_bridge_v2_status.json | jq .laser_director
```

## Laser Pad (web mapping UI)

Run the in-repo Laser Pad server:

```bash
cd /Users/bbui
python3 -m rb_ss_bridge_v2.scripts.laser_pad --host 127.0.0.1 --port 8765
```

> **iPad on LAN** (optional): for operator access from another device on the same Wi-Fi,
> edit `launchagents/com.bbui.laser-pad.plist` and change `--host 127.0.0.1` to
> `--host 0.0.0.0`, then `launchctl unload` + `launchctl load` the plist. Treat this as
> a deliberate exposure — anyone on your LAN can write the laser config draft.

Then open:

- `http://127.0.0.1:8765` on desktop

Laser Pad is now the canonical mapping surface.

Detailed workflow and API notes are in `docs/laser_pad.md`.

## Development

Install the project with test dependencies:

```bash
pip install -e ".[dev]"
```

Run the test suite:

```bash
python -m unittest discover tests
```
