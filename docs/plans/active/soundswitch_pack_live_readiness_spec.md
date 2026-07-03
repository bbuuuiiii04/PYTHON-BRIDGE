---
doc_status: active-plan
truth_level: code-verified
last_verified_commit: 87d5ed6
last_verified_date: 2026-07-02
validation_scope: Codex implementation spec preparing the SoundSwitch pack runtime for operator live use and hardware validation — normal-launch truth-check default-off, watcher sync helper, read-only live-readiness checker, operator runbook. Software/docs only; Codex performs no live, process, serial, or MIDI action.
---

# Codex Implementation Spec — SoundSwitch Pack Live-Readiness Preparation

## Part A — Context & root cause (verified; read, do not implement)

The pack runtime software side is complete (2026-07-02 finalization pass; see
`docs/plans/active/soundswitch_exporter_remaining_work.md`). What stands between
"software-complete" and "operator runs hardware validation" is launch/config
hygiene, not code:

1. **Truth-check is pinned on in the OPERATOR's launcher, not the repo's.**
   The repo watcher `scripts/ss_bridge_watcher.sh` sets no Art-Net truth flags
   [confirmed — no `RBSS_ARTNET_*` in the repo copy]. The deployed root copy
   `/Users/bbui/ss_bridge_watcher.sh` hardcodes `RBSS_ARTNET_TRUTH_CHECK=1` and
   `RBSS_ARTNET_UNIVERSE=1` at lines 98-99 (watch path) and again inside the
   manual-session `do script` line 115 [confirmed by grep this session]. The
   2026-07-02 truth-exam doc recorded this as the "Disarm / Operator Control
   Blocker": a normal menubar restart silently re-arms truth mode. The two
   copies have drifted (root also carries `RBSS_POS_CHAIN_SKIP_OBJC=1` and the
   telemetry CSV env not present in the repo copy) [confirmed].
2. **Live pack config is default-off by design.** The example config
   `config/soundswitch_pack_player.example.json` ships
   `enabled:false, dry_run:true, output_backend:"none", enttec_port:""`,
   identity `fixture_map` 1..19, `phase_offset_beats: 0.0` [confirmed]. The
   live gitignored `config/soundswitch_pack_player.json` must be edited by the
   OPERATOR (never committed; reload/export never enables output).
3. **A hardware procedure exists but predates the pack surface.**
   `docs/validation/soundswitch_hardware_validation_procedure.md` covers the
   reviewed non-Autoloop matrix with kill-path/dark-baseline framing;
   `docs/validation/soundswitch_hardware_runs/TEMPLATE.md` is the evidence
   template [confirmed files exist; content anchored on the non-Autoloop
   route]. The current validation needs: scripted witness playback, native
   autoloop (selection-beat anchor + `phase_offset_beats` A/B), static
   press/toggle including between-tracks idle pads, blackout precedence,
   seek/scrub dark-hold, and a transition — reflecting the 2026-07-02 fixes.
4. **Expected-to-pass state** [confirmed this session]: suite 2665 OK, proof
   gate 29/0/0, active lanes `unverified_parity=0`, `pack_start_failed`
   fail-closed already live-proven with the Enttec absent.

## Part B — Tasks (implement exactly, in order; commit after each)

### Absolute rules
- Codex performs NO live action: never start/stop/restart the bridge, never
  open a serial/MIDI port, never send runtime commands, never touch
  SoundSwitch/Rekordbox, never modify files outside the repo checkout
  (`/Users/bbui/ss_bridge_watcher.sh` is operator-owned — provide a sync
  helper, do not run it).
- Never commit `config/soundswitch_pack_player.json`, `config/laser_director.json`,
  `govee.env`, serial device paths embedded anywhere outside example/docs, or
  `config/led_look_director.json.backup_1781599611`.
- Do not weaken: default-off truth check, no-implicit-hot-enable, validate-first
  swap, fail-closed `pack_start_failed`.

### Task 1 — `scripts/ss_bridge_watcher.sh`: explicit opt-in truth mode

Make the repo watcher the single canonical launcher able to serve both modes:

- Near the top (beside `MANUAL_MODE="${RBSS_BRIDGE_MANUAL:-0}"` at `:15`), add:

```bash
TRUTH_MODE="${RBSS_BRIDGE_TRUTH:-0}"
TRUTH_ENV=()
if [ "${TRUTH_MODE}" = "1" ]; then
    TRUTH_ENV=(RBSS_ARTNET_TRUTH_CHECK=1 "RBSS_ARTNET_UNIVERSE=${RBSS_ARTNET_UNIVERSE:-1}")
fi
```

