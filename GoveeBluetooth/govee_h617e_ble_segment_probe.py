#!/usr/bin/env python3
"""
Govee H617E BLE Segment Probe
Operator-driven probe for RGBIC BLE segment control investigation.
NO production bridge integration. NO automatic writes.

Usage:
  python3 govee_h617e_ble_segment_probe.py <command> [address]

Commands (safe/non-write):
  scan                        - list nearby BLE devices
  services <addr>             - connect, print services/characteristics, disconnect (no writes)

Commands (write, require explicit operator approval):
  keepalive <addr>            - send keepalive packet every 2s for 30s
  power-on <addr>             - send power-on packet
  power-off <addr>            - send power-off packet
  brightness <addr> <0-255>   - send brightness command
  all-red <addr>              - send all segments red
  all-green <addr>            - send all segments green
  all-blue <addr>             - send all segments blue
  all-black <addr>            - send all segments off (black)
  left-mask-sweep <addr>      - walk LEFT_MASK through single bits, log which segment lights
  right-mask-sweep <addr>     - walk RIGHT_MASK through single bits, log which segment lights
  alternating-test <addr>     - send odd/even segment groups in different colors
  frame-compiler-dry-run      - no BLE; compile RGB list to mask-color packets (print only)
"""

import sys
import asyncio
import time

# ── Known UUIDs ──────────────────────────────────────────────────────────────
GOVEE_SERVICE_UUID = "00010203-0405-0607-0809-0a0b0c0d1910"
GOVEE_WRITE_CHAR   = "00010203-0405-0607-0809-0a0b0c0d2b11"

# H617E: 8 left segments (bits 0-7 in LEFT_MASK) + 7 right segments (bits 0-6 in RIGHT_MASK)
# ponytail: configurable but default is 15; sweep empirically confirms actual count
LEFT_SEGMENT_COUNT  = 8
RIGHT_SEGMENT_COUNT = 7
TOTAL_SEGMENTS      = LEFT_SEGMENT_COUNT + RIGHT_SEGMENT_COUNT  # 15

SCAN_TIMEOUT = 12.0  # seconds


# ── Packet encoder ────────────────────────────────────────────────────────────

def xor_checksum(first_19: bytes) -> int:
    """XOR of first 19 bytes → last byte."""
    assert len(first_19) == 19, f"expected 19 bytes, got {len(first_19)}"
    result = 0
    for b in first_19:
        result ^= b
    return result


def _finalize(payload19: bytes) -> bytes:
    """Append XOR checksum byte and assert 20-byte total."""
    assert len(payload19) == 19
    packet = payload19 + bytes([xor_checksum(payload19)])
    assert len(packet) == 20, f"packet must be 20 bytes, got {len(packet)}"
    assert packet[-1] == xor_checksum(packet[:19])
    return packet


def build_keepalive_packet() -> bytes:
    """AA 01 00...00 XOR  (standard Govee keepalive)"""
    payload = bytes([0xAA, 0x01]) + bytes(17)
    return _finalize(payload)


def build_power_packet(on: bool) -> bytes:
    """33 01 01/00 00...00 XOR"""
    payload = bytes([0x33, 0x01, 0x01 if on else 0x00]) + bytes(16)
    return _finalize(payload)


def build_brightness_packet(brightness: int) -> bytes:
    """33 04 <brightness 0-255> 00...00 XOR"""
    assert 0 <= brightness <= 255
    payload = bytes([0x33, 0x04, brightness]) + bytes(16)
    return _finalize(payload)


def build_solid_color_packet(r: int, g: int, b: int) -> bytes:
    """33 05 02 B G R 00...00 XOR — H617E GBK firmware uses BGR wire order."""
    assert all(0 <= v <= 255 for v in (r, g, b))
    # ponytail: BGR confirmed empirically — send R=255 → blue, send B=255 → red
    payload = bytes([0x33, 0x05, 0x02, b, g, r]) + bytes(13)
    return _finalize(payload)


