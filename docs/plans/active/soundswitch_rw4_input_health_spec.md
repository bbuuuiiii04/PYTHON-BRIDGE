---
doc_status: active-plan
truth_level: code-grounded-design-spec
last_verified_commit: d37a472
last_verified_date: 2026-06-24
validation_scope: RW-4 controller-input health → manual-overlay fail-to-released for the bridge-native CH1-CH19 pack driver; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; default-off (enabled=false, dry_run=true, output_backend=none) — no restart/enable/backend/MIDI/serial/hardware authorized
---

# Codex Implementation Spec — RW-4 Controller-input health fail-to-released

> **Scope.** The pack driver consumes controller input (held Static Look + blackout)
> but ignores controller *health*. When the DDJ-800 (or its MIDI link) dies, errors,
> goes stale, drops a message, or its holds conflict, the driver still trusts whatever
> the snapshot's held fields say. RW-4 makes the driver honor held input **only from a
> fresh healthy snapshot**; an unhealthy controller drops its **manual overlay only**
> (Static Look + blackout forced released), while the **automatic scripted base is
> deliberately left running** (RW-3 gate untouched).
>
> **Operator policy decision [P], confirmed 2026-06-24.** *"If the DDJ-800 drops out
> mid-show, keep the automatic scripted show running; only drop the manual Static
> Override / blackout the dead controller was holding."* Chosen over the strict
> whole-output-ZERO option because the MIDI surface is an optional manual **overlay**,
> not the source of the scripted show (which derives independently from
> Rekordbox/StateManager). A flaky USB cable must not black the whole rig. This matches
> the accepted "Static Override = authoritative overlay" policy and RW-3's blessed
> held-static. **Accepted consequence:** if a blackout was *being held* on the DDJ when
> it dropped, the held blackout releases and the scripted base comes back on — the
> chosen-safe direction under this policy.
>
> **Roles.** Opus authored this; **Codex implements it**. No implementation, output
> enable, backend change, restart, or hardware action is authorized. Pack output stays
> default-off (`enabled=false`, `dry_run=true`, `output_backend=none`).
>
> **Builds on, does not reopen:** RW-1A (shutdown zero), RW-2 (pause-hold latch), and
> RW-3 (mode-only scripted gate + identity-aware pause hold) are done and software-tested
> at HEAD. RW-4 changes **only** the controller block (step 1) of `_drive_pack_output`
> and adds two push-local trackers; it does not touch the RW-2/RW-3 base gate, the player,
> the runtime, config, or startup.
>
> **Evidence labels:** **[C]** confirmed in current code at `d37a472` · **[P]** policy
> (operator-confirmed where noted) · **[A]** assumed/inferred · **[U]** needs
> live/hardware evidence (none promoted by software).

## Revision note — adversarial spec review round 1 incorporated (REJECT → repaired)
Round 1 REJECTED the first draft (2 BLOCKER, 1 HIGH, 1 MEDIUM). All folded in and
re-verified against current code, not taken on faith:

- **(BLOCKER) mailbox-drop degradation was one-tick.** The draft set `input_healthy =
  … and not new_drops`, where `new_drops` is true only on the tick the count increases.
  The next tick (`drops == last`) re-honored the held slot — so a **missed note-off**
  (the very thing a drop signals) could resurrect a stale Static Override until the
  adapter's `stale_timeout_ms` (~2 s). **Fixed:** the mail-drop degradation is now
  **latched** in a push-local flag (`_pack_input_degraded_latched`) that stays set across
  ticks and clears **only** on a clean, quiet, healthy snapshot (worker alive, no error,
  **no held static, no blackout**). The adapter exposes **no** fresh-re-press event, so
  none is invented — recovery is proven by observing a clean snapshot. Tested by H4
  (three ticks: render → drop → still-dropped) and H9 (clean tick clears the latch, a
  later press is re-honored).
- **(BLOCKER) missing health fields defaulted to healthy (fail-open).** The draft used
  `getattr(s, "worker_alive", True)` / `getattr(s, "error", None)`, so a snapshot double
  missing the health fields read as healthy. **Fixed:** health fields are read **directly**
  (`s.worker_alive`, `s.error`, `s.mail_drop_count`). `MidiInputSnapshot` is a frozen
  slots dataclass (`soundswitch_midi_input.py:36-48`) whose fields always exist; a
  malformed double raises and the **existing outer `except`** submits ZERO
  (`state_manager.py:3365-3372`) — missing health is **fail-closed**, never healthy.
- **(HIGH) the no-alias safety test was fake.** The draft's H3 used `_FakeInput()` with
  healthy defaults to stand in for "no controller." **Fixed:** H3 now drives a **real**
  `SoundSwitchMidiInputGroup(bindings=[], aliases={})`. The empty-alias safety comes from
  the **real** empty-group `snapshot()` (`worker_alive=True, error=None,
  mail_drop_count=0`, `:455`), not a stubbed default. The `midi_input is None` variant is
  kept.
