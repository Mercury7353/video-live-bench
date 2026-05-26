import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from common import DEFAULT_OUTPUT_DIR, read_jsonl, write_jsonl


def index_by_candidate(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(row.get("candidate_id")): row for row in rows if row.get("candidate_id")}


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def review_one(
    row: Dict[str, Any],
    mcq_by_id: Dict[str, Dict[str, Any]],
    mcq_review_by_id: Dict[str, Dict[str, Any]],
    gt_by_id: Dict[str, Dict[str, Any]],
    option_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    candidate_id = str(row.get("candidate_id"))
    mcq = mcq_by_id.get(candidate_id, {})
    mcq_review = mcq_review_by_id.get(candidate_id, {})
    gt = gt_by_id.get(candidate_id, {})
    option = option_by_id.get(candidate_id, {})

    issues = []
    actions = []
    keep = True

    if not as_bool(row.get("category_aligned", True)):
        issues.append("category_mismatch")
        actions.append("drop_or_rewrite_question")
        keep = False

    if not as_bool(row.get("gt_verified", True)):
        issues.append("stage_judge_gt_not_verified")
        actions.append("verify_gt_with_tool_harness")
        keep = False

    tool_verdict = gt.get("tool_verdict")
    if tool_verdict == "contradicted":
        issues.append("tool_contradicts_gt")
        actions.append("repair_ground_truth")
        keep = False
    elif tool_verdict in {"inconclusive", "skipped"}:
        issues.append(f"gt_tool_{tool_verdict}")
        actions.append("collect_more_evidence")
        keep = False

    if not as_bool(row.get("nontrivial", True)):
        issues.append("judge_marked_trivial")
        actions.append("drop_trivial_or_rewrite_question")
        keep = False

    triviality_reasons = mcq.get("triviality_risk_reasons") or []
    if triviality_reasons:
        issues.extend(f"mcq_triviality:{reason}" for reason in triviality_reasons)
        actions.append("repair_options_or_question")
        keep = False

    if mcq and not as_bool(mcq.get("mcq_ready")):
        issues.append("mcq_not_ready")
        actions.append("repair_options")
        keep = False

    review_decision = mcq_review.get("mcq_review_decision")
    if review_decision in {"repair", "drop"}:
        issues.append(f"mcq_review_{review_decision}")
        for issue in mcq_review.get("mcq_review_issues") or []:
            issues.append(f"mcq_review_issue:{issue}")
        actions.append("repair_options_or_question" if review_decision == "repair" else "drop_or_rewrite_question")
        keep = False
    if mcq_review and not as_bool(mcq_review.get("mcq_review_keep")):
        issues.append("mcq_review_not_kept")
        actions.append("repair_options_or_question")
        keep = False

    option_verdict = option.get("option_tool_verdict")
    if option_verdict in {"correct_not_supported", "distractor_supported"}:
        issues.append(f"option_tool_{option_verdict}")
        actions.append("repair_options")
        keep = False

    direct_correct = as_bool(row.get("direct_model_correct"))
    try:
        direct_confidence = float(row.get("direct_confidence", 1.0))
    except Exception:
        direct_confidence = 1.0
    if direct_correct and direct_confidence > 0.45:
        issues.append("direct_model_not_failed")
        actions.append("do_not_count_as_hard_case")
        keep = False

    if not issues:
        actions.append("keep_hard_case")

    return {
        "candidate_id": candidate_id,
        "task_type": row.get("task_type"),
        "question": row.get("question"),
        "reference_answer": row.get("reference_answer"),
        "direct_answer": row.get("direct_answer"),
        "direct_model_correct": direct_correct,
        "direct_confidence": direct_confidence,
        "failure_mode": row.get("failure_mode"),
        "meta_keep": keep,
        "meta_issues": sorted(set(issues)),
        "meta_actions": sorted(set(actions)),
        "has_mcq": bool(mcq),
        "mcq_ready": as_bool(mcq.get("mcq_ready")) if mcq else False,
        "mcq_review_decision": review_decision,
        "mcq_review_keep": as_bool(mcq_review.get("mcq_review_keep")) if mcq_review else False,
        "gt_tool_verdict": tool_verdict,
        "option_tool_verdict": option_verdict,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judged", type=Path, default=DEFAULT_OUTPUT_DIR / "judged_cases.jsonl")
    parser.add_argument("--mcq", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_candidates.jsonl")
    parser.add_argument("--mcq-reviews", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_reviews.jsonl")
    parser.add_argument("--gt-verifications", type=Path, default=DEFAULT_OUTPUT_DIR / "gt_verifications.jsonl")
    parser.add_argument("--option-verifications", type=Path, default=DEFAULT_OUTPUT_DIR / "option_verifications.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "meta_reviews.jsonl")
    args = parser.parse_args()

    judged = read_jsonl(args.judged)
    mcq_by_id = index_by_candidate(read_jsonl(args.mcq))
    mcq_review_by_id = index_by_candidate(read_jsonl(args.mcq_reviews))
    gt_by_id = index_by_candidate(read_jsonl(args.gt_verifications))
    option_by_id = index_by_candidate(read_jsonl(args.option_verifications))
    reviews = [review_one(row, mcq_by_id, mcq_review_by_id, gt_by_id, option_by_id) for row in judged]
    write_jsonl(args.output, reviews)

    summary = {
        "reviewed": len(reviews),
        "kept": sum(1 for row in reviews if row.get("meta_keep")),
        "action_counts": Counter(action for row in reviews for action in row.get("meta_actions", [])),
        "issue_counts": Counter(issue for row in reviews for issue in row.get("meta_issues", [])),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
