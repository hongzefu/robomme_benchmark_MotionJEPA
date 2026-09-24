# V5 S3g：VideoRepick 的 xhard 改动（2026-09-24）

> 对应计划：`NEWTASK_RELEASE_V5_PLAN.md` 1.1 口径 10、1.4 L47～L51 与 L54、2.15（全部）、3.5 的 P4、第二部分「一」S3g 行；红线 N13/N14/N17。
> 工作树：`/data/hongzefu/robomme_v5_wt/vrepick`（分支 `v5wt-vrepick`，基线 12.120 `328e607`），未 commit。
> 依赖的已有 API：S2a `spawn_random_cube(min_center_dist=...)`、`cube_obb2d_exact`、`_RealSceneGenerationError`；S2b `check_swap_sweep_prefiltered`、`button_base_state`。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 |
|---|---|---|---|
| `src/robomme/robomme_env/VideoRepick.py` | 模块头 import（`from .utils.bin_collision import (...)` 之后） | 追加导入 `ObjectState`、`button_base_state`、`check_swap_sweep_prefiltered`、`cube_actor_pose`、`cube_shape_specs`，以及 `EpisodeSpecError as _EpisodeSpecError`；`from .utils.xhard import` 行加 `cube_obb2d_exact` | 规划期扫掠判据、按钮底座、精确 OBB、N17 |
| 同上 | `_cube_index_of` 之后新增模块级 `_xhard_slot_states`、`_XhardSlotSweepFeasibility`、`_plan_swap_partners_xhard` | 纯函数/类：名义槽位 → 放大形状的方块状态；按无序槽位对缓存的扫掠可行性（bystander = 其余槽位 + 按钮底座）；搭档规划主循环（含回放钩子） | L48/L49/L54，便于离线与单测直接调用 |
| 同上 | `_native_decision` 的 xhard 段末尾 | `decision.xhard.layout.min_center_dist_m`；新增 `decision.xhard.swap_plan = {initiator_rule, partner_rule, nearest_k, sweep_margin_m, button_obstacle}` | 「新规则全挂 decision.xhard」 |
| 同上 | 类属性 `config_xhard` | 新增 `min_center_dist_m: 0.12`、`partner_nearest_k: 3`、`partner_sweep_margin_m: 0.005`、`partner_button_obstacle: True` | L50、L48、L49、L54；decision 从这里取值 |
| 同上 | `_load_scene` 最外层 `except Exception as exc:` | 首行加 `if self.difficulty == "xhard" and isinstance(exc, _EpisodeSpecError): raise` | N17 回放复核失败按规格/代码类上报，不包成可重试的 `SceneGenerationError`（S2a 报告的提示） |
| 同上 | `_load_cubes_xhard`（重写） | ① `spawn_random_cube(..., include_existing=False, min_center_dist=(0.12, placed))`，已放方块用 `cube_obb2d_exact` 同时进 `avoid` 与参考点集；② `objects.swap_initiators_remaining` 改为完整 `randperm(5)`（长度 5），回放时校验是完整排列；③ 追加取值 `objects.swap_partner_u = torch.rand(n_swaps)`（回放校验长度与取值域）；④ 发起者 `seq[k % 6]`；⑤ 调 `_plan_swaps_xhard` | L50、L47 a'、L48 |
| 同上 | 新增方法 `_plan_swaps_xhard` | 从 decision 读 `swap_plan`，槽位取自刚生成方块的精确位姿，按钮底座取 `avoid[0]`（`build_button` 返回的 OBB，中心即随机偏移后的最终中心）× `positions.button.scale`；规划并逐次 `value` 注入 `actions.swap_pairs.<k>`；结果存 `self._xhard_swap_partners`，诊断存 `self._xhard_swap_plan_info`（不进规格） | L48/L49/L54、N17 |
| 同上 | 新增方法 `_xhard_planned_partner` | `step` 取第 k 次规划搭档；缺规划或自换抛 `SpecBindingError` | 运行时绑定 |
| 同上 | `step` 的 `for i in range(len(self.swap_schedule))` 循环内 `if pair_idx2 is None and pair_idx1 is not None:` | 新增 `if getattr(self, "difficulty", None) == "xhard": closest_actor = self._xhard_planned_partner(i, pair_idx1)`，原最近邻代码原样缩进进 `else`；之后的甲通道搭档核验、D5 `_check_swap_sweep_from_actual`、xhard 的 `record` 全部不动 | L49；D5 保留作运行时守卫 |
| `tests/lightweight/test_v5_xhard_videorepick.py`（新） | — | 38 条单测，见 3.3 节 | 验收 |
| `tests/lightweight/test_v4_xhard_videorepick.py` | `test_xhard_新值只挂在xhard子键下`、`test_xhard_交换调度八到十二次首尾相接`、模块 docstring | V4 断言改 V5 语义（见第五节） | V4 作废 |
| `tests/lightweight/test_v5_shared_sampling.py`（S2a 的共享测试文件，范围外，最小改动） | `test_videorepick_xhard_raise_is_real_class` 的假 `_sampling` | layout 补 `"min_center_dist_m": 0.12`（1 行 + 1 行注释） | 新代码在第一次 spawn 前就读这个键 |

