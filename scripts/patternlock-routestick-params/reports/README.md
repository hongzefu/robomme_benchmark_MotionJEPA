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
