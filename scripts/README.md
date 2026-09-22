# scripts/ 说明

本文只讲三件事：

1. **生成数据的两阶段**——用到哪些 jsonl，值是怎么注入进环境的（第一节）；
2. **控制哪些**——十六个环境各自能调什么参数、现值多少、在哪被消费（第二节）；
3. **eval 怎么传入**——评估侧怎么把身份与配置喂进环境、指标落哪，以及新值数据目前**传不进去**的缺口（第三节）。

> 原 `scripts/INJECTION.md` 已并入本文第一节，文件已删除；历史文档里指向它的链接对应本文第一节。
> 旧版本 README 里的十五份难度字典表、A/B/C 四路历史对拍五项结论、schema 3 多 GPU 并行校准五轮报告不再收录，
> 它们留档在 [docs/validation/newtask-v2/](../docs/validation/newtask-v2/README.md)（尤其 `20260909-actions-v3`、
> `20260909-schema3-parallel-v2`、`20260917-injection-refactor` 三轮证据包）与 [newtask-v3](../docs/validation/newtask-v3/)。

---

## 〇、scripts/ 的布局

**顶层只放五个入口，别的一律收进子目录。**（2026-09-22 用户定：「只保留这五个入口，以后新增要和用户沟通」，
已写进 [AGENTS.md](../AGENTS.md) 强制规则第 12 条。）

| 顶层入口 | 干什么 |
| --- | --- |
| [generate_dataset_newseed.py](generate_dataset_newseed.py) | **主入口**，三种模式：生成数据集 / `--extract-config` 核对导出原值快照 / `--merge-only` 按需合并 |
| [seed_layout.py](seed_layout.py) | seed 公式 `offset + env_code × env_block + episode × 100 + attempt`、难度循环、16 任务规范序。纯标准库，被主入口导入 |
| [dataset_replay.py](dataset_replay.py) | 回放已生成的数据集（与上游 main 逐字节相同） |
| [evaluation.py](evaluation.py) | 评估示例（与上游 main 逐字节相同） |
| [run_example.py](run_example.py) | 单环境运行示例（与上游 main 逐字节相同） |

| 子目录 | 装什么 |
| --- | --- |
| [injection/](injection/) | 新值注入链路：`candidates/`（阶段一，造候选）、`rollout/`（阶段二，实跑）、`hf_release.py`（HF 发布）。见第一节 |
| [parity/](parity/README.md) | 对拍链路：`train_split_*.py` 六件（原始 train 五路逐位对拍）＋ `compare_vs_original.py` / `calibrate.py` / `tolerance.json`（vs 原版发布集的容差校验）＋ `comparator_fixtures.py`。见第一节 1.5 |
| [configs/](configs/) | 冻结的配置与快照：`newtask-v2/`（注入契约、原值快照、交付配置）、`newtask-v3/`（官方身份 manifest、原值快照、历史报告留档） |

> 2026-09-22 的一次整理把六个 `train_split_*.py` 与 `comparator_fixtures.py` 从顶层移进 `parity/`
> （该目录由 `test-vs-original/` 改名而来），把 `hf_release.py` 移进 `injection/`；文件名一律未改。
> `parity/` 下的脚本既可按路径直跑，也可 `python -m scripts.parity.<模块>`；
> `seed_layout` 仍在顶层，各入口自行把 `scripts/` 接上 `sys.path`。

---

## 第一节　生成数据的两阶段：用什么 jsonl、怎么注入

### 1.0 先分清：仓库里有两条注入链路

两条链路共用同一套「外部造值、环境只消费」的思路，但覆盖范围、输入文件和使用的 kwarg 都不同，读代码时不要混。

> **链路甲已决定废弃**（2026-09-22 用户拍板）。后续的新值注入在链路乙上实现，
> 并沿用甲的 jsonl 封套契约（见 1.2～1.4）；甲的代码与已进 Git 的产物作为历史证据原样保留、不删不改。
> 方案见 [NEWTASK_RELEASE_V4_PLAN.md](../NEWTASK_RELEASE_V4_PLAN.md)。本节描述的是**当前代码的实际状态**。
>
> **退役口径（V4 步 1，2026-09-22 起生效）**：
> - `scripts.injection.candidates` 与 `scripts.injection.rollout` **不再发起任何新运行**（不造新候选、不跑新 rollout），
>   新值一律走链路乙的 xhard 档（V4 第三节的抽签／冻结／实跑三步）；
> - 甲的代码、`artifacts/injection/**`、已进 Git 的 `candidates.jsonl` / `results.jsonl` **原样保留、不删不改**（红线 N6），
>   相关测试（`tests/_shared/contract_builder_fixture.py`、`test_injection_delivery.py` 等）也不改；
> - `injection/hf_release.py` 维持现状；
> - 环境里甲的旧通道（`episode_spec` kwarg 与"传了规格就跳过抽样"的分支）保留不动，V4 不复用。

| | 链路甲：新值注入 | 链路乙：原始 train 五路对拍 |
| --- | --- | --- |
| 入口 | `scripts.injection.candidates` + `scripts.injection.rollout` | `scripts/parity/train_split_parity.py` |
| 覆盖环境 | 4 个（`BinFill`／`RouteStick`／`VideoUnmaskSwap`／`VideoRepick`，即 `candidates/io.py` 的 `_ENV_CODES`） | 16 个全部 |
| 用哪个 kwarg | `sampling_config` + `episode_spec` | `sampling_config` + `native_episode_spec` |
| 身份来源 | 自己按 `seed_for()` 公式造 | 官方 metadata 逐条读，**不重算 seed** |
| 冻结输入 | `candidates.jsonl`（一行 header + 每行一条候选） | `subset_manifest.json` / `train_manifest.json`（json，不是 jsonl） |
| 目的 | 把原随机取值换成新值，做更难的布局 | 证明拆接口与原值回注一个数都没改 |

环境侧三个 kwarg 现在**16 个任务都有**（每个任务模块的 `__init__` 形参里各有一份 `sampling_config=None`、
`episode_spec=None`、`native_episode_spec=None`），三者相互独立：

- `sampling_config`：**每 task 一份**，只替换候选与区间的**来源**（类级 `configs` 字典与散落的字面常量 → 实例副本），
  抽样表达式、`torch.randint` / `torch.rand` 的运算元与顺序原样保留；
- `episode_spec`：**每 episode 一条**，直接定死这一局的具体值（board 的 xy 与 yaw、button 中心、每个 cube 的
  xy 与 yaw、生成顺序、配额、动作序列、`dynamic` 等），命中的量不再走随机流——链路甲用它；
- `native_episode_spec`：走 `robomme_env/utils/episode_spec.py` 的 `SpecRecorder`，
  **传 `None` 时是只读导出**（把原随机分支上真实取到的值记下来）、**传冻结规格时是原值回注**——链路乙用它，
  各任务源码里注明「与旧注入通道相互独立，本记录器只挂在原随机分支上」。

三者都不传时，链路与改动前逐字相同，`DEFAULT_PARITY` 就靠这一条成立。

### 1.1 链路甲第一阶段：造候选，冻成 candidates.jsonl

