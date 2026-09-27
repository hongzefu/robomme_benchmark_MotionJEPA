# 0926 方案：`src/robomme_hard/` 独立包 + `scripts/evaluation_hard.py` 接口重构（只规划不实施）

> **权威性**：本文件是「把 V6 新难度链路拆成独立包 `robomme_hard`、原包 `robomme` 回到上游原样」的实施方案；只规划，不实施，每一阶段须用户单独批准后才动手。**本方案与 P1（`scripts/` 顶层五入口冻结）、P2（`src/robomme/` 逐个批准）直接相关，第一部分「待用户裁决」一节列出的四项没有裁决前不得开工。**
> **代码锚点**：本仓库 `newtaskRelease-v5` @ `bcd7d08`（12.194；2026-09-27 更新，原初稿锚点 `716f992`／12.174；工作区在途改动见红线 R7）；生产源码含审查修复 `ca32e9b`（12.188）；V5 原始锚点 `da77662`；V1 基线 `13e5151`；上游 `RoboMME/robomme_benchmark` `main` @ `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`（2026-09-26 `git ls-remote` 实测）。
> **工作副本**：`/data/hongzefu/robomme_benchmark_MotionJEPANewTask`（环境 A，sled-vail）。上游只读快照在会话 scratchpad `upstream/`（浅克隆，用后即弃，实施时按第二部分 §2.1 重新取）。
> **commit 体例**：`<大>.<小>[.<修订>] <中文描述>`，接 12.195。
> **前置状态（2026-09-27）**：`0925-newtask-release-v6-plan.md`（S0～S5）与 `0926-v6-audit-fix-plan.md`（8.4 四步）均已完成，本方案进入可实施状态；细节见第一部分 §〇。
> **依赖锚点**：`uv.lock` / `pyproject.toml` 现状不变；本方案唯一的依赖侧改动是 `[tool.hatch.build.targets.wheel].packages` 增加 `src/robomme_hard`。
> **对话来源**：用户 2026-09-26 转贴的与合作者的对话（逐字保留在第一部分 §一），本方案是对该对话「能否实现、怎么实现」的回答。

# 第一部分（给人看）

> 2026-09-27 修订：按用户要求，第一部分只讲三件事——①env make 的接口；②`src/robomme` → `src/robomme_hard` 的文件级清单（哪些原样继承、哪些要加东西）；③三个脚本阶段（生成 json、生成规格与轨迹、评估）各自怎么把参数传进 env make。原第一部分的对话原话、逻辑链条、裁决项、验收表全部移到第二部分附录 A，内容不变。文件级事实以 2026-09-27 `git fetch` 上游 `main` 后 `git diff --name-status FETCH_HEAD HEAD -- src/robomme` 实测为准（FETCH_HEAD = `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`，本地 HEAD = `57fe972`）。

## 〇、前提实施与交付已完成；拆包仍待裁决，legacy 归档须先补齐依赖与证据保留清单（2026-09-27，两轮修订）

> 修订记录：第一轮（12.195/12.197）写入前置完成状态与 legacy 清单；第二轮按 Codex 审计（锚点 `e9ff7a2`，五条全部核实成立）与用户裁决改写。用户裁决原话：「我要的是归档V6 之前的 不再做对拍也不再生成 只作为经验教训」「robomme_hard 重跑 144 局与 S0 基线比 sha 这个是要保留的！并且需要wrap up成新的 …/scripts/parity负责对拍」「其他同意 修改计划」。

### 0.1 完成证据（判定行原文，不改述）

| 前置计划 | 状态 | 判定行 / 证据 |
|---|---|---|
| `0925-newtask-release-v6-plan.md` §5.3 S0～S5 | 完成 | S3 原三档 144 局：`NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0`（跑在 `c8c06ab`，**审查修复之前**）；S4 55 格 165 成功局；[最终报告](docs/validation/newtask-v6/20260926-final.md) |
| `0926-v6-audit-fix-plan.md` 8.4 四步 | 实施与 165 局交付完成；**语义验收仍有证据缺口** | 14 项 `src/robomme` 改动落地于 `ca32e9b`（12.188）；G1 `RESET_PARITY_NATIVE=PASS resets=48 sha_mismatch=0`；G2 `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0 declared_deltas=6`；165 局重生成为 `v6-02`，`S4_DELIVERY=PASS cells=55 successes=165 shortfall=0`；第二节 10 项检查 `failed=0`，但汇总行原文是 `SEMANTIC_SUMMARY=FAIL checks=10 failed=0 episodes_read=165 read_errors=3`（三个失败局的空 H5 被枚举），且 `PEG_NEARFAR=REPORT episodes=3` 对不上计划要求的 `PASS candidates=10`。两个缺口不阻塞拆包，V1′ 留档须原样带出；[留档](docs/validation/newtask-v6/20260927-audit-fix.md) |

### 0.2 对本方案的影响

1. **D-4 已满足**：S3 结论已出，「不改 `src/robomme/`」的时间锁解除；阶段 5 仍排在 V1′ 之后（红线 R1）。
2. **V1′ 保留（用户明令），且分量加重**：S3 跑在 `c8c06ab`，审查修复 `ca32e9b` 之后原三档只做过 48 次 reset 零漂移，**没有做过 144 局轨迹对拍**；V1′ 兼任修复后首次全量轨迹对拍。**V1′ 由新入口 `scripts/parity/hard_parity.py` 承担**（第二部分 §2.2），不再依赖 `artifacts/…/run_s3.py`。V1′ 是本方案唯一的生成预算（144 次轨迹尝试，阶段 1 一次申请）。
3. **legacy 口径改为「V6 之前的全部归档为经验教训」**：不再做 V2～V5 任何对拍与生成；相关代码、测试、配置、产物只有两种去处——经验教训文本进 `docs/`，其余删除（跟踪文件留 git 历史；`artifacts/` 未跟踪文件的唯一副本就是搬进 `docs/` 的那份）。V6 自己的中间产物同样只留现行交付。细则见 §0.3 与附录 B。
4. **现行规格是 `v6-02`**：包内 `env_metadata/xhard{1..4}/specs.jsonl` 从 `scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl` 复制（260 K / 280 K / 301 K / 367 K）；`SPECS_IDENTITY` 与 `v6-02` 比。附录 A 里的 `v6-01` 以本节为准。
5. **数字勘误**：`scripts`+`tests` 引用 `robomme` 的文件 60 个；`src/robomme` 绝对 import 7 文件；对上游 `1fadc0e` 为 26 个 .py 改、9 个 .py 新增、4 份 train 元数据改。
6. **D-1、D-2、D-3 仍待裁决**（附录 A §四）。

### 0.3 阶段 0b：legacy 归档与删除（拆包前做；执行顺序即下列编号）

目标：`scripts/` 与 `tests/` 里只剩 V6 四阶段 + V1′ 的闭包（附录 B 表 0），其余按「教训进 docs、其余删」处置。放在拆包前的理由：阶段 3 的 import 机械替换从 60 个文件缩到约 30 个。

| # | 步骤 | 判据 |
|---|---|---|
| 1 | **解依赖**：`scripts/parity/v4_specs.py` 内联 `canonical_json`/`digest`（原在 `scripts/injection/candidates/io.py`）；`tests/lightweight/test_v4_specs.py` 的 import 改为 `from scripts.parity.v4_specs import canonical_json`（审计第 2 条） | `grep -rn "scripts\.injection" scripts tests --include=*.py` 零命中 |
| 2 | **改默认路径**（审计第 5 条）：`scripts/parity/v6_site_catalog.py::--delivery` 默认改为 `artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json`；`grep -rn "s4-launch\|newtask-v6/v6-01\|v6-s3-20260926-01" scripts tests` 逐处改写；重跑 `test_v6_site_labels.py`、`test_v6_site_v11.py` | 零残留、两测试通过 |
| 3 | **下沉 V1′ 运行器**：新建 `scripts/parity/hard_parity.py`（§2.2），从 `artifacts/newtask-v6/v6-s3-20260926-01/run_s3.py` 搬「1 条冒烟 + 143 条、逐局 H5 身份/终态校验、30 分钟无进展/4 小时硬上限、`compare`」逻辑，去掉绝对路径，加 `--env-package {robomme,robomme_hard}` 与 `--base`/`--manifest`/`--official-root`/`--output` 参数（审计第 3 条）；`--dry-run` 只打印命令 | `--dry-run` 输出与 S3 实际命令逐字相同；单测覆盖参数解析与 H5 校验反例 |
| 4 | **生成保留清单**（审计第 4 条）：新建只读脚本 `scripts/parity/legacy_keep_list.py`，输入 ①`docs/validation/**`、`docs/ledger/**`、三份 0925/0926 计划里出现的全部 `artifacts/…` 路径串（实测唯一路径 949 个）②显式验收依赖：`s0/lightweight-baseline.log`、`s0/lightweight-shards/**`（含 `v6-final-identities.txt`）、`s4-launch/verification/*.json`、`s4-launch/recovery/approval.json`、`s4-launch/incident/**`、`v6-s3-20260926-01/{run_s3.py,compare/summary.json,handoff-prep/production-session-*/{outcome,final_verification}.json}`、`audit/*/{审查汇总.md,verify/**,records/**}`、`v6-01/**/final-delivery.json` ③类型白名单 `.md/.json/.jsonl/.txt/.log/.sh/.py`。被引用但 >1 MiB 的非媒体文件也保留并单列；`.h5/.mp4/.png/.jpg/.npy` 一律不搬 | `LEGACY_KEEP=PASS referenced=<n> resolved=<n> missing=0`；`missing` 非零即停交用户 |
| 5 | **归档**：按清单复制到 `docs/validation/<版本>/records/legacy/<原二级目录>/…`（`newtask-v4`→v4、`newtask-v5`→v5、`newtask-v6/*` 与 `audit/*`→v6），写 `MANIFEST.md`（原路径、新路径、字节、sha256）；三份旧计划 `0921/0922/0924-newtask-release-v{3,4,5}-plan.md` `git mv` 到 `docs/plans/` 并改 docstring/测试注释里的链接；`docs/validation/newtask-v2～v5/` 原地保留 | `LEGACY_ARCHIVE=PASS copied=<n> bytes=<b> sha_mismatch=0` |
| 6 | **删跟踪文件**（附录 B 表 A 全部 + 表 B 的跟踪项）：`git rm` 逐路径；`generate_dataset_newseed.py` 一并删，P1 改四入口（`AGENTS.md` P1、`CLAUDE.md` 核实清单计数同步） | `uv run --no-sync python -m pytest --collect-only -q tests/lightweight tests/dataset` 收集错误 0；`ls -1 scripts/*.py` = 4 |
| 7 | **重采 LIGHTWEIGHT 基线**：删后按 V6 §5.3 四片口径跑一次，失败/错误身份写 `artifacts/newtask-v6/hard-split/lightweight-baseline-0b.txt`；阶段 3 的 `LIGHTWEIGHT=PASS new_failures=0` 以它为分母（S0 的 46/12 含已删测试，不再适用） | 四片各 ≤280 s |
| 8 | **删 `artifacts/` 大目录**（单独 commit，body 记 `du`/`df`）：附录 B 表 B 所列目录逐个显式列名，不用 glob；删前 `du -sh` 逐目录、删后 `df -h /data` | 附录 B 表 C 的保留目录一个不少 |

