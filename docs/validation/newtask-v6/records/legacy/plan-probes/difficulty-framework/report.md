# V6 规划期调查 A：难度档管道与全任务四档参数总表

> 2026-09-25，只读调查，代码锚点 HEAD da77662（12.134）。由主会话代 subagent 落盘。探针脚本：本目录 `dump_configs.py`（导出 `configs_dump.json`）、`h5_frames.py`（导出 `h5_frames.json`）。

## 〇、结论先行

1. **原版有梯度的任务是 13 个，不是 16 个。** StopCube、MoveCube、InsertPeg 在 `4137a41` 与基线 `13e5151` 里 `self.difficulty` 只在 `__init__` 按 `seed % 3` 赋值、之后从不读取，三档行为完全相同；它们现在的 xhard 是 V4 新造的。
2. **现有管道从头到尾只认一个新值档，名字写死为 `"xhard"`。** `src` 里约 60 处 `== / != "xhard"` 分支、约 45 处 `decision["xhard"]` 查表；共用件 `sampling_config.XHARD_KEY / _strip_xhard / _xhard_shape`、`episode_spec.spec_kind_for`、`task_goal._unmask_pick_count`、`xhard_home_site.validate_demo_plan` 同样只认这一个键。scripts 侧 `parity/v4_specs.py` 的 `DIFFICULTY="xhard"` 是模块常量、`SEED_RULE` 只有一套、header 只有一个 `difficulty`；实跑目录 `<Task>_episode_<n>` 与推理身份键 `<task>/<episode>` 都不带难度维。
3. **两道硬上限，评估侧 1301 步比生成侧 5000 步更早撞。** 生成：录像器 `fail_safe_limit=5000` 按 `elapsed_steps` 计，含演示与 NO RECORD 步（约 330 步），v5-01 最长一局估计约 2500。评估：`scripts/evaluation.py` 写死 `max_steps=1300`（`max_steps_without_demonstration = max_steps + 2`），只计非演示步，策略实际 1301 步；V5 xhard 已有局超出（BinFill ep0 非演示 1523、PickXtimes ep3 1309）。PatternLock / RouteStick 在 V5 口径（演示 25～35 s、不改布局）下已到顶。
4. **V1 风险可控但必须重跑 144 条 V1**（本机约 3 小时一侧）。陷阱：VideoRepick 的 `elif self.difficulty == "hard"` 分支链、RouteStick 查不到档位时静默回退 easy、`test_v5_xhard_pickswing` 用 AST 锁住分支判断式原文。

## 一、难度档的定义与流转

- `utils/difficulty.py::VALID_DIFFICULTIES={"easy","medium","hard","xhard"}`，16 任务共用；`normalize_robomme_difficulty` 只做 `strip().lower()` 与白名单校验。
- 各环境类有 `config_easy/medium/hard/xhard` 汇成 `configs`；StopCube 例外，用模块常量 `_CONFIG_CURRENT`（三档同值）与 `_CONFIG_XHARD`。没传 difficulty 时按 `seed%3` 回退到原三档，新档不会被该回退选中。
- sampling_config 两块结构：`NATIVE_SAMPLING` + `_native_decision(cls)`，`_resolve_sampling_config` 依次调 `split_sampling_config` 与 `assert_native_decision`。decision 里新值有两种挂法：
  - **按难度名分键的映射**（由 `cls.configs.items()` 自动生成，如 `number_range.*`、`path_length_range.*`、VideoPlace `targets/swap.*`、BinFill `configs.*`、Unmask `bin_layout_policy.count.*`、PickHighlight `spawn_count/highlight_count.*`）：会自动长出新档键。
  - **键名为 `xhard` 的手写子树**（PickXtimes `decision.xhard.*`、VUS `decision.xhard.{swap_speed_multiplier,distractor,distractor_swap}`、MoveCube `demo_layout.xhard.center_exclusion`、VideoRepick `num_repeats_range.xhard`）：不会自动长出新档。
