---
doc_status: current
truth_level: handoff-report
last_verified_commit: c1402a6
last_verified_date: 2026-07-09
validation_scope: >
  Kickoff brief for the HAZE AUDITION operator session (Fable, MEDIUM effort, tmux
  `haze`, spawned 2026-07-09 morning on operator directive). Operator-attended live
  look pass with haze in the room: burn-down tune-or-kill, chase ladder visibility,
  pre-chorus breath, darkness ladder in haze. Read-mostly; config knob changes only on
  the operator's explicit in-session word.
---

# Haze audition — session kickoff (2026-07-09)

You are the **haze audition runner** (Fable, MEDIUM). Brandon attends with haze in the
room and the bridge running (HE starts it via the menubar — never you). You run the
checklist, capture his verdicts verbatim, and note wall-clock times of anything off.

## Context (all landed last night, software-tested only — this session IS the live gate
for the laser-side look)
- Burn-down (AWR-162 C) is **ENABLED as of this morning** (operator word; executive
  flipped `f2.impact_burndown.enabled=true`, loader-verified): at each drop hit, CH9
  color speed starts at the tier's max and eases down over `ease_beats: 8`.
- Per-tier chases (AWR-170 B): red/white menus chase 100 (standard) → 116 (intense)
  → 140 (monster).
- Pre-chorus breath (AWR-170 D.2): lasers dark 4 beats before every chorus phrase;
  LEDs stay up (`f2.pre_chorus_laser_beats: 4`).
- Darkness ladder (F2): snap / 1 / 2 / 4 / 8 / 16 beats + balloon; lasers mirror the
  emphasis blackouts (AWR-162 D).

## The checklist (walk him through it, one item at a time, verdicts verbatim)
1. **Burn-down feel per tier** — does the speed-easing land? Verdict per tier:
   KEEP / RETUNE (`f2.impact_burndown.ease_beats`, currently 8) / KILL (flip enabled
   back to false). Any change: his explicit word, then edit the live config, loader-
   verify, and note that it takes effect per the config's reload semantics (bridge
   restart via HIS menubar if needed).
2. **Chase ladder in haze** — with beams visible, can he SEE the 100→116→140
   aggression steps across small/standard/intense/monster drops?
3. **Pre-chorus breath** — the 4-beat laser cut before choruses: visible, musical,
   right length? (Knob: `pre_chorus_laser_beats`; 0/absent = off.)
4. **Darkness ladder in haze** — blackouts and balloons read differently with beams;
   any length that feels wrong, note track + wall-clock mm:ss.
5. **Anything broken** — stuck-dark, wrong colors, missed drops: capture wall-clock
   time immediately; correlate later against `~/Library/Logs/rb_ss_bridge/current.jsonl`
   (ts = epoch). Triage load/CPU first per standing rule.

## Rules
- Live-mixing safety first: never start/stop/restart the bridge yourself; after HIS
  menubar start verify exactly one bridge process
  (`pgrep -f 'rb_ss_bridge_v2$' | wc -l` → 1, frame-engine child separate).
- Config edits ONLY on his explicit in-session word, one knob at a time, loader-verify
  after each; live config is gitignored — never commit it.
- His verdicts and any timestamped bugs go to a short findings note in
  `docs/research/` at session end (registered, checks green); tuning rounds that need
  code go through the executive seat (tmux `superman3`), not this lane.
- Chat is the surface: talk him through everything plainly; no jargon walls.
