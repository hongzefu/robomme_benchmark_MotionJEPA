# V5 S3h：VideoUnmaskSwap / ButtonUnmaskSwap xhard——10 个干扰容器、外环随内环同步交换、两对联合碰撞证明

日期：2026-09-24；worktree：`/data/hongzefu/robomme_v5_wt/swap`（分支 `v5wt-swap`，基于 12.120，未 commit）。
依据：`NEWTASK_RELEASE_V5_PLAN.md` 1.1 口径 4～6、1.4 L13～L23、2.2、2.5（伪码与陷阱）、2.6、2.7、3.5 P5、红线 N13/N14/N17/N18、第二部分「一」S3h 行；
S2b（`check_multi_swap_sweep` / `check_swap_sweep_prefiltered`）、S2c（统一采样器、停放 helper）两份报告的 API。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 |
|---|---|---|---|
| `src/robomme/robomme_env/utils/unmask_swap_xhard.py` | 模块 docstring、导入 | 说明 V5 一节；新增导入 `bin_collision` 的联合判据与若干私有件、`unmask_distractor_sampler` 的采样器 | 接入 S2b/S2c |
| 同上 | 文件末尾新节「V5：统一采样器 10 个干扰容器 + 外环随内环同步交换」 | 新增：配置 `v5_distractor_cfg` / `v5_distractor_swap_cfg` / `parse_distractor_swap_cfg`；内环预演 `InnerWindow`、`predict_inner_windows(_from_states)`；L20 `prejudge_inner_windows`；几何件 `padded_bin_shapes`、`distractor_bin_state`、`lane_center_paths`、`bins_visible_many`；H1 守卫 `InnerSweepGuard`；外环规划 `nearest_distractor`、`evaluate_outer_candidate`、`plan_distractor_swaps`、`verify_distractor_swap_plan`；reset 入口 `plan_swap_distractors`（纯几何）/ `spawn_swap_distractors_v5`（建 actor）；运行时 `joint_sweep_from_actual`、`run_outer_swaps` | 计划 2.5 伪码 |
| 同上 | V4 的 `XHARD_DISTRACTOR`、`sample_distractors`、`build_distractors`、`visible_on_camera`、`predict_swap_sweeps` | **未改**，环境不再调用（旧单测仍锁着它们的语义） | 不扩大改动面 |
| `src/robomme/robomme_env/VideoUnmaskSwap.py` | 导入 | 去掉 V4 采样器导入，改导入 V5 入口与停放 helper | — |
| 同上 | `_native_decision` 的 `xhard` 子键 | `distractor` 改为统一预设（10 个、`[0.2675,0.45]`、cube `[5,5]`）；新增 `distractor_swap` | L13/L16 b/L17～L23 |
| 同上 | `__init__` 的 `if self._is_xhard:` 块 | 初始化 `distractor_swap_pairs` / `distractor_cube_bin_pairs` / `predicted_inner_swap_pairs` | 运行时读取 |
| 同上 | `_spawn_xhard_distractors` | 函数体改为调用 `spawn_swap_distractors_v5(generator=distractor_generator(self.seed), ...)`，把结果挂到实例上；仍是 `_load_scene` 最后一个 `if` 块里的调用 | 2.6 |
| 同上 | `_check_swap_sweep_from_actual` 开头 | xhard 分支改调新方法 `_check_joint_sweep_xhard`（两对联合、实际位姿、预筛；内环搭档与预演不一致时 `logger.warning` + `record`）；原三档（甲通道）路径逐字未动 | L22 a、L23 |
| 同上 | `step` 顶部揭示段 | xhard：内环容器 `reveal_actors_parked(group="bin")` + 干扰容器 `reveal_distractor_bins_parked`；原三档的 `lift_and_drop_objects_back_to_original` 循环原样挪进 `else` | L14（主会话定内环也停独立点） |
| 同上 | `step` 末尾 cube 段（AST 锁定循环之后） | xhard：`run_outer_swaps` + 内环/外环 cube 各自 `park_cubes_onto_bins`；原三档 `lift_and_drop_objectA_onto_objectB` 循环原样挪进 `else` | 口径 4、L14 |
| `src/robomme/robomme_env/ButtonUnmaskSwap.py` | 同上各处 | 与 VUS 同构；`_spawn_xhard_distractors(button_obbs)` 把按钮 OBB 预制三元组精确进障碍、按钮中心进 0.122 约束；`_check_swap_sweep_from_actual` 内联 xhard 联合分支 | 2.7 |
| 同上 | `_load_scene` 内环 `spawn_random_bin` 的 `except RuntimeError` | xhard 下改 `raise _RealSceneGenerationError(...) from e`，原三档仍 `break` | L15 |
| `tests/lightweight/test_v5_xhard_unmaskswap.py`（新） | 34 条 | 见第四节 | 任务第 8 条 |
| `tests/lightweight/test_v4_xhard_unmaskswap.py` | `test_decision去掉xhard后与原值相同`、`test_守卫放行xhard收窄_...` | V4 断言改为 V5 语义：distractor 期望值改为统一预设并断言 `distractor_swap`；收窄的键从 `with_cube_range` 改为 `cube_count_range` | V4 作废 |
| `tests/lightweight/test_v4_xhard_unmask_distractor_reveal.py`（**共享文件**） | `test_四环境揭示只在xhard且原揭示循环不变` | 揭示调用同时认 `reveal_distractor_bins` 与 `reveal_distractor_bins_parked`（一行） | Swap 两环境改用停放版；S3b 若改同一行需合并 |