- 守卫 `_strip_xhard` 只剥键名恰为 `xhard` 的条目；新档若叫 `xhard2` 不会被剥掉，「只允许收窄新值档」的放行与 V0「剥掉新值键后与旧快照逐字相同」核验都会失效。各环境 `if "xhard" not in decision:` 旧快照兜底同样只认一个键。
- xhard 加入历史：`52e1fc9`（10.58）RouteStick/VUS/VideoRepick 首加；`7deae3d`（12.65）共用底座 `utils/xhard.py`；12.68～12.75 V4 逐环境建 xhard；V5 12.117～12.129 只改 xhard 的值与算法。固定模式：每环境一个 `config_xhard`、一个 `XHARD_DECISION` 子树、若干 `if self.difficulty=="xhard": self._xxx_xhard()` 独立方法。
- V5 链路：源码 → `parity/train_split_config.py extract --release newtask-v5` → `scripts/configs/newtask-v5/sampling_config.json`；`parity/v5_generation.py pipeline` 依次 `v4_specs draw`（seed offset 4e6）→ `v4_specs freeze`（10 候选、选 [0,3,6]）→ `v4_rollout run` → `report`。推理侧 `scripts/eval/v4_eval.py` → `BenchmarkEnvBuilder.from_v4_specs`，按 `<task>/<episode>` 取行。`generate_dataset_newseed.py` 与 `scripts/injection/*` 不在新值链路上，V6 不必改。

## 二、新增 3 档必须触碰的文件与符号

### src

| 文件 | 符号 | 要改什么 | 原三档风险 |
|---|---|---|---|
| `utils/difficulty.py` | `VALID_DIFFICULTIES` | 加 3 个名字；建议新增 `NEWVALUE_DIFFICULTIES` 与 `is_newvalue_difficulty()` / `newvalue_tier()` | 无 |
| `utils/sampling_config.py` | `XHARD_KEY`、`_strip_xhard`、`_xhard_shape`、`assert_native_decision` | 单一键名改为键名集合 | 中（原三档必经，但只多剥新名字） |
| `utils/episode_spec.py` | `spec_kind_for` | 族判断 | 低 |
| `utils/task_goal.py` | `_unmask_pick_count`、`num2words` | 族判断；`num2words` 只到 20 | 无 |
| `utils/xhard_home_site.py` | `validate_demo_plan` | 族判断，否则新档被当原三档拒掉 | 无 |
| `utils/unmask_swap_xhard.py` | 读 `decision["xhard"]` 与 2 处 `== "xhard"` | 按本局档位取子树 | 无 |
| `utils/unmask_distractors.py`、`unmask_distractor_sampler.py`、`xhard.py` | xhard 专用采样件 | 容量参数化 | 无 |
| `utils/subgoal_planner_func.py` | `_xhard_peg_yaw_reduction` | 不改；MoveCube/InsertPeg 新档同样置位 | 无 |
| `utils/object_generation.py` | `spawn_random_cube/target` | 新共用参数默认必须等价关闭 | 高（三档共用） |
| 各环境文件 | `config_xhard`、`configs`、`XHARD_*`、`_native_decision`、`_resolve_sampling_config`、全部分支与查表 | 每档一份 config 与子树（或参数化成档位表）；分支改族判断 | 中 |
| `RecordWrapper.py` | `fail_safe_limit`、`_video_build_filename_parts` | 冻结不改 | — |
| `episode_config_resolver.py` | `from_v4_specs` | 每档一份 specs 时不用改 | 无 |

分支点分布（`== / != "xhard"`）：VideoRepick 10，BinFill 5，VideoPlaceOrder 5，PatternLock/SwingXtimes/InsertPeg 各 4，MoveCube/RouteStick/StopCube 各 3，其余各 2，utils 6。`["xhard"]` 查表：VideoRepick 8，InsertPeg/MoveCube/StopCube 各 4。合计约 105 处。

### scripts

