# 新值模式 V6（定稿）：四档 xhard1～xhard4、交换对象均匀化、MoveCube 圆环区域

> 分支 `newtaskRelease-v5`，代码锚点 `da77662`（12.134；此后至本文件只改文档），依赖锚点（文件 sha256）`uv.lock` `ff0ffd847a55…` / `pyproject.toml` `d03537d6c77a…`。
> **前置文档**：V5 计划 [NEWTASK_RELEASE_V5_PLAN.md](NEWTASK_RELEASE_V5_PLAN.md)、V5 总报告 [docs/validation/newtask-v5/20260924-v5-final-report.md](docs/validation/newtask-v5/20260924-v5-final-report.md)、V5 规格 `scripts/configs/newtask-v5/v5-01/specs.jsonl`。
> **V5 决策除本文明确改动的以外全部延续**：原三档逐位冻结（V1 唯一硬闸门）、录像器冻结、`evaluation.py`/`run_example.py`/`dataset_replay.py` 与上游逐字节相同、L1(a)（新值流允许原地移位）、L4(b)（共用采样函数新参数默认等价关闭）、五入口冻结。
> **授权边界**：`src/robomme/` 改动免逐项事前批准，每步收尾在 `docs/validation/newtask-v6/` 出 md 报告（用户 2026-09-21 口头、2026-09-26 重申「免逐项批准、改完出报告」）。代码改动目前只在四个 worktree 副本里（`/data/hongzefu/v6-draft/*`），主仓库源码未动，副本分支不 push。
> **证据**：全部实测留档 `artifacts/newtask-v6/plan-probes/<议题>/report.md`（本机、不进 git，索引见第二部分六）。
> **简称**：VU/BU/VUS/BUS = Video/ButtonUnmask(Swap)，VPB/VPO = VideoPlaceButton/Order，VR = VideoRepick，PH = PickHighlight，PL = PatternLock，RS = RouteStick；「内环」= `spawned_bins`，「外环」= `distractor_bins`；源码路径省略前缀 `src/robomme/robomme_env/`。

# 第一部分（给人看）

## 一、用户决策列表

| # | 日期 | 用户原话（逐字） | 决策 |
|---|---|---|---|
| D1 | 09-25 | 「给出v6的方案 / 把movecube继续往外推 / unmask任务外部的swap 内部的swap 对象 / repick任务swap的对象 要做到碰撞检测后 对象层面的选择仍然均匀 / 并且对所有task 原版中有难度梯度的 也加入3个难度梯度 都要比现在的hard更难 / binfill按照数量 / unmask按照干扰/swap次数/pickup次数 / pattern/route按照难度 / pickhighlight按照干扰数量 pick数量 / videoplacebuttonorder你来定 给出方案 / swing pickxtimes按照数量 / 给出方案 我没考虑到的设置为代决 / 使用workflow/subagent辅助判定 不要全自己看」「汇总v6写入根目录」 | 范围 = 原版有梯度的 13 个环境各加三档；梯度维度按用户指定；MoveCube 往外推；Swap/Repick 交换对象在碰撞检测后仍均匀 |
| D2 | 09-25 | 「出图每次都目视检查 现在文字叠一起来」 | 出图必须 Read 目视检查再发 |
| D3 | 09-25 | 「圆形 放在可达范围的中心 而不是现在这样」「movecube这个同意 就这么做 固化到plan内」 | MoveCube 统一区域 = 以可达范围中心为圆心的圆环 |
| D4 | 09-25 | 「我需要做到局内均衡 给出Swap方案可视化图 内环外环分别是什么样的」 | 均匀性要求局内均衡；可视化已交付 |
| D5 | 09-25 | 「你现在有GL两个job的submit权限 …这个的意思是连接现有两个job 不允许开新job！」「参考这个对话 都在gl上跑 产物搬回data 不要在nfs上留大文件」 | GL 只 `srun --overlap` 连现有占位 job；产物搬回 `/data`；NFS 不留大文件 |
| D6 | 09-25 | 「V6plan内部所有的其他内容 也要全部详细检查 尽可能拿到实际测试」「可以先开始做代码的改动但是不要修改原文件以副本的形式保留下来」「反正你要用满这个时间尽可能的做 直到用户回来为止」 | 计划全文审计并实测；代码只在副本改 |
| D7 | 09-26 | 「M1：这个表格已经涵盖所有的梯度吗 现在这个数值可以」「m2不动」「m3不要做任何对拍xhard xhard是为了迭代的 只需要对拍之前的easy medium hard」「m4 a」「m5 b」「m6 s5」「m7 a」「m8同意」「m9 忽略原版的hard 和medium对比 原版的hard其实是另外一种单独的task」「m10 a」「m12 有干扰不用管内环数量了」「m13 免逐项批准、改完出报告」「m14 a」「四个副本分支不要 push」 | 见口径 3～13 |
| D8 | 09-26 | 「vpb vpo都是放回原位 xhard123 只在cube放target的步骤上有区分 给出难度梯度」 | VP 五档都放回原位，梯度 = 放到台上的次数 |
| D9 | 09-26 | 「改为xhard123 xhard现在xhard改为xhard4！原来的纯xhard废弃 不要再使用 容易混淆 每个难度要有区分 不能有重叠交集合 给出新的难度梯度表」 | 档名 xhard1～xhard4，`xhard` 废弃；四档区间互不重叠 |
| D10 | 09-26 | 「可以超过1300 新的四档表（hard 冻结不动）同意」「在第一部分不要留我md演进的过程 只保留用户决策列表 和最后定下来的计划」「把你已经定下来的分支和结论写入第二部分 新的agent可能无记忆要重新开始」 | 评估 1301 步不限制新档取值；四档表定稿；本文件结构；第二部分含接手指南 |

