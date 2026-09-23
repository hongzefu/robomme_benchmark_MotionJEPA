# V4 步 3b：VideoRepick 的 xhard（clutter 6 块 + swap [8,12] + pick [4,6] + D5）

> 红线 N1 的逐步报告。起点 `12.66`（`00e2ef4`），隔离 worktree，GPU 0，本机 sm_89（结果只作调试，口径 10）。
> 录像器未改（`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` 通过）。
> 依据：计划 2.13、2.2②③④、2.21 VideoRepick 简图；决策 A3 / A7 / B12 / C2 / D5 / G2（N=6）/ H2 / H3。

## 一、改动清单

| 文件／锚点 | 改什么 | 为什么 | 怎么验 |
|---|---|---|---|
| `VideoRepick.py::VideoRepick.config_xhard` | 覆盖旧值 `{cube 3, swap [4,5]}` 为 `{cube 6, swap_min 8, swap_max 12, num_repeats_low 4, num_repeats_high_exclusive 7, layout_mode "clutter", region_center [-0.1,0], region_half_size [0.2,0.25]}` | A7 旧 xhard 作废；A3 swap [8,12]；G2 用户定 N=6；pick times [4,6] 写成半开 [4,7)；整片区域取计划 2.13 的中心/半边 | 单测 `test_xhard_新值只挂在xhard子键下` |
| `VideoRepick.py::_native_decision` | 在原返回之上追加：`num_repeats_range.xhard = {low 4, high_exclusive 7}`；顶层 `xhard = {layout:{mode, cube_count, region_center, region_half_size}, block_color:{policy, sampler, rgb_low, rgb_high}}`；`swap.xhard` 由原有的 `cls.configs` 推导自动变成 [8,12] | xhard 新 decision 键全部挂在名为 `xhard` 的子键下，守卫只放行这些键；去掉 xhard 后与改动前逐字相同 | `test_去掉xhard后decision与改动前相同`、`test_守卫放行xhard收窄且拒绝改原三档` |
| `VideoRepick.py::XHARD_BLOCK_COLOR`（新增模块常量） | C2「同色、色值任意」：RGB 三通道各自在 `[rgb_low, rgb_high]=[0,1]` 上均匀抽，alpha 1 | 口径没细化色域，取最字面实现，可经 `decision.xhard.block_color` 覆盖（见「待用户决策」） | reset 冒烟：33/33 颜色三通道均落在 [0,1] |
| `VideoRepick.py::VideoRepick.__init__` | ① xhard 且传了甲的 `episode_spec` ⇒ `ValueError`；② xhard 的 `num_repeats` 从 `decision.num_repeats_range.xhard` 取（`torch.randint` 同形态），经 `_spec.value("objects.num_repeats", decision_key="num_repeats_range.xhard")`；③ xhard 的 `swap_times` 从 `decision.swap.xhard` 取，经 `_spec.value("objects.n_swaps", decision_key="swap.xhard")` | ① A7＋口径 1：甲规格只有 3 块、颜色按名字存，结构不兼容；② 计划 2.2② 的死键 `num_repeats_range` 在 xhard **接上消费点**（原三档仍读 native，仍是死键）；③ 让 decision 里的 xhard 收窄真生效 | 原三档分支代码一字未动（`elif` 之后原样）；reset 探针 diff=0；xhard reset 冒烟 num_repeats∈{4,5,6}、n_swaps∈{8..12} |
| `VideoRepick.py::_load_scene` | 在 `if self.difficulty == "hard":` 前加 `if self.difficulty == "xhard": self._load_cubes_xhard(avoid)`，原 `if` 变 `elif` | xhard 走独立方法，原三档分支与取值点一行不动（H2/N12）；也避免 `test_episode_action_sampling` 这类按 AST 取 `_load_scene` 赋值表达式的测试串味 | reset 探针 diff=0；`test_real_object_selection_expressions_match_baseline` 仍通过 |
| `VideoRepick.py::_load_cubes_xhard`（新增） | 取值顺序：颜色（`objects.color_rgb`）→ 6 块逐块 `spawn_random_cube`（`recorder=self._spec, spec_path=layout.cubes.<i>.xy_yaw`，区域来自 `decision.xhard.layout`，`include_existing/include_goal/random_yaw` 沿用 `positions.hard_cubes`，`min_gap=self.cube_half_size`，命名 `bin_<i>`）→ `record objects.cube_count.{requested,actual}`，不等抛 `SceneGenerationError` → 目标 `objects.target`（randint）→ 其余 2 个发起者 `objects.swap_initiators_remaining`（randperm[:2]）→ `record objects.swap_initiators` → 第 k 次发起者 `swap_indices[k%3]` → `_refresh_swap_schedule()` | 计划 2.13 / 2.21：放弃三组锚点改整片区域；B12 发起者仍 3 个；2.2④ 请求数 vs 实际数；每个新取值点都经 SpecRecorder | reset 冒烟 33/33：6 块全部落在区域内、3 个发起者互异且首个是目标、调度长度 = n_swaps |
| `VideoRepick.py::_sweep_checks_enabled`（新增） | `return self._episode_spec is not None or self.difficulty == "xhard"` | D5 / H2：检查开关改为「甲通道，或 xhard 的乙通道」 | `test_D5_开关只在甲通道或xhard乙通道打开`（6 种组合） |
| `VideoRepick.py::_before_simulation_step` / `_after_simulation_step` / `_initialize_episode`（初态复核） / `step`（扫掠检查调用点） | 四处 `self._episode_spec is None / is not None` 开关换成 `_sweep_checks_enabled()`；`step` 里搭档身份核验 `_verify_swap_binding` 仍只在甲通道（只有甲规格预写搭档），扫掠检查走新开关；xhard 另把实际搭档与窗口 `record` 到 `actions.swap_pairs.<i>` / `actions.swap_windows.<i>` | D5；计划 2.13 的「注入 actions.swap_pairs[] / swap_windows[]」 | `test_D5_四处检查都改走统一开关`；演示期实测 `runtime_checks` 里 `initial=2`、`swap_sweep=n_swaps`（成功局），拒绝局抛 `BinCollisionError` |
| `VideoRepick.py::_solve_hold_obj_xhard`（新增）＋ `_initialize_episode` 的 `hold_fn` | xhard 的两个静止/交换任务改用本地等待函数：与 `solve_hold_obj(close=False)` 同语义，只把裸 `except:` 收窄为 `except AttributeError`；原三档仍用 `solve_hold_obj` | **计划外发现**（见第四节）：D5 打开后，`BinCollisionError` 被 `solve_hold_obj` 的裸 except 吞掉 ⇒ `elapsed_steps` 不前进 ⇒ 死循环、`_runtime_checks` 无限增长 ⇒ 本机 rc=139 崩溃。共享函数缺陷按 N12 不就地修 | `test_xhard_等待函数不吞碰撞拒绝`、`test_只有xhard换用专用等待函数`；修后同一 seed 961818 在 7.9 s 内以 `BinCollisionError` 干净失败 |
| `tests/lightweight/test_v4_xhard_videorepick.py`（新增） | 18 项纯 CPU 结构测试 | 必做验证 4 | 18 passed |
| `tests/lightweight/test_episode_action_sampling.py::test_real_swap_resolution_matches_baseline_and_preserves_ties` | 对 VideoRepick 给假 env 补 `difficulty="easy"` 与 `_sweep_checks_enabled=lambda: False` | 该测试 exec `step` 里的循环体，新开关要这两个属性；补的是「原三档乙通道关闭态」，语义与改动前相同 | 该文件失败数仍为基线的 20 项，且这 2 条参数化恢复通过 |

