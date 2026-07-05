---
doc_status: active-spec
truth_level: implementation-spec, code-grounded
last_verified_commit: f114c39
last_verified_date: 2026-07-05
validation_scope: spec only until tasks land; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED
---

# Codex Implementation Spec - Edge-triggered health for repeat-warning spam (AWR-125 UX item 11)

Operator-approved 2026-07-05 ("approve all", UX review item 11). Authored by Claude from a live
review of the 2026-07-05 02:02 run: one message was 82.5% of all WARNING+ records (387 of 469),
and a real recovery (Rekordbox re-attach) never cleared its red latch in the viewer.

## Part A - Context & Root Cause (verified; read, do not implement)

The logging contract (`docs/architecture/logging_authority.md`) requires health records to be
**edge-triggered transitions only** (fail → one record, recover → one record). Five sites violate
that today; all claims below re-verified at `f114c39`:

1. **[confirmed]** `soundswitch_midi_input.py:540` — `log.warning("[SS-MIDI] input port gone;
   retrying exact port")` inside the reopen-retry loop. The guard `if ready or not ever_ready:`
   (line 537) means a port that has NEVER appeared warns on **every** retry cycle (~5s), forever
   — 387 repeats in the 33-minute 2026-07-05 run. This is a legacy stdlib warning (not `health()`),
   so it floods the OPERATOR lens via `level >= WARNING`.
2. **[confirmed]** `osl_output.py:151` — `bridge_log.health("os2l", "soundswitch send failed
   (%s); reconnecting", exc)` has **no guard at all**. Bounded today only by `disconnect()` +
   the 3s reconnect cadence; a flapping connection emits one WARNING per flap indefinitely.
3. **[confirmed]** `osl_output.py:130` — `health("queue", "soundswitch send queue full; dropping
   updates")` re-emits every 5s (`bf.log_throttled("os2l_queue_full", 5.0)`) while full: a
   throttled repeat, not an edge.
4. **[confirmed]** `state_manager.py:861` — `health("tick", "push loop error; skipping tick
   error=%s count=%d", ..., lvl=ERROR)` re-emits every 1s (`next_loop_error_log = now + 1.0`)
   while the push loop keeps erroring.
5. **[confirmed]** `rb_state_reader.py:664` — `health("queue", "rb_state queue full; dropping
   %s", ev.kind)` re-emits every 5s (`bf.log_throttled("rb_state_queue_full", 5.0)`).

Plus one **missing recovery edge**:

6. **[confirmed live 2026-07-05 02:28]** `rb_memory.py:1087` emits `health("rb", "rekordbox
   pid=%d gone; detaching", ...)` (WARNING) when Rekordbox exits — but the re-attach success
   path (`rb_memory.py:_try_attach`, ~line 1259; legacy INFO `[RBMEM][ATTACH]` at line 1282)
   emits **no `health("rb", ...)` recovery**, so the viewer's red "rekordbox gone" latch stayed
   up while Rekordbox was re-attached and BPM was flowing. Red must only ever mean broken.
   **[unknown]** whether `rb_state_reader`'s direct-event attach also re-establishes after an RB
   restart — do NOT claim it does; the recovery message must be truthful about what recovered
   (memory reader re-attach), e.g. "rekordbox re-attached (memory reader)".

The viewer clears a latch when a `health.*` record with the SAME cat arrives below WARNING
(`bridge_view.py`, `LatchState.note`), so each fail edge needs a matching same-cat recovery edge.

`bridge_fmt.log_changed(key, value)` (`bridge_fmt.py:120`) is the repo's existing edge-guard
primitive — a value-change detector already used for exactly this pattern at
`enttec_dmx_pro.py:224/229` ("dmx_write_err") and `osl_output.py:183` ("os2l_conn_fail",
re-armed on connect at line 176). Reuse it; do not invent a parallel mechanism.

## Part B - Tasks (implement exactly, in order)