没有改：`NATIVE_SAMPLING`、`config_easy/medium/hard`、`_resolve_sampling_config` 的 JSON 全等守卫、`bin_collision.py`、`object_generation.py`、`statechange.py`、录像器、`scripts/` 下任何文件。

## 二、关键设计点

1. **规格路径与形状（给生成报告脚本）**：`actions.swap_pairs.<k>`，k = 0…n_swaps−1，用 `SpecRecorder.value` 在 **reset 时**写入，因此冻结规格里是按事件序号的**字典**：
   `spec["actions"]["swap_pairs"] = {"0": {"initiator": "bin_a", "partner": "bin_b"}, "1": {...}, ...}`（键是十进制字符串，值两个字段都是 `bin_<方块生成序号>`）。
   这与 `scripts/parity/v5_generation.py` 的 `VR_PAIRS_PATHS=("actions.swap_pairs",)` + `indexed_items` + `PAIR_KEYS[0]=("initiator","partner")` 直接对上；运行时 `step` 仍按 V4 原样 `record` 同一路径（值相同）与 `actions.swap_windows.<k>`，所以 `rng_trace` 里也有。
   其他新/变规格字段：`objects.swap_initiators_remaining`（长度 5 的 `range(5)` 排列）、`objects.swap_initiators`（record，长度 6：`[目标]+其余 5 块顺序`）、`objects.swap_partner_u`（长度 n_swaps 的 float 列表，value）。
