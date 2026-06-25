# Codex Implementation Spec — Lighting Pack enable/disable from the menu bar

## Part A — Context & root cause (verified; read, do not implement)

The operator is heading toward running lights **direct-to-DMX via the pack player**
(bypassing the SoundSwitch app). The export button already compiles a pack; the goal
of this spec is the one missing operator control: turning the pack **on/off from the
menu bar**.

**Most of the wiring already exists — do NOT rebuild it:**

- [confirmed] The pack controller is constructed and registered at startup:
  `__main__.py:1288` builds `SoundSwitchPackController(...)`, and `__main__.py:1310`
  passes `pack_command_callback=soundswitch_pack_controller.handle` into `CommandReader`.
- [confirmed] The command path works end to end: `runtime_status.py:415-430` dispatches
  `set_soundswitch_pack`, forwarding `command["action"]` plus optional `backend`/`enabled`
  to the controller; parse/validate at `runtime_status.py:474-486` accepts
  `action ∈ {reload, backend, enable}`, `backend ∈ {pack, none, midi}`, `enabled: bool`.
- [confirmed] Controller behavior: `soundswitch_pack_controller.py:70` `handle(action, *,
  backend=None, enabled=None)` →
  `enable True` ⇒ validate-first `_swap_to_started` (`:124,:98`);
  `enable False` ⇒ `_go_disabled` which zeros + stops output (`:81,:126`);
  `backend none` ⇒ disabled, `backend pack` ⇒ start, `backend midi` ⇒ `unsupported_action`.
  **No implicit hot-enable** (`:139-147`).
- [confirmed] Config-driven auto-enable at startup already works:
  `__main__.py:966-967` sets `enabled=(bundle.reason == "pack")`. A config with
  `enabled:true`/`output_backend:"pack"`/valid Enttec setup comes up **on at boot** —
  this is the operator's "automatic" path, made as one deliberate config choice.
- [confirmed] The status snapshot already exposes everything a toggle needs:
  `runtime_status.py:29-45` (`_DEFAULT_PACK_STATUS`) and `state_manager.py:123-146`
  (`_pack_operational_state`) give `soundswitch_pack` keys `available`, `enabled`,
  `operational_state`, `reason` (`reason=="not_configured"` when no config file).
- [confirmed] The menu already renders pack state in the status line under the Export
  button (`scripts/bridge_menubar.py` `pack_export_status_line`), and already knows how
  to enqueue this command family: `bridge_menubar.py:934` sends
  `append_command({"cmd":"set_soundswitch_pack","action":"reload"})`. `append_command`
  is `bridge_menubar.py:278` (appends a JSON line to `/tmp/rb_ss_bridge_v2_commands.jsonl`).
- [confirmed] `self.menu.setAutoenablesItems_(False)` is set (`bridge_menubar.py:644`), so
  `setEnabled_()` on a menu item is now honored (a greyed item really is unclickable).

**The one gap:** there is **no menu item** that sends `set_soundswitch_pack action=enable`.
The menu can only `reload`. That is what this spec adds.

**Honest limitation the operator must know (state it, do not paper over it):**

- [confirmed] **"dry-run" cannot run enabled without hardware.** `__main__.py:477-480`:
  when `dry_run` is true OR `output_backend=="none"`, the startup bundle has
  `frame_sender=None` and `reason` `"dry_run"`/`"none"` (not `"pack"`), so it comes up
  disabled. The controller's `prepare` (`__main__.py:1277-1286`) **raises**
  `pack_prepare_failed` when `frame_sender is None` (`:1279`), so an `enable=true` while in
  dry-run/none/no-config **fails** (returns `(False, "RuntimeError")`, surfaced as
  `_last_error`; runtime stays disabled). Net: **enabling the pack requires a real
  `output_backend:"pack"` + `dry_run:false` + Enttec port.** Making true no-hardware
  "enabled" testing possible would require changing the controller/startup to build a
  no-op (NoneBackend) frame sender — that is **out of scope** here (see Open question).

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Do not touch** the pack controller (`soundswitch_pack_controller.py`), the startup
  wiring (`__main__.py`), `runtime_status.py`, `state_manager.py`, the export button
  (`export_button_text`), export detection (`detect_export_state`), or the status-line
  wording (`pack_export_status_line`). They are already correct/validated.
