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
work; the Windows/cross-platform half is deferred. Reviewed + revised 2026-07-04 (adversarial
review at `8abccdf`; env-list, process-discoverability, watcher-scope, eject-flow, and
PyInstaller-version findings folded in). Next step after this spec is a Codex implementation
plan: `docs/plans/active/usb_bridge_launcher_m1_codex_spec.md` (Milestone 1 only — the
risk-killer; Milestones 2-4 get specced after M1's unknowns resolve).

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

**3.1 The bundle** — PyInstaller `--onedir --windowed` `.app` on the stick, carrying its own Python +
all deps + the whole `rb_ss_bridge_v2` package. Ad-hoc signed (free; satisfies Apple-silicon's
must-be-signed-to-run rule). Purpose: package. Depends on: the repo + PyInstaller.

**3.2 Bridge runner (`--run-bridge`)** — the main rework. `confirmed`: today the menubar shells to
`ss_bridge_watcher.sh` → host Homebrew Python → `python3 -m rb_ss_bridge_v2` **from the repo's parent
dir** (the package imports from parent — `BRIDGE_DIR="$(dirname "${REPO_ROOT}")"`). None of that exists
in a bundle. Design: the menubar app spawns **its own bundled binary** with a `--run-bridge` flag; that
entrypoint runs the bridge in-bundle with the §2(a) launch profile. The bash watcher's watch logic
(wait for Rekordbox + SoundSwitch present, adopt/restart exactly one process, backoff — plus the §2(b)
watcher-scope items) ports into the app. Purpose: run exactly one bridge. `ss_bridge_watcher.sh` stays
untouched for the current dev workflow.
> **One-process invariant under a bundle (found in review — this is the invariant-killer):**
> `confirmed`: both the operator check (`pgrep -f rb_ss_bridge_v2`) and the watcher's own
> `bridge_pids()` regex (`ss_bridge_watcher.sh:97-99`) match the SOURCE-RUN command line
> (`python3 -m rb_ss_bridge_v2`). A PyInstaller binary has a different argv — invisible to both. Two
> failure modes: the operator's check reports 0 while a bundled bridge runs; and on Brandon's own Mac
> the watcher and the launcher cannot see each other's bridge → **two bridges**. Requirements:
> 1. **Discoverability:** name the bundled bridge executable so its process command line contains
>    `rb_ss_bridge_v2` (e.g. the `--run-bridge` child runs as `rb_ss_bridge_v2 --run-bridge`) — then
>    the operator's one check counts BOTH forms.
> 2. **Mutual exclusion, launcher-side:** before starting a bridge, the launcher must count existing
>    bridge processes of EITHER form (source-run pattern + its own) and refuse/adopt rather than
>    double-start; plus a single-instance guard for the launcher itself (precedent:
>    `streamdeck_midi.py::_acquire_singleton_lock`). The watcher stays untouched, so the launcher owns
>    this entirely.

**3.3 Setup controller** — first-run detection (is there a permanent install / LaunchAgent on this
Mac?) and the two install modes (§4). Purpose: manage where the app lives + its lifecycle. Depends on:
filesystem, `launchd`, and the reader-spec's memory-grant step (invoked, not designed here).

**3.4 Menubar UI** — extend the existing PyObjC app `scripts/bridge_menubar.py` (`confirmed`: it's raw
AppKit/`NSStatusBar`, not rumps). Adds a Setup section (Run temporarily / Install permanently /
Uninstall) above the current status display. Purpose: surface Setup + status.

## 4. The two modes

**Temporary** — run the bridge off the stick. All logs/cache/config/`govee.env` go to **one scratch
folder** (e.g. `$TMPDIR/rbss-<run-id>/`, under a stable `rbss-` prefix so a later run can sweep
leftovers). Cleanup flow, revised in review:
- **Primary: quit-from-menubar.** Quit stops the bridge, wipes the scratch folder, exits — THEN the
  operator ejects. This is the documented flow because `confirmed` macOS behavior blocks unmounting a
  volume whose binaries are running: while the app runs from the stick, a polite eject FAILS busy.
- **Secondary: `NSWorkspaceWillUnmountNotification`** (not `Did` — by `Did` the app's own volume is
  gone). On will-unmount of the stick's volume: stop bridge, wipe scratch, exit fast so the unmount
  can proceed. `assumed` workable — Milestone 2 must verify the app can win that race in practice.
- **Force-eject / yanked stick:** the app dies mid-flight; scratch survives until the NEXT temporary
  run sweeps stale `rbss-*` folders (or the host's own `$TMPDIR` cleanup does). Accepted residual.
Residual trace, per operator decision: the OS memory-permission grant (admin, sticky), possibly a TCC
entry, and — after a force-eject only — a scratch folder that the next run or the OS sweeps.

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
2. **Temporary mode** — run-from-stick + scratch folder + the §4 cleanup flow (quit-first primary,
   will-unmount secondary). **Verify:** after menubar-quit + eject, the scratch folder is gone, bridge
   stopped, one-process count 0 (counting BOTH process forms per §3.2); after a will-unmount eject,
   same; after a simulated force-eject, the next run sweeps the stale scratch.
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
