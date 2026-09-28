# robomme_hard：RoboMME 新值四档（xhard1～xhard4）环境包

## ① 一句话与对拍结论

`robomme_hard` 与官方 `robomme` 并列、分层继承：`src/robomme/` 逐字节等于官方 `1fadc0ec`（`UPSTREAM_BYTES=PASS`），本包只放差异——16 个环境类与改过／新增／传递依赖改过模块的 utils、wrapper 复制；依赖闭包干净的官方模块用 shim 借用；`BenchmarkEnvBuilder` 子类化并新增 `dataset="test-hard"`（每任务 80 局，xhard4-only 的 StopCube／InsertPeg／MoveCube 为 20 局）。

三侧对拍（A40@greatlakes，16 worker，判定为「输入绑定、结构与任务成功一致，且动作／状态／图像／帧数差异在标定容差内」，不是字节级）：

```text
PARITY_O_P=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 tol=PASS action_max=0.0275/0.0413 state_max=0.0274/0.0411 image_mad=0.144/1 frames_max=0/5 sha_equal=143 frames_equal=144 binding_ok=144 shape=16x3x3
PARITY_P_H=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 tol=PASS action_max=0.0275/0.0413 state_max=0.0274/0.0411 image_mad=0.144/1 frames_max=0/5 sha_equal=143 frames_equal=144 binding_ok=144 shape=16x3x3
PARITY_O_H=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 tol=PASS action_max=0/0.0413 state_max=0/0.0411 image_mad=0/1 frames_max=0/5 sha_equal=144 frames_equal=144 binding_ok=144 shape=16x3x3
PARITY_P_H=PASS tier=xhard compared=165 identity_equal=165 setup_equal=165 schema_equal=165 success_equal=165 both_success=165 tol=PASS action_max=0/0.0413 state_max=0/0.0411 image_mad=0/1 frames_max=0/5 sha_equal=165 frames_equal=165 binding_ok=165 shape=13x3x3+16x3
```

O 官方（编排 `d53f21a7` + 环境源码 `1fadc0ec`）、P 修改前（tag `pre-hard-split`）、H 本包（拆包后 HEAD）。原三档 16 任务 × 3 档 × 3 局 = 144，O↔H 全部逐字节相同；xhard 为 xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165，与 S4 交付全部逐字节相同。详见 `docs/validation/newtask-v6/hard-split/stage4.md`。

## ② 四档定稿表（逐字搬自 `0925-newtask-release-v6-plan.md` 第一部分 §三）

