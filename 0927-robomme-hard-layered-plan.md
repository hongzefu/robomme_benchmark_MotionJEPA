# 0927 方案：`robomme_hard` 分层继承双包 · 两阶段生成 · 单一 jsonl（只规划不实施）

> **权威性**：本文件是 [`0926-robomme-hard-split-plan.md`](0926-robomme-hard-split-plan.md) §〇′ 的精简定稿版，只写最新口径，不保留历史决策与备选；两份冲突时以本文件为准。只规划，不实施；阶段 3 触碰 P2 须逐文件批准，阶段 4 的生成预算按 §四 一次性申请。
> **代码锚点**：本仓库 `newtaskRelease-v5` @ `66d9a424`（12.204.1）；官方 `RoboMME/robomme_benchmark` `main` @ `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`；官方隔离源码树 `artifacts/train-parity/local-smoke-01/official-src/`（`.official_tree` = `1d4c1369…`）；现行规格 `scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl`（selected 行合计 165）；S4 交付清单 `artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json`。
> **已完成、不再赘述**：V6 四档生成与 S0～S5 验收、审查修复、拆包阶段 0b 瘦身（12.200～12.203：`scripts/` 顶层四入口、删 injection／V3 容差对拍／V4 探针、V1′ 入口 `scripts/parity/hard_parity.py` 落地）。
> **commit 体例**：`<大>.<小>[.<修订>] <中文描述>`，实施从 12.205 起。

---

## 一、一句话与保证

**两个并列包**：`src/robomme/` 逐字节等于官方 `main`；`src/robomme_hard/` 只放差异（复制 16 个环境类与改过的 utils，借用没改过的，`BenchmarkEnvBuilder` 子类化），四档规格作为包数据 `env_metadata/xhardN/specs.jsonl` 随包分发。**生成链路两阶段**：`scripts/injection-dev/freeze_specs.py` 在内存里定规则→抽签→封存、只落一份 jsonl；`generate_h5.py` 只读这份 jsonl 生成 h5，跑完把结果回写进同一份 jsonl。**评估**：`HardBenchmarkEnvBuilder(env_id, dataset="xhard3")` 自己读包内 jsonl，合作者只看到这一个文件。

| 保证 | 判定行 |
|---|---|
| G1 `src/robomme/**` 与官方逐字节相同 | `UPSTREAM_BYTES=PASS commit=1fadc0ec files=<n> diff=0 borrowed=<m>` |
| G2 `robomme_hard` 跑原三档，h5 与 S0 基线 sha 逐位相同 | `NATIVE_REGRESSION_HARD=PASS compared=144 sha_equal=144` |
| G3 `robomme_hard` 跑 xhard，与 S4 交付一致 | `HARD_RESET_REPLAY=PASS resets=55 mismatch=0`、`HARD_ROLLOUT_SHA=PASS compared=16 sha_equal=16` |
| G4 评估接口与 `dataset="test"` 同形，只多认四个档名 | `EVAL_PY_UPSTREAM=PASS ENTRIES=5`、`EVAL_HARD_DIFF=PASS lines≤12` |
| G5 同进程内 16 个环境 id 的归属唯一可查 | `REGISTRY_OWNER=PASS envs=16 owner=robomme_hard` |
| G6 两阶段只依赖 jsonl，中间量不落盘，回写不破坏封存 | `FREEZE_ONLY_JSONL=PASS files_written=1`、`ROLLBACK_WRITE=PASS spec_hash_unchanged=1` |

---

## 二、文件结构

### 2.1 `src/`

