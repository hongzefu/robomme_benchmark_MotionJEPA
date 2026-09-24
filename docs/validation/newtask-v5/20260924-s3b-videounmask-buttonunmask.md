# V5 S3b：VideoUnmask / ButtonUnmask 的 xhard 干扰容器接入统一采样器（L13）与独立停放点（L14）

> 日期 2026-09-24；worktree `/data/hongzefu/robomme_v5_wt/vubu`（分支 `v5wt-vubu`，基于 12.120 `328e607`），改动未 commit。
> 依据：`NEWTASK_RELEASE_V5_PLAN.md` 1.4 L6～L15、2.2、2.3、2.4、第二部分「一」S3b 行；S2c 报告第三节 3.1 的接入示例。
> 主会话决定（本任务下达时）：xhard 下内环容器与被藏 cube 也用独立停放点。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 |
|---|---|---|---|
| `src/robomme/robomme_env/VideoUnmask.py` | 模块头 import | 不再 import V4 的 `spawn_ring_distractor_bins` / `reveal_distractor_bins`；改从 `utils/unmask_distractor_sampler` 导入 `V5_DISTRACTOR_PRESETS`、`spawn_distractor_layout`、`reveal_actors_parked`、`reveal_distractor_bins_parked` | L13 / L14 |
| 同上 | `XHARD_DISTRACTOR` | V4 的 6 键字面量（3 个、`[0.2675,0.45]`、cube `[1,2]`、256 次）→ `copy.deepcopy(V5_DISTRACTOR_PRESETS["VideoUnmask"])`：15 个、`[0.2425,0.3289]`、cube `[7,8]`、`balanced_cycle`、0.75、1024，统一 7 键 | 2.3 / L6～L12 |
| 同上 | `_load_scene` 末尾 `if xhard:` 分支 | `spawn_ring_distractor_bins(...)` → `spawn_distractor_layout(...)`，参数原样（主场景 `generator`、`avoid`、`self._spec`、被藏 cube 半边），多返回 `self.distractor_layout`；位置不动（仍在 `inject_fail_grasp` 之后、`add_distractor_misgrasp_failure` 之前） | L13；N5：仍在全部既有取值点之后 |
| 同上 | `step` | 原来「无条件的内环揭示循环 + `if xhard: reveal_distractor_bins`」改为 `if self.difficulty == "xhard":` 内环容器 `reveal_actors_parked(..., group="bin")` + 干扰容器 `reveal_distractor_bins_parked`；`else:` 里是**原样搬过来**的原三档循环（AST 文本逐字相同，只多一层缩进） | L14 + 主会话「内环也停独立点」 |
| 同上 | `config_xhard` 上方注释 | 「另有 3 个外环干扰容器」改成 V5 描述 | 文档同步 |
| `src/robomme/robomme_env/ButtonUnmask.py` | 同 VU 五处 | 同上，预设取 `"ButtonUnmask"`：14 个、同一环带、cube `[7,7]`；`avoid` 里已有按钮 OBB 预制三元组，照传 | 2.4 |
| `tests/lightweight/test_v4_xhard_videounmask_buttonunmask.py` | `test_xhard_values_match_user_decisions` | V4 断言 `count == 3`、`ring == [0.2675,0.45]`、`cube_count_range == [1,2]` → V5：7 键齐全、VU 15 / BU 14、`[0.2425,0.3289]`、VU `[7,8]` / BU `[7,7]`、`balanced_cycle`、0.75、1024；模块 docstring 加一行说明 | 规则第 6 条：V4 断言失效改 V5 语义 |
| `tests/lightweight/test_v4_xhard_unmask_distractor_reveal.py` | `test_四环境揭示只在xhard且原揭示循环不变` | 被调函数从只认 `reveal_distractor_bins` 改为 `reveal_distractor_bins` **或** `reveal_distractor_bins_parked` 都认（两种都必须在 xhard 分支）；其余断言不动 | VU/BU 改调停放版；VUS/BUS 在 S3h 接入前仍调 V4 版，两边都得过 |
| `tests/lightweight/test_v5_xhard_videounmask_buttonunmask.py`（新） | 10 条轻量 + 2 条 gpu（参数化后 12 + 4 例） | 见第三节 | 任务第 4 条验收 |

