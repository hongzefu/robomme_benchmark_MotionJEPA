# V5 S3i：PickHighlight / VideoPlaceButton / VideoPlaceOrder 的 xhard 障碍框修复与 StopCube 异常类核对（2026-09-24）

> 对应计划：`NEWTASK_RELEASE_V5_PLAN.md` 1.4 L2 (b)、L3，2.0①③，2.16，第二部分「一」S3i 行。
> 工作树：`/data/hongzefu/robomme_v5_wt/phvp`（分支 `v5wt-phvp`，基线 12.120 `328e607`），未 commit。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 | 怎么验的 |
|---|---|---|---|---|
| `src/robomme/robomme_env/PickHighlight.py` | 模块中部 `from .utils.xhard import ...` | 多导入 `cube_obb2d_exact` | 下一行要用 | import 冒烟、全量轻量测试 |
| 同上 | `_load_scene` 方块循环里「方块建成后入 avoid」一句 | 原 `avoid.append(cube)` 改为 `if xhard: avoid.append(cube_obb2d_exact(cube.initial_pose, self.cube_half_size))` / `else: avoid.append(cube)`（`xhard` 是该函数已有的局部变量 `self.difficulty == "xhard"`） | 2.0①：actor 经 `_trimesh_box_to_obb2d` 会退化成线段，`min_gap` 在法向失效 | 新单测 + 300 次真 reset 修复前后对比 |
| `src/robomme/robomme_env/VideoPlaceButton.py` | 模块头 import 区（`xhard_home_site` 之后） | 新增 `from .utils.xhard import cube_obb2d_exact` | 同上 | 同上 |
| 同上 | `_load_scene` 三色方块循环里「方块建成后入 avoid」一句 | 同上，守卫写 `if self.difficulty == "xhard":` | 同上；此后第 2、3 块方块与 4 个目标台的 spawn 都读这张 avoid | 同上 |
| `src/robomme/robomme_env/VideoPlaceOrder.py` | 同 VideoPlaceButton 两处 | 同上 | 同上 | 同上 |
| `tests/lightweight/test_v5_xhard_obb_fix.py`（新文件） | — | 16 条单测，见第四节 | 完成判据 | 全过（约 6 s） |

未改：三个环境里所有 `spawn_random_cube` / `spawn_random_target` 调用本身（参数逐字不动，`include_existing` 本来就全是 `False`）；
`object_generation.py`（`_trimesh_box_to_obb2d`、`_safe_unit`、两个 spawn 函数，N13）；StopCube.py（见第三节）；
任何 `config_easy/medium/hard`、`NATIVE_SAMPLING`、`decision` 键；录像器；`scripts/` 顶层；V4 配置与产物。

### 1.1 为什么取 `cube.initial_pose` 而不是 actor 当前位姿

`_load_scene` 阶段 GPU 仿真尚未初始化，`cube.pose` 不一定可读（`utils/xhard_home_site.py::build_home_sites` 已有同样的注释与处理）；
`initial_pose` 就是 `spawn_random_cube` 建方块时传入的位姿（float32 四元数），CPU/GPU 两种后端下都可用。
`cube_obb2d_exact` 对位姿输入取「最水平体轴」求 yaw，任何姿态都不退化；与建方块时的 yaw 相差只在 float32 舍入量级（实测 < 5e-7）。

### 1.2 调用点逐处核对（计划写「PickHighlight 约 1 处、VideoPlace* 各约 4 处」）

| 环境 | `spawn_*` 调用点 | avoid 里是否有已放方块 | 本次处理 |
|---|---|---|---|
| PickHighlight | `spawn_random_cube` × 1（循环 8～10 次） | 第 2 块起有 | 入 avoid 处改为精确三元组 |
| VideoPlaceButton | `spawn_random_target`（goal_site，`avoid=None`） | 无（在方块之前） | 不涉及 |
| | `spawn_random_cube` × 1（循环 3 次） | 第 2、3 块有 | 入 avoid 处改为精确三元组 |
| | `spawn_random_target`（目标台，循环 4 次） | 有（3 块方块） | 同一张 avoid，自动生效 |
| VideoPlaceOrder | 同 VideoPlaceButton（goal_site / 方块 / 目标台） | 同上 | 同上 |

