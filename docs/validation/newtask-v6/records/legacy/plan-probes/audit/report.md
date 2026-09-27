# NEWTASK_RELEASE_V6_PLAN.md 全文审计报告

> 2026-09-25，只读审计（HEAD 0b1d542 / 12.139；src、scripts、tests 自计划锚点 da77662 以来零改动）。未改任何 git 跟踪文件，未用 greatlakes。
> 本文 = 汇总（本节）+ 主审表 + 四段逐条核对表（A 头部/口径/冻结/runbook；B 规划期数字重跑；C 三档数值/单调性/键名；D h5 与模拟器 reset 实测）。

## 汇总一：必须改计划的条目（20 条）

| # | 章节 | 问题 | 证据 |
|---|---|---|---|
| 1 | 1.1 口径 5 / N7 / 3.2 | 口径 5「单调不减 + 至少一字段严格」与 N7/3.2「所有加码字段严格」矛盾；按 N7 计划自己的表 ≥10 字段违例，TIER_MONOTONE 必 FAIL | C 二 |
| 2 | 2.9 PH | 用户点名「干扰数量」，但干扰均值 3/3/3.5/3/3：hard=x1、x2 超 xhard、x3 回落（spawn/pick 独立抽） | C 二；D 三 实测分布印证 |
| 3 | 2.10 VPB/VPO | 「演示放置次数」口径错（原三档本有 goal_site 放置段，放回只换终点）；「放回」x1→x2 倒退；VPO x2 v 均值 2.5 < hard 3 | C 一、二 |
| 4 | 2.10 / 2.0 | `validate_demo_plan` 也会拒 (k=2, 不放回)；原场景只有一个 goal_site，两块去处未定义 | C 三 |
| 5 | 第二部分一 | decision 子树键名多处与源码不符：`min_center_gap`→`min_center_dist_m`；`corner_bias` 已删；`distractor_count` 非 decision 键；`hsv_floor_color`/`exact_obb` 不存在；`cube_range`→`cube_count_range`；`partner_policy`→`swap_plan.partner_rule`；BinFill 在 `decision.configs.<tier>.{layout_mode,color_mix}` | C 三 |
| 6 | 2.0 tests | `test_v4_xhard_stopcube` 不应改 7 档；漏 `test_operand_scope.py`、`test_episode_action_sampling.py` 4 档写法、`test_v4_specs.py::test_seed_rule_disjoint_from_existing_layouts` | C 三；主审 |
| 7 | 2.3 | 「干扰总数 > hard 的 15 个容器」对 BU xhard1 不成立（8+7=15） | C 一 |
| 8 | 2.5 / M9 | VR xhard1/xhard2 reset 成功率 ≈0.9/≈0.75 无出处，补测 N=4 0.625、N=5 0.629；「4/5 块可行图更密」不成立（可行度 1.29/1.46 < 1.54） | B13 |
| 9 | 2.4 | 算术错：65+33×6+177×3−40 = 754 不是 794；xhard 同式 820，「远低于」偏强 | B21 |
| 10 | 2.4 | 「外环可行率随干扰减少只会更高」无出处，已有 BUS c10/14/18 = 0.983/0.996/0.986 不单调；4/6/8 未测 | B19 |
| 11 | 1.4 M3 | 「未被改动的 9 个环境」应为 10 个 | B32 |
| 12 | 1.3 第 3 点 | 「极差 0.54、p=0.967、撤销 0」拼了两个口径：全部布局下撤销 0.002/0.050，撤销 0 仅 G 连通子集 | B7 |
| 13 | 三 runbook 第 1 条 | `git diff --quiet 13e5151 -- RecordWrapper.py` 实测返回 1（12.76 的 5000 改动在 13e5151 之后），应改 HEAD/da77662 | A 6a |
| 14 | 三 runbook | `v4_rollout.py probe` 子命令不存在；实际 `scripts/parity/v4_demo_probe.py --task --difficulty --n --out` | A 6c |
| 15 | 3.3 | commit 编号 12.136～12.139 已被计划文档自身占用，S1～S7 须顺延 | A 7d |
| 16 | 3.1 / 3.2 X0 / 2.0 v4_specs | v6-01 xhard 档混装 v5-01 回注行（4e6）与重冻行（6e6）；`v4_specs` header 只封一条 seed_rule 且比对 source_fingerprint/sampling_config，放不进同一份规格，计划未说封装方式 | A 9c；主审 |
| 17 | 三 runbook pytest / 3.2 LIGHTWEIGHT | 缺 `-m 'not gpu and not slow'`（S0 基线口径）；原样全量 300 s 超时只跑 ~5% | A 6b |
| 18 | 1.5 | 「演示 25～35 s 不变」只对 xhard 成立（xhard PL 27.3～29.1 s、RS 26.7～35.0 s 实测在带内）；PL/RS 新档按设计 9～25 s，`v5_generation.DEMO_BAND=(750,1050)` 会全部判越界，需按档豁免 | A 4；D 四 |
| 19 | 1.3 / 2.6 / 风险 #4 | 12.139 已把 2.6 改为圆环版 120/144，但 1.3 结论、2.6 验收行、风险 #4 仍写第一版 118/144 | A 附 |
| 20 | 2.11 | 「xhard3 最长约 735 帧」是均值口径；按实测段均值上界 36.3 帧约 763 帧（25.4 s），单段最大 52～56 帧 | B27；D |

## 汇总二：建议改（摘要）

- 头部代码锚点写成「da77662，此后到 12.139 只改文档」；依赖锚点注明 sha256（A）。
- 口径 2 补 `run_example.py`、`dataset_replay.py`，写明官方副本路径 `artifacts/train-parity/local-smoke-01/official-src/scripts/`（A）。
- 口径 4「self.difficulty 从不读取」改「原三档之间无取值分支」（三文件都读 `== "xhard"`）（A）。
- 「约 105 处 xhard」写明口径：`==/!=` 61 行 + `["xhard"]` 41 行 ≈102～106；`grep '"xhard"'` 为 130 行；风险 #1「计数归零」给出可执行正则（A、B、C）。
- `generate_dataset_newseed.py` 的 `extract_native_sampling/validate_sampling_config` 只认 config_xhard，「不动」需加前提（A）。
- runbook 生成命令：`--tiers` 为新参数、另有 `--draw-workers`、补 `--official-root`、先 `mkdir -p`；补写 V1 run 步（`run --subset` 不存在）（A）。
- N9 与 CLAUDE.md 对齐：workflow 内 `agent()` 用 sonnet（A）。
- 授权边界引用用户 2026-09-21 原话，AGENTS.md 规则 11 字面仍「逐个批准」待用户确认（A）。
- 风险 #7 峰值按 230～270 GB 估（生成 80～115 + V1 两侧 ~98 + worktree ~56），/data 余 2.4 TB 足够（A）。
- V0 diff 范围补 `config_native`（A）。
- `spec_kind_for` 对 xhard1/2/3 现返回 `native-parity/1`；是否升 `native-newvalue/2` 以拒 v5-01 旧规格需写明（主审）。
- S5 数字来自「(max,sum) 贪心不重排」，计划描述的「重排 ≤20 次」补测极差≤1 达 VUS 100%/BUS 99.94%，验收 0.89 过松（B）。
- 零可行搭档槽基线统一（1.3 的 28% vs M7 的 31.7%）；2.2 外环 ≥99%/≥98% 注明是 V5 内环口径（B）。
- 2.10 VPO 二项分布 p 统一（0.48→96.47%，0.483→96.7%，0.50→97.9%）（B）。
- 2.3「pick 最坏 125 / put down 52」改为「xhard 实测最大 125/52（n=9）」，B 段另从 h5 统计到 126/53（B、D）。
- 风险 #2 写死 60 与待决 M4 抵触，改「按 M4 答复」（B）。
- 死代码 `_compute_dynamic_swap_candidates` 等 VR 也有（B、C）。
- PickXtimes x3 [7,12]、SwingXtimes x3 [5,8] 下界高于 xhard 下界（6、4）；VU/BU 内环容器 15→8 挂待决或声明非加码字段；补 VUS/BUS 新档外环含 cube 数、BinFill 新档投入色；VPO v 上界走 decision 新键；VUS 外环为方环；MoveCube「0.040 m²」是候选中心框口径（C）。
- 2.8 补 SwingXtimes reset 成功率：xhard 与三新档实测均 96.0%（失败 seed 相同，圆盘采样失败，与干扰数无关），抽签上限按 0.96 估（D）。

## 汇总三：已实测 / 已核实通过

- 依赖锚点 sha256、前置文档与 v5-01 数字（160 候选/48 正式）、L1(a)/L4(b)/L51/V5 口径引用、`fail_safe_limit=5000`、五入口、`evaluation.py`/`run_example.py`/`dataset_replay.py` 与上游逐字节相同、V1=144 与 13e5151、FROZEN_FILES 判据原文、seed 偏移四段互不重叠且不碰 4e6 与 train/test/val/heldout、v4_eval 兼容新档名、`/data` 余 2.4 TB（A、主审）。
- 16 环境 hard/xhard 全部数值与源码、V5 快照一致（16/16 逐字）；计划点名符号大多存在（C）。
- 1.3/1.4 规划期数字：VUS 参与频率、bin_3 不发起 50%、槽对可行率、S1/S1n/S5、G 连通率 66.5%/95.4%、VR 40%/1.54/41%/50.3%/100%/96.7%、外环 5.6/3.6、28%/44%、O4、M7(b) 31.7→15.0、PH N=8/9/10、VPB 81.8%/VPO 50.0%、PL DFS、RS 50 帧、BinFill 100%、规模 43/430/129/36——固定种子重跑**逐位复现**（B）。
- 模拟器实测（本机 GPU 1）：「xhard 已有超 1301 的局」成立（BinFill ep0 执行 1523、PickXtimes ep3 1309；评估预算只数执行段、上限 1302；hard 400 局 0 超）；PH reset xhard1 99.9% / xhard2 98.7% / xhard3 96.2% / xhard 89.4%（各 1000 次），N=8/9/10 = 98.7/92.9/73.0%；PH 干扰分布与计划表一致；BinFill 四档 200/200；PickXtimes 干扰 1/2/3 全 200/200；SwingXtimes 各 192/200（D）。

---

# 主审表

## 主审已核条目

