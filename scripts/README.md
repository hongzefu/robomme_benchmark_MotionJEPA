# scripts/ 说明：V4 xhard 档

本文只讲四件事：

1. **逐环境改动**：十六个环境各自新增了哪些配置字段、哪些规格字段，改了什么行为，subgoal 执行流程怎么变（第一节）；
2. **全局改动**：共用代码、快照文件、结果文件里新增了哪些字段（第二节）；
3. **推理侧怎么兼容**（第三节）；
4. **三步各自怎么调用**：抽签与冻结、实跑、推理（第四节）。

验证数字、决策来由和风险见 [V4 总报告](../docs/validation/newtask-v4/20260923-v4-final-report.md)，计划见
[NEWTASK_RELEASE_V4_PLAN.md](../NEWTASK_RELEASE_V4_PLAN.md)。

新值**只挂在 `self.difficulty == "xhard"` 分支上**，原三档（easy/medium/hard）的定义、reset 取值、完整演示产物都与改动前逐位相同。

---

## 第一节　逐环境改动

**怎么读：**

- **新增配置字段**：写在 [configs/newtask-v4/sampling_config.json](configs/newtask-v4/sampling_config.json) 里，路径相对于 `tasks.<环境>`。
  「hard 值」一列是原值，用来对照；键名本来就有、只是新加了 `xhard` 档的，也列在这里。
- **新增规格字段**：该环境 xhard 局在 `specs.jsonl` 每行的 `spec` 里记录的字段，即 `SpecRecorder` 在 reset 时导出、回注时再读回的值。
  `<i>` 表示按序号展开，`{a,b}` 表示并列的几个字段。原三档的规格（`native-parity/1`）不受影响。
- **subgoal 流程**：xhard 的任务表（`self.task_list`）与基准档的对照；D 表示演示段（`demonstration=True`），「执行」表示交给策略的段。
  只有 VideoPlaceButton / VideoPlaceOrder 重写了流程，其余要么顺序不变只改某个 subgoal 的等待、名字或失败判定，要么只是次数变。
- **基准**：xhard 是从哪一档派生出来的。标 A6 的三个环境（StopCube、MoveCube、InsertPeg）原来没有 `configs`，
  这次在源码里新建了 easy/medium/hard 三档，三档取值相同，都等于原来的全局常量。

### 1.1 BinFill（基准 hard）

| 新增配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.configs.xhard.spawn_cubes` | `[10,12]` | `[12,12]` |
| `decision.configs.xhard.color` | 3 | 3 |
| `decision.configs.xhard.put_in_numbers` | `[3,5]` | `[5,7]` |
| `decision.configs.xhard.layout_mode` | （沿用顶层 `native_dynamic`） | `clutter` |
| `native.parameters.put_in_color.xhard` | `[2,3]` | `[2,3]` |

**新增规格字段（15 类，按颜色与序号展开后共 24 个）：**
- `layout.mode`：布局模式，xhard 恒为 `clutter`；
- `layout.dynamic`：xhard 固定为 False，不再抽 `randint(0,2)`；
- `layout.cubes.{red,green,blue}_<i>`：每块的位姿；
- `layout.board.offsets`、`layout.button_xy`：板位偏移、按钮位置；
- `objects.spawn_numbers`、`spawn_order`、`spawn_requested`、`spawn_actual`：各色生成数、生成顺序、请求数与实际放下的数；
- `objects.color_pool`、`put_in_color`、`target_numbers`：可选颜色、投入颜色、每色投入数；
- `initializations.<i>.color_order`：每次初始化的颜色顺序。

**行为改动：**
- 12 块开局就全部在场；放不满 12 块，或某个颜色的块数不够投入数，就抛 `SceneGenerationError`；
- layout_mode 守卫只对 xhard 的 clutter 放行；
- `min_gap` 改读 `min_gap_value`，值不变。

**subgoal 流程：** 结构不变，只是次数变。按颜色顺序循环 [`pick up the {序数} {color} cube` → `put it into the bin`]，最后 `press the button`；
pick/put 对的总数 hard `[3,5]` → xhard `[5,7]`（单色最多 7 个，序数用到扩展后的序数表）。failure_func 与 solve 不变。

### 1.2 PickXtimes（基准 hard）

| 新增配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.number_range.xhard` | `[4,5]` | `[6,15]` |
| `decision.color.xhard` | 3 | 3 |
| `decision.xhard.target_cube_position_policy` | — | 区域中心 `[-0.1,0]`、半宽 0.2、`corner_bias: 0.5` |
| `decision.xhard.goal_position_policy` | — | 区域中心 `[-0.1,0]`、半宽 0.2（与方块分开的一套） |
| `decision.xhard.distractor` | — | 颜色 `yellow/cyan/magenta` 各 1 个，放在方块区域内 |

**新增规格字段（19 个）：**
- `layout.cubes.{red,green,blue}_0`：3 个有色方块的位姿；
- `layout.distractors.{yellow,cyan,magenta}_0`：3 个干扰方块的位姿；
- `layout.goal_xy`、`layout.button_xy`：目标盘、按钮位置；
- `layout.cube_corner_bias`：推边角的系数；
- `objects.num_repeats`：重复次数；
- `objects.color_order`、`target_candidates`、`target_color_idx`、`target_cube_idx`：颜色顺序、目标候选、选中的颜色与方块；
- `objects.distractors`：干扰方块列表；
- `objects.cube_count.{requested,actual}`、`objects.distractor_count.{requested,actual}`：请求数与实际放下的数。

**行为改动：**
- 先放圆盘再放方块，圆盘换成外接正方形参与避让（圆盘没有碰撞体，原来会被 `spawn_random_cube` 忽略）；
- 3 个有色方块都往边角推；目标候选池与干扰方块分开；
- 干扰方块进 `non_target_cubes`，抓到即失败；
- num=15 时演示约 2206 步，依赖录像器上限 5000（见第二节）。