## 二、定稿口径

| # | 口径 |
|---|---|
| 1 | **原三档 easy/medium/hard 逐位冻结**（定义、reset 取值、演示 h5）；V1（16 环境 × 9 局与基线 `13e5151` 逐位比）是唯一硬闸门。 |
| 2 | **冻结文件**：录像器 `RecordWrapper.py`（`fail_safe_limit=5000`）、`scripts/evaluation.py`（`max_steps=1300`，2026-02-23 上游 MME-VLA 实验设定，只数执行段）、`run_example.py`、`dataset_replay.py` 与上游逐字节相同；`scripts/` 顶层五入口不增。**新档取值不受 1301 限制**（D10）；生成侧 5000 步 fail_safe 不动。 |
| 3 | **难度序 easy < medium < hard < xhard1 < xhard2 < xhard3 < xhard4**。现在的 xhard 改名 **xhard4**；档名 `xhard` 废弃，`VALID_DIFFICULTIES`、`config_xhard`、decision 子树键、`XHARD_*` 常量、`spec_kind` 一律改用 `xhard4` 命名，代码与配置里不再出现 `xhard`。 |
| 4 | **四档取值区间互不重叠**，并尽量与 hard 不重叠（D9）；xhard4 的数值为此可以重排（口径 7）。 |
| 5 | **范围**：13 个原版有梯度的环境（BinFill、PickXtimes、SwingXtimes、PH、VU、BU、VUS、BUS、VR、PL、RS、VPB、VPO）四档；MoveCube 只有 xhard4（圆环 U）；InsertPeg、StopCube 原 xhard 改名 xhard4、数值不动。 |
| 6 | **四档全部沿用现 xhard 的生成机制**（杂乱布局、精确 OBB、干扰环带、外环同步交换、HSV 任意色、拒绝采样等），只有用户指定维度的数值分档；机制型字段（框半宽、交换速度、间距、搜索预算、颜色表）沿 xhard 值不分档。单调性只查用户指定维度。 |
| 7 | **xhard4 不做任何对拍**（xhard 是为了迭代的）：16 个环境的 xhard4 在 V6 全部重新抽签，v5-01 的 xhard 规格作废。 |
| 8 | **交换对象均匀（VUS/BUS/VR）**：碰撞检测是硬约束，均匀在可行集合内实现；内环用 S5（可行槽对图 G 的边 − 上一对，参与次数最少者优先、平局均匀抽、禁止立即撤销，整条极差 >1 重排 ≤20 趟，G 不连通则 reset 重抽）；外环用 O4 均衡贪心 + 放置后序号随机重排，只做跨局均匀；藏 cube 的容器规则不动（bin_3 恒空，目视无区别）。 |
| 9 | **MoveCube xhard4 = 圆环 U**：圆心 (−0.06, 0)（实测可达环带中点）、内孔 0.12、外径 0.20；方块中心、goal 中心、杆抓取点共用；杆/方块 yaw 全 2π。 |
| 10 | **VPB/VPO 五档都 `return_to_origin`**，梯度 = 演示里「拿起→放到台上」的次数。 |
| 11 | **VR 的 hard（15 块静态）视为另一种任务**，新档只向 xhard4 内插，不与 hard/medium 比较。 |
| 12 | **规模**：13 × 3 新档 + 16 个 xhard4 = **55 格**，每格 10 候选、取 index 0/3/6 三局正式 = 550 候选、165 正式局；一次多 worker 生成。seed 偏移：xhard4 6e6、xhard1 8e6、xhard2 10e6、xhard3 12e6（公式 `offset + env_code×1e5 + episode×100 + attempt`，四段互不重叠，也不碰 V5 的 4e6 段）。 |
| 13 | **算力与流程**：GL 只 `srun --overlap` 连现有占位 job，不开新 job；逐局产物写节点 `/tmp` 即删，结果搬回 `/data`，NFS 不留大文件；长任务 tmux + Monitor；出图必须目视检查；代码改动先在副本 worktree，分支不 push；细节（取整、预算次数、平局规则）由实施方自决并在报告注明。 |

## 三、四档定稿表（hard 冻结不动；区间互不重叠）

