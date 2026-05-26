import argparse
import json
import random
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from common import DEFAULT_OUTPUT_DIR, read_jsonl, write_jsonl


LABELS = ["A", "B", "C", "D"]
OCR_WORD_REPLACEMENTS = {
    "MID": ["NEW", "SOFT", "RAW"],
    "WORN": ["WASHED", "WOOL", "WARM"],
    "KNITS": ["COATS", "SHIRTS", "WEAVES"],
    "DENIM": ["LINEN", "COTTON", "CANVAS"],
    "RAIN": ["WIND", "SUN", "SNOW"],
    "MODEL": ["STYLE", "FRAME", "DESIGN"],
    "MODELS": ["STYLES", "FRAMES", "DESIGNS"],
    "LORD": ["KING", "SAINT", "SRI"],
    "ALGY": ["ALBY", "ALGIE", "ALGO"],
}
RELATION_FLIPS = {
    "left": "right",
    "right": "left",
    "above": "below",
    "below": "above",
    "front": "behind",
    "behind": "front",
    "before": "after",
    "after": "before",
}
GENERIC_BAD_OPTIONS = [
    "It cannot be determined from the video.",
    "The video does not show enough information.",
    "None of the described events happens.",
]
SPATIAL_DIRECTION_OPTIONS = ["left", "right", "front", "back", "above", "below"]
SHORT_CLOSED_CLASS_OPTIONS = {
    "left",
    "right",
    "front",
    "back",
    "above",
    "below",
    "yes",
    "no",
    "red",
    "blue",
    "green",
    "yellow",
    "black",
    "white",
}
BRITTLE_QUESTION_PATTERNS = [
    r"\bexact timestamp\b",
    r"\bexact frame\b",
    r"\bframe number\b",
    r"\bsingle letter\b",
    r"\bminor detail\b",
]


def norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def compact_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def token_count(text: str) -> int:
    return len(norm_text(text).split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, compact_text(a), compact_text(b)).ratio()


def parse_count(text: str) -> Optional[int]:
    match = re.search(r"\b\d+\b", text)
    if match:
        return int(match.group(0))
    words = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    lower = text.lower()
    for word, value in words.items():
        if re.search(rf"\b{word}\b", lower):
            return value
    return None


def answer_profile(text: str) -> str:
    norm = norm_text(text)
    if not norm:
        return "empty"
    if norm in SPATIAL_DIRECTION_OPTIONS:
        return "direction"
    if norm in SHORT_CLOSED_CLASS_OPTIONS:
        return "closed_class"
    if parse_count(norm) is not None and len(norm.split()) <= 3:
        return "count"
    if any(ch.isalpha() for ch in text) and token_count(text) >= 2:
        return "text_phrase"
    return "other"


def ocr_like_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    words = norm_text(stripped).split()
    if len(words) < 2 or len(words) > 8:
        return False
    if re.search(r"[.!?]\s*$", stripped):
        return False
    if words[0] in {"the", "a", "an", "she", "he", "they", "it", "this", "that"}:
        return False
    letters = [ch for ch in stripped if ch.isalpha()]
    uppercase_letters = [ch for ch in letters if ch.isupper()]
    uppercase_ratio = len(uppercase_letters) / max(1, len(letters))
    has_sign_symbol = bool(re.search(r"[+&:/#0-9-]", stripped))
    title_like = sum(1 for word in stripped.split() if word[:1].isupper()) >= max(2, len(stripped.split()) - 1)
    return uppercase_ratio >= 0.45 or has_sign_symbol or title_like


def count_to_answer_like(correct: str, value: int) -> str:
    if re.search(r"\b\d+\b", correct):
        return re.sub(r"\b\d+\b", str(value), correct, count=1)
    return str(value)


def looks_like_brittle_question(row: Dict[str, Any]) -> Tuple[bool, List[str]]:
    question = row.get("question", "")
    answer = row.get("reference_answer", "")
    reasons = []
    if any(re.search(pattern, question.lower()) for pattern in BRITTLE_QUESTION_PATTERNS):
        reasons.append("question_mentions_frame_or_minor_detail")
    if token_count(answer) <= 1 and row.get("task_type") not in {"Counting", "Spatial"}:
        reasons.append("answer_is_too_short_for_non_counting_task")
    spans = row.get("answer_span") or row.get("question_span") or []
    has_duration = False
    if isinstance(spans, list):
        for span in spans:
            if isinstance(span, list) and len(span) >= 2:
                try:
                    if float(span[1]) - float(span[0]) >= 0.5:
                        has_duration = True
                        break
                except Exception:
                    continue
    if not has_duration:
        reasons.append("missing_or_too_short_temporal_evidence")
    return bool(reasons), reasons


def build_answer_bank(rows: Iterable[Dict[str, Any]]) -> Dict[str, List[str]]:
    bank: Dict[str, List[str]] = {}
    for row in rows:
        task = row.get("task_type", "")
        answer = str(row.get("reference_answer", "")).strip()
        if answer:
            bank.setdefault(task, []).append(answer)
            bank.setdefault("__all__", []).append(answer)
    return bank


