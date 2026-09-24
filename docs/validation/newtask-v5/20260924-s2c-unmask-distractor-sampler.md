# V5 S2c：四个 Unmask 环境的干扰容器统一采样器（L13）与独立停放点（L14）

> 日期 2026-09-24；worktree `/data/hongzefu/robomme_v5_wt/s2c`（分支 `v5wt-s2c`，基于 `f5b6a17`），改动未 commit。
> 依据：`NEWTASK_RELEASE_V5_PLAN.md` 1.4 L6～L23、2.2～2.7、3.5 P5、第二部分「一」S2 行（`utils/unmask_distractors.py` 停放 helper）。
> 本步是**共用基础设施**，不接入任何环境：VU / BU / VUS / BUS 四个环境文件零改动，由 S3 的两个 agent 接入。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 |
|---|---|---|---|
| `src/robomme/robomme_env/utils/unmask_distractor_sampler.py`（新） | 整个模块 | 统一采样器、统一配置与 schema、四环境 V5 预设、记录纪律驱动、建 actor、精确障碍框、独立停放点 helper | L13 (a)、L14 (a)、N17/N18 |
| `tests/lightweight/test_v5_unmask_distractor_sampler.py`（新） | 26 条测试 | 纯几何规则、复现性、随机调用序列、回调、N18 记录纪律、回放复核、停放 helper、密度推导锁定 | 任务第 5 条 |

没有改动任何已被 git 跟踪的文件：`unmask_distractors.py`、`unmask_swap_xhard.py`、`statechange.py`、
`object_generation.py`、`bin_collision.py`、`xhard.py` 与四个环境文件都只被只读引用（`git diff --stat` 为空）。

## 二、设计

### 2.1 统一配置（四环境同一套键）

```python
DISTRACTOR_CFG_KEYS = ("count", "ring_max_abs_xy", "cube_count_range", "color_pool",
                       "color_rule", "min_gap_factor", "max_trials")
```

`V5_DISTRACTOR_PRESETS[<Env>]` 给出四个环境的 V5 值，环境文件的 `XHARD_DISTRACTOR` 直接深拷贝即可：

| 环境 | count | ring_max_abs_xy | cube_count_range | 其余 |
|---|---|---|---|---|
| VideoUnmask | 15 | [0.2425, 0.3289] | [7, 8] | color_pool 黄/青/品红、`balanced_cycle`、min_gap_factor 0.75、max_trials 1024 |
| ButtonUnmask | 14 | [0.2425, 0.3289] | [7, 7] | 同上 |
| VideoUnmaskSwap | 10 | [0.2675, 0.45]（V4 环带，L16 b） | [5, 5] | 同上 |
| ButtonUnmaskSwap | 10 | [0.2675, 0.45] | [5, 5] | 同上 |

`parse_distractor_cfg` 校验：键集合必须恰好是上面 7 个；`0 < r_in < r_out`；`0 ≤ lo ≤ hi ≤ count`（V4 VU/BU 的
`high > 3` 限制随三色轮转取消，计划 2.3）；`color_pool` 必须等于全局 `xhard.DISTRACTOR_COLORS`（**不改全局色板**，
PickXtimes/SwingXtimes 也用）；`color_rule` 只认 `balanced_cycle`；`max_trials ≥ 1`。

### 2.2 采样规则与随机调用顺序

`sample_distractor_layout(cfg, *, obstacles, generator, cube_half_size, extra_reject=None) -> DistractorLayout`，**纯几何**：

1. 逐容器最多 `max_trials` 次：`x, y = rand·2R − R`（2 次 rand）→ max-norm 环带 → 精确 8 角点可见
   （`visible_in_camera(bin_corners(x, y, 任意 yaw 外接半边, 高度))`，与 V4 VU/BU 同一判据）→ OBB 间距
   （候选中心到每个障碍 OBB 的点距 ≥ 0.0275 + min_gap）→ 抽 yaw（1 次 rand）→ `extra_reject(i, x, y, yaw, 已放列表)`；
2. 已放的干扰容器以**精确**矩形（由 x、y、yaw 经 `bin_actor_pose` 算出，外廓半边 0.03，外扩 min_gap）进障碍；
3. 全部放完后：`n = randint(lo, hi+1)` → `cube_bins = randperm(N)[:n]` → `color_order = randperm(3)`；
   第 j 个 cube 颜色 `DISTRACTOR_COLORS[color_order[j % 3]]`，名字 `distractor_cube_<j>_<colour>`。

