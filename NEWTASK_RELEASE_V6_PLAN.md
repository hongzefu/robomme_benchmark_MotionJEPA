# 新值模式 V6：hard 与 xhard 之间插入 xhard1/2/3、交换对象均匀化、MoveCube 环带外推

> 本方案以用户 2026-09-25 的两轮要求为准，**只规划，不实施**。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，
> 分支 `newtaskRelease-v5`，代码锚点 `da77662`（12.134；此后到 12.139 只改文档与 `docs/greatlakes.md`，src/scripts/tests/依赖零改动，审计 A 段核实）。commit 编号沿用 `<大版本>.<小版本> <中文描述>`；S1～S7 的编号自 12.140 起顺延（12.136～12.139 已被计划文档占用）。
> 依赖锚点（文件 sha256）：`uv.lock` `ff0ffd847a55…` / `pyproject.toml` `d03537d6c77a…`。
>
> **前置文档**：V5 计划 [NEWTASK_RELEASE_V5_PLAN.md](NEWTASK_RELEASE_V5_PLAN.md)（口径 1～14、L1～L54）；V5 总报告
> [docs/validation/newtask-v5/20260924-v5-final-report.md](docs/validation/newtask-v5/20260924-v5-final-report.md)；V5 正式快照
> `scripts/configs/newtask-v5/v5-01/specs.jsonl`（160 候选、48 正式局）与实跑产物 `artifacts/newtask-v5/v5-01/rollout/run1/`。
> **V5 决策除本文 1.5 明确推翻或修改的以外全部延续**：原三档逐位冻结（V1 唯一硬闸门）、录像器冻结、`scripts/` 顶层五入口、
> `scripts/evaluation.py` 与上游逐字节相同、L1(a)（新值流允许原地移位）、L4(b)（共用采样函数各环境各加显式参数）。
>
> **规划期证据**：2026-09-25 一次规划期调查（6 个议题并行、各由一个 opus subagent 只读完成，未启动 workflow），
> 六份调查报告与探针留在 `artifacts/newtask-v6/plan-probes/<议题>/report.md`（本机留档、未进 Git，索引见第二部分七）。
> 数字全部来自与仓库纯函数或 v5-01 冻结规格逐值对齐过的离线副本，模拟器实跑样本为零，只当规划期估计，不能当验收结论。
> **例外：MoveCube 统一区域 U（2.6）是 2026-09-25 第二次调查用真实模拟器实测的**（本机三路可达探针 + greatlakes 144 局真演示），见 `artifacts/newtask-v6/plan-probes/reach/`。
> **调查是按第一轮口径（三档都比 xhard 更难）做的**，第二轮口径改为「三档落在 hard 与 xhard 之间」后，
> 外推的上限探测（放大框、预算、评估步数）不再需要，但现状刻画、均匀性算法、MoveCube 外推三块结论原样有效。
>
> **授权边界**：本文是计划，不是实施授权。`src/robomme/` 改动沿 V4/V5：免逐项事前批准，每步收尾在 `docs/validation/newtask-v6/`
> 出 md 报告。录像器 `src/robomme/env_record_wrapper/RecordWrapper.py` 全程冻结（`fail_safe_limit=5000`）。
> **1.4 的待决项 M1～M9 一个都不许在实施时自行取建议值**；取整、预算次数、平局规则、seed 偏移这类细节由实施方自决并在报告注明。
>
> **简称**：VU/BU/VUS/BUS = Video/ButtonUnmask(Swap)，VPB/VPO = VideoPlaceButton/Order，VR = VideoRepick，PH = PickHighlight；
> 「内环」= `spawned_bins`，「外环」= `distractor_bins`；源码路径省略前缀 `src/robomme/robomme_env/`。

# 第一部分（给人看）

## 一、用户决策

**一句话方案**：难度序列变为 **easy < medium < hard < xhard1 < xhard2 < xhard3 < xhard**，现有 xhard 保持最难档。
对**原版 easy/medium/hard 有梯度的 13 个环境**，在 hard 与 xhard 之间插入三档：**新档一律沿用 xhard 的生成机制**
（杂乱布局、精确 OBB、干扰环带、外环同步交换、HSV 任意色、拒绝采样等），**只把数值从 hard 一侧向 xhard 一侧逐档内插**，
每档在用户指定的维度上均值单调上升。同时修三处 xhard 本身并随新档共用：**MoveCube 三物体改为「机器人能抓到的最大区域、挖掉桌心」的统一区域 U**（实测定界），
**VUS/BUS 内环与外环的交换对象、VR 的交换对象在碰撞检测之后按对象层面均匀选取**。原三档逐位不变（V1）；
InsertPeg、StopCube 原版无梯度，一字不动。所有新档与重冻的 xhard 抽签冻成 `v6-01`，链路与闸门沿 V5。

按环境说（明细与依据见第二节）：

| 环境 | 梯度维度 | hard → xhard1 → xhard2 → xhard3 → xhard |
|---|---|---|
| BinFill | 数量（投入块数） | 投入 [3,5] → [4,5] → [4,6] → [5,6] → [5,7]；总块 12，xhard 杂乱布局 + 同色团上限 |
| PickXtimes | 数量（次数 + 干扰块） | 次数 [4,5] → [5,7] → [6,9] → [6,12] → [6,15]；干扰 0 → 1 → 2 → 3 → 3 |
| SwingXtimes | 数量（轮数 + 干扰块） | 轮数 3 → [3,4] → [4,6] → [4,8] → [4,10]；干扰 0 → 1 → 2 → 3 → 3 |
| PickHighlight | 干扰数 + pick 数 | pick 3 → 4 → [4,5] → [5,6] → [5,7]；总块 6 → 7 → 8 → [8,9] → [8,10] |
| VU / BU | 干扰数 / pick 次数 | VU 干扰 0 → 8 → 10 → 13 → 15，pick 2 → 2 → 3 → 3 → 3；BU 干扰 0 → 7 → 9 → 12 → 14，pick 同 |
| VUS / BUS | swap 次数 / pick / 干扰 | VUS swap [2,3] → [4,5] → [5,7] → [7,9] → [8,12]；BUS [2,3] → [3,4] → [4,5] → [5,6] → [6,8]；pick 2 → 2 → 3 → 3 → 3；外环干扰 0 → 4 → 6 → 8 → 10 |
| VideoRepick | 块数 / swap / repick | 块 (聚簇) → 4 → 5 → 6 → 6；swap → [3,5] → [5,7] → [6,9] → [8,12]；repick [1,3] → [2,3] → [3,4] → [4,5] → [4,6] |
| PatternLock | 难度（节点数） | 5×5 节点 [4,8] → [9,12] → [13,17] → [18,22] → 25 |
| RouteStick | 难度（段数 L） | L [4,7] → [8,10] → [11,12] → [13,14] → [15,21] |
| VPB | 实施方定：放置次数 | (k=1,不放回) → (k=1,放回) → (k=2,不放回) → (k=2,只放回末块) → (k=2,全放回) |
| VPO | 实施方定：放置次数 | (k=1,v[2,4],不放回) → (k=1,v[2,4],放回) → (k=2,v[2,3],不放回) → (k=2,v[2,4],不放回) → (k=2,v[2,4],放回) |
| MoveCube | 只推 xhard，不加档（M2）；**用户已定** | 中心圆禁区 R=0.05 + 三个小框 → 统一区域 U（圆环）：圆心 (−0.06, 0) = 可达环带中点，内孔 0.12、外径 0.20，方块/goal/杆抓取点共用，杆/方块 yaw 全 2π（2.6） |
| InsertPeg / StopCube | 原版无梯度 | 不动（xhard 逐位复现 v5-01） |

### 1.1 定死的口径

