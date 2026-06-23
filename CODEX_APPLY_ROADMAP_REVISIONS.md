# DISPOSABLE — Codex: apply SoundSwitch roadmap review revisions

**This file is disposable. Delete it (`git rm CODEX_APPLY_ROADMAP_REVISIONS.md`) as your last step.**

You are Codex applying the corrections from an Opus adversarial review of the SoundSwitch
exporter roadmap. This is a **docs-only** task on branch `soundswitch/impl`.

## Hard rules
- **Docs only.** Do NOT change any `*.py`, config, the SoundSwitch project, or the bridge.
- Do NOT start/stop/restart the bridge. Do NOT open any device.
- Code wins over docs (AGENTS.md §1). Every claim you write must match current code at HEAD.
- Re-resolve every line anchor yourself at current HEAD before editing — **line numbers shift as
  you edit**, so match by content/grep, not by the numbers quoted here. Apply edits top-to-bottom.
- The review was performed at HEAD `0b781a6`. Code is unchanged since `b2ce63d`; only Markdown +
  `change_contracts.yml` (housekeeping) + `tools/prove_soundswitch_pack_generation.py` (docstring
  path fix) changed after `b2ce63d`.

## Files you may edit
- `docs/plans/active/soundswitch_exporter_remaining_work.md` (the roadmap — primary)
- `docs/prompts/reviews/soundswitch_exporter_remaining_work_adversarial_review_prompt.md` (metadata only)
- `docs/agents/change_contracts.yml` (only if bumping the `soundswitch_pack_player`
  `last_verified_commit`; otherwise leave it)

---

## P1 — CRITICAL: shutdown ownership of a runtime-swapped sender (currently omitted + overclaimed)

**Evidence (verify before writing):**
- `__main__.py` `pack_output_owners = {"sender": None, "midi_input": None}` (~line 872) is written
  ONLY at startup (~906–907, 911–912). `_cleanup_pack_outputs()` (~874–890) and the SIGTERM/SIGINT
  `_shutdown` (~1540–1563) and `atexit` (~893) stop only those startup-registered objects.
- A runtime `set_soundswitch_pack` enable / `backend=pack` / reload-while-enabled goes through
  `SoundSwitchPackController._swap_to_started()` (`soundswitch_pack_controller.py:98–121`), which
  builds a NEW started `frame_sender`/`midi_input` and publishes them via
  `StateManager.set_pack_runtime` (`state_manager.py:3233–3240`). It never updates
  `pack_output_owners`. So after a swap the live sender lives only in `sm._pack_runtime`; SIGTERM
  zeroes the stale (already-stopped) startup sender, NOT the live one.
- `StateManager.stop()` (`state_manager.py:614–615`) only sets the stop event; the run loop
  (`_run`, ~868–895) has no teardown that zeroes the live backend.
- The only shutdown test, `tests/test_soundswitch_pack_startup.py:193`
  (`test_shutdown_zeros_pack_before_slow_bridge_joins`), is a **static source-order assertion** on
  `_shutdown`; it does not exercise SIGTERM-after-runtime-swap.
- Live exposure today is gated OFF (pack disabled, local config absent). This is a **latent** defect
  that becomes live the moment pack mode is enabled and a runtime swap occurs.

**Edits:**
1. In §4.4 ("Low-level direct-DMX software lane"), the bullet
   `[x] [C] Graceful stop requests a zero packet before serial close.` — qualify it. Make clear the
   zero-before-close holds for the **startup-owned** sender only; a sender created by a runtime
   `set_soundswitch_pack` swap is published into `sm._pack_runtime` but is **not** registered in
   `__main__.pack_output_owners`, so `_cleanup_pack_outputs` on SIGTERM/SIGINT/atexit does not
   zero/stop it. Cross-reference the new RW item from P1.4.
2. In the §3 completion matrix, row `Pack config/startup/runtime commands | implemented, default-off`
   — change the "Verified boundary" cell to flag that the atomic runtime-bundle swap does **not**
   re-register output owners for shutdown cleanup (post-swap shutdown-ownership gap).
3. Mandatory-invariants §7 #13 ("Graceful shutdown sends zero") — add a parenthetical that this is
   currently guaranteed only for the startup-owned sender; runtime-swapped senders need the fix in
   the new RW item.
4. Add a new remaining-work item under §5 (e.g. **RW-1A — Runtime output ownership on shutdown**,
   placed before RW-6 and gating M5/hardware and any pack-enable). Content:
   - Status: `[C] confirmed gap`.
   - Evidence anchors above.
   - Required: after any runtime swap, the live published `PackRuntime`'s `frame_sender`/`midi_input`
     must be reachable by shutdown cleanup — either re-register them into `pack_output_owners` at
     publish time, or have `_shutdown`/`atexit` zero+stop `sm.get_pack_runtime()` directly. No
     blocking work may enter `_push_tick`.
   - Acceptance gate (must be able to FALSIFY failure): a behavioral test that performs a runtime
     swap to a new fake sender, raises SIGTERM, and asserts the **live** sender's
     `zero_and_stop()` was called and the stale startup sender's stop is a harmless no-op. Note that
     the current `test_shutdown_zeros_pack_before_slow_bridge_joins` is source-order only and does
     not cover this.
   - Add this item to the §6 dependency-ordered milestones (it gates enabling pack output at all).

---

## P2 — HIGH: "controller already validates a disabled pack while staying off" is misleading

**Evidence:**
- RW-1 currently says (under "Required behavior", the reload bullet):
  *"The existing controller already validates a disabled pack while staying off."*