与 V4 VU/BU 相比，不给回调时**随机调用的次序与次数逐项相同**（V4 颜色是 `randperm(3)[:n]`，同一次 randperm），
单测 `test_随机调用序列与V4的VU_BU同构` 用重放生成器锁住。VU/BU 仍用主场景 generator、放在全部既有取值点之后，
因此内环取值与 V4 同 seed 不变（N5 字面成立）。Swap 两环境改用本采样器后，干扰容器从「每次尝试都抽 yaw、
圆间距 0.04、线性可见性、512 次」变为上述统一规则——这是计划 1.5 与 2.6 表明确要求的变化。

放不下时抛 `DistractorPlacementError`（`SceneGenerationError` 的子类，带 `placed` 个数）。

### 2.3 障碍框：精确 OBB，不走 trimesh

`obstacle_obbs(avoid, min_gap)` 收集口径与 V4 `_obstacle_obbs` 相同（预制三元组原样、`(actor, pad)` 按 pad、裸 actor 按
min_gap 外扩），区别是 actor 用 `actor_obb2d_exact`：读真实 `PhysxCollisionShapeBox`，直立物体取水平投影最长的两根轴，
否则退回世界轴对齐框；读不到盒体时退回 V4 的 trimesh 路径。这样绕开计划 2.0① 的「2D 框退化成线段」缺陷。
本机模拟器实测：VU/BU 各两个 seed 的 8 个内环容器，trimesh 路径**都没有退化**（共 0/32，容器三维尺寸 0.06×0.06×0.054 不是正方体），
所以对容器而言精确框与 V4 结果一致；对被藏 cube 等正方体更稳。

### 2.4 记录纪律（N18）与回放复核（N17 精神）

- `commit_distractor_layout(layout, *, cfg, recorder, obstacles, cube_half_size, spec_prefix, decision_prefix, extra_reject)`：
  把**已被接受**的布局写进规格，每个取值点只调一次 `recorder.value`；回注模式返回冻结值拼成的布局，并用同一套规则
  （含 `extra_reject`）复核，违反即抛 `SceneGenerationError`。
- `resample_distractor_layout(cfg, *, obstacles, generator, cube_half_size, recorder, accept, max_attempts, extra_reject, …)`：
  整段重抽驱动。每次尝试「纯几何放置 → `accept(layout)`」，放不满与 accept 拒绝都记一次失败；第一次被接受时
  `record` 尝试序号与此前失败原因，再 `commit`；全部失败 `record` 后抛 `SceneGenerationError`。`accept` 可以接着抽同一条流
  （Swap 外环发起者的 `randperm(count)`）。回注模式下若冻结布局与本次重抽被接受的布局不同，`accept` 的附带结果（交换对）
  已无法对应，默认抛错（`require_replay_match=True`）。

统一 schema（`spec_prefix` 默认 `objects.distractors`，与 V4 VU/BU 路径一致）：

| 路径 | 方式 | 内容 | decision_key |
|---|---|---|---|
| `objects.distractors.requested` | record | 请求个数 | — |
| `objects.distractors.bins.<i>` | value | `[x, y, yaw_deg]` | `xhard.distractor.ring_max_abs_xy` |
| `objects.distractors.placed` / `.trials` | record | 实际个数 / 每个容器用掉的尝试次数 | — |
| `objects.distractors.cube_count` | value | 含 cube 个数 | `xhard.distractor.cube_count_range` |
| `objects.distractors.cube_bins` | value | 第 j 个 cube 所在容器序号 | `xhard.distractor.count` |
| `objects.distractors.color_order` | value | `randperm(3)` | `xhard.distractor.color_rule` |
| `objects.distractors.cube_colors` / `.cube_names` | record | 派生的颜色名 / actor 名 | — |
| `layout.distractor_layout_attempts` / `layout.distractor_layout_failures` | record | （整段重抽）被接受的是第几次 / 此前失败原因 | — |

计划正文写的 `objects.distractor_cube_bins` 落为 `objects.distractors.cube_bins`（沿用 V4 VU/BU 已有路径）。
V4 Swap 的 `layout.distractors.<i>`、`objects.distractors.n_with_cube` 不再使用。

### 2.5 建 actor

