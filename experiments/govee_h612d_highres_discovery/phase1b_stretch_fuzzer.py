import time
import json
import socket
import sys
import argparse
import base64
import signal

ACTIVATE_BASE64 = "uwABsQEK"
DEACTIVATE_BASE64 = "uwABsQAL"
TARGET_PORT = 4003

def compute_checksum(packet_bytes):
    chk = 0
    for b in packet_bytes:
        chk ^= b
    return chk

def build_packet(byte_4_val, segment_count):
    packet = [0xBB, 0x00, 0x20, 0xB0, byte_4_val]
    packet.append(segment_count)
    
    # Build alternating red and green segments
    for i in range(segment_count):
        if i % 2 == 0:
            packet.extend([200, 0, 0])
        else:
            packet.extend([0, 200, 0])
        
    chk = compute_checksum(packet)
    packet.append(chk)
    return bytes(packet)

def send_udp(sock, ip, data_str):
    try:
        sock.sendto(data_str.encode('utf-8'), (ip, TARGET_PORT))
    except Exception as e:
        print(f"Error: {e}")

def wrap_json(bin_packet):
    b64 = base64.b64encode(bin_packet).decode('utf-8')
    return json.dumps({"msg": {"cmd": "razer", "data": {"pt": b64}}})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", type=str, default="192.168.0.216")
    parser.add_argument("--segments", type=int, default=60, help="Number of segments in the packet")
    args = parser.parse_args()
    
    def signal_handler(sig, frame):
        print("\nStopping via SIGTERM.")
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, signal_handler)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send_udp(sock, args.ip, json.dumps({"msg": {"cmd": "razer", "data": {"pt": ACTIVATE_BASE64}}}))
    time.sleep(0.5)
    
    import threading
    try:
        for byte_4_val in range(10):
            print(f"\n==============================================")
            print(f"Testing byte 4 = {byte_4_val} (Sending {args.segments} segments)")
            print(f"==============================================")
            bin_packet = build_packet(byte_4_val, args.segments)
            payload = wrap_json(bin_packet)
            
            stop_event = threading.Event()
            def sender():
                while not stop_event.is_set():
                    send_udp(sock, args.ip, payload)
                    time.sleep(0.1)
                    
            t = threading.Thread(target=sender)
            t.start()
            
            try:
                choice = input("How much of the strip lit up? (Press Enter for none/ignore, type notes, or 'q' to quit): ").strip()
            finally:
                stop_event.set()
                t.join()
                
            if choice.lower() in ['q', 'quit']:
                break
            
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        print("Blacking out and deactivating...")
        bin_packet = build_packet(0, args.segments)
        # overwrite with zeros
        for i in range(5, len(bin_packet)-1):
            pass # Actually just send deactivate
        send_udp(sock, args.ip, json.dumps({"msg": {"cmd": "razer", "data": {"pt": DEACTIVATE_BASE64}}}))
        time.sleep(0.1)
        sock.close()

if __name__ == "__main__":
    main()
