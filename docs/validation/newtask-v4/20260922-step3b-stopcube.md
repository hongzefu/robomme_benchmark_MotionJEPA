# V4 步 3b：StopCube 的 xhard（计划 2.6，A6 / C4）

> 红线 N1 的逐步报告。起点 `12.66`（`00e2ef4`），隔离 worktree 实施。录像器未改
> （`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` 通过）。
> 本机（sm_89，GPU 1）结果只用于调试，不进判据（口径 10）。

## 一、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `src/robomme/robomme_env/StopCube.py` 模块常量 `_CONFIG_CURRENT` / `_CONFIG_XHARD`、类属性 `StopCube.configs` | 新建 `configs = {easy/medium/hard: 原全局常量（三档同值、各自深拷贝）, xhard: {move_interval_choices [60], stop_time_range {low 6, high_exclusive 16}}}` | A6：本环境原无难度分档，现值作 hard 派生 xhard；C4 只锁「速度最快档」与 number `[6,15]`（原实现是半开 `randint(2,6)` ⇒ `[2,5]`，新值同样写半开） | `test_v4_xhard_stopcube.py::test_configs_three_same_and_xhard_new` |
| `StopCube.py::_native_decision` | 顶层两键改从 `configs["hard"]` 取（值与 V3 逐字相同），新增 `xhard` 子键＝`configs["xhard"]` | 2.2①：新值必须进 decision 才能过守卫；放在 `xhard` 键下，守卫按键名放行、原三档可见部分不变 | `test_native_decision_visible_part_unchanged`、`test_guard_allows_xhard_narrowing_rejects_original_change` |
| `StopCube.py::_resolve_sampling_config` | 守卫之后若 decision 无 `xhard` 键（v2/v3 旧快照），补上源码申报的默认值 | 旧快照守卫照旧放行，但 xhard 局要读 `decision["xhard"]`，不补会 `KeyError`；原三档不读这个键 | `test_old_snapshot_without_xhard_gets_default` |
| `StopCube.py::_initialize_episode`（速度档与停止序号取值点） | 按 `self.difficulty == "xhard"` 选 `decision["xhard"]` 或顶层原值；两处 `self._spec.value` 加 `decision_key`（`[xhard.]move_interval_choices` / `[xhard.]stop_time_range`） | 让 difficulty 真正被消费（全文件唯一消费点），且只有 xhard 取新值；随机调用次数／顺序／区间形式在两个分支完全相同（N5） | reset 探针原三档 diff=0；xhard 冒烟 20/20 |
| `StopCube.py::_initialize_episode`（新增 `self.motion_segments` 与 xhard 规格记录） | `motion_segments = max(5, stop_time)`（xhard）或 5（原三档）；仅 xhard 用 `self._spec.record` 记 `actions.move_interval / motion_segments / steps_press / stop_window` | 计划 2.6「注入 actions.move_interval / segments / steps_press / stop_window」；原三档不记，保证规格文档逐字不变 | xhard 冒烟打印规格 `actions` 全部落值；原三档 reset 探针规格文档零差异 |
| `StopCube.py::step`（方块往返循环） | 原三档分支逐字保留 `range(5)`；xhard 分支 `range(self.motion_segments)`，`segment % 2` 起终点交替规则不变 | 2.6 实施要点：不改则 `stop_time ≥ 6` 时第 6 次起的「经过目标」根本不存在，必然全部失败。第 n 次经过目标＝第 n 段中点 `move_interval*(n-0.5)`，所以 `max(5, stop_time)` 段恰好覆盖 | `test_step_keeps_literal_range5_for_original_three`（AST 查两个分支）、`test_xhard_segments_cover_stop_pass`；端点 15 演示 6/6 成功 |
| `src/robomme/robomme_env/utils/vqa_options.py::_options_stopcube` | **未改代码**，改为用测试锁住「与环境侧公式逐项一致」 | 两侧公式本就都是 `range(100, int(steps_press - interval), 100)` ＋补末项，且都只依赖 `steps_press`，不依赖段数；环境侧 `static_checkpoints` 公式本轮没动，所以 VQA 自动同步、原三档输出不变。改它反而引入风险 | `test_vqa_checkpoints_match_env`：原三档 12 组合＋xhard 10 组合逐项相等；xhard 最多 9 条 remain static |
| `tests/lightweight/test_v4_xhard_stopcube.py`（新增） | 纯 CPU 结构测试 37 项（见第四节） | 必做验证 4 | 37 passed |