- **(MEDIUM) the worker-death narrative was imprecise.** Exception worker death **clears**
  held state via `_clear_held` (`:354-362`), so it is *not* the gap. The real gap is the
  **`finally` path** (normal source closure, `:363-369`): it sets `worker_alive=False`
  **without** clearing held state, leaving a held slot reported on a not-alive worker.
  **Fixed:** A.3 and H1 now target exactly that "worker not alive while held state is
  still reported" case and no longer overclaim that *every* worker death preserves holds.

---

## Part A — Context & root cause (verified; read, do not implement)

### A.1 What the driver reads from the controller today [C]
The 200 Hz push loop calls `_drive_pack_output()` once per tick when the runtime is
active (`state_manager.py:3242-3243`; no early return skips it). Step 1 — the controller
block — is `state_manager.py:3280-3290`:

```python
            # 1. Controller masks + static overrides (in-memory snapshot; no I/O).
            if midi_input is not None:
                s = midi_input.snapshot()
                player.set_masks(blackout=bool(s.blackout_held), emergency=False)
                slot = s.held_static_slot
                if slot != self._pack_last_static_slot:
                    if slot is not None:
                        player.hold_static(int(slot))
                    elif self._pack_last_static_slot is not None:
                        player.release_static(int(self._pack_last_static_slot))
                    self._pack_last_static_slot = slot
```

- **[C]** It reads **only** `s.blackout_held` (`:3283`) and `s.held_static_slot`
  (`:3284`). It **never** reads `worker_alive`, `error`, or `mail_drop_count`.
- **[C]** The snapshot is `MidiInputSnapshot` (frozen slots dataclass,
  `soundswitch_midi_input.py:36-48`) with five fields: `held_static_slot`,
  `blackout_held`, `worker_alive`, `error`, `mail_drop_count`. Because it is
  `frozen=True, slots=True`, every field always exists on a real snapshot.
- **[C]** The whole body of `_drive_pack_output` is wrapped in `try/except Exception`
  that submits `_PACK_ZERO_FRAME` on any raise (`state_manager.py:3365-3372`). This is
  the fail-closed backstop RW-4 relies on for a malformed snapshot.

### A.2 What the controller actually controls [C]
The MIDI surface only mutates two render-affecting things — hold a **Static Look**
(`_process_note_on` kind `static_look`, `soundswitch_midi_input.py:218-225`) and hold
**blackout** (kind `blackout_mask`, `:226-229`). All other learned kinds are inventoried
but no-op (`:230-233`). It does **not** drive the scripted base — that is the RW-3 gate
(`state_manager.py:3334-3361`) reading `DeckState`. So "drop the manual overlay" = force
`held_static_slot → released` and `blackout → off`; "keep the scripted show" = leave the
RW-3 base gate untouched. These are independent layers in the player (A.5).

### A.3 The health signals already exist; only the consumer is missing [C]
The adapter/group already compute health into the snapshot:

- **[C] worker death (two distinct paths — only one preserves holds):**
  - *Exception death* — `_worker` catches any exception and calls
    `_clear_held("worker_death", …)` (`:354-362`), which **nulls held state** and sets
    `_worker_alive=False` (`:201-210`). Held state is gone, so this path is **not** the
    gap; pre-RW-4 already renders the base here.
  - *Normal source closure* — the message generator returns without raising and without
    `stop_event`; the `except` is skipped and the **`finally`** (`:363-369`) sets
    `_worker_alive=False` **without** calling `_clear_held`. A previously-held Static Look
    therefore stays reported with `worker_alive=False`. **This is the real fail-open gap
    RW-4 closes**, and the snapshot H1 models.
- **[C] stale hold:** `snapshot()` clears a static/blackout held past `stale_timeout_ms`
  and sets `error="stale_hold"` (`:106-115`). (Note: it nulls the static slot but a
  blackout can still be reported on the same stale tick — see A.6.)
- **[C] group aggregation** (`SoundSwitchMidiInputGroup.snapshot()`, `:443-460`):
  `worker_alive = all(per-adapter worker_alive) if snapshots else True` (`:455`);
  `held_static_slot = None` on a **conflict** between adapters (`:450,:453`);
  `error = "conflicting_static_holds"` on conflict, else `"input_error"` if any adapter
  errored, else `None` (`:457-458`); `mail_drop_count = sum(...)` (`:459`).

So the driver has everything it needs in-memory; RW-4 is purely a **consumer** change.
No new MIDI API call enters `_push_tick` — it reads the existing snapshot only.

