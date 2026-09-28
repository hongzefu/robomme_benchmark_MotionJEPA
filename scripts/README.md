# scripts/ 说明

> 按 `newtaskRelease-v5` 12.214 写成。官方锚点：环境源码 `RoboMME/robomme_benchmark@1fadc0ec`（`src/robomme/` 与之逐字节相同）、生成编排 `d53f21a7`（`parity/official/` 四文件逐字节 vendor）。历史正文（V4/V5 逐环境字段表、V6 发布说明）见 [`docs/ledger/scripts-README-legacy-20260928.md`](../docs/ledger/scripts-README-legacy-20260928.md)，不再维护。

# 第一部分　使用

## 1. 入口：`evaluation_hard.py`

`scripts/` 顶层四个入口里，`dataset_replay.py`、`evaluation.py`、`run_example.py` 与官方逐字节相同，用法见仓库根 `readme.md`。新增的只有 `evaluation_hard.py`：跑新值档（xhard1～xhard4）的评估入口，与 `evaluation.py` 只差 4 处，其余逐字相同（核查：`diff scripts/evaluation.py scripts/evaluation_hard.py`）。

```diff
- from robomme.env_record_wrapper import BenchmarkEnvBuilder
+ from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, TIER_MAX_STEPS
-         dataset="test",
+         dataset="test-hard",
-         env = env_builder.make_env_for_episode(episode)
+         seed, tier = env_builder.resolve_episode(episode)
+         env = env_builder.make_env_for_episode(episode, max_steps=TIER_MAX_STEPS[tier])
```

四处差别用人话说：

1. **换包**。新值档的环境代码放在 `robomme_hard` 包里，与官方 `robomme` 并列、互不干扰。它的 builder 是官方 builder 的子类，用法一样，只是多认一个数据集名 `test-hard`。
2. **换数据集**。官方 `test` 每任务 50 局。`test-hard` 每任务 80 局：xhard1 到 xhard4 各 20 局、按档依次排列；StopCube、InsertPeg、MoveCube 只有 xhard4 这 20 局。16 任务合计 1100 局。
3. **多拿一个档位**。`resolve_episode` 和官方一样返回两个值，第二个值在 `test-hard` 下就是档位名（`xhard1`～`xhard4`）。
4. **步数上限按档给**。四档的上限分别是 1500、1700、2000、2600，用上一步拿到的档位查表后传给 `make_env_for_episode`。不传就用构造 builder 时的 `max_steps`。

### 每一局的场景从哪里来

每局的场景不是评估时随机抽的，而是生成数据时就冻结好、随包发布的。四份文件 `src/robomme_hard/env_metadata/test-hard/xhard1～4/specs.jsonl` 每行记一局：seed、档位、以及场景里每个随机取值点当时抽到的值（放了哪些块、什么颜色、放在哪、演示序列是什么）。

构造 builder 时，它读这四份文件，挑出本任务的正式局，按「xhard1 → xhard4、档内按候选号」排好，这就是 episode 号的顺序。`make_env_for_episode(i)` 做的事与官方相同（`gym.make` 再套 wrapper），只是在 `gym.make` 里多传两个参数：这局所属档位的取值配置（`sampling_config`），和这局冻结的场景规格（`native_episode_spec`）。

环境拿到这两个参数后，建场景时每个随机取值点照常抽一次随机数，但真正用的值是规格里冻结的那个。所以评估时建出的场景与生成数据时是同一局；抽到的值只用来核对随机流有没有漂移，不影响场景。`reset()` 之后可以调 `robomme_hard.env_record_wrapper.spec_binding(env)` 看核对结果，正常应该零差。

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

## 3. 四档配置对比与 episode 长度

**配置对比**（一句话版；完整定稿表与备注见 [`src/robomme_hard/README.md`](../src/robomme_hard/README.md) ②，源自 `docs/plans/0925-newtask-release-v6-plan.md` 第一部分 §三）。列格式 hard → xhard1 → xhard2 → xhard3 → xhard4；`[a,b]` 为整数均匀区间。

| 环境 | 梯度维度 | hard | xhard1 | xhard2 | xhard3 | xhard4 |
|---|---|---|---|---|---|---|
| BinFill | 投入块数（总块固定 12） | [3,5] | 6 | 7 | 8 | 9 |
| PickXtimes | 抓取次数 / 干扰块 | [4,5] / 0 | [6,7] / 1 | [8,9] / 2 | [10,12] / 3 | [13,15] / 3 |
| SwingXtimes | 摆动轮数 / 干扰块 | 3 / 0 | [4,5] / 1 | [6,7] / 2 | [8,9] / 3 | [10,11] / 3 |
| PickHighlight | pick 数 / 总块 | 3 / 6 | 4 / 7 | 5 / 8 | 6 / 9 | 7 / 10 |
| VideoUnmask | 干扰容器 / pick | 0 / 2 | 8 / 2 | 10 / 3 | 13 / 3 | 15 / 3 |
| ButtonUnmask | 干扰容器 / pick | 0 / 2 | 8 / 2 | 10 / 3 | 12 / 3 | 14 / 3 |
| VideoUnmaskSwap | swap / pick / 外环干扰 | [2,3] / 2 / 0 | [4,5] / 2 / 4 | [6,7] / 3 / 6 | [8,9] / 3 / 8 | [10,12] / 3 / 10 |
| ButtonUnmaskSwap | swap / pick / 外环干扰 | [2,3] / 2 / 0 | 4 / 2 / 4 | 5 / 3 / 6 | [6,7] / 3 / 8 | [8,9] / 3 / 10 |
| VideoRepick | 块数 / swap / repick | 另一种任务 | 4 / [3,4] / 2 | 5 / [5,6] / 3 | 6 / [7,8] / 4 | 7 / [9,12] / [5,6] |
| PatternLock | 节点数（5×5 不重访） | [4,8] | [9,12] | [13,16] | [17,20] | [21,25] |
| RouteStick | 段数 L（执行段 = 50·L） | [4,7] | [8,10] | [11,13] | [14,16] | [17,21] |
| VideoPlaceButton | 放台次数 | 2（放桌面） | 1 块 3 次 | 1 块 4 次 | 2 块 5 次 | 2 块 6 次 |
| VideoPlaceOrder | 总放台次数 | 1 块 [2,4] | 2 块 5 | 2 块 6 | 2 块 7 | 2 块 8 |
| MoveCube | 不加档 | 原三档同值 | — | — | — | 圆环 U |
| InsertPeg / StopCube | 不加档 | 原三档同值 | — | — | — | 原 xhard 改名，数值不动 |

