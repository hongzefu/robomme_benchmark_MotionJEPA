# 0927 方案：`robomme_hard` 分层继承双包 · 两阶段生成 · 单一 jsonl（只规划不实施）

> **权威性**：本文件是 [`0926-robomme-hard-split-plan.md`](0926-robomme-hard-split-plan.md) §〇′ 的精简定稿版，只写最新口径，不保留历史决策与备选；两份冲突时以本文件为准。只规划，不实施；每一阶段须单独获批后才动手，阶段 3 触碰 P2 须逐文件批准，阶段 4 的生成预算按第二部分 §三 一次性申请。
> **代码锚点**：本仓库 `newtaskRelease-v5` @ `66d9a424`（12.204.1）；官方 `RoboMME/robomme_benchmark` `main` @ `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`；官方隔离源码树 `artifacts/train-parity/local-smoke-01/official-src/`（`.official_tree` = `1d4c1369…`，tree sha）；现行规格 `scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl`（selected 行合计 165）；S4 交付清单 `artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json`。
> **工作副本**：`/data/hongzefu/robomme_benchmark_MotionJEPANewTask`（环境 A，sled-vail）。
> **commit 体例**：`<大>.<小>[.<修订>] <中文描述>`，实施从 12.205 起。
> **外部依赖锚点**：`uv.lock` / `pyproject.toml` 不变，唯一依赖侧改动是 wheel `packages` 增加 `src/robomme_hard`；ManiSkill 注册语义以 `.venv` 内 `mani_skill/utils/registration.py` 现版本为准。
> **已完成、不再赘述**：V6 四档生成与 S0～S5 验收、审查修复、拆包阶段 0b 瘦身（12.200～12.203：`scripts/` 顶层四入口、删 injection／V3 容差对拍／V4 探针、V1′ 入口 `scripts/parity/hard_parity.py` 落地）。

---

# 第一部分（给人看）

## 一、总览

**一句话方案**：两个并列包——`src/robomme/` 逐字节等于官方 `main`，`src/robomme_hard/` 只放差异（复制 16 个环境类与改过的 utils、借用没改过的、`BenchmarkEnvBuilder` 子类化），四档规格作为包数据 `env_metadata/xhardN/specs.jsonl` 随包分发；生成链路收成两阶段 `scripts/injection-dev/`——第一阶段在内存里定规则→抽签→封存、只落一份 jsonl，第二阶段只读这份 jsonl 生成 h5 并把结果回写进去；评估侧 `BenchmarkEnvBuilder(env_id, dataset="xhard3")` 自己读包内 jsonl，合作者只看到这一个文件。

**已定死口径**（依据小节随条给出）：

| 编号 | 口径 | 依据 |
|---|---|---|
| E-1 | 双包、分层继承：环境类与改过／新增的 utils 复制，未改的 utils 与 wrapper 借用，builder 子类化 | §三 |
| E-2 | 环境类同 id，副本一律 `@register_env(<id>, override=True)`，包导入末尾断言注册表归属 | §3.3 |
| E-3 | G1 用钉 commit + 逐文件 sha256 清单 + 守卫脚本 + 导入时 cheap 校验 | §3.4 |
| E-4 | 生成链路两阶段，全部依赖放 `scripts/injection-dev/`；第一阶段中间量只在内存，只落一份 jsonl | §五 |
| E-5 | 第二阶段只读 jsonl，跑完回写 `rollout` 块；`identity_sha256` 只盖 `spec`，递补追加行不改原行 | §5.2、§5.3 |
| E-6 | jsonl 落 `src/robomme_hard/env_metadata/xhardN/specs.jsonl`，一档一目录 | §四 |
| E-7 | `scripts/evaluation.py` 官方原样不动，`evaluation_hard.py` 为第五入口，只差 import 与循环 | §四 |
| E-8 | `scripts/parity/` 只做「与官方比」：S0 基线对拍、V1′、G1 守卫、xhard 侧回归 | §5.4 |
| E-9 | 官方 `generate_dataset.py` 及三个兄弟文件 vendor 进 `scripts/parity/official/` | §3.5 |
| E-10 | `tests/` 只保证可收集，语义修复另立任务 | 第二部分 §〇 |
| E-11 | xhard 侧回归三道闸门加入，预算一次申请 | §六 |
| E-12 | 四个 Unmask 系 train 元数据 400 条只留 `robomme_hard`，`robomme` 回 100 条 | §3.1 |

## 二、要保证什么

| 保证 | 靠什么 | 判定行 |
|---|---|---|
| G1 `src/robomme/**` 与官方逐字节相同 | §3.4 | `UPSTREAM_BYTES=PASS commit=1fadc0ec files=<n> diff=0 borrowed=<m>` |
| G2 `robomme_hard` 跑原三档，h5 与 S0 基线 sha 逐位相同 | V1′ 144 局 | `NATIVE_REGRESSION_HARD=PASS compared=144 sha_equal=144` |
| G3 `robomme_hard` 跑 xhard，与 S4 交付一致 | §六 | `HARD_RESET_REPLAY=PASS resets=55 mismatch=0`、`HARD_ROLLOUT_SHA=PASS compared=16 sha_equal=16` |
| G4 评估接口与 `dataset="test"` 同形 | §四 | `EVAL_PY_UPSTREAM=PASS ENTRIES=5`、`EVAL_HARD_DIFF=PASS lines≤12` |
| G5 同进程 16 个环境 id 归属唯一可查 | §3.3 | `REGISTRY_OWNER=PASS envs=16 owner=robomme_hard` |
| G6 两阶段只依赖 jsonl，中间量不落盘，回写不破坏封存 | §五 | `FREEZE_ONLY_JSONL=PASS files_written=1`、`ROLLBACK_WRITE=PASS spec_hash_unchanged=1` |

