# PAD/LAB overhaul brief — manager seat (operator orders, 00:05 wave)

doc_status: current
truth_level: dispatch-brief
seat: `pad` lane, Fable/XHIGH (standing order), manager charter, full review chain.

## Operator orders (verbatim anchors)

- "the LED Pad is outdated. It needs to be updated and also never go stale. It
  shouldn't EVER be outdated."
- "the LED Template lab is INCREDIBLY unintuitive and inefficient." (screenshots
  on file with the executive; the concrete indictments are below — every one was
  live-verified tonight)

## The verified defect list (all reproduced/root-caused at the executive desk tonight)

1. **Accept ≠ what you hear**: `lab_accept` flips status only (`tools/led_pad_web.py:603`);
   Play layers live sliders over saved params — audition state and accepted state
   can silently differ. FIX: accept-what-you-hear (Accept snapshots effective
   params) + a dirty-state indicator; Save/Accept flow made un-trappable.
2. **Preview silently saves first** (`lab.js` previewDraft: `await save()`) — save
   failures kill Preview with no visible reason. Surface errors loudly; decouple
   or make the implicit save visible.
3. **Promotion never retires the source draft**: tonight's promotion left the
   authoring draft colliding with its production twin ("lab name collides with
   production renderer") — bricking save/preview/play for that draft. LAW: the
   promotion workflow renames/retires the draft atomically.
4. **The `fn` field is dead code in lookup**: preview/play resolve the lab module
   function by draft NAME, ignoring stored `fn` (`led_pad_web.py` `_lab_play_spec`)
   — renames break rendering. Honor `fn`.
5. **Triple-source param bounds**: renderer clamps vs `led_pad_controls.py`
   CONTROL_META vs per-draft `param_specs` — three copies of the same number
   (tonight: two were fixed, the third kept the operator's slider floored).
   Single source of truth, or a generated/validated sync with a tripwire.
6. **Raw R/G/B sliders in B-G-R order, no swatches**: replace with color pickers +
   live swatches; and show the color-regime per control (palette-fed looks must
   visibly mark baked-color controls as overridden/inert during audition —
   "palette overrides this in the room").
7. **Agent-facing content in the operator UI**: the promotion checklist + raw
   Traceback panel move out of the creative surface (dev toggle / docs).
8. **Unlabeled controls**: the 4/8/16/32 row and bare-number sliders get plain
   labels; Delete moves away from Accept + confirm-gated.
9. **The page corpses on server restart**: survive restarts (reconnect + refetch
   state); the pad server restarted twice tonight and each time the open page
   silently broke.
10. **Never-stale by construction**: the pad/Lab reads live config truth at
    request time (no baked snapshots); new production effects/params appear the
    moment they exist (tonight the running pad predated the evening's effects).
    Include the freshness contract in tests.

## Fences

- The `ledsim` round (separate lane, holding for operator room images) owns the
  accurate room-simulation ENGINE; your round owns the pad/Lab server + UI. The
  future preview-backend swap is an integration point — design the preview
  surface swappable, do not build the sim.
- No production renderer/policy changes (govee_frame_renderer, dispatch policy
  are OUT of scope — pad/lab server, assets, controls table, lab registry only).
- Staged/tooling-only; the pad server may be restarted at YOUR round's end for
  activation (it is operator tooling, launchd-supervised) — announce via mailbox
  first.

## Chain + signals

Manager seat: design note → build (own lane or orchestrator via tmux; NO Fable
Agent-tool subagents) → adversarial review inside the round → executive gate.
Explicit-path commits; tests; three hard checks; docs per contract. Registry id
ASSIGNED by the executive at dispatch.
Signals: `/tmp/rbss_lane_signals/pad.PADOVH.report.md` + `.done` / `.blocked`.
Run straight through. SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED.
