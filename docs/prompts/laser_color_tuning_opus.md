# Prompt — Laser-color tuning with Brandon (Claude Opus 4.8)

**Target:** Claude Opus 4.8 · **effort: xhigh** · set a large max-output-token budget (~64k).

---

## Mission

Work **with Brandon, iteratively**, to tune the laser-color feature in `/Users/bbui/rb_ss_bridge_v2`. Two goals:

1. **Primary:** make the laser color follow the LED's **actual current (wandering) color** instead of the fixed palette-**center** color it uses today.
2. **Ongoing:** tune the feature overall to Brandon's taste (which color the laser tracks, the v2 slot choice, quantizer behavior, CH9/settle, rainbow/white handling, sampling cadence).

This drives **real lasers during live DJ sets**. It was silently broken until 2026-07-07 (a config path bug — see below) and now works. Brandon is the operator, not a software engineer; he live-tests every change immediately and trusts what he sees with his own eyes over any argument.

This is a **collaborative session**, not a fire-and-forget one-shot. Propose, let him steer, change one thing, verify it hard, and iterate.

## Source-of-truth order (obey it)

Executable `*.py` > tests (`tests/`) > config (`config/*.json`) > `runtime_status.py` > docs. **If a doc conflicts with code, code wins for describing current behavior.** Everything in this packet was verified on 2026-07-07 but treat file:line anchors as **leads to re-confirm** — several of these files were edited that day, so line numbers may have shifted; grep the named symbol.

## How the feature works today (verified 2026-07-07)

The laser is driven by the bridge's own SoundSwitch **pack render → Enttec DMX** (SoundSwitch is out of the live path). On autoloop tracks, the bridge overwrites the pack's authored **CH8 (Color)** and **CH9 (Color Speed)** with a color derived from the LED palette, quantized to the laser's fixed colors.

- **The pure mapper** — `laser_color_engine.py`: `LaserColorEngine.update()/_target()/snapshot()` turn an LED color state into a `LaserColorSnapshot(ch8, ch9, seq)`. `_nearest_fixed_color()` quantizes an RGB to the nearest of **6 fixed colors** — red, green, blue, cyan, yellow, purple (`FIXED_COLOR_ORDER`); **white is reserved** (white-moments only, never from quantizing). CH8 values live in `config/laser_color_map.json` (`enabled`, `fixed`, `fixed_ch9`=null, `effects.rainbow_family`=null, `settle.ease_beats`). Loaded by `load_laser_color_map()` (default now `_DEFAULT_COLOR_MAP_PATH`, module-relative).
- **The LED color source** — `led_color_engine.py`: `color_state()` (~:918) is what the laser reads. It returns `{"rgb", "palette", "white_sand_active", "rainbow_active"}`. It is documented (`laser_color_authority.md` Implementation Notes) as a **pure read of the current anchor RGB without advancing RNG or mutating journey state** — this constraint is load-bearing (see the primary task).
- **The merge to the wire** — `soundswitch_laser_player.py`: `_merge_color_snapshot()` (~:124) copies the rendered autoloop frame and overwrites only CH8 (`frame[7]`) and CH9 (`frame[8]`) from the snapshot; a None/invalid snapshot leaves the authored bytes → **fail-open to baked pack color**.
- **The forwarding + sampling** — `state_manager.py`: `_update_laser_color_from_led()` reads `color_state()` and calls `laser_engine.update()`; it is called from three sites — `_sync_laser_color_if_needed()` (on LED color-signature change, every playing tick), `_bootstrap_laser_color_if_needed()` (once when the snapshot is None), and a re-sample on accepted LED automation triggers. `_drive_pack_output()` forwards `laser_color_engine.snapshot()` to the player via `set_color_snapshot()` before each render. (Line numbers here shifted on 2026-07-07 — grep the method names.)

## The just-fixed bug (context — do NOT re-fix, just know it)

