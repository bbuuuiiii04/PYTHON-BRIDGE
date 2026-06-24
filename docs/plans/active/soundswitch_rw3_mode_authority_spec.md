---
doc_status: active-plan
truth_level: code-grounded-design-spec
last_verified_commit: d97ff44
last_verified_date: 2026-06-24
validation_scope: RW-3 scripted/autoloop/idle mode-authority gate (mode-only) + de-ownership-safe pause-hold latch for the bridge-native CH1-CH19 pack driver; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; default-off (enabled=false, dry_run=true, output_backend=none) — no restart/enable/backend/hardware authorized
---

# Codex Implementation Spec — RW-3 Explicit scripted/autoloop/idle mode-authority gate

> **Scope.** The SoundSwitch pack driver decides *whether it owns a scripted base at
> all* from the wrong signal: a syntactically-valid embedded `soundswitch_id`, instead
> of the bridge's actual scripted-mode authority (`DeckState.scripted_id`, the flag
> `_update_lighting` uses for the OS2L / laser / LED lanes). RW-3 makes the pack gate
> on `scripted_id` (a **mode-only** gate), and hardens the RW-2 pause-hold latch so a
> de-owned deck cannot resurrect a stale paused frame. It honors the same
> scripted/autoloop/idle decision as every other lane and ZEROs when the deck is not a
> bridge-owned scripted track.
>
> **Roles.** Opus authored this; **Codex implements it**. No implementation, output
> enable, backend change, restart, or hardware action is authorized. Pack output stays
> default-off (`enabled=false`, `dry_run=true`, `output_backend=none`).
>
> **Builds on, does not reopen:** RW-1A (shutdown zero) and RW-2 (pause-vs-stop
> transport latch) are done and software-tested. RW-3 composes with the RW-2 latch and
> changes one predicate plus the hold-latch identity/teardown; it must not regress RW-2.
>
> **Evidence labels:** **[C]** confirmed in current code at `d97ff44` (runtime code
> byte-identical to `e295e37`; only docs auto-synced) · **[P]** policy decision
> (operator-confirmed where noted) · **[A]** assumed/inferred · **[U]** needs
> live/hardware evidence (none promoted by software).

## Revision note — review rounds 1 & 2 incorporated (REJECT → REJECT → repaired)
Round 1 REJECTED the first draft (5 objections) and round 2 REJECTED the revision (3
objections). This revision folds in a code-verification pass against `d97ff44` and
fixes all of round 2. Each is re-verified, not taken on faith:

- **(R2 BLOCKER) the 4-tuple hold identity could not prove "reacquisition requires a
  fresh PLAY" for a SAME-IDENTITY clear→re-resolve→arm.** Under
  `RBSS_SCRIPTED_DIRECT=0`, one exhaustive drain can process `SCRIPTED_CLEAR`
  (`_arm_unscripted` clears `scripted_id`+`soundswitch_id`) → `FILEPATH_RESOLVED` (same
  `load_gen`, **restores the same ssid**, no auto-arm under `=0`) → `SCRIPTED_ARM`
  (restores the same `scripted_id`). The driver then sees an **identical**
  `(active, load_gen, scripted_id, norm_ssid)`, so the paused branch could render
  without a fresh PLAY. **Fixed:** add a one-line latch teardown inside
  `_arm_unscripted` (the SCRIPTED_CLEAR handler) so any scripted de-ownership
  immediately disarms the pack pause-hold; the 4-tuple still covers the other de-owner
  paths. Completeness proof + thread-safety in A.4; test R8 reproduces the exact
  sequence.
- **(R2 MAJOR) `scripted_identity_ok` false-zeroed a legitimate direct-mode filepath
  match, and "restart recovers" was false.** Verified: `resolve_filepaths` only writes
  ssid `if not track.get("ssid")` (`scripted_tracks.py:82`), so a stale **non-empty**
  registry ssid survives restart; and a filepath-matched track (registry ssid=OLD,
  loaded ssid=NEW-in-pack) would be wrongly ZEROed. **Fixed:** the registry identity
  guard is **removed**. RW-3 is now **mode-only** (`scripted_id != 0`); the false
  restart claim is deleted. Identity coupling is handled honestly by the bound that the
  pack renders only the *loaded* ssid (A.3), which closes round-1 Objection 3 via the
  "mode-only, don't overclaim identity" route both reviewers accepted.
- **(R2 MINOR) R9 used `register()` twice for the same id, which is a no-op.**
  Verified: `register()` only writes when the id is absent (`scripted_tracks.py:29`).
  **Fixed:** R9 registers a single stale entry with explicit `addCleanup` pop and
  asserts the gate renders anyway (proving the registry is not consulted); D R9.

Preserved-good parts (unchanged): the held Static Override blessing (A.6,
operator-confirmed); the automatic-base-only safety proof (A.7); ZERO path stays
`clear_selection()`; no `transport="stopped"/"ended"/"unloaded"`; `select_autoloop`
uncalled; RW-4 out of scope; default-off; no blocking in the push loop; StateManager
the only `DeckState` writer.

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
  import; `soundswitch_laser_player.py:166-177`): non-`None` for **any exact UUID**,
  with no notion of which tracks are scripted. So `metadata_ready` answers "does this
  track carry a well-formed UUID?", **not** "is this a bridge-owned scripted track?".