源码里 VideoPlace* 各只有 **3 个** `spawn_*` 调用点（不是 4 个）；计划的「4 处」应是把 goal_site、方块、目标台以及循环展开后的次数混在一起数的。
真正需要改的只有「方块入 avoid」这一句（每环境 1 处），其后所有 spawn 调用读的都是同一张 avoid 表，因此一处改动覆盖全部受影响调用。
xhard 的尾段（`_load_scene_xhard_tail`）建放回原位落点用 `build_home_sites`，不走 spawn/avoid，不涉及。

`include_existing` 注意事项（S2a 报告）：三处调用原本就传 `include_existing=False`，不会有方块经旧退化路径混进来，不需要另外处理。
goal_site 与目标台以 actor 进 avoid，但它们带 `_target_radius`，两个 spawn 函数把它们当**圆**障碍处理（精确，不经 `_trimesh_box_to_obb2d`）；
按钮本来就是预制三元组（`create_button_obb`）。所以修完后 xhard 下 avoid 里没有任何会退化的项。

## 二、原三档静态自查（逐处说明为何不执行 / 不改变随机流）

1. 三处 import：只多绑定一个模块级名字，`utils/xhard.py` 早已被 PickHighlight 导入（VideoPlace* 首次导入它也无副作用、不抽随机数）。
2. 三处 `if xhard / if self.difficulty == "xhard"`：原三档走 `else: avoid.append(cube)`，与改动前那一句逐字相同；条件判断本身不抽随机数。
3. xhard 分支内 `cube_obb2d_exact` 是纯函数，不抽随机数、不读写环境状态，因此 xhard 自己的随机流也只因「障碍形状变化 → 拒绝采样 trial 次数变化」而移位（这正是计划要的；按 L1 (a)/N5 这三个环境重冻进 `v5-01`）。
4. spawn 调用参数、`decision` / `NATIVE_SAMPLING` / `config_*` 零改动：`git diff` 中不含 `config_easy|config_medium|config_hard|NATIVE_SAMPLING` 的增删行（V0 通过）。
5. 新单测 `test_静态自查_精确OBB只在xhard分支且spawn调用逐字不动` 用 AST 锁住：`_load_scene` 里恰有一个 xhard 守卫的 `if` 使用 `cube_obb2d_exact`，其 `else` 恰为 `avoid.append(cube)`，不存在未受守卫的 `avoid.append(cube)`，spawn 调用不带 V5 新参数且 `include_existing=False`。
6. `test_原三档方块仍以actor进avoid`（3 档 × 3 环境 × 5 seed）：原三档 avoid 里方块仍是 actor、唯一的三元组是按钮（轴为单位阵）。

## 三、StopCube 异常类（L3）

- S2a 已在 `StopCube.py` 模块头加了 `_RealSceneGenerationError` 别名与 `_scene_gen_error(difficulty)`。
- 核对结果：`StopCube.py` 全文**没有任何 `raise` 语句，也没有任何 `except` 子句**（`grep -nE "raise |except "` 只命中 S2a 加的注释/文档串）；xhard 路径（`_initialize_episode` 的 `xhard` 分支、`motion_segments` 展开等）不抛也不接 `SceneGenerationError`。方块用 `spawn_fixed_cube`，不走会抛 `RuntimeError` 的 `spawn_random_cube`。
- import 自省：`StopCube.SceneGenerationError` 仍是子模块（遮蔽仍在，原三档不动），`StopCube._scene_gen_error("xhard")` 是真类。
- **结论：无需改动**。计划 2.0③ 也写明「RouteStick、StopCube 在 V5 没有新增抛错点，但按 L3 一并修掉遮蔽」——别名 S2a 已加，今后若在 StopCube 的 xhard 路径新增抛错，直接用 `_scene_gen_error(self.difficulty)` 或 `_RealSceneGenerationError` 即可。

## 四、测试

### 4.1 新测试 `tests/lightweight/test_v5_xhard_obb_fix.py`（16 条，全过）

