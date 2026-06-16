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
- **Phase 1A**: Segment Fuzzing. Sends varying segment counts and headers to the target IP with dry-run capabilities and interactive operator prompts.

## Safety Notes & Fallback Rules
- Stop immediately if the LED strip blackouts, freezes, or behaves erratically. The script will automatically stop after 3 consecutive "no-response" inputs or upon a blackout signal.
- **Live fuzzing is strictly gated.** It requires explicit `--live` and `--i-am-watching-the-strip` flags.
- **Ambiguous discovery blocks live fuzzing.** If multiple H612D devices are found, live fuzzing will refuse to run without explicit `--ip` overrides.
- **Configured IP fallback is not safe by default.** Discovery must explicitly match a device or SKU to be marked safe.
- Ensure all competing processes (iCUE, LedFx, main bridge script) are closed before running live network tests to avoid conflicting UDP streams.

## Dry-Run Instructions
You can safely validate packet generation and payload formatting without sending any network traffic. **Dry runs now fully write to the JSONL log**, so you can inspect exactly what would be sent:
```bash
python3 experiments/govee_h612d_highres_discovery/segment_fuzz.py --dry-run
```

## First Live Run
The first live run should use a small subset of test cases to minimize risk. By default, adding `--live` limits testing to known safe counts (15, 20, 25), safe headers, and basic patterns. You can also explicitly control the subset:
```bash
python3 experiments/govee_h612d_highres_discovery/segment_fuzz.py --live --i-am-watching-the-strip --counts 15,20,30 --patterns gradient,unique_bands
```

## Visual Operator Evidence Required
A successful UDP packet send (no exceptions) means nothing. The Govee controller may accept a 50-segment packet but silently truncate it or display corrupted data. **Visual operator evidence is strictly required** to confirm whether the strip actually displays finer resolution transitions.

## Production Impact
**No production files are modified.** All scripts and logs generated during this experiment are confined to `experiments/govee_h612d_highres_discovery/`.