- `build_distractor_actors(env, layout, *, hidden_half_size) -> (bins, cubes)`：容器 `distractor_bin_<i>`（`build_bin`，`[x, y, 0.002]`，yaw），
  cube `distractor_cube_<j>_<colour>`（`spawn_fixed_cube`，放在 `bins[cube_bins[j]]` 的 XY，yaw 0，dynamic）；名字重复直接抛错。
  不设 `bin_<i>` 属性，不进 `spawned_bins`。
- `distractor_cube_bin_pairs(layout, bins, cubes) -> [(cube_j, bin)]`：Swap 外环 cube 跟随用。
- `spawn_distractor_layout(env, *, cfg, avoid, generator, recorder, hidden_half_size, spec_prefix, decision_prefix) -> (bins, cubes, layout)`：
  VU/BU 的一站式入口（避让列表 → 采样 → commit → 建 actor → 容器追加进 `avoid`）。

### 2.6 独立停放点（L14）

- `xhard_park_point(group, index) -> float32 xyz`：四组 `distractor_bin` / `distractor_cube` / `bin` / `hidden_cube`，每组 64 个点
  （4 行 × 16 列），原点 `(20, 20, 10)`，间距 0.5 m。所有 256 个点两两 ≥ 0.5 m，离旧停放点 (10,10,10) > 14 m，在前视相机背后。
  物体外接圆直径约 0.085 m，窗口内每个控制步都被传送回停放点（自由下落不到 2 cm），彼此永不接触。纯函数，与调用次序无关。
- `lift_and_park_back_to_original(env, obj, start, end, cur, park_xyz)`、`lift_and_park_onto(env, obj_a, obj_b, start, end, cur, park_xyz)`：
  与 `statechange.lift_and_drop_objects_back_to_original` / `lift_and_drop_objectA_onto_objectB` **时间线逐步相同**（窗口、半窗落回步
  `min(end, start + max(1,(end−start)//2))`、终点放到 obj_b 当前 XY 与 obj_a 原高度都不变），唯一差别是「远处」换成停放点；
  缓存属性 `_xhard_park_cache` / `_xhard_park_onto_cache` 与 statechange 的分开。**`statechange.py` 未改。**
- 组合入口：`reveal_distractor_bins_parked(env, *, start_step, end_step, cur_step)`（`reveal_distractor_bins` 的停放版）、
  `reveal_actors_parked(env, actors, *, group, …)`、`park_cubes_onto_bins(env, pairs, *, group, start_step, end_step, cur_step)`。

## 三、两类环境怎么接入（给 S3 的调用示例）

### 3.1 VideoUnmask / ButtonUnmask（S3b）

```python
from .utils.unmask_distractor_sampler import (
    V5_DISTRACTOR_PRESETS, spawn_distractor_layout, reveal_distractor_bins_parked, reveal_actors_parked)

XHARD_DISTRACTOR = copy.deepcopy(V5_DISTRACTOR_PRESETS["VideoUnmask"])   # BU 用 "ButtonUnmask"

# _load_scene 末尾，原 spawn_ring_distractor_bins 调用处（仍在全部既有取值点之后、用主场景 generator）：
if xhard:
    self.distractor_bins, self.distractor_cubes, self.distractor_layout = spawn_distractor_layout(
        self,
        cfg=decision_cfg["xhard"]["distractor"],
        avoid=avoid,                       # BU 的 avoid 里已有按钮 OBB 预制三元组
        generator=generator,
        recorder=self._spec,
        hidden_half_size=self.cube_half_size / hidden_cfg["half_size_divisor"],
    )
    add_distractor_misgrasp_failure(self, self.task_list)

# step：原 reveal_distractor_bins(...) 换成
if self.difficulty == "xhard":
    reveal_distractor_bins_parked(self, start_step=win["start_step"], end_step=win["end_step"], cur_step=timestep)
```

VU 传 15 个、环带 [0.2425, 0.3289]、cube [7,8]；BU 传 14 个、同一环带、cube [7,7]（都已在预设里）。
`decision.xhard.distractor` 的键从 V4 的 6 个变成统一的 7 个（新增 `color_rule`），`assert_native_decision` 对 xhard 子键只校验结构，S3 接入时注意同步相关单测。

**建议（见「待用户决策」第 1 条）**：xhard 下内环 8 个容器也改停独立点。原三档那段 `for i in range(step_bin_scan)` 循环不能动，可以在 xhard 分支里另写：