### Absolute Rules
- Out of scope: `bridge_view.py`, `scripts/ss_bridge_watcher.sh`, laser/LED/Govee decision logic,
  OS2L/MIDI/DMX send behavior, anything that changes WHAT the rig outputs. This spec changes only
  WHEN log records are emitted (edge vs repeat) and adds recovery emits.
- Behavior that must not change: every failure still emits at least once per fail→recover cycle;
  message levels stay as they are today; drop-counting/retry/reconnect logic untouched.
- Expected error handling: emit-path failures must never break the surrounding I/O loop —
  but do NOT add new try/except around the health calls; `bridge_log` already isolates.
- The bridge may be live while you work; never launch or signal any bridge process.

### Task 1 - `soundswitch_midi_input.py`: edge-trigger the port-gone warning
At line ~537-540, gate the warning with `bf.log_changed("ss_midi_port_gone", True)` (import
`bridge_fmt as bf` following the module's existing import style; check for an existing import
first). On successful (re)open of the port (the code path that sets `ready = True` /
`ever_ready = True`), emit the recovery edge once via `bf.log_changed("ss_midi_port_gone", False)`
guarding a `log.info("[SS-MIDI] input port connected")` (stdlib INFO is enough — this module is
legacy; do not convert it to `health()` in this task). Keep the existing retry-interval logic
(lines 541-552, incl. the 2026-06-30 slow-retry comment) byte-identical.

### Task 2 - `osl_output.py:151`: guard the send-failed emit
Wrap with `bf.log_changed("os2l_send_fail", type(exc).__name__)` so a repeating identical
failure emits once. Re-arm on successful connect: next to the existing
`bf.log_changed("os2l_conn_fail", None)` re-arm at line ~176, add
`bf.log_changed("os2l_send_fail", None)`.

### Task 3 - `osl_output.py:130`: queue-full fail/recover edge
Replace the 5s throttle with `bf.log_changed("os2l_queue_full", True)`. Add the recovery edge
where a `put_nowait` succeeds after fullness: `bf.log_changed("os2l_queue_full", False)` guarding
`health("queue", "soundswitch send queue recovered", lvl=logging.INFO)`. Include the number of
drops during the episode in the recovery message if `self._drop_count` deltas are cheaply
available in scope; otherwise omit — do NOT add new counters.

### Task 4 - `state_manager.py:861`: push-loop error streak edge
Replace the 1s time-throttle with an edge on error-streak start:
`bf.log_changed("push_loop_error", True)` guarding the existing ERROR emit (keep the running
`loop_error_count` in the message). At the top of a clean tick that follows any error (the
existing success path), emit recovery once via `bf.log_changed("push_loop_error", False)`
guarding `health("tick", "push loop recovered after %d errors", loop_error_count,
lvl=logging.INFO)`. HOT PATH: `log_changed` is a dict lookup — same cost class as today's
monotonic compare; add NOTHING heavier (no I/O, no allocation-heavy formatting on the healthy
path — the healthy-path cost must be one boolean check).

### Task 5 - `rb_state_reader.py:664`: queue-full fail/recover edge
Same pattern as Task 3 with key `"rb_state_queue_full"`: fail edge on first `queue.Full`,
recovery edge (`health("queue", "rb_state queue recovered", lvl=logging.INFO)`) on the first
successful `put_nowait` after fullness.

### Task 6 - `rb_memory.py`: re-attach recovery edge for `health.rb`
In `_try_attach`'s success path (where the `[RBMEM][ATTACH]` INFO at line ~1282 is emitted),
emit `bridge_log.health("rb", "rekordbox re-attached (memory reader) pid=%d", pid,
lvl=logging.INFO)` — but ONLY when this attach follows a detach in the same process lifetime
(guard with `bf.log_changed("rb_mem_attached", True)`, and set
`bf.log_changed("rb_mem_attached", False)` at the pid-gone detach at line ~1087, so first-boot
attach does not emit a spurious "re-attached"). Same cat `rb` as the "gone" warning so the
viewer latch clears.