2. **随机流**（xhard 专属，原三档不经过）：颜色 `rand(3)` → 逐块 `3×rand(1)`/trial（0.12 m 只增加 trial 次数）→ 目标 `randint(0,6,(1,))` → `randperm(5)`（V4 同一次调用，不再截断）→ **追加** `rand(n_swaps)` → 规划（不抽随机数）。单测 `test_VR_RNG_ORDER` 用 torch 间谍锁定这一序列与取值点顺序。
3. **规划规则**（与 P4 原型变体 B 逐位一致，见 3.1）：槽位按 XY 距离稳定排序；最近 `nearest_k=3` 个里至少一个可行 ⇒ 候选池 = 按距离序的前 3 个可行者（可以越过不可行者取到第 4、5 近）；否则回退到全部可行者；`slot = pool[min(floor(u[k]·len), len−1)]`；池空 ⇒ 真 `SceneGenerationError`（`_load_scene` 在 xhard 下原样上抛）。每次名义对换后更新占用关系。
4. **可行性判据**：`check_swap_sweep_prefiltered`（判定与 `check_swap_sweep` 相同，只加认证预筛）；两个移动者与其余 4 个槽位都用 `cube_shape_specs(0.02+0.005)`、中心高 0.02（与 P4 `InflCache` 同口径）；**按钮底座**用 `button_base_state("button_base", 按钮最终中心, scale=1.5)`（真实尺寸，不加余量）作静止 bystander（L54 a）。按无序槽位对缓存。
5. **N17 回放复核**：①最小中心距由 `spawn_random_cube(min_center_dist=...)` 在 `recorder.value` 返回冻结位姿后复核；②`swap_initiators_remaining` 必须是 `range(5)` 完整排列（V4 规格长度 2 ⇒ 报错）；③`swap_partner_u` 长度与 [0,1) 校验；④逐次冻结搭档：发起者必须与规划一致、搭档非自身且其槽位对在规划口径下扫掠可行，否则 `EpisodeSpecError`；占用关系按**冻结**搭档推进。回放与规划不同但仍可行时，`value` 记 mismatch（`decision_key="xhard.swap_plan"`）并用冻结值。
6. **step**：xhard 用 `_xhard_planned_partner`，不再读 native 的 `position_axes`；D5 `_check_swap_sweep_from_actual`（真实形状、实际位姿、不含按钮）照跑。AST 锁测试把循环抽到 `SimpleNamespace` 上执行，所以判档写成 `getattr(self, "difficulty", None)`。

## 三、实测

### 3.1 离线多 seed reset 统计（真实 `_load_cubes_xhard` 代码 + 假 actor，seed 7_000_000～7_002_399，共 2400 局，与 P4 同一批）

脚本：scratchpad `vr_fake.py` / `offline_stats.py`（不入库）。随机流头部复刻 `__init__`（num_repeats、n_swaps）与 `build_button` 的 `rand(2)`。以下均为**规划期离线估计**（N16）。

| 指标 | 按钮不作障碍（对照 = P4 FINAL） | **按钮作障碍（V5 实现，L54 a）** |
|---|---|---|
| 摆放成功 | 100%（2400/2400），最小对距 ≥ 0.1200，中位 0.1274 | 同左 |
| **规划失败率** | **9.04%**（217/2400） | **39.96%（959/2400）** |
| 失败发生在第 k 次 | 0:58 1:38 2:32 3:33 4:35 5:21 | 0:228 1:184 2:143 3:153 4:137 5:114 |
| 6 块全参与（成功局） | 100% | 100% |
| 单段路径均值 | 0.196 m | **0.173 m** |
| 每局最长段 均值 / p95 / 最大 | 0.301 / 0.423 / 0.516 m | **0.231 / 0.320 / 0.461 m** |
| 回退（3 近全不可行）局占比 | 1.01% | 2.01% |
| 目标块被换次数均值 | 3.66 | 3.65（P(≤2)=5.6%） |
| 同一对最多重复 均值 / 最大 | 2.81 / 4 | 3.23 / 4 |
| reset 取值+规划墙钟（假 actor） | 均值 48 ms，p95 89 ms，最大 1.09 s | 均值 53 ms，p95 99 ms，最大 1.10 s |

- **与 P4 原型逐位对照**（按钮关）：2400 局成败 2400/2400 一致，成功的 2183 局搭档序列逐次全部一致——实现与 P4 规划规则等价。
- 按钮关成功、按钮开失败的局 742/2400。
- 敏感性（只作参考，未改实现）：全部不加余量 + 按钮 ⇒ 规划失败 24.21%；方块之间 +5 mm、方块对按钮用真实尺寸 ⇒ 34.62%。按钮约束本身就很贵：0.12 m 间距把方块推到区域边缘，按钮（x≈−0.2，底座半边 0.0375）在区域内，靠近按钮的槽位常常 5 个搭档全被挡。
- 对正式生成的影响：每局 reset 成功率 ≈ 0.60，攒 10 条候选的期望尝试 ≈ 16.7 次；上限 30 次内攒不够 10 条的二项估计 ≈ 0.08%（9.04% 口径时 ≈ 1e-15）。

