---
doc_status: active-plan
truth_level: code-grounded-design-spec
last_verified_commit: 000fcb1
last_verified_date: 2026-06-24
validation_scope: RW-3 scripted/autoloop/idle mode-authority + identity gate for the bridge-native CH1-CH19 pack driver; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; default-off (enabled=false, dry_run=true, output_backend=none) — no restart/enable/backend/hardware authorized
---

# Codex Implementation Spec — RW-3 Explicit scripted/autoloop/idle mode-authority gate

> **Scope.** The SoundSwitch pack driver decides *whether it owns a scripted base
> at all* from the wrong signal: a syntactically-valid embedded `soundswitch_id`,
> instead of the bridge's actual scripted-mode authority (`DeckState.scripted_id`,
> the flag `_update_lighting` uses for the OS2L / laser / LED lanes). RW-3 adds the
> mode-authority term, an identity guard, and an identity-aware pause-hold latch so
> the pack honors the same scripted/autoloop/idle decision as every other lane and
> ZEROs when the deck is not a bridge-owned scripted track.
>
> **Roles.** Opus authored this; **Codex implements it**. No implementation, output
> enable, backend change, restart, or hardware action is authorized. Pack output
> stays default-off (`enabled=false`, `dry_run=true`, `output_backend=none`).
>
> **Builds on, does not reopen:** RW-1A (shutdown zero) and RW-2 (pause-vs-stop
> transport latch) are done and software-tested. RW-3 composes with the RW-2 latch
> and changes one predicate plus the hold-key identity; it must not regress RW-2.
>
> **Evidence labels:** **[C]** confirmed in current code at `000fcb1` (runtime code
> byte-identical to `e295e37`; only docs auto-synced) · **[A]** assumed/inferred,
> not executed · **[U]** needs live/hardware evidence (none promoted by software).

## Revision note — review round 1 incorporated (REJECT → repaired)
An independent second-opinion review
(`docs/prompts/reviews/soundswitch_rw3_mode_authority_review_prompt.md`) **rejected**
the first draft. This revision folds in a code-verification pass against `000fcb1`
and fixes all five objections. Each is re-verified, not taken on faith:

- **(BLOCKER) hold latch was not identity-aware.** The first draft kept the hold
  keyed by `(active, load_gen)`, so a `scripted_id` change inside the hold window
  (clear→arm, or a re-resolve to a different show, same `load_gen`) could keep a
  stale paused frame alive. **Fixed:** the hold latch is now keyed by the full
  played identity `(active, load_gen, scripted_id, normalized_ssid)`; any identity
  change invalidates the hold, and reacquisition requires a fresh PLAY tick (B.Task
  1c, A.4, D R7/R8).
- **(MAJOR) the strict-narrowing proof was false under held Static Override.**
  Verified in the player: `clear_selection()` yields `missing_selection` (held
  static stands), but `select_scripted(valid-UUID-not-in-pack)` yields
  `scripted_not_found`, a *non-`missing_selection`* diagnostic that `render()`
  returns **before** the static check — suppressing static. So for a valid-UUID-not-
  in-pack + held-static deck, RW-3 flips the submitted frame from ZERO (today) to
  static. **Fixed:** the proof is narrowed to the *automatic scripted base only*,
  and the held-static change is explicitly blessed against the accepted manual-
  static policy, with a test (A.6, C.5/C.7, D R10).
- **(MAJOR) `scripted_id != 0` did not prove identity coupling to the current
  `soundswitch_id`.** Under `RBSS_SCRIPTED_DIRECT=0`, OSC arming or the
  master-deck transfer (`state_manager.py:2559-2568`) can set `scripted_id` for a
  different track than the loaded `soundswitch_id`. **Fixed:** RW-3 is now
  **mode + identity**: a read-only `scripted_identity_ok` predicate fails closed
  when the in-memory scripted registry positively maps `scripted_id` to a different
  ssid, and falls open on the consciously-allowed showfile-direct / filepath-matched
  cases (A.3, B.Task 1b, D R9). Residual bounds are stated honestly (A.3).
- **(MAJOR) R6 asserted a pack frame after driving `_push_tick_inner`.** `inner`
  only mutates state; the wrapper `_push_tick` submits the frame. **Fixed:** R6 now
  drives the real path via `_push_tick()` (the harness `_tick()` helper), not
  `_push_tick_inner`, and not synthetic `_set` injection (A-D R6).
- **(MINOR) test coverage.** Added: same-drain clear→arm while paused (R8),
  scripted_id-change-during-pause isolation (R7), scripted_id↔ssid mismatch ZERO
  (R9), valid-UUID-not-in-pack + held static (R10); R6 rewritten; all RW-2 tests
  stay green (one tuple assertion updated for the 4-tuple hold key, Task 2c).

---

## Part A — Context & root cause (verified; read, do not implement)

### A.1 What happens today — the pack driver's "is this scripted?" test [C]
The 200 Hz push loop drives the pack once per tick from
`StateManager._drive_pack_output()` (`state_manager.py:3253`), called by `_push_tick`
(`:3233`, after `_push_tick_inner()` returns). The scripted-base happy gate is at
`state_manager.py:3296-3312`:

```python
playing = bool(getattr(d, "playing", False))                       # 3296
ssid = getattr(getattr(d, "meta", None), "soundswitch_id", "") or ""    # 3297
metadata_ready = _pack_normalize_id(ssid) is not None              # 3298
...
happy = fresh and metadata_ready and not track_changed and not discont  # 3312
```