## 三、文件结构与分层继承

### 3.1 `src/` 目录：每个文件从哪来

```text
src/robomme/                          官方 main 原样；本仓库不再往里放任何自有文件
src/robomme_hard/
  __init__.py                         先注册自家 16 环境 → 断言注册表归属 → 借用清单 cheap 校验（§3.3、§3.4）
  UPSTREAM.json                       官方 commit/tree、src/robomme 逐文件 sha256、借用清单、自校验哈希
  README.md
  robomme_env/
    __init__.py                       复制；新增 ENV_IDS 16 元组
    <Task>.py × 16                    复制；装饰器改 @register_env("<id>", override=True)
    utils/
      __init__.py                     复制
      改过 8 个（difficulty object_generation route segmentation_utils subgoal_language
                task_goal subgoal_planner_func vqa_options）                              复制
      新增 9 个（bin_collision episode_spec sampling_config swap_uniform unmask_distractor_sampler
                unmask_distractors unmask_swap_xhard xhard xhard_home_site）              复制
      未改约 15 个（adjacent choice_action_mapping constant obschange oracle_action_matcher
                planner_denseStep planner_fail_safe reset_panda rpy_util save_reset_video
                SceneGenerationError statechange task4recovery generate_sample_action
                subgoal_evaluate_func）                                                  借用：三行 shim（§3.2）
  env_record_wrapper/
    __init__.py                       导出自家 RobommeRecordWrapper / BenchmarkEnvBuilder / hard_specs；
                                      借用 DemonstrationWrapper EndeffectorDemonstrationWrapper FailAwareWrapper
                                           MultiStepDemonstrationWrapper RRTPlanFailure 与 episode_dataset_resolver 导出项
    RecordWrapper.py                  复制（fail_safe_limit=5000 是 step() 内部字面量，子类改不了）
    OraclePlannerDemonstrationWrapper.py   复制（它 import 的 vqa_options 是改过的）
    hard_builder.py                   class BenchmarkEnvBuilder(官方 BenchmarkEnvBuilder)（§四）
    hard_specs.py                     load_specs 与封套校验、两段源码指纹
  env_metadata/
    xhard1/specs.jsonl … xhard4/specs.jsonl      四档规格（§5.3）
    train/record_dataset_{ButtonUnmask,ButtonUnmaskSwap,VideoUnmask,VideoUnmaskSwap}_metadata.json   400 条（E-12）
pyproject.toml                        wheel packages 加 "src/robomme_hard"
```

按层归纳，以及为什么这样选：

| 层 | 做法 | 数量 | 理由 |
|---|---|---|---|
| 环境类 | 复制 | 16 | xhard 改动交错在 `_load_scene` / `_initialize_episode` 等几百行方法内（`BinFill.py` 1120 行里 98 处），继承只能整段覆写，无收益 |
| 改过／新增 utils | 复制 | 8 + 9 | 与官方不同，必须自有 |
| 未改 utils | 借用 shim | ~15 | 单一真源，官方更新自动跟随 |
| 未改 wrapper | 借用 re-export | 6 | 同上 |
| `RecordWrapper.py` | 复制 | 1 | `fail_safe_limit` 在 `RobommeRecordWrapper.step`（约 310 行）内部，子类覆写等于整段复制 |
| `BenchmarkEnvBuilder` | 子类 | 1 | 改动就是「多认四个档名 + 读 jsonl + 拼三个 kwargs」，官方各方法都很短 |

自有 `.py` 约 38 个，其余全部指向 `robomme`。

### 3.2 借用 shim 与 import 改写规则

**为什么借用必须和注册归属一起设计**：Python 导入子模块前先执行父包 `__init__`，而 `robomme/robomme_env/__init__.py` 就是 16 行 `from .BinFill import *`——任何一次 `from robomme.robomme_env.utils.x import …` 都会顺带把官方 16 个环境注册进 ManiSkill 注册表。

shim（每个借用的 utils 一个同名文件，不含逻辑）：

```python
# 借用：robomme 同名模块的别名，逻辑以官方为准；清单见 ../../UPSTREAM.json
import importlib, sys
sys.modules[__name__] = importlib.import_module("robomme.robomme_env.utils.rpy_util")
```

复制文件里的绝对 import 三条规则：相对 import 不动；`from robomme.<path>` 且 `<path>` 在借用清单内不动；`<path>` 是改过／新增的一律改 `robomme_hard.`——漏一处就静默回头用官方旧逻辑。AST 扫描判定 `ABS_IMPORT=PASS files=<n> retargeted=<k> borrowed=<m> stray=0`。

### 3.3 注册表归属：同 id 为什么不会静默出错

⚠ 实测语义（`mani_skill/utils/registration.py::register_env`）：同 uid 二次注册在 `override=False` 时只 `logger.warn("… already registered. Skip registration.")` 并**静默保留第一个**；`override=True` 时弹出旧登记重新注册。什么都不做的话，谁先 import 谁赢，输的一方无异常。

三道机制：

1. 16 个副本 `@register_env("BinFill", override=True)`：进程 import 过 `robomme_hard.robomme_env` 后 16 个 id 一律归它，与顺序无关；
2. `robomme_hard/__init__.py`：官方已先导入时 `warnings.warn`；导入自家 `robomme_env` 后遍历 `ENV_IDS`，`REGISTERED_ENVS[uid].cls.__module__` 不以 `robomme_hard.` 开头即 `raise ImportError`；
3. 包指纹进产物：h5 attrs、jsonl header／`rollout` 块、builder `info` 都写 `env_package="robomme_hard"` 与 `package_fingerprint`。

