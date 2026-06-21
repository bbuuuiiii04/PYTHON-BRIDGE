---
doc_status: draft
truth_level: design-intent
last_verified_commit: fd40843
last_verified_date: 2026-06-19
validation_scope: software-only
---

# Laser Color — Design Spec (pre-handoff)

> **Status: PLANNED / DESIGN-INTENT. Not implemented. Blocked on one external input
> (CH8/CH9 channel behavior from VirtualLaserNode captures).**
> Roles: Claude authors this spec (planning); **Codex implements the bridge code**
> once the spec is finalized. This doc exists to preserve the design we agreed on
> so it is not lost when the channel behavior arrives.

This is a forward-looking design doc. It is **not** current truth and is not in the
active work registry yet. Verify every "confirmed" claim against code before relying
on it. Per AGENTS.md §1, code wins over this doc.

---

## Part A — Goal & scope

Add laser **color** to the bridge. Today the laser subsystem is MIDI-only and has no
color concept; SoundSwitch drives the lasers over DMX. We want the bridge to control
laser color so it is coordinated with the LED color engine, without changing any other
laser/SoundSwitch behavior.

In scope:
- Non-scripted tracks: laser color **follows the LED color engine's palette** (LED
  engine stays the color authority), re-anchored on smart-phrasing phrase boundaries.
- Scripted tracks: laser color uses the track's **own defined colors** and **bypasses**
  the LED color engine.
- Laser color **effects / speed / gradient / water-flow / color-change**, available
  through the DMX color channels, layered on top of the base color family without
  breaking palette coordination.

Out of scope (do not redesign these away):
- The bridge keeps firing laser phrase decisions **every phrase** — that is acceptable.
- SoundSwitch keeps owning pattern, movement, intensity, and blackouts. Breakdown /
  groove / buildup autoloops stay blacked out; only drop / post-drop autoloops carry
  visible laser content.
- The existing MIDI scene path is untouched. This feature is purely additive.

## Part B — Confirmed evidence (code-grounded, this HEAD `fd40843`)

- **No DMX/Art-Net code exists anywhere in the bridge** — *confirmed* (`grep` for
  `artnet|art-net|art_net|dmx` across all `*.py` is empty). A new transport is required.
- **Laser output is MIDI-only; the laser subsystem has no color concept** — *confirmed*.
  In `laser_*.py` / `midi_output.py`, "color"/"channel" only ever means a MIDI channel.
  CH8/CH9 are SoundSwitch DMX channels, currently unknown to the bridge.
- **Smart phrasing emits four labels** (`smart_phrasing.py`): `PhraseLabel =
  "up" | "chorus" | "low" | "other"`, plus `phrase_anchor_*` fields
  (`phrase_anchor_last_beat`, `phrase_anchor_period_beats`, `phrase_anchor_target_beat`,
  `phrase_start_crossing`) — *confirmed*. These give us anchor timing.
- **A mature, Claude-owned LED color engine exists** (`led_color_engine.py`,
  `led_models.py`) — *confirmed*: `LedColorEngine.resolve_color(role, section_id, cycle,
  look_name, ...)` returns RGB via a hue-scale / `_p_to_rgb` piecewise lerp; `Palette`
  library with weighted selection, dwell, drop-snap, per-track focus. This is the color
  source we reuse for non-scripted tracks.
- **Scripted track handling lives in `scripted_tracks.py`** — *assumed relevant; the
  exact laser-color definition path is UNKNOWN and must be verified before spec finalizes*.

## Part C — Architecture & locked decisions

**Transport — inline color-overlay (LOCKED).**
The bridge sits inline in the DMX path:

```
SoundSwitch ──Art-Net/DMX frame──▶ [BRIDGE color-overlay] ──▶ laser DMX interface ──▶ lasers
                                       │ overrides ONLY CH8/CH9
                                       │ forwards every other byte untouched
```

- Runs on its **own thread**; **never** in the 200 Hz `StateManager` push loop (honors
  the runtime invariant: no blocking network/socket I/O in the push loop).
- Overriding on **every forwarded frame** means the "autoloops reset channels to 0 each
  phrase" behavior is harmless — there is no re-assert race and no scheduling needed.
- Autoloops **leave color neutral** (confirmed by operator), so the bridge owns CH8/CH9
  outright with nothing to fight.

