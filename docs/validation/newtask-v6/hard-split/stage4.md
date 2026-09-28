# 拆包阶段 4：三侧对拍（A40@greatlakes，2026-09-28）

计划：`0927-robomme-hard-layered-plan.md` 第一部分 §5.4、§6.1，第二部分 §3.1、§3.2、§3.4。

## 一、判定行（全部原文）

```text
SHARD_SMOKE=PASS side=O tier=native rows=1 recorded=1 success=1 runner_exit=0 gpu=NVIDIA A40 mover_errors=0
SHARD_SMOKE=PASS side=P tier=native rows=1 recorded=1 success=1 runner_exit=0 gpu=NVIDIA A40 mover_errors=0
SHARD_SMOKE=PASS side=H tier=native rows=1 recorded=1 success=1 runner_exit=0 gpu=NVIDIA A40 mover_errors=0
GENERATE=PASS side=O tier=native rows=144 recorded=144 success=144 runner_exit=0 gpu=NVIDIA A40 mover_errors=0
GENERATE=PASS side=P tier=native rows=144 recorded=144 success=144 runner_exit=0 gpu=NVIDIA A40 mover_errors=0
GENERATE=PASS side=H tier=native rows=144 recorded=144 success=144 runner_exit=0 gpu=NVIDIA A40 mover_errors=0
GENERATE=FAIL side=H tier=xhard rows=165 recorded=0 success=0 runner_exit=1 gpu=NVIDIA A40 mover_errors=0   （首次，被自家预写文件拦下、一局未跑，见三①）
GENERATE=PASS side=H tier=xhard rows=165 recorded=165 success=165 runner_exit=0 gpu=NVIDIA A40 mover_errors=0   （H-xhard-r2，12.208.2）
HARD_RESET_REPLAY=PASS resets=55 replay=55 injected_mismatch=0 recorded_drift=6 max_abs=1.2e-07 goal_mismatch=0 errors=0 shape=13x3+16
PULL_DONE=PASS segments=7 failed=[]      （每段 PULL_SEGMENT=PASS sha_bad=0 nfs_leftover_media=0）
S4_IMPORT=PASS rows=165 sha_mismatch=0   （P 侧 xhard = S4 交付存档，只读 symlink）

PARITY_TOL_CALIB=PASS pair=O:P n=144 action_p95=0 action_max=0.0275 state_max=0.0274 image_mad_max=0.144 frames_max=0 tol_file_sha=9600a1ed6d8c
PARITY_O_P=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 tol=PASS action_max=0.0275/0.0413 state_max=0.0274/0.0411 image_mad=0.144/1 frames_max=0/5 sha_equal=143 frames_equal=144 binding_ok=144 shape=16x3x3
PARITY_P_H=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 tol=PASS action_max=0.0275/0.0413 state_max=0.0274/0.0411 image_mad=0.144/1 frames_max=0/5 sha_equal=143 frames_equal=144 binding_ok=144 shape=16x3x3
PARITY_O_H=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 tol=PASS action_max=0/0.0413 state_max=0/0.0411 image_mad=0/1 frames_max=0/5 sha_equal=144 frames_equal=144 binding_ok=144 shape=16x3x3
PARITY_P_H=PASS tier=xhard compared=165 identity_equal=165 setup_equal=165 schema_equal=165 success_equal=165 both_success=165 tol=PASS action_max=0/0.0413 state_max=0/0.0411 image_mad=0/1 frames_max=0/5 sha_equal=165 frames_equal=165 binding_ok=165 shape=13x3x3+16x3
ENV_PACKAGE_BINDING=PASS sides=3 O=robomme P=robomme H=robomme_hard mismatch=0
PARITY_REFERENCE=INFO pair=O:P / P:H native first_divergence_n=1（PickHighlight/hard/seed 12300，第 549 步起，两侧帧数同为 643）；O:H native、P:H xhard first_divergence_n=0
BUCKET_SYNC=FAIL sides=0 objects=0 readback_sha_equal=0 reason=HF_403_billing   （见三④，停止类，置顶报告）
HOLD_RELEASE=PASS released=62126060,62126061,62018665 kept=62126062 others_unchanged=1
```

**读法**：原三档 O↔H 144 对、xhard P(S4)↔H 165 对**全部逐字节相同**；O↔P、P↔H 各有同一对（PickHighlight hard seed 12300）在 P 侧那次运行中从第 549 步分叉，最大动作差 0.0275 rad、图像平均差 0.144，而 O 与 H 在该身份上逐字节相同——分叉只来自 P 侧那次运行的 RRT 墙钟噪声，不是代码差异。判定口径是「输入绑定、结构与任务成功一致，差异在标定容差内」（U-1、U-19），字节相等数只作参考。

