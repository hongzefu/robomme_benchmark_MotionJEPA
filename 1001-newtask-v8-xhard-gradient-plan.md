# 1001 newtask v8：xhard 梯度（SwingXtimes／StopCube 扩至 xhard1～5）与 1600 步上限的配置调整方案

> **权威性**：本文件是 v8 配置调整的方案，只规划不实施：改 `src/robomme_hard` 常量、改 `TIER_MAX_STEPS`、删 V6、正式抽签与生成，每一步单独获批。
>
> **分支**：v8 的现行分支为 `newtaskRelease-taskV8`，基于旧分支 `newtaskRelease-v6` 的 `f406abe5`（12.281）仅新增，旧分支名称与提交指针均保留。旧 `newtaskRelease-v6` 自旧 `newtaskRelease-v5` 的 `49ba3eb8`（12.279）分出；`49ba3eb8` 已包含 V8 计划，不能称作纯 v7 交付态。历史用户原话与当时理解保留在第二部分 §2.8；本次只对齐分支名称与当前说明，V8 仍只规划不实施。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`。
>
> **代码锚点**：v7 交付规格 `src/robomme_hard/env_metadata/test-hard/xhard{1..4}/specs.jsonl`（四份 header 的 `sampling_config_sha256` 都是 `4a308ee7…`，`seed_rule.offset=14000000`）。官方环境源码 `1fadc0ec`、官方生成编排 `d53f21a7`（vendor 在 `scripts/parity/official/`）都不改。
>
> **commit 编号**：12.277 首版；12.278、12.279 修订局数口径；12.280 重写第一部分（表格 + 改动清单 + 验收；删 V6 对拍；建分支 v6）；12.281 修订（PickXtimes 去掉 9、10 次；抽样过滤执行步 > 1600；VideoUnmask／ButtonUnmask xhard1 改 2／4／2；RouteStick／PatternLock 改区间；非梯度参数一律不改）。12.282 为分支对齐文档。12.283 修订（四项拍板：各档布局独立抽、PickXtimes 50 局分 17／17／16、派生工具链保留不调用、只抽交付格、V6 留档保留）。12.284 本次修订（v8 站点与 v7 布局完全一致、评估板块置空不删；v8 不做两策略评估；`v6_site.py` 服务端改名保留）。真正的 V8 实施从 12.285 接续，仍须另行获批。
>
> **术语**：执行步 = h5 的 `timestep_*` 个数减去 `info/is_video_demo` 为真的帧数（口径同 `hard_regression.py::cmd_step_headroom`）；`TIER_MAX_STEPS` 只约束执行段；d = 放置圆盘中心到机械臂底座 (−0.615, 0) 的水平距离，单位米。
>
> **已定**（用户原话逐字见第二部分 §2.8）：非梯度参数一律不改（PickXtimes 圆盘区域不动）；PickXtimes 去掉 9、10 次，交付 xhard1～3 = 6／7／8；SwingXtimes、StopCube 扩为 xhard1～5 每档一个定值；三任务每档 10 局；VideoUnmask／ButtonUnmask xhard1 改 2／4／2；RouteStick、PatternLock xhard1～3 改区间；抽样时全部任务过滤执行步超过 1600 的候选并递补，上限定死 1600；其余任务局数沿用 v7 总数、缺档平分；xhard0 保留，xhard0 对拍保留；V6 对拍不再跑，V6 设施删除；V7 对拍设施保留改名 V8；实施分支按本轮分支对齐改为 `newtaskRelease-taskV8`。**2026-10-01 四项拍板（原话见 §2.8 第 13～16 条）**：①各档布局各自独立抽初始化位置，不再从母布局派生、不要求前缀重叠；②PickXtimes 仍按 50 局分到三档，17／17／16；③派生工具链（`derive_specs.py`、`layout_whitelist.json`、`layout-shared`／`prefix-geometry` 守卫）保留，v8 不调用；④只抽交付的 43 格，不交付的档不抽、不生成；⑤`docs/validation/newtask-v6/` 与 `docs/plans/0925-newtask-release-v6-plan.md` 留档保留。**⑥站点与评估（原话见 §2.8 第 16 条）**：v8 交付一个与 v7 站点（`site/v7_site.html`）布局完全一致的逐局站点；v8 不做 SimpleMemVLA／MME-VLA 两策略评估，站点里所有评估板块（策略成功率列、成败筛选、每局的两段策略视频、旧入口对照、翻转标记）原位保留、内容置空，不删除；阶段 4 的「评估侧核对」取消，xhard0 评估对拍沿用 v7 结果不重跑。
>
> **待拍板**：无。原①（布局共用前缀还是独立）与 PickXtimes 局数已于 2026-10-01 拍板，见上「已定」。

# 第一部分（给人看）

## 1. 难度梯度

表 1 是 v8 全部难度表述。xhard0 即官方 hard，不动。「不交付」= 数值仍在代码里、v8 不生成；「无」= 该任务没有这个档的配置。

| 任务 | 维度 | xhard0 | xhard1 | xhard2 | xhard3 | xhard4 | xhard5 | 改动 |
|---|---|---|---|---|---|---|---|---|
| PickXtimes | 抓放次数 | 4～5 | 6 | 7 | 8 | 9，不交付 | 无 | 改，原 7／10／12／15；9、10 次去掉，xhard4 留 9 只为保住四键结构、不交付 |
| PickXtimes | 干扰块 | 0 | 1 | 2 | 3 | 4，不交付 | 无 | 不动 |
| PickXtimes | 圆盘区域 | 原区域 | 原区域 | 原区域 | 原区域 | 原区域 | 无 | 不动：非梯度参数，用户定不改 |
| SwingXtimes | 摆动轮数 | 3 | 4 | 5 | 6 | 7 | 8 | 改，原 5／7／9／11；xhard5 新增 |
| SwingXtimes | 干扰块 | 0 | 1 | 2 | 3 | 4 | 4 | xhard5 取 4：`BLOCK_DISTRACTOR_COLORS` 只有黄／青／品红／橙 4 色 |
| StopCube | 停止序号 `stop_time` | 2～5 | 6 | 7 | 8 | 9 | 10 | 改，原仅 xhard4、6～15 随机；xhard1～3、5 新增 |
| StopCube | 方块速度 `move_interval` | 60／80／120 随机 | 60 | 60 | 60 | 60 | 60 | xhard1～3、5 新增，同 xhard4 最快档 |
| BinFill | 投入块数 | 3～5 | 6 | 7 | 8，不交付 | 9，不交付 | 无 | 不动 |
| VideoUnmask | 抓取数／干扰容器／干扰方块 | 2／0／0 | 2／4／2 | 3／4／2 | 3／8／4 | 3／12／6 | 无 | xhard1 改，原 2／0／0 |
| ButtonUnmask | 抓取数／干扰容器／干扰方块 | 2／0／0 | 2／4／2 | 3／4／2 | 3／8／4 | 3／12／6 | 无 | xhard1 改，原 2／0／0 |
| VideoUnmaskSwap | 换位次数／抓取数／外圈干扰 | 2～3／2／0 | 5／2／2 | 7／3／4 | 9／3／6，不交付 | 11／3／8，不交付 | 无 | 不动 |
| ButtonUnmaskSwap | 换位次数／抓取数／外圈干扰 | 2～3／2／0 | 3／2／2 | 5／3／4 | 7／3／6，不交付 | 9／3／8，不交付 | 无 | 不动 |
| VideoPlaceButton | 放置次数 | 2 | 3 | 4 | 5，不交付 | 6，不交付 | 无 | 不动 |
| VideoPlaceOrder | 访问总次数 | 3 | 5 | 6 | 7，不交付 | 8，不交付 | 无 | 不动 |
| PickHighlight | 抓取数／总方块数 | 3／6 | 4／7 | 5／8 | 6／9，不交付 | 7／10，不交付 | 无 | 不动 |
| VideoRepick | 方块数／换位／重抓 | 原布局／0／1～3 | 4／4／2 | 5／6／3 | 6／8／4，不交付 | 7／10／5，不交付 | 无 | 不动 |
| RouteStick | 路线段数 | 4～7 | 8～10 | 11～13 | 14～16 | 19，不交付 | 无 | 改，原定值 10／13／16；区间内均匀抽 |
| PatternLock | 图案节点数 | 4～8 | 9～12 | 13～15 | 16～18 | 21，不交付 | 无 | 改，原定值 12／15／18；区间内均匀抽 |
| MoveCube | 官方 xhard4 配置，三种运动方式分层 | 官方 hard | 无 | 无 | 无 | 不动 | 无 | 不动 |
| InsertPeg | 官方 xhard4 配置 | 官方 hard | 无 | 无 | 无 | 不动 | 无 | 不动 |
| 全部任务 | 步数上限 `TIER_MAX_STEPS` | 1300 | 1600 | 1600 | 1600 | 1600 | 1600 | 改，原 1500／2400／2900／3800；定死 1600。抽样时全部任务过滤执行步超过 1600 的候选并递补，交付集按构造不超 |

**表 2 局数**。PickXtimes 50 局分三档 17／17／16；SwingXtimes 与 StopCube 五档各 10；其余每任务总数等于 v7，缺档平分（两档各 40，三档 27／27／26）；xhard0 每任务 12。每格布局各自独立抽，档与档之间不共用。

| 任务 | xhard0 | xhard1 | xhard2 | xhard3 | xhard4 | xhard5 | v8 合计 | v7 合计 |
|---|---|---|---|---|---|---|---|---|
| PickXtimes | 12 | 17 | 17 | 16 | — | — | 62 | 92 |
| SwingXtimes | 12 | 10 | 10 | 10 | 10 | 10 | 62 | 92 |
| StopCube | 12 | 10 | 10 | 10 | 10 | 10 | 62 | 32 |
| VideoUnmask | 12 | 20 | 20 | 20 | 20 | — | 92 | 92 |
| ButtonUnmask | 12 | 20 | 20 | 20 | 20 | — | 92 | 92 |
| BinFill | 12 | 40 | 40 | — | — | — | 92 | 92 |
| VideoUnmaskSwap | 12 | 40 | 40 | — | — | — | 92 | 92 |
| ButtonUnmaskSwap | 12 | 40 | 40 | — | — | — | 92 | 92 |
| VideoPlaceButton | 12 | 40 | 40 | — | — | — | 92 | 92 |
| VideoPlaceOrder | 12 | 40 | 40 | — | — | — | 92 | 92 |
| PickHighlight | 12 | 40 | 40 | — | — | — | 92 | 92 |
| VideoRepick | 12 | 40 | 40 | — | — | — | 92 | 92 |
| RouteStick | 12 | 27 | 27 | 26 | — | — | 92 | 92 |
| PatternLock | 12 | 27 | 27 | 26 | — | — | 92 | 92 |
| MoveCube | 12 | — | — | — | 20 | — | 32 | 32 |
| InsertPeg | 12 | — | — | — | 20 | — | 32 | 32 |
| **合计** | 192 | 411 | 411 | 128 | 100 | 20 | **1262** | **1292** |

乘式：新值局 1 × (17 + 17 + 16) + 2 × 5 × 10 + 4 × 4 × 20 + 7 × 2 × 40 + 2 × (27 + 27 + 26) + 2 × 1 × 20 = 1070；xhard0 16 × 12 = 192；共 1262。新值格 43，xhard0 格 16。

## 2. 要改哪些文件

### 2.1 数值与档位（`src/robomme_hard/`）

| 文件 | 改什么 |
|---|---|
| `robomme_env/PickXtimes.py` | `config_xhard1..3` 改 6／7／8，`config_xhard4` 改 9（不交付）；不加 xhard5；`XHARD_DECISION`（含圆盘区域）不动；注释改 v8 口径 |
| `robomme_env/SwingXtimes.py` | `config_xhard1..4` 改 4／5／6／7，新增 `config_xhard5` = 8；`NEWVALUE_DECISION` 加 xhard5（干扰 4） |
| `robomme_env/StopCube.py` | `configs` 加 `xhard1`～`xhard5` 五份，`stop_time_range` 各 `{low: k, high_exclusive: k+1}`，k = 6／7／8／9／10，`move_interval_choices` 仍 `[60]`；`_native_decision` 暴露五个子键；`__init__` 去掉 `require_xhard4_only` |
| `robomme_env/VideoUnmask.py`、`ButtonUnmask.py` | xhard1 的 decision `distractor.count` 0 → 4、`distractor.cube_count_range` [0, 0] → [2, 2]，`pick_count` 仍 2；xhard2～4 不动 |
| `robomme_env/RouteStick.py`、`PatternLock.py` | xhard1～3 的 `segment_count_range`／`path_length_range` 由定值改区间：RouteStick [8, 10]／[11, 13]／[14, 16]，PatternLock [9, 12]／[13, 15]／[16, 18]；xhard4 不动 |
| `robomme_env/utils/difficulty.py` | `NEWVALUE_DIFFICULTIES` 加 `xhard5`，`newvalue_tier` 到 5；`require_xhard4_only` 只剩 InsertPeg、MoveCube 调用；没有 xhard5 配置的任务收到 `xhard5` 时明确报错 |
| `robomme_env/utils/vqa_options.py` | `_options_stopcube` 按五档各自的 `stop_time` 定值核对 |
| `env_record_wrapper/hard_specs.py` | `TIERS` 加 `xhard5`，`BUILDER_TIERS` 为 xhard0～5；`XHARD4_ONLY = ("InsertPeg", "MoveCube")`；`EXPECTED_CELLS` 换成表 2 的逐格局数表；`TIER_MAX_STEPS` 改 `{xhard0: 1300, xhard1..5: 1600}`；header 记 `exec_cap: 1600`（进 identity）；`layout_rule` 新增 `mode: independent`（行 `layout_parent` 一律 null），`validate_specs` 对该模式不查母档；`shared` 分支代码保留；`identity_sha256` 覆盖范围变了，`schema` 升 `hard-specs/4`；删 `V6_SEED_OFFSETS` 与 v6 seed profile |
| `env_record_wrapper/hard_builder.py` | `_test_hard_entries` 去掉写死的 `!= 20`，按表 2 查表；按 `TIERS` 依次读 xhard1～5 目录，xhard5 里没有的任务跳过 |
| `env_metadata/test-hard/xhard5/specs.jsonl` | 新增，只含 SwingXtimes、StopCube 各 10 局 |
| `env_metadata/test-hard/layout_whitelist.json` | 不动：v8 各档独立抽布局，白名单只服务 v7 派生链路（保留不调用） |
| `README.md` | ①～④ 节同步五档、局数、上限 |

每档定值只改常量，不改抽样代码：`PickXtimes`／`SwingXtimes` 用 `torch.randint(number_range[0], number_range[1]+1)`，`StopCube` 用 `torch.randint(low, high_exclusive)`，区间两端相等即定值。工具链「每档一个定数」的假设（`tests/_shared/v7_tier_values.py::_point`）对定值任务继续成立；RouteStick、PatternLock 改区间后，`_point` 对这两个任务放行 [lo, hi]，环境代码本来就是 `randint(lo, hi)`，同样只改常量。

### 2.2 抽签、派生、生成（`scripts/injection-dev/`）

| 文件 | 改什么 |
|---|---|
| `freeze_specs.py`、`_freeze.py` | 去掉「v7 只在 xhard4 抽母布局」的限制，新增 seed profile `v8`：每个交付格各自独立抽签（任务 × 档各跑一次），逐格配额按表 2，header `layout_rule.mode = independent`、行 `layout_parent = null`；不交付的档不抽；不再按值分层 |
| `derive_specs.py` | **保留不调用**（用户拍板③）：v8 不派生，各档布局互相独立；文件、`_check_layout_parent` 与白名单机制原样保留供 v7 规格继续通过 |
| `_rollout.py` | **新增丢弃原因 `exec_over_cap`：候选的专家执行步 > 1600 即丢弃并递补，全部任务都过**；`_task_tiers`、`initial_pool`、`sync_drop_and_backfill`、`delivery_rows` 改逐格，递补按格独立（某格某候选失败只退该格，不再「一个候选全档退选」）；`V7_BACKFILL_CAP` 按任务（InsertPeg 按 v7 实际消耗留、BinFill 每档约 8～10）；判定行 `V7_DELIVERY_SET` 改 `V8_DELIVERY_SET` |
| `export_eval_identities.py` | 1292／646 改按 1262 与逐任务数（62／62／92／32）重算；`V6_SECONDS` 改名 `TASK_SECONDS` |
| `site/v8_site.py`、`v8_site.html`、`v8_site_catalog.py` | 由 v7 三件复制而来：`v8_site.html` 与 `v7_site.html` 的 DOM 结构、样式、侧栏、矩阵、档位页签、筛选、图例、局号条、单局区、注释区逐一保持一致，只加 xhard5 列与改标题；`v8_site_catalog.py` 把评估来源（`records_*`、`official_*`、`eval_videos*`、`tables`、`rerun11`）全部改为可缺省：缺省时每局 `eval.new`／`eval.old` 为空字典、`flip` 为空、矩阵成功率列显示「—」、成败筛选保留但无命中、单局区的两个策略视频位保留并显示「未评估」；1292 改 1262，加 xhard5。`v7_*` 三件原样保留 |
| `site/v6_site.py` | **改名 `site_server.py` 保留**（§2.5 原列为删，纠正）：它是 v7／v8 站点的服务端（`create_server`、媒体白名单、Range、`/api/subgoals`），`v7_site.py`、`v7_subgoal_lengths.py` 都依赖它；`v6_site.html` 与 v6 目录脚本照删 |
| 抽签规模 | 每格候选数 = 该格局数 × 1.3 再加抽签拒绝率；43 格各自独立，不存在「为不交付档抽母布局」 |

### 2.3 对拍与守卫（`scripts/parity/`）

| 文件 | 改什么 |
|---|---|
| `hard_regression.py` | `step-headroom` 判据由「90% + ×1.25 提议」改为「全集最大执行步 ≤ 1600」并报全局最大值与抽样阶段被过滤的候选数；`reset-replay` 的 `V7_*` 判定行改 `V8_*`，92／32 改按任务查表（62／62／92／32）；`eval-smoke` 与 `xhard0-eval-parity` 保留不改、v8 不跑（无两策略评估）；`layout-shared`／`prefix-geometry` 保留不动、v8 不跑（独立布局下无母档可比）；新增 `tier-values` 子命令（自 `site/v6_tier_monotone.py --fixed` 迁入：定值任务逐档相等，RouteStick／PatternLock 落在区间内）；`xhard0-reset-parity`、`xhard0-eval-parity` **不动** |
| `hard_parity.py` | `SHAPES`（`13x3x20+16x1x20`）改逐格表（按档 411／411／128／100／20） |
| `train_split_config.py` | 删 `newtask-v6` release 条目 |
| `scripts/README.md` | 同步 |

### 2.4 测试（`tests/`）

| 文件 | 改什么 |
|---|---|
| `_shared/v7_tier_values.py` | `TIERS` 五档；`V7_TIER_VALUES` 三任务改档、StopCube 入表、RouteStick／PatternLock 改区间；`_point` 对这两个任务放行区间，其余严格单值 |
| `lightweight/test_v4_xhard_pickxtimes.py`、`test_v4_xhard_swingxtimes.py`、`test_v5_xhard_pickswing.py` | 钉的次数与档数同步；圆盘区域断言不动 |
| `lightweight/test_v4_xhard_videounmask_buttonunmask.py`、`test_v5_xhard_videounmask_buttonunmask.py` | xhard1 干扰 0 → 4、干扰方块 0 → 2 |
| `lightweight/test_v5_xhard_patternlock_routestick.py` | xhard1～3 改区间 |
| `lightweight/test_v4_xhard_stopcube.py` | 五档定值；原「拒绝 xhard1～3」断言反转为「五档都接受、值正确」 |
| `lightweight/test_xhard0_native.py` | `TIER_MAX_STEPS` 六档字典 |
| `lightweight/test_sampling_config_split.py`、`test_v7_freeze_schema.py` | v8 快照、schema/4 |
| `lightweight/test_v6_difficulty_tiers.py` | 改名 `test_v8_difficulty_tiers.py`，五档断言，删 v6 seed 两个测试 |

### 2.5 删 V6

| 处置 | 内容 |
|---|---|
| 删 | `scripts/configs/newtask-v6/`；`scripts/injection-dev/site/v6_*` 中 7 个文件（候选值、长度表、`v6_site.html`、目录、检查器；**`v6_site.py` 不删，改名 `site_server.py`**，见 §2.2）；`site_io.py` 与 `train_split_config.py` 读 V6 快照的分支；`hard_specs.py` 的 v6 seed 偏移；`tests/lightweight/test_v6_candidate_values.py`、`test_v6_site_labels.py`、`test_v6_site_v11.py`、`test_v6_tier_monotone.py` |
| 改名保留 | `test_v6_swap_uniform.py`、`test_v6_xhard_movecube_region.py`、`test_v6_audit_fix.py`、`test_v6_audit_fix_scripts.py`（测的是现行环境行为，不是 V6 对拍）；`V6_SECONDS` → `TASK_SECONDS` |
| 留（只读） | `docs/validation/newtask-v6/`、`docs/plans/0925-newtask-release-v6-plan.md` 留档；是否删由用户另说 |
| 不动 | `scripts/configs/newtask-v3/`、`newtask-v7/xhard0_manifest.json`、`hard-parity-tolerances.json`：xhard0 对拍与 V8 对拍仍用 |

逐文件清单与理由见第二部分 §2.1b。另：`AGENTS.md` 第 0 条判据表的当前分支名在本轮分支对齐中改为 `newtaskRelease-taskV8`。

## 3. 验收

| 查什么 | 怎么查 | 判定行 |
|---|---|---|
| 官方源码不变 | `uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | `UPSTREAM_GUARD=PASS` |
| 录像器冻结 | `git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` | 退出码 0 |
| 四入口 | `ls -1 scripts/*.py` | 恰好四个 |
| xhard0 与原三档 decision 不变 | `test_decision_visible_part_unchanged`（Pick／Swing／InsertPeg 同名测试）；`assert_native_decision` 剥掉 xhard1～5 子键后逐键相同 | 核心短测无 failed |
| **xhard0 reset 对拍（保留）** | `hard_regression.py xhard0-reset-parity --src-root <官方 1fadc0ec worktree>` | `XHARD0_RESET_PARITY=PASS det_diff=0` |
| xhard0 评估对拍 | **v8 不重跑**：xhard0 规格不变，沿用 v7 留档 `docs/validation/newtask-v7/README.md` 的 `XHARD0_EVAL_PARITY=PASS`；v8 不做两策略评估 | 引用 v7 判定行 |
| 站点与 v7 布局一致 | `v8_site_browser_check.py`（Playwright，同 v7 检查器）：逐一核对侧栏、矩阵、档位页签、筛选、图例、局号条、单局区、注释区都在；评估位显示「—」／「未评估」且不缺元素；`--shots` 截图目视复核 | `V8_SITE=PASS sections=9 eval_placeholders=<n> missing=0` |
| 交付形态 | `validate_specs` 按表 2 核对每格选中数 | `V8_DELIVERY_SET=PASS tasks=16 cells=43 total=1070` |
| 档位取值 | `hard_regression.py tier-values` 读 spec：定值任务逐档相等，RouteStick／PatternLock 落在区间内 | `V8_TIER_VALUES=PASS tasks=16 mismatches=0` |
| 布局独立 | `validate_specs`：五份 header `layout_rule.mode == independent`，所有行 `layout_parent` 为 null；跨档同任务的位置类注入值不要求相同 | `V8_LAYOUT_INDEPENDENT=PASS files=5 rows=1070` |
| 回注回放 | `hard_regression.py reset-replay` | `V8_RESET_REPLAY=PASS` |
| 步数上限 | 改写后的 `step-headroom` 逐局读交付 h5；抽样阶段已按真实 h5 过滤 > 1600 | `V8_STEP_CAP=PASS max=<实测> cap=1600 over=0 filtered=<n>` |
| 同规格两次生成对拍（V7 设施，A40） | `hard_parity.py`（R7：只在 A40@greatlakes 生成） | `PARITY_*=PASS` |
| 核心短测 | `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q` | 末行 `passed` 且无 failed |
| V6 对拍 | **不跑**；V6 判定行、配置、站点随 §2.5 删除 | — |

