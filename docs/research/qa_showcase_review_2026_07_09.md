---
doc_status: current
truth_level: qa-findings-report
last_verified_commit: d634471
last_verified_date: 2026-07-09
validation_scope: >
  Adversarial QA review loop over everything shipped overnight 2026-07-09 (operator
  showcase mandate): AWR-157, AWR-159, AWR-160, AWR-161+micro, laser config round,
  AWR-163 F2, AWR-164 F4, plus AWR-170 post-landing. Five finder dimensions (regression
  matrix, edge cases, live-scenario replay simulation, stress, AWR-170 review), each
  independently refuted; one directed flake hunt (executive order). All evidence is
  software-only, produced on frozen source trees at pinned commits with example configs
  and test seams — no bridge start, no hardware, live config read-only. Nothing here is
  hardware-validated; the operator's morning mix remains the live gate.
---

# Showcase QA review — findings report (overnight 2026-07-09)

**Program:** Fable QA manager (claude10) per `docs/prompts/active/qa_showcase_review_kickoff_2026_07_09.md`;
Opus orchestrator lanes + Sonnet subagents; every finding verified by an independent
refuter (default-to-refuted), ship-blocker escalated to the executive in real time.
**Pins:** review `b2af2bf` (all of AWR-157…164 in, AWR-170 out), pre-tonight `f4bfd06`,
AWR-170 shipping tree `53a4513`. Canonical interpreter `/opt/homebrew/bin/python3` (3.14.6).

## Verdict in one paragraph
Tonight's shipped surface is in strong shape for the morning mix: the kill-switch matrix
is proven identical-when-off cell by cell, the centerpiece F2 engine is cheap (worst
realistic plan ≈ 10 ms, off the push loop), leak-free over a simulated multi-hour set,
and storm-safe at the load gate. The program surfaced **one SHIP-BLOCKER — D3-F1, a
latent pre-tonight stuck-blackout leak on the idle-no-audible path, live-reachable on the
operator's Director-enabled rig — escalated in real time, executive-verified, fixed same
hour as AWR-171, and the fix independently confirmed by the refuter chain. Live risk
CLOSED before the mix.** Beyond it: 1 CONFIRMED MAJOR (rare-trigger, evidence-bounded),
MINOR polish items, one refuted finding, and a resolved test-flake classification. Full
ledger below.

## Findings ledger (post-refutation)

