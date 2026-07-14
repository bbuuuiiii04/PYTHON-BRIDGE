---
doc_status: current
truth_level: spec
last_verified_commit: b629b93
last_verified_date: 2026-07-13
validation_scope: >
  Current macOS USB launcher design reconciled to the landed M1/M2 code and
  earlier foreign-Mac packaging failures. Target get-task-allow is the expected
  TimecodeLink-style access mechanism; a positive entitlement proves the
  Rekordbox target patch only, not a live attach. Stock Apple-Silicon
  foreign-Mac attach after successful patch + deep verify + GTA=true + relaunch
  is live-unvalidated / unknown (not confirmed unsupported; not a confirmed
  caller-authorization blocker). Earlier attempts never reached that clean
  pre-attach state. A dormant Accessibility MEASUREMENT probe
  (`--probe-rekordbox-accessibility`) is implemented/software-tested and not
  executed; it is not a reader, adds no menu item of its own, and has no
  runtime wiring. The separate RB7216 Patch Rekordbox menubar action sits in
  the maintenance block with Export/Rebuild (always visible; Export/Rebuild
  source-only; valid target patch only). `rekordbox_patch.py` adds only
  get-task-allow, preserves existing entitlements, and runs exactly one
  root-bundle ad-hoc codesign (no --deep, no nested re-sign) under the calling
  app's native macOS authorization (not osascript; no full Rekordbox backup by
  operator request). Its privileged script is carried in argv and creates the
  entitlement plist root-owned, rather than leaving either pending payload in
  a user-writable temp file. Local `/Applications` RB 7.2.16 apply passed deep+strict
  verification and GTA inspection; a signed frozen probe app also performed a
  native-authorized inert write/remove in the Rekordbox bundle. Frozen Info.plist declares
  NSAppBundlesUsageDescription (implemented/software-tested). Frozen Patch
  Rekordbox confirmation/result dialogs use native AppKit rather than bare
  `osascript display dialog`; its native authorization path keeps RBSS Bridge as
  the App Management requester. This proves the local patch mechanism, not a
  physical foreign-Mac run or live attach. make_stick excludes mutable
  AppleDouble transport metadata from both package and USB-publication hash
  authority, mounts the finished DMG read-only, and
  runs both deep signature verification and the real installer package
  validator before publication. It also stamps build GENERATION into
  CFBundleShortVersionString/CFBundleVersion (fallback
  0.0.1 outside make_stick). Packaging components remain software-tested;
  stock foreign-Mac attach remains live-unvalidated / unknown.
work_status: implementation partial; packaging/install UX landed; AWR-222 AX measurement probe implemented/software-tested/not executed; rekordbox_patch root-only/native-authorization + App Management Info.plist declaration implemented/software-tested with local patch-path evidence; target-patch→stock-attach hypothesis reopened by TimecodeLink parity; blocked on stock-SIP live gate evidence, not on a proven impossibility
relates_to: cross_platform_portability_plan.md, track_identity_move_invariance_design.md, awr222_ax_probe_sol_spec_2026_07_12.md
---

# USB Bridge Launcher — design spec (macOS-only)

> **Implementation reality (2026-07-10/11 foreign-Mac fix round, branch `claude/rbss-bridge-install-debug-59yrn6`; see AWR-186).** The first run of the built M2 bundle on a second Mac (macOS 12, Apple Silicon) failed across the board — this design assumed a source/dev host and never captured that the FROZEN bundle must: (a) build against a **python.org universal2, LOW-deployment-target** interpreter — Homebrew's macOS-15 `libpython` hard-binds `_mkfifoat` and crashes on macOS < 15 (`make_stick.sh` now enforces this; **spectral analysis stays REQUIRED**, fail-loud, never dropped); (b) guard the menubar singleton with an **flock**, not argv-`pgrep` (a frozen argv never matches); (c) **surface silent child-process crashes** (bridge start, Rekordbox patch) instead of failing invisibly; (d) point the Laser/LED pads at the **App Support live config**, never the code-signed bundle (a pad Save into the bundle invalidates the signature/TCC grants); (e) resolve `ICON_DIR` and pad assets from the bundle, not `/Users/bbui`. Eight defects fixed, one (unresponsive-menu) refuted. ALL frozen/macOS behavior remains operator-unvalidated.

> **Current AWR-222 status (honesty correction 2026-07-13).** Packaging fixes do
> not by themselves prove stock foreign-Mac live input. Target
> `get-task-allow` is the expected TimecodeLink-style mechanism; TimecodeLink
> itself had no caller `cs.debugger` and used the same Mach attach APIs. A
> positive entitlement proves the Rekordbox patch only. Stock Apple-Silicon
> attach after successful patch + deep verify + GTA=true + relaunch is
> **live-unvalidated / unknown** — not a confirmed caller-authorization
> blocker. Earlier foreign-Mac packaging failures and the RB7216 apply (failed
> on `libssl.3.dylib`, GTA left absent) never reached that clean pre-attach
> state. The maintainer Mac has custom SIP (Debugging Restrictions disabled),
> so local success is not foreign-Mac proof. Do not weaken a guest's SIP.
>
> **Dormant AX measurement probe (implemented/software-tested, not executed).**
> Packaged dispatch `--probe-rekordbox-accessibility` on `usb_launcher.py` lazily
> loads `usb_launcher_ax_probe.py` and never starts the bridge. It is a
> measurement diagnostic only — not a reader; the dormant AX measurement probe
> itself adds no menu item and no runtime wiring; no live AX/TCC/USB evidence yet.
> The separate RB7216 **Patch Rekordbox** action sits in the maintenance block
> with Export/Rebuild (always visible in both editions; Export/Rebuild remain
> source-only). It targets only the Rekordbox entitlement. AWR-222 remains
> open on the stock-SIP live gate (and AX E3 matrix), not on a proven
> impossibility of the target-patch path.

