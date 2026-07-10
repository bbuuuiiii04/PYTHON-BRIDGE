---
doc_status: current
truth_level: prompt-only
last_verified_date: 2026-07-10
validation_scope: >
  Claude Opus 4.8 (ultracode) handoff prompt text only. No bridge behavior changed, no RE run,
  no hardware validation in authoring this prompt. Every "confirmed" label below was checked this
  session against current code / the installed binaries and then adversarially re-reviewed by four
  independent agents (verdicts folded in). The executing session MUST still re-verify against
  code+binaries — code/binary wins over this document.
---

# HANDOFF PROMPT — Rekordbox cross-version reader safety + version-extension mechanism (Opus 4.8, ultracode, GhidraMCP)

**Brandon: this file IS the prompt.** Restart the Claude Code session first (so the GhidraMCP tools load — see §3), then paste the block from `=== BEGIN PROMPT ===` to `=== END PROMPT ===` into the new Opus 4.8 session. Nothing here executes until you do that.

---

=== BEGIN PROMPT ===

**Driver model:** Brandon's pick at launch — a strong reasoning model for the orchestration seat. **Per-subtask model, effort, and context window are YOUR judgment under the cost budget in §0** — do not default everything to the biggest model. **Agentic multi-agent orchestration ON** (Workflows if this environment provides them; otherwise parallel subagents — see §3.1). Raise the max-output budget only where a task needs it.

This is read-only interoperability RE of Brandon's own, legally-installed Rekordbox and TimecodeLink on his own Mac, so his own DJ lighting bridge keeps working when Rekordbox updates. The bridge already reads Rekordbox playback state through the macOS `task_for_pid` access it uses today; you add nothing to that access.

## 0. Model, effort & context budget — COST-CONSTRAINED (read first)

Brandon is on the **$20/month Cursor plan**; every premium-model call draws from a shared **~$20 monthly API credit pool**. Spend it like it's your own money. **You** choose the model, effort, and context window for **every** sub-task and sub-agent from this roster — match the tool to the job:

- **Agentic driver / workhorse — your default for the tool-use-heavy loop** (Cursor Grok 4.5, **~$2/M in, $6/M out base**): Cursor bills it as their "most intelligent model," built for "difficult, long-running tasks that require creatively using tools" — exactly this RE + orchestration job, and the **best value** in the roster for it. Drive the per-function decompile loop, per-version verification, routine review rounds, and decompiler-output reading with this. Use **base**, not the **Fast** variant (~$4/$18, ≈3× the output cost), unless latency blocks you. **Ignore its CursorBench ranking** — Cursor disclosed an old snapshot of their own codebase leaked into its training, so it's inflated; judge by the task. (Context window / effort levels weren't stated in Cursor's post — check the picker.)
- **Mid / cross-family workhorse** (GPT 5.6 Terra, **~$2.50/M in, $15/M out** short-context, ~1.05M window): OpenAI's balanced 5.6 tier — a solid alternate driver, and because it's a *different model family* it's a strong second-opinion voice in review. Medium effort.
- **Premium — the hardest reasoning + every SAFETY adjudication (pick per step):**
  - **Opus 4.8** (~$5/$25, 1M) — Brandon's designated tier for safety-critical reasoning; the **default for the strobe/clamp safety adjudication** (§7) and the hardest RE calls.
  - **GPT 5.6 Sol** (~$5/$30 short-context, ~1.05M) — OpenAI's flagship 5.6; ≈ Opus price, different family → the best **cross-family second opinion** on a hard RE claim or a safety verdict.
  - **Fable 5** (~$10/$50, 1M) — Anthropic's most capable, but the **priciest in the roster (~2× Opus)** *and* its safety classifiers can **false-positive and refuse security-adjacent RE framing** (the repo's `fable-prompt-writer` skill has the benign-framing handling). For most premium RE/safety work here, Opus 4.8 or GPT 5.6 Sol is cheaper with no refusal risk — reserve Fable for a step that genuinely needs it.
  - High/xhigh effort only where it changes the answer; `max` rarely (overthinks with diminishing returns).
