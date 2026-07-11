"""AWR-207 R1 — executed end-to-end phrase proof, NO mocked seams.

The original AWR-207 resolver tests mocked `_extract_beatgrid_from_anlz` /
`read_anlz_drops` / `_start_anlz_worker`, so nothing proved that phrase markers
actually flow when a USB-export track resolves to its local twin. This test
drives the REAL production chain over REAL ANLZ files built on disk:

    _db_lookup_by_anlz(usb_path)              # real resolver + fingerprint match
      -> _payload_for_content / _local_anlz_path   # real payload build
      -> StateManager._on_filepath_resolved   # real local_anlz_path routing
        -> _start_anlz_worker(local_twin)     # real worker thread
          -> _read_runtime_anlz_data -> read_anlz_drops   # real PSSI parse
            -> ANLZ_DATA event with real drop_beat_indices

Only two things are injected, and neither is a seam in the logic under test:
  * the Rekordbox DB (a data source) is a fake returning one content row;
  * `_RB_SHARE_ROOT` (a config constant) points at the temp share dir.
Every resolver/worker/parser function runs for real against real files.

The fixtures mirror the operator's live situation exactly: the USB export
carries a PQTZ beatgrid but NO PSSI phrase; the local twin carries the same
beatgrid plus a real PSSI phrase in its .EXT sibling.
"""
from __future__ import annotations

import os
import queue
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from construct import Container  # noqa: E402
from pyrekordbox.anlz import structs  # noqa: E402

from rb_ss_bridge_v2.models import BridgeEvent, Ev  # noqa: E402
from rb_ss_bridge_v2.rb_memory import PositionCache  # noqa: E402
from rb_ss_bridge_v2.state_manager import StateManager  # noqa: E402
from rb_ss_bridge_v2.filepath_resolver import _db_lookup_by_anlz  # noqa: E402


_BEATS = 400
_BEAT_MS = 60000.0 / 128.0            # 128.000 BPM, constant tempo
_TEMPO_CENTIBPM = 12800
_ANALYSIS_REL = "PIONEER/USBANLZ/967/938c2a63-a637-4000-8000-000000000001/ANLZ0000.DAT"
_USB_ANLZ = "PIONEER/USBANLZ/P018/000086A0/ANLZ0000.DAT"   # non-UUID device id


# ── real ANLZ fixture builders (pyrekordbox construct structs) ───────────────
def _tick(i: int) -> Container:
    return Container(beat=(i % 4) + 1, tempo=_TEMPO_CENTIBPM, time=int(round(i * _BEAT_MS)))


def _sse(index: int, beat: int, kind: int) -> Container:
    # SongStructureEntry: only index/beat/kind matter to _extract_pssi_phrases.
    return Container(
        index=index, beat=beat, kind=kind, u1=0, k1=0, u2=0, k2=0, u3=0, b=0,
        beat_2=0, beat_3=0, beat_4=0, u4=0, k3=0, u5=0, fill=0, beat_fill=0,
    )


def _tag_bytes(tag_type: str, content_struct, content: Container, len_header: int) -> bytes:
    content_len = len(content_struct.build(content))
    return structs.AnlzTag.build(Container(
        type=tag_type, len_header=len_header, len_tag=12 + content_len, content=content,
    ))


def _anlz_file(*tag_bytes: bytes) -> bytes:
    body = b"".join(tag_bytes)
    header = Container(type="PMAI", len_header=28, len_file=28 + len(body),
                       u1=0, u2=0, u3=0, u4=0)
    return structs.AnlzFileHeader.build(header) + body


def _pqtz_bytes() -> bytes:
    content = Container(entry_count=_BEATS, entries=[_tick(i) for i in range(_BEATS)])
    return _tag_bytes("PQTZ", structs.PQTZ, content, len_header=24)


def _pssi_bytes() -> bytes:
    # mood=1: kind 2=buildup, 3=breakdown, 5=DROP. bridge_beat = beat-1.
    entries = [_sse(1, 17, 2), _sse(2, 33, 3), _sse(3, 65, 5)]
    content = Container(
        len_entries=len(entries), mood=1, u1=b"\0" * 6, end_beat=_BEATS,
        u2=b"\0" * 2, bank=0, u3=b"\0", entries=entries,
    )
    return _tag_bytes("PSSI", structs.PSSI, content, len_header=32)


def _write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class _FakeDB:
    """One local content row. Same shape the resolver reads from the real DB."""

    def __init__(self, content) -> None:
        self._content = content
        self.closed = False

    def get_content(self):
        return [self._content]

    def get_cue(self, **_kwargs):
        return []

    def close(self):
        self.closed = True


