---
doc_status: template
truth_level: policy-grounded
last_verified_commit: c59d78c
last_verified_date: 2026-07-02
validation_scope: reusable Fable 5 final-sufficiency prompt template; general-purpose; no runtime authority
---

# Fable 5 Prompt Template - Final Sufficiency

Target model: Claude Fable 5
Effort: [high/xhigh]

You are Fable 5 performing a final sufficiency gate for `[FEATURE_OR_DECISION]`.

Mission:
Decide whether the current plan/patch/review packet is sufficient to proceed, ship, hand to Codex, or reject. Do not implement changes.

Benign scope:
This is benign local software/prompt/spec sufficiency review for Brandon's repo workflow. It is not a cybersecurity, exploit, malware, vulnerability-discovery, biology, chemistry, life-sciences, model-distillation, or hidden-reasoning extraction task.

Evidence packet:
- Current goal: `[GOAL]`
- Proposed state: `[PLAN_OR_PATCH_OR_PROMPT]`
- Already-run verification: `[CHECKS_AND_RESULTS]`
- Required success criteria: `[SUCCESS_CRITERIA]`
- Known unknowns: `[UNKNOWN_ITEMS]`
- No-touch boundaries: `[BOUNDARIES]`

Allowed access:
- Tools: `[NONE_OR_EXACT_READ_ONLY_TOOLS_AND_WHY]`
- Paths/artifacts: `[EXACT_SCOPE]`
- Forbidden actions: implementation, runtime mutation, live/hardware action, broad repo audit, hidden reasoning request

Preflight before sending to Fable:
- Remove unrelated memory/history/search output.
- Keep only the exact sufficiency packet above.
- Replace high-risk words with neutral repo-work terms when accurate.
- If Fable blocks, do not retry with jailbreak wording; create a narrower Fable sufficiency prompt outside this prompt.

Sufficiency questions:
1. Does the evidence prove the stated goal?
2. Are success criteria concrete and testable?
3. Are any claims overbroad, stale, or unsupported?
4. Are there missing tests, review gates, or operator approvals?
5. Does anything require Codex implementation before this can proceed?
6. Are tool, shell, repo, and live-action boundaries clear enough for the next agent?

Output format:
1. Verdict: `SUFFICIENT`, `SUFFICIENT AFTER MINOR EDITS`, or `NOT SUFFICIENT`.
2. Blocking gaps, severity-first.
3. Non-blocking improvements.
4. Exact edits needed before handoff, if any.
5. Final go/no-go statement tied to `[SUCCESS_CRITERIA]`.