```text
scripts/configs/newtask-v2/{injection_contract_v3,native_sampling,delivery_400}.json
        |  scripts.injection.candidates（纯 CPU，不导入仿真）
        v
artifacts/injection/<run-id>/candidates/candidates.jsonl   ← 冻结快照，唯一环境输入，进 Git
        |  header 行内嵌 sampling_config / runtime / 来源指纹
        |  每条候选行内嵌该 episode 的完整 spec
        |
        |  scripts.injection.rollout（execute_scope 只读取、校验、转发）
        v
generate_dataset_newseed 的 EpisodeJob（sampling_config / episode_spec 各一份 deepcopy）
        v
gym.make(task, seed=..., difficulty=..., sampling_config=..., episode_spec=...)
        v
任务 __init__ → _load_scene → _initialize_episode 上的各个取值点岔路
        v
artifacts/injection/<run-id>/rollout/results.jsonl   ← 唯一结果表，进 Git
```

候选由纯 CPU、不导入仿真的进程生成并做碰撞筛查，所以「造值」与「跑仿真」彻底分离。
`candidates.jsonl` 冻结后进 Git，不再读外部配置覆盖快照；显式提供配置时只允许断言相等。

**header 行（21 个必选 + 4 个可选）**，字段集合由 `candidates/io.py` 的 `_HEADER_KEYS` / `_HEADER_OPTIONAL` 定义：

| 分组 | 字段 |
| --- | --- |
| 标识 | `record`（固定 `"header"`）、`run_id`、`candidate_schema_version`、`spec_schema_version`、`purpose`（`delivery` / `smoke`） |
| 生成器 | `generator_seed`（须等于契约里的值）、`generator_version` |
| 来源指纹 | `contract` / `contract_sha256`、`delivery_config` / `delivery_config_sha256`、`sampling_file_sha256`（采样配置整文件）、`sampling_config_sha256`（只对 `parameters` + `positions` 的运算元，`configs` 先按本次难度集合过滤） |
| 内嵌快照 | `sampling_config`（整份采样配置全文，`schema_version` 必须为 3）、`delivery_config_snapshot`（`per_env_target` / `margin` / `extra_candidates` / `groups[]` …）、`runtime` |
| 计数与溯源 | `groups`、`candidates`（须与实际行数一致）、`group_provenance`（每个 `"<task>/<difficulty>"` 记 `derived_seed`、`sampling_config_sha256`、`blocks` 等） |
| 身份 | `identity_sha256` |
| 可选 | `roles`、`parent_run_id`、`parent_candidates_sha256`、`evidence_source` |

两个机制要点名：

- **`runtime` 必须逐字等于 `io.py` 里的 `RUNTIME` 常量**——`{"layout": "train", "kwargs": {"obs_mode": "rgb+depth+segmentation",
  "control_mode": "pd_joint_pos", "render_mode": "rgb_array", "reward_mode": "dense"}}`。`generate_dataset_newseed`
  在消费候选时还会硬比对这一项，保证环境构造参数不因换了运行编号而漂。
- **`identity_sha256`** 是「去掉全部可变字段（`_MUTABLE`：`run_id`、`role`、`error_type`、`screening`、`roles`、
  `evidence_source` 等）的 header + 排序后同样去可变字段的全部候选行」的摘要。角色回填、重跑改 `run_id` 都不会动它，
  改了任何一个规格值就会变。

**候选行（12 个字段，全必选）**，集合由 `_CANDIDATE_KEYS` 定义：

| 字段 | 约束 |
| --- | --- |
| `record` | 固定 `"candidate"` |
| `task` / `difficulty` / `episode` | 三者为主键，须与内层 `spec` 的同名字段一致 |
| `block` | `= episode // 100` |
| `seed` | `= _ENV_CODES[task] * 1000 + episode * 100`（`io.py` 的 `seed_for()`） |
| `spec_sha256` | 身份散列，须同时等于 `spec["spec_sha256"]` 与 `record_sha256(spec)`（摘要时排除 `spec_sha256` 与 `collision`） |
| `spec` | 该 episode 的完整规格；`project_spec()` 返回其深拷贝，**绝不补键或删键** |
| `split` | `"train" if episode < groups[(task, difficulty)]["run_episodes"] else "test"` |
| `role` | ∈ `{pending, primary, spare, failed, unused}`；train 分片不得为 `unused` |
| `error_type` | 非 `failed` 时必须为 `null` |
| `screening` | 九键：`geometry`（必须 `PASS`）、`collision_initial`、`collision_sweeps`、`min_g_m`、`evidence_origin`（`generated` / `reconstructed`）、`count_unit`、`candidates_tried`、`accepted`、`rejected_before_accept`；`RouteStick` 走 `count_unit="not_applicable"` + 三个 null 的特例 |

一条真实候选（`artifacts/injection/20260912-contract-v3-10/candidates/candidates.jsonl` 的第 2 行，为可读性展开并截断）：

```json
{"record": "candidate", "task": "BinFill", "difficulty": "easy", "episode": 0,
 "block": 0, "seed": 4000, "split": "train", "role": "primary", "error_type": null,
 "spec_sha256": "05fee817…",
 "screening": {"geometry": "PASS", "evidence_origin": "reconstructed", "count_unit": "object_proposal",
               "candidates_tried": 10, "accepted": 5,
               "rejected_before_accept": {"contact": 0, "geometry": 5, "numerical_boundary": 0, "uncertified": 0},
               "collision_initial": null, "collision_sweeps": null, "min_g_m": null},
 "spec": {"task": "BinFill", "difficulty": "easy", "episode": 0,
          "layout": {"board": {"xy": [-0.020671134581938193, -0.14911099603529915], "yaw_deg": 15.82872727714144},
                     "button_xy": [-0.24090228580683687, 0.19811769630071246],
                     "cubes": [{"color": "blue", "color_index": 0, "object_id": "cube_blue_0",
                                "xy": [-0.19911465696333294, -0.020226357107070908], "yaw_rad": 4.4418427774738385}, …],
                     "dynamic": false},
          "objects": {"colors_present": …, "initialize_color_order": …, "spawn_total": …, "spawn_count": …,
                      "target_pool": …, "target_count": …, "put_in_total": …},
          "actions": [{"pick": "cube_blue_0", "put_in": true}, {"pick": "cube_blue_4", "put_in": true}],
          "sampling_cells": {"board_x": [1, 4], "board_y": [1, 2], "board_yaw": [8, 9], "button_x": [0, 9], …},
          "spec_sha256": "05fee817…"}}
```

读写两端共用的守门是 `io.py` 的 `_keys()`：它对 header 与每一行做**精确集合比对**，缺字段、多出未知字段一律报错。
这就是「`candidates.jsonl` 是唯一环境输入」能成立的技术原因——没有第二处能悄悄塞进一个值。

### 1.2 链路甲第二阶段：rollout 只读取、校验、转发

顶层 `python -m scripts.injection.rollout` 的流程是 `import_candidates`（需要时复制候选副本并把 `role` 全部重置为
`pending`）→ `RunStore` 取运行级独占写锁 → `recover` → `invoke_generator` → `run_reset` → `generate_windows` → `report`。
真正喂给生成器的是拉起的子进程里的 `execute_scope`，它只做这些事，**一个值都不造**：