**subgoal 流程：** 结构不变，只是次数变。[`pick up the {color} cube for the {序数} time` → `place the {color} cube onto the target`] ×N，
最后 `press the button to stop`；N：hard `[4,5]` → xhard `[6,15]`。任务表代码没改，但 failure_func 读的 `non_target_cubes` / `all_cubes`
在 xhard 下多了 3 个干扰方块，所以抓到干扰方块在每个 pick/place 与按钮 subgoal 上都判失败。

### 1.3 SwingXtimes（基准 hard）

| 新增配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.number_range.xhard` | `[3,3]` | `[4,10]` |
| `decision.color.xhard` | 3 | 3 |
| `decision.xhard.distractor` | — | 颜色 `yellow/cyan/magenta` 各 1 个，区域中心 `[-0.1,0]`、半宽 0.25 |

**新增规格字段（18 个）：** 结构同 PickXtimes（有色方块、干扰方块、按钮、颜色与目标选择、计数），另有：
- `layout.targets.<i>`：两个摆动目标的位置。

**行为改动：**
- `_color_lists` 改成动态建表，避免加第四种颜色时 KeyError；
- 干扰色单列在 `decision.xhard.distractor`，没有并进 `native.color_pool`，否则会改动原三档的随机流；
- 目标候选池与干扰方块分开，干扰方块进非目标列表；圆盘避让同 PickXtimes。

**subgoal 流程：** 结构不变，只是次数变。`pick up the {color} cube` → [`move to the top of the right-side target for the {序数} time` →
`move to the top of the left-side target for the {序数} time`] ×N → `put the {color} cube on the table` → `press the button`；
N：hard 3 → xhard `[4,10]`（总 subgoal 9 → 11～23）。failure_func 不变，干扰方块并入 `non_target_cubes`，抓到即失败。

### 1.4 StopCube（基准 A6）

| 新增配置字段 | hard 值（原全局常量） | xhard 值 |
|---|---|---|
| `decision.xhard.move_interval_choices` | `[60,80,120]` | `[60]`（最快档） |
| `decision.xhard.stop_time_range` | `{low: 2, high_exclusive: 6}`，即 2～5 | `{low: 6, high_exclusive: 16}`，即 6～15 |

**新增规格字段（11 个）：**
- `actions.move_interval`、`move_interval_idx`：移动间隔及其序号；
- `actions.stop_time`、`steps_press`、`stop_window`：停止次数、按键步、停止窗口；
- `actions.motion_segments`、`rotation_deg`：往返段数、路线旋转角；
- `actions.sampling_trace.interval_draw`：原代码那次会被覆盖的间隔抽样（保留以免随机流平移）；
- `layout.button_xy`、`layout.target_xy`、`objects.cube_rgb`：按钮、目标位置和方块颜色。

**行为改动：**
- 往返段数 xhard 取 `max(5, stop_time)`，原三档仍是 5 段；
- `vqa_options._options_stopcube` 的 checkpoint 公式只依赖 `steps_press`，两边自动一致，代码没改。

**subgoal 流程：** 结构不变，只是次数变。`move to the top of the button to prepare` → `remain static` ×K → `press the button to stop the cube on the target`；
K 是每 100 步一个检查点再加最终时刻，hard 1～6 个 → xhard 3～8 个（stop_time 6→3 个、7→4、8～9→5、10～11→6、12～13→7、14～15→8）。

### 1.5 VideoUnmask（基准 hard）

| 新增配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.pick_count.xhard` | 2 | 3 |
| `decision.bin_layout_policy.count.xhard` | 15（实际只放得下 4～8） | 8 |
| `decision.bin_layout_policy.xhard.min_gap_factor` | 2 | 0.75 |
| `decision.xhard.distractor` | — | `count: 3`、`ring_max_abs_xy: [0.2675, 0.45]`、`cube_count_range: [1,2]`、`color_pool: [yellow,cyan,magenta]`、`min_gap_factor: 0.75`、`max_trials: 256` |

**新增规格字段（12 个）：**
- `layout.bins.<i>`：区域容器位姿；
- `layout.bin_count.{requested,placed}`：容器请求数与实际放下的数；
- `objects.color_order`、`n_picks`、`pick_order`：颜色顺序、抓取次数、抓取顺序；
- `objects.distractors.{requested,placed}`：干扰容器请求数与放下的数；
- `objects.distractors.bins.<i>`：干扰容器位姿；
- `objects.distractors.cube_bins`、`cube_colors`、`cube_count`：哪几个干扰容器扣了方块、方块颜色与数量。

**行为改动：**
- pick 改成按次数循环（`_append_xhard_pick_tasks`），`task_goal.py` 加了 pick=3 的文本；
- 干扰容器放在外环（`max(|x|,|y|)` 落在 `[0.2675, 0.45]`、相机可见），存进 `distractor_bins`，不进 `spawned_bins`，也不用 `bin_<i>` 命名；
- 干扰容器与区域容器同一机制、同一窗口 [0,64) 揭示；**误抓（z>0.15）即失败**，加在每个已有 failure_func 上；
- 容器放不满时抛 `SceneGenerationError`。

**subgoal 流程：** 结构不变，只是次数变。

| 档 | 序列 |
|---|---|
| hard | `static`（D，等 64 步）→ `pick up the container that hides the {c0} cube` → `put down the container` → `pick up … {c1} cube` |
| xhard | `static` → pick c0 → [`put down the container` → `pick up … {c_k} cube`] ×2（k=1,2，由 `_append_xhard_pick_tasks` 生成），共 6 个 |

另外所有带 failure_func 的 subgoal 都被外包一层「抬起任一干扰容器即失败」（`utils/unmask_distractors.py`），`static` 不受影响。

### 1.6 ButtonUnmask（基准 hard）

新增配置字段与 VideoUnmask 相同（`pick_count.xhard`、`bin_layout_policy.count.xhard`、`bin_layout_policy.xhard.min_gap_factor`、`decision.xhard.distractor`）。

