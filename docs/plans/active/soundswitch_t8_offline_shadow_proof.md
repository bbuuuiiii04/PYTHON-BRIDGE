# Task 8 — SoundSwitch offline + shadow proof (completion record)

status: done (software) — **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**
last_updated: 2026-06-22
implementer: Claude (Opus 4.8) — per operator override for this task (NOT Codex)
target branch/PR: `soundswitch/impl` / #116

> Scope guard: Task 8 is an OFFLINE + SHADOW software gate. No MIDI/serial/Enttec/DMX device was
> opened, no bridge was restarted, no output was sent. This record never claims hardware, show, or
> rig readiness. The hardware gate is Task 9 (operator-executed only).

## Item-by-item evidence (spec `soundswitch_t7_t8_t9_implementation_spec.md` Task 8)

| # | Requirement | Evidence | Status |
|---|---|---|---|
| 0 | Proof gate PASS; canonical UUID + active-cue union SHA | `prove_soundswitch_pack_generation` → `PASS_IMPLEMENTATION_MAY_BEGIN`, 29 PASS / 0 FAIL / 0 INCOMPLETE (foundation 27/27); UUID `{3CCBCD6F-7C1B-44D8-882C-A52A74CC1827}`; union SHA `88a2e94848b696ff685fc747593d1440abb760034f8b6ea2fd71a525d1b4f4a2` | confirmed |
| 1 | F9 (one-byte pack mutation rejected) + F10 (active CC/pitch override export-fail) | proof gate `F9-pack-one-byte-mutation` PASS, `F10-active-cc-override` PASS | confirmed |
| 2 | Export twice → byte-identical tree | `test_soundswitch_pack.py::test_two_exports_are_byte_identical` (skips if live project absent) | confirmed (local) |
| 3 | Independent verifier rejects every adversarial mutation | proof gate `F1–F10`; `test_soundswitch_pack.py` source/inventory/hash/canonicalization/semantic mutation rejection | confirmed |
| 4 | Totals all hold | `test_soundswitch_pack.py::test_current_totals_crosswalk_and_catalog_tail` (233/232/1/32/42/45/44; DDJ slots 8/16/17/24) | confirmed (local) |
| 5 | Oracles without contamination | proof gate A5 / cold new-track / legacy-discriminator checks; captures used as oracles only (production modules do not import `tools/ssfmt/re/`) | confirmed |
| 6 | Static tests slots 8/16/17/24 + controlled slot-7 create/edit | proof gate `check_static_looks` render of 8/16/17/24; `test_shadow_soundswitch_pack.py::StaticSlotCoverageTests` (slot 8 + slot-7 create→edit via reload) | confirmed |
| 7 | Shadow mode: physical backend `none`, log ONLY frame hashes, compare to independent expected | **new** `tools/shadow_soundswitch_pack.py` + `tests/test_shadow_soundswitch_pack.py` | confirmed (software) |

## Shadow harness (`tools/shadow_soundswitch_pack.py`)

- Drives a verified `LaserPackPlayer` through scripted/static/blackout transitions with the physical
  output backend forced to `none` (`NoneBackend`, or `PackOutputBackend` with **no** frame sender).
  `run_shadow` REJECTS any backend that is not `none`/`pack` or that reports `has_frame_sender` — so
  shadow mode can never open a device or transmit a frame.
- Records **only** per-step frame SHA-256 hashes plus the sanitized player diagnostic *code*; the
  report dict carries no raw channel values, audio/file paths, SoundSwitch identities, or device
  names (asserted by `ReportSanitizationTests`).
- Each emitted frame hash is compared against an **independently hand-computed** expected frame
  (not produced via the player's renderer), so a transition/precedence regression fails closed.
- Proven transitions resolve to a zero frame: scripted-stopped, cleared-selection, blackout,
  emergency, and post-reload-wait. A held Static Override stands alone over a cleared base, and
  loses to blackout/emergency and to the post-reload wait latch.
- Twice-run determinism: two passes produce byte-identical report dicts.

## Autoloop coverage — DEFERRED (not skipped silently)

Autoloop FRAME shadow coverage is gated on the T7d phase-origin proof (ticks/beat + universal phase
origin), which remains unproven. The report records this explicitly as
`autoloop_coverage = "deferred_t7d_phase_origin"` with a human note, and `categories_covered` never
contains `autoloop`. The live driver still resolves autoloop output to safe-zero and never calls
`select_autoloop`.

## Single-process verification + rollback plan

- The harness is a single throwaway process: it builds an in-memory player and exits. It writes no
  files, opens no sockets/MIDI/serial, and starts no threads, so there is **nothing to roll back**.
- It does not touch the running bridge. Running it does not change the one-bridge-process invariant
  (`pgrep -f rb_ss_bridge_v2 | wc -l == 1`); no restart is involved.
- Rollback for the code change itself is a normal `git revert` of the two added files
  (`tools/shadow_soundswitch_pack.py`, `tests/test_shadow_soundswitch_pack.py`) plus the doc edits;
  no runtime behavior of the bridge changes if they are removed.

## Commands run (results)

- `python3.14 -m unittest tests.test_shadow_soundswitch_pack` → **OK** (14 tests).
- `python3.11 -m unittest tests.test_shadow_soundswitch_pack` → **OK** (14 tests).
- `cd /Users/bbui && python3.14 -m rb_ss_bridge_v2.tools.prove_soundswitch_pack_generation` →
  **PASS_IMPLEMENTATION_MAY_BEGIN** (29/0/0; foundation 27/27).
- `python3 -m unittest discover tests` → see PR/CI run.

## Remaining (not part of Task 8)

- The spec's **after-T8 adversarial review** (opus max) is a separate review step, not executed here.
- **Task 9** — operator hardware-gate handoff DOCUMENT (author only; never execute).
- **T7d** — autoloop DMX stays blocked until the phase-origin capture proof lands.
