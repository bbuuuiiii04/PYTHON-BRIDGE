---
doc_status: active
truth_level: operator-intent
validation_scope: codex-review-charter
---

# Codex Strict Review — SoundSwitch Pack Feature (review + fix-if-necessary)

## Your job
Perform a **strict, adversarial, code-grounded review of the bridge-native SoundSwitch pack
feature** as it stands now, and **implement fixes ONLY where you find a concrete, proven defect.**
This is not a review of the chat that produced it — review the *feature and its current code*.

You have authority to implement bridge-code fixes (the operator delegates bridge implementation to
Codex). But the bar is high: **a fix requires a concrete failure with file:line + a reproduction or
a failing test first.** No speculative refactors, no style churn, no new abstractions, no new menu
buttons. If you find a problem you decide *not* to fix, say so explicitly with your reasoning.

Work directly on `main`. Do **not** create branches or worktrees. Commit after each discrete fix.

---

## Part A — Context & what changed this session (verified; read, do not blindly trust)

The feature: the bridge can drive a 19-channel DMX lighting pack directly through an Enttec DMX USB
**Pro**, bypassing the SoundSwitch app. A menu-bar app (`scripts/bridge_menubar.py`) watches the
bridge status JSON and **auto-toggles** pack output based on whether SoundSwitch is connected:
SS disconnected → enable pack; SS connected → disable pack (SS drives). The bridge command thread
owns all output via a validate-first controller; the menubar only appends command lines.

**Operator intent (the contract to judge against):**
- Bridge runs lighting **without** the SoundSwitch app when SS is closed.
- Generated pack lives **repo-local + gitignored** at `local/soundswitch/rbss_canonical_pack`.
- SS disconnected + configured → pack output enabled; SS connected → pack output disabled.
- Unknown/stale status must **not** spam commands.
- No extra menu toggle button.

**Changes made THIS session (your primary review targets — re-verify each at current HEAD):**

1. `scripts/bridge_menubar.py:882` `_auto_set_soundswitch_pack` — **[confirmed]** the debounce
   latch `_pack_auto_pending_enabled` previously cleared only when the live snapshot confirmed
   `enabled == pending`. If an enable **failed** (e.g. no Enttec port, or port busy → controller
   never flips `enabled` true), the latch stuck forever and killed BOTH auto-enable and
   auto-disable for the menubar's lifetime. Fix: clear the latch whenever a **fresh** snapshot
   (`self._status == "on"` and snapshot present and not `stale`) needs no command; stale/off keeps
   the latch (no spam). Regression test `tests/test_bridge_menubar.py:131`.

2. `scripts/bridge_menubar.py:403` `pack_export_status_line` — **[confirmed]** added param
   `soundswitch_connected`. When the pack is **off**: if SS connected → note `"SoundSwitch active"`
   (benign, expected handoff); else map failure reasons → `pack_load_failed` → "pack unreadable —
   re-export", `pack_start_failed` → "output didn't start (check Enttec)". The benign auto-off
   reason `"disabled"`/`"none"` shows no failure note. Caller wires it at
   `scripts/bridge_menubar.py:879`. Tests at `tests/test_bridge_menubar.py:170` and `:199`.
   - **Why the connection-awareness exists [confirmed]:** SoundSwitch holds the same FTDI port
     while running (VLN docs: `[Errno 16] Resource busy`). At boot with `enabled=true`, the bridge
     eagerly opens the port (`_start_soundswitch_pack_workers` → `frame_sender.start()` which
     **raises** if the open fails, `soundswitch_frame_sender.py:138-148`), so with SS up the boot
     open fails → `reason="pack_start_failed"`. Without the SS-connected guard the menu would cry
     "check Enttec" in the *normal* SS-running case. The guard makes that benign.

3. `config/soundswitch_pack_player.json` (**gitignored, local — do NOT commit, do NOT add to git**)
   — **[confirmed]** `enttec_port` set to `/dev/cu.usbserial-EN396681`, the VLN Enttec **Pro**
   (FTDI serial `EN396681`, stable across replugs; source `~/virtuallasernode/calib/run_supervisor.sh:6`).
   Config still has `enabled=true`, `dry_run=false`, `output_backend=pack`, identity
   `fixture_map` CH1→DMX1 … CH19→DMX19. Loads clean (`available=ok`).

