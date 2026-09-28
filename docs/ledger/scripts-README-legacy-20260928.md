> **本文件为历史留档（12.214 之前的 `scripts/README.md`，2026-09-28 先改名 `scripts/README-legacy.md`、同日归档到 `docs/ledger/`，不再维护）。现行说明见 [`scripts/README.md`](../../scripts/README.md)。**

# scripts/ 说明：robomme_hard 拆包后的目录、V6 四档新值与历史说明

**拆包后（12.205～12.210，[0927 计划](../plans/0927-robomme-hard-layered-plan.md)）的布局**：

| 位置 | 内容 |
|---|---|
| `dataset_replay.py`、`evaluation.py`、`run_example.py`、`evaluation_hard.py` | 四个顶层入口（P1）；前三者与官方逐字节相同；`evaluation_hard.py` 与 `evaluation.py` 只差 4 处（import、`dataset="test-hard"`、取 tier、按档 `max_steps`） |
| `injection-dev/` | 新值档生产链路（不随包分发，路径直跑）：`freeze_specs.py`（第一阶段：定规则 → 抽签 → 封存，只落一份 jsonl）、`generate_h5.py`（第二阶段：continue 状态机回写／replay 只读重放）、`_extract/_draw/_freeze/_rollout/_report.py`、一次性迁移 `migrate_smvla_specs.py`、seed 公式与 16 任务规范序 `seed_layout.py`（12.214 自 `scripts/` 顶层移入，调用方把本目录插入 `sys.path` 后按模块名导入）；`site/` 为只读出图与候选核对工具 |
| `parity/` | 只做「与官方比」：S0 基线设施 `train_split_*.py`、vendor 的官方编排 `official/`（`d53f21a7` 四文件）、G1 守卫 `upstream_guard.py`、三侧对拍入口 `hard_parity.py`、拉取 `hard_pull.py`、回归 `hard_regression.py`；详见 [parity/README.md](../../scripts/parity/README.md) |
| `configs/` | 12.214 起只留两样：`newtask-v6/v6-02/`（S4 生成所用规格 xhard1～xhard4 四份 `specs.jsonl`，只读留档）、`hard-parity-tolerances.json`（对拍容差层阈值）。原 `newtask-v3/`（原三档 144 身份清单与官方 train 元数据）与 `newtask-v6/smvla-smoke-0927/` 已从工作树删除，用 `git show 6e70c0bf:<原路径>` 取回 |

新值档环境源码在 `src/robomme_hard/`（`src/robomme/` 与官方 `1fadc0ec` 逐字节相同）；四档规格随包分发在 `src/robomme_hard/env_metadata/test-hard/xhardN/specs.jsonl`，评估用 `BenchmarkEnvBuilder(env_id, dataset="test-hard")`，说明见 [src/robomme_hard/README.md](../../src/robomme_hard/README.md)。

**第一节**记录十六个环境新值档的配置字段、规格字段与行为（源码现在 `src/robomme_hard/robomme_env/` 下，文中「V5 现行代码」均指该历史版本的写法）。**第二～五节**是 V4/V5 的全局改动、快照字段、推理兼容与三步命令，所引模块 `scripts/parity/{v4_specs,v4_rollout,v5_generation}.py`、`scripts/eval/` 与 `configs/newtask-v4`、`newtask-v5` 已于拆包阶段 2 删除，正文整段移出，原文见 `git show 7a6cee35:scripts/README.md`。**第六节**为 V6 发布说明（命令已改到 `injection-dev/site/`）。

## 第一节　逐环境改动

**怎么读：**

- **配置字段**：当时写在 `configs/newtask-v5/sampling_config.json` 里（V4 为 `configs/newtask-v4/sampling_config.json`，
  两份均已随拆包阶段 2 删除，git 历史可取回；现行新值配置在包内规格 header 的 `sampling_config`），路径相对于 `tasks.<环境>`。
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