- **[C]** `_drive_pack_output` reads `active = self._os.active_deck` (`:3266`) and
  `d = self._deck[active]` (`:3267`) but **never reads `d.scripted_id`** — the
  whole-bridge scripted authority is invisible to the pack lane.

### A.2 The bridge's real scripted-mode authority is `d.scripted_id` [C]
Every other lane derives scripted/autoloop/idle from `DeckState.scripted_id`
(`models.py:83`, an `int`; `0` = none), **not** `meta.soundswitch_id`
(`models.py:35`, a `str`):

- **[C]** `_update_lighting` (`:3096`): `desired = "scripted"` iff `d.scripted_id and
  is_playing` (`:3117-3118`), else autoloop/idle; writes `os.lighting_mode` (`:3145`).
- **[C]** The two identifiers are written by **different events**: `meta.soundswitch_id`
  ← `FILEPATH_RESOLVED` (`:2878`), set for any UUID-bearing track; `scripted_id` ←
  `SCRIPTED_ARM` (`:1242-1248`) / `_arm_scripted` (`:3014`), cleared by
  `SCRIPTED_CLEAR`→`_arm_unscripted` (`:3091`), `_on_track_loaded` (`:2616`),
  `RB_RESTARTED` (`:1263`).

### A.3 RW-3 is a MODE gate, not an identity-coupling gate (round-1 Obj 3 + round-2 MAJOR) [C]/[A]
A first instinct is to also check that `scripted_id` "belongs to" the current
`soundswitch_id` via the scripted registry. **That guard is removed**, because it
false-zeros legitimate tracks:

- **[C]** Under `RBSS_SCRIPTED_DIRECT=1` (live), `_on_filepath_resolved` matches
  `scripted_id` by exact ssid (`:2927-2930`) **but falls back to a unique filepath
  match** (`:2938-2945`) when the embedded ssid does not match any registry ssid. A
  track whose registry entry holds a **stale non-empty ssid=OLD** while the loaded
  track now has **ssid=NEW (present in the pack)** is filepath-matched and armed; a
  registry guard comparing OLD≠NEW would ZERO a show the player can render. The earlier
  "restart recovers" escape is **false**: `resolve_filepaths` only overwrites ssid
  `if not track.get("ssid")` (`scripted_tracks.py:82`), so a stale non-empty ssid
  survives restart.
- **[C]** The harm of *not* coupling is bounded: the pack renders by
  `d.meta.soundswitch_id` (`:3297`, passed to `select_scripted` at `:3333`) — the
  **loaded** track's ssid, **never** a third track's. A `scripted_id` that refers to a
  different show (OSC arm under `=0`, or the master-deck transfer `:2559-2568`) only
  affects *whether* the loaded track renders as scripted (the mode question), not
  *what* renders. If the loaded ssid is not in the pack, the player's own
  `scripted_not_found` (`soundswitch_laser_player.py:298-301`) ZEROs.
- **[C]** The master-deck transfer (`:2559-2568`, `=0` only) and the OSC-race fix are
  *intended* to make the new/target deck scripted; mode-only renders the loaded ssid
  there, which is correct. A registry guard would have wrongly ZEROed those too.

**Decision [P]:** RW-3 gates on `scripted_id != 0` (mode) only. It does **not** assert
that `scripted_id` and `soundswitch_id` name the same show — that coupling is the
bridge's arming responsibility, and under `=1` it is normally exact-ssid by
construction. The spec does not overclaim identity safety; it states the bound above.
This satisfies both reviewers (round 1 accepted "mode-only, say it clearly"; round 2
offered mode-only as option 1).

### A.4 De-ownership-safe pause-hold latch (round-2 BLOCKER) [C]
RW-2 keys its pause-hold latch by `(active, load_gen)`
(`_pack_play_hold_key`/`_pack_play_hold_deadline`, init `:361-362`; set on a playing
tick `:3316-3317`; checked `:3318-3323`; reset in the else `:3326-3330`). The round-1
revision widened the hold key to the **played identity**
`play_identity = (active, load_gen, scripted_id, norm_ssid)`. That is still required
(it catches a bare re-arm to a different `scripted_id`, or a bare re-resolve to a
different `ssid`, with no intervening clear), **but it is not sufficient on its own.**

**Why the 4-tuple alone is insufficient [C].** Under `RBSS_SCRIPTED_DIRECT=0`, one
exhaustive `_drain_events()` pass (`:1070-1076`, runs before `_push_tick`, `:872-877`)
can process, for a deck paused inside `STOP_DEBOUNCE_S`:
1. `SCRIPTED_CLEAR` → `_arm_unscripted` (`:3087-3092`): `scripted_id=0`,
   `soundswitch_id=""`.
2. `FILEPATH_RESOLVED` (same `load_gen`): `meta.soundswitch_id` restored to the **same**
   ssid (`:2878`); under `=0` the arm/clear block (`:2920`) is skipped, so no auto event.
