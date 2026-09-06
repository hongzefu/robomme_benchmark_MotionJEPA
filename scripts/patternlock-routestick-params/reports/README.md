# PatternLock / RouteStick 的 test+val 源逐 episode 动作参数

四个源各 50 条，共 200 个 episode。每个 episode 给出：move 了几次、每次 move 的起终点坐标、每次 move 占多少 timestep。明细见同目录的四份分源报告。

## 口径

- **seed / 难度**：一律读 `src/robomme/env_metadata/{test,val}/record_dataset_{Task}_metadata.json`，不用公式反推（存在 attempt 尾号例外，如 PatternLock-val ep37 = 1153701）。
- **move 次数与坐标**：不需要跑仿真。两个 env 的场景随机段只用一个 `torch.Generator(seed)`，消费顺序确定，离线重跑一遍随机数即可还原（`derive_episode_params.py`）。
- **坐标**：SAPIEN 世界坐标，单位米，机器人 base 在 `(-0.615, 0, 0)`。表里是按钮本身的位置（PatternLock z=0.01；RouteStick 偶数下标 z=0.01）；规划实际下发的终点高度统一抬到 z=0.07。
- **时长**：1 timestep = 1 个 env step = 0.05 s（控制频率 20 Hz），与数据集的采样频率一致。录像 fps=30 与 timestep 不等长，报告里不用视频帧。
- **演示段 / 执行段**：同一组 move 在数据里出现两遍——前一遍 `is_video_demo=True` 是给模型看的示范，后一遍才是真正 rollout。表中两列分开给。每条 episode 末尾还有一个几到十几 timestep 的收尾段，不算 move。

## 各源总览

| 源 | 条数 | 难度分布 | move 次数（min~max，均值） | move 总数 | 单次 move 时长 | 整条时长 | 时长来源 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [PatternLock-test](PatternLock-test.md) | 50 | easy 26/hard 12/medium 12 | 1~7，3.10 | 155 | 14~52 ts（均值 30.5） | 50~516 ts | 本轮按 test metadata 死 seed 实跑生成 |
| [PatternLock-val](PatternLock-val.md) | 50 | easy 26/hard 12/medium 12 | 1~7，2.98 | 149 | 14~52 ts（均值 30.7） | 50~510 ts | 原版 h5 `/data/hongzefu/data-0306/record_dataset_PatternLock.h5` |
| [RouteStick-test](RouteStick-test.md) | 50 | easy 26/hard 12/medium 12 | 2~7，3.66 | 183 | 43~50 ts（均值 48.1） | 200~700 ts | 本轮按 test metadata 死 seed 实跑生成 |
| [RouteStick-val](RouteStick-val.md) | 50 | easy 26/hard 12/medium 12 | 2~7，3.74 | 187 | 43~50 ts（均值 48.1） | 200~700 ts | 原版 h5 `/data/hongzefu/data-0306/record_dataset_RouteStick.h5` |

## 校验

1. **复算 vs h5 逐条对拍**（`cross_check.py`）：比对 seed、难度、move 次数（= h5 执行段数）、move 语义串（= h5 段名串），并检查 h5 内部演示段与执行段是否同一组 move。**四个源 200 条全部一致**（val 见 `outputs/cross_check.json`，test 见 `outputs/cross_check_test.json`）。语义串是从复算坐标算出来的方向，所以这一项同时验证了坐标。
2. **test seed 一致性**（`check_test_seeds.py`）：本轮实跑 100 条全部 attempt=0 一次通过，seed 与 test metadata **逐条相等，0 条不一致**，即拿到的时长就是原版 seed 下的时长（`outputs/test_seed_check.json`）。
3. **口径自洽**：RouteStick 满足「整条时长 = 段数 × 50」；两个 env 的 move 段数都是偶数（演示段与执行段成对）。

test 与 val 的统计高度吻合（PatternLock 单次 move 均值 30.5 vs 30.7，RouteStick 均为 48.1），这是当前环境代码与原版行为一致的旁证。
