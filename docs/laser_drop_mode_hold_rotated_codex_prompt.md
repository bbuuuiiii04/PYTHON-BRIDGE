# Codex prompt: drop_mode holds the rotated drop look (no separate post-drop)

**Branch:** `laser-drop-rotation-seed`
**Authoring split:** Claude analysis from live logs; **Codex implements.**
**Risk:** Laser Director is LIVE. Behavior change to drop handling.

## Target behavior (confirmed with operator)
In `drop_style == "drop_mode"`: each drop fires the **next look in the drop bank**
and **holds that same look** for the drop window. **No separate post-drop look at
all.** (Emphasized mode `emphasized_drop` keeps its current separate post-drop hold —
do not change it.)

## Root cause (from live logs + code)
Operator mapped 5 drops in `drop_mode`; every drop visually shows the same look
(`house_drop_5`). Three contributing facts:

1. **The director ignores `drop_style`.** `laser_director.py` has no reference to
   `drop_style`/`drop_mode`. It always emits `drop_crossing` (using `drop_scene`)
   then a separate `post_drop_hold` (using `post_drop_scene`, held
   `post_drop_hold_beats` ≈ 8). So even in `drop_mode` it holds a separate post-drop.
2. **`drop_mode` pins post-drop to the last-mapped drop.** `apply_mapping`
   (`tools/laser_config_ops.py:812-820`) sets `post_drop_scene = <that drop>` and
   `post_drop_bank = [<that drop>]` (cleared to one entry) on every drop mapping. So
   after mapping drops 1→5, post-drop froze to `house_drop_5`, single-entry → the
   held look never varies. Live config: `drop_bank=[house_drop_1..5]`,
   `post_drop_scene=house_drop_5`, `post_drop_bank=[house_drop_5]`.
3. **The drop-crossing itself is not rotating live** — see the UNRESOLVED section.

## Part 1 — director honors drop_mode (PRIMARY fix)
Teach `LaserDirector` the personality's `drop_style` (add it alongside
`post_drop_scene` in the director's personality config, set from
`personality.drop_style`). Then in `drop_mode`:
- Do **not** emit a separate post-drop decision with `post_drop_scene`. Instead, the
  drop scene selected at `drop_crossing` should **sustain** for the post-drop window
  (`post_drop_hold_beats`). i.e. the held look == the drop look just fired.
- `emphasized_drop` path unchanged.
Net: in `drop_mode` a drop = one rotated drop look, held; no second look.

## Part 2 — UNRESOLVED: drop rotation does not advance live (instrument first)
Live: 11/11 drops fired `house_drop_1` (bank[0]) despite `drop_bank` of 5 and the
`randomize_cursors` rotation change being loaded in the running process (verified:
the imported module has it). Unit tests + offline sim show the cursor seeds non-zero
and advances — but on the rig it behaves like cursor is pinned at 0 / reseeds to 0
each track. **Do not blind-fix this.** Steps:
1. Add diagnostic logging at each bank selection: role, `cursor` before/after,
   `len(bank)`, selected index, scene, and whether a reseed/reset just happened.
2. Likely suspect to verify: `set_personality` is called on **every** master/track
   change (`state_manager.py:_apply_personality_change` → `executor.set_personality`
   → `reset_runtime_state(reset_cursors=True)` → reseed) even when the personality is
   **unchanged** — which would reset/replace the cursor every track. If so, only
   reseed on an **actual personality change**, not on every track/deck event.
3. Confirm on the rig (logs) that the drop cursor advances one step per drop and
   persists across track loads before declaring done.

This must be solved for Part 1 to be meaningful (a held look is only good if it
rotates). Root-cause from the logging, not assumption.

## Part 3 — config cleanup
With the director no longer using a separate post-drop in `drop_mode`, stop
`apply_mapping` from pinning `post_drop_scene`/`post_drop_bank` to the last drop in
`drop_mode` (`tools/laser_config_ops.py:812-820`) — leave them empty/mirroring so the
config isn't misleading. Don't touch `emphasized_drop` mapping behavior.

## Out of scope
`emphasized_drop` behavior; removing the `primary` concept; config schema beyond the
above; the deck-2 work.

## Tests
- `drop_mode` director: a drop emits exactly one sustained scene = the rotated drop
  look; no separate post-drop decision; held for `post_drop_hold_beats`.
- Rotation: consecutive drops in `drop_mode` step through the drop bank
  (`drop_1→2→3→…`) and persist across a simulated track load / unchanged-personality
  re-apply (this is the regression that the live bug would trip).
- `emphasized_drop` unchanged. Verifier still green.

## Live validation (the gate)
Play several tracks: each drop shows a **different** look cycling through the drop
bank, **held** for the drop, with **no** second/post-drop look. Confirm via `[LASER]
scene` log that consecutive drops fire `house_drop_1 → house_drop_2 → …` and there is
no `post_drop_hold` line in `drop_mode`.
