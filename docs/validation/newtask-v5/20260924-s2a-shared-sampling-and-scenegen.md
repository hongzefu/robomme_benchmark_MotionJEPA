# V5 S2a：共用采样基础设施与 SceneGenerationError 遮蔽修复（2026-09-24）

> 对应计划：`NEWTASK_RELEASE_V5_PLAN.md` 2.0（①③）、2.9、2.13、2.14、2.15、2.16，第二部分「一」S2 行；决策 L2 (b)、L3、L4 (b)。
> 工作树：`/data/hongzefu/robomme_v5_wt/s2a`（分支 `v5wt-s2a`，基线 `f5b6a17`），未 commit。
> 本步只提供共用能力，**不接入任何环境的 xhard 分支**（接入由 S3c/S3f/S3g/S3i 等后续步骤做）。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 |
|---|---|---|---|
| `src/robomme/robomme_env/utils/xhard.py` | 新增 `cube_obb2d_exact`（及私有 `_as_numpy`、`_xy_yaw_from_pose`） | 纯函数：按方块真实 yaw 给出预制 2D 障碍 `(c, A, h)` | 2.0①：`_trimesh_box_to_obb2d` 对正方体轴序任意，竖直轴落进前两列时退化成线段 |
| `src/robomme/robomme_env/utils/object_generation.py` | 新增私有 `_center_rule_point_xy`、`_normalize_center_rules`、`_center_rules_violation`、`_assert_center_rules_hold`；`spawn_random_cube` / `spawn_random_target` 各加 `min_center_dist=None`、`center_exclusion=None` | 中心类拒绝规则（L4 b），在既有 OBB／圆判据之后、`recorder.value` 之前求值；回放冻结值与 `fixed_xy` 注入按同一规则复核（N17） | 2.9 MoveCube 中心禁区、2.13/2.14 Pick/Swing 8 cm、2.15 VideoRepick 12 cm |
| 同上 | 文件头 import | `from .episode_spec import EpisodeSpecError as _EpisodeSpecError`（下划线别名，不经 `from .utils import *` 外泄） | N17 复核失败抛的异常类 |
| `VideoRepick.py`、`SwingXtimes.py`、`PatternLock.py`、`RouteStick.py`、`StopCube.py`、`VideoUnmaskSwap.py`、`ButtonUnmaskSwap.py` | 模块头：`from .utils import *` 之后加 `_RealSceneGenerationError` 别名；`from ..logging_utils import logger` 之后加模块级 `_scene_gen_error(difficulty)` | L3：仿 `VideoPlaceOrder.py` 的 K2 修法 | 2.0③：`SceneGenerationError` 被遮蔽成子模块，raise / except 都变 TypeError |
| `VideoRepick.py` | `_load_scene` 最外层 `try` 的两个 handler；`_load_cubes_xhard` 的 3 处 raise | handler 改为 `_scene_gen_error(self.difficulty)`；xhard 专用方法直接用 `_RealSceneGenerationError` | 同上 |
| `SwingXtimes.py` | `_load_scene` 里三档共用的有色方块循环与两个圆盘的 3 处 raise、最外层 `try` 的两个 handler；`_color_name_of`、`_select_target_xhard`、`_spawn_distractors_xhard` 的 5 处 raise | 共用处用 `_scene_gen_error(self.difficulty)`；xhard 专用方法用 `_RealSceneGenerationError` | 同上（计划点名的「圆盘放不下实际走 TypeError」即共用处的两个圆盘 raise） |
| `tests/lightweight/test_v5_shared_sampling.py`（新文件） | — | 41 条单测，见第四节 | 完成判据 |

没有改：`_trimesh_box_to_obb2d`、`_safe_unit`、`_build_new_cube_obb2d`、`_obb2d_intersect`、`spawn_random_bin`、`statechange.py`、`bin_collision.py`（N13）；任何 `config_easy/medium/hard` 与 `NATIVE_SAMPLING`（V0）；录像器；`scripts/` 顶层。

## 二、新 API（给后续环境改动者）

### 2.1 `cube_obb2d_exact`

```python
from .utils.xhard import cube_obb2d_exact

cube_obb2d_exact(pose_or_xy_yaw, half, pad=0.0) -> (c, A, h)
```

