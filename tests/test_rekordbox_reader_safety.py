"""Rekordbox reader cross-version safety.

Load-bearing guarantee: a garbage / out-of-range memory read — from the direct
reader OR the live-BPM memory scanner — can never feed SoundSwitch a tempo
outside an operator-tunable band, so it cannot drive a dangerously fast flash.
The clamp lives at the OS2L emit boundary (osl_output), so it covers BOTH the
computed-tempo path and the scanner-follow path (send_live_bpm_follow ->
send_bpm) that bypasses d.meta.bpm.

Also covers the offline version-extension mechanism: deriving a new build's
chain anchors from the rekordbox symbol table reproduces the known 7.2.11 row.
"""
from __future__ import annotations

import queue
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.osl_output import (  # noqa: E402
    OS2LOutput, clamp_emit_bpm, BPM_EMIT_MIN, BPM_EMIT_MAX,
)
from rb_ss_bridge_v2.sound_switch_engine import SoundSwitchEngine  # noqa: E402
from rb_ss_bridge_v2.rb_offsets import all_offsets, load_offsets_for_version  # noqa: E402
from rb_ss_bridge_v2.rb_state_reader import _RB_BPM_READ_MAX, make_rb_state_reader  # noqa: E402
from rb_ss_bridge_v2.live_bpm import (  # noqa: E402
    _normalize_rb_version, _valid_bpm, LIVE_BPM_MIN, LIVE_BPM_MAX,
)
from rb_ss_bridge_v2.tools.rekordbox_derive_offsets import (  # noqa: E402
    parse_nm, derive_anchors, SINGLETON_ANCHORS, INSTANCE_OFF, DEFAULT_IMAGE_BASE,
)