**新增规格字段（14 个）：** VideoUnmask 的 12 个，另加：
- `layout.button_xy`：按钮位置；
- `actions.sampling_trace.constructor_draw`：构造期那次 `randint(1,6)` 占位抽样。

**行为改动：** 同 VideoUnmask；另外构造期的占位抽样原样保留，首个 pickup 任务的单元素列表形态也保留。按钮区与容器区重叠，放置更紧。

**subgoal 流程：** 同 VideoUnmask，只是开头是 `press the button` 而不是 `static`：
hard `press → pick c0 → put down → pick c1`（4 个）→ xhard `press → pick c0 → [put down → pick c_k] ×2`（6 个）；干扰容器误抓外包同上。

### 1.7 VideoUnmaskSwap（基准 hard，覆盖旧 xhard）

| 新增配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.swap_count_range.xhard` | `[2,3]` | `[8,12]`（旧 xhard `[4,5]` 作废） |
| `decision.pick_count_range.xhard` | `[2,2]` | `[3,3]` |
| `native.parameters.xhard.object_selection.pickup_selected_indices` | `[0,1]` | `[0,1,2]` |
| `decision.xhard.swap_speed_multiplier` | 1 | 1.5，每段 `round(50/1.5)=33` 步，从第 64 步开始 |
| `decision.xhard.distractor` | — | `count: 3`、`with_cube_range: [1,2]`、`ring_half_extent: [0.2675, 0.45]`、`min_gap: 0.04`、`colors: [yellow,cyan,magenta]` |

**新增规格字段（17 个）：**
- `actions.swap_window.{start_step,duration_steps,speed_multiplier}`：交换窗口起点、每段步数、速度倍率；
- `layout.bins.<i>`、`layout.type_choice`：容器位姿、容器类型；
- `layout.distractors.<i>`、`distractors_requested`、`distractors_placed`：干扰容器位姿、请求数与放下的数；
- `objects.n_swaps`、`n_picks`、`selected`、`target_choice`、`color_order`：交换次数、抓取次数、被选中的容器、目标、颜色顺序；
- `objects.swap_initiator_indices`、`swap_initiator_third`：交换发起者；
- `objects.distractors.cube_colors`、`n_with_cube`：干扰方块颜色、扣了方块的干扰容器数。

**行为改动：**
- 交换窗口改用具名常量，按倍率取整；
- 新开交换碰撞检查（初态加连续扫掠），干扰容器也并入检查；
- 交换期等待改用 `solve_hold_obj_xhard`：原共享函数 `solve_hold_obj` 的裸 except 会吞掉碰撞拒绝，导致死循环；
- 揭示规则与误抓即失败同 VideoUnmask。

**subgoal 流程：** 顺序不变，pick 次数 2 → 3，开头 `static` 的等待方式变了。

| 档 | 序列 |
|---|---|
| hard | `static`（D，`solve_hold_obj` 等到最后一段交换结束，164 或 214 步）→ pick c0 → `put down the container` → pick c1 |
| xhard | `static`（D，改用 `solve_hold_obj_xhard`，等 64+33n 步，n∈[8,12] 即 328～460 步）→ pick c0 → [put down → pick c_j] ×2，共 6 个 |

原 hard 分支写死 `pick_times==2`，xhard 另开循环生成；干扰容器误抓外包同 VideoUnmask。

### 1.8 ButtonUnmaskSwap（基准 hard）

| 新增配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.swap_count_range.xhard` | `[2,3]` | `[6,8]` |
| `decision.pick_count_range.xhard` | `[2,2]` | `[3,3]` |
| `native.parameters.bin_count.xhard` | 4 | 4 |
| `decision.xhard.swap_speed_multiplier` | 1 | 1.5（`native.swap_window` 实际消费，为 `{64, 33}`） |
| `decision.xhard.distractor` | — | 同 VideoUnmaskSwap |

**新增规格字段（17 个）：** 同 VideoUnmaskSwap。

**行为改动：**
- `_refresh_swap_schedule` 的三个分支换成通式，并用 `for k in range(3, swap_times)` 补槽位；六处字面量 50 改成具名常量；
- 按完第二个按钮后原地等到最后一段交换结束再去抓（原解法会在容器还在交换时去抓）；
- 碰撞检查、揭示、误抓即失败同 VideoUnmaskSwap。

**subgoal 流程：** 顺序不变，pick 次数 2 → 3，**第二个按钮的 solve 变了**。

| 档 | 序列 |
|---|---|
| hard | `press the first button` → `press the second button` → pick c0 → `put down the container` → pick c1（5 个） |
| xhard | `press the first button` → `press the second button`（solve 换成 `_solve_press_then_wait_swaps`：按完原地等到最后一段交换结束，64+33n 步，n∈[6,8] 即 262～328 步）→ pick c0 → [put down → pick c_j] ×2（7 个） |

等待挂在按钮 subgoal 上而不是 pick 上，是因为 `inject_fail_grasp` 会替换 pick 的 solve。干扰容器误抓外包同 VideoUnmask。

### 1.9 VideoRepick（基准 medium，覆盖旧 xhard）

| 新增配置字段 | medium 值 | xhard 值 |
|---|---|---|
| `decision.xhard.layout` | 三组锚点 | `mode: clutter`、`cube_count: 6`、`region_center: [-0.1, 0]`、`region_half_size: [0.2, 0.25]` |
| `decision.num_repeats_range.xhard` | 死键（实际取 1～3） | `{low: 4, high_exclusive: 7}`，即 4～6，xhard 接上了消费点 |
| `decision.swap.xhard` | `[2,3]` | `{swap_min: 8, swap_max: 12}` |
| `decision.xhard.block_color` | 三块同色，红/蓝/绿 | `policy: same_color_hsv_floor`、`sampler: torch.rand`、`h_range: [0,1]`、`s_range: [0.5,1]`、`v_range: [0.4,1]` |

