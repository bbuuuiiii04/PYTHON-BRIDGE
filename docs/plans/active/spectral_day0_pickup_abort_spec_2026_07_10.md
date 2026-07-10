---
doc_status: current
truth_level: implementation spec (AWR-199, spectral refactor owner seat)
last_verified_commit: d1ad03b
last_verified_date: 2026-07-10
validation_scope: >
  DAY-0 interim guard for the SOL2-confirmed darkness-pickup hazard (deep sub-void
  rung keeps the room dark through an audible pickup when the dip ended beats before
  the drop). All Part A claims desk-verified 2026-07-10 ~01:2x by the spectral owner
  seat: synthetic repro through the real planner + full-library sweep (706 v4-backed
  tracks, 4163 drops, 93 rung-0b firings) + real-cache Utopia pin measurements.
  Staged only; nothing here restarts or contacts the running bridge.
---

# Codex Implementation Spec — AWR-199 deep-sub-void pickup abort (day-0 interim guard)

Implementer: Fable/xhigh tmux lane (`spectralb`). Scope is EXACT. This is a bounded
interim guard; the full fix (approach-shape classifier) is stage 2 of AWR-195 and is
NOT this task.

## Part A — Context & Root Cause (verified; read, do not implement)

**The hazard [confirmed, reproduced].** `lighting_moments_v2.py` rung 0b (AWR-184
deep-sub-void blackout, lines 508–533 at `d1ad03b`) returns `abort_at=None`. Every
other quantized blackout branch passes its window through `_abort()` (the
music-came-back early release, line 422); rung 0b suppresses it. Combined with two
of its own properties this darkens audible music:

1. `tolerant_scan` (line 342) accepts a sub-gone beat anywhere in `[D-4, D-1]`
   (`PICKUP_TOLERANCE = 4`), so the deep-void run may END up to 3 beats before the
   drop with the sub (music) back for the remaining beats.
2. The window is anchored at the drop — `(drop - beats, drop)` with
   `beats = _round_up_rung(deep)` — so those returned-music beats sit INSIDE the
   planned dark window, and with `abort_at=None` nothing releases them.

Reproduced via the pure planner at my desk (synthetic v4, drop 48, deep run 42–44
ending at D-4, pickup 45–47 audible): plan = `blackout 4 window (44,48)
abort_at=None` — three audible pickup beats planned dark. A 6-beat variant plans
`blackout 8 window (40,48)` with three audible beats dark. This matches the SOL2
panel repro (`docs/research/sol_panel_code_review_2026_07_10.md`).

