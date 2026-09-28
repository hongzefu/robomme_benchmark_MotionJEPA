# 拆包阶段 1：建 `src/robomme_hard`、迁移 test-hard 20 局规格（2026-09-28）

计划：`0927-robomme-hard-layered-plan.md` 第一部分 §三～§五、第二部分 §1.2。代码锚点：开工时 HEAD `7a6cee35`（12.205）。本阶段不改 `src/robomme`。

## 一、包结构（复制／借用／子类）

- 复制：16 个环境类（装饰器改 `@register_env("<id>", override=True)`）、`robomme_env/__init__.py`（末尾追加 `ENV_IDS` 16 元组）、`utils/__init__.py`、改过的 8 个 utils、新增的 9 个 utils、传递依赖改过模块的 `subgoal_evaluate_func`／`task4recovery`、`RecordWrapper.py`（`fail_safe_limit=5000`，不加 h5 attrs）、`DemonstrationWrapper.py`、`OraclePlannerDemonstrationWrapper.py`、四份 Unmask 任务 train 元数据（`cp`，400 条）。
- 绝对导入改写（按次数断言）：`subgoal_planner_func.py` 两处（`from robomme.robomme_env import *`、`from robomme.robomme_env.utils import *`）、`subgoal_evaluate_func.py` 一处、`vqa_options.py` 一处、`OraclePlannerDemonstrationWrapper.py` 一处、`RecordWrapper.py::step` 内延迟导入一处，全部改为 `robomme_hard.`。
- 借用 shim 18 个（13 utils + 4 wrapper + `logging_utils`），每个三行：`sys.modules[__name__] = importlib.import_module("robomme.<同名模块>")`。
- 新写：`__init__.py`（导入检查）、`env_record_wrapper/__init__.py`、`hard_specs.py`（由 `scripts/parity/v4_specs.py` 下沉；`TIER_MAX_STEPS`、`RECORDED_FLOAT_TOL=1e-5`、`spec_binding()`、`identity_sha256`／`delivery_sha256`、`load_specs`）、`hard_builder.py`（官方 `BenchmarkEnvBuilder` 子类，`dataset="test-hard"`，55 格表 `EXPECTED_CELLS` 断言，只读 `resolve_identity`，`from_v4_specs` 薄包装）。
- `pyproject.toml`：`packages = ["src/robomme", "src/robomme_hard"]`（hatch 构建配置，不改依赖与 `uv.lock`）。
- `UPSTREAM.json` 的 shim 条目补 `target_bytes`／`target_cheap`（首尾 1 MiB blake2b），供导入时 cheap 校验。

逐文件表（`upstream_guard.py manifest-md` 生成）：

