---
doc_status: current
truth_level: planned-procedure
last_verified_commit: 9705363
last_verified_date: 2026-07-03
validation_scope: future repo move checklist only; no move, LaunchAgent edit, watcher edit, or live process action executed
---

# Repo Move Checklist

This is a planned procedure for a future move of `/Users/bbui/rb_ss_bridge_v2`.
Nothing here authorizes doing the move during a live night.

## 1. Choose The Target

Prefer `~/Projects/rb_ss_bridge_v2` over `~/Desktop/rb_ss_bridge_v2`.
`~/Desktop` is a macOS TCC-protected folder, so launchd, Terminal, or Python may
need Files-and-Folders permissions at the worst possible time.

If Desktop is chosen anyway, grant and test Files-and-Folders access for
Terminal, Python, and launchd before any live use.

## 2. Stop Everything First

1. Stop the bridge through the menubar/watcher.
2. Confirm no bridge process remains:

   ```bash
   pgrep -f rb_ss_bridge_v2 | wc -l
   ```

   Expected: `0`.

3. Unload the three LaunchAgents:

   ```bash
   launchctl unload ~/Library/LaunchAgents/com.bbui.led-pad.plist
   launchctl unload ~/Library/LaunchAgents/com.bbui.laser-pad.plist
   launchctl unload ~/Library/LaunchAgents/com.bbui.bridge-menubar.plist
   ```

## 3. Move And Rewire

1. Move the repo folder to the chosen location.
2. Update `~/ss_bridge_watcher.sh`:
   - `BRIDGE_DIR`
   - `STREAMDECK_SCRIPT`
   - the osascript manual-session `cd`
3. Update `scripts/bridge_menubar.py`:
   - `WATCHER`
   - `MENUBAR_PATTERN`
   - `ICON_DIR`

   This is a code change. Route it through the `bridge_menubar` contract.

4. Regenerate and reinstall the three plist files from the repo `launchagents/`
   copies.
5. Recreate `.venv`; venvs are not relocatable.
6. Run:

   ```bash
   pip install -e .
   ```

7. Regenerate `graphify-out/` using `docs/setup/graphify.md`.

## 4. Claude And Codex Data

To preserve Claude sessions and auto-memory, rename:

```text
~/.claude/projects/-Users-bbui-rb-ss-bridge-v2
```

to the new absolute path key, using dashes for slashes. Claude's project key is
path-derived in the documented layout; migration behavior is not officially
documented, so verify after the move.

Repo-local `.claude/` moves with the repo. Global `~/.claude` and `~/.codex`
do not need repo-local edits.

## 5. Verify After The Move

Run:

```bash
python3 -m unittest discover tests
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
```

Start the bridge through the watcher, then confirm:

```bash
pgrep -f rb_ss_bridge_v2 | wc -l
```

Expected: `1`.

Then verify:

- LED Pad reachable on `:8766` or the current guide port.
- Laser Pad reachable on `:8767` or the current guide port.
- Menubar is present.
- One manual Graphify smoke query works:

  ```bash
  graphify query "what owns active deck state?"
  ```

## 6. Roll Back

Move the folder back to the original location and reverse every path edit above.
Git state is location-independent; the fragile pieces are watcher paths,
LaunchAgents, virtualenv metadata, generated Graphify output, and path-keyed
Claude project data.
