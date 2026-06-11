#!/usr/bin/env python3
"""
SoundSwitch memory probe — investigation tool for PR-F discovery.

Read-only. No writes, no injection, no patching. mach_vm_read_overwrite only.
Stands outside the production import graph; never imported by the bridge.

Subcommands:
    regions <pid>                       — dump readable/writable regions via vmmap
    smoketest <pid>                     — verify task_for_pid + a single vm_read
    find-string <pid> <needle> [opts]   — scan readable regions for a string
    read <pid> <addr> <len>             — hex dump
    walk <pid> <addr> [steps]           — follow pointer chain with bounds checks
    watch <pid> <addr> <len> [hz secs]  — periodic read, log when bytes change

Usage:
    python3 tools/ss_memory_probe.py smoketest 71767
    python3 tools/ss_memory_probe.py find-string 71767 "NEON STUTTER" --enc utf-16le
    python3 tools/ss_memory_probe.py read 71767 0x1015bc000 256
"""
from __future__ import annotations

import argparse
import ctypes
import re
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Iterator


KERN_SUCCESS = 0
KERN_INVALID_ADDRESS = 1
KERN_PROTECTION_FAILURE = 2
KERN_INVALID_ARGUMENT = 4
KERN_NO_ACCESS = 8

KERN_NAMES = {
    0: "KERN_SUCCESS",
    1: "KERN_INVALID_ADDRESS",
    2: "KERN_PROTECTION_FAILURE",
    3: "KERN_NO_SPACE",
    4: "KERN_INVALID_ARGUMENT",
    5: "KERN_FAILURE",
    8: "KERN_NO_ACCESS",
}


_libsys = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
_task_self_var = ctypes.c_uint32.in_dll(_libsys, "mach_task_self_")

_fn_task_for_pid = _libsys.task_for_pid
_fn_task_for_pid.restype = ctypes.c_int
_fn_task_for_pid.argtypes = [
    ctypes.c_uint32,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_uint32),
]

_fn_vm_read = _libsys.mach_vm_read_overwrite
_fn_vm_read.restype = ctypes.c_int
_fn_vm_read.argtypes = [
    ctypes.c_uint32,
    ctypes.c_uint64,
    ctypes.c_uint64,
    ctypes.c_uint64,
    ctypes.POINTER(ctypes.c_uint64),
]


def task_for_pid(pid: int) -> int:
    task = ctypes.c_uint32(0)
    kr = _fn_task_for_pid(_task_self_var.value, pid, ctypes.byref(task))
    if kr != KERN_SUCCESS:
        name = KERN_NAMES.get(kr, f"kr={kr}")
        raise OSError(
            f"task_for_pid({pid}) failed: {name}. "
            "On macOS, this typically requires the target to have "
            "com.apple.security.get-task-allow=true, or the caller to run as root, "
            "or the caller to be signed with com.apple.security.cs.debugger."
        )
    return task.value


def vm_read(task: int, addr: int, size: int) -> bytes:
    buf = (ctypes.c_uint8 * size)()
    out = ctypes.c_uint64(0)
    kr = _fn_vm_read(task, addr, size, ctypes.addressof(buf), ctypes.byref(out))
    if kr != KERN_SUCCESS:
        name = KERN_NAMES.get(kr, f"kr={kr}")
        raise OSError(f"vm_read(0x{addr:x}, {size}) failed: {name}")
    return bytes(buf[: int(out.value)])


def vm_read_safe(task: int, addr: int, size: int) -> bytes | None:
    try:
        return vm_read(task, addr, size)
    except OSError:
        return None


@dataclass
class Region:
    start: int
    end: int
    perms: str
    detail: str

    @property
    def size(self) -> int:
        return self.end - self.start

    @property
    def readable(self) -> bool:
        return "r" in self.perms.split("/")[0]

    @property
    def writable(self) -> bool:
        return "w" in self.perms.split("/")[0]


_REGION_RE = re.compile(
    r"^(?P<type>\S(?:\S| )*?)\s+"
    r"(?P<start>[0-9a-f]+)-(?P<end>[0-9a-f]+)\s+"
    r"\[\s*[^\]]+\]\s+"
    r"(?P<perms>\S+)\s+"
    r"SM=\S+\s*"
    r"(?P<detail>.*)$"
)


