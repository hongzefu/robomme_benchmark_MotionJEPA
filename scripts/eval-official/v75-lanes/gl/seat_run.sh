#!/bin/bash
# GL 计算节点内：seat_run.sh <cond> <seat> <seat_idx> <policy> <det_report|on|off> [run_seat 额外参数...]
# MME 权重用 v75eval/ckpt 下的真实目录副本（run_seat 以 $MME_CKPT/.. 读 history_config，符号链接会解析到错误父目录）
# 输出先写节点 /tmp，结束后 rsync（只比内容，不比 NFS ACL/组权限）到 NFS stage/<cond>/<policy>/s-<seat> 并核对，再删节点副本；返回 run_seat 的 rc（暂存失败 rc=7）
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval
WT=$N/wt/${V75_WT:-30257b46}
COND=$1; SEAT=$2; IDX=$3; POL=$4; DETSRC=$5; shift 5
case "$DETSRC" in on|off) DET=$DETSRC;; *) DET=$(bash $N/lanes/det_of.sh "$DETSRC") || exit 9;; esac
cd "$WT" || exit 97
for f in /usr/share/vulkan/icd.d/nvidia_icd.x86_64.json /usr/share/vulkan/icd.d/nvidia_icd.json; do [ -f "$f" ] && { export VK_ICD_FILENAMES=$f; break; }; done
export MME_PY=$N/wt/2abf227d/third_party/mme-vla/.venv/bin/python SMVLA_PY=$N/venvs/smvla-env/bin/python BENCH_PY=$WT/.venv/bin/python
OUT=/tmp/v75-$COND-$SEAT-$POL-${SLURM_JOB_ID:-local}
mkdir -p "$OUT"
CPUS=$(python3 -c 'import os;print(",".join(map(str,sorted(os.sched_getaffinity(0)))))')
echo "SEAT_RUN_START cond=$COND seat=$SEAT idx=$IDX policy=$POL det=$DET host=$(hostname) out=$OUT $(date -Is)"
bash scripts/eval-official/run_seat.sh --seat "$SEAT" --seat-idx "$IDX" --gpu 0 --cpus "$CPUS" --cond "$COND" --out "$OUT" \
  --policies "$POL" --det "$DET" \
  --mme-ckpt /nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval/ckpt/mme/perceptual-framesamp-modul/79999 \
  --smvla-ckpt /nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA/checkpoints/simplememvla_robomme "$@"
rc=$?
DST=$N/stage/$COND/$POL/s-$SEAT; mkdir -p "$DST"
rsync -rt "$OUT/" "$DST/" && n=$(rsync -rc --dry-run --out-format="%n" "$OUT/" "$DST/" | { grep -v "/$" || true; } | wc -l) || n=err
if [ "$n" = 0 ]; then rm -rf "${OUT:?}"; echo "SEAT_STAGED cond=$COND seat=$SEAT policy=$POL dst=$DST"; else echo "SEAT_STAGE_FAIL n=$n"; rc=7; fi
echo "SEAT_RUN_END cond=$COND seat=$SEAT policy=$POL det=$DET rc=$rc $(date -Is)"
exit $rc