def build_h617e_segment_color_packet(
    r: int, g: int, b: int,
    left_mask: int, right_mask: int
) -> bytes:
    """
    33 05 15 01 R G B 00 00 00 00 00 LEFT_MASK RIGHT_MASK 00 00 00 00 00 XOR
    Byte layout (0-indexed):
      0:    0x33  (command header)
      1:    0x05  (segment color sub-cmd)
      2:    0x15  (mode: manual RGB)
      3:    0x01  (segment group 1)
      4-6:  R G B
      7-11: 0x00 padding
      12:   LEFT_MASK  (bits 0-7 → left segments 1-8)
      13:   RIGHT_MASK (bits 0-6 → right segments 1-7, bit7 unused)
      14-18:0x00 padding
      19:   XOR checksum
    """
    assert all(0 <= v <= 255 for v in (r, g, b, left_mask, right_mask))
    # ponytail: mode=15 uses plain RGB; mode=02 uses BGR (different sub-command, empirically confirmed)
    payload = bytes([
        0x33, 0x05, 0x15, 0x01,
        r, g, b,
        0x00, 0x00, 0x00, 0x00, 0x00,
        left_mask, right_mask,
        0x00, 0x00, 0x00, 0x00, 0x00,
    ])
    return _finalize(payload)


def masks_for_segments(
    indices: list[int],
    physical_segment_count: int = TOTAL_SEGMENTS,
    left_count: int = LEFT_SEGMENT_COUNT,
) -> tuple[int, int]:
    """
    Given a list of 0-based physical segment indices, return (left_mask, right_mask).
    Segments 0..(left_count-1) → LEFT_MASK bits 0..(left_count-1)
    Segments left_count..(left_count+right_count-1) → RIGHT_MASK bits
    """
    left_mask = 0
    right_mask = 0
    for idx in indices:
        assert 0 <= idx < physical_segment_count, f"segment index {idx} out of range"
        if idx < left_count:
            left_mask |= (1 << idx)
        else:
            right_mask |= (1 << (idx - left_count))
    return left_mask, right_mask


def _hex(packet: bytes) -> str:
    return " ".join(f"{b:02X}" for b in packet)


def _log_packet(label: str, packet: bytes):
    print(f"  [{label}] {_hex(packet)}  ({len(packet)} bytes)")


# ── Self-test ─────────────────────────────────────────────────────────────────

def _run_self_tests():
    # keepalive: AA 01 00*17 XOR
    ka = build_keepalive_packet()
    assert len(ka) == 20
    assert ka[0] == 0xAA and ka[1] == 0x01
    assert ka[-1] == xor_checksum(ka[:19])
    assert ka[-1] == 0xAB  # AA^01 = AB

    # power on
    pon = build_power_packet(True)
    assert len(pon) == 20
    assert pon[0] == 0x33 and pon[1] == 0x01 and pon[2] == 0x01
    assert pon[-1] == xor_checksum(pon[:19])

    # power off
    poff = build_power_packet(False)
    assert poff[2] == 0x00
    assert poff[-1] == xor_checksum(poff[:19])

    # brightness
    bpkt = build_brightness_packet(128)
    assert len(bpkt) == 20
    assert bpkt[2] == 128
    assert bpkt[-1] == xor_checksum(bpkt[:19])

    # all-red: mode=15 uses plain RGB; byte[4]=R=255, byte[5]=G=0, byte[6]=B=0
    red = build_h617e_segment_color_packet(255, 0, 0, 0xFF, 0x7F)
    assert len(red) == 20
    assert red[4] == 255 and red[5] == 0 and red[6] == 0  # RGB
    assert red[12] == 0xFF and red[13] == 0x7F
    assert red[-1] == xor_checksum(red[:19])

    # masks_for_segments
    lm, rm = masks_for_segments([0, 1, 8, 9])
    assert lm == 0b00000011  # segments 0,1
    assert rm == 0b00000011  # segments 8,9 → right bits 0,1

    # all segments
    lm_all, rm_all = masks_for_segments(list(range(15)))
    assert lm_all == 0xFF
    assert rm_all == 0x7F  # 7 right segments

    print("Self-tests: ALL PASS")