1. `load_candidates`——内含 `validate_candidates` 的全量校验（封套版本、完整键集、内外身份一致、旧规格散列）
   与采样快照的**源码指纹核对**；
2. 比对 `scope.json` 里记的 `identity_sha256` 与 header 的是否一致，身份变了直接拒；
3. `validate_sampling_config(header["sampling_config"])`——采样配置**从 header 快照取，不再读磁盘**；
4. 逐条二次核验：`split == "train"`，且 `seed` 等于 `get_layout("train").seed(task, episode, 0)`；
5. `project_spec(candidate)` 取规格（深拷贝，不补键不删键）→ `validate_episode_spec(...)`（生成器侧第二份独立校验）；
6. 组 `EpisodeJob`（`sampling_config` 与 `episode_spec` 各一份 `deepcopy`）→ `_run_jobs(..., max_attempts=1)`。

`max_attempts=1` 要单独记住：注入链路**固定单次尝试**，不会靠换 seed 重试把一条失败的规格试成功。
`SpecBindingError` 与 `BinCollisionError` 在生成器里被归入「任务性失败」，只是为了不被连续非任务性失败的计数器
当成代码 bug，它们同样不触发换 seed。

生成器侧只多了转发这一步，其余与原版逐字相同：

```python
if job.sampling_config is not None: kwargs["sampling_config"] = job.sampling_config
if job.episode_spec  is not None: kwargs["episode_spec"]  = job.episode_spec
base_env = gym.make(job.task, **kwargs)
```

父进程读一次配置、每个 job 各 `deepcopy` 一份独立副本，因此同一进程里的下一局不会被上一局改到。

### 1.3 链路甲用到的全部 jsonl

| 文件 | 谁生成 | 内容 | 谁消费 |
| --- | --- | --- | --- |
| `candidates/candidates.jsonl` | `candidates/io.py` 的 `write_candidates`（rollout 侧回填 `role` 时也会重写） | 见 1.1 | `load_candidates` ← `execute_scope`、`RunStore`、`generate_dataset_newseed` |
| `rollout/results.jsonl` | `RunStore.publish`（原子写） | **唯一结果表**，38 键并集：身份、`ok`/`outcome`/`failure_class`/`error_type`、`h5_path`/`h5_sha256`/`h5_bytes`/`timestep_count`、`video`、`injection_evidence`/`runtime_checks`、`phases`/`wall_s`/`peak_rss_mb`/`bound`、`role`/`counted`/`delivered` 等。`kind`／`split`／`spec_sha256` 由 `normalize` 强制覆盖；`role`／`counted`／`delivered` 由 `assign_roles` 派生；`outcome` 是七类互斥中文值：通过／规格拒绝／碰撞拒绝／实际对象·动作不符／规划失败／超时／未运行 | `rollout/report.py`、`windows.py`、`parity.py` |
| `rollout/logs/attempts/h5-XXXX/episode_results.jsonl` | `generate_dataset_newseed` 的 `_run_jobs` 边跑边写 | worker 原始记录，一行一次 attempt | `terminal_cache` 重放 → `normalize` → `merge` |
| `rollout/logs/attempts/reset-XXXX/episode_results.jsonl` 及其 `batches/<task>/<difficulty>.jsonl` | `rollout/reset_check.py` | test 分片的 make / reset / close 三段结果 | 同上（`kind="reset"`） |
| `candidates/logs/rejections.jsonl` | 候选筛查的 `ObservationCollector` | 每次被拒的提案：`object_id`／`trial`／`proposal`／`reason`／`detail` | 候选侧统计与 `group_stats.json` |

同一份快照的 test 分片由 `reset_check.py` 消费，**只做 make / reset / close，证明能建环境**——不能当成
能完成任务或能出 HDF5。策略侧未来入口同样只认这一份读取契约。

### 1.4 链路甲的落地命令与产物布局

两阶段各一条入口，均在仓库根目录用 `uv` 启动：

```bash
uv run --no-sync python -m scripts.injection.candidates --run-id <新运行编号> \
  --contract scripts/configs/newtask-v2/injection_contract_v3.json \
  --delivery-config scripts/configs/newtask-v2/delivery_400.json
```

```bash
uv run --no-sync python -m scripts.injection.rollout --run-id <编号> --tier <每卡worker数> --gpus 0,1
```

| 阶段 | 参数 |
| --- | --- |
| 一（candidates） | `--run-id`（必填）、`--sampling-config`、`--contract`、`--delivery-config`、`--seed`（须等于契约 seed）、`--purpose {delivery,smoke}`、`--groups`（形如 `BinFill/easy`）、`--blocks`（**只有 `--purpose smoke` 能给**）、`--reconstruct-run`（只读旧运行重算补证）、`--no-figures` |
| 二（rollout） | `--run-id`（必填）、`--candidates`、`--purpose {delivery,parity,smoke}`、`--groups`、`--episodes`、`--episode-range`（`start:end` 半开）、`--skip-done`、`--wall-limit-h`、`--tier`（= worker 数）、`--gpus`、`--reset-limit`、`--label`、`--no-figures` |

```text
artifacts/injection/<run-id>/
├── candidates/
│   ├── candidates.jsonl          ← 冻结快照（进 Git）
│   ├── DISTRIBUTION.md  figures/<task>/<difficulty>/*.png
│   └── logs/{plan_meta,check_result,quota_report,group_stats}.json  rejections.jsonl
└── rollout/
    ├── results.jsonl             ← 唯一结果表（进 Git）
    ├── ROLLOUT.md  WINDOWS.md  figures/
    ├── <task>/<difficulty>/{hdf5_files/, videos/, record_dataset_*_metadata.json}
    └── logs/attempts/{h5-XXXX,reset-XXXX}/{scope.json, episode_results.jsonl, summary.json, …}
```

**已有候选禁止覆盖**：阶段一发现已存在 `candidates.jsonl` / `rollout/results.jsonl` / `logs/plan_meta.json` 直接拒绝，
失败重试一律换新编号。正式大规模仿真前先跑单组、单条、单 worker 的冒烟。
运行编号、续跑与恢复协议、角色与配额规则、图表口径等运维细节见
[INJECTION_REFACTOR_PLAN.md](../INJECTION_REFACTOR_PLAN.md) 与
[20260917-injection-refactor](../docs/validation/newtask-v2/20260917-injection-refactor/README.md)。

两处如实标注的边界：

- `scripts/injection/hf_release.py` 本轮冻结，仍读迁移前的 `delivery_manifest.json` + `feasibility/*/episode_results.jsonl`；
  「改为读 `results.jsonl` 的 `role`」是**未做事项**，代码里不存在。
- `--skip-done` 在 rollout 的执行路径里**没有任何读取点**（终态始终复用），是纯声明式开关。

### 1.5 链路乙：原始 train 五路对拍的两阶段

入口是 `scripts/parity/train_split_parity.py`，子命令按方案步骤排：

