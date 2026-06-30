"""
Packet encoder tests for H617E BLE probe.
Run: python3 test_packet_encoder.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from govee_h617e_ble_segment_probe import (
    xor_checksum,
    build_keepalive_packet,
    build_power_packet,
    build_brightness_packet,
    build_h617e_segment_color_packet,
    masks_for_segments,
    TOTAL_SEGMENTS,
    LEFT_SEGMENT_COUNT,
    RIGHT_SEGMENT_COUNT,
)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  PASS  {name}")
        PASS += 1
    else:
        print(f"  FAIL  {name}  {detail}")
        FAIL += 1


# ── xor_checksum ─────────────────────────────────────────────────────────────

def test_xor_checksum():
    print("xor_checksum:")
    # AA ^ 01 = AB
    data = bytes([0xAA, 0x01]) + bytes(17)
    check("AA 01 zeros → 0xAB", xor_checksum(data) == 0xAB)

    # known keepalive last byte
    check("zeros 19 → 0x00", xor_checksum(bytes(19)) == 0x00)

    # must require exactly 19 bytes
    try:
        xor_checksum(bytes(18))
        check("rejects 18 bytes", False, "no error raised")
    except AssertionError:
        check("rejects 18 bytes", True)


# ── keepalive ─────────────────────────────────────────────────────────────────

def test_keepalive():
    print("build_keepalive_packet:")
    pkt = build_keepalive_packet()
    check("length=20", len(pkt) == 20)
    check("byte[0]=0xAA", pkt[0] == 0xAA)
    check("byte[1]=0x01", pkt[1] == 0x01)
    check("bytes[2..18]=0x00", all(b == 0 for b in pkt[2:19]))
    check("checksum=0xAB", pkt[19] == 0xAB)
    check("checksum valid", pkt[19] == xor_checksum(pkt[:19]))


# ── power ─────────────────────────────────────────────────────────────────────

def test_power():
    print("build_power_packet:")
    pon = build_power_packet(True)
    check("on: length=20", len(pon) == 20)
    check("on: byte[0]=0x33", pon[0] == 0x33)
    check("on: byte[1]=0x01", pon[1] == 0x01)
    check("on: byte[2]=0x01", pon[2] == 0x01)
    check("on: checksum valid", pon[19] == xor_checksum(pon[:19]))

    poff = build_power_packet(False)
    check("off: byte[2]=0x00", poff[2] == 0x00)
    check("off: checksum valid", poff[19] == xor_checksum(poff[:19]))


# ── brightness ───────────────────────────────────────────────────────────────

def test_brightness():
    print("build_brightness_packet:")
    pkt = build_brightness_packet(128)
    check("length=20", len(pkt) == 20)
    check("byte[0]=0x33", pkt[0] == 0x33)
    check("byte[1]=0x04", pkt[1] == 0x04)
    check("byte[2]=128", pkt[2] == 128)
    check("checksum valid", pkt[19] == xor_checksum(pkt[:19]))

    pkt0 = build_brightness_packet(0)
    check("brightness=0 valid", pkt0[19] == xor_checksum(pkt0[:19]))

    pkt255 = build_brightness_packet(255)
    check("brightness=255 valid", pkt255[19] == xor_checksum(pkt255[:19]))


# ── segment color ─────────────────────────────────────────────────────────────

def test_segment_color():
    print("build_h617e_segment_color_packet:")
    # mode=15 uses plain RGB; byte[4]=R=255, byte[5]=G=0, byte[6]=B=0
    red = build_h617e_segment_color_packet(255, 0, 0, 0xFF, 0x7F)
    check("length=20", len(red) == 20)
    check("byte[0]=0x33", red[0] == 0x33)
    check("byte[1]=0x05", red[1] == 0x05)
    check("byte[2]=0x15", red[2] == 0x15)
    check("byte[3]=0x01", red[3] == 0x01)
    check("R=255 (mode=15 RGB)",  red[4] == 255)
    check("G=0",                  red[5] == 0)
    check("B=0",                  red[6] == 0)
    check("padding bytes[7..11]=0", all(red[i] == 0 for i in range(7, 12)))
    check("LEFT_MASK=0xFF", red[12] == 0xFF)
    check("RIGHT_MASK=0x7F", red[13] == 0x7F)
    check("padding bytes[14..18]=0", all(red[i] == 0 for i in range(14, 19)))
    check("checksum valid", red[19] == xor_checksum(red[:19]))

    # single segment
    # green (0,255,0): mode=15 RGB, byte[5]=G=255
    s1 = build_h617e_segment_color_packet(0, 255, 0, 0x01, 0x00)
    check("single-left-bit0: checksum", s1[19] == xor_checksum(s1[:19]))
    check("single-left-bit0: LEFT=0x01", s1[12] == 0x01)
    check("single-left-bit0: RIGHT=0x00", s1[13] == 0x00)
    check("single-left-bit0: G=255", s1[5] == 255)

    # blue (0,0,255): mode=15 RGB, byte[6]=B=255
    s2 = build_h617e_segment_color_packet(0, 0, 255, 0x00, 0x01)
    check("single-right-bit0: LEFT=0x00", s2[12] == 0x00)
    check("single-right-bit0: RIGHT=0x01", s2[13] == 0x01)
    check("single-right-bit0: checksum", s2[19] == xor_checksum(s2[:19]))
    check("single-right-bit0: B=255", s2[6] == 255)


# ── masks_for_segments ────────────────────────────────────────────────────────

def test_masks():
    print("masks_for_segments:")
    check("segment_count=15", TOTAL_SEGMENTS == 15)
    check("left_count=8",  LEFT_SEGMENT_COUNT == 8)
    check("right_count=7", RIGHT_SEGMENT_COUNT == 7)

    lm, rm = masks_for_segments([0])
    check("seg0 → LEFT bit0", lm == 0x01 and rm == 0x00)

    lm, rm = masks_for_segments([7])
    check("seg7 → LEFT bit7", lm == 0x80 and rm == 0x00)

    lm, rm = masks_for_segments([8])
    check("seg8 → RIGHT bit0", lm == 0x00 and rm == 0x01)

    lm, rm = masks_for_segments([14])
    check("seg14 → RIGHT bit6", lm == 0x00 and rm == 0x40)

    lm, rm = masks_for_segments(list(range(15)))
    check("all segs → LEFT=0xFF RIGHT=0x7F", lm == 0xFF and rm == 0x7F)

    lm, rm = masks_for_segments([0, 1, 8, 9])
    check("0,1,8,9 → LEFT=0x03 RIGHT=0x03", lm == 0x03 and rm == 0x03)

    # even segments: 0,2,4,6 (left) + 8,10,12,14 (right bits 0,2,4,6)
    even = list(range(0, 15, 2))
    lm, rm = masks_for_segments(even)
    check("even segs LEFT=0x55", lm == 0x55)
    check("even segs RIGHT=0x55", rm == 0x55)

    odd = list(range(1, 15, 2))
    lm, rm = masks_for_segments(odd)
    check("odd segs LEFT=0xAA", lm == 0xAA)
    check("odd segs RIGHT=0x2A", rm == 0x2A)  # bits 1,3,5 of right (segs 9,11,13) = 0b0101010 = 0x2A

    # out of range
    try:
        masks_for_segments([15])
        check("rejects seg15", False, "no error raised")
    except AssertionError:
        check("rejects seg15", True)


# ── frame compiler dry-run (integration) ─────────────────────────────────────

def test_frame_compiler():
    print("frame_compiler_dry_run (packet integrity):")
    from govee_h617e_ble_segment_probe import cmd_frame_compiler_dry_run
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_frame_compiler_dry_run(
            [(255, 0, 0)] * 8 + [(0, 0, 255)] * 7  # left=red, right=blue
        )
    out = buf.getvalue()
    check("dry-run produced output", "packet" in out)
    check("no BLE writes claimed", "BLE writes" in out)


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_xor_checksum()
    test_keepalive()
    test_power()
    test_brightness()
    test_segment_color()
    test_masks()
    test_frame_compiler()
    print(f"\n{'='*40}")
    print(f"Results: {PASS} PASS, {FAIL} FAIL")
    if FAIL:
        sys.exit(1)
