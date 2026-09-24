# V5 S3c：MoveCube xhard 桌面中心禁区、删 corner_bias、执行段方块不避让演示段方块（2026-09-24）

> 对应计划：`NEWTASK_RELEASE_V5_PLAN.md` 1.1 口径 8、1.4 L30～L34、2.9（伪码与实施要点）、3.5 P2、第二部分「一」S3c 行；红线 N13/N17/N18。
> 工作树：`/data/hongzefu/robomme_v5_wt/movecube`（分支 `v5wt-movecube`，基线 12.120 `328e607`），未 commit。
> 只改 xhard；原三档（easy/medium/hard）规格、位姿与随机流逐位不变（见第四节金标准哈希）。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 |
|---|---|---|---|
| `src/robomme/robomme_env/MoveCube.py` | 模块头 import | 删 `from .utils.xhard import corner_push`；加 `from .utils.episode_spec import EpisodeSpecError` | L33 删干净；N17 复核抛的异常类 |
| 同上 | `config_xhard` | 删 `corner_bias`；加 `center_exclusion = {shape: circle, center: [0,0], radius_m: 0.05, judge: object_center, max_trials: 128}` | L30、L33 |
| 同上 | `_native_decision` | `demo_layout.xhard` / `execution_layout.xhard` 由 `{corner_bias}` 改为 `{center_exclusion}`（各自一份 deepcopy，两段各自声明、各自消费） | 计划 2.9 表第 2 行 |
| 同上 | 新增模块级纯函数 `_peg_axis_extent`、`_peg_root_xy`、`_peg_zone_distance`、`_zone_violated`、`_assert_peg_outside_zone` | 杆轴线段区间、杆根 xy（与建杆同一 float32 算法）、线段到圆心最近距离、物体中心判据、回放复核 | 杆判据与 N17 |
| 同上 | `_load_scene` 档位分叉 | xhard 取 `demo_zone/exec_zone = _xhard_center_exclusion(...)`、`peg_extent = _peg_axis_extent(self.length)`；`decision_key` 改为 `*.xhard.center_exclusion`；原三档 `demo_zone = exec_zone = None` | — |
| 同上 | `_load_scene` 演示段杆、执行段杆 | xhard：`_xhard_sample_peg_outside_zone` 按原顺序抽 x、y、yaw，杆轴线段离圆心最近点 `< 0.05` 就三者原地重抽（上限 128，超出抛真 `SceneGenerationError`；`base_y` 不重抽）；随后照常两次 `_spec.value`，再 `_assert_peg_outside_zone` 复核（N17）。原三档：`(corner_push(u, 0.0) - 0.5)` 改写为 `(u - 0.5)`（`corner_push(u, 0)` 原样返回同一对象，数值逐位相同），yaw 仍在原位置抽 | L30、L31、N17、N18 |
| 同上 | `_load_scene` 建杆之后 | xhard 调 `_xhard_verify_peg_extent(peg_extent)`：读真实杆 head/tail 两个 link 的碰撞盒与可视盒半长、形状局部位姿、tail 固定关节 `pose_in_parent/pose_in_child`，算出沿杆朝向的实际区间，与判据用的区间不一致即 RuntimeError | 任务要求「线段端点从实际碰撞几何取，不写死」 |
| 同上 | `_load_scene` 两段 goal | xhard 多传 `center_exclusion=((0,0),0.05)`；两处 `spawn_random_target` 包进 `try/except RuntimeError`，xhard 下包成真 `SceneGenerationError`，原三档原样 re-raise | L30；预算耗尽的失败分类 |
| 同上 | `_load_scene` 两段 `_sample_cube_center` | 删 `corner_push`；接受条件在 `|c−g| > 0.1` 之后加「xhard 且候选中心离圆心 `< 0.05` 就 `continue`」（与 goal 距离判据共用同一次试验与原 128 次预算），拒绝次数计数 | L32 |
| 同上 | `_load_scene` 两段方块最终 `spawn_random_cube` | xhard 额外参数由 `{corner_bias}` 改为 `{include_existing: False, center_exclusion: ((0,0),0.05)}`（演示段与执行段都是） | L32、L34、2.0① |
| 同上 | `_load_scene` 末尾记录 | 删 `layout.*.corner_bias`；改记 `layout.{demo,execution}.center_exclusion`（配置原样 + `peg_axis_extent_m`）与 `layout.{demo,execution}.center_exclusion_trials`（`peg_trials`、`cube_candidate_center_rejects`） | 注入规则留痕、N18 |
| 同上 | 删 `_xhard_corner_bias`；新增 `_xhard_center_exclusion`、`_xhard_sample_peg_outside_zone`、`_xhard_verify_peg_extent` | 配置校验（shape/judge/center/radius/max_trials 不合法即 `SamplingConfigError`）、杆重抽循环、实测几何复核 | — |
| `tests/lightweight/test_v4_xhard_movecube.py` | 文件头说明、`test_configs_three_tiers_identical_and_xhard_values`、`test_decision_visible_part_unchanged_and_guard`、删 `test_corner_bias_validation` | V4 断言改 V5 语义（见 4.3） | L33「对应单测一并删除」 |
| `tests/lightweight/test_v5_xhard_movecube.py`（新文件） | — | 17 条离线用例 + 1 条 `gpu`/`slow` 真实 reset 用例，见 4.1 | 验收 |

