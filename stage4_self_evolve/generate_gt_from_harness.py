import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import DEFAULT_OUTPUT_DIR, GeminiClient, append_jsonl, extract_gemini_text, extract_json, read_jsonl
from eval_local_video_mcq import load_upload_cache
from generate_from_harness import (
    compact_evidence,
    generate_text_only,
    generate_with_local_video,
    load_keys,
    load_seed_examples,
    pick_seed_examples,
)
from prompts import HARNESS_GT_GENERATION_PROMPT


def validate_gt_item(item: Dict[str, Any]) -> Optional[str]:
    question = str(item.get("question", "")).strip()
    answer = str(item.get("reference_answer", "")).strip()
    if len(question.split()) < 6:
        return "question_too_short"
    if not answer:
        return "missing_reference_answer"
    if item.get("options") or item.get("correct_option"):
        return "gt_stage_contains_options"
    if not item.get("evidence_spans"):
        return "missing_evidence_spans"
    lower_q = question.lower()
    brittle_terms = ["exact timestamp", "frame number", "exact frame", "single pixel", "around the"]
    if any(term in lower_q for term in brittle_terms):
        return "brittle_question"
    if re.search(r"\b\d{1,2}:\d{2}\b", question):
        return "timestamp_leak_in_question"
    return None


def validate_hard_item(item: Dict[str, Any], args: argparse.Namespace) -> Optional[str]:
    question = str(item.get("question", "")).lower()
    task_type = str(item.get("task_type", "")).lower()
    single_cue_terms = ["what text", "what word", "what brand", "what color", "what object"]
    if args.reject_single_cue_questions and (
        any(term in question for term in single_cue_terms)
        or task_type in {"ocr", "perception"}
    ):
        return "single_cue_question"
    return None


def normalize_gt_item(
    item: Dict[str, Any],
    source: Dict[str, Any],
    index: int,
    selected_seed_examples: List[Dict[str, Any]],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    out = dict(item)
    out["candidate_id"] = f"{args.run_id}-{source.get('video_id')}-{index:02d}"
    out["video_id"] = source.get("video_id")
    out["url"] = source.get("url")
    out["local_video_path"] = source.get("local_video_path")
    out["generator_model"] = args.model
    out["generator_provider"] = args.provider
    out["generation_stage"] = "gt"
    out["generation_source"] = "benchmark_seed_plus_video_plus_harness_evidence" if args.seed_examples else "video_plus_harness_evidence"
    out["harness_status"] = source.get("harness_status")
    out["question_span"] = out.get("evidence_spans") or []
    out["answer_span"] = out.get("evidence_spans") or []
    out["benchmark_seed_ids"] = [
        seed.get("seed_id")
        for seed in selected_seed_examples
        if seed.get("seed_id")
    ]
    out["benchmark_seed_sources"] = sorted(
        {
            str(seed.get("source_benchmark"))
            for seed in selected_seed_examples
            if seed.get("source_benchmark")
        }
    )
    out["benchmark_seed_capabilities"] = sorted(
        {
            str(seed.get("capability"))
            for seed in selected_seed_examples
            if seed.get("capability")
        }
    )
    out["benchmark_seed_examples"] = selected_seed_examples
    out["benchmark_seed_stratify_fields"] = args.seed_stratify_fields.split(",")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "gt_candidates.jsonl")
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--provider", choices=["google", "vectorengine"], default="google")
    parser.add_argument("--model", default="gemini-3.5-flash")
    parser.add_argument("--run-id", default="v2-gt")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--items-per-video", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-evidence-chars", type=int, default=24000)
    parser.add_argument("--seed-examples", type=Path, default=None)
    parser.add_argument("--seed-examples-per-video", type=int, default=8)
    parser.add_argument("--require-seed-examples", action="store_true")
    parser.add_argument("--seed-stratify-fields", default="source_benchmark,capability")
    parser.add_argument("--seed", type=int, default=31)
    parser.add_argument("--reject-single-cue-questions", action="store_true")
    parser.add_argument("--include-local-video", action="store_true")
    parser.add_argument("--upload-cache", type=Path, default=DEFAULT_OUTPUT_DIR / "gemini_file_upload_cache.jsonl")
    args = parser.parse_args()

    rows = [row for row in read_jsonl(args.input) if row.get("harness_status") == "ok"]
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("", encoding="utf-8")

    written = 0
    rejected: Dict[str, int] = {}
    for row in rows:
        selected_seed_examples = pick_seed_examples(seed_examples, row, args)
        prompt = HARNESS_GT_GENERATION_PROMPT.format(
            video_id=row.get("video_id"),
            url=row.get("url"),
            seed_examples_json=json.dumps(selected_seed_examples, ensure_ascii=False, indent=2),
            evidence_json=compact_evidence(row, args.max_evidence_chars),
        )
        prompt += f"\nGenerate up to {args.items_per_video} GT QA items for this video."
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
            reason = validate_gt_item(item)
            if not reason:
                reason = validate_hard_item(item, args)
            if reason:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue
            append_jsonl(args.output, normalize_gt_item(item, row, index, selected_seed_examples, args))
            written += 1
        print(json.dumps({"video_id": row.get("video_id"), "gt_items": min(len(items), args.items_per_video)}, ensure_ascii=False), flush=True)
    print(json.dumps({"input_videos": len(rows), "written": written, "rejected": rejected}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
