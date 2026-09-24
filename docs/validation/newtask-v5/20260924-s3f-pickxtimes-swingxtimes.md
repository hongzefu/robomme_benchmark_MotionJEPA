# V5 S3f：PickXtimes 与 SwingXtimes 的 xhard 去扎堆（2026-09-24）

> 对应计划：`NEWTASK_RELEASE_V5_PLAN.md` 1.4 L43～L46、2.0①、2.13、2.14、3.5 P1、第二部分「一」S3f 行。
> 工作树：`/data/hongzefu/robomme_v5_wt/pickswing`（分支 `v5wt-pickswing`，基线 12.120 `328e607`），未 commit。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 |
|---|---|---|---|
| `src/robomme/robomme_env/PickXtimes.py` | 模块头 import | 加 `cube_obb2d_exact` | 精确 OBB（2.0①） |
| 同上 | `XHARD_DECISION` | 删 `target_cube_position_policy.corner_bias`；`target_cube_position_policy.region_half_size` 与 `distractor.region_half_size` 0.2 → **0.25**；新增顶层 `min_center_dist_m: 0.08`；`goal_position_policy` 不变 | L43 (c)、L46、L44 |
| 同上 | 新增模块常量 `XHARD_CUBE_MAX_TRIALS = 1024` | 有色 + 干扰方块每块拒绝预算 | L45 |
| 同上 | `_spawn_scene_objects_xhard` | 不再读/传 `corner_bias`，不再 `record("layout.cube_corner_bias")`；改为 `record("layout.cube_min_center_dist", 0.08)`；建 `self._xhard_cube_obbs = []`；`spawn_random_cube(..., max_trials=1024, min_center_dist=(0.08, self._xhard_cube_obbs))`；放下后 `self._append_cube_obstacle_xhard(cube, avoid)` 代替 `avoid.append(cube)` | 2.13 |
| 同上 | 新增方法 `_append_cube_obstacle_xhard(cube, avoid)` | `cube_obb2d_exact(cube, self.cube_half_size)` 同时进 `self._xhard_cube_obbs` 与 `avoid` | 已放方块作为精确障碍 + 中心距参考点 |
| 同上 | `_spawn_distractors_xhard` | 同样加 `max_trials=1024`、`min_center_dist=(0.08, self._xhard_cube_obbs)`、精确 OBB 登记 | 6 块共用一张表 |
| `src/robomme/robomme_env/SwingXtimes.py` | 模块头 import | 加 `cube_obb2d_exact` | 同上 |
| 同上 | `XHARD_DECISION` | 新增 `min_center_dist_m: 0.08` | L44 |
| 同上 | `_load_scene` 有色方块循环（三档共用） | 外包显式分支 `if self.difficulty == "xhard": self._spawn_colored_cubes_xhard(generator, avoid, color_groups)` / `else:` **原循环逐字保留，只缩进一级**（`git diff -w` 只有新增 6 行；S2a 改的 `_scene_gen_error(self.difficulty)` 原样保留） | 2.14「非 xhard 一支逐字保留」 |
| 同上 | 新增方法 `_spawn_colored_cubes_xhard`、`_append_cube_obstacle_xhard` | xhard 有色方块：区域/间距/yaw/取值点路径/预算（默认 256）与原循环相同，另加 0.08 中心距与精确 OBB 登记；`record("layout.cube_min_center_dist")`；放不下抛 `_RealSceneGenerationError` | 2.14 |
| 同上 | `_spawn_distractors_xhard` | 加 `min_center_dist=(0.08, self._xhard_cube_obbs)` 与精确 OBB 登记 | 2.14 |
| `tests/lightweight/test_v5_xhard_pickswing.py`（新） | — | 20 条单测（见第三节） | 验收 |
| `tests/lightweight/test_v4_xhard_pickxtimes.py` | `test_decision_xhard_entries`、`test_native_blocks_are_independent_copies`、`test_guard_allows_declared_xhard_narrowing`、`test_guard_rejects_original_or_undeclared`、文件头说明 | V4 断言改 V5 语义：xhard 键集合加 `min_center_dist_m`、方块区 `{center, 0.25}` 无 corner_bias；独立拷贝改用 `region_half_size` 验证；守卫放行样例从 corner_bias 0.5/0.0 改为 `min_center_dist_m` 0.06/0.10；拒绝样例新增「把已删的 corner_bias 塞回 xhard」 | corner_bias 已删 |
| `tests/lightweight/test_v4_xhard_swingxtimes.py` | `test_decision_xhard_entries` | xhard 键集合 `{"distractor"}` → `{"distractor", "min_center_dist_m"}`，并断言 0.08 | 新键 |