### 3.2 本机演示（GPU 1，走 `generate_dataset_newseed._worker` 正式入口；scratchpad `demo_instrumented.py` 只包一层只读仪表记录 D5 与逐控制步位移）

产物：`artifacts/newtask-v5/demo-probe/s3g-videorepick/`（`run.log`、`instrumented_summary.json`、h5、视频）与 `.../s3g-videorepick-rerun4900300/`。

| seed | 来源 | reset | 演示 | n_swaps | 控制步 | 参与块数 | 规划最长/均段 (m) | D5 检查/拒绝 | D5 最小余隙 | 交换窗内逐步最大位移 | 单帧跳变(>25 mm) | 墙钟 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4900300 | v4-01 ep3 | ✓ | ✓（重跑，见下） | 12 | 1732 | 6 | 0.380 / 0.233 | 12/0 | 9.1 mm | 11.3 mm | 0 | 182 s |
| 4900100 | P4 压按钮局 | ✓ | ✓ | 11 | 1837 | 6 | 0.223 / 0.159 | 11/0 | 20.6 mm | 7.3 mm（P4 49.9） | 0 | 206 s |
| 4900400 | P4 压按钮局 | ✓ | ✓ | 10 | 1644 | 6 | 0.212 / 0.164 | 10/0 | 54.9 mm | 6.9 mm（P4 64.9） | 0 | 178 s |
| 4900700 | P4 压按钮局 | ✓ | ✓ | 11 | 1729 | 6 | 0.153 / 0.135 | 11/0 | 21.0 mm | 5.7 mm（P4 59.0） | 0 | 184 s |
| 4900500 | P4 压按钮局 | ✗ 规划失败（第 2 次交换 bin_0 无可行搭档，真 `SceneGenerationError`） | — | 8 | — | — | — | — | — | — | — | 2 s |
| 4900200 | v4-01 | ✓ | ✓ | 10 | 1533 | 6 | 0.215 / 0.178 | 10/0 | 38.2 mm | 6.9 mm | 0 | 160 s |
| 7000000 | 新 seed | ✓ | ✓ | 12 | 1630 | 6 | 0.243 / 0.181 | 12/0 | 23.2 mm | 7.6 mm | 0 | 168 s |
| 7000001 | 新 seed | ✓ | ✓ | 11 | 2112 | 6 | 0.366 / 0.256 | 11/0 | 12.8 mm | 10.8 mm | 0 | 220 s |

- 汇总：reset 成功 7/8（唯一失败是按钮约束导致的规划失败，与离线一致）；演示成功 7/7；运行时 D5 **77 次检查 0 拒绝**；**单帧跳变 0**（P4 的 4 个跳变局现在最大逐步位移 5.7～7.3 mm，与无按钮干扰的解析平滑曲线一致）；非交换方块逐步位移 0。
- 8 局模拟器里的规划搭档序列与离线假环境 8/8 逐次一致（4900500 两边都失败）。
- 4900300 第一次跑报 `DatasetGenerationError: 缺少原始 HDF5`：演示本身已跑完且判成功（视频已落盘），h5 缺失是我在同一输出目录上先起后杀的第一次探针（误绑 GPU 0）与第二次运行抢同一 h5 路径造成的；换独立目录单独重跑成功（上表数据来自重跑，规划与第一次完全相同）。不是代码问题。

### 3.3 测试

