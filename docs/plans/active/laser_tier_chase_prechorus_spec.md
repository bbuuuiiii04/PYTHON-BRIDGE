---
doc_status: current
truth_level: code-verified
last_verified_date: 2026-07-09
last_verified_commit: HEAD-2026-07-09-overnight
validation_scope: implementation spec for the small dedicated laser round carrying the two AWR-162 items deferred out of the F2 build (executive ruling at the F2 gate 2026-07-09 - one named follow-up, NOT folded into F4): (B) per-tier chase divisions and (D.2) 4-beat pre-chorus laser blackout; seams re-verified at HEAD this session (read-only sweep + manager spot-verification); implements only AFTER F4 (AWR-164) lands and gates
---

# Codex Implementation Spec - Laser round: per-tier chase divisions + pre-chorus blackout (AWR-170)

Carries AWR-162 (B) and (D.2), deferred from the F2 round (`docs/status/active_work_registry.md`
AWR-162 row). Normative annex: `docs/plans/active/laser_energy_ladder_spec.md` (B and D.2 text;
operator-approved). **STRICT ORDER: dispatch only after F4 (AWR-164) lands + gates.** Line numbers
below were verified at HEAD 2026-07-09 pre-F4; F4 touches disjoint files but RE-VERIFY every cite
at implementation HEAD before editing.

## Part A - Context (verified; read, do not implement)

1. [confirmed] Chase selection is tier-blind today: `laser_color_engine.py` `_parse_menus`
   (:223-256) turns `{"chase": N, "colors": [...]}` into `("chase", ch8, names)` tuples;
   `_pick_menu_entry` (:281-305) selects by LED-color match + `is_drop` only. A monster drop and a
   standard drop pick the identical chase. `_f2_laser_tiers` (`state_manager.py:4825-4840`)
   produces `{beat: "small"|"standard"|"intense"|"monster"}` but it is collapsed to the binary
   LEDS_ONLY/LEDS_PLUS_LASERS gate in `drop_presentation.py:315-316`; nothing downstream reaches
   chase selection.
2. [confirmed] CH8/CH9 emission path: `state_manager.py:3703-3704` per-frame
   `player.set_color_snapshot(engine.snapshot())`; `soundswitch_laser_player.py:124-141`
   `_merge_color_snapshot` writes `merged[7]`=CH8 / `merged[8]`=CH9.
3. [confirmed] All 12 moods in `config/laser_color_map.json:14-25` carry `chase` entries; the
   red+white chase menus are `crimson` and `v2:EMBERCORE` (both `chase: 100`). No per-tier form
   exists anywhere (grep 116/140 negative).
4. [confirmed] Laser dark windows are NAMED MASK OWNERS: `laser_executor.py:346-382`
   `hold_blackout_mask(owner)`/`release_blackout_mask(owner)` on `self._mask_owners: set[str]`;
   `mask_owners_active()` is read at `state_manager.py:3717` to force smart_dark. Sole owner today:
   `"breakdown"` (F2 shared transition window via `smart_phrasing.py:398-424` edge flags →
   `smart_rearm.py:168/:244/:274/:289`).
5. [confirmed] Chorus phrase starts are the RAW ANLZ drop markers: `smart_phrasing.py:523-548`
   `build_phrase_segments_from_markers` maps every `anlz_drops` beat → a `"chorus"` segment start
   (caller `state_manager.py:4925`). Drop DECISIONS collapse consecutive markers (AWR-131), but the
   phrase data retains every marker — so (D.2) adds a laser breath before chorus markers that F2's
   per-drop window does NOT cover (the collapsed ones inside a drop section), and before primaries
   it simply overlaps the F2 window (mask owners are a set; longest coverage wins naturally).
6. [confirmed] Reusable lookahead shape: `laser_director.py:567-578` Priority-11 buildup window
   gates on `0 < sp.beats_to_next_drop <= lookahead` — the same countdown pattern (D.2 needs a NEW
   series over chorus markers, not `beats_to_next_drop`, which tracks collapsed decisions).
7. [assumed → verify at implementation] F4 (in flight at authoring time) does not touch
   `laser_color_engine.py`, `laser_executor.py`, `smart_rearm.py`, or `config/laser_color_map.json`
   (its spec scope is LED-side). Confirm with `git log` at dispatch.

## Part B - Tasks (in order, one commit each, explicit paths)

### Absolute Rules
- Out of scope: LED render path, F2 plan engine internals (`lighting_moments_v2.py` decision
  logic), F4 texture code, live config (`config/led_look_director.json` read-only), bridge starts,
  pad restarts. Do not revert unrelated dirty-worktree changes; never `git add -A`, never stash.
- Behavior that must not change: tier-less tracks and every menu WITHOUT the new per-tier form
  render byte-identical CH8/CH9 to today; LEDS_ONLY (small) drops still fire no lasers; blackout /
  emergency / pack-disabled masks still beat everything.
- Error handling: config parse failures fail CLOSED to the single-value form (never crash the
  engine, never invent a division); missing tier at runtime falls back to the `standard` value.

### Task 1 - `config/laser_color_map.json`: per-tier chase seed
Extend ONLY the two red+white chase entries (`crimson`, `v2:EMBERCORE`):
`"chase": {"standard": 100, "intense": 116, "monster": 140}` (operator-approved seed). Every other
menu keeps its single int (operator supplies divisions later). JSON stays valid for the old parser
until Task 2 lands in the same round — order the commits Task 2 FIRST if the loader would reject
dict form (verify; if `_parse_menus` skips non-int `chase` silently, either order works but the
seed must not vanish — add the Task 4 test first in that case).

