import os
import json
import pandas as pd

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent


def repo_path(*parts):
    return str(PROJECT_ROOT.joinpath(*parts))

"""
1. question
2. answer
3. options
4. task_type
5. o_benchmark
6. o_task_type
"""

question_pool = []
new_task_type = "Reasoning"
#videomme

path = repo_path('stage1_gen_q', 'original_benchmarks', 'Video-MME.tsv')
df = pd.read_csv(path, sep="\t")

#查看所有类别task_type
task_types = df["task_type"].unique()
# for task_type in task_types:
#     print(task_type)

used_task_types = [
    # "Counting Problem",
    # "Information Synopsis",
    # "Object Recognition",
    "Action Reasoning",
    "Object Reasoning",
    # "Temporal Perception",
    # "Attribute Perception",
    "Temporal Reasoning",
    # "Action Recognition",
    # "OCR Problems",
    # "Spatial Perception",
    "Spatial Reasoning",
]
used_task_types = {task_type: [] for task_type in used_task_types}

for index, row in df.iterrows():
    question = row["question"]
    answer = row["answer"]
    options = row["candidates"]
    options = eval(options)
    task_type = row["task_type"]
    o_benchmark = "videomme"
    
    if task_type not in used_task_types:
        continue
    question_pool.append({
        "question": question,
        "answer": answer,
        "options": options,
        "task_type": new_task_type,
        "o_benchmark": o_benchmark,
        "o_task_type": task_type,
    })
current_num = len(question_pool)
print(current_num)
print(question_pool[-1])

#mlvu
path = repo_path('stage1_gen_q', 'original_benchmarks', 'MLVU_MCQ.tsv')
df = pd.read_csv(path, sep="\t")

task_types = df["task_type"].unique()
# for task_type in task_types:
#     print(task_type)

used_task_types = [
    # "plotQA",
    # "needle",
    # "ego",
    # "count",
    "order",
    # "anomaly_reco",
    "topic_reasoning",
]
used_task_types = {task_type: [] for task_type in used_task_types}


for index, row in df.iterrows():
    question = row["question"]
    answer = row["answer"]
    options = row["candidates"]
    options = eval(options)
    task_type = row["task_type"]
    o_benchmark = "mlvu"
    o_task_type = task_type
    if task_type not in used_task_types:
        continue
    question_pool.append({
        "question": question,
        "answer": answer,
        "options": options,
        "task_type": new_task_type,
        "o_benchmark": o_benchmark,
        "o_task_type": o_task_type,
    })
print(len(question_pool) - current_num)
print(question_pool[-1])
current_num = len(question_pool)
#longvideobench
path = repo_path('stage1_gen_q', 'original_benchmarks', 'LongVideoBench.tsv')
df = pd.read_csv(path, sep="\t")

for index, row in df.iterrows():
    question = row["question"]
    if "subtitle" in question:
        continue
    answer = row["correct_choice"]
    options = row["candidates"]
    options = eval(options)
    level = row["level"]
    question_category = row["question_category"]
    if "L2" not in level:
        continue
    o_benchmark = "longvideobench"
    o_task_type = question_category
    question_pool.append({
        "question": question,
        "answer": answer,
        "options": options,
        "task_type": new_task_type,
        "o_benchmark": o_benchmark,
        "o_task_type": o_task_type,
    })

print(len(question_pool) - current_num)
current_num = len(question_pool)
print(question_pool[-1])

#
print(f"total question number: {len(question_pool)}")
save_path = repo_path('stage1_gen_q', 'question_pool')
with open(os.path.join(save_path, f"{new_task_type}.json"), "w", encoding="utf-8") as f:
    json.dump(question_pool, f, ensure_ascii=False, indent=4)
