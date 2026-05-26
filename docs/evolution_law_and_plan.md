# Evolution Law and Pipeline Plan

## Core Motivation

The central hypothesis is:

```text
harness + model > bare model
```

As foundation models improve, they gradually absorb abilities that previously required
external harnesses, tools, scaffolding, and agentic workflows. Therefore, a benchmark that
is useful over time must evolve with:

- new videos,
- new task types and evaluation methods,
- new harnesses and skills.

The benchmark should expose the gap between:

```text
agentic/harness-assisted understanding
vs.
direct bare-model video QA
```

This gap is the target signal. A valid hard item should be answerable and verifiable with
the harness, but difficult or unstable for the bare SOTA model.

## Canonical Roadmap

This is the controlling plan for the project. Validation-only experiments must not be
confused with the benchmark generation pipeline.

### Step 1: Build One Complete Generation + Validation Cycle

The benchmark item generation pipeline is:

```text
download fresh/local video
-> run harness skills over the video
-> strongest available Gemini uses harness evidence to design questions
-> strongest available Gemini writes GT and reasoning grounded in harness evidence
-> generate MCQ distractors
-> verify GT and distractors with harness/model checks
-> validate the resulting benchmark on multiple bare models
```

Important constraints:

- One video can and should generate multiple benchmark questions when it supports
  multiple nontrivial align-relevant skills.
- Questions must be designed from harness-visible evidence, not merely converted from
  existing Stage2 text.
- GT must be basically correct or independently verifiable.
- Distractors must be plausible but wrong, with explicit rejection evidence.
- The validation set should be run across model families/versions to test whether the
  benchmark has discrimination power.

Step 1 output is not just model accuracy. It is a complete artifact containing:

- local video path or stable video reference,
- harness evidence pack,
- generated question,
- GT,
- MCQ options,
- distractor provenance and rejection reasons,
- validation results across several models.

### Step 2: Evolve When the Benchmark Has Weak Discrimination

If validation shows that items are too easy, too brittle, or fail to separate models,
the pipeline must support evolution through proposal and experiment:

```text
analyze eval results
-> identify no-signal/easy/trivial/wrong-GT failure modes
-> propose new harness usage patterns, question styles, evidence spans, or distractor rules
-> regenerate or revise items
-> rerun validation
-> keep the generation strategy that improves discrimination while preserving GT quality
```

The goal is not to make arbitrary harder questions. The goal is to discover better ways
to use harness capabilities to generate questions that remain aligned, nontrivial, and
verifiable while exposing bare-model weaknesses.

### Step 3: Prove Pipeline Evolution Is General

The paper-level claim requires controlled evolution experiments:

- **Teacher/model evolution:** generating with a stronger model should produce harder
  but still valid benchmarks.
  - Example: Gemini 2.5-generated benchmark vs Gemini 3.5-generated benchmark.
- **Seed benchmark evolution:** using newer or richer seed distributions should produce
  harder and/or broader benchmarks.
  - Example: Video-MME v1-style seeds vs Video-MME v2-style seeds.
- **Harness evolution:** adding stronger skills should unlock new question families that
  bare models cannot yet solve reliably.
  - Example: frame sampling + OCR + detection/tracking + ASR vs prompt-only video QA.

Success means the pipeline demonstrates an evolution law:

```text
stronger generator/harness/seed -> harder validated benchmark
while GT verification remains high
```

### What Current V0 Is and Is Not

Current V0 is a bootstrap diagnostic run:

- It reused Stage2 question/GT/reasoning as the source.
- It generated MCQs and reviewed them.
- It downloaded 21 usable videos for the accepted subset.
- It started bare-model local-video validation.

Current V0 is **not** the final intended pipeline because it does not yet use the
harness as the primary question/GT generator. It is useful only for debugging download,
MCQ formatting, upload, and validation infrastructure.

## Three Evolution Dimensions

### 1. New Video Evolution

Continuously crawl fresh YouTube videos and rebalance the video pool.

Current implementation:

- `stage0_get_videoid/s0_collect_videos`: YouTube search by target categories.
- `stage0_get_videoid/s1_fifter_videos`: duration/category balancing.
- Existing artifacts:
  - 18,040 raw fused video candidates.
  - 11,486 duration-filtered videos.
  - 795 balanced new videos.

Future direction:

- Refresh crawl windows, e.g. month-by-month or version-by-version.
- Track versioned video pools: `video_pool_v1`, `video_pool_v2`, etc.
- Compare benchmark versions by video novelty and model performance shift.

### 2. New Benchmark / Task Evolution

Introduce new question types and evaluation styles rather than only regenerating similar
questions.

Current implementation:

- `stage1_gen_q/question_pool`: extracts examples from existing benchmarks.
- Five current categories:
  - Counting
  - OCR
  - Perception
  - Reasoning
  - Spatial
- Existing generated question counts:
  - Counting: 799
  - OCR: 957
  - Perception: 847
  - Reasoning: 944
  - Spatial: 768

Future direction:

- Run a monthly related-work monitor with web search over new video/multimodal
  benchmark papers, datasets, leaderboards, and arXiv releases.
