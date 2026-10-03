# 1001 newtask v8：xhard 梯度（SwingXtimes／StopCube 扩至 xhard1～5）与 1600 步上限的配置调整方案

> **权威性**：本文件是 v8 配置调整的方案，只规划不实施：改 `src/robomme_hard` 常量、改 `TIER_MAX_STEPS`、删 V6、正式抽签与生成，实施范围、子代理分配表（第二部分 §2.12）与全部 reset／rollout 预算（§2.4.3）已于 2026-10-01 一次获批（§2.8 第 28 条），之后按依赖顺序连续执行，运行中按 §2.4.5 的预定动作处置、不再发起授权提问；只在出现表外任务、超预算或范围实质变化时停下补充授权。
>
> **分支**：v8 的现行分支为 `newtaskRelease-taskV8`，基于旧分支 `newtaskRelease-v6` 的 `f406abe5`（12.281）仅新增，旧分支名称与提交指针均保留。旧 `newtaskRelease-v6` 自旧 `newtaskRelease-v5` 的 `49ba3eb8`（12.279）分出；`49ba3eb8` 已包含 V8 计划，不能称作纯 v7 交付态。历史用户原话与当时理解保留在第二部分 §2.8；本次只对齐分支名称与当前说明，V8 仍只规划不实施。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`。
>
> **代码锚点**：v7 交付规格 `src/robomme_hard/env_metadata/test-hard/xhard{1..4}/specs.jsonl`（四份 header 的 `sampling_config_sha256` 都是 `4a308ee7…`，`seed_rule.offset=14000000`）。官方环境源码 `1fadc0ec`、官方生成编排 `d53f21a7`（vendor 在 `scripts/parity/official/`）都不改。
>
> **commit 编号**：12.277 首版；12.278、12.279 修订局数口径；12.280 重写第一部分（表格 + 改动清单 + 验收；删 V6 对拍；建分支 v6）；12.281 修订（PickXtimes 去掉 9、10 次；抽样过滤执行步 > 1600；VideoUnmask／ButtonUnmask xhard1 改 2／4／2；RouteStick／PatternLock 改区间；非梯度参数一律不改）。12.282 为分支对齐文档。12.283 修订（四项拍板：各档布局独立抽、PickXtimes 50 局分 17／17／16、派生工具链保留不调用、只抽交付格、V6 留档保留）。12.284 修订（v8 站点与 v7 布局完全一致、评估板块置空不删；v8 不做两策略评估；`v6_site.py` 服务端改名保留）。12.285 修订（维持 A40；7 个占位 job 已提交；xhard0 评估对拍与生成并行；生成完自动建站并通知）。12.286 本次修订（对抗验证：workflow 4 方向审查 57 条、反驳后保留 56 条，加 Codex 审查 9 条逐条核实成立，合并为 11 项修改——xhard5 不进全局族常量、按档 seed 偏移、阶段重排并补「换包」、schema/4 的加载与生成入口、判定行可产出且不误报、逐任务候选表、P3 一次性预算、GL 运行手册与 P4 通知链、站点逐段信息链、测试清单补全、表述更正；外加对抗验证后四项拍板）。12.287 记录 P3 预算整表获批，并写定 gen1 与二次生成结果不同时的处置口径（第二部分 §2.2 第 11 条）。12.288 为规则同步（正本 `2b0b735`「计划执行模式」）。12.289 修订（补第一部分 §4「子代理分工与合并（简述）」与第二部分 §2.12「子代理分配表」，按正本 `AGENTS.md` 第 2 条新子项；用户 2026-10-01「同意 开始修改v8 md」）。12.290 本次修订（Codex 审计后三项拍板：整份实施一次授权、H2 正常失败预定 (a)、reset 预算更正 7,715；新增 §2.4.5 运行中预定动作；§2.12 分配表 8 项修正——档位断言归 S1-A、S1-B 顺序派发与四条可达守卫、`H.TIERS` 归 S2-C、`load_specs_v8(root, expected_cells)` 契约、S4-A 提前合入、MoveCube 旧导入归属、独立 watchdog、Codex 口径）。真正的 V8 实施从 12.291 接续，整份已获批、不再逐步请示。
>
> **术语**：执行步 = h5 的 `timestep_*` 个数减去 `info/is_video_demo` 为真的帧数（口径同 `hard_regression.py::cmd_step_headroom`）；`TIER_MAX_STEPS` 只约束执行段；d = 放置圆盘中心到机械臂底座 (−0.615, 0) 的水平距离，单位米。
>
> **已定**（用户原话逐字见第二部分 §2.8）：非梯度参数一律不改（PickXtimes 圆盘区域不动）；PickXtimes 去掉 9、10 次，交付 xhard1～3 = 6／7／8；SwingXtimes、StopCube 扩为 xhard1～5 每档一个定值、每档 10 局，PickXtimes 17／17／16；VideoUnmask／ButtonUnmask xhard1 改 2／4／2；RouteStick、PatternLock xhard1～3 改区间（RouteStick 区间内均匀抽；PatternLock 只保证落在区间内、区间内比例不保证均匀）；抽样时全部任务过滤执行步超过 1600 的候选并递补，上限定死 1600；其余任务局数沿用 v7 总数、缺档平分；xhard0 保留，xhard0 对拍保留；V6 对拍不再跑，V6 设施删除；V7 对拍设施保留改名 V8；实施分支按本轮分支对齐改为 `newtaskRelease-taskV8`。**2026-10-01 四项拍板（原话见 §2.8 第 13～16 条）**：①各档布局各自独立抽初始化位置，不再从母布局派生、不要求前缀重叠；②PickXtimes 仍按 50 局分到三档，17／17／16；③派生工具链（`derive_specs.py`、`layout_whitelist.json`、`layout-shared`／`prefix-geometry` 守卫）保留，v8 不调用；④只抽交付的 43 格，不交付的档不抽、不生成；⑤`docs/validation/newtask-v6/` 与 `docs/plans/0925-newtask-release-v6-plan.md` 留档保留。**⑥站点与评估（原话见 §2.8 第 16 条）**：v8 交付一个与 v7 站点（`site/v7_site.html`）布局完全一致的逐局站点；v8 不做 SimpleMemVLA／MME-VLA 两策略评估，站点里所有评估板块（策略成功率列、成败筛选、每局的两段策略视频、旧入口对照、翻转标记）原位保留、内容置空，不删除；阶段 4 的「评估侧核对」取消。**⑦席位与并行（原话见 §2.8 第 17～19 条）**：维持 A40；2026-10-01 16:05～16:07 EDT 已提交 7 个 48 h 占位 job——生成席 `v8gen-hold-1～4`（63003408～63003411，各 1 A40／4 CPU／48 G）、xhard0 评估席 `v8eval-hold-1～2`（63003486、63003487，同规格）、编排席 `v8eval-orch`（63003488，standard 分区 1 CPU／4 G 无 GPU），清单 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/gl-hold-logs/hold-jobs-v8gen-20261001.txt`；xhard0 评估在评估席上跑、与生成并行（规模与口径见 ⑧②），v8 新局不评估；生成完成后自动建站、浏览器检查并推送通知，该链路读取并核验最终报告而不是只听完成行，只在当前会话存活时成立（P4），阶段 2 用六种小夹具走通成功与失败两类路径（第二部分 §2.4.4）。**⑧对抗验证后四项拍板（2026-10-01，原话见 §2.8 第 20～24 条）**：①二次生成对拍要跑：交付集 43 格再生成一遍，1 任务 × (17 + 17 + 16) + 2 任务 × 5 档 × 10 + 2 任务 × 4 档 × 20 + 7 任务 × 2 档 × 40 + 2 任务 × (27 + 27 + 26) + 2 任务 × 1 档 × 20 = 1070 局；②xhard0 评估两条路线（官方路线、hard 路线）都重跑：16 任务 × 1 档 × 12 局 × 2 策略 × 2 路线 = 768 局，只出 `XHARD0_EVAL_PARITY=INFO`，「v8 没改坏 xhard0」由确定性的 `XHARD0_RESET_PARITY` 证明；③PatternLock 不改采样代码，只改表述，生成后逐格报告节点数分布；④7 个占位 job 等全部任务结束后按清单释放，现在不动。
>
> **待拍板**：无。**已批准**：P3 一次性预算表（第二部分 §2.4.3）已于 2026-10-01 整表获批（原话「同意所有预算」，§2.8 第 25 条）：reset 上限 **7,715**（2026-10-01 更正：rollout 内的 reset 计入，原 4,452 漏算 1,425 + 768 + 1,070 = 3,263；§2.8 第 28 条）、rollout 上限 3,272、基础设施重试另列 ≤ 3,263（每身份 ≤ 1 次）；之后按整份清单连续执行，不再逐阶段申请同一授权；超出任一行上限时暂停受影响部分，合并为一次补充授权。**已批准（实施）**：2026-10-01 用户「1同意 2 a 3更正 其他全部同意」——整份实施与 §2.12 分配表一次授权；H2 正常失败预定为 (a) 保留 gen1；运行中裁决全部改为 §2.4.5 预定动作；Codex 审计提出的分配表 8 项修正全部采纳。

# 第一部分（给人看）

## 1. 难度梯度

表 1 是 v8 全部难度表述。xhard0 即官方 hard，不动。「不交付」= 数值仍在代码里、v8 不生成；「无」= 该任务没有这个档的配置。

| 任务 | 维度 | xhard0 | xhard1 | xhard2 | xhard3 | xhard4 | xhard5 | 改动 |
|---|---|---|---|---|---|---|---|---|
| PickXtimes | 抓放次数 | 4～5 | 6 | 7 | 8 | 9，不交付 | 无 | 改，原 7／10／12／15；9、10 次去掉，xhard4 留 9 只为保住四键结构（v7 兼容的配置与测试），不交付、不评估；9 次超 1600，不得用于生成 |
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
| RouteStick | 路线段数 | 4～7 | 8～10 | 11～13 | 14～16 | 19，不交付 | 无 | 改，原定值 10／13／16；`torch.randint` 在区间内均匀抽 |
| PatternLock | 图案节点数 | 4～8 | 9～12 | 13～15 | 16～18 | 21，不交付 | 无 | 改，原定值 12／15／18；反复生成随机路径，第一条落在区间内的即采用（拒绝采样），区间内各节点数比例不保证均匀（v6 区间 [21, 25] 实测 10 局为 21 节点 6 局、22 节点 2 局、23 节点 2 局）；不改采样代码，生成后逐格报分布 |
| MoveCube | 官方 xhard4 配置，三种运动方式分层 | 官方 hard | 无 | 无 | 无 | 不动 | 无 | 不动 |
| InsertPeg | 官方 xhard4 配置 | 官方 hard | 无 | 无 | 无 | 不动 | 无 | 不动 |
| 全部任务 | 步数上限 `TIER_MAX_STEPS` | 1300 | 1600 | 1600 | 1600 | 1600 | 1600 | 改，原 1500／2400／2900／3800；定死 1600。抽样时全部任务过滤执行步超过 1600 的候选并递补，交付集按构造不超；保证范围限于交付 h5 的非演示步，二次生成（H2）超限只记录 |

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

乘式：新值局 1 任务 × (17 + 17 + 16) + 2 任务 × 5 档 × 10 + 2 任务 × 4 档 × 20 + 7 任务 × 2 档 × 40 + 2 任务 × (27 + 27 + 26) + 2 任务 × 1 档 × 20 = 50 + 100 + 160 + 560 + 160 + 40 = 1070（12.285 及以前误写成 4 任务 × 4 档 × 20，那样加起来是 1230；四档齐全的只有 VideoUnmask、ButtonUnmask 两个任务）；xhard0 16 任务 × 1 档 × 12 局 = 192；共 1262。新值格 43，xhard0 格 16。

## 2. 要改哪些文件

「阶段」列对应 §3 的实施步骤表。阶段 3b「换包」之前，包内规格一律是 v7、`hard_specs` 的档位结构与 `hard_builder` 不动，所以阶段 1、2 的闸门都在 v7 包上跑得通（第二部分 R10）。

### 2.1 数值与档位（`src/robomme_hard/`）

| 文件 | 改什么 | 阶段 |
|---|---|---|
| `robomme_env/PickXtimes.py` | `config_xhard1..3` 改 6／7／8，`config_xhard4` 改 9（不交付、不评估）；不加 xhard5；`XHARD_DECISION`（含圆盘区域）不动；注释改 v8 口径 | 1 |
| `robomme_env/SwingXtimes.py` | 四处：`config_xhard1..4` 改 4／5／6／7，新增 `config_xhard5` = 8；`configs` 末尾追加 `xhard5`（测试断言前四键顺序）；`NEWVALUE_DECISION` 加 xhard5（干扰 4）；`_native_decision` 的字面档元组加 `xhard5` | 1 |
| `robomme_env/StopCube.py` | `configs` 加 `xhard1`～`xhard5` 五份，`stop_time_range` 各 `{low: k, high_exclusive: k+1}`，k = 6／7／8／9／10，`move_interval_choices` 仍 `[60]`；`_native_decision` 暴露五个子键；`__init__` 去掉 `require_xhard4_only`；`_resolve_sampling_config` 里的 `NEWVALUE_DIFFICULTIES[-1]` 改字面 `"xhard4"` | 1 |
| `robomme_env/VideoUnmask.py`、`ButtonUnmask.py` | xhard1 的 decision `distractor.count` 0 → 4、`distractor.cube_count_range` [0, 0] → [2, 2]，`pick_count` 仍 2；xhard2～4 不动 | 1 |
| `robomme_env/RouteStick.py`、`PatternLock.py` | xhard1～3 的 `segment_count_range`／`path_length_range` 由定值改区间：RouteStick [8, 10]／[11, 13]／[14, 16]，PatternLock [9, 12]／[13, 15]／[16, 18]；xhard4 不动；`_native_decision`／`_resolve_sampling_config` 里的 `NEWVALUE_DIFFICULTIES[-1]` 改字面 `"xhard4"` | 1 |
| `robomme_env/utils/difficulty.py` | **`NEWVALUE_DIFFICULTIES` 保持 xhard1～4 不动**：`VideoRepick`、`VideoUnmaskSwap`、`ButtonUnmaskSwap` 把它当「每个任务都有的档」遍历，加进 xhard5 会让 VideoRepick 连原三档都初始化失败（`cls.configs["xhard5"]` 不存在）、让两个 Swap 任务凭空多出 xhard5 子树。新增 `XHARD5` 与 `ALL_NEWVALUE_TIERS = (*NEWVALUE_DIFFICULTIES, XHARD5)`，只用于 `VALID_DIFFICULTIES` 与 `newvalue_tier`／`is_newvalue_difficulty`；`require_xhard4_only` 只剩 InsertPeg、MoveCube 调用。原「没有 xhard5 配置的任务收到 xhard5 时明确报错」改为：builder 只按交付格表发档，并在 3b 加断言「(任务, 档) 必须在交付格表内」 | 1 |
| `robomme_env/utils/sampling_config.py` | `NEWVALUE_KEYS` 改由 `ALL_NEWVALUE_TIERS` 生成（否则 `_strip_xhard` 剥不掉 Swing／StopCube 的 xhard5 子树，`assert_native_decision` 报错）；`V6_ADDED_KEYS` 写死 `{"xhard1", "xhard2", "xhard3"}`（原 `NEWVALUE_DIFFICULTIES[:-1]`） | 1 |
| `robomme_env/utils/vqa_options.py` | 不改代码（`_options_stopcube` 只读 `steps_press`／`interval`，与档位无关）；`test_vqa_checkpoints_match_env` 的字面 XHARD 字典补上 stop_time 6～10 | 1 |
| 其余 9 个环境（BinFill、VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、VideoRepick、MoveCube、InsertPeg） | 不改；新增回归测试 `test_v8_native_blocks_unchanged`：这 9 个环境的 `native_blocks()` 与 v7 逐字节相同，7 个改值环境剥掉新值键后与 v7 逐字节相同、新值子树只在本表列出的键上不同，16 个环境全部可实例化 | 1 |
| `env_record_wrapper/hard_specs.py` | 阶段 1：删 `V6_SEED_OFFSETS` 的取值与 v6 profile（按档偏移机制保留）；新增冻结常量 `V7_TIERS`、`V7_XHARD4_ONLY = ("StopCube", "InsertPeg", "MoveCube")`，`load_specs_v7`、`_rollout` 的 v7 函数与 v7 夹具改用它们。阶段 2：新增 `V8_TIERS`（xhard1～5）、`V8_CELLS`（表 2 逐格局数）、`V8_EXEC_CAP = 1600`、`V8_SEED_OFFSETS` 与 profile `v8`、schema `hard-specs/4`、`load_specs_v8`（第二部分 §2.2）。阶段 3b：`TIERS`／`BUILDER_TIERS`／`EXPECTED_CELLS` 切到 v8，`XHARD4_ONLY = ("InsertPeg", "MoveCube")`，`TIER_MAX_STEPS` 改 `{xhard0: 1300, xhard1..5: 1600}` | 1／2／3b |
| `env_record_wrapper/hard_builder.py` | `_test_hard_entries` 去掉写死的 `!= 20`，按 `EXPECTED_CELLS` 查表并断言 (任务, 档) 在表内；按 `TIERS` 读 xhard1～5，xhard5 只含 SwingXtimes、StopCube | 3b |
| `env_metadata/test-hard/xhard{1..4}/specs.jsonl` | 整体替换为 v8 的 `hard-specs/4` 文件；v7 版本由已有标签 `parity-anchor-v7` 保存 | 3b |
| `env_metadata/test-hard/xhard5/specs.jsonl` | 新增，只含 SwingXtimes、StopCube 各 10 局 | 3b |
| `env_metadata/test-hard/layout_whitelist.json` | 不动：只服务 v7 派生链，该链在换包后只对合成夹具保持可用 | — |
| `README.md` | ①～④ 节同步五档、局数、上限 | 3b |

