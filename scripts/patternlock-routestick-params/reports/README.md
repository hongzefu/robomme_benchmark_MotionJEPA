# PatternLock / RouteStick 的 test+val 源逐 episode 动作参数

四个源各 50 条，共 200 个 episode。每个 episode 给出：move 了几次、每次 move 的起终点坐标、每次 move 占多少 timestep。明细见同目录的四份分源报告。

## 口径

- **seed / 难度**：一律读 `src/robomme/env_metadata/{test,val}/record_dataset_{Task}_metadata.json`，不用公式反推（存在 attempt 尾号例外，如 PatternLock-val ep37 = 1153701）。
- **move 次数与坐标**：不需要跑仿真。两个 env 的场景随机段只用一个 `torch.Generator(seed)`，消费顺序确定，离线重跑一遍随机数即可还原（`derive_episode_params.py`）。
- **坐标**：SAPIEN 世界坐标，单位米，机器人 base 在 `(-0.615, 0, 0)`。表里是按钮本身的位置（PatternLock z=0.01；RouteStick 偶数下标 z=0.01）；规划实际下发的终点高度统一抬到 z=0.07。
- **时长**：1 timestep = 1 个 env step = 0.05 s（控制频率 20 Hz），与数据集的采样频率一致。录像 fps=30 与 timestep 不等长，报告里不用视频帧。
- **演示段 / 执行段**：同一组 move 在数据里出现两遍——前一遍 `is_video_demo=True` 是给模型看的示范，后一遍才是真正 rollout。下面的时长统计只算执行段。每条 episode 末尾还有一个几到十几 timestep 的收尾段，不算 move。

## 按难度分组

难度是决定 move 次数的唯一配置项（env 的 `configs[difficulty]`），所以统计一律按难度分开看。四个源的难度分布相同：easy 26 / medium 12 / hard 12（难度循环 `211`，按 `episode % 4`）。

### easy

PatternLock：3×3 格点，路径长度约束 `[2, 4]` → move 1~3 次。RouteStick：`steps ∈ [2, 3]`，不允许原地折返。

| 源 | 条数 | move 次数（min~max） | move 次数均值 | 单次 move 时长（min~max） | 单次 move 时长均值 |
| --- | --- | --- | --- | --- | --- |
| [PatternLock-test](PatternLock-test.md) | 26 | 1~3 | 2.15 | 16~40 ts | 28.1 ts |
| [PatternLock-val](PatternLock-val.md) | 26 | 1~3 | 1.96 | 15~38 ts | 28.2 ts |
| [RouteStick-test](RouteStick-test.md) | 26 | 2~3 | 2.46 | 43~50 ts | 47.2 ts |
| [RouteStick-val](RouteStick-val.md) | 26 | 2~3 | 2.50 | 43~50 ts | 47.2 ts |

### medium

PatternLock：4×4 格点，路径长度约束 `[3, 5]` → move 2~4 次。RouteStick：`steps ∈ [4, 5]`，不允许原地折返。

| 源 | 条数 | move 次数（min~max） | move 次数均值 | 单次 move 时长（min~max） | 单次 move 时长均值 |
| --- | --- | --- | --- | --- | --- |
| [PatternLock-test](PatternLock-test.md) | 12 | 2~4 | 3.25 | 14~47 ts | 31.3 ts |
| [PatternLock-val](PatternLock-val.md) | 12 | 2~4 | 3.00 | 14~47 ts | 30.0 ts |
| [RouteStick-test](RouteStick-test.md) | 12 | 4~5 | 4.58 | 43~50 ts | 48.5 ts |
| [RouteStick-val](RouteStick-val.md) | 12 | 4~5 | 4.42 | 43~50 ts | 48.4 ts |

### hard

PatternLock：5×5 格点，路径长度约束 `[4, 8]` → move 3~7 次。RouteStick：`steps ∈ [4, 7]`，**允许原地折返**（`backtrack=True`）。