## 二、容差标定（U-22：主代理自定，最终报告交用户）

`scripts/configs/hard-parity-tolerances.json`（sha256 前缀 `9600a1ed6d8c`），规则「O:P 最大值 × 1.5（帧数向上取整），下界 0.005/0.005/1.0/5，合理性上界 0.05/0.05/10/200」：

| 指标 | O:P p95 | O:P 最大值 | 所定阈值 | 说明 |
|---|---|---|---|---|
| `action_max`（rad） | 0 | 0.0275 | 0.0413 | 最大值 × 1.5，未触上界 0.05 |
| `state_max` | 0 | 0.0274 | 0.0411 | 同上 |
| `image_mad`（0～255） | 0 | 0.144 | 1.0 | 取下界 |
| `frames_max` | 0 | 0 | 5 | 取下界 |

144 对里 143 对逐字节相同，p95 全为 0，唯一非零样本即 PickHighlight/12300。标定只有这一个非零样本，阈值偏宽／偏窄的风险见计划风险 24、盲区 ⑭；本轮 P:H 与 O:H 的实测最大值都不超过该样本。

## 三、计划外事件与处置

1. **H-xhard 首次被自家预写文件拦下**：`hard_parity generate` 先在输出目录写 `launch-*.json`／`_identities.jsonl`，再调 `generate_h5 --mode replay`，后者见目录非空即拒跑；一局未跑、不耗预算。12.208.2 把拒跑条件改为「已有 `episodes/` 或 `_rounds/`」，以新段名 `H-xhard-r2` 在 `b1afc804` 重跑（launch 记录如实写该 commit；原三档三侧在 `34a1ceab` 生成，两者 `src/` 零差异）。切 GL 克隆到 `b1afc804` 时片 C 的回注 reset 正在同一克隆运行，它不导入 `_rollout.py`、模块早已加载，不受影响。
2. **首次 O:P 判定行 FAIL（记录缺陷）**：`binding_ok=82`——O／P 侧 identities 行运行中逐局写入，拿不到 runner 结束后才写进 `results.json` 的 `robomme_module`，62 行为空。修 `hard_parity.py::side_lines` 从该侧 `_runner/results.json` 补齐（runner 探针原值，不覆盖已有值）后重跑 O:P，判定层其余各项与首次完全相同。首次原文：`PARITY_O_P=FAIL tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 tol=PASS … sha_equal=143 frames_equal=144 binding_ok=82 shape=16x3x3 severity=none tol_over=0`。
3. **bucket 过滤写法错误**：`hf buckets sync --exclude "*" --include …` 在 1.8.0 下把全部排除（dry-run `uploads=0`），只给 `--include` 才是白名单；读回时对象不存在 `cp` 只警告不报错，已改为计入 mismatch。
4. **BUCKET_SYNC 被 HF 拒绝（停止类，未解决）**：修正过滤后上传 O 侧原三档到约 44.6 GB / 46.2 GB 时报 `403 Forbidden: You need to setup automatic credit recharge in order to upload more data`。这是账户计费设置，主代理不触碰。bucket `HongzeFu/robomme-hard-parity` 现有 O 侧原三档部分对象 100 个、28.6 GB（`O-1fadc0e-a40/native/`，只增不改、原样保留、**未读回核对**）；P／H 两侧与 xhard 均未上传。三侧全部 h5 在本机 `/data`（O/P/H native 各 49 G、H xhard 112 G；P xhard 为 S4 存档 symlink），逐局 sha 已核，对拍判定不依赖 bucket。候选处置：用户开通自动充值（或清理其它 bucket 腾额度）后用 `hard_parity.py publish --resume-upload` 续传并读回；或由用户决定不再持久化到 bucket。

## 四、运行记录

| 片 | job／节点 | 段 | 时间（EDT） |
|---|---|---|---|
| A | 62126060／gl1517 | smoke-O-native → O-native（1fadc0ec worktree，官方 `_worker`） | 01:32:54～01:59:13 |
| A2 | 62126060／gl1517 | H-xhard-r2（`generate_h5 --mode replay`，镜像 worker + robomme_hard） | 02:00:49～03:02:04 |
| B | 62126061／gl1504 | smoke-P-native → P-native（tag pre-hard-split worktree，官方 `_worker`） | 01:32:55～01:59:47 |
| C | 62126062／gl1506 | smoke-H-native → H-native（`--force-mirror`）→ reset-replay 55 | 01:32:54～02:09:01 |

