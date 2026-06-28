---
doc_status: current
truth_level: code-and-config-grounded
last_verified_commit: 27a078b
last_verified_date: 2026-06-28
validation_scope: software-validated only plus Rekordbox 7.2.11 passive mixer RE evidence routing; hardware-unvalidated in repo evidence
---


# Feature Status Matrix

Status vocabulary:

- `implemented`: runtime path exists in code.
- `software-tested`: tests exist or deterministic validation exists.
- `local-setup-operational`: I have it working locally, but repo hardware evidence is incomplete.
- `hardware-unvalidated`: no repeatable hardware-validation record in this repo.
- `experimental`: implemented or prototyped, but behavior may change.
- `partial`: some pieces exist, but important gaps remain.
- `planned`: not implemented yet.
- `unknown`: not enough evidence.
- `unsupported`: out of current scope.
- `stale/superseded`: old docs or plans no longer match code.

| Feature area | Implementation status | Validation status | Compatibility scope | Notes |
| --- | --- | --- | --- | --- |
| Core startup | implemented | software-tested indirectly | local setup | `__main__.py` wires the runtime components. |
| StateManager event/push loop | implemented | software-tested partially | local setup | Central owner for deck/runtime/lighting state. Ordinary loop exceptions are covered for tick-throttled skip/continue, bounded logging, process-control exception escape, and no duplicate pack ZERO after `_push_tick()` inner failures. |
| Runtime `[BEAT]` heartbeat | implemented | software-tested partially | local setup | `StatusWriter` emits a throttled status-only heartbeat and writes the same summary into status JSON. Hardware-visible output is unchanged and unvalidated. |
| Logging visibility live watch | implemented | software-tested partially | local setup | `docs/setup/logging_live_watch.json` provides a curated control-file preset for `[BEAT]`, laser, LED/Govee, SoundSwitch, and master/deck logs using existing `LoggingManager` filters. It changes logging visibility only and remains hardware-unvalidated. |
| SoundSwitch OS2L output | implemented | software-tested partially | local setup | Uses OS2L TCP and VirtualDJ-shaped messages. |
| SoundSwitch offline decoder/exporter/pack/verifier | implemented | software-tested | pinned SoundSwitch 2.10.3 canonical UUID/RAVE profile only | Strict read-only full rescan, deterministic repo-local canonical export, independent verification, dynamic saved-project inventory reconciliation, required binding-sidecar stage-before-swap publication, and one-click canonical replacement/reload. The old exact-count snapshot is retained only as an explicit proof gate; live export accepts internally consistent saved edits. |
| SoundSwitch scripted pack player/runtime/direct-DMX lane | partial | substantial software/wire tests; live runtime/hardware unvalidated | pinned pack/local setup only | Loader/player, MIDI adapter, backend abstraction, Enttec sender, default-off config, startup, StateManager driver, commands, and copied RW-5 operational status exist. The MIDI adapter honors the SoundSwitch-saved Static Override Press/Toggle interaction mode (decoded byte; unknown fails closed to momentary) and auto-binds static-controller input unless an alias overrides it; missing/ambiguous controller input degrades manual Static Looks without disabling pack DMX. All 32 active scripted tracks export/render. The canonical pack lives at the repo-local ignored `local/soundswitch/rbss_canonical_pack`. Status preserves degraded-input plus scripted-active truth, but software zero/attempted frames do not prove sender or fixture state; local pack hardware remains unvalidated. |
| SoundSwitch native-DMX Autoloops | planned/blocked | pure renderer and capture tooling software-tested; 4 live wire captures pass conductor integrity only | pinned pack only | `select_autoloop` exists but StateManager never calls it. T7d arm/refire have two accepted captures each, but four scenario pairs and the unique oracle remain; ticks/beat, quantizer, and six active transition-origin rules are unknown. Automatic Autoloop base stays zero-safe. |
| Rekordbox memory position reader | implemented | software-tested partially | macOS local setup | macOS Mach APIs. Other OSes unsupported/unknown. |
| Rekordbox direct state reader | implemented | software-tested partially | current local Rekordbox only | Offset/version assumptions require validation per version. |
| Rekordbox mixer active-deck authority | planned | static RE plus passive live process-memory proof for Deck 1/2 upfader and LOW/BASS EQ; runtime unimplemented; hardware unvalidated | current local Rekordbox 7.2.11 target only | Operator-authoritative target behavior is documented in `docs/architecture/active_deck_authority.md`; the implementation handoff lives in `docs/plans/active/rekordbox_mixer_active_deck_re_spec.md`; proof lives in `docs/research/rekordbox_mixer_active_deck_re_evidence.md`. Ghidra headless static evidence plus operator-approved passive sampling confirms local Deck 1/2 upfader chains, LOW/BASS chains, Deck 1/2 channel ownership, and EQ band 2 = LOW/BASS. Filter, version/relaunch stability, play/stop/master-change survival, runtime validity/freshness, resolver thresholds, and status/heartbeat integration remain unimplemented or unproven. Current code still uses Rekordbox master/playing-only auto-switch as active-deck authority. |
| Live BPM | implemented | software-tested partially | current local Rekordbox only | Direct offset-table path plus discovery fallback. |
| MTC fallback | implemented | software-tested unknown | local setup | Fallback path, not primary compatibility proof. |
| Smart phrasing/drop/breakdown | implemented | software-tested partially | local setup | Must remain StateManager-owned at runtime. |
| Laser Director policy | implemented | software-tested partially | local setup | The default-on gated drop/post-drop lifecycle is software-tested and mirrors the LED flat-window role gate, with configurable impact/cap values and a default-true runtime kill switch. Execution remains separate. |
| Laser MIDI executor | implemented | software-tested partially | hardware-unvalidated in repo evidence | Drop/post-drop cycles use usable-only shuffle bags on autoloop ticks; static initial-impact fallback and deterministic Laser Pad Verify are covered. Local rig may work, but broad safety/fixture support is not claimed. |
| Laser Pad web UI | implemented | software/frontend tested partially | local setup | Operator tool, not broad support claim. |
| LED Look Director | implemented | software-tested partially | local setup | Active bank behavior must be checked against code before changing docs. The live LED lifecycle is unchanged; a pure flat-window parity resolver is used by laser policy only. |
| LED scripted-track automation policy | implemented | software-tested partially | hardware-unvalidated | When enabled during `lighting_mode == "scripted"`, groove/drop/post-drop select the existing `utility` blackout bank while buildup/pre-drop and breakdown remain active. The shipped example config now enables the master switch (`true`) with the conservative blackout policy, so out-of-box scripted LED automation is active; room-visible behavior still needs hardware validation. |
| LED color engine M2 work | implemented/partial | software-tested partially | local setup | Current code includes color engine paths, fixed six-slot slot-color output, configurable slot-fill strategies including Patch S `random_with_mono_chance`, software-tested generic groove/post_drop/drop chase, drop center-burst, Patch E1 nebula slot cues, Patch E2 center-comet slot cue, Patch E3 ambient twinkle slot cue, and Patch F default-bank cleanup into generic slot looks plus `legacy_color_suffix` storage. Patch D/E/S/F remain SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED. |
| Govee cloud scene adapter | implemented | software-tested partially | local setup | Single API-key path, device compatibility not generalized. |
| Govee realtime runner/transport | implemented/experimental | software-tested partially | local setup | H612D evidence exists in config examples, broad Govee support unknown. |
| SoundSwitch export/operator UI | implemented | software-tested | pinned canonical project only | `Export from SS` publishes one canonical pack, shows exporting/reloading/result state, and uses only the conservative existing reload command. Verification now fails closed on loader-only runtime metadata gaps before publication, and the import report surfaces reserved-event/deactivated-script diagnostics. Pack output auto-switches by SoundSwitch connection using `set_soundswitch_pack action=enable`; a fresh disconnected `pack_start_failed` gets one bounded retry. There is no manual pack button, and auto-switching does not imply hot-enable without a real pack backend + Enttec port. The combined pack row is copied-state only; stale status renders `Lighting: no status yet`. SoundSwitch save remains operator-owned. |
| Multi-Rekordbox-version support | unknown | unvalidated | unknown | Needs explicit compatibility expansion tasks. |
| Windows/Linux support | unsupported/unknown | unvalidated | unsupported currently | Current reader architecture is macOS-bound. |