红线：**同进程一旦导入 `robomme_hard`，16 个 id 全部归它；要官方原三档行为另开进程只导 `robomme`。** 守卫只在 `robomme_hard` 侧，只导 `robomme` 的进程不知道 `robomme_hard` 存在，这是正确行为。

### 3.4 G1 强校验

- `src/robomme_hard/UPSTREAM.json`：`upstream.commit` 40 位（禁 `main`）、`robomme_files`（`src/robomme/**` 逐文件 sha256，含 `env_metadata`）、`borrowed`（借用文件 sha256）、`manifest_sha256`（剔掉本键后 canonical JSON 的 sha256，清单自防篡改）。
- `scripts/parity/upstream_guard.py`（纯 CPU、秒级，纳入核心短测）：`git fetch <url> <commit>` 后 `git diff --stat <commit> HEAD -- src/robomme` 为空（网络不可达标 `net=skipped`）；文件集合与 sha **相等**（多一少一都 FAIL）；`borrowed` 每项命中且 `robomme_hard` 侧对应文件是 ≤ 3 行非注释行的 shim。
- 导入时对 `borrowed` 做 cheap 档（字节数 + 首尾 1 MiB blake2b）校验，不符只 `warnings.warn`；显式声明 cheap 挡不住等长改中间字节，full 档由守卫脚本负责。
- 源码指纹两段：`base_fingerprint`（借用文件总 sha）+ `hard_fingerprint`（`src/robomme_hard/**.py` 总 sha），写 jsonl header，`load_specs` 不符只警告（发布后指纹本就该在打包时重算）。

### 3.5 `scripts/` 目录

```text
scripts/
  seed_layout.py  dataset_replay.py  evaluation.py  run_example.py     四入口不动（后三者官方原样）
  evaluation_hard.py                                                    第五入口，与 evaluation.py diff ≤ 12 行
  injection-dev/                V6 四档生产链路，不随包分发（§五）
    freeze_specs.py  generate_h5.py                                     两个入口（路径直跑，不 -m）
    _extract.py  _draw.py  _freeze.py  _rollout.py  _report.py           内部模块
    site/                                                               v6_site*.py、v6_candidate_values.py 等只读出图
  parity/                       只做「与官方比」
    train_split_parity.py  train_split_runner.py  train_split_worker.py  train_split_config.py
    train_split_comparison.py  train_split_audit.py  comparator_fixtures.py     S0 基线对拍设施，不动
    hard_parity.py              V1′：robomme_hard 跑原三档 144 局 vs S0 基线
    upstream_guard.py           G1 守卫
    hard_regression.py          xhard 侧回归（G3）
    official/                   vendor 官方 scripts/data-generation 四文件 + SOURCE.json
      scripts/data-generation/{generate_dataset,validate_generated_dataset_contract,
                               write_generation_report,compare_joint_actions}.py
    identities_16x3.txt  manifest_16x3.json  README.md
  configs/
    newtask-v3/                 parity 用，不动
    newtask-v6/v6-02/           只读留档（S4 生成用的那份）；jsonl 真源改为包内
    其余（newtask-v4/ v5/ v6 的 sampling_config.json、v6-01/）  删
```

vendor 四文件的原因：`generate_dataset.py`（563 行）`import` 同目录的 `validate_generated_dataset_contract` 与 `write_generation_report`，后者又 `import compare_joint_actions`，缺一不可 import。`train_split_runner.py --official-root` 语义不变（把 `<root>/scripts/data-generation` 插 `sys.path`），所以 vendor 目录照官方布局放置。`artifacts/…/official-src/` 整棵树保留作 S0 基线证据，但生产与对拍默认不再依赖它。

## 四、评估过程中的 env make

### 4.1 合作者看到的

```python
from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder      # 与官方唯一不同的一行
builder = BenchmarkEnvBuilder(env_id="BinFill", dataset="xhard3", action_space="joint_angle", max_steps=1300)
for episode in range(builder.get_episode_num()):                       # 3 局：0、1、2
    env = builder.make_env_for_episode(episode)
```

`scripts/evaluation_hard.py` = `evaluation.py` 复制后只改三处：import 行；`for tier in BenchmarkEnvBuilder.get_difficulty_list():` 套在 `for task in TASKS` 外、`dataset=tier`；视频文件名加 tier。

### 4.2 builder 内部两条路

```text
dataset ∈ {train,test,val}   → 官方父类逻辑：env_metadata/<dataset>/record_dataset_<task>_metadata.json（seed/difficulty/episode）
                                → gym.make(env_id, obs_mode, control_mode, render_mode, reward_mode, seed=…, difficulty=…)
                                （train × Unmask 四任务改读 robomme_hard 包内 400 条）
dataset ∈ {xhard1..4}        → hard_specs.load_specs(env_metadata/<tier>/specs.jsonl)
                                → 取 task==env_id 且 selected 且 rollout.status=="ok" 的行，按 candidate 升序编为 episode 0..2
                                → gym.make(env_id, 同上四项 runtime, seed=row.seed, difficulty=tier,
                                           sampling_config=header.sampling_config[env_id],
                                           native_episode_spec=row.spec)
                                → 套 robomme_hard 的 RobommeRecordWrapper（fail_safe_limit=5000）
```

`native_episode_spec` 是回注：reset 时抽样流程照常发生，但每个取值点用冻结值替换，原抽样只作核验（`SpecRecorder` 记 `mismatch/unused`）。`info["hard_candidate_index"]` 带原候选序号；`runtime` 四项与 header 逐字比对，不等 `raise`。