- Ingest high-quality new benchmarks as seed sources, not as final benchmark items.
  The pipeline should extract task schemas, evaluation formats, evidence requirements,
  and failure modes, then generate fresh video-grounded items from current video pools.
- Add new task templates when new benchmarks appear.
- Add new evaluation formats:
  - free-form QA,
  - MCQ,
  - evidence-span grounding,
  - option-level verification,
  - model-failure-mode labels.
- Make each task type define:
  - valid question transformations,
  - acceptable evidence,
  - allowed distractor patterns,
  - ambiguity rejection rules.

### 3. New Harness / Skill Evolution

Use stronger harnesses to help SOTA models understand videos in an agentic way.

Current implementation:

- `stage2_fifter_q/anno_qa_ref.py`: Gemini video annotator generates:
  - reference answer,
  - question span,
  - answer span,
  - reasoning,
  - answerability metadata.
- `stage4_self_evolve`: direct bare-model probing and hard-case selection.
- Current harness is mostly prompt-scaffolded Gemini, not yet a full external-tool harness.

Useful external tools identified:

- `/mnt/afs/luhao2/workspace/VideoAgentDataFlow`
  - `VideoIOManager`: inspect, frame extraction, segment clip export.
  - `PaddleOCRTool`: OCR evidence with bbox and confidence.
  - `UltralyticsYOLOTool`: detection and tracking.
  - `WhisperASRTool`: ASR.
  - FastAPI tool server with `/ocr/extract`, `/yolo/detect_frames`, `/yolo/track`.

Future direction:

- Maintain a skill discovery loop that periodically searches GitHub, Clawhub, and
  similar tool/agent hubs for high-quality video-understanding skills.
- Candidate skills should be screened for relevance, activity, quality, license,
  reproducibility, cost, and whether they produce structured evidence that can verify
  GT or reject distractors.
- Accepted skills should enter a versioned skill registry with declared inputs,
  outputs, task coverage, verification rules, latency/cost, and known failure modes.
- Build a tool-assisted evidence harness:
  - extract frames from answer spans,
  - run OCR/YOLO/ASR,
  - verify GT,
  - verify distractors are wrong,
  - reject ambiguous or brittle items.

### 4. LiveBench Maintenance Agent

The long-term system should have a scheduled agent entry point, for example a Codex
maintenance agent, that runs monthly or quarterly.

Routine maintenance tasks:

- crawl and download fresh YouTube videos,
- deduplicate and version video pools,
- monitor new benchmark papers/datasets/leaderboards through web search,
- search GitHub/Clawhub-style sources for new video-understanding skills,
- run skill smoke tests and update the skill registry,
- regenerate benchmark candidates with the latest generator model and harness,
- run validation across model versions,
- publish a versioned report and commit/release artifacts.

Release cadence:

- monthly lightweight refresh for new videos, new papers, and small skill updates,
- quarterly larger release with new benchmark seeds, new harness versions, and full
  multi-model validation.

## Evolving Data Pipeline

Given:

- new videos,
- new example questions or task templates,
- current strongest harness/model,

the pipeline should:

1. Generate candidate questions aligned with the target task type.
2. Build harness evidence:
   - video spans,
   - OCR,
   - detections/tracks,
   - captions,
   - possibly ASR.
3. Generate GT using the harness.
4. Verify GT using positive checks.
5. Generate distractors through multi-model discussion.
6. Verify distractors using negative checks.
7. Probe bare models directly.
8. Keep items where:
   - GT is verified,
   - category is aligned,
   - distractors are plausible but wrong,
   - the question is not brittle/trivial,
   - bare SOTA fails or is unstable.
9. Use a meta-thinker to inspect bad cases and refine:
   - reject wrong-GT cases,
   - reject brittle detail questions,
   - improve distractors,
   - improve task templates and harness tools.

## Meta-Thinker Loop

The benchmark should not be one-pass generated. It should iterate.

Inputs:

- model evaluation results,
- examples many models got wrong,
- examples many models got right,
- examples flagged as ambiguous,
- human or tool verifier feedback.

Actions:

- Check whether the GT is wrong.
- Check whether the question is overly brittle or detail-punishing.
- Check whether multiple MCQ options are acceptable.
- Check whether the item is too easy or too template-like.
- Rewrite question/options or discard the item.
- Update generation prompts and verification rules.

Target output:

- a fine-grained evaluation set with:
  - task category,
  - evidence,
  - verified GT,
  - verified distractors,
  - failure mode,
  - model-version difficulty metadata.

## Existing Infrastructure

### Stage 0: Video Pool

Status: usable.

Capabilities:

- YouTube crawling by category keywords.
- Duration filtering.
- Category balancing.

Limitations:

- API keys are hardcoded in old scripts.
- Fresh crawl versioning is not formalized.

### Stage 1: Question Generation

Status: usable for initial candidate generation.

Capabilities:

- Builds task question pools from existing benchmarks.
- Uses Gemini to imitate question styles for new YouTube videos.

Limitations:

- Mostly style imitation.
- Does not yet enforce evidence-first generation.
- No explicit novelty score for new task types.