| ID | Sev | One-line | Where | Refuter verdict |
|---|---|---|---|---|
| D3-F1 | **SHIP-BLOCKER → FIXED (AWR-171)** | `drop_spotlight` LED blackout owner leaks when active-deck resolves to 0 during a live solo dark-hold window; room stays dark (no self-release while idle); latent pre-tonight, exposure raised by tonight's solo ergonomics; live rig is Director-enabled (`enabled:true,dry_run:false` verified) | `state_manager.py:2084` (idle gap), `:4129-4132` (early return), vs `:5067→:2863` (correct stop path); fix at `state_manager.py:2120-2125` (HEAD) | Manager triple-verified (repro at review pin + shipping HEAD + PRE pin; live config read); executive desk-verified; **fix round AWR-171 LANDED (`250a8a9`, one-call `_drop_presentation_release_on_stop()` from `_enter_idle_no_audible`)**; QASR3: leak re-proven on unfixed tree (exit 2), finder's repro now CLEAN on fixed tree (exit 0), fix verified pure/in-memory + idempotent, exposure realism CONFIRMED (`active_deck=0` = both faders down/paused, `active_deck_resolver.py:103,:219` — a normal fader-mixer move), 192-beat cap arithmetic verified, pre_chorus does NOT share the class. **Live risk CLOSED** |
| D1-F1 | MAJOR | AWR-160 gate re-fires TRACK_LOADED on a transient unreadable `track_info` (None) → full mid-song LED/laser reset via non-idempotent `_on_track_loaded`; re-fire carries no ANLZ_PATH; PRE absorbed the same transient | `rb_state_reader.py:405-409`; consumer `state_manager.py:2148` | **CONFIRMED, MAJOR upheld** (QASR1): repro re-ran both pins; no-downstream-dedup verified incl. the one candidate guard (`_is_playing_sibling_load` same-deck False); severity closed empirically — 543 real loads across 9 operator sessions on the gate-less PRE reader show ~0 same-title mid-song reloads, so the trigger is rare; fix shape: distinguish None (unreadable → preserve `_last_track`) from "" (real eject → clear) |
| D2-F1 | MINOR | F2 `abort_at` (early darkness release when the sub floor returns) computed but never consumed → up to ~3 extra pre-drop dark beats on hard-family collapses with a pickup; docstring claims OLC-B early-release that was never wired | `lighting_moments_v2.py:358-372,:444-451`; only consumer reads `.beats` (`:826`) | **CONFIRMED MINOR** (QASR2): dead-field grep re-proven, repro extended to the consumer (`transition_window_for` returns 4.0 not the abort-shortened 1); bounded within one pre-drop window, no stuck-dark |
| D2-F2 | MINOR | F2 plan reassignment gated on `markers_changed`, not plan-changed → stale darkness/tiers after a beatgrid-only re-analysis | `state_manager.py:1495,:1503-1504` | **CONFIRMED MINOR** (QASR2): sole-writer coupling proven (`:1504` only assign; `models.py:74` clears); trigger rarity keeps it MINOR |
| ~~D2-F3~~ | — | ~~Partial `laser_tiers` dict fires lasers unconditionally on a `for_drop` miss~~ | `drop_presentation.py:315-318` (latent handling, unreachable) | **REFUTED-COUNTEREVIDENCE** (QASR2): `select_smart_drops` is a pure subset filter — every smart drop IS a raw drop (distance 0), both call sites share one list, counter-repro shows MISSES=[]; the finder's repro hand-built the partial dict. Latent-only; fails toward lasers-on if ever reachable |
| D4-F1 | MINOR | `govee_manual_trigger.py` provenance gate hard-aborts on ANY HEAD drift within 24h (AWR-169 class; auto-sync makes drift constant); fails safe, operator-tool only | `tools/govee_manual_trigger.py:203,:98` | **CONFIRMED MINOR** (QASR4): mechanism + exit-2-before-device-read code-confirmed; fails safe; reachability real (auto-sync moves HEAD every turn) |
| D4-F2 | MINOR | Unbounded anlz-worker thread spawn per load → transient CPU starvation risk under a rapid multi-track *cache-miss* storm (GIL fine; scheduler contention); operator's 716 warm caches make it an unknown-track edge | `state_manager.py:2279` | **CONFIRMED MINOR** (QASR4): bare `Thread().start()` per load verified, threads exit (no leak), GIL-vs-scheduler distinction audited sound; storm consequence stays reasoned-only |
| D4-F3 | MINOR | Pack export reads `git rev-parse HEAD` twice per publish (manifest + sidecar) → inconsistent provenance record if a commit lands between (AWR-169 class; currently inert — no reader compares the field) | `tools/export_soundswitch_pack.py:142,:276` | **CONFIRMED MINOR** (QASR4): inert claim strengthened — `scripts/bridge_menubar.py:169` keys only on `source_fingerprint`; the commit guard was deliberately removed (in-code `ponytail:` note names auto-sync HEAD drift) |
| D4-F4 | MINOR | Three per-load structures grow monotonically, never trimmed (`_drop_presentation_audible_start_beat`, `_arm_times`, `_v2_bloomed`) — load-cadence growth, ~tens-to-100 KB over a multi-hour set, no mask/loop consequence | `state_manager.py:599,:807`; `led_color_engine.py:356` | **CONFIRMED MINOR** (QASR4): no pop/clear/del path exists for any of the three (grep-proven); growth bounded by loads/distinct tracks, cannot stick a look or block the loop |
| D5 | — | AWR-170 review: NO findings at any severity — all six lenses SAFE with pinned-test evidence | 470/470 targeted tests green at `53a4513` | **ALL-CLEAR CONFIRMED** (QASR5): every SAFE lens attacked and held; all 8 suites independently re-run, 470 exact; all four dismissed edges re-derived benign (worst case = one missed breath, never stuck-dark); config parses re-verified; no refuter-discovered defects |

## Directed flake hunt (executive order, resolved)
The two `test_state_manager_drop_presentation` reds observed once in the USB lane
(`test_fire_enqueues_to_a_background_writer_not_the_tick_path`,
`test_arm_fire_learn_disarm_round_trip_via_real_event_dispatch`):
**load-dependent TEST flake, no runtime defect implicated, AWR-170 timeline attribution
not supported.** Recipe: full suite + 8×`yes` CPU load reproduced BOTH red together in
1 of 5 loaded full runs; never at pair×10 or file×6 scope (loaded or not), both cwd forms
green. Test 1 is starvation-margin by construction (1.0 s disk deadline on a 0.01 s
debounced background-writer thread, `tests/test_state_manager_drop_presentation.py:929-933`).
Test 2's traceback was not captured in 3 further loaded runs; both real occurrences failed
as a pair ⇒ shared environmental cause at suite scope. The production path (off-tick
background writer) got a clean tripwire bill across D3's 12,268-tick replay. Fix shape:
test-hygiene round (widen deadline / timing-independent setup), polish tier.

