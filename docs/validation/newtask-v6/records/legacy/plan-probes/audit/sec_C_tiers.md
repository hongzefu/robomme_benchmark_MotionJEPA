# 审计 C：V6 计划档位数值、单调性、键名存在性（只读）

- 审计对象：根目录 `NEWTASK_RELEASE_V6_PLAN.md` 第一节总表、2.0 管道改造表、2.3～2.13 各环境三档表、第二部分一「按文件清单」。
- 代码基准：当前 HEAD `0b1d542`（12.139）。计划写的锚点 `da77662`（12.134）到 HEAD 之间 `src/ scripts/ tests/` **零 diff**（`git diff --stat da77662..HEAD -- src scripts tests` 为空），锚点仍有效。
- 脚本与输出（全部在 `artifacts/newtask-v6/plan-probes/audit/sec_C/`）：
  - `dump_c.py` → `dump_c.json`：重新 import 16 个环境类，dump `config_easy/medium/hard/xhard`、`configs`、`XHARD_DECISION`、`_native_decision(cls)`，并附 `scripts/configs/newtask-v5/sampling_config.json` 全文。
  - `cmp_native.py` → `cmp_native.out`：16 环境 `native_blocks(cls)` 与 V5 快照的 decision/native **全部逐字相同**（16/16）。与旧 `difficulty-framework/configs_dump.json` 数值一致。
  - `grep_syms.sh` → `grep_syms.out`：任务 3 的符号 grep（src/scripts/tests，*.py/*.json）。
  - `monotone.py` → `monotone.out`：按计划表手录各档取值，自动判均值严格单调、上下界单调不减、新档是否越过 xhard / 低于 hard。
- 下文「出处」均写「文件::符号」，不写行号；文件路径省略前缀 `src/robomme/robomme_env/`。

## 一、任务 1：hard / xhard 数值对照

| 条目 | 计划原文摘要 | 核实方法 | 结果 | 备注（源码出处 / 实际值） |
|---|---|---|---|---|
| BinFill hard | 3 色 / 总块 [10,12] / 投入色 [2,3] / 投入 [3,5] / 原生布局 | dump_c | 一致 | `BinFill.py::BinFill.config_hard` = color 3, spawn_cubes [10,12], put_in_color [2,3], put_in_numbers [3,5]；快照 `decision.configs.hard` 同（put_in_color 在 `native.parameters.put_in_color`，不在 decision） |
| BinFill xhard | 总块 12 / 投入 [5,7] / 杂乱布局 + 精确 OBB + 同色团 ≤3 | dump_c + grep | 一致 | `BinFill.config_xhard` = spawn_cubes [12,12], put_in_numbers [5,7], layout_mode "clutter", color_mix.max_component 3（link_m 0.09, max_redraws 64）；精确 OBB 见 `BinFill.py` 引 `utils/xhard.py::cube_obb2d_exact`。投入色 xhard 仍 [2,3]，计划新档未写投入色 |
| PickXtimes hard | [4,5]，干扰 0，框 0.2 | dump_c | 一致 | `PickXtimes.config_hard` number_min 4/max 5；`_native_decision.target_cube_position_policy.region_half_size` 0.2；`distractor` None |
| PickXtimes xhard | [6,15]，干扰 3，框 0.25，中心距 0.08，均匀无偏置 | dump_c + grep | 一致 | `PickXtimes.config_xhard` 6/15；`PickXtimes.py::XHARD_DECISION` target 框 0.25、goal 框 0.2（不变）、distractor.colors 黄/青/品红（**干扰数 = len(colors)=3，无独立计数键**）、`min_center_dist_m` 0.08；corner_bias 已在 V5 删除（注释 L43） |
| SwingXtimes hard | 3 | dump_c | 一致 | `SwingXtimes.config_hard` 3/3 |
| SwingXtimes xhard | [4,10]，干扰 3，0.08、精确 OBB | dump_c | 一致 | `SwingXtimes.config_xhard` 4/10；`SwingXtimes.py::XHARD_DECISION` distractor 三色、`min_center_dist_m` 0.08；`cube_obb2d_exact` 已引用 |
| PH hard | pick 3 / spawn 6 / RGB 均匀色 | dump_c | 一致 | `PickHighlight.config_hard` spawn 6 pickup 3；`_native_decision.block_color_policy` "native_per_cube_uniform" |
| PH xhard | pick [5,7] / spawn [8,10] / HSV 任意色 / 精确 OBB / `spawn_lo ≥ pick_hi` 断言 | dump_c + 读码 | 一致 | `PickHighlight.config_xhard` spawn [8,10] pickup [5,7]；`PickHighlight.py::XHARD_DECISION` block_color_policy "hsv_floor"；断言在 `PickHighlight` 场景加载的 xhard 分支（`spawn_lo < highlight_hi` 抛 `SamplingConfigError`）。spawn 与 pick **独立抽**（`torch.randint` 各一次） |
| VU hard | 15 容器 / pick 2 / 无干扰 | dump_c | 一致 | `VideoUnmask.config_hard` bin 15 pick 2；`_native_decision.distractor` None |
| VU xhard | 8 容器 / pick 3 / 干扰 15 / 含 cube [7,8] / min_gap_factor 0.75 | dump_c | 一致 | `VideoUnmask.config_xhard` bin 8 pick 3；`_native_decision.xhard.distractor` count 15, cube_count_range [7,8], min_gap_factor 0.75, ring_max_abs_xy [0.2425,0.3289]；另 `bin_layout_policy.xhard.min_gap_factor` 0.75 |
| BU xhard | 干扰 14 / 含 cube [7,7] | dump_c | 一致 | `ButtonUnmask._native_decision.xhard.distractor` count 14, cube_count_range [7,7] |
| VUS/BUS hard | swap [2,3] / pick 2 / 50 步 / 无外环 | dump_c + 读码 | 一致 | `VideoUnmaskSwap.config_hard`/`ButtonUnmaskSwap.config_hard` swap 2～3, pick 2；步数 = `utils/unmask_swap_xhard.py::scaled_window_steps(SWAP_WINDOW_STEPS=50, swap_speed_multiplier=1)` = 50 |
| VUS xhard | swap [8,12] / pick 3 / 33 步 / 外环 10 / 环带 [0.2675,0.45] | dump_c | 一致 | `VideoUnmaskSwap.config_xhard` 8/12, pick 3；`XHARD_SWAP_SPEED_MULTIPLIER`=1.5 ⇒ round(50/1.5)=33；`xhard.distractor.count` 10、`ring_max_abs_xy` [0.2675,0.45]。**注意**：这是方环 `max(|x|,|y|)∈[r_in,r_out]`（`utils/unmask_distractors.py` 文档），不是圆环；外环 `cube_count_range` [5,5]，计划新档未给 |
| BUS xhard | swap [6,8] | dump_c | 一致 | `ButtonUnmaskSwap.config_xhard` 6/8；其余同 VUS，`path_constraints.min_button_center_dist_m` 0.122 |
| VR medium | 3 / [2,3] / [1,3] | dump_c | 一致 | `VideoRepick.config_medium` cube 3, swap 2～3；repick = `NATIVE_SAMPLING.parameters.num_repeats` low 1 high_exclusive 4 ⇒ [1,3] |
| VR hard | 聚簇 15 / 0 / [1,3] | dump_c + 读码 | 一致 | `config_hard` cluster True, swap 0/0；15 = `NATIVE_SAMPLING.parameters.hard_spawn_rounds`(5) × 3 色 |
| VR xhard | 6 / [8,12] / [4,6] / min_center_gap 0.12 | dump_c | 数值一致，**键名不一致** | `config_xhard` cube 6, swap 8/12, num_repeats 4～7(半开) ⇒ [4,6]；中心距键名实为 `min_center_dist_m`（`decision.xhard.layout.min_center_dist_m`=0.12），源码无 `min_center_gap`；`partner_nearest_k` 3 |
| PatternLock hard | 5×5 / [4,8] / 预算 1000（耗尽静默沿用） | dump_c + 读码 | 一致 | `PatternLock.config_hard` grid 5 length [4,8]；`NATIVE_SAMPLING.parameters.path_selection.max_attempts` 1000；耗尽走「use the last one」分支 |
| PatternLock xhard | 25 节点 / 预算 20000（耗尽抛错） | dump_c | 一致 | `config_xhard` length [25,25]；`PatternLock.py::XHARD_DECISION.path_search_max_attempts` 20000 |
| RouteStick hard/xhard | [4,7] T / [15,21] T | dump_c | 一致 | `RouteStick.config_hard` length [4,7] backtrack True；`config_xhard` [15,21] True；`_native_decision.xhard.segment_count_range` [15,21] |
| VPB hard/xhard | k 1→2；不放回→return_to_origin；颜色 3、目标台 4、swap True | dump_c | 一致 | `VideoPlaceButton._native_decision` demo_object_count 1 / "native_random_goal_site"；`XHARD_DEMO_DECISION` 2 / "return_to_origin"；config_hard/xhard color 3, targets 4, swap True |
| VPO hard/xhard | 同上，v [2,4] | dump_c + 读码 | 一致 | `VideoPlaceOrder.py::NATIVE_SAMPLING.parameters.visit_selection.count_sampler` = `"torch.randint(2, len(targets) + 1)"`，targets 4 ⇒ [2,4]；**v 是 native 里的字符串表达式，不是 decision 数值键** |
| VPB/VPO「演示放置次数」 | hard 2/3，xhard1 3/4（放回 +1） | 读码 | **不一致** | 原三档演示在两个 target 之外还有一段 pick + `drop onto goal_site`（`VideoPlaceButton`/`VideoPlaceOrder` 任务表 `target=self.goal_site`）；xhard 的 `return_to_origin` 是把这段换成「放回原位」（`_xhard_pick_place(..., home=True)`），**动作段数不变**。计划把 goal_site 那次计 0、放回计 1，hard→xhard1 实际 pick-place 段数相同，标尺不成立 |
| MoveCube 方块框 | ±0.10（面积 0.040） | dump_c + 读码 | 一致（注意口径） | `_native_decision.demo_layout.cube_position_policy` center_span 0.2, center_offset −0.1 ⇒ 候选中心 ∈ [−0.1,0.1]²；之后 `spawn_random_cube(region_half_size=0.05)` 以候选为中心再抖 ±(0.05−0.02)，**实际方块中心 ≈ ±0.13**，0.040 m² 只是候选框面积 |
| MoveCube goal 框 | demo ±0.11、exec ±0.06 | 读码 | 一致 | `MoveCube.py::NATIVE_SAMPLING.positions.goal_demo.region_half_size` 0.15、`goal_execution` 0.10，radius = cube_half_size(0.02)×radius_factor 2 = 0.04；`utils/object_generation.py::spawn_random_target` 中心界 = half − radius ⇒ ±0.11 / ±0.06 |
| MoveCube 杆根 | ±0.05，y=±0.2 | dump_c | 一致 | `peg_position_policy` base_y_abs 0.2, jitter_span 0.1 ⇒ ±0.05 |
| MoveCube 禁区 / yaw | R=0.05；杆/方块 yaw 全 2π | dump_c + 读码 | 一致 | `config_xhard.center_exclusion.radius_m` 0.05；`peg_yaw_range` xhard span 2π；`spawn_random_cube` random_yaw ⇒ `yaw_sample*2π` |
| InsertPeg / StopCube | 原三档无梯度，不动 | dump_c | 一致 | 两者 `configs.easy/medium/hard` 逐字相同；MoveCube 同（三档都是 span π/2 + corner_bias 0） |
| 快照一致性 | 源码与 `newtask-v5/sampling_config.json` | cmp_native | 一致 | 16/16 decision、native 逐字相同 |
| 总表 PH 维度 | 「干扰数 + pick 数」 | 对照 2.9 | 不一致（表述） | 总表只给「总块 6→7→8→[8,9]→[8,10]」，2.9 的干扰列均值实为 3/3/3.5/3/3，干扰数并未随档上升（见任务 2） |
| 2.3 「干扰总数保证 > hard 的 15 个容器」 | VU/BU 新档 | 计算 | **BU xhard1 不满足** | BU xhard1 = 8 内环 + 7 干扰 = 15，等于而非大于 15；若「干扰总数」指干扰单独计数则 VU 8/BU 7 都远小于 15。句意需明确 |
| 「src 约 105 处 `"xhard"`」 | 管道规模 | grep | 无法精确核实 | `"xhard"` 字面量 130 处（含注释/字符串），`==/!= "xhard"` 比较 61 处；105 的口径未说明 |

## 二、任务 2：单调性（口径 5 / N7 / 3.2）

判定口径：均值按区间中点；「越过」指新档均值 > xhard 或 < hard；区间界按「下界、上界各自单调不减」读口径 5 的「单调不减」。完整输出见 `sec_C/monotone.out`。

| 环境 / 字段 | hard → x1 → x2 → x3 → xhard（均值） | 问题 | 与口径 5 冲突？ | 与 N7 / 3.2 冲突？ |
|---|---|---|---|---|
| PickXtimes 次数 | [4,5]→[5,7]→[6,9]→[7,12]→[6,15]（4.5/6/7.5/9.5/10.5） | 均值严格；**x3 下界 7 > xhard 下界 6**（区间不嵌套，x3 的最小次数比 xhard 还难） | 若「单调不减」按下界读：冲突；按均值读：不冲突（口径 5 明写「区间允许重叠」） | 不冲突 |
| PickXtimes 干扰块 | 0→1→2→3→3 | **x3 = xhard**（非严格） | 不冲突（不减） | **冲突**（N7 要所有加码字段严格） |
| PickXtimes 框半宽 | 0.2→0.25×4 | x1=x2=x3=xhard | 不冲突 | 冲突（若算加码字段；它属「机制」，建议明确排除） |
| SwingXtimes 轮数 | 3→[3,4]→[4,6]→[5,8]→[4,10]（3/3.5/5/6.5/7） | **x3 下界 5 > xhard 下界 4**；x1 下界 3 = hard | 同 PickXtimes | 不冲突 |
| SwingXtimes 干扰块 | 0→1→2→3→3 | x3 = xhard | 不冲突 | **冲突** |
| PH pick | 3→4→[4,5]→[5,6]→[5,7] | 严格 | 不冲突 | 不冲突 |
| PH spawn | 6→7→8→[8,9]→[8,10] | 严格 | 不冲突 | 不冲突 |
| **PH 干扰数（spawn−pick，独立抽）** | 3→3→3～4→2～4→1～5（**3/3/3.5/3/3**） | hard = x1；**x2 均值 3.5 > xhard 3**；x3 下降；xhard 本身干扰均值 = hard。用户点名「pickhighlight 按照干扰数量」，但这一维**根本没加码** | **冲突**（x2→x3 下降） | **冲突**（x2 越过 xhard） |
| VU / BU pick | 2→2→3→3→3 | hard = x1，x2 = x3 = xhard | 不冲突 | **冲突**（用户点名「pickup 次数」维度） |
| VU 干扰 / 含 cube | 0→8→10→13→15；0→4→5→6.5→7.5 | 严格 | 不冲突 | 不冲突 |
| BU 干扰 / 含 cube | 0→7→9→12→14；0→3.5→4.5→6→7 | 严格；xhard [7,7] 是单点 | 不冲突 | 不冲突 |
| VU/BU 内环容器 | 15→8→8→8→8 | **hard→x1 下降**（新档低于 hard）；x1..xhard 相等 | 若算字段：冲突（计划以「干扰总数 >15」辩护，BU x1 恰 15 不成立） | 冲突（若算字段） |
| VUS swap | [2,3]→[4,5]→[5,7]→[7,9]→[8,12] | 严格，区间界单调（x3 [7,9] 与 xhard [8,12] 无问题） | 不冲突 | 不冲突 |
| BUS swap | [2,3]→[3,4]→[4,5]→[5,6]→[6,8] | 严格 | 不冲突 | 不冲突 |
| VUS/BUS pick | 2→2→3→3→3 | hard = x1，x2 = x3 = xhard | 不冲突 | **冲突** |
| VUS/BUS 每次交换步数 | 50→50→33→33→33 | hard = x1，x2 = x3 = xhard | 不冲突 | **冲突**（若算字段） |
| VUS/BUS 外环干扰 | 0→4→6→8→10 | 严格 | 不冲突 | 不冲突 |
| VR 块数 | 15(聚簇)→4→5→6→6 | **hard→x1 下降**；**x3 = xhard** | 冲突（下降；M9 已挂待决） | **冲突**（x3 = xhard 非严格） |
| VR swap / repick | 0→4→6→7.5→10；2→2.5→3.5→4.5→5 | 严格，界单调 | 不冲突 | 不冲突 |
| BinFill 投入 | 4/4.5/5/5.5/6 | 严格 | 不冲突 | 不冲突 |
| BinFill 总块 | [10,12]→12×4 | x1 = x2 = x3 = xhard | 不冲突 | 冲突（若算字段） |
| PatternLock 节点 | 6/10.5/15/20/25 | 严格 | 不冲突 | 不冲突 |
| PatternLock 预算 | 1000→20000×4 | x1..xhard 相等 | 不冲突 | 冲突（若算字段；它是搜索预算，建议明确排除） |
| RouteStick L | 5.5/9/11.5/13.5/18 | 严格 | 不冲突 | 不冲突 |
| VPB k | 1→1→2→2→2 | 非严格 | 不冲突 | 冲突（若算字段） |
| **VPB 放回块数** | 0→1→0→1→2 | **x1→x2 下降**（x1 放回、x2 不放回） | **冲突** | **冲突** |
| VPO v | [2,4]→[2,4]→[2,3]→[2,4]→[2,4]（3/3/2.5/3/3） | **x2 均值 2.5 < hard 3**，x1→x2 下降 | **冲突** | **冲突** |
| **VPO 放回块数** | 0→1→0→0→2 | x1→x2 下降 | **冲突** | **冲突** |
| VPB/VPO 放置次数（计划口径） | 2..6 / 3..8 | 严格，但计数口径本身有误（见任务 1） | — | — |

**口径 5 与 N7 是否矛盾**：矛盾。
- 口径 5 原文「每档在已加码字段上**单调不减**，且**至少一个字段**均值严格上升；取值区间允许重叠，均值必须严格介于相邻两档之间」——前半句允许「其他字段相等」，末句「均值必须严格介于」未说字段范围，本身就二义。
- N7「每档**所有**加码字段均值严格介于相邻档之间」、3.2 单调性判据「各加码字段均值严格递增」（`TIER_MONOTONE=PASS … violations=0`）把末句解释成「全部字段严格」。
- 按 N7/3.2，计划自己的表至少在 PickXtimes/SwingXtimes 干扰块、PH 干扰数、VU/BU/VUS/BUS pick、VUS/BUS 步数、VR 块数、BinFill 总块、PatternLock 预算、VPB/VPO k 上违例；`TIER_MONOTONE` 按字面实现会必然 FAIL。
- 按口径 5 前半句（单调不减），仍有真违例：PH 干扰数 x2→x3 下降、VPB/VPO 放回 x1→x2 下降、VPO v x1→x2 下降、VR 块数 / VU 内环容器 hard→x1 下降。
- 「新档 ≥ xhard」：PH 干扰 x2 均值 3.5 > xhard 3；PickXtimes x3 下界 7 > 6、SwingXtimes x3 下界 5 > 4（只在下界上，均值未越）。
- 「新档 ≤ hard」：VR 块数 x1..x3 < 15；VU/BU 内环容器 8 < 15；VPO v x2 2.5 < 3。

## 三、任务 3：键名 / 符号存在性

| 条目 | 计划原文摘要 | 核实方法 | 结果 | 备注 |
|---|---|---|---|---|
| `VALID_DIFFICULTIES` | `utils/difficulty.py` 加 xhard1/2/3 | grep | 一致 | `utils/difficulty.py::VALID_DIFFICULTIES = {"easy","medium","hard","xhard"}` |
| `XHARD_KEY` / `_strip_xhard` / `_xhard_shape` / `assert_native_decision` | `utils/sampling_config.py` | grep | 一致 | 均在 `utils/sampling_config.py`；`XHARD_KEY = "xhard"` 单一字符串 |
| `spec_kind_for` | `utils/episode_spec.py` | grep | 一致 | 另被 `tests/lightweight/test_episode_spec_recorder.py` 引用 |
| `_unmask_pick_count` | `task_goal.py` | grep | 一致 | `utils/task_goal.py`（内有 `self.difficulty == "xhard"`） |
| `validate_demo_plan` | `xhard_home_site.py` | grep + 读码 | 一致，**但计划改动描述不全** | 现逻辑：非 xhard 只许 `(1, native_random_goal_site)`，xhard 只许 `return_to_origin`。计划新档 VPB x2 `(2, 不放回)`、VPO x2/x3 `(2, 不放回)` 同样会被拒；且原三档只有一个 `goal_site`，「k=2 不放回」两块放哪未定义。计划只写了放行 `return_last_only` |
| `decision["xhard"]` | 列在 episode_spec/task_goal/xhard_home_site/unmask_swap_xhard 行 | grep | 部分一致 | 字面 `decision["xhard"]` 在 `utils/unmask_swap_xhard.py`（`env._sampling["decision"]["xhard"]`）及 VUS/BUS/VR/PickXtimes/SwingXtimes/InsertPeg/StopCube；episode_spec/task_goal/xhard_home_site 里是 `== "xhard"` / `!= "xhard"` 字面比较，不是 `decision["xhard"]` |
| `spawn_random_cube/target` | `utils/object_generation.py` | grep | 一致 | 两函数都在；已有 V5 可选参数 `center_exclusion`、`min_center_dist` |
| `DIFFICULTY` / `SEED_RULE` | `scripts/parity/v4_specs.py` | grep | 一致 | `DIFFICULTY = "xhard"`，`SEED_RULE.offset` 4_000_000、env_block 100_000（16 环境占 1.6e6，计划 6e6/8e6/10e6/12e6 间隔 2e6 不重叠）；`DIFFICULTY` 另见 `v4_rollout.py`、`train_split_runner.py`、`scripts/injection/rollout/single_binfill.py` |
| `RELEASE_NOTES` | `train_split_config.py` 加 newtask-v6 | grep | 一致 | 现有 newtask-v4/v5 两键 |
| `NATIVE_SAMPLING` | 各环境 | grep | 一致 | 28 文件 |
| `NATIVE_SPEC_GOLDEN` / `NATIVE_AST_GOLDEN` | 不动 | grep | 一致 | 只在 `tests/lightweight/test_v5_xhard_pickswing.py` |
| `_spawn_cubes_xhard` | BinFill | grep | 一致 | `BinFill.py` |
| `_plan_swap_partners_xhard` / `_xhard_planned_partner` | VR | grep | 一致 | `VideoRepick.py`（前者为模块级函数） |
| `plan_distractor_swaps` / `evaluate_outer_candidate` / `predict_inner_windows` / `prejudge_inner_windows` / `joint_sweep_from_actual` | 2.2 | grep | 一致 | 全在 `utils/unmask_swap_xhard.py` |
| `check_swap_sweep_prefiltered` | 2.2 | grep | 一致 | 定义在 `utils/bin_collision.py`，被 unmask_swap_xhard、VR 引用 |
| `swap_initiator_indices` / `swap_initiator_third` | 2.2 | grep | 一致 | 是 VUS/BUS 里的 spec 记录键 `objects.swap_initiator_indices/third` |
| `_compute_dynamic_swap_candidates` / `_select_swap_pair_from_positions` | 「死代码」 | grep | 存在 | 在 VUS/BUS **以及 VR** 三处都有；计划只点了 Unmask |
| `demo_return_policy` / `return_to_origin` | VPB/VPO | grep | 一致 | `xhard_home_site.py::RETURN_TO_ORIGIN` |
| `visit_selection.count_sampler` | VPO 按档取上界 | grep | 存在，**位置冲突** | 它在 `NATIVE_SAMPLING.parameters`（native 块，V0 要求零 diff），第二部分表又写 decision 子树新键 `visit_count_max`（源码无），两处说法不一致；只能走 decision 新键 |
| `path_search_max_attempts` | PatternLock | grep | 一致 | `PatternLock.py::XHARD_DECISION` |
| `segment_count_range` | RouteStick | grep | 一致 | 只在 `decision.xhard` 下；原三档读 `parameters.configs.<d>.length` |
| `demo_layout` / `execution_layout` | MoveCube | grep | 一致 | 两者下各有 `xhard.center_exclusion` 子树；计划新子键 `region` 不存在（新增） |
| `swap_speed_multiplier` / `distractor_swap` | VUS/BUS | grep | 一致 | `decision.xhard.*` |
| `corner_bias` | PickXtimes/Swing 子树 `corner_bias: 0` | grep | **不一致** | PickXtimes/SwingXtimes 的 decision 已无此键（V5 L43 删除，SwingXtimes 注释「本环境没有 corner_bias」）；源码中只剩 `MoveCube.configs.<d>.corner_bias` 与 `utils/xhard.py::corner_push`。写回会触发 `_xhard_shape` 的「申报外新键」 |
| `hsv_floor_color` | PH 子树 | grep | **不一致** | 源码只有常量 `utils/xhard.py::HSV_FLOOR_COLOR` 与 decision 键 `block_color_policy: "hsv_floor"` + `block_color_hsv`；`hsv_floor_color` 仅是测试名 `test_hsv_floor_color_gamut` |
| `exact_obb` | PH 子树 | grep | **不一致** | 源码无此键；精确 OBB 在 xhard 分支硬编码调用 `cube_obb2d_exact`；`exact_obb` 只出现在测试函数名 |
| `min_center_gap` | PickXtimes/Swing、VR 子树 | grep | **不一致** | 源码 0 命中；实际键 `min_center_dist_m`（PickXtimes/Swing 在 `decision.xhard`，VR 在 `decision.xhard.layout`） |
| `distractor_count` | PickXtimes/Swing 子树 | grep | **不一致** | 不是 decision 键，只是 spec 记录路径 `objects.distractor_count`；干扰数由 `distractor.colors` 长度决定 |
| VU/BU `distractor.{count, cube_range}` | 第二部分表 | grep | **部分不一致** | `count` 对；`cube_range` 实为 `cube_count_range`（`"cube_range"` 只在一个测试文件字符串里）。且 VU/BU 还有第二个 xhard 子树 `bin_layout_policy.xhard.min_gap_factor`，表未列 |
| VR `{min_center_gap 0.12, partner_policy: balanced}` | 第二部分表 | grep | **不一致** | 实际 `xhard.layout.min_center_dist_m`、`xhard.swap_plan.partner_rule`（"reset_plan_nearest_feasible"）；另有嵌套 `num_repeats_range.xhard`（手写，非自动派生），表未列 |
| BinFill `<tier>.{layout: clutter, color_mix}` | 第二部分表 | dump | **不一致** | 实际位于 `decision.configs.xhard.{layout_mode, color_mix}`（BinFill 没有顶层 `decision.xhard`），键名 `layout_mode` |
| `random_yaw` | MoveCube | grep | 一致 | `spawn_random_cube(random_yaw=True)` ⇒ `u·2π` |
| `partner_policy` / `inner_swap_policy` / `visit_count_max` / `is_newvalue_difficulty` / `newvalue_tier` / `NEWVALUE_DIFFICULTIES` / `v6_generation.py` | 新增 | grep | 不存在（预期） | 均为计划新建 |
| `seed_layout.DIFFICULTY_ORDER` / `generate_dataset_newseed.py` / `injection/*` | 不动 | ls/grep | 一致 | `scripts/seed_layout.py`、`scripts/generate_dataset_newseed.py`、`scripts/injection/` 存在 |
| 测试文件 | `test_v4_xhard_{pickxtimes,swingxtimes,stopcube}`、`test_episode_spec_recorder`、`test_sampling_config_split`、`test_v5_xhard_pickswing`、`test_v5_generation_tools`、`test_episode_action_sampling` | ls | 一致 | 均在 `tests/lightweight/` |
| 「断言恰 4 档」 | → 7 档 | grep | 存在，**但 stopcube 不该改** | `test_v4_xhard_{pickxtimes,swingxtimes,stopcube}.py` 都有 `assert set(CLS.configs) == {"easy","medium","hard","xhard"}`。StopCube 不加档，其断言应保持 4 档，计划写「4 → 7 档」错。另有 `test_operand_scope.py`（`operand_sha256(..., {"easy","medium","hard","xhard"})`、`difficulties_of(GROUPS_V3)`）计划未列；`test_episode_action_sampling.py` 的 4 档 parametrize 已在计划清单内 |
| VR `elif self.difficulty == "hard"` 链 | 族判断必须在前 | 读码 | 一致 | `VideoRepick._load_scene`：`if == "xhard"` → `elif == "hard"`（聚簇）→ `else`（easy/medium）；新档若不先族判断会落进 else 分支按 `configs[difficulty]['cube']` 走 |
| RouteStick `.get(difficulty, 回退 easy)` | 改缺键抛错 | 读码 | 一致 | `sampling_configs.get(getattr(self,"difficulty","easy"), sampling_configs[fallback_difficulty])`，`NATIVE_SAMPLING.parameters.configs_fallback_difficulty = "easy"`；另：`RouteStick.__init__` 无显式 difficulty 时按 seed%3 赋值后又被无条件覆盖为 "easy"（上游原样，非本轮问题） |

## 四、必须改（标红）

1. <span style="color:red">**口径 5 与 N7 / 3.2 互相矛盾**：前者「单调不减 + 至少一个字段严格」，后者「所有加码字段严格」。按 N7 字面，计划自己的表在 ≥10 个字段上违例，`TIER_MONOTONE=PASS violations=0` 不可能达成。须二选一，并明确「加码字段」清单（建议逐环境列出参与判定的字段，排除框半宽、搜索预算、交换步数等机制型字段）。</span>
2. <span style="color:red">**PH 干扰数没有被加码**：用户点名「pickhighlight 按照干扰数量」，但计划均值 3/3/3.5/3/3（hard 与 xhard 相等，x2 越过 xhard，x3 下降）。spawn 与 pick 独立抽，xhard 本身的干扰均值就等于 hard。须重排 spawn/pick 使干扰均值严格递增，或改为直接按干扰数抽。</span>
3. <span style="color:red">**VPB/VPO「演示放置次数」计数口径错**：原三档已有一段 pick + `drop onto goal_site`，`return_to_origin` 只是替换这段终点，hard→xhard1 的 pick-place 段数不变。另外 VPB x1→x2、VPO x1→x2 的「放回」字段倒退、VPO x2 的 v 均值 2.5 < hard 3，违反口径 5「单调不减」。</span>
4. <span style="color:red">**`validate_demo_plan` 放行范围不全**：除 `return_last_only` 外，`(k=2, 不放回)`（VPB x2、VPO x2/x3）也被现逻辑拒绝；且原三档只有一个 `goal_site`，「k=2 不放回」时两块的去处未定义。</span>
5. <span style="color:red">**第二部分一 decision 子树键名与源码不符**：`min_center_gap`→`min_center_dist_m`（PickXtimes/Swing 在 `xhard`，VR 在 `xhard.layout`）；`corner_bias` 在 PickXtimes/Swing 已删，写回会被 `_xhard_shape` 当作申报外新键；`distractor_count` 不是 decision 键；PH 的 `hsv_floor_color`/`exact_obb` 不存在（实为 `block_color_policy`/`block_color_hsv`，OBB 硬编码）；VU/BU `cube_range`→`cube_count_range`；VR `partner_policy`→`swap_plan.partner_rule`；BinFill 实际在 `decision.configs.<tier>.{layout_mode, color_mix}`。</span>
6. <span style="color:red">**测试改动清单错一处、漏一处**：`test_v4_xhard_stopcube` 的 4 档断言不应改成 7 档（StopCube 不加档）；`test_operand_scope.py` 的 4 档写法（`operand_sha256`/`difficulties_of`）未列入。</span>
7. <span style="color:red">**2.3「干扰总数保证 > hard 的 15 个容器」对 BU xhard1 不成立**（8+7=15）；若「干扰总数」指干扰单独计数，VU 8、BU 7 都 < 15。须改句或改数。</span>

## 五、建议改

1. PickXtimes x3 [7,12]、SwingXtimes x3 [5,8] 的下界高于 xhard 下界（6、4）：均值合规，但 x3 的最易局比 xhard 最易局还难。若「单调不减」要落到区间界，建议 x3 下界 ≤ xhard 下界（如 [6,13]、[4,9]）；否则在口径 5 写明「只看均值」。
2. VR 块数 hard 15 → x1 4 下降、x3 = xhard = 6；VU/BU 内环容器 15 → 8 下降。前者已挂 M9；后者建议也在 1.4 挂待决或在口径 5 写明「内环容器数不算加码字段」。
3. VUS/BUS 新档外环 `cube_count_range` 未给（xhard 为 [5,5]/10）；BinFill 新档投入色未给（hard/xhard 同 [2,3]）；建议补齐，免得实施方自填（N3）。
4. VPO v 上界按档取：`visit_selection.count_sampler` 在 native 块（V0 要求零 diff），只能走 decision 新键；2.10 正文与第二部分表的两种说法统一为 decision 键。
5. VUS 外环「环带 [0.2675,0.45]」实为方环（`max(|x|,|y|)`），建议写明，与 MoveCube 圆环区分。
6. MoveCube 现状「方块框 ±0.10、面积 0.040」只是候选中心框，实际方块中心还要再抖 ±0.03（约 ±0.13）；与 U 的 0.080 m² 对比时注明口径。
7. 死代码 `_compute_dynamic_swap_candidates`/`_select_swap_pair_from_positions` 在 VR 也有，2.2 只点了 Unmask。
8. 2.0 行「`decision["xhard"]`」对应到 episode_spec/task_goal/xhard_home_site 不准确（那里是 `== "xhard"` 字面比较）；「src 约 105 处」口径未说明（实测字面量 130、`==/!=` 比较 61）。
9. 3.3 提交编号「S1 = 12.136 … S7 = 12.152」与现 HEAD 已到 12.139 冲突，需顺延。