- Inject `"${TRUTH_ENV[@]}"` into the single `env`-block launch site
  (the hard-coded flag block starting near `:114`) so DEFAULT launches carry NO
  truth flags and `RBSS_BRIDGE_TRUTH=1` restores the exam configuration
  exactly. If the repo copy has more than one launch site (watch + manual
  `do script`), inject into every one; keep quoting exactly as shown so an
  empty array expands to nothing under `set -u` if enabled.
- Fold in the two root-copy drift items so the repo copy is a strict superset
  of today's operational launcher: add `RBSS_POS_CHAIN_SKIP_OBJC=1` and the
  `RBSS_SMART_DROP_TELEMETRY_CSV` env exactly as the root copy has them
  [confirmed present in root copy line 115].

### Task 2 — `scripts/sync_bridge_watcher.sh`: operator-run sync helper (new, ~20 lines)

```bash
#!/bin/bash
# Operator-run: deploy the repo watcher over the root copy with a backup.
# Never started automatically; takes effect at the NEXT operator-initiated
# bridge start. Refuses to run while a bridge process is alive.
```

- Source paths: repo `scripts/ss_bridge_watcher.sh` → `/Users/bbui/ss_bridge_watcher.sh`.
- Behavior: if `bridge_pids`-style pgrep (copy the exact pattern from the
  watcher `:89-91`) finds a live bridge process, print a refusal and exit 1
  (deploying mid-show is pointless and confusing — the running process keeps
  its env). Otherwise `cp -p` the current root copy to
  `/Users/bbui/ss_bridge_watcher.sh.bak-<epoch>` then install the repo copy,
  `chmod +x`, print old/new `shasum -a 256`.
- `bash -n` clean; mark executable.

### Task 3 — `tools/check_pack_live_readiness.py`: read-only go/no-go checker (new)

One command the operator runs before a hardware session. STRICTLY read-only:
stat/exists/read JSON only — never open the serial device, never signal
processes, never send commands. Checks (each prints PASS/FAIL/WARN + one plain
sentence):

1. Live config `config/soundswitch_pack_player.json` exists, parses via
   `load_soundswitch_pack_player_config()` (import the real loader — no
   duplicate parsing), and reports `enabled`, `output_backend`, `dry_run`,
   `enttec_port` non-empty, `phase_offset_beats` value. FAIL when
   `enabled=true` with `output_backend!="pack"` or `dry_run=true` (misarmed);
   WARN when fully default-off (expected before the operator arms it).
2. Canonical pack manifest at the configured `pack_path`: parses, active
   `parity_lanes.unverified_parity == 0`, prints lane counts + `pack sha12`.
3. Enttec device node: `Path(enttec_port).exists()` only (existence, no open).
   WARN-not-FAIL when absent (expected until plugged in).
4. Watcher sync: repo `scripts/ss_bridge_watcher.sh` vs
   `/Users/bbui/ss_bridge_watcher.sh` sha256 — WARN on drift, and FAIL if the
   ROOT copy contains `RBSS_ARTNET_TRUTH_CHECK=1` outside a
   `RBSS_BRIDGE_TRUTH` guard (the truth-rearm blocker).
5. Exactly-zero-or-one bridge process via the same pgrep pattern (report only —
   informational, never kills).
- Exit code 0 iff no FAIL. `--json` flag emits a machine dict (sorted keys).
- Structure every check as a pure function taking injected paths/readers so
  tests never touch the real machine state.

### Task 4 — `docs/validation/soundswitch_pack_live_validation_runbook.md` (new)

Operator-facing, plain language, one page. Sections:

1. **Prep (software)**: save + quit SoundSwitch → menubar `Export from
   Soundswitch` → expect green/`Exported`; run
   `python3 tools/check_pack_live_readiness.py`.
2. **Arm (operator-only)**: edit `config/soundswitch_pack_player.json`:
   `enabled: true`, `output_backend: "pack"`, `dry_run: false`,
   `enttec_port: "/dev/cu.usbserial-EN396681"`, `phase_offset_beats: 0.0`;
   plug the Enttec; re-run the readiness checker (device check flips PASS).
3. **Launch**: menubar start only (`RBSS_BRIDGE_MANUAL=1` path); verify
   `pgrep -f rb_ss_bridge_v2 | wc -l` == 1; confirm SoundSwitch is NOT running
   (SS-present = pack deliberately dark); confirm dark idle baseline and a
   reachable physical kill (defer to
   `soundswitch_hardware_validation_procedure.md` for the safety framing —
   this runbook does not restate it).
4. **Validation matrix** (each row: action → expected → record in TEMPLATE):
   scripted witness track plays and matches the show; pause/resume (≤0.5 s hold
   then dark; resume re-lights); stop (dark); backward+forward drag-scrub
   (dark during drag, re-lights ≈0.6 s after release); hotcue jump (brief dark,
   instant resume); autoloop arm + one full 32-beat wrap; autoloop A/B with
   `phase_offset_beats` 0 vs ±1 to confirm 0 is correct (two-flight
   calibration from roadmap §3); static press + release, toggle on/off, press
   DURING idle between tracks (must work — 2026-07-02 fix); blackout over
   scripted, over autoloop, over held static, during idle; one deck-to-deck
   transition; emergency kill rehearsal + known-dark restore.
