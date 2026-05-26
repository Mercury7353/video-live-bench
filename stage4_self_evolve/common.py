import ast
import csv
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent

STAGE4_DIR = PROJECT_ROOT / "stage4_self_evolve"
DEFAULT_OUTPUT_DIR = STAGE4_DIR / "outputs"


def repo_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> int:
    ensure_parent(path)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_literal(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (list, dict, bool, int, float)):
        return value
    text = str(value).strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        return ast.literal_eval(text)
    except Exception:
        return fallback


def video_id_from_url(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url or "")
    return match.group(1) if match else ""


def spans_total_duration(spans: Any) -> float:
    parsed = parse_literal(spans, [])
    total = 0.0
    if not isinstance(parsed, list):
        return total
    for item in parsed:
        if isinstance(item, list) and len(item) >= 2:
            try:
                total += max(0.0, float(item[1]) - float(item[0]))
            except Exception:
                continue
    return total


def extract_json(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("empty response")
    clean = text.strip()
    clean = clean.replace("```json", "```")
    if "```" in clean:
        parts = clean.split("```")
        candidates = [p.strip() for p in parts if "{" in p and "}" in p]
        if candidates:
            clean = candidates[-1]
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        clean = clean[start : end + 1]
    return json.loads(clean)


def extract_gemini_text(response_text: str) -> str:
    data = json.loads(response_text)
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [p.get("text", "") for p in parts if p.get("text") and not p.get("thought")]
    if texts:
        return "\n".join(texts)
    return "\n".join(p.get("text", "") for p in parts if p.get("text"))


def get_env_keys(*names: str) -> List[str]:
    keys = []
    for name in names:
        value = os.environ.get(name, "")
        if not value:
            continue
        keys.extend(k.strip() for k in value.split(",") if k.strip())
    return keys


def extract_legacy_vectorengine_keys() -> List[str]:
    keys = []
    for path in [
        repo_path("stage1_gen_q", "anno_q.py"),
        repo_path("stage2_fifter_q", "anno_qa_ref.py"),
    ]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        keys.extend(re.findall(r"sk-[A-Za-z0-9]+", text))
    seen = set()
    unique = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


class GeminiClient:
    def __init__(
        self,
        provider: str,
        model: str,
        api_keys: List[str],
        sleep_seconds: float = 1.0,
        timeout_seconds: int = 120,
    ) -> None:
        if provider not in {"vectorengine", "google"}:
            raise ValueError(f"Unsupported provider: {provider}")
        if not api_keys:
            raise ValueError("No API keys provided")
        self.provider = provider
        self.model = model
        self.api_keys = api_keys
        self.sleep_seconds = sleep_seconds
        self.timeout_seconds = timeout_seconds
        self._index = 0

    def _next_key(self) -> str:
        key = self.api_keys[self._index % len(self.api_keys)]
        self._index += 1
        return key

    def generate(
        self,
        prompt: str,
        *,
        video_url: Optional[str] = None,
        temperature: float = 0.0,
        response_mime_type: Optional[str] = "application/json",
    ) -> str:
        key = self._next_key()
        if self.provider == "vectorengine":
            url = f"https://api.vectorengine.ai/v1beta/models/{self.model}:generateContent?key={key}"
        else:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={key}"

        parts: List[Dict[str, Any]] = [{"text": prompt}]
        if video_url:
            parts.insert(
                0,
                {
                    "file_data": {
                        "mime_type": "video/mp4",
                        "file_uri": video_url,
                    }
                },
            )

        generation_config: Dict[str, Any] = {"temperature": temperature}
        if response_mime_type:
            generation_config["response_mime_type"] = response_mime_type
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini request failed: {exc.code} {error_text[:500]}") from exc
        finally:
            time.sleep(self.sleep_seconds)
        return response_text


def shuffled_sample(rows: List[Dict[str, Any]], limit: Optional[int], seed: int) -> List[Dict[str, Any]]:
    rows = list(rows)
    random.Random(seed).shuffle(rows)
    if limit is not None:
        rows = rows[:limit]
    return rows