| # | 口径 | 依据 |
|---|---|---|
| 1 | **原三档逐位冻结**（定义、reset 取值、演示 h5）；V1 是唯一硬闸门 | V5 口径 1/12 |
| 2 | **录像器、`evaluation.py`、`run_example.py`、`dataset_replay.py`、五入口冻结**（三文件与官方副本 `artifacts/train-parity/local-smoke-01/official-src/scripts/`、`origin/dataset-gen-NewSeed`、`13e5151` 逐字节相同，审计已核）；新档步数都不超过 xhard，评估预算问题不再存在，V5 FROZEN_FILES 判据原文保留 | V5 口径 2 |
| 3 | **难度序 easy < medium < hard < xhard1 < xhard2 < xhard3 < xhard**，档名固定 `xhard1/xhard2/xhard3`；xhard 是最难档 | 用户 2026-09-25「改名为xhard1 xhard2 xhard3 / 目前的xhard作为最难一档」 |
| 4 | **范围 = 原版有梯度的 13 个环境**（BinFill、PickXtimes、SwingXtimes、PH、VU、BU、VUS、BUS、VR、PatternLock、RouteStick、VPB、VPO）；StopCube、MoveCube、InsertPeg 原三档之间没有任何取值分支（MoveCube/InsertPeg 三档指向同一 `config_native`，StopCube 三档同值；三者只读 `== "xhard"`），不加档 | 用户原话「原版中有难度梯度的」；调查 A |
| 5 | **新档沿用 xhard 的全部生成机制、只内插数值**：**「加码字段」= 用户为该环境指定的难度维度**（BinFill 投入数；Unmask 干扰/swap/pick；PH pick 与总块；PickX/Swing 次数与干扰；Pattern/Route 长度；VP 放置次数），其均值逐档严格上升（区间允许重叠、下界不高于 xhard）；机制型字段（框半宽、搜索预算、交换步数、容器数、环带宽）只要求单调不减或不变，不计入 TIER_MONOTONE（审计 C 段：按「所有字段严格递增」计划表自身有 10 处违例，故收窄口径） | 用户原话「都要比现在的hard更难」+ 第二轮「X1 < X2 < X3 … xhard 最难」 |
| 6 | **「均匀」的执行定义**：碰撞/可行性判定是硬约束，均匀性在可行集合内实现；① 跨局：每个对象作为交换参与者的边际频率相等（10000 局离线卡方 p>0.05）；② 局内：各对象参与次数极差 ≤1（做不到时 ≤2）；③ 不许「刚换完立即换回」。算法选型见 M6 | 用户原话「碰撞检测后 对象层面的选择仍然均匀」「先给出可行候选 再均匀采」 |
| 7 | **均匀化算法 xhard 与新档共用**，VUS、BUS、VR 的 xhard 重冻；其余环境 xhard 逐位复现 v5-01（回注闸门 X0） | 用户把不均匀当缺陷提出；M3 |
| 8 | **MoveCube「往外推」= 方块中心、goal 中心、杆抓取点三者共用一个圆环 U 做拒绝采样**：圆心放在实测可达范围的中心 (−0.06, 0)，内孔挖掉、朝向全随机，直接拒绝、不用 bias；约束落在杆的抓取点（杆尾）而不是杆根。**用户 2026-09-25 已批准：「movecube这个同意 就这么做 固化到plan内」** | 用户原话「改为一个 robot 能抓到的最大的区域 去掉中间区域…统一作为生成区域 杆/方块朝向加入全随机」「圆形 放在可达范围的中心 而不是现在这样」；实测 reach/A、B、C、U |
| 9 | **只做一次对拍、一次生成**：V1 = 16 × 9 原三档与 `13e5151` 逐位比；生成 = 一次多 worker 运行，每格「10 候选 + index 0/3/6 三局正式」（M4 未改前） | V5 口径 12 |
| 10 | **待决项不许自填**；细节自决并在报告注明 | V5 口径 14 |
| 11 | **实现上所有 `== "xhard"` 字面判断改为族判断**（`is_newvalue_difficulty()` + `newvalue_tier()`），不得复制四份分支 | 调查 A |

### 1.2 用户原文（逐字保留）

```text
给出v6的方案
把movecube继续往外推
unmask任务外部的swap 内部的swap 对象
repick任务swap的对象 要做到碰撞检测后 对象层面的选择仍然均匀

并且对所有task 原版中有难度梯度的 也加入3个难度梯度 都要比现在的hard更难
binfill按照数量
unmask按照干扰/swap次数/pickup次数
pattern/route按照难度
pickhighlight按照干扰数量 pick数量
videoplacebuttonorder你来定 给出方案
swing pickxtimes按照数量


给出方案 我没考虑到的设置为代决
使用workflow/subagent辅助判定 不要全自己看
```

```text
汇总v6写入根目录
```

```text
X1 < X2 < X3
改名为xhard1 xhard2 xhard3
目前的xhard作为最难一档
修改计划 


修改后的 Swap  怎么做到均匀 因为有一些碰撞不可达？
是否可以采用先给出可行候选 再均匀采

修改后的movecube采样采出来会是什么样 可视化表达
```

### 1.3 用户提问的直接回答与调查结论（结论先行）

**问：修改后的 Swap 怎么做到均匀，有些碰撞不可达？能不能先给出可行候选、再均匀采？**

**答：能，这正是推荐算法的骨架；调查还发现两件事让它比想象的更简单，和一件事让它需要再加一步。**

1. **碰撞不可达作用在「位置槽」上，与对象编号无关。** 每次交换在窗口末精确对换位姿，所以一局里 4 个内环容器只是在 4 个固定位姿槽之间轮换；一对能不能换只取决于它们此刻占的两个槽（VUS 长方形锚点的两条对角线几乎总不可行：可行率 6.6%，其余四条边 85～99%）。reset 时对 6 个槽对各跑一次仓库精确判定 `check_swap_sweep_prefiltered`，得到「可行槽对图 G」，之后每次交换的可行候选就是 G 里的边。对象一开始被随机分到槽里，所以**任何对编号对称的选取规则，在碰撞拒绝之后跨局边际仍然均匀**。V5 现状不均匀（VUS 参与频率 [.236,.283,.279,.201]，p≈0）的根源是发起者抽样 `randperm(3)[:2]` 只可能是 0/1/2、bin_3 永不发起的概率约 50%，**不是碰撞**。
2. **「可行候选里均匀抽」（S1）做到跨局均匀，但局内不均衡。** 10000 局离线：S1 边际 p=0.285（均匀），但每局各对象参与次数极差均值 3.79、27% 的交换是「刚换完立即换回」；加一条「禁止立即撤销」（S1n）后极差 2.63、撤销 0。
3. **再加一步「参与次数少者优先、平局均匀抽」（S5）就同时满足局内均衡**：单趟极差均值 0.54、撤销 0、边际 p=0.967；单趟 + G 连通时极差 ≤1 的局 VUS 95.7%、BUS 89.4%；**再加「整条极差 >1 重排 ≤20 趟」（M6(a) 的完整形式）后 VUS 100%、BUS 99.9%，撤销 0，边际 p 0.977/0.996**（VUS 平均 1.18 趟、4.8% 的局需重排；BUS 2.40 趟、13.9%）。可视化 `plan-probes/unmask/viz/`（6 张图，见证据索引）。代价：BUS 约 1/3 内环布局在 reset 被拒（G 连通率 66.5%，VUS 95.4%）。
4. **VR 同理**：规划失败 40% 的根因是可行图太稀（每块平均只能与 1.54 块互换、41% 布局有孤立块），不是「3 个最近」限制；S1 在 VR 上「全员参与」只有 50.3%（违反 V5 口径 10），S5 为 100%、极差 ≤1 达 96.7%、reset 成功率不降。
5. **外环做不到局内均匀**：V5 路径约束（全程可见、离内环净距、离按钮）下每窗 45 个槽对只有 5.6/3.6 对可行，28%/44% 的槽某窗没有任何搭档（按整局平均度数计；按「窗 × 槽」计为 31.7%/45%，M7(b) 的 31.7% → 15.0% 用后一口径），任何算法「全员参与」≤4.3%。能做到的是跨局均匀（放置后序号随机重排）+ 均衡贪心 O4 把未参与率从 40%/54% 降到 28%/43%、撤销率从 42%/56% 降到 0.5%/6.7%。处置见 M7。

用户提出的「先给出可行候选、再均匀采」= S1；本文推荐 S5 = 「可行候选中优先参与次数最少者，平局均匀抽，禁止立即撤销，整条极差 >1 重排」。两者对比与选型放 M6。

**问：修改后的 MoveCube 采样采出来会是什么样？**