> V5：修方块障碍框退化 + 同色成团上限（报告 [S3e](../validation/newtask-v5/20260924-s3e-binfill.md)，计划 2.12）。

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

> V5：取消边角偏置、6 块两两 ≥ 0.08 m、精确 OBB、每块 1024 次（报告 [S3f](../validation/newtask-v5/20260924-s3f-pickxtimes-swingxtimes.md)，计划 2.13）。

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

> V5：共用循环加显式 xhard 分支、6 块两两 ≥ 0.08 m、精确 OBB（报告 [S3f](../validation/newtask-v5/20260924-s3f-pickxtimes-swingxtimes.md)，计划 2.14）。

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
> 所以别名只是为今后在 xhard 路径上抛错备用（报告 [S3i](../validation/newtask-v5/20260924-s3i-obb-fix-pickhighlight-videoplace.md) 第三节）。

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

> V5：干扰容器 3 → 15、贴身环带、接入四个 Unmask 共用的统一采样器，揭示时各容器停独立点（报告 [S3b](../validation/newtask-v5/20260924-s3b-videounmask-buttonunmask.md)、
> 共用设施 [S2c](../validation/newtask-v5/20260924-s2c-unmask-distractor-sampler.md)，计划 2.2、2.3）。

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

> V5：同 VideoUnmask，干扰容器 14 个（报告 [S3b](../validation/newtask-v5/20260924-s3b-videounmask-buttonunmask.md)，计划 2.4）。

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

> V5：干扰容器 3 → 10（环带沿用 V4）、外环随内环同窗交换、两对联合碰撞证明、内环对内环 reset 预判（报告 [S3h](../validation/newtask-v5/20260924-s3h-unmaskswap.md)、
> 共用设施 [S2b](../validation/newtask-v5/20260924-s2b-multi-swap-sweep.md) / [S2c](../validation/newtask-v5/20260924-s2c-unmask-distractor-sampler.md)，计划 2.5、2.6）。

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

> V5：同 VideoUnmaskSwap，另加外环路径离按钮中心的约束、内环静默截断改报错（报告 [S3h](../validation/newtask-v5/20260924-s3h-unmaskswap.md)，计划 2.7）。

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

> V5：最小中心距 0.12 m、6 块 `k%6` 轮流发起、reset 时从 3 个最近可行者里规划搭档、按钮底座纳入扫掠障碍（报告 [S3g](../validation/newtask-v5/20260924-s3g-videorepick.md)，计划 2.15）。

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

> V5：配置字段、规格字段与 subgoal 流程都不变，**只修方块障碍框**（计划 2.16、L2 b；报告 [S3i](../validation/newtask-v5/20260924-s3i-obb-fix-pickhighlight-videoplace.md)）：
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

> V5：同 VideoPlaceButton，只修方块障碍框（报告 [S3i](../validation/newtask-v5/20260924-s3i-obb-fix-pickhighlight-videoplace.md)）。
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
> [S3i](../validation/newtask-v5/20260924-s3i-obb-fix-pickhighlight-videoplace.md)）。修复前 83% 的局里至少有一对方块间距不到名义 0.04；
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

> V5：删掉 `corner_bias`，杆/goal/方块都不得落进桌面中心 R = 0.05 m 的圆；执行段方块不避让演示段方块（报告 [S3c](../validation/newtask-v5/20260924-s3c-movecube.md)，计划 2.9）。

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

> V5：删第 4 根杆的专用采样器与贴近带，4 根一个循环；杆与杆轮廓间隔 > 0.03 m、离孔板 > 0.01 m（报告 [S3d](../validation/newtask-v5/20260924-s3d-insertpeg.md)，计划 2.8）。

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

> V5：布局不动；节点数固定 25、搜索预算 20000、搜索耗尽抛错（报告 [S3a](../validation/newtask-v5/20260924-s3a-patternlock-routestick.md)，计划 2.10）。

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

> V5：L `[12,15]` → `[15,21]`，L 范围冻进 decision（报告 [S3a](../validation/newtask-v5/20260924-s3a-patternlock-routestick.md)，计划 2.11）。

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

