import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
    "longvideobench": {
        "benchmark": "LongVideoBench",
        "question": "question",
        "options": "candidates",
        "answer": "correct_choice",
        "answer_index_base": 0,
        "task_type": "question_category",
        "video_id": "video_id",
        "video_path": "video_path",
        "domain": "topic_category",
        "duration": "duration_group",
        "sub_category": "level",
    },
    "mlvu": {
        "benchmark": "MLVU",
        "question": "question",
        "options": "candidates",
        "answer": "answer",
        "task_type": "task_type",
        "video_id": "video",
        "video_path": "video",
        "duration": "duration",
    },
    "lsdbench": {
        "benchmark": "LSDBench",
        "question": "question",
        "answer": "correct_answer",
        "task_type": "question",
        "video_id": "video",
        "video_path": "video",
    },
    "video_holmes": {
        "benchmark": "Video-Holmes",
        "question": "Question",
        "options": "Options",
        "answer": "Answer",
        "task_type": "Question_Type",
        "video_id": "video_ID",
        "explanation": "Explanation",
    },
    "lvbench": {
        "benchmark": "LVBench",
        "question": "question",
        "answer": "answer",
        "task_type": "question_type",
        "video_id": "id",
        "url": "video_url",
        "video_path": "video_url",
        "domain": "video_type",
        "sub_category": "question_type",
        "time_reference": "time_reference",
    },
    "vsi_bench": {
        "benchmark": "VSI-Bench",
        "question": "question",
        "options": "options",
        "answer": "ground_truth",
        "task_type": "question_type",
        "video_id": "scene_name",
        "domain": "dataset",
        "sub_category": "question_type",
    },
    "cg_av_counting": {
        "benchmark": "CG-AV-Counting",
        "question": "question",
        "answer": "answer",
        "task_type": "type",
        "video_id": "video",
        "video_path": "video",
        "domain": "category",
        "sub_category": "type",
        "query_interval": "query_interval",
    },
    "mme_videoocr": {
        "benchmark": "MME-VideoOCR",
        "question": "question",
        "options": "option",
        "answer": "answer",
        "task_type": "task_type",
        "video_id": "video_index",
        "duration": "duration",
        "sub_category": "task",
        "eval_method": "eval_method",
    },
    "video_mmmu": {
        "benchmark": "Video-MMMU",
        "question": "question",
        "options": "options",
        "answer": "refanswer",
        "task_type": "question_type",
        "video_id": "video",
        "video_path": "video",
        "domain": "subject",
        "sub_category": "source",
    },
    "mmvu": {
        "benchmark": "MMVU",
        "question": "question",
        "options": "options",
        "answer": "refanswer",
        "task_type": "question_type",
        "video_id": "video",
        "video_path": "video",
        "domain": "subject",
    },
    "charades_sta": {
        "benchmark": "Charades-STA",
        "question": "question",
        "answer": "refanswer",
        "task_type": "temporal_grounding",
        "video_id": "video",
        "video_path": "video",
        "sub_category": "temporal_grounding",
    },
}


