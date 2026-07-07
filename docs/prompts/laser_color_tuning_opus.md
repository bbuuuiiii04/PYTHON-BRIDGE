# Prompt — Laser-color tuning, WITH Brandon (Claude Opus 4.8)

**Target:** Claude Opus 4.8 · **effort: xhigh** · set a large max-output-token budget (~64k).

---

## Mission

**Work with Brandon as a thinking partner** to explore and tune the laser-color feature in `/Users/bbui/rb_ss_bridge_v2`. This is a **collaborative design/tuning conversation**, not an implementation job. Two threads:

1. **Primary:** figure out, together, how to make the laser color follow the LED's **actual current (wandering) color** instead of the fixed palette-**center** color it uses today — what the options are, what each would look like on the dance floor, and which one he wants.
2. **Ongoing:** tune the feature overall to his taste — which color the laser tracks, the v2 slot choice, quantizer behavior, CH9/settle, rainbow/white handling, sampling cadence.

**Do NOT make code changes.** Your job is to understand the current behavior, explain it to him plainly, lay out real options with real trade-offs, measure exact before/after color values so decisions are grounded, and design the change *with* him. Only when Brandon explicitly says "implement it" do you move — and even then, the default in this repo is that **Codex implements bridge code**; unless Brandon says otherwise in the moment, your output at that point is a written plan/spec he can hand off, not edits. Talk it through first. Always.

This drives **real lasers during live DJ sets**. Brandon is the operator, not a software engineer; he live-tests immediately and trusts his own eyes over any argument.

## Source-of-truth order (obey it)

Executable `*.py` > tests (`tests/`) > config (`config/*.json`) > docs. **If a doc conflicts with code, code wins for current behavior.** Everything below was verified 2026-07-07 but treat file:line anchors as **leads to re-confirm** — several of these files were edited that day, so line numbers may have shifted; grep the named symbol before relying on it.

## How the feature works today (verified 2026-07-07 — confirm against code)

The laser is driven by the bridge's own SoundSwitch **pack render → Enttec DMX** (SoundSwitch is out of the live path). On autoloop tracks the bridge overwrites the pack's authored **CH8 (Color)** and **CH9 (Color Speed)** with a color derived from the LED palette, quantized to the laser's fixed colors.

- **Pure mapper** — `laser_color_engine.py`: `LaserColorEngine.update()/_target()/snapshot()` → `LaserColorSnapshot(ch8, ch9, seq)`. `_nearest_fixed_color()` snaps an RGB to the nearest of **6 fixed colors** (red, green, blue, cyan, yellow, purple; `FIXED_COLOR_ORDER`); **white is reserved** (white-moments only). CH8 values in `config/laser_color_map.json` (`enabled`, `fixed`, `fixed_ch9`=null, `effects.rainbow_family`=null, `settle.ease_beats`).
- **LED color source** — `led_color_engine.py`: `color_state()` (~:918) is what the laser reads, returning `{"rgb","palette","white_sand_active","rainbow_active"}`. It is documented as a **pure read of the current anchor RGB without advancing RNG or mutating journey state** — that purity is load-bearing (see the primary thread).
- **Merge to the wire** — `soundswitch_laser_player.py`: `_merge_color_snapshot()` (~:124) overwrites only CH8 (`frame[7]`) / CH9 (`frame[8]`); a None/invalid snapshot leaves the authored bytes → **fail-open to baked pack color**.
- **Forwarding + sampling** — `state_manager.py`: `_update_laser_color_from_led()` reads `color_state()` and calls `laser_engine.update()`, from three sites — `_sync_laser_color_if_needed()` (LED color-signature change, per playing tick), `_bootstrap_laser_color_if_needed()` (once when snapshot is None), and a re-sample on accepted LED automation triggers. `_drive_pack_output()` forwards `laser_color_engine.snapshot()` via `set_color_snapshot()` before each render. (Line numbers shifted 2026-07-07 — grep method names.)

## Recent fix (context only — the feature is now live)

The bridge runs `python3 -m rb_ss_bridge_v2` from the repo **parent** (`/Users/bbui`). `load_laser_color_map()` used a **relative** default path, so from that cwd the map loaded **disabled** and the whole feature was silently off. Fixed 2026-07-07 (module-relative default + startup log); the live bridge now logs `[SM] laser-color-map enabled=True fixed_colors=7`. Do not re-litigate this; just know the feature works now.

## The primary thread: laser follows the LED's actual wandering color

**Today (verified by running the engine):** the laser tracks `color_state()` → `_p_to_rgb(self._anchor_p, ...)`. `_anchor_p` sits at the palette **center** (set by `_apply_palette_now()` → `_palette_center()`; moved only by `advance_fade()`, sliding between palette centers on a palette change). So the laser holds one color per palette (the center) and only shifts while a palette change fades.

**The LEDs** wander *within* the palette per section via a **separate** path — `resolve_color()` / `_focus_window()` (~:557-591): a focus window inside the palette's p-interval, widened by `spread` (and `role_spread` when `drama_by_role`), with `step_within_section`. This wander does **not** write `_anchor_p`, so the laser never sees it. That decoupling is what Brandon wants to change.

