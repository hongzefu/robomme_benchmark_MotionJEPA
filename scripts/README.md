# scripts/ 说明

> 按 `newtaskRelease-v5` 12.214 写成。官方锚点：环境源码 `RoboMME/robomme_benchmark@1fadc0ec`（`src/robomme/` 与之逐字节相同）、生成编排 `d53f21a7`（`parity/official/` 四文件逐字节 vendor）。历史正文（V4/V5 逐环境字段表、V6 发布说明）见 [`README-legacy.md`](README-legacy.md)，不再维护。

# 第一部分　使用

## 1. 入口：`evaluation_hard.py`

`scripts/` 顶层四个入口里，`dataset_replay.py`、`evaluation.py`、`run_example.py` 与官方逐字节相同，用法见仓库根 `readme.md`。新增的只有 `evaluation_hard.py`：新值档（xhard1～xhard4）的评估入口，跑 `dataset="test-hard"`，与 `evaluation.py` 只差 4 处。

```diff
- from robomme.env_record_wrapper import BenchmarkEnvBuilder
+ from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, TIER_MAX_STEPS
-         dataset="test",
+         dataset="test-hard",
-         env = env_builder.make_env_for_episode(episode)
+         seed, tier = env_builder.resolve_episode(episode)
+         env = env_builder.make_env_for_episode(episode, max_steps=TIER_MAX_STEPS[tier])
```

第一处是 import：`robomme_hard` 是与官方 `robomme` 并列的包，它的 `BenchmarkEnvBuilder` 是官方同名类的子类，构造参数与方法名完全同形，只多认一个 `dataset="test-hard"`；另外多取一个 `TIER_MAX_STEPS`，值是 `{xhard1: 1500, xhard2: 1700, xhard3: 2000, xhard4: 2600}`。

第二处是 `dataset`。官方 `test` 每任务 50 局、三档混排。`test-hard` 每任务 80 局，按 xhard1 → xhard4 排列、每档 20 局、档内按候选号升序；StopCube、InsertPeg、MoveCube 只有 xhard4，各 20 局。16 任务合计 13 × 80 + 3 × 20 = 1100 局。构造 builder 时它把包内四份规格文件 `src/robomme_hard/env_metadata/test-hard/xhard{1..4}/specs.jsonl` 各读一次并做封套校验，挑出本任务已交付的正式局，按上面的顺序编成 episode 号。

第三处是 `resolve_episode`。官方返回 `(seed, difficulty)`；这里同样返回二元组，只是 `test-hard` 下第二项就是档位名 `xhard1`～`xhard4`，所以循环里多写一行拿到 `tier`，再用它查按档步数上限传给第四处的 `max_steps`。不逐局传就沿用构造时的 `max_steps`。

### 规格 jsonl 是怎么被读进环境的

**构造 builder 时读文件。** `BenchmarkEnvBuilder(env_id, dataset="test-hard")` 先以 `dataset="test"` 走一遍官方父类构造（父类只认 `train/test/val`，官方代码不能改），再把 `self.dataset` 改回 `"test-hard"`、清空父类顺手读的 test 元数据，然后调 `_test_hard_entries(env_id)`。这个函数对 xhard1～xhard4 四个档各调一次 `hard_specs.load_specs(packaged_specs_path(tier))`：路径是包内 `src/robomme_hard/env_metadata/test-hard/<tier>/specs.jsonl`，按行读 JSON，第一行是 header、其余每行一局，`validate_specs` 核封套（键集合、状态值），源码指纹不符只警告。每档结果 `lru_cache` 只读一次。然后按本任务筛出 `delivered` 的行（`selected` 为真且 `rollout.status=="ok"`），按 `candidate` 升序，行数必须恰好等于 header 的 `delivery_per_cell`（不在 55 格表里的档为 0），把每行连同 header 里的 `sampling_config[env_id]`、`runtime`、`recovery_rule` 打成一个 entry；四档依次拼接后 `enumerate` 成 `self._episode_map`，episode 号就是这个顺序。

