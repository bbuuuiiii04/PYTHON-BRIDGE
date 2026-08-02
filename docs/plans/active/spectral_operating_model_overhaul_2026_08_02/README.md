# Spectral operating-model overhaul — the review chain and the attacks that followed it

**Status: experimental — a finished design (v8) plus five later attacks that argue against
adopting it. NOTHING HERE IS ADOPTED. The spectral program is PAUSED by operator order
(2026-08-02).**

These 14 files were written loose at the repo root on 2026-08-01/02 and relocated here intact
on 2026-08-02 by exec13. **Nothing was edited**, and they reference each other by bare
filename, so they all moved together and those references still resolve.

**This README was rewritten after all 14 files were read end to end** (three independent Opus
readers, 2026-08-02 ~01:2x). An earlier version of it described the chain as arguing over
drafts v1–v4; that was wrong — it ran to **v8 and converged**, and was then attacked by five
fresh seats afterward.

## What actually happened, in order

**Part 1 — the convergence loop (COMBINED_DESTROY → ROUND_8).** Alternating Fable and Sol seats,
each attacking the version it was handed, then curing what it found. Findings per round:
**14 → 8 → 3 → 3 → 3 → 1 → 0**. Round 8 opens with the single word `AGREED` and records the
terminal verdict (`ROUND_8_fable.md:215`):

> "This design has reached its floor. Further design rounds stop reducing real risk."

**v8 is the surviving design** (`../spectral_program_operating_model_v8_2026_08_02.md`); v1–v7
are retained only as the audit trail. There is no v9 and no round is owed.

**Part 2 — the five ATTACK passes, all written AFTER round 8** (timestamps 23:40 → 00:12 vs
round 8 at 23:29, v8 at 23:16). Fresh seats, no round history. **They are unabsorbed by
anything** — every distinctive phrase in them returns zero hits in v8 and in every round file.
Four of the five converge against adopting v8 as written:

> `ATTACK_AUTONOMY_SOL.md:20-23` — "V8 is not an operating model for an autonomous agent
> organization. It is a careful run, checking, evidence, refusal, and publication protocol for
> a list-producing tool."

> `ATTACK_AUTONOMY.md:325` — "v8 is the wrong artifact for the corrected goal, and it is not
> close."

## The files

| file | what it is | keep? |
|---|---|---|
| `COMBINED_DESTROY_review.md` | opening destroy-review of v1, verdict `FAILS`, 14 findings. Origin of the chain's central argument (`:230`) **and the only cache-inventory measurements in the folder** (`:63`) | **KEEP** |
| `REVISION_ROUND_1.md` | the v2 author's 14-row response table. No new evidence; re-ruled twice and two rows overturned | redundant |
| `ROUND_2_fable.md` | attacks v2 → v3. Carries the most-quoted line in the folder (`:224-231`), but round 8 restates and attributes it | redundant |
| `ROUND_3_sol.md` | attacks v3 → v4. Contains **the chain's only reversal** — Lowkey custody "cannot be made true" (`:30-34`) — but round 4 restates it with a sharper count | redundant |
| `ROUND_4_fable.md` | attacks v4 → v5. First convergence argument; superseded by round 8's full trajectory | redundant |
| `ROUND_5_sol.md` | attacks v5 → v6. **Refutes round 4's claimed cure** (`:39-40`) | **KEEP** |
| `ROUND_6_fable.md` | attacks v6 → v7. The "true limit" ruling (`:82-92`) and the anti-recursion guard exist only here | **KEEP** |
| `ROUND_7_sol.md` | attacks v7 → v8. **Refuses to sign AGREED and kills round 6's cure** (`:47-53`). This is the round that produced the surviving design | **KEEP** |
| `ROUND_8_fable.md` | verifies v8, finds no new hole, **terminates the loop**. Sole holder of the floor verdict and the full re-audit of all seven prior rounds | **KEEP** |
| `ATTACK_NORTH_STAR.md` | attacks **the goal**, not the design. The **only** file in the overhaul that reads the actual bridge runtime — 14 code citations, all verified | **KEEP — highest value** |
| `ATTACK_HUMAN_ANGLES.md` | v8 through the operator's daily experience; the compliant-fraud walkthrough and the backfill hole exist only here | **KEEP** |
| `ATTACK_SYSTEM_ANGLES.md` | **the only file carrying measurements off this machine** — disk, time, corpus shape, economics | **KEEP** |
| `ATTACK_AUTONOMY.md` | Claude seat. Unique: the counter-example night that already worked, and the deletion argument | **KEEP** |
| `ATTACK_AUTONOMY_SOL.md` | Sol seat, same prompt, different provider family — deliberate two-family run, **~40% unique** (champion/promotion/rollback, work-conservation) | **KEEP** |

Nine KEEP, four redundant-but-harmless, **zero trash**. Nothing was archived: the four
redundant ones are small, and their supersession is only legible while the chain is intact.

**No operator words originate here.** Every operator quote in these files is a re-quote from a
primary source that still exists (the failure dossier, the program trail, PROGRAM_STATE, the
memory store), verified line by line. Nothing here is the sole custodian of anything he said.

## Two unresolved contradictions, recorded so they are not lost

1. **Scoreboard: remove or restore?** The rounds treat an internal scoreboard as a hazard and
   v8 removes it (`ROUND_8_fable.md:155`). `ATTACK_AUTONOMY.md:277-282` demands one be added
   back as internal steering currency, explicitly separate from the operator's acceptance gate.
   Both are argued well; whatever follows v8 has to choose.
2. **Offline fails closed, the runtime fails open.** `ATTACK_NORTH_STAR.md:277-281` — a moment
   the offline list refuses can still be treated as a true drop by the live path, because the
   live path re-detects independently. **Confirmed against code by exec13**:
   `smart_phrasing.py:783-797` `select_true_drops` returns its input unchanged when the runway
   filter would empty it ("Fail open" in its own docstring, AWR-257). Pre-existing and
   intentional; it matters the day any of this is wired.

## Related, already filed beside this folder

`spectral_program_operating_model_v1..v8_2026_08_02.md` (v8 current) ·
`spectral_program_failure_dossier_2026_08_02.md` (the evidence base) · registry row AWR-294.