| 环境 | 梯度维度 | hard | xhard1 | xhard2 | xhard3 | xhard4 | 备注 |
|---|---|---|---|---|---|---|---|
| BinFill | 投入块数（总块 12） | [3,5] | 6 | 7 | 8 | 9 | 无演示段，8/9 块约 1500～1900 步，允许超 1301 |
| PickXtimes | 次数 / 干扰块 | [4,5] / 0 | [6,7] / 1 | [8,9] / 2 | [10,12] / 3 | [13,15] / 3 | 干扰颜色表若 ≥4 色则 xhard4 取 4 |
| SwingXtimes | 轮数 / 干扰块 | 3 / 0 | [4,5] / 1 | [6,7] / 2 | [8,9] / 3 | [10,11] / 3 | reset 约 96%（放圆盘采样失败，与干扰无关） |
| PickHighlight | pick / 总块 | 3 / 6 | 4 / 7 | 5 / 8 | 6 / 9 | 7 / 10 | 干扰数 = 总块 − pick，均值全程 3（不作梯度）；总块 10 时 reset 73% |
| VideoUnmask | 干扰容器 / pick | 0（15 容器）/ 2 | 8 / 2 | 10 / 3 | 13 / 3 | 15 / 3 | pick ≤3（可藏 cube 的容器只有 3 个），靠干扰数区分；内环容器数不作梯度 |
| ButtonUnmask | 干扰容器 / pick | 0 / 2 | 8 / 2 | 10 / 3 | 12 / 3 | 14 / 3 | 同上 |
| VideoUnmaskSwap | swap / pick / 外环干扰 | [2,3] / 2 / 0 | [4,5] / 2 / 4 | [6,7] / 3 / 6 | [8,9] / 3 / 8 | [10,12] / 3 / 10 | 外环含 cube 数 = 干扰一半；交换步数 xhard1 50、其余 33 |
| ButtonUnmaskSwap | swap / pick / 外环干扰 | [2,3] / 2 / 0 | 4 / 2 / 4 | 5 / 3 / 6 | [6,7] / 3 / 8 | [8,9] / 3 / 10 | 同上 |
| VideoRepick | 块数 / swap / repick | 另一种任务 | 4 / [3,4] / 2 | 5 / [5,6] / 3 | 6 / [7,8] / 4 | 7 / [9,12] / [5,6] | 4～6 块 reset 约 60%；7 块待实测 |
| PatternLock | 节点数（5×5，不重访，预算 20000） | [4,8] | [9,12] | [13,16] | [17,20] | [21,25] | 执行段 ≤ 约 850 步 |
| RouteStick | 段数 L | [4,7] | [8,10] | [11,13] | [14,16] | [17,21] | 执行段 = 50·L |
| VideoPlaceButton | 放台次数（都放回原位） | 2（放桌面） | 1 块 3 次 | 1 块 4 次 | 2 块 5 次 | 2 块 6 次 | 额外放台 = 放到无关台（原版 `additional_place` 语义），见四.9；xhard3/4 台数 4→5（`config_xhard3/4["targets"]=5`，xhard1/2 仍 4），额外放台按完整序列占用表抽取，before 题答案 = 按钮前最后一次放置的台 |
| VideoPlaceOrder | 总放台次数（都放回原位） | 1 块 v∈[2,4] | 2 块 (2,3)=5 | 2 块 (3,3)=6 | 2 块 (3,4)=7 | 2 块 (4,4)=8 | 每档总数定值，哪块多访问随机 |
| MoveCube | 不加档 | 原三档同值 | — | — | — | 圆环 U | 只有 xhard4 |
| InsertPeg / StopCube | 不加档 | 原三档同值 | — | — | — | 原 xhard 改名 | 数值不动 |


## ③ 逐文件：复制／借用／子类／新增（`scripts/parity/upstream_guard.py manifest-md` 生成）

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

## ④ 机制

- **`sampling_config` 两块**：每个环境的 `native_blocks(cls, release=...)` 返回 `decision`（按档位的新值取值）与 `native`（原三档参数与位置），`gym.make(..., sampling_config={"decision","native"})` 显式传入；`utils/sampling_config.py::assert_native_decision` 保证去掉新值键后与原值全等。
- **`SpecRecorder` 导出与回注**（`utils/episode_spec.py`）：`spec=None` 时导出（每个取值点在原调用点记下）；传 `native_episode_spec` 时回注——原抽样照常发生，但建场景用的值一律取冻结规格，原抽样只作兼容核验记入 `mismatches`；`record()` 只记录不回注的观测值。评估侧用 `env_record_wrapper.spec_binding(env)` 取摘要：回注点（trace `source="spec"`）必须零差，记录点（`source="record"`）浮点差 ≤ `RECORDED_FLOAT_TOL=1e-5` 计 `recorded_drift`（U-13 方案甲）。
- **jsonl 两段与两个哈希**（`env_record_wrapper/hard_specs.py`，`schema="hard-specs/2"`）：签 `task tier candidate episode seed attempt spec spec_sha256` 由 `identity_sha256` 覆盖；结果 `selected tried initial_selected rollout` 不进身份。`delivery_sha256` 盖排序后的 `(task, tier, candidate, seed, spec_sha256, rollout.h5_sha256)`（只取 `selected` 且 `rollout.status=="ok"`），锁住正式交付集合。
- **seed 偏移**：`seed = offset(tier) + env_code × 100000 + episode × 100 + attempt`，offset xhard4 6e6、xhard1 8e6、xhard2 10e6、xhard3 12e6（`hard_specs.seed_rule_for(tier, "v6")`），与 train／test／val／heldout 及彼此都不重叠。
- **注册表与命名空间归属**：16 个环境类 `@register_env("<id>", override=True)`，导入本包即接管 16 个 id（与导入顺序无关）；包 `__init__` 末尾断言 `REGISTERED_ENVS[uid].cls.__module__` 属于本包，并断言 16 个环境模块与 `utils` 包里本包同名可调用对象都属于本包（专挡官方 `subgoal_evaluate_func` 的星号导入回灌）。同进程要官方行为须另开只导入 `robomme` 的进程。
- **借用闭包规则**：借用资格按传递闭包判，不按单文件字节——shim 目标在官方源码上的依赖闭包不得含任何被本包复制的模块（`BORROWED_DEPS`）。复制文件里的绝对导入 `robomme.<path>`：`<path>` 在 shim 清单内的保持，是复制件的一律改成 `robomme_hard.`（`ABS_IMPORT`）。