**episode 长度**（步数均值，格式 演示段 / 执行段 / 全部；源 `injection-dev/site/v6_gt_lengths.json`，由 `site/v6_gt_lengths.py` 统计生成侧 h5：步数 = `timestep_*` 个数，演示段 = `info/is_video_demo` 为真的时刻）。hard 列取原版示例目录每任务 9 局；xhard 列取包内 test-hard 每格 20 局。

| 环境 | hard | xhard1 | xhard2 | xhard3 | xhard4 |
|---|---|---|---|---|---|
| BinFill | 0 / 665 / 665 | 0 / 1177 / 1177 | 0 / 1352 / 1352 | 0 / 1514 / 1514 | 0 / 1710 / 1710 |
| PickXtimes | 0 / 637 / 637 | 0 / 1056 / 1056 | 0 / 1314 / 1314 | 0 / 1704 / 1704 | 0 / 2180 / 2180 |
| SwingXtimes | 0 / 475 / 475 | 0 / 611 / 611 | 0 / 779 / 779 | 0 / 916 / 916 | 0 / 1106 / 1106 |
| StopCube | 0 / 308 / 308 | — | — | — | 0 / 631 / 631 |
| VideoUnmask | 66 / 195 / 261 | 66 / 259 / 325 | 66 / 409 / 475 | 66 / 410 / 476 | 66 / 405 / 471 |
| ButtonUnmask | 0 / 317 / 317 | 0 / 373 / 373 | 0 / 522 / 522 | 0 / 520 / 520 | 0 / 525 / 525 |
| VideoUnmaskSwap | 161 / 195 / 356 | 288 / 259 / 548 | 287 / 411 / 699 | 344 / 407 / 752 | 432 / 407 / 838 |
| ButtonUnmaskSwap | 0 / 446 / 446 | 0 / 518 / 518 | 0 / 626 / 626 | 0 / 676 / 676 | 0 / 741 / 741 |
| VideoRepick | 272 / 466 / 738 | 390 / 401 / 791 | 494 / 547 / 1041 | 595 / 663 / 1258 | 746 / 929 / 1675 |
| VideoPlaceButton | 758 / 240 / 998 | 927 / 201 / 1128 | 1098 / 199 / 1297 | 1544 / 202 / 1745 | 1723 / 203 / 1926 |
| VideoPlaceOrder | 1016 / 241 / 1257 | 1428 / 200 / 1628 | 1629 / 205 / 1834 | 1783 / 204 / 1987 | 1953 / 206 / 2160 |
| PickHighlight | 0 / 434 / 434 | 0 / 874 / 874 | 0 / 1041 / 1041 | 0 / 1200 / 1200 | 0 / 1366 / 1366 |
| MoveCube | 230 / 186 / 416 | — | — | — | 247 / 185 / 432 |
| InsertPeg | 243 / 244 / 487 | — | — | — | 234 / 230 / 464 |
| PatternLock | 104 / 104 / 207 | 357 / 357 / 714 | 476 / 476 / 952 | 588 / 588 / 1176 | 714 / 714 / 1427 |
| RouteStick | 189 / 189 / 378 | 460 / 460 / 920 | 602 / 602 / 1205 | 745 / 745 / 1490 | 952 / 952 / 1905 |

按档步数上限 `TIER_MAX_STEPS`（1500 / 1700 / 2000 / 2600）只约束执行段；演示段不计入。

# 第二部分　开发者文档

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
- `train_split_*.py` 是 S0 原始 train 基线设施；`train_split_runner.py` 同时是第 4 节的运行器。细表见 [`parity/README.md`](parity/README.md)。

## 6. 核查清单

```bash
ls -1 scripts/*.py                                                        # 恰好四个入口（P1）
git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py  # 录像器零 diff
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream
diff scripts/evaluation.py scripts/evaluation_hard.py                     # 恰好第 1 节的 4 处
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
```

实跑一律先「单任务 × 单档 × 单局 × 单 worker」冒烟；超过 5 分钟进 detached tmux 并监听日志；结果写 `docs/validation/`，过程写 commit body。
