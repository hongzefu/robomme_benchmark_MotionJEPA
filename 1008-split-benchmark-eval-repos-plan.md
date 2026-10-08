# 1008 仓库拆分方案：benchmark 仓回到「官方 + 两个文件夹」，评估独立成仓（初步，待审核）

> **权威性**：本文件是初步方案，只规划不实施；每一步都须用户单独获批，且按正本第 2 条，实施要等用户明确说「开工」。
> **代码锚点**：现仓库 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，HEAD `9c78c076`（12.540），工作区 clean。
> **官方锚点**：`RoboMME/robomme_benchmark` HEAD `016ac1c4ef3df2b88488abc19db08f3de83647b5`（2026-10-03「Update WeChat group QR code」）。本机实测 `src/robomme/`（102 文件）、`challenge_interface/`、`scripts/{dataset_replay,evaluation,run_example}.py`、`Dockerfile`、`.dockerignore`、`LICENSE`、`assets/` 与该 HEAD **逐字节零差异**；只有 `readme.md`（我们加了已失效的「Data Generation」节）、`.gitignore`（多 13 行）、`doc/Wechat.jpg`（官方更新了二维码）、`doc/submission/ponderpounce.md`（官方新增）四处不同。此前文档写的环境锚点 `1fadc0ec` 与 `016ac1c4` 在 `src/robomme` 上同样零差异。
> **外部依赖锚点**：四个子模块 gitlink 原样保留——`third_party/mme-vla@ecf086c3`、`third_party/SimpleMemVLA@c564c17d`、`third_party/PonderPounce@723df357`、`third_party/Astra-on-RoboMME@4c3fd6a8`。
> **体例**：新仓库 commit subject 沿用 `<大>.<小>[.<修订>] <中文描述>`；本文件放根目录是用户本轮明确要求（「落在根目录上先让我审核」），与仓库「计划进 `docs/plans/`」的惯例冲突，审核后移入 `docs/plans/` 或随归档分支冻结。

# 第一部分（给人看）

## 一、要做什么与全部一览

用户原话（2026-10-08）：「https://github.com/RoboMME/robomme_benchmark 在根目录写一个重构的方案 就是需要相比于官方的benchmark只多多出一个scripts和一个source文件夹 然后所有Evaluation的内容单独出一个Repo。然后这个repo来fork所有的repo就不在现有的repo里面实现。另外我还需要就是删除所有的生成ENV的工具只保留这个EVUation的工具然后EVUation只能生出来这个Xhard0和ood 先写初步的方案然后落在根目录上先让我审核。然后如果有需要的话可以生成HTML。」「HTML必须使用SubAgent。」

三句话：

1. **现仓库一分为二。** 「benchmark 仓」从官方 HEAD `016ac1c4` 直接分出，相对官方只多 `src/robomme_hard/`（环境包，含 `ood` 五份冻结规格）和 `scripts/hard/`（一个评估入口）两个文件夹；「eval 仓」承接 `scripts/eval-official/` 全部内容、四个模型仓的 fork 子模块、评估测试与评估留档，并以子模块方式依赖 benchmark 仓。
2. **生成工具全部删除。** `scripts/injection-dev/`（抽签、封存、回放生成 h5）、`scripts/parity/`（对拍、噪声闸门、上游守卫）、`scripts/configs/`（生成冻结配置）以及对应的 46 个生成类测试与 90 MB 生成留档，不进任何新仓；`robomme_hard` 包内只为生成服务的分支（`train` 元数据、规格根覆盖、V4 旧接口、xhard0 前置开关）一并裁掉，builder 只认 `hard-verify`（＝xhard0，官方 test 的 hard 子集每任务 12 局）与 `ood`（V9 五档每任务 50 局）两个数据集。
3. **现仓库分支冻结归档，不删历史。** `newtaskRelease-taskV9` 打归档 tag 后不再提交；`artifacts/`、HF bucket、本机站点全部不动。

```text
RoboMME/robomme_benchmark @016ac1c4（官方，只读）
        │ fork（git 历史直接接在官方 HEAD 之后）
        ▼
benchmark 仓（建议名 hongzefu/robomme_benchmark_hard）
  官方全部文件（零改动）
  + src/robomme_hard/        ← 现仓库 src/robomme_hard 裁剪后搬入
  + scripts/hard/            ← evaluation_hard.py（唯一评估入口）
        │ submodule（gitlink 钉 40 位 sha）
        ▼
eval 仓（建议名 hongzefu/robomme_hard_eval）
  third_party/robomme_benchmark   ← 上面的 benchmark 仓
  third_party/mme-vla             ← fork（eval-official-v1 分支）
  third_party/SimpleMemVLA        ← fork（eval-official-v1 分支）
  third_party/PonderPounce        ← 上游锁定
  third_party/Astra-on-RoboMME    ← 上游锁定
  scripts/eval/                   ← 现仓库 scripts/eval-official 平移
  tests/、docs/validation/        ← 只带评估相关部分

现仓库 newtaskRelease-taskV9 → tag archive-newtask-v9-20261008，只读归档
```

