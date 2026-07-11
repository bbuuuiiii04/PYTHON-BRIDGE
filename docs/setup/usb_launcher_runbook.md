---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: a31bde9
last_verified_date: 2026-07-10
validation_scope: >
  USB bridge launcher runbook, M1 build + M2 native install/PURGE (AWR-186).
  M1 build/sign/DMG commands verified on the maintainer's Mac (PyInstaller
  6.21.0 × Python 3.14.6). M2 (make_stick.sh, native menubar install, config
  overrides, frozen state dir, menubar PURGE) is code + unit tests only —
  make_stick.sh has NOT been run against the stick and no M2 bundle has been
  built yet. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED — the operator
  walkthrough (parity table below) is the physical gate.
---

# USB Bridge Launcher — Runbook (M1 build · M2 install/PURGE)

What M1 delivers: a double-clickable macOS app (`RBSS Bridge.app`, shipped as
`RBSS Bridge.dmg`) that carries its own Python and the whole `rb_ss_bridge_v2`
package, so it runs the FULL bridge with no host Python. M1 proves the bundle
builds and its pieces dispatch; it does NOT install anything and does NOT prove
the bundled bridge lights the room identically to a source run — that is the
operator parity run at the end.

## Build environment (Task 0 — REVISED after the foreign-Mac failure)

**Do NOT build with Homebrew Python.** Homebrew's Python 3.14 is arm64-only and
was compiled targeting macOS 15, so its `libpython` hard-binds macOS-13 symbols
(`_mkfifoat`). A bundle built with it aborts at launch on any Mac older than the
build target — the original bundle died on macOS 12 with `Symbol not found:
_mkfifoat` before any bridge code ran — and can't run on Intel at all. Setting
`MACOSX_DEPLOYMENT_TARGET` at PyInstaller time does NOT help: it cannot relink a
prebuilt `libpython`. Only a low-target interpreter fixes it.

- **Interpreter:** the **python.org universal2** build of Python 3.11+ (install
  the "macOS 64-bit universal2 installer" `.pkg`). It targets macOS 10.13 and
  ships both arm64 + x86_64 slices, fixing the crash AND Intel support at once.
  `make_stick.sh` auto-selects it from
  `/Library/Frameworks/Python.framework/Versions/*/bin/python3` (target < 13,
  universal2); override with `RBSS_BUILD_PYTHON=/path/to/python3`. It refuses to
  build with a Homebrew/target-15 interpreter.
- **Minimum macOS supported by the fixed build:** ~**macOS 11 (Big Sur)** in
  practice (`MACOSX_DEPLOYMENT_TARGET=11.0`); the `libpython` floor is 10.13, but
  the real floor is the highest `minos` among the bundled wheels/dylibs. This
  comfortably clears the reported macOS 12 target.
- **Deps:** NO `--system-site-packages` (that pulled Homebrew's arm64/target-15
  wheels back in). `make_stick.sh` installs the rig fresh into a clean venv:
  ```bash
  <python.org python3> -m venv .build-venv-u2
  ./.build-venv-u2/bin/python -m pip install pyinstaller
  ./.build-venv-u2/bin/python -m pip install ".[bundle,analysis,spectral]"
  ```
  **Spectral analysis is REQUIRED, not optional.** It does NOT trade off against
  the macOS-12 fix — that fix is purely the interpreter's deployment target and is
  independent of the spectral deps. `numpy`/`scipy`/`librosa`→`numba`/`llvmlite`
  install fine on a stable python.org build; only the very newest Python (e.g.
  3.14) may lack a `numba` wheel yet, which is why `make_stick.sh` prefers a stable
  version (3.13/3.12) and **fails loudly** — never ships without spectral — if the
  chosen interpreter can't install it, telling you to point `RBSS_BUILD_PYTHON` at
  a python.org 3.12/3.13. On Apple Silicon the app is arm64 and runs on any arm64
  Mac ≥ the deployment floor with full spectral. Intel (x86_64) support is a
  SEPARATE concern that needs universal2 wheels for the C extensions — only pursue
  it if a target Mac is actually Intel (the `_mkfifoat` crash proved this one is
  Apple Silicon).
- **Gatekeeper/quarantine:** ad-hoc signing satisfies Apple-silicon's
  must-be-signed rule, and a plain USB/DMG copy applies no `com.apple.quarantine`,
  so the app launches without a notarization step. `make_stick.sh` runs
  `xattr -cr` on the built app as belt-and-suspenders.

## Build → ship: `make_stick.sh` (M2 — THE build path)