3. `SCRIPTED_ARM` → handler (`:1242-1248`): `scripted_id` restored to the **same** value.

Net at driver time: `play_identity` is **byte-identical** to the stored hold key, the
deadline is still live, `was_playing` is still True → the paused branch would render
**without a fresh PLAY**. The driver never observed `scripted_owned==False` (it only
sees net state after the exhaustive drain).

**Fix [C] — teardown the latch at the de-ownership event, not just at the driver.**
Add to `_arm_unscripted` (the sole `SCRIPTED_CLEAR` consumer, `:1254-1255`):
```python
self._pack_play_hold_key = None
self._pack_play_hold_deadline = 0.0
```
When the CLEAR is processed *during the drain* (step 1), the latch is nulled. Steps 2–3
do **not** restore it (only the driver's playing branch sets it, and the driver runs
**after** the drain). At driver time the latch is `None`, the paused branch fails
(`play_identity != None`), and the else-branch keeps it `None` → ZERO, requiring a
fresh PLAY tick to re-arm. Closes the BLOCKER.

**Thread-safety [C].** `_arm_unscripted` is reached only via `SCRIPTED_CLEAR` →
`_handle_event` (`:1089`) → `_drain_events` → `_run` (`:872-877`). `_drive_pack_output`
runs in the same `_run` thread (`_push_tick`, `:3233`). `_pack_play_hold_key` is
written only by the driver (`:3316`, `:3329`) and now `_arm_unscripted` — all on the
one `_run` thread. No lock needed; it is push-local state, not `DeckState`.

**Completeness — why `_arm_unscripted` is the only handler that needs the teardown [C].**
Every scripted de-ownership path is covered:
| De-owner | What changes | Caught by |
|---|---|---|
| `SCRIPTED_CLEAR` (`_arm_unscripted`) | `scripted_id`→0, `ssid`→"" (both **restorable** same-drain) | **the new teardown** |
| `TRACK_LOADED` (`_on_track_loaded` `:2616-2618`) | `load_gen` ++ (monotonic, **not** restorable) | 4-tuple `load_gen` |
| `RB_RESTARTED` (`:1257-1271`) | `scripted_id`→0 **and** `was_playing`→False | paused branch needs `was_playing` |
| active-deck switch (`_on_master_changed` `:2569`,`:2580`) | `active` changes **and** `was_playing`→False | 4-tuple `active` + `was_playing` |
Only `SCRIPTED_CLEAR` can restore an *identical* 4-tuple within one drain; the others
change a monotonic/irreversible field or drop `was_playing`. So a single teardown in
`_arm_unscripted` is the smallest complete fix. (A normal pause does **not** emit a
`SCRIPTED_CLEAR` for the active deck — `_on_filepath_resolved` does not re-fire without
a new load — so the teardown never disturbs a legitimate pause-hold; see R8 vs R1/R3.)

### A.5 Authority variable: `d.scripted_id`, not `os.lighting_mode` [C]/[A]
The mode term is `d.scripted_id`, not `os.lighting_mode`: `scripted_id` is read in-tick
off the same `d`, is the same per-deck authority `_update_lighting` keys on (`:3117`),
and is not debounced. `os.lighting_mode` is a derived view that lags during the idle
debounce (`:3133-3134`) and is skipped on the stale-while-playing early return
(`:3384-3406`); ANDing it would couple the pack to debounce timing without adding
safety. It remains a documented cross-check only.

### A.6 Held Static Override during unowned mode — blessed (round-1 Obj 2) [C]/[P]
**Player asymmetry, verified [C]:** `clear_selection()` (`:247-256`) → `missing_selection`
base → held static **stands** (`render()` `:363-372`); `select_scripted(valid-UUID-
not-in-pack)` → `scripted_not_found` (`:298-301`), a **non-`missing_selection`**
diagnostic that `render()` returns **before** the static check (`:361-362`) →
**suppresses** static. So today a valid-UUID-not-in-pack + held-static deck outputs
ZERO; after RW-3 it has `scripted_id==0` → `happy` False → `clear_selection()` →
**held static stands → CH1==200**.

**Policy decision [P], operator-confirmed 2026-06-24.** This is **blessed**. The
operator's intent: a held Static Override is an **authoritative overlay** — while held
it wins over whatever automatic base is active (scripted OR autoloop); the instant it
is released or toggled off, output returns immediately to the underlying base. It loses
**only** to a real blackout/emergency (the safety kill zeroes first) and to
pack-disabled/shutdown. This matches the accepted manual-static policy
(`tests/test_state_manager_pack_driver.py:350-382`; RW-2 spec A.3) and the player
precedence (`render()` `:345-373`). "Deck is not a bridge-owned scripted track" is a
deck-authority condition, not blackout — so held static **should** stand. RW-3's change
is a correction toward that policy, making the unowned case behave like the
stale/track-change cases where static already stands. Tested by R10.