def acceptable_distractor(correct: str, option: str, existing: List[str], task_type: str) -> Tuple[bool, str]:
    option = option.strip()
    correct_norm = norm_text(correct)
    option_norm = norm_text(option)
    if not option_norm:
        return False, "empty"
    if option_norm == correct_norm:
        return False, "same_as_correct"
    if any(option_norm == norm_text(item) for item in existing):
        return False, "duplicate_option"
    if compact_text(option) in compact_text(correct) or compact_text(correct) in compact_text(option):
        return False, "substring_overlap"
    sim = similarity(correct, option)
    max_similarity = 0.96 if task_type == "OCR" else 0.88
    if sim > max_similarity and task_type != "Counting":
        return False, "too_close_textually"
    if task_type in {"Reasoning", "Perception"} and token_count(option) <= 1:
        return False, "too_short_for_semantic_task"
    correct_profile = answer_profile(correct)
    option_profile = answer_profile(option)
    if task_type == "OCR":
        if correct_profile == "text_phrase" and option_profile != "text_phrase":
            return False, "ocr_shape_mismatch"
        if not ocr_like_text(option):
            return False, "ocr_not_display_text_like"
        correct_tokens = token_count(correct)
        option_tokens = token_count(option)
        if correct_tokens >= 3 and option_tokens < 2:
            return False, "ocr_distractor_too_short"
        if option_tokens > max(3, correct_tokens * 3):
            return False, "ocr_distractor_too_long"
    if task_type == "Spatial" and correct_profile == "direction" and option_profile != "direction":
        return False, "spatial_direction_mismatch"
    return True, "ok"


def spatial_relation_distractors(correct: str) -> List[str]:
    if answer_profile(correct) == "direction":
        return [item for item in SPATIAL_DIRECTION_OPTIONS if norm_text(item) != norm_text(correct)]
    lower = correct.lower()
    for source in SPATIAL_DIRECTION_OPTIONS:
        if re.search(rf"\b{re.escape(source)}\b", lower):
            return [
                re.sub(rf"\b{re.escape(source)}\b", target, correct, count=1, flags=re.I)
                for target in SPATIAL_DIRECTION_OPTIONS
                if target != source
            ]
    distractors = []
    for source, target in RELATION_FLIPS.items():
        if re.search(rf"\b{re.escape(source)}\b", lower):
            distractors.append(re.sub(rf"\b{re.escape(source)}\b", target, correct, count=1, flags=re.I))
    return distractors


def counting_distractors(correct: str) -> List[str]:
    value = parse_count(correct)
    if value is None:
        return []
    candidates = []
    for delta in [-2, -1, 1, 2, 3]:
        new_value = value + delta
        if new_value >= 0:
            candidates.append(str(new_value))
    return candidates


def replace_preserving_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement.title()
    return replacement.lower()


def mutate_ocr_token(token: str, rng: random.Random) -> str:
    if not token:
        return token
    upper = token.upper()
    replacements = OCR_WORD_REPLACEMENTS.get(upper)
    if replacements:
        return replace_preserving_case(token, rng.choice(replacements))
    if len(token) <= 2:
        return token
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if token.isupper() else "abcdefghijklmnopqrstuvwxyz"
    index = rng.randrange(len(token))
    current = token[index]
    if not current.isalpha():
        index = next((i for i, ch in enumerate(token) if ch.isalpha()), index)
        current = token[index]
    if not current.isalpha():
        return token
    choices = [ch for ch in alphabet if ch.lower() != current.lower()]
    return token[:index] + rng.choice(choices) + token[index + 1 :]


def ocr_text_distractors(correct: str, rng: random.Random) -> List[str]:
    parts = re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9]+", correct)
    word_indices = [i for i, part in enumerate(parts) if re.search(r"[A-Za-z0-9]", part)]
    if len(word_indices) < 2:
        return []
    candidates = []
    for word_index in word_indices:
        mutated = list(parts)
        mutated[word_index] = mutate_ocr_token(mutated[word_index], rng)
        text = "".join(mutated).strip()
        if norm_text(text) != norm_text(correct):
            candidates.append(text)
    if len(word_indices) >= 3:
        for _ in range(4):
            left, right = rng.sample(word_indices, 2)
            mutated = list(parts)
            mutated[left], mutated[right] = mutated[right], mutated[left]
            text = "".join(mutated).strip()
            if norm_text(text) != norm_text(correct):
                candidates.append(text)
    for _ in range(6):
        mutated = list(parts)
        for word_index in rng.sample(word_indices, min(2, len(word_indices))):
            mutated[word_index] = mutate_ocr_token(mutated[word_index], rng)
        text = "".join(mutated).strip()
        if norm_text(text) != norm_text(correct):
            candidates.append(text)
    return candidates


def bank_distractors(
    row: Dict[str, Any],
    answer_bank: Dict[str, List[str]],
    rng: random.Random,
    max_scan: int = 200,
) -> List[str]:
    task = row.get("task_type", "")
    correct = row.get("reference_answer", "")
    pool = list(answer_bank.get(task) or []) + list(answer_bank.get("__all__") or [])
    rng.shuffle(pool)
    picked = []
    rejects: Dict[str, int] = {}
    for option in pool[:max_scan]:
        ok, reason = acceptable_distractor(correct, option, picked, task)
        if ok:
            picked.append(option)
            if len(picked) >= 8:
                break
        else:
            rejects[reason] = rejects.get(reason, 0) + 1
    return picked


