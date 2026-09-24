# scripts/ 说明：V4/V5 xhard 档

**V4 与 V5 的关系**：V5 是在 V4 xhard 档之上的第二轮修订（xhard 去扎堆、四个 Unmask 环境的干扰容器加密且 Swap 两环境的外环随内环同步交换、
PatternLock/RouteStick 演示时长校准、放下的方块作障碍时 2D 包围框退化的缺陷修复），**只改 xhard 档**。V4 已作废：
V4 的配置 `scripts/configs/newtask-v4/` 与产物 `artifacts/newtask-v4/` 原样留档、不再引用，v4-01 的规格在 V5 代码上被拒是预期。

- V5 计划：[NEWTASK_RELEASE_V5_PLAN.md](../NEWTASK_RELEASE_V5_PLAN.md)（1.4 决策 L1～L54、第二节逐环境改动、第三节对拍与 runbook）；
- V5 逐步实施报告：[docs/validation/newtask-v5/](../docs/validation/newtask-v5/)（S2a/S2b/S2c 共用设施，S3a～S3i 各环境，工具链）；
- V4 计划与总报告：[NEWTASK_RELEASE_V4_PLAN.md](../NEWTASK_RELEASE_V4_PLAN.md)、[V4 总报告](../docs/validation/newtask-v4/20260923-v4-final-report.md)（验证数字、决策来由和风险）。

本文讲五件事：

1. **逐环境改动**：十六个环境 xhard 档各自的配置字段、规格字段、行为与 subgoal 执行流程（第一节）。**一律以 V5 现行代码为准**，
   V4 的取值只在对照时保留，写作「V4 原值 …」；
2. **全局改动**：共用代码、快照文件、结果文件里新增了哪些字段（第二节，V4 表 + V5 追加表）；
3. **推理侧怎么兼容**（第三节，V5 沿用同一路径）；
4. **三步各自怎么调用**：抽签与冻结、实跑、推理（第四节；V4 命令原样保留，每步另注 V5 对应路径）；
5. **V5 怎么调用**：快照重导、一条命令串起抽签/冻结/实跑/报告、V1 原三档逐位对拍（第五节）。

V5 改动范围（计划 2.1 总表）：

| 类别 | 环境 |
|---|---|
| 改规则与字段（12 个） | BinFill、PickXtimes、SwingXtimes、VideoUnmask、ButtonUnmask、VideoUnmaskSwap、ButtonUnmaskSwap、VideoRepick、MoveCube、InsertPeg、PatternLock、RouteStick |
| 只修方块障碍框（配置与规格字段不变） | PickHighlight、VideoPlaceButton、VideoPlaceOrder |
| 只修异常类 | StopCube |

新值**只挂在 `self.difficulty == "xhard"` 分支上**（或默认关闭的新参数上），原三档（easy/medium/hard）的定义、reset 取值、完整演示产物都与改动前逐位相同；
V5 由 V0 静态检查（`config_easy/medium/hard` 与原三档消费的 `NATIVE_SAMPLING` 零改动）与 V1 的 144 条 h5 逐位对拍（5.4）守住。

---

## 第一节　逐环境改动

**怎么读：**

- **配置字段**：写在 [configs/newtask-v5/sampling_config.json](configs/newtask-v5/sampling_config.json) 里（V4 为
  [configs/newtask-v4/sampling_config.json](configs/newtask-v4/sampling_config.json)），路径相对于 `tasks.<环境>`。
  「hard 值」一列是原值，用来对照；「xhard 值」一列是 V5 现值，V5 改过的在括号里注明 V4 原值；键名本来就有、只是新加了 `xhard` 档的，也列在这里。
  这份快照由源码（各环境的 `config_xhard` / `XHARD_*` 常量 / `_native_decision`）一次性导出（5.1），两者不一致时以源码为准。
- **规格字段**：该环境 xhard 局在 `specs.jsonl` 每行的 `spec` 里记录的字段，即 `SpecRecorder` 在 reset 时导出、回注时再读回的值。
  `<i>` 表示按序号展开，`{a,b}` 表示并列的几个字段。value 点是回放时会被冻结值替换的取值点，record 点只留痕。原三档的规格（`native-parity/1`）不受影响。
- **subgoal 流程**：xhard 的任务表（`self.task_list`）与基准档的对照；D 表示演示段（`demonstration=True`），「执行」表示交给策略的段。
  只有 VideoPlaceButton / VideoPlaceOrder 重写了流程，其余要么顺序不变只改某个 subgoal 的等待、名字或失败判定，要么只是次数变。**V5 没有改任何环境的任务表结构**，只有次数随取值范围变化（PatternLock、RouteStick）。
- **基准**：xhard 是从哪一档派生出来的。标 A6 的三个环境（StopCube、MoveCube、InsertPeg）原来没有 `configs`，
  V4 在源码里新建了 easy/medium/hard 三档，三档取值相同，都等于原来的全局常量。
- **V5 的跨环境改动**（计划 2.0，各环境不再重复）：
  - **方块障碍框精确化**：`spawn_random_cube` / `spawn_random_target` 把 `avoid` 里的方块 actor 转成 2D 障碍框时，正方体的竖直轴可能落进前两列，
    障碍框退化成一条 4 cm 线段，`min_gap` 在其法向失效。V5 在 xhard 分支里改把已放方块以 `utils/xhard.py::cube_obb2d_exact` 的精确三元组放进 `avoid`
    （BinFill、PickXtimes、SwingXtimes、VideoRepick、PickHighlight、VideoPlaceButton、VideoPlaceOrder；MoveCube 改为执行段不避让演示段方块，结构上不再有方块障碍）。
  - **`SceneGenerationError` 遮蔽修复**：7 个模块（VideoRepick、SwingXtimes、PatternLock、RouteStick、StopCube、VideoUnmaskSwap（下文简称 VUS）、ButtonUnmaskSwap（BUS））的 `SceneGenerationError`
    被 `from .utils import *` 覆盖成子模块，`raise` 实际抛 TypeError。V5 在模块头加 `_RealSceneGenerationError` 别名与 `_scene_gen_error(difficulty)`，
    xhard 抛真类（可重试），原三档仍是 TypeError。
  - **回放复核（N17）**：带几何保证的环境在回注冻结规格时重新核验规则（间距、禁区、路径合法性等），违反抛 `EpisodeSpecError`；
    带整段重抽的采样器只在被接受的那次调用 `recorder.value`，尝试次数用 `record()` 留痕（N18）。

### 1.1 BinFill（基准 hard）

> V5：修方块障碍框退化 + 同色成团上限（报告 [S3e](../docs/validation/newtask-v5/20260924-s3e-binfill.md)，计划 2.12）。