⚠ 唯一别扭处：官方父类 `__init__` 的 `_ALLOWED_DATASETS` 白名单只认 `train/test/val` 且官方代码不能改，子类对 xhard 档先喂 `dataset_for_parent="test"` 过校验、再把 `self.dataset` 改回档名；父类顺手读的 `test` 元数据不被使用（`resolve_episode` 等全被覆写）。写进 README 实现说明。

## 五、数据生成链条：两阶段

### 5.1 第一阶段 `freeze_specs.py`：定规则 → 抽签 → 封存，只落一份 jsonl

```bash
uv run --no-sync python scripts/injection-dev/freeze_specs.py \
  --tier xhard3 --tasks all --candidates-per-env 10 --select 0,3,6 \
  --max-reset-attempts 30 --workers 4 --gpus 0,1 \
  --out src/robomme_hard/env_metadata/xhard3/specs.jsonl
```

| 步 | 做什么 | 实现来源（搬过去不改语义） | 起环境 | 去向 |
|---|---|---|---|---|
| ① 定规则 | 对 16 任务 `import robomme_hard.robomme_env.<Task>`，读类上申报的 `native_blocks` → 该档 decision／native 取值范围，合成 `sampling_config` dict | `train_split_config.extract_task` | 否 | 内存 → header |
| ② 抽签 | 每任务每档 10 候选：seed = `offset(tier) + env_code×1e5 + episode×100 + attempt`，`gym.make(task, sampling_config=…, seed, difficulty=tier, 四项 runtime)` → `reset()` → `env.unwrapped._spec.to_dict()`；reset 失败计入 `draw_stats` | `v4_specs._draw_one` / `draw_task` | 是（只 reset） | 内存 |
| ③ 封存 | 每格选候选 0/3/6 为正式局（`selected=true`），算每行 `spec_sha256`、整份 `identity_sha256`、两段源码指纹，封套校验 | `v4_specs.cmd_freeze` | 否 | **唯一落盘** `--out` |

不再产生 `sampling_config.json`、`drafts.jsonl`；10 个候选与 reset 失败统计都在 jsonl 里，信息不丢。写盘用同目录临时文件 + `os.replace`；`--out` 已存在默认拒绝。

### 5.2 第二阶段 `generate_h5.py`：只读 jsonl → 回注演示 → 回写

```bash
uv run --no-sync python scripts/injection-dev/generate_h5.py \
  --specs src/robomme_hard/env_metadata/xhard3/specs.jsonl \
  --output artifacts/newtask-v6/<run>/xhard3 --workers 4 --gpu 0 \
  --official-root scripts/parity/official
```

1. `load_specs` 读入并封套校验，记下 `identity_sha256` 与每行 `spec_sha256`；
2. 待跑集 = `selected` 且 `rollout` 缺失或 `status != ok` 的行（重跑已 ok 须 `--redo`）；
3. 分批写 `jobs.json / sampling.json / specs.json` 到 `--output/_rounds/round_NN/`，子进程 `scripts/parity/train_split_runner.py`，环境变量 `ROBOMME_ENV_PACKAGE=robomme_hard` 让 worker 选包。worker 内：`gym.make(task, sampling_config=…, native_episode_spec=row.spec, …)` → 套 `RobommeRecordWrapper` → 官方 `_planner_classes` / `_execute_tasks`（vendor 的 `generate_dataset.py`）→ h5 / mp4；
4. **递补**：某行 failed，从同格 `selected=false` 候选按 `candidate` 升序取下一个置 `selected=true` 加入下一轮；失败行保留、`rollout.status="failed"`；
5. **回写**（全部批次结束后一次）：重读 `--specs`，重算 `identity_sha256`，与第 1 步相等才继续；只改 `selected` 与 `rollout`；临时文件 + `os.replace`；写后再 `load_specs` 核 `identity_sha256` 未变；`--output` 下 `.lock`（`O_EXCL`）保证同一 jsonl 同时只有一个回写进程；
6. `results.jsonl` 照旧写 `--output` 供报告与回归，但身份来源是 jsonl。

递补闭合点：评估侧只取 `rollout.status=="ok"` 的行，合作者跑到的就是真正生成成功的那一局。中断恢复按 `_rounds/*/results.json` 复用已完成局，不重复消耗预算。

### 5.3 jsonl 结构（`schema="hard-specs/2"`）

```json
{"task": "BinFill", "tier": "xhard3", "candidate": 3, "episode": 3, "seed": 12300003, "attempt": 0,
 "selected": true, "spec": {…}, "spec_sha256": "…",
 "rollout": {"status": "ok", "final_candidate": 3, "h5_sha256": "…", "frames": 412, "mp4": true,
             "duration_s": 83.1, "env_package": "robomme_hard", "package_fingerprint": "…", "written_at": "…"}}
```

数轴式理解：一行 = 「签」+「跑的结果」两段。

```text
  ├── spec 块（第一阶段封存，identity_sha256 覆盖，定死）──┤├── selected / rollout 块（第二阶段回写，不进哈希）──┤
  task tier candidate seed attempt spec spec_sha256          selected  rollout{status final_candidate h5_sha256 …}
```

header 键：`schema`、`difficulty`、`tasks`、`per_env`、`runtime`、`seed_rule`、`select_indices`、`sampling_config`（全文）、`sampling_config_sha256`、`recovery_rule`、`identity_source`、`run_id`、`record`、**新增** `draw_stats`、`base_fingerprint`、`hard_fingerprint`、`env_package`、`identity_sha256`；删 `drafts_sha256`。`identity_sha256` 只盖 header 里除 `identity_sha256 / draw_stats / record` 外的键 + 每行 `{task, tier, candidate, seed, attempt, spec, spec_sha256}`。`rollout` 第一阶段不存在（不是 `null`）；failed／timeout 行同样写全部键、计数显式零值。

### 5.4 原三档对拍归 `scripts/parity/`