没有改 `bin_collision.py`、`statechange.py`、`object_generation.py`、`unmask_distractor_sampler.py`、`unmask_distractors.py`、录像器、`scripts/` 任何文件。

## 二、关键设计点

1. **reset 流程**（`plan_swap_distractors`，仍由 `_spawn_xhard_distractors` 调用、仍在 `_load_scene` 最后一个 `if self._is_xhard:` 块里）：
   内环预演（与 V4 `predict_swap_sweeps` 同语义，另返回每窗起点全部内环状态）→ `record actions.predicted_inner_swap_pairs` →
   **L20 预判**（`check_swap_sweep_prefiltered` 逐窗，拒绝即 `record layout.inner_sweep_prejudge` 并抛真 `SceneGenerationError`）→
   S2c 的 `resample_distractor_layout` 整段重抽（放置时 `extra_reject` = H1 守卫；`accept` 里先 `perm = randperm(10)` 再逐窗规划）→
   被接受后 `value objects.distractors.swap_order` → `record actions.distractor_swap_pairs` / `actions.distractor_swap_fallback` → 建 actor。
   全部抽样只走 `distractor_generator(seed)`，主流一次不多抽。
2. **外环规划**（`plan_distractor_swaps`）：第 k 窗依次试 `o = perm[(k+j) % 10]`，`p` = 干扰容器中 XY 最近邻（float32、严格 <、平局取序号小，与内环 `step` 扫描同语义），
   按便宜到贵查四条：`vis`（两条中心路径 401 个采样点全部精确 8 角点可见）→ `btn`（仅 BUS，两路径离每个按钮中心 ≥ 0.122）→
   `inner_clear`（两路径离本窗内环两条交换路径同一时刻位置、其余内环静止位置的中心距 − 2×外接圆半径 0.0424 ≥ 0.04，与 P5 原型同式）→
   `exact`（`check_multi_swap_sweep([内环对 k, (o,p)], 其余全部静止)`）。接受后名义对换 o、p 位姿。
3. **5 mm 余量**（2.5「关键设计点」）：外环在 reset 规划、运行时照规划执行不再解析搭档，所以近平局翻转不存在；剩下的风险是运行时复核读到的位姿与名义差约 0.7 mm。
   实现为：**只在 reset 规划里**把每个干扰容器的 6 个碰撞盒各向外扩 `plan_pad_m = 0.005`（H1 候选与联合证明都用），内环容器仍用真实盒体；
   运行时复核一律用真实碰撞盒。于是被接受的方案里内外环之间名义间隙 ≥ 5 mm、外环两两 ≥ 10 mm。
4. **H1 守卫**（`InnerSweepGuard`）：候选（静止）× 每窗两个交换者，逐项复刻 `check_multi_swap_sweep` 的「静止物 × 交换者」三层（包围球粗筛 → 认证预筛 → `_prove_pair`），
   只是不再每个候选都重证内环对自身（L20 已证过）。为此从 `bin_collision` 导入了 `_swap_movers`、`_Static`、`_prove_pair`、`_prefilter_*` 私有件（只读使用，未改）。
   单测随机 70 个候选与 `check_multi_swap_sweep` 判定、证据对象与窗口号逐一一致。
