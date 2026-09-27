# V6 S4：Great Lakes 双席正式生成 Runbook

状态：仅准备与核对文档；本轮未运行 `srun`、`sbatch`、`scancel` 或仿真。正式启动前仍须完成本文的源码增量同步、作业状态和 `/tmp` 容量闸门。

## 一、定稿规模与双席切分

S4 目标来自 `NEWTASK_RELEASE_V6_PLAN.md`：55 个「环境 × 难度」格；每格抽签 10 个成功候选，冻结候选 index `0,3,6` 各一局，目标为 550 个成功候选与 165 个正式 episode。抽签拒绝按 M4 上限 60 次记录 shortfall，不换掉失败证据，也不把候选数写成正式局数。

| 作业 | 当前节点快照 | 难度档 | 每档环境数 | 格数 | 候选目标 | 正式局目标 |
|---|---|---|---:|---:|---:|---:|
| `61890467` | `gl1526` | `xhard1,xhard2` | 13 + 13 | 26 | 260 | 78 |
| `61890468` | `gl1517` | `xhard3,xhard4` | 13 + 16 | 29 | 290 | 87 |
| 合计 | 两个独立节点 | 四档各一次 | — | 55 | 550 | 165 |

切分没有重复的 tier/task 单元。`pipeline_tasks_for_tier("all")` 将 `xhard1..3` 展开成 13 个有梯度环境，将 `xhard4` 展开为全部 16 个环境。两边使用同一个 run id 字符串 `/tmp/v6-s4-v6-01` 是安全的：两个 job 位于不同节点，`/tmp` 是节点本地盘，且每席只写自己的 tier 子目录。若节点不再分别是 `gl1526` 与 `gl1517`，先停止并重新安排唯一 run id。

`v4_specs.draw_task` 中 `--max-reset-attempts 60` 是**每个环境最多 60 次总抽签尝试**，不是每个候选再各重试 60 次：reset 成功后候选 episode 前进，失败只推进该候选的 attempt。候选不足 10 条时，`freeze` 只选实际存在的 index 0/3/6，`candidate_shortfall` 与 `selected_shortfall` 必须如实报告。`v4_rollout.cmd_run` 会从未选候选做正式局递补；`backfilled` 和最终 shortfall 独立留在报告中。

## 二、当前检查快照与正式启动前同步边界

- 主仓当前为 `newtaskRelease-v5@75865a26`。相对 GL 已有同步锚点 `949b6eb`，提交差异新增 `scripts/parity/v6_v0_native_definitions.py` 与 `tests/lightweight/test_v6_v0_native_definitions.py`；主仓工作区当前还有 `NEWTASK_RELEASE_V6_PLAN.md` 在途修订及三个在途测试：`tests/lightweight/test_TaskGoal.py`、`tests/lightweight/test_v4_decision_guard.py`、`tests/lightweight/test_v5_xhard_obb_fix.py`。正式启动前先等最终 ref 与需同步的 `src/scripts/tests` 改动稳定；不要把这些在途修改默认为可同步，计划文件也不在同步 pathspec 内。
- GL 是 `newtaskRelease-v5@1bb4190`，已在本轮之前应用 `da77662..949b6eb` 的 `src scripts tests` 精确 diff；当前工作区正好 68 个预期路径，`git diff --check` 通过，尚未同步上面主仓在 949b 之后的最终增量。`artifacts/` 中的历史数据不纳入同步，也不可清理。
- 正式启动前记录最终主仓 ref，并只同步最终差异：

  ```bash
  git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask diff --name-status 949b6eb <MAIN_FINAL_REF> -- src scripts tests
  git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask diff --binary 949b6eb <MAIN_FINAL_REF> -- src scripts tests \
    | git -C /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl apply --verbose
  ```

  先确认 GL 当前 68 路径正是 `da77662..949b6eb` 的同步结果、主仓已稳定，再应用这段**增量**。应用后核对 GL `git status --short --untracked-files=all` 的路径集合等于 `da77662..<MAIN_FINAL_REF>` 在 `src scripts tests` 下的差异，并运行 `git diff --check`。不把任何 `artifacts/` 路径带进补丁，不在 GL commit/push。
- `scripts/parity/v4_specs.py::source_fingerprint` 只对 `src/robomme/robomme_env` 下的 Python 源计算路径与 SHA-256。主仓 949b 之后没有 `src/` 差异，所以这次新增的 V0 检查脚本/测试本身不改变环境指纹；仍按上一步同步最终 `src scripts tests` 差异，并在每个 job 上核对 GL import 来自 GL 副本。`src/robomme/env_record_wrapper/RecordWrapper.py` 继续对 `da77662` 零 diff。

