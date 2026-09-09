# newtask-v2 三路对拍：用例说明与运行索引

对应 [NEWTASK_V2_PLAN.md](../../../NEWTASK_V2_PLAN.md) 第四步。目标是证明
「把四个任务已在用的位置分布与参数候选提取成显式输入」之后，原版行为逐位不变。

## 三路口径

| 路 | 来源 | 入口 | 配置 |
| --- | --- | --- | --- |
| `A1` / `A2` | `artifacts/native-baseline`（指向 `94449db` 的 detached worktree） | `scripts/data-generation-newSeed/generate_dataset_newseed.py` | 无 |
| `B` | 当前工作树 | `scripts/generate_dataset_newseed.py` | 不传 |
| `C` | 当前工作树 | 同上 | `--sampling-config scripts/configs/newtask-v2/native_sampling.json` |

`A1`/`A2` 是同一用例的两次独立运行，用于原版重复性校准与 `rrt_fallback_count` 登记：
screw→RRTStar 回退走 mplib/OMPL，种子接口未暴露且有 1 秒墙钟预算，**触发回退的局不具备逐位可复现性**。

四路共用同一 `.venv`，固定 `--workers 1 --gpus 0 --layout train --max-attempts 1
--max-tasks-per-child 8 --episodes 1`，同一格固定任务、难度、episode、seed、attempt=0，独立进程串行执行。

## 五项重要对拍与证据来源

| 编号 | 内容 | 证据 |
| --- | --- | --- |
| ① | 关键帧目视无区别 | 观察器捕获的 `reset` 初态指纹；图版 PNG 留 `artifacts/`，目视记录绑定图片散列 |
| ② | 变量跳变、物体位置及产生／消失过程 | `boundaries`（构造与两次 `_initialize_episode`）、`steps`（逐步状态与全部 actor 位姿）、`events` |
| ③ | HDF5 产物内容 | 遍历实际落盘树的全字段逐元素比较，浮点按位模式、不设容差 |
| ④ | 随机抽样调用及流状态 | `torch.rand/randint/randperm` 的调用序列、上下界、shape、随机源与状态散列；`np.random.seed` 单独登记 |
| ⑤ | 同一 worker 连续生成互不污染 | 连续运行与对应独立运行逐局比较，父配置前后散列不变 |

## 用例矩阵

15 格，见 [cases.json](cases.json)：`BinFill` 三难度 × `dynamic` 两分支共 6 格，
`RouteStick` / `VideoUnmaskSwap` / `VideoRepick` 各三难度共 9 格。
`--difficulty` 是三位 easy/medium/hard 循环配额，`100` 表示全 easy，不是"难度 100"。

原版在某格首次尝试即失败或触发 RRT* 回退时，该格记为受阻并保留记录，
另选**同格其他 episode** 补足（只换 episode，seed 仍由原公式算出，不自动换 seed 顶替）。

## 运行索引

| 运行编号 | 范围 | 结论 |
| --- | --- | --- |
| [20260908T2255Z-parity15-3804e87](20260908T2255Z-parity15-3804e87/README.md) | 15 格 × 四路（A1/A2/B/C）+ ⑤ 连续 worker 两路 + ① 全量 354 张关键帧出图 | ②③④ 15 格通过、⑤ 两路通过、① 9 格通过 6 格待目视；15 格 `rrt_fallback_count` 全为 0 |
| [20260909T1441Z-postclean](20260909T1441Z-postclean/README.md) | 第五步清理后的抽样复验（每任务 easy 一格 B/C）+ 定向检查清单 + attempt 重试分支三路对照 + `--env all` 16 任务 smoke | 抽样复验八项 0 差异、重试分支三路一致且产物 0 差异、16/16 任务成功；轻量全量 4 failed（基线既有）/176 passed |