`train_split_parity.py run --paths B` 用主仓代码（切到 `robomme_hard`）按官方 seed 生成 easy/medium/hard 16×3×3=144 局，`compare` 与 S0 基线逐局 h5 sha；V1′ 由 `hard_parity.py run --env-package robomme_hard` 执行（1 条冒烟 + 143 条，30 分钟无进展／4 小时硬上限）。原三档不走抽签→回注。

## 六、验收（查什么 / 怎么查 / 过了说明什么 / 判定行）

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| `src/robomme` 逐字节同官方 | §3.4 守卫脚本 | G1；上游合并零 diff | `UPSTREAM_BYTES=PASS commit=1fadc0ec files=<n> diff=0 borrowed=<m> net=<ok\|skipped>` |
| vendor 四文件同源 | `sha256sum` 与隔离树同名文件比 | 执行代码来源未变 | `VENDOR_SAME=PASS files=4` |
| 绝对 import 无漏改 | AST 扫描 | 无静默回头用官方旧逻辑 | `ABS_IMPORT=PASS … stray=0` |
| 注册表归属 | 三种导入顺序（只 hard；官方→hard；hard→官方）各起一进程 | G5 | `REGISTRY_OWNER=PASS envs=16 owner=robomme_hard` |
| 包内 jsonl 就是 S4 那份 | 新收窄口径重算 `identity_sha256` 与由 `v6-02` 同口径重算值相等；`spec_sha256` 逐行相等 | 分发规格未变 | `SPECS_IDENTITY=PASS tiers=4 rows=550 selected=165` |
| 冻结脚本未破 | `cmp` 三脚本；`ls -1 scripts/*.py \| wc -l` = 5 | G4 | `EVAL_PY_UPSTREAM=PASS ENTRIES=5` |
| 评估入口只差 import 与循环 | `diff … \| grep -c '^[<>]'` ≤ 12 | G4 | `EVAL_HARD_DIFF=PASS lines=<n>` |
| 两阶段入口没改抽签口径 | `freeze_specs.py --dry-run` 与 `v5_generation.plan_pipeline` 命令逐项对照 | 抽签语义不变 | `FREEZE_DRYRUN_EQUIV=PASS` |
| 第一阶段只落一份文件 | 单任务单档 1 候选 smoke，运行后工作区与 `artifacts/` 无新文件 | G6 上半 | `FREEZE_ONLY_JSONL=PASS files_written=1` |
| 回写不破坏封存 | 对 smoke jsonl 跑第二阶段，`identity_sha256` 不变、`rollout` 齐全 | G6 下半 | `ROLLBACK_WRITE=PASS spec_hash_unchanged=1` |
| 原三档逐位 | V1′ | G2 | `NATIVE_REGRESSION_HARD=PASS compared=144 sha_equal=144` |
| xhard 回注复现 | 每档每任务取 `candidate` 最小的 ok 行 1 条（13+13+13+16），回注 reset，导出 spec 与冻结值逐字段比 | 回注通道在新包下逐值一致 | `HARD_RESET_REPLAY=PASS resets=55 mismatch=0` |
| xhard 产物逐位 | 16 任务各 1 局、档位轮换（xhard4-only 三任务固定 xhard4），h5 sha 与 `final-delivery.json` 比 | 新包在 xhard 下产物同 S4 | `HARD_ROLLOUT_SHA=PASS compared=16 sha_equal=16` |
| 合作者入口可用 | `evaluation_hard.py` 限 1 任务 1 档 1 局 | G4 | `HARD_EVAL_SMOKE=PASS` |

为什么 sha 能逐位：生成用的执行代码（vendor 的官方 `generate_dataset.py`）、worker、seed、回注规格与 S4 完全相同，唯一变量是包名；S3 已证明同机同代码下 h5 逐位可复现。

## 七、实施步骤表

| 阶段 | 内容 | 判据 | 改 `src/robomme` | commit |
|---|---|---|---|---|
| 0 只读准备 | fetch 官方 `1fadc0ec` 并核 tree；生成 `UPSTREAM.json`；vendor 四文件 + `SOURCE.json`；绝对 import 全量扫描 | `VENDOR_SAME`；清单落 `docs/validation/newtask-v6/hard-split/stage0.md` | 否 | 12.205 |
| 1 建 `robomme_hard` | 按 §3.1 复制／shim／子类；迁四份 jsonl 到新 schema；`pyproject.toml` | `REGISTRY_OWNER`、`ABS_IMPORT`、`SPECS_IDENTITY`、单局 `make_env_for_episode` 冒烟 | 否 | 12.206 |
| 2 `scripts/` 重组 | 按 §3.5；`train_split_worker.py` 加 `ROBOMME_ENV_PACKAGE`；`tests/` 机械替换只保证可收集 | `FREEZE_DRYRUN_EQUIV`、`FREEZE_ONLY_JSONL`、`ROLLBACK_WRITE`、`EVAL_PY_UPSTREAM`、`EVAL_HARD_DIFF`、`--collect-only` 错误 0 | 否 | 12.207 |
| 3 回退 `robomme` | 官方树覆盖 `src/robomme/**`（含 `env_metadata`），删 9 个新增 utils，train 元数据换回 100 条 | `UPSTREAM_BYTES`；阶段 1、2 判定行重跑仍 PASS | **是（P2 逐文件批准）** | 12.208 |
| 4 回归 | 第二部分 §三预算 | `NATIVE_REGRESSION_HARD`、`HARD_RESET_REPLAY`、`HARD_ROLLOUT_SHA`、`HARD_EVAL_SMOKE` | 否 | 12.209 |
| 5 留档 | `robomme_hard/README.md`、`scripts/README.md`、`parity/README.md`、`docs/validation/newtask-v6/hard-split/`、`AGENTS.md` P1 五入口、`CLAUDE.md` 核实清单 | `git diff --check` | 否 | 12.210 |