没有改：`utils/xhard.py::corner_push`、`spawn_random_cube` 的 `corner_bias` 形参（PickXtimes 仍用）、`object_generation.py` 任何代码（S2a 的 `center_exclusion` 参数直接用）、`config_native`（含其中未被消费的 `corner_bias: 0.0`，属原三档配置，V0 要求零改动）、`NATIVE_SAMPLING`、`peg_yaw_range` ±π、三条 way、goal 区域尺寸、录像器、`scripts/` 顶层、V4 配置与产物。

## 二、关键设计点

1. **禁区与判据**：圆心 (0,0)、R = 0.05 m；「落进圆」一律按 `距离 < R` 判（边界 `= R` 放行，与 S2a 的 `_center_rules_violation` 同一口径）。
   - 杆：线段 `root + t·u`，`t ∈ [−1.5·L, +0.5·L]`，`L = self.length = 0.1` → `[−0.15, +0.05]`，`u = (cos yaw, sin yaw)`；`root` 用与建杆完全相同的 float32 平移算出。
   - goal、方块候选中心、方块最终中心：按中心判。
2. **杆线段端点的取法（核实结果）**：真实模拟器读 seed 5400000 的杆：head/tail 碰撞盒半长 0.045（`0.45·L`）、可视盒半长 0.05（`0.5·L`），tail 固定关节 `pose_in_parent = (−0.1, 0, 0)`，head 中心 = 杆根、tail 中心 = 杆根 − 0.1·u。所以碰撞外形是 `[−0.145, +0.045]`，可视外形是 `[−0.15, +0.05]`（P2 报的就是可视外形）。
   **实施方取二者并集（= 可视外形 `[−0.15, +0.05]`）**：包住碰撞外形、与 P2 统计口径一致、也对应「画面中心看不到杆」这一用户原意；两者只差 5 mm。区间用 `L` 推出，并在每次 xhard 建杆后用实际形状复核（`_xhard_verify_peg_extent`），build_peg 几何一变就报错，不会静默失效。
3. **随机流**：杆循环每轮按原顺序各抽一次 x、y、yaw（原代码 yaw 在 `peg_offsets` 的 `value` 之后抽，`value` 不抽随机数，所以顺序不变）；被拒时整组重抽，`base_y` 不重抽。goal／候选／方块的拒绝都在各自原有循环内 `continue`，不额外抽随机数。整个流与 P2 离线副本（`plan-probes-r2/movecube_circle/mc_v5.py`，R=0.05、杆段 `(−0.15, 0.05)`、bias 0、执行段不避让）**3004/3004 局逐值一致**（含每局杆重抽次数），见 4.2。
4. **预算**：`max_trials = 128` 只约束新增的杆重抽循环；goal（`spawn_random_target` 默认 256）、候选（原 `max_trials = 128`）、方块最终（`spawn_random_cube` 默认 256）沿用各自原有循环的预算，禁区拒绝计入同一预算，耗尽时 xhard 一律抛真 `SceneGenerationError`（goal 两处是本次新包的，方块两处 V4 已包）。
5. **N17 回放复核**：杆——`peg_offsets`、`peg_yaw` 两次 `value` 返回冻结值后用同一判据复核，违规抛 `EpisodeSpecError`；goal、方块最终——S2a 的 `center_exclusion` 参数已在 `recorder.value` 返回后复核；方块候选中心不进规格、回放时照常由随机流在拒绝循环里重新算出，规则天然成立，无需另复核。
6. **N18**：杆循环只在被接受的那组之后调用 `recorder.value`；尝试次数与候选中心拒绝次数用 `record()` 写在 `layout.*.center_exclusion_trials`，排在全部取值点之后。
7. **L34 与 2.0①**：执行段 `cube_2` 传 `include_existing=False`（两块从不同时在场）；演示段 `cube` 也传 `include_existing=False`——首次建场景时它之前本来没有方块，结果与默认值相同，但这样 xhard 下就**不存在任何以 actor 作障碍的方块**，2.0① 的退化 OBB 缺陷在 MoveCube 结构性消失，不需要 `cube_obb2d_exact`。`include_goal` 保持默认（goal 圆盘无碰撞形状，`get_actor_obb` 取不到，本来就不参与；P2 副本不建模 goal 障碍而与 v4-01 10/10 一致可证）。