未改：`_spawn_scene_objects_native`、`_load_scene`（Pick）、任何 `config_easy/medium/hard` 与 `NATIVE_SAMPLING`、`utils/object_generation.py`、`utils/xhard.py`（`corner_push` 与 `spawn_random_cube` 的 `corner_bias` 形参保留）、录像器、`scripts/` 顶层、V4 配置。

### 抽样顺序
- Pick：按钮 → `randperm(3)` → `randint(3)` → 圆盘（G1 先放盘）→ 3 有色 → `randint(3)` 选目标 → [恢复抽样] → 3 干扰，**不变**；只是每块 trial 次数因规则改变（N5 按 L1 (a) 重冻）。
- Swing：按钮 → `randperm` → `randint` → 3 有色 → 两圆盘 → 目标 → 干扰，不变。精确 OBB 让两个圆盘也按方块真实 yaw 避让（原先方块 actor 路径退化），这是计划预期的「圆盘放不下 1.9% → 3.6%」的来源。

## 二、原三档逐位不变的静态自查

| diff 处 | 原三档为何不执行 / 不改随机流 |
|---|---|
| 两文件 import `cube_obb2d_exact` | 纯导入，无副作用 |
| 两个 `XHARD_DECISION` 改值 / 新键 | 只在 `decision["xhard"]` 子树（`_strip_xhard` 后与原值相同，V4 测试 `test_decision_visible_part_unchanged` 通过） |
| `XHARD_CUBE_MAX_TRIALS` | 只被 xhard 方法引用 |
| Pick `_spawn_scene_objects_xhard` / `_spawn_distractors_xhard` / `_append_cube_obstacle_xhard` | 只在 `_load_scene` 的 `if self.difficulty == "xhard"` 分支调用（该分支未改） |
| Swing `_load_scene` 新 `if/else` | 原三档只多一次字符串比较，进 `else`，其中循环 AST 与改动前逐字相同（单测锁定 ast.dump 哈希） |
| Swing 新方法 / `_spawn_distractors_xhard` | 只在 xhard 调用 |

动态自查：离线场景对 easy/medium/hard × 6 seed × 两环境跑真实 `_load_scene`，规格 SHA-256 与改动前代码（`328e607`）金标准相同（`test_native_tiers_offline_specs_unchanged`）。
V0：`git diff -U0 src/ | grep -E "config_(easy|medium|hard)|NATIVE_SAMPLING"` 无输出，零改动。

## 三、测试

### 3.1 离线场景（新测试的基础设施）
`test_v5_xhard_pickswing.py` 提供 `OfflineScene` / `run_offline(task, seed, difficulty, spec)` / `sweep(task, seeds)`：用假 actor 顶替 `actors.build_cube` 与圆盘 builder、trimesh 盒子顶替 `get_actor_obb`、复刻 `build_button` 取值段，调用**仓库真实的** `_load_scene`。可信度核验：
- 改动前代码 + 离线场景 vs v4-01 冻结规格（Pick 10 + Swing 10，比 `layout` 与 `objects`）：**20/20 逐位一致**（`HARNESS_V4_PARITY=20/20`）。
- V5 代码 + 离线场景 vs 本机真实模拟器 `gym.make(...).reset()` 导出规格（Pick 4100000/4100300/4100003/5000123，Swing 4300000/4300300/4300777/5000123）：**8/8 逐位一致**（`HARNESS_V5_REAL_PARITY=8/8`）。

### 3.2 新单测（20 条，全过，约 10 s）
- 决策值：Pick 键集合、无 corner_bias、半宽 0.25/0.25、圆盘 0.2、0.08、`XHARD_CUBE_MAX_TRIALS == 1024`；Swing 键集合与 0.08；Pick 源码无 `corner_bias=` 实参、无 `cube_corner_bias`。
- 原三档：`_spawn_scene_objects_native` 与 Swing 原循环 AST 哈希锁定；Swing 分支结构（xhard 调新方法、else 恰为原循环）；离线规格金标准哈希。
- 400 seed（5000000～5000399）离线 reset，判定行（`-s` 输出）：
  ```
  V5_EXACT_OBB=PASS task=PickXtimes degenerate=0 actor_cubes_in_avoid=0 include_existing_true=0 premade=22400 bad_axes=0 gap_violations=0
  V5_EXACT_OBB=PASS task=SwingXtimes degenerate=0 actor_cubes_in_avoid=0 include_existing_true=0 premade=18424 bad_axes=0 gap_violations=0
  V5_PICK_DISPERSION=PASS min_pair_lt_0p08=0.000 episodes=400 min_of_min=0.0802 median_min=0.0949
  V5_SWING_SPACING=PASS min_pair_lt_0p08=0.000 episodes=392 min_of_min=0.0800 median_min=0.0963
  V5_RESET_FEASIBILITY=PASS task=PickXtimes fail=0/400 rate=0.0000 bound=0.015 classes={}
  V5_RESET_FEASIBILITY=PASS task=SwingXtimes fail=8/400 rate=0.0200 bound=0.04 classes={'SceneGenerationError:First target sampling failed': 6, 'SceneGenerationError:Second target sampling failed': 2}
  PICK_GOAL_DIST median=0.593 p95=0.670 max=0.684
  ```
  `V5_EXACT_OBB` 的口径：审计 xhard 每次 spawn 调用的 `avoid`，方块 actor（旧退化路径）个数 0、`include_existing=True` 次数 0、所有预制三元组的轴正交单位；6 块按放置顺序两两做「后放方块外扩 min_gap 的精确 OBB 与先放方块精确 OBB 不相交」检查，违例 0；`_xhard_cube_obbs` 与 `cube_obb2d_exact(actor)` 逐位相同。
  间距判定允许 1e-6 的 float32 舍入（参考点取自 actor 的 float32 位姿）。