## 第二～五节（历史，已移出）

V4/V5 的全局改动表、`v4-specs/1` 快照与结果字段、`from_v4_specs` 推理兼容、抽签／冻结／实跑／推理三步命令、V5 流水线与 V1 对拍命令，所依赖的脚本与配置已于拆包阶段 2（12.207）删除。完整原文：

```bash
git show 7a6cee35:scripts/README.md | sed -n '/^## 第二节/,/^## 第六节/p'
```

现行对应物：快照字段见 `src/robomme_hard/env_record_wrapper/hard_specs.py`（`hard-specs/2`：签 + 结果两段、`identity_sha256`／`delivery_sha256`）；抽签／冻结见 `injection-dev/freeze_specs.py`；实跑见 `injection-dev/generate_h5.py`；推理见 `dataset="test-hard"` 与 `scripts/evaluation_hard.py`；原三档对拍见 `parity/hard_parity.py`。

## 第六节　V6 四档新值发布

范围与授权以 [V6 计划](../plans/0925-newtask-release-v6-plan.md) 第 5.3 节为准；配置为包内 xhard4 规格 header 的 `sampling_config`（原 V6 快照 `configs/newtask-v6/sampling_config.json` 已删，与之逐任务相同）。本节说明本轮用法，不把尚未完成的检查写成通过。

### 6.1 档位、规模与失败预算

13 个原版有难度梯度的任务使用 `xhard1`～`xhard4`：BinFill、PickXtimes、SwingXtimes、PickHighlight、VideoUnmask、ButtonUnmask、VideoUnmaskSwap、ButtonUnmaskSwap、VideoRepick、PatternLock、RouteStick、VideoPlaceButton、VideoPlaceOrder。MoveCube、InsertPeg、StopCube 只有 `xhard4`，不接受另外三个新档。合计 `13×4＋3×1＝55` 格，每格 10 个成功候选、3 个成功正式轨迹目标，即 **550 候选、165 条正式轨迹目标**。

| 批次 | 固定范围或上限 | 失败处理 |
|---|---|---|
| S2 新档演示探针 | 144 次固定身份尝试 | 每身份一次，失败留在分母，不补抽、不补跑 |
| S3 原三档对拍 | 16 任务×3 档×3 局＝144 次 | 复用 S0 基线，同 seed，不换 seed 补成功，不比较任何新档 |
| S4 候选 | 每格 10 成功或最多 60 次总抽签尝试，合计最多 3300 次 | 失败计入上限；不是每个候选各重试 60 次 |
| S4 正式轨迹 | 每格首选候选 index `0,3,6`；最多尝试该格已有 10 候选，合计最多 550 次 | 按当时 `BACKFILL_ORDER` 的 `1,2,4,5,7,8,9` 递补，成功 3 条或已有候选用尽即停 |
| 额外抽样与重跑 | 0 | 不恢复额外 200 reset、分布补样、run2 或整批重跑 |

候选不足、正式轨迹不足及各失败类别分别报告；**预算中的165是成功目标，最终实测亦为165程序成功，但另有2条已披露题意问题**。S2＋S3＋S4 的轨迹尝试总上限为 `144＋144＋550＝838`，不追加独立冒烟。逻辑候选／轨迹尝试与环境构造、显式 reset 调用不是同一计数；实际调用数没有记录时写“未观测”，不把 3300 当作所有阶段的 reset 调用总数。

### 6.2 本轮产物与接纳条件

本机汇集根为 `artifacts/newtask-v6/v6-01/`，四个档位分别落在 `xhard1/`、`xhard2/`、`xhard3/`、`xhard4/` 下。每档包含 `draft/drafts.jsonl`、`specs.jsonl`、`rollout/run1/` 与 `report/`；逐局 HDF5、视频及回放记录在 `rollout/run1/episodes/`。以实际清单核对存在性与完整性，不以目录存在认定完成。

