---
doc_status: current
truth_level: implementation spec skeleton (banked; NOT authorized to implement)
last_verified_commit: f95a53b
last_verified_date: 2026-07-09
validation_scope: >
  Part A–E Codex spec skeleton for F3 blend (AWR-175), authored from
  docs/architecture/f3_blend_design.md the same day. Every Part A claim was verified at
  f95a53b. IMPLEMENTATION IS NOT AUTHORIZED: this spec activates only after the operator
  live-gates F2 (AWR-163) and F4 (AWR-164) and re-verification of every file:line below
  at the then-current HEAD. planned / hardware-unvalidated.
---

# Codex Implementation Spec — F3 Blend (LIGHTING ENGINE v2 Feature 3) — SKELETON

> **GATE: DO NOT IMPLEMENT.** Banked design artifact (AWR-175). Preconditions to
> activation: (1) operator live-gates F2/F4; (2) an operator instruction explicitly
> authorizes F3 implementation; (3) the implementer re-verifies every Part A citation at
> the current HEAD — this skeleton was verified at `f95a53b` and the LED dispatch surface
> is under active change (AWR-177 white-share consumer was spec'd the same afternoon).
> Design authority: `docs/architecture/f3_blend_design.md` (D§n references below);
> operator contract: `lighting_engine_v2_authority.md` §7.

## Part A — Context & Root Cause (verified; read, do not implement)

- [confirmed] Today the room follows exactly one deck. The active-deck resolver
  (`active_deck_resolver.py:59-215`) picks a leader from playing + upfader label +
  LOW label; on a 1↔2 flip the F1 color engine soft-flips identity
  (`led_color_engine.py:1068-1084`, `_v2_pending_flip_fade` over `soft_flip_beats`).
  The transition between two tracks is otherwise invisible — no runtime object knows a
  blend is in progress. That is the gap F3 fills (D§0).
- [confirmed] The mixer signal already flows: `RBStateReader._tick_mixer`
  (`rb_state_reader.py:534-596`) publishes a `MixerAuthoritySnapshot` (deck 1/2
  `upfader_norm` 0–1, `low_norm` 0–1, labels) per reader tick; `StateManager` stores it
  and reruns the resolver (`state_manager.py:1401-1405`). Measured live rate ≈ 29.5
  snapshots/s (2026-07-09 session recording). **F3 needs zero reader work.**
- [confirmed] The isolation pattern to copy is CFX (AWR-173): store-only consumption, no
  authority coupling, inert-by-construction (`rb_state_reader.py:598-618`,
  `state_manager.py:1407-1412`).
- [confirmed] F1 identities install lazily on first *active* dispatch
  (`led_color_engine.py:1077-1078`, `_v2_install_default` inside the track-key-change
  branch) — the incoming deck's palette does not exist pre-flip today. F3's painter
  needs it earlier (Part B Task 3).
- [confirmed] F2 plans attach per (deck, load_gen) at load (`state_manager.py:279,
  1556-1559`) and the shared pre-drop transition window is plan-driven
  (`state_manager.py:5006-5007` → `lighting_moments_v2.transition_window_for`,
  `lighting_moments_v2.py:811-827`).
- [confirmed] Per-frame slot-color interpolation exists (`resolve_fade`,
  `govee_frame_renderer.py:74-97`) and the color engine has a claims arbiter
  (`Claim`/`RANKS`, `led_color_engine.py:1095-1097`).
- [assumed — re-verify at activation] The `_v2_resolve_color` path
  (`led_color_engine.py:1101+`) remains the single color conduit for engine-sourced
  looks; AWR-177 (white-share consumer) may have moved lines.
- [unknown] Whether the F2 pre-drop window machine tolerates opening mid-window
  (design case C, D§6). Part B Task 7 makes it explicit; the implementer must first read
  the then-current window code and report which behavior already holds.

## Part B — Tasks (implement exactly, in order; one commit per task)

### Absolute Rules
- **Out of scope:** `rb_state_reader.py`, `rb_offsets.py` (no new reads, no new events);
  the active-deck resolver (F3 NEVER influences `active_deck`); laser modules
  (`laser_director.py`, `laser_executor.py` — D§5: F3 does not drive lasers);
  SoundSwitch output; drop presentation ladder; scripted rendering; F2's
  family/tier/darkness decisions.
- **Behavior that must not change:** F3 disabled (default) ⇒ byte-identical rendering
  (same bar as F4's proof, `tests/test_lighting_moments_v2_f4.py` precedent); every
  existing mask/manual precedence; F1 soft flip on non-blend flips; scripted
  sovereignty; `_enter_idle_no_audible` outcomes.
- **Error handling:** invalid/stale mixer snapshot is a NORMAL state, not an exception —
  fail toward today per D§8 (freeze → release to leader identity); never a broad
  try/except around the painter; a malformed config block fails closed to F3-off with
  one WARNING at load.
- **Dirty worktree:** other lanes are active in this checkout; never revert unrelated
  changes; commit by explicit paths only; no destructive git.

### Task 1 — `f3_blend.py` (NEW, pure — the state machine)
Pure module in the `active_deck_resolver.py` mold: frozen dataclasses + one advance
function, no I/O, no clock reads (caller passes `now`/beat).
- `F3Config` (from Task 2), `F3State` (state enum, presence step, β smoothed, leader,
  timers), `F3Decision` (state, β raw+step, paint directive: accent weight, base morph
  fraction or trade step, resolve-claim request, reason string).
- `presence(up_norm, low_norm, playing, cfg)` and
  `advance_f3(state, snapshot, active_deck, deck_playing, scripted_pair, now, beat, cfg)
  -> (F3State, F3Decision)` implementing D§2–§3 exactly: `LOW_FLOOR=0.35`,
  `BETA_ENTER=0.10`/`ENTER_BEATS=4`, `BETA_MID=0.5`, `BETA_COMMIT=0.85`,
  `SLAM_DELTA=0.5`, 8 bar-quantized steps, ABANDON release staircase, slam bypass,
  leader-swap-in-place on mid-blend flip (β′ = 1 − β), stale-snapshot fail path
  (D§8 grace then release). All constants module-level named, config-overridable.
- Every decision carries a `reason` string (D§10 observability contract).

### Task 2 — `led_config.py` + `config/led_look_director.example.json`: `/f3` block
`F3Config` parsed like the existing `F4Config` (AWR-164 precedent): `enabled`
(default **false**), `mode` (`blend`|`handover`, default `blend`), `hold_tightness`
(default 0.7), and the Task 1 constants. Malformed block ⇒ disabled + one WARNING.
Update the example config; **live config untouched** (ships OFF).

### Task 3 — incoming-deck identity pre-derivation (F1-side, small)
At TRACK_LOADED, derive+store the F1 identity for the loaded deck even while inactive
(identity is a pure function of the track — authority §3 permanence). Reuse
`_v2_install_default`'s derivation; key by (deck, load_gen) exactly as
`_v2_load_gen_by_deck` does; the active-dispatch path must find it already installed and
behave identically (assert via the byte-identity test). No repaint of the live room.

### Task 4 — `state_manager.py` wiring
In the push tick, after the resolver output is settled: build `advance_f3` inputs from
the stored `_mixer_snapshot` + `active_deck` + per-deck playing/scripted, store the
decision. Pure math only — the push loop gains no blocking I/O (AGENTS.md §6).
**Pending-state guard (checklist §3):** the F3 decision must coexist with, and be
checked against, ALL of: `_led_hold_active` (F3 paints nothing while the hold runs),
`_led_cfx_sweep`/`CfxEnvState` (AWR-173 sweep owns its dim envelope; F3 freezes painting
while a sweep is active — both are color-adjacent overlays and must never compose),
drop-presentation windows (freeze, D§6 case A/F), and the smart-drop blackout key.
**Mode-transition cleanup (checklist §4):** F3 state resets in `_enter_idle_no_audible`
(`state_manager.py:2137+`), on TRACK_LOADED for either deck (`state_manager.py:2210+`),
on scripted-pair detection, and on the master v1/v2 or F3-off flip. Enumerate each path
in the implementation commit message.

### Task 5 — `led_color_engine.py` painting
Apply the F3 paint directive as a slot-color transform where engine colors resolve
(the `_v2_resolve_color` conduit): accent ownership steps (slots 3–4), base
glide/trade past midpoint (slots 0–2, `is_hard_pivot` distance decides glide vs trade),
hold-tightness scaling for same-zone pairs, COMMIT resolve as a rank-4 claim through the
existing `Claim`/`RANKS` machinery (skip-not-queue — reuse the existing claim-overlap
logic, do not invent a second arbiter). Slot 5 (white) never touched (D§4.7). Freeze
rule: while any rank 0–3 claim is active, the painter emits the frozen pre-claim
transform.

### Task 6 — observability
Status surface: `f3_state`, `blend_beta` (raw + step), per-deck presence, `f3_reason`.
INFO logs on state transitions only; everything per-snapshot at DEBUG (repo log-style
rule). Extend `runtime_status.py` command surface per its contract if a new status key
is exposed (check `docs/agents/change_contracts.yml` `runtime_commands`).

### Task 7 — F2 window mid-open tolerance (design case C)
Read the then-current pre-drop window machine first. Required behavior: an active-deck
flip landing inside the incoming plan's darkness window opens the REMAINDER of the
window (elapsed portion skipped, never stretched); the drop cue itself is
marker-authoritative and unaffected. If the code already behaves this way, prove it with
a test and change nothing.

## Part C — Invariants That MUST Still Hold (live safety)

- Push loop gains **no** blocking network/socket/MIDI/filesystem/subprocess I/O
  (AGENTS.md §6); F3 is pure math over an already-stored snapshot.
- F3 never writes `active_deck`, `DeckState`, `lighting_mode`, or any `BridgeEvent`;
  `StateManager` remains the only `DeckState` writer; events stay immutable.
- Emergency blackout / manual holds / LED mute / static overrides beat F3 absolutely
  (law 2); a held manual look survives the entire blend; blackout ownership untouched
  (`laser_blackout_authority.md`).
- F3 owns no intensity except the rank-4 resolve bloom (brighten-only): **no new
  dark-room failure mode is possible by construction.**
- Scripted pair ⇒ F3 paints nothing (authority §11 sovereignty).
- F3-off ⇒ byte-identical rendering; F1-off + F3-on ⇒ soft-flip collapse
  (kill-matrix dependency rule 1, `LIGHTING_ENGINE_V2_DESIGN.md:593-594`).
- Drop cues render full-scale in whatever colors stand (law 5); F3 never scales them.
- After any bridge restart: exactly one process (`pgrep -f rb_ss_bridge_v2 | wc -l` = 1).

## Part D — Tests

Pure-function seams first (checklist §7) — all of these run with no files, no clock,
no runtime:
- `tests/test_f3_blend.py`: presence formula edges (fader-top/LOW-cut, non-playing ⇒ 0,
  boost cap); β relative share + <0.05 sum guard; full state-table walk
  (enter→blend→mid→commit; abandon + re-entry mid-release; slam bypass; chop = repeated
  slams; mid-blend leader flip with β re-expression; flip-without-blend stays SETTLED;
  stale-snapshot grace→release; scripted stand-down; idle reset).
- Freeze semantics: a rank 1–3 claim active ⇒ paint directive frozen, state still
  advancing underneath.
- Config: default-off, malformed-block fail-closed, mode/hold_tightness parsing.
- Byte-identity: F3 disabled ⇒ identical dispatch/color output on a recorded scenario
  (the `test_lighting_moments_v2_f4.py` idiom), including Task 3's pre-derivation being
  invisible.
- Task 7's mid-window-open test.
- Replay evidence (non-gating): `session_replayer.py` over
  `local/sessions/f3_live_feedback_20260709.jsonl` episodes as a smoke input.

## Part E — Acceptance (definition of done)

- [ ] Contract first: extend `docs/agents/change_contracts.yml` (`led_govee` +
      `config_schema`; add `f3_blend.py` to the module lists) BEFORE code lands.
- [ ] Every `docs_update` doc updated: `docs/subsystems/led_govee.md`,
      `docs/subsystems/config.md`, `docs/architecture/f3_blend_design.md` (flip design
      claims to implemented where true), registry row AWR-175 status,
      `docs/validation/software_test_inventory.md`.
- [ ] `python3 tools/check_docs_metadata.py && python3 tools/check_agent_contracts.py &&
      python3 tools/check_docs_drift.py` green; `python3 -m unittest discover tests`
      green (note: CI runs Python 3.11 from the parent dir — no 3.14-only syntax).
- [ ] Status language: implemented / software-tested / hardware-unvalidated only.
- [ ] Ships **OFF**: live config gains no `/f3` keys; activation is an operator action.
- [ ] Part B task-by-task commits, explicit paths only.

## When You Finish
Report: changed files; tests/checks run with output; which Part A [assumed]/[unknown]
items were resolved and how; the Task 4 cleanup-path enumeration. Then a plain-language
operator summary: what the room will do differently once he turns `/f3.enabled` on
(and that until then nothing changes), the two runtime toggles he owns (mode,
hold-tightness), the D§11 taste list (T1–T6) as his desk agenda, and rollback = flip
`enabled:false` (no restart needed; next look boundary).

## Adversarial self-review (checklist §9 — attack recorded at authoring)
- *Worst credible failure:* the painter keeps repainting during a pre-drop blackout ⇒
  color crawls under darkness, violating single-axis. Prevented structurally: Task 5's
  freeze rule keys on claim rank, tested in Part D, and the painter has no intensity
  authority regardless.
- *Second:* stale mixer offsets after an RB upgrade ⇒ β frozen mid-blend forever.
  Prevented: D§8 grace-then-release path is part of the Task 1 state machine (not a
  wrapper), with its own test row; end state is F1-only behavior.
- *Third:* two overlays composing (F3 paint + CFX sweep dim) into an unreviewed look.
  Prevented: Task 4's pending-state guard names `_led_cfx_sweep` explicitly — sweep
  active ⇒ F3 frozen. Both features ship OFF, so the composition is also operator-gated
  twice.