| 子命令 | 干什么 | 产物 |
| --- | --- | --- |
| `freeze-identities` | 从官方 `dataset-gen` 固定提交逐字读十六份 train metadata，冻结 1600 条来源身份与 144 条运行子集；只读、不启动仿真 | `scripts/configs/newtask-v3/`（进 Git）下的 `train_manifest.json`、`subset_manifest.json`、`official_train/record_dataset_<task>_metadata.json` 与 `sources.json` |
| `freeze-history` | 冻结官方历史生成报告原文与散列，按子集投影可比字段 | `configs/newtask-v3/history/{generation_report.json,generation_report.md,history_projection.json,reference_set_verification.json}` |
| `run` | 按 A1／A2／B／C／D 五路运行选定身份 | `artifacts/train-parity/<run>/<路>/<Task>_episode_<k>/` |
| `merge` | 把某一路的逐 episode 产物合并成官方格式 | 供官方比较器消费 |
| `compare` | 只读比较五路产物，HDF5 全字段逐位对拍 | `<run>/compare/{h5_pairs.jsonl, summary.json}` |

**这条链路的冻结输入是 json 不是 jsonl**（`subset_manifest.json` / `train_manifest.json`），
jsonl 只出现在比较结果 `compare/h5_pairs.jsonl`——每行一对文件，记 `left`／`right`／`sha_equal`／`field_mismatch`／
`missing_left`／`missing_right` 与每处 mismatch 的路径、左右 dtype／shape、首个不同元素的展平索引与取值。

每一路的每条身份各落一个目录，里面除 `hdf5_files/` 与 `videos/` 外还有三份核验件：

- `episode_spec.json`——`SpecRecorder` 在原随机分支上**只读导出**的本局规格（C 路产出，D 路回注用）；
- `rng_trace.json`——随机流记录，供 P3 `RNG_PARITY` 比每次调用的次序、参数、shape、dtype、结果与前后状态；
- `spec_replay.json`——D 路回注时的消费核验，记 `value_points`／`consumed`／`unused`／`mismatches`，
  这就是 G4 `SPEC_BINDING=PASS missing=0 unused=0 mismatch=0` 的证据文件。

身份的红线：严格取官方 `(task, episode, seed, difficulty)`，**不用 `SeedLayout.base_seed` 公式替换实际 seed**，
不重编号 episode，失败不换 seed、不补样本。同目录的配套工具还有 `train_split_runner.py`（A 路隔离运行器，
用官方固定源码跑官方 `_worker`，不打补丁）、`train_split_worker.py`（C／D 路 worker，官方 `_worker` 的最小镜像，
只多传两个显式输入）、`train_split_config.py`（从每个环境的 `native_blocks(cls)` 提取原值快照，不创建环境、
不抽随机数）、`train_split_comparison.py`（官方比较器的稀疏范围适配）、`train_split_audit.py`（G2／G3／C1 的
离线核对）、`comparator_fixtures.py`（G5 夹具）。

### 1.6 `episode_spec` 是怎么定死值的：三种手法

**手法 A：关掉被调工具的随机开关，直接喂最终值。** button 的注入即属此类：规格给的是**最终中心**，
调用 `build_button` 时传 `center_xy=spec["layout"]["button_xy"]` 并把 `randomize` 置为 `False`，
于是 `build_button` 内部不抽随机数，其余（缩放、travel、连杆、OBB）全走原路径。

**手法 B：反解回原公式的中间变量，位置计算行本身不动。** board 的规格存的是最终位置，注入时用
「最终 xy − `base_position`」反解出原公式里的 `x_var` / `y_var`，`yaw` 直接取规格值，
后面构造旋转四元数与调用 `build_board_with_hole` 的那几行与原路径共用，一字未改。

**手法 C：给底层 spawn 工具加固定值通道，短路整个拒绝采样循环。** `spawn_random_cube` 有 `fixed_xy` / `fixed_yaw`
参数：传了就直接用该位姿建方块，不进入「三次 `torch.rand` + 避让判定」的重试循环。为杜绝两份创建代码漂移，
原来内联在循环里的创建段被提取成共用的 `_finalize_cube`，两条路径共用。固定值路径不抽随机数，所以原本
`generator is None` 就报错的强制检查放宽为「`generator` 为空**且**没给固定值才报错」。运行时不再做几何可行性判定
——可行性已在冻结候选之前用同一套 OBB 判据筛过。

**顺序与配额同样归规格管。** 原来用 `torch.randperm` 打乱方块生成顺序，传规格时改为按 `spec["layout"]["cubes"]`
的列表次序重排（并借 `color` 与 `color_index` 对上 `object_id`）；`_initialize_episode` 里决定颜色遍历顺序的那次
`randperm` 由 `spec["objects"]["initialize_color_order"]` 顶掉；每色的 `spawn_count` / `target_count` 直接由规格给出。

### 1.7 三条硬约束与随机流语义

`gym.make` 的 kwargs 被任务 `__init__` 的显式形参接住，第一时间 resolve 成实例私有副本赋给 `self._sampling`
与 `self._episode_spec`。`_resolve_sampling_config` 与 `_resolve_episode_spec` 只做三件事——
**类型与键集校验 → `copy.deepcopy` → 返回**，全程不调用任何随机数。三条硬约束及其原因：

1. **必须显式取走。** `BaseEnv.__init__` 是纯显式形参、没有 `**kwargs`，漏接一个未知 kwarg 直接 `TypeError`。
2. **必须 deepcopy。** gymnasium 会把传入 kwargs 字典的**引用**存进 `env.unwrapped.spec.kwargs`，多个环境会共享同一个
   dict；而且构造期内部 reset 与外层 reset 会各重建一次工作态，两次都要从同一份原始规格重建。任务内只改私有副本，
   绝不碰调用方传进来的原对象。
3. **必须落在 `torch.Generator()` 创建之前、任何随机数调用之前。** 在这里多抽或少抽一次随机数，会平移其后全部取值。

不传 `sampling_config` 时 fallback 到任务模块顶层的 `NATIVE_SAMPLING` 常量，并把类级难度字典 `configs` 也复制进
实例副本。这份常量同时是 `generate_dataset_newseed.py --extract-config` 的 AST 提取目标，因此「提取到的原值」与
「实际跑的默认值」永远是同一处，不存在双真值。配套四条口径：JSON 里存的是**运算元**（`base_position` / `scale` /
`subtract`）不是折算好的区间（`0.15 + (u*0.2 - 0.2)` 与 `-0.05 + u*0.2` 的 float64 位模式实测不同）；整数区间照旧
交给原 `torch.randint(low, high + 1)`；配置值一律以 Python 标量参与运算，不包成 `torch.tensor`（否则会把
`rotate_points_random`、`build_button` 内部的 float32 路径提升成 float64）；类级 `configs` 的读点必须**全部**改成读
实例副本，漏改任一处会产生「不传配置时相同、传配置时才发散」的隐性双真值。

**随机流语义：规格覆盖的量由规格决定，不刻意对齐。** 规格分支不会为了对齐随机流而补抽一次废弃的随机数。
后果是明确的、被接受的：规格没有覆盖的量（如 `inject_fail_grasp` 的抽取）会因随机流位置平移而与原版不同，
这些量不在验收范围内。

seed 的入口没有变：`seed` 仍是 `gym.make` 的 kwarg，由任务 `__init__` 的显式形参接住并自建
`torch.Generator().manual_seed(seed)`；`record_env.reset()` 不传 seed。若把 seed 改挂到 `reset(seed=...)`，
会同时改变 ManiSkill 的 `_main_seed` / `_episode_seed` 并触发 `fork_rng` 分支，原链立即失守。