5. **认证预筛覆盖三处**：L20 预判（`check_swap_sweep_prefiltered`）、外环规划（`check_multi_swap_sweep` 默认开）、运行时复核（同上），H1 守卫也带同一预筛。
6. **运行时**（`step`，全部在 AST 锁定的 `for i in range(len(self.swap_schedule))` 循环之外，N14）：内环搭档照旧在锁定循环里运行时解析；锁定循环里调用的
   `_check_swap_sweep_from_actual` 在 xhard 改为两对联合复核（内环实际对 + 本窗规划的外环对，其余全部静止）。锁定循环之后：内环 `swap_flat_two_lane` 循环不动 →
   `run_outer_swaps`（第 k 个外环对用内环第 k 窗同一 `[start,end]`，lane 0.07、smoothstep、其余干扰容器钉住，窗口首步 `record actions.distractor_swap_windows.<k>`）→
   内环 cube `park_cubes_onto_bins(group="hidden_cube")`、外环 cube `park_cubes_onto_bins(group="distractor_cube")`。`swap_schedule` 与所有等待点不变 ⇒ **不增加控制步**。
7. **L14 独立停放**：xhard 下内环 4 个容器（`group="bin"`）、10 个干扰容器、3 个内环 cube、5 个外环 cube 各停各的点（S2c 的 helper，时间线与 statechange 逐步相同）。
8. **N17 / N18**：`resample_distractor_layout` 只在被接受那次走 `value`；回放时整条流程重跑，冻结布局经 `commit` 按同一规则（含 H1 回调，用同一份内环预演）复核；
   冻结布局与重抽不同 ⇒ 抛错；冻结的 `swap_order` 与重抽不同 ⇒ 用冻结排列重新规划并复核可行性，不可行抛真 `SceneGenerationError`（交换对以冻结排列为准，差异记进 mismatch）。
9. **配置可关**：`distractor_swap.enabled = False` 时不抽 `perm`、不做外环交换（其余规则照旧）；默认开。

## 三、原三档静态自查（逐处说明为何不执行 / 不改随机流）

| diff 位置 | 原三档为何不受影响 |
|---|---|
| `_native_decision` 的 `xhard` 子键 | `_strip_xhard` 后与原值逐键相同；原三档只读顶层键（守卫单测与 V0 为证） |
| `__init__` 新增三行属性 | 在 `if self._is_xhard:` 块内 |
| `_spawn_xhard_distractors` | 只在 `_load_scene` 末尾的 `if self._is_xhard:` 里调用 |
| `_check_swap_sweep_from_actual` / `_check_joint_sweep_xhard` | 新分支以 `getattr(self, "_is_xhard", False)` 为条件；VUS 原三档甲通道仍走原函数体逐字未动；BUS 原三档从不调用该函数 |
| BUS `except RuntimeError` | 新增 `if self._is_xhard: raise`，原三档仍执行原 `break`；不抽随机数 |
| `step` 揭示段、cube 段 | 原三档走 `else`，里面是原循环逐字（只有缩进变化，删掉一行尾随空格）；新增的 `if self._is_xhard` 判断不抽随机数、不读写任何状态 |
| `unmask_swap_xhard.py` 新节 | 只被上述 xhard 分支调用 |

V0：`git diff` 中 `config_easy/config_medium/config_hard/NATIVE_SAMPLING` 命中 0 处。

## 四、测试

### 4.1 新单测 `tests/lightweight/test_v5_xhard_unmaskswap.py`（34 条全过，约 32 s）