| 源 | 条数 | move 次数（min~max） | move 次数均值 | 单次 move 时长（min~max） | 单次 move 时长均值 |
| --- | --- | --- | --- | --- | --- |
| [PatternLock-test](PatternLock-test.md) | 12 | 3~7 | 5.00 | 17~52 ts | 32.2 ts |
| [PatternLock-val](PatternLock-val.md) | 12 | 3~7 | 5.17 | 15~52 ts | 33.2 ts |
| [RouteStick-test](RouteStick-test.md) | 12 | 4~7 | 5.33 | 43~50 ts | 48.7 ts |
| [RouteStick-val](RouteStick-val.md) | 12 | 4~7 | 5.75 | 43~50 ts | 48.8 ts |

## Counting suite（BinFill / PickXtimes）

这两个任务的结构与上面两个不同：**没有视频演示段**，动作是 pick / place 成对再加一次 press button，
「动作次数」= BinFill 要放进 bin 的 cube 总数 / PickXtimes 同一动作的重复次数，直接写在 `setup/task_goal` 里。核心段数 = 2 × 动作次数 + 1（每条都验过）。

### easy

BinFill：场上 1 种颜色、spawn 4~6 个 cube，要放进 bin 的 `put_in_numbers ∈ [1, 3]`。PickXtimes：场上 1 种颜色，重复次数 ∈ [1, 3]。

| 源 | 条数 | 动作次数（min~max） | 动作次数均值 | pick up 时长 | put / place 时长 | press 时长 |
| --- | --- | --- | --- | --- | --- | --- |
| [BinFill-test](BinFill-test.md) | 26 | 1~3 | 1.96 | 115.7（78~210） | 69.8（54~93） | 63.2（42~80） |
| [BinFill-val](BinFill-val.md) | 26 | 1~3 | 1.85 | 116.7（84~208） | 70.0（52~93） | 64.9（44~78） |
| [PickXtimes-test](PickXtimes-test.md) | 26 | 1~3 | 1.92 | 103.1（69~200） | 76.2（53~103） | 61.5（44~73） |
| [PickXtimes-val](PickXtimes-val.md) | 26 | 1~3 | 2.04 | 98.4（69~189） | 74.4（53~107） | 61.9（43~75） |

### medium

BinFill：2 种颜色、spawn 8~10 个，目标涉及 1~2 种颜色、总数 ∈ [2, 4]。PickXtimes：**重复次数区间与 easy 相同（[1, 3]）**，难点在于场上有 3 种颜色的 cube 作干扰。

| 源 | 条数 | 动作次数（min~max） | 动作次数均值 | pick up 时长 | put / place 时长 | press 时长 |
| --- | --- | --- | --- | --- | --- | --- |
| [BinFill-test](BinFill-test.md) | 12 | 2~4 | 3.17 | 107.7（76~151） | 67.4（52~92） | 62.6（48~80） |
| [BinFill-val](BinFill-val.md) | 12 | 2~4 | 2.83 | 109.7（82~195） | 68.8（52~92） | 68.0（52~87） |
| [PickXtimes-test](PickXtimes-test.md) | 12 | 1~3 | 1.83 | 96.6（70~163） | 76.3（53~110） | 63.9（54~75） |
| [PickXtimes-val](PickXtimes-val.md) | 12 | 1~3 | 2.17 | 94.8（69~145） | 74.7（53~100） | 62.8（49~77） |

### hard

BinFill：3 种颜色、spawn 10~12 个，目标涉及 2~3 种颜色、总数 ∈ [3, 5]。PickXtimes：3 种颜色，重复次数 ∈ [4, 5]。

| 源 | 条数 | 动作次数（min~max） | 动作次数均值 | pick up 时长 | put / place 时长 | press 时长 |
| --- | --- | --- | --- | --- | --- | --- |
| [BinFill-test](BinFill-test.md) | 12 | 3~5 | 4.25 | 111.1（77~178） | 72.6（49~96） | 72.2（51~126） |
| [BinFill-val](BinFill-val.md) | 12 | 3~5 | 4.17 | 106.9（80~182） | 71.6（53~99） | 64.1（50~79） |
| [PickXtimes-test](PickXtimes-test.md) | 12 | 4~5 | 4.50 | 86.9（68~197） | 68.9（52~108） | 62.3（49~75） |
| [PickXtimes-val](PickXtimes-val.md) | 12 | 4~5 | 4.50 | 85.0（69~162） | 66.2（53~111） | 61.3（42~74） |

