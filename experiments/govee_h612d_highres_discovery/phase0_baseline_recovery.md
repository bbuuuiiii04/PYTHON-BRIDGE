# Phase 0: Baseline Recovery

## How to quit competing apps
Before running experiments, ensure no other applications are holding the Govee UDP port or sending conflicting commands:
1. Quit the Govee mobile app.
2. Quit iCUE from the macOS menu bar.
3. Quit LedFx if running.
4. Stop the local `rb_ss_bridge_v2` process (`Ctrl+C` in its terminal window).
5. Verify using `python3 experiments/govee_h612d_highres_discovery/phase0_environment_probe.py`

## How to run phase0_environment_probe.py
```bash
python3 experiments/govee_h612d_highres_discovery/phase0_environment_probe.py
```

## How to inspect phase0_environment.json
```bash
cat experiments/govee_h612d_highres_discovery/phase0_environment.json
```
Look for `"safe_to_fuzz": true` and a valid `"resolved_live_ip"`.
**Note:** If discovery was ambiguous or only found a fallback IP from your configuration, `safe_to_fuzz` will be false and live mode will require manual IP overrides.

## How to run dry-run fuzz validation
Run the segment fuzzer in dry-run mode to verify payload construction and write JSONL logs without network sends:
```bash
python3 experiments/govee_h612d_highres_discovery/segment_fuzz.py --dry-run
```

## How to run baseline 15 and 20 segment tests
The bridge historically defaulted to 20 segments, and iCUE exposed 15 zones. For your first live run, the script defaults to a reduced safe subset automatically. You must pass explicit safety flags:
```bash
python3 experiments/govee_h612d_highres_discovery/segment_fuzz.py --live --i-am-watching-the-strip
```

## How to recover
If the strip freezes, goes black permanently, or exhibits corrupted behavior:
1. **Blackout frame**: The fuzzer script automatically attempts to send a blackout frame and deactivate command if you select `[6] Blackout/freeze` or hit `Ctrl+C`.
2. **Deactivate realtime mode**: The script sends `uwABsQAL` to return control to the onboard controller.
3. **Verify Govee app control**: Open the Govee mobile app and attempt to change the color/scene. If it responds, the network stack is still alive.
4. **Power-cycle fallback**: If the device drops off the network entirely or fails to respond to the app, unplug the physical power adapter from the wall, wait 10 seconds, and plug it back in.

## Network Troubleshooting (macOS)
### Interface Discovery
Find the network interface routing to the target IP:
```bash
route get <resolved_device_ip> | grep interface
```

### Idle Traffic Capture
To capture baseline idle traffic on UDP port 4003:
```bash
sudo tcpdump -i <interface> -w govee_idle_capture.pcap "host <resolved_device_ip> and udp port 4003"
```
*(Note: `lsof -i UDP:4003` is weak evidence because apps often send outbound UDP packets from ephemeral high ports rather than binding locally to 4003.)*