The bridge runs `python3 -m rb_ss_bridge_v2` from the repo **parent** (`/Users/bbui`; the watcher `cd`s to `dirname(REPO_ROOT)`). `load_laser_color_map()` used a **relative** default path, so from that cwd the file wasn't found → map loaded **disabled** → the whole feature was silently off (lasers played baked pack CH8). Fixed by making the default module-relative (`_DEFAULT_COLOR_MAP_PATH = Path(__file__).resolve().parent / "config" / "laser_color_map.json"`), plus a warning log and a `[SM] laser-color-map enabled=... fixed_colors=...` startup line. The live bridge now logs `enabled=True fixed_colors=7`.

## The primary change: laser follows the LED's actual wandering color

**Current behavior (verified by running the engine):** the laser tracks `color_state()` → `_p_to_rgb(self._anchor_p, ...)`. `_anchor_p` sits at the palette **center** (`_apply_palette_now()` sets it to `_palette_center()`; only `advance_fade()` moves it, sliding between palette centers on a palette change). So the laser holds one color per palette (the center) and only shifts colors while a palette change is fading.

**The LEDs, by contrast,** wander *within* the palette per section via a **separate** path — `resolve_color()` / `_focus_window()` (~:557-591): a focus window inside the palette's p-interval widened by `spread` (and `role_spread` when `drama_by_role`), with `step_within_section`. This wander does **not** write `_anchor_p`, so the laser never sees it. That decoupling is exactly what Brandon wants changed.

**The hard constraint you must design around:** `color_state()` must stay a **pure read** — the laser samples it opportunistically and it must not advance the LED engine's RNG or mutate its journey/focus state, or you'll perturb the LED show itself. `resolve_color()` may mutate/advance. So "make the laser follow the wander" almost certainly means exposing the LED's **last-resolved actual color** (a read-only mirror the LED dispatch already computed) or a pure recompute — **not** calling `resolve_color()` from the laser path. Find the cleanest pure source of "the color the LEDs are showing right now" and feed that to the mapper. Confirm whether the LED dispatch already stashes its last emitted color somewhere readable.

**v2 path:** when v2 is active, `color_state()` samples `dressing.slot_rgbs[2]` (a fixed slot). This can mismatch the zone's vibe (e.g. EMBERCORE's slot-2 dark-purple quantizes to blue/red, not a warm color). Part of tuning is deciding what "the color the LEDs show" means in v2 (which slot / a dominant-color computation) and applying the same pure-read discipline.

## The broader tuning knobs (for the ongoing session)

Which LED color the laser follows (center vs wander vs dominant-look color); the v2 slot/dominant choice; the quantizer's 6 colors and deterministic tie-breaks (yellow effectively never fires — the hue space avoids it; white reserved); `fixed` CH8 values; `fixed_ch9` (null → CH9 authored passthrough) and `settle.ease_beats` (post-drop CH9 ease-down); `effects.rainbow_family` (null → Rainbow mode is currently laser-passthrough; could drive a color-change effect tier); white-moment / `white_sand` → white; and the sampling cadence (how often the snapshot refreshes). Any config-only change (CH8/CH9/settle/rainbow values) lands without code.

## Authority docs (the intended-behavior "should")