纯 CPU、不起 sapien：假 `self`（SimpleNamespace，带真 `_resolve_sampling_config` 与 `SpecRecorder`）直接调环境类的 `_load_scene`；
`TableSceneBuilder`、`build_button`、方块与圆盘 builder 换成替身，按钮替身与真 `build_button` 抽同样的随机数、返回同一个按钮 OBB；
`spawn_random_cube/target` 外包一层探针，记下每次调用的 avoid 快照、`min_gap`、半径与建出的物体。xhard 尾段置空。

**替身布局与真 reset 逐 seed 相同**（对拍，见 4.3）：三环境各 300 个 seed，reset 成败 300/300 一致，成功局方块位姿最大差 5e-7（float32 舍入），
所以单测里的间距数字就是真 reset 的数字。

| 测试 | 内容 | 结果 |
|---|---|---|
| `test_xhard已放方块间距不小于名义min_gap且障碍无退化` ×3 环境 | 60 seed：后放方块/目标台对每个先放方块的实际欧氏间距（方块-方块为两正方形间距，目标台为圆到正方形间距减半径）≥ 该次调用的名义 `min_gap`；spawn 收到的三元组全部非退化（两列单位且正交）；方块 actor 进 avoid 的次数 = 0 | 见下表 |
| `test_精确三元组与方块初始位姿一致` | avoid 里的三元组与由 initial_pose 解析算出的正方形一致（中心 1e-7，轴按 90° 对称等价） | 过 |
| `test_原三档方块仍以actor进avoid` ×9 | 见第二节 6 | 过 |
| `test_静态自查_...` ×3 | 见第二节 5 | 过 |

单测打印（`-s`）：

```
V5_XHARD_OBB_FIX env=PickHighlight    seeds=60 ok=50 scenegen_fail=10 pairs=2102 violations=0 min_margin=0.000254 exact_obstacles=2633 degenerate=0 cube_actor=0
V5_XHARD_OBB_FIX env=VideoPlaceButton seeds=60 ok=50 scenegen_fail=10 pairs=861  violations=0 min_margin=0.000027 exact_obstacles=1268 degenerate=0 cube_actor=0
V5_XHARD_OBB_FIX env=VideoPlaceOrder  seeds=60 ok=25 scenegen_fail=35 pairs=729  violations=0 min_margin=0.000102 exact_obstacles=1092 degenerate=0 cube_actor=0
```

（`pairs` 含 reset 失败局里失败之前已放好的物体对；失败局照样统计间距。）

### 4.2 全量轻量测试

`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider`：
`46 failed, 954 passed, 22 skipped, 74 deselected, 12 errors in 176.72s`。失败 + 错误共 58 条，
按 `grep -E '^(FAILED|ERROR) ' log | sed 's/ - .*//' | sort` 提取后与基线 `/data/hongzefu/robomme_v5_wt/wt_baseline_failset.txt` **逐条相同**（`diff` 无输出）；新增 16 条全部通过。
没有既有 V4 断言因本改动失效，未改任何共享测试文件。

### 4.3 真 reset 统计：修复前后各 300 次（计划盲区「clutter 布局 reset 成功率未评估」）

脚本放在会话临时目录（不进仓库，`scripts/` 顶层不许加文件）：每个 seed 一次 `gym.make(task, obs_mode="none", seed=s, difficulty="xhard")` + `reset()`，
记异常类与消息，成功局从 `unwrapped.all_cubes` / `targets` 的 `initial_pose` 算两两实际间距。seed 为 5000000～5000299，本机 GPU1，每次 reset 约 0.1～0.3 s。
「修复前」用主仓 `src`（同为 12.120，未含本改动），「修复后」用本工作树 `src`，其余完全相同。所有失败都是 `SceneGenerationError`（可重试类），没有其他异常类型。