**答（第一轮，环带 T1～T3 方案；已被下一问的统一区域 U 取代，留作对照）：见图 `artifacts/newtask-v6/plan-probes/movecube/movecube_v6_layouts.png`**（`viz_v6.py` 用与 v5-01 逐值核对过的离线副本各跑 2000 局；已发给用户）。四列 = V5 现状 / 环带 T1 [0.08,0.12] / T2 [0.10,0.14]（建议）/ T3 [0.12,0.16]；四行 = 示例一局（杆身线段、方块、goal 圆盘、禁区、采样框）、4000 个方块中心散点、4000 个 goal 中心散点、离桌心距离与方块-goal 距离直方图。要点：
- V5 现状：方块中心离桌心均值 0.094、goal 0.078，goal 挤在 [−0.06,0.06]² 的小方框里贴着 R=0.05 的禁区，画面上三物体都在桌心附近。
- T2：方块与 goal 都只落在半径 0.10～0.14 的圆环上（均值 0.120，最小 0.100），远端 x ≤ 0.11 封顶让环在 +x 侧被切平（不往远离机器人的方向扩），方块-goal 距离均值 0.147 → 0.191；2000/2000 局布局成功，杆仍在 y=±0.2 两侧。
- T3 环更大（0.12～0.16），方块-goal 距离 0.211，peg_push 路点离基座 >0.80 m 比例 4.5%（V5 3.6%），是可达性的边缘。

**问（第二轮）：杆/方块/target 改为机器人能抓到的最大区域、去掉中间、朝向全随机，采出来什么样？机械臂在 xy 不同朝向抓取会不会影响能抓到的最大区域？**

**答：会影响，但只影响「手腕转不转得过去」，不改变远近硬边界；统一区域 U 已按实测定界并在 greatlakes 真演示 144 局验证。** 三路实测（本机 opus subagent 并行，`artifacts/newtask-v6/plan-probes/reach/`）：
- A 末端可达图（顶抓 / 夹爪推 / 带杆推起点 × 8 个 yaw，57288 次真实规划）：全 yaw 可达 = 离基座 0.31～0.80 m，y=0 线上 x∈[−0.30, 0.175]；grasp 在 yaw=90° 时 screw 全灭但 `solve_pickup` 取最近边使 yaw≡yaw+180°，push 在 yaw=270° 缺左上楔形（有 IK、RRT* 兜底）；远端 0.80 m 与 yaw 无关。
- B 抓杆可达图（杆根网格 × 12 个 yaw，12276 次真调 `grasp_and_lift_peg_side`）：成败只看抓取点（杆尾 = root − 0.10·u）离基座距离，0.27～0.80 全成功、≥0.85 为 0；杆 yaw 只是把抓取点伸到不同位置，所以**约束要落在抓取点而不是杆根**。
- C 放宽区域真演示（环带 0.06～0.24、杆根也在环带、yaw 全 2π，144 局）：peg_push 24/48、gripper_push 35/48、grasp_putdown 48/48；失败集中在抓杆点 x>0.15 / 离基座 >0.80 与推距 >0.30。
- 由此定 U（2.6；第一版绕桌心挖洞 GL 118/144，用户改为圆环后定稿）：圆环版离线图 `reach/U/unified_region_v2.png`；GL 复测 `reach/U/gl2/u2_results.png`：**120/144，peg_push 35/48、gripper_push 37/48、grasp_putdown 48/48**（V5 基线 5/8、6/8、8/8），失败全是推动接触（推没到位 22、抓杆 4），与位置无关。

**调查结论（决定方案走向的事实）**

| 事实 | 结论 |
|---|---|
| 哪些任务「原版有梯度」 | 13 个；StopCube、MoveCube、InsertPeg 三档逐字同值 |
| 管道认几个新值档 | 只认写死的 `"xhard"`（审计实测：src 带引号 `"xhard"` 143 行 = 16 个环境文件 134 行 + `utils/` 7 文件 9 行，其中 `==`/`!=` 比较 61 行；scripts 另 14 行；scripts 单一 `DIFFICULTY`/`SEED_RULE`/身份键）；加档是一次管道改造 |
| 新档的时长/预算 | 全部落在 hard 与 xhard 之间，执行步与总步数都不超过 xhard 现状；`fail_safe_limit=5000` 与评估 1301 步都不新增约束（xhard 本身已有超 1301 的局，那是 V5 现状，本轮不动） |
| MoveCube 能推多远 | 实测：三种 way 的可达硬边界是离基座 0.31～0.80 m（与 yaw 无关）；统一区域 U（圆环版）在 GL 真演示 120/144，失败与位置无关；V5 另有 2.7% 的局方块生成时压在杆身，U 带离杆 ≥ 0.04 顺带修 |
| 均匀性 | 见上 |
| 规模 | 13 环境 × 3 档 + 重冻 4 个 xhard = 43 格，430 候选、129 正式局；另 12 个 xhard 回注 36 局 |

### 1.4 待决项（实施前逐条答复，不许自填）

| 编号 | 问题 | 选项 | 建议 | 结论（用户答复） |
|---|---|---|---|---|
| M1 | 新档是否**沿用 xhard 的全部机制只内插数值**（口径 5）。这意味着 BinFill xhard1 就是杂乱布局、PH xhard1 就是 HSV 任意色、VUS xhard1 就带外环同步交换、PickXtimes xhard1 就是均匀无偏置 + 0.08 间距 | (a) 是。<br>(b) 否：某些机制（如外环交换、杂乱布局）也按档分级引入，需逐环境再定 | (a) | |
| M2 | MoveCube 要不要也加三档（原版无梯度） | (a) 不加，只推 xhard。<br>(b) 加：xhard1/2/3 = 在现状与 U 之间按桌心半径 / 离基座环带内插三档，xhard = U | (a) | |
| M3 | 未被改动的 10 个环境（加 InsertPeg、StopCube 共 12 个）的 xhard 是否必须逐位复现 v5-01 | (a) 必须：回注闸门 X0（v5-01 specs 行在 V6 代码重跑 3 局，h5 SHA 相同）。<br>(b) 不要求，16 个 xhard 全部重抽 | (a) | |
| M4 | 每格规模 | (a) 沿用「10 候选 + 3 正式」，抽签尝试上限按环境 30～60。<br>(b) 新档减到「6 候选 + 2 正式」 | (a) | |
| M5 | Unmask 内环 xhard 里「bin_3 恒为空容器」（藏 cube 只在 bin_0..2）要不要一并随机化 | (a) 随机化（`randperm(4)[:pick]`，xhard 流原地移位）。<br>(b) 不动 | (a) | |
| M6 | **均匀化算法选型**（口径 6 的实现） | (a) S5：可行候选中参与次数最少者优先、平局均匀抽、禁止立即撤销、整条极差 >1 重排 ≤20 次；VUS/BUS 另以 G 连通作 reset 接受条件。<br>(b) S1n：可行候选里均匀抽 + 禁止立即撤销（用户提议的形式；跨局均匀，局内极差 2.63，VR 全员参与只 50%）。<br>(c) S1：可行候选里均匀抽，不加任何约束 | (a) | |
| M7 | 外环在 V5 路径约束下局内做不到均匀 | (a) 接受「跨局均匀 + O4 尽量均衡」，报告逐局未参与数。<br>(b) 放宽「路径全程可见」（零可行搭档槽 31.7% → 15.0%），交换会出画。<br>(c) 外环改沿环切向成对放置（改布局）。<br>(d) 外环不做均匀化，只做内环 | (a) | |
| M8 | MoveCube 统一区域 | **已定**：圆环，圆心 (−0.06, 0)，内孔 0.12、外径 0.20，推距上限 0.30 保留（2.6） | — | 用户 2026-09-25「movecube这个同意 就这么做 固化到plan内」 |
| M10 | PickHighlight「按干扰数量」在 xhard 不重冻时无法加码（干扰均值 hard=xhard=3） | (a) 只按 pick 与总块加码，干扰均值全程 3（2.9 现表）。<br>(b) 重冻 PH xhard：新增 decision 键直接抽干扰数（如 3/4/5/6），pick 不变 | (a) | |
| M12 | VU/BU 新档内环容器数从 hard 的 15 降到 xhard 机制的 8（口径 5 下容器数算不算加码字段） | (a) 不算（机制型字段），按 2.3 表。<br>(b) 算，新档内环容器 12/10/8 递减不允许，改为保持 15 并只加干扰 | (a) | |
| M13 | AGENTS.md 规则 11 字面仍是「逐个批准」，与本计划授权边界（用户 2026-09-21 口头：src/robomme 免逐项批准、改完出报告）不一致 | (a) 更新 AGENTS.md 规则 11。<br>(b) 计划头部引用用户原话并保留 AGENTS.md 原文 | (b) | |
| M11 | VPB/VPO 的三档：原三档本就有「pick 后放到 goal_site」一段，`return_to_origin` 只是换终点，放置段数不随 hard→xhard1 增加；(k=2,不放回) 时第二块放哪没有定义（只有一个 `goal_site`），`validate_demo_plan` 也会拒；xhard1→xhard2 从放回变不放回是倒退 | (a) 只用两个已存在的旋钮：xhard1=(k1,放回)、xhard2=(k2,放回)=xhard 的机制但 VPO v 上界 3、xhard3=(k2,放回) + 演示时长/按钮数等第三轴（实施方定）。<br>(b) 引入 `return_last_only` 新语义（vp 副本已在实现）并定义 (k2,不放回) 的第二块落点（第二个 goal_site）。<br>(c) VP 两环境退出加档（13→11） | (b)；vp 副本（/data/hongzefu/v6-draft/vp）已实现并回放核验：不放回的块落在隐藏 `goal_site` 中心沿 y 轴等距排开（VPB 间距 0.07、VPO 0.10，落点确定、不抽随机数，generator 状态逐字节不变）；`return_last_only` = 前 k−1 块按不放回落点、末块放回原位；`validate_demo_plan` 按档读策略；VPO 新增 decision 键 `visit_count_range`（会让 `test_snapshot_matches_source` 对 v5 快照失败，S4 重导快照后修）。按 reset 实际任务表，VPB 各档 pick-place 段数 3/3/6/6/6，难度差在终点是原位还是桌面。本机真演示 VPB (k1,放回) 3/3、(k2,不放回) 3/3、VPO (k1,v[2,4],放回) 3/3；PatternLock 三档 3/3 且首局步数 646/924/1256（xhard 1614），RouteStick xhard1/2 3/3（1000/1200 步）；VP 的 xhard 本身 1500～1993 步已超评估 1301（V5 现状，与口径 2 一致：新档不超 xhard） | |
| M9（论据修正：审计补测 4 块/5 块 reset 成功率 0.625/0.629，低于原写的 ≈0.9/≈0.75；块数少时可行图更稀 1.29/1.46 < 6 块的 1.54，「块数少更易」不成立） | VR 的 hard 是「聚簇 15 块、0 交换」另一条路线，新档按 medium → xhard 的轴（块数/交换/重拿）内插，xhard1（4 块、[3,5] 次交换、[2,3] 次重拿）是否算「比 hard 更难」 | (a) 算，照表。<br>(b) 不算，VR 新档从 6 块起只内插交换/重拿次数 | (a) | |

