# scripts/ 总说明：与官方的文件差异、新 episode 生成链路、对拍链路、评估链路

> 锚点：本文按 `newtaskRelease-v5` 分支 12.214（`217bfee1`）写成。官方两个锚点：环境源码 `RoboMME/robomme_benchmark@1fadc0ec`（`src/robomme/` 逐字节等于它）、生成编排 `d53f21a7`（`scripts/parity/official/` 四文件逐字节 vendor）。拆包总计划见 [`0927-robomme-hard-layered-plan.md`](../0927-robomme-hard-layered-plan.md)，四档新值口径见 [`0925-newtask-release-v6-plan.md`](../0925-newtask-release-v6-plan.md)。
>
> 本文只讲「现在怎么用、怎么核」。V4/V5 逐环境字段表、V6 发布说明等历史正文整份保留在 [`README-legacy.md`](README-legacy.md)（12.214 之前的 `scripts/README.md`，不再维护）；更早版本用 `git show 7a6cee35:scripts/README.md` 取回。

## 目录

1. 一览：`scripts/` 里有什么
2. 仓库相对官方的文件差异
3. 生成新 episode 链路（`injection-dev/`，两阶段）
4. 对拍链路（`parity/`，G1 守卫 + 三侧对拍 + 回归）
5. 评估链路（`evaluation_hard.py` 与 `dataset="test-hard"`）
6. 三条链路的共同约束与核查清单

---

## 1. 一览：`scripts/` 里有什么

`scripts/` 顶层只允许四个入口（`AGENTS.md` P1，核查 `ls -1 scripts/*.py` 恰好四行），其余一律收进子目录：

| 位置 | 角色 | 一句话 |
|---|---|---|
| `dataset_replay.py`、`evaluation.py`、`run_example.py` | 官方入口 | 与官方 `1fadc0ec` 逐字节相同，不得改动 |
| `evaluation_hard.py` | 新值档评估入口 | 与 `evaluation.py` 只差 4 处（见第 5 节），跑 `dataset="test-hard"` |
| `injection-dev/` | 生成新 episode 的生产链路 | 第一阶段 `freeze_specs.py`（定规则 → 抽签 → 封存 jsonl），第二阶段 `generate_h5.py`（只读 jsonl → 生成 h5 → 状态机回写）；`site/` 是只读出图与候选核对工具；`seed_layout.py` 是 seed 公式与 16 任务规范序 |
| `parity/` | 与官方比 | `upstream_guard.py`（G1 守卫）、`hard_parity.py`（三侧对拍 generate/publish/compare）、`hard_pull.py`（NFS → 本机拉取）、`hard_regression.py`（S4 子集、reset 回放、评估冒烟）、`train_split_*.py`（S0 原始 train 基线设施与实际起环境的运行器）、`official/`（vendor 的官方编排四文件）；细表见 [`parity/README.md`](parity/README.md) |
| `configs/` | 冻结配置 | `hard-parity-tolerances.json`（对拍容差层阈值）、`newtask-v6/v6-02/xhard1～4/specs.jsonl`（S4 正式生成所用规格，只读留档） |
| `README-legacy.md` | 历史说明 | V4/V5 逐环境字段表、V6 发布说明；只读 |

三条链路之间的关系：**生成链路**产出新值档规格 jsonl 与 h5；**对拍链路**证明拆包后的 `robomme_hard` 在原三档上与官方行为一致、在新值档上与 S4 交付一致；**评估链路**让合作者用与官方同形的 builder 接口跑 `test-hard` 四档。

## 2. 仓库相对官方的文件差异

比较基线是官方 `1fadc0ec`（本地对象库里有该 commit，`git cat-file -t 1fadc0ec` 返回 `commit`）。一键复现：

```bash
git diff --name-status 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9 HEAD -- . ':!docs' ':!artifacts' | sort
```

### 2.1 按目录分类

