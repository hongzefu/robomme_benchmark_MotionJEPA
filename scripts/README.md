# scripts/ 说明

> V9 定稿口径（12.333 `820ca142` 换包；本文 12.338 重写，方案 `docs/plans/1002-v9-final-cleanup-plan.md`）。用户定义（2026-10-02）：**`dataset="test-hard"` 的交付集严格是 800 局 = 16 任务 × 每任务 50 局**（xhard1～xhard5 共 43 格）；官方 hard 的 xhard0 12 局保留在 test-hard 里但**不算在 800 内**；步数上限是固定常量表，不从 episode 读。官方锚点：环境源码 `RoboMME/robomme_benchmark@1fadc0ec`（`src/robomme/` 与之逐字节相同）、生成编排 `d53f21a7`（`parity/official/` 四文件逐字节 vendor）。v8 口径的本文（1262 局、43 格 1070、v7 实测长度表）见 12.337 以前的版本；V4/V5 逐环境字段表与 V6 发布说明见 [`docs/ledger/scripts-README-legacy-20260928.md`](../docs/ledger/scripts-README-legacy-20260928.md)，均不再维护。

# 第一部分　使用

## 1. 入口：`evaluation_hard.py`

`scripts/` 顶层四个入口里，`dataset_replay.py`、`evaluation.py`、`run_example.py` 与官方逐字节相同，用法见仓库根 `readme.md`。新增的只有 `evaluation_hard.py`：跑六档（xhard0～xhard5）的评估入口，**调用方式与官方 `evaluation.py` 完全一样**，只差 4 处（3 个 hunk），其余逐字相同（核查：`diff scripts/evaluation.py scripts/evaluation_hard.py`；测试 `tests/lightweight/test_v9_packaged_800.py` 钉死 `HARD_ENTRY_DIFF=PASS hunks=3`）。

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

1. **换包**。新值档的环境代码放在 `robomme_hard` 包里，与官方 `robomme` 并列、互不干扰。它的 builder 是官方 builder 的子类，用法一样（`BenchmarkEnvBuilder(env_id, dataset, action_space, max_steps)` → `get_episode_num()` → `make_env_for_episode(i)` → `env.reset()`／`env.step()`），只是多认一个数据集名 `test-hard`。
2. **换数据集**。官方 `test` 每任务 50 局（easy／medium／hard 混排）。`test-hard` 每任务 **62 局 = xhard0 12 局 + V9 交付 50 局**，16 任务共 992 局；其中 V9 交付集 **16 × 50 = 800 局**是用户定义的正式集合，xhard0 是官方 hard 原局、只作对照、不计入 800。episode 号顺序：先 xhard0 12 局（按官方原 episode 号），再按 xhard1→xhard5 排该任务交付的档、档内按候选号升序（每格局数见第 3 节局数表）。
3. **多拿一个档位**。`resolve_episode` 和官方一样返回两个值，第二个值在 `test-hard` 下就是档位名（`xhard0`～`xhard5`）。
4. **步数上限是固定常量表**。`TIER_MAX_STEPS = {xhard0: 1300, xhard1～xhard5: 1600}`，用上一步拿到的档位查表后传给 `make_env_for_episode`；不传就用构造 builder 时的 `max_steps`。这个数**不从 episode、不从规格文件读**（规格 header 只签 `exec_cap`＝1600，行里没有 `max_steps`）。xhard0 的 1300 与官方 `evaluation.py` 默认值相同；1600 是新值档的执行步上限，V9 交付集按构造不超（实测最大 1469，见第 3 节末）。

### 每一局的场景从哪里来

**xhard0** 就是官方 `test` 里 `difficulty="hard"` 的那 12 局（每任务 50 局里挑出 hard 的），seed 与原 episode 号不变，环境走官方原生 hard 分支现场抽，不读任何规格文件（`spec_binding` 里 `mode=export`）。