| 环境 | 版本 | reset 成功 | 失败类别 | 成功局中方块-方块最小间距 | 成功局里有方块对 < 名义间距的局数 | 方块-目标台最小间距（名义 0.02） | 有 < 0.02 的局数 |
|---|---|---|---|---|---|---|---|
| PickHighlight（名义 0.04） | 修复前 | 291/300（97.0%） | 方块放不满 9 | 0.0207 | **241/291** | — | — |
| | 修复后 | 261/300（87.0%） | 方块放不满 39 | 0.0400 | **0** | — | — |
| VideoPlaceButton（名义 0.02） | 修复前 | 263/300（87.7%） | 目标台 4 放不下 28、目标台 3 放不下 9 | 0.0050 | **20/263** | 0.0000（贴边） | **120/263** |
| | 修复后 | 245/300（81.7%） | 目标台 4 放不下 44、目标台 3 放不下 11 | 0.0204 | **0** | 0.0200 | **0** |
| VideoPlaceOrder（名义 0.02） | 修复前 | 178/300（59.3%） | 目标台 4 放不下 82、3 放不下 32、2 放不下 8 | 0.0060 | **13/178** | 0.0005 | **78/178** |
| | 修复后 | 145/300（48.3%） | 目标台 4 放不下 88、3 放不下 56、2 放不下 11 | 0.0204 | **0** | 0.0201 | **0** |

PickHighlight 按本局请求的方块数拆（请求数在方块循环之前抽，修复前后同 seed 相同）：

| 请求方块数 | 修复前成功 | 修复后成功 |
|---|---|---|
| 8 | 89/89 | 87/89（97.8%） |
| 9 | 108/109 | 103/109（94.5%） |
| 10 | 94/102 | **71/102（69.6%）** |

读法：

- 修复把名义间距真正落实了：修复后三环境所有成功局、所有物体对都满足名义间距（与单测 violations=0 一致）；修复前 PickHighlight 83% 的局里至少有一对方块间距不到名义 0.04（最小 0.0207），VideoPlace* 有目标台与方块几乎贴边（0.0000 / 0.0005 m）。
- 代价是 reset 成功率下降：PickHighlight 97.0% → 87.0%（集中在 10 块：→ 69.6%），VideoPlaceButton 87.7% → 81.7%，VideoPlaceOrder 59.3% → 48.3%。
- VideoPlaceOrder 的 reset 失败率**修复前就已高达 40.7%**（V4 冻结 v4-01 里该环境的 seed 出现 5100101、5100202、5100302 等 attempt>0 的值，就是这个现象），根因是目标台（半径 0.04 + 间距 0.02）与半径 0.1 的 goal_site、按钮、3 块方块挤在 0.4×0.4 区域；不是本次修复引入的。
- 失败全部是可重试的 `SceneGenerationError`；抽签按 `--max-reset-attempts` 换 attempt 继续，成功率下降只增加抽签次数，不会让正式生成出现代码类失败。但它意味着被接受的布局是「放得下的那部分」，存在一定幸存者偏差（尤其 PickHighlight 10 块）。

## 五、演示（`scripts.parity.v4_demo_probe`，本机，只作调试证据）

本机 GPU0（补跑用 GPU1），与 6 路 reset 统计并行，墙钟偏高。seed：每环境 3 个 v4-01 冻结规格里的 seed（便于与 V4 对照）+ 2 个新 seed（910000、910101，探针默认 seed 规则）；
VideoPlaceOrder 因 v4-01 seed 有 2 个在修复后 reset 即失败，另补 2 个 reset 统计里可成功的 seed（5000002、5000004）。
产物在 `artifacts/newtask-v5/demo-probe/s3i-<Env>/`（h5、视频、`summary.jsonl`）。

| 环境 | seed | 来源 | reset | 演示 | 失败类别 | 墙钟 |
|---|---|---|---|---|---|---|
| PickHighlight | 5200000 | v4-01 | 成功 | **成功** | — | 146 s |
| | 5200100 | v4-01 | 成功 | **成功** | — | 170 s |
| | 5200200 | v4-01 | 成功 | **成功** | — | 132 s |
| | 910000 | 新 | 成功 | **成功** | — | 113 s |
| | 910101 | 新 | 成功 | **成功** | — | 108 s |
| VideoPlaceButton | 5000000 | v4-01 | 成功 | **成功** | — | 208 s |
| | 5000100 | v4-01 | 成功 | **成功** | — | 185 s |
| | 5000200 | v4-01 | 成功 | **成功** | — | 190 s |
| | 910000 | 新 | 成功 | **成功** | — | 176 s |
| | 910101 | 新 | 成功 | **成功** | — | 173 s |
| VideoPlaceOrder | 5100000 | v4-01 | **失败** | — | task: `SceneGenerationError`（Target 4 sampling failed） | 3 s |
| | 5100101 | v4-01 | 成功 | **成功** | — | 259 s |
| | 5100202 | v4-01 | **失败** | — | task: `SceneGenerationError`（Target 4 sampling failed） | 3 s |
| | 910000 | 新 | 成功 | **成功** | — | 239 s |
| | 910101 | 新 | 成功 | **成功** | — | 205 s |
| | 5000002 | 补（reset 统计可成功） | 成功 | **成功** | — | 229 s |
| | 5000004 | 补（reset 统计可成功） | 成功 | **成功** | — | 244 s |