```python
if self.difficulty == "xhard":
    reveal_actors_parked(self, self.spawned_bins, group="bin", start_step=…, end_step=…, cur_step=timestep)
    reveal_distractor_bins_parked(self, start_step=…, end_step=…, cur_step=timestep)
else:
    for i in range(step_bin_scan): lift_and_drop_objects_back_to_original(...)   # 原样
```

### 3.2 VideoUnmaskSwap / ButtonUnmaskSwap（S3h）

```python
from .utils.unmask_distractor_sampler import (
    V5_DISTRACTOR_PRESETS, obstacle_obbs, resample_distractor_layout, build_distractor_actors,
    distractor_cube_bin_pairs, reveal_distractor_bins_parked, park_cubes_onto_bins)

XHARD_DISTRACTOR = copy.deepcopy(V5_DISTRACTOR_PRESETS["VideoUnmaskSwap"])   # BUS 用 "ButtonUnmaskSwap"

def _spawn_xhard_distractors(self, button_obbs=()):          # 仍是 _load_scene 的最后一句（N14）
    cfg = self._sampling["decision"]["xhard"]["distractor"]
    gen = distractor_generator(self.seed)                    # 独立流，主流一次不多抽
    chs = self.cube_half_size
    obstacles = obstacle_obbs(list(self.spawned_bins) + list(button_obbs), chs * cfg["min_gap_factor"])
    seq = ...                                                # 内环预演（S3h：predict_swap_sweeps 的扩展版）
    # 内环对内环 reset 预判（L20）不属于干扰采样，放在这之前，拒绝即 SceneGenerationError

    def extra_reject(i, x, y, yaw, placed):                  # H1：候选与任一段内环扫掠相交即拒绝；不许抽随机数
        cand = ObjectState(f"distractor_bin_{i}", *bin_actor_pose([x, y], yaw, chs), bin_shape_specs(chs))
        return any(check_swap_sweep(a, b, [cand], sweep_index=k, stage="distractor")[1] is not None
                   for k, (a, b) in enumerate(sweeps))       # 或 S2 新的 check_multi_swap_sweep + 预筛

    def accept(layout):                                       # 外环规划：perm=randperm(count) 从同一条流抽
        plan = plan_distractor_swaps(gen, layout, seq, ...)  # S3h 实现，L17～L19/L21
        return (True, plan) if plan.ok else (False, f"window_{plan.fail_win}")

    layout, plan = resample_distractor_layout(
        cfg, obstacles=obstacles, generator=gen, cube_half_size=chs, recorder=self._spec,
        accept=accept, max_attempts=16, extra_reject=extra_reject)
    self.distractor_bins, self.distractor_cubes = build_distractor_actors(
        self, layout, hidden_half_size=chs / self._sampling["positions"]["hidden_cube"]["half_size_divisor"])
    self.distractor_cube_bin_pairs = distractor_cube_bin_pairs(layout, self.distractor_bins, self.distractor_cubes)
    self.distractor_cube_colors = layout.cube_colors
    # plan 的 swap_order 走 self._spec.value("objects.distractors.swap_order", …)，配对与回退走 record（S3h）
```

VUS/BUS 都传 10 个、V4 环带 [0.2675, 0.45]、cube [5,5]（预设）。BUS 的按钮 OBB（`build_button` 返回的预制三元组）直接进 `obstacle_obbs`，
不再像 V4 那样按外接圆近似。

`step` 里（全部写在 AST 锁定的 `for i in range(len(self.swap_schedule))` 循环**之外**，N14）：

```python
if self._is_xhard:
    reveal_distractor_bins_parked(self, start_step=0, end_step=self.swap_window_start, cur_step=timestep)
...
# 内环 cube：xhard 下改用停放版（原三档的 lift_and_drop_objectA_onto_objectB 循环原样保留在 else 分支）
park_cubes_onto_bins(self, self.cube_bin_pairs, group="hidden_cube",
                     start_step=self.swap_window_start, end_step=self.swap_schedule[-1][3], cur_step=timestep)
# 外环 cube 跟随外环容器
park_cubes_onto_bins(self, self.distractor_cube_bin_pairs, group="distractor_cube",
                     start_step=self.swap_window_start, end_step=self.swap_schedule[-1][3], cur_step=timestep)
```

