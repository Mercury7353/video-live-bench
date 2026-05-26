import argparse
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from common import DEFAULT_OUTPUT_DIR, append_jsonl, extract_gemini_text, extract_json, read_jsonl
from eval_mcq import format_options, parse_answer_label, result_row
from prompts import MCQ_EVAL_PROMPT


def existing_keys(path: Path, model: str, mode: str) -> Set[str]:
    return {
        f"{row.get('candidate_id')}::{row.get('eval_model')}::{row.get('eval_mode')}"
        for row in read_jsonl(path)
        if row.get("eval_model") == model and row.get("eval_mode") == mode
    }


def load_api_key(args: argparse.Namespace) -> str:
    if args.api_key_file:
        key = args.api_key_file.read_text(encoding="utf-8").strip()
        if key:
            return key
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        key = os.environ.get(name, "").strip()
        if key:
            return key
    raise ValueError("Set GEMINI_API_KEY/GOOGLE_API_KEY or pass --api-key-file")


def parse_upload_url(headers: Any) -> str:
    for key in ("x-goog-upload-url", "X-Goog-Upload-URL"):
        value = headers.get(key)
        if value:
            return value
    raise RuntimeError("Gemini upload start response did not include x-goog-upload-url")


def request_json(
    url: str,
    *,
    api_key: str,
    payload: Optional[Dict[str, Any]] = None,
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_seconds: int = 300,
    method: str = "POST",
) -> Dict[str, Any]:
    request_headers = {"x-goog-api-key": api_key}
    if headers:
        request_headers.update(headers)
    body = data
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text.strip() else {}
    except urllib.error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini request failed: {exc.code} {error_text[:800]}") from exc


def start_resumable_upload(api_key: str, path: Path, mime_type: str, timeout_seconds: int) -> str:
    url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
    payload = {"file": {"display_name": path.name}}
    headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(path.stat().st_size),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json",
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return parse_upload_url(response.headers)
    except urllib.error.HTTPError as exc:
        error_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini upload start failed: {exc.code} {error_text[:800]}") from exc


def upload_file(api_key: str, path: Path, timeout_seconds: int) -> Dict[str, Any]:
    mime_type = mimetypes.guess_type(path.name)[0] or "video/mp4"
    upload_url = start_resumable_upload(api_key, path, mime_type, timeout_seconds)
    data = path.read_bytes()
    result = request_json(
        upload_url,
        api_key=api_key,
        data=data,
        headers={
            "Content-Length": str(len(data)),
            "Content-Type": mime_type,
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        timeout_seconds=timeout_seconds,
    )
    file_obj = result.get("file") or result
    file_obj.setdefault("mimeType", mime_type)
    return file_obj


def get_file(api_key: str, file_name: str, timeout_seconds: int) -> Dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}"
    return request_json(url, api_key=api_key, method="GET", timeout_seconds=timeout_seconds)


def wait_active(api_key: str, file_obj: Dict[str, Any], timeout_seconds: int, poll_seconds: float) -> Dict[str, Any]:
    deadline = time.time() + timeout_seconds
    name = file_obj.get("name")
    if not name:
        return file_obj
    while time.time() < deadline:
        state = str(file_obj.get("state") or "").upper()
        if state in {"ACTIVE", ""}:
            return file_obj
        if state == "FAILED":
            raise RuntimeError(f"Uploaded file processing failed: {file_obj}")
        time.sleep(poll_seconds)
        file_obj = get_file(api_key, name, timeout_seconds)
    raise TimeoutError(f"Timed out waiting for uploaded file to become ACTIVE: {name}")


def cache_key(path: Path) -> str:
    stat = path.stat()
    return f"{path.resolve()}::{stat.st_size}::{int(stat.st_mtime)}"


def load_upload_cache(path: Path) -> Dict[str, Dict[str, Any]]:
    rows = read_jsonl(path)
    return {str(row.get("cache_key")): row for row in rows if row.get("cache_key") and row.get("file_uri")}


