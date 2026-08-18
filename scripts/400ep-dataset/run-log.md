# 400ep 数据集：过程 log 全记录（2026-08-18）

按执行顺序记录每一段的命令、实际运行数据与验收结果。背景与复现步骤见 [README.md](README.md)。

## 0. 代码改动与轻量测试

- 改动清单见 README 第三节，commit `82f4895`（2.8）。
- `uv run python -m pytest tests/lightweight/`：**129 passed + 4 failed，239.4 s**。
  4 个失败（`test_TaskGoal` 2 个、`test_step_error_handling` 2 个）为**与本轮无关的存量失败**：
  单独重跑仍确定性失败，且涉及文件（`DemonstrationWrapper.py`、`run_example.py`、
  `dataset_replay.py`）本轮未动；已另立任务处理。本轮新增/修改的
  `test_seed_layout.py`（5 项）与 `test_append_train_metadata.py`（7 项）全部通过。

## 1. newSeed 冒烟（VideoUnmask ep100–101）

```bash
uv run python scripts/data-generation-newSeed/generate_dataset_newseed.py \
  --env VideoUnmask --episode-start 100 --episodes 2 --difficulty 211 \
  --gpus 1 --workers 2 \
  --output-dir scripts/data-generation-newSeed/outputs/smoke-ep100
```

2/2 成功，13.8 s（单条 8.3/8.6 s，attempt 均为 0），worker 峰值 RSS 2285 MB。验收逐项通过：

| 项 | 期望 | 实际 |
| --- | --- | --- |
| ep100 seed | 16000 | 16000 ✓ |
| ep101 seed | 16100 | 16100 ✓ |
| 难度 | easy / easy（100%4=0, 101%4=1） | easy / easy ✓ |
| 文件名 | `VideoUnmask_ep100_seed16000.h5` 等 | ✓ |
| metadata | record_count=2，仅 ep100–101 | ✓ |
| run_parameters | 含 `episode_start: 100` | ✓ |

## 2. ep0–99 段：复现链路尝试失败 → 改为拼接官方数据副本

### 2.1 复现链路尝试（已取消）

最初计划用复现链路重新生成 ep0–99（tmux session `gen-ep0-99`，GPU0）。启动即失败：

```
ERROR: Missing required paths: /data/hongzefu/robomme_benchmark_MotionJEPA/data/robomme_data_h5
EXIT_CODE=1
```

`scripts/data-generation/generate_dataset.py` 硬性要求仓库内 `data/robomme_data_h5`
（官方参考数据，用于生成报告里的哈希清单，只读）。曾建软链
`data/robomme_data_h5 → /data/hongzefu/robomme_data_h5` 准备重跑；此时用户改口径：
**「ep0–99 直接拼接现有数据集 不用再验证 拼接现有的 Yinpei/robomme_data_h5 副本」**，
复现段整体取消，软链已清理。

另记录一个此路线的既有事实（对拼接路线同样适用）：复现链路收尾会把逐 episode h5
合并成官方格式后删除原始文件，其最终产物是合并文件而非逐 episode 文件。

### 2.2 拼接官方数据副本（split_official_h5.py）

启动 2026-08-18 14:0x，tmux session `split-ep0-99`，日志
`scripts/data-generation-newSeed/outputs/train-ep0-99-official.log`：

```bash
uv run python scripts/400ep-dataset/split_official_h5.py \
  --official-dir /data/hongzefu/robomme_data_h5 \
  --env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask \
  --episodes 100 \
  --output-dir scripts/data-generation-newSeed/outputs/train-ep0-99-official
```

与 ep100–399 生成段并行（拆分吃 IO、生成吃 CPU，互不干扰）。

结果：**4 env × 100 = 400 条全部写出，耗时 256.7 s，EXIT_CODE=0**，合计 77 GB。
400 条的 `setup/seed` 防错检查全部通过（任何一条不符脚本会即刻报错中止）。
8 条探针（seed 尾号 1）的文件名逐一在列：`ButtonUnmask_ep5_seed8501.h5`、
`ButtonUnmask_ep72_seed15201.h5`、`ButtonUnmaskSwap_ep70_seed14001.h5`、
`ButtonUnmaskSwap_ep94_seed16401.h5`、`ButtonUnmaskSwap_ep98_seed16801.h5`、
`VideoUnmask_ep10_seed7001.h5`、`VideoUnmaskSwap_ep32_seed8201.h5`、
`VideoUnmaskSwap_ep61_seed11101.h5` —— 与 train metadata 完全一致。

## 3. ep100–399 生成段（4 env × 300，无 seed 自算）

启动 2026-08-18 14:0x，tmux session `gen-ep100-399`，GPU1（启动时空闲约 30 GB，
外部任务 roihn 占约 15.6 GB / 210 W；标定已证 GPU 非瓶颈、单卡 32 workers 最优），日志
`scripts/data-generation-newSeed/outputs/train-ep100-399.log`：

```bash
uv run python scripts/data-generation-newSeed/generate_dataset_newseed.py \
  --env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask \
  --episode-start 100 --episodes 300 --difficulty 211 \
  --gpus 1 --workers 32 \
  --output-dir scripts/data-generation-newSeed/outputs/train-ep100-399
```

结果（`run_summary.json` 副本在本目录）：