取值只改常量、不改抽样代码：PickXtimes／SwingXtimes 用 `torch.randint(number_range[0], number_range[1]+1)`，StopCube 用 `torch.randint(low, high_exclusive)`，RouteStick 用 `torch.randint(length_min, length_max+1)`，区间两端相等即定值；PatternLock 是随机路径的拒绝采样，改区间后只保证落在区间内（表 1）。但「加一档」不是只改常量：xhard5 只登记在全局合法档与 Swing／StopCube 自己的配置里，四处用 `[-1]`／`[:-1]` 指代「xhard4」的写法改成字面值，见上表。`tests/_shared/v7_tier_values.py::_point` 对 RouteStick、PatternLock 放行 [lo, hi]，其余严格单值。

### 2.2 抽签、生成、站点（`scripts/injection-dev/`）

| 文件 | 改什么 | 阶段 |
|---|---|---|
| `freeze_specs.py`、`_freeze.py` | 新增 profile `v8`（按档 seed 偏移）；每档一次冻结、档内逐任务独立抽，不交付的档不抽；CLI 增加 `--candidates-per-env TASK=N,...`、`--select TASK=a..b,...` 与逐任务 `--task-max-reset-attempts`；`freeze` 显式传 schema（现按「header 有无 `layout_rule`」推断，会把 independent 写成 /3 再被自己的校验拒掉）；`stratified_select` 加逐格配额、保留 MoveCube 运动方式分层；`--dry-run` 打印逐格候选数与 reset 上限 | 2 |
| `derive_specs.py` | **保留不调用**（用户拍板③）：v8 不派生；文件、`_check_layout_parent` 与白名单机制原样保留，换包后只对 v7 合成夹具可用 | — |
| `_rollout.py` | `h5_facts` 加 `exec_steps`（`timestep_*` 数 − `info/is_video_demo` 为真的帧数）；执行步 > 1600 记 `status=failed`、`error_type=exec_over_cap` 并保留步数，h5／mp4 按显式格目录删除，同格递补；复用已能逐格递补的单档 `run_continue`（`plan_pending` 接逐任务配额），另加聚合步写 `delivery.json` 并打印 `V8_DELIVERY_SET`；某格备用候选耗尽即 FAIL；`run_continue_v7` 与 `V7_*` 原样保留，只供 v7 夹具 | 2 |
| `generate_h5.py`（原漏列） | 按 header schema 分派：/4 走 `load_specs_v8` 与 v8 驱动，/3 走原 v7 路径；退出码判断改认 `V8_DELIVERY_SET=PASS`，与判定行改名同一提交（否则成功也返回 1）；replay 分支的规格路径按 `V8_TIERS` | 2 |
| `_report.py`（原漏列） | `delivery_per_cell` 按逐任务字典读 | 2 |
| `export_eval_identities.py` | v8 不评估新局：轮次／分片字段置空；1292／646 改为由表 2 推出（1262）；`V6_SECONDS` 改名 `TASK_SECONDS` | 2 |
| `site/v8_site.py`、`v8_site.html`、`v8_site_catalog.py`、`v8_site_browser_check.py` | 由 v7 四件复制（原写「三件」，检查器是第四件）：`v8_site.html` 的 DOM 结构、样式与 `v7_site.html` 逐一一致，只加 xhard5 列、改标题、去掉写死的 `PL_ACTUAL`；`v8_site_catalog.py` 的评估来源（`records_*`、`official_*`、`eval_videos*`、`tables`、`rerun11`）全部可缺省，每局评估显示「未评估」——这是独立状态，不算失败，任何成败筛选都不得命中；检查器删除或反转 v7 的评估断言（评估视频播放、翻转／重跑筛选、6 路同步），新增断言见 §3；1292 改 1262；xhard0 生成视频复用 `artifacts/newtask-v7/site-media/xhard0-gen`（0 次渲染）。`v7_*` 原样保留 | 4 |
| `site/v8_subgoal_lengths.py`、`v8_oracle_browser_check.py`（新增） | 由 v7 复制改写：配置、目标、逐段长度、步数上限一律从 v8 规格与真实 h5 取，不读评估记录（v7 版从 `eval.new.simplememvla.max_steps` 取上限，评估置空即报错），不读 0928 计划表格，去掉 PatternLock 定值断言；`subgoals.json` 缺失时检查器报错，不允许服务端返回空对象让页面静默缺内容 | 4 |
| `site/v6_site.py` | **改名 `site_server.py` 保留**：它是 v7／v8 站点的服务端（`create_server`、媒体白名单、Range、`/api/subgoals`），`v7_site.py`、`v7_subgoal_lengths.py` 的加载路径同步；内容不改 | 1 |
| `site/site_io.py` | 整个删除（唯一使用者 `v6_candidate_values.py` 及其测试随 V6 删除） | 1 |
| 抽签规模 | 逐任务候选表（第二部分 §2.2 第 6 条），替代原「每格 × 1.3」；抽签拒绝率只放大 reset 次数，单列进预算 | 2 |

### 2.3 对拍与守卫（`scripts/parity/`）

| 文件 | 改什么 | 阶段 |
|---|---|---|
| `hard_regression.py` | 新增只读子命令 `delivery-set --specs-root`：读 5 份 /4 文件，按表 2 做**相等**比较（`validate_specs` 只抛异常不打印，且只查上限），打印 `V8_DELIVERY_SET`、`V8_SEED_DISJOINT`、`V8_LAYOUT_INDEPENDENT`；新写 `tier-values`（不是从 `v6_tier_monotone.py --fixed` 迁入——那段绑死 13 任务、四档链与单调检查，也没有 StopCube 的读取分支）：定值任务逐档等于表 1，RouteStick／PatternLock 落在区间内并打印逐格长度直方图，StopCube 读 `stop_time`；`step-headroom` 改为「交付集最大执行步 ≤ 1600」，加 `--pool` 读超限过滤数，xhard0 按 1300 单独查；`reset-replay` 判定行改 `V8_RESET_REPLAY`；`eval-smoke` 的 92／32（原文误记在 reset-replay 名下，实际在 `cmd_eval_smoke`）改按任务查表；`xhard0-reset-parity` 不动；`xhard0-eval-parity` 比较器不动，只出 INFO；`layout-shared`／`prefix-geometry` 标为只适用 v7，v8 不跑 | 2 |
| `hard_parity.py` | tier 键 `v7` 改 `v8`：`TIERS`、`TIER_NAMES` 加 xhard5、`rows_for`、`cmd_generate`、`import-delivery` 选项、默认根改 `artifacts/newtask-v8/parity`；`SHAPES` 改逐格表（按档 411／411／128／100／20）；**`compare` 先核对分母**：冻结交付集 = `delivery.json` = H = H2，拒绝空集、重复、缺失、多余身份（现在 `compared=` 就是调用方给的清单行数，空清单时各项计数都是 0 = 0 也能过） | 2 |
| `train_split_config.py` | 删 `newtask-v6` release 条目；机器标签沿用 `newtask-v7`，其说明改为「v7 机制、v8 取值」并去掉对 V6 快照的引用 | 1 |
| `scripts/README.md` | 同步 | 3b |

### 2.4 测试（`tests/`）

清单由 `git grep -lE 'TIERS|XHARD4_ONLY|EXPECTED_CELLS|TIER_MAX_STEPS|seed_rule_for|SEED_PROFILES|NEWVALUE_DIFFICULTIES|SCHEMA_V7|V7_DELIVERY_SET|V6_FROZEN|load_specs_v7|run_continue_v7|delivery_per_cell|PACKAGED_SPECS_ROOT|require_xhard4_only|site_io|v6_site|v6_tier_monotone' -- tests` 生成（AUDIT_BASE `0978a082` 命中 21 个文件，其中 4 个随 V6 删除），再加按取值钉死的测试；阶段 1 开工前重跑该 grep，结果必须全部落在本表内。

| 文件 | 改什么 | 阶段 |
|---|---|---|
| `_shared/v7_tier_values.py` | `V7_TIER_VALUES` 三任务改档、StopCube 入表、RouteStick／PatternLock 改区间；`TIERS` 保持四档，另加逐任务支持档表（Swing、StopCube 含 xhard5）；`_point` 对两区间任务放行 [lo, hi] | 1 |
| `lightweight/test_v7_tier_values.py`（原漏列） | 逐任务支持档；VideoUnmask xhard1 干扰 0 → 4；`lo == hi` 断言对两区间任务放开；任务数 13 → 14 | 1 |
| `test_v4_xhard_pickxtimes.py`、`test_v4_xhard_swingxtimes.py`、`test_v5_xhard_pickswing.py` | 次数与档数同步；圆盘区域断言不动 | 1 |
| `test_v4_xhard_videounmask_buttonunmask.py`、`test_v5_xhard_videounmask_buttonunmask.py` | xhard1 干扰 0 → 4、干扰方块 0 → 2 | 1 |
| `test_v5_xhard_patternlock_routestick.py` | xhard1～3 改区间；`test_v6_pl_partial_snapshot_filled`、`test_v6_rs_partial_snapshot_filled_v4_not` 原样保留作回归 | 1 |
| `test_v4_xhard_stopcube.py` | 五档定值；「拒绝 xhard1～3」反转为「五档都接受、值正确」；`test_old_snapshot_without_xhard_gets_default` 原样保留作回归 | 1 |
| `test_v6_difficulty_tiers.py` | 改名 `test_v8_difficulty_tiers.py`；断言 `NEWVALUE_DIFFICULTIES` 仍四档、`ALL_NEWVALUE_TIERS` 五档；删 3 个 v6 seed 测试（原写 2 个：`test_v6_seed_rule_offsets_disjoint`、`test_draw_rows_carry_tier_and_rule`、`test_v7_seed_rule_disjoint_from_v5_v6`） | 1 |
| `test_hard_state_machine.py`（原漏列） | 模块顶层调用 `seed_rule_for(TIER, "v6")`，删 v6 profile 后收集即报错；改用 v7 规则 | 1 |
| `test_v6_audit_fix_scripts.py` | 改名去 `v6_` 前缀时，把 `seed_rule_for("xhard3", "v6")` 改为 v7 规则（原写「与 V6 无关」不准确） | 1 |
| `test_v7_seed_rule.py`（原漏列） | 阶段 1 删 v6 比较；阶段 2 把「v8 必须报错」改为「v8 按档偏移两两不交」 | 1／2 |
| `test_v7_freeze_schema.py` | 阶段 1 去掉 profile `v6` 用例；3b 读包内规格的两个用例改读合成夹具或删除 | 1／3b |
| `test_sampling_config_split.py` | 删 `test_v6_snapshot_matches_source`，`test_v7_snapshot_matches_source` 尾部的 V6 快照比较删掉（两处都读要删的 V6 快照）；快照换 v8 | 1 |
| `test_v7_whitelist_semantics.py`（原漏列） | 断言改用独立常量 `WHITELIST_TASKS`（13 个），不再由 `XHARD4_ONLY` 推出（StopCube 离开后会变 14，白名单 JSON 不动） | 1 |
| `_shared/v7_specs_fixture.py`、`test_v7_candidate_pool.py`（原漏列） | 改用 `V7_XHARD4_ONLY`；v7 判定行与 `run_continue_v7` 的断言不变 | 1 |
| `test_xhard0_native.py` | 阶段 2：`'v7' in H.TIERS` 改 `'v8'`；3b：`TIERS` 五档、`BUILDER_TIERS` 六项、`EXPECTED_CELLS` 43 格（原 55）、`TIER_MAX_STEPS` 六档字典 | 2／3b |
| `test_hard_builder_xhard0.py`（原漏列） | 逐任务局数 62／62／62／32／32／92（PickXtimes、SwingXtimes、StopCube 62；MoveCube、InsertPeg 32；其余 92），档集按交付格表 | 3b |
| 新增 v8 测试 | `load_specs_v8`；schema/4 改配额、`exec_cap` 或 seed 规则而不重签必失败；v8 按档 seed 不交；`delivery-set`／`tier-values`／`step-headroom --pool` 走「写 JSON → 读 JSON → 守卫」往返；所有计数键显式输出零值；`generate_h5` continue 模式在合成 v8 根上退出码 0 | 2 |
| 原样保留作回归 | `test_v4_xhard_binfill.py`、`test_TaskGoal_newvalue.py`、`test_v4_xhard_videorepick.py`、`test_v5_xhard_videorepick.py`（都遍历 `NEWVALUE_DIFFICULTIES`，该常量不扩档故无需改） | — |

### 2.5 删 V6

| 处置 | 内容 |
|---|---|
| 删 | `scripts/configs/newtask-v6/`；`scripts/injection-dev/site/v6_*` 中 7 个文件（候选值、长度表两件、`v6_site.html`、目录、v0 定义、检查器；**`v6_site.py` 不删，改名 `site_server.py`**，见 §2.2）；`site_io.py` 整个模块；`train_split_config.py` 的 `newtask-v6` 条目；`hard_specs.py` 的 v6 偏移取值与 v6 profile；`tests/lightweight/test_v6_candidate_values.py`、`test_v6_site_labels.py`、`test_v6_site_v11.py`、`test_v6_tier_monotone.py` |
| 迁移 | 调用 v6 seed 规则或读 V6 快照的测试先改再删 v6（§2.4：`test_hard_state_machine.py`、`test_v6_audit_fix_scripts.py`、`test_v7_seed_rule.py`、`test_v7_freeze_schema.py`、`test_v6_difficulty_tiers.py`、`test_sampling_config_split.py`），同一提交内完成 |
| 改名保留 | `test_v6_swap_uniform.py`、`test_v6_xhard_movecube_region.py`、`test_v6_audit_fix.py`、`test_v6_audit_fix_scripts.py`（测的是现行环境行为，不是 V6 对拍）；`V6_SECONDS` → `TASK_SECONDS` |
| 留（只读） | `docs/validation/newtask-v6/`、`docs/plans/0925-newtask-release-v6-plan.md` 留档；是否删由用户另说 |
| 不动 | `scripts/configs/newtask-v3/`、`newtask-v7/xhard0_manifest.json`、`hard-parity-tolerances.json`：xhard0 对拍与 V8 对拍仍用 |

