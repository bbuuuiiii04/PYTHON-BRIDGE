# MENUBAR overhaul brief — manager seat (operator order, 00:05 wave)

doc_status: current
truth_level: dispatch-brief
seat: `menubar` lane, Fable/HIGH (operator's explicit tier for this seat), manager
charter with full review chain (this tool LAUNCHES the show — launch-critical class).

## Operator order (verbatim): "dispatch another fable high manager to refactor and
overhaul the current menubar menu, and make sure it works alongside M2 build."

## Scope

Audit `scripts/bridge_menubar.py` at HEAD, then design + build the menu overhaul:
structure, naming, grouping, states (running/stopped/degraded visibility), and
whatever the audit shows the operator actually needs at a glance mid-show. You are
the manager: write your own design note first, dispatch a build orchestrator lane
if warranted (tmux lanes only — NO Fable Agent-tool subagents), adversarial-review
whatever builds, then signal for the executive gate.

## HARD FENCE vs the concurrent M2 build (usbm2 lane, AWR-186)

M2's spec ADDS a native menubar PURGE item (typed-confirmation flow) — that item's
FUNCTION belongs to M2. Your round owns menu STRUCTURE/UX. Rules:
- Read `docs/plans/active/usb_bridge_launcher_m2_codex_spec.md` §menubar before
  designing; leave a labeled structural SLOT for the purge item.
- No simultaneous edits to `scripts/bridge_menubar.py`: usbm2 lands its purge item
  FIRST (watch for the executive's mailbox note / usbm2.USBM2.done), then your
  structural refactor folds it in. If your build is ready earlier, stage the diff
  and hold for the executive's sequencing word.
- Coordinate through the executive mailbox (`tmux send-keys -t superman4 '...'`,
  one-liners) — never directly into usbm2's pane.

## Invariants that CANNOT move (the show depends on them)

- The menubar is how the operator STARTS the bridge: launch semantics, watcher
  integration (`scripts/ss_bridge_watcher.sh` modes, RBSS_BRIDGE_MANUAL), the
  single-process invariant (`pgrep -f 'rb_ss_bridge_v2$' | wc -l` == 1 after
  start), and the launch-profile env (fail-closed) are UNTOUCHABLE behavior.
  Structure around them freely; change none of their semantics.
- The pad/laser-pad supervision behavior (launchd relaunch) stays as-is.
- Staged-only: no bridge/process contact; the operator activates by restart.

## Deliverables + chain

Design note (docs/plans/active/), build (explicit-path commits), tests where the
menu logic is testable, docs per the change contract, three hard checks green,
adversarial review INSIDE your round (builder ≠ reviewer), then:
`/tmp/rbss_lane_signals/menubar.MBAR.report.md` + `.done` (or `.blocked` + evidence).
Registry id: ASSIGNED by the executive at dispatch. Run straight through.
SOFTWARE-VALIDATED ONLY / HARDWARE-UNVALIDATED language.
