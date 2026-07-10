---
doc_status: current
truth_level: operator-directive-capture
last_verified_commit: 7b8555f
last_verified_date: 2026-07-09
validation_scope: >
  Verbatim capture + decomposition of the operator's M2 product directive for the
  USB bridge launcher (2026-07-09 ~19:25, attended usb lane). Requirements only —
  nothing here authorizes code; routing/sequencing is the executive's (M2 build
  requires the fresh executive gate per the M1 close-out ruling). One requirement
  (R5) is recorded as hardware-impossible on RX-family with the settled evidence.
---

# USB launcher M2 — operator directive (2026-07-09 evening)

## Operator's words (verbatim)

> "I'll rename the stick, and also the step involving copying the folder should be
> automated. It should be extremely easy to plug in usb into macbook, launch dmg
> and installs, and then the bridge is ready and performs JUST LIKE on my current
> macbook. It should also survive being unplugged, and be able to read usb exported
> tracks from the usb that is then plugged into the XDJ RX3 WHILE the bridge stays
> on the macbook. The bridge will only eliminate itself from the macbook once my
> friend clicks on the menu bar launcher and hit's PURGE with an explicit
> confirmation button. That is how it should be."

## Decomposition

| # | Requirement (his words → engineering) | Status |
|---|---|---|
| R1 | One-action install: open DMG → installs to the Mac (app copy + payload) → menubar ready | **IMPLEMENTED 2026-07-10 (AWR-186 M2 build: `install_controller.py` + menubar "Install on this Mac…"; software-tested, walkthrough pending)** |
| R2 | Cache-copy automated: the spectral pre-warm folder (and payload) installs itself — no manual folder copy | **IMPLEMENTED 2026-07-10 (payload rides INSIDE the DMG via `packaging/make_stick.sh`; installer copies it file-level; software-tested)** |
| R3 | "Performs JUST LIKE my current macbook": live configs + govee.env ride the stick and install | **IMPLEMENTED 2026-07-10 (secrets-on-stick operator-APPROVED ~22:40; installed App Support copies win via existing env seams + new `RBSS_LASER_COLOR_MAP_CONFIG`; frozen `local/state` → App Support `state/`; software-tested)** |
| R4 | Survives unplug: bridge keeps running/reinstalls not needed after stick removal | **IMPLEMENTED via R1 (install-to-disk; DMG eject offered post-install).** Note stands: TRACKS still need the stick present — rekordbox plays audio from it |
| R5 | Read USB-exported tracks while the stick is in the **XDJ-RX3** and the bridge stays on the MacBook | **IMPOSSIBLE — hardware, settled 2026-07-09 ~03:00 (P0 STOP, AWR-167, dual-confirmed: beat-link README + official AlphaTheta).** RX-family emits no Pro DJ Link: standalone stick playback broadcasts nothing the laptop can hear, on any cable. Working equivalent, same gear: performance mode with the stick in the LAPTOP port (the XDJ stays the hands). Revive trigger stands for link-capable gear (XZ / 1000-family / CDJ) |
| R6 | PURGE: menubar action, explicit confirmation → bridge fully removes itself (app copy, LaunchAgent if any, App Support incl. cache/configs/secrets, logs) | **IMPLEMENTED 2026-07-10 (menubar "Purge RBSS Bridge…": explicit Purge confirm, stop-child-first, manifest allowlist + whole App Support + logs, own bundle to Trash; software-tested).** Honest residue stands: macOS TCC permission rows can't be self-deleted — everything else goes. No LaunchAgent exists (M3 not built) |

*(All "IMPLEMENTED" rows are SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED —
code + unit tests at HEAD; no M2 bundle has been built or run yet. The
operator walkthrough in the runbook parity table is the physical gate.)*

## Saturday bridge (proposed, small, this lane)

M2 proper cannot be built + gated before Saturday (quota window + live lanes). Proposed
interim so Saturday already FEELS one-action: stick-side `install.command` /
`purge.command` helpers next to the DMG (double-click → copy app to ~/Applications +
install spectral pre-warm folder + open app; purge = confirmed reverse). New stick-side
files only; zero bridge-code edits; same risk class as the AWR-183 sweep tool.
Routed to the executive with this capture.

## Operational note (time-sensitive tonight)

Operator renames the stick → the after-20:00 stick sweep MUST run against the NEW
volume name (`/Volumes/<NewName>`), and Saturday's mount-name match is against that
name. Rename BEFORE the sweep fires or the pre-warm keys all miss.

## Operator decisions

1. Secrets/configs ride the stick + install to the friend's Mac — **ANSWERED YES
   (operator, in-chat 2026-07-09 ~22:40: "I approve of secrets on stick")**. Decision
   closed; the Part A security line stands as accepted risk.
2. Auto-start on login vs launch-on-click — **default launch-on-click** (same as home
   today; simpler purge); veto still open if he wants boot-time start.

**Same message, broader ruling:** the operator approved the full CANNOT-DO-YET build
list (native install/PURGE = AWR-186, home-parity payload, AWR-165 move-invariance)
EXCEPT items requiring physical validation — the foreign-Mac memory-read test and the
parity walkthrough remain tests/gates, not approvals, correctly.
