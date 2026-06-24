---
doc_status: current
truth_level: code-verified-procedure
last_verified_commit: f6910f9
last_verified_date: 2026-06-24
validation_scope: one local non-Autoloop SoundSwitch pack setup; procedure only; SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED until a completed run record exists
---

# SoundSwitch Hardware Validation Procedure

This procedure is an operator-run safety gate for one local SoundSwitch 2.10.3 direct-DMX setup.
It does not authorize Codex to edit live config, control a process, open a device, or operate
hardware. Copy the run template before starting and record each result before continuing.

Stop at the first failed or unknown gate. Record `FAIL` or `INCOMPLETE`; do not improvise another
stimulus. T7d capture, phase derivation, and native Autoloop DMX are outside this procedure.

## 1. Offline software gate

These checks are read-only with respect to runtime and hardware:

```bash
git rev-parse HEAD
python3 -m unittest \
  tests.test_state_manager_pack_driver \
  tests.test_soundswitch_pack_commands \
  tests.test_runtime_status \
  tests.test_bridge_menubar \
  tests.test_soundswitch_frame_sender \
  tests.test_enttec_dmx_pro \
  tests.test_soundswitch_pack_startup
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
git diff --check
```

Run the current-project proof to a private temporary directory. Supply the canonical project path
without pasting it into the run record:

```bash
python3 tools/prove_soundswitch_pack_generation.py \
  --project "$PRIVATE_CANONICAL_PROJECT" \
  --output-dir /tmp/rbss-soundswitch-hardware-proof
```

Require `PASS_IMPLEMENTATION_MAY_BEGIN` with no FAIL or INCOMPLETE result. Record only the bounded
verdict and counts. A failure stops the procedure before any operator action. This proof is
software/wire evidence; it does not prove physical output.

## 2. Operator setup gate

- `OPERATOR ACTION — approval required:` Copy
  `docs/validation/soundswitch_hardware_runs/TEMPLATE.md` to the dated run path and fill the
  non-private environment fields.
- `OPERATOR ACTION — private local check:` Confirm the canonical pack and ignored live config exist.
  Record only a redacted config SHA-256, never the config body or its path.
- `OPERATOR OBSERVATION:` Confirm the physical fixture map, exclusive Enttec ownership,
  SoundSwitch 2.10.3 project/profile, controller mapping, a low-risk static look, and the physical
  kill method.
- `OPERATOR ACTION — physical safety check:` Put the physical kill within immediate reach. Do not
  enable output unless this is confirmed.

Do not commit local paths, ports, aliases, device names, fixture serials, project UUIDs, secrets,
raw exceptions, raw status files, or config contents.

## 3. Exact bridge-process gate

Use the same anchored detector as `scripts/bridge_menubar.py`:

```bash
pgrep -f '^[^[:space:]]*(python3|Python)[^[:space:]]*([[:space:]]+-u)?[[:space:]]+-m[[:space:]]+rb_ss_bridge_v2$' | wc -l
```

It matches only a Python executable running optional `-u` and then
`-m rb_ss_bridge_v2`. It excludes:

- `bridge_menubar.py`;
- `ss_bridge_watcher.sh`;
- exporter subprocesses;
- tests;
- shell, grep, and pgrep commands;
- unrelated processes whose argv merely contains `rb_ss_bridge_v2`.

- `OPERATOR ACTION — transport:` Stop Rekordbox transport in the room.
- `OPERATOR ACTION — controller:` Physically release Static Look and blackout controls.
- `OPERATOR OBSERVATION:` Confirm the agreed safe fixture state and reachable physical kill.
- `OPERATOR ACTION — process stop:` Stop the bridge through the menubar and allow graceful zero.
- `OPERATOR ACTION — process check:` Run the exact detector and require `0` before editing live
  config. Any other result stops the run.

The copied status file cannot prove transport stopped, controller holds released, fixture darkness,
Enttec darkness, or physical-kill reachability. Those are operator observations.

## 4. Explicit enable and start gate

- `OPERATOR ACTION — live config edit:` With zero bridge processes, set only the already-supported
  ignored-config fields to `enabled=true`, `dry_run=false`, `output_backend=pack`, and fill the
  verified local fixture map and Enttec alias. Do not print or commit the file.
- `OPERATOR APPROVAL GATE — menubar start:` Immediately before clicking start, obtain explicit
  operator approval for this live restart. Without approval, stop here.