| 环境 | 梯度维度 | hard | xhard1 | xhard2 | xhard3 | xhard4 | 备注 |
|---|---|---|---|---|---|---|---|
| BinFill | 投入块数（总块 12） | [3,5] | 6 | 7 | 8 | 9 | 无演示段，8/9 块约 1500～1900 步，允许超 1301 |
| PickXtimes | 次数 / 干扰块 | [4,5] / 0 | [6,7] / 1 | [8,9] / 2 | [10,12] / 3 | [13,15] / 3 | 干扰颜色表若 ≥4 色则 xhard4 取 4 |
| SwingXtimes | 轮数 / 干扰块 | 3 / 0 | [4,5] / 1 | [6,7] / 2 | [8,9] / 3 | [10,11] / 3 | reset 约 96%（放圆盘采样失败，与干扰无关） |
| PickHighlight | pick / 总块 | 3 / 6 | 4 / 7 | 5 / 8 | 6 / 9 | 7 / 10 | 干扰数 = 总块 − pick，均值全程 3（不作梯度）；总块 10 时 reset 73% |
| VideoUnmask | 干扰容器 / pick | 0（15 容器）/ 2 | 8 / 2 | 10 / 3 | 13 / 3 | 15 / 3 | pick ≤3（可藏 cube 的容器只有 3 个），靠干扰数区分；内环容器数不作梯度 |
| ButtonUnmask | 干扰容器 / pick | 0 / 2 | 8 / 2 | 10 / 3 | 12 / 3 | 14 / 3 | 同上 |
| VideoUnmaskSwap | swap / pick / 外环干扰 | [2,3] / 2 / 0 | [4,5] / 2 / 4 | [6,7] / 3 / 6 | [8,9] / 3 / 8 | [10,12] / 3 / 10 | 外环含 cube 数 = 干扰一半；交换步数 xhard1 50、其余 33 |
| ButtonUnmaskSwap | swap / pick / 外环干扰 | [2,3] / 2 / 0 | 4 / 2 / 4 | 5 / 3 / 6 | [6,7] / 3 / 8 | [8,9] / 3 / 10 | 同上 |
| VideoRepick | 块数 / swap / repick | 另一种任务 | 4 / [3,4] / 2 | 5 / [5,6] / 3 | 6 / [7,8] / 4 | 7 / [9,12] / [5,6] | 4～6 块 reset 约 60%；7 块待实测 |
| PatternLock | 节点数（5×5，不重访，预算 20000） | [4,8] | [9,12] | [13,16] | [17,20] | [21,25] | 执行段 ≤ 约 850 步 |
| RouteStick | 段数 L | [4,7] | [8,10] | [11,13] | [14,16] | [17,21] | 执行段 = 50·L |
| VideoPlaceButton | 放台次数（都放回原位） | 2（放桌面） | 1 块 3 次 | 1 块 4 次 | 2 块 5 次 | 2 块 6 次 | 额外放台 = 放到无关台（原版 `additional_place` 语义），见四.9 |
| VideoPlaceOrder | 总放台次数（都放回原位） | 1 块 v∈[2,4] | 2 块 (2,3)=5 | 2 块 (3,3)=6 | 2 块 (3,4)=7 | 2 块 (4,4)=8 | 每档总数定值，哪块多访问随机 |
| MoveCube | 不加档 | 原三档同值 | — | — | — | 圆环 U | 只有 xhard4 |
| InsertPeg / StopCube | 不加档 | 原三档同值 | — | — | — | 原 xhard 改名 | 数值不动 |

## 四、逐环境定稿（机制、实现落点、实测）

### 1. 难度档管道（全环境共用）

- `utils/difficulty.py`：`VALID_DIFFICULTIES = {easy, medium, hard, xhard1, xhard2, xhard3, xhard4}`；新增 `NEWVALUE_DIFFICULTIES`、`is_newvalue_difficulty()`、`newvalue_tier()`（1～4）、`require_xhard4_only()`（MoveCube/InsertPeg/StopCube 拒收 xhard1～3）。
- `utils/sampling_config.py`：新值键名集合剥离、按档核对结构、`fill_missing_newvalue`（只在同层已有 xhard4 时补缺档）；`spec_kind_for` 对四档返回 `native-newvalue/2`；`task_goal._unmask_pick_count`、`xhard_home_site.validate_demo_plan`、`unmask_swap_xhard` 全部族判断。
- 各环境：`config_xhard1..4` + 同结构 decision 子树，`NEWVALUE_DECISION[<tier>]` 替代 `XHARD_DECISION`；VUS 的 swap/pick 次数挂在 `native.parameters.configs[<tier>]`（decision 键无人读）；VR 的 `elif hard` 链前先族判断；RouteStick 缺键抛错。
- scripts：`v4_specs --difficulty <tier> --seed-profile v6`（默认参数与 V5 逐字节同）、`train_split_runner` 按档核验、`v4_rollout` 从 header 取档与 seed 规则、`v5_generation pipeline --tiers`、`train_split_config extract --release newtask-v6`、`DEMO_BAND=(750,1050)` 只对 xhard4 判定（新档 PL/RS 演示 9～25 s 是预期）；`v4_eval` 从规格行读档名无需改；`generate_dataset_newseed.py` 的 `extract_native_sampling`/`validate_sampling_config` 若在链路上则改族判断。
- tests：`test_v4_xhard_{pickxtimes,swingxtimes}`、`test_operand_scope.py`、`test_episode_action_sampling.py` 的 4 档断言改 7 档（`test_v4_xhard_stopcube` 不改）；`test_v4_specs::test_seed_rule_disjoint_from_existing_layouts` 扩 6e6/8e6/10e6/12e6 四段；`test_sampling_config_split` 改指 `newtask-v6` 快照；`NATIVE_SPEC_GOLDEN`/`NATIVE_AST_GOLDEN` 不动。
- 已实现（副本 `v6-draft-pipeline`，按旧档名 xhard 做，合入时改 xhard4 命名）：`"xhard"` 字面 130→40 行且业务比较清零；lightweight 失败集合与基线 46F/12E 逐条相同；V0 `NATIVE_DEFS_UNCHANGED=PASS envs=16`；16 环境 × 4 档 128 局 reset 的 spec/位姿 sha 与主仓库逐字相同；13 × 3 新档 76/78 reset 成功。

### 2. Unmask 四环境的交换对象均匀化（VUS/BUS，VR 同法）

