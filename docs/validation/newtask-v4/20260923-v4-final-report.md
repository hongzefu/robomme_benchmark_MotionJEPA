# 新值模式 V4 实施总报告：十六环境 xhard 档与可重放生成

> 对应计划 [NEWTASK_RELEASE_V4_PLAN.md](../../../NEWTASK_RELEASE_V4_PLAN.md)（以下简称「计划」）。工作副本
> `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-v4`，起点 `13e5151`（12.63），
> 本报告对应提交见第八节。commit 体例 `12.<n> <中文描述>`。
> 录像器 `RecordWrapper.py` 只按用户授权改了一处（`fail_safe_limit` 2000→5000，I1），其余冻结。
> 所有结论均在本机（2× RTX 6000 Ada，sm_89）得出——V1 与步 7 按用户决定在本机跑（口径 10 例外、K4）。

---

## 一、结论先行

**十六个环境的 xhard 档全部落地**：新值只落 xhard，原三档（easy/medium/hard）在定义、reset 取值与完整演示产物上都与改动前一致；
xhard 的每条规格可冻结、可回注、回注零偏差；抽签→冻结→实跑→推理整条链路打通；正式快照 `v4-01`（160 候选、48 条正式局）已冻结进 Git，
48 条正式局第一遍实跑 **47/48 凑满**（InsertPeg 缺 1 条，已按 H4 递补规则如实记录），视频与 h5 全部保存。

| 判据 | 查什么 | 判定行 | 结论 |
|---|---|---|---|
| **V0** | 原三档定义没被动过（静态） | `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0`（另：StopCube/MoveCube/InsertPeg 按 A6 新建三档同值 configs） | 通过 |
| **V1** | 原值回归（本机，改动前 `13e5151` vs 改动后） | `H5_PARITY compared=144 sha_equal=144 field_mismatch=0`；补跑 7 环境 63 条 62 相同，差的 1 条（PickHighlight/3）查实为 RRT 墙钟预算随负载变化，同负载下前后逐位相同 | 通过 |
| **V2** | 新值可重放（同一规格两遍） | 正式全量两遍（12 worker，K5 只报告）：`NEWVALUE_REPLAY=REPORT identities=56 terminal_mismatch=0 compared_success=47 sha_equal=47 field_mismatch=0 empty_or_invalid=0`；冒烟两份快照单 worker 同样全等 | 两遍逐位相同 |
| **V3g** | 规格真被消费 | `SPEC_BINDING=PASS specs=48 bad=0`；`SPEC_NEGATIVE=PASS cases=93 diff_zero=0`；全量第一遍 47 条成功局 `mismatch=0 unused=0` | 通过 |
| **V4f** | 新值可完成性（只报告） | 抽签：尝试 172、reset 成功 160、`candidate_shortfall=0`；实跑第一遍：`rollout_attempted=56 rollout_ok=47 backfilled=3 selected_shortfall=1` | 报告（不设门槛） |
| **V5e** | 推理链路通 | 正式快照（每环境 1 局，共 16 局）：`EVAL_PIPELINE=PASS episodes=16 runtime_ok=16 join_missing=0`，规格绑定 16/16 零偏差 | 通过 |
| **V6** | 组合覆盖（口径 14） | `COMBO_COVERAGE=PASS combos=91 missing_combinations=0 zero_success_combinations=0`（455 条：reset 452、演示 402）；PatternLock 长度 25 被静默兜底掩盖，已按 K1 把上界改为 24 | 通过（K1 修正后） |

---

## 二、口径与用户决策汇总

计划 1.1 的十四条口径不变，实施中新增/改变的决策（全部为用户原话选定，已写回计划 1.3）：

| 编号 | 决策 | 影响 |
|---|---|---|
| G2 | Unmask 容器区域不动、`min_gap_factor` 0.75、N=8；VideoRepick clutter 6 块 | 2.8 / 2.9 / 2.13 |
| G3 | MoveCube `corner_bias=0.5` | 2.17 |
| V1 本机 | 「原值回归只需要在本机器跑」 | 口径 10 例外 |
| I1 | 录像器 `fail_safe_limit` 2000→5000（PickXtimes num=15 约 2206 步） | N2 唯一例外 |
| I2 | InsertPeg 第 4 根杆开局重叠 2.4%→31.6%：维持现状 | 2.18 |
| I3 | V4 抽签/实跑/推理全部不开 fail recover | 3.3 / 第四节 |
| J1 | 四个 Unmask 的干扰容器参与揭示、误抓即失败 | 2.7 |
| J2 | VideoRepick 演示期约 45% D5 拒绝：接受、靠 H4 递补 | 2.13 |
| J3 | 任意颜色：HSV 限定色域（S≥0.5、V≥0.4） | 2.12 / 2.13 |
| J4 | PickHighlight 颜色后缀整段去掉 | 2.12 |
| J5 | PickXtimes `corner_bias=0.5`、推全部 3 个有色方块 | 2.4 |
| J6 | BinFill「全部 clutter」＝12 块开局全在场、放不满即失败；投入色数 `[2,3]` | 2.3 |
| J7 | VideoPlace 两环境演示 2 块后「随机挑一块来问」 | 2.14 / 2.15 |
| J8 | V6 每组合 5 条、本机多 worker | V6 |
| J9 | 48 条全量保存视频与 h5 | 步 7 |
| K1 | PatternLock 节点数 `[20,25]`→`[20,24]` | 2.19 |
| K2 | VideoPlaceOrder 异常遮蔽只在 xhard 修 | 2.15 |
| K3 | InsertPeg 近目标杆距离带上限 0.085 m | 2.18 |
| K4 | 步 7 全量在本机跑 | 口径 10 |
| K5 | 抽签、实跑都用多 worker，允许两遍少量不同（V2 改为报告） | V2 |

