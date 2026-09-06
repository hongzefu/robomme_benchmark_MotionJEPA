# 四个任务的 test+val 逐 episode 动作参数

回答一个具体问题：**每个 episode 做了几次动作、每次动作的坐标、每次动作的时长**。
覆盖两个 suite 共四个任务、test+val 两个 split（每源 50 条，共 400 个 episode）：

| suite | 任务 | 「动作次数」指什么 |
| --- | --- | --- |
| Imitation | PatternLock、RouteStick | move 次数（看视频重现一条轨迹） |
| Counting | BinFill、PickXtimes | BinFill 要放进 bin 的 cube 总数 / PickXtimes 同一动作的重复次数 |

成品报告在 [`reports/`](reports/)：一份总览（含 policy 侧 eval 的成功率分析与图）+ 八份分源明细。

## 两个 suite 的结构差异（先看这个）

| 项 | PatternLock / RouteStick | BinFill / PickXtimes |
| --- | --- | --- |
| 视频演示段 | **有**（`is_video_demo=True` 的前半段），真实次数 = 段数 / 2 | **没有**，段数就是实际次数 |
| 子目标语义 | `move {方位}` / `move to the nearest {left,right} …` | `pick up the … cube` / `put it into the bin` / `press the button` |
| 参数从哪来 | 按 seed **离线复算**（env 的随机段可纯函数还原） | 直接读 `setup/task_goal` 与 `action/waypoint_action` |
| 段数恒等式 | —— | 核心段数 = 2 × 动作次数 + 1 |

因为段语义完全不同，两类各用一个提取器（`extract_move_durations.py` / `extract_task_params.py`），
没有硬塞进同一个函数。

## 三类参数各自怎么来

| 参数 | 来源 | 要不要跑仿真 |
| --- | --- | --- |
| seed / 难度（四个任务） | `src/robomme/env_metadata/{test,val}/record_dataset_{Task}_metadata.json` | 否 |
| move 次数、落点坐标、动作语义（Imitation） | 按 seed 离线重跑两个 env 的随机数序列 | **否** |
| 动作次数、颜色组成（Counting） | h5 的 `setup/task_goal` 原文解析 | 否 |
| 动作坐标（Counting） | h5 的 `action/waypoint_action`，取段内 z 最低点 | —— |
| 每次动作的时长（四个任务） | h5 的子目标边界数帧 | val 有现成 h5；test 要实跑 |

**为什么坐标能离线算：** 两个 env 的 `_load_scene` 里，场景随机段只用一个局部
`torch.Generator(seed)`，消费顺序完全确定，格点位置本身又是纯公式。所以不必启动 SAPIEN，
按同样顺序重跑一遍随机数就能还原 `selected_buttons`。RNG 顺序错一步就全错，两个 env 各有坑：

- **PatternLock**：选起终点 + DFS 找路径的循环最多试 1000 次，**失败的 attempt 同样消耗 RNG**，
  必须逐次模拟；1000 次都不满足长度约束时沿用最后一次的路径（`for...else`）。
- **RouteStick**：顺序是 `theta` → **4 根障碍柱各一次 `torch.rand(3)` 颜色** → `steps` → 随机游走 →
  逐次绕行方向。中间那 4 次颜色不消费就整体错位。

**为什么时长必须从 h5 拿：** 它是运动规划器跑出来的。PatternLock 走 mplib screw planner，
步数取决于规划结果，闭式算不出；RouteStick 每次 move 采 45 个贝塞尔点 + 5 个停留点，
名义 50 步，但 IK 失败会丢点，实测执行段末次 move 常是 43 步。

## 数据来源

- **val**：用原版 h5 `/data/hongzefu/data-0306/record_dataset_{PatternLock,RouteStick}.h5`（只读，不拷不改）。
  其 ep0–49 的 `setup/seed` 与 `env_metadata/val/` 逐条一致。
- **test**：本机从来没有 test 种子域的 h5，一律按 test metadata 的死 seed 实跑生成。
  - PatternLock / RouteStick 用 `scripts/data-generation-newSeed/generate_dataset_newseed.py --layout test`
    （这两个 env 的 test seed 全是 attempt=0 尾号，公式自算恰好等于 metadata，实跑后逐条核对过）。
  - BinFill / PickXtimes **不能用那个入口**：它们的 test metadata 里有一批 seed 尾号非 0
    （BinFill 8 条、PickXtimes 1 条，当年 attempt=0 失败过）。生成型入口从 attempt=0 起算，
    而当前环境代码比 2025-12 更容易通过，这些 episode 会在 attempt=0 就成功 —— 拿到的是**另一个场景**。
    因此改用 `run_test_fixed_seed.py`：逐条锁死 metadata 的 (seed, difficulty)、`max_attempts=1`，
    失败即放弃、绝不 bump seed。

