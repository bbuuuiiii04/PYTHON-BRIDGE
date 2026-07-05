# Tests must never write the live operator's Stream Deck feedback file
# (/tmp/rb_ss_bridge_v2_palette_state.json). A real bridge process running
# on this machine heartbeats that file every 5s; any StateManager built by
# the test suite spins up its own PaletteFeedbackWriter thread and, without
# this override, would fight the live bridge over the same path for the
# whole suite run -- the operator's Stream Deck visibly blinks (seq
# regressions, latch clears, palette keys blanking) while tests are running.
#
# Set the override here, before any bridge module is imported, so
# led_palette_control.PALETTE_STATE_PATH and streamdeck_midi.PALETTE_STATE_PATH
# both read the env var at import time and pick up the redirected path. The
# pid suffix keeps concurrent suite runs (this repo has multiple agents
# testing at once) from fighting each other over one shared temp file.
# setdefault() so an explicitly exported RBSS_PALETTE_STATE_PATH still wins.
import os
import tempfile

os.environ.setdefault(
    "RBSS_PALETTE_STATE_PATH",
    os.path.join(tempfile.gettempdir(), f"rbss_test_palette_state_{os.getpid()}.json"),
)