| 区域 | 相对官方 | 说明 |
|---|---|---|
| `src/robomme/**` | **零差异**（102 文件） | `UPSTREAM_BYTES=PASS src_commit=1fadc0ec files=102 diff=0`。受 P2 保护，任何改动或运行时覆盖须用户逐个批准；录像器 `RecordWrapper.py` 默认冻结 |
| `src/robomme_hard/**` | **全部新增**（74 文件） | 与 `robomme` 并列的新值档环境包：16 个环境类与改过的 utils／wrapper 为「复制」（33 个），依赖闭包干净的官方模块为「借用 shim」（18 个，每个 ≤ 3 行非注释行），`hard_builder.py` 是官方 `BenchmarkEnvBuilder` 的子类，`hard_specs.py`、`utils/{episode_spec,sampling_config,xhard,...}.py` 为新增；逐文件表见 [`src/robomme_hard/README.md`](../src/robomme_hard/README.md) ③（由 `upstream_guard.py manifest-md` 生成）。四档规格随包分发在 `env_metadata/test-hard/xhard{1..4}/specs.jsonl`，四个 Unmask 任务的 `train` 元数据改读本包 `env_metadata/train` |
| `scripts/dataset_replay.py`、`evaluation.py`、`run_example.py` | 零差异 | 官方 `scripts/` 只有这三个文件 |
| `scripts/evaluation_hard.py` | 新增 | 见第 5 节 |
| `scripts/injection-dev/**`、`scripts/parity/**`、`scripts/configs/**` | 新增 | 第 3、4 节 |
| `tests/` | 新增 53 个文件、修改 `conftest.py` | 官方测试原样保留；新增 `test_hard_*`、`test_v4_xhard_*`、`test_v5_*`、`test_v6_*`、`test_registry_owner`、`test_scripts_do_not_import_tests` 等；`conftest.py` 只加了路径与标记 |
| `pyproject.toml` | 3 处 | 新增依赖 `pebble>=5.2.2`；wheel `packages` 加 `src/robomme_hard`；pytest 新增 `slow/gpu/dataset/lightweight` 四个 marker |
| `.gitignore` | 1 处 | 追加 `/artifacts/*`（产物根整体不进 git） |
| `readme.md` | 「Data Generation」一节 | ⚠ 该节仍指向已删的 `scripts/generate_dataset_newseed.py` 与 `configs/newtask-v2/`（拆包阶段 0b 删除），属陈旧文本，现行生成入口以本文第 3 节为准 |
| `uv.lock` | 随依赖变化 | — |
| 根目录 `AGENTS.md`、`CLAUDE.md`、`greatlakes.md`、`0925～0927-*-plan.md` | 新增 | 规则与计划，不是代码 |
| `docs/**` | 新增（约 3650 文件） | `docs/validation/` 是各阶段实测留档（判定行原文都在里面），`docs/plans/` 是 V2～V5 旧计划，`docs/ledger/` 是只读历史账本 |

### 2.2 为什么是「并列包」而不是改官方源码

拆包（12.205～12.210）之前，新值档改动直接落在 `src/robomme/` 里，官方基线被遮蔽、无法在同一仓库里并排比。拆包后：官方源码按固定 sha 原样回退（12.208，39 项，用户 U-21 预批准），差异全部搬进 `robomme_hard`；导入 `robomme_hard` 时 16 个环境 id 用 `@register_env(..., override=True)` 接管，包 `__init__` 末尾断言注册归属（`test_registry_owner.py` 守）。同一进程要官方行为必须另开只导入 `robomme` 的进程——这就是对拍链路里 O／P 侧与 H 侧分进程的原因（红线 R5）。

### 2.3 核查命令（秒级、纯 CPU）

```bash
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream
```

12.214 实跑末五行：

```text
UPSTREAM_BYTES=PASS src_commit=1fadc0ec files=102 diff=0 shims=18
VENDOR_SAME=PASS files=4 orchestration_commit=d53f21a7
SHIMS=PASS shims=18
ABS_IMPORT=PASS files=44 retargeted=27 kept=3 unresolved=0
BORROWED_DEPS=PASS shims=18 copied=33 changed_hits=0
UPSTREAM_GUARD=PASS
```

五行含义：`UPSTREAM_BYTES` 官方源码逐字节；`VENDOR_SAME` vendor 四文件与 `official/SOURCE.json` 的 sha256 一致；`SHIMS` 借用 shim 无逻辑；`ABS_IMPORT` 复制件里的 `robomme.<path>` 导入按规则改写（shim 清单内保持、复制件改成 `robomme_hard.`）；`BORROWED_DEPS` 每个 shim 目标在官方源码上的传递依赖闭包不含任何被复制的模块。

## 3. 生成新 episode 链路（`injection-dev/`，两阶段）

### 3.1 概念

- **档位**：`xhard1 < xhard2 < xhard3 < xhard4`，13 个有梯度的任务用四档，StopCube／InsertPeg／MoveCube 只有 `xhard4`；合计 13 × 4 + 3 × 1 = 55 格。四档定稿表见 `src/robomme_hard/README.md` ②。
- **seed 公式**（`seed_layout.py` 与 `hard_specs.seed_rule_for(tier, "v6")`，两处同一公式）：

  ```text
  seed = offset(tier) + env_code × 100000 + episode × 100 + attempt
  offset: xhard4 = 6e6, xhard1 = 8e6, xhard2 = 10e6, xhard3 = 12e6
  ```

  `env_code` 是任务在 16 任务规范序（`seed_layout.ALL_TASKS`，顺序不得改）里的 1-indexed 位置，`attempt` 每 reset 失败加 1。四段偏移与 train／test／val／heldout 及彼此互不重叠。