- **[C]** `_pack_normalize_id` is `normalize_soundswitch_id` (`state_manager.py:66`
  import; `soundswitch_laser_player.py:166-177`): it returns non-`None` for **any
  exact UUID** and has no notion of which tracks are scripted. So `metadata_ready`
  answers "does this track carry a well-formed UUID?", **not** "is this a
  bridge-owned scripted track?".
- **[C]** `_drive_pack_output` reads `active = self._os.active_deck` (`:3266`) and
  `d = self._deck[active]` (`:3267`) but **never reads `d.scripted_id` or
  `self._os.lighting_mode`** — the whole-bridge scripted authority is invisible to
  the pack lane.

### A.2 The bridge's real scripted-mode authority is `d.scripted_id` [C]
Every other lane derives scripted/autoloop/idle from `DeckState.scripted_id`
(`models.py:83`, an `int`; `0` = none), **not** `meta.soundswitch_id`
(`models.py:35`, a `str`):

- **[C]** `_update_lighting` (`:3096`): `desired = "scripted"` iff `d.scripted_id
  and is_playing` (`:3117-3118`), else `"autoloop"` if playing, else `"idle"`; it
  writes `os.lighting_mode` (`:3145`). OS2L/laser/LED follow that.
- **[C]** The two identifiers are written by **different events**: `meta.soundswitch_id`
  ← `FILEPATH_RESOLVED` (`_on_filepath_resolved`, `:2878`), set for **any** track
  with an embedded UUID; `scripted_id` ← `SCRIPTED_ARM` (`:1242-1248`) and
  `_arm_scripted` (`:3014`), cleared by `SCRIPTED_CLEAR`→`_arm_unscripted` (`:3091`),
  `_on_track_loaded` (`:2616`), `RB_RESTARTED` (`:1263`).

So `metadata_ready` and `scripted_id` are **not the same authority**. The driver
gates on the former; the rest of the bridge gates on the latter.

### A.3 Investigation A — when does the driver observe a divergence, and the identity question (Objection 3) [C]/[A]
**Drain ordering [C].** `_run()` (`:872-877`) runs `_drain_events()` **then**
`_push_tick()` serially in one thread. `_drain_events()` (`:1070-1076`) is an
exhaustive `while True: get_nowait()` loop consuming **every** pending event,
including events enqueued *during* the drain. `_on_filepath_resolved` enqueues its
follow-on `SCRIPTED_ARM` (`:2960`) or `SCRIPTED_CLEAR` (`:2971`) into the same queue,
so the follow-on is normally consumed in the **same drain pass**, before the driver
runs.

**Under live `RBSS_SCRIPTED_DIRECT=1` (the operator's config) [C].** The direct
block (`:2920`) runs:
- Non-scripted UUID track: `_on_filepath_resolved` sets `meta.soundswitch_id`
  (`:2878`) then enqueues `SCRIPTED_CLEAR`→`_arm_unscripted` which **clears
  `meta.soundswitch_id=""`** (`:3092`) and `scripted_id=0` (`:3091`) in the same
  drain. Net: `soundswitch_id==""` → `metadata_ready` False → pack **already ZEROs**.
- Scripted track: `scripted_id` is matched by **exact ssid** (`:2927-2930`,
  `t.get("ssid") == ssid`) → `SCRIPTED_ARM` sets `scripted_id`. So under `=1`,
  `scripted_id` and `soundswitch_id` are **coupled by construction**.

So under the live flags the common path already ZEROs non-scripted tracks — **but
only as an incidental side effect of `_arm_unscripted` clearing the UUID** (`:3092`),
not as a deliberate pack-mode gate. The pack's current correctness is **accidental**.

**Where the driver *can* observe a real divergence:**
1. **[C] Mode divergence, durable under `RBSS_SCRIPTED_DIRECT=0`.** The `:2920`
   block is skipped, so no auto arm/clear; `soundswitch_id` stays set while
   `scripted_id` is driven only by external OSC. `_update_lighting` reports
   `"autoloop"` while the pack would render a scripted base.
2. **[C] Identity divergence (Objection 3).** Under `=0`, OSC `SCRIPTED_ARM`
   (`:1242-1248`, sets only `scripted_id`) or the master-deck transfer
   (`_on_master_changed:2559-2568`, copies `scripted_id` to the new deck without its
   `soundswitch_id`) can leave `scripted_id` referring to a **different show** than
   the loaded `soundswitch_id`. A bare `scripted_id != 0` mode gate would treat that
   as scripted-owned.
3. **[A] Mode divergence on a dropped `SCRIPTED_CLEAR`.** The production event queue
   is bounded (`queue.Queue(maxsize=512)`, `__main__.py:1020`); the enqueue is
   guarded by `except queue.Full` (`:2976`), so on saturation the clear is dropped,
   leaving `soundswitch_id` set with `scripted_id==0`.

**Bound on the identity harm [C].** The pack renders by `d.meta.soundswitch_id`
(`:3297`, `:3333`), i.e. the **loaded** track's ssid — **never** a third track's. So
a mismatched `scripted_id` can only affect *whether* the loaded track renders as
scripted (the mode question), not *what* content is rendered. RW-3 still adds an
explicit identity guard (A.3 → B.Task 1b) so a positively-contradicting `scripted_id`
fails closed.

**Honest severity [C].** Under the operator's `=1` flags the common mode path
already ZEROs non-scripted tracks; RW-3 is **explicit-authority + identity guard +
defense-in-depth + legacy(`=0`)/queue-drop closure**, not "the rig is rendering wrong
content right now." It satisfies the roadmap requirement (require `d.scripted_id`; do
not render an SSID merely because it is syntactically valid;
`soundswitch_exporter_remaining_work.md:377-381`).

