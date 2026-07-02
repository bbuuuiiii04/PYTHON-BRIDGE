"""Focused tests for computed SoundSwitch parity lanes."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_pack_loader import LoadedPack
from rb_ss_bridge_v2.soundswitch_pack_runtime import PackRuntime
from rb_ss_bridge_v2.soundswitch_parity_registry import (
    classify_parity_lane,
    count_lanes,
    parity_evidence,
)


class ParityLaneClassifierTests(unittest.TestCase):
    def test_lane_classifier_uses_evidence_not_identity(self) -> None:
        self.assertEqual(
            classify_parity_lane(
                structural_supported=True,
                oracle_report={"verdict": "PASS", "truth_source": "SoundSwitch U0"},
            ),
            "oracle_proven",
        )
        self.assertEqual(
            classify_parity_lane(structural_supported=True, generalized_witness_passed=True),
            "algorithm_generalized",
        )
        self.assertEqual(
            classify_parity_lane(
                structural_supported=True,
                oracle_report={"verdict": "PASS", "truth_source": "pack self-render"},
            ),
            "unverified_parity",
        )

    def test_lane_counts_and_evidence_are_sanitized(self) -> None:
        self.assertEqual(
            count_lanes(["oracle_proven", "algorithm_generalized", "unknown"]),
            {"algorithm_generalized": 1, "oracle_proven": 1, "unverified_parity": 1},
        )
        self.assertEqual(
            parity_evidence(
                lane="unverified_parity",
                reason="no_u0_oracle_evidence",
                structural_supported=True,
            )["truth_source"],
            "",
        )

    def test_runtime_status_exposes_unverified_lanes(self) -> None:
        pack = LoadedPack(
            schema_version="1.0.0",
            manifest_sha256="0" * 64,
            has_intensity_channel=False,
            scripted=MappingProxyType({}),
            autoloops=MappingProxyType({}),
            static_looks=MappingProxyType({}),
            parity_summary=MappingProxyType({
                "algorithm_generalized": 1,
                "oracle_proven": 2,
                "unverified_parity": 3,
            }),
            unverified_documents=("scripted:a", "autoloop:b", "static:1"),
        )
        runtime = PackRuntime(player=SimpleNamespace(pack=pack))
        status = runtime.sanitized_status()
        self.assertEqual(status["unverified_parity_count"], 3)
        self.assertEqual(status["unverified_documents"], ["scripted:a", "autoloop:b", "static:1"])


if __name__ == "__main__":
    unittest.main()
