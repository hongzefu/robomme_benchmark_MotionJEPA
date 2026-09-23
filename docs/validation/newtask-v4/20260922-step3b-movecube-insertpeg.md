# V4 步 3b（g9）：MoveCube + InsertPeg 的 xhard

> 红线 N1 逐步报告。起点 `12.66`（`00e2ef4`）。录像器 `RecordWrapper.py` 未改（`RECORDER_FROZEN=PASS`）。
> 对应计划 2.16（Imitation 族两条前提）、2.17（MoveCube）、2.18（InsertPeg）、2.21 两张简图。
> 本机（sm_89）结果只用于调试，不进判据（口径 10）。

## 一、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `MoveCube.py::MoveCube.configs`（新增 `config_native` / `config_xhard`） | A6：`easy/medium/hard` 同一份原值（±45°、`corner_bias=0`），`xhard` = `peg_yaw_range {span 2π, offset π}`、`corner_bias=None` | A4/A6：本环境原本无分档；G3 未定数，默认写 None | `test_v4_xhard_movecube.py::test_configs_three_tiers_identical_and_xhard_values` |
| `MoveCube.py::_native_decision` | 原值键逐字不动；新增 `demo_layout.xhard.corner_bias`、`execution_layout.xhard.corner_bias`、`peg_yaw_range.xhard` | 守卫只放行 `xhard` 子键偏离；演示段与执行段**各自声明、各自消费**（两套不可合并） | `test_decision_visible_part_unchanged_and_guard`（去掉 xhard 后与 V3 原值逐键相等；两段取不同值守卫放行；原值偏离拒绝） |
| `MoveCube.py::MoveCube._load_scene` | xhard 分支：杆 x/y 抖动与方块候选中心的 `u` 经 `corner_push(u, bias)`，方块小区 `spawn_random_cube(corner_bias=bias)`；两次 yaw 改读 `peg_yaw_range.xhard`（±180°）；取值点带 `decision_key`；末尾 `record` 本局生效的 `layout.{demo,execution}.corner_bias` | 计划 2.17 表：cube 与 peg 推向边角、yaw ±180°（A1） | 原三档 `corner_push(u, 0.0)` 原样返回同一对象、`spawn_random_cube` 不多传参数、yaw 仍读顶层 span/offset ⇒ 随机调用序列逐字不变（reset 探针 diff=0） |
| `MoveCube.py::MoveCube._load_scene`（D3） | xhard 下 `_sample_cube_center` 返回 None ⇒ 抛 `SceneGenerationError`（演示段、执行段各一处）；`spawn_random_cube` 内部的 `RuntimeError` 在 xhard 下转成 `SceneGenerationError` | D3 只在 xhard 修（H2/N12）；`SceneGenerationError` 在生成器里是任务性失败（可换 seed），原来的 `TypeError` 会被当成代码 bug | 原三档仍保留 `float(None)` 的 `TypeError` 路径（未动）；几何蒙特卡洛量化见「实测数字」三 |
| `MoveCube.py::MoveCube._xhard_corner_bias`（新增） | xhard 取 `corner_bias`：None ⇒ 抛 `SamplingConfigError`（「待用户定数（G3），请经 sampling_config 显式传入」）；越界 [0,1] 同样拒绝 | 简报要求：G3 未定时 xhard reset 抛明确错误，不许静默当 0 | `test_corner_bias_validation`；实跑 `gym.make(..., difficulty="xhard")` 不传配置 ⇒ `SamplingConfigError`（冒烟 1/1 按预期失败） |
| `MoveCube.py::MoveCube.__init__` / `_initialize_episode` | xhard 时设 `_xhard_peg_yaw_reduction=True`；每次初始化清 `_peg_grasp_flipped` / `_peg_grasp_flip_log` | B11 归约开关挂在环境上，求解器按它分叉；原三档**不设**这个属性 | 求解器用 `getattr(..., False)`，原三档路径与改前逐字相同 |
| `InsertPeg.py::InsertPeg.configs`（新增） | A6：三档 = 原值 `{peg_count 3, peg_offsets [0.1,0,-0.1], near_target_distractor None, ±45°}`；xhard = `{peg_count 4, peg_offsets [0.1,0,-0.1,-0.2], near_target_distractor {anchor_peg_index 0, max_center_distance_m 0.085}, ±180°}` | 计划 2.18 表 | `test_v4_xhard_insertpeg.py::test_configs_three_tiers_identical_to_native` |
| `InsertPeg.py::_native_decision` | 原四键逐字不动；新增顶层 `xhard`（= `configs["xhard"]` 深拷贝） | 同上 | `test_decision_visible_part_unchanged_and_guard`（含「xhard 里多出申报外键被拒」） |
| `InsertPeg.py::InsertPeg._load_scene` | xhard 下 `decision_cfg` 改读 `xhard` 子键 ⇒ 构造 4 根杆；`randint(0, peg_count)` 取值域变成 4（结果仍被 `overridden_to=0` 覆盖），带 `decision_key="xhard.peg_count"` | 计划 2.18：`peg_count` 同步 4，⚠ 平移随机流（仅 xhard，计划明文可接受） | xhard 冒烟 20/20 `n_pegs=4` |
| `InsertPeg.py::InsertPeg._initialize_episode` | xhard：前 3 根照原判据均匀拒绝采样（yaw ±180°）；**第 4 根排到 `obj_sample/dir_sample` 之后**由 `_xhard_place_near_target_peg` 放；放不下抛 `SceneGenerationError`（前 3 根的 512 次耗尽同样） | N5：xhard 新增抽样追加在既有取值点之后；2.2④ 不许静默截断 | 冒烟 20/20：`peg_placement={requested:4, placed:4}`、`peg_init_poses[3]` 与实际位姿一致 |
| `InsertPeg.py::InsertPeg._xhard_place_near_target_peg`（新增） | 以目标杆 peg_0 为圆心、半径 ∈ (length·1.5, `max_center_distance_m`]、方位均匀采样；判据与原三档**完全相同**（离孔板 > 0.06、与任何已放杆 > 0.075、落在原杆位区域内），上限沿用 512；记 `pegs.3`（`decision_key="xhard.near_target_distractor"`）、`peg_placement`、`near_target_distance`、`near_target_attempts`；按下标覆盖 `peg_init_poses[3]` | B6：判据不动，「在现判据允许范围内尽量贴近 0.075 下限」；`near_target_distractor` 此前无消费点 | 冒烟 20/20：peg3↔peg0 距离 0.0751~0.0839 m，任意两杆最小距离 > 0.075 |
| `utils/subgoal_planner_func.py`（新增 `_quat_wxyz_mul` / `_quat_x_axis_heading` / `peg_grasp_needs_flip` / `flip_grasp_q` / `_xhard_reduce_peg_grasp_q` / `_xhard_peg_grasp_flipped`） | B11 归约工具：夹爪 x 轴朝向相对「基座→抓取点」方位角超过 ±90° 时右乘 Rz(π) | 见二、B11 | `test_native_yaw_range_never_flips`（±45° 从不翻）、`test_reduced_grasp_keeps_relative_heading_within_90`（归约后相对角 ≤90°，approach 轴不变） |
| `utils/subgoal_planner_func.py::grasp_and_lift_peg_side` | 仅当环境带 `_xhard_peg_yaw_reduction` 时调用归约，记 `_peg_grasp_flipped` | B11：只改夹爪姿态、不碰杆位姿 | `test_grasp_and_lift_sets_flag_only_when_switch_on`（开关关时不设属性、姿态与原来相同） |
| `utils/subgoal_planner_func.py::insert_peg`（`_resolve_target_pose`） | 翻转过时局部平移 (x,y,z) → (−x,−y,z)（在原有的 head-tail 补偿之后） | ⚠ 夹持等价 ≠ 整段动作等价（Codex 审计） | `test_insert_peg_waypoints_equivalent_after_flip`：obj × direction 四组合 × 3 个 yaw，世界系 TCP 路点与杆位姿逐点一致（1e-5）；反例 `test_insert_peg_without_compensation_diverges` 不补偿时差 > 0.1 m |
| `utils/subgoal_planner_func.py::solve_push_to_target_with_peg` | 翻转过时推杆姿态右乘 Rz(π)（路点位置本就在世界系，不变） | MoveCube 抓杆后的推杆同样要核 | `test_push_waypoints_equivalent_after_flip`：obj_flag × direction 四组合 × 2 个 yaw，杆世界位姿一致；反例不补偿时杆长轴反向（点积 < −0.99） |
| `utils/vqa_options.py::_options_insertpeg` | **未改代码** | `available = env.peg_heads + env.peg_tails`，随杆数自动 6→8，且只有 xhard 有 4 根杆 | `test_vqa_insertpeg_available_scales_with_peg_count` |
| `tests/lightweight/test_v4_xhard_movecube.py` / `test_v4_xhard_insertpeg.py`（新增） | 纯 CPU 结构测试 + 路点等价测试（mock 夹爪/杆刚体，不起 sapien 场景） | 必做验证 4 | 20 + 87 项全过（约 4 s） |
| `docs/validation/newtask-v4/step3b-g9-scripts/placement_mc.py`（新增） | 两环境 xhard 放置失败与杆重叠的纯几何蒙特卡洛 | 量化 `max_attempts=512` 耗尽风险与 D3 | 见「实测数字」三、四 |