### A.4 Identity-aware pause-hold latch (Objection 1) [C]
RW-2 keys its pause-hold latch by `(active, load_gen)`
(`_pack_play_hold_key`/`_pack_play_hold_deadline`, init `state_manager.py:361-362`;
set on a playing tick `:3316-3317`; checked on the paused branch `:3318-3323`).
`load_gen` only changes on `TRACK_LOADED` (`:2618`), so a **scripted_id change with
the same `load_gen`** (clear→arm to a different show via OSC, or a re-resolve, all
within one drain) does **not** change `(active, load_gen)`. The first RW-3 draft's
`not scripted_owned` reset did not help: after a same-drain clear→arm the driver sees
`scripted_id != 0` again, so it never observes `scripted_owned==False`.

**Fix [C].** Bind the hold latch to the full played identity:

```
play_identity = (active, load_gen, scripted_id, normalized_ssid)
```

The latch is set only on a happy **playing** tick and matched exactly on the paused
branch. Any change to deck, loaded track, scripted show, or ssid changes
`play_identity` → the paused branch fails closed and the else-branch resets the
latch. Reacquisition therefore requires a fresh PLAY tick (`happy and playing`) to
re-store the latch. Note the natural backstop: `_arm_unscripted` (`:3092`) clears
`soundswitch_id`, so a same-drain clear→arm **without** a fresh resolve also ZEROs
via `metadata_ready` (`norm_ssid is None`) regardless of the latch — `play_identity`
covers the case where a re-resolve restores a *different* ssid.

`load_key = (active, load_gen)` is still computed separately for `track_changed`
(`:3283-3287`, `_pack_last_load_gen`) — **unchanged**. Only the *hold* identity grows
to the 4-tuple.

### A.5 Authority variable: `d.scripted_id`, not `os.lighting_mode` [C]/[A]
The gate reuses `active_deck`, `d.scripted_id`, `d.meta.soundswitch_id`, transport,
and fresh-position, but the new *mode* term is `d.scripted_id`, not
`os.lighting_mode`:
- **[C]** `d.scripted_id` is read in-tick off the same `d` the driver holds, is the
  same per-deck authority `_update_lighting` keys on (`:3117`), and is not debounced.
- **[C]** `os.lighting_mode` is a *derived, debounced* view: `_update_lighting`
  returns early without updating it during the idle debounce (`:3133-3134`) and is
  skipped entirely on the stale-while-playing early return (`:3384-3406`). ANDing it
  would couple the pack to debounce timing without adding safety. It remains a
  documented cross-check (`"scripted"` iff `d.scripted_id and is_playing`), not a
  gate term.

### A.6 Held Static Override during unowned mode — the blessed behavior change (Objection 2) [C]
**Player asymmetry, verified [C].** In `LaserPackPlayer.render()`
(`soundswitch_laser_player.py:345-373`):
- `clear_selection()` (`:247-256`) sets `selection=None` → base diagnostic is
  `missing_selection` → the held-static check (`:363-372`) applies → **held static
  stands alone.**
- `select_scripted(valid-UUID-not-in-pack)` → `_scripted_base` (`:271-315`) hits
  `self._pack.scripted.get(normalized) is None` → `_diagnostic("scripted_not_found",
  …)` (`:298-301`). `render()` returns any **non-`missing_selection`** diagnostic
  **before** the static check (`:361-362`) → **held static suppressed → ZERO.**

So today, a valid-UUID-not-in-pack deck that is playing+fresh+held-static outputs
**ZERO** (the `scripted_not_found` path suppresses static). After RW-3, that deck has
`scripted_id==0` (or identity-mismatch) → `happy` False → `clear_selection()` →
`missing_selection` → **held static stands → CH1==200**. The submitted frame changes
from ZERO to static.

**Policy decision [C], operator-aligned.** This is **blessed**. The accepted
manual-static policy (`tests/test_state_manager_pack_driver.py:350-382`; RW-2 spec
A.3) is: held Static Override is operator-controlled, stands during deck-authority
problems (stale/error/track-change/discontinuity), and loses **only** to
blackout/emergency/pack-disabled/shutdown. "Deck is not a bridge-owned scripted
track" is a deck-authority condition, not blackout — so held static **should** stand.
RW-3's change is a **correction toward the accepted policy**, removing today's
accidental suppression. It is live-safe: held static means the operator is physically
holding a controller button and wants that look visible. Tested by R10.

### A.7 Corrected safety statement — automatic scripted base only [C]
RW-3 adds necessary conditions to `happy` (`scripted_owned`, `scripted_identity_ok`),
so for the **automatic scripted base**: `happy_RW3 → happy_today`, hence the
automatic base can only move render→ZERO, **never** ZERO→render. RW-3 therefore
**cannot produce a new non-zero automatic scripted base** under any input. The held
Static Override is a **separate layer** composed by the player after the base; per
A.6 it may now stand alone in more unowned cases (an intended, blessed change). The
*automatic-base-only* proof is what holds; the prior unqualified "never a new
non-zero submitted frame" claim is retracted.

### A.8 Transition table the gate must satisfy (Investigation E) [C]/[A]
`scripted_owned ≡ int(getattr(d,"scripted_id",0) or 0) != 0`;
`norm_ssid ≡ _pack_normalize_id(ssid)`;
`play_identity ≡ (active, load_gen, scripted_id, norm_ssid)`. "Base" = the automatic
base; held static composes independently (A.6).

