import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set

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
from prompts import DIRECT_PROBE_PROMPT


def existing_ids(path: Path) -> Set[str]:
    return {row.get("candidate_id", "") for row in read_jsonl(path)}


def make_client(args: argparse.Namespace) -> GeminiClient:
    file_keys: List[str] = []
    if args.api_key_file:
        text = args.api_key_file.read_text(encoding="utf-8").strip()
        if text:
            file_keys = [key.strip() for key in text.split(",") if key.strip()]
    keys: List[str]
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


def probe_one(client: GeminiClient, candidate: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    prompt = DIRECT_PROBE_PROMPT.format(question=candidate["question"])
    response_text = client.generate(
        prompt,
        video_url=candidate["url"],
        temperature=args.temperature,
        response_mime_type="application/json",
    )
    model_text = extract_gemini_text(response_text)
    parsed = extract_json(model_text)
    out = {
        "candidate_id": candidate["candidate_id"],
        "video_id": candidate["video_id"],
        "url": candidate["url"],
        "local_video_path": candidate.get("local_video_path"),
        "task_type": candidate["task_type"],
        "question": candidate["question"],
        "reference_answer": candidate["reference_answer"],
        "answer_span": candidate["answer_span"],
        "evidence_spans": candidate.get("evidence_spans") or candidate.get("answer_span"),
        "harness_reasoning": candidate["harness_reasoning"],
        "gt_verification_plan": candidate.get("gt_verification_plan", ""),
        "nontriviality_rationale": candidate.get("nontriviality_rationale", ""),
        "direct_model": args.model,
        "direct_provider": args.provider,
        "direct_answer": parsed.get("answer", ""),
        "direct_confidence": parsed.get("confidence", None),
        "direct_reasoning_brief": parsed.get("reasoning_brief", ""),
        "raw_response_text": response_text if args.keep_raw_response else None,
    }
    for key in [
        "generation_stage",
        "generation_source",
        "generator_model",
        "generator_provider",
        "benchmark_seed_ids",
        "benchmark_seed_sources",
        "benchmark_seed_capabilities",
        "benchmark_seed_examples",
        "benchmark_seed_stratify_fields",
    ]:
        if key in candidate:
            out[key] = candidate[key]
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "candidates.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "direct_probes.jsonl")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--provider", choices=["vectorengine", "google"], default="vectorengine")
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--use-legacy-vectorengine-keys", action="store_true")
    parser.add_argument("--keep-raw-response", action="store_true")
    args = parser.parse_args()

    candidates = read_jsonl(args.input)
    done = existing_ids(args.output)
    pending = [c for c in candidates if c.get("candidate_id") not in done]
    if args.limit is not None:
        pending = pending[: args.limit]
    client = make_client(args)

    success = 0
    failures = []
    for candidate in pending:
        try:
            row = probe_one(client, candidate, args)
            append_jsonl(args.output, row)
            success += 1
            print(json.dumps({"ok": candidate["candidate_id"], "answer": row["direct_answer"]}, ensure_ascii=False))
        except Exception as exc:
            failure = {"candidate_id": candidate.get("candidate_id"), "error": str(exc)}
            failures.append(failure)
            print(json.dumps(failure, ensure_ascii=False))
    print(json.dumps({"attempted": len(pending), "success": success, "failures": failures}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
