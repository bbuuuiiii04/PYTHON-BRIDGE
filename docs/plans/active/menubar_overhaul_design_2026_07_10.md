# Menubar overhaul — AWR-192 design note (manager: menubar lane, Fable/HIGH)

doc_status: current
truth_level: design (audit verified against HEAD `99b9e7f`, 2026-07-10 00:0x)
scope: menu STRUCTURE/UX of `scripts/bridge_menubar.py` only. SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED. Staged-only: no bridge/process contact; operator activates by
restarting the menubar app.

## Audit findings (all verified in the file at HEAD)

Confirmed facts:

1. **Menu order today** (init, `bridge_menubar.py:783-866`): 9 disabled status rows →
   sep → Bridge toggle → Export + export-status line → Smart Phrasing ▸ → Laser
   Director ▸ (toggle, Emergency Blackout, Clear Blackout, sep, 5 info rows) → sep →
   Run Health Check → Record Session → Test the Lights… → Laser Pad… → LED Pad… →
   LED Engine v2 → sep → Quit Menu.
2. **Emergency laser blackout is two clicks deep** (`bridge_menubar.py:822-832`) —
   inside the Laser Director submenu. Mid-show panic control behind a hover-submenu is
   the single worst glance/reach defect found.
3. **Zero LED visibility in the status rows** (`compact_status_lines`,
   `bridge_menubar.py:587-741`): lasers get a full row; LEDs get nothing. The status
   snapshot already carries everything needed (verified against the live
   `/tmp/rb_ss_bridge_v2_status.json` + `runtime_status.py:166-181`):
   `led_look_director.enabled`, `.adapter.degraded/degraded_reason`,
   `.adapter.realtime.achieved_fps/active_effect/active`, and
   `state_manager.led_color_engine.engine/current_palette/zone`. AWR-151 (28→60 fps
   launchd throttle) was diagnosed blind for lack of exactly this row.
4. **Grouping is muddled**: Export (authoring, occasional) sits ABOVE the live
   performance controls; tools (pads/record/test/health) are one undifferentiated run;
   `Quit Menu` (quits the menubar app, NOT the bridge) reads ambiguous mid-show.
5. **Launch path** (`toggleBridge_`, `bridge_menubar.py:1194-1219` +
   `_toggle_bridge_frozen` 1170-1192): watcher spawn with `RBSS_BRIDGE_MANUAL=1`,
   launchctl bootout, pkill patterns, frozen-bundle child re-exec. UNTOUCHABLE
   semantics per the brief; structure may move the item, never its behavior.
6. **Testability**: 37 tests green at baseline (local 0.2 s; CI skips on missing
   PyObjC). Existing pattern = pure functions + methods driven with Mock selves; menu
   CONSTRUCTION itself is untested inline code in `init`.
7. **M2 fence** (AWR-186 spec §Task 2/4): M2 adds native install + "Purge RBSS
   Bridge…" (manifest-gated, frozen installs only) into this same file. Not landed at
   HEAD as of this audit; usbm2 lane building now.

## Design (safe defaults; every point veto-open to the operator)

New menu order — five labeled blocks:

```
[STATUS — glance zone, all disabled rows]
  ● BRIDGE / SS / D1+track / D2+track / Checks / Smart Phrasing / Lasers   (as today)
  LEDs <On|Off|—> <fps> <effect> <palette> [degraded_reason]               (NEW row 10)
──────────────
Bridge On|Off|Initializing (click to …)        ← unchanged mechanism & title logic
──────────────  [LIVE]
Laser Blackout                                  ← PROMOTED to top level
Clear Laser Blackout                            ← promoted, same enable-gating
Smart Phrasing ▸  (Drops / Breakdowns — unchanged)
Laser Director ▸  (toggle + 5 info rows; blackout items REMOVED from submenu)
LED Engine v2                                   ← unchanged (still marked temporary)
Laser Pad… / LED Pad…
──────────────  [AUTHORING + CHECKS]
Export  +  Lighting: status line                (unchanged logic, moved down)
Record Session / Test the Lights… / Run Health Check
──────────────  [MAINTENANCE]
«M2 SLOT: Purge RBSS Bridge…»                   ← labeled structural slot, see fence
Quit Menubar (bridge keeps running)             ← retitled from "Quit Menu"
```