> **Lane nuance [C] (RW-8 boundary, not a regression).** On the bridge-native pack
> lane, the underlying base for an *autoloop* track is ZERO until RW-8 (native autoloop
> DMX is out of scope). So releasing a held static during an autoloop track returns the
> pack lane to ZERO, not an autoloop pack look; releasing during a *scripted* track
> returns to the scripted show. The live OS2L/SoundSwitch lane is unaffected. The
> overlay/release mechanics are correct on both (the driver reads `held_static_slot`
> each tick and calls `release_static` on release, `:3274-3280`).

### A.7 Corrected safety statement — automatic scripted base only [C]
RW-3 adds one necessary condition (`scripted_owned`) to `happy`, so for the **automatic
scripted base**: `happy_RW3 → happy_today`, hence it can only move render→ZERO, never
ZERO→render. RW-3 **cannot produce a new non-zero automatic scripted base**. The held
Static Override is a **separate layer** composed by the player after the base; per A.6
it may now stand alone in more unowned cases (an intended, blessed change). The prior
unqualified "never a new non-zero submitted frame" claim is retracted.

### A.8 Transition table (Investigation E) [C]/[A]
`scripted_owned ≡ int(getattr(d,"scripted_id",0) or 0) != 0`;
`norm_ssid ≡ _pack_normalize_id(ssid)`;
`play_identity ≡ (active, load_gen, scripted_id, norm_ssid)`. "Base" = automatic base;
held static composes independently (A.6).

| Transition | Authority that proves it | Automatic base |
|---|---|---|
| Fresh load, before resolve | `metadata_ready` False (`:2615`); `scripted_owned` False (`:2616`) | ZERO |
| Resolved, not scripted | `scripted_owned` False (`_arm_unscripted` `:3091`; or no auto-arm under `=0`) | ZERO |
| Resolved, scripted match, not yet armed | `scripted_owned` False until `SCRIPTED_ARM` (`:1248`) | ZERO (conservative) |
| Scripted armed + playing | `scripted_owned`+`metadata_ready`+`fresh`+`playing` | render `playing`; set latch=`play_identity` |
| Scripted, pause within hold | RW-2 latch + `happy`; `play_identity == hold key` | render `paused` ≤ `STOP_DEBOUNCE_S` |
| Scripted, pause past hold / stop | deadline expired / `was_playing` False | ZERO |
| **same-drain clear→re-resolve→arm (same identity), paused** | `_arm_unscripted` teardown (A.4) → hold key None | ZERO; needs fresh PLAY |
| bare re-arm / re-resolve to different scripted_id or ssid, paused | `play_identity` mismatch | ZERO; latch reset |
| scripted_id↔ssid mismatch (OSC/transfer, `=0`) | mode-only renders the **loaded** ssid (A.3 bound); player ZEROs if not in pack | render loaded ssid, or ZERO |
| Master switch / active change | `play_identity` deck change + `was_playing` False | ZERO until new deck observed playing |
| Track replacement (`load_gen` change) | `track_changed` True (`:3284`) + `play_identity` change | ZERO that tick |
| Return to autoloop / idle / stale / discontinuity | `scripted_owned`/`playing`/`fresh` False; `discont` True | ZERO |

### A.9 Constants & symbols (re-verified at `d97ff44`) [C]
`STOP_DEBOUNCE_S=0.5` (`config.py:74`); `MEM_STALE_S=3.0` (`config.py:62`);
`_PACK_SEEK_JUMP_MS=2000` (`state_manager.py:113`). Driver-local trackers init
`:358-363`; `_pack_play_hold_key` (`:361`) currently typed `tuple[int, int] | None`.
RW-3 adds **no** new instance field (it re-types the existing hold key) and **no new
helper** (the registry guard is removed). `_arm_unscripted` is at `:3087-3092`.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Touch only** `state_manager.py` — the `_drive_pack_output` gate block (`3296-3338`),
  the `_pack_play_hold_key` type comment (`:361`), and **a two-line teardown appended to
  `_arm_unscripted`** (`:3087-3092`, the single SCRIPTED_CLEAR consumer) — and
  `tests/test_state_manager_pack_driver.py`. Do **not** otherwise modify
  `_arm_unscripted`'s existing two writes, and do **not** modify
  `soundswitch_laser_player.py`, `soundswitch_pack_runtime.py`, `_update_lighting`,
  `_apply_lighting`, `_push_tick_inner`, `_on_filepath_resolved`, `_arm_scripted`,
  `_on_track_loaded`, `_on_master_changed`, other event handlers, OS2L/laser/LED lanes,
  config, scripted_tracks.py, or any startup/dataclass/import surface.
- **Out of scope — name the boundaries:** RW-4 (controller-input health — masks/static
  block `:3271-3280` unchanged); RW-5 (status/menubar — no status string/field/path/id/
  port; `sanitized_status()` untouched); RW-8 (native-DMX Autoloop — do **not** add
  `select_autoloop`; autoloop/idle ZERO via `clear_selection()`; test D10 stays green).
