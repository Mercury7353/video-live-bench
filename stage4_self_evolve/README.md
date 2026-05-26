# Stage 4: Tool-Verified Direct-Failure Mining

This stage mines harder benchmark items by separating two roles:

- **Harness Gemini**: allowed to use evidence, spans, repeated checks, and structured verification.
- **Direct Gemini**: asked the original video question without evidence or scaffolding.

An item is kept as a hard case only when it is category-aligned, nontrivial,
grounded in a verifiable reference answer, and the direct model fails or is
unstable.

## Bootstrap Pipeline

The first implementation reuses the existing Stage 2 QA file as harness-verified
input:

```bash
python stage4_self_evolve/prepare_candidates.py --limit 50
python stage4_self_evolve/direct_probe.py --limit 10 --use-legacy-vectorengine-keys
python stage4_self_evolve/judge_probes.py
python stage4_self_evolve/generate_mcq.py --ready-only
python stage4_self_evolve/review_mcq.py --heuristic-only
python stage4_self_evolve/meta_review.py
python stage4_self_evolve/export_benchmark.py
python stage4_self_evolve/summarize.py
```

## MCQ Generation

`generate_mcq.py` turns verified Stage2 candidates into four-option MCQ rows:

```bash
python stage4_self_evolve/generate_mcq.py \
  --input stage4_self_evolve/outputs/candidates.jsonl \
  --output stage4_self_evolve/outputs/mcq_candidates.jsonl \
  --ready-only
```

The current generator is deterministic and API-free. It builds distractors from
task-aware sources:

- OCR: local mutations of the visible text, preserving sign-like/display-text form.
- Counting: nearby but different counts, normalized to count-only option text.
- Spatial: relation flips such as left/right and above/below when available.
- Other task types: same-task answer bank, with generic fallbacks only for
  non-OCR/non-counting semantic tasks.

Rows are marked `mcq_ready` only when they pass conservative non-triviality checks:

- the original question is not framed around an exact frame/timestamp/minor detail;
- there is usable temporal evidence span;
- options are unique and not near string duplicates;
- semantic-task options are not one-word traps or obvious length leaks.

`review_mcq.py` adds a second-pass reviewer over generated MCQs. The default
`--heuristic-only` mode checks schema and existing quality flags. With API keys,
the same script can ask Gemini to reject option leakage, multiple-correct items,
and brittle questions:

```bash
python stage4_self_evolve/review_mcq.py \
  --input stage4_self_evolve/outputs/mcq_candidates.jsonl \
  --output stage4_self_evolve/outputs/mcq_reviews.jsonl \
  --provider vectorengine \
  --use-legacy-vectorengine-keys
```

## Meta Review

`meta_review.py` is the first meta-thinker pass over bad cases. It joins direct
probe judgements, MCQ quality metadata, GT tool-verification results, and option
tool-verification results:

```bash
python stage4_self_evolve/meta_review.py \
  --judged stage4_self_evolve/outputs/judged_cases.jsonl \
  --mcq stage4_self_evolve/outputs/mcq_candidates.jsonl \
  --mcq-reviews stage4_self_evolve/outputs/mcq_reviews.jsonl \
  --gt-verifications stage4_self_evolve/outputs/gt_verifications.jsonl \
  --option-verifications stage4_self_evolve/outputs/option_verifications.jsonl \
  --output stage4_self_evolve/outputs/meta_reviews.jsonl
```

It emits actions such as `keep_hard_case`, `repair_options`,
`repair_options_or_question`, `collect_more_evidence`, `repair_ground_truth`, and
`drop_trivial_or_rewrite_question`. This keeps the evolution loop explicit:
model failures are not automatically accepted unless the GT and MCQ form survive
the harness checks.

Export accepted/rejected benchmark rows after review:

```bash
python stage4_self_evolve/export_benchmark.py \
  --mcq-reviews stage4_self_evolve/outputs/mcq_reviews.jsonl \
  --meta-reviews stage4_self_evolve/outputs/meta_reviews.jsonl \
  --accepted-output stage4_self_evolve/outputs/benchmark_accepted.jsonl \
  --rejected-output stage4_self_evolve/outputs/benchmark_rejected.jsonl
```

Add `--require-meta-keep` when exporting only items that also pass the direct
failure/meta-review loop.

## Tool-Assisted Evidence Pipeline

The next layer adds optional external tool evidence through
`/mnt/afs/luhao2/workspace/VideoAgentDataFlow`.

Recommended mode is HTTP, so the heavy OCR/YOLO/ASR dependencies stay isolated in
the tool server environment.

