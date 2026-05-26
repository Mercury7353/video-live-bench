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

Status: completed.

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
- Added `stage4_self_evolve/build_valid_video_pool.py` to ffprobe-filter cached
  downloads and emit the final valid local-video pool.
- Started an extra 200-candidate stage0 fresh-video pool because the first 120
  candidates may not yield 100 usable downloads.
- Started an additional 300-candidate `fusion_all_vides` short-video fast lane
  at 240p/low retry to reach the 100-video target faster.
- Current valid pool: 106 ffprobe-valid local videos.
- Valid pool file: `stage4_self_evolve/outputs/v1_valid_video_pool_partial.jsonl`.

### Step 3: Harness Evidence Packs

Status: completed for V1 pilot.

Actions:

- Added `stage4_self_evolve/build_video_evidence.py`.
- Added `stage4_self_evolve/build_gemini_video_evidence.py`.
- The script converts local video rows into versioned harness evidence packs.
- It records ffprobe metadata for every local video.
- It can call VideoAgentDataFlow through `--run-dataflow` to add caption,
  OCR/YOLO/ASR/tracking-derived evidence summaries.
- Because local OCR/YOLO/ASR dependencies are not installed in this environment,
  the current executable harness path uses Gemini video inspection to produce
  structured timeline/OCR/audio/object/question-opportunity evidence.
- It writes local runtime outputs only; generated evidence JSONL is ignored by git.

Success criteria:

- Each processed video has a versioned evidence pack.
- Evidence is structured enough to support GT and distractor verification.

V1 pilot result:

- Ran Gemini video evidence harness on 75 selected local videos.
- Evidence success: 74/75.
- One failure was malformed Gemini JSON and is retryable.

Current smoke test:

- Ran metadata-only evidence generation on the first two available local videos from
  the 100-video pool manifest.
- Output: `stage4_self_evolve/outputs/v1_harness_evidence_smoke.jsonl`.
- Status: 2/2 metadata-only evidence rows written.

### Step 4: Harness-First Question Generation

Status: completed for V1 pilot.

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

V1 pilot result:

- Generated 184 MCQ candidates from 74 evidence packs.
- Exported a fixed 150-item pilot set.
- The 150-item set covers 61 videos.
- Task mix: OCR 55, Reasoning 41, Perception 27, Temporal 22,
  Counting 4, Tracking 1.

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

V1 pilot validation:

- Options-only leakage probe with `gemini-3.5-flash`: 149/150 parsed,
  accuracy 65.1%.
- Local-video sample30 with `gemini-3.5-flash`: 29/30 parsed,
  parsed accuracy 100%.
- Local-video sample30 with `gemini-2.5-flash-lite`: 30/30 parsed,
  accuracy 96.7%.
- YouTube-link direct eval with `gemini-3.5-flash`: 147/150 parsed across
  three shards.
- Strict hard-gate filtering with `stage4_self_evolve/strict_filter_candidates.py`:
  2 accepted, 148 rejected.
- Main rejection reasons: direct model correct on 145 items, options-only correct
  on 97 items, missing direct eval on 3 items, one date-style brittle question.
- `gemini-2.0-flash` is listed by the API but this key receives a 404
  "no longer available to new users" response.
- OpenAI/GPT validation did not run because `OPENAI_API_KEY` is not configured
  in this environment.

Interpretation:

- The pipeline is mechanically working end to end.
- The first generated set is too easy for current Gemini video models.
- The options-only score is too high, so distractor and question leakage filters
  must be strengthened before treating this as a benchmark release.

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
- 2026-05-27: Added a 300-candidate short-video fast lane from `fusion_all_vides`.
- 2026-05-27: Added ffprobe-based valid-video-pool export tooling.
- 2026-05-27: Completed the first 100-video local pool with 106 ffprobe-valid videos.
- 2026-05-27: Completed V1 pilot generation: 74 evidence packs, 184 candidates,
  and a fixed 150-item candidate set.
- 2026-05-27: Ran first validation probes; results show weak model separation and
  high options-only leakage, motivating the next evolution round.
- 2026-05-27: Converted options-only and YouTube direct eval into strict hard
  gates; only 2/150 V1 candidates survived.
