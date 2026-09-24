# V5 S3a：PatternLock 与 RouteStick 的 xhard 改动（2026-09-24）

依据：`NEWTASK_RELEASE_V5_PLAN.md` 1.1 口径 9、1.4 L35～L39、2.10、2.11、3.5 的 P3、第二部分「一」S3a 行。
工作树：`/data/hongzefu/robomme_v5_wt/plrs`（分支 `v5wt-plrs`，基于 12.120），未 commit。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 |
|---|---|---|---|
| `src/robomme/robomme_env/PatternLock.py` | 模块头 import | 新增 `from .utils.episode_spec import EpisodeSpecError as _EpisodeSpecError` | 回放复核失败抛的异常类（下划线别名，不经 `from .utils import *` 外泄） |
| 同上 | 新增模块常量 `XHARD_DECISION` | `{"path_search_max_attempts": 20000}` | 计划 2.10：xhard 搜索预算 1000 → 20000，作为 xhard decision 键 |
| 同上 | `_native_decision` | 返回值新增顶层 `"xhard": copy.deepcopy(XHARD_DECISION)` | 预算随 decision 冻进 `sampling_config` 快照与规格 header |
| 同上 | `PatternLock.config_xhard` | `length` `[20, 24]` → `[25, 25]`（`grid` 5 不变） | L35/L36 + P3 后实施方定：固定 25 节点。`decision.path_length_range.xhard` 由它派生，自动变成 `[25, 25]` 并冻进 header |
| 同上 | `_load_scene` 中 `max_attempts = ...` 之后 | `if self.difficulty == "xhard": max_attempts = self._xhard_decision("path_search_max_attempts")` | xhard 读 decision（header 冻结值），原三档仍读 native 的 1000 |
| 同上 | `_load_scene` 搜索循环的 `for … else` 分支 | 在原 `logger.debug` 之前加 `if self.difficulty == "xhard": raise _RealSceneGenerationError(...)` | L36/L3：xhard 耗尽抛真 `SceneGenerationError`（可重试）；原三档仍静默沿用最后一条路径 |
| 同上 | `_load_scene` 中 `self._spec.record("actions.path_attempts", ...)` 之后 | `if self.difficulty == "xhard": self._check_xhard_path(...)` | N17 精神：回放时 `SpecRecorder.value` 直接返回冻结值不复核，这里复核节点数在范围内、不重访、8 邻接、不越界，违反抛 `EpisodeSpecError` |
| 同上 | 新方法 `_xhard_decision(key)`、静态方法 `_check_xhard_path(...)` | 见上 | 缺 `decision.xhard` 键（V4 或更早快照）时报 `ValueError`，不回退到原三档值 |
| `src/robomme/robomme_env/RouteStick.py` | 模块头 import | 新增 `EpisodeSpecError as _EpisodeSpecError` 别名 | 同上 |
| 同上 | `_native_decision` | 返回值新增 `"xhard": {"segment_count_range": list(cls.config_xhard["length"])}` | L38：L 范围冻进 decision 与规格 header |
| 同上 | `RouteStick.config_xhard` | `length` `[12, 15]` → `[15, 21]`（`backtrack` True 不变） | L37 |
| 同上 | `_load_scene` 中 `length_min, length_max = cfg.get("length")` 之后 | 新增 `length_decision_key`；`if self.difficulty == "xhard":` 改从 `self._xhard_segment_count_range()` 取范围、归因键改为 `xhard.segment_count_range`；`objects.L` 的 `value()` 调用的 `decision_key=` 改用该变量 | 回放时从 header（传入的 sampling_config.decision）读 L 范围，不再读类属性；抽样调用 `torch.randint(length_min, length_max + 1, (1,), generator=generator)` 的位置与形状不变，只改值域 |
| 同上 | `_load_scene` 中 `actions.nodes` 的 `value()` 之后 | `if self.difficulty == "xhard":` 复核 L 在范围内、节点数 = L+1，违反抛 `EpisodeSpecError` | N17 精神，同上 |
| 同上 | 新方法 `_xhard_segment_count_range()` | 读 `decision.xhard.segment_count_range`，校验为 `[下界, 上界]` 正整数对 | 缺键（V4 header）即 `ValueError`（口径 13：V4 作废） |
| `tests/lightweight/test_v5_xhard_patternlock_routestick.py` | 新文件，18 条 | 见第三节 | 验收单测 |