| 项 | 值 |
| --- | --- |
| 成功 | **1200/1200**，`exhausted_count=0`，`EXIT_CODE=0` |
| attempt | **全部 1200 条 attempt=0 一次通过**，零 seed 演进（metadata 里新段 seed 全部尾号 00） |
| 耗时 | 2500.6 s（41.7 分钟），稳态吞吐 28.79 ep/min |
| worker 峰值 RSS | 4357 MB |
| 产物 | 1200 个 h5（约 224 GB）+ 视频 |

日志里的 `screw plan failed` 行是 planner 内部 screw→RRT\* 的正常降级重试，不是 episode 失败
（`episode_results.jsonl` 无任何 ok=false 或 attempt≠0 记录）。

## 4. metadata 写回

dry-run 与正式写入输出一致：四个 env 均为「100 条 + 追加 300 条（ep100..399）→ 400 条」。
git diff 为纯追加（4 文件 +7204/−4 行，−4 是 record_count 行与收尾括号的重排）。
ep0–99 段一字未动（探针 seed 尾号 1 全部保留，见第 5 节 resolver 验证）。

写回后重跑 `tests/lightweight/test_seed_layout.py + test_append_train_metadata.py`：
**15 passed（0.11 s）** —— 400 条 metadata 与 seed 公式、难度循环全量自洽。

## 5. 汇总目录与终验

汇总（硬链接，同一文件系统零额外磁盘）：

```bash
mkdir -p scripts/data-generation-newSeed/outputs/train-ep0-399/hdf5_files
cd scripts/data-generation-newSeed/outputs/train-ep0-399/hdf5_files
ln -f ../../train-ep0-99-official/hdf5_files/*.h5 .
ln -f ../../train-ep100-399/hdf5_files/*.h5 .
```

**1600 个文件（每 env 恰 400），合计 301 GB**。终验三项全过：

1. **文件名 ↔ metadata 双向逐条对应**：四个 env 各 400/400，无缺无多。
2. **h5 抽查**（每 env 3 条，官方段/生成段都覆盖）：`episode_N` 组在、`setup/seed`
   与文件名一致、timestep 数正常；字段数官方段 27、生成段 21，与已知差异一致。
   h5 内部结构为 `episode_N/{setup, timestep_K/{action,info,obs}}`。
3. **消费侧 resolver 冒烟**（`BenchmarkEnvBuilder(dataset="train")`）：四 env
   `get_episode_num()` 均为 400；`resolve_episode(100)` = (15000..18000, easy) 逐一正确；
   探针 ep10=7001 / ep32=8201 / ep70=14001 / ep5=8501 保留无损；ep399 难度 hard（399%4=3）。

## 6. v2 合并（2026-08-18 下午，tmux `merge-v2`）

输入准备：把 4 份 400 条版 metadata json 从 `src/robomme/env_metadata/train/` 拷入
`outputs/train-ep0-399/`（merge 脚本按 metadata 逐条定位源文件，不 glob）。

结果（日志 `outputs/merge-v2.log`，`EXIT_CODE=0`，全程约 20 分钟）：

| task | episode 数 | 体量 |
| --- | ---: | ---: |
| VideoUnmaskSwap | 400 | 84.5 GiB |
| VideoUnmask | 400 | 52.9 GiB |
| ButtonUnmaskSwap | 400 | 96.7 GiB |
| ButtonUnmask | 400 | 65.0 GiB |
| 合计 | 1600 | ≈292 GiB |

落点 `/data/hongzefu/robomme_data_h5_v2_4env400ep/`，另拷入 4 份 metadata json 供溯源。

## 7. v2 契约校验（tmux `verify-v2`，verify_merged_v2.py）

对全部 1600 集预演 dataset-build 的断言（episode/timestep 连续、front_rgb 形状、
demo 严格前缀、exec 段 completed 余量、setup/seed 与 metadata 对拍）：

**4 个文件全部通过**（VideoUnmaskSwap 83.3s / VideoUnmask 52.2s /
ButtonUnmaskSwap 76.3s / ButtonUnmask 28.5s），`EXIT_CODE=0`。

## 8. NFS 转换器验收冒烟（tmux `smoke-v2`）

用 NFS 仓库本体 `build_data_raw_from_h5.py`（只读该仓库）对
`--episodes 0,100,399` × 4 env 跑转换，输出落本机 scratch：

```bash
uv run python /nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA/scripts/dataset-build/build_data_raw_from_h5.py \
  --h5_dir /data/hongzefu/robomme_data_h5_v2_4env400ep \
  --tasks ButtonUnmask,ButtonUnmaskSwap,VideoUnmask,VideoUnmaskSwap \
  --episodes 0,100,399 --num_workers 8 --output_root <scratch>/v2-accept-smoke
```

**4 env × 3 episode 全部成功、零断言失败、`EXIT_CODE=0`**。产出 12 个
`<Task>_ep{0,100,399}/video_exec.h5`，抽查确认 `frames` 为 (T,256,256,3) uint8、
attrs 含 `fps=30.0`/`num_frames`/`source`（source 串正确指向 v2 文件的
`episode_N/exec[lo:hi]`，即下游 arm-mask 依赖的定位格式）。官方段（ep0）与
生成段（ep100/399）都被覆盖 —— **v2 数据集被 dataset-build 链路原样接受**。

## 9. 工作区备注

- `.gitignore` 存在一处**非本轮**的在途改动（新增 `scripts/data-generation-MotionJEPALabel/outputs/`
  一行，来源为其他会话/用户），本轮提交绕开未动，留待其归属方处置。