阶段 3 放在 2 之后、4 之前：先让 `robomme_hard` 在 `robomme` 还带改动时独立跑通，再回退 `robomme`，阶段 3 失败时只回滚一个 commit。实施完成后实测结果以子节追加在本表之后，不改写原计划。

---

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

- R1 `src/robomme/**` 从阶段 3 起是官方原样，不放任何自有文件（`UPSTREAM.json`、README 补充一律放 `robomme_hard/` 或 `docs/`）。
- R2 `scripts/parity/official/` 四文件不改；shim 不含逻辑（≤ 3 行非注释行，守卫脚本检查）。
- R3 `identity_sha256` 覆盖范围（第一部分 §5.3）落地后不变；变更即换 `schema` 版本并重跑 `SPECS_IDENTITY`。
- R4 第二阶段回写只改 `selected` 与 `rollout`；同一 jsonl 同时只许一个回写进程；`--force` 覆盖 jsonl 起跑前 `ls -ld` 并在回复里复述目标路径。
- R5 同进程导入 `robomme_hard` 后 16 个 id 归它；需要官方行为另开进程。
- R6 reset／rollout 计数按 §三逐项记入留档，冒烟与重跑都计入；超出先停再补授权（P3）。
- R7 `injection-dev` 目录名保留连字符、各入口路径直跑并自行 `sys.path.insert`；若实测 import 混乱须回来请示改名，不自行改。
- R8 `tests/` 本轮只做 `from robomme.` → `robomme_hard.` 机械替换，判据仅 `--collect-only` 错误 0；留档列出被替换文件并标「未验证语义」（E-10）。
- R9 commit 只 add 本阶段文件；阶段 4 起跑前 HEAD 冻结，结果以子节追加；工作区他人在途改动一律不碰，实施时以当时 `git status --short` 为准。
- R10 `src/robomme/` 的任何改动（阶段 3）先列「文件 / 改什么 / 为什么」清单交用户逐文件批准（P2）。

## 一、逐阶段、逐文件改动清单

### 1.1 阶段 0（只读，不改仓库跟踪文件之外的东西）

| 动作 | 命令 / 产物 | 判定 |
|---|---|---|
| 取官方快照 | `git fetch https://github.com/RoboMME/robomme_benchmark 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`；`git rev-parse FETCH_HEAD^{tree}` 与 `1d4c1369…` 对照，记入 `stage0.md`（不等则两值都记，`SOURCE.json` 以 commit 为准） | — |
| `UPSTREAM.json` | `robomme_files` 用 `git ls-tree -r FETCH_HEAD -- src/robomme` 列文件后逐个 `git cat-file blob \| sha256sum`；`borrowed` 按第一部分 §3.1 清单；`manifest_sha256` 按 §3.4 算法 | 文件就绪 |
| vendor | `git show FETCH_HEAD:scripts/data-generation/<f>` × 4 → `scripts/parity/official/scripts/data-generation/`；`SOURCE.json`{`url, commit, tree, path, files{sha256}, vendored_at`}；与 `artifacts/…/official-src/scripts/data-generation/<f>` 逐个 `cmp` | `VENDOR_SAME=PASS files=4` |
| 绝对 import 扫描 | AST 遍历 `src/robomme/**.py`，收集 `from robomme.… import` 与 `import robomme.…`，按借用清单分 keep／retarget 两列写 `stage0.md` | 清单落盘 |
| 官方 builder 类方法盘点 | `git show FETCH_HEAD:src/robomme/env_record_wrapper/episode_config_resolver.py` 列全部 `def`，核对 `evaluation.py` 依赖项（盲区①） | 记入 `stage0.md` |

### 1.2 阶段 1：`src/robomme_hard/`

| 文件 | 来源 | 改什么 |
|---|---|---|
| `robomme_env/<Task>.py` × 16 | `cp src/robomme/robomme_env/<Task>.py` | `@register_env("<id>")` → `@register_env("<id>", override=True)`；按 §3.2 规则改绝对 import |
| `robomme_env/__init__.py` | cp | 追加 `ENV_IDS = ("BinFill", …)` 16 元组，顺序同 import 顺序 |
| `robomme_env/utils/` 改过 8 + 新增 9 + `__init__.py` | cp | 按 §3.2 规则改绝对 import（`subgoal_planner_func.py`、`vqa_options.py` 各有一处） |
| `robomme_env/utils/<借用>.py` × ~15 | 新写 | 三行 shim；文件名与官方一致（`planner-ref.py`、`vqa_options copy.py` 不可 import，不建） |
| `env_record_wrapper/RecordWrapper.py` | cp | `step()` 内延迟 `from robomme.robomme_env.utils.vqa_options import …` → `robomme_hard.`；h5 attrs 加 `env_package`、`package_fingerprint` |
| `env_record_wrapper/OraclePlannerDemonstrationWrapper.py` | cp | 顶部 `from robomme.robomme_env.utils.vqa_options` → `robomme_hard.` |
| `env_record_wrapper/hard_specs.py` | 从 `scripts/parity/v4_specs.py` 下沉 | 搬 `HEADER_KEYS`、`canonical_json`、`digest`、`identity_sha256`（改为收窄口径）、`seed_rule_for`、`_known_seed_rule`、`load_specs`、`RUNTIME`；新增 `base_fingerprint()` / `hard_fingerprint()`；`source_fingerprint` 不符 `warnings.warn`；`draw`/`freeze` 不搬 |
| `env_record_wrapper/hard_builder.py` | 新写 | 第一部分 §4.2 两条路；`_bind(env_id, header, rows)` 只取 `task==env_id and selected and rollout.status=="ok"`，按 `candidate` 升序；`from_v4_specs` 保留为薄包装 |
| `env_record_wrapper/__init__.py` | 新写 | 自家三项 + 借用 re-export（第一部分 §3.1） |
| `__init__.py` | 新写 | 顺序：读 `UPSTREAM.json` → `sys.modules` 检查官方是否已导入（warn）→ 临时把 `mani_skill` logger 提到 ERROR → `from . import robomme_env` → 恢复 logger → 遍历 `ENV_IDS` 断言归属 → 对 `borrowed` 做 cheap 校验（warn） |
| `env_metadata/xhard{1..4}/specs.jsonl` | `scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl` 迁移 | 行 `difficulty`→`tier`；header 加 `draw_stats`（从 v6-02 对应 drafts 的 `record` 或置空并注明）、`base_fingerprint`、`hard_fingerprint`、`env_package`；`schema` → `hard-specs/2`；旧 `identity_sha256` 存 `record.legacy_identity_sha256`，按新口径重算 |
| `env_metadata/train/` 4 份 | mv 自 `src/robomme/env_metadata/train/`（阶段 3 才真正从 `robomme` 删） | 不改 |
| `UPSTREAM.json`、`README.md` | 阶段 0 产物 / 阶段 5 写 | — |
| `pyproject.toml` | 现有 | `packages = ["src/robomme", "src/robomme_hard"]` |

