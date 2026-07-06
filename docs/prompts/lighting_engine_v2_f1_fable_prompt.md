---
doc_status: current
truth_level: prompt/handoff — Fable 5 prompt text only
last_verified_commit: 20c6ea5
last_verified_date: 2026-07-05
validation_scope: Claude Fable 5 prompt text only; no bridge behavior, runtime action, or hardware validation. Seams cited were verified read-only against HEAD 20c6ea5 this session.
---

# Fable 5 Prompt — LIGHTING ENGINE v2 · Feature 1 (identity + Stream Deck correction surface)

**Paste-to-Fable kickstart:** *"Read `docs/prompts/lighting_engine_v2_f1_fable_prompt.md` and execute it. Effort: high."*

---

**Target model: Claude Fable 5. Effort: `high`.**

> This is benign local software work for Brandon's DJ lighting bridge and agent workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task. Review only normal software correctness, tests, maintainability, runtime safety, and operator behavior inside the named scope.

## Mission

Own **Feature 1** of LIGHTING ENGINE v2 end-to-end: author the Codex implementation spec, drive Codex (via tmux) to implement it, and review Codex's implementation to acceptance. F1 is the **per-track color identity engine** plus the **Stream Deck correction surface** — the foundation the whole v2 experience stands on.

## Why it matters / who it's for

This is the most important build in the bridge — what the bridge exists for. It runs live, in front of a crowd, while Brandon mixes. Act as a **senior engineer for EDM performance light shows**: reason about the room and the live mix, not just the code. Brandon (the operator) is the only real acceptance gate — his eyes on the room decide. Your spec feeds Codex; your checkpoint and review feed Brandon.

## The pipeline you own — three phases, one autonomous run

1. **Author the F1 Codex spec.** Part A–E per `.claude/skills/codex-spec/SKILL.md`; satisfy its 9-point pre-handoff checklist; close every gap in the list below. Reason, do not implement.
2. **Checkpoint for Brandon.** Present the finished spec — a readiness verdict plus the plan in plain operator language — and get his go before driving Codex. This is live-critical; plan-first is his standing rule, and only he can green-light live implementation.
3. **Drive Codex, then review.** Hand the spec to Codex over tmux (repo convention: `/clear` the Codex session before each new task; Codex implements, you do not). Then review Codex's implementation — findings first, ordered by severity, each with file:line — verified against the spec, the live-safety invariants, and the v1↔v2 toggle. Iterate with Codex until it passes.

## Deliverables

- The spec at `docs/plans/active/lighting_engine_v2_f1_spec.md` (repo frontmatter; registered per the codex-spec skill).
- A driven-to-acceptance F1 implementation (by Codex) plus your review verdict — `PASS` / `PASS WITH REQUIRED FIXES` / `FAIL` — with evidence: the test suite, the change-contract's checks, and a demonstration that v2-OFF is byte-identical to v1.

## Evidence packet — source-of-truth order: code > tests > this packet > docs

**Authoritative design (locked — implement, do not re-litigate):**
`docs/architecture/LIGHTING_ENGINE_V2_DESIGN.md`. F1 scope = §2 (zones / hash / depth / dynamics / permanence), §2.4 (Stream Deck correction surface), §7 kill-matrix F1 rows, §8 color-slot contract. Operator contract: `docs/architecture/lighting_engine_v2_authority.md`.

**Verified seams (read-only against HEAD 20c6ea5 this session — treat as confirmed; re-verify any you build on):**
- Stream Deck `streamdeck_midi.py` (single file, no package): renders per-key PIL images `:527-565` (dynamic feedback IS possible), each key also emits MIDI note ch3 `:35-36,83-92`; 15 keys, live layout keys 0–5 = palette/white_sand selectors, 7 LED-mute, 8 laser-mute, 9 laser-solo, 10–13 static-look bindings, 14 rainbow `:209-247`; **only ~5 keys genuinely free — the 6 zones + white/sand + R/G/B must repurpose keys 0–5.**
- Manual color: engine emits arbitrary RGB via `fixed_rgb` + `rainbow` + `set_mode_override` `led_color_engine.py:567-581,845-850`; scale_stops = green/cyan/blue/purple/magenta/red `led_models.py:72-79`, so **pure green renders** `(0,255,0)`; white_sand already ships `fixed_rgb` `config/led_look_director.json:168-179`. **No new RGB path needed.**
- Pad gestures `led_palette_control.py`: tap = queue-for-next-track, hold = override + fade to next phrase anchor (`_override_palette_now:297-309`) + lock `:279-295`. Engine controls `lock/unlock/set_palette/queue_palette:783-809`. v1 `_lock` freezes dwell-rotation + drop-snap `led_color_engine.py:396,416` and persists across tracks; it is NOT stored or per-track.
- Identity/permanence: per-track color is a salted, re-derived seed `led_color_engine.py:373-376` (F1 replaces it with a content_id-keyed, file-backed store); first-load analysis seam `state_manager.py:263-268`.
- Slot contract `govee_frame_renderer.py`: `universal_colorizer:1026`, `_slots:42`, `resolve_fade`/`slot_colors_from|to:74,92-94`, `render_comet` name-fallback `:1882`; comet route `govee_realtime_runner.py:_compose_frame:351,364`, `EffectSpec:36-42`; `color_source` engine|baked flag `led_models.py:54,241`.
- Reset/teardown seam `beat_sync_engine.py:128-131`.