## 三、执行入口、路径和恢复语义

V6 `v5_generation.pipeline` 的 `pipeline_paths` 在 `--run-id` 是绝对路径时把该路径作为根；因此必须使用 `/tmp/v6-s4-v6-01`，不能用相对 `v6-01`，否则 `artifacts/newtask-v6` 与 `scripts/configs/newtask-v6` 会落在 NFS 工作树。V6 每档的四步输出为：

| 内容 | 节点本地路径 |
|---|---|
| 抽签 drafts | `/tmp/v6-s4-v6-01/<tier>/draft/drafts.jsonl` |
| 冻结 specs | `/tmp/v6-s4-v6-01/<tier>/specs.jsonl` |
| rollout、HDF5、视频、回放记录 | `/tmp/v6-s4-v6-01/<tier>/rollout/run1/` |
| 每档报告 | `/tmp/v6-s4-v6-01/<tier>/report/` |
| V6 配置快照和 official tree | GL 副本内只读输入 |

`pipeline --tiers` 会逐档依次执行 draw → freeze → run → report，再在该 job 的节点 `/tmp/v6-s4-v6-01/report/` 聚合本席的档位。两个节点本地的顶层 `report/` 互不相同；回传时只传 `xhard1..xhard4` tier 目录，不传两份席位级顶层 report。稍后在本机用 `aggregate_tier_reports` 从四个 tier 报告重算全局 55 格报告。

首次运行不加 `--resume`，并用唯一空 run id。`plan_pipeline` 的 resume 判据只是 drafts/specs/results 文件是否存在，report 总是重出，不校验内容散列后才决定跳过。特别是 rollout 目录已存在但没有 `results.jsonl` 时，`cmd_pipeline` 会直接报错，即使加 `--resume` 也不会清理或自动修复。遇到中断先保留并检查该 tier 的现存文件；禁止 `rm -rf` 或覆盖。仅在确认输入、参数、source fingerprint 和已完成文件一致时，才由正式执行者决定是否对同一节点路径使用 `--resume`；无法证明完整时改用新 run id 并保留旧目录。

## 四、正式执行前闸门

按顺序逐项核验；任一失败就停止，不改用新 job、不把输出改写到 NFS：

1. **作业状态和节点**：从登录机查询 `squeue -h -j 61890467,61890468 -o "%i|%T|%N|%C|%m|%M|%l|%L"`。当前快照为两者均 `RUNNING`、分别 `gl1526/gl1517`、16 CPU/192G、48 小时配额。启动前重查，两个 ID 任一非 `RUNNING` 或节点/资源改变都暂停；只允许下面列出的两个 `srun --jobid`，不用 `sbatch` 或 `scancel`。
2. **GL 最终代码**：按第二节等主仓稳定后只增量同步 `src scripts tests`，对照精确路径集合和 `git diff --check`。本 runbook 准备阶段没有执行同步。
3. **uv 与副本导入**：GL 上 `command -v uv`；所有 NFS 上的 uv 命令设 `UV_LINK_MODE=copy`、使用 `uv run --project "$PWD" --no-sync`，不 `uv sync`。从 GL 仓库根运行 `PYTHONPATH="$PWD/src" ... python -c`，用 `importlib.import_module("robomme.robomme_env.BinFill")` 确认 `robomme.__file__` 与模块文件都位于 GL 副本；不能只看包的同名导出类。
4. **配置/官方源**：确认 GL `scripts/configs/newtask-v6/sampling_config.json` 存在并与最终主仓一致；确认 `artifacts/train-parity/local-smoke-01/official-src/.official_tree` 存在且 marker 与批准快照一致。它们只读，不向其中写 output。
5. **节点 `/tmp` 容量**：本准备轮未运行 `srun`，所以**实际剩余空间尚未测量**。正式起跑前在各自现有 job 上执行只读预检：

   ```bash
   # job 61890467，预期 gl1526
   ssh -o BatchMode=yes greatlakes 'srun --jobid=61890467 --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared bash -lc "hostname; df -hP /tmp; df -B1 --output=avail /tmp; df -Pi /tmp; test ! -e /tmp/v6-s4-v6-01"'
   # job 61890468，预期 gl1517
   ssh -o BatchMode=yes greatlakes 'srun --jobid=61890468 --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared bash -lc "hostname; df -hP /tmp; df -B1 --output=avail /tmp; df -Pi /tmp; test ! -e /tmp/v6-s4-v6-01"'
   ```

   以计划总产物上限 270 GB 按候选数切分：席 A `270×260/550≈127.6 GB`，席 B `270×290/550≈142.4 GB`。为缓冲估算误差，本 runbook 建议的启动下限分别为 **160,000,000,000 bytes** 与 **180,000,000,000 bytes** 空闲空间；席 A 还要注意其 `/tmp/v6-gl-smoke-61890467-binf-xhard1-20260926T195419Z` 现有约 795 MiB smoke 产物，必须保留，`df` 的 available 值应已扣除它。此分配是基于计划上限的预检门槛，不是已测容量；低于门槛、inode 不足、target 已存在或 hostname 不符就暂停，不清理任何既有数据。