### 1.3 阶段 2：`scripts/`

| 文件 | 来源 | 改什么 |
|---|---|---|
| `injection-dev/_extract.py` | 新写 | `from scripts.parity.train_split_config import extract_task`；`build_sampling(tasks, release="newtask-v6") -> dict` |
| `injection-dev/_draw.py` | `parity/v4_specs.py` draw 侧 | `_draw_one`、`draw_task`、`_draw_worker_init`、`_parse_gpus`、`parse_task_max_reset_attempts`、`seed_for`、`env_kwargs`、`recovery_mode`；输入 sampling dict 不读文件；返回 rows + `draw_stats` |
| `injection-dev/_freeze.py` | `parity/v4_specs.py` freeze 侧 | `cmd_freeze` 逻辑改为纯函数 `freeze(rows, header_parts) -> (header, rows)`；哈希用 `hard_specs` |
| `injection-dev/freeze_specs.py` | 新写 | CLI（第一部分 §5.1）；串 ①②③；`--dry-run`；原子写；AST 自检「除 `--out` 外无写文件调用」 |
| `injection-dev/_rollout.py` | `parity/v4_rollout.py` | `_run_batch` 的 runner 命令加 `env=ROBOMME_ENV_PACKAGE`；输入改 jsonl 行；新增 `write_back(specs_path, rows_delta)`（第一部分 §5.2 第 5 步）；`.lock` |
| `injection-dev/generate_h5.py` | 新写 | CLI（§5.2）；`--redo`；调 `_rollout` |
| `injection-dev/_report.py` | `parity/v5_generation.py` report 侧 | 输入改为 jsonl `rollout` 块 + `results.jsonl`；去 drafts 依赖；输出 `HARD_GENERATION=REPORT …` |
| `injection-dev/site/` | `git mv parity/{v6_site.py,v6_site.html,v6_site_catalog.py,v6_candidate_values.py,v6_tier_monotone.py,v6_v0_native_definitions.py,v6_gt_lengths.py,v6_gt_lengths.json}` | 内部 import 路径随之改 |
| `parity/train_split_worker.py` | 现有 | `pkg = os.environ.get("ROBOMME_ENV_PACKAGE", "robomme")`，四处 `import robomme…` 改 `importlib.import_module(f"{pkg}…")`；唯一非机械改动 |
| `parity/train_split_runner.py` | 现有 | `--official-root` 默认 `scripts/parity/official`；把 `ROBOMME_ENV_PACKAGE` 透传给子进程 |
| `parity/hard_parity.py` | 现有 | `--official-root` 默认改 vendor；`.official_tree` 校验改读 `official/SOURCE.json["tree"]` |
| `parity/upstream_guard.py` | 新写 | 第一部分 §3.4；`--manifest-md` 输出 README ③表 |
| `parity/hard_regression.py` | 新写 | 子命令 `reset-replay`（55 次，复用 `_draw._draw_one` 的 make+reset 与 `v4_eval._binding` 的比对）、`rollout-sha`（16 局，调 `generate_h5.py` 到临时 `--output`，与 `final-delivery.json` 比）、`eval-smoke` |
| `evaluation_hard.py` | `cp scripts/evaluation.py` | 三处改动（第一部分 §4.1） |
| 删除 | `git rm` `parity/{v4_specs,v4_rollout,v5_generation,legacy_keep_list}.py`、`scripts/eval/`、`configs/newtask-v4/`、`configs/newtask-v5/`、`configs/newtask-v6/{sampling_config.json,v6-01/}`；`rm -r` 未跟踪 `scripts/injection/`、`parity/results/` | `ls -1 scripts/*.py` = 5 |
| `tests/**` | 现有 | `sed` `from robomme.` → `from robomme_hard.`、`import robomme.` → `import robomme_hard.`（R8） |

### 1.4 阶段 3：`src/robomme/`（P2）

先出清单交批：`git diff --name-status FETCH_HEAD HEAD -- src/robomme`（预期 26 M + 9 A + 4 M json）。批准后 `git checkout FETCH_HEAD -- src/robomme/` + `git rm` 9 个新增 utils；`git status --short -- src/robomme` 与清单逐项对上才 commit。

## 二、闸门总表

