# PatternLock / RouteStick 的 test+val 源逐 episode 动作参数

四个任务各 100 条（test 50 + val 50 合并），共 400 个 episode。每个 episode 给出：做了几次动作、每次动作的起终点坐标、每次动作占多少 timestep。明细见同目录的四份任务报告。

## 口径

- **seed / 难度**：一律读 `src/robomme/env_metadata/{test,val}/record_dataset_{Task}_metadata.json`，不用公式反推（存在 attempt 尾号例外，如 PatternLock-val ep37 = 1153701）。
- **move 次数与坐标**：不需要跑仿真。两个 env 的场景随机段只用一个 `torch.Generator(seed)`，消费顺序确定，离线重跑一遍随机数即可还原（`derive_episode_params.py`）。
- **坐标**：SAPIEN 世界坐标，单位米，机器人 base 在 `(-0.615, 0, 0)`。表里是按钮本身的位置（PatternLock z=0.01；RouteStick 偶数下标 z=0.01）；规划实际下发的终点高度统一抬到 z=0.07。
- **时长**：1 timestep = 1 个 env step = 0.05 s（控制频率 20 Hz），与数据集的采样频率一致。录像 fps=30 与 timestep 不等长，报告里不用视频帧。
- **演示段 / 执行段**：同一组 move 在数据里出现两遍——前一遍 `is_video_demo=True` 是给模型看的示范，后一遍才是真正 rollout。下面的时长统计只算执行段。每条 episode 末尾还有一个几到十几 timestep 的收尾段，不算 move。

## 按难度分组

难度是决定 move 次数的唯一配置项（env 的 `configs[difficulty]`），所以统计一律按难度分开看。四个任务的难度分布相同：easy 52 / medium 24 / hard 24（每 split easy 26 / medium 12 / hard 12，难度循环 `211`，按 `episode % 4`）。

### easy

PatternLock：3×3 格点，路径长度约束 `[2, 4]` → move 1~3 次。RouteStick：`steps ∈ [2, 3]`，不允许原地折返。

| 任务 | 条数 | move 次数（min~max） | move 次数均值 | 单次 move 时长（min~max） | 单次 move 时长均值 |
| --- | --- | --- | --- | --- | --- |
| [PatternLock](PatternLock.md) | 52 | 1~3 | 2.06 | 15~40 ts | 28.1 ts |
| [RouteStick](RouteStick.md) | 52 | 2~3 | 2.48 | 43~50 ts | 47.2 ts |

### medium

PatternLock：4×4 格点，路径长度约束 `[3, 5]` → move 2~4 次。RouteStick：`steps ∈ [4, 5]`，不允许原地折返。

| 任务 | 条数 | move 次数（min~max） | move 次数均值 | 单次 move 时长（min~max） | 单次 move 时长均值 |
| --- | --- | --- | --- | --- | --- |
| [PatternLock](PatternLock.md) | 24 | 2~4 | 3.12 | 14~47 ts | 30.7 ts |
| [RouteStick](RouteStick.md) | 24 | 4~5 | 4.50 | 43~50 ts | 48.4 ts |

### hard

PatternLock：5×5 格点，路径长度约束 `[4, 8]` → move 3~7 次。RouteStick：`steps ∈ [4, 7]`，**允许原地折返**（`backtrack=True`）。

| 任务 | 条数 | move 次数（min~max） | move 次数均值 | 单次 move 时长（min~max） | 单次 move 时长均值 |
| --- | --- | --- | --- | --- | --- |
| [PatternLock](PatternLock.md) | 24 | 3~7 | 5.08 | 15~52 ts | 32.7 ts |
| [RouteStick](RouteStick.md) | 24 | 4~7 | 5.54 | 43~50 ts | 48.7 ts |

## Counting suite（BinFill / PickXtimes）

这两个任务的结构与上面两个不同：**没有视频演示段**，动作是 pick / place 成对再加一次 press button，
「动作次数」= BinFill 要放进 bin 的 cube 总数 / PickXtimes 同一动作的重复次数，直接写在 `setup/task_goal` 里。核心段数 = 2 × 动作次数 + 1（每条都验过）。