汇总：PickHighlight `ok=5/5`；VideoPlaceButton `ok=5/5`；VideoPlaceOrder `ok=5/7`，2 条失败都是 reset 阶段目标台 4 放不下（可重试的任务类失败，
与第 4.3 节 VideoPlaceOrder 48% 的 reset 成功率一致；这两个 seed 在 V4 代码上 reset 可成功、被 v4-01 冻结，修复后障碍变大才放不下）。
**reset 成功的 15 条演示全部成功**，没有规划失败、超时或代码类失败——修复只改变布局，没有影响演示链路。

## 六、与计划不符之处

1. 计划写 VideoPlaceButton / VideoPlaceOrder「各 4 处」`spawn_random_*` 调用，源码各只有 3 个调用点（goal_site、方块循环、目标台循环）；受影响的是方块循环第 2 次起与目标台循环全部，均通过同一句「方块入 avoid」修复（见 1.2）。
2. 计划写「xhard 分支里调 spawn 时改用预制三元组」；VideoPlace* 的方块与目标台 spawn 是**三档共用的调用**（没有单独的 xhard 分支），为了「原三档调用逐字不动」，改在入 avoid 那一句按档分支，spawn 调用本身一字未改。PickHighlight 同理。
3. 位姿取 `cube.initial_pose`（而不是 S2a 示例里的 actor 本身），理由见 1.1；结果与由采样值算出的正方形差 < 5e-7。
4. StopCube 无需改动（第三节）。

## 七、待用户决策

1. **PickHighlight xhard 的 `spawn_count` 上界 10 是否下调**（改变设计意图，未自行处理）：V4 的 B5「区域与 min_gap 不动时实测只稳放 8～10」是在障碍框退化（间距实际未生效）的前提下测的。修复后 10 块的 reset 成功率只有 69.6%（8 块 97.8%、9 块 94.5%）。选项：(a) 保持 [8,10]，接受抽签多耗约 15% 的 attempt，以及 10 块局向「稀疏可放」的布局偏；(b) 改为 [8,9]；(c) 保持 10 但缩小 `min_gap_factor`。本步按计划「其他一个数都不动」保持 (a)。
2. **VideoPlaceOrder xhard 的 reset 成功率 48%**（修复前 59%）：失败都在目标台放置阶段。是否接受（抽签约 2 次 attempt 出 1 条），或另行放宽目标台区域/半径——后者改变布局设计，需用户定。VideoPlaceButton 81.7% 一般可接受。

## 八、给合并者的注意事项

- 本步没有新 API；只是用了 S2a 的 `cube_obb2d_exact(pose_or_xy_yaw, half, pad=0.0) -> (c, A, h)`，传入 `cube.initial_pose`。
- 三个环境文件的改动都只在「方块入 avoid」一句和 import 区，若其他 S3 步也动这三个文件（目前计划里只有 S3i 动），冲突面很小。
- 这三个环境的 xhard 布局已变，**v4-01 同 seed 的 xhard 规格在 V5 代码上会回注失败或 reset 失败**（例如 v4-01 的 VideoPlaceOrder seed 5100000 在修复后 reset 即失败），属 V4 作废的预期；需随其他环境一起重抽进 `v5-01`。
- 新测试文件里的替身布局与真 reset 逐位对得上（第四节），后续若改这三个环境的 `_load_scene` 前半段（按钮、spawn 顺序），替身 `_fake_build_button` 需同步。