- **No behavior change to the 200 Hz push loop or any DMX/output path.** The menu only
  enqueues a command string; the bridge command thread + validate-first controller own all
  output and safety. The menubar must **not** import or call the controller / frame sender.
- No new git branch; work on `main`.

### Task 1 — `scripts/bridge_menubar.py`: pure decision function (place next to `export_button_text`)
Add a pure function so the title/clickability is testable without AppKit:

```python
def pack_toggle_line(pack_status: dict, *, bridge_status: str | None = None) -> tuple[str, bool]:
    """(title, clickable) for the Lighting Pack on/off item.

    Pure: derived only from the copied snapshot. The menu never drives DMX —
    clicking only enqueues a set_soundswitch_pack command for the bridge.
    """
    if bridge_status == "off":
        return "Lighting Pack: bridge off", False
    pack = pack_status if isinstance(pack_status, dict) else {}
    if not pack.get("available") or pack.get("reason") == "not_configured":
        return "Lighting Pack: not configured", False
    if pack.get("enabled"):
        return "Lighting Pack: On  (click to turn off)", True
    return "Lighting Pack: Off  (click to turn on)", True
```

### Task 2 — `scripts/bridge_menubar.py`: add the menu item (right after the export status line)
The export button + its status line are created at the block ending with
`self.export_status_item` being added to the menu. Immediately **after** that block, add:

```python
self.pack_toggle_item = self._add_action("Lighting Pack: …", "toggleSoundswitchPack:")
```

(`_add_action` exists at `bridge_menubar.py:751`; it sets target=self and appends.)

### Task 3 — `scripts/bridge_menubar.py`: title/enabled update in the refresh path
In the same method that calls `self._render_export_state()` (the per-refresh apply method;
`self._status` is already assigned earlier in `refresh_`), right after the
`self._render_export_state()` call, add:

```python
pack_title, pack_clickable = pack_toggle_line(
    self._snapshot.get("soundswitch_pack", {}), bridge_status=self._status)
self.pack_toggle_item.setTitle_(pack_title)
self.pack_toggle_item.setEnabled_(pack_clickable)
```

### Task 4 — `scripts/bridge_menubar.py`: the click handler (place next to `toggleLaserDirector_`)
Mirror the existing toggle pattern (`bridge_menubar.py:1055`): enqueue, then refresh.

```python
def toggleSoundswitchPack_(self, _sender):
    pack = self._snapshot.get("soundswitch_pack", {}) if isinstance(self._snapshot, dict) else {}
    currently_on = bool(pack.get("enabled"))
    append_command({"cmd": "set_soundswitch_pack", "action": "enable",
                    "enabled": not currently_on})
    self.refresh_(None)
```

### Task 5 — `config/soundswitch_pack_player.json` (gitignored starter; local only)
[confirmed] `config/soundswitch_pack_player.json` is gitignored (`git check-ignore` passes),
so this file is local and will not be committed. Create it from the example with **safe,
disabled defaults** plus clear placeholders the operator fills when hardware arrives:

```json
{
  "_comment": "LIVE pack-player config (gitignored). Starts DISABLED + dry-run = no DMX. To run lights: set enttec_port to your Enttec device path, confirm fixture_map (DMX channel per fixture 1-19), set output_backend=pack, dry_run=false, then enable from the menu (Lighting Pack: Off -> On).",
  "enabled": false,
  "dry_run": true,
  "output_backend": "none",
  "pack_path": "~/Music/SoundSwitch/rbss_canonical_pack",
  "fixture_map": {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10, "11": 11, "12": 12, "13": 13, "14": 14, "15": 15, "16": 16, "17": 17, "18": 18, "19": 19},
  "fixture_map_path": "",
  "midi_input_aliases": {},
  "enttec_port": "",
  "frame_stale_timeout_ms": 250,
  "controller_hold_timeout_ms": 2000
}
```

Validate the file loads cleanly: `load_soundswitch_pack_player_config()` must return
`available` truthfully and never raise (it is fail-closed). Do not invent an Enttec port.

## Part C — Invariants that MUST still hold (live safety)
- The menubar process **never** drives DMX and never imports the controller/frame sender;
  it only appends a command line. All output + validate-first safety stays in the bridge
  command thread (`soundswitch_pack_controller.py`).
