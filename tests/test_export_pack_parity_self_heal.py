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

from rb_ss_bridge_v2 import soundswitch_pack
from rb_ss_bridge_v2.soundswitch_project_decoder import decode_project
from rb_ss_bridge_v2.tools import export_soundswitch_pack as export_module
from rb_ss_bridge_v2.tools.export_soundswitch_pack import export_pack

SOURCE_PROJECT = Path.home() / "Music/SoundSwitch/default.ssproj"
# Healed-export lane split (fixtures present -- the operator's real publish
# path). Re-baselined 2026-07-16 (AWR-276): the operator (a) authored 2 new
# static looks into SoundSwitchVenues.bin (its sha changed 6ec3.. -> dd7d..)
# and (b) had earlier edited SSAutoLoop16.ssfile and SSAutoLoop52.ssfile after
# the 2026-07-02 capture, so those two loops no longer render byte-exact
# against their committed capture evidence. On the healed path the
# recompute-from-fixtures pass witnesses that 16/52 diverged and RETIRES their
# stale evidence (reconcile_edited_witnesses), so both fall back to
# algorithm_generalized on their supported layout family. Result:
# 70 algorithm_generalized / 14 oracle_proven / 0 unverified -- publishable.
# Taken from the export tooling against the current venue, not hand-tuned.
#
# The fixtures-ABSENT fallback split is deliberately NOT pinned here -- it
# drifts with the operator's live, mutable SoundSwitch project. See
# ExportFallsBackWhenFixturesAreAbsentTests below.
EXPECTED_HEALED_LANES = {
    "algorithm_generalized": 70, "oracle_proven": 14, "unverified_parity": 0,
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
    back to the committed registry snapshot for that surface (status quo).

    Drift-proof regression guard. This test used to pin the fallback split to a
    hard-coded {68 algorithm_generalized / 14 oracle_proven / 2 unverified}
    (``EXPECTED_FALLBACK_LANES``), which only held while the operator's LIVE,
    mutable ``SoundSwitchVenues.bin`` sha equalled the committed snapshot's
    frozen ``venue_source_sha256``. That venue file drifts every time the
    operator edits their real SoundSwitch project:

        6ec3..  ->  dd7d..           ->  68ab..
                    (2026-07-16       (2026-07-19 23:02, +2 static looks;
                     snapshot baseline, current live venue -- makes every
                     ``EXPECTED_FALLBACK_LANES``   committed row's frozen dd7d..
                     + fixtures set)              sha miss the live gate)

    Since 2026-07-19 the live venue is ``68ab..`` while every committed snapshot
    row still carries ``dd7d..``, so the exporter's compile-time venue-sha gate
    (``soundswitch_pack.py``) honors NO row and every document fail-closes to
    ``unverified_parity`` -- correct, fail-closed-by-design behavior, but it
    broke the hard-coded pin. Root-cause diagnosis:
    ``local/spectral_v5_2026_07_17/PACKDIAG_report.md`` (verdict: machine-local
    data dependency the test wrongly assumed).

    The pin cannot be re-baselined durably: even the historical {68,14,2} is no
    longer reproducible even at venue-match, because per-loop ``.ssfile`` source
    shas have drifted independently of the venue (simulating venue-match today
    yields {68 / 8 / 8}, not {68,14,2}; see PACKFIX). So this test now asserts
    the STRUCTURAL fail-closed invariant instead of any fixed count, branching
    on the venue-sha reality it computes at runtime.
    """

    def _committed_snapshot_venue_sha(self) -> str:
        """The single frozen ``venue_source_sha256`` every committed-snapshot
        row carries (the exporter's compile-time gate compares each row against
        the CURRENT live venue sha)."""
        registries = export_module._load_parity_registries()
        shas: set[str] = set()
        for surface in ("scripted", "autoloop"):
            rows = registries.get(surface)
            if isinstance(rows, dict):
                for row in rows.values():
                    if isinstance(row, dict) and row.get("venue_source_sha256"):
                        shas.add(row["venue_source_sha256"])
        static = registries.get("static")
        if isinstance(static, dict) and static.get("venue_source_sha256"):
            shas.add(static["venue_source_sha256"])
        self.assertEqual(
            len(shas), 1,
            f"committed snapshot must carry exactly one venue sha, got {shas}",
        )
        return shas.pop()

    def test_absent_fixtures_fall_back_to_committed_snapshot(self) -> None:
        committed_registries = export_module._load_parity_registries()
        committed_venue_sha = self._committed_snapshot_venue_sha()
        # The live venue sha computed the SAME way the exporter's compile-time
        # gate computes it (``soundswitch_pack._source_sha``). Resolved as a
        # module attribute so the venue-match simulation (PACKFIX) can patch it.
        live_venue_sha = soundswitch_pack._source_sha(
            decode_project(SOURCE_PROJECT), "SoundSwitchVenues.bin"
        )

        real_compile = export_module.compile_pack_artifacts
        observed_registries: list[object] = []

        def spy_compile(*args, **kwargs):
            observed_registries.append(kwargs.get("parity_registry"))
            return real_compile(*args, **kwargs)

        missing_dir = Path("/nonexistent-parity-fixture-dir-for-self-heal-fallback-test")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "pack"
            with mock.patch.object(export_module, "SCRIPTED_FIXTURE",
                                   missing_dir / "scripted_reduced.json"), \
                 mock.patch.object(export_module, "AUTOLOOP_FIXTURE",
                                   missing_dir / "autoloop_reduced.json"), \
                 mock.patch.object(export_module, "STATIC_FIXTURE",
                                   missing_dir / "static_reduced.json"), \
                 mock.patch.object(export_module, "compile_pack_artifacts",
                                   side_effect=spy_compile):
                export_pack(SOURCE_PROJECT, dest)

            lanes = json.loads((dest / "manifest.json").read_text())["parity_lanes"]

        # Fallback-path proof (REAL in BOTH worlds): with every fixture absent
        # the export must NOT re-derive -- it must compile exactly ONCE, and the
        # committed snapshot is the registry LOADED AND HANDED to that compile.
        # The spy proves loaded-and-handed-once, not that the packer honored the
        # snapshot's rows (that is covered by test_soundswitch_scripted_parity
        # .py:233-243); "consumed" holds only in the match branch below. If the
        # fallback were broken (snapshot never loaded, or a spurious second
        # compile), these fail regardless of lanes.
        self.assertEqual(len(observed_registries), 1)
        self.assertEqual(observed_registries[0], committed_registries)

        total = sum(lanes.values())
        self.assertGreater(total, 0, "export staged zero classified documents")

        if live_venue_sha != committed_venue_sha:
            # Mismatch world (the operator's current reality): the committed
            # snapshot's frozen venue sha no longer matches the live venue and
            # there are no capture fixtures to re-verify against, so EVERY
            # document fail-closes to unverified_parity. Count derived from the
            # staged pack, never a hard-coded total.
            self.assertEqual(
                lanes,
                {"algorithm_generalized": 0, "oracle_proven": 0,
                 "unverified_parity": total},
            )
        else:
            # Match world: the snapshot's venue sha equals the live venue, so
            # its rows are honored and the fallback is NOT fully fail-closed --
            # trusted lanes are populated. Exact counts intentionally NOT pinned
            # (they drift with per-loop source edits), so assert the structural
            # invariant: the snapshot was actually consumed and trusted some
            # documents.
            self.assertLess(lanes["unverified_parity"], total)
            self.assertGreater(
                lanes["algorithm_generalized"] + lanes["oracle_proven"], 0
            )


if __name__ == "__main__":
    unittest.main()
