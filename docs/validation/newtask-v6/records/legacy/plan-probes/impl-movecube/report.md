# V6 MoveCube xhard 统一区域 U（圆环版）源码实现报告（2026-09-25）

> 副本 worktree `/data/hongzefu/v6-draft/movecube`，分支 `v6-draft-movecube`，自 `e1755f9` 切出；提交 `7adbca5`（`12.139-draft-movecube …`），**未 push**。主仓库源码一个字没动（`git status` 仍只有原来就在的 `M NEWTASK_RELEASE_V6_PLAN.md`），只在本目录写了报告和小体积产物。

## 结论

| 验收 | 结果 |
|---|---|
| ① lightweight pytest | MoveCube 相关子集 **133 passed**（18 s）；全量 1359 passed，47 failed + 12 errors **全部是改动前就有的**（在同一 worktree 上 stash 掉改动后重跑，失败清单逐条一致，共 58 项）；本轮唯一引入的新失败 `test_snapshot_matches_source` 已通过重新提取快照修复 |
| ② 真实 reset 2000 局 | `MC_REGION=PASS resets=2000 violations=0 layout_fail=0 actual_mismatch=0`；散点图 `region_check.png` 已目视检查 |
| ③ 真演示 12 局 | **9/12**：peg_push 3/4、gripper_push 2/4、grasp_putdown 4/4；3 局失败都是 task 类「推没到位」 |
| ④ 原三档逐位 | easy/medium/hard 各 1 个 seed 做真实 reset，主仓库与副本逐字 **IDENTICAL**；离线金标准哈希（3 档 × 44 seed）照旧通过 |

## 一、改了什么

### 1. `utils/object_generation.py`

`spawn_random_cube` / `spawn_random_target` 新增 4 个显式可选参数，默认都是 None：

| 参数 | 含义 |
|---|---|
| `annulus=(center, r_in, r_out)` | 中心离圆心在 [r_in, r_out] 内 |
| `base_band=(base, lo, hi)` | 中心离基座在 [lo, hi] 内 |
| `segment_clearance=[(a, b, gap), …]` | 中心离每条线段 ≥ gap |
| `push_feasible=(target, d_min, d_max, backoff, lateral, base, r_min, r_max)` | 推距在 [d_min, d_max] 内；三个推起点 `c − backoff·d − s·lateral·n`（s ∈ {0, ±1}）离基座都在 [r_min, r_max] 内 |

- 判定放在 V5 中心规则之后、`recorder.value` 之前，本身不抽随机数。
- 回放冻结值和 `fixed_xy` 注入不走拒绝循环，改为按同一规则复核（N17），违反就抛 `EpisodeSpecError`。
- 四个参数都是 None 时整段跳过。测试已确认「传 None」和「不传」的结果逐位相同。
- 另外公开了一个工具函数 `point_segment_distance_xy`。

### 2. `MoveCube.py`

**配置**

- `config_xhard.center_exclusion` 换成 `config_xhard.region`：
  `{center [-0.06,0], r_in 0.12, r_out 0.20, base_dist [0.35,0.76], push_len_max 0.30, peg_gap 0.04, goal_peg_gap 0.02, peg_max_trials 128, goal_max_trials 256, cube_max_trials 4096}`。
- `_native_decision` 在 `demo_layout.xhard.region` 和 `execution_layout.xhard.region` 各放一份副本。
- `_xhard_region` 负责校验，缺字段或数值不合法时抛 `SamplingConfigError`。

**`_load_scene` 的分叉**

- 读完 decision 后按难度分叉：xhard 进新方法 `_load_scene_xhard_region` 并直接 return。
- 原三档路径删掉了全部 xhard 条件分支；由于原来的条件在 xhard=False 时本来就不生效，删掉后行为逐字等价。
- 两段共用的尾部逻辑抽成 `_sample_obj_and_dir` 和 `_store_goal_poses`，调用次序不变。

**xhard 的新随机次序**（只在 xhard 分支内）

1. length、radius
2. 演示段杆：每次试验抽 3 次 `torch.rand`，依次是抓取点 x、抓取点 y（在圆环外接正方形里均匀抽）和 yaw（±π）。由此推出杆根 = 抓取点 + length·u，经 float32 平移后判定两条：抓取点在 U 内，杆身线段 (−0.15, +0.05) 离 C0 ≥ r_in。不满足就三个值一起重抽。
3. 执行段杆（同上）
4. obj_sample、dir_sample
5. 演示段 goal → 执行段 goal
6. 演示段方块 → 执行段方块

**goal 与方块的约束**

- goal：annulus + base_band + 离本段杆身 ≥ 0.02。
- 方块：annulus + base_band + 离本段杆身 ≥ 0.04 + push_feasible。min_cg 取原 `cube_rejection` 的 5 × 半边长 = 0.10。
- 两者的采样框都是圆环外接正方形，并传 `include_existing=False`、`include_goal=False`：约束全部由区域规则给出。

