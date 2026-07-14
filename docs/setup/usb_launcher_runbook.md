---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 81f1b15
last_verified_date: 2026-07-13
validation_scope: >
  Current USB builder, frozen launcher, native install/purge, target
  Rekordbox patch, and software tests. The patch adds only target
  get-task-allow while preserving existing entitlements. A valid menu verdict
  additionally requires deep+strict signature verification. Target GTA is the expected
  TimecodeLink-style access mechanism. A positive entitlement proves the
  Rekordbox target patch only — not a live attach. Stock Apple-Silicon
  foreign-Mac attach after successful patch + deep verify + GTA=true +
  relaunch is live-unvalidated / unknown (not confirmed unsupported; not a
  confirmed caller-authorization blocker). Earlier foreign-Mac and RB7216
  attempts never reached that clean pre-attach state. Rekordbox patch signing
  is one root-bundle ad-hoc codesign (no --deep, no nested re-sign) under one
  native macOS authorization (not osascript; no full Rekordbox backup by
  operator request). The native privileged payload is passed in argv and its
  entitlement plist is created root-owned, closing the password-prompt temp-file
  race. Local `/Applications` RB 7.2.16 apply passed deep+strict
  verification and GTA inspection; a signed frozen RBSS probe also made a
  native-authorized inert write/remove in the Rekordbox bundle. Frozen Info.plist declares
  NSAppBundlesUsageDescription for App Management; frozen confirmation/result
  dialogs are native AppKit and the admin escalation stays inside RBSS Bridge.
  This proves the local patch mechanism, not a physical friend-Mac patch or live
  attach. A dormant Accessibility MEASUREMENT probe is
  implemented/software-tested and not executed (not a reader; no menu item;
  no runtime wiring). The separate RB7216 Patch Rekordbox menubar action sits
  in the maintenance block with Export/Rebuild (valid target-patch state only;
  always visible; Export/Rebuild source-only). make_stick stamps GENERATION
  into Info.plist (fallback 0.0.1). No install.command/purge.command helpers.
  SOFTWARE-VALIDATED COMPONENTS ONLY / STOCK FOREIGN-MAC ATTACH
  LIVE-UNVALIDATED / UNKNOWN.
---

# USB Bridge Launcher — Runbook (M1 build · M2 install/PURGE)

> **Pause before another foreign-Mac show test (AWR-222 honesty, 2026-07-13).**
> Packaging can ship, but stock Apple-Silicon foreign-Mac attach after a
> successful patch + deep verify + GTA=true + relaunch is still
> **live-unvalidated / unknown** — not confirmed unsupported. Target
> `get-task-allow` matches the TimecodeLink model; a positive check proves the
> Rekordbox patch only, not a live attach. Earlier foreign-Mac packaging
> failures and the RB7216 apply (failed on `libssl.3.dylib`, GTA absent) never
> reached that clean pre-attach state, so they cannot prove caller denial.
> Do not weaken SIP on a guest Mac. The next decisive gate is that ordered
> stock-SIP live run; only a `task_for_pid` denial after every prior step
> passes may be classified as caller attach denial.

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
It runs the whole chain: PyInstaller build → stamp `GENERATION` into the app's
Info.plist → `sign.sh` → DMG **built from a staging dir so the DMG carries
`RBSS Bridge.app` plus an embedded `RBSS_payload/`**
(the pre-warmed spectral cache from App Support + the home-parity files:
`govee.env`, `laser_director.json`, `led_look_director.json`,
`soundswitch_pack_player.json`, `laser_color_map.json` — secrets-on-stick is
operator-approved, AWR-186), then ships **only** `RBSS Bridge.dmg` (+ stick
`lighting_sidecar/` when the exporter runs). There are **no** `install.command` /
`purge.command` helpers — native in-app Install/Update/Retry and Purge are the
only install/removal path (AWR-226). It refuses
any target volume without `PIONEER/` (wrong stick), stages only under
`mktemp -d` (never the repo tree), skips absent payload files with a note, and
aborts naming the step if a source exists but is unreadable — including a
malformed/unreadable `soundswitch_pack_player.json` or a declared non-empty
`pack_path` that is not a readable directory (fail closed, so a stick never
ships claiming success with no show; an absent config or empty `pack_path`
stays backward-compatible no-pack). Summary line reports DMG size, payload file
count, stick free space.

There is no supported manual build recipe. Use `make_stick.sh`; it owns the
low-target build environment and the app-plus-payload DMG layout. The retired
`.build-venv-314`/app-only commands can recreate the macOS-12 launch crash or
ship a DMG without its payload.

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
| `--probe-rekordbox-accessibility` | dormant Rekordbox Accessibility MEASUREMENT probe (AWR-222); never starts the bridge; not a reader; the probe itself adds no menu item and no runtime wiring; software-tested only, not executed in the implementation round |