红线：`artifacts/` 删除逐目录显式列名（正本第 14 条）；D 组（他人在途）不读不删；步骤 4、5 未 PASS 不得进入 6、8。

## 一、env make 的接口：外层多传什么、内部多传什么

分两层看：外层是 `scripts/evaluation.py` 里用户写的那个 `BenchmarkEnvBuilder(...)` 调用；内部是 builder 在 `make_env_for_episode` 里拼给 `gym.make` 的 kwargs。

### 1.1 外层：`evaluation.py` 的调用只改一个参数的取值，不加新参数

上游 `evaluation.py` 原样：

```python
env_builder = BenchmarkEnvBuilder(
    env_id=task,
    dataset="test",
    action_space="joint_angle",
    max_steps=1300,
)
```

`evaluation_hard.py` 里对应写法：

```python
env_builder = BenchmarkEnvBuilder(
    env_id=task,
    dataset=tier,            # 唯一变化：取值从 "test" 变成 "xhard1" / "xhard2" / "xhard3" / "xhard4"
    action_space="joint_angle",
    max_steps=1300,
)
```

| 参数 | `evaluation.py` | `evaluation_hard.py` | 说明 |
|---|---|---|---|
| `env_id` | 任务名 | 任务名 | 不变 |
| `dataset` | `"test"` | `"xhard1"`～`"xhard4"` | **唯一变化**。原值域 `{train,test,val}` 扩为七个 |
| `action_space` | `"joint_angle"` | `"joint_angle"` | 不变 |
| `gui_render` | 默认 `False` | 默认 `False` | 不变 |
| `override_metadata_path` | 默认 `None` | 默认 `None` | 不变；xhard 档下若传，解释为「含 `<tier>/specs.jsonl` 的目录」 |
| `max_steps` | `1300` | `1300`（值由用户定，xhard 不受 1301 限制，默认仍传 1300） | 不变 |

**外层不多传任何新参数。** 后面用到的 `get_task_list()`、`get_episode_num()`、`make_env_for_episode(episode)` 三个方法签名与返回类型也不变。新增的只有一个类方法 `get_difficulty_list()`，`evaluation_hard.py` 用它做外层循环；三个无梯度任务（MoveCube / InsertPeg / StopCube）在 xhard1～3 下 `get_episode_num()` 返回 0，循环体自然跳过。

### 1.1.1 最小用法：只改 `dataset` 一个字符串，其余逐字不动（用户 2026-09-27 确认口径）

用户原话：「`dataset="test"` 能否只改这里 改为 xhard1 xhard2 xhard3 xhard4 其他都正常？」答：可以。把 `scripts/evaluation.py` 原样复制，只做两处：

```python
from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder   # ① import 指向新包（旧包不认 xhard，会 ValueError）
...
        dataset="xhard3",          # ② 唯一要改的取值；换 xhard1/2/4 各跑一次即四档
```

循环体、`get_task_list()`、`get_episode_num()`、`make_env_for_episode(episode)`、`reset()`/`step()`、`max_steps=1300`、视频落盘、成功率计算全部原样。各处在 xhard 档下的行为：

| 位置 | 行为 |
|---|---|
| `TASKS = get_task_list()` | 仍 16 任务固定序 |
| `get_episode_num()` | 13 个有梯度任务返回 3；MoveCube / InsertPeg / StopCube 在 xhard1～3 返回 0（`range(0)` 自然跳过，不需加 `if`），xhard4 返回 3 |
| `make_env_for_episode(0/1/2)` | 起该档三条正式规格；候选序号 0/3/6 在 builder 内重编为 0..2 |
| `info["task_goal"]`、`info["status"]`、`obs` 形状 | 与原三档相同 |

因此 `for tier in get_difficulty_list()` 那层外循环只是为了一次跑完四档，**不是必需**；H4「改一行 import 就能用」在这条最小用法下成立。唯一副作用：四档同任务同 episode 的视频文件名相同，分四次跑要各自换输出目录或在文件名里加档名。

### 1.2 内部：builder 按 `dataset` 取值分两条路，拼给 `gym.make` 的 kwargs 多三项

`make_env_for_episode(episode)` 内部最终调 `gym.make(self.env_id, **env_kwargs)`。两条路的 `env_kwargs`：

| kwarg | `dataset="test"`（上游原样，`robomme` 与 `robomme_hard` 相同） | `dataset="xhardN"`（只有 `robomme_hard`） | 值从哪来 |
|---|---|---|---|
| `obs_mode="rgb+depth+segmentation"` | 传 | 传 | builder 写死 |
| `control_mode="pd_joint_pos"` | 传 | 传 | builder 写死 |
| `render_mode="rgb_array"` | 传 | 传 | builder 按 `gui_render` 定 |
| `reward_mode="dense"` | 传 | 传 | builder 写死 |
| `seed` | 传 | 传 | test：包内 `env_metadata/test/record_dataset_<task>_metadata.json` 该 episode 的 `seed`；xhard：包内 `env_metadata/<tier>/specs.jsonl` 该行的 `seed` |
| `difficulty` | 传，`easy/medium/hard` | 传，`xhardN` | 同上两个文件 |
| `sampling_config` | **不传** | **多传**：header 里该任务那一段（16 任务的 decision/native 块） | `specs.jsonl` 的 header |
| `native_episode_spec` | **不传** | **多传**：该行的 `spec`，让 `SpecRecorder` 进回注模式，每个取值点用冻结值、原抽样照常发生只作核验 | `specs.jsonl` 的行 |
| `robomme_failure_recovery` / `robomme_failure_recovery_mode` | **不传** | 条件传：header 的 `recovery_rule` 把该 episode 划进 z 或 xy 段时才传；V6 正式规格 `recovery_rule` 为空，实际**不传** | `specs.jsonl` 的 header |

所以内部多传的就是 `sampling_config`、`native_episode_spec` 两项必传，`robomme_failure_recovery` 一项条件传。`sampling_config` 严格说可以省（不传时环境用类里的 `NATIVE_SAMPLING` 默认值，V6 快照正是从源码导出的同一份），传它是为了让 header 的 `sampling_config_sha256` 校验能挡住「包内源码与分发规格对不上」。

`gym.make` 之后的包装层（`DemonstrationWrapper` 及按 `action_space` 选的 `Endeffector` / `MultiStep` / `OraclePlanner` wrapper）两条路完全相同，模型看到的 `obs` / `info["task_goal"]` / `step()` 五元组形状一致。

### 1.3 builder 内部要改的三处

| 锚点 | 现状 | 改成 |
|---|---|---|
| `episode_config_resolver.py::_ALLOWED_DATASETS` | `{"train","test","val"}` | 并入 `NEWVALUE_DIFFICULTIES` 四档 |
| `BenchmarkEnvBuilder.__init__` | 只走 `_resolve_metadata_path` → `load_episode_metadata` | `dataset` 是 xhard 值时改走 `hard_specs.load_specs(包内 env_metadata/<tier>/specs.jsonl)`，把 header 该任务段与行装进 `self._hard`（即现 `from_v4_specs` 装 `self._v4` 的那套结构） |
| `BenchmarkEnvBuilder.get_difficulty_list` | 不存在 | 新增类方法，返回四档列表 |

`resolve_episode` / `get_episode_num` / `make_env_for_episode` 现在已经有 `self._v4` 分支（`from_v4_specs` 路径在用），只需把 `_v4` 改名 `_hard` 并让 `__init__` 也能填它；`from_v4_specs` 保留为薄包装以免打断现有 `scripts/eval/v4_eval.py`。episode 编号：xhard 行的候选序号是 0/3/6，builder 内存里重编为 0..2 让 `for episode in range(episode_count)` 循环体不改，原候选序号放 `info["hard_candidate_index"]`；规格行与 `identity_sha256` 不动。

## 二、文件级清单：`src/robomme_hard` 从哪来、哪些不动、哪些要加

`src/robomme_hard/` = 当前 `src/robomme/` 整包复制（D-2 已推荐 copy）。下面按「相对上游 `main` 是否相同」分四组；「继承」指从当前 `src/robomme` 原样复制进 `robomme_hard` 后一个字不改。

### 2.1 原样继承（与上游逐字节相同，28 个 .py + 44 个 json）

| 位置 | 文件 | 备注 |
|---|---|---|
| 包顶层 | `__init__.py`、`logging_utils.py` | — |
| `robomme_env/` | `__init__.py` | 16 个 `@register_env` 的登记处 |
| `env_record_wrapper/` | `__init__.py`、`DemonstrationWrapper.py`、`EndeffectorDemonstrationWrapper.py`、`MultiStepDemonstrationWrapper.py`、`FailAwareWrapper.py`、`episode_dataset_resolver.py` | — |
| `env_record_wrapper/` | `OraclePlannerDemonstrationWrapper.py` | ⚠ 内容同上游，但含 `from robomme.…` 绝对 import，复制后须改包名 |
| `robomme_env/utils/` | `__init__.py`、`adjacent.py`、`choice_action_mapping.py`、`constant.py`、`obschange.py`、`oracle_action_matcher.py`、`planner_denseStep.py`、`planner_fail_safe.py`、`planner-ref.py`、`reset_panda.py`、`rpy_util.py`、`save_reset_video.py`、`SceneGenerationError.py`、`statechange.py`、`task4recovery.py` | — |
| `robomme_env/utils/` | `generate_sample_action.py`、`subgoal_evaluate_func.py`、`vqa_options copy.py` | ⚠ 同上，含绝对 import，复制后须改包名 |
| `env_metadata/` | `test/` 16 份、`val/` 16 份、`train/` 12 份 | 原三档身份 |

### 2.2 已被 V3～V6 改过（与上游不同，26 个 .py + 4 个 json）——复制进 `robomme_hard`，`robomme` 侧回上游