- `parity/v4_specs.py`：`DIFFICULTY`、`SEED_RULE`、`env_kwargs`、`_draw_one`、freeze/validate 的 header 档位比对、`DEFAULT_SAMPLING`。档位改成 CLI 参数，默认仍为 xhard。
- `parity/v4_rollout.py`：`import DIFFICULTY` 改为从 header 取档位。
- `parity/v5_generation.py`：`DEFAULT_RELEASE`、`DEMO_BAND`、`SWAP_*`、`VR_*` 口径改为按档配置（或另起 V6 版）。
- `parity/train_split_config.py`：`RELEASE_NOTES` 加 `newtask-v6`。
- `parity/train_split_runner.py`：`V4_DIFFICULTY` 身份硬校验改为按行档位查 seed 规则。
- 新建 `scripts/configs/newtask-v6/`；更新 `scripts/README.md`。
- 不改：`seed_layout.DIFFICULTY_ORDER`、`generate_dataset_newseed.py`、`injection/*`、`v4_combos.py`。

### tests

- `test_v4_xhard_{pickxtimes,swingxtimes,stopcube}`：断言 `set(CLS.configs)` 恰为 4 档。
- `test_episode_spec_recorder`：`spec_kind_for` 断言要扩。
- `test_sampling_config_split::test_snapshot_matches_source`：改指 V6 快照。
- `test_v5_xhard_pickswing`：`NATIVE_AST_GOLDEN` 锁原三档函数不许变；`test_swing_loop_branch_is_explicit` 要求判断式原文恰为 `self.difficulty == 'xhard'`，改族判断后需重写。
- `test_v5_generation_tools`、`test_episode_action_sampling`（参数化 4 档）要扩。
- 基线失败集合 46 failed / 12 errors，V6 按同口径比对。

## 三、命名候选

名字出现位置：`VALID_DIFFICULTIES`、`configs`/decision 键、spec `identity.difficulty`、drafts/specs header、h5 `setup/difficulty`、视频文件名 `<Task>_ep<n>_seed<seed>_<难度>_<目标>.mp4`、`hf_release` 归档名。任务文本与 h5 文件名不含难度名。长度：目标文本先按 180 字符截断（`__HASH__` 12 位），拼上难度名后整体再按 220 截断；难度名 ≤ 39 字符不触发第二次截断，总长 < 255。档名只能用 `[A-Za-z0-9._-]`。

| 方案 | 形式 | 优点 | 缺点 |
|---|---|---|---|
| A（建议） | `xhard2/3/4` | 成族、排序即难度序、文件名只多 1 字符 | xhard 本身不带数字 |
| B | `xhard_l2/l3/l4` | 显式「级」 | 与文件名 `_` 分隔混淆 |
| C | `xxhard/xxxhard/xxxxhard` | 直观 | 难数清，排序不等于难度序 |
| D | `insane/nightmare` 等 | 好记 | 不成族、不可排序 |

## 四、全任务四档参数总表（原三档与 `13e5151` 原文逐一核对一致）