```text
src/robomme/                          官方 main 原样；本仓库不再往里放任何自有文件
src/robomme_hard/
  __init__.py                         先注册自家 16 环境 → 断言注册表归属 → 借用清单 cheap 校验（§2.3）
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
                subgoal_evaluate_func）                                                  借用：三行 shim
  env_record_wrapper/
    __init__.py                       导出自家 RobommeRecordWrapper / BenchmarkEnvBuilder / hard_specs；
                                      借用 DemonstrationWrapper EndeffectorDemonstrationWrapper FailAwareWrapper
                                           MultiStepDemonstrationWrapper RRTPlanFailure 与 episode_dataset_resolver 导出项
    RecordWrapper.py                  复制（fail_safe_limit=5000 在 step() 内部字面量，无法子类改）
    OraclePlannerDemonstrationWrapper.py   复制（它 import 的 vqa_options 是改过的）
    hard_builder.py                   class BenchmarkEnvBuilder(官方 BenchmarkEnvBuilder)（§三）
    hard_specs.py                     load_specs 与封套校验、两段源码指纹
  env_metadata/
    xhard1/specs.jsonl … xhard4/specs.jsonl      四档规格（§4.3 schema）
    train/record_dataset_{ButtonUnmask,ButtonUnmaskSwap,VideoUnmask,VideoUnmaskSwap}_metadata.json   400 条
pyproject.toml                        wheel packages 加 "src/robomme_hard"
```

**借用 shim**（每个未改的 utils 一个同名文件，不含逻辑）：

```python
# 借用：robomme 同名模块的别名，逻辑以官方为准；清单见 ../../UPSTREAM.json
import importlib, sys
sys.modules[__name__] = importlib.import_module("robomme.robomme_env.utils.rpy_util")
```

**复制文件里的绝对 import 规则**：相对 import 不动；`from robomme.<path>` 且 `<path>` 在借用清单内不动；`<path>` 是改过／新增的一律改 `robomme_hard.`——AST 扫描判定 `ABS_IMPORT=PASS stray=0`。

### 2.2 `scripts/`