| 文件 | 做法 | 官方对应 |
|---|---|---|
| `src/robomme_hard/__init__.py` | 复制 | `src/robomme/__init__.py` |
| `src/robomme_hard/env_record_wrapper/DemonstrationWrapper.py` | 复制 | `src/robomme/env_record_wrapper/DemonstrationWrapper.py` |
| `src/robomme_hard/env_record_wrapper/EndeffectorDemonstrationWrapper.py` | 借用 shim | `robomme.env_record_wrapper.EndeffectorDemonstrationWrapper` |
| `src/robomme_hard/env_record_wrapper/FailAwareWrapper.py` | 借用 shim | `robomme.env_record_wrapper.FailAwareWrapper` |
| `src/robomme_hard/env_record_wrapper/MultiStepDemonstrationWrapper.py` | 借用 shim | `robomme.env_record_wrapper.MultiStepDemonstrationWrapper` |
| `src/robomme_hard/env_record_wrapper/OraclePlannerDemonstrationWrapper.py` | 复制 | `src/robomme/env_record_wrapper/OraclePlannerDemonstrationWrapper.py` |
| `src/robomme_hard/env_record_wrapper/RecordWrapper.py` | 复制 | `src/robomme/env_record_wrapper/RecordWrapper.py` |
| `src/robomme_hard/env_record_wrapper/__init__.py` | 复制 | `src/robomme/env_record_wrapper/__init__.py` |
| `src/robomme_hard/env_record_wrapper/episode_dataset_resolver.py` | 借用 shim | `robomme.env_record_wrapper.episode_dataset_resolver` |
| `src/robomme_hard/env_record_wrapper/hard_builder.py` | 子类 | `robomme.env_record_wrapper.episode_config_resolver.BenchmarkEnvBuilder` |
| `src/robomme_hard/env_record_wrapper/hard_specs.py` | 新增 | `—` |
| `src/robomme_hard/logging_utils.py` | 借用 shim | `robomme.logging_utils` |
| `src/robomme_hard/robomme_env/BinFill.py` | 复制 | `src/robomme/robomme_env/BinFill.py` |
| `src/robomme_hard/robomme_env/ButtonUnmask.py` | 复制 | `src/robomme/robomme_env/ButtonUnmask.py` |
| `src/robomme_hard/robomme_env/ButtonUnmaskSwap.py` | 复制 | `src/robomme/robomme_env/ButtonUnmaskSwap.py` |
| `src/robomme_hard/robomme_env/InsertPeg.py` | 复制 | `src/robomme/robomme_env/InsertPeg.py` |
| `src/robomme_hard/robomme_env/MoveCube.py` | 复制 | `src/robomme/robomme_env/MoveCube.py` |
| `src/robomme_hard/robomme_env/PatternLock.py` | 复制 | `src/robomme/robomme_env/PatternLock.py` |
| `src/robomme_hard/robomme_env/PickHighlight.py` | 复制 | `src/robomme/robomme_env/PickHighlight.py` |
| `src/robomme_hard/robomme_env/PickXtimes.py` | 复制 | `src/robomme/robomme_env/PickXtimes.py` |
| `src/robomme_hard/robomme_env/RouteStick.py` | 复制 | `src/robomme/robomme_env/RouteStick.py` |
| `src/robomme_hard/robomme_env/StopCube.py` | 复制 | `src/robomme/robomme_env/StopCube.py` |
| `src/robomme_hard/robomme_env/SwingXtimes.py` | 复制 | `src/robomme/robomme_env/SwingXtimes.py` |
| `src/robomme_hard/robomme_env/VideoPlaceButton.py` | 复制 | `src/robomme/robomme_env/VideoPlaceButton.py` |
| `src/robomme_hard/robomme_env/VideoPlaceOrder.py` | 复制 | `src/robomme/robomme_env/VideoPlaceOrder.py` |
| `src/robomme_hard/robomme_env/VideoRepick.py` | 复制 | `src/robomme/robomme_env/VideoRepick.py` |
| `src/robomme_hard/robomme_env/VideoUnmask.py` | 复制 | `src/robomme/robomme_env/VideoUnmask.py` |
| `src/robomme_hard/robomme_env/VideoUnmaskSwap.py` | 复制 | `src/robomme/robomme_env/VideoUnmaskSwap.py` |
| `src/robomme_hard/robomme_env/__init__.py` | 复制 | `src/robomme/robomme_env/__init__.py` |
| `src/robomme_hard/robomme_env/utils/SceneGenerationError.py` | 借用 shim | `robomme.robomme_env.utils.SceneGenerationError` |
| `src/robomme_hard/robomme_env/utils/__init__.py` | 复制 | `src/robomme/robomme_env/utils/__init__.py` |
| `src/robomme_hard/robomme_env/utils/adjacent.py` | 借用 shim | `robomme.robomme_env.utils.adjacent` |
| `src/robomme_hard/robomme_env/utils/bin_collision.py` | 新增 | `—` |
| `src/robomme_hard/robomme_env/utils/choice_action_mapping.py` | 借用 shim | `robomme.robomme_env.utils.choice_action_mapping` |
| `src/robomme_hard/robomme_env/utils/constant.py` | 借用 shim | `robomme.robomme_env.utils.constant` |
| `src/robomme_hard/robomme_env/utils/difficulty.py` | 复制 | `src/robomme/robomme_env/utils/difficulty.py` |
| `src/robomme_hard/robomme_env/utils/episode_spec.py` | 新增 | `—` |
| `src/robomme_hard/robomme_env/utils/generate_sample_action.py` | 借用 shim | `robomme.robomme_env.utils.generate_sample_action` |
| `src/robomme_hard/robomme_env/utils/object_generation.py` | 复制 | `src/robomme/robomme_env/utils/object_generation.py` |
| `src/robomme_hard/robomme_env/utils/obschange.py` | 借用 shim | `robomme.robomme_env.utils.obschange` |
| `src/robomme_hard/robomme_env/utils/oracle_action_matcher.py` | 借用 shim | `robomme.robomme_env.utils.oracle_action_matcher` |
| `src/robomme_hard/robomme_env/utils/planner_denseStep.py` | 借用 shim | `robomme.robomme_env.utils.planner_denseStep` |
| `src/robomme_hard/robomme_env/utils/planner_fail_safe.py` | 借用 shim | `robomme.robomme_env.utils.planner_fail_safe` |
| `src/robomme_hard/robomme_env/utils/reset_panda.py` | 借用 shim | `robomme.robomme_env.utils.reset_panda` |
| `src/robomme_hard/robomme_env/utils/route.py` | 复制 | `src/robomme/robomme_env/utils/route.py` |
| `src/robomme_hard/robomme_env/utils/rpy_util.py` | 借用 shim | `robomme.robomme_env.utils.rpy_util` |
| `src/robomme_hard/robomme_env/utils/sampling_config.py` | 新增 | `—` |
| `src/robomme_hard/robomme_env/utils/save_reset_video.py` | 借用 shim | `robomme.robomme_env.utils.save_reset_video` |
| `src/robomme_hard/robomme_env/utils/segmentation_utils.py` | 复制 | `src/robomme/robomme_env/utils/segmentation_utils.py` |
| `src/robomme_hard/robomme_env/utils/statechange.py` | 借用 shim | `robomme.robomme_env.utils.statechange` |
| `src/robomme_hard/robomme_env/utils/subgoal_evaluate_func.py` | 复制 | `src/robomme/robomme_env/utils/subgoal_evaluate_func.py` |
| `src/robomme_hard/robomme_env/utils/subgoal_language.py` | 复制 | `src/robomme/robomme_env/utils/subgoal_language.py` |
| `src/robomme_hard/robomme_env/utils/subgoal_planner_func.py` | 复制 | `src/robomme/robomme_env/utils/subgoal_planner_func.py` |
| `src/robomme_hard/robomme_env/utils/swap_uniform.py` | 新增 | `—` |
| `src/robomme_hard/robomme_env/utils/task4recovery.py` | 复制 | `src/robomme/robomme_env/utils/task4recovery.py` |
| `src/robomme_hard/robomme_env/utils/task_goal.py` | 复制 | `src/robomme/robomme_env/utils/task_goal.py` |
| `src/robomme_hard/robomme_env/utils/unmask_distractor_sampler.py` | 新增 | `—` |
| `src/robomme_hard/robomme_env/utils/unmask_distractors.py` | 新增 | `—` |
| `src/robomme_hard/robomme_env/utils/unmask_swap_xhard.py` | 新增 | `—` |
| `src/robomme_hard/robomme_env/utils/vqa_options.py` | 复制 | `src/robomme/robomme_env/utils/vqa_options.py` |
| `src/robomme_hard/robomme_env/utils/xhard.py` | 新增 | `—` |
| `src/robomme_hard/robomme_env/utils/xhard_home_site.py` | 新增 | `—` |