| 测试 | 内容 |
|---|---|
| `test_decision_xhard为统一预设与外环交换配置块`（×2） | 预设值、配置块各键、BUS 0.122 / VUS None |
| `test_外环交换配置非法即报错`（×8） | lane 0.05、规则名、partner、smooth、预算 0、多余键、负阈值 |
| `test_向量化可见判据与精确判据逐点一致` | 3000 个随机点 |
| `test_H1守卫与联合判据的静止物对判定一致` | 70 个候选，判定与证据一致（拒绝、通过各 ≥ 5） |
| `test_内环预演与V4预演同语义` | 与 `predict_swap_sweeps` 逐段同对同位姿 |
| `test_V4碰撞局4500300在reset预判被拒` | 4500300 内环布局 L20 在第 1 段拒绝 `bin_1`/`bin_2`（contact），`plan_swap_distractors` 抛真 `SceneGenerationError` |
| `test_正常布局通过内环预判`（×4） | 4 个真实内环布局 |
| `test_每窗恰好一次外环交换且规划可行`（×4） | 窗口数 = n_swaps；外环对只在 0..9 且 o≠p；`verify_distractor_swap_plan` 独立复核（最近邻、可见、离内环、按钮、联合证明）为空；放置规则（含 H1）复核为空；发起者 = `perm[(k+fallback)%10]`；名字无重复且与内环名不相交；5 个 cube |
| `test_外环路径约束真的在拒绝候选` | 阈值调到 10 m：16 次整段重抽后抛真异常，`attempts=16`，失败原因 16 条，**不留任何 `bins`/`swap_order` value** |
| `test_规划只用独立流且同seed可复现` | 主流状态不变；同 seed 逐值相同 |
| `test_只在被接受那次value_回放逐值复现` | `swap_order`、`bins.0` 各 value 一次；导出规格回放后布局与交换对相同、mismatch 0 |
| `test_回放篡改冻结布局被拒` / `test_回放篡改发起者排列按冻结值重规划并复核` | N17 |
| `test_运行时外环与内环同窗口且每窗恰好一次` | 假环境逐步跑 `run_outer_swaps`：每窗对象、窗口、lane、钉住个数正确；运行时留痕 3 窗 |
| `test_运行时联合复核带外环对并记录搭档不一致` | 联合判据收到两对、10 个旁观者；不一致标志 |
| `test_外环循环在锁定循环之外且只在xhard`（×2） | AST：锁定循环里没有外环 / 停放；外环只在 `if self._is_xhard` 且 `else` 仍是原函数 |
| `test_spawn只用独立流且调用V5入口`（×2）、`test_bus内环截断在xhard抛真异常` | AST |

### 4.2 改为 V5 语义的既有断言

- `test_v4_xhard_unmaskswap.py::test_decision去掉xhard后与原值相同`：期望的 `xhard.distractor` 从 V4 的 `{count 3, with_cube_range, ring_half_extent, min_gap, colors}` 改为统一预设，并加 `distractor_swap` 断言。
- `test_v4_xhard_unmaskswap.py::test_守卫放行xhard收窄_...`：收窄示例的键 `with_cube_range` → `cube_count_range`。
- `test_v4_xhard_unmask_distractor_reveal.py::test_四环境揭示只在xhard且原揭示循环不变`：揭示调用同时认停放版。
- AST 锁 `test_real_swap_resolution_matches_baseline_and_preserves_ties`、末句约束 `test_干扰容器在load_scene末尾且不用主流`、`test_v4_xhard_swap_hold.py` 全部**原样通过**。

### 4.3 全量轻量测试

`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider`：
`47 failed, 971 passed, 22 skipped, 74 deselected, 12 errors in 203.14s`（与演示探针同时跑）。失败集合 59 条 = 基线 58 条 ∪
`test_sampling_config_split.py::test_snapshot_matches_source`——报错 `scripts/configs/newtask-v4/sampling_config.json 与源码提取结果不一致`，
即 V4 快照与 V5 的 xhard decision 不符，属于规则文件「S3 追加说明」所述 V4 作废的预期失败（**未改 V4 快照**，交主会话 S4 统一处理）。

## 五、离线复算（规划期口径，N16：只是调试参考）

脚本在会话 scratchpad（`offline_v5.py`，用 P5 已核对的内环副本 + 本 worktree 的正式 `plan_swap_distractors`），每环境 300 局：

| 指标 | VUS 余量 5 mm（采用） | VUS 余量 0 | BUS 余量 5 mm（采用） | BUS 余量 0 |
|---|---|---|---|---|
| L20 内环预判拒绝 | 1.33% | 1.33% | 11.0% | 11.0% |
| 首次干扰布局可行（进入外环规划的局） | 99.32% | 99.66% | 95.49% | 98.50% |
| 平均重抽 / 最多尝试 / 16 次耗尽 | 0.0068 / 2 / 0 | 0.0034 / 2 / 0 | 0.045 / 2 / 0 | 0.015 / 2 / 0 |
| 第一候选发起者即可行的窗口 | 54.0% | 63.2% | 41.8% | 48.4% |
| 外环来回撤销率（相邻两窗同一对） | 40.0% | 31.9% | 57.2% | 50.8% |
| reset 规划墙钟 p50 / p95 / max（s） | 0.53 / 2.81 / 4.75 | 0.17 / 1.31 / 2.66 | 0.46 / 2.44 / 3.86 | 0.12 / 1.43 / 2.38 |