# ── BLE helpers ───────────────────────────────────────────────────────────────

async def _find_write_char(client):
    """Return (characteristic, write_without_response: bool) or raise."""
    from bleak import BleakClient
    for svc in client.services:
        for char in svc.characteristics:
            if char.uuid.lower() == GOVEE_WRITE_CHAR.lower():
                props = char.properties
                wwr = "write-without-response" in props
                wr  = "write" in props
                print(f"  Found write char: {char.uuid}")
                print(f"  Properties: {props}")
                if not (wwr or wr):
                    raise RuntimeError(f"Characteristic has no write property: {props}")
                return char, wwr
    raise RuntimeError(f"Write characteristic {GOVEE_WRITE_CHAR} not found — check services output")


async def _send(client, char, packet: bytes, label: str, wwr: bool):
    _log_packet(label, packet)
    if wwr:
        await client.write_gatt_char(char, packet, response=False)
    else:
        await client.write_gatt_char(char, packet, response=True)


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_scan(verbose: bool = False):
    from bleak import BleakScanner
    print(f"Scanning for {SCAN_TIMEOUT}s ...")
    devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT, return_adv=True)
    govee_hits = []
    govee_mfr_hits = []
    print(f"\nFound {len(devices)} device(s):")
    for addr, (dev, adv) in devices.items():
        name = dev.name or "(no name)"
        rssi = adv.rssi if adv.rssi is not None else "?"
        flag = ""
        mfr_data = adv.manufacturer_data or {}
        # Govee uses manufacturer ID 0xEC06 (little-endian key = 0x06EC = 1772)
        govee_mfr = 0xEC06 in mfr_data or 0x06EC in mfr_data
        if govee_mfr:
            govee_mfr_hits.append((addr, name, rssi, mfr_data))
            flag = "  ← GOVEE (mfr data)"
        elif name and ("govee" in name.lower() or "h617" in name.lower() or "h61" in name.lower()):
            flag = "  ← LIKELY TARGET (name)"
            govee_hits.append((addr, name, rssi))
        print(f"  {addr}  {name!r:30s}  RSSI={rssi}{flag}")
        if verbose and mfr_data:
            for mfr_id, mfr_bytes in mfr_data.items():
                print(f"    MFR 0x{mfr_id:04X}: {mfr_bytes.hex()}")
        if verbose and adv.service_uuids:
            for uuid in adv.service_uuids:
                print(f"    SVC: {uuid}")
    print()
    if govee_mfr_hits:
        print("Govee devices (confirmed by manufacturer data):")
        for addr, name, rssi, mfr in govee_mfr_hits:
            print(f"  {addr}  {name}  RSSI={rssi}")
            for mid, mbytes in mfr.items():
                print(f"    MFR 0x{mid:04X}: {mbytes.hex()}")
    elif govee_hits:
        print("Govee candidates (by name):")
        for addr, name, rssi in govee_hits:
            print(f"  {addr}  {name}  RSSI={rssi}")
    else:
        print("No Govee devices found by name or manufacturer data.")
    print(f"\nUse address above with 'services', 'keepalive', etc.")
    print(f"Tip: run 'scan-verbose' to see all manufacturer data for unlabeled devices.")