**没改**：`utils/object_generation.py`、`utils/bin_collision.py`、`utils/subgoal_planner_func.py::solve_hold_obj`（共享缺陷不就地修）、录像器、链路甲、`scripts/configs/**`、计划文件。
`test_swap_schedule_generic.py::test_xhard_四五次首尾相接每段五十帧` 只验通式、不读 config，现仍通过，没改（VideoUnmaskSwap 组可能同改此处，避免冲突）；8/10/12 次的调度断言放在新测试文件里。

## 二、验证

### 1. 原三档 reset 零差异

```bash
uv run --no-sync python -m scripts.parity.v4_reset_probe probe --tasks VideoRepick --out <scratch>/g7_probe2.json
uv run --no-sync python -m scripts.parity.v4_reset_probe diff artifacts/newtask-v4/probe/base-13e.json <scratch>/g7_probe2.json
# RESET_REGRESSION=FAIL compared=9 diff=0 missing=135   ← missing 全是其他 15 个环境（预期），VideoRepick 9 行 diff=0
```

最终代码（含 hold 修复）与首次改动后各跑一次，均为 VideoRepick `compared=9 diff=0`。

### 2. xhard reset 冒烟

脚本同 `xr.py` 写法（make→reset→核对）。**33/33 reset 成功**（seed 900000 起 3 个 + 930000 起 30 个，步长 101），另离线扫掠估计里又 reset 了 60 个（960000 起）也全部成功，合计 **93/93**：

