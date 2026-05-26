import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import DEFAULT_OUTPUT_DIR, read_jsonl, video_id_from_url, write_jsonl


def row_video_id(row: Dict[str, Any]) -> str:
    return str(row.get("video_id") or video_id_from_url(str(row.get("url", ""))))


def ffprobe_duration(path: Path) -> Optional[float]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        return float(json.loads(proc.stdout).get("format", {}).get("duration") or 0)
    except Exception:
        return None


def load_manifest_rows(paths: List[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        rows.extend(read_jsonl(path))
    return rows


def best_manifest_by_id(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        video_id = row_video_id(row)
        if not video_id:
            continue
        current = out.get(video_id)
        if current is None or (row.get("local_video_path") and not current.get("local_video_path")):
            out[video_id] = row
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, action="append", default=[])
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_OUTPUT_DIR / "video_cache")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "valid_video_pool.jsonl")
    parser.add_argument("--min-duration-sec", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    by_id = best_manifest_by_id(load_manifest_rows(args.manifest))
    rows: List[Dict[str, Any]] = []
    for path in sorted(args.cache_dir.glob("*.mp4")):
        video_id = path.stem
        duration = ffprobe_duration(path)
        if duration is None or duration < args.min_duration_sec:
            continue
        manifest = dict(by_id.get(video_id) or {})
        manifest.setdefault("video_id", video_id)
        manifest.setdefault("url", f"https://www.youtube.com/watch?v={video_id}")
        manifest["local_video_path"] = str(path)
        manifest["video_path"] = str(path)
        manifest["ffprobe_duration_sec"] = duration
        manifest["valid_video"] = True
        rows.append(manifest)
    if args.limit is not None:
        rows = rows[: args.limit]
    write_jsonl(args.output, rows)
    print(json.dumps({"written": len(rows), "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
