import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import DEFAULT_OUTPUT_DIR, append_jsonl, ensure_parent, read_jsonl, video_id_from_url


def run_command(cmd: List[str], *, env: Optional[Dict[str, str]] = None, timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=timeout,
    )


def ffprobe_video(path: Path) -> Dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"status": "missing_ffprobe"}
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = run_command(cmd, timeout=120)
    if proc.returncode != 0:
        return {"status": "failed", "stderr": proc.stderr[-1000:]}
    data = json.loads(proc.stdout or "{}")
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    duration = data.get("format", {}).get("duration") or video_stream.get("duration")
    fps_text = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0/1"
    try:
        num, den = fps_text.split("/", 1)
        fps = float(num) / max(1.0, float(den))
    except Exception:
        fps = 0.0
    return {
        "status": "ok",
        "duration_sec": float(duration) if duration else 0.0,
        "fps": fps,
        "width": video_stream.get("width", 0),
        "height": video_stream.get("height", 0),
        "has_audio": bool(audio_stream),
        "format_name": data.get("format", {}).get("format_name", ""),
        "size_bytes": int(data.get("format", {}).get("size", 0) or 0),
    }


def load_dataflow_summary(path: Path, max_segments: int) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    global_summary = data.get("global_summary", {})
    final_output = data.get("final_output", {})
    segments = []
    for segment in data.get("segments", [])[:max_segments]:
        span = segment.get("time_span", {})
        final_caption = segment.get("final_segment_caption", {})
        claims = segment.get("claims", [])
        core_objects = segment.get("core_object_claims", [])
        segments.append(
            {
                "segment_id": segment.get("segment_id"),
                "time_span": span,
                "caption": final_caption.get("timeline_caption", ""),
                "claim_count": len(claims),
                "core_object_count": len(core_objects),
                "sample_claims": [claim.get("text", "") for claim in claims[:5]],
                "sample_core_objects": [
                    {
                        "label": item.get("object_label", ""),
                        "description": item.get("object_description", ""),
                        "action": item.get("past_action", ""),
                        "time_spans": item.get("time_spans", []),
                    }
                    for item in core_objects[:5]
                ],
            }
        )
    return {
        "global_summary": {
            "one_sentence": global_summary.get("one_sentence", ""),
            "short_paragraph": global_summary.get("short_paragraph", ""),
            "style_tags": global_summary.get("style_tags", []),
            "primary_scene_type": global_summary.get("primary_scene_type"),
            "primary_characters": global_summary.get("primary_characters", []),
        },
        "timeline_caption": final_output.get("timeline_caption", []),
        "dense_caption": final_output.get("dense_caption", ""),
        "segments": segments,
        "trace": data.get("trace", {}),
    }


def resolve_video_path(row: Dict[str, Any]) -> Optional[Path]:
    for key in ("local_video_path", "video_path"):
        value = row.get(key)
        if value and Path(value).exists():
            return Path(value)
    return None


