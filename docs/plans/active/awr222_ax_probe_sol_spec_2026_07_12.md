# AWR-222 Accessibility Probe Review and Terra High Implementation Spec

Review date: 2026-07-12  
Review pin: current working tree observed at `aa7d4410a720ee2ee77a837d9a515ef6eccd5a5c`; the tree was already dirty in the USB, reader, menubar, test, docs, and lighting areas.  
Lane: Sol xHigh manager/reviewer, read-only repository review.  
Status: **PROCEED WITH MEASUREMENT ONLY**. This is not approval of AX as a bridge reader. It is not hardware validation.

## Manager verdict and adversarial findings

1. **P0 — AX has not met any live bridge contract yet.** [confirmed] Current code needs separate two-deck track-load, transport, BPM, position, mixer, and master facts. `PositionSnapshot` must carry elapsed, playing, length, and freshness (`models.py:98-117`); the active-deck resolver needs both decks' playing, upfader, LOW, and Rekordbox-master state (`active_deck_resolver.py:25-73`). [unknown] None of those required fields has been observed in Rekordbox's live AX tree. The user-provided AppKit/JUCE strings establish only that AX support exists somewhere in the binary, not that the deck surface exposes the required semantics, cadence, or grouping.

2. **P0 — current `lsof` is not independently exact two-deck identity.** [confirmed] `_lsof_audio_files()` returns every open audio path for the Rekordbox process (`filepath_resolver.py:95-115`). The resolver assigns one to a deck using `PositionCache.track_length_ms`, or accepts the only open file (`filepath_resolver.py:1205-1229`). That cache is exactly what fails when `task_for_pid` is unavailable. For USB-device ANLZ misses, current code explicitly skips `lsof` (`filepath_resolver.py:1070-1078`), and `tests/test_filepath_resolver_usb_twin.py:230-243` pins that behavior. Therefore the probe may record exact process-wide candidates, but it must not call them deck-exact unless AX supplies an independently unique join. Duplicate or unresolved joins must abstain.

3. **P0 — AX-only capture cannot measure action-to-observation latency against itself.** [confirmed reasoning] An AX notification timestamp proves when the probe received AX, not when the operator pressed Play, Cue, or moved a control. A read-only AX probe is forbidden from performing target actions, and screen/input capture is out of scope. Play/pause, cue/scrub, and control latency therefore require a separately permitted reference timestamp in the later operator gate. If no reference is available, latency is `unmeasured` and acceptance fails; the implementation must not manufacture a number.

4. **P1 — the installed dependency set does not currently expose the AX wrapper.** [confirmed-current-machine] `AppKit`, `Foundation`, and `objc` resolve, but `ApplicationServices` and `Quartz` do not. The official PyObjC `pyobjc-framework-ApplicationServices` 12.2.1 package exists and pulls its matching Quartz/CoreText wrappers; the locked build currently pins only `pyobjc-core` and `pyobjc-framework-cocoa` (`packaging/macos12_arm64_cp313.lock:40-41`). The smallest maintainable implementation is the official wrapper, locked with the rest of the bundle—not a hand-written CoreFoundation/AX `ctypes` layer.

5. **P1 — the normal menu is deliberately locked and tested.** [confirmed] The frozen menu intentionally exposes only bridge, log, four status rows, laser safety, purge when installed, and restart (`scripts/bridge_menubar.py:1083-1115`); inventory tests pin the exact selector set and reject dead controls (`tests/test_bridge_menubar.py:993-1064`). Adding an everyday AX item now would violate that contract before AX is even known to work.

6. **Recommendation after refutation attempts:** retain AX as the smallest next *measurement*, not the selected replacement. [confirmed] MTC is active-deck-only and depends on already-correct active-deck routing (`mtc_reader.py:15-16,124-142`); OSC supplies legacy active-deck and scripted triggers, not the full deck state (`__main__.py:644-726`); the installed sidecar supplies analysis/identity data but no live transport or mixer state (`filepath_resolver.py:475-518`); and current memory readers all reach `task_for_pid`/`mach_vm_read_overwrite` (`rb_memory.py:62-100`). No current public path is smaller *and complete*. AX remains viable only if the operator capture passes every hard gate below.