---

## 三、逐 task 的变化与字段

每个 task 一节：**用户原文 → 参数（decision/native 路径｜hard 值｜xhard 值）→ 行为改动 → 规格里记录的字段 → 实测**。
参数路径指 `scripts/configs/newtask-v4/sampling_config.json` 里该任务的 `{decision, native}` 块；「规格字段」取自正式快照
`scripts/configs/newtask-v4/v4-01/specs.jsonl` 的一条规格（`<i>` 表示按序号展开）。实测列：「正式局」为步 7 第一遍，
「V6」为组合覆盖（每组合 5 条）演示成功数。所有新值只在 `self.difficulty == "xhard"` 分支生效。

### 3.1 BinFill（派生自 hard；12.69）

用户原文：「全部clutter, 12, color 3 个, put_in_number [5,7]」

| 参数路径 | hard | xhard |
|---|---|---|
| `decision.configs.xhard.spawn_cubes` | `[10,12]` | `[12,12]` |
| `decision.configs.xhard.color` | 3 | 3 |
| `decision.configs.xhard.put_in_numbers` | `[3,5]` | `[5,7]` |
| `decision.configs.xhard.layout_mode` | （顶层 `native_dynamic`） | `clutter`（J6） |
| `native.parameters.put_in_color.xhard` | `[2,3]` | `[2,3]`（J6） |
| dynamic | `randint(0,2)` | 固定 False，xhard 不再抽这一次 |

行为改动：放开 `_resolve_sampling_config` 的 layout_mode 守卫（只对 xhard 的 clutter 放行）；D1 只在 xhard 修——放不满 12 块抛
`SceneGenerationError`、`_initialize_episode` 某色不够也抛；`min_gap` 改读 `min_gap_value`（值不变）。主入口
`SAMPLING_OPERAND_PATHS` 的 BinFill configs 改为三档逐条比对。

规格字段（24）：`layout.mode`、`layout.dynamic`、`layout.cubes.{red,green,blue}_<i>`、`layout.board.offsets`、`layout.button_xy`、
`objects.{spawn_numbers,spawn_order,spawn_requested,spawn_actual,color_pool,put_in_color,target_numbers}`、`initializations.<i>.color_order`。

实测：正式局 3/3；V6 6 组合 19/30（投入 2 色 × put_in 取 5/7、以及 put_in=7 × 3 色 各 2/5，失败均为演示期规划失败）。

### 3.2 PickXtimes（派生自 hard；12.73、12.79）

用户原文：「把 target 生成的位置尽可能推向边角，color 3, num [6, 15], 增加其他颜色 distractor」

| 参数路径 | hard | xhard |
|---|---|---|
| `decision.number_range.xhard` | `[4,5]` | `[6,15]` |
| `decision.color.xhard` | 3 | 3 |
| `decision.xhard.target_cube_position_policy` | 区域 `[-0.1,0]`±0.2、均匀 | 同区域，`corner_bias=0.5`（J5，推全部 3 个有色方块） |
| `decision.xhard.goal_position_policy` | 与方块同区域 | 独立一套，值同原区域（C1） |
| `decision.xhard.distractor` | 无 | 3 个：黄/青/品红各 1（B2），方块区域内均匀 |

行为改动：xhard 先放圆盘再放方块（G1），并把无碰撞体的圆盘换成外接正方形参与避让（否则会被 `spawn_random_cube` 静默忽略）；
目标候选池与干扰物解耦；`target_color_name` 按对象回填；干扰物进 `non_target_cubes`（抓错即失败）；D2 只在 xhard 修；
序数表已全局扩到 20（E2）。num=15 演示约 2206 步，依赖录像器上限 5000（I1）。

规格字段（19）：`layout.cubes.{red,green,blue}_0`、`layout.distractors.{yellow,cyan,magenta}_0`、`layout.goal_xy`、`layout.button_xy`、
`layout.cube_corner_bias`、`objects.{num_repeats,color_order,target_candidates,target_color_idx,target_cube_idx,distractors}`、
`objects.cube_count.{requested,actual}`、`objects.distractor_count.{requested,actual}`。

