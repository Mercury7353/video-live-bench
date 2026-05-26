import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

from common import (
    DEFAULT_OUTPUT_DIR,
    parse_literal,
    read_csv_rows,
    repo_path,
    shuffled_sample,
    spans_total_duration,
    video_id_from_url,
    write_jsonl,
)


TRIVIAL_PATTERNS = [
    r"\btitle\b",
    r"\bthumbnail\b",
    r"\bstatic image\b",
    r"\bshown in the static image\b",
]


def is_answerable(row: Dict[str, str]) -> bool:
    uncertainty = parse_literal(row.get("uncertainty"), {})
    if isinstance(uncertainty, dict) and uncertainty.get("is_answerable") is False:
        return False
    answer = (row.get("reference_answer") or "").strip()
    if not answer or answer.lower() == "unanswerable":
        return False
    return True


def heuristic_nontrivial(row: Dict[str, str]) -> bool:
    question = (row.get("question") or "").lower()
    reasoning = (row.get("reasoning") or "").lower()
    if any(re.search(pattern, question) or re.search(pattern, reasoning) for pattern in TRIVIAL_PATTERNS):
        return False
    task_type = row.get("task_type", "")
    span_duration = spans_total_duration(row.get("ref_answer_span") or row.get("question_span"))
    question_tokens = len((row.get("question") or "").split())
    if task_type == "Counting":
        return question_tokens >= 8 and span_duration > 0
    if task_type in {"Spatial", "Reasoning"}:
        return question_tokens >= 7 and span_duration > 0
    if task_type == "OCR":
        return question_tokens >= 6 and span_duration > 0
    return question_tokens >= 6 and span_duration > 0


def row_to_candidate(row: Dict[str, str], index: int) -> Dict[str, Any]:
    url = row.get("url", "")
    return {
        "candidate_id": f"stage2-{index:05d}",
        "video_id": video_id_from_url(url),
        "url": url,
        "task_type": row.get("task_type", ""),
        "question": row.get("question", ""),
        "reference_answer": row.get("reference_answer", ""),
        "question_span": parse_literal(row.get("question_span"), []),
        "answer_span": parse_literal(row.get("ref_answer_span"), []),
        "harness_reasoning": row.get("reasoning", ""),
        "uncertainty": parse_literal(row.get("uncertainty"), {}),
        "bootstrap_source": "stage2_fusion_csv",
        "gt_verified": True,
        "category_aligned": True,
        "nontrivial_heuristic": True,
    }


def build_candidates(rows: List[Dict[str, str]]) -> Iterable[Dict[str, Any]]:
    for index, row in enumerate(rows):
        if not is_answerable(row):
            continue
        if not heuristic_nontrivial(row):
            continue
        yield row_to_candidate(row, index)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=repo_path("stage2_fifter_q", "outputs", "anno_qa_ref_fusion_by_question.csv"),
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "candidates.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = read_csv_rows(args.input_csv)
    candidates = list(build_candidates(rows))
    candidates = shuffled_sample(candidates, args.limit, args.seed)
    count = write_jsonl(args.output, candidates)
    summary = {
        "input_rows": len(rows),
        "candidate_rows": len(candidates),
        "output": str(args.output),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
