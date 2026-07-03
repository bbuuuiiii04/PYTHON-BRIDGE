---
doc_status: review-evidence
truth_level: review-instructions
last_verified_commit: fc56bb5
last_verified_date: 2026-07-03
validation_scope: adversarial pre-implementation review prompt; review-only, no implementation authority
---

# Codex Task — STRICT pre-implementation review of Phase 2 (Part F)

**Role:** You are a strict, adversarial reviewer. **Do not implement. Do not edit any file.** Produce a
written review only. Your job is to try to break this plan before any code is written and before any
bridge restart on a live-performance rig.

**Repo:** `/Users/bbui/rb_ss_bridge_v2`

**Baseline:** the plan was written against `2eff33e`. Re-verify HEAD yourself
(`git rev-parse HEAD`, `git status`). If HEAD moved or the tree is dirty, re-resolve everything against
the actual current code and say so explicitly.

**Source-of-truth order (AGENTS.md §1):** executable code > tests > the plan doc > the spec. If the
plan doc or the spec disagrees with the code, **the code wins — quote the code**. Do not trust any
`file:line` in the docs; open the file and confirm.

---

## Read (in this order)
1. `AGENTS.md` fully — especially §6 invariants (200 Hz push loop must gain no blocking/MIDI/socket/
   file/subprocess I/O; one writer of DeckState), §1 source-of-truth, §10 status language.
2. `docs/plans/active/streamdeck_midi_bridge_integration_spec.md` — **Part F only**.
3. `docs/plans/active/streamdeck_phase2_plan_review.md` — **the plan you are reviewing**.
4. The exact current code (re-resolve every anchor yourself):
   - `soundswitch_midi_input.py`
   - `soundswitch_laser_player.py`
   - `soundswitch_pack_loader.py`
   - `soundswitch_pack_player_config.py`
   - `state_manager.py` — the `_drive_pack_output` pack driver and the degradation latch
   - `__main__.py` — `SoundSwitchMidiInputGroup` wiring
   - Task 6 path: `tools/export_soundswitch_pack.py`, `soundswitch_pack.py`,
     `soundswitch_pack_verifier.py`
   - `tests/test_soundswitch_midi_input.py`, `tests/test_soundswitch_laser_player.py`,
     `tests/test_prove_soundswitch_pack_generation.py`

## Run if you can
- `python3 -m unittest discover tests` — baseline is ~**2382 OK** (skipped 3, xfail 1). Report the
  actual number.
- A token grep proving the compositor stays generic: no `streamdeck` / `Stream Deck` string anywhere
  under the bridge runtime `*.py` (the controller script and the sibling sidecar are the only
  device-aware surfaces).

---

## Anchor audit (do not trust the docs' line numbers)
For **every** `file:line` claim the plan cites, open the file and mark it:
**CONFIRMED** / **MOVED** (give the new line) / **CONTRADICTED** (quote the code) / **NOT-FOUND**.
At minimum cover: single-slot player state; the opaque `[0]*19` static render + whole-frame-replace
`resolve_frame`; the scalar `_held_static_slot`; the **stale-clear writes inside `snapshot()`** (the
read path that runs on the push loop); the group snapshot conflict collapse; the StateManager
degradation latch (trip/clear/overlay-drop); pack reload reset; `interaction` decode →
`PackMidiBinding.interaction`; the sparse `generic_attributes` + the `fixture_group !=
PRIMARY_FIXTURE_GROUP` filter; `controller_hold_timeout_ms` wiring; and the Task 6 verifier file-set
equality + pinned `manifest_sha256`.

---

## Scrutinize these hard (the plan lives or dies on them)
1. **200 Hz push-loop purity.** The plan moves the stale-clear writes out of `snapshot()` (which today
   mutates engine state on the hot path) to the worker thread, and has the push loop read an immutable
   tuple. **Prove or disprove:** after the change there is **no** write, lock, or I/O on the push loop
   (`_drive_pack_output`), and `snapshot()` is a pure read. Find any path where the loop still mutates
   engine state or could hand the loop a live (mutable, shared) list.
2. **Transparency seed.** `apply_layers` must start from a **copy of `base`**, never `[0]*19`. Confirm
   the plan's render rules cannot reintroduce the black-fill, and that the `fixture_group` filter is
   replicated **per layer** (a naive `(channel, value)` patch would write channels the engine
   intentionally drops). State exactly which test would catch a regression.