**没有改**：`utils/unmask_distractors.py`（`reveal_distractor_bins` / `spawn_ring_distractor_bins` 原样保留，前者 VUS/BUS 还在用，后者对 VU/BU 已成死代码，删不删留给主会话，避免与 S3h 在同一文件撞冲突）、
`utils/unmask_distractor_sampler.py`、`statechange.py`、`object_generation.py`、录像器、`scripts/` 与 V4 配置 / 快照。

### 被藏 cube 的停放（主会话决定的落实情况）

VU / BU 的揭示只把**容器**挪走、露出桌上原地不动的被藏 cube（`step` 里从来不碰 `target_cube_*`），所以两个环境里被藏 cube 没有可停放的动作；
主会话「内环容器与被藏 cube 也用独立停放点」在本步落实为**内环 8 个容器**用 `group="bin"` 停放。`hidden_cube` 停放组要到 Swap 两环境的交换窗口（S3h）才用得上。

## 二、原三档逐位不变的静态自查（diff 逐处）

| diff 处 | 原三档下为何不执行 / 不改变随机流 |
|---|---|
| import 换成新模块 | import 只在模块加载时执行一次，新模块顶层只定义常量与函数，**不抽随机数、不建 actor**；原三档不调用其中任何函数（AST 单测锁定：新模块所有调用都在 `xhard` 条件下；gpu 单测把三个函数换成「一调就抛错」后 hard 真 reset + 40 步照常通过） |
| `XHARD_DISTRACTOR` 取值 | 只进入 `decision["xhard"]`，`_strip_xhard` 后与 V4 原值逐字相同（V0 实测 `changed_keys=0`）；原三档不读这个子树 |
| `_load_scene` 的 spawn 调用 | 在 `if xhard:` 分支内部，原三档不执行 |
| `step` 的 `if/else` | 原三档 `self.difficulty != "xhard"` 走 `else`，其中循环的 `ast.unparse` 与 V4 逐字相同（单测 `test_step原三档揭示循环原样搬进else` 用 V4 文本字面量锁定）；真 step 代码的假 actor 测试：hard 下 8 个容器 `[0,32)` 都在 (10,10,10)、半窗后回原位，`_xhard_park_cache` 不存在 |
| `config_xhard` 注释 | 注释 |

V0：`config_easy/config_medium/config_hard` 与 `NATIVE_SAMPLING` 在 diff 中零改动（`git diff -U0` 里 grep 不到这几个名字）；另把 HEAD 版模块载入与现版逐项比较：
`NATIVE_DEFS_UNCHANGED=PASS envs=2 changed_keys=0`（三档 `configs`、`NATIVE_SAMPLING`、`_strip_xhard(_native_decision)` 全等）。
xhard 子树 V4→V5 的差异恰好是 `count`、`ring_max_abs_xy`、`cube_count_range`、`max_trials` 四个值与新增的 `color_rule`，`color_pool` / `min_gap_factor` 不变。

## 三、测试

### 3.1 新增单测 `tests/lightweight/test_v5_xhard_videounmask_buttonunmask.py`

轻量（12 例全过，约 3 s）：

