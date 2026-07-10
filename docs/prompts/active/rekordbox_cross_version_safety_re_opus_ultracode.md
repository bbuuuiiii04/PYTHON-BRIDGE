---
doc_status: current
truth_level: prompt-only
last_verified_date: 2026-07-10
validation_scope: >
  Claude Opus 4.8 (ultracode) handoff prompt text only. No bridge behavior changed, no RE run,
  no hardware validation in authoring this prompt. Every "confirmed" label below was checked this
  session against current code / the installed binaries; the executing session MUST re-verify
  against code+binaries (code/binary wins over this document).
---

# HANDOFF PROMPT — Rekordbox cross-version reader safety + version-extension mechanism (Opus 4.8, ultracode, GhidraMCP)

**Brandon: this file IS the prompt.** Restart the Claude Code session first (so the GhidraMCP tools load — see §0), then paste the block from `=== BEGIN PROMPT ===` to `=== END PROMPT ===` into the new Opus 4.8 session. Nothing here executes until you do that.

---

=== BEGIN PROMPT ===

**Model:** Claude Opus 4.8 · **Effort:** xhigh · **ultracode ON** (author and run Workflows for the substantive phases) · Set a large max-output budget (~64k). This is benign local software work on Brandon's own machine: making his own DJ lighting bridge keep working when his own, legally-installed Rekordbox updates. The bridge reads Rekordbox playback state on Brandon's own Mac through a macOS-sanctioned, admin-granted `task_for_pid` mechanism the bridge already uses today. Reverse engineering here is read-only static/dynamic analysis of software Brandon owns, for interoperability of his own tool. There is no exploit, no DRM bypass, no evasion, no third party.

## 1. Mission (one line)

Make the `rb_ss_bridge_v2` Rekordbox memory reader **provably safe across every supported Rekordbox version**, and build a **repeatable mechanism to add new versions**, by reverse-engineering how TimecodeLink derives its per-version offsets — under strict and adversarial multi-agent review.

**Why it matters:** Brandon (operator, not an engineer) drives real lasers/strobes/LEDs from this bridge. A garbage memory read must **never** produce a dangerous flash rate, and when Rekordbox updates to a build the bridge has never seen, the bridge must **degrade safely** and be **quickly extendable** — the way TimecodeLink stays current across the 7.2.x line. Output is for Brandon and for the bridge codebase.

## 2. Definition of DONE (this is your stop condition — falsifiable)

You are finished **only** when you can state, each point backed by evidence you produced this session:

1. **Safety across supported versions.** For every supported Rekordbox version (every row in `rb_offsets.py`), the reader either (a) reads correct values, or (b) fails closed to an inert reader — and in **no** case can it emit a tempo/beat that drives an unsafe strobe rate. "Supported" = in the table. Live-confirm on the version(s) actually installed (currently 7.2.11); for versions not installed, prove safety by test + code review + the version-independent strobe floor, and **say explicitly** which versions were live-confirmed vs. proven-by-construction. Do not claim live validation you did not run.
2. **The strobe floor exists and is tested** (§7): a garbage or out-of-range BPM/beat cannot produce a flash rate above the operator-set ceiling, on any version, regardless of read quality.
3. **The version-extension mechanism exists**, is tested, documented, and adversarially reviewed: a new supported version can be added and validated by a defined procedure, and an unknown version fails closed.
4. **All software tests pass** (`python3 -m unittest discover tests`), with the pre-existing baseline count reported before/after.
5. **Strict + adversarial review passed** on every reverse-engineered offset and every safety claim (§8).
6. You have written a **final safety statement + a residual-unknowns list** in plain English for Brandon.

If you cannot prove any of these, **you are not done** — state exactly what is unproven and stop. Do not paper over a gap.

## 3. FIRST ACTIONS — before any reverse engineering

Do these in order; do not skip to RE.

