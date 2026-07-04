---
doc_status: current
truth_level: plan
last_verified_date: 2026-07-04
validation_scope: >
  Feasibility report + phased Codex plan for cross-platform (macOS-arm64 + Windows-x64)
  and cross-version portability. Software-planning only — no bridge behavior changed, no
  hardware run, no foreign-host validation. The reader's per-host authorization mechanism,
  Windows field-data derivation, and any version-adaptive lookup mechanism are OUT OF SCOPE
  here (separate reader implementation/RE spec). Code claims verified against HEAD; external
  packaging/signing claims cited and labelled by confidence.
work_status: parked — operator 2026-07-04: parked with the USB launcher final-project bundle (AWR-122); AWR-124 review findings R1-R11 + five composition stitches are NOT yet folded into this doc; re-verify all code claims at pickup
---

# Cross-platform / cross-version portability — feasibility + plan (planning half)

**Goal (Brandon's words):** plug a USB stick into *any* host laptop — a friend's Windows machine, his next MacBook — and have the same physical rig (DDJ-800 → SoundSwitch → lasers / LEDs / Govee) driven correctly, instead of only his one Mac today.

**This document is the planning half.** The reader — how each host authorizes memory access and how per-version field data is produced per platform — is a *given* here and becomes a separate reader/RE spec. This plan designs everything *around* the reader and names the reader-side items as blocking dependencies.

---

## 0. Verdict — lead with the outcome

**`READY WITH GAPS` for Codex**, split by platform:

| Target | Verdict | Why |
|---|---|---|
| **macOS-arm64 packaging & first launch** | `READY` · $0 | **Notarization declined by operator (2026-07-04).** Free path: ad-hoc-signed `.app`. Non-issue on your own Macs; on a friend's Mac it's a one-time "Open Anyway". No paid pipeline needed. |
| **The seam + version-resilience + strobe safety** | `READY` | All three are pure-Python refactors/additions above a seam that already *latently* exists; no new platform code needed to land them. |
| **Windows non-reader stack** | `READY WITH GAPS` | The whole output chain is portable Python, **except one hard blocker**: the bridge creates *virtual MIDI ports*, which python-rtmidi cannot self-create on Windows. Needs a decision (bundle a loopback driver, or ship a Windows MIDI-backend variant). |
| **Windows clean first launch** | `READY WITH GAPS` | Signing is cheap but **cannot guarantee** a wall-free SmartScreen first launch for a low-volume tool. Set expectations; don't overspend. |
| **A working Windows reader** | `NOT READY` — **top Windows blocker** | Windows field data does not exist; it's the reader spec's job. This plan assumes it will exist. |
| **Foreign-Mac memory authorization under a signed/notarized build** | `NOT READY` — **top macOS blocker** | Reader-spec territory, but it *intersects* this plan's signing work — see the critical finding in §4/§7. |

**One-line recommendation:** the portability work is real and mostly de-riskable *without owning a Windows machine* (CI builds both targets). Do the cheap, high-information validations first — prove the reader still works from a *packaged (ad-hoc)* macOS build, and prove the output stack runs on Windows from a *replayed* deck-state — before committing to the expensive reader RE. With notarization declined (below), the one dominant remaining risk is **Windows virtual-MIDI ports** (§1.3).

> **Operator decision (2026-07-04): notarization declined — will not pay the $99/yr.** Consequences: on Brandon's own Macs nothing is lost (signing was never involved). On a friend's Mac the app still runs — worst case a one-time "Open Anyway" in System Settings, or it may launch silently if a plain USB copy carries no quarantine flag. Upside: skipping notarization also drops the **Hardened Runtime** requirement, which *removes* one of the constraints behind the §7 memory-access risk — so this **lowers** the macOS risk, it doesn't raise it. The Developer-ID → notarize → staple pipeline in §3.4 is retained as **optional reference only**.

---

## 1. Portability architecture — the seam

### 1.1 The seam already exists, latently — it just isn't an interface yet

`confirmed` (code at HEAD). The reader's OS-specific surface is astonishingly small and already isolated in **one file**. `rb_state_reader.py` imports exactly five private primitives from `rb_memory.py` (`rb_state_reader.py:48-56`):

```
get_rb_pid            # rb_memory.py:126  → subprocess ["pgrep","-x","rekordbox"]  (rb_memory.py:127)
_task_for_pid         # rb_memory.py:85   → mach task_for_pid via libSystem.B.dylib (rb_memory.py:54,70)
_get_vmmap_output +   # rb_memory.py:136  → subprocess ["vmmap","--wide",pid]      (rb_memory.py:139)
_base_from_vmmap      # rb_memory.py:144  → parse TEXT segment load address
_read_bytes           # rb_memory.py:93   → mach_vm_read_overwrite
PositionCache         # rb_memory.py:967  (data container, already platform-neutral)
```

**Everything above that line is pure, portable Python.** The pointer-chain walker (`_follow_addr`/`_follow_u8`/`_follow_float`/`_follow_i64`/`_follow_string`, `rb_state_reader.py:658-790`) is `struct.unpack` over bytes; the diffing, play-inference, deck A/C→1 B/D→2 mapping (`_bridge_deck`, `rb_state_reader.py:70`), availability callbacks, and `BridgeEvent` emission are OS-agnostic. `RBMemoryReader` (the 60 Hz position thread, `rb_memory.py:992`) attaches through the *same three* primitives (`rb_memory.py:1255-1260`).

`confirmed`: `models.py` is already the platform-agnostic currency — `DeckState` (`models.py:76`), `PositionSnapshot` (`models.py:93`), `BridgeEvent`/`Ev` (`models.py:147,237`), `RBMasterState` (`models.py:139`) are pure dataclasses. `StateManager` consumes only these (plus the reader's availability callbacks). So **the bridge above the seam needs zero changes to run on Windows** — the entire OS-specific surface is the reader implementations behind the seam.

### 1.2 The interface the reader must satisfy (three small contracts)

Define these so the reader (macOS today, Windows later, adaptive later) is swappable without touching the rest of the bridge:

**(a) `ProcessMemorySource` (Protocol)** — the raw primitives, the only genuinely OS-specific code:
```
find_pid() -> int | None            # macOS: pgrep;      Windows: toolhelp/psapi
attach(pid) -> Handle               # macOS: task_for_pid; Windows: OpenProcess
module_base(pid) -> int             # macOS: vmmap parse; Windows: EnumProcessModules
read(handle, addr, size) -> bytes   # macOS: mach_vm_read; Windows: ReadProcessMemory
```
The existing `_follow_*` chain-walker and all event logic consume this unchanged. macOS impl = today's `rb_memory.py` bodies, moved behind the Protocol. Windows impl = reader spec.

**(b) `FieldResolver`** — `resolve(version) -> FieldSet | None` (today's `load_offsets_for_version`, `rb_offsets.py:308`). Table impl now; adaptive impl later. See §2.

**(c) `detect_target_version() -> str`** — today `read_rekordbox_version()` reads `Rekordbox.app/Contents/Info.plist → CFBundleShortVersionString` (`live_bpm.py:799,806,813`). macOS-bundle-specific; Windows needs the `.exe` file-version or registry (reader spec). Also feeds the DB path (per-OS).

**What has to change so the same bridge runs on both:** only the three impls above, selected once at startup by platform. `RBStateReader`/`RBMemoryReader` become thin wrappers that take a `ProcessMemorySource` instead of importing `rb_memory` internals. Nothing in `state_manager.py`, `models.py`, or any output subsystem changes.

### 1.3 Three portability items that live OUTSIDE the deck-state reader (in scope here)

These are *not* reader-spec items — they're the bridge's own OS couplings and this plan owns them:

- **⚠ Virtual MIDI ports — the hard Windows blocker.** `confirmed`: `streamdeck/streamdeck_midi.py:431` calls `mido.open_output(PORT_NAME, virtual=True)`; SoundSwitch look-selection and the laser MIDI path use the same mechanism (`soundswitch_midi_input.py:445` opens rtmidi ports; look-selection rides a macOS IAC virtual bus). `confirmed` (external): **python-rtmidi cannot create virtual ports on Windows** — Windows has no app-created virtual MIDI without a kernel loopback driver (loopMIDI / loopBe1). This breaks the bridge↔SS look-selection channel and the Stream Deck bridge on Windows unless resolved. **Decision needed** (§5, Phase 3): bundle/instruct a loopback driver, or ship a Windows variant that opens a real hardware/loopback port by name.
- **`lsof` filepath resolution.** `confirmed`: `filepath_resolver.py:85-87` shells `lsof -p <pid> -Fn` to identify the loaded track file; but it has a **DB/ANLZ fallback** (`filepath_resolver.py:370`, uses `pyrekordbox`). On Windows `lsof` doesn't exist — the plan should route Windows to the DB/ANLZ path (likely sufficient) rather than porting `lsof`.
- **Per-OS DB & version paths.** `pyrekordbox` reads the Rekordbox library DB; the path differs (macOS `~/Library/Pioneer/…` vs Windows `%APPDATA%\Pioneer\…`). Small, well-known.

`confirmed`: the dependency manifest **already platform-gates** — `pyobjc-framework-Cocoa … sys_platform == 'darwin'` (`pyproject.toml:12`). Good precedent: conditional platform deps are an established pattern here.

### 1.4 Out of scope, note once (per brief)

Raspberry-Pi / standalone (no-Rekordbox) operation is out of scope. The seam does not foreclose it: the `ReplaySource` (Phase 2) already feeds `BridgeEvent`s + `PositionSnapshot`s with no Rekordbox present, injecting at the reader→StateManager boundary *above* the `ProcessMemorySource` level — the same mechanism a no-Rekordbox standalone mode would use. Not designed for; just not blocked.

---

## 2. Version-resilience policy

### 2.1 Today

`confirmed`: `rb_offsets.py` carries a hardcoded macOS-arm64 table (`_OFFSETS_MACOS_ARM64`, `rb_offsets.py:49`) for **five exact builds** (7.2.8/7.2.10/7.2.11/7.2.13/7.2.14). Lookup is exact-string; unknown build → `None` (`rb_offsets.py:308-314`) → reader is a **clean no-op** (`rb_state_reader.py:184-190`, `make_rb_state_reader` logs and returns an inert reader, `:953-967`). The table entries are absolute addresses in the RB binary (e.g. `04E514D8`) plus pointer hops — they shift on every RB recompile, which is why the table is per-build.

### 2.2 Table vs version-adaptive lookup — recommendation

**Recommend: keep the per-version table as the reliable baseline; make the seam expose `FieldResolver` so an adaptive resolver can slot in later without touching the bridge.** Rationale:

- The **data** (per-version addresses, or the signature-scan that finds them on an unseen build) is *reader-spec* work either way — this plan only defines the interface. `assumed`: a version-adaptive resolver (pattern/signature scanning instead of hardcoded addresses) is materially more RE-heavy and is precisely the "version-adaptive lookup mechanism" the brief routes to the reader spec.
- A friend's laptop is **likely to run a build nobody pre-analyzed** — this is the strongest argument *for* adaptive. But "best-effort accuracy is acceptable" (locked constraint 3) plus the clean fail-closed (unknown build → no direct events → bridge still runs, lighting degrades) means a table miss is *safe*, just degraded. So the table is an acceptable v1; adaptive is a resilience upgrade, not a correctness prerequisite.

### 2.3 Concrete support policy

- **Supported = in the table** for its platform. macOS: the 5 current builds. Windows: **none yet** (top Windows blocker).
- **Unknown build → fail-closed → degraded lighting, never unsafe** (the strobe floor in §4 guarantees the "never unsafe" half regardless of data quality).
- **Refresh path:** each new RB build adds a table row, produced by the reader spec (the RE step). Document that the table is expected to lag new RB releases, and that the operator can keep an old RB build installed on his own machines as the reliable path.
- **The seam makes it swappable:** `FieldResolver.resolve(version)` is the only touch-point. Table impl → adaptive impl is a one-file swap; `RBStateReader` never knows which it got (it already handles `None` and a populated `FieldSet` identically).

---

## 3. Deployment & packaging

`confirmed` (external research, cited). Applies to **both** platforms except where noted.

### 3.1 Recommended packaging — PyInstaller `--onedir`, never onefile

- **Both OSes: PyInstaller `--onedir`.** onefile self-extracts to temp on every launch, and that self-extracting-bootloader pattern is exactly what Windows AV heuristics flag as a dropper (multiple corroborated PyInstaller/Nuitka reports; one case saw a signing account suspended over a Defender ML flag). onefile's internal binaries also can't be signed post-hoc. `--onedir` runs fine from a USB path with no admin install.
  - Sources: pyinstaller.org/en/stable/usage.html · pyinstaller.org/en/stable/operating-mode.html · github.com/pyinstaller/pyinstaller/issues/8164, /6754 · github.com/Nuitka/Nuitka/issues/3842
- **macOS: `--onedir --windowed`** → a real `.app` bundle (never a `.command` — it flashes a Terminal window). PyInstaller ad-hoc-signs bundled binaries by default, which isn't cosmetic: Apple-silicon AMFI rejects unsigned arm64 Mach-O outright. But ad-hoc is not enough for a clean *foreign* launch — see §3.4 (Developer ID + notarize).
- **Ship one clearly-named double-click target** (a shortcut on Windows; the `.app` on macOS). A bare onedir folder of DLLs confuses non-technical users.
- **Fallback if AV still misbehaves on Windows:** the official Python *embeddable* distribution + a hand-rolled launcher has the cleanest AV profile (plain files, no bootloader) at the cost of no hook system (you `pip install --target` yourself).
- **Disqualified:** shiv/pex (dispatch through an already-installed interpreter — the foreign laptop has none).

### 3.2 Build story — you do NOT need to own a Windows machine to *build*

`confirmed`: **neither PyInstaller nor Nuitka cross-compiles** (PyInstaller docs + FAQ: "not supported"; Nuitka maintainer: "cross compilation is not supported"). The documented, maintainer-endorsed path is a **GitHub Actions matrix**: a `macos-latest` job + a `windows-latest` job build natively off the same commit, in parallel. `confirmed`: GitHub's `macos-latest` runner is Apple-silicon (arm64) since 2024 — a native arm64 build for free. You still need a Windows machine to *test* and to run the rig, but not to produce the binary.
- Sources: pyinstaller.org/en/stable/usage.html · github.com/pyinstaller/pyinstaller/wiki/FAQ · github.com/Nuitka/Nuitka/issues/2149 · github.com/actions/runner-images/issues/9741

### 3.3 Dependency gotchas (repo-specific, verified against this codebase)

- `confirmed`: **numpy/scipy are optional at runtime** — zero unconditional imports in the core bridge (they live under the `analysis`/`spectral` extras, `pyproject.toml:23-24`). The default packaged build is numpy-free and light. Only enabling smart-drop spectral features pulls in the heavy native wheels (and their PyInstaller arch-slice strictness).
- `confirmed`: **mido dynamically imports its backend** — PyInstaller's static scanner misses it → `ModuleNotFoundError: mido.backends.rtmidi` at runtime. Fix: `--hidden-import mido.backends.rtmidi` (or `import mido.backends.rtmidi` explicitly). This repo *does* use rtmidi (`soundswitch_midi_input.py:445`), so this is a real ship-blocker if missed. Source: github.com/mido/mido/issues/219
- `confirmed`: **the certifi/SSL trap applies here.** `govee_runtime_sender.py:20` calls `https://openapi.api.govee.com` via `urllib` with `GOVEE_API_KEY` (`:246`). PyInstaller removed its old runtime hook that auto-set `SSL_CERT_FILE`, so a frozen build can fail cert verification only on the target machine. Fix: `--collect-data certifi` **and** set `os.environ["SSL_CERT_FILE"] = certifi.where()` at startup. (Govee *LAN*/UDP is separate and unaffected — only the Govee *cloud* path is at risk.) Source: github.com/pyinstaller/pyinstaller-hooks-contrib/issues/332
- python-rtmidi's compiled extension itself has no known hook problem. hidapi/libusb only matter if something does raw USB/HID rather than going through CoreMIDI/WinMM.

### 3.4 Clean, trusted first launch

**macOS — fully solvable, ~$99/yr.** `confirmed` (Apple docs):
1. Apple Developer Program ($99/yr) → **Developer ID Application** cert (the free personal-team cert is explicitly excluded from notarization).
2. `codesign` every Mach-O inside-out (nested dylibs/.so first, `.app` last) with `--options runtime` (Hardened Runtime) and `--timestamp`. Avoid relying on `--deep` — PyInstaller's use of it is a known source of intermittent rejections.
3. `ditto -c -k --keepParent` → `xcrun notarytool submit … --wait` (the old altool path was cut off 2023-11-01).
4. `xcrun stapler staple MyApp.app` **before** copying to the stick — this is what makes the check pass **offline** on a machine with no internet.
- **Quarantine on USB:** `confirmed` mechanism / `assumed` exact scenario — `com.apple.quarantine` is set only by quarantine-*aware* transfer apps (browsers, Mail, AirDrop), **not** a plain Finder copy/`cp` to a stick. So a locally-built app drag-copied to the stick very likely gets **no** quarantine and possibly no prompt at all — but this is "plausible, not empirically proven," so verify with `xattr -l` on the target Mac. It doesn't change the pipeline: with notarize+staple, worst case is one "Open" click, best case is silent. Defensive: `xattr -cr YourApp.app` before copying. Note Sequoia removed the old right-click "Open Anyway" bypass, so *don't* rely on a non-notarized app + a manual bypass on a foreign Mac.
- **Common notarization failures** (budget for a submit→fix→resubmit loop): unsigned/incorrectly-signed nested binary ("signature of the binary is invalid" — the #1 PyInstaller failure), missing Hardened Runtime on a nested binary, missing secure timestamp, leftover `get-task-allow` debug entitlement.

**Windows — partially solvable; sign cheap, don't chase a guarantee.** `confirmed` (Microsoft docs):
- Signing (`signtool sign /fd sha256 /tr <RFC3161> /td sha256`) stops the scary *unsigned* "Unknown Publisher" flow and gives a verified publisher name — but does **not** eliminate the SmartScreen "Windows protected your PC" screen on a fresh, low-volume file. That screen is **reputation-gated** (per-file-hash telemetry across Microsoft's user base; "several weeks and hundreds of clean installs"). A hobby tool shared with a handful of people **may never clear it**, signed or not. There's no manual reputation boost for consumer software.
- **⚠ EV certificates no longer help for this goal** — `confirmed`, and this *reverses* years-old advice: Microsoft stopped recognizing EV as distinct for SmartScreen (policy Feb 2024; EV OIDs removed from trusted roots 2024-08-27). Microsoft's current doc: *"Paying a premium for EV solely to avoid SmartScreen warnings is no longer justified."* **Don't buy EV.** (`verify at purchase time` — CA marketing pages lag.)
- **HSM reality (2023+):** OV/EV keys must live on FIPS hardware or a CA cloud-signing service (CA/B Forum CSC-17, eff. 2023-06-01). For a hobbyist, pick a **cloud signing** option — no dongle.
- **Cheapest clean paths:** Azure Artifact Signing (~$120/yr, no token, Microsoft's own recommended path; OV-equivalent reputation, individual track currently US/Canada-gated) or, **if the bridge source is public**, Certum Open Source Code Signing (~$85 setup + ~$30/yr — cheapest of all). Traditional OV+cloud (Sectigo/SSL.com/GlobalSign) ~$180-400/yr.
- Sources: learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation · …/code-signing-options · cabforum.org CSC-17 · learn.microsoft.com/azure/artifact-signing/faq

### 3.5 USB-stick specifics

- **Format the stick exFAT** (NTFS mounts read-only on macOS). Assume the media is read-only at runtime.
- **Write only to per-user appdata** (`%LOCALAPPDATA%\App`, `~/Library/Application Support/App`) for logs/cache/config — durable and host-agnostic (leaves a small folder behind), or `tempfile.gettempdir()` for zero-trace. **Never write beside the executable on the stick.** This repo writes `/tmp/bridge.log` today — fine on macOS, but the Windows path/temp location needs the per-OS appdata treatment.
- Paths with spaces are fine at launch; only self-inflicted unquoted subprocess calls to the app's own path break (quote them).

---

## 4. Live-performance safety — the one hard floor

**Requirement:** a bad reading must never drive a dangerous strobe.

### 4.1 Where a garbage BPM/beat can become a flash rate (bridge-controlled surfaces)

`confirmed`:
1. **BPM/beat → SoundSwitch over OS2L.** `StateManager`'s push loop sends `send_bpm` (`state_manager.py:3623,3630`), `send_beat` (`:3717`), `send_live_bpm_follow` (`:3667`); SoundSwitch runs *its own* strobes/effects on that tempo. This is the **primary** hazard because SS is the main lighting engine and the bridge feeds it the clock.
2. **In-bridge LED strobe.** LED strobe rate = BPM × beat-subdivision (subdivision ∈ {1,2,4,8}); `beat_sync_engine.py` runs animations at `bpm/60` (`:187,194`).
3. **Laser strobe** is a named scene/CC to the laser's own strobe (`laser_config.py:41`), not a bridge-computed rate — lower BPM-rate risk, but note it.

### 4.2 Current guards are insufficient

`confirmed`: the only bounds today are a read-side filter `0 < bpm < 1000` (`rb_state_reader.py:690`), a per-flash *duration* cap `max_strobe_duration_ms ≤ 750` (`led_models.py:171`), and `beat_sync_engine` clamping `born_bpm ≥ 1.0` (lower bound only, `:174`). **There is no upper BPM clamp and no flash-frequency ceiling.** A reading near the 1000 filter ceiling × subdivision 8 is, in principle, an extreme flash rate. (There is precedent for BPM bounds — `bpm_min <= meta.bpm < bpm_max`, `state_manager.py:1919` — but it gates *track selection*, not flash safety.)

### 4.3 Where to clamp — defense in depth, two small additions

1. **Source clamp (root cause, smallest diff).** Clamp `d.meta.bpm` to a plausible DJ range `[BPM_MIN, BPM_MAX]` at the single point it is written in `StateManager` — the `BPM_UPDATE` handler (`state_manager.py:3304`) and the track-load setter (`:2363`). Because `StateManager` is the **sole fan-out owner**, this one clamp bounds *every* downstream tempo — OS2L→SS, LED, laser sync — so a garbage reading can never propagate a dangerous tempo. Suggested range 40–220 BPM; **operator-tunable** (leave the knob — a real reading near the edges shouldn't be silently eaten).
2. **Hard flash-rate ceiling (the true floor).** At the in-bridge periodic-emit computation (LED strobe rate), cap effective flash frequency at `MAX_FLASH_HZ` regardless of BPM×subdivision — so even an *in-range* BPM with a high subdivision cannot exceed the ceiling. Reference point: photosensitive-safety guidance is ≤3 flashes/sec (WCAG 2.3.1 / Harding); club strobes intentionally exceed this, so the **exact ceiling is an operator decision** (medical-safe 3 Hz vs a club cap ~15-25 Hz). The architecture is fixed regardless: one clamp helper at the emit boundary.

**Boundary honesty:** the bridge **cannot** clamp SoundSwitch's own internal strobe effects — it can only bound the tempo/beat it *feeds* SS. Clamp #1 covers that (SS can't be driven faster than `BPM_MAX`). SS's authored effect rates are outside bridge control; that's a SoundSwitch-side authoring concern, not a bridge clamp.

This is platform-independent and should land **early** (before any foreign-machine run) — see Phase 2.

---

## 5. Phased, Codex-executable plan

Ordering principle: cheapest, highest-information, no-new-hardware validations first; expensive reader RE last. Each phase has a deliverable, files/areas, verification, and a live-safety note.

### Phase 1 — Prove the packaged (ad-hoc) macOS build still reads memory + drives the rig
- **Why first:** cheapest validation, and with notarization declined (no Hardened Runtime) the scary §7 memory-access risk is largely defused — so this is now a straightforward "does the frozen build still work like the source run" check, not a go/no-go gate. Needs only Brandon's Mac, $0.
- **Deliverable:** package **today's** macOS bridge with PyInstaller `--onedir --windowed` (ad-hoc signed — PyInstaller's free default, which satisfies Apple-silicon's must-be-signed-to-run rule); run it on Brandon's Mac; **confirm the memory reader still attaches and drives lighting** end-to-end. Optionally try a friend's Mac (one-time "Open Anyway").
- **Files/areas:** build spec (`.spec`, CI); `--hidden-import mido.backends.rtmidi`; `--collect-data certifi` + `SSL_CERT_FILE` shim; the `com.apple.security.cs.debugger` entitlement (still needed for memory access — that's separate from, and unaffected by, the notarization decision).
- **Verify:** the packaged app attaches (`[RBMEM][ATTACH]`/`RBStateReader: attached`), emits `MASTER_CHANGED`/`BPM_UPDATE`, and rotates SoundSwitch. `pgrep -f rb_ss_bridge_v2 | wc -l == 1` after launch.
- **Live-safety note:** run against a *test* Rekordbox session, not a live show.

### Phase 2 — Extract the seam + replay reader + land the strobe floor (pure Python, macOS, no behavior change)
- **Deliverable:** (a) hoist the five primitives behind `ProcessMemorySource`; make `RBStateReader`/`RBMemoryReader` consume it; add `FieldResolver` + `detect_target_version` seams (§1.2). (b) Wire a startup-selectable **`ReplaySource`**. `confirmed`: this is nearly free — `session_replayer.py` ("Offline replay helpers for recorded **StateManager input** sessions", `:1`) already parses recorded `BridgeEvent`s + `PositionSnapshot`s and `put_nowait`s them into a StateManager event queue (`:160,235`), and `session_recorder.py` captures at exactly that boundary (`record_event`/`record_position`, `:77,92`). So the replay path already injects at the reader→StateManager seam — **above** the `ProcessMemorySource` level, bypassing memory reads entirely. Phase 2(b) is promoting that offline test helper to a runtime-selectable source, not writing a new reader. (c) Land the §4 strobe clamps.
- **Files/areas:** new `reader_backend.py` (Protocols) + `reader_macos.py` (today's `rb_memory` bodies); thin edits to `rb_state_reader.py:48-56` imports; `state_manager.py:3304,2363` (BPM clamp) + LED strobe emit (flash-Hz ceiling); no change to `models.py`/output subsystems.
- **Verify:** `python3 -m unittest discover tests` green (2898-baseline); macOS behavior byte-identical (the macOS impl is the same code behind an interface); a unit test that a garbage BPM (e.g. 999) is clamped before any `send_bpm`/LED-rate call.
- **Live-safety note:** the strobe floor makes every later foreign-machine run safe-by-construction. The seam extraction must be behavior-preserving on macOS — diff the emitted event stream against a recorded session before/after.

### Phase 3 — Windows bring-up of the non-reader stack via ReplaySource ⭐ surfaces the MIDI blocker
- **Why:** proves *everything around the reader* is portable **without** waiting for the Windows reader RE. Decouples from the top Windows blocker.
- **Deliverable:** CI matrix builds a Windows `--onedir` bundle; run it on a real Windows 11 machine driving the **real rig** from a `ReplaySource`. Resolve the **virtual-MIDI-port** decision (loopMIDI bundling vs Windows MIDI-backend variant); route filepath resolution to the DB/ANLZ path (no `lsof`); fix the per-OS DB/temp/appdata paths.
- **Files/areas:** CI workflow; `streamdeck/streamdeck_midi.py:431` + the SS look-selection MIDI open; `filepath_resolver.py` (Windows → DB/ANLZ only); path/appdata handling; `pyproject.toml` platform-gated deps.
- **Verify:** on Windows, replayed deck-state produces SoundSwitch rotation **and** look-selection over MIDI, laser MIDI, LED/Govee output. Confirm the frozen build's MIDI + a Govee cloud HTTPS call actually work (the two silent-frozen-build traps).
- **Live-safety note:** replay input means no live-mixing risk; but validate the strobe clamp fires on the Windows build too.

### Phase 4 — Version-resilience seam wiring + support policy
- **Deliverable:** finalize `FieldResolver` as the only version touch-point; keep the table baseline; document the §2.3 support policy + refresh path; confirm fail-closed (unknown build → no direct events → bridge runs, strobe floor still holds).
- **Files/areas:** `rb_offsets.py` behind `FieldResolver`; `make_rb_state_reader` path (`rb_state_reader.py:953`); docs.
- **Verify:** unit test — unknown version → inert reader, no crash, bridge still starts.
- **Live-safety note:** none beyond the strobe floor; degraded lighting on an unknown build is acceptable per locked constraint 3.

### Phase 5 — Windows real-reader integration (BLOCKED on reader spec)
- **Deliverable:** swap `ReplaySource` for the real Windows `ProcessMemorySource` + Windows `FieldResolver` data once the reader spec delivers them. Validate the per-host authorization UX on a foreign Windows machine.
- **Blocked by:** the reader spec (Windows field data + authorization). This plan's job ends at defining the interface it plugs into.

**Windows clean-first-launch signing** is a parallel, optional track (§3.4) — cheap OV/cloud or Certum-open-source signature for legitimacy; do **not** gate the phases on clearing SmartScreen (likely unachievable for a low-volume tool).

---

## 6. Unknowns + readiness verdict

**Verdict: `READY WITH GAPS` for Codex.** Phases 1–4 are executable now (Phase 1 needs a $99 Apple account; Phase 3 needs a Windows 11 machine + the rig). Phase 5 is blocked on the reader spec.

**Blocking gaps (highest first):**
1. **`NOT READY` — Windows field data does not exist.** Top Windows blocker; reader-spec deliverable. Phases 1–4 are designed to progress *without* it; Phase 5 needs it. `unknown` until the reader spec runs.
2. **`NOT READY` — foreign-Mac memory authorization under a signed/notarized build.** See §7. Reader-spec territory, but it *intersects* this plan's signing work. **Can only be settled on real hardware** — Brandon's Mac (Phase 1) then a live foreign Mac.
3. **⚠ `READY WITH GAPS` — Windows virtual MIDI.** python-rtmidi can't self-create virtual ports on Windows; the SS look-selection + Stream Deck paths depend on them. Decision + validation in Phase 3. `assumed` a loopback driver (loopMIDI) or a real-port variant resolves it; **unproven on Windows**.
4. **`READY WITH GAPS` — Windows clean first launch.** SmartScreen reputation may be structurally unreachable for a low-volume tool; signing buys legitimacy, not a guaranteed wall-free launch. Not a blocker (worst case: one "Run anyway" click) but set expectations.

**Unknowns settleable only on real hardware / a live foreign host:**
- Does today's reader still attach from a packaged (ad-hoc) build? (Phase 1, Brandon's Mac.)
- Does the whole output stack — especially MIDI look-selection — run on real Windows? (Phase 3.)
- Does the per-host authorization actually work on a machine Brandon doesn't own? (reader spec + a live foreign Mac.)
- Does a plain USB Finder-copy avoid quarantine in practice? (`xattr -l` on a target Mac.)

---

## 7. Critical finding for the reader-spec handoff (⚠ read before writing the reader spec)

`confirmed` (Apple docs, via signing research): **`com.apple.security.cs.debugger` + notarization does NOT, by itself, grant a hardened app read access to another process's memory on a stock SIP-enabled Mac.** Apple's own docs: a debugger-entitled app "can't get the task ports of processes that don't have the Get Task Allow entitlement, and that are therefore protected by SIP." Rekordbox, being notarized, won't ship `get-task-allow`; and notarization *forbids your own app* from shipping it. So the entitlement passes notarization cleanly (`assumed`: it's a self-service checkbox, notarization is an automated scan) but the *access* comes from a **separate** authorization path — the brief's "per-install, admin-gated setup step."

**Why the reader works today** is therefore the crux the reader spec must nail down (`unknown` from this plan's read — it's reader-spec scope): today's reader runs unsigned/dev-mode, and its memory access comes from that admin-gated grant, **not** from being unsigned per se. The open question — and the reason Phase 1 exists — is whether that same grant still lets a **signed + Hardened-Runtime + notarized** bridge attach. **Do not assume today's dev-mode behavior carries over to the packaged build.** This is a feasibility risk, not paperwork.

**Handoff to the separate reader/RE spec — named dependencies this plan does not design:**
- **Per-host authorization mechanism** (macOS admin-gated grant; Windows equivalent) — how it's applied, re-applied on RB update, and its UX/reliability on a machine Brandon doesn't own. **Top operator-experience risk.** Must be validated against a **signed+notarized** macOS build (this plan's Phase 1 is the first checkpoint).
- **Windows field data** — the per-version `FieldSet` for Windows x64 (the Windows analogue of `rb_offsets.py`). Does not exist. **Top Windows blocker.**
- **Version-adaptive lookup mechanism** — if resilience against unseen builds is wanted, the signature/pattern-scan that finds fields without pre-analysis. This plan defines only the `FieldResolver` interface it must satisfy (§2).

The reader spec should be authored *after* this plan is accepted, using the three interfaces in §1.2 and the Phase-1 result as its feasibility gate.

---

### Registration note (not part of the deliverable)
This doc lives in `docs/plans/active/` per the brief. To make it *authoritative* under AGENTS.md §9, it must also be listed in `docs/status/active_work_registry.md` and pass the §8 doc checks — I did **not** modify the registry (out of the "produce the plan only" scope). Flagging it as a one-line follow-up if you want it tracked as active work.