| 位置 | 文件 | 改动规模（相对上游） | 复制后还要做什么 |
|---|---|---|---|
| `robomme_env/` | 16 个环境文件 `BinFill.py` … `VideoUnmaskSwap.py` | 每个 +200～+1100 行：`sampling_config` / `episode_spec` 接入、xhard 分支 | 不改 |
| `env_record_wrapper/` | `RecordWrapper.py` | +7 行：`fail_safe_limit` 2000→5000（V4 用户授权的唯一解冻） | 改绝对 import |
| `env_record_wrapper/` | `episode_config_resolver.py` | +79 行：`from_v4_specs` / `v4_episodes` / `_v4_kwargs` | **要加东西**：`_ALLOWED_DATASETS` 并入四档、`__init__` 的 `dataset` 分支读包内规格、`get_difficulty_list()`（§一） |
| `robomme_env/utils/` | `difficulty.py`、`object_generation.py`、`route.py`、`segmentation_utils.py`、`subgoal_language.py`、`task_goal.py` | 各 +20～+340 行 | 不改 |
| `robomme_env/utils/` | `subgoal_planner_func.py`、`vqa_options.py` | +104 / +21 行 | 改绝对 import |
| `env_metadata/train/` | `ButtonUnmask`、`ButtonUnmaskSwap`、`VideoUnmask`、`VideoUnmaskSwap` 四份 | 100 条→400 条 | 留在 `robomme_hard`（D-3） |

### 2.3 fork 新增（上游没有，9 个 .py）——复制进 `robomme_hard`，`robomme` 侧删除

`robomme_env/utils/`：`bin_collision.py`、`episode_spec.py`、`sampling_config.py`、`swap_uniform.py`、`unmask_distractor_sampler.py`、`unmask_distractors.py`、`unmask_swap_xhard.py`、`xhard.py`、`xhard_home_site.py`。复制后不改。

### 2.4 `robomme_hard` 相对当前 `src/robomme` 还要**新增**的（5 项）

| 文件 | 内容 | 来源 |
|---|---|---|
| `__init__.py`（改写） | 同进程已 import `robomme.robomme_env` 时 `raise ImportError`（ManiSkill 注册表按 env_id 唯一，两包不能共存） | 新写 |
| `env_record_wrapper/hard_specs.py` | `load_specs()` 及其纯函数依赖（`canonical_json`、`digest`、`identity_sha256`、`seed_rule_for`、`HEADER_KEYS`） | 从 `scripts/parity/v4_specs.py` 下沉只读部分；`draw`/`freeze` 不搬 |
| `env_metadata/xhard{1,2,3,4}/specs.jsonl` | 四档冻结规格 | `cp scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl`（现行 v6-02，非方案初稿的 v6-01） |
| `README.md` | 四档定义、改动清单、用法 | 新写，改动清单由 `scripts/parity/hard_pkg_manifest.py` 生成 |
| `pyproject.toml` | `packages = ["src/robomme", "src/robomme_hard"]` | 一行 |

绝对 import 共 7 个文件要改（2.1 的 4 个 + 2.2 的 3 个）：`from robomme.` → `from robomme_hard.`，或改相对 import。这是拆包时唯一容易漏的洞，漏一处就静默回头用旧包。

## 三、三个脚本阶段：env make 怎么传

三阶段的入口都在 `scripts/`，每阶段一句话说它调不调 `gym.make`、传什么。

```
阶段 1  生成 json    train_split_config.py extract --release newtask-v6
        ──▶ scripts/configs/newtask-v6/sampling_config.json        （不起环境）
阶段 2  生成规格与轨迹
   2a   v4_specs draw --difficulty <tier> --seed-profile v6           gym.make + reset，只抽签不 step
        ──▶ drafts.jsonl
   2b   v4_specs freeze                                              纯 CPU，不起环境
        ──▶ scripts/configs/newtask-v6/<run>/<tier>/specs.jsonl
   2c   v4_rollout run --specs <tier>/specs.jsonl                    gym.make + RecordWrapper + planner
        ──▶ h5 / mp4
阶段 3  评估          evaluation_hard.py（或现有 scripts/eval/v4_eval.py）  BenchmarkEnvBuilder → gym.make
```

| 阶段 | 入口 | 起环境的代码位置 | `gym.make` 收到的 kwargs | 拆包后要改的 |
|---|---|---|---|---|
| 1 生成 json | `scripts/parity/train_split_config.py::extract_task` | **不调 `gym.make`**。`importlib.import_module("robomme.robomme_env.<Task>")` 读类属性 `NATIVE_SAMPLING` / decision 块，写成 json | 无 | import 串改 `robomme_hard` |
| 2a 抽签 | `scripts/parity/v4_specs.py::_draw_one` | `gym.make(task, sampling_config=<json 该任务段>, **env_kwargs(seed, episode, difficulty))` → `env.reset()` → `env.unwrapped._spec.to_dict()` 导出规格 | 四项 runtime + `seed` + `difficulty=xhardN` + `sampling_config`（+ recovery，V6 为空） | `from robomme.` → `robomme_hard` |
| 2b 冻结 | `scripts/parity/v4_specs.py::cmd_freeze` | 不起环境；校验 header 与源码指纹后写 `specs.jsonl` | 无 | `load_specs` 改为薄包装调 `robomme_hard.…hard_specs.load_specs` |
| 2c 实跑 | `scripts/parity/v4_rollout.py` → `train_split_worker.py::run_one` | `gym.make(job.task, **kwargs)` 再套 `RobommeRecordWrapper` 与 planner | 四项 runtime + `seed` + `difficulty` + `sampling_config` + `native_episode_spec`（+ recovery） | import 改包名 |
| 3 评估（现状） | `scripts/eval/v4_eval.py` | `load_specs` → `BenchmarkEnvBuilder.from_v4_specs(task, header, rows)` → `make_env_for_episode(ep)` | 与 2c 相同（builder 内 `_v4_kwargs` 拼出） | import 改包名；`from_v4_specs` 保留为薄包装 |
| 3 评估（方案后） | `scripts/evaluation_hard.py` | `BenchmarkEnvBuilder(env_id=task, dataset="xhardN")` → `make_env_for_episode(ep)`，builder 自己读包内 `specs.jsonl` | 与 2c 相同 | 新增文件（与 `evaluation.py` diff ≤ 12 行，见第二部分 §5.4） |

三点结论：

1. **2a、2c、3 传进 `gym.make` 的 kwargs 集合是同一套**，差别只在 2a 没有 `native_episode_spec`（它正是要导出这个），2c/3 有。这就是回注能逐位复现的原因：抽签时导出的规格，实跑和评估原样喂回去。
2. **阶段 1 和 2b 不起环境**，只 import 包读属性或算散列，所以对 `robomme_hard` 的依赖只是 import 串。
3. **阶段 3 现状与方案后的唯一区别是「谁读 `specs.jsonl`」**：现在是脚本读了再喂 builder（`from_v4_specs`），方案后 builder 按 `dataset` 档名自己读包内规格。合作者拿到包后只需要 `dataset="xhard3"`，不需要知道 `scripts/parity` 存在。

原三档在 `robomme_hard` 下走的是与上游相同的 metadata 路径（`dataset="test"`），kwargs 只有四项 runtime + `seed` + `difficulty`，与 `robomme` 逐字相同；这条路的逐位一致由第二部分 §2.2 的 V1′ 对拍保证。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

- R1 **（2026-09-27 改写）S3 与审查修复 G1 均已通过，D-4 满足；`src/robomme/` 的整体回退仍只在阶段 5、且排在 V1′ PASS 之后**；阶段 0～4 只新增文件或改 `scripts/`、`tests/`、`pyproject.toml`，阶段 0b 的删除按附录 B 勾选清单。
- R2 `src/robomme/` 的目标字节 = 上游 `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`；取法只允许 `git fetch https://github.com/RoboMME/robomme_benchmark.git main` 后 `git checkout FETCH_HEAD -- src/robomme`（不合并、不 rebase）。
- R3 `robomme_hard` 内零 `robomme.` 绝对 import；两包同进程互斥由 `robomme_hard/__init__.py` 负责，`robomme` 不改。
- R4 `specs.jsonl` 行内容与 `identity_sha256` 不动；builder 侧 episode 重编号只在内存。
- R5 三脚本 `evaluation.py` / `run_example.py` / `dataset_replay.py` 继续逐字节同上游；`evaluation_hard.py` 只允许 §5.4 的 diff。
- R6 V1′ 144 次轨迹尝试是本方案唯一的生成预算（P3：单 worker >10 须授权，阶段 1 一次列齐）；不加 reset 对拍、不加 rollout。
- R7 commit 只 add 本阶段文件。**当前在途改动（2026-09-27，属其他会话）一律不碰、不读、不删**：`M scripts/parity/v6_site.html`、`M scripts/parity/v6_site.py`、`?? logs/`、`?? scripts/configs/newtask-v6/smvla-smoke-0927/`、`?? scripts/parity/v6_gt_lengths.{py,json}`；以及 `artifacts/newtask-v6/smvla-0927{,-more,-fill,-smoke}`（约 2 TB，`logs/gen-*.sh` 的产物，账本无记录）与 tmux 会话 `smvla-site-8060`、`corlvis-site`。实施时以当时 `git status --short` 为准重列。
- R8 长期文档禁行号引用；本文件锚点全部用 `文件::符号`。

## 一、逐文件改动清单

### 1.1 `src/robomme_hard/`（阶段 2）

| 文件 | 锚点 | 改动 |
|---|---|---|
| `__init__.py` | 模块顶部 | `import sys; if "robomme.robomme_env" in sys.modules: raise ImportError(...)`；其余空 |
| `robomme_env/utils/subgoal_planner_func.py` | 顶部 `from robomme.robomme_env import *`、`from robomme.robomme_env.utils import *` | 改 `from robomme_hard…`（保持星号，不改语义） |
| `robomme_env/utils/subgoal_evaluate_func.py` | `from robomme.robomme_env.utils import *` | 同上 |
| `robomme_env/utils/vqa_options.py`、`vqa_options copy.py` | `from robomme.robomme_env.utils.subgoal_planner_func import (` | 同上（`copy.py` 是上游遗留死文件，随包复制、不删） |
| `robomme_env/utils/generate_sample_action.py` | 函数内 `from robomme.robomme_env.utils.rpy_util import …` | 同上 |
| `env_record_wrapper/OraclePlannerDemonstrationWrapper.py` | `from robomme.robomme_env.utils.vqa_options import get_vqa_options` | 改相对 `from ..robomme_env.utils.vqa_options import …` |
| `env_record_wrapper/RecordWrapper.py` | `_write_h5` 内局部 `from robomme.robomme_env.utils.vqa_options import get_vqa_options` | 同上；`fail_safe_limit = 5000` 保留 |
| `env_record_wrapper/episode_config_resolver.py` | `BenchmarkEnvBuilder.__init__`、`_ALLOWED_DATASETS`、`_resolve_metadata_path`、`resolve_episode`、`get_episode_num`、`make_env_for_episode`、`from_v4_specs`、`v4_episodes`、`_v4_kwargs` | 按 §5.2：`_v4` 改名 `_hard`；`_ALLOWED_DATASETS` 并入四档；新增 `_resolve_specs_path()`、`get_difficulty_list()`、`hard_episodes()`；`from_v4_specs` 保留为包装 |
| `env_record_wrapper/hard_specs.py` | 新 | 从 `scripts/parity/v4_specs.py` 搬 `HEADER_KEYS`、`canonical_json`、`digest`、`identity_sha256`、`seed_rule_for`、`_known_seed_rule`、`load_specs`；`source_fingerprint` 不符改 `warnings.warn` |
| `env_record_wrapper/__init__.py` | 导出表 | 增 `hard_specs` |
| `env_metadata/xhard{1..4}/specs.jsonl` | 新 | `cp scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl`（现行 v6-02，2026-09-27 更正）；打包前按 §2.3 重算 `source_fingerprint` |
| `README.md` | 新 | §5.5 |