```text
scripts/
  seed_layout.py  dataset_replay.py  evaluation.py  run_example.py     四入口不动（后三者官方原样）
  evaluation_hard.py                                                    第五入口，与 evaluation.py diff ≤ 12 行
  injection-dev/                V6 四档生产链路，不随包分发（§四）
    freeze_specs.py  generate_h5.py                                     两个入口（路径直跑，不 -m）
    _extract.py  _draw.py  _freeze.py  _rollout.py  _report.py           内部模块
    site/                                                               v6_site*.py、v6_candidate_values.py 等只读出图
  parity/                       只做「与官方比」
    train_split_parity.py  train_split_runner.py  train_split_worker.py  train_split_config.py
    train_split_comparison.py  train_split_audit.py  comparator_fixtures.py     S0 基线对拍设施，不动
    hard_parity.py              V1′：robomme_hard 跑原三档 144 局 vs S0 基线
    upstream_guard.py           G1 守卫（纳入核心短测）
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

去向：`parity/v4_specs.py` → `_draw.py` + `_freeze.py`（`load_specs` 下沉 `hard_specs.py`）；`v4_rollout.py` → `_rollout.py`；`v5_generation.py` 的 `report` → `_report.py`、`pipeline` 废弃；`train_split_config.py` 与 runner／worker **留在 parity**，`injection-dev` 以包 import／子进程调用（生产与对拍共用同一份执行代码）；`scripts/eval/`、`legacy_keep_list.py`、空壳 `scripts/injection/`、空目录 `parity/results/` 删。

### 2.3 注册表归属（同 id 为什么不会静默出错）

`mani_skill/utils/registration.py::register_env` 实测：同 uid 二次注册在 `override=False` 时只 `logger.warn` 并**静默保留第一个**。而 `robomme/robomme_env/__init__.py` 是 16 行 `from .X import *`，任何借用 utils 都会先执行它、把官方 16 环境注册进去。三道机制：

1. 16 个副本 `@register_env("BinFill", override=True)`：只要进程 import 过 `robomme_hard.robomme_env`，16 个 id 一律归它，与顺序无关；
2. `robomme_hard/__init__.py`：官方已先导入时 `warnings.warn`；导入自家 `robomme_env` 后遍历 `ENV_IDS`，`REGISTERED_ENVS[uid].cls.__module__` 不以 `robomme_hard.` 开头即 `raise ImportError`；
3. 包指纹进产物：h5 attrs、jsonl header／`rollout` 块、builder `info` 都写 `env_package="robomme_hard"` 与 `package_fingerprint`。

红线：**同进程一旦导入 `robomme_hard`，16 个 id 全部归它；要官方原三档行为另开进程只导 `robomme`。**

### 2.4 G1 强校验

- `UPSTREAM.json`：`upstream.commit` 40 位（禁 `main`）、`robomme_files`（`src/robomme/**` 逐文件 sha256，含 `env_metadata`）、`borrowed`（借用文件 sha256）、`manifest_sha256`（剔掉本键后 canonical JSON 的 sha256）。
- `scripts/parity/upstream_guard.py`：`git fetch <url> <commit>` 后 `git diff --stat <commit> HEAD -- src/robomme` 为空（网络不可达标 `net=skipped`）；文件集合与 sha **相等**；`borrowed` 每项命中且 `robomme_hard` 侧对应文件是 ≤ 3 行非注释行的 shim。
- 导入时对 `borrowed` 做 cheap 档（字节数 + 首尾 1 MiB blake2b）校验，不符只 `warnings.warn`。
- 源码指纹两段：`base_fingerprint`（借用文件总 sha）+ `hard_fingerprint`（`src/robomme_hard/**.py` 总 sha），写 jsonl header。

---

## 三、评估过程中的 env make

### 3.1 合作者看到的

```python
from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder      # 与官方唯一不同的一行
builder = BenchmarkEnvBuilder(env_id="BinFill", dataset="xhard3", action_space="joint_angle", max_steps=1300)
for episode in range(builder.get_episode_num()):                       # 3 局：0、1、2
    env = builder.make_env_for_episode(episode)
```

`scripts/evaluation_hard.py` = `evaluation.py` 复制后只改三处：import 行；`for tier in BenchmarkEnvBuilder.get_difficulty_list():` 套在 `for task in TASKS` 外、`dataset=tier`；视频文件名加 tier。

### 3.2 builder 内部两条路

```text
dataset ∈ {train,test,val}   → 官方父类逻辑：env_metadata/<dataset>/record_dataset_<task>_metadata.json（seed/difficulty/episode）
                                → gym.make(env_id, obs_mode, control_mode, render_mode, reward_mode, seed=…, difficulty=…)
                                （train 的四个 Unmask 系任务改读 robomme_hard 包内 400 条）
dataset ∈ {xhard1..4}        → hard_specs.load_specs(env_metadata/<tier>/specs.jsonl)
                                → 取 task==env_id 且 selected 且 rollout.status=="ok" 的行，按 candidate 升序编为 episode 0..2
                                → gym.make(env_id, 同上四项 runtime, seed=row.seed, difficulty=tier,
                                           sampling_config=header.sampling_config[env_id],
                                           native_episode_spec=row.spec)
                                → 套 robomme_hard 的 RobommeRecordWrapper（fail_safe_limit=5000）
```

`native_episode_spec` 是回注：环境 reset 时抽样流程照常发生，但每个取值点用冻结值替换，原抽样只作核验（`SpecRecorder` 记 `mismatch/unused`）。`info["hard_candidate_index"]` 带原候选序号；`runtime` 四项与 header 逐字比对，不等 `raise`。

### 3.3 子类怎么写

```python
from robomme.env_record_wrapper.episode_config_resolver import BenchmarkEnvBuilder as _Upstream
class BenchmarkEnvBuilder(_Upstream):
    def __init__(self, env_id, dataset="test", action_space="joint_angle", max_steps=1300, override_metadata_path=None):
        self._hard = None
        if dataset in _HARD_TIERS:
            header, rows = load_specs(_PKG_METADATA / dataset / "specs.jsonl")
            self._hard = _bind(env_id, header, rows)
            dataset_for_parent = "test"        # 父类白名单只认 train/test/val 且官方代码不能改；父类顺手读的 test 元数据不被使用
        else:
            dataset_for_parent = dataset
        super().__init__(env_id, dataset_for_parent, action_space, max_steps, override_metadata_path)
        self.dataset = dataset
    def _resolve_metadata_path(self): ...      # train × Unmask 四任务 → 包内 400 条；其余父类
    def get_episode_num(self): ...             # hard → len(ok 行)
    def resolve_episode(self, episode): ...    # hard → (seed, tier, candidate)
    def make_env_for_episode(self, episode, **kw): ...   # hard → 3.2 的 kwargs
    @classmethod
    def get_difficulty_list(cls): return ["xhard1", "xhard2", "xhard3", "xhard4"]
```

---

## 四、数据生成链条：两阶段

### 4.1 第一阶段 `freeze_specs.py`：定规则 → 抽签 → 封存，只落一份 jsonl

```bash
uv run --no-sync python scripts/injection-dev/freeze_specs.py \
  --tier xhard3 --tasks all --candidates-per-env 10 --select 0,3,6 \
  --max-reset-attempts 30 --workers 4 --gpus 0,1 \
  --out src/robomme_hard/env_metadata/xhard3/specs.jsonl
```

| 步 | 做什么 | 实现来源 | 起环境 | 去向 |
|---|---|---|---|---|
| ① 定规则 | 对 16 任务 `import robomme_hard.robomme_env.<Task>`，读类上申报的 `native_blocks` → 该档的 decision／native 取值范围，合成 `sampling_config` dict | `train_split_config.extract_task` | 否 | 内存 → header |
| ② 抽签 | 每任务每档 10 个候选：按 seed 公式（`offset(tier) + env_code×1e5 + episode×100 + attempt`）`gym.make(task, sampling_config=…, seed, difficulty=tier, 四项 runtime)` → `reset()` → `env.unwrapped._spec.to_dict()` 记下本局全部取值；reset 失败计入 `draw_stats` | `v4_specs._draw_one` / `draw_task` | 是（只 reset） | 内存 |
| ③ 封存 | 每格选候选 0/3/6 为正式局（`selected=true`），算每行 `spec_sha256`、整份 `identity_sha256`、两段源码指纹，封套校验 | `v4_specs.cmd_freeze` | 否 | **唯一落盘** `--out` |

- 写盘：同目录临时文件 + `os.replace`；`--out` 已存在默认拒绝（`--force` 起跑前 `ls -ld`）。
- `--dry-run` 只打印三步参数，与现 `v5_generation.plan_pipeline` 的 draw／freeze 命令逐项对照（`FREEZE_DRYRUN_EQUIV=PASS`）。
- 不再产生 `sampling_config.json`、`drafts.jsonl`；判定 `FREEZE_ONLY_JSONL=PASS files_written=1`（入口内除 `--out` 外无任何写文件调用的 AST 检查 + 运行后工作区／`artifacts/` 无新文件）。

### 4.2 第二阶段 `generate_h5.py`：只读 jsonl → 回注演示 → 回写

```bash
uv run --no-sync python scripts/injection-dev/generate_h5.py \
  --specs src/robomme_hard/env_metadata/xhard3/specs.jsonl \
  --output artifacts/newtask-v6/<run>/xhard3 --workers 4 --gpu 0 \
  --official-root scripts/parity/official
```

1. `load_specs` 读入并封套校验，记下 `identity_sha256` 与每行 `spec_sha256`；
2. 待跑集 = `selected` 且 `rollout` 缺失或 `status != ok` 的行（重跑已 ok 须 `--redo`）；
3. 分批写 `jobs.json / sampling.json / specs.json` 到 `--output/_rounds/round_NN/`，子进程 `scripts/parity/train_split_runner.py --official-root … `，环境变量 `ROBOMME_ENV_PACKAGE=robomme_hard` 让 `train_split_worker.py` 选包（worker 唯一非机械改动）。worker 内：`gym.make(task, sampling_config=…, native_episode_spec=row.spec, …)` → 套 `RobommeRecordWrapper` → 官方 `_planner_classes` / `_execute_tasks`（vendor 的 `generate_dataset.py`）→ h5 / mp4；
4. **递补**：某行 failed，从同格 `selected=false` 候选按 `candidate` 升序取下一个置 `selected=true` 加入下一轮；失败行保留、`rollout.status="failed"`；
5. **回写**（全部批次结束后一次）：重读 `--specs`，重算 `identity_sha256`，与第 1 步相等才继续；只改 `selected` 与 `rollout`；临时文件 + `os.replace`；写后再 `load_specs` 核 `identity_sha256` 未变。`--output` 下 `.lock`（`O_EXCL`）保证同一 jsonl 同时只有一个回写进程；
6. `results.jsonl` 照旧写 `--output` 供报告与回归，但身份来源是 jsonl。

判定 `ROLLBACK_WRITE=PASS rows=<n> ok=<k> failed=<f> substituted=<s> spec_hash_unchanged=1`。中断恢复：按 `_rounds/*/results.json` 复用已完成局，不重复消耗预算。

### 4.3 jsonl 结构（`schema="hard-specs/2"`）

header：`schema`、`difficulty`、`tasks`、`per_env`、`runtime`（四项）、`seed_rule`、`select_indices`、`sampling_config`（全文）、`sampling_config_sha256`、`recovery_rule`、`identity_source`、`run_id`、`record`、**新增** `draw_stats`（`{task: {attempts, ok, failed, error_types}}`）、`base_fingerprint`、`hard_fingerprint`、`env_package`、`identity_sha256`。删 `drafts_sha256`。

行：

```json
{"task": "BinFill", "tier": "xhard3", "candidate": 3, "episode": 3, "seed": 12300003, "attempt": 0,
 "selected": true, "spec": {…}, "spec_sha256": "…",
 "rollout": {"status": "ok", "final_candidate": 3, "h5_sha256": "…", "frames": 412, "mp4": true,
             "duration_s": 83.1, "env_package": "robomme_hard", "package_fingerprint": "…", "written_at": "…"}}