**Already reviewed and judged sound earlier (re-verify, don't re-litigate without evidence):**
- One canonical pack path agreed by exporter (`tools/export_soundswitch_pack.py:35`), menubar
  (`scripts/bridge_menubar.py:49`), and config `pack_path`; regenerates there every publish.
- Generated pack + sidecar + live config are gitignored (`.gitignore` `local/` and
  `config/soundswitch_pack_player.json`); `git check-ignore` passes; example config is tracked.
- Menubar never imports/calls the controller or frame sender — it only appends command lines.
- Controller is validate-first, stop-before-start on the shared port, sanitized status/errors,
  no implicit hot-enable, pack failure → disabled (never MIDI).
- F3 (a stale-pack-schema re-export guard) was deliberately **not** built (YAGNI: loader already
  rejects a stale schema major at `soundswitch_pack_loader.py:176`, and change #2 makes the failure
  visible). Confirm you agree or argue otherwise — do not build it without a concrete trigger.

---

## Part B — Review areas + adversarial questions (find real defects)

Attack each. For every finding: **file:line, what breaks, how to reproduce/prove, minimal fix.**

1. **Latch correctness (change #1).** Trace `_auto_set_soundswitch_pack` across these snapshot
   sequences and prove it neither (a) spams a command on the ~1 Hz refresh, nor (b) re-introduces a
   stuck latch: enable succeeds; enable fails then SS reconnects then disconnects; snapshot flaps
   `stale`↔fresh while a command is in flight; bridge goes `on→off→on`; `connected` missing/non-bool.
   Confirm the regression test fails on the OLD logic (red-green), not just passes on the new.

2. **Status-line truth (change #2).** Is every off-state line accurate? Specifically: SS connected +
   `pack_start_failed` (boot open lost to SS) must read benign; SS disconnected + `pack_start_failed`
   must read "check Enttec"; an in-flight export note must still win; sanitized (no paths/ports);
   `[:80]` bound holds. Any state where the line lies about what the rig is doing?

3. **Auto enable/disable end-to-end.** With the live config, confirm: SS disconnect → bridge opens
   the now-free port and drives; SS reconnect → `_go_disabled` zeros + **releases** the port so SS
   can reclaim it (`soundswitch_pack_controller.py:81`, `_safe_zero_and_stop`). Prove there is **no
   window where both SoundSwitch and the bridge hold/drive the Enttec at once.**

4. **Boot eager-open design (U3 below).** Is opening the port at boot when SS is connected (and
   eating a guaranteed `Resource busy`) the right behavior, or should the boot open be gated so the
   bridge does not fight SS for the port? Decide and justify; only change if it's a real defect.

5. **Controller/runtime boundary + 200 Hz loop.** Confirm no change pushed blocking I/O
   (serial/socket/file/subprocess) into `StateManager._push_tick`, and the menubar still drives no
   DMX. Confirm `PackRuntime` swaps stay atomic and the push loop never reads a mixed bundle.

6. **Config semantics.** `enabled` / `dry_run` / `output_backend` / `enttec_port` — coherent? Does a
   disabled/dry-run config correctly make the pack inert and `pack_auto_command` a no-op? Does
   `_prepare_pack_runtime` (`__main__.py:1273`) correctly re-read config so a hot enable works from a
   disabled runtime when (and only when) the config is armed?

### Known unknowns — INVESTIGATE and resolve (these are why this review exists)

- **U1 — fixture_map vs the real rig [unknown, HIGH value].** The live config maps CH1→DMX1 …
  CH19→DMX19 (identity). VLN owns the real fixture/DMX channel layout
  (`~/virtuallasernode/calib/fixtures.py`, `fixture_model_adapter.py`, `calib/dmx_pro.py`). **Cross-
  check the identity map against VLN's actual per-fixture DMX addressing.** If they differ, lights
  move *wrong*, not absent. If you can prove the correct map from VLN, update
  `config/soundswitch_pack_player.json` (local only) and say exactly what you derived it from. If you
  cannot prove it, leave it and flag it loudly — do **not** guess a mapping.

- **U2 — handoff race on SS quit [unknown].** SS quit → bridge sees OS2L drop (TCP) and auto-enables,
  but SS may not have released the FTDI serial port yet → `frame_sender.start()` gets `Resource busy`
  → enable fails → by change #1's anti-spam design it won't retry until the next SS connect/disconnect
  transition, leaving the pack stuck off after the operator *wanted* the bridge to take over.
  Determine whether SS releases the port before or after the OS2L socket closes. If a real race
  exists, the minimal fix is a **single bounded retry** of a failed auto-enable while still
  disconnected (no busy-loop, no per-tick spam) — implement only if you can show the race is real.

- **U3 — boot eager-open (see B4).** Tie this off with B4.

---

## Part C — Invariants that MUST still hold (live safety; do not regress)

- The menubar process **never** drives DMX and never imports the controller/frame sender; it only
  appends a JSONL command line. All output + validate-first safety stays on the bridge command
  thread.
- **No command spam:** stale / bridge-off / unknown status sends nothing.
- **No double-drive:** SoundSwitch and the bridge never simultaneously hold or drive the Enttec.
  Disabling always zeros output AND releases the serial port; enabling is validate-first and on
  failure keeps the old runtime safe (no half-swap).
- `StateManager` stays the only `DeckState` writer; the 200 Hz push loop gains no blocking I/O.
- Sanitized status only — no paths, ports, aliases, device names, fixture maps, UUIDs, or raw
  exception messages in `soundswitch_pack` status or any `set_soundswitch_pack` error.
- Generated pack artifacts and `config/soundswitch_pack_player.json` are **never** committed.
- No new git branch; no new menu toggle button.

---

## Part D — Tests

- Keep `tests/test_bridge_menubar.py`, `tests/test_soundswitch_pack_commands.py`,
  `tests/test_soundswitch_pack_player_config.py`, `tests/test_soundswitch_pack_startup.py`,
  `tests/test_soundswitch_pack*.py`, `tests/test_prove_soundswitch_pack_generation.py`,
  `tests/test_source_fingerprint_parity.py` **green**.
- Any fix you make needs a **pure-function test** (no AppKit, no on-disk/subprocess dependency) that
  fails before the fix and passes after. Do not modify existing tests just to make them pass; if an
  existing assertion is wrong, justify the change.

---

## Part E — Acceptance (definition of done)

- A written verdict: **PASS / REVISE / FAIL**, findings severity-ordered, each with file:line +
  proof.
- Every claim labeled **confirmed / assumed / unknown**; unknowns surfaced, not buried.
- U1 and U2 explicitly resolved (fixed-with-evidence, or flagged-with-reason-not-fixed).
- Any fix: committed, with a pure-function test, all suites green, and you confirm you did NOT touch
  out-of-scope subsystems, the 200 Hz loop, the export/detection logic, or commit any local pack/config.
- If nothing needs fixing, say so plainly with the evidence that proves it — do not invent work.

---

## Verification commands

```bash
# tests that import the package run from the PARENT of the repo:
cd /Users/bbui && python3 -m unittest \
  rb_ss_bridge_v2.tests.test_bridge_menubar \
  rb_ss_bridge_v2.tests.test_soundswitch_pack_commands \
  rb_ss_bridge_v2.tests.test_soundswitch_pack_player_config \
  rb_ss_bridge_v2.tests.test_soundswitch_pack_startup

# the prove + parity tests import `tests.*`, so run them from the REPO ROOT:
cd /Users/bbui/rb_ss_bridge_v2 && python3 -m unittest \
  tests.test_prove_soundswitch_pack_generation tests.test_source_fingerprint_parity

# gitignore + hygiene:
cd /Users/bbui/rb_ss_bridge_v2
git check-ignore local/soundswitch/rbss_canonical_pack/manifest.json config/soundswitch_pack_player.json
git diff --check
python3 tools/check_docs_drift.py    # if you touch runtime command/status surfaces

# canonical export still lands repo-local (optional, needs the SS source project):
cd /Users/bbui && python3 -m rb_ss_bridge_v2.tools.export_soundswitch_pack \
  --publish-canonical --result-json /tmp/rbss-pack-codex-review.json && cat /tmp/rbss-pack-codex-review.json
```

## When you finish
Report: the verdict, every finding (with file:line + proof), what you fixed (with test output
pass/fail counts) and what you deliberately left (with reasons), U1/U2 resolutions, and confirm you
committed only in-repo source/tests on `main` — never the local pack or `config/soundswitch_pack_player.json`.