| Transition | Authority that proves it | Automatic base |
|---|---|---|
| Fresh load, before resolve | `metadata_ready` False (`:2615`); `scripted_owned` False (`:2616`) | ZERO |
| Resolved, not scripted | `scripted_owned` False (`_arm_unscripted` `:3091`; or no auto-arm under `=0`) | ZERO |
| Resolved, scripted match, not yet armed | `scripted_owned` False until `SCRIPTED_ARM` (`:1248`) | ZERO (conservative) |
| Scripted armed + playing | `scripted_owned`+`scripted_identity_ok`+`metadata_ready`+`fresh`+`playing` | render `playing`; set latch=`play_identity` |
| Scripted, pause within hold | RW-2 latch + `happy`; `play_identity == hold key` | render `paused` ≤ `STOP_DEBOUNCE_S` |
| Scripted, pause past hold / stop | deadline expired / `was_playing` False | ZERO |
| **scripted_id changes during pause (same load_gen)** | `play_identity != hold key` (scripted_id differs) | ZERO; latch reset; needs fresh PLAY (A.4) |
| **same-drain clear→arm while paused** | `metadata_ready` False (ssid cleared `:3092`) and/or `play_identity` change | ZERO; latch reset (A.4) |
| **scripted_id↔ssid mismatch (OSC/transfer, `=0`)** | `scripted_identity_ok` False (registry maps scripted_id to a different ssid) | ZERO |
| Master switch / active change | `play_identity` deck change → reset | ZERO until new deck observed playing |
| Track replacement (`load_gen` change) | `track_changed` True (`:3284`) + `play_identity` change | ZERO that tick |
| Return to autoloop | `scripted_owned` False → `happy` False | ZERO (autoloop base is RW-8) |
| Return to idle / stale / discontinuity | `playing`/`was_playing` False; `fresh` False; `discont` True | ZERO |

### A.9 Constants & symbols (re-verified at `000fcb1`) [C]
`STOP_DEBOUNCE_S=0.5` (`config.py:74`); `MEM_STALE_S=3.0` (`config.py:62`);
`_PACK_SEEK_JUMP_MS=2000` (`state_manager.py:113`). `st_lookup` =
`scripted_tracks.lookup` (import `state_manager.py:71`); `_pack_normalize_id` import
`:66`. Driver-local trackers init `:358-363`; `_pack_play_hold_key` (`:361`) currently
typed `tuple[int, int] | None`. RW-3 adds no new instance field (it re-types the
existing hold key) and one read-only helper method.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Touch only** `state_manager.py` (the `_drive_pack_output` gate block `3296-3338`,
  the `_pack_play_hold_key` type comment at `:361`, and one new read-only helper) and
  `tests/test_state_manager_pack_driver.py`. Do **not** modify
  `soundswitch_laser_player.py`, `soundswitch_pack_runtime.py`, `_update_lighting`,
  `_apply_lighting`, `_push_tick_inner`, `_on_filepath_resolved`, `_arm_scripted`,
  `_arm_unscripted`, `_on_master_changed`, the event handlers, OS2L/laser/LED lanes,
  config, scripted_tracks.py, or any startup/dataclass/import surface.
- **Out of scope — name the boundaries:**
  - **RW-4 (controller-input health):** do not read
    `worker_alive`/`error`/`mail_drop_count`; the masks/static block (`:3271-3280`)
    is unchanged.
  - **RW-5 (status/menubar):** add no status string/field/path/id/port;
    `sanitized_status()` untouched.
  - **RW-8 (native-DMX Autoloop):** do not add `select_autoloop`; autoloop/idle ZERO
    via `clear_selection()`. Test D10 (autoloop never called) stays green.
- Driver-local, read-only w.r.t. `DeckState`/`OutputState`: RW-3 only *reads*
  `d.scripted_id`. StateManager stays the sole `DeckState` writer (S7.1). No new
  transport owner. The new helper does **no I/O** (in-memory dict lookup + UUID
  parse).
- ZERO path stays `clear_selection()`; never emit
  `transport="stopped"/"ended"/"unloaded"`. (Held static may stand alone over the
  ZEROed base — the blessed A.6 behavior.)
- No filesystem/subprocess/MIDI/serial/socket/sleep/retry/blocking-queue added
  (S7.2). Injected `now` clock from RW-2 unchanged.
- Default-off neutral: driver inert unless `rt.active` (`:3261-3262`); no enable,
  backend change, restart, or hardware open.

### Task 1 — `state_manager.py`: mode + identity gate and identity-aware hold latch
**1a. Add the read-only identity helper** (place it just above `_drive_pack_output`,
`~:3253`):
```python
    def _pack_scripted_identity_ok(self, scripted_id: int, norm_ssid: str | None) -> bool:
        """RW-3 spatial identity guard. READ-ONLY, no I/O.

        True unless the in-memory scripted registry POSITIVELY maps `scripted_id` to
        a normalized ssid that DIFFERS from `norm_ssid`. Fail-OPEN on registry
        absence or empty registry ssid (showfile-direct hash / filepath-matched
        track — consciously allowed, see spec A.3). Under RBSS_SCRIPTED_DIRECT=1
        (live), scripted_id is chosen by exact ssid-match, so this is a no-op for
        normally resolved tracks; it fails closed only on the =0 OSC/transfer
        mismatch.
        """
        if scripted_id == 0 or norm_ssid is None:
            return False
        track = st_lookup(scripted_id)
        if track is None:
            return True
        reg = _pack_normalize_id(track.get("ssid") or "")
        if reg is None:
            return True
        return reg == norm_ssid
```