class _RecordConn:
    """Fake OS2LConnection that records every emitted message dict."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, obj: dict, verbose: bool = False) -> None:
        self.sent.append(obj)


def _emitted_bpms(sent: list[dict]) -> list[float]:
    """Every bpm/get_bpm value pulled out of recorded OS2L messages."""
    out: list[float] = []
    for o in sent:
        if o.get("evt") == "beat":
            out.append(o["bpm"])
        elif o.get("evt") == "subscribed" and str(o.get("trigger", "")).endswith("get_bpm"):
            out.append(o["value"])
    return out


class ClampEmitBpmTests(unittest.TestCase):
    def test_in_range_passthrough(self) -> None:
        for v in (BPM_EMIT_MIN, 60.0, 128.0, 174.5, BPM_EMIT_MAX):
            self.assertEqual(clamp_emit_bpm(v), v)

    def test_high_capped_to_max(self) -> None:
        self.assertEqual(clamp_emit_bpm(999.0), BPM_EMIT_MAX)
        self.assertEqual(clamp_emit_bpm(1e9), BPM_EMIT_MAX)

    def test_low_capped_to_min(self) -> None:
        self.assertEqual(clamp_emit_bpm(5.0), BPM_EMIT_MIN)

    def test_zero_negative_nonfinite_to_zero(self) -> None:
        for v in (0.0, -1.0, float("nan"), float("inf"), float("-inf")):
            self.assertEqual(clamp_emit_bpm(v), 0.0)


class EmitBoundaryClampTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = _RecordConn()
        self.out = OS2LOutput(self.conn)

    def test_send_bpm_clamps_garbage_high(self) -> None:
        self.out.send_bpm(1, 5000.0)
        self.assertEqual(_emitted_bpms(self.conn.sent), [BPM_EMIT_MAX])

    def test_send_beat_clamps_garbage_high(self) -> None:
        self.out.send_beat(1, 5000.0, 0)
        self.assertEqual(_emitted_bpms(self.conn.sent), [BPM_EMIT_MAX])

    def test_send_bpm_nan_becomes_zero(self) -> None:
        self.out.send_bpm(1, float("nan"))
        self.assertEqual(_emitted_bpms(self.conn.sent), [0.0])

    def test_realistic_bpm_unchanged(self) -> None:
        self.out.send_bpm(1, 128.0)
        self.out.send_beat(2, 174.0, 0)
        self.assertEqual(_emitted_bpms(self.conn.sent), [128.0, 174.0])

    def test_scanner_follow_path_is_clamped(self) -> None:
        # send_live_bpm_follow is the memory-SCANNER path; it fans out through
        # send_bpm, so a garbage scanned BPM must be clamped at the emit boundary
        # even though it never touches d.meta.bpm.
        SoundSwitchEngine(self.out).send_live_bpm_follow(1, 99999.0)
        vals = _emitted_bpms(self.conn.sent)
        self.assertTrue(vals, "expected a fanned-out 4-deck route")
        self.assertTrue(all(v == BPM_EMIT_MAX for v in vals))

    def test_autoloop_bpm_path_is_clamped(self) -> None:
        SoundSwitchEngine(self.out).send_autoloop_bpm(1, -3.0)
        self.assertTrue(all(v == 0.0 for v in _emitted_bpms(self.conn.sent)))


class InjectorClampTests(unittest.TestCase):
    """os2l_injector (RBSS_OS2L_INJECT debug path) writes to the OS2L socket
    directly, bypassing OS2LOutput; its bpm packets must be clamped too
    (adversarial-review finding A)."""

    def _packets(self, command: dict) -> list[dict]:
        from rb_ss_bridge_v2.os2l_injector import OS2LInjector
        return OS2LInjector(_RecordConn())._packets_for(command)

    def test_bpm_cmd_clamped(self) -> None:
        pkts = self._packets({"cmd": "bpm", "decks": [1], "bpm": 99999.0})
        self.assertEqual([p["value"] for p in pkts], [BPM_EMIT_MAX])

    def test_beat_change_clamped(self) -> None:
        pkts = self._packets({"cmd": "beat_change", "decks": [1], "bpm": 99999.0, "pos": 0})
        self.assertEqual([p["bpm"] for p in pkts], [BPM_EMIT_MAX])

    def test_arm_clamped(self) -> None:
        pkts = self._packets({"cmd": "arm", "decks": [1], "bpm": 99999.0, "filepath": "/x/y.mp3"})
        bpms = [p["value"] for p in pkts if str(p.get("trigger", "")).endswith("get_bpm")]
        self.assertEqual(bpms, [BPM_EMIT_MAX])


class UnknownVersionFailClosedTests(unittest.TestCase):
    def test_unknown_version_returns_none(self) -> None:
        self.assertIsNone(load_offsets_for_version("9.9.9"))
        self.assertIsNone(load_offsets_for_version(""))
        self.assertIsNone(load_offsets_for_version("7.2.12"))  # plausible FUTURE build

    def test_scanner_value_still_clamped_on_unknown_build(self) -> None:
        # Fail-closed is partial: the scanners keep running on an unsupported
        # build, but the version-INDEPENDENT emit clamp still bounds their output.
        conn = _RecordConn()
        SoundSwitchEngine(OS2LOutput(conn)).send_live_bpm_follow(1, 800.0)
        vals = _emitted_bpms(conn.sent)
        self.assertTrue(vals, "expected a fanned-out 4-deck route (guard against vacuous all([]))")
        self.assertTrue(all(v == BPM_EMIT_MAX for v in vals))


class InertReaderOnUnknownVersionTests(unittest.TestCase):
    def test_unknown_version_reader_is_inert(self) -> None:
        # make_rb_state_reader returns a reader with NO offsets on an unknown
        # build; run() early-returns when _offs is None, so it issues no direct
        # memory reads / BPM_UPDATE events (exercises the inert-reader limb).
        r = make_rb_state_reader(queue.Queue(), "9.9.9")
        self.assertIsNone(r._offs)

    def test_supported_version_reader_has_offsets(self) -> None:
        r = make_rb_state_reader(queue.Queue(), "7.2.11")
        self.assertIsNotNone(r._offs)


class ScannerBoundIsVersionIndependentTests(unittest.TestCase):
    def test_valid_bpm_gate_rejects_out_of_band(self) -> None:
        # The live-BPM scanner accepts only [40, 250] regardless of Rekordbox
        # version — the primary bound on the scanner path.
        self.assertLessEqual(LIVE_BPM_MAX, 250.0)
        self.assertGreaterEqual(LIVE_BPM_MIN, 40.0)
        for good in (LIVE_BPM_MIN, 128.0, 174.0, LIVE_BPM_MAX):
            self.assertTrue(_valid_bpm(good), good)
        for bad in (LIVE_BPM_MIN - 0.1, LIVE_BPM_MAX + 0.1, 999.0,
                    float("nan"), float("inf"), -1.0):
            self.assertFalse(_valid_bpm(bad), bad)


class DirectReadBpmCeilingTests(unittest.TestCase):
    def test_read_ceiling_is_a_real_tempo_bound(self) -> None:
        # A garbage direct-read BPM must be rejected before it can reach
        # d.meta.bpm -> beat-locked LED/laser flash timing. The ceiling must stay
        # a real-tempo bound, never the old permissive 1000.
        self.assertLessEqual(_RB_BPM_READ_MAX, 300.0)
        self.assertGreaterEqual(_RB_BPM_READ_MAX, 250.0)


class VersionStringNormalizationTests(unittest.TestCase):
    def test_four_component_truncates(self) -> None:
        self.assertEqual(_normalize_rb_version("7.2.11.0342"), "7.2.11")

    def test_three_component_passthrough(self) -> None:
        self.assertEqual(_normalize_rb_version("7.2.11"), "7.2.11")

    def test_too_short_is_empty(self) -> None:
        self.assertEqual(_normalize_rb_version("7.2"), "")
        self.assertEqual(_normalize_rb_version(""), "")

    def test_nondigit_component_rejected(self) -> None:
        self.assertEqual(_normalize_rb_version("7.2.11beta"), "")
        self.assertEqual(_normalize_rb_version("abc.def.ghi"), "")

    def test_normalized_but_unsupported_is_fail_closed(self) -> None:
        self.assertIsNone(load_offsets_for_version(_normalize_rb_version("7.2.99.1234")))


class PerVersionFieldPresenceTests(unittest.TestCase):
    def test_mixer_cfx_only_on_7_2_11(self) -> None:
        for ver, t in all_offsets().items():
            if ver == "7.2.11":
                self.assertIsNotNone(t.mixer_deck1_upfader_raw)
                self.assertIsNotNone(t.cfx_deck1_filter_param0)
            else:
                self.assertIsNone(t.mixer_deck1_upfader_raw, ver)
                self.assertIsNone(t.cfx_deck1_filter_param0, ver)


class VersionExtensionToolTests(unittest.TestCase):
    def test_derive_reproduces_known_7_2_11_anchors(self) -> None:
        # The three singletonHolder symbols at their real 7.2.11 vaddrs; deriving
        # anchor = symbol + 0x40 must reproduce the shipped table exactly.
        base = DEFAULT_IMAGE_BASE
        t = all_offsets()["7.2.11"]
        expected = {
            "master": t.master_deck.hops[0],
            "anlz": t.anlz_path_per_deck[0].hops[0],
            "mixer": t.mixer_deck1_upfader_raw.hops[0],
        }
        symbols = {
            SINGLETON_ANCHORS[role]: base + (rva - INSTANCE_OFF)
            for role, rva in expected.items()
        }
        self.assertEqual(derive_anchors(symbols, base), expected)

    def test_missing_symbol_fails_closed(self) -> None:
        with self.assertRaises(KeyError):
            derive_anchors({}, DEFAULT_IMAGE_BASE)
        with self.assertRaises(KeyError):
            derive_anchors({SINGLETON_ANCHORS["master"]: 0x104e18958}, DEFAULT_IMAGE_BASE)

    def test_duplicate_anchor_symbol_fails_closed(self) -> None:
        # An anchor symbol at two different addresses is ambiguous -> raise,
        # never silently pick one (adversarial-review finding E).
        txt = (
            "0000000104e18958 s __ZN15ApplicationMode15singletonHolderE\n"
            "0000000205e18958 s __ZN15ApplicationMode15singletonHolderE\n"
        )
        with self.assertRaises(ValueError):
            parse_nm(txt)

    def test_implausible_rva_fails_closed(self) -> None:
        # A wrong-arch / bad address deriving an absurd RVA must raise, not
        # return a silently-wrong offset (adversarial-review finding E).
        base = DEFAULT_IMAGE_BASE
        bad = {sym: base + 0x40000000 for sym in SINGLETON_ANCHORS.values()}
        with self.assertRaises(ValueError):
            derive_anchors(bad, base)

    def test_parse_nm_skips_malformed(self) -> None:
        txt = (
            "0000000104e18958 s __ZN15ApplicationMode15singletonHolderE\n"
            "badline\n"
            "0000000104e16ea8 s __ZN8djengine10DjEngineIF15singletonHolderE\n"
        )
        d = parse_nm(txt)
        self.assertEqual(d["__ZN15ApplicationMode15singletonHolderE"], 0x104e18958)
        self.assertEqual(len(d), 2)


if __name__ == "__main__":
    unittest.main()