| 配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.configs.xhard.spawn_cubes` | `[10,12]` | `[12,12]` |
| `decision.configs.xhard.color` | 3 | 3 |
| `decision.configs.xhard.put_in_numbers` | `[3,5]` | `[5,7]` |
| `decision.configs.xhard.layout_mode` | （沿用顶层 `native_dynamic`） | `clutter` |
| `decision.configs.xhard.color_mix`（V5 新增） | — | `max_component: 3`、`link_m: 0.09`、`max_redraws: 64` |
| `native.parameters.put_in_color.xhard` | `[2,3]` | `[2,3]` |

**规格字段：**
- `layout.mode`：布局模式，xhard 恒为 `clutter`；
- `layout.dynamic`：xhard 固定为 False，不再抽 `randint(0,2)`；
- `layout.slots.<k>`（V5 新增，value，k=0..11，`[x, y, yaw]`）：12 个槽位的几何位置；
- `objects.slot_assignment`（V5 新增，value）：槽位 k 放哪一块，12 个 `<颜色>_<色内序号>`（如 `red_3`），与 actor 名 `cube_<身份>` 对应；
- `objects.color_redraws`、`color_mix_fallback`、`color_mix_max_component`（V5 新增，record）：配色重排次数、是否走了兜底、最终最大同色团块数；
- `layout.cubes.{red,green,blue}_<i>`：每块的位姿；V4 是 value 点，V5 改为 record（由槽位与配色派生）；
- `layout.board.offsets`、`layout.button_xy`：板位偏移、按钮位置；
- `objects.spawn_numbers`、`spawn_order`、`spawn_requested`、`spawn_actual`：各色生成数、生成顺序、请求数与实际放下的数；
- `objects.color_pool`、`put_in_color`、`target_numbers`：可选颜色、投入颜色、每色投入数；
- `initializations.<i>.color_order`：每次初始化的颜色顺序。

相对 V4：value 点从「12 个 `layout.cubes`」变为「12 个 `layout.slots` + 1 个 `slot_assignment`」，另加 3 个 record 点。

**行为改动：**
- 12 块开局就全部在场；放不满 12 块，或某个颜色的块数不够投入数，就抛 `SceneGenerationError`；
- layout_mode 守卫只对 xhard 的 clutter 放行；`min_gap` 改读 `min_gap_value`，值不变；
- **V5：方块生成改为三段式 `_spawn_cubes_xhard`**（xhard 且未注入旧 `episode_spec` 时；原循环原样留在 `else`）：
  1. **槽位**：与 `spawn_random_cube` 同一拒绝抽样（每块 256 次，`min_gap=0.02`），障碍 = 按钮 OBB + 孔板四条边 + 已放槽位的**精确** OBB
     （V4 走 actor 路径，障碍框退化后 23.3% 的方块离最近邻不到 2 cm）；放不下立即抛 `SceneGenerationError`；
  2. **配色**：最大同色连通团（同色且中心距 ≤ 0.09 m 即相连）超过 3 块时，每次对初始配色做一次独立的 `randperm(12)` 重排，
     最多 64 次，都不满足就取团最小的一次（`color_mix_fallback`）；位置不动；
  3. **建 actor**：按槽位用固定位姿建方块，不再抽随机数；
- **V5 回放复核**：冻结槽位必须在区域内、外扩 0.02 后不与按钮/孔板/已放槽位相交；`slot_assignment` 必须是本局方块的一个排列，且最大同色团不劣于实算最优；否则 `EpisodeSpecError`。

**subgoal 流程：** 结构不变，只是次数变。按颜色顺序循环 [`pick up the {序数} {color} cube` → `put it into the bin`]，最后 `press the button`；
pick/put 对的总数 hard `[3,5]` → xhard `[5,7]`（单色最多 7 个，序数用到扩展后的序数表）。failure_func 与 solve 不变。

### 1.2 PickXtimes（基准 hard）

> V5：取消边角偏置、6 块两两 ≥ 0.08 m、精确 OBB、每块 1024 次（报告 [S3f](../docs/validation/newtask-v5/20260924-s3f-pickxtimes-swingxtimes.md)，计划 2.13）。

| 配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.number_range.xhard` | `[4,5]` | `[6,15]` |
| `decision.color.xhard` | 3 | 3 |
| `decision.xhard.target_cube_position_policy` | — | 区域中心 `[-0.1,0]`、半宽 **0.25**，均匀抽（V4 原值：半宽 0.2、`corner_bias: 0.5`；V5 删掉 `corner_bias` 键） |
| `decision.xhard.goal_position_policy` | — | 区域中心 `[-0.1,0]`、半宽 0.2（与方块分开的一套，V5 不变） |
| `decision.xhard.distractor` | — | 颜色 `yellow/cyan/magenta` 各 1 个，区域中心 `[-0.1,0]`、半宽 **0.25**（V4 原值 0.2） |
| `decision.xhard.min_center_dist_m`（V5 新增） | — | 0.08（3 个有色 + 3 个干扰共 6 块两两中心距下限） |

另有模块常量 `XHARD_CUBE_MAX_TRIALS = 1024`（6 块每块的拒绝预算），不进 decision。

**规格字段（19 个）：**
- `layout.cubes.{red,green,blue}_0`：3 个有色方块的位姿；
- `layout.distractors.{yellow,cyan,magenta}_0`：3 个干扰方块的位姿；
- `layout.goal_xy`、`layout.button_xy`：目标盘、按钮位置；
- `layout.cube_min_center_dist`（V5 新增，record，恒 0.08）：两两中心距下限；**V4 的 `layout.cube_corner_bias` 已删除**；
- `objects.num_repeats`：重复次数；
- `objects.color_order`、`target_candidates`、`target_color_idx`、`target_cube_idx`：颜色顺序、目标候选、选中的颜色与方块；
- `objects.distractors`：干扰方块列表；
- `objects.cube_count.{requested,actual}`、`objects.distractor_count.{requested,actual}`：请求数与实际放下的数。

**行为改动：**
- 先放圆盘再放方块，圆盘换成外接正方形参与避让（圆盘没有碰撞体，原来会被 `spawn_random_cube` 忽略）；
- **V5**：3 个有色方块在半宽 0.25 的区域里**均匀**抽（取消 V4 的边角偏置）；有色与干扰方块共用一张表，经
  `spawn_random_cube(max_trials=1024, min_center_dist=(0.08, 已放方块))` 保证两两中心距 ≥ 0.08；已放方块以精确 OBB 同时进 `avoid` 与中心距参考点集；
  抽样顺序（按钮 → 颜色 → 圆盘 → 3 有色 → 选目标 → 3 干扰）不变，只是每块 trial 次数变；
- 目标候选池与干扰方块分开；干扰方块进 `non_target_cubes`，抓到即失败；
- num=15 时演示约 2206 步，依赖录像器上限 5000（见第二节）。

**subgoal 流程：** 结构不变，只是次数变。[`pick up the {color} cube for the {序数} time` → `place the {color} cube onto the target`] ×N，
最后 `press the button to stop`；N：hard `[4,5]` → xhard `[6,15]`。任务表代码没改，但 failure_func 读的 `non_target_cubes` / `all_cubes`
在 xhard 下多了 3 个干扰方块，所以抓到干扰方块在每个 pick/place 与按钮 subgoal 上都判失败。

### 1.3 SwingXtimes（基准 hard）

> V5：共用循环加显式 xhard 分支、6 块两两 ≥ 0.08 m、精确 OBB（报告 [S3f](../docs/validation/newtask-v5/20260924-s3f-pickxtimes-swingxtimes.md)，计划 2.14）。

| 配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.number_range.xhard` | `[3,3]` | `[4,10]` |
| `decision.color.xhard` | 3 | 3 |
| `decision.xhard.distractor` | — | 颜色 `yellow/cyan/magenta` 各 1 个，区域中心 `[-0.1,0]`、半宽 0.25 |
| `decision.xhard.min_center_dist_m`（V5 新增） | — | 0.08 |

**规格字段（19 个）：** 结构同 PickXtimes（有色方块、干扰方块、按钮、颜色与目标选择、计数、`layout.cube_min_center_dist`），另有：
- `layout.targets.<i>`：两个摆动目标的位置。

**行为改动：**
- `_color_lists` 改成动态建表，避免加第四种颜色时 KeyError；
- 干扰色单列在 `decision.xhard.distractor`，没有并进 `native.color_pool`，否则会改动原三档的随机流；
- 目标候选池与干扰方块分开，干扰方块进非目标列表；圆盘避让同 PickXtimes；
- **V5**：`_load_scene` 里三档共用的有色方块循环外包显式分支——xhard 走新方法 `_spawn_colored_cubes_xhard`，原三档 `else` 里原循环逐字保留；
  xhard 有色方块与干扰方块两两中心距 ≥ 0.08、精确 OBB 登记（两个圆盘也因此按方块真实朝向避让），区域、间距、预算（256）与原循环相同；
  放不下抛真 `SceneGenerationError`（V4 在这里实际抛的是被遮蔽的 TypeError）。

**subgoal 流程：** 结构不变，只是次数变。`pick up the {color} cube` → [`move to the top of the right-side target for the {序数} time` →
`move to the top of the left-side target for the {序数} time`] ×N → `put the {color} cube on the table` → `press the button`；
N：hard 3 → xhard `[4,10]`（总 subgoal 9 → 11～23）。failure_func 不变，干扰方块并入 `non_target_cubes`，抓到即失败。

### 1.4 StopCube（基准 A6）

> V5：配置字段、规格字段、行为与 subgoal 流程都不变，**只修异常类**：S2a 在模块头加了 `_RealSceneGenerationError` 别名与 `_scene_gen_error(difficulty)`
> （计划 2.0③、L3）。核对结果是 StopCube 全文没有 `raise` 与 `except`（方块用 `spawn_fixed_cube`，不走会抛错的 `spawn_random_cube`），xhard 路径没有新增抛错点，
> 所以别名只是为今后在 xhard 路径上抛错备用（报告 [S3i](../docs/validation/newtask-v5/20260924-s3i-obb-fix-pickhighlight-videoplace.md) 第三节）。

| 配置字段 | hard 值（原全局常量） | xhard 值 |
|---|---|---|
| `decision.xhard.move_interval_choices` | `[60,80,120]` | `[60]`（最快档） |
| `decision.xhard.stop_time_range` | `{low: 2, high_exclusive: 6}`，即 2～5 | `{low: 6, high_exclusive: 16}`，即 6～15 |

**规格字段（11 个）：**
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

> V5：干扰容器 3 → 15、贴身环带、接入四个 Unmask 共用的统一采样器，揭示时各容器停独立点（报告 [S3b](../docs/validation/newtask-v5/20260924-s3b-videounmask-buttonunmask.md)、
> 共用设施 [S2c](../docs/validation/newtask-v5/20260924-s2c-unmask-distractor-sampler.md)，计划 2.2、2.3）。

| 配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.pick_count.xhard` | 2 | 3 |
| `decision.bin_layout_policy.count.xhard` | 15（实际只放得下 4～8） | 8 |
| `decision.bin_layout_policy.xhard.min_gap_factor` | 2 | 0.75 |
| `decision.xhard.distractor` | — | 统一 7 键：`count: 15`、`ring_max_abs_xy: [0.2425, 0.3289]`、`cube_count_range: [7,8]`、`color_pool: [yellow,cyan,magenta]`、`color_rule: balanced_cycle`、`min_gap_factor: 0.75`、`max_trials: 1024`（V4 原值：3 个、`[0.2675, 0.45]`、`[1,2]`、256 次，无 `color_rule`） |

