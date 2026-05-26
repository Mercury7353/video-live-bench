# Benchmark Self-Evolving

**Citation key:** `wang2024benchmarkSelfEvolving`

**Paper:** Benchmark Self-Evolving: A Multi-Agent Framework for Dynamic LLM Evaluation

**URL:** https://arxiv.org/abs/2402.11443

## Problem

Static benchmarks become stale as LLMs improve and as benchmark data leaks into training.
The paper proposes evolving existing benchmark instances instead of building entirely new
datasets from scratch.

## Core Idea

Represent each benchmark instance as `(context, question, answer)` and generate an evolved
instance by editing either the context or the question while updating or preserving the
answer as required.

The paper groups evolution into three evaluation goals:

- **Scalable evaluation:** create alternative or more complex questions from the same context.
- **Robust evaluation:** perturb the context through paraphrasing, noising, or polarity reversal.
- **Fine-grained evaluation:** generate sub-ability questions, such as planning, implicit
  knowledge, and relevant context retrieval.

## Multi-Agent Workflow

The method uses four GPT-4 powered agents:

1. **Instance pre-filter**
   - Keep original instances that GPT-4 can already answer correctly.
   - Purpose: ensure the seed instance is within the system's reliable operating region.

2. **Instance creator**
   - Generates the evolved `(context, question, answer)` according to one of the reframing
     operations.

3. **Candidate option formulator**
   - Generates an intentionally wrong option for the evolved context-question pair.
   - This is not only for multiple-choice evaluation; it is also used as a reliability test.

4. **Instance verifier**
   - Verifies that the generated correct answer is valid.
   - Also verifies that the generated wrong option is invalid.
   - The final item is kept only if:
     - `Verifier(context, question, correct_answer) == true`
     - `Verifier(context, question, wrong_option) == false`

This is the paper's key quality-control mechanism: a generated instance must pass a
positive verification and a negative verification.

## Relevance to Our Video Benchmark

The paper's text-only setting maps naturally to our video setting if we replace `context`
with `video + evidence spans`.

Recommended adaptation:

```text
Original video QA
 -> pre-filter: keep items whose GT can be verified from evidence spans
 -> creator: derive harder but category-aligned video questions
 -> option formulator: create plausible-but-wrong distractors
 -> verifier:
      accepts correct answer from evidence
      rejects each distractor from evidence
 -> direct probe:
      keep if Gemini-direct / SOTA model selects a distractor or is unstable
```

For MCQ generation, the most useful part is the **candidate option formulator + verifier**
loop. Distractors should be generated adversarially, but they should not be trusted until
an evidence-aware verifier confirms they are wrong.

## Design Implications

- Do not use direct-model failure alone as the definition of hardness.
- Maintain separate roles:
  - generator proposes hard variants or distractors;
  - verifier checks correctness using evidence;
  - direct solver measures model failure.
- For each MCQ, store verification metadata:
  - `correct_option_verified`
  - `distractors_verified_wrong`
  - `ambiguity_flags`
  - `failure_modes`
- Add a negative verification test for every distractor, not only a positive test for GT.

## Caveats

- The paper relies on GPT-4 for all agents, so verifier errors can still propagate.
- Their wrong-option generation is binary-choice oriented; our video benchmark likely needs
  3 distractors and stronger ambiguity checking.
- For video tasks, verifier quality should be improved with frame/OCR/object/evidence tools,
  not only an LLM judge.
