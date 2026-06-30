---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 74febec
last_verified_date: 2026-06-29
validation_scope: software-validated only plus Rekordbox 7.2.11 passive mixer RE evidence routing; hardware-unvalidated in repo evidence
---


# Support Matrix

This matrix is deliberately conservative. If evidence is missing, the answer is `unknown`, not “probably works.” Computers punish “probably.”

## Rekordbox versions

| Version | Status | Evidence | Notes |
| --- | --- | --- | --- |
| My current local version | local-setup-operational | operator-local knowledge, not yet captured as repo validation | Exact version must be recorded. |
| Rekordbox 7.2.11 | code-referenced; local mixer RE-proven for Deck 1/2 upfader and LOW/BASS chains; mixer active-deck authority software-tested | `rb_memory.py` comments reference `get-task-allow` confirmation; `docs/research/rekordbox_mixer_active_deck_re_evidence.md` records static plus passive process-memory proof; unit/integration tests cover the resolver/reader/status paths, including direct-master refresh/invalidation and raw Deck C/D no-aliasing | This is not broad 7.x support, and it is not live or hardware validation. Named mixer offsets are accepted only when all required labels are present; unknown/anonymous lines fail closed for authority. |
| Other Rekordbox 7.x | unknown | no matrix evidence | Offset validation required. |
| Rekordbox 6.x | unknown | app path fallback exists, but support is not proven | Do not claim support. |
| Future versions | unknown/unsupported until validated | none | Offsets may break. |

## Operating systems

| OS | Status | Evidence | Notes |
| --- | --- | --- | --- |
| macOS local setup | local-setup-operational | current project architecture and local use | Exact macOS version matrix needed. |
| Other macOS versions | unknown | no compatibility matrix evidence | Must be tested. |
| Windows | unsupported/unknown | current memory reader is macOS Mach-based | Would require separate reader strategy. |
| Linux | unsupported/unknown | current memory reader is macOS Mach-based | Not current scope. |

## Lighting outputs

The SoundSwitch project/pack tooling is not a live lighting-output claim. For
the pinned SoundSwitch 2.10.3 canonical UUID/RAVE profile, strict decode,
deterministic new-path export, independent verification, immutable pack
loading/rendering, MIDI-input routing, backend abstraction, config/startup,
StateManager scripted driving, copied operational status, commands, Enttec framing/sending, and
tick-throttled ordinary loop-error handling have software tests. Live export reconciles saved-project inventory dynamically; the
old exact-count closure snapshot is proof-only.
Direct-DMX code exists but is default-off, locally unconfigured, and
hardware-unvalidated. The Art-Net truth-check gate is also default-off and
validation-only: it emits bridge shadow-render U1 packets plus a sidecar for
comparison against SoundSwitch U0, opens no Enttec/serial, and does not make the
bridge a physical lighting authority. Copied status proves software intent only;
sender health, native-Autoloop live/runtime evidence, final U0/U1 capture
evidence, and physical validation remain open.

| Output | Status | Evidence | Notes |
| --- | --- | --- | --- |
| SoundSwitch OS2L | implemented | code path exists | Exact SoundSwitch version support unknown. |
| SoundSwitch scripted pack/direct DMX | partial, default-off | dynamic export/verifier tests plus player/startup/driver/sender/status/truth-check tests | Active existing-path scripts export when decoded and reconciled from the saved project; SoundSwitch-saved Static Override Press/Toggle interaction mode is honored; static-controller input auto-binds unless an alias overrides it, and missing/ambiguous input degrades manual Static Looks without disabling pack DMX; canonical pack lives at repo-local ignored `local/soundswitch/rbss_canonical_pack`; copied RW-5 status and Art-Net U1 truth-check are software/wire evidence only, sender health is not reported, and physical validation remains. |
| SoundSwitch native-DMX Autoloops | implemented, default-off | resolver/player/loader/StateManager software tests plus historical T7d tooling/captures | Uses canonical pack note-to-Autoloop bindings, bridge-owned 32-beat phase at 600 ticks/beat, and `phase_offset_beats`. Live/runtime and hardware evidence are pending; old T7d SoundSwitch-hidden-phase proof is historical and no longer blocks native output. |
| Laser MIDI | implemented | code path plus lifecycle unit/integration tests | Default-on gated drop/post-drop cycling, shuffle-bag selection, static-impact fallback, and kill-switch-OFF legacy behavior are software-tested. Broad fixture/safety validation is not documented. |
| LED/Govee cloud scene | implemented | code path exists | Scripted groove/drop/post-drop blackout mapping is software-tested and the shipped example config now enables the master switch (`true`) with the conservative blackout policy; device support and room-visible behavior are not generalized. |
| LED/Govee realtime | implemented/experimental | code path exists | Slot-color strategy behavior, Patch S `random_with_mono_chance`, generic M2.5 groove/post_drop/drop/Patch E1 nebula/Patch E2 center-comet/Patch E3 twinkle cues, and Patch F default-bank cleanup are software-tested only; current H612D setup must be validated through hardware log before broad claims. |

## Hardware validation state

| Scope | Status |
| --- | --- |
| My current local rig | locally operational, but repo validation record incomplete |
| Repeatable hardware validation in repo | procedure/template present; no completed run evidence |
| Broad hardware compatibility | not claimed |
| Show-ready claim | not allowed |
| Production-ready claim | not allowed |
