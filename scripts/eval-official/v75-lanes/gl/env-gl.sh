#!/bin/bash
# 2.1 GL 车道（计算节点内执行）：用法 env-gl.sh <cell> [额外参数...]
set -uo pipefail
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
WT=$N/wt/2176a0e3
CELL=$1; shift
cd "$WT" || { echo "EXIT_CODE=97"; exit 97; }
for f in /usr/share/vulkan/icd.d/nvidia_icd.x86_64.json /usr/share/vulkan/icd.d/nvidia_icd.json /etc/vulkan/icd.d/nvidia_icd.json; do [ -f "$f" ] && { export VK_ICD_FILENAMES=$f; break; }; done
export __GLX_VENDOR_LIBRARY_NAME=nvidia PYTHONUNBUFFERED=1
echo "GL_LANE cell=$CELL host=$(hostname) commit=$(git rev-parse HEAD) vk=${VK_ICD_FILENAMES:-none} gpu=$(nvidia-smi --query-gpu=name,uuid,driver_version --format=csv,noheader) $(date -Is)"
"$WT/.venv/bin/python" scripts/parity/hard_regression.py env-digest --cell "$CELL" --identities $N/identities-small48.json --out $N/env "$@"
echo "STEP_EXIT $CELL rc=$?"