- **一格 = 若干候选 + 从中选出的正式局**：每格默认抽 10 个成功候选，按 index `0,3,6` 选 3 局正式（MoveCube 按运动方式分层选）。局数一律写乘式（P5）：xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165。
- **规格 jsonl（`schema="hard-specs/2"`，`hard_specs.py`）**：每行分「签」与「结果」两段。签 = `task tier candidate episode seed attempt spec spec_sha256`，被 `identity_sha256` 覆盖，第二阶段不得改；结果 = `selected tried initial_selected rollout`，可回写。`delivery_sha256` 盖排序后的 `(task, tier, candidate, seed, spec_sha256, rollout.h5_sha256)`（只取 `selected` 且 `rollout.status=="ok"` 的行），锁住正式交付集合。
- **规格怎么进环境**：`SpecRecorder`（`robomme_hard/robomme_env/utils/episode_spec.py`）。第一阶段 `spec=None` 时每个取值点在原调用处导出；第二阶段与评估传 `native_episode_spec` 回注——原抽样照常发生但建场景一律用冻结值，原抽样只作兼容核验记入 `mismatches`；`record()` 点只留痕不回注。`sampling_config` 由各环境 `native_blocks(cls, release=...)` 给出 `decision`（按档新值）与 `native`（原三档参数）两块，`assert_native_decision` 保证去掉新值键后与原值全等。
- **新值档一律不开 fail recover**（`RECOVERY_RULE`，用户 2026-09-22）。

### 3.2 第一阶段 `freeze_specs.py`：定规则 → 抽签 → 封存

```bash
uv run --no-sync python scripts/injection-dev/freeze_specs.py \
  --tier xhard3 --tasks all --candidates-per-env 10 --select default \
  --max-reset-attempts 30 --workers 4 --gpus 0,1 --out <新路径>/specs.jsonl
```

| 步 | 模块 | 做什么 | 不做什么 |
|---|---|---|---|
| ① 定规则 | `_extract.build_sampling` | 对 16 任务读 `native_blocks`，合成 `sampling_config`（`--pkg` 默认 `robomme_hard`，`--release` 默认 `newtask-v6`） | 不创建环境、不抽随机数 |
| ② 抽签 | `_draw.draw_rows` | 每任务每档攒候选，只 `reset`，导出 `SpecRecorder` 规格；`--max-reset-attempts` 是每任务共享的总预算（`--task-max-reset-attempts TASK[@TIER]=N` 可单独覆盖）；多 worker 时每任务一个 spawn 子进程、按任务序合并，行序与单 worker 相同 | 不 step、不录像、不写盘 |
| ③ 封存 | `_freeze.freeze` | 按选签规则选正式局，算 `spec_sha256`／`identity_sha256`／`delivery_sha256`，用 `os.link` 排他落盘到 `--out`（目标已存在即失败） | 不再产生 `sampling_config.json` 与 `drafts.jsonl` |

- `--dry-run` 只打印参数与预算（任务数 × 最多尝试数），不起环境。
- `--self-check` 跑完后用 `find -newer` 快照差集核对本次只写出一个文件 → `FREEZE_ONLY_JSONL=PASS|FAIL`。
- 中断即整批重抽，重抽次数计入预算。**预算红线（P3）**：单 worker reset 总尝试 > 10 或多 worker 合计 > 50 必须事先取得用户一次性授权，`--dry-run` 打印的数就是要报给用户的数。

### 3.3 第二阶段 `generate_h5.py`：只读 jsonl → 生成 h5 → 状态机回写

```bash
# 正常生产：跑每格 selected 且未生成的行，失败递补，结束持锁回写 --specs
uv run --no-sync python scripts/injection-dev/generate_h5.py --mode continue \
  --specs <specs.jsonl> --output <输出目录> --workers 16 --gpu 0

# 对拍专用：按身份清单只读重放，不递补、不回写（默认读包内四档 jsonl）
uv run --no-sync python scripts/injection-dev/generate_h5.py --mode replay \
  --identities artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json --output <输出目录>
```

真正起环境、录 h5、跑规划的是 `parity/train_split_runner.py`（`--identity-source formula --no-recovery`）→ `train_split_worker.run_one`（`gym.make(..., sampling_config=, native_episode_spec=)`），环境包由 `ROBOMME_ENV_PACKAGE` 环境变量决定（`--pkg` 默认 `robomme_hard`）。`_rollout.py` 只负责调度与状态机：

