import json
import matplotlib.pyplot as plt

import numpy as np
import matplotlib.pyplot as plt
import os
import re

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent


def repo_path(*parts):
    return str(PROJECT_ROOT.joinpath(*parts))

def parse_duration(duration_str):
    if not duration_str or not isinstance(duration_str, str):
        return 0

    hours = minutes = seconds = 0

    h = re.search(r"(\d+)H", duration_str)
    m = re.search(r"(\d+)M", duration_str)
    s = re.search(r"(\d+)S", duration_str)

    if h: hours = int(h.group(1))
    if m: minutes = int(m.group(1))
    if s: seconds = int(s.group(1))

    return hours * 60 + minutes + seconds / 60


path = repo_path('stage0_get_videoid', 's1_fifter_videos', 'outputs', 'selected_videos_balance_category.json')
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

new_list = []
for key, value in data.items():
    duration_type = key
    for item in value:
        item["duration_type"] = duration_type
        item["original_duration"] = item["duration"]
        item["duration"] = parse_duration(item["duration"])
        new_list.append(item)

with open(path.replace(".json", "_new.json"), "w", encoding="utf-8") as f:
    json.dump(new_list, f, ensure_ascii=False, indent=4)



new_data = []
for key, value in data.items():
    new_data.extend(value)

#统计每个类别的视频数量
num_categories = {}
for item in new_data:
    category = item["parent_category"]
    if category not in num_categories:
        num_categories[category] = 0
    num_categories[category] += 1
for category in num_categories:
    print(f"number of videos in {category}: {num_categories[category]}")

# 分钟列表（可按你需求改成 round/ceil）
duration_list = [item["duration"] for item in new_data]
mins = np.floor(duration_list).astype(int)   # 3.9 -> 3 分钟档

max_min = mins.max() if len(mins) else 0
counts = np.bincount(mins, minlength=max_min + 1)  # counts[i] = i分钟的数量
x = np.arange(len(counts))  # 0,1,2,...

plt.figure(figsize=(12, 5))
bars = plt.bar(x, counts, width=0.9, align='edge', alpha=0.7, edgecolor='k')


# 刻度在柱子中间（x 就是柱中心）
plt.xticks(np.arange(0, max_min + 1, 5))  # 每5分钟一个刻度（按需改）
plt.xlabel('Duration (minutes)')
plt.ylabel('Frequency')
plt.title('Duration Distribution (1-min bins, centered)')
save_path=repo_path('stage0_get_videoid', 's1_fifter_videos', 'outputs')
plt.savefig(os.path.join(save_path, "duration_distribution.png"))
plt.close()