- `spec_kind` 全部 `native-newvalue/1`；
- 方块数 6、`objects.cube_count = {requested 6, actual 6}`；全部落在 x∈[-0.3,0.1]、|y|≤0.25；
- 30 条样本：num_repeats {4:7, 5:8, 6:15}，n_swaps {8:6, 9:7, 10:7, 11:7, 12:3}，均在声明范围内；
- 颜色三通道均在 [0,1]；3 个发起者互异、首个为目标；
- 初态复核（D5 的 initial，构造期与正式 reset 各一次）**0 拒绝**；最近方块中心距 0.054~0.124 m，初态最小间隙 0.0016~0.055 m（OBB 退化导致名义 0.02 间距不保证，与 G2 结论一致，但无重叠）。

**结论：reset 级（含 D5 初态检查）拒绝率 0/93。D5 的扫掠拒绝全部发生在演示期（交换开始时才解析最近邻搭档），抽签段只 reset 看不到。**

### 3. xhard 演示（两级判据，H3）

入口与正式生成同一函数 `generate_dataset_newseed._worker`：官方 `v4_demo_probe`（4 条）＋ 同路径的 scratch 包装（额外取出 `runtime_checks`，36 条）。端点组合用 `--sampling-config` 把 `decision.swap.xhard` / `decision.num_repeats_range.xhard` 钉死。以下只计 hold 修复**之后**的 40 条（修复前另有 9 条成功，均为无拒绝局，未计入）：

| 组合 | 条数 | 演示成功 | D5 拒绝（BinCollisionError） | 其他失败 |
|---|---|---|---|---|
| 默认范围 [8,12]×[4,6] | 12 | **7** | 5 | 0 |
| swap 8 × pick 4 | 7 | **5** | 2 | 0 |
| swap 8 × pick 6 | 9 | **4** | 5（含 1 条 substep_after） | 0 |
| swap 12 × pick 4 | 3 | **2** | 1 | 0 |
| swap 12 × pick 6 | 9 | **3** | 5 | 1（FailsafeTimeout，12 次扫掠全过之后） |
| **合计** | **40** | **21（52.5%）** | **18（45%）** | 1 |

口径 14 端点：swap=8 成功 9/16、swap=12 成功 5/12、pick=4 成功 7/10、pick=6 成功 7/18；**四个角组合都有 ≥2 条演示成功，没有 0 成功组合**。
单条耗时：成功 51~76 s，D5 拒绝 9~36 s（首次交换就被拒的约占拒绝的一半）。

D5 拒绝的形态：`contact`、`中点判定`，交换双方之一在弯道中点与旁观块相交（g = -0.002~-0.020 m）；首段即拒的比例明显高于离线估计——演示里机器人先把目标方块抓起放下，放回点偏移后第一次交换（发起者就是目标）更容易扫到旁观块。

离线推演（reset 后按真实碰撞盒、运行时同一最近邻规则、交换后位姿互换，不含演示对目标的扰动）60 局：拒绝 23（38.3%），与 G2 的 41.5% 相符；真实演示拒绝率 45% 略高，原因同上。

### 4. 抽签规则估计（30 次内攒够 10 条 reset 成功）

- reset 级成功率 93/93 ⇒ 10 条候选在前 10 次尝试内即攒满，**30 次上限绰绰有余**；
- 但 D5 拒绝不在 reset 级暴露 ⇒ 10 条候选里演示成功数 ~ Binomial(10, ≈0.525)。H4 要在 10 条内递补出 3 条演示成功：P(≥3) ≈ 0.96（p=0.525）；按最差端点组合 swap12×pick6（3/9）估 p≈0.33，P(≥3) ≈ 0.69。即 VideoRepick 有约 4% 概率报 `selected_shortfall`（按默认范围）。

### 5. 轻量测试

- 新增 `test_v4_xhard_videorepick.py`：18 passed。
- 涉及文件子集（swap_schedule_generic / episode_action_sampling / native_sampling_config / episode_specs / operand_scope / TaskGoal / window_timeline / candidates_refactor / v4_decision_guard / 新文件）：改前（前 8 个文件）35 failed / 154 passed / 12 errors；改后（多加 v4_decision_guard 与新文件两项） **35 failed / 177 passed / 12 errors，失败集合与基线逐条相同**（中途一度多出 2 条，即上表 `test_real_swap_resolution...[VideoRepick]`，补假 env 属性后恢复）。
- 全量轻量套件在本机多 agent 并发下超过 500 s 未跑完，改跑上述覆盖 VideoRepick 的子集。

## 三、实测数字汇总