**xhard1～xhard5** 的场景不是评估时随机抽的，而是生成数据时就冻结好、随包发布的。五份文件 `src/robomme_hard/env_metadata/test-hard/xhard1～5/specs.jsonl`（`schema="hard-specs/4"`）每行记一局：seed、档位、以及场景里每个随机取值点当时抽到的值（放了哪些块、什么颜色、放在哪、演示序列是什么）。文件里**同时留着未入选的候选行**（五份合计 1518 行、正式局 800 行），builder 用 `hard_specs.delivered(row)`（`selected` 且 `rollout.status=="ok"`）过滤，只发正式局；每格正式局数不等于交付格表 `EXPECTED_CELLS`＝`V9_CELLS` 即报错，(任务, 档) 不在表内却有正式局也报错。V9 的 800 局里 720 局逐字节复用 V8 交付（14 任务各 50 + InsertPeg 20），80 局新生成（MoveCube xhard4 50 + InsertPeg xhard4 30）。各档布局独立抽（`layout_parent` 全空），seed 公式 `offset + env_code × 100000 + episode × 100 + attempt`，按档 offset xhard1 16e6、xhard2 18e6、…、xhard5 24e6，档与档两两不交。

构造 builder 时，它先列出本任务的 xhard0 局，再用 `load_specs_v8` 读这五份文件（整根校验：逐档封套、逐格局数等于交付格表、跨档 seed 不交），挑出本任务的正式局排在后面。`make_env_for_episode(i)` 做的事与官方相同（`gym.make` 再套 wrapper），只是在 `gym.make` 里多传两个参数：这局所属档位的取值配置（`sampling_config`），和这局冻结的场景规格（`native_episode_spec`）。环境建场景时每个随机取值点照常抽一次随机数，但真正用的值是规格里冻结的那个，所以评估时建出的场景与生成数据时是同一局；`reset()` 之后可调 `robomme_hard.env_record_wrapper.spec_binding(env)` 看核对结果，正常应零差（V9 回注闸门 `V9_RESET_REPLAY=PASS resets=43 injected_mismatch=0`）。

## 2. 相对官方的文件差异

复现：`git diff --name-status 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9 HEAD -- . ':!docs' ':!artifacts'`。

| 区域 | 相对官方 |
|---|---|
| `src/robomme/**` | 零差异（102 文件）。受 P2 保护，改动须用户逐个批准 |
| `src/robomme_hard/**` | 全部新增：16 个环境类与改过的 utils／wrapper 为复制，依赖闭包干净的官方模块为借用 shim，`hard_builder.py` 子类化官方 builder 并新增 `dataset="test-hard"`，`hard_specs.py`／`utils/episode_spec.py` 等新增。逐文件表见 [`src/robomme_hard/README.md`](../src/robomme_hard/README.md) |
| `scripts/` | 官方三入口零差异；新增 `evaluation_hard.py`、`injection-dev/`、`parity/`、`eval-official/`、`configs/` |
| `tests/` | 新增轻量测试，改 `conftest.py` |
| `pyproject.toml` | 加依赖 `pebble`；wheel 加 `src/robomme_hard`；加 pytest marker |
| `.gitignore` | 追加 `/artifacts/*` |
| `readme.md` | 「Data Generation」节仍指向已删的 `generate_dataset_newseed.py`，陈旧 |

为什么并列包：官方源码原样回退到 `1fadc0ec`，差异全部搬进 `robomme_hard`；导入它时 16 个环境 id 被 `register_env(override=True)` 接管，同进程要官方行为须另开只导入 `robomme` 的进程。

守卫（秒级、纯 CPU）：

```bash
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream   # 末行 UPSTREAM_GUARD=PASS
```

## 3. 六档配置、V9 局数与步数上限

**配置对比**（取值与 v8 相同，源 `docs/plans/1001-newtask-v8-xhard-gradient-plan.md` 第一部分表 1；代码真源为各环境的 `native_blocks` 与包内 header 的 `sampling_config`，测试侧副本 `tests/_shared/v7_tier_values.py`）。xhard0 列就是官方 hard 配置（`[a,b]` 为整数均匀区间；RouteStick、PatternLock 的 xhard1～3 也是区间）。「不交付」= 数值仍在代码里、不生成；「无」= 该任务没有这个档。V9 唯一的取值改动：MoveCube xhard4 生成区域改为圆环 r_in 0.24／r_out 0.42、base_dist [0.31, 0.80]（圆心 (−0.06, 0)），闸门 `V9_MOVECUBE_LAYOUT=PASS episodes=50 in_region=300 outside_old=300`。

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
| MoveCube | 不加档 | 官方 hard | 无 | 无 | 无 | 圆环 U（V9 区域） | 无 |
| InsertPeg | 不加档 | 官方 hard | 无 | 无 | 无 | 原 xhard 改名，数值不动 | 无 |