- 新测试 `tests/lightweight/test_v5_xhard_videorepick.py`：**38 passed**（约 5 s）。判据行：`VR_MIN_CENTER_DIST=PASS min_d>=0.120`（10 seed）；`VR_ALL_CUBES_SWAP=PASS min_participants=6`（10 seed，含发起者 `seq[k%6]`、`swap_initiators_remaining` 长度 5、规格 `actions.swap_pairs` 形状）；`VR_PLAN_D5=PASS rejected=0`（4 seed 的全部规划槽位对用**原** `check_swap_sweep`（不预筛）+ 按钮底座复核）；按钮确实生效（4900100 按钮关时的压按钮对在按钮开时不再出现）；无可行搭档抛真 `SceneGenerationError`；`VR_RNG_ORDER=PASS`；N17 回放 5 条（原样零 mismatch、篡改不可行搭档/发起者/自换/V4 形态发起者/违反 0.12 m 均报 `EpisodeSpecError`）；`_load_scene` 放行 xhard 的 `EpisodeSpecError`；`step` 循环 AST 抽出实跑（xhard 用规划搭档且 D5、record 照跑；原三档仍最近邻；缺规划报错）。
- `test_episode_action_sampling.py::test_real_swap_resolution_matches_baseline_and_preserves_ties`：通过（原三档语义与历史基线相同）。
- 全量：`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider` ⇒ `47 failed, 975 passed, 22 skipped, 74 deselected, 12 errors in 178.01s`。失败集合 59 条 = 基线 58 条 **∪ `tests/lightweight/test_sampling_config_split.py::test_snapshot_matches_source`**；后者报「`scripts/configs/newtask-v4/sampling_config.json` 与源码提取结果不一致」，原因是 VideoRepick 的 `decision.xhard` 新增了 `layout.min_center_dist_m` 与 `swap_plan`——属于规则里说明的 V4 快照校验预期失败，未改 V4 快照，留给主会话 S4 统一处理。
- V0 静态检查：`git diff` 中 `config_easy|config_medium|config_hard|NATIVE_SAMPLING` 的增删行 **0**。

## 四、原三档静态自查（逐处说明为何不执行/不改随机流）

| diff 位置 | 原三档是否执行 | 说明 |
|---|---|---|
| 新 import、模块级新函数/类 | 只在 import 时定义 | 不抽随机数、无副作用 |
| `config_xhard` 新键、`_native_decision` 的 xhard 段 | `decision.xhard` 生成，但原三档不读 | 去掉 xhard 子键后 decision 与改动前逐字相同（`test_去掉xhard后decision与改动前相同` 通过）；`parameters.configs` 里 easy/medium/hard 条目不变 |
| `_load_scene` 的 `except Exception` 首行 | 只在已发生异常时执行一次 `self.difficulty == "xhard"` 判断，为假 | 随后原样 `raise _scene_gen_error(...)`（原三档仍是 TypeError），行为逐字不变 |
| `_load_cubes_xhard` / `_plan_swaps_xhard` / `_xhard_planned_partner` | 不执行 | 只在 `_load_scene` 的 `if self.difficulty == "xhard"` 分支与 `step` 的 xhard 分支调用 |
| `step` 的 `if getattr(self, "difficulty", None) == "xhard"` | 执行一次判断，为假 | 走 `else`，是原最近邻代码逐行原样（仅缩进），`test_real_swap_resolution_matches_baseline_and_preserves_ties` 对历史基线通过；不抽随机数 |

## 五、改动的既有断言（V4 → V5 语义）

1. `test_v4_xhard_videorepick.py::test_xhard_新值只挂在xhard子键下`：layout 期望值加 `"min_center_dist_m": 0.12`，并新增对 `decision.xhard.swap_plan` 的整体断言。
2. `test_v4_xhard_videorepick.py::test_xhard_交换调度八到十二次首尾相接`：测试自造发起者由 `k % 3`（B12「发起者 3 个」）改为 `k % 6`，断言 6 个发起者都出现（L47 a'）。
3. `test_v5_shared_sampling.py::test_videorepick_xhard_raise_is_real_class`（S2a 文件）：假 `_sampling` 的 layout 补 `min_center_dist_m`，断言不变。

## 六、与计划不符之处