### 1.5 本计划推翻或修改的 V5 决策

| V5 决策 | V6 处理 |
|---|---|
| VUS/BUS 内环「3 个固定发起者 + 最近邻搭档」、VR「k%6 轮流 + 3 最近可行」 | 全部换成 S5（M6） |
| 2.9 MoveCube「R=0.05 圆形禁区」+ 三个小采样框 | 改为以可达中心为圆心的圆环 U（口径 8，用户已定） |
| 难度白名单只有一个新值档 | 加 `xhard1/2/3`，族判断（口径 11） |
| 口径 5 / N7「所有加码字段严格递增」 | 收窄为「用户指定维度严格递增、机制型字段单调不减」（审计 C 段） |
| 其余（xhard 的演示 25～35 s 校准、`evaluation.py` 判据、L51 VR 不扩区、录像器冻结） | 不变（25～35 s 只约束 xhard；新档 PatternLock/RouteStick 按计划数字约 700～735 帧，低于 25 s 是预期） |

## 二、逐环境改动

### 2.0 全局：难度档管道改造

原则：族判断替代字面比较，一份档位表替代复制的分支；原三档路径上不新增、不挪动任何随机抽样；共用函数的新参数默认关闭。

| 文件 | 符号 | 改什么 | 原三档风险 |
|---|---|---|---|
| `utils/difficulty.py` | `VALID_DIFFICULTIES` | 加 `xhard1/2/3`；新增 `NEWVALUE_DIFFICULTIES`、`is_newvalue_difficulty()`、`newvalue_tier()`（xhard1=1 … xhard=4） | 无 |
| `utils/sampling_config.py` | `XHARD_KEY`、`_strip_xhard`、`_xhard_shape`、`assert_native_decision` | 单一键名改键名集合；V0「剥掉全部新值键后与原三档快照逐字相同」照旧 | 中：三档必经，但只多剥名字 |
| `utils/episode_spec.py`、`task_goal.py`、`xhard_home_site.py`、`unmask_swap_xhard.py` | `spec_kind_for`、`_unmask_pick_count`、`validate_demo_plan`（三者是 `== "xhard"` 字面比较）、`unmask_swap_xhard` 的 `decision["xhard"]` | 族判断；`spec_kind` 升为 `native-newvalue/2`（VUS/BUS/VR/MoveCube 的 v5-01 旧规格在类别层即拒，其余 12 环境的回注行由 X0 单独规格文件承载）；`validate_demo_plan` 按档读 `demo_return_policy` 不写死 `return_to_origin`；VUS 的交换/pick 次数实际取自 `native.parameters.configs[档]`（decision 键无人读，探针 E 实测），新档要挂到该位置；按本局档位取 `decision[<tier>]` | 无 |
| `utils/xhard.py`、`unmask_distractor_sampler.py`、`unmask_distractors.py` | 环带、干扰数、颜色轮转 | 容量从档位子树读 | 无 |
| 各环境文件 | `config_xhard` → `config_xhard1/2/3` + 档位表、`XHARD_DECISION` → `NEWVALUE_DECISION[<tier>]`、`_native_decision`、`_resolve_sampling_config` 兜底、全部 `== "xhard"` | 自动派生的 `number_range.*` 一类会自动长出新键；手写的 `decision.xhard.*` 改成按档表 | 中；VR 的 `elif self.difficulty == "hard"` 链族判断必须在前；RouteStick `.get(difficulty, 回退 easy)` 改缺键抛错 |
| `utils/object_generation.py` | `spawn_random_cube/target` | MoveCube 三个显式可选参数（环带外半径、x 封顶、离杆距离），默认 None 整段跳过 | 高：V1 覆盖 |
| `scripts/parity/v4_specs.py` | `DIFFICULTY`、`SEED_RULE`、header 档位比对、`source_fingerprint`/每任务 `sampling_config` 校验 | 档位改 CLI 参数（默认 xhard 保 V5 字节不变）；seed 偏移：xhard 重冻 6e6、xhard1 8e6、xhard2 10e6、xhard3 12e6；**一份快照只封一条 `seed_rule`，而 v6-01 的 xhard 档同时含 12 个环境的 v5-01 回注行（4e6）与 4 个环境的重冻行（6e6）：X0 回放用单独规格文件（header 保留 V5 的 `seed_rule` 并重新封存来源指纹），v6-01 快照只装重冻行与新档行**（审计必改 4）；`tests/lightweight/test_v4_specs.py::test_seed_rule_disjoint_from_existing_layouts` 扩到 6e6/8e6/10e6/12e6 四段（`test_v5_xhard_obb_fix.py` 离线扫描已用 5e6/6e6 起的 seed，只是测试、不影响数据集） | 无 |
| `scripts/parity/v4_rollout.py`、`v5_generation.py`（另起 `v6_generation.py`）、`train_split_config.py`（`RELEASE_NOTES` 加 `newtask-v6`）、`train_split_runner.py` | 从 header 取档位；产物 `artifacts/newtask-v6/v6-01/<tier>/…`；快照 `scripts/configs/newtask-v6/v6-01/<tier>/specs.jsonl` | 无 |
| tests | `test_v4_xhard_{pickxtimes,swingxtimes}`（断言恰 4 档 → 7 档；`test_v4_xhard_stopcube` 不改，StopCube 不加档）、`test_operand_scope.py`、`test_episode_action_sampling.py`（同样写死 4 档）、`test_v4_specs.py::test_seed_rule_disjoint_from_existing_layouts`（扩四段）、`test_episode_spec_recorder`、`test_sampling_config_split`（改指 V6 快照）、`test_v5_xhard_pickswing`（`NATIVE_AST_GOLDEN` 不动；分支原文断言改族判断）、`test_v5_generation_tools`、`test_episode_action_sampling` | 扩到 7 档 | — |
| 不动 | 录像器、`evaluation.py`、`seed_layout.DIFFICULTY_ORDER`、`injection/*` | — | — |
| `scripts/parity/v5_generation.py` | `DEMO_BAND=(750,1050)` 演示时长带 | 只对 xhard 判定；新档（PatternLock/RouteStick 演示 9～25 s）按档豁免或按档给带 | 无 |
| 待核 | `generate_dataset_newseed.py` 的 `extract_native_sampling` / `validate_sampling_config` 只认 `config_xhard`，`v4_demo_probe` 与 `injection/rollout` 会调用 | S1 先确认 V6 链路是否经过；经过则按族判断改 | 低 |

