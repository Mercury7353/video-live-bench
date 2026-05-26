import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from common import DEFAULT_OUTPUT_DIR, read_jsonl, write_jsonl
from tool_adapters.video_agent_dataflow import (
    FFmpegVideoExtractor,
    LocalVideoResolver,
    ToolAPIError,
    VideoAgentDataFlowClient,
)


TOOL_TASKS = {"OCR", "Counting", "Spatial", "Perception"}


def normalize_spans(candidate: Dict[str, Any]) -> List[List[float]]:
    spans = candidate.get("answer_span") or candidate.get("question_span") or []
    clean = []
    for span in spans:
        if isinstance(span, list) and len(span) >= 2:
            try:
                start = max(0.0, float(span[0]))
                end = max(start, float(span[1]))
                clean.append([start, end])
            except Exception:
                continue
    return clean


def build_one(
    candidate: Dict[str, Any],
    resolver: LocalVideoResolver,
    extractor: FFmpegVideoExtractor,
    client: VideoAgentDataFlowClient,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "candidate_id": candidate.get("candidate_id"),
        "video_id": candidate.get("video_id"),
        "url": candidate.get("url"),
        "task_type": candidate.get("task_type"),
        "question": candidate.get("question"),
        "reference_answer": candidate.get("reference_answer"),
        "answer_span": candidate.get("answer_span", []),
        "question_span": candidate.get("question_span", []),
        "harness_reasoning": candidate.get("harness_reasoning", ""),
        "evidence_status": "pending",
        "local_video_path": None,
        "frames": [],
        "ocr_items": [],
        "detections": [],
        "tracked_objects": [],
        "errors": [],
    }
    if row["task_type"] not in TOOL_TASKS and not args.all_tasks:
        row["evidence_status"] = "skipped_unsupported_task"
        return row

    video_path = resolver.resolve(candidate)
    if video_path is None:
        row["evidence_status"] = "skipped_missing_local_video"
        row["errors"].append(
            "No local video found. Set candidate.video_path or VIDLIVE_VIDEO_CACHE_DIR/VIDEO_CACHE_DIR."
        )
        return row
    row["local_video_path"] = str(video_path)

    spans = normalize_spans(candidate)
    if not spans:
        row["evidence_status"] = "skipped_missing_span"
        return row
    if not extractor.available():
        row["evidence_status"] = "skipped_missing_ffmpeg"
        row["errors"].append("ffmpeg is not available")
        return row

    try:
        frames = extractor.extract_frames(
            video_path,
            spans,
            str(candidate.get("candidate_id")),
            frames_per_span=args.frames_per_span,
        )
        row["frames"] = frames
    except Exception as exc:
        row["evidence_status"] = "failed_frame_extraction"
        row["errors"].append(str(exc))
        return row

    if not client.configured():
        row["evidence_status"] = "frames_only_no_tool_api"
        row["errors"].append("VIDEO_AGENT_TOOL_API_URL is not configured")
        return row

    try:
        if row["task_type"] in {"OCR", "Perception"} or args.all_tools:
            row["ocr_items"] = client.ocr_extract(frames)
        if row["task_type"] in {"Counting", "Spatial", "Perception"} or args.all_tools:
            row["detections"] = client.yolo_detect_frames(frames)
            clip = extractor.export_clip(video_path, spans[0], str(candidate.get("candidate_id")))
            if clip:
                row["tracked_objects"] = client.yolo_track(clip)
        row["evidence_status"] = "ok"
    except ToolAPIError as exc:
        row["evidence_status"] = "failed_tool_api"
        row["errors"].append(str(exc))
    except Exception as exc:
        row["evidence_status"] = "failed_tool_runtime"
        row["errors"].append(str(exc))
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "candidates.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "evidence_packs.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--video-cache-dir", action="append", default=[])
    parser.add_argument("--tool-api-url", default=None)
    parser.add_argument("--frames-per-span", type=int, default=3)
    parser.add_argument("--all-tasks", action="store_true")
    parser.add_argument("--all-tools", action="store_true")
    args = parser.parse_args()

    candidates = read_jsonl(args.input)
    if args.limit is not None:
        candidates = candidates[: args.limit]
    resolver = LocalVideoResolver(args.video_cache_dir)
    extractor = FFmpegVideoExtractor()
    client = VideoAgentDataFlowClient(args.tool_api_url)
    rows = [build_one(candidate, resolver, extractor, client, args) for candidate in candidates]
    count = write_jsonl(args.output, rows)
    status_counts: Dict[str, int] = {}
    for row in rows:
        status = row.get("evidence_status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    print(json.dumps({"written": count, "status_counts": status_counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

