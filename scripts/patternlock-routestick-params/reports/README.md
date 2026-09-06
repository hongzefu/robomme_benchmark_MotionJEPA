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

| 源 | 条数 | 动作次数（min~max） | 动作次数均值 | 单段时长（min~max） | 单段时长均值 |
| --- | --- | --- | --- | --- | --- |
| [BinFill-test](BinFill-test.md) | 26 | 1~3 | 1.96 | 42~210 ts | 86.7 ts |
| [BinFill-val](BinFill-val.md) | 26 | 1~3 | 1.85 | 44~208 ts | 87.3 ts |
| [PickXtimes-test](PickXtimes-test.md) | 26 | 1~3 | 1.92 | 44~200 ts | 83.8 ts |
| [PickXtimes-val](PickXtimes-val.md) | 26 | 1~3 | 2.04 | 43~189 ts | 81.6 ts |

### medium

BinFill：2 种颜色、spawn 8~10 个，目标涉及 1~2 种颜色、总数 ∈ [2, 4]。PickXtimes：**重复次数区间与 easy 相同（[1, 3]）**，难点在于场上有 3 种颜色的 cube 作干扰。

| 源 | 条数 | 动作次数（min~max） | 动作次数均值 | 单段时长（min~max） | 单段时长均值 |
| --- | --- | --- | --- | --- | --- |
| [BinFill-test](BinFill-test.md) | 12 | 2~4 | 3.17 | 48~151 ts | 84.1 ts |
| [BinFill-val](BinFill-val.md) | 12 | 2~4 | 2.83 | 52~195 ts | 86.1 ts |
| [PickXtimes-test](PickXtimes-test.md) | 12 | 1~3 | 1.83 | 53~163 ts | 81.6 ts |
| [PickXtimes-val](PickXtimes-val.md) | 12 | 1~3 | 2.17 | 49~145 ts | 80.7 ts |

### hard

BinFill：3 种颜色、spawn 10~12 个，目标涉及 2~3 种颜色、总数 ∈ [3, 5]。PickXtimes：3 种颜色，重复次数 ∈ [4, 5]。

| 源 | 条数 | 动作次数（min~max） | 动作次数均值 | 单段时长（min~max） | 单段时长均值 |
| --- | --- | --- | --- | --- | --- |
| [BinFill-test](BinFill-test.md) | 12 | 3~5 | 4.25 | 49~178 ts | 89.8 ts |
| [BinFill-val](BinFill-val.md) | 12 | 3~5 | 4.17 | 50~182 ts | 86.6 ts |
| [PickXtimes-test](PickXtimes-test.md) | 12 | 4~5 | 4.50 | 49~197 ts | 76.3 ts |
| [PickXtimes-val](PickXtimes-val.md) | 12 | 4~5 | 4.50 | 42~162 ts | 74.2 ts |

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

### 总体

| suite | 任务 | framesamp-modul | framesamp-context |
| --- | --- | --- | --- |
| Imitation | PatternLock | 17/48（35.4%） | 0/48（0.0%） |
| Imitation | RouteStick | 14/48（29.2%） | 2/48（4.2%） |
| **Imitation 合计** | | **31/96（32.3%）** | **2/96（2.1%）** |
| Counting | BinFill | 11/48（22.9%） | 9/48（18.8%） |
| Counting | PickXtimes | 41/48（85.4%） | 16/48（33.3%） |
| **Counting 合计** | | **52/96（54.2%）** | **25/96（26.0%）** |

**最重要的一点：变体差异是逐任务的，不是全局的。** BinFill 上两个变体统计上毫无差异
（policy 侧 result.md 的任务级 Fisher 单尾 p，hard 与 medium 两档**均为 0.50**），
而 PickXtimes 上差距悬殊。把两个任务平均成一个 suite 数字会把这个结构完全抹掉。

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
