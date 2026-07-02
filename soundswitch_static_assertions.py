"""Static Look non-generic map assertions for the bounded CH1-CH19 profile."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

PRIMARY_FIXTURE_GROUP = 0x493


@dataclass(frozen=True, slots=True)
class StaticNonGenericAssertion:
    passed: bool
    checked_fixture_group: int
    profile_channel_types: dict[str, str]
    violations: tuple[str, ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "checked_fixture_group": self.checked_fixture_group,
            "passed": self.passed,
            "profile_channel_types": dict(sorted(self.profile_channel_types.items())),
            "violations": list(self.violations),
        }


def _field(row: object, name: str) -> Any:
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name)


def _channel_type(name: str) -> str:
    lowered = name.strip().lower()
    if "intensity" in lowered or "dimmer" in lowered:
        return "intensity"
    if "strobe" in lowered:
        return "strobe"
    if "color" in lowered or "colour" in lowered or "gradient" in lowered:
        return "colour"
    if any(token in lowered for token in ("pan", "tilt", "horizontal", "vertical")):
        return "position"
    return "generic"


def profile_channel_types(channels: Iterable[object]) -> dict[int, str]:
    return {
        int(_field(row, "dmx_channel")): _channel_type(str(_field(row, "name")))
        for row in channels
    }


def assert_static_non_generic_safe(
    look: object,
    channels: Iterable[object],
    *,
    primary_fixture_group: int = PRIMARY_FIXTURE_GROUP,
) -> StaticNonGenericAssertion:
    """Prove retained static maps do not add CH1-CH19 output outside generic attrs."""
    channel_types = profile_channel_types(channels)
    generic_channels = {
        int(_field(row, "dmx_channel"))
        for row in _field(look, "generic_attributes")
        if int(_field(row, "fixture_group")) == primary_fixture_group
    }
    violations: list[str] = []

    typed_channels: dict[str, list[int]] = {}
    for channel, kind in channel_types.items():
        typed_channels.setdefault(kind, []).append(channel)

    if typed_channels.get("intensity"):
        for row in _field(look, "intensity_values"):
            if int(_field(row, "fixture_instance_id")) != primary_fixture_group:
                continue
            if float(_field(row, "value")) != 0.0 \
                    and not set(typed_channels["intensity"]).issubset(generic_channels):
                violations.append("intensity_map_targets_primary_without_generic_equivalent")
                break

    if typed_channels.get("strobe"):
        for row in _field(look, "strobe_values"):
            if int(_field(row, "fixture_instance_id")) != primary_fixture_group:
                continue
            if float(_field(row, "value")) != 0.0 \
                    and not set(typed_channels["strobe"]).issubset(generic_channels):
                violations.append("strobe_map_targets_primary_without_generic_equivalent")
                break

    if typed_channels.get("colour"):
        for row in _field(look, "colour_values"):
            if int(_field(row, "fixture_instance_id")) != primary_fixture_group:
                continue
            raw_value = _field(row, "raw_value")
            if raw_value and not set(typed_channels["colour"]).issubset(generic_channels):
                violations.append("colour_map_targets_primary_without_generic_equivalent")
                break

    if typed_channels.get("position"):
        for row in _field(look, "position_values"):
            if int(_field(row, "fixture_instance_id")) != primary_fixture_group:
                continue
            guid = str(_field(row, "position_guid"))
            if guid and set(guid) != {"0"} \
                    and not set(typed_channels["position"]).issubset(generic_channels):
                violations.append("position_map_targets_primary_without_generic_equivalent")
                break

    return StaticNonGenericAssertion(
        passed=not violations,
        checked_fixture_group=primary_fixture_group,
        profile_channel_types={str(channel): kind for channel, kind in channel_types.items()},
        violations=tuple(sorted(violations)),
    )


__all__ = [
    "PRIMARY_FIXTURE_GROUP",
    "StaticNonGenericAssertion",
    "assert_static_non_generic_safe",
    "profile_channel_types",
]