## 二、B11 等价朝向归约：判据与补偿

- **判据**：`rel = heading(夹爪 x 轴) − atan2(抓取点 − 基座)`，`|wrap(rel)| > 90°` 则 `grasp_q ← grasp_q ⊗ Rz(π)`。
  实测 home 姿态 TCP 四元数为 `[0,1,0,0]`（即 Rx(π)，x 轴沿基座径向）、`q7 ≈ π/4 − rel`（诊断中 5 条实跑逐一吻合），
  因此归约后 `q7 ∈ [−45°, 135°]`，距 ±166° 限位至少 31°。原三档 ±45° 杆加基座方位角约 ±25° 以内，相对角最多约 70°，从不翻。
- **插杆补偿**：`_compute_insert_pose = box · insert_obj⁻¹ · tcp`，夹爪相对杆多一个 Rz(π) ⇒ 结果也右乘 Rz(π)；
  它与 obj/direction 的 Rz(π) 可交换，所以局部平移换成 `Rz(π)·off = (−x,−y,z)` 后，世界系 TCP 位置与杆的完整位姿都与未归约时相同
  （推导与单测一致；`obj=1, direction=−1` 的 head-tail 补偿只用相对位置，不受翻转影响，先补偿再取反）。
- **推杆补偿**：推杆路点位置在世界系、姿态由推方向构造；杆相对夹爪多了 Rz(π) ⇒ 推杆姿态右乘 Rz(π)，杆的世界位姿不变。
- **实跑证据**：InsertPeg seed 920202 两次抓杆都翻转，演示段与执行段插杆都成功；MoveCube seed 910202（b=0.5，peg_push）两次抓杆都翻转，推杆成功。
  InsertPeg seed 920000 翻转后失败，但关掉归约（`--no-reduce`）对照同样失败 ⇒ 失败与归约无关。