**规格字段：**
- `layout.bins.<i>`：区域容器位姿；
- `layout.bin_count.{requested,placed}`：容器请求数与实际放下的数；
- `objects.color_order`、`n_picks`、`pick_order`：颜色顺序、抓取次数、抓取顺序；
- 干扰容器（统一 schema，前缀 `objects.distractors`）：
  - `bins.<i>`（value，`[x, y, yaw_deg]`）：干扰容器位姿；
  - `cube_count`（value）、`cube_bins`（value）：扣了方块的干扰容器个数、每个方块在哪个容器里；
  - `color_order`（V5 新增，value，`randperm(3)`）：方块颜色轮转的起始顺序；
  - `requested`、`placed`（record）：请求数与放下的数；`trials`（V5 新增，record）：每个容器用掉的尝试次数；
  - `cube_colors`（record）：方块颜色；`cube_names`（V5 新增，record）：方块 actor 名。

**行为改动：**
- pick 改成按次数循环（`_append_xhard_pick_tasks`），`task_goal.py` 加了 pick=3 的文本；
- 干扰容器存进 `distractor_bins`，不进 `spawned_bins`，也不用 `bin_<i>` 命名；**误抓（z>0.15）即失败**，加在每个已有 failure_func 上；
- 容器放不满时抛 `SceneGenerationError`；
- **V5：干扰容器改由统一采样器 `utils/unmask_distractor_sampler.py::spawn_distractor_layout` 放置**：15 个放在贴身环带（`max(|x|,|y|)` 落在
  `[0.2425, 0.3289]`，V4 是 `[0.2675, 0.45]` 的外环），其中 7～8 个扣方块，方块颜色按黄/青/品红三色平衡轮转；仍排在全部既有取值点之后，
  所以内环取值与 V4 同 seed 相同；
- **V5：揭示时各容器停独立点**。揭示窗口仍是 [0,64)、落回时刻不变，但被抬起的内环 8 个容器（`group="bin"`）与干扰容器
  （`distractor_bin`）各自停到 `xhard_park_point(group, i)`（原点 `(20, 20, 10)`、间距 0.5 m），不再全部叠在 `(10,10,10)`；
  原三档的揭示循环原样搬进 `else`。

**subgoal 流程：** 结构不变，只是次数变。

| 档 | 序列 |
|---|---|
| hard | `static`（D，等 64 步）→ `pick up the container that hides the {c0} cube` → `put down the container` → `pick up … {c1} cube` |
| xhard | `static` → pick c0 → [`put down the container` → `pick up … {c_k} cube`] ×2（k=1,2，由 `_append_xhard_pick_tasks` 生成），共 6 个 |

另外所有带 failure_func 的 subgoal 都被外包一层「抬起任一干扰容器即失败」（`utils/unmask_distractors.py`），`static` 不受影响。

### 1.6 ButtonUnmask（基准 hard）

> V5：同 VideoUnmask，干扰容器 14 个（报告 [S3b](../docs/validation/newtask-v5/20260924-s3b-videounmask-buttonunmask.md)，计划 2.4）。

配置字段与 VideoUnmask 相同（`pick_count.xhard`、`bin_layout_policy.count.xhard`、`bin_layout_policy.xhard.min_gap_factor`、`decision.xhard.distractor`），
只是 `distractor.count: 14`、`cube_count_range: [7,7]`（按钮挡住环带约 5.7%），其余 5 键同 VideoUnmask（V4 原值同 VideoUnmask）。

**规格字段：** VideoUnmask 的全部字段，另加：
- `layout.button_xy`：按钮位置；
- `actions.sampling_trace.constructor_draw`：构造期那次 `randint(1,6)` 占位抽样。

**行为改动：** 同 VideoUnmask（含 V5 的统一采样器与独立停放点）；按钮 OBB 以预制三元组进干扰容器的障碍表。构造期的占位抽样原样保留，
首个 pickup 任务的单元素列表形态也保留。按钮区与容器区重叠，放置更紧。

**subgoal 流程：** 同 VideoUnmask，只是开头是 `press the button` 而不是 `static`：
hard `press → pick c0 → put down → pick c1`（4 个）→ xhard `press → pick c0 → [put down → pick c_k] ×2`（6 个）；干扰容器误抓外包同上。

### 1.7 VideoUnmaskSwap（基准 hard，覆盖旧 xhard）

> V5：干扰容器 3 → 10（环带沿用 V4）、外环随内环同窗交换、两对联合碰撞证明、内环对内环 reset 预判（报告 [S3h](../docs/validation/newtask-v5/20260924-s3h-unmaskswap.md)、
> 共用设施 [S2b](../docs/validation/newtask-v5/20260924-s2b-multi-swap-sweep.md) / [S2c](../docs/validation/newtask-v5/20260924-s2c-unmask-distractor-sampler.md)，计划 2.5、2.6）。