| 环境 | 字段 | easy | medium | hard | xhard | 原版梯度 |
|---|---|---|---|---|---|---|
| PickXtimes | 颜色数 / 抓放次数 | 1 / [1,3] | 3 / [1,3] | 3 / [4,5] | 3 / [6,15]；干扰块 3、区半宽 0.25、最小中心距 0.08、精确 OBB、预算 1024 | 有 |
| StopCube | 单程步数候选 / 停止序号 | [60,80,120] / [2,5] | 同 | 同 | [60] / [6,15] | 无 |
| SwingXtimes | 颜色数 / 次数 | 1 / [1,3] | 3 / [1,2] | 3 / [3,3] | 3 / [4,10]；干扰块 3、0.08 | 有 |
| BinFill | 颜色 / 生成块 / 投入颜色 / 投入块 | 1 / [4,6] / [1,1] / [1,3] | 2 / [8,10] / [1,2] / [2,4] | 3 / [10,12] / [2,3] / [3,5] | 3 / [12,12] / [2,3] / [5,7]；杂乱布局、同色团 ≤3 | 有 |
| VideoUnmaskSwap | 容器 / 交换 / 抓取 | 3 / [1,2] / [1,2] | 4 / [1,2] / [1,1] | 4 / [2,3] / [2,2] | 4 / [8,12] / 3；交换 ×1.5 速、外环 10 容器同窗交换 | 有 |
| VideoUnmask | 容器 / 抓取 | 3 / 1 | 5 / 1 | 15 / 2 | 8 / 3；环带干扰容器 15 | 有 |
| ButtonUnmaskSwap | 容器 / 交换 / 抓取 | 同 VUS | 同 VUS | 同 VUS | 4 / [6,8] / 3；交换段计入评估步数 | 有 |
| ButtonUnmask | 容器 / 抓取 | 3 / 1 | 5 / 1 | 15 / 2 | 8 / 3；干扰容器 14 | 有 |
| VideoRepick | 方块 / 交换 / 抓取次数 | 3 / [1,2] / [1,4) | 3 / [2,3] / 同 | 聚簇 / 0 / 同 | 6 / [8,12] / [4,7)；中心距 0.12、最近 3 搭档、按钮入障碍 | 有 |
| VideoPlaceButton | 颜色 / 目标台 / 交换 / 追加放置 | 1 / 3 / F / F | 3 / 4 / F / F | 3 / 4 / T / F | 与 hard 同；演示 2 块、放回原位 | 有 |
| VideoPlaceOrder | 颜色 / 目标台 / 交换 | 1 / 4 / F | 3 / 4 / F | 3 / 4 / T | 与 hard 同；演示 2 块、放回原位 | 有 |
| PickHighlight | 方块 / 高亮 | 3 / 1 | 4 / 2 | 6 / 3 | [8,10] / [5,7]；HSV 任意色 | 有 |
| InsertPeg | 杆数 / yaw 半宽 | 3 / 45° | 同 | 同 | 4 / 180°；间隔约束 | 无 |
| MoveCube | 杆 yaw 范围 | span π/2 | 同 | 同 | span 2π；桌心 R=0.05 禁区 | 无 |
| PatternLock | 网格 / 节点数 | 3 / [2,4] | 4 / [3,5] | 5 / [4,8] | 5 / 25（5×5 上限） | 有 |
| RouteStick | 段数 L / backtrack | [2,3] / F | [4,5] / F | [4,7] / T | [15,21] / T | 有 |

梯度不单调的字段：Unmask 两个的容器数 hard 15 → xhard 8；VideoRepick hard 是聚簇、0 交换的特例；VideoPlace 两个 xhard 的 config 与 hard 相同，难度全在子树里。

## 五、硬上限

四道约束：生成 fail-safe 5000（计 `elapsed_steps`，含演示与 NO RECORD）；评估 1300（只计非演示步）；演示带 750～1050 帧（只约束 PatternLock/RouteStick）；`max_episode_steps` 未设置。h5 只记非 NO RECORD 步；RouteStick 例：elapsed ≈ 100·L + 327，h5 = 100·L。

v5-01 实测（h5 步数 / 演示帧 / 非演示）：PickXtimes（num 6/7/7）1017/1309/1122，演示 0，ep3 超 1301；StopCube 428/846/553；SwingXtimes（5/7/8）649/826/926；BinFill（ep0 投入 7）1523/1187/956，ep0 超；VUS（交换 10/10/9）约 800，演示约 390；VideoUnmask 约 470，演示 66；BUS（8/7/8）约 700；ButtonUnmask 约 520；VideoRepick（交换 8/12/9，抓 4/5/4）1324/1696/1346，演示 655/851/699；VideoPlaceButton 约 1570，演示约 1370；VideoPlaceOrder（访问 5/8/6）1700/2171/1832，演示 1520/1952/1606；PickHighlight（高亮 6/5/6）1032/872/1060；InsertPeg 约 480；MoveCube 约 280～480；PatternLock 约 1640～1744，演示 818～872；RouteStick（L 21/17/16）2100/1700/1600。