四侧统一：NVIDIA A40，驱动 595.71.05，python 3.11.14、mani_skill 3.0.0b21、sapien 3.0.2、torch 2.9.1、CUDA 12.8；每片 `srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared`，16 worker，`OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`。GL 克隆：NFS 新 clone `robomme_benchmark-hs-gl`（U-17，旧克隆 `robomme_benchmark-newtask-gl` 未碰）＋ worktree `-p`（7c7118fa）、`-o`（1fadc0ec，从官方远端按 sha 取得、tree `3006988f` 核对），三处 `git status --short` 均为空；`uv sync --frozen` 用 NFS 上的 cpython 3.11.14（109 包）。

流转：节点 `/tmp`（300 G 可用）→ 逐局 sha 后复制到 NFS `hs-stage/<段>/` 并写 `SHIPPED` → sled-vail `hs-pull` 拉回 `artifacts/newtask-v6/hard-split/h5/<段>/`，核 sha 后删 NFS 大文件；七段全部 `nfs_leftover_media=0`。

tmux 会话清单：GL 登录节点 gl-login3 `hs-uvsync`、`hs-shardA`、`hs-shardB`、`hs-shardC`、`hs-shardA2`、`hs-mme-env`（均已自行退出）；本机 `hs-migrate`、`hs-pull`、`hs-cmp-op`、`hs-cmp-op2`、`hs-cmp-PH`、`hs-cmp-OH`、`hs-cmp-PHx`（自行退出）、`hs-publish`、`hs-publish2`（按清单 `kill-session -t '=名'`，删前删后 `tmux ls` 差集恰为目标）。

占位 job 释放（删前删后 `squeue -u hongzefu`；四个 job 内只有 `batch`／`extern` 步骤）：

```text
BEFORE: 62126062 RUNNING gl1506；62126061 RUNNING gl1504；62126060 RUNNING gl1517；62018665 RUNNING gl1510
AFTER:  62126062 hs-hold-20260927-3 RUNNING 1-17:27:31 gl1506 192G 16 gres/gpu:1
```

随后按 U-9／E-22 提交 10 个评估占位 job（各 1 GPU／1 CPU／32 G／48 h）：`62177614`～`62177623`（`hs-eval-1`～`hs-eval-10`）。

## 五、预算计数（P3 / U-14，批准 rollout ≤ 638、reset ≤ 715）

| 项 | 乘式 | rollout | reset |
|---|---|---|---|
| 本机冒烟（阶段 1～3） | 见 stage1～stage3 | 8 | 纯 reset 6 |
| 片前冒烟 | 3 片 × 1 局 | 3 | — |
| O／P／H 原三档 | 3 侧 × 16 任务 × 3 档（easy/medium/hard）× 3 局 = 432 | 432 | — |
| H xhard | xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165 | 165 | — |
| H xhard 首次（被拦） | 0 局 | 0 | — |
| 基础设施重跑 | — | 0 | — |
| 回注 reset | xhard1/2/3 各 13 任务 × 1 + xhard4 16 任务 × 1 = 55 | 0 | 55 |
| **累计** | | **608／638** | **纯 reset 61 + rollout 各 1 次 608 = 669／715** |

## 六、归档

`records/stage4/`：四个比对的 `h5_pairs.jsonl`（逐身份四项指标与首个分叉步）与 `summary.json`、`reset-replay.jsonl`（55 局逐局 `spec_binding` 与 `goal_equal`）、四片日志清洗版 `shard_*.summary.log`。h5 本体（约 260 G）留在 `/data`，删不删交用户（计划 §5.4 收尾）。

## 七、片脚本原文（NFS `hs-scripts/`，不进 git）

`shard_common.sh`：