| 测试 | 内容 |
|---|---|
| `test_xhard干扰配置等于V5预设且是深拷贝` | 两环境 `XHARD_DISTRACTOR == V5_DISTRACTOR_PRESETS[env]` 且不是同一对象；7 键；`parse_distractor_cfg` 后 VU 15/[7,8]、BU 14/[7,7]、环带、`balanced_cycle`、0.75、1024；`_native_decision` 的子树是独立副本 |
| `test_统一采样器只在xhard且排在全部既有取值点之后` | `_load_scene` 里 `spawn_distractor_layout` 恰一次、在 `xhard` 条件下，且行号晚于全部 `self._spec.value` / `spawn_random_bin` / `torch.rand*` / `inject_fail_grasp` / `build_button`；V4 采样器不再被调用 |
| `test_新模块的调用全部在xhard分支` | 整个文件里新模块四个名字的调用都在 `xhard` 条件下；`reveal_distractor_bins` 不再出现 |
| `test_step原三档揭示循环原样搬进else` | `step` 顶层恰一个 `if self.difficulty == 'xhard'`，`else` 只有一条语句且与 V4 循环文本逐字相同；xhard 分支里有 `reveal_actors_parked(group='bin')` 与 `reveal_distractor_bins_parked`，没有 `lift_and_drop_objects_back_to_original` |
| `test_hard仍走statechange停在10_10_10` | 用真 `step` 代码（`BaseEnv.step` 打桩）+ 假 actor 走 70 步：hard 下 8 个容器 `[0,32)` 全在 (10,10,10)，之后回原位 |
| `test_xhard内环与干扰容器各停各的点且落回原位` | xhard 下 8 个内环容器停 `xhard_park_point("bin", i)`、15 / 14 个干扰容器停 `("distractor_bin", j)`，`[0,32)` 两两不同、离 (10,10,10) > 5 m；第 32 步起全部回原位（误差 0）；statechange 缓存从未创建 |

模拟器（`@pytest.mark.gpu`，轻量全量不跑；手动 `-m gpu` 跑，4 例全过，49 s，GPU 1）：

| 测试 | 内容 |
|---|---|
| `test_真reset验收` | VU seed 4600000/4600300/4600600（v4-01）+ 5100001（新）；BU 4800000/4800300/4800600 + 5100001；逐条断言下表各项 |
| `test_真reset原三档不进新模块` | 把三个新函数换成「一调就抛 AssertionError」，hard 真 reset 后保持关节角走 40 步（揭示窗口内）：通过；规格里没有 `objects.distractors`、没有 `distractor_layout` 属性、没有停放缓存 |

真 reset 实测（日志 `artifacts/newtask-v5/s3b/gpu_reset.log`，本机留档）：

| 环境 | seed | 放下/请求 | out_of_ring | not_visible | cube 数（区间） | 颜色差 | 本环境 actor 名重复 | 内环与 V4 同 seed 相同 | 最大 trials |
|---|---|---|---|---|---|---|---|---|---|
| VU | 4600000 | 15/15 | 0 | 0 | 7（[7,8]） | 1 | 0 / 33 | 是 | 12 |
| VU | 4600300 | 15/15 | 0 | 0 | 7 | 1 | 0 / 33 | 是 | 32 |
| VU | 4600600 | 15/15 | 0 | 0 | 8 | 1 | 0 / 34 | 是 | 32 |
| VU | 5100001（新） | 15/15 | 0 | 0 | 8 | 1 | 0 / 34 | —（V4 无此 seed） | 45 |
| BU | 4800000 | 14/14 | 0 | 0 | 7（[7,7]） | 1 | 0 / 32 | 是 | 31 |
| BU | 4800300 | 14/14 | 0 | 0 | 7 | 1 | 0 / 32 | 是 | 44 |
| BU | 4800600 | 14/14 | 0 | 0 | 7 | 1 | 0 / 32 | 是 | 40 |
| BU | 5100001（新） | 14/14 | 0 | 0 | 7 | 1 | 0 / 32 | — | 16 |

判定行：
- `V5_UNMASK_RING=PASS VU=15 BU=14 out_of_ring=0 not_visible=0 shortfall=0`（8 次 reset）
- `V5_UNMASK_HALF_CUBE=PASS range_ok=1 color_imbalance_max=1`
- `V5_UNMASK_NAMES=PASS duplicate_actor_names=0`（本环境自建的内环容器、3 个被藏 cube、干扰容器、干扰 cube 逐个列出查重，并确认都已登记在 `scene.actors` 里）
- `V5_UNMASK_INNER_PARITY=PASS compared=6`：v4-01 冻结规格里同 seed 的 `layout`（8 个内环容器 xy/yaw、个数）与 `objects` 去掉 `distractors` 后（`color_order`、`n_picks`、`pick_order`）逐值相等
- 可见性用 actor 真实位姿复算 8 角点（`bin_visible`），不是只看采样器自报。

