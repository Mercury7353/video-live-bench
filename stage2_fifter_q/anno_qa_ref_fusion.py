import os, json
import pandas as pd
from collections import defaultdict

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent


def repo_path(*parts):
    return str(PROJECT_ROOT.joinpath(*parts))

path = repo_path('stage2_fifter_q', 'outputs')
save_path = path

# 1) 读取 CSV（建议排序，保证可复现）
csv_list = sorted([os.path.join(path, f) for f in os.listdir(path) if f.endswith(".csv")])

q_samples = []
for csv_file in csv_list:
    df = pd.read_csv(csv_file)
    q_samples.extend(df.to_dict(orient="records"))

# 2) 建立 question -> 多条记录 的索引（因为 question 可能重复）
q_index = defaultdict(list)
for item in q_samples:
    q = item.get("question")
    if pd.isna(q) or q is None:
        continue
    q_index[str(q)].append(item)

# 3) 读取 ref_a_data，并要求其中必须包含 question（否则没法用 question 匹配）
ref_a_file = os.path.join(path, "ref_a_fusion.json")
with open(ref_a_file, "r") as f:
    ref_a_data = json.load(f)

# 4) 融合：按 question 匹配，优先 url 精确匹配
samples = []
used_q = set()
missing = 0
multi_hit = 0

for _, ref in ref_a_data.items():
    if "question" not in ref:
        raise ValueError("ref_a_fusion.json 的每条记录里没有 'question' 字段，无法用 question 匹配。")

    q = str(ref["question"])
    if q in used_q:
        continue
    used_q.add(q)

    candidates = q_index.get(q, [])
    if not candidates:
        missing += 1
        continue

    chosen = None
    if "url" in ref and ref["url"] is not None:
        for c in candidates:
            if str(c.get("url")) == str(ref["url"]):
                chosen = c
                break
    if chosen is None:
        chosen = candidates[0]
        if len(candidates) > 1:
            multi_hit += 1
            print(f"[WARN] question 命中多条({len(candidates)})且未用 url 唯一确定，取第一条。question={q[:80]}")

    # 只把你需要的 ref 字段拷过来，避免覆盖 CSV 的 task_type 等
    new_item = chosen.copy()

    # 下面这些字段名请按你 ref_a_fusion.json 的真实 key 调整
    new_item["reference_answer"] = ref.get("reference_answer", new_item.get("reference_answer"))
    new_item["question_span"] = ref.get("question_span", new_item.get("question_span"))
    # 你原来用的是 ref["answer_span"] -> ref_answer_span
    new_item["ref_answer_span"] = ref.get("answer_span", ref.get("ref_answer_span", new_item.get("ref_answer_span")))
    new_item["reasoning"] = ref.get("reasoning", new_item.get("reasoning"))
    new_item["uncertainty"] = ref.get("uncertainty", new_item.get("uncertainty"))

    samples.append({
        "url": new_item.get("url"),
        "task_type": new_item.get("task_type"),  # 以 CSV 的 task_type 为准
        "question": new_item.get("question"),
        "answer": None,
        "reference_answer": new_item.get("reference_answer"),
        "question_span": new_item.get("question_span"),
        "ref_answer_span": new_item.get("ref_answer_span"),
        "reasoning": new_item.get("reasoning"),
        "uncertainty": new_item.get("uncertainty"),
        "id": None,  # 不再使用 enumerate 的 id，避免错配；需要的话可以另设 uuid
    })

df = pd.DataFrame(samples)
os.makedirs(save_path, exist_ok=True)
df.to_csv(os.path.join(save_path, "anno_qa_ref_fusion_by_question.csv"), index=False)
print(f"save to anno_qa_ref_fusion_by_question.csv")
print(f"[STAT] missing={missing}, multi_hit={multi_hit}, total={len(df)}")

# shuffle（可选）
df = df.sample(frac=1, random_state=42).reset_index(drop=True)

# 每个 task_type 抽 20
task_type_df = (
    df.groupby("task_type", group_keys=False)
      .sample(n=20, random_state=42)
)

# 均分成两份
part1, part2 = [], []
for task_type, g in task_type_df.groupby("task_type"):
    g = g.sample(frac=1, random_state=42).reset_index(drop=True)  # 类内再打散一下（可选）
    half = len(g) // 2
    part1.append(g.iloc[:half])
    part2.append(g.iloc[half:])

task_type_df_1 = pd.concat(part1, ignore_index=True)
task_type_df_2 = pd.concat(part2, ignore_index=True)

task_type_df_1.to_excel(os.path.join(save_path, f"anno_qa_ref_fusion_1_new.xlsx"), index=False)
#save to csv
task_type_df_1.to_csv(os.path.join(save_path, f"anno_qa_ref_fusion_1_new.csv"), index=False)
task_type_df_2.to_excel(os.path.join(save_path, f"anno_qa_ref_fusion_2_new.xlsx"), index=False)
task_type_df_2.to_csv(os.path.join(save_path, f"anno_qa_ref_fusion_2_new.csv"), index=False)
print(f"save to anno_qa_ref_fusion_1_new.xlsx and anno_qa_ref_fusion_2_new.xlsx")