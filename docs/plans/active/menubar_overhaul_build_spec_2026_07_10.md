# Codex Implementation Spec — Menubar menu overhaul (AWR-192 build round)

doc_status: current
truth_level: implementation-spec (authored by the AWR-192 manager seat; design authority
`docs/plans/active/menubar_overhaul_design_2026_07_10.md`)
seat: build orchestrator lane (tmux), executes under `docs/agents/opus_seat_harness.md` rails.
SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. STAGED-ONLY: never launch the menubar app,
never start/stop/kill the bridge, watcher, or any process. The operator activates by restart.

## Part A — Context & Root Cause (verified; read, do not implement)

All cites verified at commit `092ca5e` (manager desk, 2026-07-10 00:1x). Re-verify each at
YOUR HEAD before editing — the tree moves (auto-sync, parallel lanes).

- [confirmed] `scripts/bridge_menubar.py` builds its menu inline in `BridgeMenuBar.init`
  (lines ~783–866): 9 disabled status rows → sep → bridge toggle → Export + export-status
  line → Smart Phrasing ▸ → Laser Director ▸ → sep → Run Health Check / Record Session /
  Test the Lights… / Laser Pad… / LED Pad… / LED Engine v2 → sep → Quit Menu.
- [confirmed] Emergency laser blackout + clear live INSIDE the Laser Director submenu
  (~822–832) — a mid-show panic control two clicks deep. Gating today:
  blackout `setEnabled_(available and enabled and not emergency)`; clear
  `setEnabled_(available and (emergency or manual_override))` (refresh_, ~922–923).
- [confirmed] `compact_status_lines` (~587–741) renders lasers a full glance row; LEDs get
  NOTHING. The snapshot already carries LED truth: top-level `led_look_director` key
  (`runtime_status.py:166-181`; default `{"enabled": False}`), with
  `adapter.degraded/degraded_reason` and `adapter.realtime.achieved_fps/active_effect/active`
  (verified in a live `/tmp/rb_ss_bridge_v2_status.json`), plus palette/engine via the
  existing `_led_color_engine_status(status)` helper (~417–427).
- [confirmed] `refresh_` fills rows via `zip(self.status_rows, compact_status_lines(...))`
  (~890): a count mismatch SILENTLY drops rows — both branches of `compact_status_lines`
  (stale: ~591–604, live: tail) and the `for _ in range(9)` row allocation (~783) must move
  9→10 together.
- [confirmed] Tests: `tests/test_bridge_menubar.py`, 37/37 green at `99b9e7f`/`092ca5e`
  (0.2 s local; CI skips on missing PyObjC). Pattern: pure functions + methods driven with
  Mock selves; the menu construction itself is untested.
- [unknown → Task 0 resolves] Whether the AWR-186 M2 round has landed its menubar items
  ("Purge RBSS Bridge…", and possibly an install item + `install_controller.py`) at your
  HEAD. The fence requires it landed BEFORE this round edits the file.

## Part B — Tasks (implement exactly, in order; ONE commit per task, explicit paths only)