三类动作的性质不同，所以分开统计（表里给的是**均值（min~max）**，单位 timestep）：
`pick up` 要在一堆 cube 里找到指定的那个并抓起来；`put / place` 是把手里的东西送到一个
固定位置（BinFill 的 bin / PickXtimes 的 target）；`press` 只是按一下按钮。
每次动作产生一对 pick + place，每条 episode 末尾另有一段 press。

## 任务长度与可切分区间

整条 episode 的 timestep 数（1 timestep = 1 个 env step = 0.05 s），以及按固定 delta **不重叠**切分时能切出多少个完整区间 —— 即 `floor(T / delta)`。

| 源 | 条数 | 整条长度 min~max | 均值 | 中位 | delta=32 | delta=16 | delta=8 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PatternLock-test | 50 | 50~516 | 208.8 | 192 | 1~16 | 3~32 | 6~64 |
| PatternLock-val | 50 | 50~510 | 201.0 | 186 | 1~15 | 3~31 | 6~63 |
| RouteStick-test | 50 | 200~700 | 366.0 | 300 | 6~21 | 12~43 | 25~87 |
| RouteStick-val | 50 | 200~700 | 374.0 | 300 | 6~21 | 12~43 | 25~87 |
| BinFill-test | 50 | 249~1080 | 613.3 | 626 | 7~33 | 15~67 | 31~135 |
| BinFill-val | 50 | 263~1097 | 583.2 | 599 | 8~34 | 16~68 | 32~137 |
| PickXtimes-test | 50 | 283~928 | 524.6 | 523 | 8~29 | 17~58 | 35~116 |
| PickXtimes-val | 50 | 270~1006 | 534.7 | 514 | 8~31 | 16~62 | 33~125 |

整个源（50 条）合计能切出的区间数：

| 源 | timestep 合计 | delta=32 | delta=16 | delta=8 |
| --- | --- | --- | --- | --- |
| PatternLock-test | 10438 | 309 | 634 | 1289 |
| PatternLock-val | 10050 | 292 | 608 | 1240 |
| RouteStick-test | 18300 | 549 | 1122 | 2275 |
| RouteStick-val | 18700 | 561 | 1146 | 2324 |
| BinFill-test | 30663 | 932 | 1894 | 3812 |
| BinFill-val | 29159 | 888 | 1801 | 3627 |
| PickXtimes-test | 26230 | 796 | 1614 | 3257 |
| PickXtimes-val | 26735 | 809 | 1645 | 3321 |

### 按难度

长度基本由难度决定（难度直接配出动作次数），所以分档看：

**easy**

| 源 | 条数 | 整条长度 min~max | 均值 | delta=32 | delta=16 | delta=8 |
| --- | --- | --- | --- | --- | --- | --- |
| PatternLock-test | 26 | 50~210 | 140.8 | 1~6 | 3~13 | 6~26 |
| PatternLock-val | 26 | 50~226 | 127.9 | 1~7 | 3~14 | 6~28 |
| RouteStick-test | 26 | 200~300 | 246.2 | 6~9 | 12~18 | 25~37 |
| RouteStick-val | 26 | 200~300 | 250.0 | 6~9 | 12~18 | 25~37 |
| BinFill-test | 26 | 249~699 | 464.7 | 7~21 | 15~43 | 31~87 |
| BinFill-val | 26 | 263~689 | 448.0 | 8~21 | 16~43 | 32~86 |
| PickXtimes-test | 26 | 283~693 | 444.7 | 8~21 | 17~43 | 35~86 |
| PickXtimes-val | 26 | 270~661 | 452.0 | 8~20 | 16~41 | 33~82 |

**medium**

