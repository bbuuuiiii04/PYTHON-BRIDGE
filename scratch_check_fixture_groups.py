import sys
import logging
from soundswitch_pack_loader import load_pack
from soundswitch_pack_models import LoadedScriptedTrack

def main():
    logging.basicConfig(level=logging.INFO)
    pack_path = "/Users/bbui/rb_ss_bridge_v2/local/soundswitch/rbss_canonical_pack"
    pack = load_pack(pack_path)
    found_groups = set()
    for track in pack.scripted.values():
        if getattr(track, "document", None):
            for ev in track.document.events:
                if ev.reference_kind == "cue":
                    for attr in ev.patch:
                        found_groups.add(attr.fixture_group)
    print("Fixture groups found in pack:", [hex(g) for g in found_groups])

if __name__ == "__main__":
    main()