未改：网格 5×5、中心 `[-0.1, 0]`、间距 0.1、`find_path_0_to_8` 与 DFS、RouteStick 1×9 布局与游走规则、`NATIVE_SAMPLING` 两份、录像器、`scripts/` 入口、V4 配置与产物。
未动任何共享测试文件。

## 二、关键设计点

1. **decision 键用顶层 `"xhard": {...}` 子树**（仿 PickXtimes）。`assert_native_decision` 剥掉 xhard 键后与原值逐键相同，原三档可见部分不变；
   不采用 `"path_search_max_attempts": {"xhard": 20000}` 这种写法，是因为剥 xhard 后会留下空字典，导致 v2/v3 旧快照在**原三档**上也被守卫拒绝。
   V4 快照的处理：
   - PatternLock：V4 decision 带 `grid.xhard` / `path_length_range.xhard`，键形状与新申报（多了 `xhard.path_search_max_attempts`）不符 → 构造时 `SamplingConfigError`。
   - RouteStick：V4 decision 完全没有 xhard 条目（旧快照放行规则），构造通过；原三档照常工作，xhard 的 reset 在 `_xhard_segment_count_range` 抛 `ValueError`（「V4 规格在 V5 代码上直接被拒」）。
2. **header 冻结路径**：`v4_specs draw/freeze` 把 `sampling_config`（含 decision）整段写进 header，回放时原样传给 `gym.make`；因此 xhard 的 20000 预算与 `[15,21]` 都从 header 读。单测用「传入 decision 改成 `[21,21]`、类属性仍是 `[15,21]`」证明 L 由 header 决定。
3. **PatternLock 预算读取点**只在 xhard 生效；native 的 `path_selection.max_attempts`（1000）只给原三档用（单测把 native 改成 1 不影响 xhard）。
4. **耗尽异常**用 S2a 的 `_RealSceneGenerationError`（xhard 专用分支里直接用真类），不用被遮蔽的 `SceneGenerationError`。
5. **回放复核**（两环境都加，计划 N17 只点名了三个环境，这里属顺手加固）：只在 xhard 执行，导出模式下等于自检（搜索/游走已保证），不抽随机数。
6. **演示帧数**：环境内没有新记 `demo_frames`；`actions.path_nodes`（PatternLock）与 `objects.L`（RouteStick）原本就在规格里，生成报告从 h5 数 `is_video_demo`（`scripts/parity/v5_generation.count_demo_frames`）即可。
7. **细节自决**：键名 `path_search_max_attempts` / `segment_count_range`；异常文案；`_check_xhard_path` 的 8 邻接判据写成 `max(|dr|,|dc|) == 1`。

## 三、测试

### 3.1 新增单测（`test_v5_xhard_patternlock_routestick.py`，18 passed，10 s）

纯 CPU：`object.__new__` 造实例，桩掉 `TableSceneBuilder` / `build_gray_white_target`、`scene` 用 MagicMock，跑**真实的 `_load_scene`**。