async def _get_device(addr: str):
    """
    On macOS, BleakClient needs a BLEDevice object from the current scan cache.
    We do a full discover scan and pull the matching device object by address.
    """
    from bleak import BleakScanner
    print(f"  Scanning to locate {addr} ...")
    devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT, return_adv=True)
    target = None
    for a, (dev, adv) in devices.items():
        if a.upper() == addr.upper():
            target = dev
            break
    if target is None:
        found_names = [f"{a} ({d.name or 'no name'})" for a, (d, _) in devices.items()]
        raise RuntimeError(
            f"Device {addr} not found in scan ({len(devices)} devices seen).\n"
            f"Seen: {found_names}"
        )
    print(f"  Found: {target.name!r}  addr={target.address}")
    return target


async def cmd_services(addr: str):
    from bleak import BleakClient
    device = await _get_device(addr)
    print(f"Connecting to {addr} (no writes) ...")
    async with BleakClient(device, timeout=20.0) as client:
        print(f"Connected: {client.is_connected}")
        print(f"\nServices and characteristics:")
        for svc in client.services:
            print(f"\n  SERVICE: {svc.uuid}  ({svc.description})")
            for char in svc.characteristics:
                desc = char.description or ""
                print(f"    CHAR: {char.uuid}  props={char.properties}  ({desc})")
                for d in char.descriptors:
                    print(f"      DESC: {d.uuid}")
    print("\nDisconnected cleanly.")


async def cmd_keepalive(addr: str, duration: int = 30):
    from bleak import BleakClient
    device = await _get_device(addr)
    print(f"Connecting to {addr} for keepalive test ({duration}s) ...")
    ka = build_keepalive_packet()
    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        print(f"Sending keepalive every 2s for {duration}s ...")
        end = time.time() + duration
        count = 0
        while time.time() < end:
            try:
                await _send(client, char, ka, f"keepalive#{count}", wwr)
                count += 1
            except Exception as e:
                print(f"  KEEPALIVE ERROR at #{count}: {e}")
            await asyncio.sleep(2.0)
        print(f"Keepalive done. Sent {count} packets.")


async def cmd_power(addr: str, on: bool):
    from bleak import BleakClient
    device = await _get_device(addr)
    label = "power-on" if on else "power-off"
    print(f"Connecting to {addr} for {label} ...")
    pkt = build_power_packet(on)
    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        await _send(client, char, pkt, label, wwr)
        print(f"{label} sent. Observe strip.")


async def cmd_brightness(addr: str, level: int):
    from bleak import BleakClient
    device = await _get_device(addr)
    print(f"Connecting to {addr} for brightness={level} ...")
    pkt = build_brightness_packet(level)
    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        await _send(client, char, pkt, f"brightness={level}", wwr)
        print(f"Brightness={level} sent. Observe strip.")


async def cmd_all_color(addr: str, r: int, g: int, b: int, label: str):
    from bleak import BleakClient
    device = await _get_device(addr)
    print(f"Connecting to {addr} for {label} (all segments, LEFT=0xFF RIGHT=0x7F) ...")
    pkt = build_h617e_segment_color_packet(r, g, b, 0xFF, 0x7F)
    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        await _send(client, char, pkt, label, wwr)
        print(f"{label} sent. Observe strip.")


async def cmd_left_mask_sweep(addr: str):
    """Walk LEFT_MASK through single bits; RIGHT_MASK=0 so only left side lights."""
    from bleak import BleakClient
    device = await _get_device(addr)
    bits = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80]
    print(f"Connecting to {addr} for left-mask-sweep ...")
    print("Each step: strip lit red, one bit at a time. Note which segment lights.")
    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        # First: black out all
        await _send(client, char, build_h617e_segment_color_packet(0, 0, 0, 0xFF, 0x7F), "all-black", wwr)
        await asyncio.sleep(0.5)
        for i, bit in enumerate(bits):
            pkt = build_h617e_segment_color_packet(255, 0, 0, bit, 0x00)
            await _send(client, char, pkt, f"left-bit{i}=0x{bit:02X}", wwr)
            print(f"  LEFT_MASK=0x{bit:02X} sent. Which physical segment lit? (wait 1.5s)")
            await asyncio.sleep(1.5)
        # Black out after sweep — small delay ensures write-without-response lands before disconnect
        await _send(client, char, build_h617e_segment_color_packet(0, 0, 0, 0xFF, 0x7F), "all-black", wwr)
        await asyncio.sleep(0.3)
    print("\nLeft mask sweep done. Note which segments corresponded to each bit.")


