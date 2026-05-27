import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set

from common import ensure_parent, read_jsonl


def ids_from(path: Path) -> Set[str]:
    out = set()
    for row in read_jsonl(path):
        candidate_id = row.get("candidate_id") or row.get("ok")
        if candidate_id:
            out.add(str(candidate_id))
    return out


def count_correct(path: Path) -> Dict[str, Any]:
    rows = [row for row in read_jsonl(path) if not row.get("error")]
    total = len(rows)
    correct = sum(1 for row in rows if row.get("is_correct"))
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else None,
    }


def task_counts(path: Path) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in read_jsonl(path):
        task = str(row.get("task_type") or "UNKNOWN")
        counts[task] = counts.get(task, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gt", type=Path)
    parser.add_argument("--frontier-hard", type=Path)
    parser.add_argument("--mid-tier", type=Path)
    parser.add_argument("--strict-frontier", type=Path)
    parser.add_argument("--accepted-mid", type=Path)
    parser.add_argument("--options-eval", type=Path, action="append", default=[])
    parser.add_argument("--direct-eval", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    summary: Dict[str, Any] = {}
    if args.gt:
        gt_rows = read_jsonl(args.gt)
        summary["gt_candidates"] = {
            "items": len(gt_rows),
            "videos": len({row.get("video_id") for row in gt_rows if row.get("video_id")}),
            "task_counts": task_counts(args.gt),
        }
    if args.frontier_hard:
        summary["frontier_hard_open_ended"] = {
            "items": len(read_jsonl(args.frontier_hard)),
            "ids": sorted(ids_from(args.frontier_hard)),
        }
    if args.mid_tier:
        summary["mid_tier_open_ended"] = {
            "items": len(read_jsonl(args.mid_tier)),
            "ids": sorted(ids_from(args.mid_tier)),
            "task_counts": task_counts(args.mid_tier),
        }
    if args.strict_frontier:
        summary["strict_frontier_mcq"] = {
            "items": len(read_jsonl(args.strict_frontier)),
            "ids": sorted(ids_from(args.strict_frontier)),
        }
    if args.accepted_mid:
        summary["accepted_mid_mcq"] = {
            "items": len(read_jsonl(args.accepted_mid)),
            "ids": sorted(ids_from(args.accepted_mid)),
            "task_counts": task_counts(args.accepted_mid),
        }
    summary["options_eval"] = {str(path): count_correct(path) for path in args.options_eval}
    summary["direct_eval"] = {str(path): count_correct(path) for path in args.direct_eval}

    ensure_parent(args.output)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sections": sorted(summary)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