**注入是否真的生效，有两套证据。** 静态证据：传了规格时，`_load_scene` 末尾把「创建输入 vs 创建后 actor 实际位姿」
写进 `self._injection_evidence`（请求的 xy 与 yaw、实际的 `p` 与 `q`、`spec_sha256`、配额等），只读位姿、不改状态、
不抽随机数。动态证据：运行期算出来的东西必须与规格预写的一致，不一致就抛 `SpecBindingError`——典型是
`VideoUnmaskSwap._verify_swap_binding`，用同一套扫描语义独立复算一次最近邻，发起者或搭档与规格对不上直接失败，
**禁止换搭档**；`VideoRepick` 同理。

---

## 第二节　控制哪些：十六个环境各自能调什么

### 2.0 两块怎么分，以及那道必过的守卫

每个环境的 `sampling_config` 分两块，由该环境模块顶层的 `native_blocks(cls)` / `_native_decision(cls)` 产出：

| 块 | 装什么 | 谁定义 |
|---|---|---|
| `decision` | **以后允许改的参数**（数量、次数、区域策略、干扰物…） | `_native_decision(cls)`，多数由类属性 `config_easy/medium/hard` 推导 |
| `native` | **原随机规则与几何常量**（锚点坐标、间距、抽样器的运算元、拒绝判据…） | 模块级常量 `NATIVE_SAMPLING` 的 `parameters` / `positions` |

**`utils/sampling_config.py::assert_native_decision` 是第一道闸**：它把传入的 `decision` 与
`_native_decision(cls)` 的返回值做 `json.dumps(sort_keys=True)` **逐键全等比对**，不等就抛
`SamplingConfigError`。所以**改参数不是"从外部传个新配置进去"就行**——必须同步改
`_native_decision()` 的返回结构（或改它依赖的类属性），否则外部传入当场被拒。

两个环境还有**额外的独立铁闸**：
- `VideoUnmaskSwap::_resolve_sampling_config` 对 `parameters.object_selection` 与 `parameters.swap_selection`
  做 `json.dumps` 全等比对 ⇒ 不能从外部改 `pickup_selected_indices`，只能改源码字面量；
- `RouteStick::_resolve_sampling_config` 要求 `parameters.walk` 除 `direction.threshold` 外完整保留原版。

`_resolve_sampling_config` 必须在任何 `torch.Generator()` 与随机调用**之前**执行，它本身不抽随机数。

### 2.1 逐环境可控字段与现值

难度列按 easy / medium / hard 排（有第四档的单独注明）。**「消费点」列写的是这个值实际在哪被读**——
有几个键读的位置和你以为的不一样，见 2.2。

#### Counting 族

| 环境 | 字段 | 块 | 现值 | 消费点 |
|---|---|---|---|---|
| **BinFill** | `layout_mode` | decision | `"native_dynamic"` | `_resolve_sampling_config` **硬守卫，非此值直接报错** |
| | `configs[难度].color` | decision | 1 / 2 / 3 | `_load_scene`（`randperm(3)` 的切片长度） |
| | `configs[难度].spawn_cubes` | decision | `[4,6]` / `[8,10]` / `[10,12]`（闭） | `_load_scene` |
| | `configs[难度].put_in_color` | native | `[1,1]` / `[1,2]` / `[2,3]`（闭） | `_load_scene` |
| | `configs[难度].put_in_numbers` | decision | `[1,3]` / `[2,4]` / `[3,5]`（闭） | `_load_scene` |
| | `dynamic` | native | `randint(0,2)` 转 bool，**generator 播种后第一次抽样** | `__init__` |
| | 方块区域 | native | 中心 `[-0.1,0]`、半边长 `[0.2,0.25]`、`min_gap` **调用点写死** `cube_half_size` | `_load_scene` |
| **PickXtimes** | `color[难度]` | decision | 1 / 3 / 3 | `_load_scene` |
| | `number_range[难度]` | decision | `[1,3]` / `[1,3]` / `[4,5]`（闭） | **`__init__`**，不是 `_load_scene` |
| | `target_cube_position_policy` | decision | 中心 `[-0.1,0]`、半边长 `0.2` | `_load_scene` |
| | `goal_position_policy` | decision | **与上同值同区域** | `_load_scene` |
| | `distractor` | decision | `None` | **全仓无消费点** |
| **SwingXtimes** | `color[难度]` | decision | 1 / 3 / 3 | `_load_scene` |
| | `number_range[难度]` | decision | `[1,3]` / `[1,2]` / `[3,3]`（闭） | `__init__` |
| | `distractor` | decision | `None` | **无消费点** |
| | `color_pool` | native | 红/蓝/绿 | `_load_scene` **真被消费**（与 PickXtimes 相反） |
| | 摆动阈值 | native | `distance 0.03`、`z 0.12`、`height 0.1` | `step` 的迟滞判定 |
| **StopCube** | `move_interval_choices` | decision | `[60, 80, 120]`，等概率抽；**值越小越快** | `_initialize_episode` |
| | `stop_time_range` | decision | `low=2, high_exclusive=6` ⇒ 实际 `[2,5]` | `_initialize_episode` |
| | 目标/按钮/颜色 | native | 目标 xy 各 `uniform(-0.1,0.1)`；方块色 `rand(3)`（**本来就是任意 RGB**） | `_load_scene` |
| | 路线旋转 | native | `uniform(-30,30)` 度 | `_initialize_episode` |

> **StopCube 没有难度字典**：类里无 `configs` / `config_*`，`self.difficulty` 被赋值但**全文件无消费点**。

#### Permanence 族

| 环境 | 字段 | 块 | 现值 | 消费点 |
|---|---|---|---|---|
| **VideoUnmask** | `bin_layout_policy.count[难度]` | decision | 3 / 5 / 15 | `_load_scene` |
| | `bin_layout_policy.region_*` | decision | 中心 `[0,0]`、半边长 `0.2` | `_load_scene` |
| | `pick_count[难度]` | decision | 1 / 1 / 2 | `_load_scene`；但 **`task_goal` 读的是类属性 `configs[...]['pick']`** |
| | `min_gap_factor` / `max_trials` | native | `2`（⇒ `min_gap=0.04`）/ `256` | `_load_scene` |
| | `step_bin_scan` | native | **15，容器遍历上限** | `step` |
| | `reveal_window` | native | `[0, 64]` | `step` |
| | `distractor` | decision | `None` | **无消费点** |
| **ButtonUnmask** | 同 VideoUnmask | | 同上 | 另有按钮 `center_xy [-0.2,0]`、`randomize_range [0.1,0.1]`、`scale 1.5` |
| | 构造期抽样 | native | `randint(1,6)`，**不决定任何行为、只占随机流位置**（红线 R8） | `__init__` |
| **VideoUnmaskSwap** | `configs[难度].bin` | **native** | 3 / 4 / 4（xhard 4） | `_load_scene` |
| | `configs[难度].swap_min/max` | **native** | `[1,2]` / `[1,2]` / `[2,3]`（xhard `[4,5]`） | `__init__` |
| | `configs[难度].pick_min/max` | **native** | `[1,2]` / `[1,1]` / `[2,2]` | `__init__` |
| | `swap_count_range`、`pick_count_range`、`swap_speed_multiplier`、`distractor` | decision | 有键 | **全是死键，一处消费都没有** |
| | `object_selection.pickup_selected_indices` | native | `[0,1]` | `_load_scene`；**受额外铁闸保护** |
| | 容器锚点 | native | 三角/直线/四点，局部半边长 `0.07`、整体旋转 `[0,180]` **弧度** | `_load_scene` |
| **ButtonUnmaskSwap** | `swap_count_range[难度]` | **decision** | `[1,2]` / `[1,2]` / `[2,3]` | `__init__`（**与 VideoUnmaskSwap 相反**） |
| | `pick_count_range[难度]` | **decision** | `[1,2]` / `[1,1]` / `[2,2]` | `__init__` |
| | `bin_count[难度]` | **native** | 3 / 4 / 4 | `_load_scene` |
| | `swap_window` `{start_step:64, duration_steps:50}` | native | 有键 | **声明了但没被消费**（`_refresh_swap_schedule` 用的是六处字面量） |
| | `swap_path` `{lane_offset, smooth, keep_upright}` | native | 有键 | **同样未被消费**，`step` 里是内联字面量 |