| 配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.swap_count_range.xhard` | `[2,3]` | `[8,12]`（旧 xhard `[4,5]` 作废） |
| `decision.pick_count_range.xhard` | `[2,2]` | `[3,3]` |
| `native.parameters.xhard.object_selection.pickup_selected_indices` | `[0,1]` | `[0,1,2]` |
| `decision.xhard.swap_speed_multiplier` | 1 | 1.5，每段 `round(50/1.5)=33` 步，从第 64 步开始 |
| `decision.xhard.distractor` | — | 统一 7 键：`count: 10`、`ring_max_abs_xy: [0.2675, 0.45]`、`cube_count_range: [5,5]`、`color_pool: [yellow,cyan,magenta]`、`color_rule: balanced_cycle`、`min_gap_factor: 0.75`、`max_trials: 1024`（V4 原值：`count: 3`、`with_cube_range: [1,2]`、`ring_half_extent: [0.2675, 0.45]`、`min_gap: 0.04`、`colors`，旧键名 V5 全部换成统一键） |
| `decision.xhard.distractor_swap`（V5 新增） | — | `enabled: true`、`initiator_rule: permutation_cycle`、`fallback: next_in_permutation`、`partner: {selection: nearest, position_axes: [0,1], tie_break: first_in_index_order, population: distractor_bins, resolve_at: reset_plan}`、`lane_offset: 0.07`、`smooth: true`、`path_constraints: {camera_visible: true, min_inner_circle_clearance_m: 0.04, min_button_center_dist_m: null}`、`path_samples: 401`、`plan_pad_m: 0.005`、`layout_max_attempts: 16` |

**规格字段：**
- `actions.swap_window.{start_step,duration_steps,speed_multiplier}`：交换窗口起点、每段步数、速度倍率；
- `layout.bins.<i>`、`layout.type_choice`：容器位姿、容器类型；
- `objects.n_swaps`、`n_picks`、`selected`、`target_choice`、`color_order`：交换次数、抓取次数、被选中的容器、目标、颜色顺序；
- `objects.swap_initiator_indices`、`swap_initiator_third`：交换发起者；
- 干扰容器：改用与 VideoUnmask 相同的统一 schema `objects.distractors.{bins.<i>, cube_count, cube_bins, color_order, requested, placed, trials, cube_colors, cube_names}`；
  **V4 的 `layout.distractors.<i>`、`layout.distractors_requested`、`layout.distractors_placed`、`objects.distractors.n_with_cube` 不再使用**；
- V5 新增（外环交换）：
  - `objects.distractors.swap_order`（value）：0..9 的排列，外环发起者的轮流顺序；
  - `actions.distractor_swap_pairs`（record）：`[[o, p], …]`，长度 = `objects.n_swaps`，第 k 窗交换的两个干扰容器（`distractor_bin_<i>` 的序号，不是内环 `bin_<i>`）；
  - `actions.distractor_swap_fallback`（record）：第 k 窗发起者在排列里顺延了几位（0 = 第一候选就可行）；
  - `actions.predicted_inner_swap_pairs`（record）：reset 预演的内环对；
  - `layout.distractor_layout_attempts`、`layout.distractor_layout_failures`（record）：干扰布局整段重抽的次数与每次失败原因；
  - `layout.inner_sweep_prejudge`（record，只出现在被预判拒绝的抽签草稿里）；
  - 运行时（只在实跑的 `rng_trace.json` 里）：`actions.distractor_swap_windows.<k>`（外环第 k 窗实际执行）、`actions.inner_swap_mismatch.<k>`（运行时内环搭档与预演不一致时）。

**行为改动：**
- 交换窗口改用具名常量，按倍率取整；交换期等待改用 `solve_hold_obj_xhard`（原共享函数 `solve_hold_obj` 的裸 except 会吞掉碰撞拒绝，导致死循环）；
  误抓即失败同 VideoUnmask（V4）；
- **V5 reset**（`utils/unmask_swap_xhard.py::plan_swap_distractors`，仍由 `_spawn_xhard_distractors` 在 `_load_scene` 最后调用）：
  1. 预演内环全部交换窗口，逐窗做内环对内环的连续扫掠预判，有碰撞就抛真 `SceneGenerationError`（V4 要到演示期才被拒）；
  2. 统一采样器放 10 个干扰容器，放置时排除会与内环交换扫掠相撞的候选；整段布局最多重抽 16 次；
  3. 抽一个 0..9 的排列，逐窗规划外环对：发起者按排列轮流，不可行就顺延；搭档取离发起者 XY 最近的干扰容器；依次检查两条路径全程相机可见、
     路径离本窗内环交换路径与其余内环容器的间隙 ≥ 0.04 m、内环对 + 外环对两对同时移动的联合连续碰撞证明（`bin_collision.check_multi_swap_sweep`）；
     规划时干扰容器碰撞盒外扩 5 mm（`plan_pad_m`）；
  4. 以上抽样全部走独立的 `distractor_generator(seed)`，主随机流一次不多抽；
- **V5 运行时**：外环第 k 对与内环第 k 窗在同一 `[start, end]` 内交换（错道 0.07 m、smoothstep、其余干扰容器钉住），`swap_schedule` 与所有等待点不变，
  **不增加控制步**；每窗对「内环实际对 + 外环规划对」做两对联合复核；揭示段与交换后内外环容器、方块各停独立点（同 VideoUnmask）；
- **V5**：内环容器放不下时，xhard 改抛真 `SceneGenerationError`，原三档仍静默截断（`break`）。计划 L15 只点名 ButtonUnmaskSwap，
  VideoUnmaskSwap 由主会话按同理自决，列在待用户复核项里；
- **V5 回放复核**：冻结布局须与按同一规则重抽的结果一致；冻结的 `swap_order` 与重抽不同时，按冻结排列重新规划并复核可行性，不可行抛 `SceneGenerationError`。

**subgoal 流程：** 顺序不变，pick 次数 2 → 3，开头 `static` 的等待方式变了；V5 的外环交换挂在同一交换窗口里，任务表不变。

| 档 | 序列 |
|---|---|
| hard | `static`（D，`solve_hold_obj` 等到最后一段交换结束，164 或 214 步）→ pick c0 → `put down the container` → pick c1 |
| xhard | `static`（D，改用 `solve_hold_obj_xhard`，等 64+33n 步，n∈[8,12] 即 328～460 步）→ pick c0 → [put down → pick c_j] ×2，共 6 个 |

原 hard 分支写死 `pick_times==2`，xhard 另开循环生成；干扰容器误抓外包同 VideoUnmask。

### 1.8 ButtonUnmaskSwap（基准 hard）

> V5：同 VideoUnmaskSwap，另加外环路径离按钮中心的约束、内环静默截断改报错（报告 [S3h](../docs/validation/newtask-v5/20260924-s3h-unmaskswap.md)，计划 2.7）。

| 配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.swap_count_range.xhard` | `[2,3]` | `[6,8]` |
| `decision.pick_count_range.xhard` | `[2,2]` | `[3,3]` |
| `native.parameters.bin_count.xhard` | 4 | 4 |
| `decision.xhard.swap_speed_multiplier` | 1 | 1.5（`native.swap_window` 实际消费，为 `{64, 33}`） |
| `decision.xhard.distractor` | — | 同 VideoUnmaskSwap（10 个、环带 `[0.2675, 0.45]`、cube `[5,5]`） |
| `decision.xhard.distractor_swap`（V5 新增） | — | 同 VideoUnmaskSwap，只是 `path_constraints.min_button_center_dist_m: 0.122` |

**规格字段：** 同 VideoUnmaskSwap（含 V5 新增的外环交换字段）。

**行为改动：**
- `_refresh_swap_schedule` 的三个分支换成通式，并用 `for k in range(3, swap_times)` 补槽位；六处字面量 50 改成具名常量；
- 按完第二个按钮后原地等到最后一段交换结束再去抓（原解法会在容器还在交换时去抓）；
- **V5**：外环 reset 规划、运行时同步交换、联合复核、独立停放同 VideoUnmaskSwap；按钮 OBB 以预制三元组精确进干扰容器的障碍表，
  外环两条交换路径离每个按钮中心 ≥ 0.122 m；内环 `spawn_random_bin` 失败时 xhard 抛真 `SceneGenerationError`（L15），原三档仍 `break`。

**subgoal 流程：** 顺序不变，pick 次数 2 → 3，**第二个按钮的 solve 变了**。

| 档 | 序列 |
|---|---|
| hard | `press the first button` → `press the second button` → pick c0 → `put down the container` → pick c1（5 个） |
| xhard | `press the first button` → `press the second button`（solve 换成 `_solve_press_then_wait_swaps`：按完原地等到最后一段交换结束，64+33n 步，n∈[6,8] 即 262～328 步）→ pick c0 → [put down → pick c_j] ×2（7 个） |

等待挂在按钮 subgoal 上而不是 pick 上，是因为 `inject_fail_grasp` 会替换 pick 的 solve。干扰容器误抓外包同 VideoUnmask。

### 1.9 VideoRepick（基准 medium，覆盖旧 xhard）

> V5：最小中心距 0.12 m、6 块 `k%6` 轮流发起、reset 时从 3 个最近可行者里规划搭档、按钮底座纳入扫掠障碍（报告 [S3g](../docs/validation/newtask-v5/20260924-s3g-videorepick.md)，计划 2.15）。

| 配置字段 | medium 值 | xhard 值 |
|---|---|---|
| `decision.xhard.layout` | 三组锚点 | `mode: clutter`、`cube_count: 6`、`region_center: [-0.1, 0]`、`region_half_size: [0.2, 0.25]`、`min_center_dist_m: 0.12`（V5 新增） |
| `decision.num_repeats_range.xhard` | 死键（实际取 1～3） | `{low: 4, high_exclusive: 7}`，即 4～6，xhard 接上了消费点 |
| `decision.swap.xhard` | `[2,3]` | `{swap_min: 8, swap_max: 12}` |
| `decision.xhard.block_color` | 三块同色，红/蓝/绿 | `policy: same_color_hsv_floor`、`sampler: torch.rand`、`h_range: [0,1]`、`s_range: [0.5,1]`、`v_range: [0.4,1]` |
| `decision.xhard.swap_plan`（V5 新增） | — | `initiator_rule: target_then_randperm_k_mod_cube_count`、`partner_rule: reset_plan_nearest_feasible`、`nearest_k: 3`、`sweep_margin_m: 0.005`、`button_obstacle: true` |

源码 `config_xhard` 里对应多了 `min_center_dist_m`、`partner_nearest_k`、`partner_sweep_margin_m`、`partner_button_obstacle` 四个键，decision 从这里取值。

**规格字段：**
- `layout.cubes.<i>.xy_yaw`：6 块的位置和朝向；
- `objects.color_rgb`：三块共用的颜色；
- `objects.n_swaps`、`num_repeats`：交换次数、重复次数；
- `objects.target`：目标块；
- `objects.swap_initiators_remaining`（value）：V5 改为完整的 `randperm(5)`，长度 5（V4 截断为长度 2）；
- `objects.swap_initiators`（record）：V5 为长度 6 的 `[目标] + 其余 5 块的顺序`（V4 只有 3 个发起者）；
- `objects.swap_partner_u`（V5 新增，value）：长度 = n_swaps 的 [0,1) 均匀数，用来在候选池里挑搭档；
- `actions.swap_pairs.<k>`（V5 新增，value，reset 时写入）：第 k 次交换 `{"initiator": "bin_a", "partner": "bin_b"}`；运行时 `step` 仍按 V4 原样 record 同一路径（值相同）与 `actions.swap_windows.<k>`；
- `objects.cube_count.{requested,actual}`：请求数与实际放下的数。

**行为改动：**
- `_load_cubes_xhard`：先定颜色，再放 6 块，再选目标；四处扫掠检查改为「甲通道，或 xhard 乙通道」；交换期等待函数同 VideoUnmaskSwap 的死循环修复；
  xhard 拒收甲通道的 `episode_spec`（V4）；
