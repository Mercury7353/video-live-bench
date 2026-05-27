# Evolution Validation Report: 2026-05-28

This report records the first non-debug validation run for the live video benchmark
flywheel. The key change from earlier smoke tests is that model validation is run on
the full 49-question candidate set, not the 15-question reviewed subset.

## Current Pipeline Snapshot

The current runnable pipeline is:

1. Start from 106 downloaded/local YouTube videos with Gemini video harness evidence.
2. Sample complete seed MCQs from the multi-benchmark seed bank.
3. Use a teacher model plus harness evidence to produce open-ended GT QA.
4. Reject single-cue / trivial questions before distractor generation.
5. Probe direct video models open-ended and keep cases where bare models fail.
6. Generate distractors from wrong direct answers plus seed MCQ style examples.
7. Fuse and shuffle options in code.
8. Validate final MCQs by options-only leakage checks and direct-video model eval.

The all-49 MCQ set used here is:

- `stage4_self_evolve/outputs/v2_three_stage_mcq_evo03_full106_all49.jsonl`
- 49 questions from 106-video evidence.
- Generator: `gemini-3.5-flash`.
- Generation source: benchmark seeds + video + harness evidence.
- Open-ended hard-filter source:
  - 33 items where `gemini-2.5-flash-lite` failed.
  - 16 items where `gemini-3.5-flash` failed.
- Task mix:
  - Temporal: 19
  - AudioVisual: 10
  - Reasoning: 9
  - Counting: 7
  - Spatial: 3
  - LongContext: 1

## Experiment A: Full 49-Question Model Validation

Protocol:

- Input: final MCQs with video URLs.
- Eval mode: direct-video multiple choice.
- Temperature: 0.
- Metric: exact option-label accuracy.
- Timeout retries were used until all model files had 49/49 results.

| Model | Correct / Total | Accuracy |
| --- | ---: | ---: |
| `gemini-2.5-flash-lite` | 23 / 49 | 46.9% |
| `gemini-2.5-flash` | 39 / 49 | 79.6% |
| `gemini-3-flash-preview` | 39 / 49 | 79.6% |
| `gemini-2.5-pro` | 41 / 49 | 83.7% |
| `gemini-3.5-flash` | 41 / 49 | 83.7% |
| `gemini-3.1-pro-preview` | 42 / 49 | 85.7% |

Interpretation:

- The set clearly separates `gemini-2.5-flash-lite` from the stronger models.
- It does not yet separate the stronger Gemini family well: `2.5-flash`,
  `3-flash-preview`, `2.5-pro`, `3.5-flash`, and `3.1-pro-preview` are clustered
  within 6.1 accuracy points.
- This means the current all-49 set is useful for detecting weaker direct-video
  models, but not yet a strong SOTA discriminator.

Immediate implication:

- The next evolution loop should optimize specifically for SOTA separation, not
  just for "any direct model fails".
- The acceptance gate should require at least one strong model failure and should
  keep calibration/easy items in a separate split.

## Experiment B: Evidence That the Flywheel Made the Set Harder

Existing run history:

| Run | Videos | GT Candidates | `gemini-3.5-flash` Open-Ended Hard | `gemini-2.5-flash-lite` Open-Ended Hard |
| --- | ---: | ---: | ---: | ---: |
| Original full74 | 44 | 53 | 3 / 53 | 16 / 53 |
| evo03 full74 | 44 | 53 | 13 / 52 | 33 / 50 |
| evo03 full106 | 106 | 82 | 17 / 82 | 48 / 81 |

Interpretation:

- The feedback strategy increased the open-ended hard yield substantially compared
  with the original full74 pass.
- Scaling to 106 videos increased candidate volume and produced 49 final MCQs for
  full-model validation.
- However, MCQ conversion and options-only leakage still soften difficulty; the
  all-49 final MCQ set is less discriminative among strong models than the
  open-ended hard-yield numbers suggest.

## Experiment C: Teacher Model Pilot

Goal:

- Test whether stronger teacher models automatically generate harder benchmark
  candidates under the same harness and seed conditions.

Protocol:

- Same first 30 evidence videos.
- Same multi-benchmark seed bank.
- Same evo03 strategy file.
- One GT item per video.
- Teacher variants:
  - `gemini-2.5-flash`
  - `gemini-3.5-flash`
- Direct-video probes:
  - `gemini-3.5-flash`
  - `gemini-2.5-flash-lite`
- Judge: `gemini-3.5-flash`, semantic match against harness GT.