### 1.2 `scripts/`、`tests/`（阶段 3）

- 机械替换：`grep -rl "from robomme\.\|import robomme\b" scripts tests --include=*.py`（实测 14 + 45 文件）→ `robomme_hard`；**排除** `scripts/evaluation.py`、`run_example.py`、`dataset_replay.py`。
- `scripts/parity/v4_specs.py::load_specs` 改为 `from robomme_hard.env_record_wrapper.hard_specs import load_specs as _load; def load_specs(path): return _load(path)`；`draw`/`freeze` 不动。
- `scripts/parity/hard_pkg_manifest.py`（新，只读）：对 `src/robomme` 与 `src/robomme_hard` 逐文件 `sha256`/行数 diff，输出 Markdown 表 + `HARD_MANIFEST=PASS same=<n> diff=<m> new=<k>`。
- `scripts/evaluation_hard.py`：§5.4。
- `tests/lightweight/test_hard_pkg_isolation.py`（新）：AST 扫描零绝对引用；子进程验证双导入 `ImportError`；`specs.jsonl` 身份相等；`evaluation_hard.py` diff 行数 ≤ 12。

### 1.3 `src/robomme/`（阶段 5，P2）

```bash
git fetch https://github.com/RoboMME/robomme_benchmark.git main          # 只写 .git/FETCH_HEAD
git rev-parse FETCH_HEAD                                                  # 期望 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9
git rm -q src/robomme/robomme_env/utils/{bin_collision,episode_spec,sampling_config,swap_uniform,unmask_distractor_sampler,unmask_distractors,unmask_swap_xhard,xhard,xhard_home_site}.py
git checkout FETCH_HEAD -- src/robomme
git diff --stat FETCH_HEAD HEAD -- src/robomme | tail -1                  # 期望空 → UPSTREAM_BYTES=PASS
```

`pyproject.toml` 的 `pebble` 行保留（生成链路要用），只改 `packages`。

## 二、对拍闸门总表与 runbook

### 2.1 上游快照

```bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
git fetch https://github.com/RoboMME/robomme_benchmark.git main && git rev-parse FETCH_HEAD
git diff --stat FETCH_HEAD HEAD -- src/robomme scripts/evaluation.py scripts/run_example.py scripts/dataset_replay.py pyproject.toml
```

2026-09-26 现状（scratchpad 浅克隆 `cmp` 实测）：`same=31 diff=26 new=9`，`env_metadata` 4 份 train 不同，`pyproject.toml` 差 `pebble` 一行，三脚本相同。

### 2.2 V1′（阶段 4）——由新入口 `scripts/parity/hard_parity.py` 承担

用户 2026-09-27 原话：「robomme_hard 重跑 144 局与 S0 基线比 sha 这个是要保留的！并且需要wrap up成新的 …/scripts/parity负责对拍」。

- **来源**：`artifacts/newtask-v6/v6-s3-20260926-01/run_s3.py`（225 行）的逻辑下沉——①先 1 条冒烟（`BinFill/0`）再剩余 143 条，失败不补跑；②逐局 H5 校验：身份目录集合、文件名 `<task>_ep<ep>_seed<seed>.h5`、`setup/seed`、`setup/difficulty`、timestep 连续、末帧 `info/is_completed` 严格 `True`；③子进程独立进程组，30 分钟无日志/文件进展或 4 小时硬上限即停；④调 `train_split_parity.py compare` 出 `h5_pairs.jsonl` 与 `summary.json`。**不新增任何抽样或 reset**。
- **CLI**：`uv run --no-sync python -m scripts.parity.hard_parity run --env-package robomme_hard --manifest scripts/configs/newtask-v3/subset_manifest.json --base artifacts/newtask-v6/v1/base --official-root artifacts/train-parity/local-smoke-01/official-src --output artifacts/newtask-v6/v1-hard --workers 1 --gpus 0`；`--env-package` 决定子进程里 `train_split_worker` import 的包名（通过环境变量 `ROBOMME_ENV_PACKAGE` 传入 worker，worker 侧按该变量选择 import；这是阶段 3 切换调用方时对 `train_split_worker.py` 的唯一非机械改动）；`--dry-run` 只打印将执行的命令。
- **判定行**：`NATIVE_REGRESSION_HARD=PASS compared=144 sha_equal=144 field_mismatch=0 env_package=robomme_hard base=<sha256 of run_config>`；H5 校验行 `HARD_H5_SEMANTICS=PASS side=hard identities=144 terminal_success=144 timesteps=<n>`。
- **运行方式**：tmux 会话 `hard-v1-<日期>`，日志 `artifacts/newtask-v6/v1-hard/run.log`（`PYTHONUNBUFFERED=1`、`pipefail`、`tee`、`EXIT_CODE=` 尾行），Monitor 一次性 `until` 等待 `EXIT_CODE=`（用户 2026-09-27 口径：不设逐条进度过滤器）。预算 144 次轨迹尝试，阶段 1 与 D-1～D-3 一并申请。
- **FAIL 时的归因**：S3 跑在 `ca32e9b` 之前，V1′ 若 FAIL 要先分清是拆包引入还是审查修复引入——办法是同一入口 `--env-package robomme` 再跑一侧，预算须另批，不自动执行。
- **单测**（`tests/lightweight/test_hard_parity.py`）：参数解析、`--dry-run` 命令逐字、H5 校验对「身份缺失／难度错／末帧未完成／空文件」四类反例必拒。

### 2.3 `specs.jsonl` 指纹重算（阶段 2 末）

`hard_specs.py` 提供 `refingerprint(path, src_root)`：只重算 header `source_fingerprint`（按 `v4_specs.source_fingerprint` 同一算法对 `src/robomme_hard` 计算）并**把旧值写进 `source_fingerprint_origin`**，`identity_sha256` 因不含指纹字段而不变（`HEADER_KEYS` 里 `source_fingerprint` 属管理字段，需在 `identity_sha256` 剔除集里核对；若现实现把它算进身份，则改为不重算、只警告——以 `identity_sha256(new_header, rows) == header["identity_sha256"]` 为准）。

### 2.4 冒烟

```bash
HARD_EVAL_LIMIT=1 uv run --no-sync python scripts/evaluation_hard.py   # 临时 env 只在冒烟用；脚本本身不读它（保持与 evaluation.py 的 diff 上限）→ 冒烟改用 python -c 调 builder 单局
uv run --no-sync python -c "from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder as B; b=B('BinFill','xhard1',max_steps=50); print(b.get_episode_num()); e=b.make_env_for_episode(0); o,i=e.reset(); print(i['task_goal'][0]); e.close()"
```

## 三、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | 8 处绝对 import 漏改一处 → `robomme_hard` 静默用旧 utils | `IMPORT_ISOLATED` AST 判定 + 双导入互斥让漏改立刻 `ImportError` |
| 2 | 两包同进程（如 pytest 一个 session 收集两边测试） | 互斥守卫 fail-loud；tests 全部切到 `robomme_hard`，`robomme` 只由三个上游脚本导入 |
| 3 | `source_fingerprint` 校验在用户机器上必不符 | §2.3 重算并保留原值；`load_specs` 对指纹只警告 |
| 4 | S3 期间误改 `src/robomme` 让 S3 后半段跑另一份代码 | R1；阶段 5 排在 S3 结论之后 |
| 5 | `env_metadata/train` 400 条扩展丢失 | D-3：搬到 `robomme_hard/env_metadata/train/`，README 注明 |
| 6 | 上游 `main` 在合并前又前进 | `UPSTREAM_BYTES` 判定行记 FETCH_HEAD sha；合并 PR 时以当时 sha 重跑一次 |
| 7 | `get_episode_num()` 对 xhard 档三个无梯度任务返回 0 让 `evaluation_hard.py` 的 `sum/len` 分母不变 | 分母只数实际跑过的局，与上游逻辑一致 |

## 四、盲区诚实清单

- 上游 `main` 与本 fork 分叉后的上游自身改动（`1fadc0e` 之前上游是否改过 `src/robomme`）未逐 commit 核对，只做了字节比对；如上游后续再改，`robomme_hard` 的原三档不会跟着变。
- V1′ 只证明原三档；四档在两个包名下是否逐位相同**没有对拍**（V6 口径 7：xhard 不对拍），本方案沿用。
- `hard_specs.load_specs` 下沉后 `identity_sha256` 是否含指纹字段，需实施时读 `v4_specs.identity_sha256` 确认（§2.3 两条分支）。
- `dataset_replay.py` 对 hard 演示 h5 是否可直接回放未验证，不在本方案范围。
- 4 份 train 元数据扩展（`052841a`）的下游消费者（`scripts/injection/`）在切到 `robomme_hard` 后路径是否仍指向包内 `env_metadata`，阶段 3 用 `LIGHTWEIGHT` 兜底，未单独核。

## 五、留档与 commit 纪律

- 每阶段一份 `docs/validation/newtask-v6/<日期>-hard-split-<阶段>.md`，判定行内联原文；`records/` 只放 git 还原不出的东西（V1′ 的 `h5_pairs.jsonl`、`run.log` 清洗版）。
- commit 只 add 本阶段文件，subject 接 `12.<n>`；阶段 5 的 `src/robomme` 回退单独一个 commit，body 写 `FETCH_HEAD` sha 与 `UPSTREAM_BYTES` 判定行。
- 本文件按正本第 2 条命名 `0926-robomme-hard-split-plan.md`；后续修订不改日期前缀。

