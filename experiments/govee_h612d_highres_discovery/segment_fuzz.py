import os
import sys
import json
import socket
import base64
import time
import argparse
from datetime import datetime
from pathlib import Path
import packet_patterns

KNOWN_HEADERS = {
    "dreams": [0xBB, 0x00, 0xFA, 0xB0, 0x00],
    "chroma": [0xBB, 0x00, 0x0E, 0xB0, 0x00],
    "govee":  [0xBB, 0x00, 0x20, 0xB0, 0x00]
}

ACTIVATE_BASE64 = "uwABsQEK"
DEACTIVATE_BASE64 = "uwABsQAL"

def compute_checksum(packet_bytes):
    chk = 0
    for b in packet_bytes:
        chk ^= b
    return chk

def build_packet(header_bytes, segment_count, pattern, brightness=50):
    packet = list(header_bytes)
    packet.append(segment_count)
    for r, g, b in pattern:
        scale = brightness / 100.0
        packet.append(packet_patterns.clamp(r * scale))
        packet.append(packet_patterns.clamp(g * scale))
        packet.append(packet_patterns.clamp(b * scale))
        
    chk = compute_checksum(packet)
    packet.append(chk)
    return bytes(packet)

def wrap_json_razer(binary_packet):
    b64_data = base64.b64encode(binary_packet).decode('utf-8')
    return json.dumps({"msg": {"cmd": "razer", "data": {"pt": b64_data}}})

def send_udp(ip, port, data_str, dry_run):
    if dry_run:
        print(f"[DRY-RUN] Would send to {ip}:{port}: {data_str}")
        return True
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        sock.sendto(data_str.encode('utf-8'), (ip, port))
        sock.close()
        return True
    except Exception as e:
        print(f"UDP Send Error: {e}")
        return False

def recover_realtime_mode(ip, header, count, dry_run=False):
    print("Attempting blackout and deactivate recovery...")
    blackout = [(0, 0, 0)] * count
    try:
        bp = build_packet(header, count, blackout, 0)
        send_udp(ip, 4003, wrap_json_razer(bp), dry_run)
        time.sleep(0.1)
    except Exception as e:
        print(f"Failed to build/send blackout: {e}")
    send_udp(ip, 4003, json.dumps({"msg": {"cmd": "razer", "data": {"pt": DEACTIVATE_BASE64}}}), dry_run)
    print("Recovery steps sent.")
    return True

def prompt_operator(prompt_text):
    print("\n" + "="*50)
    print(prompt_text)
    print("="*50)
    print("[1] No response")
    print("[2] Same chunky zones as 15/20")
    print("[3] Visibly smoother than 20")
    print("[4] Corrupted/wrapped/mirrored")
    print("[5] Partial strip only")
    print("[6] Blackout/freeze")
    print("[7] Other")
    
    while True:
        choice = input("Select an option (1-7) or type 'quit' to exit: ").strip()
        if choice.lower() in ['q', 'quit', 'exit']:
            return "quit", "", ""
        if choice in [str(i) for i in range(1, 8)]:
            visible = input("Estimated visible transitions/blocks (optional): ").strip()
            notes = input("Freeform notes (optional): ").strip()
            return choice, visible, notes
        print("Invalid choice.")

def load_environment():
    env_path = Path(__file__).parent / "phase0_environment.json"
    if not env_path.exists():
        return None
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def validate_and_build(header, count, pattern, brightness):
    assert len(pattern) == count, f"Pattern length {len(pattern)} != count {count}"
    for r, g, b in pattern:
        assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255, f"Invalid RGB: {(r, g, b)}"
    
    bin_packet = build_packet(header, count, pattern, brightness)
    expected_len = 5 + 1 + count * 3 + 1
    assert len(bin_packet) == expected_len, f"Binary packet length {len(bin_packet)} != expected {expected_len}"
    return bin_packet

