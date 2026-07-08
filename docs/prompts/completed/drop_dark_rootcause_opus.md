# Prompt — Prove the root cause: lasers dark at the drop (#1), then LED flash before solo (#2) — Claude Opus 4.8

**Target:** Claude Opus 4.8 · **effort: xhigh** · set a large max-output-token budget (~64k).

---

## Mission

Find and **prove** the root cause of two live-lighting bugs in `/Users/bbui/rb_ss_bridge_v2`, in strict order:

- **#1 — lasers go dark at the drop:** at a real drop, the laser produces no visible output on ~80% of drops; a laser burst appears mid-section (~32 beats later) instead.
- **#2 — LED flash before a laser solo:** when a laser solo fires, the LEDs briefly play a drop look, then blacken, instead of already being dark going into the hit.

**Hard gate: you may not begin #2 until #1's root cause is reproduced AND has survived an adversarial attempt to falsify it.** State plainly when #1 is proven, and only then start #2.

This is a **root-cause investigation, not a fix job.** The deliverable is a proven diagnosis. Do not implement a behavior fix.

## The discipline — this is the whole point (read twice)

Brandon has been handed wrong, confident root causes before (including by me — twice on #1; see below). He will not accept another. Therefore:

- **Prove, don't assert.** Every load-bearing claim must be backed by either (a) a reproduction you actually ran and can show, or (b) an exact code/log line you quote. A claim with neither is not allowed in the report.
- **Reproduce before you name a root cause.** A cause you cannot reproduce and demonstrate on demand is a *hypothesis*, not a root cause — label it as such. The bar for "root cause" is: you can make the failure happen and not-happen at will, and you can show the exact line where it originates.
- **Unknown is a valid, required answer.** If you cannot prove something, write `unknown` / `unproven` and say exactly what evidence you'd need. Do **not** guess, do **not** fill the gap with a plausible-sounding story, do **not** round a lead up to a conclusion.
- **Adversarially falsify your own conclusion** before presenting it. Opus spawns few subagents by default — **explicitly spawn at least one subagent per issue whose only job is to break your root cause** (attack the reproduction, the mechanism, the evidence, and hunt for a simpler/different cause). Report what attacks it survived. If it doesn't survive, you don't have the root cause yet — keep going.
- **Do not overstate.** Separate, in the report, what you proved from what remains open. Match claim strength to evidence strength. No triumphant language.
- **Label every claim** `confirmed` (you ran it / quote the line), `assumed` (inferred — say why and what would confirm it), or `unknown`.
- **No hidden reasoning** — evidence-tied reasoning, quoted lines, labels, and verdicts only.

## Source-of-truth order

Executable `*.py` > tests (`tests/`) > config (`config/*.json`) > event log > docs. **Code wins over docs for current behavior.** Everything below was gathered 2026-07-07; treat file:line anchors as **leads to re-confirm** (several files were edited that day — grep the symbol). Do not trust any lead in this packet as fact until you re-verify it yourself.

## #1 — lasers dark at the drop: what is established, and what is NOT

**My two earlier root-cause attempts on #1 were WRONG — do not inherit them:**
- Wrong theory A: "the laser MIDI refire is late / ungated." Falsified — the MIDI fires on time (below).
- Wrong theory B: "a blackout mask (`master_switch`) is held through the crossing." Falsified — no mask on/off events land near any crossing; `master_switch` is a deck-load thing.
Start from the evidence, not from these.

**Confirmed (re-verify each):**
- The laser's MIDI selection fires **on time at every drop.** Log `perf.laser.fired reason="drop_crossing"` lands at the same beat as `perf.drop "crossing"`, within ~1ms, at every one of 9/9 (and 13/13 in a sibling log) crossings. Log: `~/Library/Logs/rb_ss_bridge/current.jsonl` (and rotated `bridge-*.jsonl` siblings in that dir). So #1 is **not** a MIDI-timing bug.
- The **DMX render** (a separate path from the MIDI trigger) comes back blank on **16 of 20 crossings across two logs:** the native-autoloop resolver logs `status=unsupported_layout` at the crossing tick, and the same target renders `rendering_active` on a later ~32-beat repeat. On `unsupported_layout`, `state_manager.py`'s pack-drive native block resets the resolver and clears the selection (`_native_autoloop.reset(); player.clear_selection(); _drop_presentation_base_live=False`), so the submitted frame is ZERO (dark) that tick.
- **The pack is not broken.** I loaded the real pack (`local/soundswitch/rbss_canonical_pack` via `soundswitch_pack_loader.load_pack`) and every one of the 16 drop-bank autoloops (`house_drop_1..16` → `SSAutoLoop*.ssfile` via the autoloop bindings) is `supported_active=True` and renders a non-zero frame through `render_autoloop_frame`. So `unsupported_layout` at runtime is **not** a static pack property.
- **`unsupported_layout` is a misleading catch-all status.** `native_autoloop_resolver.finalize_native_autoloop_render()` maps `inactive_autoloop`, a genuine unsupported layout, **and any other render diagnostic** (e.g. `player_error`) all onto `status="unsupported_layout"`. The real `diagnostic` sub-code is computed but **not printed** in the `[SM] native-autoloop status=...` log line — so the true failure reason is currently invisible in the log.
- Because the same target renders both ways at different crossings, and the static diagnostics (`inactive_autoloop`, layout) are fixed per target, the failing diagnostic is most likely a **transient/per-tick** one (candidates: `player_error` from a render raise, or a resolver identity/phase mismatch) — **but which one is genuinely `unknown` and is the crux you must prove.**

**The core unknown to prove:** the exact `diagnostic` sub-code (and the exact code line and runtime condition) that makes `player.select_autoloop(target_identity, phase_tick)` return a diagnostic at the crossing, given the target is valid/active offline. Trace: the executor's selected drop scene → `_native_captured_scene` → `native_autoloop_resolver.resolve(scene, bindings, ...)` (scene→binding→`target_identity`, `phase_tick` via `_phase_tick`) → `state_manager._drive_pack_output` → `player.select_autoloop(...)` → `soundswitch_laser_player._autoloop_base` (which returns `inactive_autoloop` / `unsupported_layout` / `player_error` / `unverified_parity`). Config that matters: `smart_drop_mode="blackout_mask"`, `pre_drop_blackout_beats=4-8` (`config/laser_director.json`), `pack_path`/`parity_live` (`config/soundswitch_pack_player.json`). The bridge runs `python3 -m rb_ss_bridge_v2` from cwd **`/Users/bbui`** (relevant — a relative-path config bug was just found and fixed there; check whether any config the pack/render path reads is cwd-dependent).

## #2 — LED flash before a laser solo: the lead to prove (do NOT start until #1 is proven)

**Lead (high-confidence but you must prove it independently, not take it on faith):** the LED pre-dark blackout can never arm, so the blackout only lands at the impact tick — after the LED drop look was already dispatched.
- Pre-dark arms in `drop_presentation.py` `WindowMachine.tick()` (idle→pre_dark branch) only when `inputs.laser_visible` is true.
- `laser_visible` is computed in `state_manager.py` `_drop_presentation_tick()` as `base_live and role in ("drop","post_drop") and not laser_masked and laser_enabled`.
- During the pre-dark window (final `led_predark_beats`, default 4, before the drop): `role` is still `"none"` (the crossing hasn't happened), **and** the laser is masked by the smart-drop pre-drop cut (`pre_drop_blackout_beats` ≥ `led_predark_beats`, so `mask_owners_active()` is true → `laser_masked` true). So `laser_visible` is false for **two** independent reasons → pre-dark never arms.
- Log-confirmed: `pre_dark` never appears before any crossing in two logs. Test note: a unit test shows `WindowMachine` *can* arm pre-dark when fed `laser_visible=True` during approach, and there is **no** integration test for approach-time pre-dark.
- **Safety coupling to #1:** darkening the LEDs early is only safe if the laser reliably fires at the drop — which is exactly what #1 breaks. Note this coupling in the #2 diagnosis.

Prove #2 the same way: reproduce that pre-dark cannot arm in the real path (a harness driving `_drop_presentation_tick` / `WindowMachine` with the real approach state), quote the exact gating lines, and adversarially try to find a condition where it *would* arm before impact.

## Allowed tools and exact limits

- **Read** any repo file, tests, config, and the event log(s) at `~/Library/Logs/rb_ss_bridge/`.
- **Build read-only harnesses** (the primary path): construct the real objects offline and drive the failing sequence. Prior art: `tests/test_state_manager_pack_driver.py` (`_make_sm`, `_pack`, `_FakeBackend`), `soundswitch_pack_loader.load_pack`, `native_autoloop_resolver`, `soundswitch_laser_player`. Run harnesses **from `/Users/bbui`** at least once (cwd matters). Reproducing the crossing render in a harness — feeding the resolver the crossing scene + the real `phase_tick` and seeing the actual diagnostic — is the cleanest proof and touches nothing.
- **Temporary instrumentation is allowed ONLY if a harness cannot surface the real diagnostic**, and only to prove #1: you may add a minimal diagnostic log (e.g. print the real `diagnostic` sub-code the `unsupported_layout` status hides) and run the bridge to observe it. If you do: launch via the watcher in manual mode (`RBSS_BRIDGE_MANUAL=1 bash scripts/ss_bridge_watcher.sh`), confirm **exactly one** bridge process (`pgrep -f "\-m[[:space:]]rb_ss_bridge_v2$" | wc -l` == 1), read the JSONL log, then **revert the temporary instrumentation** and kill any watcher you started (leave no watcher fighting the menubar). Ask Brandon to play a drop track if live reproduction needs it.
- **Forbidden:** implementing a behavior fix; leaving any temporary/experimental change in the tree; modifying tests to make a point; `git clean`; committing; running the bridge for anything other than surfacing the hidden diagnostic; touching #2 before #1 is proven.

## How to work with Brandon

- Plain English; explain the mechanism; no jargon (banned: "blast radius", "load-bearing", "seams"). Describe behavior as scenes on the floor.
- One issue at a time; #1 fully proven before #2. Give a clear update when #1 is proven and you're moving to #2.
- Chat is the surface — say everything fully in chat, don't point him at a doc.
- Pause only for a real decision (a genuine fork with no safe default, or needing him to play a track / run the bridge live). Otherwise investigate and report.

## Deliverable and falsifiable success criteria

A written diagnosis, in chat, for **each** issue, containing: the reproduction (how to make it happen and not-happen), the exact mechanism at `file:line` with quoted code, the exact log/harness evidence, the adversarial-falsification verdict (what attacks it survived), and per-claim `confirmed`/`assumed`/`unknown` labels — with the proven part cleanly separated from any remaining unknown.

- **#1 is done only when:** the dark-at-drop failure is reproduced deterministically, the exact diagnostic/mechanism (which sub-code, which line, which runtime condition) is proven — not assumed — and an adversarial subagent's attempt to falsify it failed. If the true diagnostic cannot be proven from code + logs + harness without live instrumentation, say so and state exactly what run would settle it, rather than guessing.
- **#2 is started only after #1 meets that bar**, and is done to the same standard.
- **Stop conditions:** if a mechanism is genuinely undeterminable from the evidence available, mark it `unknown` with the specific missing evidence and stop — do not manufacture a conclusion. If code contradicts a lead in this packet, report the contradiction and follow the code.