### 2.1 改动范围总表

| 环境 | V6 动作 | xhard 处置 |
|---|---|---|
| BinFill、PickXtimes、SwingXtimes、PH、PatternLock、RouteStick、VPB、VPO、VU、BU | 加 xhard1/2/3 | 逐位复现 v5-01（X0） |
| VUS、BUS、VR | 加 xhard1/2/3 + 均匀化 | 重冻 |
| MoveCube | 只推 xhard | 重冻 |
| InsertPeg、StopCube | 不动 | X0 |

### 2.2 四个 Unmask 环境的共用事项（交换对象均匀化）

**现状**：发起者 `swap_initiator_indices=randperm(3)[:2]` + `swap_initiator_third`，第 k 次 `swap_indices[k%3]`；搭档在 step 的 AST 锁定循环里按实际位姿取 XY 最近邻；reset `predict_inner_windows`/`prejudge_inner_windows` 预判，运行时 `joint_sweep_from_actual` 复核。`_compute_dynamic_swap_candidates`/`_select_swap_pair_from_positions` 是死代码。

**内环（M6(a) S5）**：
1. reset 时对 4 个位姿槽的 6 个槽对各跑一次 `check_swap_sweep_prefiltered` 得可行槽对图 G；G 不连通抛 `SceneGenerationError` 重抽。
2. 主流追加一次 `torch.rand(n_swaps)` 作平局打破；预规划整段序列：每次在 G 的边里选「两块已参与次数之和最小」的一对，平局按该随机数，禁止与上一次相同的对；整条极差 >1 重排 ≤20 次，仍不满足接受极差 2。
3. 锁定循环里的搭档分支改为读预规划（仿 VR `_xhard_planned_partner` 先例），仍做 `joint_sweep_from_actual` 复核；外环 H1 守卫改为覆盖 G 中全部可行槽对。
4. M5(a)：藏 cube 容器 `randperm(4)[:pick]`。
5. 离线验收（按 M6(a) 完整形式 S5 + 整条重排 ≤20 + G 连通）：边际 p>0.05、极差 ≤1 ≥ 99%（离线 VUS 100% / BUS 99.9%）、撤销 0（「全部布局」口径下 S5 单趟撤销率 0.2%/5.0%，G 连通子集上为 0）；单测锁定「G 为完全图时 S5 边际严格均匀」。

**外环（O4）**：`plan_distractor_swaps` 改均衡贪心（每窗在可行槽对里选参与次数和最小、禁止立即撤销），放置后追加一次 `randperm(count)` 重排序号；`evaluate_outer_candidate` 的 vis → btn → inner_clear → exact 四道判定不动（M7(a)）。离线目标：未参与对象 VUS ≤30%、BUS ≤45%，撤销 ≤1%/≤7%，整局可行率 ≥99%/≥98%。

**验收**：`UNMASK_INNER_UNIFORM=PASS env=<E> chi2_p>=0.05 range_le1>=0.89 undo=0`；`UNMASK_G_REJECT=REPORT`；`OUTER_SWAP_BALANCE=REPORT unvisited_mean=… undo=…`。

### 2.3 VideoUnmask / ButtonUnmask

hard = 15 容器 / pick 2 / 无干扰；xhard = 8 容器 / pick 3 / 贴身环带干扰 15（VU）/ 14（BU），一半含 cube，`min_gap_factor` 0.75，独立停放。新档沿 xhard 机制（8 容器 + 贴身环带），容器总数（8 内环 + 干扰）保证 ≥ 16 > hard 的 15：

| 字段 | hard | xhard1 | xhard2 | xhard3 | xhard |
|---|---|---|---|---|---|
| VU 内环容器 / pick / 干扰 / 含 cube | 15 / 2 / 0 | 8 / 2 / 8 / 4 | 8 / 3 / 10 / 5 | 8 / 3 / 13 / [6,7] | 8 / 3 / 15 / [7,8] |
| BU | 15 / 2 / 0 | 8 / 2 / 8 / 4 | 8 / 3 / 10 / 5 | 8 / 3 / 12 / 6 | 8 / 3 / 14 / [7,7] |

- 环带、密度推导、三色轮转、停放点全沿 V5；干扰数少时环带随机稀疏放置（不重新推导带宽）。
- 帧数：pick 约 125（9 个样本的最大值）+ put down 52，全部 ≤ xhard。
- 验收：`UNMASK_RING=PASS n=<N> in_band=<N> visible=<N>`。

### 2.4 VideoUnmaskSwap / ButtonUnmaskSwap

hard = 4 容器 / swap [2,3] / pick 2 / 每次 50 步 / 无外环；xhard = swap [8,12]（BUS [6,8]）/ pick 3 / 33 步 / 外环 10 + 同窗外环交换。

| 字段 | hard | xhard1 | xhard2 | xhard3 | xhard |
|---|---|---|---|---|---|
| VUS swap / pick / 干扰 / 每次交换步数 | [2,3] / 2 / 0 / 50 | [4,5] / 2 / 4 / 50 | [5,7] / 3 / 6 / 33 | [7,9] / 3 / 8 / 33 | [8,12] / 3 / 10 / 33 |
| BUS | [2,3] / 2 / 0 / 50 | [3,4] / 2 / 4 / 50 | [4,5] / 3 / 6 / 33 | [5,6] / 3 / 8 / 33 | [6,8] / 3 / 10 / 33 |

- xhard1 保留 50 步交换速度（与 hard 同），xhard2 起用 xhard 的 ×1.5 速；外环交换从 xhard1 起每窗一次（M1(a)）。
- 干扰 4/6/8 时外环方环 [0.2675,0.45]（按 max(|x|,|y|) 判，不是圆环）稀疏放置；干扰 4/6/8 的外环可行率未测（已有 BUS 10/14/18 三点 0.983/0.996/0.986 不单调），S3 实测后填；外环 ≥99%/≥98% 的数字是在 V5 内环序列下测的。
- BUS 交换段计入评估步：xhard3 最坏 65+33×6+177×3−40 = 754，xhard 同公式 820，低于 xhard。
- 验收：沿 V5（外环窗口数 = n_swaps、`bin_collision=0`）+ 2.2 均匀性判定。

### 2.5 VideoRepick

**均匀化（M6(a)）**：搭档规划改 S5：每次在全部可行对（不限最近 3 个）里选参与次数和最小的一对，平局随机（主流追加一次抽取得规划种子，平局与重试在局部生成器上做），禁止立即换回；整条极差 >1 重排 ≤20 次，仍不满足接受极差 2。5 mm 规划余量保留、按钮继续当障碍。

| 字段 | medium | hard | xhard1 | xhard2 | xhard3 | xhard |
|---|---|---|---|---|---|---|
| 块数 / swap / repick | 3 / [2,3] / [1,3] | 聚簇 15 / 0 / [1,3] | 4 / [3,5] / [2,3] | 5 / [5,7] / [3,4] | 6 / [6,9] / [4,5] | 6 / [8,12] / [4,6] |
| reset 成功率（离线，审计 D 段补测） | — | — | 0.625（4 块） | 0.629（5 块） | 0.59 | 0.59 |

