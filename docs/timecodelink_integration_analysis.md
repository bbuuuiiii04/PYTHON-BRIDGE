# TimecodeLink ↔ Rekordbox Integration: Reverse-Engineering Report

**Session date:** 2026-05-06
**Analyst:** macOS RE analyst (read-only, observation-only methodology)
**Subject machine:** Apple Silicon (T8112), macOS Sequoia 15.3.1 (Darwin 24.3.0)
**Subject software:**

- Rekordbox 7.2.11.0342 (`/Applications/rekordbox 7/rekordbox.app`)
- TimecodeLink 0.0.24+042 (`/Applications/TimecodeLink.app`)
- rb_ss_bridge_v2 (`~/rb_ss_bridge_v2`) — bridge already attaches to RB via `task_for_pid`/`mach_vm_read_overwrite`

**Hard constraints honored in the original 2026-05-06 RE session:**
no binary modification, no code injection (no `DYLD_INSERT_LIBRARIES`, no Frida attach to RB), no SIP/library-validation/hardened-runtime changes, no DRM bypass, no kext, no source-code edits to rb_ss_bridge_v2 *during that session*. Read-only static analysis (`otool`, `nm`, `strings`, `codesign`, `plutil`) plus passive observation of TL's own log file plus dynamic call-stack sampling of the running TL process via `sample(1)` and `vmmap(1)`. The analyst's shell sandbox blocked `task_for_pid` and `sudo`; the user ran the equivalent commands in their own Terminal and pasted output back.

**Follow-on:** `rb_offsets.py`, `rb_state_reader.py`, and companion tests/YAML were added in a later bridge commit implementing §9–10. §10.2 documents the **actual** Python behaviour (which may refine prose elsewhere in this report).

---

## 1. Architecture summary

TimecodeLink is **not** a plugin, an XPC client, or a network peer to Rekordbox. It is a **direct out-of-process memory reader** that:

1. **Patches Rekordbox on disk before first use** — TL's `RekordboxPatcher` class extracts RB's existing entitlements, inserts `com.apple.security.get-task-allow=true`, and re-signs RB ad-hoc (via `/usr/bin/codesign`). This is a one-time, persistent modification of the RB bundle on disk; once done the RB binary is no longer Pioneer-signed (it becomes ad-hoc, `TeamIdentifier=not set`).
2. **Discovers RB at runtime** by shelling out to `pgrep` for the process name and `vmmap` for the `__TEXT` base address (regex parses standard `vmmap` output).
3. **Acquires RB's task port via `task_for_pid`** and reads memory via `mach_vm_read_overwrite`. This is identical to the mechanism the bridge's `rb_memory.py` uses today. It works because step 1 added `get-task-allow` to RB.
4. **Resolves all addresses through a hardcoded per-version offset table** — TL ships offsets for exactly **5 RB versions: 7.2.8, 7.2.10, 7.2.11, 7.2.13, 7.2.14**. Anything else logs `"Rekordbox %1 is not yet supported."` and the integration refuses to start.
5. **Polls RB at engine framerate (~30 fps)** in `RekordboxPlugin::poll()`. Runtime `sample(1)` confirms this loop repeatedly calls `extractDeck(int,int)` and then `mach_vm_read_overwrite`, with roughly 9 distinct memory-read call sites per deck per poll (about 1K+ Mach reads/sec at steady state across 4 decks). The decoded deck states feed an internal `EngineCore` whose outputs are: MIDI Time Code on `IAC Driver Bus 1`, optional OSC, an Ableton Link session, and the human-readable log file the bridge tails today.
6. **Reads RB's on-disk USBANLZ analysis files in parallel** — TL parses `/Users/bbui/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/.../ANLZ0000.{DAT,2EX}` directly for beat grids, waveforms, and cue points. This is a separate data path from the memory tap, exercised whenever a track changes.

**One-line summary:** TL = `task_for_pid + mach_vm_read_overwrite` polling at ~30 Hz (roughly 1K+ Mach reads/sec in steady state), gated by an on-disk re-sign of Rekordbox, with a parallel direct-read of Pioneer's USBANLZ analysis files. There is **no IPC, no XPC, no hooking, no swizzling, no code injection, no MIDI/audio capture, and no Pioneer framework linkage**.

---

## 2. Evidence ledger