**V9 局数**（交付格表 `hard_specs.EXPECTED_CELLS`＝`V9_CELLS`，43 格，每任务恰 50 局；模块级断言 `sum==800`、每任务 50；源 `docs/plans/1002-newtask-v9-movecube-region-800-plan.md` 表 2）：

| 任务 | xhard0（对照，不计入 800） | xhard1 | xhard2 | xhard3 | xhard4 | xhard5 | V9 合计 | test-hard 实发 |
|---|---|---|---|---|---|---|---|---|
| PickXtimes、RouteStick、PatternLock | 12 | 17 | 17 | 16 | — | — | 各 50 | 各 62 |
| SwingXtimes、StopCube | 12 | 10 | 10 | 10 | 10 | 10 | 各 50 | 各 62 |
| VideoUnmask、ButtonUnmask | 12 | 13 | 13 | 12 | 12 | — | 各 50 | 各 62 |
| BinFill、VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、VideoRepick | 12 | 25 | 25 | — | — | — | 各 50 | 各 62 |
| MoveCube、InsertPeg | 12 | — | — | — | 50 | — | 各 50 | 各 62 |
| **合计** | 192 | 272 | 272 | 92 | 144 | 20 | **800** | **992** |

一句话：**800 = 16 任务 × 50 局**（xhard1～5）；**992 = 800 + 16 任务 × 1 档 × 12 局（xhard0）**。闸门 `V9_DELIVERY_SET=PASS tasks=16 cells=43 total=800 new=80 reused=720`、`V9_SEED_DISJOINT=PASS`、`V9_LAYOUT_INDEPENDENT=PASS`，测试 `V9_PACKAGED=PASS total=800 per_task=50 cells=43 episodes_per_task=62 total_with_xhard0=992`。

**步数上限与实测**：`TIER_MAX_STEPS`（xhard0 1300 / xhard1～xhard5 一律 1600）只约束执行段，演示段不计入；抽样时过滤执行步超过 1600 的候选（`exec_over_cap` 递补），交付集按构造不超。V9 交付实测：`V9_STEP_CAP=PASS max=1469 cap=1600 over=0 xhard0_max=1074 xhard0_cap=1300 rows=800`（`hard_regression.py step-headroom`）。逐格步数均值表不再维护，逐局长度看 V9 站点（`http://sled-vail.eecs.umich.edu:8082/`）的 oracle 总表。历史上限：v7 为 1500 / 2400 / 2900 / 3800，v6 为 1500 / 1700 / 2000 / 2600。

# 第二部分　开发者文档

## 4. V9 生成链路（`injection-dev/`）

**高层**：V9 = **720 局复用 V8 + 80 局新生成**，以 `v9_subset_specs.py` 为中心：
1. **derive**：14 个子集任务从 V8 交付行按候选号升序取前 N 局（N 按表 2 平分，每任务 50），加 InsertPeg 的 V8 交付 20 局，重签写子集根（→ `V9_DERIVE=PASS cells=42 subset=700 insertpeg=20 total=720`）。
2. **MoveCube 整任务重抽**（新区域）：`freeze_specs.py --tier xhard4 --seed-profile v8 --cells v9shard1 --candidates-per-env MoveCube=80` 冻结 80 候选，`generate_h5.py --mode split/continue` 生成，逐方式硬配额 17／17／16、同方式递补（→ `V9_MOVECUBE_WAYS=PASS ways=17/17/16`）。
3. **InsertPeg extend**：`v9_subset_specs.py extend --task InsertPeg --tier xhard4 --quota 50 --append 35` 导入 V8 该格 40 行与已试终态、配额 20→50、经 `append_candidates.draw_extra` 追加候选，写可 `--mode continue --resume` 的片根（→ `V9_INSERTPEG_EXTEND=PASS imported_ok=20 appended=35 quota=50`）。
4. **assemble**：子集根 + MoveCube 片根 + InsertPeg 片根合成五档规格与 800 行 `v8-delivery/1` 清单，每行带 `source`（→ `V9_ASSEMBLE=PASS rows=800 reused=720 new=80 cells=43`）。
5. **link**：按身份建硬链接交付树 `artifacts/newtask-v9/delivery/episodes/`，不复制、不覆盖（→ `V9_LINK=PASS rows=800 files=1600 linked=1600`）。
6. **verify**：720 复用局规格／h5／mp4 与 V8 逐字节相同（→ `V9_SUBSET=PASS reused=720 spec_equal=720 h5_equal=720 video_equal=720`）。