- **`continue` 状态机**：进入即在 `<specs>.lock` 上 `O_EXCL` 取锁并持有到回写结束。待跑集 = 每格 `selected` 且 `rollout` 缺失的行。某行失败 → 该行 `selected=false`、`rollout.status="failed"`、`tried=true`，从同格 `tried=false` 且未选中的候选里按 `candidate` 升序递补一个；每格 `selected` 行数不超过 `delivery_per_cell`。基础设施失败（`BrokenProcessPool`、`svulkan2`、`EXCLUSIVE`、`CUDA error`、`out of memory` 等特征）每身份最多重跑 1 次并记原因；任务失败不重试挑成功（第 22 条）。全部批次结束后一次回写：重读 specs，整份文件 sha256 必须等于读入时；只改 `selected`／`tried`／`rollout`（红线 R4）；临时文件 + `os.replace`；写后 `load_specs` 核 `identity_sha256` 未变并重算 `delivery_sha256`。`--self-check` 把这一核对打成 `ROLLBACK_WRITE=PASS|FAIL`。
- **`replay`**：清单与调度集合必须全等 → `REPLAY_SET=PASS|FAIL`；结束打 `GENERATE_REPLAY_DONE scheduled= ok= failed=`。对拍链路 H 侧 xhard 就是用这条路重放 S4 的 165 个身份。
- `--redo TASK:CANDIDATE,...` 显式重跑已 ok 的身份；`--tasks` 只跑部分任务、其余待跑行留到下次；`--resume` 联合核对各轮 `jobs.json`、`results.partial.jsonl`、局目录与 h5，有 h5 却无 partial 记录的身份标 `UNKNOWN` 并停止交用户，不直接采纳。
- **报告**：`uv run --no-sync python scripts/injection-dev/_report.py <specs.jsonl>... [--out 报告.json]` → `HARD_GENERATION=REPORT ...`，计数字段显式输出零值（P4 教训：`Counter` 相加会丢零计数，消费方不得假定键存在）。演示帧口径只统计 PatternLock／RouteStick 的 `info/is_video_demo` 帧数，合格带 750～1050。

### 3.4 从规格到包内交付：`migrate_smvla_specs.py`（一次性，已执行）

包内 `src/robomme_hard/env_metadata/test-hard/xhard{1..4}/specs.jsonl`（每任务 20 局，共 1100 局）不是由上面两阶段直接产出，而是 12.206 把上次 SimpleMemVLA 评估用的 `smvla-0927{,-fill}` 快照迁移而来（用户 U-5「20 局走迁移」）。身份真源是 SimpleMemVLA `aab093f` 的六个 records 目录共 1100 行；h5 逐局重算 sha256／字节数／帧数并读 `setup` 核 seed 与档位。子命令 `build`／`check`／`export-s4-setup`，判定行 `SOURCE_POOL`、`SPECS_IDENTITY`、`DELIVERY_SET`、`H5_BINDING`、`TIER_MAX_STEPS_SOURCE`；排他发布，已存在拒绝覆盖。以后再加档或改规格走 3.2／3.3，不再走迁移。

`configs/newtask-v6/v6-02/` 四份 jsonl 是 S4 正式生成（每格 10 候选选 3 局）所用规格，与包内 20 局版本逐字节不同；`hard_regression.py s4-subset` 证明 S4 的 165 局是包内 1100 局的子集（回注点逐位、记录点 ≤ 1e-5）。

### 3.5 `site/`：只读出图与候选核对（不起环境）

| 工具 | 用途 | 判定行 |
|---|---|---|
| `v6_candidate_values.py --drafts ... --out` | 逐条核对 13 × 4 × 10 = 520 个梯度候选的实际取值落在配置区间内、身份覆盖、失败尝试信息齐全 | `CANDIDATE_VALUES=PASS|FAIL cells= candidates= mismatches= shortfall= input_errors=` |
| `v6_tier_monotone.py [--json]` | 静态检查计划表的档位单调性（`hard → xhard1 → … → xhard4` 每步至少一维严格上升、无下降）；`--reset-all` 真实 reset 诊断只在用户明确要求时跑 | `TIER_PLAN_TABLE` |
| `v6_v0_native_definitions.py --v5 <快照> --v6 <快照>` | 比较两代快照里冻结的原三档定义逐字相同（快照已删，须 `git show 7a6cee35:...` 取回） | `NATIVE_DEFS_UNCHANGED` |
| `v6_gt_lengths.py --records --site-dir` | 统计生成侧 h5 的演示段／执行段步数，写 `v6_gt_lengths.json` | `GT_LENGTHS` |
| `v6_site_catalog.py` → `v6_site.py --site-dir <目录> --port` | 从已验证交付媒体生成难度梯度网站目录并提供只读播放服务（白名单媒体、单段 Range） | `SITE_CATALOG`、`FLOW_LABELS`、`KNOWN_ISSUE_MATCH` |

默认 `sampling_config` 改读包内 `xhard4/specs.jsonl` header（`site_io.load_sampling_document`），与已删的 V6 快照逐任务相同。网站历史（site-v4 213 视频全测、site-v10 现行）见 `README-legacy.md` 第六节与 `docs/validation/newtask-v6/20260926-site.md`。

## 4. 对拍链路（`parity/`）

