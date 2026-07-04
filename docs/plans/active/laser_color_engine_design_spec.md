---
doc_status: draft
truth_level: design-intent
last_verified_commit: bd96b32
last_verified_date: 2026-07-04
validation_scope: software-only
---

# Laser Color — Design Spec (pre-handoff)

> **Status: PLANNED / DESIGN-INTENT. Not implemented.**
> Roles: Claude authors this spec (planning); **Codex implements the bridge code** once the
> spec is finalized. **Fable reviewed (Phase 1) and expanded (Phase 2) this design on
> 2026-07-04** with operator answers folded in; awaiting operator approval (gate 2).
> Per AGENTS.md §1, **code wins over this doc** — verify every claim against current code.

This is a forward-looking design doc. It is **not** current truth and is not in the active
work registry yet. Claims are labelled **confirmed / assumed / unknown / operator-decided**;
file:line evidence is in Part F.

**Implementation gate:** the CH8/CH9 encoding chart (Part E #1) **gates Phase 3 implementation
of the color mapper's value table only** — the operator will produce its inputs later. All other
parts (merge seam, blackout re-wire, sampling plumbing) are implementable without it.

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
  smart-phrasing phrase boundaries. The engine **deliberately overwrites** the pack's authored
  CH8/CH9 on these frames (operator-confirmed 2026-07-04; see Part B — the channels are NOT
  empty in the pack).
- **Scripted tracks** (active deck playing a scripted track): lasers follow **whatever is
  authored for that scripted track** — the track's own SoundSwitch cues, already baked into
  the pack; the color engine **stands down** entirely (operator 2026-07-04: scripted tracks
  run their own timeline; LEDs render only breakdown/buildup windows there; lasers stay
  authored throughout).
- Laser color **effects / speed / gradient / water-flow** (CH8/CH9), layered on the base
  color family.

Out of scope (do not redesign away):
- Firing a laser phrase decision **every phrase** is acceptable.
- Pattern / movement / intensity come from the pack render. Breakdown/groove/buildup autoloops
  stay dark; only drop / post-drop autoloops carry visible laser content. *(operator-stated;
  not re-verified against pack bytes)*
- **CH11 (strobe) is untouched everywhere** — operator-decided 2026-07-04: strobe stays baked
  into authored cues; whether the bridge may ever control laser strobe is a future decision.
  The color engine writes CH8/CH9 only. (Note `CONTROL_CHANNELS = {8, 9, 11}` — CH11 shares
  the persistent-control behavior, `soundswitch_laser_player.py:25,109-111`.)
- The MIDI scene path and existing laser policy/execution split are untouched by the *color*
  feature; the *blackout re-wire* (Part D) is the one behavioral change to laser output.

## Part B — Architecture (locked, code-grounded)

**Ownership.** SS out of the live laser path. The bridge's pack player (`LaserPackPlayer`)
produces the whole 19-channel laser DMX frame (`CHANNEL_COUNT = 19` — *confirmed*). Two
producers write one frame:

```
pack render (position/movement/intensity + AUTHORED CH8/CH9)
        │
        ▼
   [MERGE, inside render(), autoloop path only]
        │   color engine OVERWRITES CH8/CH9 on autoloop frames;
        │   scripted frames pass through untouched
        ▼
   static-override layers apply over the merged frame (existing apply_layers)
        ▼
   blackout/emergency: absolute override ABOVE everything (ZERO_FRAME)
```

- **The pack authors CH8/CH9 on autoloops too** — *confirmed, corrects the earlier draft*:
  922 CH8/CH9 cue writes across the 42 autoloop docs, including bridge-active ones
  (SSAutoLoop13 CH8=137/CH9=214, SSAutoLoop14/15/16/17/4/46/47/48/50 …). The merge is a
  **deliberate overwrite** of authored autoloop color with the LED-following color
  (operator-confirmed 2026-07-04), not a fill of empty channels. Those authored values double
  as calibration anchors for the encoding chart (Part E #1).
- **Merge seam (pinned).** Injection happens **inside `LaserPackPlayer.render()`, in the
  autoloop base path only** (`_autoloop_base`, after a successful `render_autoloop_frame`).
  This one placement yields, for free:
  - **blackout/emergency safety** — `render()` returns `ZERO_FRAME` before any base render
    when a mask is held (:422-424), and `apply_layers` re-checks (:202-203), so injected
    color can never reach a blacked-out frame. Injecting *after* `player.render()` returns
    would defeat blackout — forbidden.
  - **scripted stand-down** — scripted frames render via `_scripted_base`, which the merge
    never touches (closes old open item #2).
  - **"unsure → do NOT inject"** — every diagnostic/error path (stale/ambiguous authority,
    missing phase, unverified parity, reload-wait, missing selection) returns before
    injection, so an uncertain frame ships authored/zero content, never engine color.
  - **static-override precedence** — held Static Override layers apply *after* the merge
    (:443-457) and keep winning over engine color, preserving the manual-overlay contract.
  - The push-tick crash path (`_push_tick` submits a direct ZERO frame on any raise,
    `state_manager.py:2092-2107`) is untouched.
- **Color layer = async producer + in-loop merge** (corrects the earlier "runs on its own
  thread" wording). The pack render **runs inside the 200 Hz push loop** (`_push_tick` →
  `_drive_pack_output` → `render()`, `state_manager.py:2092-2107,2415,2635` — *confirmed*);
  the invariant bans blocking I/O there, not pure compute. So: the **color computation/
  sampling** (LED-engine sampling at phrase anchors, RGB→CH8/CH9 mapping, white-moment edges)
  runs off-loop and publishes an **atomic immutable (CH8, CH9) snapshot**; `render()` reads
  the snapshot non-blockingly at merge time. No locks, I/O, or allocation storms on the loop.
- **Color source accessor (new, small).** There is **no** "current RGB now" API on the LED
  engine today — `resolve_color` (`led_color_engine.py:507`) needs full per-cue context, and
  `snapshot()` returns a palette *name* (corrects the earlier Part F citation to
  `led_models.py`, which contains neither). The design adds a public engine accessor
  returning the current anchor RGB (derived from `_anchor_p`/`_p_to_rgb`), called on the
  StateManager thread and published into the color producer's snapshot.
- **Fixed-color model + effect taxonomy (operator 2026-07-04).** The laser has **no RGB wheel** —
  CH8 selects from a fixed color set: **Red, Green, Blue, Cyan, Yellow, Purple, White**, and above
  the fixed colors CH8 carries **effect families** (operator-stated): color-change effects, RGB
  color-change effects, an **"original color change"** effect, **various combinations of
  flowing-water effects**, and a **color-gradient effect**. **CH9 = color speed** (rate of the
  active CH8 effect). So the mapper is a **nearest-of-7 quantizer** over the LED anchor RGB for
  the base color, plus an optional effect-selection tier — table-driven config (CH8 value per
  fixed color + per-family range boundaries + CH9 speed curve) so chart updates never touch code.
  Notes: the LED hue band excludes yellow/orange, so nearest-color will rarely/never select
  Yellow; White is reserved for the white-moment signal and `white_sand` (Part E #5-6), never
  nearest-color output.
- **Per-drop color variation comes for free** — the LED engine already varies color per drop
  section (`drop_section_index`, per-cue seeded variation), and this design samples the LED engine
  at phrase anchors, so each drop's laser color follows automatically (quantized to the fixed set).
  A drop landing mid-override-fade (Stream Deck doc C.2) samples the blended color — acceptable.

**Scripted vs non-scripted gate (locked, now structural).** The player's own selection type
decides: `_AutoloopSelection` → merge injects; `_ScriptedSelection` → untouched. No separate
active-deck read at frame time is needed; the selection is already deck-authoritative.
**Safe default: when unsure, do NOT inject** — automatic on every non-autoloop path.

## Part C — Blackout (locked, code-grounded)

Blackout has two sources; with SS out they are **separate owner systems in a bridge-owned
priority**, which is what makes the old SoundSwitch "undo-on-release" bug structurally
impossible here. **The separation is by OWNER, not by MIDI note** — corrected 2026-07-04:
the "distinct notes" claim in the earlier draft was a numbering-convention artifact.
Smart-drop's configured note (`config/laser_director.json` `manual_blackout_on`:
`channel: 1, note: 0`, 1-based) is **wire ch0/note0 on IAC Bus 1** (`midi_output.py:252`
subtracts 1), which is the **same** wire note as the pack's `blackout_mask` binding
(`manual_blackout`: `channel_zero_based: 0, data_byte: 0` — *confirmed from the loaded pack*)
that the operator's laser-pad-web blackout (note 0, breakdown section) triggers. This works
anyway because in the target design **smart-drop stops emitting MIDI entirely** (below).

**1. Smart-drop / smart-breakdown auto-blackout.**
- *Today:* emits a MIDI note that pack-mode silently drops — `PackOutputBackend.trigger()`
  resolves only by `scene_name`, and blackout messages carry none (*confirmed*,
  `laser_output_backend.py:169-176`; `laser_config.py:803-819` builds them without
  `scene_name`). So smart-drop blackout currently **does nothing** to the bridge's own DMX.
  Documented open gap: `docs/subsystems/laser.md` §runtime-flow "Blackout-mask migration"
  bullet (~:69), which also requires the masking *decision* be **ported, not deleted**, and
  points at the deferred reference design
  `docs/archive/plans/laser_smartnet_mask_preserve_spec.md`.
- **Worse (found in review): the owner-refcount itself never latches in pack mode** —
  `hold_blackout_mask` adds the owner, then **discards it when `backend.trigger()` returns
  False** (`laser_executor.py:330-340`), which it always does in pack mode. It also
  early-outs when `smart_drop_mode != "blackout_mask"` (:325) or `manual_blackout_on` is
  unset (:327-329). So `_mask_owners` is permanently empty in pack mode today.
- *Design:* smart-drop/breakdown blackout drives the pack player's **frame-level blackout**
  directly — no MIDI note, frame-accurate — with the executor's owner-refcount
  (`_mask_owners`) as its source of truth, **after two required changes**:
  1. **Decouple owner bookkeeping from MIDI-send success**: hold/release must latch owners
     unconditionally (the note send becomes MIDI-backend-only behavior, absent in pack mode).
  2. **The OR happens at the single existing mask writer** — `state_manager.py:2361-2364`,
     the only `set_masks` call site, which today computes `blackout` from the MIDI-input
     snapshot alone and **rewrites it every push tick** (a naive extra `set_masks` call
     elsewhere would be stomped within ~5 ms). New computation:
     `blackout = (midi_input_blackout AND input_healthy) OR executor_mask_owners_active`.
     The SS-present clear path (:2387) keeps clearing only the MIDI-input contribution's
     latch state; it must not be able to wipe a live executor-side hold silently — Codex
     spec pins the exact behavior + test.

**2. Manual operator blackout (laser pad).**
- **Already works end-to-end today** (*confirmed*, stronger than the earlier draft): laser
  pad web note 0 → IAC wire ch0/note0 → pack `blackout_mask` binding →
  `SoundSwitchMidiInputAdapter` refcounted `_blackout_held` (:280-314) → group `any(...)`
  merge (:621-635) → `state_manager.py:2350-2364` → `player.set_masks(blackout=True)` →
  `render()` ZERO_FRAME. Overlay-trust gates it (`input_healthy`, :2352-2361). Nothing to
  build here; the design must simply **not break it**.
- The Stream Deck sidecar's "BLACK OUT" row is dead weight: the deck script filters non-ch2
  rows out (`streamdeck_midi.py:85`), so it never renders as a pad; the deck's working dark
  pad is "OFF" (ch2/note43 → static look slot 16, an all-zero **layer** — *confirmed* — which
  loses to blackout and rides overlay-trust, a different, weaker mechanism than blackout).

**Coexistence / the anti-undo rule.**
- Smart-drop's release clears only *its* owner; the manual hold lives in a **different
  system** (MIDI-input binding refcount) and survives. Both systems are refcounted
  (`soundswitch_midi_input.py:308-314,625`; `laser_executor.py:323-356`) — *confirmed*.
- **The manual pad must NEVER be routed through executor `_mask_owners`**: the executor's
  owner set is wiped by `reset_runtime_state` → `clear_pending_blackout` →
  `_release_all_masks` on **every** lifecycle boundary — master change, active track load,
  stop, resume (`state_manager.py:1419,1462,1504,3517,3551`; `laser_executor.py:97,79-82,
  358-362`) plus five direct clear sites (`state_manager.py:1225,1232,3244,3263,3558`). A
  manual hold there would vanish at the next track load. This is why the two-system split is
  load-bearing, not stylistic.
- **Do NOT port the C2 artifact** — `clear_pending_blackout()` → `_release_all_masks()`
  releases every owner unconditionally (`laser_executor.py:79-82,358-362`). In the frame-level
  design those wipe sites become **frame-blackout releases for the smart side**; the Codex
  spec must enumerate them (list above), confirm each is a legitimate smart-side release
  (track boundaries end breakdown covers today — expected), and add the test:
  **a manually-held blackout survives every one of them.**

**Exported blackout static look (slot 31 "BLACK OUT").**
- *Confirmed*: slot 31 content is all-zero; the `manual_blackout` binding row (IAC wire
  ch0/note0 → `blackout_mask`, target slot 31) loads via `soundswitch_pack_loader.py:358-368`.
- **Fate:** smart-drop **bypasses** it (direct frame-level blackout, identical all-zero
  result). The **binding row keeps serving the manual laser-pad path** (it is that path,
  Part C.2). The all-zero content is redundant but harmless; re-export regenerates it.

**Timing knobs are preserved.** Beat counts (smart-drop 4→16 beats, breakdown length cap)
live in the smart-drop/breakdown **decision layer** (`smart_rearm.py:244,274,289` hold/release
call sites — *confirmed*), not in the pack and not in the actuation. Editing them changes
*when/how long* blackout holds; the frame-level actuation just follows. (Longer holds are
*more* reliable here than the old MIDI-to-SS path, which exposed a long hold to the undo bug
for its whole window.)

## Part D — Fail-open & live safety

- **Fail-open = authored color passes through; pack keeps rendering.** If the color producer
  errors, stalls, or hits an unmapped color, it publishes no snapshot (or a stale one is
  ignored via its seq/age field) and the merge **leaves the pack's authored CH8/CH9
  untouched** — exactly today's output. Lasers keep moving with authored color; never "no
  lasers." The merge must **never block** on the color engine. (Corrected from "write
  nothing/neutral": per Part B the channels are authored, so pass-through IS the neutral.)
- Blackout is the absolute override above everything (Part B seam); injected color can never
  defeat it by construction.
- Color computation off the push loop; merge is pure in-loop compute (Part B).
- After any bridge restart: `pgrep -f rb_ss_bridge_v2 | wc -l` must be `1`.
- **Live-safety flag:** the blackout re-wire is laser-blackout / runtime-invariant territory —
  re-verify on a high tier before any live show, before wiring `LaserSceneExecutor` owners
  into the frame-level mask writer, and cover Part C's survival tests in software first.

## Part E — Open items

1. **CH8/CH9 encoding chart (operator-gated; blocks the mapper table ONLY).** The exporter
   contains no color-encoding logic (scripted color rides in cues; the exporter serializes
   values), so the RGB→CH8/CH9 mapper is a genuine new build over an empirical chart.
   **Operator decision 2026-07-04: deferred — he will produce the inputs later; this gates
   Phase 3 implementation of the mapper's value table, not the rest of the feature.** Inputs,
   in order of leverage:
   - **Fixture profile** — the operator HAS it; it should yield the CH8 segment map outright.
   - **Label existing pack values** — the pack already uses CH8 ∈ {0,10,17,21,24,25,28,69,71,
     77,90,137,165,172,255} and CH9 ∈ {0,86,115,124,145,203,214,238,255} (autoloops alone;
     scripted cues add more); labeling what a handful of known cues display anchors the chart
     without hardware risk.
   - **Live visual validation** — required regardless for the **ambiguous CH8 multi-color
     effects** (operator: only knowable visually); a supervised sweep with the beam contained,
     scheduled by the operator.
   The mapper is table-driven config, so the chart landing later costs no rework. **The
   fixed-color model + effect taxonomy (Part B) shrinks the ask to:** one CH8 value per fixed
   color (Red, Green, Blue, Cyan, Yellow, Purple, White); the **range boundaries of each effect
   family** — color-change, RGB color-change, "original color change", the flowing-water
   combinations, color gradient (the ambiguous part needing live visual validation); and the
   **CH9 color-speed** value curve (what values are slow/fast; whether 0 freezes).
2. **Scripted stand-down mechanism — RESOLVED.** Structural: injection lives in the autoloop
   render path only (Part B merge seam); scripted/diagnostic/idle paths never inject.
3. **Manual pad note — RESOLVED (corrected).** Same wire note as smart-drop's old note
   (IAC ch0/note0); manual pad = laser pad web note 0 (breakdown section), already working
   end-to-end via the pack `blackout_mask` binding (Part C.2). Owner separation comes from the
   two-system split, not note distinctness. Smart-drop stops using MIDI, dissolving the
   collision.
4. **Pre-drop blackout: full-off (operator default stands).** Boolean blackout = full-off
   (slot 31 all-zero equivalent). If a non-black pre-drop look is ever wanted, blackout stops
   being a boolean and becomes a look-select — raise before implementing if it matters.
5. **White-moment mirroring (operator-decided 2026-07-04).** Lasers go **white during the LED
   engine's cue-mandated white moments** — drop white-strobe (`govee_frame_renderer.py`
   `drop_white_aggressive`:505), white buildups (`buildup_white_*`:874-953), post-drop shatter
   (:515), and the reserved slot-5 firework accent. No such signal exists anywhere today
   (*confirmed* — white lives only inside renderer template functions as raw RGB). Design: the
   LED dispatch path publishes a **"white moment" boolean** (template-name allowlist + firework
   accent flag) into the color producer's snapshot; the mapper emits CH8 white while it holds.
   Non-scripted only; scripted-track white already rides the pack cues. *(Exact publish point —
   renderer template selection vs dispatch policy — is a Codex-spec detail; the source data is
   the selected template name.)*
6. **`white_sand` palette → laser white (operator-decided 2026-07-04).** The Stream-Deck-only
   `white_sand` palette (see `streamdeck_palette_control_design_spec.md`) maps, for lasers, to
   **CH8 white** — sustained until the palette's track/lock rules revert it. One shared
   palette **name**, per-engine value. Exact CH8 white value comes from the chart (#1). On
   scripted tracks `white_sand` affects only the breakdown/buildup LED windows; lasers stay
   authored (operator 2026-07-04).
7. **CH11 strobe — deferred by operator (2026-07-04): the bridge does not touch it now**;
   whether the bridge may ever control laser strobe is a future decision. The chart work in #1
   should still record CH11 semantics when convenient.
8. **Post-drop settle (operator-accepted 2026-07-04; chart-gated).** The drop fires at full
   palette color/speed; across the **post-drop autoloop** CH9 color speed eases down so the moment
   decays instead of hard-stopping. CH8 keeps the family color — or, once the chart lands, may
   drop into the **gradient / flowing-water families** at easing speed as the settle texture
   (taste call for the operator when the effects are visually validated). Rides the existing
   drop-lifecycle events; pure mapper behavior. **Gated on exact CH8/CH9 behavior from the chart
   (#1).**
9. **Drop spotlight & choreography (cross-reference only — zero laser code).** The operator-armed
   one-shot "lasers own the room" moment plus the automated earned-drop policy (pre-drop
   full-dark, lasers-only impact, track budget) are LED-side features; design lives in
   `streamdeck_palette_control_design_spec.md` Part C.9.

## Part F — Evidence (file:line, HEAD `bd96b32`)

- Pack autoloops author CH8/CH9 (922 writes / 42 docs, incl. active): scan of loaded
  `rbss_canonical_pack` autoloop documents, 2026-07-04 (values listed in Part E #1).
- 19-channel frame + control channels + clear_control persistence:
  `soundswitch_laser_player.py:23,25,32,109-111`.
- Frame-level blackout override: `render()` early return `:422-424`; `apply_layers` recheck
  `:202-203`; static layers over base `:443-457`; masks API `set_masks/set_blackout`
  `:323-333`.
- The single mask writer + overlay-trust gate + SS-present clear:
  `state_manager.py:2342-2364,2387`.
- Push-loop render path + crash-ZERO: `state_manager.py:2092-2107` (`_push_tick`),
  `_drive_pack_output` `:2300`, `render()` calls `:2415,2635`.
- Smart-drop note config → wire channel: `config/laser_director.json` `manual_commands`
  (channel 1/note 0, 1-based); `midi_output.py:252` (`int(msg.channel) - 1`); message build
  `laser_config.py:803-819` (no `scene_name`; `laser_models.py:53` default `""`).
- Pack-mode drops the note: `laser_output_backend.py:169-176`.
- Executor owner-refcount + pack-mode latch failure + C2 wipe:
  `laser_executor.py:66,323-340,342-356` (hold/release), `:330-340` (discard-on-reject),
  `:79-82,358-362` (wipe), `:97` (wipe via reset), `:325,327-329` (mode/config gates).
- Executor wipe call sites: `state_manager.py:1225,1232,1419,1462,1504,3244,3263,3517,3551,3558`.
- MIDI-input blackout refcount + group merge: `soundswitch_midi_input.py:280-314,621-635`;
  binding match incl. zero-based channel `:346-374`.
- Pack `manual_blackout` binding (IAC wire ch0/note0 → slot 31) + loader:
  `rbss_canonical_pack/selection_map.json` `manual_blackout`; `soundswitch_pack_loader.py:358-368`;
  slot 31 + slot 16 ("OFF") contents all-zero: loaded-pack scan 2026-07-04.
- Deck script filters non-ch2 rows (dead "BLACK OUT" row): `streamdeck/streamdeck_midi.py:85`.
- Smart-drop/breakdown hold/release call sites: `smart_rearm.py:244,274,289`.
- Backend selection (pack vs MIDI): `__main__.py:413-421` (structure; `:508,554` not re-read).
- Documented open gap + port-don't-delete requirement: `docs/subsystems/laser.md`
  §runtime-flow blackout-mask-migration bullet (~:69);
  `docs/archive/plans/laser_smartnet_mask_preserve_spec.md` (deferred reference design).
- LED color source: `led_color_engine.py:507` (`resolve_color`, needs cue context — no
  current-RGB accessor exists; new accessor required, Part B).

## Change-contract note

Design-only; changes no runtime behavior, so no `change_contracts.yml` entry yet. Per AGENTS.md
§7, **before** implementation begins, add/extend the `laser` contract (and likely a new
`laser_color` entry) with its `docs_update` list, then edit code.
