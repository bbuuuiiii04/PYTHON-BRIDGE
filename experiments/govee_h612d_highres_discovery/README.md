# Govee H612D High-Resolution Framebuffer Investigation

## Purpose
The purpose of this investigation is to safely determine whether the stock Govee H612D controller accepts higher-than-20 segment RGB frame payloads (Razer/DreamView protocol) and displays visibly finer addressable control, unlocking higher resolution for live DJ performance lighting.

## Hard Constraints
- **Do not** modify production bridge files.
- **Do not** modify config files.
- **Do not** edit existing probe files.
- **Do not** change existing runtime behavior.
- Use standard library only.
- Packet send success over UDP does *not* mean visual success.
- Never claim high-resolution control was found unless operator visual confirmation proves it.

## Implemented Phases
- **Phase 0**: Environment Probe & Baseline Recovery. Safely discovers local devices, parses existing config defensively, identifies competing processes, and prepares a recovery plan.
- **Phase 1A**: Segment Fuzzing. Sends varying segment counts and headers to the resolved target IP with dry-run capabilities and interactive operator prompts.

## Safety Notes
- Stop immediately if the LED strip blackouts, freezes, or behaves erratically.
- Use the recovery steps outlined in `phase0_baseline_recovery.md` if the device becomes unresponsive.
- Ensure all competing processes (iCUE, LedFx, main bridge script) are closed before running live network tests to avoid conflicting UDP streams.

## Dry-Run Instructions
You can safely validate packet generation and payload formatting without sending any network traffic by using the `--dry-run` flag:
```bash
python3 experiments/govee_h612d_highres_discovery/segment_fuzz.py --dry-run
```

## Run Order
1. Close competing processes.
2. Run `python3 experiments/govee_h612d_highres_discovery/phase0_environment_probe.py` to generate `phase0_environment.json`.
3. Verify the generated JSON has `safe_to_fuzz: true` and a valid target IP.
4. Run `python3 experiments/govee_h612d_highres_discovery/segment_fuzz.py --dry-run` to inspect payloads.
5. Manually review and run `python3 experiments/govee_h612d_highres_discovery/segment_fuzz.py` for live testing.

## Visual Operator Evidence Required
A successful UDP packet send (no exceptions) means nothing. The Govee controller may accept a 50-segment packet but silently truncate it or display corrupted data. **Visual operator evidence is strictly required** to confirm whether the strip actually displays finer resolution transitions.

## Production Impact
**No production files are modified.** All scripts and logs generated during this experiment are confined to `experiments/govee_h612d_highres_discovery/`.