def main():
    parser = argparse.ArgumentParser(description="Phase 1A: Govee H612D High-Res Fuzzer")
    parser.add_argument("--ip", type=str, help="Override target IP")
    parser.add_argument("--force-ip", action="store_true", help="Allow manual override if Phase 0 was ambiguous")
    parser.add_argument("--dry-run", action="store_true", help="Explicit alias for dry-run (no-send mode)")
    parser.add_argument("--live", action="store_true", help="Enable actual UDP sending")
    parser.add_argument("--i-am-watching-the-strip", action="store_true", help="Required for live fuzzing to confirm visual presence")
    
    # Run controls
    parser.add_argument("--counts", type=str, help="Comma-separated segment counts (e.g. 15,20,30)")
    parser.add_argument("--patterns", type=str, help="Comma-separated pattern names")
    parser.add_argument("--headers", type=str, help="Comma-separated header names")
    parser.add_argument("--stretches", type=str, help="Comma-separated stretch bytes (0,1)")
    parser.add_argument("--max-tests", type=int, help="Maximum number of tests to run")
    
    args = parser.parse_args()

    if args.dry_run and args.live:
        print("ERROR: Conflicting flags. Cannot use --dry-run and --live together.")
        sys.exit(1)

    is_live = args.live
    
    if is_live and not args.i_am_watching_the_strip:
        print("ERROR: Live fuzzing requires --i-am-watching-the-strip to ensure operator is visually confirming changes.")
        sys.exit(1)
        
    env = load_environment()
    
    if not env and not (args.ip and args.force_ip):
        print("ERROR: phase0_environment.json is missing. Please run phase0_environment_probe.py first, or use --ip and --force-ip.")
        sys.exit(1)

    target_ip = args.ip
    resolution_source = "manual_override"
    configured_ip = None
    safe_to_fuzz = False
    
    if env:
        configured_ip = env.get("configured_ip")
        if not target_ip:
            target_ip = env.get("resolved_live_ip")
            resolution_source = env.get("resolution_source", "unknown")
            
        safe_to_fuzz = env.get("safe_to_fuzz", False)

    if not target_ip:
        print("ERROR: No resolved IP exists.")
        sys.exit(1)

    if not safe_to_fuzz and not (args.ip and args.force_ip):
        if is_live:
            print("ERROR: Environment is not safe to fuzz (ambiguous discovery, configured fallback IP, or competing processes).")
            print("Use --force-ip and --ip if you are absolutely sure.")
            sys.exit(1)
        else:
            print("WARNING: Environment not safe, but allowing dry-run.")

    print(f"Targeting IP: {target_ip} (Source: {resolution_source})")
    
    if is_live:
        print("MODE: LIVE SENDING")
        print("WARNING: You have enabled live UDP sending. Please keep eyes on the strip.")
    else:
        print("MODE: DRY-RUN (No UDP packets will be sent)")

    log_path = Path(__file__).parent / "fuzz_results.jsonl"
    
    # Define matrix based on arguments or safe defaults
    segment_counts = [int(x) for x in args.counts.split(",")] if args.counts else ([15, 20, 25] if is_live else [1, 5, 10, 15, 20, 25, 30, 40, 50])
    headers_to_test = args.headers.split(",") if args.headers else (["govee", "chroma"] if is_live else list(KNOWN_HEADERS.keys()))
    stretch_variants = [int(x) for x in args.stretches.split(",")] if args.stretches else ([0] if is_live else [0, 1])
    
    all_patterns = {
        "traveling_marker": lambda c: packet_patterns.traveling_marker(c, c//2),
        "gradient": packet_patterns.gradient,
        "alternating_rg": packet_patterns.alternating_rg,
        "sparse_marker": packet_patterns.sparse_marker,
        "binary_split": packet_patterns.binary_split,
        "sentinel": packet_patterns.sentinel,
        "unique_bands": packet_patterns.unique_bands
    }
    
    pattern_names = args.patterns.split(",") if args.patterns else (["alternating_rg", "gradient"] if is_live else list(all_patterns.keys()))
    
    patterns = [(name, all_patterns[name]) for name in pattern_names if name in all_patterns]
    
    brightness = 50
    test_count = 0
    consecutive_no_response = 0
    last_header = list(KNOWN_HEADERS["govee"]) # safe fallback for recovery

    try:
        if is_live:
            print("Activating realtime mode...")
            send_udp(target_ip, 4003, json.dumps({"msg": {"cmd": "razer", "data": {"pt": ACTIVATE_BASE64}}}), False)
            time.sleep(0.5)

        for count in segment_counts:
            for header_name in headers_to_test:
                for stretch in stretch_variants:
                    for pat_name, pat_func in patterns:
                        if args.max_tests and test_count >= args.max_tests:
                            print(f"Max tests ({args.max_tests}) reached. Stopping.")
                            raise KeyboardInterrupt
                            
                        test_count += 1
                        pattern = pat_func(count)
                        header = list(KNOWN_HEADERS[header_name])
                        header[4] = stretch
                        last_header = header
                        
                        try:
                            bin_packet = validate_and_build(header, count, pattern, brightness)
                        except AssertionError as e:
                            print(f"Validation failed: {e}")
                            continue
                            
                        payload_str = wrap_json_razer(bin_packet)
                        chk = bin_packet[-1]
                        
                        print(f"\n--- Testing: {count} segs | {header_name} | stretch:{stretch} | {pat_name} ---")
                        print(f"Checksum: {chk} (0x{chk:02X})")
                        
                        send_ok = send_udp(target_ip, 4003, payload_str, not is_live)
                        
                        if not is_live:
                            result = {
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                                "device_ip": target_ip,
                                "configured_ip": configured_ip,
                                "resolved_ip": target_ip,
                                "resolution_source": resolution_source,
                                "header_name": header_name,
                                "header_bytes": header,
                                "segment_count": count,
                                "stretch": stretch,
                                "pattern_name": pat_name,
                                "brightness": brightness,
                                "payload_length_bytes": len(payload_str),
                                "binary_length_bytes": len(bin_packet),
                                "checksum": chk,
                                "send_ok": send_ok,
                                "dry_run": True,
                                "operator_response": "dry_run",
                                "visible_transitions": None,
                                "operator_notes": "dry-run only; no packet sent",
                                "recovery_ok": True
                            }
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(result) + "\n")
                        else:
                            choice, vis, notes = prompt_operator(f"Check strip. Sent: {count} segments, pattern {pat_name}")
                            
                            if choice == "quit":
                                raise KeyboardInterrupt
                                
                            if choice == "1":
                                consecutive_no_response += 1
                            else:
                                consecutive_no_response = 0
                                
                            recovery_ok = True
                            is_fatal = False
                            
                            if choice == "6" or consecutive_no_response >= 3:
                                is_fatal = True
                            
                            result = {
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                                "device_ip": target_ip,
                                "configured_ip": configured_ip,
                                "resolved_ip": target_ip,
                                "resolution_source": resolution_source,
                                "header_name": header_name,
                                "header_bytes": header,
                                "segment_count": count,
                                "stretch": stretch,
                                "pattern_name": pat_name,
                                "brightness": brightness,
                                "payload_length_bytes": len(payload_str),
                                "binary_length_bytes": len(bin_packet),
                                "checksum": chk,
                                "send_ok": send_ok,
                                "dry_run": False,
                                "operator_response": choice,
                                "visible_transitions": vis,
                                "operator_notes": notes,
                                "recovery_ok": None # will set below if fatal
                            }
                            
                            if is_fatal:
                                print(f"Fatal condition met (Freeze or 3x no-response). Logging result and attempting recovery...")
                                recovery_ok = recover_realtime_mode(target_ip, header, count, False)
                                result["recovery_ok"] = recovery_ok
                                with open(log_path, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(result) + "\n")
                                sys.exit(1)
                                
                            result["recovery_ok"] = True
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(result) + "\n")
                                
                        time.sleep(0.1)
                        
    except KeyboardInterrupt:
        print("\nExiting early.")
    finally:
        if is_live:
            print("Run finished or interrupted. Cleaning up...")
            recover_realtime_mode(target_ip, last_header, segment_counts[0] if segment_counts else 20, False)

if __name__ == "__main__":
    main()