内环容器在 `[0, 64)` 的锁定段同样可以按 3.1 的建议改用 `reveal_actors_parked(..., group="bin")`。

### 3.3 `reveal_distractor_bins` 等现有揭示逻辑怎么切

- `unmask_distractors.reveal_distractor_bins` **本步未改**（现有单测 `test_v4_xhard_unmask_distractor_reveal.py` 锁着它走 statechange 的 (10,10,10)）。
  S3 接入时两种做法任选其一：①四个环境 step 里把调用直接换成 `reveal_distractor_bins_parked`（推荐，签名相同）；②把
  `reveal_distractor_bins` 的函数体改成调用 `reveal_distractor_bins_parked`。两种做法都要把该测试里「与 statechange 同机制、停在 (10,10,10)」
  的断言改为 V5 语义（每个干扰容器停在 `xhard_park_point("distractor_bin", i)`，落回步不变）。
- `unmask_distractors.spawn_ring_distractor_bins` 与 `unmask_swap_xhard.sample_distractors` / `build_distractors` 接入后成为死代码，
  由 S3 在接入同一提交里删除或保留（保留不影响行为）；`visible_on_camera` 线性近似同理。
- 误抓判失败 `add_distractor_misgrasp_failure` 不受影响（停放点 z = 10 > 0.15，与 (10,10,10) 同样算「被抬起」，但揭示窗口内没有抓取任务在判）。

## 四、怎么验的

### 4.1 新增单测（`tests/lightweight/test_v5_unmask_distractor_sampler.py`，26 条全过，约 13 s）

| 测试 | 内容 |
|---|---|
| `test_预设与计划数值一致` | 四个预设的 count / 环带 / cube 区间 / 1024 / 0.75 / balanced_cycle；Swap 环带等于 V4 `ring_half_extent`；VU/BU 的 cube 区间 = [floor(N/2), ceil(N/2)]；全局色板未改 |
| `test_非法配置直接报错`（7 例） | 色池、颜色规则、cube 区间越界/倒置、环带倒置、max_trials=0、多余键 |
| `test_代表性内部布局下全部规则成立且预算不耗尽`（4 环境 × 40 个随机内部布局） | 数量、环带、精确可见、yaw ∈ [0,90)、干扰两两及对内环容器**真实方形外廓**距离 ≥ 0.015（凸多边形精确距离）、不压按钮 OBB、cube 数在区间内、cube_bins 不重复、颜色差 ≤ 1、名字无重复、`verify` 通过、1024 次不耗尽 |
| `test_颜色平衡轮转对任意个数都平衡` | n = 0..16、三种 order |
| `test_同一seed可复现且不同seed不同` | — |
| `test_随机调用序列与V4的VU_BU同构` | 用 trials 重放：2·Σtrials + N 次 rand → randint → randperm(N)[:n] → randperm(3)，之后两条流下一段逐值相同 |
| `test_额外拒绝回调生效且可复核` | 回调拒绝 x>0 后全部 x ≤ 0；回调拿到的已放列表长度正确；`verify` 用同一回调能查出违规 |
| `test_放不下时抛候选级异常` | `DistractorPlacementError` 是 `SceneGenerationError`，`placed` 正确 |
| `test_actor精确包围框与由位姿算出的一致` | 用容器 6 个真实盒体 + 翻转位姿喂 `actor_obb2d_exact`，与 `bin_obb2d` 相同 |
| `test_整段重抽只在被接受的那次记录且回放逐值一致` | 真 `SpecRecorder`：前 2 次 accept 拒绝，`bins.<i>` 与 `cube_count` 各只 value 一次，attempts=3、failures 两条；导出的规格回放，布局与 accept 结果逐值相同、mismatch 0 |
| `test_回放篡改的冻结布局被拒` | 把冻结的 0 号容器挪到 (0,0) → `SceneGenerationError` |
| `test_整段重抽全部失败抛错并留痕` | attempts=4、failures 4 条、无任何 `bins` value |
| `test_停放点两两远离且不在旧停放点与场景附近` | 256 个点两两 ≥ 0.5 m、离 (10,10,10) > 5 m、离原点 > 10 m、越界报错 |
| `test_揭示停放与statechange时间线逐步相同` / `test_交换窗口cube停放与statechange时间线逐步相同` | 与 statechange 对应函数并排跑 70 / 80 步：每一步「在远处」的判定相同，不在远处时位置逐值相同，落回原位 / 容器新位置 |
| `test_每个干扰容器与cube各停各的点` | 15 个容器各在自己的停放点、半窗落回原位；5 个 cube 停在 5 个不同点 |
| `test_VU_BU密度推导锁定15与14` | 按计划 2.2 公式在 1 mm 网格上重算：环带 [0.2425, 0.3289]；VU A_usable 0.3027、BU A_usable 0.2858（按钮遮挡 5.60%）；N = floor(50·A + 0.5) = 15 / 14，且离取整边界 > 0.1 |