- `pose_or_xy_yaw`：`(x, y, yaw)` 三个数；或带 `.p`/`.q`（wxyz）的位姿（mani_skill `Pose`，允许 `[1, ·]` batch 维；`sapien.Pose`）；或带 `.pose` 的 actor（取当前位姿）。
- `half`：方块半边长（标量）；`pad`：两个半轴各外扩的余量，语义同 actor 路径 `avoid=[(actor, pad)]`。
- 返回 `c:(2,)`、`A:(2,2)`（列为单位轴 `[[cos,-sin],[sin,cos]]`）、`h:(2,)`，全是 float64 `np.ndarray`。
  这正是两个 spawn 函数 `avoid` 里「预制障碍」分支的识别格式（三元组且前两项 `np.ndarray`），**两个 spawn 函数原本就支持预制障碍，任务 2 无需改代码**（`spawn_random_cube` 与 `spawn_random_target` 的 avoid 循环里已有该分支，actor 旧路径逐字未动）。
- 与 `_build_new_cube_obb2d(x, y, half, yaw, pad)` 逐位同构（同一写法）。位姿输入时 yaw 取「三根体轴里最水平的那根」的朝向：最水平那根 |z| ≤ 1/√3、xy 投影 ≥ √(2/3)，**任何姿态都不退化**；直立方块取体 x 轴，yaw 与建方块时相同（模 2π）。

用法（xhard 分支里替代「把 actor 放进 avoid」）：

```python
cube = spawn_random_cube(self, ..., avoid=avoid, include_existing=False, ...)
avoid.append(cube_obb2d_exact(cube, self.cube_half_size))   # 不再 avoid.append(cube)
```

⚠ `include_existing=True` 时 `spawn_random_cube` 仍会把 `self.cube` 与 `self._spawned_cubes` 里的 actor 走旧的（会退化的）路径加进障碍；`spawn_random_target` 的 `include_existing=True` 同理（外加 `self.target`）。要让障碍全部精确，xhard 调用须传 `include_existing=False` 并自行维护预制障碍列表。**VideoRepick 的 `_load_cubes_xhard` 目前传的是 `region_cfg["include_existing"]`（沿用 hard 档，为 True）**，S3g 接入时要改。

### 2.2 中心类拒绝参数（`spawn_random_cube` 与 `spawn_random_target` 同名同义）

```python
spawn_random_cube(self, ..., corner_bias=0.0,
                  min_center_dist=None,    # (d, points)
                  center_exclusion=None)   # (center_xy, radius)
spawn_random_target(self, ..., recorder=None, spec_path=None,
                    min_center_dist=None, center_exclusion=None)
```

- **候选中心**：两个函数拒绝循环里的 `(x, y)`。`spawn_random_cube` 中是 `x_low + u1·(x_high − x_low)`（区域已按 `half_size` 内缩，`corner_bias` 映射之后），即方块中心、也是建方块用的 xy；`spawn_random_target` 中是圆盘中心。
- `min_center_dist=(d, points)`：候选中心与 `points` 中任一点距离 `< d` 即拒。`points` 元素可以是 xy（列表／数组／CPU 张量），也可以直接是 `cube_obb2d_exact` 的三元组（取其 `c`）；可为空列表。
- `center_exclusion=(center_xy, radius)`：候选中心离 `center_xy` 距离 `< radius` 即拒。
- 求值位置：既有 OBB 判据、圆判据之后，`recorder.value` 之前；违反即 `continue`。自身不抽随机数，只改变 trial 次数；预算耗尽照旧抛 `RuntimeError`（调用方按惯例在 xhard 包成 `SceneGenerationError`）。
- 默认 `None`：只做一次 `is not None` 判断，不执行任何新判定、不多抽随机数（单测以改动前代码的金标准哈希锁定）。
- d、radius 允许 0（永不拒绝）；负数、NaN、形状不对抛 `ValueError`。
- **N17 复核**：`recorder.value` 返回后（导出模式恒通过；回放模式返回冻结值）以及 `spawn_random_cube(fixed_xy=...)` 注入路径，若传了规则就用同一规则复核，违反抛 `EpisodeSpecError`（`ValueError` 子类，生成器归为不可重试的代码类失败）。不传规则时两条路径逐字不变。

各环境调用示例（名字与数值取自计划，接入细节由各 S3 步决定）：

