# Fable 5 Prompt — Logging viewer launch fix + operator-experience review (AWR-125 follow-up)

**Paste everything below the line into Claude Fable 5. Target model: Claude Fable 5. Effort: xhigh.**

*(Brandon-facing note, not part of the prompt: if this gets blocked, retry with a narrower evidence
packet and more neutral wording — never jailbreak language.)*

---

You own the operator experience of the just-built AWR-125 logging system in Brandon's DJ lighting
bridge (`rb_ss_bridge_v2`, `/Users/bbui/rb_ss_bridge_v2`). Two jobs this run, in order:

1. **Fix a launch regression (pre-approved — do it immediately):** starting the bridge from the
   menubar no longer opens the log viewer window. Diagnose root cause first, then fix.
2. **Strict operator-experience review of the whole logging system** — visual intuitiveness,
   inattentive-ADHD fit, practicality, accuracy, usability, aesthetics — then deliver an
   operator-friendly report and **STOP. Nothing from the review may be implemented until Brandon
   replies with which items he approves.** Implement only the approved items, then close out.

> This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is
> not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry,
> life-sciences, model-distillation, or hidden-reasoning extraction task. Review only normal
> software correctness, tests, maintainability, runtime safety, and operator behavior inside the
> named scope.

## Why this matters

The logging overhaul (AWR-125) shipped software-complete: one JSONL event stream (`bridge_log.py`),
a four-lens curses viewer (`bridge_view.py`), one monitor window opened by the watcher. Brandon has
inattentive ADHD; the viewer exists so he can glance mid-set and instantly know what the rig should
be doing and whether anything broke. The readability contract is written down and is the review's
ground truth — but a contract on paper isn't a screen that feels effortless in a dark booth, and
Brandon's first real look already caught one gap the build reviews missed (an all-white feed, fixed
in `249b475`). Your review is the pass that treats his eyes as the acceptance test.

## Part 1 — the launch bug (fix authorized now)

Symptom [confirmed, operator, 2026-07-05]: menubar start → bridge runs, but no viewer window
appears. Started after the W7 watcher rework (`4f4c1ad`) and the reopen-guard change (`18689e9`).

Evidence: `scripts/ss_bridge_watcher.sh` — `open_monitor` (osascript that opens Terminal running
`"$PYTHON" "$REPO_ROOT/bridge_view.py"`; note W7 switched its heredoc from quoted to **unquoted**
for variable expansion, with hand-traced backslash escaping), `monitor_open` (pgrep for
`RBSS_BRIDGE_MONITOR` or `bridge_view\.py`), the manual-mode branch (menubar sets
`RBSS_BRIDGE_MANUAL=1`), and both `! monitor_open` reopen guards.

Root-cause candidates, all [unknown] — verify, don't assume: (a) the unquoted-heredoc osascript
escaping renders wrong at runtime (`bash -n` can't validate the AppleScript string it builds);
(b) macOS automation permission — osascript→Terminal from the watcher/menubar context can fail
silently; (c) `monitor_open` false-positives: `pgrep -f` matches any process whose command line
merely *contains* the pattern (an editor, an agent session, a test run touching
`bridge_view.py`), making the watcher believe a monitor already exists; (d) manual-branch ordering.
Check the watcher's own log lines in `/tmp/bridge.log` (`[watcher]` prefix) for what actually
happened at launch.

Fix constraints: watcher/viewer files only; keep the one-window semantics (close-viewer ≠
stop-bridge; watcher reopens a missing viewer); make `monitor_open` robust against
substring-coincidence matches if (c) is implicated. `bash -n` plus a real isolated test of the fix.

## Part 2 — the operator-experience review

Review the whole logging surface Brandon touches, strictly and with evidence, across his named
dimensions: **visual intuitiveness, inattentive-ADHD friendliness, practicality, accuracy,
usability, aesthetics.** Surfaces: the four screens + header + alert strip in `bridge_view.py`
(colors, the line grammar, latching, keys, staleness, filter); the actual message texts of every
`perf(`/`health(` emit site (are they instantly parseable at a glance, or still engineer-speak?);
whether SHOW genuinely answers "what should the rig be doing / is anything broken" on real data;
the first-run experience (window size/font, what a fresh operator sees before any records).

Ground truth documents: `docs/architecture/logging_authority.md` (the 9-rule ADHD readability
contract + latched-alert contract — review against it, and also review whether the *contract
itself* has gaps his dimensions expose), `docs/subsystems/logging.md`. Real data: the bridge may be
running — read `~/Library/Logs/rb_ss_bridge/current.jsonl` (read-only) and render real records
through the viewer's pure layer (`format_line`, `lens_of`, `LatchState`) to judge with actual
stream content, not fixtures. Mock-render before/after screen fragments in the report so Brandon
can see each proposal instead of imagining it. Parallel subagents are fine for breadth
(token-frugal); judgment stays yours.

## The report (the gate)

Deliver in chat, operator-voice (plain words, no walls of text, no jargon): one short paragraph on
the bug fix (what was broken, what you changed, how you proved it), then the review as a **ranked,
numbered list** grouped MUST / SHOULD / NICE — each item: what he'd *see* change (before → after,
mock lines where visual), why it helps (tied to one of his dimensions), and effort (S/M/L). Keep
the digest under one screen; detail may follow below it. End with: "Reply with the numbers you
approve (or 'all' / 'none')." Then **stop and wait.** Implement only what he approves, one commit
per item; anything not approved is recorded as rejected in the closing summary, not implemented.

## Boundaries

- **The bridge may be live.** Never start, stop, restart, signal, or run a second bridge process;
  never touch MIDI/DMX/Govee/SoundSwitch/hardware. Brandon owns restarts. You may launch
  `bridge_view.py` directly and test `open_monitor`'s osascript in isolation (a Terminal window is
  harmless; close what you open).
- Code changes limited to: `scripts/ss_bridge_watcher.sh`, `bridge_view.py`, their tests, and — for
  approved wording items only — the message text of existing `perf(`/`health(` calls (text only:
  no trigger, level, guard, data-field, or timing changes; light output must stay byte-identical).
  No new dependencies. Approved contract-affecting changes update
  `docs/architecture/logging_authority.md` + `docs/subsystems/logging.md` in the same commit.
- Suite green after every commit (`python3 -m unittest discover tests`; baseline 3189 OK / 5
  skipped / 1 expected failure) + the three hard doc checks. Commit by explicit paths only — the
  repo's auto-sync hook commits anything left dirty, and a parallel session may be working. Never
  use `git stash` in this repo.

## Claim discipline & success criteria

Label load-bearing claims confirmed / assumed / unknown / rejected, tied to file:line or observed
output. Done means: the viewer opens on a menubar bridge start (root cause named with evidence, not
just "works now"); the report covers every named dimension with at least one concrete finding or an
explicit "no finding" per dimension; every proposal has a visible before→after; nothing beyond the
bug fix changed before Brandon's approval; approved items landed with green suite + checks; the
closing summary lists implemented / rejected / deferred by number.