### 3.2 全量轻量测试

命令：`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider`（tmux，175 s）。
结果 `47 failed, 949 passed, 22 skipped, 76 deselected, 12 errors`；失败集合 59 条 = 基线 58 条 ∪ 1 条：

- `tests/lightweight/test_sampling_config_split.py::test_snapshot_matches_source`：`scripts/configs/newtask-v4/sampling_config.json 与源码提取结果不一致`。
  这是按规则预期的 **V4 快照校验失败**：VU/BU 的 xhard decision 从 6 键变 7 键、取值变了，V4 快照理应被拒；**未改 V4 快照**，交主会话在 S4 统一处理。

其余与 `/data/hongzefu/robomme_v5_wt/wt_baseline_failset.txt` 逐条相同；受影响的两份 V4 测试文件改后全部通过（37 例）。

## 四、演示（本机，调试参考）

做法：scratchpad 脚本 `s3b_demo_timing.py`（副本留在 `artifacts/newtask-v5/s3b/`），与 `v4_demo_probe` 一样直接调用 `generate_dataset_newseed._worker`
（gym.make 参数、录像器、规划器、失败分类与正式生成相同，episode 9、不开 recovery），另外在进程内给环境类的 `step` 包一层计时：
逐步记 `step` 耗时（含物理与观测渲染，不含录像器），第 0 步前记下全部被揭示容器的初位，第 32 步（半窗落回步）之后量误差。
VU 在 GPU 1、BU 在 GPU 0 同时跑（CPU 有争用）。h5 / 视频在 `artifacts/newtask-v5/demo-probe/s3b-{vu,bu}/`（git 忽略，本机留档）。

### 4.1 V5 演示（8 局，全部成功）

| 环境 | seed | 演示 | 步数 | 墙钟 s（solve s） | 揭示前半窗 [0,32) 每步 p50/p95/均值 ms | 揭示窗口 [0,64) 均值 ms | 整局每步 p50/p95/均值 ms | 落回误差 XY / 3D（mm） | 停放物体数 |
|---|---|---|---|---|---|---|---|---|---|
| VU | 4600000 | 成功 | 507 | 66.8（57.6） | 8.0 / 293.0 / 53.1 | 67.2 | 14.2 / 301.3 / 82.6 | 0.067 / 1.382 | 23 |
| VU | 4600300 | 成功 | 441 | 54.8（47.4） | 12.5 / 289.8 / 55.5 | 60.7 | 12.9 / 299.3 / 77.9 | 0.067 / 1.383 | 23 |
| VU | 4600600 | 成功 | 466 | 59.3（52.2） | 13.6 / 301.3 / 56.7 | 60.9 | 16.5 / 304.3 / 81.6 | 0.053 / 1.382 | 23 |
| VU | 5100001（新） | 成功 | 461 | 59.4（50.0） | 17.3 / 306.6 / 61.3 | 79.9 | 22.1 / 309.1 / 78.5 | 0.065 / 1.375 | 23 |
| BU | 4800000 | 成功 | 538 | 71.3（62.3） | 10.9 / 284.1 / 69.7 | 78.9 | 14.9 / 300.4 / 83.7 | 0.053 / 1.382 | 22 |
| BU | 4800300 | 成功 | 516 | 65.5（57.8） | 15.8 / 294.5 / 72.3 | 87.0 | 14.9 / 299.6 / 80.3 | 0.049 / 1.375 | 22 |
| BU | 4800600 | 成功 | 511 | 69.0（60.6） | 12.9 / 295.6 / 71.5 | 95.5 | 21.3 / 310.2 / 86.8 | 0.053 / 1.382 | 22 |
| BU | 5100001（新） | 成功 | 541 | 71.2（62.1） | 21.3 / 305.4 / 70.3 | 95.0 | 21.6 / 310.3 / 82.5 | 0.053 / 1.382 | 22 |

