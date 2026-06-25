---
doc_status: active
truth_level: operator-intent
last_verified_commit: 8f57e49
last_verified_date: 2026-06-25
validation_scope: planning-handoff
---

# SoundSwitch Pack Repo-Local Handoff

Next Codex session: move the generated SoundSwitch pack location into the
`rb_ss_bridge_v2` checkout, but keep the generated pack artifacts out of git.

## Operator Intent

- The bridge is meant to operate without the SoundSwitch app.
- The canonical generated pack should not live under `~/Music/SoundSwitch/...`.
- Put the pack under the bridge repo so the bridge owns its runtime files in one
  local workspace.
- The generated pack directory must be gitignored. Do not commit generated pack
  JSON/artifacts.

## Suggested Target

Use a repo-local ignored path such as:

```text
/Users/bbui/rb_ss_bridge_v2/local/soundswitch/rbss_canonical_pack
```

Then add an ignore rule for the repo-local generated area, for example:

```gitignore
local/
```

If a narrower rule is preferred, ignore only:

```gitignore
local/soundswitch/
```

## Current State To Change

- `config/soundswitch_pack_player.json` is gitignored and currently controls the
  live pack-player path.
- The old `pack_path` pointed outside the repo under the user's Music
  SoundSwitch folder.

- Update `tools/export_soundswitch_pack.py`, `scripts/bridge_menubar.py`, and
  local config/example references to publish and load from the repo-local path.

## Implementation Boundaries

- Do not commit `config/soundswitch_pack_player.json`.
- Do not commit generated pack contents.
- Keep the bridge loading from one canonical pack path after the move.
- Update current tests/docs that hard-code the old Music-folder pack path.
- Keep runtime controller behavior unchanged unless a separate prompt explicitly
  asks for controller changes.

## Verification

After implementation, verify:

```bash
git check-ignore local/soundswitch/rbss_canonical_pack/manifest.json
python3 -m unittest tests.test_bridge_menubar tests.test_soundswitch_pack_commands
git diff --check
```

Also run the exporter once and confirm the generated `manifest.json` lands under
the repo-local ignored path, not under `~/Music/SoundSwitch/`.