## 二、判定行（★ 为官方态：`PYTHONPATH=artifacts/hard-split/official-1fadc0ec/src`，`robomme` 解析到官方 1fadc0ec 树）

```text
$ uv run --no-sync python scripts/parity/upstream_guard.py check
UPSTREAM_BYTES=PENDING src_commit=1fadc0ec files=102 diff=39 changed=30 extra=9 missing=0
VENDOR_SAME=PASS files=4 orchestration_commit=d53f21a7
SHIMS=PASS shims=18
ABS_IMPORT=PASS files=44 retargeted=27 kept=3 unresolved=0          ★（在官方 git 对象上求闭包，与工作区状态无关）
BORROWED_DEPS=PASS shims=18 copied=33 changed_hits=0               ★
UPSTREAM_GUARD=PASS

$ ROBOMME_OFFICIAL_SRC=<官方树>/src uv run --no-sync python -m pytest tests/lightweight/test_registry_owner.py -q -s
REGISTRY_OWNER=PASS envs=16 owner=robomme_hard order=official_first   ★
NAMESPACE_OWNER=PASS envs=16 stray=0 order=official_first            ★
（hard_first、subpackage_first 两种顺序同样 PASS；测试内还把官方 spawn_random_cube 灌进 MoveCube 命名空间，检测器能报出，证明不是空检查）

$ CUDA_VISIBLE_DEVICES=1 ROBOMME_OFFICIAL_SRC=<官方树>/src uv run --no-sync python -m pytest tests/lightweight/test_wrapper_chain.py -m gpu -s
WRAPPER_CHAIN=PASS action_spaces=4 chain_equal=4 hard_modules_ok=4   ★

$ uv run --no-sync python scripts/injection-dev/migrate_smvla_specs.py build   （check 子命令复核同样全 PASS）
SOURCE_POOL=PASS raw=1717 dedup=89 merged=1628 delivery=1100 nondelivery=528
SPECS_IDENTITY=PASS files=6 tiers=4 legacy_equal=6
DELIVERY_SET=PASS compared=1100 equal=1100 cells=55 shape=13x3x20+16x20
H5_BINDING=PASS compared=1100 mismatch=0 ambiguous=0 missing=0
WROTE xhard1 rows=338 delivered=260 identity=1bfed4fbd722 delivery=9e2882114170
WROTE xhard2 rows=390 delivered=260 identity=2236f8df3e59 delivery=8092019c01e9
WROTE xhard3 rows=390 delivered=260 identity=2de16aad987f delivery=dfb1791ebda9
WROTE xhard4 rows=510 delivered=320 identity=9e1cf8f3a132 delivery=ef9d8d194174
EVAL_IDENTITIES sha256=0278a587d2f3f91dc1d68dba3ee0ac094f1e4c7d75002735ff40b9fb7daf9a44 rows=1100

$ uv run --no-sync python scripts/injection-dev/migrate_smvla_specs.py export-s4-setup
S4_SETUP count=165 sha_mismatch_vs_final_delivery=0
TIER_MAX_STEPS_SOURCE=PASS tiers=4 values=1500/1700/2000/2600 same_as=v4_eval.NEWVALUE_MAX_STEPS:1 max_exec=1209/1390/1663/2215

$ uv run --no-sync python scripts/parity/hard_regression.py s4-subset
S4_SUBSET=PASS s4=165 seed_match=165 spec_exact=154 spec_within_tol=11 max_abs=1.2e-07 injected_diff=0

$ CUDA_VISIBLE_DEVICES=1 PYTHONPATH=<官方树>/src uv run --no-sync python scripts/parity/hard_regression.py reset-replay --limit 1 --out artifacts/hard-split/stage1-smoke/reset.jsonl
HARD_RESET_REPLAY=PASS resets=1 replay=1 injected_mismatch=0 recorded_drift=0 max_abs=0 goal_mismatch=0 errors=0 shape=limit1   ★（阶段 1 单局冒烟：BinFill@xhard1 builder episode 0，seed 8400000，spec_sha256 916b71a5…，value_points=23，task_goal 与 S4 h5 逐字相等）
```