| 环境 | 单位代价 | fail-safe 5000 允许 | 评估 1301 允许 | 其他 |
|---|---|---|---|---|
| PickXtimes | 约 138～150 步/次 | num ≲ 32 | num ≲ 8（xhard 已大半超） | num > 20 文本退回数字 |
| SwingXtimes | 约 92 步/次 | num ≲ 50 | num ≲ 12 | |
| BinFill | 约 170～200 步/块 | ≲ 24 块 | ≲ 6 块（xhard 已部分超） | |
| PickHighlight | 约 170 步/次 | 高亮 ≲ 28 | 高亮 ≲ 7（贴线） | |
| VUS | 交换 33 步（计演示），抓取约 135 步 | 交换 ≲ 120 | 交换不计；抓取 ≲ 9 | |
| BUS | 同上，交换计入评估 | 交换 ≲ 120 | 交换 ≲ 25 | |
| Unmask 两个 | 抓取约 150 步 | 抓取 ≲ 30 | 抓取 ≲ 8 | |
| VideoRepick | 交换约 49 步，抓取约 176 步 | | 抓取 ≲ 7 | |
| VideoPlace 两个 | 访问约 200～220 步 | 访问 ≲ 20 | 不受限 | |
| PatternLock | 每段约 35 帧 | ≲ 65 段 | ≲ 37 段 | 演示带 ⇒ ≲ 30 段；5×5 上限 25 节点 |
| RouteStick | 每段 50 帧 | L ≤ 46 | L ≤ 26 | 演示带 ⇒ L ≤ 21，已到顶 |

守住评估 1301 就一定守得住 5000。

## 六、抽签与快照

- drafts header 为 `HEADER_KEYS`（schema、run_id、difficulty、sampling_config 全文与 sha、源码指纹、runtime、seed_rule、recovery_rule、tasks）；specs 1 行 header + 160 行，header 另含 `drafts_sha256`、`select_indices=[0,3,6]`、`per_env`、`identity_sha256`；`spec_kind="native-newvalue/1"`。
- `SEED_RULE = 4_000_000 + env_code·100_000 + episode·100 + attempt`。
- 实跑：`episodes/<Task>_episode_<n>/{hdf5_files/<Task>_ep<n>_seed<seed>.h5, videos, rng_trace.json, spec_replay.json}`。v5-01 抽签共尝试 188 次（VideoPlaceOrder 23 次），48 局约 32 GB，总墙钟约 25 分钟。
- 单档假设 6 条：`DIFFICULTY` 模块常量被多处 import；header 单档位、身份键不含难度；只有一套 seed 规则；实跑目录不带难度；`from_v4_specs` 以 episode 号为键；报告口径为 xhard 专属常量。最省改动：每档一套独立产物，`DIFFICULTY` 改参数，seed offset 按档区分。
- 规模：13 环境 × 3 档 = 39 格，390 候选、117 正式局，约 78～120 GB；16 环境则 480 / 144；若 xhard 也重生再加 160 / 48。

## 七、V1 风险点

a. 守卫改写：原三档快照无新键，扩大剥离集合不影响。b. VideoRepick 分支链：族判断必须放在 `elif self.difficulty == "hard"` 与 `!= "hard"` 之前。c. RouteStick 静默回退：缺键应改抛错。d. `object_generation` 共用参数默认关闭，`NATIVE_SPEC_GOLDEN` 照跑。e. 按 `cls.configs.items()` 派生的 decision 只多出键，快照字节会变。f. AST 锁不许变。g. 录像器 `git diff --quiet` 核验。h. 原三档路径不得新增/挪动抽样。i. xhard 工具参数化后 xhard 取值不变需回注闸门。V1 判定行：`H5_PARITY pair=base.B|v6.B compared=144 sha_equal=144 field_mismatch=0`。

## 八、待决项（调查方建议）

Q1 范围 13 或 16（建议 13）；Q2 命名（建议 `xhard2/3/4`）；Q3 xhard 是否冻结（建议冻结+回注闸门）；Q4 PatternLock/RouteStick 放宽演示带 / 换轴 / 改布局；Q5 评估 1300 预算：封顶 / 新档另设 max_steps / 接受超出；Q6 fail-safe 5000 封顶、录像器冻结；Q7 seed 每档独立 offset（6e6/8e6/10e6）；Q8 每档仍 10 候选 + 3 正式局；Q9 每档独立一套产物；Q10 低 reset 率环境新档是否允许改布局；Q11 每档所有已加码字段单调不减。
