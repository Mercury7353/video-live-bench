import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from common import GeminiClient, extract_gemini_text, extract_json, read_jsonl


STRATEGY_PROMPT = """You are designing the next evolution strategy for a live video benchmark.

The benchmark pipeline is:
fresh/local videos -> harness evidence -> strong model writes GT -> direct model probes
-> wrong answers become distractors -> MCQ fusion -> options-only and direct-video gates.

Given recent validation summaries and example cases, propose the next generation
strategy. The goal is aligned, nontrivial, verifiable video understanding with
better model separation. Do not propose arbitrary trivia. Avoid fragile tiny
details and GT that cannot be checked by harness evidence.

Return JSON only:
{{
  "strategy_id": "short id",
  "prompt_addendum": "compact prompt text to append to GT generation",
  "target_question_patterns": ["pattern"],
  "avoid_question_patterns": ["pattern"],
  "distractor_lessons": ["lesson"],
  "harness_skill_needs": ["ocr|yolo|asr|tracking|temporal_reasoning|audio_visual_alignment|retrieval"],
  "success_metrics": ["metric"],
  "risk_controls": ["control"]
}}

Recent evidence:
{evidence_json}
"""


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


def compact_rows(path: Path, limit: int) -> List[Dict[str, Any]]:
    rows = []
    for row in read_jsonl(path)[:limit]:
        rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "video_id": row.get("video_id"),
                "task_type": row.get("task_type"),
                "question": row.get("question"),
                "reference_answer": row.get("reference_answer"),
                "direct_answer": row.get("direct_answer"),
                "direct_model_correct": row.get("direct_model_correct"),
                "failure_mode": row.get("failure_mode"),
                "judgement": row.get("judgement"),
                "options": row.get("options"),
                "correct_option": row.get("correct_option"),
                "harness_reasoning": row.get("harness_reasoning"),
                "evolution": row.get("evolution"),
            }
        )
    return rows


def eval_summary(path: Path) -> Dict[str, Any]:
    rows = [row for row in read_jsonl(path) if not row.get("error")]
    correct = sum(1 for row in rows if row.get("is_correct"))
    return {
        "path": str(path),
        "items": len(rows),
        "correct": correct,
        "accuracy": round(correct / len(rows), 4) if rows else None,
        "examples": [
            {
                "candidate_id": row.get("candidate_id"),
                "eval_model": row.get("eval_model"),
                "eval_mode": row.get("eval_mode"),
                "pred_option": row.get("pred_option"),
                "correct_option": row.get("correct_option"),
                "is_correct": row.get("is_correct"),
                "reasoning_brief": row.get("reasoning_brief"),
            }
            for row in rows[:8]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--provider", choices=["google", "vectorengine"], default="google")
    parser.add_argument("--model", default="gemini-3.5-flash")
    parser.add_argument("--case-file", type=Path, action="append", default=[])
    parser.add_argument("--eval-file", type=Path, action="append", default=[])
    parser.add_argument("--notes", default="")
    parser.add_argument("--limit-per-file", type=int, default=12)
    parser.add_argument("--temperature", type=float, default=0.25)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    evidence = {
        "notes": args.notes,
        "case_files": {str(path): compact_rows(path, args.limit_per_file) for path in args.case_file},
        "eval_files": [eval_summary(path) for path in args.eval_file],
    }
    client = GeminiClient(
        args.provider,
        args.model,
        load_keys(args),
        sleep_seconds=args.sleep_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    prompt = STRATEGY_PROMPT.format(evidence_json=json.dumps(evidence, ensure_ascii=False, indent=2))
    parsed = extract_json(extract_gemini_text(client.generate(prompt, temperature=args.temperature, response_mime_type="application/json")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "strategy_id": parsed.get("strategy_id")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