## 三、迁移口径与实测

- **身份真源**：SimpleMemVLA `aab093f` 六个 run 目录 200+60+260+260+314+6 = 1100 行（xhard4-fill 是 6 片），55 格每格恰好 20、无重复身份；抽出的 `records/eval-identities-1100.jsonl` sha256 `0278a587…`，写进四档 header 的 `eval_identities_sha256`。
- **来源池**：benchmark `1fe2d185` 六份 `specs.reselected.jsonl` 原始 1717 行；主集与补抽集同 seed 同规格的重复 89 条（xhard1 BinFill 25 + VideoPlaceOrder 15 + VideoRepick 19 = 59，xhard4 InsertPeg 30），保留评估实际所用的那一侧；合并 1628 行（正式 1100 + 非正式 528，非正式行留作将来递补）。补抽集与主集用同一 seed 公式，候选号（= 公式 episode）合并后无冲突。
- **h5 绑定**：六份 `results.jsonl` 的成功局共 1583 个 h5，16 进程重算 sha256／字节数／帧数／演示帧数约 3 分钟（缓存 `artifacts/hard-split/migrate-h5-stats.json`）；正式 1100 局 h5 全部存在，`setup` 的 seed、档位与规格一致，`task_goal` 非空（规格里没有 `task_goal` 字段，文本逐字比对放在 `S4_SUBSET` 子集与 `HARD_RESET_REPLAY` 里做）。
- **演示帧带外（U-16 照收）**：沿用上次生成报告口径（只统计 PatternLock／RouteStick 的 `info/is_video_demo` 帧数，带 750～1050），xhard1 正式局带外 40 局（PatternLock 20 局 266～423 帧、RouteStick 20 局 400～500 帧），清单写在 xhard1 header `demo_frames_out_of_band`；用原口径（主集全部成功局）复算同为 40。
- **S4 子集**：165 个 `(task, tier, seed)` 全部落在交付集；规格逐叶比对，11 局只在记录点（`SpecRecorder.record` 的路径，按任务静态收集、排除同任务 `value()` 回注路径）有 ≤ 1.2e-7 的浮点差，回注点零差。映射表 `env_metadata/test-hard/s4-to-delivery.json`，S4 setup 清单 `env_metadata/test-hard/s4-setup-manifest.json`（165 局 setup 与 h5 sha256，GL 节点读不到 `/data` 时用它比对）。