Decisions + why:

- **D1 LED status row (the one net-new surface).** Sourced ONLY from existing snapshot
  fields (finding 3); pure formatter alongside the laser row's style; no runtime, no
  new commands. Degraded/fps visibility is the operator's #1 blind spot mid-show.
- **D2 Blackout promotion.** Same two commands (`laser_blackout` /
  `laser_clear_blackout`), same enabled-gating expressions, top level. Items live in
  ONE place (removed from submenu) — no duplicate-item ambiguity. Titled "Laser
  Blackout" (not "Emergency Blackout") because it does NOT touch LEDs — the old title
  overclaimed.
- **D3 Grouping.** Live controls above authoring; separators as block boundaries.
  Export block keeps its status line directly beneath it (pairing preserved).
- **D4 Purge SLOT.** A comment marker + reserved position in the MAINTENANCE block:
  `# AWR-186 M2 SLOT: "Purge RBSS Bridge…" lands here (manifest-gated; function owned
  by the usbm2 round — fold in unchanged)`. If M2 has landed by build time, the
  builder MOVES M2's item into this position verbatim (title/action/gating untouched).
  REVIEW CORRECTION (this manager, fix round): M2's INSTALL item does NOT move here —
  the M2 spec (Task 2) requires "Install on this Mac…" as the PRIMARY item (top of
  menu, DMG-guest flow); it keeps M2's original index-0 + separator placement. Only
  the purge item lives in maintenance.
- **D5 Testable seam.** Extract a pure `menu_blueprint()` → ordered list of row
  descriptors `(kind, title_or_key, selector|None)`; `init` iterates it. Tests pin:
  block order, blackout at top level + absent from submenu, purge slot position,
  selector SET identical to HEAD's (no command lost, none invented), LED row
  formatter truth table. Matches the file's existing pure-function test pattern.
- **D6 Naming pass.** Three retitles (build round corrected this note's original
  "two" miscount): "Emergency Blackout"→"Laser Blackout", "Clear Blackout"→"Clear
  Laser Blackout" (D2), and "Quit Menu"→"Quit Menubar (bridge keeps running)".
  Everything else keeps its name — muscle memory is a feature.

## Explicit non-scope (unchanged behavior, verified untouchable)

- `toggleBridge_` / `_toggle_bridge_frozen` / watcher integration / launchctl /
  single-process invariant / launch-profile env: byte-level semantics frozen.
- Pad/laser-pad supervision (launchd relaunch): untouched.
- All `append_command` payloads: byte-identical set, none added, none removed.
- Export/detect/reload state machine, pack auto-enable, icon logic, timers: logic
  untouched (items may move position only).
- M2 purge item FUNCTION (dialog, manifest, deletion): owned by AWR-186.

## Risks

- Fence: simultaneous edits with usbm2 — mitigated by hard hold until M2's purge item
  is at HEAD (or executive's sequencing word), then fold-in.
- Muscle memory: blackout moves OUT of the submenu — flagged for operator veto.
- The LED row reads adapter fields that are absent when the LED director is off —
  formatter must degrade to "—" (test-pinned), like the laser row does.

## Chain

Build: dispatched orchestrator lane (tmux; Opus/HIGH; opus_seat_harness rails) on a
Part A–E spec. Review: THIS manager seat, adversarial, at its own desk (builder ≠
reviewer). Gate: executive (superman4). Contract: `bridge_menubar` in
`docs/agents/change_contracts.yml` — docs_update: `docs/subsystems/runtime_commands.md`,
`docs/validation/software_test_inventory.md`; tests: `tests.test_bridge_menubar` +
hard checks.