- 揭示窗口内所有停放物体离桌面原点 ≥ 28.28 m（停放网格原点 (20,20,10)），不在画面内；抽帧（`artifacts/newtask-v5/s3b/bu_frames.png`，BU 4800000 第 10 / 50 帧）：
  第 10 帧 22 个容器全部消失、3 个被藏 cube 与 7 个干扰 cube 露出；第 50 帧 22 个容器全部回原位。
- **落回误差**：XY 0.049～0.067 mm，满足 `V5_UNMASK_REVEAL max_return_err_mm ≤ 0.1`（按 XY 口径，与 S2c / 计划 2.2 的 0.04～0.05 mm 同口径）。
  3D 误差恒为约 1.38 mm，全部来自 z：落回那一步传送到窗口首帧记下的高度后，同一控制步内容器再落稳约 1.4 mm。4.2 的对照组显示 V4 的 (10,10,10) 机制是**完全相同**的 1.382 mm，属于原机制固有，不是停放点引入的。
- 失败类别：无（8/8 成功）。进程退出码 139 发生在 `S3B_DEMO_DONE` 打印之后（sapien 退出时段错误，与 V4 探针同样现象），不影响结果。

### 4.2 停放 vs V4 叠放（同一 seed、同样负载，进程内把两个停放函数换回 statechange 做对照）

| 环境 / seed | 方式 | 揭示前半窗每步 p50 / p95 / 均值 ms | 揭示窗口 64 步合计 s | 窗口后每步 p50 / p95 / 均值 ms | 整局 step 合计 s | 墙钟 s | 落回误差 XY / 3D mm |
|---|---|---|---|---|---|---|---|
| VU 4600000 | park（V5） | 18.0 / 154.3 / 35.2 | **3.20** | 23.8 / 314.6 / 78.3 | 37.9 | 62.6 | 0.067 / 1.382 |
| VU 4600000 | stack（V4 机制） | 129.4 / 388.9 / 215.1 | 8.87 | 23.8 / 312.4 / 78.8 | 43.8 | 68.5 | 0.067 / 1.382 |
| BU 4800000 | park（V5） | 21.8 / 300.2 / 55.2 | **4.37** | 23.6 / 314.4 / 80.8 | 42.7 | 69.2 | 0.053 / 1.382 |
| BU 4800000 | stack（V4 机制） | 216.7 / 406.3 / 238.4 | 10.09 | 24.2 / 308.8 / 81.1 | 48.5 | 73.9 | 0.053 / 1.382 |

结论：

- 独立停放把揭示前半窗的每步均值从 215 / 238 ms 降到 35 / 55 ms，揭示窗口合计省 5.7 s（VU）/ 5.7 s（BU），整局墙钟少约 5～6 s；落回误差逐位相同。
- **p95 仍约 300 ms 的原因不是停放**：逐步耗时显示整局约 20% 的步（窗口内外都有，窗口后 p95 两种方式都是 310 ms 左右）是约 300 ms 的周期性慢步，
  叠放时前半窗是「约 110 ms / 约 350 ms」交替，停放后前半窗大部分步降到 5～30 ms，只剩这种与窗口无关的周期性慢步。
  S2c 的基准（保持初始关节角、不走规划器、不开录像器）p95 为 10.5～12.2 ms，差别应来自演示链路本身（规划器 / 观测渲染）与两局并行的 CPU 争用；本机未进一步定位（不在本步范围）。

## 五、与计划不符之处