async def cmd_right_mask_sweep(addr: str):
    """Walk RIGHT_MASK through single bits; LEFT_MASK=0."""
    from bleak import BleakClient
    device = await _get_device(addr)
    bits = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40]
    print(f"Connecting to {addr} for right-mask-sweep ...")
    print("Each step: strip lit blue, one bit at a time. Note which segment lights.")
    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        await _send(client, char, build_h617e_segment_color_packet(0, 0, 0, 0xFF, 0x7F), "all-black", wwr)
        await asyncio.sleep(0.5)
        for i, bit in enumerate(bits):
            pkt = build_h617e_segment_color_packet(0, 0, 255, 0x00, bit)
            await _send(client, char, pkt, f"right-bit{i}=0x{bit:02X}", wwr)
            print(f"  RIGHT_MASK=0x{bit:02X} sent. Which physical segment lit? (wait 1.5s)")
            await asyncio.sleep(1.5)
        await _send(client, char, build_h617e_segment_color_packet(0, 0, 0, 0xFF, 0x7F), "all-black", wwr)
        await asyncio.sleep(0.3)
    print("\nRight mask sweep done.")


async def cmd_alternating_test(addr: str):
    """
    Attempt to set alternating physical segments to different colors.
    Group A (even segments: 0,2,4,6,8,10,12,14) → red
    Group B (odd  segments: 1,3,5,7,9,11,13)    → blue
    Sends two sequential packets; if H617E honors independent groups, two colors show.
    """
    from bleak import BleakClient
    device = await _get_device(addr)
    even = list(range(0, TOTAL_SEGMENTS, 2))
    odd  = list(range(1, TOTAL_SEGMENTS, 2))
    lm_even, rm_even = masks_for_segments(even)
    lm_odd,  rm_odd  = masks_for_segments(odd)
    pkt_a = build_h617e_segment_color_packet(255, 0, 0, lm_even, rm_even)
    pkt_b = build_h617e_segment_color_packet(0, 0, 255, lm_odd,  rm_odd)
    print(f"Alternating test:")
    print(f"  Group A (even segs {even}): LEFT=0x{lm_even:02X} RIGHT=0x{rm_even:02X} → RED")
    print(f"  Group B (odd  segs {odd}):  LEFT=0x{lm_odd:02X}  RIGHT=0x{rm_odd:02X}  → BLUE")
    print(f"Connecting to {addr} ...")
    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        await _send(client, char, pkt_a, "even-segs-red", wwr)
        await asyncio.sleep(0.05)  # small gap between writes
        await _send(client, char, pkt_b, "odd-segs-blue", wwr)
        print("Both packets sent. Observe: independent alternating colors = segment control confirmed.")
        await asyncio.sleep(5.0)
        # clean up
        await _send(client, char, build_h617e_segment_color_packet(0, 0, 0, 0xFF, 0x7F), "cleanup-black", wwr)
    print("Alternating test done.")


