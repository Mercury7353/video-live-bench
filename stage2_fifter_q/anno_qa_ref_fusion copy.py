import requests
import json
import torch
import torch.multiprocessing as mp
import tqdm
import os
import time
import json
import tqdm
from filelock import FileLock
import random
import argparse

        
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent


def repo_path(*parts):
    return str(PROJECT_ROOT.joinpath(*parts))

if __name__ == "__main__":

   #数据准备
   path = repo_path('stage2_fifter_q', 'outputs')
   csv_list = [os.path.join(path, file) for file in os.listdir(path) if file.endswith(".csv")]
   q_samples = []
   import pandas as pd
   for csv_file in csv_list:
      df = pd.read_csv(csv_file)
      df_dict = df.to_dict(orient="records")
      for item in df_dict:
         q_samples.append(item)

   ref_a_file = repo_path('stage2_fifter_q', 'outputs', 'ref_a_fusion.json')
   with open(ref_a_file, "r") as f:
      ref_a_data = json.load(f)

   samples = []
   used_q = []
   for id, item in enumerate(q_samples):
      if str(id) in ref_a_data:
         if item["question"] in used_q:
            continue
         new_item = item.copy()
         used_q.append(item["question"])
         ref_a_item = ref_a_data[str(id)]
         new_item.update(ref_a_item)
         samples.append({
            "url": new_item["url"],
            "task_type": new_item["task_type"],
            "question": new_item["question"],
            "answer": None,
            "reference_answer": new_item["reference_answer"],
            "question_span": new_item["question_span"],
            "ref_answer_span": new_item["answer_span"],
            "reasoning": new_item["reasoning"],
            "uncertainty": new_item["uncertainty"],
            "id": id
         })
   df = pd.DataFrame(samples)
   save_path = repo_path('stage2_fifter_q', 'outputs')
   os.makedirs(save_path, exist_ok=True)
   df.to_csv(os.path.join(save_path, f"anno_qa_ref_fusion.csv"), index=False)
   print(f"save to anno_qa_ref_fusion.csv")

   #random shuffle
   df = df.sample(frac=1).reset_index(drop=True)
   #按照task_type类型，每类选出40条数据
   task_type_df = df.groupby("task_type").apply(lambda x: x.sample(20))

   # INSERT_YOUR_CODE
   # 将每个task_type类别的数据均分成两份，然后合并所有类别的分组
   grouped = []
   for task_type, group_df in task_type_df.groupby(level=0):
      group_df = group_df.reset_index(drop=True)
      n = len(group_df)
      half = n // 2
      group1 = group_df.iloc[:half]
      group2 = group_df.iloc[half:]
      grouped.append((group1, group2))

   # 合并每个类别的第1份/第2份
   task_type_df_1 = pd.concat([g[0] for g in grouped], ignore_index=True)
   task_type_df_2 = pd.concat([g[1] for g in grouped], ignore_index=True)



   #保存到xlsx
   task_type_df_1.to_excel(os.path.join(save_path, f"anno_qa_ref_fusion_1_new.xlsx"), index=False)
   task_type_df_2.to_excel(os.path.join(save_path, f"anno_qa_ref_fusion_2_new.xlsx"), index=False)
   print(f"save to anno_qa_ref_fusion_1_new.xlsx and anno_qa_ref_fusion_2_new.xlsx")

      

      

    