### A.4 The "no controller configured" trap is safe by REAL construction [C]
An intentionally-empty controller-alias setup (`midi_input_aliases: {}`, the tracked
example value at `config/soundswitch_pack_player.example.json:29`) builds a
`SoundSwitchMidiInputGroup` with **zero entries** (`__main__._build_soundswitch_pack_startup`
constructs it from `cfg.midi_input_aliases`, `__main__.py:495-499`). An empty group's
`snapshot()` returns `worker_alive=True`, `error=None`, `mail_drop_count=0`,
`held_static_slot=None` (`soundswitch_midi_input.py:455` — the `if snapshots else True`
branch — and no held state). RW-4 reads those fields **directly** (not via a healthy
default), so the empty group is healthy **because the real code returns healthy values**,
and a no-controller show keeps playing scripted with **no special-casing of worker
count**. A configured worker that dies instead reports `worker_alive=False` (and
`error="input_error"`), so it is unhealthy. (`midi_input is None` — the
default-off/dry-run/none/midi paths, `__main__.py:478-485` — skips the block entirely;
also a no-controller show.) **H3 proves this against the real empty group, not a stub.**

### A.5 Player precedence — overlay vs base are independent layers [C]
`render()` (`soundswitch_laser_player.py:345-373`) composes: emergency/blackout mask
ZEROs everything first (`:346-347`); else the base (scripted / autoloop / missing) is
rendered; a held Static Look is layered **on top** of a `missing_selection` base or
stands alone (`:359-373`, via `resolve_frame` precedence
`emergency/blackout > static > base`, `:154-163`). Dropping the overlay (release static,
clear blackout mask) therefore leaves the RW-3-gated base exactly as it was — which is
the whole point of the operator policy.

### A.6 The health latch [C]/[P]
RW-4 derives one per-tick boolean from the snapshot:

```
input_healthy ≡ worker_alive AND error is None AND NOT mail_drop_degraded_latched
```

- `worker_alive` False ⇒ unhealthy (worker died/closed/restarting/not-ready). **Not
  latched** — this field persists while the worker is down and the instant it reports
  `True` again (with `error is None`) the overlay is re-honored. The existing
  `_pack_last_static_slot` diff makes release/re-acquire idempotent (H7).
- `error is not None` ⇒ unhealthy. One rule covers **every** error category:
  `stale_hold`, `conflicting_static_holds`, `input_error`, `worker_error:*`. Also **not
  latched** (self-clears when the adapter clears the error). **[P] Consequence
  (accepted):** an errored snapshot drops the **entire** overlay (static *and* blackout),
  not just the errored part — fail toward the running scripted base. `stale_hold`/
  `conflicting_static_holds` already null the static slot at the source; RW-4's addition
  is dropping a still-reported **blackout** under those errors too.
- **`mail_drop_degraded_latched`** ⇒ unhealthy until recovery. A new mailbox drop
  (`mail_drop_count > last seen`) may be a missed note-off, leaving a stale held slot the
  adapter will **not** clear until `stale_timeout_ms`. A one-tick flag is therefore
  **insufficient** (the BLOCKER): the next tick would re-honor the stale slot. So a new
  drop **sets a latch** that stays set across ticks. The latch clears **only** on a
  clean, quiet, healthy snapshot: `worker_alive AND error is None AND held_static_slot is
  None AND not blackout_held`. Requiring held state to be `None` first is what prevents a
  stale (missed-note-off) slot from re-honoring before either the operator releases it or
  the adapter's `stale_timeout_ms` nulls it. After the latch clears, a later **fresh**
  press is honored normally (H9).

> **[C] `mail_drop_count` is INERT in current code.** It is initialized to `0`
> (`soundswitch_midi_input.py:85`) and **never incremented**; the `_mailbox` deque
> (`:86`) is created but nothing appends to it (messages process synchronously in
> `_feed_raw_message`, `:262-301`). So a real drop never occurs today. RW-4 wires the
> latch as a **forward-compat hook** (clearly marked `ponytail:` in the code) so a future
> change that starts counting drops is handled safely, and so a falsifiable test exists
> (H4/H9 drive a synthetic counter). No live behavior depends on it today.

The strict `>` comparison means a pack-reload's fresh group (which reports
`mail_drop_count=0`) can never trip a false drop against a stale-high last value (H8); the
baseline tracker therefore needs **no** reset.

### A.7 Why the automatic base is untouched (safety statement) [C]
RW-4 changes **only** the inputs to `set_masks`/`hold_static`/`release_static` (the
overlay layer). It does **not** touch `happy`, `scripted_owned`, `play_identity`, the
transport derivation, `select_scripted`, or `clear_selection()` (`:3292-3361`). Therefore
RW-4 **cannot** change whether or what the automatic scripted/autoloop/idle base renders;
it can only release a manual overlay. Blackout-as-emergency safety is unchanged: a *real*
blackout/emergency still ZEROs first in the player (`:346-347`) when genuinely held by a
**healthy** controller. The only behavior change is: an **unhealthy** controller's
reported holds are no longer trusted.

### A.8 Transition table [C]/[A]
"Overlay" = held static + blackout mask. "Base" = RW-3-gated automatic base (untouched).
`latched` = `_pack_input_degraded_latched`.