过滤在抽样阶段按每个候选生成出来的真实 h5 判，交付集按构造 over=0。A40 第二次生成若因 RRT 噪声让个别局冒过 1600（v7 H:H2 的 1100 局里 13 局帧数最多差 116），按 `PARITY_*` 的噪声口径记录，不改交付。

**实施步骤**（每步单独获批）

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 拍板（已完成 2026-10-01：布局独立、PickXtimes 17／17／16、派生链保留不调用、只抽交付格、V6 留档保留） | 已答复 |
| 1 | 档位结构 + 常量 + 测试同步 + 删 V6（§2.1、§2.3、§2.4、§2.5） | 核心短测通过；`UPSTREAM_GUARD=PASS`；`XHARD0_RESET_PARITY=PASS` |
| 2 | 交付形态：逐格局数表、`v8` seed profile 与 `independent` 模式、builder 查表、逐格递补（§2.2） | 纯 CPU 夹具测试通过，覆盖「写 JSON → 读 JSON」之后的形态 |
| 3 | 43 格各自独立抽签 → 生成（无派生步）；先按 P3／P5 一次性报预算（第二部分 §2.4） | `V8_DELIVERY_SET`、`V8_TIER_VALUES`、`V8_STEP_CAP`（over=0）、`V8_LAYOUT_INDEPENDENT`、`V8_RESET_REPLAY` |
| 4 | A40 两次生成对拍；生成 v8 站点（评估板块置空） | `PARITY_*=PASS`；`V8_SITE=PASS` |

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