### Absolute Rules
- Touch ONLY: `scripts/bridge_menubar.py`, `tests/test_bridge_menubar.py`,
  `docs/subsystems/runtime_commands.md`, `docs/validation/software_test_inventory.md`.
  Everything else is out of scope — `scripts/ss_bridge_watcher.sh`, `usb_launcher.py`,
  `install_controller.py` (M2's file, if present), all runtime modules, all configs.
- Behavior that must not change (byte-level semantics):
  `toggleBridge_`, `_toggle_bridge_frozen`, watcher spawn env (`RBSS_BRIDGE_MANUAL=1`),
  launchctl/pkill patterns, `already_running`, the export/detect/reload state machine,
  `_auto_set_soundswitch_pack`, all `append_command` payloads (byte-identical SET — none
  added, none removed, none reworded), timers/icons, pad URLs, and — if M2 landed them —
  the install/purge items' titles, selectors, gating, and handlers (they MOVE, verbatim;
  their function is AWR-186's).
- Error handling: the new LED row formatter fails SOFT to "—" segments on any missing/
  malformed field (same posture as the laser row's `or 0` / `or "—"` guards). No broad
  try/except, no silent fallback anywhere else.
- Dirty worktree: other lanes' files may be dirty or move under you. Never revert or
  clean anything you didn't write; commit by explicit paths only; never `git -a`,
  never `git clean`, never rewrite pushed history.
- Report, don't certify: you report evidence (commits, test names/counts, red names);
  the manager reviews; the executive gates. You never declare the round shipped.
- Run straight through: do not pause at checkpoints for acknowledgment.
- Block, don't invent: if reality diverges from this spec (unknown name, missing file,
  unexpected M2 shape, extra reds you can't name against the baseline): STOP, write
  `/tmp/rbss_lane_signals/menubuild.MBLD.blocked` with one line of evidence, and wait.
  Blocking is a success mode; invention is the failure mode.
- An improvement you notice = a NOTE in your final report, never an edit.

### Task 0 — Verify-first (no commit)
1. FENCE GATE: `grep -n "Purge RBSS Bridge" scripts/bridge_menubar.py` — if absent, the
   AWR-186 M2 menubar item has NOT landed: write the `.blocked` signal ("M2 purge item not
   at HEAD") and stop. (The manager should only have dispatched you after it landed; this
   is the double-check.)
2. Inventory the M2 landing: list every menu item + handler M2 added to this file
   (expected: purge item, possibly an install item; note their exact titles, selectors,
   attribute names, and any visibility gating such as manifest-presence checks). These
   fold into the new layout UNCHANGED in Task 2.
3. Baseline: `python3 -m unittest tests.test_bridge_menubar` — record the exact count
   (37 at spec time + whatever M2 added). Any red here = `.blocked`, do not proceed.
4. Verify the LED field paths at HEAD: `led_look_director` top-level status key exists in
   `runtime_status.py` snapshot assembly, and `led_look_director.py` `status()` (~:225)
   returns `enabled` + `adapter.realtime.achieved_fps/active_effect`. If names differ,
   use the REAL names and say so in the report; if the shape is missing entirely, block.

### Task 1 — `scripts/bridge_menubar.py` + tests: LED glance row (commit 1)
1. Add a pure helper near `_phrasing_summary`:
   ```python
   def led_row_fields(status: dict) -> dict:
       """Glance fields for the LEDs status row; every field degrades to a
       safe default when absent (director off, bridge starting, stale)."""
   ```
   Input: the full status dict. Output keys (exact):
   `state` ("on" | "off" | "unknown"), `fps` (float | None), `effect` (str, "" if none),
   `palette` (str, "" if none), `degraded_reason` (str, "" if healthy).
   Sourcing: `led = status.get("led_look_director")` (non-dict → unknown);
   `state` = "on"/"off" from `bool(led.get("enabled"))` when `led` is a dict, else
   "unknown"; adapter/realtime fields via `.get` chains with `isinstance` guards;
   `fps` only when realtime `active` is truthy and `achieved_fps` is a number;
   `palette` from `_led_color_engine_status(status).get("current_palette")`;
   `degraded_reason` from `adapter.degraded_reason` when `adapter.degraded` is truthy.
2. Render it as status row 10 in BOTH branches of `compact_status_lines`, matching the
   laser row's style exactly (`_seg`/`_join`, `_cs()` labels):
   - stale branch: `_join(_seg("  LEDs  ", color=_cs()), _seg("—", color=_cs()))`
   - live branch: label "  LEDs  "; state text On (`_cg()`) / Off (`_cs()`) / — (`_cs()`);
     when on: append `f"  {fps:.0f}fps"` (omit when None), `f"  {effect}"` (truncate >18
     like the laser scene), `f"  {palette}"` (truncate >18), all `_cs()`; degraded_reason
     as trailing `_co()` segment truncated to 14, exactly like the laser row's suffix.
     `state == "on" and degraded_reason` → state text color `_co()` (matches laser
     enabled-degraded).
3. Bump the row allocation `for _ in range(9)` → `range(10)` in `init`.
4. Tests (`tests/test_bridge_menubar.py`, same module style):
   - `led_row_fields` truth table: empty dict → unknown; enabled False → off;
     enabled True + realtime active + fps 59.63 + effect + palette → all fields;
     degraded True + reason → reason surfaces; malformed (`"led_look_director": "x"`,
     adapter not a dict, fps a string) → safe defaults, never an exception.
   - both `compact_status_lines` branches return EXACTLY 10 rows (pins the zip contract).

### Task 2 — `scripts/bridge_menubar.py` + tests: blueprint + regroup (commit 2)
1. Add a module-level layout spec (pure data, above the class):
   ```python
   # (kind, attr, title, selector) — kind: "status_rows" | "sep" | "action" | "info" | "submenu"
   # "submenu" carries a nested tuple of entries in slot 4.
   MENU_BLUEPRINT: tuple = (...)
   ```
   Exact top-level order (titles exact; selectors are today's — none added/removed):
   1. `("status_rows", "status_rows", 10, None)`
   2. sep
   3. `("action", "toggle_item", "", "toggleBridge:")` — title still set by `refresh_`
   4. sep  — LIVE block
   5. `("action", "laser_blackout_item", "Laser Blackout", "laserBlackout:")`
   6. `("action", "laser_clear_blackout_item", "Clear Laser Blackout", "laserClearBlackout:")`
   7. `("submenu", "smart_phrasing_item", "Smart Phrasing", None, (Smart Drops/`toggleSmartDrop:`, Smart Breakdowns/`toggleSmartBreakdown:`))`
   8. `("submenu", "laser_item", "Laser Director", None, (laser_toggle_item/`toggleLaserDirector:`, sep, 5 info rows: scene/reason/personality/midi/phrasing))`
      — blackout + clear REMOVED from this submenu (they moved to top level; ONE place).
   9. `("action", "led_engine_v2_item", "LED Engine v2", "toggleLedEngineV2:")`
   10. `("action", "map_lasers_item", "Laser Pad…", "mapLasers:")`
   11. `("action", "led_pad_item", "LED Pad…", "openLedPad:")`
   12. sep  — AUTHORING + CHECKS block
   13. `("action", "export_item", "Export", "exportFromSS:")`
   14. `("info", "export_status_item", "", None)`
   15. `("action", "record_session_item", "Record Session: Off", "toggleRecordSession:")`
   16. `("action", "test_lights_item", "Test the Lights…", "testLights:")`
   17. `("action", "validation_item", "Run Health Check", "runValidation:")`
   18. sep  — MAINTENANCE block
   19. M2 items fold in HERE, verbatim (install item first if present, then purge item),
       with the comment marker: `# AWR-186 M2 SLOT: install/purge items — function owned
       by the usbm2 round; structure only.` Preserve their attr names, titles, selectors,
       and every visibility/gating call site in `refresh_`/handlers UNCHANGED.
   20. `("action", "quit_item", "Quit Menubar (bridge keeps running)", "quit:")`
2. Rewrite the menu-construction part of `init` to iterate `MENU_BLUEPRINT` through a
   small builder (one loop + a nested loop for submenus) that reproduces today's per-item
   mechanics exactly: `_add_action` for actions; disabled no-action items for "info";
   `setSubmenu_` for submenus; `setattr(self, attr, item)` for every named entry;
   `self.status_rows` allocation for "status_rows". Everything AFTER construction
   (`setAutoenablesItems_(False)`, export/detect state init, timer, `refresh_`) stays
   byte-identical. Only two title strings change anywhere: "Emergency Blackout" →
   "Laser Blackout" (its `refresh_` gating expressions unchanged) and "Quit Menu" →
   "Quit Menubar (bridge keeps running)".
3. Tests:
   - selector inventory: flatten `MENU_BLUEPRINT` (incl. submenus + M2 entries) → the
     selector multiset equals EXACTLY the pre-refactor 14 (`toggleBridge:`,
     `exportFromSS:`, `toggleSmartDrop:`, `toggleSmartBreakdown:`, `toggleLaserDirector:`,
     `laserBlackout:`, `laserClearBlackout:`, `runValidation:`, `toggleRecordSession:`,
     `testLights:`, `mapLasers:`, `openLedPad:`, `toggleLedEngineV2:`, `quit:`) plus the
     M2 selectors found in Task 0 — each exactly once.
   - blackout placement: `laserBlackout:`/`laserClearBlackout:` at top level, NOT inside
     the laser submenu entries.
   - maintenance block: purge entry (when present) sits after the last separator and
     before `quit_item`; `quit_item` is last.
   - every named attr in the blueprint is unique.
4. If any M2 menubar test from Task 0's baseline pins item TITLES or positions that this
   reorder moves: re-pin those tests to the new blueprint positions (titles/selectors/
   gating stay identical — only position assertions may change). Name every such re-pin
   in the report.

### Task 3 — docs + checks (commit 3)
- `docs/subsystems/runtime_commands.md`: update the menubar surface description (menu
  blocks, the LED glance row, blackout promotion, retitles, M2 slot) to match the code.
- `docs/validation/software_test_inventory.md`: update the `tests.test_bridge_menubar`
  row (new test names + count).
- Bump `bridge_menubar` `last_verified_commit` in `docs/agents/change_contracts.yml` if
  that is the repo convention you observe there (verify before editing; if the field
  lives elsewhere, follow the observed convention).
- Run: `python3 tools/check_docs_metadata.py && python3 tools/check_agent_contracts.py
  && python3 tools/check_docs_drift.py` — all three must pass.

## Part C — Invariants that MUST still hold (live safety)

- The menubar remains the operator's ONLY bridge start surface; this round never starts,
  stops, or signals any process (STAGED-ONLY; builder never launches the app).
- Launch semantics byte-identical: watcher modes, `RBSS_BRIDGE_MANUAL`, launchctl label,
  pkill patterns, frozen re-exec child handling, single-process invariant
  (`pgrep -f 'rb_ss_bridge_v2$' | wc -l` == 1 after an operator start).
- Pad/laser-pad supervision (launchd relaunch) untouched.
- Blackout/emergency SEMANTICS untouched: same two commands, same enabled-gating
  expressions — only menu position and title change. Fail-open beats fail-dark.
- The M2 install/purge items keep their exact function, gating, and confirmation flow.
- No new I/O, threads, or timers in `refresh_`; `led_row_fields` is pure dict-reading.

## Part D — Tests

Named in Tasks 1–2. All new tests follow the module's existing style (import via
`_import_module`, PyObjC skip guard, Mock selves; pure helpers tested as plain dicts).
No test may instantiate `BridgeMenuBar` or touch `NSStatusBar`.

## Part E — Acceptance (definition of done)

1. Three commits by explicit paths, one per task, messages prefixed `AWR-192:`.
2. `python3 -m unittest tests.test_bridge_menubar` — ALL green; report exact count and
   every new/changed test BY NAME.
3. Scoped neighbor check: `python3 -m unittest tests.test_ss_bridge_watcher` (guards the
   untouched-watcher claim) — green or reds named against the environmental baseline.
4. Three hard doc checks green (Task 3).
5. `git diff <pre-round-HEAD> -- scripts/bridge_menubar.py` shows: no `append_command`
   payload changes, no `toggleBridge_`/`_toggle_bridge_frozen` body changes, M2 handler
   bodies unmoved-or-moved-verbatim. State this diff-review result explicitly.
6. Report (final message + `/tmp/rbss_lane_signals/menubuild.MBLD.report.md`): commits,
   test names/counts, the Task 0 M2 inventory, any re-pins (Task 2.4), noted-not-done
   improvements, and the plain-language operator summary (what looks different in the
   menu, what behaves identically, evidence class = software-tested only).
7. Signal: `touch /tmp/rbss_lane_signals/menubuild.MBLD.done` (or `.blocked` + reason).
   Also print your sentinel `MBLD-ROUND-COMPLETE` on its own line.

## When you finish
You report evidence; the AWR-192 manager adversarially reviews at its own desk; the
executive gates. You never declare the round shipped.

## Fix-round addendum (manager review, 2026-07-10 ~01:0x)

Part B Task 2 item 19 was WRONG about the install item: the AWR-186 M2 spec (Task 2)
requires "Install on this Mac…" as the PRIMARY item (top of menu — the DMG-guest
flow). The ordered fix restores M2's original index-0 + separator placement verbatim
and removes the install entry from `MENU_BLUEPRINT`; the maintenance slot holds only
the purge item, then Quit. Tests re-pinned accordingly (blueprint asserts
`installOnMac:` NOT present; M2's own gate tests keep pinning the install source).
The build lane flagged this in its round-1 NOTES before the manager ordered the fix.