见第一部分 §六（判定行已内联，此处不重复）。补充判定实现位置：`UPSTREAM_BYTES` / `VENDOR_SAME` / `ABS_IMPORT` → `upstream_guard.py`；`REGISTRY_OWNER` → `tests/lightweight/test_registry_owner.py`（三种顺序各 `subprocess` 一进程）；`SPECS_IDENTITY` → `hard_specs` 加载 + `v6-02` 同口径重算脚本（阶段 1 一次性，命令与输出进 `stage1.md`）；`FREEZE_*` / `ROLLBACK_WRITE` → `injection-dev` 入口的 `--self-check`；`HARD_*` → `hard_regression.py`。

## 三、预算与 runbook

| 项 | reset | rollout | 授权状态 |
|---|---|---|---|
| `FREEZE_ONLY_JSONL` smoke | 1 | 0 | 本轮申请 |
| `ROLLBACK_WRITE` smoke | 0 | 1 | 本轮申请 |
| 阶段 1 单局 `make_env_for_episode` 冒烟 | 0 | 1（计入 `HARD_EVAL_SMOKE`） | 本轮申请 |
| `NATIVE_REGRESSION_HARD` | 0 | 144 | 已授权（0926 计划 D 项） |
| `HARD_RESET_REPLAY` | 55 | 0 | 本轮申请 |
| `HARD_ROLLOUT_SHA` | 0 | 16 | 本轮申请 |
| **合计** | **56** | **162（新增 18）** | 阶段 4 起跑回复复述「reset 56 / rollout 18」即为执行授权 |

runbook（阶段 4，全部进 tmux，会话名前缀 `hs-`，日志 `artifacts/newtask-v6/hard-split/logs/<名>.log`，每份日志一个 Monitor，过滤词含 `NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT|EXIT_CODE=|Traceback|=PASS|=FAIL`）：

```bash
# V1′
uv run --no-sync python -m scripts.parity.hard_parity run --env-package robomme_hard \
  --manifest scripts/configs/newtask-v3/subset_manifest.json --base artifacts/newtask-v6/v1/base \
  --official-root scripts/parity/official --output artifacts/newtask-v6/hard-split/v1-hard --workers 1 --gpus 0
uv run --no-sync python -m scripts.parity.hard_parity compare --output artifacts/newtask-v6/hard-split/v1-hard
# xhard 侧
uv run --no-sync python -m scripts.parity.hard_regression reset-replay --out artifacts/newtask-v6/hard-split/reset-replay
uv run --no-sync python -m scripts.parity.hard_regression rollout-sha --delivery artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json --out artifacts/newtask-v6/hard-split/rollout-sha --gpu 1
uv run --no-sync python -m scripts.parity.hard_regression eval-smoke --task BinFill --tier xhard4
```

FAIL 处置：只记证据链与候选修法，不放宽、不重试挑成功；`--env-package robomme` 对照侧须另批。

## 四、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | shim 借用触发官方 16 环境注册，日志 16 条 `Override registered env` | 接受；`__init__` 只在自家注册段临时压 `mani_skill` logger |
| 2 | 官方 `main` 前进，借用文件变化悄悄改 xhard 行为 | `UPSTREAM.json` 钉 commit，守卫 FAIL 即停；升级 commit 是显式动作，重跑全部闸门 |
| 3 | 父类 `__init__` 白名单绕行在官方改签名时断裂 | 属风险 2 的升级流程 |
| 4 | `identity_sha256` 收窄后旧值不可直接比 | 同口径重算判定，旧值存 `record.legacy_identity_sha256` |
| 5 | 两个 `generate_h5.py` 同时回写同一 jsonl | `.lock`（`O_EXCL`）+ 读前／写前哈希核对 |
| 6 | `tests/` 机械替换后假 PASS／假 FAIL | R8，留档标注 |
| 7 | 连字符目录名与 `-m` 不兼容 | R7 |

## 五、盲区诚实清单

①官方 `episode_config_resolver.py` 是否还有 `evaluation.py` 依赖的其他类方法——阶段 0 读官方树核实；②借用的 `MultiStepDemonstrationWrapper` 内部 `from ..robomme_env.utils import planner_denseStep` 解析到官方 utils，与 `robomme_hard` 环境同进程是否有状态耦合——阶段 1 冒烟观察；③`final-delivery.json` 可比的 h5 sha 是否覆盖全部 16 任务——不足则 `HARD_ROLLOUT_SHA` 的 `compared` 按实际减少并写明；④`v6-02` 的 drafts 已删，`draw_stats` 迁移时只能置空并在 header `record` 注明「历史批次无抽签统计」。

## 六、留档与 commit 纪律

- 每阶段一个 commit（12.205～12.210），subject 接体例，body 按 `AGENTS.md` 第 11 条六项；只 `git add` 本阶段文件。
- 判定行原文与命令进 `docs/validation/newtask-v6/hard-split/stage<n>.md`；阶段 4 的 reset／rollout 逐项计数表进 `stage4.md`。
- 实施完成后实测结果以子节追加在第一部分 §七步骤表之后，不改写原计划。
- `robomme_hard/README.md` 必含：①一句话与 V1′ 判定行原文；②四档定稿表（从 `0925-newtask-release-v6-plan.md` 第一部分 §三逐字搬）；③复制／借用／子类／新增逐文件表（`upstream_guard.py --manifest-md` 生成，内联结果与命令）；④机制：`sampling_config` 两块、`SpecRecorder` 导出／回注、jsonl 封套、seed 偏移、注册表归属；⑤使用：`evaluation_hard.py` 三行示例、`override_metadata_path`、两阶段生产命令（注明不随包分发）；⑥红线 R1～R5；⑦`dataset_for_parent="test"` 绕行说明。