对拍分三层，从便宜到贵：**G1 静态守卫**（秒级，任何机器）→ **三侧 h5 对拍**（A40@greatlakes，16 worker）→ **回归**（S4 子集、reset 回放、评估冒烟）。

### 4.1 G1 守卫 `upstream_guard.py`

见 2.3。`build` 子命令从 git 对象重建 `src/robomme_hard/UPSTREAM.json`（双锚点、官方逐文件 sha256、shim 清单、vendor 清单、自校验哈希 `manifest_sha256`）；`--net` 在网络可达时 `git fetch` 官方复核 tree；`manifest-md` 输出 ③ 逐文件表。任何一行 FAIL 都不得起下面两层。

### 4.2 三侧对拍 `hard_parity.py`

**三侧是谁**：

| 侧 | 代码 | 起环境的方式 | 进程里导入的包 |
|---|---|---|---|
| O 官方 | vendor 编排 `d53f21a7` + 环境源码 `1fadc0ec` worktree | `train_split_runner.py --src-root <1fadc0ec worktree>` 调官方 `_worker` | `robomme` |
| P 修改前 | tag `pre-hard-split` worktree | 同上，`--src-root` 指该 worktree | `robomme` |
| H 修改后 | 拆包后 HEAD | `--force-mirror` + `ROBOMME_ENV_PACKAGE=robomme_hard`（native 档）；xhard 档走 `generate_h5.py --mode replay` | `robomme_hard` |

O／P 侧进程不得导入 `robomme_hard`（R5）。原三档身份清单 `subset_manifest.json`（16 任务 × 3 档 × 3 局 = 144）已随 `configs/newtask-v3/` 删除，需要时 `git show 6e70c0bf:scripts/configs/newtask-v3/subset_manifest.json` 取回；xhard 档 P 侧不重跑而是 `import-s4` 只读 symlink S4 交付存档（`S4_IMPORT=PASS rows=165 sha_mismatch=0`）。

**流转**（GL 节点 → NFS 暂存 → 本机 `/data` → bucket）：

```bash
# ① GL 节点生成（默认断言 GPU 为 A40，红线 R11；--dev-smoke 放行本机 Ada 只作开发冒烟 NATIVE_SMOKE）
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side O --tier native \
  --manifest <subset_manifest.json> --src-root <1fadc0ec worktree> \
  --workers 16 --gpu 0 --out /tmp/hs/O-native --stage <NFS>/hs-stage/O-native
# 每局 sha256 后搬到 --stage 并写 SHIPPED；--smoke N 只跑前 N 局（SHARD_SMOKE）；--resume 续跑

# ② sled-vail 逐局拉取：只拉带 SHIPPED 的局，重算 sha 相等才删 NFS 上的 h5/mp4
uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/hs-stage \
  --dest artifacts/newtask-v6/hard-split/h5 --segments O-native,P-native,H-native,H-xhard
# 段末出现 SEGMENT_DONE 后拉小文件并核 identities → PULL_SEGMENT=PASS|FAIL；全部段完 → PULL_DONE

# ③ 比对（本机，读 /data 拉回目录）
uv run --no-sync python scripts/parity/hard_parity.py compare --pair O:P --tier native --manifest <...> --calibrate
uv run --no-sync python scripts/parity/hard_parity.py compare --pair O:H --tier native --manifest <...>
uv run --no-sync python scripts/parity/hard_parity.py compare --pair P:H --tier xhard  --manifest <...>

# ④ 持久化到 bucket HongzeFu/robomme-hard-parity 并逐对象读回核 sha
uv run --no-sync python scripts/parity/hard_parity.py publish --side O --tier native --prefix O-1fadc0e-a40 \
  --gpu-model "NVIDIA A40" --driver <版本>   # → BUCKET_SYNC
```

**判定口径是「行为一致」，不是字节级**（用户 U-1）：mplib RRT 的墙钟预算让 16 worker 并发下同身份轨迹可能分叉（`docs/validation/newtask-v3/20260921-worker-nondeterminism.md`）。`compare` 分三层：

| 层 | 内容 | 结果 |
|---|---|---|
| 每侧自检 | 身份唯一、h5 `setup` 的 seed／difficulty 与身份一致、`timestep_*` 连续、数据集可读 | `SIDE_SELF_CHECK` |
| 判定层（全等才 PASS） | 身份集合；`setup`（seed、difficulty、task_goal、多选项、相机内参）；结构（数据集名／dtype／shape 集合，不比帧数）；任务成功相等且双侧各自成功（`both_success`）；包归属（`ENV_PACKAGE_BINDING`） | `PARITY_<pair>` 的 `identity_equal setup_equal schema_equal success_equal both_success binding_ok` |
| 容差层（U-19） | 共同前缀上的 `action_max`（`joint_action` 最大绝对差，rad）、`state_max`、`image_mad`（前视与腕视 RGB 逐像素平均绝对差的每身份均值，取最大）、`frames_max`；阈值只从 `configs/hard-parity-tolerances.json` 读（R21） | `tol=PASS action_max=实测/阈值 ...` |
| 参考层（INFO） | `sha_equal`、`frames_equal`、首个分叉时间步 | `PARITY_REFERENCE=INFO` |