- 内环：reset 时对 4 个位姿槽的 6 个槽对各跑一次 `check_swap_sweep_prefiltered` 得 G；G 不连通抛 `SceneGenerationError` 重抽；主流末尾追加一次抽取作规划种子，平局与重排在局部生成器上做；预规划整段序列（S5）；锁定循环里 xhard4 分支读预规划搭档，并在窗首显式做 `joint_sweep_from_actual` 复核；`_verify_swap_binding` 改为「规划对 + 扫掠可行」核验；`swap_initiators` 轮转语义作废，规格记 `actions.swap_pairs.<k>`；藏 cube 规则不动。
- 外环：`plan_distractor_swaps` 改 O4（每窗可行槽对里取参与次数最少者、禁止立即撤销），放置后 `randperm(count)` 重排序号（记为取值点 `label_perm`）；vis → btn → inner_clear → exact 四道判定不动；G_k 为空整段重抽。
- VR：搭档规划改 S5（全部可行对、5 mm 余量、按钮当障碍、有孤立块则拒），`swap_partner_u` → `swap_plan_seed`，`resolve` 允许任意方向。
- 实测：离线 10000 局 VUS/BUS/VR 极差 ≤1 100% / 99.8% / 95.7%，撤销 0，卡方 p 0.998 / 0.937 / 0.994；GL 真演示 292 局（`plan-probes/swap-real/`）：三环境各 48 局演示 48/48（V5 对照各 24/24），局内极差 ≤1 100% / 100% / 93.8%，撤销 0，逐控制步真实碰撞盒复核零拒绝，规划序列 = 执行序列；外环 O4 未参与 28% / 40%、撤销 0.4% / 3.3%（V5 45%/52%、44%/46%）；reset 接受率 VUS 92%、**BUS 63%（G 不连通拒 37%，用户接受）**、VR 61%（与 V5 同种子逐局相同）。副本 `v6-draft-swap`：原三档 36 局逐字节相同。
- 验收：`UNMASK_INNER_UNIFORM=PASS env=<E> chi2_p>=0.05 range_le1>=0.99 undo=0`、`VR_UNIFORM=PASS range_le1>=0.93 undo=0 all_participate=1`、`OUTER_SWAP_BALANCE=REPORT`、`UNMASK_G_REJECT=REPORT`。

### 3. VideoUnmask / ButtonUnmask

8 个内环容器 + 贴身环带干扰（沿 xhard4 机制：环带、密度推导、三色轮转、停放点、`min_gap_factor` 0.75），干扰数按表，干扰少时环带稀疏放置；外环含 cube 数 = 干扰数一半。实测：新档各 6 局演示全成功，pick 段最大 126 帧、put down 53 帧。验收 `UNMASK_RING=PASS`。

### 4. VideoUnmaskSwap / ButtonUnmaskSwap

swap/pick/外环干扰按表；xhard1 交换步数 50（与 hard 同），xhard2 起 33；外环从 xhard1 起每窗一次同步交换；外环方环 [0.2675,0.45]（按 max(|x|,|y|) 判）。实测：新档各 6 局演示全成功；BUS 评估步 ≤ 约 820。验收沿 V5（外环窗口数 = n_swaps、`bin_collision=0`）+ 第 2 条均匀性判定。

### 5. VideoRepick

块数/swap/repick 按表；沿 xhard4 机制（杂乱区、中心距 0.12、按钮入障碍、reset 预规划）+ S5。实测：4/5/6 块 reset 成功率 0.625/0.629/0.59（7 块待实测）；通过 reset 的局演示全成功。

### 6. MoveCube（只有 xhard4：圆环 U）

方块中心、goal 中心、杆抓取点（杆尾 = 杆根 − 0.10·u）共用圆环 0.12 ≤ |p − (−0.06, 0)| ≤ 0.20；保险条件离基座 0.35～0.76；0.10 ≤ |方块 − goal| ≤ 0.30，推起点（后退 0.10、带杆再侧移 ±0.10）离基座也在 0.35～0.76；杆：抽抓取点 + yaw∈U(−π,π) 推杆根，杆身线段不进内孔，方块离杆身 ≥0.04、goal 离杆身 ≥0.02；方块 yaw 全 2π。参数放 `demo_layout.xhard4.region` / `execution_layout.xhard4.region`（`center, r_in, r_out, base_dist, push_len_max, peg_gap, goal_peg_gap`），`spawn_random_cube/target` 新增 `annulus/base_band/segment_clearance/push_feasible` 四个可选参数（默认 None 整段跳过），方块预算 4096；回放按同一规则复核。
实测依据：末端可达图 57288 次规划、抓杆可达图 12276 次真抓（可达硬边界离基座 0.31～0.80 m，与 yaw 无关）；GL 真演示 144 局 **120/144**（peg_push 35/48、gripper_push 37/48、grasp_putdown 48/48），失败全为推动接触、与位置无关。副本 `v6-draft-movecube`：真实 reset 2000 局 `MC_REGION=PASS violations=0`，原三档逐字节相同。图 `reach/U/unified_region_v2.png`、`reach/U/gl2/u2_results.png`。验收 `MC_REGION=PASS violations=0 layout_fail=0`、`MC_DEMO=REPORT`。

### 7. BinFill / PickXtimes / SwingXtimes / PickHighlight

数值按表，机制沿 xhard4（BinFill 杂乱布局 + 精确 OBB + 同色团 ≤3；PickX/Swing 框 0.25、中心距 0.08、精确 OBB、均匀无偏置、干扰色取前 k 色；PH HSV 任意色、精确 OBB，保持 `spawn_lo ≥ pick_hi`）。实测（GL 273 局）：四环境新档演示级全成功（BinFill 5/6、6/6、4/6 为原有 DatasetGenerationError 类型），reset：BinFill/PickX 100%、Swing 96%、PH 新档 99.9%/98.7%/96.2%；PickX xhard3/4、BinFill xhard3/4、PH xhard4 会超 1301 步（允许）。

### 8. PatternLock / RouteStick

节点数 / 段数按表；PL 5×5 不重访、DFS 预算 20000（三档耗尽 0，平均尝试 ≤5.3 次）；RS 每段恒 50 帧、缺键抛错。实测：各档 3/3～6/6 成功，步数 PL 824/1166/1326（xhard 对照 1720）、RS 1316/1473/1718（2220）。