```python
# MoveCube（2.9，R = 0.05，按物体中心判）
zone = ((0.0, 0.0), 0.05)
self.goal_site = spawn_random_target(self, ..., center_exclusion=zone)          # 演示段 goal
self.goal_site_2 = spawn_random_target(self, ..., center_exclusion=zone)        # 执行段 goal
self.cube = spawn_random_cube(self, ..., center_exclusion=zone)                 # 方块最终中心
self.cube_2 = spawn_random_cube(self, ..., include_existing=False, center_exclusion=zone)  # L34
# 局部函数 _sample_cube_center 的候选中心禁区、杆轴线段判据都在 MoveCube 内自己写，不经本参数

# PickXtimes / SwingXtimes（2.13 / 2.14，6 块两两 ≥ 0.08）
placed = []                                   # 已放方块的精确 OBB（有色 + 干扰共用一张表）
cube = spawn_random_cube(self, ..., avoid=avoid, include_existing=False,
                         min_center_dist=(0.08, placed))
obb = cube_obb2d_exact(cube, self.cube_half_size)
placed.append(obb); avoid.append(obb)

# VideoRepick（2.15，6 块两两 ≥ 0.12）
cube_actor = spawn_random_cube(self, ..., include_existing=False,
                               min_center_dist=(0.12, placed), recorder=self._spec,
                               spec_path=f"layout.cubes.{i}.xy_yaw")
```

`fixed_xy` 路径（BinFill 等用）不经拒绝循环；若同时传规则，只做 N17 复核。VideoRepick 原三档的 `fixed_xy` 注入不受影响（不传规则）。

### 2.3 SceneGenerationError 按档选类（7 个模块统一用法）

```python
# 模块级（7 个模块各一份，与 VideoPlaceOrder 的别名同名）
from .utils.SceneGenerationError import SceneGenerationError as _RealSceneGenerationError
def _scene_gen_error(difficulty): ...   # xhard → 真类；原三档 → 本模块被遮蔽的原名字

# 三档共用的代码
raise _scene_gen_error(self.difficulty)("说明") from exc
except _scene_gen_error(self.difficulty):
# 只在 xhard 执行的方法 / 分支
raise _RealSceneGenerationError("说明")
```

原三档拿到的仍是子模块对象，`raise` 与 `except` 仍抛同样的 TypeError（消息也相同：`'module' object is not callable` / `catching classes that do not inherit from BaseException is not allowed`），H2 不变。

## 三、import 自省（L3 前提）

在工作树上 import 全部 16 个环境模块并检查模块级名字 `SceneGenerationError` 的类型：**恰好** VideoRepick、SwingXtimes、PatternLock、RouteStick、StopCube、VideoUnmaskSwap、ButtonUnmaskSwap 7 个被遮蔽成子模块，外加已按 K2 修过（但遮蔽仍在）的 VideoPlaceOrder；其余 8 个是真类。与计划 2.0③ 一致，并落成单测 `test_no_other_env_module_is_shadowed`。

7 个模块里，**只有 VideoRepick 与 SwingXtimes 现有代码写了 raise / except `SceneGenerationError`**；PatternLock、RouteStick、StopCube、VUS、BUS 目前一处都没有（名字只经 `from .utils import *` 进来），本步只给它们加别名与 helper，后续 S3a（PatternLock 搜索耗尽抛错）、S3h（Unmask 内环预判拒绝、BUS 截断改报错 L15）直接用。

VideoRepick 中 `_load_scene` 的 hard / plain 分支里 5 处 raise 只在原三档执行，保持原样；SwingXtimes 的有色方块循环与两个圆盘是三档共用代码，改用 `_scene_gen_error(self.difficulty)`，原三档行为逐字不变。

## 四、测试

### 4.1 新测试 `tests/lightweight/test_v5_shared_sampling.py`（41 条，全过，约 7 s）

纯 CPU，用 monkeypatch 顶替 `actors.build_cube` 与圆盘 builder（假 actor 只存位姿）：

