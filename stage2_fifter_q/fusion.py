import os
import json
import tqdm
import pandas as pd
import re

import json

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent


def repo_path(*parts):
    return str(PROJECT_ROOT.joinpath(*parts))

def try_fix(s: str) -> str:

    # 2) json5
    try:
        import json5
        obj = json5.loads(s)
        return obj
    except Exception:
        print(f"fail to fix {s}")
        pass

    # 3) dirtyjson
    try:
        import dirtyjson
        obj = dirtyjson.loads(s)
        return obj
    except Exception:
        print(f"fail to fix {s}")
        pass

    

def find_json_in_text(text):
    #获取text中```json和```之间的内容
    json_str = re.search(r"```json(.*)```", text)
    if json_str is not None:
        return json_str.group(1).strip()
    json_str = re.search(r"```json(.*)\\n\]", text)
    if json_str is not None:
        return json_str.group(1).strip()
    return None

def find_list_in_text(text):
    #获取text中[\\n和\\n]之间的内容
    list_str = re.search(r"\[\\n(.*)\\n\]", text)
    if list_str is None:
        return None
    try:
        return list_str.group(1).strip()
    except:
        return None

import re
import json

import re
import json

TIME_PATTERN = re.compile(
    r'(?<!")\b\d{1,2}:\d{2}(?::\d{2})?\b(?!")'
)

def fix_time_strings(raw_text: str) -> dict:
    """
    仅修复 question_span 和 answer_span 中未加引号的时间
    支持多个时间窗口（嵌套数组）
    """

    def fix_span(key: str, text: str) -> str:
        key_pos = text.find(f'"{key}"')
        if key_pos == -1:
            return text

        # 找到冒号后的第一个 [
        start = text.find('[', key_pos)
        if start == -1:
            return text

        # 括号计数，找到完整 span 数组
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '[':
                depth += 1
            elif text[i] == ']':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        else:
            return text  # 括号不匹配，直接返回

        span_block = text[start:end]

        fixed_block = TIME_PATTERN.sub(
            lambda m: f'"{m.group(0)}"', span_block
        )

        return text[:start] + fixed_block + text[end:]

    # 依次修复两个 key
    fixed_text = raw_text
    for key in ("question_span", "answer_span"):
        fixed_text = fix_span(key, fixed_text)

    return fixed_text

if __name__ == "__main__":
    annos_path = repo_path('stage2_fifter_q', 'outputs', 'ref_a')
    task_type = os.path.basename(annos_path)

    data = {}
    num_no_json = 0
    for anno_file in tqdm.tqdm(os.listdir(annos_path)):
        video_id = anno_file.split(".")[0]
        anno_file = os.path.join(annos_path, anno_file)
        with open(anno_file, "r", encoding="utf-8") as f:
            anno_info = json.load(f)

        response_text = anno_info["response_text"]
        output = json.loads(response_text)
        
        try:
            response_text = output["candidates"][0]['content']['parts'][1]['text']
        except:
            print(f"fail to output[candidates][0]['content']['parts'][1]['text']")
            continue

        try:
            clean_text = response_text.strip().replace("```json", "").replace("```", "").strip()
            clean_text = clean_text.replace("\n", " ")
        except:
            print(f"fail to clean text {video_id}")
            continue
        is_fixed = False
        try:
            response_text = json.loads(clean_text)
        except:
            is_fixed = True
        if is_fixed:
            clean_text = fix_time_strings(clean_text)
            try:
                response_text = json.loads(clean_text)
            except:
                print(f"fail to load json {video_id} after fix time strings")
                print(clean_text)
                continue
        
        id = os.path.basename(anno_file).split(".")[0]
        data[id] = response_text
    print(f"num_no_json: {num_no_json}")
    print(len(data))

    save_path = str(PROJECT_ROOT / f"stage2_fifter_q/outputs/ref_a_fusion.json")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"save to {save_path}")