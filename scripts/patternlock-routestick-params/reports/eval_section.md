## eval 成功率

- **数据来源**（只读）：`/data/hongzefu/robomme_policy_learning_MotionJEPA/docs/training-doc/` 下的
  `eval-{medium,hard}-patternlock-routestick/records/{context,modul}/` 与
  `eval-binfill-pickxtimes/records/{hard,medium}/{context,modul}/`（后者难度档在 records 下面一层）。
- **两个变体**：`perceptual-framesamp-modul` 与 `perceptual-framesamp-context`，同一批 ckpt 79999、同 seed 42。
- **覆盖范围**：每个 `(task, split)` 的 50 条 metadata 是 easy 26 / medium 12 / hard 12，eval 跑 medium 全 12 条 + hard 全 12 条，**easy 未跑**。每任务 test 24 + val 24 = 48 集，四任务合计 384 条。
- **分组参数**：PatternLock / RouteStick 由 seed 离线复算；BinFill / PickXtimes 解析 task_goal。
- **误差棒**：Wilson 95% 置信区间。0 成功的格子画成一根从 0 起的竖线（点估计 0，上界不为 0）。

### 分难度

每格 24 集（test 12 + val 12）；任务的 medium+hard 合计每格 48 集，suite 合计每格 48 集。

| suite | 任务 | 难度 | framesamp-modul | framesamp-context |
| --- | --- | --- | --- | --- |
| Imitation | PatternLock | medium | 13/24（54.2%） | 0/24（0.0%） |
| Imitation | PatternLock | hard | 4/24（16.7%） | 0/24（0.0%） |
| Imitation | **PatternLock** | **medium+hard** | **17/48（35.4%）** | **0/48（0.0%）** |
| Imitation | RouteStick | medium | 10/24（41.7%） | 2/24（8.3%） |
| Imitation | RouteStick | hard | 4/24（16.7%） | 0/24（0.0%） |
| Imitation | **RouteStick** | **medium+hard** | **14/48（29.2%）** | **2/48（4.2%）** |
| **Imitation 合计** | | **medium** | **23/48（47.9%）** | **2/48（4.2%）** |
| **Imitation 合计** | | **hard** | **8/48（16.7%）** | **0/48（0.0%）** |
| Counting | BinFill | medium | 10/24（41.7%） | 9/24（37.5%） |
| Counting | BinFill | hard | 1/24（4.2%） | 0/24（0.0%） |
| Counting | **BinFill** | **medium+hard** | **11/48（22.9%）** | **9/48（18.8%）** |
| Counting | PickXtimes | medium | 21/24（87.5%） | 12/24（50.0%） |
| Counting | PickXtimes | hard | 20/24（83.3%） | 4/24（16.7%） |
| Counting | **PickXtimes** | **medium+hard** | **41/48（85.4%）** | **16/48（33.3%）** |
| **Counting 合计** | | **medium** | **31/48（64.6%）** | **21/48（43.8%）** |
| **Counting 合计** | | **hard** | **21/48（43.8%）** | **4/48（8.3%）** |

### 成功率 vs 动作次数

![Imitation 成功率 vs move 次数](figures/success_by_moves_imitation.png)

![Counting 成功率 vs 动作次数](figures/success_by_actions_counting.png)

Imitation 的 x 轴是 move 次数；Counting 的 x 轴是 BinFill 要放进 bin 的 cube 总数 / PickXtimes 同一动作的重复次数。medium 与 hard 合并。

### 成功率 vs 路径形状（Imitation）

![Imitation 路径形状](figures/success_by_imitation_turns.png)

两个任务各用一个语义成立的维度：

- **PatternLock 转角次数** = 相邻两步的 8 方位不同的次数。它的 move 是格点上的八方位移动，方向变了就是拐了个弯。
- **RouteStick 折返次数** = 路径里走到 j 又退回 i 的次数。它是在 1×9 一字排开的格点上左右走，**没有「转角」这回事**；另外「左右切换次数」与折返次数在 100 条上逐条相等（同一件事），故不重复列。

PatternLock 的路径由 DFS 生成、不重复节点，折返恒为 0，所以它没有折返这一档。

### 成功率 vs 目标颜色种类数（BinFill）

![BinFill 颜色种类数](figures/success_by_binfill_color.png)

颜色种类数 = 该 episode 的目标里涉及几种颜色的 cube（1 / 2 / 3）。

> 图与数字由 `plot_eval_success.py` 生成，改动 eval 结果后重跑即可。