实测：正式局 3/3；V6 10 组合 46/50（num=15 为 4/5）。

### 3.3 SwingXtimes（派生自 hard；12.73）

用户原文：「number [4, 10]， 增加其他颜色 distractor」

| 参数路径 | hard | xhard |
|---|---|---|
| `decision.number_range.xhard` | `[3,3]` | `[4,10]` |
| `decision.color.xhard` | 3 | 3 |
| `decision.xhard.distractor` | 无 | 黄/青/品红各 1，区域 `[-0.1,0]`±0.25 |

行为改动：`_color_lists` 改动态建表（防第四色 KeyError）；目标候选池解耦、干扰物进非目标列表；圆盘避让同 PickXtimes。
干扰色没有扩进 `native.color_pool`（那会改原三档随机流），而是单列在 `decision.xhard.distractor`。

规格字段（18）：同 PickXtimes 的结构，另有 `layout.targets.<i>`（两个摆动目标）。

实测：正式局 3/3；V6 7 组合 34/35；num=10 演示约 1000 步。

### 3.4 StopCube（现值即 hard，A6；12.70）

用户原文：「速度最快档， number [6,15]」

| 参数路径 | hard（＝原全局常量） | xhard |
|---|---|---|
| `decision.xhard.move_interval_choices` | `[60,80,120]` | `[60]` |
| `decision.xhard.stop_time_range` | `{low 2, high_exclusive 6}` ⇒ 2～5 | `{low 6, high_exclusive 16}` ⇒ 6～15 |

行为改动：新建 `configs`（easy/medium/hard 三档同值＝原常量）；`step` 的往返段数 xhard 用 `max(5, stop_time)`（原三档仍 `range(5)`）；
`vqa_options._options_stopcube` 的 checkpoint 公式只依赖 `steps_press`，两侧自动一致，未改代码（用参数化测试锁住）；C4 阈值一个都没调。

规格字段（11）：`actions.{move_interval,move_interval_idx,stop_time,steps_press,stop_window,motion_segments,rotation_deg}`、
`actions.sampling_trace.interval_draw`、`layout.{button_xy,target_xy}`、`objects.cube_rgb`。

实测：正式局 3/3；V6 10 组合 50/50；stop_time=15 演示约 910 帧。

### 3.5 VideoUnmask（派生自 hard；12.72、12.81）

用户原文：「增加其他颜色 distractor, clutter bin, pick 3」

| 参数路径 | hard | xhard |
|---|---|---|
| `decision.pick_count.xhard` | 2 | 3 |
| `decision.bin_layout_policy.count.xhard` | 15（实际只放下 4～8） | 8（G2） |
| `decision.bin_layout_policy.xhard.min_gap_factor` | 2 | 0.75（G2） |
| `decision.xhard.distractor` | 无 | 3 个外环容器（`max(|x|,|y|)∈[0.2675,0.45]`、相机可见），1～2 个扣黄/青/品红 cube |

行为改动：pick 分支改按次数循环（`_append_xhard_pick_tasks`）；`task_goal.py` 给 pick=3 的文本；放不满抛 `SceneGenerationError`；
干扰容器存 `distractor_bins`、不进 `spawned_bins`、不用 `bin_<i>` 命名；**J1：干扰容器与区域容器同一机制、同一窗口 [0,64) 揭示**，
**误抓（z>0.15）即失败**（加在每个已有 failure_func 上）。

规格字段（12）：`layout.bins.<i>`、`layout.bin_count.{requested,placed}`、`objects.{color_order,n_picks,pick_order}`、
`objects.distractors.{requested,placed,bins.<i>,cube_bins,cube_colors,cube_count}`。

实测：正式局 3/3；V6 2 组合 10/10。

### 3.6 ButtonUnmask（派生自 hard；12.72、12.81）

用户原文：同 VideoUnmask。参数与行为与 3.5 同构（pick 3、容器 8、系数 0.75、外环干扰容器、揭示、误抓即失败），差异：
构造期 `randint(1,6)` 占位抽样逐字保留（N5）；首个 pickup 任务的单元素列表形态保留；按钮区与容器区重叠，放置更紧。

规格字段（14）：3.5 的字段外加 `layout.button_xy`、`actions.sampling_trace.constructor_draw`。

实测：正式局 3/3；V6 2 组合 10/10。

### 3.7 VideoUnmaskSwap（派生自 hard，覆盖旧 xhard；12.68、12.80、12.81）

用户原文：「swap [8, 12], pick 3, 增加其他颜色 distractor, swap 速度 x1.5」

| 参数路径 | hard | xhard |
|---|---|---|
| `decision.swap_count_range.xhard` | `[2,3]` | `[8,12]`（旧 xhard `[4,5]` 作废，A7） |
| `decision.pick_count_range.xhard` | `[2,2]` | `[3,3]` |
| `native.parameters.xhard.object_selection.pickup_selected_indices` | `[0,1]` | `[0,1,2]` |
| `decision.xhard.swap_speed_multiplier` | 1（死键） | 1.5 ⇒ 每段 `round(50/1.5)=33` 步，起点 64 |
| `decision.xhard.distractor` | 无 | 3 个外环容器，1～2 个含 cube |