CONFIG_NAME_TO_SCHEMA = {
    "videomme": "video_mme",
    "longvideobench": "longvideobench",
    "mlvu": "mlvu",
    "hourvideobench_dev": "lsdbench",
    "lsdbench": "lsdbench",
    "video_holmes": "video_holmes",
    "video_mmmu": "video_mmmu",
    "mmvu": "mmvu",
    "charades_sta": "charades_sta",
    "lvbench": "lvbench",
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


def option_sort_key(label: str) -> Tuple[int, str]:
    labels = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    clean = str(label).strip().upper()
    if clean in labels:
        return labels.index(clean), clean
    try:
        return int(clean), clean
    except Exception:
        return len(labels), clean


def extract_embedded_options(question: str) -> Tuple[str, List[Dict[str, str]]]:
    options: List[Dict[str, str]] = []
    kept_lines: List[str] = []
    pattern = re.compile(r"^\s*(?:\(([A-Ha-h])\)|([A-Ha-h])[\.:：)]|([A-Ha-h])\s*:)\s*(.+?)\s*$")
    for line in str(question or "").splitlines():
        match = pattern.match(line)
        if match:
            label = (match.group(1) or match.group(2) or match.group(3) or "").upper()
            text = match.group(4).strip()
            if label and text:
                options.append({"label": label, "text": text})
            continue
        kept_lines.append(line)
    return "\n".join(line for line in kept_lines if line.strip()).strip(), options


def normalize_options(value: Any) -> List[Dict[str, str]]:
    parsed = parse_literal(value, value)
    labels = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    def label_for_index(index: int) -> str:
        return labels[index] if index < len(labels) else str(index + 1)

    def strip_label_prefix(text: str, default_label: str) -> tuple[str, str]:
        clean = text.strip()
        if len(clean) >= 2 and clean[0].upper() in labels and clean[1] in {".", ")", ":"}:
            return clean[0].upper(), clean[2:].strip()
        return default_label, clean

    if isinstance(parsed, list):
        options = []
        for idx, item in enumerate(parsed):
            if isinstance(item, dict):
                label = str(item.get("label") or label_for_index(idx))
                text = str(item.get("text") or item.get("option") or item.get("value") or "")
            else:
                label = label_for_index(idx)
                text = str(item)
            label, text = strip_label_prefix(text, label)
            if text:
                options.append({"label": label, "text": text})
        return options
    if isinstance(parsed, dict):
        return [
            {"label": str(label).upper(), "text": str(text)}
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
        label, part = strip_label_prefix(part, label_for_index(idx))
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


def normalize_answer_with_schema(value: Any, options: List[Dict[str, str]], schema: Dict[str, Any]) -> str:
    text = str(value or "").strip()
    if options and str(text).isdigit() and "answer_index_base" in schema:
        index = int(text) - int(schema["answer_index_base"])
        if 0 <= index < len(options):
            return options[index]["label"]
    return normalize_answer(value, options)


def canonicalize_capability(source_benchmark: str, task_type: str, question: str, sub_category: Any = None) -> Tuple[str, List[str]]:
    text = " ".join(
        str(item or "").lower()
        for item in [source_benchmark, task_type, question, sub_category]
    )
    tags: List[str] = []
    if any(term in text for term in ["ocr", "text", "subtitle", "caption", "sign", "visual_text"]):
        tags.append("OCR")
    if any(term in text for term in ["count", "how many", "number of", "cg-av"]):
        tags.append("Counting")
    if any(term in text for term in ["spatial", "left", "right", "front", "behind", "navigation", "room", "vsi"]):
        tags.append("Spatial")
    if any(term in text for term in ["temporal", "time", "before", "after", "order", "sequence", "grounding", "charades"]):
        tags.append("Temporal")
    if any(term in text for term in ["action", "event", "steps", "activity"]):
        tags.append("Action")
    if any(term in text for term in ["reason", "why", "infer", "intention", "relationship", "holmes", "causal"]):
        tags.append("Reasoning")
    if any(term in text for term in ["audio", "a2v", "v2a", "sound", "bell", "spoken"]):
        tags.append("AudioVisual")
    if any(term in text for term in ["longvideobench", "lvbench", "lsdbench", "hourvideobench"]):
        tags.append("LongContext")
    if any(term in text for term in ["vsi", "egocentric", "camera wearer", "room"]):
        tags.append("EgoSpatial")
    if any(term in text for term in ["object", "attribute", "recognition", "perception", "color"]):
        tags.append("Perception")
    if any(term in text for term in ["knowledge", "science", "biology", "chemistry", "geography", "subject"]):
        tags.append("DomainKnowledge")
    if not tags:
        tags.append("GeneralVideoQA")
    seen = []
    for tag in tags:
        if tag not in seen:
            seen.append(tag)
    return seen[0], seen


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
    raw_question = str(get_value(row, schema.get("question")) or "").replace("\\n", "\n").strip()
    question, embedded_options = extract_embedded_options(raw_question)
    if not question:
        return None
    options = normalize_options(get_value(row, schema.get("options")))
    if not options:
        options = normalize_options(first_present(row, "options", "candidates", "choices"))
    if not options and embedded_options:
        options = embedded_options
    options = sorted(options, key=lambda item: option_sort_key(item.get("label", "")))
    answer = normalize_answer_with_schema(get_value(row, schema.get("answer")), options, schema)
    task_field = schema.get("task_type")
    task_value = get_value(row, task_field)
    if task_value is None and task_field and task_field not in {"question"}:
        task_value = task_field
    task_type = str(task_value or "").strip()
    if schema.get("task_type") == "question":
        task_type = ""
    source_benchmark = schema.get("benchmark", "benchmark")
    sub_category = get_value(row, schema.get("sub_category"))
    capability, capability_tags = canonicalize_capability(source_benchmark, task_type, question, sub_category)
    source_task_type = task_type or capability
    out = {
        "seed_id": f"{source_benchmark}::{source_path.name}::{index:06d}",
        "source_benchmark": source_benchmark,
        "source_path": str(source_path),
        "video_id": get_value(row, schema.get("video_id")) or first_present(row, "video_id", "videoID", "video"),
        "url": get_value(row, schema.get("url")) or first_present(row, "url", "youtube_url"),
        "video_path": get_value(row, schema.get("video_path")) or first_present(row, "video_path", "video"),
        "duration": get_value(row, schema.get("duration")),
        "domain": get_value(row, schema.get("domain")),
        "sub_category": sub_category,
        "source_task_type": source_task_type,
        "task_type": source_task_type,
        "capability": capability,
        "capability_tags": capability_tags,
        "question": question,
        "options": options,
        "answer": answer,
        "raw_answer": get_value(row, schema.get("answer")),
        "seed_style_notes": infer_style_notes(question, options, task_type),
    }
    for optional in ("group_type", "group_structure", "query_interval", "time_reference", "eval_method", "explanation"):
        value = get_value(row, schema.get(optional))
        if value is not None:
            out[optional] = value
    return out


def load_manifest(path: Path) -> List[Tuple[str, Path]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    specs: List[Tuple[str, Path]] = []
    for name, item in data.items():
        schema_name = CONFIG_NAME_TO_SCHEMA.get(name)
        if not schema_name:
            continue
        source = item.get("tsv_path") or item.get("json_path") or item.get("path")
        if source:
            specs.append((schema_name, Path(source)))
    return specs


def parse_input_spec(value: str) -> Tuple[str, Path]:
    if "=" in value:
        schema_name, path = value.split("=", 1)
    elif ":" in value:
        schema_name, path = value.split(":", 1)
    else:
        raise ValueError("--input-spec must look like schema=/path/to/file")
    schema_name = schema_name.strip()
    if schema_name not in KNOWN_SCHEMAS:
        raise ValueError(f"Unknown schema in input spec: {schema_name}")
    return schema_name, Path(path.strip())


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    def counts(field: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for row in rows:
            values = row.get(field)
            if isinstance(values, list):
                for value in values:
                    out[str(value)] = out.get(str(value), 0) + 1
            else:
                out[str(values or "unknown")] = out.get(str(values or "unknown"), 0) + 1
        return dict(sorted(out.items(), key=lambda item: (-item[1], item[0])))

    return {
        "total": len(rows),
        "by_source_benchmark": counts("source_benchmark"),
        "by_capability": counts("capability"),
        "by_capability_tag": counts("capability_tags"),
        "by_source_task_type": counts("source_task_type"),
        "by_sub_category": counts("sub_category"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--input-spec", action="append", default=[])
    parser.add_argument("--manifest", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "benchmark_seed_bank.jsonl")
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--schema", choices=sorted(KNOWN_SCHEMAS), default="video_mme")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    specs: List[Tuple[str, Path]] = []
    for manifest in args.manifest:
        specs.extend(load_manifest(manifest))
    for item in args.input_spec:
        specs.append(parse_input_spec(item))
    for path in args.input:
        specs.append((args.schema, path))

    seeds: List[Dict[str, Any]] = []
    for schema_name, path in specs:
        schema = KNOWN_SCHEMAS[schema_name]
        if not path.exists():
            print(json.dumps({"status": "missing", "schema": schema_name, "path": str(path)}, ensure_ascii=False), flush=True)
            continue
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
    summary = summarize(seeds)
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"written": len(seeds), "output": str(args.output), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