```bash
#!/bin/bash
# 阶段 4 片脚本公共部分（0927 计划第二部分 §3.2）：在占位 job 的 srun 步骤内顺序跑若干段，每段写 EXIT_CODE=。
# 红线 R15：生成期间不另起申请 GPU 的 srun；sha 与搬运在生成步骤内完成。
set -u
N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu
REPO=$N/robomme_benchmark-hs-gl
MANIFEST=$REPO/scripts/configs/newtask-v3/subset_manifest.json
S4=$N/hs-scripts/final-delivery.json
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 UV_CACHE_DIR=$HOME/.cache/uv
unset PYTHONPATH
cd "$REPO" || exit 90
echo "SHARD_HOST $(hostname) job=${SLURM_JOB_ID:-none} step=${SLURM_STEP_ID:-none} $(date -Is)"
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
nvidia-smi --query-gpu=name --format=csv,noheader | grep -q A40 || { echo "GPU_ASSERT=FAIL 不是 A40"; echo "EXIT_CODE=91"; exit 91; }
df -h /tmp | tail -1
avail=$(df --output=avail -BG /tmp | tail -1 | tr -dc 0-9); [ "$avail" -ge 160 ] || { echo "TMP_ASSERT=FAIL avail=${avail}G <160G"; echo "EXIT_CODE=92"; exit 92; }
[ "$(git -C $REPO status --short | wc -l)" = 0 ] || { echo "REPO_DIRTY=FAIL"; echo "EXIT_CODE=93"; exit 93; }
uv run --frozen --no-sync python -c "import robomme, robomme_hard; print(\"IMPORT_CHECK robomme=\" + robomme.__file__ + \" robomme_hard=\" + robomme_hard.__file__)" || { echo "IMPORT_CHECK=FAIL"; echo "EXIT_CODE=94"; exit 94; }
mkdir -p /tmp/hongzefu-hs
gen() {  # gen <段名> <side> <tier> <src-root> [额外参数…]
  local name=$1 side=$2 tier=$3 src=$4; shift 4
  local manifest=$MANIFEST; [ "$tier" = xhard ] && manifest=$S4
  local out=/tmp/hongzefu-hs/$name stage=$N/hs-stage/$name
  echo "SEGMENT_START $name $(date -Is)"
  uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side $side --tier $tier \
      --manifest $manifest --src-root $src --workers 16 --gpu 0 --out $out --stage $stage "$@"
  local code=$?
  mkdir -p $stage && rsync -a --exclude='*.h5' --exclude='*.mp4' $out/ $stage/ && rm -rf $out
  touch $stage/SEGMENT_DONE
  echo "SEGMENT $name EXIT_CODE=$code $(date -Is)"
  return $code
}
```

`shard_A.sh`：

```bash
#!/bin/bash
# 片 A（62126060）：O 原三档 16×3×3 → H xhard（xhard1/2/3 各 13 任务 × 3 + xhard4 16 任务 × 3，replay）
source /nfs/turbo/coe-chaijy-unreplicated/hongzefu/hs-scripts/shard_common.sh
O=$N/robomme_benchmark-hs-gl-o
gen smoke-O-native O native $O --smoke 1 || { echo "EXIT_CODE=1"; exit 1; }
gen O-native O native $O || { echo "EXIT_CODE=2"; exit 2; }
gen H-xhard H xhard $REPO || { echo "EXIT_CODE=3"; exit 3; }
echo "SHARD_A 全部完成"; echo "EXIT_CODE=0"
```

`shard_A2.sh`：

```bash
#!/bin/bash
# 片 A 续：H xhard（xhard1/2/3 各 13 任务 × 3 + xhard4 16 任务 × 3 = 165，replay）；首次 H-xhard 段被自家预写文件拦下未跑，12.208.2 修复后重跑
source /nfs/turbo/coe-chaijy-unreplicated/hongzefu/hs-scripts/shard_common.sh
gen H-xhard-r2 H xhard $REPO || { echo "EXIT_CODE=3"; exit 3; }
echo "SHARD_A2 全部完成"; echo "EXIT_CODE=0"
```

`shard_B.sh`：

```bash
#!/bin/bash
# 片 B（62126061）：P 原三档 16×3×3（tag pre-hard-split worktree）
source /nfs/turbo/coe-chaijy-unreplicated/hongzefu/hs-scripts/shard_common.sh
P=$N/robomme_benchmark-hs-gl-p
gen smoke-P-native P native $P --smoke 1 || { echo "EXIT_CODE=1"; exit 1; }
gen P-native P native $P || { echo "EXIT_CODE=2"; exit 2; }
echo "SHARD_B 全部完成"; echo "EXIT_CODE=0"
```

`shard_C.sh`：

```bash
#!/bin/bash
# 片 C（62126062）：H 原三档 16×3×3 → 回注 reset xhard1/2/3 各 13 任务 × 1 + xhard4 16 任务 × 1 = 55（经 builder 评估链）
source /nfs/turbo/coe-chaijy-unreplicated/hongzefu/hs-scripts/shard_common.sh
gen smoke-H-native H native $REPO --smoke 1 || { echo "EXIT_CODE=1"; exit 1; }
gen H-native H native $REPO || { echo "EXIT_CODE=2"; exit 2; }
echo "SEGMENT_START reset-replay $(date -Is)"
uv run --frozen --no-sync python scripts/parity/hard_regression.py reset-replay --out $N/hs-stage/reset-replay/reset.jsonl
code=$?; echo "SEGMENT reset-replay EXIT_CODE=$code $(date -Is)"
[ $code = 0 ] || { echo "EXIT_CODE=4"; exit 4; }
echo "SHARD_C 全部完成"; echo "EXIT_CODE=0"
```