6. **先 dry-run**：两个席位分别用实际参数加 `--dry-run` 检查打印的所有可写路径以 `/tmp/v6-s4-v6-01/` 开头，且只读输入为上述 GL snapshot/official tree；不要把正式命令中的 `--run-id` 改成相对路径。
7. **本机接收空间**：启动前在 `/data` 重查可用空间，建议至少 300 GB（270 GB 上界加缓冲）。目标 `artifacts/newtask-v6/s4-prep/v6-01/` 必须不存在对应 tier 子目录；不覆盖旧 artifacts。

## 五、双席正式命令

在本机主仓启动两个独立 tmux session，避免工作流会话中断时杀掉长任务；attach 后在 session 内粘贴对应命令，再用 `Ctrl-b d` 脱离。stdout/stderr 都通过 SSH 流到本机主仓日志，不在 NFS 写生成日志。先建立本机日志目录并确认日志文件不存在：

```bash
mkdir -p /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/s4-prep/logs
tmux new-session -d -s v6s4_61890467
tmux new-session -d -s v6s4_61890468
```

在 `v6s4_61890467` session 中运行席 A：

```bash
set -o pipefail
LOG=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/s4-prep/logs/61890467.log
test ! -e "$LOG" || exit 73
ssh -o BatchMode=yes greatlakes 'srun --jobid=61890467 --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared bash -lc "bash -s"' 2>&1 <<'REMOTE' | tee -a "$LOG"
#!/usr/bin/env bash
set -euo pipefail
cd /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
export UV_LINK_MODE=copy PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$PWD/src"
RUN_ID=/tmp/v6-s4-v6-01
test ! -e "$RUN_ID"
command -v uv
uv run --project "$PWD" --no-sync python -m scripts.parity.v5_generation pipeline \
  --release newtask-v6 --run-id "$RUN_ID" --tiers xhard1,xhard2 --tasks all \
  --candidates-per-env 10 --max-reset-attempts 60 --select 0,3,6 \
  --draw-workers 16 --draw-gpus 0 --workers 16 --rollout-gpu 0 \
  --official-root artifacts/train-parity/local-smoke-01/official-src
REMOTE
rc=$?
printf 'EXIT_CODE=%s\n' "$rc" >> "$LOG"
exit "$rc"
```

在 `v6s4_61890468` session 中运行席 B；参数相同，只换 job/tier 和本机日志名：

```bash
set -o pipefail
LOG=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/s4-prep/logs/61890468.log
test ! -e "$LOG" || exit 73
ssh -o BatchMode=yes greatlakes 'srun --jobid=61890468 --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared bash -lc "bash -s"' 2>&1 <<'REMOTE' | tee -a "$LOG"
#!/usr/bin/env bash
set -euo pipefail
cd /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
export UV_LINK_MODE=copy PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH="$PWD/src"
RUN_ID=/tmp/v6-s4-v6-01
test ! -e "$RUN_ID"
command -v uv
uv run --project "$PWD" --no-sync python -m scripts.parity.v5_generation pipeline \
  --release newtask-v6 --run-id "$RUN_ID" --tiers xhard3,xhard4 --tasks all \
  --candidates-per-env 10 --max-reset-attempts 60 --select 0,3,6 \
  --draw-workers 16 --draw-gpus 0 --workers 16 --rollout-gpu 0 \
  --official-root artifacts/train-parity/local-smoke-01/official-src
REMOTE
rc=$?
printf 'EXIT_CODE=%s\n' "$rc" >> "$LOG"
exit "$rc"
```