| 仓库 | 基点 | 装什么 | 相对官方的差异 |
|---|---|---|---|
| benchmark 仓 | 官方 `016ac1c4` | 官方全部 + `src/robomme_hard/` + `scripts/hard/evaluation_hard.py` | 新增恰好两个目录；`pyproject.toml` 的 wheel 多一行 `src/robomme_hard`；`readme.md` 多一节「Hard evaluation」；`.gitignore` 多 13 行忽略 `runs/` 与媒体文件 |
| eval 仓 | 空仓 | 五个子模块、`scripts/eval/`、评估测试、评估留档、独立 `pyproject.toml`（`pebble`、`eval-client`、`server` 组、三个子 venv） | 不与官方比，整仓都是我们的 |
| 归档分支 | 现 HEAD `9c78c076` | 一切历史（生成工具、对拍、98 MB docs、1379 个 commit） | 冻结 |

**已定死口径**（来自用户原话，依据见括号）：

1. benchmark 仓相对官方「只多出一个 scripts 和一个 source 文件夹」（§三的 `BENCH_DELTA` 判定行把它写成可机检条件）。
2. 所有评估内容单独一个仓，模型仓的 fork 都在那个仓里接，不在 benchmark 仓里实现（§四）。
3. 删除所有生成环境的工具，只保留评估工具（§二表的「删除」列）。
4. 评估只能生出 xhard0 与 ood 两种数据集（§三 `BENCH_DATASETS` 判定行）。
5. 先写初步方案落根目录审核；HTML 由子代理生成（§九）。

## 二、现仓库相对官方多了什么、各自去哪

取数：`git ls-files | awk -F/ '{print $1}' | sort | uniq -c` 与 `diff -rq` 对官方 HEAD，2026-10-08。

| 区域 | 现状（相对官方 `016ac1c4`） | 去向 |
|---|---|---|
| `src/robomme/`（102 文件）、`challenge_interface/`（10）、`scripts/` 三入口、`Dockerfile`、`assets/`、`LICENSE` | 零差异 | benchmark 仓原样（直接是官方文件，不需要再对拍） |
| `doc/Wechat.jpg`、`doc/submission/ponderpounce.md` | 官方更新／新增，我们落后 | benchmark 仓取官方版本 |
| `src/robomme_hard/`（73 文件：16 环境类、33 个 utils、10 个 wrapper、5 份 `ood/*/specs.jsonl` 共 1523 行 3.4 MB、4 份 `train` 元数据） | 全部新增 | benchmark 仓，按 §三裁剪 |
| `scripts/evaluation_hard.py` | 与官方 `evaluation.py` 只差 3 处单行 + 1 段 | 移到 `scripts/hard/evaluation_hard.py` |
| `scripts/eval-official/`（55 文件，5 MB；含三个子 venv 的 `pyproject.toml`/`uv.lock`、`orig_observer/`） | 全部新增 | eval 仓 `scripts/eval/` |
| `scripts/injection-dev/`（25）、`scripts/parity/`（22，含 vendored 官方生成编排四文件）、`scripts/configs/`（23） | 生成、对拍、守卫 | **删除**（`eval-official` 引用 `injection-dev` 的 4 个文件——`eval_video_mover.py`、`export_eval_identities.py`、`site_build.py`、`seed_layout.py`——随 eval 仓迁走，不留在 benchmark 仓） |
| `tests/`（265 文件） | 全部重写，官方 29 个旧测试已删 | `unit/hard`（56）、`unit/robomme`（28）、`unit/wrappers`（7）、`unit/common`（1）、`contract`（16）、`static`（9）、`sim`（4）、`_support`（3）共 124 个属环境包 → 去向见 Q3；`pipeline/eval`（30）、`pipeline/evalx`（43）、`pipeline/challenge`（10）、`pipeline/recording`（8）共 91 个 → eval 仓；`pipeline/gen`（11）、`pipeline/parity`（20）、`pipeline/site`（7）、`mutation`（8）共 46 个 → 删除 |
| `docs/`（3944 文件，98 MB） | 全部新增 | 评估留档 `validation/{sg-eval-gl-20261004-01,sg-eval-gl-20261006-02,sg-eval-gl-20261006-03,v7.5eval,v8-two-policy-gl10-20261002-01,v9-two-policy-gl10-20261002-01}`（约 4 MB）与 `validation/legacy-names.md` → eval 仓；`plans/`、`ledger/`、`validation/newtask-v2～v9`、噪声基线、测试重构留档 → 只留归档分支 |
| `third_party/` 四个子模块 | 全部新增 | eval 仓（gitlink sha 不变） |
| `pyproject.toml` | 多 `pebble`、`eval-client` 组、`openpi-client` 源、wheel 多 `src/robomme_hard`、pytest 段 | benchmark 仓只保留 wheel 那一行；其余进 eval 仓的 `pyproject.toml` |
| `.gitignore` | 多 `/artifacts/*`、`/runs/`、`*.mp4`、`*.h5` 等 13 行；实测官方 `.gitignore` 不含 `runs/`、`*.mp4`、`*.h5` | benchmark 仓保留这 13 行（入口默认把视频写到 `runs/`，不加就会把 mp4 提交进仓），算第四个允许的 `M`；eval 仓自带 |
| `readme.md` | 「Data Generation」节指向已删的 `generate_dataset_newseed.py` | benchmark 仓回到官方正文，追加一节「Hard evaluation」说明两个数据集与入口 |
| `AGENTS.md`、`CLAUDE.md`、`greatlakes.md`、根目录 7 份 `1003～1006` 计划 | 规则与计划 | 规则三件见 Q4；计划只留归档分支 |
| `artifacts/`、`runs/`、`.venv`、HF bucket、本机 8081/8082/8084 站点 | 不进 git | 一律不动 |