## 三、实测数字

### 1. 原三档 reset 零差异（必做 1）

```text
uv run --no-sync python -m scripts.parity.v4_reset_probe probe --tasks MoveCube,InsertPeg --out <g9_probe2.json>
uv run --no-sync python -m scripts.parity.v4_reset_probe diff artifacts/newtask-v4/probe/base-13e.json <g9_probe2.json>
RESET_REGRESSION=FAIL compared=18 diff=0 missing=126
```

18 行（两环境各 9 行）全部 reset 成功、`diff=0`；FAIL 只因基线其余 14 个环境的 126 行不在本次探针里（预期）。
最后一处改动（`random_peg_idx` 加 `decision_key`）之后重跑，结果相同。

### 2. xhard reset 冒烟（必做 2，每环境 20 个 seed：900000+101·i）

| 环境 | 成功 | 关键新值 | spec_kind |
|---|---|---|---|
| InsertPeg | 20/20 | 杆数 4、`placement={4,4}`；peg3↔peg0 距离 0.0751~0.0839 m（全部落在 (0.075, 0.085]），近杆尝试 1~5 次；yaw 覆盖 −174.8°~170.2°；obj×dir 四组合都出现 | 全部 `native-newvalue/1` |
| MoveCube（`corner_bias=1.0`） | 20/20 | 两段 yaw 都在 [−180°,180°)（−169.6°~177.5°）；杆根点 `|x|≤0.05`、`|y|∈[0.15,0.25]`；方块中心被推到约 ±0.12；三种 way 都出现 | 全部 `native-newvalue/1` |
| MoveCube（不传配置、`corner_bias=None`） | 0/1（按预期） | `SamplingConfigError: decision.demo_layout.xhard.corner_bias 待用户定数（G3）` | — |

MoveCube 冒烟另算了「杆中轴线到方块中心」的最近距离：40 个布局中 1 个为 0.017 m（< 方块半边长 0.02 + 杆半宽 0.01，即初始重叠，seed 900404 演示段）。

### 3. 放置失败风险（几何蒙特卡洛，`placement_mc.py`）