| 源 | 条数 | 整条长度 min~max | 均值 | delta=32 | delta=16 | delta=8 |
| --- | --- | --- | --- | --- | --- | --- |
| PatternLock-test | 12 | 128~304 | 222.2 | 4~9 | 8~19 | 16~38 |
| PatternLock-val | 12 | 112~302 | 199.2 | 3~9 | 7~18 | 14~37 |
| RouteStick-test | 12 | 400~500 | 458.3 | 12~15 | 25~31 | 50~62 |
| RouteStick-val | 12 | 400~500 | 441.7 | 12~15 | 25~31 | 50~62 |
| BinFill-test | 12 | 420~837 | 655.4 | 13~26 | 26~52 | 52~104 |
| BinFill-val | 12 | 399~828 | 612.2 | 12~25 | 24~51 | 49~103 |
| PickXtimes-test | 12 | 298~619 | 419.8 | 9~19 | 18~38 | 37~77 |
| PickXtimes-val | 12 | 306~648 | 468.9 | 9~20 | 19~40 | 38~81 |

**hard**

| 源 | 条数 | 整条长度 min~max | 均值 | delta=32 | delta=16 | delta=8 |
| --- | --- | --- | --- | --- | --- | --- |
| PatternLock-test | 12 | 184~516 | 342.7 | 5~16 | 11~32 | 23~64 |
| PatternLock-val | 12 | 186~510 | 361.2 | 5~15 | 11~31 | 23~63 |
| RouteStick-test | 12 | 400~700 | 533.3 | 12~21 | 25~43 | 50~87 |
| RouteStick-val | 12 | 400~700 | 575.0 | 12~21 | 25~43 | 50~87 |
| BinFill-test | 12 | 626~1080 | 892.9 | 19~33 | 39~67 | 78~135 |
| BinFill-val | 12 | 608~1097 | 847.1 | 19~34 | 38~68 | 76~137 |
| PickXtimes-test | 12 | 686~928 | 802.5 | 21~29 | 42~58 | 85~116 |
| PickXtimes-val | 12 | 677~1006 | 779.8 | 21~31 | 42~62 | 84~125 |

### 切片前必须注意：Imitation 的前一半是演示段

PatternLock / RouteStick 的每条 episode 把同一组动作走了两遍——前一遍是给模型看的示范（`is_video_demo=True`），后一遍才是真正执行。实测演示段**恰好占整条长度的 50%**：

| 源 | 演示段 | 执行段 | 收尾段 | 合计 | 演示占比 |
| --- | --- | --- | --- | --- | --- |
| PatternLock-test | 5219 | 4729 | 490 | 10438 | 50.0% |
| PatternLock-val | 5025 | 4574 | 451 | 10050 | 50.0% |
| RouteStick-test | 9150 | 8800 | 350 | 18300 | 50.0% |
| RouteStick-val | 9350 | 9000 | 350 | 18700 | 50.0% |

所以按上表的 delta 切 Imitation 的整条长度时，**约一半的区间落在演示段里**。只想要真正执行的那部分，把长度按执行段重算即可（约为整条的一半）。BinFill / PickXtimes 没有演示段，整条都是执行。

> 换成滑动窗口时，窗长 `w`、步长 `s` 的窗口数是 `floor((T - w) / s) + 1`；上表 `floor(T / delta)` 对应的是 `w = s = delta` 的不重叠切法。

## 时长来源

| 源 | 来源 |
| --- | --- |
| PatternLock-test | 本轮按 test metadata 死 seed 实跑生成 |
| PatternLock-val | 原版 h5 `/data/hongzefu/data-0306/record_dataset_PatternLock.h5` |
| RouteStick-test | 本轮按 test metadata 死 seed 实跑生成 |
| RouteStick-val | 原版 h5 `/data/hongzefu/data-0306/record_dataset_RouteStick.h5` |
| BinFill-test | 本轮按 test metadata 死 seed 实跑生成 |
| BinFill-val | 原版 h5 `/data/hongzefu/data-0306/record_dataset_BinFill.h5` |
| PickXtimes-test | 本轮按 test metadata 死 seed 实跑生成 |
| PickXtimes-val | 原版 h5 `/data/hongzefu/data-0306/record_dataset_PickXtimes.h5` |

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