## 三、benchmark 仓：目标树与「只多两个文件夹」的保证

```text
robomme_benchmark_hard/            ← git 历史：官方 016ac1c4 之后接我们的 commit
├── （官方全部文件，字节不动）
├── src/robomme_hard/              ← 新增目录 1
│   ├── __init__.py、logging_utils.py
│   ├── env_metadata/ood/xhard{1..5}/specs.jsonl      ← 5 份冻结规格，sha 不变
│   ├── env_record_wrapper/{hard_builder,hard_specs,RecordWrapper,…}.py
│   └── robomme_env/{16 个环境类}.py、utils/
└── scripts/hard/                  ← 新增目录 2
    ├── evaluation_hard.py
    └── README.md                  ← 两个数据集、步数、与官方 evaluation.py 的 diff
```

**机检条件 `BENCH_DELTA`**：`git diff --name-status 016ac1c4 HEAD` 的每一行，要么是 `A` 且路径以 `src/robomme_hard/` 或 `scripts/hard/` 开头，要么是 `M` 且路径 ∈ {`pyproject.toml`, `uv.lock`, `readme.md`, `.gitignore`}（Q4 批准后再加 `A AGENTS.md`、`A CLAUDE.md`、`A greatlakes.md`；Q3 批准后再加 `A tests/robomme_hard/**`）；不允许 `D`。判定行 `BENCH_DELTA=PASS added_dirs=2 modified=4 deleted=0`。

**`src/robomme_hard` 的裁剪**（只删生成专用分支，环境类与 utils 一个不动，五份 `specs.jsonl` 字节不变）：

| 锚点 | 现状 | 改成 |
|---|---|---|
| `hard_builder.py::_ALLOWED_DATASETS` | 官方 train/test/val + `ood` + `hard-verify` | 只剩 `{"hard-verify", "ood"}`；传 `train`/`test`/`val` 一律 `ValueError`（官方三个 split 由官方 `robomme` 包自己提供，不在本包重复） |
| `hard_builder.py::HARD_TRAIN_TASKS`、`_resolve_metadata_path`、`env_metadata/train/*.json` | 四个 Unmask 任务的 train 元数据，只为生成对拍 | 删除 |
| `hard_builder.py::from_v4_specs`、`v4_episodes` | V4 旧快照薄包装，注释已写「新代码一律用 ood」 | 删除 |
| `hard_specs.py::XHARD0_IN_TEST_HARD`（环境变量 `ROBOMME_HARD_XHARD0_IN_TEST_HARD`） | 开关打开时 xhard0 12 局前置进 ood | 删除：`ood` 永远只有 xhard1～5 的 800 局，xhard0 只走 `hard-verify` |
| `hard_specs.py::SPECS_ROOT_ENV`（规格根覆盖）、`_override_cells` | 评估时读包外规格根，为生成迭代服务 | 删除：只读包内 `env_metadata/ood/` |
| `hard_builder.py::make_env_for_episode` 其余、`spec_binding`、`EXPECTED_CELLS=V9_CELLS`、`EXEC_CAP=1600` 校验 | 评估必需 | 不动 |

**评估入口** `scripts/hard/evaluation_hard.py`：内容就是现在的 `scripts/evaluation_hard.py`，继续保持「与官方 `evaluation.py` 只差 3 处单行替换 + 1 段 `DATASET` 选择」；`DATASET_MAX_STEPS` 现为 `{"hard-verify": 1300, "ood": 1600}`，而 10-06 第三阶段接口冻结文件把 eval 侧 `ood` 定为 1800（`run_seat.sh` 第 221 行、`astra_hard_runner.py::DATASET_STEP_PAIRING`），入口要不要同步到 1800 见 Q5。

**机检条件 `BENCH_DATASETS`**：在 benchmark 仓 `.venv` 里 `BenchmarkEnvBuilder("MoveCube", dataset=d)` 对 `d ∈ {train,test,val,xhard1}` 必须抛 `ValueError`，对 `hard-verify` 得 12 局、对 `ood` 得 50 局（MoveCube 只有 xhard4 格，50 局全在 xhard4）；16 任务 `ood` 合计 16 任务 × 50 局 = 800、`hard-verify` 合计 16 任务 × 12 局 = 192。判定行 `BENCH_DATASETS=PASS rejected=4 hard_verify=192 ood=800`。

