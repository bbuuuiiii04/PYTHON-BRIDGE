---
doc_status: current
truth_level: prompt-artifact
last_verified_commit: d2ed39c
last_verified_date: 2026-07-08
validation_scope: Fable 5 manager prompt text only; commissions offline spectral-calibration expansion + orchestrated implementation; no live process or hardware action authorized by the prompt itself
---

# Fable 5 Prompt — Spectral Calibration Expansion: Strengthen Track Preparation for LIGHTING ENGINE v2

**Target model:** Claude Fable 5 · **Effort:** `xhigh`

Paste everything below the rule into Fable. It is self-contained.

---

This is benign local software work on Brandon's DJ lighting bridge (`rb_ss_bridge_v2`, this repo): offline audio analysis of his own music library to calibrate lighting decisions. Nothing here touches security, biology, or model internals.

## Mission

Brandon: "I want to tune the spectral analysis more, with more tracks, to really strengthen it — in preparation of tracks." You are the manager for this lane, end to end: verify the current state, expand the calibration evidence across many more tracks from his library, find where today's calibration stops generalizing, then propose and orchestrate the implementation of improvements. The output feeds LIGHTING ENGINE v2 (darkness tiers, bass-forward classification, arrival/drop presentation) — the better the per-track spectral preparation, the better every automated lighting call. Brandon is the operator, not an engineer; your final report must read plainly.

## Where to start (verify against code — memories and docs may have drifted)

- Authority docs: `docs/research/spectral_audio_analysis_redesign.md` (spectral v4), `docs/research/anlz_energy_project.md`, and the v2 consumers in `docs/architecture/lighting_engine_v2_authority.md` + `LIGHTING_ENGINE_V2_DESIGN.md`.
- Code: `audio_spectral_features.py`, `spectral_cache.py`, `spectral_profile.py`, `energy_model.py`; corpus tools `tools/analyze_anlz_energy_corpus.py`, `tools/spectral_sweep.py`. These are offline-analysis surfaces; confirm what, if anything, the runtime imports from them before touching anything.
- Known state (re-verify, do not trust blindly): darkness classification was verified 6/6 with tier and bass-forward behavior on the shipped cache as of 2026-07-07; a held-out operator listening pass has been planned but never run. How many of Brandon's tracks are locally analyzable is unknown — establishing real coverage is part of the job.

## Hard rules

- **Generalization is the law (operator standing rule):** features and calibration must hold across the whole EDM catalog. Per-track hand-tuning or special-casing gets cut, not shipped. If a signal only works on some subgenres, grade it honestly (backbone / heuristic / unreliable) rather than forcing it.
- **Offline only.** No bridge restart or launch, no frames or commands to any lighting hardware or cloud, no edits to live gitignored configs. Before any heavy corpus run, check whether the bridge is live (`pgrep -f 'rb_ss_bridge_v2$'`) — if Brandon is mixing, defer heavy compute until it exits.
- **Changes that alter what the lights would do** (calibration constants, shipped cache contents) must be revertable in one commit, labeled software-tested / hardware-unvalidated, and explicitly flagged in your final report as awaiting Brandon's listening gate — you prepare a short listening sheet (a handful of tracks and moments, thumbs-up/down each) as part of the deliverable; his ear is the acceptance test.
- **Lane isolation (other agent lanes are active in this worktree TODAY):** do not modify `govee_*`, `led_*`, `state_manager.py`, `beat_sync_engine.py`, or `tools/led_pad*` — other sessions own those files right now. If your improvements genuinely require touching them, STOP that part and report the dependency back in your final summary instead of editing. Shared docs (`docs/status/active_work_registry.md`, `docs/agents/change_contracts.yml`) are being edited by parallel lanes: re-read them fresh immediately before your edit, take the next free AWR id for your registry row, and commit ONLY by explicit file paths (never `-a`, never `add -A`) — an auto-sync hook also commits in this worktree. Never use destructive git.
- **You manage; you do not implement in this session.** Orchestrate implementation and heavy corpus grinding through an idle Opus tmux session (`claude4`, `claude5`, or `claude6`; `claude`/`claude2`/`claude3` are taken): send `/clear`, then a short kickstart pointing at a written spec/task file you author, then verify it actually submitted (`tmux capture-pane`; typed prompts sometimes need one extra Enter). Subagents and orchestrators are cheaper-tier ONLY — never Fable-tier, never a second Fable session; announce every spawn. Every handoff is a written file, not a chat paraphrase.
- Do not ask any model to reveal private reasoning. Repo conventions: `AGENTS.md` §1 source-of-truth order, §7 contract-first, §8 checks; spec format lives in `.claude/skills/codex-spec/SKILL.md`.

## Deliverables, in order

1. **Current-state verification:** what the spectral pipeline actually computes today, where its calibration constants live, what the v2 engine consumes, and current corpus coverage (how many tracks analyzed vs. available). Claims labeled confirmed / assumed / unknown with file:line.
2. **Corpus expansion run:** analyze as much of the library as the tools support (orchestrated, parallelized via the Opus session). Report coverage and failures honestly (unreadable files, missing ANLZ, format gaps).
3. **Stability findings:** which calibration claims hold at scale and which drift — darkness tier boundaries, bass-forward split, arrival detection — with distributions and concrete counterexample tracks, not vibes.
4. **Tuning proposal + verdict** (`READY` / `READY WITH GAPS` / `NOT READY`): the specific changes worth making, each tied to evidence, ranked by expected live impact; explicitly list what you decided NOT to change and why.
5. **Orchestrated implementation** of the evidence-backed changes (spec file → Opus session → your adversarial review → tests + the three hard checks in `tools/` green), respecting the lane-isolation rule above.
6. **Brandon's listening sheet + plain-English final report in chat:** outcome first — what got stronger, what the numbers say, what changed on disk, what his ears still need to confirm, and one-commit rollback instructions.

## Success criteria

Coverage is a number; every calibration claim has a distribution behind it; no per-track special-casing anywhere in the diff; runtime LED/laser/SS files untouched; suite green apart from the known environmental reds; the final report readable cold by a non-engineer. Rejection conditions: implementing in your own session; touching another lane's files; shipping a calibration change without the revert path and listening-gate flag; spawning any Fable-tier agent.
