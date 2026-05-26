import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from common import DEFAULT_OUTPUT_DIR, read_jsonl, write_jsonl


BRITTLE_PATTERNS = [
    r"\bexact timestamp\b",
    r"\bframe number\b",
    r"\bexact frame\b",
    r"\bsingle pixel\b",
    r"\bwhat date\b",
    r"\bwhat is the date\b",
    r"\bwhich date\b",
]


def index_latest(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id:
            out[candidate_id] = row
    return out


def load_eval_indexes(paths: List[Path]) -> List[Dict[str, Dict[str, Any]]]:
    return [index_latest(read_jsonl(path)) for path in paths if path.exists()]


def as_float(value: Any, default: float = 1.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def is_correct(row: Optional[Dict[str, Any]]) -> bool:
    return bool(row and row.get("is_correct"))


def confidence(row: Optional[Dict[str, Any]]) -> float:
    return as_float(row.get("confidence") if row else None, 1.0)


def has_brittle_pattern(question: str) -> Optional[str]:
    lower = question.lower()
    for pattern in BRITTLE_PATTERNS:
        if re.search(pattern, lower):
            return pattern
    return None


def option_texts(row: Dict[str, Any]) -> List[str]:
    return [str(item.get("text", "")).strip() for item in row.get("options") or []]


def filter_one(
    row: Dict[str, Any],
    options_eval: Dict[str, Dict[str, Any]],
    direct_indexes: List[Dict[str, Dict[str, Any]]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    candidate_id = str(row.get("candidate_id"))
    issues: List[str] = []

    options_row = options_eval.get(candidate_id)
    if not options_row:
        issues.append("missing_options_only_eval")
    elif is_correct(options_row):
        if args.reject_any_options_correct or confidence(options_row) >= args.options_conf_threshold:
            issues.append("options_only_correct")
        else:
            issues.append("options_only_correct_low_confidence_warning")

    if not direct_indexes:
        issues.append("missing_direct_eval_file")
    direct_rows = [index.get(candidate_id) for index in direct_indexes]
    if any(row is None for row in direct_rows):
        issues.append("missing_direct_eval")
    for direct_row in direct_rows:
        if not direct_row:
            continue
        if is_correct(direct_row):
            if args.reject_any_direct_correct or confidence(direct_row) >= args.direct_conf_threshold:
                model = direct_row.get("eval_model", "direct")
                issues.append(f"direct_model_correct:{model}")
            else:
                issues.append("direct_model_correct_low_confidence_warning")

    brittle = has_brittle_pattern(str(row.get("question", "")))
    if brittle:
        issues.append(f"brittle_question:{brittle}")

    texts = option_texts(row)
    if len(texts) != 4:
        issues.append("bad_option_count")
    if len(set(text.lower() for text in texts)) != len(texts):
        issues.append("duplicate_options")
    if any("cannot be determined" in text.lower() or "not enough information" in text.lower() for text in texts):
        issues.append("generic_or_refusal_option")

    warning_only = {
        "options_only_correct_low_confidence_warning",
        "direct_model_correct_low_confidence_warning",
    }
    hard_issues = [issue for issue in issues if issue not in warning_only]
    out = dict(row)
    out["strict_filter_keep"] = not hard_issues
    out["strict_filter_issues"] = sorted(set(issues))
    out["options_only_pred"] = options_row.get("pred_option") if options_row else None
    out["options_only_correct"] = is_correct(options_row)
    out["options_only_confidence"] = options_row.get("confidence") if options_row else None
    out["direct_eval_summary"] = [
        {
            "model": direct_row.get("eval_model"),
            "mode": direct_row.get("eval_mode"),
            "pred": direct_row.get("pred_option"),
            "correct": direct_row.get("is_correct"),
            "confidence": direct_row.get("confidence"),
        }
        for direct_row in direct_rows
        if direct_row
    ]
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--options-eval", type=Path, required=True)
    parser.add_argument("--direct-eval", type=Path, action="append", default=[])
    parser.add_argument("--accepted-output", type=Path, default=DEFAULT_OUTPUT_DIR / "strict_accepted.jsonl")
    parser.add_argument("--rejected-output", type=Path, default=DEFAULT_OUTPUT_DIR / "strict_rejected.jsonl")
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--options-conf-threshold", type=float, default=0.35)
    parser.add_argument("--direct-conf-threshold", type=float, default=0.35)
    parser.add_argument("--reject-any-options-correct", action="store_true")
    parser.add_argument("--reject-any-direct-correct", action="store_true")
    args = parser.parse_args()

    candidates = read_jsonl(args.candidates)
    options_eval = index_latest(read_jsonl(args.options_eval))
    direct_indexes = load_eval_indexes(args.direct_eval)
    reviewed = [filter_one(row, options_eval, direct_indexes, args) for row in candidates]
    accepted = [row for row in reviewed if row.get("strict_filter_keep")]
    rejected = [row for row in reviewed if not row.get("strict_filter_keep")]
    write_jsonl(args.accepted_output, accepted)
    write_jsonl(args.rejected_output, rejected)

    issue_counts = Counter(issue for row in rejected for issue in row.get("strict_filter_issues", []))
    summary = {
        "candidates": len(candidates),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "issue_counts": issue_counts,
        "accepted_output": str(args.accepted_output),
        "rejected_output": str(args.rejected_output),
    }
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