**AWR-222 probe (measurement only).** First live run requires explicit operator
approval and a rebuilt/installed app that includes the probe. Do not treat this
mode as supported, operational, validated, or a replacement reader. The dormant
AX measurement probe itself adds no menu item and no runtime wiring. The separate
RB7216 **Patch Rekordbox** action sits in the maintenance block with
Export/Rebuild (always visible in both editions; Export/Rebuild source-only); it
  targets only the Rekordbox target. Positive patch state ≠ live attach
proof; stock foreign-Mac attach after clean patch+verify+GTA+relaunch remains
live-unvalidated / unknown.

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

## Before a show: using somebody else's Rekordbox USB on this Mac

Do this in Rekordbox before starting the bridge:

1. Import the guest tracks into this Mac's Rekordbox collection.
2. Select those imported tracks and finish Rekordbox analysis. Do not stop at
   the copy/import step.
3. Leave the guest USB mounted while playing it. Its read-only
   `PIONEER/rekordbox/export.pdb` supplies the title/artist/duration identity;
   the local analysis supplies phrases and the local lighting identity.
4. Watch the bridge log on the first guest-track load. `usb-pdb-match` means
   both identity checks agreed. The bridge never writes to the guest USB.

If it stays unresolved, the log tells you why:

- `usb-crossanalysis-unconfirmed`: the stick tags could not be read; keep the
  track unresolved rather than risk the wrong song.
- `usb-pdb-miss`: the stick's exact title/artist/duration did not find a local
  import; import the track, then try again.
- `usb-pdb-ambiguous`: two or more local copies have the same identifying
  tags; remove/retag the duplicate instead of asking the bridge to guess.
- `usb-pdb-conflict`: the tags matched but BPM/duration did not; verify that
  the imported local file is the same recording/version.
- `imported-not-analyzed`: the local copy exists but its ANLZ is absent or
  unreadable; finish analysis in Rekordbox.

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
- **Foreign-Mac live Rekordbox reads** — blocked by AWR-222. The existing target
  patch is diagnostics/setup plumbing, not a working stock-macOS authorization
  mechanism. The next gate is an approved replacement-reader feasibility pass,
  not another physical retry of this package.
- **XDJ-RX3 stick reading (R5)** — settled IMPOSSIBLE (AWR-167).
- **Dev-only watcher features** not carried into the bundle: the
  `RBSS_BRIDGE_TRUTH=1` Art-Net truth-check and the `WATCHER_NO_LOOP` test hook.

### Supported target & known limitations (round-2 guest-Mac review)

- **arm64 / Apple Silicon only.** The produced `.app` is thin arm64 (pip pulls
  arm64 wheels on Apple Silicon; the spec sets no `target_arch`), floored at macOS
  12.3 (`LSMinimumSystemVersion`). It does NOT run on Intel; `make_stick.sh` asserts
  the built arch with `lipo` and **fails closed** if arm64 is missing. Real Intel
  support would need `target_arch='universal2'` + universal2 wheels for every C
  extension (numba/llvmlite have none for the newest Python) — not pursued.
- **`mutagen` is a bundle dependency** (SoundSwitch track-id reads). It's in the
  `[bundle]` extra + spec `hiddenimports`; the maintainer's Homebrew Python already
  has it, but the clean build venv needs it or scripted/autoloop selection silently
  dies on the guest.
- **Target patch is not yet a proven stock-Mac attach (AWR-222).** Target
  `get-task-allow` is the expected TimecodeLink-style access mechanism. The
  bridge bundle is still ad-hoc signed without caller debugger entitlement;
  that fact alone does **not** prove stock attach is impossible. A positive
  menubar/target entitlement check proves the Rekordbox patch only — not a
  live `task_for_pid` attach. Stock Apple-Silicon foreign-Mac attach after
  successful patch + deep verify + GTA=true + relaunch remains
  live-unvalidated / unknown. Earlier failed runs never reached that state.
  The menubar may surface `RB reads blocked`, but that is not by itself proof
  of caller denial after a clean GTA path. `unsupported_version` and transient
  `attach_failed` are not standing menubar reasons today; inspect the bridge log.
- **KNOWN LIMITATION — Local Network (TCC) denial is not detected.** macOS has no
  Python-visible API for the Local Network permission state, so if the guest denies
  it, Govee/SoundSwitch discovery just finds nothing. There is no clean signal to
  surface; if the rig is silent and reads are OK, check System Settings → Privacy →
  Local Network for "RBSS Bridge".