**新增规格字段（9 个）：**
- `layout.cubes.<i>.xy_yaw`：6 块的位置和朝向；
- `objects.color_rgb`：三块共用的颜色；
- `objects.n_swaps`、`num_repeats`：交换次数、重复次数；
- `objects.target`、`swap_initiators`、`swap_initiators_remaining`：目标块、交换发起者；
- `objects.cube_count.{requested,actual}`：请求数与实际放下的数。

**行为改动：**
- 新方法 `_load_cubes_xhard`：先定颜色，再放 6 块，再选目标和另外 2 个发起者（发起者仍是 3 个）；
- 四处扫掠检查改为「甲通道，或 xhard 乙通道」；
- 交换期等待函数同 VideoUnmaskSwap 的死循环修复；xhard 拒收甲通道的 `episode_spec`；
- 约 45% 的局在演示期被碰撞检查拒绝，按用户决定接受，靠递补补足。

**subgoal 流程：** 结构同 medium，只是次数变、等待函数换了。

| 档 | 序列 |
|---|---|
| medium | `pick up the cube`（D）→ `drop the cube on the table`（D）→ `static`（D，复位后等 20 步）→ `static`（D，swap）×[2,3] → `NO RECORD` → [`pick up the correct cube for the {序数} time` → `put it down`] ×[1,3] → `press the button to finish` |
| xhard | 同上；swap 的 `static` ×[8,12]，repick 对 ×[4,6]；两种 `static` 的等待改用只吞 AttributeError 的修复版（同 VideoUnmaskSwap） |

hard 档没有交换（swap 0），所以没有那组 `static`；failure_func 与名字都不变。

### 1.10 VideoPlaceButton（基准 hard）

| 新增配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.xhard.demo_object_count` | 1 | 2 |
| `decision.xhard.demo_return_policy` | 放到隐藏的 goal_site | `return_to_origin` |
| `decision.targets.xhard` / `swap.xhard` / `additional_place.xhard` | 4 / true / false | 4 / true / false（不变） |
| `native.parameters.color.xhard` | 3 | 3（不变） |

**新增规格字段（14 个）：**
- `layout.cubes.<color>_0`、`layout.goal_xy`、`layout.targets.<i>`、`layout.button_xy`：方块、目标、各台、按钮位置；
- `objects.demo_ids`：演示里放的两块；
- `objects.answer_demo_index`：提问问的是哪一块；
- `objects.task_flag`、`color_order`、`swap_pair_ids`：任务标志、颜色顺序、交换对；
- `actions.target_target_id`：答案台；
- `actions.return_pose_by_object_id.<cube>`：每块放回原位的位姿。

**行为改动：**
- 演示模板改成按对象循环：每块在按钮前放 `targets[2k]`，按一次按钮，再放 `targets[2k+1]`，然后各自放回原位；
- 提问时随机挑一块，问它在按钮前/后放在了哪个台；
- 原位落点由 `utils/xhard_home_site.py::build_home_sites` 在方块初始位姿上直接建（不用 `spawn_random_target`，不消耗随机数）；
- vqa 的 drop 候选追加这两个落点。

**subgoal 流程（重写）：** hard 档 `additional_place=False`，所以原版没有额外放到 target_2/target_3 的那两步。

hard 原流程（1 个方块）：

| # | subgoal | 段 | 做什么 |
|---|---|---|---|
| 1–2 | `pick up the cube` → `drop the cube onto target` | D | 放到 target_0（按钮**前**） |
| 3 | `press the button` | D | 按按钮 |
| 4–5 | `pick up the cube` → `drop the cube onto target` | D | 放到 target_1（按钮**后**） |
| 6–7 | `pick up the cube` → `drop the cube onto table` | D | 放到隐藏的随机 goal_site |
| 8 | `static` | D | 复位后静止 20 步 |
| 9 | `static`（`specialflag=swap`） | D | 静止 60 步，目标台互换 |
| 10 | `NO RECORD` | D | 强复位 |
| 11 | `pick up the cube` | 执行 | 抓目标方块，抓错别的方块即失败 |
| 12 | `place the cube onto the correct target` | 执行 | before → target_0，after → target_1；放错台即失败 |

xhard 新流程（`_load_scene_xhard_tail`，演示方块 A、B，targets 仍是 4 个台）：

| # | subgoal | 段 | 做什么 |
|---|---|---|---|
| 1–2 | `pick up the cube` → `drop the cube onto target` | D | A 放到 targets[0]（按钮前） |
| 3–4 | `pick up the cube` → `drop the cube onto target` | D | B 放到 targets[2]（按钮前） |
| 5 | `press the button` | D | 按按钮 |
| 6–7 | `pick up the cube` → `drop the cube onto target` | D | A 放到 targets[1]（按钮后） |
| 8–9 | `pick up the cube` → `drop the cube onto target` | D | B 放到 targets[3]（按钮后） |
| 10–11 | `pick up the cube` → **`put the cube back to its original position`** | D | A 放回初始位置 |
| 12–13 | `pick up the cube` → **`put the cube back to its original position`** | D | B 放回初始位置 |
| 14 | `static` | D | 静止 20 步（同原版） |
| 15 | `static`（swap） | D | 静止 60 步，目标台互换（同原版） |
| 16 | `NO RECORD` | D | 强复位 |
| 17 | `pick up the cube` | 执行 | 抓**答案方块**（A、B 中随机一个，`objects.answer_demo_index`），抓其他方块即失败 |
| 18 | `place the cube onto the correct target` | 执行 | 放到答案方块按钮前（before）或按钮后（after）放过的台 |

与原版的区别：
- 原来 1 块依次走「按钮前台 → 按钮 → 按钮后台」；现在两块先各放按钮前台，按一次按钮，再各放按钮后台；
- 演示结尾从放隐藏 goal_site（`drop the cube onto table`）改成两块各自放回原位，subgoal 名换成 `put the cube back to its original position`；
- 执行段结构不变，先随机抽问哪一块，再由 task_flag 决定问按钮前还是按钮后；任务目标文本没改。

### 1.11 VideoPlaceOrder（基准 hard）

新增配置字段与 VideoPlaceButton 相同（`demo_object_count: 2`、`demo_return_policy: return_to_origin`，其余不变）。

**新增规格字段（18 个）：** VideoPlaceButton 的 14 个，另加：
- `actions.button_task_index`：按钮插在第几个任务；
- `objects.button_after_visit_index`：按钮在第几次访问之后；
- `objects.which_in_subset`：提问问的是第几个台；
- `objects.num_targets_by_object.<i>`、`visit_ids_by_object.<i>`：每块访问的台数与台序列。

**行为改动：**
- 两块依次各走一遍访问序列，走完放回原位；提问随机挑一块，问它放过的第 N 个台；
- 按钮插入点公式重推为 `2×(b+1+此前已完成的放回原位次数)`，单对象时退化为原来的 `k*2+2`；
- `SceneGenerationError` 被 `from .utils import *` 遮蔽成 TypeError 的问题只在 xhard 修了，原三档仍是 TypeError。

**subgoal 流程（重写）：**

hard 原流程（1 个方块）：

| # | subgoal | 段 | 做什么 |
|---|---|---|---|
| 1…2n | [`pick up the cube` → `drop the cube onto target`] ×n | D | n 取 2～4，按随机顺序访问 n 个台 |
| 插入 | `press the button` | D | 插在第 k 对之后，下标 `k*2+2`，k∈[0,n) 随机 |
| 接着 | `pick up the cube` → `drop the cube onto table` | D | 放到隐藏的 goal_site |
| 接着 | `static` 20 → `static`（swap）60 → `NO RECORD` | D | 同 VideoPlaceButton |
| 最后 | `pick up the cube` → `place the cube onto the correct target` | 执行 | 放到它第 `which_in_subset` 次放过的台 |

xhard 新流程（`_load_scene_xhard_tail` + `_build_xhard_task_list`，演示方块 A、B）：

| # | subgoal | 段 | 做什么 |
|---|---|---|---|
| A 段 | [`pick up the cube` → `drop the cube onto target`] ×n_A | D | A 按自己的随机顺序访问 n_A 个台（2～4） |
| A 回原位 | `pick up the cube` → **`put the cube back to its original position`** | D | A 放回初始位置 |
| B 段 | [`pick up the cube` → `drop the cube onto target`] ×n_B | D | B 访问自己的 n_B 个台（2～4） |
| B 回原位 | `pick up the cube` → **`put the cube back to its original position`** | D | B 放回初始位置 |
| 插入 | `press the button` | D | 插在全局第 b+1 次访问放置之后，b∈[0, n_A+n_B) 随机 |
| 接着 | `static` 20 → `static`（swap）60 → `NO RECORD` | D | 同原版 |
| 最后 | `pick up the cube` → `place the cube onto the correct target` | 执行 | 随机问 A 或 B，放到它自己第 N 次放过的台 |

按钮插点：下标 = `2 × (b + 1 + 此前已完成的放回原位次数)`（`xhard_button_task_index`）。每个单元都是一对 pick+drop，按钮永远不会插在
pick 与 drop 之间；插点恰好是 A 的最后一次访问时，按钮排在 A 放回原位**之前**；只有一个方块时退化为原来的 `k*2+2`。

与原版的区别：
- 两块**串行**演示：A 走完并放回原位后 B 才开始，台面不会被上一块占着；
- 按钮插点从「第 k 对之后」推广成两块全局访问序号；
- 演示结尾从放 goal_site 改成各自放回原位；
- 执行段先随机抽问哪一块，`which_in_subset` 在该块自己的访问序列里抽；任务目标文本没改。

### 1.12 PickHighlight（基准 hard）

| 新增配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.highlight_count.xhard` | 3 | `[5,7]` |
| `decision.spawn_count.xhard` | 6 | `[8,10]` |
| `decision.xhard.block_color_policy` | 红/蓝/绿逐块抽 | `hsv_floor` |
| `decision.xhard.block_color_hsv` | — | `h_range: [0,1]`、`s_range: [0.5,1]`、`v_range: [0.4,1]` |
| `decision.xhard.subgoal_color_suffix` | `, which is {color}` | `omit`（去掉） |