- PatternLock：原三档 `configs` 与去 xhard 后的 decision 逐字等于改动前；`config_xhard == {"grid":5,"length":[25,25]}`；`decision.xhard == {"path_search_max_attempts":20000}`；native 预算仍 1000。
- **`PL_LEN_EXACT`**：5 个 seed（5500900/5500000/5500300/5500600/7100001）xhard reset 路径恰 25 节点、覆盖全部 25 格、合法 8 邻接，`path_attempts ≤ 20000`，演示段与执行段各 24 段 move。判定行：`PL_LEN_EXACT=PASS wrong_length=0 seeds=5`。
- 搜索耗尽：把 header 里的 `decision.xhard.path_search_max_attempts` 改成 3 → 抛真 `SceneGenerationError`（`pytest.raises(SceneGenerationError)` 接得住）。
- 原三档耗尽（hard，内存里把预算改 2、范围改成不可能的 [30,30]）→ 不抛错，`path_attempts == 2`，静默沿用最后一条路径（行为不变）。
- 回放：自导出规格回放 mismatch 为 0；截短冻结路径 / 打乱成非邻接 → `EpisodeSpecError`。
- V4 形状 decision → `SamplingConfigError`。
- RouteStick：原三档不变；`config_xhard == {"length":[15,21],"backtrack":True}`；`decision.xhard == {"segment_count_range":[15,21]}`。
- L 值域：seed 0～159 的 L 全在 [15,21] 且 7 个值都出现，节点数 = L+1；前 20 个 seed 按「theta 1 次 rand、4 次障碍色 rand(3)、然后 randint(15,22)」手工复算与环境一致（抽样点与顺序不变）。
- header 冻结：传入 `[21,21]` → L 恒为 21（类属性仍 [15,21]）。
- V4 header（无 xhard 条目）：xhard reset `ValueError`，hard 仍正常。
- 回放冻结 L=22 → `EpisodeSpecError`。

### 3.2 全量轻量测试

`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider`：
47 failed, 955 passed, 22 skipped, 74 deselected, 12 errors，180 s。
失败集合 = 基线 58 条 ∪ 1 条：`tests/lightweight/test_sampling_config_split.py::test_snapshot_matches_source`
（`scripts/configs/newtask-v4/sampling_config.json 与源码提取结果不一致`）——PatternLock / RouteStick 的 decision.xhard 变了，属规则允许的 V4 快照校验失败，**未改 V4 快照**，留 S4 统一处理。无其他新增失败，未改任何既有断言。

### 3.3 V0 与原三档逐位静态自查

- `git diff` 删除行只有：两处 `config_xhard.length`、V4 注释、RouteStick `decision_key=` 的表达式（改为同值变量）。`config_easy/medium/hard`、两份 `NATIVE_SAMPLING` 零改动。
- 逐处说明原三档为何不受影响：
  - 新增 decision 顶层 `xhard` 子树：`_strip_xhard` 后与原值相同；原三档代码从不读它。
  - PatternLock 三处新增语句都挂在 `if self.difficulty == "xhard"` 下，原三档只多做一次字符串比较，不抽随机数。
  - RouteStick 新增 `length_decision_key` 赋值在原三档下取值等于原表达式 `f"configs.{difficulty}.length"`，只影响新值模式 mismatch 归因字段；xhard 分支与回放复核在原三档不执行。
  - 内存里 RouteStick 的 `parameters.configs.xhard.length` 会变成 [15,21]（`setdefault` 自类属性），原三档不读该条目，快照里也没有 `configs`（`NATIVE_SAMPLING` 不含）。
- **动态对拍**（CPU，同一假实例法）：把 12.120 的 `src` 用 `git archive` 导出到临时目录，改动前后各跑 PatternLock / RouteStick × easy/medium/hard × 44 个 seed（0～39 与 1000000/2000001/3000002/4500300）共 264 次 `_load_scene`，比较完整规格文档（`to_dict`）、任务表（名称与 demonstration 标志）、native 与 positions：**264/264 全等**，唯一差异是上面所说的内存 `configs.xhard.length`（已预期并排除）。

## 四、本机演示（`scripts.parity.v4_demo_probe`，xhard，无 fail recover，本机只作调试参考）

帧数从 h5 读：`<episode>/timestep_*/info/is_video_demo` 为真的帧数（与 `v5_generation.count_demo_frames` 一致）；非演示帧 = 执行段步数。
产物：`artifacts/newtask-v5/demo-probe/s3a-patternlock/`、`s3a-routestick/`（h5 + 视频 + `summary.jsonl`，共约 10 GB，未进 Git）。

