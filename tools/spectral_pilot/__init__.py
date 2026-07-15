# Phase-0 offline spectral-AI falsification pilot package (spec
# docs/plans/active/spectral_ai_phase0_protocol_spec_2026_07_14.md, Part B).
#
# OFFLINE ONLY. No repo-root runtime module may import this package; the AST guard
# in tests/test_spectral_pilot_guards.py enforces that direction. This package may
# read-only-call the F2 / spectral_profile / spectral_cache / hardness_v0 /
# approach_features_v0 surfaces named in spec B4, and nothing else in the runtime.
#
# Empty on purpose: importing the package has no side effects.