行为改动：交换窗口改具名常量按倍率取整；**H1：xhard 乙通道新开初态＋连续扫掠碰撞检查，干扰容器并入**；xhard 交换期等待改用
只吞 `AttributeError` 的 `solve_hold_obj_xhard`（修复碰撞拒绝被共享函数裸 except 吞掉导致的死循环）；J1 揭示与误抓即失败。
撤销审计豁免 `swap_speed_multiplier`。

规格字段（17）：`actions.swap_window.{start_step,duration_steps,speed_multiplier}`、`layout.{bins.<i>,type_choice,distractors.<i>,distractors_requested,distractors_placed}`、
`objects.{n_swaps,n_picks,selected,target_choice,color_order,swap_initiator_indices,swap_initiator_third}`、`objects.distractors.{cube_colors,n_with_cube}`。

实测：正式局 3/3（1 条正式局碰撞拒绝，由候选 1 递补）；V6 10 组合 49/50。

### 3.8 ButtonUnmaskSwap（派生自 hard；12.68、12.81）

用户原文：「swap [6, 8], pick 3, 增加其他颜色 distractor, swap 速度 x1.5」

| 参数路径 | hard | xhard |
|---|---|---|
| `decision.swap_count_range.xhard` | `[2,3]` | `[6,8]` |
| `decision.pick_count_range.xhard` | `[2,2]` | `[3,3]` |
| `native.parameters.bin_count.xhard` | 4 | 4 |
| `decision.xhard.swap_speed_multiplier` | 1（死键） | 1.5；`native.swap_window` 真正被消费，`{64, 33}` |
| `decision.xhard.distractor` | 无 | 同 3.7 |

行为改动：`_refresh_swap_schedule` 三分支换通式＋`for k in range(3, swap_times)` 补槽位；六处 50 字面量改具名常量；
xhard 下按完第二个按钮后原地等到最后一段交换结束（原解法会在容器还在交换时去抓）；碰撞检查与揭示/误抓同 3.7。

规格字段（17）：同 3.7。

实测：正式局 3/3；V6 6 组合 24/30（失败均为碰撞拒绝）；8 swap + 3 pick 最长约 728 步（低于 1302 配额）。

### 3.9 VideoRepick（派生自 medium，覆盖旧 xhard；12.77、12.78）

用户原文：「clutter, pick times [4,6], block颜色任意, 如果是 swap [8, 12]」

| 参数路径 | medium | xhard |
|---|---|---|
| `decision.xhard.layout` | 三组锚点 | `clutter`，6 块（G2），整片区域 `[-0.1,0]`±`[0.2,0.25]` |
| `decision.num_repeats_range.xhard` | 死键（native 实取 1～3） | `{low 4, high_exclusive 7}` ⇒ 4～6，xhard 接上消费点 |
| `decision.swap.xhard` | `[2,3]` | `{swap_min 8, swap_max 12}`（A3） |
| `decision.xhard.block_color` | 三块同色、红/蓝/绿 | 三块同色、HSV 限定色域任意色（C2、J3） |

行为改动：新方法 `_load_cubes_xhard`（颜色→6 块位姿→目标→另 2 个发起者，发起者仍 3 个，B12）；**D5：四处扫掠检查改为「甲通道，或 xhard 乙通道」**；
xhard 专用等待函数（同 3.7 的死循环修复）；xhard 拒收甲通道 `episode_spec`。

规格字段（9）：`layout.cubes.<i>.xy_yaw`、`objects.{color_rgb,n_swaps,num_repeats,target,swap_initiators,swap_initiators_remaining}`、`objects.cube_count.{requested,actual}`。

实测：正式局 3/3；V6 15 组合 50/75（BinCollisionError 23，J2 接受）。

### 3.10 VideoPlaceButton（派生自 hard；12.74）

用户原文：「video 里面完成2 个 block, 各自放回原位，其余不变」

| 参数路径 | hard | xhard |
|---|---|---|
| `decision.xhard.demo_object_count` | 1（死键） | 2 |
| `decision.xhard.demo_return_policy` | 放到隐藏 goal_site | `return_to_origin` |
| 其余（color 3、targets 4、swap True、additional_place False） | — | 不变 |

行为改动（J7）：演示模板改按对象循环——每块在按钮前放 `targets[2k]`、按一次按钮、再放 `targets[2k+1]`，然后各自放回原位；
问法随机挑一块问「按钮前/后放的台」；「原位」落点由 `utils/xhard_home_site.py::build_home_sites` 直接调 target builder 在方块初始位姿建
（不用 `spawn_random_target`，验收：位姿逐位相等、建 actor 前后 generator 状态逐字节相等）；vqa 的 drop 候选追加两个落点；撤销审计豁免。

