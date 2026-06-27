---
doc_status: active-adversarial-findings-register
truth_level: code-grounded
last_verified_commit: b0e5e47
last_verified_date: 2026-06-26
validation_scope: running findings register for the adversarial sweep of the SoundSwitch RE ->
  pack -> runtime -> live-DMX pipeline. Read-only on ~/Music; all mutation on scratchpad copies /
  in-memory models. Every finding cites file:line and a runnable repro. SOFTWARE-ONLY discovery,
  HARDWARE-UNVALIDATED. Continued from soundswitch_re_edgecase_hardening_spec.md.
---

# SoundSwitch RE-pipeline adversarial findings register

Repros live under the session scratchpad `work/` (`harness.py` + `repro_*.py` + `fuzz_decode.py` +
`re_sweep.py`). Baseline before any mutation: proof gate **29 PASS / 0 / 0**, SS unit suite
**262 OK**, oracle export **verified / 95 artifacts**.

> ## ⚠️ LIVE-PATH REALITY CHECK (read first)
> The SoundSwitch **pack player is NOT the operator's live light path.** Verified this session:
> there is **no `config/soundswitch_pack_player.json`** → the loader returns `not_configured` →
> `__main__` keeps the **legacy** path (SoundSwitch app via OS2L + laser director). And even if the
> pack were enabled, it opens **only DDJ-800** as a MIDI input; the IAC ch0/note0 blackout binding is
> on a device the pack never reads, so the pack player's blackout **cannot fire**.
>
> Consequence: the **runtime** findings below (F1, F1b, F12, and F2's "dark tracks" impact) describe a
> subsystem that is **not currently driving lights**. They are real *code* issues that matter only
> **when/if the pack is flipped to `output_backend=pack` with a real Enttec port** — they do **not**
> describe the operator's current live behavior. The operator's actual blackout / smart-drop /
> transition-mask behavior is in the **legacy path (OS2L + laser director + smart_phrasing/smart_drop),
> which this sweep did NOT analyze.**
>
> The findings that bite **now** — while the pack is being *built/exported* (PR #116) regardless of
> whether it drives DMX — are the **export/verify/decode** ones: **F3, F4, F5** (green export → won't
> load; decode crash on corrupt catalog). Those are the actionable ones. Everything tagged "runtime"
> is pre-go-live.

Severity key: **S1** live-safety-critical · **S2** false-pass-verify (green export, runtime refuses) ·
**S3** silent-wrong-output · **S4** crash-blocks-export · **S5** cosmetic/mislabel/hardening.

## Summary table

| ID | Sev | One-line | Confidence |
|----|-----|----------|------------|
| F3  | **S2 — bites now (export)** | Two pads → same Static Override slot: `verify_pack`=True, `load_pack` rejects → whole pack would be disabled at load | confirmed (byte-level) |
| F5  | **S2 — bites now (export)** | Control on bridge-reserved `house_post_drop_1` (ch0/note41): verify=True, load rejects | confirmed |
| F4  | **S4 — bites now (export)** | `decode_catalog` leaks `struct.error` (not `SoundSwitchDecodeError`) on a truncated catalog | confirmed |
| F1  | pre-go-live runtime | Static Look on the reserved IAC blackout event (ch0/note0) → blackout classification (LIVE map: StaticOverride31). **Pack not live + IAC not opened ⇒ does not fire today.** Latent for go-live. | confirmed (code) |
| F1b | pre-go-live runtime | Same collision generalises to **autoloop** controls on ch0/note0. Same not-live caveat. | confirmed |
| F2  | export non-determinism now / dark-tracks pre-go-live | Scripted "active" gate keys on the **export host's** filesystem → export differs by host (6 tracks); their "dark" impact is pre-go-live | confirmed |
| ~~F11~~ | — | ~~Emergency blackout doesn't cover the pack laser~~ — **DROPPED: operator never uses emergency blackout.** Code gap is real but irrelevant to actual use (safety theater). | n/a |
| F12 | S3? | Held blackout auto-releases after `stale_timeout_ms` (2s) while the pad is still held — **only matters if the operator holds the blackout pad >2s in pack-DMX mode** | confirmed (repro), relevance unconfirmed |
| F6  | S5 | RE inventory "DDJ overrides" lumps an IAC binding under a DDJ label; RE↔production disagree on StaticOverride31 | confirmed |
| F7  | S5 | Proof `D2-ddj-ch1-19-frames` is a latent content pin — recolouring slots 8/16/17/24 fails the gate | confirmed |
| F8  | S5 | Production export lacks the catalog-declared-count completeness oracle (it exists only in the RE tool) | confirmed |
| — | S5 | `verify_export_completeness` docstring over-claims (only checks Venue cues, not tracks/autoloops) | confirmed |

Ruled OUT after verification (kept for honesty / so the next agent doesn't re-chase):
- **F9 static-override "bleed-through"** — INTENDED. `apply_layers` is a transparent sparse overlay,
  pinned by `tests/test_soundswitch_laser_player.py::test_apply_layers_transparency_zero_and_topmost_wins`
  (asserts base bleeds through unauthored channels). Not a bug; open *fidelity* question only (does
  transparent overlay match SoundSwitch for sparse looks — unknowable without capture).
- **F10 static drops on stop/stale/ended** — DEFENDED by `state_manager.py:3464-3496`, which converts
  every non-happy-path to `clear_selection()` and always passes `authority="fresh"`. The player's
  suppression path is never wired live; held static stands alone. Documented invariant holds.
- **Export atomicity** — solid: forced verify-fail leaves no destination; failed re-publish leaves the
  old canonical pack intact (tested by monkeypatching `verify_pack` to raise).
- **freeze/compare drift detection** — byte-exact (`has_changes` is per-file sha256) + semantic; no
  drift slips past as "no change"; worst case is honest `partial_fail_closed`/`confidence: unknown`.
- **Multi-venue cue contamination** — `decode_venue_cues` does NOT GUID-filter (confirmed with a
  crafted 2-venue blob), but foreign cues are unreferenced (harmless) and a duplicate GUID fails
  closed. Bounded; live project is single-venue (232/232 canonical). Note for the next agent.
- **frame_sender / laser_output_backend / config loader / autoloop catalog resolution** — all
  verified fail-closed; autoloop resolution 0 mismatches vs independent recompute.

---

## Runtime / reload axis (the flagged gap) — detail

### F11 — Emergency-blackout does not cover the SoundSwitch pack laser  [S1, confirmed by code]
- **Where:** pack player exposes `set_emergency` / an `emergency` mask
  (`soundswitch_laser_player.py:296-304,381-382`) that forces ZERO, but the ONLY production caller of
  `set_masks` is `state_manager.py:3422`, which hardcodes `emergency=False`. The operator's
  `laser_blackout` command (`scripts/bridge_menubar.py:1138` → `runtime_status.py:327` →
  `__main__.py:1149` `Ev.LASER_BLACKOUT` → `state_manager.py:1369-1370`
  `laser_director.set_emergency_blackout(True)`) reaches only the **laser director** (MIDI lasers) and,
  separately, the LED director — never the pack player.
- **Live impact:** the SoundSwitch pack drives the *primary laser* over CH1-19 DMX. When the pack is in
  pack-DMX mode and the operator hits "laser blackout" expecting all lasers dark, the pack-driven
  laser keeps rendering whatever scripted/autoloop/static frame is active. The pack's only blackout is
  the IAC ch0/note0 pad (F1) — there is no bridge-level / global emergency blackout for the pack laser.
  The vestigial `emergency` mask strongly suggests the coupling was intended but never wired.
- **Caveat:** bites only when the pack runs `output_backend=pack` with a real `enttec_port`
  (default config is `enabled=False, dry_run=True`); HARDWARE-UNVALIDATED. The wiring gap is real
  regardless of current config.
- **Repro:** `grep` chain above; `state_manager.py:3422` is the only `set_masks` caller and passes
  `emergency=False`. No production path sets the pack player's emergency/blackout except the IAC pad.
- **Fix direction:** route `Ev.LASER_BLACKOUT` (and any global panic) to the pack player's emergency
  mask via the pack runtime, so a laser blackout zeros the pack DMX too.

### F12 — Held blackout auto-releases after the stale timeout (lights return mid-hold)  [S1, confirmed]
- **Where:** `soundswitch_midi_input.py` — `_process_note_on` sets `_blackout_held_at = monotonic()`
  once on the blackout note-on (`:287`); `_expire_blackout_if_needed` (`:246-255`, called every empty
  worker poll at `:457`) releases the blackout when `now - _blackout_held_at >= stale_timeout_ms`.
  `_blackout_held_at` is **never refreshed**, and MIDI sends no repeat note-ons during a physical hold,
  so the timer fires `stale_timeout_ms` (default 2000ms, `controller_hold_timeout_ms`) after the
  *press* regardless of whether the pad is still held.
- **Live impact:** the operator holds the blackout pad (the live StaticOverride31 "BLACK OUT" on IAC
  ch0/note0 — F1) for a breakdown / technical pause / audience-safety moment; after 2s the pack lights
  come back on while the pad is still down. Contradicts the module's own contract
  (`:8` "note-on holds blackout; note-off releases it"). Static-look *press* holds do NOT auto-expire
  (`_expire_blackout_if_needed` only touches blackout), so the behaviour is asymmetric.
- **Repro:** feed `_feed_raw_message(0x90,0,100)` (note-on, no note-off), then
  `_expire_blackout_if_needed(now=t0+2.1)` → `blackout_held` flips True→False, `error="stale_hold"`.
  (Session inline repro; reproduced.)
- **Root cause / fix direction:** the stale timer should track *controller liveness* (time since the
  last message from that device), not time since the blackout press — a healthy held blackout must not
  expire. If a max-duration cap is genuinely intended, document it and make it explicit, not a
  stale-named safety.

### Verified-sound in this axis (ran end-to-end, not just read)
- Controller reload (`soundswitch_pack_controller.py:87-111`): validate-first, atomic single-ref
  publish, stop-before-start on the shared Enttec port, old runtime zeroed — no partial swap. One live
  *consideration* (not a bug): the "swapping" disabled window darkens the rig for up to ~2s while the
  new Enttec port opens.
- Degradation latch (`state_manager.py:3380-3424`): a DDJ dropout drops the manual overlay (held
  static + blackout) but keeps the automatic base — documented operator policy; latch clears only on a
  clean quiet healthy snapshot. Sound.
- `player.reload()` wait-latch (`:247-255`) is **test-only** — production always builds a fresh player
  via the controller. The documented re-anchor latch never runs live (minor; not a bug).
- Reload clears held static (new player + new adapter both empty; old adapter stopped). A held layer
  for a slot absent in the new pack is skipped, not crashed (`apply_layers:193-197`).

---

## LIVE-path audit — transition mask / breakdown blackout (the operator's actual blackout behavior)

This round audited the **legacy live path** (what actually drives lights today): the laser
director / executor + `smart_phrasing` + `smart_rearm` transition-mask and breakdown-blackout
lifecycle. The operator's "transition mask" = a held laser blackout (`laser_executor.py:321` mask_on
dark / `:334` mask_off) armed on entering the pre-drop transition window and on breakdown.

**Result: VERIFIED SOUND — no stuck-dark / leaked-mask bug found.** The class of bug worth fearing
("lasers stuck blacked out after a transition") is defended at every path I could construct:
- The pending laser blackout is force-resolved on **stop** (`_do_stop` → `_clear_smart_rearm_state`
  `:4433` + `reset_runtime_state` `:4398`), **resume** (`:4425-4427`), **deck switch**
  (`_on_master_changed` `:2631-2639`), and **active-track load** (`_on_track_loaded` `:2660-2669`).
- The **transition mask** self-clears every tick via the falling edge (`smart_phrasing.py:410-411`
  `elif scratch.transition_window_active: transition_mask_should_clear = True`), so backward scrub,
  track loop, or a tick that skips the drop all drive the window inactive and clear the mask
  (`laser_executor.py:104-105`), plus the `drop_crossing` resolves it (`:129-248`).
- The **breakdown mask** (latched, not per-tick) has an explicit leaked-window guard
  (`smart_rearm.py:258-277`): "if the playhead leaves the breakdown window any other way … the mask
  sticks on forever … Release the mask and clear the latch" — handled via `if not
  sp_state.smart_breakdown_active`.

**One noted edge (not a confirmed bug):** `Ev.PAUSE` (`state_manager.py:1161-1166`) only sets
`playing=False`; it does not itself resolve the laser pending blackout. A transition mask armed at the
exact moment of a pause holds the laser dark for the pause duration until stop-detection or resume
clears it. Lasers dark while the music is paused is plausibly intended; operator has not reported it.
Worth a live confirm only if the operator pauses mid-pre-drop and sees the lasers stay dark.

This matches the operator's experience ("never noticed a half-blackout / stuck mask"). The remaining
live-path surface that this read-only audit could NOT verify is the **timing math** (drop-beat
detection, autoloop phrase-arm grace windows, master-correction scheduling) — those need a live
runtime / replay harness, not static reading, and are the right target for a runtime-capable follow-up.

## Pre-runtime findings (carried from the hardening spec, re-verified this session)
F1, F1b, F2, F3, F4, F5 detail + repros are in `soundswitch_re_edgecase_hardening_spec.md` Part A and
the `work/repro_*.py` scripts. F3 additionally proven from raw `recordable` bytes through
`decode_learned_midi` → `_resolve_controls` (two slot-8 controls emerge — no model injection).

## Coverage map (this session)
Swept: full pack pipeline (decoder/compile/verify/loader/runtime/controller/frame_sender/backend/
config), the player layering + reload + degradation latch, export atomicity, the RE toolkit
(crash-fuzz of 7 importable parsers — all clean; divergence check — only the DDJ mislabel),
freeze/compare drift, multi-venue cue handling, autoloop catalog resolution.
NOT yet swept (handoff): the OS2L legacy path (`sound_switch_engine`/`osl_output`/`os2l_injector` —
arguably out of the pack pipeline), `enttec_dmx_pro` wire framing (hardware-adjacent), the
capture-replay RE tools (`validate_*_capture`, `parse_artnet_pcap`, `align_capture`,
`audit_legacy_capture`, `correlate_midi_autoloop`, `uuidxref`, `t7d_phase_contract`), and a
structural (length/offset-consistent) corruption fuzz of `SoundSwitchVenues.bin` for silent mis-parse.
