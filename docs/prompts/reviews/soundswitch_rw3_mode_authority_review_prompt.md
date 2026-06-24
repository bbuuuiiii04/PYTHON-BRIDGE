---
doc_status: active-review-prompt
truth_level: code-grounded
last_verified_commit: e295e37
last_verified_date: 2026-06-24
validation_scope: independent second-opinion review of the RW-3 mode-authority DESIGN SPEC (docs/plans/active/soundswitch_rw3_mode_authority_spec.md); review-only; SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED; no implementation/enable/backend/restart/hardware authorized
---

# Independent second-opinion review — RW-3 scripted/autoloop/idle mode-authority gate

You are an independent, adversarial reviewer for a live-performance lighting bridge,
rb_ss_bridge_v2 (Python, AI-maintained, repo status SOFTWARE-VALIDATED ONLY /
HARDWARE-UNVALIDATED). You have repo access but no prior context. Review a DESIGN
SPEC only — no code is written yet. Your job is to find reasons it is wrong or unsafe,
not to bless it.

SPEC UNDER REVIEW:
  docs/plans/active/soundswitch_rw3_mode_authority_spec.md  (RW-3 — explicit
  scripted/autoloop/idle mode-authority gate for the bridge-native CH1-CH19 pack driver)

WHAT RW-3 DOES (one sentence): the SoundSwitch pack driver currently decides "is this a
scripted track" from a syntactically-valid embedded soundswitch_id (a UUID), instead of
the bridge's real scripted-mode authority DeckState.scripted_id; RW-3 ANDs one term —
scripted_owned = int(getattr(d,"scripted_id",0) or 0) != 0 — into the existing happy-path
gate, plus a one-line hold-latch reset on scripted de-ownership.

OPERATOR CONTEXT YOU MUST WEIGH (affects severity, not correctness): the live rig runs
RBSS_SCRIPTED_DIRECT=1 (direct mode ON) with a bounded event queue (queue.Queue(maxsize=512),
__main__.py:1020), and the pack output is default-off (enabled=false, output_backend=none).
The spec (Part A.3) argues that under direct=1 the common path already ZEROs non-scripted
UUID tracks — because FILEPATH_RESOLVED and its follow-on SCRIPTED_CLEAR reconcile in the
SAME serial _drain_events pass before the pack driver runs — so RW-3 is hardening /
explicit-authority / queue-drop-edge closure, NOT a fix for a currently-observable live
bug on this config. Confirm or refute that severity claim from code; if you think the spec
over- or under-states severity, say so with file:line.

READ FIRST, IN THIS ORDER (code wins over docs):
  1. state_manager.py::_drive_pack_output  (def ~3253; gate block 3296-3338; the new
     term goes at ~3298, the happy line at ~3312, the latch-reset else at ~3326)
  2. state_manager.py::_update_lighting  (~3096; scripted derivation 3117-3122; writes
     os.lighting_mode at 3145; idle-debounce early-return 3133-3134)
  3. state_manager.py::_drain_events (1070-1076) and _run (872-877) — event drain vs tick
     ordering (serial, same thread); production queue is bounded (__main__.py:1020)
  4. state_manager.py::_on_filepath_resolved (2863; soundswitch_id set 2878; direct-mode
     block 2920; SCRIPTED_ARM enqueue 2960; SCRIPTED_CLEAR enqueue 2971; Full-drop 2976),
     SCRIPTED_ARM handler (1242-1252), _arm_unscripted (3087-3092), _arm_scripted
     (2982; scripted_id 3014; ssid fallback 3024), _on_track_loaded (2613-2618),
     _on_master_changed scripted transfer (2559-2568)
  5. soundswitch_laser_player.py — select_scripted (213-224), _scripted_base (271-315,
     incl. scripted_not_found 298-301), clear_selection (247-256), render (345-373),
     normalize_soundswitch_id (166-177)
  6. models.py — DeckState.scripted_id (83), TrackMetadata.soundswitch_id (35),
     OutputState.lighting_mode / was_playing (139, 129)
  7. The reviewed precedent it must not regress:
     docs/plans/active/soundswitch_rw2_scripted_transport_spec.md (the pause-vs-stop
     hold latch _pack_play_hold_key/_pack_play_hold_deadline, bound to (active,load_gen)
     + STOP_DEBOUNCE_S), and tests/test_state_manager_pack_driver.py
  8. The status authority: docs/plans/active/soundswitch_exporter_remaining_work.md —
     RW-3 section (360-386) and §7 invariants (692-725)

