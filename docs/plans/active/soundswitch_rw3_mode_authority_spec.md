---
doc_status: active-plan
truth_level: code-grounded-design-spec
last_verified_commit: e295e37
last_verified_date: 2026-06-24
validation_scope: RW-3 scripted/autoloop/idle mode-authority gate for the bridge-native CH1-CH19 pack driver; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; default-off (enabled=false, dry_run=true, output_backend=none) — no restart/enable/backend/hardware authorized
---

# Codex Implementation Spec — RW-3 Explicit scripted/autoloop/idle mode-authority gate

> **Scope.** This spec closes the second M2 dependency: the SoundSwitch pack
> driver decides *whether it owns a scripted base at all* from the wrong signal.
> It infers "this is a scripted track" purely from a syntactically-valid embedded
> `soundswitch_id`, instead of the bridge's actual scripted-mode authority
> (`DeckState.scripted_id`, the same flag `_update_lighting` uses for the OS2L /
> laser / LED lanes). RW-3 adds one explicit mode-authority term to the existing
> happy-path gate so the pack honors the same scripted/autoloop/idle decision as
> every other lane, and ZEROs when the deck is not a bridge-owned scripted track.
>
> **Roles.** Opus authored this; **Codex implements it**. No implementation,
> output enable, backend change, restart, or hardware action is authorized by this
> document. Pack output stays default-off (`enabled=false`, `dry_run=true`,
> `output_backend=none`).
>
> **Builds on, does not reopen:** RW-1A (shutdown zero) and RW-2 (pause-vs-stop
> transport latch) are done and software-tested. RW-3 composes with the RW-2 latch
> and changes one predicate; it must not regress RW-2 (see Part C.4 / D).
>
> **Evidence labels:** **[C]** confirmed in current code at `e295e37` (read this
> session) · **[A]** assumed / inferred but not directly executed · **[U]** needs
> live/hardware evidence (none promoted by software inference).

---

## Part A — Context & root cause (verified; read, do not implement)

### A.1 What happens today — the pack driver's "is this scripted?" test [C]
The 200 Hz push loop drives the pack output once per tick from
`StateManager._drive_pack_output()` (`state_manager.py:3253`), called by `_push_tick`
(`state_manager.py:3233`, after `_push_tick_inner()` returns). The scripted-base
happy gate is computed at `state_manager.py:3296-3312`:

```python
playing = bool(getattr(d, "playing", False))                      # 3296
ssid = getattr(getattr(d, "meta", None), "soundswitch_id", "") or ""   # 3297
metadata_ready = _pack_normalize_id(ssid) is not None             # 3298
...
happy = fresh and metadata_ready and not track_changed and not discont   # 3312
```

- **[C]** `_pack_normalize_id` is `normalize_soundswitch_id`
  (`state_manager.py:66` import; `soundswitch_laser_player.py:166-177`). It returns
  non-`None` for **any exact UUID** — it "never inspect[s]/fuzzy-match[es] paths"
  and has **no notion of which tracks are scripted shows**. So `metadata_ready`
  answers only "does this track carry a well-formed SoundSwitch UUID?", **not** "is
  this a bridge-owned scripted track?".
- **[C]** `_drive_pack_output` reads `active = self._os.active_deck`
  (`state_manager.py:3266`) and `d = self._deck[active]` (`:3267`) but **never reads
  `d.scripted_id` or `self._os.lighting_mode`.** The whole-bridge scripted-mode
  authority is invisible to the pack lane.

### A.2 The bridge's real scripted-mode authority is `d.scripted_id` [C]
Every other lane derives scripted-vs-autoloop-vs-idle from `DeckState.scripted_id`
(`models.py:83`, an `int`; `0` = unscripted/none), **not** from
`meta.soundswitch_id` (`models.py:35`, a `str`):

- **[C]** `_update_lighting` (`state_manager.py:3096`): `desired = "scripted"` iff
  `d.scripted_id and is_playing` (`:3117-3118`), else `"autoloop"` if playing
  (`:3119-3120`), else `"idle"` (`:3121-3122`); it writes `os.lighting_mode`
  (`:3145`). The OS2L/laser/LED lanes follow that.
- **[C]** The two identifiers are written by **different events**:
  - `meta.soundswitch_id` ← `FILEPATH_RESOLVED` payload
    (`_on_filepath_resolved`, `state_manager.py:2878`), set for **any** track that
    carries an embedded SoundSwitch UUID, scripted or not.
  - `scripted_id` ← `SCRIPTED_ARM` handler (`state_manager.py:1242-1248`, sets
    `d.scripted_id = sid`) and `_arm_scripted` (`:3014`); cleared by `SCRIPTED_CLEAR`
    → `_arm_unscripted` (`:3091`), by `_on_track_loaded` (`:2616`), and by
    `RB_RESTARTED` (`:1263`).

