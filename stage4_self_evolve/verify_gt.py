import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import DEFAULT_OUTPUT_DIR, read_jsonl, write_jsonl


NUMBER_WORDS = {
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

YOLO_LABEL_HINTS = {
    "person": {"person", "people", "man", "men", "woman", "women", "boy", "girl"},
    "car": {"car", "cars", "vehicle", "vehicles"},
    "bus": {"bus", "buses"},
    "truck": {"truck", "trucks"},
    "dog": {"dog", "dogs"},
    "cat": {"cat", "cats"},
    "chair": {"chair", "chairs"},
    "tv": {"monitor", "screen", "tv", "television"},
    "laptop": {"laptop", "computer"},
    "book": {"book", "books"},
    "bottle": {"bottle", "bottles"},
}


def norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def compact_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def extract_number(text: str) -> Optional[int]:
    match = re.search(r"\b\d+\b", text)
    if match:
        return int(match.group(0))
    lower = text.lower()
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lower):
            return value
    return None


def verify_ocr(row: Dict[str, Any], threshold: float) -> Dict[str, Any]:
    answer = row.get("reference_answer", "")
    ocr_items = row.get("ocr_items", [])
    ocr_text = " ".join(item.get("text", "") for item in ocr_items)
    answer_compact = compact_text(answer)
    ocr_compact = compact_text(ocr_text)
    if not ocr_items:
        return verdict("inconclusive", False, "No OCR evidence was available.")
    if answer_compact and answer_compact in ocr_compact:
        return verdict("supported", True, "Reference answer text appears in OCR evidence.")
    ratio = SequenceMatcher(None, answer_compact, ocr_compact).ratio() if answer_compact else 0.0
    if ratio >= threshold:
        return verdict("supported", True, f"OCR evidence is similar to reference answer (ratio={ratio:.3f}).")
    return verdict(
        "inconclusive",
        False,
        f"OCR evidence did not strongly match reference answer (ratio={ratio:.3f}).",
    )


def infer_yolo_label(question: str, answer: str) -> Optional[str]:
    haystack = set(norm_text(f"{question} {answer}").split())
    for label, hints in YOLO_LABEL_HINTS.items():
        if haystack & hints:
            return label
    return None


def verify_counting(row: Dict[str, Any]) -> Dict[str, Any]:
    expected = extract_number(row.get("reference_answer", ""))
    if expected is None:
        return verdict("inconclusive", False, "Could not parse a count from reference answer.")
    label = infer_yolo_label(row.get("question", ""), row.get("reference_answer", ""))
    if not label:
        return verdict("inconclusive", False, "Question object does not map to a known YOLO label.")
    tracks = row.get("tracked_objects", [])
    detections = row.get("detections", [])
    if tracks:
        observed = sum(1 for item in tracks if item.get("label") == label)
        source = "tracks"
    else:
        observed = sum(1 for item in detections if item.get("label") == label)
        source = "frame detections"
    if observed == expected:
        return verdict("supported", True, f"YOLO {source} count for label '{label}' matches GT ({expected}).")
    if observed > 0:
        return verdict(
            "contradicted",
            False,
            f"YOLO {source} count for label '{label}' is {observed}, expected {expected}.",
        )
    return verdict("inconclusive", False, f"No YOLO evidence for mapped label '{label}'.")


def bbox_center(item: Dict[str, Any], key: str = "bbox_xyxy") -> Optional[tuple[float, float]]:
    bbox = item.get(key) or item.get("first_bbox_xyxy") or []
    if not isinstance(bbox, list) or len(bbox) < 4:
        return None
    return ((float(bbox[0]) + float(bbox[2])) / 2.0, (float(bbox[1]) + float(bbox[3])) / 2.0)


def verify_spatial(row: Dict[str, Any]) -> Dict[str, Any]:
    question = row.get("question", "").lower()
    if not any(term in question for term in ["left", "right", "above", "below", "closest", "nearest"]):
        return verdict("inconclusive", False, "No supported spatial relation keyword found.")
    objects = row.get("tracked_objects") or row.get("detections") or []
    if len(objects) < 2:
        return verdict("inconclusive", False, "Not enough detected objects for spatial verification.")
    return verdict(
        "inconclusive",
        False,
        "Spatial tool evidence exists, but semantic object-option matching is not implemented for this item.",
    )


def verdict(status: str, verified: bool, reason: str) -> Dict[str, Any]:
    return {
        "tool_verdict": status,
        "gt_tool_verified": verified,
        "tool_reason": reason,
    }


def verify_one(row: Dict[str, Any], threshold: float) -> Dict[str, Any]:
    result = dict(row)
    if row.get("evidence_status") != "ok":
        result.update(verdict("skipped", False, f"Evidence status is {row.get('evidence_status')}."))
        return result
    task_type = row.get("task_type")
    if task_type == "OCR":
        result.update(verify_ocr(row, threshold))
    elif task_type == "Counting":
        result.update(verify_counting(row))
    elif task_type == "Spatial":
        result.update(verify_spatial(row))
    else:
        result.update(verdict("inconclusive", False, f"No tool verifier implemented for task type {task_type}."))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_OUTPUT_DIR / "evidence_packs.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "gt_verifications.jsonl")
    parser.add_argument("--ocr-sim-threshold", type=float, default=0.72)
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    results = [verify_one(row, args.ocr_sim_threshold) for row in rows]
    write_jsonl(args.output, results)
    counts: Dict[str, int] = {}
    for row in results:
        key = row.get("tool_verdict", "unknown")
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({"verified_rows": len(results), "verdict_counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