- The gate is **mode-only** (`scripted_id != 0`); **no registry/identity lookup** in the
  driver. The driver stays read-only w.r.t. `DeckState`/`OutputState` (reads
  `d.scripted_id`); the `_arm_unscripted` teardown writes only the driver-local
  `_pack_play_hold_*` push state. StateManager stays the sole `DeckState` writer (S7.1).
- ZERO path stays `clear_selection()`; never emit `transport="stopped"/"ended"/
  "unloaded"`. No filesystem/subprocess/MIDI/serial/socket/sleep/retry/blocking-queue
  added (S7.2). Injected `now` clock from RW-2 unchanged. Driver inert unless `rt.active`
  (`:3261-3262`); no enable/backend/restart/hardware.

### Task 1 — `state_manager.py`: mode-only gate + identity-aware hold latch
**1a. Bind the new gate terms** — replace the `metadata_ready` line at `:3298` and add
the mode/identity bindings immediately after it (reuse `ssid` `:3297`, `active` `:3266`,
and the EXISTING `load_key = (active, load_gen)` computed at `:3283`):
```python
            norm_ssid = _pack_normalize_id(ssid)              # RW-3: capture once
            metadata_ready = norm_ssid is not None
            # RW-3 mode authority: the bridge's scripted classification is
            # DeckState.scripted_id (the flag _update_lighting keys on, :3117), NOT a
            # syntactically valid UUID. Mode-only: do not consult the scripted registry
            # for identity (it false-zeros filepath-matched shows; see spec A.3).
            scripted_id = int(getattr(d, "scripted_id", 0) or 0)
            scripted_owned = scripted_id != 0
            # RW-3 temporal hold identity (A.4): bind the pause-hold to the full played
            # identity so a bare re-arm / re-resolve to a different scripted_id or ssid
            # cannot resurrect a stale paused frame. Same-identity clear->re-resolve->arm
            # is closed by the _arm_unscripted teardown (Task 2). Reuse load_key (:3283).
            play_identity = (*load_key, scripted_id, norm_ssid)
```

**1b. AND `scripted_owned` into `happy` and switch the hold latch to `play_identity`** —
replace `:3312-3330`:
```python
            happy = (
                fresh and metadata_ready and scripted_owned
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
                transport = None  # stopped/hold-expired/unloaded/stale/changed/discont/unowned
                if play_identity != self._pack_play_hold_key:
                    self._pack_play_hold_key = None
                    self._pack_play_hold_deadline = 0.0
```
Everything above (`:3266-3296`) and the `select_scripted(...)`/`clear_selection()`
calls (`:3331-3338`) and the `submit_frame` (`:3341`) stay unchanged.

**1c. Re-type the hold-key comment** at `:361`:
`self._pack_play_hold_key: tuple[int, int, int, str] | None = None  # play identity (active, load_gen, scripted_id, norm_ssid)`.

Commit: `feat(soundswitch): RW-3 mode-only scripted gate + identity-aware pause hold`.

### Task 2 — `state_manager.py`: de-ownership teardown in `_arm_unscripted`
Append to `_arm_unscripted` (`:3087-3092`), after the two existing writes:
```python
    def _arm_unscripted(self, deck: int) -> None:
        """Clear scripted state. Lighting machine re-evaluates next tick."""
        d = self._deck[deck]
        log.info("[SM] clear-scripted  deck=%d", deck)
        d.scripted_id = 0
        d.meta.soundswitch_id = ""
        # RW-3 (A.4): scripted de-ownership immediately disarms the pack pause-hold.
        # SCRIPTED_CLEAR is the only de-owner whose state a same-drain re-resolve+re-arm
        # can fully restore, so the 4-tuple play_identity cannot see the transient; tear
        # the latch down here. Same _run thread as the driver (no lock); push-local only.
        self._pack_play_hold_key = None
        self._pack_play_hold_deadline = 0.0
```
This is the **only** change to `_arm_unscripted`; do not alter its existing behavior.

Commit: `fix(soundswitch): RW-3 disarm pack pause-hold on scripted de-ownership`.

### Task 3 — `tests/test_state_manager_pack_driver.py`: seam + RW-3 cases + RW-2 fixup
**3a. Extend `_set`** (`:102-110`) with `scripted_id` (default keeps existing tests
unchanged) and add a second valid UUID absent from the pack:
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
The default keeps every existing driver-level test green (ssid=SSID → `scripted_owned`
True; ssid="" → ZERO on `metadata_ready`). No registry is consulted by the gate.

**3b. Add the RW-3 cases** (Part D R1–R10). For R9 import `SCRIPTED_TRACKS`/`register`
from `rb_ss_bridge_v2.scripted_tracks` and `addCleanup(lambda: SCRIPTED_TRACKS.pop(7,
None))`; **do not** double-register an id (round-2 MINOR).

**3c. Fix the one RW-2 assertion that pins the hold-key tuple.**
`test_master_switch_zeros_until_new_deck_confirmed` (`:308`) asserts
`sm._pack_play_hold_key == (2, 1)`; update to
`self.assertEqual(sm._pack_play_hold_key, (2, 1, 1, SSID))` (deck 2, load_gen 1, default
scripted_id 1, normalized SSID == SSID). Other `_pack_play_hold_key` assertions are
`assertIsNone` (`:199`, `:536`) — unaffected.