## 口径

- **坐标**：SAPIEN 世界坐标，单位米，机器人 base 在 `(-0.615, 0, 0)`。报告表里给的是按钮本身的位置；
  运动规划实际下发的终点高度统一抬到 `z=0.07`（见 `subgoal_planner_func.py` 的 `solve_swingonto*`）。
- **时长**：timestep，1 timestep = 1 个 env step = 0.05 s（控制频率 20 Hz），与数据集采样频率一致。
  录像 fps=30 与 timestep 不等长，报告一律不用视频帧。
- **演示段 vs 执行段**：同一组 move 在数据里出现两遍——前一遍 `is_video_demo=True` 是给模型看的示范，
  后一遍才是真正 rollout，所以真实 move 次数 = move 段数 / 2。每条末尾还有一个
  `All tasks completed` 收尾段（几到十几 timestep），不算 move。
- `task_list` 里的 `NO RECORD` 段（首步到达起点、结尾 reset）不写进 h5，因此报告里看不到它们。

## 脚本与用法

| 脚本 | 作用 |
| --- | --- |
| `derive_episode_params.py` | 离线复算 move 次数 / 坐标 / 动作语义，出 `outputs/derived_params.json` |
| `extract_move_durations.py` | 从 h5 按子目标边界切段，出每次 move 的 timestep 时长 |
| `cross_check.py` | 复算 vs h5 真值逐条对拍（seed、move 次数、语义串） |
| `extract_task_params.py` | BinFill / PickXtimes 的参数提取：goal 解析 + 段时长 + 段内目标点坐标 |
| `run_test_fixed_seed.py` | 按 metadata 死 seed 实跑指定 split（不让 seed 漂移），复用生成链路的 worker |
| `plot_eval_success.py` | 把 policy 侧三轮 eval 的逐集结果按动作参数分组，出成功率分布图与解读段落 |
| `build_report.py` | 合成 `reports/` 下的 Markdown（存在 `reports/eval_section.md` 时自动拼进总览） |

```bash
# 1. 离线复算四个源
uv run python scripts/patternlock-routestick-params/derive_episode_params.py

# 2. val 时长（原版 h5，只读）
uv run python scripts/patternlock-routestick-params/extract_move_durations.py \
  --h5 PatternLock-val=/data/hongzefu/data-0306/record_dataset_PatternLock.h5 \
  --h5 RouteStick-val=/data/hongzefu/data-0306/record_dataset_RouteStick.h5 \
  --episodes 0-49 --out scripts/patternlock-routestick-params/outputs/durations_val.json

# 3. 对拍校验（复算的正确性地基，免 GPU）
uv run python scripts/patternlock-routestick-params/cross_check.py

# 4. test 实跑（tmux 后台，双卡，约 10 分钟；日志用 Monitor 等，别 sleep 轮询）
tmux new-session -d -s plrs-test \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run python scripts/data-generation-newSeed/generate_dataset_newseed.py \
     --output-dir scripts/patternlock-routestick-params/outputs/test-h5 \
     --env PatternLock,RouteStick --layout test --episodes 50 --gpus 0,1 --workers 16 \
     2>&1 | tee scripts/patternlock-routestick-params/outputs/test-run.log; \
   echo \"EXIT_CODE=\$?\" >> scripts/patternlock-routestick-params/outputs/test-run.log"

# 5. test 时长 + 合成报告
uv run python scripts/patternlock-routestick-params/extract_move_durations.py \
  --h5 PatternLock-test=<合并后的 test h5> --h5 RouteStick-test=<...> \
  --episodes 0-49 --out scripts/patternlock-routestick-params/outputs/durations_test.json
uv run python scripts/patternlock-routestick-params/build_report.py \
  --durations scripts/patternlock-routestick-params/outputs/durations_val.json \
  --durations scripts/patternlock-routestick-params/outputs/durations_test.json
```

## Counting 侧的命令