The adversarial failure to design around is library browsing: an AX table/label may expose the highlighted browser song and look exactly like a deck title. Current memory code already needed a three-tick stability gate because this caused real phantom loads (`rb_state_reader.py:95-103,369-427`), with browse-storm coverage in `tests/test_rb_state_reader.py:425-440`. The AX probe must collect enough structure and timing to disprove this confusion; it must not bind a field merely because its text resembles a track.

---

# Part A — Context and root cause (verified; read, do not implement)

## A1. Current blocking boundary

- [confirmed] The reader calls `task_for_pid` and then `mach_vm_read_overwrite` directly (`rb_memory.py:62-100`). Two user-reported physical foreign-Mac attempts failed. Target-only `get-task-allow`, ad-hoc caller debugger entitlements, SIP weakening, and DevToolsSecurity workarounds are rejected requirements.
- [confirmed] The current frozen app identity is `com.bbui.rb-ss-bridge-v2` (`packaging/rbss_launcher.spec:101-120`). `usb_launcher.main()` already provides lazy, mutually exclusive self-dispatch before bridge startup (`usb_launcher.py:258-288`). This is the correct place for a probe entrypoint.
- [confirmed] `_run_bridge()` is the dangerous boundary: it imports `rb_ss_bridge_v2.__main__`, loads live settings, and starts the full bridge (`usb_launcher.py:85-128`). The probe must never call or import this path.
- [confirmed] The bridge consumes fresh position at 60 Hz (`config.py:60-62`; `rb_memory.py:1230-1276`) and the 200 Hz loop stops live behavior when a snapshot is absent/stale (`state_manager.py:4362-4425`). MTC can synthesize a position only when there is no snapshot, and it is routed to the current active deck (`state_manager.py:4385-4398`; `mtc_reader.py:124-142`). Title, MTC, or Link-like tempo alone is not parity.
- [confirmed] Mixer authority is whole-snapshot fail-closed: both decks' upfaders and LOW values must be finite and readable, then normalize to the model used by `resolve_active_deck` (`rb_state_reader.py:544-606`).
- [confirmed] The installed sidecar path is fixed under App Support (`filepath_resolver.py:54-58`) and the validator checks schema, record types, confined paths, BPM/duration, fingerprints, ANLZ, v4, IDs, and tags (`filepath_resolver.py:475-518`). The normal runtime discovery also enumerates `/Volumes` (`filepath_resolver.py:559-564`); the diagnostic must not call that discovery helper.
- [user-provided, not reverified in this lane] Rekordbox 7.2.11 contains AppKit/JUCE accessibility handlers and AX title/value notification strings. [unknown] Live field exposure, grouping, cadence, layout behavior, language behavior, and TCC persistence.

## A2. Binding source contract AX would eventually have to satisfy

AX is rejected as a future runtime source unless it can supply, independently for bridge decks 1 and 2:

| Required fact | Current consumer contract | Why a partial public path is insufficient |
|---|---|---|
| title + artist + stable load identity | `TRACK_LOADED`, `load_gen`, ANLZ/sidecar resolution; browser phantoms forbidden | `lsof` is process-wide; title-only duplicates are ambiguous |
| play/pause | per-deck `DeckState.playing`; resolver eligibility | MTC movement for one routed deck does not identify both decks |
| elapsed + duration + freshness | `PositionSnapshot` fields and `updated_at`; 60 Hz publication | a one-second UI label cannot safely drive cue/scrub or beat phase |
| BPM + beat phase | per-deck BPM plus sidecar beatgrid/elapsed | Link/tempo without deck identity and elapsed is not enough |
| master | separate fresh `rb_master_deck` tie authority | active deck and Rekordbox master are deliberately not the same fact |
| upfader + LOW, decks 1/2 | `MixerDeckReading` normalized values | active-deck policy depends on both decks and fails closed on missing values |
| stale/quit/layout loss | invalid/unavailable transition, never held success | stale values can keep the wrong deck and room state alive |

This round does **not** create `BridgeEvent`s, write `PositionCache`, or change source arbitration. It only determines whether a later adapter could do so honestly.

---

# Part B — Tasks (implement exactly, in order)

## Absolute rules

### Exact allowed files

Code/build:

