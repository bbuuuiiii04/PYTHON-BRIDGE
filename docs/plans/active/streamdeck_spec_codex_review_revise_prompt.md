# Codex task — independent review & revise of the Stream Deck spec

You are a senior adversarial reviewer **with edit rights to one file**. A spec for a **live lighting
rig** was just revised after an Opus adversarial review; your job is an **independent cross-check** of
those revisions — verify they hold against the actual code, catch anything missed, and **revise the
spec in place** where you find a concrete defect. A wrong call here causes a bad show.

**Target (review, and edit only this file):**
`docs/plans/active/streamdeck_midi_bridge_integration_spec.md`
**Repo:** `/Users/bbui/rb_ss_bridge_v2` — read the code freely; do **not** modify any code, only the
spec file above.
**Prior human review that drove the current revision (context, not gospel):**
`docs/plans/active/streamdeck_spec_review_prompt.md`

## Rules of engagement
- **Code wins over the spec** (AGENTS.md §1: code > tests > config > docs). Open every `file:line` the
  spec cites and confirm the code still says what's claimed. List any anchor that is stale/wrong/moved.
- Label every finding **BLOCKER / MAJOR / MINOR**, each with exact `file:line`, the **specific failure
  scenario** it causes on a live rig, and a concrete fix. No vague "consider".
- **"Looks fine" is not review.** Force a failure for each risk.
- Work on the current branch (`main`); do **not** create branches/worktrees (AGENTS §0).

## Authorization & guardrails (read carefully)
- You **may edit `streamdeck_midi_bridge_integration_spec.md`** to fix concrete defects you prove:
  stale anchors, an underspecified seam Codex couldn't build without guessing, a missing live-safety
  guard, an internally inconsistent instruction.
- You may **not** touch any `*.py`, the watcher, or any other file. Spec-doc only.
- **The four "RESOLVED 2026-06-25" decisions and the Phase-1/Phase-2 gating are operator sign-off.**
  If you believe one is wrong or unsafe, **flag it with evidence and propose an alternative in your
  report — do NOT silently flip it in the spec.** Everything else you may revise directly.
- Preserve the existing Part A–F structure, the `[confirmed]/[assumed]` labels, and the status
  language rules (AGENTS §10 — no "production-ready/show-ready/stable" etc.).
- After any edit, run the hard checks (below) and confirm green.

## What to verify

### Phase 1 (Tasks 1–4 — ready for Codex)
- SIGTERM: registering both SIGINT+SIGTERM + making waits `stop.wait()` actually runs the deck
  reset/port close on the watcher's `kill`/`pkill`. Confirm current code handles only SIGINT.
- flock single-instance: the spec now mandates a **module-global lock-file reference** for the process
  lifetime. Confirm that's stated and correct (fd GC would release the lock). Confirm flock
  auto-releases on crash.
- Supervisor loop: `acquire_deck()` now catches **any** enumeration exception (not just
  Transport/OSError); `deck.connected()` exists and detects a yank; the key callback is shown wrapped
  in try/except so it can't raise out of the library reader thread.
- Watcher wiring (`/Users/bbui/ss_bridge_watcher.sh`): does `stop_streamdeck` fire on **every**
  teardown path (auto `stop_bridge`, `cleanup`/EXIT/INT/TERM, manual-terminal-closed)? Does
  `start_streamdeck` run only while the bridge is up, in both manual and auto modes? Confirm the
  **anchored** `pgrep`/`pkill` pattern (`[p]ython3?.*streamdeck_midi\.py`) can't match an editor or
  the watcher's own grep — and can't miss the real process.