1. **被藏 cube 停放在 VU/BU 无对象可做**：VU/BU 的揭示从不移动被藏 cube（见第一节），主会话「被藏 cube 也停独立点」在本步只落实为内环容器停放；`hidden_cube` 组留给 S3h。
2. **`reveal_distractor_bins` 未就地改**：按 S2c 3.3 的做法①，VU/BU 在 `step` 里直接改调 `reveal_distractor_bins_parked`；`unmask_distractors.reveal_distractor_bins` 本身与其单测
   `test_揭示时序与区域容器同一机制`（(10,10,10) 语义）保持原样——VUS/BUS 在 S3h 接入前仍调它，这条断言对它仍然成立，所以没有改成 V5 语义。
   任务里说的「(10,10,10) 断言」在本步的对应改动是：VU/BU 的 V5 停放语义由新文件的真 `step` 测试锁定，旧文件只把 AST 断言放宽为两种函数都认。
3. **`spawn_ring_distractor_bins` 留作死代码**：计划 S3b 行写「`spawn_ring_distractor_bins` 校验改为 `0≤lo≤hi≤count`」；V5 改用统一采样器后 VU/BU 不再调用它
   （统一采样器的 `parse_distractor_cfg` 已是 `0 ≤ lo ≤ hi ≤ count`），因此没有改它的校验，也没有删（避免与 S3h 在同一文件撞冲突）。`test_distractor_geometry_helpers` 仍测它的几何函数。
4. **落回误差口径**：判据 `max_return_err_mm ≤ 0.1` 按 XY 计（与 S2c、计划 2.2 的 0.04～0.05 mm 同口径）；3D 误差恒约 1.38 mm，原机制同样如此（4.2）。
5. **decision 路径**：计划写的 `objects.distractor_cube_bins` 实为 `objects.distractors.cube_bins`（S2c 统一 schema，沿用 V4 路径），颜色改为 `color_order`（value）+ `cube_colors`（record）。

## 六、待用户决策

无改变设计意图的待决项。以下只作知会：

- 演示链路里约 20% 的控制步耗时约 300 ms，与揭示 / 停放无关（窗口外同样存在，V4 叠放对照同样存在）。是否需要单独定位由主会话决定。

## 七、给合并者的注意事项

- **共享测试文件改动**：`tests/lightweight/test_v4_xhard_unmask_distractor_reveal.py` 只改了 `test_四环境揭示只在xhard且原揭示循环不变` 一处（被调函数两种都认），
  S3h 若也改这条，合并时保留「两种都认」或在 S3h 完成后收紧为只认 `reveal_distractor_bins_parked`。
- 预期新增失败：`test_sampling_config_split.py::test_snapshot_matches_source`（V4 快照被拒，S4 重导 V5 快照后恢复）。
- 新 API 用法（均来自 S2c，本步只消费）：
  - `spawn_distractor_layout(env, *, cfg, avoid, generator, recorder, hidden_half_size) -> (bins, cubes, layout)`；环境上新挂 `self.distractor_layout`（`DistractorLayout`，`layout.bins` 为 `[(x, y, yaw_deg)]`、`layout.cube_bins`、`layout.cube_colors`、`layout.cube_names`）。
  - `reveal_actors_parked(env, actors, *, group, start_step, end_step, cur_step)`：本步 VU/BU 内环用 `group="bin"`，actors 顺序为 `bin_0..bin_{k-1}`，第 i 个停 `xhard_park_point("bin", i)`。
  - `reveal_distractor_bins_parked(env, *, start_step, end_step, cur_step)`：读 `env.distractor_bins`。
- worktree 根目录有一个误建的空 `.venv`（一次 `uv run` 忘带 `UV_PROJECT_ENVIRONMENT` 时生成，git 忽略、无内容）；删除命令被权限拒绝，未删，可忽略或手动删。
- 本机留档：`artifacts/newtask-v5/s3b/`（`lightweight.log`、`failset.txt`、`gpu_reset.log`、`demo_{vu,bu}.log`、`cmp_{vu,bu}.log`、`s3b_demo_timing.py`、`bu_frames.png`）、`artifacts/newtask-v5/demo-probe/s3b-*`（h5 / 视频 / `timing.jsonl`，约 3.9 GB），均被 git 忽略。
