# Opus 4.8 — Laser Mute pad wiring investigation

**Target model:** Claude Opus 4.8 · **Effort:** xhigh · Set a large max-output-token budget (~64k).

## Mission
Determine whether the Stream Deck **"Laser Mute"** pad on the rb_ss_bridge_v2 bridge is actually wired to mute the lasers, or whether a MIDI-note mismatch makes it a no-op. Read-only investigation. Report findings; do not change anything.

## Why it matters / who it's for
The operator noticed the Laser Mute pad physically emits **MIDI note 44** (on channel 3), but the bridge config (`config/led_look_director.json`, key `laser_mute_note`) says **59**. If the deck sends 44 and the bridge listens for 59, the button does nothing. This report tells the operator whether the button works, and if not, hands Codex the smallest correct fix. The audience is the operator (plain-language verdict) plus a Codex-ready fix note.

## Deliverable (answer in chat, every item with a file:line citation or an explicit "unknown, because…")
1. **What the deck SENDS** for Laser Mute: exact MIDI note + channel, and *where that number is decided* — `NOTE_BASE + key`, a feedback-provided note, or config.
2. **What the bridge LISTENS for** as the laser-mute action: exact note + channel, and where that binding is built.
3. **Do they agree?** If not, state the exact mismatch (note and/or channel).
4. **Full press→action path:** from "MIDI note arrives" to "lasers go dark" — which module, which state (pack blackout mask vs laser-director emergency blackout vs `soundswitch_midi_input` `blackout_held`), and whether the behavior is momentary-hold or toggle.
5. **Verdict:** does pressing Laser Mute mute the lasers? One of: *confirmed working* / *confirmed no-op* / *cannot determine from code* (and the exact live observation that would settle it).
6. **If broken:** the smallest correct fix, described precisely **for Codex to implement — do NOT implement it yourself and write no production code changes.**

## Evidence packet (verify every item against current code — these notes were assembled fast and were wrong twice; code wins over these notes)
- `streamdeck/streamdeck_midi.py`: `NOTE_BASE = 36` (~line 36); `CHANNEL = 2` meaning MIDI channel 3 (~line 35, comment "chans 1-2 are the lasers'"). The `controls` table lists `laser_mute` at physical key 8 (~line 241). `_control_row` (~line 185) pulls a control pad's note from `feedback["controls"][key]["note"]`. A hardcoded **sample/demo** layout near lines 905–918 lists `laser_mute` note 59 — this is a sample, **not** necessarily the live value; do not trust it (it already misled once).
- `config/led_look_director.json` (~line 195): `laser_mute_note: 59`. `led_config.py` builds a MIDI binding whose `data_byte` comes from `laser_mute_note`.
- `led_palette_control.py` (~line 409): the `laser_mute` feedback entry reflects `laser_blackout`; `get_laser_blackout` is wired at `state_manager.py:555` to `pack_status_snapshot["blackout"]`.
- Action-side candidates to trace: `soundswitch_midi_input.py` `blackout_mask` (note-on holds `blackout_held`, note-off releases); `state_manager.py:1505` `Ev.LASER_BLACKOUT → laser_director.set_emergency_blackout(True)`; the drop-presentation darkness guard reads `laser_masked` / `midi_input.snapshot().blackout_held` at `state_manager.py:2332`.
- Operator observation (**assumed**, unverified in code by the note author): the pad emits note 44.

## Key questions to resolve
- Does the bridge **write** the laser_mute note into the deck feedback (so the deck emits whatever config says, e.g. 59), or does the deck **fall back** to `NOTE_BASE + key` (44) when feedback lacks a note? Trace `led_palette_control` feedback build (`publish_feedback` / `_control_payload`) to see exactly what note it emits for `laser_mute`, and what happens when a control has no configured note.
- On which **channel** does the bridge listen for the laser_mute binding, and does it match the deck's channel 3?
- Is there **more than one** laser-mute path (pack blackout vs laser-director emergency vs SoundSwitch-direct), and which one (if any) does this pad actually reach?

## Source-of-truth order
Executable code > tests > config examples > this evidence packet > the note author's prose. If a claim can't be verified in code, mark it **unknown** — do not guess.

## Scope / boundaries
- **READ-ONLY.** Do not modify any file, config, or runtime. Do not start, stop, restart, or otherwise touch the bridge process. Do not run the bridge.
- **Investigation + analysis only.** Opus reasons and reports; it does not implement. If a fix is warranted, describe it for Codex — write no production code changes.
- Tools allowed: shell for `rg`/`grep`/reading files, and file reads. No network. No hardware.
- Do **not** expose hidden chain-of-thought. Evidence-tied findings, claim labels, and a verdict only.

## Claim discipline
Label every load-bearing claim **confirmed / assumed / unknown**, each tied to a `file:line` or command output.

## Success criteria (falsifiable)
- All 6 deliverable items answered, each with a `file:line` citation or an explicit "unknown, because…".
- The **note-44-vs-59** question resolved to exactly one of: {they reconcile via X}, {genuine mismatch — pad is a no-op}, {cannot tell from code — needs live test Y}.
- A single clear one-line verdict on whether the button works.