One command from the repo root, with the renamed stick mounted:
```bash
bash packaging/make_stick.sh /Volumes/<stick>
```
It runs the whole chain: PyInstaller build → `sign.sh` → DMG **built from a
staging dir so the DMG carries both `RBSS Bridge.app` and `RBSS_payload/`**
(the pre-warmed spectral cache from App Support + the home-parity files:
`govee.env`, `laser_director.json`, `led_look_director.json`,
`soundswitch_pack_player.json`, `laser_color_map.json` — secrets-on-stick is
operator-approved, AWR-186), then ships the DMG + the two stick `.command`
helpers into the stick's **`RBSS BRIDGE USB/` folder** (the operator's layout,
2026-07-09) and refreshes the folder's sibling `RBSS_payload/` so the interim
helpers and the native installer never drift apart (M2 review fix). It refuses
any target volume without `PIONEER/` (wrong stick), stages only under
`mktemp -d` (never the repo tree), skips absent payload files with a note, and
aborts naming the step if a source exists but is unreadable — including a
malformed/unreadable `soundswitch_pack_player.json` or a declared non-empty
`pack_path` that is not a readable directory (fail closed, so a stick never
ships claiming success with no show; an absent config or empty `pack_path`
stays backward-compatible no-pack). Summary line reports DMG size, payload file
count, stick free space.

### Manual reference (what make_stick.sh runs, M1 commands)

```bash
# 1. Build the .app (onedir, windowed). build/ and dist/ are gitignored.
./.build-venv-314/bin/pyinstaller packaging/rbss_launcher.spec \
    --noconfirm --distpath dist --workpath build
rm -rf build                                   # delete the intermediate (disk)

# 2. Sign (re-runnable): Apple Development identity if present, else ad-hoc.
bash packaging/sign.sh "dist/RBSS Bridge.app"

# 3. DMG for the exFAT stick (never a raw .app / Finder-zip on exFAT).
#    make_stick.sh points -srcfolder at its staging dir (app + RBSS_payload).
hdiutil create -volname "RBSS Bridge" -srcfolder "dist/RBSS Bridge.app" \
    -ov -format UDZO "dist/RBSS Bridge.dmg"
```
M1 reference sizes: `dist/RBSS Bridge.app` ~252 MB, app-only DMG ~111 MB (the
M2 DMG is larger — it carries the payload).

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
- **Sessions live in `/tmp` and vanish on reboot** — `/tmp/rbss-session-*.jsonl`
  is cleared by macOS across restarts, so re-record after a reboot. A durable
  canned demo session that rides the stick is M2 scope, not M1.
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

## Native install (M2 — the one-action flow, AWR-186)

On the guest Mac: plug the stick → double-click `RBSS Bridge.dmg` → launch the
app (right-click → Open the first time) → the menubar's PRIMARY item is
**"Install on this Mac…"** (it appears only when running from the DMG/
translocation with no manifest on that Mac). Confirm the NSAlert and it:

1. copies the app to `~/Applications/RBSS Bridge.app`;
2. installs `RBSS_payload/spectral_cache` (from inside the DMG) into App
   Support — pre-warmed analysis, full-strength lights from the first beat;