本轮生成当时沿用已删的 `parity/v5_generation.py`（见 git 历史）的 `pipeline --release newtask-v6 --tiers`，明确指定 `--seed-profile v6`、`--candidates-per-env 10`、`--max-reset-attempts 60`、`--select 0,3,6`，每个集群席位最多 16 worker。集群运行参数、席位和中转路径由本轮执行记录固定；不要直接运行第五节的 V5 示例，也不要把旧预备资料当作当前资源状态或额外生成授权。

用户最新资源决定：原占位作业 `61890467`、`61890468` 跑完后继续保留，不自动取消；另提交相同规格的 48 小时占位作业 `62018665`、`62018666`，当前四席均保留。新增席位不等于新增生成、重跑或故障恢复预算授权，具体状态以实时调度查询为准。

最终执行快照：550 个候选已足额；[候选取值报告](../../artifacts/newtask-v6/s4-launch/verification/candidate-values.json) 已核对 520 个梯度候选，`CANDIDATE_VALUES=PASS`。S4 原运行143成功，获批恢复实际23次、22成功、1次真正任务失败，现共 **165程序成功、55格各3条、短缺0**；恢复最多76次的授权未用满，原成功及真正任务失败没有重跑。原60次基础设施失败与8次中断未知完整保留，不被恢复结果抹掉。实际交付身份以[最终清单](../validation/newtask-v6/records/final-delivery.json)为准，不能遍历失败目录中的HDF5推断交付。S3已通过144条严格对拍；`accepted=true`仅指原V1及来源／文件闸门，清单另以`semantic_status=KNOWN_ISSUES`披露VPB/xhard3/episode3、6的题意问题。用户决定仅网站注明、不修数据，不把程序成功写成题意无缺陷。

四份550条冻结规格当时逐字复制至`configs/newtask-v6/v6-01/`（拆包阶段 2 删除，git 历史可取回；S4 实际生成所用规格见 `configs/newtask-v6/v6-02/`）。规格中的`selected`是原首选；实际成功包含递补，例如InsertPeg/xhard4最终为episode 6、2、4。完整执行、失败与恢复边界见[S4报告](../validation/newtask-v6/20260926-s4.md)。

**S3 原三档严格对拍已真实通过：`NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0`。** 两侧各144个成功终态、75404时间步，身份完整，无单侧缺失；本轮证明不外推到新档题意。S2 的固定探针失败及 S4 的候选拒绝、递补、短缺照实报告，不通过重试挑成功，也不把媒体存在或进程退出 0 当作任务成功。完整结论见[S5总报告](../validation/newtask-v6/20260926-final.md)。

### 6.3 纯离线核对候选实际取值

入口 [v6_candidate_values.py](../../scripts/injection-dev/site/v6_candidate_values.py) 只读取四档原始 drafts、V6 配置及各档来源指纹的一致性，不创建环境、不执行 reset。它逐条核对 **13×4×10＝520** 个梯度候选的实际取值与配置区间、身份覆盖及失败尝试信息；三个只有 `xhard4` 的任务不计入这 520 条。

四档原始 drafts 汇集完整后，在仓库根执行一次，输出文件必须尚不存在：

```bash
UV_CACHE_DIR="$HOME/.cache/uv" uv run --no-sync python scripts/injection-dev/site/v6_candidate_values.py \
  --drafts artifacts/newtask-v6/v6-01/xhard1/draft/drafts.jsonl \
  --drafts artifacts/newtask-v6/v6-01/xhard2/draft/drafts.jsonl \
  --drafts artifacts/newtask-v6/v6-01/xhard3/draft/drafts.jsonl \
  --drafts artifacts/newtask-v6/v6-01/xhard4/draft/drafts.jsonl \
  --out artifacts/newtask-v6/v6-01/report/candidate-values.json
```