### Task 2 - `laser_color_engine.py`: parse + select per-tier
`_parse_menus`: accept `chase` as int (today's form → same value all tiers) or a dict with keys
among `standard|intense|monster` (values int 0-255; missing keys fall back to `standard`, then to
the first present value; junk entry → skip, fail closed). Entry tuple gains the resolved mapping —
keep the existing `("chase", ch8, names)` shape for single-value entries so untouched menus are
provably unchanged, and use `("chase_tiered", {tier: ch8}, names)` for dict form.
`_pick_menu_entry`/`_target`: when the picked entry is tiered, resolve CH8 by the CURRENT drop
tier (Task 3 input); `None`/unknown tier → `standard`.

### Task 3 - `state_manager.py`: plumb the tier one hop
At the existing per-frame snapshot call (:3703, re-verify), pass the active drop's tier string
(from the same `_f2_laser_tiers` beat-keyed map, matched to the drop window the presentation layer
is currently in; `None` when F2 off / no plan / scripted / tier-less). PUSH-LOOP RULE: this is a
dict lookup on already-computed plan data — no new computation, no I/O in the tick path.

### Task 4 - pre-chorus blackout (D.2), new mask owner `"pre_chorus"`
- `smart_phrasing.py`: new plan-time series `beats_to_next_chorus_marker` from the RAW chorus
  marker beats (Part A-5), alongside the existing edge-flag pattern (:398-424): arm flag when
  `0 < beats_to_next_chorus_marker <= f2.pre_chorus_laser_beats`, clear flag at/after the marker
  beat. Same rising/falling edge discipline as `transition_mask_should_arm/clear`.
- `smart_rearm.py`: consume the flags exactly like :168/:244/:274 — `hold_blackout_mask("pre_chorus")`
  / `release_blackout_mask("pre_chorus")`.
- Gating: only when F2 enabled AND an f2 plan exists AND not scripted (v2 stand-down discipline);
  config `f2.pre_chorus_laser_beats` — example ships `4`, ABSENT ⇒ `0` ⇒ feature fully off
  (absent-key = today's behavior, the mirror rule).
- Mode-transition cleanup (checklist rule): the `pre_chorus` owner is released on EVERY reset path
  that releases `breakdown` today — track change, active-deck change, scripted entry, transport
  loss, stop. Enumerate each site; a leaked owner = latched-dark lasers (AWR-154's failure class).

### Task 5 - Tests
Pure seams only. Parser: int form unchanged (byte-identical tuples), dict form resolution +
fallbacks + junk fail-closed. Selection: per-tier CH8 for `crimson` at standard/intense/monster;
`None`-tier → standard == today's value. Window: arm/release edges for the new series incl. a
collapsed-marker fixture (two chorus markers 32 beats apart inside one drop section → second
marker still gets its 4-beat window); overlap-with-F2-window fixture (owner set holds both, no
early release); every cleanup path releases `pre_chorus`. Config: absent key ⇒ 0 ⇒ no arm flags
ever; example ships 4. F2-off ⇒ no series, no flags, byte-identical.

### Task 6 - Contract docs
Contracts: `laser` + `laser_color` + `config_schema` (+ `led_govee` only if the f2 config block
schema counts there — follow `docs/agents/change_contracts.yml`). Full `docs_update` lists; AWR-170
registry row with real numbers; AWR-162 row flips (B)/(D.2) from deferred to implemented.

## Part C - Invariants (live safety)
- The 200 Hz push loop gains no blocking I/O and no new computation beyond dict lookups.
- Mask precedence unchanged: blackout / emergency / pack-disabled always win; Static Override
  semantics untouched.
- AWR-138 both-sides re-entry untouched (`drop_presentation.py:698-727`): this round never touches
  the window machine.
- A `pre_chorus` mask can NEVER outlive its track: prove via the cleanup-path tests.
- F2-off, scripted, and un-mirrored live config ⇒ byte-identical laser output to today.

## Part D - Tests
See Task 5 — all pure-function seams (parser, selector, edge flags, cleanup); no disk, no
subprocess, no bridge.

## Part E - Acceptance
- [ ] Dispatched only after AWR-164 lands + passes the executive gate.
- [ ] Tasks in order, one commit each, explicit paths; Part A cites re-verified at HEAD first.
- [ ] Full suite (parent-dir form) at EXACTLY the known-six-red baseline BY NAME; the two
  `test_soundswitch_pack` byte-identity tests are a known commit-race (AWR-169) — isolate before
  counting. Three hard checks pass.
- [ ] Operator summary (plain, for the morning note): hard drops now spin the red/white chase
  faster the harder the drop reads (100→116→140); every chorus gets a 4-beat laser breath before
  it lands, including choruses mid-drop-section that LEDs already play through; one config line
  (`pre_chorus_laser_beats: 0`) turns the breath off; nothing changes until the live config is
  mirrored and the bridge restarts.
- [ ] Print exactly AWR170-DONE with real suite numbers, or AWR170-BLOCKED with the reason.

## When You Finish
Report changed files, tests/checks run, and every deviation named explicitly (never fold a miss
into "config-seeded"/"documented" labels). Adversarial self-check before the sentinel: the
named-owner leak scenario (Task 4 cleanup), the dict-form parse failure scenario (must fail closed
to single-value), and the tier-lookup-on-tick cost (must be a lookup, not a recompute).