## 四、eval 仓：内容与依赖方式

```text
robomme_hard_eval/
├── third_party/robomme_benchmark   ← submodule，gitlink 钉 benchmark 仓的 40 位 sha
├── third_party/{mme-vla, SimpleMemVLA, PonderPounce, Astra-on-RoboMME}   ← 四个 gitlink 原样
├── scripts/eval/                   ← 现 scripts/eval-official/** 平移（含 orig_observer/、三个子 venv 目录）
│   └── + eval_video_mover.py、export_eval_identities.py、site_build.py、seed_layout.py（从 injection-dev 带来）
├── tests/                          ← pipeline/eval、evalx、challenge、recording 四组 + _support、conftest
├── docs/validation/                ← 六个评估留档目录 + legacy-names.md
├── pyproject.toml / uv.lock        ← pebble、openpi-client 源、eval-client 与 server 组；主依赖 robomme 走 path 源 third_party/robomme_benchmark（editable）
└── AGENTS.md / CLAUDE.md / greatlakes.md
```

- **「fork 所有 repo 都在这个仓接」**：四个模型仓以 submodule 锁 gitlink 接入（正本第 24 条）；需要改模型代码时在各自 fork 的 `eval-official-v1` 分支改、先推 fork 再更新 gitlink，benchmark 仓永远不含任何模型代码。
- **对 benchmark 仓的依赖走 submodule 而不是 PyPI 式 git 依赖**：评估脚本 14 个文件 `import robomme_hard`、0 个引用 `challenge_interface`，wheel 内含 `robomme` 与 `robomme_hard` 两个包即可，但保留 submodule 还能让 eval 仓直接拿到官方 `scripts/evaluation.py` 做原侧对照（`gate2_compare.py` 的「原侧」就是官方入口）。
- **数据集限制在 eval 仓同样成立**：`run_seat.sh::step_cap_pairing`、`astra_hard_runner.py::DATASET_STEP_PAIRING`、`official_defs.py::LEGACY_DATASET_ALIASES` 现已只认 `hard-verify`／`ood`；迁移时不改语义，只改路径。
- **三个子 venv**（`client-env`、`orig-framesamp-modul-client-env`、`smvla-env`）原样带走，各自 `pyproject.toml`/`uv.lock` 继续被 git 跟踪（正本第 3 条）。

## 五、现仓库与磁盘产物的处置

- `newtaskRelease-taskV9` 打 tag `archive-newtask-v9-20261008`，此后不再提交；GitHub 上 `hongzefu/robomme_benchmark_MotionJEPA` 保留。
- `/data/hongzefu/robomme_benchmark_MotionJEPANewTask` 工作副本保留到两个新仓都验收 PASS 且用户另行下令后再定去留；`artifacts/`（V9 数据集、评估视频、对拍 h5）、HF bucket、NFS 集群克隆、三个本机站点全部不动。
- 本方案不触碰 `src/robomme/`（P2），也不改任何模型 fork。

## 六、验收判定行

| 判定行 | 查什么 | 怎么查 | 过了说明什么 |
|---|---|---|---|
| `BENCH_DELTA=PASS added_dirs=2 modified=4 deleted=0` | 相对官方只多两个目录 | `git diff --name-status 016ac1c4 HEAD` 逐行按 §三规则分类 | 用户口径 1 成立，且可随时复查 |
| `BENCH_UPSTREAM=PASS files=0` | 官方文件零改动 | `git diff --quiet 016ac1c4 HEAD -- src/robomme challenge_interface scripts/dataset_replay.py scripts/evaluation.py scripts/run_example.py Dockerfile doc assets` | 不再需要 `upstream_guard.py`，git 本身就是守卫 |
| `BENCH_SPECS_SHA=PASS files=5` | 五份 `specs.jsonl` 字节不变 | `sha256sum` 对现仓库 `tests/contract/packaged_specs.sha256` 钉值 | 800 局场景与 V9 交付一致 |
| `BENCH_DATASETS=PASS rejected=4 hard_verify=192 ood=800` | builder 只认两个数据集 | §三的 Python 单测 | 用户口径 4 成立 |
| `BENCH_ENTRY_DIFF=PASS hunks=4` | 入口与官方 `evaluation.py` 仍只差 3 单行 + 1 段 | `diff scripts/evaluation.py scripts/hard/evaluation_hard.py` | 入口没有夹带别的改动 |
| `BENCH_SMOKE=PASS resets=2` | 入口真能跑 | `DummyModel`、MoveCube、`hard-verify` 与 `ood` 各 1 局（单 worker 共 2 次 reset，低于 P3 的 10 次阈值） | 环境包搬家没断 |
| `EVAL_IMPORT=PASS` | eval 仓里 `robomme_hard.__file__` 指向 `third_party/robomme_benchmark/src/` | `uv run python -c "import robomme_hard;print(robomme_hard.__file__)"` | editable 指向正确（正本第 24 条） |
| `EVAL_TESTS=PASS` | 迁来的 91 个评估测试全过 | `timeout 280s uv run --no-sync python -m pytest -m 'not slow' -q` | 评估链路没因搬家断 |
| `EVAL_SMOKE`（待授权） | 一个模型跑 1 局 | 需 GPU 与权重，列入 eval 仓第一次正式评估前的 smoke，本方案不跑 | — |