- **InsertPeg 512 次耗尽**：原三档 0/20000；xhard（`d_max=0.085`）1/20000（≈5e-5，全部失败在第 4 根）。
  近杆单次接受率均值约 0.59，尝试次数均值 1.7、p95 为 4；单局接受率最低 0.02（锚点被挤在区域角落 + 另两根杆占位），此时 512 次全失败约 3e-5，与直接计数吻合。`d_max` 取 0.08 / 0.1 时失败率同为 1/20000。
- **MoveCube D3（方块中心 128 次拒绝）**：对 goal 可行域取 21×21 网格找最坏位置，单次拒绝率 b=0 为 0.78，b≥0.25 为 0.42~0.51 ⇒ 128 次全失败上界 b=0 约 2e-14、b≥0.25 约 1e-38 以下。边角偏置反而**降低** D3 触发（方块被推离中间的 goal）。D3 修复是正确性保障，实际几乎不触发。

### 4. InsertPeg 初始几何重叠（`placement_mc.py::run_insertpeg_overlap`，4000 局）

| | 任一对杆重叠 | 目标杆 peg_0 与他杆重叠 |
|---|---|---|
| 原三档（3 根均匀、±45°） | 3.9% | 2.4% |
| xhard（第 4 根贴近 peg_0、±180°） | 35.4% | 31.6% |

判据「中轴线距离 < 2×radius = 0.02 m」。杆跨度 0.1 m（根点前 0.025、后 0.075）而中心间距下限只有 0.075 m，
第 4 根又刻意贴近下限 ⇒ 重叠率上升一个数量级。重叠的杆在第一个仿真步被弹开，目标杆可能被撞翻/滚转：
诊断中 seed 920101 的目标杆在抓取前已从 yaw −135° 被撞到 yaw 约 10°、侧翻约 90°（抓取点 z 0.015），随后插杆 IK 无解。

### 5. xhard 演示小样本（必做 3，`v4_demo_probe`，本机 GPU 0）

**InsertPeg：6/10 成功**（口径 14 要求至少 6 条：共跑 10 条）

| seed | 结果 | 分类 / 诊断 |
|---|---|---|
| 910000 | ✓ | 未翻转 |
| 910101 | ✗ PlannerExhausted | 第一次抓杆 IK 差 0.038 m：目标杆头在 (0.173, −0.277)，杆位区域远角，接近 Panda 可达边界；未翻转，与归约无关 |
| 910202 | ✓ | 未翻转，插杆末端 q7=2.60（149°） |
| 920000 | ✗ 跑完 task_list 未成功 | 两次都翻转；关掉归约对照同样失败 ⇒ 与归约无关 |
| 920101 | ✗ PlannerExhausted | 目标杆被初始重叠的干扰杆撞翻（见 4），插杆 IK 无解 |
| 920202 | ✓ | 两次都翻转，插杆成功（补偿实跑证据） |
| 930000 / 930202 / 930303 | ✓ ✓ ✓ | — |
| 930101 | ✗ 跑完 task_list 未成功 | 未逐条诊断 |

**MoveCube：G3 扫描（演示段与执行段取同一 `corner_bias`；yaw ±180° 同时生效）**

扫描样本 = 主扫描 4 个 seed（910000/910101/910202/910303）+ peg_push 补充 4 个 seed（910404/910505/910606/910808）。
⚠ way 由 `_initialize_episode` 最后一次 `randint` 决定，而方块拒绝采样的抽样次数随 bias 变化 ⇒ **同一 seed 在不同 bias 下 way 可能不同**，下表按每个 bias 逐条 reset 复核的 way 统计。

| corner_bias | 总成功 | peg_push | gripper_push | grasp_putdown | 失败条目与分类 |
|---|---|---|---|---|---|
| 0.0 | **8/8** | 4/4 | 2/2 | 2/2 | — |
| 0.25 | **7/8** | 3/4 | 2/2 | 2/2 | 910606（peg_push）跑完 task_list 未成功 |
| 0.5 | **6/8** | 3/5 | 2/2 | 1/1 | 910202（peg_push）跑完未成功（同配置诊断重跑成功，属规划器非确定性）；910404（peg_push）跑完未成功 |
| 0.75 | **6/8** | 3/5 | 1/1 | 2/2 | 910404（peg_push）跑完未成功；910606（peg_push）PlannerExhausted |
| 1.0 | **5/8** | 2/4 | 1/2 | 2/2 | 910404（此 bias 下为 gripper_push）跑完未成功；910505 / 910606（peg_push）PlannerExhausted，诊断均在**执行段推杆**规划失败（一条翻转、一条未翻转） |