## 四、计划到实施的意外

1. 旧 `v4_specs` 按 `55f1b027` 原文执行时要从 `scripts/seed_layout.py` 取 `SeedLayout`，首次迁移在 h5 统计完成后于此处报 `ModuleNotFoundError`；补 `sys.path` 后重跑（统计走缓存）。
2. 第一次写出时带外计数统计了 13 个任务得 240，与计划所记 40 不符；查上次生成报告（`scripts/parity/v5_generation.py::DEMO_BAND` 只统计 PatternLock／RouteStick）后改为同口径，删去自己刚写出的四份 jsonl 重建；identity／delivery 两个哈希不变（该键不进身份）。
3. 迁移 dry-run 的 tmux 管道里 `grep -v` 没加行缓冲，日志到进程结束才落盘；之后的长任务管道一律 `--line-buffered`。
4. S4 子集比对的记录点判定最初用全局前缀，`layout`、`layout.cubes` 这类 f-string／跨任务路径会把回注点误归为记录点；改为按任务收集、f-string 占位符只匹配一个路径段、同任务 `value()` 路径优先按回注点处理。

## 五、核心短测

`timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q` → `4 failed, 1212 passed, 5 skipped`（180.85 s）。4 个失败（`test_TaskGoal.py` 两个、`test_step_error_handling.py` 两个）在开工前的提交 `4e3e979` 的临时 worktree 上复跑结果完全相同（`4 failed, 39 passed`），属既有失败，与拆包无关，本方案不处理。

## 六、预算计数（P3 / U-14）

本阶段 reset 1（单局冒烟），rollout 0。累计：生成侧 rollout 0／638，reset 1／715。