- **Patch Rekordbox path (AWR-223):** it signs Rekordbox with **one**
  root-bundle ad-hoc `codesign` (no `--deep`, no nested re-sign), under the
  RBSS app's native macOS authorization. It adds only `get-task-allow`,
  preserves the target's existing entitlements, passes the privileged script
  in argv, and creates the signing entitlement plist root-owned under
  `/var/tmp`. It does **not** create a full Rekordbox
  backup, by the operator's instruction. A failure therefore never claims that
  Rekordbox was restored; reinstall/update Rekordbox if its later signature
  check fails. Local `/Applications` RB 7.2.16 patch passed deep+strict + GTA
  verification, and a signed frozen RBSS probe completed a native-authorized
  inert write/remove in the protected bundle. Frozen `Info.plist` declares
  `NSAppBundlesUsageDescription`. If macOS blocks the action, enable **RBSS
  Bridge** in App Management and retry; do not grant Terminal or osascript for
  this feature. The frozen Patch Rekordbox consent/result modal and admin prompt
  are native. This is local patch-path evidence only: a friend-Mac physical
  patch and stock-SIP attach remain unvalidated.
  AWR-224/229 are selecting and verifying the complete macOS-12 wheel set.
  AWR-225's partial-install retry is implemented. These remain software-only
  until a clean foreign-Mac run.

## One installation path

The stick ships no `.command` installers and no duplicate payload. Open
`RBSS Bridge.dmg`, open the app, and use its single native action:

- **Install on This Mac…** on a fresh Mac;
- **Update This Mac…** when an installed copy already exists;
- **Retry Installation…** after an interrupted copy.

The installed menubar owns **Purge RBSS Bridge…**. Older manifests created by
the retired shell helpers remain readable so native Purge can clean them safely.

## Patch Rekordbox on a friend's Mac

This changes only that Mac's Rekordbox target. It does not start the bridge,
change SIP, or prove memory reads.

1. Quit Rekordbox.
2. Open the exact installed **RBSS Bridge** app, then choose **Patch Rekordbox**
   in the maintenance block. It is beside the source-only Export/Rebuild items;
   on a guest build it remains visible even though those other two are hidden.
3. Choose **Apply Patch** in the RBSS confirmation, then approve the native
   macOS admin prompt. If macOS reports App Management blocking the action, open
   System Settings → Privacy & Security → App Management, enable **RBSS Bridge**,
   and retry the same action.
4. After restart, a grey **Checking Rekordbox…** may appear while the large app
   is deep-verified. A grey **Rekordbox Patched** means `get-task-allow` is
   present and the full deep+strict signature passes. **Patch Rekordbox** stays
   actionable if either check fails, including repair after a partial attempt.
   Relaunch Rekordbox and confirm it opens.

Do not use Terminal, `osascript`, or a USB rebuild to patch the friend's app.
There is no retained or temporary full-app Rekordbox backup. A Rekordbox update
will remove the target patch; repeat this flow after an update.

`make_stick.sh` publishes only to an existing `/Volumes/...` target with
`PIONEER/`, and a real build refuses tracked/untracked repo dirt or a HEAD/file
change during the build. Payload symlinks are rejected, `govee.env` is staged
and installed mode `0600`, and an installer rollback error no longer claims the
installed copy is safe; retry from the installer-disk copy instead.

## Operator parity run (PAUSED pending stock-SIP live gate)

Do not treat earlier foreign-Mac packaging failures or the RB7216
`libssl.3.dylib` apply failure as proof that stock attach is impossible —
neither reached patch OK → deep verify OK → main GTA=true → relaunch before
attach. Resume the physical attach gate only as an ordered stock-SIP
Apple-Silicon live run (patch → deep verify → GTA=true → relaunch → attach).
Do not weaken guest SIP. Only a `task_for_pid` denial after every prior step
passes may be classified as caller attach denial. The table remains the later
acceptance checklist.

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
| **Memory reads** | **LIVE-UNVALIDATED / UNKNOWN** on stock SIP until ordered patch + deep verify + GTA=true + relaunch + attach (AWR-222); do not classify as confirmed caller denial beforehand | ☐ |
| Test the Lights | recorded session drives the rig; refuses while Rekordbox open | ☐ |

**Memory-read STOP rule:** earlier physical attempts failed, but they are not
proof of post-GTA caller denial. Do not improvise entitlements or weaken SIP
on a guest Mac. Resume only with the ordered stock-SIP live gate above; treat
AX as a dormant measurement probe, not a selected replacement reader, unless
that gate shows green-GTA + red-attach.

Evidence class until this table is green: **SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED**.