| Controller state | snapshot | `input_healthy` | Overlay | Base |
|---|---|---|---|---|
| Healthy, holding static slot 8 | `alive=T, err=None, slot=8` | True | static 8 layered | per RW-3 |
| Healthy, holding blackout | `alive=T, err=None, blackout=T` | True | blackout ZEROs frame | (masked) |
| **No aliases configured** (real empty group) | `alive=T, err=None, slot=None` | **True** | none | **scripted renders** |
| `midi_input is None` (dry-run/none/midi) | block skipped | n/a | none | scripted renders |
| Worker not alive, static still reported (source-closed) | `alive=F, err=None, slot=8` | False | **dropped** | scripted renders |
| Stale hold (static) | `err="stale_hold", slot=None` | False | dropped (already none) | scripted renders |
| Stale + blackout still reported | `err="stale_hold", blackout=T` | False | **blackout dropped** | scripted renders |
| Conflicting static holds | `err="conflicting_static_holds", slot=None` | False | **dropped** | scripted renders |
| New mailbox drop (future) | `mail_drop_count↑` → `latched=T` | False | dropped | scripted renders |
| Latched, slot still reported (next tick) | `alive=T, err=None, slot=8, latched=T` | **False** | **still dropped** | scripted renders |
| Latch recovery: clean quiet healthy tick | `alive=T, err=None, slot=None, blackout=F` | True (`latched→F`) | none yet | per RW-3 |
| Worker-death recovery: fresh healthy | `alive=T, err=None, slot=8, latched=F` | True | static 8 re-acquired | per RW-3 |
| Pack reload (fresh group) | `alive=T, err=None, drop=0` | True | per fresh holds | per RW-3 |

### A.9 Constants & symbols (re-verified at `d37a472`) [C]
Controller block `state_manager.py:3280-3290`; `set_masks` call `:3283`; static diff
`:3285-3290`. Driver-local push trackers init `:358-363`; `_pack_last_static_slot`
(`:360`) is `int | None`. RW-4 adds **two** push-local fields
(`_pack_last_mail_drop_count: int`, `_pack_input_degraded_latched: bool`) and **no** new
helper, no instance state in the swappable bundle. Player: `set_masks`
(`soundswitch_laser_player.py:264-268`), `hold_static`/`release_static` (`:234-245`),
`render` precedence (`:345-373`).

---

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- **Touch only** `state_manager.py` — the controller block (`:3280-3290`) and the
  push-tracker init (`:358-363`) — and `tests/test_state_manager_pack_driver.py`. Do
  **not** modify the RW-2/RW-3 base gate (`:3292-3361`), `select_scripted`,
  `clear_selection`, `_arm_unscripted`, `_update_lighting`, the player
  (`soundswitch_laser_player.py`), the input adapter (`soundswitch_midi_input.py`), the
  controller (`soundswitch_pack_controller.py`), the runtime (`soundswitch_pack_runtime.py`),
  `__main__.py`, config, or any startup/dataclass/import surface.
- **Out of scope — name the boundaries:** RW-5 (status/menubar — no status string/field/
  path/id/port; `sanitized_status()` untouched); RW-8 (native-DMX autoloop — base stays
  RW-3/zero); the input adapter itself (the snapshot contract is consumed as-is, not
  changed; do **not** start counting mailbox drops in this task).
- The driver stays **read-only** w.r.t. `DeckState`/`OutputState`; the only new writes are
  the driver-local `_pack_last_mail_drop_count` and `_pack_input_degraded_latched`.
  StateManager stays the sole `DeckState` writer. No filesystem/subprocess/MIDI/serial/
  socket/sleep/retry/lock added; the snapshot read is the existing in-memory call. Driver
  inert unless `rt.active` (`:3271`).
- **Fail-closed:** read `s.worker_alive` / `s.error` / `s.mail_drop_count` **directly** —
  no `getattr` healthy defaults. A malformed snapshot raises into the existing outer
  `except` (`:3365-3372`) → ZERO.
- ZERO/overlay semantics use the existing `set_masks`/`hold_static`/`release_static` calls
  only; no `transport=` change; no `emergency=` change (stays `False`).

### Task 1 — `state_manager.py`: add the two push-local trackers
In `__init__`, immediately after `self._pack_last_static_slot` (`:360`), add:
```python
        self._pack_last_mail_drop_count: int = 0      # RW-4: monotonic mailbox-drop baseline
        self._pack_input_degraded_latched: bool = False  # RW-4: latched on a new mail drop
```
No other init change.

Commit: `feat(soundswitch): RW-4 add controller mail-drop baseline + degrade latch`.

