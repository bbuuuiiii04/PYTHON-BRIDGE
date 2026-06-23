---
doc_status: historical-evidence
truth_level: evidence-constrained-procedure
last_verified_commit: 8ca5875
last_verified_date: 2026-06-21
validation_scope: operator procedure only; no live commands executed; hardware-unvalidated
---

# SoundSwitch Stage 3 Operator Handoff

> **Completed/superseded 2026-06-21.** The required fixture-bearing mutation
> corpus, Autoloop capture, cold newly authored track capture, static-look
> diffs, and binary reader/writer work are complete. No operator action in this
> historical handoff remains a product blocker. Current authority is
> `soundswitch_re_closure_report.md`.

> **2026-06-20 update.** The controlled scratch-project authoring corpus is now
> captured (`/tmp/soundswitch_finish_IiVlD1`), including the legacy scripted-edit
> experiment. Key result: cue-reference convention is provenance-dependent (legacy
> scripted=one-based wire-proven, new=direct, edited-legacy=MIXED, autoloops
> non-uniform/unproven). Remaining operator-gated blockers below still require
> explicit per-run approval: playback/wire captures (esp. an autoloop wire anchor
> to settle the autoloop convention and the CH11=227 layer), restarts/toggles,
> and any hardware check. See `docs/research/soundswitch/soundswitch_ssfile_format.md` and
> `soundswitch_authoring_mutation_matrix.md`.

## Purpose and approval boundary

Existing files and captures are exhausted for the blockers below. Further
progress requires controlled operator evidence. Codex must not execute these
commands, manipulate the SoundSwitch UI, edit the real project, start/stop/signal
the bridge, or send MIDI, OS2L, Art-Net, serial, Enttec, or physical DMX.

Before any run, the operator must explicitly approve the live operation and
confirm fixtures are physically disconnected or otherwise safe. No restart or
toggle is implied by this document.

Status remains **SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED**.

The older `artnet_lo.pcap` does not remove this need: its derived 41-index
library lacks raw segment timestamps and matching copied AppLogs, so using it as
exact per-frame evidence would require fabricated boundaries.

## Priority 1: isolate CH11/control ownership

Hypothesis to falsify: CH11=227 is retained by an independent control/effect
layer rather than produced by the referenced Venue `STROBE` cue.

Run from a known clear state with only one SoundSwitch deck active. Keep BPM
fixed. Capture at least two complete 32-beat cycles per look and repeat each
look.

| Note | AppLog index | File | Role |
| ---: | ---: | --- | --- |
| 32 | 4 | `SSAutoLoop5.ssfile` | clean raw-zero/blackout control |
| 64 | 17 | `SSAutoLoop18.ssfile` | clean raw-zero/blackout control |
| 105 | 46 | `SSAutoLoop47.ssfile` | CH11=227 residual |
| 106 | 47 | `SSAutoLoop48.ssfile` | CH11=227 + auxiliary residual |
| 111 | 54 | `SSAutoLoop55.ssfile` | CH11=227 + negative/ref-zero residual |

Expected observations:

- If files 47/48/55 still produce CH11=227 after a confirmed clear with the
  other deck stopped, another-deck inheritance is falsified.
- If disabling one effect/control lane removes only CH11=227, that lane becomes
  the leading owner.
- If changing only the cue's CH11 changes the wire from 227, the cue and
  retained layer have a defined precedence that can be modeled.
- If repeated runs differ from identical initial state, deterministic static
  export is blocked.

## Priority 2: low-ratio autoloops

After the priority-1 control run, capture:

| Note | AppLog index | File |
| ---: | ---: | --- |
| 101 | 15 | `SSAutoLoop16.ssfile` |
| 107 | 49 | `SSAutoLoop50.ssfile` |
| 108 | 51 | `SSAutoLoop52.ssfile` |
| 110 | 53 | `SSAutoLoop54.ssfile` |

The expected result is not “looks right.” It is an exact CH1-CH19 frame sequence
with separate timing residuals. Each mismatch must retain expected/actual values
and source offsets.

## Priority 3: controlled project diffs

Never edit the real project. The operator creates a scratch/duplicate project
and changes one property at a time. Preserve before/after file hashes and a copy
of every changed source file.

Current evidence and gate:

- [confirmed] A blank operator-created scratch did not expose the fixtures. Its
  attempted AL-ADD run produced no cataloged autoloop and is invalid setup
  evidence.
- [confirmed] Opening `default.ssproj` rewrote only its non-authoritative Venue
  backup to equal current Venue bytes. No authoritative Venue/cue/catalog/script
  change was observed, and no restore was performed.
- [assumed] SoundSwitch `Save Project As` is the next candidate for a
  fixture-bearing duplicate, but it is not authorized by this handoff.
- [unknown] Before any further UI step, the operator must explicitly accept the
  possibility of another application-managed backup write and identify the new
  duplicate path. Codex must freeze and compare the project before requesting
  the next one-action audible ping.

For an authorized run, request exactly one UI action at a time. An audible ping
is the execution signal; the operator need not type a response. After the files
settle, freeze the complete after state and stop for comparison. Do not combine
creation, editing, naming, playing, or triggering in one experiment.

Use the read-only freezer/comparator commands in
`docs/research/soundswitch/research_tools.md`. A source that changes during read, an unsupported or
opaque changed source, an unresolved reference, or an unexplained consistency
failure invalidates the experiment and stops the sequence.

Once a fixture-bearing duplicate exists, run these as separate experiments:

