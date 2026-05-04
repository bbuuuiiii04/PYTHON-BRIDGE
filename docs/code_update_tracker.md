# Code Update Tracker For Claude Code

Updated: 2026-05-04

## Collaboration Rule

Do not edit bridge code without explicit user approval.

Before any code edit:

1. Propose the exact file and function to change.
2. Explain the evidence and reasoning.
3. State the expected behavior change and risk.
4. Wait for the user to approve.

Markdown documentation edits are allowed when requested.

## Current Uncommitted Code Changes For Review

These code changes exist in the worktree and should be reviewed before commit:

### `rb_memory.py`

Proposed/implemented behavior:

```text
For Deck 2 snapshots, set track_length_ms=0.
```

Reasoning:

```text
The runtime-discovered Deck 2 inner is proven by the +0x0c i32 position field.
Its surrounding layout is not proven to match Deck 1.
Live evidence showed +0x08 can mirror current position rather than track length.
Returning that as track_length_ms creates bogus lsof duration matching.
Deck 2 filepath resolution should rely on ANLZ/title fallback instead.
```

Validation so far:

```text
RBMemoryReader still resolves Deck 2 after restart.
Deck 2 elapsed advances correctly.
Deck 2 len now reports 0ms instead of mirroring elapsed.
```

### `state_manager.py`

Proposed/implemented behavior:

```text
Apply the 45-second TC freshness guard to the snap.elapsed_ms == 0 fallback path.
```

Reasoning:

```text
The no-snapshot TC fallback already has a 45-second guard.
The zero-position fallback previously did not.
Using stale TC anchors when a memory snap is zero can synthesize drifted position.
```

Validation so far:

```text
compileall passed after the change.
Deck 2 memory snapshots still resolve and advance.
```

## Deck 2 Discovery Evidence To Preserve

Session 1:

```text
pid=83311
base=0x102a0c000
container=0x1596c9a00
inner1=0x600006b28410
Deck 2 field=0x600006b284ec
inner2=0x600006b284e0
offset=inner1+0xd0
playing rate≈44.1 kHz
paused delta=0
cue reset≈50 ms
container+0x480/+0x488 rejected as flat pos=1
```

Session 2:

```text
pid=88640
base=0x100548000
container=0x10cd1e200
inner1=0x6000070e5520
Deck 2 field=0x6000070e84ec
inner2=0x6000070e84e0
offset=inner1+0x2fc0
scan rate=44102.4 samples/sec
playing rate=44158.0 samples/sec
paused delta=0
container+0x480/+0x488 rejected as flat pos=1
```

Full bridge runtime log:

```text
deck2 candidate B(container-0x270+0x78): 0x6000000916e0
ObjC zone scan: pos=inner1+0x2fcc inner_ptr=inner1+0x2fc0
deck2 candidate C(zone): 0x6000070e84e0
deck2 candidate 0x6000070e84e0 PASS: rate=44045 samples=57 ms=21812
deck2 inner committed: 0x6000070e84e0
```

Conclusion:

```text
Deck 2 inner pointer is session-dependent.
Do not hardcode inner1+0xd0 or inner1+0x2fc0.
Runtime behavioral scan is required.
```