- 新档沿 xhard 机制：杂乱区、最小中心距 0.12、按钮入障碍、reset 预规划；块数 4/5 时可行图更密、reset 成功率更高（M9）。
- 验收：`VR_UNIFORM=PASS range_le1>=0.93 undo=0 all_participate=1`。

### 2.6 MoveCube（只推 xhard，重冻；M2、M8）

**现状**：方块候选中心框 ±0.10（面积 0.040 m²；最终中心再抖 ±0.03，实际覆盖约 ±0.13）、demo goal 框 ±0.11、exec goal 框 ±0.06、杆根两个 ±0.05 小框（y=±0.2），三者各不相同；桌心 R=0.05 圆禁区；2.7% 的局方块生成时压在杆身；杆 yaw 与方块 yaw 已是全 2π。

**要做（统一区域 U 圆环版，用户已定；`reach/U/region.py` 为离线定义）**：方块中心、goal 中心、**杆抓取点（杆尾 = root − 0.10·u）**三者共用同一个圆环做拒绝采样，杆根由抓取点 + yaw 推出：

| 条件 | 值 | 依据（实测） |
|---|---|---|
| 圆环 | R_IN ≤ \|p − C0\| ≤ R_OUT，**C0 = (−0.06, 0)**，**R_OUT = 0.20**，**R_IN = 0.12** | C0 = 可达环带（离基座 0.31～0.80）的中点；该圆心最大可达圆 0.245（A），留 4.5 cm；内孔 0.12 时面积 0.080 m²（V5 方块框 0.040 的 2 倍），0.14 时 0.064 |
| 保险 | 离基座 0.35 ≤ \|p − base\| ≤ 0.76 | 圆环整体在其内，恒满足，回放复核用 |
| 成对 | 0.10 ≤ \|方块 − goal\| ≤ 0.30；推起点（后退 0.10，带杆再侧移 ±0.10）离基座也在 [0.35, 0.76] | C 推距 >0.30 成功 12/22 |
| 杆 | 抓取点在圆环内均匀，yaw ∈ U(−π, π)；杆身线段离 C0 ≥ R_IN（不进内孔）；方块离杆身 ≥ 0.04、goal 离杆身 ≥ 0.02 | B；V5 压杆缺陷 |
| 朝向 | 杆 yaw、方块 yaw 全 2π（方块本来就是） | C 核实 `random_yaw` = u·2π |

第一版（绕桌心挖洞、外沿到可达边界）已被用户否定（「圆形 放在可达范围的中心 而不是现在这样」），其 GL 实测数字保留在下表作对照。

参数放 `demo_layout.xhard.region` / `execution_layout.xhard.region` 子键（两段统一：`center`、`r_in`、`r_out`、`base_dist`、`push_len_max`、`peg_gap`、`goal_peg_gap`），`spawn_random_target/cube` 新增显式可选参数（圆环圆心/内外径、离基座环带、离杆距离；默认 None 整段跳过，L4(b)），杆改为「抽抓取点 + yaw → 推杆根」并复核杆身离桌心；回放按同一规则复核；随机调用次序在 xhard 分支内重排（xhard 重冻，原三档不经过）。

**实测（2026-09-25，`artifacts/newtask-v6/plan-probes/reach/`）**：

| 口径 | peg_push | gripper_push | grasp_putdown | 合计 |
|---|---|---|---|---|
| V5 xhard 基线（P2，本机） | 5/8 | 6/8 | 8/8 | 19/24 |
| 探针 C：放宽环带 0.06～0.24、杆根满环带（本机 144 局） | 24/48 | 35/48 | 48/48 | 107/144 |
| U 第一版（绕桌心挖洞 0.14，已否定）：greatlakes A40 真演示 144 局 | 35/48 | 35/48 | 48/48 | 118/144 |
| **U 圆环版（C0 (−0.06,0)，0.12～0.20）：greatlakes A40 真演示 144 局** | **35/48** | **37/48** | **48/48** | **120/144** |

圆环版 24 局失败：推没到位 20（gripper 11、钩推 9）、抓杆 PlannerExhausted 3、FailsafeTimeout 1（步数中位 500、最大 5000，墙钟中位 49 s，517 s 跑完 144 局）。第一版 26 局失败：推没到位 22（gripper 13、钩推 9）、抓杆 PlannerExhausted 2、FailsafeTimeout 2；成功/失败段的推距、抓杆点、离基座距离中位数持平（位置不再是失败来源）；失败段方块棱角更朝前（|yaw mod 90° − 45°| 中位 14～19° 对 24～26°），是推动接触问题，V5 同样存在。步数中位 500、最大 5000（1 局）。无 SceneGenerationError / EpisodeSpecError。

- 可视化：`reach/U/unified_region_v2.png`（圆环版区域、散点、示例）、`reach/U/gl2/u2_results.png`（圆环版复测）；第一版 `reach/U/unified_region.png`、`reach/U/gl/u_results.png` 留作对照、`reach/A/reach_envelope.png`、`reach/B/peg_envelope.png`。
- 验收：`MC_REGION=PASS violations=0 layout_fail=0`（三物体、推起点、杆身全部按 U 复核）；`MC_DEMO=REPORT ok=…/12`，与 GL 120/144 同量级。
- 复测运行方式：GL 占位 job 内 `srun --overlap` 16 worker，逐局产物写节点 `/tmp` 即删，NFS 不留大文件，结果搬回 `/data`。

### 2.7 BinFill

hard = 3 色 / 总块 [10,12] / 投入色 [2,3] / 投入 [3,5] / 原生布局；xhard = 12 / [5,7] / 杂乱布局 + 精确 OBB + 同色团 ≤3。

| 档 | 总块 | 投入 | 投入均值 | 机制 |
|---|---|---|---|---|
| hard | [10,12] | [3,5] | 4 | 原生 |
| xhard1 | 12 | [4,5] | 4.5 | xhard 机制 |
| xhard2 | 12 | [4,6] | 5 | 同 |
| xhard3 | 12 | [5,6] | 5.5 | 同 |
| xhard | 12 | [5,7] | 6 | 同 |

帧数、reset 成功率全部在 hard 与 xhard 之间（xhard 离线 100%）。

### 2.8 PickXtimes / SwingXtimes

| 环境 | 档 | 次数 / 轮数 | 均值 | 干扰块 | 机制 |
|---|---|---|---|---|---|
| PickXtimes | hard | [4,5] | 4.5 | 0 | 原生（框 0.2） |
| | xhard1 | [5,7] | 6 | 1 | xhard 机制（框 0.25、中心距 0.08、精确 OBB、均匀无偏置） |
| | xhard2 | [6,9] | 7.5 | 2 | 同 |
| | xhard3 | [6,12] | 9 | 3 | 同 |
| | xhard | [6,15] | 10.5 | 3 | 同 |
| SwingXtimes | hard | 3 | 3 | 0 | 原生 |
| | xhard1 | [3,4] | 3.5 | 1 | xhard 机制（0.08、精确 OBB） |
| | xhard2 | [4,6] | 5 | 2 | 同 |
| | xhard3 | [4,8] | 6 | 3 | 同 |
| | xhard | [4,10] | 7 | 3 | 同（reset 成功率约 96%：三个新档与 xhard 都是 192/200，8 个失败 seed 相同、皆为放圆盘采样失败，与干扰数无关） |

干扰块颜色仍取黄/青/品红前 k 个；数词 ≤ 12 不越界；帧数 ≤ xhard。

### 2.9 PickHighlight

| 档 | pick | 总块 spawn | 干扰 = spawn − pick | 机制 |
|---|---|---|---|---|
| hard | 3 | 6 | 3（均值 3） | 原生（RGB 均匀色） |
| xhard1 | 4 | 7 | 3 | xhard 机制（HSV 任意色、精确 OBB） |
| xhard2 | [4,5] | [7,8] | 3（均值 3） | 同 |
| xhard3 | [5,6] | [8,9] | 3（均值 3） | 同 |
| xhard | [5,7] | [8,10] | 1～5（均值 3） | 同 |

审计 C 段发现：PH 的干扰数 = spawn − pick 两者独立抽，**xhard 自己的干扰均值 3 与 hard 相同**，所以在不重冻 PH xhard 的前提下「按干扰数量加码」做不到；上表已把 xhard2 的 spawn 改为 [7,8]（原 8，干扰均值 3.5 会高过 xhard）。要不要为 PH 重冻 xhard 引入直接抽干扰数的轴，见 M10。