```

- `identity_sha256` 只盖 header 里除 `identity_sha256 / draw_stats / record` 外的键 + 每行 `{task, tier, candidate, seed, attempt, spec, spec_sha256}`；**不盖** `selected` 与 `rollout`——第一阶段封存的是「签」，第二阶段回写的是「跑的结果」，两者分层。
- `rollout` 第一阶段不存在（不是 `null`）；failed／timeout 行同样写全部键（计数字段显式零值）。
- 迁移现 `v6-02`：行字段 `difficulty`→`tier`，按新口径重算 `identity_sha256`，旧值存 `record.legacy_identity_sha256`；`SPECS_IDENTITY=PASS tiers=4 rows=550 selected=165` 以「同口径重算」判定。

### 4.4 原三档对拍（`scripts/parity/`）

`train_split_parity.py run --paths B` 用主仓代码（切到 `robomme_hard`）按官方 seed 生成 easy/medium/hard 16×3×3=144 局，`compare` 与 S0 基线逐局 h5 sha；V1′ 由 `hard_parity.py run --env-package robomme_hard` 执行（1 条冒烟 + 143 条，30 分钟无进展／4 小时硬上限）。原三档不走抽签→回注。

---

## 五、闸门与预算

| 判定行 | 怎么查 | reset | rollout |
|---|---|---|---|
| `UPSTREAM_BYTES` / `VENDOR_SAME=PASS files=4` / `ABS_IMPORT` / `REGISTRY_OWNER`（三种导入顺序各一进程） / `SPECS_IDENTITY` / `EVAL_PY_UPSTREAM` / `EVAL_HARD_DIFF` / `FREEZE_DRYRUN_EQUIV` | 纯 CPU | 0 | 0 |
| `FREEZE_ONLY_JSONL` | 单任务单档 1 候选 smoke | 1 | 0 |
| `ROLLBACK_WRITE` | 对上一行 smoke jsonl 跑第二阶段 | 0 | 1 |
| `NATIVE_REGRESSION_HARD` | V1′ | 0 | 144（已授权） |
| `HARD_RESET_REPLAY=PASS resets=55 mismatch=0` | 每档每任务取 `candidate` 最小的 ok 行 1 条（13+13+13+16），回注 reset，导出 spec 与冻结值逐字段比 | 55 | 0 |
| `HARD_ROLLOUT_SHA=PASS compared=16 sha_equal=16` | 16 任务各 1 局、档位轮换（xhard4-only 三任务固定 xhard4），h5 sha 与 `final-delivery.json` 比 | 0 | 16 |
| `HARD_EVAL_SMOKE=PASS` | `evaluation_hard.py` 限 1 任务 1 档 1 局 | 0 | 1 |

**本轮新增待授权：reset 56、rollout 18**（V1′ 144 沿用已有授权）。阶段 4 起跑回复复述这两个数字即为执行授权；FAIL 不放宽、不重试挑成功。

---

## 六、阶段表

| 阶段 | 内容 | 判据 | 改 `src/robomme` | commit |
|---|---|---|---|---|
| 0 只读准备 | fetch 官方 `1fadc0ec` 并核 tree；生成 `UPSTREAM.json`；vendor 四文件 + `SOURCE.json`；绝对 import 全量扫描 | `VENDOR_SAME`；清单落 `docs/validation/newtask-v6/hard-split/stage0.md` | 否 | 12.205 |
| 1 建 `robomme_hard` | 按 §2.1 复制／shim／子类；迁四份 jsonl 到新 schema；`pyproject.toml` | `REGISTRY_OWNER`、`ABS_IMPORT`、`SPECS_IDENTITY`、单局 `make_env_for_episode` 冒烟 | 否 | 12.206 |
| 2 `scripts/` 重组 | 按 §2.2；`train_split_worker.py` 加 `ROBOMME_ENV_PACKAGE`；`tests/` 机械替换只保证可收集 | `FREEZE_DRYRUN_EQUIV`、`FREEZE_ONLY_JSONL`、`ROLLBACK_WRITE`、`EVAL_PY_UPSTREAM`、`EVAL_HARD_DIFF`、`--collect-only` 错误 0 | 否 | 12.207 |
| 3 回退 `robomme` | 官方树覆盖 `src/robomme/**`（含 `env_metadata`），删 9 个新增 utils，train 元数据换回 100 条 | `UPSTREAM_BYTES`；阶段 1、2 判定行重跑仍 PASS | **是（P2 逐文件批准）** | 12.208 |
| 4 回归 | §五预算 | `NATIVE_REGRESSION_HARD`、`HARD_RESET_REPLAY`、`HARD_ROLLOUT_SHA`、`HARD_EVAL_SMOKE` | 否 | 12.209 |
| 5 留档 | `robomme_hard/README.md`、`scripts/README.md`、`parity/README.md`、`docs/validation/newtask-v6/hard-split/`、`AGENTS.md` P1 五入口、`CLAUDE.md` 核实清单 | `git diff --check` | 否 | 12.210 |

---

## 七、红线

- R1 `src/robomme/**` 从阶段 3 起是官方原样，不放任何自有文件。
- R2 `scripts/parity/official/` 四文件不改；shim 不含逻辑（≤ 3 行非注释行）。
- R3 `identity_sha256` 覆盖范围落地后不变；变更即换 `schema` 版本并重跑 `SPECS_IDENTITY`。
- R4 第二阶段回写只改 `selected` 与 `rollout`；同一 jsonl 同时只许一个回写进程；`--force` 覆盖 jsonl 起跑前 `ls -ld`。
- R5 同进程导入 `robomme_hard` 后 16 个 id 归它；需要官方行为另开进程。
- R6 reset／rollout 计数按 §五逐项记入留档，冒烟与重跑都计入；超出先停再补授权（P3）。
- R7 `injection-dev` 目录名保留连字符、路径直跑；若实测 import 混乱须回来请示改名，不自行改。

## 八、已知盲区

①官方 `episode_config_resolver.py` 是否还有 `evaluation.py` 依赖的其他类方法，阶段 0 读官方树核实；②借用的 `MultiStepDemonstrationWrapper` 内部相对 import 解析到官方 utils，与 `robomme_hard` 环境同进程是否有状态耦合，阶段 1 冒烟观察；③`final-delivery.json` 可比的 h5 sha 是否覆盖全部 16 任务，不足则 `HARD_ROLLOUT_SHA` 的 `compared` 按实际减少并写明；④父类 `__init__` 用 `dataset_for_parent="test"` 绕白名单，官方改签名时会断，属升级官方 commit 的显式流程。