**The second SOL2 leg — growl `min()` over the run — is measured OUT OF SCOPE
[confirmed].** A single dark growl beat anywhere in the run passes the
Caramelle-discriminator gate (line 523). I swept all 706 v4-backed tracks: a
growl-dark-at-tail gate at the existing 5.0 threshold would flip **52 of 93**
current rung-0b firings, including breaking the OMG b400 operator pin ("1 bar
blackout is perfect", growl tail 7.0) and endangering the House x Pressure bo16 pin
(growl tail 6.5). The B1 review batch cleared the current firing class by ear
(104 firings, "NO AWR-186" ruling). Any threshold-shaped growl-gate change breaks
more operator-cleared behavior than it fixes; the false positive it would fix
(Radiohead b383, B2-4 pin) is a stage-2 approach-shape target with both-side pins
banked. Therefore: **the growl gate does not change in this round.**

**The guard boundary comes from the operator's own verdicts [confirmed].**
Void-end distance among today's 93 firings: `{gap 0: 43, gap 1: 45, gap 2: 5}`
(gap = beats between the void's last beat and `drop-1`; `tolerant_scan` caps it
at 3). The operator has explicitly approved darkness over 1-beat pickups (Utopia
b384 lone transient, "1 bar blackout" exact) AND over 2-beat pickups (TOXIC b159
"blackout is perfect"; OMG b400 "1 bar blackout is perfect" — both gap-2 with the
sub back for the final two beats). A 2-consecutive-present release rule would
therefore override two operator-verdicted windows — rejected. The gap-3 cell
(3 returned-music beats dark) is the one REACHABLE cell no verdict covers, and it
is exactly the SOL2 repro. **Rule: release only when the pickup run is >= 3
beats.** Library engagements today: ZERO — the guard is prophylactic, closing the
reachable hazard cell. It matters live because marker edits move drops: SOL's
measured ±1-beat marker perturbation flips darkness answers on 23% of markers, and
a 1-beat drop shift turns any of today's five gap-2 firings into gap-3.

**Frozen pins hold [confirmed, measured on the real cache].**
- Utopia b192: deep run ends `e=190`, beat 191 is a LONE present transient
  (sub 5.3) — a single beat cannot form a present-pair, so `abort_at` stays `None`;
  decision byte-identical (`blackout 8 (184,192)`).
- Utopia b384: `e=382`, lone transient at 383 (sub 13.7) → `None`;
  `blackout 4 (380,384)` byte-identical.
- The consumer path needs NO change: `transition_release_for` (line 956) already
  converts `blackout` + `abort_at` into the early-release beats; balloon/dip/snap
  and `abort_at=None` paths are untouched.

Measured window values for the test fixtures (real cache, current grid):
- b192 window beats 40..47 of the fixture: sub `[12.8, -28.7, -28.2, -25.1, -25.7,
  -27.6, -28.1, 5.3]`, growl `[20.6, 17.7, 14.7, 11.8, 7.8, -4.3, -1.7, 5.7]`.
- b384 window beats 44..47: sub `[-4.9, -10.9, -16.7, 13.7]`,
  growl `[3.3, -1.5, -4.4, -3.1]`.

## Part B — Tasks (implement exactly, in order)

### Absolute Rules
- Touch ONLY: `lighting_moments_v2.py`, `tests/test_lighting_moments_v2.py`, and the
  Part E docs. NOTHING else.
- FROZEN, do not change: every named constant (`SUB_VOID_DB`, `GROWL_DARK_DB`,
  `VOID_MIN_BEATS`, `PICKUP_TOLERANCE`, all others), `tolerant_scan`, `_abort`,
  `_round_up_rung`, the growl `min()` gate, rungs H/1/2, the stop hoist (AWR-185),
  the balloon split, `transition_window_for`, `transition_release_for`.
- No config writes, no cache writes, no process contact, no bridge restart.
- Commit by explicit paths only. Do not create branches.
- Error handling: none needed — the helper is pure over in-memory lists; do not add
  try/except anywhere.

### Task 1 — `lighting_moments_v2.py`: pickup-region abort on rung 0b
Add near `_abort` (module level):

```python
# AWR-199 interim guard (day-0, SOL2-confirmed hazard): the deep-sub-void rung's
# round-up window is drop-anchored, but tolerant_scan lets the void END up to
# 3 beats before the drop — those returned-music pickup beats were planned dark
# with no release. The release boundary is operator-verdicted, not invented:
# 1-beat pickups stay dark (Utopia b384 "1 bar blackout" counts its lone
# transient), 2-beat pickups stay dark (TOXIC b159 / OMG b400 "perfect" verdicts
# are gap-2 windows), so ONLY a >=3-beat returned-music run — the one reachable
# shape no verdict covers, and exactly the SOL2 repro — releases, at the first
# returned beat. The round-up padding BEFORE the void always stays dark (the
# b192 2-bar label counts from the musical cut). Stage 2 (AWR-195) replaces
# this with the approach-shape classifier; the growl min() gate is measured out
# of scope here (a tail gate flips 52/93 library firings incl. an operator pin
# — see the AWR-199 spec).
PICKUP_ABORT_ENV = "RBSS_F2_VOID_PICKUP_ABORT"
_PICKUP_ABORT_ON = os.environ.get(PICKUP_ABORT_ENV, "1") != "0"


def _pickup_abort(sub: Sequence[float], e: int, drop: int) -> Optional[int]:
    """Release beat for a deep-sub-void window whose void ended >= 3 beats
    before the drop with the floor audibly back the whole way, else None.
    AWR-199; boundary per the operator gap-0/1/2 verdicts."""
    if drop - 1 - e >= 3 and all(
            sub[b] >= FLOOR_PRESENT_DB for b in range(e + 1, drop)):
        return e + 1
    return None
```

Add `import os` to the module imports (it currently has none).

In `darkness_ladder` rung 0b, replace the return (lines 524–533) so the decision
carries the abort:

```python
        if growl_min < GROWL_DARK_DB:
            beats = _round_up_rung(deep)
            abort_at = _pickup_abort(sub, e, drop) if _PICKUP_ABORT_ON else None
            return DarknessDecision(
                "blackout", beats, (drop - beats, drop), abort_at,
                {"raw_gap": raw_gap, "bass_duty": round(bass_duty, 3),
                 "perc_build": round(perc_build, 3), "grade": grade, "stop": False,
                 "sub_void": deep, "growl_min": round(growl_min, 2),
                 "growl_tail": round(growl[e], 2)},
                f"deep-sub-void blackout {beats}: sub voided {deep} beats "
                f"(< {SUB_VOID_DB} dB) with the growl band dark "
                f"(min {growl_min:.1f} < {GROWL_DARK_DB}) into the drop"
                + (f"; pickup abort@{abort_at}" if abort_at is not None else ""))
```

The ONLY behavioral deltas vs today: `abort_at` may be set (early release on
returned music), the reason string gains the abort suffix when set, and
`cap_inputs` gains the `growl_tail` observability field (no consumer reads it).

### Task 2 — `tests/test_lighting_moments_v2.py`: pin the guard
Extend `TestDeepSubVoidBlackout` (follow its existing synthetic-builder style) with:

1. `test_pickup_ended_dip_releases_early` — n=64, drop=48; sub 20.0 everywhere
   except beats 39–44 at −15.0 (deep run 6 ending at D-4 → 3-beat pickup);
   growl 18.0 everywhere except beat 44 at −4.0; perc_full 0.2; full_db 15.0 on
   present beats / 5.0 on void beats. Assert: kind `blackout`, beats 8,
   `abort_at == 45`, reason contains `pickup abort@45`, and
   `cap_inputs["growl_tail"] == -4.0`.
2. `test_two_beat_pickup_stays_dark` — same recipe, deep run beats 40–45 at −15.0
   with growl −4.0 at beat 45 (void ends at D-3 → 2-beat pickup). Assert
   `abort_at is None` (the TOXIC b159 / OMG b400 operator-verdicted shape).
3. `test_lone_pickup_transient_stays_dark` — deep run beats 44–46 at −15.0 with
   growl −4.0 there (void ends at D-2, single present beat 47). Assert
   `abort_at is None` (the UT-6 / Utopia-b384 semantics).
3b. `test_void_into_drop_no_abort` — deep run 42–47 (ends at D-1), growl −4.0
   across it. Assert `abort_at is None`.
4. `test_kill_switch_restores_none` — recipe from (1); patch
   `lighting_moments_v2._PICKUP_ABORT_ON` to `False`
   (`unittest.mock.patch.object`). Assert `abort_at is None` and the reason has no
   abort suffix.
5. `test_utopia_pin_fixtures_hold` — two fixtures with the MEASURED Part A window
   values placed at beats 40..47 (b192 recipe) and 44..47 (b384 recipe) of an
   n=64/drop=48 synthetic (pad all other beats sub 20.0 / growl 18.0 / perc 0.2).
   Assert b192-recipe → `blackout 8, abort_at None`; b384-recipe →
   `blackout 4, abort_at None`. These pin the real-cache shapes into the suite.

Extend `TestTransitionRelease` with one case: a plan whose drop decision is a
deep-sub-void blackout carrying `abort_at` → `transition_release_for` returns
`drop_beat - abort_at`.

## Part C — Invariants That MUST Still Hold
- **Fail-open beats fail-dark:** this change only ever RELEASES darkness earlier;
  no path gains longer or new darkness. Verify by reading the diff: the only new
  assignment is `abort_at`.
- Utopia b192/b384 decisions byte-identical except nothing (abort stays None
  there) — the frozen AWR-184 pins.
- Balloon / stop / true-silence / dip / snap / rung-2 behavior unchanged.
- The module stays pure at call time (env read at import only); no I/O added to
  any function; the 200 Hz push loop is untouched (this code runs at plan build).
- Markers stay timing-authoritative; no timing shifts anywhere.

## Part D — Tests
Part B Task 2 is the test work. Run scoped:
`python3 -m unittest tests.test_lighting_moments_v2` — must be green.
Then `python3 -m unittest discover tests` — reconcile reds BY NAME against the
named environmental baseline (five env reds repo-root; see
`docs/agents/codex_resume_state_2026_07_09.md`). Do not chase known flappers;
isolate-if-green.

## Part E — Acceptance (definition of done)
- [ ] Task 1 diff matches the spec shape (no drive-by edits, constants untouched).
- [ ] All Task 2 tests green; module suite green; discover reconciled by name.
- [ ] Docs: `docs/status/active_work_registry.md` AWR-199 row updated to
  BUILT/software-tested with commit ids; `docs/subsystems/led_govee.md` darkness
  section gains one sentence (deep-sub-void rung now carries the pickup abort +
  env kill-switch name); `docs/validation/software_test_inventory.md` gains the
  new test names. No other docs (matrices do not describe rung-level behavior —
  verified by the spec author; if your grep finds rung-0b named elsewhere, update
  that doc too and say so).
- [ ] `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`,
  `python3 tools/check_docs_drift.py` all green.
- [ ] Commits by explicit paths, message prefixed `AWR-199:`.
- [ ] STAGED ONLY: no process contact; the running bridge keeps old behavior until
  the operator's morning restart.

## When You Finish
Report: changed files, commit ids, test counts (module + discover with red names),
the exact diff of rung 0b, and a plain-language line for the operator ("when a
musical dip ends three or more beats before the drop and the music audibly comes
back, the room now re-lights on the return instead of staying dark into the drop;
every blackout you have already approved — including the two-beat-pickup ones —
behaves exactly as before; zero tracks in today's library change; one env flag
`RBSS_F2_VOID_PICKUP_ABORT=0` restores the old behavior"). Evidence class:
SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
