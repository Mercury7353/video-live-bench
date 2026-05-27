import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Set

from common import DEFAULT_OUTPUT_DIR, GeminiClient, append_jsonl, extract_gemini_text, extract_json, read_jsonl
from prompts import DISTRACTOR_GENERATION_PROMPT


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


def normalize_distractors(parsed: Dict[str, Any], reference_answer: str, target: int) -> List[Dict[str, str]]:
    seen = {reference_answer.strip().lower()}
    out: List[Dict[str, str]] = []
    for item in parsed.get("distractors") or []:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            rationale = str(item.get("rationale") or "").strip()
            source = str(item.get("source") or "generated").strip()
        else:
            text = str(item).strip()
            rationale = ""
            source = "generated"
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "rationale": rationale, "source": source})
        if len(out) >= target:
            break
    return out


def load_seed_index(path: Path) -> Dict[str, Dict[str, Any]]:
    return {
        str(row.get("seed_id")): row
        for row in read_jsonl(path)
        if row.get("seed_id")
    }


def compact_seed_example(seed: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "seed_id": seed.get("seed_id"),
        "source_benchmark": seed.get("source_benchmark"),
        "source_task_type": seed.get("source_task_type"),
        "capability": seed.get("capability"),
        "question": seed.get("question"),
        "options": seed.get("options"),
        "answer": seed.get("answer"),
    }


def seed_examples_for_row(row: Dict[str, Any], seed_index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    existing = row.get("benchmark_seed_examples")
    if isinstance(existing, list) and existing:
        return [compact_seed_example(seed) for seed in existing if isinstance(seed, dict)]
    out = []
    for seed_id in row.get("benchmark_seed_ids") or []:
        seed = seed_index.get(str(seed_id))
        if seed:
            out.append(compact_seed_example(seed))
    return out


def simple_answer_key(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace(".", "").replace(",", "").split())


def load_wrong_answer_candidates(paths: List[Path]) -> Dict[str, List[Dict[str, Any]]]:
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    for path in paths:
        for row in read_jsonl(path):
            candidate_id = str(row.get("candidate_id") or "")
            answer = str(row.get("direct_answer") or row.get("answer") or "").strip()
            if not candidate_id or not answer:
                continue
            if str(row.get("direct_model_correct", "")).lower() == "true":
                continue
            by_id.setdefault(candidate_id, []).append(
                {
                    "answer": answer,
                    "source_file": str(path),
                    "model": row.get("direct_model") or row.get("eval_model"),
                    "provider": row.get("direct_provider") or row.get("eval_provider"),
                    "sample_index": row.get("sample_index"),
                    "confidence": row.get("direct_confidence") or row.get("confidence"),
                    "judge_correct": row.get("direct_model_correct"),
                    "failure_mode": row.get("failure_mode"),
                    "judgement": row.get("judgement"),
                }
            )
    return by_id


def wrong_answers_for_row(row: Dict[str, Any], wrong_answer_index: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    reference_key = simple_answer_key(row.get("reference_answer"))
    seen: Set[str] = {reference_key}
    out: List[Dict[str, Any]] = []
    if row.get("direct_answer"):
        wrong_answer_index.setdefault(str(row.get("candidate_id")), []).append(
            {
                "answer": row.get("direct_answer"),
                "model": row.get("direct_model"),
                "provider": row.get("direct_provider"),
                "sample_index": row.get("sample_index"),
                "confidence": row.get("direct_confidence"),
                "judge_correct": row.get("direct_model_correct"),
                "failure_mode": row.get("failure_mode"),
                "judgement": row.get("judgement"),
            }
        )
    for item in wrong_answer_index.get(str(row.get("candidate_id")), []):
        key = simple_answer_key(item.get("answer"))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "distractor_candidates.jsonl")
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--provider", choices=["google", "vectorengine"], default="google")
    parser.add_argument("--model", default="gemini-3.5-flash")
    parser.add_argument("--seed-examples", type=Path, default=None)
    parser.add_argument("--require-seed-examples", action="store_true")
    parser.add_argument("--wrong-answer-file", type=Path, action="append", default=[])
    parser.add_argument("--target-distractors", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    if args.limit is not None:
        rows = rows[: args.limit]
    seed_index = load_seed_index(args.seed_examples) if args.seed_examples else {}
    wrong_answer_index = load_wrong_answer_candidates(args.wrong_answer_file)
    client = GeminiClient(
        args.provider,
        args.model,
        load_keys(args),
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("", encoding="utf-8")

    written = 0
    rejected: Dict[str, int] = {}
    for row in rows:
        seed_examples = seed_examples_for_row(row, seed_index)
        wrong_answer_candidates = wrong_answers_for_row(row, wrong_answer_index)
        if args.require_seed_examples and not seed_examples:
            rejected["missing_seed_examples"] = rejected.get("missing_seed_examples", 0) + 1
            continue
        prompt = DISTRACTOR_GENERATION_PROMPT.format(
            num_distractors=args.target_distractors,
            task_type=row.get("task_type", ""),
            question=row.get("question", ""),
            reference_answer=row.get("reference_answer", ""),
            evidence_spans=row.get("evidence_spans") or row.get("question_span") or [],
            harness_reasoning=row.get("harness_reasoning", ""),
            gt_verification_plan=row.get("gt_verification_plan", ""),
            wrong_answer_candidates_json=json.dumps(wrong_answer_candidates, ensure_ascii=False, indent=2),
            seed_examples_json=json.dumps(seed_examples, ensure_ascii=False, indent=2),
        )
        try:
            response_text = client.generate(prompt, temperature=args.temperature, response_mime_type="application/json")
            parsed = extract_json(extract_gemini_text(response_text))
            distractors = normalize_distractors(parsed, str(row.get("reference_answer", "")), args.target_distractors)
        except Exception as exc:
            rejected["generation_error"] = rejected.get("generation_error", 0) + 1
            print(json.dumps({"candidate_id": row.get("candidate_id"), "error": str(exc)}, ensure_ascii=False), flush=True)
            continue
        if len(distractors) != args.target_distractors:
            rejected["bad_distractor_count"] = rejected.get("bad_distractor_count", 0) + 1
            continue
        out = dict(row)
        out["generation_stage"] = "distractors"
        out["distractor_model"] = args.model
        out["distractor_provider"] = args.provider
        out["distractors"] = distractors
        out["wrong_answer_candidates"] = wrong_answer_candidates
        out["discarded_equivalent_candidates"] = parsed.get("discarded_equivalent_candidates", [])
        out["distractor_rationale"] = parsed.get("distractor_rationale", "")
        out["benchmark_seed_examples"] = seed_examples
        append_jsonl(args.output, out)
        written += 1
        print(json.dumps({"ok": row.get("candidate_id"), "distractors": len(distractors)}, ensure_ascii=False), flush=True)
    print(json.dumps({"input_items": len(rows), "written": written, "rejected": rejected}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
