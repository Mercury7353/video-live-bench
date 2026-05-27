# LiveBench Execution Roadmap - 2026-05-27

## Target

Build the first harness-first pilot at roughly 100 local videos, then generate and
validate benchmark questions from harness evidence rather than from Stage2 bootstrap
question text.

Correction after V1:

- V1 did not use real benchmark QA seeds; it only used prompt taxonomy plus harness
  evidence. That was insufficient and produced many easy or leaky items.
- V2 generation must use existing benchmark questions, starting with Video-MME, as
  a seed bank for capability style and evaluation logic.
- The production generation contract is now: benchmark seed examples + current
  video input + harness evidence + strongest available generator model.

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

Status: completed for V1 pilot; revised for V2 seed-bank generation.

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
- Added `stage4_self_evolve/prepare_benchmark_seeds.py` to normalize existing
  benchmark annotations into a seed bank.
- The local `stage1_gen_q/original_benchmarks/Video-MME.tsv` file now converts
  into 2700 Video-MME seed examples.
- The broader local/configured registry currently normalizes 25,860 seed
  examples from Video-MME, LongVideoBench, MLVU, LSDBench, Video-Holmes,
  LVBench, VSI-Bench, CG-AV-Counting, MME-VideoOCR, Video-MMMU, MMVU, and
  Charades-STA.
- Each seed keeps its original benchmark subtype as `source_task_type` /
  `sub_category` and is mapped into a common `capability` plus
  `capability_tags` taxonomy.
- `generate_from_harness.py` now accepts `--seed-examples` and
  `--require-seed-examples`, records `benchmark_seed_ids`, and marks generated
  rows as `benchmark_seed_plus_harness_evidence`.
- Seed examples are stratified by `source_benchmark,capability` by default; the
  field can be changed to other subtype combinations such as
  `source_benchmark,source_task_type`, `sub_category`, or `capability`.
- Production V2 runs should use `--include-local-video` so the generator sees the
  original video along with the harness evidence and benchmark seed examples.
- The V2 MCQ pipeline is now split into three stages:
  `generate_gt_from_harness.py` creates only question + verified GT,
  `generate_distractors.py` creates only wrong options, and
  `fuse_mcq_options.py` deterministically shuffles GT + distractors into A-D.
  This removes the one-shot MCQ bias where the model often placed the correct
  answer in option A.

Success criteria:

- Items are evidence-grounded from the start.
- One video can yield multiple nontrivial aligned items.

V1 pilot result:

- Generated 184 MCQ candidates from 74 evidence packs.
- Exported a fixed 150-item pilot set.
- The 150-item set covers 61 videos.
- Task mix: OCR 55, Reasoning 41, Perception 27, Temporal 22,
  Counting 4, Tracking 1.

V2 seed-bank smoke:

- Built `stage4_self_evolve/outputs/benchmark_seed_bank_videomme.jsonl` locally
  from Video-MME; this output is not pushed.
- Ran a 1-video smoke with Video-MME seeds, Gemini video upload, and harness
  evidence.
- Result: 1 item generated with `benchmark_seed_sources=["Video-MME"]` and five
  recorded Video-MME seed ids.
- The smoke item was still somewhat OCR/counting-detail-like, so seed-bank
  generation is necessary but not sufficient; strict filtering and rewrite loops
  remain mandatory before export.

V2 three-stage pilot:

- One-shot MCQ generation was abandoned because it produced strong correct-label
  bias and weak distractor control.
- Three-stage generation fixed option fusion mechanically: GT is generated first,
  distractors are generated separately with complete benchmark seed MCQ examples,
  and labels are assigned only by code.
- A 30-video attack pilot produced 25 GT candidates after rejecting 16 single-cue
  questions and 1 brittle question.
- GT-stage bare Gemini direct probing found 3/25 direct-failure candidates.
- After distractor generation, MCQ fusion, options-only probing, and YouTube
  direct-video evaluation, 1/3 direct-failure candidates survived the strict gate.
- The accepted pilot item asks how many times a dancing-club-crowd background
  visual sequence fully loops; options-only guessed wrong and bare Gemini video
  also answered incorrectly.

V2 60-video attack pilot:

- Generated 47 GT candidates from 60 videos after rejecting 32 single-cue
  questions and 1 brittle question.
- GT-stage direct probing showed clear difficulty tiers:
  `gemini-2.5-flash-lite` failed 21/47, while `gemini-3.5-flash` failed 3/47.
- This supports a tiered benchmark design rather than a single hard-only set:
  calibration items, mid-tier model-separating items, and frontier-hard
  harness-gap items.
- The 21 `gemini-2.5-flash-lite` hard GT cases were converted into MCQs.
  Options-only Gemini still answered 17/21 correctly, showing that distractor
  generation remains the main bottleneck.
