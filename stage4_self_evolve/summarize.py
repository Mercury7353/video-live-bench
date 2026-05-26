import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from common import DEFAULT_OUTPUT_DIR, read_jsonl


def summarize(rows: List[Dict[str, Any]], hard_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "direct_probes": len(rows),
        "hard_cases": len(hard_rows),
        "hard_rate": round(len(hard_rows) / len(rows), 4) if rows else 0,
        "task_type_counts": Counter(row.get("task_type", "unknown") for row in rows),
        "hard_task_type_counts": Counter(row.get("task_type", "unknown") for row in hard_rows),
        "failure_mode_counts": Counter(row.get("failure_mode", "unknown") for row in hard_rows),
        "hard_case_preview": [
            {
                "candidate_id": row.get("candidate_id"),
                "task_type": row.get("task_type"),
                "question": row.get("question"),
                "reference_answer": row.get("reference_answer"),
                "direct_answer": row.get("direct_answer"),
                "failure_mode": row.get("failure_mode"),
                "judgement": row.get("judgement"),
            }
            for row in hard_rows[:10]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judged", type=Path, default=DEFAULT_OUTPUT_DIR / "judged_cases.jsonl")
    parser.add_argument("--hard", type=Path, default=DEFAULT_OUTPUT_DIR / "hard_cases.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "summary.json")
    args = parser.parse_args()

    rows = read_jsonl(args.judged)
    hard_rows = read_jsonl(args.hard)
    summary = summarize(rows, hard_rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
