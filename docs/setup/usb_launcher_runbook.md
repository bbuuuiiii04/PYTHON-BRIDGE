---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: b87745a
last_verified_date: 2026-07-09
validation_scope: >
  USB bridge launcher Milestone-1 runbook. Build/sign/DMG commands verified on the
  maintainer's Mac (PyInstaller 6.21.0 × Python 3.14.6): the .app builds, ad-hoc
  signs, and a DMG is produced. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED —
  whether the bundled bridge drives the real rig identically to a source run is the
  operator's §2 parity run (below), not proven here.
---

# USB Bridge Launcher — M1 Runbook

What M1 delivers: a double-clickable macOS app (`RBSS Bridge.app`, shipped as
`RBSS Bridge.dmg`) that carries its own Python and the whole `rb_ss_bridge_v2`
package, so it runs the FULL bridge with no host Python. M1 proves the bundle
builds and its pieces dispatch; it does NOT install anything and does NOT prove
the bundled bridge lights the room identically to a source run — that is the
operator parity run at the end.

## Build environment (Task 0 — decided)

- **Interpreter:** Python 3.14.6 (Homebrew, the current runtime). No python.org
  fallback needed — PyInstaller supports it.
- **PyInstaller:** 6.21.0, installed in a disposable, gitignored, system-site-packages
  venv so the bridge's deps are visible without reinstalling them:
  ```bash
  python3 -m venv --system-site-packages .build-venv-314
  ./.build-venv-314/bin/python -m pip install pyinstaller
  ```
- Test suite passes on this interpreter at the M1 baseline (known 5 pre-existing reds).

## Build → sign → DMG

Run from the repo root:
```bash
# 1. Build the .app (onedir, windowed). build/ and dist/ are gitignored.
./.build-venv-314/bin/pyinstaller packaging/rbss_launcher.spec \
    --noconfirm --distpath dist --workpath build
rm -rf build                                   # delete the intermediate (disk)

# 2. Sign (re-runnable): Apple Development identity if present, else ad-hoc.
bash packaging/sign.sh "dist/RBSS Bridge.app"

# 3. DMG for the exFAT stick (never a raw .app / Finder-zip on exFAT).
hdiutil create -volname "RBSS Bridge" -srcfolder "dist/RBSS Bridge.app" \
    -ov -format UDZO "dist/RBSS Bridge.dmg"
```
Result: `dist/RBSS Bridge.app` (~252 MB) and `dist/RBSS Bridge.dmg` (~111 MB).

### Signing status (A1/A8)

No Apple Development certificate exists on the build machine (Xcode needs ~40 GB;
not minted on the build night), so the app is **ad-hoc signed** (`codesign -s -`),
which satisfies Apple-silicon's must-be-signed-to-run rule for local use.
`packaging/sign.sh` is re-runnable: once an Apple Development cert exists, run it
again and it upgrades the signature to that identity (stable TCC identity, idea 8)
**without rebuilding**.

## What double-clicking does now (frozen dispatch)

One binary, dispatched by its first flag (`usb_launcher.py`):

| Invocation | Does |
|---|---|
| (no args) | the PyObjC menubar app |
| `--run-bridge` | the full bridge, in-process, with the shared launch profile |
| `--run-streamdeck` | the Stream Deck MIDI controller |
| `--run-frame-engine --fd N` | the headless Govee frame-engine child |
| `--replay-session <file>` | Test the Lights (below) |

**Frozen menubar lifecycle (Task 3 choice):** launch-on-click, no auto-restart.
The menubar owns the bridge as its OWN child process (spawns `--run-bridge`, keeps
the handle) and starts/stops it by that handle + the flock — never by pkill/pattern
(a frozen binary's argv doesn't match the source-run regexes). M2 finalizes the
lifecycle (adopt/backoff, End Set).

## Test the Lights (replay)

Menubar → **Test the Lights…** replays the newest recorded session through the whole
rig, so you can watch the lights respond with Rekordbox closed.

- **Record a session first:** menubar → **Record Session** during a real set. It
  writes `/tmp/rbss-session-<stamp>.jsonl`. Test the Lights plays the newest one.
- **Live-safety (fail closed):** replay refuses to start while **Rekordbox is
  running** (it must not run against live decks) and refuses if **no session has
  been recorded yet** — both show a plain message, neither starts the bridge.
- Under the hood: the bridge runs normally but its readers are inert (no Rekordbox),
  and a replay pump feeds the recorded events/positions/BPM onto the live
  StateManager, re-stamped to the live clock so they aren't dropped as stale.
- **Not yet proven live:** that a recorded session actually drives the rig end-to-end
  is part of the parity run below — no recorded session existed on the build night.

## Coexistence warning (the one gotcha)

Quit the dev watcher/menubar before launching the bundle. The bridge takes an
exclusive flock (`/tmp/rb_ss_bridge_v2.lock`); a second bridge of ANY form refuses
to start. If the dev watcher is running, a bundled launch is correctly refused, but
the watcher will log adopt/start churn. One bridge at a time.

## Deliberately NOT built in M1 (say so, don't assume)

- **Install modes** — temporary "stage to scratch" and permanent (`~/Applications`
  copy + LaunchAgent + `StartOnMount` + Uninstall) are M2/M3. `launch_agent_plist.py`
  can *render* an Interactive LaunchAgent plist, but nothing installs/loads it.
- **Foreign-Mac** anything (the memory grant, permission cascade) — M4.
- **Frame-engine frozen re-exec fix** — the client-side spawn
  (`govee_frame_engine_client.py`) still uses the source-run `sys.executable -m …`
  form; under the frozen binary that spawn needs a `--run-frame-engine` re-exec. The
  launcher side is ready; the fenced client edit is gated on F4 (pending).
- **Dev-only watcher features** not carried into the bundle: the
  `RBSS_BRIDGE_TRUTH=1` Art-Net truth-check and the `WATCHER_NO_LOOP` test hook.

## Operator parity run (Task 7 — the gate, do on a TEST session, never a live show)

Quit the dev watcher, mount the DMG, launch the app, and check each subsystem
against a watcher run. Nothing here is "working" until these pass.

| Check | Expected | Pass? |
|---|---|---|
| App launches, menubar appears | menubar icon present | ☐ |
| One-bridge count | anchored `…rb_ss_bridge_v2$` count reads ONE bridge (+ frame-engine child = two processes total) | ☐ |
| SoundSwitch rotation | autoloops rotate as in a watcher run | ☐ |
| MIDI look-selection | look changes fire over IAC/virtual port | ☐ |
| Laser output | laser scenes fire | ☐ |
| LED / Govee frames | realtime frames render (frame-engine child alive) | ☐ |
| Stream Deck | pads live | ☐ |
| **Memory reads** | deck state reads match a source-run bridge | ☐ |
| Test the Lights | recorded session drives the rig; refuses while Rekordbox open | ☐ |

**Memory-read STOP rule:** if the bundled bridge's memory reads behave differently
from a source-run bridge, STOP and report — do not improvise entitlements or new
authorization mechanics (that is the separate reader spec's scope).

Evidence class until this table is green: **SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED**.
