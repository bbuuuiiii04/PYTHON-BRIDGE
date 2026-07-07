---
doc_status: current
truth_level: operator-evidence + code-verified leads
last_verified_commit: 42c45c7
last_verified_date: 2026-07-06
validation_scope: Fable 5 investigation/fix/Codex-orchestration prompt for the 2026-07-06 evening live-run themes; prompt text only; this file changes no bridge behavior
---

# Fable 5 — Investigate tonight's live-run themes, propose fixes, orchestrate Codex

**Target model:** Claude Fable 5. **Effort:** xhigh. **This file is the prompt** — paste it, or point Fable at this path.

> This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. "Laser" and "strobe" are stage-lighting effects. Review only normal software correctness, tests, maintainability, runtime safety, and operator behavior inside the named scope.

## Mission, and why it matters

Brandon (the operator — a DJ, not a software engineer) played a ~65-minute live set tonight on the v2 lighting engine and wrote down 20 problems with wall-clock times. Claude already correlated every one against the event log and read the code, producing **7 root-cause themes with exact file:line leads** (below). Take it from diagnosis to **landed, software-tested fixes**: verify each theme against current code yourself, decide the minimal live-safe fix, write the Codex-executable spec, and drive **Codex through its tmux session** to implement and verify — one theme at a time. The lighting is the centerpiece of his rig; correctness under live mixing matters more than speed.

## Roles (hard boundary)

You **reason, verify, decide fixes, write Codex specs, orchestrate Codex, and review its output. You do not implement bridge code yourself — Codex does.** When you fan out, send those subagents to **cheaper models**; you are the only Fable-tier agent and must not spawn another. Announce nested spawns rather than running them silently.

## Usage discipline — your Fable-tier turns are expensive; spend them only on the hard part

Be conscious of your own cost and **default to delegating.** Reserve Fable-tier reasoning for the calls only you should make: re-verifying each root cause against code, deciding the minimal live-safe fix, every live-safety judgment, and the final review of what Codex produced. Push everything else down to **cheaper-tier subagents** — correlating the log timestamps, reading and grepping files to confirm the file:line leads, drafting the first pass of each Codex spec, running the test suite and the hard checks, and condensing results. Route read-only grinding (log correlation, file reads, grep) to the cheapest tier that can do it (Haiku/Sonnet) and moderate code reasoning (draft specs, confirm a mechanism) to a mid tier (Sonnet/Opus); keep only safety-critical judgment on yourself. **Batch independent investigations into one parallel fan-out** rather than a chain of serial Fable turns. A good pass has you reading a handful of subagent conclusions and making decisions — not grinding files yourself. If a subtask doesn't need Fable-level judgment, it shouldn't run on Fable.

## Source of truth

Code > tests > config > `runtime_status.py` > file tree > docs. If a doc conflicts with code, code wins. Read `AGENTS.md` first (source map §4, live-safety invariants §6, hard checks §8). **Treat every finding below as a lead to re-verify against current HEAD, not settled fact** — Brandon specifically wants you to look for yourself, not trust the handoff.

## Evidence packet

**Log for this run:** `~/Library/Logs/rb_ss_bridge/bridge-20260706-192659.jsonl` (persists across restarts; each record carries `ts` = epoch seconds and `mono` = uptime). Run 19:27–20:32, **v2 engine, direct-DMX pack mode** — the bridge owned the Enttec DMX box (`/dev/cu.usbserial-EN396681`) and SoundSwitch was **not** rendering. The run was **not** CPU-starved (`event-late=0` all night, phrase read "other" only 7%, bpm known 94%), so these are **real logic/design issues, not lag** — unlike the earlier 2026-07-06 daytime run.