### easy

BinFill：场上 1 种颜色、spawn 4~6 个 cube，要放进 bin 的 `put_in_numbers ∈ [1, 3]`。PickXtimes：场上 1 种颜色，重复次数 ∈ [1, 3]。

| 任务 | 条数 | 动作次数（min~max） | 动作次数均值 | pick up 时长 | put / place 时长 | press 时长 |
| --- | --- | --- | --- | --- | --- | --- |
| [BinFill](BinFill.md) | 52 | 1~3 | 1.90 | 116.2（78~210） | 69.9（52~93） | 64.0（42~80） |
| [PickXtimes](PickXtimes.md) | 52 | 1~3 | 1.98 | 100.7（69~200） | 75.3（53~107） | 61.7（43~75） |

### medium

BinFill：2 种颜色、spawn 8~10 个，目标涉及 1~2 种颜色、总数 ∈ [2, 4]。PickXtimes：**重复次数区间与 easy 相同（[1, 3]）**，难点在于场上有 3 种颜色的 cube 作干扰。

| 任务 | 条数 | 动作次数（min~max） | 动作次数均值 | pick up 时长 | put / place 时长 | press 时长 |
| --- | --- | --- | --- | --- | --- | --- |
| [BinFill](BinFill.md) | 24 | 2~4 | 3.00 | 108.7（76~195） | 68.1（52~92） | 65.3（48~87） |
| [PickXtimes](PickXtimes.md) | 24 | 1~3 | 2.00 | 95.6（69~163） | 75.5（53~110） | 63.4（49~77） |

### hard

BinFill：3 种颜色、spawn 10~12 个，目标涉及 2~3 种颜色、总数 ∈ [3, 5]。PickXtimes：3 种颜色，重复次数 ∈ [4, 5]。

| 任务 | 条数 | 动作次数（min~max） | 动作次数均值 | pick up 时长 | put / place 时长 | press 时长 |
| --- | --- | --- | --- | --- | --- | --- |
| [BinFill](BinFill.md) | 24 | 3~5 | 4.21 | 109.0（77~182） | 72.1（49~99） | 68.2（50~126） |
| [PickXtimes](PickXtimes.md) | 24 | 4~5 | 4.50 | 85.9（68~197） | 67.5（52~111） | 61.8（42~75） |

三类动作的性质不同，所以分开统计（表里给的是**均值（min~max）**，单位 timestep）：
`pick up` 要在一堆 cube 里找到指定的那个并抓起来；`put / place` 是把手里的东西送到一个
固定位置（BinFill 的 bin / PickXtimes 的 target）；`press` 只是按一下按钮。
每次动作产生一对 pick + place，每条 episode 末尾另有一段 press。

## 采样窗口与帧路

口径与 policy 侧的 motion store / frame sampling 对齐：

- **motion 窗口**：窗口 `[f, f+32]`（33 帧），**stride = 16**，且**不跨段** —— demo 与 exec 两段各自从自己的段起点铺网格。每段窗口数 `len(range(0, max(0, L - 32), 16))`；一条 episode 的 motion token 数 = demo 窗口数 + exec 窗口数。
- **帧路**：`linspace(0, t, N)`（`t = T - 1`），相邻采样帧间隔 **Δ = t / (N - 1)**。帧预算 N 取 32（`512 // (16 × 1)`）与 8（`128 // (16 × 1)`）。注意 32 / 8 是**帧预算**，16 才是窗口 stride，三者不是同一个东西。

> 这套公式已用 policy 侧 16 个任务的中位集逐条验证：窗口数（demo+exec）与 Δ 全部一致，16/16。

### 四个任务总表

每任务 100 条（test 50 + val 50）。