- `usb_launcher_ax_probe.py` (new; name deliberately matches the existing `usb_launcher*.py` contract glob)
- `usb_launcher.py`
- `pyproject.toml`
- `packaging/rbss_launcher.spec`
- `packaging/macos12_arm64_cp313.lock`

Tests:

- `tests/test_usb_launcher_ax_probe.py` (new)
- `tests/test_usb_launcher.py`
- `tests/test_make_stick.py`

Required docs for the existing `usb_launcher` contract and the reader/status truth surfaces:

- `docs/plans/active/usb_bridge_launcher_design.md`
- `docs/setup/usb_launcher_runbook.md`
- `docs/status/active_work_registry.md`
- `docs/validation/software_test_inventory.md`
- `docs/subsystems/rekordbox_readers.md`
- `docs/subsystems/runtime_commands.md`
- `docs/status/support_matrix.md`
- `docs/status/validation_matrix.md`

No other file is allowed. Re-read every allowed file immediately before editing because the working tree is shared and already dirty. Preserve all unrelated edits. Do not commit, revert, clean, stage, or rewrite files outside the lane's explicit commit instruction from its executive.

### Forbidden files and systems

- No edits to `state_manager.py`, `__main__.py`, `models.py`, `rb_memory.py`, `rb_state_reader.py`, `active_deck_resolver.py`, `filepath_resolver.py`, `live_bpm.py`, `mtc_reader.py`, `scripts/bridge_menubar.py`, `install_controller.py`, `rekordbox_patch.py`, any lighting/SoundSwitch/laser/LED/Govee/Stream Deck module, any `config/*.json`, `govee.env`, signing identity, or local state.
- Do not start or stop the bridge, menubar, Rekordbox, Stream Deck, SoundSwitch, Enttec, OS2L, lasers, LEDs/Govee, pads, viewers, or helpers.
- Do not run the probe. Do not call `AXIsProcessTrusted*`, inspect any live AX tree, trigger TCC, run `lsof` against Rekordbox, read `/Volumes`, read an installed sidecar, open an audio file, build/sign/open the `.app`, or contact hardware during this implementation round.
- No screen capture, event tap, keyboard monitoring, Accessibility write, Apple Event to Rekordbox, target patch, process-memory read, MIDI input/output, OSC, network, serial, DMX, or config mutation.
- No new everyday menu item. `scripts/bridge_menubar.py` remains byte-untouched.

### Error behavior

- Fail closed with a nonzero code and a short native/plain-language error. No broad success-shaped fallback.
- Permission missing, wrong bundle, source/DMG/translocated launch, bridge already running, zero/multiple Rekordbox processes, unsupported AX, truncated tree, target quit, layout loss, sanitizer failure, evidence write failure, sidecar ambiguity, or duplicate identity are explicit unsuccessful outcomes.
- Shareable evidence must never receive a raw exception message; it gets an error class/token only. Private evidence may retain a traceback locally.

## Task 1 — add the one official AX wrapper to the locked bundle

1. Add `pyobjc-framework-ApplicationServices` with the same macOS/PyObjC version policy as the existing Cocoa dependency. Do not add a custom AX binding or another library.
2. Update `packaging/macos12_arm64_cp313.lock` with exact 12.2.1 hashes/artifact names for ApplicationServices and every newly required PyObjC wheel (including matching Quartz/CoreText as resolved). Do not alter the source lock.
3. Add `ApplicationServices` to `_REQUIRED_BUNDLE_MODULES` in `usb_launcher.py` so the existing frozen `--check-deps` gate fails closed when it is absent.
4. Add the narrow PyInstaller collection needed for `ApplicationServices`; do not broaden collection to unrelated frameworks.
5. Extend the lock/dependency tests. Tests may read files and use import metadata; they must not import AX or call TCC.

## Task 2 — add isolated packaged dispatch

In `usb_launcher.py`:

1. Document `--probe-rekordbox-accessibility` in the mode list.
2. Add `_run_rekordbox_accessibility_probe(argv)` that lazily imports only `rb_ss_bridge_v2.usb_launcher_ax_probe.main` and returns its integer status.
3. Dispatch the exact first argument before `--run-bridge`, forwarding remaining arguments unchanged.
4. Do not load Govee env, `launch_profile`, `rb_ss_bridge_v2.__main__`, menubar code, output code, or config for this mode.
5. Unknown arguments remain a nonzero error. The probe parser owns its own flags.