#### Reference 族

| 环境 | 字段 | 块 | 现值 | 消费点 |
|---|---|---|---|---|
| **PickHighlight** | `spawn_count[难度]` | decision | 3 / 4 / 6 | `_load_scene` |
| | `highlight_count[难度]` | decision | 1 / 2 / 3 | `_load_scene` 与 `step` |
| | `cube_region` | decision | 中心 `[-0.1,0]`、半边长 `0.2` | `_load_scene` |
| | `min_gap_factor` | native | `2` ⇒ `min_gap=0.04` | `_load_scene` |
| | `color_pool` / `color_draw` | native | 红/蓝/绿，**逐块独立抽、可重复** | `_load_scene` |
| | `highlight_window` | native | `{start 10, end 100, simultaneous: True}` | `step`（**所有目标共用同一窗口、同时高亮**） |
| **VideoRepick** | `configs[难度].cube` | native | 3 / 3 / **hard 无此键** | `_load_scene` |
| | `configs[难度].swap_min/max` | native | `[1,2]` / `[2,3]` / `[0,0]`（xhard `[4,5]`） | `__init__` |
| | `num_repeats` | **native** `parameters.num_repeats` | `low=1, high_exclusive=4` ⇒ 1/2/3 | `__init__` |
| | `num_repeats_range` | decision | 有键 | **死键，改了不生效也不报错** |
| | `hard_spawn_rounds` | native | `5`（每轮红蓝绿各一 ⇒ 15 块） | `_load_scene` hard 分支 |
| | easy/medium 锚点 | native | 三角/直线/四点，局部半边长 `0.07` | `_load_scene` |
| | hard 区域 | native | 中心 `[-0.1,0]`、半边长 `[0.2,0.25]` | `_load_scene` |
| **VideoPlaceButton** | `targets[难度]` | decision | 3 / 4 / 4 | `_load_scene` |
| | `swap[难度]` | decision | False / False / True | `_load_scene` |
| | `additional_place[难度]` | decision | 全 `False` ⇒ **`target_2`/`target_3` 分支永不执行** | `_load_scene` |
| | `demo_object_count` | decision | `1` | **死键**（审计文件里明文豁免："扩到 2 块时才会出现消费点"） |
| | `demo_return_policy` | decision | `"native_random_goal_site"` | 演示末尾放**随机** `goal_site`，不是原位 |
| | `color[难度]` | **native** | 1 / 3 / 3，`cubes_per_color=1` ⇒ **场上方块数 = color 值** | `_load_scene` |
| **VideoPlaceOrder** | 同上，`targets` 全档 4 | | | `button_task_index = k*2+2`（假设每个 visit 恰两条任务） |

#### Imitation 族

| 环境 | 字段 | 块 | 现值 | 消费点 |
|---|---|---|---|---|
| **MoveCube** | `demo_layout.peg_position_policy` | decision | `base_y_abs 0.2`、`jitter_span 0.1` ⇒ 根点 `x ∈ [-0.05,0.05]`、`y ∈ [±0.15,±0.25]` | `_load_scene` |
| | `demo_layout.cube_position_policy` | decision | `center_span 0.2`、`center_offset -0.1`、`region_half_size 0.05` | `_load_scene` |
| | `execution_layout.*` | decision | **与 demo 逐键同值，但各抽一套** | `_load_scene` |
| | `peg_yaw_range` | decision | `span π/2`、`offset π/4` ⇒ **±45°** | `_load_scene` |
| | `cube_rejection` | native | `max_trials 128`、`min_distance_factor 5` | `_load_scene` |
| | `peg_size` | native | `length 0.1`、`radius 0.01`（两次 rand 乘 0，**必须保留**） | `_load_scene` |
| **InsertPeg** | `peg_count` | decision | `3` | 只在一次 `randint(0, peg_count)` 用过，**结果立刻被 `overridden_to=0` 覆盖** |
| | `peg_offsets` | decision | `[0.1, 0, -0.1]` | **杆数实际由它的长度决定** |
| | `near_target_distractor` | decision | `None` | **无消费点**（V3 预留键） |
| | `peg_yaw_range` | decision | `half_span_deg 45` ⇒ **±45°** | `_initialize_episode` |
| | `peg_sampling` | native | `x ∈ [-0.2,0.2]`、`y ∈ [-0.3,0.3]`、离孔板 > `radius*6`、杆间 > `length*1.5`、`max_attempts 512` | `_initialize_episode` |
| | `box` | native | xy 各 `±0.1`、yaw `90°±20°` | `_initialize_episode` |
| **PatternLock** | `grid[难度]` | decision | 3 / 4 / 5（正方形网格，**无 xhard**） | `_load_scene` |
| | `length[难度]` | decision | `[2,4]` / `[3,5]` / `[4,8]`，语义是**节点数**不是段数 | `_load_scene` |
| | `path_selection.max_attempts` | native | `1000`，耗尽**不报错**、用最后一条 | `_load_scene` |
| | 网格几何 | native | 中心 `[-0.1,0]`、间距 `0.1` | `_load_scene` |
| **RouteStick** | `configs[难度].length` | decision | `[2,3]` / `[4,5]` / `[4,7]`（xhard `[8,10]`），语义是**段数 L** | `_load_scene` |
| | `configs[难度].backtrack` | decision | False / False / True | `_load_scene` |
| | `walk` | native | 节点 `[0,2,4,6,8]`、邻居 `[-1,1]`、端点强制回退 | **除 `direction.threshold` 外受铁闸保护** |
| | `yaw_deg` | native | `rand*60 - 30` ⇒ ±30° | `_load_scene` |
| | `tcp_trail.end_offset_steps` | native | **40**（官方原值，已恢复） | `step` |

> **MoveCube 与 InsertPeg 没有难度分档**：两个类都无 `configs` / `config_*`，`self.difficulty` 算出来之后
> 全文件无读取点。`env_metadata/train/` 里它们每条 record 都带 `difficulty` 字段，但**环境不读**。

