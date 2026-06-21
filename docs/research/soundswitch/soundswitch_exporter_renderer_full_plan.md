---
doc_status: historical-evidence
truth_level: evidence-constrained-plan
last_verified_commit: 8ca5875
last_verified_date: 2026-06-21
validation_scope: planning only; no exporter/renderer implementation; hardware-unvalidated
---

# SoundSwitch Exporter / Renderer Full Plan

> **Historical plan, superseded 2026-06-21.** The mixed/provenance and active
> coverage blockers described below are closed for the bounded 2.10.3 product.
> The final scope now also requires all 32 Static Looks and learned DDJ/IAC
> mappings. Use `soundswitch_re_closure_report.md` and the final grouped
> importer/exporter/player implementation spec.

> **2026-06-20 correction (authoritative).** A newly identified hard blocker:
> cue-reference resolution is provenance-dependent and NOT byte-deterministic
> (legacy scripted=one-based wire-proven; new=direct; edited-legacy=MIXED;
> captured legacy autoloops=one-based wire-proven). The exporter cannot deterministically resolve
> cue identities for edited/mixed files from bytes alone — it must fail closed or
> consume an external wire/playback oracle or provenance. Exporter readiness and
> renderer readiness are reported separately and both remain NOT ready. See
> `docs/research/soundswitch/soundswitch_ssfile_format.md`. The concrete implementation spec
> for the standalone laser path (exporter + byte-exact renderer + Enttec output
> via VLN `dmx_pro.py`) is
> `docs/research/soundswitch/soundswitch_standalone_laser_exporter_spec.md`.

## Current decision

Do not implement the exporter, pack, importer, or runtime renderer yet. The
research has a viable structural path, but render-affecting unknowns remain.
This plan defines the order and gates once controlled evidence exists.

Status remains **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

## Product boundary

The first product is a deterministic, versioned, static pack for the current
SoundSwitch 2.10.3 project and current 19-channel fixture output. It is not a
general SoundSwitch clone, project editor, broad fixture engine, or promise of
compatibility with other projects/versions.

The future bridge-import path must preserve SoundSwitch as a supported existing
authoring/runtime route. No implementation may remove, bypass, or silently alter
the current OS2L/SoundSwitch path.

SoundSwitch is the continuing authoring source. Every export performs a complete
stable rescan of the named project. Frozen copies and passive captures are
independent test oracles; users do not need a new capture for each ordinary edit
once that mutation/layout/semantic class is supported.

## Phase 0 — close research blockers

Required before code design:

- isolate CH11=227 control ownership;
- name auxiliary and negative-time semantics or exclude affected files;
- prove shared-table role or prove it non-rendering for declared scope;
- capture at least one repeated, known-state, byte-exact representative per
  supported autoloop semantic/layout class and every outlier/new residual;
- decode and recapture the residuals in the three representative scripted
  captures (TITANIUM 16/64, Opalite 23/39, New Sky 304/367); merely adding more
  tracks does not clear this gate;
- extend the captured Opalite transport result beyond its current partial gate:
  representative seek/loop/refire positions are exact and confirmed stops clear
  to zero, but one seek/pause interval inherits a known base-render residual and
  unload leaves stale bridge metadata;
- define bridge-owned deck precedence/composition; SoundSwitch master/crossfader
  parity is required only if explicitly included in product scope;
- decode universe/address/mirror routing or define a versioned external bridge
  fixture-map input with explicit provenance and hashing;
- choose a bounded TrackMap source rule and classify sidecar/preset effects.
- complete the authoring mutation matrix on a fixture-bearing duplicate so a
  full rescan proves create/edit/rename/remove behavior.

Gate: the pack contract can be filled without `unknown`, guessed fields, or
wire-seeded production state.

## Phase 1 — frozen corpus and independent verifier

Create a read-only frozen test corpus outside the live project, with:

- source-relative files and SHA-256 manifest;
- the current Venue, catalogs, TrackMap, all 42 autoloops, all 45 scripted
  files, classified sidecars, and passive captures/logs;
- controlled before/after diffs;
- expected parser JSON generated from reviewed evidence.

The frozen corpus is a verifier oracle, not the exporter's normal input
authority. Production export always rescans the named current project.

Implement an independent verifier before the exporter. It must reject:

- one changed source byte;
- a duplicate/missing source;
- an unresolved cue index;
- a changed footer/trailer;
- omitted continuation records;
- an identity conflict;
- an unsupported source silently excluded from totals.

Gate: verifier passes the frozen corpus and fails each adversarial mutation.

## Phase 2 — production read-only decoders

Promote only byte-verified research seams into production-quality modules:

