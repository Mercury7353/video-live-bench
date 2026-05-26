# V0 150-Question Flywheel Experiment

Date: 2026-05-26

## Goal

Run a first small design + evaluation pass with 150 Stage2-derived candidates.
This pass is intended to test the benchmark flywheel mechanics and option
leakage, not to claim final video-model accuracy.

## Pipeline

Inputs and outputs:

- Candidates: `stage4_self_evolve/outputs/v0_150_candidates.jsonl`
- MCQ candidates: `stage4_self_evolve/outputs/v0_150_mcq_candidates.jsonl`
- MCQ reviews: `stage4_self_evolve/outputs/v0_150_mcq_reviews.jsonl`
- Accepted benchmark rows: `stage4_self_evolve/outputs/v0_150_benchmark_accepted.jsonl`
- Rejected benchmark rows: `stage4_self_evolve/outputs/v0_150_benchmark_rejected.jsonl`
- Eval results: `stage4_self_evolve/outputs/v0_150_mcq_eval_results.jsonl`
- Eval summary: `stage4_self_evolve/outputs/v0_150_mcq_eval_summary.json`

## Generation Results

From 1,087 Stage2 QA rows, sampled 150 candidates.

MCQ generation produced 59 ready rows:

| Task | Ready rows |
| --- | ---: |
| Counting | 26 |
| Spatial | 26 |
| OCR | 7 |

Gemini MCQ reviewer results:

| Decision | Rows |
| --- | ---: |
| keep | 30 |
| repair | 14 |
| drop | 15 |

Exported benchmark rows:

| Split | Rows |
| --- | ---: |
| accepted | 30 |
| rejected | 29 |

Accepted task distribution:

| Task | Rows |
| --- | ---: |
| Counting | 21 |
| OCR | 5 |
| Spatial | 4 |

## Tool Evidence Status

Tool evidence was attempted on 50 candidates.

| Evidence status | Rows |
| --- | ---: |
| skipped_missing_local_video | 43 |
| skipped_unsupported_task | 7 |

GT verifier and option verifier therefore returned `skipped` for all 50 checked
rows. This remains the main blocker for high-confidence GT/tool verification.

## Options-Only Evaluation

This measures leakage/triviality: models see only question + options, no video.
Random chance is 25%.

| Provider | Model | Mode | N | Accuracy |
| --- | --- | --- | ---: | ---: |
| vectorengine | gemini-2.5-flash | gemini_options | 29 | 55.17% |
| vectorengine | gemini-2.5-pro | gemini_options | 30 | 60.00% |
| vectorengine | gemini-3-flash-preview | gemini_options | 28 | 57.14% |

Task observations:

- OCR options-only accuracy was 100% for all completed Gemini runs, which suggests
  OCR options are still too recoverable from text form alone.
- Counting options-only accuracy was around 47-52%, above chance but not saturated.
- Spatial had only 3-4 accepted samples, so the estimate is noisy.

## GPT Status

No `OPENAI_API_KEY` or `OPENAI_BASE_URL` was set in the environment. The new
`eval_mcq.py` supports `openai_options`, but GPT-series evaluation was not run in
this pass.

## Video Evaluation Status

Attempted a 10-row Gemini video MCQ evaluation with YouTube URLs. The process did
not produce a first result after roughly 10 minutes and was stopped. Video direct
evaluation should be moved to a background/batched runner with retries, or to a
local-video frame harness once the video cache is connected.

## Interpretation

The flywheel mechanics work end to end for candidate sampling, MCQ generation,
model review, export, and options-only evaluation.

The current V0 accepted set is not yet a final benchmark:

- accepted rows are skewed toward Counting;
- OCR distractors still leak under options-only evaluation;
- GT/tool verification is skipped because local video cache is missing;
- GPT evaluation is blocked by missing OpenAI-compatible credentials;
- video direct evaluation through YouTube URLs is too slow for interactive runs.

Immediate next changes:

1. Add OCR option generation that creates harder same-format near-miss text
   without making the answer obvious from lexical plausibility.
2. Connect local video cache and VideoAgentDataFlow tool server for GT evidence.
3. Run GPT options-only after `OPENAI_API_KEY`/`OPENAI_BASE_URL` is available.
4. Move Gemini video MCQ evaluation to a resumable batch job with per-row timeout
   and retry accounting.