### 2.2 改之前要知道的五个陷阱

1. **死键**——有键、改了不生效、还不报错：`VideoRepick.decision.num_repeats_range`（真正读的是
   `native.parameters.num_repeats`）、`VideoPlace*.decision.demo_object_count`、
   `VideoUnmaskSwap.decision.{swap_count_range, pick_count_range, swap_speed_multiplier}`、
   六个环境的 `decision.distractor`、`ButtonUnmaskSwap.native.{swap_window, swap_path}`。
2. **读写方向相反**——`VideoUnmaskSwap` 的 swap/pick 读 **native** 的 `parameters.configs`，
   `ButtonUnmaskSwap` 恰好读 **decision**；`VideoUnmask` / `ButtonUnmask` 的 pick 在 `_load_scene` 读 decision、
   在 `task_goal` 读**类属性**。
3. **同一个值有两处真值**——`PickXtimes` 的颜色池：`_load_scene` 用硬编码字面量，而
   `NATIVE_SAMPLING.parameters.color_pool` 声明了却从未被读（`SwingXtimes` 则是真读）。
   `BinFill` 的 `min_gap`：`positions.cubes.min_gap` 只是个说明字符串，运行时读的是调用点写死的字面量。
4. **抽样区间闭/半开不统一**——写在难度字典里的 `[min,max]` 由 `torch.randint(low, high+1)` 消费、**含两端**；
   而 `VideoRepick.num_repeats` 与 `StopCube.stop_time_range` 用的是 `high_exclusive`、**不含上界**。
5. **生成失败多半是静默的**——`spawn_random_cube` / `spawn_random_bin` 放不下就 `RuntimeError`，
   而环境侧普遍 `except: break` 或 `logger.debug` 且不补抽 ⇒ **实际数量可能少于设定值而没有任何信号**。
   实测 `VideoUnmask` 的 `bin=15` 只放得下 9~12 个。少数例外是显式抛错：`SwingXtimes` 抛
   `SceneGenerationError`、`InsertPeg` 的杆位采样耗尽 512 次抛 `RuntimeError`。

### 2.3 不开放的东西

物体尺寸、材质、碰撞几何、相机、速度、交换时序、失败恢复、成功阈值都属于原实现，没有开放为可配。
`cube_half_size`（= `0.02`）是个特例：它同时是四任务 `min_gap` 的实际值、容器半边长的收缩量、
方块可行域的收缩量——不是纯尺寸参数，**被冻结为派生输入记进快照，但不开放为可配**。

源码里的若干旧问题（`RouteStick` 结尾无条件覆盖难度、创建后从未使用的局部 generator、无调用者的死代码、
`VideoRepick` 永不命中的 `region4` 分支、与实际不符的注释等）**原样保留、没有顺手修**，只在快照与计划文档里记录。

## 第三节　eval 怎么传入

### 3.1 上游 main 怎么说