**新增规格字段（7 个）：**
- `layout.cubes.<i>`、`layout.button_xy`：方块、按钮位置；
- `objects.n_cubes`、`n_cubes_spawned`：请求数与实际放下的数；
- `objects.color_rgba.<i>`：每块的颜色；
- `objects.highlight_count`、`highlight_ids`：高亮数与被高亮的块。

**行为改动：**
- 硬断言生成数不少于高亮数；放不满、以及 `randperm[:k]` 截断时，xhard 抛错；
- 首个按钮任务补上 failure_func；`disk_radius` 不动。

**subgoal 流程：** 顺序不变，次数变，名字和第一个 subgoal 的失败判定变了。

| 档 | 序列 |
|---|---|
| hard | `press the button` → [`pick up the {序数} highlighted cube, which is {color}` → `place the cube onto the table`] ×3（最后一块不放回） |
| xhard | `press the button` → [`pick up the {序数} highlighted cube` → `place the cube onto the table`] ×[5,7]（最后一块不放回） |

- pick 的名字与 `subgoal_segment` 去掉 `, which is {color}` 后缀（HSV 任意色没有颜色名）；
- `press the button` 的 failure_func：hard 在构造时就求了值，等于不生效；xhard 包成 lambda，按按钮前抓了任何方块即失败。

### 1.13 MoveCube（基准 A6）

| 新增配置字段 | hard 值（原全局常量） | xhard 值 |
|---|---|---|
| `decision.demo_layout.xhard.corner_bias` | 0（均匀） | 0.5 |
| `decision.execution_layout.xhard.corner_bias` | 0 | 0.5（演示段与执行段各一份） |
| `decision.peg_yaw_range.xhard` | `span_rad: π/2, offset_rad: π/4`，即 ±45° | `span_rad: 2π, offset_rad: π`，即 ±180° |