- Channel-3 safety: the selftest asserts `CHANNEL not in (0,1)` (lasers' MIDI ch 1–2). Confirm
  `CHANNEL = 2` today and that the assertion really guards the laser channels.

### Phase 2 (Part F, Task 5 — live-critical; gated, but verify the spec is buildable & safe)
- **Anchors:** re-verify the load-bearing `[confirmed]` cites against current code:
  `soundswitch_laser_player.py:143-163,186` (`render_static_look_frame` `[0]*19`, `resolve_frame`,
  `_active_static_slot`); `_apply_attribute` `PRIMARY_FIXTURE_GROUP` filter at `:78`;
  `soundswitch_midi_input.py` `_held_static_slot`/`snapshot()` stale-clear (`:110-119`)/
  `MidiInputSnapshot` (`:47`)/group single-slot collapse (`:508-525`)/`_make_real_source`
  (`:361-372`); `generic_attributes` sparsity (`soundswitch_pack_loader.py:586`); `on_pack_reload`
  and slot-index keying (`:582`); degradation latch (`state_manager.py:3418-3428`); inert
  `_mail_drop_count` (`soundswitch_midi_input.py:89,125` — never appended/incremented).
- **Transparency:** confirm the render rule (copy base, never `[0]*19`, apply only set channels,
  replicate the `PRIMARY_FIXTURE_GROUP` filter) actually produces transparency + Lego compose +
  topmost-wins + explicit-0 override. Find any path where a layer would black channels it doesn't set.
- **Purity:** the render must be a pure function read by the 200 Hz push loop, with stack mutation +
  the new `get_ports()` re-check on the **worker** thread, and the snapshot an **immutable tuple**
  copied under `_lock`. Find any place the spec would put I/O or a live-list read on the push loop, or
  leave `snapshot()` mutating state.
- **Precedence:** confirm emergency/blackout still blacks the **whole** stack and that "blackout-hold
  auto-release" survives removing the 2 s timeout.
- **The port-gone backstop (the resolved #1 decision) — stress its core assumption:** verify that when
  the controller closes its virtual MIDI **output** port (Task 3 `finally: port.close()`, or the
  controller process dying), that port actually **disappears from the bridge's `MidiIn.get_ports()`**
  so the worker's re-check fires. This is `[assumed]` and load-bearing — if a closed/abandoned virtual
  source can linger in `get_ports()`, the backstop fails and a held press sticks. Confirm or refute
  against python-rtmidi/CoreMIDI behavior, and confirm calling `get_ports()` periodically on an
  already-open `MidiIn` is safe. If refuted, that's a BLOCKER — flag it (don't flip the decision).
- **Edge cases — enumerate concrete outcomes:** re-press toggle = remove (not move-to-top);
  remove-then-re-add lands on top; two toggles overlapping one channel; press-over-toggle reverts to
  the toggle; removing a mid-stack layer; pack reload while layers held (slot reindex → wrong look —
  spec says clear on reload; verify the reset path); controller-LED vs bridge-stack divergence (spec
  now says cosmetic/may-invert — confirm it no longer claims "correct by construction").
- **"No Stream Deck in the bridge" invariant:** confirm no `streamdeck`/`Stream Deck`/`StreamDeck`
  token under `rb_ss_bridge_v2/*.py`; the compositor + MIDI input are generic; device logic lives only
  in the controller + the device-agnostic sidecar.
- **Implementability:** can Codex build **Task 5** with no guessing? The spec now names the snapshot
  field (`held_layers`), the player API (`set_static_layers`), the group merge, the render function
  (`apply_layers`), and the disconnect seam. Name anything still underspecified.
- **Test seams:** are the listed pure-function + stack-lifecycle + port-gone-clear + skip-bad-layer +
  LED-mapping tests sufficient to catch regressions, and is the `get_ports()` check injectable for
  hardware-free testing? Name what's still untestable.

## Cross-cutting (codex-spec 9-point pre-handoff checklist)
Claims labeled; verified vs current code; pending-state guards; mode-transition cleanup; third-party
API completeness (rtmidi/StreamDeck); cross-checked vs existing code; pure-function test seam;
live-safety explicit; adversarial self-review.

## After editing
Run and confirm green (AGENTS §8):
```
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
```
Do not modify tests/code to make a check pass.

## Output (report back in chat)
1. **Verdict:** `APPROVED` / `REVISE-AND-APPROVE` / `REJECT`.
2. **Failed-verification list:** every spec claim that did not hold vs code, with `file:line`.
3. **Revisions you made** to the spec (what + why), and the hard-check results after.
4. **Flagged-not-changed:** any concern with the four operator-signed decisions or the gating, with
   evidence + proposed alternative (you did not edit these).
5. **Top 3 things most likely to cause a bad show**, ranked.
Be terse. Evidence over assertion.
