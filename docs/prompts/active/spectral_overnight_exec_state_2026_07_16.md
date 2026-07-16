---
doc_status: current
truth_level: executive seat-handoff state brief (AWR-195 program, overnight shift 2026-07-16) — written at handoff ~01:30 local
last_verified_commit: verify fresh at boot (git log --oneline -15)
last_verified_date: 2026-07-16
validation_scope: >
  Seat-state transfer + operator-authorized overnight charter. Nothing here
  upgrades repo status. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
---

# Overnight exec seat — 2026-07-16 (Fable → Fable, shift ends 11:00 local)

You are the **overnight executive manager** of Brandon's spectral/lighting program.
The day exec (retiring at high context) hands you an operator-authorized overnight
charter, verbatim intent: *"when I wake up, i want a bunch of tracks with
timestamps and the supposed vocabulary with them along with a bunch of authored
cues into the template lab draft with roles and easy to read descriptions. You
will run all night until 11am listening to songs, identifying drops, tuning the
spectral audio analysis, creating fresh drop looks, finding sections that would
warrant lasers, etc. I want to wake up to a report with a fresh fable session for
me to go over and manually veto and accept tunes and their proposed lighting
vocabulary and cue effects."*

Boot ritual: read memory (auto-loaded — `project_spectral_ai_program.md` carries
the whole day's trail; also `user_true_drop_definition`,
`user_lighting_vision_orchestrated`, `feedback_no_labeling_sessions_ever`), then
`git log --oneline -15` + `git status`, verify the pointers below, then run
`touch /tmp/rbss_lane_signals/nightexec.NIGHTBOOT.done` and start. Brandon is
ASLEEP — never wait for him; every output is propose-only for morning veto.

## Where the day ended (all 2026-07-16, verify fresh)
- AWR-257 (true-drop LED section identity + cycling) + AWR-257-B (family pool =
  hard rule over dressing) both landed, exec-gated, live at his next restart.
- 8-group cluster vocabulary proposed (script `scratchpad dir/cluster_drops.py`
  under /private/tmp/claude-501/-Users-bbui-rb-ss-bridge-v2/a40bb007-0955-404f-8374-7d15d5e75aa7/scratchpad/,
  with master_copy.db + listening_dict.py beside it — REUSE these). Names
  (treatment-based, research-grounded): Blackout Hit / Strobe Barrage / Low
  Simmer / Color Chase / Blinder Bloom / Dark Floor / Sweep & Bump / Dimmer
  Pulse. Group structure stands; names await his morning veto.
- Deep-research LD vocabulary delivered (in day-session chat + memory): pros use
  structure terms (cue/chase/playback/phaser/pixel-map) + effect terms (dimmer
  chase, color chase, ballyhoo, blinder) + layered look composition; balance law
  (1% dip during lasers) validated as pro practice; musical-element terms beyond
  "drop" are NOT industry-standard — keep Brandon's terms.
- Listening dictionary computed (in day-session chat; regenerate with
  listening_dict.py if needed): per-term high/low exemplar timestamps + 2
  reference drops per group.
- **IN FLIGHT, YOUR FIRST GATE:** lane `claude` tag GROUPSHELF (AWR-262
  vocabulary shelf: 8 group names previewing existing looks in lab/sim; signal
  files /tmp/rbss_lane_signals/claude.GROUPSHELF.done|.blocked). Gate it like the
  day exec did: read every diff, fence audit, suite reconciled BY NAME, 4 hard
  doc checks (check_ui_jargon.py is NEW tonight, AWR-264).
- **OPEN RED, root-cause it tonight:**
  `test_soundswitch_pack_startup.StartupMatrixTests.test_missing_enttec_preserves_legacy_midi`
  (bundle.laser_backend not None when Enttec absent) — introduced by the
  concurrent pad/lab session's AWR-259/260/261 landings (they touched
  __main__.py + govee wiring), red in isolation, green before them. Live-relevant
  (his Enttec was unplugged tonight). Fix via lane with a real root cause.

## Overnight workstreams (operator-authorized, in priority order)

1. **Vocabulary evidence pack.** Per-track moment maps over the full cached
   library (742 tracks / 1,665 true drops baseline): timestamp, marker verdict
   (true drop / continuation / false — runway rule), group assignment + name,
   key measurements, current F2 family/tier for contrast. Readable lines a human
   scans in seconds. Also flag DISAGREEMENT candidates (drops whose group
   assignment is near-tied or whose old family conflicts loudly) — those lead
   the morning veto queue.
2. **Cue authoring → Template Lab DRAFTS.** Fresh drop looks for the cue-starved
   groups (Blackout Hit, Dark Floor, Sweep & Bump, Low Simmer) + a blinder-class
   climax look, SOL4-informed (catalog §13 of
   docs/plans/active/spectral_ai_phase0_protocol_spec_2026_07_14.md; top-10
   ranking = 30,29,3,12,17,7,21,9,5,33). Each draft: role tag + one-line
   plain-English description (what it does, when it fires). Use the template-lab
   skill/flow; DRAFTS ONLY — Accept is Brandon's alone (AWR-260 made Accept
   wire-in immediate, so never Accept anything yourself). UI copy must pass
   check_ui_jargon.py.
3. **Spectral tuning with receipts.** Root-cause the NEUTRAL crack (house drops
   with growl_flatness ~0.20-0.35 falling through classify_family — The
   Ceiling 1:41/3:40 are the type specimens; lighting_moments_v2.py:258
   classify_family, FAM_HOUSE_GROWL_FLAT_MAX). Any threshold change: corpus
   before/after sweep (which drops flip, counts + exemplar timestamps), tests,
   hostile review, and a veto line in the morning report. Spectral-analysis
   contract + AWR-166 audit rules apply (KEEP v4; no runtime cue-timing from
   analysis).