容差文件由 `compare --pair O:P --calibrate` 按「O:P 最大值 × 1.5（帧数向上取整），下界 0.005/0.005/1.0/5，合理性上界 0.05/0.05/10/200」写入（U-22），只许 O:P 标定。现行值：`action_max_rad=0.0413`、`state_max=0.0411`、`image_mad=1.0`、`frames_max=5`（自 O:P 原始最大值 0.0275／0.0274／0.144／0）。改阈值须改该文件并写进留档。

**阶段 4 实测（2026-09-28，A40@greatlakes，`docs/validation/newtask-v6/hard-split/stage4.md`）**：

```text
PARITY_O_P=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 tol=PASS action_max=0.0275/0.0413 state_max=0.0274/0.0411 image_mad=0.144/1 frames_max=0/5 sha_equal=143 frames_equal=144 binding_ok=144 shape=16x3x3
PARITY_P_H=PASS tier=native compared=144 ... sha_equal=143 frames_equal=144 binding_ok=144 shape=16x3x3
PARITY_O_H=PASS tier=native compared=144 ... action_max=0/0.0413 state_max=0/0.0411 image_mad=0/1 frames_max=0/5 sha_equal=144 frames_equal=144 binding_ok=144 shape=16x3x3
PARITY_P_H=PASS tier=xhard compared=165 ... action_max=0/0.0413 ... sha_equal=165 frames_equal=165 binding_ok=165 shape=13x3x3+16x3
ENV_PACKAGE_BINDING=PASS sides=3 O=robomme P=robomme H=robomme_hard mismatch=0
```

读法：原三档 O↔H 144 对、xhard P(S4)↔H 165 对全部逐字节相同；O↔P、P↔H 各有同一对（PickHighlight/hard/seed 12300）在 P 侧那次运行中从第 549 步分叉，而 O 与 H 在该身份上逐字节相同，说明分叉只来自 P 侧那次运行的 RRT 墙钟噪声。bucket 上传当时因 HF 计费被拒（`BUCKET_SYNC=FAIL`），12.213 改公开后三侧 h5 全部上传并读回一致（762 对象）。

### 4.3 回归 `hard_regression.py`

| 子命令 | 算力 | 证明什么 | 判定行 |
|---|---|---|---|
| `s4-subset` | CPU | S4 交付 165 局 ⊂ 包内 test-hard 1100 局：seed 匹配、规格回注点逐位相等、记录点浮点差 ≤ `RECORDED_FLOAT_TOL=1e-5`（U-13 方案甲）；输出映射表 `env_metadata/test-hard/s4-to-delivery.json` | `S4_SUBSET` |
| `reset-replay --out` | GPU | 从 S4 每格取 candidate 最小的一局（13 × 3 + 16 = 55），经 builder 评估链 `make_env_for_episode` + `reset`，`spec_binding()` 摘要、`task_goal` 与多选项和 `s4-setup-manifest.json` 逐字比 | `HARD_RESET_REPLAY=PASS resets=55 replay=55 injected_mismatch=0 recorded_drift=6 max_abs=1.2e-07 goal_mismatch=0 errors=0 shape=13x3+16` |
| `eval-smoke [--task --episode --max-policy-steps]` | GPU，本机 1 任务 × 1 档 × 1 局 | 合作者入口可用 | `HARD_EVAL_SMOKE` |
| `xhw-reference` | CPU | Ada 原三档存档与 A40 O 侧的跨硬件参考（Ada≈A6000 逐位、A40 全面分叉，`hard-split/20260927-cross-hardware-probe.md`），不进总判定 | `XHW_REFERENCE=INFO` |

### 4.4 S0 基线设施 `train_split_*.py`

`train_split_runner.py` 是三条链路共用的**唯一起环境的运行器**：把官方源码目录接上 `sys.path`、按身份构造官方 `EpisodeJob`、用官方自己的 `ProcessPoolExecutor(spawn)` 调官方 `_worker`（A 路，`--src-root` 指官方源码树），或调镜像 worker `train_split_worker.run_one`（`--force-mirror`／`--sampling-config`／`--episode-specs`，只多传 `sampling_config`／`native_episode_spec`）。父进程不得先导入本仓库的 `robomme`，否则 spawn 子进程继承的 `sys.path` 会让官方源码被遮蔽。`--identity-source train_metadata|formula` 决定身份复核走官方 train 元数据逐字比还是 seed 公式硬校验；`--metadata-root` 须显式给官方 train 元数据目录（原默认 `configs/newtask-v3/official_train` 已删，`git show 6e70c0bf:...` 取回）；逐局追加 `results.partial.jsonl` 并 fsync，`--resume` 续跑。`train_split_config.py extract --pkg --release` 从源码提取 `sampling_config`；`train_split_parity/comparison/audit.py` 与 `comparator_fixtures.py` 是 S0 原始 train 五路逐位对拍的比较器（`compare_h5_pair` 等），现行只被单测与历史留档引用。

