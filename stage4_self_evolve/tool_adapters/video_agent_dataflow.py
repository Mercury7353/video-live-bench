from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from common import DEFAULT_OUTPUT_DIR, video_id_from_url


VIDEO_SUFFIXES = (".mp4", ".mkv", ".webm", ".mov", ".avi")


class ToolAPIError(RuntimeError):
    pass


class LocalVideoResolver:
    """Resolve YouTube-style candidate URLs to local video files."""

    def __init__(self, cache_dirs: Iterable[str | Path] = ()) -> None:
        dirs = list(cache_dirs)
        env_dirs = [
            os.environ.get("VIDLIVE_VIDEO_CACHE_DIR"),
            os.environ.get("VIDEO_CACHE_DIR"),
        ]
        dirs.extend(d for d in env_dirs if d)
        dirs.append(DEFAULT_OUTPUT_DIR / "video_cache")
        self.cache_dirs = [Path(d).expanduser() for d in dirs if d]

    def resolve(self, candidate: Dict[str, Any]) -> Optional[Path]:
        explicit = candidate.get("video_path") or candidate.get("local_video_path")
        if explicit and Path(explicit).exists():
            return Path(explicit)

        url = candidate.get("url", "")
        video_id = candidate.get("video_id") or video_id_from_url(url)
        if not video_id:
            return None

        for directory in self.cache_dirs:
            for suffix in VIDEO_SUFFIXES:
                path = directory / f"{video_id}{suffix}"
                if path.exists():
                    return path
        return None


class FFmpegVideoExtractor:
    """Minimal frame/clip exporter that does not require OpenCV."""

    def __init__(self, output_root: Path = DEFAULT_OUTPUT_DIR / "evidence_media") -> None:
        self.output_root = output_root
        self.ffmpeg = shutil.which("ffmpeg")

    def available(self) -> bool:
        return self.ffmpeg is not None

    def extract_frames(
        self,
        video_path: Path,
        spans: List[List[float]],
        candidate_id: str,
        frames_per_span: int = 3,
    ) -> List[Dict[str, Any]]:
        if not self.ffmpeg:
            raise RuntimeError("ffmpeg is not available")
        out_dir = self.output_root / candidate_id / "frames"
        out_dir.mkdir(parents=True, exist_ok=True)
        frame_rows: List[Dict[str, Any]] = []
        for span_index, span in enumerate(spans):
            if not isinstance(span, list) or len(span) < 2:
                continue
            start = max(0.0, float(span[0]))
            end = max(start, float(span[1]))
            sample_secs = self._sample_times(start, end, frames_per_span)
            for sample_index, sec in enumerate(sample_secs):
                image_path = out_dir / f"span{span_index:02d}_{sample_index:02d}_{sec:.2f}.jpg"
                cmd = [
                    self.ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{sec:.3f}",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    "-y",
                    str(image_path),
                ]
                subprocess.run(cmd, check=True)
                if image_path.exists():
                    frame_rows.append(
                        {
                            "image_path": str(image_path),
                            "frame_index": int(round(sec * 1000.0)),
                            "frame_sec": sec,
                        }
                    )
        return frame_rows

    def export_clip(
        self,
        video_path: Path,
        span: List[float],
        candidate_id: str,
    ) -> Optional[Dict[str, Any]]:
        if not self.ffmpeg:
            raise RuntimeError("ffmpeg is not available")
        if not isinstance(span, list) or len(span) < 2:
            return None
        start = max(0.0, float(span[0]))
        end = max(start + 0.1, float(span[1]))
        duration = max(0.1, end - start)
        out_dir = self.output_root / candidate_id / "clips"
        out_dir.mkdir(parents=True, exist_ok=True)
        clip_path = out_dir / f"{start:.2f}_{end:.2f}.mp4"
        cmd = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-y",
            str(clip_path),
        ]
        subprocess.run(cmd, check=True)
        if not clip_path.exists():
            return None
        return {
            "clip_path": str(clip_path),
            "fps": 30.0,
            "start_sec": start,
            "end_sec": end,
        }

    def _sample_times(self, start: float, end: float, count: int) -> List[float]:
        count = max(1, count)
        if end <= start + 0.05 or count == 1:
            return [start]
        if count == 2:
            return [start, max(start, end - 0.05)]
        return [
            start + ((end - start) * i / (count - 1))
            for i in range(count)
        ]


class VideoAgentDataFlowClient:
    """HTTP client for VideoAgentDataFlow's FastAPI tool server."""

    def __init__(self, api_url: Optional[str] = None, timeout_sec: float = 300.0) -> None:
        self.api_url = (api_url or os.environ.get("VIDEO_AGENT_TOOL_API_URL") or "").rstrip("/")
        self.timeout_sec = timeout_sec

    def configured(self) -> bool:
        return bool(self.api_url)

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health")

    def ocr_extract(self, frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        body = self._request("POST", "/ocr/extract", {"frames": frames})
        return body.get("items", []) if isinstance(body, dict) else []

    def yolo_detect_frames(self, frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        body = self._request("POST", "/yolo/detect_frames", {"frames": frames})
        return body.get("detections", []) if isinstance(body, dict) else []

    def yolo_track(self, clip: Dict[str, Any]) -> List[Dict[str, Any]]:
        body = self._request("POST", "/yolo/track", {"clip": clip})
        return body.get("tracked_objects", []) if isinstance(body, dict) else []

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.api_url:
            raise ToolAPIError("VIDEO_AGENT_TOOL_API_URL is not configured")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            raise ToolAPIError(f"{method} {path} failed: {exc.code} {error_text[:500]}") from exc
        except Exception as exc:
            raise ToolAPIError(f"{method} {path} failed: {exc}") from exc
        return json.loads(text) if text else {}