No menu selector or normal-start behavior changes.

## Task 3 — implement the smallest read-only AX capture

Create `usb_launcher_ax_probe.py` as a diagnostic, not a framework and not a reader abstraction.

### 3.1 CLI and preflight

Accepted flags only:

- `--duration-s N` (default 120; integer 10..900)
- `--layout TEXT` and `--language TEXT` (recorded verbatim only in private evidence; normalized shape/token in shareable evidence; missing values become `unknown` and make a validation run incomplete)
- `--prompt-permission` (absent by default)

Output location is fixed, not caller-selectable:

`~/Library/Application Support/RBSS Bridge/diagnostics/rekordbox_ax/<UTC-run-id>/`

Create the directory as `0700` and files as `0600`. Never write inside the app bundle, repo, `/tmp`, mounted volumes, sidecar, Rekordbox directories, or bridge logs.

Preflight, in this order:

1. Require `sys.frozen`, `NSBundle.mainBundle().bundleIdentifier() == "com.bbui.rb-ss-bridge-v2"`, an enclosing `RBSS Bridge.app`, an installed non-DMG/non-AppTranslocation location, and the expected bundle version metadata. A source run is a testable refusal, not a supported mode.
2. Read the bridge lock/PID without creating or locking files. If it names any live PID, refuse. This is deliberately fail-closed; the probe never shares a session with a running bridge.
3. Check trust with `AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: False})`. With no `--prompt-permission`, never request a prompt. If false, write only the minimal permission/bundle summary, show a native explanation, and exit nonzero without creating a target AX element, running `lsof`, or reading the sidecar.
4. With `--prompt-permission`, first show a native consent panel explaining that the action grants read-only Accessibility observation to this exact installed app and does not start the bridge. Cancel exits without prompting. Continue is the only path allowed to call `AXIsProcessTrustedWithOptions(...True)`. Recheck without prompting; if still false, exit nonzero.
5. Find running applications by Rekordbox bundle ID `com.pioneerdj.rekordboxdj` using `NSRunningApplication`. Require exactly one live PID. Never launch, activate, focus, or send an Apple Event to Rekordbox.
6. Read the target app's version from its bundle metadata. Do not inspect or modify its signature/entitlements.

### 3.2 AX API allowlist

Only these classes of AX calls are allowed:

- trust check
- create application element for the already-running PID
- copy attribute names/values or bounded child slices
- copy action names only for evidence (never perform them)
- set the local AX messaging timeout
- create an observer, add/remove notifications, obtain its run-loop source
- obtain AX value types/geometry for serialization

Explicitly forbidden symbols/calls include `AXUIElementSetAttributeValue`, `AXUIElementPerformAction`, `AXUIElementPostKeyboardEvent`, any posting API, any target launch/activation, and any screen/input capture API. A static unit test must reject these names in the module.

### 3.3 Bounded tree snapshot and update observation

1. Take one breadth-first read of the application/windows tree. Track element identity to break cycles. Hard limits: depth 24, 2,500 elements, 1,000 scalar-bearing elements, 10 seconds wall time, and a short AX messaging timeout. Hitting any cap marks `tree_incomplete=true`; missing fields from an incomplete tree are not negative evidence.
2. For every element, privately record ancestry, child ordinal, role, subrole, identifier, title, value, description/help, enabled/focused/selected state, position/size, supported attribute names, and supported action names. Read only attributes the element advertises; unsupported/error results are data, not crashes.
3. Register read-only observers for title, value, selected-children, row-count, layout, focus, window-created, and element-destroyed notifications where supported. Unsupported notification registration is recorded and polling remains available.
4. Poll only the bounded scalar-bearing set at 10 Hz using the multiple-attribute API where available; observers provide higher-frequency change evidence. Do not repeatedly walk the whole tree. Record monotonic nanoseconds, UTC timestamp, sequence, source (`initial`, `notification`, or `poll`), AX error class, and call duration.
5. On PID loss, invalid element, permission loss, window/layout destruction, or repeated `cannotComplete`, publish a terminal unavailable record within the probe and stop. Never hold the last value as healthy.
6. Produce grouping *candidates*, not deck assignments: stable ancestry fingerprints, mirrored/repeated subtree shape, normalized/quantized geometry, change cadence, and cross-field co-change. No role/title heuristic may label a group deck 1 or 2 automatically.