**Color source (LOCKED, evolved from earlier "4-row lookup").**
- Non-scripted: sample the **LED color engine's resolved color** at each phrase anchor
  and map it to the nearest fixture color. Smart phrasing decides *when* color re-anchors
  (family-anchor granularity); the LED palette decides *what* the color is.
- Scripted: bypass the LED engine; use the track's own laser colors.

**New pure resolver (LOCKED shape; values pending channel behavior).**
A pure function `resolved_RGB → (CH8, CH9)` mapping the LED engine's RGB onto the
fixture's discrete color set (red/green/blue/cyan/yellow/magenta/white + effects). Pure =
the required test seam. Hard-cut at the phrase anchor unless the channel behavior exposes
a transition/scroll capability we choose to use.

**Effects / speed / gradient / water-flow (design pending channel behavior).**
Layered on top of the base color family so palette coordination is preserved — i.e. the
base color comes from the palette mapping; effect/speed selection is an orthogonal choice.
Concrete encoding waits on the CH8/CH9 chart.

## Part D — Pending inputs & open decisions

**BLOCKING input — CH8/CH9 channel behavior (from VLN captures/decoder).** Needed to
build the RGB→fixture-color map and the effects design. Specifically: what each of CH8
and CH9 does, whether color is an indexed macro with value *ranges* vs. a continuous
value, and which value ranges produce red/green/blue/cyan/yellow/magenta/white,
gradients, water-flow/color-flow, RGB/color-change, and speed/direction.
*Treat VLN prose docs as untrusted (mid-refactor); prefer captures + decoder code.*

Open decisions (not blocking, but record the answers here when known):
1. **Scripted-track color source** — where scripted laser colors are defined and how the
   overlay reads them (verify `scripted_tracks.py`).
2. **Transport finalization** — the *SoundSwitch export/import* reverse-engineering (a
   separate research run) may push the long-term design toward "bridge owns all DMX." The
   inline overlay is the safe interim; the **pure resolver survives either way**, so only
   the transport layer is at risk of rework.
3. **`other` phrase behavior** — recommend fail-open (forward SS bytes unmodified).
4. **Blackout independence** — confirm the fixture's intensity/blackout channel is
   independent of CH8/CH9 so injected color can never defeat a SoundSwitch blackout.

## Part E — Smallest useful implementation path (for Codex)

1. **Pure color mapper** (`resolved_RGB → (CH8, CH9)`) + unit tests. Buildable the moment
   the channel chart lands; architecture-independent; zero live risk.
2. **Color-intent producer**: at each smart-phrasing anchor, choose color source
   (non-scripted → LED engine resolved color; scripted → track colors) and emit a color
   intent. No I/O.
3. **Inline overlay transport** (own thread): receive SS Art-Net/DMX, override CH8/CH9
   from the current intent, forward. **Shadow/dry-run first** (log or emit to a test sink
   / VLN, not the live rig) until validated.
4. Promote to live overlay only after rig-visual validation, with the live-safety
   invariants below in place.

**Live-safety invariants (must hold):**
- Inline overlay makes the bridge a **single point of failure for the whole laser rig**,
  not just color. Mitigate: **transparent passthrough** + **fail-open** (any resolver
  error or unknown family → forward SS bytes unmodified, never impose a wrong color).
- Forward thread must **never block** and must be isolated from the 200 Hz push loop.
- After any bridge restart: `pgrep -f rb_ss_bridge_v2 | wc -l` must be `1`.
- Confirm intensity/blackout channel is independent of CH8/CH9 (open decision #4).

**Pre-handoff checklist status:** verified claims (Part B) — done; knowns/unknowns —
captured (Part D); pending-state / mode-transition guards — scripted vs non-scripted +
fail-open specified; third-party API completeness — **blocked** (CH8/CH9 chart); pure
test seam — defined (step 1); live-safety invariants — specified; adversarial self-review
— pending final spec. **This spec is not handoff-ready until the channel behavior lands.**

## Change-contract note

This is design-only and changes no runtime behavior, so no `change_contracts.yml` entry
is added yet. Per AGENTS.md §7, **before** implementation begins, add/extend the `laser`
(and likely a new `laser_color` / transport) contract with its `docs_update` list, then
edit code.
