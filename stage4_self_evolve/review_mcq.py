import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import (
    DEFAULT_OUTPUT_DIR,
    GeminiClient,
    extract_gemini_text,
    extract_json,
    extract_legacy_vectorengine_keys,
    get_env_keys,
    read_jsonl,
    write_jsonl,
)
from prompts import MCQ_REVIEW_PROMPT


def bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return default


def make_client(args: argparse.Namespace) -> Optional[GeminiClient]:
    if args.heuristic_only:
        return None
    if args.provider == "vectorengine":
        keys = get_env_keys("VECTORENGINE_API_KEY", "VECTORENGINE_API_KEYS")
        if args.use_legacy_vectorengine_keys:
            keys.extend(extract_legacy_vectorengine_keys())
    else:
        keys = get_env_keys("GEMINI_API_KEY", "GOOGLE_API_KEY")
    return GeminiClient(
        provider=args.provider,
        model=args.model,
        api_keys=keys,
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
    )


def heuristic_review(row: Dict[str, Any]) -> Dict[str, Any]:
    issues = list(row.get("triviality_risk_reasons") or [])
    if not row.get("mcq_ready"):
        issues.append("mcq_not_ready")
    options = row.get("options") or []
    correct = row.get("correct_option")
    if len(options) != 4:
        issues.append("not_four_options")
    labels = [item.get("label") for item in options]
    if correct not in labels:
        issues.append("correct_label_missing")
    texts = [str(item.get("text", "")).strip().lower() for item in options]
    if len(set(texts)) != len(texts):
        issues.append("duplicate_option_text")
    decision = "keep" if not issues else "repair"
    if "correct_label_missing" in issues or "not_four_options" in issues:
        decision = "drop"
    return {
        "category_aligned": True,
        "gt_supported": True,
        "nontrivial": not issues,
        "unique_correct": "duplicate_option_text" not in issues and "correct_label_missing" not in issues,
        "distractors_plausible": not issues,
        "option_leakage": bool(issues),
        "decision": decision,
        "issues": sorted(set(issues)),
        "notes": "heuristic MCQ review",
    }


def review_one(client: Optional[GeminiClient], row: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    if client is None:
        return heuristic_review(row)
    prompt = MCQ_REVIEW_PROMPT.format(
        task_type=row.get("task_type", ""),
        question=row.get("question", ""),
        reference_answer=row.get("reference_answer", ""),
        harness_reasoning=row.get("harness_reasoning", ""),
        options=json.dumps(row.get("options", []), ensure_ascii=False),
        correct_option=row.get("correct_option", ""),
    )
    response_text = client.generate(prompt, temperature=0.0, response_mime_type="application/json")
    model_text = extract_gemini_text(response_text)
    return extract_json(model_text)


def merge_review(row: Dict[str, Any], review: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    merged = dict(row)
    issues = review.get("issues") or []
    if not isinstance(issues, list):
        issues = [str(issues)]
    decision = str(review.get("decision", "repair")).lower()
    if decision not in {"keep", "repair", "drop"}:
        decision = "repair"
    merged.update(
        {
            "mcq_review_model": "heuristic" if args.heuristic_only else args.model,
            "mcq_review_provider": "heuristic" if args.heuristic_only else args.provider,
            "mcq_review_decision": decision,
            "mcq_review_issues": issues,
            "mcq_review_notes": review.get("notes", ""),
            "mcq_review_category_aligned": bool_value(review.get("category_aligned"), True),
            "mcq_review_gt_supported": bool_value(review.get("gt_supported"), True),
            "mcq_review_nontrivial": bool_value(review.get("nontrivial"), False),
            "mcq_review_unique_correct": bool_value(review.get("unique_correct"), False),
            "mcq_review_distractors_plausible": bool_value(review.get("distractors_plausible"), False),
            "mcq_review_option_leakage": bool_value(review.get("option_leakage"), True),
        }
    )
    merged["mcq_review_keep"] = (
        decision == "keep"
        and merged["mcq_review_category_aligned"]
        and merged["mcq_review_gt_supported"]
        and merged["mcq_review_nontrivial"]
        and merged["mcq_review_unique_correct"]
        and merged["mcq_review_distractors_plausible"]
        and not merged["mcq_review_option_leakage"]
    )
    return merged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_candidates.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_reviews.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--provider", choices=["vectorengine", "google"], default="vectorengine")
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--use-legacy-vectorengine-keys", action="store_true")
    parser.add_argument("--heuristic-only", action="store_true")
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    if args.limit is not None:
        rows = rows[: args.limit]
    client = make_client(args)
    results = [merge_review(row, review_one(client, row, args), args) for row in rows]
    write_jsonl(args.output, results)
    counts: Dict[str, int] = {}
    for row in results:
        decision = row.get("mcq_review_decision", "unknown")
        counts[decision] = counts.get(decision, 0) + 1
    print(
        json.dumps(
            {
                "reviewed": len(results),
                "kept": sum(1 for row in results if row.get("mcq_review_keep")),
                "decision_counts": counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