输出 `CANDIDATE_VALUES=PASS|FAIL`，并列 `cells`、`candidates`、`mismatches`、`shortfall`、`input_errors`。缺失候选、取值越界、来源不匹配或缺少失败尝试信息都会失败；不能用只含成功候选的冻结 specs 冒充完整 drafts。该检查证明本批候选的取值符合配置，不证明分布均匀、不证明全部可能取值，也不触发额外采样。

### 6.4 难度梯度与视频网站

**现行版本为`artifacts/newtask-v6/site-v10/`。** VPB／VPO的30个样例按各自真实HDF5边界展示原子子目标，标签为人读表述（正确／干扰方块及颜色、台代号、按钮前／后第几次放置），列表上方给出中文题目问句并标出「题目所问」的那一步；方块身份由`injection-dev/site/v6_site_catalog.py::label_flow`按位置链从坐标反推并以源码档定值与题目颜色校验。只列“演示子目标／执行子目标”，切换样例同步切换列表；网页不再显示图像坐标（保留在审计JSON），连续同名静止保留。30样例逐项列表及播放的Playwright检查通过，页面错误0，移动截图核验通过。VPB顶部已知问题框保留；用户只要求网站注明，不改环境源码或数据、不补跑。213媒体与预览保持不变，下面全213播放结论属于v4的相同媒体。

**v4历史验证：`artifacts/newtask-v6/site-v4/`包含16任务、71卡片、213个主视频，API确认每卡3个样例；213条真实界面逐视频测试全部通过，失败0、过短0、页面错误0。** 用户报告SwingXtimes/xhard4示例7的片段2／2无法观看，Playwright复现该尾片只有1帧、0.033333秒，播放约50毫秒即结束。原251文件中38个`NO_OBJECT`尾片只有1～4帧，现仅从展示目录排除，原数据保留。

旧验证仅按任务抽查部分样例，没有覆盖全部251片段；首帧解码或JPEG预览不能证明可观看。补做v3全部251片段的真实界面播放／seek／恢复检查，结果213条PASS、38条`TOO_SHORT_FOR_TRAJECTORY`、FAIL 0、页面错误0；不能把38条过短片段算作通过。v4另做213条全测，每条核验解码尺寸／时长、播放推进至少0.25秒、seek后继续推进至少0.2秒及样例按钮匹配URL，均通过；这是逐视频交互验证，不是全帧播放。原用户位置的桌面与390像素宽移动测试也通过，主视频时长36.8667秒。下面保留v3历史，v4真实证据为`site-v4/playwright-all-results.json`及`playwright-detail/`。

网站地址：[V6难度梯度与视频](http://141.212.115.116:8060/)。按用户要求逐任务、逐难度单独介绍梯度并提供视频，不合并成一张表。历史v3为16任务、71张卡片、251个视频文件；来源为165条新值程序成功轨迹与48条原hard轨迹，部分轨迹含多个视频文件。现行213主视频剔除了展示中的38个状态尾片。S3已由独立真实对拍证明通过，网站只展示视频与难度，不替代该证明；VPB题意问题按用户决定明确保留。

目录生成入口为 `uv run --no-sync python scripts/injection-dev/site/v6_site_catalog.py`，默认输出初版`artifacts/newtask-v6/site/`；当前服务明确使用`artifacts/newtask-v6/site-v10/`，不能误用默认目录替代。生成器拒绝覆盖已有目录文件，不为重建网站重跑任何轨迹。服务运行在唯一tmux会话`v6-gradient-site-8060`，实际入口为：

```bash
UV_CACHE_DIR="$PWD/artifacts/cache/uv" PYTHONUNBUFFERED=1 uv run --no-sync python \
  scripts/injection-dev/site/v6_site.py --host 0.0.0.0 --port 8060 \
  --site-dir artifacts/newtask-v6/site-v10
```

当前服务已启动，不重复占用8060端口；保留网站会话和产物，不自动清理。浏览器已验证16任务播放、拖动进度与样例切换，搜索、移动导航和无表格布局通过，JavaScript错误0。截图、首帧预览与验证边界见[网站报告](../validation/newtask-v6/20260926-site.md)。
