import os
import json

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent


def repo_path(*parts):
    return str(PROJECT_ROOT.joinpath(*parts))

path = repo_path('stage0_get_videoid', 's0_collect_videos', 'outputs')
result_files = [f for f in os.listdir(path) if f.endswith(".json")]


used_video_ids = {}
fusion_video_info = []

num_categories = {}

for file in result_files:
    with open(os.path.join(path, file), "r", encoding="utf-8") as f:
        data = json.load(f)
    for item in data:
        video_id = item["videoId"]
        if video_id in used_video_ids:
            continue
        used_video_ids[video_id] = True
        item["category1"] = item["parent_category"]
        item["parent_category"] = item["keyword"]
        if item["parent_category"] not in num_categories:
            num_categories[item["parent_category"]] = 0
        num_categories[item["parent_category"]] += 1
        fusion_video_info.append(item)

print("num_categories: ", num_categories)
print("number of categories: ", len(num_categories))
print("used_video_ids length: ", len(used_video_ids))
print("fusion_video_info length: ", len(fusion_video_info))
with open(os.path.join(path, "fusion_all_vides.json"), "w", encoding="utf-8") as f:
    json.dump(fusion_video_info, f, indent=4, ensure_ascii=False)