async def cmd_mode_scan(addr: str, start: int = 0x01, end: int = 0x2F):
    """
    Walk through candidate 33 05 <mode> bytes to find undiscovered packet modes.
    Resets to black before each mode so each one is clearly isolated.
    Known modes (02=solid, 15=segment-mask) are skipped.
    """
    from bleak import BleakClient
    device = await _get_device(addr)

    known = {0x02, 0x15}
    candidates = [m for m in range(start, end + 1) if m not in known]

    print(f"mode-scan: {len(candidates)} modes  (0x{start:02X}–0x{end:02X})  ~{len(candidates)*4}s")
    print("Strip resets to black before each mode. Watch for any change.\n")

    def _make_mode_packet(mode: int) -> bytes:
        payload = bytes([0x33, 0x05, mode, 0x01, 0xFF, 0x00, 0x00]) + bytes(12)
        return _finalize(payload)

    black = build_h617e_segment_color_packet(0, 0, 0, 0xFF, 0x7F)

    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)

        for mode in candidates:
            # Reset to black first so each mode starts clean
            await _send(client, char, black, "reset", wwr)
            await asyncio.sleep(0.5)

            pkt = _make_mode_packet(mode)
            print(f">>> MODE 0x{mode:02X}  ({' '.join(f'{b:02X}' for b in pkt)})")
            try:
                await _send(client, char, pkt, f"mode=0x{mode:02X}", wwr)
            except Exception as e:
                print(f"    WRITE ERROR: {e}")
            await asyncio.sleep(3.0)

        await _send(client, char, black, "cleanup", wwr)
        await asyncio.sleep(0.3)

    print("\nmode-scan done. Report the 0xXX value of any mode that did something.")


async def cmd_segment_seq_probe(addr: str):
    """
    Test hypothesis: 33 05 15 <start_idx> R0 G0 B0 R1 G1 B1 R2 G2 B2 R3 G3 B3 R4 G4 B4 XOR
    sets 5 segments from start_idx to 5 independent colors.
    If the strip shows a rainbow pattern, we have per-segment color control in 3 packets.

    Sends 3 packets covering segs 0-14 with a repeating R/G/B/W/Y pattern.
    If it works: strip shows rainbow stripes (not solid color).
    If it falls back to mask mode: strip shows one color for all segments (because byte3=0 = LEFT_MASK=0 = all off).
    """
    from bleak import BleakClient
    device = await _get_device(addr)

    # Test pattern: 5 colors cycling R/G/B/W/Y across 15 segments
    palette = [
        (255, 0,   0),    # red
        (0,   255, 0),    # green
        (0,   0,   255),  # blue
        (255, 255, 255),  # white
        (255, 255, 0),    # yellow
    ]
    all_colors = [palette[i % 5] for i in range(15)]

    def _seq_packet(start: int, colors: list) -> bytes:
        """33 05 15 <start> R0 G0 B0 R1 G1 B1 R2 G2 B2 R3 G3 B3 R4 G4 B4 XOR"""
        assert len(colors) == 5
        data = bytes([start])
        for r, g, b in colors:
            data += bytes([r, g, b])
        assert len(data) == 16
        payload = bytes([0x33, 0x05, 0x15]) + data
        return _finalize(payload)

    packets = [
        _seq_packet(0,  all_colors[0:5]),
        _seq_packet(5,  all_colors[5:10]),
        _seq_packet(10, all_colors[10:15]),
    ]

    print("segment-seq-probe: testing sequential per-segment color format.")
    print("Expected if it works: rainbow stripes across the strip.")
    print("Expected if it doesn't: strip goes black or one color (mask-mode fallback).\n")
    for i, (start, pkt) in enumerate(zip([0, 5, 10], packets)):
        print(f"  packet {i+1}: segs {start}-{start+4}  {' '.join(f'{b:02X}' for b in pkt)}")

    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        for pkt in packets:
            await _send(client, char, pkt, "seq-seg", wwr)
            await asyncio.sleep(0.05)
        print("\nPackets sent. Observe strip for ~5s...")
        await asyncio.sleep(5.0)

        # Send it again as a solid-red via mask to confirm strip is still responding normally
        print("Sending known-good all-red via mask for comparison...")
        await _send(client, char, build_h617e_segment_color_packet(255, 0, 0, 0xFF, 0x7F), "all-red-mask", wwr)
        await asyncio.sleep(3.0)

        black = build_h617e_segment_color_packet(0, 0, 0, 0xFF, 0x7F)
        await _send(client, char, black, "cleanup", wwr)
        await asyncio.sleep(0.3)

    print("segment-seq-probe done.")