## 七、实施步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| S0 | 用户审核本方案，裁决 Q1～Q9；用户说「开工」 | — |
| S1 | 建 benchmark 仓：从官方 `016ac1c4` 分支，取官方 `readme.md`/`.gitignore`/`doc/` | `BENCH_UPSTREAM` |
| S2 | 搬入 `src/robomme_hard/` 并按 §三表裁剪；`pyproject.toml` wheel 加包 | `BENCH_SPECS_SHA`、`BENCH_DATASETS` |
| S3 | 建 `scripts/hard/`，入口与 README；`readme.md` 加「Hard evaluation」节 | `BENCH_ENTRY_DIFF`、`BENCH_SMOKE`、`BENCH_DELTA` |
| S4 | 建 eval 仓：五个子模块、`scripts/eval/`、测试、留档、`pyproject.toml`、规则三件 | `EVAL_IMPORT`、`EVAL_TESTS` |
| S5 | 归档：tag、旧分支不再提交；两仓 push、规则正本 `sync-targets.json` 登记新仓 | `git status -sb` 无 ahead |

## 八、待你裁决

| 编号 | 问题 | 推荐 |
|---|---|---|
| Q1 | 仓库名与托管：benchmark 仓是 GitHub 上对 `RoboMME/robomme_benchmark` 的真 fork（历史接官方），eval 仓是全新空仓 | 推荐真 fork，名 `hongzefu/robomme_benchmark_hard`；eval 仓 `hongzefu/robomme_hard_eval` |
| Q2 | 评估入口放 `scripts/hard/evaluation_hard.py`（一个文件夹）还是像现在放 `scripts/` 顶层第四入口 | 推荐文件夹，才满足「只多一个 scripts 文件夹」 |
| Q3 | 环境包的 124 个测试（`unit/hard`、`contract` 等）放哪：benchmark 仓允许第三个目录 `tests/robomme_hard/`，还是严格两目录、测试全放 eval 仓 | 推荐允许 `tests/robomme_hard/`（代码与测试同仓），`BENCH_DELTA` 把它列为第三个允许目录 |
| Q4 | `AGENTS.md`/`CLAUDE.md`/`greatlakes.md` 三个规则文件是否进 benchmark 仓根 | 推荐进（是文件不是文件夹，agent 开工需要） |
| Q5 | 入口 `ood` 步数上限：保持 1600（现入口）还是改 1800（10-06 接口冻结的 eval 口径） | 推荐 1800，与 eval 仓一致；`hard-verify` 1300 不变 |
| Q6 | 数据集 id：`hard-verify` 保持（10-06「照官方名」裁决）还是改成 `xhard0` | 推荐保持 `hard-verify`，README 写明「xhard0 = hard-verify」 |
| Q7 | §三表列的五处裁剪（train 元数据、V4 接口、xhard0 前置开关、规格根覆盖、`_ALLOWED_DATASETS` 收窄）全做 | 推荐全做 |
| Q8 | 六个评估留档目录随 eval 仓，其余 94 MB 留档只在归档分支 | 推荐如此 |
| Q9 | 本机工作副本、`artifacts/`、HF、站点一律不动，等两仓验收后另议 | 推荐如此 |

## 九、子代理分工与合并（简述）

本方案落地时按 `CLAUDE.md`「计划执行模式」分三块、串行合并：① benchmark 仓的 `robomme_hard` 裁剪（一个写入型子代理，可写集合 `src/robomme_hard/**`、`pyproject.toml`，禁触官方文件）；② benchmark 仓的入口与 README（一个写入型子代理，可写 `scripts/hard/**`、`readme.md`）；③ eval 仓的平移（主会话自做：子模块登记、`git mv` 级搬迁与 `uv lock` 归主会话）。每块合并前由只读审查子代理按 `BENCH_DELTA`/`BENCH_DATASETS` 等判定行审一次，合并后主会话跑核心短测再审一次。本方案本身的 HTML 版由一个只读 sonnet 子代理渲染（写到 scratchpad，不进仓库）。

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

- R1 `src/robomme/**`、`challenge_interface/**`、官方三入口、`Dockerfile`、`doc/`、`assets/` 在 benchmark 仓里必须与官方 `016ac1c4` 逐字节相同；任何改动按 P2 逐个批准，本方案不申请任何一处。
- R2 五份 `src/robomme_hard/env_metadata/ood/xhard{1..5}/specs.jsonl` 字节不变（`tests/contract/packaged_specs.sha256` 钉值）。
- R3 不动四个模型 fork 的 gitlink sha；不在 benchmark 仓出现任何模型代码。
- R4 删除只发生在新仓的「不搬入」动作上；现仓库与归档分支不执行任何 `git rm`、不改写历史、不 force push。
- R5 本方案的 smoke 预算：benchmark 仓 `BENCH_SMOKE` 单 worker 2 次 reset（MoveCube × {hard-verify, ood} × 1 局）；eval 仓不跑模型，P3 不触发。
- R6 开工令：以上一切要等用户明确说「开工」；用户审核通过、裁决 Q1～Q9 都不是开工。
- R7 `uv.lock`、`pyproject.toml`、`.gitmodules`、gitlink 一律主会话改。