保持 `spawn_lo ≥ pick_hi` 断言；框、预算不动；reset 成功率随 N 从 7 到 10 单调下降（离线 N=8 98.7%、N=9 93.4%、N=10 71.8%），全部不低于 xhard。

### 2.10 VideoPlaceButton / VideoPlaceOrder（实施方定维度）

hard 与 xhard 之间只有两个开关（演示方块数 k：1 → 2；`demo_return_policy`：不放回 → `return_to_origin`），VPO 另有每块访问台数 v。以「演示放置次数」作难度标尺，逐档 +1：

| 环境 | 档 | k | 放回策略 | v | 演示放置次数 |
|---|---|---|---|---|---|
| VPB | hard | 1 | 不放回 | — | 2 |
| | xhard1 | 1 | 放回 | — | 3 |
| | xhard2 | 2 | 不放回 | — | 4 |
| | xhard3 | 2 | 只放回末块（新策略 `return_last_only`） | — | 5 |
| | xhard | 2 | 全放回 | — | 6 |
| VPO | hard | 1 | 不放回 | [2,4] | 3 |
| | xhard1 | 1 | 放回 | [2,4] | 4 |
| | xhard2 | 2 | 不放回 | [2,3] | 5 |
| | xhard3 | 2 | 不放回 | [2,4] | 6 |
| | xhard | 2 | 放回 | [2,4] | 8 |

- 颜色 3、目标台 4、swap True 与 hard/xhard 同；布局、`goal_site` 占位、reset 成功率与 xhard 相同（VPB 81.8%、VPO 50.0%），抽签上限沿 V5（VPO 30 次攒 10 条在 0.48 下 96.7%）。
- `return_last_only` 是新策略值，`validate_demo_plan` 要放行；VPO xhard2 的 v 上限 3 需 `visit_selection.count_sampler` 按档取上界。
- 验收：`VP_DEMO=REPORT placements=… frames=…`。

### 2.11 PatternLock

| 档 | 网格 | 节点数 | 搜索预算 |
|---|---|---|---|
| hard | 5×5 | [4,8] | 1000（耗尽静默沿用） |
| xhard1 | 5×5 | [9,12] | 20000（耗尽抛错） |
| xhard2 | 5×5 | [13,17] | 20000 |
| xhard3 | 5×5 | [18,22] | 20000 |
| xhard | 5×5 | 25 | 20000 |

布局不动，不重访；每段约 35 帧（均值）⇒ xhard3 约 735 帧，按每段均值上界算约 763 帧（25.4 s）；DFS 命中率 n≥22 远高于 n=25 的 0.9996。

### 2.12 RouteStick

| 档 | L | backtrack |
|---|---|---|
| hard | [4,7] | T |
| xhard1 | [8,10] | T |
| xhard2 | [11,12] | T |
| xhard3 | [13,14] | T |
| xhard | [15,21] | T |

每段恒 50 帧；xhard3 执行段 ≤ 700。缺键抛错。

### 2.13 InsertPeg / StopCube（不动）

原三档逐字同值，不加档；xhard 逐位复现 v5-01（X0）。

## 三、改完怎么对拍

### 3.1 链路

源码 → `train_split_config.py extract --release newtask-v6` → `scripts/configs/newtask-v6/sampling_config.json` → 按档 `v4_specs draw --difficulty <tier>` → `freeze` → `v4_rollout run` → 报告；推理 `v4_eval` 默认预算不变。xhard 未改动的 12 个环境不重抽：v5-01 specs 行复制进 v6-01 的 xhard 档并重跑 3 局比 SHA（X0）。

### 3.2 验收判据

| 判据 | 查什么 | 判定行 |
|---|---|---|
| V0 | `config_easy/medium/hard`（StopCube/MoveCube/InsertPeg 为 `config_native`/`_CONFIG_CURRENT`）与原三档消费的 `NATIVE_SAMPLING` 键零 diff；剥掉四个新值键后 decision 与 V5 快照逐字相同 | `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0` |
| LIGHTWEIGHT | `tests/lightweight/` 全量 ≤5 分钟，失败集合与 S0 基线（46 failed / 12 errors）相同；新增族判断覆盖、S5 均匀性、档位单调性单测 | `LIGHTWEIGHT=PASS failure_set_equal_baseline=1` |
| **V1（唯一硬闸门）** | 原三档 16×9 = 144 条与 `13e5151` 逐位比 | `NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0` |
| X0（M3(a)） | 12 个未改动环境的 xhard：v5-01 specs 行在 V6 代码重跑 3 局，h5 SHA 与 v5-01 相同 | `XHARD_REPLAY=PASS envs=12 compared=36 sha_equal=36` |
| FROZEN_FILES | 录像器 `git diff --quiet`；`evaluation.py` 与官方副本 diff；五入口 | `RECORDER_FROZEN=PASS EVAL_PY_UPSTREAM=PASS ENTRIES=5` |
| 单调性 | 每环境每档抽 200 局离线：用户指定维度的均值严格递增、机制型字段单调不减（口径 5） | `TIER_MONOTONE=PASS envs=13 violations=0`（字段清单按 2.3～2.12 各表「加码字段」列） |
| 生成报告（不设门槛） | 每格 draft/rollout/backfilled/shortfall；均匀性统计（每局各对象参与次数、撤销数、外环未参与数）；MoveCube 环带违例 | `V6_GENERATION=REPORT cells=43 draft_ok=… rollout_ok=… shortfall=… uniform_range_gt1=… undo=…` |

### 3.3 实施步骤

| 步 | 内容 | 产出 |
|---|---|---|
| S0 | 存 LIGHTWEIGHT 基线；V1 基线侧（`13e5151` worktree）开跑 | 基线失败集合、基线 h5 |
| S1 | 管道改造（2.0）：族判断、档位表、守卫、specs/rollout 按档、tests 扩 7 档；三新档 config 先复制 xhard 值 | 12.136 + 报告 |
| S2 | 共用件：S5 内环/外环/VR 均衡贪心 + 离线均匀性单测；MoveCube 统一区域 U 参数与采样器；VP `return_last_only`；单调性检查器 | 12.137～12.139 |
| S3 | 逐环境填新档值并做本机演示探针（每格 ≥2 局，MoveCube 12 局，VUS/BUS/VR 各档 4 局）；opus subagent 按环境组在独立 worktree 并行，主会话审核合并 | 12.140～12.148 + 逐环境报告 |
| S4 | 重导 `newtask-v6` 快照、测试改指 | 12.149 |
| S5 | V1 V6 侧 144 条 + X0 36 局回放 | 12.150 |
| S6 | 一次多 worker 生成 v6-01（43 格）；tmux 起、Monitor 挂 | 12.151 + 生成报告 |
| S7 | 总报告、`scripts/README.md` 更新、收尾只留正式产物 | 12.152 |

规模与时间（估）：129 正式局 + 36 回放局，单局步数 ≤ xhard ⇒ 生成约 1.5 h；V1 两侧各约 3 h；产物 80～100 GB。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

N1 原三档路径不新增、不挪动任何随机抽样。N2 录像器、`evaluation.py`、五入口冻结。N3 待决项不自填。N4 新值流按 L1(a) 允许原地移位，未改动环境的 xhard 须过 X0。N5 共用函数新参数默认等价关闭，`NATIVE_SPEC_GOLDEN`/`NATIVE_AST_GOLDEN` 不动。N6 碰撞检测不为均匀让路。N7 每档在用户指定维度上均值严格介于相邻档之间，机制型字段单调不减（口径 5）。N8 文档禁硬编码行号。N9 Agent 工具派的 subagent 一律 opus、并行不设上限；workflow 需逐次审批且其 `agent()` 只用 sonnet（收尾/计划类最多 3 次 opus）、`model` 不得省略（与 CLAUDE.md 一致）。N10 长任务 tmux + Monitor。

## 一、按阶段、按文件的逐项改动清单

见 2.0 表；S3 逐环境字段落点：