**The constraint that makes it interesting:** `color_state()` must stay a **pure read** — the laser samples it opportunistically and it must not advance the LED engine's RNG or mutate its journey/focus state, or it perturbs the LED show itself. `resolve_color()` may mutate/advance. So "follow the wander" likely means finding a **read-only mirror of the color the LEDs are actually showing** (does the LED dispatch already stash its last emitted color?) rather than calling the wander function from the laser side. Work this design out *with* Brandon — options, trade-offs, what each looks like live.

**v2 path:** when v2 is active, `color_state()` samples `dressing.slot_rgbs[2]` (a fixed slot), which can mismatch the zone's vibe (e.g. EMBERCORE's slot-2 dark-purple → blue/red, not warm). Deciding what "the color the LEDs show" means in v2 (which slot / a dominant-color idea) is part of the same conversation.

## The broader tuning knobs (for the ongoing conversation)

Which LED color the laser follows (center vs wander vs dominant-look); the v2 slot/dominant choice; the quantizer's 6 colors + deterministic tie-breaks (yellow effectively never fires — the hue space avoids it; white reserved); `fixed` CH8 values; `fixed_ch9` (null → CH9 authored passthrough) and `settle.ease_beats` (post-drop CH9 ease-down); `effects.rainbow_family` (null → Rainbow mode is currently laser-passthrough); white-moment / `white_sand` → white; sampling cadence. Config-only changes (CH8/CH9/settle/rainbow values) would land without code — useful because Brandon can iterate on those by ear/eye.

## How to measure (so the conversation uses real numbers, not guesses)

You may **investigate read-only** to ground the discussion: read code, run the real engine offline with his real config to compute exact laser colors per palette/zone (there is prior art — a harness pattern in `tests/test_state_manager_pack_driver.py` and standalone scripts that load `config/led_look_director.json` + `config/laser_color_map.json` and print RGB → fixed-color), and read the event log. Show Brandon concrete before/after values ("blue_cyan center is (0,127,255) → **blue**; if we follow the wander it would swing cyan↔blue across a section"). **This is read-only measurement, not implementation** — do not edit repo files or touch the running bridge to do it.

## Authority docs (the intended-behavior "should")

- `docs/architecture/laser_color_authority.md` — target behavior; it currently says laser color is "sampled at phrase anchors and per drop section." If a change would alter that intent, note that this doc is the acceptance oracle and would need updating as part of the eventual implementation.
- `docs/subsystems/laser.md` (Package 4), `docs/plans/active/laser_color_engine_design_spec.md` — detail. Change contract key `laser` in `docs/agents/change_contracts.yml`.

## How to work with Brandon (hard rules)

- **Plain English; explain the mechanism; no jargon.** Banned: "blast radius", "load-bearing", "seams". He needs *how* and *why* without the engineering vocabulary. Describe color behavior as scenes ("on a palette change the laser slides red → purple → blue, then holds blue").
- **Decide with safe defaults; ask only for a veto.** Don't run design-fork question rounds or hand him a menu. When there are options, recommend one, describe in a line or two what each looks like on the floor, and let him veto.
- **One idea at a time.** Think one thread through with him, then stop for his reaction. Don't sprint ahead.
- **Chat is the surface.** Say everything fully in chat; never "see the doc."
- **Humble reporting.** Never claim a check or observation you didn't actually run — verify by running/looking first, and say the evidence class plus what's still untested.
- **You are a partner, not an autopilot.** Explore, explain, propose, and design *with* him. Implementation is a separate, explicit step he initiates — not something you start on your own.

## Live-safety facts (so your designs respect them)

- **Fail-open — never "no lasers."** Any missing/disabled/None/invalid snapshot must pass authored CH8/CH9 through; a read failure keeps the held color. Blackout/emergency zeroes everything; static override wins over injected color; scripted/diagnostic/idle inject nothing. Any design you propose must preserve this.
- **`color_state()` must stay pure** (no RNG advance, no journey mutation).
- The push loop is **200 Hz** — the color math is pure in-memory; no design should add blocking I/O to the render/color path.
- The bridge runs from `/Users/bbui`; it logs to `~/Library/Logs/rb_ss_bridge/current.jsonl`. (You are not launching or restarting it — read-only.)

## Claim discipline + what "good" looks like

- Label load-bearing claims **confirmed** / **assumed** / **unknown**, tied to evidence; re-confirm the file:line leads against current code before relying on them. No hidden chain-of-thought — evidence-tied reasoning and labels only.
- **A good session** leaves Brandon with a clear, plain-English understanding of how the laser color works today, real measured before/after values for the options, a recommended approach he's agreed to (or vetoed toward another), and — only if he says so — a written plan/spec ready for implementation. Success is the shared decision, not shipped code.
- **Stop and ask** only for a real decision (a taste call, a behavior trade-off with no safe default, a code/doc conflict). Otherwise reason it out and put it in front of him in plain terms.