## 5. 评估链路

### 5.1 合作者看到的：`evaluation_hard.py` 与 `evaluation.py` 只差 4 处

```diff
- from robomme.env_record_wrapper import BenchmarkEnvBuilder
+ from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, TIER_MAX_STEPS
-         dataset="test",
+         dataset="test-hard",
-         env = env_builder.make_env_for_episode(episode)
+         seed, tier = env_builder.resolve_episode(episode)
+         env = env_builder.make_env_for_episode(episode, max_steps=TIER_MAX_STEPS[tier])
```

其余（`VideoRecorder`、`DummyModel`、循环与成功统计）与官方逐字相同。核查：`diff scripts/evaluation.py scripts/evaluation_hard.py` 应恰好是这三处 hunk。

### 5.2 builder 内部（`src/robomme_hard/env_record_wrapper/hard_builder.py`）

- `BenchmarkEnvBuilder` 子类化官方 builder，`_ALLOWED_DATASETS` 多一个 `test-hard`。官方父类 `__init__` 只认 `train/test/val` 且官方代码不能改，所以子类先以 `dataset="test"` 过父类校验再改回 `"test-hard"`，父类顺手读的 test 元数据随即清空（`dataset_for_parent` 绕行）。
- `test-hard` 的局序：xhard1 → xhard4 排列、档内按 `candidate` 升序；每任务 80 局（4 档 × 20），xhard4-only 的三个任务 20 局；16 任务合计 13 × 80 + 3 × 20 = 1100。`resolve_episode(episode)` 返回 `(seed, tier)`，与官方二元组同形；`resolve_identity(episode)` 只读返回 `{episode, tier, candidate, seed, spec_sha256, source_run}`。
- 步数上限按档：`TIER_MAX_STEPS = {xhard1: 1500, xhard2: 1700, xhard3: 2000, xhard4: 2600}`（U-6，沿用上次评估便于对比）；不逐局传就用构造时的 `max_steps`。
- `make_env_for_episode` 把包内规格作为 `native_episode_spec` 与 `sampling_config` 一并传给 `gym.make`，所以评估侧每局的场景就是生成侧冻结的那一局。`env_record_wrapper.spec_binding(env)`（须在 `reset()` 之后调用）给出回注摘要：回注点必须零差（`injected_mismatch=0`），记录点浮点差 ≤ 1e-5 计 `recorded_drift`。
- `train`／`test`／`val` 行为同官方；只有四个 Unmask 任务的 `train` 元数据改读本包 `env_metadata/train`（400 条）。

### 5.3 两个策略仓库的接入（阶段 6，`hard-split/stage6-eval-prep.md`）

两个策略仓库都从官方干净检出切分支、以子模块钉 benchmark 12.210（`SUBMODULE_PIN=PASS commit=31e6125 repos=2`），官方源码文件改动量受上限约束（`POLICY_DIFF=PASS repo=smvla src_files=3 src_lines=47(<=60)`、`repo=mmevla src_files=2 src_lines=34(<=45)`），其余全为新增脚本：

| 策略 | 切出点 | 分支 → 推到 | 改动实质 |
|---|---|---|---|
| SimpleMemVLA | `OpenBMB/SimpleMemVLA@c564c17` | `testhard-eval-0928-0134` → `hongzefu/SimpleMemVLA` | `robomme_env.py` 换 builder 与按档上限、`--resume` 放进自有 `testhard_eval.py` |
| MME-VLA | `RoboMME/robomme_policy_learning@ecf086c` | `official-testhard-eval-0928-0137` → `hongzefu/robomme_policy_learning_MotionJEPA` | `env_runner.py`／`eval.py` 换 builder；GL 分片脚本、`merge_eval_shards.py`；ManiSkill 用 `uv pip install --override` 钉到 benchmark 同一提交 |

GL 侧要点（细节以 `greatlakes.md` 为准）：一律 48 h 占位 job + `srun --overlap --gpu_cmode=shared`；计算节点有 HTTP 代理，server/client 进程须去掉代理变量并连 `127.0.0.1`；MME-VLA 新值档演示约 1419 帧，显存上限 0.4 不够、改 0.75。

### 5.4 阶段 7 实测（2026-09-28，两策略各 1100 局，`hard-split/stage7-eval.md`）

评估身份 `records/eval-identities-1100.jsonl`（xhard1/2/3 各 13 任务 × 20 局 + xhard4 16 任务 × 20 局 = 1100），每策略分两轮 55 格 × 10 局 = 550（U-9），10 张卡串接：