| 环境 | 新档 config 键 | decision 子树键 | 新增/改动方法 |
|---|---|---|---|
| BinFill | 投入数区间 | `decision.configs.<tier>.{layout_mode: clutter, color_mix}`（投入色沿 xhard） | `_spawn_cubes_xhard` 读档位 |
| PickXtimes / SwingXtimes | 次数区间、干扰数 | `<tier>.{distractor.colors（长度即干扰数）, min_center_dist_m}`（`corner_bias` V5 已删，不得写回，`_xhard_shape` 会拒） | 干扰颜色取前 k 色 |
| PH | pick、spawn 区间 | `<tier>.{block_color_policy, block_color_hsv}`（精确 OBB 是硬编码调用，无键） | — |
| VU / BU | pick、内环容器 8 | `<tier>.distractor.{count, cube_count_range}`、`bin_layout_policy.<tier>.min_gap_factor` | 环带稀疏放置；藏 cube `randperm(4)[:pick]`（M5） |
| VUS / BUS | swap、pick、干扰、交换步数 | `<tier>.{distractor（含 cube 数 = 干扰数一半：2/3/4）, distractor_swap, swap_speed_multiplier, inner_swap_policy: balanced}`；VUS 的 swap/pick 次数实际读 `native.parameters.configs[<tier>]`（探针 E 实测） | `_plan_inner_swaps_balanced`、G 连通判定、锁定循环内改读预规划 |
| VR | 块数、swap、repick | `<tier>.layout.min_center_dist_m 0.12`、`<tier>.swap_plan.partner_rule: balanced`、`num_repeats_range.<tier>`（手写子树，不会自动长出） | `_plan_swap_partners_xhard` 改 S5；`_compute_dynamic_swap_candidates` / `_select_swap_pair_from_positions` 死代码同 Unmask 处理 |
| MoveCube | — | `demo_layout.xhard.region`（离基座环带、桌心半径、x/y 封顶、推距、离杆）、`execution_layout.xhard.region` | `spawn_random_*` 新增可选参数；杆改抽抓取点 |
| PatternLock | 节点区间 | `<tier>.path_search_max_attempts 20000` | — |
| RouteStick | `segment_count_range` | — | 缺键抛错 |
| VPB / VPO | k、放回策略、v 上界 | `<tier>.{demo_object_count, demo_return_policy}`；VPO 的 v 上界只能走 decision 新键（`visit_selection.count_sampler` 在 native 块，V0 零 diff） | `return_last_only`；`validate_demo_plan` 按档放行（含 (k2,不放回) 的落点定义，M11） |

## 二、对拍闸门总表

V0 → LIGHTWEIGHT → V1 → X0 → FROZEN_FILES → TIER_MONOTONE → 生成报告；判定行见 3.2。

## 三、runbook（参数名以 S1 实现为准）

```bash
# 只读核验
git diff --quiet da77662 -- src/robomme/env_record_wrapper/RecordWrapper.py && echo RECORDER_FROZEN=PASS; ls -1 scripts/*.py | wc -l   # 期望 5（fail_safe_limit 2000→5000 发生在 12.76，不能与 13e5151 比）
# 每次提交前（与 V5 S0 基线同口径）
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
# 单环境演示探针（S3）
uv run --no-sync python -m scripts.parity.v4_demo_probe --task <Env> --difficulty <tier> --n 4 --out artifacts/newtask-v6/demo-probe/<Env>-<tier>
# V1
uv run --no-sync python scripts/parity/train_split_parity.py compare --run base=artifacts/newtask-v6/v1/base --run v6=artifacts/newtask-v6/v1/v6 --pair base/B:v6/B
# 生成（tmux 起）
mkdir -p artifacts/newtask-v6/v6-01
tmux new-session -d -s v6gen "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.v5_generation pipeline --run-id v6-01 --tiers xhard,xhard1,xhard2,xhard3 --official-root artifacts/train-parity/local-smoke-01/official-src --draw-workers 8 --workers 8 2>&1 | tee artifacts/newtask-v6/v6-01/run.log; echo \"EXIT_CODE=\$?\" >> artifacts/newtask-v6/v6-01/run.log"
# （`--tiers` 是 S1 新增参数；V1 的 run 步用 `train_split_parity run --manifest scripts/parity/manifest_16x3.json …`，V5 的 `--subset 16x9` 已不存在）
```

## 四、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | src 143 行 `"xhard"` 字面（61 行比较）改族判断时漏掉一处，新档静默落进原三档或 xhard 路径 | 以 143/61/14 为起点 grep 计数归零作 S1 验收；每环境每档一次 reset 断言 `spec_kind` 与档名 |
| 2 | BUS 内环 G 连通率 66.5%，reset 拒绝约 1/3 | 抽签上限按 M4 定（建议 60）；如实报 shortfall |
| 3 | 外环局内不均匀（M7） | 报告逐局未参与数 |
| 4 | MoveCube 两种推法约 25% 推没到位（V5 同量级，与位置无关） | 已实测（GL 圆环版 120/144）；S3 只做回归 12 局 |
| 5 | VP `return_last_only` 是新语义，任务文本要能描述 | S3 核对 `__ALT__` 文本 |
| 6 | AST 锁：内环预填搭档会跳过锁定循环的运行时复核分支 | 复核另挂在循环内读预规划处，锁定测试保持通过 |
| 7 | 生成产物 80～115 GB（v5-01 实测 48 局 h5 33 GB）+ V1 两侧约 98 GB + worktree 约 56 GB，峰值约 230～270 GB；V1 6 h | `/data` 余 2.4 TB（审计核），够；起跑前再核 |

## 五、盲区诚实清单

- 全部帧数与成功率来自离线副本，无一格跑过模拟器演示；新档数值内插后未单独做过离线扫描（介于已扫过的 hard 与 xhard 之间，按单调性推断）。
- MoveCube 例外：可达边界与 U 已用真实模拟器实测（本机三路探针 + GL 144 局）。
- 蒙特卡洛用 numpy 随机数，只做统计，不与 torch 随机流逐位一致。

## 六、留档与 commit 纪律

沿 V5：每步一份 `docs/validation/newtask-v6/<日期>-<步>.md`；commit 只 add 本步文件；探针留 `artifacts/newtask-v6/plan-probes/`（不进 git）；收尾只保留正式 h5/视频与规格。

## 七、规划期证据索引（`artifacts/newtask-v6/plan-probes/`）

| 议题 | 目录 | 报告 | 关键脚本 / 图 |
|---|---|---|---|
| A 难度框架与四档总表 | `difficulty-framework/` | report.md | dump_configs.py、h5_frames.py |
| B MoveCube | `movecube/` | report.md | mc_v6.py、sweep_v6.py、budget_tail.py、**viz_v6.py → movecube_v6_layouts.png**、viz_ranges.py |
| B2 MoveCube 统一区域 U（第二轮，真实模拟器实测） | `reach/A`、`reach/B`、`reach/C`、`reach/U` | 各 report.md | A：probe_reach.py → reach_maps.png / reach_envelope.png；B：probe.py → peg_reach_maps.png / peg_envelope.png；C：gen_layouts.py → w_results.png；U：region.py、viz_u.py → unified_region.png，gl/ → u_results.png |
| C Unmask 四环境 | `unmask/` | report.md | p2_inner_mc.py、p2d_connected.py、p3_outer_mc.py、p4b_ring_wide.py、p5_inner_count.py |
| C2 Swap 方案可视化（用户「我需要做到局内均衡 给出 Swap 方案可视化图 内环外环分别是什么样的」） | `unmask/viz/` | — | fig1～fig6 → layout_inner_outer.png（内环 4 槽 + 外环 10/14/18、可见区、按钮禁入圈）、feasible_slot_graph.png（G 的 6 条边可行率）、s5_episode_timeline.png（S5 vs S1 一局）、balance_compare.png（S1/S1n/S5 极差与撤销）、outer_ring.png（O4、零搭档热力图）、swap_scheme_overview.png（流程） |
| D VideoRepick | `videorepick/` | report.md | （见目录） |
| E 计数类四环境 | `count-tasks/` | report.md | mc_lib.py、run_mc.py、binfill_color.py、camera_reach.py、frames_analyze.py |
| F 路径/放置类六环境 | `path-place-tasks/` | report.md | pl_dfs_hit.py、pl_path_study_v6.py、rs_reach.py、vp_layout_mc.py |