1. 计划 2.15 写 `spawn_random_cube(..., extra_reject=…)`，S2a 实际提供的参数名是 `min_center_dist=(d, points)`，按 S2a 实现。
2. 计划写扫掠过滤用 `check_swap_sweep`，实现用 S2b 的 `check_swap_sweep_prefiltered`（判定相同、只加预筛；单测里用原 `check_swap_sweep` 独立复核规划结果）。
3. 规划参数（`nearest_k=3`、`sweep_margin_m=0.005`、`button_obstacle=True`）除进 decision 外也在 `config_xhard` 里留一份（沿用 V4「decision 从 config_xhard 取值」的模式）；decision 键名 `swap_plan` 及其子键名是实施方自定。
4. 按钮底座用真实尺寸（`build_button` 的 `base_half × scale`，不含按帽），方块两侧用 +5 mm 放大形状；按钮不另加余量（计划只说「按钮底座 OBB 作为静止 bystander」）。
5. 规划失败率计划预期「从 9.04% 上升」，实测升到 **39.96%**（见待决项）。

## 七、待用户决策

1. **L54 实施后规划失败率 9.04% → 39.96%**（离线 2400 局；本机演示 8 局中 1 局 reset 规划失败，与离线一致）。VideoRepick 每局 reset 成功率约 0.60，攒 10 条候选期望约 17 次尝试，30 次上限内攒不够的概率约 0.08%，生成仍可行；但拒绝率是原估计的 4 倍多，且被拒的都是「有方块靠近按钮、被按钮完全围住」的布局，会让通过的布局系统性地偏向方块远离按钮。是否接受？可选的调整（都会改变设计意图，需用户定）：(a) 接受现状；(b) 按钮底座检查不配 5 mm 余量（方块对按钮用真实尺寸，离线 34.62%）；(c) 在摆放时就让方块离按钮更远（例如按钮附近的禁区加大，会动 L51「区域与按钮不动」）；(d) 其他。本实现取 (a) 的字面口径。
2. 附带观察（非待决，仅供参考）：按钮开后每局最长段均值 0.231 m、最大 0.461 m（P4 无按钮 0.301/0.516），速度问题比 P4 预估轻；演示逐步最大位移 ≤ 11.3 mm，没有单帧跳变。

## 八、给合并者的注意事项

- 新函数/方法签名：
  - `_xhard_slot_states(slots: list[(x, y, yaw)], cube_half: float, margin: float) -> list[ObjectState]`
  - `_XhardSlotSweepFeasibility(slot_states, statics=()).feasible(slot_a, slot_b) -> bool`（`.cache`/`.evidence` 按无序对）
  - `_plan_swap_partners_xhard(slot_xy, seq, u, feasible, nearest_k, resolve=None) -> list[dict]`（每项 `initiator/partner/slot_a/slot_b/dist_m/pool/fallback`；池空抛真 `SceneGenerationError`；`resolve(k, a, b) -> 实际搭档号`，违规抛 `EpisodeSpecError`）
  - `VideoRepick._plan_swaps_xhard(self, initiator_seq, partner_u, button_obb)`；`VideoRepick._xhard_planned_partner(self, sweep_index, initiator)`
  - 实例属性：`_xhard_swap_partners`（第 k 次搭档方块号）、`_xhard_swap_plan_info`（诊断：`slots`、`plan`、`checked_slot_pairs`、`infeasible_slot_pairs`，不进规格）。
- `_load_cubes_xhard` 依赖 `avoid[0]` 是 `build_button` 返回的按钮 OBB（`_load_scene` 现状如此）；若以后 `_load_scene` 调整 avoid 的构造顺序，需同步。
- 生成报告脚本：`vr_min_participants` 从规格 `actions.swap_pairs` 直接可读（形状见 2.1），不再需要 rng_trace 兜底。
- `test_sampling_config_split.py::test_snapshot_matches_source` 在本分支失败属预期（V4 快照），S4 统一处理。
