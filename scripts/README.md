# scripts/ 说明

> 按 `newtaskRelease-v5` 12.214 写成，v7（12.237 起，方案 `docs/plans/0928-newtask-v7-xhard0-shared-layout-plan.md`）更新第 1、3、4、5 节：新增 xhard0 档、xhard1～4 共用 20 个母布局、五档定值。v8（阶段 3b 换包起，方案 `1001-newtask-v8-xhard-gradient-plan.md`）再更新第 1、3、4、5 节：新值档扩到 xhard1～xhard5、只交付 43 格（1070 局）、各格布局独立抽、步数上限 xhard1～5 一律 1600。官方锚点：环境源码 `RoboMME/robomme_benchmark@1fadc0ec`（`src/robomme/` 与之逐字节相同）、生成编排 `d53f21a7`（`parity/official/` 四文件逐字节 vendor）。历史正文（V4/V5 逐环境字段表、V6 发布说明）见 [`docs/ledger/scripts-README-legacy-20260928.md`](../docs/ledger/scripts-README-legacy-20260928.md)，不再维护。

# 第一部分　使用

## 1. 入口：`evaluation_hard.py`

`scripts/` 顶层四个入口里，`dataset_replay.py`、`evaluation.py`、`run_example.py` 与官方逐字节相同，用法见仓库根 `readme.md`。新增的只有 `evaluation_hard.py`：跑六档（xhard0～xhard5）的评估入口，与 `evaluation.py` 只差 4 处，其余逐字相同（核查：`diff scripts/evaluation.py scripts/evaluation_hard.py`）。

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
2. **换数据集**。官方 `test` 每任务 50 局。`test-hard` 每任务先是 xhard0 的 12 局，再按 xhard1→xhard5 排该任务交付的档（每格局数见第 3 节局数表）：PickXtimes 12 + 17 + 17 + 16 = 62 局；SwingXtimes、StopCube 12 + 五档各 10 = 62 局；VideoUnmask、ButtonUnmask 12 + 四档各 20 = 92 局；BinFill、两个 Swap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、VideoRepick 12 + 两档各 40 = 92 局；RouteStick、PatternLock 12 + 27 + 27 + 26 = 92 局；MoveCube、InsertPeg 12 + xhard4 20 = 32 局。合计 1262 局（xhard0 16 任务 × 12 = 192，新值档 43 格共 1070）。
3. **多拿一个档位**。`resolve_episode` 和官方一样返回两个值，第二个值在 `test-hard` 下就是档位名（`xhard0`～`xhard5`）。
4. **步数上限按档给**。xhard0 1300，xhard1～xhard5 一律 1600（`TIER_MAX_STEPS`），用上一步拿到的档位查表后传给 `make_env_for_episode`。不传就用构造 builder 时的 `max_steps`。xhard0 的 1300 与官方 `evaluation.py` 默认值相同；1600 是 v8 抽样时的执行步上限，交付集按构造不超（见第 3 节末）。

### 每一局的场景从哪里来

**xhard0** 就是官方 `test` 里 `difficulty="hard"` 的那 12 局（每任务 50 局里挑出 hard 的），seed 与原 episode 号不变，环境走官方原生 hard 分支现场抽，不读任何规格文件（`spec_binding` 里 `mode=export`）。它是新值档的起点，用来和 xhard1 对比。

**xhard1～xhard5** 的场景不是评估时随机抽的，而是生成数据时就冻结好、随包发布的。五份文件 `src/robomme_hard/env_metadata/test-hard/xhard1～5/specs.jsonl`（`schema="hard-specs/4"`）每行记一局：seed、档位、以及场景里每个随机取值点当时抽到的值（放了哪些块、什么颜色、放在哪、演示序列是什么）。每份只含本档交付格的任务（xhard5 只有 SwingXtimes、StopCube）。v8 起**各档布局独立抽**：每档用自己的 seed 段（xhard1 16e6 起，每档隔 2e6）逐任务抽签，`layout_parent` 全为空，档与档之间不共用布局（v7 曾让四档共用 xhard4 的 20 个母布局，见标签 `parity-anchor-v7`）。

