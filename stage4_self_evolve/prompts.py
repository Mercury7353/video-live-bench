DIRECT_PROBE_PROMPT = """You are evaluating a video benchmark question.

Answer the question based ONLY on the provided video.
Do not use external knowledge.
Do not mention uncertainty unless the answer is genuinely not visible.

Return JSON only:
{{
  "answer": "short final answer",
  "confidence": 0.0,
  "reasoning_brief": "one concise sentence"
}}

Question: {question}
"""


JUDGE_PROMPT = """You are judging whether a direct model answer matches a verified video QA ground truth.

The ground truth was produced by a tool-assisted harness and includes evidence spans.
Judge semantic correctness, not exact string match. Be strict about counts, temporal order,
OCR text, spatial relations, and attributes. If the direct answer is vague, incomplete,
or contradicts the verified evidence, mark it incorrect.

Return JSON only:
{{
  "direct_model_correct": true,
  "category_aligned": true,
  "gt_verified": true,
  "nontrivial": true,
  "failure_mode": "none|missed_short_event|wrong_count|temporal_confusion|ocr_miss|spatial_relation_error|attribute_confusion|over_refusal|unanswerable_claim|other",
  "judgement": "short explanation"
}}

Task type: {task_type}
Question: {question}
Verified reference answer: {reference_answer}
Evidence spans: {evidence_spans}
Harness reasoning: {harness_reasoning}
Direct model answer: {direct_answer}
Direct model confidence: {direct_confidence}
Direct model brief reasoning: {direct_reasoning}
"""


CATEGORY_ALIGNMENT_PROMPT = """You are validating a video benchmark item.

Check if the question belongs to the stated task type and whether the reference answer
is verifiable from the provided evidence. Do not judge whether the direct model is correct.

Return JSON only:
{{
  "category_aligned": true,
  "gt_verified": true,
  "nontrivial": true,
  "notes": "short explanation"
}}

Task type: {task_type}
Question: {question}
Reference answer: {reference_answer}
Evidence spans: {evidence_spans}
Harness reasoning: {harness_reasoning}
"""


MCQ_REVIEW_PROMPT = """You are reviewing one multiple-choice video benchmark item.

The benchmark goal is to find aligned, nontrivial video questions where a
tool-assisted harness can verify the answer but a direct model may fail.

Reject items that are:
- outside the stated task type;
- answerable from option wording alone;
- brittle because they rely on an unnecessary tiny detail;
- invalid because more than one option could be correct;
- invalid because the correct option is not supported by the reference answer and reasoning.

For distractors, prefer plausible wrong alternatives of the same semantic form
as the correct option. Do not reward distractors that are merely unrelated.

Return JSON only:
{{
  "category_aligned": true,
  "gt_supported": true,
  "nontrivial": true,
  "unique_correct": true,
  "distractors_plausible": true,
  "option_leakage": false,
  "decision": "keep|repair|drop",
  "issues": ["short issue labels"],
  "notes": "short explanation"
}}

Task type: {task_type}
Question: {question}
Reference answer: {reference_answer}
Harness reasoning: {harness_reasoning}
Options: {options}
Correct option label: {correct_option}
"""


MCQ_EVAL_PROMPT = """Answer this multiple-choice video benchmark question.

Return JSON only:
{{
  "answer": "A|B|C|D",
  "confidence": 0.0,
  "reasoning_brief": "one concise sentence"
}}

Question: {question}
Options:
{options}
"""


MCQ_OPTIONS_ONLY_PROMPT = """Answer this multiple-choice benchmark question without seeing the video.

This is an options-only leakage/triviality probe. Use only the question text and
options. If the answer cannot be determined without the video, make your best
guess and keep confidence low.

Return JSON only:
{{
  "answer": "A|B|C|D",
  "confidence": 0.0,
  "reasoning_brief": "one concise sentence"
}}

Question: {question}
Options:
{options}
"""