def _manager() -> StateManager:
    env = {"RBSS_SMART_REARM_EXPERIMENT": "1", "RBSS_SPECTRAL_ENABLE": "1"}
    with patch.dict(os.environ, env, clear=False):
        return StateManager(queue.Queue(), PositionCache(), Mock())


def _drain_anlz_data(eq: "queue.Queue", timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            ev = eq.get(timeout=0.2)
        except queue.Empty:
            continue
        if ev.kind == Ev.ANLZ_DATA:
            return ev
    return None


class Awr207UsbPhraseEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="awr207_e2e_")
        share = os.path.join(self._tmp, "share")
        self.local_dat = os.path.join(share, _ANALYSIS_REL)
        self.local_ext = self.local_dat[:-4] + ".EXT"
        self.usb_dat = os.path.join(self._tmp, "usb", _USB_ANLZ)
        # Local twin: beatgrid in .DAT, phrase (PSSI) in .EXT sibling.
        _write(self.local_dat, _anlz_file(_pqtz_bytes()))
        _write(self.local_ext, _anlz_file(_pssi_bytes()))
        # USB export: same beatgrid, NO phrase (operator-confirmed root fact).
        _write(self.usb_dat, _anlz_file(_pqtz_bytes()))
        self._share_root = Path(share)
        self._content = SimpleNamespace(
            ID="39964930", FolderPath="/music/twin.wav",
            AnalysisDataPath=_ANALYSIS_REL, BPM=_TEMPO_CENTIBPM,
            Length=int(round((_BEATS - 1) * _BEAT_MS / 1000.0)), rb_local_deleted=0,
        )

    def _resolve_usb(self) -> dict:
        with patch("pyrekordbox.db6.Rekordbox6Database", return_value=_FakeDB(self._content)), \
             patch("rb_ss_bridge_v2.filepath_resolver._RB_SHARE_ROOT", self._share_root):
            return _db_lookup_by_anlz(self.usb_dat)

    def test_real_resolver_matches_twin_and_carries_local_anlz_path(self) -> None:
        payload = self._resolve_usb()
        self.assertIsNotNone(payload)
        self.assertEqual(payload["content_id"], "39964930")
        # Real fingerprint match routed the LOCAL twin's ANLZ path (built by the
        # real _local_anlz_path against the patched share root).
        self.assertEqual(payload["local_anlz_path"], self.local_dat)
        self.assertTrue(payload["beatgrid_times_ms"])

    def test_phrase_flows_end_to_end_via_real_start_anlz_worker(self) -> None:
        payload = self._resolve_usb()
        self.assertIsNotNone(payload)

        sm = _manager()
        gen = sm._deck[1].load_gen
        payload["load_gen"] = gen
        # Mirror the raw USB path stored at TRACK_LOADED time; _on_filepath_resolved
        # must prefer payload["local_anlz_path"] over it (state_manager.py:2552).
        sm._loaded_anlz_path[1] = (self.usb_dat, gen)

        # REAL _on_filepath_resolved -> REAL _start_anlz_worker thread -> REAL
        # read_anlz_drops over the local twin (finds its .EXT sibling for PSSI).
        sm._on_filepath_resolved(1, payload)
        ev = _drain_anlz_data(sm._eq)

        self.assertIsNotNone(ev, "no ANLZ_DATA emitted by the real worker")
        self.assertEqual(ev.payload.get("load_gen"), gen)
        # Phrase actually landed: PSSI drop at beat 65 -> bridge beat 64.
        self.assertEqual(list(ev.payload.get("drop_beat_indices", [])), [64])
        self.assertEqual(list(ev.payload.get("breakdown_beat_indices", [])), [32])

    def test_raw_usb_path_yields_no_phrase_proving_the_differential(self) -> None:
        # The whole point of Task 1b/1c: parsing the RAW USB ANLZ yields nothing,
        # so routing the local twin is what makes phrase appear.
        sm = _manager()
        gen = sm._deck[1].load_gen
        sm._start_anlz_worker(self.usb_dat, 1, gen, spectral_enabled=False)
        ev = _drain_anlz_data(sm._eq)

        self.assertIsNotNone(ev, "no ANLZ_DATA emitted for the raw USB path")
        self.assertEqual(list(ev.payload.get("drop_beat_indices", [])), [])
        self.assertEqual(list(ev.payload.get("breakdown_beat_indices", [])), [])


if __name__ == "__main__":
    unittest.main()