### 3.4 Exact `lsof` candidates and installed sidecar, without changing runtime code

Only after trust and unique-target preflight:

1. Import and call the existing `filepath_resolver._lsof_audio_files(str(pid))` unchanged at initial capture and at most 2 Hz/on observed scalar changes. This deliberately records the exact process-wide audio candidates current code would see. Do not call `FilepathResolver`, `_duration_ms`, DB lookup, title workers, mounted-sidecar discovery, or any bridge object.
2. Privately record the full candidate paths and set changes. In shareable evidence record only a per-run keyed token, extension class, candidate count, and first/last-seen times—never basename, directory, volume name, or raw path.
3. Load only `_INSTALLED_SIDECAR_INDEX` through `_load_sidecar_index`. Never call `_mounted_sidecar_indexes`, enumerate `/Volumes`, or write the sidecar. Record schema validity/count and per-run tokens for title, artist, duration, BPM, content ID, and fingerprint. Do not expose raw sidecar values in shareable output.
4. Use one per-run secret key to HMAC normalized AX strings and normalized sidecar title/artist values. This permits equality/correlation in shareable evidence without revealing the text. Keep the key only in the private manifest.
5. A candidate identity is `unique` only when title + artist match exactly after the existing Unicode normalization rule and, when available, duration agrees within the current two-second USB tolerance, with exactly one sidecar record. Title-only, missing artist, multiple sidecar records, or multiple plausible `lsof` paths is `ambiguous`; abstain. `lsof` set-delta correlation is evidence, not proof of deck identity.

### 3.5 Evidence files

Write atomically within the fixed run directory:

- `private.jsonl`: exact local-only AX values, full AX ancestry, full `lsof` paths, exact sidecar candidate data needed for semantic review, and private errors/tracebacks. Mode `0600`. Never presented as shareable.
- `private_manifest.json`: run HMAC key, exact bundle paths, argv, layout/language, and a prominent `DO NOT SHARE` warning. Mode `0600`.
- `shareable.jsonl`: sanitized event stream only.
- `summary.json`: sanitized counts/cadence/grouping candidates, permission state, versions, completeness flags, and explicit pass/fail/unmeasured fields.

Shareable schema version 1 must include:

- run ID; sequence; UTC and monotonic timestamps
- exact bridge/Rekordbox bundle IDs and public version strings; installed/translocated classification; signing identity class if it can be obtained without exposing certificate/person names
- permission state (`trusted`, `not_trusted`, `prompt_requested`, `revoked`, `unknown`) and AX error names
- declared layout/language shape/token
- node token; parent token; depth; child ordinal; role/subrole; identifier *shape/token*; title/value/description *type, length bucket, format class, token, change count*; normalized geometry; supported-attribute/action names
- event source, update intervals, observer-registration outcomes, call durations
- two-deck grouping candidates with reasons but no assigned deck
- `lsof` candidate tokens/extensions/counts/timing
- installed-sidecar validity/count and tokenized equality candidates
- completeness/truncation/quit/layout-loss flags

Sanitization is fail-closed. Before committing a shareable record, recursively reject any raw private string, home path, `/Volumes` path, basename, song/artist text, sidecar `source_filepath`, content ID, IP, device ID, API key, environment value, exception text, or HMAC key. A sanitizer failure stops the run and leaves only private evidence plus a minimal safe summary.

Do not add a semantic-field classifier beyond the exact equality/cadence/grouping evidence above. The live tree has not been seen; pre-guessing labels would be speculative code.

## Task 4 — software-only tests

Build the module around injected/fake facades so every behavior below is testable without importing ApplicationServices, AppKit UI, touching TCC, finding Rekordbox, running `lsof`, reading App Support, or opening `/Volumes`.

Required tests:

1. Dispatch forwards args to the probe and never calls `_run_bridge`, `_run_menubar`, or any other mode.
2. Source/wrong-bundle/translocated/bridge-live/zero-target/multi-target preflights fail nonzero before AX target, `lsof`, or sidecar calls.
3. Default permission check passes prompt false; denial makes zero target/`lsof`/sidecar calls. Prompt true is reachable only after fake native consent; cancel makes zero prompt calls.
4. BFS cycle handling, depth/node/scalar/time caps, advertised-attribute reads, unsupported errors, notification fallback, and terminal invalidation are deterministic under fakes.
5. Sanitizer canaries include a fake song, artist, duplicate title, home path, `/Volumes/MINK/...`, filename, API key, IP, device ID, content ID, source path, exception string, and HMAC key. None may appear anywhere in serialized shareable output; all required shapes/tokens remain.
6. Private files are `0600`, run directory `0700`, and atomic publication never crosses the fixed diagnostics root.
7. Same raw value has a stable token within a run and a different token across runs; no key appears in shareable output.
8. Sidecar exact title+artist(+duration) unique match succeeds; title-only, missing artist, duplicate-name, duration collision, and multiple matches abstain.
9. `lsof` is treated as a set of process-wide candidates; multiple candidates never become an exact deck assignment. Mounted-sidecar discovery is patched to explode and is never called.
10. Pure cadence summaries distinguish measured, failed, and unmeasured; they never infer action latency from AX callback time alone.
11. Static AST/import guard proves the probe contains no forbidden AX calls and no imports of `__main__`, StateManager, SoundSwitch, Enttec, OS2L, laser, LED/Govee, Stream Deck, MIDI, screen capture, target patch, or config loaders.
12. Dependency/spec/lock tests pin `ApplicationServices` and its required wrappers; existing locked-wheel compatibility rules stay intact.

## Task 5 — docs, no onboarding menu yet

Update every existing `usb_launcher` contract doc listed under `docs_update`, plus the exact reader/status docs in the allowed list. State only:

- probe implemented/software-tested, not executed
- no live AX evidence, no TCC evidence, no USB read, no foreign-Mac parity claim
- AWR-222 remains blocked
- normal menu unchanged
- first live run requires the explicit operator gate below

Do not call the probe supported, operational, ready, validated, or a replacement reader.

UX decision: **no everyday menu item in this round.** The packaged dispatch is the durable seam. The probe itself owns the native permission explanation when explicitly launched. After a successful operator capture, a separate design may choose one of two small onboarding surfaces: launch it once from installer completion, or show a conditional temporary **Set Up Rekordbox Access…** action only while setup is incomplete. Neither is justified before live feasibility. Do not add either now.

---

# Part C — invariants that MUST still hold

1. The probe process never imports or starts the bridge. It creates no `StateManager`, `PositionCache`, event queue, reader, status writer, command reader, output backend, worker, server, MIDI port, network socket, serial port, DMX sender, or hardware client.
2. `state_manager.py`, all lighting engines, current memory/MTC/OSC readers, active-deck policy, and output behavior remain byte-unchanged.
3. No Accessibility write/action API exists in the module. All target interaction is attribute copy or observer registration.
4. No TCC prompt without both the explicit CLI flag and native Continue confirmation.
5. The implementation/test round never executes any AX function or probe dispatch.
6. The probe refuses while a bridge PID appears live. It never starts/stops another process.
7. Runtime `lsof`/sidecar behavior is unchanged; the probe reuses read-only helpers without editing them. USB candidates remain process-wide until independently proven unique.
8. No mounted volume is enumerated by the probe. A later approved live run may observe paths already returned by `lsof`; that approval does not authorize writes.
9. Private evidence stays local with restrictive permissions. Shareable evidence contains no songs, artists, filenames, paths, secrets, device identity, or raw exception text.
10. Missing, ambiguous, stale, unsupported, truncated, revoked, quit, or layout-lost state is explicit unavailable/failed evidence, never last-known-good success.
11. A successful software test proves only dispatch/safety/sanitization logic. It does not prove a frozen app, TCC identity, Rekordbox AX exposure, update persistence, USB identity, timing, output, or hardware.

---

# Part D — verification commands (software only; never execute the probe)

Run from `/Users/bbui/rb_ss_bridge_v2`:

```bash
python3 -m unittest tests.test_usb_launcher_ax_probe tests.test_usb_launcher tests.test_make_stick
python3 -m unittest tests.test_filepath_resolver_usb_twin tests.test_filepath_resolver_sidecar tests.test_rb_state_reader tests.test_active_deck_resolver
python3 tools/check_docs_metadata.py
python3 tools/check_agent_contracts.py
python3 tools/check_docs_drift.py
python3 tools/check_docs_staleness.py --report
python3 -m unittest discover tests
```