Start the external tool server from the VideoAgentDataFlow repo:

```bash
cd /mnt/afs/luhao2/workspace/VideoAgentDataFlow
uvicorn video_captioner.tools.tool_api_server:app --host 127.0.0.1 --port 23001
```

Then point this repo at the server:

```bash
export VIDEO_AGENT_TOOL_API_URL=http://127.0.0.1:23001
export VIDLIVE_VIDEO_CACHE_DIR=/path/to/local/video/cache
```

The cache should contain local video files named by video id, for example:

```text
/path/to/local/video/cache/BudSD89N5TI.mp4
```

Build evidence packs:

```bash
python stage4_self_evolve/build_evidence.py \
  --input stage4_self_evolve/outputs/candidates.jsonl \
  --output stage4_self_evolve/outputs/evidence_packs.jsonl \
  --limit 20
```

Verify GT with tool evidence:

```bash
python stage4_self_evolve/verify_gt.py \
  --input stage4_self_evolve/outputs/evidence_packs.jsonl \
  --output stage4_self_evolve/outputs/gt_verifications.jsonl
```

Verify MCQ options against the same evidence packs:

```bash
python stage4_self_evolve/verify_options.py \
  --input stage4_self_evolve/outputs/mcq_evidence_packs.jsonl \
  --output stage4_self_evolve/outputs/option_verifications.jsonl
```

The verifier is intentionally conservative:

- OCR can produce `supported` when the reference answer matches OCR evidence.
- OCR MCQ options can pass only when the correct option is supported and the
  distractors are not supported by the OCR evidence.
- Counting only verifies when the target maps to a known YOLO label.
- Spatial currently records tool evidence but returns `inconclusive` unless the relation can
  be safely checked.
- Missing local videos or missing tool server are explicit skip statuses, never silent passes.

Default paths:

- Input: `stage2_fifter_q/outputs/anno_qa_ref_fusion_by_question.csv`
- Candidates: `stage4_self_evolve/outputs/candidates.jsonl`
- Direct probes: `stage4_self_evolve/outputs/direct_probes.jsonl`
- Judged cases: `stage4_self_evolve/outputs/judged_cases.jsonl`
- Hard cases: `stage4_self_evolve/outputs/hard_cases.jsonl`
- Summary: `stage4_self_evolve/outputs/summary.json`

## Benchmark Seed Bank

V2 generation should not rely on prompt taxonomy alone. Prepare seed examples
from existing video benchmarks, then pass them into the harness-first generator:

```bash
python stage4_self_evolve/prepare_benchmark_seeds.py \
  --input stage1_gen_q/original_benchmarks/Video-MME.tsv \
  --schema video_mme \
  --output stage4_self_evolve/outputs/benchmark_seed_bank_videomme.jsonl
```

Generate with benchmark seeds, harness evidence, and the local video:

```bash
python stage4_self_evolve/generate_from_harness.py \
  --input stage4_self_evolve/outputs/v1_gemini_video_evidence_merged_74.jsonl \
  --output stage4_self_evolve/outputs/v2_seeded_candidates.jsonl \
  --api-key-file /path/to/gemini_api_key.txt \
  --provider google \
  --model gemini-3.5-flash \
  --run-id v2-seeded \
  --items-per-video 2 \
  --seed-examples stage4_self_evolve/outputs/benchmark_seed_bank_videomme.jsonl \
  --seed-examples-per-video 5 \
  --require-seed-examples \
  --include-local-video
```

Rows generated this way record `benchmark_seed_ids` and
`benchmark_seed_sources`, so later validation can analyze which seed families
produce hard, valid items.

## API Keys

New scripts do not store API keys. Use one of:

```bash
export VECTORENGINE_API_KEY=...
export GEMINI_API_KEY=...
```

For compatibility with the current codebase, `direct_probe.py` and
`judge_probes.py` also support `--use-legacy-vectorengine-keys`, which extracts
existing `sk-...` keys from earlier scripts.

## Hardness Criteria

Each kept hard case should satisfy:

- `gt_verified`: the reference answer is answerable and has evidence spans.
- `category_aligned`: the question matches the intended task category.
- `nontrivial`: the question is not a shallow title/static-image/question-only case.
- `direct_model_correct == false` or `direct_model_confidence <= threshold`.

Failure modes are normalized into labels such as:

- `missed_short_event`
- `wrong_count`
- `temporal_confusion`
- `ocr_miss`
- `spatial_relation_error`
- `attribute_confusion`
- `over_refusal`
- `unanswerable_claim`
- `other`