**Operator ground truth (Brandon, this session — decided, do not re-open):**
- Stream Deck pads become **6 zone selectors** (GLACIER/DEEP_POOL/TWILIGHT/ION/VOLT/EMBERCORE) + **white/sand + full R/G/B**.
- Zone pads = per-track identity **correction**; hold/lock stores it permanently, unlock-while-that-track-plays clears it; a stored correction always stamps the **active deck**.
- Manual pads (white/sand, R/G/B) = **live-only** override, arbiter rank 0 (always wins), never stored.
- **Queue = apply to the current track at the next phrase boundary** (not v1's next-track queue).
- In v2 **"lock" means store the correction** — drop v1's freeze-rotation meaning.
- **Lasers do not coordinate with the LED blackout** — they fire at drops and are already dark beforehand; laser beam scenes are Brandon's SoundSwitch work, out of F1 scope.

**Known-stale / unknowns:** any pre-2026-07-05 spec/plan; live RGB config values; Govee/Stream Deck device latency; DB-rebuild content_id stability (filepath fallback pinned). Verify before relying.

## Gaps to consider and close

**F1 — resolve in the spec and implement:**
- Stream Deck surface: gesture→intent wiring for zone pads (correction) vs manual pads (live-only); the 10-control **key layout on the 15-key deck** (repurpose 0–5; **mark operator-veto**); lock = store-correction plus its residual freeze behavior in a world with no dwell-rotation; queue = current-track-at-phrase; active-deck stamp; per-key active-zone feedback rendering.
- Correction granularity: does a zone pad set zone-only (hash picks the variant) or zone+variant — decide and justify.
- The permanence store: content_id-keyed, file-backed, holds derived identity + corrections; never silently repaints on analysis upgrade.

**Resolve as design and mark for the future F2 spec — do NOT implement in F1:**
- **Repeat/dense drop markers → family-driven.** The hardcoded `LED_MAX_DROP_IMPACTS = 2` (`led_dispatch_policy.py:41`, predecessor set `:37`, gate `_led_drop_impact_allowed:1350-1370`) must become family-driven: WALL/COMET stay full-energy across the whole chorus (every marker impactful); HOUSE keeps ~2 impactful drops then settles to `post_drop` groove. **Signal/family-driven, never a genre string** — the classifier never sees genre labels. Operator ground truth: v1 today is a fixed 2-then-post_drop (confirmed this session).
- **Live-mix edges:** blend + pre-drop blackout + correction colliding during a transition. **Mark every live-mix decision operator-veto** — this is Brandon's top live-safety concern.
- Scripted + non-scripted decks mixing into shared fixtures.

## Hard requirements — live safety

- **v1↔v2 is a clean live toggle.** F1 sits behind the §7 master switch: live-switchable, and **v2 OFF ⇒ v1 byte-identical** — no cross-engine blending, no residual v2 state on any transition path. Brandon must be able to flip to v1 mid-show and get exactly today's behavior. Your review must demonstrate this, not assert it.
- **Manual/hands always win** (arbiter rank 0). The 200 Hz push loop gains no blocking network/socket/MIDI/filesystem/subprocess I/O. No new dark-room failure mode. Honor AGENTS.md §6 and `docs/architecture/runtime_invariants.md`.

## Boundaries

- **You may:** author the spec; drive Codex via tmux; run the test suite and repo checks read-only to verify; write the spec + your review under `docs/plans/active/`.
- **You may not:** edit bridge code yourself (Codex implements); touch the running bridge or hardware; create branches/worktrees; force-push or rewrite history. Work on `main`.
- Scope: **F1 only is implemented.** F2/F3-owned gaps are resolved-as-design and parked, not built. Do not add features, refactors, or abstractions beyond what F1 needs; only validate at real boundaries; no compatibility shims — v2 is a clean toggle, not a migration.

## Claim discipline

Label every claim **confirmed / assumed / unknown / rejected**, tied to a file:line you re-checked at HEAD. This packet and any memory may be stale — code wins. Report progress only against real tool results; if the suite fails, say so with the output; state done plainly only when verified.

## Success criteria (falsifiable) / stop conditions

- Spec closes every F1 gap above, satisfies the codex-spec 9-point checklist, and encodes every F1 decision from LIGHTING_ENGINE_V2_DESIGN.md §2/§2.4/§7/§8.
- Codex's F1 implementation: full `python3 -m unittest discover tests` green; the matching change-contract's checks green; **v2-OFF proven byte-identical to v1**; manual-override and push-loop invariants intact.
- Your review verdict is explicit and evidence-tied; layout and live-mix decisions are flagged operator-veto for Brandon's live gate.
- **Stop and ask Brandon** at the phase-2 checkpoint, and only if you hit a genuine scope change, an irreversible action, or a decision only he can make. Otherwise proceed autonomously through the pipeline. Lead your checkpoint and final messages with the outcome in plain language — Brandon reads them cold.

**Do not reveal, transcribe, or explain private chain-of-thought** — give evidence-tied findings, claim labels, and verdicts only.

---
*Brandon-facing note (outside the Fable task): if any phase returns blocked by a safeguard misclassification, retry with narrower evidence and more neutral wording — never jailbreak language. Model auto-switch is off, so a blocked prompt yields nothing.*