### 9. VideoPlaceButton / VideoPlaceOrder

现行结构：VPB hard = 1 块：放 before 台 → 按按钮 → 放 after 台 → 放桌面；xhard4 = 2 块各 before/after → 各放回原位。VPO hard = 1 块依次访问 v∈[2,4] 张台（按钮插在某次后）→ 放桌面；xhard4 = 2 块各 v∈[2,4] → 各放回原位。
定稿：五档 `demo_return_policy = return_to_origin`；VPB 放台次数 3/4/5/6（1 块时在按钮前/后多放到无关台，沿用原版 `additional_place` 的 pre/post 语义；2 块时 5 = 一块 3 次一块 2 次，6 = 各 3 次），需在 xhard4 任务表构造里实现按档额外放台段；VPO 总放台 5/6/7/8，两块的访问数按档定值分配（哪块多随机），用副本已加的 `visit_count_range`/`demo_object_count` 按档取值。副本 `v6-draft-vp` 另实现的 `return_last_only`/不放回落点保留不启用。实测：(k1,放回)、(k2,各种 v) 各组合本机与 GL 演示全成功，reset 失败只来自 VPO 既有的 Target 4 放不下（约 50%）；VPB/VPO xhard 同 seed h5 与基线逐字节相同。验收 `VP_TIERS=REPORT`（每档实抽放台次数均值单调）。

### 10. InsertPeg / StopCube

原三档不动；原 xhard 改名 xhard4，数值不动，随其余 xhard4 重新抽签。

## 五、对拍、验收与实施步骤

### 5.1 两件事分开：对拍原三档（本机）与生成四档（GL）

**对拍 V1（唯一硬闸门，只对原三档）**：

| 项 | 内容 |
|---|---|
| 对拍什么 | easy / medium / hard 三档，16 个环境 × 3 档 × 3 局 = **144 局**（清单 `scripts/parity/manifest_16x3.json`） |
| 两侧 | 基线侧 = `13e5151` 的代码（worktree），V6 侧 = 合并后的主分支代码；同一批 seed |
| 判定 | 逐局 h5 SHA 逐字节相同、规格字段零不一致：`NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0` |
| 在哪跑 | **本机**（两侧必须同一台机器、同一 GPU 架构，跨架构逐位必然不同；V5 实测每侧约 3 h） |
| 不对拍的 | xhard1～xhard4 一律不对拍（口径 7） |

**生成 v6-01（正式数据）**：

| 档 | 环境数 | 每格候选 / 正式 | 候选 | 正式局 |
|---|---|---|---|---|
| xhard1 | 13 | 10 / 3 | 130 | 39 |
| xhard2 | 13 | 10 / 3 | 130 | 39 |
| xhard3 | 13 | 10 / 3 | 130 | 39 |
| xhard4 | 16（13 + MoveCube + InsertPeg + StopCube） | 10 / 3 | 160 | 48 |
| 合计 | 55 格 | | 550 | 165 |

- 候选 = 抽签（只 reset，不跑演示），每格 10 个；正式局 = 每格取候选 index 0/3/6 跑完整演示；抽签失败按 M4 上限 60 次递补，如实报 shortfall。
- 在哪跑：**全部在 GL**，两个占位 job 各 `srun --overlap` 16 worker（`OMP_NUM_THREADS=1`，driver 不用 `max_tasks_per_child`），逐局产物写节点 `/tmp`，正式局的 h5/视频与规格搬回 `/data`，NFS 不留大文件。
- 原三档不重新生成数据。

### 5.2 链路与验收判据

链路：源码 → `train_split_config extract --release newtask-v6` → `scripts/configs/newtask-v6/sampling_config.json` → `v4_specs draw --difficulty <tier> --seed-profile v6` → `freeze` → `v4_rollout run` → 报告；推理 `v4_eval` 不改。

| 判据 | 查什么 | 在哪 | 判定行 |
|---|---|---|---|
| V0 | 原三档 config（StopCube/MoveCube/InsertPeg 为 `config_native`/`_CONFIG_CURRENT`）与原三档消费的 `NATIVE_SAMPLING` 键零 diff；剥掉四个新值键后 decision 与 V5 快照逐字相同 | 本机静态 | `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0` |
| LIGHTWEIGHT | `tests/lightweight/ -m 'not gpu and not slow'`，失败集合与 S0 基线（46 failed / 12 errors）相同 | 本机 | `LIGHTWEIGHT=PASS failure_set_equal_baseline=1` |
| **V1** | 见 5.1 | 本机 | `NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0` |
| FROZEN_FILES | 录像器对 `da77662` 零 diff；三脚本与官方副本逐字节同；五入口 | 本机静态 | `RECORDER_FROZEN=PASS EVAL_PY_UPSTREAM=PASS ENTRIES=5` |
| TIER_MONOTONE | 每环境每档 200 局离线 reset：用户指定维度均值严格递增且区间不重叠（`scripts/parity/v6_tier_monotone.py`） | 本机 | `TIER_MONOTONE=PASS envs=13 violations=0` |
| 均匀性 / 区域 | 第四节 2、6 的判定行 | 本机离线 + 生成报告 | 同上 |
| 生成报告（不设门槛） | 每格 draft/rollout/backfilled/shortfall；均匀性统计；MoveCube 区域违例 | GL | `V6_GENERATION=REPORT cells=55 …` |

### 5.3 实施步骤