Reconcile full-suite failures by test name against a fresh named baseline. Do not run any of these:

```text
--probe-rekordbox-accessibility
open ... RBSS Bridge.app
lsof -p <rekordbox-pid>
AXIsProcessTrusted*
any app build/sign/install/start/restart command
```

No test may make the forbidden operation indirectly. Mocking the operation is required.

---

# Part E — acceptance and fail-closed gates

## E1. Software implementation gate

All must be true before asking the operator to run anything:

- [ ] Only allowed files changed; existing unrelated dirty work preserved.
- [ ] Normal menubar selector inventory is byte-identical.
- [ ] Probe dispatch is lazy and cannot reach `_run_bridge`.
- [ ] Default permission path cannot prompt.
- [ ] Static guards ban output/runtime/AX-write imports and symbols.
- [ ] Private/shareable file permissions and atomic writes are tested.
- [ ] Every sanitizer canary is absent from shareable bytes.
- [ ] Duplicate/ambiguous identity abstention is tested.
- [ ] Dependency, PyInstaller collection, lock, and `--check-deps` declaration agree.
- [ ] Focused suites and three hard doc checks pass; full-suite results are named and reconciled.
- [ ] Docs say `implemented/software-tested/not executed`; AWR-222 remains blocked.
- [ ] No probe, TCC, Rekordbox, USB, sidecar, process, config, or hardware action occurred.

## E2. Later operator-approved live feasibility gate

The implementation lane must stop and request explicit approval. The exact first-run command to present—but **not run**—is:

```bash
open -n "$HOME/Applications/RBSS Bridge.app" --args \
  --probe-rekordbox-accessibility \
  --prompt-permission \
  --layout "<operator-confirmed layout>" \
  --language "<operator-confirmed language>" \
  --duration-s 180
```

The probe itself must refuse if the bridge is live. The operator must launch Rekordbox manually before this gate. The command must not launch Rekordbox or the bridge. A longer no-prompt validation run uses the same command without `--prompt-permission` and with `--duration-s 900`.

Healthy diagnostic behavior means: one native permission/setup explanation when requested; one local run directory; changing private/sanitized event counts; explicit completeness and permission state; no bridge PID; no Stream Deck/SoundSwitch/Enttec/OS2L/laser/LED/Govee process or output created by the probe. SoundSwitch, lasers, LEDs/Govee, Rekordbox reader status, and bridge logs should remain unchanged because the bridge is off. The probe writes its own diagnostics directory, not bridge logs.

## E3. Semantic acceptance matrix

Every row is mandatory for AX to advance to a separate runtime-adapter spec. One miss keeps AWR-222 blocked.

