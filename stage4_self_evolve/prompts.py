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


HARNESS_QA_GENERATION_PROMPT = """You are constructing a live video benchmark from tool-assisted harness evidence.

Goal:
- Generate aligned, nontrivial multiple-choice video questions.
- The ground truth must be verifiable from the provided harness evidence.
- A direct bare video model should plausibly fail without using the harness.

Allowed question families:
- OCR: meaningful text/sign/UI in the video, not single-character nitpicks.
- Counting: count salient objects/actions over a span, not a single ambiguous frame.
- Spatial: relation among salient objects/people, only when evidence supports it.
- Temporal: order, persistence, or state change across multiple moments.
- Action/Event reasoning: what happened, what changed, or why a later state follows.
- Multi-object tracking: identities or roles across time, when tracking evidence exists.

Reject brittle/trivial items:
- Do not ask exact timestamps, frame numbers, tiny colors/logos, or one-pixel details.
- Do not make options differ only by minor wording or hidden formatting.
- Do not ask questions answerable from common sense or option wording alone.
- Do not create an item if the harness evidence does not verify one unique answer.

For each item, create plausible distractors of the same semantic type as the answer.
Distractors should be wrong according to the evidence but close enough to test video understanding.

Return JSON only:
{{
  "items": [
    {{
      "task_type": "OCR|Counting|Spatial|Temporal|Reasoning|Tracking|Perception",
      "question": "question text",
      "reference_answer": "short answer text",
      "options": [
        {{"label": "A", "text": "option"}},
        {{"label": "B", "text": "option"}},
        {{"label": "C", "text": "option"}},
        {{"label": "D", "text": "option"}}
      ],
      "correct_option": "A|B|C|D",
      "evidence_spans": [[0.0, 1.0]],
      "required_skills": ["ocr|yolo|asr|tracking|temporal_reasoning|caption"],
      "harness_reasoning": "brief evidence-grounded reasoning",
      "gt_verification_plan": "how a harness can verify the answer",
      "nontriviality_rationale": "why this is not a brittle detail or option-only question",
      "distractor_rationale": "why the wrong options are plausible but unsupported"
    }}
  ]
}}

Video id: {video_id}
Video URL: {url}
Harness evidence JSON:
{evidence_json}
"""