构造 builder 时，它先列出本任务的 xhard0 局，再用 `load_specs_v8` 读这五份文件（整根校验：逐档封套、逐格局数等于交付格表、跨档 seed 不交），挑出本任务的正式局，按「xhard1 → xhard5、档内按候选号」排在后面，这就是 episode 号的顺序；(任务, 档) 不在交付格表 `EXPECTED_CELLS` 内却有正式局即报错。`make_env_for_episode(i)` 做的事与官方相同（`gym.make` 再套 wrapper），只是在 `gym.make` 里多传两个参数：这局所属档位的取值配置（`sampling_config`），和这局冻结的场景规格（`native_episode_spec`）。

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

## 3. 六档配置对比、局数与 episode 长度

**配置对比**（v8，源 `docs/plans/1001-newtask-v8-xhard-gradient-plan.md` 第一部分表 1；代码真源为各环境的 `native_blocks` 与包内 header 的 `sampling_config`，测试侧副本 `tests/_shared/v7_tier_values.py`）。xhard0 列就是官方 hard 配置（`[a,b]` 为整数均匀区间；RouteStick、PatternLock 的 xhard1～3 也是区间：RouteStick 在区间内均匀抽，PatternLock 拒绝采样、只保证落在区间内）。「不交付」= 数值仍在代码里、v8 不生成；「无」= 该任务没有这个档的配置。各档布局独立抽。v7 的五档表见标签 `parity-anchor-v7` 下的本文件。

| 环境 | 梯度维度 | xhard0（官方 hard） | xhard1 | xhard2 | xhard3 | xhard4 | xhard5 |
|---|---|---|---|---|---|---|---|
| PickXtimes | 抓取次数 / 干扰块 | [4,5] / 0 | 6 / 1 | 7 / 2 | 8 / 3 | 9 / 4，不交付 | 无 |
| SwingXtimes | 摆动轮数 / 干扰块 | 3 / 0 | 4 / 1 | 5 / 2 | 6 / 3 | 7 / 4 | 8 / 4 |
| StopCube | 停止序号 `stop_time` / 方块速度 `move_interval` | [2,5] / 60、80、120 随机 | 6 / 60 | 7 / 60 | 8 / 60 | 9 / 60 | 10 / 60 |
| BinFill | 投入块数（总块固定 12） | [3,5] | 6 | 7 | 8，不交付 | 9，不交付 | 无 |
| VideoUnmask | 干扰容器（含 cube 数）/ pick | 0 / 2 | 4（2）/ 2 | 4（2）/ 3 | 8（4）/ 3 | 12（6）/ 3 | 无 |
| ButtonUnmask | 干扰容器（含 cube 数）/ pick | 0 / 2 | 4（2）/ 2 | 4（2）/ 3 | 8（4）/ 3 | 12（6）/ 3 | 无 |
| VideoUnmaskSwap | swap / pick / 外环干扰（含 cube 数） | [2,3] / 2 / 0 | 5 / 2 / 2（1） | 7 / 3 / 4（2） | 9 / 3 / 6（3），不交付 | 11 / 3 / 8（4），不交付 | 无 |
| ButtonUnmaskSwap | swap / pick / 外环干扰（含 cube 数） | [2,3] / 2 / 0 | 3 / 2 / 2（1） | 5 / 3 / 4（2） | 7 / 3 / 6（3），不交付 | 9 / 3 / 8（4），不交付 | 无 |
| VideoRepick | 块数 / swap / repick | 另一种任务 | 4 / 4 / 2 | 5 / 6 / 3 | 6 / 8 / 4，不交付 | 7 / 10 / 5，不交付 | 无 |
| PickHighlight | pick 数 / 总块 | 3 / 6 | 4 / 7 | 5 / 8 | 6 / 9，不交付 | 7 / 10，不交付 | 无 |
| PatternLock | 节点数（5×5 不重访） | [4,8] | [9,12] | [13,15] | [16,18] | 21，不交付 | 无 |
| RouteStick | 段数 L（执行段 = 50·L） | [4,7] | [8,10] | [11,13] | [14,16] | 19，不交付 | 无 |
| VideoPlaceButton | 放台次数 | 2（放桌面） | 1 块 3 次 | 1 块 4 次 | 2 块 5 次，不交付 | 2 块 6 次，不交付 | 无 |
| VideoPlaceOrder | 总放台次数 | 1 块 [2,4] | 2 块 5 | 2 块 6 | 2 块 7，不交付 | 2 块 8，不交付 | 无 |
| MoveCube | 不加档 | 官方 hard | 无 | 无 | 无 | 圆环 U | 无 |
| InsertPeg | 不加档 | 官方 hard | 无 | 无 | 无 | 原 xhard 改名，数值不动 | 无 |