## Dimension summaries (each: what ran, what held)

### D1 — Regression matrix (finder claude/QASD1; refuter claude5/QASR1)
Kill-switch matrix F2×F4×scripted×tier-less×cache-less proven cell-by-cell IDENTICAL or
DIFFERS-OK at REVIEW vs PRE pins (config-off harnesses, AST byte-compare of the
preference predicate, tree-vs-tree diffs). Suite reconciliation exact at both pins: REVIEW
3676/6E/12skip/1xfail, PRE 3503/same-6-error-IDs, +173 collected = tonight's new tests all
green; 3716−3676 = 40 = exactly the three no-`.git` setUpClass-swallowed classes (8+28+4,
AST-counted). Zero tests deleted/weakened tonight. One finding (D1-F1, above). Refuter
re-ran every harness; no IDENTICAL cell collapsed.

### D2 — Edge cases (finder claude3/QASD2; refuter claude5/QASR2)
All 11 kickoff edge classes verdicted with runnable repros (32-check harness driving the
real engines): track change mid-window, seek both directions, deck swap, pause-at-threshold,
marker/cache-less, FEIN, load storms, mask-owner enumeration (one subagent leak candidate
REFUTED at the full call chain — `_clear_smart_rearm_state → clear_pending_blackout →
_release_all_masks`), tempo bend (windows beat-anchored), beatgrid recompute, AWR-138
re-entry × energy gate (stateless per-drop, no double-fire). 3 MINOR findings above.

### D3 — Live-scenario replay simulation (finder claude5/QASD3; refuter claude/QASR3)
Real recorded capture (19,204 rows) replayed through the actual push loop (12,268 ticks)
plus a synthetic 12-track 128–174 BPM set with mid-set pause / instant swap / tempo-bend
variants, F2+F4 ON, invariant TRIPWIRES asserted in-harness: 0 exceptions, 0 in-tick plan
computes, 0 blocking-I/O trips, ANLZ-before-TRACK_LOADED held, 23/23 windows closed,
owners empty at rest on every path except the one that produced D3-F1. Named honest gaps:
LED emphasis-ladder dispatch not driven end-to-end — **gap CLOSED by QASR3**: driven
end-to-end at the review pin (drop at 96, ladder rung 8 → `room_blackout` frame fired at
beat 88, held latched without re-fire, released exactly at the drop crossing → `room_drop`);
proven on the 8-rung, mechanism shared by 1/2/4/16 (same arm/clear path, different beats);
pre_dark arming needs an enabled Director (confirmed by code only); "full-scale law" does
not exist verbatim in `runtime_invariants.md` — nearest hard rule is the Output invariant
(:195-196), which D3-F1 violated. QASR3's clean-claim audit: every finder scenario re-ran
identically (12,268-tick replay, oracle 4/4, 23/23 windows, exposure regimes 1-tick/192-beat);
two honesty corrections logged — the R1 plan-tripwire pass is vacuous (that capture builds
no plans; the full-set counter is the load-bearing proof) and the MIDI "tripwire" claim was
overstated (Mock output sink is the actual safety; socket/subprocess tripwires are real).

### D4 — Stress (finder claude/QASD4; refuter TBD/QASR4)
Measured, not estimated (medians under noted ambient load): F2+F4 plan compute over 716
real cached v4 tracks — dense-path p50 2.9 ms / p95 5.7 ms / max 10.4 ms, on a per-load
daemon; push-loop consumption ≤ 5.4 µs/tick (0.11% of budget); a single load's plan compute
delays 1-2 ticks, within ambient jitter; the 16 s cache-miss extraction is GIL-releasing
(loop jitter unchanged during); F2 plan lifecycle leak-free over 400 loads × 2 decks
(F2TrackPlan pinned at 2, tracemalloc flat 33-42 KB); AWR-160 gate storm-proof (phantom
storm 0 emits/10 suppressed, ANLZ→TRACK order under interleave + rapid loads, single-writer
architecture — no cross-thread mutation). AWR-169 class sweep found 2 more instances
(D4-F1/F3) + 1 spawn-cap gap (D4-F2) + 3 untrimmed per-load structures (D4-F4). QASR4
re-ran the measurement harnesses (numbers reproduced equal-or-better on a quieter machine:
consume 5.40 µs, dense plan p50 2.2 ms, all 4 storm invariants), resolved the
accumulator-sweep placeholder (folded in; all 11 bounded-structure claims re-verified at
the pin), ran its own independent sweep of the hot dispatch files (two structures the
finder never named — both bounded), and confirmed all four findings at MINOR with
immaterial line-cite drift noted. No new defects.