## 一 benchmark 仓逐文件改动清单

| 路径 | 动作 | 来源 | 说明 |
|---|---|---|---|
| 官方全部文件 | 保持 | 官方 `016ac1c4` | fork 自带，零改动 |
| `src/robomme_hard/{__init__,logging_utils}.py`、`robomme_env/**`（16 环境类 + `utils/` 33 文件）、`env_record_wrapper/{DemonstrationWrapper,EndeffectorDemonstrationWrapper,FailAwareWrapper,MultiStepDemonstrationWrapper,OraclePlannerDemonstrationWrapper,RecordWrapper,__init__,episode_dataset_resolver}.py` | 搬入，字节不动 | 现仓库 `9c78c076` | 复制／借用 shim 结构不变；`__init__.py` 第 13 行注释里指向 `scripts/parity/upstream_guard.py` 的一句改成指向 git 守卫 |
| `src/robomme_hard/env_record_wrapper/hard_builder.py` | 搬入后裁剪 | 同上 | 删 `HARD_TRAIN_TASKS`、`_resolve_metadata_path` 的 train 分支、`from_v4_specs`、`v4_episodes`、`dataset="v4-specs"` 相关；`_ALLOWED_DATASETS = {OOD, HARD_VERIFY}`；`__init__` 里「先以 `dataset="test"` 过父类校验再改回」的 shim 保留（官方父类 `_ALLOWED_DATASETS` 只认 train/test/val 且不能改）；`_ood_entries` 的 `xhard0` 入参固定为空列表 |
| `src/robomme_hard/env_record_wrapper/hard_specs.py` | 搬入后裁剪 | 同上 | 删 `XHARD0_IN_TEST_HARD`、`SPECS_ROOT_ENV`、`_override_cells`、`resolve_cell_table` 的覆盖分支；`load_specs_root` 只接受包内根；`XHARD0_PER_TASK=12`、`XHARD0_EPISODES=range(3,48,4)`、`EXEC_CAP=1600`、`V9_CELLS`/`EXPECTED_CELLS` 不动 |
| `src/robomme_hard/env_metadata/ood/xhard{1..5}/specs.jsonl` | 搬入，字节不动 | 同上 | R2 |
| `src/robomme_hard/env_metadata/train/*.json`（4 份） | 不搬 | — | 生成对拍用 |
| `src/robomme_hard/README.md` | 重写 | — | 只留「包结构、两个数据集、逐文件复制／借用表」；对拍判定行与六档表移到归档 |
| `scripts/hard/evaluation_hard.py` | 搬入 | 现 `scripts/evaluation_hard.py` | Q5 定 1600/1800；`import` 路径不变（包装进 wheel） |
| `scripts/hard/README.md` | 新写 | — | 两个数据集、局数乘式（`hard-verify` 16 × 12 = 192；`ood` 43 格合 16 × 50 = 800）、步数、与官方入口 diff |
| `.gitignore` | 追加 13 行 | 现仓库 | `/artifacts/*`、`/.claude/worktrees/`、`/runs/`、`*.mp4`、`*.mkv`、`*.h5`、`*.hdf5` |
| `pyproject.toml` | 改一行 | — | `[tool.hatch.build.targets.wheel] packages = ["src/robomme", "src/robomme_hard"]`；不加 `pebble`、不加 `eval-client` 组、不加 pytest 段（Q3 允许 tests 时只加 `testpaths`） |
| `uv.lock` | 随 `uv lock` | — | 依赖集与官方相同，预期只有 hash 变化 |
| `readme.md` | 官方正文 + 一节 | 官方 | 「### 🧗 Hard evaluation (xhard0 / ood)」放在官方「Evaluation」节之后、「Data Generation」节之前；不再出现 `generate_dataset_newseed.py` |
| `tests/robomme_hard/**`（Q3） | 搬入并裁剪 | 现 `tests/{unit/hard,unit/robomme,unit/wrappers,unit/common,contract,static,sim,_support}` + `conftest.py` | 删掉断言 train 元数据、`XHARD0_IN_TEST_HARD`、规格根覆盖、`upstream_guard`、`scripts/parity` 的用例（`tests/contract/test_metadata.py`、`test_constants.py`、`test_builder_800.py` 三个文件各有涉及，逐用例判断） |
| `AGENTS.md`、`CLAUDE.md`、`greatlakes.md`（Q4） | 新写 | 正本标记块 + 本仓专属（P1 改为「`scripts/` 顶层三官方入口 + `hard/`」、P2 不变、P3 保留） | 用 `sync_rules.py apply` 落标记块，`sync-targets.json` 登记 |

