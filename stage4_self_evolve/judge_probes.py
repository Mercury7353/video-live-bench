import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import (
    DEFAULT_OUTPUT_DIR,
    GeminiClient,
    extract_gemini_text,
    extract_json,
    extract_legacy_vectorengine_keys,
    get_env_keys,
    read_jsonl,
    write_jsonl,
)
from prompts import JUDGE_PROMPT


def bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return default


def make_client(args: argparse.Namespace) -> Optional[GeminiClient]:
    if args.heuristic_only:
        return None
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


def heuristic_correct(row: Dict[str, Any]) -> bool:
    ref = str(row.get("reference_answer", "")).strip().lower()
    ans = str(row.get("direct_answer", "")).strip().lower()
    if not ref or not ans:
        return False
    if ref == ans:
        return True
    ref_tokens = {t for t in ref.replace(".", "").replace(",", "").split() if len(t) > 1}
    ans_tokens = {t for t in ans.replace(".", "").replace(",", "").split() if len(t) > 1}
    if len(ref_tokens) <= 3:
        return ref_tokens <= ans_tokens
    overlap = len(ref_tokens & ans_tokens) / max(1, len(ref_tokens))
    return overlap >= 0.75


def judge_one(client: Optional[GeminiClient], row: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    if client is None:
        correct = heuristic_correct(row)
        return {
            "direct_model_correct": correct,
            "category_aligned": True,
            "gt_verified": True,
            "nontrivial": True,
            "failure_mode": "none" if correct else "other",
            "judgement": "heuristic lexical judge",
        }
    prompt = JUDGE_PROMPT.format(
        task_type=row.get("task_type", ""),
        question=row.get("question", ""),
        reference_answer=row.get("reference_answer", ""),
        evidence_spans=row.get("answer_span", []),
        harness_reasoning=row.get("harness_reasoning", ""),
        direct_answer=row.get("direct_answer", ""),
        direct_confidence=row.get("direct_confidence", ""),
        direct_reasoning=row.get("direct_reasoning_brief", ""),
    )
    response_text = client.generate(prompt, temperature=0.0, response_mime_type="application/json")
    model_text = extract_gemini_text(response_text)
    return extract_json(model_text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "direct_probes.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "judged_cases.jsonl")
    parser.add_argument("--hard-output", type=Path, default=DEFAULT_OUTPUT_DIR / "hard_cases.jsonl")
    parser.add_argument("--provider", choices=["vectorengine", "google"], default="vectorengine")
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--use-legacy-vectorengine-keys", action="store_true")
    parser.add_argument("--heuristic-only", action="store_true")
    parser.add_argument("--confidence-threshold", type=float, default=0.45)
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    client = make_client(args)
    judged = []
    hard_cases = []
    errors = []
    for row in rows:
        try:
            judgement = judge_one(client, row, args)
        except Exception as exc:
            if not args.continue_on_error:
                raise
            errors.append({"candidate_id": row.get("candidate_id"), "error": str(exc)})
            print(json.dumps({"candidate_id": row.get("candidate_id"), "error": str(exc)}, ensure_ascii=False), flush=True)
            continue
        merged = dict(row)
        merged.update(
            {
                "direct_model_correct": bool_value(judgement.get("direct_model_correct")),
                "category_aligned": bool_value(judgement.get("category_aligned"), True),
                "gt_verified": bool_value(judgement.get("gt_verified"), True),
                "nontrivial": bool_value(judgement.get("nontrivial"), True),
                "failure_mode": judgement.get("failure_mode", "other"),
                "judge_model": "heuristic" if client is None else args.model,
                "judge_provider": "heuristic" if client is None else args.provider,
                "judgement": judgement.get("judgement", ""),
            }
        )
        judged.append(merged)
        confidence = merged.get("direct_confidence")
        try:
            confidence_float = float(confidence)
        except Exception:
            confidence_float = 1.0
        is_hard = (
            merged["gt_verified"]
            and merged["category_aligned"]
            and merged["nontrivial"]
            and (not merged["direct_model_correct"] or confidence_float <= args.confidence_threshold)
        )
        if is_hard:
            hard_cases.append(merged)

    write_jsonl(args.output, judged)
    write_jsonl(args.hard_output, hard_cases)
    print(json.dumps({"judged": len(judged), "hard_cases": len(hard_cases), "errors": errors}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
