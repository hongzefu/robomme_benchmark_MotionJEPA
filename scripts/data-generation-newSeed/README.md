# 无 seed 独立生成（data-generation-newSeed）

本目录是**生成型**链路：seed 由公式自算（`offset + env_code*env_block + episode*100 + attempt`），
失败自动 attempt+1 换 seed 重试，可独立产生新数据。与之相对，`scripts/data-generation/` 是
**复现型**链路：读 train metadata 里的死 seed、单次尝试，只能重放。

已用四个 Unmask 系 env 全量 400 条（2026-08-17）与原版官方数据
（`/data/hongzefu/robomme_data_h5`）逐条比对，两个核心结论如下。

## 结论一：同 seed 时，joint angle 与原版几乎逐位相同

400 条中 392 条与原版同 seed。这 392 条 timestep 数全部一致，逐 timestep 逐元素比对
`action/joint_action`（8 维）：

- **389/392 条（99.2%）逐位相同**（差值 < 1e-8）；VideoUnmask 整个 env 100 条全部逐位相同。
- 仅 3 条有可见偏差，**最大绝对差 2.146e-06**——量级远小于关节角的物理意义尺度。
  且偏差集中在连续关节 j3、离散的夹爪 j7 三条恒为 0、峰值都在轨迹末段，
  是浮点误差沿轨迹单向累积的特征，**不是决策/逻辑分叉**（timestep 数与原版完全一致）。

→ **生成链路与原版在数值层面等价。** 逐 episode 的 400 行完整差异表见
`reports/joint_action_diff_full.md`。

## 结论二：不同 seed 的 8 条 = 环境代码三个月来的行为漂移

8 条 seed 与原版不同，**恰好全部是 train 里 attempt=1（当年失败过一次）的 8 个探针**，
偏差一律 −1：当前环境代码下这 8 个 episode 全部在 attempt=0 一次通过，反向情况
（train 成功、现在失败）一例都没有——漂移单向，当前环境比 2025-12 更容易通过
（与 `fix choice action reading` 等修复方向吻合）。

→ 实践含义：**用本目录无 seed 重跑，无法逐字复现 train 的 seed 集合**，差异恰好落在
train 当年失败过的 episode 上。要复现 train 请用 `scripts/data-generation/generate_dataset.py`
读死 seed；本目录用于**产生新数据**。

## 目录内容

| 文件 | 作用 |
| --- | --- |
| `seed_layout.py` | seed 公式与难度循环的唯一定义；train/test/val/heldout 四代布局的 offset 与 env_block |
| `generate_dataset_newseed.py` | 生成入口：每卡一个进程池、进程终身绑卡、失败自动换 seed 重试、结果边跑边写 JSONL |
| `merge_episode_h5.py` | 把逐 episode 的 h5 合并成官方格式 `record_dataset_{task}.h5`（按 metadata 逐条定位而非 glob；生成入口刻意不合并） |
| `utils/compare_with_metadata.py` | 与 train metadata 逐条比对 (seed, difficulty)，出一致性报告——实质是检验当前环境代码与 2025-12 的行为等价性 |
| `utils/calibrate_parallelism.py` | 并行度标定：串行跑多档 workers/GPU/线程限制配置，采资源指标，出稳态吞吐对比表 |
| `outputs/` | 生成与标定产物（h5、视频、JSONL、报告） |
| `reports/joint_action_diff_full.md` | 与原版官方数据的逐 episode joint_action 差异全表（400 行） |

命令用法、seed 公式细节、并行执行要点与全部实测数据（标定表、资源上限、全量比对明细）
见本目录 [CLAUDE.md](CLAUDE.md)。
