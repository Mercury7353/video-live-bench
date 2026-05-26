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

Status: in progress.

Actions:

- Add GitHub remote.
- Add this execution roadmap.
- Push the initial roadmap commit.

### Step 2: Build a 100-Video Local Pool

Status: pending.

Actions:

- Select approximately 100 unique videos from the available candidate pool.
- Use the existing resumable `yt-dlp` downloader with cookies, Deno, and `web_safari`.
- Produce a manifest with downloaded, existing, and failed videos.
- If download yield is below 100, expand the candidate input beyond the first 100
  videos and retry failed/incomplete items.

Success criteria:

- Around 100 local videos are available in `stage4_self_evolve/outputs/video_cache/`.
- Download failures are explicitly recorded.

### Step 3: Harness Evidence Packs

Status: pending.

Actions:

- Build evidence packs for local videos using frame/clip extraction first.
- Add OCR, detection/tracking, and ASR when the local tools are available.
- Store structured evidence that a generator can cite.

Success criteria:

- Each processed video has a versioned evidence pack.
- Evidence is structured enough to support GT and distractor verification.

### Step 4: Harness-First Question Generation

Status: pending.

Actions:

- Use the strongest available Gemini model as generator.
- Generate multiple questions per video from harness evidence.
- Generate GT, MCQ options, distractor rationales, and verification plans.

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

Status: pending.

Actions:

- Evaluate the same generated benchmark on Gemini 2.5, Gemini 3.0/3.1, Gemini 3.5,
  and other available model APIs.
- Report per-model accuracy and model separation.

Success criteria:

- The benchmark demonstrates discrimination across model versions.
- Easy/no-signal items are flagged for evolution.

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
