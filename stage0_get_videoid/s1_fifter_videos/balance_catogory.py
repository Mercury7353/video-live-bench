import json
import random
import re
import os

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent


def repo_path(*parts):
    return str(PROJECT_ROOT.joinpath(*parts))

seed = random.randint(1, 1000000)
random.seed(seed)
# ===============================
# 解析 ISO 8601 Duration
# ===============================
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

# 时长区间定义
# ===============================
duration_buckets = {
    "[0-5)":  lambda m: 0 <= m < 5,
    "[5-10)": lambda m: 5 <= m < 10,
    "[10-30)": lambda m: 10 <= m < 30,
    "[30-60)": lambda m: 30 <= m < 60,
    # "[60+)": lambda m: m >= 60
}

path = repo_path('stage0_get_videoid', 's1_fifter_videos', 'outputs', 'selected_videos.json')
with open(path, "r", encoding="utf-8") as f:
    videos = json.load(f)

videos_list = []
for key, value in videos.items():
    videos_list.extend(value)

print("number of videos: ", len(videos_list))

MIN_PER_CATEGORY = 8
new_videos = []
num_categories = {}

import random
random.shuffle(videos_list)

DURATION_RULES = [
    {"min": 0,  "max": 1,  "limit": 42,  "count": 0},
    {"min": 1,  "max": 2,  "limit": 44,  "count": 0},
    {"min": 2,  "max": 3,  "limit":  43,  "count": 0},
    {"min": 3,  "max": 4,  "limit": 44,  "count": 0},
    {"min": 4,  "max": 5,  "limit": 50,  "count": 0},
    {"min": 5,  "max": 6,  "limit": 43,  "count": 0},
    {"min": 6,  "max": 7,  "limit": 42,  "count": 0},
    {"min": 7,  "max": 8,  "limit": 43,  "count": 0},
    {"min": 8,  "max": 9,  "limit": 44,  "count": 0},
    {"min": 9,  "max": 10, "limit": 42,  "count": 0},
    {"min": 5,  "max": 10, "limit": 210, "count": 0},
    {"min": 10, "max": 30, "limit": 195, "count": 0},
    {"min": 30, "max": 60, "limit": 185, "count": 0},
]


def match_duration_rule(mins, rules):
    for rule in rules:
        if rule["min"] <= mins < rule["max"]:
            return rule
    return None
for video in videos_list:
    category = video["parent_category"]

    if category not in num_categories:
        num_categories[category] = 0
    elif num_categories[category] >= MIN_PER_CATEGORY:
        continue

    mins = parse_duration(video["duration"])
    rule = match_duration_rule(mins, DURATION_RULES)

    # 不在任何区间，直接跳过（或你也可以选择接受）
    if rule is None:
        continue

    # 区间数量已满
    if rule["count"] >= rule["limit"]:
        continue

    # 通过所有限制
    rule["count"] += 1
    num_categories[category] += 1
    new_videos.append(video)



print("number of categories: ", len(num_categories))
print("number of new videos: ", len(new_videos))

#统计时间
bucketed = {k: [] for k in duration_buckets}
for video in new_videos:
    mins = parse_duration(video["duration"])
    for key, cond in duration_buckets.items():
        if cond(mins):
            bucketed[key].append(video)
            break
#统计每个区间的视频数量
for key, value in bucketed.items():
    print(f"number of videos in {key}: {len(value)}")
#统计每个类别的视频数量
for category in num_categories:
    print(f"number of videos in {category}: {num_categories[category]}")
with open(path.replace(".json", f"_balance_category_{seed}.json"), "w", encoding="utf-8") as f:
    json.dump(bucketed, f, indent=4, ensure_ascii=False)