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


# ===============================
# 文件加载
# ===============================
root_path = repo_path('stage0_get_videoid', 's0_collect_videos', 'outputs', 'fusion_all_vides.json')

save_path = repo_path('stage0_get_videoid', 's1_fifter_videos')
save_path = os.path.join(save_path, "outputs")
if not os.path.exists(save_path):
    os.makedirs(save_path)

with open(root_path, "r", encoding="utf-8") as f:
    videos = json.load(f)


# ===============================
# 时长区间定义
# ===============================
duration_buckets = {
    "[0-5)":  lambda m: 0 <= m < 5,
    "[5-10)": lambda m: 5 <= m < 10,
    "[10-30)": lambda m: 10 <= m < 30,
    "[30-60)": lambda m: 30 <= m < 60,
    # "[60+)": lambda m: m >= 60
}

# 可配置参数
SAMPLE_PER_BUCKET = 3000
MIN_PER_CATEGORY = (SAMPLE_PER_BUCKET * 4) // 100


# ===============================
# Step 1: 按时长区间分桶
# ===============================
bucketed = {k: [] for k in duration_buckets}

for v in videos:
    mins = parse_duration(v["duration"])
    for key, cond in duration_buckets.items():
        if cond(mins):
            bucketed[key].append(v)
            break


# ===============================
# Step 2: 从每个区间抽样
# ===============================
selected_initial = {k: [] for k in bucketed}

for key, items in bucketed.items():
    if len(items) <= SAMPLE_PER_BUCKET:
        selected_initial[key] = items.copy()
    else:
        selected_initial[key] = random.sample(items, SAMPLE_PER_BUCKET)


# ===============================
# Step 3: 计算初步类别数量
# ===============================
parent_stats_initial = {}
for bucket in selected_initial.values():
    for v in bucket:
        p = v["parent_category"]
        parent_stats_initial[p] = parent_stats_initial.get(p, 0) + 1


# ===============================
# Step 4: 补齐每个 parent_category 至少 MIN_PER_CATEGORY
# ===============================

used_ids = {v["videoId"] for bucket in selected_initial.values() for v in bucket}

parent_to_videos = {}
for bucket in selected_initial.values():
    for v in bucket:
        p = v["parent_category"]
        parent_to_videos.setdefault(p, []).append(v)

# 补齐
for p, vids in parent_to_videos.items():
    need = MIN_PER_CATEGORY - len(vids)
    if need <= 0:
        continue

    candidates = [
        v for v in videos
        if v.get("parent_category") == p and v["videoId"] not in used_ids
    ]

    if len(candidates) < need:
        print(f"⚠ 警告：类别 {p} 不足以补齐，需要 {need}，可用 {len(candidates)}")
        need = len(candidates)

    selected_extra = random.sample(candidates, need)

    for v in selected_extra:
        parent_to_videos[p].append(v)
        used_ids.add(v["videoId"])


# ===============================
# Step 5: 最终按时长区间分类
# ===============================
selected_final = {k: [] for k in duration_buckets}

for vs in parent_to_videos.values():
    for v in vs:
        mins = parse_duration(v["duration"])
        for key, cond in duration_buckets.items():
            if cond(mins):
                selected_final[key].append(v)
                break


# ===============================
# Step 6: 打印统计结果
# ===============================

print("\n==============================")
print("📌 最终时长区间统计")
print("==============================")
for key, vids in selected_final.items():
    print(f"{key:8s}: {len(vids)} 个")

print("\n==============================")
print("📌 最终 parent_category 数量统计")
print("==============================")

num_categories = {}
for bucket in selected_final.values():
    for v in bucket:
        p = v["parent_category"]
        if p not in num_categories:
            num_categories[p] = 0
        num_categories[p] += 1
print("number of categories: ", len(num_categories))


all_num = 0
final_parent_stats = {}
for bucket in selected_final.values():
    for v in bucket:
        p = v["parent_category"]
        final_parent_stats[p] = final_parent_stats.get(p, 0) + 1
        all_num += 1
i = 0
for p, count in sorted(final_parent_stats.items(), key=lambda x: -x[1]):
    print(f"{{{i:2d}}} {p:20s}: {count} 个")
    i += 1

print("number of all videos: ", all_num)




# ===============================
# Step 7: 保存
# ===============================
with open(os.path.join(save_path, "selected_videos.json"), "w", encoding="utf-8") as f:
    json.dump(selected_final, f, ensure_ascii=False, indent=4)