## 三、原三档静态自查（diff 逐处）

| diff 处 | 原三档为何逐位不变 |
|---|---|
| 删 `corner_push` import | 原三档只通过 `corner_push(u, 0.0)` 用它，而它对 0 原样返回同一对象 |
| `config_xhard`、`_native_decision` 的 `xhard` 子键 | 原三档不读 `configs["xhard"]`；`_strip` 去掉 `xhard` 子键后 decision 与 V3 逐字相同（既有单测守住） |
| 新模块级函数、新方法 | 只在 `if xhard:` 分支里被调用 |
| 档位分叉 | 原三档新增的只有 `demo_zone = exec_zone = None` 赋值 |
| 两段杆 x/y 抖动 | `(corner_push(u, 0.0) - 0.5) * span` → `(u - 0.5) * span`，同一 float 运算 |
| 两段 yaw | 原三档仍在原位置 `if not xhard:` 下抽，表达式逐字不变 |
| 两段 `_assert_peg_outside_zone`、`_xhard_verify_peg_extent` | 挂在 `if xhard:` 下 |
| goal 的 `**demo_goal_extra`、try/except | 原三档 extra 为 `{}`；except 分支对原三档直接 `raise`，异常类型与消息不变 |
| 候选中心 `_sample_cube_center` | 删 `corner_push(·, 0.0)`（恒等）；新增判断以 `demo_zone is not None` 开头，原三档短路，不多抽随机数 |
| 方块 `demo_cube_extra/exec_cube_extra` | 原三档仍为 `{}` |
| 末尾 `record` | 挂在 `if xhard:` 下 |

实测证据：离线假场景（顶替 sapien 建物体、跑真实 `_load_scene`）对 44 个 seed（0～39 与 1000442、1000446、5400000、5400500）逐档记录完整规格、全部物体位姿（float hex）与调用后随机流哨兵，SHA-256 在改动前（基线 12.120）与改动后**相同**：`84326bef…e3aa94`（easy/medium/hard 三档同值，因为 MoveCube 三档本来同配置）。另在 2000 个 seed 上确认原三档无一抛错。V0：`git diff` 中 `config_easy/medium/hard/native`、`NATIVE_SAMPLING` 零增删行。

## 四、测试

### 4.1 新测试 `tests/lightweight/test_v5_xhard_movecube.py`