### 4.2 全量轻量测试

命令：`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider`
（与 4.4 的模拟器基准同时跑，148 s）。结果 `46 failed, 866 passed, 22 skipped, 74 deselected, 12 errors`；
按规则提取的失败集合 58 条，与 `/data/hongzefu/robomme_v5_wt/wt_baseline_failset.txt` **逐条相同**（`diff` 为空）；
新增 26 条全部通过。判定行：`LIGHTWEIGHT=PASS failure_set_equal_baseline=1 new_tests=26/26`。

V0：`git diff --stat` 为空（只新增两个未跟踪文件），`config_easy/config_medium/config_hard` 与 `NATIVE_SAMPLING` 零改动。

### 4.3 密度推导实测（单测内重算，1 mm 网格）

| 环境 | A_usable（m²） | 按钮遮挡 | ρ·A | N = floor(ρA+0.5) | 计划 2.2 |
|---|---|---|---|---|---|
| VU | 0.3027 | 0 | 15.136 | **15** | 0.3027 / 15.14 / 15 |
| BU | 0.2858 | 5.60% | 14.288 | **14** | 0.2853 / 14.27 / 14（遮挡 5.7%） |

BU 的按钮遮挡在计划里用 300 次蒙特卡洛，单测改用 21×21 按钮位置中点网格求期望（确定性），差 0.0005 m²，不影响取整；
两个 ρA 离取整边界都 > 0.1。Swap 两环境按 L16 (b) 不用贴身环带，只锁定常量（10 个、V4 环带、cube [5,5]）。

### 4.4 本机模拟器检查（进程内补丁，不落盘，只作调试参考）

脚本在会话 scratchpad（`park_bench.py`），日志 `artifacts/newtask-v5/s2c/park_bench.log`（本机留档、不进 Git）。做法：给 V4 代码的
`VideoUnmask` / `ButtonUnmask` 模块打补丁，把 `spawn_ring_distractor_bins` 换成 `spawn_distractor_layout(V5 预设)`；三种揭示方式：
`stack` = V4 原样（内环 8 个 + 干扰 15/14 个全停 (10,10,10)）、`park` = 干扰容器用 `reveal_distractor_bins_parked`、
`park_all` = 再把内环 8 个容器也用 `group="bin"` 停独立点。保持初始关节角步进 70 步，统计揭示前半窗 `[0,32)` 每步耗时与第 33 步所有容器、干扰 cube 相对初位的最大 XY 误差。
GPU 1，与全量轻量测试同时跑（有 CPU 争用，绝对值偏大，横向对比有效）。

| 环境 | 方式 | seed | 干扰容器 / cube | 采样耗时 | 最大 trials | 揭示前半窗每步 p50 / p95 / 均值（ms） | 窗口后每步 p50 | 第 33 步最大落回误差 |
|---|---|---|---|---|---|---|---|---|
| VU | stack（V4） | 910000 / 910101 | 15 / 7、15 / 8 | 0.019 / 0.020 s | 17 / 33 | 303.7 / 361.1 / 233.1；209.2 / 327.6 / 212.4 | 7.6；10.9 | 0.040；0.043 mm |
| VU | park | 同上 | 同上 | 同上 | 同上 | 17.7 / 288.9 / 43.5；20.1 / 293.0 / 62.1 | 8.1；8.1 | 0.040；0.043 mm |
| VU | park_all | 同上 | 同上 | 同上 | 同上 | **6.0 / 10.8 / 15.1；5.2 / 70.8 / 14.2** | 8.9；7.9 | 0.040；0.043 mm |
| BU | stack（V4） | 910000 / 910101 | 14 / 7、14 / 7 | 0.020 / 0.018 s | 34 / 22 | 299.0 / 338.5 / 228.4；208.8 / 334.7 / 210.8 | 8.2；8.1 | 0.034；0.042 mm |
| BU | park | 同上 | 同上 | 同上 | 同上 | 15.1 / 289.1 / 43.0；14.8 / 291.4 / 42.9 | 5.8；8.4 | 0.034；0.042 mm |
| BU | park_all | 同上 | 同上 | 同上 | 同上 | **4.3 / 10.5 / 13.6；6.2 / 12.2 / 15.6** | 8.4；9.5 | 0.034；0.042 mm |