| 条目 | 计划原文摘要 | 核实方法 | 结果 | 备注 |
|---|---|---|---|---|
| 五入口 | scripts/ 顶层五入口冻结 | ls scripts/*.py | 一致 | dataset_replay、evaluation、generate_dataset_newseed、run_example、seed_layout 共 5 个 |
| seed 偏移 | xhard 重冻 6e6、xhard1 8e6、xhard2 10e6、xhard3 12e6 | 读 v4_specs.SEED_RULE、seed_layout.LAYOUTS | 与数据集 seed 不撞，但有结构问题 | 公式 offset+env_code×1e5+ep×100+attempt，每段跨度约 1.6e6，间隔 2e6 不重叠；V5=4e6，heldout 最大约 3.1e6。但 tests/lightweight/test_v5_xhard_obb_fix.py 离线扫描已用 5e6、6e6 起的 seed（只是测试，不撞数据集） |
| **seed_rule 单一 header** | xhard 档 = 12 环境 v5-01 行回注 + 4 环境 6e6 重冻 | v4_specs.py 的 header 校验 `header["seed_rule"] != SEED_RULE` | **不一致（必须改）** | 同一份 v6-01/xhard/specs.jsonl 里混了 4e6 与 6e6 两种 seed 规则，现有 header 只能封存一条 seed_rule；计划需说明是按环境记 seed_rule 还是把 xhard 回注行与重冻行拆成两份快照 |
| 测试清单遗漏 | 2.0 tests 行 | grep tests | **遗漏（建议改）** | tests/lightweight/test_v4_specs.py::test_seed_rule_disjoint_from_existing_layouts 只校 V4 单段，新增 4 个偏移后要扩展，计划 tests 行未列 |
| spec_kind | 2.0 把 spec_kind_for 改成族判断 | 读 utils/episode_spec.py | 部分一致（建议改） | 现状只有字面 `== "xhard"` 才返回 `native-newvalue/1`，xhard1/2/3 不改会被标成 `native-parity/1`；计划未说要不要升 `native-newvalue/2` 以区分 VUS/BUS/VR/MoveCube 重冻后 v5-01 旧规格（旧规格喂给 V6 代码时现在只会靠 decision 归因报错，不会在 kind 层面拒绝） |
| v4_eval 兼容 | 3.1「推理 v4_eval 默认预算不变」 | 读 scripts/eval/v4_eval.py、episode_config_resolver.from_v4_specs | 一致 | difficulty 从规格行取、不写死档名；`--max-steps` 默认 1300 |
| seed_layout.DIFFICULTY_ORDER | 2.0「不动」 | 读 scripts/seed_layout.py | 一致 | 值为 ("easy","medium","hard")，只服务原三档数据集，不动合理 |
| 磁盘 | 风险 #7 80～100 GB | df -h /data | 余量够 | /data 剩 2.4T（已用 82%） |



# V6 计划审计 · A 段：头部锚点、冻结口径、runbook 与链路命令

审计对象：根目录 `NEWTASK_RELEASE_V6_PLAN.md`（审计期间 HEAD 由 `e1755f9`（12.138）前进到 `0b1d542`（12.139，只改计划文件），结论以 `0b1d542` 为准）。
只读审计，未改任何 git 跟踪文件；全部命令输出在本目录 `sec_A_*.log`。

| 条目 | 计划原文摘要 | 核实方法 | 结果 | 备注 |
|---|---|---|---|---|
| 1a 代码锚点 | 「代码锚点 HEAD `da77662`（12.134）」 | `git log`、`git diff --stat da77662 HEAD`（sec_A_item1.log） | 不一致（文字过时，代码内容一致） | 现 HEAD `0b1d542`（12.139）。`da77662..HEAD` 只动了 `NEWTASK_RELEASE_V6_PLAN.md` 与 `docs/greatlakes.md`，`src/`、`scripts/`、`tests/`、`uv.lock`、`pyproject.toml` 零改动，所以作为「代码锚点」仍然有效；但应写明「代码锚点 = `da77662`，计划文档本身在 12.135～12.139」，否则读者会以为 HEAD 就是 da77662 |
| 1b 依赖锚点 | `uv.lock ff0ffd847a55…` / `pyproject.toml d03537d6c77a…` | `sha256sum` 与 `git hash-object` 对照 | 一致 | 两者是**文件 sha256**（git blob 分别是 `fc274bd1…`、`11d02c57…`），与当前工作区、`da77662`、HEAD 三处完全一致。建议注明「sha256」 |
| 1c 前置文档路径 | V5 计划、V5 总报告、`v5-01/specs.jsonl`、`rollout/run1/` | `ls`、逐行解析 specs | 一致 | 四个路径都存在；specs.jsonl 161 行 = 1 header + 160 候选；header `per_env` 每环境 `selected [0,3,6]` ⇒ 48 正式局；`run1/episodes/` 48 个目录，`summary.json` 16 环境各 ok 3/3 |
| 1d V5 L1(a) / L4(b) | 「L1(a)（新值流允许原地移位）、L4(b)（共用采样函数各环境各加显式参数）」 | V5 计划 1.4 表 L1、L4 行 | 一致 | L1 结论「(a)：N5 只保护原三档，xhard 流允许原地移位」；L4 结论「(b)：各环境各加各的显式参数」 |
| 1e V5 口径 1/2/10/12/14 | V6 口径 1←V5 1/12；口径 2←V5 2；口径 6 引「V5 口径 10」；口径 9←V5 12；口径 10←V5 14 | V5 计划 1.1 表（sec_A_item1_v5refs.log） | 基本一致，口径 2 有收窄 | V5 口径 1 = 只改 xhard、原三档逐位、V1 硬闸门；12 = 16×9 V1 + 一次生成；10 = VR 全部方块参与交换；14 = 待决不自填、取整自决。**V5 口径 2 原文是 `evaluation.py`、`run_example.py`、`dataset_replay.py` 三个文件与上游逐字节相同**，V6 口径 2 与开头声明只写了 `evaluation.py`，漏了另外两个 |
| 1f V5 L51 | 「L51 VR 不扩区」 | V5 计划 1.4 L47～L51 组（VideoRepick 小节） | 一致 | L51「是否改区域或按钮，让方块铺满更多画面」→「不改」，属 VR 组 |
| 2a fail_safe_limit | 录像器冻结（`fail_safe_limit=5000`） | grep `RecordWrapper.py` | 一致 | `RobommeRecordWrapper` 的 failsafe 段 `fail_safe_limit = 5000`；来自 `749158e`（12.76，V4 用户授权 2000→5000） |
| 2b src 改动授权 | 「`src/robomme/` 改动沿 V4/V5：免逐项事前批准，每步收尾出 md 报告」 | 对照 MEMORY `src-robomme-changes-need-approval.md` 与 `AGENTS.md` 规则 11 | 与 MEMORY 一致；**与 AGENTS.md 规则 11 字面冲突** | MEMORY：2026-09-21 起免逐项批准、改完出报告；录像器仍冻结，仅 5000 例外。但仓库 `AGENTS.md` 规则 11 仍写「任何改动和覆盖都必须由用户逐个批准」「计划文档里写了改动清单不等于批准」，而 `CLAUDE.md` 声明两者冲突时以 AGENTS.md 为准。计划应引用用户 2026-09-21 原话作授权依据，并提示 AGENTS.md 规则 11 待用户更新 |
| 3a 口径 2 `evaluation.py` 与上游逐字节相同 | 「录像器、`evaluation.py`、五入口冻结」 | sha256 与 `git diff --quiet` 对照三个来源（sec_A_item3_eval.log） | 一致 | `scripts/evaluation.py` sha256 `9ffa32d9…` 与官方副本 `artifacts/train-parity/local-smoke-01/official-src/scripts/evaluation.py`（V5 runbook 的 `--official-root`，被 `.gitignore` 忽略）逐字节相同，与 `origin/dataset-gen-NewSeed`、`13e5151` 也零 diff；`run_example.py`、`dataset_replay.py` 同样三处一致。计划应写明「官方副本」指哪个路径 |
| 3b V5 FROZEN_FILES 判据原文 | 「V5 FROZEN_FILES 判据原文保留」 | V5 计划 3.2 表 | 一致（找到原文） | V5 原文：「`git diff --quiet` 录像器；`scripts/evaluation.py` 与官方副本 diff；`ls -1 scripts/*.py` 恰好五个」，判定行 `RECORDER_FROZEN=PASS EVAL_PY_UPSTREAM=PASS ENTRIES=5`；V5 runbook 用的是 `git diff --quiet HEAD`；V5 总报告实写「录像器与 12.116 无差异」 |
| 3c 五入口 | 「`scripts/` 顶层五入口」 | `ls -1 scripts/*.py` | 一致 | 恰 5 个：`dataset_replay.py`、`evaluation.py`、`generate_dataset_newseed.py`、`run_example.py`、`seed_layout.py`，与 AGENTS.md 规则 12 名单一致 |
| 3d 口径 4 三环境不读 difficulty | 「StopCube、MoveCube、InsertPeg 原三档 `self.difficulty` 只在 `__init__` 赋值从不读取」「三档逐字同值」 | grep + 导入类比对（sec_A_item3_k4*.log） | 实质一致，措辞不准 | `MoveCube`/`InsertPeg` 的 `configs` 里 easy/medium/hard 指向**同一个** `config_native` 对象，StopCube 在模块级 `NATIVE_SAMPLING` 与 `configs` 里三档同值；源码注释明写「三档同值，difficulty 只在 xhard 生效」。但 `self.difficulty` 并非「从不读取」：三个文件都有 `self.difficulty == "xhard"` 的读取（MoveCube 3 处、InsertPeg 4 处、StopCube 2 处）。应改为「原三档之间没有任何取值分支」 |
| 3e 口径 9 V1 = 16×9 与 `13e5151` | V1 144 条与 `13e5151` 逐位比 | `git cat-file`、`git log -1 13e5151`、V5 总报告第四节 | 一致 | `13e5151` 是 commit（12.63 V4 计划，2026-09-22），是 HEAD 祖先；V5 报告写明基线 = `13e5151`，身份 = `scripts/configs/newtask-v3/subset_manifest.json`（16 任务 × easy/medium/hard × 3 局 = 144），`H5_PARITY compared=144 sha_equal=144`。注意「16×9」= 每任务 9 局（3 档×3），不是 9 档 |
| 3f 口径 11 字面判断现状 | 「所有 `== "xhard"` 字面判断改为族判断」；1.3「src 约 105 处、共用件 5 处、scripts 单一 DIFFICULTY/SEED_RULE/身份键」 | grep 计数（sec_A_item3_k11*.log） | 数字偏低 | 族判断函数 `is_newvalue_difficulty`/`newvalue_tier` 当前不存在（预期）。实测：src 带引号 `"xhard"` 共 **143 行**（16 个环境文件 134 行，`utils/` 7 个文件 9 行），其中 `== / != "xhard"` 比较 61 行；scripts 14 行（`v4_specs.DIFFICULTY`、`v4_demo_probe --difficulty` 默认、`generate_dataset_newseed.extract_native_sampling`、`v4_combos`、`injection/*` 等）。风险 #1 的「grep 计数归零」应以 143 行为起点 |
| 4 1.5 表出处 | 「演示 25～35 s、`evaluation.py` 判据、L51 VR 不扩区、录像器冻结 不变」 | V5 计划 口径 9、L35/L37、L51 | 出处存在，但与新档自相矛盾 | 「25～35 s」出自 V5 口径 9（750～1050 帧），当时只约束 xhard。V6 自己的新档数字低于 25 s：PatternLock xhard3「最长约 735 帧」、RouteStick xhard3「执行段 ≤ 700」。应改为「25～35 s 只约束 xhard，新档不设时长下限」 |
| 5a `train_split_config.py extract --release newtask-v6` | 3.1 链路第一跳 | `--help`（sec_A_item5_help.log） | 当前不支持（计划内的 S1 改动） | `--release` 可选值只有 `{newtask-v4,newtask-v5}`，由 `RELEASE_NOTES` 决定；2.0 已列「`RELEASE_NOTES` 加 `newtask-v6`」，一致 |
| 5b `v4_specs draw --difficulty <tier>` | 按档抽签 | `v4_specs.py draw --help` | 当前不支持（计划内的 S1 改动） | draw 参数：`--run-id --tasks --sampling-config --candidates-per-env --max-reset-attempts --workers --gpus --out`，没有 `--difficulty`；档位写死在模块常量 `DIFFICULTY = "xhard"`。2.0 已列「档位改 CLI 参数」 |
| 5c `freeze` | 冻结 | `v4_specs.py freeze --help` | 存在 | `--drafts --sampling-config --select --candidates-per-env --out`；`_check_sources` 按 header 比对 `seed_rule`、`source_fingerprint`、每任务 `sampling_config`（见 9c 的冲突） |
| 5d `v4_rollout run` | 实跑 | `v4_rollout.py run --help` | 存在 | `--specs --label --tasks --official-root --identities-from --workers --gpu --output`；`--official-root` 必填，计划未写 |
| 5e `v4_eval` | 「推理 `v4_eval` 默认预算不变」 | `find`、`scripts/eval/v4_eval.py --help`（sec_A_item5_v4eval.log） | 一致（路径未写全） | 入口是 `scripts/eval/v4_eval.py`（`scripts/eval/` 子目录，不在 `scripts/parity/`）；参数 `--specs --tasks --action-space --max-steps（默认口径 1300）--model-seed --limit-per-task --run-id --join-results --out`；档位随 specs header 走，不需要新参数。建议写全路径 |
| 6a runbook 第 1 条 | `git diff --quiet 13e5151 -- …/RecordWrapper.py && ls -1 scripts/*.py \| wc -l` | 原样执行（sec_A_item6_cmd1.log） | **不一致：命令失败** | `git diff --quiet 13e5151` 返回 1，`&&` 后半不执行、没有输出。原因：`13e5151`（12.63）早于 `749158e`（12.76 把 2000 改成 5000），两者之间录像器恰好差这 5 行。改 `HEAD`（AGENTS.md 规则 11 与 V5 runbook 的写法）或 `749158e`/`f5b6a17`（12.116，V5 报告口径）即可通过；单独执行 `ls -1 scripts/*.py \| wc -l` = 5 |
| 6b runbook pytest | `uv run python -m pytest tests/lightweight/ -q` | `--collect-only`；全量带 `timeout 300`（sec_A_item6_collect.log、sec_A_item6_pytest_full.log） | 不一致（口径与 S0 基线不同） | 可收集 1506 条；V5 S0 基线（`artifacts/newtask-v5/s0/lightweight_baseline.log`）是 `-m 'not gpu and not slow'` 口径（74 条被排除，结果 46 failed / 840 passed / 22 skipped / 12 errors，135.9 s），现在该口径收集 1427/1506。V6 runbook 漏了 `-m 'not gpu and not slow'` 和 `--no-sync`/`timeout`，按原样跑会把 GPU/慢测也跑进去：按原样（不带 marker）全量跑，`timeout 300` 到点被杀（rc=143，只跑到约 5%，且同机另有两份轻量测试在跑、负载偏高），没能核对失败集合。「46 failed / 12 errors」与 V5 S0 数字一致，但必须用同一 marker 口径比较 |
| 6c `v4_rollout.py probe --env --difficulty --episodes` | 单环境演示探针 | `v4_rollout.py probe --help` | **不一致：子命令不存在** | 报错 `invalid choice: 'probe' (choose from 'run', 'compare')`。现有探针入口是 `scripts/parity/v4_demo_probe.py`：`--task`（不是 `--env`）、`--difficulty`（已有，默认 xhard）、`--n`（不是 `--episodes`）、`--out` 必填、`--sampling-config`、`--seeds`、`--gpu`；V5 runbook 就是用它 |
| 6d `train_split_parity.py compare --run … --pair base/B:v6/B` | V1 判定 | `compare --help` | 一致 | `--run` 可重复、支持 `<标签>=<目录>`，`--pair LEFT:RIGHT` 支持 `<标签>/<路径>`，与 V5 报告实际用的命令同形。但 runbook 缺 V1 **run** 那一步；V5 runbook 写的 `run --subset 16x9` 在当前 `run --help` 里也不存在（实际参数为 `--manifest/--env/--paths/--workers/--gpus/--output` 等），V6 补写时不要照抄 |
| 6e `v6_generation.py pipeline --run-id --tiers --workers` | 生成 | 对照 `v5_generation.py pipeline --help` | 预期不存在；参数部分可沿用 | `v6_generation.py` 不存在（S1 新建，预期）。`v5_generation pipeline` 有 `--run-id --release --label --tasks --candidates-per-env --max-reset-attempts --select --draw-workers --draw-gpus --workers --rollout-gpu --official-root --resume --dry-run`；**没有 `--tiers`**；`--workers` 只管实跑，抽签并行另是 `--draw-workers`。另外 runbook 的日志 `tee artifacts/newtask-v6/v6-01/run.log` 需要目录先存在（tee 不会建目录），建议先 `mkdir -p` |
| 7a V0 | 「`NATIVE_SAMPLING` 键零 diff」「`envs=16`」 | grep | 一致 | 16 个环境文件都有模块级 `NATIVE_SAMPLING`；有 `config_easy` 的是 13 个（StopCube/MoveCube/InsertPeg 用 `config_native`），V0 的 `git diff` 范围应写成「`config_easy/medium/hard` 或 `config_native`」。判定行与 V5 3.2 原文同名，检查器当前不存在（V5 也是手工/单测实现） |
| 7b FROZEN_FILES 判定行 | `RECORDER_FROZEN=PASS EVAL_PY_UPSTREAM=PASS ENTRIES=5` | 对照 V5 3.2 | 一致 | 与 V5 原文逐字相同；但它依赖的 runbook 第 1 条基线提交写错（见 6a） |
| 7c TIER_MONOTONE | 新判据 | grep | 当前不存在（预期） | 属 S2「单调性检查器」 |
| 7d commit 编号 | S1=12.136，S2=12.137～12.139 … S7=12.152 | `git log --all --oneline` | **不一致：已冲突** | 12.136（`215531e`）、12.137（`1bb4190`）、12.138（`e1755f9`）、12.139（`0b1d542`，审计期间新增）都已被占用。S1 起至少要从 12.140 开始整体顺延（S7 变 12.156 左右），或只写「顺延编号」不写死 |
| 8a 红线 N9 | 「subagent 一律 opus、并行不设上限、workflow 需逐次审批」 | 对照全局 CLAUDE.md 与项目 CLAUDE.md 第 3 节 | 部分冲突 | CLAUDE.md：**用 Agent 工具派单个 subagent 强制 opus**；**Workflow 脚本里 `agent()` 默认且只能 sonnet**，只有收尾综合/制定计划的 agent 可用 opus，每个 workflow 累计 ≤3 次。N9「一律 opus」若 S3 走 workflow 即违规；应改为「Agent 工具 subagent 用 opus；workflow 内 `agent()` 用 sonnet（总结/计划 ≤3 次 opus）；`model` 不得省略」 |
| 8b N2/N8/N10 | 冻结、禁硬编码行号、tmux + Monitor | 对照 AGENTS.md 规则 4/5/11/12 | 一致 | 计划正文 grep 没有 `file.py:行号` 形式；tmux 模板带 `set -o pipefail`、`PYTHONUNBUFFERED=1`、`tee`、`EXIT_CODE=`，与规则 4 一致 |
| 8c N1/N3/N5 | 原三档不动、待决不自填、共用函数新参数默认关闭 | 对照 V5 N 系列 | 一致 | 与 V5 口径 1/14 和 L4(b) 同义 |
| 9a 「不动」清单符号存在 | `seed_layout.DIFFICULTY_ORDER`、`generate_dataset_newseed.py`、`injection/*` | grep | 存在；但「`generate_dataset_newseed.py` 不动」**有风险** | `DIFFICULTY_ORDER = ("easy","medium","hard")` 在 `scripts/seed_layout.py`，被 `train_split_parity` 引用，不动合理。`scripts/generate_dataset_newseed.py` 的 `extract_native_sampling` 只抽 `config_easy/medium/hard` 与 `config_xhard`（注释「第四档 xhard：类里存在才写入」），`validate_sampling_config` 用它的形状去 `_same_shape` 比对 payload；`v4_demo_probe`、`injection/rollout/{run,reset_check}.py` 都调 `gen._worker`/`gen.validate_sampling_config`。环境类新增 `config_xhard1/2/3` 后，凡走这条校验的路径（legacy 快照格式）都不会认识新档。S1 前需先确认 V6 链路是否只走 `{decision,native}` 格式（v5 `sampling_config.json` 就是这种格式），否则这个「不动」站不住。2.0 列的 8 个测试文件与 `XHARD_KEY`/`_strip_xhard`/`_xhard_shape`/`assert_native_decision`/`spec_kind_for`/`_unmask_pick_count`/`validate_demo_plan` 均存在 |
| 9b seed 偏移区间 | 「xhard 重冻 6e6、xhard1 8e6、xhard2 10e6、xhard3 12e6」 | 读 `v4_specs.SEED_RULE`、v5-01 实际 seed（sec_A_item9_seed.log） | 互不重叠 | 公式 `seed = offset + env_code×100000 + episode×100 + attempt`，env_code 1～16，episode 0～9，attempt < 100 ⇒ 每个 offset 占 [offset+1e5, offset+1.7e6)。V5 用 4e6：实测 v5-01 seed 4 100 000～5 600 900（最大 attempt 4）；V6 各档依次为 6.1e6～7.7e6、8.1e6～9.7e6、10.1e6～11.7e6、12.1e6～13.7e6，间隔 2e6 > 1.7e6 跨度，互不重叠，也不碰 train/test/val/heldout（heldout 上界约 3.1e6）。只要抽签上限 ≤ 99 次/局、episode < 1000 就安全（计划写 30～60，满足） |
| 9c X0 与 seed/来源封存冲突 | 「xhard 未改的 12 个环境不重抽：v5-01 specs 行复制进 v6-01 的 xhard 档并重跑 3 局比 SHA」+「xhard 重冻 6e6」 | 读 `v4_specs._check_sources` | **机制冲突，计划未说明** | 一个规格文件只有一个 header 级 `seed_rule`，`freeze`/`run` 会逐项比对 `seed_rule`、`source_fingerprint`（V6 改了 src 必然变）、每任务 `sampling_config`（V6 快照多出新档键必然变）。所以 xhard 档里「12 个环境沿用 4e6 的 v5-01 行 + 4 个环境 6e6 重冻」不能直接放进同一份 specs，v5-01 行在 V6 代码上也过不了来源校验。需在 S1 设计里写明：X0 另建单独规格文件（header 记 v5 seed_rule）并重新封存来源，或按环境记 seed_rule |
| 10a 产物 80～100 GB | 风险 #7 | `df -h /data`、`du`、V5 总报告（sec_A_item10.log） | 生成部分合理，总量偏低 | `/data` 可用 2.4 TB（已用 82%），空间不是问题。v5-01 正式 48 局 h5 合计 33.0 GB（每局约 0.69 GB，xhard）+ 视频 1.0 GB；V6 129 正式局 + 36 回放局 = 165 局，新档短于 xhard，估 80～115 GB，计划数字只算了生成。V5 报告另记 V1 两侧 h5 约 98 GB、worktree 约 56 GB，峰值应按 **约 230～270 GB** 核对 |
| 10b V1 两侧各约 3 h | 3.3 末段 | V5 总报告第四节 | 大致一致 | 基线侧「约 3 小时跑完」（单 worker、高负载）；V5 侧 05:43 起跑、后 4 个任务拆出去并行分担，无精确总时长。风险 #7「V1 6 h」是按串行算；V5 实际两侧并行 |
| 10c 生成约 1.5 h | 3.3 末段 | V5 S6 报告 | 合理偏保守 | V5：8 抽签 worker + 8 实跑 worker，抽签约 5 分钟、48 局第 0 轮 749 s、总计约 25 分钟；V6 候选 430（约 2.7 倍）、实跑 165 局（约 3.4 倍）⇒ 约 1～1.5 h |
| 附 计划内部不一致（顺带发现） | 2.6 表 U 圆环版 120/144 | grep | 不一致 | 12.139 把 2.6 表改成圆环版 **120/144（35/37/48）**，但 1.3 结论、1.3 调查结论表「MoveCube 能推多远」、2.6 验收行「与 GL 118/144 同量级」、风险 #4「GL 118/144」仍写第一版的 118/144；1.3 那段「U 的 26 局失败」的明细也是第一版的 |

## 必须改

1. **runbook 第 1 条基线提交写错**：`git diff --quiet 13e5151 -- …/RecordWrapper.py` 实测返回 1（12.76 的 5000 改动在 `13e5151` 之后），整条命令没有输出、会被误判为录像器被改。改为 `git diff --quiet HEAD -- …`（AGENTS.md 规则 11 与 V5 的写法），或写成 `git diff --quiet da77662 -- …`，并在后面补 `&& echo RECORDER_FROZEN=PASS`。
2. **runbook 探针命令不存在**：`v4_rollout.py probe --env --difficulty --episodes` 报 `invalid choice: 'probe'`。改为 `uv run --no-sync python -m scripts.parity.v4_demo_probe --task <Env> --difficulty <tier> --n 4 --out artifacts/newtask-v6/demo-probe/<name>`（`--difficulty` 已存在，但白名单要等 S1 才认 xhard1/2/3）。
3. **commit 编号冲突**：12.136～12.139 已被 V6 计划文档自己占用，3.3 的 S1～S7（12.136～12.152）须整体顺延（从 12.140 起），或只写「顺延编号」。
4. **X0 回放与 seed/来源封存的冲突**：`v4_specs` 按 header 逐项比对 `seed_rule`/`source_fingerprint`/`sampling_config`，v5-01 的 4e6 行不能与 6e6 重冻行放进同一份 xhard 规格，也过不了 V6 代码的来源校验。计划要写明 X0 的规格封装方式。
5. **pytest 命令口径与 S0 基线不同**：必须加上 `-m 'not gpu and not slow'`（V5 S0 基线就是这个口径）以及 `timeout 280s`、`--no-sync`，否则「失败集合与 46 failed / 12 errors 相同」无法比较，也可能超过 5 分钟。

## 建议改

1. 头部改为「代码锚点 `da77662`（12.134，此后至 12.139 只改文档）」；依赖锚点注明是 sha256。
2. 口径 2 与开头声明补上 `run_example.py`、`dataset_replay.py`（V5 口径 2 原文是三个文件与上游逐字节相同）；写明「官方副本」= `artifacts/train-parity/local-smoke-01/official-src/scripts/`。
3. 口径 4 措辞改为「原三档之间没有任何取值分支（configs 三档同一对象）」，不要写「从不读取」，这三个文件都会读 `self.difficulty == "xhard"`。
4. 1.3「src 约 105 处、共用件 5 处」改为实测数字：src 143 行（环境文件 134 行、`utils/` 7 个文件 9 行，其中 `==/!=` 比较 61 行），scripts 14 行；风险 #1 的归零基数随之改。
5. 1.5「演示 25～35 s 不变」限定为「只约束 xhard」，因为 PatternLock/RouteStick 的 xhard3 按计划只有约 735 / ≤700 帧（< 750）。
6. 2.0「不动 `generate_dataset_newseed.py`」加前提：确认 V6 链路不经 `extract_native_sampling`/`validate_sampling_config`（它们只认 `config_xhard`）；否则要么列进改动清单，要么在 S1 验收里加一条「新档不走 legacy 校验」。
7. runbook 生成命令：`--tiers` 是新参数（S1 定），注明抽签并行另有 `--draw-workers`，补上必填的 `--official-root`、`mkdir -p artifacts/newtask-v6/v6-01`；补写 V1 **run** 步（`run --subset` 不存在，用 `--manifest`/默认 144 条身份）。
8. N9 改为与 CLAUDE.md 一致：Agent 工具 subagent 用 opus；workflow 内 `agent()` 只用 sonnet（收尾/计划 ≤3 次 opus）；`model` 不得省略。
9. 授权边界引用用户 2026-09-21 原话作依据，并标注 AGENTS.md 规则 11 字面仍是「逐个批准」（CLAUDE.md 规定冲突时以 AGENTS.md 为准），请用户确认或更新 AGENTS.md。
10. 风险 #7 的空间峰值改为「生成约 80～115 GB + V1 两侧约 98 GB + worktree 约 56 GB」，`/data` 余 2.4 TB 足够；V1 注明两侧可并行。
11. 3.1 链路把 `v4_eval` 写全为 `scripts/eval/v4_eval.py`。
12. V0 的 `git diff` 范围补上 `config_native`（StopCube/MoveCube/InsertPeg 没有 `config_easy`）。
13. 把 1.3、2.6 验收行、风险 #4 中残留的 118/144 统一成圆环版 120/144（第一版数字只留在对照行）。

# 审计 B：V6 计划规划期数字核验（1.3 / 1.4 M1～M9 / 2.2 / 2.4 / 2.5 / 2.7 / 2.9～2.12 / 风险登记）

> 2026-09-25，只读审计。对象 `NEWTASK_RELEASE_V6_PLAN.md`（HEAD `0b1d542`；计划锚点 `da77662`，`git diff da77662 HEAD -- src` 为空，src 未变）。
> 所有重跑脚本与输出只写在 `artifacts/newtask-v6/plan-probes/audit/`（`sec_B_*.log`、`sec_B_rerun/<议题>/`、`sec_B_calc.py`、`sec_B_s5_variant.py`），未改任何 git 跟踪文件、未覆盖原探针产物。
> 蒙特卡洛种子：unmask P2/P2b/P3（`seed = 9_100_000/9_300_000 + i`）、VR study（`7_100_000+i`）、VR sweep（`7_200_000+s`）、count-tasks（`1_000_003·seed + 7919·N + 17`）、PatternLock DFS（`manual_seed(20260925)`）、VP 布局（`5_000_000+k`）**全部固定**，因此重跑结果与原日志**逐位相同**，不存在统计误差问题。

## 核验表

| 条目 | 计划原文摘要 | 核实方法 | 结果 | 备注 |
|---|---|---|---|---|
| B1 VUS 参与频率 | 1.3：V5 现状 VUS 参与频率 [.236,.283,.279,.201]，p≈0 | 出处 `unmask/p2_vus_summary.txt` S0 行；重跑 `p2_inner_mc.py` 两环境各 10000 局 + `p2_analyze.py`（`sec_B_unmask_p2.log`） | 一致 | 重跑逐位相同：[0.2364,0.2832,0.2793,0.2011]，χ²=3566.4，p=0；BUS [.218,.287,.287,.208] 同 |
| B2 bin_3 永不发起约 50% | 1.3、2.2：发起者 `randperm(3)[:2]` + `swap_initiator_third`，第 k 次 `swap_indices[k%3]` | 读源码 `VideoUnmaskSwap.py`/`ButtonUnmaskSwap.py` `_load_scene`；重跑 `p2b_v5_initiators.py`（`sec_B_unmask_p2b.log`）；解析：third 从其余 2 个生成序号中均匀抽，bin_3 入选概率 1/2 | 一致 | 源码为 `torch.randperm(len(selected_bin_indices))[:swap_seed_target_count]`，xhard 下 `hidden_bin_permutation_size=3`、`hidden_bin_count_max=3`、`swap_seed_target_count=2`，即 `randperm(3)[:2]`；第 0～2 次直接用 `swap_indices[0..2]`，k≥3 用 `swap_indices[k%3]`。实测永不发起 VUS [.170,.159,.169,.502]、BUS [...,.506]，逐位复现 |
| B3 死代码 | 2.2：`_compute_dynamic_swap_candidates`/`_select_swap_pair_from_positions` 是死代码 | `grep -rn` 于 src/tests/scripts | 一致 | 唯一调用关系是 `_select_…` 内部调 `_compute_…`；`_select_…` 无任何调用者（VUS、BUS、VR 三处都一样）；`scripts/configs/newtask-v2/native_sampling.json` 也注明「无调用者」。注意 VR 里同名函数同样是死代码，计划只说了 Unmask |
| B4 对角线 6.6%、四边 85～99% | 1.3 | 出处 p2_vus_summary 槽对可行率；重跑 | 一致 | [.863,.066,.994,.993,.066,.855]；BUS 对角线 9.0%、两条长边只有 37%/36%（计划只说 VUS，没问题） |
| B5 S1 p=0.285、极差 3.79、撤销 27% | 1.3 第 2 点 | 同上重跑 | 一致 | 逐位相同 |
| B6 S1n 极差 2.63 | 1.3、M6(b) | 同上 | 一致 | 撤销 0，p=0.638 |
| B7 S5 极差 0.54、p=0.967、「撤销 0」 | 1.3 第 3 点 | `p2c_balanced.py` 重跑 | **部分不一致** | 0.54、0.967 复现；但同一口径（全部布局、不要求 G 连通）下撤销率是 **0.002**（VUS）/ **0.050**（BUS），不是 0。撤销 0 只在 G 连通子集上成立（p2d）。计划把两个口径拼在一句里 |
| B8 G 连通后极差 ≤1：VUS 95.7%、BUS 89.4% | 1.3 第 3 点、2.2 验收「range_le1≥0.89」 | `p2d_connected.py` 重跑；自算 (5264+3871)/9542、(3618+2320)/6640 | 一致（数值）；**算法口径不符** | 数值 0.9573/0.8943 复现。但探针实测的是「(max,sum) 字典序贪心、**不重排**」，而计划 2.2 写的是「两块次数之和最小 + 整条极差>1 重排 ≤20 次」。审计按计划描述的算法补测（`sec_B_s5_variant.py`，同一批 G，只读原 json）：4 对象时两种键结果完全相同；加上 ≤20 次重排后 G 连通子集的极差 ≤1 **VUS 100%、BUS 99.94%**，边际 p=0.999/0.992。即计划数字是「不重排」的保守值，与计划自己描述的算法不对应；验收门槛 0.89 过松 |
| B9 G 连通率 BUS 66.5%、VUS 95.4% | 1.3、风险 #2 | p2d 重跑 | 一致 | 0.6649 / 0.9542 |
| B10 VR 规划失败 40% | 1.3 第 4 点 | 出处 VR report（validate 2400 局 39.96%；study 10000 局 41.03%）；重跑 `study.py` 10000 局 S0/S1/S5（`sec_B_vr_study.log`） | 一致 | 重跑成功率 0.5897 → 失败 41.0%；「40%」取的是 validate 的 39.96%，两者都约 40% |
| B11 每块平均可互换 1.54 块、41% 孤立 | 1.3 第 4 点 | 同上 + `sweep_geom.txt` | 一致 | 槽位平均可行度 1.54、孤立槽位局 0.4102（逐位复现） |
| B12 VR S1 全员参与 50.3%、S5 100%、极差≤1 96.7%、reset 不降 | 1.3 第 4 点 | 同上 | 一致 | S1 0.5029；S5 全员 1.0000、极差≤1 0.9673、成功率 0.5897 与 S0 相同，逐位复现 |
| B13 VR 2.5 表 reset 成功率 xhard1 ≈0.9（4 块）/ xhard2 ≈0.75（5 块）/ xhard3 0.59 / xhard 0.59 | 2.5 表 + 「块数 4/5 时可行图更密、reset 成功率更高」 | VR 报告 `sweep_geom` 只测 N=6～10，**无 N=4/5 行 → ≈0.9/≈0.75 无出处**；审计用同一复刻库补测（`sec_B_rerun/videorepick/vr_n45.py`，每档 2000 局，`sec_B_vr_n45.log`） | **不一致** | 实测规划成功上界 **N=4 0.625、N=5 0.629**、N=6 0.589（N=6 与原 sweep 逐位一致）。N=4/5 平均可行度 1.29/1.46 **反而低于** N=6 的 1.54，孤立槽位局 37.5%/37.1%。「更密、更高」的推断不成立；xhard1/xhard2 实际只比 xhard 高约 3～4 个百分点。xhard3/xhard 0.59 有出处（N=6 0.589） |
| B14 外环每窗 45 对只有 5.6/3.6 对可行、28%/44% 槽无搭档 | 1.3 第 5 点 | 出处 `p3_vus_c10_summary.txt`、`p3_more_summary.txt`；重跑 `p3_outer_mc.py` 两环境前 2000 种子（10000 局太慢，取子集），与原 json 同种子子集比对（`sec_B_unmask_p3.log`） | 一致 | 原 10000 局 5.6/3.6 对、0.281/0.435；前 2000 种子重跑与原 json 同种子子集 VUS、BUS 两环境 p3_analyze/p3c 输出逐位相同 |
| B15 全员参与 ≤4.3% | 1.3 第 5 点 | p3c | 一致 | VUS O4 0.0431、BUS O4 0.0094 |
| B16 O4 未参与 40%/54%→28%/43%、撤销 42%/56%→0.5%/6.7% | 1.3 第 5 点 | p3 summary | 一致 | 0.401/0.537→0.284/0.427；0.415/0.561→0.005/0.067（0.415 取整为 42% 属四舍五入边界） |
| B17 M7(b) 零可行搭档槽 31.7%→15.0% | 1.4 M7 | 出处 `p3b.log`（VUS，593 局，第 0 窗）；重跑 `p3b_reasons.py VideoUnmaskSwap 600` （`sec_B_unmask_p3.log` P3B 行） | 一致（数值逐位复现）；**口径与 1.3 的 28% 不同** | base 0.317 → novis 0.150。同一个「零可行搭档槽」指标，1.3 用的是 P3 全窗 10000 局口径 28.1%，M7 用的是 P3b 第 0 窗 593 局口径 31.7%，同一文档出现两个基线值，读者会以为矛盾 |
| B18 2.2 外环验收「整局可行率 ≥99%/≥98%」 | 2.2 外环 | 出处 p3 summary O4 整局可行 | 一致（有出处），**前提不同** | VUS 0.9989、BUS 0.9826（count=10）。但该数字是在 **V5 内环序列**（`swap_indices[k%3]`+最近邻）下测的；V6 内环改 S5 后外环窗口的内环状态变了，外环可行率未重测；另外 xhard1～3 的外环干扰数 4/6/8 从未测过（见 B19） |
| B19 2.4「干扰 4/6/8 时…外环可行率随干扰数减少只会更高」 | 2.4 | 查 unmask 报告与 P3：只测过 count=10/14/18 | **无出处，且与已有数据趋势不符** | O4 整局可行率 BUS：c10 0.983 → c14 0.996 → c18 0.986；VUS 0.999/0.999/1.000，**干扰数增加时并不单调下降**（c14 反而高于 c10）。干扰更少时环带更稀、最近邻更远，路径出画（vis）拒绝可能反而上升。该句是推断，需实测 count=4/6/8 |
| B20 2.3「pick 最坏 125 + put down 52」 | 2.3 帧数 | 出处 unmask 报告三节帧数公式；核 `p1_h5_frames.log`（v5-01 12 条 h5） | **不一致（小）** | 同一份报告一节写「每次 pick 平均 100 帧（最多 126），put down 平均 48（最多 53）」，h5 实测最大值 pick **126**、put down **53**，大于公式里的「最坏」125/52。结论「全部 ≤ xhard」不受影响 |
| B21 2.4 BUS xhard3 最坏「65+33×6+177×3−40 ≈ 794」 | 2.4 | 算术复算（`sec_B_calc.log`） | **不一致（算术错）** | 65+198+531−40 = **754**；794 是漏减 40 的结果。xhard（n=8）同公式为 820，754 比它低约 8%，「远低于 xhard」措辞偏强。若用实测最大 126/53，xhard3 为 760 |
| B22 2.9 PH reset N=8 98.7%、N=9 93.4%、N=10 71.8% | 2.9 | 出处 `count-tasks/mc_PickHighlight.log`；重跑 `run_mc.sweep`（`sec_B_count_rerun.log`） | 一致 | 逐位复现 98.73/93.36/71.78%；补测 N=7 99.90%（xhard1） |
| B23 2.9「全部不低于 xhard」 | 2.9 | xhard spawn [8,10] 均匀 → 平均 (98.73+93.36+71.78)/3 | 一致 | xhard 平均 87.96%；xhard1 N=7 99.9%、xhard2 N=8 98.7%、xhard3 [8,9] 平均 96.05%，都高于 xhard 平均 |
| B24 2.10 VPB 81.8%、VPO 50.0% | 2.10 | 出处 `vp_layout_mc_{VPB,VPO}.log`（goal 占位、半宽 0.2、3 块 4 台、500 种子）；重跑 `vp_layout_mc_cfg.py`（`sec_B_vp.log`） | 一致 | 0.818、0.500 逐位复现 |
| B25 2.10「VPO 30 次攒 10 条在 0.48 下 96.7%」 | 2.10 | 自算 P(Binom(30,p)≥10) | **不一致（小）** | p=0.48 → **96.47%**；96.7% 对应的是 p=0.483（path-place 报告原文就是 0.483）。同一句前面写 VPO reset = 50.0%，p=0.50 → 97.86%。输入值前后不一 |
| B26 2.11 DFS 命中率 n≥22 远高于 n=25 的 0.9996 | 2.11 | 出处 `pl_dfs_hit_5x5.log`；重跑 `pl_dfs_hit.py 5 5 400000`（`sec_B_pl_dfs.log`） | 一致 | 逐位复现：n≥22 单次 0.0259、20000 次命中 1.0000；n=25 0.000387 → 0.9996；n≥18 0.187 |
| B27 2.11「每段约 35 帧 ⇒ xhard3 最长约 735 帧」 | 2.11 | 算术 + v5-01 h5 逐段帧数（`sec_B_h5_segments.log`） | 算术一致；**「最长」措辞不符** | 22 节点 = 21 段，21×35 = 735 ✓。但 35 是均值（实测 34.1～36.3），单段最大 52～53 帧，所以 735 是「均值口径的典型值」而不是「最长」；xhard 25 节点实测 818～872 帧，xhard3 ≤ xhard 的结论仍成立 |
| B28 2.12 RouteStick 每段恒 50 帧、xhard3 ≤700 | 2.12 | h5 逐段（3 局所有段均为 50）+ 14×50 | 一致 | |
| B29 2.7 BinFill「xhard 离线 100%」 | 2.7 | 出处 `mc_BinFill.log` N=12、`binfill_color.log` N=12/[5,7]；重跑两者 | 一致 | 纯布局 1024/1024；带同色团规则 1024/1024（重排 3.3%，兜底 0） |
| B30 1.3「src 约 105 处 `"xhard"` 字面判断、共用件 5 处」 | 1.3、风险 #1 | 多口径 grep（HEAD，src 未变） | **口径不明，按某一口径可对上** | `grep '"xhard"'` 行数 **130**（出现 134 次）；`== "xhard"` 59 行、`!= "xhard"` 2 行（合计 61，其中 3 行在 utils 的注释/docstring，代码 58）；`["xhard"]` 查表 41 行；`.get("xhard"` 4 行；`'xhard'` 单引号 13 行（全是 `'xhard': config_xhard` 档位表）。出处 difficulty-framework 报告写的是「约 60 处 ==/!= + 约 45 处 `["xhard"]`」≈105，即 **61+41(+4)=102～106** 的口径，不是 `grep '"xhard"'` 的 130。共用件 5 处按「utils 下代码级」可数出：`task_goal:54`、`episode_spec:36`、`xhard_home_site:36`、`unmask_swap_xhard:852 decision["xhard"]`、`sampling_config XHARD_KEY` = 5 ✓（difficulty.py 的 VALID 列表未计入）。风险 #1「grep 计数归零作 S1 验收」无法按字面执行：xhard 仍是合法档名，档位表键、`VALID_DIFFICULTIES`、`XHARD_KEY` 等必然保留，需写明 grep 口径（例如只数 `[=!]= *["']xhard["']`） |
| B31 1.3 规模「43 格、430 候选、129 正式；另 12 个 xhard 回注 36 局」 | 1.3、3.2 X0 | 算术 + 2.1 表 | 一致 | 13×3+4=43，×10=430，×3=129；16−4=12，×3=36；2.1 表 10 个「逐位复现 v5-01」+ InsertPeg/StopCube = 12，一致 |
| B32 M3「未被改动的 9 个环境（含 InsertPeg、StopCube 共 12 个）」 | 1.4 M3 | 对照 2.1 表 | **不一致（笔误）** | 加档但 xhard 不改的是 10 个（BinFill、PickXtimes、SwingXtimes、PH、PatternLock、RouteStick、VPB、VPO、VU、BU），+2 = 12。「9 个」应为「10 个」 |
| B33 风险 #2「抽签上限 60」与 M4「30～60」 | 风险 #2、M4 | 读 `v4_specs.py`/`v5_generation.py` 默认 `--max-reset-attempts 30`；二项分布自算 | 数值兼容，**存在先定待决项的问题** | 60 落在 M4(a) 的 30～60 内，不冲突；但 M4 是待决项，风险表已写死 60。BUS 按 G 连通 0.665 估，30 次攒 10 条概率 ≈1.0000（p=0.60 时 0.9991），60 并非必要。VR 新档按 B13 实测 0.625，30 次即 0.9995 |
| B34 1.3「VUS 长方形锚点…S5 G 连通代价：BUS 约 1/3 被拒」 | 1.3 第 3 点 | = 1−0.665 | 一致 | |

## 必须改

1. **2.5 表 VR reset 成功率 xhard1 ≈0.9、xhard2 ≈0.75 无出处且被实测推翻**：同一复刻库补测 N=4 **0.625**、N=5 **0.629**（N=6 0.589 与原报告逐位一致）；「块数 4/5 时可行图更密、reset 成功率更高（M9）」也不成立（平均可行度 1.29/1.46 < 1.54）。应改为实测值，并据此重新考虑 M9 的论据。
2. **2.4 算术错误**：「65+33×6+177×3−40 ≈ 794」应为 **754**（794 是漏减 40）；「远低于 xhard」应改为「低于 xhard 的 820」。
3. **2.4「外环可行率随干扰数减少只会更高」无出处**，已有 count=10/14/18 的数据反而不单调（BUS 0.983/0.996/0.986）。应改为「未测，S3 实测 count=4/6/8」，或补离线扫描。
4. **M3「9 个环境」应为「10 个环境」**（与 2.1 表、X0 的 12/36 对齐）。
5. **1.3 第 3 点「撤销 0」与「极差 0.54、p=0.967」不是同一口径**：全部布局口径下撤销率 0.002（VUS）/0.050（BUS），撤销 0 只在 G 连通子集成立。应分开写。

## 建议改

1. **S5 数字与计划描述的算法不对应**：95.7%/89.4%、0.54 来自「(max,sum) 贪心、不重排」；计划 2.2 写的是「和最小 + 极差>1 重排 ≤20 次」。按后者补测，G 连通子集极差 ≤1 达 VUS 100%、BUS 99.94%。建议注明口径，并考虑把 2.2 验收 `range_le1>=0.89` 提高（如 ≥0.99）。
2. **零可行搭档槽基线两个值**：1.3 用 28%（P3 全窗、10000 局），M7(b) 用 31.7%（P3b 第 0 窗、593 局）。建议统一或注明口径。
3. **2.2 外环 ≥99%/≥98% 是在 V5 内环序列下测的**，内环改 S5 后与干扰数 4/6/8 下都未重测，应标「V5 内环口径」。
4. **2.10 VPO 二项分布输入**：0.48 → 96.47%，96.7% 对应 0.483；reset 写 50.0% 时应为 97.9%。统一一个 p。
5. **2.3「pick 最坏 125 + put down 52」**低于 v5-01 h5 实测最大 126/53，改成「实测最大 126/53」或注明是公式取值。
6. **2.11「最长约 735 帧」**是均值口径（35 帧/段），单段实测最大 53 帧；改为「均值约 735 帧」。
7. **1.3 与风险 #1 的「约 105 处」写明 grep 口径**（`[=!]= "xhard"` 61 行 + `["xhard"]` 41 行 ≈ 102～106），并把「grep 计数归零」改为可执行的具体正则；`grep '"xhard"'` 是 130 行，不可能归零。
8. **风险 #2 写死「抽签上限 60」**与待决 M4 抵触（数值兼容），建议改为「按 M4 答复」，并注明 30 次在 BUS/VR 新档的估计成功率已 ≥99.9%。
9. 2.2 只说 Unmask 的 `_compute_dynamic_swap_candidates`/`_select_swap_pair_from_positions` 是死代码；VR 里同名函数同样无调用者，可一并注明。

## 已实测通过（重跑逐位一致或算术正确）

B1～B6、B9～B12、B14～B16、B22～B24、B26、B28、B29、B31、B34；B8、B17、B18 的数值本身复现（问题在口径/前提）；B27 算术正确。

## 附：审计产物

- `sec_B_unmask_p2.log`（P2 全量 10000×2 重跑 + P2 分析 + P2c + P2d，与原 summary 仅行序不同）、`sec_B_unmask_p2b.log`、`sec_B_unmask_p3.log`（P3 两环境前 2000 种子 + P3b VUS 600）、`sec_B_rerun/unmask/orig_subset/`（原 json 同种子子集，供逐位比对）
- `sec_B_s5_variant.py/.log`（计划描述的 S5 与探针变体对比）
- `sec_B_vr_study.log`（VR 10000 局 S0/S1/S5）、`sec_B_vr_n45.log` + `sec_B_rerun/videorepick/vr_n45.py`（N=4/5 补测）
- `sec_B_count_rerun.log`（PH N=7～10、BinFill N=12 + 同色团）、`sec_B_vp.log`、`sec_B_pl_dfs.log`、`sec_B_h5_segments.log`、`sec_B_calc.py/.log`

# 审计 C：V6 计划档位数值、单调性、键名存在性（只读）

- 审计对象：根目录 `NEWTASK_RELEASE_V6_PLAN.md` 第一节总表、2.0 管道改造表、2.3～2.13 各环境三档表、第二部分一「按文件清单」。
- 代码基准：当前 HEAD `0b1d542`（12.139）。计划写的锚点 `da77662`（12.134）到 HEAD 之间 `src/ scripts/ tests/` **零 diff**（`git diff --stat da77662..HEAD -- src scripts tests` 为空），锚点仍有效。
- 脚本与输出（全部在 `artifacts/newtask-v6/plan-probes/audit/sec_C/`）：
  - `dump_c.py` → `dump_c.json`：重新 import 16 个环境类，dump `config_easy/medium/hard/xhard`、`configs`、`XHARD_DECISION`、`_native_decision(cls)`，并附 `scripts/configs/newtask-v5/sampling_config.json` 全文。
  - `cmp_native.py` → `cmp_native.out`：16 环境 `native_blocks(cls)` 与 V5 快照的 decision/native **全部逐字相同**（16/16）。与旧 `difficulty-framework/configs_dump.json` 数值一致。
  - `grep_syms.sh` → `grep_syms.out`：任务 3 的符号 grep（src/scripts/tests，*.py/*.json）。
  - `monotone.py` → `monotone.out`：按计划表手录各档取值，自动判均值严格单调、上下界单调不减、新档是否越过 xhard / 低于 hard。
- 下文「出处」均写「文件::符号」，不写行号；文件路径省略前缀 `src/robomme/robomme_env/`。

## 一、任务 1：hard / xhard 数值对照

| 条目 | 计划原文摘要 | 核实方法 | 结果 | 备注（源码出处 / 实际值） |
|---|---|---|---|---|
| BinFill hard | 3 色 / 总块 [10,12] / 投入色 [2,3] / 投入 [3,5] / 原生布局 | dump_c | 一致 | `BinFill.py::BinFill.config_hard` = color 3, spawn_cubes [10,12], put_in_color [2,3], put_in_numbers [3,5]；快照 `decision.configs.hard` 同（put_in_color 在 `native.parameters.put_in_color`，不在 decision） |
| BinFill xhard | 总块 12 / 投入 [5,7] / 杂乱布局 + 精确 OBB + 同色团 ≤3 | dump_c + grep | 一致 | `BinFill.config_xhard` = spawn_cubes [12,12], put_in_numbers [5,7], layout_mode "clutter", color_mix.max_component 3（link_m 0.09, max_redraws 64）；精确 OBB 见 `BinFill.py` 引 `utils/xhard.py::cube_obb2d_exact`。投入色 xhard 仍 [2,3]，计划新档未写投入色 |
| PickXtimes hard | [4,5]，干扰 0，框 0.2 | dump_c | 一致 | `PickXtimes.config_hard` number_min 4/max 5；`_native_decision.target_cube_position_policy.region_half_size` 0.2；`distractor` None |
| PickXtimes xhard | [6,15]，干扰 3，框 0.25，中心距 0.08，均匀无偏置 | dump_c + grep | 一致 | `PickXtimes.config_xhard` 6/15；`PickXtimes.py::XHARD_DECISION` target 框 0.25、goal 框 0.2（不变）、distractor.colors 黄/青/品红（**干扰数 = len(colors)=3，无独立计数键**）、`min_center_dist_m` 0.08；corner_bias 已在 V5 删除（注释 L43） |
| SwingXtimes hard | 3 | dump_c | 一致 | `SwingXtimes.config_hard` 3/3 |
| SwingXtimes xhard | [4,10]，干扰 3，0.08、精确 OBB | dump_c | 一致 | `SwingXtimes.config_xhard` 4/10；`SwingXtimes.py::XHARD_DECISION` distractor 三色、`min_center_dist_m` 0.08；`cube_obb2d_exact` 已引用 |
| PH hard | pick 3 / spawn 6 / RGB 均匀色 | dump_c | 一致 | `PickHighlight.config_hard` spawn 6 pickup 3；`_native_decision.block_color_policy` "native_per_cube_uniform" |
| PH xhard | pick [5,7] / spawn [8,10] / HSV 任意色 / 精确 OBB / `spawn_lo ≥ pick_hi` 断言 | dump_c + 读码 | 一致 | `PickHighlight.config_xhard` spawn [8,10] pickup [5,7]；`PickHighlight.py::XHARD_DECISION` block_color_policy "hsv_floor"；断言在 `PickHighlight` 场景加载的 xhard 分支（`spawn_lo < highlight_hi` 抛 `SamplingConfigError`）。spawn 与 pick **独立抽**（`torch.randint` 各一次） |
| VU hard | 15 容器 / pick 2 / 无干扰 | dump_c | 一致 | `VideoUnmask.config_hard` bin 15 pick 2；`_native_decision.distractor` None |
| VU xhard | 8 容器 / pick 3 / 干扰 15 / 含 cube [7,8] / min_gap_factor 0.75 | dump_c | 一致 | `VideoUnmask.config_xhard` bin 8 pick 3；`_native_decision.xhard.distractor` count 15, cube_count_range [7,8], min_gap_factor 0.75, ring_max_abs_xy [0.2425,0.3289]；另 `bin_layout_policy.xhard.min_gap_factor` 0.75 |
| BU xhard | 干扰 14 / 含 cube [7,7] | dump_c | 一致 | `ButtonUnmask._native_decision.xhard.distractor` count 14, cube_count_range [7,7] |
| VUS/BUS hard | swap [2,3] / pick 2 / 50 步 / 无外环 | dump_c + 读码 | 一致 | `VideoUnmaskSwap.config_hard`/`ButtonUnmaskSwap.config_hard` swap 2～3, pick 2；步数 = `utils/unmask_swap_xhard.py::scaled_window_steps(SWAP_WINDOW_STEPS=50, swap_speed_multiplier=1)` = 50 |
| VUS xhard | swap [8,12] / pick 3 / 33 步 / 外环 10 / 环带 [0.2675,0.45] | dump_c | 一致 | `VideoUnmaskSwap.config_xhard` 8/12, pick 3；`XHARD_SWAP_SPEED_MULTIPLIER`=1.5 ⇒ round(50/1.5)=33；`xhard.distractor.count` 10、`ring_max_abs_xy` [0.2675,0.45]。**注意**：这是方环 `max(|x|,|y|)∈[r_in,r_out]`（`utils/unmask_distractors.py` 文档），不是圆环；外环 `cube_count_range` [5,5]，计划新档未给 |
| BUS xhard | swap [6,8] | dump_c | 一致 | `ButtonUnmaskSwap.config_xhard` 6/8；其余同 VUS，`path_constraints.min_button_center_dist_m` 0.122 |
| VR medium | 3 / [2,3] / [1,3] | dump_c | 一致 | `VideoRepick.config_medium` cube 3, swap 2～3；repick = `NATIVE_SAMPLING.parameters.num_repeats` low 1 high_exclusive 4 ⇒ [1,3] |
| VR hard | 聚簇 15 / 0 / [1,3] | dump_c + 读码 | 一致 | `config_hard` cluster True, swap 0/0；15 = `NATIVE_SAMPLING.parameters.hard_spawn_rounds`(5) × 3 色 |
| VR xhard | 6 / [8,12] / [4,6] / min_center_gap 0.12 | dump_c | 数值一致，**键名不一致** | `config_xhard` cube 6, swap 8/12, num_repeats 4～7(半开) ⇒ [4,6]；中心距键名实为 `min_center_dist_m`（`decision.xhard.layout.min_center_dist_m`=0.12），源码无 `min_center_gap`；`partner_nearest_k` 3 |
| PatternLock hard | 5×5 / [4,8] / 预算 1000（耗尽静默沿用） | dump_c + 读码 | 一致 | `PatternLock.config_hard` grid 5 length [4,8]；`NATIVE_SAMPLING.parameters.path_selection.max_attempts` 1000；耗尽走「use the last one」分支 |
| PatternLock xhard | 25 节点 / 预算 20000（耗尽抛错） | dump_c | 一致 | `config_xhard` length [25,25]；`PatternLock.py::XHARD_DECISION.path_search_max_attempts` 20000 |
| RouteStick hard/xhard | [4,7] T / [15,21] T | dump_c | 一致 | `RouteStick.config_hard` length [4,7] backtrack True；`config_xhard` [15,21] True；`_native_decision.xhard.segment_count_range` [15,21] |
| VPB hard/xhard | k 1→2；不放回→return_to_origin；颜色 3、目标台 4、swap True | dump_c | 一致 | `VideoPlaceButton._native_decision` demo_object_count 1 / "native_random_goal_site"；`XHARD_DEMO_DECISION` 2 / "return_to_origin"；config_hard/xhard color 3, targets 4, swap True |
| VPO hard/xhard | 同上，v [2,4] | dump_c + 读码 | 一致 | `VideoPlaceOrder.py::NATIVE_SAMPLING.parameters.visit_selection.count_sampler` = `"torch.randint(2, len(targets) + 1)"`，targets 4 ⇒ [2,4]；**v 是 native 里的字符串表达式，不是 decision 数值键** |
| VPB/VPO「演示放置次数」 | hard 2/3，xhard1 3/4（放回 +1） | 读码 | **不一致** | 原三档演示在两个 target 之外还有一段 pick + `drop onto goal_site`（`VideoPlaceButton`/`VideoPlaceOrder` 任务表 `target=self.goal_site`）；xhard 的 `return_to_origin` 是把这段换成「放回原位」（`_xhard_pick_place(..., home=True)`），**动作段数不变**。计划把 goal_site 那次计 0、放回计 1，hard→xhard1 实际 pick-place 段数相同，标尺不成立 |
| MoveCube 方块框 | ±0.10（面积 0.040） | dump_c + 读码 | 一致（注意口径） | `_native_decision.demo_layout.cube_position_policy` center_span 0.2, center_offset −0.1 ⇒ 候选中心 ∈ [−0.1,0.1]²；之后 `spawn_random_cube(region_half_size=0.05)` 以候选为中心再抖 ±(0.05−0.02)，**实际方块中心 ≈ ±0.13**，0.040 m² 只是候选框面积 |
| MoveCube goal 框 | demo ±0.11、exec ±0.06 | 读码 | 一致 | `MoveCube.py::NATIVE_SAMPLING.positions.goal_demo.region_half_size` 0.15、`goal_execution` 0.10，radius = cube_half_size(0.02)×radius_factor 2 = 0.04；`utils/object_generation.py::spawn_random_target` 中心界 = half − radius ⇒ ±0.11 / ±0.06 |
| MoveCube 杆根 | ±0.05，y=±0.2 | dump_c | 一致 | `peg_position_policy` base_y_abs 0.2, jitter_span 0.1 ⇒ ±0.05 |
| MoveCube 禁区 / yaw | R=0.05；杆/方块 yaw 全 2π | dump_c + 读码 | 一致 | `config_xhard.center_exclusion.radius_m` 0.05；`peg_yaw_range` xhard span 2π；`spawn_random_cube` random_yaw ⇒ `yaw_sample*2π` |
| InsertPeg / StopCube | 原三档无梯度，不动 | dump_c | 一致 | 两者 `configs.easy/medium/hard` 逐字相同；MoveCube 同（三档都是 span π/2 + corner_bias 0） |
| 快照一致性 | 源码与 `newtask-v5/sampling_config.json` | cmp_native | 一致 | 16/16 decision、native 逐字相同 |
| 总表 PH 维度 | 「干扰数 + pick 数」 | 对照 2.9 | 不一致（表述） | 总表只给「总块 6→7→8→[8,9]→[8,10]」，2.9 的干扰列均值实为 3/3/3.5/3/3，干扰数并未随档上升（见任务 2） |
| 2.3 「干扰总数保证 > hard 的 15 个容器」 | VU/BU 新档 | 计算 | **BU xhard1 不满足** | BU xhard1 = 8 内环 + 7 干扰 = 15，等于而非大于 15；若「干扰总数」指干扰单独计数则 VU 8/BU 7 都远小于 15。句意需明确 |
| 「src 约 105 处 `"xhard"`」 | 管道规模 | grep | 无法精确核实 | `"xhard"` 字面量 130 处（含注释/字符串），`==/!= "xhard"` 比较 61 处；105 的口径未说明 |

## 二、任务 2：单调性（口径 5 / N7 / 3.2）

判定口径：均值按区间中点；「越过」指新档均值 > xhard 或 < hard；区间界按「下界、上界各自单调不减」读口径 5 的「单调不减」。完整输出见 `sec_C/monotone.out`。

| 环境 / 字段 | hard → x1 → x2 → x3 → xhard（均值） | 问题 | 与口径 5 冲突？ | 与 N7 / 3.2 冲突？ |
|---|---|---|---|---|
| PickXtimes 次数 | [4,5]→[5,7]→[6,9]→[7,12]→[6,15]（4.5/6/7.5/9.5/10.5） | 均值严格；**x3 下界 7 > xhard 下界 6**（区间不嵌套，x3 的最小次数比 xhard 还难） | 若「单调不减」按下界读：冲突；按均值读：不冲突（口径 5 明写「区间允许重叠」） | 不冲突 |
| PickXtimes 干扰块 | 0→1→2→3→3 | **x3 = xhard**（非严格） | 不冲突（不减） | **冲突**（N7 要所有加码字段严格） |
| PickXtimes 框半宽 | 0.2→0.25×4 | x1=x2=x3=xhard | 不冲突 | 冲突（若算加码字段；它属「机制」，建议明确排除） |
| SwingXtimes 轮数 | 3→[3,4]→[4,6]→[5,8]→[4,10]（3/3.5/5/6.5/7） | **x3 下界 5 > xhard 下界 4**；x1 下界 3 = hard | 同 PickXtimes | 不冲突 |
| SwingXtimes 干扰块 | 0→1→2→3→3 | x3 = xhard | 不冲突 | **冲突** |
| PH pick | 3→4→[4,5]→[5,6]→[5,7] | 严格 | 不冲突 | 不冲突 |
| PH spawn | 6→7→8→[8,9]→[8,10] | 严格 | 不冲突 | 不冲突 |
| **PH 干扰数（spawn−pick，独立抽）** | 3→3→3～4→2～4→1～5（**3/3/3.5/3/3**） | hard = x1；**x2 均值 3.5 > xhard 3**；x3 下降；xhard 本身干扰均值 = hard。用户点名「pickhighlight 按照干扰数量」，但这一维**根本没加码** | **冲突**（x2→x3 下降） | **冲突**（x2 越过 xhard） |
| VU / BU pick | 2→2→3→3→3 | hard = x1，x2 = x3 = xhard | 不冲突 | **冲突**（用户点名「pickup 次数」维度） |
| VU 干扰 / 含 cube | 0→8→10→13→15；0→4→5→6.5→7.5 | 严格 | 不冲突 | 不冲突 |
| BU 干扰 / 含 cube | 0→7→9→12→14；0→3.5→4.5→6→7 | 严格；xhard [7,7] 是单点 | 不冲突 | 不冲突 |
| VU/BU 内环容器 | 15→8→8→8→8 | **hard→x1 下降**（新档低于 hard）；x1..xhard 相等 | 若算字段：冲突（计划以「干扰总数 >15」辩护，BU x1 恰 15 不成立） | 冲突（若算字段） |
| VUS swap | [2,3]→[4,5]→[5,7]→[7,9]→[8,12] | 严格，区间界单调（x3 [7,9] 与 xhard [8,12] 无问题） | 不冲突 | 不冲突 |
| BUS swap | [2,3]→[3,4]→[4,5]→[5,6]→[6,8] | 严格 | 不冲突 | 不冲突 |
| VUS/BUS pick | 2→2→3→3→3 | hard = x1，x2 = x3 = xhard | 不冲突 | **冲突** |
| VUS/BUS 每次交换步数 | 50→50→33→33→33 | hard = x1，x2 = x3 = xhard | 不冲突 | **冲突**（若算字段） |
| VUS/BUS 外环干扰 | 0→4→6→8→10 | 严格 | 不冲突 | 不冲突 |
| VR 块数 | 15(聚簇)→4→5→6→6 | **hard→x1 下降**；**x3 = xhard** | 冲突（下降；M9 已挂待决） | **冲突**（x3 = xhard 非严格） |
| VR swap / repick | 0→4→6→7.5→10；2→2.5→3.5→4.5→5 | 严格，界单调 | 不冲突 | 不冲突 |
| BinFill 投入 | 4/4.5/5/5.5/6 | 严格 | 不冲突 | 不冲突 |
| BinFill 总块 | [10,12]→12×4 | x1 = x2 = x3 = xhard | 不冲突 | 冲突（若算字段） |
| PatternLock 节点 | 6/10.5/15/20/25 | 严格 | 不冲突 | 不冲突 |
| PatternLock 预算 | 1000→20000×4 | x1..xhard 相等 | 不冲突 | 冲突（若算字段；它是搜索预算，建议明确排除） |
| RouteStick L | 5.5/9/11.5/13.5/18 | 严格 | 不冲突 | 不冲突 |
| VPB k | 1→1→2→2→2 | 非严格 | 不冲突 | 冲突（若算字段） |
| **VPB 放回块数** | 0→1→0→1→2 | **x1→x2 下降**（x1 放回、x2 不放回） | **冲突** | **冲突** |
| VPO v | [2,4]→[2,4]→[2,3]→[2,4]→[2,4]（3/3/2.5/3/3） | **x2 均值 2.5 < hard 3**，x1→x2 下降 | **冲突** | **冲突** |
| **VPO 放回块数** | 0→1→0→0→2 | x1→x2 下降 | **冲突** | **冲突** |
| VPB/VPO 放置次数（计划口径） | 2..6 / 3..8 | 严格，但计数口径本身有误（见任务 1） | — | — |

**口径 5 与 N7 是否矛盾**：矛盾。
- 口径 5 原文「每档在已加码字段上**单调不减**，且**至少一个字段**均值严格上升；取值区间允许重叠，均值必须严格介于相邻两档之间」——前半句允许「其他字段相等」，末句「均值必须严格介于」未说字段范围，本身就二义。
- N7「每档**所有**加码字段均值严格介于相邻档之间」、3.2 单调性判据「各加码字段均值严格递增」（`TIER_MONOTONE=PASS … violations=0`）把末句解释成「全部字段严格」。
- 按 N7/3.2，计划自己的表至少在 PickXtimes/SwingXtimes 干扰块、PH 干扰数、VU/BU/VUS/BUS pick、VUS/BUS 步数、VR 块数、BinFill 总块、PatternLock 预算、VPB/VPO k 上违例；`TIER_MONOTONE` 按字面实现会必然 FAIL。
- 按口径 5 前半句（单调不减），仍有真违例：PH 干扰数 x2→x3 下降、VPB/VPO 放回 x1→x2 下降、VPO v x1→x2 下降、VR 块数 / VU 内环容器 hard→x1 下降。
- 「新档 ≥ xhard」：PH 干扰 x2 均值 3.5 > xhard 3；PickXtimes x3 下界 7 > 6、SwingXtimes x3 下界 5 > 4（只在下界上，均值未越）。
- 「新档 ≤ hard」：VR 块数 x1..x3 < 15；VU/BU 内环容器 8 < 15；VPO v x2 2.5 < 3。

## 三、任务 3：键名 / 符号存在性

| 条目 | 计划原文摘要 | 核实方法 | 结果 | 备注 |
|---|---|---|---|---|
| `VALID_DIFFICULTIES` | `utils/difficulty.py` 加 xhard1/2/3 | grep | 一致 | `utils/difficulty.py::VALID_DIFFICULTIES = {"easy","medium","hard","xhard"}` |
| `XHARD_KEY` / `_strip_xhard` / `_xhard_shape` / `assert_native_decision` | `utils/sampling_config.py` | grep | 一致 | 均在 `utils/sampling_config.py`；`XHARD_KEY = "xhard"` 单一字符串 |
| `spec_kind_for` | `utils/episode_spec.py` | grep | 一致 | 另被 `tests/lightweight/test_episode_spec_recorder.py` 引用 |
| `_unmask_pick_count` | `task_goal.py` | grep | 一致 | `utils/task_goal.py`（内有 `self.difficulty == "xhard"`） |
| `validate_demo_plan` | `xhard_home_site.py` | grep + 读码 | 一致，**但计划改动描述不全** | 现逻辑：非 xhard 只许 `(1, native_random_goal_site)`，xhard 只许 `return_to_origin`。计划新档 VPB x2 `(2, 不放回)`、VPO x2/x3 `(2, 不放回)` 同样会被拒；且原三档只有一个 `goal_site`，「k=2 不放回」两块放哪未定义。计划只写了放行 `return_last_only` |
| `decision["xhard"]` | 列在 episode_spec/task_goal/xhard_home_site/unmask_swap_xhard 行 | grep | 部分一致 | 字面 `decision["xhard"]` 在 `utils/unmask_swap_xhard.py`（`env._sampling["decision"]["xhard"]`）及 VUS/BUS/VR/PickXtimes/SwingXtimes/InsertPeg/StopCube；episode_spec/task_goal/xhard_home_site 里是 `== "xhard"` / `!= "xhard"` 字面比较，不是 `decision["xhard"]` |
| `spawn_random_cube/target` | `utils/object_generation.py` | grep | 一致 | 两函数都在；已有 V5 可选参数 `center_exclusion`、`min_center_dist` |
| `DIFFICULTY` / `SEED_RULE` | `scripts/parity/v4_specs.py` | grep | 一致 | `DIFFICULTY = "xhard"`，`SEED_RULE.offset` 4_000_000、env_block 100_000（16 环境占 1.6e6，计划 6e6/8e6/10e6/12e6 间隔 2e6 不重叠）；`DIFFICULTY` 另见 `v4_rollout.py`、`train_split_runner.py`、`scripts/injection/rollout/single_binfill.py` |
| `RELEASE_NOTES` | `train_split_config.py` 加 newtask-v6 | grep | 一致 | 现有 newtask-v4/v5 两键 |
| `NATIVE_SAMPLING` | 各环境 | grep | 一致 | 28 文件 |
| `NATIVE_SPEC_GOLDEN` / `NATIVE_AST_GOLDEN` | 不动 | grep | 一致 | 只在 `tests/lightweight/test_v5_xhard_pickswing.py` |
| `_spawn_cubes_xhard` | BinFill | grep | 一致 | `BinFill.py` |
| `_plan_swap_partners_xhard` / `_xhard_planned_partner` | VR | grep | 一致 | `VideoRepick.py`（前者为模块级函数） |
| `plan_distractor_swaps` / `evaluate_outer_candidate` / `predict_inner_windows` / `prejudge_inner_windows` / `joint_sweep_from_actual` | 2.2 | grep | 一致 | 全在 `utils/unmask_swap_xhard.py` |
| `check_swap_sweep_prefiltered` | 2.2 | grep | 一致 | 定义在 `utils/bin_collision.py`，被 unmask_swap_xhard、VR 引用 |
| `swap_initiator_indices` / `swap_initiator_third` | 2.2 | grep | 一致 | 是 VUS/BUS 里的 spec 记录键 `objects.swap_initiator_indices/third` |
| `_compute_dynamic_swap_candidates` / `_select_swap_pair_from_positions` | 「死代码」 | grep | 存在 | 在 VUS/BUS **以及 VR** 三处都有；计划只点了 Unmask |
| `demo_return_policy` / `return_to_origin` | VPB/VPO | grep | 一致 | `xhard_home_site.py::RETURN_TO_ORIGIN` |
| `visit_selection.count_sampler` | VPO 按档取上界 | grep | 存在，**位置冲突** | 它在 `NATIVE_SAMPLING.parameters`（native 块，V0 要求零 diff），第二部分表又写 decision 子树新键 `visit_count_max`（源码无），两处说法不一致；只能走 decision 新键 |
| `path_search_max_attempts` | PatternLock | grep | 一致 | `PatternLock.py::XHARD_DECISION` |
| `segment_count_range` | RouteStick | grep | 一致 | 只在 `decision.xhard` 下；原三档读 `parameters.configs.<d>.length` |
| `demo_layout` / `execution_layout` | MoveCube | grep | 一致 | 两者下各有 `xhard.center_exclusion` 子树；计划新子键 `region` 不存在（新增） |
| `swap_speed_multiplier` / `distractor_swap` | VUS/BUS | grep | 一致 | `decision.xhard.*` |
| `corner_bias` | PickXtimes/Swing 子树 `corner_bias: 0` | grep | **不一致** | PickXtimes/SwingXtimes 的 decision 已无此键（V5 L43 删除，SwingXtimes 注释「本环境没有 corner_bias」）；源码中只剩 `MoveCube.configs.<d>.corner_bias` 与 `utils/xhard.py::corner_push`。写回会触发 `_xhard_shape` 的「申报外新键」 |
| `hsv_floor_color` | PH 子树 | grep | **不一致** | 源码只有常量 `utils/xhard.py::HSV_FLOOR_COLOR` 与 decision 键 `block_color_policy: "hsv_floor"` + `block_color_hsv`；`hsv_floor_color` 仅是测试名 `test_hsv_floor_color_gamut` |
| `exact_obb` | PH 子树 | grep | **不一致** | 源码无此键；精确 OBB 在 xhard 分支硬编码调用 `cube_obb2d_exact`；`exact_obb` 只出现在测试函数名 |
| `min_center_gap` | PickXtimes/Swing、VR 子树 | grep | **不一致** | 源码 0 命中；实际键 `min_center_dist_m`（PickXtimes/Swing 在 `decision.xhard`，VR 在 `decision.xhard.layout`） |
| `distractor_count` | PickXtimes/Swing 子树 | grep | **不一致** | 不是 decision 键，只是 spec 记录路径 `objects.distractor_count`；干扰数由 `distractor.colors` 长度决定 |
| VU/BU `distractor.{count, cube_range}` | 第二部分表 | grep | **部分不一致** | `count` 对；`cube_range` 实为 `cube_count_range`（`"cube_range"` 只在一个测试文件字符串里）。且 VU/BU 还有第二个 xhard 子树 `bin_layout_policy.xhard.min_gap_factor`，表未列 |
| VR `{min_center_gap 0.12, partner_policy: balanced}` | 第二部分表 | grep | **不一致** | 实际 `xhard.layout.min_center_dist_m`、`xhard.swap_plan.partner_rule`（"reset_plan_nearest_feasible"）；另有嵌套 `num_repeats_range.xhard`（手写，非自动派生），表未列 |
| BinFill `<tier>.{layout: clutter, color_mix}` | 第二部分表 | dump | **不一致** | 实际位于 `decision.configs.xhard.{layout_mode, color_mix}`（BinFill 没有顶层 `decision.xhard`），键名 `layout_mode` |
| `random_yaw` | MoveCube | grep | 一致 | `spawn_random_cube(random_yaw=True)` ⇒ `u·2π` |
| `partner_policy` / `inner_swap_policy` / `visit_count_max` / `is_newvalue_difficulty` / `newvalue_tier` / `NEWVALUE_DIFFICULTIES` / `v6_generation.py` | 新增 | grep | 不存在（预期） | 均为计划新建 |
| `seed_layout.DIFFICULTY_ORDER` / `generate_dataset_newseed.py` / `injection/*` | 不动 | ls/grep | 一致 | `scripts/seed_layout.py`、`scripts/generate_dataset_newseed.py`、`scripts/injection/` 存在 |
| 测试文件 | `test_v4_xhard_{pickxtimes,swingxtimes,stopcube}`、`test_episode_spec_recorder`、`test_sampling_config_split`、`test_v5_xhard_pickswing`、`test_v5_generation_tools`、`test_episode_action_sampling` | ls | 一致 | 均在 `tests/lightweight/` |
| 「断言恰 4 档」 | → 7 档 | grep | 存在，**但 stopcube 不该改** | `test_v4_xhard_{pickxtimes,swingxtimes,stopcube}.py` 都有 `assert set(CLS.configs) == {"easy","medium","hard","xhard"}`。StopCube 不加档，其断言应保持 4 档，计划写「4 → 7 档」错。另有 `test_operand_scope.py`（`operand_sha256(..., {"easy","medium","hard","xhard"})`、`difficulties_of(GROUPS_V3)`）计划未列；`test_episode_action_sampling.py` 的 4 档 parametrize 已在计划清单内 |
| VR `elif self.difficulty == "hard"` 链 | 族判断必须在前 | 读码 | 一致 | `VideoRepick._load_scene`：`if == "xhard"` → `elif == "hard"`（聚簇）→ `else`（easy/medium）；新档若不先族判断会落进 else 分支按 `configs[difficulty]['cube']` 走 |
| RouteStick `.get(difficulty, 回退 easy)` | 改缺键抛错 | 读码 | 一致 | `sampling_configs.get(getattr(self,"difficulty","easy"), sampling_configs[fallback_difficulty])`，`NATIVE_SAMPLING.parameters.configs_fallback_difficulty = "easy"`；另：`RouteStick.__init__` 无显式 difficulty 时按 seed%3 赋值后又被无条件覆盖为 "easy"（上游原样，非本轮问题） |

## 四、必须改（标红）

1. <span style="color:red">**口径 5 与 N7 / 3.2 互相矛盾**：前者「单调不减 + 至少一个字段严格」，后者「所有加码字段严格」。按 N7 字面，计划自己的表在 ≥10 个字段上违例，`TIER_MONOTONE=PASS violations=0` 不可能达成。须二选一，并明确「加码字段」清单（建议逐环境列出参与判定的字段，排除框半宽、搜索预算、交换步数等机制型字段）。</span>
2. <span style="color:red">**PH 干扰数没有被加码**：用户点名「pickhighlight 按照干扰数量」，但计划均值 3/3/3.5/3/3（hard 与 xhard 相等，x2 越过 xhard，x3 下降）。spawn 与 pick 独立抽，xhard 本身的干扰均值就等于 hard。须重排 spawn/pick 使干扰均值严格递增，或改为直接按干扰数抽。</span>
3. <span style="color:red">**VPB/VPO「演示放置次数」计数口径错**：原三档已有一段 pick + `drop onto goal_site`，`return_to_origin` 只是替换这段终点，hard→xhard1 的 pick-place 段数不变。另外 VPB x1→x2、VPO x1→x2 的「放回」字段倒退、VPO x2 的 v 均值 2.5 < hard 3，违反口径 5「单调不减」。</span>
4. <span style="color:red">**`validate_demo_plan` 放行范围不全**：除 `return_last_only` 外，`(k=2, 不放回)`（VPB x2、VPO x2/x3）也被现逻辑拒绝；且原三档只有一个 `goal_site`，「k=2 不放回」时两块的去处未定义。</span>
5. <span style="color:red">**第二部分一 decision 子树键名与源码不符**：`min_center_gap`→`min_center_dist_m`（PickXtimes/Swing 在 `xhard`，VR 在 `xhard.layout`）；`corner_bias` 在 PickXtimes/Swing 已删，写回会被 `_xhard_shape` 当作申报外新键；`distractor_count` 不是 decision 键；PH 的 `hsv_floor_color`/`exact_obb` 不存在（实为 `block_color_policy`/`block_color_hsv`，OBB 硬编码）；VU/BU `cube_range`→`cube_count_range`；VR `partner_policy`→`swap_plan.partner_rule`；BinFill 实际在 `decision.configs.<tier>.{layout_mode, color_mix}`。</span>
6. <span style="color:red">**测试改动清单错一处、漏一处**：`test_v4_xhard_stopcube` 的 4 档断言不应改成 7 档（StopCube 不加档）；`test_operand_scope.py` 的 4 档写法（`operand_sha256`/`difficulties_of`）未列入。</span>
7. <span style="color:red">**2.3「干扰总数保证 > hard 的 15 个容器」对 BU xhard1 不成立**（8+7=15）；若「干扰总数」指干扰单独计数，VU 8、BU 7 都 < 15。须改句或改数。</span>

## 五、建议改

1. PickXtimes x3 [7,12]、SwingXtimes x3 [5,8] 的下界高于 xhard 下界（6、4）：均值合规，但 x3 的最易局比 xhard 最易局还难。若「单调不减」要落到区间界，建议 x3 下界 ≤ xhard 下界（如 [6,13]、[4,9]）；否则在口径 5 写明「只看均值」。
2. VR 块数 hard 15 → x1 4 下降、x3 = xhard = 6；VU/BU 内环容器 15 → 8 下降。前者已挂 M9；后者建议也在 1.4 挂待决或在口径 5 写明「内环容器数不算加码字段」。
3. VUS/BUS 新档外环 `cube_count_range` 未给（xhard 为 [5,5]/10）；BinFill 新档投入色未给（hard/xhard 同 [2,3]）；建议补齐，免得实施方自填（N3）。
4. VPO v 上界按档取：`visit_selection.count_sampler` 在 native 块（V0 要求零 diff），只能走 decision 新键；2.10 正文与第二部分表的两种说法统一为 decision 键。
5. VUS 外环「环带 [0.2675,0.45]」实为方环（`max(|x|,|y|)`），建议写明，与 MoveCube 圆环区分。
6. MoveCube 现状「方块框 ±0.10、面积 0.040」只是候选中心框，实际方块中心还要再抖 ±0.03（约 ±0.13）；与 U 的 0.080 m² 对比时注明口径。
7. 死代码 `_compute_dynamic_swap_candidates`/`_select_swap_pair_from_positions` 在 VR 也有，2.2 只点了 Unmask。
8. 2.0 行「`decision["xhard"]`」对应到 episode_spec/task_goal/xhard_home_site 不准确（那里是 `== "xhard"` 字面比较）；「src 约 105 处」口径未说明（实测字面量 130、`==/!=` 比较 61）。
9. 3.3 提交编号「S1 = 12.136 … S7 = 12.152」与现 HEAD 已到 12.139 冲突，需顺延。

# V6 计划审计 D 节：h5 实测 + 本机模拟器 reset 实测

审计对象：根目录 `NEWTASK_RELEASE_V6_PLAN.md`（1.3、1.5、2.3、2.7～2.12、第五节盲区）。只读审计，未改任何 git 跟踪文件；
脚本与原始输出全部在 `artifacts/newtask-v6/plan-probes/audit/sec_D/`。本机 GPU 1，未用 greatlakes。

## 口径说明

- **xhard 实测源**：`artifacts/newtask-v5/v5-01/rollout/run1/episodes/*/hdf5_files/*.h5`，16 环境 × 3 局 = 48 局（`h5_stats.py` → `h5_xhard.json`）。
- **hard 对照源**：仓库内 `artifacts/newtask-v5/v1/`、`s0/` 只有日志、没有 h5；改用原始 RoboMME 数据集 `/data/hongzefu/data-0306/record_dataset_<Task>.h5`，按 metadata 取 `difficulty=="hard"` 的局，16 环境 × 25 局 = 400 局（`h5_hard.py` → `h5_hard.json`）。前提假设：data-0306 就是原三档的「最原始基线」发布集。
- **fps**：录像器 `src/robomme/env_record_wrapper/RecordWrapper.py` 写视频 `fps=30`，V5 口径 9 也按 30 fps 计；演示帧 = `info/is_video_demo` 为真的 timestep 数；执行帧 = 总 timestep − 演示帧。
- **评估步数口径**：`scripts/evaluation.py` 写的是 `max_steps=1300`；`episode_config_resolver.py` 把它换成 `max_steps_without_demonstration = max_steps + 2 = 1302`；`DemonstrationWrapper._step_batch` 只在 `current_task_demonstration == False` 时累加 `steps_without_demonstration`，达到 ≥1302 时置 `truncated`。所以预算管的是**执行段（非演示）步数**，演示段不计入；上限实际约 1301～1302 步。计划写的「1301」与这一口径吻合。h5 的执行帧还多出末尾 1～2 帧（终止时额外补录一帧），差别可以忽略。
- **reset 探针**：`reset_probe.py` 从 `scripts/configs/newtask-v5/sampling_config.json` 取单任务 `{decision, native}`，在**内存里**把 xhard 的数值换成新档值，再照 `v4_specs._draw_one` 的写法调用 `gym.make(task, sampling_config=…, **v4_specs.env_kwargs(seed, 0))` 和 `env.reset()`，只做 reset、不跑演示。seed 从 9100000 起连号；同一环境的各个组合用同一批 seed，所以组合之间是配对比较。覆盖点：PH 改 `spawn_count.xhard` / `highlight_count.xhard`；BinFill 改 `configs.xhard.put_in_numbers`；PX/SX 把 `xhard.distractor.colors` 截成前 k 个（干扰块数 = 颜色数）。已核实覆盖真的生效：PH 成功局的 spawn/pick 等于设定值，BinFill 的 `target_numbers` 之和落在设定区间，PX/SX 的 `all_cubes` 等于 3+k。
- **reset 内部有没有重试**：四个环境的 xhard 分支都没有 reset 级重试。每块方块的拒绝采样在 `spawn_random_cube` 里（PH 默认 256 次，PX/SX 用 `XHARD_CUBE_MAX_TRIALS=1024`），用满预算就直接抛 `SceneGenerationError`；换 seed 重抽发生在抽签层（`v4_specs draw`，每次 attempt 换一个 seed）。所以「最终失败率」= 单 seed 的 reset 失败率，「平均抽签次数」= 1/成功率。每块内部的拒绝采样次数没有插桩，拿不到。

## 一、h5 实测（任务 1）

### 1.1 xhard 48 局逐局（帧数；秒数按 30 fps 换算）

| 环境 | ep0 总/演示/执行 | ep3 总/演示/执行 | ep6 总/演示/执行 | 演示时长 s |
|---|---|---|---|---|
| BinFill | 1523/0/**1523** | 1187/0/1187 | 956/0/956 | — |
| ButtonUnmask | 538/0/538 | 516/0/516 | 511/0/511 | — |
| ButtonUnmaskSwap | 716/0/716 | 689/0/689 | 721/0/721 | — |
| InsertPeg (ep0/1/5) | 451/238/213 | 496/248/248 | 484/242/242 | 7.9/8.3/8.1 |
| MoveCube | 481/263/218 | 281/167/114 | 280/170/110 | 8.8/5.6/5.7 |
| PatternLock | 1636/818/818 | 1744/872/872 | 1674/837/837 | **27.3/29.1/27.9** |
| PickHighlight | 1032/0/1032 | 872/0/872 | 1060/0/1060 | — |
| PickXtimes | 1017/0/1017 | 1309/0/**1309** | 1122/0/1122 | — |
| RouteStick | 2100/1050/1050 | 1700/850/850 | 1600/800/800 | **35.0/28.3/26.7** |
| StopCube | 428/0/428 | 846/0/846 | 553/0/553 | — |
| SwingXtimes | 649/0/649 | 826/0/826 | 926/0/926 | — |
| VideoPlaceButton | 1552/1365/187 | 1568/1373/195 | 1589/1368/221 | 45.5/45.8/45.6 |
| VideoPlaceOrder | 1700/1520/180 | 2171/1952/219 | 1832/1606/226 | 50.7/65.1/53.5 |
| VideoRepick | 1324/655/669 | 1696/851/845 | 1346/699/647 | 21.8/28.4/23.3 |
| VideoUnmaskSwap | 802/396/406 | 807/396/411 | 780/366/414 | 13.2/13.2/12.2 |
| VideoUnmask | 507/66/441 | 441/66/375 | 466/66/400 | 2.2/2.2/2.2 |

### 1.2 hard 对照（data-0306，每环境 25 局）

| 环境 | 总帧 min/中位/max | 演示 s min/max | 执行帧 max | 执行 >1301 的局 |
|---|---|---|---|---|
| BinFill | 608/871/1097 | — | 1097 | 0 |
| ButtonUnmask | 351/372/459 | — | 459 | 0 |
| ButtonUnmaskSwap | 432/463/577 | — | 577 | 0 |
| InsertPeg | 418/464/808 | 7.0/13.5 | 404 | 0 |
| MoveCube | 254/437/497 | 5.0/8.8 | 249 | 0 |
| PatternLock | 186/328/572 | 3.1/9.5 | 286 | 0 |
| PickHighlight | 497/544/623 | — | 623 | 0 |
| PickXtimes | 677/803/1006 | — | 1006 | 0 |
| RouteStick | 400/500/700 | 6.7/11.7 | 350 | 0 |
| StopCube | 121/236/579 | — | 579 | 0 |
| SwingXtimes | 447/495/573 | — | 573 | 0 |
| VideoPlaceButton | 899/965/1046 | 23.4/27.0 | 310 | 0 |
| VideoPlaceOrder | 918/1135/1336 | 23.8/37.5 | 298 | 0 |
| VideoRepick | 408/540/893 | 4.9/6.8 | 694 | 0 |
| VideoUnmask | 305/332/410 | 2.2/2.2 | 344 | 0 |
| VideoUnmaskSwap | 401/460/550 | 5.6/7.2 | 334 | 0 |

hard 400 局中执行帧超过 1301 的为 0 局（最大是 BinFill 的 1097）；xhard 48 局中有 2 局超过。

### 1.3 分段帧数（按 `simple_subgoal` 文本切段；相邻两段文本相同会被并成一段）

- **RouteStick**：xhard 三局的演示段全部是 50 的整数倍（50 / 100 / 150，100 和 150 是同方向连续段被合并）；执行帧 = 演示帧 = 50·L（L = 21/17/16）。hard 25 局同样如此：50×101 段、100×17 段、150×1 段。
- **PatternLock**：xhard 节点数 = 25（specs `path_nodes`），共 24 段；每段平均 818/24 = 34.1、872/24 = 36.3、837/24 = 34.9 帧，单段范围 21～56 帧（66/98/116 这几个值是合并段）。hard 单段最常见的是 35 帧。
- **VU/BU 的 pick / put down**：xhard（每环境 3 局 × 3 次 pick）中，VU pick 单段最大 125、put down 最大 52；BU pick 最大 109、put down 最大 51、按按钮 119。对照：原生 hard（15 容器布局）VU pick 最大 202、put down 最大 59；BU pick 最大 169、按按钮 130。

## 二、reset 布局可行性（任务 2；PH 每组合 1000 次，其余每组合 200 次）

| 环境 | 组合 | n | 成功 | 失败 | 成功率（95% CI） | 期望抽签次数 | 失败类型 | 每次 reset 墙钟 |
|---|---|---|---|---|---|---|---|---|
| PH | xhard1（pick 4 / spawn 7） | 1000 | 999 | 1 | 99.9%（99.4–100） | 1.001 | SceneGenerationError 放不满 ×1 | ~1.3 s |
| PH | xhard2（pick [4,5] / spawn 8） | 1000 | 987 | 13 | 98.7%（97.8–99.2） | 1.013 | 放不满（请求 8）×13 | ~1.3 s |
| PH | xhard3（pick [5,6] / spawn [8,9]） | 1000 | 962 | 38 | 96.2%（94.8–97.2） | 1.040 | 请求 8 ×7、请求 9 ×31 | ~1.2 s |
| PH | xhard 现值（pick [5,7] / spawn [8,10]） | 1000 | 894 | 106 | 89.4%（87.3–91.2） | 1.119 | 请求 8 ×1、9 ×32、10 ×73 | ~1.2 s |
| PH | 固定 N=8（pick [5,7]） | 1000 | 987 | 13 | **98.7%** | 1.013 | 放不满 | |
| PH | 固定 N=9 | 1000 | 929 | 71 | **92.9%** | 1.076 | 放不满 | |
| PH | 固定 N=10 | 1000 | 730 | 270 | **73.0%** | 1.370 | 放不满 | |
| BinFill | xhard1 投入 [4,5] | 200 | 200 | 0 | 100% | 1 | — | ~1.3 s |
| BinFill | xhard2 [4,6] | 200 | 200 | 0 | 100% | 1 | — | |
| BinFill | xhard3 [5,6] | 200 | 200 | 0 | 100% | 1 | — | |
| BinFill | xhard [5,7] | 200 | 200 | 0 | 100% | 1 | — | |
| PickXtimes | 干扰 1（共 4 块） | 200 | 200 | 0 | 100% | 1 | — | ~1.6 s |
| PickXtimes | 干扰 2（5 块） | 200 | 200 | 0 | 100% | 1 | — | |
| PickXtimes | 干扰 3（6 块，= xhard3 = xhard） | 200 | 200 | 0 | 100% | 1 | — | |
| SwingXtimes | 干扰 1 | 200 | 192 | 8 | 96.0% | 1.042 | 放置圆盘采样失败：First ×3、Second ×5 | ~1.8 s |
| SwingXtimes | 干扰 2 | 200 | 192 | 8 | 96.0% | 1.042 | 同上 | |
| SwingXtimes | 干扰 3（= xhard） | 200 | 192 | 8 | 96.0% | 1.042 | 同上 | |

要点：
- PH 固定 N 的实测（98.7 / 92.9 / 73.0%）与计划的离线数（98.7 / 93.4 / 71.8%）都落在彼此的误差范围内。新档成功率随难度单调下降（99.9 → 98.7 → 96.2 → 89.4%），全部高于 xhard。
- **xhard 有幸存者偏差**：它的成功局 spawn 分布是 8:9:10 = 350:302:242，名义上应各占三分之一；V5 抽签留档（drafts）里 PH 也是 12 次 attempt 失败 2 次。
- SwingXtimes 的 8 个失败 seed 在四个组合里**完全相同**（9100040、48、51、70、81、107、114、189）。失败发生在放置圆盘（target）采样，这一步在放干扰块之前，所以和干扰数无关。这说明 V5 的 xhard 本身就有约 4% 的 reset 失败（v5-01 抽签是 10 次 attempt 全部成功，样本太小没暴露出来）。计划 2.8 没有写 SX 的 reset 成功率，本项不算不一致，但不能写成「100%」。
- PX/SX 的干扰块都在所有取值点之后才放（源码注释 N5），干扰数少只会让放置更宽松；实测 PX 全部 100%，与之相符。

## 三、PH 干扰块数分布（任务 3，成功局，n=1000/组合）

| 档 | 实测干扰数 = spawn − pick | 计划表 |
|---|---|---|
| xhard1 | 3：999 | 3 ✓ |
| xhard2 | 3：484、4：503 | 3～4 ✓ |
| xhard3 | 2：251、3：489、4：222 | 2～4 ✓ |
| xhard | 1：134、2：210、3：283、4：181、5：86 | 1～5 ✓ |

## 四、逐条核对表

| 条目 | 计划原文摘要 | 核实方法 | 结果 | 备注（实测数字） |
|---|---|---|---|---|
| 1.3 评估步数口径 | 「`evaluation.py` 评估 1301 步」 | 读 `evaluation.py`、`episode_config_resolver.py`、`DemonstrationWrapper` | 一致 | `max_steps=1300` 在代码里变成 `max_steps_without_demonstration=1302`；只数非演示步，≥1302 截断，所以演示段不占预算 |
| 1.3 xhard 已有超 1301 的局 | 「xhard 本身已有超 1301 的局，那是 V5 现状」 | 48 局 h5 的执行帧 | 一致 | 48 局中 2 局超：BinFill ep0 执行 1523 帧、PickXtimes ep3 1309 帧（约多 7 帧，扣掉补录帧后仍超）。hard 400 局 0 局超（最大 1097） |
| 1.3 新档执行步 / 总步数 ≤ xhard | 「新档全部落在 hard 与 xhard 之间」 | 无法跑演示；只能对照 hard/xhard 的端点 | 无法核实（端点相符） | 两个端点：hard 执行帧最大 1097、xhard 最大 1523。BinFill、PX 的新档次数上界在 xhard 以下，推断合理，但没有实测 |
| 1.5 演示 25～35 s 不变 | 「演示 25～35 s … 不变」 | 按 30 fps 换算 xhard PL/RS 的演示帧 | xhard 一致；**对新档的表述有歧义** | xhard：PL 27.3/29.1/27.9 s，RS 35.0/28.3/26.7 s，全部在带内（RS ep0 正好在 1050 上界）。但按 2.11/2.12 的新档参数，PL xhard1～3 的演示约 8～21 段 × 35 ≈ 9～24.5 s，RS xhard1～3 为 400～700 帧 = 13～23 s，**全部低于 25 s**。V5 报告里的 `demo_frames_out_of_band`（`v5_generation.py` 的 `DEMO_BAND=(750,1050)`，作用于 PL/RS）会把新档全部记成越界。计划要写明「25～35 s 只约束 xhard」，并让报告按档豁免。另：VPB/VPO 的 xhard 演示 45～65 s，不在口径 9 的管辖范围内（口径 9 只管 PL/RS） |
| 2.3 帧数 | 「pick 最坏 125 + put down 52，全部 ≤ xhard」 | xhard VU/BU 分段帧数 | 一致（样本小） | xhard VU pick 最大 125、put down 最大 52；BU pick 109、put down 51。每环境只有 9 次 pick 样本，「最坏」的说法依据不足。原生 hard（15 容器）VU pick 最大 202、put down 59，但新档用的是 8 容器 xhard 布局，不能直接套用 |
| 2.7 BinFill reset | 「reset 成功率在 hard 与 xhard 之间（xhard 离线 100%）」 | 本机 reset，每组合 200 次 | 一致 | xhard1/2/3/xhard 全部 200/200。投入数不影响杂乱布局（12 块总数固定） |
| 2.8 PickXtimes 干扰 1/2/3 | 「xhard 机制，中心距 0.08、框 0.25」 | reset，每组合 200 次 | 一致 | 全部 200/200；`all_cubes` = 4/5/6 |
| 2.8 SwingXtimes 干扰 1/2/3 | 同上（0.08） | reset，每组合 200 次 | 一致（附注） | 全部 192/200 = 96.0%，失败 seed 各组合完全相同，都是圆盘采样失败，与干扰数无关。xhard 现值本身就有约 4% 的 reset 失败 |
| 2.9 PH reset 离线数 | 「N=8 98.7%、N=9 93.4%、N=10 71.8%」 | reset，每组合 1000 次 | 一致 | 实测 98.7% / 92.9% / 73.0% |
| 2.9 PH 新档成功率 | 「随 N 单调下降，全部不低于 xhard」 | reset，每组合 1000 次 | 一致 | xhard1 99.9%、xhard2 98.7%、xhard3 96.2%、xhard 89.4% |
| 2.9 PH 干扰数 | 「xhard2 3～4、xhard3 2～4」 | 成功局 spawn − pick | 一致 | 分布见第三节 |
| 2.11 PatternLock | 「每段约 35 帧 ⇒ xhard3 最长约 735 帧」 | xhard 分段帧数 | 基本一致 | 每段平均 34.1～36.3 帧；按 36.3 算，xhard3（22 节点 = 21 段）约 763 帧 ≈ 25.4 s，比计划的 735 多约 4%，可能刚好碰到 25 s 线 |
| 2.12 RouteStick | 「每段恒 50 帧；xhard3 执行段 ≤ 700」 | xhard 与 hard 分段 | 一致 | hard 与 xhard 全部段都是 50 的倍数；执行帧 = 演示帧 = 50·L，L=14 时正好 700 |
| 第五节盲区 | 「全部帧数与成功率来自离线副本，无一格跑过模拟器」 | — | 本审计部分补上 | PH/BinFill/PX/SX 的新档 reset 成功率已用真实模拟器实测；帧数仍未实测（没跑演示） |

## 已实测通过

- 1.3「xhard 已有超 1301 的局」：BinFill ep0 1523、PickXtimes ep3 1309；评估预算只数执行段，上限 1302。
- 1.5 在 xhard 上成立：PL 27.3～29.1 s，RS 26.7～35.0 s。
- 2.3 xhard 的 pick 125 / put down 52（小样本）。
- 2.7 BinFill 四档 reset 100%（各 200 次）。
- 2.8 PickXtimes 三档 reset 100%（各 200 次）；SwingXtimes 三档 96.0%，与 xhard 相同。
- 2.9 PH：离线 N=8/9/10 的数复现（98.7 / 92.9 / 73.0%）；新档 99.9 / 98.7 / 96.2%，全部高于 xhard 的 89.4%；干扰数区间相符。
- 2.11 PL 每段约 35 帧（34.1～36.3）；2.12 RS 每段恒 50 帧、xhard3 执行段 ≤ 700。

## 不一致需改计划

1. **1.5「演示 25～35 s 不变」要限定到 xhard**：PL/RS 的 xhard1～3 按设计就短于 25 s（PL 约 9～25 s，RS 13～23 s）。计划要明写口径 9 只约束 xhard，并在生成报告的 `DEMO_BAND` / `demo_frames_out_of_band` 里对新档豁免，或改成按档给出区间，否则报告会把 PL/RS 的新档全部标成越界。
2. **2.11 PL「xhard3 最长约 735 帧」偏乐观**：按实测每段均值上界 36.3 帧算约 763 帧（25.4 s）。不影响任何预算（执行段远低于 1301），只是数字要改成「约 735～765 帧」。
3. **2.8 SwingXtimes 的 reset 成功率要补上**：实测 xhard 及三档新档都是约 96%（圆盘采样失败，与干扰数无关），抽签上限要按 0.96 估，不能按 100% 估。这不是计划的错误陈述，只是缺了这一项。
4. **2.3「pick 最坏 125」的依据只有 9 个样本**：建议改成「xhard 实测最大 125（n=9）」，不要称「最坏」。

## 产物

- `artifacts/newtask-v6/plan-probes/audit/sec_D/h5_stats.py`、`h5_xhard.json/.log`（xhard 48 局）
- `artifacts/newtask-v6/plan-probes/audit/sec_D/h5_hard.py`、`h5_hard.json/.log`（data-0306 的 hard 400 局）
- `artifacts/newtask-v6/plan-probes/audit/sec_D/reset_probe.py`、`combos.txt`、`run_all.sh`、`run_ext.sh`、`reset/*.jsonl`（19 组合 × 200）、`reset_ext/*.jsonl`（PH 7 组合 × 800）、`summarize_reset.py`、`ph_1000_summary.txt`、`reset_run.log`、`reset_ext.log`