- **V5 摆放**：6 块两两中心距 ≥ 0.12 m（`spawn_random_cube(min_center_dist=...)`），已放方块以精确 OBB 进 `avoid`；区域与按钮不动；
- **V5 发起者**：6 块全部轮流发起，第 k 次发起者 = `seq[k % 6]`，`seq = [目标] + randperm(5)`；
- **V5 搭档在 reset 时规划**（`_plan_swaps_xhard`，不抽随机数）：其余槽位按 XY 距离排序；最近 3 个里至少一个扫掠可行时，候选池 = 按距离序的前 3 个可行者，
  否则回退到全部可行者；用 `swap_partner_u[k]` 在池里均匀挑；池空抛真 `SceneGenerationError`。扫掠判据是 `check_swap_sweep_prefiltered`，
  方块按半边 +5 mm 放大，**按钮底座**以真实尺寸作静止障碍；`step` 里 xhard 直接用规划好的搭档，不再运行时找最近邻，运行时扫掠检查仍保留作守卫；
- **V5 回放复核**：`swap_initiators_remaining` 必须是完整排列、`swap_partner_u` 长度与取值域、每次冻结搭档须与规划发起者一致且扫掠可行，否则 `EpisodeSpecError`；
- 实测（报告 S3g，离线 2400 局）：按钮纳入障碍后 reset 规划失败率 9.04% → **39.96%**（V4 是约 45% 的局在演示期被碰撞检查拒绝）；
  本机演示 7/7 成功，运行时扫掠检查 77 次 0 拒绝。是否接受这一失败率列在待用户决策项里。

**subgoal 流程：** 结构同 medium，只是次数变、等待函数换了。

| 档 | 序列 |
|---|---|
| medium | `pick up the cube`（D）→ `drop the cube on the table`（D）→ `static`（D，复位后等 20 步）→ `static`（D，swap）×[2,3] → `NO RECORD` → [`pick up the correct cube for the {序数} time` → `put it down`] ×[1,3] → `press the button to finish` |
| xhard | 同上；swap 的 `static` ×[8,12]，repick 对 ×[4,6]；两种 `static` 的等待改用只吞 AttributeError 的修复版（同 VideoUnmaskSwap） |

hard 档没有交换（swap 0），所以没有那组 `static`；failure_func 与名字都不变。

### 1.10 VideoPlaceButton（基准 hard）

> V5：配置字段、规格字段与 subgoal 流程都不变，**只修方块障碍框**（计划 2.16、L2 b；报告 [S3i](../docs/validation/newtask-v5/20260924-s3i-obb-fix-pickhighlight-videoplace.md)）：
> xhard 下每块方块建成后改以 `cube_obb2d_exact(cube.initial_pose, cube_half_size)` 的精确三元组进 `avoid`（原三档仍放 actor），
> 此后第 2、3 块方块与 4 个目标台的放置都读这张表，spawn 调用本身一字未改。修复后名义间距真正生效，xhard reset 成功率（300 次真 reset）87.7% → 81.7%，
> 失败都是目标台放不下（可重试的 `SceneGenerationError`）。

| 配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.xhard.demo_object_count` | 1 | 2 |
| `decision.xhard.demo_return_policy` | 放到隐藏的 goal_site | `return_to_origin` |
| `decision.targets.xhard` / `swap.xhard` / `additional_place.xhard` | 4 / true / false | 4 / true / false（不变） |
| `native.parameters.color.xhard` | 3 | 3（不变） |

**规格字段（14 个）：**
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

> V5：同 VideoPlaceButton，只修方块障碍框（报告 [S3i](../docs/validation/newtask-v5/20260924-s3i-obb-fix-pickhighlight-videoplace.md)）。
> 修复后 xhard reset 成功率 59.3% → 48.3%，根因是目标台与 goal_site、按钮、3 块方块挤在 0.4×0.4 的区域里；是否放宽布局列在待用户决策项里。

配置字段与 VideoPlaceButton 相同（`demo_object_count: 2`、`demo_return_policy: return_to_origin`，其余不变）。

**规格字段（18 个）：** VideoPlaceButton 的 14 个，另加：
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

> V5：配置字段、规格字段与 subgoal 流程都不变，**只修方块障碍框**：xhard 下已放方块改以精确三元组进 `avoid`（同 VideoPlaceButton；报告
> [S3i](../docs/validation/newtask-v5/20260924-s3i-obb-fix-pickhighlight-videoplace.md)）。修复前 83% 的局里至少有一对方块间距不到名义 0.04；
> 修复后全部满足，但 xhard reset 成功率 97.0% → 87.0%，集中在 10 块的局（69.6%）；`spawn_count` 上界 10 是否下调列在待用户决策项里。

| 配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.highlight_count.xhard` | 3 | `[5,7]` |
| `decision.spawn_count.xhard` | 6 | `[8,10]` |
| `decision.xhard.block_color_policy` | 红/蓝/绿逐块抽 | `hsv_floor` |
| `decision.xhard.block_color_hsv` | — | `h_range: [0,1]`、`s_range: [0.5,1]`、`v_range: [0.4,1]` |
| `decision.xhard.subgoal_color_suffix` | `, which is {color}` | `omit`（去掉） |

**规格字段（7 个）：**
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

> V5：删掉 `corner_bias`，杆/goal/方块都不得落进桌面中心 R = 0.05 m 的圆；执行段方块不避让演示段方块（报告 [S3c](../docs/validation/newtask-v5/20260924-s3c-movecube.md)，计划 2.9）。

| 配置字段 | hard 值（原全局常量） | xhard 值 |
|---|---|---|
| `decision.demo_layout.xhard.center_exclusion`（V5 新增，替代 V4 的 `corner_bias: 0.5`） | — | `shape: circle`、`center: [0, 0]`、`radius_m: 0.05`、`judge: object_center`、`max_trials: 128` |
| `decision.execution_layout.xhard.center_exclusion`（同上） | — | 同上（演示段与执行段各一份，各自消费） |
| `decision.peg_yaw_range.xhard` | `span_rad: π/2, offset_rad: π/4`，即 ±45° | `span_rad: 2π, offset_rad: π`，即 ±180° |

**规格字段（15 个）：**
- `layout.demo.{cube_pose,goal_xy,peg_offsets,peg_yaw}`：演示段的方块、目标、杆位与杆朝向；
- `layout.execution.{cube_pose,goal_xy,peg_offsets,peg_yaw}`：执行段同上；
- `layout.{demo,execution}.center_exclusion`（V5 新增，record）：本局生效的禁区配置原样，另加 `peg_axis_extent_m`（判据用的杆轴区间）；
- `layout.{demo,execution}.center_exclusion_trials`（V5 新增，record）：`peg_trials`（杆重抽次数）、`cube_candidate_center_rejects`（方块候选中心被禁区拒绝的次数）；
- `initializations.<i>.way_idx`：每次初始化选的推法；
- `objects.obj_sample`、`objects.sampling_trace.dir_sample`：对象与方向抽样。

**V4 的 `layout.{demo,execution}.corner_bias` 已删除。**

**行为改动：**
- 等价朝向归约（V4）：夹爪 x 轴相对「基座→抓取点」方位角超过 ±90° 时，夹爪姿态右乘 Rz(π)，抓杆后的推杆姿态同步右乘 Rz(π)；
  这段在 `subgoal_planner_func` 里由环境开关 `_xhard_peg_yaw_reduction` 守着，原三档不进这个分支；三种推法都保留；
- **V5 桌面中心禁区**（圆心 (0,0)、R = 0.05 m，`距离 < R` 算落进圆）：
  - 杆：按杆的实际轴线段判（杆根沿朝向 `[−0.15, +0.05]` m，取可视外形；每次建杆后用实际几何复核这个区间，建模一变就报错），
    离圆心最近点落进圆就把 x、y、yaw 原地重抽，上限 128 次，超出抛 `SceneGenerationError`；
  - goal、方块候选中心、方块最终中心：按物体中心判，拒绝计入各自原有循环的预算（256 / 128 / 256），耗尽抛 `SceneGenerationError`；
- **V5**：演示段与执行段的方块都传 `include_existing=False`，执行段方块不再避让演示段方块（两块从不同时在场），xhard 下不再有以 actor 作障碍的方块；
- **V5 回放复核**：`peg_offsets`、`peg_yaw` 的冻结值按同一判据复核，违规抛 `EpisodeSpecError`；goal 与方块由 `spawn_random_*` 的 `center_exclusion` 参数复核。

**subgoal 流程：** 任务表完全不变，三种推法（peg_push 6 个、gripper_push 4 个、grasp_putdown 6 个 subgoal）照旧。
只有执行方式变：`Pick up the peg` 的 `grasp_and_lift_peg_side` 与 `Hook the cube …` 的 `solve_push_to_target_with_peg` 在需要时右乘 Rz(π)（见上）。

### 1.14 InsertPeg（基准 A6）

> V5：删第 4 根杆的专用采样器与贴近带，4 根一个循环；杆与杆轮廓间隔 > 0.03 m、离孔板 > 0.01 m（报告 [S3d](../docs/validation/newtask-v5/20260924-s3d-insertpeg.md)，计划 2.8）。

