#!/usr/bin/env bash
# 1017-test-xhard5-12per：算 sha256 清单 → 建私有 HF bucket → 上传五组产物与清单 → 列对象核对。
#
# 在 sled-aspen 本仓库主检出根目录、detached tmux（xh-testx-upload）里跑，日志三件套由 tmux 外层负责：
#   tmux new-session -d -s xh-testx-upload "set -o pipefail; PYTHONUNBUFFERED=1 bash scripts/hf-upload/upload_bucket.sh 2>&1 \
#     | tee artifacts/test-xhard/upload/upload.log; echo \"EXIT_CODE=\$?\" >> artifacts/test-xhard/upload/upload.log"
# HF_TOKEN 由交互 shell 事先 export（属于 HongzeFu 且有写权限），脚本只从环境变量读，不写进任何文件或参数。
#
# 可用环境变量覆盖：
#   BUCKET_ID   默认 HongzeFu/robomme-test-xhard5-12per-1017
#   GROUP_DIRS  空格分隔的产物目录，默认 artifacts/test-xhard/full/G1 … G5（续跑目录如 G5-r2 追加进来）
#   OUT_DIR     清单输出目录，默认 artifacts/test-xhard/upload
#   EXPECT_H5   默认 624
#   BATCH       每次 sync 提交的文件数，默认 10（一次提交上百个对象会在 commit 一步超时，见策略仓库 run_dataset400ep_export.sh 2026-09-08 实测）
#   HF_CLI      默认 uvx --python 3.11 --from huggingface_hub==1.30.0 hf（项目 .venv 的 1.4.1 未验证 buckets 子命令）
# 末行判定行：HF_UPLOAD=PASS|FAIL objects=<n> bytes=<n>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

BUCKET_ID="${BUCKET_ID:-HongzeFu/robomme-test-xhard5-12per-1017}"
BUCKET="hf://buckets/$BUCKET_ID"
GROUP_DIRS="${GROUP_DIRS:-artifacts/test-xhard/full/G1 artifacts/test-xhard/full/G2 artifacts/test-xhard/full/G3 artifacts/test-xhard/full/G4 artifacts/test-xhard/full/G5}"
OUT_DIR="${OUT_DIR:-artifacts/test-xhard/upload}"
EXPECT_H5="${EXPECT_H5:-624}"
BATCH="${BATCH:-10}"
read -r -a HF_CMD <<< "${HF_CLI:-uvx --python 3.11 --from huggingface_hub==1.30.0 hf}"
read -r -a DIRS <<< "$GROUP_DIRS"

fail() { echo "错误: $*"; echo "HF_UPLOAD=FAIL objects=0 bytes=0"; exit 1; }
hf() { "${HF_CMD[@]}" "$@"; }

[ -n "${HF_TOKEN:-}" ] || fail "环境变量 HF_TOKEN 未设置（在交互 shell 里 export 后再起 tmux）"
echo "开始时间(UTC): $(date -u +%FT%TZ)  主机: $(hostname)  HEAD: $(git rev-parse HEAD)"
echo "bucket: $BUCKET_ID  目录: ${DIRS[*]}  清单输出: $OUT_DIR"

# ---------------------------------------------------------------- 1. sha256 清单
echo "阶段1：算 sha256 清单"
uv run --no-sync python scripts/hf-upload/make_sha256sums.py --out-dir "$OUT_DIR" --expect-h5 "$EXPECT_H5" "${DIRS[@]}" \
  || fail "make_sha256sums.py 未通过"

# ---------------------------------------------------------------- 2. 建私有 bucket（已存在则继续）
echo "阶段2：建私有 bucket"
echo "账号: $(hf auth whoami 2>&1 | tr '\n' ' ')"
hf buckets create "$BUCKET_ID" --private --exist-ok || fail "hf buckets create 失败"
hf buckets info "$BUCKET_ID" || fail "hf buckets info 失败"

# ---------------------------------------------------------------- 3. 分批上传
# sync 对已存在且大小、mtime 一致的文件跳过，因此中断后重跑即续传；每批失败最多重试 8 次（间歇性 commit 超时，同上实测）。
sync_batch() {  # $1 = 本地目录；$2 = bucket 内前缀；$3.. = 本批文件名（作为 --include 精确匹配）
  local src="$1" dst="$2"; shift 2
  local args=() f attempt
  for f in "$@"; do args+=(--include "$f"); done
  for attempt in 1 2 3 4 5 6 7 8; do
    if hf buckets sync "$src" "$BUCKET/$dst" "${args[@]}"; then return 0; fi
    echo "  批 [$dst，$# 个] 第 $attempt 次失败，60s 后重试"; sleep 60
  done
  fail "批 [$dst：$*] 八次仍失败"
}

upload_dir() {  # 把一个目录下的直接子文件按 BATCH 个一批 sync 到同名前缀；子目录递归
  local src="$1" dst="$2"
  local files=() sub f i end
  while IFS= read -r f; do files+=("$f"); done < <(find "$src" -mindepth 1 -maxdepth 1 -type f -printf '%f\n' | LC_ALL=C sort)
  for ((i = 0; i < ${#files[@]}; i += BATCH)); do
    sync_batch "$src" "$dst" "${files[@]:i:BATCH}"
    end=$(( i + BATCH < ${#files[@]} ? i + BATCH : ${#files[@]} ))
    echo "  已传 $dst：$end/${#files[@]}"
  done
  while IFS= read -r sub; do upload_dir "$src/$sub" "$dst/$sub"; done < <(find "$src" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | LC_ALL=C sort)
}

echo "阶段3：上传产物"
for d in "${DIRS[@]}"; do
  echo " 组 $d"
  upload_dir "$d" "$(basename "$d")"
done
for f in SHA256SUMS MANIFEST.tsv; do
  ok=0
  for attempt in 1 2 3 4 5 6 7 8; do
    if hf buckets cp "$OUT_DIR/$f" "$BUCKET/$f"; then ok=1; break; fi
    echo "  $f 第 $attempt 次失败，60s 后重试"; sleep 60
  done
  [ "$ok" = 1 ] || fail "$f 八次仍失败"
done

# ---------------------------------------------------------------- 4. 列对象核对（不下载内容；内容读回由 GL job 做）
echo "阶段4：列对象核对"
set +e
list_out="$(uv run --no-sync python scripts/hf-upload/verify_bucket.py --bucket "$BUCKET_ID" --manifest-dir "$OUT_DIR" --list-only 2>&1)"
rc=$?
set -e
echo "$list_out"
list_line="$(printf '%s\n' "$list_out" | grep '^HF_LIST=' | tail -n 1 || true)"
objects="$(printf '%s\n' "$list_line" | sed -n 's/.* objects=\([0-9]*\).*/\1/p')"
bytes="$(printf '%s\n' "$list_line" | sed -n 's/.* bytes=\([0-9]*\).*/\1/p')"
echo "结束时间(UTC): $(date -u +%FT%TZ)"
if [ "$rc" = 0 ] && [[ "$list_line" == HF_LIST=PASS* ]]; then
  echo "HF_UPLOAD=PASS objects=${objects:-0} bytes=${bytes:-0}"
else
  echo "HF_UPLOAD=FAIL objects=${objects:-0} bytes=${bytes:-0}"
  exit 1
fi
