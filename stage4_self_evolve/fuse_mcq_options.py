import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List

from common import DEFAULT_OUTPUT_DIR, read_jsonl, write_jsonl


LABELS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def option_text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return str(value or "").strip()


def fuse_row(row: Dict[str, Any], seed: int) -> Dict[str, Any]:
    answer = str(row.get("reference_answer") or "").strip()
    distractors = [option_text(item) for item in row.get("distractors") or []]
    choices = [{"text": answer, "is_correct": True}]
    choices.extend({"text": text, "is_correct": False} for text in distractors if text)
    if len(choices) != 4:
        raise ValueError("fusion requires exactly one GT answer and three distractors")
    if len({item["text"].lower() for item in choices}) != 4:
        raise ValueError("fusion choices are not unique")

    rng = random.Random(f"{seed}:{row.get('candidate_id')}")
    rng.shuffle(choices)
    options: List[Dict[str, str]] = []
    correct_option = ""
    for index, item in enumerate(choices):
        label = LABELS[index]
        options.append({"label": label, "text": item["text"]})
        if item["is_correct"]:
            correct_option = label

    out = dict(row)
    out["generation_stage"] = "mcq_fusion"
    out["options"] = options
    out["correct_option"] = correct_option
    out["mcq_ready"] = True
    out["nontrivial_mcq"] = True
    out["option_fusion"] = {
        "method": "deterministic_shuffle",
        "seed": seed,
        "source": "reference_answer_plus_generated_distractors",
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_fused.jsonl")
    parser.add_argument("--seed", type=int, default=97)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    if args.limit is not None:
        rows = rows[: args.limit]
    fused = []
    rejected: Dict[str, int] = {}
    for row in rows:
        try:
            fused.append(fuse_row(row, args.seed))
        except Exception as exc:
            key = str(exc)
            rejected[key] = rejected.get(key, 0) + 1
    write_jsonl(args.output, fused)
    print(json.dumps({"input_items": len(rows), "written": len(fused), "rejected": rejected}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