**局数**（v8 交付格表 `hard_specs.EXPECTED_CELLS`＝`V8_CELLS`，43 格；方案第一部分表 2）：

| 任务 | xhard0 | xhard1 | xhard2 | xhard3 | xhard4 | xhard5 | 合计 |
|---|---|---|---|---|---|---|---|
| PickXtimes | 12 | 17 | 17 | 16 | — | — | 62 |
| SwingXtimes、StopCube | 12 | 10 | 10 | 10 | 10 | 10 | 各 62 |
| VideoUnmask、ButtonUnmask | 12 | 20 | 20 | 20 | 20 | — | 各 92 |
| BinFill、VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、VideoRepick | 12 | 40 | 40 | — | — | — | 各 92 |
| RouteStick、PatternLock | 12 | 27 | 27 | 26 | — | — | 各 92 |
| MoveCube、InsertPeg | 12 | — | — | — | 20 | — | 各 32 |
| **合计** | 192 | 411 | 411 | 128 | 100 | 20 | **1262** |

**episode 长度**（以下为 **v7** 实测步数均值，供参考；v8 各格取值与局数已变，v8 长度以 `hard_regression.py step-headroom` 在 v8 交付上的报告为准，本节暂未换表。格式 演示段 / 执行段 / 全部；步数 = h5 里 `timestep_*` 个数，演示段 = `info/is_video_demo` 为真的时刻）。xhard1～4 取 v7 gen1 交付每格 20 局（`hard_regression.py step-headroom` 报告的 `per_cell_mean`，`artifacts/newtask-v7/step-headroom-gen1.json`）；xhard0 取 xhard0 O:H 对拍 H 侧 16 任务 × 12 局中生成成功的 190 局（VideoPlaceOrder 两局官方原版即生成失败）。v6 的旧表见本文件 12.237 以前的版本。

| 环境 | xhard0 | xhard1 | xhard2 | xhard3 | xhard4 |
|---|---|---|---|---|---|
| PickXtimes | 0 / 803 / 803 | 0 / 1154 / 1154 | 0 / 1588 / 1588 | 0 / 1889 / 1889 | 0 / 2354 / 2354 |
| StopCube | 0 / 250 / 250 | — | — | — | 0 / 661 / 661 |
| SwingXtimes | 0 / 500 / 500 | 0 / 666 / 666 | 0 / 831 / 831 | 0 / 996 / 996 | 0 / 1161 / 1161 |
| BinFill | 0 / 892 / 892 | 0 / 1161 / 1161 | 0 / 1338 / 1338 | 0 / 1518 / 1518 | 0 / 1689 / 1689 |
| VideoUnmaskSwap | 204 / 263 / 467 | 318 / 253 / 571 | 300 / 403 / 703 | 366 / 405 / 771 | 432 / 403 / 835 |
| VideoUnmask | 66 / 268 / 334 | 66 / 260 / 326 | 66 / 410 / 476 | 66 / 410 / 476 | 66 / 409 / 475 |
| ButtonUnmaskSwap | 0 / 468 / 468 | 0 / 474 / 474 | 0 / 627 / 627 | 0 / 689 / 689 | 0 / 760 / 760 |
| ButtonUnmask | 0 / 389 / 389 | 0 / 372 / 372 | 0 / 521 / 521 | 0 / 521 / 521 | 0 / 521 / 521 |
| VideoRepick | 174 / 440 / 614 | 413 / 398 / 812 | 526 / 532 / 1059 | 619 / 704 / 1323 | 718 / 817 / 1535 |
| VideoPlaceButton | 752 / 212 / 964 | 938 / 208 / 1146 | 1104 / 207 / 1311 | 1552 / 201 / 1753 | 1708 / 201 / 1908 |
| VideoPlaceOrder | 911 / 214 / 1125 | 1438 / 205 / 1644 | 1600 / 199 / 1799 | 1770 / 201 / 1970 | 1930 / 201 / 2131 |
| PickHighlight | 0 / 548 / 548 | 0 / 870 / 870 | 0 / 1037 / 1037 | 0 / 1221 / 1221 | 0 / 1368 / 1368 |
| InsertPeg | 238 / 238 / 476 | — | — | — | 232 / 230 / 462 |
| MoveCube | 234 / 181 / 415 | — | — | — | 233 / 191 / 424 |
| PatternLock | 171 / 171 / 342 | 374 / 374 / 748 | 480 / 480 / 960 | 583 / 583 / 1166 | 686 / 686 / 1372 |
| RouteStick | 267 / 267 / 534 | 500 / 500 / 1000 | 650 / 650 / 1300 | 800 / 800 / 1600 | 950 / 950 / 1900 |

