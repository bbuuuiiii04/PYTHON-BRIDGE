import os
import json
import socket
import struct
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
        return False, None, None, None, {}
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        candidates = []
        
        def search(obj, path):
            if isinstance(obj, dict):
                ip = obj.get("ip") or obj.get("device_ip") or obj.get("address") or obj.get("host")
                ref = obj.get("device_ref") or obj.get("device_id") or obj.get("device") or obj.get("mac")
                sku = obj.get("sku") or obj.get("model") or obj.get("expected_sku") or obj.get("expected_model")
                if ip or ref or sku:
                    candidates.append({
                        "path": path,
                        "ip": ip,
                        "device_ref": ref,
                        "sku": sku
                    })
                for k, v in obj.items():
                    search(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    search(v, f"{path}[{i}]")

        search(config, "$")
        
        best_ip = None
        best_ref = None
        best_sku = None
        paths = {}
        
        for c in sorted(candidates, key=lambda x: (x["ip"] is not None) + (x["sku"] is not None), reverse=True):
            if not best_ip and c["ip"]: best_ip = c["ip"]; paths["ip"] = c["path"]
            if not best_ref and c["device_ref"]: best_ref = c["device_ref"]; paths["device_ref"] = c["path"]
            if not best_sku and c["sku"]: best_sku = c["sku"]; paths["sku"] = c["path"]

        return True, best_ip, best_ref, best_sku, paths
    except Exception as e:
        return True, None, None, None, {}

def run_lan_discovery():
    MULTICAST_GROUP = "239.255.255.250"
    MULTICAST_PORT = 4001
    LISTEN_PORT = 4002
    
    msg = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}})
    discovered = {}
    
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, 'SO_REUSEPORT'):
        try:
            recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
    recv_sock.bind(("", LISTEN_PORT))
    
    mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
    try:
        recv_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    except Exception:
        pass
    
    recv_sock.settimeout(2.0)
    
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    
    try:
        send_sock.sendto(msg.encode("utf-8"), (MULTICAST_GROUP, MULTICAST_PORT))
        end_time = time.time() + 2.5
        while time.time() < end_time:
            try:
                data, addr = recv_sock.recvfrom(4096)
                ip = addr[0]
                try:
                    payload = json.loads(data.decode("utf-8"))
                    msg_obj = payload.get("msg", {})
                    data_obj = msg_obj.get("data", {})
                    
                    if ip not in discovered:
                        discovered[ip] = {
                            "ip": ip,
                            "cmd": msg_obj.get("cmd"),
                            "device": data_obj.get("device"),
                            "sku": data_obj.get("sku"),
                            "bleVersionHard": data_obj.get("bleVersionHard"),
                            "bleVersionSoft": data_obj.get("bleVersionSoft"),
                            "wifiVersionHard": data_obj.get("wifiVersionHard"),
                            "wifiVersionSoft": data_obj.get("wifiVersionSoft"),
                            "raw": payload
                        }
                except json.JSONDecodeError:
                    pass
            except socket.timeout:
                continue
    except Exception as e:
        pass
    finally:
        recv_sock.close()
        send_sock.close()
        
    return list(discovered.values())

def detect_competing_processes():
    competing = []
    targets = ["Govee", "iCUE", "LedFx", "ledfx", "rb_ss_bridge_v2", "python -m rb_ss_bridge_v2"]
    my_pid = str(os.getpid())
    
    try:
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
    
    config_exists, configured_ip, configured_device_ref, configured_expected_sku, config_paths = parse_config(repo_path)
    
    discovered_devices = run_lan_discovery()
    competing_processes = detect_competing_processes()
    
    target_device_id = "C1:0A:DA:B9:81:C6:3C:02"
    expected_sku_fallback = "H612D"
    
    resolved_live_ip = None
    resolution_source = None
    resolved_device_id = None
    resolved_sku = None
    firmware_fields = {}
    discovery_ambiguous = False
    
    # 1. Match configured device_ref or known device ID
    for dev in discovered_devices:
        dev_id = dev.get("device")
        if configured_device_ref and dev_id == configured_device_ref:
            resolved_live_ip = dev.get("ip")
            resolution_source = "configured_device_ref"
            resolved_device_id = dev_id
            resolved_sku = dev.get("sku")
            break
        if dev_id == target_device_id:
            resolved_live_ip = dev.get("ip")
            resolution_source = "known_device_id"
            resolved_device_id = dev_id
            resolved_sku = dev.get("sku")
            break
            
    # 2. Match exact SKU
    if not resolved_live_ip:
        sku_matches = [d for d in discovered_devices if d.get("sku") == expected_sku_fallback]
        if len(sku_matches) == 1:
            dev = sku_matches[0]
            resolved_live_ip = dev.get("ip")
            resolution_source = "expected_sku_unambiguous"
            resolved_device_id = dev.get("device")
            resolved_sku = dev.get("sku")
        elif len(sku_matches) > 1:
            discovery_ambiguous = True
            resolution_source = "ambiguous_expected_sku"
            
    # 3. Fallback to configured IP (unsafe by default)
    if not resolved_live_ip and not discovery_ambiguous and configured_ip:
        resolved_live_ip = configured_ip
        resolution_source = "configured_ip_fallback"
        resolved_device_id = configured_device_ref
        resolved_sku = configured_expected_sku

    if resolved_live_ip:
        for d in discovered_devices:
            if d.get("ip") == resolved_live_ip:
                firmware_fields = {
                    "bleVersionHard": d.get("bleVersionHard"),
                    "bleVersionSoft": d.get("bleVersionSoft"),
                    "wifiVersionHard": d.get("wifiVersionHard"),
                    "wifiVersionSoft": d.get("wifiVersionSoft")
                }
                break

    warnings = []
    if discovery_ambiguous:
        warnings.append("Multiple devices matched expected SKU, discovery is ambiguous.")
    if len(competing_processes) > 0:
        warnings.append(f"Found {len(competing_processes)} competing processes. Close them before fuzzing.")
    if not resolved_live_ip:
        warnings.append("Could not resolve target IP.")
    if resolution_source == "configured_ip_fallback":
        warnings.append("Discovery failed. Fallback configured IP found, but live fuzzing requires explicit override.")

    safe_to_fuzz = (resolved_live_ip is not None) and (not discovery_ambiguous) and (len(competing_processes) == 0) and (resolution_source != "configured_ip_fallback")
    reason = "Safe" if safe_to_fuzz else " | ".join(warnings)

    output = {
        "repo_path": str(repo_path),
        "branch": branch,
        "git_status_summary": status_summary,
        "config_exists": config_exists,
        "configured_ip": configured_ip,
        "configured_device_ref": configured_device_ref,
        "configured_expected_sku": configured_expected_sku,
        "config_paths": config_paths,
        "discovered_devices": discovered_devices,
        "discovery_ambiguous": discovery_ambiguous,
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