async def cmd_probe_writes(addr: str):
    """
    Try multiple write formats in sequence to find which the H617E responds to.
    Each write is separated by 2s so the operator can observe visual changes.
    Logs every packet hex.
    """
    from bleak import BleakClient
    device = await _get_device(addr)
    print("probe-writes: trying multiple packet formats — watch the strip after each.")
    print("Each step waits 2s. Note which step produces a visible change.\n")

    variants = [
        # (label, packet_bytes)
        ("1. power-on (33 01 01)",        build_power_packet(True)),
        ("2. brightness-255 (33 04 FF)",  build_brightness_packet(255)),
        ("3. solid-red mode=02",          build_solid_color_packet(255, 0, 0)),
        ("4. solid-blue mode=02",         build_solid_color_packet(0, 0, 255)),
        ("5. solid-green mode=02",        build_solid_color_packet(0, 255, 0)),
        ("6. segment-red mode=15 grp=01 (BGR)", build_h617e_segment_color_packet(255, 0, 0, 0xFF, 0x7F)),
        ("7. segment-blue mode=15 grp=01 (BGR)", build_h617e_segment_color_packet(0, 0, 255, 0xFF, 0x7F)),
        ("8. segment-grn mode=15 grp=01 (BGR)", build_h617e_segment_color_packet(0, 255, 0, 0xFF, 0x7F)),
        ("9. keepalive (AA 01)",          build_keepalive_packet()),
        ("10. power-off (33 01 00)",      build_power_packet(False)),
        ("11. power-on  (33 01 01)",      build_power_packet(True)),
    ]

    async with BleakClient(device, timeout=20.0) as client:
        char, wwr = await _find_write_char(client)
        for label, pkt in variants:
            print(f"Sending {label}")
            _log_packet("→", pkt)
            try:
                await _send(client, char, pkt, label, wwr)
                print("  Sent OK — did strip change? (watching 2s)")
            except Exception as e:
                print(f"  WRITE ERROR: {e}")
            await asyncio.sleep(2.0)
    print("\nprobe-writes done. Report which step number produced a visible change.")


def cmd_frame_compiler_dry_run(rgb_segments: list[tuple[int, int, int]] | None = None):
    """
    No BLE writes. Take a list of RGB values (one per physical segment),
    group identical colors into masks, print packets that would be sent.
    """
    if rgb_segments is None:
        # default demo: alternating red/blue
        rgb_segments = [(255, 0, 0) if i % 2 == 0 else (0, 0, 255) for i in range(TOTAL_SEGMENTS)]

    print(f"Frame compiler dry-run ({len(rgb_segments)} segments):")
    for i, rgb in enumerate(rgb_segments):
        print(f"  seg[{i:2d}] = RGB{rgb}")

    # Group by color
    color_to_segs: dict[tuple, list[int]] = {}
    for i, rgb in enumerate(rgb_segments):
        color_to_segs.setdefault(rgb, []).append(i)

    print(f"\nColor groups ({len(color_to_segs)} unique colors → {len(color_to_segs)} packet(s)):")
    packets = []
    for rgb, segs in color_to_segs.items():
        r, g, b = rgb
        lm, rm = masks_for_segments(segs)
        pkt = build_h617e_segment_color_packet(r, g, b, lm, rm)
        print(f"  RGB{rgb} segs={segs} LEFT=0x{lm:02X} RIGHT=0x{rm:02X}")
        _log_packet("packet", pkt)
        packets.append(pkt)

    print(f"\nTotal BLE writes needed: {len(packets)} (one per unique color group)")
    print("Dry-run complete. No BLE writes performed.")


# ── CLI dispatch ──────────────────────────────────────────────────────────────

WRITE_COMMANDS = {
    "keepalive", "power-on", "power-off", "brightness",
    "all-red", "all-green", "all-blue", "all-black",
    "left-mask-sweep", "right-mask-sweep", "alternating-test",
}