| 配置字段 | hard 值（原全局常量） | xhard 值 |
|---|---|---|
| `decision.xhard.peg_count` | 3 | 4 |
| `decision.xhard.peg_offsets` | `[0.1, 0, -0.1]` | `[0.1, 0, -0.1, -0.2]`（构造期的临时排布，随后被重采样覆盖） |
| `decision.xhard.peg_yaw_range` | `half_span_deg: 45` | `half_span_deg: 180` |
| `decision.xhard.peg_min_pair_gap_m`（V5 新增） | — | 0.03（杆与杆轮廓间隔下限，严格大于） |
| `decision.xhard.peg_box_min_gap_m`（V5 新增） | — | 0.01（杆与孔板轮廓间隔下限） |
| `decision.xhard.peg_x_max_m`（V5 新增） | — | 0.1（杆根 x 上界，x 取值 `[-0.2, 0.1]`） |

**V4 的 `decision.xhard.near_target_distractor` 已删除**（原三档可见部分的 `near_target_distractor: None` 不动）。

**规格字段（10 个）：**
- `initializations.<i>.pegs.<i>`：每根杆的位姿 `[[x, y], yaw]`；
- `initializations.<i>.box_jitter`、`box_yaw`：盒子扰动与朝向；
- `initializations.<i>.obj_sample`、`dir_sample`：对象与方向抽样；
- `initializations.<i>.peg_attempts`（V5 新增，record）：4 根杆各自的尝试次数；
- `initializations.<i>.min_pair_gap_m`、`min_box_gap_m`（V5 新增，record）：本局实测的最小杆间、杆到孔板轮廓间隔；
- `objects.head_rgb`：杆头颜色；
- `objects.sampling_trace.random_peg_idx`：目标杆抽样。

**V4 的 `near_target_distance`、`near_target_attempts`、`peg_placement.{requested,placed}` 已删除。**

**行为改动：**
- **V5**：4 根杆由 `_xhard_sample_pegs` 在一个循环里依次抽（目标恒为 peg_0，只是第一个被抽），排在孔板采样之后、obj/dir 抽样之前；
  原生杆循环在 xhard 下一根都不跑（循环体逐字不动）。每根最多 512 次：
  1. 按原生取法抽杆根 x、y（x 跨度改为 `[-0.2, 0.1]`）；原生规则保留：离孔板中心 ≤ 0.06 或离已放杆根 ≤ 0.075 就重抽；
  2. 通过后才抽 yaw（±180°）；
  3. 按有向矩形轮廓（杆、孔板尺寸从建模参数推出）算精确间隔：离孔板 ≤ 0.01 或离任一已放杆 ≤ 0.03 就重抽；
  4. 接受后只调一次 `_spec.value`；耗尽抛 `SceneGenerationError`；
- **V5 回放复核**：对冻结位姿重算两种轮廓间隔，违反抛 `EpisodeSpecError`；
- `insert_peg` 在朝向翻转时把夹爪局部系里的平移 xy 取反（V4）；vqa 候选随杆数从 6 个变成 8 个（V4）；
- 本机演示成功率约 40%，失败主体是「抓尾插头」时插入不到位（L53 决定不修），以及一次复位后目标杆被弹飞；两项都列在待用户决策项里。

**subgoal 流程：** 任务表完全不变，仍是 6 个：`Pick up the peg by grasping the {near|far} end` → `Insert the peg from the {left|right} side of the box`
→ `NO RECORD`（reset pegs）→ `NO RECORD`（静止 100 步）→ 执行段的 pick 与 insert。执行段「抓了别的杆即失败」的判定现在覆盖 3 根非目标杆（原 2 根）；
朝向翻转时 `insert_peg` 的局部 xy 取反（见上）。

### 1.15 PatternLock（基准 hard）

> V5：布局不动；节点数固定 25、搜索预算 20000、搜索耗尽抛错（报告 [S3a](../docs/validation/newtask-v5/20260924-s3a-patternlock-routestick.md)，计划 2.10）。