| Gate | Exact acceptance | Fail-closed result |
|---|---|---|
| 20/20 loads | 20 distinct loads total, at least 10 per physical deck; correct deck grouping, title, artist, and unique installed-sidecar record on all 20; include loads while the other deck plays | any miss, cross-deck swap, incomplete tree, or unmeasured identity rejects the mapping |
| browse phantoms | at least 50 browser-cursor changes per deck over at least 2 minutes with loaded decks unchanged; zero semantic load transitions | any browser selection classified as a load rejects the candidate fields |
| duplicate names | at least 3 duplicate-title/artist collision trials; no identity until artist+duration/path evidence makes exactly one candidate | resolving an ambiguous duplicate is an automatic reject |
| play/pause | each deck: 20 play and 20 pause transitions; separately permitted reference timestamps; p95 detection <=150 ms, maximum <=300 ms; no false transition | no independent reference = `unmeasured` = fail; any false transition rejects |
| elapsed cadence | both decks simultaneously: while playing, changed anchors have p95 interval <=100 ms and maximum <=250 ms; steady-play extrapolation residual p95 <=40 ms, max <=100 ms over 10 minutes; paused value remains fixed | slower/jumpy/missing cadence or unexplained drift rejects AX as position authority |
| cue/scrub | each deck: 20 cue jumps and 10 scrubs, independently timestamped; discontinuity detected and new elapsed established <=150 ms p95, <=300 ms max; interpolation never crosses the jump as healthy | any missed/backfilled jump or no reference rejects |
| BPM | both decks, normal and changed tempo: exact displayed value to available precision; finite 40..250 usable range; change visible <=250 ms; missing/invalid never keeps prior as fresh | missing or stale BPM blocks parity unless sidecar beatgrid plus validated elapsed provides the same fact |
| beat phase | sidecar beatgrid + observed elapsed produces phase error <=0.10 beat p95 and <=0.25 beat max against a separately permitted reference, including after cue/scrub | no reference, wrong grid join, or excess phase error rejects fresh `PositionCache` feasibility |
| faders + LOW | decks 1/2 independently: endpoints, midpoint, and at least 20 transitions each; normalized direction/endpoints stable; p95 <=150 ms, max <=300 ms; no cross-deck swap | missing one deck/control, inverted scale, stale value, or cross-deck coupling rejects mixer authority |
| master/audible deck | at least 20 master changes plus two-deck audible scenarios covering fader-down, one top, both top/LOW-neutral tie, LOW dominance, pause, and idle; replay through current `resolve_active_deck` yields expected decisions every time | AX label guessing or any wrong decision rejects authority |
| stale/quit/layout loss | permission revoke, Rekordbox quit/relaunch, window close/reopen, supported layout switch, unsupported layout, and element destruction each become unavailable within 500 ms; no old value remains healthy; recovery requires a fresh full group | held last-good or silent regroup is a reject |
| version/layout/language | evidence names Rekordbox version, layout, language; current intended combination passes. Unknown combinations report unsupported, not guessed | missing metadata or silent cross-layout reuse rejects |
| TCC/update persistence | trust survives app quit/reopen and one normal signed update using the intended stable bundle/signing identity; the new version records the same identity and can re-read without a surprise prompt | permission churn keeps AX experimental and blocks normal onboarding; never weaken SIP or patch TCC |
| fresh `PositionCache` feasibility | offline replay can generate simultaneous deck-1/deck-2 `PositionSnapshot`-shaped rows at 60 Hz with correct elapsed, playing, duration, monotonic freshness, the cadence/accuracy above, and immediate invalidation on loss—without changing runtime | inability to populate any field or safely invalidate means no runtime-adapter round |

The latency/accuracy reference may be a separately approved read-only trace, but it cannot be AX observing itself. This spec does not authorize MIDI input, screen/input capture, target actions, or another live source; the manager must approve the reference method before the operator run.

## E4. Final decision rule after live capture

- **PASS TO NEXT SPEC:** every E3 row passes with private evidence inspected locally and sanitized evidence independently reviewed. Then author a new runtime-adapter spec; do not fold integration into this probe round.
- **AX PARTIAL ONLY:** identity or labels exist but any timing/mixer/master/freshness row fails. AX may remain a setup/status aid, but it is rejected as the bridge reader.
- **AX REFUTED:** required two-deck elements are absent, browse-safe grouping is impossible, elapsed is too slow/inaccurate, permission does not persist, or layout loss cannot fail closed. Keep AWR-222 blocked and return to public-source research.

No outcome from this probe is hardware validation.

## When You Finish

Report:

1. exact changed files and commit(s), if the executive authorized commits
2. focused/full test names and results; named baseline reds
3. proof that the probe was not executed and no live/TCC/USB/hardware action occurred
4. proof that normal menu, `state_manager.py`, readers, configs, and lighting engines were unchanged
5. dependency/lock/spec agreement
6. remaining unknowns and the exact operator approval command above

Plain-language operator summary must say:

- **What should change live:** nothing yet. The installed app merely gains a dormant, explicit diagnostic mode.
- **What stays unchanged:** normal bridge start, SoundSwitch, lasers, LEDs/Govee, Stream Deck, Rekordbox target patch, reader authority, menu layout, and config.
- **Healthy behavior later:** only after approval, the separate probe writes local evidence and never starts lighting.
- **What to watch:** no bridge/output process appears; Rekordbox remains operator-controlled; private evidence stays local; sanitized output contains no track/path/secret text.
- **Verified vs not:** software dispatch/safety/sanitization only; AX fields, TCC persistence, USB identity, timing, frozen-app behavior, room output, and hardware remain unvalidated until their separate gates.

