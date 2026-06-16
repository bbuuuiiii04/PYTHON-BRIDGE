import sys
import os
import time
import socket
import base64

sys.path.insert(0, os.path.abspath('.'))

from rb_ss_bridge_v2.govee_realtime_transport import GoveeRealtimeTransport

IP = "192.168.0.216"
PORT = 4003
SEGMENTS = 60
HEADER_BYTES = (187, 0, 250, 176, 0) # dreams header

def main():
    transport = GoveeRealtimeTransport(
        ip=IP,
        port=PORT,
        segments=SEGMENTS,
        header_bytes=HEADER_BYTES
    )
    
    print("Activating transport...")
    transport.activate()
    transport.set_brightness(100)
    time.sleep(0.5)

    try:
        print("1. Sending alternating Red/Green (Static Sentinel)...")
        # 60 segments: Even = Red, Odd = Green
        frame_rg = [(255, 0, 0) if i % 2 == 0 else (0, 255, 0) for i in range(SEGMENTS)]
        for _ in range(60): # 2 seconds at 30fps
            transport.send_frame(frame_rg)
            time.sleep(1/30.0)

        print("2. Sending 1-segment moving marker (White on Blue)...")
        # A single white pixel running across a blue background
        for i in range(SEGMENTS * 2): # Run across twice
            pos = i % SEGMENTS
            frame_chase = [(0, 0, 255)] * SEGMENTS
            frame_chase[pos] = (255, 255, 255)
            transport.send_frame(frame_chase)
            time.sleep(1/15.0) # Slower so we can see the individual physical LEDs
            
        print("Done. Blacking out.")
        transport.blackout()
        
    except KeyboardInterrupt:
        transport.blackout()
        
    finally:
        transport.deactivate()
        transport.close()

if __name__ == "__main__":
    main()