**1b. Bind the new gate terms** — replace the `metadata_ready` line at
`state_manager.py:3298` and add the mode/identity bindings immediately after it (reuse
the `ssid` at `:3297` and the `active` at `:3266`):
```python
            norm_ssid = _pack_normalize_id(ssid)              # RW-3: capture once
            metadata_ready = norm_ssid is not None
            # RW-3 mode authority: the bridge's scripted classification is
            # DeckState.scripted_id (the flag _update_lighting keys on, :3117), NOT a
            # syntactically valid UUID. Read defensively (getattr) like d.playing.
            scripted_id = int(getattr(d, "scripted_id", 0) or 0)
            scripted_owned = scripted_id != 0
            # RW-3 spatial identity (fail-closed only on a positive registry contradiction):
            scripted_identity_ok = self._pack_scripted_identity_ok(scripted_id, norm_ssid)
            # RW-3 temporal identity for the pause-hold latch (A.4): bind the hold to
            # the full played identity so a clear->arm / re-resolve to a different
            # scripted_id or ssid within the hold window cannot resurrect a stale
            # paused frame. Reacquisition requires a fresh PLAY tick. Reuse the
            # EXISTING `load_key = (active, load_gen)` computed at :3283 (do not
            # recompute load_gen) so the track_changed and hold identities stay aligned.
            play_identity = (*load_key, scripted_id, norm_ssid)
```

**1c. AND the new terms into `happy` and switch the hold latch to `play_identity`** —
replace the transport-derivation block at `state_manager.py:3312-3338`:
```python
            happy = (
                fresh and metadata_ready and scripted_owned and scripted_identity_ok
                and not track_changed and not discont
            )
            was_playing = bool(getattr(self._os, "was_playing", False))
            if happy and playing:
                transport = "playing"
                self._pack_play_hold_key = play_identity
                self._pack_play_hold_deadline = now + STOP_DEBOUNCE_S
            elif (
                happy and was_playing
                and play_identity == self._pack_play_hold_key
                and now < self._pack_play_hold_deadline
            ):
                transport = "paused"
            else:
                transport = None  # stopped/hold-expired/unloaded/stale/changed/discont/unowned/mismatch
                if play_identity != self._pack_play_hold_key:
                    # New deck/track/show/ssid identity OR de-ownership: a prior
                    # identity's hold must not resurrect. Only a real PLAY of THIS
                    # identity re-enables (the playing branch above).
                    self._pack_play_hold_key = None
                    self._pack_play_hold_deadline = 0.0
            if transport is not None:
                player.select_scripted(
                    soundswitch_id=ssid, elapsed_ms=elapsed_ms, transport=transport,
                    metadata_ready=True, authority="fresh", source_errored=False,
                    elapsed_discontinuous=False, track_changed=False,
                )
            else:
                player.clear_selection()
```
Keep everything above (`:3266-3296`: masks/static, `load_key`/`track_changed`,
`discont`, `fresh`, `playing`, `ssid`) and the single `submit_frame` (`:3341`)
unchanged. The `_pack_last_load_gen`/`_pack_last_elapsed_ms` bookkeeping (`:3287`,
`:3294`) must keep updating every tick.

**1d. Re-type the hold-key field comment** at `state_manager.py:361`:
`self._pack_play_hold_key: tuple[int, int, int, str] | None = None  # play identity (active, load_gen, scripted_id, norm_ssid)`.

Commit: `feat(soundswitch): RW-3 gate pack base on scripted_id + identity, identity-aware hold`.

### Task 2 — `tests/test_state_manager_pack_driver.py`: seam + RW-3 cases + RW-2 fixups
**2a. Extend `_set`** (`:102-110`) to carry `scripted_id`, defaulting so existing
tests are unchanged (a track with an `ssid` is a scripted track by these tests'
convention), and add a second valid UUID for not-in-pack cases:
```python
SSID2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"   # valid UUID, ABSENT from _pack()
def _set(sm, *, ssid="", elapsed_ms=0, playing=False, load_gen=1, snap=FRESH,
         active=1, was_playing=None, scripted_id=None):
    if was_playing is None:
        was_playing = playing
    if scripted_id is None:
        scripted_id = 1 if ssid else 0   # ssid present ⇒ bridge-owned scripted, by default
    sm._os = SimpleNamespace(active_deck=active, was_playing=was_playing)
    sm._deck = {active: SimpleNamespace(
        meta=SimpleNamespace(soundswitch_id=ssid), elapsed_ms=elapsed_ms,
        playing=playing, load_gen=load_gen, scripted_id=scripted_id)}
    sm._cache = SimpleNamespace(get=lambda _dk: snap)
```
The default `scripted_id = 1 if ssid else 0` keeps every existing driver-level test
green (ssid=SSID render tests get `scripted_owned True`; `st_lookup(1)` is None in
unit tests → `scripted_identity_ok` falls open → True; ssid="" tests already ZERO on
`metadata_ready`). Confirm the full existing module passes after 2a before adding R*.

**2b. Add the RW-3 cases** (Part D R1–R10), using the real `LaserPackPlayer` over
`_pack()` and `_FakeBackend`; pass `now` where the hold deadline matters; import
`SCRIPTED_TRACKS`/`register` from `rb_ss_bridge_v2.scripted_tracks` for R9 and
`addCleanup`-pop the registered id so the module global does not leak.

**2c. Fix the one RW-2 assertion that pins the hold-key tuple.**
`test_master_switch_zeros_until_new_deck_confirmed` (`:308`) asserts
`sm._pack_play_hold_key == (2, 1)`; the hold key is now the 4-tuple — update to
`self.assertEqual(sm._pack_play_hold_key, (2, 1, 1, SSID))` (deck 2, load_gen 1,
default scripted_id 1, normalized SSID == SSID). All other RW-2 assertions
(`assertIsNone(...)`, `assertEqual(..._deadline, 10.7)`) are unaffected.