### Task 2 — `state_manager.py`: health-gate the manual overlay
Replace the controller block (`:3280-3290`) with:
```python
            # 1. Controller masks + static overrides (in-memory snapshot; no I/O).
            #    RW-4: an UNHEALTHY controller drops its MANUAL OVERLAY ONLY (held
            #    Static Look + blackout forced released); the automatic scripted base
            #    (RW-3 gate below) is deliberately left running, so a DDJ-800 dropout
            #    keeps the scripted show on (operator policy 2026-06-24). Held input is
            #    honored only from a FRESH HEALTHY snapshot.
            #
            #    FAIL-CLOSED: health fields are read DIRECTLY off the snapshot. A
            #    malformed double missing them raises and the outer except submits ZERO
            #    (state_manager.py:3365-3372) — missing health never reads as healthy. An
            #    empty-alias group is healthy by REAL construction (worker_alive=True,
            #    error=None; soundswitch_midi_input.py:455), not by a default, so a
            #    no-controller show still plays scripted.
            #
            #    LATCHED mailbox-drop: a new mail drop may be a missed note-off that
            #    leaves a stale held slot the adapter won't clear until stale_timeout. A
            #    one-tick flag would re-honor the stale slot next tick, so the degradation
            #    is LATCHED across ticks and clears only on a clean, quiet, healthy
            #    snapshot (no held static, no blackout).
            if midi_input is not None:
                s = midi_input.snapshot()
                worker_alive = bool(s.worker_alive)
                err = s.error
                drops = int(s.mail_drop_count)
                held_slot = s.held_static_slot
                blackout_held = bool(s.blackout_held)
                # ponytail: mail_drop_count is inert in the current adapter (never
                # incremented; the _mailbox deque is unused). The latch is a forward-compat
                # hook with a falsifiable test (H4/H9); drop it only if the mailbox is
                # provably never wired.
                if drops > self._pack_last_mail_drop_count:
                    self._pack_input_degraded_latched = True
                self._pack_last_mail_drop_count = drops
                # Recovery: a clean, quiet, healthy snapshot clears the latch so a later
                # FRESH press may be honored. Requiring held state None first stops a stale
                # (missed-note-off) slot re-honoring before stale_timeout / operator release.
                if (
                    self._pack_input_degraded_latched
                    and worker_alive and err is None
                    and held_slot is None and not blackout_held
                ):
                    self._pack_input_degraded_latched = False
                input_healthy = (
                    worker_alive and err is None
                    and not self._pack_input_degraded_latched
                )
                blackout = blackout_held if input_healthy else False
                slot = held_slot if input_healthy else None
                player.set_masks(blackout=blackout, emergency=False)
                if slot != self._pack_last_static_slot:
                    if slot is not None:
                        player.hold_static(int(slot))
                    elif self._pack_last_static_slot is not None:
                        player.release_static(int(self._pack_last_static_slot))
                    self._pack_last_static_slot = slot
```
Everything below (`:3292` onward — the RW-3 base gate) stays **unchanged**.

Commit: `fix(soundswitch): RW-4 drop manual overlay when controller unhealthy`.

### Task 3 — `tests/test_state_manager_pack_driver.py`: extend `_FakeInput`, add H-cases
**3a. Extend `_FakeInput`** (`:83-92`) with the three health fields, healthy defaults so
every existing test stays green:
```python
class _FakeInput:
    # The driver reads .blackout_held/.held_static_slot plus RW-4 health fields
    # (.worker_alive/.error/.mail_drop_count) from the snapshot.
    def __init__(self, *, held_static_slot=None, blackout_held=False,
                 worker_alive=True, error=None, mail_drop_count=0):
        self._snap = SimpleNamespace(
            held_static_slot=held_static_slot, blackout_held=blackout_held,
            worker_alive=worker_alive, error=error, mail_drop_count=mail_drop_count)
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        return self._snap
```

**3b. Add RW-4 cases (H1–H9)** in a new `PackDriverInputHealthTests` class. `_pack()`
scripted SSID renders CH1==9 at 50 ms; static slot 8 → CH1==200; ZERO_FRAME = all-zero.
Each H-case asserts the submitted frame (read the backend's last submitted frame, as the
existing driver tests do).

- **H1 `test_worker_not_alive_drops_held_static`** — scripted playing (`_set(ssid=SSID,
  elapsed_ms=50, playing=True)`) + `_FakeInput(held_static_slot=8, worker_alive=False,
  error=None)` → frame == scripted CH1==9 (overlay dropped, base runs). Models the **real
  source-closed `finally` path** (`soundswitch_midi_input.py:363-369`): worker not alive
  while a held static is still reported. **Pre-RW-4: CH1==200** (driver honors the
  still-reported slot). Comment: exception death instead clears held state (`_clear_held`,
  `:354-362`), so it is **not** the gap — this models normal source closure.
- **H2 `test_worker_not_alive_drops_held_blackout`** — scripted playing +
  `_FakeInput(blackout_held=True, worker_alive=False, error=None)` → CH1==9 (blackout
  dropped, scripted base comes back — the accepted policy consequence). **Pre-RW-4: ZERO**
  (blackout mask honored).