def main():
    _run_self_tests()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd in ("scan", "scan-verbose"):
        asyncio.run(cmd_scan(verbose=(cmd == "scan-verbose")))

    elif cmd == "services":
        if len(sys.argv) < 3:
            print("Usage: services <addr>")
            sys.exit(1)
        asyncio.run(cmd_services(sys.argv[2]))

    elif cmd == "keepalive":
        if len(sys.argv) < 3:
            print("Usage: keepalive <addr> [duration_seconds=30]")
            sys.exit(1)
        dur = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        asyncio.run(cmd_keepalive(sys.argv[2], dur))

    elif cmd == "power-on":
        if len(sys.argv) < 3:
            print("Usage: power-on <addr>")
            sys.exit(1)
        asyncio.run(cmd_power(sys.argv[2], True))

    elif cmd == "power-off":
        if len(sys.argv) < 3:
            print("Usage: power-off <addr>")
            sys.exit(1)
        asyncio.run(cmd_power(sys.argv[2], False))

    elif cmd == "brightness":
        if len(sys.argv) < 4:
            print("Usage: brightness <addr> <0-255>")
            sys.exit(1)
        asyncio.run(cmd_brightness(sys.argv[2], int(sys.argv[3])))

    elif cmd == "all-red":
        asyncio.run(cmd_all_color(sys.argv[2], 255, 0, 0, "all-red"))

    elif cmd == "all-green":
        asyncio.run(cmd_all_color(sys.argv[2], 0, 255, 0, "all-green"))

    elif cmd == "all-blue":
        asyncio.run(cmd_all_color(sys.argv[2], 0, 0, 255, "all-blue"))

    elif cmd == "all-black":
        asyncio.run(cmd_all_color(sys.argv[2], 0, 0, 0, "all-black"))

    elif cmd == "left-mask-sweep":
        if len(sys.argv) < 3:
            print("Usage: left-mask-sweep <addr>")
            sys.exit(1)
        asyncio.run(cmd_left_mask_sweep(sys.argv[2]))

    elif cmd == "right-mask-sweep":
        if len(sys.argv) < 3:
            print("Usage: right-mask-sweep <addr>")
            sys.exit(1)
        asyncio.run(cmd_right_mask_sweep(sys.argv[2]))

    elif cmd == "alternating-test":
        if len(sys.argv) < 3:
            print("Usage: alternating-test <addr>")
            sys.exit(1)
        asyncio.run(cmd_alternating_test(sys.argv[2]))

    elif cmd == "mode-scan":
        if len(sys.argv) < 3:
            print("Usage: mode-scan <addr> [start_hex=01] [end_hex=2F]")
            sys.exit(1)
        start = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x01
        end   = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x2F
        asyncio.run(cmd_mode_scan(sys.argv[2], start, end))

    elif cmd == "segment-seq-probe":
        if len(sys.argv) < 3:
            print("Usage: segment-seq-probe <addr>")
            sys.exit(1)
        asyncio.run(cmd_segment_seq_probe(sys.argv[2]))

    elif cmd == "probe-writes":
        if len(sys.argv) < 3:
            print("Usage: probe-writes <addr>")
            sys.exit(1)
        asyncio.run(cmd_probe_writes(sys.argv[2]))

    elif cmd == "frame-compiler-dry-run":
        # Optional: pass segment RGB values as "R,G,B" space-separated args
        if len(sys.argv) > 2:
            segs = []
            for token in sys.argv[2:]:
                parts = token.split(",")
                segs.append((int(parts[0]), int(parts[1]), int(parts[2])))
            cmd_frame_compiler_dry_run(segs)
        else:
            cmd_frame_compiler_dry_run()

    elif cmd == "self-test":
        print("Self-tests passed (run at startup).")

    else:
        print(f"Unknown command: {cmd!r}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