```bash
# val：现成 h5，只读
uv run python scripts/patternlock-routestick-params/extract_task_params.py \
  --h5 BinFill-val=/data/hongzefu/data-0306/record_dataset_BinFill.h5 \
  --h5 PickXtimes-val=/data/hongzefu/data-0306/record_dataset_PickXtimes.h5 \
  --episodes 0-49 --out scripts/patternlock-routestick-params/outputs/counting_params_val.json

# test：按死 seed 实跑（tmux 后台，双卡，约 15 分钟），再提参数
tmux new-session -d -s bp-test \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run python scripts/patternlock-routestick-params/run_test_fixed_seed.py \
     --output-dir scripts/patternlock-routestick-params/outputs/test-h5-counting \
     --env BinFill,PickXtimes --split test --workers 16 --gpus 0,1 \
     2>&1 | tee scripts/patternlock-routestick-params/outputs/test-counting-run.log; \
   echo \"EXIT_CODE=\$?\" >> scripts/patternlock-routestick-params/outputs/test-counting-run.log"

uv run python scripts/patternlock-routestick-params/extract_task_params.py \
  --h5 'BinFill-test=scripts/patternlock-routestick-params/outputs/test-h5-counting/hdf5_files/BinFill_ep*.h5' \
  --h5 'PickXtimes-test=scripts/patternlock-routestick-params/outputs/test-h5-counting/hdf5_files/PickXtimes_ep*.h5' \
  --episodes 0-49 --out scripts/patternlock-routestick-params/outputs/counting_params_test.json

# 合成报告时把两份 counting JSON 一起传进去
uv run python scripts/patternlock-routestick-params/build_report.py \
  --durations .../durations_val.json --durations .../durations_test.json \
  --counting .../counting_params_val.json --counting .../counting_params_test.json
```

## 成功率分析（跨仓库）

`plot_eval_success.py` 读 policy 仓库的 eval 结果，按本目录复算出的动作参数分组画成功率分布：

```bash
uv run python scripts/patternlock-routestick-params/plot_eval_success.py
uv run python scripts/patternlock-routestick-params/build_report.py \
  --durations scripts/patternlock-routestick-params/outputs/durations_val.json \
  --durations scripts/patternlock-routestick-params/outputs/durations_test.json
```

数据来自 `/data/hongzefu/robomme_policy_learning_MotionJEPA/docs/training-doc/` 下的
`eval-{medium,hard}-patternlock-routestick/`（Imitation，192 条）与
`eval-binfill-pickxtimes/`（Counting，192 条，**难度档在 records 下面一层**），共 384 条，只读。
两个变体是 framesample 的 `modul` 与 `context`，三轮同一批 ckpt 79999、同 seed 42。
Imitation 侧 join 键 `(task, split, episode)` 并逐条断言 seed 一致；
Counting 侧的参数直接解析 eval 记录 `video` 字段里的 task_goal（与 val h5 校验 48/48 相同）。

**覆盖边界**：四个任务都只测了 medium 与 hard 各 12 条（该难度全集），**easy 26 条一条未测**。图落在 `reports/figures/`，解读段落 `reports/eval_section.md` 由 `build_report.py`
自动拼进 `reports/README.md` 末尾——所以改了 eval 结果后，先跑 `plot_eval_success.py` 再跑 `build_report.py`。

## 校验结果

- **对拍（核心判据）**：val 100 条，复算的 move 次数与动作语义串 vs 原版 h5 段名串，**100/100 逐条一致**。
  这同时也验证了坐标——PatternLock 的方向串、RouteStick 的 left/right 都是从复算坐标算出来的。
- **test 也对拍过**：实跑出的 test 100 条同样与复算逐条一致（`outputs/cross_check_test.json`）。
- **Counting 的 goal 解析**：`核心段数 == 2 × 动作次数 + 1` 这条恒等式，200 条全中；
  另外 val 侧用 h5 的 `setup/task_goal` 校验过从 eval `video` 字段解析出的 goal，48/48 相同。
- **Counting 的 test seed 锁死**：`run_test_fixed_seed.py` 逐条用 metadata 的 seed，
  smoke 用 attempt≠0 的 BinFill ep1（seed 540101）验证过死 seed 真的被用上。
- **test seed 一致性**：实跑 100 条全部 attempt=0 一次通过，seed 与 test metadata **逐条相等、0 条不一致**
  （`outputs/test_seed_check.json`），所以 test 的时长就是原版 seed 下的时长。实跑耗时 381 s（双卡 16 worker）。

产物 `outputs/*.json` 是机器可读版本，供下游脚本消费；`outputs/test-h5/` 是本轮生成的 test 原始数据。
