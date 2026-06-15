import os
import json
import socket
import subprocess
import time
from pathlib import Path

def get_git_info(repo_path):
    branch = "unknown"
    status_summary = "unknown"
    try:
        branch = subprocess.check_output(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"], 
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", str(repo_path), "status", "--short"], 
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        status_summary = "clean" if not status else "dirty"
    except Exception:
        pass
    return branch, status_summary

def parse_config(repo_path):
    config_path = repo_path / "config" / "led_look_director.json"
    if not config_path.exists():
        return False, None, None, None
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Try to find target IP defensively
        configured_ip = None
        device_ref = None
        expected_sku = None
        
        # Heuristic search through config
        if isinstance(config, dict):
            # Might be at root or under a "devices" key
            target = config.get("govee_strip") or config.get("h612d") or config
            if isinstance(target, dict):
                configured_ip = target.get("ip") or target.get("device_ip") or target.get("address")
                device_ref = target.get("device_ref") or target.get("device_id") or target.get("mac")
                expected_sku = target.get("sku") or target.get("model") or target.get("expected_sku")

            # Deep search if still not found
            if not configured_ip:
                for k, v in config.items():
                    if isinstance(v, dict) and "ip" in v and "sku" in v:
                        configured_ip = v.get("ip")
                        device_ref = v.get("device_ref") or v.get("device_id")
                        expected_sku = v.get("sku")
                        break

        return True, configured_ip, device_ref, expected_sku
    except Exception as e:
        return True, None, None, None

def run_lan_discovery():
    MULTICAST_GROUP = "239.255.255.250"
    MULTICAST_PORT = 4001
    LISTEN_PORT = 4002
    
    msg = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}})
    discovered = []
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Enable broadcasting mode
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", LISTEN_PORT))
    sock.settimeout(2.0)
    
    try:
        sock.sendto(msg.encode("utf-8"), (MULTICAST_GROUP, MULTICAST_PORT))
        end_time = time.time() + 2.5
        while time.time() < end_time:
            try:
                data, addr = sock.recvfrom(4096)
                try:
                    payload = json.loads(data.decode("utf-8"))
                    discovered.append({
                        "ip": addr[0],
                        "raw": payload
                    })
                except json.JSONDecodeError:
                    pass
            except socket.timeout:
                continue
    except Exception as e:
        pass
    finally:
        sock.close()
        
    return discovered

def detect_competing_processes():
    competing = []
    targets = ["Govee", "iCUE", "LedFx", "ledfx", "rb_ss_bridge_v2", "python -m rb_ss_bridge_v2"]
    my_pid = str(os.getpid())
    
    try:
        # standard ps call
        output = subprocess.check_output(["ps", "-A", "-o", "pid,command"], text=True)
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                pid, cmd = parts
                if pid == my_pid:
                    continue
                for t in targets:
                    if t in cmd:
                        competing.append(line)
                        break
    except Exception:
        pass
    return competing

def main():
    repo_path = Path(__file__).resolve().parent.parent.parent
    branch, status_summary = get_git_info(repo_path)
    
    config_exists, configured_ip, configured_device_ref, configured_expected_sku = parse_config(repo_path)
    
    discovered_devices = run_lan_discovery()
    
    competing_processes = detect_competing_processes()
    
    # Resolve Target
    target_device_id = "C1:0A:DA:B9:81:C6:3C:02"
    expected_sku_fallback = "H612D"
    
    resolved_live_ip = None
    resolution_source = None
    resolved_device_id = None
    resolved_sku = None
    firmware_fields = {}
    
    for dev in discovered_devices:
        raw = dev.get("raw", {})
        msg = raw.get("msg", {})
        data = msg.get("data", {})
        
        dev_ip = dev.get("ip")
        dev_id = data.get("device")
        dev_sku = data.get("sku")
        
        # priority 1: configured device ref
        if configured_device_ref and dev_id == configured_device_ref:
            resolved_live_ip = dev_ip
            resolution_source = "configured_device_ref"
            resolved_device_id = dev_id
            resolved_sku = dev_sku
            firmware_fields = {k:v for k,v in data.items() if "version" in k.lower()}
            break
            
        # priority 2: known device ID
        if dev_id == target_device_id:
            resolved_live_ip = dev_ip
            resolution_source = "known_device_id"
            resolved_device_id = dev_id
            resolved_sku = dev_sku
            firmware_fields = {k:v for k,v in data.items() if "version" in k.lower() or "ble" in k.lower() or "wifi" in k.lower()}
            break
            
        # priority 3: expected sku
        if expected_sku_fallback and dev_sku == expected_sku_fallback:
            # Only if unambiguous
            if resolved_live_ip is None:
                resolved_live_ip = dev_ip
                resolution_source = "expected_sku"
                resolved_device_id = dev_id
                resolved_sku = dev_sku
                firmware_fields = {k:v for k,v in data.items() if "version" in k.lower() or "ble" in k.lower() or "wifi" in k.lower()}
            else:
                resolution_source = "ambiguous_expected_sku"
                resolved_live_ip = None
                
    if not resolved_live_ip and configured_ip:
        resolved_live_ip = configured_ip
        resolution_source = "configured_ip_fallback"
        resolved_device_id = configured_device_ref
        resolved_sku = configured_expected_sku

    warnings = []
    if resolution_source == "ambiguous_expected_sku":
        warnings.append("Multiple devices matched expected SKU, targeting ambiguous.")
    if len(competing_processes) > 0:
        warnings.append(f"Found {len(competing_processes)} competing processes. Close them before fuzzing.")
    if not resolved_live_ip:
        warnings.append("Could not resolve target IP.")

    safe_to_fuzz = (resolved_live_ip is not None) and (len(competing_processes) == 0) and ("ambiguous" not in str(resolution_source))
    reason = "Safe" if safe_to_fuzz else " | ".join(warnings)

    output = {
        "repo_path": str(repo_path),
        "branch": branch,
        "git_status_summary": status_summary,
        "config_exists": config_exists,
        "configured_ip": configured_ip,
        "configured_device_ref": configured_device_ref,
        "configured_expected_sku": configured_expected_sku,
        "discovered_devices": discovered_devices,
        "resolved_live_ip": resolved_live_ip,
        "resolution_source": resolution_source,
        "resolved_device_id": resolved_device_id,
        "resolved_sku": resolved_sku,
        "firmware_fields": firmware_fields,
        "competing_processes": competing_processes,
        "warnings": warnings,
        "safe_to_fuzz": safe_to_fuzz,
        "reason": reason
    }
    
    out_path = Path(__file__).parent / "phase0_environment.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
        
    print(f"Phase 0 complete. Results written to {out_path.name}")
    print(f"Target IP: {resolved_live_ip} (Source: {resolution_source})")
    print(f"Safe to fuzz: {safe_to_fuzz}")

if __name__ == "__main__":
    main()