规格字段（14）：`layout.{cubes.<color>_0,goal_xy,targets.<i>,button_xy}`、`objects.{demo_ids,answer_demo_index,task_flag,color_order,swap_pair_ids}`、
`actions.{target_target_id,return_pose_by_object_id.<cube>}`。

实测：正式局 3/3；V6 1 组合 4/5；抽签 13 次得 10 条。

### 3.11 VideoPlaceOrder（派生自 hard；12.74、12.86）

用户原文：同 3.10。参数同 3.10。行为改动（J7）：两块依次各走一遍访问序列、走完放回原位；问法随机挑一块、问它放过的第 N 个台；
按钮插点公式重推为 `2×(b+1+此前已完成的放回原位次数)`（单对象时退化为原 `k*2+2`）；**K2：只在 xhard 修 `SceneGenerationError`
被 `from .utils import *` 遮蔽成 TypeError 的问题**（原三档仍 TypeError）。

规格字段（18）：3.10 的字段外加 `actions.button_task_index`、`objects.{button_after_visit_index,which_in_subset,num_targets_by_object.<i>,visit_ids_by_object.<i>}`。

实测：正式局 3/3；V6 1 组合 3/5（2 条为修复前的 TypeError）；抽签 19 次得 10 条（hard 布局本身约 45% 放不下第 4 个台）。

### 3.12 PickHighlight（派生自 hard；12.71、12.78）

用户原文：「clutter, highlight number [5, 7], block颜色任意」

| 参数路径 | hard | xhard |
|---|---|---|
| `decision.highlight_count.xhard` | 3 | `[5,7]` |
| `decision.spawn_count.xhard` | 6 | `[8,10]`（B5） |
| `decision.xhard.block_color_policy` | 红/蓝/绿逐块抽 | `hsv_floor`（J3） |
| `decision.xhard.subgoal_color_suffix` | `, which is {color}` | `omit`（J4） |

行为改动：spawn≥highlight 硬断言；放不满与 `randperm[:k]` 截断在 xhard 抛错；D4 只在 xhard 修（首个按钮任务补 failure_func）；
`disk_radius` 不动（C3）。

规格字段（7）：`layout.{cubes.<i>,button_xy}`、`objects.{n_cubes,n_cubes_spawned,color_rgba.<i>,highlight_count,highlight_ids}`。

实测：正式局 3/3；V6 9 组合 43/45；高亮 7 块演示 1146～1204 步（对 1300 评估上限余量约 8～12%）。

### 3.13 MoveCube（现值即 hard，A6；12.75、12.76）

用户原文：「把 cube 和 stick 生成的位置尽可能推向边角, stick 的转角更大，可以和桌面平行, 更难抓」

| 参数路径 | hard（＝原全局常量） | xhard |
|---|---|---|
| `decision.demo_layout.xhard.corner_bias` | 0（均匀） | 0.5（G3） |
| `decision.execution_layout.xhard.corner_bias` | 0 | 0.5（两套各自一份） |
| `decision.peg_yaw_range.xhard` | ±45°（span π/2） | ±180°（span 2π，A1） |

行为改动：新建 `configs`（三档同值）；B11 等价朝向归约——夹爪 x 轴相对「基座→抓取点」方位角超过 ±90° 时夹爪姿态右乘 Rz(π)，
抓杆后的推杆姿态同步右乘 Rz(π)（`subgoal_planner_func` 里由环境开关 `_xhard_peg_yaw_reduction` 守着，原三档不进分支）；D3 只在 xhard 修；
三种 way 都保留。

规格字段（13）：`layout.{demo,execution}.{cube_pose,goal_xy,peg_offsets,peg_yaw,corner_bias}`、`initializations.<i>.way_idx`、`objects.obj_sample`、
`objects.sampling_trace.dir_sample`。

实测：正式局 3/3；V6 1 组合 5/5；G3 扫描 0→8/8、0.25→7/8、0.5→6/8、0.75→6/8、1.0→5/8。

### 3.14 InsertPeg（现值即 hard，A6；12.75）

用户原文：「多生成一个 stick 里 target stick 更近，stick 的转角更大，可以和桌面平行, 更难抓」

| 参数路径 | hard（＝原全局常量） | xhard |
|---|---|---|
| `decision.xhard.peg_count` / `peg_offsets` | 3 / `[0.1,0,-0.1]` | 4 / `[0.1,0,-0.1,-0.2]` |
| `decision.xhard.near_target_distractor` | 无消费点 | 第 4 根在目标杆 peg_0 周围、中心距 (0.075, 0.085] m（K3） |
| `decision.xhard.peg_yaw_range` | ±45° | ±180° |

行为改动：新建 `configs`；第 4 根杆独立采样（排在既有抽样之后，N5），原判据一条未改（B6）；`insert_peg` 在归约翻转时把夹爪局部系里的
平移取反 xy，四种 obj×direction 组合核过世界系路点一致；vqa 候选随杆数自动 6→8。