- **R1**：`src/robomme/**` 是官方 `1fadc0ec` 原样，不改（P2）。本方案的改动全部在 `src/robomme_hard/` 与 `scripts/`、`tests/`。
- **R2**：xhard0 与原三档的 decision 不变；以 `assert_native_decision` 和 `UPSTREAM_GUARD=PASS` 为准。
- **R3**：录像器 `RecordWrapper.py` 冻结，零 diff（`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`）。
- **R4**：正式抽签和生成属于大规模 reset／rollout，开跑前必须按 P3 一次性报完整预算，计数按 P5 写乘式。本轮「本机随便跑」的授权**只覆盖探针**，不延伸到正式生成。
- **R5**：`scripts/` 顶层仍然恰好四个入口（P1）。新脚本放进 `scripts/injection-dev/`。
- **R6**：`identity_sha256`／`delivery_sha256` 的覆盖范围一旦改变（逐格局数、值配额进 header），要升 `schema`（例如 `hard-specs/4`），并重跑身份类闸门（`src/robomme_hard/README.md` ⑥ R3）。
- **R7**：对拍只在 A40@greatlakes 上生成（R11）。本轮 Ada 上的探针数字只用于定配置，不进 `PARITY_*`。
- **R8**：新增 xhard5 只落在 `src/robomme_hard/` 新值子树与 `scripts/`、`tests/`；官方 `src/robomme`、xhard0 与原三档不感知该档（`assert_native_decision` 剥掉 `xhard5` 子键后仍逐键相同）。

## 2.1 逐文件改动清单（配置值）

| 文件 | 锚点 | 现值 | 新值 | 方案 |
|---|---|---|---|---|
| `src/robomme_hard/robomme_env/PickXtimes.py` | `PickXtimes.config_xhard1..4` 的 `number_min`／`number_max` | 7／10／12／15 | 6／7／8／9（xhard4 不交付）；不加 xhard5；`XHARD_DECISION` 不动 | 都改 |
| 同上 | 注释「V7 定值（0928 方案 §3.2.2）」 | — | 改写为 v8 口径 | 都改 |
| `src/robomme_hard/robomme_env/SwingXtimes.py` | `SwingXtimes.config_xhard1..4`，新增 `config_xhard5`；`NEWVALUE_DECISION` 加 `xhard5`（干扰 4） | 5／7／9／11 | 4／5／6／7／8 | 都改 |
| `src/robomme_hard/robomme_env/StopCube.py` | `_CONFIG_XHARD` 拆为五份（`configs["xhard1".."xhard5"]`）；`_native_decision` 暴露五个子键；`__init__` 去掉 `require_xhard4_only` | 仅 xhard4，`stop_time_range` `{low:6, high_exclusive:16}` | xhard1～5 各 `{low:k, high_exclusive:k+1}`，k = 6／7／8／9／10；`move_interval_choices` 仍 `[60]` | 都改 |
| `src/robomme_hard/robomme_env/utils/vqa_options.py` | `_options_stopcube` | 复刻 StopCube 公式 | 公式不变，但要按五档各自的 `stop_time` 定值核对；须跑 `test_vqa_checkpoints_match_env` 确认 | 都改 |
| `src/robomme_hard/robomme_env/VideoUnmask.py`、`ButtonUnmask.py` | xhard1 decision 的 `distractor.count`、`distractor.cube_count_range` | 0、[0, 0] | 4、[2, 2]（`pick_count` 仍 2） | 都改 |
| `src/robomme_hard/robomme_env/RouteStick.py`、`PatternLock.py` | xhard1～3 的 `segment_count_range`／`path_length_range` | 定值 10／13／16、12／15／18 | 区间 [8,10]／[11,13]／[14,16]、[9,12]／[13,15]／[16,18] | 都改 |
| `src/robomme_hard/robomme_env/utils/difficulty.py` | `NEWVALUE_DIFFICULTIES`、`newvalue_tier`、`require_xhard4_only` 的文案 | xhard1～4 | 加 `xhard5`；闸门只剩 InsertPeg、MoveCube 调用 | 都改 |
| `src/robomme_hard/env_record_wrapper/hard_specs.py` | `TIERS`、`BUILDER_TIERS`、`XHARD4_ONLY`、`EXPECTED_CELLS`、`validate_specs` 里的 `parent_tier == "xhard4"` | 四档；`XHARD4_ONLY` 含 StopCube | 五档；`XHARD4_ONLY = ("InsertPeg", "MoveCube")`；逐格表（第一部分表 2）；`layout_rule.mode` 新增 `independent`，`validate_specs` 该模式不查 `parent_tier` | 都改 |
| 同上 | `TIER_MAX_STEPS`；header 新增 `exec_cap` | 1300／1500／2400／2900／3800；无 | 1300／1600 × 5（加 xhard5）；`exec_cap: 1600` | 都改 |
| `src/robomme_hard/env_metadata/test-hard/layout_whitelist.json` | 整个文件 | v7 派生白名单 | 不动（派生链保留不调用） | — |
| `src/robomme_hard/env_metadata/test-hard/xhard5/` | 新目录 `specs.jsonl` | 无 | 只含 SwingXtimes、StopCube 各 10 局，独立抽 | 都改 |
| `scripts/injection-dev/freeze_specs.py`、`_freeze.py`、`_rollout.py` | `freeze_specs.py` 的「v7 只在 xhard4 抽」拦截、`layout_rule` 组装；`_rollout.py` 的 `_task_tiers`、`initial_pool`（读 xhard4 初选）、`sync_drop_and_backfill`（全档退选）、`delivery_per_cell` | 母布局固定 xhard4、四档共用候选 | 新增 profile `v8`：每格独立抽、`mode: independent`；候选池与递补逐格独立；`derive_specs.py` 不改、不调用 | 都改 |
| `scripts/evaluation_hard.py` | `TIER_MAX_STEPS[tier]` | 读包内常量 | 不改（P1「只差 4 处」照旧） | — |
| `tests/_shared/v7_tier_values.py` | `V7_TIER_VALUES`、`TIERS`、`_point`（遇区间抛 `NotFixedValue`） | v7 定值、四档 | 同步新值：三任务改档、StopCube 入表、RouteStick／PatternLock 改区间；`_point` 对这两个任务放行区间，其余严格单值 | 都改 |
| `scripts/injection-dev/site/v6_tier_monotone.py` | 整个文件 | V6 检查器 + V7 定值检查 `--fixed` | 删除；`--fixed`（`_V7_NEW`、`check_fixed`、`V7_VISUAL_COUNT`）迁入 `hard_regression.py tier-values`，改五档、StopCube 入表、RouteStick／PatternLock 区间 | 都改 |
| `tests/lightweight/test_v4_xhard_pickxtimes.py` | `V6_NUMBER_RANGE`、`test_v6_newvalue_config_values`、`test_xhard_config_values`、`test_decision_xhard_entries` | 钉 7／10／12／15、四档 | 同步新次数，加 xhard5 | 都改 |
| `tests/lightweight/test_v4_xhard_videounmask_buttonunmask.py`、`test_v5_xhard_videounmask_buttonunmask.py`、`test_v5_xhard_patternlock_routestick.py` | 钉 xhard1 干扰 0／[0,0]；三档定值 | 旧值 | 4／[2,2]；区间 | 都改 |
| `tests/lightweight/test_v4_xhard_swingxtimes.py` | `V6_NUMBER_RANGE`、`test_v6_newvalue_config_values` | 钉 5／7／9／11、四档 | 4／5／6／7／8，加 xhard5 | 都改 |
| `tests/lightweight/test_v4_xhard_stopcube.py` | `XHARD`、`test_xhard_segments_cover_stop_pass`（`range(6,16)`）、「xhard1～3 必报错」类断言 | 仅 xhard4，[6,15] | 五档各一个定值；原「拒绝 xhard1～3」的断言反转为「五档都接受、值正确」 | 都改 |
| `tests/lightweight/test_xhard0_native.py` | `test_TIER_MAX_STEPS五档且xhard0为1300` | 精确字典（五档） | 新字典六档（仍非递减），测试名同步 | 都改 |
| `tests/lightweight/test_sampling_config_split.py` | `test_v7_snapshot_matches_source` | v7 快照 | 换成 v8 快照或改名 | 都改 |
| `scripts/parity/hard_regression.py` | `cmd_step_headroom` | 90% + B4 ×1.25 | 「全集最大 ≤ 1600」，报全局最大值与过滤数 | 都改 |
| `scripts/injection-dev/site/v8_site.py`、`v8_site.html`、`v8_site_catalog.py`、`v8_site_browser_check.py` | 自 v7 四件复制 | 无 | 布局与 v7 逐一一致；目录脚本评估来源可缺省、置空渲染；浏览器检查器加「评估占位存在且不缺元素」断言，判定行 `V8_SITE` | 新增 |
| `scripts/injection-dev/site/v6_site.py` | 整个文件 | v6／v7 站点共用服务端 | 改名 `site_server.py`，内容不改；`v7_site.py`、`v7_subgoal_lengths.py` 的引用同步 | 改名 |
| `scripts/injection-dev/_rollout.py` | `sync_drop_and_backfill` | 只按生成失败递补 | 新增丢弃原因 `exec_over_cap`（候选专家执行步 > 1600），全部任务；递补计入预算 | 都改 |
| `scripts/README.md`、`src/robomme_hard/README.md` | 第 1、3、4 节；② | v7 定值与上限 | 同步 | 都改 |