**新增规格字段（13 个）：**
- `layout.demo.{cube_pose,goal_xy,peg_offsets,peg_yaw,corner_bias}`：演示段的方块、目标、杆位与杆朝向、边角系数；
- `layout.execution.{cube_pose,goal_xy,peg_offsets,peg_yaw,corner_bias}`：执行段同上；
- `initializations.<i>.way_idx`：每次初始化选的推法；
- `objects.obj_sample`、`objects.sampling_trace.dir_sample`：对象与方向抽样。

**行为改动：**
- 等价朝向归约：夹爪 x 轴相对「基座→抓取点」方位角超过 ±90° 时，夹爪姿态右乘 Rz(π)，抓杆后的推杆姿态同步右乘 Rz(π)；
  这段在 `subgoal_planner_func` 里由环境开关 `_xhard_peg_yaw_reduction` 守着，原三档不进这个分支；
- 三种推法都保留。

**subgoal 流程：** 任务表完全不变，三种推法（peg_push 6 个、gripper_push 4 个、grasp_putdown 6 个 subgoal）照旧。
只有执行方式变：`Pick up the peg` 的 `grasp_and_lift_peg_side` 与 `Hook the cube …` 的 `solve_push_to_target_with_peg` 在需要时右乘 Rz(π)（见上）。

### 1.14 InsertPeg（基准 A6）

| 新增配置字段 | hard 值（原全局常量） | xhard 值 |
|---|---|---|
| `decision.xhard.peg_count` | 3 | 4 |
| `decision.xhard.peg_offsets` | `[0.1, 0, -0.1]` | `[0.1, 0, -0.1, -0.2]` |
| `decision.xhard.near_target_distractor` | null | `anchor_peg_index: 0`、`max_center_distance_m: 0.085`（中心距落在 (0.075, 0.085] m） |
| `decision.xhard.peg_yaw_range` | `half_span_deg: 45` | `half_span_deg: 180` |

**新增规格字段（11 个）：**
- `initializations.<i>.pegs.<i>`：每根杆的位姿；
- `initializations.<i>.box_jitter`、`box_yaw`：盒子扰动与朝向；
- `initializations.<i>.obj_sample`、`dir_sample`：对象与方向抽样；
- `initializations.<i>.near_target_distance`、`near_target_attempts`：第 4 根杆到目标杆的中心距、尝试次数；
- `initializations.<i>.peg_placement.{requested,placed}`：请求与放下的杆数；
- `objects.head_rgb`：杆头颜色；
- `objects.sampling_trace.random_peg_idx`：目标杆抽样。

**行为改动：**
- 第 4 根杆单独采样，排在既有抽样之后；原判据一条没改；
- `insert_peg` 在朝向翻转时把夹爪局部系里的平移 xy 取反；
- vqa 候选随杆数从 6 个变成 8 个。

**subgoal 流程：** 任务表完全不变，仍是 6 个：`Pick up the peg by grasping the {near|far} end` → `Insert the peg from the {left|right} side of the box`
→ `NO RECORD`（reset pegs）→ `NO RECORD`（静止 100 步）→ 执行段的 pick 与 insert。执行段「抓了别的杆即失败」的判定现在覆盖 3 根非目标杆（原 2 根）；
朝向翻转时 `insert_peg` 的局部 xy 取反（见上）。

### 1.15 PatternLock（基准 hard）