| 任务 | 条数 | 整条长度 min~中位~max | demo 窗口 | exec 窗口 | motion token（min~max，中位） | Δ(N=32) | Δ(N=8) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PatternLock | 100 | 50~187~516 | 0~15 | 0~15 | 0~30，中位 8 | 1.6~16.6 | 7.0~73.6 |
| RouteStick | 100 | 200~300~700 | 5~20 | 5~20 | 10~40，中位 16 | 6.4~22.5 | 28.4~99.9 |
| BinFill | 100 | 249~609~1097 | 0~0 | 14~67 | 14~67，中位 37 | 8.0~35.4 | 35.4~156.6 |
| PickXtimes | 100 | 270~519~1006 | 0~0 | 15~61 | 15~61，中位 30 | 8.7~32.4 | 38.4~143.6 |

### 每个任务每个难度的最短 / 中位 / 最长

按整条长度 T 排序取三档，每格给出具体是哪一条（`split-ep号`），便于回查明细。

| 任务 | 难度 | 档 | 来源 | seed | T | demo 段长 | demo窗+exec窗 | motion token | Δ(N=32) | Δ(N=8) | subgoal 段数 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PatternLock | easy | 最短 | test-ep25 | 652500 | 50 | 25 | 0+0 | 0 | 1.6 | 7.0 | 2 |
| PatternLock | easy | 中位 | val-ep13 | 1151300 | 138 | 69 | 3+3 | 6 | 4.4 | 19.6 | 4 |
| PatternLock | easy | 最长 | val-ep41 | 1154100 | 226 | 113 | 6+6 | 12 | 7.3 | 32.1 | 6 |
| PatternLock | medium | 最短 | val-ep10 | 1151000 | 112 | 56 | 2+2 | 4 | 3.6 | 15.9 | 4 |
| PatternLock | medium | 中位 | val-ep14 | 1151400 | 210 | 105 | 5+5 | 10 | 6.7 | 29.9 | 6 |
| PatternLock | medium | 最长 | test-ep22 | 652200 | 304 | 152 | 8+8 | 16 | 9.8 | 43.3 | 8 |
| PatternLock | hard | 最短 | test-ep7 | 650700 | 184 | 92 | 4+4 | 8 | 5.9 | 26.1 | 6 |
| PatternLock | hard | 中位 | test-ep19 | 651900 | 364 | 182 | 10+10 | 20 | 11.7 | 51.9 | 12 |
| PatternLock | hard | 最长 | test-ep15 | 651500 | 516 | 258 | 15+15 | 30 | 16.6 | 73.6 | 12 |
| RouteStick | easy | 最短 | test-ep1 | 660100 | 200 | 100 | 5+5 | 10 | 6.4 | 28.4 | 4 |
| RouteStick | easy | 中位 | val-ep48 | 1164800 | 200 | 100 | 5+5 | 10 | 6.4 | 28.4 | 4 |
| RouteStick | easy | 最长 | val-ep49 | 1164900 | 300 | 150 | 8+8 | 16 | 9.6 | 42.7 | 6 |
| RouteStick | medium | 最短 | test-ep2 | 660200 | 400 | 200 | 11+11 | 22 | 12.9 | 57.0 | 8 |
| RouteStick | medium | 中位 | test-ep14 | 661400 | 500 | 250 | 14+14 | 28 | 16.1 | 71.3 | 10 |
| RouteStick | medium | 最长 | val-ep42 | 1164200 | 500 | 250 | 14+14 | 28 | 16.1 | 71.3 | 10 |
| RouteStick | hard | 最短 | test-ep3 | 660300 | 400 | 200 | 11+11 | 22 | 12.9 | 57.0 | 8 |
| RouteStick | hard | 中位 | val-ep47 | 1164700 | 500 | 250 | 14+14 | 28 | 16.1 | 71.3 | 10 |
| RouteStick | hard | 最长 | val-ep43 | 1164300 | 700 | 350 | 20+20 | 40 | 22.5 | 99.9 | 14 |
| BinFill | easy | 最短 | test-ep17 | 541700 | 249 | 0 | 0+14 | 14 | 8.0 | 35.4 | 3 |
| BinFill | easy | 中位 | test-ep9 | 540900 | 455 | 0 | 0+27 | 27 | 14.6 | 64.9 | 5 |
| BinFill | easy | 最长 | test-ep8 | 540800 | 699 | 0 | 0+42 | 42 | 22.5 | 99.7 | 7 |
| BinFill | medium | 最短 | val-ep26 | 1042600 | 399 | 0 | 0+23 | 23 | 12.8 | 56.9 | 5 |
| BinFill | medium | 中位 | test-ep46 | 544600 | 637 | 0 | 0+38 | 38 | 20.5 | 90.9 | 7 |
| BinFill | medium | 最长 | test-ep2 | 540201 | 837 | 0 | 0+51 | 51 | 27.0 | 119.4 | 9 |
| BinFill | hard | 最短 | val-ep43 | 1044300 | 608 | 0 | 0+36 | 36 | 19.6 | 86.7 | 7 |
| BinFill | hard | 中位 | val-ep23 | 1042300 | 922 | 0 | 0+56 | 56 | 29.7 | 131.6 | 11 |
| BinFill | hard | 最长 | val-ep11 | 1041100 | 1097 | 0 | 0+67 | 67 | 35.4 | 156.6 | 11 |
| PickXtimes | easy | 最短 | val-ep32 | 1013200 | 270 | 0 | 0+15 | 15 | 8.7 | 38.4 | 3 |
| PickXtimes | easy | 中位 | val-ep12 | 1011200 | 442 | 0 | 0+26 | 26 | 14.2 | 63.0 | 5 |
| PickXtimes | easy | 最长 | test-ep0 | 510000 | 693 | 0 | 0+42 | 42 | 22.3 | 98.9 | 7 |
| PickXtimes | medium | 最短 | test-ep10 | 511000 | 298 | 0 | 0+17 | 17 | 9.6 | 42.4 | 3 |
| PickXtimes | medium | 中位 | val-ep18 | 1011800 | 432 | 0 | 0+25 | 25 | 13.9 | 61.6 | 5 |
| PickXtimes | medium | 最长 | val-ep2 | 1010200 | 648 | 0 | 0+39 | 39 | 20.9 | 92.4 | 7 |
| PickXtimes | hard | 最短 | val-ep43 | 1014300 | 677 | 0 | 0+41 | 41 | 21.8 | 96.6 | 9 |
| PickXtimes | hard | 中位 | val-ep23 | 1012300 | 795 | 0 | 0+48 | 48 | 25.6 | 113.4 | 11 |
| PickXtimes | hard | 最长 | val-ep27 | 1012700 | 1006 | 0 | 0+61 | 61 | 32.4 | 143.6 | 11 |