1. **Confirm tooling is live.** Run `claude mcp list` — `ghidra` must show `✔ Connected` and its tools must be callable (search your tool list for a ghidra decompile/list-functions tool). If the tools are not callable, **STOP** and tell Brandon: the session was not restarted, or Ghidra is not open. GhidraMCP's HTTP backend needs Ghidra running with the target program open (server on `http://127.0.0.1:8080/`). Confirm with `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/` (000 = down). There is an existing Ghidra project `~/Desktop/Ghidra Projects/Rekordbox Mixer RE` — check whether `rekordbox` and/or `TimecodeLink` are already imported+analyzed there before importing (analysis of the 268 MB rekordbox binary is slow).
2. **Surface the ONE role decision to Brandon and wait:** "Do I implement the bridge-code changes directly this session (operator-granted exception to the Codex-implements rule), or do I produce the RE + a Codex-executable spec and drive Codex for the edits?" The repo standing rule is Codex implements bridge code; Brandon's request to "orchestrate implementation" leans toward direct. Default to **direct implementation behind the seam with tests + adversarial review** only if he confirms; otherwise author the Codex spec. Either way the RE, the design, the tests, and the review are yours.
3. **Re-verify the entire Evidence Packet (§4) against current code and the installed binaries.** This handoff may be stale. **Code and the binaries win over this document.** Flag every disagreement.

## 4. Evidence packet — labeled, tied to how it was checked (RE-VERIFY EVERYTHING)

Source-of-truth order (repo `AGENTS.md` §1): executable code > tests > config > runtime surfaces > file tree > docs > old prompts. Binaries on disk win over any prose about them.

**`confirmed` (checked 2026-07-10 this session):**
- The reader is isolated: `rb_state_reader.py` + `rb_memory.py` + `rb_offsets.py`. `rb_offsets.py` embeds an **arm64** offset table for exactly **5 builds — 7.2.8 / 7.2.10 / 7.2.11 / 7.2.13 / 7.2.14**. Unknown version → `load_offsets_for_version` returns `None` → `make_rb_state_reader` returns an **inert reader** (fail-closed; bridge still runs, direct events stop). [`rb_offsets.py`; parked plan §2.1]
- **Per-version structure is NOT uniform — do not assume "only the base addresses change":** each block = 1 master line + 4 decks × (bpm, pos, track_info, anlz). `track_info` final offset is `...F0 4` (inline) on 7.2.8/10/11/13 but `...F0 0` (heap pointer) on **7.2.14** (documented convention change). `anlz` final is `3F0`, **except 7.2.8 has an extra trailing `0`** (`3F0 0`). [`rb_offsets.py:49-157`]
- **7.2.11 ALONE carries extra `MIXER_*` and `CFX_*` chains** (upfader / LOW-EQ / CFX filter). They are `Optional` fields, `None` on the other four versions. So **active-deck-authority and filter-knob-lighting features are 7.2.11-only today** — on other supported versions those features have no data and must degrade safely. [`rb_offsets.py:108-117,186-197`]
- Brandon's installed Rekordbox = **7.2.11.0342** (in the table — the reader works on his machine today). Binary: `/Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox` — Mach-O **universal (x86_64 + arm64)**, ~268 MB. [`plutil`, `file`]
- **TimecodeLink 0.0.31** is installed at `/Applications/TimecodeLink.app`. Its binary is **NOT stripped** (~2862 arm64 symbols). It embeds the offset table as **Qt resources** `:/qt/qml/TimecodeLink/resources/offsets-macos` **and** `offsets-macos-x86_64`. Its arm64 table = **the same 5 versions and the same chains** the bridge has. It still contains the strings `"Rekordbox %1 is not yet supported."`, `"No offsets for Rekordbox %1"`, `"VersionUnsupported"` → exact-version-match then refuse; **no fallback/nearest-version string was found**. Key symbols to decompile: `OffsetManager::selectVersion(QString)` @`0x1000a8fa4`, `OffsetManager::loadOffsetsFile(QString)` @`0x1000a7d60`, `ProcessFinder::getRekordboxVersion()` @`0x1000abb5c`, `ProcessFinder::getRekordboxBaseAddress(pid)` @`0x1000ad8c4`, `MemoryReader::followPointerChain(base,QList,final)` @`0x10013fb08`. TL's own bundled comments name its offline toolchain: `tools/rekordbox/static_discover.py` (finds base addresses per new build), `tools/rekordbox/validate_offsets.py` (validates with tracks on all 4 decks), `kb/runbooks/rekordbox-new-version.md`, and a Python sibling `timecodelink-py/data/offsets-macos`. [`nm`, `strings`, `otool` this session]
- **TimecodeLink source is NOT on disk** — only the compiled `.app`. So the discovery logic must be recovered from the TL binary (it has symbols) plus the rekordbox binary. [`find` over `/Users/bbui`]
- The bridge already ships a **runtime memory-scan discovery seed** that TL lacks: `live_bpm.py` (`_scan_region`, `LiveBPMCandidate.scan_candidates`, tolerance/Hz candidate validation) and `rb_memory.py` (`_scan_objc_zone`, `_i32_moving_candidates`, `_strict_eval_candidate` plausibility gating) already do discover-by-scan-and-validate for BPM and deck-2 position. [`rg`]
- The repo already mirrors TL's data at `docs/data/offsets-macos.yaml` + `docs/data/offsets-macos-x86_64.yaml`. [`find`]
- **GhidraMCP was repaired this session** (its venv broke when Homebrew upgraded python@3.14; rebuilt → `✔ Connected`). But MCP tools load at **session start**, and its backend `:8080` was **down** (Ghidra not running) at handoff. [`claude mcp list`, `curl`, `pgrep`]