- **H3 `test_no_aliases_scripted_renders`** (safety-trap regression guard, REAL group) —
  scripted playing + `midi_input = SoundSwitchMidiInputGroup(bindings=[], aliases={})`
  (its real `snapshot()` reports `worker_alive=True, error=None, slot=None,
  mail_drop_count=0`) → CH1==9, and `player` static is **not** held. Proves the real
  empty-alias boundary with no worker-count special case. **Add a `midi_input=None`
  variant → CH1==9.** Import `SoundSwitchMidiInputGroup` from
  `rb_ss_bridge_v2.soundswitch_midi_input`.
- **H4 `test_new_mailbox_drop_latches_overlay_drop`** — three ticks on one sm, holding
  slot 8 throughout:
  - tick 1 `_FakeInput(held_static_slot=8, mail_drop_count=0)` → CH1==200 (static renders);
  - set `inp._snap.mail_drop_count = 1` → tick 2 → CH1==9 (new drop ⇒ overlay drops,
    scripted base renders);
  - tick 3 with `mail_drop_count = 1` unchanged, slot still 8 → CH1==9 (**still dropped** —
    the latch holds; the one-tick draft would wrongly re-render CH1==200 here).
  **Pre-RW-4: CH1==200 all three ticks.** Comment: `mail_drop_count` is inert in
  production; synthetic counter exercises the forward-compat latch.
- **H5 `test_stale_hold_drops_blackout`** — scripted playing +
  `_FakeInput(blackout_held=True, error="stale_hold", worker_alive=True)` → CH1==9.
  **Pre-RW-4: ZERO.**
- **H6 `test_conflicting_holds_drops_overlay`** — scripted playing +
  `_FakeInput(blackout_held=True, error="conflicting_static_holds", held_static_slot=None,
  worker_alive=True)` → CH1==9. **Pre-RW-4: ZERO.**
- **H7 `test_worker_recovery_re_honors_overlay`** — two ticks: tick 1
  `_FakeInput(held_static_slot=8, worker_alive=False, error=None)` → CH1==9 (overlay
  dropped, `_pack_last_static_slot is None`); then heal (`inp._snap.worker_alive=True`) →
  tick 2 → CH1==200 (re-acquired from a fresh healthy snapshot). Proves worker-death needs
  **no** latch (it self-clears).
- **H8 `test_reload_fresh_group_no_false_drop`** — set `sm._pack_last_mail_drop_count = 5`
  (drops before a reload), then drive a fresh group
  `_FakeInput(held_static_slot=8, mail_drop_count=0)` (reset-to-zero count) → CH1==200
  (strict `>` treats `0 > 5` as no new drop; latch never set; overlay honored).
- **H9 `test_mailbox_drop_latch_recovers_after_clean_tick`** (BLOCKER recovery) —
  continue from a latched state: drive `_FakeInput(held_static_slot=8, mail_drop_count=0)`
  (CH1==200), set `mail_drop_count=1` (CH1==9, latched), then:
  - release the hold: `inp._snap.held_static_slot=None`, `mail_drop_count=1` → tick →
    CH1==9 (clean quiet healthy tick **clears the latch**; nothing held);
  - re-press: `inp._snap.held_static_slot=8`, `mail_drop_count=1` → tick → CH1==200 (a
    fresh press after recovery is re-honored). Asserts `sm._pack_input_degraded_latched is
    False` after the clean tick.

**3c. No RW-3/RW-2 assertion changes are required** — the `_FakeInput` defaults are
healthy, so D1–D14, the RW-2 driver/inner-tick tests, the RW-3 R-cases, and the
manual-static-policy tests (`:350-382`) render/zero exactly as before.

Commit: `test(soundswitch): RW-4 controller-health overlay-drop, latch + recovery cases`.

---

## Part C — Invariants that MUST still hold (live safety; maps to roadmap §7)

1. **S7.1 sole `DeckState` writer.** RW-4 only *reads* the snapshot; the two new writes are
   driver-local push state (`_pack_last_mail_drop_count`, `_pack_input_degraded_latched`).
   No `DeckState` write.
2. **S7.2 push-loop purity.** Added work is in-memory only (direct field reads, one int
   compare, a couple of boolean tests); the snapshot call already existed. No
   I/O/sleep/lock/MIDI added.
3. **S7.8 release on uncertain/degraded (fail-closed overlay).** Every unhealthy snapshot
   resolves the **overlay** toward released; a malformed snapshot raises → outer except →
   ZERO. The automatic base keeps its RW-3 fail-to-ZERO semantics, untouched.
4. **Automatic base not regressed (A.7).** RW-4 does not touch `happy`/`scripted_owned`/
   `play_identity`/transport/`select_scripted`/`clear_selection`. It cannot change whether
   or what the base renders. RW-2/RW-3 suites stay green.