`static_checkpoints` 公式、`evaluate` 的超时判据 `current_step > move_interval * stop_time`、停止窗口公式、
`is_obj_stopped_onto` 阈值、按钮提前量 `interval=30` 均未改：它们本就按 `move_interval`/`stop_time` 参数化，
随 number 自动膨胀（60×15 ⇒ 9 条 remain static、超时 900 步），实测演示无需调阈值（见第三节）。

## 二、C4：阈值是否调整

**本轮一个阈值都没调**。依据：xhard 演示 16/16 成功（含两端点各 6 条），失败类为空。
速度 60 本来就是原三档 `[60,80,120]` 里的一档，演示的按压时机只取决于 `steps_press - interval`，
与 `stop_time` 无关；`stop_time` 变大只是多几条 remain static 等待任务、方块多往返几趟。
停止窗口宽度 60 步、`cube_half_size*3=0.06 m` 配 0.01 m/step ⇒ 约 ±6 步的判定裕度，演示规划器实测都能命中。
若 A40 正式验收（V4f/V6）出现按压时机类失败，再按实测放宽，且只放宽 xhard。

## 三、实测数字

### 1. 原三档 reset 零差异

```bash
uv run --no-sync python -m scripts.parity.v4_reset_probe probe --tasks StopCube --out /tmp/g2_probe.json
# PROBE_DONE rows=9 ok=9
uv run --no-sync python -m scripts.parity.v4_reset_probe diff \
  /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/probe/base-13e.json /tmp/g2_probe.json
# RESET_REGRESSION=FAIL compared=9 diff=0 missing=135
```

compared 的 9 行全是 StopCube（easy/medium/hard 各 3 个身份），**diff=0**；`missing=135` 是基线里其他 15 个环境，
本 probe 只采了 StopCube，属预期。diff 输出里不出现 StopCube 任何行（`grep -c StopCube` = 0）。

### 2. xhard reset 冒烟（20 seed，`seed = 900000 + 101*i`）

`XHARD_RESET ok=20/20`，失败 0。全部 `spec_kind=native-newvalue/1`。

| 量 | 声明 | 实测 |
|---|---|---|
| `move_interval` | `[60]` | 20/20 为 60（`move_interval_idx` 恒 0） |
| `stop_time` | `[6,15]` | 取到 6,8,9,10,11,12,13,14,15（20 个样本里 7 未出现，属抽样；6 出现 3 次、15 出现 1 次） |
| `motion_segments` | `max(5, stop_time)` | 恒等于 `stop_time` |
| `steps_press` / `stop_window` | `60*st-30` / `[60(st-1), 60st]` | 例：st=6 ⇒ 330 / [300,360]；st=15 ⇒ 870 / [840,900] |
| remain static 条数 | 随 number 膨胀 | st=6 ⇒ 3 条，st=15 ⇒ 9 条（与计划 2.6 的「60×15 ⇒ 9 条」一致） |
| 规格 `actions` | 新增 4 个记录项 | `move_interval / motion_segments / steps_press / stop_window` 均落值 |

### 3. xhard 演示（`scripts.parity.v4_demo_probe`，GPU 1）

| 批次 | 配置 | seed | 结果 | 帧数（timesteps） | 单条墙钟 |
|---|---|---|---|---|---|
| 全范围 | 源码默认 xhard | 910000/910101/910202/910303（st=7/12/10/10） | **4/4** | 434/722/606/613 | 23~32 s |
| 端点 st=6 | `--sampling-config` 收窄 `stop_time_range={6,7}` | 920000/920101 + 950000~950303 | **6/6** | 362/369/366/371/379/365 | 18.5~22.3 s |
| 端点 st=15 | 收窄 `stop_time_range={15,16}` | 930000/930101 + 940000~940303 | **6/6** | 902/917/908/907/902/908 | 36.8~46.7 s |

口径 14：两个参数的全部组合＝`move_interval ∈ {60}` × `stop_time` 端点 `{6, 15}`，两端点演示均非 0 成功，
**不存在「传入但生成不出来」的组合**。

### 4. 评估步数上限（MAX_STEPS）

