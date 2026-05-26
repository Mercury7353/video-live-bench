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

sys_prompt = """
You are a rigorous Video QA annotation assistant. Your job is to generate a high-quality reference answer for the given question based ONLY on the provided video content (subtitles/ASR/keyframe captions/event logs, etc.), and to provide strict temporal localization and evidence-based explanation.

[GOALS]
1) Generate a concise and unambiguous reference answer (reference_answer) that matches the question exactly, without adding any information not present in the video content.
2) Provide the question temporal span (question_span): the minimal time segment(s) a viewer must watch to understand the event/condition/object being asked about.
3) Provide the answer temporal span (answer_span): the key evidence time segment(s) that directly support the answer (can be a subset of question_span or a different segment).
4) Provide reasoning: explain how the evidence supports the answer, and you MUST cite specific timestamps/spans as evidence.
5) If the video content is insufficient to determine the answer, output "Unanswerable" and explain what critical evidence is missing; still provide the most relevant spans.

[CRITICAL CONSTRAINTS]
- You must answer ONLY using the provided video content. No world knowledge completion, no guessing, no hallucination.
- If the question requires multiple steps/events, question_span must cover ALL necessary events; answer_span should include ONLY the key evidence segments.
- Spans should be as tight as possible (minimal coverage). If evidence is scattered, you may return multiple spans (array of spans).
- Output MUST be valid JSON ONLY (no extra text). All fields must be present.
- If the question includes temporal relations such as "before/after/while/until/start/end", reflect the correct event order in reasoning and ensure spans are consistent.

[REFERENCE ANSWER LENGTH CONSTRAINT (MUST FOLLOW)]
- reference_answer must be short and evaluation-friendly. Do NOT write long sentences.
- Default limit: <= 12 English words (or <= 20 Chinese characters).
- If a short phrase with multiple components is necessary to fully answer, allow at most ONE sentence, <= 18 English words (or <= 30 Chinese characters).
- Do NOT include reasons, evidence, timestamps, or any explanation in reference_answer. Put those ONLY in reasoning.

[OUTPUT JSON FORMAT]
{
  "question": "{question}",
  "reference_answer": "... or 'Unanswerable'",
  "question_span": [[start, end], ...],
  "answer_span": [[start, end], ...],
  "reasoning": "Evidence-based explanation with timestamps/spans",
  "uncertainty": {
    "is_answerable": true/false,
    "missing_info": "If unanswerable, what key info is missing; otherwise empty string"
  }
}

Now complete the task: generate the OUTPUT JSON based on the INPUT.
"""



def anno_video_process(rank, num_processes, api_keys_group, model_name, sys_prompt, samples, save_path):
    """
    多进程处理视频标注任务（优化版）
    每个 API key 每分钟仅调用一次，防止因视频输入触发 TPM 限制。
    """

    api_keys = api_keys_group[rank]
    random.shuffle(api_keys)  # 随机打乱 key 顺序，避免总是使用第一个 key
    num_api_keys = len(api_keys)
    interval = 5  # 每个 key 间隔 65 秒（视频输入token高，预留安全余量）

    for idx, sample in tqdm.tqdm(enumerate(samples), desc=f"Process {rank}"):
        # 按进程 rank 分配任务
        if idx % num_processes != rank:
            continue

        q_id = sample["q_id"]
        yt_id = sample["video_id"]
        chat = sample["chat"]
        json_name = f"{q_id}.json"
        save_file = os.path.join(save_path, json_name)

        # 已处理过则跳过
        if os.path.exists(os.path.join(save_path, json_name)):
            try:
                json_dict = json.load(open(os.path.join(save_path, json_name), "r", encoding="utf-8"))
                if json_dict.get("response_text") is not None:
                    continue
            except Exception:
                pass  # 文件损坏则重新处理

        video_url = f"https://www.youtube.com/watch?v={yt_id}"
        print(f"[INFO][Rank {rank}] Processing {video_url}")

        start_time = time.time()
        try:
            # 根据样本 idx 选择 API key
            api_key = api_keys[idx % num_api_keys]
            # client = genai.Client(api_key=api_key)  # 每次循环新建 client

            # response = client.models.generate_content(
            #     model=model_name,
            #     contents=types.Content(
            #         parts=[
            #             types.Part(text=sys_prompt),
            #             types.Part(file_data=types.FileData(file_uri=video_url)),
            #             types.Part(text=chat)
            #         ]
            #     )
            # )
            
            url = f"https://api.vectorengine.ai/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = json.dumps({
                  "contents": [
                     {
                        "role": "user",
                        "parts": [
                           {
                              "text": sys_prompt + " The videos that need to be annotated are as follows: "
                           },
                           {
                              "file_data": {
                                 "mime_type": "video/mp4",
                                 "file_uri": video_url
                              }
                           },
                           {
                              "text": chat
                           }
                        ]
                     }
                  ]
               })
            headers = {
            #    'Authorization': 'Bearer <token>',
               'Content-Type': 'application/json'
            }

            response = requests.request("POST", url, headers=headers, data=payload)

            if response.text is None:
                print("response.text is None")
                continue

            print("get_response")
            anno_info = {
                "video_id": yt_id,
                "model_name": model_name,
                "response_text": response.text,
                "question": sample["question"]
            }

            os.makedirs(save_path, exist_ok=True)
            with open(save_file, "w", encoding="utf-8") as f:
                json.dump(anno_info, f, ensure_ascii=False, indent=4)


        except Exception as e:
            print(e)
            time.sleep(10)  # 出错后等待 10 秒再继续
            continue

        # ---- 控制速率（关键部分）----
        end_time = time.time()
        elapsed = end_time - start_time
        sleep_time = max(0, interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

        
if __name__ == "__main__":


   all_api_keys = [
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",   
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      "REDACTED_VECTORENGINE_API_KEY",
      # "REDACTED_VECTORENGINE_API_KEY",
   ]

   num_api_per_group = 1


   num_worker = 16
   max_num_worker = len(all_api_keys) // num_api_per_group
   if num_worker > max_num_worker:
      num_worker = max_num_worker


   api_keys_group = []
   for i in range(num_worker):
      start = i * num_api_per_group
      end = (i + 1) * num_api_per_group
      api_keys_group.append(all_api_keys[start:end])

   print(f"Here are {num_worker} groups of api keys, each group has {num_api_per_group} api keys")
   ########################
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


   samples = []
   for id, item in enumerate(q_samples):
      text = f"Question Q: {item['question']}" + "\n" + "Please strictly follow the above requirements for annotation, and reply only in JSON format."
      samples.append({
         "video_id": item["video_id"],
         "q_id": id,
         "chat": text,
         "question": item["question"]
      })
   ##########################
   #多进程处理
   save_path = repo_path('stage2_fifter_q', 'outputs', 'ref_a')
   if not os.path.exists(save_path):
      os.makedirs(save_path)


   model_name = "gemini-3-flash-preview"
   # mp.spawn(anno_video_process, args=(num_worker, api_keys_group, model_name, sys_prompt, samples, save_path), nprocs=num_worker)

   while True:
      if len(os.listdir(save_path)) >= len(samples):
         break
      mp.spawn(anno_video_process, args=(num_worker, api_keys_group, model_name, sys_prompt, samples, save_path), nprocs=num_worker)

      

    