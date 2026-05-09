# rb_ss_bridge_v2

Status: CURRENT AUTHORITATIVE

`rb_ss_bridge_v2` is a realtime Rekordbox to SoundSwitch bridge. It reads
Rekordbox state, reconciles guarded direct-memory signals with TimecodeLink and
MTC fallbacks, and speaks VirtualDJ-shaped OS2L to SoundSwitch.

Start here:

1. `docs/current_architecture.md` - 15-minute current-state overview.
2. `docs/bridge_design.md` - detailed current design and invariants.
3. `docs/runtime_invariants.md` - rules that should not be broken during code
   changes.
4. `docs/doc_index.md` - classification of every markdown file.

Historical rollout notes and investigation logs are preserved under
`docs/history/` and `docs/validation/`. They are evidence, not the primary
description of current behavior.

Run:

```bash
cd /Users/bbui
python3 -m rb_ss_bridge_v2
```

The local launcher scripts currently default to guarded direct B1-B6 paths with
TimecodeLink and MTC retained as fallbacks.