按档步数上限 `TIER_MAX_STEPS`（v8：xhard0 1300 / xhard1～xhard5 一律 1600）只约束执行段；演示段不计入。v8 抽样时全部任务过滤执行步超过 1600 的候选（记 `exec_over_cap` 并递补），交付集按构造不超，闸门 `V8_STEP_CAP`（`hard_regression.py step-headroom`，xhard0 按 1300 单独查）。历史：v7 为 1500 / 2400 / 2900 / 3800（B4 上调），v6 为 1500 / 1700 / 2000 / 2600。

# 第二部分　开发者文档

## 4. 生成新 episode 链路（`injection-dev/`）

**高层**：v8 是两阶段、五份 jsonl 为中心——**每档抽签 → 生成（可四席分片）并合并聚合**。
1. **抽签**（`freeze_specs.py --tier <档> --seed-profile v8 --cells full`，每档一次）：只抽交付格（`--cells`：`full` 43 格、`smoke` 7 格、`shard1～4` 或格表 JSON），档内逐任务独立抽；逐任务候选数、选取区间与 reset 上限用 `--candidates-per-env TASK=N,...`、`--select TASK=a..b,...`、`--task-max-reset-attempts TASK[@TIER]=N,...` 给出；MoveCube 保留运动方式分层。
2. **生成**（`generate_h5.py --mode continue --specs <规格根> --cells full`）：按 header schema 分派到 v8 驱动，逐格递补；执行步（h5 `timestep_*` 数减演示帧）超过 1600 的局记 `status=failed`、`error_type=exec_over_cap` 并同格递补；某格备用候选耗尽即 FAIL。四席分片走 `split` → 各片 `continue` → `merge`（写封存规格根与 `delivery.json`），`aggregate --rebase` 用于整树搬迁后重算。

规格 `schema="hard-specs/4"`：每行分「签」（`task tier candidate episode seed attempt spec spec_sha256 layout_parent`，由 `identity_sha256` 覆盖，不可改）与「结果」（`selected tried initial_selected rollout`，可回写；v8 的 `rollout` 另带 `exec_steps`）；`delivery_sha256` 锁正式交付集合；header 另签 `exec_cap`（＝1600）与逐任务 `delivery_per_cell`，`select_rule`／`per_env` 为逐任务字典，`layout_rule={"mode":"independent"}`、`layout_parent` 全为空。seed 公式 `offset + env_code × 100000 + episode × 100 + attempt`，v8 按档 offset：xhard1 16e6、xhard2 18e6、xhard3 20e6、xhard4 22e6、xhard5 24e6（`hard_specs.seed_rule_for(tier, "v8")`，档与档两两不交）。新值档不开 fail recover。v7 的「母布局抽签 → `derive_specs.py` 派生 → 四档同步生成」链路与 `layout-shared`／`prefix-geometry` 守卫保留，v8 不调用，换包后只对 v7 合成夹具可用。

**调用接口**（v8 实跑口径，GL 四席分片）：

