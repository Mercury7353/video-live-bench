import os
import json
import pandas as pd
import random
import char

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent


def repo_path(*parts):
    return str(PROJECT_ROOT.joinpath(*parts))

path = repo_path('stage1_gen_q', 'anno_q')
json_list = [os.path.join(path, file) for file in os.listdir(path) if file.endswith(".json")]


all_data = {}
for json_file in json_list:
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    task_type = os.path.basename(json_file).split(".")[0]
    all_data[task_type] = data

num_qa_per_task = 40


video_dict = {}
path = repo_path('stage0_get_videoid', 's1_fifter_videos', 'outputs', 'selected_videos_balance_category_v2_new.json')
with open(path, "r", encoding="utf-8") as f:
    video_data = json.load(f)
for item in video_data:
    video_dict[item["videoId"]] = item

import re

def has_chinese(s: str) -> bool:
    return bool(re.search(r'[\u4e00-\u9fff]', s))

all_sub_data = []

#生成六份不同的sub_data
for i in range(6):
    sub_data = []
    for task_type, data in all_data.items():
        random.shuffle(data)
        used_videos = []
        num = 0
        for item in data:
            #检查是否有中文 
            if has_chinese(item["question"]):
                print(f"has chinese: {item['question']}")
                continue
            if item["video_id"] not in used_videos:
                try:
                    used_videos.append(item["video_id"])
                    

                    item["url"] = f"https://www.youtube.com/watch?v={item['video_id']}"
                    ref_idx = item["ref_idx"].replace("ref_q", "")
                    if len(item["ref_q"][int(ref_idx) - 1]) == 1:
                        continue
                    else:
                        item["ref_q"] = item["ref_q"][int(ref_idx) - 1]
                    
                    item["duration"] = video_dict[item["video_id"]]["duration"]
                    item["category"] = video_dict[item["video_id"]]["keyword"]
                    item["duration_type"] = video_dict[item["video_id"]]["duration_type"]
                    item["publishedAt"] = video_dict[item["video_id"]]["publishedAt"]
                    item["answer"] = ""
                except Exception as e:
                    print(f"error: {e}")
                    continue
                new_item = {
                    "url": item["url"],
                    "task_type": task_type,
                    "question": item["question"],
                    "answer": item["answer"],
                    "ref_q": item["ref_q"],
                    "duration": item["duration"],
                    "category": item["category"],
                    "duration_type": item["duration_type"],
                    "publishedAt": item["publishedAt"],
                    "video_id": item["video_id"],
                    "ref_idx": item["ref_idx"],
                    "ref_q": item["ref_q"],
                    "duration": item["duration"] * 60,
                    "category": item["category"],
                    "duration_type": item["duration_type"],
                    "publishedAt": item["publishedAt"],
                }
                
                sub_data.append(new_item)
                num += 1
                if num >= num_qa_per_task:
                    break
    
    all_sub_data.extend(sub_data)
    print(len(sub_data))
    print(sub_data[0])
    # # save to csv
    df = pd.DataFrame(sub_data)
    save_path = repo_path('stage2_fifter_q', 'outputs')
    os.makedirs(save_path, exist_ok=True)
    df.to_csv(os.path.join(save_path, f"sub_data_{i}.csv"), index=False)
    print(f"save to sub_data.csv")

#

#检查一共有多少个不同的video_id
all_videoids = []
for item in all_sub_data:
    all_videoids.append(item["video_id"])
print(f"num_videoids: {len(all_videoids)}")
print(f"num_unique_videoids: {len(set(all_videoids))}")

#统计有多少个问题，有多少个重复
all_questions = []
for item in all_sub_data:
    all_questions.append(item["question"])
print(f"num_questions: {len(all_questions)}")
print(f"num_unique_questions: {len(set(all_questions))}")