Commit: `test(soundswitch): RW-3 mode/identity/hold cases; RW-2 hold-key fixup`.

### Task 3 — inner / event-path integration test (corrected mechanics)
Add R6 and R8 driving the **real** path via `_push_tick()` (the `PackDriverInnerTickTests`
`_tick()` helper already calls `self.sm._push_tick()` at `:481` — use it; do **not**
call `_push_tick_inner` directly and do **not** use synthetic `_set`). R6 runs under
`RBSS_SCRIPTED_DIRECT="0"` so a valid ssid resolves with `scripted_id` staying `0`.

Commit: `test(soundswitch): RW-3 inner-path autoloop-uuid zero + same-drain clear→arm`.

---

## Part C — Invariants that MUST still hold (live safety; maps to roadmap §7)

1. **S7.1 sole `DeckState` writer.** RW-3 only *reads* `d.scripted_id`/registry; it
   writes only the existing driver-local `_pack_play_hold_*` fields.
2. **S7.2 push-loop purity.** Added work is in-memory only: a `getattr`/`int`, a UUID
   parse, and a dict `.get()` (`st_lookup`). No I/O, sleep, retry, lock, or blocking.
3. **S7.8 ZERO on unowned/stale/error/invalid/mismatched identity.** `scripted_owned`
   (mode) + `scripted_identity_ok` (registry contradiction) + the existing
   fresh/track_changed/discont terms resolve every non-owned case to
   `clear_selection()` → ZERO. The roadmap "require `d.scripted_id`" gap is closed.
4. **RW-2 not regressed.** The paused branch requires `happy` (now incl.
   `scripted_owned`/`scripted_identity_ok`) and an exact `play_identity` match; a deck
   that loses scripted ownership or whose identity changes mid-hold cannot render a
   stale scripted frame (`happy` False and/or `play_identity` mismatch + latch reset).
   Normal pause/resume/expiry behavior is byte-identical (the new terms stay
   True/identity stable across a legitimate pause). `STOP_DEBOUNCE_S` and the deadline
   math are unchanged.
5. **S7.9 manual Static Override + blackout precedence.** Masks/static block
   (`:3271-3280`) and player precedence (`render()` `:345-373`) untouched. **Blessed
   change (A.6):** held static now stands alone over the ZEROed automatic base in
   unowned mode (incl. valid-UUID-not-in-pack), consistent with the accepted
   manual-static policy; blackout/emergency still win first. Only the *automatic*
   base is gated; the controller path is unchanged (RW-4 boundary held).
6. **No `transport="stopped"/"ended"/"unloaded"`.** ZERO stays `clear_selection()`.
7. **Corrected safety proof (A.7).** `happy_RW3 → happy_today`, so RW-3 cannot create
   a new non-zero **automatic scripted base**. The held-static layer is separate and
   explicitly blessed (C.5); the unqualified "never a new non-zero frame" claim is
   retracted.
8. **S7.10/S7.11 default-off neutrality.** Inert unless `rt.active`; byte/order-neutral
   for OS2L/lasers/LEDs/Rekordbox/commands/logs when pack is absent/disabled/dry-run/
   none.
9. **S7.12 no leaks.** No new status string/path/id/port/byte; `sanitized_status()`
   untouched.
10. **Autoloop safe-zero (RW-8 boundary).** `select_autoloop` still uncalled; autoloop
    mode ZEROs.
11. **Identity-guard false-zero is bounded and fail-safe ([A]).** `scripted_identity_ok`
    can only ZERO a scripted track when the registry positively maps its `scripted_id`
    to a *different* ssid. Under `=1` that cannot happen for normally resolved tracks
    (ssid-match makes registry ssid == current ssid). The lone residual is a track
    whose embedded ssid is **re-authored mid-session** so a stale registry ssid
    differs — rare, in the fail-closed (dark) direction, and recovered by a restart
    (which re-runs `resolve_filepaths`). No silent wrong-content render results.

---

## Part D — Tests (pure seams; no device, no AppKit, no hardware)

`_pack()`: scripted SSID present; at 0 ms CH1==5; at 50/60 ms CH1==9; static slot 8 →
CH1==200. `SSID2` is a valid UUID **absent** from `_pack().scripted`.

**Driver-level (extended `_set`; explicit `scripted_id`):**
- **R1 `test_valid_ssid_but_unscripted_playing_zeros`** — `_set(ssid=SSID,
  elapsed_ms=50, playing=True, scripted_id=0)` → ZERO (core fix). Pre-RW-3: CH1==9.
- **R2 `test_scripted_owned_playing_still_renders`** — `_set(ssid=SSID, elapsed_ms=50,
  playing=True, scripted_id=7)` → CH1==9 (regression guard; `st_lookup(7)` None →
  identity falls open).
- **R3 `test_unscripted_pause_does_not_hold`** — play `scripted_id=7` (`now=t0`); then
  `playing=False, was_playing=True, scripted_id=0, now=t0+0.1`, same load_gen → ZERO,
  assert `sm._pack_play_hold_key is None` and `_pack_play_hold_deadline == 0.0`.
- **R4 `test_scripted_id_set_but_ssid_empty_zeros`** — `_set(ssid="", playing=True,
  scripted_id=7)` → ZERO (`metadata_ready` False; proves `scripted_owned` is ANDed).
- **R5 `test_unscripted_in_pack_with_held_static_shows_static`** — `_set(ssid=SSID,
  playing=True, scripted_id=0)` + `_FakeInput(held_static_slot=8)` → CH1==200 (base
  ZEROs, held static stands).
