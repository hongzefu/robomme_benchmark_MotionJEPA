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

## 时长来源

| 源 | 来源 |
| --- | --- |
| PatternLock-test | 本轮按 test metadata 死 seed 实跑生成 |
| PatternLock-val | 原版 h5 `/data/hongzefu/data-0306/record_dataset_PatternLock.h5` |
| RouteStick-test | 本轮按 test metadata 死 seed 实跑生成 |
| RouteStick-val | 原版 h5 `/data/hongzefu/data-0306/record_dataset_RouteStick.h5` |

## 校验

1. **复算 vs h5 逐条对拍**（`cross_check.py`）：比对 seed、难度、move 次数（= h5 执行段数）、move 语义串（= h5 段名串），并检查 h5 内部演示段与执行段是否同一组 move。**四个源 200 条全部一致**（val 见 `outputs/cross_check.json`，test 见 `outputs/cross_check_test.json`）。语义串是从复算坐标算出来的方向，所以这一项同时验证了坐标。
2. **test seed 一致性**（`check_test_seeds.py`）：本轮实跑 100 条全部 attempt=0 一次通过，seed 与 test metadata **逐条相等，0 条不一致**，即拿到的时长就是原版 seed 下的时长（`outputs/test_seed_check.json`）。
3. **口径自洽**：RouteStick 满足「整条时长 = move 段数 × 50」；两个 env 的 move 段数都是偶数（演示段与执行段成对）。

同难度下 test 与 val 的统计高度吻合，是当前环境代码与原版行为一致的旁证。

## 这些参数怎么影响策略成功率

把 policy 侧两轮 eval 的逐集结果按上面复算出的动作参数分组，就能看出成功率随哪些参数塌陷。

- **数据来源**：`/data/hongzefu/robomme_policy_learning_MotionJEPA/docs/training-doc/eval-{medium,hard}-patternlock-routestick/records/{context,modul}/per_episode.json`（只读）。
- **两个变体**：framesample 的官方两档 —— `perceptual-framesamp-modul`（上游脚本默认）与 `perceptual-framesamp-context`（本基准原先锁死的那个）。
- **范围**：medium 与 hard 两档 × 两变体 × 48 集 = 192 条，join 键是 `(task, split, episode)`，并逐条断言 seed 与本目录复算表相同。easy 档尚未评测。
- **误差棒**：Wilson 95% 置信区间。每格只有个位数到十几条样本，0 成功的格子画出来是一根从 0 起的竖线（点估计 0，上界不为 0），不是缺数据。

### 总体

| 变体 | PatternLock | RouteStick | 合计 |
| --- | --- | --- | --- |
| framesamp-modul | 17/48（35.4%） | 14/48（29.2%） | 31/96（32.3%） |
| framesamp-context | 0/48（0.0%） | 2/48（4.2%） | 2/96（2.1%） |

### 成功率 vs move 次数

![成功率 vs move 次数](figures/success_by_moves.png)

这是最陡的一条趋势，两个任务都随 move 次数上行而塌陷（不是严格单调：PatternLock 的 2 次与 3 次基本持平，RouteStick 的 6 次那格只有 3 条样本、置信区间几乎覆盖满量程）：

- PatternLock（modul）：2~3 次 move 13/18（72%），4 次掉到 4/17（24%），**5 次及以上 0/13（0%）**。
- RouteStick（modul）：4 次 10/18（56%），5 次 3/19（16%），6 次 1/3（33%）（样本仅 3 条，不足以判读），7 次 0/8（0%）。

换句话说，两个策略的能力边界都卡在「一条轨迹里要连续做对几步」上——而 move 次数正是 env 按难度直接配出来的（见上面的按难度分组），所以难度档之间的差距本质上就是这条曲线的不同区段。

### 成功率 vs 难度档

![成功率 vs 难度档](figures/success_by_difficulty.png)

modul 在 medium 上 23/48（47.9%），到 hard 掉成 8/48（16.7%）；context 两档分别是 2/48（4.2%） 与 0/48（0.0%）。

### PatternLock：路径布局

![PatternLock 路径布局](figures/success_by_patternlock_layout.png)

- **方向种类数**（这条路径用到几种不同的移动方向）比 move 次数更能区分难易：只用 2 种方向时成功率最高，用到 4 种以上基本归零。它和 move 次数不完全重合——同样 4 步，走「一直向右」和「右、前右、左、前左」的难度不一样。
- **起终点跨度**（曼哈顿格距）影响温和，跨 1~3 格差别不大，跨 5 格以上没有成功样本。
- **起点位置**：起点在格边上时成功率明显高于落在格点内部——内部起点四周八向都通，更容易在第一步就走错方向。注意这一项与格点尺寸耦合（3×3 几乎没有内部点），
  样本上主要反映的是 medium/hard 的差异。

### RouteStick：路径布局

![RouteStick 路径布局](figures/success_by_routestick_layout.png)

- **绕行方向切换次数**：切换 0~3 次时成功率相当（30%~50%），切到 4 次以上全灭——同样是「连续做对几步」的表现。
- **整排旋转角 |θ|**：中间档（10°~20°）反而最高，两端都低，且各档只有 16 条样本、置信区间大幅重叠，**不足以支持「旋转角影响成功率」的结论**。
- **是否原地折返**：有无折返差别不大（折返只在 hard 档允许）。

### split 对照

![成功率 vs split](figures/success_by_split.png)

test 与 val 的成功率接近，没有明显的 split 偏置——两个 split 的参数分布本来就同源（同一套难度循环、只是 seed 域不同），这张图是用来确认这一点的。

> 图与数字由 `plot_eval_success.py` 生成，改动 eval 结果后重跑即可。