- `SoundSwitchPackController._reload` (`soundswitch_pack_controller.py:139–147`) calls
  `_prepare()` and, when the runtime is disabled, returns `(True, "reloaded_disabled")` only if
  `_prepare()` succeeds.
- `__main__._prepare_pack_runtime` (`__main__.py:1234–1247`) raises `RuntimeError("pack_prepare_failed")`
  unless the built bundle has non-None `player` AND `frame_sender` AND `laser_backend`.
- `_build_soundswitch_pack_startup` (`__main__.py:454–529`) only yields a non-None `frame_sender`
  in the `reason=="pack"` branch — which requires `enabled=true`, `output_backend=="pack"`, a valid
  `enttec_port`, and a valid CH1–CH19 `fixture_map`. Config defaults are
  `enabled=false / dry_run=true / output_backend="none"` (`soundswitch_pack_player_config.py:105–107`;
  `config/soundswitch_pack_player.example.json`), and an absent local config → `available=false`.
- Therefore: for a missing / `enabled=false` / `output_backend=none` / `dry_run=true` /
  `pack` + missing-port config, `_prepare()` RAISES and `reload` returns a sanitized failure — it
  does **not** "validate while staying off." Validate-while-off works only when the on-disk config is
  fully pack-capable AND the runtime is currently disabled. Validation also REQUIRES a configured
  `enttec_port` + `fixture_map` (it just doesn't open the port).

**Edit:** Replace the misleading sentence in RW-1 with the precise semantics above. Make explicit:
in the documented safe posture (RW-6: `enabled=false / dry_run=true / output_backend=none`), a
post-publish `set_soundswitch_pack/reload` returns a sanitized failure, so the RW-1 design must treat
**export success as standalone** and must not depend on reload to confirm the published pack when
disabled. Note this is a design input for RW-1, not a contradiction of "reload never enables."

---

## P3 — MEDIUM: metadata staleness + inaccurate "Markdown only" claim

**Evidence:** roadmap + review-prompt frontmatter `last_verified_commit: 0c2ba07`; current HEAD is
`0b781a6`. Commits `43a00dd` and `0b781a6` (after `0c2ba07`) changed
`docs/agents/change_contracts.yml` (contract housekeeping: added the two new prompts, dropped
`history/` files) and `tools/prove_soundswitch_pack_generation.py` (docstring path fix only — no
behavior change). The §2 sentence *"The intervening commits changed Markdown only (plus an unrelated
plan file)"* is now literally false.

**Edits:**
1. Bump `last_verified_commit` to the HEAD you re-verify against in BOTH the roadmap and the review
   prompt frontmatter, and update `last_verified_date` to today.
2. In §2 ("Audit snapshot"), correct the "Markdown only" sentence: note the two post-`0c2ba07`
   commits also touched `change_contracts.yml` (housekeeping) and the proof tool's docstring; code
   findings remain tied to `b2ce63d` (no runtime-behavior change).

---

## P4 — LOW: "consolidation corrects that routing drift" overstates

**Evidence:** `python3 tools/check_docs_staleness.py --report` at HEAD still reports
`soundswitch_pack_player ... STALE` (baseline `a5f7ced`) and lists the roadmap among re-verify docs;
the contract's `last_verified_commit` was not bumped.

**Edit:** In §2.2, soften "This consolidation corrects that routing drift" — state that routing was
de-duplicated but the advisory staleness for `soundswitch_pack_player` persists at HEAD until the
contract's `last_verified_commit` is re-verified/bumped. (Optionally bump that contract's
`last_verified_commit` in `change_contracts.yml` only if you actually re-verify its docs.)

---

## P5 — LOW: hot-path lock wording

**Evidence:** the 200 Hz path takes two short-held, non-blocking locks — the Enttec mailbox lock
(`enttec_dmx_pro.py:158–161`, `put_frame` → `deque.append` under `self._lock`; serial write happens
off-lock in the worker `_run`) and the MIDI input snapshot lock
(`soundswitch_midi_input.py:100–122`). Each guards only an in-memory operation with NO I/O inside.
Invariant §7 #2 bans "blocking queue operation"/I/O, not these locks — so the invariant holds, but a
reader scanning for "no locks in the hot path" would be misled.

**Edit:** In §7 #2 (or §4.4), add a one-line acknowledgement that these two short-held non-blocking
mailbox/snapshot locks are the permitted synchronization (no I/O within the critical section), so the
invariant is precise.

---

## P6 — LOW (optional): RW-1 acceptance gate cannot falsify the reload-failure mode

**Evidence:** RW-1 acceptance gate "disabled runtime stays disabled" passes whether reload
validated-and-stayed-off OR errored-and-stayed-off — it cannot distinguish the failure mode in P2.

**Edit:** Add an RW-1 acceptance line distinguishing a `reloaded_disabled` success (pack-capable
config) from a sanitized reload failure (non-pack-capable/disabled config), so the gate can falsify
the P2 failure mode.

---

## After editing — verify (docs-only checks)
```bash
cd /Users/bbui/rb_ss_bridge_v2
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
git diff --check
```
All three hard checks must pass; `git diff --check` must be clean. Do NOT run hardware, the bridge,
or any device. Do not modify tests or code to make a doc claim true.

## Last step — dispose of this prompt
```bash
git rm /Users/bbui/rb_ss_bridge_v2/CODEX_APPLY_ROADMAP_REVISIONS.md
```
Then report: which P-items you applied, the HEAD you re-verified against, and the check results.