| 环境 | seed | 来源 | 节点/段 | reset | 演示成功 | 演示帧 | 秒 | 执行段步数 | 750～1050 | 墙钟 |
|---|---|---|---|---|---|---|---|---|---|---|
| PatternLock | 5500000 | V4 ep0 | 25 节点（搜索 2649 次） | ✓ | ✓ | 818 | 27.3 | 818 | 是 | 247 s |
| PatternLock | 5500300 | V4 ep3 | 25（141 次） | ✓ | ✓ | 872 | 29.1 | 872 | 是 | 256 s |
| PatternLock | 5500600 | V4 ep6 | 25（1137 次） | ✓ | ✓ | 837 | 27.9 | 837 | 是 | 234 s |
| PatternLock | 5501000 | 新 | 25（1416 次） | ✓ | ✓ | 859 | 28.6 | 859 | 是 | 224 s |
| RouteStick | 5600000 | V4 ep0 | L=21 | ✓ | ✓ | 1050 | 35.0 | 1050 | 是（上界） | 306 s |
| RouteStick | 5601400 | 新（离线挑的 L=21） | L=21 | ✓ | ✓ | 1050 | 35.0 | 1050 | 是（上界） | 291 s |
| RouteStick | 5600300 | V4 ep3 | L=17 | ✓ | ✓ | 850 | 28.3 | 850 | 是 | 231 s |
| RouteStick | 5600600 | V4 ep6 | L=16 | ✓ | ✓ | 800 | 26.7 | 800 | 是 | 198 s |
| RouteStick | 5600100 | V4 ep1 | L=15 | ✓ | ✓ | 750 | 25.0 | 750 | 是（下界） | 187 s |

- 判定行：`DEMO_PROBE PatternLock ok=4/4 frames=[818,872,837,859] in_band=4/4`；`DEMO_PROBE RouteStick ok=5/5 frames=[1050,1050,850,800,750] in_band=5/5`。
- RouteStick：`RS_DEMO_LEN=PASS rule=L*50 mismatches=0 min_frames=750 max_frames=1050`（5 局演示帧恰为 50·L）。执行段步数同为 50·L，L=21 时 1050，在评估 1301 步预算内（余量 251），演示成功即执行段在该步数内完成：`EXEC_BUDGET=PASS timeouts=0 max_exec_steps=1050`。
- PatternLock：每段平均 34.1～36.3 帧（24 段），与 P3 的 35.06 相符；四局 27.3～29.1 s，落在 750～1050 带内。
- 失败：0，无需归因。

## 五、与计划不符之处

1. 第二部分「一」S3a 行仍写 `length [24,25]`；按 2.10 表与 P3 后的实施方决定实现为 **`[25,25]`**（任务说明同此）。
2. 计划 2.10 表「运行记录」写「记 `demo_frames`」：环境内未新增记录，帧数由生成报告从 h5 读（任务说明允许）。
3. 计划 N17 只点名 InsertPeg / MoveCube / VideoRepick 需要回放复核；本步对 PatternLock 路径与 RouteStick 段数也加了 xhard 下的回放复核（只挂在 xhard、不抽随机数），属加固。
4. 计划 2.11 称「V4 规格在 V5 代码上直接被拒」：RouteStick 的 V4 header decision 不含 xhard 条目，按守卫的旧快照放行规则能通过构造，拒绝发生在 xhard reset 时（`ValueError`，而不是构造期的 `SamplingConfigError`）；原三档仍可用旧快照。

## 六、待用户决策

无。

## 七、给合并者的注意

- 新 decision 键：PatternLock `decision["xhard"]["path_search_max_attempts"]`（默认 20000）；RouteStick `decision["xhard"]["segment_count_range"]`（默认 `[15, 21]`，源自 `config_xhard.length`）。S4 重导 `scripts/configs/newtask-v5/sampling_config.json` 时会自动带上。
- 新方法：`PatternLock._xhard_decision(key)`、`PatternLock._check_xhard_path(path_nodes, num_rows, num_cols, length_range)`（静态）、`RouteStick._xhard_segment_count_range() -> (lo, hi)`。
- `test_sampling_config_split.py::test_snapshot_matches_source` 在 S4 重导 / 切换快照前会一直失败（V4 快照过期）。
- 新测试文件的假实例工具 `_load(mod, cls, seed, difficulty, sampling=None, spec=None, tweak=None)` 可供其他 CPU 侧 `_load_scene` 单测参考（需要桩掉的只有 `TableSceneBuilder` 与 `build_gray_white_target`）。
