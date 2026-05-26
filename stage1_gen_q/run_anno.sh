#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# TASK_NAME="Counting"
# TASK_PATH="$SCRIPT_DIR/question_pool/${TASK_NAME}.json"
# SAVE_PATH="$SCRIPT_DIR/anno_q/${TASK_NAME}"

# python anno_q.py \
#     --qa_json_path $TASK_PATH \
#     --save_path $SAVE_PATH


# TASK_NAME="Spatial"
# TASK_PATH="$SCRIPT_DIR/question_pool/${TASK_NAME}.json"
# SAVE_PATH="$SCRIPT_DIR/anno_q/${TASK_NAME}"

# python anno_q.py \
#     --qa_json_path $TASK_PATH \
#     --save_path $SAVE_PATH

# TASK_NAME="OCR"
# TASK_PATH="$SCRIPT_DIR/question_pool/${TASK_NAME}.json"
# SAVE_PATH="$SCRIPT_DIR/anno_q/${TASK_NAME}"

# python anno_q.py \
#     --qa_json_path $TASK_PATH \
#     --save_path $SAVE_PATH

TASK_NAME="Perception"
TASK_PATH="$SCRIPT_DIR/question_pool/${TASK_NAME}.json"
SAVE_PATH="$SCRIPT_DIR/anno_q/${TASK_NAME}"

python anno_q.py \
    --qa_json_path $TASK_PATH \
    --save_path $SAVE_PATH


# TASK_NAME="Reasoning"
# TASK_PATH="$SCRIPT_DIR/question_pool/${TASK_NAME}.json"
# SAVE_PATH="$SCRIPT_DIR/anno_q/${TASK_NAME}"

# python anno_q.py \
#     --qa_json_path $TASK_PATH \
#     --save_path $SAVE_PATH