- `evaluate` 超时判据 `move_interval*stop_time` 最大 60×15 = **900 步**；演示实测 st=15 的整条 902~917 帧（按下后还有收尾帧）。
- `scripts/evaluation.py` 里 `BenchmarkEnvBuilder(max_steps=1300)`（非演示步数上限，`DemonstrationWrapper.max_steps_without_demonstration`）**够用**，余量约 400 步。
- `BenchmarkEnvBuilder` 默认 `max_steps=10000`；生成链路（`generate_dataset_newseed._worker`）无步数上限，只有单条墙钟 600 s，st=15 实测约 40 s。
- `StopCube` 注册时未设 `max_episode_steps`，不存在 gym TimeLimit 截断。
- ⚠ `scripts/run_example.py` 的 `MAX_STEPS = 300`：xhard 下必然截断（原三档最长 120×5 = 600 步，同样会截断，属既有状况）。该文件与上游逐字节相同（口径 9），不改；新值评估入口（`scripts/eval/`，步 6）须把步数上限设到 ≥ 900＋按压余量，建议沿用 1300。

## 四、测试

- `tests/lightweight/test_v4_xhard_stopcube.py`：37 passed（configs／decision 结构、守卫放行与拒绝、旧快照补默认、`step` 两分支 AST、VQA 与环境 checkpoint 22 组合逐项一致、xhard 10 个 stop_time 的段数覆盖与窗口自洽）。
- 连带：`test_StopcubeIncrement.py`（4 项）、`test_v4_decision_guard.py` 同跑，合计 46 passed。
- 轻量全量：本机当时负载约 20～27（其他组同时跑全量），整跑在 590 s 限时内未跑完（到约 12% 被 `timeout` 杀掉），
  按规则 3 改跑核心子集：凡引用 `native_blocks` / `_native_decision` / `StopCube` / `sampling_config` / 守卫 / 审计的测试文件，
  外加 `test_swap_schedule_generic` / `test_window_timeline` / `test_subgoal_ordinal_v4`，逐文件限时 300 s：

  | 文件 | 结果 | 与基线比 |
  |---|---|---|
  | test_candidates_refactor | 6 passed / 12 errors | 同基线 12 errors |
  | test_candidate_loader | 4 failed / 7 passed | 同基线 4 |
  | test_episode_action_sampling | 20 failed / 23 passed | 同基线 20 |
  | test_native_sampling_config | 13 failed / 11 passed | 同基线 13（全是 v2 快照校验类，与 StopCube 无关） |
  | test_TaskGoal | 2 failed / 25 passed | 同基线 2（SwingXtimes 与未知环境两项） |
  | **test_sampling_config_split** | **1 failed** / 32 passed | **基线外**：`test_snapshot_matches_source`，见第五节，属预期 |
  | test_TaskGoalI_isList | 整文件负载下 300 s 超时；`-k StopCube` 4 passed | — |
  | test_injection_blocks / test_env_check / test_episode_specs / test_refactor_figures / test_v4_decision_guard / test_parallel_calibration / test_reset_pipeline / test_StopcubeIncrement / test_subgoal_ordinal_v4 / test_swap_schedule_generic / test_window_timeline / test_v4_xhard_stopcube | 全部通过 | — |

## 五、计划外

- 计划 2.6 说「`_options_stopcube` 复刻了同一套 checkpoint 公式 ⇒ 改环境侧必须同步改它」。源码实测两侧公式都只依赖
  `steps_press` 与 `interval`，本身就按 number 参数化；本轮**没有改**环境侧 checkpoint 公式，所以 VQA 侧无需改代码，
  已用参数化测试锁住两侧逐项一致（含原三档全部 12 组合）。
- 计划 2.6 表里 native 的 `motion_segments: 5` 是说明键；本轮没有改 native 块（改了会让 v4 快照多出原三档可见的变化），
  xhard 的段数规则写在代码里并记进 xhard 规格 `actions.motion_segments`。建议主 agent 写回计划时把「段数＝max(5, stop_time)」记入 2.6。
- `test_sampling_config_split.py::test_snapshot_matches_source` 新失败：`scripts/configs/newtask-v4/sampling_config.json`
  与源码提取不一致。逐任务比对（`native_blocks` 对快照）结果**只有** `StopCube.decision` 多出 `xhard` 键，其余 15 环境与 native 块全部一致。
  这是给 decision 加 xhard 条目的必然后果；按公共说明快照由主 agent 统一重导、本组**不提交**快照，重导后该项应恢复通过。
- 环境模块 `robomme.robomme_env.StopCube` 被包 `__init__` 的 `from .StopCube import *` 遮住（属性名解析成同名类），
  取模块须用 `importlib.import_module`；测试与脚本已按此写。

## 六、待用户决策

无。C4 授权的「其余阈值由实施方按实测调」本轮实测不需要调；若 A40 验收出现按压时机类失败，再回报。
