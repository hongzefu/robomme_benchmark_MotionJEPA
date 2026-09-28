# scripts/ 说明

> 按 `newtaskRelease-v5` 12.214 写成。官方锚点：环境源码 `RoboMME/robomme_benchmark@1fadc0ec`（`src/robomme/` 与之逐字节相同）、生成编排 `d53f21a7`（`parity/official/` 四文件逐字节 vendor）。历史正文（V4/V5 逐环境字段表、V6 发布说明）见 [`README-legacy.md`](README-legacy.md)，不再维护。

# 第一部分　使用

## 1. 入口

| 文件 | 角色 | 说明 |
|---|---|---|
| `evaluation_hard.py` | 新值档评估入口 | 与 `evaluation.py` 只差 4 处（见第 2 节），跑 `dataset="test-hard"` |

`dataset_replay.py`、`evaluation.py`、`run_example.py` 与官方逐字节相同，用法见仓库根 `readme.md`。

## 2. `evaluation_hard.py` 与 `evaluation.py` 的 4 处差别

```diff
- from robomme.env_record_wrapper import BenchmarkEnvBuilder
+ from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, TIER_MAX_STEPS
-         dataset="test",
+         dataset="test-hard",
-         env = env_builder.make_env_for_episode(episode)
+         seed, tier = env_builder.resolve_episode(episode)
+         env = env_builder.make_env_for_episode(episode, max_steps=TIER_MAX_STEPS[tier])
```

| 处 | 差别 | 含义 |
|---|---|---|
| ① import | `robomme` → `robomme_hard`，多取 `TIER_MAX_STEPS` | `robomme_hard` 与官方包并列，builder 是官方 `BenchmarkEnvBuilder` 的子类，接口同形 |
| ② `dataset` | `"test"` → `"test-hard"` | `test` 每任务 50 局、三档混排；`test-hard` 每任务 80 局（xhard1 → xhard4 各 20 局，StopCube／InsertPeg／MoveCube 只有 xhard4 共 20 局），16 任务合计 1100 局 |
| ③ `resolve_episode` | 新增一行 | 返回 `(seed, tier)`，与官方二元组同形，只多了档位 |
| ④ `max_steps` | 按档传入 | `TIER_MAX_STEPS = {xhard1: 1500, xhard2: 1700, xhard3: 2000, xhard4: 2600}`；不逐局传就用构造时的 `max_steps` |

其余（`VideoRecorder`、`DummyModel`、循环、成功统计）逐字相同。核查：`diff scripts/evaluation.py scripts/evaluation_hard.py`。每局的场景由包内冻结规格回注，与生成侧同一局；`reset()` 后可用 `robomme_hard.env_record_wrapper.spec_binding(env)` 取回注摘要（回注点应零差）。

# 第二部分　开发者文档

## 3. 相对官方的文件差异

复现：`git diff --name-status 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9 HEAD -- . ':!docs' ':!artifacts'`。

| 区域 | 相对官方 |
|---|---|
| `src/robomme/**` | 零差异（102 文件）。受 P2 保护，改动须用户逐个批准 |
| `src/robomme_hard/**` | 全部新增（74 文件）：16 个环境类与改过的 utils／wrapper 为复制（33），依赖闭包干净的官方模块为借用 shim（18），`hard_builder.py` 子类化官方 builder 并新增 `dataset="test-hard"`，`hard_specs.py`／`utils/episode_spec.py` 等新增。逐文件表见 [`src/robomme_hard/README.md`](../src/robomme_hard/README.md) |
| `scripts/` | 官方三入口零差异；新增 `evaluation_hard.py`、`injection-dev/`、`parity/`、`configs/` |
| `tests/` | 新增 53 个文件，改 `conftest.py` |
| `pyproject.toml` | 加依赖 `pebble`；wheel 加 `src/robomme_hard`；加 pytest marker |
| `.gitignore` | 追加 `/artifacts/*` |
| `readme.md` | 「Data Generation」节仍指向已删的 `generate_dataset_newseed.py`，陈旧 |

为什么并列包：官方源码原样回退到 `1fadc0ec`，差异全部搬进 `robomme_hard`；导入它时 16 个环境 id 被 `register_env(override=True)` 接管，同进程要官方行为须另开只导入 `robomme` 的进程。

守卫（秒级、纯 CPU）：

```bash
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream   # 末行 UPSTREAM_GUARD=PASS
```

## 4. 生成新 episode 链路（`injection-dev/`）

**高层**：两阶段、一份 jsonl 为中心。第一阶段只 `reset` 抽候选并封存规格；第二阶段只读规格生成 h5，结束按状态机回写。规格（`schema="hard-specs/2"`）每行分「签」（`task tier candidate episode seed attempt spec spec_sha256`，由 `identity_sha256` 覆盖，不可改）与「结果」（`selected tried initial_selected rollout`，可回写）；`delivery_sha256` 锁正式交付集合。seed 公式 `offset(tier) + env_code × 100000 + episode × 100 + attempt`（`seed_layout.py`）。每格默认 10 候选选 3 局（index `0,3,6`）；局数写乘式，如 xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165。新值档不开 fail recover。

**调用接口**：

