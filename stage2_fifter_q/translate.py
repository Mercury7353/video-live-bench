import pandas as pd
from openai import OpenAI
import time
import math
import json
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve()
while not (PROJECT_ROOT / "stage0_get_videoid").exists():
    if PROJECT_ROOT == PROJECT_ROOT.parent:
        raise RuntimeError("Could not locate project root")
    PROJECT_ROOT = PROJECT_ROOT.parent


def repo_path(*parts):
    return str(PROJECT_ROOT.joinpath(*parts))

client = OpenAI(api_key="REDACTED_OPENAI_API_KEY")

IN_PATH = repo_path('stage2_fifter_q', 'outputs', '20260205', 'anno_qa_ref_fusion_2_20260205.xlsx')
OUT_PATH = IN_PATH.replace(".xlsx", "_zh.xlsx")
COLS = ["question", "reference_answer", "reasoning"]   # ✅ 需要翻译的列名，改成你的多列
SUFFIX = "_zh"                            # 译文列后缀：content_zh / question_zh ...
BATCH_SIZE = 20                           # 5~20 常用
SLEEP_SEC = 0.1                           # 轻微限速保护
SKIP_IF_TARGET_NONEMPTY = True            # 目标列非空则跳过（方便断点续跑）

df = pd.read_excel(IN_PATH)



def normalize_cell_text(s: str) -> str:
    # 避免单元格内部换行破坏结构；先转义成 \n 文字，输出再还原
    return (s.replace("\r\n", "\n")
             .replace("\r", "\n")
             .replace("\n", "\\n")
             .strip())

def batch_translate(lines):
    payload = [normalize_cell_text(t) for t in lines]

    prompt = (
        "你是一个专业翻译器。把输入数组中的每个字符串翻译成自然准确的中文。\n"
        "要求：\n"
        "1) 输出必须是严格的 JSON 数组（不要代码块、不要解释）；\n"
        "2) 数组长度必须与输入一致；\n"
        "3) 每个元素仅包含对应条目的中文译文；\n"
        "4) 尽量保留特殊符号与转义序列，例如 \\n、{xxx}、<tag>、URL。\n"
        f"输入JSON：{json.dumps(payload, ensure_ascii=False)}"
    )

    resp = client.responses.create(
        model="gpt-5-mini",
        input=prompt,
    )

    text = resp.output_text.strip()
    out = json.loads(text)

    if not isinstance(out, list) or len(out) != len(lines):
        raise ValueError(
            f"JSON output mismatch: expected {len(lines)}, got "
            f"{len(out) if isinstance(out, list) else 'non-list'}"
        )

    # 还原 \n
    out = [t.replace("\\n", "\n") if isinstance(t, str) else "" for t in out]
    return out

def translate_column(df: pd.DataFrame, col: str):
    tgt_col = f"{col}{SUFFIX}"
    if tgt_col not in df.columns:
        df[tgt_col] = ""

    src = df[col].fillna("").astype(str)
    tgt = df[tgt_col].fillna("").astype(str)

    # 仅翻译需要翻译的行：源非空 + (可选)目标为空
    idx = []
    for i, s in enumerate(src):
        if not s.strip():
            continue
        if SKIP_IF_TARGET_NONEMPTY and tgt.iloc[i].strip():
            continue
        idx.append(i)

    result = df[tgt_col].fillna("").astype(str).tolist()
    if not idx:
        print(f"[INFO] {col}: nothing to translate.")
        return

    num_batches = math.ceil(len(idx) / BATCH_SIZE)
    for b in range(num_batches):
        batch_ids = idx[b * BATCH_SIZE:(b + 1) * BATCH_SIZE]
        batch_lines = [src.iloc[i] for i in batch_ids]

        try:
            zh = batch_translate(batch_lines)
            for i, z in zip(batch_ids, zh):
                result[i] = z
        except Exception as e:
            print(f"[WARN] {col} batch {b+1}/{num_batches} failed, fallback single. err={e}")
            for i in batch_ids:
                try:
                    result[i] = batch_translate([src.iloc[i]])[0]
                    time.sleep(SLEEP_SEC)
                except Exception as e2:
                    print(f"[ERROR] {col} row {i} failed: {e2}")
                    # 你也可以改成保留原文：result[i] = src.iloc[i]
                    result[i] = ""

        time.sleep(SLEEP_SEC)

    df[tgt_col] = result
    print(f"[OK] {col} -> {tgt_col}")

# 逐列翻译
for c in tqdm(COLS):
    if c not in tqdm(df.columns):
        print(f"[SKIP] column not found: {c}")
        continue
    translate_column(df, c)

df.to_excel(OUT_PATH, index=False)
print("Done:", OUT_PATH)