余量 0 这一列与 P5 离线（VUS 62.6% / BUS 48.3% 第一候选、内环拒绝 0.8% / 9.8%）吻合，说明正式实现与原型同一口径。

## 六、演示（本机，只作调试参考）

探针脚本 `sim_probe.py`（scratchpad）只加计时与观测包装、走 `generate_dataset_newseed._worker`；日志 `artifacts/newtask-v5/demo-probe/s3h/demo_{vus,bus}.log`，h5 与视频在同目录下按环境分。
外环终点误差 = 每窗结束那一步全部干扰容器 XY 与名义规划的最大偏差；cube 跟随误差 = last_end+1 步 cube 与所在容器 XY 最大偏差；可见性每个交换窗口步用精确 8 角点判全部干扰容器。

| 环境 | seed | 来源 | n_swaps | 演示 | BinCollisionError | 外环终点误差 mm | 外环 cube 跟随 mm | 内环 cube 跟随 mm | 外环不可见帧 | `_load_scene` 墙钟 s | 每步 p50 / p95 ms | 总墙钟 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VUS | 4500000 | v4-01 | 10 | 成功 | 0 | 0.048 | 0.060 | 0.088 | 0 | 2.26 | 12.4 / 295 | 88.0 |
| VUS | 4500100 | v4-01 | 10 | 成功 | 0 | 0.063 | 0.083 | 0.062 | 0 | 0.49 | 11.9 / 294 | 85.7 |
| VUS | 4500200 | v4-01 | 11 | 成功 | 0 | 0.106 | 0.079 | 0.114 | 0 | 0.84 | 11.0 / 294 | 91.8 |
| VUS | 9100205 | 新 | 12 | 成功 | 0 | 0.074 | 0.107 | 0.086 | 0 | 0.28 | 9.6 / 291 | 92.2 |
| VUS | 4500300 | v4-01（V4 碰撞局） | — | reset 被拒（L20，预期） | — | — | — | — | — | 0.085 | — | — |
| BUS | 4700000 | v4-01 | 8 | 成功 | 0 | 0.070 | 0.088 | 0.101 | 0 | 0.81 | 14.4 / 294 | 88.5 |
| BUS | 4700100 | v4-01 | 6 | 成功 | 0 | 0.046 | 0.066 | 0.083 | 0 | 0.16 | 13.3 / 294 | 77.0 |
| BUS | 4700200 | v4-01 | 7 | 成功 | 0 | 0.078 | 0.106 | 0.090 | 0 | 1.26 | 11.5 / 294 | 83.4 |
| BUS | 9300006 | 新 | 6 | 成功 | 0 | 0.152 | 0.073 | 0.053 | 0 | 0.18 | 10.3 / 291 | 80.0 |

合计 **8/8 演示成功**，BinCollisionError 0，运行时联合复核全部通过、内环搭档与 reset 预演 0 处不一致；4500300 在 reset 被拒：
`xhard 内环对内环扫掠在 reset 预判被拒（L20）：碰撞排除[contact] inner_prejudge#1 对象 bin_2(形状1) 与 bin_1(形状1) g=-0.00123`（V4 实跑同段同对 g=−0.00207，差别来自 V4 运行时读 99.7% 进度位姿）。

回放（`replay_check.py`）：VUS 9100000、BUS 9300000 导出规格原样回放，交换对相同、mismatch 0；把冻结的 3 号干扰容器挪到 (0.3, 0)，VUS 因与重抽布局不一致被拒、BUS 因违反间距被拒（均为 `SceneGenerationError`）。

## 七、每步耗时（任务第 6 条）