- **R7 `test_pause_hold_not_resurrected_by_scripted_id_change`** (Objection 1, driver
  isolation) — play `ssid=SSID, scripted_id=1, load_gen=1, now=t0` (latch=`(1,1,1,
  SSID)`); then `ssid=SSID, scripted_id=2, playing=False, was_playing=True,
  load_gen=1, now=t0+0.1` → ZERO (`play_identity (1,1,2,SSID) != hold key`), assert
  `sm._pack_play_hold_key is None`.
- **R9 `test_scripted_id_ssid_mismatch_zeros`** (Objection 3) — `register(7, {"name":
  "x", "ssid": SSID2})`; `_set(ssid=SSID, playing=True, scripted_id=7)` →
  `scripted_identity_ok` False (registry maps 7→SSID2 ≠ SSID) → ZERO;
  `addCleanup(lambda: SCRIPTED_TRACKS.pop(7, None))`. Also assert the **allowed**
  case: register 7 with `ssid=SSID` → renders CH1==9 (identity matches).
- **R10 `test_valid_uuid_missing_from_pack_with_held_static`** (Objection 2 policy) —
  `_set(ssid=SSID2, playing=True, scripted_id=0)` + `_FakeInput(held_static_slot=8)` →
  CH1==200. Comment: pre-RW-3 this ZEROs (player `scripted_not_found` suppresses
  static); RW-3 lets held static stand (blessed, A.6/C.5).

**Inner / event-path (`PackDriverInnerTickTests`; drive `_push_tick()` via `_tick()`):**
- **R6 `test_inner_autoloop_uuid_stays_zero`** (Objection 4 mechanics) — under
  `patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "0"})`: `TRACK_LOADED`, then
  `_on_filepath_resolved` with valid `soundswitch_id=SSID` (no auto-`SCRIPTED_ARM`
  under `=0`, so `scripted_id` stays 0), then `PLAY` + `_tick()` (which calls
  `_push_tick()`). Assert **both** `self.sm._os.lighting_mode == "autoloop"` **and**
  frame `== ZERO_FRAME`. Pre-RW-3 this renders CH1==9. Purely exercisable (events +
  injected clock + real `PositionCache`); the `[U]` escape is **not** permitted.
- **R8 `test_inner_same_drain_clear_then_arm_while_paused_zeros`** (Objection 1
  real-path) — `_load_scripted` (load_gen=1, scripted_id=1), `_start_playing` (latch
  set), `Ev.PAUSE`, `_tick()` → CH1==9 (held). Then, before the next `_tick()`, apply
  `_event(Ev.SCRIPTED_CLEAR)` then `_event(Ev.SCRIPTED_ARM, payload={"scripted_id":2})`
  (simulating both drained in one pass; `_event` calls `_handle_event` directly).
  `_tick()` → ZERO (ssid cleared by `_arm_unscripted` → `metadata_ready` False, and/or
  `play_identity` change), assert `self.sm._pack_play_hold_key is None`.

**Regression — green unchanged after 2a/2c:** D1–D14, the RW-2 driver tests, the three
`PackDriverInnerTickTests` RW-2 timing tests, and the manual-static-policy tests
(`:350-382`). The `scripted_id` default and the single 2c tuple fixup keep them all
rendering/zeroing as before.

---

## Part E — Acceptance (definition of done)

- [ ] `_drive_pack_output` ANDs `scripted_owned` and `scripted_identity_ok` into
      `happy`; the pause-hold latch is keyed by `play_identity = (active, load_gen,
      scripted_id, norm_ssid)`; the else-branch resets on `play_identity != hold key`.
      New read-only helper `_pack_scripted_identity_ok` added. Diff confined to the
      gate block + helper + the `:361` type comment in `state_manager.py`, and to the
      test file. No `DeckState`/`OutputState` write; no new instance field; no
      player/runtime/config/startup/scripted_tracks change.
- [ ] R1–R10 pass (R6 via `_push_tick()`); existing D1–D14, all RW-2 driver and
      inner-tick tests green after the `_set` default and the single 2c tuple fixup.
- [ ] Invariants C.1–C.11 hold; the corrected automatic-base-only proof (C.7/A.7);
      the blessed held-static policy (C.5/A.6, R10); RW-2 non-regression (R3/R7/R8 +
      the unchanged RW-2 suite); identity false-zero bound (C.11).
- [ ] **Gates run and outputs recorded (all HARDWARE-UNVALIDATED):**
      ```bash
      cd /Users/bbui
      python3.14 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation \
        --project ~/Music/SoundSwitch/default.ssproj \
        --output-dir /tmp/rbss-soundswitch-rw3-proof        # expect 29/0/0 (RW-3 does not touch pack gen)

      cd /Users/bbui/rb_ss_bridge_v2
      python3 -m unittest discover tests                     # full suite green
      python3 tools/check_docs_metadata.py
      python3 tools/check_agent_contracts.py
      python3 tools/check_docs_drift.py
      python3 tools/check_docs_staleness.py --report         # advisory
      git diff --check
      ```
- [ ] Focused module also run under Python 3.11
      (`python3.11 -m unittest tests.test_state_manager_pack_driver`) — RW-3 touches no
      dataclass/import/startup surface, so 3.11 is advisory.
- [ ] `enabled=false`, `dry_run=true`, `output_backend=none` unchanged; no restart,
      enable, backend change, MIDI/serial open, or hardware action.
