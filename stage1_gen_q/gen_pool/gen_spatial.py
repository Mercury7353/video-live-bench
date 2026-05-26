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
new_task_type = "Spatial"


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
    # "Action Reasoning",
    # "Object Reasoning",
    # "Temporal Perception",
    # "Attribute Perception",
    # "Temporal Reasoning",
    # "Action Recognition",
    # "OCR Problems",
    "Spatial Perception",
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

#VSI-Bench
path = repo_path('stage1_gen_q', 'original_benchmarks', 'vsi_bench.jsonl')
all_qa_list = []
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        item = json.loads(line)
        all_qa_list.append(item)

all_task_types = []
for item in all_qa_list:
    if item["question_type"] not in all_task_types:
        all_task_types.append(item["question_type"])
        # print(item["question_type"])
current_num = 0
used_task_types = [
    # "object_counting",
    # "object_size_estimation",
    # "room_size_estimation",
    # "object_abs_distance",
    "object_rel_direction_hard",
    "object_rel_direction_medium",
    "object_rel_direction_easy",
    "object_rel_distance",
    # "obj_appearance_order",
    "route_planning",
]
used_task_types = {task_type: [] for task_type in used_task_types}
for item in all_qa_list:
    if item["question_type"] not in used_task_types:
        continue
    question = item["question"]
    answer = item["ground_truth"]
    options = item["options"]
    o_benchmark = "vsi_bench"
    o_task_type = item["question_type"]
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


#STI-Bench
path = repo_path('stage1_gen_q', 'original_benchmarks', 'sti_bench.json')

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

all_task_types = []
for item in data:
    if item["Task"] not in all_task_types:
        all_task_types.append(item["Task"])
        # print(item["Task"])

used_task_types = [
    # "Displacement & Path Length",
    # "Speed & Acceleration",
    # "Pose Estimation",
    # "3D Video Grounding",
    "Spatial Relation",
    # "Dimensional Measurement",
    # "Ego-Centric Orientation",
    # "Trajectory Description",
]
used_task_types = {task_type: [] for task_type in used_task_types}
for item in data:
    if item["Task"] not in used_task_types:
        continue

    if item["QType"] != "Single Choice":
        continue
    question = item["Question"]
    answer = item["Answer"]
    options = item["Candidates"]
    o_benchmark = "sti_bench"
    o_task_type = item["Task"]
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

print(f"total question number: {len(question_pool)}")
save_path = repo_path('stage1_gen_q', 'question_pool')
with open(os.path.join(save_path, f"{new_task_type}.json"), "w", encoding="utf-8") as f:
    json.dump(question_pool, f, ensure_ascii=False, indent=4)