```text
EVAL_ROUND1=PASS policy=simplememvla episodes=550 normal=550 error_left=0 retries=0/55(max_per_shard=0) shards=10 per_shard=55-55 shape=55x10
EVAL_ROUND2=PASS policy=simplememvla episodes=550 normal=550 error_left=0 retries=0/55(max_per_shard=0) shards=10 per_shard=55-55 shape=55x10
EVAL_IDENTITY_SET=PASS policy=simplememvla rounds=2 shards=10 per_shard=55 episodes=1100 missing=0 extra=0 dup=0
EVAL_BINDING=PASS policy=simplememvla episodes=1100 replay=1100 injected_mismatch=0 recorded_drift=62 max_abs=1.2e-07 unused=0
EVAL_TIER_CAP=PASS policy=simplememvla episodes=1100 mismatch=0
EVAL_ROUND1=PASS policy=mmevla episodes=550 normal=550 error_left=0 retries=47/55(max_per_shard=9) shards=10 per_shard=55-55 shape=55x10
EVAL_ROUND2=PASS policy=mmevla episodes=550 normal=550 error_left=0 retries=0/55(max_per_shard=0) shards=10 per_shard=55-55 shape=55x10
EVAL_IDENTITY_SET=PASS policy=mmevla rounds=2 shards=10 per_shard=55 episodes=1100 missing=0 extra=0 dup=0
EVAL_BINDING=PASS policy=mmevla episodes=1100 replay=1100 injected_mismatch=0 recorded_drift=62 max_abs=1.2e-07 unused=0
EVAL_TIER_CAP=PASS policy=mmevla episodes=1100 mismatch=0
```

| 档 | 局数 | SimpleMemVLA 成功率 | MME-VLA 成功率 |
|---|---|---|---|
| xhard1 | 13 × 20 = 260 | 35.0% | 5.4% |
| xhard2 | 13 × 20 = 260 | 18.1% | 4.2% |
| xhard3 | 13 × 20 = 260 | 11.5% | 2.7% |
| xhard4 | 16 × 20 = 320 | 16.3% | 5.6% |

与上次 SimpleMemVLA 评估（benchmark `robomme` 12.191）同 1100 身份比：四档 success／fail／timeout 逐档完全相同，逐局终态 1100/1100 相同、步数 1099/1100 相同，唯一差异是一局 fail 的步数 463 → 494（RRT 墙钟噪声）。这说明拆包没有改变评估行为。MME-VLA 第一轮 47 次重跑全部是基础设施原因（server 显存、代理、记录缺陷），每片 ≤ 9、未超每轮 55 的硬上限。

## 6. 三条链路的共同约束与核查清单

**红线**（0927 计划第二部分 R1～R5、R11、R21）：

- R1 `src/robomme/**` 是官方原样，不放自有文件；R2 `parity/official/` 四文件不改、shim 不含逻辑。
- R3 `identity_sha256` 与 `delivery_sha256` 的覆盖范围不变，要变就换 `schema` 版本并重跑身份类闸门。
- R4 第二阶段回写只改 `selected`／`tried`／`rollout`，锁在 `<specs>.lock`，回写前整份 sha 必须与读入时相同。
- R5 同进程导入 `robomme_hard` 后 16 个 id 归它；O／P 侧对拍进程不得导入它。
- R11 对拍只在 A40@greatlakes 上生成，Ada 产物不混入 `PARITY_*`。
- R21 容差阈值只从 `configs/hard-parity-tolerances.json` 读。
- P3 reset／rollout 预算阈值（单 worker > 10、多 worker 合计 > 50 须一次性授权）；P5 局数一律写乘式。

**开工前秒级核查**（全部 CPU、不起环境）：

```bash
ls -1 scripts/*.py                                             # 恰好四个入口
git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py && echo 录像器零 diff
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream   # 末行 UPSTREAM_GUARD=PASS
diff scripts/evaluation.py scripts/evaluation_hard.py          # 恰好 4 处差异
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q   # 核心短测
```

**实跑前**：任何生成／对拍／评估一律先「单任务 × 单档 × 单局 × 单 worker」冒烟；超过 5 分钟的任务进 detached tmux 并挂日志监听（过滤 `NO RECORD`、`reset 拒绝`、`svulkan2`、`EXCLUSIVE`、`RRT`、`EXIT_CODE=`）；结果写 `docs/validation/`，过程写 commit body。

**取回已删文件**：

```bash
git show 6e70c0bf:scripts/configs/newtask-v3/subset_manifest.json      # 原三档 144 局清单
git show 7a6cee35:scripts/README.md                                      # V4/V5 完整说明（第二～五节）
git show 7a6cee35:scripts/configs/newtask-v5/sampling_config.json        # V5 快照
```
