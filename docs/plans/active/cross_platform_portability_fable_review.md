---
doc_status: current
truth_level: review
last_verified_date: 2026-07-04
validation_scope: >
  Fable 5 adversarial review + creative expansion of cross_platform_portability_plan.md, and its
  composition ruling against usb_bridge_launcher_design.md. Desk review only: code claims verified
  against HEAD 7aef68f on 2026-07-04 (first-hand reads + one read-only sweep, load-bearing sweep
  claims re-verified directly); external claims web-verified against primary sources 2026-07-04.
  No code, config, runtime, or hardware touched. Line numbers cited here will drift — this repo
  moved the same day the plan was written; treat symbols as the durable anchors.
work_status: delivered
relates_to: cross_platform_portability_plan.md, usb_bridge_launcher_design.md
---

# Fable 5 review — cross-platform portability plan

## Verdict first

**Part 1 verdict: `PASS WITH REQUIRED FIXES`.**
**Part 3 verdict: the two docs COMPOSE — no foreclosure found — but need five specific stitches.**

The plan's skeleton is right and most of its research is genuinely solid (10 of 12 external packaging/signing claims verified against primary sources, several with exact dates). What fails is precisely the two places the review brief told me to push:

1. **The strobe floor (§4) is insufficient as specified** — both clamps, for different reasons. Clamp #1 cites the wrong code sites and misses the live-BPM ingress family entirely (the path most exposed to garbage memory reads). Clamp #2's "one clamp helper at the emit boundary" has no such boundary to live at — strobe rate is distributed across six pattern functions as a pure function of the beat clock. And the "club cap ~15–25 Hz" option it offers the operator **is the peak seizure-provocation band**, not a middle ground (Fisher et al. 2005; HSE's event-industry number is ≤4 flashes/sec).
2. **The seam (§1) is under-counted** — the "five primitives, one consumer" story misses `live_bpm.py` (nine `rb_memory` imports including objc-zone scanning the proposed Protocol can't express), two additional independent attach sites, and the fact that the bridge's own entrypoint (`__main__.py:24` `import fcntl`) cannot even be imported on Windows. "The bridge above the seam needs zero changes to run on Windows" is false as written — the falsifiers are small, but they are exactly the untracked OS couplings the plan claimed didn't exist.

Plus one finding neither doc saw coming: **the plan's own §3.5 advice ("format the stick exFAT") breaks its own §3.1 deliverable** — PyInstaller's docs state onedir bundles "can only be moved or copied to a filesystem that supports symbolic links," and exFAT has none. The `.app` needs a DMG carrier on the stick. This hits the launcher's Milestone 1 ("run it off the stick") directly.

Everything below is evidence for those three sentences, then the fixes, then ideas that make the plan better, then the composition ruling.

---

## Part 1 — Adversarial review (severity-first)

### R1 · HIGH · §4.3(1) — the BPM source clamp misses the live-BPM/arm ingress family, so its guarantee is false

**Location:** plan §4.3(1); real code `state_manager.py:1298-1310, 1960, 2369`, `autoloop_controller.py:111-122, 144-148, 164`, `state_manager.py:3671-3683`.

**The flaw.** The plan says: clamp `d.meta.bpm` at "the `BPM_UPDATE` handler (`state_manager.py:3304`) and the track-load setter (`:2363`)", and claims "because `StateManager` is the sole fan-out owner, this one clamp bounds *every* downstream tempo." `confirmed` — three problems:

1. **Both cited lines are wrong.** `:3304` is the push-loop's position-read comment, not a BPM handler; the actual `Ev.BPM_UPDATE` handler writes `d.meta.bpm = new_bpm` at `state_manager.py:1310`. `:2363` is `last_arm_mono`; the scripted-arm meta write is `:2369`. A third `meta.bpm` write the plan never found: the filepath-resolved payload at `:1960`.
2. **The live-BPM-follow path never touches `d.meta.bpm` at all.** `autoloop_controller.py:111` takes `live_bpm_value(deck)` from `live_bpm.py`'s *own direct memory read*; the only sanity checks are `isfinite` and `> 0` (`:133`) — **no upper bound**. It lands in `os.pending_live_bpm` (`:122`), and the push loop then sends it (`self._sse.send_live_bpm_follow(active, pending_live_bpm)`, `state_manager.py:3673`), overwrites the outgoing tick `bpm` (`:3674`), seeds `os.autoloop_arm_bpm` (`:3675`) and `os.last_sent_bpm` (`:3679`). Clamping `meta.bpm` bounds none of this.
3. **The arm path is a second bypass.** `arm_bpm()` (`autoloop_controller.py:144-148`) returns the raw live value when available; `:164` writes it to `os.autoloop_arm_bpm`, which the push loop prefers over `meta.bpm` when armed (`bpm = os.autoloop_arm_bpm`).

The read-side `0 < bpm < 1000` filter the plan leans on (`rb_state_reader.py:690`, `confirmed`) guards only `rb_state_reader`'s own reads — not `live_bpm.py`'s, which is a separate reader with a separate chain.

**Why it matters for Brandon.** The live-follow path is *the* path a torn/garbage memory read on an unknown foreign build would ride into SoundSwitch's tempo clock during a live set — precisely the scenario the strobe floor exists for. As specified, the floor has a hole exactly where the risk is.

**Required change.** One clamp helper, applied at every tempo ingress into `OutputState`/the tick, not two `meta.bpm` writes: (a) the three `meta.bpm` writes (`:1310, :1960, :2369`); (b) the push-loop tick finalization (after `apply_live_bpm_follow`); (c) the pending-live apply block (`:3672-3683`) *before* `send_live_bpm_follow`; (d) `autoloop_controller.py:122` and `:164` (or equivalently `arm_bpm()`'s return). Add one parametrized unit test that feeds a 999-BPM value through **each ingress family** and asserts nothing downstream (send_bpm / send_live_bpm_follow / LED rate) sees it unclamped — see E7. Note `sound_switch_engine.py:57,66` are additional `send_bpm` call sites whose inputs must trace to clamped state.

### R2 · HIGH · §4.3(2)+§4.2 — the flash-rate ceiling has no single site to live at, and the offered "club cap" is the peak-hazard band

**Location:** plan §4.3(2); real code `govee_frame_renderer.py:276-282, 423, 460, 481, 492, 511`, `beat_sync_engine.py:174, 186-196`, `led_config.py:776-784, 449, 624-627`, `led_models.py:167-175`.

**The flaw, in three parts.**

1. **"One clamp helper at the emit boundary" assumes a rate variable that doesn't exist.** `confirmed`: flash generation is distributed. `_beat_strobe` computes `on = ((beat * subdivision) % 1.0) < duty` with subdivision hard-limited to {1,2,4,8} (`govee_frame_renderer.py:278-282`), and at least five other pattern functions carry hardcoded 16th-note strobes (`int(beat * 16.0) % 2` at `:423,:460,:481,:492`; `beat % 0.25 < 0.0625` at `:511`). All are pure functions of the continuous `beat` clock — the flash frequency is implicit in rendered frames, never computed as a number you can clamp. The enforceable identity is: **max flash Hz = clamped_BPM/60 × max subdivision (8)**. With the plan's suggested 220 BPM ceiling that is 29.3 Hz — comfortably inside the hazard band. So clamp #2 as described cannot be "landed" by Codex; it has to be respecified either as a derived constraint (pick `BPM_MAX` so that `BPM_MAX/60×8 ≤ MAX_FLASH_HZ`, which forces absurdly low BPM), or — correctly — as a shared limiter *inside* the strobe-pattern family that rescales subdivision when `bpm/60 × subdivision > MAX_FLASH_HZ`.
2. **The "operator decision: medical-safe 3 Hz vs a club cap ~15-25 Hz" framing is wrong on the medicine.** `confirmed` (primary sources): WCAG 2.3.1's general threshold is ≤3 flashes/sec; Fisher et al. 2005 (Epilepsia, the Epilepsy Foundation consensus review): "Frequencies of 15-25 Hz are most provocative, but the range is 1-65 Hz." **15–25 Hz is the peak of the sensitivity curve** — offering it as the "club" endpoint of a reasonable range invites the operator to pick the most dangerous number available. The defensible club-context anchor is UK HSE's event guide (HSG195 ¶614-615): "keep flicker rates at or below four flashes per second." The choice to present is **3–4 Hz (guidance-backed) vs. an explicit informed override**, with 15–25 Hz named as the band to *avoid*, not a menu option.
3. **The plan ignores a hard floor that already exists.** `confirmed`: `safety.allow_strobe` is a validated global + per-look boolean (`led_config.py:776-784`; per-look default *false* `:449`; realtime strobe effects require both to be true `:624-627`), alongside the validated 1–750 ms `max_strobe_duration_ms` (`:783`) the plan does cite. `allow_strobe=false` in a foreign-host profile is a zero-new-code kill switch stronger than any Hz clamp — see E1.

**Boundary honesty check (plan's own §4.3 caveat): correct and confirmed.** The bridge cannot bound SS-authored effect rates; clamping the fed tempo (R1, fixed) is the whole of the bridge's SS-side power. Laser strobe is scene/CC-selected, not bridge-rate-computed (`laser_config.py` safety classes include `strobe`; `confirmed` at the design level) — the plan's "lower risk, note it" stands.

**Ruling the brief asked for:** §4 as specified — **insufficient**. §4's *architecture* (bound the tempo at the source; add an absolute flash ceiling; accept SS-authoring as out of scope) — sound. The respec above + R1 makes it sufficient, and cheap.

### R3 · HIGH · §1.1-1.2 — the seam is real but under-counted: three attach sites, nine primitives, one un-importable entrypoint

**Location:** plan §1.1, §1.2(a), §5 Phase 2 files list; real code `live_bpm.py:24-33, 595-602, 1005-1020`, `rb_memory.py:1249-1260`, `rb_state_reader.py:229-237`, `__main__.py:24, 770-785`, `streamdeck/streamdeck_midi.py:16, 38, 55-66`, `validation_runner.py:130-140, 316-323`.

**What survives:** the seam *concept* is genuinely strong. `confirmed`: `rb_state_reader.py:48-55` imports exactly the five primitives + `PositionCache`; the chain walker is `struct.unpack` over bytes; `models.py` and `state_manager.py` have **zero** OS-specific code (verified by sweep across 17 pattern groups, load-bearing results re-checked first-hand); the offsets table is exact-match fail-closed (`rb_offsets.py:308-314`) into an inert reader (`rb_state_reader.py:953-967`). All as advertised.

**What the plan missed:**

1. **`live_bpm.py` is a third, unlisted consumer of `rb_memory` internals — and a wider one.** `confirmed`: it imports **nine** names (`live_bpm.py:24-33`), including `_objc_regions_from_vmmap`, `_scan_objc_zone`, and `_read_u64` — region enumeration and objc-zone scanning that the proposed `ProcessMemorySource` (find_pid / attach / module_base / read) **cannot express**. It runs its own attach/session lifecycle (`:595-602`, `os.kill(pid, 0)` liveness at `:1010`). Even `RBMemoryReader`'s own attach captures objc regions (`rb_memory.py:1258`), so "attaches through the *same three* primitives" was under-stated for the file the plan did cite.
2. **Three independent attach call sites**, not one: `rb_memory.py:1249-1260`, `live_bpm.py:595-602`, `rb_state_reader.py:229-237` (plus the two `probe_*.py` dev CLIs, non-runtime). The Phase 2 hoist must intercept all three; the plan's files list (`reader_backend.py`, `reader_macos.py`, thin edits to `rb_state_reader.py:48-56`) **omits `live_bpm.py` entirely**, which means Phase 2 as scoped would ship with live-BPM still importing private mac internals — silently mac-only, or broken, after the "seam extraction."
3. **"Everything above the seam is pure, portable Python" is falsified by the entrypoint itself.** `confirmed`: `__main__.py:24` does a module-level `import fcntl` (Unix-only stdlib) for the single-instance lock (`fcntl.flock`, `:778`, on hardcoded `/tmp/rb_ss_bridge_v2.lock`, `:770`). On Windows this is an `ImportError` before `main()` runs. Same pattern in `streamdeck/streamdeck_midi.py:16,55-66`. These are the **enforcement mechanism of the one-process invariant** (AGENTS.md §6) — so the invariant's implementation (flock ×2, `pgrep` in the watcher/menubar/`validation_runner.py:316-323`, `os.kill(pid,0)` ×3) is itself platform-specific and currently owned by no plan section. Windows needs a named owner for "exactly one bridge" (e.g. `msvcrt.locking` or a bound-socket lock, plus a `tasklist`-side check).

**Required change.** §1.2(a) grows two members (roughly `regions(handle) -> list[Region]` and whatever minimal scan support `_scan_objc_zone` reduces to — or live-BPM is explicitly declared a macOS-only capability behind its own smaller seam, degraded elsewhere; either is honest, pick one). Phase 2's files list adds `live_bpm.py`. A new §1.3 bullet owns "single-instance + process-liveness mechanism, per OS." The §0 seam row's `READY` stands only after these are folded in.

### R4 · HIGH · §3.5 vs §3.1 — the exFAT stick breaks the macOS `.app` the plan builds

**Location:** plan §3.5 ("Format the stick exFAT"), §3.1; launcher §3.1, §7.1; PyInstaller docs.

**The flaw.** `confirmed` (primary source): PyInstaller ≥6.0 generates macOS bundles whose `Contents/Resources` ↔ `Contents/Frameworks` trees are **cross-linked via symlinks** (6.0.0 changelog, done for codesign compliance), and its docs state onedir builds "can only be generated on a filesystem that supports symbolic links. Similarly, they **can only be moved or copied to a filesystem that supports symbolic links**." exFAT (the plan's own stick format, needed so Windows can read the stick) has no symlinks. A raw drag-copy of the `.app` onto the stick produces a broken bundle — likely "damaged app" / dyld failures on the foreign Mac. Note zip-extraction *onto* the stick can't fix this (the extraction target still lacks symlinks); the artifact on exFAT must be a **container**.

**Why it matters.** This is the first thing that happens in the whole USB story — launcher Milestone 1 is literally "run it off the stick." Both docs would have discovered this at M1 for $0, but it invalidates written deliverable text in both, and the fix changes the stick layout.

**Required change.** Ship the Mac slice as a **DMG on the exFAT stick** (`hdiutil create -format UDZO` in CI — one line): DMG mounts as its own filesystem, symlinks intact, read-only by construction (which the launcher's scratch-folder design already assumes), double-click UX preserved (open DMG → app). Stick layout: exFAT volume holding `Mac/Bridge.dmg` + a future `Windows/bridge/` onedir folder (onedir-of-plain-files is exFAT-safe on Windows). A symlink-preserving zip (`ditto -c -k --keepParent`) extracted **to the host** is the fallback. Both docs need the carrier decision; see Part 3 stitch #5.

### R5 · MED-HIGH · §3.3 + launcher §2(b) — the packaging story is built on an untrue manifest and a one-process assumption

**Location:** `pyproject.toml` (whole file), plan §3.3, launcher §2(b)/§3.2; `scripts/ss_bridge_watcher.sh:35-37, 55-68`, `streamdeck/streamdeck_midi.py:28-30`, `enttec_dmx_pro.py:84-85`, `soundswitch_midi_input.py:444`.

**The flaws.**

1. **Undeclared runtime dependencies.** `confirmed`: `pyproject.toml` declares mido, pyobjc-Cocoa (darwin-gated), pyrekordbox, python-osc, zeroconf — and **not** `python-rtmidi` (imported directly at `soundswitch_midi_input.py:444`; mido≥1.3 does *not* pull it), **not** `pyserial` (`enttec_dmx_pro.py:84-85`, its own comment says "optional runtime dep"), **not** the pip `streamdeck` package, **not** `Pillow` (both at `streamdeck/streamdeck_midi.py:28-31`). A CI build that installs from project metadata produces a bridge with **no MIDI** — which on this rig means no SS look-selection, no laser MIDI, no Stream Deck. Today's source runs work only because the operator's venv was hand-provisioned.
2. **The `streamdeck/` subpackage isn't in `[tool.setuptools] packages` at all** — `pip install .` drops it silently.
3. **Plan §3.3's "hidapi/libusb only matter if something does raw USB/HID" dismisses its own Stream Deck subsystem** — the `streamdeck` pip package *is* raw HID and needs the hidapi native library collected into the bundle on both OSes.
4. **The shipped system is multi-process and no packaging section says so.** `confirmed`: the watcher supervises a **second** long-lived process (`streamdeck_midi.py`, spawned at `ss_bridge_watcher.sh:59-63`, own lockfile, own log), beside the menubar and the on-demand pad servers. The plan packages "the bridge"; the launcher's §2(b) parity bar *requires* Stream Deck but its §3.2 runner design speaks only of "exactly one bridge." Someone has to spawn and supervise that child in the bundle world.

**Required change.** A Phase-1 step 0: make `pyproject.toml` truthful (declare rtmidi/pyserial/streamdeck/Pillow with appropriate platform/extra gating; add the `streamdeck` package) — or explicitly state builds are source-tree-driven and metadata is dead, and say which. Extend the launch-profile/runner design to enumerate child processes (bridge, streamdeck, menubar; pads optional). Correct §3.3's hidapi line.

### R6 · MED · §5 Phase 2 — the verification method doesn't exist, and "nearly free" oversizes the replay promotion

**Location:** plan Phase 2 deliverable (b) + verify bullet; `session_recorder.py:77-92`, `session_replayer.py:10-11, 54, 122, 137, 196-200, 232-242, 251-253`.

**The flaw.** Phase 2's verify says "diff the emitted event stream against a recorded session before/after." `confirmed`: the recorder captures StateManager **input** (`record_event`/`record_position`), and the replay side is `ReplayHarness` — which constructs its own StateManager with a **`Mock()` output** (`:196-200`) and drives **virtual time** by monkey-patching `state_manager.time.monotonic` (`:251-253`, stepping `mono_t` at `:232-242`). There is no recorded-*output* stream and no live-pacing replay source today. So (a) the stated before/after diff has no harness to run on, and (b) "promoting that offline test helper to a runtime-selectable source" is not "nearly free": the promotion needs wall-clock pacing, the real output stack, and injection shims wired into the real StateManager. What *is* free: `CapturedSession.from_jsonl` (`:54`), the event/position decoders (`:99`), and the `ReplayPositionCache`/`ReplayLiveBPMService` shims (`:122`, `:137`) — the data layer is done; the runtime adapter is real but small.

**Required change.** Respecify Phase 2's verification as: run `ReplayHarness` over a recorded session with a *capturing* fake output before and after the seam extraction and assert identical output-call sequences (deterministic by construction — virtual time is a feature here, not a bug). Resize Phase 2(b) honestly ("data layer exists; write the pacing adapter"). Phase 3's premise (drive the real rig on Windows from replay) survives unchanged.

### R7 · MED · §6/§7 — not updated for the declined-notarization decision the plan itself records

**Location:** plan §6 (verdict + gap 2), §7 (crux paragraph), vs. §0 decision block and Phase 1.

**The flaw.** `confirmed` by internal reading: §6 still says "Phase 1 needs a $99 Apple account" — Phase 1 as rewritten is the $0 ad-hoc path. §6 gap 2 and §7's crux are still phrased as "foreign-Mac memory authorization under a **signed/notarized** build" / "whether that same grant still lets a **signed + Hardened-Runtime + notarized** bridge attach" — with notarization declined there is no Hardened Runtime and no notarization; the §0 decision block even (correctly) notes this *removes* a §7 constraint. The residual Phase-1 question is narrower and should be stated as such: **does the admin-granted memory access survive the jump from dev-mode source runs to a PyInstaller-frozen, ad-hoc-signed `.app`?** (Different binary identity, bundled interpreter — still a real question; reader-spec mechanics remain out of scope here.)

**Required change.** Rewrite §6's Phase-1 cost note and gap 2, and §7's crux sentence, into the ad-hoc world. Keep the old signed/notarized phrasing only inside the §3.4 "optional reference" block.

### R8 · MED · §1.3/§6 gap 3 — Windows MIDI research is one product behind, and the MIDI surface is wider than "virtual-port creation"

**Location:** plan §1.3 first bullet, §5 Phase 3, §6 gap 3; `mtc_reader.py:30, 67-82`, `midi_output.py:189, 458`, `soundswitch_midi_input.py:88, 444-454`, `streamdeck/streamdeck_midi.py:530`.

**What's right:** `confirmed` (primary source): python-rtmidi's WinMM backend raises `NotImplementedError` on virtual-port creation — the blocker is real. loopMIDI is a kernel-mode driver, admin install, per-machine — usable but **not stick-portable**, license free for private use (commercial by permission). teVirtualMIDI's SDK forbids redistribution without written clearance — correctly not on the table.

**What's missed:** **Windows MIDI Services** is now in-box on the plan's own locked target. `confirmed` (microsoft.github.io/MIDI + Windows blog 2026-02-17): shipped in retail Windows 11 24H2/25H2/26H1; **built-in loopback endpoints creatable in the in-box MIDI Settings app with no third-party driver**; classic WinMM apps (i.e. python-rtmidi/mido unchanged) see those endpoints because WinMM is repointed at the new service. There is no documented Python `Windows.Devices.Midi2` binding, so the sane recipe is: one-time GUI creation of a loopback pair, bridge opens it **by name** — which is exactly the bridge's existing mac pattern (named IAC bus). loopMIDI remains the fallback for pre-24H2 machines. This flips §1.3's framing from "hard blocker needing a bundling decision" to "per-OS port-naming config + a runbook step," and Phase 3's decision is largely pre-made.

Also under-counted: item (d) covers only virtual-port *creation* (`streamdeck_midi.py:530`), but three more independent MIDI call sites open **existing named ports** (`mtc_reader.py:82` input; `midi_output.py:189,458` laser out; `soundswitch_midi_input.py:444-454` raw rtmidi, bypassing mido) — and the literal `"IAC Driver Bus 1"` is hardcoded **five times across runtime files with no shared constant** (`mtc_reader.py:30`, `soundswitch_midi_input.py:88`, `soundswitch_pack.py`, `soundswitch_pack_loader.py`, `soundswitch_pack_verifier.py`). Phase 3's "streamdeck_midi + the SS look-selection open" files list is short by three call sites and needs a single port-name config point first.

### R9 · LOW-MED · §3.5 — the per-OS path surface is ~10× what the plan names

**Location:** plan §3.5 (names only `/tmp/bridge.log`); sweep results, spot-verified.

`confirmed`: hardcoded per-OS paths in runtime code include: `/tmp/rb_ss_bridge_v2.lock` (`__main__.py:770`), `/tmp/rb_ss_bridge_v2_status.json` + `/tmp/rb_ss_bridge_v2_commands.jsonl` (`runtime_status.py:16-17` — the whole runtime-command surface is a growing-file tail poll, mechanism itself portable), `/tmp/rb_ss_bridge_v2_logging.json` (`__main__.py:1797`), `/tmp/rbss-session-*.jsonl` (`:1531`), `/tmp/rbss_os2l_inject.jsonl` (`os2l_injector.py:22`), `/tmp/rbss_artnet_truth_frames.jsonl` (`artnet_truth.py:30`), `/tmp/govee_h612d_{devices,scenes}.json` (`govee_runtime_sender.py:26-27`), `/tmp/streamdeck_midi.lock` + palette state (`streamdeck_midi.py:38,42`); `~/Library/Pioneer/rekordbox/master.db` hardcoded **twice independently, no shared constant** (`config.py:20`, `scripted_tracks.py:54`); `~/Library/Application Support/...` (`spectral_cache.py:17-18`, watcher `:34`); `~/Music/SoundSwitch` roots (`ss_library_scanner.py:30,74-95`); `/System/Library/Fonts/Helvetica.ttc` (`streamdeck_midi.py:242`); serial `cu.*` naming convention (`enttec_dmx_pro.py:104` + `enttec_port` config). And the one that isn't even OS-portability: **`/Users/bbui` baked into `bridge_menubar.py:35,54`** — the menubar breaks for a different *user account* on the same Mac. Meanwhile there are **zero `sys.platform`/`os.name`/`platform.system()` branches anywhere in the repo** (verified) — §1.3(e)'s "per-OS paths" describes paths that need to *become* per-OS; none are yet.

**Required change:** Phase 3's "path/appdata handling" bullet should point at one `paths.py`-style module (single choke point, the same shape as the launch-profile idea) and enumerate this list, rather than implying `/tmp/bridge.log` is the job. The `/Users/bbui` menubar hardcodes belong on the launcher's M1 list regardless of Windows.

### R10 · LOW · line-citation rot + a stale registration note

`confirmed`: beyond R1's wrong clamp sites, several plan cites drifted the same day it was written (`streamdeck_midi.py:431`→`:540` — both docs cite 431; `send_bpm :3623,3630`→`:3627-3637`; `send_beat :3717`→`:3722-3723`; recorder `:77,92`≈`:78,92`). Four sessions were working this repo today; raw line numbers in plans rot in hours here. Recommend plans cite symbol + short quote (lines as hints only). Also the plan's closing "Registration note" says the registry was *not* updated — stale: both docs are registered (AWR-120, AWR-122, `docs/status/active_work_registry.md:28-29`, marked "Unreviewed"). This review discharges the "unreviewed" caveat for AWR-120 once its fixes are folded in.

### R11 · LOW · external-claims polish (the rest all verified)

Verified against primary sources, matching the plan: PyInstaller no-cross-compile + CI-matrix path; onedir/onefile AV rationale; ad-hoc-sign-by-default + Apple-silicon mandatory signing; mido hidden-import; certifi/`SSL_CERT_FILE` hook removal (hooks-contrib #332, removed 2021.4); EV/SmartScreen reversal with exact dates (Feb 2024 policy, Aug 2024 OID removal — Microsoft: "Paying a premium for EV solely to avoid SmartScreen warnings is no longer justified"); SmartScreen reputation being per-file telemetry with no manual boost; `macos-latest`=arm64 since 2024; quarantine only set by quarantine-aware apps. Three refinements: (a) **"Azure Artifact Signing" is the correct current name** (lineage Azure Code Signing → Trusted Signing → Artifact Signing; FAQ updated 2026-06-22), ~$9.99/mo basic, individual developers currently **US/Canada only** (orgs also EU/UK) — plan's parenthetical is accurate today, keep its "verify at purchase" hedge; (b) Certum open-source pricing is option-dependent (~€49+VAT/yr cloud, or card-kit ≈ plan's figure) — plan's number is the right neighborhood, not exact; (c) macOS Tahoe (26) has further tightened bypasses (`spctl --master-disable` / bare `xattr -d com.apple.quarantine` now require System-Settings confirmation) while the Settings "Open Anyway" path the plan relies on **still exists** — the $0 path holds today, but Apple ratchets this every release; a foreign Mac likely runs latest macOS, so re-verify each fall. PyInstaller supports Python 3.14 since 6.15.0 (local dev is 3.14, CI is 3.11 — pin the build Python in the `.spec`/CI).

### What the plan got right (so the knives have context)

The seam concept and its fail-closed version policy are correct and verified at the code level; `models.py`/`state_manager.py` purity is real; the replay-at-the-right-boundary insight is genuinely good (the data layer already exists); the packaging research is unusually well-sourced for a plan (10/12 spot-checks verified, several with exact dates); "don't gate on SmartScreen" and "don't buy EV" are both correct and save money; the notarization-declined consequence analysis in §0 is right (including that it *lowers* §7 risk); numpy/scipy optionality confirmed (`pyproject` extras; the only numpy import is lazy, `audio_spectral_features.py:36`); §1.4's Pi non-foreclosure note is accurate.

---

## Seam completeness — the file-by-file answer (brief criterion 2)

Every OS-specific touchpoint found in the runtime bridge (sweep across 17 pattern groups + full-file reads; load-bearing rows re-verified first-hand). **Plan bucket** = covered by the plan's claimed surface (a) five primitives / (b) version detect / (c) lsof / (d) virtual MIDI / (e) per-OS paths.

| File | OS-specific content | Plan bucket | Status |
|---|---|---|---|
| `rb_memory.py` | ctypes/mach primitives, pgrep, vmmap (`:54-141`); own attach `:1249-1260`; `os.kill(pid,0)` `:1070` | (a) | covered, but attach-site count and `os.kill` unlisted |
| `rb_state_reader.py` | imports 5 primitives `:48-55`; **own attach** `:229-237` | (a) | covered; 2nd attach site unlisted |
| `live_bpm.py` | **9 rb_memory imports** incl. objc-zone scan `:24-33`; **own attach** `:595-602`; `os.kill` `:1010`; Info.plist version detect `:799-820` | (b) only | **MISSED** (R3) except version-detect |
| `rb_offsets.py` | macOS-arm64 offsets **data** | (a)-adjacent | covered by §2 (data, not code — correctly routed to reader spec) |
| `filepath_resolver.py` | pgrep `:78-85` (re-implemented), lsof `:86-90,481-556` | (c) | covered |
| `__main__.py` | **`import fcntl` `:24`**, flock lock + `/tmp` lock path `:770-785`; signals (SIGHUP correctly guarded `:1903-1905`) | — | **MISSED** (R3) |
| `mtc_reader.py` | mido `open_input`, hardcoded "IAC Driver Bus 1" `:30,82` | (d)-adjacent | **MISSED** as written — open-by-name, not virtual-create (R8) |
| `midi_output.py` | mido `open_output` by name `:189,458` | (d)-adjacent | **MISSED** as written (R8) |
| `soundswitch_midi_input.py` | raw `rtmidi.MidiIn` `:444-454`; IAC literal `:88` | (d)-adjacent | **MISSED** as written (R8) |
| `soundswitch_pack{,_loader,_verifier}.py` | "IAC Driver Bus 1" literals in crosswalk logic | — | **MISSED** (R8; constant-ize) |
| `streamdeck/streamdeck_midi.py` | `virtual=True` `:540` = plan's (d); **fcntl `:16,55-66`**; HID/Pillow deps `:28-31`; `/tmp` + Helvetica paths | (d) partial | (d) covered; rest **MISSED** (R3/R5/R9) |
| `runtime_status.py` | `/tmp` status+commands paths `:16-17`; POSIX 0o600 chmod (already OSError-wrapped) | (e) partial | paths under-enumerated (R9); mechanism portable |
| `logging_manager.py` | `/tmp` control-file default `:310`; stdout-only handler (bridge.log is watcher-side redirection) | (e) partial | covered-ish; plan's "repo writes /tmp/bridge.log" is actually the watcher |
| `config.py` / `scripted_tracks.py` | RB DB path hardcoded ×2, no constant | (e) | covered in principle; duplication unlisted (R9) |
| `spectral_cache.py` | `~/Library/App Support` default; POSIX dir-fsync (silently degrades on Windows) | (e) partial | minor; note in Phase 3 |
| `ss_library_scanner.py` | `~/Music/SoundSwitch`, `~/Desktop`, `~/Downloads` roots | (e) | covered in principle (R9 list) |
| `enttec_dmx_pro.py` | pyserial (undeclared dep); `cu.*` device naming | — | **MISSED** (R5/R9 — config value is per-OS) |
| `govee_lan_discovery.py` | multicast + SO_REUSEPORT already guarded | — | fine as-is (portable) |
| `govee_realtime_transport.py` / `artnet_truth.py` / `os2l_injector.py` | plain UDP; `/tmp` sidecar paths | (e) | paths only (R9) |
| `govee_runtime_sender.py` | HTTPS cloud (certifi trap — plan covers); `/tmp` cache paths | (e)+§3.3 | covered + R9 paths |
| `validation_runner.py` | pgrep-based singleton/process checks `:130-140,316-323` | — | **MISSED** (R3 — invariant enforcement) |
| `scripts/ss_bridge_watcher.sh` | bash, pgrep/pkill/kill -0, osascript/Terminal.app, Homebrew python path, env profile, streamdeck child spawn | — | **out-of-plan operator layer** — launcher owns the Mac port (§3.2); Windows equivalent owned by no one (Part 3 #4) |
| `scripts/bridge_menubar.py` | AppKit/PyObjC; pgrep/pkill/launchctl/osascript/`open`; `os.getuid`; **`/Users/bbui` hardcodes `:35,54`** | — | launcher extends it (its §3.4); hardcodes unlisted anywhere (R9) |
| Zero-hit files (verified) | `state_manager.py`, `models.py`, `active_deck_resolver.py`, `beat_sync_engine.py`, all `led_*`/`govee_frame_renderer`/`laser_director`/`laser_executor`, `sound_switch_engine.py`, `session_recorder/replayer`, 25+ more | — | plan's purity claim **holds** for the event/lighting core |
| Dev-only (non-runtime) | `probe_deck2.py`, `probe_live_bpm.py` (4th/5th attach sites), `scripts/record_session.py` (`os.execvpe`), `direct_rt_groove_chase.py` | — | correctly out of scope; note in reader spec only |

**Bottom line for criterion 2:** the plan's surface (a)–(e) is real but captures roughly the *reader* half. The missed half clusters into five nameable items — live-BPM's wider primitive set (R3), single-instance/process-liveness enforcement (R3), MIDI open-by-name + port-name constants (R8), the undeclared native deps (R5), and the path inventory (R9) — plus the operator layer the launcher owns on macOS and nobody yet owns on Windows.

---

## Part 2 — Creative expansion (ranked; solo-hobby ethos, each idea priced)

**E1 · adopt now — a "travel profile," not scattered mitigations.** One switch (a second profile in the launcher's own `launch_profile` module) that flips the bridge into foreign-host posture: `safety.allow_strobe=false` unless the operator re-enables it that night (existing validated config, `led_config.py:776-784` — zero new enforcement code), flash ceiling at the HSE 4 Hz default (R2's respec knob), session recording ON to a small rotating dir (recorder already env-gated, `session_recorder.py:from_env`), and the unknown-build banner (E5). *Why it earns it:* converts five one-off decisions into one operator-visible mode; the launcher already needs the profile module, so marginal cost is a dict + docs. *Cost:* small config/glue + a few tests.

**E2 · adopt now — make Windows MIDI Services the primary Windows MIDI path.** Pre-makes Phase 3's "decision needed": in-box loopback endpoints on Win11 24H2+ (the locked target), classic-API visible, no driver; loopMIDI only as pre-24H2 fallback; teVirtualMIDI rejected (redistribution license). *Cost:* rewrite two plan paragraphs + a runbook step ("create loopback pair in MIDI Settings, name it X") + the R8 port-name config point. *Why:* deletes the scariest-sounding Windows blocker for ~zero code.

**E3 · adopt now — DMG carrier on the stick** (R4's fix). *Cost:* one `hdiutil` CI line + doc edits in both docs. *Why:* without it, M1 fails on the first double-click.

**E4 · adopt now — merge portability Phase 1 into launcher Milestone 1.** They are the same experiment (package today's bridge, run on Brandon's Mac, prove reader+rig) with different acceptance bars; run it once under the launcher's stricter §2 parity bar, with Phase 1's attach/one-process checks folded in as line items. One `.spec`, one experiment, two docs cite it. *Cost:* doc edit. *Why:* avoids literally duplicated work and two drifting acceptance bars (see Part 3 #1).

**E5 · adopt now — unknown-build canary in the operator's face.** Today an unsupported RB build logs once (`rb_state_reader.py:962-966`) and the bridge silently degrades. Surface it where Brandon looks: a status field (`runtime_status.py` already publishes JSON the menubar polls) → menubar line "RB 7.2.15 not in table — direct reads off, lighting degraded." *Cost:* one status field + one menubar row. *Why:* on a friend's laptop, the difference between "bridge is broken" and "this RB build isn't mapped, everything else is fine" is the whole night's debugging budget. Complements §2.3's fail-closed policy with fail-*visible*.

**E6 · adopt now (with R1) — tempo-ingress clamp contract test.** One parametrized unit test enumerating every tempo ingress family (BPM_UPDATE, filepath payload, scripted arm, live-follow pending, arm-time live) asserting the clamp holds downstream. *Why:* R1 happened because ingress points multiplied past the doc; a test is the only enumeration that can't rot. *Cost:* ~1 test file.

**E7 · adopt later (after R3 fixes) — Windows import-smoke CI job.** `windows-latest` job that just imports the portable core (`state_manager`, `models`, the LED/laser/govee stack) + runs the platform-agnostic unit subset. *Why:* while Windows is deferred, this is the cheap tripwire that stops new `fcntl`-class couplings from accumulating — it enforces the seam continuously instead of re-auditing later. *Cost:* ~10 CI lines, but blocked until `__main__`/streamdeck locks are portable-guarded (R3), so *later*.

**E8 · adopt later — foreign-host replay smoke as the standard first move.** Phase 3 already invents "drive the real rig from `ReplaySource`" for Windows; generalize it: on *any* new host (including a friend's Mac), step 1 is replaying a recorded set against real outputs — full output-stack proof with zero Rekordbox/reader dependency, strobe floor already active. *Cost:* free once Phase 2(b) lands; a runbook paragraph. *Why:* separates "host can drive the rig" from "host can read RB" — the two failure domains Brandon would otherwise debug entangled, live.

**E9 · explored and rejected — version-adaptive FieldResolver now.** The plan already routes it to the reader spec; agree, and go further: with fail-closed + E5's banner + "keep an old RB build installed" (§2.3), the table is not just an acceptable v1 but arguably the *permanent* right answer for a solo rig; adaptive lookup is RE-heavy resilience against a risk the operator can route around. Revisit only if table-lag actually bites twice.

**E10 · explored and rejected — Nuitka / embeddable-Python as primary packaging.** Plan's onedir choice is the evidence-backed one (P1-P5 verified); embeddable stays the documented AV-fallback. No change.

**E11 · explored and rejected — Python-native Windows virtual-MIDI (WinRT `Windows.Devices.Midi2`).** No documented Python binding exists (verified); GUI-created loopback + open-by-name (E2) achieves the goal with zero exotic code. Revisit only if Microsoft ships Python projections.

**E12 · adopt now — deletions (cut list).** Per the ethos, cuts are first-class: (a) trim §3.4's four-step Developer-ID/notarization walkthrough to two lines + links — it's marked "optional reference" but is the plan's longest section and invites ceremony against a declined decision; (b) collapse the EV/HSM/CA-pricing detail to "signing is optional; if ever wanted: Artifact Signing ~$120/yr (US/CA individuals) or Certum OSS if public-source; EV is dead for SmartScreen" + links; (c) §2.2's table-vs-adaptive argumentation compresses to its §2.3 conclusion (the reasoning now lives in the reader spec's court). Net: the plan gets ~a page shorter and harder to misread as "we should go buy certs."

---

## Part 3 — Relationship ruling: portability plan × USB launcher design

**Ruling: they compose as intended — launcher = the Mac slice executing this plan's Mac path; plan = the superset holding the seam, version resilience, and deferred Windows. I found no decision in either that forecloses the other.** `confirmed` points of alignment: notarization decision identical (plan §0 ↔ launcher §1 locked decisions); packaging identical (PyInstaller `--onedir --windowed` ad-hoc, plan §3.1 ↔ launcher §3.1); write-locations policy compatible (plan §3.5 appdata/temp ↔ launcher §4 scratch-and-wipe); one-process invariant carried by both (launcher §3.2); the launcher's out-of-scope list (§8) correctly defers Windows and the memory-grant mechanism to exactly the places the plan assigns them (§7 handoff). The launcher's `StartOnMount` caveat and `assumed` labels are honest and stay standing (build-time verify).

**Five required stitches (specifics, per section):**

1. **Phase 1 ≡ Milestone 1 — merge, don't run twice.** Plan §5 Phase 1 ("package today's bridge... confirm the reader attaches and drives lighting") and launcher §7.1 ("bundle the existing menubar + bridge; run it off the stick... subsystem-parity check") are the same $0 experiment with different acceptance bars. Unmerged, either the work is duplicated or — worse — Phase 1 "passes" on its weaker bar (attach + rotation) while the launcher's §2 bar (full parity incl. Stream Deck, Govee cloud+LAN, pads) would have failed. Execute once as launcher M1 with Phase 1's checks folded in (E4).
2. **The launch profile must become the shared artifact — and the launcher just proved why.** Launcher §2(a) mandates a single `launch_profile` source so the bundle and `ss_bridge_watcher.sh` can't drift, then hand-copies the watcher's env list into its own text — and that copy is **already stale**: the watcher also sets six `RBSS_LED_*` flags (`RBSS_LED_PHRASE_MONOTONIC`, `_MIN_DWELL`, `_CANCEL_PENDING`, `_RT_RECONCILE`, `_TRANSPORT_STICKY`, `_TRANSPORT_COOLDOWN`, `ss_bridge_watcher.sh:122-145`) that launcher §2(a)'s list omits (`confirmed`, both read this session). Meanwhile the plan's packaging phases never mention the env profile at all — a Phase-1 bundle built from the plan alone would run a *different bridge* than the watcher runs. Stitch: the plan's Phase 1/3 deliverables adopt `launch_profile` by name; the launcher's §2(a) list gets replaced by a pointer to the module ("the module is the list").
3. **Launcher §5's MIDI fix must not be sold as "host-agnostic."** "Create a virtual port instead... the lazier and host-agnostic one" is agnostic *among Macs only* — `virtual=True` is precisely what Windows rtmidi cannot do (plan §1.3, verified). Fine for the Mac slice, but state it as the per-OS strategy it is (macOS: create-virtual or enable IAC; Windows: open named in-box loopback, E2) behind one port-config point (R8) — otherwise the Windows target inherits a Mac-only assumption from its own base, which is exactly the "quiet foreclosure" this ruling was asked to hunt. Also both docs cite `streamdeck_midi.py:431` for the virtual-port call; it's `:540` at HEAD (R10).
4. **The second supervised process.** Launcher §2(b)'s parity bar requires Stream Deck, but §3.2's runner design ports the watcher's logic as "run exactly one bridge" — omitting that the watcher *also* spawns and supervises `streamdeck_midi.py` (`ss_bridge_watcher.sh:35-37,55-68`). The plan is equally silent (R5.4). Whoever owns the bundle's process model must own both children (and say what happens to the pads). One paragraph in the launcher's §3.2 + one line in the plan's Phase 1 files list.
5. **The stick carrier (R4) is a joint decision.** Launcher M1 runs the `.app` "off the stick"; on the plan's exFAT stick that app arrives with broken symlinks. The DMG-on-exFAT layout (E3) needs to land in *both* docs — plan §3.5 and launcher §3.1/§7.1 — and it composes nicely with the launcher's existing read-only-media assumption and scratch-folder design (a mounted DMG is read-only by construction).

**Windows-extensibility check (the brief's specific question):** with stitches 2–4 applied, the launcher's choices remain the base a Windows target extends, not a Mac fork: PyInstaller onedir is shared; `launch_profile` and the ported watch/setup logic are platform-neutral Python; the AppKit menubar, `NSWorkspaceDidUnmountNotification`, `StartOnMount`/launchd, and the memory-grant invocation are correctly per-OS *shell* concerns with known Windows analogues (tray icon, `WM_DEVICECHANGE`, Task Scheduler/Run key — all deferred, none foreclosed). The one structural ask: the launcher should state explicitly that setup/watch/profile logic lands in platform-neutral modules with the Cocoa layer as a thin shell — it's implied by its four-unit decomposition (§3) but not committed to, and it is the single sentence that keeps the future Windows launcher from starting life as a rewrite.

**Cross-report reconciliation (done, not deferred).** The launcher-side Fable review already exists (`docs/plans/active/usb_bridge_launcher_fable_review.md`, AWR-123), and its Part 3 was checked against this one: it independently ruled **COMPOSE**, independently found the exFAT/DMG contradiction with the same resolution (its Contradiction A ≡ stitch 5), the same M1 ≡ Phase 1 dedupe (its Contradiction B ≡ stitch 1), the same per-OS MIDI port-strategy seam with "Setup enables IAC" demoted to runbook-only (≡ stitch 3), and the same launch-profile ruling — adding one refinement this review endorses: the watcher should *read* the shared profile rather than stay frozen beside it (≡ stitch 2). **No disagreements between the two reports.** The one stitch net-new here is #4 (the second supervised process — the watcher's Stream Deck child), which neither the launcher review's Part 3 nor either design doc covers. Incidental confirmation of R10: that review cites the virtual-port call at `streamdeck_midi.py:530`, this one verified `:540` at HEAD — the line moved *between the two reviews on the same day*.

---

## Success-criteria ledger (brief §Success criteria, checked off)

**1. Every `assumed`/`unknown` in the plan dispositioned:**

| Plan label | Disposition |
|---|---|
| §1.1 `confirmed` seam small/one-file | **Overturned in part** — R3 (live_bpm 9 imports, 3 attach sites, fcntl entrypoint) |
| §1.1 `confirmed` models/StateManager purity | **Confirmed** (sweep + direct reads; zero OS hits) |
| §1.3 `confirmed` rtmidi-can't-virtual-on-Windows | **Confirmed** (official docs: `NotImplementedError`) — but decision space changed (R8/E2) |
| §1.3 `confirmed` lsof + DB/ANLZ fallback | **Confirmed** (`filepath_resolver.py:78-90`; nuance: ANLZ resolve is primary with lsof fallback within it — direction reversed vs plan prose, conclusion unchanged) |
| §1.2(c) `confirmed` Info.plist version detect | **Confirmed** (`live_bpm.py:799-820`, hardcoded /Applications paths) |
| §2.1 `confirmed` 5-build table, exact-match, inert reader | **Confirmed** (7.2.8/10/11/13/14; `rb_offsets.py:308-314`; `rb_state_reader.py:953-967`) |
| §2.2 `assumed` adaptive resolver is materially heavier | **Left standing** — not settleable from a desk; routed to reader spec (and E9 argues the table may be permanently sufficient) |
| §3.1–3.3 external packaging claims | **Verified** (P1–P5, primary sources) |
| §3.4 `confirmed` mechanism / `assumed` quarantine scenario | Mechanism **verified** (quarantine-aware apps only); scenario **left standing** — only `xattr -l` on the target Mac settles it |
| §3.4 EV reversal / SmartScreen reputation | **Verified** with exact dates (Feb/Aug 2024) |
| §3.4 Azure Artifact Signing name/price/individual track | **Verified current** (FAQ 2026-06-22; US/CA individuals) |
| §3.4 Certum pricing | **Partly verified** — right neighborhood, option-dependent (plan's hedge stands) |
| §3.5 exFAT stick | **Contradicted for the `.app`** (R4 — PyInstaller docs) |
| §4.2 `confirmed` no upper BPM clamp / no flash ceiling | **Confirmed — and worse than stated** (R1: unclamped live-BPM ingress) |
| §6 hardware-only unknowns (packaged attach, Windows stack, foreign grant, quarantine-in-practice) | **Left standing by design** — desk-unsettleable; §6 text needs the R7 rewrite |
| §7 `confirmed` Apple debugger-entitlement limitation; `assumed` notarization-scan checkbox | **Left standing as quoted** (reader-spec territory per the brief's boundary); both need the R7 re-frame to the ad-hoc world |

**2. Seam completeness answered file-by-file** — the table above; five named missed clusters. ✅
**3. Strobe floor explicit ruling** — **insufficient as specified**, sound in architecture, concrete respec given (R1/R2). ✅
**4. ≥1 external claim spot-verified per area** — packaging (P1/P2/P3/P5), signing (P6/P7/P8), Windows MIDI (A1/A2/A3), plus flash-safety (WCAG/Fisher/HSE) beyond the ask. ✅
**5. Ideas ranked + costed, rejections reasoned (E1–E12); relationship ruling cites specific sections of both docs (Part 3, stitches 1–5).** ✅

*Follow-ups that belong to the operator, not this review: fold R1–R9 into the plan (then into Codex specs), apply the Part 3 stitches to both docs, and update AWR-120's "Unreviewed" note in the registry when that happens. Nothing was changed by this review beyond writing this file.*
