import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Set

from common import DEFAULT_OUTPUT_DIR, append_jsonl, extract_gemini_text, extract_json, read_jsonl, video_id_from_url
from eval_local_video_mcq import get_or_upload, load_upload_cache, request_json
from prompts import GEMINI_VIDEO_EVIDENCE_PROMPT


def load_api_key(args: argparse.Namespace) -> str:
    if args.api_key_file:
        key = args.api_key_file.read_text(encoding="utf-8").strip()
        if key:
            return key.split(",", 1)[0].strip()
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        key = os.environ.get(name, "").strip()
        if key:
            return key.split(",", 1)[0].strip()
    raise ValueError("Set GEMINI_API_KEY/GOOGLE_API_KEY or pass --api-key-file")


def done_video_ids(path: Path, model: str) -> Set[str]:
    return {
        str(row.get("video_id"))
        for row in read_jsonl(path)
        if row.get("evidence_model") == model and row.get("video_id")
    }


def resolve_video_path(row: Dict[str, Any]) -> Path:
    value = row.get("local_video_path") or row.get("video_path")
    if not value:
        raise ValueError("missing local_video_path/video_path")
    path = Path(value)
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path


def generate_evidence(api_key: str, upload: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{args.model}:generateContent"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "file_data": {
                            "mime_type": upload["mime_type"],
                            "file_uri": upload["file_uri"],
                        }
                    },
                    {"text": GEMINI_VIDEO_EVIDENCE_PROMPT},
                ],
            }
        ],
        "generationConfig": {
            "temperature": args.temperature,
            "response_mime_type": "application/json",
        },
    }
    response = request_json(url, api_key=api_key, payload=payload, timeout_seconds=args.timeout_seconds)
    return extract_json(extract_gemini_text(json.dumps(response)))


def normalize(row: Dict[str, Any], evidence: Dict[str, Any], upload: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    video_id = row.get("video_id") or video_id_from_url(str(row.get("url", "")))
    return {
        "candidate_id": row.get("candidate_id"),
        "video_id": video_id,
        "url": row.get("url") or (f"https://www.youtube.com/watch?v={video_id}" if video_id else None),
        "local_video_path": row.get("local_video_path") or row.get("video_path"),
        "harness_status": "ok",
        "harness_type": "gemini_video_evidence",
        "evidence_model": args.model,
        "gemini_file_name": upload.get("file_name"),
        "video_metadata": row.get("video_metadata", {}),
        "evidence": evidence,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "gemini_video_evidence.jsonl")
    parser.add_argument("--upload-cache", type=Path, default=DEFAULT_OUTPUT_DIR / "gemini_file_upload_cache.jsonl")
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--model", default="gemini-3.5-flash")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    rows = [row for row in read_jsonl(args.input) if row.get("local_video_path") or row.get("video_path")]
    if args.limit is not None:
        rows = rows[: args.limit]
    api_key = load_api_key(args)
    upload_cache = load_upload_cache(args.upload_cache)
    done = done_video_ids(args.output, args.model) if args.resume else set()
    if not args.resume:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("", encoding="utf-8")

    success = 0
    failures: List[Dict[str, Any]] = []
    for row in rows:
        video_id = row.get("video_id") or video_id_from_url(str(row.get("url", "")))
        if video_id in done:
            continue
        try:
            video_path = resolve_video_path(row)
            upload = get_or_upload(
                api_key,
                video_path,
                args.upload_cache,
                upload_cache,
                args.timeout_seconds,
                args.poll_seconds,
            )
            evidence = generate_evidence(api_key, upload, args)
            append_jsonl(args.output, normalize(row, evidence, upload, args))
            success += 1
            print(json.dumps({"ok": video_id}, ensure_ascii=False), flush=True)
        except Exception as exc:
            failure = {"video_id": video_id, "error": str(exc)}
            failures.append(failure)
            print(json.dumps(failure, ensure_ascii=False), flush=True)
    print(json.dumps({"input_rows": len(rows), "success": success, "failures": failures}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