def list_regions(pid: int) -> list[Region]:
    out = subprocess.run(
        ["/usr/bin/vmmap", str(pid)],
        capture_output=True, text=True, check=True,
    ).stdout
    regions: list[Region] = []
    for line in out.splitlines():
        m = _REGION_RE.match(line)
        if not m:
            continue
        rtype = m.group("type").strip()
        start = int(m.group("start"), 16)
        end = int(m.group("end"), 16)
        perms = m.group("perms")
        detail = (rtype + " " + m.group("detail")).strip()
        regions.append(Region(start, end, perms, detail))
    return regions


def cmd_regions(args: argparse.Namespace) -> int:
    regions = list_regions(args.pid)
    show_writable_only = args.writable
    for r in regions:
        if show_writable_only and not r.writable:
            continue
        print(f"0x{r.start:012x}-0x{r.end:012x} {r.size:>12d}  {r.perms}  {r.detail}")
    return 0


def cmd_smoketest(args: argparse.Namespace) -> int:
    pid = args.pid
    print(f"[smoketest] pid={pid}")
    try:
        task = task_for_pid(pid)
        print(f"[smoketest] task_for_pid -> port=0x{task:x}")
    except OSError as e:
        print(f"[smoketest] FAIL: {e}")
        return 2

    regions = list_regions(pid)
    targets = [r for r in regions if r.readable and "SoundSwitch" in r.detail and "__TEXT" in r.detail]
    if not targets:
        targets = [r for r in regions if r.readable][:1]
    if not targets:
        print("[smoketest] FAIL: no readable regions found")
        return 3

    r = targets[0]
    print(f"[smoketest] reading 64B from {r.detail} @ 0x{r.start:x}")
    try:
        data = vm_read(task, r.start, 64)
    except OSError as e:
        print(f"[smoketest] FAIL: {e}")
        return 4

    hex_str = " ".join(f"{b:02x}" for b in data[:32])
    print(f"[smoketest] OK: read {len(data)} bytes")
    print(f"[smoketest] head: {hex_str}")
    if data[:4] == b"\xcf\xfa\xed\xfe":
        print("[smoketest] confirmed mach-o magic (MH_MAGIC_64) at region head")
    return 0


def encode_needle(needle: str, encoding: str) -> bytes:
    if encoding == "utf-16le":
        return needle.encode("utf-16-le")
    if encoding == "utf-16be":
        return needle.encode("utf-16-be")
    return needle.encode(encoding)


def iter_region_chunks(task: int, region: Region, chunk: int = 1 << 20) -> Iterator[tuple[int, bytes]]:
    addr = region.start
    while addr < region.end:
        size = min(chunk, region.end - addr)
        data = vm_read_safe(task, addr, size)
        if data is None:
            addr += size
            continue
        yield addr, data
        addr += size


def cmd_find_string(args: argparse.Namespace) -> int:
    pid = args.pid
    needle = encode_needle(args.needle, args.enc)
    task = task_for_pid(pid)
    regions = list_regions(pid)

    if args.regions == "all":
        scan_regions = [r for r in regions if r.readable]
    elif args.regions == "writable":
        scan_regions = [r for r in regions if r.readable and r.writable]
    elif args.regions == "malloc":
        scan_regions = [r for r in regions if r.readable and "MALLOC" in r.detail]
    elif args.regions == "binary":
        scan_regions = [r for r in regions if r.readable and "SoundSwitch" in r.detail]
    else:
        scan_regions = [r for r in regions if r.readable]

    print(f"[find] needle={args.needle!r} enc={args.enc} bytes={needle.hex()} regions={len(scan_regions)}")
    hits = 0
    for region in scan_regions:
        for base, data in iter_region_chunks(task, region):
            idx = 0
            while True:
                pos = data.find(needle, idx)
                if pos < 0:
                    break
                addr = base + pos
                ctx_start = max(0, pos - 16)
                ctx_end = min(len(data), pos + len(needle) + 16)
                ctx = data[ctx_start:ctx_end]
                hex_ctx = " ".join(f"{b:02x}" for b in ctx)
                print(f"[hit] 0x{addr:012x} in {region.detail}")
                print(f"      ctx: {hex_ctx}")
                hits += 1
                if args.max and hits >= args.max:
                    print(f"[find] reached max={args.max}, stopping")
                    return 0
                idx = pos + 1
    print(f"[find] total hits: {hits}")
    return 0 if hits else 1


