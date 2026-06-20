---
doc_status: active-operator-handoff
truth_level: evidence-constrained-procedure
last_verified_commit: fd40843
last_verified_date: 2026-06-20
validation_scope: operator procedure only; no live commands executed; hardware-unvalidated
---

# SoundSwitch Stage 3 Operator Handoff

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

Run these as separate experiments:

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

The combined capture is not an ownership oracle. Use one-variable runs:

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
- Do not call a visual impression byte-exact.

The next agent session should first verify hashes and read the new capture
passively, then rerun the research validators. Production work stays deferred
until every declared in-scope gate passes.
