---
doc_status: draft
truth_level: design-intent
last_verified_commit: 955552f
last_verified_date: 2026-07-04
validation_scope: software-only
---

# Laser Color — Design Spec (pre-handoff)

> **Status: PLANNED / DESIGN-INTENT. Not implemented.**
> Roles: Claude authors this spec (planning); **Codex/Fable implements the bridge code**
> once the spec is finalized. Fable will review and expand this design before handoff.
> Per AGENTS.md §1, **code wins over this doc** — verify every claim against current code.

This is a forward-looking design doc. It is **not** current truth and is not in the active
work registry yet. Claims are labelled **confirmed / assumed / unknown**; file:line evidence
is in Part F.

---

## Part A — Goal & scope

Add laser **color** to the bridge, coordinated with the LED color engine, without changing
any other laser behavior.

**Foundational change since the original draft (2026-07-04):** the bridge now renders laser
DMX **itself** via the SoundSwitch exporter / pack player. **SoundSwitch is fully out of the
live path** — it is used only to *author* the pack offline. This kills the original
"inline-overlay on a live SoundSwitch DMX frame" architecture entirely (old Part C). The
bridge owns the whole laser frame now, not two color channels on someone else's frame.

In scope:
- **Non-scripted tracks** (active deck playing an autoloop): laser color **follows the LED
  color engine's palette** (LED engine stays the color authority), re-anchored on
  smart-phrasing phrase boundaries.
- **Scripted tracks** (active deck playing a scripted track): laser color comes from the
  **track's own SoundSwitch cues, already baked into the pack**; the color engine **stands
  down** and lets the pack's CH8/CH9 pass through.
- Laser color **effects / speed / gradient / water-flow**, layered on the base color family.

Out of scope (do not redesign away):
- Firing a laser phrase decision **every phrase** is acceptable.
- Pattern / movement / intensity come from the pack render. Breakdown/groove/buildup autoloops
  stay dark; only drop / post-drop autoloops carry visible laser content.
- The MIDI scene path and existing laser policy/execution split are untouched by the *color*
  feature; the *blackout re-wire* (Part D) is the one behavioral change to laser output.

## Part B — Architecture (locked, code-grounded)

**Ownership.** SS out of the live laser path. The bridge's pack player (`LaserPackPlayer`)
produces the whole 19-channel laser DMX frame. Two producers write one frame:

```
pack render (position/movement/intensity, leaves CH8/CH9 open on autoloops)
        │
        ▼
   [MERGE] ── color engine writes CH8/CH9 ──▶ one frame ──▶ laser DMX out
        ▲
   blackout: absolute override ABOVE the merge (zeros ALL 19 ch when active)
```

- **Two separate producers stitched by a merge step** (operator preference; Fable may revisit
  the exact seam). Pack render owns movement channels; the color engine owns CH8/CH9. The merge
  emits the single frame that ships.
- **Color layer.** `resolved_RGB → (CH8, CH9)` pure mapper. Non-scripted: sample the LED color
  engine at each phrase anchor, map to the fixture's color set. Scripted: engine stands down.
- **Runs on its own thread**, never in the 200 Hz `StateManager` push loop (runtime invariant:
  no blocking I/O in the push loop).
- **Blackout is an absolute override above the color layer** — *confirmed*
  (`soundswitch_laser_player.py:202-203,423-424`): when blackout is set, the frame is
  `ZERO_FRAME` regardless of what CH8/CH9 the color engine wrote. Color can never defeat a
  blackout, and there is no color/blackout ordering problem.

**Scripted vs non-scripted gate (locked).** The merge decides per active deck:
- active deck = **autoloop** → color engine **injects** CH8/CH9.
- active deck = **scripted track** → color engine **stands down**; pack cue color passes through.
- **Safe default: when unsure, do NOT inject** — never stomp an authored scripted color.

## Part C — Blackout (locked, code-grounded)

Blackout has two sources; with SS out they are **separate mechanisms in a bridge-owned
priority**, which is what makes the old SoundSwitch "undo-on-release" bug structurally
impossible here.

**1. Smart-drop / smart-breakdown auto-blackout.**
- *Today:* emits a MIDI note (ch0/note0, IAC Bus 1) that was consumed by live SoundSwitch.
  In pack-mode this note is **silently dropped** — `PackOutputBackend.trigger()` resolves only
  by `scene_name → autoloop identity`, and the blackout message carries no `scene_name`, so it
  misses and no note is ever emitted (*confirmed*, `laser_output_backend.py:169-176`). So
  smart-drop blackout currently **does nothing** to the bridge's own DMX output. This is a
  documented open gap (`docs/subsystems/laser.md:69`).
- *Design:* smart-drop/breakdown blackout calls the pack player's **frame-level blackout
  directly** (`set_masks(blackout=…)`), bypassing `PackOutputBackend.trigger()`'s scene
  resolution — the bridge zeros the DMX itself, no MIDI note, frame-accurate. Driven by the
  executor's existing **owner-refcount** (`_mask_owners`) as the source of truth.

**2. Manual operator blackout (laser pad).**
- The pad sends its own note (**ch1/note0** per operator; Fable to confirm), *distinct* from
  smart-drop's ch0/note0. Received by the **bridge's MIDI input**, classified as a
  `blackout_mask` binding, drives the same frame-level blackout **as a separate owner**.