规格字段（11）：`initializations.<i>.{pegs.<i>,box_jitter,box_yaw,obj_sample,dir_sample,near_target_distance,near_target_attempts,peg_placement.{requested,placed}}`、
`objects.{head_rgb,sampling_trace.random_peg_idx}`。

实测：**正式局 2/3**——10 条候选跑了 10 条只成功 2 条（规划器找不到路径 4、跑完任务表仍未成功 4），`selected_shortfall=1`；
V6 1 组合 5/5。开局目标杆与他杆重叠率 31.6%（I2 维持现状）是主要原因之一。

### 3.15 PatternLock（派生自 hard；12.65、12.86）

用户原文：「最难情形 video 部分生成 20-30s」

| 参数路径 | hard | xhard |
|---|---|---|
| `decision.grid.xhard` | 5 | 5（B8 不改布局） |
| `decision.path_length_range.xhard` | `[4,8]` | `[20,24]`（K1；原定 `[20,25]`） |

行为改动：只加 `config_xhard`，路径搜索不改（B8）。长度 25 实测 1000 次预算内只 4/10 真得到、其余静默用错长路径 ⇒ K1 改为 24。

规格字段（2）：`actions.path_nodes`、`actions.path_attempts`。

实测：正式局 3/3；V6 6 组合 30/30（其中长度 25 的 5/5 是被兜底掩盖的，已作废）。20 节点 ≈ 19 段 × 31 帧 ≈ 19.6 s，略低于 20 s 下限（计划 2.19 已提示）。

### 3.16 RouteStick（派生自 hard，覆盖旧 xhard；12.65）

用户原文：同 PatternLock。

| 参数路径 | hard | xhard |
|---|---|---|
| `native.parameters.configs.xhard.length` | `[4,7]` | `[12,15]`（旧 xhard `[8,10]` 作废，B9） |
| `...backtrack` | True | True |

行为改动：只改 `config_xhard`。演示 L×50 帧 ⇒ 600～750 帧 ⇒ 20～25 s。

规格字段（5）：`objects.L`、`actions.{nodes,directions.<i>}`、`layout.{rotation_deg,obstacle_rgb.<i>}`。

实测：正式局 3/3；V6 4 组合 20/20。

---

## 四、链路实现（第三、四节的落地）

| 环节 | 文件 / 锚点 | 要点 |
|---|---|---|
| 规格记录器 | `utils/episode_spec.py::SpecRecorder`、`spec_kind_for` | xhard 局标 `native-newvalue/1`，原三档 `native-parity/1`，两类不许互喂；`value(..., decision_key=)` 归因 |
| decision 守卫 | `utils/sampling_config.py::assert_native_decision` | 去掉所有 `xhard` 键后须与原值全等；xhard 子树只许改值、键结构须与源码申报一致 |
| 共用件 | `utils/xhard.py`（干扰色池、`corner_push`、`hsv_floor_rgb`）、`subgoal_language.py`（序数表 20） | 默认参数下与原行为逐字等价 |
| 抽签/冻结 | `scripts/parity/v4_specs.py`（draw / freeze / reselect / `load_specs`） | 来源（配置全文、源码指纹、runtime、seed 规则、recover 规则）抽签时封存、冻结时逐项核；身份散列剔除 `selected`；seed 段 `4_000_000+env_code×100_000+episode×100+attempt` |
| 实跑 | `scripts/parity/v4_rollout.py`（run / compare）→ `train_split_runner.py --identity-source formula --no-recovery` → `train_split_worker.run_one` | H4 递补；V2 两层（终态＋HDF5 逐位，前置有效性与根属性检查）；K5 多 worker ＋ `--report-only` |
| 推理 | `env_record_wrapper/episode_config_resolver.py::BenchmarkEnvBuilder.from_v4_specs`、`scripts/eval/v4_eval.py` | runtime 四项不等即拒；`eval_results.jsonl` / `eval_summary.json`；`--join-results` 打印 V5e |
| 探针与覆盖 | `scripts/parity/v4_reset_probe.py`、`v4_demo_probe.py`、`v4_combos.py`、`v4_spec_negative.py` | reset 级回归、演示摸底、V6 分片并行、V3g 反例 |

---

## 五、验证结果明细

### V0
静态导出十六环境的原三档 `configs`、`decision`（去掉 xhard）与 `native`，改动前 `13e5151` 与当前逐项比对：十三个环境零差异；
StopCube/MoveCube/InsertPeg 由「无 configs」变为「三档同值 configs」（A6 预期，三档值等于原全局常量，各自单测锁住）。

### V1（本机，见 [20260923-v1-native-regression-local.md](20260923-v1-native-regression-local.md)）
全量 144 条 `sha_equal=144`；补跑 63 条 62 相同，PickHighlight/3 在空闲/繁忙两种负载下各有一个可重复结果，改动前代码同样如此——无代码回归。
另：reset 级探针在每次合并后对 144 条复核，全部 `RESET_REGRESSION=PASS diff=0`。