```bash
# 阶段一：定规则 → 抽签 → 封存（--dry-run 只打印预算；--self-check → FREEZE_ONLY_JSONL）
uv run --no-sync python scripts/injection-dev/freeze_specs.py \
  --tier xhard3 --tasks all --candidates-per-env 10 --select default \
  --max-reset-attempts 30 --workers 4 --gpus 0,1 --out <新路径>/specs.jsonl

# 阶段二 continue：跑每格 selected 且未生成的行，失败递补，结束持锁回写（--self-check → ROLLBACK_WRITE）
uv run --no-sync python scripts/injection-dev/generate_h5.py --mode continue \
  --specs <specs.jsonl> --output <输出目录> --workers 16 --gpu 0

# 阶段二 replay：按身份清单只读重放，不递补、不回写（对拍用；→ REPLAY_SET）
uv run --no-sync python scripts/injection-dev/generate_h5.py --mode replay \
  --identities <final-delivery.json> --output <输出目录>

# 报告（→ HARD_GENERATION=REPORT，计数字段显式输出零值）
uv run --no-sync python scripts/injection-dev/_report.py <specs.jsonl>... --out <报告.json>
```

- 真正起环境的是 `parity/train_split_runner.py` → `train_split_worker.run_one`（`gym.make(..., sampling_config=, native_episode_spec=)`），环境包由 `ROBOMME_ENV_PACKAGE` 决定（`--pkg` 默认 `robomme_hard`）。
- 回写只改 `selected`／`tried`／`rollout`，回写前整份 sha 必须与读入时相同（红线 R4）；基础设施失败每身份最多重跑 1 次，任务失败不重试。
- 预算红线（P3）：单 worker reset 总尝试 > 10 或多 worker 合计 > 50 须事先一次性授权，`--dry-run` 打印的数就是要报的数。
- 包内 `env_metadata/test-hard/xhard{1..4}/specs.jsonl`（1100 局）由 `migrate_smvla_specs.py` 一次性迁移而来，以后加档改规格走上面两阶段。`site/` 为只读出图与候选核对工具（`v6_candidate_values.py` → `CANDIDATE_VALUES`，`v6_tier_monotone.py` → `TIER_PLAN_TABLE`），不起环境。

## 5. 对拍链路（`parity/`）

**高层**：三层。① G1 静态守卫（第 3 节）；② 三侧 h5 对拍：O 官方（`d53f21a7` 编排 + `1fadc0ec` 源码）、P 修改前（tag `pre-hard-split`）、H 修改后（HEAD，`robomme_hard`），只在 A40@greatlakes 生成、16 worker；③ 回归。判定是「行为一致」不是字节级（RRT 墙钟预算让并发轨迹可能分叉）：身份／`setup`／结构／任务成功全等才 PASS，动作／状态／图像／帧数差异按 `configs/hard-parity-tolerances.json` 判（只许 O:P 标定：最大值 × 1.5，下界 0.005/0.005/1.0/5，上界 0.05/0.05/10/200），sha 相等数只作参考。O／P 侧进程不得导入 `robomme_hard`（R5）。

**调用接口**：

```bash
# ① GL 节点生成（断言 A40；每局 sha 后搬到 --stage 并写 SHIPPED；--smoke N 只跑前 N 局）
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side O --tier native \
  --manifest <subset_manifest.json> --src-root <1fadc0ec worktree> --workers 16 --gpu 0 \
  --out /tmp/hs/O-native --stage <NFS>/hs-stage/O-native
# ② 本机拉取：只拉带 SHIPPED 的局，sha 相等才删 NFS 副本（→ PULL_SEGMENT / PULL_DONE）
uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/hs-stage --dest <本机目录> --segments O-native,P-native,H-native,H-xhard
# ③ 比对（→ PARITY_<pair>；O:P 加 --calibrate 写容差文件）
uv run --no-sync python scripts/parity/hard_parity.py compare --pair O:H --tier native --manifest <subset_manifest.json>
# ④ 上传 bucket 并逐对象读回核 sha（→ BUCKET_SYNC）
uv run --no-sync python scripts/parity/hard_parity.py publish --side O --tier native --prefix O-1fadc0e-a40
# 回归：S4 165 局 ⊂ 包内 1100 局（CPU，→ S4_SUBSET）；55 次回注 reset 经评估链（GPU，→ HARD_RESET_REPLAY）；入口冒烟（→ HARD_EVAL_SMOKE）
uv run --no-sync python scripts/parity/hard_regression.py s4-subset
uv run --no-sync python scripts/parity/hard_regression.py reset-replay --out <目录>
uv run --no-sync python scripts/parity/hard_regression.py eval-smoke --task BinFill --episode 0
```

- 原三档 144 局清单（16 任务 × 3 档 × 3 局）已随 `configs/newtask-v3/` 删除：`git show 6e70c0bf:scripts/configs/newtask-v3/subset_manifest.json`。xhard 档 P 侧用 `hard_parity.py import-s4` 只读复用 S4 交付。
- 阶段 4 结论（`docs/validation/newtask-v6/hard-split/stage4.md`）：原三档 O↔H 144 对、xhard P↔H 165 对全部逐字节相同；O↔P 仅一对因 P 侧 RRT 噪声分叉且在容差内。
- `train_split_*.py` 是 S0 原始 train 基线设施；`train_split_runner.py` 同时是第 4 节的运行器。细表见 [`parity/README.md`](parity/README.md)。

## 6. 核查清单

```bash
ls -1 scripts/*.py                                                        # 恰好四个入口（P1）
git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py  # 录像器零 diff
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream
diff scripts/evaluation.py scripts/evaluation_hard.py                     # 恰好第 2 节的 4 处
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
```

实跑一律先「单任务 × 单档 × 单局 × 单 worker」冒烟；超过 5 分钟进 detached tmux 并监听日志；结果写 `docs/validation/`，过程写 commit body。
