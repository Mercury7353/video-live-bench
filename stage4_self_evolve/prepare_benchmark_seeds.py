import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from common import DEFAULT_OUTPUT_DIR, parse_literal, write_jsonl


KNOWN_SCHEMAS = {
    "video_mme": {
        "benchmark": "Video-MME",
        "question": "question",
        "options": "candidates",
        "answer": "answer",
        "task_type": "task_type",
        "video_id": "video",
        "url": "url",
        "domain": "domain",
        "duration": "duration",
        "sub_category": "sub_category",
    },
    "video_mme_v2": {
        "benchmark": "Video-MME-v2",
        "question": "question",
        "options": "options",
        "answer": "answer",
        "task_type": "third_head",
        "video_id": "video_id",
        "url": "url",
        "domain": "second_head",
        "duration": "level",
        "sub_category": "third_head",
        "group_type": "group_type",
        "group_structure": "group_structure",
    },
}


def read_table(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "rows", "examples", "questions"):
                if isinstance(data.get(key), list):
                    return data[key]
            return list(data.values()) if all(isinstance(v, dict) for v in data.values()) else [data]
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    if suffix == ".tsv":
        with path.open("r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f, delimiter="\t"))
    if suffix == ".parquet":
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:
            raise RuntimeError("Reading parquet seed files requires pandas/pyarrow.") from exc
        return pd.read_parquet(path).to_dict(orient="records")
    raise ValueError(f"Unsupported seed file type: {path}")


def get_value(row: Dict[str, Any], field: Optional[str]) -> Any:
    if not field:
        return None
    return row.get(field)


def first_present(row: Dict[str, Any], *fields: str) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def normalize_options(value: Any) -> List[Dict[str, str]]:
    parsed = parse_literal(value, value)
    labels = list("ABCDEFGH")
    def strip_label_prefix(text: str, default_label: str) -> tuple[str, str]:
        clean = text.strip()
        if len(clean) >= 2 and clean[0].upper() in labels and clean[1] in {".", ")", ":"}:
            return clean[0].upper(), clean[2:].strip()
        return default_label, clean

    if isinstance(parsed, list):
        options = []
        for idx, item in enumerate(parsed):
            if isinstance(item, dict):
                label = str(item.get("label") or labels[idx])
                text = str(item.get("text") or item.get("option") or item.get("value") or "")
            else:
                label = labels[idx]
                text = str(item)
            label, text = strip_label_prefix(text, label)
            if text:
                options.append({"label": label, "text": text})
        return options
    if isinstance(parsed, dict):
        return [
            {"label": str(label), "text": str(text)}
            for label, text in parsed.items()
            if str(text)
        ]
    text = str(value or "").strip()
    if not text:
        return []
    try:
        return normalize_options(json.loads(text))
    except Exception:
        pass
    parts = [part.strip() for part in text.split("\n") if part.strip()]
    options = []
    for idx, part in enumerate(parts):
        label, part = strip_label_prefix(part, labels[idx])
        options.append({"label": label, "text": part})
    return options


def normalize_answer(value: Any, options: List[Dict[str, str]]) -> str:
    text = str(value or "").strip()
    if len(text) == 1 and text.upper() in {item["label"].upper() for item in options}:
        return text.upper()
    for item in options:
        if text and text.strip().lower() == item["text"].strip().lower():
            return item["label"]
    return text


def infer_style_notes(question: str, options: List[Dict[str, str]], task_type: str) -> List[str]:
    notes: List[str] = []
    lower = question.lower()
    if any(term in lower for term in ["before", "after", "sequence", "order", "first", "finally"]):
        notes.append("temporal_order")
    if any(term in lower for term in ["how many", "count", "number of"]):
        notes.append("counting_or_aggregation")
    if any(term in lower for term in ["why", "infer", "according to", "suggest"]):
        notes.append("reasoning")
    if any(term in lower for term in ["left", "right", "behind", "front", "near", "next to"]):
        notes.append("spatial_relation")
    if len(options) > 4:
        notes.append("large_option_set")
    if task_type:
        notes.append(f"task:{task_type}")
    return notes


def normalize_row(row: Dict[str, Any], schema: Dict[str, str], source_path: Path, index: int) -> Optional[Dict[str, Any]]:
    question = str(get_value(row, schema.get("question")) or "").strip()
    if not question:
        return None
    options = normalize_options(get_value(row, schema.get("options")))
    if not options:
        options = normalize_options(first_present(row, "options", "candidates", "choices"))
    answer = normalize_answer(get_value(row, schema.get("answer")), options)
    task_type = str(get_value(row, schema.get("task_type")) or "").strip()
    out = {
        "seed_id": f"{schema.get('benchmark', 'benchmark')}::{source_path.name}::{index:06d}",
        "source_benchmark": schema.get("benchmark", "benchmark"),
        "source_path": str(source_path),
        "video_id": get_value(row, schema.get("video_id")) or first_present(row, "video_id", "videoID", "video"),
        "url": get_value(row, schema.get("url")) or first_present(row, "url", "youtube_url"),
        "duration": get_value(row, schema.get("duration")),
        "domain": get_value(row, schema.get("domain")),
        "sub_category": get_value(row, schema.get("sub_category")),
        "task_type": task_type,
        "question": question,
        "options": options,
        "answer": answer,
        "raw_answer": get_value(row, schema.get("answer")),
        "seed_style_notes": infer_style_notes(question, options, task_type),
    }
    for optional in ("group_type", "group_structure"):
        value = get_value(row, schema.get(optional))
        if value is not None:
            out[optional] = value
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "benchmark_seed_bank.jsonl")
    parser.add_argument("--schema", choices=sorted(KNOWN_SCHEMAS), default="video_mme")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    schema = KNOWN_SCHEMAS[args.schema]
    seeds: List[Dict[str, Any]] = []
    for path in args.input:
        rows = read_table(path)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            normalized = normalize_row(row, schema, path, index)
            if normalized:
                seeds.append(normalized)
    if args.limit is not None:
        seeds = seeds[: args.limit]
    write_jsonl(args.output, seeds)
    print(json.dumps({"written": len(seeds), "output": str(args.output), "schema": args.schema}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