### V2
- 冒烟 smoke-01（PatternLock+RouteStick）、smoke-02（StopCube+SwingXtimes，无 recover）单 worker：均 `NEWVALUE_REPLAY=PASS identities=4 sha_equal=4`。（冒烟产物已于 2026-09-23 清理）
- 正式全量两遍（12 worker，K5）：第二遍严格重放第一遍跑过的 56 个身份（48 selected ＋ 8 条递补候选）。
  `NEWVALUE_REPLAY=REPORT identities=56 terminal_mismatch=0 compared_success=47 sha_equal=47 field_mismatch=0 empty_or_invalid=0`——
  终态与失败类别 56/56 一致，47 条成功局 HDF5 整文件逐位相同。多 worker 负载下也没有出现分叉（K5 允许的「少量不同」本轮为零）。
  命令：`v4_rollout compare artifacts/newtask-v4/v4-01/rollout/run1 …/run2 --report-only`；第二遍 `ROLLOUT_DONE rollout_attempted=56 rollout_ok=47`，墙钟 1078 s。

### V3g
- 绑定：正式全量第一遍 47 条成功局 `mismatch=0 unattributed_mismatch=0 unused=0`；冒烟回注同样零偏差。
- 反例（`scripts/parity/v4_spec_negative.py`，reset 级）：48 条 selected 规格各取 2 个取值点改坏（数值 +0.037／+1，0/1 取反，整数列表倒序）再回注，
  比较 actor 与关节体位姿、渲染颜色、任务表与任务指令文本、环境上的数值/位姿/整数属性：`SPEC_NEGATIVE=PASS cases=93 diff_zero=0`；
  原样回注 `SPEC_BINDING=PASS specs=48 bad=0`。
- 检验本身迭代过三轮（首轮 `diff_zero=51` 全部查实为检验盲区而非规格未被消费）：①只抓 actor 位姿，看不到按钮（关节体）、颜色、reset 后被藏起的目标原位姿；
  ②把 `record()` 记的派生量（如 `bin_count.placed`、`path_attempts`）也拿去改——它们回注时只核对不建场景，应排除；
  ③ManiSkill 在 `gym.make` 构造期先初始化一次、`reset` 再初始化一次，非最后一次 `initializations.<k>` 的取值会被覆盖，只改最后一次；
  另把 0/1 整数的改法由 +1 改为取反（InsertPeg 的 `obj_sample` 只判是否为 0，1→2 语义不变）。

### V4f（只报告）
- 抽签：尝试 172、成功 160；VideoPlaceButton 13 次、VideoPlaceOrder 19 次攒满，其余 10 次攒满。
- 实跑第一遍：`rollout_attempted=56 rollout_ok=47 backfilled=3 selected_shortfall=1`。失败 9 条：InsertPeg 8（PlannerExhausted 4、跑完任务表未成功 4），
  VideoUnmaskSwap 1（BinCollisionError）。递补：VideoUnmaskSwap 候选 1 成功顶上；InsertPeg 候选 4、5 成功顶上，其余耗尽。

### V5e
- 冒烟：`EVAL_PIPELINE=PASS episodes=4 runtime_ok=4 join_missing=0`，规格绑定零偏差（dummy 策略全部 timeout 属预期）。
- 正式快照（每环境取 1 条 selected，dummy 策略、`max_steps=1300`）：`EVAL_PIPELINE=PASS episodes=16 runtime_ok=16 join_missing=0`；
  16 局规格绑定全部 `mismatch=0 unused=0`；结果 15 timeout、1 fail（dummy 策略的预期结果，只验链路）。产物 `artifacts/newtask-v4/v4-01/eval-all/eval_results.jsonl`。
- **发现：推理应评「按实跑结果重标」的快照。** 冻结时 InsertPeg 的初选 0/3/6 在实跑中演示全部失败（H4 递补上来的是候选 4、5），
  用原快照评 InsertPeg/0 时，推理入口在 reset 期重放示范、规划器反复失败，进程卡死（连续两次各 15～34 分钟无进展，进程处于 D 状态）。
  于是新增 `v4_specs reselect`：按 `results.jsonl` 的成功局重标 `selected`，header 与规格值一字不动、`identity_sha256` 不变（`2e3766c9…`），
  另写 `scripts/configs/newtask-v4/v4-01/specs.selected.jsonl`（47 条正式局，InsertPeg 为 4/5、VideoUnmaskSwap 为 0/1/6）。
  前 12 局用原快照（这 12 个环境的初选第 0 条都演示成功），后 4 局（InsertPeg、MoveCube、PatternLock、RouteStick）用重标快照。

### V6（见 [20260923-step3c-v6-combo-coverage.md](20260923-step3c-v6-combo-coverage.md)）
`COMBO_COVERAGE=PASS combos=91 zero_success_combinations=0`；K1 后清单重建为 90 个组合（PatternLock 去掉长度 25）。