| 步 | 内容 | 在哪 | commit（自 12.150 起顺延） |
|---|---|---|---|
| S0 | 存 LIGHTWEIGHT 基线；V1 基线侧（`13e5151` worktree）144 局开跑 | 本机 | — |
| S1 | 合并四个副本到主分支：管道改 `xhard4` 命名、四档 config 按第三节表填值、S5/O4、MoveCube U、VP 放台段、单调检查器；恢复 V5 快照原样、另起 `newtask-v6` 快照；V0 + LIGHTWEIGHT + FROZEN_FILES + TIER_MONOTONE | 本机 | 12.150～12.153 + 报告 |
| S2 | 本机演示探针：每格 ≥2 局（VUS/BUS/VR 各档 4 局、MoveCube 12 局）；VR 7 块 reset 率实测 | 本机 | 12.154 + 报告 |
| S3 | V1 V6 侧 144 局 + 与基线侧比 | 本机 | 12.155 |
| S4 | 抽签 550 候选 + 生成 165 正式局（5.1 表） | GL | 12.156 + 生成报告 |
| S5 | 总报告、`scripts/README.md` 更新、收尾只留正式产物、`scancel` 占位 job | 本机 + GL | 12.157 |

规模与时间（估）：V1 两侧各约 3 h（本机）；生成约 2 h（GL 两席）；产物峰值约 230～270 GB（`/data` 余 2.4 TB）。

# 第二部分（技术细节，供 agent 追踪）

## 〇、接手指南（新 agent 无记忆时从这里开始）

**仓库与分支**

