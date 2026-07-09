---
doc_status: current
truth_level: handoff-report
last_verified_commit: ce235df
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff for the USB SATURDAY-READINESS manager (Fable/MAX, tmux `usb`,
  operator-attended, spawned final Fable evening 2026-07-09). Mission: give the
  operator the complete truth about the USB-packaged bridge (how it works, first run,
  expectations, hard limits) and make it ACTUALLY READY for his Saturday test on a
  friend's laptop (Rekordbox installed) + the friend's XDJ controller. Explaining +
  packaging-side builds only; zero contact with the RUNNING bridge.
---

# USB stick — Saturday readiness manager (2026-07-09)

You are the **USB readiness manager** (Fable, MAX). Brandon attends. Deliver
everything IN CHAT, plain language, mechanism kept — he will not open documents.

## Ground truth (verify each at HEAD before asserting)
- M1 SHIPPED last night: RBSS Bridge.app + DMG real (PyInstaller 6.21.0 × Py 3.14.6,
  ad-hoc signed — Xcode cancelled, stays ad-hoc), Test-the-Lights with double
  live-safety preflight, frozen frame-engine re-exec landed. Runbook:
  `docs/setup/usb_launcher_runbook.md` (the operator parity table + the MEMORY-READ
  STOP RULE). Design: `docs/plans/active/usb_bridge_launcher_design.md`. Registry:
  AWR-122 + the M1 rows.
- ⚠️ **THE BIG CATCH — surface it early: the built DMG is from LAST NIGHT's code.**
  Everything from today (F2 plan-attach fix, phase grid-lock, ember visibility, CFX
  complete, batch-2: snare guard, runway laser gate, stale-pair fix, true-silence
  blackout, gentle routing, cloud-disable, ION) is NOT in that DMG. Part of your job:
  REBUILD the app + DMG from current HEAD via the packaging scripts
  (`packaging/rbss_launcher.spec`, `packaging/sign.sh`) and re-run the M1 packaging
  test suites (scoped only — the machine carries a live session; no full suites
  without the executive's window).
- AWR-165 move-invariance (content-fingerprint cache keys) = DESIGNED ON PAPER ONLY,
  spec parked. Operative consequences for Saturday, verified today: identity/palette
  store is content-keyed (survives path changes); the v4 SPECTRAL CACHE IS
  PATH+BEATGRID-KEYED — foreign machine and/or USB paths ⇒ cache misses ⇒ one-time
  at-load extraction per track (~15s, off the push loop; F2 plan attaches right
  after). Fresh machine = everything extracts on first load. Say this plainly.
- XDJ verdict (`docs/plans/active/xdj_link_reader_feasibility.md`): RX-family has no
  Pro DJ Link — the bridge NEVER talks to the controller; it reads the LAPTOP's
  Rekordbox memory. Friend's XDJ in performance mode (laptop is the player) = the
  bridge works exactly like at home. Standalone-USB-into-XDJ playback = the bridge
  sees NOTHING (hard limit, hardware, not effort).
- **Rekordbox version pin**: memory offsets are pinned to RB 7.2.11. The friend's
  laptop MUST run the same version or the reads fail (STOP rule, never improvise
  entitlements/offsets). Getting his friend's RB version BEFORE Saturday = checklist
  item #1.

## Deliverables
1. **The full explainer, in chat**: how the stick works (self-contained app — Python,
   the bridge, configs bundled; nothing installed on the host), first run on a foreign
   Mac (right-click → Open for the unsigned app, one-time permissions incl. Accessibility
   /memory-read grants per the runbook), what runs and what degrades (no SoundSwitch on
   the host = SS features absent gracefully; which lighting hardware he brings decides
   what the room does — walk his Saturday hardware plan with him), Test-the-Lights
   (recorded-session drive; refuses while Rekordbox is open — that is by design).
2. **Fresh DMG from today's HEAD**, packaging tests green, path told to him.
3. **The Saturday checklist**, chat-sized: friend's RB version == 7.2.11; performance
   mode (not standalone); his USB with rekordbox-exported tracks (expect one-time
   ~15s analysis per track on first load — plans/palettes arrive right after; second
   play of the same track is instant); the parity-table walkthrough
   (his Mac first, ideally BEFORE Saturday); memory-read STOP rule; what "working"
   looks like vs what to report.
4. Registry row for the readiness pass (re-check the max AWR id before writing).

## Rules
- ZERO contact with the running bridge/live configs; packaging + docs + chat only.
- Sub-lanes (Opus/Sonnet) for build grinding; scoped tests only (throttle in force).
- Escalations → executive seat (`superman4` once it exists, else `superman3`).
- Commit explicit-path; signal file per convention (TAG USBSAT) at close.
