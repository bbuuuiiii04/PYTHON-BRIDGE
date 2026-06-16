import time
import json
import socket
import sys
import argparse
import base64

ACTIVATE_BASE64 = "uwABsQEK"
DEACTIVATE_BASE64 = "uwABsQAL"
TARGET_PORT = 4003

def compute_checksum(packet_bytes):
    chk = 0
    for b in packet_bytes:
        chk ^= b
    return chk

def build_chunk_packet(chunk_idx, segment_count, color):
    # Byte 1 is the chunk offset multiplier?
    packet = [0xBB, chunk_idx, 0x20, 0xB0, 0x00]
    packet.append(segment_count)
    for _ in range(segment_count):
        packet.append(color[0])
        packet.append(color[1])
        packet.append(color[2])
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

import signal

def main():
    parser = argparse.ArgumentParser(description="Phase 1B: Chunking Protocol Fuzzer")
    parser.add_argument("--ip", type=str, default="192.168.0.216")
    parser.add_argument("--segments", type=int, default=20, help="Number of segments per packet")
    parser.add_argument("--chunks", type=int, default=4, help="Number of chunk offsets to cycle")
    args = parser.parse_args()
    
    def signal_handler(sig, frame):
        print("\nStopping via SIGTERM.")
        raise KeyboardInterrupt
        
    signal.signal(signal.SIGTERM, signal_handler)
    
    print(f"Starting Phase 1B Chunk Fuzzer to {args.ip}")
    print(f"Testing {args.chunks} chunks, {args.segments} segments per chunk.")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    print("Activating realtime mode...")
    send_udp(sock, args.ip, json.dumps({"msg": {"cmd": "razer", "data": {"pt": ACTIVATE_BASE64}}}))
    time.sleep(0.5)
    
    # 6 distinct colors to paint the chunks
    colors = [
        (200, 0, 0),     # 0: Red
        (0, 200, 0),     # 1: Green
        (0, 0, 200),     # 2: Blue
        (200, 200, 0),   # 3: Yellow
        (200, 0, 200),   # 4: Magenta
        (0, 200, 200),   # 5: Cyan
    ]
    
    try:
        print("\nSending multi-packet stream... Watch the strip!")
        print("Press Ctrl+C to stop.")
        while True:
            # Send each chunk packet in rapid succession
            for i in range(args.chunks):
                color = colors[i % len(colors)]
                bin_packet = build_chunk_packet(i, args.segments, color)
                send_udp(sock, args.ip, wrap_json(bin_packet))
                time.sleep(0.01) # 10ms between packets
            
            time.sleep(0.05) # 50ms before rewriting the strip
            
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        print("Blacking out and deactivating...")
        for i in range(args.chunks):
            bin_packet = build_chunk_packet(i, args.segments, (0, 0, 0))
            send_udp(sock, args.ip, wrap_json(bin_packet))
            time.sleep(0.01)
        send_udp(sock, args.ip, json.dumps({"msg": {"cmd": "razer", "data": {"pt": DEACTIVATE_BASE64}}}))
        time.sleep(0.1)
        sock.close()

if __name__ == "__main__":
    main()