### Stage 2: GT Annotation

Status: usable but weak as a verifier.

Capabilities:

- Gemini video input generates reference answer, spans, reasoning, answerability.
- Produces `anno_qa_ref_fusion_by_question.csv`.

Limitations:

- Harness is prompt-scaffolded Gemini only.
- No independent OCR/YOLO/frame verification.
- Some GTs may be questionable.

### Stage 3: MCQ

Status: incomplete.

Capabilities:

- Some temp xlsx outputs exist.

Limitations:

- `stage3_gen_mcq/temp/gen_mcq.py` has an empty prompt and is not a real MCQ pipeline.
- Distractor generation and verification are not implemented.

### Stage 4: Self-Evolve Bootstrap

Status: small working prototype.

Capabilities:

- Converts Stage2 QA into candidate pool.
- Directly probes Gemini without evidence.
- Judges direct answer against harness GT.
- Produces hard cases.

Current result:

- 839 candidate rows from 1,087 Stage2 QA rows.
- 11 direct probes.
- 4 hard cases.
- Failure modes found:
  - `ocr_miss`
  - `wrong_count`
  - `spatial_relation_error`
  - `other`

Limitations:

- Uses Stage2 as GT source.
- Judge is still Gemini.
- No tool-assisted GT/distractor verification yet.

## Implementation Plan

### Phase 1: Formalize Evidence Harness

Deliverables:

- `stage4_self_evolve/tool_adapters/video_agent_dataflow.py`
- Local/HTTP adapter for:
  - frame extraction,
  - OCR,
  - YOLO detection,
  - YOLO tracking.
- `verify_gt.py`:
  - positive verification for OCR/counting/spatial items.
- `evidence_pack.jsonl` schema.

Success criteria:

- For each candidate, store evidence spans and tool outputs.
- At least OCR and spatial examples can be verified without relying only on Gemini.

### Phase 2: Real MCQ Pipeline

Deliverables:

- `stage3_gen_mcq/generate_mcq.py`
- `stage3_gen_mcq/verify_options.py`
- `stage3_gen_mcq/multi_model_distractors.py`

MCQ constraints:

- one uniquely correct option,
- three plausible but wrong distractors,
- every distractor has a rejection reason,
- no brittle detail-only options,
- task distractor policy.

Success criteria:

- MCQ items include:
  - `correct_option_verified = true`
  - `distractors_verified_wrong = true`
  - `ambiguity_flags = []`

### Phase 3: Meta-Thinker Iteration

Deliverables:

- `stage5_meta_thinker/analyze_bad_cases.py`
- `stage5_meta_thinker/rewrite_or_reject.py`
- versioned audit reports.

Meta-thinker decisions:

- accept,
- reject_wrong_gt,
- reject_brittle,
- reject_trivial,
- rewrite_question,
- rewrite_options,
- require_more_evidence.

Success criteria:

- Bad cases are not blindly kept.
- Every final benchmark item has an audit trail.

### Phase 4: Evolution Experiments

Deliverables:

- Benchmark versioning:
  - `vidlivebench_v1`
  - `vidlivebench_v2`
- Model-version comparisons:
  - Gemini 1.5 vs Gemini 3.x,
  - possibly GPT/Claude/Qwen if available.
- Difficulty metrics:
  - direct accuracy drop,
  - harness-direct gap,
  - hard-case retention rate,
  - distractor attraction rate,
  - GT verification pass rate.

Hypothesis to validate:

```text
As models become stronger, the pipeline can mine harder items by using stronger
harnesses and newer videos/task types.
```

Experimental shape:

```text
Video-MME v1 style seeds -> evolving pipeline -> Video-MME-like v2
Gemini 1.5 direct failures vs Gemini 3.x direct failures
Harness success rate should stay high while direct failure frontier shifts.
```

## Near-Term Priority

1. Build a harness-first generation runner over the 21 downloaded local videos:
   - sample frames/clips around candidate spans or discovered events,
   - run available OCR/detection/ASR/frame tools,
   - package evidence for Gemini 3.5 or the strongest available generator.
2. Let the generator propose multiple questions per video:
   - each proposal must include task type, evidence references, GT, and verification plan,
   - reject proposals that depend on brittle pixel-level trivia or unverifiable details.
3. Generate and verify MCQ distractors:
   - use model-generated semantic distractors,
   - use harness checks to reject distractors that may also be correct,
   - store distractor rejection evidence.
4. Run validation across model versions:
   - Gemini 2.5 Flash,
   - Gemini 2.5 Pro,
   - Gemini 3 Flash Preview,
   - Gemini 3.5 Flash,
   - plus GPT/Claude if keys become available.
5. Report benchmark quality:
   - GT verification pass rate,
   - distractor verification pass rate,
   - per-model accuracy,
   - model separation / discrimination,
   - too-easy and too-brittle rejection rates,
   - examples of harness-success vs bare-model-failure.
6. Iterate generation strategy if discrimination is weak:
   - propose new harness usage patterns,
   - regenerate items,
   - rerun validation,
   - compare difficulty and validity against the previous generation.