---

## 六、实施步骤与状态

| 步 | 内容 | 状态 |
|---|---|---|
| 0 | G2/G3 实测与定数 | 完成（G2、G3 均已定） |
| 1 | 链路甲退役 | 完成（README 退役口径，甲的代码与产物零改动） |
| 2 | SpecRecorder 升版、守卫分叉 | 完成 |
| 3a/3b | 十六环境建 xhard | 完成（9 组子任务并行＋合并复核） |
| 3c | V6 组合覆盖 | 完成 |
| 4 | 正式抽签与冻结 | 完成（`v4-01`，160 行、48 selected） |
| 5 | 实跑编排 | 完成（冒烟两次通过） |
| 6 | 推理侧 | 完成（冒烟通过） |
| 7 | 全量两遍 + V2/V3g/V4f/V5e | 全部完成：V2 两遍逐位相同、V3g 通过、V4f 报告、V5e 通过 |
| 8 | 留档 | 本报告＋`docs/validation/newtask-v4/` 下各步报告 |

---

## 七、计划外发现、风险与盲区

1. **G2 基线错误**：hard `bin=15` 真实只放下 4～8 个（`spawn_random_bin` 把 min_gap 加了两次），不是计划写的 9～12。
2. **recover 会改变 reset 期抽样**：抽签与实跑必须同口径，最终用户定 V4 全部不开（I3）。
3. **共享函数 `solve_hold_obj` 裸 except 吞掉碰撞拒绝**，导致 VideoRepick 与 VideoUnmaskSwap 的被拒局死循环；只在 xhard 用专用等待函数修复（N12）。
4. **PatternLock 长度 25 被静默兜底**：V6 判据在此被掩盖，靠单独 reset 实测发现，已按 K1 改上界。
5. **VideoPlaceOrder 异常遮蔽**（四档既有）：只在 xhard 修（K2），原三档布局失败仍被主入口记为代码类失败。
6. **负载敏感**：mplib RRT 墙钟预算让同一规格在不同负载下轨迹不同（V1 的 PickHighlight/3、K5 的依据）。以后 V1 两侧应在相近负载下跑。
7. **InsertPeg 演示成功率低**（正式候选 2/10）：开局杆重叠 31.6%（I2 维持现状）＋ ±180° 杆的规划难度。
8. **PickHighlight 高亮 7 块、BinFill 端点组合的步数/成功率余量偏紧**，见 3.1、3.12。
9. 盲区：新值没有官方原版可比，V2 只能证明「同一规格可重放」，「值对不对」靠第三节的实测与人工看片；本机结论未在 A40 上复核。

---

## 八、提交与产物

**提交**（均已推送 `origin/newtaskRelease-v4`）：12.64 步 1～2 → 12.65 共用底座与两个长度环境 → 12.66 G2 定数与演示探针 →
12.67 链路层（抽签/冻结/实跑/推理/V6 工具）→ 12.68～12.75 十四个环境 xhard 合并 → 12.76～12.79 用户决策落地 → 12.80～12.81 Swap 死循环修复与干扰容器揭示 →
12.82～12.84 V6 → 12.85 V1 报告 → 12.86～12.87 K1～K5 → 12.88 正式快照冻结 → 12.89 报告初稿 → 12.90 全量两遍、V2/V3g/V5e 与重标快照。

**产物**（仓库内，`artifacts/` 不入 Git）：

| 内容 | 位置 |
|---|---|
| 正式规格快照（入 Git） | `scripts/configs/newtask-v4/v4-01/specs.jsonl`（冻结初选 48 条，identity `2e3766c9…`）；`specs.selected.jsonl`（按实跑重标，47 条，身份相同，**推理用这份**） |
| V4 采样快照 / V6 组合清单（入 Git） | `scripts/configs/newtask-v4/sampling_config.json`、`combos.json` |
| 抽签原始记录 | `artifacts/newtask-v4/v4-01/draft/drafts.jsonl` |
| 全量第一遍 / 第二遍（h5＋视频，J9） | `artifacts/newtask-v4/v4-01/rollout/run1/`、`run2/`（每局 `episodes/<task>_episode_<i>/{hdf5_files,videos}`，汇总 `results.jsonl`、`summary.json`） |
| V1 | `artifacts/newtask-v4/v1-base-13e/`、`v1-after-6cc/`、`v1-sup-00a94de/`、`v1-compare*/` |
| V6 | `artifacts/newtask-v4/combos/v6-01/`（`samples-*.jsonl`、`summary.json`） |
| V3g / V5e | `artifacts/newtask-v4/v4-01/v3g-v3.json`；`artifacts/newtask-v4/v4-01/eval-all/eval_results.jsonl` |
| 各步报告 | `docs/validation/newtask-v4/`（step1-2、step0-g2、step3、step3b-*、step3c-v6、step4-6、v1、本报告） |
