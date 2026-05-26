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
new_task_type = "OCR"
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
    "OCR Problems",
    # "Spatial Perception",
    # "Spatial Reasoning",
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



#MME-VideoOCR
path = repo_path('stage1_gen_q', 'original_benchmarks', 'mm_videoocr.json')
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

all_task_types = []
for item in data:
    if item["task_type"] not in all_task_types:
        all_task_types.append(item["task_type"])
        # print(item["task_type"])

used_task_types = [
    "Text_Recognition", 
    "Visual_Text_QA",
    # "Text_Grounding",
    "Attribute_Recognition",
    # "Text_Based_Reasoning",
    # "Change_Detection_and_Tracking",
    # "Special_Text_Parising",
    # "Robust_Video_Testing",
    # "Cross_Frame_Text_Understanding",
    # "Text_Based_Video_Understanding",
]
used_task_types = {task_type: [] for task_type in used_task_types}
for item in data:
    if item["task_type"] not in used_task_types:
        continue
    question = item["question"]
    answer = item["answer"]
    options = item["option"]
    o_benchmark = "mm_videoocr"
    o_task_type = item["task_type"]
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


#FG-Bench
path = repo_path('stage1_gen_q', 'original_benchmarks', 'fg_bench_fusion.json')
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

all_task_types = []
for item in data:
    if item["Question Type"] not in all_task_types:
        all_task_types.append(item["Question Type"])

used_task_types = [
    "Text Recognition",
    # "Semantic Understanding",
    # "Spatial Relation",
    # "Script Information",
    # "Temporal Localization",
    # "Movement Detection",
    # "Temporal Information",
]
used_task_types = {task_type: [] for task_type in used_task_types}
for item in data:
    if item["Question Type"] not in used_task_types:
        continue
    question = item["Q"]
    answer = item["A"]
    options = []
    o_benchmark = "fg_bench"
    o_task_type = item["Question Type"]
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