So **`metadata_ready` and `scripted_id` are not the same authority.** The pack
driver gates on the former; the rest of the bridge gates on the latter.
(VERIFIED STARTING FACT #2 in the task prompt called these "decoupled today"; A.3
below resolves *exactly when* the driver can observe them diverge — the honest
answer is narrower than "always," but the fix is the same.)

### A.3 Investigation A resolved — when can the driver actually observe `soundswitch_id` valid while `scripted_id == 0`? [C]
This is the crux. The answer depends on `RBSS_SCRIPTED_DIRECT` and on event-drain
ordering. I traced both.

**Drain ordering [C].** `_run()` (`state_manager.py:872-877`) calls
`_drain_events()` **then** `_push_tick()` each tick. `_drain_events()`
(`:1070-1076`) is an exhaustive `while True: get_nowait()` loop — it consumes
**every** pending event, *including events enqueued during the same drain*, until
`queue.Empty`. `_on_filepath_resolved` enqueues its follow-on `SCRIPTED_ARM`
(`:2960-2965`) or `SCRIPTED_CLEAR` (`:2971-2975`) via `put_nowait` **into the same
queue being drained**, so the follow-on is normally consumed in the **same drain
pass**, before `_push_tick` → `_drive_pack_output` runs.

**Direct mode (live default), healthy queue [C].** With `RBSS_SCRIPTED_DIRECT !=
"0"` (the gate at `state_manager.py:2920`; live flags run the direct paths on):
- Non-scripted track with an embedded UUID: `_on_filepath_resolved` sets
  `meta.soundswitch_id` (`:2878`) **and** enqueues `SCRIPTED_CLEAR` (`:2971`) →
  `_arm_unscripted` (`:3087-3092`) which **clears `meta.soundswitch_id = ""`**
  (`:3092`) and `scripted_id = 0` (`:3091`) in the same drain. Net state the driver
  sees: `soundswitch_id == ""` → `metadata_ready` False → **pack already ZEROs.**
- Scripted track: same drain sets `soundswitch_id` and `scripted_id = sid`
  (`SCRIPTED_ARM`, `:1248`). Net: both set → pack renders. Correct.

So in the **common live path the pack already ZEROs non-scripted tracks** — **but
only as an incidental side effect of `_arm_unscripted` clearing
`meta.soundswitch_id`** (`:3092`), a clear that exists for personality/autoloop
reasons, not as a deliberate pack-mode gate. The pack's current non-scripted
correctness is **accidental, not explicit.** [C]

**Where the driver *can* observe the divergence (valid SSID + `scripted_id == 0`):**
1. **[C] Durably under `RBSS_SCRIPTED_DIRECT == "0"` (legacy/OSC arming).** The
   whole `:2920` block is skipped, so **no** `SCRIPTED_ARM`/`SCRIPTED_CLEAR` is
   emitted from filepath resolution; `meta.soundswitch_id` stays set (`:2878`) for
   non-scripted tracks while `scripted_id` is driven only by external OSC (which may
   never arrive, or land on the other deck via the `_on_master_changed` transfer at
   `:2559-2568`). `_update_lighting` then reports `"autoloop"`, while the pack would
   render a **scripted** base. This is the real, durable bug.
2. **[A] When `SCRIPTED_CLEAR` is dropped on a full queue.** The enqueue is
   `put_nowait` guarded by `except queue.Full` (`:2976-2977`) — on saturation the
   clear is logged and dropped, leaving `soundswitch_id` set and `scripted_id == 0`
   until the next track event. Queue boundedness in production is **[A]** (tests use
   an unbounded `queue.Queue()`); the code path exists.
3. **[A] Defense-in-depth.** Even in the common path, the pack's correctness hangs
   on the unrelated `:3092` clear. If that incidental clear were ever changed, the
   pack would silently begin rendering non-scripted UUID tracks. An explicit gate
   removes that latent coupling.