def generate_distractors(
    row: Dict[str, Any],
    answer_bank: Dict[str, List[str]],
    rng: random.Random,
) -> Tuple[List[str], Dict[str, Any]]:
    task = row.get("task_type", "")
    correct = str(row.get("reference_answer", "")).strip()
    sources = []
    candidates: List[str] = []
    if task == "OCR":
        candidates.extend(ocr_text_distractors(correct, rng))
        sources.append("ocr_text_mutation")
    if task == "Counting":
        candidates.extend(counting_distractors(correct))
        sources.append("count_perturbation")
    if task == "Spatial":
        candidates.extend(spatial_relation_distractors(correct))
        sources.append("relation_flip")
    if task not in {"Counting", "Spatial", "OCR"} or len(candidates) < 3:
        bank_items = bank_distractors(row, answer_bank, rng)
        candidates.extend(bank_items)
        sources.append("same_task_answer_bank")
    if len(candidates) < 3 and task not in {"OCR", "Counting"}:
        candidates.extend(GENERIC_BAD_OPTIONS)
        sources.append("generic_fallback")

    picked = []
    reject_counts: Dict[str, int] = {}
    for option in candidates:
        ok, reason = acceptable_distractor(correct, option, picked, task)
        if ok:
            picked.append(option.strip())
        else:
            reject_counts[reason] = reject_counts.get(reason, 0) + 1
        if len(picked) >= 3:
            break

    return picked, {
        "sources": sources,
        "reject_counts": reject_counts,
        "candidate_pool_size": len(candidates),
    }


def option_quality(correct: str, distractors: List[str], task_type: str) -> Tuple[bool, List[str]]:
    reasons = []
    if len(distractors) < 3:
        reasons.append("not_enough_distractors")
    all_options = [correct] + distractors
    norms = [norm_text(item) for item in all_options]
    if len(set(norms)) != len(norms):
        reasons.append("duplicate_options")
    pair_sims = []
    for i, left in enumerate(all_options):
        for right in all_options[i + 1 :]:
            pair_sims.append(similarity(left, right))
    if any(score > 0.90 for score in pair_sims) and task_type != "Counting":
        reasons.append("options_are_near_string_duplicates")
    if task_type in {"Reasoning", "Perception"}:
        reasons.append("semantic_distractors_need_model_review")
        lengths = [token_count(item) for item in all_options]
        if min(lengths) <= 1:
            reasons.append("semantic_options_too_short")
        if max(lengths) >= 5 * max(1, min(lengths)):
            reasons.append("option_length_leak")
    return not reasons, reasons


def build_mcq(row: Dict[str, Any], answer_bank: Dict[str, List[str]], rng: random.Random) -> Dict[str, Any]:
    result = dict(row)
    correct = str(row.get("reference_answer", "")).strip()
    correct_option_text = correct
    if row.get("task_type") == "Counting":
        parsed_count = parse_count(correct)
        if parsed_count is not None:
            correct_option_text = str(parsed_count)
    brittle, brittle_reasons = looks_like_brittle_question(row)
    distractors, trace = generate_distractors(row, answer_bank, rng)
    high_quality, option_reasons = option_quality(correct_option_text, distractors, row.get("task_type", ""))

    option_texts = [correct_option_text] + distractors[:3]
    rng.shuffle(option_texts)
    options = [{"label": LABELS[index], "text": text} for index, text in enumerate(option_texts)]
    correct_option = next(item["label"] for item in options if norm_text(item["text"]) == norm_text(correct_option_text))

    result.update(
        {
            "options": options,
            "correct_option": correct_option,
            "mcq_ready": len(options) == 4 and bool(correct) and high_quality and not brittle,
            "nontrivial_mcq": high_quality and not brittle,
            "triviality_risk_reasons": brittle_reasons + option_reasons,
            "distractor_generation": trace,
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "candidates.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "mcq_candidates.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--ready-only", action="store_true")
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    if args.limit is not None:
        rows = rows[: args.limit]
    rng = random.Random(args.seed)
    answer_bank = build_answer_bank(rows)
    mcq_rows = [build_mcq(row, answer_bank, rng) for row in rows]
    if args.ready_only:
        mcq_rows = [row for row in mcq_rows if row.get("mcq_ready")]
    count = write_jsonl(args.output, mcq_rows)
    summary: Dict[str, Any] = {
        "input_rows": len(rows),
        "written": count,
        "ready_rows": sum(1 for row in mcq_rows if row.get("mcq_ready")),
    }
    by_task: Dict[str, Dict[str, int]] = {}
    for row in mcq_rows:
        task = row.get("task_type", "unknown")
        bucket = by_task.setdefault(task, {"rows": 0, "ready": 0})
        bucket["rows"] += 1
        if row.get("mcq_ready"):
            bucket["ready"] += 1
    summary["by_task"] = by_task
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