3. **Behavior inversion (single-slot REPLACE → STACK).** Confirm the new lifecycle is internally
   consistent: press over a toggle reverts to the toggle on release; two toggles compose; re-press of an
   active toggle removes it **without reordering**; remove-then-re-press lands on top. Confirm the plan
   correctly flags the existing single-slot tests as needing **REWRITE** (not extension). **Name any
   single-slot test the plan missed.**
4. **Degradation latch restriction.** The plan limits the push-loop drop-all to **true worker-death /
   port-gone** and stops dropping on transient `error` strings / `new_drop`. **Prove both:** it cannot
   strand a stale layer (fail-closed still holds when the snapshot is malformed), AND it cannot blink the
   whole stack on a transient glitch. Confirm the latch-clear still requires a clean/quiet/healthy tick.
5. **Port-gone backstop.** Worker-thread only; injectable `get_ports`; **exact string match**;
   **non-string entries treated as absent**. Confirm it never runs on the push loop and is the only
   thing that clears a stuck held layer — load-bearing on the Phase 1 controller closing its virtual
   port on deck loss. Confirm the accepted residual (a `note_off` lost while the port stays up) is
   correctly flagged, not silently relied upon.
6. **Blackout auto-release.** Removing the 2 s static timeout must **not** kill blackout-hold
   auto-release (they share a gate today). Confirm the plan keeps blackout's timeout, evaluated on the
   worker thread, and that a test pins it.
7. **Pack reload.** `reload()` empties the stack and the player resets via `set_static_layers([])`; slot
   indices are positional and **unstable** across reload. Confirm a carried-over layer cannot survive a
   reload and point at the wrong look.
8. **Task 6 — LOCKED to sibling sidecar (next to the pack folder, NOT inside it).** Confirm: writing
   `midi_bindings.json` **inside** the pack dir is rejected by the verifier's strict file-set equality
   and wiped by the re-export/atomic-swap; the plan's sibling approach (mirroring `_write_source_sidecar`)
   leaves `manifest_sha256` and the **pinned** proof-gate hash untouched. Verify the pinned-hash location
   and that the plan does **not** edit `compile_pack_artifacts` or the manifest.

---

## Locked decisions — do NOT reopen (flag only if the code makes one impossible)
- Stack order = execution **recency**, newest on top; re-press of an active toggle **removes** it (no
  reorder).
- Per-layer render error → **skip + non-blocking diagnostic** (never ZERO the whole frame; never log
  from the render path).
- Degradation drop-all **restricted to worker-death / port-gone**.
- Cross-device ordering = **by process-global recency** (one controller live; multi-surface merge is
  still tested, not relied on live).
- Task 6 sidecar = **next to the pack folder (sibling)**, build-time only.

---

## Adversarial mandate
Actively try to break Phase 2 against a live mix. For each break, give: **the scenario → the exact
code/plan line that allows it → the smallest fix.** Cover at least:
- a look held when blackout/emergency fires;
- a deck yanked mid-press;
- a pack reload while looks are held;
- a malformed look sitting in the middle of a 3-layer stack;
- a transient worker `error` string mid-set;
- two looks fighting over the same DMX channel;
- the controller's pad LED diverging from the bridge's real stack.

---

## Output (concise, evidence-first; no `STATUS:` blocks)
1. **Verdict:** exactly one — READY / REVISE / NOT-READY.
2. **Anchor audit table:** each cited claim → CONFIRMED / MOVED / CONTRADICTED / NOT-FOUND + citation.
3. **New risks the plan misses** — each with `file:line` and the smallest fix.
4. **Any spec/plan line that contradicts code** → quote the exact replacement wording.
5. **Per-task go/no-go (5A–5G, 6, 7):** can Codex implement it as written without guessing? If not, name
   the exact missing detail.
6. **Live-safety sign-off:** does any task add I/O, locks, or mutation to the 200 Hz loop, or change
   autoloop/scripted/blackout output when no layer is active? Yes/no, with proof.

Label every claim **confirmed / assumed / unknown**. Surface unknowns; never guess. **Review only — do
not implement, do not edit files.**