## 二 eval 仓逐文件改动清单

| 路径 | 动作 | 来源 | 说明 |
|---|---|---|---|
| `.gitmodules` + `third_party/robomme_benchmark` | 新增 submodule | benchmark 仓 | gitlink 钉 S3 完成后的 sha |
| `third_party/{mme-vla,SimpleMemVLA,PonderPounce,Astra-on-RoboMME}` | 原样登记 | 现 `.gitmodules` 四条 | url、branch、sha 不变 |
| `scripts/eval/**` | 平移 | 现 `scripts/eval-official/**` 55 文件 + `injection-dev` 四文件 | 路径字符串逐处改：`scripts/eval-official` → `scripts/eval`，`scripts/injection-dev/<x>` → `scripts/eval/<x>`，`third_party/<模型>` 不变，`src/robomme_hard` 经 submodule 由 editable 安装提供；`pp_client.py` 对 `configs/robomme.yaml` 的三处引用只是注释里指 PonderPounce 自己的配置，不依赖现仓库 `scripts/configs/`，无需随迁 |
| `tests/{pipeline/eval,pipeline/evalx,pipeline/challenge,pipeline/recording}`、`tests/_support`、`tests/conftest.py`、`tests/contract/benchmark_contracts.json` 评估部分 | 平移 | 现仓库 | `_support/loaders.py` 的按路径加载改到新路径 |
| `docs/validation/{sg-eval-gl-20261004-01,sg-eval-gl-20261006-02,sg-eval-gl-20261006-03,v7.5eval,v8-two-policy-gl10-20261002-01,v9-two-policy-gl10-20261002-01}`、`docs/validation/legacy-names.md` | 平移 | 现仓库 | 留档内引用的 `artifacts/` 路径是本机绝对事实，不改写 |
| `pyproject.toml` | 新写 | 现仓库同名文件 | `robomme = { path = "third_party/robomme_benchmark", editable = true }`；`pebble`、`openpi-client` path 源（指向 `third_party/mme-vla/packages/openpi-client`）、`eval-client`、`server` 组、pytest 段照搬 |
| `scripts/eval/{client-env,orig-framesamp-modul-client-env,smvla-env}/{pyproject.toml,uv.lock}` | 平移 | 现仓库 | 三个子 venv，`UV_PROJECT_ENVIRONMENT` 取法不变 |
| `AGENTS.md`、`CLAUDE.md`、`greatlakes.md` | 新写 | 正本标记块 + 现仓库专属段（P3、P4、P5、覆盖项） | 同样登记进 `sync-targets.json` |

## 三 子代理分配表（S0 获批与「开工」后才派）

| 子任务 | 目标 | 可写集合 | 禁触 | 接口契约 | 合并顺序 | 验收命令与判定行 | 资源 |
|---|---|---|---|---|---|---|---|
| H1（写入型，opus，worktree） | benchmark 仓 `robomme_hard` 裁剪 | `src/robomme_hard/**`、`src/robomme_hard/README.md` | 官方全部文件、`pyproject.toml` | `BenchmarkEnvBuilder(env_id, dataset, action_space, max_steps)` 签名不变；`get_task_list`/`get_episode_num`/`make_env_for_episode`/`resolve_episode`/`resolve_identity` 语义不变 | 1 | `BENCH_DATASETS`、`BENCH_SPECS_SHA`；环境取法 `UV_PROJECT_ENVIRONMENT=<benchmark 仓 .venv> PYTHONPATH=<worktree>/src` | CPU |
| H2（写入型，opus，worktree） | 入口与两份 README | `scripts/hard/**`、`readme.md` | `src/**`、`pyproject.toml` | 入口 import `robomme_hard.env_record_wrapper.BenchmarkEnvBuilder` | 2 | `BENCH_ENTRY_DIFF` | CPU |
| H3（Q3 批准才派；写入型，opus，worktree） | 环境包测试搬迁裁剪 | `tests/robomme_hard/**` | 其余 | 用 H1 合入后的接口 | 3 | `timeout 280s … pytest -m 'not slow' -q` 末行 `TEST_RESOURCE=` | CPU |
| 主会话自做 | 建仓、fork、submodule、`pyproject.toml`/`uv.lock`、`.gitmodules`、`BENCH_DELTA`/`BENCH_UPSTREAM`/`BENCH_SMOKE`、eval 仓整仓平移、tag、push、规则同步 | — | — | — | 0 与 4 | 全部判定行 | GPU 1 张只在 `BENCH_SMOKE` 用 2 次 reset |
| 审查（只读，sonnet，不加 isolation） | 每块合并前一次 | 无 | — | 只许 `git diff/log/show` 钉死 sha | 每块后 | `PRE_MERGE_REVIEW=PASS|FAIL …` | — |

## 四 闸门总表