- **停放点改动后，揭示段 `[0,64)` 的叠放卡顿消失**：空跑（保持关节角，不走规划器）VUS 9100000 揭示段 p95 从 P5 的 316.8 ms 降到 36.8 ms，BUS 9300000 为 41.2 ms。
- **但 P5 看到的 p95 约 290 ms 仍在，根因已定位，与交换、停放、外环无关**：慢步是**每 15～20 步一次、约 300 ms（偶尔拆成两步各约 150 ms）的周期性卡顿**，出现在整局所有阶段，与窗口边界无对应。对照：
  - 同一 VUS 用原三档 `hard`（本次改动完全不涉及的代码路径）空跑：p50 9.9 ms、p95 165 ms，同样的周期性 ~300 ms 慢步；
  - 与任务无关的 PickXtimes `easy`、换到另一张 GPU：同样的周期性 ~300 ms；
  - VUS `xhard` 改用 `obs_mode="state"`（不渲染传感器）：p50 2.4 ms、p95 **2.9 ms**、0 个慢步；`obs_mode="rgb"` 仍有；
  - 挂 `gc.callbacks` 统计：300 步里只有 4 次 > 50 ms 的回收，排除 Python 垃圾回收。
  ⇒ 卡顿来自每步的**传感器渲染管线**（相机图像读回），是本机渲染环境的共性，不是 V5 引入，也不是 V4 的叠放造成。约 7% 的步落在卡顿上，恰好把 p95 推到 ~290 ms；p50 只有 10～14 ms。
  它影响生成墙钟（每局约多 20 s），不影响结果；是否值得追查属于渲染层议题，超出本任务范围。

## 八、规格里新增 / 变化的字段（给 `scripts/parity/v5_generation.py` 对齐常量用）

| 路径 | 方式 | 形状 | 说明 |
|---|---|---|---|
| `objects.distractors.bins.<i>` | value | `[x, y, yaw_deg]`，i=0..9 | 统一 schema（S2c）；V4 的 `layout.distractors.<i>` 不再使用 |
| `objects.distractors.cube_count` / `cube_bins` / `color_order` | value | int / `list[int]` 长 5 / `list[int]` 长 3 | 同上 |
| `objects.distractors.requested` / `placed` / `trials` / `cube_colors` / `cube_names` | record | int / int / `list[int]` / `list[str]` / `list[str]` | 同上 |
| `objects.distractors.swap_order` | value | `list[int]`，0..9 的排列 | 外环发起者排列（L17），decision_key `xhard.distractor_swap.initiator_rule` |
| `actions.distractor_swap_pairs` | record | `list[[o, p]]`，长度 = `objects.n_swaps` | 第 k 窗外环对，o、p 为 `distractor_bin_<i>` 的序号（**不是**内环 `bin_<i>`）；`OUTER_PAIRS_PATHS` 现值已能认 |
| `actions.distractor_swap_fallback` | record | `list[int]`，长度 = n_swaps | 第 k 窗发起者在排列里顺延的位数（0 = 第一候选） |
| `actions.predicted_inner_swap_pairs` | record | `list[[a, b]]`，长度 = n_swaps | reset 预演的内环对（`bin_<i>` 序号） |
| `layout.distractor_layout_attempts` / `layout.distractor_layout_failures` | record | int / `list[str]`（如 `"window_3"`、`"placement"`） | 整段重抽留痕（N18） |
| `layout.inner_sweep_prejudge` | record（仅 L20 拒绝时） | `{"window": k, "rejection": {...}}` | 只出现在被拒的抽签草稿 |
| `actions.distractor_swap_windows.<k>` | record（运行时，只在 rollout 的 rng_trace 里） | `{"initiator", "partner", "start_step", "end_step"}` | 外环第 k 窗真正开始执行；`OUTER_TRACE_PREFIXES` 第一项已对上 |
| `actions.inner_swap_mismatch.<k>` | record（运行时，仅不一致时） | `{"runtime": [a,b], "predicted": [a,b]}` | L22 a 不一致日志 |
| `_runtime_checks[*]`（`kind == "swap_sweep"`） | 运行时 | 另加 `inner_pair`、`outer_pair`、`predicted_inner_pair`、`inner_partner_mismatch` | `_worker` 返回的运行时检查 |

decision 侧：`decision.xhard.distractor` 键集变为统一 7 键（`count, ring_max_abs_xy, cube_count_range, color_pool, color_rule, min_gap_factor, max_trials`），
新增 `decision.xhard.distractor_swap`（10 键：`enabled, initiator_rule, fallback, partner{5}, lane_offset, smooth, path_constraints{3}, path_samples, plan_pad_m, layout_max_attempts`）。