def get_or_upload(
    api_key: str,
    path: Path,
    upload_cache_path: Path,
    upload_cache: Dict[str, Dict[str, Any]],
    timeout_seconds: int,
    poll_seconds: float,
) -> Dict[str, Any]:
    key = cache_key(path)
    cached = upload_cache.get(key)
    if cached:
        return cached
    file_obj = upload_file(api_key, path, timeout_seconds)
    file_obj = wait_active(api_key, file_obj, timeout_seconds, poll_seconds)
    row = {
        "cache_key": key,
        "path": str(path),
        "file_name": file_obj.get("name"),
        "file_uri": file_obj.get("uri"),
        "mime_type": file_obj.get("mimeType") or mimetypes.guess_type(path.name)[0] or "video/mp4",
    }
    if not row["file_uri"]:
        raise RuntimeError(f"Upload did not return file URI: {file_obj}")
    append_jsonl(upload_cache_path, row)
    upload_cache[key] = row
    return row


class GeminiLocalVideoClient:
    def __init__(self, api_key: str, model: str, timeout_seconds: int, sleep_seconds: float) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.sleep_seconds = sleep_seconds

    def generate(self, prompt: str, file_uri: str, mime_type: str, temperature: float) -> Dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                        {"text": prompt},
                    ],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "response_mime_type": "application/json",
            },
        }
        response_text = json.dumps(
            request_json(url, api_key=self.api_key, payload=payload, timeout_seconds=self.timeout_seconds)
        )
        time.sleep(self.sleep_seconds)
        return extract_json(extract_gemini_text(response_text))


def result_with_local(row: Dict[str, Any], parsed: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    out = result_row(row, parsed, args)
    out["local_video_path"] = row.get("local_video_path") or row.get("video_path")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_local_video_eval_results.jsonl")
    parser.add_argument("--upload-cache", type=Path, default=DEFAULT_OUTPUT_DIR / "gemini_file_upload_cache.jsonl")
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--model", required=True)
    parser.add_argument("--mode", default="gemini_local_video")
    parser.add_argument("--provider", default="google")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    args = parser.parse_args()

    api_key = load_api_key(args)
    rows = [row for row in read_jsonl(args.input) if row.get("local_video_path") or row.get("video_path")]
    if args.limit is not None:
        rows = rows[: args.limit]
    done = existing_keys(args.output, args.model, args.mode)
    pending = [row for row in rows if f"{row.get('candidate_id')}::{args.model}::{args.mode}" not in done]
    client = GeminiLocalVideoClient(api_key, args.model, args.timeout_seconds, args.sleep_seconds)
    upload_cache = load_upload_cache(args.upload_cache)

    success = 0
    failures: List[Dict[str, Any]] = []
    for row in pending:
        try:
            video_path = Path(row.get("local_video_path") or row.get("video_path"))
            print(json.dumps({"start": row.get("candidate_id"), "video": str(video_path)}, ensure_ascii=False), flush=True)
            upload = get_or_upload(
                api_key,
                video_path,
                args.upload_cache,
                upload_cache,
                args.timeout_seconds,
                args.poll_seconds,
            )
            prompt = MCQ_EVAL_PROMPT.format(question=row.get("question", ""), options=format_options(row))
            parsed = client.generate(prompt, upload["file_uri"], upload["mime_type"], args.temperature)
            out = result_with_local(row, parsed, args)
            out["gemini_file_name"] = upload.get("file_name")
            append_jsonl(args.output, out)
            success += 1
            print(json.dumps({"ok": row.get("candidate_id"), "pred": out["pred_option"], "correct": out["correct_option"]}, ensure_ascii=False), flush=True)
        except Exception as exc:
            failure = {"candidate_id": row.get("candidate_id"), "video_id": row.get("video_id"), "error": str(exc)}
            failures.append(failure)
            print(json.dumps(failure, ensure_ascii=False), flush=True)

    all_rows = [
        row for row in read_jsonl(args.output)
        if row.get("eval_model") == args.model and row.get("eval_mode") == args.mode
    ]
    total = len(all_rows)
    correct = sum(1 for row in all_rows if row.get("is_correct"))
    print(
        json.dumps(
            {
                "attempted": len(pending),
                "success": success,
                "failures": failures,
                "total_results_for_model_mode": total,
                "accuracy": round(correct / total, 4) if total else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