| 用例 | 内容 |
|---|---|
| `test_original_tiers_bitwise_unchanged[easy/medium/hard]` | 上节金标准哈希；且原三档调 `spawn_random_cube` 不带任何新参数 |
| `test_corner_bias_removed_cleanly` | 模块源码无 `corner_push`；无 `_xhard_corner_bias`；`config_xhard` 无 `corner_bias`；两段 decision 的 `xhard` 只有 `center_exclusion`；`_load_scene` 源码不再消费 `corner_bias` |
| `test_center_exclusion_decision_and_validation` | 默认规则解析为 `((0,0),0.05)`、128；10 种非法配置（形状、判据、负/NaN/缺失半径、0/小数/布尔预算、一维圆心、缺键）都抛 `SamplingConfigError` |
| `test_peg_axis_extent_matches_measured_geometry` | `_peg_axis_extent(0.1) == (−0.15, 0.05)`（P2 实测） |
| `test_center_exclusion_and_rejection_budget` | **5000 seed（2000000 起）**：每局两段的杆轴线段（测试内独立实现、区间独立写成 P2 实测值）、goal、方块候选中心（从 `spawn_random_cube` 的 `region_center` 截获）、方块最终中心都 ≥ 0.05；无一局失败；两段方块调用参数恰为 `{include_existing: False, center_exclusion: ((0,0),0.05)}`；规格里无 `corner_bias`、有规则与尝试次数；杆规则确实触发过 |
| `test_peg_budget_exhaustion_raises_real_scene_generation_error` | R 调到 1.0：杆循环 128 次耗尽抛真 `SceneGenerationError` |
| `test_goal_budget_exhaustion_raises_real_scene_generation_error` | R 调到 0.09（执行段 goal 中心最远 0.085，必然耗尽）：抛真 `SceneGenerationError`，`__cause__` 为原 RuntimeError |
| `test_exec_spawn_offline_known_seeds` | seed 1000442、1000446 离线生成成功，`cube_2` 带 `include_existing=False` |
| `test_replay_valid_spec_reproduces_layout` | 3 个 seed 导出规格再回放：零 mismatch、全部位姿逐位相同 |
| `test_replay_rejects_peg_in_zone[demo/execution]` | 篡改冻结的杆位姿使杆身穿过圆心 → `EpisodeSpecError` |
| `test_replay_rejects_goal_and_cube_in_zone[×4]` | 篡改两段 goal、两段方块中心进圆 → `EpisodeSpecError` |
| `test_real_reset_exec_spawn_and_peg_geometry`（`gpu`、`slow`） | 真实模拟器 xhard reset seed 1000442、1000446：成功；三物体都不在圆内；head/tail 中心距 0.1；`_xhard_verify_peg_extent` 通过 |

实测判定行（`-s` 输出）：

```
MOVECUBE_CENTER_EXCLUSION=PASS seeds=5000 zone_violations=0 layout_fail=0
MOVECUBE_REJECTION_BUDGET=PASS exhausted=0 peg_redraw_mean=0.0395 local_redraw_max=5
MOVECUBE_EXEC_SPAWN_OFFLINE=PASS seeds=2 ok=2
MOVECUBE_EXEC_SPAWN=PASS seeds=2 ok=2        # 真实模拟器，GPU 1，CUDA_VISIBLE_DEVICES=1 单独跑 -k real_reset
```

`peg_redraw_mean=0.0395` 为每段杆的平均重抽轮数（规划期 P2 离线估计每段约 3.8% 的杆触发，吻合）；`local_redraw_max` 只统计 MoveCube 内部两处循环（杆 + 候选中心），goal 与方块最终位置的禁区拒绝发生在 spawn 函数内部、不单独计数。

新文件离线 17 条与 `test_v4_xhard_movecube.py` 14 条合跑 31 passed、约 16 s，其中 5000 seed 用例约 12 s。最终代码上两个文件连同 gpu 用例一起跑（`CUDA_VISIBLE_DEVICES=1`）：`32 passed in 20.81s`。

### 4.2 与 P2 离线副本对拍（调试证据，不进单测）

用 P2 的 `mc_v5.simulate(seed, bias=0, R=0.05, peg_seg=(−0.15, 0.05))` 与本实现的假场景 `_load_scene` 逐局比对两段的杆根、杆 yaw、goal、方块中心与 yaw、杆重抽次数：seed 2000000～2002999 与 1000442、1000446、5400000、5400500 共 **3004/3004 一致**（误差 < 1e-6）。另：改动前的假场景对 v4-01 的 seed 5400000 规格逐值一致，证明假场景就是真实 `_load_scene` 的取值路径。

### 4.3 改成 V5 语义的既有断言（`test_v4_xhard_movecube.py`）

1. `test_configs_three_tiers_identical_and_xhard_values`：`x["corner_bias"] == 0.5` → `"corner_bias" not in x` 且 `x["center_exclusion"]` 等于 L30 定值；三档 `configs[tier]["corner_bias"] == 0.0` 保留（`config_native` 未动）。
2. `test_decision_visible_part_unchanged_and_guard`：两段 `xhard == {"corner_bias": 0.5}` → `== {"center_exclusion": …}`，并断言两段是各自的副本；「两段可取不同值」由改 `corner_bias` 为 0.25/0.75 改为改 `radius_m` 为 0.04/0.06，守卫仍放行。
3. 删除 `test_corner_bias_validation`（6 个参数化）：被测方法 `_xhard_corner_bias` 已删；新配置的校验在新文件 `test_center_exclusion_decision_and_validation`。

### 4.4 全量轻量测试

