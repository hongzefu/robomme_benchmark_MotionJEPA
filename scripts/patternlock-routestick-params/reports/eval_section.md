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

### Counting suite：场景布局

![Counting 场景布局](figures/success_by_counting_layout.png)

- **BinFill 的颜色种类数**比 cube 总数更能说明问题：目标只涉及 1 种颜色时两变体都是 9/18（50%）；涉及 2 种时 modul 2/23（9%）、context 0/23（0%）；3 种时两者都是 0/7（0%）。要同时按颜色分类并计数，两个变体都做不到。
- **PickXtimes 的 cube 颜色**没有信号（三种颜色成功率相当），这正是想要的对照结果 ——  差异来自次数而不是颜色。

> 顺带一个 env 配置层面的注意点：PickXtimes 的 medium 与 easy 的重复次数范围相同（都是 1~3 次），
> medium 的难点在于场上同时有 3 种颜色的 cube 作干扰，而不是次数更多；hard 才是 4~5 次。
> 所以 PickXtimes 的难度档之间不能只按「次数」理解。

### 成功率 vs 难度档

![成功率 vs 难度档](figures/success_by_difficulty.png)

难度效应（medium 比 hard 好多少）是判断模型是否真在工作的关键量：

- Imitation：modul 23/48（47.9%） vs 8/48（16.7%）；context 2/48（4.2%） vs 0/48（0.0%）。
- Counting：modul 31/48（64.6%） vs 21/48（43.8%）；context 21/48（43.8%） vs 4/48（8.3%）。

policy 侧 result.md 对这八组做了 Fisher 检验：**四组里唯有 context-on-Imitation 失去了难度效应**
（p = 0.247，不显著），其余三组降低难度都带来显著提升。所以 context 的问题是
**在 Imitation suite 上失灵**，而不是普遍能力弱 —— 同一份权重在 Counting 的 medium 档达 43.75%，
与 modul 在 Imitation medium 的 47.92% 相当。

### split 对照

![成功率 vs split](figures/success_by_split.png)

四个任务的 test 与 val 都接近，没有明显的 split 偏置 —— 两个 split 的参数分布本来就同源
（同一套难度循环、只是 seed 域不同），这张图是用来确认这一点的。

> 图与数字由 `plot_eval_success.py` 生成，改动 eval 结果后重跑即可。