| 项 | 值 |
|---|---|
| 主仓库 | `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-v5`，upstream `origin/newtaskRelease-v5`（GitHub `hongzefu/robomme_benchmark_MotionJEPA`）。源码相对锚点 `da77662` 未改，只有本计划与 `docs/greatlakes.md` 更新到 12.148+ |
| V1 基线 commit | `13e5151`（12.63） |
| GL 侧仓库 | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl`（本机已挂载可直接读写；已切到 `newtaskRelease-v5`、`uv sync` 完成；官方隔离源码树在其 `artifacts/train-parity/local-smoke-01/official-src/`，7.5 MB，`.official_tree` 标记 `1d4c1369…`）。历史 `artifacts/` 有 654 GB 旧产物，不是 V6 的，不要动 |
| 官方源码树（本机） | `artifacts/train-parity/local-smoke-01/official-src/scripts/data-generation/generate_dataset.py`，规格回放 worker 用 `scripts/parity/train_split_worker.run_one` |
| venv | 主仓库 `.venv`（editable 安装指向主仓库 src）。在副本里跑代码必须 `cd <副本> && PYTHONPATH=$PWD/src /data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv/bin/python …`，先 `python -c "import robomme;print(robomme.__file__)"` 确认指向副本 |

**四个代码副本（git worktree，分支从 `e1755f9` 切出，全部已 commit、工作区干净、不 push）**

| worktree | 分支 / commit | 内容 | 合入时要改 |
|---|---|---|---|
| `/data/hongzefu/v6-draft/pipeline` | `v6-draft-pipeline` / `891180f`（51 文件 +1774/−315） | 难度档管道：族常量与 `require_xhard_only`、键名集合剥离、`fill_missing_newvalue`、13 环境 `config_xhard1/2/3` + decision 子树（数值是 09-25 的旧表）、三环境拒收新档、`v4_specs --difficulty/--seed-profile`、runner/rollout/generation/config 按档、`test_v6_difficulty_tiers.py`；报告 `plan-probes/impl-pipeline/report.md` | 档名 `xhard` → `xhard4` 全量改名（含常量、config、decision 键、spec_kind `native-newvalue/2`）；数值按第一部分第三节表重填（四档不重叠）；VP 的「不放回」占位删掉改 `return_to_origin`；`test_episode_action_sampling` 扩 7 档未做；V6 快照未导出 |
| `/data/hongzefu/v6-draft/movecube` | `v6-draft-movecube` / `7adbca5`（6 文件 +801/−367） | MoveCube 圆环 U：`object_generation.spawn_random_cube/target` 四个可选参数、`config_xhard.center_exclusion` → `region`、`_load_scene_xhard_region`、`test_v6_xhard_movecube_region.py`；报告 `plan-probes/impl-movecube/report.md` | **该副本把 V5 快照 `scripts/configs/newtask-v5/sampling_config.json` 就地重导了（只有 MoveCube xhard 两段 diff）→ 合入时恢复 V5 快照原样、另起 `newtask-v6` 快照**；键名 `xhard` → `xhard4` |
| `/data/hongzefu/v6-draft/swap` | `v6-draft-swap` / `fec4d98`（10 文件 +1035/−91） | 新文件 `utils/swap_uniform.py`（G、S5、序列复核、O4）；VUS/BUS `decision.xhard.swap_plan_v6`（含 M5 开关 `hidden_bin_permutation_size=4`）、外环 `label_perm`、锁定循环读预规划 + 窗首复核；VR `swap_plan_seed`；4 个锁旧配置的测试更新；`test_v6_swap_uniform.py`；报告 `plan-probes/impl-swap/report.md` | **M5 已定 (b) 不动 → 合入时把 `hidden_bin_permutation_size` 设回 3（或删键）**；键名 `xhard` → `xhard4`；`test_snapshot_matches_source` 对 V5 快照失败属预期，V6 快照重导后消失 |
| `/data/hongzefu/v6-draft/vp` | `v6-draft-vp` / `9b51421`（7 文件 +646/−27） | `xhard_home_site.validate_demo_plan` 放行三种策略、避障落点 `plan_goal_drop_xy/build_goal_drop_sites`；VPB/VPO `_build_xhard_final_sites`；VPO `xhard.visit_count_range`；`vqa_options` drop 候选；`scripts/parity/v6_tier_monotone.py` + `test_v6_tier_monotone.py`；报告 `plan-probes/impl-vp/report.md` | 五档都 `return_to_origin`（D8）→ `return_last_only`/不放回代码保留不启用；**VPB 按档额外放台段（放到无关台）未实现，要新做**；VPO 每档总放台定值的分配逻辑要新做；`v6_tier_monotone.PLAN_TIERS` 按第三节表更新 |

合并顺序建议：pipeline → swap → movecube → vp（后三者只动各自环境文件与少量共用件，冲突点是 `sampling_config.py`、`xhard_home_site.py`、各环境 `config_xhard*`、V5 快照与测试文件）。合并后先做 V0、LIGHTWEIGHT，再逐环境 reset 冒烟。

**已完成的实测（都在 `artifacts/newtask-v6/plan-probes/`，可直接引用，不必重跑）**

| 目录 | 结论 |
|---|---|
| `reach/A`、`reach/B`、`reach/C`、`reach/U` | MoveCube 可达硬边界离基座 0.31～0.80 m（与 yaw 无关）；圆环 U 定义 `reach/U/region.py`；GL 144 局 120/144 |
| `unmask/`、`unmask/viz/`、`swap-real/` | S5/O4 离线与 GL 292 局真机验证（三环境 48/48） |
| `tiers/` | 13 × 3 新档（旧表数值）× 6 局 + xhard 对照 273 局：37/39 格演示级 100%，失败仅既有 reset 拒绝；`tables.md` 有每格步数 |
| `audit/` | 计划四段审计逐条核对表（数字全部逐位复现） |
| `impl-*/` | 四个副本各自的改动、测试、reset 逐字比、真演示 |

**GL 现状**：占位 job `61890467`（gl1526）与 `61890468`（gl1517），各 1 GPU/16 CPU/192 G/48 h，2026-09-25 约 16:00 起跑，属 V6 生成任务；只许 `srun --jobid=<ID> --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared`，不许 sbatch/scancel 其它 job；生成完成 commit 后按这两个 ID `scancel`。登录 `ssh -o BatchMode=yes greatlakes`（ControlMaster 复用，不弹认证；失败就停下问用户认证方式）。NFS 上 V6 目录已清空。

**踩过的坑（不要再踩）**：driver 用 `ProcessPoolExecutor(max_tasks_per_child=N)` 在 spawn 上下文换代点必挂死（GL 两次）；`RobommeRecordWrapper` 的 h5 逐帧记录挂在 `save_video` 上，关视频会让全部局判失败；`generate_dataset_newseed._worker` 只认 `episode_spec`，MoveCube 等只认 `native_episode_spec`，规格回放走 `train_split_worker.run_one`；VUS 的 swap/pick 次数读 `native.parameters.configs[档]` 不读 decision；VUS/BUS 交换对、VR 发起者方向不是规格取值点（S5 需新增取值点）；出图用 `Noto Sans CJK JP`，出完必须 Read 目视检查；GL 上 NFS `rm -rf` 偶尔报 Directory not empty，重试即可。

**下一步**：从第一部分 5.3 的 S0/S1 开始（S0～S3 本机，S4 GL）。

## 一、红线

N1 原三档路径不新增、不挪动任何随机抽样。N2 录像器、`evaluation.py`、五入口冻结。N3 第一部分决策清单以外不自加设计；细节自决并在报告注明。N4 新值流按 L1(a) 允许原地移位；xhard4 不对拍。N5 共用函数新参数默认等价关闭，`NATIVE_SPEC_GOLDEN`/`NATIVE_AST_GOLDEN` 不动。N6 碰撞检测不为均匀让路。N7 每档在用户指定维度上均值严格递增且区间不重叠。N8 文档禁硬编码行号。N9 Agent 工具派的 subagent 一律 opus、并行不设上限；workflow 需逐次审批且其 `agent()` 只用 sonnet（收尾/计划类最多 3 次 opus）、`model` 不得省略。N10 长任务 tmux + Monitor；GL 只 `srun --overlap` 连现有 job。

## 二、按文件的改动落点

| 环境 / 文件 | decision 子树键（按 `<tier>` = xhard1..4） | 方法 |
|---|---|---|
| `utils/difficulty.py`、`sampling_config.py`、`episode_spec.py`、`task_goal.py`、`xhard_home_site.py`、`unmask_swap_xhard.py`、`xhard.py`、`unmask_distractor_sampler.py`、`unmask_distractors.py` | 键名集合、`fill_missing_newvalue`、`spec_kind native-newvalue/2` | 族判断 |
| BinFill | `decision.configs.<tier>.{layout_mode: clutter, color_mix}`（投入色沿 xhard4） | `_spawn_cubes_xhard` 读档位 |
| PickXtimes / SwingXtimes | `<tier>.{distractor.colors（长度即干扰数）, min_center_dist_m}`（`corner_bias` 已删不得写回） | 干扰颜色取前 k 色 |
| PH | `<tier>.{block_color_policy, block_color_hsv}` | — |
| VU / BU | `<tier>.distractor.{count, cube_count_range}`、`bin_layout_policy.<tier>.min_gap_factor` | 环带稀疏放置 |
| VUS / BUS | `<tier>.{distractor, distractor_swap, swap_speed_multiplier, swap_plan_v6}`；swap/pick 次数在 `native.parameters.configs[<tier>]` | `utils/swap_uniform.py`（S5、G、O4），锁定循环读预规划 + 窗首复核 |
| VR | `<tier>.layout.min_center_dist_m 0.12`、`<tier>.swap_plan.partner_rule: balanced`、`num_repeats_range.<tier>` | `_plan_swap_partners_xhard` 改 S5；死代码 `_compute_dynamic_swap_candidates`/`_select_swap_pair_from_positions` 删除 |
| MoveCube | `demo_layout.xhard4.region`、`execution_layout.xhard4.region` | `spawn_random_*` 四个可选参数；杆改抽抓取点 |
| PatternLock | `path_length_range.<tier>`、`<tier>.path_search_max_attempts 20000` | — |
| RouteStick | `<tier>.segment_count_range` | 缺键抛错 |
| VPB / VPO | `<tier>.{demo_object_count, demo_return_policy: return_to_origin, extra_place_before/after（VPB）, visit_count_range / visit_counts（VPO）}` | xhard4 任务表构造加额外放台段；`validate_demo_plan` 按档 |
| `scripts/parity/v4_specs.py`、`v4_rollout.py`、`v5_generation.py`、`train_split_config.py`、`train_split_runner.py` | `--difficulty`、`--seed-profile v6`、`--tiers`、`RELEASE_NOTES newtask-v6`、header 取档 | 产物 `artifacts/newtask-v6/v6-01/<tier>/…`、快照 `scripts/configs/newtask-v6/v6-01/<tier>/specs.jsonl` |

## 三、runbook（参数名以 S1 实现为准）

```bash
# 只读核验
git diff --quiet da77662 -- src/robomme/env_record_wrapper/RecordWrapper.py && echo RECORDER_FROZEN=PASS; ls -1 scripts/*.py | wc -l   # 期望 5
# 每次提交前（与 V5 S0 基线同口径）
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
# 单环境演示探针
uv run --no-sync python -m scripts.parity.v4_demo_probe --task <Env> --difficulty <tier> --n 4 --out artifacts/newtask-v6/demo-probe/<Env>-<tier>
# V1
uv run --no-sync python scripts/parity/train_split_parity.py run --manifest scripts/parity/manifest_16x3.json …
uv run --no-sync python scripts/parity/train_split_parity.py compare --run base=artifacts/newtask-v6/v1/base --run v6=artifacts/newtask-v6/v1/v6 --pair base/B:v6/B
# 生成（GL 占位 job 内；本机同理去掉 srun）
mkdir -p artifacts/newtask-v6/v6-01
srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared bash -c "OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.v5_generation pipeline --run-id v6-01 --tiers xhard1,xhard2,xhard3,xhard4 --official-root artifacts/train-parity/local-smoke-01/official-src --draw-workers 16 --workers 16 2>&1 | tee artifacts/newtask-v6/v6-01/run.log; echo EXIT_CODE=\$? >> artifacts/newtask-v6/v6-01/run.log"
```

## 四、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | `xhard` → `xhard4` 全量改名漏一处（src 143 行字面、61 行比较、scripts 14 行） | grep `"xhard"` 归零作 S1 验收；每环境每档一次 reset 断言 `spec_kind` 与档名 |
| 2 | BUS G 不连通 reset 拒绝约 37%、VR 约 40%、VPO 约 50% | 抽签上限 60；如实报 shortfall |
| 3 | 外环局内不均匀 | 只报告未参与数 |
| 4 | MoveCube 两种推法约 25% 推没到位（与位置无关，V5 同量级） | 已实测；S2 只做回归 12 局 |
| 5 | VPB 额外放台段是新实现；VR 7 块 reset 率未测 | S2 本机探针 |
| 6 | AST 锁：内环预填搭档会跳过锁定循环的运行时复核分支 | 窗首另挂复核（副本已做），锁定测试保持通过 |
| 7 | 多 worker driver 用 `max_tasks_per_child` 会在 spawn 换代点挂死（GL 实测两次） | 不用该参数 |
| 8 | 产物峰值约 230～270 GB | `/data` 余 2.4 TB，起跑前再核 |

## 五、留档与 commit 纪律

沿 V5：每步一份 `docs/validation/newtask-v6/<日期>-<步>.md`；commit 只 add 本步文件，message 沿 `<大版本>.<小版本> 中文描述`；探针留 `artifacts/newtask-v6/plan-probes/`（不进 git）；收尾只保留正式 h5/视频与规格；GL 生成完成 commit 后 `scancel` 本任务的占位 job。

## 六、证据索引（`artifacts/newtask-v6/plan-probes/`）

| 议题 | 目录 | 内容 |
|---|---|---|
| 难度框架 | `difficulty-framework/` | 管道 `"xhard"` 分布、四档参数总表 |
| MoveCube 离线 | `movecube/` | 离线副本 mc_v6.py、环带扫描、viz |
| MoveCube 实测 | `reach/A`、`reach/B`、`reach/C`、`reach/U` | 末端可达图、抓杆可达图、放宽区域真演示、圆环 U 定义与 GL 复测（unified_region_v2.png、gl2/u2_results.png） |
| Unmask 均匀化 | `unmask/`、`unmask/viz/`、`swap-real/` | 离线蒙特卡洛、6 张方案图、GL 292 局真机验证（swap_real.png） |
| VideoRepick | `videorepick/` | 可行图与 S5 离线 |
| 计数类 / 路径放置类 | `count-tasks/`、`path-place-tasks/` | 离线扫描 |
| 新档真演示 | `tiers/` | 13 × 3 × 6 + 对照 273 局（tables.md、tiers_summary.png） |
| 计划审计 | `audit/` | 四段逐条核对表 |
| 副本实现报告 | `impl-pipeline/`、`impl-movecube/`、`impl-swap/`、`impl-vp/` | 各副本的改动、测试、实测 |