**Honest severity.** Under the **current live flags** the common path already ZEROs
non-scripted tracks, so this is **not** "the rig is rendering wrong content right
now." It is: (a) a **real** divergence under the legacy `RBSS_SCRIPTED_DIRECT=0`
flag and on queue-drop; and (b) a **structural** gap — the pack lane does not
consult the bridge's scripted-mode authority and is correct only by accident. RW-3
makes the pack honor `scripted_id` explicitly, matching the roadmap requirement
("require `d.scripted_id`… do not render an SSID merely because it is syntactically
valid", `soundswitch_exporter_remaining_work.md:377-381`).

### A.4 The chosen authority variable: `d.scripted_id`, not `os.lighting_mode` [C]/[A]
The task lists `active_deck`, `d.scripted_id`, `d.meta.soundswitch_id`,
`os.lighting_mode`, transport, and fresh-position as the available authorities. The
gate **reuses all of them**, but the new *hard predicate term* is `d.scripted_id`,
and `os.lighting_mode` is deliberately **not** ANDed in. Rationale (Investigation B):

- **[C] `d.scripted_id` is read in-tick off the same `d = self._deck[active]` the
  driver already holds.** It needs no cross-function ordering guarantee. It is the
  *same* per-deck authority `_update_lighting` keys on (`:3117`), so the pack and
  OS2L lanes agree by construction.
- **[C] `os.lighting_mode` is a derived, debounced, possibly-stale view of the same
  signal.** `_update_lighting` runs inside `_push_tick_inner` (`:3411`, `:3523`)
  *before* the driver runs in the `_push_tick` wrapper (`:3233`) — so on a normal
  tick `lighting_mode` is same-tick fresh. **But** it lags in two ways the pack must
  not inherit:
  1. **Idle-debounce lag.** `_update_lighting` returns early without updating
     `lighting_mode` during the stop/idle debounce window (`:3133-3134`), so after a
     scripted track pauses, `lighting_mode` *stays* `"scripted"` for up to
     `STOP_DEBOUNCE_S` (or the autoloop idle-debounce). That lag happens to align
     with the RW-2 pause hold, but it makes `lighting_mode` an *indirect* proxy.
  2. **Early-return skips.** When inner takes the stale-while-playing early return
     (`:3384-3406`), `_update_lighting` is not called at all; `lighting_mode` keeps
     its prior value. (Safe here only because that path also implies `fresh=False`.)
- **[A] Net:** ANDing `os.lighting_mode == "scripted"` would couple the pack to the
  idle-debounce timing and the inner early-return paths, adding fragility **without
  adding safety** — `d.scripted_id` already encodes scripted ownership without those
  hazards, and is strictly fresher. So `os.lighting_mode` is used as a documented
  **cross-check** (it is, by `_update_lighting`'s own rule, `"scripted"` iff
  `d.scripted_id and is_playing`), not as a gate term. `active_deck` is already in
  the gate (`:3266`); transport and fresh-position are unchanged from RW-2.

### A.5 The player already fails closed on `scripted_not_found`, but that is a *different* key space [C]
`LaserPackPlayer._scripted_base` (`soundswitch_laser_player.py:271-315`) ZEROs with
`scripted_not_found` (`:298-301`) when `self._pack.scripted.get(normalized)` misses.
That is **not** a substitute for RW-3: the pack's `scripted` dict is keyed by SSID
and authored **independently** of the bridge's runtime scripted authority. A UUID
can be present in the pack (player would render it) while the bridge treats the
deck as autoloop (`scripted_id == 0`). RW-3 gates on the **bridge's** authority so
the pack lane never renders a base the OS2L lane is treating as autoloop, regardless
of what the pack happens to contain. The gate is enforced **driver-side** (the
existing `select_scripted` call already hard-codes `metadata_ready=True,
authority="fresh", source_errored=False, elapsed_discontinuous=False,
track_changed=False`, `:3334-3335`; the decision lives in StateManager, not the
player).

### A.6 The reverse decoupling (`scripted_id != 0` but `soundswitch_id == ""`) is already safe [C]
`_arm_scripted` sets `scripted_id = track_id` (`:3014`) but only sets
`meta.soundswitch_id` from the registry **if it is still empty** (`:3024-3025`); a
scripted track matched **by filepath** with no embedded UUID ends up
`scripted_id != 0`, `soundswitch_id == ""`. Today and after RW-3 that ZEROs via
`metadata_ready` (no UUID → no pack key). RW-3 ANDs `scripted_owned` **with** the
existing `metadata_ready`; neither alone authorizes a render. So this case is
unchanged — the pack needs **both** a bridge-owned scripted classification **and** a
usable UUID key.

### A.7 Why RW-3 is maximally live-safe — the one-line safety proof [C]
RW-3 adds a **necessary** condition to `happy` (`happy = fresh and metadata_ready
and scripted_owned and not track_changed and not discont`). A strictly-narrower
`happy` can only move ticks **from render to ZERO**, never the reverse:

> For any deck state, `happy_RW3 → happy_today`. Therefore every tick that ZEROs
> today still ZEROs; only some ticks that render today will now ZERO. RW-3 can
> **never** cause a non-zero frame on a tick that is ZERO today.

So RW-3 **cannot introduce a new non-zero output** under any input — the only
behavior change is *more* ZEROing (the intended fix), under the unchanged default-off
posture. This is the core invariant the reviewer should verify.

### A.8 The transition table the gate must satisfy (Investigation E) [C]/[A]
`scripted_owned ≡ int(getattr(d, "scripted_id", 0) or 0) != 0`. "Base" is the
*automatic* base only; a held manual Static Override is independent (Part C.6).

| Transition | Authority that proves it | Desired automatic base |
|---|---|---|
| Fresh load, before resolve | `metadata_ready` False (meta cleared, `:2615`); `scripted_owned` False (`:2616`) | **ZERO** |
| Filepath resolved, **not** scripted (no registry/showfile match) | `scripted_owned` False (no `SCRIPTED_ARM`; or `_arm_unscripted` cleared, `:3091`) | **ZERO** |
| Filepath resolved, scripted match, **not yet armed** | `scripted_owned` False until `SCRIPTED_ARM` processed (`:1248`) | **ZERO** (conservative; arms within same drain normally) |
| Scripted match armed + playing | `scripted_owned` True + `metadata_ready` + `fresh` + `playing` | render `transport="playing"` |
| Scripted, pause within hold | RW-2 latch + `happy` (now incl. `scripted_owned`, still True on pause) | render `transport="paused"` ≤ `STOP_DEBOUNCE_S` |
| Scripted, pause past hold / stop | RW-2 deadline expired / `was_playing` False | **ZERO** (`clear_selection`) |
| Master switch / active-deck change | `load_key` identity change → RW-2 latch reset (`:3326-3330`) | **ZERO** until new deck observed playing |
| Track replacement (`load_gen` change) | `track_changed` True (`:3284`) | **ZERO** that tick |
| Return to autoloop (unscripted track plays) | `scripted_owned` False → `happy` False | **ZERO** (autoloop pack base is RW-8, out of scope) |
| Return to idle (stop) | `playing`/`was_playing` False; `_update_lighting` → idle | **ZERO** |
| Stale position | `fresh` False (`:3295`) | **ZERO** |
| Elapsed discontinuity | `discont` True (`:3289-3294`) | **ZERO** that tick |
| **Mode flip mid-play: `scripted_id` cleared while same `load_gen`** | `scripted_owned` False → `happy` False; latch reset on de-ownership (Task 1c) | **ZERO**; cannot resurrect a paused hold |

### A.9 Constants & facts the gate relies on (re-verified at `e295e37`) [C]
- `STOP_DEBOUNCE_S = 0.5` (`config.py:74`); `MEM_STALE_S = 3.0` (`config.py:62`);
  `_PACK_SEEK_JUMP_MS = 2000` (`state_manager.py:113`); `ARM_GUARD_S = 3.0`
  (`config.py:75`).
- Driver-local trackers init at `state_manager.py:358-363`: `_pack_last_load_gen`,
  `_pack_last_elapsed_ms`, `_pack_last_static_slot`, `_pack_play_hold_key` (`:361`),
  `_pack_play_hold_deadline` (`:362`). RW-3 adds **no** new instance field.
- `was_playing` writers: `_on_master_changed` (`:2580`), `RB_RESTARTED` (`:1271`),
  and `_do_stop` (RW-2 path). Unchanged by RW-3.

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Touch only** `state_manager.py` (the `_drive_pack_output` gate block at
  `3296-3338`) and `tests/test_state_manager_pack_driver.py`. Do **not** modify
  `soundswitch_laser_player.py`, `soundswitch_pack_runtime.py`, `_update_lighting`,
  `_apply_lighting`, `_push_tick_inner`, `_on_filepath_resolved`, `_arm_scripted`,
  `_arm_unscripted`, the OS2L/laser/LED lanes, config, or any startup/dataclass/
  import surface.
- **Out of scope — name the boundaries so the change does not bleed:**
  - **RW-4 (controller-input health fail-to-zero):** do **not** read
    `worker_alive`/`error`/`mail_drop_count` (`soundswitch_midi_input.py:36-47`); the
    masks/static block at `state_manager.py:3271-3280` is **unchanged**.
  - **RW-5 (status/menubar):** add **no** status string, field, path, id, or port;
    `sanitized_status()` untouched.
  - **RW-8 (native-DMX Autoloop):** do **not** add `select_autoloop`. Autoloop and
    idle modes ZERO via `clear_selection()`. The "autoloop never called" guard
    (test D10) must stay green.
- The gate stays **driver-local and read-only** w.r.t. `DeckState`/`OutputState`:
  RW-3 only *reads* `d.scripted_id`. `StateManager` remains the sole `DeckState`
  writer (S7.1). No new transport owner.
- The ZERO path stays `clear_selection()` (never `transport="stopped"/"ended"/
  "unloaded"`), preserving the held-static-stands-alone policy (RW-2 A.3, Part C.6).
- No filesystem/subprocess/MIDI/serial/socket/sleep/retry/blocking-queue work added
  (S7.2). The injected `now` clock from RW-2 is unchanged.
- **Default-off neutral:** the driver is already inert unless `rt.active`
  (`:3261-3262`); RW-3 adds no enable, backend change, restart, or hardware open.

### Task 1 — `state_manager.py`: add the `scripted_owned` authority term to the gate
**1a. Bind `scripted_owned`** next to the existing gate bindings, immediately after
the `metadata_ready` line at `state_manager.py:3298`:

```python
            metadata_ready = _pack_normalize_id(ssid) is not None
            # RW-3: the bridge's scripted-mode authority is DeckState.scripted_id
            # (the same flag _update_lighting keys on, :3117), NOT a syntactically
            # valid soundswitch_id. A valid UUID alone does not make a deck a
            # bridge-owned scripted track (see spec Part A.2/A.3). getattr keeps the
            # synthetic test harness safe, mirroring getattr(d, "playing", ...).
            scripted_owned = int(getattr(d, "scripted_id", 0) or 0) != 0
```

**1b. AND `scripted_owned` into `happy`** at `state_manager.py:3312` — change the one
line:

```python
            # was: happy = fresh and metadata_ready and not track_changed and not discont
            happy = (
                fresh and metadata_ready and scripted_owned
                and not track_changed and not discont
            )
```

Everything else in the transport-derivation block (`:3313-3338`: `was_playing`, the
`playing`/`paused`/`None` branches, the `select_scripted` call, the
`clear_selection()` fallback, and the `submit_frame` at `:3341`) stays **unchanged**,
**except** the one-line latch-reset hardening in 1c.

**1c. Harden the latch reset for mode de-ownership** (Part C.4 / A.8 last row).
The RW-2 else-branch resets the hold latch only on identity change
(`state_manager.py:3326`). Extend that single condition so a deck that **loses
scripted ownership** while keeping the same `load_gen` cannot later resurrect a
paused hold:

```python
            else:
                transport = None  # stopped / hold-expired / unloaded / stale / changed / discont / not-scripted
                if load_key != self._pack_play_hold_key or not scripted_owned:
                    # New identity (track replaced / deck switched) OR scripted
                    # ownership lost: a prior track's hold must not resurrect. Only a
                    # real PLAY of a scripted-owned THIS-key deck re-enables (3314-3317).
                    self._pack_play_hold_key = None
                    self._pack_play_hold_deadline = 0.0
```

> This is safe for normal pause: a paused scripted track still has
> `scripted_owned == True` (pause does not touch `scripted_id`) and is handled by the
> `elif … paused` branch **before** the else, so the extra reset never fires on a
> legitimate hold (proven by RW-2 tests T1/T4/T5, which keep `scripted_id` set).

Commit: `feat(soundswitch): RW-3 gate scripted pack base on DeckState.scripted_id`.

### Task 2 — `tests/test_state_manager_pack_driver.py`: extend the seam + add RW-3 cases
**2a. Extend `_set`** (`tests/test_state_manager_pack_driver.py:102-110`) to carry
`scripted_id` onto the synthetic deck, defaulting so every existing test is
unchanged (a track with an `ssid` is, by these tests' convention, a scripted track):

```python
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

The default `scripted_id = 1 if ssid else 0` keeps **all** existing driver-level
tests green: every `ssid=SSID` render test gets `scripted_owned True`; every
`ssid=""` test already ZEROs on `metadata_ready`. Confirm the full existing module
still passes after this edit before adding new cases.

**2b. Add the RW-3 driver-level cases** (Part D R1–R5). All use the real
`LaserPackPlayer` over `_pack()` and the `_FakeBackend` recorder; pass `now`
explicitly where the hold deadline matters.

Commit: `test(soundswitch): RW-3 valid-SSID-but-unscripted zeros; scripted still renders`.

### Task 3 — inner / event-path integration test for the durable decoupling
The driver-level cases prove the predicate. Add **one** real-path test (Part D
R6) that drives `_push_tick_inner` under `RBSS_SCRIPTED_DIRECT="0"` so a track
resolves a **valid** `soundswitch_id` while `scripted_id` stays `0` (the durable
A.3 case), and asserts **both** lanes: `os.lighting_mode == "autoloop"` **and** the
pack frame is `ZERO_FRAME`. This is the case the gate uniquely fixes — pre-fix it
would render the scripted frame (CH1==9); the assertion only passes post-fix.
Use the `PackDriverInnerTickTests` harness (injected clock + real `PositionCache`)
and `unittest.mock.patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "0"})`.

Commit: `test(soundswitch): RW-3 inner-path autoloop UUID stays zero (direct=0)`.

---

## Part C — Invariants that MUST still hold (live safety; maps to roadmap §7)

1. **S7.1 sole `DeckState` writer.** RW-3 only *reads* `d.scripted_id`; it writes
   only the existing driver-local `_pack_play_hold_*` fields. StateManager stays the
   only `DeckState` writer.
2. **S7.2 push-loop purity.** One extra in-memory `getattr`/`int` comparison; no I/O,
   sleep, retry, lock, or blocking added.
3. **S7.8 automatic base ZEROs on unowned/stale/error/invalid identity.** The new
   `scripted_owned` term makes "unowned mode" (`scripted_id == 0`, i.e. autoloop/idle
   per `_update_lighting`) resolve to `clear_selection()` → ZERO, closing the
   roadmap gap "require `d.scripted_id`; do not render an SSID merely because it is
   syntactically valid."
4. **RW-2 not regressed.** The paused branch requires `happy`, which now includes
   `scripted_owned`; a deck that was scripted-playing then loses scripted ownership
   (`scripted_id` cleared) **cannot** render a stale scripted frame through the hold
   window — `happy` goes False **and** Task 1c resets the latch on de-ownership.
   Normal pause/resume/expiry/identity-reset behavior is byte-identical (the new term
   stays True across a pause). The RW-2 latch fields, deadline math, and
   `STOP_DEBOUNCE_S` bound are unchanged.
5. **S7.9 / manual Static Override + blackout precedence unchanged.** The masks/static
   block (`:3271-3280`) and the player's precedence (`render()`
   `soundswitch_laser_player.py:345-373`) are untouched. A held Static Override still
   stands alone over a ZEROed automatic base (the ZERO path stays
   `clear_selection()`), and blackout/emergency still win first. RW-3 changes only
   the **automatic** base, never the controller path (RW-4 boundary respected).
6. **No `transport="stopped"/"ended"/"unloaded"` emitted.** ZERO stays
   `clear_selection()`; held static is not suppressed.
7. **Strict-narrowing safety proof (A.7).** `happy_RW3 → happy_today`; RW-3 can only
   convert renders to ZEROs, never create a new non-zero frame. No new output can
   appear under any input.
8. **S7.10/S7.11 default-off neutrality.** Driver still no-ops unless `rt.active`; no
   implicit enable, backend, restart, or hardware. With pack absent/disabled/dry-run/
   `output_backend=none` the change is byte/order-neutral for OS2L, lasers, LEDs,
   Rekordbox readers, commands, and logs.
9. **S7.12 no leaks.** No new status string/path/id/port/byte; `sanitized_status()`
   untouched (RW-5 owns status).
10. **Autoloop stays safe-zero (RW-8 boundary).** `select_autoloop` is still never
    called; autoloop mode ZEROs rather than rendering an autoloop pack base.

---

## Part D — Tests (pure seams; no device, no AppKit, no hardware)

`_pack()` frame: at 0 ms CH1==5; at 50/60 ms CH1==9; `ZERO_FRAME` is all zeros.
Static slot 8 → CH1==200.

**Driver-level (extended `_set`; explicit `scripted_id`):**
- **R1 `test_valid_ssid_but_unscripted_playing_zeros`** — `_set(ssid=SSID,
  elapsed_ms=50, playing=True, scripted_id=0)` → **ZERO** (the core fix: valid UUID,
  `scripted_id==0`). Without RW-3 this renders CH1==9.
- **R2 `test_scripted_owned_playing_still_renders`** — `_set(ssid=SSID,
  elapsed_ms=50, playing=True, scripted_id=7)` → CH1==9 (regression guard: scripted
  ownership + UUID still renders).
- **R3 `test_unscripted_pause_does_not_hold`** — play a scripted-owned tick
  (`scripted_id=7`, `now=t0`); then `playing=False, was_playing=True, scripted_id=0,
  now=t0+0.1` (same `load_gen`) → **ZERO**, and assert `sm._pack_play_hold_key is
  None` and `sm._pack_play_hold_deadline == 0.0` (Task 1c de-ownership reset; proves
  Investigation C — a paused, mode-invalidated deck cannot keep rendering).
- **R4 `test_scripted_id_set_but_ssid_empty_zeros`** — `_set(ssid="", playing=True,
  scripted_id=7)` → **ZERO** (reverse decoupling A.6: scripted but no UUID key;
  `metadata_ready` False). Confirms `scripted_owned` is ANDed, not OR'd.
- **R5 `test_unscripted_with_held_static_shows_static`** — `_set(ssid=SSID,
  playing=True, scripted_id=0)` with `_FakeInput(held_static_slot=8)` → CH1==200
  (automatic base ZEROs, manual Static Override still stands alone — Part C.5).

**Inner / event-path (Task 3 harness; drive `_push_tick_inner`, not `_set`):**
- **R6 `test_inner_autoloop_uuid_stays_zero`** — under
  `patch.dict(os.environ, {"RBSS_SCRIPTED_DIRECT": "0"})`: `TRACK_LOADED`, then
  `_on_filepath_resolved` with a **valid** `soundswitch_id=SSID` (no `SCRIPTED_ARM`
  is emitted in direct=0 mode, so `scripted_id` stays `0`), then `PLAY` + ticks with
  a fresh snap. Assert **both**: `self.sm._os.lighting_mode == "autoloop"` **and**
  the pack frame `== ZERO_FRAME`. (Pre-fix this renders CH1==9 — the test fails
  without RW-3.) If any step genuinely cannot be exercised purely, mark it **[U]**;
  this test **is** purely exercisable (events + injected clock + real
  `PositionCache`, no device), so the `[U]` escape is **not** permitted here.

**Regression — must stay green unchanged after the `_set` default (2a):** D1–D14 and
the RW-2 cases (`test_pause_holds_current_scripted_frame`, `…_derives_from_events…`,
`…_hold_expires…`, `…_loaded_unplayed_track_not_held`, `…_resume_continues`,
`…_held_static_shows_static`, `…_blackout_is_zero`, `…_stale_while_paused…`,
`…_unloaded_paused…`, `…_track_change_while_paused…`, `…_seek_discontinuity…`,
`…_master_switch…`) plus the three `PackDriverInnerTickTests` RW-2 timing tests and
the manual-static-policy tests (`:350-382`). The `scripted_id` default keeps all of
them rendering/zeroing exactly as before.

---

## Part E — Acceptance (definition of done)

- [ ] `_drive_pack_output` ANDs `scripted_owned = int(getattr(d,"scripted_id",0) or
      0) != 0` into `happy`; the else-branch latch reset fires on
      `load_key != hold_key or not scripted_owned`. Diff confined to the gate block in
      `state_manager.py` and to `tests/test_state_manager_pack_driver.py`. No
      `DeckState`/`OutputState` write; no new instance field; no
      `soundswitch_laser_player.py`/runtime/config/startup change.
- [ ] R1–R5 pass; R6 (inner direct=0) asserts both `lighting_mode=="autoloop"` and
      ZERO; existing D1–D14 + all RW-2 driver and inner-tick tests still green after
      the `_set` default.
- [ ] Invariants C.1–C.10 hold; the strict-narrowing safety proof (C.7/A.7) is
      reflected by R2 (scripted still renders) + R1/R6 (unscripted now ZEROs);
      RW-2 non-regression by the unchanged RW-2 suite + R3.
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
      (`python3.11 -m unittest tests.test_state_manager_pack_driver`) — RW-3 touches
      no dataclass/import/startup surface, so 3.11 is advisory but cheap.
- [ ] `enabled=false`, `dry_run=true`, `output_backend=none` unchanged; no restart,
      enable, backend change, MIDI/serial open, or hardware action.
- [ ] Doc update per anti-drift (AGENTS.md §7): flip RW-3 in
      `soundswitch_exporter_remaining_work.md` §5 to `[x] [C]` with the implementing
      commit, and re-verify the `soundswitch_output`/`soundswitch_pack_player`
      contract docs before bumping `last_verified_commit`. The
      `soundswitch_pack_player` contract already lists `state_manager.py`
      (`change_contracts.yml:249`), so **no contract extension is required**; this
      new plan doc does not need to be added to a contract (the RW-2 spec is not, and
      `check_docs_metadata.py` only requires headers on its fixed `REQUIRED_DOCS`
      list, not on every plan doc).

## When you finish
Commit per task with the messages above. Report back: the gate diff (the
`scripted_owned` binding, the `happy` line, the latch-reset line), the `_set` seam
change, the new test names with pass counts, the proof-gate verdict (expect
`PASS_IMPLEMENTATION_MAY_BEGIN`, 29/0/0), and the full-suite + hard-docs-check
results. Provide an updated ChatGPT review prompt in your final response.

---

## Appendix — 9-point pre-handoff checklist (run against this spec)

1. **Every claim labeled C/A/U.** ✅ Part A labels each fact [C]/[A]/[U]; the
   severity refinement in A.3 (durable vs incidental) is explicitly [C]/[A]; queue
   boundedness is [A]; no live/hardware claim is promoted.
2. **Verified against CURRENT code (`e295e37`).** ✅ Every file:line re-read this
   session; line numbers reconfirmed (gate at `3296-3338`, init `358-363`,
   `_update_lighting` `3096`, drain `1070-1076`, `_on_filepath_resolved` `2863`,
   `_arm_unscripted` `3087-3092`). HEAD drifted from the prompt's `1a90b01` to
   `e295e37` with no runtime change to these paths.
3. **Pending-state guard (all same-tick fields).** ✅ The gate composes with **all**
   pending fields active in the same tick, not just itself: RW-2 latch
   (`_pack_play_hold_key`/`deadline` — Task 1c + R3), held static + blackout
   (untouched masks block, R5), `track_changed`/`discont` (table A.8). The
   de-ownership latch reset (1c) closes the one cross-feature interaction RW-3
   introduces.
4. **Mode-transition cleanup on every path.** ✅ A.8 table covers idle/scripted/
   autoloop/stale/discont/replace/master-switch/mode-flip; the latch is reset on
   identity change **and** on scripted de-ownership (1c); no new state field is added
   so there is nothing else to clean up.
5. **Third-party API completeness.** ✅ No new player call; the existing
   `select_scripted(...)`/`clear_selection()` shapes (`:3331-3338`) are unchanged and
   reproduced verbatim. The gate is StateManager-side only.
6. **Cross-checked against existing authority vars.** ✅ Uses the canonical
   `d.scripted_id` (same var as `_update_lighting:3117`) and existing
   `d.meta.soundswitch_id`/`metadata_ready`; `os.lighting_mode` is explicitly
   evaluated and *deliberately* not ANDed in, with the staleness rationale (A.4). No
   ad-hoc locals introduced beyond the `scripted_owned` boolean derived from the
   canonical field.
7. **Pure-function test seam.** ✅ R1–R5 drive the real player + fake backend via the
   extended `_set` (no disk/subprocess); R6 uses the inner-tick harness with an
   injected clock and real `PositionCache` (no device/AppKit).
8. **Live safety explicit.** ✅ Part C maps S7.1/7.2/7.8/7.9/7.10–7.12; the
   strict-narrowing proof (A.7/C.7) shows RW-3 can only add ZEROs (never a new
   non-zero output); the RW-2 hold and the held Static Override are never clobbered
   (C.4/C.5); ZERO-on-uncertainty is the default for every unproven case (A.8).
9. **Adversarial self-review (forced failure).** ✅ The prompt's named attack —
   *"`scripted_id` set but `soundswitch_id` empty mid-pause"* — is handled in A.6/R4:
   `scripted_owned` is ANDed with `metadata_ready`, so a scripted deck with no UUID
   key ZEROs (no pack key to render), unchanged from today; the new term cannot
   render it. The reverse forced failure — *valid UUID, `scripted_id==0`, paused
   after playing* — is handled by `happy` going False **and** the 1c latch reset
   (R3). The subtle attack — *scripted_id flickers off→on for the same `load_gen`
   within `STOP_DEBOUNCE_S`* — is closed by 1c (de-ownership clears the latch, so
   re-acquisition needs a fresh PLAY, not a resurrected hold). The honesty attack —
   *"is this even a live bug?"* — is answered in A.3: under live direct-mode flags
   the common path already ZEROs via an **incidental** clear, so RW-3 is
   explicit-authority + legacy(`direct=0`)/queue-drop closure + defense-in-depth, not
   an "actively wrong right now" claim.

**Verdict: all 9 pass — Codex-ready.**