逐文件清单与理由见第二部分 §2.1b。另：`AGENTS.md` 第 0 条判据表的当前分支名已在分支对齐中改为 `newtaskRelease-taskV8`（已执行）。

## 3. 验收

每条判定行都写全 k=v；产出者（文件::函数）见第二部分 §2.3。

| 查什么 | 怎么查 | 过了说明什么 | 判定行 | 阶段 |
|---|---|---|---|---|
| 官方源码不变 | `uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | `src/robomme` 与官方 `1fadc0ec` 逐字节相同、借用闭包干净 | `UPSTREAM_GUARD=PASS` | 1、3b |
| 录像器冻结 | `git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` | 录像器零改动 | 退出码 0 | 每阶段 |
| 四入口 | `ls -1 scripts/*.py` | P1 成立 | 恰好四个 | 每阶段 |
| 原三档与不改环境的决策不变 | Pick／Swing 的 `test_decision_visible_part_unchanged`、StopCube 的 `test_native_decision_visible_part_unchanged`、InsertPeg／MoveCube 的 `test_decision_visible_part_unchanged_and_guard`、新增 `test_v8_native_blocks_unchanged` | 剥掉新值键后与原值逐键相同；9 个不改的环境整份 `native_blocks()` 逐字节相同——xhard5 没有漏进原三档，也没有漏进不该有它的任务 | 核心短测无 failed | 1 |
| xhard0 环境层对拍 | `hard_regression.py xhard0-reset-parity --src-root <官方 1fadc0ec worktree>` | 官方与 hard 两侧 xhard0 192 局 reset 后**比较器已检查的演示前字段**逐位一致（不是整个 reset 后状态逐位一致），是「v8 没改坏 xhard0」的确定性证明 | `XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0` | 1、3b |
| xhard0 身份 | `hard_parity.py export-xhard0-manifest` | 192 个身份与官方元数据一致（R6 要求重跑的身份类闸门） | `XHARD0_IDENTITY=PASS shape=16x1x12 identities=192` | 1、3b |
| 最小冒烟 | 阶段 2b：7 种新格各 1 局走全链（§2.4.2） | 新档位、按档 seed、/4 封存、生成驱动、判定行全链能走通 | `generate_h5` 退出码 0，且 `delivery-set --cells smoke` 打印 `V8_DELIVERY_SET=PASS tasks=6 cells=7 total=7` | 2b |
| 交付形态 | `hard_regression.py delivery-set --specs-root <v8 根>` | 43 格逐格交付数与表 2 **相等**（不是「≤」） | `V8_DELIVERY_SET=PASS tasks=16 cells=43 total=1070` | 3 |
| seed 按档隔离 | 同上 | 同任务不同档的 seed 集合两两不交——布局独立的前提 | `V8_SEED_DISJOINT=PASS tasks=16 tier_pairs=<n> shared=0` | 3 |
| 布局独立 | 同上 | 5 份 header `mode == independent`、所有行 `layout_parent` 为 null，**并且**同任务跨档的位置类取值相同的对数为 0；只查前两项是同义反复（冻结器自己写的标志），必然通过 | `V8_LAYOUT_INDEPENDENT=PASS files=5 delivered=1070 parent_non_null=0 layout_equal_pairs=0` | 3 |
| 档位取值 | `hard_regression.py tier-values --specs-root <v8 根>` | 14 个有取值维度的任务逐格等于表 1，RouteStick／PatternLock 落在区间内；同时打印两区间任务的逐格长度直方图（PatternLock 比例不保证均匀，只报告） | `V8_TIER_VALUES=PASS tasks=14 cells=41 mismatches=0` | 3 |
| 步数上限 | `hard_regression.py step-headroom --delivery <delivery.json> --pool <候选池>` | 交付 h5 的非演示步全部 ≤ 1600；`filtered=` 是抽样阶段因超限被丢弃并递补的候选数；xhard0 按 1300 单独查 | `V8_STEP_CAP=PASS max=<实测> cap=1600 over=0 filtered=<n> xhard0_max=<实测> xhard0_cap=1300` | 3 |
| 回注回放 | `hard_regression.py reset-replay`（换包后读包内） | 43 格各 1 局按规格回注 reset，注入值与记录一致 | `V8_RESET_REPLAY=PASS shape=cells43 resets=43 replay=43 injected_mismatch=0 layout_drift=0 unused=0 layout_hit_bad=0 errors=0` | 3b |
| 评估入口 | `hard_regression.py eval-smoke`，xhard0 与 xhard5 各 1 局 | `evaluation_hard.py` 的 builder、按档步数上限、xhard5 档能走通 | `HARD_EVAL_SMOKE=PASS`（每局一行，带 task／episode／tier／seed） | 3b |
| 二次生成对拍 | `hard_parity.py compare --pair H:H2 --tier v8` | 先核对「冻结交付集 = `delivery.json` = H = H2」，再逐局比身份、成败、配置、schema 与容差；FAIL 时逐身份按 §2.2 第 11 条五个互斥终态计数并写入留档；按用户 2026-10-01 预定动作 (a)：交付永远以 gen1 为准、保留真实 FAIL，不换候选、不重试正常失败、不发起裁决提问，只有身份／来源／结构错误停受影响分支（§2.4.5） | `PARITY_H_H2=PASS tier=v8 compared=1070 cells=43 missing=0 extra=0 duplicate=0 identity_equal=1070 ...` | 4 |
| xhard0 评估 | `scripts/eval-official/orchestrate.py` 在评估席跑两条路线，再逐策略 `hard_regression.py xhard0-eval-parity` | **只报告，不是闸门**：策略层不可复现（v7 MME 同入口同卡重跑 11 局有 5 局翻转），参考 v7 值 SimpleMemVLA status_diff 0／steps_diff 16、MME 11／71 | `XHARD0_EVAL_PARITY=INFO policy=<名> compared=192 status_diff=<n> steps_diff=<n>`（每策略一行） | 3′ |
| 站点与 v7 布局一致 | `v8_site_browser_check.py --shots <目录>`（Playwright） | v7 页面的 15 个 DOM 区块都在（`sidebar`、`task-search`、`task-nav`、`status-panel`、`outlier-section`、`oracle-section`、`task-section`、`matrix`、`tier-tabs`、`filters`、`legend`、`rerun-panel`、`chips`、`episode`、`notes`）；评估位显示「未评估」、成败筛选零命中、无失败徽标、无评估媒体请求；逐段数据完整；配置面板数值与表 1 一致；xhard5 列与生成视频可播放；截图目视复核 | `V8_SITE=PASS sections=15 eval_placeholders=<n> eval_filter_hits=0 eval_media_requests=0 subgoal_missing=0 config_mismatch=0` | 4 |
| 各档总表页 | `v8_oracle_browser_check.py` | oracle 区的逐格专家步数统计与 v8 交付 h5 一致 | `V8_ORACLE_BROWSER=PASS cells=59 missing=0` | 4 |
| 核心短测 | `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q` | 未知回归 | 末行 `passed` 且无 failed | 每阶段 |
| V6 对拍 | **不跑**；V6 判定行、配置、站点随 §2.5 删除 | — | — | — |

过滤在抽样阶段按每个候选生成出来的真实 h5 判，交付集按构造 over=0。1600 的保证范围限于交付 h5 的非演示步（`timestep_*` 数 − `info/is_video_demo` 为真的帧数），不含策略外部动作数与底层 `env.step` 数。二次生成（H2）若因 RRT 噪声让个别局冒过 1600（v7 H:H2 的 1100 局里 13 局帧数最多差 116），只按 `PARITY_H_H2` 的噪声口径记录、不改交付；所以「重新生成也不超过 1600」不成立。

**实施步骤**（整份实施与 §2.12 分配表已于 2026-10-01 一次获批，按依赖顺序连续执行；运行中裁决按第二部分 §2.4.5 预定动作，不再发起授权提问）

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 拍板（已完成 2026-10-01：布局独立、PickXtimes 17／17／16、派生链保留不调用、只抽交付格、V6 留档保留；对抗验证后四项见引言 ⑧） | 已答复 |
| 0′ | P3 一次性预算表（第二部分 §2.4.3）获批 | 用户一次答复 |
| 1 | 第一部分 §2.1～§2.5 中「阶段 1」各行：环境常量与档位合法性、删 V6、测试迁移；`hard_specs` 档位结构与 `hard_builder` 不动 | 核心短测；`UPSTREAM_GUARD`；`XHARD0_RESET_PARITY`；`XHARD0_IDENTITY` |
| 2 | 「阶段 2」各行：schema/4、`load_specs_v8`、按档 seed、逐格配额、`exec_over_cap`、生成入口分派、`delivery-set`／`tier-values`／`step-headroom`、`hard_parity` 分母核对；包内 v7 规格照常加载 | 核心短测；新增 v8 夹具测试（写 JSON → 读 JSON → 守卫）；P4 六种夹具（第二部分 §2.4.4） |
| 2b | 最小冒烟：在一个生成席上单 worker 跑 7 种新格各 1 局（第二部分 §2.4.2） | 冒烟判定行；测速结果回填 §2.4.3 的耗时估计 |
| 3 | 43 格逐档冻结、逐任务独立抽签 → 生成，写到 `artifacts/newtask-v8/specs-root/`，闸门一律带 `--specs-root` | `V8_DELIVERY_SET`、`V8_SEED_DISJOINT`、`V8_LAYOUT_INDEPENDENT`、`V8_TIER_VALUES`、`V8_STEP_CAP` |
| 3′（阶段 1 之后即可，与 2、3 并行） | xhard0 评估：16 任务 × 1 档 × 12 局 × 2 策略 × 2 路线 = 768 局，在评估席上跑，代码为阶段 1 的提交（换包后由 `XHARD0_RESET_PARITY` 重证） | `XHARD0_EVAL_PARITY=INFO` × 2（只报告） |
| 3b 换包 | 一次提交：用 v8 的 /4 文件替换 `xhard1..4/specs.jsonl`、新增 `xhard5/specs.jsonl`，同时切 `TIERS`／`BUILDER_TIERS`／`XHARD4_ONLY`／`EXPECTED_CELLS`／`TIER_MAX_STEPS`／`hard_builder` 与读包内规格的测试 | 核心短测；`V8_RESET_REPLAY`；`XHARD0_RESET_PARITY`；`XHARD0_IDENTITY`；`HARD_EVAL_SMOKE`（xhard0、xhard5 各 1 局）；`UPSTREAM_GUARD` |
| 4 | 二次生成对拍；生成完成后自动建站（评估板块置空）、浏览器检查并推送通知 | `PARITY_H_H2`；`V8_SITE`；`V8_ORACLE_BROWSER` |

## 4. 子代理分工与合并（简述）

按正本 `CLAUDE.md`「计划执行模式」执行：改代码的活拆给在各自 git worktree 副本里干活的子代理，主会话不亲自改代码，只负责派发、审查、合并、跑 GPU 闸门和生成。

**怎么拆。** 阶段 1 拆两块、顺序派发：S1-A 管 7 个改值环境的常量与档位合法性（`difficulty.py`、`sampling_config.py`）以及钉这些值的测试；S1-B 在 S1-A 合入后派出，管删 V6、v6 seed 迁移、`hard_specs.py` 的阶段 1 部分（`V7_TIERS`、`V7_XHARD4_ONLY`）、`site_server` 改名，以及 MoveCube 测试改名后的旧导入与 V7 合成回归里「四档结果对五档枚举」的比较修正（它们要用到 S1-A 的五档枚举，所以不能并行）。阶段 2 先一块后两块：S2-A 先做 `hard_specs.py` 的 v8 常量、schema/4 与 `load_specs_v8`（其余两块都要 import 它，所以必须先合入）；然后 S2-B（抽签、生成驱动、`generate_h5` 分派、identities）与 S2-C（`hard_regression` 三个子命令、`hard_parity` 的 v8 键与分母核对）并行，站点六件 S4-A 紧接着合入——自动建站要调用它，所以必须在正式生成之前就位；S2-D（P4 接续脚本、独立 watchdog 与六种夹具）在 S4-A 之后派出，用真实站点入口做合成目录接续测试。阶段 3b「换包」按 R10 必须一个提交完成，所以只派一个子代理 S3b。阶段 2b 冒烟、3 生成、3′ 评估、4 二次生成与真实站点检查都是跑任务不是改代码，主会话自己用 tmux + Monitor 跑。

**每块管哪些文件。** 逐块的可写文件集合、禁触路径、接口契约见第二部分 §2.12；几个会被多块碰到的文件按阶段只有一个 owner：`hard_specs.py` 阶段 1 归 S1-B、阶段 2 归 S2-A、阶段 3b 归 S3b；`test_xhard0_native.py` 阶段 2 归 S2-A、3b 归 S3b；`test_v7_seed_rule.py` 阶段 1 归 S1-B、阶段 2 归 S2-A；`test_v6_difficulty_tiers.py` 整个归 S1-A（改名、四档与五档断言、删 3 个 v6 seed 测试一并做），S1-B 禁触——合法档位全集的断言必须随扩档一起改，不靠新建另一份测试掩盖旧断言；`test_xhard0_native.py` 阶段 2 那条 `'v8' in H.TIERS` 归 S2-C（`H` 是 `hard_parity`）。

**怎么合回来。** 每块合入前先过第一道审查：主会话核对主检出没被污染、改动文件没超出该块的可写集合、在它的 worktree 里把该块的 CPU 定向测试复跑一遍；再派一个只读审查子代理，锁定起止两个 sha 审 diff，拿到 `PRE_MERGE_REVIEW=PASS`。然后主会话 `git merge --no-ff <sha>` 合入，合并提交按 12.x 编号、body 按第 11 条写。合入后第二道审查由主会话做：核心短测全量 + `UPSTREAM_GUARD` + 录像器零 diff + 四入口，`POST_MERGE_REVIEW=PASS` 才 push、才合下一块。合并顺序：S1-A → S1-B →（阶段 1 GPU 闸门 `XHARD0_RESET_PARITY`／`XHARD0_IDENTITY` 由主会话跑）→ S2-A → S2-B → S2-C → S4-A → S2-D →（2b 冒烟、阶段 3 生成；gen1 验收通过即建站，3′ 评估与阶段 4 H2 独立跑）→ S3b →（3b 的 GPU 闸门）。审查 FAIL 的块发回原子代理续改，最多两轮；两轮仍 FAIL 则保留该分支不合入、停止依赖它的块，收尾统一报告（§2.4.5）；两块文本冲突先判越界。

**worktree 里怎么跑测试。** 按本仓库 `CLAUDE.md`「项目专属补充」：`UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <定向测试> -q`，先确认 `robomme_hard.__file__` 指向 worktree；worktree 里没有 `artifacts/`、没有子模块，所以需要 GPU、仿真或真实产物的闸门（`XHARD0_*`、`V8_RESET_REPLAY`、`HARD_EVAL_SMOKE`、`V8_SITE`、`V8_ORACLE_BROWSER`）一律留给合并后主会话在主检出跑。

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

- **R1**：`src/robomme/**` 是官方 `1fadc0ec` 原样，不改（P2）。本方案的改动全部在 `src/robomme_hard/` 与 `scripts/`、`tests/`。
- **R2**：xhard0 与原三档的 decision 不变；以 `assert_native_decision`、`test_v8_native_blocks_unchanged` 和 `UPSTREAM_GUARD=PASS` 为准。
- **R3**：录像器 `RecordWrapper.py` 冻结，零 diff（`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`）。
- **R4**：正式抽签和生成属于大规模 reset／rollout。全部阶段（含阶段 1 的 xhard0 对拍、冒烟、二次生成、xhard0 评估）的 reset 与 rollout 按 §2.4.3 一张表、按 P5 写乘式，在阶段 1 开跑前一次批完；批准前不启动任何一项。本轮「本机随便跑」的授权**只覆盖探针**，不延伸到正式生成。
- **R5**：`scripts/` 顶层仍然恰好四个入口（P1）。新脚本放进 `scripts/injection-dev/` 或 `scripts/parity/`。
- **R6**：`identity_sha256`／`delivery_sha256` 的覆盖范围一旦改变，要升 `schema`（`hard-specs/4`，§2.2 第 2 条），并重跑身份类闸门（`src/robomme_hard/README.md` ⑥ R3）：本方案点名的是 `XHARD0_IDENTITY`（阶段 1 与 3b 各一次）和 schema/4 篡改测试（改配额、`exec_cap` 或 seed 规则而不重签必失败）。
- **R7**：对拍只在 A40@greatlakes 上生成（R11）。本轮 Ada 上的探针数字只用于定配置，不进 `PARITY_H_H2`。
- **R8**：xhard5 只登记在 `ALL_NEWVALUE_TIERS`（全局合法档）与 SwingXtimes、StopCube 自己的配置里；`NEWVALUE_DIFFICULTIES` 保持四档；官方 `src/robomme`、xhard0、原三档与其余 14 个任务不感知该档（`assert_native_decision` 剥掉 `xhard5` 子键后仍逐键相同，9 个不改环境的 `native_blocks()` 逐字节不变）。
- **R9**：布局独立靠按档 seed 偏移（§2.2 第 3 条）构造，并由 `V8_SEED_DISJOINT` 与 `V8_LAYOUT_INDEPENDENT` 的数据检查验证，不靠冻结器自己写的标志位。
- **R10**：阶段 3b「换包」之前，包内 `env_metadata/test-hard/` 一律是 v7 规格，`hard_specs` 的 `TIERS`／`BUILDER_TIERS`／`EXPECTED_CELLS`／`TIER_MAX_STEPS` 与 `hard_builder` 不动；v8 规格只放 `artifacts/newtask-v8/specs-root/`，相关闸门一律带 `--specs-root` 或 `ROBOMME_HARD_SPECS_ROOT`。换包在一个提交里同时替换数据与切换常量；换包后 v8 代码不再加载 v7 包，v7 规格靠已有标签 `parity-anchor-v7` 复现。
- **R11**：7 个占位 job（清单 `hold-jobs-v8gen-20261001.txt`）在全部任务结束后按清单逐个 `scancel`；在那之前不释放（用户 2026-10-01「你任务全部结束后释放 现在别管」）。

## 2.1 逐文件改动清单（配置值）

阶段划分以第一部分 §2.1～§2.5 的「阶段」列为准；本表补锚点与现值、新值。

| 文件 | 锚点 | 现值 | 新值 | 方案 |
|---|---|---|---|---|
| `src/robomme_hard/robomme_env/PickXtimes.py` | `PickXtimes.config_xhard1..4` 的 `number_min`／`number_max` | 7／10／12／15 | 6／7／8／9（xhard4 不交付、不评估）；不加 xhard5；`XHARD_DECISION` 不动 | 都改 |
| 同上 | 注释「V7 定值（0928 方案 §3.2.2）」 | — | 改写为 v8 口径 | 都改 |
| `src/robomme_hard/robomme_env/SwingXtimes.py` | `config_xhard1..4`、新增 `config_xhard5`；`configs`（末尾追加 xhard5）；`NEWVALUE_DECISION`（加 xhard5，干扰 4）；`_native_decision` 的字面档元组 | 5／7／9／11；元组 `("xhard1","xhard2","xhard3")` 加字面 xhard4 | 4／5／6／7／8；元组加 `xhard5` | 都改 |
| `src/robomme_hard/robomme_env/StopCube.py` | `_CONFIG_XHARD` 拆为 `configs["xhard1".."xhard5"]`；`_native_decision` 五个子键；`__init__` 的 `require_xhard4_only`；`_resolve_sampling_config` 的 `NEWVALUE_DIFFICULTIES[-1]` | 仅 xhard4，`stop_time_range` `{low:6, high_exclusive:16}`；`[-1]` 指 xhard4 | xhard1～5 各 `{low:k, high_exclusive:k+1}`，k = 6／7／8／9／10；`move_interval_choices` 仍 `[60]`；`[-1]` 改字面 `"xhard4"` | 都改 |
| `src/robomme_hard/robomme_env/utils/vqa_options.py` | `_options_stopcube` | 只读 `steps_press`／`interval`，与档位无关 | 不改；`test_vqa_checkpoints_match_env` 的字面 XHARD 字典补 stop_time 6～10 | 不改 |
| `src/robomme_hard/robomme_env/VideoUnmask.py`、`ButtonUnmask.py` | xhard1 decision 的 `distractor.count`、`distractor.cube_count_range` | 0、[0, 0] | 4、[2, 2]（`pick_count` 仍 2） | 都改 |
| `src/robomme_hard/robomme_env/RouteStick.py`、`PatternLock.py` | xhard1～3 的 `segment_count_range`／`path_length_range`；`_native_decision` 推导式的 `d != NEWVALUE_DIFFICULTIES[-1]` 与 `_resolve_sampling_config` 的 `NEWVALUE_DIFFICULTIES[-1] in decision` | 定值 10／13／16、12／15／18；`[-1]` 指 xhard4 | 区间 [8,10]／[11,13]／[14,16]、[9,12]／[13,15]／[16,18]；`[-1]` 改字面 `"xhard4"` | 都改 |
| `src/robomme_hard/robomme_env/utils/difficulty.py` | `NEWVALUE_DIFFICULTIES`、`VALID_DIFFICULTIES`、`_NEWVALUE_TIER`、`require_xhard4_only` 的文案 | xhard1～4 | `NEWVALUE_DIFFICULTIES` 不动；新增 `XHARD5`、`ALL_NEWVALUE_TIERS`，`VALID_DIFFICULTIES` 与 `_NEWVALUE_TIER` 改由它生成；闸门只剩 InsertPeg、MoveCube 调用 | 都改 |
| `src/robomme_hard/robomme_env/utils/sampling_config.py` | `NEWVALUE_KEYS`、`V6_ADDED_KEYS` | 由 `NEWVALUE_DIFFICULTIES` 生成；`[:-1]` | `NEWVALUE_KEYS` 由 `ALL_NEWVALUE_TIERS` 生成；`V6_ADDED_KEYS` 写死 `{"xhard1","xhard2","xhard3"}` | 都改 |
| `utils/task_goal.py`、`utils/xhard_home_site.py`、`VideoPlaceButton.py`、`VideoPlaceOrder.py` 里的字面四档元组 | — | `("xhard1",…,"xhard4")` | 不改：这些分支只服务没有 xhard5 的任务 | 不改 |
| `src/robomme_hard/env_record_wrapper/hard_specs.py` | 阶段 1：`V6_SEED_OFFSETS`、`SEED_PROFILES`、`seed_rule_for` 的 v6 分支；新增 `V7_TIERS`、`V7_XHARD4_ONLY` | v6 偏移 6e6～12e6 | 删 v6 取值；`load_specs_v7`、v7 夹具改用 `V7_*` | 都改 |
| 同上 | 阶段 2：新增 `V8_TIERS`、`V8_CELLS`、`V8_EXEC_CAP`、`V8_SEED_OFFSETS`、profile `v8`、`SCHEMA_V8 = "hard-specs/4"`、`IDENTITY_KEYS_BY_SCHEMA["hard-specs/4"]`、`validate_specs` 的 /4 分支、`load_specs_v8` | 无 | 见 §2.2 第 2～4 条 | 新增 |
| 同上 | 阶段 3b：`TIERS`、`BUILDER_TIERS`、`XHARD4_ONLY`、`EXPECTED_CELLS`、`TIER_MAX_STEPS` | 四档；`XHARD4_ONLY` 含 StopCube；55 格；1300／1500／2400／2900／3800 | 五档；`("InsertPeg", "MoveCube")`；43 格逐格表；1300／1600 × 5 | 都改 |
| `src/robomme_hard/env_record_wrapper/hard_builder.py` | `_test_hard_entries` 的 `!= 20` 与档循环 | 写死 20、按四档读 | 按 `EXPECTED_CELLS` 查表、断言 (任务, 档) 在表内、按五档读（3b） | 都改 |
| `src/robomme_hard/env_metadata/test-hard/xhard{1..4}/specs.jsonl` | 整个文件 | v7，`hard-specs/3`、每格 20、`layout_rule.mode = shared` | v8 `hard-specs/4`（3b 替换） | 都改 |
| `src/robomme_hard/env_metadata/test-hard/xhard5/specs.jsonl` | 新文件 | 无 | 只含 SwingXtimes、StopCube 各 10 局（3b 新增） | 新增 |
| `src/robomme_hard/env_metadata/test-hard/layout_whitelist.json` | 整个文件 | v7 派生白名单（13 任务） | 不动 | — |
| `scripts/injection-dev/freeze_specs.py`、`_freeze.py` | 「v7 只在 xhard4 抽」拦截、`layout_rule` 组装、schema 推断、`--candidates-per-env`／`--select`（全局单值）、`stratified_select` | 母布局固定 xhard4、四档共用候选、按有无 `layout_rule` 推断 /3 | profile `v8`、逐任务候选数与选取区间、显式传 schema、逐格配额（保留 MoveCube 运动方式分层） | 都改 |
| `scripts/injection-dev/_rollout.py` | `h5_facts`、`run_batch`／`apply_results`、`run_continue`／`plan_pending`、新增聚合步 | 只按生成失败递补；`frames` 含演示帧；v7 走 `run_continue_v7` | `exec_steps`、`exec_over_cap`、逐任务配额、聚合写 `delivery.json` 与 `V8_DELIVERY_SET`；`run_continue_v7` 保留供 v7 夹具 | 都改 |
| `scripts/injection-dev/generate_h5.py` | continue／replay 两个分支、退出码判断 | 只走 `load_specs_v7`／`run_continue_v7`，认 `V7_DELIVERY_SET=PASS` | 按 schema 分派；认 `V8_DELIVERY_SET=PASS`；replay 按 `V8_TIERS` | 都改 |
| `scripts/injection-dev/_report.py` | `build_report` 的 `int(header["delivery_per_cell"])` | 整数 | 逐任务字典 | 都改 |
| `scripts/evaluation_hard.py` | `TIER_MAX_STEPS[tier]` | 读包内常量 | 不改（P1「只差 4 处」照旧；3b 后自动拿到 1600 与 xhard5） | — |
| `scripts/injection-dev/site/v6_tier_monotone.py` | 整个文件 | V6 检查器 + V7 定值检查 `--fixed` | 删除；`hard_regression.py tier-values` 新写（不迁移，§2.3） | 删 |
| `scripts/parity/hard_regression.py` | 新增 `delivery-set`、`tier-values`；`cmd_step_headroom`、`cmd_reset_replay` 判定行名、`cmd_eval_smoke` 的 `expected` | 90% + B4 ×1.25；`V7_*`；`32 if task in XHARD4_ONLY else 92` | 「交付集最大 ≤ 1600」加 `--pool`；`V8_*`；按任务查表 62／62／62／32／32／92 | 都改 |
| `scripts/parity/hard_parity.py` | `TIERS`、`TIER_NAMES`、`SHAPES`、`rows_for`／`v7_rows`、`cmd_generate`、`cmd_import_delivery`、`cmd_compare`、默认根 | tier 键 `v7`；分母取自调用方清单 | tier 键 `v8`；`compare` 先核对四方集合相等 | 都改 |
| `scripts/injection-dev/site/v8_site.py`、`v8_site.html`、`v8_site_catalog.py`、`v8_site_browser_check.py`、`v8_subgoal_lengths.py`、`v8_oracle_browser_check.py` | 自 v7 六件复制改写 | 无 | 见第一部分 §2.2；判定行 `V8_SITE`、`V8_ORACLE_BROWSER` | 新增 |
| `scripts/injection-dev/site/v6_site.py` | 整个文件 | v6／v7 站点共用服务端 | 改名 `site_server.py`，内容不改；`v7_site.py`、`v7_subgoal_lengths.py` 的引用同步 | 改名 |
| 测试 | 见第一部分 §2.4 逐文件表 | — | — | 都改 |
| `scripts/README.md`、`src/robomme_hard/README.md` | 第 1、3、4 节；② | v7 定值与上限 | 同步 | 都改 |

## 2.1b V6 删除清单（用户：「V6 的可以全部删除」）

| 处置 | 文件 | 说明 |
|---|---|---|
| 删 | `scripts/configs/newtask-v6/v6-sampling-frozen.json` | V6 定值快照；读它的两处测试先改（`test_sampling_config_split.py`） |
| 删 | `scripts/injection-dev/site/v6_candidate_values.py`、`v6_gt_lengths.py`、`v6_gt_lengths.json`、`v6_site.html`、`v6_site_catalog.py`、`v6_v0_native_definitions.py`、`v6_tier_monotone.py` | V6 站点页面、V6 长度表、V6 候选值与单调性检查器；`git grep` 核实：这 7 个文件只被 v6 测试与彼此引用（`scripts/README.md` 只有文字提及）。`site_server.py` 的 `/api/gtlen` 路由读 `v6_gt_lengths.json`，文件缺失时返回空表、页面照常 |
| 改名保留 | `scripts/injection-dev/site/v6_site.py` → `site_server.py` | `v7_site.py` 用 `importlib` 加载它的 `create_server`，`v7_subgoal_lengths.py` 依赖它的 `/api/subgoals` 路由；删掉 v7／v8 站点就起不来。改名后 `v7_site.py`、`v8_site.py` 的加载路径同步 |
| 删 | `scripts/injection-dev/site/site_io.py`（整个模块）；`scripts/parity/train_split_config.py` 的 `newtask-v6` release 条目 | `site_io.py` 唯一的使用者是 `v6_candidate_values.py` 及其测试，删后整个模块无人引用 |
| 删 | `hard_specs.py::V6_SEED_OFFSETS` 的取值、`SEED_PROFILES` 的 `"v6"`、`seed_rule_for` 的 v6 分支 | 按档偏移的机制保留给 v8（§2.2 第 3 条）；v7 单 offset 规则保留。先迁移 5 个调用 v6 规则的测试（第一部分 §2.5「迁移」行），同一提交内完成 |
| 删 | `tests/lightweight/test_v6_candidate_values.py`、`test_v6_site_labels.py`、`test_v6_site_v11.py`、`test_v6_tier_monotone.py` | 只测被删的 V6 站点／检查器 |
| 改名保留 | `test_v6_difficulty_tiers.py` → `test_v8_difficulty_tiers.py`（`NEWVALUE_DIFFICULTIES` 四档、`ALL_NEWVALUE_TIERS` 五档；删 3 个 v6 seed 测试）；`test_v6_swap_uniform.py`、`test_v6_xhard_movecube_region.py`、`test_v6_audit_fix.py`、`test_v6_audit_fix_scripts.py` 去掉 `v6_` 前缀（后者的 v6 seed 调用改 v7） | 测的是现行环境行为（交换均匀化、MoveCube 区域、审查修复后的语义），与 V6 对拍无关；删了就丢覆盖。用户要求「全部删除」时按删处理 |
| 改名保留 | `scripts/injection-dev/export_eval_identities.py::V6_SECONDS` → `TASK_SECONDS` | 是 v6 评估实测的每任务单局用时，用于分片均衡，不是对拍 |
| 留（只读） | `docs/validation/newtask-v6/`、`docs/plans/0925-newtask-release-v6-plan.md` | 留档，git 可取回；是否删由用户另说 |
| 不动 | `scripts/configs/newtask-v3/`、`newtask-v7/xhard0_manifest.json`、`hard-parity-tolerances.json` | V3 官方 train 元数据、xhard0 清单、V7 对拍容差，xhard0 对拍与 V8 对拍仍用 |

另：`AGENTS.md` 第 0 条判据表「仓库根」一栏的当前分支名已在分支对齐中由 `newtaskRelease-v5` 改为 `newtaskRelease-taskV8`（标记块外，已执行）。

## 2.2 交付形态改动（合作者的表要求的，不属于数值配置）

**现行假设**：
- 全局只有一个 `--select 0..19` 和一个 `delivery_per_cell=20`。
- 55 格表 `EXPECTED_CELLS` = `XHARD4_ONLY` 推出来的格子。
- 四档必须交付同一组 20 个候选，seed 规则四档同一 offset（同候选同 seed）。
- builder 里写死 `!= 20`；`load_specs_v7`、`run_continue_v7`、`generate_h5.py` 只认 /3 与 xhard4 母布局。

**要改的地方**：
1. **阶段与包内规格（R10）**：阶段 2 新增的 v8 常量与 /4 分支与 v7 并存；3b 一次提交里替换包内规格，并切 `TIERS`／`BUILDER_TIERS`／`XHARD4_ONLY`／`EXPECTED_CELLS`／`TIER_MAX_STEPS` 与 `hard_builder`。`EXPECTED_CELLS` 换成 43 格逐格表 `{(task, tier): count}`（取值即第一部分表 2）；`hard_builder._test_hard_entries` 去掉 `!= 20` 改查表；xhard0 的 `_xhard0_entries`、`XHARD0_PER_TASK` 不动。
2. **schema `hard-specs/4`**：
   - 签（进 `identity_sha256`）：header 键 = /3 的键（含 `layout_rule`）+ `exec_cap` + `delivery_per_cell`；行键 = /3 的键（含 `layout_parent`）。
   - `select_rule` 改 `{task: [indices]}`、`per_env` 改 `{task: 候选数}`、`delivery_per_cell` 改 `{task: n}`。
   - `layout_rule = {"mode": "independent"}`，所有行 `layout_parent = null`、`spec_kind = native-newvalue/2`；`seed_rule` 必须等于 `seed_rule_for(tier, "v8")`；`exec_cap` 必须等于 `V8_EXEC_CAP`（1600）。
   - `validate_specs` 新增 /4 分支检查上述各项与「逐任务 selected ≤ 配额」；/2、/3 分支逐字不动。
   - `_freeze.freeze` 显式接收 schema 参数（现按 header 有无 `layout_rule` 推断，会把 independent 写成 /3 再被自己拒掉）。
   - 篡改测试：改配额、`exec_cap` 或 seed 规则而不重签，`validate_specs` 必须拒绝。
3. **按档 seed（R9）**：`V8_SEED_OFFSETS = {"xhard1": 16_000_000, "xhard2": 18_000_000, "xhard3": 20_000_000, "xhard4": 22_000_000, "xhard5": 24_000_000}`；公式不变（`offset + env_code × 100000 + episode × 100 + attempt`），每档用到的最大增量 16 × 100000 + 999 × 100 + 99 < 1.7e6，小于步长 2e6，所以各档互不重叠，也不碰 v5（4e6 起）、v6 旧段（6e6～13.7e6）、v7 与探针（14e6～15.7e6）。`seed_rule_for(tier, "v8")` 返回本档规则；`SEED_PROFILES` 加 `"v8"`，`_known_seed_rule` 随之接受（`train_split_runner.py` 用它校验 job 的 seed 规则）。「四档同一 offset、同候选同 seed」只保留给 v7。
4. **加载器**：新增 `load_specs_v8(root)`：读 `V8_TIERS` 五份；每份走 /4 校验；每份的任务集合等于该档的交付格；跨文件检查同任务跨档 seed 不交。`load_specs_v7` 改按 `V7_TIERS` 读，只服务 /3（v7 合成夹具）。
5. **抽签**：每档一次 `freeze_specs.py --tier <档> --seed-profile v8`，档内逐任务独立抽（`_draw.draw_task` 本来就是逐任务循环）；逐任务候选数、选取区间与 `max_reset_attempts` 用新 CLI 给出；只抽交付格；`stratified_select` 保留 MoveCube 运动方式分层。
6. **候选表**（替代「每格 × 1.3」：InsertPeg 只给 26 个候选时，按 37.5% 失败率期望只能交付 16.3 局）。每格候选数 = ⌈局数 ÷ (1 − 生成失败率)⌉ + 余量：

   | 任务 | 每格局数 | 每格候选数 | 依据 |
   |---|---|---|---|
   | InsertPeg | 20 | 40 | v7 生成失败 37.5%（32 次试 12 次失败），期望交付 25 |
   | MoveCube | 20 | 32 | 失败 20%，期望交付 25.6 |
   | BinFill | 40／40 | 57／57 | 失败 15～21%，期望交付 ≥ 45 |
   | PickXtimes | 17／17／16 | 22／22／21 | 生成失败 ≤ 5%，加 8 次（xhard3）超限过滤，比例未知 |
   | SwingXtimes、StopCube | 每档 10 | 13 | 失败约 7% |
   | VideoUnmask、ButtonUnmask | 每档 20 | 26 | 失败 0～5%，× 1.3 |
   | VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、VideoRepick | 每档 40 | 52 | × 1.3 |
   | RouteStick、PatternLock | 27／27／26 | 36／36／34 | × 1.3 |

   候选合计 1 任务 × (22 + 22 + 21) + 2 任务 × 5 档 × 13 + 2 任务 × 4 档 × 26 + 1 任务 × 2 档 × 57 + 6 任务 × 2 档 × 52 + 2 任务 × (36 + 36 + 34) + 1 任务 × 1 档 × 32 + 1 任务 × 1 档 × 40 = 65 + 130 + 208 + 114 + 624 + 212 + 32 + 40 = 1425。抽签拒绝率只放大 reset 次数（§2.4.3），不改候选数。每格递补上限 = 该格候选数 − 局数（共 1425 − 1070 = 355）；某格备用候选耗尽即该格 `V8_DELIVERY_SET=FAIL`，不静默。
7. **生成驱动与超限过滤**：
   - `_rollout.h5_facts` 增加 `exec_steps`（`timestep_*` 数 − `info/is_video_demo` 为真的帧数；现有 `frames` 含演示帧），写进行的 rollout 结果段（不进签）。
   - 执行步 > `V8_EXEC_CAP` 的局在 `apply_results` 里记 `status=failed`、`error_type=exec_over_cap`、保留 `exec_steps`，`selected=false`、`tried=true`，触发同格递补；其 h5／mp4 按显式格目录删除，不跨运行 glob。
   - 驱动复用单档 `run_continue`（已逐格递补，`plan_pending` 改接逐任务配额），五档各一个规格文件；聚合步读五份结果写 `delivery.json`（schema `v8-delivery/1`，所有计数键显式写零：`exec_over_cap`、`backfills`、`infra_retries`、`failed`），并打印 `V8_DELIVERY_SET`。
   - `generate_h5.py` 按 header schema 分派，退出码认 `V8_DELIVERY_SET=PASS`。
   - 4 个生成席分片：`run_continue_v7` 是目录锁单写者，一个驱动只能占一个席位；v8 每片各自的 `--output`、候选池与锁，按任务切片（每片只写自己那几格），每席 4 worker，全部片完成后确定性合并进五份规格。
8. **不派生**（用户拍板①③④）：`derive_specs.py`、`_check_layout_parent`、`layout_whitelist.json` 原样保留，v8 一律不调用，换包后只对 v7 合成夹具可用（原文「供 v7 规格继续通过」不成立：换包后包内已无 v7 规格）；不交付的档不抽、不生成。各档布局互相独立，低档不照抄高档前缀。
9. **下游写死的数**：PickXtimes／SwingXtimes／StopCube 各 62（含 xhard0），MoveCube／InsertPeg 32，其余 92；全集 1070（含 xhard0 1262）。
   - `hard_parity.py::SHAPES` 改逐格表（按档 411／411／128／100／20），tier 键改 `v8`。
   - `hard_regression.py::cmd_eval_smoke` 的 `expected` 改按任务查表；`cmd_reset_replay` 在非 55 格时已打印 `shape=cells{N}`，只改判定行名；`delivery_index` 按 `V8_TIERS` 读。
   - `export_eval_identities.py`（1292、646）：轮次／分片字段置空，总数由表 2 推出 1262；`v8_site_catalog.py` 校验 1262，身份文件名 `eval-identities-1262.jsonl`；`eval_video_mover.py` 帮助文字里的 1292 同步。
10. **每格局数取整**：
    - PickXtimes 50 ÷ 3，取 17／17／16（用户拍板②「全部都是 50 局来分配」）；SwingXtimes／StopCube 50 ÷ 5 = 10，整除。
    - VideoUnmask／ButtonUnmask：四档各 20，不需要取整。
    - RouteStick／PatternLock：80 ÷ 3，取 27／27／26。
    - 取整按「低档多一局」，已按「取整等细节自己定」的长期指示决定。
11. **gen1 与二次生成的区别，以及两者结果不同时怎么处理**（用户 2026-10-01 问「这些之前生成过程中有不同吗 如果不同是怎么处理的」，§2.8 第 26 条）：
    - **两者做的事不同，所以局数不同**：gen1 是「抽候选 → 逐个生成 → 失败就从同格备用候选递补，直到每格凑够配额」，上限 1425 = 首轮 1070 + 备用 355；二次生成只把 gen1 已交付的 1070 个身份（同规格、同 seed）各重放一次，不递补，所以恰好 1070。交付数据集永远是 gen1；二次生成只用来对拍「同一份规格再生成一次是否得到同样的数据」，不替换交付。
    - **v7 实测（`docs/validation/newtask-v7/README.md` ③⑤）**：gen1 首跑 `attempted=1130 delivered=1098 sync_dropped=27 backfills=25`，InsertPeg 12 个候选生成失败、递补上限用尽，只交付 18/20，`V7_DELIVERY_SET=FAIL`；追加抽 60 个 InsertPeg 候选（60 次 reset）、手动补位 2 局后交付 1100，超出每格递补上限的部分由用户事后追认（2026-09-29「3同意递补」）。二次生成在另一个占位 job 上重放 1100 局（2 小时 45 分），结果：1086 局逐字节相同；13 局 sha 不同，但身份、setup、结构、成败全相同，首个分叉步 ≥ 118，按噪声口径记录（1.2%，在 5% 硬线内）；1 局 `xhard4/InsertPeg/8` 二次生成在规划阶段失败（gen1 同身份成功 505 帧），使 `PARITY_H_H2=FAIL`。没有改判据，交用户在「(a) 认定偶发、交付集不动」与「(b) 换备用候选重生成并重评」之间裁决；用户 2026-09-29 裁决「1暂时不管」——交付集保持 gen1 不动，H2 副本保留，FAIL 不阻塞打 `parity-anchor-v7`。
    - **v8 的处置口径（预先写定，不现场放宽）**：
      - 逐身份分成**五个互斥终态**并在判定行与留档里分别计数（每个身份恰好落一类，合计等于 1070）：①逐字节相同；②噪声（身份、setup、schema、成败相同，只有 sha 与帧数不同，记首个分叉步）；③二次生成失败而 gen1 成功；④成败相反；⑤身份／来源／结构错误（身份对不上、文件缺失、schema 不符）。
      - 噪声在容差内、且超容差局数 ≤ 5% 硬线时只记录；二次生成里冒过 1600 的局同样只记录，不回改交付（第一部分 §3）。
      - 出现「二次生成失败」或「成败相反」即 `PARITY_H_H2=FAIL`，不改判据、不重试正常失败（只对基础设施错误重试每身份 ≤ 1 次），**预定动作（用户 2026-10-01 拍板 (a)，§2.8 第 28 条）**：保留 gen1 作为交付、保留真实 `PARITY_H_H2=FAIL` 与逐身份证据，不换候选、不重试正常失败、不发起裁决提问，建站与收尾照常继续；只有第⑤类停止受影响分支，收尾统一报告。
      - gen1 某格备用候选耗尽时，不再像 v7 那样先手动补位再追认：该格判 FAIL、其余格继续，追加抽签须先补充授权。§2.2 第 6 条的候选表（InsertPeg 40 个，按 37.5% 失败率期望交付 25）就是为避免重演 v7 的 InsertPeg 缺口。

## 2.3 闸门总表

| 判定行 | 产出者（文件::函数） | 阶段 |
|---|---|---|
| `UPSTREAM_GUARD=PASS` | `scripts/parity/upstream_guard.py check --require-upstream` | 1、3b |
| 录像器零 diff（退出码 0） | `git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` | 每阶段 |
| 四入口 | `ls -1 scripts/*.py` 恰好四个 | 每阶段 |
| 核心短测末行 `passed` 且无 failed | `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q` | 每阶段 |
| `XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0` | `hard_regression.py::cmd_xhard0_reset_parity`（不改） | 1、3b |
| `XHARD0_IDENTITY=PASS shape=16x1x12 identities=192` | `hard_parity.py::cmd_export_xhard0_manifest`（不改） | 1、3b |
| `V8_DELIVERY_SET=PASS tasks=16 cells=43 total=1070` | `hard_regression.py::cmd_delivery_set`（新增）；生成时 `_rollout` 聚合步打印同名一行 | 2b（冒烟格表）、3 |
| `V8_SEED_DISJOINT=PASS tasks=16 tier_pairs=<n> shared=0` | `cmd_delivery_set` | 3 |
| `V8_LAYOUT_INDEPENDENT=PASS files=5 delivered=1070 parent_non_null=0 layout_equal_pairs=0` | `cmd_delivery_set` | 3 |
| `V8_TIER_VALUES=PASS tasks=14 cells=41 mismatches=0` | `hard_regression.py::cmd_tier_values`（新写） | 3 |
| `V8_STEP_CAP=PASS max=<实测> cap=1600 over=0 filtered=<n> xhard0_max=<实测> xhard0_cap=1300` | `hard_regression.py::cmd_step_headroom`（改写，加 `--pool`） | 3 |
| `V8_RESET_REPLAY=PASS shape=cells43 resets=43 replay=43 injected_mismatch=0 layout_drift=0 unused=0 layout_hit_bad=0 errors=0` | `hard_regression.py::cmd_reset_replay`（改判定行名） | 3b |
| `HARD_EVAL_SMOKE=PASS task=<任务> episode=<局> tier=<档> seed=<seed> ...` | `hard_regression.py::cmd_eval_smoke`（改 `expected`） | 3b |
| `XHARD0_EVAL_PARITY=INFO policy=<名> compared=192 status_diff=<n> steps_diff=<n>`（只报告，不是闸门） | `hard_regression.py::cmd_xhard0_eval_parity`（不改） | 3′ |
| `PARITY_H_H2=PASS tier=v8 compared=1070 cells=43 missing=0 extra=0 duplicate=0 identity_equal=1070 ...` | `hard_parity.py::cmd_compare`（加分母核对） | 4 |
| `V8_SITE=PASS sections=15 eval_placeholders=<n> eval_filter_hits=0 eval_media_requests=0 subgoal_missing=0 config_mismatch=0` | `site/v8_site_browser_check.py`（新增） | 4 |
| `V8_ORACLE_BROWSER=PASS cells=59 missing=0` | `site/v8_oracle_browser_check.py`（新增） | 4 |
| 不跑 | `layout-shared`、`prefix-geometry`（只适用 v7）；V6 全部判定行 | — |

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

### 2.4.2 正式运行手册（阶段 2b、3、3′、4，须先获批）

**集群克隆**：现有 `<GL_REPO>`（`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl`）停在 12.137／`newtaskRelease-v5`，落后 167 个提交，有他人未提交改动，也没有 `src/robomme_hard`——不动它。另建两份新克隆，git 操作只在本机有凭据的一侧发起：`robomme_benchmark-v8gen` 冻结在阶段 2 通过后的提交，供 2b、3、4 使用，二次生成结束前不改 HEAD（二次生成必须与 gen1 同一份代码，读封存的 v8 规格根，不读 3b 之后的包内规格）；`robomme_benchmark-v8eval` 冻结在阶段 1 通过后的提交，供 3′ 使用。两份各自 `UV_LINK_MODE=copy uv sync`。

**席位与 srun**：
- 生成席 63003408～63003411（各 1 A40／4 CPU／48 G）；评估席 63003486、63003487（同规格）；编排席 63003488（standard，1 CPU／4 G，无 GPU）。
- 每片：`srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared bash <包装脚本>`。`--gpu_cmode=shared` 只给干活的那一步，辅助 srun 不带（shared 步骤结束会把卡重置为独占）；从 standard 编排席发起前先清 `SLURM_*` 变量；长 ssh 会话 ≤ 9 条，多片改在登录节点 tmux 里起。
- 每席 4 worker（每 worker 1 CPU、12 G）；driver 不用 `max_tasks_per_child`。

**进程与监听**：tmux 会话名前缀 `v8-`，本轮起过的会话名记进 `docs/validation/newtask-v8/launch.md`；命令形如 `set -o pipefail; PYTHONUNBUFFERED=1 <命令> 2>&1 | tee <日志>; echo "EXIT_CODE=$?" >> <日志>`；一份日志挂一个 Monitor，过滤词含 `NO RECORD`、`reset 拒绝`、`svulkan2`、`EXCLUSIVE`、`RRT`、`全部完成`、`EXIT_CODE=`、`Traceback`；按进度文件 mtime 判无进展（阈值取 2b 实测单局最长用时的 3 倍），超阈值杀掉该片重起，重起 ≤ 1 次。

**产物**：逐局 h5 先落节点 `/tmp` 或 NFS 暂存，每片完成即 `rsync` 回 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v8/`，逐文件比 sha256，相同后删 NFS 副本（v7 gen1 共 828,434,639,410 字节，在 NFS 上逐局读 h5 曾 25 分钟超时）；`step-headroom` 等读 h5 的检查只在 `/data` 副本上跑；带输出根的命令先 `ls -ld <输出根>`；删除只按显式格目录，不跨运行 glob；收尾只留正式局 h5、视频与规格 jsonl。

**顺序**：
1. `freeze_specs.py --dry-run --seed-profile v8`（每档一次）打印逐格候选数与 reset 上限，与 §2.4.3 核对。
2. 2b 冒烟：在生成席 63003408 上单 worker 跑 7 种新格各 1 局（StopCube xhard1、StopCube xhard5、SwingXtimes xhard5、VideoUnmask xhard1、RouteStick xhard2、PatternLock xhard3、PickXtimes xhard3），走 freeze → 封存 → `generate_h5` → `delivery-set --cells smoke` → `step-headroom`；测单局用时回填 §2.4.3。
3. 阶段 3：五档冻结 → 4 片生成 → 合并 → `delivery-set`／`tier-values`／`step-headroom`。
4. gen1 验收（`V8_DELIVERY_SET`／`V8_TIER_VALUES`／`V8_STEP_CAP`）通过即建站与通知（§2.4.4；S4-A 已在正式生成前合入），不等 H2 与 3′。
5. 3′：编排席跑 `scripts/eval-official/orchestrate.py`，计划 JSON 把两条车道固定到 63003486／63003487，官方路线与 hard 路线 × 两策略各 192 局；两条路线 × 两策略共四组命令（入口、权重、参数、结果目录与结果格式）由运行负责人在 3′ 开跑前照 v7 的 `docs/validation/newtask-v7/` 留档逐字写进 `docs/validation/newtask-v8/launch.md`，不写「沿用 v7 设置」；结束后逐策略 `hard_regression.py xhard0-eval-parity --manifest scripts/configs/newtask-v7/xhard0_manifest.json --official <官方路线结果> --hard <hard 路线结果> --policy <名> --out <docs/validation/newtask-v8/records/xhard0-eval-parity-<策略>.json>`（`--out` 必填，结果格式与 v7 的转换入口同）。
6. 阶段 4（与 3′ 独立）：`hard_parity.py import-delivery --tier v8` 把 gen1 登记为 H，`hard_parity.py generate --tier v8 --specs-root <封存的 v8 根>` 生成 H2，再 `compare --pair H:H2 --tier v8`。
7. 全部任务结束后按 R11 逐个 `scancel` 清单内的 JobID，收尾报告写明「已释放」。

### 2.4.3 P3 一次性预算表（阶段 1 开跑前一次批完）

reset 与 rollout 分列，各自与 P3 阈值比较；成功、失败、递补、对照侧、冒烟、重跑都计入。

| 项目 | 阶段 | reset | rollout | worker | 上限与停止条件 | 预计耗时 |
|---|---|---|---|---|---|---|
| xhard0 环境层对拍 | 1 | 16 任务 × 1 档 × 12 局 × 2 侧 × 2 次 = 768（构造期另有 reset，以运行实数为准） | 0 | 2 进程 | 任一 `det_diff` > 0 即停，阻断进入阶段 2，收尾报告（§2.4.5） | 以 2b 前本机实测为准 |
| 同上（换包后重跑） | 3b | 768 | 0 | 2 进程 | 同上 | 同上 |
| 最小冒烟 | 2b | ≤ 7 格 × 3 = 21 | 7 格 × 1 = 7 | 1 | 任一失败即停，不进阶段 3 | 约 20 分钟 |
| 抽签 | 3 | 期望 2 任务 × 2 档 × 52 ÷ 0.46 + 1 任务 × 2 档 × 52 ÷ 0.54 + 1 任务 × 2 档 × 52 ÷ 0.57 + 1 任务 × 2 档 × 52 ÷ 0.65 + 其余 905 个候选 ÷ 0.97～1.0 ≈ 1,900；上限每格 ⌈候选数 ÷ 接受率 × 1.5⌉，合计约 2,850 | 0 | 4 席 × 4 | 某格到上限仍凑不够候选即停该格并报告 | 约 1～2 小时 |
| gen1 | 3 | ≤ 1,425（每条候选 rollout 含 1 次 reset；更正前误填 0） | 首轮 1070（乘式见第一部分表 2）；递补上限 1425 − 1070 = 355，每个候选至多试一次，合计 ≤ 1425；基础设施重试每身份 ≤ 1 次 | 4 席 × 4 | 某格备用候选耗尽即该格 FAIL，其余格继续 | 约 3～4 小时（v7 二次生成 16 worker 回放 1100 局用 2 小时 45 分） |
| 回注回放 | 3b | 43 格 × 1 = 43 | 0 | 1 | 任一不符即停 | 约 15 分钟 |
| 评估入口冒烟 | 3b | 2 | 2 局 × 1 = 2 | 1 | 失败即停 | 约 10 分钟 |
| xhard0 评估 | 3′ | 768（每局含 1 次 reset） | 16 任务 × 1 档 × 12 局 × 2 策略 × 2 路线 = 768 | 2 评估席 | 只对基础设施错误重试，每局 ≤ 1 次；正常失败如实记 0，不重试 | 约 6～9 小时（按 v7 正式评估 10 席 7 小时跑完 2 策略 × 1292 局折算） |
| 二次生成 | 4 | 1,070（每局含 1 次 reset） | 16 任务的 43 格交付集 = 1070，只回放、不递补 | 4 席 × 4 | 失败如实记录，基础设施重试每身份 ≤ 1 次 | 约 3 小时 |
| **合计** | | 上限 768 × 2 + 21 + 2,850 + 43 + 2 + 1,425 + 768 + 1,070 = **7,715**（2026-10-01 更正：rollout 内的 reset 计入，原 4,452 漏算 3,263；构造期 reset 以运行实数单列报告，不计入阈值比较） | 上限 7 + 1425 + 2 + 768 + 1070 = 3,272 | | 基础设施重试另列 ≤ 3,263（每身份 ≤ 1 次，账本跨重启保留，分片重启不重置） | |

已有产物复用：xhard0 的站点生成视频复用 `artifacts/newtask-v7/site-media/xhard0-gen`（0 次渲染）；v7 的官方路线评估结果按用户 2026-10-01 决定不复用，两条路线都重跑。超出本表任何一行的上限，暂停受影响部分，合并为一次补充授权。

### 2.4.4 P4 自动建站与通知链

- **触发**：不只听「完成行」。生成结束后读取并核验最终报告（`delivery.json`、`V8_DELIVERY_SET` 与 `V8_STEP_CAP` 判定行），全部 PASS 才建站；任一 FAIL 停在报告，只通知、不建站。
- **监督**：建站与浏览器检查跑在独立的 tmux 会话里，每步写心跳文件（计数键显式写零）；主会话对检查日志与心跳文件各挂一个 Monitor，检查器自身崩溃由心跳超时发现，不靠同一个可能崩溃的脚本自报。**独立 watchdog**：另起一个只读监督进程（`scripts/injection-dev/v8_watchdog.py`，S2-D 产出）按心跳文件 mtime 判「停止更新」，阈值 = 该步实测用时的 3 倍（2b 回填，缺省 15 分钟），超阈值发事件 `P4_WATCHDOG=FAIL step=<名> stale_s=<n>` 并停止受影响部分；监听文件更新本身发现不了「不再更新」，所以 Monitor 挂在 watchdog 的事件日志上。夹具⑤必须真正 `kill` 被监督子进程，证明监督者仍能报出失败。
- **夹具（阶段 2，不触发仿真）**：①成功；②生成报告出现 FAIL 行；③完成行超时未到；④守卫 FAIL（如 `V8_STEP_CAP over>0`）；⑤建站脚本或浏览器检查器崩溃；⑥同一完成事件重复到达。另加零计数报告（`exec_over_cap=0`、`filtered=0`、`backfills=0`、`infra_retries=0`）走「写 JSON → 读 JSON → 接续守卫」往返。
- **通知路径**：Monitor 事件由主会话转达给用户；未注册宿主唤醒时照实写「后台进程会继续，但自动唤醒未建立」，不承诺无人值守完成。
- **恢复**：只做未完成步骤；已存在的报告先核身份、来源与完整性再复用，不覆盖、不重跑生成；续行前先查各片是否已启动，防止重复派发。

### 2.4.5 运行中预定动作（用户 2026-10-01「其他全部同意」；运行中不再发起授权提问）

| 情形 | 预定动作 |
|---|---|
| 基础设施错误（节点掉、Vulkan 起不来、NFS 超时等） | 只用已批重试额度（每身份 ≤ 1 次、合计 ≤ 3,263）；尝试账本写进该片的 `results.jsonl` 并跨重启保留，分片重启不重置额度；额度用尽即该身份记失败 |
| H2 正常失败（第③类）或成败相反（第④类） | 保留 gen1 作为交付、保留真实 `PARITY_H_H2=FAIL`，不换候选、不重试，建站与收尾继续（§2.2 第 11 条） |
| 身份／来源／结构错误（第⑤类，含 `delivery.json` 身份对不上、文件缺失、schema 不符） | 停止受影响分支（该片或该对拍），保全证据，其余分支继续，收尾统一报告 |
| gen1 某格候选或递补额度耗尽 | 不补抽；该格 `V8_DELIVERY_SET=FAIL`，其他格继续；全集不齐就如实报未完成，不发起补充授权 |
| 某块两轮审查仍 `PRE_MERGE_REVIEW=FAIL` | 保留该 worktree 分支不合入，停止依赖它的后续块，无依赖的块继续；收尾统一报告 |
| `POST_MERGE_REVIEW=FAIL` | 停止后续合并、不 push，合并提交留本地 `ahead`，收尾报告写明 |
| 预算表任一行达到上限 | 暂停该行对应工作，其余继续；收尾合并为一次补充授权请求，运行中不问 |
| 未覆盖的异常或疑似超授权 | 保全证据（日志、报告、`git status`）、停止受影响部分，收尾统一报告 |
| 占位 job 到期 | 按 `greatlakes.md` 重提同规格席位并记入清单，收尾报告写明；不释放未到期席位（R11） |

## 2.5 风险登记

1. **过滤改变布局分布**：过滤掉执行步 > 1600 的候选，会剔掉 PickXtimes 8 次（xhard3）里极近底座的布局。原区域内的超限比例未知：原区域 8 次 21 局 0 局超限；1614 那局来自强制近底座带，混用两种样本得出的「约 1/22」不能当概率用。正式生成按逐格同一分母统计 `exec_over_cap` 数。其余任务按实测不会触发。
2. **上限定死 1600 对策略侧的截断**：专家侧按构造不超；策略成功局可比专家长（§2.9.5），v7 评估里有 2 局成功会被截（BinFill xhard2 1823、MoveCube xhard4 3120）。
3. **生成失败**：InsertPeg 37.5%、MoveCube 20%、BinFill 15～21%、StopCube／SwingXtimes 约 7%。已按 §2.2 第 6 条候选表留量（InsertPeg 40 个候选期望交付 25，够 20）；仍不够时该格 FAIL，补抽须补充授权。
4. **硬件差异**：本轮在 Ada 上测，正式生成在 A40 上。screw 规划是确定的，步数应一致；但 RRT 兜底（`ScrewThenRRT`）带随机性，可能有个别局不同。
5. **布局独立带来的差异**：各档独立抽布局（按档 seed，R9）后，同任务跨档不再共享圆盘位置等前缀，跨档比较时布局噪声与难度梯度叠在一起；换取的是不需要派生链、每格过滤 > 1600 各自独立。`layout-shared`／`prefix-geometry` 守卫对 v8 规格无意义，不跑。
6. **新增档位的结构改动面**：xhard5 只登记在全局合法档与 Swing／StopCube 的配置里（R8），避开了 VideoRepick 与两个 Swap 任务对 `NEWVALUE_DIFFICULTIES` 的遍历；按符号 grep 命中 21 个测试文件（第一部分 §2.4 逐个列出），另有 48 个测试文件提到 xhard1～4 字面值、多数不受影响。StopCube 的 xhard4 本来就在 v7 冻结规格里，新增的是 xhard1～3、5 四格，`reset-replay` 要覆盖。核心短测与 `XHARD0_RESET_PARITY` 必须全绿才能进阶段 2。
7. **xhard0 评估只能出 INFO**：策略层不可复现（v7 MME 同入口同卡重跑 11 局有 5 局翻转），两路线的差异不能判为回归；「没改坏 xhard0」由 `XHARD0_RESET_PARITY` 判定。
8. **二次生成 FAIL**：v7 先例——InsertPeg 二次生成在规划阶段失败致 `PARITY_H_H2=FAIL`，用户裁决交付集不动。v8 按 §2.2 第 11 条逐身份分四类计数，出现「二次生成失败」或「成败相反」按 §2.2 第 11 条预定动作保留 gen1 与 FAIL，不改判据、不裁决提问。
9. **席位时效**：7 个占位 job 于 2026-10-01 16:05～16:07 EDT 提交、48 h；阶段 1～2b 实施期间可能到期。按 R11 不提前释放；到期则按 `greatlakes.md` 重提并在汇报里说明。

## 2.6 盲区诚实清单

- PickXtimes 8 次在原区域只有 21 局实测（最大 1533），原区域内的超限比例未知；1614 那局来自强制近底座带。
- 「近底座强化带」有一半成功局落在原区域外，它的数字不是原区域的上界。
- 探针走的是现场抽样，不是 v7 的「母布局 → 派生」链路；也没在 A40 上跑。
- xhard5 档没有在任何链路上跑过：本轮探针是把取值从外部传给 xhard4 的 decision（§2.4.1），等价于「xhard5 = 10 次、干扰 4 块」，但档位枚举、builder、生成驱动都没经过；由阶段 2b 冒烟首次走通。
- SwingXtimes 5、7 轮与 PickHighlight、VideoRepick、Unmask、Swap、Place、PatternLock、RouteStick 都直接沿用 v7 每格 20 局的数据，本轮没有重测。
- PatternLock 区间 [9, 12]／[13, 15]／[16, 18] 内的节点数分布没有实测，只知道 v6 区间 [21, 25] 贴下界。
- StopCube 每个值只有 1～3 局（执行步由时钟决定，波动 ≤ 10 步）；1/13 的生成失败是小样本。
- 没有测新配置下的策略成功率；按用户 2026-10-01 决定，v8 不做两策略评估，站点评估板块置空。
- VideoUnmask／ButtonUnmask xhard1 的 2／4／2 没单独测，上界按 xhard2 的 3／4／2（454／557）推断。RouteStick／PatternLock 区间档的最大按上端 16 段 800、18 节点 626，与定值时相同。
- `V8_LAYOUT_INDEPENDENT` 的数据检查只比位置类取值（`spec.layout.*`、`actions.path_nodes` 等），不是逐帧比对；按档 seed 不交才是独立的构造性保证。
- 生成与评估的耗时估计来自本机探针与 v7 记录，A40 席位上的实际用时以 2b 测速为准。
- 230 局里有 19 局是我把区域写错（开局即 `ValueError`），不是环境问题；在 §2.10.1 单列，不计入任何失败率。

## 2.7 留档与 commit 纪律

- 本文件 12.277 首版、12.278／12.279 修订局数、12.280 重写第一部分并建分支、12.281 修订梯度（去 9／10 次、过滤 1600、VU／BU xhard1、区间档），每次只 `git add` 这一个文件。工作区里 `third_party/SimpleMemVLA` 的子模块内容改动（` m`）是他人在途工作，不动。
- 探针产物 `artifacts/v8-probe/` 不进 git。探针脚本在会话 scratchpad 不保留，方法按 §2.4.1 可以复现。
- 12.282 只记录本轮分支对齐文档；12.283 记录四项拍板；12.284 记录站点与评估口径；12.285 记录席位与并行口径；12.286 记录对抗验证修订与之后的四项拍板；12.287 记录 P3 预算整表获批与 gen1／二次生成差异处置口径；12.288 是正本规则同步；12.289 记录子代理分工与分配表；12.290 记录审计后三项拍板、预定动作与分配表修正；均不算 V8 实施。后续获批的 V8 实施在分支 `newtaskRelease-taskV8` 上进行，按 §2.12 的分配表派写入型子代理：子代理在各自 worktree 分支上的 `sub/<编号>: ` 提交全部保留、不占 12.x 号；主会话每合入一块打一个 `--no-ff` 合并提交，合并提交按 12.x 递增，从 12.291 接续。commit body 按第 11 条写用户原话、计划、过程、意外、实测与下一步。正式生成的留档写到 `docs/validation/newtask-v8/`（`launch.md` 记席位、会话名、命令与 env 覆盖，`result.md` 记判定行与结论）。

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
   - 12.286 更正：上式「4 任务 × 4 档 × 20」有误，四档齐全的只有 VideoUnmask、ButtonUnmask 两个任务，应为 2 任务 × 4 档 × 20 = 160；原式各项加起来是 1230 而不是 1070，正确为 150 + 160 + 560 + 160 + 40 = 1070。本条已被第一部分表 2 下方的乘式取代，原文保留不改。
9. 「给我呈现一个这样的完整表格　你现在的废话太多了 第一部分（给人看）彻底重写第一部分对于难度的表述只写在表格内就是这个表格来表达这个梯度的问题。然后你再说你需要修改哪些文件内容最后说怎么去验收我不需要再去对拍V6了我还是需要之前的XR的0对拍但是新的V7的只需要保留V7V6的可以全部删除。」（2026-10-01，附用户贴回的梯度表；本次重写依据）
   - 我的理解：第一部分只留「梯度表 + 局数表」「要改哪些文件」「验收」三节；xhard0 保留且 xhard0 对拍（`xhard0-reset-parity`／`xhard0-eval-parity`）保留；V6 的对拍、配置、站点、检查器与只服务它们的测试删除；V7 的对拍设施保留并改名 V8。
10. 「你现在先表上只写在计划里并且让这个计划要开启一个新的Bronch现在的Brach是v5改成v6。」（2026-10-01）
   - 我的理解：本轮只改计划、不动代码；v8 在新分支 `newtaskRelease-v6` 上实施，自 `newtaskRelease-v5` 的 `49ba3eb8` 分出，本次计划 commit 落在新分支。
11. 「我要的是你不改任何的这个非难度梯度以外的参数你如实的报告我哪些会抄了不要自己改。」（2026-10-01）
   - 我的理解：圆盘区域等非梯度参数一律不动，方案 A 作废。只改梯度值时超 1600 的是 PickXtimes 抓 9 次（最大 1973）与抓 10 次（最大 1919），抓 8 次偶尔（1614）。
12. 「PickXtime 的 9/10次去掉　sample 的时候全部任务 filter 掉execution 超过 1600 的　VideoUnmask ButtonUnmask Xhard1 是 2/4/2　RouteStick, xhar1 8-10, xhard2 11-13, xhard3 14-16　PatternLock  xhar1 9-12, xhard2 13-15, xhard3 16-18」（2026-10-01，本次修订依据）
   - 我的理解：PickXtimes 交付 xhard1～3 = 6／7／8，每档 10 局；抽样阶段全部任务按候选的真实 h5 过滤执行步 > 1600 并递补，上限定死 1600；VideoUnmask／ButtonUnmask xhard1 改为抓 2、干扰容器 4、干扰方块 2；RouteStick、PatternLock xhard1～3 改为区间、档内均匀抽。
   - 12.286 更正：RouteStick 是档内均匀抽；PatternLock 是随机路径的拒绝采样，只保证落在区间内，比例不保证均匀（表 1；用户第 23 条定为不改代码、只改表述）。
13. 「各档布局改为每一个都是独立的初始化位置不需要再做重叠的」（2026-10-01，答原「待拍板」①）
   - 我的理解：每个交付格各自独立抽初始化布局，不再从母布局派生，低档不照抄高档前缀；`derive_specs.py` 链路 v8 不走。
14. 「还有什么我没有定下来」→ 我列出四项：PickXtimes 30 还是 50 局、派生工具链删还是留、不交付的档抽不抽、V6 留档删不删。
15. 「1全部都是50局来分配 2保留 3只抽交付的 4留着」（2026-10-01）
   - 我的理解：①PickXtimes 50 局分三档 17／17／16（低档多一局），每任务合计改 62、全集 1070、含 xhard0 1262；②`derive_specs.py`、`layout_whitelist.json`、`layout-shared`／`prefix-geometry` 守卫保留在仓库，v8 不调用；③只抽 43 个交付格，不交付的档不抽、不生成；④`docs/validation/newtask-v6/` 与 `docs/plans/0925-newtask-release-v6-plan.md` 保留只读。
   - 第 8 条里 PickXtimes 「每档 10 局」的记法被本条取代。
16. 「你需要和上一代一样生成一个同样的网站尽可能保持这个布局的完全一致但是因为现在没有新的两个model的invution的制空不要删除。Evaluation就没有新的两个model的evaluation了」（2026-10-01）
   - 「invution的制空」按语音转写理解为「evaluation 的置空」。我的理解：v8 出一个与 v7 站点布局完全一致的逐局站点；v8 不跑 SimpleMemVLA／MME-VLA 评估，站点里评估相关板块原位保留、内容置空、不删；阶段 4 的评估侧核对随之取消，xhard0 评估对拍引用 v7 结果。
   - 复核时发现 §2.5 原拟删除的 `v6_site.py` 是 v7 站点服务端，改为改名 `site_server.py` 保留。
17. 「维持使用A40。你可以开多少个job」「你现在就可以生成V40Jb开始排队了。A40的J0B」（2026-10-01；「V40Jb」按语音转写理解为「4 个 job」）
   - 处置：按规约默认上限提交 4 个 A40 占位 job 63003408～63003411（4C/48G，超默认规格，已在当轮说明）。
18. 「生成和Evaluation可以同步进行吗就是EXC的0的xhard0的Evaluation是否可以同步进行用四个站位J0B进行生成然后再用一些jb去进行。再用一些jb进行evaluation。并且只要生成完毕了就直接做网站然后通知用户」（2026-10-01）
   - 我的理解：xhard0 评估对拍与新局生成并行，各用各的席位；生成完成后自动建站并通知。本条把第 16 条「xhard0 评估对拍沿用 v7 不重跑」改回「照跑」。
19. 「同意使用两个A40席位。加上一个StandardCPU。」（2026-10-01）
   - 处置：提交 63003486、63003487（A40 评估席）与 63003488（standard 编排席），本人名下共 7 个作业，超过默认 4 个已由本条放行。
20. 「/data/hongzefu/robomme_benchmark_MotionJEPANewTask/1001-newtask-v8-xhard-gradient-plan.md 对抗验证该计划 使用workflow 给出修改方案」（2026-10-01）
   - 处置：锚定 `0978a0821490bf2e10311acf9f9375a3a2b9fac8`（只审该提交，排除 `third_party/SimpleMemVLA` 子模块在途改动，用户选定）；workflow 4 个方向只读审查（环境常量与档位枚举、规格抽签递补与下游、验收闸门与删 V6 及测试同步、规则合规预算与内部一致性），每方向 1 个 agent 逐条反驳，共 8 个 sonnet agent；57 条 finding 反驳后保留 56 条，驳回 1 条（PickXtimes xhard4 取 9 不算缺陷）。
21. 用户转来 Codex 的审查结果（9 条），并说：「以上这些是Codex的审查结果。根据Codex的审查结果你可以再去核实比如说用来核实然后总体给我一个修改方案」（2026-10-01）
   - 处置：9 条逐条对代码核实，全部成立；与第 20 条合并去重为 11 项修改，即 12.286 本次修订。其中两条比原报告更重：档位扩展同时影响 `VideoRepick`、`VideoUnmaskSwap`、`ButtonUnmaskSwap` 三处遍历与四处 `[-1]`／`[:-1]` 写法；v7 留档显示 MME 同入口同卡重跑 11 局有 5 局翻转，`XHARD0_EVAL_PARITY` 按设计拿不到 PASS。
22. 「1要跑 2 m没看懂 3没看懂 4你任务全部结束后释放 现在别管」（2026-10-01，答四项待拍板）
   - 我的理解：①二次生成对拍要跑；②③没看懂，需重新详细解释后再选；④7 个占位 job 等全部任务结束后按清单释放，现在不动。
23. 详细解释后用户选择：第 2 条「B：两条路线都重跑 768 局」；第 3 条「A：不改代码，只改表述」（2026-10-01）
   - 我的理解：xhard0 评估的官方路线与 hard 路线都重跑，16 任务 × 1 档 × 12 局 × 2 策略 × 2 路线 = 768 局，只出 INFO；PatternLock 保持现有拒绝采样，计划改述并在生成后报逐格分布。
24. 「同意 修改计划」（2026-10-01）
   - 处置：按第 20～23 条改写本文件，即 12.286。
25. 「同意所有预算」（2026-10-01，答 §2.4.3 P3 一次性预算表）
   - 处置：整表获批，记入引言「已批准」与 12.287；阶段实施仍按 §3 实施步骤表另行获批。
26. 「gen1（第一次生成，含递补）≤ 1,425 局／├ 二次生成 1,070 局　这些之前生成过程中有不同吗 如果不同是怎么处理的」（2026-10-01）
   - 处置：按 v7 留档作答，并把 v7 实测与 v8 处置口径写进 §2.2 第 11 条。
27. 「不执行 只改plan」（2026-10-01）
   - 我的理解：本轮只改计划文件，不开始任何阶段的实施，也不启动任何 reset／rollout。
28. 「1同意 2 a 3更正 其他全部同意」（2026-10-01，答 Codex 审计 `d7c806f0` 后提出的三项决策与预定动作清单；此前「同意 开始修改v8 md」「v8 md有最新修改 注意看」）
   - 我的理解：①整份实施范围与 §2.12 分配表一次授权，按依赖顺序连续执行，不再逐步请示；②H2 正常失败预定为 (a) 保留 gen1 与真实 FAIL，不换候选、不重试正常失败；③reset 预算按「rollout 内的 reset 计入」更正为 7,715，重试另列 ≤ 3,263；运行中裁决全部改为 §2.4.5 预定动作；审计提出的分配表 8 项修正全部采纳。

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
10. **StopCube 拆档的代价要如实列出。** 原建议 S1（单档分层）只改一个区间常量；用户 2026-10-01 决定拆成 xhard1～5 五档定值后，须动 `require_xhard4_only` 闸门、`XHARD4_ONLY` 和若干测试（第一部分 §2.1、§2.4），这是用户知情后的选择，不再作为「不推荐」。（12.286 更正：原文写「白名单 L／G 表」与第一部分 §2.1「白名单不动」矛盾；定为白名单 JSON 不动，`test_v7_whitelist_semantics.py` 改用独立常量 `WHITELIST_TASKS`。）

## 2.12 子代理分配表（正本 `AGENTS.md` 第 2 条「子代理分工与合并必须写进计划」；执行机制按 `CLAUDE.md`「计划执行模式」）

**通用口径**：每个写入型子代理 `isolation: "worktree"` + `model: "opus"`；`BASE` 在每块派发时取当时工作分支 HEAD 填入；commit 前缀 `sub/<编号>: `；worktree 内验收一律按本仓库 `CLAUDE.md` 的取法只跑 CPU 定向测试；GPU／仿真／真实产物闸门列在「合并后主会话」行。可写集合用 `git diff --name-only BASE..TIP` 逐项核对，越界即 `SCOPE=FAIL`。`uv.lock`、`pyproject.toml`、子模块 gitlink、`src/robomme/**`（P2）任何块都不得碰。**Codex 接手时的口径**（正本 `AGENTS.md` 第 26 条）：本表的文件边界、接口契约与合并顺序沿用；`isolation`／`opus`／子代理自行 commit 是 Claude 路径，Codex 由主代理自己 `git worktree add` 建隔离目录、在委派说明里指定路径，子代理不暂存、不提交、不 push，提交与合并由主代理负责。

| 编号 | 阶段 | 目标 | 可写文件集合 | 禁触 | 接口契约 / 依赖 | 合并顺序 | worktree 内验收 | 资源 | 判定行 |
|---|---|---|---|---|---|---|---|---|---|
| S1-A | 1 | 7 个改值环境的常量与档位合法性（第一部分 §2.1 前 9 行） | `src/robomme_hard/robomme_env/{PickXtimes,SwingXtimes,StopCube,VideoUnmask,ButtonUnmask,RouteStick,PatternLock}.py`、`robomme_env/utils/{difficulty,sampling_config}.py`；`tests/_shared/v7_tier_values.py`；`tests/lightweight/test_v7_tier_values.py`、`test_v4_xhard_{pickxtimes,swingxtimes,stopcube,videounmask_buttonunmask}.py`、`test_v5_xhard_{pickswing,videounmask_buttonunmask,patternlock_routestick}.py`；`tests/lightweight/test_v6_difficulty_tiers.py`→`test_v8_difficulty_tiers.py`（改名；`NEWVALUE_DIFFICULTIES` 四档、`ALL_NEWVALUE_TIERS` 五档断言；删 3 个 v6 seed 测试——合法档位全集的断言随扩档一起改）；新建 `tests/lightweight/test_v8_native_blocks_unchanged.py`（9 个不改环境 `native_blocks()` 逐字节回归、7 个改值环境剥新值键后一致） | `hard_specs.py`、`scripts/**`、其他 `test_v6_*.py`、`vqa_options.py`（不改代码） | 对外暴露 `difficulty.XHARD5`、`ALL_NEWVALUE_TIERS`；`NEWVALUE_DIFFICULTIES` 保持四档（R8）；四处 `[-1]`／`[:-1]` 改字面 `"xhard4"` | 1 | 上列测试文件定向 pytest；`test_decision_visible_part_unchanged`、`test_native_decision_visible_part_unchanged`、`test_vqa_checkpoints_match_env` 通过 | CPU | `S1A_TESTS=PASS failed=0` |
| S1-B | 1 | 删 V6、v6 seed 迁移、`hard_specs` 阶段 1、`site_server` 改名 | `src/robomme_hard/env_record_wrapper/hard_specs.py`（只做阶段 1 部分：删 v6 偏移取值与 profile，加 `V7_TIERS`、`V7_XHARD4_ONLY`）；`scripts/configs/newtask-v6/`（删）；`scripts/injection-dev/site/v6_candidate_values.py`、`v6_gt_lengths.py`、`v6_gt_lengths.json`、`v6_site.html`、`v6_site_catalog.py`、`v6_v0_native_definitions.py`、`v6_tier_monotone.py`、`site_io.py`（删）；`site/v6_site.py`→`site_server.py`、`site/v7_site.py`、`site/v7_subgoal_lengths.py`（改加载路径）；`scripts/parity/train_split_config.py`；`tests/lightweight/test_v6_{candidate_values,site_labels,site_v11,tier_monotone}.py`（删）；`test_v6_{swap_uniform,xhard_movecube_region,audit_fix,audit_fix_scripts}.py`（去前缀，后者 v6 seed 调用改 v7）；`tests/lightweight/test_v5_xhard_movecube.py`（MoveCube 测试改名后的旧导入）；`test_hard_state_machine.py`、`test_v7_seed_rule.py`（阶段 1 部分）、`test_v7_freeze_schema.py`（阶段 1 部分）、`test_sampling_config_split.py`、`test_v7_whitelist_semantics.py`、`_shared/v7_specs_fixture.py`、`test_v7_candidate_pool.py` | `robomme_env/**`、`test_v8_difficulty_tiers.py`、`_rollout.py`、`hard_regression.py`、`hard_parity.py`、`export_eval_identities.py` | **派发于 S1-A 合入之后**（要用 S1-A 的 `ALL_NEWVALUE_TIERS` 修正 `_shared/v7_specs_fixture.py`／`test_v7_candidate_pool.py` 里「V7 四档结果对五档全局枚举」的比较）；删 v6 与迁移 5 个调用 v6 规则的测试在同一块内完成（第一部分 §2.5「迁移」行）；`site_server.create_server` 签名不变；`V7_XHARD4_ONLY = ("StopCube","InsertPeg","MoveCube")` 供 v7 夹具 | 2 | 四条可达检查：①删除对象不存在（逐路径 `test ! -e`）；②无悬空导入：`git grep -n 'site_io\|v6_tier_monotone\|v6_candidate_values\|v6_gt_lengths\|v6_v0_native_definitions\|v6_site_catalog\|v6_site\.html' -- scripts tests` 为空；③无活动 V6 快照读取：`git grep -n 'V6_FROZEN\|v6-sampling-frozen' -- scripts tests` 为空；④无 v6 seed 调用：`git grep -n 'seed_rule_for([^)]*"v6"' -- scripts tests src` 为空。九个冻结环境、`V6_ADDED_KEYS`、`test_v6_*` 改名后的回归以及 `scripts/README.md` 的历史文字里的 v6 兼容标识允许保留，不作为命中；上列测试定向 pytest | CPU | `S1B_DELETED=PASS missing=0`、`S1B_GREP=PASS dangling=0 snapshot=0 seed_v6=0`、`S1B_TESTS=PASS failed=0` |
| 主会话 | 1 | 阶段 1 闸门 | — | — | S1-A、S1-B 合入后 | — | 核心短测全量、`UPSTREAM_GUARD`、录像器零 diff、四入口、`XHARD0_RESET_PARITY`、`XHARD0_IDENTITY` | GPU（本机 Ada 或生成席） | `POST_MERGE_REVIEW=PASS ×2`；`XHARD0_RESET_PARITY=PASS … det_diff=0`；`XHARD0_IDENTITY=PASS identities=192` |
| S2-A | 2 | `hard_specs` 的 v8 常量、schema/4、按档 seed、`load_specs_v8` | `src/robomme_hard/env_record_wrapper/hard_specs.py`（阶段 2 部分）；`tests/lightweight/test_v7_seed_rule.py`（阶段 2 部分）；新建 `tests/lightweight/test_v8_specs_schema.py`（`load_specs_v8` 对完整根、冒烟 7 格根、分片子集根的往返；schema/4 篡改必失败；按档 seed 两两不交；`TIERS`／`BUILDER_TIERS`／`EXPECTED_CELLS`／`TIER_MAX_STEPS` 保持 v7 值） | `scripts/**`、`robomme_env/**` | **对外契约**（S2-B、S2-C、S2-D 据此并行开发）：`V8_TIERS`、`V8_CELLS: dict[(task, tier)] -> int`、`V8_EXEC_CAP = 1600`、`V8_SEED_OFFSETS`、`SEED_PROFILES["v8"]`、`seed_rule_for(tier, "v8")`、`SCHEMA_V8 = "hard-specs/4"`、`IDENTITY_KEYS_BY_SCHEMA[SCHEMA_V8]`、`validate_specs` 的 /4 分支、**`load_specs_v8(root, expected_cells: dict[(task, tier)] -> int)`**——只校验调用方给定的格表（文件集合、每格 selected 数、跨档 seed 不交都按 `expected_cells` 算），完整根传 `V8_CELLS`、2b 冒烟传 7 格表、分片传该片子集，最终聚合时才核全部 43 格；`TIERS`／`BUILDER_TIERS`／`EXPECTED_CELLS`／`TIER_MAX_STEPS` 不动（R10）。S2-A 不碰 `hard_parity`（`test_xhard0_native.py` 的 `'v8' in H.TIERS` 归 S2-C） | 3（阶段 2 第一个，单独合入后再派 S2-B／C） | 定向 pytest 上列测试（含三种局部根往返） | CPU | `S2A_TESTS=PASS failed=0` |
| S2-B | 2 | 抽签、生成驱动、入口分派、identities | `scripts/injection-dev/freeze_specs.py`、`_freeze.py`、`_rollout.py`、`generate_h5.py`、`_report.py`、`export_eval_identities.py`（含 `V6_SECONDS`→`TASK_SECONDS`）；新建 `tests/lightweight/test_v8_delivery_flow.py`（合成 v8 根上 `generate_h5` continue 模式退出码 0；分片子集根与冒烟 7 格根各一次往返，`expected_cells` 按片传；`delivery.json` 计数键显式零值；聚合步只在全部片齐后核 43 格） | `hard_specs.py`、`scripts/parity/**`、`site/**` | 依赖 S2-A 已合入；产出 `delivery.json`（schema `v8-delivery/1`，键 `exec_over_cap`／`backfills`／`infra_retries`／`failed` 显式写零）与判定行 `V8_DELIVERY_SET`，供 S2-C 读、S2-D 听；`run_continue_v7`、`V7_*` 原样保留 | 4 | 定向 pytest；`uv run … generate_h5.py --help` 可运行 | CPU | `S2B_TESTS=PASS failed=0` |
| S2-C | 2 | 对拍守卫三个子命令与 `hard_parity` 的 v8 键、分母核对 | `scripts/parity/hard_regression.py`、`scripts/parity/hard_parity.py`；`tests/lightweight/test_xhard0_native.py`（阶段 2 部分：`'v8' in H.TIERS`）；新建 `tests/lightweight/test_v8_regression_cmds.py`（`delivery-set --cells <格表>`／`tier-values`／`step-headroom --pool` 对完整根、冒烟 7 格根、分片子集根的往返；`compare` 四方集合不等即 FAIL） | `scripts/injection-dev/**`、`hard_specs.py` | 依赖 S2-A；读 S2-B 的 `delivery.json` 契约（只按 §2.2 第 7 条键名编码，不等 S2-B 合入）；`xhard0-reset-parity`、`xhard0-eval-parity` 比较器不动 | 5（与 S2-B 并行开发、顺序合入） | 定向 pytest；三个子命令 `--help` 可运行 | CPU | `S2C_TESTS=PASS failed=0` |
| S2-D | 2 | P4 自动建站与通知链的接续脚本、独立 watchdog 与六种夹具（§2.4.4） | 新建 `scripts/injection-dev/v8_continue_after_gen.py`（读 `delivery.json` 与判定行→建站→浏览器检查→通知，每步心跳文件）、新建 `scripts/injection-dev/v8_watchdog.py`（按心跳 mtime 判停更，发 `P4_WATCHDOG=FAIL` 事件）、新建 `tests/lightweight/test_v8_continue_fixtures.py`（①成功 ②报告 FAIL 行 ③完成行超时 ④守卫 FAIL ⑤检查器崩溃——真正 `kill` 被监督子进程、watchdog 仍报出 ⑥重复事件 + 零计数报告往返） | 其余全部 | 依赖 S2-B 的 `delivery.json` 契约、S2-C 的判定行名、**S4-A 已合入**（用真实入口 `site/v8_site.py`、`site/v8_site_browser_check.py` 对合成目录做接续测试，不用占位名） | 7 | 定向 pytest（不触发仿真；夹具⑤含真实子进程终止） | CPU | `S2D_FIXTURES=PASS cases=6 watchdog_detected=1` |
| 主会话 | 2～4 运行 | 阶段 2 闸门与运行 | — | — | S2-A／B／C、S4-A、S2-D 合入后 | — | 核心短测全量；2b 冒烟、阶段 3 生成按 §2.4.2 在 GL 席位 tmux 跑，预算按 §2.4.3；gen1 验收通过即建站与通知；3′ 评估与阶段 4 H2 独立跑 | GL A40 席 | `POST_MERGE_REVIEW=PASS ×5`；§2.3 各判定行 |
| S3b | 3b | 换包（一个提交） | `src/robomme_hard/env_metadata/test-hard/xhard{1..5}/specs.jsonl`（从主检出 `artifacts/newtask-v8/specs-root/` 复制）；`hard_specs.py`（3b 部分：`TIERS`／`BUILDER_TIERS`／`XHARD4_ONLY`／`EXPECTED_CELLS`／`TIER_MAX_STEPS`）；`hard_builder.py`；`tests/lightweight/test_xhard0_native.py`（3b 部分）、`test_hard_builder_xhard0.py`、`test_v7_freeze_schema.py`（3b 部分）；`src/robomme_hard/README.md`、`scripts/README.md` | `robomme_env/**`、`scripts/injection-dev/**`、`scripts/parity/**` | 依赖阶段 3 产出的封存 v8 根与 `V8_DELIVERY_SET=PASS`；worktree 内只能 commit 一次（R10 一个提交），分多次就先 squash 到一次再交回 | 8 | 定向 pytest（builder、xhard0_native、freeze_schema） | CPU | `S3B_TESTS=PASS failed=0`、`git log BASE..HEAD` 恰 1 条 |
| 主会话 | 3b | 换包闸门 | — | — | S3b 合入后 | — | 核心短测全量、`V8_RESET_REPLAY`、`XHARD0_RESET_PARITY`、`XHARD0_IDENTITY`、`HARD_EVAL_SMOKE`、`UPSTREAM_GUARD` | GPU | `POST_MERGE_REVIEW=PASS`；§2.3 判定行 |
| S4-A | 4（代码在正式生成前合入） | 站点六件 | 新建 `scripts/injection-dev/site/v8_site.py`、`v8_site.html`、`v8_site_catalog.py`、`v8_site_browser_check.py`、`v8_subgoal_lengths.py`、`v8_oracle_browser_check.py`；新建 `tests/lightweight/test_v8_site_catalog.py`（评估来源全部缺省时每局 `eval` 为空、筛选零命中、1262 校验） | 其余全部（`v7_*` 六件原样保留） | 依赖 S1-B 的 `site_server`、S2-B 的 identities 文件名 `eval-identities-1262.jsonl`；真实媒体在主检出 `artifacts/`，worktree 内只用合成目录；S2-D 的接续测试依赖本块真实入口 | 6 | 定向 pytest；`uv run --no-project --with playwright … v8_site_browser_check.py` 对合成小目录 `--shots <scratchpad>` 通过 | CPU + 无头浏览器 | `S4A_TESTS=PASS failed=0`、合成目录 `V8_SITE=PASS` |
| 主会话 | 4 | 二次生成、真实站点检查、通知 | — | — | gen1 验收通过（建站不等 H2） | — | `hard_parity.py generate`／`compare`；`v8_site_browser_check.py --shots` 对真实 `artifacts/newtask-v8`；`v8_oracle_browser_check.py`；P4 链路 | GL A40 席 + 本机浏览器 | `PARITY_H_H2`、`V8_SITE`、`V8_ORACLE_BROWSER` |

**共享文件归属裁决**：`hard_specs.py` 阶段 1 → S1-B、阶段 2 → S2-A、阶段 3b → S3b（三块串行、同一时间只有一个 owner）；`test_xhard0_native.py` 阶段 2 → S2-C、3b → S3b；`test_v7_seed_rule.py` 阶段 1 → S1-B、阶段 2 → S2-A；`test_v7_freeze_schema.py` 阶段 1 → S1-B、3b → S3b；`test_v6_difficulty_tiers.py` → S1-A（整个文件：改名、四档与五档断言、删 v6 seed 测试）；`test_v5_xhard_movecube.py`、`_shared/v7_specs_fixture.py`、`test_v7_candidate_pool.py` → S1-B；`v7_site.py`、`v7_subgoal_lengths.py` → S1-B；`export_eval_identities.py` → S2-B；`scripts/README.md`、`src/robomme_hard/README.md` → S3b。

**派发前核对**（每块都做）：`~/.claude/settings.json` 的 `worktree.baseRef == "head"`（本机 2026-10-01 已设）；`git status --short --ignore-submodules=dirty` 为空（` m third_party/SimpleMemVLA` 是他人在途改动，不计）；`git check-ignore -q .claude/worktrees/probe`；`git worktree list` 存档——`.claude/worktrees/v7`、`/data/hongzefu/v6-draft/*` 一律不动。

**审查轮次与冲突**：每块合并前派一个只读审查子代理（`model: "opus"`，不加 `isolation`），锚定 `REVIEW_BASE`／`REVIEW_TIP` 两个 sha，输出 `PRE_MERGE_REVIEW=PASS|FAIL base= tip= files= commits= findings=`；FAIL 用 `SendMessage` 交回原子代理续改，第二轮只复核上轮 findings 与增量，两轮仍 FAIL 则保留该分支不合入、停止依赖它的块，收尾统一报告（§2.4.5），运行中不问。两块文本冲突先判 `SCOPE=FAIL`；确需整合时派整合子代理在新 worktree 里 `git merge`、解冲突、跑验收、commit（`sub/MERGE-<n>: `），重走审查后合入。