`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider`（全部改动完成后的一次）：
`47 failed, 948 passed, 22 skipped, 75 deselected, 2 warnings, 12 errors in 184.56s`。失败 + 错误 59 条，与基线 `wt_baseline_failset.txt`（58 条）相比**只多 1 条**：

- `tests/lightweight/test_sampling_config_split.py::test_snapshot_matches_source`：报 `scripts/configs/newtask-v4/sampling_config.json 与源码提取结果不一致`。原因是 MoveCube 的 xhard decision 由 `corner_bias` 改为 `center_exclusion`，V4 快照已过时——属 S3 追加说明所述「V4 作废的预期失败」，**未改 V4 快照**，交主会话 S4 统一处理。

收尾判据「失败集合 = 基线 ∪ 已注明的 V4 快照校验失败」成立；新增用例全部通过。（本机当时负载约 26，墙钟比基线的 140 s 长。）

## 五、演示（本机调试证据，不设门槛）

命令（GPU 1，tmux 会话 `s3c_movecube_demo`，不带 `--sampling-config`，即代码里的 xhard 默认）：
`CUDA_VISIBLE_DEVICES=1 uv run --no-sync python -m scripts.parity.v4_demo_probe --task MoveCube --seeds 5400000,5400100,…,5400900,5401001,5401002,5401003 --out artifacts/newtask-v5/demo-probe/s3c-movecube`
（v4-01 冻结规格里 MoveCube 的 10 个 seed + 3 个新 seed；产物 h5/视频/summary 在工作树 `artifacts/newtask-v5/demo-probe/s3c-movecube/`，日志 `…/s3c-movecube.log`）。

way 取演示实际使用的 `initializations.1.way_idx`（P2 已核实 gym.make 与 reset 各初始化一次、演示用第二次）；另用真实模拟器对这 13 个 seed 各单独 reset 一次读规格，way 与离线假场景推算一致，三物体离圆心距离也逐一核对（下表后三列取两段中较小者，单位 m）。