**删掉的旧逻辑**（xhard 分支内）：V5 的 base_y 抽样、方块候选两级采样、`center_exclusion` 圆禁区、演示段和执行段 goal 用不同框。

**规格与复核**

- 规格键沿用原来的路径。`layout.<seg>.peg_offsets = [0.0, 杆根x, 杆根y]`：base_y 恒为 0，两个「抖动」值就是杆根 xy。
- 新增两个只读记录：`layout.<seg>.region`（带 `peg_axis_extent_m`、`robot_base_xy`、推起点常数、`min_cube_goal_m`）和 `layout.<seg>.region_trials`。
- N17 回放复核：杆由 `_assert_peg_in_region` 复核（`_assert_peg_outside_zone` 的写法，改成离 C0），goal 和方块由 spawn 函数复核。
- 建杆后仍调用 `_xhard_verify_peg_extent`，用实际碰撞/可视几何复核杆身区间。真实 reset 2000 次没有报错。

**抓取点的定义**：抓取点 = tail link 中心 = 杆根 − length·u（length = 0.1）。`evaluate` 里 `obj_flag` 恒为 −1，所以 `grasp_target = peg_tail`，二者一致。

### 3. 预算为什么取这些值

离线用与 `region.py` 相同的判据估算：

- 杆：单次接受率 0.29，128 次预算耗尽的概率是 8e-20。
- goal：单次接受率 ≥ 0.41。
- 方块：受推距和推起点约束，按 goal 的条件接受率均值 0.106、最低 0.005。沿用 256 次预算时期望耗尽 0.32%/段，所以把 `cube_max_trials` 提到 4096，最坏段的耗尽概率约 1e-9。

实测每次试验只是 3 次 rand 加几个判断，reset 仍约 0.25 s/局。

### 4. 测试与快照

- **新增 `tests/lightweight/test_v6_xhard_movecube_region.py`**：判据在测试里独立实现（照 `region.py`，不从被测代码取）。覆盖以下几类：
  - 2000 seed 离线复核，结果 `MC_REGION=PASS seeds=2000 violations=0 layout_fail=0 peg_trials_mean=3.47 max=30`；
  - decision 校验；
  - 杆、方块预算耗尽时抛真 `SceneGenerationError`；
  - 回放：合规规格逐值一致；杆的三种违规（抓取点进内孔、抓取点出外圈、杆身穿过圆心）和 goal/方块违规都报 `EpisodeSpecError`；
  - spawn 新参数：默认 None 与不传逐位相同，给了就按规则拒，注入值违规报错。
- **`test_v5_xhard_movecube.py`**：
  - 原三档金标准哈希不动，照旧通过；
  - 删掉 V5 圆禁区专属用例（禁区校验、5000 seed 禁区统计、禁区预算耗尽）；
  - xhard 子键断言改为 == {"region"}；
  - 杆违规回放用例改为匹配「统一区域 U」；
  - gpu 用例改用 V6 独立判据，结果 `MOVECUBE_EXEC_SPAWN=PASS`。
- **`test_v4_xhard_movecube.py`**：configs/decision 断言从 `center_exclusion` 改为 `region`。
- **`scripts/configs/newtask-v5/sampling_config.json`**：`test_snapshot_matches_source` 要求快照和源码提取一致，所以用 `train_split_config.py extract --release newtask-v5` 重新提取。diff 只有 MoveCube 两段 xhard 的 center_exclusion → region，其余 15 个任务逐字不变。
  - ⚠ 这等于就地改了 V5 快照里 MoveCube 那一块。合入时是另起 `newtask-v6` 快照，还是保留这样改，需要主会话定。

## 二、验收细节

### ② 真实 reset 2000 局

**跑法**：seed 6100000～6101999，`obs_mode=state`，GPU 0/1 各开 2 个进程，每局一次 `gym.make` + `reset`，约 0.25 s/局。脚本是 `reset_check.py`，汇总与出图是 `region_check.py`。

**结果**：`MC_REGION=PASS resets=2000 violations=0 layout_fail=0 actual_mismatch=0`

- 判据用独立实现，同时核对规格值和实际 actor 位姿：两者逐项一致（误差 ≤ 1e-5）。演示段实测杆尾（tail link 中心）也都在 U 内。
- way 分布：gripper_push 648 / peg_push 694 / grasp_putdown 658。

**实测范围**：

| 量 | 离圆心 | 离基座 |
|---|---|---|
| 方块 | [0.1200, 0.2000] | [0.3996, 0.6941] |
| goal | [0.1200, 0.2000] | [0.3559, 0.7546] |
| 抓取点 | [0.1203, 0.2000] | [0.3557, 0.7546] |
| 推起点 | — | [0.3500, 0.7600] |

推距在 [0.100, 0.300] 内，均值 0.208。

**散点图 `region_check.png`**：左图是三物体，右图是推起点和杆身线段。目视检查过，图中文字和图例没有重叠。

**分布特点**：方块中心在圆环上下（y ≈ ±0.15、x ≈ −0.15 一带）更密，+x 远端和 −x 近端稀。这是推距 ≤ 0.30 与推起点离基座区间这两条成对约束筛出来的。goal 和抓取点在环内基本均匀。