> **2026-07-13 patch/USB hardening (`81f1b15`, plus installer/builder commit
> `8cef272`).** The menu's grey **Rekordbox Patched** state now requires both
> GTA and a deep+strict signature; the initial slow check renders grey
> **Checking Rekordbox…**, and GTA with an invalid signature remains actionable
> for repair. The patch adds nothing beyond GTA, uses no full-app backup, and
> removes user-writable privileged script/entitlement races. Real USB builds
> require a clean, unchanged HEAD and a `/Volumes/.../PIONEER` target; payload
> symlinks are refused and the Govee credential is owner-only. AppleDouble
> `._*` files and `.DS_Store` are removed before manifest generation; after DMG
> creation, the builder mounts the final image read-only and requires both the
> deep signature check and `install_controller._validate_package()` to pass
> before it can publish to the stick. The outer FAT publication also removes
> and ignores mutable AppleDouble companions so later macOS metadata writes do
> not invalidate the DMG/sidecar manifest. Native install
> rejects payload symlinks, keeps the Govee file `0600`, and gives conservative
> guidance if rollback itself fails. These are software proofs only; no physical
> foreign-Mac patch, attach, installer, or lighting run was performed.

Approved design (2026-07-04). This is the Mac-only "USB-ify" concretization of the portability
work; the Windows/cross-platform half is deferred. Reviewed + revised 2026-07-04, twice and
independently: this session's adversarial review at `8abccdf` (env-list, process-discoverability,
watcher-scope, eject-flow, PyInstaller-version findings) AND the parallel Fable design review
(AWR-123, `docs/plans/active/usb_bridge_launcher_fable_review.md`, verdict PASS WITH REQUIRED
FIXES — its P1 fixes F1-F4 are folded in below; its repo claims were independently re-verified
at HEAD before adoption; its F5-F12 are Codex-plan content). Re-verified in full at `9ead100`
(2026-07-09 paper-phase pickup): every code claim re-checked against current code; the deltas
are folded in below (§2(a) env change, §2(b)/§6 frame-engine child, §4 log surface +
ProcessType, §5 port-map correction). The Milestone-1-only Codex implementation spec now
exists at `docs/plans/active/usb_bridge_launcher_m1_codex_spec.md` (authored 2026-07-09 in
the same paper phase; implementation gates on the executive). Milestones 2-4 get specced
after M1's unknowns resolve.

## 1. Goal

A self-contained macOS USB stick. Plug it into any Mac, open the stick, double-click one app →
the bridge menubar appears. First time on a given Mac, the menubar offers **Run temporarily** or
**Install permanently**. No Python, no dependencies, and no developer tools on the host — the whole
runtime is bundled on the stick. The **full** bridge runs, not a stripped-down subset.

**Operator decisions locked (2026-07-04):**
- Bundle everything (PyInstaller) — no host Python/dependency install. `confirmed` choice.
- Accept the one-time admin memory-grant on foreign Macs (not literally zero-trace). `confirmed` choice.
- No notarization / no $99 (from `cross_platform_portability_plan.md`). Ad-hoc signing only.
- **USB mode drives lighting via the bridge-native pack player (AWR-107), not SoundSwitch on the
  host** (operator 2026-07-04, recorded at parking). Voids §5's "SoundSwitch host-side" bullet —
  no SS install or SS-MIDI-input setup on foreign hosts; pack assets ride the stick, which §2(c)
  already provides for. Foreign-host MIDI needs shrink to Stream Deck + bridge-internal look
  wiring; Enttec DMX output (pyserial — an undeclared dependency, AWR-124 R5) joins the §2(b)
  bundle-parity surface. Re-scope §2(b)/§5 at pickup; AWR-107's pending live hardware run becomes
  a pickup dependency of this bundle.