## ⑤ 使用

```python
from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, TIER_MAX_STEPS   # 与官方唯一不同的 import
builder = BenchmarkEnvBuilder(env_id="BinFill", dataset="test-hard", action_space="joint_angle", max_steps=1300)
for episode in range(builder.get_episode_num()):             # BinFill 80 局：xhard1 二十局 → xhard4 二十局
    seed, tier = builder.resolve_episode(episode)             # (seed, tier)，与官方二元组同形
    env = builder.make_env_for_episode(episode, max_steps=TIER_MAX_STEPS[tier])
    obs, info = env.reset()
```

- 与官方 `dataset="test"` 的对应：`test` 每任务 50 局、三档混排、步数上限一个数；`test-hard` 每任务 80（或 20）局，按 xhard1→xhard4 排列、档内按 `candidate` 升序，步数上限按档 `TIER_MAX_STEPS = {xhard1: 1500, xhard2: 1700, xhard3: 2000, xhard4: 2600}`（沿用上次评估，便于对比；不逐局传就用构造时的 `max_steps`）。
- `builder.resolve_identity(episode)` 只读返回 `{episode, tier, candidate, seed, spec_sha256, source_run}`；`spec_binding(env)` 须在 `reset()` 之后调用。
- `train`／`test`／`val` 行为同官方；只有四个 Unmask 任务的 `train` 元数据改读本包 `env_metadata/train`（400 条）。`override_metadata_path` 语义同官方。
- 两阶段生产命令（不随包分发，在仓库 `scripts/injection-dev/` 下，路径直跑）：`freeze_specs.py`（定规则 → 抽签 → 封存，只落一份 jsonl）、`generate_h5.py --mode continue|replay`（只读 jsonl 生成 h5，按状态机回写）。

## ⑥ 红线（0927 计划第二部分 R1～R5、R11）

- R1 `src/robomme/**` 是官方 `1fadc0ec` 原样，不放任何自有文件（`UPSTREAM.json`、说明一律放本包或 `docs/`）。
- R2 `scripts/parity/official/` 四文件不改；shim 不含逻辑（≤ 3 行非注释行，守卫检查）。
- R3 `identity_sha256` 与 `delivery_sha256` 的覆盖范围不变；要变就换 `schema` 版本并重跑身份类闸门。
- R4 第二阶段回写只改 `selected`、`tried`、`rollout`；锁在 `<specs>.lock`；回写前整份文件 sha 必须与读入时相同。
- R5 同进程导入 `robomme_hard` 后 16 个 id 归它；需要官方行为另开进程；O／P 侧对拍进程不得导入 `robomme_hard`。
- R11 对拍只在 A40@greatlakes 上生成；各侧 manifest 如实记录硬件与驱动，驱动不明写 `unknown`；Ada 产物不混入 `PARITY_*`。

## ⑦ `dataset_for_parent="test"` 绕行

官方父类 `__init__` 的 `_ALLOWED_DATASETS` 只认 `train/test/val`，而官方代码不能改。子类对 `test-hard` 先以 `dataset="test"` 过父类校验，再把 `self.dataset` 改回 `"test-hard"`；父类顺手读的 test 元数据随即清空、不被使用。官方父类签名若变化属于升级流程（`UPSTREAM.json` 换锚点、重跑全部闸门）。