- Among the 4 options-only-hard MCQs, YouTube direct-video Gemini 3.5 failed 1.
  The strict accepted item asks which hand a comedian consistently uses to hold
  his microphone throughout a stand-up performance.
- Adversarial distractor mining was then added: wrong open-ended model answers
  from GT-stage direct probes are fed into distractor generation, equivalent
  paraphrases of the GT are discarded, and the remaining candidates are rewritten
  into a unified option style.
- On the 3 Gemini-3.5 frontier-hard GT cases from the 60-video pilot, adversarial
  distractors improved strict MCQ acceptance from 0/3 to 2/3. The accepted items
  used actual model errors such as overcounting Gerald's falls as 6 instead of 5,
  and confusing the animal sequence as "chimpanzee, vulture, and baboon."

V2 74-video full local-video run:

- Reused the existing local videos and Gemini upload cache. No video redownload was
  needed for this run.
- Input: 74 Gemini evidence/video rows.
- GT-only generation wrote 53 candidates covering 44 videos. It rejected 39
  single-cue/trivial-risk candidates before MCQ construction.
- Seed examples were sampled from the multi-benchmark seed bank, with coverage from
  LSDBench, Video-MME, Video-MMMU, MLVU, LVBench, Video-Holmes, LongVideoBench,
  MMVU, CG-AV-Counting, and Charades-STA.
- Open-ended direct probing produced a clear model-separation signal:
  `gemini-2.5-flash-lite` failed 16/53, while `gemini-3.5-flash` failed 3/53.
- Cross-model tiers:
  - 14 mid-tier cases: `gemini-2.5-flash-lite` failed and `gemini-3.5-flash`
    passed.
  - 2 frontier-overlap cases: both models failed.
  - 3 Gemini-3.5 frontier-hard cases in total.
- The 3 Gemini-3.5 frontier-hard cases were converted to MCQ with adversarial
  distractors mined from real wrong answers. Strict filtering accepted 1/3; the
  two rejected cases were still answered correctly by direct-video Gemini 3.5 once
  options were shown.
- The 14 mid-tier cases were converted to MCQ with adversarial distractors mined
  from real wrong answers. In MCQ direct-video validation, Gemini 3.5 scored
  14/14, while Gemini 2.5 Flash-Lite scored 3/14 after one retry for malformed JSON
  output.
- Among those 14 mid-tier MCQs, options-only Gemini 3.5 answered 10/14 correctly.
  Requiring options-only to fail leaves 4/14 leak-free discriminative mid-tier
  items where Gemini 3.5 is correct and Gemini 2.5 Flash-Lite is wrong.
- Interpretation: the harness-first GT generation and model-tiering logic now
  works at small scale. The remaining bottleneck is still distractor leakage:
  many valid open-ended hard cases become easy when options are visible.

### Step 5: Verification and Filtering

Status: in progress.

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
- V1 should be treated as a failed difficulty pilot, not a benchmark release.
- V2 three-stage generation solves the option-label/fusion problem but still has
  low hard-case yield. The next scaling run should do GT-stage direct filtering
  before spending calls on distractors.
- The current main bottleneck is no longer GT generation; it is adversarial
  distractor generation. Many GT-hard items become easy once choices are shown.
- Early adversarial distractor mining confirms that direct-model wrong answers
  are much stronger distractors than free-form generated wrong options.
- The 74-video full run confirms the same pattern at a larger local-video scale:
  adversarial distractors produce usable MCQs, but options-only leakage remains
  the main reason candidates are rejected.

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
- 2026-05-27: Added Video-MME seed-bank preparation and wired benchmark seeds into
  harness-first Gemini video generation.
- 2026-05-27: Added stratified seed sampling so Video-MME subtypes do not get
  sampled according to raw row frequency.
- 2026-05-27: Expanded seed-bank support to the configured multi-benchmark
  registry and local specialized datasets including LSDBench, LVBench,
  Video-Holmes, VSI-Bench, CG-AV-Counting, and MME-VideoOCR.
- 2026-05-27: Replaced one-shot MCQ generation with a three-stage GT,
  distractor, and fusion pipeline; ran a 30-video attack pilot and obtained
  1 strict accepted item after GT-stage direct filtering.
- 2026-05-27: Ran a 60-video attack pilot. GT-stage direct probes produced
  21 mid-tier failures for Gemini 2.5 Flash-Lite and 3 frontier-hard failures
  for Gemini 3.5 Flash; strict MCQ filtering accepted 1 additional item.
- 2026-05-27: Added wrong-answer-pool distractor generation and verified on the
  60-video frontier-hard cases that strict MCQ acceptance improved to 2/3.
- 2026-05-27: Ran the 74-video full local-video generation/validation cycle.
  It produced 53 GT candidates, 16 Gemini-2.5-lite open-ended failures, 3
  Gemini-3.5 open-ended failures, 1 strict frontier-hard MCQ, and 4 leak-free
  discriminative mid-tier MCQs.
