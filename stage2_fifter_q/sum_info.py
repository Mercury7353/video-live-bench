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

path = repo_path('stage1_gen_q', 'anno_q')
json_list = [os.path.join(path, file) for file in os.listdir(path) if file.endswith(".json")]


all_data = []
for json_file in json_list:
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    all_data.extend(data)

print(len(all_data))

# save to csv
df = pd.DataFrame(all_data)

videos_ids = df["video_id"].unique()
print(f"num_videos: {len(videos_ids)}")
# df.to_csv(json_file.replace(".json", ".csv"), index=False)
# print(f"save to {json_file.replace('.json', '.csv')}")