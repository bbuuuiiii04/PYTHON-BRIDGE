# Codex prompt: fix Verify false-fail on multi-entry banks (deterministic cursor in validation path)

**Branch:** `laser-drop-rotation-seed` (follow-up to the role-bank rotation change).
**Authoring split:** Claude review; **Codex implements.**
**Severity:** BLOCKER for this branch. Smallest safe fix (reviewer option i).

## Problem
The rotation change made `LaserSceneExecutor` seed `_role_cursors` randomly. But the
config verifier constructs an executor with **no `rng`** and then compares the emitted
MIDI note against each role's **primary** scene:
- `tools/laser_config_ops.py:1326` — `ex = LaserSceneExecutor(config=cfg, midi_output=midi, personality=personality)` (random cursor)
- `tools/laser_config_ops.py:1387-1388` — `expect_note = scene.midi.note` (`scene = personality.<role>_scene`) then `if int(sent.note) != int(expect_note): <fail>`

With a multi-entry bank (e.g. house: 32 grooves, 5 drops) the random start makes the
executor emit a non-primary bank look, so Verify reports "expected note X, got Y" on a
valid config. Live rotation is correct; this is a **validation-only** false failure, but
it ships on this branch and misleads during setup.

(Note: the second executor in that function, `tools/laser_config_ops.py:1438` `ex2`, is
the cooldown check — its pass/fail is `len(calls)==1 and last_error=="role_cooldown_blocked"`,
note-agnostic, so it is NOT broken by the random cursor. Fixing it too is only for
determinism/consistency, not correctness.)

## Fix (option i — keep randomization out of the validation path)
Make the verifier run with a deterministic cursor at index 0 (the primary), so the
existing primary-note comparison holds. Keep live randomization intact.

1. `laser_executor.py`:
   - Add constructor param `randomize_cursors: bool = True`; store `self._randomize_cursors`.
   - In `_seed_role_cursors()` (`laser_executor.py:329`): when `self._randomize_cursors`
     is False, return `{role: 0 for role in _AUTO_ROLES}`; otherwise keep the
     `randrange(len(bank))` behavior.
   - `set_personality` → `reset_runtime_state(reset_cursors=True)` reseed path must also
     respect the flag (it calls `_seed_role_cursors`, so this is automatic — just verify).
2. `tools/laser_config_ops.py`: construct both verifier executors with
   `randomize_cursors=False` — line `1326` (`ex`) and line `1438` (`ex2`).

Net: Verify deterministically exercises each role's primary mapping (cursor 0 → bank[0]
→ `*_scene`), so valid multi-entry configs pass. Live executors keep
`randomize_cursors=True` (default), so rotation behavior is unchanged.

## Tests
- Add a verifier test: a personality with a **multi-entry** bank (e.g. `drop_bank` of
  3-5 scenes, distinct MIDI notes) passes `verify_mappings_runtime` with **no** false
  "expected note" failure (run it a few times / with the default RNG to prove it's
  deterministic, not luck).
- Keep all existing `tests/` green (`1288 passed` baseline). The executor-rotation tests
  that inject `random.Random(...)` are unaffected.

## Out of scope
- Option ii (rewriting the verifier to map the emitted note back to a bank member) —
  larger, changes verifier semantics. Not needed.
- Config schema, Laser Pad UI, LaserDirector policy, removing the `primary`/`*_scene`
  field. None of these.

## Commit hygiene
Touched files for this fix: `laser_executor.py`, `tools/laser_config_ops.py`, and the
new verifier test. Do **not** commit `spec/*.npy` or other unrelated generated/untracked
files. `ss_memory_probe.py` is unrelated — leave it.

## Verification
```
python3 -m pytest tests/ -q          # expect prior pass count + the new test
python3 -m py_compile laser_executor.py tools/laser_config_ops.py
git diff --check
```
Plus: open the Laser Pad, run **Verify** against the house personality (5-look drop
bank) and confirm it reports OK, not a spurious note mismatch.