上游 [RoboMME/robomme_benchmark](https://github.com/RoboMME/robomme_benchmark) main 的 README 在 Evaluation 一节
**不给命令行**，只给一段 Python：把 `BenchmarkEnvBuilder` 的 `dataset` 设成 `"test"`，
`make_env_for_episode(episode_idx)` 拿环境，`env.reset()` 后取 `info['task_goal'][0]`，之后逐步 `env.step(action)`；
train 100 条、val／test 各 50 条，**所有 seed 固定**。提交排行榜那一节把「eval scripts」指向 `scripts/evaluation.py`。
上游 `scripts/` 只有 `evaluation.py`、`run_example.py`、`dataset_replay.py` 三个文件，本仓库 `scripts/` 下其余内容
全是本 fork 新增。

### 3.2 环境是怎么搭起来的

唯一工厂是 `BenchmarkEnvBuilder.make_env_for_episode`，在
[src/robomme/env_record_wrapper/episode_config_resolver.py](../src/robomme/env_record_wrapper/episode_config_resolver.py)：

- **env id 就是任务名本身**，没有 `-v0` 后缀（各任务文件顶上的 `@register_env("BinFill")` 等）。
  16 个 id 的规范序写死在 `_DEFAULT_TASK_LIST`、由 `get_task_list()` 返回，**不从 metadata 自动发现**。
- **四个 env kwargs**：`obs_mode="rgb+depth+segmentation"`、`control_mode="pd_joint_pos"`、
  `render_mode`（GUI 时 `human`，否则 `rgb_array`）、`reward_mode="dense"`。
  **reward 虽然是 dense，但评估完全不用它**（`doc/env_format.md` 标注 not used，两个评估脚本都把它丢弃），
  成功率只看 `info["status"]`。
- **seed 与 difficulty 来自 metadata**：读 `src/robomme/env_metadata/{train,test,val}/record_dataset_<task>_metadata.json`
  的每条 `{task, episode, seed, difficulty}`，注入成 env kwargs——这就是 README 那句「All seeds are fixed for
  benchmarking」的实现。`get_episode_num()` 即该 task 的 episode 去重计数（train 100 / test 50 / val 50）。
- **wrapper 栈**（外层在后）：`gym.make(<Task>)` → `DemonstrationWrapper` → 动作空间 wrapper
  （`ee_pose` → `EndeffectorDemonstrationWrapper`，`waypoint` → `MultiStepDemonstrationWrapper`，
  `multi_choice` → `OraclePlannerDemonstrationWrapper`，`joint_angle` 无）→ `FailAwareWrapper`。
  **没有专门的 eval wrapper**：评估与数据生成共用同一套，区别只在 `dataset="test"` 与 `max_steps`。
  `multi_choice` 会强制打开前视相机内外参。
- **步数预算**：构造器的 `max_steps` 会 +2 存成 `max_steps_without_demonstration`，
  `DemonstrationWrapper` 只在非演示帧累加计数 ⇒ **演示阶段的帧不计入预算**，超出即 `truncated`。
- **成功判据**：`DemonstrationWrapper` 依 `info["success"]` → `terminated` → `truncated` 依次给出
  `info["status"] ∈ {success, fail, timeout, ongoing}`；底层 `info["success"]` 由各任务的 ManiSkill `evaluate()` 产出。
  异常路径由 `FailAwareWrapper` 捕获一切异常 → 返回 `status="error"` 并 terminate（IK 失败同理）。
- **录像**：环境本身不录（`DemonstrationWrapper` 里已注明不再存视频），各入口脚本自己用 `imageio.mimsave`，fps 固定 30。

### 3.3 四个入口各是什么

| 入口 | CLI | 跑什么 | 指标落哪 |
| --- | --- | --- | --- |
| [scripts/evaluation.py](evaluation.py) | **无 CLI**，配置是模块级常量 | `DummyModel` 占位策略（基准关节动作加小噪声，需替换成自己的策略），16 任务 × 50 局 = 800 局，`max_steps=1300` | **不写任何文件**，只有 stdout 的 `Success rate:`；视频落 `runs/saved_videos/` |
| [scripts/run_example.py](run_example.py) | tyro：`--dataset`、`--task-id`、`--action-space-type`、`--episode-idx` | 不跑模型，用 `generate_sample_actions` 的示例动作跑单局（或 `--episode-idx -1` 跑全部） | 无；视频落 `runs/sample_run_videos/<action_space>/` |
| [scripts/dataset_replay.py](dataset_replay.py) | tyro：`--h5-data-dir`、`--action-space-type`、`--replay-number` | 从 `record_dataset_<task>.h5` 抽动作序列重放做 sanity check（**固定用 `dataset="train"`**） | 无；视频落 `runs/replay_videos/<action_space>/` |
| [challenge_interface/scripts/phase1_eval.py](../challenge_interface/scripts/phase1_eval.py) | argparse：`--transport`、`--action_space`、`--use_depth`、`--use_camera_params`、`--host`、`--port`、`--team_id`、`--max_steps`、`--num_episodes` | 连远端策略服务器（websocket／http）取 action chunk，16 任务 × `num_episodes`，挑战赛口径 10 局／`max_steps=1500` | **唯一写结构化结果**：`challenge_results/<team_id>/metrics.json`（`per_task[env] = {avg_success, success_count, num_episodes}` ＋ `overall`）与 `progress.json`（断点续跑，带 config 指纹）；视频落同目录 `videos/` |

```bash
# 官方评估模板（改 DummyModel 为自己的策略后直接跑）
uv run --no-sync python scripts/evaluation.py

# 单局 sanity check
uv run --no-sync python scripts/run_example.py --task-id BinFill --dataset test --episode-idx 0

# 挑战赛口径评估（需另起策略服务器，见 challenge_interface/readme.md）
uv run --no-sync python challenge_interface/scripts/phase1_eval.py \
  --transport websocket --host 0.0.0.0 --port 8001 \
  --action_space joint_angle --team_id team_0000 --num_episodes 10 --max_steps 1500
```

一处如实记下的不一致：README 把排行榜指向 `scripts/evaluation.py`，但只有 `phase1_eval.py` 产出 `metrics.json`，
两者口径也不同（800 局／1300 步 vs 160 局／1500 步）。另有一条上游既有、本轮不修的边界：
`scripts/evaluation.py` 里的 `outcome` 只在正常结束分支赋值，若某任务首局走 error 分支 break 会 `NameError`，
后续局则会沿用上一局的过期值。

### 3.4 本 fork 改没改评估栈

**评估侧一行没改，而且是逐字节相同。** `scripts/evaluation.py`、`scripts/run_example.py`、`scripts/dataset_replay.py`
三份与上游 main 的 blob SHA 逐一相同（`9be77ddc…`／`8fe01bfd…`／`b3fb5e9b…`）；
`src/robomme/env_record_wrapper/` 全部 9 个文件、`challenge_interface/` 全部 10 个文件、
`src/robomme/env_metadata/test/` 16 份 metadata 也全部与上游相同。

**但不能据此认为 success rate 可以直接和原版比。** `src/robomme/robomme_env/` 下 16 个任务实现已大幅改动
（相对本地的原版镜像分支共 31 文件、+11352／−713，含新增的 `utils/bin_collision.py`、`utils/episode_spec.py`、
`utils/sampling_config.py`），任务的 `evaluate()` 与场景生成都变了 ⇒ **评估脚本一字未动，跑出来的数也不等价于原版。**
另记 `env_metadata/train/` 下四个 Unmask 系列文件各 +1802 行，**test／val 未改**。

数据生成侧的主入口是 [generate_dataset_newseed.py](generate_dataset_newseed.py)（三种模式：生成数据集 /
`--extract-config` 核对导出原值快照 / `--merge-only` 按需合并），seed 由 [seed_layout.py](seed_layout.py) 的公式
`offset + env_code × env_block + episode × 100 + attempt` 现算、不读表；这条链路与本节的评估入口互不影响。

### 3.5 新值数据目前传不进去：缺口与 V4 的接法

上面四个入口**只能评官方那套固定身份**。第一节的两条注入链路产出的数据（新值规格、`specs.jsonl`）
**现在没有任何办法喂进评估侧**——这不是"实现了但没写 jsonl"，是整条路都没接。三条实据：

1. **`BenchmarkEnvBuilder` 不认注入参数。** 在
   [episode_config_resolver.py](../src/robomme/env_record_wrapper/episode_config_resolver.py) 里 grep
   `sampling_config` / `episode_spec` / `native_episode_spec` / `candidates` / `jsonl`——**零命中**。
   它只会从 `env_metadata/{train,test,val}` 读 `(seed, difficulty)` 建环境。生成侧靠
   `generate_dataset_newseed` 转发这几个 kwarg，**评估侧没有这个转发点**。
2. **评估侧一个 jsonl 都不写。** 全仓写 jsonl 的文件都在生成/对拍侧（`scripts/injection/`、`scripts/parity/`、
   `generate_dataset_newseed.py`）。`evaluation.py` 只有 stdout，`phase1_eval.py` 写的是 json 不是 jsonl，
   而且读的也是官方 test 分片。
3. **账本里写明是故意留空的。** 注入重构阶段 0~9 的收尾记录原话：
   「策略侧第三处只定义消费契约，本仓库未新增策略实现。」

留了半截口子：`candidates.jsonl` 里确实按设计切了 test 分片（14 组 × 50 = 700 条 `test/primary`，
另有 858 条 `test/spare`），行上还带 `role` / `counted` / `delivered` 三个为评估预留的字段。
但这批 test 候选**唯一的消费者是 [reset_check.py](injection/rollout/reset_check.py)**，
而它的 docstring 第一行就把边界划死了：只做 `gym.make → reset → 读证据 → close`，
**不套录像器、不建 planner、不 step**。它证明的是"这些规格能产生环境"，跟"策略在这些局上成功率多少"
是两回事。

**[NEWTASK_RELEASE_V4_PLAN.md](../NEWTASK_RELEASE_V4_PLAN.md) 第四节规划的接法**（尚未实施）：

| 要补的 | 怎么接 |
|---|---|
| 环境构建侧 | `BenchmarkEnvBuilder` 增加一条**并列**的构建路径：给定一份 `specs.jsonl` 与一条身份，取出该局规格与 header 里的 `sampling_config`，连同 `seed` / `difficulty` 一起进 `gym.make`。**现有 metadata 路径的行为逐字不变**，新路径由显式参数开启；`runtime` 四项 env kwargs 必须与快照 header 逐字相等，不等直接拒绝起环境 |
| 评估入口 | 另起入口按 `specs.jsonl` 的分片逐局跑策略，边跑边写 `eval_results.jsonl`。**不改 `scripts/evaluation.py`**——它与上游逐字节相同这个性质要保住（见 3.4） |
| 结果表 | `eval_results.jsonl` 每行的字段与生成侧 `results.jsonl` 对齐，能按 `(task, difficulty, episode, seed, spec_sha256)` 直接 join：身份 / `status`（取自 `info["status"]`）/ `steps` / `demo_steps` / 策略指纹 / `runtime_ok` / `spec_binding` / 产物路径。汇总另落 `eval_summary.json`，字段名与 `challenge_interface` 的 `metrics.json` 对齐 |

⚠ 新入口要放进一个新建的子目录，而 [AGENTS.md](../AGENTS.md) 强制规则第 12 条要求新建子目录**先与用户沟通获准**，
该项在 V4 计划的开放项 E1 里待批。