## 2.1b V6 删除清单（用户：「V6 的可以全部删除」）

| 处置 | 文件 | 说明 |
|---|---|---|
| 删 | `scripts/configs/newtask-v6/v6-sampling-frozen.json` | V6 定值快照，只被 v6 检查器与站点读 |
| 删 | `scripts/injection-dev/site/v6_candidate_values.py`、`v6_gt_lengths.py`、`v6_gt_lengths.json`、`v6_site.html`、`v6_site_catalog.py`、`v6_v0_native_definitions.py`、`v6_tier_monotone.py` | V6 站点页面、V6 长度表、V6 候选值与单调性检查器；`v6_tier_monotone.py --fixed` 的 V7 定值检查先迁入 `hard_regression.py tier-values` 再删。`git grep` 核实：这 7 个文件只被 v6 测试与彼此引用 |
| 改名保留 | `scripts/injection-dev/site/v6_site.py` → `site_server.py` | 2026-10-01 复核纠正：`v7_site.py` 用 `importlib` 加载它的 `create_server`，`v7_subgoal_lengths.py` 依赖它的 `/api/subgoals` 路由；删掉 v7／v8 站点就起不来。改名后 `v7_site.py`、`v8_site.py` 的加载路径同步 |
| 删 | `scripts/injection-dev/site/site_io.py::V6_FROZEN`／`frozen_v6_sampling_document`；`scripts/parity/train_split_config.py` 的 `newtask-v6` release 条目 | 读 V6 快照的分支 |
| 删 | `hard_specs.py::V6_SEED_OFFSETS`、`SEED_PROFILES` 的 `"v6"`、`seed_rule_for` 的 v6 分支 | V6 按档 seed 偏移；v7 单 offset 规则保留 |
| 删 | `tests/lightweight/test_v6_candidate_values.py`、`test_v6_site_labels.py`、`test_v6_site_v11.py`、`test_v6_tier_monotone.py` | 只测被删的 V6 站点／检查器 |
| 改名保留 | `test_v6_difficulty_tiers.py` → `test_v8_difficulty_tiers.py`（五档断言，删 v6 seed 两个测试）；`test_v6_swap_uniform.py`、`test_v6_xhard_movecube_region.py`、`test_v6_audit_fix.py`、`test_v6_audit_fix_scripts.py` 去掉 `v6_` 前缀 | 测的是现行环境行为（交换均匀化、MoveCube 区域、审查修复后的语义），与 V6 对拍无关；删了就丢覆盖。用户要求「全部删除」时按删处理 |
| 改名保留 | `scripts/injection-dev/export_eval_identities.py::V6_SECONDS` → `TASK_SECONDS` | 是 v6 评估实测的每任务单局用时，用于分片均衡，不是对拍 |
| 留（只读） | `docs/validation/newtask-v6/`、`docs/plans/0925-newtask-release-v6-plan.md` | 留档，git 可取回；是否删由用户另说 |
| 不动 | `scripts/configs/newtask-v3/`、`newtask-v7/xhard0_manifest.json`、`hard-parity-tolerances.json` | V3 官方 train 元数据、xhard0 清单、V7 对拍容差，xhard0 对拍与 V8 对拍仍用 |

另：`AGENTS.md` 第 0 条判据表「仓库根」一栏的当前分支名在本轮分支对齐中由 `newtaskRelease-v5` 改为 `newtaskRelease-taskV8`（标记块外，允许改）。

## 2.2 交付形态改动（合作者的表要求的，不属于数值配置）

**现行假设**：
- 全局只有一个 `--select 0..19` 和一个 `delivery_per_cell=20`。
- 55 格表 `EXPECTED_CELLS` = `XHARD4_ONLY` 推出来的格子。
- 四档必须交付同一组 20 个候选。
- builder 里写死 `!= 20`。

**要改的地方**：
1. `hard_specs.py`：把 `EXPECTED_CELLS` 换成逐格局数表 `{task: {tier: count}}`（取值即第一部分表 2，43 格）；header 的 `delivery_per_cell` 改成逐任务字典（升 schema）；`validate_specs` 按表核对。
2. `hard_builder.py::_test_hard_entries`：去掉写死的 20，改为查表；按 `hard_specs.TIERS`（含 xhard5）依次读 `env_metadata/test-hard/<tier>/specs.jsonl`，xhard5 文件里没有的任务跳过。xhard0 保留（引言「已定」），涉及 `_xhard0_entries`、`XHARD0_PER_TASK`、`BUILDER_TIERS`。
3. `_freeze.py::freeze` 与 `stratified_select`：加逐格配额；新增 seed profile `v8`，`freeze_specs.py` 对每个交付格（任务 × 档）各跑一次独立抽签，header `layout_rule = {"mode": "independent"}`、行 `layout_parent = null`。不再需要按值分层（每档单值）。
4. **不派生**（用户拍板①③④）：`derive_specs.py`、`_check_layout_parent`、`layout_whitelist.json` 原样保留供 v7 规格通过，v8 一律不调用；不交付的档不抽、不生成。各档布局互相独立，低档不照抄高档前缀。
5. `_rollout.py`：`_task_tiers`、`initial_pool`（不再从 xhard4 初选取交集，改为每格读自己的 `initial_selected`）、`sync_drop_and_backfill`（逐格独立递补，新增 `exec_over_cap` 丢弃原因；某格某候选失败只退该格）、`delivery_rows`、`V7_BACKFILL_CAP` 都改为逐格。判定行改名为 `V8_DELIVERY_SET`。
6. **下游写死的数**：PickXtimes 50（含 xhard0 62）、SwingXtimes／StopCube 各 50（62），其余与 v7 相同（92／32）；全集 1070（含 xhard0 1262）。
   - `hard_parity.py::SHAPES`（`13x3x20+16x1x20`）要改成逐格表（按档 411／411／128／100／20）。
   - `hard_regression.py` 的 `delivery_index`、`_replay_targets`、`cmd_eval_smoke`（92／32）：改为按任务查表（62／62／92／32）。
   - `export_eval_identities.py`（1292、646）、`site/v7_site_catalog.py`（1292）：按 1262 与逐任务数重算。
7. **每格局数取整**：
   - PickXtimes 50 ÷ 3，取 17／17／16（用户拍板②「全部都是 50 局来分配」）；SwingXtimes／StopCube 50 ÷ 5 = 10，整除。
   - VideoUnmask／ButtonUnmask：四档各 20，不需要取整。
   - RouteStick／PatternLock：80 ÷ 3，取 27／27／26。
   - 取整按「低档多一局」，已按「取整等细节自己定」的长期指示决定。

## 2.3 闸门总表

