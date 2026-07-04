---
doc_status: current
truth_level: review
last_verified_commit: cb9b081 (session-start HEAD; parallel sessions may advance main)
last_verified_date: 2026-07-04
validation_scope: >
  Fable 5 design review of docs/plans/active/usb_bridge_launcher_design.md against
  docs/plans/active/cross_platform_portability_plan.md and repo HEAD. Software-design
  review only — no code changed, no build performed, no bridge run or restarted, no
  hardware validated. Repo claims verified by direct read (file:line cited); external
  macOS/PyInstaller/launchd/TCC claims come from four web-research threads and are
  confidence-labelled with sources. Findings feed the design revision + Codex plan;
  nothing here authorizes implementation by itself.
work_status: delivered
relates_to: usb_bridge_launcher_design.md, cross_platform_portability_plan.md
---

# USB bridge launcher — Fable 5 design review (review · expand · relationship ruling)

## Outcome first

**Verdict: `PASS WITH REQUIRED FIXES`.** The core shape is right — self-contained
`--onedir` `.app`, two install modes, menubar-first UX, watch-logic ported into the app,
reader mechanics routed to the reader spec. Nothing here kills the design. But four
findings are load-bearing enough that the Codex plan would fail on contact with reality
if written from the design as-is:

1. **F1 — A raw `.app` cannot live on the stick the parent plan mandates.** PyInstaller 6
   bundles are symlink-load-bearing; exFAT can't hold them. Ship a DMG on the exFAT stick.
2. **F2 — Temporary mode's run-from-stick lifecycle is wrong for a live set.** Eject is
   blocked while running; a yank kills the lights mid-set. Stage to internal scratch and
   make the stick a key, not a dependency.
3. **F3 — The design's "confirmed" launch profile is already wrong at HEAD.** The watcher
   has six `RBSS_LED_*` flags the design's list omits, and the watcher's own two paths
   diverge from each other. The profile module must be generated from code truth.
4. **F4 — Foreign-Mac first run hits a permission cascade the design never inventories.**
   Local Network (Sequoia+) silently kills zeroconf/Govee-LAN without an Info.plist usage
   string; Stream Deck needs Input Monitoring, sometimes with no prompt at all.

