# LiveBench Execution Roadmap - 2026-05-27

## Target

Build the first harness-first pilot at roughly 100 local videos, then generate and
validate benchmark questions from harness evidence rather than from Stage2 bootstrap
question text.

## Operating Rules

- Keep a roadmap/status document updated after each completed step.
- Push code and documentation to `git@github.com:Mercury7353/video-live-bench.git`.
- Do not commit local videos, cookies, API keys, or large transient outputs.
- Treat the existing Stage2-derived V0 as infrastructure/debugging only, not as the
  final benchmark generation method.

## Current Baseline

- V0 accepted benchmark items: 30.
- V0 local videos available: 21.
- Available candidate source for scale-up: `stage4_self_evolve/outputs/v0_150_candidates.jsonl`.
- Candidate source size: 150 rows, 126 unique videos.

## Step Plan

### Step 1: Repository and Roadmap Setup

Status: completed.

Actions:

- Added GitHub remote.
- Added this execution roadmap.
- Pushed a clean skeleton branch to GitHub.
- The pushed branch excludes data, videos, outputs, original benchmark files, and keys.

### Step 2: Build a 100-Video Local Pool

Status: in progress.

Actions:

- Select approximately 100 unique videos from the available candidate pool.
- Use the existing resumable `yt-dlp` downloader with cookies, Deno, and `web_safari`.
- Produce a manifest with downloaded, existing, and failed videos.
- If download yield is below 100, expand the candidate input beyond the first 100
  videos and retry failed/incomplete items.

Success criteria:

- Around 100 local videos are available in `stage4_self_evolve/outputs/video_cache/`.
- Download failures are explicitly recorded.

Current run:

- Selected 120 unique video candidates from `stage4_self_evolve/outputs/v0_150_candidates.jsonl`.
- Candidate file: `stage4_self_evolve/outputs/v1_100_video_pool_candidates.jsonl`.
- Main download manifest: `stage4_self_evolve/outputs/v1_100_video_pool_download_manifest.jsonl`.
- Parallel shard manifests: `stage4_self_evolve/outputs/v1_100_video_pool_download_manifest_part*.jsonl`.
- Annotated local-video pool: `stage4_self_evolve/outputs/v1_100_video_pool_local.jsonl`.
- These are local runtime artifacts and are intentionally not pushed to GitHub.
- Added `stage4_self_evolve/merge_video_manifests.py` to merge shard manifests,
  deduplicate by video id, and produce the final annotated local-video pool.
- Added `stage4_self_evolve/prepare_video_pool.py` to turn stage0 fresh-video
  JSON exports into download candidate JSONL while excluding already attempted ids.
- Started an extra 200-candidate stage0 fresh-video pool because the first 120
  candidates may not yield 100 usable downloads.

### Step 3: Harness Evidence Packs

Status: in progress.

Actions:

- Added `stage4_self_evolve/build_video_evidence.py`.
- The script converts local video rows into versioned harness evidence packs.
- It records ffprobe metadata for every local video.
- It can call VideoAgentDataFlow through `--run-dataflow` to add caption,
  OCR/YOLO/ASR/tracking-derived evidence summaries.
- It writes local runtime outputs only; generated evidence JSONL is ignored by git.

Success criteria:

- Each processed video has a versioned evidence pack.
- Evidence is structured enough to support GT and distractor verification.

Current smoke test:

- Ran metadata-only evidence generation on the first two available local videos from
  the 100-video pool manifest.
- Output: `stage4_self_evolve/outputs/v1_harness_evidence_smoke.jsonl`.
- Status: 2/2 metadata-only evidence rows written.

### Step 4: Harness-First Question Generation

Status: in progress.

Actions:

- Added `stage4_self_evolve/generate_from_harness.py`.
- The generator consumes harness evidence, not Stage2 question text.
- It can also run with `--include-local-video`, uploading the local video to
  Gemini so the generator sees both the video and harness evidence.
- It has `--allow-metadata-only` for smoke tests; production generation should
  prefer full harness evidence.
- Prompt constraints require aligned video skills, verifiable GT, non-brittle
  question design, plausible same-type distractors, and explicit verification plans.
- The output schema is compatible with the existing MCQ validation/eval scripts.

Success criteria:

- Items are evidence-grounded from the start.
- One video can yield multiple nontrivial aligned items.

### Step 5: Verification and Filtering

Status: pending.

Actions:

- Verify GT support with evidence.
- Verify distractors are plausible but wrong.
- Reject brittle, trivial, ambiguous, or non-aligned items.

Success criteria:

- Final items have explicit GT and distractor verification records.

### Step 6: Multi-Model Validation

Status: in progress.

Actions:

- Evaluate the same generated benchmark on Gemini 2.5, Gemini 3.0/3.1, Gemini 3.5,
  and other available model APIs.
- Report per-model accuracy and model separation.

Success criteria:

- The benchmark demonstrates discrimination across model versions.
- Easy/no-signal items are flagged for evolution.

Current smoke test:

- Generated 2 MCQ items from 1 local video with Gemini local-video upload mode.
- Ran `eval_local_video_mcq.py` on those 2 items with the same Gemini model.
- Result: 2/2 correct. This validates the mechanics but is not a discrimination
  result; it should be treated as a smoke test only.

### Step 7: Evolution Loop

Status: pending.

Actions:

- Use validation results to propose better harness usage, question types, evidence
  spans, and distractor rules.
- Regenerate and revalidate.
- Compare difficulty and validity across generations.

Success criteria:

- Stronger generator/harness/seed configurations produce harder but still valid items.

## Step Log

- 2026-05-27: Created execution roadmap and set target scale to roughly 100 local videos.
- 2026-05-27: Pushed a clean code/documentation skeleton to GitHub without data artifacts.
- 2026-05-27: Started 120-candidate download run to build an approximately 100-video local pool.
- 2026-05-27: Added harness evidence and harness-first MCQ generation scripts; smoke-tested metadata-only evidence on two local videos.
- 2026-05-27: Added parallel download shard support through manifest merge tooling.
- 2026-05-27: Added local-video upload mode for harness-first Gemini generation.
- 2026-05-27: Smoke-tested harness-first generation and local-video evaluation on 1 video / 2 items.
- 2026-05-27: Expanded video acquisition with a 200-candidate stage0 fresh-video pool.