Commit: `test(soundswitch): RW-3 mode/hold/de-ownership cases; RW-2 hold-key fixup`.

### Task 4 — inner / event-path integration tests (real `_push_tick()`)
Add R6 and R8 driving the **real** path via `_push_tick()` (the `PackDriverInnerTickTests`
`_tick()` helper already calls `self.sm._push_tick()` at `:481`; do **not** call
`_push_tick_inner` directly and do **not** use `_set`). Both run under
`patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "0"})`.

Commit: `test(soundswitch): RW-3 inner autoloop-uuid zero + same-identity clear→arm`.

---

## Part C — Invariants that MUST still hold (live safety; maps to roadmap §7)

1. **S7.1 sole `DeckState` writer.** RW-3 only *reads* `d.scripted_id`; the
   `_arm_unscripted` teardown writes only driver-local `_pack_play_hold_*` push state.
2. **S7.2 push-loop purity.** Added work is in-memory only (a `getattr`/`int`, a UUID
   parse, tuple compares); the teardown is two attribute writes. No I/O/sleep/lock.
3. **S7.8 ZERO on unowned/stale/error/invalid.** `scripted_owned` + the existing
   fresh/track_changed/discont terms resolve every non-owned case to `clear_selection()`
   → ZERO; the roadmap "require `d.scripted_id`" gap is closed.
4. **RW-2 not regressed.** Paused branch requires `happy` (now incl. `scripted_owned`)
   and an exact `play_identity` match; a deck that loses scripted ownership cannot render
   a stale frame (`happy` False and/or `play_identity` mismatch and/or the
   `_arm_unscripted` teardown). A normal pause emits no `SCRIPTED_CLEAR` for the active
   deck, so the teardown never disturbs a legitimate hold (R1/R3 vs R8). `STOP_DEBOUNCE_S`
   and deadline math unchanged.
5. **S7.9 manual Static Override + blackout precedence.** Masks/static block (`:3271-3280`)
   and player precedence (`:345-373`) untouched. **Blessed change (A.6, operator-confirmed
   2026-06-24):** held static is an authoritative overlay — stands alone over the ZEROed
   base in unowned mode, returns to base on release; blackout/emergency still win first.
6. **No `transport="stopped"/"ended"/"unloaded"`.** ZERO stays `clear_selection()`.
7. **Corrected proof (A.7).** `happy_RW3 → happy_today` ⇒ no new non-zero **automatic
   scripted base**; the held-static layer is separate and blessed (C.5).
8. **S7.10/S7.11 default-off neutrality.** Inert unless `rt.active`; byte/order-neutral
   for OS2L/lasers/LEDs/Rekordbox/commands/logs when pack is absent/disabled/dry-run/none.
9. **S7.12 no leaks.** No new status string/path/id/port/byte; `sanitized_status()`
   untouched.
10. **Autoloop safe-zero (RW-8 boundary).** `select_autoloop` still uncalled; autoloop
    ZEROs.
11. **Mode-only identity bound ([C]).** The pack renders only the *loaded*
    `soundswitch_id`; a mismatched `scripted_id` (OSC/transfer under `=0`) can change
    *whether* it renders, never render a third track's content, and the player's
    `scripted_not_found` ZEROs an unloaded/absent ssid. No registry guard ⇒ no
    false-zero of filepath-matched/showfile-direct shows.

---

## Part D — Tests (pure seams; no device, no AppKit, no hardware)

`_pack()`: scripted SSID present; 0 ms CH1==5; 50/60 ms CH1==9; static slot 8 →
CH1==200. `SSID2` is a valid UUID **absent** from `_pack().scripted`.

**Driver-level (extended `_set`; explicit `scripted_id`):**
- **R1 `test_valid_ssid_but_unscripted_playing_zeros`** — `_set(ssid=SSID,
  elapsed_ms=50, playing=True, scripted_id=0)` → ZERO (core fix). Pre-RW-3: CH1==9.
- **R2 `test_scripted_owned_playing_still_renders`** — `_set(ssid=SSID, elapsed_ms=50,
  playing=True, scripted_id=7)` → CH1==9.
- **R3 `test_unscripted_pause_does_not_hold`** — play `scripted_id=7` (`now=t0`); then
  `playing=False, was_playing=True, scripted_id=0, now=t0+0.1`, same load_gen → ZERO,
  `_pack_play_hold_key is None`, `_pack_play_hold_deadline == 0.0`.
- **R4 `test_scripted_id_set_but_ssid_empty_zeros`** — `_set(ssid="", playing=True,
  scripted_id=7)` → ZERO (`metadata_ready` False).
- **R5 `test_unscripted_in_pack_with_held_static_shows_static`** — `_set(ssid=SSID,
  playing=True, scripted_id=0)` + `_FakeInput(held_static_slot=8)` → CH1==200.