| 闸门 | 命令 | 判定行 |
|---|---|---|
| 官方源码与借用闭包 | `uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | `UPSTREAM_GUARD=PASS` |
| 录像器冻结 | `git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` | 退出码 0 |
| 四入口 | `ls -1 scripts/*.py` | 恰好四个 |
| 核心短测 | `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q` | 无 failed |
| 布局独立 | `validate_specs`（`mode == independent`、`layout_parent` 全 null） | `V8_LAYOUT_INDEPENDENT=PASS files=5 rows=1070` |
| 站点 | `v8_site_browser_check.py --shots <目录>`；评估位置空不缺 | `V8_SITE=PASS sections=9 eval_placeholders=<n> missing=0` |
| 定值 | `hard_regression.py tier-values`（自 `v6_tier_monotone.py --fixed` 迁入） | `V8_TIER_VALUES`（由 V7_* 改名）；`layout-shared`／`prefix-geometry` 保留不跑 |
| 交付、取值、上限 | 见第一部分 §3 | `V8_DELIVERY_SET`／`V8_TIER_VALUES`／`V8_STEP_CAP` |
| 回注回放 | `hard_regression.py reset-replay` | `V8_RESET_REPLAY=PASS` |

## 2.4 runbook

### 2.4.1 复现本轮探针（只读仓库，产物落 `artifacts/v8-probe/`）

`jobs.json` 每行：

```json
{"task": "PickXtimes", "episode": 840, "seed": 14184000, "attempt": 0, "difficulty": "xhard4",
 "seed_rule": {"env_block": 100000, "episode_stride": 100, "formula": "offset + env_code*env_block + episode*100 + attempt", "offset": 14000000},
 "worker_dir": "artifacts/v8-probe/<轮>/<标签>/episodes/PickXtimes_episode_840"}
```

`sampling.json` 的取法：
- 形如 `{"tasks": {"PickXtimes": <cfg>}}`。
- `<cfg>` = v7 xhard4 header 的 `sampling_config["PickXtimes"]`，再改 decision 里的键，例如：

```json
"number_range": {"xhard4": [10, 10]},
"xhard4": {"goal_position_policy": {"region_center": [0.0, 0.0], "region_half_size": 0.15}}
```

运行：

```bash
ROBOMME_ENV_PACKAGE=robomme_hard OMP_NUM_THREADS=1 uv run --no-sync python scripts/parity/train_split_runner.py --src-root . --jobs-json jobs.json --results-json results.json --workers 10 --gpu 0 --sampling-config sampling.json --identity-source formula --no-recovery
```

每局跑完后读 `worker_dir/hdf5_files/*.h5`：执行步 = `timestep_*` 个数 − `info/is_video_demo` 为真的帧数。读完即删 h5 与 mp4。逐局结果在 `artifacts/v8-probe/{smoke,r1,r2,r2b,r3,r4}/results.jsonl`，PickXtimes 合并表在 `artifacts/v8-probe/px_rows.json`（含每局 d）。

### 2.4.2 正式生成（阶段 3，须先获批）

- **先打印预算**：`freeze_specs.py --dry-run --seed-profile v8`（43 格逐格）。按 P5 写成乘式后一次性报给用户。
- **逐格独立抽签**：43 个交付格各自抽，每格候选数约为「该格局数 × 1.3」，加上抽签拒绝率；不派生，不为不交付的档抽。
  - v7 的 xhard4 抽签接受率：VideoPlaceButton／VideoPlaceOrder 约 46%、VideoRepick 约 54%、ButtonUnmaskSwap 57%、PickHighlight 65%，其余 97～100%。
- **生成**：交付 rollout 共 1 任务 × (17 + 17 + 16) + 2 任务 × 5 档 × 10 + 4 任务 × 4 档 × 20 + 7 任务 × 2 档 × 40 + 2 任务 × (27 + 27 + 26) + 2 任务 × 1 档 × 20 = 1070 局（逐格见第一部分表 2），另加失败递补。v7 与本轮的失败率：
  - InsertPeg 37.5%、MoveCube 20%、BinFill 15～21%。
  - StopCube、SwingXtimes 约 7%。
  - 其余多为 0～5%。
  - 预算要按这些比例逐任务留，并写成乘式。
  - 过滤递补：候选专家执行步 > 1600 即丢弃递补。按本轮实测只有 PickXtimes 8 次会触发（原区域 21 局 0 超，强制近底座带 1 局 1614，估约 1/22），其余任务 0；预算按此留。
- **seed 偏移**：建议新开一个 offset（例如 16e6），与 v7 的 14e6 和本轮探针（14e6 + episode ≥ 500）都不重叠。

## 2.5 风险登记

1. **过滤改变布局分布**：过滤掉执行步 > 1600 的候选，会把 PickXtimes 8 次里极近底座的布局剔掉（估约 1/22），分布略偏离原区域；其余任务按实测不会触发。
2. **上限定死 1600 对策略侧的截断**：专家侧按构造不超；策略成功局可比专家长（§2.9.5），v7 评估里有 2 局成功会被截（BinFill xhard2 1823、MoveCube xhard4 3120）。
3. **生成失败**：InsertPeg 37.5%、MoveCube 20%、BinFill 15～21%、StopCube／SwingXtimes 约 7%。v8 里 InsertPeg 和 MoveCube 仍各交付 20 局，与 v7 相同，但 v7 的 InsertPeg 已经用满每格 10 的递补上限、追加一轮才补齐，v8 的递补额度至少按 v7 实际消耗留。BinFill 两档各 40 局，比 v7 每格 20 多一倍，按 15～21% 失败率每档要留约 8～10 局递补。
4. **硬件差异**：本轮在 Ada 上测，正式生成在 A40 上。screw 规划是确定的，步数应一致；但 RRT 兜底（`ScrewThenRRT`）带随机性，可能有个别局不同。
5. **布局独立带来的差异**：各档独立抽布局后，同任务跨档不再共享圆盘位置等前缀，跨档比较时布局噪声与难度梯度叠在一起；换取的是不需要派生链、每格过滤 > 1600 各自独立。`layout-shared`／`prefix-geometry` 守卫对 v8 规格无意义，不跑。
6. **新增档位的结构改动面**：xhard5 牵动 `difficulty.py`、`hard_specs.TIERS`、builder、抽签 profile、站点与约 27 个测试文件里钉四档的断言（§2.1）。这是 v6 以来第一次改档位枚举，核心短测与 `XHARD0_RESET_PARITY` 必须全绿才能进阶段 2。StopCube 首次进入冻结规格，`reset-replay` 回注回放要覆盖它。

## 2.6 盲区诚实清单

- PickXtimes 8 次在原区域只有 21 局实测（最大 1533）；1614 那局来自强制近底座带，原区域内可达。正式抽样被过滤的比例只能估计约 1/22。
- 「近底座强化带」有一半成功局落在原区域外，它的数字不是原区域的上界。
- 探针走的是现场抽样，不是 v7 的「母布局 → 派生」链路；也没在 A40 上跑。
- xhard5 档没有在任何链路上跑过：本轮探针是把取值从外部传给 xhard4 的 decision（§2.4.1），等价于「xhard5 = 10 次、干扰 4 块」，但档位枚举、builder、派生都没经过。
- SwingXtimes 5、7 轮与 PickHighlight、VideoRepick、Unmask、Swap、Place、PatternLock、RouteStick 都直接沿用 v7 每格 20 局的数据，本轮没有重测。
- StopCube 每个值只有 1～3 局（执行步由时钟决定，波动 ≤ 10 步）；1/13 的生成失败是小样本。
- 没有测新配置下的策略成功率；按用户 2026-10-01 决定，v8 不做两策略评估，站点评估板块置空。
- VideoUnmask／ButtonUnmask xhard1 的 2／4／2 没单独测，上界按 xhard2 的 3／4／2（454／557）推断。RouteStick／PatternLock 区间档的最大按上端 16 段 800、18 节点 626，与定值时相同。
- 230 局里有 19 局是我把区域写错（开局即 `ValueError`），不是环境问题；在 §2.10.1 单列，不计入任何失败率。

## 2.7 留档与 commit 纪律

- 本文件 12.277 首版、12.278／12.279 修订局数、12.280 重写第一部分并建分支、12.281 修订梯度（去 9／10 次、过滤 1600、VU／BU xhard1、区间档），每次只 `git add` 这一个文件。工作区里 `third_party/SimpleMemVLA` 的子模块内容改动（` m`）是他人在途工作，不动。
- 探针产物 `artifacts/v8-probe/` 不进 git。探针脚本在会话 scratchpad 不保留，方法按 §2.4.1 可以复现。
- 12.282 只记录本轮分支对齐文档；12.283 记录四项拍板；12.284 记录站点与评估口径，均不算 V8 实施。后续获批的 V8 实施在分支 `newtaskRelease-taskV8` 上进行；每个阶段单独 commit，从 12.285 接续。commit body 按第 11 条写用户原话、计划、过程、意外、实测与下一步。正式生成的留档写到 `docs/validation/newtask-v8/`。

## 2.8 口径来源：用户原话（逐字，按时间）

1. **合作者的交付表**，用户转述，逐字照录：
   > 你有的档位设置的太离散了
   >
   > BinFill, xhard 1,2 即 put 6,7 个cube, 各 25 episodes
   > PickXtimes, pick times 改成 6, 7, 8, 9,10 各10 episode
   > SwingXtimes 摆动 4,5,6,7,8次 各10 episode
   > StopCube 次数 6,7,8,9,10 各10 episode
   >
   > VideoUnmask/ButtonUnmask xhard1-4 各 50/4 episodes
   > VideoUnmaskSwap/ButtonUnmaskSwap  保留xhard 1,2， 各 25 episodes
   >
   > VideoPlaceButton/VideoPlaceOrder 保留 xhard 1,2，各 25 episodes
   > PickHighlight  保留 xhard 1,2，各 25 episodes
   > VideoRepick 保留 xhard 1,2，各 25 episodes
   >
   > MoveCube xhard4 only
   > InsertPeg  xhard4 only
   > RouteStick xhard1,2,3  各 50/3 episodes
   > PatternLock  xhard1,2,3  各 50/3  episodes
   > 嗯嗯收到好的
   > 生成完data后，确定出expert demo 里面的最大execution step, 作为 max_step， 应该在 1600 附近
   > 现在的执行上限都是虚高
2. 「给出下一版的方案 只给出配置调整的方案 你可以实测 max step尽可能在1600左右这是你先统计一下现在超过一千600步的task然后你再调整一下这个配置然后实测一下然后尽可能给我一个完整的结论」
3. 「调整的内容只能是XHard。1234的这些梯度。」
   - 我的理解：xhard0（即官方 hard）和原三档 easy／medium／hard 一律不动，只调 xhard1～4（第 8 条之后含三任务新增的 xhard5）。
   - 方案 A 收紧的圆盘区域也在 xhard 子树里（`PickXtimes.py::XHARD_DECISION`），不影响 xhard0。但它不是「梯度值」，超出这句话的字面范围，所以列为待决项（引言「待拍板」①）。
4. 「尽可能使用塞subagent」
5. 「结束之后把你的计画和所有的教训结论都写入一个根目录文档。」（即本文件）
6. /goal：「尽可能给我完整的结论和调整建议 我要吃饭去了 你可以自己在本机随便跑reset 和 rollout 单次配置调整尽可能先少跑一些先把各个配置都跑完了有一个全面的了解了在跑。单个配置更多的resetrout。并且你每次跑日晒汤乳酪的时候你要稍微测个速对于一次工作的时间要有一个认知不能跑太久了尽可能在两小时内收尾」
   - 「日晒汤乳酪」按语音转写理解为「reset 和 rollout」。
   - 本轮实际做法是：先每个配置 3～4 局全覆盖，再给关键配置加量；每轮都测速。13:14 开工，13:41 跑完第四轮（东部时间）。
7. 「episode数量先都不改都按照V7生成的总数量。然后如果档位XR的1234中有缺少这个档位比如说X2的只有12这种情况下就把数量平分。就是保证总数是一样的修改计划并且重新告诉我现在要改成什么样」（2026-10-01，本文件修订依据）
   - 我的理解：每任务总局数与 v7 相同（四档任务 80、仅 xhard4 任务 20）。四档齐全的任务仍每档 20；只保留部分档的任务把 80 平分到保留的档（两档各 40，三档 27／27／26，低档多一局）。
   - 本条对 PickXtimes、SwingXtimes、StopCube 的部分（原拟 xhard4 放两个值按值平分、StopCube 单档分层）已被第 8 条取代，这三个任务改为五档各 10 局。
8. 「PickXtimes, pick times 改成 6, 7, 8, 9,10 各10 episode／SwingXtimes 摆动 4,5,6,7,8次 各10 episode／StopCube 次数 6,7,8,9,10 各10 episode　这些都需要改为xhard12345 每一档都是确定的　其他都可以了」（2026-10-01，本文件第二次修订依据）
   - 我的理解：这三个任务新增 xhard5 档，xhard1～5 每档恰好一个取值（PickXtimes 6／7／8／9／10 次，SwingXtimes 4／5／6／7／8 轮，StopCube 6／7／8／9／10 次），每档 10 局，每任务 50 局；不再有「一档两个值」或「单档按值分层」。
   - 「其他都可以了」理解为其余 13 个任务按第 7 条（局数沿用 v7、缺档平分）不再改；其他任务不加 xhard5。
   - 全集总数：3 任务 × 5 档 × 10 + 4 任务 × 4 档 × 20 + 7 任务 × 2 档 × 40 + 2 任务 × (27 + 27 + 26) + 2 任务 × 1 档 × 20 = 150 + 320 + 560 + 160 + 40 = 1070；含 xhard0 则 1070 + 16 × 12 = 1262。
9. 「给我呈现一个这样的完整表格　你现在的废话太多了 第一部分（给人看）彻底重写第一部分对于难度的表述只写在表格内就是这个表格来表达这个梯度的问题。然后你再说你需要修改哪些文件内容最后说怎么去验收我不需要再去对拍V6了我还是需要之前的XR的0对拍但是新的V7的只需要保留V7V6的可以全部删除。」（2026-10-01，附用户贴回的梯度表；本次重写依据）
   - 我的理解：第一部分只留「梯度表 + 局数表」「要改哪些文件」「验收」三节；xhard0 保留且 xhard0 对拍（`xhard0-reset-parity`／`xhard0-eval-parity`）保留；V6 的对拍、配置、站点、检查器与只服务它们的测试删除；V7 的对拍设施保留并改名 V8。
10. 「你现在先表上只写在计划里并且让这个计划要开启一个新的Bronch现在的Brach是v5改成v6。」（2026-10-01）
   - 我的理解：本轮只改计划、不动代码；v8 在新分支 `newtaskRelease-v6` 上实施，自 `newtaskRelease-v5` 的 `49ba3eb8` 分出，本次计划 commit 落在新分支。
11. 「我要的是你不改任何的这个非难度梯度以外的参数你如实的报告我哪些会抄了不要自己改。」（2026-10-01）
   - 我的理解：圆盘区域等非梯度参数一律不动，方案 A 作废。只改梯度值时超 1600 的是 PickXtimes 抓 9 次（最大 1973）与抓 10 次（最大 1919），抓 8 次偶尔（1614）。
12. 「PickXtime 的 9/10次去掉　sample 的时候全部任务 filter 掉execution 超过 1600 的　VideoUnmask ButtonUnmask Xhard1 是 2/4/2　RouteStick, xhar1 8-10, xhard2 11-13, xhard3 14-16　PatternLock  xhar1 9-12, xhard2 13-15, xhard3 16-18」（2026-10-01，本次修订依据）
   - 我的理解：PickXtimes 交付 xhard1～3 = 6／7／8，每档 10 局；抽样阶段全部任务按候选的真实 h5 过滤执行步 > 1600 并递补，上限定死 1600；VideoUnmask／ButtonUnmask xhard1 改为抓 2、干扰容器 4、干扰方块 2；RouteStick、PatternLock xhard1～3 改为区间、档内均匀抽。
13. 「各档布局改为每一个都是独立的初始化位置不需要再做重叠的」（2026-10-01，答原「待拍板」①）
   - 我的理解：每个交付格各自独立抽初始化布局，不再从母布局派生，低档不照抄高档前缀；`derive_specs.py` 链路 v8 不走。
14. 「还有什么我没有定下来」→ 我列出四项：PickXtimes 30 还是 50 局、派生工具链删还是留、不交付的档抽不抽、V6 留档删不删。
15. 「1全部都是50局来分配 2保留 3只抽交付的 4留着」（2026-10-01）
   - 我的理解：①PickXtimes 50 局分三档 17／17／16（低档多一局），每任务合计改 62、全集 1070、含 xhard0 1262；②`derive_specs.py`、`layout_whitelist.json`、`layout-shared`／`prefix-geometry` 守卫保留在仓库，v8 不调用；③只抽 43 个交付格，不交付的档不抽、不生成；④`docs/validation/newtask-v6/` 与 `docs/plans/0925-newtask-release-v6-plan.md` 保留只读。
   - 第 8 条里 PickXtimes 「每档 10 局」的记法被本条取代。
16. 「你需要和上一代一样生成一个同样的网站尽可能保持这个布局的完全一致但是因为现在没有新的两个model的invution的制空不要删除。Evaluation就没有新的两个model的evaluation了」（2026-10-01）
   - 「invution的制空」按语音转写理解为「evaluation 的置空」。我的理解：v8 出一个与 v7 站点布局完全一致的逐局站点；v8 不跑 SimpleMemVLA／MME-VLA 评估，站点里评估相关板块原位保留、内容置空、不删；阶段 4 的评估侧核对随之取消，xhard0 评估对拍引用 v7 结果。
   - 复核时发现 §2.5 原拟删除的 `v6_site.py` 是 v7 站点服务端，改为改名 `site_server.py` 保留。

## 2.9 现状、机理与上限取法（原第一部分 §1～§3、§4.1、§6，逐字搬入）

### 2.9.1 现状：v7 有多少局超过 1600

数据来自 v7 gen1 交付的 1100 局。逐局重算的结果与 `artifacts/newtask-v7/step-headroom-gen1.json` 的 `per_cell_max`／`per_cell_mean` 在 55 格上全部一致。

| 格子（梯度值） | n | 执行步均值 | max | 超过 1600 的局数 |
|---|---|---|---|---|
| PickXtimes xhard2（抓 10 次） | 20 | 1588 | 1857 | 6 |
| PickXtimes xhard3（12 次） | 20 | 1889 | 2293 | 20 |
| PickXtimes xhard4（15 次） | 20 | 2354 | 2998 | 20 |
| BinFill xhard3（投 8 块） | 20 | 1518 | 1650 | 2 |
| BinFill xhard4（投 9 块） | 20 | 1689 | 1842 | 16 |

- **超限的局**：共 64 局超过 1600，全部是 PickXtimes 和 BinFill。xhard0 的最大值是 BinFill 1074。
  - 按含演示段的总步数算会有 204 局超过 1600，多出来的是 RouteStick、VideoPlaceButton、VideoPlaceOrder、VideoRepick 这类演示很长的任务。上限只约束执行段，所以与它们无关。
- **现行上限怎么来的**：`hard_specs.py::TIER_MAX_STEPS = {xhard0:1300, xhard1:1500, xhard2:2400, xhard3:2900, xhard4:3800}`。
  - xhard2～4 的值来自 B4 规则：取「实测最大执行步 × 1.25」，再向上取整到百；实测最大值来自 PickXtimes 的 1857／2293／2998。xhard1 的 1500 沿用 v6。
  - 同档其余任务全部继承这个上限。例如 InsertPeg 专家最多只要 277 步，却给了 3800 步。
- **评估侧证据**：
  - 两策略合计 2 × 1292 局里，成功局超过 1600 步的只有 2 局，都是 SimpleMemVLA：BinFill xhard2 一局 1823 步，MoveCube xhard4 一局 3120 步。
  - xhard1～4 中，timeout 局消耗的策略评估步数约占全部评估步数的 36%（SimpleMemVLA 307,500／860,944）。这里是策略侧步数，不是文首定义的专家执行步。
  - 所以「虚高」成立。

### 2.9.2 按合作者的表直接套用：各任务最大执行步

| 任务 | 新表取值 | 执行步 max（n） | > 1600？ |
|---|---|---|---|
| **PickXtimes（原区域）** | 6／7／8／9／10 次 | 1282（4）／1304（v7 20）／1533（21）／**1973**（22）／**1919**（8） | **9、10 次超** |
| PickXtimes（近底座强化带，含原区域外位置） | 6～10 次 | 1301／1408／**1614**／**2002**／**1990**（各 2～3）；其中圆盘落在原区域内的只有 7 次 1408、8 次 1614、9 次 2002 | 原区域内 8、9 次也可能超 |
| BinFill | 6／7 块 | 1315（本轮 6 + v7 20）／1464（本轮 17 + v7 20） | 否 |
| SwingXtimes | 4～8 轮 | 618（4）／732（v7 20）／841（4）／913（v7 20）／983（9） | 否 |
| StopCube | 6～10 次 | 371／424／492／555／611（各 1～3） | 否 |
| PickHighlight | xhard1、2 | 960／1152（v7 各 20） | 否 |
| VideoRepick | xhard1、2 | 422／616 | 否 |
| ButtonUnmaskSwap／VideoUnmaskSwap | xhard1、2 | 494、648／273、429 | 否 |
| VideoUnmask／ButtonUnmask | xhard1～4 | ≤454／≤557 | 否 |
| VideoPlaceButton／VideoPlaceOrder | xhard1、2 | 执行段 ≤236／≤259；演示段逐局 868～1707 帧，不计入 | 否 |
| PatternLock | 12／15／18 节点 | 422／521／626 | 否 |
| RouteStick | 10／13／16 段 | 恒为 500／650／800（= 50·L） | 否 |
| MoveCube／InsertPeg | xhard4 | 300／277 | 否 |

**结论**：不调整的话，全集最大执行步由 PickXtimes 抓 9～10 次决定，约 1900～2000，不是 1600。排第二的是 BinFill 7 块，约 1460。

### 2.9.3 机理：PickXtimes 的长尾来自圆盘近底座时的零空间漂移

**定义**：PickXtimes 的执行段由三部分组成。

| 段 | 内容 | 步数 |
|---|---|---|
| 首轮抓放 F | 从 home 出发，带水平运输 | 182～260，均值约 220 |
| 第 2～N 轮循环 Σc_k | 方块已在圆盘上，原地「抓起 → 放回」 | 正常每轮 123～158 |
| 按钮 B | 按下按钮结束 | 稳定布局 91～122，均值约 104 |

- 夹爪每次开合固定 6 步。
- 按 v7 交付 92 局做最小二乘：exec ≈ 121 + 148·N（只算粗略，同一 N 的波动由布局决定）。

**代码锚点**：
- 子目标表：`PickXtimes._load_scene`。
- 抓放：`subgoal_planner_func.py::solve_pickup`、`solve_putonto_whenhold`。
- 规划：mplib `Planner.plan_screw`。先用 pinv(J) 做微分 IK，再用 TOPPRA 做时间参数化，步数 = int(时长 / 0.05)。
- 圆盘区域：`PickXtimes.py::XHARD_DECISION["goal_position_policy"]`，现值中心 (−0.1, 0)、半宽 0.2。
  - `spawn_random_target` 要求圆盘完整落在方区内，所以圆盘中心范围是「中心 ± (半宽 − 半径 0.04)」，现值下 x ∈ [−0.26, 0.06]。
  - 按钮由 `build_button` 随机放在 x ∈ [−0.25, −0.15]、y ∈ [−0.2, 0.2]，圆盘还要避开它。

**漂移的过程**：
- d 小于约 0.5 时，手臂在圆盘上方是折叠姿态：第 4 关节约 −2.6～−2.8 rad，关节 0 与关节 2 接近同轴。
- pinv 微分 IK 每轮都沿零空间滑一点。末端走的笛卡尔路径不变（约 0.27 m），关节路程却越来越长。
- 例：v7 cand 17 共 14 轮循环，q0 累计 +0.84 rad，每轮关节路程从 1.95 rad 涨到 4.88 rad，每轮步数从 158 涨到 235。

**示意**（同为抓 10 次，执行步随 d 变化；数据来自 v7 xhard2 与本轮探针）：

```text
d:     0.37  0.39  0.40  0.44  0.45  0.46 | 0.49  0.51  0.52  0.58  0.64  0.66
执行步: 1919  1857  1802  1750  1647  1615 | 1580  1558  1585  1591  1471  1457
       └──────── 漂移带：每轮 +1～6 步 ────────┘└──── 稳定：每轮步数近似常数 ────┘
```

d ≥ 0.5 之后已经没有漂移。剩下 1457～1591 的差别来自方块与圆盘的相对位置：每轮循环本身长短不同，但不再逐轮变长。

**⚠ 陷阱**：
- 这条长尾**不是** RRT 重试，也**不是** fail-safe。
  - v7 有 80 局 PickXtimes、共 5520 段运动，按 `eef_action` 查直线度，偏离弦线最多 3.8 cm，看不到绕行。
  - `--no-recovery` 下，夹爪重抓段数为 0。
- **干扰块数不影响步数**：screw 规划不带点云避障（`use_point_cloud=False`）。同一 seed 下干扰从 1 块到 4 块，前缀步数差 ≤ 15 步。
  - 本轮第一轮里，抓 10 次配 1 块干扰最大 1647、配 4 块干扰最大 1919，差别全来自 d（0.452 对 0.368），不是来自干扰块。
- **只看少量样本会严重低估尾部**：
  - v6 同一格，3 局的最大值约 2215，20 局的最大值是 3384。
  - 本轮原区域抓 9 次，前 12 局最大 1676，再加 10 局就到了 1973。
- **0.45 附近仍然漂移**：d = 0.451 的一局抓 9 次 1676，d = 0.452 的一局抓 10 次 1647。所以阈值要取 0.5，不能取 0.45。

**收益**：
- 圆盘中心收进 x、y ∈ [−0.11, 0.11] 后，d ≥ 0.505（实测最小 0.5097）。
- 本轮探针抓 6～10 次的最大值是 1046／1143／1275／1421／1577。
- v7 里本来就落在这个区域内的 6 个布局：抓 7 次最大 1182，抓 10 次最大 1591。
- 抓 10 次合计 44 局的极差为 1424～1591。同档波动从原区域的 1424～1919 收窄到约 170 步以内。

### 2.9.4 PickXtimes 方案 A／B 对比（原 §4.1；已作废：用户定非梯度参数不改、9／10 次去掉）

| 方案 | 抓取次数（xhard1／2／3／4／5） | 圆盘区域（xhard1～5 共用 `XHARD_DECISION.goal_position_policy`） | 本轮实测最大执行步 | 评价 |
|---|---|---|---|---|
| **A（推荐）** | 6／7／8／9／10 | 中心 (−0.1, 0)、半宽 0.2 → **中心 (0, 0)、半宽 0.15**；圆盘中心 x、y ∈ [−0.11, 0.11]，d ≥ 0.505 | 本轮 1046／1143／1275／1421／1577（n = 10／10／10／12／38，0 失败）；加上 v7 区域内布局后，7 次 1182、10 次 **1591** | 保留合作者的 6～10 次（五档各 10 局），已知全集最大约 1590，上限 1600。代价是改了一个布局参数，不是梯度值 |
| B（只改梯度） | 4／5／6／7／8 | 不动 | 8 次 1533（21 局），极近底座布局 1614 | 完全符合「只改梯度」，上限 1600～1700。但最难档从 10 次降到 8 次，且 xhard1 的 4 次、xhard2 的 5 次与 xhard0（[4,5]）同难度 |
| 不调整 | 6／7／8／9／10 | 不动 | 9 次 1973、10 次 1919；原区域内近底座布局 9 次可达 2002 | max_step 会在 1900～2000，达不到「1600 附近」 |

方案 A 的几点说明：
- **区域改动只落在 xhard 子树**：`_newvalue_decision` 深拷贝 `XHARD_DECISION`，`_native_decision` 的原值 `goal_position_policy` 不动。`sampling_config.py::assert_native_decision` 剥掉新值键后与原值逐键比对，所以 xhard0 和原三档不受影响。
  - 本轮探针把同样的覆盖值从外部传进环境，这道守卫逐局放行，说明结构相符。
- **reset 代价**：半宽 0.15 的区域在 80 局里圆盘放置失败 0 次。区域收得更窄时会出现 `SceneGenerationError`（报错为 Region crowded or constraints too tight，圆盘与按钮、方块挤不下）：半宽 0.12 的近底座强化带 2/15，半宽 0.08 的内侧带 1/4。
- **对视觉分布的影响**：圆盘离开桌面靠近底座的那一侧，集中到桌面中部。方块区域（中心 (−0.1, 0)、半宽 0.25）不变。

### 2.9.5 统一步数上限的取法与零余量代价（原 §6；已被「抽样过滤 > 1600、上限定死 1600」取代）

**口径**
- `TIER_MAX_STEPS` 里 xhard1～5 都设成同一个 N，xhard0 保持 1300。
- 这样 `scripts/evaluation_hard.py` 不用改，P1 写明的「与 `evaluation.py` 只差 4 处」照旧成立。
- 上限的验收判定行见第一部分 §3 `V8_STEP_CAP`。

**N 的取法**
- N = 新交付集（正式生成后）逐局执行步的最大值，再向上取整到百。不再乘 1.25。
- 方案 A 下已知最大值是 1591（v7 区域内布局；本轮探针最大 1577），**预计 N = 1600**。
- 正式交付的最大值若超过 1600（例如 1612），就取 1700。

**零余量的代价**
- **专家侧几乎没有余量**：1591 离 1600 只差 9 步。另外，同一份规格的两次生成本身也有噪声——v7 H:H2 的 1100 局里有 13 局判为 RRT 噪声，帧数最多差 116。所以正式交付的最大值落在 1600 以上的可能性不能排除。
- **策略侧会被截掉一些成功**：策略的成功局可以比专家长不少。BinFill 约 1.25～1.4 倍（例：一局成功用了 1455 步，同一局专家 1049 步）；短任务可达 2～3 倍（VideoUnmask xhard2 一局成功用了 1552 步，MoveCube 一局 3120 对专家 470）。
  - N = 1600 时，v7 评估里会被截掉的成功局只有 2 局：BinFill xhard2 的 1823 步、MoveCube xhard4 的 3120 步。其余成功局都在 1600 以内。
- 要不要留余量（例如取 1700 或 1800）：已由第 12 条「上限定死 1600」决定，不留。

**判据要改写**
- `hard_regression.py::cmd_step_headroom` 现在是「90% 判据 + B4 ×1.25 提议」。上限等于实测最大值时，这个判据按定义必然 FAIL。
- 要改成「全集最大执行步 ≤ N」，并报出全局最大值。

## 2.10 本轮本机实测（原 §9）

**环境**：2026-10-01，sled-vail，2 × RTX 6000 Ada，32 核，HEAD `07d56981`。工作区 clean，只有 `third_party/SimpleMemVLA` 子模块内容有改动（git status 显示 ` m`），属于他人在途工作，未碰。

**做法**
- 从 v7 header 取 `sampling_config`，只覆盖 decision 里的几个键：`number_range.xhardK`、`xhardK.goal_position_policy`、`xhard4.stop_time_range`。
- 不传规格，走现场抽样（导出模式），再交给 `train_split_runner.py --identity-source formula --no-recovery`。
  - 起环境、跑 oracle、录 h5 的入口与 v7 生成相同（`train_split_worker.run_one`）。
  - 但没有走 v7 的「母布局 → 派生」链路：每局各自独立抽布局。
- seed = 14000000 + env_code × 100000 + episode × 100，episode 取 500～999，与 v7 的候选（< 100）不重叠。

### 2.10.1 规模与测速（P5 乘式）

| 轮次 | 内容 | 局数 | 成功 | 墙钟 | 单局秒（并发下） |
|---|---|---|---|---|---|
| 冒烟 | PickXtimes 8 次 × 1 | 1 | 1 | 59 s | 58 |
| 第一轮（广覆盖） | PickXtimes 5 配置 × 4 + SwingXtimes 3 × 4 + StopCube 3 × 3 | 41 | 41 | 221 s | 48～109 |
| 第二轮（PickXtimes 定向） | 最坏区域 5 × 3 + 边界 1 × 4（这 19 局区域写错，见 §2.11 第 3 条）+ 收紧区域 6／8／10 局 + 原区域 6／8 局 | 57 | 38 | 482 s | 122～143 |
| 第二轮补跑（与第二轮并行） | 近底座强化带 5 次数 × 3 + 收紧区域内侧 1 × 4 | 19 | 15 | 226 s | 144～225 |
| 第三轮（加量） | PickXtimes 收紧区域 10＋10＋4＋4＋8、原区域 10；SwingXtimes 6；StopCube 2 × 2；BinFill 10＋6 | 72 | 69 | 413 s | 47～170 |
| 第四轮（尾部） | PickXtimes 收紧区域 10 次 × 20 + 原区域 9 次 × 10 + BinFill 7 块 × 10 | 40 | 38 | 281 s | 137～212 |
| **合计** | | **230** | **202** | 各轮相加 28 分钟；因第二轮补跑、第三轮与第二轮重叠，实际墙钟 13:17～13:41 约 24 分钟 | |

- **失败构成**：230 局里失败 28 局。
  - 19 局是我把区域写错，开局即 `ValueError`：第二轮最坏区域 5 配置 × 3 = 15 局，加边界 1 配置 × 4 = 4 局。
  - 4 局 `SceneGenerationError`：PickXtimes 收窄区域内圆盘放不下 3 局（近底座强化带 2 局、内侧带 1 局，报错 Region crowded or constraints too tight），SwingXtimes 第一个目标采样失败 1 局。
  - 4 局 `environment reported failure`：BinFill 3 局、StopCube 1 局。
  - 1 局 `Fail to parameterize path`：近底座强化带。
- 每个 worker 约占 3.4 GB 内存。20～33 个进程并发时，机器负载 20～38，GPU 利用率很低（瓶颈在 CPU）。

### 2.10.2 PickXtimes（全部探针，按区域口径 × 抓取次数）

| 区域口径 | 抓取次数 | 尝试 | 成功 | 执行步均值 | max | 其中 d < 0.45 的局 | 失败 |
|---|---|---|---|---|---|---|---|
| 原区域（v7 现值） | 6 | 4 | 4 | 1081 | 1282 | 2 | — |
| 原区域 | 7（v7 gen1） | 20 | 20 | 1154 | 1304 | 5 | — |
| 原区域 | 8 | 21 | 21 | 1249 | 1533 | 2 | — |
| 原区域 | 9 | 22 | 22 | 1451 | **1973** | 4 | — |
| 原区域 | 10 | 8 | 8 | 1576 | **1919** | 1 | — |
| 近底座强化带（中心 (−0.25,0)、半宽 0.12；圆盘中心 x ∈ [−0.33,−0.17]，比原区域的 −0.26 更靠近底座，12 个成功局里 6 局落在原区域外，d = 0.29～0.36） | 6／7／8／9／10 | 3／3／3／3／3 | 3／2／2／3／2 | 1280／1372／1498／1840／1970 | 1301／1408／1614／2002／1990（原区域内可达的只有 7 次 1408、8 次 1614、9 次 2002） | 全部 | 场景 2、规划 1 |
| **收紧区域（方案 A）** | 6 | 10 | 10 | 971 | 1046 | 0 | — |
| 收紧区域 | 7 | 10 | 10 | 1101 | 1143 | 0 | — |
| 收紧区域 | 8 | 10 | 10 | 1232 | 1275 | 0 | — |
| 收紧区域 | 9 | 12 | 12 | 1367 | 1421 | 0 | — |
| 收紧区域 | 10 | 38 | 38 | 1493 | **1577** | 0 | — |
| 收紧区域内离底座最近的一侧（中心 (−0.07,0)、半宽 0.08） | 10 | 4 | 3 | 1509 | 1525 | 0 | 场景 1 |
| v7 gen1 里圆盘本来就落在方案 A 区域内的布局（6 个，跨档同布局） | 7／10／12／15 | 各 6 | 各 6 | — | 1182／**1591**／1863／2281 | 0 | — |

### 2.10.3 其余任务

| 配置 | 尝试 | 成功 | 执行步均值 | max | 失败 |
|---|---|---|---|---|---|
| SwingXtimes 4 轮（xhard1） | 4 | 4 | 596 | 618 | — |
| SwingXtimes 6 轮（xhard2） | 4 | 4 | 738 | 841 | — |
| SwingXtimes 8 轮（xhard3） | 10 | 9 | 928 | 983 | `SceneGenerationError` 1（First target sampling failed） |
| StopCube 6／7／8／9／10 次 | 3／2／3／2／3 | 3／1／3／2／3 | 367／424／489／552／608 | 371／424／492／555／611 | 7 次 1 局 `environment reported failure` |
| BinFill 6 块（xhard1，v7 配置） | 6 | 6 | 1202 | 1315 | — |
| BinFill 7 块（xhard2，v7 配置） | 20 | 17 | 1336 | 1434 | `environment reported failure` 3（15%） |

StopCube 的执行步 ≈ 60·次数 + 6，与公式 `steps_press = 60·k − 30` 加上按钮动作的长度吻合。

## 2.11 教训与结论（原 §11）

1. **最大执行步看的是尾部，尾部由布局决定。**
   - PickXtimes 的尾部来自 d < 0.5 时的零空间漂移，是规划器的伪影，不是任务难度。
   - 定上限、选取值都要看 max 和最坏布局，不能看均值，也不能只看 3～8 局。本轮原区域抓 9 次，12 局最大 1676，22 局最大 1973。
2. **用「强制布局带」做探针能很快看清机理，但要核对它是否落在真实区域内。**
   - 把圆盘区域强制放到近底座带，每个次数 3 局，就看到了 6～10 次的 1301～2002。
   - 但这条带（圆盘中心 x ∈ [−0.33, −0.17]）比原区域（x ≥ −0.26）更靠近底座，一半成功局落在原区域根本抽不到的位置。所以它只是「强化带」的取值，不是原区域的上界；原区域内可达的只有 7 次 1408、8 次 1614、9 次 2002。
   - 下次做强制带探针，先按真实区域的边界截取，再谈上界。
3. **强制区域时，半宽必须大于圆盘半径 0.04。**
   - `spawn_random_target` 要求「中心 ± (半宽 − 半径)」非空，否则 100% 报 `ValueError`。
   - 本轮第二轮把半宽写成 0.02 和 0.01，19 局开局即报错，白做了。
   - 圆盘还要给按钮让位（按钮随机在 x ∈ [−0.25, −0.15]、y ∈ [−0.2, 0.2]）。区域收窄后会出现 `SceneGenerationError`：半宽 0.12 的近底座带 2/15，半宽 0.08 的内侧带 1/4。
4. **干扰块不影响执行步**（screw 不带点云避障）。所以干扰块可以只当视觉梯度用，与步数上限无关。
5. **「按档一个上限 × 1.25」会把单个任务的伪影放大到全档。** 改成「全集一个上限 = 实测最大向上取整到百」时，要同时改写 `cmd_step_headroom` 的判据，否则它按定义必然 FAIL。
6. **探针不必改代码。**
   - runner 的 `--sampling-config` 能直接传 decision 覆盖值，区间语义仍在。
   - `assert_native_decision` 会挡住结构不符的覆盖，所以覆盖只能改值，不能加键。
7. **测速与规模感**：
   - 本机 32 核下 20～33 个进程并发，单局约 0.8～3.7 分钟。PickXtimes 抓 10 次约 2～2.5 分钟一局。
   - 一轮 40～72 局约 4～8 分钟；230 局各轮相加 28 分钟，因为几轮有重叠，实际墙钟约 24 分钟。
   - 每个 worker 约 3.4 GB 内存，瓶颈在 CPU，GPU 几乎空闲。
   - PickXtimes 的 h5 每局约 700 MB，读完步数要立刻删。
8. **即使配置不变，生成失败也要留递补额度。**
   - BinFill 7 块失败 3/20（v7 6 块失败 6/28）。
   - StopCube 失败 1/13（`environment reported failure`，原因未查）。
   - SwingXtimes 失败 1/18（第一个目标采样失败）。
   - 本轮没测、但 v7 记录在案的：InsertPeg xhard4 失败 12/32（37.5%），MoveCube xhard4 失败 5/25（20%）。这两个任务在 v8 仍各交付 20 局（与 v7 同），递补预算仍要按这个比例留；BinFill 两档各 40 局，比 v7 每格 20 多一倍，递补也要翻倍。
9. **子代理分工有效。** 5 个只读子代理分别统计 v7 逐局步数、还原 v6 旧数据、梳理代码落点、推导步长模型、汇总历史教训。它们并行跑了 11～17 分钟，主会话同时做探针，两边互不阻塞。

   v6 的 h5 已删，只能从留档小文件还原，每个取值只有 0～5 局，参考价值有限。v6 的档级统计 `v6_gt_lengths.json` 在 165 局重叠样本上与 h5 口径的 demo／exec／total 逐局相等，可以用。

   历史留档里有一句「这份文件的 exec 按视频帧计、比 h5 大」，没有找到证据，本轮核对也不成立。
10. **StopCube 拆档的代价要如实列出。** 原建议 S1（单档分层）只改一个区间常量；用户 2026-10-01 决定拆成 xhard1～5 五档定值后，须动 `require_xhard4_only` 闸门、`XHARD4_ONLY`、白名单 L／G 表和 4 个测试（第一部分 §2.1），这是用户知情后的选择，不再作为「不推荐」。
