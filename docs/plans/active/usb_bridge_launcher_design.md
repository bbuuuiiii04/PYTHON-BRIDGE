---
doc_status: current
truth_level: spec
last_verified_commit: 8abccdf
last_verified_date: 2026-07-04
validation_scope: >
  Design spec for a macOS-only self-contained USB bridge launcher (PyInstaller bundle +
  menubar with temporary/permanent install). Software-design only — no code, no build, no
  hardware run. Windows is deferred (out of scope). The memory-read authorization *mechanism*
  is the separate reader spec's job; this design only *invokes* that step. Code claims verified
  against HEAD and labelled confirmed/assumed/unknown.
work_status: planned
relates_to: cross_platform_portability_plan.md
---

# USB Bridge Launcher — design spec (macOS-only)

Approved design (2026-07-04). This is the Mac-only "USB-ify" concretization of the portability
work; the Windows/cross-platform half is deferred. Reviewed + revised 2026-07-04, twice and
independently: this session's adversarial review at `8abccdf` (env-list, process-discoverability,
watcher-scope, eject-flow, PyInstaller-version findings) AND the parallel Fable design review
(AWR-123, `docs/plans/active/usb_bridge_launcher_fable_review.md`, verdict PASS WITH REQUIRED
FIXES — its P1 fixes F1-F4 are folded in below; its repo claims were independently re-verified
at HEAD before adoption; its F5-F12 are Codex-plan content). Next step after this spec is a
Codex implementation plan: `docs/plans/active/usb_bridge_launcher_m1_codex_spec.md`
(Milestone 1 only — the risk-killer; Milestones 2-4 get specced after M1's unknowns resolve).

## 1. Goal

A self-contained macOS USB stick. Plug it into any Mac, open the stick, double-click one app →
the bridge menubar appears. First time on a given Mac, the menubar offers **Run temporarily** or
**Install permanently**. No Python, no dependencies, and no developer tools on the host — the whole
runtime is bundled on the stick. The **full** bridge runs, not a stripped-down subset.

**Operator decisions locked (2026-07-04):**
- Bundle everything (PyInstaller) — no host Python/dependency install. `confirmed` choice.
- Accept the one-time admin memory-grant on foreign Macs (not literally zero-trace). `confirmed` choice.
- No notarization / no $99 (from `cross_platform_portability_plan.md`). Ad-hoc signing only.

## 2. "Operates normally" — the acceptance bar

The bundled bridge must behave **identically** to today's source-run bridge: every subsystem live,
same launch profile. This is a hard parity requirement, not "mostly works." Three concrete parts,
all `confirmed` against `scripts/ss_bridge_watcher.sh`:

**(a) Same launch profile.** Today the watcher's AUTO path (`ss_bridge_watcher.sh:122-145`) launches
the bridge with: `RBSS_GOVEE_REALTIME=1`, `RBSS_LIVE_BPM_FOLLOW=1`, `RBSS_ANLZ_DIRECT=1`,
`RBSS_POS_CHAIN_DIRECT=1`, `RBSS_POS_CHAIN_SKIP_OBJC=1`, `RBSS_MASTER_SEED_DIRECT=1`,
`RBSS_MASTER_DIRECT=1`, `RBSS_PLAY_DIRECT=1`, `RBSS_TRACK_LOAD_DIRECT=1`, `RBSS_SCRIPTED_DIRECT=1`,
`RBSS_SCRIPTED_SHOWFILE_DIRECT=1`, `RBSS_SMART_REARM_EXPERIMENT=1`, `RBSS_SMART_DROP=1`,
`RBSS_SMART_BREAKDOWN=1`, **`RBSS_LED_PHRASE_MONOTONIC=1`, `RBSS_LED_MIN_DWELL=1`,
`RBSS_LED_CANCEL_PENDING=1`, `RBSS_LED_RT_RECONCILE=1`, `RBSS_LED_TRANSPORT_STICKY=1`,
`RBSS_LED_TRANSPORT_COOLDOWN=0`**, plus `RBSS_LASER_CONFIG` and the Govee env. The bundle's
`--run-bridge` mode **must reproduce this exact set**.
> **Live evidence for the no-drift decision (found in review, 2026-07-04):** the watcher's own
> MANUAL path (`ss_bridge_watcher.sh:161`) already omits the six `RBSS_LED_*` flags the auto path
> sets — the two hand-maintained lists inside ONE script have drifted. `confirmed` harmless today
> only because all six happen to match their code defaults (five default on; `TRANSPORT_COOLDOWN`
> defaults off and the watcher sets 0). Any future default change breaks manual-mode parity
> silently.
> **Design decision — one launch profile, no drift:** extract this env set + config paths into a
> single shared source (a small `launch_profile` module or a JSON the app loads) that **both**
> `ss_bridge_watcher.sh` and the bundle read. Parity is then guaranteed by construction — one source
> of truth instead of hand-maintained flag lists that have already diverged once.

**(b) Every subsystem in the bundle.** OS2L/SoundSwitch (`python-osc`, `zeroconf` discovery), MIDI
(`mido` + `python-rtmidi`), lasers, LEDs/Govee (cloud HTTPS **and** LAN), Stream Deck, `pyrekordbox`,
ANLZ reading. Nothing silently dropped by PyInstaller's static scanner (see §5 hidden-imports).
> **Watcher scope (found in review):** "port the watch logic" is bigger than adopt/restart/backoff.
> `confirmed` at HEAD, `ss_bridge_watcher.sh` today ALSO: sources the Govee env (`:114-119`),
> creates + force-enables the laser config (`ensure_laser_config`, `:73-95`, sets `enabled=true`,
> `dry_run=false`), **starts and stops the Stream Deck script** (`start_streamdeck`/`stop_streamdeck`,
> `:59-69`, invoked at `:300,315`), and opens the log-monitor Terminal. The bundle runner must state a
> disposition for EACH: Govee env + laser config = port (resolved per §2(c)); Stream Deck runner =
> port (a bundled `--run-streamdeck` entrypoint or equivalent — without it the §2 bar's "Stream Deck"
> line fails; note `streamdeck_midi.py` already guards itself with `_acquire_singleton_lock`);
> monitor Terminal = replace with menubar status/log access (dropping the auto-opened Terminal is
> fine, say so in the runbook).

**(c) Config + secrets from the stick.** `confirmed`: today config resolves to host paths —
`GOVEE_ENV_FILE="$HOME/Library/Application Support/RBSS Bridge/govee.env"`, laser config from the repo,
host `/opt/homebrew/bin/python3`. On a foreign Mac none of those exist. The bundle must resolve config,
`govee.env`, laser/LED config, and SoundSwitch packs from the **stick** (temporary) or the installed
copy (permanent) — never a hardcoded host path.

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
> **One-process invariant under a bundle (both reviews converged here; flock fact re-verified):**
> `confirmed`: the INVARIANT itself is already safe — the bridge takes an exclusive flock on
> `/tmp/rb_ss_bridge_v2.lock` and a second bridge of ANY form refuses to start
> (`__main__.py:772-785`, refusal in `main()` at `:1082-1084`). Command-line-agnostic: it holds
> across any mix of source-run and bundled bridges. What BREAKS under a bundle is observability and
> control: the operator check (`pgrep -f rb_ss_bridge_v2`), the watcher's `bridge_pids()` regex
> (`ss_bridge_watcher.sh:97-99`), and the menubar's own patterns/start/stop
> (`bridge_menubar.py:35-36` + `pkill -f`) all match the SOURCE-RUN command line only — a frozen
> binary is invisible to every one of them (menubar shows "off" while the bundled bridge runs; the
> stop button can't stop it). Requirements:
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
filesystem, `launchd`, and the reader-spec's memory-grant step (invoked, not designed here).

**3.4 Menubar UI** — extend the existing PyObjC app `scripts/bridge_menubar.py` (`confirmed`: it's raw
AppKit/`NSStatusBar`, not rumps). Adds a Setup section (Run temporarily / Install permanently /
Uninstall) above the current status display. Purpose: surface Setup + status.

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
- **Fixed `/tmp` state (AWR-123 F8):** the runtime also writes fixed `/tmp` paths outside any
  scratch dir (status/commands IPC `runtime_status.py:16-17`, the instance lock, Govee caches,
  palette state, logs). Cleanup must delete an enumerated fixed-path list, or a later milestone
  threads one `RBSS_RUNTIME_DIR` knob through the launch profile (the Windows-shaped fix).
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
> one-process invariant.

## 5. Foreign-Mac "operate normally" gaps to handle

- **MIDI port creation.** `confirmed`: laser/legacy MIDI opens a port **by name** — `MidiOutput(port_name=cfg.midi_output_port…)` (`__main__.py:417,429`), default IAC Bus 1; MTC fallback also reads RB over IAC Bus 1 (`__main__.py:1737`). A fresh Mac has no IAC bus enabled. **Fix:** on a machine without the named port, create a **virtual** port instead (Stream Deck already does exactly this — `mido.open_output(PORT_NAME, virtual=True)`, `streamdeck/streamdeck_midi.py:654` at `8abccdf`), or have Setup enable/create the IAC bus. Decide at implementation; the virtual-port path is the lazier and host-agnostic one.
- **SoundSwitch host-side.** The rig is a given, but note once: SoundSwitch itself must be installed on the host and its MIDI input pointed at the bridge's port, and its project/packs present. If the MTC fallback matters on that host, Rekordbox's MIDI/MTC output over the bridge-visible port is a runbook item too. Out of scope to automate; name both in the operator runbook.
- **Config/secrets resolution** — §2(c).
- **Permission cascade (AWR-123 F4, adopted):** the foreign-Mac first run hits more than the memory
  grant — **Local Network** (Sequoia+: silent denial kills zeroconf/Govee-LAN; requires
  `NSLocalNetworkUsageDescription` in Info.plist or the app is never even prompted), **Input
  Monitoring** for Stream Deck HID (sometimes no automatic prompt at all), the macOS 13+
  "Background Items Added" notification for the permanent-mode LaunchAgent, and ad-hoc signing
  re-triggering the whole cascade on every rebuild (TCC keys grants to the per-build cdhash).
  Setup needs a permission inventory + plain-language concierge screens; a timeboxed Milestone-1
  experiment: sign with a free personal-team Apple Development cert for a stable TCC identity.
  Detail + sources: AWR-123 review F4.
- **MIDI port map (AWR-123 F7):** three IAC-coupled endpoints in two directions (laser/look-select
  OUT via laser config name; MTC IN `mtc_reader.py:30`; SoundSwitch pack MIDI IN hardcoded
  `soundswitch_midi_input.py:88`) — the Codex plan carries a port-map table (endpoint, direction,
  name source, consumer, foreign-Mac strategy). Default strategy: bridge-created virtual ports
  (Stream Deck precedent); "enable IAC in Audio MIDI Setup" is runbook fallback only, never a code
  path (it would fork the launch path Mac-only — portability ruling).
- **Memory grant** — reader-spec dependency; Setup invokes it. `unknown` until that spec lands whether the grant works cleanly on a foreign Mac (the top open risk, carried from `cross_platform_portability_plan.md` §7).

## 6. Risky bits (Milestone 1 must prove)

- **Bundling the PyObjC menubar** with PyInstaller — feasible but AppKit can need hooks. `assumed`.
- **Running the bridge in-bundle** without host Python and without the parent-dir import trick. `assumed` — this is the biggest unknown.
- **PyInstaller × Python version.** `confirmed`: PyInstaller is not currently installed; the local
  runtime is Python 3.14 (CI is 3.11). Whether PyInstaller supports 3.14 at build time is `unknown` —
  the bundle may need a pinned 3.12/3.13 build environment, and whichever interpreter gets bundled
  must be one the test suite passes on. Milestone 1 resolves this first.
- **Memory reads under an ad-hoc-signed bundle, on Brandon's OWN Mac.** `confirmed`: the reader uses
  `task_for_pid` + `mach_vm_read_overwrite` (`rb_memory.py:60-72`); code-signing state can change
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
   full bridge, one-process invariant holds. **Verify:** subsystem-parity check (§2) vs a watcher run.
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