| 配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.grid.xhard` | 5 | 5（布局不改） |
| `decision.path_length_range.xhard` | `[4,8]` | `[25,25]`（由源码 `config_xhard.length` 派生；V4 原值 `[20,24]`） |
| `decision.xhard.path_search_max_attempts`（V5 新增） | —（原三档读 native 的 1000） | 20000 |

**规格字段（2 个）：**
- `actions.path_nodes`：路径节点序列；
- `actions.path_attempts`：搜到这条路径用了几次尝试。

**行为改动：**
- **V5**：xhard 的路径搜索预算从 native 的 1000 改读 `decision.xhard.path_search_max_attempts`（20000，随 decision 冻进快照 header）；
  预算耗尽抛真 `SceneGenerationError`（原三档仍静默沿用最后一条路径）。25 节点在 20000 次预算内命中率 1.000（1000 次时只有 0.365）；
- **V5 回放复核**：节点数在范围内、不重访、8 邻接、不越界，违反抛 `EpisodeSpecError`；
- 缺 `decision.xhard` 键（V4 或更早的快照）时报错，不回退到原三档值；
- 演示时长：本机 4 局演示帧 818～872（约 27～29 s），落在口径 9 的 750～1050 帧内；V4 的 20 节点约 19.6 s。

**subgoal 流程：** 结构不变，只是次数变。`NO RECORD` → `move {方向}` ×(n−1)（演示）→ `NO RECORD` ×2 → `move {方向}` ×(n−1)（执行）；
n：hard 4～8 → xhard 25（V4 为 20～24），总 subgoal 9～17 → 51（V4 为 41～49）。

### 1.16 RouteStick（基准 hard，覆盖旧 xhard）

> V5：L `[12,15]` → `[15,21]`，L 范围冻进 decision（报告 [S3a](../docs/validation/newtask-v5/20260924-s3a-patternlock-routestick.md)，计划 2.11）。

| 配置字段 | hard 值 | xhard 值 |
|---|---|---|
| `decision.xhard.segment_count_range`（V5 新增） | — | `[15,21]`（由源码 `config_xhard.length` 派生；`backtrack` 仍为 True） |

V4 没有配置字段，xhard 值只写在源码 `config_xhard` 里（`length` `[4,7]`→`[12,15]`，旧 xhard `[8,10]` 作废），不随快照冻结；V5 把 L 范围冻进 decision 与快照 header。

**规格字段（5 个）：**
- `objects.L`：段数；
- `actions.nodes`、`actions.directions.<i>`：走过的节点与每段方向；
- `layout.rotation_deg`、`layout.obstacle_rgb.<i>`：网格旋转角、障碍物颜色。

**行为改动：**
- **V5**：xhard 的 L 范围从传入的 `sampling_config.decision.xhard.segment_count_range`（即 header 冻结值）读，不再读类属性；
  抽样调用的位置与形状不变，只改值域；缺这个键（V4 header）时 xhard reset 抛 `ValueError`（V4 规格在 V5 上被拒的方式）；
- **V5 回放复核**：L 在范围内、节点数 = L+1，违反抛 `EpisodeSpecError`；
- 演示每段恰 50 帧，L×50 = 750～1050 帧，即 25～35 s（口径 9）；执行段步数同为 50·L，L=21 时 1050，在推理 1300 步预算内。

**subgoal 流程：** 结构不变，只是次数变。`NO RECORD` → `move to the nearest {left|right} target by circling around the stick {方向}` ×L（演示）
→ `NO RECORD` ×2 → 同名 move ×L（执行）；L：hard 4～7 → xhard 15～21（V4 为 12～15），总 subgoal 11～17 → 33～45（V4 为 27～33）。

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

**V5 追加的代码改动**（只加不改：`_trimesh_box_to_obb2d`、`_safe_unit`、`check_swap_sweep`、`statechange.py`、`spawn_random_bin` 的语义都没动）：

| 位置 | 改了什么 |
|---|---|
| `utils/xhard.py::cube_obb2d_exact`（新增） | 按方块真实 yaw 给出预制 2D 障碍 `(c, A, h)`，不抽随机数；xhard 分支用它替代「把方块 actor 放进 `avoid`」（报告 S2a） |
| `utils/object_generation.py` 的 `spawn_random_cube` / `spawn_random_target` | 新增可选参数 `min_center_dist=None`、`center_exclusion=None`，在既有 OBB/圆判据之后、`recorder.value` 之前判，回放时对冻结值复核；默认 `None` 时整段跳过（S2a） |
| VideoRepick、SwingXtimes、PatternLock、RouteStick、StopCube、VUS、BUS 模块头 | `_RealSceneGenerationError` 别名与 `_scene_gen_error(difficulty)`：xhard 抛真 `SceneGenerationError`，原三档仍是 TypeError（S2a） |
| `utils/bin_collision.py` | 新增 `check_multi_swap_sweep`（多对同时交换的联合连续证明）、`check_swap_sweep_prefiltered`（同判定加认证预筛）、静止障碍 helper（`static_box_state`、`static_rect_state`、`button_base_state` 等）；单对时与 `check_swap_sweep` 逐位相同（S2b） |
| `utils/unmask_distractor_sampler.py`（新增） | 四个 Unmask 环境共用的干扰容器采样器、统一配置 7 键与 `objects.distractors.*` schema、整段重抽驱动、独立停放点 `xhard_park_point` 与停放版揭示 helper（S2c） |
| `utils/unmask_swap_xhard.py` 末尾「V5」一节 | 内环预演与预判、H1 守卫、外环规划与复核、`plan_swap_distractors` / `spawn_swap_distractors_v5`、运行时 `run_outer_swaps`；V4 的采样函数保留为死代码（S3h） |
| `scripts/parity/v4_specs.py` | `draw --workers N --gpus …` 多进程抽签，结果与单 worker 逐行相同（工具链报告） |
| `scripts/parity/train_split_config.py` | `extract --release newtask-v5`；不带 `--release` 时仍是 `newtask-v4`（5.1） |
| `scripts/parity/v5_generation.py`（新增） | `pipeline` 串起抽签 → 冻结 → 实跑 → 报告，`report` 写生成报告（5.2、5.3） |

V5 没有再动录像器（`RecordWrapper.py` 仍只有 V4 的 `fail_safe_limit` 5000 一处改动）；**V5 的抽签、实跑、推理同样全部不开 fail recover。**

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

**V5**：快照沿用同一封套（`schema` 仍为 `v4-specs/1`、`spec_kind` 仍为 `native-newvalue/1`、`seed_rule` 与 `recovery_rule` 不变），只换
`run_id`（`v5-01`）、落点（`scripts/configs/newtask-v5/v5-01/specs.jsonl`）与封存的配置（`scripts/configs/newtask-v5/sampling_config.json`）。
候选行 `spec` 里各环境的字段按第一节的 V5 列表；V4 快照在 V5 代码上会被 decision 形状检查、xhard reset 或回放复核拒绝（预期）。

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

**V5**：字段不变，落点为 `artifacts/newtask-v5/v5-01/rollout/run1/`；另有生成报告 `artifacts/newtask-v5/v5-01/report/generation_report.{md,json}`（字段见 5.3）。

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
6. **V5 走同一条路径。** `from_v4_specs` 与 `load_specs` 不区分 V4/V5，只看快照本身；V5 推理用
   `scripts/configs/newtask-v5/v5-01/specs.selected.jsonl`（由 4.2 的 `reselect` 生成，见下）。

---

## 第四节　三步各自怎么调用

正式快照 `v4-01` 在 [configs/newtask-v4/v4-01/](configs/newtask-v4/v4-01/)，已进 Git。以下命令都在仓库根目录执行。
V5 的正式快照是 `v5-01`，落在 `configs/newtask-v5/v5-01/`（冻结后进 Git），产物一律落 `artifacts/newtask-v5/v5-01/`；每一步下面另列 V5 的写法。
V5 推荐用 5.2 的 `v5_generation pipeline` 一条命令串起 4.1～4.2，分步写法与下面的 V5 命令等价。

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

**V5 对应**（`v4_specs` 的 `--sampling-config` 默认仍指 V4 快照，V5 必须显式传 `scripts/configs/newtask-v5/sampling_config.json`，否则 header 会封存 V4 配置）：

```bash
uv run --no-sync python -m scripts.parity.v4_specs draw --run-id v5-01 --tasks all --sampling-config scripts/configs/newtask-v5/sampling_config.json --candidates-per-env 10 --max-reset-attempts 30 --workers <抽签并行数> --gpus 0,1 --out artifacts/newtask-v5/v5-01/draft/drafts.jsonl
```

```bash
uv run --no-sync python -m scripts.parity.v4_specs freeze --drafts artifacts/newtask-v5/v5-01/draft/drafts.jsonl --sampling-config scripts/configs/newtask-v5/sampling_config.json --select 0,3,6 --candidates-per-env 10 --out scripts/configs/newtask-v5/v5-01/specs.jsonl
```

`--workers N` 按环境分给 N 个子进程抽签，结果与单 worker 逐行相同（5.2）。

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

**V5 对应**：

```bash
uv run --no-sync python -m scripts.parity.v4_rollout run --specs scripts/configs/newtask-v5/v5-01/specs.jsonl --label run1 --tasks all --workers <实跑并行数> --gpu 0 --official-root artifacts/train-parity/local-smoke-01/official-src --output artifacts/newtask-v5/v5-01/rollout
```

```bash
uv run --no-sync python -m scripts.parity.v4_specs reselect --specs scripts/configs/newtask-v5/v5-01/specs.jsonl --results artifacts/newtask-v5/v5-01/rollout/run1/results.jsonl --out scripts/configs/newtask-v5/v5-01/specs.selected.jsonl
```

- V5 实跑只跑一遍（口径 12），不跑 run2 / compare；递补规则同上。
- `v5_generation pipeline` 只做抽签 → 冻结 → 实跑 → 报告，**不含 `reselect`**；要做推理时在实跑完成后手工补上面这条。

### 4.3 第三步：推理（[eval/v4_eval.py](eval/v4_eval.py)）

```bash
uv run --no-sync python -m scripts.eval.v4_eval --specs scripts/configs/newtask-v4/v4-01/specs.selected.jsonl --max-steps 1300 --join-results artifacts/newtask-v4/v4-01/rollout/run1/results.jsonl --out artifacts/newtask-v4/v4-01/eval-all
```

- 逐局边跑边写 `eval_results.jsonl`，全部跑完写 `eval_summary.json`。给了 `--join-results` 时，收尾按身份与生成侧 join，
  并打印 `EVAL_PIPELINE=...` 判定行。
- 可选参数：`--tasks` 限定环境，`--limit-per-task` 限定每个环境评几局，`--action-space` 默认 `joint_angle`，`--model-seed` 默认 7。
- 默认策略是 `DummyModel`，与 `scripts/evaluation.py` 里的同构，只用来验证链路；换成真实策略时替换 `v4_eval.py` 里的模型类即可。

**V5 对应**：

```bash
uv run --no-sync python -m scripts.eval.v4_eval --specs scripts/configs/newtask-v5/v5-01/specs.selected.jsonl --max-steps 1300 --join-results artifacts/newtask-v5/v5-01/rollout/run1/results.jsonl --out artifacts/newtask-v5/v5-01/eval-all
```

V5 的 RouteStick 执行段最长 1050 步（L=21），仍在 1300 步预算内。

---

## 第五节　V5：生成工具链与 V1 对拍

计划见 [NEWTASK_RELEASE_V5_PLAN.md](../NEWTASK_RELEASE_V5_PLAN.md) 第三节（3.1 链路、3.2 判据、3.3 S4～S6）与第二部分「三、runbook」。
V5 **沿用 V4 的脚本与封套**（`v4_specs` / `v4_rollout` 的 schema、`SEED_RULE`、不开 recover 的规则都不变），只换快照目录与 run id：
快照 `scripts/configs/newtask-v5/`，run id `v5-01`，产物一律落 `artifacts/newtask-v5/`。V4 的配置与产物原样留档、不再引用（N15）。
所有命令在仓库根目录执行；超过 5 分钟的一律用 detached tmux，等待用 Monitor 挂日志（AGENTS.md 规则 4）。
环境侧的 V5 改动（配置字段、规格字段、行为）见第一节各环境开头的「V5：」标注与报告链接；快照、结果文件与推理侧的 V5 说明见第二～四节的「V5」段。

### 5.1 S4：一次性重导快照

```bash
uv run --no-sync python scripts/parity/train_split_config.py extract --release newtask-v5
uv run --no-sync python scripts/parity/train_split_config.py extract --release newtask-v5 --verify   # 之后随时核对快照与源码一致
uv run --no-sync python scripts/parity/train_split_audit.py config-map                               # SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0
```

`--release` 决定默认落点 `scripts/configs/<release>/sampling_config.json` 与快照里的说明文字；不带时仍是 `newtask-v4`，V4 命令与字节不变。

### 5.2 S6：一条命令串起抽签 → 冻结 → 实跑 → 报告

入口是 [parity/v5_generation.py](parity/v5_generation.py) 的 `pipeline`，它只按 `--release`／`--run-id` 推导落点，然后依次以子进程调用
`v4_specs draw --workers <抽签并行数>` → `v4_specs freeze` → `v4_rollout run --workers <实跑并行数>` → `v5_generation report`，
任一步失败即停（`PIPELINE_FAIL step=… exit=…`），全部完成打印 `PIPELINE_DONE`。

```bash
tmux new-session -d -s v5-gen "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.v5_generation pipeline \
  --run-id v5-01 --draw-workers <抽签并行数> --draw-gpus 0,1 --workers <实跑并行数> --rollout-gpu 0 \
  --official-root artifacts/train-parity/local-smoke-01/official-src \
  2>&1 | tee artifacts/logs/v5-gen-v5-01.log; echo \"EXIT_CODE=\$?\" >> artifacts/logs/v5-gen-v5-01.log"