**Open operator decisions (flagged at the 2026-07-09 pickup — NOT adopted; do not fold
silently):** three AWR-123 Part 2 adopt labels are still the operator's to make:
- **Idea 1 — Guest-first:** ship v1 with no first-run mode question and defer permanent mode
  (M3's whole launchd/uninstall surface) until a House Mac exists. This design keeps both
  modes on paper; the M1 spec is valid under either answer (M1 touches neither mode).
- **Idea 8 — $0 stable-TCC-identity experiment:** sign with a free personal-team Apple
  Development cert instead of `-s -`, timeboxed inside M1. Carried in the M1 spec as an
  operator-gated optional task, not a dependency.
- **Idea 9 — "Test the lights" replay demo:** adopt-later; rides the portability plan's
  Phase-2 `ReplaySource`. In no current milestone.

## 2. "Operates normally" — the acceptance bar

The bundled bridge must behave **identically** to today's source-run bridge: every subsystem live,
same launch profile. This is a hard parity requirement, not "mostly works." Three concrete parts,
all `confirmed` against `scripts/ss_bridge_watcher.sh`:

**(a) Same launch profile.** Today the watcher launches the bridge from ONE shared
`start_bridge()` function used by BOTH auto and manual modes (`ss_bridge_watcher.sh:130-175`;
the `exec env` block at `:147-169`) with: `RBSS_GOVEE_REALTIME=1`, `RBSS_LIVE_BPM_FOLLOW=1`,
`RBSS_ANLZ_DIRECT=1`, `RBSS_POS_CHAIN_DIRECT=1`, `RBSS_POS_CHAIN_SKIP_OBJC=1`,
`RBSS_MASTER_SEED_DIRECT=1`, `RBSS_MASTER_DIRECT=1`, `RBSS_PLAY_DIRECT=1`,
`RBSS_TRACK_LOAD_DIRECT=1`, `RBSS_SCRIPTED_DIRECT=1`, `RBSS_SCRIPTED_SHOWFILE_DIRECT=1`,
`RBSS_SMART_REARM_EXPERIMENT=1`, `RBSS_SMART_DROP=1`, `RBSS_SMART_BREAKDOWN=1`,
**`RBSS_LED_PHRASE_MONOTONIC=1`, `RBSS_LED_MIN_DWELL=1`, `RBSS_LED_CANCEL_PENDING=1`,
`RBSS_LED_RT_RECONCILE=1`, `RBSS_LED_TRANSPORT_COOLDOWN=0`**, plus
`RBSS_LASER_CONFIG="$LASER_CONFIG_PATH"`, the Govee env (sourced at `:139-144`), and an
optional `$TRUTH_ENV` Art-Net truth-check injection (`RBSS_BRIDGE_TRUTH=1` opt-in, `:22-28` —
dev/validation only, not a bundle feature). All `confirmed` 2026-07-09. The bundle's
`--run-bridge` mode **must reproduce this exact set**.
> **Re-verified 2026-07-09 — two changes since `8abccdf`.** (1) `RBSS_LED_TRANSPORT_STICKY=1`
> was REMOVED from the launch env by AWR-149 (2026-07-08): the deterministic transport
> rotation (`plan_backend_sequence()` in `led_look_director.py`) replaced the WI-7 sticky
> latch that flag gated. Do not resurrect it in the bundle profile. (2) The 2026-07-04
> manual/auto env drift is FIXED structurally: the manual-only
> `start_manual_terminal_bridge()` function (with its own shorter, drifted env list) was
> deleted; manual mode now calls the same `start_bridge()` (invoked in the `MANUAL_MODE`
> branch, `:323` region). One env list — the two-hand-maintained-lists failure mode can no
> longer recur INSIDE the watcher. Manual mode also changed shape: the bridge always runs as
> a background subprocess now, and the visible Terminal is a read-only `bridge_view.py`
> JSONL viewer (AWR-125) — closing it never kills the bridge in either mode.
> **Design decision — one launch profile, no drift (STANDS):** extract this env set + config
> paths into a single shared source (a small `launch_profile` module or a JSON the app loads)
> that **both** `ss_bridge_watcher.sh` and the bundle read. The watcher unification fixed
> watcher-internal drift; watcher-vs-bundle would still be two hand-maintained lists without
> this. Parity is then guaranteed by construction — one source of truth.

**(b) Every subsystem in the bundle.** OS2L/SoundSwitch (`python-osc`, `zeroconf` discovery), MIDI
(`mido` + `python-rtmidi`), lasers, LEDs/Govee (cloud HTTPS **and** LAN, **plus the AWR-146
frame-engine child process — see below**), Stream Deck (`python-elgato-streamdeck` + `Pillow`,
both **undeclared** in `pyproject.toml` — §5), `pyrekordbox`, ANLZ reading. Nothing silently
dropped by PyInstaller's static scanner (see §5 hidden-imports).
> **Watcher scope (re-verified 2026-07-09):** "port the watch logic" is bigger than
> adopt/restart/backoff. `confirmed` at HEAD, `ss_bridge_watcher.sh` today ALSO: sources the
> Govee env (`:139-144`, path var at `:38`), creates + force-enables the laser config
> (`ensure_laser_config`, `:79-101`, sets `enabled=true`, `dry_run=false` at `:97-98`, called
> at `:138`), **starts and stops the Stream Deck script** (`start_streamdeck`/`stop_streamdeck`,
> `:63-75`, started at `:326,:344`, stopped with a reason argument at `:296,:304`), and opens
> the log-monitor Terminal (`open_monitor`, `:234-254` — now a read-only `bridge_view.py`
> JSONL viewer per AWR-125, not a `tail -F`). The bundle runner must state a disposition for
> EACH: Govee env + laser config = port (resolved per §2(c)); Stream Deck runner = port (a
> bundled `--run-streamdeck` entrypoint or equivalent — without it the §2 bar's "Stream Deck"
> line fails; note `streamdeck_midi.py` still guards itself with `_acquire_singleton_lock`,
> `:69`, lock at `/tmp/streamdeck_midi.lock`, `:38`); monitor Terminal = replace with menubar
> status/log access (dropping the auto-opened Terminal is fine, say so in the runbook).
> Dev-only watcher features NOT ported (state so in the runbook): the `RBSS_BRIDGE_TRUTH=1`
> Art-Net truth-check injection (`:22-28`) and the `WATCHER_NO_LOOP` test hook (`:311,:354`).
> **NEW subsystem since 2026-07-04 — the Govee frame-engine child (AWR-146).** `confirmed`:
> the bridge now spawns a second process of itself —
> `govee_frame_engine_client.py:454-461` runs `subprocess.Popen([sys.executable, "-m",
> "rb_ss_bridge_v2.govee_frame_engine", "--fd", ...])` over a socketpair, `cwd` pinned to the
> package's parent dir. There is NO `sys.frozen` handling anywhere in that path — under
> PyInstaller, `sys.executable` is the frozen app binary, not a Python interpreter, so this
> spawn breaks unfixed. The bundle must give the frozen binary a re-exec-self path for the
> frame-engine child (the standard PyInstaller pattern). Added to §6 risky bits; proving it
> is Milestone-1 scope (§7.1) because realtime LED output depends on this child.

**(c) Config + secrets from the stick.** `confirmed` (re-verified 2026-07-09): today config
resolves to host paths — `GOVEE_ENV_FILE="$HOME/Library/Application Support/RBSS Bridge/govee.env"`
(`ss_bridge_watcher.sh:38`), laser config from the repo, host `/opt/homebrew/bin/python3`
(now override-capable `${PYTHON:-...}` at `:19`; resolves to Python 3.14.6 today). On a
foreign Mac none of those exist. The bundle must resolve config, `govee.env`, laser/LED
config, and SoundSwitch packs from the **stick** (temporary) or the installed copy
(permanent) — never a hardcoded host path.
> **Config surface additions found at re-verification (all `confirmed`):** the LED v2
> identity store and the laser-solo learned store resolve **cwd-relative**
> (`local/state/led_identity_v2.json`, `led_models.py:87`; `local/state/laser_solo_learned.json`,
> `drop_presentation.py:51`) — the live bridge's cwd is the repo's PARENT dir, so today they
> live at `~/local/state/…`. A bundle that changes cwd silently relocates (or loses) them;
> the bundle must pin these into its stick/scratch config surface explicitly. The spectral
> caches live at `~/Library/Application Support/RBSS Bridge/spectral_cache/` (+`/v4/`),
> relocatable via `RBSS_SPECTRAL_CACHE_DIR` (`spectral_cache.py:32-34,215-217`). The Stream
> Deck helper reads a repo-relative canonical pack + MIDI-binding sidecar
> (`streamdeck/streamdeck_midi.py:41-42`). Track-identity portability itself (same track,
> different path ⇒ same lighting identity) is a separate design:
> `track_identity_move_invariance_design.md`.

**Verification of the bar:** a bundled run must produce the same observable outputs as a watcher run —
SoundSwitch rotation, MIDI look-selection, laser output, LED/Govee frames, Stream Deck — checked on
Brandon's Mac against a recorded/known session before any foreign-Mac use.

## 3. Components (four isolated units)

**3.1 The bundle** — PyInstaller `--onedir --windowed` `.app`, carrying its own Python + all deps +
the whole `rb_ss_bridge_v2` package. Ad-hoc signed (free; satisfies Apple-silicon's
must-be-signed-to-run rule). Purpose: package. Depends on: the repo + PyInstaller.
> **Stick layout (AWR-123 F1, adopted):** the `.app` is NEVER raw on the stick — the parent plan
> fixes the stick as exFAT, and PyInstaller 6 onedir bundles are symlink-load-bearing (exFAT has no
> symlinks; a flattened copy breaks the signature seal → "damaged" dialog on the friend's Mac). Ship
> **`RBSS Bridge.dmg` on the exFAT stick** (built with `hdiutil`, never Finder-zip); the DMG mounts
> as a real symlink-capable volume. Keeps the stick Windows-readable for the parent plan.
> **Build decisions (AWR-123 F9, adopted):** arm64-only (three deps ship no universal2 wheels;
> runbook says "Apple silicon only"); minimum-macOS chosen and documented at build time; build
> interpreter = a python.org arm64 Python the suite passes on (Homebrew Python inherits high
> deployment targets; PyInstaller-vs-3.14 support is a Milestone-1 gate, §6).

**3.2 Bridge runner (`--run-bridge`)** — the main rework. `confirmed`: today the menubar shells to
`ss_bridge_watcher.sh` → host Homebrew Python → `python3 -m rb_ss_bridge_v2` **from the repo's parent
dir** (the package imports from parent — `BRIDGE_DIR="$(dirname "${REPO_ROOT}")"`). None of that exists
in a bundle. Design: the menubar app spawns **its own bundled binary** with a `--run-bridge` flag; that
entrypoint runs the bridge in-bundle with the §2(a) launch profile. The bash watcher's watch logic
(wait for Rekordbox + SoundSwitch present, adopt/restart exactly one process, backoff — plus the §2(b)
watcher-scope items) ports into the app. Purpose: run exactly one bridge. `ss_bridge_watcher.sh` stays
untouched for the current dev workflow.
> **One-process invariant under a bundle (both reviews converged here; flock fact re-verified
> 2026-07-09):** `confirmed`: the INVARIANT itself is already safe — the bridge takes an
> exclusive flock on `/tmp/rb_ss_bridge_v2.lock` and a second bridge of ANY form refuses to
> start (`__main__.py:614-629`, refusal in `main()` at `:930-933`). Command-line-agnostic: it
> holds across any mix of source-run and bundled bridges. What BREAKS under a bundle is
> observability and control: the operator check (`pgrep -f rb_ss_bridge_v2`), the watcher's
> `bridge_pids()` regex (`ss_bridge_watcher.sh:103-105`; `kill_bridge_processes` `:107-109`),
> and the menubar's own patterns/start/stop (`bridge_menubar.py:35-38` + `pkill -f`,
> stop/start mechanics in `toggleBridge_` `:1146-1163`) all match the SOURCE-RUN command line
> only — a frozen binary is invisible to every one of them (menubar shows "off" while the
> bundled bridge runs; the stop button can't stop it).
> **Process-count nuance (new since 2026-07-04):** with the v2 realtime engine on, the bridge
> legitimately runs TWO processes — itself plus the AWR-146 frame-engine child, whose argv
> (`-m rb_ss_bridge_v2.govee_frame_engine`) matches the operator's loose
> `pgrep -f rb_ss_bridge_v2` but NOT the watcher/menubar anchored regexes
> (`…rb_ss_bridge_v2$`). The bundle's status surface must count bridges by the anchored
> convention (or flock/status liveness), never by the loose substring — and the runbook's
> "exactly one process" language needs the same footnote. Requirements:
> 1. **Discoverability:** name the bundled binary so its argv contains `rb_ss_bridge_v2` — the
>    operator's one check then counts both forms.
> 2. **Bundle-mode control is owned-child-pid based** (the menubar spawned `--run-bridge`; it holds
>    the handle) + the flock + status.json liveness — no pattern matching when frozen. Menubar
>    self-dedupe when frozen = `NSRunningApplication` by bundle id.
> 3. **Coexistence note for Brandon's own Mac:** with the dev watcher running, a bundled launch is
>    refused by the flock (correct) but the watcher will log adopt/start churn — quit the dev
>    watcher/menubar first, or expect noise. The launcher must SURFACE a lock refusal ("bridge
>    already running") instead of dying silently.

**3.3 Setup controller** — first-run detection (is there a permanent install / LaunchAgent on this
Mac?) and the two install modes (§4). Purpose: manage where the app lives + its lifecycle. Depends on:
filesystem and `launchd`; a working foreign-Mac reader is now the separate AWR-222 blocker.
*Historical note (2026-07-09, AWR-122): the stick-side shell install/purge
helpers were an interim path. They are retired and no longer ship; their old
file-level manifests remain readable by native Purge. The native controller is
the only install/update/purge surface. The M2 operator directive + decomposition:
`docs/plans/active/usb_launcher_m2_operator_directive_2026_07_09.md`.*

*IMPLEMENTED NOW (2026-07-10, AWR-186 M2, software-tested / hardware-unvalidated): the permanent
half of this controller exists as `install_controller.py` + frozen-gated menubar items — DMG-run
detection (`/Volumes/` + AppTranslocation), "Install on this Mac…" (app → `~/Applications`,
DMG-carried `RBSS_payload/` → App Support incl. `govee.env`/live configs, interim-compatible
file-level manifest, relaunch + eject offer, never auto-starts the bridge), config-override env
wiring via `launch_profile.app_support_config_env`, frozen-only `local/state` →
App Support `state/` (`launch_profile.resolve_state_path`), and the menubar PURGE (§R6:
confirm-gated, stop-child-first, three-root allowlist, Trash own bundle, honest TCC residue note).
`packaging/make_stick.sh` is the one-command operator-side builder (AWR-186 executive-gate
hardening 2026-07-10: it fails closed on a malformed/unreadable `soundswitch_pack_player.json` or a
non-empty `pack_path` that is not a readable directory, so a stick never ships claiming success with
no show; and the Enttec DMX port auto-detect — `enttec_dmx_pro.find_enttec_port` — now returns a
device ONLY on positive ENTTEC identity, never a bare FTDI VID or `usbserial` name, falling back to
the configured port). No LaunchAgent/auto-start (M3)
and no temporary/stage-to-scratch mode was built.*

**3.4 Menubar UI** — extend the existing PyObjC app `scripts/bridge_menubar.py` (`confirmed`
re-verified 2026-07-09: raw AppKit/`NSStatusBar`, not rumps; 1224 lines). Adds a Setup section
(Run temporarily / Install permanently / Uninstall) above the current status display. Purpose:
surface Setup + status. Since 2026-07-04 the menubar also gained a temporary "LED Engine v2"
checkbox item + a nested-status read fix (`7d58acf`; `_led_color_engine_status` `:417-427`,
item wiring `:839,:930-936`) — v2-rollout surface, expected to be removed later; the Setup
design is unaffected.

## 4. The two modes

**Temporary** — **"the stick is a key, not a dependency" (AWR-123 F2, adopted — supersedes the
original run-from-stick model).** Running the show off a pullable device converts a mid-set stick
yank into a guaranteed outage, and macOS blocks polite ejects of a volume with running binaries
anyway. Instead: first run **stages the payload to internal scratch**
(`$TMPDIR/rbss-<version>/`, version-keyed so later runs skip the copy) and runs from the internal
disk; from that moment the stick can be pulled at any time and nothing dies. All
logs/cache/config/`govee.env` for the run live under the same stable `rbss-` prefix.
- **Ending a set is an explicit menubar action ("End Set" / Quit):** stop bridge → wipe scratch →
  "safe to pull the stick." Stick unmount is only a SIGNAL to offer cleanup, never a load-bearing
  lifecycle event.
- **Yank / force-eject mid-set:** non-event by construction (bridge runs from internal disk). A
  scratch left behind by a crash is swept by the next run's stale-`rbss-*` sweep or the OS's own
  `$TMPDIR` cleanup.
- **Fixed-path state outside any scratch dir (AWR-123 F8, inventory re-swept 2026-07-09):**
  the enumerated cleanup list, all `confirmed` at HEAD:
  - `/tmp/rb_ss_bridge_v2.lock` (instance flock, `__main__.py:614`);
    `/tmp/rb_ss_bridge_v2_status.json` + `/tmp/rb_ss_bridge_v2_commands.jsonl` (IPC,
    `runtime_status.py:17-18`); `/tmp/rb_ss_bridge_v2_palette_state.json`
    (`led_palette_control.py:42`); `/tmp/rbss-session-<ts>.jsonl` (session-recorder default,
    `__main__.py:1416`); `/tmp/rbss_artnet_truth_frames.jsonl` (`artnet_truth.py:30`);
    `/tmp/rbss_os2l_inject.jsonl` (`os2l_injector.py:22`); `/tmp/streamdeck_midi.lock`
    (`streamdeck/streamdeck_midi.py:38`); `/tmp/govee_h612d_devices.json` +
    `/tmp/govee_h612d_scenes.json` (Govee LAN caches, `govee_runtime_sender.py:29-30`).
  - **Logs are NO LONGER under `/tmp`** — AWR-125 moved them to `~/Library/Logs/rb_ss_bridge/`
    (`bridge_log.py:329-334`): per-run `bridge-<ts>.jsonl` pruned to the newest 20, a
    `current.jsonl` symlink, a `viewer_acks.json` sidecar (`bridge_view.py:987`), plus a
    legacy `/tmp/bridge-events.jsonl` compat symlink created only when `RBSS_RUNTIME_DIR` is
    unset (`bridge_log.py:395-397`).
  - Cwd-relative stores (§2(c)): `local/state/led_identity_v2.json`,
    `local/state/laser_solo_learned.json` — persistent lighting identity/learned state, NOT
    disposable temp; Guest-mode cleanup wipes the scratch copies, but the design must decide
    where these live on the stick so identity persists across guest sessions (they ride the
    stick's config payload, not `/tmp`).
  - `RBSS_RUNTIME_DIR` **now exists but covers logs only** (`bridge_log.py` is its sole
    consumer, `confirmed` by grep) — every `/tmp` path above is still a hardcoded literal.
    So cleanup must delete the enumerated list above, until a later milestone threads
    `RBSS_RUNTIME_DIR` through the remaining fixed paths (the Windows-shaped fix — the knob
    exists now, its coverage doesn't).
Residual trace, restated honestly: the OS memory-permission grant (admin, sticky) and TCC entries
persist (accepted); all bridge FILES are removed by End Set (or the next run's sweep after a crash).

**Permanent** — copy the `.app` off the stick to `~/Applications`; install
`~/Library/LaunchAgents/<id>.plist` with `StartOnMount` so future USB insertions auto-spawn the menubar
(`assumed`: `StartOnMount` is the right launchd key for insert-detection — verify at build); do the
one-time memory grant; run. Provide **Uninstall** (remove app copy + LaunchAgent + config). Config lives
in the installed location, not the stick.
> **`StartOnMount` caveat** (`confirmed` behavior): it fires on **any** volume mount, not just this
> stick. The agent must be cheap and **idempotent** — check "is my menubar already running?" and no-op
> if so; ideally confirm the mounted volume is the bridge stick before acting. Folds into the
> one-process invariant. Re-verified 2026-07-09: still no `StartOnMount` usage anywhere in the
> repo or the live LaunchAgents — design-only, `assumed` until built.
> **LaunchAgent lesson learned since design (AWR-151, `confirmed` live 2026-07-08): any plist
> this feature generates MUST set `ProcessType=Interactive`.** A ProcessType-less LaunchAgent
> gets macOS's background-QoS throttle — the live bridge ran at 28.1 fps until the flip
> proved 60.0. All 4 live plists now carry it, and the advisory checker
> `tools/check_launch_agents.py` (new since `8abccdf`) guards regressions — run it against
> any generated plist template. Also: `~/Library/LaunchAgents/com.bbui.ss-bridge-watcher.plist.disabled`
> points at a path that no longer exists (`/Users/bbui/ss_bridge_watcher.sh`) — never copy it
> as a template.

## 5. Foreign-Mac "operate normally" gaps to handle

- **MIDI port creation.** `confirmed` (re-verified 2026-07-09): laser/legacy MIDI opens a port **by name** — `MidiOutput(port_name=cfg.midi_output_port…)` (`__main__.py:221-224` primary, `:233-236` dual-trigger); the default name is **config data, not code** — `"IAC Driver Bus 1"` in `config/laser_director.json` and `.example.json`. The MTC fallback also reads RB over IAC Bus 1 (`__main__.py:1626`). A fresh Mac has no IAC bus enabled. **Fix:** on a machine without the named port, create a **virtual** port instead (Stream Deck already does exactly this — `mido.open_output(PORT_NAME, virtual=True)`, `streamdeck/streamdeck_midi.py:928`, `PORT_NAME` at `:34`), or have Setup enable/create the IAC bus. Decide at implementation; the virtual-port path is the lazier and host-agnostic one.
- **SoundSwitch host-side.** The rig is a given, but note once: SoundSwitch itself must be installed on the host and its MIDI input pointed at the bridge's port, and its project/packs present. If the MTC fallback matters on that host, Rekordbox's MIDI/MTC output over the bridge-visible port is a runbook item too. Out of scope to automate; name both in the operator runbook.
- **Config/secrets resolution** — §2(c).
- **Permission cascade (AWR-123 F4, adopted):** the foreign-Mac first run hits more than the memory
  grant — **Local Network** (Sequoia+: silent denial kills zeroconf/Govee-LAN; requires
  `NSLocalNetworkUsageDescription` in Info.plist or the app is never even prompted), **Input
  Monitoring** for Stream Deck HID (sometimes no automatic prompt at all), the macOS 13+
  "Background Items Added" notification for the permanent-mode LaunchAgent, and ad-hoc signing
  re-triggering the whole cascade on every rebuild (TCC keys grants to the per-build cdhash).
  Setup needs a permission inventory + plain-language concierge screens; the timeboxed
  free-Apple-Development-cert experiment for a stable TCC identity is §1's OPEN operator
  decision (Part 2 idea 8) — operator-gated, not adopted. Detail + sources: AWR-123 review F4.
- **MIDI port map (AWR-123 F7, corrected 2026-07-09):** three IAC-coupled endpoints in two
  directions (laser/look-select OUT via laser config name; MTC IN `mtc_reader.py:31`,
  `_PORT_SUBSTR = "IAC Driver Bus 1"`; SoundSwitch pack MIDI IN — **correction:** the
  `soundswitch_midi_input.py` "hardcoded IAC" cite was a docstring illustration (now `:90`).
  The real runtime port selection is `SoundSwitchMidiInputGroup` (`:592-643`): one adapter
  per controller device name auto-derived from `pack.learned_midi_bindings`, with per-device
  overrides via the `midi_input_aliases` config key — so this endpoint's foreign-Mac story is
  config-driven, not a code literal). The Codex plan carries a port-map table (endpoint,
  direction, name source, consumer, foreign-Mac strategy). Default strategy: bridge-created
  virtual ports (Stream Deck precedent); "enable IAC in Audio MIDI Setup" is runbook fallback
  only, never a code path (it would fork the launch path Mac-only — portability ruling).
- **Memory grant — live-unvalidated on stock SIP (AWR-222).** The current setup
  re-signs only Rekordbox ad-hoc with `get-task-allow` (TimecodeLink-style
  target patch); the frozen bridge is also ad-hoc and carries no caller
  debugger entitlement. That is the expected target-patch model, not by itself
  proof that stock attach is impossible. Positive entitlement proves the
  target patch only. Stock Apple-Silicon attach after successful patch + deep
  verify + GTA=true + relaunch remains live-unvalidated / unknown; earlier
  physical attempts and the RB7216 apply never reached that clean pre-attach
  state. AWR-221 verifies only the target patch and improves feedback. Do not
  weaken guest SIP. AX remains a dormant measurement probe, not a selected
  replacement reader, unless a green-GTA + red-attach stock-SIP result appears.
- **Rekordbox target patch signing (software-tested / hardware-unvalidated).**
  `rekordbox_patch.py` no longer uses one-shot `codesign --deep` and no longer
  walks/re-signs nested Mach-O helpers. The apply plan is exactly one
  root-bundle command:
  `codesign --force --sign - --entitlements <merged.plist> <rekordbox.app>`.
  Nested helpers (including `rekordboxAgent` / crashpad) keep their original
  Pioneer signatures. The command runs under **one** native macOS authorization
  session from RBSS Bridge, not an `osascript` helper. The operator explicitly
  declined a full Rekordbox backup, so failures report no recovery claim rather
  than copying the whole app. Post-sign check is `codesign --verify --deep
  --strict` plus positive main `get-task-allow`. Local evidence: RB 7.2.16 at
  `/Applications` patched successfully, passed deep+strict and GTA=true, and
  was subsequently observed launched and closed. A separately built, signed
  frozen RBSS probe used that same native path to create/remove an inert marker
  in the Rekordbox bundle (no Terminal/osascript responsibility). Earlier root
  signing through osascript was blocked by App Management.
  Frozen packaging now declares `NSAppBundlesUsageDescription`
  (implemented/software-tested and built-inspected). If macOS blocks a patch,
  enable **RBSS Bridge** in App Management and retry; granting Terminal or
  osascript is not part of the shipped route. The frozen Patch Rekordbox
  consent/result modal is native AppKit, followed by the native macOS admin
  prompt. A real friend-Mac patch and every stock-SIP live attach remain
  unvalidated. AWR-222 honesty unchanged.
- **Dependency manifest gap (re-swept 2026-07-09, `confirmed`):** `pyproject.toml` declares
  only `mido, pyobjc-framework-Cocoa, pyrekordbox, python-osc, zeroconf` (+ optional
  spectral/analysis extras: `librosa`, `soundfile`, `numpy`, `scipy`) and has ZERO diff since
  `8abccdf` — but the runtime also imports **`python-elgato-streamdeck`** (+ its `hidapi`),
  **`Pillow`** (`streamdeck/streamdeck_midi.py`), **`python-rtmidi`** (mido's backend), and
  `pyserial` (Enttec, AWR-124 R5). The PyInstaller spec needs either the manifest fixed or an
  explicit hidden-imports list covering all of these. External system binaries the runtime
  shells out to (inventory for entitlement/runbook purposes): `vmmap` (`rb_memory.py:140-143`),
  `pgrep` (`rb_memory.py:129-132`), `lsof` (`filepath_resolver.py:83-95`).

## 6. Risky bits (Milestone 1 must prove)

- **Bundling the PyObjC menubar** with PyInstaller — feasible but AppKit can need hooks. `assumed`.
- **Running the bridge in-bundle** without host Python and without the parent-dir import trick. `assumed` — this is the biggest unknown.
- **The frame-engine child under a frozen bundle (NEW since 2026-07-04, AWR-146).** `confirmed`
  at HEAD: `govee_frame_engine_client.py:454-461` spawns `sys.executable -m
  rb_ss_bridge_v2.govee_frame_engine` with no `sys.frozen` handling — this exact invocation
  cannot work inside a PyInstaller bundle (frozen `sys.executable` is not a Python
  interpreter). The bundle needs a re-exec-self path; realtime LED output depends on it.
  Milestone 1 must prove the child spawns, streams frames over its socketpair, and dies with
  its parent, under the frozen binary.
- **PyInstaller × Python version.** `confirmed` (re-verified 2026-07-09): PyInstaller is still
  not installed; the local runtime is Python 3.14.6 (CI is 3.11). Whether PyInstaller supports
  3.14 at build time is `unknown` — the bundle may need a pinned 3.12/3.13 build environment,
  and whichever interpreter gets bundled must be one the test suite passes on. Milestone 1
  resolves this first.
- **Memory reads under an ad-hoc-signed bundle, on Brandon's OWN Mac.** `confirmed` (re-verified
  2026-07-09): the reader uses
  `task_for_pid` + `mach_vm_read_overwrite` (`rb_memory.py:58-70`); code-signing state can change
  `task_for_pid` behavior. So Milestone 1 can hit the memory wall BEFORE any foreign-Mac work and
  before the reader/authorization spec exists. Milestone 1's rule: if the bundled bridge's memory
  reads behave differently from a source-run bridge, STOP and report — do not improvise
  entitlements or new authorization mechanics (that is the separate reader spec's scope).
- **`StartOnMount` idempotency** vs the one-process invariant (§4 caveat).
- **The memory grant** under a bundled/ad-hoc app (§5) — foreign-Mac half; blocked on the reader
  spec, Milestone 4 territory.

## 7. Build order (smallest risk-killer first)

1. **Bundle the existing menubar + bridge; run it off the stick on Brandon's own Mac.** Proves it
   packages and runs with no host Python, PyObjC menubar works bundled, `--run-bridge` launches the
   full bridge, the AWR-146 frame-engine child spawns under the frozen binary (§6), and the
   one-process invariant holds. **Verify:** subsystem-parity check (§2) vs a watcher run.
   Kills the biggest unknown for $0.
2. **Temporary mode** — stage-to-scratch launch + the §4 "stick is a key" model + End Set cleanup.
   **Verify:** stick pulled mid-run → bridge keeps running (a literal yank test); End Set → scratch
   + enumerated `/tmp` files gone, bridge stopped, one-process count 0 (counting BOTH process forms
   per §3.2); a crashed run's scratch is swept by the next run.
3. **Permanent mode** — copy-to-host + `StartOnMount` auto-spawn + Uninstall. **Verify:** replug
   auto-spawns exactly one menubar; Uninstall leaves nothing but the memory grant.
4. **Foreign-Mac dry run** — take the stick to another Mac, do the one memory grant, temporary-run the
   full rig, confirm cleanup. **Verify:** all subsystems live (§2 bar) on a machine Brandon doesn't own;
   nothing left after eject except the (accepted) permission entry.

Each milestone carries the same live-safety note as the parent plan: run against a test session, not a
live show, until parity is proven; the strobe floor (portability plan §4) should already be in place.

## 8. Out of scope

- **Windows** — deferred by operator (2026-07-04).
- **The memory-read authorization mechanism** — separate reader/RE spec; this design only invokes it.
- **Standalone / no-Rekordbox operation** — not designed for (the `ReplaySource` seam from the
  portability plan doesn't foreclose it, but it's not this feature).
- **Auto-spawn on a virgin machine** — impossible on macOS (no autorun); auto-spawn exists only
  post-permanent-install via `StartOnMount`. First run on a new Mac is always a manual double-click.