LIVE-SAFETY INVARIANTS THE CHANGE MUST NOT REGRESS (roadmap §7):
  - StateManager is the only DeckState writer; the driver is read-only w.r.t. DeckState.
  - No filesystem/subprocess/MIDI/serial/socket/sleep/retry/blocking-queue work in the
    200 Hz push loop.
  - The automatic base resolves ZERO on unowned-mode / stop-unload / stale / error /
    invalid identity, via clear_selection() (never transport="stopped"/"ended"/"unloaded").
  - Manual Static Override + blackout/emergency precedence unchanged; the gate must change
    ONLY the automatic scripted base, never the controller path (RW-4 is out of scope).
  - Default-off neutral: with pack absent/disabled/dry_run/output_backend=none the change
    is byte/order-neutral for OS2L, lasers, LEDs, Rekordbox readers, commands, and logs.
  - Pack failure never falls back to physical MIDI.
  - select_autoloop stays uncalled (RW-8 out of scope); autoloop mode ZEROs.

ATTACK THESE SPECIFICALLY (give a concrete failing tick sequence, not vibes):
  1. The scripted_id <-> soundswitch_id identity coupling. The spec (Part A.3) claims that
     under live RBSS_SCRIPTED_DIRECT!="0" the FILEPATH_RESOLVED and its follow-on
     SCRIPTED_ARM/SCRIPTED_CLEAR reconcile in the SAME _drain_events pass, so the driver
     normally sees a consistent pair, and the durable divergence is only under
     RBSS_SCRIPTED_DIRECT=0 or a dropped SCRIPTED_CLEAR. Verify that against _drain_events
     (1070-1076), _run (872-877), and the put_nowait sites. Is the "same drain pass" claim
     correct? Is there a tick where the driver observes soundswitch_id valid while
     scripted_id==0 that the spec missed (partial drain, reader-thread interleave, the
     master-deck transfer at 2559-2568, OSC SCRIPTED_ARM landing on the wrong deck, queue
     saturation at maxsize=512)?
  2. same-tick vs stale os.lighting_mode ordering. The spec chooses d.scripted_id over
     os.lighting_mode and refuses to AND lighting_mode into the gate (Part A.4). Is that
     justified, or is there a state where d.scripted_id is set but the deck should NOT
     render a scripted base (so lighting_mode would have caught it)? Conversely, does
     using scripted_id introduce a flicker/dark-flash on a legitimately scripted track
     during the arm window, and is that acceptable vs the OS2L lane?
  3. RW-2 pause-hold interaction. happy now requires scripted_owned. Prove the paused
     branch (elif happy and was_playing and key==hold_key and now<deadline) cannot render
     a stale scripted frame after scripted ownership is lost. Check the Task 1c latch
     reset (load_key != hold_key OR not scripted_owned) for any case where it (a) fails to
     reset when it should, or (b) wrongly resets a legitimate pause (would break RW-2 T1/
     T4/T5). Force the "scripted_id flickers off then on within STOP_DEBOUNCE_S for the
     same load_gen" case.
  4. Every mode-transition cleanup path (the A.8 table): fresh-load, resolved-not-scripted,
     scripted-not-yet-armed, play, pause, master switch, track replacement (load_gen
     change), return to autoloop, return to idle, stale, discontinuity, mid-play mode flip.
     Find one transition where the desired base (render vs ZERO) is wrong or the named
     authority variable does not actually prove it.
  5. Static Override / blackout independence. Confirm the masks/static block (3271-3280)
     and player precedence (render 345-373) are untouched and a held static still stands
     alone over the now-ZEROed automatic base. Find any way the mode gate silently changes
     controller behavior.
  6. Any ZERO-on-uncertainty hole: a state the spec leaves rendering when it should ZERO,
     or any path that could produce a NON-ZERO frame that the current code ZEROs. The spec
     leans on a "strict-narrowing" proof (Part A.7: happy_RW3 -> happy_today, so RW-3 can
     only add ZEROs). Try to falsify that proof.
  Also: is the test plan (Part D R1-R6) sufficient to catch a regression of each of the
  above? Is R6 (inner-path RBSS_SCRIPTED_DIRECT=0) actually exercisable purely as claimed?

DELIVER A VERDICT in this exact format:
  VERDICT: APPROVE | REVISE-AND-APPROVE | REJECT
  Then a numbered list of objections, each as: [BLOCKER|MAJOR|MINOR] file:line — the
  problem — a concrete failing scenario or the exact line to change. No general praise;
  cite file:line for every objection. If you cannot find a concrete failure for an attack
  vector above, say so explicitly rather than inventing one.
