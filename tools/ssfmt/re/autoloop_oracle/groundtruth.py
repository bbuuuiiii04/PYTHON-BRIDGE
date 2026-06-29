"""Passive Art-Net capture ground truth for the offline Autoloop oracle."""
from __future__ import annotations

from pathlib import Path

from tools.ssfmt.re.parse_artnet_pcap import universe_frames

DMX_CH = 19
DMX_CHANNEL_BASE = 0


def load_groundtruth(pcap_path: str | Path) -> list[tuple[float, tuple[int, ...]]]:
    frames = universe_frames(Path(pcap_path), universe=0, channels=DMX_CH)
    if not frames:
        raise ValueError("no ArtDmx universe-0 frames found")
    for _timestamp, frame in frames:
        if len(frame) != DMX_CH:
            raise ValueError(f"expected {DMX_CH} DMX channels, got {len(frame)}")
    return frames
