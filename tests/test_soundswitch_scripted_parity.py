"""Focused tests for computed SoundSwitch parity lanes."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.soundswitch_pack import compile_pack_artifacts
from rb_ss_bridge_v2.soundswitch_pack_loader import LoadedPack
from rb_ss_bridge_v2.soundswitch_pack_models import (
    DecodedSoundSwitchProject,
    LightingDocument,
    ProjectIdentity,
    ScriptedTrackClassification,
    SourceFile,
    TimelineRecord,
    TrackMapRecord,
)
from rb_ss_bridge_v2.soundswitch_pack_runtime import PackRuntime
from rb_ss_bridge_v2.soundswitch_parity_registry import (
    classify_parity_lane,
    count_lanes,
    generalized_witness_passed,
    parity_evidence,
)
from rb_ss_bridge_v2.soundswitch_project_decoder import (
    CANONICAL_CONTAINER_VERSION,
    CANONICAL_PROJECT_UUID,
    CANONICAL_SOUNDSWITCH_VERSION,
    CANONICAL_VENUE_GUID,
)


SCRIPT_ID = "11111111-1111-4111-8111-111111111111"
WITNESS_ID = "22222222-2222-4222-8222-222222222222"
SOURCE_SHA = "a" * 64
WITNESS_SHA = "b" * 64
VENUE_SHA = "c" * 64
LAYOUT = "shared_441_dictionary_timeline"


def _path(identity: str) -> str:
    return f"{{{identity.upper()}}}.ssfile"


def _identity(path: str) -> str:
    return path.removeprefix("{").removesuffix("}.ssfile").lower()


def _document(
    identity: str = SCRIPT_ID,
    *,
    source_sha: str = SOURCE_SHA,
    layout: str = LAYOUT,
    timeline: tuple[TimelineRecord, ...] = (),
) -> LightingDocument:
    return LightingDocument(
        _path(identity),
        source_sha,
        1,
        CANONICAL_CONTAINER_VERSION,
        CANONICAL_VENUE_GUID,
        layout,
        0,
        (),
        timeline,
        (),
        1,
        b"",
        "0" * 64,
        None,
    )


def _registry_entry(
    *,
    source_sha: str = SOURCE_SHA,
    venue_sha: str = VENUE_SHA,
    layout: str = LAYOUT,
    verdict: str = "PASS",
    truth_source: str = "SoundSwitch U0",
) -> dict[str, object]:
    return {
        "capture_id": "parity_20260701T185231Z",
        "divergence": [],
        "layout": layout,
        "oracle_report_sha256": "d" * 64,
        "rows_passed": 2,
        "rows_total": 2,
        "source_sha256": source_sha,
        "truth_source": truth_source,
        "venue_source_sha256": venue_sha,
        "verdict": verdict,
    }


def _project(
    documents: tuple[LightingDocument, ...],
    *,
    active_identities: set[str] | None = None,
    venue_sha: str = VENUE_SHA,
) -> DecodedSoundSwitchProject:
    active_identities = active_identities if active_identities is not None else {SCRIPT_ID}
    source_inventory = (
        SourceFile("SoundSwitchVenues.bin", 1, venue_sha, 0, 0),
        *(
            SourceFile(document.relative_path, document.source_size, document.source_sha256, 0, 0)
            for document in documents
        ),
    )
    classifications = tuple(
        ScriptedTrackClassification(
            soundswitch_id=_identity(document.relative_path),
            relative_path=document.relative_path,
            fixture_profile_guid=CANONICAL_VENUE_GUID,
            track_map_mapping_count=1,
            status="supported_mapped_primary",
        )
        for document in documents
    )
    track_map = tuple(
        TrackMapRecord(
            source_offset=index,
            soundswitch_id=identity,
            title="Synthetic",
            artist="Test",
            filepath=__file__,
        )
        for index, identity in enumerate(sorted(active_identities))
    )
    return DecodedSoundSwitchProject(
        identity=ProjectIdentity(
            CANONICAL_PROJECT_UUID,
            CANONICAL_SOUNDSWITCH_VERSION,
            CANONICAL_CONTAINER_VERSION,
            CANONICAL_VENUE_GUID,
            "Synthetic Venue",
        ),
        source_inventory=source_inventory,
        fixture_channels=(),
        attribute_cues=(),
        static_looks=(),
        autoloop_catalogs=(),
        autoloops=(),
        scripted_tracks=documents,
        scripted_track_classifications=classifications,
        track_map=track_map,
        learned_midi_maps=(),
        resolved_controls=(),
        no_target_policy_inputs=(),
        diagnostics=(),
    )


def _compile_script(
    document: LightingDocument,
    registry: dict[str, object],
    *,
    extra_documents: tuple[LightingDocument, ...] = (),
) -> tuple[dict[str, object], dict[str, object]]:
    artifacts = compile_pack_artifacts(
        _project((document, *extra_documents)),
        generator_commit="0" * 40,
        parity_registry={"scripted": registry},
    )
    identity = _identity(document.relative_path)
    scripted = json.loads(artifacts[f"scripted/{identity}.json"])["document"]
    manifest = json.loads(artifacts["manifest.json"])
    return scripted, manifest


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

    def test_generalized_witness_requires_u0_pass_and_resolved_document(self) -> None:
        registry = {WITNESS_ID: _registry_entry(source_sha=WITNESS_SHA)}
        self.assertTrue(generalized_witness_passed(registry, LAYOUT, True))
        self.assertFalse(generalized_witness_passed(registry, "other_layout", True))
        self.assertFalse(generalized_witness_passed(registry, LAYOUT, False))
        self.assertFalse(
            generalized_witness_passed(
                {WITNESS_ID: _registry_entry(source_sha=WITNESS_SHA, verdict="FAIL")},
                LAYOUT,
                True,
            )
        )
        self.assertFalse(
            generalized_witness_passed(
                {WITNESS_ID: _registry_entry(source_sha=WITNESS_SHA, truth_source="pack self-render")},
                LAYOUT,
                True,
            )
        )

    def test_compiler_promotes_scripted_registry_hit_to_oracle_proven(self) -> None:
        document, manifest = _compile_script(
            _document(),
            {SCRIPT_ID: _registry_entry()},
        )

        self.assertEqual(document["parity_lane"], "oracle_proven")
        self.assertEqual(document["parity_evidence"]["truth_source"], "SoundSwitch U0")
        self.assertEqual(document["parity_evidence"]["capture_id"], "parity_20260701T185231Z")
        self.assertEqual(document["parity_evidence"]["oracle_report_sha256"], "d" * 64)
        self.assertEqual(manifest["parity_lanes"]["oracle_proven"], 1)

    def test_compiler_fails_closed_on_stale_scripted_registry_hashes(self) -> None:
        stale_source, _ = _compile_script(
            _document(),
            {SCRIPT_ID: _registry_entry(source_sha="e" * 64)},
        )
        stale_venue, _ = _compile_script(
            _document(),
            {SCRIPT_ID: _registry_entry(venue_sha="f" * 64)},
        )

        self.assertEqual(stale_source["parity_lane"], "unverified_parity")
        self.assertEqual(stale_venue["parity_lane"], "unverified_parity")

    def test_compiler_generalizes_same_layout_from_current_witness(self) -> None:
        witness = _document(WITNESS_ID, source_sha=WITNESS_SHA)
        document, _ = _compile_script(
            _document(),
            {WITNESS_ID: _registry_entry(source_sha=WITNESS_SHA)},
            extra_documents=(witness,),
        )

        self.assertEqual(document["parity_lane"], "algorithm_generalized")
        self.assertEqual(document["parity_evidence"]["reason"], f"generalized_from_{LAYOUT}")

    def test_compiler_does_not_generalize_unresolved_scripted_reference(self) -> None:
        witness = _document(WITNESS_ID, source_sha=WITNESS_SHA)
        unresolved = _document(
            timeline=(
                TimelineRecord(
                    source_offset=10,
                    record_version=1,
                    time=0,
                    raw_reference=1,
                    reference_kind="cue",
                    resolved_stored_key=0,
                    resolved_cue_guid=None,
                ),
            )
        )
        document, _ = _compile_script(
            unresolved,
            {WITNESS_ID: _registry_entry(source_sha=WITNESS_SHA)},
            extra_documents=(witness,),
        )

        self.assertEqual(document["parity_lane"], "unverified_parity")

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

    def test_runtime_status_exposes_static_binding_gap(self) -> None:
        pack = LoadedPack(
            schema_version="1.0.0",
            manifest_sha256="0" * 64,
            has_intensity_channel=False,
            scripted=MappingProxyType({}),
            autoloops=MappingProxyType({}),
            static_looks=MappingProxyType({}),
        )
        midi_input = SimpleNamespace(status=lambda: {
            "static_binding_gap": True,
            "static_binding_gap_count": 1,
        })
        runtime = PackRuntime(player=SimpleNamespace(pack=pack), midi_input=midi_input)
        status = runtime.sanitized_status()
        self.assertTrue(status["static_binding_gap"])
        self.assertEqual(status["static_binding_gap_count"], 1)


if __name__ == "__main__":
    unittest.main()