### D5 — AWR-170 post-landing review (finder claude3/QASD5; refuter claude3/QASR5 fresh-context)
Pin `53a4513` (the shipping tree), scoped to the AWR-170 commit set (AWR-122 M1 files in
the same range excluded — separate review chain). All six lenses SAFE with evidence:
absent-knob = byte-identical no-op (pinned both directions); malformed per-tier chase
configs fail CLOSED (all-junk/list-valued/out-of-range variants); F2-off resolves
`standard` = the pre-170 int; every pre_chorus mask exit provably releases (level-triggered
release + 11 `_clear_smart_rearm_state` call sites + refcounted owner overlap with
breakdown — the fatal flag-cleared/mask-stuck shape structurally cannot occur); window
math safe at collapsed markers / track-start / marker-less / late-ANLZ / re-entry;
held-static duck AND restore pinned end-to-end (`test_state_manager_pack_driver.py:682-711`),
emergency > manual > tactical intact; 200 Hz adds are O(#segments) compares + a one-hop
`for_drop` on drop ticks only — no I/O, no recompute. 470/470 targeted tests green. Four
hunted-and-dismissed edges logged (resume-path flag staleness = exact breakdown parity,
misses a breath, never sticks dark; pause-inside-window holds like breakdown; back-to-back
choruses <4 beats = longer breath, pathological data only; NEUTRAL→standard is the
division picker's correct job separation from the energy gate). Manager settled its one
assumption read-only: live `smart_drop_mode = "blackout_mask"` — the pre-chorus feature is
fully active at morning start.

## Suite baseline accounting
Pin-tree (no `.git`) anchor: 3676 ran / 6 errors / 12 skipped / 1 xfail — all 6 errors are
the `export_soundswitch_pack._generator_commit` no-git family (3 setUpClass + 3 individual),
identical IDs at PRE pin. **Final independent quiet run at the FIXED head (`d634471`,
repo-root form): 3745 ran (= 3742 + AWR-171's 3 pinned tests) / 9F / 6 skipped / 1 xfail;
the AWR-169 pack byte-identity pair GREEN (no mid-run commit).** The 9 attribute fully, by
name: 5 of the registry's known-six (`absent_fixtures`, `stale_venue_sha`, `ddj_slots`,
`autoloop_capture`, `drop_slot_color_smoke_and_snap`); the sixth (`loader_ships_calibrated`)
is parent-dir-form-only — at repo root it is green while the two `test_smart_transitions`
env-flag tests go red instead (cwd-form asymmetry, consistent across all 6 repo-root runs
tonight, pre- and post-AWR-171); plus the patch_c/patch_d live-vs-tracked config tests
(expected while the applied mirror diverges live from example; patch_c's validate went
green mid-stream — a concurrent lane is editing that test file, visible as the one dirty
working-tree file). Zero reds attributable to tonight's reviewed surface or to AWR-171.

## Escalations + fix rounds
- D3-F1 escalated via `claude10.QASHOWCASE.blocked` at ~05:39; executive desk-verified;
  fix round authorized through the LED-manager chain and **LANDED as AWR-171**
  (`c0aafda` spec + registry, `250a8a9` code, ~05:46) — the ruled one-call release from
  `_enter_idle_no_audible`. Manager pre-spec sufficiency check delivered (pre_chorus mask
  NOT a sibling leak; the one-call release covers the defect class); QASR3 independently
  confirmed the fix (finder's repro CLEAN on fixed tree, present at real HEAD, pure
  in-memory + idempotent, no push-loop I/O added).
- Flake hunt: resolved as test-flake (above); escalation note appended, no second blocker.

## Harness-integrity note (transparency)
The AWR-171 fix was applied into the QA program's frozen `qa_pin` tree mid-program
(`state_manager.py` only, the exact 6-line fix — caught by QASR3 via mtime + diff vs
`git show b2af2bf:state_manager.py`). Impact contained: all pre-05:46 verifications used
the pure pin; QASR1's `_on_track_loaded` compare was content-based (unaffected by the
line-shift); every AWR-170-surface file stayed pristine; QASR3 re-proved the leak against
the untouched `qa_pin170` tree instead. No verdict in this report rests on the drifted file.

## Method + evidence trail
Frozen trees: `qa_pin` (b2af2bf), `qa_prepin` (f4bfd06), `qa_pin170` (53a4513) under the
session scratchpad; finder findings + refuter verdicts + repro harnesses at
`<scratchpad>/findings/` and `<scratchpad>/lane_scratch/QAS*/`; escalation note at
`<scratchpad>/escalations/d3f1_escalation.md`. All lanes ran read-only against the repo
(git history reads only), example configs, and test seams; live config was opened
read-only twice (Director enable check). No bridge/pad/device/network contact by any lane.