- **精确 OBB**：`(x,y,yaw)` 输入对 721 个 yaw（±4π）× pad 0/0.02 与 `_build_new_cube_obb2d` **逐位相等**；spawn 同款 float32 四元数位姿 361 个 yaw 与解析方块一致（atol 1e-6）；绕 x／y 转 90° 后任意 yaw（各 200 个，含旧路径退化的「竖直轴在第 0/1 列」）均不退化、俯视正方形与解析一致；构造旧路径 `_trimesh_box_to_obb2d` 的退化实例（第 0 列范数 < 1e-9）对照；actor / 非 batch 位姿输入结果相同；非法输入报错；预制三元组放进两个 spawn 函数的 `avoid` 确实挡住候选（各 30 seed）。
- **默认值逐位不变**：3 个方块场景（均匀 yaw、固定 yaw + 矩形区域、`corner_bias=0.5`）与 1 个圆盘场景，各 40 seed × 连放 4 块／3 盘（含 `max_trials` 耗尽的 FAIL 局，方块 20/480、圆盘 0/120），记录每块位姿的 float hex 与调用后随机流哨兵，SHA-256 与**改动前代码**（基线 `f5b6a17`，改 `object_generation.py` 之前算出）的金标准相同；显式传 `None`、只传其中一个 `None`、传永不触发的规则（d=0 / R=0）也都与金标准相同。
- **开启即拒绝**：方块两两中心距 ≥ 0.1、禁区 R=0.1 与圆盘 ≥ 0.15 + R=0.05 全部满足，且确有 seed 结果与默认不同；「被接受的恰是同一随机流里第一个满足规则的 trial、调用后生成器状态逐字节相同」各 60 seed（方块、圆盘）；预算耗尽抛 RuntimeError；`points` 接受预制三元组；6 种非法参数两个函数都抛 ValueError。
- **N17**：回放替身返回违规冻结值时方块（中心禁区、中心距）、圆盘都抛 `EpisodeSpecError`；`fixed_xy` 违规同样抛；合规冻结值放行；不传规则时违规冻结值照旧不复核。
- **L3**：7 个模块 `_scene_gen_error("xhard")` 是真类并能被 `pytest.raises(SceneGenerationError)` 接住，三档仍是子模块、raise 与 except 均为 TypeError；AST 检查 VideoRepick / SwingXtimes 的 xhard 专用方法不再出现裸名 `SceneGenerationError`、`_load_scene` 最外层 handler 按档选类；用假 `self` 实跑 `VideoRepick._load_cubes_xhard`（`spawn_random_cube` 顶替为抛 RuntimeError）与 `SwingXtimes._color_name_of`，抛出的都是真 `SceneGenerationError`。

### 4.2 全量轻量测试

`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider`：
`46 failed, 881 passed, 22 skipped, 74 deselected, 12 errors in 140.75s`。失败 + 错误共 58 条，按 `grep -E '^(FAILED|ERROR) ' log | sed 's/ - .*//' | sort` 提取后与基线 `/data/hongzefu/robomme_v5_wt/wt_baseline_failset.txt` **逐条相同**（`diff` 无输出）；新增的 41 条全部在 passed 里。

### 4.3 V0 静态检查

`git diff` 中没有任何 `config_easy` / `config_medium` / `config_hard` / `NATIVE_SAMPLING` 的增删行：**零改动**。

### 4.4 演示

本步不接入环境、不改任何档的取值路径，未跑演示探针（原三档逐位不变由金标准哈希单测守住，xhard 行为要等各 S3 步接入后才有变化）。

## 五、与计划不符之处

1. 计划写「`spawn_random_cube` / `spawn_random_target` 的 `avoid` 要能接受预制三元组」——**代码已支持**（两个函数的 avoid 循环里本来就有「三元组且前两项 ndarray → 直接当障碍」的分支，PickXtimes / SwingXtimes 的 `_disk_avoid_obb` 已在用），本步没有改 avoid 逻辑。
2. 计划 S2 行给 `utils/xhard.py` 还列了 `footprint_gap`、`center_zone_half`、`balanced_color_cycle`、`max_same_color_component`，不在本子任务（S2a）范围，未做。
3. 计划写参数名「如 `center_zone`、`min_center_dist`」，实现取 `min_center_dist=(d, points)` 与 `center_exclusion=(center_xy, radius)`（后者与 MoveCube 计划里的配置键 `center_exclusion` 同名）。每个参数是一个二元组，避免「给了 d 忘了点集」的半配置状态。
4. N17 复核放进了两个 spawn 函数本身（只在传了规则时生效），而不是留给各环境自己写；异常类取 `EpisodeSpecError`。

## 六、待用户决策

无改变设计意图的待决项。以下是给主会话的提示（不是需要用户拍板的问题）：

- VideoRepick / SwingXtimes 的 `_load_scene` 在 xhard 下现在会把 try 内**所有**异常包成真 `SceneGenerationError`（可重试），这是原代码 `except Exception → raise SceneGenerationError` 的本意，与 VideoPlaceOrder 的 K2 修法相同；但这也意味着 N17 复核抛的 `EpisodeSpecError` 若发生在这两个环境的 `_load_scene` 里会被包成 `SceneGenerationError`（原因链 `__cause__` 保留）。S3g 若希望它按代码类失败上报，可在 xhard 分支里单独放行。
- 正式生成固定 `--max-attempts 1`，可重试与否只影响失败分类、不触发换 seed。

## 七、给合并者的注意事项

- 本步改动的 7 个环境模块只加了模块头两段与少量 raise/except 名字替换；SwingXtimes 的有色方块循环 S3f 还要拆分支，合并时注意这 3 处 raise 已改名为 `_scene_gen_error(self.difficulty)`。
- `object_generation.py` 的新私有函数都在 `spawn_random_cube` 定义之前；两个 spawn 函数的新参数都放在参数表最后，关键字调用即可，不影响任何现有位置参数。