| 新增配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.grid.xhard` | 5 | 5（布局不改） |
| `decision.path_length_range.xhard` | `[4,8]` | `[20,24]`（原定 25；长度 25 在 1000 次搜索预算内常找不到，会被静默换成长度不对的路径，所以改成 24） |

**新增规格字段（2 个）：**
- `actions.path_nodes`：路径节点序列；
- `actions.path_attempts`：搜到这条路径用了几次尝试。

**行为改动：** 只在源码里加了 `config_xhard`，路径搜索不改。20 个节点约 19.6 s 演示。

**subgoal 流程：** 结构不变，只是次数变。`NO RECORD` → `move {方向}` ×(n−1)（演示）→ `NO RECORD` ×2 → `move {方向}` ×(n−1)（执行）；
n：hard 4～8 → xhard 20～24，总 subgoal 9～17 → 41～49。

### 1.16 RouteStick（基准 hard，覆盖旧 xhard）

**新增配置字段：** 无。xhard 值写在源码 `RouteStick.py` 的 `config_xhard` 里：`length` `[4,7]`→`[12,15]`（旧 xhard `[8,10]` 作废），`backtrack` 仍为 True。

**新增规格字段（5 个）：**
- `objects.L`：段数；
- `actions.nodes`、`actions.directions.<i>`：走过的节点与每段方向；
- `layout.rotation_deg`、`layout.obstacle_rgb.<i>`：网格旋转角、障碍物颜色。

**行为改动：** 只改了 `config_xhard`。演示 L×50 帧，即 600～750 帧，约 20～25 s。

**subgoal 流程：** 结构不变，只是次数变。`NO RECORD` → `move to the nearest {left|right} target by circling around the stick {方向}` ×L（演示）
→ `NO RECORD` ×2 → 同名 move ×L（执行）；L：hard 4～7 → xhard 12～15，总 subgoal 11～17 → 27～33。

---

## 第二节　全局改动

### 2.1 代码

| 位置 | 改了什么 |
|---|---|
| `utils/episode_spec.py::SpecRecorder`、`spec_kind_for` | 新增规格类别：xhard 局标 `native-newvalue/1`，原三档标 `native-parity/1`，两类规格不许互喂；`value(..., decision_key=)` 把取值点归因到配置键 |
| `utils/sampling_config.py::assert_native_decision` | 守卫：去掉所有 `xhard` 键之后，其余部分必须与原值全等；xhard 子树只能改值，键结构必须与源码里申报的一致 |
| `utils/xhard.py`（新增） | `DISTRACTOR_COLORS`（黄/青/品红干扰色池）、`corner_push`（推边角）、`HSV_FLOOR_COLOR` 与 `hsv_floor_rgb`（HSV 限定色） |
| `utils/object_generation.py` | 新增参数 `corner_bias`，默认 0，此时行为与原来逐字相同 |
| `utils/subgoal_language.py` | 序数表扩到 20 |
| `utils/unmask_distractors.py`、`unmask_swap_xhard.py`、`xhard_home_site.py`（新增） | Unmask 的外环干扰容器与误抓判定、Swap 的 xhard 等待与碰撞检查、VideoPlace 的原位落点 |
| `subgoal_planner_func.py` | MoveCube 的朝向归约，由 `_xhard_peg_yaw_reduction` 开关守着 |
| `RecordWrapper.py` | `fail_safe_limit` 2000→5000。录像器只有这一处改动，其余仍冻结 |
| `scripts/parity/train_split_runner.py` | 新增 `--identity-source formula`（按 V4 seed 公式硬校验）、`--no-recovery` |
| `scripts/parity/train_split_worker.py` | 任务元组第 4 项 `disable_recovery` |
| `env_record_wrapper/episode_config_resolver.py` | 新增 `from_v4_specs`，见第三节 |

两条全局规则：**新增的随机抽样一律排在既有抽样之后**，原三档的随机流因此不受影响；**V4 的抽签、实跑、推理全部不开 fail recover。**

### 2.2 快照 `specs.jsonl` 的字段（新增文件）

第一行是 header，其余每行一条候选。

**header 字段：**

| 字段 | 含义 |
|---|---|
| `schema` | `v4-specs/1` |
| `record` | 固定为 `header` |
| `run_id` | 快照编号，如 `v4-01` |
| `difficulty` | 固定为 `xhard` |
| `tasks` | 十六个环境的规范顺序 |
| `sampling_config`、`sampling_config_sha256` | 抽签时用的配置全文及其散列 |
| `source_fingerprint` | 源码指纹：`files`（文件数）、`sha256` |
| `runtime` | `obs_mode` / `control_mode` / `render_mode` / `reward_mode` 四项，推理时逐字比对 |
| `seed_rule` | `offset: 4000000`、`env_block: 100000`、`episode_stride: 100`，公式 `offset + env_code*env_block + episode*100 + attempt` |
| `identity_source` | 固定为 `formula` |
| `recovery_rule` | V4 全部不开 fail recover |
| `select_indices` | 冻结时每个环境选中的候选序号，默认 `[0,3,6]` |
| `per_env` | 每个环境的 `attempted`（尝试数）、`candidates`（成功候选数）、`candidate_shortfall`、`selected` |
| `drafts_sha256` | 来源 `drafts.jsonl` 的散列 |
| `identity_sha256` | 整个快照的身份散列；计算时剔除 `selected` 等管理字段，所以重标 `selected` 不会改变它 |

**候选行字段：**

| 字段 | 含义 |
|---|---|
| `record` | 固定为 `spec` |
| `task`、`difficulty`、`episode`、`attempt`、`seed` | 身份；`episode` 就是候选序号 |
| `selected` | 是否为正式局 |
| `spec` | 规格本体：`spec_kind`（`native-newvalue/1`）、`task`、`identity`（task/difficulty/episode/seed/recovery_mode）、`provenance`（导出时的 `mode`、`value_points`、`mismatches`）、以及第一节列出的 `layout` / `objects` / `actions` / `initializations` 字段 |
| `spec_sha256` | 该条规格的散列，结果文件按它 join |

### 2.3 实跑结果的字段（新增文件）

**`results.jsonl`（每局一行）：**

| 字段 | 含义 |
|---|---|
| `task`、`difficulty`、`episode`、`attempt`、`seed`、`spec_sha256` | 身份 |
| `run_label` | 本轮标签，如 `run1` |
| `role` | `selected`（正式局）或 `backfill`（递补局） |
| `round` | 第几轮（0 为正式局，之后是递补轮） |
| `ok` | 演示是否成功 |
| `error_type`、`error` | 失败类别与信息 |
| `h5` | h5 文件路径 |
| `spec_binding` | `value_points`、`mismatch`、`unattributed_mismatch`、`unused`：规格是否被原样消费 |

**`summary.json`：** `specs`、`identity_sha256`、`label`，以及 `per_env` 下每个环境的 `attempted`、`ok`、`backfilled`（递补数）、`selected_shortfall`（没凑满的正式局数）。

**每局目录 `episodes/<task>_episode_<n>/`：** `hdf5_files/`、`videos/`、`rng_trace.json`（每个取值点的 `path` / `drawn` / `source`）、`spec_replay.json`（`value_points` / `consumed` / `unused` / `mismatches`）。

### 2.4 推理结果的字段（新增文件）

**`eval_results.jsonl`（每局一行）：**

| 字段 | 含义 |
|---|---|
| `task`、`difficulty`、`episode`、`seed`、`spec_sha256` | 身份，可与 `results.jsonl` 直接 join |
| `run_id` | 本次推理编号 |
| `status`、`steps`、`wall_s` | 终态（取自 `info["status"]`）、步数、墙钟秒数 |
| `policy_id`、`policy_sha256`、`model_seed` | 策略标识、策略指纹、模型种子 |
| `action_space`、`max_steps` | 动作空间、步数上限 |
| `runtime_ok` | runtime 四项是否与快照一致 |
| `spec_binding` | `available`、`mode`、`mismatch`、`unattributed_mismatch`、`unused` |
| `error_type`、`error` | 异常信息 |

**`eval_summary.json`：** `specs_identity_sha256`、`per_task`（每个环境的 `avg_success` / `success_count` / `num_episodes`）、`overall`（同样三项）。字段名与 `challenge_interface` 的 `metrics.json` 对齐。

---

## 第三节　推理侧怎么兼容

1. **构建器加了一条并列路径。** [episode_config_resolver.py](../src/robomme/env_record_wrapper/episode_config_resolver.py) 里的
   `BenchmarkEnvBuilder.from_v4_specs(env_id, header, specs_by_identity, ...)`：episode 号就是候选序号，
   seed、difficulty、`sampling_config`、`native_episode_spec` 全部取自快照，统一经 `gym.make` 传进环境。
   `resolve_episode`、`get_episode_num`、建环境三处在 `self._v4` 不为 None 时走快照；`self._v4 is None` 时（原来的 metadata 路径）行为逐字不变。
   `scripts/evaluation.py` 一行没改。
2. **runtime 必须一致。** 快照 header 里的 `runtime` 四项与构建器参数有一项不相等，就直接拒绝起环境。
3. **构建器本身不读文件。** 调用方先用 `scripts/parity/v4_specs.py::load_specs` 校验封套（header 来源、每行 `spec_sha256`、
   整文件 `identity_sha256`），拿到 `(header, sampling_by_task, specs_by_identity)`（只含 `selected=true` 的行）再交给构建器。
4. **每局结束都核验规格绑定。** 读 `env.unwrapped._spec`，统计 `missing` / `unused` / `mismatch` 写进 `eval_results.jsonl`；
   每行都能按 `(task, difficulty, episode, seed, spec_sha256)` 与生成侧的 `results.jsonl` 直接 join。
5. **推理要用重标后的快照 `specs.selected.jsonl`，不要用 `specs.jsonl`。** 冻结时初选的局可能在实跑中演示失败、被递补替换
   （如 InsertPeg 初选的 0/3/6 全部失败，递补上来的是 4/5）；用原快照评这类局时，reset 期重放示范会卡死。
   `reselect` 只改 `selected` 标记，header 与规格值一字不动，`identity_sha256` 也不变。

---

## 第四节　三步各自怎么调用

正式快照 `v4-01` 在 [configs/newtask-v4/v4-01/](configs/newtask-v4/v4-01/)，已进 Git。以下命令都在仓库根目录执行。

### 4.1 第一步：抽签与冻结（[parity/v4_specs.py](parity/v4_specs.py)）

```bash
uv run --no-sync python -m scripts.parity.v4_specs draw --run-id v4-01 --candidates-per-env 10 --max-reset-attempts 30 --out artifacts/newtask-v4/v4-01/draft/drafts.jsonl
```

```bash
uv run --no-sync python -m scripts.parity.v4_specs freeze --drafts artifacts/newtask-v4/v4-01/draft/drafts.jsonl --out scripts/configs/newtask-v4/v4-01/specs.jsonl
```

- `draw` 占 GPU，只做 reset、不 step、不录像。每个环境攒够 `--candidates-per-env` 条成功，或者试满 `--max-reset-attempts` 次为止；
  每次尝试（包括失败的）都写进 `drafts.jsonl`。header 在抽签时就封存配置全文、源码指纹、runtime、seed 规则和 recover 规则。
  可以用 `--tasks` 限定环境，`--sampling-config` 换配置文件。
- `freeze` 只用 CPU：先核验 header 封存的来源与当前磁盘逐项一致，不一致就拒绝；然后只保留 reset 成功的行，
  每个环境按 `--select`（默认 `0,3,6`）标 `selected=true`，写出 `specs.jsonl`。目标文件已存在时拒绝覆盖。

### 4.2 第二步：实跑（[parity/v4_rollout.py](parity/v4_rollout.py)）

```bash
uv run --no-sync python -m scripts.parity.v4_rollout run --specs scripts/configs/newtask-v4/v4-01/specs.jsonl --label run1 --workers 12 --official-root artifacts/train-parity/local-smoke-01/official-src --output artifacts/newtask-v4/v4-01/rollout
```

```bash
uv run --no-sync python -m scripts.parity.v4_specs reselect --specs scripts/configs/newtask-v4/v4-01/specs.jsonl --results artifacts/newtask-v4/v4-01/rollout/run1/results.jsonl --out scripts/configs/newtask-v4/v4-01/specs.selected.jsonl
```

- `run` 先跑每个环境 `selected=true` 的正式局。某局演示失败时，在本环境剩下的候选里按 `1,2,4,5,7,8,9` 的顺序递补，
  直到凑满或者候选用完；不追加抽签，失败局照样留在分母里。每局的 h5 和视频落在 `<output>/<label>/episodes/`，
  汇总在 `results.jsonl` 和 `summary.json`。调用链是 `train_split_runner.py --identity-source formula --no-recovery`
  → `train_split_worker.run_one`。
- 实跑完成后用 `reselect` 按成功局重标 `selected`，推理用它输出的这份快照。
- 可选的重放检查：`run --label run2 --identities-from <run1/results.jsonl>` 严格重放第一遍跑过的全部身份，
  再用 `compare <run1目录> <run2目录> --report-only` 对比。多 worker 下 RRT 的墙钟预算随负载变化，两遍之间允许少量不同，所以结果只作报告。

### 4.3 第三步：推理（[eval/v4_eval.py](eval/v4_eval.py)）

```bash
uv run --no-sync python -m scripts.eval.v4_eval --specs scripts/configs/newtask-v4/v4-01/specs.selected.jsonl --max-steps 1300 --join-results artifacts/newtask-v4/v4-01/rollout/run1/results.jsonl --out artifacts/newtask-v4/v4-01/eval-all
```

- 逐局边跑边写 `eval_results.jsonl`，全部跑完写 `eval_summary.json`。给了 `--join-results` 时，收尾按身份与生成侧 join，
  并打印 `EVAL_PIPELINE=...` 判定行。
- 可选参数：`--tasks` 限定环境，`--limit-per-task` 限定每个环境评几局，`--action-space` 默认 `joint_angle`，`--model-seed` 默认 7。
- 默认策略是 `DummyModel`，与 `scripts/evaluation.py` 里的同构，只用来验证链路；换成真实策略时替换 `v4_eval.py` 里的模型类即可。
