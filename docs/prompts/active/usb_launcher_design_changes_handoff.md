---
doc_status: current
truth_level: handoff-report
last_verified_commit: 02250de
last_verified_date: 2026-07-04
validation_scope: >
  Handoff describing doc-only edits this session made to the AWR-122 USB launcher design
  spec and its registry rows before the operator descoped launcher work from this session
  (2026-07-04 evening). No code changed, no impl spec authored, nothing implemented.
  For the agent that owns the USB launcher workstream.
---

# Handoff — edits made to the USB launcher design spec by the gesture-v2 session

**To:** the agent/session that owns AWR-122 (`usb_bridge_launcher_design.md`).
**From:** the Fable session running `docs/prompts/active/spec_review_revise_implement_fable_prompt.md`
(spec review + gesture-v2 implementation). That prompt named your design spec as a review
target; the operator has since ruled the launcher OUT of my scope. This handoff is the
complete record of what I changed so you can keep, adjust, or revert it. I stopped before
authoring any implementation spec.

## Where the changes live

- Commits: `ff3d855` (a parallel auto-sync swept my in-progress edits) + `02250de` (my
  labeled commit). Diff both against `8abccdf` to see the full delta:
  `git diff 8abccdf..02250de -- docs/plans/active/usb_bridge_launcher_design.md docs/status/active_work_registry.md`
- Files touched: `docs/plans/active/usb_bridge_launcher_design.md`,
  `docs/status/active_work_registry.md` (AWR-121/122/123 rows). Nothing else.

## What I changed in the design spec, and why

1. **Header/intro** — added `last_verified_commit: 8abccdf`; noted the doc was reviewed
   twice (my pass + AWR-123) and pointed "next step" at a Milestone-1-only Codex spec
   named `docs/plans/active/usb_bridge_launcher_m1_codex_spec.md`. **That file does NOT
   exist** — I was descoped before authoring it. Keep the M1-first framing or rename the
   pointer as you see fit; if you drop it, nothing else references it.
2. **§2(a) launch profile** — corrected the env list against
   `scripts/ss_bridge_watcher.sh:122-145` at HEAD: the design omitted six flags
   (`RBSS_LED_PHRASE_MONOTONIC=1`, `RBSS_LED_MIN_DWELL=1`, `RBSS_LED_CANCEL_PENDING=1`,
   `RBSS_LED_RT_RECONCILE=1`, `RBSS_LED_TRANSPORT_STICKY=1`,
   `RBSS_LED_TRANSPORT_COOLDOWN=0`). Also documented that the watcher's own manual path
   (`:161`) omits those six — the two paths in one script have already drifted
   (verified harmless today only because all six match code defaults; defaults verified
   at `led_dispatch_coordinator.py:64,69,72`, `led_look_director.py:57`,
   `govee_realtime_runner.py:91`, `led_dispatch_policy.py:120`).
