import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from common import DEFAULT_OUTPUT_DIR, ensure_parent


DEFAULT_QUERIES = [
    "video understanding agent OCR ASR YOLO",
    "video question answering agent object tracking",
    "video RAG OCR ASR object detection",
    "multimodal video analysis agent temporal grounding",
]

CURATED_SKILLS = [
    {
        "id": "clawhub-openclaw-video-understand",
        "name": "OpenClaw video-understand",
        "source_type": "clawhub",
        "source": "https://llmbase.ai/openclaw/video-understand/",
        "capabilities": ["video_analysis", "local_video", "youtube", "transcription", "timestamped_qa"],
    },
    {
        "id": "clawhub-wayinvideo-video-understanding",
        "name": "WayinVideo video understanding and clipping",
        "source_type": "clawhub",
        "source": "https://wayin.ai/api-docs/skills-video-understanding-and-ai-clipping/",
        "capabilities": ["video_summary", "find_moments", "transcription", "clipping"],
    },
    {
        "id": "agent-skill-gemini-video-understanding",
        "name": "Gemini video understanding skill",
        "source_type": "agent_skill_marketplace",
        "source": "https://eliteai.tools/agent-skills/gemini-video-understanding",
        "capabilities": ["gemini_video", "youtube", "timeline_detection", "timestamp_query", "transcription"],
    },
]


def github_search(query: str, limit: int) -> List[Dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query, "sort": "updated", "order": "desc", "per_page": min(limit, 20)})
    request = urllib.request.Request(
        f"https://api.github.com/search/repositories?{params}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "video-live-bench-skill-discovery",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    out = []
    for item in data.get("items") or []:
        text = " ".join(
            str(item.get(key) or "")
            for key in ("name", "full_name", "description", "topics", "language")
        ).lower()
        capabilities = []
        for key, capability in [
            ("ocr", "ocr"),
            ("asr", "asr"),
            ("whisper", "asr"),
            ("yolo", "object_detection"),
            ("tracking", "tracking"),
            ("rag", "retrieval"),
            ("ground", "grounding"),
            ("video", "video_analysis"),
        ]:
            if key in text and capability not in capabilities:
                capabilities.append(capability)
        out.append(
            {
                "id": f"github-{item.get('full_name', '').replace('/', '-').lower()}",
                "name": item.get("full_name"),
                "source_type": "github_repo",
                "source": item.get("html_url"),
                "description": item.get("description"),
                "language": item.get("language"),
                "stars": item.get("stargazers_count"),
                "forks": item.get("forks_count"),
                "updated_at": item.get("updated_at"),
                "topics": item.get("topics") or [],
                "capabilities": capabilities,
                "discovery_query": query,
            }
        )
    return out


def score_candidate(row: Dict[str, Any]) -> Dict[str, Any]:
    caps = set(row.get("capabilities") or [])
    score = 0
    reasons = []
    for cap in ["ocr", "asr", "object_detection", "tracking", "grounding", "retrieval", "video_analysis"]:
        if cap in caps:
            score += 2
            reasons.append(f"capability:{cap}")
    stars = int(row.get("stars") or 0)
    if stars >= 1000:
        score += 3
        reasons.append("stars>=1000")
    elif stars >= 100:
        score += 2
        reasons.append("stars>=100")
    elif stars >= 20:
        score += 1
        reasons.append("stars>=20")
    if row.get("source_type") in {"clawhub", "agent_skill_marketplace"}:
        score += 1
        reasons.append("agent_skill_packaging")
    row = dict(row)
    row["score"] = score
    row["score_reasons"] = reasons
    row["status"] = "candidate_external"
    row["integration_policy"] = "inspect, sandbox, and reimplement minimal adapter before use"
    return row


def dedupe(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for row in rows:
        key = row.get("source") or row.get("id")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR / "video_skill_discovery.json")
    parser.add_argument("--github-limit-per-query", type=int, default=5)
    parser.add_argument("--skip-github", action="store_true")
    parser.add_argument("--query", action="append", default=[])
    args = parser.parse_args()

    rows = list(CURATED_SKILLS)
    errors = []
    if not args.skip_github:
        for query in args.query or DEFAULT_QUERIES:
            try:
                rows.extend(github_search(query, args.github_limit_per_query))
            except Exception as exc:
                errors.append({"query": query, "error": str(exc)})
            time.sleep(1.0)
    scored = sorted((score_candidate(row) for row in dedupe(rows)), key=lambda item: item.get("score", 0), reverse=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "queries": args.query or DEFAULT_QUERIES,
        "errors": errors,
        "candidates": scored,
    }
    ensure_parent(args.output)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": len(scored), "errors": len(errors), "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