```bash
# 阶段一：每档抽签（只抽交付格；--dry-run 只打印逐格候选数与 reset 上限）
uv run --no-sync python scripts/injection-dev/freeze_specs.py --tier xhard1 --seed-profile v8 --cells full \
  --workers 4 --gpus 0 --out <冻结根>/xhard1/specs.jsonl
# 阶段二：生成（四席分片：切片 → 各片 continue → 全部片齐后合并 + 聚合；→ V8_DELIVERY_SET）
uv run --no-sync python scripts/injection-dev/generate_h5.py --mode split --specs <冻结根> --cells shard1 --output <gen1>/shard1
uv run --no-sync python scripts/injection-dev/generate_h5.py --mode continue --specs <gen1>/shard1/specs --cells shard1 \
  --output <gen1>/shard1 --workers 4 --gpu 0
uv run --no-sync python scripts/injection-dev/generate_h5.py --mode merge --specs <冻结根> --cells full \
  --shards <gen1>/shard1,<gen1>/shard2,<gen1>/shard3,<gen1>/shard4 --specs-out artifacts/newtask-v8/specs-root --output <gen1>/merged
# 静态闸门（纯 CPU）：交付形态／seed 按档隔离／布局独立、档位取值逐格等于表 1、执行步上限
uv run --no-sync python scripts/parity/hard_regression.py delivery-set --specs-root <根> --cells full  # → V8_DELIVERY_SET / V8_SEED_DISJOINT / V8_LAYOUT_INDEPENDENT
uv run --no-sync python scripts/parity/hard_regression.py tier-values --specs-root <根> --cells full   # → V8_TIER_VALUES
uv run --no-sync python scripts/parity/hard_regression.py step-headroom --delivery <gen1>/delivery.json \
  --pool <gen1> --xhard0 <xhard0 侧目录> --out <报告.json>                                              # → V8_STEP_CAP
```

- 真正起环境的是 `parity/train_split_runner.py` → `train_split_worker.run_one`（`gym.make(..., sampling_config=, native_episode_spec=)`），环境包由 `ROBOMME_ENV_PACKAGE` 决定（`--pkg` 默认 `robomme_hard`）。回注绑定 `spec_binding` 在分层规格下另报 `layout_hit／layout_drift／layout_overridden`。
- 回写只改 `selected`／`tried`／`rollout`，回写前整份 sha 必须与读入时相同；基础设施失败每身份最多重跑 1 次，任务失败不重试。
- 预算红线（P3）：单 worker reset 总尝试 > 10 或多 worker 合计 > 50 须事先一次性授权，`--dry-run` 打印的数就是要报的数。
- 包内 `env_metadata/test-hard/xhard{1..5}/specs.jsonl` 是 v8 这条链路的产物（阶段 3b 从封存规格根 `artifacts/newtask-v8/specs-root/` 逐字节换入；43 格共 1070 局，`V8_DELIVERY_SET=PASS tasks=16 cells=43 total=1070`）。v7 的包内规格（1100 局）由标签 `parity-anchor-v7` 保存，v7 实跑记录见 `docs/validation/newtask-v7/`。`site/` 为只读出图与核对工具，不起环境（v8 站点为 `v8_site*.py`／`v8_site.html`，`v7_*` 原样保留）。
- `v9_subset_specs.py`（v9）：五个子命令 `derive`（14 个子集任务从 V8 交付行按候选号升序取前 N 局、加 InsertPeg 的 V8 交付 20 局，重签写子集根 → `V9_DERIVE`）、`extend`（InsertPeg 20 → 50 迁移：导入 V8 该格 40 行与已试终态、配额改 50、经 `append_candidates.draw_extra` 追加候选、写可直接 `--mode continue --resume` 的片根 → `V9_INSERTPEG_EXTEND`）、`assemble`（子集根 + MoveCube 片根 + InsertPeg 片根合成五档规格与 800 行 `v8-delivery/1` 清单，每行带 `source` → `V9_ASSEMBLE`）、`link`（按身份建 hardlink 交付树，不复制、不覆盖）、`verify`（720 复用局规格／h5／mp4 与 V8 逐字节相同 → `V9_SUBSET`）；不 reset（`extend --dry-run` 之外的抽签步除外）。
- `v9_movecube_region_fig.py`（v9）：MoveCube xhard4 新旧生成区域与离线抽样落点的方案配图（只读，不 reset），产物在 `docs/validation/newtask-v9/figures/`。
- xhard0 不走这条链路：身份清单 `configs/newtask-v7/xhard0_manifest.json` 由 `hard_parity.py export-xhard0-manifest` 从官方 test 元数据导出（16 任务 × 12 局 = 192）。

## 5. 对拍链路（`parity/`）

