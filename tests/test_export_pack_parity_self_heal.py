"""Real-project tests for the export-time parity-registry self-heal.

`_compile_and_stage_with_self_healed_parity()` recomputes each parity
surface's registry from the committed capture fixtures
(`tests/fixtures/soundswitch/parity_oracle/*_reduced.json`) against the pack
actually being exported. This closes the "first new SoundSwitch cue after the
committed registry snapshot" gap: a venue-cue ADDITION changes
`SoundSwitchVenues.bin`'s sha, which used to strand every witnessed document
in `unverified_parity` until someone manually reran
`tools/ssfmt/update_parity_registry.py` and committed fresh snapshots. Now the
export itself heals a stale snapshot from the fixtures it was originally
derived from.

Machine-local: needs the maintainer's real, read-only SoundSwitch project.
Guarded like `tests/test_soundswitch_parity_oracle.py::ReducedCaptureFixtureTests`.
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.tools import export_soundswitch_pack as export_module
from rb_ss_bridge_v2.tools.export_soundswitch_pack import export_pack

SOURCE_PROJECT = Path.home() / "Music/SoundSwitch/default.ssproj"
# Lane split after the 2026-07-02 exact-R + precede-association correction:
# SSAutoLoop14/48 moved from algorithm_generalized to oracle_proven when
# their previously "lit divergent" fixture rows started matching byte-exactly
# under the corrected render model.
#
# re-baselined 2026-07-16 (AWR-276): the operator (a) authored 2 new static
# looks into SoundSwitchVenues.bin (its sha changed 6ec3.. -> dd7d..) and
# (b) had earlier edited SSAutoLoop16.ssfile and SSAutoLoop52.ssfile after the
# 2026-07-02 capture, so those two loops no longer render byte-exact against
# their committed capture evidence. The two paths under test now land on
# DIFFERENT lane splits, and that difference is real -- not a pin that should
# be forced equal:
#
#  * Healed export (fixtures present -- the operator's real publish path):
#    the recompute-from-fixtures pass witnesses that 16/52 diverged and RETIRES
#    their stale evidence (reconcile_edited_witnesses), so both loops fall back
#    to algorithm_generalized on their supported layout family. Result:
#    70 algorithm_generalized / 14 oracle_proven / 0 unverified -- publishable.
#
#  * Fixtures-absent fallback (a degraded safety net, not the real path):
#    with no capture fixtures to re-verify against, the committed snapshot's
#    stale-source records for 16/52 cannot be retired, so those two loops
#    strand as unverified_parity (fail-closed). Result:
#    68 algorithm_generalized / 14 oracle_proven / 2 unverified.
#
# Both splits are taken from the export tooling against the current venue, not
# hand-tuned.
EXPECTED_HEALED_LANES = {
    "algorithm_generalized": 70, "oracle_proven": 14, "unverified_parity": 0,
}
EXPECTED_FALLBACK_LANES = {
    "algorithm_generalized": 68, "oracle_proven": 14, "unverified_parity": 2,
}
WITNESSED_SCRIPTED_SSID = "528e8b22-bd17-41b9-a111-275d3e8b3031"


@unittest.skipUnless((SOURCE_PROJECT / ".ssproj").is_file(),
                     "canonical read-only SoundSwitch project is unavailable")
class ExportSelfHealsStaleParityRegistryTests(unittest.TestCase):
    """A stale committed snapshot (wrong venue sha) must be healed at export
    time from the real committed capture fixtures, not permanently strand the
    pack in `unverified_parity`."""

    def _corrupted_snapshot(self) -> dict[str, object]:
        real = export_module._load_parity_registries()
        corrupted = copy.deepcopy(real)
        for row in corrupted["scripted"].values():
            row["venue_source_sha256"] = "0" * 64
        for row in corrupted["autoloop"].values():
            row["venue_source_sha256"] = "0" * 64
        static = corrupted["static"]
        if isinstance(static, dict) and "venue_source_sha256" in static:
            static["venue_source_sha256"] = "0" * 64
        return corrupted

    def test_stale_venue_sha_snapshot_is_healed_at_export(self) -> None:
        corrupted = self._corrupted_snapshot()
        real_compile = export_module.compile_pack_artifacts
        observed_registries: list[object] = []

        def spy_compile(*args, **kwargs):
            observed_registries.append(kwargs.get("parity_registry"))
            return real_compile(*args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "pack"
            with mock.patch.object(export_module, "_load_parity_registries", return_value=corrupted), \
                 mock.patch.object(export_module, "compile_pack_artifacts", side_effect=spy_compile):
                export_pack(SOURCE_PROJECT, dest)

            manifest = json.loads((dest / "manifest.json").read_text())
            self.assertEqual(manifest["parity_lanes"], EXPECTED_HEALED_LANES)

            scripted_doc = json.loads(
                (dest / f"scripted/{WITNESSED_SCRIPTED_SSID}.json").read_text()
            )["document"]
            self.assertEqual(scripted_doc["parity_lane"], "oracle_proven")
            evidence = scripted_doc["parity_evidence"]
            self.assertEqual(evidence["reason"], "registry_u0_oracle")
            self.assertTrue(evidence["capture_id"])
            self.assertTrue(evidence["oracle_report_sha256"])

        # The second-compile path must actually have run: pass 1 compiled with
        # the corrupted (stale) registries; pass 2 compiled with the healed
        # (fresh) registries, which must differ from the stale ones fed in.
        self.assertEqual(len(observed_registries), 2)
        self.assertEqual(observed_registries[0], corrupted)
        self.assertNotEqual(observed_registries[1], corrupted)


@unittest.skipUnless((SOURCE_PROJECT / ".ssproj").is_file(),
                     "canonical read-only SoundSwitch project is unavailable")
class ExportFallsBackWhenFixturesAreAbsentTests(unittest.TestCase):
    """A missing capture fixture must not crash the export -- it must fall
    back to the committed registry snapshot for that surface (status quo)."""

    def test_absent_fixtures_fall_back_to_committed_snapshot(self) -> None:
        missing_dir = Path("/nonexistent-parity-fixture-dir-for-self-heal-fallback-test")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "pack"
            with mock.patch.object(export_module, "SCRIPTED_FIXTURE",
                                   missing_dir / "scripted_reduced.json"), \
                 mock.patch.object(export_module, "AUTOLOOP_FIXTURE",
                                   missing_dir / "autoloop_reduced.json"), \
                 mock.patch.object(export_module, "STATIC_FIXTURE",
                                   missing_dir / "static_reduced.json"):
                export_pack(SOURCE_PROJECT, dest)

            manifest = json.loads((dest / "manifest.json").read_text())
            self.assertEqual(manifest["parity_lanes"], EXPECTED_FALLBACK_LANES)


if __name__ == "__main__":
    unittest.main()