# 等待：tail -n +1 -F artifacts/logs/v5-gen-v5-01.log | stdbuf -oL tr '\r' '\n' \
#   | grep --line-buffered -E "PIPELINE_|DRAW_DONE|FREEZE_DONE|ROLLOUT_DONE|V5_GENERATION=|EXIT_CODE=|Error|Traceback"
```

| 参数 | 默认 | 含义 |
|---|---|---|
| `--run-id` | 必填 | run id，正式为 `v5-01` |
| `--release` | `newtask-v5` | 快照与产物的目录名 |
| `--draw-workers` / `--draw-gpus` | 1 / 沿用环境 | 抽签并行进程数；子进程按轮转领取物理 GPU 号写进 `CUDA_VISIBLE_DEVICES` |
| `--workers` / `--rollout-gpu` | 1 / `0` | 实跑 runner 的并行 worker 数与 GPU 号（worker 把它写进 `CUDA_VISIBLE_DEVICES`，即物理编号） |
| `--candidates-per-env` / `--max-reset-attempts` / `--select` | 10 / 30 / `0,3,6` | 口径 12：每环境攒 10 条 reset 成功、最多 30 次；按 index 0/3/6 选 3 条正式局 |
| `--label` | `run1` | 实跑轮次标签；V5 只跑这一轮 |
| `--resume` | 关 | 已有产物的步骤跳过（drafts／specs 本来就禁止覆盖；下游 freeze／run 仍会重新核验来源，陈旧产物会被拒） |
| `--dry-run` | 关 | 只打印四步完整命令，不执行 |

落点：抽签 `artifacts/newtask-v5/v5-01/draft/drafts.jsonl`；冻结 `scripts/configs/newtask-v5/v5-01/specs.jsonl`（进 Git）；
实跑 `artifacts/newtask-v5/v5-01/rollout/run1/`（`results.jsonl`、`summary.json`、`episodes/<Task>_episode_<n>/` 下的 h5 与视频）；
报告 `artifacts/newtask-v5/v5-01/report/generation_report.{md,json}`。

等价的分步写法（与 `pipeline --dry-run` 打印的完全一致，可以手工 `&&` 串起来）：

```bash
uv run --no-sync python -m scripts.parity.v4_specs draw --run-id v5-01 --tasks all \
  --sampling-config scripts/configs/newtask-v5/sampling_config.json --candidates-per-env 10 --max-reset-attempts 30 \
  --workers <抽签并行数> --gpus 0,1 --out artifacts/newtask-v5/v5-01/draft/drafts.jsonl \
&& uv run --no-sync python -m scripts.parity.v4_specs freeze --drafts artifacts/newtask-v5/v5-01/draft/drafts.jsonl \
  --sampling-config scripts/configs/newtask-v5/sampling_config.json --select 0,3,6 --candidates-per-env 10 \
  --out scripts/configs/newtask-v5/v5-01/specs.jsonl \
&& uv run --no-sync python -m scripts.parity.v4_rollout run --specs scripts/configs/newtask-v5/v5-01/specs.jsonl \
  --label run1 --tasks all --official-root artifacts/train-parity/local-smoke-01/official-src --workers <实跑并行数> --gpu 0 \
  --output artifacts/newtask-v5/v5-01/rollout \
&& uv run --no-sync python -m scripts.parity.v5_generation report --drafts artifacts/newtask-v5/v5-01/draft/drafts.jsonl \
  --specs scripts/configs/newtask-v5/v5-01/specs.jsonl --rollout artifacts/newtask-v5/v5-01/rollout/run1 \
  --candidates-per-env 10 --out artifacts/newtask-v5/v5-01/report
```

- **抽签多 worker**：`v4_specs draw --workers N` 按环境把任务分给 N 个 spawn 子进程（每进程独立 gym 环境）。每个环境的
  (episode, attempt, seed) 序列只由 `SEED_RULE` 决定，与 worker 数无关；合并时 header 只有一份，行按 header 的任务序、
  每环境内按抽签先后排列，**与单 worker 的 drafts.jsonl 逐行相同**（只有墙钟 `wall_s` 不同），freeze 直接读。`--workers 1`（默认）
  与改动前逐字相同。任一环境的子进程崩溃（如段错误）时整体失败、不写 drafts。
- **实跑**只跑一遍（口径 12），不跑 run2 / compare，H4 递补在本环境剩余候选里按 `1,2,4,5,7,8,9` 进行，不追加抽签。

### 5.3 生成报告（`v5_generation report`）

只读 drafts、specs、`results.jsonl`、各局 h5 与 `rng_trace.json`，打印计划 3.2 的判定行并写 markdown 与 JSON：

```text
V5_GENERATION=REPORT tasks=16 draft_ok=… rollout_ok=… backfilled=… selected_shortfall=… demo_frames_out_of_band=… outer_swap_mismatch=… bin_collision=… vr_min_participants=…
```

| 字段 | 怎么算 |
|---|---|
| `draft_ok` | 全部环境 reset 成功的候选数；逐环境表另列 `draft_attempted` / `candidate_shortfall`（= max(0, 10 − 成功数)）与抽签失败类别 |
| `rollout_ok` / `backfilled` / `selected_shortfall` | 与 `v4_rollout run` 的 `summary.json` 同口径；逐环境表另列 `rollout_attempted` 与 `by_class`（失败局的 `error_type` 计数） |
| `demo_frames_out_of_band` | PatternLock / RouteStick 每个成功局 h5 中 `episode_*/timestep_*/info/is_video_demo` 为真的帧数，落在 750～1050 之外的局数（口径 9；两环境取值见 1.15、1.16） |
| `outer_swap_mismatch` | VideoUnmaskSwap / ButtonUnmaskSwap 每局：规格 `actions.distractor_swap_pairs` 的窗口数（及 rng_trace 里若有的运行时逐窗记录）≠ `objects.n_swaps` 的局数（口径 4；字段形状见 1.7） |
| `bin_collision` | 实跑失败类别为 `BinCollisionError` 的局数；抽签期的同类失败另记在 JSON 的 `draft_bin_collision` |
| `vr_min_participants` | VideoRepick 每局参与交换的不同方块数的最小值（口径 10，应为 6）：优先规格 `actions.swap_pairs.<k>`，缺失时用 rng_trace 的运行时记录（字段形状见 1.9） |

字段名集中在 `v5_generation.py` 顶部的常量里；规格缺字段或形状认不出时对应项记 `N/A` 并在「提示」里写明，不会崩溃。

### 5.4 S5：V1 原三档 16×9（144 条）逐位对拍

比较器是 [parity/train_split_parity.py](parity/train_split_parity.py) 的既有 `run` / `compare`，不需要新代码。身份取默认的
`scripts/configs/newtask-v3/subset_manifest.json`（144 行 = 16 任务 × easy/medium/hard × 3 局）。基线侧在基线提交的工作树里、
V5 侧在 V5 工作树里各跑一遍**同一条命令**（本机、单 worker、相近负载，只跑 B 路）：

```bash
# <tree> 为该侧的工作树根目录，<side> 为 base 或 v5；两侧的 --output 都写到 V5 工作树下便于比较
tmux new-session -d -s v5-v1-<side> "set -o pipefail; cd <tree>; CUDA_VISIBLE_DEVICES=0 PYTHONUNBUFFERED=1 \
  uv run --no-sync python scripts/parity/train_split_parity.py run --paths B --workers 1 --gpus 0 \
  --official-root /data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/train-parity/local-smoke-01/official-src \
  --output <V5 工作树>/artifacts/newtask-v5/v1/<side> 2>&1 | tee <V5 工作树>/artifacts/logs/v5-v1-<side>.log; \
  echo \"EXIT_CODE=\$?\" >> <V5 工作树>/artifacts/logs/v5-v1-<side>.log"
```

两侧都跑完后逐位比较（`compare_h5_pair`：先整文件 SHA-256，不同再逐路径比 dtype/shape/attribute/`tobytes()`，不设容差）：

```bash
uv run --no-sync python scripts/parity/train_split_parity.py compare \
  --run base=artifacts/newtask-v5/v1/base --run v5=artifacts/newtask-v5/v1/v5 --pair base/B:v5/B \
  --output artifacts/newtask-v5/v1/compare
# 输出：H5_PARITY pair=base.B|v5.B compared=144 sha_equal=… field_mismatch=…
#       （另有「仅一侧存在的身份」「伴生文件散列不同」两类提示行；逐局明细在 <output>/h5_pairs.jsonl）
```

判定：`compared=144 sha_equal=144 field_mismatch=0` 且没有「仅一侧存在」提示行，即计划的 `NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0`。
一侧演示失败没有 h5 的身份会计入 `field_mismatch`（记「hdf5 缺失或不唯一」），不会被静默跳过。
⚠ 计划 runbook 里的 `run --subset 16x9` 与 `compare <dir> <dir>` 两种写法在代码里不存在，以本节为准。
