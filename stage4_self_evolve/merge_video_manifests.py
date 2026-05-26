import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from common import read_jsonl, video_id_from_url, write_jsonl


SUCCESS_STATUSES = {"downloaded", "exists"}


def row_video_id(row: Dict[str, Any]) -> str:
    return str(row.get("video_id") or video_id_from_url(str(row.get("url", ""))))


def load_manifest_rows(paths: List[Path]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        rows.extend(read_jsonl(path))
    return rows


def best_by_video_id(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        video_id = row_video_id(row)
        if not video_id:
            continue
        current = best.get(video_id)
        if current is None:
            best[video_id] = row
            continue
        status = row.get("status")
        current_status = current.get("status")
        if status in SUCCESS_STATUSES and current_status not in SUCCESS_STATUSES:
            best[video_id] = row
    return best


def attach(candidates: List[Dict[str, Any]], manifest_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in candidates:
        merged = dict(row)
        manifest = manifest_by_id.get(row_video_id(row))
        if manifest and manifest.get("local_video_path"):
            merged["local_video_path"] = manifest["local_video_path"]
            merged["video_path"] = manifest["local_video_path"]
            merged["download_status"] = manifest.get("status")
        elif manifest:
            merged["download_status"] = manifest.get("status")
            merged["download_error"] = manifest.get("error")
        else:
            merged["download_status"] = "not_attempted"
        out.append(merged)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--merged-manifest-output", type=Path, required=True)
    parser.add_argument("--annotated-output", type=Path, required=True)
    args = parser.parse_args()

    manifest_rows = load_manifest_rows(args.manifest)
    by_id = best_by_video_id(manifest_rows)
    merged_manifest = list(by_id.values())
    candidates = read_jsonl(args.candidates)
    annotated = attach(candidates, by_id)
    write_jsonl(args.merged_manifest_output, merged_manifest)
    write_jsonl(args.annotated_output, annotated)

    status_counts: Dict[str, int] = {}
    for row in annotated:
        status = str(row.get("download_status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    print(
        json.dumps(
            {
                "candidate_rows": len(candidates),
                "manifest_rows": len(manifest_rows),
                "unique_manifest_videos": len(merged_manifest),
                "annotated_rows": len(annotated),
                "usable_local_videos": sum(1 for row in annotated if row.get("local_video_path")),
                "status_counts": status_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