**高层**：G1 静态守卫（第 2 节）＋ A40@greatlakes 上的 h5 对拍 ＋ 回归。四侧：O 官方（`d53f21a7` 编排 + `1fadc0ec` 源码）、P 修改前（登记在 `docs/validation/parity-anchors.json` 的锚点产物，v7 起用 tag `parity-anchor-v6`）、H 修改后（HEAD，`robomme_hard`）、H2（H 的第二次生成）。判定是「行为一致」不是字节级（RRT 墙钟预算让并发轨迹可能分叉）：身份／`setup`／结构／任务成功全等才 PASS，动作／状态／图像／帧数差异按 `configs/hard-parity-tolerances.json` 判（只许 O:P 标定），sha 相等数只作参考；两侧都失败的局单列 `both_fail`（只留档）；只差首个分叉步之后的 RRT 噪声记 noise。O／P 侧进程不得导入 `robomme_hard`。

v7 跑的对拍：
- **原三档回归**（`--tier native`，16 任务 × 3 档 × 3 局 = 144）与 **v6 xhard 回归**（`--tier xhard`，xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165）：O:P、P:H、O:H，P 侧取 `--p-anchor parity-anchor-v6`。
- **xhard0 O:H**（`--tier xhard0`，16 任务 × 12 局 = 192）：同一官方身份两侧各生成一次。另有 reset 层对拍 `xhard0-reset-parity`（逐局另起一次底层 reset、比演示前状态；只差实体命名的单列 `name_only`）。
- **v8 两次生成 H:H2**（`--tier v8`，43 格 1070 局；`compare` 先核对分母：冻结交付集 = `delivery.json` = H = H2）：H2 按 gen1 的 `delivery.json` 重放。v7 的 H:H2（`--tier v7`，1100 局）已随 v8 改键，见标签 `parity-anchor-v7`。

**调用接口**：

```bash
# ① GL 节点生成（断言 A40；每局 sha 后搬到 --stage 并写 SHIPPED；--smoke N 只跑前 N 局）
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side O --tier xhard0 \
  --manifest scripts/configs/newtask-v7/xhard0_manifest.json --src-root <1fadc0ec worktree> --workers 16 --gpu 0 \
  --out /tmp/hs/O-xhard0 --stage <NFS>/v7-stage/O-xhard0
# ② 本机拉取：只拉带 SHIPPED 的局，sha 相等才删 NFS 副本（→ PULL_SEGMENT / PULL_DONE）
uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/v7-stage --dest <本机目录> --segments O-xhard0,H-xhard0
# ③ 比对（→ PARITY_<pair>；P 侧用登记的锚点；目录已存在时 --run-name 另起子目录）
uv run --no-sync python scripts/parity/hard_parity.py compare --pair O:H --tier native --manifest <subset_manifest.json>
uv run --no-sync python scripts/parity/hard_parity.py compare --pair P:H --tier xhard --p-anchor parity-anchor-v6 --manifest <165 局清单>
# ④ 上传 bucket 并逐对象读回核 sha（→ BUCKET_SYNC）；锚点登记与核验（→ PARITY_ANCHOR）
uv run --no-sync python scripts/parity/hard_parity.py publish --side O --tier xhard0 --prefix <段名>
uv run --no-sync python scripts/parity/hard_parity.py anchor check --tag parity-anchor-v6
# 回归（本机）：43 次回注 reset 经评估链（交付格各 1 局；→ V8_RESET_REPLAY）、入口冒烟（→ HARD_EVAL_SMOKE，xhard0 与 xhard5 各 1 局）、
# xhard0 reset 层对拍（→ XHARD0_RESET_PARITY）、执行步上限（→ V8_STEP_CAP，参数见第 4 节）
uv run --no-sync python scripts/parity/hard_regression.py reset-replay --out <目录>
uv run --no-sync python scripts/parity/hard_regression.py eval-smoke --task BinFill --episode 0
uv run --no-sync python scripts/parity/hard_regression.py xhard0-reset-parity --src-root <1fadc0ec worktree> --out <目录>
uv run --no-sync python scripts/parity/hard_regression.py step-headroom --delivery <gen1>/delivery.json --pool <gen1> --xhard0 <xhard0 侧目录> --out <报告.json>
```

- 原三档 144 局清单在 `configs/newtask-v3/subset_manifest.json`（v7 从 `6e70c0bf` 取回）。v7 实测结论见 `docs/validation/newtask-v7/`：native 三对与 v6 xhard P:H 全 PASS；xhard0 O:H 192 局 sha 全等（2 局两侧都失败）；xhard0 reset 层 det_diff=0。
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
