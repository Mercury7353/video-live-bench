import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Set

from common import DEFAULT_OUTPUT_DIR, GeminiClient, append_jsonl, extract_gemini_text, extract_json, read_jsonl
from prompts import MCQ_EVOLUTION_PROMPT


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


def simple_answer_key(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace(".", "").replace(",", "").split())


def load_eval_feedback(paths: List[Path]) -> Dict[str, List[Dict[str, Any]]]:
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    for path in paths:
        for row in read_jsonl(path):
            candidate_id = str(row.get("candidate_id") or row.get("ok") or "")
            if not candidate_id or row.get("error"):
                continue
            by_id.setdefault(candidate_id, []).append(
                {
                    "source_file": str(path),
                    "eval_model": row.get("eval_model"),
                    "eval_provider": row.get("eval_provider"),
                    "eval_mode": row.get("eval_mode"),
                    "pred_option": row.get("pred_option") or row.get("answer"),
                    "correct_option": row.get("correct_option") or row.get("correct"),
                    "is_correct": row.get("is_correct"),
                    "confidence": row.get("confidence"),
                    "reasoning_brief": row.get("reasoning_brief"),
                }
            )
    return by_id


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
    for item in row.get("wrong_answer_candidates") or []:
        answer = str(item.get("answer") or "").strip()
        key = simple_answer_key(answer)
        if answer and key and key not in seen:
            seen.add(key)
            out.append(item)
    for item in wrong_answer_index.get(str(row.get("candidate_id")), []):
        key = simple_answer_key(item.get("answer"))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def normalize_distractors(parsed: Dict[str, Any], reference_answer: str, target: int) -> List[Dict[str, str]]:
    seen = {simple_answer_key(reference_answer)}
    out: List[Dict[str, str]] = []
    for item in parsed.get("distractors") or []:
        if isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            source = str(item.get("source") or "rewritten").strip()
            rationale = str(item.get("rationale") or "").strip()
        else:
            text = str(item).strip()
            source = "rewritten"
            rationale = ""
        key = simple_answer_key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "source": source, "rationale": rationale})
        if len(out) >= target:
            break
    return out


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


def load_seed_index(path: Path) -> Dict[str, Dict[str, Any]]:
    return {str(row.get("seed_id")): row for row in read_jsonl(path) if row.get("seed_id")}


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


def has_options_leakage(feedback: List[Dict[str, Any]]) -> bool:
    return any(item.get("eval_mode") == "gemini_options" and item.get("is_correct") for item in feedback)


def should_process(row: Dict[str, Any], feedback: List[Dict[str, Any]], args: argparse.Namespace) -> bool:
    if args.only_options_leakage and not has_options_leakage(feedback):
        return False
    if args.require_feedback and not feedback:
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "evolved_distractors.jsonl")
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--provider", choices=["google", "vectorengine"], default="google")
    parser.add_argument("--model", default="gemini-3.5-flash")
    parser.add_argument("--eval-file", type=Path, action="append", default=[])
    parser.add_argument("--wrong-answer-file", type=Path, action="append", default=[])
    parser.add_argument("--seed-examples", type=Path, default=None)
    parser.add_argument("--target-mode", choices=["frontier_hard", "mid_tier", "leakfree"], default="mid_tier")
    parser.add_argument("--round-id", default="evo01")
    parser.add_argument("--target-distractors", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-options-leakage", action="store_true")
    parser.add_argument("--require-feedback", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    rows = read_jsonl(args.candidates)
    if args.limit is not None:
        rows = rows[: args.limit]
    feedback_index = load_eval_feedback(args.eval_file)
    wrong_answer_index = load_wrong_answer_candidates(args.wrong_answer_file)
    seed_index = load_seed_index(args.seed_examples) if args.seed_examples else {}
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
    skipped = 0
    rejected: Dict[str, int] = {}
    for row in rows:
        candidate_id = str(row.get("candidate_id") or "")
        feedback = feedback_index.get(candidate_id, [])
        if not should_process(row, feedback, args):
            skipped += 1
            continue
        seed_examples = seed_examples_for_row(row, seed_index)
        wrong_answer_candidates = wrong_answers_for_row(row, wrong_answer_index)
        prompt = MCQ_EVOLUTION_PROMPT.format(
            target_mode=args.target_mode,
            task_type=row.get("task_type", ""),
            question=row.get("question", ""),
            reference_answer=row.get("reference_answer", ""),
            evidence_spans=row.get("evidence_spans") or row.get("question_span") or [],
            harness_reasoning=row.get("harness_reasoning", ""),
            gt_verification_plan=row.get("gt_verification_plan", ""),
            nontriviality_rationale=row.get("nontriviality_rationale", ""),
            options_json=json.dumps(row.get("options") or [], ensure_ascii=False, indent=2),
            correct_option=row.get("correct_option", ""),
            feedback_json=json.dumps(feedback, ensure_ascii=False, indent=2),
            wrong_answer_candidates_json=json.dumps(wrong_answer_candidates, ensure_ascii=False, indent=2),
            seed_examples_json=json.dumps(seed_examples, ensure_ascii=False, indent=2),
            num_distractors=args.target_distractors,
        )
        try:
            response_text = client.generate(prompt, temperature=args.temperature, response_mime_type="application/json")
            parsed = extract_json(extract_gemini_text(response_text))
        except Exception as exc:
            rejected["generation_error"] = rejected.get("generation_error", 0) + 1
            print(json.dumps({"candidate_id": candidate_id, "error": str(exc)}, ensure_ascii=False), flush=True)
            continue

        action = str(parsed.get("action") or "").strip()
        if action in {"drop", "regenerate_from_video"}:
            rejected[action] = rejected.get(action, 0) + 1
            continue
        distractors = normalize_distractors(parsed, str(row.get("reference_answer", "")), args.target_distractors)
        if len(distractors) != args.target_distractors:
            rejected["bad_distractor_count"] = rejected.get("bad_distractor_count", 0) + 1
            continue

        out = dict(row)
        out["candidate_id"] = f"{candidate_id}--{args.round_id}"
        out["evolution_parent_candidate_id"] = candidate_id
        out["generation_stage"] = "mcq_feedback_evolution"
        out["question"] = str(parsed.get("revised_question") or row.get("question") or "").strip()
        out["reference_answer"] = str(parsed.get("reference_answer") or row.get("reference_answer") or "").strip()
        out["distractors"] = distractors
        out.pop("options", None)
        out.pop("correct_option", None)
        out.pop("option_fusion", None)
        out["evolution"] = {
            "round_id": args.round_id,
            "target_mode": args.target_mode,
            "model": args.model,
            "provider": args.provider,
            "action": action,
            "feedback": feedback,
            "wrong_answer_candidates": wrong_answer_candidates,
            "discarded_equivalent_candidates": parsed.get("discarded_equivalent_candidates", []),
            "skill_plan": parsed.get("skill_plan", []),
            "expected_gate_improvement": parsed.get("expected_gate_improvement", ""),
            "gt_risk": parsed.get("gt_risk", ""),
            "triviality_risk": parsed.get("triviality_risk", ""),
            "notes": parsed.get("notes", ""),
        }
        append_jsonl(args.output, out)
        written += 1
        print(json.dumps({"ok": candidate_id, "action": action, "evolved": out["candidate_id"]}, ensure_ascii=False), flush=True)

    print(json.dumps({"input_items": len(rows), "written": written, "skipped": skipped, "rejected": rejected}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