5. **S7.9 manual Static Override + blackout precedence.** A *healthy* held static/blackout
   behaves exactly as today (player precedence `:345-373` unchanged). The blessed RW-3
   held-static-as-overlay policy is preserved for the healthy case; RW-4 only withholds
   trust from an **unhealthy** controller. A real emergency/blackout from a healthy
   controller still ZEROs first.
6. **No `transport=` / `emergency=` change.** Overlay drop uses the existing
   `set_masks(emergency=False)` + `release_static`; no new transport or emergency path.
7. **No-controller neutrality (A.4).** Real empty-alias group and `midi_input is None`
   both keep scripted playback; the health latch treats them as healthy with no
   worker-count logic (H3).
8. **Latched degradation recovers deterministically (A.6).** A mail-drop latch clears only
   on a clean, quiet, healthy snapshot (no held static/blackout), so a stale missed-note-off
   slot cannot re-honor mid-degradation (H4) but a genuine fresh press after recovery is
   honored (H9). worker_alive/error are not latched and self-clear (H7).
9. **S7.10/S7.11 default-off neutrality.** Inert unless `rt.active`; byte/order-neutral for
   OS2L/lasers/LEDs/Rekordbox/commands/logs when pack is absent/disabled/dry-run/none.
10. **S7.12 no leaks.** No new status string/path/id/port/byte; `sanitized_status()`
    untouched.
11. **Reload safety (A.6).** Strict-`>` mail-drop comparison means a fresh group's
    `mail_drop_count=0` cannot false-trip against a stale-high baseline; no tracker reset
    needed (H8).

---

## Part D — Tests (pure seams; no device, no AppKit, no hardware)

All RW-4 tests are pure driver-level (`_make_sm` + `_set` + extended `_FakeInput`, plus a
real **empty** `SoundSwitchMidiInputGroup` for H3); no real MIDI port, no worker thread.
H1/H2/H5/H6 prove the **pre-RW-4 defect** (each renders the wrong frame on current code:
H1 CH1==200, H2/H5/H6 ZERO). H4 proves the **latch** (third tick stays dropped — the
one-tick draft regressed here). H9 proves **recovery** (clean tick clears the latch, fresh
press re-honored). H3/H7/H8 are regression/recovery guards (no-controller safe; worker
self-clears; reload no false drop). Map: H1↔source-closed worker-not-alive, H2↔worker-dead
blackout, H3↔no-aliases (real group), H4↔mailbox-drop latch, H5↔stale-hold, H6↔conflict,
H7↔worker recovery, H8↔pack-reload, H9↔latch recovery — the full RW-4 required-work test
list with the strengthened latch coverage.

---

## Part E — Acceptance (definition of done)

- [ ] `_drive_pack_output` controller block derives `input_healthy = worker_alive and
      error is None and not _pack_input_degraded_latched`, reading the health fields
      **directly** (fail-closed); a new mail drop **latches** the degradation, cleared only
      on a clean, quiet, healthy snapshot; an unhealthy snapshot forces `blackout=False`
      and `slot=None` (overlay released) and re-honors holds only from a fresh healthy
      snapshot. Two new push-local fields (`_pack_last_mail_drop_count`,
      `_pack_input_degraded_latched`). Diff confined to the controller block + the two init
      lines in `state_manager.py`, and the test file. No base-gate / player / runtime /
      controller / config / startup / adapter change.
- [ ] H1–H9 pass; H1/H2/H5/H6 fail on pre-RW-4 code, and H4 tick 3 fails the one-tick
      draft (recorded). Existing D1–D14, the RW-2 driver + inner-tick tests, the RW-3
      R-cases, and the manual-static-policy tests (`:350-382`) stay green after the
      `_FakeInput` default extension (no assertion edits).
- [ ] Invariants C.1–C.11 hold; the automatic-base-not-regressed proof (C.4/A.7); the
      no-controller neutrality (C.7/A.4, H3); the latch determinism (C.8/A.6, H4/H9); the
      fail-closed read (A.4/B); the reload no-false-drop guard (C.11, H8).
- [ ] **Gates run and outputs recorded (all HARDWARE-UNVALIDATED):**
      ```bash
      cd /Users/bbui
      python3.14 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation \
        --project ~/Music/SoundSwitch/default.ssproj \
        --output-dir /tmp/rbss-soundswitch-rw4-proof    # expect 29/0/0 (RW-4 does not touch pack gen)

      cd /Users/bbui/rb_ss_bridge_v2
      python3 -m unittest discover tests                 # full suite green
      python3 tools/check_docs_metadata.py
      python3 tools/check_agent_contracts.py
      python3 tools/check_docs_drift.py
      python3 tools/check_docs_staleness.py --report     # advisory
      git diff --check
      ```
- [ ] Focused module also run under Python 3.11
      (`python3.11 -m unittest tests.test_state_manager_pack_driver`) — RW-4 touches no
      dataclass/import/startup surface, so 3.11 is advisory.
