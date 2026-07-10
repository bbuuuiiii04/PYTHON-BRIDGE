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
| R1 | One-action install: open DMG → installs to the Mac (app copy + payload) → menubar ready | M2 build item (design doc §3.3 install modes — designed, not built) |
| R2 | Cache-copy automated: the spectral pre-warm folder (and payload) installs itself — no manual folder copy | M2 build item; payload rides the stick next to the DMG (stick-builder step) |
| R3 | "Performs JUST LIKE my current macbook": live configs + govee.env ride the stick and install | M2 build item; **secrets-on-stick decision inferred YES from his words — one-line veto open** (purge must remove them; see R6) |
| R4 | Survives unplug: bridge keeps running/reinstalls not needed after stick removal | Follows from R1 (install-to-disk). Note: TRACKS still need the stick present — rekordbox plays audio from it |
| R5 | Read USB-exported tracks while the stick is in the **XDJ-RX3** and the bridge stays on the MacBook | **IMPOSSIBLE — hardware, settled 2026-07-09 ~03:00 (P0 STOP, AWR-167, dual-confirmed: beat-link README + official AlphaTheta).** RX-family emits no Pro DJ Link: standalone stick playback broadcasts nothing the laptop can hear, on any cable. Working equivalent, same gear: performance mode with the stick in the LAPTOP port (the XDJ stays the hands). Revive trigger stands for link-capable gear (XZ / 1000-family / CDJ) |
| R6 | PURGE: menubar action, explicit confirmation → bridge fully removes itself (app copy, LaunchAgent if any, App Support incl. cache/configs/secrets, logs) | M2 build item. Honest residue: macOS TCC permission rows can't be self-deleted by the app — everything else goes |

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