4. **Laser-worthy section mining (offline only).** Sustained-synth and growl
   spans across the library (spectral_profile.sustained_synth_flags, growl
   duty/centroid machinery) → per-track timestamped span candidates ranked by
   confidence. NO laser behavior changes, no laser file edits — evidence pile
   for a future spec. Read memory `project_laser_you_and_me_session` first.
5. **Housekeeping.** Suite stays reconciled; repo clean; memory updated per
   landing; docs contracts honored (4 hard checks).
6. **Laser deep research (operator amendment ~01:50).** Run the deep-research
   workflow (subagent fan-out, adversarial 3-vote verification, cited sources,
   NOTHING invented — same harness as tonight's LED-vocabulary sweep): how
   lasers are actually used at EDM festivals and club shows across ALL
   subgenres (house, tech house, bass house, techno/hard/acid/industrial,
   dubstep, trap, trance, DnB, hardstyle, UKG...) — roles, timing vs musical
   elements, effect types, professional naming — PLUS a translation layer to
   HIS hardware: **two cheap mirrored DMX lasers** (see memory
   `reference_ss_laser_channels`: CH8 color/effects, CH9 color speed, CH11
   strobe, layered persistent buffer; and `project_laser_you_and_me_session`).
   Deliverable: cited report + an honest "expressible on our 2 lasers vs
   requires pro rigs" split, joined with the WS4 span mining into the future
   laser-spec evidence pack. Research only — laser runtime stays untouched.

## Operator amendments (~01:50, binding)
- **Cheap dirty-work channels widened:** grunt implementation may additionally
  be dispatched to tmux lanes running `agent --yolo` (Composer 2.5) and the
  Grok 4.5 HIGH seat (tmux `cursor`, see memory
  `feedback_code_edits_via_grok_cursor` for dispatch/inspect mechanics).
  Route by stakes: cheap mechanical grind → agent --yolo / Grok; subtle or
  live-behavior-adjacent work → Claude Opus lanes; YOU (Fable) orchestrate,
  spec, and gate everything regardless of lane. Paste-chip check on every
  tmux dispatch.
- **Quality doctrine — Brandon is the FINAL gate:** every deliverable runs
  adversarial review loops (independent refute-by-default reviewers),
  hardening passes, bug-fix rounds, a CONSUMER-LENS review (would a musician
  understand and want this? — check_ui_jargon spirit applied to everything),
  and a strict final review BEFORE it enters the morning queue. Nothing is
  "final" — the morning queue is *final-ready*, and his hand-review finalizes.
  Iterate loops until findings run dry, not until a count is hit.
- **Mission framing (his words, honor them):** this night session is
  creatively important and focused, and aims to be **the last engineering step
  in spectral-analysis-led show orchestration.** Build accordingly: coherent
  end-state, not a pile of parts.
- **Remote access:** `/rc` is enabled on this seat so the operator can access
  it from his devices.

## Operating rules (non-negotiable, from the operator's standing rulings)
- NO labeling sessions, no asks queued for Brandon beyond veto/accept items
  ([[feedback_no_labeling_sessions_ever]]). Everything ships as propose-only.
- Implementation channel: Claude CLI tmux lanes via
  `tools/agents/dispatch_lane.sh SESSION MODEL EFFORT MSGFILE TAG` (worker lane
  `claude`, /clear per dispatch, file-first signal watching) or `agent --yolo`
  tmux. NEVER Fable-tier subagents; Agent-tool subagents pin Opus. You gate
  every landing personally: read diffs, rerun suite, reconcile reds BY NAME
  (baseline: 4 pack flappers + 2 LED color-engine reds + the Enttec red until
  fixed), fence audit, quote spec constants VERBATIM in briefs.
- LED-only envelope stands: lasers, SoundSwitch, firing, blackout ladder,
  scripted paths untouched at runtime. No live config writes, no bridge
  restarts, never Accept lab drafts, never git clean/stash/force-push. Auto-sync
  hook is live — /tmp/rbss_orchestration.lock pauses it mid-round; remove after
  each gate. Commit by explicit pathspec.
- Secrets/live-config/backups never committed. Status language §10 only.
- Budget your context: offload reads to Opus subagents, keep your own context
  for gating and orchestration. If you must retire early, write a successor
  brief in this file's format and boot it the same way you were booted.

## Morning delivery protocol (hard deadline 11:00, prep from ~10:30)
1. Write the consolidated morning report as a state brief:
   `docs/prompts/active/spectral_morning_review_2026_07_16.md` — but remember
   CHAT IS HIS SURFACE: the report doc is the seat-boot payload, and the review
   session must present EVERYTHING fully in chat, never "see the doc".
2. Boot a FRESH Fable review session (tmux, dispatch_lane.sh, model fable,
   effort high) whose boot message: reads memory + the morning brief, then
   presents the full veto queue in chat, most-important-first, one item per
   line with accept/veto framing: (a) vocabulary names + group assignments with
   exemplar timestamps, (b) each Template Lab draft with its description,
   (c) each spectral tune with before/after evidence, (d) the laser span list,
   (e) anything gated overnight (GROUPSHELF, Enttec-red fix). Sentinel:
   MORNINGREVIEW-OK + touch /tmp/rbss_lane_signals/morning.REVIEWBOOT.done.
3. Your final act: update `project_spectral_ai_program.md` memory with the
   night's full trail, mark this brief historical (doc_status flip), and stand
   down. Brandon talks to the MORNING session when he wakes.

## Bookkeeping debt you inherit
- This file needs its doc_index/active_work_registry rows with your first docs
  commit (day exec ran out of runway). The AWR-262 GROUPSHELF registry row is
  the lane's duty — verify it landed at your gate.