5. **Closeout**: restore config default-off if desired, fill
   `docs/validation/soundswitch_hardware_runs/TEMPLATE.md`, commit the evidence
   file (sanitized — no ports/paths/serials).

Header: `doc_status: active-plan` (flip to a validation record pointer after
the run). Cross-link from the hardware procedure doc with ONE added sentence;
do not rewrite the reviewed procedure.

### Task 5 — docs/contract updates

- Roadmap `docs/plans/active/soundswitch_exporter_remaining_work.md`: under
  Remaining work §2/§5, note the runbook + readiness checker as the live gate's
  entry point.
- `docs/validation/software_test_inventory.md`: add the new tests.
- If `docs/agents/change_contracts.yml` has no glob covering
  `scripts/ss_bridge_watcher.sh` or `tools/check_pack_live_readiness.py`,
  extend the `soundswitch_pack_player` contract's `code_globs` FIRST (anti-drift
  rule), then edit code.

## Part C — Invariants that MUST still hold (live safety)

- Codex executes nothing live: no bridge start/stop, no serial/MIDI open, no
  runtime command appends, no writes outside the repo. The sync helper and the
  config arming are OPERATOR actions the docs describe.
- Default launch = truth-check OFF; truth mode only via explicit
  `RBSS_BRIDGE_TRUTH=1`; `RBSS_ARTNET_UNIVERSE` alone must still emit nothing
  (existing runtime invariant, unchanged).
- Menubar-only launch discipline preserved (`RBSS_BRIDGE_MANUAL=1`); the
  watcher's single-process kill/monitor semantics unchanged.
- Reload/export still never enables output; enabling requires the operator's
  real config (`output_backend=pack`, `dry_run=false`, port) exactly as today.
- The readiness checker adds no dependency into the bridge runtime and is never
  imported by `rb_ss_bridge_v2` runtime modules.
- No secrets/paths/serials in committed docs beyond what already appears in
  example configs and existing validation docs.

## Part D — Tests

- `tests/test_check_pack_live_readiness.py`: pure-seam tests with injected
  paths/fixtures — (1) fully-armed config + present device + synced watcher →
  exit 0, all PASS; (2) `enabled=true, dry_run=true` → FAIL misarmed;
  (3) missing device → WARN not FAIL; (4) root watcher containing an unguarded
  `RBSS_ARTNET_TRUTH_CHECK=1` → FAIL; (5) unverified lanes ≠ 0 → FAIL;
  (6) `--json` output keys stable/sorted.
- Shell syntax gates: a small test (or extend an existing tooling test) running
  `bash -n scripts/ss_bridge_watcher.sh` and `bash -n scripts/sync_bridge_watcher.sh`.
- Watcher truth-mode logic: test via `bash -c` sourcing the TRUTH_ENV block
  with `RBSS_BRIDGE_TRUTH` unset/`1` and asserting the composed env string
  (keep the block extractable or test the launch line with `grep`).

## Part E — Acceptance (definition of done)

- [ ] `python3 -m unittest discover tests` green; docs gates
      (`check_docs_metadata` / `check_agent_contracts` / `check_docs_drift`)
      green; `git diff --check` clean.
- [ ] `python3 tools/check_pack_live_readiness.py` runs on this machine and
      correctly reports the CURRENT state (expected today: WARN default-off
      config or FAIL misarmed only if operator already armed it; WARN device
      absent; FAIL root-watcher unguarded truth flags until the operator runs
      the sync helper) — paste its output in the report.
- [ ] No file outside the repo modified; no live config committed; no process
      started.
- [ ] Commit messages: `Watcher: default-off truth mode with explicit opt-in`,
      `Add pack live-readiness checker and sync helper`, `Add pack live
      validation runbook`.
- Report back: readiness-checker output, the exact env-injection diff lines in
  the watcher, and confirmation the root copy was NOT touched.

## Adversarial self-review (already applied to this spec)

Forced failure scenario: operator runs the sync helper while the bridge is
live — the running process keeps its old env, the operator believes truth mode
is off, and the next crash-restart flips behavior mid-show; hence the helper's
hard refusal while any bridge process exists. Second: the readiness checker
opening the serial port to "test" it would steal the port from a
starting bridge or wake hardware — hence existence-stat only, stated as an
absolute rule. Third: making the menubar auto-arm truth mode again via a
convenience toggle would recreate the original operator-control blocker — the
only truth entry point is the explicit `RBSS_BRIDGE_TRUTH=1` env at launch.
