import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from common import (
    DEFAULT_OUTPUT_DIR,
    GeminiClient,
    append_jsonl,
    extract_gemini_text,
    extract_json,
    extract_legacy_vectorengine_keys,
    get_env_keys,
    read_jsonl,
)
from prompts import MCQ_EVAL_PROMPT, MCQ_OPTIONS_ONLY_PROMPT


def existing_keys(path: Path, model: str, mode: str) -> Set[str]:
    return {
        f"{row.get('candidate_id')}::{row.get('eval_model')}::{row.get('eval_mode')}"
        for row in read_jsonl(path)
        if row.get("eval_model") == model and row.get("eval_mode") == mode
    }


def format_options(row: Dict[str, Any]) -> str:
    lines = []
    for option in row.get("options") or []:
        lines.append(f"{option.get('label')}. {option.get('text')}")
    return "\n".join(lines)


def parse_answer_label(value: Any) -> str:
    text = str(value or "").strip().upper()
    match = re.search(r"\b([ABCD])\b", text)
    return match.group(1) if match else text[:1]


class OpenAIChatClient:
    def __init__(self, model: str, api_key: str, base_url: str, timeout_seconds: int, sleep_seconds: float) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.sleep_seconds = sleep_seconds

    def generate(self, prompt: str, temperature: float) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI request failed: {exc.code} {error_text[:500]}") from exc
        finally:
            time.sleep(self.sleep_seconds)
        data = json.loads(text)
        return data["choices"][0]["message"]["content"]


def make_gemini(args: argparse.Namespace) -> GeminiClient:
    file_keys: List[str] = []
    if args.api_key_file:
        text = args.api_key_file.read_text(encoding="utf-8").strip()
        if text:
            file_keys = [key.strip() for key in text.split(",") if key.strip()]
    if args.provider == "vectorengine":
        keys = get_env_keys("VECTORENGINE_API_KEY", "VECTORENGINE_API_KEYS")
        if args.use_legacy_vectorengine_keys:
            keys.extend(extract_legacy_vectorengine_keys())
    else:
        keys = get_env_keys("GEMINI_API_KEY", "GOOGLE_API_KEY")
    keys = file_keys + keys
    return GeminiClient(
        provider=args.provider,
        model=args.model,
        api_keys=keys,
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
    )


def make_openai(args: argparse.Namespace) -> OpenAIChatClient:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return OpenAIChatClient(args.model, api_key, base_url, args.timeout_seconds, args.sleep_seconds)


def eval_gemini(row: Dict[str, Any], client: GeminiClient, args: argparse.Namespace) -> Dict[str, Any]:
    options = format_options(row)
    if args.mode == "gemini_video":
        prompt = MCQ_EVAL_PROMPT.format(question=row.get("question", ""), options=options)
        response_text = client.generate(
            prompt,
            video_url=row.get("url"),
            temperature=args.temperature,
            response_mime_type="application/json",
        )
    else:
        prompt = MCQ_OPTIONS_ONLY_PROMPT.format(question=row.get("question", ""), options=options)
        response_text = client.generate(prompt, temperature=args.temperature, response_mime_type="application/json")
    model_text = extract_gemini_text(response_text)
    return extract_json(model_text)


def eval_openai(row: Dict[str, Any], client: OpenAIChatClient, args: argparse.Namespace) -> Dict[str, Any]:
    prompt = MCQ_OPTIONS_ONLY_PROMPT.format(question=row.get("question", ""), options=format_options(row))
    text = client.generate(prompt, args.temperature)
    return extract_json(text)


def result_row(row: Dict[str, Any], parsed: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    pred = parse_answer_label(parsed.get("answer"))
    correct = str(row.get("correct_option", "")).strip().upper()
    return {
        "candidate_id": row.get("candidate_id"),
        "video_id": row.get("video_id"),
        "url": row.get("url"),
        "task_type": row.get("task_type"),
        "question": row.get("question"),
        "correct_option": correct,
        "eval_model": args.model,
        "eval_provider": args.provider,
        "eval_mode": args.mode,
        "pred_option": pred,
        "is_correct": pred == correct,
        "confidence": parsed.get("confidence"),
        "reasoning_brief": parsed.get("reasoning_brief", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_reviews.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_eval_results.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-reviewed-keep", action="store_true")
    parser.add_argument("--mode", choices=["gemini_video", "gemini_options", "openai_options"], required=True)
    parser.add_argument("--provider", choices=["vectorengine", "google", "openai"], default="vectorengine")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--use-legacy-vectorengine-keys", action="store_true")
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    if args.only_reviewed_keep:
        rows = [row for row in rows if row.get("mcq_review_keep")]
    if args.limit is not None:
        rows = rows[: args.limit]

    done = existing_keys(args.output, args.model, args.mode)
    pending = [row for row in rows if f"{row.get('candidate_id')}::{args.model}::{args.mode}" not in done]
    client: Any
    if args.mode == "openai_options":
        client = make_openai(args)
    else:
        client = make_gemini(args)

    success = 0
    failures = []
    for row in pending:
        try:
            parsed = eval_openai(row, client, args) if args.mode == "openai_options" else eval_gemini(row, client, args)
            out = result_row(row, parsed, args)
            append_jsonl(args.output, out)
            success += 1
            print(json.dumps({"ok": row.get("candidate_id"), "pred": out["pred_option"], "correct": out["correct_option"]}, ensure_ascii=False))
        except Exception as exc:
            failure = {"candidate_id": row.get("candidate_id"), "error": str(exc)}
            failures.append(failure)
            print(json.dumps(failure, ensure_ascii=False))

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
        )
    )


if __name__ == "__main__":
    main()
