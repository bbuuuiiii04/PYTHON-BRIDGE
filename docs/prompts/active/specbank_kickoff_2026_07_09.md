---
doc_status: current
truth_level: handoff-report
last_verified_commit: d106492
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff for the SPECBANK lane (Fable/HIGH, tmux specbank, final Fable afternoon
  2026-07-09): author three Codex-ready artifacts — P1 growl-band-centroid spec,
  white-share LED-consumer spec, drop-echo theme-and-variation design note. Paper
  only; no implementation, no runtime contact.
---

# Specbank — kickoff (2026-07-09, paper only)

You are the **specbank lane** (Fable/HIGH). Mission: three implementation-ready
artifacts banked before Fable access ends tonight. The ledtune session conceptually
owns two of these (its Tracks B/C) but is live-tuning with the operator right now —
you AUTHOR, the executive gates, ledtune gets post-mix review visibility. Do not
message ledtune during the mix.

## Artifact 1 — P1 growl-band centroid spec (the audit's #1 recommendation)
Source: `docs/research/spectral_upgrade_audit_2026_07_09.md` (P1 section + §298
reasoning). Spec: the additive extraction field (spectral centroid of the harmonic
60–500 Hz band per STFT frame, alongside `growl_band_frames` in
`audio_spectral_features.py`), cache schema addition (additive, never breaking:
verify `spectral_cache.py` versioning), the one-time overnight re-sweep plan
(`tools/spectral_sweep.py` pattern; NEVER against a mix; disk floor), and the F4
consumer seam sketch (wobble-following seasoning — seam only, consumer is a later
round). Zero change to existing calibration constants. Part A–E format
(.claude/skills/codex-spec/SKILL.md read as a doc).

## Artifact 2 — white-share LED consumer spec
Ground truth (verified today, re-verify at HEAD): `white_share` computed per drop in
`lighting_moments_v2.build_track_plan`, ZERO consumers in led_dispatch_policy /
led_color_engine / led_look_director / govee_frame_renderer. Spec the first consumer:
per-drop white fraction riding the drop look (big builds flash whiter), kill-switched
config (example-OFF, absent-OFF, byte-identical when off — the F2/F4 containment
pattern), push-loop-safe (plan lookup only), mask precedence untouched, tests pinning
on/off byte-identity + the mapping. Part A–E.

## Artifact 3 — drop-echo theme-and-variation design note
The one surviving creative proposal (operator: "small round after F2/F4 live-tuning"
— live-tuning is happening TODAY, so the build gets queued behind its outcomes).
Design note (not a full spec): what it is in plain words, the mechanism sketch over
the F2 plan surface, config shape, open taste calls as a named veto list.

## Rules
- Contract-first: name the change_contracts.yml contract each artifact extends
  (spectral_analysis / led_govee); extend contracts IN THE SPEC as a listed task,
  don't edit them yourself for paper-only work.
- Every cite verified at HEAD (the tree moved all day). Registry rows: next AWR ids,
  re-check max immediately before writing.
- Sub-lanes (Opus/Sonnet) allowed for verification grinding. Escalations →
  superman3. Completion: signal file + sentinel per dispatch convention.