结论（本机调试参考）：

- 统一采样器在真实场景里放满 15 / 14 个，单次采样约 0.02 s，最多用 34 次尝试（预算 1024）；颜色平衡轮转（7 或 8 个 cube 三色差 ≤ 1）。
- 只把干扰容器分开停放，揭示段 p50 从约 210～300 ms 降到约 15～20 ms，但 p95 仍约 290 ms（剩下 8 个内环容器仍叠在 (10,10,10)）；
  内环容器也分开停放后 p95 降到 10.5～12.2 ms（一例 70.8 ms）——**叠放是揭示段慢的主因**。
- 落回误差与 V4 相同（0.034～0.043 mm），停放点不影响落回精度。
- 8 个内环容器在 V4 trimesh 路径下 0/8 退化（两环境四个 seed 共 0/32）。

## 五、与计划不符之处

1. **helper 位置**：计划第二部分「一」写「`utils/unmask_distractors.py` 新增停放 helper」；本步放在新模块 `utils/unmask_distractor_sampler.py`
   （与统一采样器同处），为了不与 S3b/S3h 对 `unmask_distractors.py` / `unmask_swap_xhard.py` 的改动撞合并冲突。功能与计划一致。
2. **记录路径**：计划写 `objects.distractor_cube_bins`，实现为 `objects.distractors.cube_bins`（V4 VU/BU 已有路径）；颜色从 V4 VU/BU 的
   `cube_colors`（索引列表，value）改为 `color_order`（randperm(3)，value）+ `cube_colors`（颜色名，record）。
3. **障碍框**：计划只说「统一 OBB 规则」；实现里 actor 障碍改用真实盒体算精确框（`actor_obb2d_exact`），不走会退化的 trimesh 路径。
   本机实测容器在 trimesh 路径下不退化（0/32），对容器结果与 V4 相同。
4. **整段重抽里放不满的处理**：P5 原型遇到放不满直接拒绝本局；驱动里记一次失败尝试（原因 `placement`）继续重抽，16 次都不行再拒绝。
   P5 离线 500 局放不满 0 次，实际不影响结果。
5. `reveal_distractor_bins` 未就地改为停放版（见 3.3，交 S3 接入时连同单测一起改）。

## 六、待用户决策

1. **内环容器与内环被藏 cube 是否也停独立点（L14 的范围）**。L14 原文只说「每个干扰容器与每个被藏 cube」。本机实测（4.4）：只停干扰容器时，
   剩下 8 个内环容器仍叠在 (10,10,10)，揭示前半窗每步 p95 仍约 290 ms；内环容器也停独立点后 p95 降到 10.5～12.2 ms（一例 70.8 ms）。
   P5 记录的 Swap 每步 p95 约 290 ms（根因未定位）在 `[0,64)` 与交换窗口都出现，与「内环容器 / 内环 cube 仍叠在 (10,10,10)」的现象吻合（推测，未在 Swap 上实测）。
   建议：xhard 下内环容器（`group="bin"`）与 Swap 的内环 cube（`group="hidden_cube"`）也用停放 helper；只影响画面外的物理，不改变任何可见行为与步数。
   helper 已支持，接入与否由用户定（不定则 S3 只接干扰容器与干扰 cube）。

## 七、给合并者的注意事项

- 新模块只依赖既有函数的只读接口；不改 N13 列出的任何共用函数；原三档不 import 本模块。
- `DistractorLayout` 是纯数据；`to_spec()` 给统一 schema 的纯数据视图，`same_geometry()` 比较位置 / cube 映射 / 颜色。
- `extra_reject` 回调在 yaw 抽完后调用，**不许抽随机数**；`accept` 回调可以抽同一条流（这是 Swap 规划的一部分）。
- 回放时 `commit` 会复核冻结布局；Swap 若用了 `extra_reject`，回放复核也会调用它（需要与导出时同一内环预演）。
