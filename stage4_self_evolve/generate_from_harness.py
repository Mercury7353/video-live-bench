import argparse
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from common import DEFAULT_OUTPUT_DIR, GeminiClient, append_jsonl, extract_gemini_text, extract_json, read_jsonl
from eval_local_video_mcq import get_or_upload, load_upload_cache, request_json
from prompts import HARNESS_QA_GENERATION_PROMPT


LABELS = {"A", "B", "C", "D"}


def load_keys(args: argparse.Namespace) -> List[str]:
    if args.api_key_file:
        text = args.api_key_file.read_text(encoding="utf-8").strip()
        if text:
            return [item.strip() for item in text.split(",") if item.strip()]
    for name in ("GEMINI_API_KEYS", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return [item.strip() for item in value.split(",") if item.strip()]
    raise ValueError("Set GEMINI_API_KEY/GOOGLE_API_KEY or pass --api-key-file")


def done_keys(path: Path, model: str) -> Set[str]:
    return {
        f"{row.get('video_id')}::{row.get('generator_model')}"
        for row in read_jsonl(path)
        if row.get("generator_model") == model and row.get("video_id")
    }


def compact_evidence(row: Dict[str, Any], max_chars: int) -> str:
    payload = {
        "video_metadata": row.get("video_metadata", {}),
        "evidence": row.get("evidence", {}),
        "dataflow_status": row.get("dataflow", {}).get("status"),
        "harness_status": row.get("harness_status"),
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...TRUNCATED..."


def load_seed_examples(path: Optional[Path]) -> List[Dict[str, Any]]:
    if not path:
        return []
    return read_jsonl(path)


def pick_seed_examples(
    seeds: List[Dict[str, Any]],
    row: Dict[str, Any],
    args: argparse.Namespace,
) -> List[Dict[str, Any]]:
    if not seeds or args.seed_examples_per_video <= 0:
        return []
    rng = random.Random(f"{args.seed}:{row.get('video_id')}")
    evidence = row.get("evidence") or {}
    opportunities = evidence.get("question_opportunities") or []
    skills = {
        str(item.get("skill", "")).lower()
        for item in opportunities
        if isinstance(item, dict)
    }
    preferred = [
        seed for seed in seeds
        if str(seed.get("task_type", "")).lower() in skills
        or str(seed.get("capability", "")).lower() in skills
    ]
    pool = preferred if len(preferred) >= args.seed_examples_per_video else seeds
    picked = rng.sample(pool, min(args.seed_examples_per_video, len(pool)))
    return [
        {
            "seed_id": seed.get("seed_id"),
            "source_benchmark": seed.get("source_benchmark"),
            "task_type": seed.get("task_type") or seed.get("capability"),
            "question": seed.get("question"),
            "options": seed.get("options"),
            "answer": seed.get("answer"),
            "domain": seed.get("domain"),
            "duration": seed.get("duration"),
            "seed_style_notes": seed.get("seed_style_notes"),
        }
        for seed in picked
    ]


def validate_item(item: Dict[str, Any]) -> Optional[str]:
    question = str(item.get("question", "")).strip()
    answer = str(item.get("reference_answer", "")).strip()
    options = item.get("options")
    correct = item.get("correct_option")
    if len(question.split()) < 6:
        return "question_too_short"
    if not answer:
        return "missing_reference_answer"
    if correct not in LABELS:
        return "bad_correct_option"
    if not isinstance(options, list) or len(options) != 4:
        return "bad_options"
    labels = {opt.get("label") for opt in options if isinstance(opt, dict)}
    if labels != LABELS:
        return "bad_option_labels"
    texts = [str(opt.get("text", "")).strip().lower() for opt in options if isinstance(opt, dict)]
    if len(texts) != 4 or len(set(texts)) != 4 or any(not text for text in texts):
        return "duplicate_or_empty_options"
    lower_q = question.lower()
    brittle_terms = ["exact timestamp", "frame number", "exact frame", "single pixel"]
    if any(term in lower_q for term in brittle_terms):
        return "brittle_question"
    return None


def normalize_item(item: Dict[str, Any], source: Dict[str, Any], index: int, args: argparse.Namespace) -> Dict[str, Any]:
    out = dict(item)
    out["candidate_id"] = f"{args.run_id}-{source.get('video_id')}-{index:02d}"
    out["video_id"] = source.get("video_id")
    out["url"] = source.get("url")
    out["local_video_path"] = source.get("local_video_path")
    out["generator_model"] = args.model
    out["generator_provider"] = args.provider
    out["generation_source"] = "benchmark_seed_plus_harness_evidence" if args.seed_examples else "harness_evidence"
    out["harness_status"] = source.get("harness_status")
    out["question_span"] = out.get("evidence_spans") or []
    out["answer_span"] = out.get("evidence_spans") or []
    out["mcq_ready"] = True
    out["nontrivial_mcq"] = True
    out["triviality_risk_reasons"] = []
    return out


def generate_text_only(client: GeminiClient, prompt: str, args: argparse.Namespace) -> Dict[str, Any]:
    response_text = client.generate(prompt, temperature=args.temperature)
    return extract_json(extract_gemini_text(response_text))


def generate_with_local_video(
    api_key: str,
    prompt: str,
    row: Dict[str, Any],
    upload_cache: Dict[str, Dict[str, Any]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    video_path_text = row.get("local_video_path") or row.get("video_path")
    if not video_path_text:
        raise ValueError("include-local-video requires local_video_path/video_path")
    upload = get_or_upload(
        api_key,
        Path(video_path_text),
        args.upload_cache,
        upload_cache,
        args.timeout_seconds,
        args.poll_seconds,
    )
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
                    {"text": prompt},
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "v1_harness_generated_mcq.jsonl")
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--provider", choices=["google", "vectorengine"], default="google")
    parser.add_argument("--model", default="gemini-3.5-flash")
    parser.add_argument("--run-id", default="v1")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--items-per-video", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-evidence-chars", type=int, default=24000)
    parser.add_argument("--seed-examples", type=Path, default=None)
    parser.add_argument("--seed-examples-per-video", type=int, default=5)
    parser.add_argument("--require-seed-examples", action="store_true")
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--include-local-video", action="store_true")
    parser.add_argument(
        "--allow-metadata-only",
        action="store_true",
        help="Allow metadata-only evidence rows for smoke tests when local video is also provided.",
    )
    parser.add_argument("--upload-cache", type=Path, default=DEFAULT_OUTPUT_DIR / "gemini_file_upload_cache.jsonl")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    allowed_statuses = {"ok"}
    if args.allow_metadata_only:
        allowed_statuses.add("metadata_only")
    rows = [row for row in read_jsonl(args.input) if row.get("harness_status") in allowed_statuses]
    if args.limit is not None:
        rows = rows[: args.limit]
    seed_examples = load_seed_examples(args.seed_examples)
    if args.require_seed_examples and not seed_examples:
        raise ValueError("--require-seed-examples was set but no seed examples were loaded")
    api_keys = load_keys(args)
    client = GeminiClient(
        args.provider,
        args.model,
        api_keys,
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    if args.include_local_video and args.provider != "google":
        raise ValueError("--include-local-video currently requires --provider google")
    upload_cache = load_upload_cache(args.upload_cache) if args.include_local_video else {}
    done = done_keys(args.output, args.model) if args.resume else set()
    if not args.resume:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("", encoding="utf-8")

    written = 0
    rejected: Dict[str, int] = {}
    for row in rows:
        key = f"{row.get('video_id')}::{args.model}"
        if key in done:
            continue
        selected_seed_examples = pick_seed_examples(seed_examples, row, args)
        prompt = HARNESS_QA_GENERATION_PROMPT.format(
            video_id=row.get("video_id"),
            url=row.get("url"),
            seed_examples_json=json.dumps(
                selected_seed_examples,
                ensure_ascii=False,
                indent=2,
            ),
            evidence_json=compact_evidence(row, args.max_evidence_chars),
        )
        prompt += f"\nGenerate up to {args.items_per_video} items for this video."
        try:
            if args.include_local_video:
                parsed = generate_with_local_video(api_keys[0], prompt, row, upload_cache, args)
            else:
                parsed = generate_text_only(client, prompt, args)
            items = parsed.get("items", [])
        except Exception as exc:
            rejected["generation_error"] = rejected.get("generation_error", 0) + 1
            print(json.dumps({"video_id": row.get("video_id"), "error": str(exc)}, ensure_ascii=False), flush=True)
            continue
        for index, item in enumerate(items[: args.items_per_video], start=1):
            reason = validate_item(item)
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue
            normalized = normalize_item(item, row, index, args)
            normalized["benchmark_seed_ids"] = [
                seed.get("seed_id")
                for seed in selected_seed_examples
                if seed.get("seed_id")
            ]
            normalized["benchmark_seed_sources"] = sorted(
                {
                    str(seed.get("source_benchmark"))
                    for seed in selected_seed_examples
                    if seed.get("source_benchmark")
                }
            )
            append_jsonl(args.output, normalized)
            written += 1
        print(json.dumps({"video_id": row.get("video_id"), "items": min(len(items), args.items_per_video)}, ensure_ascii=False), flush=True)
    print(json.dumps({"input_videos": len(rows), "written": written, "rejected": rejected}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
