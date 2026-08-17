# 无 seed 独立生成（data-generation-newSeed）

`scripts/data-generation/` 是**复现型**链路：从 `src/robomme/env_metadata/train/*.json` 读死 seed、
单次尝试、不重试，只能重放已知 seed。本目录是**生成型**链路：seed 由公式自算，失败自动 attempt+1 重试，
因此可以独立产生新数据。

## seed 公式

```
seed = offset + env_code * env_block + episode * 100 + attempt
```

`env_code` 是任务在 16 任务规范序（`scripts/data-generation/validate_generated_dataset_contract.py`
的 `ALL_TASKS`）里的 1-indexed 位置。四代数据集的布局：

| 布局 | offset | env_block |
| --- | ---: | ---: |
| `train` | 0 | 1,000 |
| `test` | 500,000 | 10,000 |
| `val` | 1,000,000 | 10,000 |
| `heldout` | 1,500,000 | 100,000 |

难度用 ratio 字符串表示，三位数字依次对应 easy/medium/hard。`211` 展开成周期 4 的
`[easy, easy, medium, hard]`，按 `episode % 4` 取 —— 这与四个 Unmask 系 env 的 train metadata 完全一致。

## 与骨架的口径一致性

env kwargs、FailRecover 分档（ep0-2 → `z`、ep3-5 → `xy`、ep≥6 → 不设）、planner 的
screw×3 → RRT\*×3 重试、成功判定（跑完 task_list 且 `evaluate(solve_complete_eval=True)`
的 `success` 真、`fail` 假）**与骨架逐字相同**。

这一点很关键：本目录的用途之一是验证「当前环境代码与 2025-12 环境代码的行为等价性」——
seed 公式是纯函数，公式层面一致是必然的，真正被检验的是 attempt 层面。这些口径一旦改动，
比对结果就失去意义。

不做的事：不 replay、不导出 segmentation PNG、不与官方 reference 做 1e-8 数值比对
（`data/robomme_data_h5` 在本仓库并不存在）。

## 用法

### 生成

```bash
uv run python scripts/data-generation-newSeed/generate_dataset_newseed.py \
  --env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask \
  --episodes 100 --difficulty 211 --gpus 0,1 --workers 32 \
  --output-dir scripts/data-generation-newSeed/outputs/full
```

产物：

| 产物 | 位置 |
| --- | --- |
| 每 episode 的 h5 | `hdf5_files/{task}_ep{N}_seed{M}.h5` |
| rollout 视频 | `videos/{task}_ep{N}_seed{M}{_FailRecoverZ/XY}_{难度}_{目标}.mp4` |
| 失败 attempt 的视频 | 同目录，`FAILED_` / `success_NO_OBJECT_` 前缀（保留作为失败演进的证据） |
| 逐 attempt 日志 | `episode_results.jsonl`（边跑边写，中途崩溃不丢已完成的部分） |
| 成功 seed 汇总 | `record_dataset_{task}_metadata.json`（与 `env_metadata` 同构） |
| 运行参数与摘要 | `run_parameters.json` / `run_summary.json` |

失败 attempt 留下的空 h5 会被 worker 删掉（`RecordWrapper` 在 `__init__` 就建文件，
但只有 episode 成功才写内容），因此 `hdf5_files/` 里只有真正成功的轨迹。

### 一致性比对

```bash
uv run python scripts/data-generation-newSeed/compare_with_metadata.py \
  --env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask \
  --output-dir scripts/data-generation-newSeed/outputs/full
```

出 `consistency_report.{json,md}`，含全量比对表、train 里 attempt≠0 的探针单列、
以及不一致条目的完整 attempt 轨迹（哪几个 seed 失败、失败原因）。

### 合并 h5（按需）

生成入口**不合并**，避免生成期就把体量翻倍、也让单条失败不牵连其余产物。需要时单独跑：

```bash
uv run python scripts/data-generation-newSeed/merge_episode_h5.py \
  --input-dir scripts/data-generation-newSeed/outputs/full \
  --env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask
```

源文件按 metadata 逐条定位而非 glob，目录里混有残留也不会被误吸。`--delete-source`
默认关闭；合并期间两份并存，需要双倍空间。

### 并行度标定

```bash
uv run python scripts/data-generation-newSeed/calibrate_parallelism.py \
  --root scripts/data-generation-newSeed/outputs/calib \
  --env VideoUnmask --episodes 64
```

默认三档 `A:20:0:off;B:32:0:on;C:32:0,1:on`（档位之间用**分号**分隔，因为 gpus 字段本身含逗号）。
出 `calibration.md`，含稳态吞吐与资源占用对比。

## 并行执行的几个要点

这些是踩过的坑，改动前请先读：

1. **物理仿真在 CPU 上**。ManiSkill 的 `num_envs` 默认 1 → `sim_backend` 解析为 `physx_cpu`，
   GPU 只承担 sapien 渲染。所以并行度上限由物理核数决定，显存不是主要约束，
   **内存才是**（视频帧全程驻留，单 worker 峰值可达数 GB）。
2. **每卡一个进程池，进程终身绑卡**。GPU 号是池的静态属性（写在 `initargs` 里），
   worker 被回收或崩溃重建后依然正确。若改成「单池 + 计数器按 job 分卡」，
   worker 每次重建都会让计数器继续递增，两卡负载会静默漂移；而且 `CUDA_VISIBLE_DEVICES`
   只在该进程首次初始化 CUDA 之前有效，池复用进程时对第二个 job 就失效了。
3. **线程限制必须在 import numpy 之前**。OpenBLAS/libgomp 在 `.so` 加载时读线程数，
   放进程池 initializer 里已经太晚 —— spawn 的子进程 bootstrap 会重跑本模块顶层，
   那时 numpy 已经 import 完毕。所以设置写在 `generate_dataset_newseed.py` 的最顶部。
4. **线程源不止 OpenMP**。OpenCV 有独立线程池（`cv2.setNumThreads`），
   ffmpeg/x264 在每个 episode 收尾编码 mp4 时按 `sched_getaffinity` 自动决定线程数、
   完全不看 `OMP_NUM_THREADS` —— 要压住它只能用 `--affinity per-gpu` 走 CPU 亲和。
5. **`BrokenProcessPool` 必须处理**。worker 在 C++ 层段错误会让整个池死掉，
   所有 in-flight 和 pending 的 job 瞬间全败。调度循环会重建该池并把它名下的 job 退回队列，
   否则一次段错误就报废整批任务。
6. **重试的边界**。五类任务性失败（`SceneGenerationError` / `FailsafeTimeout` /
   `PlannerExhausted` / `ScrewPlanFailure` / `DatasetGenerationError`）视为「该 seed 不通」，
   换 seed 重试；其余异常记为 `failure_class: "code"`，同一 episode 连续 3 次即放弃，
   避免对着一个必然复现的 bug 空转到 attempt 上限。
