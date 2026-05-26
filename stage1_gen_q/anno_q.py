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
You are a “Video Benchmark Question Generator”.

## Task
Given:
1) VIDEO
2) REFERENCE_QUESTIONS: EXACTLY 10 reference questions labeled ref_q1 ~ ref_q10,
Generate:
3-5 new questions that STRICTLY imitate the style of the reference questions.

## Non-negotiable Requirements
### R1. Strict imitation ONLY (no creativity)
- You MUST reuse the SAME question types and wording patterns found in the reference questions.
- You may ONLY change the information point being asked about (swap the target event/object/attribute/time/order/count, etc.).

### Video-answerable ONLY
- Each question MUST be answerable using ONLY VIDEO_CONTENT.
- DO NOT require outside knowledge, guesses, or common-sense inference beyond what is explicitly shown or stated.
- DO NOT ask about audio information.

### Output format (JSON only)
- Output JSON ONLY. No markdown, no extra text, no explanations.
- The JSON MUST follow the schema exactly:
{
  "generated_questions": [
    {
      "question": "string",
      "matched_reference_style": "ref_q1|ref_q2|...|ref_q10"
    }
  ]
}
- Generate EXACTLY 3-5 items in "generated_questions".
- "matched_reference_style" MUST be the single reference question whose phrasing template you copied most closely.
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

        yt_id = sample["video_id"]
        chat = sample["chat"]
        json_name = f"{yt_id}.json"
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
                "ref_q": sample["ref_q"]
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
   parser = argparse.ArgumentParser()
   parser.add_argument("--qa_json_path", type=str, default=None)
   parser.add_argument("--save_path", type=str, default=None)
   args = parser.parse_args()

   if args.qa_json_path is None:
      raise ValueError("qa_json_path is required")

   with open(args.qa_json_path, "r", encoding="utf-8") as f:
      qa_data = json.load(f)
   file_name = os.path.basename(args.qa_json_path)
   task_type = file_name.split(".")[0]
   
   ref_q_list = [item["question"] for item in qa_data]

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
   video_json_path = repo_path('stage0_get_videoid', 's1_fifter_videos', 'outputs', 'selected_videos_balance_category_v2_new.json')
   with open(video_json_path, "r", encoding="utf-8") as f:
      video_data = json.load(f)

   random.shuffle(video_data)
   video_data = video_data[:300]

   samples = []
   for item in video_data:
      yt_id = item["videoId"]
      ref_q = random.sample(ref_q_list, 10)

      ref_q_str = "The task type is " + task_type + ". Here are 10 reference questions: " + "\n".join([f"ref_q{i+1}: {q}" for i, q in enumerate(ref_q)])

      text = "Please strictly follow the above requirements for annotation, and reply only in JSON format."
      samples.append({
         "video_id": yt_id,
         "chat": ref_q_str + text,
         "ref_q": ref_q
      })
   random.shuffle(samples)
   ##########################
   #多进程处理
   save_path = args.save_path
   if not os.path.exists(save_path):
      os.makedirs(save_path)


   model_name = "gemini-3-flash-preview"
   # mp.spawn(anno_video_process, args=(num_worker, api_keys_group, model_name, sys_prompt, samples, save_path), nprocs=num_worker)

   while True:
      if len(os.listdir(save_path)) >= 200:
         break
      mp.spawn(anno_video_process, args=(num_worker, api_keys_group, model_name, sys_prompt, samples, save_path), nprocs=num_worker)

      

    