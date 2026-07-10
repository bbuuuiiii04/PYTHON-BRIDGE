---
doc_status: current
truth_level: operator-runbook-distillation
last_verified_commit: 33c3bb9
last_verified_date: 2026-07-09
validation_scope: >
  One-page operator card for the Saturday foreign-Mac test (friend's Apple Silicon
  laptop + friend's XDJ + the MINK stick). Distilled from
  docs/setup/usb_launcher_runbook.md at HEAD; stick contents verified 2026-07-09
  21:33. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED — Saturday IS the test.
---

# Saturday card — bridge on a friend's Mac (MINK stick)

## Before leaving home
- [ ] Friend confirmed: **Rekordbox 7.2.11** (Rekordbox → About) — wrong version =
      lights stay idle; there is no workaround on site.
- [ ] Friend's laptop is **Apple Silicon** (M-series). Intel = app won't launch.
- [ ] MINK carries a `RBSS BRIDGE USB` folder holding: `RBSS Bridge.dmg`, `install.command`, `purge.command`,
      `RBSS_payload/` (the pre-warm — if missing, everything still works, tracks
      just analyze ~15s on first play).
- [ ] Note his exact XDJ model (decides whether stick-in-deck can ever work later).

## Setup at the venue (10 minutes)
1. **MINK goes in the LAPTOP's USB port** — never the XDJ's slot (the XDJ can't
   tell the laptop what it's playing; that's hardware, not settings).
2. XDJ → laptop over its USB cable; Rekordbox in **performance mode** (laptop is
   the player, the XDJ is the hands).
3. Double-click **`install.command`** on MINK (blocked? right-click → Open). It
   installs the app + the pre-warmed analysis and records everything it created.
4. Launch **RBSS Bridge** from `~/Applications` — **right-click → Open** the first
   time — and approve the one-time permission prompts.
5. Open Rekordbox, load a track from the MINK device, play.

## What you should see
- Menubar icon present; with a track playing, lights react on beat.
- Pre-warmed tracks are full-strength from the first beat. Anything not pre-warmed
  runs beat-synced immediately and gets track-smart ~15s in. Second plays: instant.
- **Test the Lights** (no decks needed): play something with the bridge running →
  menubar **Record Session** → quit Rekordbox → **Test the Lights**. It REFUSES
  while Rekordbox is open — that is deliberate, not a bug.

## If lights stay idle while Rekordbox 7.2.11 plays
**STOP — do not troubleshoot on site.** This is the one genuinely untested thing
(foreign-Mac memory reads). Note the wall-clock time and what you did; report back.

## Rules for the set
- MINK stays plugged in the whole time (the music lives on it).
- One bridge only: don't launch it twice; it refuses anyway.

## Leaving / removing everything
Quit the bridge (menubar). To remove it from his Mac: double-click
**`purge.command`**, type `PURGE`, Return. It deletes exactly what install created.
What remains: inert permission entries in System Settings and log files — say the
word and they're gone by hand; the native one-button PURGE ships in the next build.
