import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from common import DEFAULT_OUTPUT_DIR, read_jsonl, video_id_from_url, write_jsonl


def row_video_id(row: Dict[str, Any]) -> str:
    return str(row.get("video_id") or row.get("videoId") or video_id_from_url(str(row.get("url", ""))))


def load_seen(paths: Iterable[Path]) -> Set[str]:
    seen: Set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        if path.suffix == ".jsonl":
            rows = read_jsonl(path)
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
        for row in rows:
            if isinstance(row, dict):
                video_id = row_video_id(row)
                if video_id:
                    seen.add(video_id)
    return seen


def load_stage0_rows(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}")
    rows = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        video_id = row_video_id(item)
        if not video_id:
            continue
        rows.append(
            {
                "candidate_id": f"stage0-{index:05d}",
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "publishedAt": item.get("publishedAt"),
                "duration": item.get("duration"),
                "category1": item.get("category1"),
                "parent_category": item.get("parent_category"),
                "keyword": item.get("keyword"),
                "seed_source": str(path),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "video_pool_candidates.jsonl")
    parser.add_argument("--exclude", type=Path, action="append", default=[])
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--seed", type=int, default=27)
    args = parser.parse_args()

    seen = load_seen(args.exclude)
    rows = [row for row in load_stage0_rows(args.input) if row["video_id"] not in seen]
    random.Random(args.seed).shuffle(rows)
    selected = rows[: args.limit]
    write_jsonl(args.output, selected)
    print(
        json.dumps(
            {
                "input": str(args.input),
                "excluded_video_ids": len(seen),
                "available_new_rows": len(rows),
                "written": len(selected),
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