- 口径 14：5 个 bias（含两个端点）× 三种 way，每格都至少 1 条演示成功 ⇒ **没有演示级 0 成功的组合**。
- 趋势：peg_push 成功率随 bias 单调下降（4/4 → 3/4 → 3/5 → 3/5 → 2/4）；grasp_putdown 始终全成；gripper_push 只在 b=1.0 出现 1 条失败。
  边角把方块推到 ±0.12 附近后，推杆起点（方块后退 0.1 m 再侧移 0.1 m）落到可达边缘，是 b 大时 PlannerExhausted 的主要原因。
- 原始记录：`artifacts/newtask-v4/demo-probe/MoveCube-g9-b{0.00,0.25,0.50,0.75,1.00}/` 与 `MoveCube-g9-pegpush-b*/` 的 `summary.jsonl`（artifacts 不进 Git）。
- 样本量小（每 bias 8 条）、本机不进判据，只供定数参考。

### 6. 轻量测试（必做 4）

- 新增两文件：`test_v4_xhard_movecube.py` 20 passed、`test_v4_xhard_insertpeg.py` 87 passed。
- `tests/lightweight/ -m 'not gpu and not slow'`：**47 failed / 628 passed / 22 skipped / 12 errors（128 s）**。
  与已知基线 46 项相比多 1 项：`test_sampling_config_split.py::test_snapshot_matches_source`——源码 decision 新增了 xhard 条目，
  `scripts/configs/newtask-v4/sampling_config.json` 快照与源码不再一致。按简报，快照由主 agent 统一重导，本组**不提交**快照；
  重导后此项应恢复。其余 46 项与基线同名同数。

## 四、计划外

1. **InsertPeg 的初始杆重叠率从 2.4% 升到 31.6%**（目标杆），是 xhard 演示失败的主要来源之一（见三、4 与 seed 920101）。计划 2.18 只提到「既有穿插风险保持原样」，没有预计到贴近下限后会放大一个数量级。
2. **MoveCube 的 way 随 corner_bias 变化**：方块拒绝采样的抽样次数依赖 bias ⇒ `way_idx` 那次 `randint` 在随机流里的位置平移。V6 组合覆盖扫描若按「bias × way」组合统计，必须按实际 way 归档，不能假定同 seed 同 way。
3. **`_options_insertpeg` 不用改代码**：候选是 `peg_heads + peg_tails` 按杆数自动展开。
4. **归约判据比最低需要更保守**：`q7 ≈ π/4 − rel` 是不对称的，真正不可达的只有 `rel ∈ (−149°, −121°)` 附近；±90° 判据会在一些本来可达的朝向也翻转（例如 seed 920000 未归约时 q7=−1.27 可达）。选择对称 ±90° 是为了在抓杆和后续动作都留出至少 31° 余量；实跑没有发现翻转导致的失败。
5. **MoveCube 避让列表没有杆**：冒烟 40 个布局中 1 个杆与方块初始重叠（计划 2.17 已点名，未修，仅量化）。
6. 工作树建出时停在 `3a5951a`（不是说明里的 `00e2ef4`），已在干净状态下 `git reset --hard 00e2ef4` 后开工。

## 五、待用户决策

1. **G3：MoveCube `corner_bias` 取值**（代码里 xhard 默认 None，不传即拒绝）。依据见三、5 的扫描表。
   仅供参考、不作默认：若要「更难但仍稳定可生成」，0.25~0.5 保住 75%~88%；1.0 下 peg_push 只剩一半、gripper_push 也开始失败。
2. **G3：成功率扫描的样本量**：本轮每个 bias 8 条（其中 peg_push 4~5 条），95% 区间很宽；建议 V6 每组合至少 10~20 条且在 A40 上跑。
3. **InsertPeg `near_target_distractor.max_center_distance_m = 0.085`** 是实施方为「尽量贴近 0.075 下限」取的带宽上限（计划没给数），可经 sampling_config 覆盖；0.08~0.1 对放置失败率无影响（均约 5e-5），主要影响重叠率。请确认或改值。
4. **InsertPeg 初始重叠是否处理**（计划外 1）：选项 A 维持现状（B6 字面），接受约 30% 局目标杆开局被撞；选项 B 只对第 4 根杆额外加「中轴线距离 > 2×radius（+余量）」的几何不重叠检查（更严、不放松 B6 的中心距判据，但属于新增判据，需要用户批准）；选项 C 把第 4 根的锚点距离带往外移。未实现，等用户定。