### Task 7 - open decision, DO NOT IMPLEMENT: expected absence
SoundSwitch deliberately not running still (correctly, per contract) shows a red latch
("soundswitch not reachable", "input port gone"). Whether an "expected absence" concept should
exist (e.g. demote to a neutral state when the operator declares SS off) is a policy question
for Brandon. Record it in the closing report as an open question; implement nothing for it.

## Part C - Invariants That MUST Still Hold (live safety)

- The 200 Hz push loop gains no blocking I/O, no new allocations on the healthy path
  (AGENTS.md §6); Task 4's healthy-path cost is one dict-lookup boolean check.
- Reader threads publish events/snapshots only; no new `DeckState` writes.
- Every genuine failure is still visible: first occurrence always emits; recovery always emits.
  Fail-closed on uncertainty — if an edge state is ambiguous, prefer emitting once more over
  staying silent.
- No change to what/when the rig outputs light. Suite must prove byte-identical light behavior
  (existing tests already cover the touched send paths).

## Part D - Tests

Extend the existing per-module test files (pure seams; no subprocess, no real MIDI/sockets):
- `tests/test_sound_switch_engine.py`: send-fail flap emits once per episode; re-arms after
  reconnect (mirror the existing `OS2LConnectionHealthTransitionTests` style at line ~399).
- SS-MIDI: port-never-seen retry loop warns exactly once (extend the module's existing tests;
  use the `_stop_event`/fake-source seam already present).
- `tests/test_state_manager*`: two consecutive push-loop errors → one ERROR; clean tick after
  errors → one INFO recovery; healthy path emits nothing.
- `tests/test_rb_state_reader.py`: queue full twice → one WARNING; successful put after
  fullness → one INFO recovery (extend the existing queue-full test at line ~1274 — it asserts
  `"queue full" in getMessage()`, keep that phrase).
- `rb_memory`: detach → attach emits the `health.rb` recovery; first-boot attach does NOT.

## Part E - Acceptance (definition of done)

- [ ] All six tasks landed; Task 7 reported, not implemented.
- [ ] Contract: `logging_visibility` in `docs/agents/change_contracts.yml` — update every
      `docs_update` doc it lists as applicable; `soundswitch_output` contract also matches
      `osl_output.py` (its `docs_update` too). Note the edge-trigger completions in
      `docs/subsystems/logging.md` (the "health = edge-triggered" claim becomes true for these
      sites) and in the AWR-125 registry row's follow-ups.
- [ ] `python3 -m unittest discover tests` green from the repo root (baseline 3220 OK / 5
      skipped / 1 expected failure as of `f114c39`).
- [ ] `python3 tools/check_docs_metadata.py`, `tools/check_agent_contracts.py`,
      `tools/check_docs_drift.py` all pass.
- [ ] Commit by explicit paths only; never `git clean -fd`, never `git stash`, no branches.

## When You Finish

Report: changed files with line refs, tests added/updated and their results, and a
plain-language operator summary — what Brandon will SEE change in the viewer (one warning per
outage instead of a scrolling wall; red clears itself when Rekordbox comes back), what is
unchanged (all light output, all retry behavior), and the Task 7 open question. Note that these
paths are SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED until a live run.

## Adversarial self-review (authoring, 2026-07-05)

Attack: "the edge guard eats a real second failure." Prevented: `log_changed` keys on the
failure VALUE (Task 2 keys on exception type; re-armed on connect/success in every task), so a
new failure mode or a new episode after recovery always emits. Attack: "Task 4 silences a
persistent push-loop error forever." Accepted and intended: one ERROR per episode + latched red
in the viewer until recovery — the latch, not repetition, is the visibility mechanism (that is
the AWR-125 contract). Attack: "Task 6 emits 're-attached' on first boot." Prevented by the
`rb_mem_attached` initial-state guard (first `log_changed(..., True)` on boot returns True but
the emit is additionally gated on a prior detach having set the key False — implement exactly
that: gate on the detach having occurred, not merely on value change from unset).