规格 `schema="hard-specs/4"`：每行分「签」（`task tier candidate episode seed attempt spec spec_sha256 layout_parent`，由 `identity_sha256` 覆盖，不可改）与「结果」（`selected tried initial_selected rollout`，可回写；`rollout` 带 `exec_steps`）；`delivery_sha256` 锁正式交付集合；header 另签 `exec_cap`（＝1600）与逐任务 `delivery_per_cell`。新值档不开 fail recover。真正起环境的是 `parity/train_split_runner.py` → `train_split_worker.run_one`（`gym.make(..., sampling_config=, native_episode_spec=)`），环境包由 `ROBOMME_ENV_PACKAGE` 决定（默认 `robomme_hard`）。回写只改 `selected`／`tried`／`rollout`，回写前整份 sha 必须与读入时相同；基础设施失败每身份最多重跑 1 次，任务失败不重试。预算红线（P3）：单 worker reset 总尝试 > 10 或多 worker 合计 > 50 须事先一次性授权，`--dry-run` 打印的数就是要报的数。

V9 实跑命令、席位、tmux 清单与实耗见 `docs/validation/newtask-v9/launch.md`，结论见同目录 `result.md`。包内 `env_metadata/test-hard/xhard{1..5}/specs.jsonl` 由封存规格根 `artifacts/newtask-v9/specs-root/` 逐字节换入（12.333）。

**静态闸门**（纯 CPU）：

```bash
uv run --no-sync python scripts/parity/hard_regression.py delivery-set --specs-root <根> --cells full  # → V9_DELIVERY_SET / V9_SEED_DISJOINT / V9_LAYOUT_INDEPENDENT
uv run --no-sync python scripts/parity/hard_regression.py tier-values --specs-root <根> --cells full   # → V8_TIER_VALUES（行名沿用 v8，表按 EXPECTED_CELLS）
uv run --no-sync python scripts/parity/hard_regression.py step-headroom --delivery <delivery.json> --pool <生成根> --xhard0 <xhard0 侧目录> --out <报告.json>  # → V9_STEP_CAP
uv run --no-sync python scripts/parity/hard_regression.py movecube-layout --specs-root <根>              # → V9_MOVECUBE_LAYOUT / V9_MOVECUBE_WAYS
```

**历史（V9 不调用，代码保留）**：v7 的「母布局抽签 → `derive_specs.py` 派生 → 四档同步生成」链路与 `layout-shared`／`prefix-geometry` 守卫、`layout_whitelist.json`；v8 的四席分片（`generate_h5.py --mode split/continue/merge --cells shard1～4`）与 `v8_continue_after_gen.py` 全链路续跑。xhard0 不走生成链路：身份清单 `configs/newtask-v7/xhard0_manifest.json` 由 `hard_parity.py export-xhard0-manifest` 从官方 test 元数据导出（16 任务 × 12 局 = 192）。

**站点与出图**（`injection-dev/site/`，只读、不起环境）：V9 逐局对照站由 `v8_site.py`（名字沿用、口径为 V9）起在 8082，目录 `artifacts/newtask-v9/site/`（`v8_site_catalog.py --cells v9` 生成 `catalog.json`，`v8_subgoal_lengths.py`、`v8_semantic_diff.py` 生成 `subgoals.json`、`semantic.json`，媒体映射 `media-private.json`）；复检 `v8_oracle_browser_check.py --port 8082`（→ `V8_ORACLE_BROWSER=PASS cells=59`）。`v9_movecube_region_fig.py` 出 MoveCube 区域配图到 `docs/validation/newtask-v9/figures/`。

## 5. 对拍与回归（`parity/`）

