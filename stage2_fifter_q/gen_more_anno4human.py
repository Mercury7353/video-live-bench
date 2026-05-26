import os
import pandas as pd

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent


def repo_path(*parts):
    return str(PROJECT_ROOT.joinpath(*parts))

all_data_path = repo_path('stage2_fifter_q', 'outputs', 'anno_qa_ref_fusion_by_question.csv')

# 直接读即可，不需要 open
all_data = pd.read_csv(all_data_path)

used_paths = [
    repo_path('stage2_fifter_q', 'outputs', 'anno_qa_ref_fusion_1_new.xlsx'),
    repo_path('stage2_fifter_q', 'outputs', 'anno_qa_ref_fusion_2_new.xlsx'),
]

def norm(x):
    if pd.isna(x):
        return ""
    return str(x).strip()

# 用 set 存 key
used_keys = set()
for p in used_paths:
    used_df = pd.read_excel(p)
    for _, r in used_df.iterrows():
        used_keys.add((norm(r["url"]), norm(r["question"])))

# 构建 all_keys 便于校验
all_keys = [(norm(r["url"]), norm(r["question"])) for _, r in all_data.iterrows()]

# ====== 校验：used 是否真的在 all 里、以及重叠数量 ======
all_key_set = set(all_keys)
overlap = used_keys & all_key_set
print(f"used_keys: {len(used_keys)}")
print(f"all_keys:  {len(all_key_set)}")
print(f"overlap (used ∩ all): {len(overlap)}")
print(f"used not in all: {len(used_keys - all_key_set)}")  # 如果不为 0，说明 used 里有 all 没有的条目

# ====== 真正过滤 ======
mask = [k not in used_keys for k in all_keys]
df = all_data[mask].reset_index(drop=True)

print(f"after filter: {len(df)} (removed {len(all_data) - len(df)})")

# shuffle（可选）
df = df.sample(frac=1, random_state=42).reset_index(drop=True)

# 每个 task_type 抽 100（注意：不足 100 会报错）
task_type_df = (
    df.groupby("task_type", group_keys=False)
      .apply(lambda g: g.sample(n=min(100, len(g)), random_state=42))
      .reset_index(drop=True)
)

save_path = repo_path('stage2_fifter_q', 'outputs', '20260205')
os.makedirs(save_path, exist_ok=True)

# 均分成两份
part1, part2 = [], []
for task_type, g in task_type_df.groupby("task_type"):
    g = g.sample(frac=1, random_state=42).reset_index(drop=True)
    half = len(g) // 2
    part1.append(g.iloc[:half])
    part2.append(g.iloc[half:])

task_type_df_1 = pd.concat(part1, ignore_index=True)
task_type_df_2 = pd.concat(part2, ignore_index=True)

out1 = os.path.join(save_path, "anno_qa_ref_fusion_1_20260205.xlsx")
out2 = os.path.join(save_path, "anno_qa_ref_fusion_2_20260205.xlsx")
task_type_df_1.to_excel(out1, index=False)
task_type_df_2.to_excel(out2, index=False)

print(f"save to {out1} and {out2}")