def cmd_read(args: argparse.Namespace) -> int:
    task = task_for_pid(args.pid)
    data = vm_read(task, args.addr, args.length)
    print(f"[read] addr=0x{args.addr:x} len={args.length} got={len(data)}")
    width = 16
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  0x{args.addr + i:012x}  {hex_part:<{width*3}}  {ascii_part}")
    return 0


def cmd_walk(args: argparse.Namespace) -> int:
    task = task_for_pid(args.pid)
    addr = args.addr
    print(f"[walk] start=0x{addr:x} steps={args.steps}")
    for i in range(args.steps):
        data = vm_read_safe(task, addr, 8)
        if data is None or len(data) < 8:
            print(f"  step {i}: 0x{addr:012x} → unreadable, stop")
            return 1
        nxt = struct.unpack("<Q", data)[0]
        print(f"  step {i}: 0x{addr:012x} → 0x{nxt:012x}")
        if nxt == 0:
            print("  null pointer, stop")
            return 0
        addr = nxt
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    task = task_for_pid(args.pid)
    period = 1.0 / args.hz
    deadline = time.monotonic() + args.duration if args.duration > 0 else float("inf")
    last = None
    changes = 0
    reads = 0
    print(f"[watch] addr=0x{args.addr:x} len={args.length} hz={args.hz} duration={args.duration}s")
    while time.monotonic() < deadline:
        data = vm_read_safe(task, args.addr, args.length)
        reads += 1
        if data is None:
            print(f"[watch] read failed at {time.strftime('%H:%M:%S')}")
            time.sleep(period)
            continue
        if data != last:
            changes += 1
            hex_str = " ".join(f"{b:02x}" for b in data)
            print(f"[watch] {time.strftime('%H:%M:%S.%f')[:-3]} change#{changes}: {hex_str}")
            last = data
        time.sleep(period)
    print(f"[watch] total reads={reads} changes={changes}")
    return 0


def _addr(s: str) -> int:
    return int(s, 0)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="SoundSwitch memory probe (read-only)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("regions")
    sp.add_argument("pid", type=int)
    sp.add_argument("--writable", action="store_true")
    sp.set_defaults(func=cmd_regions)

    sp = sub.add_parser("smoketest")
    sp.add_argument("pid", type=int)
    sp.set_defaults(func=cmd_smoketest)

    sp = sub.add_parser("find-string")
    sp.add_argument("pid", type=int)
    sp.add_argument("needle", type=str)
    sp.add_argument("--enc", default="utf-8",
                    choices=["utf-8", "utf-16le", "utf-16be", "ascii", "latin-1"])
    sp.add_argument("--regions", default="all",
                    choices=["all", "writable", "malloc", "binary"])
    sp.add_argument("--max", type=int, default=0, help="stop after N hits (0=unlimited)")
    sp.set_defaults(func=cmd_find_string)

    sp = sub.add_parser("read")
    sp.add_argument("pid", type=int)
    sp.add_argument("addr", type=_addr)
    sp.add_argument("length", type=int)
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("walk")
    sp.add_argument("pid", type=int)
    sp.add_argument("addr", type=_addr)
    sp.add_argument("--steps", type=int, default=8)
    sp.set_defaults(func=cmd_walk)

    sp = sub.add_parser("watch")
    sp.add_argument("pid", type=int)
    sp.add_argument("addr", type=_addr)
    sp.add_argument("length", type=int)
    sp.add_argument("--hz", type=float, default=10.0)
    sp.add_argument("--duration", type=float, default=10.0)
    sp.set_defaults(func=cmd_watch)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