## 附录 A、原第一部分（2026-09-26 初稿，内容未改，仅标题降一级）

> 勘误注（2026-09-27）：本附录 §二口径 4、§六 SPECS_IDENTITY 行、§七阶段表所写 `v6-01` 均应读作 `v6-02`；§四 D-4 已满足；§六 V1′ 行「复用 S3 运行器 `run_s3.py`」改为新入口 `scripts/parity/hard_parity.py`（第二部分 §2.2）；阶段表在阶段 0 与 1 之间新增阶段 0b（第一部分 §0.3），阶段 4 的判定行改为 `NATIVE_REGRESSION_HARD=…`。附录正文按「内容未改」原则不动。


### 一、用户与合作者的原话（逐字）

| # | 原话 | 落成口径 |
|---|---|---|
| Q1 | 「新的 robomme hard 的话最好这样 直接加个 src/robomme_hard/* scripts 里面加一个 scripts/evaluation_hard.py 这样应该不影响旧的，同时能最后都放到同一个分支上」 | 目标形态：两个并列包 + 一个并列评估入口，同一分支交付 |
| Q2 | 「src/robomme_hard/ 不影响 src/robomme/ 是独立的 / 你现在的做法是直接 改了 src/robomme/」 | 现状确认：本仓库 16 个环境文件、2 个 wrapper、7 个 utils 都改在 `src/robomme/` 里（§三实测表） |
| Q3 | 「我做了对比的机制 会有新的src/robomme_hard/ 而且传入同样参数也能生成 src/robomme/的内容」 | 硬要求 H1：`robomme_hard` 在原三档参数下产出与 `robomme` **逐位相同**（即 V1 对拍的保证要在新包名下继续成立） |
| Q4 | 「就如果说有的task 机制一样的话 robomme_hard 里面的文件会调用 robomme 里面的文件」「task本身的文件 目前全部都有改动 但是utils可能会继承一些」「全部都改动了的话，那就直接 copy 到 src/robomme_hard 里面」 | 复用方式待定：copy 还是引用（§四 D-2 给出推荐） |
| Q5 | 「src/robomme_hard/ 是新的 src/robomme 是旧的 两者互不干扰，然后在 src/robomme_hard/readme 里面说清楚改动在哪，hard 在哪」 | 硬要求 H2：`src/robomme/` = 上游原样；硬要求 H3：`src/robomme_hard/README.md` 写清改动与 hard 定义 |
| Q6 | 「两者的接口应该基本保持一致 比如 …/scripts/evaluation.py 可能只需要改 from robomme.env_record_wrapper import BenchmarkEnvBuilder 成 from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder」 | 硬要求 H4：`BenchmarkEnvBuilder` 公开签名不变，`evaluation_hard.py` 与 `evaluation.py` 只差 import 行与难度循环 |
| 用户 | 「现在已经基本完成了 除了对拍 / 现在的整个逻辑链条是什么 / 能否实现以下对话的内容 / 给出重构接口的方案 / 落到根目录md」 | 本文件 |

### 二、一句话结论与已定死口径

**能实现，而且比现状更干净**：本仓库现在把「上游原三档」和「V6 新四档」揉在同一个 `src/robomme/` 里，靠 `difficulty` 字符串族判断分叉；拆成两个包后，`src/robomme/` 直接回到上游 `main` 的字节，全部 V3～V6 改动（含录像器 `fail_safe_limit` 2000→5000 这个「被迫解冻」项）整体搬进 `src/robomme_hard/`，`BenchmarkEnvBuilder` 只在 `dataset` 参数上多认四个值 `xhard1`～`xhard4`，`scripts/evaluation_hard.py` 与上游 `evaluation.py` 的 diff 控制在两处。

已定死口径（依据小节）：

1. **`src/robomme/` 逐字节等于上游 `main` @ `1fadc0e`**（§三）——不是「等于 V1 基线 `13e5151`」。两者不同：本 fork 的 `src/robomme` 从未与上游字节相同（§三表：26 文件不同、9 文件新增、4 份 train 元数据从 100 条扩到 400 条）。
2. **`src/robomme_hard/` = 当前 `src/robomme/` 的整包复制 + 包名改写**，不做「部分引用 `robomme`」（§四 D-2，推荐 copy；理由是 ManiSkill 注册表冲突与 `utils/__init__.py` 星号导入把「逐字节相同的文件」也拖进依赖链）。
3. **公开接口不变**：`BenchmarkEnvBuilder(env_id, dataset, action_space, gui_render, override_metadata_path, max_steps)`、`get_task_list()`、`get_episode_num()`、`make_env_for_episode(...)` 签名与语义全部保留；新增只有 `dataset ∈ {"xhard1","xhard2","xhard3","xhard4"}` 与类方法 `get_difficulty_list()`（§五）。
4. **四档规格随包分发**：`scripts/configs/newtask-v6/v6-01/<tier>/specs.jsonl`（实测 256 K / 276 K / 296 K / 360 K）复制为包数据 `src/robomme_hard/env_metadata/<tier>/specs.jsonl`，`load_specs` 的封套校验从 `scripts/parity/v4_specs.py` 下沉到 `src/robomme_hard/env_record_wrapper/hard_specs.py`（src 不反向依赖 scripts 的红线不变）（§五）。
5. **原三档在 `robomme_hard` 下必须与 `robomme` 逐位相同（H1）**：验收不是新跑对拍，而是把 S3 正在跑的 V1 对拍换成「`robomme_hard` 侧 vs S0 基线」重跑 144 局（§六 V1′）；**在 S3 出结果前不动 `src/robomme/`**（S3 启动锚点 `c8c06ab` 读的是主仓活树）。
6. **V6 计划里的「冻结」项全部自然落位**：录像器在 `robomme` 回 2000 步（上游原样），在 `robomme_hard` 保持 5000；`scripts/evaluation.py` / `run_example.py` / `dataset_replay.py` 继续与上游逐字节相同；`scripts/` 顶层从五入口变六入口需用户按 P1 放行（§四 D-1）。
7. **最小用法（2026-09-27 用户确认）**：复制 `evaluation.py`，只改 import 行与 `dataset` 取值，其余逐字不动即可跑单档（第一部分 §1.1.1）。
8. **不在本方案内**：hard 演示数据（165 局）的 HF 发布、`dataset_replay.py` 的 hard 版本、网站；V6 计划 S3/S5 照旧按 `0925-newtask-release-v6-plan.md` 收尾。

### 三、现在的整个逻辑链条（回答「逻辑链条是什么」）

以下按「数据怎么来、代码怎么分叉、评估怎么进」三层写，每层给锚点。

#### 3.1 代码层：一个包、两条路径，靠难度字符串分叉

```
src/robomme/robomme_env/<Task>.py::__init__
   ├─ _resolve_sampling_config(cls, sampling_config)      # utils/sampling_config.py：拆 decision/native、assert_native_decision、fill_missing_newvalue
   ├─ SpecRecorder(native_episode_spec, task, {"seed"}, difficulty)   # utils/episode_spec.py：导出(spec=None)/回注(传冻结规格)
   ├─ normalize_robomme_difficulty(kwargs.pop("difficulty"))          # utils/difficulty.py：VALID = 原三档 ∪ {xhard1..4}
   └─ 之后每个取值点：
        if is_newvalue_difficulty(self.difficulty):  → 走 xhard 机制（utils/xhard.py 精确 OBB、unmask_swap_xhard.py、swap_uniform.py S5/O4、xhard_home_site.py …）
        else:                                        → 原三档路径（红线 N1：不新增、不挪动任何随机抽样）
```

- 原三档的「不变」不是靠字节不变保证，而是靠 **V1 对拍**：`scripts/parity/train_split_parity.py` 用官方隔离源码树 `artifacts/train-parity/local-smoke-01/official-src/`（`.official_tree` 标记 `1d4c1369…`）跑 S0 基线 144 局，再用主仓代码跑同 seed 144 局，逐局 h5 sha 相等 → `NATIVE_REGRESSION=PASS compared=144 sha_equal=144`。这就是用户说的「除了对拍」：S3 正在跑（tmux `v6-s3-20260926-01`，报告 `docs/validation/newtask-v6/20260926-s3.md` 现状 `NATIVE_REGRESSION=PENDING`，已闭合 23/144 身份前缀 sha 一致）。
- 与上游 `main` 的真实差异（2026-09-26 浅克隆逐文件 `cmp` 实测，`src/robomme` 不含 `env_metadata`）：

| 类别 | 文件 | 说明 |
|---|---|---|
| 逐字节相同 | 31 个（`__init__.py` ×3、`logging_utils.py`、5 个 wrapper、`utils/` 下 22 个） | 可原样保留 |
| 不同：16 个环境 | `BinFill.py` 495→1120 行 … `VideoRepick.py` 657→1621 行（全部 16 个） | 每个都加了 `sampling_config`/`episode_spec`/xhard 分支 |
| 不同：wrapper | `RecordWrapper.py`（+3 行：`fail_safe_limit` 2000→5000）、`episode_config_resolver.py`（+79 行：`from_v4_specs`/`v4_episodes`/`_v4_kwargs`） | 前者是 V4 用户明确授权的唯一解冻 |
| 不同：utils | `difficulty.py`、`object_generation.py`、`route.py`（`walk_config`）、`subgoal_language.py`、`subgoal_planner_func.py`、`task_goal.py`、`vqa_options.py` | `route.py` 的改动来自 10.8（2026-09-09），早于 V3 |
| fork 新增 utils | `bin_collision.py`、`episode_spec.py`、`sampling_config.py`、`swap_uniform.py`、`unmask_distractor_sampler.py`、`unmask_distractors.py`、`unmask_swap_xhard.py`、`xhard.py`、`xhard_home_site.py` | 9 个 |
| 元数据 | `env_metadata/train/record_dataset_{VideoUnmask,VideoUnmaskSwap,ButtonUnmask,ButtonUnmaskSwap}_metadata.json` | fork 把四个 Unmask 系 train 集从 100 条扩到 400 条（2.8.1，`052841a`）；`test`/`val` 与上游相同 |
| `pyproject.toml` | 多一行 `pebble>=5.2.2` | 生成链路依赖 |

- 包内 **绝对 import** 8 处（`subgoal_planner_func.py`、`subgoal_evaluate_func.py`、`vqa_options.py`、`generate_sample_action.py`、`OraclePlannerDemonstrationWrapper.py`、`RecordWrapper.py` 等写的是 `from robomme.robomme_env…`），复制成 `robomme_hard` 后若不改写，会静默回头去 import 旧包——这是拆包时第一个要堵的洞（§六 IMPORT_ISOLATED）。

#### 3.2 数据层：四档「规格」是身份，不是 seed

```
源码申报 ──train_split_config extract --release newtask-v6──▶ scripts/configs/newtask-v6/sampling_config.json（88 K，含 16 任务 decision/native）
   └─▶ v4_specs draw --difficulty <tier> --seed-profile v6   （seed 偏移 xhard4 6e6 / xhard1 8e6 / xhard2 10e6 / xhard3 12e6；只 reset 不 step）
        └─▶ freeze ──▶ scripts/configs/newtask-v6/v6-01/<tier>/specs.jsonl（header：sampling_config 全文、源码指纹、runtime 四项、seed_rule、identity_sha256；行：selected=0/3/6 的候选规格）
              └─▶ v4_rollout run（GL）──▶ 165 局正式 h5/视频（artifacts/newtask-v6/v6-01/<tier>/…，待 S3 接纳）
```

评估侧起环境时**不再抽签**：`BenchmarkEnvBuilder.from_v4_specs(env_id, header, specs_by_identity)` 把 `seed / difficulty / sampling_config / native_episode_spec` 从 `specs.jsonl` 行里取出传给 `gym.make`，`SpecRecorder` 进入回注模式，每个取值点用冻结值、原抽样照常发生只作核验（`scripts/eval/v4_eval.py::_binding` 读 `env.unwrapped._spec` 报 `mismatch/unused`）。这条路径目前只有 `scripts/eval/v4_eval.py` 在用，且 `load_specs` 住在 `scripts/parity/v4_specs.py`——**src 不能反向依赖 scripts**，所以现在没有任何 `src` 内的公开入口能按档名直接起 xhard 环境。这是拆包时接口要补的唯一一块。

#### 3.3 评估层：上游只认 `dataset="test"` 的 metadata

上游 `scripts/evaluation.py`：`BenchmarkEnvBuilder(env_id=task, dataset="test", action_space="joint_angle", max_steps=1300)` → `_resolve_metadata_path` 读包内 `env_metadata/test/record_dataset_<task>_metadata.json`（每条 `seed/difficulty/episode`）→ `gym.make(env_id, seed=…, difficulty=…)`。`dataset` 只允许 `{train,test,val}`（`_ALLOWED_DATASETS`）。四档评估目前只能走 `python -m scripts.eval.v4_eval --specs …`，与上游入口不是同一个形状。

### 四、待用户裁决的四项（未裁决不开工）

| # | 问题 | 推荐 | 不选推荐的代价 |
|---|---|---|---|
| D-1 | `scripts/evaluation_hard.py` 触碰 P1「顶层只许五入口」 | **放行第六入口**，P1 清单改为六项并写明与 `evaluation.py` 的 diff 上限（两处） | 退而放 `scripts/eval/evaluation_hard.py`，但合作者要的「改一行 import 就能用」体验变差 |
| D-2 | `robomme_hard` 对 31 个逐字节相同文件是 copy 还是 `from robomme… import *` 引用 | **整包 copy，零跨包 import**（§五 5.1 给三个硬理由） | 引用会让 `robomme_hard` 强依赖 `robomme`，且两包同进程各自 `register_env("BinFill")` 必撞（ManiSkill `register_env` 对重复 id 默认 `raise RuntimeError`） |
| D-3 | 四个 Unmask 系 train 元数据 100→400 条的扩展留在哪 | **只留在 `robomme_hard/env_metadata/train/`**，`robomme` 回上游 100 条 | 留在 `robomme` 就违反 H2「旧包 = 上游原样」 |
| D-4 | 拆包时点 | **S3 拿到 `NATIVE_REGRESSION` 结论后再动 `src/robomme/`**；在此之前只做不碰 `src/` 的准备（第二部分阶段 0） | S3 启动锚点 `c8c06ab` 读的是活树，中途改 `src/robomme` 会让 S3 后半段跑在另一份代码上 |

用户已在 V6 计划 D7 m13 给过「`src/robomme/` 改动免逐项批准、改完出报告」，但那是对 V6 新值改动的授权；**本方案把 `src/robomme/` 整体回退到上游**属于新范围，按 P2 须另行批准。

### 五、重构后的接口与包结构

#### 5.1 目录（改动一览：文件 / 来源 / 改什么）

| 路径 | 来源 | 改什么 |
|---|---|---|
| `src/robomme/**` | 上游 `main` @ `1fadc0e` 的 `src/robomme/**` 逐文件覆盖（含 `env_metadata/`） | 删 fork 新增的 9 个 utils；`RecordWrapper.py` 回 2000 步；`episode_config_resolver.py` 回 247 行 |
| `src/robomme_hard/**` | 当前 `src/robomme/**` @ 本方案 Beta 锚点整包复制 | ①包名：8 处绝对 import `robomme.` → `robomme_hard.`（或改相对）；②`env_record_wrapper/episode_config_resolver.py`：`from_v4_specs` 收编进 `__init__` 的 `dataset` 分支（5.2）；③新增 `env_record_wrapper/hard_specs.py`（5.3）；④新增 `env_metadata/xhard{1,2,3,4}/specs.jsonl`；⑤新增 `README.md`（5.5） |
| `src/robomme_hard/__init__.py` | 新 | 导入时若 `"robomme.robomme_env" in sys.modules` 则 `raise ImportError("robomme 与 robomme_hard 不能同进程导入：ManiSkill 注册表按 env_id 唯一")`；反向在 `robomme` 侧**不加**（旧包不改） |
| `scripts/evaluation_hard.py` | `scripts/evaluation.py` 复制 | 只改两处：import 行；`for task in TASKS` 外面套 `for tier in BenchmarkEnvBuilder.get_difficulty_list()`，`dataset=tier`；`max_steps` 注释加一句「xhard 档不受 1301 限制，见 V6 口径 2」（值本身由用户定，默认仍 1300） |
| `scripts/eval/v4_eval.py`、`scripts/parity/*.py`、`scripts/injection/**`（14 文件）、`tests/**`（45 文件） | 现有 | `from robomme.` → `from robomme_hard.`（机械替换，AST 校验零残留）；`v4_specs.load_specs` 改为薄包装调用 `robomme_hard.env_record_wrapper.hard_specs.load_specs` |
| `pyproject.toml` | 现有 | `packages = ["src/robomme", "src/robomme_hard"]` |
| `AGENTS.md` P1/P2 | 现有 | P1 清单加第六入口（D-1 放行后）；P2 `<PROTECTED_DIRS>` 扩为 `src/robomme/`（冻结 = 上游原样）+ `src/robomme_hard/`（逐个批准） |

**D-2 推荐 copy 的三个硬理由**：①ManiSkill `register_env` 对重复 id 在 `override=False` 时 `raise RuntimeError`（`.venv/lib/python3.11/site-packages/mani_skill/utils/registration.py::register_env`），两包各自装饰 `@register_env("BinFill")`，任何跨包 import 都会把两套注册拉进同一进程；②`utils/__init__.py` 虽逐字节相同，但它星号导入 `subgoal_planner_func`、`object_generation` 等**不相同**的模块，引用它等于引用旧实现；③H1 要求的是「行为逐位相同」，拆包后由 V1′ 对拍保证，不需要用共享字节来保证。

#### 5.2 `BenchmarkEnvBuilder`（`robomme_hard` 版）签名与语义

```python
class BenchmarkEnvBuilder:
    _ALLOWED_DATASETS = {"train", "test", "val"} | set(NEWVALUE_DIFFICULTIES)   # 后者 = ("xhard1","xhard2","xhard3","xhard4")

    def __init__(self, env_id, dataset="test", action_space="joint_angle",
                 gui_render=False, override_metadata_path=None, max_steps=10000):
        # 签名与上游逐字相同；只多认四个 dataset 值
        if is_newvalue_difficulty(dataset):
            header, _, rows = hard_specs.load_specs(self._resolve_specs_path())   # 包内 env_metadata/<tier>/specs.jsonl
            self._hard = {"sampling_config": header["sampling_config"][env_id], "recovery_rule": header.get("recovery_rule"),
                          "rows": {int(r["episode"]): r for k, r in rows.items() if k.split("/")[0] == env_id}}
            self.metadata_index = {}
        else:
            self._hard = None
            self.metadata_index = load_episode_metadata(self._resolve_metadata_path())   # 与上游同一条路

    @classmethod
    def get_task_list(cls): ...            # 不变：16 任务固定序
    @classmethod
    def get_difficulty_list(cls): return list(NEWVALUE_DIFFICULTIES)   # 新增；MoveCube/InsertPeg/StopCube 只在 xhard4 有行，其余档 get_episode_num()==0
    def get_episode_num(self): ...         # xhard 档 = 该任务 selected 行数（3）；原三档不变
    def make_env_for_episode(self, episode_idx, max_steps=None, include_*...): ...   # 不变；xhard 档 env_kwargs.update(self._hard_kwargs(episode_idx))
```

- `override_metadata_path` 在 xhard 档下解释为「含 `<tier>/specs.jsonl` 的目录」，与原三档「含 `record_dataset_<task>_metadata.json` 的目录」平行，不新增参数。
- `from_v4_specs` 保留为 `@classmethod` 薄包装（`scripts/eval/v4_eval.py` 的 `--specs` 任意路径用法不断），内部走同一 `_hard` 结构。
- **episode 编号语义**：xhard 档 `episode_idx` = specs 行里的候选序号（0/3/6），不是 0..2；`get_episode_num()` 返回 3 但可评 episode 要用 `hard_episodes()`（= 现 `v4_episodes()`）。为了让 `evaluation_hard.py` 与 `evaluation.py` 的 `for episode in range(episode_count)` 循环体不改，推荐**在 `_hard` 构造时把行按候选序升序重编为 0..n-1**，原候选序号保留在 `info["hard_candidate_index"]`（⚠ 陷阱：重编号只影响 builder 侧索引，规格行本身与 `identity_sha256` 不动，否则 §六 SPECS_IDENTITY 必炸）。

#### 5.3 `hard_specs.py`（从 `scripts/parity/v4_specs.py` 下沉的只读部分）

只搬 `load_specs()` 与它依赖的纯函数：`canonical_json`、`digest`、`identity_sha256`、`HEADER_KEYS`、`seed_rule_for`、`_known_seed_rule`；**不搬 `draw`/`freeze`**（抽签与冻结留在 `scripts/parity/`，它们要起环境、写文件）。`load_specs` 现有的封套校验（`sampling_config_sha256` 自洽、每行 `spec_sha256`、`identity_sha256`、runtime 四项与 builder 的 `gym.make` 参数逐字相等）一条不少；源码指纹校验（`source_fingerprint`）在包内改为**只警告不拒绝**——发布后用户机器上的源码 sha 就是包自己的 sha，指纹应在打包时重算写回 header，第二部分 §2.3 给命令。

#### 5.4 `scripts/evaluation_hard.py` 与 `evaluation.py` 的 diff（上限）

```diff
-from robomme.env_record_wrapper import BenchmarkEnvBuilder
+from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder
 ...
 TASKS = BenchmarkEnvBuilder.get_task_list()
+TIERS = BenchmarkEnvBuilder.get_difficulty_list()   # xhard1..xhard4
 ...
-for task in TASKS:
-    env_builder = BenchmarkEnvBuilder(env_id=task, dataset="test", ...)
+for tier in TIERS:
+  for task in TASKS:
+    env_builder = BenchmarkEnvBuilder(env_id=task, dataset=tier, ...)
+    if env_builder.get_episode_num() == 0: continue      # MoveCube/InsertPeg/StopCube 只有 xhard4
```

视频落盘名加 `tier`，其余逐字不动。判定：`diff scripts/evaluation.py scripts/evaluation_hard.py | grep -c '^[<>]'` ≤ 12。

#### 5.5 `src/robomme_hard/README.md` 必含内容（H3）

①一句话：hard = 四档 `xhard1<xhard2<xhard3<xhard4`，原三档在本包下与 `robomme` 逐位相同（附 V1′ 判定行原文）；②四档定稿表（从 `0925-newtask-release-v6-plan.md` 第一部分 §三逐字搬，含备注列）；③「改动在哪」表：由脚本 `scripts/parity/hard_pkg_manifest.py` 生成，逐文件列「与 `src/robomme` 相同 / 不同（+x/−y 行）/ 本包新增」，README 里内联生成结果并写生成命令；④机制说明：`sampling_config` 两块结构、`SpecRecorder` 导出/回注、`specs.jsonl` 封套、seed 偏移公式；⑤使用：`evaluation_hard.py` 三行示例 + `override_metadata_path` 用法；⑥红线：两包不可同进程导入、xhard 不受 1301 步限制、`fail_safe_limit=5000`。

### 六、验收（查什么 / 怎么查 / 过了说明什么 / 判定行）

| 项 | 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|---|
| UPSTREAM_BYTES | `src/robomme/**` 与上游逐字节相同 | `git diff --stat <上游 main 树> HEAD -- src/robomme/`（上游以 `git fetch <url> main` 到 `FETCH_HEAD` 取）为空；另 `cmp` 三个冻结脚本 | H2 成立；上游合并时 `src/robomme` 零 diff | `UPSTREAM_BYTES=PASS files=<n> diff=0` |
| IMPORT_ISOLATED | `robomme_hard` 包内没有任何 `robomme.` 绝对引用；同进程双导入被拒 | AST 遍历 `src/robomme_hard` 全部 `Import`/`ImportFrom`，模块名以 `robomme.` 开头计数；`uv run python -c "import robomme.robomme_env, robomme_hard"` 期望 `ImportError` | copy 方案没有静默回头依赖旧包 | `IMPORT_ISOLATED=PASS abs_refs=0 dual_import=REJECTED` |
| SPECS_IDENTITY | 包内四份 `specs.jsonl` 与 `scripts/configs/newtask-v6/v6-01/<tier>/` 的 `identity_sha256` 相等 | `hard_specs.load_specs` 各加载一次，比对 header 字段 | 分发的规格就是 S4 生成用的那份 | `SPECS_IDENTITY=PASS tiers=4 rows=165` |
| **V1′** | `robomme_hard` 原三档 vs S0 基线 144 局 h5 sha | 复用 S3 运行器 `run_s3.py` 的路径 B，只把 `PYTHONPATH`/import 切到 `robomme_hard`；比较 `compare/h5_pairs.jsonl` | H1 成立：同参数产同内容 | `NATIVE_REGRESSION_HARD=PASS compared=144 sha_equal=144 field_mismatch=0` |
| HARD_EVAL_SMOKE | `evaluation_hard.py` 链路能跑 | 单 tier、单任务、单 episode（`--limit` 用临时 env `HARD_EVAL_LIMIT=1`，不改脚本）；`DummyModel` 跑到 `terminated/truncated` | 接口闭环 | `HARD_EVAL_SMOKE=PASS tiers=1 tasks=1 episodes=1 status=<任意>` |
| LIGHTWEIGHT | 现有轻量测试在改 import 后失败/错误集合是 S0 的子集 | 沿 V6 §5.3 四片各 280 s | 机械替换没打坏测试 | `LIGHTWEIGHT=PASS new_failures=0 new_errors=0` |
| EVAL_PY_UPSTREAM / ENTRIES | 三脚本逐字节同上游；顶层入口数 | `cmp`；`ls -1 scripts/*.py \| wc -l` = 6（D-1 放行后） | 冻结项未破 | `EVAL_PY_UPSTREAM=PASS ENTRIES=6` |
| DIFF_CAP | `evaluation_hard.py` 与 `evaluation.py` diff 行数 | `diff … \| grep -c '^[<>]'` | H4 成立 | `EVAL_HARD_DIFF=PASS lines=<n≤12>` |

V1′ 为什么能逐位：`robomme_hard` 的原三档路径与现 `src/robomme` 是同一份字节（copy），只改包名与 import；随机流由 `torch.Generator(seed)` 决定、与包名无关；S3 已在证明现 `src/robomme` 的原三档与 S0 基线逐位相同，V1′ 只是把「被测包」换名再证一次，所以两者要么同过、要么同挂。

### 七、实施步骤表（阶段 / 内容 / 判据）

| 阶段 | 内容 | 判据 | 是否碰 `src/` |
|---|---|---|---|
| 0 准备（可在 S3 结束前做） | 取上游 `main` 快照并固化 sha；写 `hard_pkg_manifest.py`（只读 diff 工具）；写 `hard_specs.py` 草稿放 `scripts/parity/`（先不下沉）；写 `evaluation_hard.py` 草稿放 scratchpad | `UPSTREAM_BYTES` 的对照表先出（现状 26 不同 / 9 新增，作为阶段 2 的期望） | 否 |
| 1 裁决 | D-1～D-4 逐条拿用户答复；P2 批准清单：「`src/robomme/**` 整体回上游」「新建 `src/robomme_hard/**`」两条 | 用户逐条同意原话写进本文件 §一 | 否 |
| 2 建 `robomme_hard` | `cp -a src/robomme src/robomme_hard`；改 8 处绝对 import；加 `__init__` 互斥；收编 `from_v4_specs`；下沉 `hard_specs.py`；复制四份 `specs.jsonl`；改 `pyproject`；`uv sync` | `IMPORT_ISOLATED`、`SPECS_IDENTITY` | 只新增 |
| 3 切换调用方 | 14 个 scripts 文件 + 45 个 tests 文件 import 替换；`v4_specs.load_specs` 改薄包装；`evaluation_hard.py` 落顶层 | `LIGHTWEIGHT`、`EVAL_HARD_DIFF`、`ENTRIES=6` | 否 |
| 4 V1′ 对拍 | 按 §六 跑 144 局（约 50 min 单卡，S0 实测 2994 s；须 tmux + Monitor；预算 144 次轨迹尝试，属 P3 阈值内须用户在阶段 1 一并授权） | `NATIVE_REGRESSION_HARD=PASS` | 否 |
| 5 回退 `src/robomme` | 用上游树覆盖 `src/robomme/**`（含 `env_metadata`）；`git rm` 9 个新增 utils | `UPSTREAM_BYTES=PASS`、`EVAL_PY_UPSTREAM=PASS`、`HARD_EVAL_SMOKE` | **是（P2）** |
| 6 文档与规则 | `src/robomme_hard/README.md`；`AGENTS.md` P1/P2 改写；账本追加；`docs/validation/newtask-v6/<日期>-hard-split.md` 报告 | `git diff --check`；README 内联全部判定行原文 | 否 |

实施完成后实测结果以子节追加在本表之后，不改写原计划。


## 附录 B、legacy 清单（2026-09-27，只读盘点；删除须用户逐组勾选后另起一轮执行）

用户原话：「告诉我有哪些 legacy 文件可以删除 我只需要 v6 的几阶段来完成 … 的重构」。分组原则：**A** 不在 V6 四阶段 + V1′ 的闭包内、也不被保留测试引用 → 可删；**B** 历史留档、git 可追溯、删不删由用户定；**C** 必须保留；**D** 他人在途、不动。引用关系由 `grep`（含裸 import，`scripts/parity/__init__.py` 往 `sys.path` 插目录）与 `git ls-files` 实测。

### 表 0　V6 四阶段 + V1′ 的依赖闭包（这就是要保留的最小集合）

| 类别 | 文件 | 谁用 |
|---|---|---|
| 入口 | `scripts/parity/train_split_config.py`（阶段 1）、`v4_specs.py`（2a/2b）、`v4_rollout.py`（2c）、`v5_generation.py`（2a～2c 一键管道，审查修复三席用的就是它）、`scripts/eval/v4_eval.py`（3） | 第一部分 §三 |
| 被入口 import | `scripts/seed_layout.py`（`train_split_config`、`v4_specs`、`train_split_parity`、`train_split_audit`、`v6_tier_monotone` 裸 import）；`train_split_runner.py`（`v4_rollout` subprocess）→ `train_split_worker.py`；`train_split_parity.py`（`v4_rollout::compare_h5_pair`、V1′ 比较器）→ `train_split_comparison.py` ↔ `comparator_fixtures.py`；`train_split_audit.py`（`test_v4_xhard_unmaskswap`/`videoplace` 用）；`scripts/injection/candidates/io.py` 的 `canonical_json`/`digest`（`v4_specs.py` 唯一的 injection 依赖，阶段 0b 内联） | 依赖闭包盘点 |
| V6 收尾 | `scripts/parity/{v6_candidate_values,v6_tier_monotone,v6_v0_native_definitions,v6_site_catalog,v6_site}.py`、`v6_site.html` | 各自 `test_v6_*` |
| 配置 | `scripts/configs/newtask-v3/{subset_manifest,train_manifest}.json` + `official_train/`（`train_split_parity.DEFAULT_FROZEN_DIR`、`train_split_audit`）；`newtask-v4/sampling_config.json`（`v4_specs.DEFAULT_SAMPLING`）；`newtask-v5/sampling_config.json`（`v6_v0_native_definitions`、CLAUDE.md 核实清单）；`newtask-v6/{sampling_config.json,v6-01/,v6-02/}`（`v6-01` 仍被 `v5_generation` 路径模板与 `test_v5_generation_tools` 引用） | grep |
| 产物 | `artifacts/train-parity/local-smoke-01/official-src/`（`--official-root` 官方源码树，`.official_tree=1d4c1369…`）；`artifacts/newtask-v6/v1/base/`（S0 基线 144 局 49 GB，V1′ 对照侧，用户明令保留）；`artifacts/newtask-v6/v6-02/`（现行 165 局 112 GB）；`artifacts/newtask-v6/{s4-relaunch-02,audit-fix-02}`（v6-02 验收链）；`artifacts/newtask-v6/{site-v11,site-v12}` | 第二部分 §2.2、审查修复留档 |

### A　可删（git 跟踪的代码、测试、配置、留档）

| 路径 | 规模 | 依据 |
|---|---|---|
| `scripts/injection/**`（`candidates/` 11 文件、`rollout/` 12 文件、`delivery.py`、`hf_release.py`、`_migrate_run10.py`、`__init__.py`） | 27 跟踪文件 | V2 注入流程（`INJECTION_REFACTOR_PLAN.md`）；V6 只用 `candidates/io.py` 两个纯函数，先内联进 `v4_specs.py`；`hf_release.py` 是运行 10 的 HF 发布器，`_migrate_run10.py` 只被 `test_injection_migration` 引用，`rollout/{figure_parity,single_binfill}.py` 无人引用 |
| `scripts/parity/{v4_combos,v4_demo_probe,v4_reset_probe,v4_spec_negative}.py`、`scripts/configs/newtask-v4/combos.json` | 5 文件 | V4 探针；零测试引用，只被 0922/0924 计划与 v4/v5 留档提到 |
| `scripts/parity/{calibrate,compare_vs_original}.py`、`tolerance.json`、`gl/`（2 文件）、`results/`（79 文件） | 83 文件 | V3 容差对拍（ada/a6000/a40 标定，`scripts/parity/README.md`）；V6 的 V1 走严格 sha 路径 `train_split_parity`，不用容差档；零测试引用 |
| `tests/_shared/{parity_keyframes,parity_observer,parity_review,parity_runner,parity_worker_isolation,action_freeze_campaign,parallel_calibration,native_sampling_parity,contract_builder_fixture,frozen_injection}.py`、`tests/_shared/parity_sitecustomize/` | 11 项 | 全部只服务 V2 对拍与 injection（保留 `tests/_shared/{__init__,dataset_generation,repo_paths}.py`，上游原有） |
| `tests/lightweight/{test_candidate_loader,test_candidates_refactor,test_env_check,test_episode_specs,test_episode_timeout,test_hf_release,test_injection_blocks,test_injection_campaign,test_injection_contract,test_injection_delivery,test_injection_migration,test_operand_scope,test_refactor_figures,test_reset_pipeline,test_rollout_parity,test_rollout_state,test_window_timeline,test_native_sampling_config,test_native_sampling_evidence,test_action_freeze_delivery,test_action_freeze_campaign}.py`、`tests/dataset/test_native_sampling_parity.py` | 22 文件 | import A 组模块或读 `scripts/configs/newtask-v2`／`docs/validation/newtask-v2`；`test_env_check` 还引用早已不存在的 `scripts/injection/env_check.py` |
| `scripts/configs/newtask-v2/`（3 文件）、`newtask-v3/history/`（4）、`newtask-v4/v4-01/`（2）、`newtask-v5/v5-01/`（2） | 11 文件 | 只被 A 组代码／测试或历史文档读；`v4-01` 被 `test_v5_xhard_videounmask_buttonunmask.py` 以绝对路径引用一处、`v5-01` 被 `test_v5_generation_tools.py` 引用一处，删前改这两处夹具 |
| `docs/validation/newtask-v2/**` | 115 文件、8.2 MB | 只被 A 组测试读取（`cases.json`、证据包） |
| `INJECTION_REFACTOR_PLAN.md`、`NEWTASK_V2_PLAN.md` | 2 文件 | 只被 `AGENTS.md` 历史账本与 v2 留档引用（账本条目不改，死链可接受） |
| `artifacts/injection/**`（320 跟踪文件、121 MB）、`artifacts/test-tmp/`（940 MB，514 个测试临时目录）、`artifacts/cache/`（144 MB uv 缓存）、`artifacts/codex-multiagent/`（5.6 MB）、`artifacts/logs/`（236 KB） | — | 与 A 组同源／临时／缓存；`artifacts/injection` 是唯一有 git 跟踪的 `artifacts` 子树，删时 `git rm -r --cached` 一并处理 |

### B　V6 之前的全部 + V6 中间产物（**已裁决：归档经验教训进 `docs/`，其余删除；不再做 V2～V5 任何对拍与生成**）

用户 2026-09-27 原话：「历史教训小文件留档 进入 …/docs 其他的全部进入删除 只保留git历史」「我要的是归档V6 之前的 不再做对拍也不再生成 只作为经验教训」。落地规则（执行顺序见第一部分 §0.3 表）：

1. **去处只有两种**：①经验教训文本 → `docs/`；②其余删除。跟踪文件靠 git 历史恢复；`artifacts/` 全部未跟踪，**搬进 `docs/` 的那份就是唯一副本**，所以保留清单由脚本从 docs 引用生成（§0.3 步骤 4），不靠人手。
2. **进 `docs/` 的**：`docs/validation/newtask-v2～v5/` 原地不动；三份旧计划 `git mv` 到 `docs/plans/`；`artifacts` 里被 docs/账本引用或属显式验收依赖的小文件（判定行来源、授权记录、事故记录、运行脚本与清洗后日志、审查汇总）复制到 `docs/validation/<版本>/records/legacy/<原二级目录>/`，附 `MANIFEST.md`。
3. **删除（跟踪）**：表 A 全部；`scripts/generate_dataset_newseed.py`（P1 改四入口，D-1 放行后 `evaluation_hard.py` 为第五入口）；`tests/lightweight/{test_swap_schedule_generic,test_binfill_demo_duplicate}.py`（只依赖它）；`test_h5_parity_compare`、`test_native_restore_step2` 若测试对象已不存在则删。
4. **删除（未跟踪 `artifacts/`）**，逐目录显式列名：`artifacts/newtask-v4`（31 GB）、`artifacts/newtask-v5`（32 GB）、`artifacts/audit`（1.1 GB）、`artifacts/newtask-v6/{v6-01,v6-01-infra-recovery-01,v6-s2-20260926-01,v6-s3-20260926-01,gl-smoke-61890467-binf-xhard1-20260926T195419Z,s3-slow-investigation,s0,s1-reset,s2-prep,s4-prep,s4-launch,plan-probes,vpb-order-fix-prep,site,site-v2,site-review,site-v3,site-v4,site-v5,site-v6,site-v7,site-v8,site-v9,site-v10}`。删前必须已 `LEGACY_KEEP=PASS`、`LEGACY_ARCHIVE=PASS`。
5. **明确保留（表 C）**：`artifacts/newtask-v6/v1/base`（S0 基线 144 局 49 GB，**V1′ 对照侧，用户明令保留对拍**）、`v6-02`、`s4-relaunch-02`、`audit-fix-02`、`site-v11`、`site-v12`、`artifacts/train-parity/local-smoke-01/official-src`。

下表保留为盘点原文（「说明」列的「建议留」「由用户定」已被上述裁决覆盖）：


| 路径 | 规模 | 说明 |
|---|---|---|
| `0921/0922/0924-newtask-release-v{3,4,5}-plan.md` | 3 文件、400 KB | 被 `train_split_parity/audit`、`v4_specs`、`v5_generation` 的 docstring 与 `test_v4_xhard_*`/`test_v5_*` 注释以链接引用（删了只是死链）；**建议留** |
| `docs/validation/newtask-v{3,4,5}/` | 60 文件、<1 MB | 代码不读 |
| `tests/lightweight/{test_swap_schedule_generic,test_binfill_demo_duplicate,test_h5_parity_compare,test_native_restore_step2}.py` | 4 文件 | 前两者只依赖 `generate_dataset_newseed.py`（随下一行裁决）；后两者只依赖 `repo_paths`，实施时看测试对象是否仍存在再定 |
| `scripts/generate_dataset_newseed.py` | 1 文件 | **不在 V6 闭包内**，只被 A 组与上一行引用；但它是 P1 五入口之一，删除须用户明确改 P1 清单为四入口 |
| `artifacts/newtask-v4/`、`artifacts/newtask-v5/` | 31 GB、32 GB | 旧规格产物；规格文件本身已在 git |
| `artifacts/newtask-v6/{v6-01（94 GB）,v6-01-infra-recovery-01（18 GB）,v6-s2-20260926-01（73 GB）,v6-s3-20260926-01（49 GB）,gl-smoke-61890467-…（795 MB）,s3-slow-investigation（361 MB）,s0（361 MB）,plan-probes（154 MB）,s1-reset,s2-prep,s4-prep,s4-launch,vpb-order-fix-prep,site,site-v2,site-review,site-v3～site-v10}` | 约 236 GB | S2/S3 结论与 v6-01 对照已写进 `docs/validation/newtask-v6/`；用户 2026-09-24 口径「收尾只保留最终产物」支持删；`v6-s3` 删前确认 `compare/summary.json` 已在 `records/`；`s4-launch/` 含 S4 事故与恢复批准记录，建议只删其中大文件 |
| `artifacts/audit/`（5 个 `v6-semantic-*`） | 1.1 GB | 两轮审查证据，结论已在 `0926-v6-audit-fix-plan.md` 第七、八节 |

### C　必须保留

`src/robomme/**`（回上游由阶段 5 处理）；`scripts/{evaluation,run_example,dataset_replay,seed_layout}.py`；表 0 全部；`scripts/parity/{manifest_16x3.json,identities_16x3.txt,README.md,__init__.py}`、`scripts/README.md`；`tests/` 其余（上游 29 文件 + `test_v4_*`、`test_v5_*`、`test_v6_*`、`test_bin_collision`、`test_sampling_config_split`、`test_comparator_scope`、`test_train_split_parity`、`test_scripts_do_not_import_tests` 等）；`docs/validation/newtask-v6/**`、`docs/README.md`、`docs/greatlakes.md`、`docs/maniskill-robomme-multiprocess.md`、`docs/validation/README.md`；三份 0925/0926 计划；上游原有 `challenge_interface/`、`doc/`、`Dockerfile`、`.dockerignore`、`readme.md`、`LICENSE`。

### D　他人在途，不动

`logs/`、`scripts/configs/newtask-v6/smvla-smoke-0927/`、`scripts/parity/v6_gt_lengths.{py,json}`、`M scripts/parity/v6_site.{html,py}`、`artifacts/newtask-v6/smvla-0927{,-more,-fill,-smoke}`（约 2 TB）、tmux `smvla-site-8060`、`corlvis-site`。