- **R7 `test_pause_hold_not_resurrected_by_scripted_id_change`** — play `ssid=SSID,
  scripted_id=1, load_gen=1, now=t0`; then `ssid=SSID, scripted_id=2, playing=False,
  was_playing=True, load_gen=1, now=t0+0.1` → ZERO (`play_identity (1,1,2,SSID) != hold
  key`), `_pack_play_hold_key is None`.
- **R9 `test_mode_only_ignores_registry_identity`** (round-2 MAJOR + MINOR) — three
  parts, registering ONE stale entry with explicit cleanup:
  - `register(7, {"name": "x", "ssid": SSID2})`;
    `addCleanup(lambda: SCRIPTED_TRACKS.pop(7, None))`.
  - **filepath-match stale-ssid renders:** `_set(ssid=SSID, playing=True,
    scripted_id=7)` → CH1==9 (the gate does NOT consult the registry; the stale
    `ssid=SSID2` does not false-zero the in-pack `ssid=SSID`).
  - **bounded mismatch, loaded ssid absent from pack → ZERO:** `_set(ssid=SSID2,
    playing=True, scripted_id=7)` → ZERO (player `scripted_not_found`; never a third
    track). Documents the mode-only identity bound (A.3/C.11).
- **R10 `test_valid_uuid_missing_from_pack_with_held_static`** (round-1 Obj 2) —
  `_set(ssid=SSID2, playing=True, scripted_id=0)` + `_FakeInput(held_static_slot=8)` →
  CH1==200. Comment: pre-RW-3 ZEROs (player suppresses static); RW-3 lets held static
  stand (blessed, A.6/C.5).

**Inner / event-path (`PackDriverInnerTickTests`; drive `_push_tick()` via `_tick()`):**
- **R6 `test_inner_autoloop_uuid_stays_zero`** — under `patch.dict(os.environ,
  {"RBSS_SCRIPTED_DIRECT": "0"})`: `TRACK_LOADED`, then `_on_filepath_resolved` with
  valid `soundswitch_id=SSID` (no auto-`SCRIPTED_ARM` under `=0`, so `scripted_id`
  stays 0), then `PLAY` + `_tick()`. Assert **both** `self.sm._os.lighting_mode ==
  "autoloop"` and frame `== ZERO_FRAME`. Pre-RW-3 renders CH1==9. *(Confirmed purely
  exercisable against current code: the inner autoloop path runs without raising,
  lighting_mode reaches "autoloop", and current code renders CH1==9 — so no `[U]`
  escape.)*
- **R8 `test_inner_same_identity_clear_resolve_arm_while_paused_zeros`** (round-2
  BLOCKER) — under `RBSS_SCRIPTED_DIRECT="0"`: `_load_scripted` (load_gen=1,
  scripted_id=7 via direct `_event(SCRIPTED_ARM, {"scripted_id":7})`), `_start_playing`
  (latch set), `Ev.PAUSE`, `_tick()` → CH1==9 (held). Then, before the next `_tick()`,
  in one simulated drain apply **the exact sequence**:
  `_event(Ev.SCRIPTED_CLEAR)` → `_on_filepath_resolved(1, {... "soundswitch_id": SSID,
  "load_gen": <same> ...})` (restores SSID; `=0` ⇒ no auto-arm) →
  `_event(Ev.SCRIPTED_ARM, {"scripted_id": 7})` (restores scripted_id 7). Then `_tick()`
  → assert frame `== ZERO_FRAME` **and** `self.sm._pack_play_hold_key is None` (the
  `_arm_unscripted` teardown disarmed the hold; the byte-identical `play_identity` did
  NOT resurrect it). This is the sequence the old R8 missed.

**Regression — green unchanged after 3a/3c:** D1–D14, the RW-2 driver tests, the three
`PackDriverInnerTickTests` RW-2 timing tests, and the manual-static-policy tests
(`:350-382`). The `scripted_id` default and the single 3c tuple fixup keep them all
rendering/zeroing as before; the `_arm_unscripted` teardown is dormant in tests that do
not issue a SCRIPTED_CLEAR.

---

## Part E — Acceptance (definition of done)

- [ ] `_drive_pack_output` ANDs `scripted_owned` into `happy` (mode-only; **no** registry
      identity lookup); the pause-hold latch is keyed by `play_identity = (active,
      load_gen, scripted_id, norm_ssid)`; the else-branch resets on `play_identity != hold
      key`. `_arm_unscripted` tears the latch down (`_pack_play_hold_key=None`,
      `_pack_play_hold_deadline=0.0`). Diff confined to the gate block + the two-line
      `_arm_unscripted` append + the `:361` comment in `state_manager.py`, and the test
      file. No new instance field; no helper; no `DeckState`/`OutputState`/player/runtime/
      config/startup/scripted_tracks change.
- [ ] R1–R10 pass (R6/R8 via `_push_tick()`); existing D1–D14 and all RW-2 driver and
      inner-tick tests green after the `_set` default and the single 3c tuple fixup.