`BENCH_UPSTREAM` → `BENCH_SPECS_SHA` → `BENCH_DATASETS` → `BENCH_ENTRY_DIFF` → `BENCH_SMOKE` → `BENCH_DELTA`（benchmark 仓五连）；`EVAL_IMPORT` → `EVAL_TESTS`（eval 仓）；任一 FAIL 停下交用户，不放宽。

## 五 runbook（命令草案，开工后按实际 sha 填）

```bash
# S1 benchmark 仓
git clone https://github.com/hongzefu/robomme_benchmark_hard   # Q1 定名后的 fork
git -C robomme_benchmark_hard checkout -b hard-release 016ac1c4ef3df2b88488abc19db08f3de83647b5
# S2 搬入（从现仓库 9c78c076 取文件，不带 train 元数据）
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask archive 9c78c076 src/robomme_hard scripts/evaluation_hard.py | tar -x -C robomme_benchmark_hard --exclude='src/robomme_hard/env_metadata/train'
mkdir -p robomme_benchmark_hard/scripts/hard && git -C robomme_benchmark_hard mv scripts/evaluation_hard.py scripts/hard/evaluation_hard.py
# 判定
git -C robomme_benchmark_hard diff --quiet 016ac1c4 HEAD -- src/robomme challenge_interface scripts/dataset_replay.py scripts/evaluation.py scripts/run_example.py Dockerfile doc assets && echo BENCH_UPSTREAM=PASS files=0
git -C robomme_benchmark_hard diff --name-status 016ac1c4 HEAD   # 逐行分类 → BENCH_DELTA
# S4 eval 仓
git submodule add https://github.com/hongzefu/robomme_benchmark_hard third_party/robomme_benchmark
UV_LINK_MODE=copy uv sync && uv run python -c "import robomme_hard;print(robomme_hard.__file__)"   # EVAL_IMPORT
# S5 归档
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask tag archive-newtask-v9-20261008 9c78c076 && git push origin archive-newtask-v9-20261008
```

## 六 风险登记

| 风险 | 影响 | 处置 |
|---|---|---|
| `robomme_hard` 导入时 `register_env(override=True)` 接管 16 个官方 env id | 同进程想要官方行为须另开进程 | 现状如此，README 写明；eval 仓原侧对照本来就是独立进程 |
| 裁掉 `XHARD0_IN_TEST_HARD` 后，历史站点／身份文件（992 局口径）无法再由新代码重导 | 只影响归档材料 | 归档分支保留全部代码，需要时在归档分支跑 |
| 官方父类 `_ALLOWED_DATASETS` 校验 shim（先传 `test` 再改回）依赖官方实现细节 | 官方升级可能断 | 已有 `tests/contract` 钉住；fork 跟官方时先跑 `BENCH_DATASETS` |
| eval 仓三个子 venv 与 `openpi-client` path 源都指向子模块路径 | 子模块未 init 时 `uv sync` 失败 | README 第一步写 `git submodule update --init --recursive`（`mme-vla` 检出约 7 GB，含权重缓存，按正本第 15 条先确认落点） |
| 规则正本 `sync-targets.json` 要新增两个目标 | 漏登记则两仓规则漂移 | S5 一并做，`sync_rules.py check` 末行 `SYNC_SUMMARY=PASS` |

## 七 盲区诚实清单

1. （已核）官方 `.gitignore` 不含 `runs/`、媒体与 h5 规则，已按 §二改为保留 13 行、`BENCH_DELTA` 允许四个 `M`。
2. （已核）`pp_client.py` 的 `configs/` 引用只是注释，无文件依赖。
3. `tests/contract/{test_metadata,test_constants,test_builder_800}.py` 里涉及 train 元数据与开关的用例数未逐条数过，H3 时逐条判断。
4. eval 仓 `EVAL_TESTS` 预期通过数（现 `pipeline/eval+evalx+challenge+recording` 共 91 文件、用例数未统计）要在搬迁后取基线。
5. （已核）官方仓库没有 tag，14 个分支（`main`、`dataset-gen`、`cvpr2026Challenge-*`、`v0.4.1-stable`、`v0.6.5-docker-video*` 等）；benchmark 仓只从 `main@016ac1c4` 分出。
6. GitHub 侧建 fork／新仓、`sync-targets.json` 改正本，都是外发动作，S0 后逐项再确认。

## 八 留档与 commit 纪律

- 本方案文件：审核后 `git add 1008-split-benchmark-eval-repos-plan.md` 单独提交（12.541），subject 「12.541 仓库拆分初步方案（benchmark 回官方 + 两目录、评估独立成仓）」，body 含用户原话、本文件要点、实测差异表；HTML 不进 git。
- 两个新仓各自的第一个 commit body 写明来源 sha（`9c78c076`）与官方 sha（`016ac1c4`）、搬入清单、裁剪清单、判定行原文；`sub/H1:`、`sub/H2:`、`sub/H3:` 前缀按计划执行模式保留。
- 归档 tag 的 message 写明「此后 newtaskRelease-taskV9 不再提交，后续工作在 robomme_benchmark_hard 与 robomme_hard_eval」。