**高层**：G1 静态守卫（第 2 节）＋ A40@greatlakes 上的 h5 对拍 ＋ 本机回归。判定是「行为一致」不是字节级（RRT 墙钟预算让并发轨迹可能分叉）：身份／`setup`／结构／任务成功全等才 PASS，动作／状态／图像／帧数差异按 `configs/hard-parity-tolerances.json` 判（只许 O:P 标定）；两侧都失败的局单列 `both_fail`；只差首个分叉步之后的 RRT 噪声记 noise。O／P 侧进程不得导入 `robomme_hard`。

**V9 跑过的对拍与回归**（`docs/validation/newtask-v9/records/gates.txt`）：
- **xhard0 reset 层对拍**（`xhard0-reset-parity`，16 任务 × 1 档 × 12 局 = 192）：`XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0 name_only=12`，换包前后各一次。
- **回注 reset**（`reset-replay`，43 格各 1 局 = 43 次）：`V9_RESET_REPLAY=PASS shape=cells43 resets=43 replay=43 injected_mismatch=0 layout_drift=0 spec_bound=43`。
- **新 80 局二次生成 H:H2**（`--tier v9`）：`PARITY_H_H2=FAIL compared=80 byte_equal=72 noise=7 h2_fail=1 hard_line_5pct=HIT`——按计划不阻断交付，交用户裁决（`docs/1002-pending-decisions.md` A1）。
- 720 复用局不重新对拍：`V9_SUBSET` 已证与 V8 交付逐字节相同；V8 当时的 H:H2（1070 局）与更早的 native／xhard／xhard0 O:H 对拍见 `docs/validation/newtask-v8/`、`newtask-v7/`。

**调用接口**：

```bash
# GL 节点生成（断言 A40；每局 sha 后搬到 --stage 并写 SHIPPED）
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side H2 --tier v9 --manifest <delivery.json> --workers 4 --gpu 0 --out /tmp/hs/H2 --stage <NFS>/stage/H2
# 本机拉取（只拉带 SHIPPED 的局，sha 相等才删 NFS 副本）
uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/stage --dest <本机目录> --segments H2
# 比对（→ PARITY_H_H2；先核对分母：冻结交付集 = delivery.json = H = H2）
uv run --no-sync python scripts/parity/hard_parity.py compare --pair H:H2 --tier v9 --manifest <delivery.json>
# 本机回归（GPU）
uv run --no-sync python scripts/parity/hard_regression.py reset-replay --out <目录>                                # → V9_RESET_REPLAY
uv run --no-sync python scripts/parity/hard_regression.py xhard0-reset-parity --src-root <1fadc0ec worktree> --out <目录>  # → XHARD0_RESET_PARITY
uv run --no-sync python scripts/parity/hard_regression.py eval-smoke --task BinFill --episode 0                    # → HARD_EVAL_SMOKE
```

- `train_split_*.py` 是 S0 原始 train 基线设施；`train_split_runner.py` 同时是第 4 节的运行器，启动时核对 `configs/newtask-v3/subset_manifest.json::records_sha256`（官方 train 元数据 16 份的散列）。细表见 [`parity/README.md`](parity/README.md)。
- `eval-official/`：双模型（SimpleMemVLA、MME-VLA）评估客户端与席位脚本，V9 评估命令见 `docs/validation/v9-two-policy-gl10-20261002-01/launch.md`（`v8_manifest.py --exclude-evaluated` 生成 V9 新 80 局清单、`run_v8_gl.sh` 单席入口、`v8_report.py` 汇总）；800 局总表 SimpleMemVLA 178/800、MME-VLA 39/800。

## 6. 核查清单

```bash
ls -1 scripts/*.py                                                        # 恰好四个入口（P1）
git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py  # 录像器零 diff
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream
diff scripts/evaluation.py scripts/evaluation_hard.py                     # 恰好第 1 节的 4 处
uv run --no-sync python -m pytest tests/lightweight/test_v9_packaged_800.py -q -s   # V9_PACKAGED / V9_MAX_STEPS / HARD_ENTRY_DIFF
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
```

实跑一律先「单任务 × 单档 × 单局 × 单 worker」冒烟；超过 5 分钟进 detached tmux 并监听日志；结果写 `docs/validation/`，过程写 commit body。