## 九、与计划不符之处

1. **5 mm 余量的落法**：计划只说「借用 VideoRepick 的 5 mm 余量」。实现为 reset 规划里每个干扰容器碰撞盒外扩 5 mm（内环不扩）。代价见第五节：第一候选可行窗口 VUS 63%→54%、BUS 48%→42%，首次布局可行 99.7%→99.3% / 98.5%→95.5%，16 次耗尽仍为 0；reset 规划 p95 1.3 s→2.8 s。
2. **配置块多三个显式键**：`path_samples`（401）、`plan_pad_m`（0.005）；VUS 的 `min_button_center_dist_m` 为 `None`（没有按钮）。
3. **H1 守卫导入了 `bin_collision` 的私有件**（`_swap_movers`、`_Static`、`_prove_pair`、`_prefilter_*`），为的是不在每个候选上重证内环对自身；判定与公开函数一致（单测锁定）。`bin_collision.py` 本身未改。
4. **来回撤销率高于计划估计**：计划 2.5 陷阱 4 写外环 25～32%，实测（300 局）VUS 40%、BUS 57%（余量 0 时 32% / 51%）。这是最近邻规则的镜像，属于已知性质，未做处理。
5. **每步 p95 ~290 ms 不是叠放造成**：P5 的疑点已定位为渲染管线的周期性卡顿（第七节）；停放点只消除了揭示段的叠放卡顿。
6. V4 的 Swap 干扰采样函数保留为死代码（S2c 允许保留）。
7. 新增了规格记录 `actions.predicted_inner_swap_pairs` 与运行时 `actions.distractor_swap_windows.<k>` / `actions.inner_swap_mismatch.<k>`（计划未列，便于生成报告与追查）。

## 十、待用户决策

1. **VUS 内环 `except RuntimeError: break` 静默截断是否也在 xhard 改抛异常？** L15 只点名 BUS；VUS `_load_scene` 里同样的写法未改（按计划字面）。若截断发生，内环少于 4 个容器，交换发起者与抓取都会变。建议与 BUS 同样处理（一行改动），待用户定。
2. **5 mm 余量是否保留**（见九.1）：保留更稳（运行时复核零拒绝的把握更大），代价是更多回退与略长的 reset；去掉则回到 P5 口径。当前实现保留。

## 十一、给合并者的注意事项

- 共享测试文件 `test_v4_xhard_unmask_distractor_reveal.py` 只改了一行（揭示调用同时认停放版）；S3b（VU/BU）若也改为停放版，同一行可能冲突，内容等价。
- 新 API（`robomme.robomme_env.utils.unmask_swap_xhard`）：
  - `v5_distractor_cfg(task) -> dict`、`v5_distractor_swap_cfg(task) -> dict`、`parse_distractor_swap_cfg(cfg) -> DistractorSwapConfig`；
  - `predict_inner_windows(env, partner_axes) -> list[InnerWindow]`、`predict_inner_windows_from_states(states, positions, initiators, axes)`；
  - `prejudge_inner_windows(windows, *, prefilter=True, stats=None) -> (k, CollisionRejection) | None`；
  - `plan_distractor_swaps(layout, perm, windows, *, cfg, cube_half_size, buttons_xy=(), stats=None) -> OuterSwapPlan`、`verify_distractor_swap_plan(...) -> list[str]`；
  - `plan_swap_distractors(*, windows, obstacles, buttons_xy, generator, recorder, distractor_cfg, swap_cfg, cube_half_size) -> (layout, pairs, timing, stats)`（纯几何，离线可调）；
  - `spawn_swap_distractors_v5(env, *, generator, partner_axes, button_obbs=(), hidden_half_size) -> SwapDistractorResult`；
  - `joint_sweep_from_actual(env, sweep_index, initiator, partner) -> (gap, rejection, info)`、`run_outer_swaps(env, timestep)`。
- 环境实例属性（xhard）：`distractor_bins`、`distractor_cubes`、`distractor_cube_bin_pairs`、`distractor_layout`、`distractor_swap_pairs`、`predicted_inner_swap_pairs`、`_distractor_plan_timing`。