def run_dataflow(
    video_path: Path,
    output_path: Path,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    root = args.video_agent_dataflow_root
    if root is None:
        return {"status": "skipped", "reason": "video_agent_dataflow_root_not_set"}
    config = args.dataflow_config
    if config is None:
        config = root / "configs" / "example.yaml"
    if not config.exists():
        return {"status": "skipped", "reason": f"missing_config:{config}"}
    ensure_parent(output_path)
    if output_path.exists() and not args.force_dataflow:
        return {"status": "exists", "output_path": str(output_path)}

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{root}:{env.get('PYTHONPATH', '')}"
    cmd = [
        "python3",
        "-m",
        "src.video_captioner.cli",
        "--config",
        str(config),
        "--video",
        str(video_path),
        "--output",
        str(output_path),
        "--density-level",
        args.density_level,
        "--output-mode",
        "both",
        "--budget-level",
        args.budget_level,
    ]
    if args.disable_audio:
        cmd.append("--disable-audio")
    if args.non_strict_factuality:
        cmd.append("--non-strict-factuality")
    proc = run_command(cmd, env=env, timeout=args.dataflow_timeout_seconds)
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "output_path": str(output_path),
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def build_one(row: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    video_path = resolve_video_path(row)
    video_id = row.get("video_id") or video_id_from_url(row.get("url", ""))
    out: Dict[str, Any] = {
        "candidate_id": row.get("candidate_id"),
        "video_id": video_id,
        "url": row.get("url"),
        "local_video_path": str(video_path) if video_path else None,
        "source_row": {
            key: row.get(key)
            for key in ("title", "duration", "channel", "seed_benchmark", "task_type")
            if key in row
        },
        "harness_status": "pending",
        "video_metadata": {},
        "dataflow": {},
        "evidence": {},
        "errors": [],
    }
    if video_path is None:
        out["harness_status"] = "missing_local_video"
        out["errors"].append("No local video path was found.")
        return out

    out["video_metadata"] = ffprobe_video(video_path)
    dataflow_output = args.media_dir / str(video_id or video_path.stem) / "dataflow_caption.json"
    if args.run_dataflow:
        out["dataflow"] = run_dataflow(video_path, dataflow_output, args)
    elif dataflow_output.exists():
        out["dataflow"] = {"status": "exists", "output_path": str(dataflow_output)}
    else:
        out["dataflow"] = {"status": "skipped", "reason": "run_dataflow_false"}

    output_value = out["dataflow"].get("output_path")
    output_path = Path(output_value) if output_value else None
    if output_path and output_path.is_file():
        try:
            out["evidence"] = load_dataflow_summary(output_path, args.max_segments)
            out["harness_status"] = "ok"
        except Exception as exc:
            out["harness_status"] = "failed_parse_dataflow"
            out["errors"].append(str(exc))
    else:
        out["evidence"] = {
            "global_summary": {},
            "segments": [],
            "note": "Only ffprobe metadata is available. Run with --run-dataflow for OCR/YOLO/ASR/caption evidence.",
        }
        out["harness_status"] = "metadata_only"
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "v1_harness_evidence.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--media-dir", type=Path, default=DEFAULT_OUTPUT_DIR / "harness_media")
    parser.add_argument("--run-dataflow", action="store_true")
    parser.add_argument("--video-agent-dataflow-root", type=Path, default=None)
    parser.add_argument("--dataflow-config", type=Path, default=None)
    parser.add_argument("--force-dataflow", action="store_true")
    parser.add_argument("--density-level", default="5s")
    parser.add_argument("--budget-level", choices=["low", "medium", "high"], default="high")
    parser.add_argument("--disable-audio", action="store_true")
    parser.add_argument("--non-strict-factuality", action="store_true")
    parser.add_argument("--dataflow-timeout-seconds", type=int, default=3600)
    parser.add_argument("--max-segments", type=int, default=24)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    rows = [row for row in read_jsonl(args.input) if row.get("local_video_path") or row.get("video_path")]
    if args.limit is not None:
        rows = rows[: args.limit]
    done = set()
    if args.resume and args.output.exists():
        done = {row.get("video_id") for row in read_jsonl(args.output) if row.get("video_id")}

    written = 0
    status_counts: Dict[str, int] = {}
    if not args.resume:
        ensure_parent(args.output)
        args.output.write_text("", encoding="utf-8")
    for row in rows:
        video_id = row.get("video_id") or video_id_from_url(row.get("url", ""))
        if video_id in done:
            continue
        evidence = build_one(row, args)
        append_jsonl(args.output, evidence)
        status = evidence.get("harness_status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        written += 1
        print(json.dumps({"video_id": video_id, "status": status}, ensure_ascii=False), flush=True)
    print(json.dumps({"input_rows": len(rows), "written": written, "status_counts": status_counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
