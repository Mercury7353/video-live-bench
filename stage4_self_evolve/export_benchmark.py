import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from common import DEFAULT_OUTPUT_DIR, read_jsonl, write_jsonl


def index_by_candidate(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(row.get("candidate_id")): row for row in rows if row.get("candidate_id")}


def reject(row: Dict[str, Any], reason: str) -> Dict[str, Any]:
    out = dict(row)
    out["export_decision"] = "reject"
    out["export_reject_reason"] = reason
    return out


def accepted_row(row: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "candidate_id": row.get("candidate_id"),
        "video_id": row.get("video_id"),
        "url": row.get("url"),
        "task_type": row.get("task_type"),
        "question": row.get("question"),
        "options": row.get("options"),
        "correct_option": row.get("correct_option"),
        "reference_answer": row.get("reference_answer"),
        "answer_span": row.get("answer_span"),
        "question_span": row.get("question_span"),
        "harness_reasoning": row.get("harness_reasoning"),
        "bootstrap_source": row.get("bootstrap_source"),
        "mcq_review_model": row.get("mcq_review_model"),
        "mcq_review_notes": row.get("mcq_review_notes"),
        "direct_model_correct": meta.get("direct_model_correct") if meta else None,
        "direct_confidence": meta.get("direct_confidence") if meta else None,
        "failure_mode": meta.get("failure_mode") if meta else None,
        "export_decision": "accept",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mcq-reviews", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_reviews.jsonl")
    parser.add_argument("--meta-reviews", type=Path, default=DEFAULT_OUTPUT_DIR / "meta_reviews.jsonl")
    parser.add_argument("--accepted-output", type=Path, default=DEFAULT_OUTPUT_DIR / "benchmark_accepted.jsonl")
    parser.add_argument("--rejected-output", type=Path, default=DEFAULT_OUTPUT_DIR / "benchmark_rejected.jsonl")
    parser.add_argument("--require-meta-keep", action="store_true")
    args = parser.parse_args()

    mcq_rows = read_jsonl(args.mcq_reviews)
    meta_by_id = index_by_candidate(read_jsonl(args.meta_reviews))
    accepted = []
    rejected = []
    for row in mcq_rows:
        candidate_id = str(row.get("candidate_id"))
        meta = meta_by_id.get(candidate_id, {})
        if not row.get("mcq_review_keep"):
            rejected.append(reject(row, f"mcq_review_{row.get('mcq_review_decision', 'not_kept')}"))
            continue
        if args.require_meta_keep and not meta.get("meta_keep"):
            issues = meta.get("meta_issues") or ["missing_meta_keep"]
            rejected.append(reject(row, ",".join(str(item) for item in issues)))
            continue
        accepted.append(accepted_row(row, meta))

    write_jsonl(args.accepted_output, accepted)
    write_jsonl(args.rejected_output, rejected)
    print(
        json.dumps(
            {
                "input_rows": len(mcq_rows),
                "accepted": len(accepted),
                "rejected": len(rejected),
                "reject_reason_counts": Counter(row.get("export_reject_reason", "unknown") for row in rejected),
                "accepted_task_counts": Counter(row.get("task_type", "unknown") for row in accepted),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