Also material: every pgrep/pkill-based control surface breaks against a frozen binary
(F5 — but the bridge's own flock already guarantees the one-process invariant), and the
runner rework has three concrete unlisted work items (F6). The relationship ruling is
**COMPOSE** — the launcher genuinely is the Mac slice of the portability plan — with one
real contradiction (stick filesystem) and one duplicated milestone to fold.

Surfaces covered per the brief: bundling/runtime → F1, F6, F9, F10; lifecycle → F2, F5,
F8, F12; foreign-Mac first run → F4, F7, F11; live-show failure modes → F2, F5, F7, and
the cleared checks (Rekordbox restart, second plug-in).

---

## Part 1 — Adversarial design review

Severity: **P1** = fix in the design before the Codex plan is written; **P2** = must be
resolved inside the Codex plan; **P3** = note/small fix. Labels: `confirmed` /
`assumed` / `unknown` per claim.

### F1 (P1) — The stick's filesystem breaks the bundle; the design never picks one

- **Location:** design §3.1 (`.app` on the stick) + §1; parent plan §3.5 ("Format the
  stick exFAT").
- **Flaw:** the design puts a raw PyInstaller `.app` on a stick whose filesystem the
  parent plan has already fixed as exFAT — and PyInstaller 6.x onedir bundles are
  symlink-cross-linked (`Contents/MacOS` ↔ `Contents/Frameworks`, 6.0 redesign).
  `confirmed` (external, high): PyInstaller's own docs — onedir builds "can only be moved
  or copied to a filesystem that supports symbolic links"; exFAT/FAT32 have no symlinks.
  A flattened copy breaks the bundle seal, and Apple silicon refuses unsigned/broken-seal
  arm64 code, so the likely result is "damaged"/won't-launch on the friend's Mac.
  (Exact exFAT round-trip behavior: `assumed` — no source tests this precise case; the
  mechanism is documented.)
- **Why it matters:** this is the first thing that happens on show day — stick in, double
  click — and it fails on the operator's happy path, on a stranger's Mac, with a scary
  "damaged" dialog.
- **Required change:** design must name the stick layout: **exFAT stick carrying
  `RBSS Bridge.dmg`** (DMG is one opaque blob to exFAT; mounts as a real symlink-capable
  volume). First-run flow: open DMG → the app itself offers Run temporarily / Install.
  Never a raw `.app` on the stick; never Finder-zip (doesn't preserve symlinks; use
  `ditto`/`hdiutil` in the build). This also keeps the stick Windows-readable (Part 3).
- Sources: pyinstaller.org/en/stable/common-issues-and-pitfalls.html · PyInstaller 6.0.0
  changelog · developer.apple.com/forums/thread/701581 (ditto/DMG guidance).

### F2 (P1) — Temporary mode runs the show off a device someone can pull

- **Location:** design §4 (Temporary), §7 M2.
- **Flaw:** the bridge runs *from* the stick. Two consequences the design misses:
  (a) `confirmed` (macOS unmount semantics): a volume with a running executable can't be
  cleanly ejected — Finder says "disk in use," so the designed
  `NSWorkspaceDidUnmountNotification` → stop → wipe path mostly *can't happen* via a
  normal eject; (b) a physical yank mid-set invalidates the executable's backing pages —
  the bridge (and the lights) die mid-show. Exact failure mode (crash vs wedge) is
  `unknown` — but both are show-killers. A DMG payload (F1) does **not** fix this: the
  mounted image is still backed by a file on the stick. Bonus flaw: cold-starting a
  hundreds-of-MB onedir tree from USB flash is seconds-to-tens-of-seconds (`assumed`,
  mechanism-based) — a non-engineer will double-click twice.
- **Why it matters:** "stick yanked mid-set" is one of the brief's named live-show
  failure modes, and the current design converts it into a guaranteed outage.
- **Required change:** invert the model — **stage to internal scratch, run from there**.
  Launcher copies the payload to `$TMPDIR/rbss-<version>/` (cache by version; first run
  pays the copy once), spawns from the internal disk, and from that moment the stick is
  *only a key*: pull it any time, nothing dies. "Wipe on eject" becomes an explicit
  **End Set** action (Part 2, idea 4) plus stick-unmount as a *signal* to offer cleanup —
  not a load-bearing lifecycle event. Yank becomes a non-event by construction. M2's
  verify step should include a literal mid-run yank test.

### F3 (P1) — The launch profile the design calls `confirmed` is already divergent at HEAD

- **Location:** design §2(a); `scripts/ss_bridge_watcher.sh:122-145` and `:161`.
- **Flaw:** `confirmed` by direct read — the watcher's background path exports the
  design's 14 flags **plus six the design omits**: `RBSS_LED_PHRASE_MONOTONIC=1`,
  `RBSS_LED_MIN_DWELL=1`, `RBSS_LED_CANCEL_PENDING=1`, `RBSS_LED_RT_RECONCILE=1`,
  `RBSS_LED_TRANSPORT_STICKY=1`, `RBSS_LED_TRANSPORT_COOLDOWN=0`
  (`ss_bridge_watcher.sh:137-142`). And the watcher's *own* manual-terminal path — the
  one the operator actually uses via the menubar (`RBSS_BRIDGE_MANUAL=1`,
  `scripts/bridge_menubar.py:1123-1129`) — omits those six (`ss_bridge_watcher.sh:161`).
  So the "one launch profile" the design wants doesn't exist even today; there are two.
  Softener: the divergence is probably behavior-neutral — five of six match code
  defaults (`led_dispatch_coordinator.py:64,69,72`, `led_look_director.py:57`,
  `govee_realtime_runner.py:91` — all default-on; `TRANSPORT_COOLDOWN` default-off);
  `RBSS_LED_PHRASE_MONOTONIC`'s default is `unknown` (env name at
  `led_dispatch_policy.py:29`; semantics not verified here).
- **Why it matters:** the design's §2 parity bar is "identical, not mostly works," and
  its own env inventory fails that bar. If the Codex plan copies the design's list, the
  bundle ships with a profile that never existed.
- **Required change:** the `launch_profile` module must be **derived from code truth,
  not from the design doc** — and must carry more than flags: the log path, status/
  commands paths (F8), laser-config path, and govee-env source are all part of the
  profile. Add an automated parity check (a test that the watcher's exported env equals
  the profile module) so the two remaining consumers can't drift. This *strengthens* the
  design's own §2(a) idea — the evidence shows it's needed, today, not hypothetically.

### F4 (P1) — Foreign-Mac first run: the permission cascade is bigger than the memory grant

- **Location:** design §5 (gaps list) — names MIDI, SoundSwitch, config, memory grant;
  nothing else.
- **Flaw:** the bundle will hit, in order, on a macOS 15/26 friend's Mac:
  1. **Local Network** (Sequoia+; applies to non-sandboxed apps): triggered by zeroconf
     mDNS browse (OS2L discovery — dep at `pyproject.toml:15`) and Govee LAN UDP.
     `confirmed` (Apple TN3179 + 2026 reporting): denial is **silent** — packets drop, no
     error; and **without `NSLocalNetworkUsageDescription` in Info.plist the app is never
     prompted at all and just fails**. Localhost exemption is *not* documented and macOS
     26 has open bugs here — even the OS2L-to-SoundSwitch localhost path should be
     treated `unknown` until M4 verifies it.
  2. **Input Monitoring** for Stream Deck HID (hidapi/IOHIDManager): `confirmed`
     (external): required; sometimes there is **no automatic prompt** — just silent
     `kIOReturnNotPermitted` until the user manually adds the app in System Settings.
  3. **"Background Items Added"** notification + Login Items & Extensions entry for the
     permanent-mode LaunchAgent (macOS 13+; informational but scary to a stranger).
  4. Ad-hoc signing makes it worse over time: TCC keys grants to the designated
     requirement, and for ad-hoc that collapses to the per-build cdhash — **every stick
     update re-triggers the whole cascade** (`confirmed`, Apple DTS forums #730043).
  Good news, also verified: the design's write locations avoid folder-TCC entirely
  (`$TMPDIR` and `~/Library/Application Support` are not TCC-protected), and the
  Application Firewall ships off by default, so the pad/OSC listeners won't prompt for
  most hosts.
- **Why it matters:** "operates normally" (§2) on a foreign Mac dies silently — no
  crash, just no lights on the LAN paths and a dead Stream Deck — exactly the failure a
  non-engineer can't diagnose at a show.
- **Required change:** §5 gains a **permission inventory** (the four items above) and
  Setup gains a **permission concierge**: before each OS prompt, one plain-language
  screen ("Next, macOS will ask about Local Network — that's how the bridge finds the
  lights. Click Allow."), then a doctor-style verify that the grant actually took
  (Part 2, idea 2). The PyInstaller spec must set `NSLocalNetworkUsageDescription` (and
  Bonjour service types). Mitigation to evaluate for the re-grant churn: sign with a
  **free personal-team Apple Development certificate** instead of `-s -` — DTS names it
  as a stable identity, it costs $0 and changes nothing about the (declined)
  notarization stance. Whether a non-Apple self-signed cert also works is **contested**
  in sources — timebox an M1 experiment, else accept per-update re-grants
  (`assumed`/`unknown` respectively). Add an open question to the Codex plan: does the
  OS2L path have a no-mDNS fallback (fixed host:port) if Local Network is denied? If
  not, add one — SoundSwitch transport must not be killable by one missed prompt.

### F5 (P2) — Every pgrep/pkill control surface breaks against a frozen binary; the flock already saves the invariant

- **Location:** design §3.2 ("preserves the one-process invariant (`pgrep -f
  rb_ss_bridge_v2 | wc -l == 1`)"); `scripts/bridge_menubar.py:35-38, 211-224,
  1109-1119`; `scripts/ss_bridge_watcher.sh:97-103`; AGENTS.md §6; the bridge-verify
  skill.
- **Flaw:** `confirmed` — every existing process control matches a *python command
  line*: the menubar's own single-instance guard even hardcodes
  `/Users/bbui/rb_ss_bridge_v2/scripts/bridge_menubar.py` (`bridge_menubar.py:35`), and
  its start/stop uses `pkill -f` on `-m rb_ss_bridge_v2` patterns. A frozen binary's
  argv is `…/RBSS.app/Contents/MacOS/<name> --run-bridge` — none of these patterns see
  it (menubar shows "off" while the bundled bridge runs; a stop button that can't stop).
  **The part the design under-credits:** the bridge already enforces single-instance
  with an `flock` on `/tmp/rb_ss_bridge_v2.lock` and refuses to start a second copy
  (`__main__.py:770-785`, refusal at `:1082-1084`). That lock is command-line-agnostic —
  it holds across any mix of source-run and bundled bridges on one machine. The
  *invariant* survives freezing; the *observability and control tooling* doesn't.
- **Required change:** (a) in bundle mode, process control is **owned child pids**
  (the app spawned `--run-bridge`; it holds the handle) + the flock + status.json
  liveness — no pattern matching; (b) menubar dedupe becomes
  `NSRunningApplication` by bundle ID (the pgrep guard is dead code when frozen);
  (c) name the frozen binary so `pgrep -f rb_ss_bridge_v2` still matches (e.g. binary
  `rb_ss_bridge_v2` inside the .app) — free compatibility with AGENTS.md §6 wording and
  the bridge-verify skill; (d) restate the invariant check for bundle runs in the design
  (lock + status heartbeat, with the pgrep form as a compatibility view); (e) M1 must
  note the coexistence scenario: with the dev watcher running, a bundled launch will be
  *refused by the lock* (correct!) but the watcher will log adopt/start churn — quit the
  source-side menubar/watcher first, or expect noise.

### F6 (P2) — The `--run-bridge` rework is feasible but has three unlisted work items

- **Location:** design §3.2, §6 (risky bit 2, "the biggest unknown").
- **Positive evidence first** (`confirmed` by grep at HEAD): the bridge core has **no**
  `sys.executable`/`-m` re-exec, no `osascript`, and no `multiprocessing` — the runtime
  is threads in one process. Risky bit 2 is therefore *enumerable work, not an unknown*:
  the remaining risks are import collection and native libs (F10), not architecture.
- **The three unlisted items:**
  1. **`PYINSTALLER_RESET_ENVIRONMENT=1`** must be set when the menubar spawns the
     long-lived `--run-bridge` child. `confirmed` (PyInstaller ≥6.9 documented rule for
     children that outlive/restart independent of the parent). Missed, this produces
     exactly the class of subtle in-bundle breakage M1 exists to catch.
  2. **The menubar's Export feature shells `sys.executable -m
     rb_ss_bridge_v2.tools.export_soundswitch_pack`** with `cwd` two levels above the
     repo (`bridge_menubar.py:304-312`, `:48`). Frozen, `sys.executable` is the app
     binary and `-m` means nothing. Either add an `--export-pack` entry mode or hide
     Export in bundle mode (it's an authoring feature; Guest-Mac shows don't export).
  3. **The watcher manages a second process the design never mentions:** the Stream
     Deck sidecar (`ss_bridge_watcher.sh:59-63` spawns `streamdeck/streamdeck_midi.py`,
     which holds its own flock, `streamdeck_midi.py:38`). The bundle runner must own it
     too (`--run-streamdeck` entry or in-process integration) or Stream Deck silently
     dies in bundle mode. Related: the Laser/LED Pad menu items just open
     `127.0.0.1:8765/8766` (`bridge_menubar.py:42-43`), but those servers are separate
     `tools/` processes (`tools/laser_pad_web.py`, `tools/led_pad_web.py`) — on a
     foreign Mac the menu items open a dead URL. Grey them out in bundle v1 (Part 2,
     idea 8 for later).

### F7 (P2) — The MIDI/IAC surface is wider than §5 says, and a virtual port is not a drop-in IAC replacement

- **Location:** design §5 bullet 1.
- **Flaw:** `confirmed` — there are **three IAC-coupled endpoints in two directions**,
  not one: laser/look-selection **out** (`midi_output.py:189`, port name from laser
  config; example default `"IAC Driver Bus 1"`, `config/laser_director.example.json:6`;
  missing port degrades gracefully to `port_unavailable`, `midi_output.py:190-191`);
  MTC **in** (`mtc_reader.py:30`, substring `"IAC Driver Bus 1"`); SoundSwitch pack MIDI
  **in** (`soundswitch_midi_input.py:88`, hardcoded literal). Plus the Stream Deck's own
  virtual **out** named `"Stream Deck"` — which is at `streamdeck/streamdeck_midi.py:530`
  now, not `:431` as both docs cite (stale line ref; fix when folding). IAC is a shared
  loopback *bus*; app-created virtual ports are directional endpoints — swapping one for
  the other changes who must point at what, and SoundSwitch's MIDI mappings are host-app
  state the stick cannot carry. External facts, `confirmed` (cited): IAC is **off** on a
  fresh macOS account; CoreMIDI has **no TCC prompt**; app-created virtual ports are
  visible to every other CoreMIDI client immediately.
- **Required change:** the Codex plan needs a **port map table** (endpoint, direction,
  name source, consumer, foreign-Mac strategy). Recommended default: bridge creates its
  own virtual ports (the Stream Deck precedent proves the mechanism), with "enable IAC
  in Audio MIDI Setup" kept only as a *runbook fallback*, never a code path (Part 3
  explains why: IAC is a Mac-only fork). Runbook must include the one-time SoundSwitch
  MIDI-mapping step on a new host, and the doctor (Part 2) must surface
  `port_unavailable` degradations — today they're silent unless the operator opens the
  laser submenu.

### F8 (P2) — "Everything else is gone" is false: fixed `/tmp` state outlives the scratch wipe

- **Location:** design §4 (Temporary: "everything else is gone").
- **Flaw:** `confirmed` — the runtime writes to fixed `/tmp` paths outside any scratch
  dir: status + commands IPC (`runtime_status.py:16-17` — also the menubar's contract,
  `bridge_menubar.py:40-41`), the instance lock (`__main__.py:770`), session recordings
  (`__main__.py:1531`), Govee device/scene caches (`govee_runtime_sender.py:26-27`),
  OS2L inject default (`os2l_injector.py:22`), palette state + Stream Deck lock
  (`streamdeck_midi.py:38,42`, `led_palette_control.py:19`), log-control file
  (`logging_manager.py:310`, env-overridable), and the watcher-side `/tmp/bridge.log` +
  `/tmp/streamdeck.log`. Content is benign-ish (track names, device IPs, no secrets),
  and `/tmp` purges on reboot — but the design states a guarantee the code doesn't keep.
- **Required change:** either (a) one `RBSS_RUNTIME_DIR` knob threaded through these
  constants via the launch profile — **menubar and bridge must move together** since
  status/commands is their IPC bus — or (b) temporary-mode cleanup deletes an enumerated
  fixed-path list. (a) is the profile-shaped fix and also what Windows needs later
  (plan §3.5's per-OS appdata rule); (b) is the smaller diff. Either way, restate §4's
  trace claim accurately: "OS memory grant + TCC entries persist (accepted); all bridge
  files are removed."

### F9 (P2) — No CPU-arch, min-macOS, or build-interpreter decision

- **Location:** design §3.1/§6 — silent on all three.
- **Facts** (`confirmed`, cited): numpy, python-rtmidi, and hidapi ship **no universal2
  wheels**; pyobjc does. macOS 26 is the last Intel release; an arm64-only app on an
  Intel Mac fails with "Bad CPU type." PyInstaller output is forward-compatible only —
  build on the **oldest** macOS you intend to meet; Homebrew Python inherits high
  deployment targets (`/opt/homebrew/bin/python3` is today's interpreter,
  `ss_bridge_watcher.sh:15`), python.org Python keeps them low.
- **Required change:** state in the design: **arm64-only**, minimum macOS = oldest
  realistic friend's-Mac (pick at build time; document), build venv on **python.org
  arm64 Python**, and the runbook says "Apple silicon Macs only" with the Intel failure
  mode named so it's recognizable.

### F10 (P3) — Asset and dependency-manifest gaps the build must not trust

- `confirmed`: menubar icons load from the **home directory** —
  `/Users/bbui/bridge_icon_*.png` (`bridge_menubar.py:54-58`; graceful text fallback at
  `:1100-1107`). Must become bundle resources (and a proper `.icns`).
- `confirmed`: `pyproject.toml` understates the runtime closure — `dependencies`
  (`pyproject.toml:10-16`) lacks `python-rtmidi` (mido's backend), `streamdeck`
  (Elgato), and `Pillow`, all imported by `streamdeck/streamdeck_midi.py:12-17`; the
  `py-modules` list (`pyproject.toml:33-69`) is stale vs the repo (no `led_*`,
  `govee_*`, most `soundswitch_pack*` — compare AGENTS.md §4). The PyInstaller build
  must collect the **actual source tree + explicit hidden imports**, never the pyproject
  manifest. `assumed` (verify at M1 build): the Elgato lib loads `libhidapi` via ctypes
  from a Homebrew path today — the dylib needs explicit collection.
- Inherited from plan §3.3, still right: `--hidden-import mido.backends.rtmidi`,
  `--collect-data certifi` + `SSL_CERT_FILE` shim. Font use is safe
  (`/System/Library/Fonts/Helvetica.ttc`, `streamdeck_midi.py:242`).

### F11 (P3) — Gatekeeper on the friend's Mac: cleared, with one behavioral rule

- `confirmed` (multi-source): a locally built, never-downloaded app carries **no
  quarantine xattr**; Gatekeeper's first-launch check and App Translocation are both
  quarantine-gated; ad-hoc CDHashes are not machine-locked. Expected: **silent launch**
  on macOS 14/15; same architecture on 26 (`assumed` there — untested case in sources).
  A locally-made DMG/zip does not add quarantine to its contents.
- The rule that keeps it true: **the app must only ever travel by stick or local copy —
  never AirDrop, browser, Mail, or Messages** — any of those adds quarantine, and on
  15+/26 the recovery is the clunky System Settings → "Open Anyway" flow (the
  Control-click bypass is gone). One runbook line + keep M4's `xattr -l` check.

### F12 (P3) — `StartOnMount` mechanics: the design's caveat, made concrete

- `confirmed` (cited): fires on **every** mount (DMGs, Time Machine, network shares),
  never says which volume, has no plist-level scoping — in-app filtering is mandatory
  (marker file, e.g. `/Volumes/*/.rbss_stick`, or volume UUID). `ThrottleInterval` is a
  crash-throttle: a fast-exiting agent can be throttled if two mounts land within 10 s
  (`assumed` edge). Whether StartOnMount also fires for already-mounted volumes at
  login is `unknown` — design the handler idempotent so it doesn't matter.
- **Required shape:** plist runs `open -b <bundle-id>` (Launch Services deduplicates and
  survives the app moving), backed by an in-app `NSRunningApplication` check (the real
  guarantee; `open` alone has LSUIElement quirks). Install with `launchctl bootstrap
  gui/$UID`; uninstall = `bootout` **+ delete the plist** (+ `launchctl enable` on any
  reinstall — bootout leaves the service disabled). Expect the macOS 13+ "Background
  Items Added" notification (pre-explain it to the friend; known OS bug can repeat it —
  `sfltool resetbtm` is the fix, runbook footnote).

### §6 risky-bits disposition (success-criteria gate)

| Design §6 risky bit | Disposition |
|---|---|
| Bundling the PyObjC menubar | **Confirmed feasible** — pyobjc ships universal2/arm64 wheels with PyInstaller support; historical LSUIElement bugs fixed; a real signed `.app` is *required* anyway for TCC identity (F4). Watch items: icon assets (F10), Info.plist keys (F4). |
| Running the bridge in-bundle | **Upgraded from "biggest unknown" to enumerated work** — no re-exec/multiprocessing in core (F6 positive evidence); the real items are `PYINSTALLER_RESET_ENVIRONMENT`, the Export subprocess, the Stream Deck sidecar (F6), and collection completeness (F10). |
| `StartOnMount` idempotency vs one-process | **Upgraded to concrete design** — `open -b` + `NSRunningApplication` + marker-file volume filter (F12); the bridge-level invariant is already lock-enforced (F5). |
| Memory grant under a bundled ad-hoc app | **Remains the top open risk, correctly routed to the reader spec** — unchanged. New intersecting fact for that spec: ad-hoc identity churns per build (F4), so grant persistence across *updates* must be part of the reader-spec's question, and the free-Apple-Development-cert experiment is relevant to it. Cleared en route: `vmmap` is a base-OS binary, not an Xcode-CLT stub (absent from CLT/Xcode dirs on this machine, no xcselect-stub markers, real symbolication linkage) — no hidden dev-tools dependency for the reader's attach path (`rb_memory.py:136-141`). |

### Cleared checks (examined, no finding)

- **Rekordbox restart mid-set:** reader restart/drift handling is in-process
  (`__main__.py:1727-1735` RB_RESTARTED path) and the ported watch logic gates on RB
  presence — bundling changes nothing. `confirmed`.
- **Second plug-in while running:** covered by F12's dedupe + F5's flock; outcome is a
  no-op, which is correct.
- **Config placement choices:** `$TMPDIR` scratch and `~/Library/Application Support`
  are outside TCC's protected-folder set — no folder prompts. `confirmed` (cited).
- **`pgrep`/`lsof` host tools:** base macOS; `lsof` additionally has the DB/ANLZ
  fallback (plan §1.3). `confirmed`.
- **RB DB path** (`config.py:20`) is per-user `~/Library/Pioneer/...` — foreign-Mac
  correct as-is.

**Part 1 verdict: `PASS WITH REQUIRED FIXES`** — F1–F4 amend the design before the
Codex plan; F5–F9 are Codex-plan content; F10–F12 are small but real.

---

## Part 2 — Creative expansion (ranked; each idea = what / why it earns its complexity / cost)

Ranked by operator value per unit of complexity, in this project's ethos: the best idea
is the one that deletes work, the second-best is the one that reuses machinery the repo
already has. The scope cut is deliberately ranked #1.

### Adopt now

1. **Ship Guest-first: defer House Mac (permanent mode) until a House Mac exists.**
   *(the temporary/permanent model itself, rethought — a delete, not an addition)*
   What: v1 has **no first-run mode question**. Double-click → Guest run (leave no
   trace). "Make this a House Mac…" ships later as a buried menu item, not a fork in the
   first-run flow. Why it earns it: the mode choice lands on a non-engineer at the
   moment of maximum time pressure, and the current population of House Macs is zero —
   Brandon's own rig runs from the repo/watcher and friends' Macs are guests until
   someone hosts repeatedly. Deferring deletes v1's entire launchd/BTM/uninstall surface
   (F12), the scariest foreign-Mac moment ("Background items added" on someone else's
   machine), and all of M3 — and the design's own build order already isolates M3, so
   nothing is architecturally foreclosed; the locked decisions explicitly leave the two
   modes challengeable. Cost: zero now; M3 later behind a trigger. Reversal condition:
   the same friend hosts twice → build M3 then, with F12's mechanics ready on the shelf.
2. **Show Doctor — one glanceable "Rig check" before doors.** What: menubar panel that
   probes and green/reds: RB running + build in the offsets table, SS running + OS2L
   connected, MIDI port present (or virtual port created), Govee cloud key + LAN reply,
   Stream Deck opened (Input Monitoring granted), Local Network state, memory grant
   done — each red row with a one-sentence fix. Why: F4/F7 failures are *silent*; this
   is the difference between "no lights, no idea" and "one red row" on a stranger's Mac
   at 21:45. Cost: moderate — the bridge already computes most of it (`runtime_status`,
   midi `degraded_reason`, pack status); this is aggregation + a few probes + strings.
   The highest UX-value *build* item in this review.
3. **The stick is a key — stage-to-scratch launch.** *(F2's required change, kept here
   because it is also the product's best behavior, not just a fix)* What: first run
   copies the payload to internal scratch (cached by version), runs from there; the
   stick is removable the moment the menubar appears; a "Setting up — one time, ~30 s"
   progress line covers the copy so nobody double-clicks twice. Why: converts the worst
   live failure (yank) into a non-event and makes every later launch faster than USB.
   Cost: one staging step + version-keyed cache dir (~15–45 s first copy, `assumed`).
4. **Crash posture: the lights keep playing, recovery is one click.** What: two halves.
   (a) Make the existing fallback doctrine ("open SoundSwitch") automatic and *proven*:
   M2's verify includes `kill -9` on the bridge mid-session → SoundSwitch continues its
   own show, no stuck DMX frame, never frozen-dark. (b) The menubar already polls bridge
   liveness every second — add a crash notification + a **Restart bridge** one-click,
   and a red Doctor row. Why: this is the highest-value failure-recovery item because it
   needs almost nothing — status polling and the restart path both exist; it turns a
   mid-set death from booth-debugging into a ten-second blip the dance floor never
   notices. Cost: a notification, a menu action, one M2 verify case.
5. **Friend-facing consent card.** What: before the first Guest run (and before the
   admin memory grant), one plain-language screen on *their* Mac: what the app reads
   (Rekordbox's playback state), what it touches (lights on this network), what it
   leaves (one admin approval + permission entries — nothing else after End Set), and
   where Quit lives. The End Set completion notification is the matching receipt
   ("Cleaned up — only the memory approval remains."). Why: it's the friend's machine
   and the friend's admin password; thirty seconds of honesty converts the scariest
   prompt an unsigned hobby app can make into an informed yes — and F8's fixes make the
   claim literally true. Cost: one dialog + strings; zero new mechanism.
6. **The stick presents itself: runbook, names, identity.** What: `START HERE.html` at
   stick root — the five host-prep steps (SS installed + project + one-time MIDI
   mapping; RB running; the permission cascade with "click Allow" framing;
   Apple-silicon-only; never AirDrop the app) plus an "if macOS says it can't open"
   rescue section (F11's Settings → Open Anyway path). Modes named **"Guest Mac — leave
   no trace"** / **"House Mac — auto-start when I plug in."** Volume label, `.icns`, DMG
   background so the thing reads as the *RBSS Show Stick*, not a folder of mystery
   files. And one explicit decision: the Terminal tail monitor is **dev-only** — bundle
   mode's answer is menubar status + an "Open log" item (no osascript/Automation prompt
   on a stranger's Mac). Why: §5 promises a runbook no artifact backs; names are how a
   non-engineer picks right; the monitor call closes a silent UX divergence. Cost: near
   zero — an HTML file, strings, an icon.
7. **End Set button.** What: one menubar action — stop bridge → optional show receipt
   (idea 12) → wipe scratch + the enumerated fixed `/tmp` files (F8) → "Safe to pull the
   stick." Why: gives Guest mode a *deliberate* ending instead of an eject race, and
   it's the trace-wipe proof moment — the friend watches it clean up. Cost: small; every
   piece already exists as an operation. (Later footnote: an idle auto-clean — bridge
   idle + RB gone for hours → offer End Set — guards the "left it running on their Mac
   overnight" case.)
8. **$0 stable-identity experiment (timeboxed, in M1).** What: try signing with a free
   personal-team **Apple Development** cert instead of `-s -`; verify TCC grants survive
   a rebuild. Why: F4's re-grant-every-update churn disappears if it works — and it
   feeds the reader spec's grant-persistence question. Cost: ~an hour in M1; no $99, no
   notarization change. If it fails: accept re-grants, one runbook line. (`unknown`
   whether it fully works — that's why it's an experiment, not a dependency.)

### Adopt later

9. **Lights-check without the decks (replay demo).** *(the flagship later feature)*
   What: menubar **"Test the lights"** plays a bundled 60–90 s recorded session through
   the real output stack — SoundSwitch rotation, look selection, laser scenes, LED/Govee
   — with no Rekordbox needed. This is the parent plan's Phase-2 `ReplaySource` promoted
   from test helper to show-day tool, plus one canned session file on the stick
   (`session_replayer.py` already injects recorded events at the StateManager boundary —
   the mechanism exists today; only the runtime selection doesn't). Why: the scariest
   show-day question on a foreign Mac is "will the lights actually fire when the first
   track drops?" — this answers it before the DJ gear is out of the bag, cleanly
   separates bridge-works from host-config-broken for the Doctor to point at, and
   doubles as the honest way to demo the rig to people. Why not now: rides plan Phase 2.
   Cost: Phase-2 dependency + a recorded session + one menu item. Live-safety rule:
   replay refuses to start while Rekordbox is running, so two drivers can never race.
10. **Phone pad over QR — the forgot-the-Stream-Deck fallback.** What: once the pads
    bundle (idea 15), "Control from phone" surfaces the existing QR flow (the AWR-113
    QR/iOS work) so a phone becomes the blackout/look surface. Why: "the Stream Deck is
    at home" is a real 1 a.m. failure and the phone is always in a pocket — a dead
    control surface becomes a 20-second recovery. Cost: rides idea 15 + existing QR
    work; F4's Local Network/firewall notes apply.
11. **Clone-a-spare-stick button.** What: insert a blank stick → menubar copies DMG +
    live configs + `govee.env` + runbook + canned session → hash-verifies → "Spare
    ready." Why: the stick is now show-critical hardware whose *gitignored* state (live
    configs, keys) a by-hand Finder copy of the DMG alone would silently miss — exactly
    the copy a human gets wrong; two sticks in the bag beats one. Cost: small — `ditto`
    + verify over the file list F3's profile module already knows.
12. **Show receipt.** *(absorbs save-diagnostics)* What: End Set writes
    `shows/<date>/` to the stick — set duration, tracks seen, drops fired, degradations,
    log tail, optional session recording. Why: show-night bugs get debugged at home with
    real evidence, and a set history is a free hobby artifact. Cost: aggregation of
    existing status/log + one copy; the stick is written only on explicit action.
13. **Update-on-insert for House Macs.** What: on stick insert, the House Mac compares
    stick bundle version vs installed copy and offers a one-click update. Why: once
    House Macs exist, stick/host skew is inevitable; this keeps the stick the single
    source of truth. Cost: version compare + staged copy + relaunch. Contingent twice
    over: needs idea 1's reversal (a House Mac existing at all) and wants idea 8 first
    (else every update re-triggers the F4 permission cascade).
14. **Venue profiles.** What: named config packs on the stick (Home / venue X: Govee
    targets, laser personality, LED look defaults) with a launch-time picker. Why:
    per-venue tuning is real — but Govee LAN auto-discovery already landed and covers
    the drifting-IP case, so this earns rent only when a second *tuned* venue actually
    exists. Cost: config schema + picker; moderate. Wait for venue #2.
15. **Bundle the pad web tools as an optional entry mode.** What: `--run-pads` serving
    `tools/laser_pad_web.py` / `led_pad_web.py` so the phone pads work on foreign Macs
    too; v1 greys the menu items out (F6). Cost: another entry mode + LAN listener
    implications (F4 firewall note).

### Explored and rejected

- **R1 — APFS second partition on the stick.** Solves F1 without a DMG, but Windows
  can't read APFS and older Windows exposes only the first partition; it quietly
  forecloses the parent plan's one-stick future. DMG-on-exFAT gets the same result
  without the fork. (Part 3, Contradiction A.)
- **R2 — universal2 build.** Three deps ship no universal2 wheels (F9); Intel Macs are
  one release from EOL; the audience is ~zero. Document "Apple silicon only" instead.
- **R3 — Bundle integrity manifest / hash-verify at launch.** Safety theater for a solo
  rig; the arm64 signature seal already fails loudly on a corrupted bundle.
- **R4 — A real auto-update framework (Sparkle-style).** The stick *is* the update
  channel; idea 13 covers the need with a file copy.
- **R5 — Automating SoundSwitch/Rekordbox host-side setup.** SS MIDI learn and RB prefs
  are app-internal state; scripting them means fragile UI automation + an Automation TCC
  prompt. The runbook line + Doctor check is the honest version.
- **R6 — Standalone no-Rekordbox "attract mode" (generative show).** New scope the
  design already excludes (§8) and the plan only promises not to foreclose (§1.4); the
  replay demo (idea 9) delivers the practical 90% — prove the rig, demo the rig — with
  zero new scope.
- **R7 — Auto-opening Terminal monitors / osascript UI on foreign Macs.** An Automation
  TCC prompt plus a Terminal dependency, spent on a dev convenience; menubar status +
  "Open log" covers it (idea 6).

---

## Part 3 — Relationship ruling: launcher spec vs portability plan

**Ruling: `COMPOSE` — confirmed, with one contradiction to resolve and two dedups.**
The launcher is genuinely the Mac slice; nothing in it structurally forecloses the
Windows superset — *provided* the two items below are folded.

**Confirmed compositions (specifics):**
- Packaging identity: design §3.1 (`--onedir --windowed`, ad-hoc) is exactly plan §3.1's
  recommendation including the onefile prohibition rationale. No drift.
- Notarization stance: design §1 locked decision restates plan §0's operator-decision
  block (2026-07-04), including the Hardened-Runtime upside for §7. Consistent.
- Live safety: design §7's closing note ("strobe floor … already in place") correctly
  sequences against plan §4/Phase 2 — the floor lands before any foreign-machine run in
  both docs.
- Scope walls: design §8 (no standalone mode; reader mechanics out) mirrors plan §1.4
  and §7's named dependencies. The launcher never designs the grant — verified: §3.3/§5
  only *invoke* it.
- Platform-gating precedent: plan §1.3 cites `pyproject.toml:12`'s darwin marker; the
  launcher's Mac-only components (menubar §3.4, launchd §3.3/§4) sit exactly where that
  precedent puts them — in per-OS units a Windows target replaces, not patches.

**Contradiction A (must fix — F1): stick filesystem.** Plan §3.5: "Format the stick
exFAT … assume the media is read-only." Design §3.1: raw `.app` on the stick. Both
cannot hold (symlink evidence, F1). Resolution that preserves the composition: exFAT
stick, Mac payload as a DMG beside a future `windows/` folder — one stick, both worlds.
Raw-`.app`-on-APFS would resolve F1 too, but it makes the stick Mac-only and quietly
breaks plan §3.5 — reject (Part 2, idea 9).

**Contradiction B (dedupe): design §7 M1 ≡ plan Phase 1.** Both are "package today's
bridge with PyInstaller ad-hoc, run on Brandon's Mac, prove the reader attaches and
subsystems drive" (design §7.1's verify vs plan Phase 1's deliverable/verify). Same
milestone, two docs. The Codex plan must implement it **once**, cross-referencing both,
or two `.spec` files and two verification harnesses will drift.

**Tensions (not contradictions — fold as decisions):**
- **MIDI seam (the ruling's key question).** Design §5's virtual-port fix is the macOS
  half of plan §1.3's hard Windows blocker (python-rtmidi cannot create virtual ports on
  Windows). If Codex implements it as an inline "if port missing, open virtual" branch,
  Windows later needs surgery; if it lands as a small port-strategy seam ("ensure
  look-selection/laser/MTC endpoints exist" with a per-OS impl), the loopMIDI/named-port
  Windows variant plugs in. The design's alternative — "have Setup enable/create the IAC
  bus" — is Mac-only and would fork the launch path; acceptable *only* as a runbook
  fallback, never the code path. With F7's port map + the seam, the launcher's launch
  profile remains the base a Windows target extends. `confirmed` need, from plan §1.3 +
  F7 evidence.
- **Launch profile shape.** Design §2(a)'s shared module composes with Windows only if
  it owns *paths* with per-OS resolution (plan §3.5's appdata rule) — F3/F8 already
  force that for macOS reasons, so alignment is free if done now. Also resolve the
  design's internal wobble: §3.2 "watcher stays untouched" vs §2(a) "both … read one
  source" — recommend the watcher reads the profile (a small touch, and it's the
  design's own anti-drift principle); if the watcher truly stays frozen, say explicitly
  that dev-watcher parity is enforced by the F3 test instead.
- **Evidence dedup.** Design §5 restates plan §1.3's virtual-MIDI research (and both
  carry the stale `streamdeck_midi.py:431` cite — now `:530`). When folding, keep the
  canonical statement in the plan and a pointer in the design, so the next drift has one
  place to land.

**Registry note:** both docs are registered (AWR-122, AWR-120) with "Unreviewed" notes —
this review discharges the review step for AWR-122; update its note when folding.

---

## Evidence appendix (load-bearing external sources)

Four parallel research threads (Gatekeeper/ad-hoc; launchd/StartOnMount; PyInstaller
bundling; TCC surface), 2026-07-04. Key citations backing the findings above:

- PyInstaller common-issues (symlink filesystems; `PYINSTALLER_RESET_ENVIRONMENT`;
  onefile vs onedir): pyinstaller.org/en/stable/common-issues-and-pitfalls.html
- PyInstaller 6.0.0 changelog (bundle restructure): pyinstaller.org/en/v6.0.0/CHANGES.html
- Apple TN3179 / NSLocalNetworkUsageDescription (Local Network scope, silent denial,
  plist key requirement): developer.apple.com/documentation/technotes/tn3179 ·
  eclecticlight.co 2026-01-14 Local Network deep-dive
- Apple DTS on TCC identity vs ad-hoc (re-grant churn; stable-identity recommendation):
  developer.apple.com/forums/thread/730043
- Quarantine/Gatekeeper/translocation gating: eclecticlight.co 2020-10-29 (quarantine),
  2023-05-09 (translocation); Apple "Open Anyway" flow:
  support.apple.com/guide/mac-help/mh40617
- launchd StartOnMount semantics + BTM: launchd.info · manpagez.com launchd.plist(5) ·
  support.apple.com/guide/deployment/depdca572563 (Login Items & Extensions)
- Input Monitoring for HID/hidapi: developer.apple.com/forums/thread/724608 ·
  nachtimwald.com 2020-11-08
- IAC off-by-default; app virtual ports visible without setup: vochlea.com IAC tutorial ·
  skratchdot.com 2016 virtual-MIDI notes (mechanism unchanged; `confirmed` in-repo by
  `streamdeck_midi.py:530` working today)

Repo evidence is cited inline as `file:line` throughout; all repo claims were verified
by direct read at review time, not taken from either design doc.

*Stopping here per the brief — no implementation planning beyond the findings above.*