1. Same cue, CH11 changed only.
2. Same timeline, one raw-reference-zero event added/removed.
3. Same timeline, one negative-time event added/removed.
4. Same autoloop, one effect/control lane disabled.
5. Same cue, one sparse channel added.
6. Same cue after two different known prior states.
7. Same auxiliary record with one value changed, if the UI exposes the owning
   property.
8. One fixture moved to a different universe/address, with every other fixture
   field unchanged.
9. One scratch audio file moved without changing its SSID tag, followed by a
   separate case-only rename.
10. One automation-preset value changed, followed by a separate track
    reanalysis that changes only its `.ssa` sidecar.

For each diff, record:

- scratch project path and SoundSwitch version;
- exact UI change;
- before/after SHA-256 for every changed file;
- byte-diff offsets;
- captured CH1-CH19 before/after;
- a prediction that can be falsified.

For TrackMap diffs, the falsifiable expectation is that SSID remains stable
while locator fields change. The current corpus has no case-fold collision, so
case behavior cannot be claimed without the case-only scratch diff. For
`.sspreset` and `.ssa`, compare bytes first and request a wire run only if the
single-variable change shows a plausible project reference or output effect.

## Priority 4: scripted layouts and transport

TITANIUM (`FC10FC02`), Opalite (`74044FA4`), and New Sky (`AE9E3C61`) plus a
dedicated Opalite transport run were captured on 2026-06-20. Both mirrored Venue
groups compare identically. Results are blocked, not complete: 16/64, 23/39,
and 304/367 event samples are exact. Opalite behaves one-based on default-project
wire despite its earlier “new direct” provenance label. New Sky's decoded
decoupled-color case clears CH8 instead of persisting it. The transport run has
exact representative seek/loop/refire samples and exact confirmed-stop clears,
but a known base-render residual remains. Summary:
`/tmp/ss_scripted_validation_summary_20260620.json`.

BLACKPINK/JUMP (`1FD042ED`) and restored clean Where Have You Been (`528E8B22`,
hash `1f740632…`) remain optional follow-up captures; they cannot by themselves
clear the current renderer gate. The archived `WHYB-AFTER.ssproj` copy
(`63302346…`) remains the edited-legacy MIXED negative control and fails closed.

Choose one safe representative from each structurally distinct layout:

- shared 441-byte layout (A5 is already the baseline);
- addressed-footer alternate-profile layout;
- addressed-footer current-profile DD42 layout;
- no-shared-anchor 1A62 layout;
- In-App Demo only if the operator can run it safely and wants that layout in
  scope.

For each representative, isolate these operations in separate captures:

1. initial load;
2. play from zero;
3. seek forward;
4. seek backward;
5. pause;
6. resume;
7. refire/reload;
8. deck transfer;
9. end of track;
10. unload/stop.

Expected observation: a deterministic output state and event-time rule for each
operation. If the same operation from the same state differs, that layout cannot
be statically imported.

## Priority 5: deck ownership and composition

The future bridge importer should take deck selection and transport from bridge
state; reproducing SoundSwitch's internal master/crossfader owner is not a
static-export gate. Run these one-variable captures only if SoundSwitch parity
is explicitly desired or if they are needed to isolate a current wire residual:

1. Hold Deck 1 selection/transport constant; change only Deck 0 selection.
2. Hold Deck 0 constant; change only Deck 1.
3. Change only master-deck ownership.
4. Change only crossfader position.
5. Stop/unload only the inactive deck, then only the active deck.
6. Transfer the same track between decks.
7. Overlap one scripted track and one autoloop.
8. Repeat for Decks 3/4 only if those decks are desired in supported scope.

Capture both Universe 0 and 1. Copy AppLogs immediately. The falsifiable question
for each run is which single deck/control change caused the next Universe state.

## Passive capture command — operator only

```bash
cd /Users/bbui/rb_ss_bridge_v2
sudo tcpdump -i lo0 -s0 \
  -w tools/ssfmt/captures/<descriptive_name>.pcap \
  udp port 6454
```

The operator starts and stops `tcpdump`; the agent does not. Use a new descriptive
name for every run and never overwrite an existing capture.

## Log-copy template — operator only

```bash
mkdir -p tools/ssfmt/captures/<descriptive_name>_logs
cp /tmp/bridge.log tools/ssfmt/captures/<descriptive_name>_logs/
cp "$HOME/Library/Application Support/Onesixone/Soundswitch/Logs"/AppLog*.txt \
  tools/ssfmt/captures/<descriptive_name>_logs/
```

Also record the project and Venue hashes immediately before and after each run.
A changed real-project hash invalidates the run.

## Acceptance for each capture

- one named hypothesis and expected falsifying observation;
- fixtures disconnected/safe confirmation recorded by operator;
- pcap, AppLogs, and bridge log copied;
- project files unchanged unless it is a named scratch diff;
- at least two complete cycles and one repeat;
- no missing deck/time selection evidence;
- parser reports capture path, size, hash, counts, and unsupported packets;
- byte equality separate from transition timing;
- no physical/hardware validation claim.

## What not to do

- Do not restart or toggle the bridge without a separate explicit approval.
- Do not send test MIDI or select looks from an agent command.
- Do not enable a physical output merely to satisfy this research.
- Do not modify `~/Music/SoundSwitch/default.ssproj/`.
- Do not substitute the Venue backup or a similarly named cue.
- Do not restore or overwrite an application-managed backup automatically.
- Do not call a visual impression byte-exact.

The next agent session should first verify hashes and read the new capture
passively, then rerun the research validators. Production work stays deferred
until every declared in-scope gate passes.