- `docs/architecture/laser_color_authority.md` — target behavior. **Note:** it currently says laser color is "sampled at phrase anchors and per drop section" (Rule 1). If the follow-the-wander change alters that intent, this doc must be **updated in the same change** (it's the acceptance oracle; drifting from it is a regression by definition).
- `docs/subsystems/laser.md` (Package 4) and `docs/plans/active/laser_color_engine_design_spec.md` — implementation detail.
- Change contract: follow `docs/agents/change_contracts.yml` key `laser` and the anti-drift rule in `AGENTS.md` §7.

## How to work with Brandon (working agreement — these are hard)

- **Plain English, explain the mechanism, no jargon.** Banned words: "blast radius", "load-bearing", "seams". He needs to understand *how* and *why*, minus the engineering vocabulary. Describe color behavior in plain scenes ("during a palette change the laser slides red → purple → blue, then holds blue").
- **Decide with safe defaults; ask only for a veto.** Do not run design-fork question rounds. When there are options (e.g. center vs wander vs dominant-color), pick the best default, describe what each would look like on the floor in one or two lines, and ask him to veto — don't make him choose from a menu.
- **One change per turn.** Ship one tuning change, verified, then stop and let him live-test.
- **Chat is the surface.** Say everything fully in chat; never answer with "see the doc." Docs are records, not where he reads answers.
- **Humble reporting, no overstatement.** Never claim a check, fix, or observation you didn't actually run — verify by running/looking first. State the evidence class and the untested remainder together ("proven in the harness; your eyes on a live track are the last confirmation").

## Verify-first flow (mandatory for every code change)

This is the flow that just nailed the cwd bug — use it, don't shortcut it. **No fix without a reproduction/verification first.**

1. **Reproduce/measure in a harness.** Drive the **real** engine + real config offline (as in `tests/test_state_manager_pack_driver.py`'s `_make_sm`/`_pack`/`_FakeBackend`, and the color computations that already exist). Compute the exact before/after laser colors per palette/zone from `config/led_look_director.json` — real values, not eyeballed. Run **from `/Users/bbui`** at least once (cwd matters here).
2. **Test.** Add a failing test first, then the change; keep `tests/test_laser_color_engine.py` and the StateManager construction suites green (`python3 -m unittest discover tests` from the repo root). Do not modify tests to make behavior pass.
3. **Adversarial subagent review.** Opus spawns few subagents by default — explicitly spawn one to **try to falsify** each load-bearing claim and the change (purity of `color_state`, no LED-show perturbation, fail-open preserved, no other consumer broken). Require a SURVIVES/FALSIFIED verdict with quoted evidence.
4. **Live confirm.** Launch the bridge the sanctioned way and read the log; then hand it to Brandon to eyeball on a real track.

## Live-safety invariants (never violate)

- **Fail-open — never "no lasers."** A missing/disabled/None/invalid snapshot must pass authored CH8/CH9 through. A read failure keeps the previously held color. Blackout/emergency still zero everything; static override still wins over injected color; scripted/diagnostic/idle frames inject nothing.
- **`color_state()` stays a pure read** — no RNG advance, no journey/focus mutation.
- **Exactly one bridge process.** After any (re)start: `pgrep -f "\-m[[:space:]]rb_ss_bridge_v2$" | wc -l` must be `1`. Launch via the watcher in manual mode (`RBSS_BRIDGE_MANUAL=1 bash scripts/ss_bridge_watcher.sh`), which runs the bridge from `/Users/bbui`; the bridge logs to `~/Library/Logs/rb_ss_bridge/current.jsonl` and `/tmp/bridge.log`. Do not leave a rogue watcher fighting his menubar — if you start one for a check, kill the watcher (leave the bridge as an orphan his menubar can adopt), or stop both cleanly.
- The push loop is 200 Hz — add no blocking I/O to the render/color path; the color math is pure in-memory.

## Roles / authority

The repo default is "Claude reasons/plans/reviews; Codex implements bridge code." **Brandon grants you (Opus) implementation authority for this laser-color tuning workstream** — an operator-granted per-workstream exception. You may edit code directly, provided you follow the verify-first flow above for every change. If a change grows beyond laser color, stop and confirm scope.

## Claim discipline, success criteria, stop conditions

- Label every load-bearing claim **confirmed** (you read/ran the exact code/line), **assumed** (inferred — say why), or **unknown** (state what you'd need). Re-confirm the file:line leads above against current code before relying on them. No hidden chain-of-thought — evidence-tied reasoning, labels, and verdicts only.
- **Success (per change):** the laser color behavior matches what Brandon asked for, proven in the harness with exact before/after values, tests green, an adversarial subagent's attempt to falsify it fails, `color_state()` verified still pure, fail-open preserved, and the authority doc updated if intent changed. Live confirmation is Brandon's to give.
- **Stop and ask** only for a real decision: a behavior/architecture choice with no safe default, a code/doc conflict, live-safety risk, or scope growth beyond laser color. Otherwise decide, act, verify, and report in plain English.
