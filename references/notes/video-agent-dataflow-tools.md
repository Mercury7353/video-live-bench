# VideoAgentDataFlow Tool Survey

**Path:** `/mnt/afs/luhao2/workspace/VideoAgentDataFlow`

## Summary

This repo contains a multi-agent video captioner scaffold with reusable tool adapters.
For our self-evolving benchmark, the useful part is mainly the tool layer and tool API,
not necessarily the full caption-generation pipeline.

## Reusable Tools

### Video IO

Source: `/mnt/afs/luhao2/workspace/VideoAgentDataFlow/src/video_captioner/tools/video_io.py`

Class: `VideoIOManager`

Useful methods:

- `inspect(video_uri)`: returns duration, fps, resolution, audio availability.
- `extract_keyframes(video_uri, segment)`: samples keyframes for a time span.
- `export_segment_frames(video_uri, segment)`: exports frames at tracking fps.
- `export_segment_clip(video_uri, segment)`: writes a clip for a time span.

Use in our project:

- Build evidence packs for a candidate QA item's `answer_span`.
- Produce frame paths for OCR and YOLO verification.
- Avoid asking Gemini to inspect an entire YouTube video when only a short span matters.

### OCR

Source: `/mnt/afs/luhao2/workspace/VideoAgentDataFlow/src/video_captioner/tools/paddle_ocr.py`

Class: `PaddleOCRTool`

Input:

- `list[FrameArtifact]` with `image_path`, `frame_index`, and `frame_sec`.

Output:

- `list[OCRItem]` with:
  - `text`
  - `normalized_text`
  - `time_span`
  - `bbox_xyxy`
  - `confidence`

Can run either:

- directly with `paddleocr`, or
- through `config.ocr.api_url`.

Use in our project:

- Verify OCR answers and OCR distractors.
- Reject brittle OCR questions where only one tiny low-confidence item supports the GT.
- Create OCR distractors from nearby wrong text or partial text, then verify they are wrong.

### YOLO Detection / Tracking

Source: `/mnt/afs/luhao2/workspace/VideoAgentDataFlow/src/video_captioner/tools/ultralytics_yolo.py`

Class: `UltralyticsYOLOTool`

Useful methods:

- `detect_from_frames(frames)`: per-frame object detection.
- `track_from_segment_clip(clip)`: object tracking over a segment clip.

Outputs:

- `DetectionObservation` with label, score, bbox, timestamp.
- `TrackedObject` with label, track id, first/last bbox, sampled crops, score.

Can run either:

- directly with `ultralytics`, or
- through `config.yolo.api_url`.

Use in our project:

- Verify Counting questions by counting detections/tracks of relevant objects.
- Verify Spatial questions using bbox relations such as left/right/closest.
- Generate plausible distractors from other detected objects in the same span.

### ASR

Source: `/mnt/afs/luhao2/workspace/VideoAgentDataFlow/src/video_captioner/tools/whisper_asr.py`

Class: `WhisperASRTool`

Use in our project:

- Verify audio/subtitle-dependent questions if we decide to include audio.
- Current benchmark generation often avoids audio; keep this optional.

### Tool API Server

Source: `/mnt/afs/luhao2/workspace/VideoAgentDataFlow/src/video_captioner/tools/tool_api_server.py`

FastAPI endpoints:

- `GET /health`
- `POST /ocr/extract`
- `POST /asr/transcribe`
- `POST /yolo/detect_frames`
- `POST /yolo/track`
- `POST /reid/embeddings`

This is likely the safest integration path because it isolates heavy dependencies
such as PaddleOCR, Ultralytics, Whisper, InsightFace, CUDA, and model downloads.

## Recommended Integration

Add a small adapter in our repo instead of importing the whole pipeline:

```text
stage4_self_evolve/tool_adapters/
  video_agent_dataflow.py
```

The adapter should support:

- `extract_frames(video_path_or_url, spans)`
- `ocr_frames(frames)`
- `detect_frames(frames)`
- `track_span(video_path_or_url, span)`
- `verify_mcq_options(question, options, evidence)`

Use HTTP API when `VIDEO_AGENT_TOOL_API_URL` is set; otherwise keep a clear error
message that the external tool server is not configured.

## Immediate Use Cases

1. **OCR GT verification**
   - Extract frames from `answer_span`.
   - Run OCR.
   - Check whether the GT text or a close normalized form is present.

2. **OCR distractor verification**
   - Ensure the correct option is supported.
   - Ensure each distractor is not supported by the OCR evidence.
   - Prefer distractors from partial text, nearby wrong text, or visually similar text.

3. **Counting verification**
   - Run YOLO track on the answer span.
   - Use tracks instead of raw frame detections when possible to avoid duplicate counting.
   - Treat model count as supporting evidence, not final GT, because generic YOLO labels may be too coarse.

4. **Spatial verification**
   - Use bboxes to verify relations such as left/right/above/below/closest.
   - Reject items when objects are not detected with high confidence or relation changes across frames.

## Caveats

- The tool repo is a scaffold, not a polished package.
- PaddleOCR/YOLO/Whisper dependencies may not be installed in our current environment.
- Direct imports can create dependency conflicts; prefer the tool API server.
- YOLO default model is `yolo11n.pt`, which is broad but may miss domain-specific objects.
- For YouTube URLs, we may need a local downloaded video path before VideoIO can process it.