- Pick 区域：6 块都在 ±0.25（内缩半边长）内且确有落在 0.2 以外环带的；圆盘仍在 ±0.2；规格无 `layout.cube_corner_bias`，有 `layout.cube_min_center_dist = 0.08`。
- 失败形态：两环境方块放不下（顶替 spawn 抛 RuntimeError）都抛真 `SceneGenerationError`。
- N17：合规冻结规格回放零 mismatch；把 `magenta_0` 挪到第一个有色方块旁 3 cm 回放 → 两环境都抛 `EpisodeSpecError`（干扰方块不在 try 包装内）；Swing 把第二个有色方块挪近 → 被 `_load_scene` 最外层 try 包成真 `SceneGenerationError`，原因链含 `EpisodeSpecError`（锁定现状，见第六节）。

### 3.3 离线大样本（每环境 3000 局，seed 6000000 起，同一离线场景）

| 指标 | Pick V4（改动前） | **Pick V5** | Swing V4（改动前） | **Swing V5** |
|---|---|---|---|---|
| reset 失败率 | 0/3000 | **0/3000** | 59/3000 = 1.97% | **94/3000 = 3.13%**（圆盘一 46、圆盘二 48） |
| 6 块最小中心距 最小 / 中位 | 0.042 / 0.073 | **0.0800 / 0.096** | 0.041 / 0.083 | **0.0800 / 0.096** |
| 最小中心距 < 8 cm 的局 | 69.7% | **0** | 44.5% | **0** |
| 最小中心距 < 10 cm 的局 | 94.0% | 59.1% | 76.9% | 58.1% |
| 10 cm 三块团（并查集最大连通 ≥3） | 47.0% | **10.7%** | 23.0% | **11.4%** |
| 目标圆盘离基座 中位/p95/最大 | 0.579/0.671/0.691 | 0.579/0.671/0.691（圆盘区与 G1 不变，逐局相同） | — | — |
| 目标方块离基座 中位/p95/最大 | 0.624/0.705/0.716 | 0.567/0.741/**0.776**，>0.75 m 占 2.8% | — | — |

与计划对照：Pick 失败率计划估 ≈1%，实测 0/3000（与 P1 离线 0/3000 一致）；Swing 计划估 3.6%，实测 3.1%，V4 对照 2.0%（计划 1.9%）；10 cm 三块团 Pick 10.7%（P1 10.2%）、Swing 11.4%（计划 10.3%）。

### 3.4 全量轻量测试
`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider`：
`47 failed, 958 passed, 22 skipped, 74 deselected, 12 errors in 179.10s`。失败集合 = 基线 58 条 ∪ **1 条**：
`tests/lightweight/test_sampling_config_split.py::test_snapshot_matches_source`——报 `scripts/configs/newtask-v4/sampling_config.json 与源码提取结果不一致`，即 V4 快照校验因 xhard decision 改动而失败，属于 AGENT_RULES「S3 追加说明」中 V4 作废的预期，未改 V4 快照（主会话 S4 统一处理）。

## 四、演示（本机 GPU 1，`scripts.parity.v4_demo_probe`，episode 9 即无恢复，代码内 xhard 默认）

| 环境 | seed | 来源 | reset | 演示 | 步数 | 墙钟 | 备注 |
|---|---|---|---|---|---|---|---|
| PickXtimes | 4100000 | v4-01 ep0 | ✓ | ✓ | 1017 | 135 s | num 6；圆盘离基座 0.485 m，目标方块 0.727 m |
| PickXtimes | **4100300** | v4-01 ep3 | ✓ | ✓ | 1309 | 168 s | num 7；圆盘 0.422 m，目标方块 0.699 m；6 块最小距 0.085 |
| PickXtimes | 4100600 | v4-01 ep6 | ✓ | ✓ | 1122 | 140 s | num 7；圆盘 0.599 m，目标方块 0.531 m |
| PickXtimes | 4100003 | P1 远角 seed | ✓ | ✓ | 1913 | 231 s | num 13；圆盘 0.568 m，**目标方块 0.765 m**（与 P1 探针同值） |
| PickXtimes | 4100777 | 新 seed | ✓ | ✓ | 941 | 114 s | num 6；圆盘 0.568 m，目标方块 0.598 m |
| SwingXtimes | 4300000 | v4-01 ep0 | ✓ | ✓ | 649 | 87 s | num 5，最小距 0.100 |
| SwingXtimes | 4300300 | v4-01 ep3 | ✓ | ✓ | 826 | 105 s | num 7，最小距 0.094 |
| SwingXtimes | 4300600 | v4-01 ep6 | ✓ | ✓ | 926 | 119 s | num 8，最小距 0.092 |
| SwingXtimes | 4300777 | 新 seed | ✓ | ✓ | 576 | 72 s | num 4，最小距 0.092 |

`DEMO_PROBE task=PickXtimes ok=5/5 by_class={}`、`DEMO_PROBE task=SwingXtimes ok=4/4 by_class={}`，无失败需归因。
产物：`artifacts/newtask-v5/demo-probe/s3f-pick/`、`s3f-swing/`（h5、视频、`summary.jsonl`）与同名 `.log`。

## 五、与计划不符之处

1. **Pick reset 失败率**：计划 2.13 估「均匀 + 8 cm + 1024 次约 1%」，本实现离线 3000 局实测 0（P1 探针同样 0/3000）。数值比计划乐观，不影响设计；注释已写实测口径。
2. **「目标离基座」口径**：P1 报告写「目标圆盘离基座最大 0.715 → 0.778 m」，但 P1 脚本 `offline_p1.py` 实际算的是**目标方块**（`pts[target_idx]`）。圆盘区（0.2）与 G1 未变，目标圆盘距离在 V4/V5 逐局相同（最大 0.691 m）；变远的是目标方块（最大 0.716 → 0.776 m）。本报告两者都列。
3. `max_trials` 1024 放成模块常量 `XHARD_CUBE_MAX_TRIALS`，没有放进 `XHARD_DECISION`（计划表把它列为独立字段，未写 decision 键；放常量可避免多一个可被 sampling_config 改的键）。Swing 维持默认 256（任务说明只要求 Pick）。
4. `min_center_dist_m` 放在 `XHARD_DECISION` 顶层（两环境同名），不在 `target_cube_position_policy` 下，因为它同时约束干扰方块。
5. Swing 的 xhard 有色方块用独立方法 `_spawn_colored_cubes_xhard` 而不是在 `_load_scene` 里内联第二份循环，`_load_scene` 只多一个 `if/else`。

## 六、待用户决策

无改变设计意图的待决项。给主会话的提示：
- Swing 的有色方块与两个圆盘在 `_load_scene` 最外层 `try` 内（S2a 结构），xhard 下回放违规抛的 `EpisodeSpecError` 会被包成真 `SceneGenerationError`（可重试类），原因链保留；干扰方块在 try 之外，直接抛 `EpisodeSpecError`。Pick 的 xhard 方法只捕 `RuntimeError`，`EpisodeSpecError` 原样上抛。正式生成 `--max-attempts 1`，只影响失败分类。已用单测锁定现状。
- `scripts/README.md`（V4 章节）仍写 `layout.cube_corner_bias` 与 PickXtimes「半宽 0.2、corner_bias 0.5」，本步没改（范围外、属 V4 文档），S4/S6 重写 README 时一并更新。

## 七、给合并者的注意事项

- 新 API（两环境各一份，签名相同）：`_append_cube_obstacle_xhard(self, cube, avoid)`——把 `cube_obb2d_exact(cube, self.cube_half_size)` 追加到 `self._xhard_cube_obbs` 与 `avoid`；`self._xhard_cube_obbs` 在 Pick 的 `_spawn_scene_objects_xhard`、Swing 的 `_spawn_colored_cubes_xhard` 开头初始化，干扰方块方法依赖它已存在。
- Swing 新方法：`_spawn_colored_cubes_xhard(self, generator, avoid, color_groups)`。
- Pick 模块常量：`XHARD_CUBE_MAX_TRIALS = 1024`。
- 规格新字段 `layout.cube_min_center_dist`（两环境）；删除字段 `layout.cube_corner_bias`（Pick）。
- SwingXtimes `_load_scene` 原循环整体缩进一级，合并时用 `git diff -w` 看；S2a 的 3 处 `_scene_gen_error(self.difficulty)` 保留。
- `test_v5_xhard_pickswing.py` 的离线场景（`OfflineScene` / `run_offline` / `sweep`）可复用于其他方块类环境；其原三档金标准哈希取自 `328e607`，若其他 S3 步合并改了 `object_generation.py` 的默认路径而导致哈希变化，说明原三档被动了。
