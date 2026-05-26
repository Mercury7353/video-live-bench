import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from common import DEFAULT_OUTPUT_DIR, read_jsonl, write_jsonl
from verify_gt import compact_text


def option_supported_by_ocr(option_text: str, ocr_items: List[Dict[str, Any]]) -> bool:
    option_compact = compact_text(option_text)
    ocr_compact = compact_text(" ".join(item.get("text", "") for item in ocr_items))
    return bool(option_compact and option_compact in ocr_compact)


def verify_ocr_options(row: Dict[str, Any]) -> Dict[str, Any]:
    options = row.get("options") or []
    correct = row.get("correct_option")
    ocr_items = row.get("ocr_items", [])
    if not options or correct is None:
        return option_verdict(False, [], "missing_options", "Missing options or correct_option.")
    if not ocr_items:
        return option_verdict(False, [], "inconclusive", "No OCR evidence available.")

    supported = []
    bad_options = []
    for option in options:
        label = str(option.get("label", "")).strip()
        text = str(option.get("text", "")).strip()
        is_supported = option_supported_by_ocr(text, ocr_items)
        if is_supported:
            supported.append(label)
        if label != correct and is_supported:
            bad_options.append(
                {
                    "label": label,
                    "reason": "Distractor text appears supported by OCR evidence.",
                }
            )

    if correct not in supported:
        return option_verdict(
            False,
            bad_options,
            "correct_not_supported",
            "Correct option was not found in OCR evidence.",
        )
    if bad_options:
        return option_verdict(
            False,
            bad_options,
            "distractor_supported",
            "At least one distractor appears supported by OCR evidence.",
        )
    return option_verdict(
        True,
        [],
        "unique_correct_supported",
        "Correct option is supported and OCR evidence does not support distractors.",
    )


def option_verdict(
    unique_correct: bool,
    bad_options: List[Dict[str, Any]],
    status: str,
    reason: str,
) -> Dict[str, Any]:
    return {
        "unique_correct_tool_verified": unique_correct,
        "bad_options": bad_options,
        "option_tool_verdict": status,
        "option_tool_reason": reason,
    }


def verify_one(row: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(row)
    if row.get("evidence_status") != "ok":
        result.update(option_verdict(False, [], "skipped", f"Evidence status is {row.get('evidence_status')}."))
        return result
    task_type = row.get("task_type")
    if task_type == "OCR":
        result.update(verify_ocr_options(row))
    else:
        result.update(
            option_verdict(
                False,
                [],
                "inconclusive",
                f"Option verifier for task type {task_type} is not implemented yet.",
            )
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_evidence_packs.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "option_verifications.jsonl")
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    results = [verify_one(row) for row in rows]
    write_jsonl(args.output, results)
    counts: Dict[str, int] = {}
    for row in results:
        key = row.get("option_tool_verdict", "unknown")
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({"verified_rows": len(results), "verdict_counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