- [ ] `enabled=false`, `dry_run=true`, `output_backend=none` unchanged; no restart, enable,
      backend change, MIDI/serial open, or hardware action.
- [ ] Doc update per anti-drift (AGENTS.md §7): flip RW-4 in
      `soundswitch_exporter_remaining_work.md` §5 to `[x] [C]` with the implementing
      commit; re-verify the `soundswitch_output`/`soundswitch_pack_player` contract docs
      before bumping `last_verified_commit`. `state_manager.py` is already in the
      `soundswitch_pack_player` contract globs — no contract extension required.

## When you finish
Commit per task. Report back: the controller-block diff, the two new init fields, the
`_FakeInput` extension, the new test names with pass counts, the pre-RW-4 failure evidence
for H1/H2/H5/H6 and the one-tick-draft failure for H4 tick 3, the proof-gate verdict
(expect `PASS_IMPLEMENTATION_MAY_BEGIN`, 29/0/0), full-suite + hard-docs-check results.
Provide an updated reviewer prompt in your final response. Preserve **SOFTWARE-VALIDATED
ONLY / HARDWARE-UNVALIDATED**.

---

## Appendix — 9-point pre-handoff checklist (run against this revision)

1. **Claims labeled C/A/U/P.** ✅ Health signals and inert mail-drop are [C]; the
   keep-scripted policy is [P] operator-confirmed 2026-06-24; the error⇒drop-whole-overlay
   consequence is [P]/[A].
2. **Verified against CURRENT code (`d37a472`).** ✅ Controller block (`:3280-3290`),
   `_drive_pack_output` always-runs (`:3242-3243`) + outer ZERO except (`:3365-3372`),
   snapshot fields (`:36-48`), exception death vs source-closed `finally`
   (`:354-362` vs `:363-369`), stale (`:106-115`), group aggregation (`:443-460`,
   empty→worker_alive True `:455`), mail_drop never incremented (`:85-86`), empty-alias
   example config (`:29`), startup wiring (`__main__.py:478-499`), player precedence
   (`:154-163,:264-268,:345-373`).
3. **Pending-state guard (all same-tick fields).** ✅ The overlay (health-gated) and the
   RW-3 base gate are independent player layers (A.5); RW-4 leaves the base inputs
   untouched, so no same-tick interaction is changed beyond withholding overlay trust.
4. **Mode-transition cleanup on every path.** ✅ `_pack_last_static_slot` already releases
   on every slot change incl. forced-None; `_pack_input_degraded_latched` is the explicit
   multi-tick state, set on a new drop and cleared **only** on a clean quiet healthy tick
   (H4/H9); `_pack_last_mail_drop_count` is monotonic with strict-`>` so reload/restart
   cannot false-trip (H8). worker_alive/error self-clear with no latch (H7).
5. **Third-party API completeness.** ✅ Reuses `snapshot()`/`set_masks(blackout=,
   emergency=)`/`hold_static(int)`/`release_static(int)` exactly as today; no new call.
   Reads `s.worker_alive`/`s.error`/`s.mail_drop_count`/`s.held_static_slot`/
   `s.blackout_held` directly (the frozen-slots snapshot guarantees them).
6. **Cross-checked against existing authority vars.** ✅ Consumes the canonical
   `MidiInputSnapshot` group fields; no re-derivation of health; base gate authority
   (`scripted_owned` etc.) deliberately untouched.
7. **Pure-function test seam.** ✅ H1–H9 via `_make_sm`/`_set`/`_FakeInput` + one real
   empty `SoundSwitchMidiInputGroup` (H3) — no device, thread, port, or file.
8. **Live safety explicit.** ✅ Part C maps S7.1/7.2/7.8–7.12; overlay fails to released
   and is fail-closed on malformed; base keeps RW-3 fail-to-ZERO; healthy emergency/blackout
   still ZEROs first.
9. **Adversarial self-review (forced failures).** ✅ (a) *worker not alive holding static*
   (source-closed) → gate forces slot None, base runs (H1; pre-RW-4 wrongly CH1==200).
   (b) *worker not alive holding blackout* → blackout dropped, scripted returns — accepted
   policy consequence (H2). (c) *no aliases (real empty group)* → healthy by real
   construction, scripted plays (H3). (d) *stale/conflict still reports blackout* →
   error⇒whole-overlay-drop (H5/H6). (e) *new mail drop* → latched, stays dropped next tick
   (H4) and recovers on a clean tick (H9) — the BLOCKER fix. (f) *missing health field* →
   direct read raises → outer except ZERO, never healthy-by-default (fail-closed). (g)
   *reload resets drop count* → strict-`>` no false drop (H8). (h) *worker recovery* →
   self-clears with no latch (H7). (i) *honesty* → mail-drop labeled inert; exception death
   does **not** preserve holds; only the source-closed path is the gap.