1. manifest and source freezer;
2. catalogs;
3. Venue cues and fixture patch;
4. autoloop containers;
5. supported scripted layouts;
6. TrackMap/SSID identity;
7. classified sidecars required by supported scope.

Requirements:

- complete start/end project inventory on every export, including added,
  removed, opaque, and unsupported paths;
- no dependency on `tools/ssfmt/re/` at runtime;
- typed models and bounded lengths/counts;
- exact EOF/trailer/continuation validation;
- source offsets in every diagnostic;
- no fuzzy path search;
- unsupported version/layout fails closed;
- no live project writes.

Gate: production decoders and research parsers agree on the frozen corpus, and
the independent verifier confirms all source coverage.

## Phase 3 — deterministic pack writer

Implement the artifacts specified in
`soundswitch_decode_export_codex_spec.md`:

- `manifest.json`
- `fixture_patch.json`
- `selection_map.json`
- `venue_cues.json`
- `autoloops/*.json`
- `scripted/*.json`
- `track_map.json`
- `import_report.json`

Requirements:

- byte-for-byte deterministic output from the same frozen input;
- canonical ordering and numeric units;
- all source hashes and identifiers retained;
- unsupported entries visible;
- no timestamp/non-deterministic absolute path in hashed payloads;
- atomic write to a new output directory, never into the SoundSwitch project.

Gate: two clean exports compare byte-identical and independently verify.

## Phase 4 — offline renderer

Build an offline-only reference renderer first. Inputs are pack artifacts plus a
fully specified owner/transport state. Outputs are CH1-CH19 frames and a trace
showing:

- active track/look and source record;
- inherited, main, and named control layers;
- clear and sentinel actions;
- fixture transformation;
- owner-deck decision;
- expected transition time;
- source/error diagnostics.

It must render canonical ticks across each 19,200-tick autoloop and every
captured scripted event. It cannot read capture frames as input.

Gate:

- every supported capture frame is byte-exact after timing alignment;
- repeated occurrences are deterministic;
- mismatch value-pair counters are zero;
- all expected transitions are within declared tolerance;
- all unsupported cases reject before output.

## Phase 5 — importer state machine

Specify and implement the offline state machine for:

- load/play/seek/pause/resume/refire/end/unload;
- autoloop phase and scripted elapsed time;
- clear/inherited control state;
- bridge-declared deck selection, precedence, and transfer;
- supported deck combinations.

SoundSwitch master/crossfader behavior is an optional parity extension. It does
not block static project export or a bridge-owned transport model unless exact
SoundSwitch multi-deck parity is declared in scope.

Gate: replayed controlled captures choose one deterministic state at every
event boundary, including backward seeks and deck changes.

## Phase 6 — bridge integration design review

Only after offline gates pass, write a separate implementation spec grounded in
current bridge code and invariants. It must preserve:

- `StateManager` as sole `DeckState` writer;
- immutable `BridgeEvent` ownership;
- 200 Hz loop free of blocking I/O;
- existing SoundSwitch, laser, LED/Govee, Rekordbox, and status behavior;
- explicit mode/config opt-in and rollback;
- bounded output worker/sender ownership;
- blackout/failure safety and stale-state handling.

No live runtime mutation occurs during design/review.

Gate: architecture, safety, failure modes, observability, and operator controls
receive explicit review approval.

## Phase 7 — software-only bridge implementation

Implementation must be split into reviewable patches:

1. pack loader and schema verification;
2. pure render/state engine;
3. runtime status/diagnostics without output;
4. disabled-by-default output adapter;
5. bounded sender and safety interlocks;
6. explicit config and docs.

Each patch follows its repo change contract. Tests cannot modify the real
SoundSwitch project or send output.

Gate: full software suite, docs checks, replay corpus, failure injection, and
code review pass with output disabled.

## Phase 8 — operator-gated live validation

Live work requires a separate explicit approval for every restart, toggle, and
hardware-adjacent check. Begin with fixtures physically disconnected, passive
network observation, and a rollback path. Physical fixture validation is a
separate matrix and cannot be inferred from Art-Net equality.

Gate: operator records version, interface, fixture, expected behavior, actual
result, date, failure/rollback result, and whether hardware validation is truly
earned.

## Non-negotiable stop conditions

Stop and report rather than guess if:

- source hashes drift;
- a positive reference does not resolve exactly;
- an unsupported file would be omitted;
- a wire frame matches only after hidden seeding;
- owner state is ambiguous;
- fixture patch fields are unknown;
- the implementation would add I/O to the 200 Hz loop;
- live approval is missing.

## Current readiness

Phase 0 is incomplete. No later phase is authorized by this plan. The next
bounded work is the operator capture/diff handoff, followed by passive analysis
and updated matrices.