3. installs `RBSS_payload/home/*` into App Support — `govee.env` + the live
   configs, so the bridge **performs like the home Mac** (`usb_launcher`
   points each subsystem's env seam at those copies; an exported env wins);
4. writes the SAME file-level `install_manifest.txt` the interim commands use
   (app path + every installed file — the two purge paths stay interoperable);
5. relaunches from `~/Applications` (menubar only — the bridge NEVER starts by
   itself) and offers to eject the DMG.

A failed step is reported BY NAME; the DMG-run app stays fully usable and the
manifest lists only what actually landed. Learned stores (`local/state/*`)
live in App Support `state/` in frozen runs, so they persist and PURGE removes
them (source runs keep today's paths, byte-identical).

## Native PURGE (M2 — the operator's exact ask, AWR-186)

Installed copies (manifest present, not DMG-run) show **"Purge RBSS Bridge…"**.
Explicit **Purge** button + Cancel; the dialog states exactly what goes. On
confirm it: stops the owned bridge child by handle + flock (never
pkill/pattern), removes the manifest paths (allowlist: `~/Applications` + App
Support only, `..` rejected), then the whole `~/Library/Application Support/
RBSS Bridge/` dir (configs, secrets, caches, learned state), then
`~/Library/Logs/rb_ss_bridge/`, reports the honest result (removed count,
leftovers by name), moves its own bundle to Trash and quits. Never touches the
stick, the DMG, or anything outside those three roots. Honest residue: macOS
System Settings permission rows stay (inert) — and the stick itself still
carries the secrets it shipped with.

## Deliberately NOT built (say so, don't assume)

- **LaunchAgent / `StartOnMount` / auto-start** — M3. Launch-on-click stands
  (operator default). `launch_agent_plist.py` can *render* a plist; nothing
  installs/loads it.
- **Foreign-Mac** memory-grant/permission cascade — M4; the walkthrough below
  is the gate.
- **XDJ-RX3 stick reading (R5)** — settled IMPOSSIBLE (AWR-167).
- **Dev-only watcher features** not carried into the bundle: the
  `RBSS_BRIDGE_TRUTH=1` Art-Net truth-check and the `WATCHER_NO_LOOP` test hook.

### Supported target & known limitations (round-2 guest-Mac review)

- **arm64 / Apple Silicon only.** The produced `.app` is thin arm64 (pip pulls
  arm64 wheels on Apple Silicon; the spec sets no `target_arch`), floored at macOS
  11 (`LSMinimumSystemVersion`). It does NOT run on Intel; `make_stick.sh` asserts
  the built arch with `lipo` and **fails closed** if arm64 is missing. Real Intel
  support would need `target_arch='universal2'` + universal2 wheels for every C
  extension (numba/llvmlite have none for the newest Python) — not pursued.
- **`mutagen` is a bundle dependency** (SoundSwitch track-id reads). It's in the
  `[bundle]` extra + spec `hiddenimports`; the maintainer's Homebrew Python already
  has it, but the clean build venv needs it or scripted/autoloop selection silently
  dies on the guest.
- **Read-authorization is surfaced, not solved.** If the guest blocks `task_for_pid`
  (KERN_FAILURE) or runs an unsupported Rekordbox build, the menubar's BRIDGE row now
  shows a named reason (`RB reads blocked` / `RB version unsupported`) instead of
  silent no-lights. The bridge still can't read in that case — the reason is the
  diagnostic, not a fix.
- **KNOWN LIMITATION — Local Network (TCC) denial is not detected.** macOS has no
  Python-visible API for the Local Network permission state, so if the guest denies
  it, Govee/SoundSwitch discovery just finds nothing. There is no clean signal to
  surface; if the rig is silent and reads are OK, check System Settings → Privacy →
  Local Network for "RBSS Bridge".

## Stick helpers (AWR-122 interim — still ride the stick as the no-menubar fallback)

`packaging/stick/install.command` + `purge.command` sit next to the DMG
(make_stick.sh copies them). The NATIVE menubar install/PURGE above is the
primary flow; these remain for a Mac where the app won't launch:

- **install.command**: mounts the DMG, copies the app to `~/Applications`,
  installs stick-side `RBSS_payload/spectral_cache` if present, records every
  path in the same `install_manifest.txt`. App + pre-warm only — the native
  installer is what carries configs/secrets.
- **purge.command**: requires typing `PURGE`, removes exactly the manifest
  paths (same allowlist discipline), prunes emptied dirs. Narrower than the
  native PURGE: App Support extras and run logs remain.
- Tests: `tests/test_stick_commands.py` (purge deletion scoping);
  `tests/test_make_stick.py` (builder staging layout, existence-gating,
  fail-closed unreadable — incl. malformed pack config + non-readable non-empty
  `pack_path` — PIONEER refusal); `tests/test_install_controller.py`
  (native install/purge pure seams: detection, manifest exactness, allowlist +
  `..` + three-root order, frozen state-dir resolution).

## Operator parity run (Task 7 — the gate, do on a TEST session, never a live show)

Quit the dev watcher, mount the DMG, launch the app, and check each subsystem
against a watcher run. Nothing here is "working" until these pass.

| Check | Expected | Pass? |
|---|---|---|
| `make_stick.sh <mount>` run | builds, stages, ships; summary prints DMG size / payload count / free space | ☐ |
| Native install (guest Mac/user) | DMG-run menubar shows "Install on this Mac…"; confirm → app in `~/Applications`, payload + configs + `govee.env` in App Support, manifest superset written, relaunch + eject offered | ☐ |
| Installed run = home parity | bridge behaves like the home Mac (Govee cloud up, laser/LED configs live, laser colors mapped, pre-warm hits) | ☐ |
| Learned stores persist (frozen) | after a run, `~/Library/Application Support/RBSS Bridge/state/` gains/updates the identity + laser-solo stores | ☐ |
| Native PURGE | "Purge RBSS Bridge…" on the installed copy: bridge child stops, all three roots removed, app in Trash, honest residue note | ☐ |
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