### ③ 真演示 12 局

**跑法**：`scripts/parity/v4_demo_probe.py --task MoveCube --difficulty xhard`，3 个 tmux 会话各跑一种 way 的 4 局。seed 按 reset 结果里的 way 挑选；实跑的 way 与 reset 记录一致，因为生成入口也是同一个 `gym.make(seed)` + `reset`。

| way | seed | 成败 | 帧数 |
|---|---|---|---|
| peg_push | 6100001 / 6100002 / 6100004 / 6100006 | ✓ / ✓ / ✗ / ✓ | 543 / 508 / — / 504 |
| gripper_push | 6100000 / 6100007 / 6100011 / 6100012 | ✗ / ✗ / ✓ / ✓ | — / — / 272 / 282 |
| grasp_putdown | 6100003 / 6100005 / 6100008 / 6100009 | ✓ ×4 | 462 / 458 / 478 / 475 |

- **合计 9/12**。3 局失败都是 `failure_class=task`、`DatasetGenerationError: 跑完整个 task_list 仍未成功`，属于推动没推到位。
- 没有 `SceneGenerationError`、`PlannerExhausted`、`EpisodeSpecError`。
- 失败局的位置量都不极端：推距 0.17～0.30，方块离基座 0.48～0.66。它们各有一段方块棱角比较正对推方向（|yaw−推向| mod 90° 离 45° 的偏差：6100000 演示段 9.4°、6100004 执行段 2.8°），与 V6 计划里记录的「失败段方块棱角更朝前」现象一致。样本太小，不下结论。
- **对照**：GL 上 U（R_IN 0.14 版）144 局为 118/144（peg 35/48、gripper 35/48、grasp 48/48），V5 基线为 19/24。本机 12 局 9/12 与之同量级，gripper 2/4 属于小样本波动范围。圆环版在 GL 上的复测由主会话另做。
- h5 和视频（约 2.6 G）已删，只保留各 way 的 summary 和日志。

### ④ 原三档逐位

- `tier_dump.py` 分别以主仓库 src（`PYTHONDONTWRITEBYTECODE=1`，不往主仓库写 pyc）和副本 src 各跑一次真实 reset：easy seed 3000、medium 3001、hard 3002。
- 比对内容：整份 `_spec`；peg / peg_head / peg_tail / goal_site / cube 的位姿；cube 两段初始位姿；goal_site_2 位置；执行段杆位姿；way；reset 后随机流的一个哨兵值。全部按 float.hex 比较。
- 结果三档都是 **IDENTICAL**（way 依次为 peg_push / gripper_push / peg_push）。

### ① pytest 说明

- 全量 lightweight 在本机被其他并行探针挤占时要跑 400 s：280 s 限时那一次被 timeout 杀掉，之后放宽到 600 s 跑完拿到失败清单。
- 58 项既有失败的来源：candidate 封套的 BinFill 源码指纹、BinFill `put_in_color` 快照字段、TaskGoal 文案、step_error_handling、episode_action_sampling 历史口径、rollout_state、injection_migration。都与本改动无关，stash 对照逐条一致。
- 5 分钟内能跑完的 MoveCube 核心子集（6 个文件）为 133 passed。

## 三、要注意的点

1. **V5 冻结规格不能再回放**：v5-01 `specs.jsonl` 里 MoveCube xhard 那几行，`peg_offsets` 语义已经变了，回放必然被判违规。这是计划里「xhard 重冻」的预期后果；V6 要用新的 seed 偏移重出规格。
2. **V5 快照被就地重提**：`scripts/configs/newtask-v5/sampling_config.json` 的 MoveCube 块已按新源码更新，见上文第一节第 4 小节。
3. **误写了共享 scratchpad**：做基线对照时，我曾把 e1755f9 解包进共享 scratchpad 的 `base/` 目录，后来发现这个目录属于另一个 agent。它原本也是同一 commit 的解包（文件 mtime 都是 17:00:30），内容应当相同。之后我改用 `scratchpad/mc/`。如果那个 agent 在 `base/` 里改过文件，可能被覆盖。

## 四、产物（本目录）

- `region_check.png`：reset 2000 局的散点图
- `reset_2000.jsonl.gz`：逐局布局与实际位姿
- `reset_check.py` / `region_check.py`：跑 reset / 汇总与出图
- `tier_dump.py` / `tier_main.json` / `tier_draft.json`：原三档逐位对比
- `demo_{peg,grip,grasp}_summary.jsonl`、`demo_*.log`：12 局演示
- 副本内改动文件：`src/robomme/robomme_env/MoveCube.py`、`src/robomme/robomme_env/utils/object_generation.py`、`tests/lightweight/test_v6_xhard_movecube_region.py`（新）、`tests/lightweight/test_v5_xhard_movecube.py`、`tests/lightweight/test_v4_xhard_movecube.py`、`scripts/configs/newtask-v5/sampling_config.json`