- [ ] Invariants C.1–C.11 hold; the automatic-base-only proof (C.7/A.7); the blessed
      held-static policy (C.5/A.6, R10); RW-2 non-regression (R3/R7/R8 + the unchanged
      RW-2 suite); the de-ownership teardown completeness (A.4, R8); the mode-only
      identity bound (C.11, R9).
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
      commit; re-verify the `soundswitch_output`/`soundswitch_pack_player` contract docs
      before bumping `last_verified_commit`. `state_manager.py` is already in the
      `soundswitch_pack_player` contract globs (`change_contracts.yml:249`) — no contract
      extension required.

## When you finish
Commit per task. Report back: the gate diff, the `_arm_unscripted` teardown, the `_set`
seam change, the 3c tuple fixup, the new test names with pass counts, the proof-gate
verdict (expect `PASS_IMPLEMENTATION_MAY_BEGIN`, 29/0/0), full-suite + hard-docs-check
results. Provide an updated reviewer prompt in your final response.

---

## Appendix 1 — Review rounds 1 & 2 objection closure

| Round/sev | Objection | Fix | Where |
|---|---|---|---|
| R1 BLOCKER | hold latch not identity-aware | 4-tuple `play_identity` | A.4, B.1 |
| R1 MAJOR | strict-narrowing proof false under held static | narrowed to automatic base; static blessed | A.6/A.7, C.5/C.7, D R10 |
| R1 MAJOR | `scripted_id != 0` ≠ identity coupling | mode-only + bounded harm (pack renders loaded ssid only) | A.3, C.11, D R9 |
| R1 MAJOR | R6 drove `_push_tick_inner` but asserted a frame | R6 drives `_push_tick()` | D R6, B.Task 4 |
| R1 MINOR | coverage | R6/R7/R8/R9/R10 | D |
| **R2 BLOCKER** | same-identity clear→re-resolve→arm resurrects hold | `_arm_unscripted` latch teardown + completeness proof | A.4, B.Task 2, D R8 |
| **R2 MAJOR** | `scripted_identity_ok` false-zeros filepath match; "restart recovers" false | registry guard removed → mode-only; false claim deleted | A.3, C.11, D R9 |
| **R2 MINOR** | R9 double-`register()` is a no-op | single register + `addCleanup` pop | D R9, B.3b |

## Appendix 2 — 9-point pre-handoff checklist (run against this revision)

1. **Claims labeled C/A/U/P.** ✅ A.3/A.4/A.6 labeled; the de-ownership completeness and
   mode-only bound are [C]; the held-static blessing is [P] operator-confirmed.
2. **Verified against CURRENT code (`d97ff44`).** ✅ Re-read this pass: `_arm_unscripted`
   call-site/thread (`:1255`→`:1089`→`_run`), latch writers (`:3316`,`:3329`),
   `resolve_filepaths` ssid guard (`scripted_tracks.py:82`), filepath-match path
   (`:2938-2945`), register-once semantics (`:29`). Runtime code byte-identical to
   `e295e37`.
3. **Pending-state guard (all same-tick fields).** ✅ Composes with RW-2 latch (now
   torn down on de-ownership), held static + blackout (untouched, R5/R10),
   track_changed/discont (A.8).
4. **Mode-transition cleanup on every path.** ✅ A.4 completeness table: every de-owner
   is caught (load_gen monotonic, active, `was_playing`, or the new teardown).
5. **Third-party API completeness.** ✅ `select_scripted(...)`/`clear_selection()` shapes
   (`:3331-3338`) reproduced verbatim and unchanged; no new player/registry call in the
   driver.
6. **Cross-checked against existing authority vars.** ✅ Canonical `d.scripted_id`
   (== `_update_lighting:3117`) and `d.meta.soundswitch_id`/`metadata_ready`; `load_key`
   reused for `play_identity`; `os.lighting_mode` deliberately not ANDed (A.5).
7. **Pure-function test seam.** ✅ R1–R10 via `_set` or the inner-tick harness (injected
   clock + real `PositionCache`); R9 uses the in-memory registry global with `addCleanup`
   pop. R6/R8 confirmed exercisable.
8. **Live safety explicit.** ✅ Part C maps S7.1/7.2/7.8/7.9/7.10–7.12; automatic-base-only
   proof; held-static blessed; ZERO-on-uncertainty default; the teardown is fail-closed.
9. **Adversarial self-review (forced failures).** ✅ (a) *same-identity clear→re-resolve→
   arm while paused* → `_arm_unscripted` teardown nulls the latch before the driver runs
   (R8). (b) *filepath-match with stale registry ssid* → mode-only renders (no registry
   guard, R9). (c) *OSC/transfer mismatch* → renders the loaded ssid, or ZEROs if not in
   pack; never a third track (A.3/C.11). (d) *valid UUID not in pack + held static* →
   blessed static stand-alone (R10). (e) *cross-deck SCRIPTED_CLEAR during a hold* → tears
   down the active hold; fail-closed, bounded to the 0.5 s window, and a normal pause emits
   no such clear (A.4). (f) *honesty* → "restart recovers" deleted; severity stated as
   explicit-authority + de-ownership safety, not "actively wrong right now."

**Verdict: all 9 pass; rounds 1 & 2 objections closed — Codex-ready (pending re-review).**
