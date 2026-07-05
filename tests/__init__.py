# Tests must never write the live operator's Stream Deck feedback file
# (/tmp/rb_ss_bridge_v2_palette_state.json). A real bridge process running
# on this machine heartbeats that file every 5s; any StateManager built by
# the test suite spins up its own PaletteFeedbackWriter thread and, without
# this override, would fight the live bridge over the same path for the
# whole suite run -- the operator's Stream Deck visibly blinks (seq
# regressions, latch clears, palette keys blanking) while tests are running.
#
# The PRIMARY protection is now structural: led_palette_control.py resolves
# its feedback path at construction time (LedPaletteControl.__init__ /
# PaletteFeedbackWriter.__init__), defaulting to a per-pid throwaway file
# unless RBSS_PALETTE_STATE_PATH is set -- only __main__.main() (the real
# bridge, after it wins the single-instance lock) ever pins the live path.
# That means an ad-hoc script that never imports this tests/ package (the
# gap this override alone used to leave open) is ALSO safe by construction.
#
# This block is belt-and-suspenders for anything running under the test
# suite: it sets the override here, before any bridge module is imported,
# so a suite run gets a stable shared throwaway path for its whole
# duration instead of a fresh one per StateManager construction. The pid
# suffix keeps concurrent suite runs (this repo has multiple agents
# testing at once) from fighting each other over one shared temp file.
# setdefault() so an explicitly exported RBSS_PALETTE_STATE_PATH still wins.
import os
import tempfile

os.environ.setdefault(
    "RBSS_PALETTE_STATE_PATH",
    os.path.join(tempfile.gettempdir(), f"rbss_test_palette_state_{os.getpid()}.json"),
)