**`resolve_episode(i)`** 只是查 `_episode_map[i]`，返回 `(row["seed"], tier)`。

**`make_env_for_episode(i, max_steps)`** 与官方同名方法逐项同构，多出一步 `_hard_env_kwargs(i)`：取 entry，核对 header `runtime` 里的 `obs_mode`、`control_mode`、`reward_mode` 与构建器一致，然后在官方原有的 `gym.make(env_id, obs_mode=..., control_mode=..., render_mode=..., reward_mode=..., seed=, difficulty=)` 参数上再加两项：

- `sampling_config=entry["sampling_config"]`：该任务在这档的取值配置，含 `decision`（按档新值）与 `native`（原三档参数）两块；
- `native_episode_spec=entry["row"]["spec"]`：该局冻结的场景规格，一棵按路径组织的值树（如 `layout.board.offsets`、`objects.color_pool`）。

之后套的 `DemonstrationWrapper` 换成 `robomme_hard` 下的同名类，参数原样透传。

**`gym.make` 之后环境怎么用这两项。** 每个环境类的 `__init__` 多收这两个关键字参数，在任何随机数调用之前先做两件事：`_resolve_sampling_config` 把传入的配置与源码默认值合并成 `self._sampling`；`SpecRecorder(native_episode_spec, task, {"seed": seed}, difficulty=...)` 建成 `self._spec`。场景生成代码里每个取值点都写成 `self._spec.value("<路径>", <原抽样结果>)`：原抽样照常执行（随机流不漂移），但传了 `native_episode_spec` 时 `value()` 一律返回冻结规格里该路径的值、把抽样值记进 `trace`，两者不等时记一条 `mismatches`；不传时 `value()` 原样返回抽样值并把它记进导出文档（这就是生成链路第一阶段导出规格的方式）。`record()` 点只留痕不回注。因此评估侧每局建出的场景与生成侧是同一局。`reset()` 之后可用 `robomme_hard.env_record_wrapper.spec_binding(env)` 读 `env.unwrapped._spec` 取摘要：回注点（`source="spec"`）应零差，记录点浮点差 ≤ 1e-5 计 `recorded_drift`。

其余部分（`VideoRecorder`、`DummyModel`、循环、成功统计）逐字相同，核查命令 `diff scripts/evaluation.py scripts/evaluation_hard.py`。

## 2. 相对官方的文件差异

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

# 第二部分　开发者文档

## 3. 生成新 episode 链路（`injection-dev/`）

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

## 4. 对拍链路（`parity/`）

**高层**：三层。① G1 静态守卫（第 2 节）；② 三侧 h5 对拍：O 官方（`d53f21a7` 编排 + `1fadc0ec` 源码）、P 修改前（tag `pre-hard-split`）、H 修改后（HEAD，`robomme_hard`），只在 A40@greatlakes 生成、16 worker；③ 回归。判定是「行为一致」不是字节级（RRT 墙钟预算让并发轨迹可能分叉）：身份／`setup`／结构／任务成功全等才 PASS，动作／状态／图像／帧数差异按 `configs/hard-parity-tolerances.json` 判（只许 O:P 标定：最大值 × 1.5，下界 0.005/0.005/1.0/5，上界 0.05/0.05/10/200），sha 相等数只作参考。O／P 侧进程不得导入 `robomme_hard`（R5）。

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
- `train_split_*.py` 是 S0 原始 train 基线设施；`train_split_runner.py` 同时是第 3 节的运行器。细表见 [`parity/README.md`](parity/README.md)。

## 5. 核查清单

```bash
ls -1 scripts/*.py                                                        # 恰好四个入口（P1）
git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py  # 录像器零 diff
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream
diff scripts/evaluation.py scripts/evaluation_hard.py                     # 恰好第 1 节的 4 处
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
```

实跑一律先「单任务 × 单档 × 单局 × 单 worker」冒烟；超过 5 分钟进 detached tmux 并监听日志；结果写 `docs/validation/`，过程写 commit body。