- **Cheap / fast — bulk mechanical work** (Composer 2.5, still offered): `otool`/`strings`/`nm`, symbol dumps, table diffs, boilerplate tests, doc edits. Low effort.

**Cross-family adversarial coverage:** when you run the ≥3 refute-prompted skeptics on a safety claim or a derived offset (§8), spread them across model *families* — e.g. Opus 4.8 + GPT 5.6 Sol + Grok 4.5 — not three of the same model. Different families catch failure modes same-family redundancy misses. (Token prices above are the underlying model list prices; confirm what Cursor actually charges from your $20 pool in the picker — it may apply its own request multiplier.)

Rules:
- **Cheapest model + lowest effort that does the sub-task correctly wins.** Escalate a tier only when the cheaper one demonstrably cannot.
- **Context window: large only when the task needs it** (whole-binary cross-refs, a multi-file safety trace). Give scoped sub-tasks a normal window — a big context on a small task is wasted spend.
- **HARD EXCEPTION — never cheap out on safety.** Any step that decides whether a clamp bounds every tempo path, whether the reader fails closed, or whether a strobe surface is covered runs on a **premium model at high effort**, cost notwithstanding. Cost discipline never overrides the §7 floor (matches Brandon's standing rule: safety-critical reasoning stays on a high tier).
- If the credit pool is a hard limit, **do the cheap, high-information phases first** (§6.1 premise, §7 strobe floor) and tell Brandon where the spend went before committing premium budget to the deep rekordbox-binary RE.

## 1. Mission (one line)

Make the `rb_ss_bridge_v2` Rekordbox memory reader **provably safe across every supported Rekordbox version**, and build a **repeatable mechanism to add new versions**, by reverse-engineering how TimecodeLink derives its per-version offsets — under strict and adversarial multi-agent review.

**Why it matters:** Brandon (operator, not an engineer) drives real lasers/strobes/LEDs from this bridge. A garbage memory read must **never** produce a dangerous flash rate, and when Rekordbox updates to a build the bridge has never seen, the bridge must **degrade safely** and be **quickly extendable**. Output is for Brandon and for the bridge codebase.

## 2. Definition of DONE (falsifiable stop condition)

You are finished **only** when each point is backed by evidence you produced this session:

1. **Strobe floor exists and is tested (the core guarantee).** A garbage or out-of-range BPM/beat cannot produce a flash rate above a safe ceiling on **any** version, regardless of read quality, on **every bridge-controlled strobe surface in scope** (§7). This is version-independent and is the load-bearing safety claim.
2. **Per-version safety, honestly scoped.** For every supported Rekordbox version (every row in `rb_offsets.py`), the reader either reads correct values or fails closed such that **no memory-derived tempo/beat reaches a strobe surface** (note §4: the position scanner and live-BPM scanner run regardless of version — "inert reader" alone does not cover them). State explicitly, per version, whether correctness was **binary-verified** (binary on disk), **live-confirmed** (installed + run), or **proven-by-construction/degrade-safe** (no binary, relies on fail-closed + the §7 floor). Do not claim verification you did not perform.
3. **Version-extension mechanism** exists, is tested, documented, and adversarially reviewed: a new supported version can be added and validated by a defined procedure, and an unknown version cannot reach a strobe surface.
4. **All software tests pass** (`python3 -m unittest discover tests`); report the baseline count before/after.
5. **Strict + adversarial review converged** (§8) with its bounded stop reached — surviving residual unknowns recorded, not hidden.
6. You wrote a **plain-English safety statement + residual-unknowns list** for Brandon (§10).

**Live-confirm is operator-owned, not a gate you satisfy.** You cannot drive Rekordbox playback and watch the rig. Your job is to *stage and script* the exact live-confirm procedure and hand it to Brandon (§10); "live-confirmed" in DONE #2 is filled in by Brandon, not you. If you cannot prove a point you own, **you are not done** — state exactly what is unproven and stop. Do not paper over a gap.

## 3. FIRST ACTIONS — before any reverse engineering

1. **Confirm both substrates are live (two separate STOP checks):**
   - **GhidraMCP:** `claude mcp list` must show `ghidra ✔ Connected` and a ghidra decompile/list-functions tool must be callable. Its HTTP backend needs Ghidra running with the target program open — confirm `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/` is not `000`. Two Ghidra projects already exist in `~/Desktop/Ghidra Projects/`: **`TimecodeLink RE`** (TL 0.0.31 arm64 slice already imported+analyzed, program node `TimecodeLink_arm64` — open this for the TL work) and **`Rekordbox Mixer RE`** (for the rekordbox-binary work; check whether `rekordbox` is already imported before re-importing the 268 MB binary). If ghidra tools are not callable, **STOP** and tell Brandon the session was not restarted or Ghidra is not open.
   - **Workflow/ultracode:** confirm the Workflow tool is callable. **If it is not, do NOT silently downgrade to a single inline pass.** Run the fan-out phases by spawning multiple independent subagents in the same turn (per-function decompile, per-version verify, per-claim skeptics) and run the review passes as discrete sequential rounds. The adversarial depth in §8 is **required regardless of which orchestration primitive is present.**
2. **Surface the ONE role decision to Brandon and wait.** Default = **produce the RE findings + a Codex-executable spec, and do NOT edit production bridge code** (repo standing rule: Codex implements bridge code). Only if Brandon explicitly says "implement directly this session" do you edit bridge code — and then only behind the planned resolver seam, with tests + adversarial review. The RE, the design, the tests, and the review are yours either way.
3. **Re-verify the entire Evidence Packet (§4) against current code and the installed binaries.** This handoff may be stale. **Code and the binaries win.** Flag every disagreement.

## 4. Evidence packet — labeled, tied to how it was checked (RE-VERIFY EVERYTHING)

Source-of-truth order (`AGENTS.md` §1): executable code > tests > config > runtime surfaces > file tree > docs > old prompts. Binaries on disk win over any prose about them.

**`confirmed` (checked 2026-07-10 this session, code + binaries):**
- Reader is isolated in `rb_state_reader.py` + `rb_memory.py` + `rb_offsets.py`. `rb_offsets.py` embeds an **arm64** table for exactly **5 builds — 7.2.8 / 7.2.10 / 7.2.11 / 7.2.13 / 7.2.14**. Unknown version → `load_offsets_for_version` returns `None` → `make_rb_state_reader` returns an **inert `RBStateReader`**.
- **Fail-closed is partial, not total.** `make_rb_state_reader` is version-gated (inert on unknown), but in `__main__.py` **`LiveBPMService()` (~:1126) and `RBMemoryReader(...)` (~:1617) are constructed UNCONDITIONALLY** and run independent memory-scan threads regardless of Rekordbox version. So on an unknown/unsupported build the scan-based tempo/position surface is **not** proven inert. The live-BPM scanner is validated only to `LIVE_BPM_MIN 40 .. LIVE_BPM_MAX 250` (`live_bpm.py:40-41`).
- **The BPM value that reaches SoundSwitch does NOT all pass through `d.meta.bpm`.** In `state_manager.py`: `send_bpm(dk, bpm)` (~:4641, :4648) and `send_beat(dk, bpm, …)` (~:4750) carry a computed `bpm`; **`send_live_bpm_follow(active, pending_live_bpm)` (~:4685)** carries `pending_live_bpm` — the memory-**scanned** live BPM (from the live-BPM scanner) — and then sets `bpm = pending_live_bpm`. So a clamp on `d.meta.bpm` at the write points would **not** bound the live-follow path. (The parked plan §4.3's "one clamp bounds every downstream tempo" is **wrong** — do not trust it.)
- **Per-version chain structure is NOT uniform.** Each block = 1 master line + 4 decks × (bpm, pos, track_info, anlz). `track_info` final is `…F0 4` (inline) on 7.2.8/10/11/13 but `…F0 0` (heap) on **7.2.14**; `anlz` final is `3F0`, **except 7.2.8 has an extra trailing `0`**. **7.2.11 ALONE carries extra `MIXER_*`/`CFX_*` chains** (upfader/LOW-EQ/CFX filter); they are `Optional`, `None` on the other four — so active-deck-authority and filter-knob-lighting are 7.2.11-only and must degrade safely elsewhere. [`rb_offsets.py:49-197`]
- The read-side filter is `if not (0.0 < v < 1000.0)` at **`rb_state_reader.py:825`** (not :690). There is **no upper BPM clamp and no flash-frequency ceiling** today — verify, then add per §7.
- The resolver seam is **PLANNED, not built.** Today's reality: `load_offsets_for_version(version) → RBOffsetVersion | None`, and `RBStateReader` already treats `None`-vs-populated uniformly. The names `FieldResolver` / `FieldSet` / `ProcessMemorySource` exist **only in the parked plan doc, nowhere in code** (grep confirmed). Build the resolver; do not assume it exists.
- Brandon's installed Rekordbox = **7.2.11.0342** (in the table — reader works on his machine today). **Only this one build's binary is on disk** (`/Applications/rekordbox 7/rekordbox.app/Contents/MacOS/rekordbox`, Mach-O universal x86_64+arm64, ~268 MB). The binaries for 7.2.8/10/13/14 are **absent** — this bounds what can be binary-verified (see §8).
- **TimecodeLink 0.0.31** installed at `/Applications/TimecodeLink.app`. Binary **NOT stripped** (~2862 arm64 symbols). Embeds the table as Qt resources `:/qt/qml/TimecodeLink/resources/offsets-macos` **and** `offsets-macos-x86_64`; its arm64 table = the **same 5 versions/same chains** the bridge has. Still contains `"Rekordbox %1 is not yet supported."` / `"No offsets for Rekordbox %1"` / `"VersionUnsupported"` → exact-match then refuse; no fallback string found. Key symbols: `OffsetManager::selectVersion(QString)` @`0x1000a8fa4`, `OffsetManager::loadOffsetsFile(QString)` @`0x1000a7d60`, `ProcessFinder::getRekordboxVersion()` @`0x1000abb5c`, `ProcessFinder::getRekordboxBaseAddress(pid)` @`0x1000ad8c4`, `MemoryReader::followPointerChain(base,QList,final)` @`0x10013fb08`. Bundled comments name an OFFLINE toolchain: `tools/rekordbox/static_discover.py`, `tools/rekordbox/validate_offsets.py`, `kb/runbooks/rekordbox-new-version.md`, `timecodelink-py/data/offsets-macos`. **TimecodeLink source is NOT on disk** — only the `.app`.
- The bridge already ships a **runtime memory-scan seed** TL lacks: `live_bpm.py` (`_scan_region`, `LiveBPMCandidate.scan_candidates`, tolerance/Hz validation) and `rb_memory.py` (`_scan_objc_zone`, `_i32_moving_candidates`, `_strict_eval_candidate`). The repo mirrors TL's data at `docs/data/offsets-macos.yaml` + `offsets-macos-x86_64.yaml`.

**`assumed` (prove or refute before relying):**
- The hop/final chain structure is *largely* stable within 7.2.x, so adding a build is *mostly* re-deriving base addresses **plus** any convention change (like 7.2.14 inline→heap). A lead, not a fact — prove it by comparing all 5 known versions field-by-field, and decompiling the walker.
- TL "works across all 7.2.xx" because its author **refreshes the table per release via the offline `static_discover.py` toolchain** — a maintained table, not a runtime adaptive resolver (consistent with the refuse-strings). **UNKNOWN:** whether a TL newer than 0.0.31 genuinely auto-adapts. Only 0.0.31 is installed and it does not — ask Brandon / check the vendor before assuming a runtime mechanism exists to copy.

## 5. Scope, forbidden actions, tools

**In scope:** macOS **arm64**, cross-**version** safety + a version-extension mechanism for Rekordbox 7.2.x.

**Out of scope — name once, do not design, do not let the resolver seam foreclose:** Windows / x86_64 cross-**platform** (blocked: no Windows binary; virtual-MIDI creation fails on Windows — parked plan §1.3/§7); Raspberry-Pi standalone. Keep the planned `FieldResolver`/`ProcessMemorySource` seam (plan §1.2) so a Windows reader can slot in later, but **do not foreclose** it and build nothing Windows this run.

**Forbidden:**
- **Do NOT modify, patch, re-sign, or inject into the Rekordbox binary or process.** RE is read-only (Ghidra static analysis; `otool`/`nm`/`objdump`/`strings`; `vmmap`/`sample` only on Brandon's own running process the way the reader already attaches). No `DYLD_INSERT_LIBRARIES`, no Frida into Rekordbox, no SIP/hardened-runtime changes, no DRM anything. (TL's installer patches Rekordbox to add `get-task-allow`; **you do not** — the bridge has its own access path.)
- **No live-show testing.** Test Rekordbox session only. Reason through the live-mixing scenario before any runtime change.
- After any bridge (re)start: `pgrep -f rb_ss_bridge_v2 | wc -l` must be `1`. Launch via the menubar/watcher, never raw `python3 -m rb_ss_bridge_v2`.
- No blocking I/O in the 200 Hz push loop. `StateManager` stays the sole `DeckState` writer. `RBStateReader._tick_deck()` enqueues `ANLZ_PATH` before `TRACK_LOADED`.
- No git branches/worktrees/PRs, no force-push, no history rewrite, never `git clean -fd`. Never commit secrets/IPs/device IDs/live config/backup files.

**Tools:** GhidraMCP (read-only RE); CLI binutils; repo read + edits (production edits only under the §3.2 exception, behind the seam, with tests); the Workflow tool (or the subagent fallback in §3.1); targeted web research on Mach-O RE, Qt resource layout, Rekordbox internals. Before committing docs/routing changes run `tools/check_docs_metadata.py`, `check_agent_contracts.py`, `check_docs_drift.py`; find each code change's contract in `docs/agents/change_contracts.yml` first (§7 anti-drift rule).

## 6. Reverse-engineering plan (verify, don't theorize — every claim tied to a decompilation or a command)

Run each phase's fan-out via Workflow (or the §3.1 subagent fallback). Cheapest-and-most-decisive first.

1. **Settle the premise.** Decompile `OffsetManager::selectVersion` + `loadOffsetsFile` (open the `TimecodeLink RE` Ghidra project); confirm 0.0.31 exact-matches-then-refuses vs. any tolerance. Extract TL's embedded `offsets-macos` resource in full, diff against `rb_offsets.py`. Resolve the "newer TL?" unknown with Brandon. **Output:** a proven statement of what TL does across versions.
2. **Recover only what is actually in the binary — and know what is NOT.** The offline discovery tool `static_discover.py` is **NOT compiled into TimecodeLink.app** — only its OUTPUT (the table) and the RUNTIME read path ship. Decompiling `ProcessFinder::getRekordboxBaseAddress` / `getRekordboxVersion` / `MemoryReader::followPointerChain` tells you how offsets are **used and selected** and how the runtime module base is found — it does **NOT** yield the per-version RVA-derivation algorithm (`getRekordboxBaseAddress` only finds the loaded module base and applies the static RVAs like `0x04E18998`; it does not compute them). **The per-version base-anchor invariant must be reverse-engineered from the REKORDBOX binary itself** — what those `0x04Exxxxx` RVAs point at (data symbol / vtable / string cross-reference / code pattern). Validate the invariant against the one installed build (7.2.11): prove each 7.2.11 table base lands where the invariant predicts. **Do not claim the version-extension mechanism is "recovered" on TL evidence alone.** **Output:** a defined, testable procedure to derive a new version's fields from a rekordbox binary.
3. **Build the resolver seam.** Per plan §1.2/§2: keep the per-version table as the reliable baseline; **build** `FieldResolver.resolve(version)` (it does not exist yet); make the discovery procedure a swappable resolver behind it; `RBStateReader` already handles `None`-vs-populated uniformly. Decide with evidence whether the extension mechanism is (a) an **offline tool** emitting a new table row (TL's model, lower risk) or (b) a **runtime scanner** on the existing `live_bpm.py`/`rb_memory.py` seed (more ambitious). Recommend one; build one.
4. **Per-version correctness + degradation.** For each of the 5 versions, define which fields exist and how missing fields (e.g. mixer/CFX outside 7.2.11) degrade safely; prove the reader fails closed on any read failure.

## 7. Live-safety floor (land this regardless of RE outcome — it is the guarantee)

The one hard floor: **a bad reading must never drive a dangerous strobe.** Defense in depth:

1. **Clamp at the EMIT boundary, not `d.meta.bpm`.** Clamp the outgoing tempo where every path converges on the sends — the `bpm`/`pending_live_bpm` locals immediately before `send_bpm`/`send_beat`/`send_live_bpm_follow` (`state_manager.py` ~:4641–:4750), and/or inside `osl_output.send_bpm`/`send_beat` and the SSE `send_live_bpm_follow`. This must bound **both** the computed-timing `bpm` **and** the scanner-derived `pending_live_bpm` (which bypasses `d.meta.bpm` and is bounded only 40..250 today). Make the range operator-tunable (leave the knob — a real edge reading must not be silently eaten). A clamp on `d.meta.bpm` alone is insufficient and does not satisfy this.
2. **Hard flash-rate ceiling** at the in-bridge periodic-emit boundary (LED strobe rate, and any other bridge-computed flash rate): cap effective flash Hz regardless of BPM×subdivision. **Build and test against a safe default now** (photosensitive-safety guidance ≈ 3 flashes/sec) so DONE #1 and the §9 tests are reachable without waiting on Brandon; surface the exact ceiling to him as *tuning of an already-safe default*, not a gate on completion.
3. **Cover the scanners.** Because `RBMemoryReader` and `LiveBPMService` run regardless of version (§4), prove that on an unknown/unsupported build no memory-derived tempo/beat can reach a strobe surface — the emit-boundary clamp (#1) is the natural single choke point; confirm it sits downstream of every scanner path.

**Boundary honesty (scope the safety claim, do not overclaim):** the bridge cannot clamp SoundSwitch's own authored effect rates — only the tempo/beat it feeds SS (clamp #1 covers that). The **native pack-player / `soundswitch_frame_sender` path renders DMX strobe frames inside the bridge** (parked plan operator note, §38) and is itself a bridge-controlled strobe surface — but it is **out of scope for this run**; name it as a known, uncovered surface so the final safety statement scopes "safe" to SS-app-mode feed + LED/laser emit and does not claim to cover bridge-rendered pack frames.

## 8. Orchestration + review doctrine (ultracode — apply recursively; bounded so it terminates)

- **Fan out** (Workflow, or §3.1 subagent fallback): per-function decompilation; per-version verification; the review passes. Default `pipeline`; barrier only when a stage needs all prior results. **Pick each fan-out agent's model/effort/context per §0** — cheap models (Composer 2.5) for mechanical decompile-reading and per-version bulk checks; a premium model at high effort for the safety-claim adjudication and the final clamp review. Never route a safety adjudication to a cheap tier.
- **Strict review:** every reverse-engineered offset/field and every code change gets an independent verifier that re-derives it **from the binary/code**, not from your notes.
- **Adversarial review:** for each safety claim and each derived offset, spawn ≥3 independent skeptics **prompted to REFUTE**, defaulting to "refuted" under uncertainty; a claim survives only on majority non-refute. Use perspective-diverse verifiers (correctness / does-it-fail-closed / does-it-reproduce-on-the-binary).
- **Scope the review to what is verifiable this session.** Only 7.2.11's binary is on disk. The "re-derive-from-binary" strict review and the refute-default adversarial review apply to versions whose binary is obtainable this session (7.2.11, plus any build you can legitimately obtain/import). **For absent-binary versions the claim under review is the fail-closed-safety claim** (inert-on-failure + version-independent §7 floor), **NOT offset correctness** — offset correctness for those is explicitly "proven-by-construction / unverified, degrade-safe" (matches DONE #2). Do not let skeptics refute an absent-binary correctness claim forever; review the safety claim instead.
- **Bounded stop (prevents infinite loops).** "Nothing new" = no finding that **changes a verdict** (a repeated refutation is not new). Cap each phase at **≤4 review rounds** or two consecutive dry rounds, whichever first; then record surviving residual-unknowns and move on. Tie fan-out breadth to your output budget. This mirrors the DONE-level escape hatch — the review must be able to end.
- **Do not assume, theorize, or overstate — recursively.** Unlabeled or unverified claims from a sub-agent are rejected. "It should work" is not evidence. Give every sub-agent a *verified* evidence packet, explicit scope ("this function only", "this version only"), claim labels, and falsifiable success criteria.

## 9. Documentation + stress testing (part of DONE)

- **Stress tests** (add to `tests/`, no new frameworks): garbage/out-of-range BPM — including a scanner-path value via the live-follow send — is clamped before it leaves the bridge; flash-Hz ceiling holds at extreme BPM×subdivision against the safe default; unknown version → no memory-derived tempo/beat reaches a strobe surface, bridge still starts; version-string edge cases (4-component `7.2.11.0342` truncation, empty, malformed); per-version field presence (mixer/CFX absent outside 7.2.11 degrades safely); the discovery procedure reproduces the known 7.2.11 row.
- **Docs:** write/refresh the reader/RE spec (the artifact plan §7 deferred); update every doc the change contract lists; refresh the `rekordbox_readers` subsystem card and the parked plan's status; fold the outstanding Fable review findings R1–R11 named in the plan's front-matter. Chat is Brandon's surface — put the plain-English summary in your final message, not "see the doc."
- **Report** the unittest baseline before/after and the exact commands you ran.

## 10. Claim discipline + final report

Label every load-bearing claim `confirmed` / `assumed` / `unknown`, each tied to a decompilation, a command, or a file:line. No hidden chain-of-thought — evidence-tied rationale, labels, and verdicts only. End with: (1) a plain-English safety statement for Brandon — what is safe, on which versions, and by which evidence class (binary-verified / live-confirmed / proven-by-construction), **explicitly scoped** to SS-app-mode + LED/laser emit and noting the pack-player surface is not covered; (2) the residual-unknowns list; (3) what you changed and where; (4) the exact operator next-actions — the staged live-confirm procedure for his 7.2.11 session, and the flash-Hz ceiling to tune; (5) which models/effort/context you used per phase and roughly how much of the credit pool that spent (§0), so Brandon can see where the budget went.

Lead with the outcome. When you can recommend, recommend — don't survey options you won't pursue.

=== END PROMPT ===

---

### Brandon-facing note (not part of the prompt)
**Cost note:** the prompt now leads with a §0 budget section — you're on the $20 Cursor plan, so it tells the agent to pick models/effort/context by its own judgment from your roster (Fable 5, GPT 5.6 SOL, GPT 5.6 TERRA, Composer 2.5, Cursor Grok 4.5, Opus 4.8), cheap models for bulk work and premium only for the hard reasoning — with a hard carve-out that the *safety* adjudication always uses a premium model at high effort, cost notwithstanding. It also reports where the credit pool went. One assumption to correct if wrong: the roster is Cursor's, so I wrote the orchestration to work whether you run this in Cursor or Claude Code — if it's specifically Cursor, its background-agent flow stands in for the "Workflow" mentions.

This is the finalized version — I ran a 4-lens adversarial review over my first draft and folded in every fix I could verify against the code. The biggest catch: the clamp site the old plan named (`d.meta.bpm`) would **not** have caught the live-BPM-follow path that sends a memory-scanned tempo straight to SoundSwitch, so the prompt now clamps at the emit boundary and explicitly covers the scanner threads. It also stops the review loop from running forever on the four Rekordbox versions whose binaries aren't on your disk, drops the stale line numbers, and fixes the roles default to "spec for Codex unless you say implement directly." The one question it asks you at the very start is that roles choice. Say the word if you want scope changed (e.g. include the x86_64 table) before you run it.
