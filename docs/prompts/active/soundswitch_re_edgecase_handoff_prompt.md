---
doc_status: active-adversarial-handoff-prompt
truth_level: code-grounded
last_verified_commit: b0e5e47
last_verified_date: 2026-06-26
validation_scope: handoff for the next agent continuing the SoundSwitch RE-pipeline edge-case hunt.
  Read-only on ~/Music; scratchpad copies only; no bridge restart / hardware / commits beyond docs.
---

# Handoff — continue the SoundSwitch RE edge-case hunt

You are continuing an adversarial edge-case sweep of the SoundSwitch RE → pack → runtime → live-DMX
pipeline. The original brief is `docs/prompts/active/soundswitch_re_edgecase_breaker_prompt.md`.
**Read that, then read `docs/plans/active/soundswitch_re_edgecase_findings.md` (the findings register)
and `docs/plans/active/soundswitch_re_edgecase_hardening_spec.md` (the fix spec) before doing
anything.** Do not re-derive what's already there.

## The single most important thing — ground every claim in what is ACTUALLY live
The prior run's biggest mistake: calling pack-runtime code paths "live-safety-critical" when **the
SoundSwitch pack is not the operator's live light path.** Verified:
- There is **no `config/soundswitch_pack_player.json`** → the pack loader returns `not_configured` →
  `__main__` keeps the **legacy** path (SoundSwitch app via OS2L + the laser director). The pack does
  not drive DMX today.
- Even enabled, the pack opens **only DDJ-800** as a MIDI input; the IAC blackout binding is on a
  device it never reads, so the pack player's blackout cannot fire.
- The operator **never uses emergency blackout**, and their smart-drop / transition-mask / breakdown
  behavior is in the **legacy** path, which the prior run did NOT analyze.

**Rules for you:** (1) Before tagging anything "live" or "S1", prove the code path is reachable in the
operator's real configuration and that they actually use the feature — check `config/*.json`, the env
flags in CLAUDE.md, and ask if unsure. (2) This is a **solo hobby rig for the operator + friends, not
a product** — dial back safety theater; a gap in a control the operator never uses is not a finding.
(3) Label every claim confirmed / assumed / unknown and back confirmed ones with a runnable repro.
(4) Verify every prior claim against current code; do not trust this doc blindly.

## What actually matters now vs later
- **Bites now (the pack is being built/exported under PR #116, so export bugs hit the dev loop even
  though the pack isn't live):** F3 + F5 (`verify_pack`=True but `load_pack` rejects → a "successful"
  export silently won't load), F4 (`decode_catalog` leaks `struct.error` on a truncated catalog),
  F2's export non-determinism. These are real today. The fix spec covers them — consider verifying/
  extending it rather than re-finding them.
- **Pre-go-live (only when `output_backend=pack` + real Enttec port):** F1/F1b (reserved-event
  blackout collision), F12 (held-blackout stale-expiry), F2's dark-tracks impact. Real code, not live.

## Where the prior run already swept (don't repeat)
Full pack pipeline (decoder / compile / verify / loader / runtime / controller / frame_sender /
backend / config), player layering + reload + degradation latch, export atomicity, RE-toolkit
crash-fuzz (7 importable parsers — all clean) + production-vs-RE divergence (only the DDJ mislabel),
freeze/compare drift, multi-venue cue handling, autoloop catalog resolution. All fail-closed except
the findings in the register. **F9 (overlay bleed-through) and F10 (static-loses-to-stale) were
investigated and RULED OUT** (intended/defended) — do not resurrect them.

## Highest-value places NOT yet swept (go here)
1. **The legacy LIVE path** — `sound_switch_engine.py`, `osl_output.py`, `os2l_injector.py`,
   `smart_phrasing.py`, `smart_drop`/`smart_rearm`, and how the operator's actual blackout / "transition
   mask" / smart-drop behavior is produced and timed. This is what's *actually driving the lights*.
   (Note: this is broader than the original RE-pack prompt — confirm with the operator whether to
   expand scope here, since this is where their real live behavior lives.)
2. **Structural (length/offset-consistent) corruption fuzz of `SoundSwitchVenues.bin`** — the prior
   run only did truncation. Hunt for a *silent mis-parse* (decode succeeds, output semantically wrong,
   still verifies) — the format entangles values with length/offset fields, so this is where a silent
   wrong-frame could hide.
3. **`enttec_dmx_pro.py` wire framing** (`build_dmx_packet`, the worker) — the last stage before the
   lights; hardware-adjacent but the packet framing/escaping is pure software.
4. **Capture-replay RE tools** (`validate_*_capture`, `parse_artnet_pcap`, `align_capture`,
   `audit_legacy_capture`, `correlate_midi_autoloop`, `uuidxref`, `t7d_phase_contract`) — only run if
   the captures exist; low live-stakes.

## Infrastructure you can reuse
- Scratchpad harness + repros: `/private/tmp/.../scratchpad/work/` (`harness.py` decodes the live
  project read-only and gives `compile_and_verify` + `dataclasses.replace` mutation helpers;
  `repro_1..7`, `fuzz_decode.py`, `re_sweep.py`). Re-create equivalents if the scratchpad is gone.
- Run the package from `/Users/bbui` as `rb_ss_bridge_v2...`; run the proof gate and
  `unittest discover tests` from inside the repo.
- Green baseline to protect: proof **29/0/0**, SS unit suite **262 OK**, oracle export **verified/95**.

## Constraints (unchanged)
READ-ONLY on `~/Music/SoundSwitch/default.ssproj` (copytree to scratchpad for mutation). No bridge
restart, no MIDI/DMX/Enttec/hardware, no commits beyond docs. Loop until two consecutive dry rounds,
then update the register and hand off again.