**Coexistence / the anti-undo rule.**
- Smart-drop's release clears only *its* owner; a manually-held blackout is a different owner
  and **survives**. The pack player's blackout is already refcounted (`any(...)` across held
  bindings, not last-writer-wins) — *confirmed* (`soundswitch_midi_input.py:308-314,625`).
- **Do NOT port the C2 artifact** — `clear_pending_blackout()` → `_release_all_masks()` releases
  *every* owner unconditionally (`laser_executor.py:79-82,358-362`). That is the one place
  SS-style "release everything" survives; porting it into the frame-level player would
  reintroduce the undo bug. The two refcount systems (MIDI-input bindings vs executor
  `_mask_owners`) must be OR'd at the frame level so neither release clears the other's hold.

**Exported blackout static look (slot 31 "BLACK OUT").**
- *Confirmed exported*: slot 31 = all-zero frame; its note binding (ch0/note0 → `blackout_mask`)
  is in the pack's `selection_map.json`, loaded to a `PackMidiBinding`
  (`soundswitch_pack_loader.py:358-368`).
- **Fate:** smart-drop **bypasses** it (direct frame-level blackout gives the identical all-zero
  result). The **binding row** still serves the *manual* pad path. The all-zero **content** is
  redundant with the frame-level override but harmless — leave it; re-export regenerates it.

**Timing knobs are preserved.** Beat counts (e.g. smart-drop 4→16 beats, breakdown length cap)
live in the smart-drop/breakdown **decision layer**, not in the pack and not in the actuation.
Editing them changes *when/how long* blackout holds; the frame-level actuation just follows.
Nothing about timing is baked into the pack export. (Longer holds are *more* reliable here than
in the old MIDI-to-SS path, which exposed a long hold to the undo bug for its whole window.)

## Part D — Fail-open & live safety

- **Fail-open = color drops to neutral, pack keeps rendering.** If the color engine errors,
  stalls, or hits an unmapped color, the merge writes nothing to CH8/CH9 and ships the pack
  frame with those channels neutral. Lasers keep moving; only color is lost. **Not** "no
  lasers." The merge must **never block** on the color engine.
- Blackout is the absolute override (Part B), so injected color can never defeat a blackout.
- Own thread, isolated from the 200 Hz push loop.
- After any bridge restart: `pgrep -f rb_ss_bridge_v2 | wc -l` must be `1`.
- **Live-safety flag:** blackout re-wire is laser-blackout / runtime-invariant territory —
  re-verify on a high tier before any live show and before wiring `LaserSceneExecutor` into the
  frame-level `LaserPackPlayer`.

## Part E — Open items for Fable

1. **RGB→CH8/CH9 mapper (build, not reuse).** The exporter does **not** contain color-encoding
   logic — scripted color rides in SS cues that already set it; the exporter just serializes
   cue values. So the non-scripted mapper is a genuine new build and needs the CH8/CH9 color
   encoding (what value ranges produce which colors / effects / speed). Fable resolves how to
   obtain it (VLN captures / decoder / fixture profile) — *unknown, needs verification*.
2. **Scripted stand-down mechanism.** Gate is "active deck = autoloop vs scripted track"
   (locked). How the merge reads active-deck kind at frame time — Fable specs; verify against
   the active-deck resolver / scripted-track path — *assumed path, unverified*.
3. **Manual pad note.** Operator says pad = ch1/note0 (distinct from smart-drop ch0/note0);
   Fable confirms against the actual pad/pack wiring so the "separate owner" separation holds —
   *unknown until confirmed*.
4. **Pre-drop blackout: full-off vs selectable look (operator decision, defaulted).** Currently
   full-off (slot 31 all-zero). Design assumes **boolean blackout = full-off**. If a non-black
   pre-drop look is ever wanted, blackout stops being a boolean and becomes a *look-select* —
   Fable should raise this before implementing if it matters. **Default: full-off.**

## Part F — Evidence (file:line, this HEAD `955552f` / prior agent read)

- Smart-drop note config (ch0/note0, IAC Bus 1, no `scene_name`): `config/laser_director.json`
  manual_commands; emit path `laser_executor.py:296,327`, message build
  `laser_config.py:803-819`.
- Pack-mode drops the note (scene_name resolution only): `laser_output_backend.py:169-176`.
- Frame-level blackout override / layer compositing: `soundswitch_laser_player.py:191-226`
  (`apply_layers`), blackout override `:202-203,423-424`.
- Blackout refcount (any-of held bindings, not last-writer): `soundswitch_midi_input.py:308-314,625`.
- Executor owner-refcount: `laser_executor.py:66,308-321,342-356`. **C2 unconditional wipe (do
  not port):** `laser_executor.py:79-82,358-362`.
- Exported blackout binding + slot 31 all-zero look: pack `selection_map.json` /
  `static_looks.json` (slot 31 "BLACK OUT"), loaded `soundswitch_pack_loader.py:358-368`.
- Smart-drop/breakdown hold/release call sites: `smart_rearm.py:244,274,289`.
- Backend selection (pack vs MIDI, runtime-state dependent): `__main__.py:413-421,508,554`.
- Documented open gap this design closes: `docs/subsystems/laser.md:69`.
- LED color engine (color source for non-scripted): `led_color_engine.py`, `led_models.py`
  (`LedColorEngine.resolve_color(...)`).

## Change-contract note

Design-only; changes no runtime behavior, so no `change_contracts.yml` entry yet. Per AGENTS.md
§7, **before** implementation begins, add/extend the `laser` contract (and likely a new
`laser_color` entry) with its `docs_update` list, then edit code.