每档会由 `cmd_pipeline` 强制使用 `release=newtask-v6` 与 V6 seed profile。`draw_workers=16` 在 13 环境 tier 会由 `draw_rows` 限到 13 个进程；xhard4 为 16 个。不要加 `max_tasks_per_child`，避免 spawn worker 回收挂死。job 每席仍只用已保留的一张 GPU；不启动第三个 job。

## 六、流式回传与本机合并

必须等对应 pipeline 完成且 `EXIT_CODE=0` 后回传。源头是节点 `/tmp`；通过 SSH/srun 的 stdout 直接进入本机 `tar`，**不要先在 GL/NFS 写 tar 包**。job A 只传 `xhard1 xhard2`，job B 只传 `xhard3 xhard4`；不传两份席位级 `/tmp/v6-s4-v6-01/report/`，因为它们各自只汇总本席。每档目录本身包含 drafts、冻结 specs、正式 rollout（HDF5/视频/spec replay/rng trace）与该档 report。

```bash
set -o pipefail
DEST=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/s4-prep/v6-01
mkdir -p "$DEST"
test ! -e "$DEST/xhard1" && test ! -e "$DEST/xhard2"
ssh -o BatchMode=yes greatlakes 'srun --jobid=61890467 --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared bash -lc "tar -C /tmp/v6-s4-v6-01 -cf - xhard1 xhard2"' \
  2>"$DEST/stream-61890467.stderr" | tar -xpf - -C "$DEST"
```

席 B 同样执行，目标检查 `xhard3`、`xhard4` 不存在，job id 换成 `61890468`，tar 源清单换成 `xhard3 xhard4`，stderr 写本机 `stream-61890468.stderr`。`pipefail` 非 0 时保留两端当前数据、核对 tar/SSH 错误；不重跑、不清理、不覆盖。

本地核对四个 tier 子树的文件数、总字节、spec/report/HDF5/MP4 SHA；用主仓 `uv run --project /data/hongzefu/robomme_benchmark_MotionJEPANewTask --no-sync python ...` 检查 HDF5 可读、episode 与结果行 task/seed 对应、`spec_replay.json` mismatch/unused、`cv2.VideoCapture` 首帧解码。重新核验官方数据仍只在 NFS 输入路径，生成数据只在本机 `/data` artifacts。

四档 per-tier report 都在本机后，用现有 `aggregate_tier_reports` 重新生成**跨两席 55 格**汇总；参数中的 run id 是 `pipeline_paths` 相对主仓 `artifacts/newtask-v6` 的路径：

```bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
command -v uv
UV_LINK_MODE=copy uv run --project "$PWD" --no-sync python -c 'from scripts.parity.v5_generation import aggregate_tier_reports; r=aggregate_tier_reports("newtask-v6", "s4-prep/v6-01", ("xhard1", "xhard2", "xhard3", "xhard4")); print(r["line"])'
```

目标报告位于 `artifacts/newtask-v6/s4-prep/v6-01/report/generation_report.{json,md}`，判定行应 `cells=55`；`draft_ok`、`candidate_shortfall`、`rollout_ok`、`backfilled`、`selected_shortfall` 必须按结果原样记录，不因短缺改分母。此 report 不设 S4 独立通过阈值。S3 的 `NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0` 是 V1 硬门槛；V1 通过前 S4 数据只是先落盘的候选产物，不能标正式。job 完成后不运行 `scancel`，待主任务另行安排。

## 七、风险与停止条件

- 本准备轮没查询节点 `/tmp` 的实际容量；容量门槛必须在每个 job 上现场测。GL 登录机的 `/tmp` 数字不能代替 `gl1526/gl1517` 节点本地值。
- 61890467 上已有本轮单格 smoke `/tmp/v6-gl-smoke-61890467-binf-xhard1-20260926T195419Z`（约 795 MiB），保留并计入 gl1526 的已用空间；不得删它或其他既有 `/tmp` 内容。
- 任一 job 非 `RUNNING`、NodeList 改变、uv/import 不是 GL 副本、source fingerprint 或 V6 sampling snapshot 不符、official marker 缺失、`/tmp` 不够、run id 已存在、dry-run 显示任何可写路径落在 NFS，都立即停下汇报。
- 任务不允许新 `sbatch`、`scancel` 或使用 61890468 以外的 job；不在这一步执行正式 run、容量命令、同步或清理。本文件只给后续执行者一个可复核的步骤表。