- **No auto-enable.** The toggle sends `enable` **only** on an explicit click, computing the
  target as the negation of the snapshot's current `enabled`. It must never send `enable`
  during refresh/render.
- Disabling is always safe (`_go_disabled` zeros + stops output). Enabling is validate-first;
  on failure the controller keeps the old runtime and sets `_last_error` — the menubar must
  not crash or assume success (it re-reads truth on the next snapshot).
- A stale/missing snapshot (`soundswitch_pack` absent or not a dict) must render
  `"Lighting Pack: not configured"`, greyed — never a clickable enable.
- No change to the export button, export detection, status-line wording, the 200 Hz loop,
  or any other menu item.

## Part D — Tests
Extend `tests/test_bridge_menubar.py` with a pure-function truth table for
`pack_toggle_line` (no AppKit, no files):

- `bridge_status="off"` → `("Lighting Pack: bridge off", False)` regardless of pack dict.
- `{}` / non-dict / `{"reason":"not_configured"}` / `{"available":False}` →
  `("Lighting Pack: not configured", False)`.
- `{"available":True,"enabled":True}` → `("Lighting Pack: On  (click to turn off)", True)`.
- `{"available":True,"enabled":False,"reason":"dry_run"}` →
  `("Lighting Pack: Off  (click to turn on)", True)`.

Run: `python3 -m unittest tests.test_bridge_menubar` (must stay green). Do not modify other
tests to pass.

## Part E — Acceptance (definition of done)
- [ ] Menu shows a **Lighting Pack** item directly under the Export status line.
- [ ] With no/dry-run/none config → item reads `not configured` and is greyed (unclickable).
- [ ] With a real `output_backend:"pack"` + `dry_run:false` + valid Enttec config:
      Off→click enqueues `{"cmd":"set_soundswitch_pack","action":"enable","enabled":true}`;
      On→click enqueues `...,"enabled":false`. (Verify by tailing
      `/tmp/rb_ss_bridge_v2_commands.jsonl`.)
- [ ] `pack_toggle_line` truth-table tests pass; full `tests/test_bridge_menubar.py` green.
- [ ] Part A "dry-run cannot run enabled" limitation is left intact (no controller/startup edits).
- [ ] After the operator restarts the menubar, exactly one menubar process
      (`pgrep -f bridge_menubar.py | wc -l` == 1); the bridge itself is untouched.

## Open question (do NOT implement without operator sign-off)
True **no-hardware enabled testing** (watch `operational_state` transition with zero DMX) needs
the controller/startup to build a no-op NoneBackend frame sender in dry-run instead of
`frame_sender=None` (`__main__.py:477-480`, `:1279`). That touches validated live-critical code
and belongs in its own plan-first spec. This spec deliberately stops at the menu control.

## When you finish
- Commit per task. Final message e.g.
  `feat(menubar): Lighting Pack enable/disable control (sends set_soundswitch_pack)`.
- Report: tasks done, test output (pass/fail counts), and confirm you did NOT modify the
  controller, startup wiring, runtime_status, state_manager, or the export/detection/status-line
  logic.
```

## Pre-handoff review (Claude — done before this was printed)
- [confirmed] Every Part A claim re-read at current HEAD (controller wiring, command path,
  startup auto-enable, snapshot fields, dry-run frame_sender=None, autoenables=False, gitignore).
- Pending-state/mode-transition: N/A — adds no output-tick logic and no persistent runtime
  state; the menu reads the snapshot and enqueues one command.
- Third-party API (AppKit): exact `_add_action` + `setTitle_`/`setEnabled_` calls mirror existing
  items; `setEnabled_` is honored because autoenables is off.
- Pure-function seam: `pack_toggle_line` is AppKit-free and unit-tested.
- Live safety: menu never drives DMX; no auto-enable; disable zeros output; failure is
  non-fatal and self-corrects on next snapshot.
- Adversarial: stale snapshot → greyed "not configured"; enable-without-hardware → fails
  safely and the toggle reverts on next refresh; double-click race → command thread serializes,
  snapshot reconciles. Surfaced the real dry-run limitation instead of hiding it.