| seed | way | 结果 | 失败类别 | 步数 | 墙钟 s | 杆重抽（演示/执行） | 杆最近 | goal 最近 | 方块最近 |
|---|---|---|---|---|---|---|---|---|---|
| 5400000 | peg_push | 成功 | — | 481 | 62 | 0/0 | 0.107 | 0.064 | 0.100 |
| 5400100 | gripper_push | 成功 | — | 261 | 33 | 0/0 | 0.165 | 0.064 | 0.073 |
| 5400200 | peg_push | **失败** | task: PlannerExhausted（screw 三次与 RRTStar 三次均失败） | — | 64 | 0/0 | 0.140 | 0.059 | 0.110 |
| 5400300 | gripper_push | 成功 | — | 281 | 39 | 0/0 | 0.196 | 0.054 | 0.057 |
| 5400400 | peg_push | 成功 | — | 685 | 86 | 0/0 | 0.085 | 0.057 | 0.104 |
| 5400500 | gripper_push | **失败** | task: DatasetGenerationError（跑完 task_list 仍未成功） | — | 40 | 0/0 | 0.200 | 0.058 | 0.054 |
| 5400600 | gripper_push | 成功 | — | 280 | 35 | 0/**1** | 0.158 | 0.072 | 0.090 |
| 5400700 | grasp_putdown | 成功 | — | 429 | 51 | 0/0 | 0.188 | 0.060 | 0.060 |
| 5400800 | grasp_putdown | 成功 | — | 432 | 51 | 0/0 | 0.130 | 0.050 | 0.090 |
| 5400900 | gripper_push | 成功 | — | 263 | 32 | 0/0 | 0.115 | 0.059 | 0.108 |
| 5401001（新） | peg_push | 成功 | — | 510 | 61 | 0/0 | 0.171 | 0.053 | 0.099 |
| 5401002（新） | gripper_push | 成功 | — | 258 | 33 | 0/0 | 0.138 | 0.060 | 0.094 |
| 5401003（新） | grasp_putdown | 成功 | — | 444 | 50 | 0/0 | 0.138 | 0.068 | 0.090 |

判定行：`MOVECUBE_DEMO=REPORT reset_ok=13/13 demo_ok=11/13 by_way=peg_push:3/4,gripper_push:5/6,grasp_putdown:3/3 fails={task:PlannerExhausted:1, task:DatasetGenerationError:1}`（墙钟为本机高负载下的数，仅供参考）。

失败归因（都是任务类，与禁区无关）：

- **5400200（peg_push，PlannerExhausted）**：两段杆都未重抽、候选中心也未被禁区拒绝；P2 的 V5 组同一 seed 同样是 peg_push + PlannerExhausted，且 P2 复跑仍失败——本次是第三次复现，属该布局下 peg_push 的规划问题（P2 已建议在 S3c 盯 peg_push，此处样本仍小，不足以下结论）。P2 对照组（R=0）该 seed 走的是 grasp_putdown，不可比。
- **5400500（gripper_push，推到 goal 旁没到位）**：零重抽，布局与 P2 的 R=0 对照组逐位相同（禁区对它不起作用），P2 两组也都失败——与禁区无关。
- 5400600 的执行段杆被禁区拒绝 1 次（P2 记录它在不设杆规则时执行段杆身离圆心仅 2.1 cm），重抽后杆最近 0.158 m；随机流后移使它的 way 由 P2 时的 peg_push 变为 gripper_push，演示成功。

## 六、与计划不符之处

1. **杆线段端点**：计划 2.9 写「P2 实测 `root − 0.15u … root + 0.05u`，线段端点从实际碰撞几何取」。核实后实际**碰撞**外形是 `[−0.145, +0.045]`（碰撞盒半长是可视盒的 0.9 倍），P2 的 `[−0.15, +0.05]` 其实是**可视**外形。实施取二者并集（即 `[−0.15, +0.05]`），理由见 2.2；差 5 mm，属边界取舍，按口径 14 自决。
2. **`max_trials` 的作用范围**：计划的配置里只有一个 `max_trials: 128`，伪码只对杆写了「上限 128」。实施为只约束新增的杆循环；goal、候选、方块最终沿用原有循环预算（256/128/256），禁区拒绝计入同一预算。P2 探针另给 goal 与方块单开 128 次「禁区拒绝计数」，与此略有不同；两种写法在 5000 局里都零耗尽（执行段 goal 拒绝率约 55%，256 次预算下耗尽概率可忽略）。
3. **演示段方块也传 `include_existing=False`**：计划只点名执行段 `cube_2`。演示段首次建场景时它之前没有方块，结果逐位相同，加上是为了让 xhard 下结构性不存在「actor 方块作障碍」（2.0①）。
4. 计划写「方块候选与最终位置 `|c_cand| < R 或 |c_final| < R → 重抽`」：候选被拒只重抽候选（同一 128 次循环），最终位置被拒只在 `spawn_random_cube` 的循环里重抽最终位置，不回退去重抽候选——与 P2 副本一致。

## 七、待用户决策

无改变设计意图的待决项。以下是给主会话的提示：

- `config_native` 里仍有 `corner_bias: 0.0`（原三档配置，不被任何代码消费）。V0 要求原三档配置零改动，所以没删；若主会话认为「删干净」应包括它，需要同时改 V0 判据与 `test_v4_xhard_movecube.py` 的三档断言。
- `test_sampling_config_split.py::test_snapshot_matches_source` 在 V5 快照重导前会一直失败（V4 快照过时）。

## 八、给合并者的注意事项

- 只动了 `MoveCube.py` 与两个 MoveCube 专属测试文件，没有动任何共享文件。
- 规格形状变化：xhard 规格不再有 `layout.*.corner_bias`，新增 `layout.*.center_exclusion`（dict：配置原样 + `peg_axis_extent_m`）与 `layout.*.center_exclusion_trials`（`peg_trials`、`cube_candidate_center_rejects`）；decision 的 `xhard` 子键由 `corner_bias` 改为 `center_exclusion`。V4 快照 / v4-01 规格不能在 V5 上回放（预期）。
- 新方法签名：`MoveCube._xhard_center_exclusion(layout, key) -> {"rule", "center", "radius", "max_trials", "decision"}`；`MoveCube._xhard_sample_peg_outside_zone(base_y, peg_policy, yaw_policy, zone, extent, seg_label) -> (x_jitter, y_jitter, yaw, trials)`；`MoveCube._xhard_verify_peg_extent(extent)`；模块级 `_peg_axis_extent(length) -> (t_min, t_max)`。
- 离线测试靠顶替 `TableSceneBuilder`、`build_peg`、`actors.build_cube`、两个圆盘 builder 并把 `_xhard_verify_peg_extent` 置空来跑真实 `_load_scene`；若后续有人改这些名字的导入方式，`test_v5_xhard_movecube.py` 的 `fake_scene` 夹具要同步。