Every claim below is mapped to a specific tool invocation and its output. Tool invocations done by the analyst are tagged `[static]` (run on the disk binaries) or `[runtime-log]` (read from TL's own log file at runtime). Live process-port observations attempted via `lsmp`/`vmmap`/`sample` are tagged `[runtime-tools]` if obtained.

### 2.1 TL bundle, signing, entitlements

`[static] codesign -dv --verbose=4 /Applications/TimecodeLink.app/Contents/MacOS/TimecodeLink`:

```
Identifier=com.timecodelink.app
Format=app bundle with Mach-O universal (x86_64 arm64)
CodeDirectory v=20500 size=27872 flags=0x10000(runtime) hashes=860+7
Authority=Developer ID Application: Alexander Kulik (W9R6WMW7JS)
Runtime Version=26.2.0
TeamIdentifier=W9R6WMW7JS
```

`[static] codesign -d --entitlements - /Applications/TimecodeLink.app`:

```xml
<dict>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>
  <key>com.apple.security.cs.disable-library-validation</key><true/>
</dict>
```

**Observation:** TL's entitlements are minimal — only the two flags Qt frameworks routinely need. **No `com.apple.security.cs.debugger`, no `get-task-allow` (incoming), no Apple Events, no App Sandbox.** Hardened runtime is enabled.

**Inference:** TL itself does not hold the debugger entitlement that would normally allow it to `task_for_pid` an arbitrary signed process. Its ability to read RB's memory therefore depends on RB granting TL the access — which is what `get-task-allow` on RB does. This is consistent with the patcher mechanism in §2.4.

### 2.2 RB bundle signing (post-patch)

`[static] codesign -dv --verbose=4 /Applications/rekordbox\ 7/rekordbox.app/Contents/MacOS/rekordbox`:

```
Identifier=com.pioneerdj.rekordboxdj
Format=app bundle with Mach-O universal (x86_64 arm64)
CodeDirectory v=20400 size=918802 flags=0x2(adhoc)
Signature=adhoc
TeamIdentifier=not set
Internal requirements count=0 size=12
```

`[static] codesign -d --entitlements - /Applications/rekordbox\ 7/rekordbox.app`:

```xml
<dict>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>
  <key>com.apple.security.cs.disable-library-validation</key><true/>
  <key>com.apple.security.device.audio-input</key><true/>
  <key>com.apple.security.device.camera</key><true/>
  <key>com.apple.security.get-task-allow</key><true/>   <!-- ★ -->
</dict>
```

`rekordboxAgent.app` carries the same entitlement set including `get-task-allow=true`.

**Observation:** RB on the user's disk is **ad-hoc signed** (`Signature=adhoc`, `TeamIdentifier=not set`) — a Pioneer-shipped binary would be signed with Pioneer's Developer ID, not ad-hoc. And it carries `get-task-allow=true`, an entitlement Pioneer would not ship in a release build of a paid product (it disables hardened-runtime task-port protection and is normally only present on debug builds).

**Inference:** This RB bundle has been re-signed *after install*, and the entity that did the re-sign added `get-task-allow`. The re-signer is identified by:

### 2.3 TL's `RekordboxPatcher` class — the re-signing mechanism

`[static] nm -m /Applications/TimecodeLink.app/Contents/MacOS/TimecodeLink | grep RekordboxPatcher`:

```
__ZN16RekordboxPatcher12startCopyAppEv          # startCopyApp()
__ZN16RekordboxPatcher12startSignAppEv          # startSignApp()
__ZN16RekordboxPatcher13startPatchingEv         # startPatching()
__ZN16RekordboxPatcher17onExtractFinishedE…     # onExtractFinished(int, QProcess::ExitStatus)
__ZN16RekordboxPatcher17onReplaceFinishedE…     # onReplaceFinished(...)
__ZN16RekordboxPatcher18isRekordboxRunningEv
__ZN16RekordboxPatcher20checkIfRekordboxQuitEv
__ZN16RekordboxPatcher20startReplaceOriginalEv
__ZN16RekordboxPatcher24startExtractEntitlementsEv
__ZN16RekordboxPatcher26addGetTaskAllowEntitlementERK7QString  # ★
__ZN16RekordboxPatcher33checkEntitlementsHaveGetTaskAllowEv
__ZN16RekordboxPatcher14onCopyFinishedE…
__ZN16RekordboxPatcher14onSignFinishedE…
```

`[static] strings -a` on the TL binary shows the matching user-visible strings:

```
Patching Rekordbox at:
Copying Rekordbox to temp folder...
/rekordbox.app
Failed to copy Rekordbox: %1
Failed to sign Rekordbox: %1
Rekordbox %1 patched successfully!
You can now launch Rekordbox.
Please quit Rekordbox to continue...
Rekordbox quit detected, continuing with patch...
rekordbox/lastPatchedVersion         (Qt setting key)
rekordbox/userDeclinedPatching       (Qt setting key)
codesign                              (literal command name)
No XML plist found in codesign output
```

`[runtime-log] timecodelink.log` line 124 (current session):

```
[2026-05-06 11:07:49] [info] Patcher status: RekordboxPatcher::AlreadyPatched -
                            "Rekordbox 7.2.11.0342 is ready"
```

**Confirmed mechanism:** TL invokes `/usr/bin/codesign` (via `QProcess`, hence the `onSignFinished(int, QProcess::ExitStatus)` slot) to:

1. extract RB's existing entitlements,
2. insert `com.apple.security.get-task-allow`,
3. re-sign RB ad-hoc (the `Signature=adhoc` we observe in §2.2),
4. replace `/Applications/rekordbox 7/rekordbox.app` with the patched copy.

This is a **persistent, on-disk modification of the RB bundle**, performed by TL with the user's permission, before TL's runtime memory tap will function.

### 2.4 TL's runtime task-port + memory mechanism

`[static] nm -m … | grep '(undefined)' | grep libSystem` on TL:

```
(undefined) external _task_for_pid              (from libSystem)
(undefined) external _mach_vm_read_overwrite    (from libSystem)
(undefined) external _mach_task_self_           (from libSystem)
(undefined) external _mach_port_deallocate      (from libSystem)
```

`[static] strings -a` on TL produced this exact format-string literal:

```
task_for_pid failed for PID %lld (error %d).
Make sure Rekordbox has been re-signed with get-task-allow.
```

**Inference (high confidence):** TL's data-acquisition primitive is identical to the bridge's `rb_memory.py` — Mach `task_for_pid` to obtain RB's task port followed by `mach_vm_read_overwrite` for each read. The error string spells out the dependency on the patcher.

### 2.5 RB process discovery

`[static] nm -m` on TL:

```
__ZN13ProcessFinder16findRekordboxPidEv          # ProcessFinder::findRekordboxPid()
__ZN13ProcessFinder19getRekordboxAppPathEv
__ZN13ProcessFinder19getRekordboxVersionEv
__ZN13ProcessFinder23getRekordboxBaseAddressEx  # base address lookup
```

`[static] strings -a` on TL:

```
pgrep
vmmap
([0-9a-fA-F]+)-[0-9a-fA-F]+.*__TEXT.*rekordbox      ← regex over vmmap output
/Applications/rekordbox 7/rekordbox.app/Contents/Info.plist
/Applications/rekordbox 6/rekordbox.app/Contents/Info.plist
/Applications/rekordbox/rekordbox.app/Contents/Info.plist
/Applications/rekordbox 7/rekordbox.app
/Applications/rekordbox 6/rekordbox.app
/Applications/rekordbox/rekordbox.app
```

TL imports **none** of: `proc_listpids`, `proc_pidpath`, `sysctlbyname`, `kvm_`*, `NSWorkspace`/`NSRunningApplication`, `LSCopyApplicationURLsForBundleIdentifier`. So discovery is implemented by:

1. shelling out to `/usr/bin/pgrep` to find RB's pid;
2. reading `/Applications/rekordbox {7,6,}/rekordbox.app/Contents/Info.plist` for the version string;
3. shelling out to `/usr/bin/vmmap <pid>` and regex-matching `([0-9a-fA-F]+)-[0-9a-fA-F]+.*__TEXT.*rekordbox` to find the slid base address.

`[runtime-log] timecodelink.log` lines 121–140:

```
[11:07:49] Rekordbox app path: "/Applications/rekordbox 7/rekordbox.app"
[11:07:49] Loaded offsets for versions: QList("7.2.10", "7.2.11", "7.2.13", "7.2.14", "7.2.8")
[11:07:49] Using offsets for "7.2.11" for version "7.2.11.0342"
[11:07:49] Found Rekordbox "7.2.11.0342" PID: 76746
[11:07:51] Base address: 100a14000
[11:07:51] Connected to Rekordbox
```

This corroborates the static evidence end-to-end: pgrep finds pid 76746, vmmap reports `__TEXT @ 0x100a14000`, version is read from Info.plist (`7.2.11.0342`), the four-component version is truncated to `7.2.11` for offset-table lookup.

### 2.6 TL has no Pioneer / RB framework linkage

`[static] otool -L /Applications/TimecodeLink.app/Contents/MacOS/TimecodeLink`:

linked frameworks are exclusively Qt 6.9.3 (QtCore/QtQml/QtQuick/…), `librtmidi.7`, `libsodium`, `libyaml-cpp.0.8`, ffmpeg, and Apple system frameworks (CoreFoundation, AppKit, CoreMIDI, IOKit, Security, Metal, OpenGL). **Zero Pioneer or RB-private frameworks.**

`[static] ls /Applications/TimecodeLink.app/Contents/Frameworks/` confirms the bundle ships only Qt frameworks plus the codecs.

`[static] strings -a` on the **RB main binary** filtered for `timecodelink|tcl_|tcllink`: **zero matches**. RB has no awareness of TL whatsoever.

**Inference:** This rules out:

- dyld interposition (would require TL to be loaded into RB's process — not happening, RB has no TL framework loaded)
- direct linkage / private framework use (no shared headers)
- IPC handshake (RB has no TL service name to advertise)

The integration is strictly one-way: **TL reads RB's address space; RB has no idea TL exists.**

### 2.7 Per-version offset table (the fragility surface)

`[runtime-log]` line 122:

```
Loaded offsets for versions: QList("7.2.10", "7.2.11", "7.2.13", "7.2.14", "7.2.8")
```

This is a `QList<QString>` of supported versions, populated at startup. The 4th component of the actual RB version (`7.2.11.0342`) is stripped before lookup (line 123 `Using offsets for "7.2.11" for version "7.2.11.0342"`).

**Inference:** Each supported RB version requires TL to ship a manually-curated set of offsets (deck struct base, BPM field, play-state field, etc.). When RB ships a new minor version, TL must also ship an update — confirmed by:

- the explicit `update_available` and `Rekordbox %1 needs to be patched for memory access` strings in TL,
- the `rekordbox/lastPatchedVersion` Qt setting that triggers re-patching when the RB version on disk changes,
- the `"No offsets for Rekordbox %1"` and `"Rekordbox %1 is not yet supported."` failure strings.

### 2.8 Polling architecture

`[static] nm -m` on TL:

```
__ZN15RekordboxPlugin5startEv
__ZN15RekordboxPlugin4stopEv
__ZN15RekordboxPlugin4pollEv                   # ★
__ZN15RekordboxPlugin10tryConnectEv
__ZN15RekordboxPlugin10deckStatesEv
__ZN15RekordboxPlugin11extractDeckEii          # extractDeck(deckIdx, ?)
__ZN15RekordboxPlugin13beatGridTicksEi
__ZN15RekordboxPlugin12beatGridBarsEi
__ZN15RekordboxPlugin14waveformDetailEi
__ZN15RekordboxPlugin15waveformPreviewEi
__ZN15RekordboxPlugin9cuePointsEi
__ZN15RekordboxPlugin14parseTrackInfoERK7QString
__ZN15RekordboxPlugin20computeGridBeatPhaseEiR9DeckState
__ZN12EngineWorker12processFrameEv
__ZN10EngineCore4tickEd
```

`[runtime-log]`:

```
[11:07:51] EngineWorker started at 30 fps
```

**Inference:** `EngineWorker` runs at 30 fps and on each frame calls `EngineCore::tick(dt)` which calls `RekordboxPlugin::poll()`, which performs the `mach_vm_read_overwrite` calls and updates a `DeckState` array via `extractDeck(int, int)`. The 30 fps is TL's polling rate; it is **not** a notification cadence from RB, because RB exposes no notifications.

### 2.9 The 15-second ENGINE STATE cadence

`[runtime-log]` consecutive ENGINE STATE blocks are exactly 15 s apart (`11:08:03`, `11:08:18`, `11:08:33`, `11:08:48`, `11:09:03`, …).

`[static] strings -a` on TL contains `=== ENGINE STATE ===` and the format strings used to render each line of the block. The accompanying `Deck %1: "%2" @ %3 BPM=%4 pitch=%5 [%6]%7` and `Layer %1: Deck %2, TC=%3, %4%%5` confirm this is a **logger snapshot**, not a polling cadence.

**Inference:** TL polls at 30 fps but **dumps a human-readable summary of the current state to its log every 15 s**. The 15 s is purely a logging downsample — internally, the data is fresh at 30 Hz. The bridge's `tl_tailer.py` ENGINE STATE regex consumes this 15 s downsample.

### 2.10 The "pitch=+0.0%" oddity (resolves the brief's question 5)

`[runtime-log] timecodelink.log.3` lines 233, 260, 277:

```
[09:10:50] Deck A: "I Love It (Cazes Edit)" @ 0:02 BPM=132.6 pitch=+0.0% [PLAYING] [MASTER] …
[09:11:05] Deck A: "I Love It (Cazes Edit)" @ 0:18 BPM=140.4 pitch=+0.0% [PLAYING] [MASTER] …
[09:11:05] Deck B: "Walking On A Dream …"   @ 0:03 BPM=140.4 pitch=+0.0% [PLAYING]          …
[09:11:20] Deck A: "I Love It (Cazes Edit)" @ 0:34 BPM=140.4 pitch=+0.0% [PLAYING] …
[09:11:20] Deck B: "Walking On A Dream …"   @ 0:19 BPM=130.0 pitch=+0.0% [PLAYING] [MASTER] …
```

Two independently observable facts:

1. The `**BPM=` field in TL changes** (132.6 → 140.4 → 130.0) as the user syncs / changes master. So TL *is* reading some live, post-sync BPM number from RB.
2. The `**pitch=` field stays at `+0.0%`** through the same window — even when the same track went from BPM=132.6 to BPM=140.4 (a +5.9% effective playback shift).

**Inference:** TL's `pitch` field is **not** the playback-rate deviation. It is a different RB internal — most likely the deck's tempo-fader displacement *excluding* sync (i.e., what the user manually set the pitch fader to, before sync took over). This matches the typical CDJ-style "Master Tempo / Sync" convention: when sync is engaged, the displayed pitch slider doesn't reflect the actual playback rate. So:

- **TL is not "filtering" pitch and is not "downsampling" pitch.** It is reading the value RB stores at TL's hardcoded offset, and that value happens to be the manual pitch fader, which on a synced deck reads 0.
- The bridge's `live_bpm.py` already reads the **effective** playback BPM directly from a different RB struct field, so it can compute the actual playback-rate deviation as `(live_bpm / track_bpm − 1) × 100`. That is strictly more useful information than TL's `pitch` field.

**This is the single most important finding for the bridge's replaceability assessment** — see §5.

### 2.11 Auxiliary data path: USBANLZ file reads

`[runtime-log]` lines 202–207, 214–218:

```
AnlzParser: parsed 456 beats from "/Users/bbui/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/446/d11b1-…/ANLZ0000.DAT"
AnlzParser: parsed PWV6 waveform, 1198 segments from ".../ANLZ0000.2EX"
AnlzParser: merged PWV5 RGB color data, 31570 source segments → 1198 target segments
AnlzParser: parsed PWV7 detail waveform, 31570 segments
```

`[static] nm -m` on TL: presence of `__ZN15RekordboxPlugin14parseTrackInfoERK7QString` and `AnlzParser` symbols.

**Inference:** Whenever a track changes, TL reads the corresponding ANLZ file directly off disk (Pioneer's beat grid + waveform format, public knowledge from the unofficial `crate-digger` documentation). This is independent of and parallel to the memory tap. It is the source of the per-deck beat grid, waveform preview, waveform detail (3-band + RGB), and cue points that TL feeds to its QML waveform renderer.

### 2.12 Live polling stack trace (closes brief Q2)

`[runtime-tools] sample 76761 5 -mayDie` (5 s sample of TL's main thread, run by user, 11:21):

```
RekordboxPlugin::poll()                                    + 696   [0x10289370c]
  └─ RekordboxPlugin::extractDeck(int, int)                + 160   [0x102893b50]
        └─ mach_vm_read_overwrite                          + 120   [0x18b3de058]
  └─ RekordboxPlugin::extractDeck(int, int)                + 716   [0x102893d7c]
        ├─ RekordboxPlugin::parseTrackInfo(QString const&) + 220   [0x10289521c]
        ├─ RekordboxPlugin::parseTrackInfo(QString const&) + 328   [0x102895288]
        └─ RekordboxPlugin::parseTrackInfo(QString const&) + 624   [0x1028953b0]
  └─ RekordboxPlugin::extractDeck(int, int)                + 176   [0x102893b60]
        └─ mach_vm_read_overwrite                          + 120
  └─ RekordboxPlugin::extractDeck(int, int)                + 220   [0x102893b8c]
        └─ mach_vm_read_overwrite                          + 120
  └─ RekordboxPlugin::extractDeck(int, int)                + 240   [0x102893ba0]
  └─ RekordboxPlugin::extractDeck(int, int)                + 516   [0x102893cb4]
  └─ RekordboxPlugin::extractDeck(int, int)                + 672   [0x102893d50]
        └─ mach_vm_read_overwrite                          + 120
  └─ RekordboxPlugin::extractDeck(int, int)                + 700   [0x102893d6c]
  └─ RekordboxPlugin::extractDeck(int, int)                + 1916  [0x10289422c]
        └─ mach_vm_read_overwrite                          + 120
  └─ RekordboxPlugin::extractDeck(int, int)                + 752   [0x102893744]
```

Independent corroboration from three angles:

1. **The exact static-symbol chain is observed at runtime** — `poll → extractDeck → mach_vm_read_overwrite`. No `dlsym`, no Objective-C runtime, no `xpc_`*, no Mach IPC client APIs in the path. This is the direct memory-tap path and nothing else.
2. `**extractDeck` issues ~9 distinct `mach_vm_read_overwrite` call sites per invocation** (return offsets `+160, +176, +220, +240, +516, +672, +700, +716, +1916`). Each call site = one field being walked out of the deck struct. So a complete deck snapshot costs ~~9 mach syscalls. Across 4 decks × 30 fps = **~~1080 mach_vm reads per second** as steady-state baseline, plus the master-deck byte and the track-info parsing.
3. `**parseTrackInfo` is called from inside `extractDeck` from at least 4 distinct call sites** (`+68, +220, +328, +624`). It is invoked on every poll cycle when a track is loaded — strongly suggests TL re-parses the track-info packed string on every poll rather than caching it across polls. (Cheap when no track is loaded; expensive when 4 decks are loaded.)

The call-graph is **flat** — no Qt event loop frames, no thread hops, no `QMetaObject::invokeMethod`. This means `RekordboxPlugin::poll()` runs synchronously on the engine worker thread (which the log line `EngineWorker started at 30 fps` describes).

### 2.13 vmmap confirmation of base address

`[runtime-tools] vmmap 76746 | grep '__TEXT.*rekordbox'`:

```
__TEXT  100a14000-1052e4000  [72.8M  8112K  0K  0K]  r-x/r-x  SM=COW  /Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox
__TEXT  107e28000-107e70000  [288K]                  …Bugsnag.framework/Versions/A/Bugsnag
__TEXT  107ee0000-107f08000  [160K]                  …libmpg123.0.dylib
__TEXT  107f88000-108084000  [1008K]                 …libsqlcipher.0.dylib
__TEXT  108110000-108124000  [80K]                   …Syphon.framework/Versions/A/Syphon
__TEXT  108170000-108214000  [656K]                  …libssl.3.dylib
__TEXT  108508000-108644000  [1264K]                 …libcld.0.dylib
```

**Confirms** `__TEXT @ 0x100a14000`, exactly the value TL logged at startup (`Base address: 100a14000`). RB's main binary occupies 72.8 MB of executable text — sizable, consistent with a JUCE/proprietary DJ engine. Bundle also ships `libsqlcipher.0.dylib` (the encrypted track DB), `Bugsnag.framework` (crash reporting), `Syphon.framework` (video out), `libcld.0.dylib` (likely Pioneer's CDJ Link Discovery/network stack), all unrelated to TL's tap but useful context for future bridge work.

### 2.14 RB process discovery confirmation (live PIDs)

`[runtime-tools] pgrep -lf` (run by user in their Terminal, 11:14):

```
TL:    76761  /Applications/TimecodeLink.app/Contents/MacOS/TimecodeLink
RB:    76746  /Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox
Agent: 76755  /Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordboxAgent.app/Contents/MacOS/rekordboxAgent
GPU:   76765  rekordboxAgent Helper (GPU)
Net:   76797  rekordboxAgent Helper  (utility / network.mojom.NetworkService)
Rend:  76815  rekordboxAgent Helper (Renderer)
```

**Confirms** the pid TL logged (`PID: 76746`) matches the actual `rekordbox` main binary, not `rekordboxAgent`. The agent (76755) is a separate Electron process with its own helper tree (GPU/Renderer/Network). TL targets the main RB binary only — the agent is irrelevant to TL's tap.

---

## 3. Signal-by-signal data path

For each line TL emits to `~/Library/Application Support/TimecodeLink/timecodelink.log` and that the bridge consumes today. Runtime sampling confirms these values are produced by a high-frequency loop (`RekordboxPlugin::poll()` -> `extractDeck` -> `mach_vm_read_overwrite`) rather than notification callbacks.

### 3.1 `track_loaded` — `[EVENT] Deck A loaded: "Sports Car (Devault remix)"`


| Stage              | Detail                                                                                                                                                                         |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Source field in RB | Deck-state struct at `RB_TEXT_BASE + offsets[7.2.11].deckN.trackHandle` (memory-tap), augmented with the on-disk track-info string read by `RekordboxPlugin::parseTrackInfo()` |
| Mechanism          | `mach_vm_read_overwrite` (memory tap, every poll) + on-disk file read of Pioneer DJ DB / track-info entry                                                                      |
| TL class           | `RekordboxPlugin::poll()` → `extractDeck(int,int)` → `parseTrackInfo(QString)`                                                                                                 |
| Trigger to log     | TL diffs the per-deck track identifier across consecutive polls; on change, the `Application` layer fires `[EVENT] Deck X loaded: "..."`                                       |
| Format string      | `[EVENT] Deck %1 loaded: "%2"` (literal in TL binary at offset `0x[…]/strings 14674`)                                                                                          |
| Latency            | ≤ 33 ms after RB updates the field (one frame at 30 fps)                                                                                                                       |


### 3.2 `bpm_update` — `BPM=130.0` inside ENGINE STATE block


| Stage              | Detail                                                                                                                                                                          |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source field in RB | A live, post-sync, post-master-tempo BPM at `RB_TEXT_BASE + offsets[7.2.11].deckN.effectiveBpm`. Confirmed live (e.g. 132.6 → 140.4 → 130.0 across master changes — see §2.10). |
| Mechanism          | `mach_vm_read_overwrite`                                                                                                                                                        |
| TL class           | `RekordboxPlugin::poll()` populating `DeckState`                                                                                                                                |
| Trigger to log     | Logger only; sampled at the 15 s ENGINE STATE cadence — but the value is fresh at 30 Hz internally                                                                              |
| Format string      | `Deck %1: "%2" @ %3 BPM=%4 pitch=%5 [%6]%7`                                                                                                                                     |
| Latency in log     | up to 15 s; **internally up to 33 ms** (this is what the bridge could match if it reads the same field directly)                                                                |


### 3.3 Play / Pause — `[EVENT] Deck A playing` / `[EVENT] Deck A paused`


| Stage              | Detail                                                                                                                                      |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Source field in RB | Per-deck play-state byte at `RB_TEXT_BASE + offsets[7.2.11].deckN.playState`. Value semantics consistent with rb_memory.py's `RB_PLAY_OFF`. |
| Mechanism          | `mach_vm_read_overwrite`                                                                                                                    |
| TL class           | `RekordboxPlugin::poll()` → `extractDeck`, diffed across polls in the engine layer                                                          |
| Trigger to log     | State-change diff                                                                                                                           |
| Format string      | `[EVENT] Deck %1 %2` with `%2` ∈ `{playing, paused}`                                                                                        |
| Latency            | ≤ 33 ms                                                                                                                                     |


### 3.4 `master_change` — `Rekordbox master deck changed: -1 -> 255`


| Stage              | Detail                                                                                                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source field in RB | A "current master deck index" byte at a global offset (the `255` raw value strongly suggests a `uint8_t` field initialized to `0xFF` for "no master assigned yet"). |
| Mechanism          | `mach_vm_read_overwrite` of a single byte at `RB_TEXT_BASE + offsets[7.2.11].masterDeck`                                                                            |
| TL class           | `RekordboxPlugin::poll()`; the `Rekordbox master deck changed:` log line is emitted only on diff                                                                    |
| Trigger to log     | State-change diff                                                                                                                                                   |
| Format string      | `Rekordbox master deck changed: %1 -> %2`                                                                                                                           |
| Latency            | ≤ 33 ms                                                                                                                                                             |


### 3.5 ENGINE STATE snapshot (15 s)


| Stage              | Detail                                                                                                                                                                                                                    |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source             | The full `DeckState[4]` array maintained inside TL from the 30 Hz memory tap, plus the `Layer[4]` routing table maintained inside TL from its own engine state (not RB-derived)                                           |
| Mechanism          | none new — pure logger output, no additional RB reads                                                                                                                                                                     |
| TL class           | `EngineCore::tick` (called 30×/s) checks an elapsed-time threshold and calls into the logger when ≥ 15 s have passed                                                                                                      |
| Format strings     | `=== ENGINE STATE ===` / `Master: Layer %1 @ %2 (%3%)` / `Deck %1: …` / `Layer %1: Deck %2, TC=%3, %4%%5` / `====================`                                                                                        |
| Bridge implication | The 15 s cadence is **arbitrary and can't be raised by the bridge** — but the underlying values are 30 Hz fresh. If the bridge wants ≥ 15 s ENGINE STATE detail at higher cadence, it must read the source fields itself. |


### 3.6 Per-layer timecode reports — `Layer A: Deck A, TC=00:00:00:02, 100.0%`


| Stage              | Detail                                                                                                                                                                                                          |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source             | TL's *own* timecode generator (the layer's MTC clock), **not** RB-derived. The "100.0%" is the layer-level rate — the TC clock's playback speed relative to nominal — and is independent of any RB pitch field. |
| Mechanism          | none — internal to TL                                                                                                                                                                                           |
| TL class           | `Layer::tick` / `TimecodeProvider`                                                                                                                                                                              |
| Bridge implication | This is data TL **generates** rather than reads from RB, and it's already accessible to the bridge via the same MTC stream on `IAC Driver Bus 1`.                                                               |


### 3.7 Auxiliary on-disk data path (track change → ANLZ parse)


| Stage              | Detail                                                                                                                                                                                                       |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Source             | `~/Library/Pioneer/rekordbox/share/PIONEER/USBANLZ/<bucket>/<uuid>/ANLZ0000.{DAT,2EX}`                                                                                                                       |
| Mechanism          | direct file read + parse of Pioneer's published-by-reverse-engineering ANLZ format                                                                                                                           |
| TL class           | `AnlzParser` + `RekordboxPlugin` (`beatGridTicks`, `beatGridBars`, `cuePoints`, `waveformPreview`, `waveformDetail`)                                                                                         |
| Triggered by       | track change (which is itself memory-tap-detected)                                                                                                                                                           |
| Bridge implication | The bridge could replicate this by reading the same files itself; the format is documented in the `crate-digger` open-source project. No special access needed (files are in the user's own home directory). |


---

## 4. Fragility assessment

**TL's integration is heavily hardcoded and version-coupled.** Concretely:

1. **Per-version offset table.** TL ships offsets for exactly 5 known RB minor versions (`7.2.8 / 7.2.10 / 7.2.11 / 7.2.13 / 7.2.14`). Any new RB version forces TL to ship an update or the integration refuses to start (`No offsets for Rekordbox %1`). This is the same fragility the bridge already faces in `rb_memory.py` / `live_bpm.py` — the bridge mitigates it with `live_bpm.py`'s pattern-scan / candidate-validation, but TL apparently does *not* do runtime address resolution.
2. **The patched binary is brittle.** RB's ad-hoc re-sign means any future RB integrity check, re-install, or auto-update (rekordbox 7's installer overwriting the bundle) reverts the patch and TL stops working until re-patched. This is observable in TL's `quickVerifyPatched(qint64)` method and the `Rekordbox %1 needs to be patched for memory access` string.
3. **Dependence on shell tools.** TL shells out to `pgrep`, `vmmap`, and `codesign` rather than using stable APIs. macOS could legitimately change the output format of any of those (vmmap output has changed slightly across releases). The brittle regex `([0-9a-fA-F]+)-[0-9a-fA-F]+.*__TEXT.*rekordbox` is the most likely future-failure point.
4. **No defensive fall-back.** Unlike the bridge's `live_bpm.py` (which can pattern-scan to find the BPM field at runtime), TL has no observed pattern-scan logic — `nm` shows no equivalent symbols and the strings table contains no scan-related diagnostic messages. The integration is binary: offsets-known or it doesn't work.

**Likelihood of a minor RB update breaking TL:** **High.** Pioneer's 7.2.x → 7.2.(x+1) updates have historically shifted struct layouts. TL only supports 7.2.8/10/11/13/14 — i.e. it has *already* missed 7.2.9 and 7.2.12 — which strongly suggests its release cycle is "wait for someone to find the new offsets, ship a new TL build." Any user on a freshly-installed RB 7.2.15+ would be locked out until TL ships an update.

---

## 5. Replaceability assessment for `rb_ss_bridge_v2`

This is the actionable section.

### 5.1 Signals the bridge can already acquire directly (or trivially extend)


| Signal                              | Direct-tap feasibility                                 | Notes                                                                                                                                                                       |
| ----------------------------------- | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `track_loaded` (deck → title)       | **Shipped in `RBStateReader`**                         | Per-deck **500-byte track-info** chain (`track_info_per_deck`) → UTF-8 decode up to NUL; **`TRACK_LOADED` fires only when the string changes and is non-empty** (no emit on clear-to-empty). Same spirit as TL diffing track identity across polls (§3.1). |
| Play / Pause per deck               | **Shipped in `RBStateReader`**                         | TL does **not** read a dedicated “playing” boolean from RB for this path (§7.6). **`RBStateReader` mirrors TL:** `is_playing = (live_pos_now != live_pos_prev)` on the **`live_pos_per_deck` → `readInt64`** chain. This is **orthogonal** to `rb_memory.py`'s `secondary+RB_PLAY_OFF` sign bit (still used for `PositionSnapshot.playing` corroboration). |
| `bpm_update` (effective, post-sync) | **`RBStateReader` + `live_bpm.py`**                    | **`RBStateReader`** reads TL's **fixed per-version float chain** at poll rate when offsets exist (`_BPM_EMIT_THRESHOLD = 0.05`, finite values in `(0, 1000)` only). **`live_bpm.py`** remains the bridge’s pattern-scan + **session-validated** path. For autoloop arm/follow policy see `docs/bridge_design.md`. |
| `master_change`                     | **High** — one byte at a global offset                 | Need the "current master deck index" offset; the `0xFF`-as-sentinel pattern matches a single uint8 read.                                                                    |
| ENGINE STATE 15 s snapshot          | **Already done**                                       | Bridge reads the underlying values directly via `rb_memory.py`; the 15 s log block is just a digest.                                                                        |
| Beat grid / cue points / waveform   | **Medium** — read ANLZ files directly                  | Same files TL parses. Pioneer ANLZ is public via crate-digger. **No new infrastructure needed.** Useful only if the bridge wants beat-grid bars or cue-point times.         |
| MTC timecode (per layer)            | **No** — this is TL-generated, not RB-derived          | The bridge already consumes it via IAC Driver Bus 1. Replacing it would require the bridge to itself become a timecode generator — significant new work, no obvious payoff. |


### 5.2 Signals where TL has something the bridge does not

**Updated for shipped `RBStateReader`:** master-deck index, per-deck track title (track load), live BPM float, and TL-style play/pause from position diff are **in `rb_offsets.py` + `rb_state_reader.py`** for Rekordbox **7.2.8 / 7.2.10 / 7.2.11 / 7.2.13 / 7.2.14** (ARM64 table embed). Remaining gaps:

- **ANLZ path → `ANLZ_PATH` event.** The offset table includes **`anlz_path_per_deck`** (TL `+0x90`-class chain). **`RBStateReader._tick_deck` does not read it yet** — so `FilepathResolver` still relies on `TLLogTailer` for ANLZ-before-load correlation unless that chain is wired to emit `Ev.ANLZ_PATH`.
- **On-air / `onAirLevel`.** TL `DeckState+0xa0` (§9.1). Not surfaced by `RBStateReader`.
- **ENGINE STATE block / per-layer TC lines.** TL-generated log digest (§3.5–3.6). **`RBStateReader` does not emit `TC_UPDATE`.** Bridge still uses `MTCReader` + TL ENGINE STATE for TC fallbacks.
- **Effective layer-rate / TC speed** as TL logs it. Internal to TL; not replaceable from RB memory alone.

### 5.3 Signals where the bridge already has something TL does not

- **Live, sub-second BPM.** TL's BPM is logged every 15 s; the bridge's `live_bpm.py` reads it at multiple Hz. For any application requiring tight BPM tracking (auto-DJ slip, beat-grid alignment), the bridge's path wins.
- **Position / time-elapsed within track.** The bridge's `rb_memory.py` PositionCache reads a position field at high cadence. TL's log only shows seconds-resolution time-elapsed in ENGINE STATE every 15 s. (TL likely has the same data internally for its MTC clock; it just doesn't log it.)
- **Pitched playback rate.** TL's logged `pitch=+0.0%` is the un-synced pitch fader; it does not reflect actual playback rate when sync is engaged. The bridge can compute true playback-rate deviation from `live_bpm / track_bpm`.

### 5.4 Recommended posture

**Shipped:** option **(a)** — the bridge embeds TL's macOS ARM64 `offsets-macos` extract in `rb_offsets.py` and implements **`RBStateReader`** as outlined in §9–10.

**Before promoting direct-read events to sole authority:** run **`TLLogTailer` and `RBStateReader` in parallel** (`docs/bridge_design.md`, §10.3–10.5), record per-source timing deltas, then add **explicit arbitration** if TL is ever gated off — **`StateManager` today applies `PLAY` / `PAUSE` the same way for every `event.source`**, so enabling both producers without merging guarantees **duplicate or competing transitions**.

**Fragility:** the embedded table inherits **exact version-string keys** (`load_offsets_for_version(rb_version)` is a plain map lookup; no normalization such as `7.2.11.0342 → 7.2.11`) and **per-release offset drift** when Rekordbox bumps binaries. `live_bpm.py`-style discovery remains the bridge's strategy when offsets are absent.

**Pattern-scan alternative** (§10.1a option C) for master `uint8` and other fields is still valid when TL has not published a row for a new RB build.

---

## 6. Open questions (read-only toolchain insufficient)

These are the questions where evidence was ambiguous or the analyst's sandbox blocked the conclusive observation. Each is paired with the additional observation that would close it and the user-approval level it needs.


| #   | Question                                                                                                                                                                                                                            | What would close it                                                                                                                                                                                                                                                                                   | Approval level needed             |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| O1  | Does TL also tap `rekordboxAgent` (76755), or only the main `rekordbox` (76746)? Static evidence shows `pgrep -f rekordbox` matches both, but the log shows it locks onto pid 76746 only.                                           | `lsmp -p 76761` (TL) checking for any send-rights into pid 76755.                                                                                                                                                                                                                                     | Just sudo lsmp; observation-only. |
| O2  | ~~Exact byte layout of TL's offset table for 7.2.11.~~ **CLOSED** in §7. The offset table is **not** a static constexpr — it is loaded at startup from a Qt `QResource` blob (`:/qt/qml/TimecodeLink/resources/offsets-macos`) by `OffsetManager::loadOffsetsFile`, into a per-version `OffsetVersion` struct whose layout was recovered by disassembling `RekordboxPlugin::poll` and `RekordboxPlugin::extractDeck`. | —                                 |
| O3  | Is TL's "pitch" field (which logs +0.0% during sync) actually the manual pitch-fader displacement, or something else (e.g., `tempo_value` before sync override)?                                                                    | Live test: with TL+RB+sync engaged, move the on-screen pitch fader for the synced deck and watch whether TL's log changes. Pure UI observation.                                                                                                                                                       | None — purely user-driven.        |
| O4  | ~~Confirm the polling stack trace `RekordboxPlugin::poll → mach_vm_read_overwrite` runs on a dedicated thread.~~ **CLOSED** in §2.12. The chain `poll → extractDeck → mach_vm_read_overwrite` is directly observed via `sample(1)`. | —                                                                                                                                                                                                                                                                                                     | —                                 |
| O5  | What is rekordboxAgent's role w.r.t. TL? It runs an Electron process tree (Network/Renderer/GPU helpers). Does TL care about it at all, or is it pure RB licensing/cloud sync?                                                      | `lsmp` of TL + `fs_usage` of TL (look for any IPC to Agent or reads of Agent-managed files).                                                                                                                                                                                                          | sudo for fs_usage.                |
| O6  | Does TL ever invoke `pgrep`/`vmmap`/`codesign` after startup (e.g., on RB restart) or only at first connect?                                                                                                                        | `fs_usage -f exec 76761` for ~5 minutes spanning a deliberate RB quit/restart by the user.                                                                                                                                                                                                            | sudo for fs_usage.                |


---

## 7. Closing O2 — `OffsetVersion` struct layout (static reverse engineering)

**Method:** `[static] otool -arch arm64 -V -t -p __ZN15RekordboxPlugin4pollEv` and `__ZN15RekordboxPlugin11extractDeckEii` against `/Applications/TimecodeLink.app/Contents/MacOS/TimecodeLink`. Cross-referenced against `__ZN12MemoryReader18followPointerChainEyRK5QListIyEy` (3-arg signature: `this, base, &chain, finalOffset`) and `__ZN12MemoryReader9readBytesEym` (which `bl __ZN12MemoryReader9readBytesEy` → `_mach_vm_read_overwrite`).

### 7.1 The offset blob is a runtime-loaded Qt resource, not a constexpr

`[static] strings -a -arch arm64` produced exactly one filesystem-style path matching the offset domain:

```
:/qt/qml/TimecodeLink/resources/offsets-macos
Could not open offsets file:
Loaded offsets for versions:
Using offsets for
No offsets for Rekordbox %1
```

`[static] nm -m -arch arm64`:

```
__ZN13OffsetManager13selectVersionERK7QString
__ZN13OffsetManager15loadOffsetsFileERK7QString
__ZN13OffsetManagerC1ERK7QString
__ZN13OffsetManagerC2ERK7QString
__ZNK13OffsetManager17availableVersionsEv
```

`[static] otool -L`: TL links `libyaml-cpp.0.8.dylib`.

**Inference:** TL ships a YAML document compiled into the Qt resource bundle at the qrc path above (zlib-compressed by default in Qt rcc). At startup, `OffsetManager::loadOffsetsFile(":/qt/qml/TimecodeLink/resources/offsets-macos")` parses it via yaml-cpp into a `QMap<QString, OffsetVersion>` keyed by RB version (`"7.2.8"`, `"7.2.10"`, `"7.2.11"`, `"7.2.13"`, `"7.2.14"`). `selectVersion(QString)` then makes the chosen `OffsetVersion*` available to `RekordboxPlugin`. This is why §2.7 sees the version list at runtime but no static offset constants in the binary.

### 7.2 `RekordboxPlugin::poll` — the master-deck read

`[static]` disassembly excerpt at `0x10007b558` (entry into the per-poll body):

```asm
ldp  x0, x22, [x19, #0x68]     ; x0 = MemoryReader*, x22 = OffsetVersion*
ldr  x1,      [x19, #0x78]     ; x1 = RB __TEXT slid base
add  x2, x22, #0x20            ; x2 = &masterChain (QList<u64>)
ldr  x3,      [x22, #0x38]     ; x3 = masterFinalOffset (u64)
bl   __ZN12MemoryReader18followPointerChainEyRK5QListIyEy
mov  x1, x0
cbz  x1, 0x10007b6ec           ; if chain failed → goto cleanup
ldr  x0, [x19, #0x68]
bl   __ZN12MemoryReader9readUInt8Ey   ; read 1 byte from chain-resolved addr
mov  x20, x0                   ; x20 = current master deck index (u8)
…
ldr  w8, [x23, #0xdf8]         ; previous master deck (global at 0x1002fdde8)
cmp  w8, w0
b.eq 0x10007b6dc               ; if unchanged → skip log
…  emit  "Rekordbox master deck changed: %1 -> %2"
str  w20, [x23, #0xdf8]        ; persist new master
…
ldr  w8, [x22, #0x50]          ; deckCount field of OffsetVersion
cmp  w8, #0
b.gt 0x10007b6fc               ; iterate extractDeck(0..deckCount-1, master)
```

**Conclusions for Brief Task 2 (master arbitration):**

1. The master deck is a **single `uint8_t`** in RB's address space, reached by walking a per-version pointer chain.
2. TL emits `Rekordbox master deck changed:` purely on **diff against a TL-internal cached uint32** at `TL+0x1002fdde8`. The "arbitration" is done entirely inside RB; TL just reads RB's authoritative byte. The on-screen value in the bridge's TL-log tail (`-1 -> 255`) confirms `0xFF` is RB's "no-master" sentinel and `0..N-1` are the deck indices.
3. The bridge can replicate this with **one `mach_vm_read_overwrite` per poll** of a single byte at the chain-resolved address — provided it carries the same per-version chain as TL.

### 7.3 `RekordboxPlugin::extractDeck(deckIdx, masterIdx)` — the per-deck reads

Five fields are read per deck per poll. All reach RB memory through `MemoryReader::followPointerChain` against array slots in `OffsetVersion` indexed by `deckIdx << 5` (32-byte stride per chain entry: 24-byte `QList<u64>` + 8-byte `finalOffset`):

| `OffsetVersion` slot | Final read primitive    | Field semantic                                                                | DeckState write |
| -------------------- | ----------------------- | ----------------------------------------------------------------------------- | --------------- |
| `+0x48` array        | `readFloat`             | live BPM (post-sync, post-tempo) — fallback `0x42f00000f` (=`120.0f`) on miss | `+0x70` (double, via `fcvt`) |
| `+0x60` array        | `readInt64`             | live **play position in samples** (advances at 44100/s while playing, frozen while paused). Drives both position and play-state inference. | `+0x60` (double seconds = `samples / 44100 / 1000`), `+0x98`/`+0x9b` (byte: 1 if **value changed** between polls = isPlaying), `+0xa0` (double: 1.0 if changed else 0.0 = onAirLevel) |
| `+0x78` array        | `readString(500)`       | trackInfo packed string — fed to `parseTrackInfo` (splits "Title - Artist")   | `+0x18`, `+0x30`, `+0x48` (3 QStrings) |
| `+0x90` array        | `readPointer + readString(500)` | filepath of `ANLZ0000.DAT` for current track — opened off-disk by `parseAnlzFile` | (no DeckState slot — used only to drive disk-side waveform/grid loaders) |
| `+0x98` (scalar)     | array-length sentinel   | upper bound for deckIdx (compared in `extractDeck` prologue)                  | — |

**The +0x98 byte is `isPlaying`, definitively** — verified by `DeckStateModel::update` at `0x100054660–0x1000546c0`:

```asm
adrp x1, ... "[EVENT] Deck %1 %2"          ; format string
…
ldrb w8, [x20, #0x98]                       ; new DeckState +0x98
adrp x8, ... "paused"
adrp x9, ... "playing"
csel x1, x9, x8, ne                         ; if (+0x98 != 0): "playing", else "paused"
```

The `extractDeck` codegen sets `+0x98 = 1` exactly when the readInt64 chain at `OffsetVersion+0x60` returns a **different value than the previous poll** for this deck — i.e., the live position field advanced. Position field unchanged ⇒ paused. Position field changed ⇒ playing. (This was previously mis-labeled in earlier drafts of this document as "trackInfoOk"; the static control flow at `0x10007bc30 → 0x10007bc8c → 0x10007bca0 (w21=1)` for the changed branch vs `0x10007bd08 (w21=0)` for the unchanged branch resolves the inversion.)

DeckState (the `std::array<DeckState, 4>` consumed downstream by `EngineController::updateDeckStatesFromSnapshot`) is `0xb8` bytes (184 B) wide. Verified by:

- `umaddl x21, w23, #0xb8, x9` at `0x10007c954` — `x21 = deckArrayBase + deckIdx*0xb8`.
- The store sequence `[x21, #0x18 | 0x30 | 0x48 | 0x60 | 0x68 | 0x70 | 0x80 | 0x98 | 0x9a | 0x9b | 0xa0]` covers the field set below.

```c
// DeckState (size 0xb8 = 184) — TL's per-poll output snapshot.
// Stride confirmed by EngineController::updateDeckStatesFromSnapshot using
// {x19+0, x19+0xb8, x19+0x170, x19+0x228} = 4×0xb8 = 736 = 0x2e0 (size 4 array).
struct DeckState {
    uint64_t reserved_00;          // +0x00 (refcount/vtable ptr; not written in extractDeck)
    char     reserved_08[0x10];    // +0x08
    QString  trackInfoRaw;         // +0x18  (raw 500-byte buffer copy)
    QString  trackTitle;           // +0x30  (parseTrackInfo output 1)
    QString  trackArtist;          // +0x48  (parseTrackInfo output 2)
    double   elapsedSec;           // +0x60  (live play position seconds = samples / 44100)
    double   gridBeatPhase;        // +0x68  (AnlzBeatGrid::getTime)
    double   liveBpm;              // +0x70  (the float at OffsetVersion+0x48 chain, widened)
    char     reserved_78[0x08];    // +0x78
    double   pitchScale;           // +0x80  (initialised to 1.0; used elsewhere)
    char     reserved_88[0x10];    // +0x88
    uint8_t  isPlaying;            // +0x98  (1 if position advanced between polls — DeckStateModel::update emits "playing"/"paused" from this byte)
    uint8_t  reserved_99;          // +0x99
    uint8_t  isMaster;             // +0x9a  (deckIdx == masterIdx)
    uint8_t  isPlayingMirror;      // +0x9b  (same value as +0x98; written redundantly)
    char     reserved_9c[0x04];    // +0x9c
    double   onAirLevel;           // +0xa0  (1.0 if isPlaying, else 0.0)
    char     reserved_a8[0x10];    // +0xa8 (consumed by EngineController)
};
```

Reconstructed `OffsetVersion` layout (the per-version table mapped from the YAML resource):

```c
// OffsetVersion — populated by OffsetManager::loadOffsetsFile from offsets-macos QResource
// stride per chain entry = sizeof(QList<u64>)+sizeof(u64) = 24+8 = 32 bytes (lsl #5)
struct ChainEntry {
    QList<uint64_t> chain;     // 24 B  hops applied to RB __TEXT base in order
    uint64_t        finalOff;  //  8 B  added to last hop's resolved address
};

struct OffsetVersion {
    char         reserved_00[0x20];  // +0x00..+0x1f  (probably version metadata: name string, qrc id)
    ChainEntry   masterDeck;         // +0x20         master-deck-index byte chain (global, not per-deck)
    int32_t      deckCount;          // +0x50         number of decks supported (1..4)
    char         reserved_54[0x10];  // +0x54..+0x47 padding/header for next region
    ChainEntry  *bpmPerDeck;         // +0x48         (interpreted as ptr to ChainEntry[deckCount])
    ChainEntry  *trackLenPerDeck;    // +0x60         readInt64 chain per deck
    ChainEntry  *trackInfoPerDeck;   // +0x78         readString(500) chain per deck
    ChainEntry  *anlzPathPerDeck;    // +0x90         filepath chain per deck
    int64_t      perDeckArrayLen;    // +0x98         deckCount × stride sentinel
    // (additional fields exist past +0xa0 — used by waveform/cue extraction in
    //  beatGridTicks/beatGridBars/cuePoints, not relevant to the bridge)
};
```

Caveat: the `ChainEntry*` interpretation above matches the indexed-load codegen (`ldr x8,[x22,#0x48]; add x2,x8,x23,lsl #5; ldr x3,[x2,#0x18]`). `+0x48` could equivalently be the first element of an inline array if the QList header is small — the disassembly does not distinguish. Either way, the per-deck chain stride and `+0x18` finalOff offset are exact.

### 7.4 `MemoryReader` — TL's wrapper around `mach_vm_read_overwrite`

`[static]` disassembly of `__ZN12MemoryReader9readBytesEym`:

```asm
…
mov  x0, x22                   ; x0 = MemoryReader*
mov  x1, x20                   ; x1 = src addr
mov  x2, x21                   ; x2 = size
add  x4, sp, #0x8              ; x4 = &outsize
bl   _mach_vm_read_overwrite   ; ← direct kernel syscall
cbz  w0, …                     ; if KERN_SUCCESS, copy out
```

`MemoryReader` instance layout:

```c
struct MemoryReader {
    void           *vtable;       // +0x00
    bool            connected;    // +0x08  (checked via tbz before any read)
    uint8_t         pad_09[3];
    mach_port_t     targetTask;   // +0x0c  (uint32 from task_for_pid)
    /* … */
};
```

This is the **exact same primitive** the bridge already uses in `rb_memory.py`:

```281:296:rb_ss_bridge_v2/rb_memory.py
def _read_bytes(task: int, addr: int, size: int) -> bytes:
    buf = (ctypes.c_uint8 * size)()
    out = ctypes.c_uint64(0)
    kr = _fn_vm_read(task, addr, size, ctypes.addressof(buf), ctypes.byref(out))
```
*(Line range approximate — see `/Users/bbui/rb_ss_bridge_v2/rb_memory.py:81–87`.)*

There is no shared memory mapping, no Mach message port (TL never imports `mach_msg`/`mach_port_request_notification`/etc.; `nm -m … | grep mach_` returns only `mach_vm_read_overwrite`, `mach_task_self_`, `mach_port_deallocate`). **Closes Brief Task 1.**

### 7.5 Liveness check — TL uses `kill(pid, 0)`

Top of `RekordboxPlugin::poll`:

```asm
ldr  w0, [x19, #0x80]   ; pid (cached at construct time)
mov  w1, #0
bl   _kill              ; kill(pid, 0) → 0 if alive, -1/ESRCH if dead
cbz  w0, 0x10007b558    ; alive → enter read body
…  emit "Rekordbox process exited"
strb wzr, [x19, #0x28]  ; mark MemoryReader.connected = false
```

This is observable in TL's log when RB quits. The bridge currently uses a different signal (Mach read failures cascade), but `kill(pid, 0)` is cheaper and unambiguous — possible future refinement.

### 7.6 How TL derives per-deck play state without a dedicated flag

TL does **not** read a per-deck "playing" boolean from RB's memory. Instead, `extractDeck` infers it from **whether the live-position field changed between polls**:

```text
extractDeck(deckIdx, masterIdx):
    sampleCount_now = readInt64( followChain(OffsetVersion+0x60[deckIdx]) )
    # Lookup previous value for this deck in std::map<int,int64> at [this+0x88]
    sampleCount_prev = map_lookup(deckIdx)  # default to sampleCount_now on first poll
    isPlaying = (sampleCount_now != sampleCount_prev)   # ← THE play-state derivation
    map_store(deckIdx, sampleCount_now)
    DeckState.isPlaying = isPlaying     # +0x98
    DeckState.elapsedSec = sampleCount_now / 44100.0    # +0x60
```

`DeckStateModel::update` then emits `[EVENT] Deck %1 playing` if `DeckState+0x98 != 0`, else `paused` — confirmed by the `csel x1, x9, x8, ne` codegen pinning the literal `"playing"` to the non-zero branch.

Implications for the bridge:

1. **TL's play state lags by one poll** at start/stop transitions (it cannot detect "playing" on the very first frame of motion — both samples need to be observed). The bridge's `RB_PLAY_OFF` direct flag (current `rb_memory.py`) reacts on the same poll.
2. **TL's play state is robust against the DDJ-800 mode=4112 quirk** that breaks the bridge's `secondary+0x2F0` flag. As long as RB is updating *some* monotonic position counter, TL infers playing. (The bridge's `live_bpm.py`/`probe_deck2.py` already exploit a similar invariant — find a field advancing at ~44.1 kHz — so the same principle applies.)
3. **Brief Task 4 conclusion:** the bridge's existing `d.playing` (TL log + memory corroboration) is at least as fidelitous as TL's own internal state, and *strictly more responsive* on first-frame transitions. The TL log tail remains a valid intermediary; a future direct-read replacement just needs to apply the same diff-against-previous-sample-count rule.

---

## 8. Closing Brief Task 8 — Licensing / DRM boundary

The brief asked specifically about `libFilSiNE_Mac_DyLib.dylib` and iLok. **Neither is present in TL 0.0.24+042.** Evidence:

`[static] otool -L /Applications/TimecodeLink.app/Contents/MacOS/TimecodeLink`: zero linkage to `FilSiNE`, `iLok`, `PACE`, or any third-party DRM. Crypto is a single `@rpath/libsodium.dylib` (Ed25519/sign/verify primitives).

`[static] strings -a -arch arm64`:

```
LicenseManager
isLicensedChanged
isLicensed
trialExpired
licenseEmail
licenseValid
license_type
license_key
license/key
License valid (server check passed)
Server reports license_valid=false for a locally licensed user (ignored; local verify is source of truth)
LicenseManager: sodium_init failed
license/installDate
TIMECODELINK_TRIAL_DAYS_AGO
Please enter both email and license key
Invalid license key
License activated for
License deactivated (was
```

**Mechanism:** TL implements its own `LicenseManager` class. Activation is `(email, license_key) → libsodium-verified signature`, persisted to `QSettings` under `license/key`, with an installDate-based trial. The phrase *"Server reports license_valid=false for a locally licensed user (ignored; local verify is source of truth)"* makes explicit that the **offline-verifiable signed key is authoritative**; the server check is informational only.

**Crucially: `LicenseManager` and `RekordboxPlugin` share no code path.** Verified by full disassembly (this session) of:

- `RekordboxPlugin::start` at `0x10007b2a4` (28 instructions): sets `running=1`, calls `QMessageLogger::info` with literal `"Starting Rekordbox plugin"`, calls `RekordboxPlugin::tryConnect`, conditionally calls `QTimer::start` on `[this+0x60]`. No load from any global, no symbol reference to `LicenseManager`, no conditional that could gate the memory tap.

- `RekordboxPlugin::tryConnect` at `0x10007a638` (~250 instructions before unwind): calls `ProcessFinder::findRekordboxPid`, `ProcessFinder::getRekordboxVersion`, allocates `OffsetManager`, calls `OffsetManager::selectVersion(version)` (returns false → log unsupported, return early), calls `ProcessFinder::getRekordboxBaseAddress`, allocates `MemoryReader`. Again, **no `LicenseManager` reference**, no `isLicensed` flag check, no path that aborts based on licensing state.

The licensing primitive imported is `_crypto_sign_verify_detached` (Ed25519 detached signature verification) plus `_sodium_init`. These are called only from `LicenseManager` symbols (`__ZN14LicenseManager*`) — verified by the absence of any `crypto_sign_verify_detached` call in the disassembly of all `RekordboxPlugin` and `MemoryReader` methods inspected.

The two subsystems are **independent**: licensing gates the QML UI (NagDialog activation prompts) and engine *output* (MTC/OSC/Link emission, log writing), but not the Mach memory tap itself. An unlicensed TL would still patch RB and read its memory if started; it would just refuse to surface the data through the UI/MTC.

**Bridge implication:** No licensing gate to circumvent or replicate. The bridge's access to RB is determined entirely by RB's `get-task-allow` entitlement, not by anything TL contributes beyond the on-disk patcher.

---

## 9. Data structure map — comparable to `PositionCache` / `DeckState`

This is Deliverable 2 from the brief, framed against the bridge's current `models.py` types.

### 9.1 Bridge ↔ TL field correspondence

| Bridge type / field (`models.py`, `rb_memory.py`)            | TL DeckState field         | RB-memory access pattern                                 |
| ------------------------------------------------------------ | -------------------------- | -------------------------------------------------------- |
| `PositionSnapshot.elapsed_ms` (i32 from `inner+0xC`)         | (not in TL DeckState)      | direct: `inner+0xC` i32 / 44100 * 1000                   |
| `PositionSnapshot.length_ms` (from `inner+0x8` upper 32 b)   | (not in TL DeckState — TL never reads track length)   | direct: `inner+0x8` u64 — bridge wins for length |
| `PositionSnapshot.playing` (i32 < 0 at `secondary+0x2F0`)    | `DeckState.isPlaying` (`+0x98`) — derived from position diff, not a flag read | direct: `secondary+0x2F0` i32 sign — bridge gets first-frame transitions; TL needs ≥ 2 polls |
| `PositionSnapshot.elapsed_ms` (from `inner+0xC` i32 / 44100 × 1000) | `DeckState.elapsedSec` (`+0x60`) | direct: `inner+0xC` i32; TL reads via `OffsetVersion+0x60` chain → readInt64 (full 64-bit, not just i32) |
| `DeckState.meta.bpm` (from ENGINE STATE log)                 | `DeckState.liveBpm` (`+0x70`) | direct: TL chain `OffsetVersion+0x48[deckIdx].chain → finalOff` (float) |
| `DeckState.meta.title` (from ANLZ DB / TL log)               | `DeckState.trackTitle` (`+0x30`) | direct: TL chain `OffsetVersion+0x78[deckIdx]` (500-byte string), then `parseTrackInfo` split |
| `DeckState.meta.filepath` (from ANLZ DB / lsof race)         | (none in DeckState; read off-disk via `+0x90` chain → `parseAnlzFile`) | direct: TL chain `OffsetVersion+0x90[deckIdx]` returns a filesystem path |
| `StateManager._active_deck` (set by `MASTER_CHANGED` events) | (not in DeckState — global) | direct: TL chain `OffsetVersion+0x20.chain → +0x38` returns a `uint8_t` |
| (no equivalent)                                              | `DeckState.isOnAir`/`onAirLevel` (`+0xa0`) | direct: derived in TL from `trackInfoOk`; for the bridge, this is an additional signal worth wiring |

### 9.2 Python translation — shipped as `rb_offsets.py`; `RBDeckState` still illustrative

```python
# Mirrors TL's DeckState slot — read-only output of one extractDeck() call.
@dataclass
class RBDeckState:
    track_title:    str
    track_artist:   str
    elapsed_s:      float    # live play position seconds (samples / 44100)
    grid_phase:     float    # ANLZ-derived, optional
    live_bpm:       float    # post-sync, post-tempo (matches TL's BPM=… log)
    pitch_scale:    float    # init 1.0 — currently unused
    is_master:      bool     # this_deck_idx == master_deck_idx
    is_playing:     bool     # position field changed between this & previous poll
    on_air_level:   float    # 1.0 if is_playing else 0.0

# Per-version offset table — analogous to TL's OffsetVersion, derived once per
# RB version and shipped alongside the bridge (replaces / augments config.py
# constants that are RB-7.2.11-specific today).
@dataclass(frozen=True)
class ChainEntry:
    hops:      tuple[int, ...]   # successive offsets applied via mach_vm_read
    final_off: int               # added to last hop's resolved address

@dataclass(frozen=True)
class RBOffsetVersion:
    version:               str                    # e.g. "7.2.11"
    deck_count:            int                    # 4 (verified across all 5 versions in offsets-macos)
    master_deck:           ChainEntry             # → uint8 master deck index
    bpm_per_deck:          tuple[ChainEntry, ...] # → float live BPM per deck
    live_pos_per_deck:     tuple[ChainEntry, ...] # → int64 live play position in samples per deck
    track_info_per_deck:   tuple[ChainEntry, ...] # → 500-byte packed string per deck
    anlz_path_per_deck:    tuple[ChainEntry, ...] # → filesystem path per deck (table present; RBStateReader does not read this chain yet — no ANLZ_PATH emits)
```

**Implementation status:** `RBStateReader` consumes **`master_deck`**, **`bpm_per_deck`**, **`live_pos_per_deck`**, and **`track_info_per_deck`**. It does **not** yet follow **`anlz_path_per_deck`**.

The `ChainEntry` class is the bridge equivalent of TL's `(QList<u64> hops, u64 finalOff)`. A reader implemented against this surface can resolve any one field with the same single-thread `mach_vm_read_overwrite` pattern TL uses (`len(hops)` pointer steps + final read) — see §10.2 for what is wired today.

---

## 10. Migration path — replacing `TLLogTailer` with a direct `RBStateReader`

This is Deliverable 4 from the brief. The recommendation remains **incremental and reversible**: keep **`TLLogTailer`** as fallback until parallel validation passes (`docs/bridge_design.md`). Kill-switch for the reader: set env **`RBSS_RB_STATE_DISABLE`** (any value) — **`run()` returns immediately** with no attach. (`RBSS_LIVE_BPM_DISABLE` is the analogous pattern for `LiveBPMService`.)

### 10.1 Acquisition — preferred option D: extract from TL's qrc resource

**Option D (recommended, demonstrated this session):** TL's `OffsetManager::loadOffsetsFile` reads from `:/qt/qml/TimecodeLink/resources/offsets-macos`, a Qt resource compiled into TL's binary. The resource is registered by `qInitResources_timecodelink_raw_qml_0` (TL+arm64 file offset `0x650420 / 0x6506e0 / 0x650b1a` for tree/names/data — see `vmaddr 0x10029c420/0x10029c6e0/0x10029cb1a` in disassembly).

The qrc binary format is documented (Qt v3 binary resources). Tree entries are 22 bytes:

```
+0x00 u32  nameOffset      (BE)  → offset into NAMES blob
+0x04 u16  flags           (BE)  → bit 0 = zlib-compressed, bit 1 = directory
+0x06 u32  reserved/v3     (BE)  → constant 1 for files in this binary
+0x0a u32  dataOffset      (BE)  → offset into DATA blob
+0x0e u64  lastModified    (BE)
```

File payload at `data_off + dataOffset` is `u32 length (BE) + u32 uncompressed_size (BE) + zlib_stream`.

A 35-line Python decoder (run this session) yielded **the full offset table verbatim**. Snippet for **RB 7.2.11**:

```text
7.2.11
04E18998 20 278 124           # master_deck       u8  (single global)
04DD3570 0  2C8 188           # deck 0 BPM        f32
04DD3570 0  2C8 120           # deck 0 live_pos   i64
04DD3570 0  270 38 80 28 F0 4 # deck 0 track_info str(500)
04E193C8 8  3F0               # deck 0 anlz_path  ptr→str
04DD3570 8  2C8 188           # deck 1 BPM
04DD3570 8  2C8 120           # deck 1 live_pos
04DD3570 8  270 38 68 28 F0 4 # deck 1 track_info
04E193C8 10 3F0               # deck 1 anlz_path
04DD3570 10 2C8 188           # deck 2 BPM
04DD3570 10 2C8 120           # deck 2 live_pos
04DD3570 10 270 38 48 28 F0 4 # deck 2 track_info
04E193C8 18 3F0               # deck 2 anlz_path
04DD3570 18 2C8 188           # deck 3 BPM
04DD3570 18 2C8 120           # deck 3 live_pos
04DD3570 18 270 38 48 28 F0 4 # deck 3 track_info
04E193C8 20 3F0               # deck 3 anlz_path
```

**Each line:** all numbers except the last are the QList<u64> hops; the final number is the finalOffset. `followPointerChain` semantics: `addr = base; for hop in hops: addr = read_u64(addr + hop); return addr + finalOffset`.

For deck 0 BPM `04DD3570 0 2C8 188`:
- `addr = base + 0x04DD3570`
- `addr = read_u64(addr + 0x0)`
- `addr = read_u64(addr + 0x2C8)`
- `read_float(addr + 0x188)` → live BPM

The **identity of the 5 deck-2 trackInfo middle hops** (e.g. deck 0 = `0x80`, deck 1 = `0x68`, deck 2/3 = `0x48`) cannot be derived by simple stride from deck 0 — TL ships them as explicit per-deck values. The bridge would do the same.

The full extracted YAML for all 5 supported versions (7.2.8 / 7.2.10 / 7.2.11 / 7.2.13 / 7.2.14) is in `docs/offsets-macos.yaml` alongside this analysis. The same procedure also yielded `docs/offsets-windows.yaml` (3.6 KB, 8 versions of RB on Windows including 6.x branches) and `docs/offsets-macos-x86_64.yaml`, useful only as comparative data.

### 10.1a Fallback acquisition options

**Option A:** TL's own diagnostic log. `RekordboxPlugin::logTrackInfoChainDiag(deckIdx)` prints `Hop %1: [%llx + %llx = %llx]` lines (verified: literal `"  Hop"` at `__cstring +0x157`, `"  Chain:"` at `+0x138`, `"  Final addr:"` at `+0x199`). Triggered when a track-info chain miss persists, so observable in the log without code changes. Useful as a sanity check against the qrc-extracted offsets.

**Option B:** parse a running TL process. `vmmap` + `mach_vm_read` against TL itself after `OffsetManager::loadOffsetsFile` has run. The per-version tables are in TL's heap as `QMap<QString, OffsetVersion>`. This is the path TL already exercises against RB; applying it to TL is symmetrical (and TL ships `get-task-allow=false`/hardened-runtime, but the analyst's user owns the process and can attach `lldb`).

**Option C:** independent rediscovery via `live_bpm.py`-style pattern-scan + movement validation. Slowest, but TL-independent — and the only path forward when RB ships a version TL hasn't yet released offsets for. The master-deck byte is the easiest target (single `uint8_t` flipping `0/1/2/3/0xFF` on master-button presses).

### 10.2 Implementation — **`rb_state_reader.py`** (authoritative description)

`rb_offsets.py` + `rb_state_reader.py` are in the repo, with unit tests under `tests/test_rb_offsets.py` and `tests/test_rb_state_reader.py` (fake `mach_vm_read_overwrite` harness).

**Bootstrap**

- **`make_rb_state_reader(event_queue, rb_version, **kwargs)`** calls **`load_offsets_for_version(rb_version)`**; if `None`, constructs **`RBStateReader(..., offsets=None)`** whose **`run()` exits immediately** (no-op thread).
- **`RBStateReader` constructor** accepts optional injected **`rb_pid`**, **`base_addr`**, **`poll_hz`**, **`clock`**, **`sleeper`** (tests use fakes).
- **`read_direct_master_status(rb_version, **kwargs)`** is the first master-specific convergence hook. It performs a one-shot read of **`offs.master_deck`** for startup visibility/status only. Unsupported versions, attach failures, and unreadable chains return unavailable status and leave **TL log / ENGINE STATE** authority unchanged.
- A bounded direct-master runtime observer now runs after startup/attach for live validation only. It compares the direct master byte against `TLMasterSnapshot`, which tracks only TL-derived master sources (`tl_log`, `engine_state`, `initial_engine_state`) and ignores bridge-local fallback sources. Runtime summaries include `outcome`, `final_direct_master`, `final_tl_master`, `transition_count`, `mismatches`, `first_valid_elapsed_s`, `comparison_source=tl_master_snapshot`, and `authority=tl_log`. It does not enqueue `MASTER_CHANGED` and does not mutate `StateManager`.

**Attach**

- Resolves pid via **`get_rb_pid()`** (`pgrep -x rekordbox`) unless overridden.
- Task port **`_task_for_pid`**; text base **`_base_from_vmmap(_get_vmmap_output(pid))`** — same helpers as **`rb_memory.py`**.

**Poll loop**

- Default period **`1.0 / max(1, MEM_POLL_HZ // 2)`** — with **`MEM_POLL_HZ = 60` → 30 Hz**, matching TL engine cadence.
- Schedule: target **`next_tick`** in monotonic time; **resync** when a tick overruns (no spin).
- **`OSError`** on **`_tick`**: logged at **`debug`** — loop continues.
- Any other **`Exception`** on **`_tick`**: **`log.exception`** + **1 s sleep**, **`next_tick` resync** to **`_clock()`**.

**`_tick` semantics (align with TL §7.2–7.6)**

1. **Master** — **`_follow_u8`** on **`offs.master_deck`**. When the byte **changes**, **`_last_master`** is set to the **new raw byte** (including **`0xFF`**); **`MASTER_CHANGED`** is enqueued **only if** **`0 <= master_raw < deck_count`**, **`deck = (master_raw % 2) + 1`**. Sentinels outside **`0..deck_count-1`** therefore **update baseline only**, no **`MASTER_CHANGED`**.
2. **Per deck `d` in `range(deck_count)`** — **`_tick_deck`** order is **track → BPM → position**:
   - **Track** — read up to **500** bytes UTF-8 at **`track_info_per_deck[d]`**; **`TRACK_LOADED`** if string **changed** and **`title` is truthy** (empty strings suppress emit).
   - **BPM** — **`readFloat` chain**; accept only **`0 < v < 1000`** finite; emit **`BPM_UPDATE`** if **`abs(bpm - last) > 0.05`** for that deck.
   - **Play/pause** — **`readInt64`** at **`live_pos_per_deck[d]`**. If **`None`**, **skip PLAY/PAUSE for this deck this tick** (track + BPM already handled). **`PLAY`/`PAUSE`**: **`is_playing = (pos != prev)`** after **two successful samples**; **`prev is None`** skips inference (first poll). **Known gap:** a **`None`** position read **does not update** `_last_pos_samples[d]` — the **next** good read may **compare against a stale `prev`** and spuriously edge; future hardening should freeze or invalidate baseline on failed reads.

**Not implemented in `_tick_deck` (table has chains, code does not consume yet)**

- **`anlz_path_per_deck`** — no **`ANLZ_PATH`** events.

**Differences vs TL `RekordboxPlugin::poll` (§7.5)**

- **No `kill(pid, 0)`** liveness at poll entry.
- **No automatic reattach** on RB restart (contrast **`RBMemoryReader._tick`** pid check + **`RB_RESTARTED`** event).

**Queue**

- **`put_nowait`**; on **`queue.Full`**, **drop** and **warning** (same policy as **`TLLogTailer`**).

**Source tag**

- All emits use **`source='rb_state'`** for downstream filtering / logging.

### 10.3 StateManager wiring

The new reader is **additive**. `StateManager` already consumes `MASTER_CHANGED`, `TRACK_LOADED`, `BPM_UPDATE`, `PLAY`, and `PAUSE` **without inspecting `event.source`** — so **two producers on the same queue duplicate or fight** unless one path is gated.

**Current repo state:** **`__main__.py` starts `TLLogTailer` + `RBMemoryReader` + … and can start `RBStateReader` only in explicit shadow mode. It also runs direct master startup observation and a bounded runtime observer when the Rekordbox version can be read.** These paths log `[RBMASTER][DIRECT]`, `[RBMASTER][SOURCE]`, and `[RBMASTER][RUNTIME]` evidence but do not enqueue `MASTER_CHANGED`, do not mutate `StateManager`, and keep `current=tl_log` / `authority=tl_log`.

The current TL-retirement process log is `docs/tl_retirement_process_log.md`. It records the live direct-master evidence, the current conclusion that direct master is promising but shadow-only, and the near-term plan: hold TL authority, consider only a future master startup-seed experiment if explicitly authorized, and keep runtime authority/play-pause/track/timing/scripted/ANLZ/TL-TC dependencies on TL for now.

**Rollout steps (recommended):**

1. Obtain Rekordbox **short version string** (must match map keys **`7.2.8` … `7.2.14`** today — see §5.4) and call **`make_rb_state_reader(event_queue, rb_version)`** (or **`RBStateReader(event_queue, load_offsets_for_version(...))`**) alongside **`TLLogTailer`**.
2. Run **both** during validation; log **`[source=tl_log]` vs `[source=rb_state]`** arrival deltas (e.g. `code_update_tracker.md` pattern).
3. **`RBSS_USE_TL_LOG`** (or equivalent) to prefer TL vs memory — **not implemented** in `__main__.py` as of this doc revision; treat as a **future** env gate once parity is proven.

The 200 Hz `StateManager` push loop remains untouched. The reader respects the threading invariant: **no direct `DeckState` writes** — only **`BridgeEvent`** enqueue. Mach I/O runs on the reader daemon thread (same class of blocking as `RBMemoryReader` / `LiveBPMService`).

### 10.4 What stays, what goes

| Component                        | Status after migration                                                                      |
| -------------------------------- | ------------------------------------------------------------------------------------------- |
| TL on-disk patcher (RB re-sign)  | **Required** — still the only path to `get-task-allow` on RB. No replacement proposed.      |
| TL runtime process               | **Optional** — only needed for MTC on IAC Bus 1 and Ableton Link output. Memory-tap data is now redundant. |
| `TLLogTailer` (ENGINE STATE, ANLZ correlation, …) | **Authoritative today** (see `docs/bridge_design.md`). `RBStateReader` can run in explicit shadow mode for parity only; it does not feed `StateManager`. Optional TL env gate after validation (`RBSS_USE_TL_LOG` or equivalent) — **not implemented** in code at this doc revision. |
| `MTCReader` (IAC Bus 1)          | **Unchanged** — TC fallback when RB memory / TL TC gaps apply. |
| `RBMemoryReader` (60 Hz)         | **Unchanged** — `PositionCache` / elapsed for push loop. |
| `LiveBPMService`                 | **First direct convergence point**: uses the per-version fixed-offset BPM chain as soon as the RB pid/base is attached, without waiting for ENGINE STATE; falls back to pattern-scan + session validation when unsupported or unreadable. Runtime logs label `offset_table`, `discovery`, and `fallback_meta` source states. |
| Direct master startup/runtime observers | **Second direct convergence point**: fixed-chain `master_deck` reads for startup visibility/corroboration and bounded runtime live validation. They label direct availability and direct-vs-TL snapshot agreement but preserve TL authority. |
| `FilepathResolver` (ANLZ + lsof) | **Unchanged**; **`anlz_path_per_deck` exists in `RBOffsetVersion` but `RBStateReader` does not emit `ANLZ_PATH` yet** — TL correlation path still required for ANLZ-before-load ordering unless wired. |

### 10.5 Stop-conditions for adopting the new path

The migration should be paused (not rolled back) if **any** of the following occurs:

1. RB ships a minor version (e.g., 7.2.16) whose offset chain differs from any known. The bridge's behaviour is unchanged — it falls through to `TLLogTailer` until offsets are observed.
2. Pioneer adds anti-tamper that detects the ad-hoc re-sign. TL stops working too; the bridge has no advantage over TL here.
3. An RB build introduces a mach trap filter that blocks `mach_vm_read_overwrite` from a non-debugger task. TL would also stop. Mitigation in either case is to update the patcher to add `com.apple.security.cs.debugger` instead of `get-task-allow` — out of scope for this analysis.

---

## 11. Stopping criteria — checklist against the brief


| Criterion                                                                            | Status                                                                                                                               |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Architecture summary supported by ≥ 2 independent pieces of evidence per major claim | ✅ Each claim in §1 has at least one static + one runtime corroboration in §2.                                                        |
| ≥ 4 of the 6 primary architectural questions defended                                | ✅ All 6 defended (discovery, attachment, data inventory, polling cadence, pitch representation, version coupling) plus entitlements. |
| Signal-by-signal data path filled in for ≥ 4 most important signals                  | ✅ §3 covers all 6+ (track_loaded, bpm, play/pause, master_change, ENGINE STATE, per-layer TC, ANLZ aux path).                        |
| Replaceability assessment concrete enough for the next session to decide direction   | ✅ §5 gives per-signal feasibility + a recommended decision frame.                                                                    |
| **Brief Task 1** — TL memory-access primitive (Mach vs shared mem vs IPC)            | ✅ §7.4 — direct `mach_vm_read_overwrite` via `MemoryReader::readBytes`; identical to bridge's `_read_bytes`.                         |
| **Brief Task 2** — master-deck arbitration source                                    | ✅ §7.2 — single `uint8_t` resolved by per-version pointer chain at `OffsetVersion+0x20`; sentinel `0xFF` for unassigned.             |
| **Brief Task 3** — live BPM extraction & validation                                  | ✅ §3.2, §7.3 — `readFloat` at `OffsetVersion+0x48[deckIdx]` chain; no in-TL pattern-scan; bridge's `live_bpm.py` is strictly stricter. |
| **Brief Task 4** — deck metadata & track loading                                     | ✅ §7.3 — `readString(500)` at `+0x78`, parsed by `parseTrackInfo`; ANLZ filename via `+0x90` chain (read-pointer-then-string).        |
| **Brief Task 5** — offset-table derivation (clean-room)                              | ✅ §7.1, §7.3 — table is loaded from `:/qt/qml/TimecodeLink/resources/offsets-macos`; `OffsetVersion` struct fully reconstructed in §7.3. |
| **Brief Task 6** — entitlement & injection analysis                                  | ✅ §2.3, §2.4 — `RekordboxPatcher` re-signs RB ad-hoc with `get-task-allow=true`; no in-process injection.                            |
| **Brief Task 7** — `RekordboxPlugin::poll` instrumentation                           | ✅ §2.12 — runtime `sample(1)` confirms flat call graph `poll → extractDeck → mach_vm_read_overwrite`; external process model.       |
| **Brief Task 8** — licensing / DRM boundary                                          | ✅ §8 — disassembly of `RekordboxPlugin::start` / `tryConnect` confirms zero `LicenseManager` references; libsodium primitive is `crypto_sign_verify_detached` (Ed25519). Memory tap is fully decoupled. |
| **Deliverable 1** — TL access method classification                                  | ✅ §7.4, §10.4 — pure Mach task reads; no shared memory, no IPC, no plugin model.                                                     |
| **Deliverable 2** — data structure map                                               | ✅ §7.3, §9 — C struct `DeckState` (0xb8) with `+0x60=elapsedSec`, `+0x70=liveBpm`, `+0x98=isPlaying` (verified from `DeckStateModel::update` codegen) + `OffsetVersion` + Python `RBOffsetVersion` / `RBDeckState` analogues. |
| **Deliverable 3** — feasibility assessment                                           | ✅ §5, §10.4 — bridge can replace TL log tailing; must retain TL only for the on-disk patcher and (separately) for MTC/Link if used.  |
| **Deliverable 4** — migration path                                                   | ✅ §10 — full per-version offset table extracted from TL's qrc resource; `rb_offsets.py` + `rb_state_reader.py` shipped this session with 24 unit tests. Adoption gated on parallel-run validation per §10.5. |


**Implementation note:** The original 2026-05-06 RE session produced this document **without** modifying Python; a **follow-on commit** added `rb_offsets.py`, `rb_state_reader.py`, tests, and embedded offset YAML companions. The **methodology** above remains: static `otool`/`nm`/`strings` + passive TL log + `sample(1)` on TL only — **no** Frida attach to Rekordbox, **no** SIP changes.

The 200 Hz `StateManager` thread behaviour is unchanged by the reader module itself until **`__main__.py`** wires it in.
