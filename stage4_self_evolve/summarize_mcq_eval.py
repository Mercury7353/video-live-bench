import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from common import DEFAULT_OUTPUT_DIR, read_jsonl


def group_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        str(row.get("eval_provider", "unknown")),
        str(row.get("eval_model", "unknown")),
        str(row.get("eval_mode", "unknown")),
    )


def accuracy(rows: List[Dict[str, Any]]) -> float:
    return round(sum(1 for row in rows if row.get("is_correct")) / len(rows), 4) if rows else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_eval_results.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_eval_summary.json")
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[group_key(row)].append(row)

    summary = []
    for (provider, model, mode), group_rows in sorted(groups.items()):
        by_task: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in group_rows:
            by_task[str(row.get("task_type", "unknown"))].append(row)
        summary.append(
            {
                "provider": provider,
                "model": model,
                "mode": mode,
                "n": len(group_rows),
                "accuracy": accuracy(group_rows),
                "task_counts": Counter(row.get("task_type", "unknown") for row in group_rows),
                "task_accuracy": {
                    task: {"n": len(task_rows), "accuracy": accuracy(task_rows)}
                    for task, task_rows in sorted(by_task.items())
                },
            }
        )

    payload = {"rows": len(rows), "summary": summary}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