| Teacher | GT Kept / 30 | Direct Model | Judged | Hard Cases | Hard Yield |
| --- | ---: | --- | ---: | ---: | ---: |
| `gemini-2.5-flash` | 30 / 30 | `gemini-3.5-flash` | 30 | 9 | 30.0% |
| `gemini-2.5-flash` | 30 / 30 | `gemini-2.5-flash-lite` | 29 | 17 | 58.6% |
| `gemini-3.5-flash` | 28 / 30 | `gemini-3.5-flash` | 28 | 4 | 14.3% |
| `gemini-3.5-flash` | 28 / 30 | `gemini-2.5-flash-lite` | 27 | 13 | 48.1% |

Interpretation:

- This pilot does not support the simple claim "stronger teacher always generates
  harder items".
- In this sample, `gemini-2.5-flash` generated more hard cases against both direct
  models.
- The likely explanation is not that 2.5 is a better teacher. More likely, the
  current prompt/gate lets a weaker teacher produce noisier or more brittle GT,
  which can look hard before deeper review.
- Therefore, teacher-evolution experiments must report both hard yield and quality
  yield:
  - GT verification rate.
  - Nontriviality rate.
  - MCQ semantic-review keep rate.
  - Options-only leakage rate.
  - Strong-model direct-video failure rate.

Next teacher-axis test:

- Run the same teacher comparison through full distractor generation, options-only
  probe, MCQ review, and all-model MCQ eval.
- Treat open-ended hard yield as a diagnostic, not the final metric.

## Experiment D: Seed Evolution Status

Current multi-benchmark seed bank:

- Total: 25,860 seed examples.
- Source benchmarks:
  - VSI-Bench: 5,130
  - Charades-STA: 3,720
  - Video-MME: 2,700
  - LSDBench: 2,486
  - MLVU: 2,174
  - MME-VideoOCR: 2,000
  - Video-Holmes: 1,837
  - LVBench: 1,549
  - LongVideoBench: 1,337
  - CG-AV-Counting: 1,027
  - MMVU: 1,000
  - Video-MMMU: 900

Video-MME v1 seed bank:

- Total: 2,700.
- Capability mix:
  - Action: 551
  - Perception: 503
  - Reasoning: 402
  - Counting: 317
  - Temporal: 307
  - GeneralVideoQA: 262
  - OCR: 176
  - Spatial: 150
  - DomainKnowledge: 31
  - AudioVisual: 1

Video-MME v2 status:

- Schema support exists as `video_mme_v2` in
  `stage4_self_evolve/prepare_benchmark_seeds.py`.
- The Hugging Face dataset file is expected at:
  `https://huggingface.co/datasets/MME-Benchmarks/Video-MME-v2/resolve/main/test.parquet`
- I added a `pyarrow` parquet fallback because local pandas import is broken due
  to a missing numpy dependency.
- Local shell download failed with `Network is unreachable`, and no local
  Video-MME-v2 source file was found under the searched AFS paths.

Seed-axis conclusion:

- Video-MME v1 vs v2 generation/eval is not completed yet because v2 source data is
  not locally accessible.
- The code path is ready once the v2 parquet/jsonl file is present.

## Current Problems

The main quality bottlenecks are:

- Strong-model clustering: 2.5-flash through 3.1-pro are too close on all49.
- Options-only leakage remains high in earlier gates:
  - Mid cases: 21/33 options-only correct by `gemini-3.5-flash`.
  - Frontier cases: 10/15 options-only correct before retry.
- Teacher hard yield can be confounded by noisy GT.
- The all49 set mixes strict-hard, mid-tier discriminative, and calibration items.
  The paper needs these split labels preserved.

## Next Roadmap

1. Build a stricter SOTA-hard acceptance split.
   - Require options-only wrong or low confidence.
   - Require at least one strong direct-video model wrong.
   - Require semantic MCQ review keep.

2. Run full MCQ pipeline for teacher comparison.
   - Teacher: `gemini-2.5-flash` vs `gemini-3.5-flash`.
   - Same videos, same seeds, same strategy.
   - Measure final accepted MCQ hard yield, not only open-ended GT hard yield.

3. Complete seed evolution experiment.
   - Video-MME v1 seeds vs Video-MME v2 seeds.
   - Multi-benchmark mixed seeds vs single-benchmark seeds.
   - Stratify results by capability and benchmark source.

4. Add stronger distractor gates.
   - Mine wrong open-ended direct answers.
   - Include repeated-sample uncertainty distractors.
   - Rewrite all options into a uniform style.
   - Reject equivalent/paraphrase distractors before fusion.

5. Add external model validation once keys are available.
   - GPT direct-video eval requires an OpenAI key and video-capable eval path.
   - Claude eval requires an Anthropic key and video/file input path.