| 项 | 数 |
|---|---|
| 原三档 reset 探针 | VideoRepick 9 行 diff=0 |
| xhard reset | 93/93（初态 D5 拒绝 0） |
| xhard 演示（修复后 40 条） | 成功 21（52.5%），D5 拒绝 18（45%），FailsafeTimeout 1 |
| 默认范围演示 | 7/12 |
| 端点四角演示成功 | s8p4 5/7，s8p6 4/9，s12p4 2/3，s12p6 3/9 |
| 离线扫掠估计 | 23/60 = 38.3% 拒绝 |
| 单条耗时 | 成功 51~76 s，拒绝 9~36 s |

## 四、计划外

1. **`solve_hold_obj` 的裸 `except:` 会吞掉 D5 抛出的 `BinCollisionError` 并死循环**（`utils/subgoal_planner_func.py::solve_hold_obj`，`try: planner.open_gripper() except: AttributeError`——写法本意应为 `except AttributeError`）。交换发生在「静止」任务的 `solve_hold_obj` 循环里，step 抛错后 `elapsed_steps` 不前进，循环永不结束；每轮 step 都会重算搭档、重跑扫掠检查、再往 `_runtime_checks` 追加一条拒绝，最终内存暴涨，本机实测 rc=139（segfault）或跑满 590 s 外部超时。首轮演示看似「9/9 成功」其实是幸存者偏差：被拒的局全部挂死没有产出。
   处置：按 N12 不改共享函数，在 VideoRepick 里另写 xhard 专用 `_solve_hold_obj_xhard`（只吞 AttributeError）。**链路甲的 VideoRepick easy/medium 局也走同一个 `solve_hold_obj`，理论上同样会挂死**（甲已退役不再跑，原三档不动）；VideoUnmaskSwap 等其他打开几何检查的环境若也用 `solve_hold_obj` 做交换段等待，会踩同一个坑，建议主 agent 转告相关组。
2. **D5 拒绝全部发生在演示期，reset 级看不到**：搭档是交换开始时的最近邻，且演示先把目标抓放一次，位置会变，reset 时无法精确预判。计划 3.2 的「10 条 reset 成功候选」对本环境几乎等于「前 10 次尝试」，拒绝全压到 H4 的演示递补上（见第二节 4）。
3. **计划 2.13 表写「`native.parameters.num_repeats` 写 low=4, high_exclusive=7」无法照字面做**：该条目是全难度共用的（原三档读它），改它会改变原三档。实际做法：xhard 从 `decision.num_repeats_range.xhard` 取半开区间（该死键在 xhard 接上消费点），`config_xhard` 里留 `num_repeats_low/high_exclusive` 作源头。
4. **decision 与 native.configs.xhard 两份同值**：`native.parameters.configs` 由 `cls.configs` setdefault 进来，所以 xhard 的 cube/swap 在 native 里也有一份；xhard 分支**只读 decision**（守卫只允许 decision 的 xhard 条目偏离，收窄扫描都改 decision），native 那份不消费。主 agent 重导快照后若有人只改 native.configs.xhard，会静默不生效——建议审计把它列为 xhard 的中性键。
5. **xhard 拒收链路甲的 `episode_spec`**（原旧 xhard 可以走甲通道注入 3 块规格）。旧 xhard 已作废（A7），甲已退役；`tests/_shared/contract_builder_fixture.py` 的 `XHARD_GROUPS` 里仍有 VideoRepick/xhard，但只是契约链路的字符串，不起环境，不受影响。
6. G2 已记录的「方块 OBB 常退化成线段、名义 0.02 间距不保证」在 xhard 同样存在（初态最小间隙低到 0.0016 m），按指示未改工具函数；初态复核 0 拒绝，说明没有重叠。

## 五、待用户决策

1. **「block 颜色任意」的色域**：现取 RGB 各通道 [0,1] 均匀（最字面），会抽到接近桌面/背景的暗色或近白色（例：seed 900202 抽到 (0.07,0.03,0.65)，seed 900101 抽到 (0.56,0.91,1.0)）。是否需要饱和度/亮度下限、或避开按钮/桌面色？可直接通过 `decision.xhard.block_color.rgb_low/rgb_high` 覆盖，不改源码；如要 HSV 之类的采样方式需再改代码。
2. **演示期 D5 拒绝率约 45%**（端点 swap12×pick6 最差，约 6/9 失败）：是否接受按 H4 在 10 条候选内递补（估算 VideoRepick 约 4% 概率 `selected_shortfall`，最差组合下约 30%）？还是要在 reset 级加一次「按初始布局离线推演扫掠」的预筛（离线估计会拒掉约 38%，但因演示扰动仍有漏网），或者改机制（减小 `lane_offset`、搭档/绕行考虑旁观块）——后两者属改机制，须用户定。
3. 计划 2.13 表「`native.parameters.num_repeats` 写 low=4, high_exclusive=7」的落点按第四节 3 改为 decision 的 xhard 子键，请确认；计划原文需主 agent 同步。
