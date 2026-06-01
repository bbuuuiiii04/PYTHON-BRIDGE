# Codex prompt: rotate role-bank looks across tracks (kill per-track primary repeat)

**Branch:** `laser-drop-rotation-seed` (off `smart-drop-post-drop-features`)
**Authoring split:** Claude analysis; **Codex implements.**
**Risk:** Laser Director runs **live** (`enabled=true, dry_run=false`). Contained
change to `laser_executor.py` only. **Config-safe** — no schema change; existing
banks (e.g. the 5-look house `drop_bank`) are untouched.

## Problem (confirmed)
Every track fires the same drop look (`bank[0]`, the "primary") even though
`drop_bank` has 5 scenes. Root cause: `reset_runtime_state()` zeroes
`_role_cursors` (`laser_executor.py:79`) and is called on **every track load,
deck switch, and stop** (`state_manager.py:963, 994, 1050, 2258`). The bank is read
`bank[cursor % len]`, so cursor=0 → `bank[0]` = primary. Since you load a new track
per song (cursor resets) and most tracks have one main drop, the rotation never
advances past index 0. The other 4 looks only appear on multiple drops within one
uninterrupted track. This applies to **all** auto roles
(`_AUTO_ROLES = phrase, buildup, drop, post_drop, breakdown`).

## Fix — persistent round-robin + randomized start
1. **Stop zeroing `_role_cursors` on track-load / deck-switch / stop.** Add a
   parameter to `reset_runtime_state`, e.g. `reset_cursors: bool = False`. Only the
   **personality-change** path (`set_personality`, `laser_executor.py:62`) passes
   `reset_cursors=True`; the other four callers keep the default (False) so the
   cursor **persists** across tracks/deck-switches/stops. Continue resetting
   `_role_active_scene`, `_last_role`, cooldowns, etc. on those events as today —
   only the cursor persists.
2. **Randomize the start on personality load.** When cursors *are* reset (personality
   change), seed each role's cursor to a random index within that role's bank:
   `self._role_cursors[role] = self._rng.randrange(len(bank))` (guard empty bank →
   0). This removes the last primary bias (otherwise the first drop of every session
   / after a personality switch is always `bank[0]`).
3. **Inject the RNG for deterministic tests.** Add an optional `rng: random.Random`
   constructor arg (default `random.Random()`); seed it in tests so round-robin
   order is assertable. Do not use the global `random` directly.

Net behavior: drop looks cycle evenly across tracks (`drop_1→…→drop_5→drop_1…`),
never repeat back-to-back, and the cycle's starting look varies per session. The
`primary`/`*_scene` field stays but becomes cosmetic (just `bank[0]`'s label) — no
config migration, no Pad UI change.

## Optional (only if the fixed cycle order ever feels scripted) — shuffle-bag
Instead of a monotonic cursor, keep a shuffled permutation of the bank per role;
hand out looks in that order; when exhausted, reshuffle (avoid making the new first
equal the previous last, to prevent a boundary repeat). Even + no-repeat like
round-robin, but order varies each cycle. Implement behind the same persistence
rule. Leave this OUT of the first pass unless requested; note it in a comment.

## Tests (`tests/test_laser_executor*.py` / `tests/test_laser_config_ops.py` area)
- **Persists across track load:** with a 5-entry `drop_bank`, simulate
  track-load/deck-switch resets between drop entries → assert successive drops return
  `bank[0], bank[1], …` (cursor not reset), seeded RNG for determinism.
- **No reset on stop/deck-switch:** cursor survives those events.
- **Personality change reseeds:** `set_personality` reseeds cursors (random with
  injected RNG → deterministic assert), and a different personality starts fresh.
- **Single-entry bank unchanged:** roles with one look (buildup/breakdown today) still
  return that look every time (cursor % 1 == 0).
- Keep existing executor/round-robin tests green (some may need the injected RNG /
  updated expectations now that cursors persist).

## Out of scope
Removing the `primary`/`*_scene` field or the Pad "Set Primary" action (deferred
cleanup); any config-schema change; LaserDirector policy changes.

## Live validation
Play several tracks in one set: confirm consecutive drops use **different** looks and
all 5 appear over time, with no back-to-back repeats; a personality switch starts a
fresh (randomized) rotation; single-look roles (buildup/breakdown) behave as before.

## Housekeeping (not code — operator step)
Delete the stale duplicate config `~/Library/Application Support/RBSS Bridge/
laser_director.json` (the bridge loads the repo `config/laser_director.json` via
`_DEFAULT_CONFIG_PATH`; the App Support copy is unused and only causes confusion).