**`assumed` (label as such; prove or refute before relying):**
- The hop/final chain structure is *largely* stable within the 7.2.x line, so adding a new build is *mostly* re-deriving base addresses **plus** any convention change (like 7.2.14's inline→heap). This is a lead, **not a fact** — prove it by comparing all 5 known versions field-by-field and by decompiling the walker, before designing around it.
- TL "works across all 7.2.xx" because its author **refreshes the table per release** via the offline `static_discover.py` toolchain — a maintained table, not a runtime adaptive resolver. (Consistent with the refuse-strings + the plan's §2.3 "refresh path.")
- The live-safety clamp sites the parked plan names — `state_manager.py:3304` (BPM_UPDATE), `state_manager.py:2363` (track-load), read filter `rb_state_reader.py:690` (`0<bpm<1000`), LED strobe emit in `beat_sync_engine.py` — are from the plan doc; re-verify line-by-line against code.

**`unknown` (must be resolved during the run):**
- **Is there a TimecodeLink newer than 0.0.31 that genuinely auto-adapts to any 7.2.xx build?** Only 0.0.31 is installed and it does not. Ask Brandon and/or check the vendor before assuming there is a runtime mechanism to copy. If none exists, "match TL" means "build the offline discovery tool," not "copy a runtime resolver."
- **Exactly how does `static_discover.py` find the per-version base anchors** — what do those anchor addresses reference inside the rekordbox binary (an exported symbol? a vtable? a string cross-reference? an `adrp`/`add` code pattern)? Source is absent; recover it from the TL binary + the rekordbox binary. This is the crux of true version-extension.
- **Does `OffsetManager::selectVersion` have any tolerance/nearest path?** The disassembly was not completed this session; strings imply a hard refuse. Decompile it to settle it.
- Relationship of the arm64 vs x86_64 tables (TL ships both) — informs a later x86_64/Windows effort only; out of scope now (see §5).

## 5. Scope, forbidden actions, tools

**In scope:** macOS **arm64**, cross-**version** safety + a version-extension mechanism for Rekordbox 7.2.x.

**Out of scope — name once, do not design, but do not let the seam foreclose them:** Windows / x86_64 cross-**platform** (blocked: no Windows binary present; virtual-MIDI port creation fails on Windows — see parked plan §1.3, §7); Raspberry-Pi / no-Rekordbox standalone. The parked plan `docs/plans/active/cross_platform_portability_plan.md` already holds the Windows half; keep the `FieldResolver` / `ProcessMemorySource` seam (plan §1.2) so a Windows reader can slot in later, but build nothing Windows this run.

**Forbidden actions:**
- **Do NOT modify, patch, re-sign, or inject into the Rekordbox binary or process.** RE is read-only (Ghidra static analysis; `otool`/`nm`/`objdump`/`strings`; and, only if needed for dynamic confirmation, `vmmap`/`sample` on Brandon's own running process the way the existing reader already attaches). No `DYLD_INSERT_LIBRARIES`, no Frida into Rekordbox, no SIP/hardened-runtime changes, no DRM anything. (Note: TL's own installer patches Rekordbox to add `get-task-allow`; **you do not** — the bridge already has its access path.)
- **No live-show testing.** Use a test Rekordbox session only. Reason through the live-mixing scenario before any runtime change (repo rule).
- After any bridge (re)start: verify **exactly one** process — `pgrep -f rb_ss_bridge_v2 | wc -l` must be `1` (SoundSwitch won't autorotate without the bridge). Use the menubar/watcher launch path, never raw `python3 -m rb_ss_bridge_v2`.
- Do not put blocking network/socket/MIDI/filesystem/subprocess I/O into the 200 Hz push loop. `StateManager` remains the sole `DeckState` writer. `RBStateReader._tick_deck()` must enqueue `ANLZ_PATH` before `TRACK_LOADED`.
- No git branches/worktrees/PRs, no force-push, no history rewrite, never `git clean -fd`. Never commit secrets, local IPs, device IDs, live config, or backup files.

**Tools allowed:** GhidraMCP (read-only RE); CLI binutils (`otool`/`nm`/`objdump`/`strings`/`vmmap`/`plutil`/`codesign -d`); repo read + edits (production edits only if Brandon granted the direct-implementation exception in §3.2, and only behind the seam with tests); the Workflow tool for orchestration; targeted web research on Mach-O RE, Qt resource layout, and Rekordbox internals. Run `tools/check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py` before committing docs/routing changes; find each code change's contract in `docs/agents/change_contracts.yml` first (repo §7 anti-drift rule).

## 6. Reverse-engineering plan (verify, don't theorize — every claim tied to a decompilation or a command)

Phase order is cheapest-and-most-decisive first. Run each phase's fan-out as a Workflow (§8).

1. **Settle the premise.** Decompile `OffsetManager::selectVersion` + `loadOffsetsFile`; confirm whether 0.2.31 exact-matches-then-refuses or has any tolerance. Extract TL's embedded `offsets-macos` resource in full and diff it against `rb_offsets.py`. Resolve the "newer TL?" unknown with Brandon. **Output:** a proven statement of what TL actually does across versions.
2. **Recover the discovery mechanism.** Decompile `ProcessFinder::getRekordboxBaseAddress` + `getRekordboxVersion` + `MemoryReader::followPointerChain`, and reverse how the per-version **base anchors** (e.g. the `04Exxxxx` values) are located in a rekordbox binary — i.e. what invariant `static_discover.py` keys on. Validate the invariant against the one installed build (7.2.11) in Ghidra: prove that each table base for 7.2.11 lands where the invariant predicts. **Output:** a defined, testable procedure to derive a new version's fields from a rekordbox binary.
3. **Design the seam + resolver.** Per parked plan §1.2 / §2: keep the per-version table as the reliable baseline; expose `FieldResolver.resolve(version)`; make the discovery procedure a swappable resolver behind it; `RBStateReader` handles `None` and a populated `FieldSet` identically (it already does). Decide, with evidence, whether the extension mechanism is (a) an **offline tool** that emits a new table row (TL's model, lower risk) or (b) a **runtime scanner** built on the existing `live_bpm.py`/`rb_memory.py` seed (more ambitious). Recommend one; do not build both.
4. **Per-version correctness + degradation.** For each of the 5 supported versions, define exactly which fields exist and how missing fields (e.g. mixer/CFX absent outside 7.2.11) degrade **safely**. Prove the reader fails closed on any read failure.

## 7. Live-safety floor (land this regardless of RE outcome — it is the guarantee)

Per parked plan §4, the one hard floor: **a bad reading must never drive a dangerous strobe.** Today there is a read filter `0<bpm<1000` and a per-flash duration cap, but **no upper BPM clamp and no flash-frequency ceiling** — verify this against code, then add, defense-in-depth:
1. **Source BPM clamp** at the single `StateManager` fan-out owner (the BPM write points) to a plausible DJ range, operator-tunable (leave the knob — a real edge reading must not be silently eaten).
2. **Hard flash-rate ceiling** at the in-bridge periodic-emit boundary: cap effective flash Hz regardless of BPM×subdivision. The exact ceiling is an **operator decision** (medically-safe ~3 Hz vs. a club cap) — surface it to Brandon; the clamp architecture is fixed regardless. Be honest about the boundary: the bridge cannot clamp SoundSwitch's own authored effects — only the tempo/beat it feeds SS.
This floor is version-independent and is what lets you claim "safe across supported versions" even for versions you cannot live-test. Land it early and test it hard.

## 8. Orchestration + review doctrine (ultracode — apply this discipline recursively to every sub-agent)

- **Use Workflows** for: per-function decompilation fan-out; per-version verification (5 versions in parallel); and the review passes. Default to `pipeline`; use a barrier only when a stage genuinely needs all prior results.
- **Strict review loop:** every reverse-engineered offset/field and every code change gets an independent verifier that re-derives it from the binary/code, not from your notes.
- **Adversarial review loop:** for each safety claim and each derived offset, spawn ≥3 independent skeptics **prompted to REFUTE it**, defaulting to "refuted" under uncertainty; a claim survives only on majority non-refute. Give perspective-diverse verifiers (correctness / does-it-fail-closed / does-it-reproduce-on-the-binary) rather than identical ones.
- **Apply the opus-prompt-writer discipline to every sub-agent you spawn:** hand each a *verified* evidence packet, an explicit scope ("this function only", "this version only"), claim labels (`confirmed`/`assumed`/`unknown`), and falsifiable success criteria. Sub-agents that read binaries return structured findings + exact addresses, not prose.
- **Do not assume, do not theorize, do not overstate — recursively.** An unverified inference is labeled `assumed` and blocks nothing until proven. "It should work" is not evidence. If a sub-agent returns an unlabeled claim, reject it.
- **Loop-until-dry** on the review: keep spawning finders until two consecutive rounds surface nothing new before you declare a phase safe.

## 9. Documentation + stress testing (part of DONE, not optional)

- **Stress tests** (add to `tests/`, no new frameworks): garbage/out-of-range BPM is clamped before any `send_bpm`/LED-rate call; flash-Hz ceiling holds at extreme BPM×subdivision; unknown version → inert reader, no crash, bridge still starts; version-string edge cases (4-component `7.2.11.0342` truncation, empty, malformed); per-version field-presence (mixer/CFX absent outside 7.2.11 degrades safely); the discovery procedure reproduces the known 7.2.11 row.
- **Docs:** write/refresh the reader/RE spec (the artifact parked plan §7 deferred); update every doc the change contract lists (`docs/agents/change_contracts.yml`), the `rekordbox_readers` subsystem card, and the parked plan's status; fold the outstanding Fable review findings R1–R11 referenced in the plan's front-matter. Chat is Brandon's surface — put the plain-English summary in your final message, not "see the doc."
- **Report** the unittest baseline before/after and the exact commands you ran.

## 10. Claim discipline + final report

Label every load-bearing claim `confirmed` / `assumed` / `unknown`, each tied to a decompilation, a command, or a file:line. No hidden chain-of-thought — evidence-tied rationale, labels, and verdicts only. End with: (1) a plain-English safety statement for Brandon (what is safe, on which versions, live-confirmed vs. proven-by-construction); (2) the residual-unknowns list; (3) what you changed and where; (4) the exact next operator action if any (e.g. a live test on his 7.2.11 session, or picking the flash-Hz ceiling).

Lead with the outcome. When you can recommend, recommend — don't survey options you won't pursue.

=== END PROMPT ===

---

### Brandon-facing note (not part of the prompt)
This hands the whole cross-version job to a fresh Opus 4.8 session that will have the GhidraMCP tools (which this session could not call — they load at session start). It bakes in everything I verified today, tells that session to re-verify it all against the code and binaries, and makes it prove safety rather than assert it. The one thing it asks you at the start is whether it implements the bridge changes itself or hands them to Codex. If you want it scoped tighter or wider (e.g. include the x86_64 table too), say so and I'll revise before you run it.
