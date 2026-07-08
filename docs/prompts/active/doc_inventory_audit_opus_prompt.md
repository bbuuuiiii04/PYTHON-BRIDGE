---
doc_status: active-prompt
truth_level: prompt-not-verified
last_verified_commit: f754853
last_verified_date: 2026-07-08
validation_scope: Opus 4.8 handoff prompt for a read-only docs-placement inventory audit of docs/**; contains recon findings gathered 2026-07-08 that the executing model must re-verify, not trust
---

# Opus 4.8 Prompt — Docs Inventory & Placement Audit (rb_ss_bridge_v2)

**Copy everything below the line into Opus 4.8. Run at effort `xhigh`. Set max output tokens ~64k (the final census is long).**

---

## Model & effort

You are Claude Opus 4.8 running at `xhigh` effort in the `rb_ss_bridge_v2` repo (root: `/Users/bbui/rb_ss_bridge_v2`). This is a read-only analysis job. Set a large max-output budget (~64k) — the full census covers ~293 files.

## Mission (one line)

Produce a complete, per-file inventory of every Markdown doc under `docs/`, split into **(A) active and correctly placed** vs **(B) inactive / stale / completed / superseded but sitting in the wrong folder** — so the operator can see, at a glance, exactly which "loose documents" to move and where.

**Why it matters:** the repo has an automated docs system (status headers + checker scripts + a classification index + an active-work registry), but it still leaves loose and misfiled docs scattered around — completed specs sitting in `active/`, un-sorted prompts dumped in a folder root, registry pointers that disagree with where the file actually lives. The operator wants one authoritative list of what's genuinely active vs. what's misfiled clutter. **You inventory and propose; you do not move anything.**

**Audience:** the operator (project owner, not a software engineer). Lead with plain English. No jargon. Explain the *mechanism* of your classification simply, then give the tables.

## The deliverable (exact format)

Two outputs:

1. **In chat — the actionable part, in full:**
   - A 4–6 sentence plain-English summary: how many docs total, how many are active-and-correctly-placed, how many are misfiled, and which 2–3 folders are the worst offenders.
   - **The MISFILED table** (this is the whole point — put it in chat in full, do not truncate):

     | # | Current path | doc_status (or NO-HEADER) | Why it's inactive/stale/completed | Correct folder | Confidence | Evidence |
     |---|---|---|---|---|---|---|

     Sort worst-offender folder first. "Confidence" = `confirmed` / `assumed` / `unknown` (see claim discipline). "Evidence" = the exact thing that proves it (the doc's own `doc_status`, a registry line, a `doc_index.md` classification, a checker output, or a code fact) with file:line where possible.

2. **In a file — the full reference census:** write the complete per-file table for **all ~293 docs** (every bucket, not just misfiled) to `docs/status/doc_inventory_audit_2026_07_08.md` with a proper status header (`doc_status: completed-investigation`, `truth_level: code-verified`, `last_verified_commit:` = current HEAD, today's date, a one-line `validation_scope:`). Columns: path · doc_status · folder-implied-status · verdict bucket · correct folder (if move needed) · note. Do **not** add it to `doc_index.md` or the registry — flag that as a follow-up the operator can approve.

Keep the full 293-row census out of chat; chat carries the summary + the misfiled move-list only. (The operator reads chat, not documents — so the *actionable* list lives in chat; the exhaustive census is the backing artifact.)

## The four verdict buckets — classify EVERY doc into exactly one

Account for **every** `.md` file under `docs/` — all ~293, not a representative sample. Each file lands in exactly one bucket:

- **A. Active & correctly placed** — authoritative current docs, registry-listed active work, or active prompts/plans that sit in the right folder. No action.
- **B. Misfiled — inactive/stale/completed/superseded but in the wrong folder** — the "loose documents" problem. These populate the chat MISFILED table. Each needs a proposed destination.
- **C. Inactive & correctly placed** — already in `docs/archive/**` or `docs/history/**` (location IS their status; they're header-exempt by design). No action; just count them.
- **D. Ambiguous / needs operator or code decision** — no header and content doesn't clearly map to a folder, OR status and location disagree in a way you can't resolve from evidence. List these separately with the specific question.

## How to decide "wrong folder" (the classification rules)

A doc's declared `doc_status:` implies where it should live. **Status ≠ folder = misfiled.** Apply these rules, in this priority:

1. **The active-work registry is authoritative for what "active" means.** `docs/status/active_work_registry.md` is the single place unfinished work is listed (AWR-001..AWR-144). AGENTS.md §9: *a doc is active only if it is listed there AND verified against current code.* A spec the registry marks done, or doesn't list at all, is **not** active work no matter what folder it's in.
   - **High-signal check:** the registry references ~40 spec paths (e.g. `docs/plans/active/…_spec.md`, `docs/plans/completed/…_spec.md`). Reconcile each referenced path against where the file *actually* lives. Registry says `completed/` but file is in `active/` (or vice-versa), or the path doesn't exist → concrete, high-confidence misfile. List every one.

2. **`doc_index.md` is the classification index.** `docs/architecture/doc_index.md` sections every doc into "Current authoritative / Agent OS / Current supporting / Active plans & prompts / Setup / Archive-historical." Use it as the second authority. A doc classified "archive/historical" there but living in an active folder = misfiled. A doc absent from the index entirely = flag it (the index has a maintenance rule requiring listing).

3. **Folder conventions (verified 2026-07-08 — confirm before relying):**
   - `docs/plans/active/` → only `active-*` statuses belong. A `completed-spec`, `superseded`, `superseded-spec`, or `completed-*` here is **misfiled → `docs/plans/completed/`** (or `docs/archive/plans/` if superseded).
   - `docs/plans/completed/` → `completed-*` / `superseded-*`. An `active-spec` here is misfiled → `active/`.
   - `docs/prompts/` has subfolders `active/`, `completed/`, `reviews/`. **Loose prompts sitting in the `docs/prompts/` root are the core "loose documents" problem** — each belongs in `active/`, `completed/`, or `reviews/` by its content and status. Propose which.
   - `docs/archive/**`, `docs/history/**` → historical, header-exempt (bucket C).
   - `docs/research/` → `research-*`. `docs/subsystems/`, `docs/architecture/`, `docs/status/`, `docs/setup/`, `docs/validation/`, `docs/agents/` → `current`/authoritative.

4. **No-header docs:** 81 docs carry no `doc_status:`. Archive/history no-header docs are fine (rule 3, bucket C). A no-header doc in `docs/prompts/` root, `docs/plans/**`, or `docs/research/` is either misfiled (bucket B) or ambiguous (bucket D) — decide from content and folder, and say which.

5. **Staleness is a separate, advisory axis.** "Wrong folder" (placement) is mechanical and high-confidence. "Stale content" (a doc whose code moved underneath it) is advisory — run `python3 tools/check_docs_staleness.py --report` and fold its flags in, but mark them `advisory`, not `confirmed`. Do not conflate a correctly-placed-but-stale doc with a misfiled one.

## Evidence packet (what I already found on 2026-07-08 — verify, don't trust)

Source-of-truth order (AGENTS.md §1): **code > tests > config > runtime surfaces > file tree > docs > old prompts.** If a doc's self-declared status conflicts with the registry or code, the registry/code wins and the doc is drift.

Recon already run (re-run to confirm; these are leads, not conclusions):
- **293** `.md` files under `docs/`. **212** carry a `doc_status:` header; **81** do not.
- Folder counts: `docs/plans/active/` = **56**, `docs/plans/completed/` = 17, `docs/prompts/` root = **30 loose**, `docs/prompts/active/` = 6, `docs/prompts/completed/` = 6, `docs/prompts/reviews/` = 9, `docs/research/` = 11, `docs/subsystems/` = 9, `docs/architecture/` = 15, `docs/status/` = 7, `docs/archive/` subtree + `docs/history/` = historical.
- **Smoking guns already visible (confirm each):**
  - `docs/plans/active/` contains a `superseded` doc and 22 `current` docs alongside 23 `active-spec` — several `active-spec` files name AWR items the registry may already mark landed. Reconcile each against the registry's Verify column.
  - `docs/prompts/` root: 19 no-header + 11 `doc_status: current` prompts, while `active/`/`completed/`/`reviews/` subfolders exist. These are the "loose documents everywhere."
  - Registry already points some specs at `docs/plans/completed/…` (e.g. AWR-105/106) — check whether the file is actually there.
- Checker scripts (run them, cite their output): `python3 tools/check_docs_metadata.py`, `python3 tools/check_agent_contracts.py`, `python3 tools/check_docs_drift.py`, `python3 tools/check_docs_staleness.py --report`. Note: `check_docs_metadata.py` *deliberately does not police every historical file* — it only enforces the required-doc set + headers. Placement classification is your job, not the checker's.

**Scope boundary — `docs/**` only.** These repo-root `.md` files are standard and in scope only to confirm they're fine, not to move: `README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, `PRIVATE_OPERATOR_PROFILE.md`. **Out of scope entirely:** anything under `.venv/`, `.pytest_cache/`, `node_modules/`, `.git/`, `graphify-out/`, `artifacts/`, `experiments/`, and `tools/ssfmt/captures/` (gitignored multi-GB corpus — never touch). If you spot a stray bridge-style doc outside `docs/` (e.g. a prompt left in a capture dir), mention it in one line as "stray, gitignored — leave it," and move on.

## How to work (cost & tool discipline)

- This job needs real file reads and greps, not reasoning from memory — actually open the files. Prefer `rg`/`grep`/`ls` for exact status-vs-folder checks; open a doc's first ~15 lines only when the header or its intent is unclear.
- **Fan out the bulk read.** ~293 files is too many to read serially in your own context. Dispatch read-only subagents (`bridge-triage` or `Explore`) to sweep folder-by-folder and return, per file: path, `doc_status`, and a one-line verdict + evidence line:number — **conclusions and file:line refs only, never full transcripts.** Keep the final cross-check against the registry and `doc_index.md`, and the final classification judgment, on yourself. Verify any load-bearing subagent claim (especially "this spec is completed") against the registry or code before you put it in bucket B.
- You may run the four checker scripts and read-only `git log`/`git show` to date a doc. **Do not** run the bridge, touch config, or run anything that writes.

## Hard boundaries (do not cross)

- **Read-only. Move nothing, rename nothing, edit nothing, delete nothing.** Not the docs, not `doc_index.md`, not the registry. Your output is the inventory + a *proposed* move plan. The operator (or a later Codex/Claude pass under a separate spec) executes moves — not you, not now.
- **No code changes and no runtime.** This is a docs analysis task; nothing you do may alter bridge behavior or the running process.
- **Do not "fix" the doc system's design.** If you think a folder convention or the checker is wrong, note it as a one-line follow-up suggestion at the end — don't act on it.
- Write exactly one new file: the census at `docs/status/doc_inventory_audit_2026_07_08.md`. Nothing else.

## Claim discipline

Label every verdict `confirmed` / `assumed` / `unknown`:
- `confirmed` — the doc's own `doc_status` contradicts its folder, or the registry/`doc_index.md` explicitly places it elsewhere, or a checker flags it. Cite the exact line.
- `assumed` — inferred from folder convention or content when the header is missing; state the inference.
- `unknown` — you can't tell without an operator or code decision → bucket D, with the specific question.

Never assert a spec is "completed" (and thus misfiled in `active/`) on the strength of a memory or a filename alone — confirm it against the registry's Verify column or the code. When the registry and a doc's header disagree, the registry wins and you say so.

## Success criteria (falsifiable) & stop conditions

You are done when:
1. **Every** `.md` under `docs/` appears in exactly one bucket (A/B/C/D) in the census file — the bucket counts sum to the total file count (state both numbers; they must match).
2. The chat MISFILED table lists every bucket-B doc with a concrete `Correct folder` and an evidence cell, worst-offender folder first, untruncated.
3. Every registry-referenced spec path is reconciled against its real location, and every mismatch is in the table.
4. The four checker scripts have been run and their results cited (pass/fail + any flags).
5. Counts and top-offender folders appear in the plain-English chat summary.

**Stop and report uncertainty** (don't guess) if: the registry and `doc_index.md` classify the same doc differently in a way you can't resolve, or a large batch of no-header docs has no clear correct home. List these in bucket D as explicit operator questions rather than forcing a verdict.

Do not implement any moves. Inventory and propose only.
