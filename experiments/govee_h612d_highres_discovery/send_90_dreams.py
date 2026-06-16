import socket
import base64
import json
import time

def build_dreams_90():
    packet = [0xBB, 0x00, 0xFA, 0xB0, 0x00]
    packet.append(90)
    for i in range(90):
        if i % 2 == 0:
            packet.extend([200, 0, 0])
        else:
            packet.extend([0, 200, 0])
    chk = 0
    for b in packet:
        chk ^= b
    packet.append(chk)
    return bytes(packet)

payload = {"msg": {"cmd": "razer", "data": {"pt": base64.b64encode(build_dreams_90()).decode('utf-8')}}}
data_str = json.dumps(payload)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# Send activate
sock.sendto(json.dumps({"msg": {"cmd": "razer", "data": {"pt": "uwABsQEK"}}}).encode('utf-8'), ('192.168.0.216', 4003))
time.sleep(0.1)

print("Continuously sending 90 segments (dreams header). Press Ctrl+C to stop.")
try:
    while True:
        sock.sendto(data_str.encode('utf-8'), ('192.168.0.216', 4003))
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    sock.sendto(json.dumps({"msg": {"cmd": "razer", "data": {"pt": "uwABsQAL"}}}).encode('utf-8'), ('192.168.0.216', 4003))
