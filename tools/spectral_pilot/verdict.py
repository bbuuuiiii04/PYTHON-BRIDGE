"""The pure verdict function — gates 1-7 and the integrated rule (spec B8).

``compute_verdict`` takes already-computed metric numbers (scoring.py produces
them) and nothing else, so the same inputs always yield the same Verdict (test
D9, D13). It implements the seven gates verbatim and the stopped-axis rule; it
invents no new thresholds.
"""
from __future__ import annotations

from .schemas import SCHEMA_VERSION, Verdict

ACTIVE_SECONDS_CEILING = 65 * 60
DECISIONS_CEILING = 113


def _g(state, *evidence):
    return {"state": state, "evidence": list(evidence)}


def _gate1(setup_failures):
    if setup_failures:
        return _g("FAIL", *setup_failures)
    return _g("PASS", "no setup failure")


def _gate2(rep):
    # contradictions (FAIL) dominate; then comparability floors (INCONCLUSIVE)
    if rep["marker_contradictions"] > 1 or rep["hardness_contradictions"] > 1 or rep["family_contradictions"] >= 1:
        return _g("FAIL", f"contradictions marker={rep['marker_contradictions']} "
                          f"hardness={rep['hardness_contradictions']} family={rep['family_contradictions']}")
    if rep["marker_repeats"] < 4 or rep["hardness_repeats"] < 3 or rep["family_repeats"] < 3:
        return _g("INCONCLUSIVE", "repeatability comparability floor unmet")
    return _g("PASS", "repeatability floors met, contradiction limits respected")


def _gate3(wl):
    reasons = []
    if wl["active_seconds"] > ACTIVE_SECONDS_CEILING:
        reasons.append(f"active_seconds={wl['active_seconds']}>{ACTIVE_SECONDS_CEILING}")
    if wl["decisions_total"] > DECISIONS_CEILING:
        reasons.append(f"decisions={wl['decisions_total']}>{DECISIONS_CEILING}")
    if wl.get("operator_stop_exhausting"):
        reasons.append("operator stopped: exhausting")
    return _g("FAIL", *reasons) if reasons else _g("PASS", "within workload ceilings")


def _availability_gate(m, *, min_calls, min_lineages, correct_delta_min, use_calls=True,
                       noncommittal_key=None):
    if m.get("stopped"):
        return _g("INCONCLUSIVE", "axis stopped at session A — availability floor unmet")
    if use_calls and m["comparable_calls"] < min_calls:
        return _g("INCONCLUSIVE", f"comparable_calls={m['comparable_calls']}<{min_calls}")
    if m["comparable_lineages"] < min_lineages:
        return _g("INCONCLUSIVE", f"comparable_lineages={m['comparable_lineages']}<{min_lineages}")
    if noncommittal_key and m.get(noncommittal_key, 0) > 4:
        return _g("FAIL", f"{noncommittal_key}={m[noncommittal_key]}>4 — two-moment family abstraction fails")
    ok = (m["correct_delta"] >= correct_delta_min and m["lineage_win_margin"] >= 4
          and m["candidate_abstentions"] <= 4)
    if ok:
        return _g("PASS", f"correct_delta={m['correct_delta']}>={correct_delta_min}, "
                          f"win_margin={m['lineage_win_margin']}, abstentions={m['candidate_abstentions']}")
    return _g("FAIL", f"correct_delta={m['correct_delta']}, win_margin={m['lineage_win_margin']}, "
                      f"abstentions={m['candidate_abstentions']}")


def _gate7(st):
    g_ok = st["genuine_central_rows"] >= 28
    h_ok = st["hardness_central_rows"] >= 28
    if not (g_ok and h_ok):
        return _g("INCONCLUSIVE", f"central rows genuine={st['genuine_central_rows']} "
                                  f"hardness={st['hardness_central_rows']} (floor 28)")
    if st["genuine_flip_gap_pp"] > 10 or st["hardness_flip_gap_pp"] > 10:
        return _g("FAIL", f"flip gap genuine={st['genuine_flip_gap_pp']}pp "
                          f"hardness={st['hardness_flip_gap_pp']}pp (>10)")
    return _g("PASS", "neither primary axis flip rate >10pp worse than baseline")


def compute_verdict(*, pilot_seed, created_from_head, input_hashes, setup_failures,
                    repeatability, workload, genuine, hardness, family, stability,
                    seed_pool_eligible_lineages) -> Verdict:
    gates = {
        "1": _gate1(setup_failures),
        "2": _gate2(repeatability),
        "3": _gate3(workload),
        "4": _availability_gate(genuine, min_calls=28, min_lineages=16, correct_delta_min=6),
        "5": _availability_gate(hardness, min_calls=24, min_lineages=14, correct_delta_min=6),
        "6": _availability_gate(family, min_calls=0, min_lineages=14, correct_delta_min=4,
                                use_calls=False, noncommittal_key="decisive_noncommittal_human"),
        "7": _gate7(stability),
    }
    states = {k: v["state"] for k, v in gates.items()}

    stopped_axes = [a for a, m in (("genuine", genuine), ("hardness", hardness), ("family", family))
                    if m.get("stopped")]
    failed_gates = [k for k, s in states.items() if s == "FAIL"]
    inconclusive_floors = [k for k, s in states.items() if s == "INCONCLUSIVE"]
    if seed_pool_eligible_lineages < 18:
        inconclusive_floors.append("seed_pool_lt_18")

    if failed_gates:
        integrated = "FAIL"
    elif all(s == "PASS" for s in states.values()) and seed_pool_eligible_lineages >= 18:
        integrated = "PASS"
    else:
        integrated = "INCONCLUSIVE"

    return Verdict(
        schema_version=SCHEMA_VERSION, pilot_seed=pilot_seed, gate_results=gates,
        integrated=integrated, failed_gates=sorted(failed_gates),
        inconclusive_floors=sorted(set(inconclusive_floors)), stopped_axes=sorted(stopped_axes),
        input_hashes=dict(input_hashes), created_from_head=created_from_head,
    )