**The 7 themes** (operator timestamps → Claude's verified root cause → file:line leads to confirm):

1. **Laser fires on the "2nd chorus" crossing, not the true drop; sometimes skips the true drop; self-cycles.** (7:35, 7:50, 7:54.) The laser engine treats *any* chorus/section-start as a drop trigger and re-fires on chorus→chorus up to `max_drops_in_a_row=2`; the true drop is demoted to `post_drop` when the preceding section label is wrong; `reason=drop_cycle` re-asserts the drop scene inside a 32-beat impact hold with no fresh crossing (it is **not** the inert `post_drop_cycle_beats`). Buildup lasers fire on a mere "up" label + a marker within 32 beats with no real-runway check. Leads: `drop_lifecycle.py:48-72,98-110`; `laser_director.py:462-512,574-601`; `smart_phrasing.py:298,318-334`; `config/laser_director.json` (house personality). 7:54 is the same machinery landing correctly once — that's why it feels random.

2. **Lasers keep their baked autoloop colors, ignore the palette.** (7:41, 7:52, 8:03, 8:21.) Claude verified this one deeply: the color merge **already overwrites CH8** on autoloop frames when a color snapshot exists (`soundswitch_laser_player.py:139`, `:462`), so hand-unchecking CH8 on every SoundSwitch cue is unneeded. The one real gap: the snapshot is computed **only on the tick a new LED look fires** (`state_manager.py:4171`) and **reset every tick** (`:3396`) — a one-frame blip, so ~99% of frames show the pack's baked color. **Proposed fix: hold the single engine color on every autoloop frame; CH8 only** (leave CH9/color-speed baked so autoloops keep their movement). Operator taste default: **one solid color per section** (hold from section entry), not tracking the zone mid-section. Preserve this hardware caveat: CH8 is "color/effects" on the fixture, so a full CH8 override may flatten a baked effect — flag it, don't silently kill movement. Other refs: `laser_color_engine.py:88-146`; `config/laser_color_map.json` (`enabled:true`, `fixed_ch9:null`).

3. **Named-palette taps do nothing in v2; drop looks show baked colors.** (7:47, 7:49, 7:52, 7:57, 8:04, 8:09.) In v2 the v1 named-palette buttons (crimson, blue_cyan, indigo, …) are a **no-op** — only `white_sand` plus the separate **manual** red/green/blue/rainbow pads change color (`led_palette_control.py:208-216,322-325`). ("red palette" = crimson = dead; real red is the manual pad.) Separately, drop/post-drop **DIY looks are pre-baked Govee cloud scenes on an exempt list** the color engine skips (`led_color_engine.py:612,729,1112,1154`), and cloud-DIY looks can't be recolored at all (`led_dispatch_coordinator.py:150-167`) — ~42 of 72 looks are baked/exempt, ~30 realtime looks follow color. **Blocked on a Brandon decision — see below.**

4. **Rainbow is half-wired.** (8:23, 8:30.) Exempt/baked looks ignore rainbow; single-fixture looks show one hue per cue rather than a spatial spread (`led_color_engine.py:1353-1355`), only multi-slot looks paint a real rainbow (`:1158-1159`). **Blocked on the same Brandon decision.**

5. **LEDs get stuck on one look.** (8:29, 8:30.) Looks change only on section/phrase transitions — no rotation *within* a section. On "Runaway (U & I) [Kaskade Remix]" the bridge read one long build for **76 s** (20:29:40→20:30:54) and the look froze that whole time (strips healthy, not idle, not starved). Fix direction: intra-section look rotation.

6. **No LED buildup on "Where Have You Been (Hardwell Club Mix)".** (7:32.) The buildup look fired for one frame then was repeatedly stomped by `room_blackout` (utility) + a re-firing `smart_drop_blackout` (emergency) through the whole build, so the strips sat dark. Lead (unverified): deck 2 was being loaded/scrubbed (Will Sparks → Afrojack) right then, which may be tripping the emergency blackout. Confirm the exact trigger before proposing a fix.

7. **"Pad effects incredibly delayed" + laser solo.** (8:18.) Two facts: `laser_solo` is **not logged anywhere** (observability gap — add it), and the bridge acted on every pad tap the instant it arrived (`event-late=0`), so the perceived delay is **upstream of the bridge** — the pad server (`:8766`/`:8765`) or the MIDI hop — which the bridge log cannot see.

**Known-stale / unknowns:** the earlier 2026-07-06 daytime run's 4 offline fixes are **not landed** (heartbeat still shows the dead v1 `palette`, no `zone` field); themes 6 and 7 have explicit unverified pieces named above.

## Two decisions only Brandon can make — do not decide these yourself

Before touching themes **3 and 4**, surface these plainly and pause:
1. Revive the dead v1 named-palette buttons (crimson, blue_cyan, …) in v2, or keep manual-pad-only and relabel the surface?
2. Should baked DIY drop/post-drop looks stay their fixed color by design, or become recolorable (which means moving them off the exempt list / off cloud-DIY rendering)?

## Order, scope, and the fixes that feed Codex

Do the clear-bug themes autonomously, **lasers first** (Brandon just engaged on theme 2): **2 → 1 → 5 → 6 → 7**. Pause for the two taste calls before 3 and 4. Keep every fix minimal — no refactoring, no new abstractions, no error handling for cases that can't happen, no feature flags; a bug fix doesn't need surrounding cleanup. Everything you write feeds Codex.

## Codex orchestration

Drive Codex through its existing **tmux** session — discover it with `tmux ls`; if the session name or the command convention is unclear, ask Brandon rather than guessing. **`/clear` the Codex session before each new theme.** Hand Codex **one theme's spec at a time** in the repo's Part A–E format (`.claude/skills/codex-spec/SKILL.md`). After each theme: run `python3 -m unittest discover tests` and the `AGENTS.md` §8 hard checks; confirm green and the live-safety invariants intact **before** starting the next theme. Before reporting a theme done, audit the claim against an actual command result from this session — if tests fail, say so with the output; if a step was skipped, say that.

## Live-safety (from AGENTS.md §6)

`StateManager` is the only writer of `DeckState` and owns the **200 Hz** push loop — do not let any fix add blocking network, socket, MIDI, filesystem, or subprocess I/O to that loop. Reader threads publish events, never mutate `DeckState`. The bridge is currently **down**; you don't need it running — Codex changes are gated by the test suite, and the **live gate is Brandon's eyes, not yours**. Never launch the bridge raw (`python3 -m rb_ss_bridge_v2`); it starts via the menubar only. After any restart anyone performs, exactly one bridge process must exist (`pgrep -f rb_ss_bridge_v2` returns 1). Never run `git clean -fd` in this repo.

## Claim discipline, checkpoints, success criteria

Label every load-bearing claim **confirmed / assumed / unknown / rejected**, tied to a file:line or a log line. Do not ask Brandon to accept a root cause you have not re-verified against current code. Pause for Brandon **only** on the two taste calls or a genuinely irreversible/scope-changing decision — otherwise proceed; don't stall on "shall I?".

**Done means:** each clear-bug theme (2, 1, 5, 6, 7) has a re-verified root cause, a landed Codex fix, the unittest suite and the three hard checks green, and the live-safety invariants intact; themes 6 and 7 are either fixed or reported with the specific reason they can't be fixed from the bridge side; and the two taste calls are surfaced to Brandon, not decided.

**Closing report:** this is Brandon's first look at the whole thing and he reads it cold. Open with the outcome in one plain sentence (what landed, what's green, what's waiting on him). Drop working shorthand — complete sentences, no arrow chains, each file/flag/theme its own plain-language clause. Then the one or two things you need from him.