3. **§2(b)** — added the "watcher scope" note: the watcher also sources the Govee env
   (`:114-119`), force-enables the laser config (`:73-95`), **starts/stops the Stream
   Deck sidecar** (`:59-69`, `:300,315`), and opens the monitor Terminal; the bundle
   runner must state a disposition for each (the design previously ported only
   adopt/restart/backoff — a bundled run without `streamdeck_midi.py` fails the
   design's own §2 bar).
4. **§3.1** — folded AWR-123 **F1** (exFAT can't hold a symlink-load-bearing PyInstaller
   6 `.app` → ship `RBSS Bridge.dmg` on the exFAT stick, built with `hdiutil`) and
   **F9** (arm64-only, min-macOS decision, python.org build interpreter).
5. **§3.2** — re-grounded the one-process invariant: the bridge's own flock
   (`__main__.py:772-785`, refusal at `main()` `:1082-1084`) already enforces
   single-instance across any mix of source-run and bundled bridges (I verified this
   directly — it was AWR-123 F5's key fact). What breaks frozen is observability and
   control (`pgrep -f rb_ss_bridge_v2`, watcher `bridge_pids()` `:97-99`, menubar
   patterns `bridge_menubar.py:35-36`). Added requirements: name the bundled binary so
   argv contains `rb_ss_bridge_v2`; bundle-mode control = owned child pid + flock +
   status liveness; `NSRunningApplication` menubar dedupe; surface lock refusals; the
   dev-watcher coexistence note.
6. **§4 Temporary mode** — replaced run-from-stick with AWR-123 **F2**'s
   stage-to-internal-scratch model ("the stick is a key"): version-keyed
   `$TMPDIR/rbss-<version>/` staging, End Set explicit cleanup action, stick unmount as
   signal only, yank = non-event; folded **F8** (fixed `/tmp` paths outlive any scratch
   wipe — enumerated-delete or a later `RBSS_RUNTIME_DIR`), and restated the residual-
   trace claim honestly.
7. **§5** — added AWR-123 **F4** (permission cascade: Local Network +
   `NSLocalNetworkUsageDescription`, Input Monitoring for Stream Deck HID, Background
   Items notification, ad-hoc cdhash re-grant churn + the free Apple Development cert
   experiment) and **F7** (three IAC-coupled endpoints, port-map table requirement,
   virtual-ports-as-default, IAC as runbook fallback only); fixed the stale
   `streamdeck_midi.py:431` cite (`:654` at `8abccdf`); added the Rekordbox-MTC runbook
   line.
8. **§7 build order** — M2 verify updated to match the stage-to-scratch model (literal
   mid-run yank test; End Set wipe; crashed-scratch sweep).
9. **§6 risky bits** — added the PyInstaller×Python-3.14 build gate (PyInstaller is not
   installed locally; local runtime is 3.14, CI 3.11) and the "memory reads under an
   ad-hoc bundle on Brandon's OWN Mac" stop-rule (reader uses `task_for_pid` +
   `mach_vm_read_overwrite`, `rb_memory.py:60-72`; if bundle behavior differs from
   source-run, stop — the authorization mechanism stays in the separate reader spec).

## Registry rows I touched (`docs/status/active_work_registry.md`)

- **AWR-122**: "Unreviewed … authoring session owns finishing" → "reviewed + revised in
  place at `8abccdf` … M1 Codex spec path …". Adjust to your liking; the M1-spec path is
  the dangling reference noted above.
- **AWR-123**: "pending operator fold-in" → "P1 findings F1-F4 folded … after independent
  re-verification; F5-F12 are Codex-plan content".
- **AWR-121** row also changed in the same commit (gesture v2 — mine, ignore).

## Verification status of what I folded

- Every REPO claim I adopted from AWR-123 was independently re-verified at `8abccdf`
  before folding: the flock, menubar patterns/paths, fixed `/tmp` paths
  (`runtime_status.py:16-17`), hardcoded IAC literals (`soundswitch_midi_input.py:88`,
  `mtc_reader.py:30`), `pyproject.toml` dependency gaps, no
  `sys.executable`/`multiprocessing` in core.
- EXTERNAL claims (exFAT/symlinks, TCC/permission behavior, StartOnMount semantics,
  `PYINSTALLER_RESET_ENVIRONMENT`) were adopted at AWR-123's own confidence labels with
  its citations — I did not re-research them.

## What I did NOT do

- No Codex implementation spec (the design's "next step" remains unwritten).
- No code, config, build, or runtime changes anywhere in the launcher scope.
- No edits to `docs/plans/active/usb_bridge_launcher_fable_review.md` (AWR-123) or
  `docs/plans/active/cross_platform_portability_plan.md` (AWR-120).
- AWR-123's F5-F12 and Part 2 ideas are NOT folded into the design — deliberately left
  as Codex-plan/milestone content per its own P2/P3 severity labels.

## Conflict warning

Your session had `usb_bridge_launcher_fable_review.md` dirty in the working tree while I
committed; if you were also mid-edit on the DESIGN doc, diff your copy against `02250de`
before writing, or my folds may be silently overwritten by an auto-sync of your turn end.
