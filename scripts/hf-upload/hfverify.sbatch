#!/bin/bash
# 1017-test-xhard5-12per：HF bucket 读回校验，Great Lakes standard 分区纯 CPU job，直接 sbatch、跑完即退。
# 规约见 AgentMetaRules greatlakes.md「HF 上传校验 job」：不带 GPU、流式读回不落盘、先 --limit 1 冒烟、
# 日志落 NFS、末行 HF_VERIFY= 后追加 EXIT_CODE=。
#
# 提交（从 aspen ssh 进登录节点的交互 shell，先 export HF_TOKEN，不写进命令行参数、不落文件）：
#   mkdir -p /nfs/turbo/coe-chaijy-unreplicated/hongzefu/logs/testx-hfverify
#   sbatch --export=ALL --account=chaijy2 --partition=standard --nodes=1 --ntasks-per-node=1 \
#     --cpus-per-task=4 --mem=8G --time=12:00:00 --job-name=testx-hfverify \
#     --output=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/logs/testx-hfverify/%x_%j.out \
#     <HFV_DIR>/hfverify.sbatch --limit 1        # 冒烟；去掉 --limit 1 即全量
# 命令行之外的参数原样传给 verify_bucket.py。下面 #SBATCH 默认值与上述规格一致，命令行显式给出的优先。
#
# 计算节点只看得到 NFS：HFV_DIR 下须放好 verify_bucket.py 与 manifest/{SHA256SUMS,MANIFEST.tsv}（主会话事先 rsync）。
# python 用 NFS 上 uv managed 的解释器（greatlakes.md「venv 可移植性」）；校验脚本只用标准库，不需要 venv、不做 uv sync。
#SBATCH --account=chaijy2
#SBATCH --partition=standard
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=12:00:00
#SBATCH --job-name=testx-hfverify
#SBATCH --export=ALL
#SBATCH --output=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/logs/testx-hfverify/%x_%j.out

set -o pipefail
export PYTHONUNBUFFERED=1

HFV_DIR="${HFV_DIR:-/nfs/turbo/coe-chaijy-unreplicated/hongzefu/testx-hfverify}"
HFV_MANIFEST_DIR="${HFV_MANIFEST_DIR:-$HFV_DIR/manifest}"
HFV_BUCKET="${HFV_BUCKET:-HongzeFu/robomme-test-xhard5-12per-1017}"
HFV_PY="${HFV_PY:-/nfs/turbo/coe-chaijy-unreplicated/hongzefu/uv-python/cpython-3.11.14-linux-x86_64-gnu/bin/python3.11}"

echo "开始时间(UTC): $(date -u +%FT%TZ)  节点: $(hostname)  JobID: ${SLURM_JOB_ID:-无}"
echo "HFV_DIR=$HFV_DIR  manifest=$HFV_MANIFEST_DIR  bucket=$HFV_BUCKET  python=$HFV_PY  参数: $*"

if [ -z "${HF_TOKEN:-}" ]; then
  echo "错误: 环境变量 HF_TOKEN 未带入（提交端先 export HF_TOKEN 并用 --export=ALL）"
  echo "HF_VERIFY=FAIL objects=0 sha_match=0 size_equal=0 missing=0 extra=0 mismatch=0 checked=0"
  echo "EXIT_CODE=2"
  exit 2
fi

cd "$HFV_DIR" || { echo "错误: 进不去 $HFV_DIR"; echo "EXIT_CODE=2"; exit 2; }
"$HFV_PY" -I "$HFV_DIR/verify_bucket.py" --bucket "$HFV_BUCKET" --manifest-dir "$HFV_MANIFEST_DIR" --workers "${SLURM_CPUS_PER_TASK:-4}" "$@"
rc=$?
echo "结束时间(UTC): $(date -u +%FT%TZ)"
echo "EXIT_CODE=$rc"
exit "$rc"