### 时序数轴：窗口、subgoal 与帧路叠在一根轴上

每张图 9 行 = 3 难度 × {最短, 中位, 最长}，同一任务内共用横轴。一行从下到上四层：**subgoal 分段**（灰色交替块，块内是压缩后的中文标签）、**帧路 N=8**（红点）、**motion 窗口**（demo 蓝 / exec 绿；窗口长 33、stride 16 有 50% 重叠，所以奇偶窗口分两行错开画，能直接数出个数）、**帧路 N=32**（紫色细竖线）。段短于 33 帧铺不出窗口，画成橙色虚线空框。

> 同一份内容的**交互版**（难度档切换、悬停看 subgoal 原文、横轴跨档固定）：[采样窗口数轴](https://claude.ai/code/artifact/093a467c-d567-466b-b57e-e4fdee2bcac0)

![PatternLock 采样窗口时序数轴](figures/sampling_PatternLock.png)

![RouteStick 采样窗口时序数轴](figures/sampling_RouteStick.png)

![BinFill 采样窗口时序数轴](figures/sampling_BinFill.png)

![PickXtimes 采样窗口时序数轴](figures/sampling_PickXtimes.png)

### 产不出 motion token 的 episode

窗口长 33 帧，段短于 33 帧就一个窗口都铺不出来。这类 episode 在 motion store 里**没有任何 motion token**，做窗口级训练/评测时要单独处理：

| 任务 | 来源 | seed | 难度 | T | demo 段长 | exec 段长 |
| --- | --- | --- | --- | --- | --- | --- |
| PatternLock | test-ep25 | 652500 | easy | 50 | 25 | 25 |
| PatternLock | test-ep29 | 652900 | easy | 64 | 32 | 32 |
| PatternLock | val-ep25 | 1152500 | easy | 64 | 32 | 32 |
| PatternLock | val-ep28 | 1152800 | easy | 64 | 32 | 32 |
| PatternLock | val-ep32 | 1153200 | easy | 50 | 25 | 25 |

### demo 段占了 Imitation 的一半

PatternLock / RouteStick 的每条 episode 把同一组动作走了两遍——前一遍是给模型看的示范（`is_video_demo=True`），后一遍才是真正执行。实测演示段**恰好占整条长度的 50%**，而窗口不跨段，所以 demo 与 exec 的窗口数也基本对半：

| 任务 | 演示段合计 | 执行段合计 | 演示占比 | demo 窗口合计 | exec 窗口合计 |
| --- | --- | --- | --- | --- | --- |
| PatternLock | 10244 | 10244 | 50.0% | 487 | 487 |
| RouteStick | 18500 | 18500 | 50.0% | 1010 | 1010 |

BinFill / PickXtimes 没有演示段，整条都是 exec，所以 demo 窗口恒为 0。

## 时长来源

| 任务 | 数据来源 |
| --- | --- |
| PatternLock | val 来自原版 h5 `/data/hongzefu/data-0306/record_dataset_PatternLock.h5`；test 本机无官方 h5，由本轮按 test metadata 死 seed 实跑生成 |
| RouteStick | val 来自原版 h5 `/data/hongzefu/data-0306/record_dataset_RouteStick.h5`；test 本机无官方 h5，由本轮按 test metadata 死 seed 实跑生成 |
| BinFill | val 来自原版 h5 `/data/hongzefu/data-0306/record_dataset_BinFill.h5`；test 本机无官方 h5，由本轮按 test metadata 死 seed 实跑生成 |
| PickXtimes | val 来自原版 h5 `/data/hongzefu/data-0306/record_dataset_PickXtimes.h5`；test 本机无官方 h5，由本轮按 test metadata 死 seed 实跑生成 |

## 校验

1. **复算 vs h5 逐条对拍**（`cross_check.py`）：比对 seed、难度、move 次数（= h5 执行段数）、move 语义串（= h5 段名串），并检查 h5 内部演示段与执行段是否同一组 move。**四个源 200 条全部一致**（val 见 `outputs/cross_check.json`，test 见 `outputs/cross_check_test.json`）。语义串是从复算坐标算出来的方向，所以这一项同时验证了坐标。
2. **test seed 一致性**（`check_test_seeds.py`）：本轮实跑 100 条全部 attempt=0 一次通过，seed 与 test metadata **逐条相等，0 条不一致**，即拿到的时长就是原版 seed 下的时长（`outputs/test_seed_check.json`）。
3. **口径自洽（Imitation）**：RouteStick 满足「整条时长 = move 段数 × 50」；两个 env 的 move 段数都是偶数（演示段与执行段成对）。
4. **goal 解析自洽（Counting）**：`核心段数 == 2 × 动作次数 + 1`，**四个源 200 条全中**；另外 val 侧用 h5 的 `setup/task_goal` 校验过从 eval `video` 字段解析的 goal，48/48 相同。
5. **Counting 的 test seed 锁死**：BinFill / PickXtimes 的 test metadata 里有 9 条 seed 尾号非 0，生成型入口会从 attempt=0 重算而拿到另一个场景，因此改用 `run_test_fixed_seed.py` 逐条锁死 seed、`max_attempts=1`。实跑 100 条全部成功，seed **逐条相等、0 条不一致**。

同难度下 test 与 val 的统计高度吻合，是当前环境代码与原版行为一致的旁证。

## 这些参数怎么影响策略成功率

把 policy 侧三轮 eval 的逐集结果按动作参数分组，就能看出成功率随哪些参数塌陷。

- **数据来源**（只读）：`/data/hongzefu/robomme_policy_learning_MotionJEPA/docs/training-doc/` 下的
  `eval-{medium,hard}-patternlock-routestick/records/{context,modul}/` 与
  `eval-binfill-pickxtimes/records/{hard,medium}/{context,modul}/`（后者难度档在 records 下面一层）。
- **两个变体**：framesample 的官方两档 —— `perceptual-framesamp-modul`（上游脚本默认）与
  `perceptual-framesamp-context`（本基准原先锁死的那个）。三轮同一批 ckpt 79999、同 seed 42，
  policy 侧已用 `PARAM_TREE_EXACT=PASS n_model=61 n_ckpt=61` 证明权重同一。
- **覆盖范围**：四个任务完全相同 —— 每个 `(task, split)` 的 50 条 metadata 是 easy 26 / medium 12 / hard 12，
  eval 跑的是 **medium 全 12 条 + hard 全 12 条**（各难度跑满全集，不是抽样），**easy 26 条一条未跑**。
  每任务 test 24 + val 24 = 48 集，四任务合计 384 条（2 变体 × 2 难度 × 96）。
- **参数从哪来**：PatternLock / RouteStick 用 seed 离线复算（见上文）；
  BinFill / PickXtimes 直接解析 eval 记录里的 task_goal（要放几个什么颜色的 cube、重复几次），
  该解析已用 val 侧 h5 的 `setup/task_goal` 逐条校验，48/48 相同。
- **误差棒**：Wilson 95% 置信区间。每格只有个位数到十几条样本，
  0 成功的格子画出来是一根从 0 起的竖线（点估计 0，上界不为 0），不是缺数据。

### 总体（分难度）

每格 24 集（test 12 + val 12），suite 合计每格 48 集。easy 档未评测。

| suite | 任务 | 难度 | framesamp-modul | framesamp-context |
| --- | --- | --- | --- | --- |
| Imitation | PatternLock | medium | 13/24（54.2%） | 0/24（0.0%） |
| Imitation | PatternLock | hard | 4/24（16.7%） | 0/24（0.0%） |
| Imitation | RouteStick | medium | 10/24（41.7%） | 2/24（8.3%） |
| Imitation | RouteStick | hard | 4/24（16.7%） | 0/24（0.0%） |
| **Imitation 合计** | | **medium** | **23/48（47.9%）** | **2/48（4.2%）** |
| **Imitation 合计** | | **hard** | **8/48（16.7%）** | **0/48（0.0%）** |
| Counting | BinFill | medium | 10/24（41.7%） | 9/24（37.5%） |
| Counting | BinFill | hard | 1/24（4.2%） | 0/24（0.0%） |
| Counting | PickXtimes | medium | 21/24（87.5%） | 12/24（50.0%） |
| Counting | PickXtimes | hard | 20/24（83.3%） | 4/24（16.7%） |
| **Counting 合计** | | **medium** | **31/48（64.6%）** | **21/48（43.8%）** |
| **Counting 合计** | | **hard** | **21/48（43.8%）** | **4/48（8.3%）** |

**变体差异是逐任务的，不是全局的。** BinFill 上两个变体统计上毫无差异
（policy 侧 result.md 的任务级 Fisher 单尾 p，hard 与 medium 两档**均为 0.50**），
而 PickXtimes 上差距悬殊。把两个任务平均成一个 suite 数字会把这个结构完全抹掉。

**难度效应（medium 比 hard 高多少）是判断模型是否真在工作的关键量。** policy 侧对这八组做过
Fisher 检验：**四组里唯有 context-on-Imitation 失去了难度效应**（p = 0.247，不显著），
其余三组降低难度都带来显著提升。所以 context 的问题是**在 Imitation suite 上失灵**，
而不是普遍能力弱 —— 同一份权重在 Counting 的 medium 档达 43.75%，与 modul 在 Imitation
medium 的 47.92% 相当。

### Imitation suite：成功率 vs move 次数

![Imitation 成功率 vs move 次数](figures/success_by_moves_imitation.png)

两个任务都随 move 次数上行而塌陷（不是严格单调：PatternLock 的 2 次与 3 次基本持平，
RouteStick 的 6 次那格只有 3 条样本、置信区间几乎覆盖满量程）：

- PatternLock（modul）：2~3 次 move 13/18（72%），4 次掉到 4/17（24%），**5 次及以上 0/13（0%）**。
- RouteStick（modul）：4 次 10/18（56%），5 次 3/19（16%），6 次 1/3（33%）（样本仅 3 条，不足以判读），7 次 0/8（0%）。

context 在这两个任务上几乎全零，没有可读的趋势。

### Counting suite：成功率 vs 动作次数

![Counting 成功率 vs 动作次数](figures/success_by_actions_counting.png)

**这张图是两个变体最锋利的分界，而且两个任务的形状完全不同：**

- **BinFill**：两条曲线几乎重合 —— 放 2 个 cube 时 modul 6/8（75%）、context 6/8（75%）（完全相同）；放 3 个就双双跌到 2/14（14%） 与 2/14（14%）；4~5 个时 modul 3/26（12%）、context 1/26（4%）。**两个变体在这个任务上是同一条曲线**，瓶颈是任务本身而不是 framesample 策略。
- **PickXtimes**：modul 几乎不随次数下降 —— 1 次 8/8（100%）、3 次 8/8（100%）、4~5 次 20/24（83%）；而 context 随次数一路塌陷 —— 1 次 7/8（88%）、3 次 2/8（25%）、4~5 次 4/24（17%）。**次数越多，两者差距越大**：这正是「要记住自己已经搬了几次」的能力差异。

（PickXtimes modul 在 2 次那格反而低于 1 次和 3 次，只有 8 条样本，置信区间与两侧大幅重叠，不构成反例。）

### Imitation suite：轨迹的曲折程度

![Imitation 转角与折返](figures/success_by_imitation_turns.png)

**转角次数**（相邻两步方向不同就算一次转向）比 move 次数更贴近「这条轨迹有多难跟」：

- PatternLock（modul）：1 次转角 7/9（78%），2 次 8/17（47%），3 次 2/11（18%），**4 次及以上 0/11（0%）**。
- RouteStick（modul）：0~3 次 14/35（40%），**4 次及以上 0/13（0%）**。

**折返次数**（走到 j 又退回 i）只有 RouteStick 有 —— PatternLock 的路径由 DFS 生成、不重复节点，折返恒为 0。RouteStick（modul）：0 次 2/5（40%），1 次 9/24（38%），2 次 3/7（43%），**3 次及以上 0/12（0%）**。

折返 0~2 次之间没有明显差别，说明「退回原地」本身不难；难的是折返多了以后轨迹整体变长变绕。

### BinFill：目标的颜色种类数

![BinFill 颜色种类数](figures/success_by_binfill_color.png)

这一项比 cube 总数更能说明 BinFill 难在哪：目标只涉及 1 种颜色时两个变体都是 9/18（50%）；涉及 2 种时 modul 2/23（9%）、context 0/23（0%）；3 种时两者都是 0/7（0%）。

**要同时按颜色分类并计数，两个变体都做不到**——这也解释了为什么 BinFill 上两个变体没有差异：瓶颈不在 framesample 怎么采帧，而在任务本身需要的组合能力。

> 顺带一个 env 配置层面的注意点：PickXtimes 的 medium 与 easy 的重复次数范围相同（都是 1~3 次），
> medium 的难点在于场上同时有 3 种颜色的 cube 作干扰，而不是次数更多；hard 才是 4~5 次。
> 所以 PickXtimes 的难度档之间不能只按「次数」理解。

> 图与数字由 `plot_eval_success.py` 生成，改动 eval 结果后重跑即可。