- `OPERATOR ACTION — device/process start:` Click the existing menubar start action. This may open
  controller MIDI input and the Enttec serial path.
- `OPERATOR ACTION — process check:` Run the exact detector and require exactly `1`. Zero or more
  than one stops the run; engage the physical kill for any unexpected light.
- `OPERATOR OBSERVATION:` Require a fresh copied status with pack enabled/backend pack, idle
  software-zero state, and physically dark fixtures while transport and overlays remain idle.

`software_zero_frame=true` proves only that the rendered CH1-CH19 software frame is zero.
`frame_count` counts attempted software frames. Neither field proves serial send success, Enttec
acceptance, or physical darkness.

## 5. Fixture and OS2L sequence

Perform one row at a time and record expected versus observed behavior before continuing:

1. `OPERATOR OBSERVATION — safe zero:` Confirm idle software zero and fixture darkness.
2. `OPERATOR ACTION — fixture stimulus:` Hold one known low-risk Static Look.
3. `OPERATOR ACTION — fixture stimulus:` Release the Static Look.
4. `OPERATOR ACTION — Rekordbox transport:` Play one known scripted track; do not use Autoloop.
5. `OPERATOR ACTION — controller blackout:` Hold healthy pack blackout.
6. `OPERATOR ACTION — controller blackout:` Release blackout.
7. `OPERATOR ACTION — controller degradation:` While a Static Look is held and the known scripted
   base continues, create only the pre-agreed low-risk controller-degradation condition. Confirm the
   manual overlay releases while the scripted base continues; stop on any other behavior.
8. `OPERATOR ACTION — Rekordbox transport:` Stop the scripted track.
9. `OPERATOR ACTION — process stop:` Stop the bridge gracefully through the menubar.

For scripted play and stop, record only OS2L `connected` and before/after deltas for sent,
send-error, and drop counters. Never record the endpoint. Also record sanitized observations for
the pack/export row, bridge log category, lasers, LEDs/Govee, and Rekordbox reader state. Do not tune
those subsystems during this run.

## 6. Emergency rehearsal and known-dark restore

1. `OPERATOR ACTION — low-risk stimulus:` Start the agreed low-risk non-zero look.
2. `OPERATOR ACTION — physical emergency kill:` Engage the physical kill and keep it engaged.
3. `OPERATOR OBSERVATION:` Confirm every affected fixture is dark. Status cannot prove this.
4. `OPERATOR ACTION — graceful process stop:` With the physical kill still engaged, stop the bridge
   gracefully so the sender attempts a zero write. Do not use `kill -9`; process death can leave the
   Enttec retransmitting stale non-zero output.
5. `OPERATOR ACTION — default-off config restore:` With the physical kill still engaged and zero
   exact bridge processes, restore the ignored config to `enabled=false`, `dry_run=true`, and
   `output_backend=none`.
6. `OPERATOR ACTION — Enttec/DMX reset:` If the graceful zero write failed, is unknown, or cannot be
   verified, do not restore physical output. Power-cycle/reset the Enttec/DMX path or use the
   pre-agreed equivalent method to establish a known-dark baseline.
7. `OPERATOR OBSERVATION — known-dark baseline:` Record how darkness was physically confirmed. A
   software status field is not sufficient.
8. `OPERATOR APPROVAL GATE — physical restore:` Obtain separate explicit approval, then and only
   then restore the physical output path.

If the known-dark baseline cannot be proven, leave the physical kill engaged and record `FAIL` or
`INCOMPLETE`. The menubar laser emergency item is not pack-DMX emergency proof.

## 7. Closeout

- `OPERATOR ACTION — default-off verification:` Confirm the ignored config remains
  `enabled=false`, `dry_run=true`, `output_backend=none` without recording its contents.
- `OPERATOR ACTION — final process choice:` Leave the bridge stopped or start it only as the
  operator explicitly requests. Any restart requires a fresh approval immediately before the
  menubar action and the exact detector must return exactly `1` afterward.
- `OPERATOR OBSERVATION:` Record final fixture darkness, physical-path state, rollback/restore
  result, and sanitized status/log watchpoints.

Only a complete, committed run record may use `PASS_LOCAL_SETUP`, and that verdict applies to this
one setup only. Otherwise the result is `FAIL` or `INCOMPLETE`, and repository status remains
`SOFTWARE/WIRE-VALIDATED ONLY / HARDWARE-UNVALIDATED`.