- [ ] Doc update per anti-drift (AGENTS.md §7): flip RW-3 in
      `soundswitch_exporter_remaining_work.md` §5 to `[x] [C]` with the implementing
      commit; re-verify the `soundswitch_output`/`soundswitch_pack_player` contract
      docs before bumping `last_verified_commit`. `state_manager.py` is already in the
      `soundswitch_pack_player` contract globs (`change_contracts.yml:249`), so no
      contract extension is required.

## When you finish
Commit per task with the messages above. Report back: the gate diff (the new
bindings, the `happy` line, the `play_identity` hold latch, the helper), the `_set`
seam change, the 2c tuple fixup, the new test names with pass counts, the proof-gate
verdict (expect `PASS_IMPLEMENTATION_MAY_BEGIN`, 29/0/0), and the full-suite +
hard-docs-check results. Provide an updated reviewer prompt in your final response.

---

## Appendix 1 — Review round 1 objection closure

| # | Objection | Fix | Where |
|---|---|---|---|
| 1 BLOCKER | hold latch not identity-aware (same-drain clear→arm resurrects) | hold keyed by `play_identity=(active,load_gen,scripted_id,norm_ssid)`; reset on mismatch; reacquire needs fresh PLAY | A.4, B.1c, D R7/R8 |
| 2 MAJOR | strict-narrowing proof false under held static | proof narrowed to automatic base; held-static stand-alone blessed per accepted policy + tested | A.6, A.7, C.5/C.7, D R10 |
| 3 MAJOR | `scripted_id != 0` ≠ identity coupling | added `scripted_identity_ok` (fail-closed on registry contradiction, fail-open on showfile-direct/filepath; no-op under `=1`); harm bounded (pack renders loaded ssid only); honest residual | A.3, B.1a/1b, C.11, D R9 |
| 4 MAJOR | R6 drove `_push_tick_inner` but asserted a frame | R6 rewritten to drive `_push_tick()` via `_tick()`, real events, no `_set` | A-D R6, B.Task 3 |
| 5 MINOR | test coverage | R6 rewrite + R7 (scripted_id change) + R8 (same-drain clear→arm) + R9 (mismatch ZERO) + R10 (uuid-not-in-pack + static); RW-2 suite green w/ 2c fixup | D, Task 2 |

## Appendix 2 — 9-point pre-handoff checklist (run against this revised spec)

1. **Claims labeled C/A/U.** ✅ Part A labels each fact; severity (A.3), identity
   false-zero (C.11), and queue boundedness are explicitly [C]/[A].
2. **Verified against CURRENT code (`000fcb1`).** ✅ Every file:line re-read this pass;
   the player render asymmetry (A.6), the `:2559-2568` transfer, the `:2920` direct
   block, `:3092` ssid-clear, and `st_lookup` import (`:71`) were re-confirmed; runtime
   code byte-identical to `e295e37`.
3. **Pending-state guard (all same-tick fields).** ✅ Gate composes with RW-2 latch
   (now identity-bound), held static + blackout (untouched, R5/R10), track_changed/
   discont (A.8). The de-ownership/identity-change interaction is closed by the
   `play_identity` reset (B.1c).
4. **Mode-transition cleanup on every path.** ✅ A.8 table covers fresh-load/resolve/
   not-yet-armed/play/pause/de-ownership/clear-arm/mismatch/master-switch/replace/
   autoloop/idle/stale/discont; the hold latch is reset on any `play_identity` change.
5. **Third-party API completeness.** ✅ Existing `select_scripted(...)`/
   `clear_selection()` shapes (`:3331-3338`) reproduced verbatim and unchanged; the
   gate is StateManager-side; the helper uses only `st_lookup` + `_pack_normalize_id`.
6. **Cross-checked against existing authority vars.** ✅ Uses canonical `d.scripted_id`
   (== `_update_lighting:3117`), `d.meta.soundswitch_id`/`metadata_ready`, and the
   `scripted_tracks` registry (the same source `_on_filepath_resolved` matches on);
   `os.lighting_mode` evaluated and deliberately not ANDed (A.5).
7. **Pure-function test seam.** ✅ R1–R10 use the real player + fake backend via `_set`
   or the inner-tick harness with injected clock + real `PositionCache`; no disk/
   subprocess/AppKit. R9 uses the in-memory registry global with cleanup.
8. **Live safety explicit.** ✅ Part C maps S7.1/7.2/7.8/7.9/7.10–7.12; corrected
   automatic-base-only proof (A.7/C.7); held-static blessed (C.5); identity false-zero
   bounded and restart-recoverable (C.11); ZERO-on-uncertainty default (A.8).
9. **Adversarial self-review (forced failures).** ✅ (a) *same-drain clear→arm while
   paused* → ssid cleared (`:3092`) ⇒ `metadata_ready` False, and `play_identity`
   change ⇒ latch reset (R8). (b) *scripted_id flips to a different show, same
   load_gen, mid-pause* → `play_identity` mismatch ⇒ no paused render, latch reset
   (R7). (c) *valid UUID not in pack + held static* → blessed static stand-alone, not a
   hidden regression (R10). (d) *OSC arms a mismatched scripted_id under `=0`* →
   `scripted_identity_ok` False ⇒ ZERO, and even absent the guard the pack renders only
   the loaded ssid (A.3 bound). (e) *identity guard false-zero* → only on mid-session
   re-author with a stale registry; fail-closed/dark, restart-recoverable (C.11). (f)
   *honesty* → under live `=1` the common path already ZEROs (A.3); RW-3 is
   explicit-authority + identity + defense-in-depth, not an "actively wrong" claim.

**Verdict: all 9 pass; all five review objections closed — Codex-ready (pending the
second-opinion re-review).**
