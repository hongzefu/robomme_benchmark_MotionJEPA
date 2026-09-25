# 新值模式 V6：三个更难档、交换对象均匀化、MoveCube 继续外推

> 本方案以用户 2026-09-25 的要求为准，**只规划，不实施**。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，
> 分支 `newtaskRelease-v5`，代码锚点为本文件落盘时的 HEAD `da77662`（12.134）。commit 编号沿用仓库现行
> `<大版本>.<小版本> <中文描述>` 体例。依赖锚点：`uv.lock` `ff0ffd847a55…` / `pyproject.toml` `d03537d6c77a…`。
>
> **前置文档**：V5 计划 [NEWTASK_RELEASE_V5_PLAN.md](NEWTASK_RELEASE_V5_PLAN.md)（口径 1～14、L1～L54）；V5 总报告
> [docs/validation/newtask-v5/20260924-v5-final-report.md](docs/validation/newtask-v5/20260924-v5-final-report.md)；V5 正式快照
> `scripts/configs/newtask-v5/v5-01/specs.jsonl`（160 候选、48 正式局）与实跑产物 `artifacts/newtask-v5/v5-01/rollout/run1/`。
> **V5 决策除本文 1.5 明确推翻或修改的以外全部延续**，尤其是：原三档逐位冻结（V1 唯一硬闸门）、录像器冻结、
> `scripts/` 顶层五入口、L1(a)（新值流允许原地移位）、L4(b)（共用采样函数各环境各加显式参数）。
>
> **规划期证据**：本文全部实测数字来自 2026-09-25 的一次规划期调查（6 个议题并行、各由一个 opus subagent 只读完成，
> 未启动 workflow），探针脚本、日志与六份调查报告留在 `artifacts/newtask-v6/plan-probes/<议题>/report.md`
> （本机留档、未进 Git，索引见第二部分七）。**数字性质**：绝大部分来自与仓库纯函数或 v5-01 冻结规格逐值对齐过的
> 离线副本（每个议题都先证明副本与 V5 实跑一致），模拟器实跑样本为零；这些数字一律只当规划期估计，不能当验收结论。
>
> **授权边界**：本文是计划，不是实施授权，实施须用户另行批准。`src/robomme/` 的改动沿用 V4/V5 做法：免逐项事前批准，
> 但每步收尾必须在 `docs/validation/newtask-v6/` 出 md 报告。录像器 `src/robomme/env_record_wrapper/RecordWrapper.py`
> 全程冻结（`fail_safe_limit=5000` 保持）。**1.4 的待决项 M1～M20 一个都不许在实施时自行取建议值**，必须先回来问用户；
> 取整、边界取舍、预算次数这类不改变设计意图的细节由实施方自决并在报告里注明（V5 口径 14）。
>
> **简称**：VU = VideoUnmask，BU = ButtonUnmask，VUS = VideoUnmaskSwap，BUS = ButtonUnmaskSwap，VPB = VideoPlaceButton，
> VPO = VideoPlaceOrder，VR = VideoRepick，PH = PickHighlight；「内环」指参与揭示/交换的 `spawned_bins`，「外环」指
> `distractor_bins`；三个新档在本文暂记 **X1 / X2 / X3**（正式名见 M3，建议 `xhard2 / xhard3 / xhard4`）；
> 源码路径省略前缀 `src/robomme/robomme_env/`。

# 第一部分（给人看）

## 一、用户决策

**一句话方案**：在 V5 的 xhard 之上，给**原版 easy/medium/hard 有难度梯度的 13 个环境**各加 **3 个更难档 X1 < X2 < X3**
（每档在用户指定的维度上单调递增、都比 xhard 更难）；同时修三处 xhard 本身：**MoveCube 三物体继续往外推**（环带 + 放大框），
**Unmask 两个 Swap 环境的内环/外环交换对象、VideoRepick 的交换对象在碰撞检测之后仍按对象层面均匀选取**（xhard 与新档共用
同一套算法，xhard 重冻）；原三档定义、reset 取值、演示 h5 逐位不变（V1）；InsertPeg、StopCube 原版无梯度，一字不动。
所有新档与重冻的 xhard 重新抽签冻成 `v6-01`，链路（抽签 → 冻结 → 实跑 → 推理）与闸门沿用 V5。

按环境说（新档参数明细与依据见第二节；帧数均为离线估计）：

| 环境 | 梯度维度（用户指定 / 实施方定） | xhard → X1 → X2 → X3 |
|---|---|---|
| BinFill | 数量 | 总块 12 → 14 → 16 → 18；投入 [5,7] → [7,9] → [9,11] → [11,13] |
| PickXtimes | 数量（次数 + 干扰块联动） | 次数 [6,15] → [10,14] → [13,16] → [16,18]；总块 6 → 9 → 12 → 15 |
| SwingXtimes | 数量（轮数 + 干扰块联动） | 轮数 [4,10] → [9,12] → [12,16] → [16,20]；总块 6 → 9 → 12 → 15 |
| PickHighlight | 干扰数 + pick 数 | pick [5,7] → [7,8] → [8,10] → [10,12]；总块 [8,10] → [11,12] → [13,14] → [15,16]（y 半宽 0.20 → 0.30） |
| VU / BU | 干扰数 / pick 次数 | VU 干扰 15 → 20 → 24 → 28，pick 3 → 4 → 5 → 6；BU 干扰 14 → 19 → 23 → 27，pick 3 → 4 → 5 → 5（pick>3 需新色，M8） |
| VUS / BUS | 干扰数 / swap 次数 / pick 次数 | VUS swap [8,12] → [12,14] → [15,17] → [18,20]；BUS [6,8] → [9,10] → [11,12] → [13,14]；pick 3 → 4；干扰 10 → 12 → 14 → 16 |
| VideoRepick | 块数 / swap 次数 / repick 次数 | 块 6 → 7 → 8 → 8；swap [8,12] → [12,16] → [16,20] → [20,24]；repick [4,6] → [6,8] → [8,10] → [10,12] |
| PatternLock | 难度（路径段数） | 25 节点不重访 → 允许重访、段数 [30,34] → [38,44] → [48,56]（M1 选 (a) 时改为换 6×6 / 7×7 网格） |
| RouteStick | 难度（段数 L） | L [15,21] → [22,27] → [28,34] → [35,41]（M1 选 (a) 时只能做 1～2 档） |
| VPB | 实施方定：演示方块数 k + 目标台 T + 交换次数 s | (2,4,1) → (2,5,2) → (3,6,2) → (3,6,3)，新档 `goal_site` 移出布局障碍 |
| VPO | 实施方定：k + T + 每块访问数 v + s | (2,4,[2,4],1) → (2,5,[4,5],1) → (3,5,[4,5],2) → (3,6,[5,6],2) |
| MoveCube | 只推 xhard，不加档（M2） | 中心禁区 R=0.05 → 环带 [0.10,0.14] + 框放大到 0.14 + 远端 x ≤ 0.11 + 方块离杆 ≥ 0.04（T2，M13） |
| InsertPeg / StopCube | 原版无梯度 | 不动（xhard 逐位复现 v5-01） |

### 1.1 定死的口径

**实施中不得更改。** 每条注明依据。

| # | 口径 | 依据 |
|---|---|---|
| 1 | **只加新档、只重冻被改动的 xhard**；easy/medium/hard 在定义、reset 取值、完整演示 h5 上都必须与改动前逐位相同；V1 是唯一硬闸门 | V5 口径 1/12；V4 H2、N4、N12 |
| 2 | **录像器冻结**；`scripts/evaluation.py`、`scripts/run_example.py`、`scripts/dataset_replay.py` 与上游逐字节相同；`scripts/` 顶层只许五个入口。新档的评估预算**不改 `evaluation.py`**，若放宽（M1）只走 `scripts/eval/v4_eval.py --max-steps` 并冻进规格 header | V5 口径 2；本文 M1 |
| 3 | **范围 = 原版有梯度的 13 个环境**：BinFill、PickXtimes、SwingXtimes、PickHighlight、VU、BU、VUS、BUS、VR、PatternLock、RouteStick、VPB、VPO。StopCube、MoveCube、InsertPeg 原三档在 `4137a41`/`13e5151` 里 `self.difficulty` 只在 `__init__` 赋值从不读取，**不加档**；MoveCube 只按用户原话推 xhard | 用户原话「对所有task 原版中有难度梯度的」；调查 A |
| 4 | **每档都要比前一档更难**：在该环境已加码的所有字段上单调不减，且至少一个字段均值上升；新档取值区间允许与 xhard 重叠，但均值必须高于 xhard | 用户原话「都要比现在的hard更难」；调查 E 待决 9 |
| 5 | **「均匀」的执行定义**（M9 未推翻前按此实施）：① 跨局：每个对象作为交换参与者的边际频率相等（卡方 p>0.05，10000 局离线）；② 局内：每局各对象参与次数极差 ≤1（做不到时 ≤2）；③ 不许「刚换完立即换回」。**碰撞检测是硬约束，均匀性在可行集合内实现**，不得为均匀去掉碰撞判定 | 用户原话「碰撞检测后 对象层面的选择仍然均匀」；调查 C/D |
| 6 | **均匀化算法 xhard 与新档共用**，因此 VUS、BUS、VR 的 xhard 重冻；其余 9 个未动 xhard 的环境（含 InsertPeg、StopCube、VU、BU、PH、VPB、VPO、PatternLock、RouteStick、BinFill、Pick/Swing）**xhard 逐位复现 v5-01**（回注闸门 X0，见 3.2） | 用户原话把均匀性当缺陷提出，不是新档专属；M4 |
| 7 | **MoveCube「往外推」= 三物体（方块、goal 圆盘、杆根）都改为环带拒绝采样**，禁区形状从圆改为环带 [R_in, R_out]，采样框同步放大，仍是直接拒绝、不用 bias | 用户原话「把 movecube 继续往外推」；V5 口径 8 |
| 8 | **演示与执行的时长上限**：生成侧 `fail_safe_limit=5000`（按 `elapsed_steps` 计，含 NO RECORD 约 330 步）不动；每档最坏总步数 ≤ 4500（留 10%）。评估侧预算按 M1 定 | V5 口径 2；调查 A 五 |
| 9 | **只做一次对拍、一次生成**：V1 = 16 任务 × 9 局原三档与最原始基线 `13e5151` 逐位比；生成 = 一次多 worker 运行，每格「10 候选 + 3 正式局」（M5 未改前），不跑第二遍，不开 fail recover | V5 口径 12 |
| 10 | **待决项不许自填**：1.4 的 M 项逐条问用户；实施中新发现的追加进 1.4。细节（取整、预算次数、平局规则、seed 偏移）实施方自决并在报告注明 | V5 口径 14；用户 2026-09-24 |
| 11 | **新档命名**在 M3 答复前用 X1/X2/X3 占位；实现上所有 `== "xhard"` 判断改为**族判断**（`is_newvalue_difficulty()`），不得复制粘贴四份分支 | 调查 A 二 |

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

### 1.3 调查结论先行（用户没问、但决定方案走向的事实）

| 事实 | 结论 | 详见 |
|---|---|---|
| 哪些任务「原版有梯度」 | **13 个**。StopCube、MoveCube、InsertPeg 原三档逐字同值（`config_native` / `_CONFIG_CURRENT` 三档共用），它们的 xhard 是 V4 新造的 | 2.1 |
| 现有管道认几个新值档 | **只认一个，名字写死 `"xhard"`**：`src` 约 60 处 `== "xhard"` 分支、约 45 处 `decision["xhard"]` 查表，共用件 `sampling_config.XHARD_KEY/_strip_xhard`、`episode_spec.spec_kind_for`、`task_goal._unmask_pick_count`、`xhard_home_site.validate_demo_plan`；scripts 侧 `v4_specs.DIFFICULTY` 模块常量、单一 `SEED_RULE`、身份键不带难度。**加 3 档是一次管道改造，不是加三份 config** | 2.0 |
| 真正的时长天花板 | **评估预算 1301 步比录像器 5000 步先撞**。`scripts/evaluation.py` 写死 `max_steps=1300`（只计非演示步）。V5 xhard 已有局超出（BinFill ep0 非演示 1523、PickXtimes ep3 1309）；RouteStick L ≥ 27 必超时；BinFill 投入 ≤6、PickXtimes ≤8 次、PH pick ≤7 才能守住。**不放宽预算，用户指定的「按数量」维度在 BinFill/PickXtimes/PH 上加不出 3 档，PatternLock/RouteStick 也加不出** | M1、2.0 |
| Unmask 内环 swap 为什么不均匀 | **根源是发起者抽样，不是碰撞**：`swap_initiator_indices=randperm(3)[:2]` 只可能是 0/1/2，bin_3 永不发起的概率约 50%（其余 16%）；且 bin_3 在 xhard 恒为空容器。碰撞拒绝作用在「槽对」上、与对象编号无关，所以对编号对称的规则在碰撞拒绝后仍均匀。推荐 S5「计数均衡贪心 + 可行槽对图连通作 reset 接受条件」：10000 局边际 p=0.997/0.966，局内极差 ≤1 占 95.7%/89.4%，撤销率 0；代价 BUS 约 1/3 内环布局在 reset 被拒 | 2.2 |
| Unmask 外环 swap 能不能局内均匀 | **在 V5 路径约束（全程可见、离内环净距、离按钮）下做不到**：每窗 45 个槽对只有 5.6/3.6 对可行，28%/44% 的槽某窗无任何搭档，任何算法「全员参与」≤4.3%。能做到的是跨局边际均匀（放置后序号随机重排）+ O4 均衡贪心把未参与率从 40%/54% 降到 28%/43%、撤销率从 42%/56% 降到 0.5%/6.7% | 2.2、M10 |
| VR swap 为什么不均匀 | 跨局已均匀（p=0.93），**局内不均**：各块参与次数极差 ≤1 的局只有 14.7%，每局平均 0.99 次立即换回。规划失败 40% 的根因是可行图太稀（每块平均只能与 1.54 块互换、41% 布局有孤立块），**不是「3 个最近」限制**，放开后成功率与路径长度不变。S5 均衡贪心 + 整条重试 ≤20 次：极差 ≤1 达 96.7%、撤销率 0、reset 成功率不降 | 2.5 |
| MoveCube 能推多远 | **不放大框 R 上限约 0.07**（exec goal 框半宽只有 0.06，R=0.08 时 128 次预算耗尽 17.7%）。推荐环带 + 放大框 + 远端 x ≤ 0.11 封顶 + 方块离杆 ≥ 0.04：T1 [0.08,0.12] / T2 [0.10,0.14] / T3 [0.12,0.16] 离线 20000 局布局成功 100%，peg_push 路点离基座 >0.80 m 的比例 3.3～4.5%（V5 3.6%）。V5 xhard 另有 2.7% 的局方块生成时压在杆身上，顺带修 | 2.6 |
| VPB/VPO reset 成功率低的根因 | xhard 分支根本不用 `goal_site`（初始化沉到桌下），它却以半径 0.06/0.10 的圆占着布局。新档移出后 3 块 4 台的 reset 成功率 VPB 81.8% → 97.5%、VPO 50.0% → 97.5%，才腾得出加目标台的余量 | 2.10 |
| PatternLock/RouteStick 还能怎么加难 | 两者在 V5 口径（不改布局、演示 25～35 s）下已到顶。RouteStick 只剩段数 L（直线加长到 1×11 就超 0.81 m 可达极限）；PatternLock 5×5 不重访已满，要么允许重访（不改布局），要么换 6×6@0.08 / 7×7@0.07 网格（7×7 前视像素间距 9.5 px、节点直径 8.2 px，几乎相接）。**两者都必然突破 1301 步或 25～35 s 演示带** | 2.11、2.12、M1、M11 |
| 数量类任务的物理上限 | PH 现框 N=10 时 reset 只有 71.8%（xhard 已骑在上限），只把 y 半宽放到 0.30 + 预算 1024 后 N≤14 ≥99.8%；PickXtimes 卡在 5000 帧（20 次约 4982 帧，上限定 18）；SwingXtimes 卡在文本（局部序数表只到 tenth）；BinFill 有余量（现框 N=17 95.8%）。可达性比相机视野紧：Pick/Swing 框远角已 0.780 m（V5 验证过最远 0.765 m），**框只能往 y 向放大** | 2.7～2.9 |
| 规模 | 13 环境 × 3 档 + 重冻 4 个 xhard（MoveCube、VUS、BUS、VR）= 43 格，430 候选、129 正式局；另 12 个 xhard 回注复现 36 局。v5-01 48 局 32 GB、25 min 多 worker；V6 估 100～130 GB、生成约 3 h，V1 两侧各约 3 h | 三 |

### 1.4 待决项（实施前逐条答复，不许自填）

「建议」一列是调查方/规划方的推荐，**不是批准值**。

**跨环境（先答 M1～M9，其余依赖它们）**

| 编号 | 问题 | 选项 | 建议 | 结论（用户答复） |
|---|---|---|---|---|
| M1 | **评估预算 1301 步怎么处理**。V5 FROZEN_FILES 判据写明「不得通过挪动评估预算常量来吸收变长的局」；但不放宽，BinFill/PickXtimes/PH 的「按数量」维度和 PatternLock/RouteStick 都加不出 3 档 | (a) 不放宽：新档执行段封顶 1301，BinFill/PickXtimes/PH 改为只加干扰/块数、PatternLock 换网格、RouteStick 只做 [22,26] 一档。<br>(b) **按档放宽，`evaluation.py` 不改**：新档推理走 `scripts/eval/v4_eval.py --max-steps`，每档预算 = 该档离线最坏执行段 × 1.2 向上取百，冻进 specs header，生成后按实测复核；V5 那句判据改写为「`evaluation.py` 不改，新档预算只在规格 header 里冻结」。<br>(c) 全部新档统一一个大预算（如 2600） | (b) | |
| M2 | MoveCube 要不要也加 3 档（原版无梯度，口径 3 之外） | (a) 不加，只把 xhard 往外推。<br>(b) 加，用 T1/T2/T3 环带当 X1/X2/X3，xhard 不动 | (a) | |
| M3 | 新档命名（进 `VALID_DIFFICULTIES`、spec `identity.difficulty`、h5 `setup/difficulty`、视频文件名） | (a) `xhard2 / xhard3 / xhard4`。<br>(b) `xhard_l2 / l3 / l4`。<br>(c) 其他 | (a) | |
| M4 | 未被 V6 改动的 9 个环境的 xhard 是否必须逐位复现 v5-01 | (a) 必须：加回注闸门 X0（用 v5-01 的 specs 行在 V6 代码上重跑 3 正式局，h5 SHA 与 v5-01 相同）。<br>(b) 不要求，全部 16 个 xhard 重抽 | (a) | |
| M5 | 每格规模 | (a) 沿用「10 候选（尝试上限按环境 30～60）+ index 0/3/6 三局正式」。<br>(b) 新档减到「6 候选 + 2 正式」。<br>(c) 其他 | (a) | |
| M6 | 均匀化算法（S5）是否同时替换 VUS/BUS/VR 的 xhard 并重冻 | (a) 是（口径 6）。<br>(b) 只用于新档，xhard 保持 V5 的不均匀 | (a) | |
| M7 | Unmask 内环 xhard 里「bin_3 恒为空容器」（藏 cube 只在 bin_0..2）算不算均匀性缺陷、要不要一并随机化空容器位置 | (a) 算，随机化（xhard 流原地移位，L1(a)）。<br>(b) 不动 | (a) | |
| M8 | **Unmask 的 pick 超过 3 需要第 4～6 种被藏 cube 颜色**（现只有 red/green/blue；干扰色池黄/青/品红是全局的不能动） | (a) 新增 orange / purple / brown 三色（避开白色与高亮圆盘、避开干扰色池），X1 起用第 4 色，VU X2/X3 用第 5/6 色。<br>(b) 允许重复目标色（语义变成「按位置记」，需实测）。<br>(c) pick 止步于 3，Unmask 只按干扰数与 swap 次数加档 | (a) | |
| M9 | 「均匀」的正式定义（口径 5 的执行定义是否成立） | (a) 口径 5：跨局边际相等 + 局内极差 ≤1（做不到 ≤2）+ 不立即撤销。<br>(b) 只要跨局边际相等（VR 现状已满足，等于不改）。<br>(c) 每对等概率（与「全员参与」冲突，几何上做不到） | (a) | |

**四个 Unmask 环境（2.2～2.4）**

| 编号 | 问题 | 选项 | 建议 | 结论 |
|---|---|---|---|---|
| M10 | 外环在 V5 路径约束下局内做不到均匀，怎么办 | (a) 接受「跨局边际均匀 + O4 尽量均衡」，报告逐局未参与数。<br>(b) 放宽「路径全程可见」（零可行搭档槽 31.7% → 15.0%），代价交换会出画。<br>(c) 外环改成沿环切向成对放置，几何上保证每个都有搭档（改布局）。<br>(d) 新档不再加外环干扰数 | (a) | |
| M11 | BUS X3 评估余量只有 8%（最坏 1195 步，M1 选 (b) 时不成问题） | (a) 接受。<br>(b) X3 的 pick 保持 3。<br>(c) BUS 新档交换改 ×2 速（余量 17%）。<br>(d) swap 降到 [12,13] | M1 选 (b) 则 (a)；否则 (c) | |
| M12 | VU/BU 干扰容器环带：贴身环带 N=18 一次放满率只有 95%/91%，N=20 只有 58%/48% | (a) 新档放宽到 [0.2425,0.45]（28 个 100%、32 个 97.5%）。<br>(b) 保持贴身环带，干扰上限约 16～17 | (a) | |

**其余环境**

| 编号 | 问题 | 选项 | 建议 | 结论 |
|---|---|---|---|---|
| M13 | MoveCube 推到哪一档 | (i) 框不动、R 0.05 → 0.07（上限，exec goal 挤到四角）。<br>(ii) T1 环带 [0.08,0.12]。<br>(iii) T2 环带 [0.10,0.14]。<br>(iv) T3 [0.12,0.16] | (iii)，各跑 smoke 后再定 | |
| M14 | VR 新档布局区要不要扩（现 6 块区域 8 块 reset 只有 0.40） | (a) 不扩，8 块 0.40、抽签上限提到 60。<br>(b) 扩到 x∈[-0.30,0.20]、y∈[-0.30,0.30]，做 7/8/9 块（0.81/0.78/0.73），推翻 V5 L51，需先验可达 | (a) | |
| M15 | VPB/VPO 多次交换（s ≥ 2）需要新代码（现 `swap_flat_two_lane` 只支持一对一窗口） | (a) 写多窗口交换，按上表 s=2/3。<br>(b) s 固定 1，只用 k/T/v 加档 | (a) | |
| M16 | VPO X3 演示约 3320～3830 帧（约 2 分钟视频，录像器占用约 88%）是否接受 | (a) 接受。<br>(b) 改 v∈[4,5]、s=3 | (b) | |
| M17 | PatternLock 走哪条路（随 M1） | (a) M1(b)：5×5 不改布局，允许重访、禁止立即回头，段数 [30,34]/[38,44]/[48,56]。<br>(b) M1(a)：换网格 6×6@0.08 [33,35] / 7×7@0.07 [38,40] / [42,44] | (a) | |
| M18 | PatternLock/RouteStick 的 V5「演示 25～35 s」口径对新档是否作废 | (a) 作废，新档只受 4500 步与评估预算约束。<br>(b) 保留 ⇒ 两环境无法加档 | (a) | |
| M19 | PH 新档把 y 半宽 0.20 → 0.30、预算 256 → 1024；现 xhard 要不要跟着改（会平移它的产物、违反 M4） | (a) 只改新档。<br>(b) xhard 一起改并重冻 | (a) | |
| M20 | PickXtimes/SwingXtimes 干扰块超过 3 时的颜色 | (a) 黄/青/品红循环重复。<br>(b) 扩充 `DISTRACTOR_COLORS`（全局，牵连 Unmask）。<br>(c) 非目标原色多放几块 | (a) | |

### 1.5 本计划推翻或修改的 V5 决策

| V5 决策 | V6 处理 |
|---|---|
| 口径 9 / L37：PatternLock、RouteStick 演示 25～35 s | 新档不再受此约束（M18）；xhard 保持 |
| 3.2 FROZEN_FILES「不得通过挪动评估预算常量来吸收变长的局」 | `evaluation.py` 仍不改；新档预算走 `v4_eval --max-steps` 并冻进 header（M1(b)） |
| L51：VR 布局区不扩 | 维持（M14(a) 建议），若用户选 (b) 则推翻 |
| VUS/BUS 内环「3 个固定发起者 + 最近邻搭档」、VR「k%6 轮流 + 3 最近可行」 | 全部换成 S5 均衡贪心（M6） |
| 2.9 MoveCube「R=0.05 圆形禁区」 | 改为环带 + 放大框（口径 7） |
| 2.16 PH/VPB/VPO 只修障碍框 | 新档加档并（VP）移出 `goal_site` 障碍 |

## 二、逐环境改动

### 2.0 全局要改什么（难度档管道改造）

改造原则：**族判断替代字面比较，一份档位表替代复制的分支**；原三档路径上不新增、不挪动任何随机抽样；共用函数的新参数默认关闭。

| 文件 | 符号 | 改什么 | 原三档风险 |
|---|---|---|---|
| `utils/difficulty.py` | `VALID_DIFFICULTIES` | 加 3 个名字；新增 `NEWVALUE_DIFFICULTIES`（xhard + 三新档）、`is_newvalue_difficulty()`、`newvalue_tier()`（0～3） | 无 |
| `utils/sampling_config.py` | `XHARD_KEY`、`_strip_xhard`、`_xhard_shape`、`assert_native_decision` | 单一键名改键名集合；剥离集合覆盖四个新值键。V0 核验「剥掉全部新值键后与原三档快照逐字相同」照旧 | 中：三档必经，但只多剥名字 |
| `utils/episode_spec.py`、`utils/task_goal.py`、`utils/xhard_home_site.py`、`utils/unmask_swap_xhard.py` | `spec_kind_for`、`_unmask_pick_count`、`validate_demo_plan`、`decision["xhard"]` 读取 | 改族判断；按本局档位取 `decision[<tier>]` 子树 | 无 |
| `utils/task_goal.py` | `num2words`、`_ORDINALS` | 1～20 已覆盖，新档最大 18/13，不越界；SwingXtimes 文件内局部 `ordinals` 表扩到 twentieth（只影响 xhard 族子目标文本） | 无 |
| `utils/xhard.py`、`unmask_distractor_sampler.py`、`unmask_distractors.py` | 环带、干扰数、颜色轮转 | 容量参数化，从档位子树读 | 无 |
| 各环境文件 | `config_xhard` → `config_<tier>`、`XHARD_DECISION` → 档位表、`_native_decision`、`_resolve_sampling_config` 兜底、全部 `== "xhard"` | 每档一份 config；decision 子树按档名放行（自动派生的 `number_range.*` 一类会自动长出新键，手写的 `decision.xhard.*` 改成 `decision.<tier>.*` 表） | 中；VideoRepick 的 `elif self.difficulty == "hard"` 链必须让族判断在前；RouteStick `.get(difficulty, 回退 easy)` 改缺键抛错 |
| `utils/object_generation.py` | `spawn_random_cube/target` | 新显式参数（MoveCube 环带外半径、x 封顶、离杆距离；PH/BinFill y 半宽由调用方传框，不加参数）默认 None 整段跳过 | 高：V1 覆盖 |
| `scripts/parity/v4_specs.py` | `DIFFICULTY`、`SEED_RULE`、header 档位比对 | 档位改 CLI 参数（默认 xhard 保 V5 字节不变）；seed 偏移按档：xhard 重冻 6e6、X1 8e6、X2 10e6、X3 12e6 | 无 |
| `scripts/parity/v4_rollout.py`、`v5_generation.py`（或新 `v6_generation.py`）、`train_split_config.py`（`RELEASE_NOTES` 加 `newtask-v6`）、`train_split_runner.py` | 从 header 取档位；报告口径按档；产物目录 `artifacts/newtask-v6/v6-01/<tier>/…`、快照 `scripts/configs/newtask-v6/v6-01/<tier>/specs.jsonl` | 无 |
| `scripts/eval/v4_eval.py` | `--max-steps` | 若 M1(b)：缺省从 specs header 的 `eval_max_steps` 读，命令行可覆盖 | 无 |
| tests | `test_v4_xhard_{pickxtimes,swingxtimes,stopcube}`（断言恰 4 档）、`test_episode_spec_recorder`、`test_sampling_config_split`（改指 V6 快照）、`test_v5_xhard_pickswing`（`NATIVE_AST_GOLDEN` 不动；分支原文断言改族判断）、`test_v5_generation_tools`、`test_episode_action_sampling` | 扩到 7 档 | — |
| 不动 | 录像器、`seed_layout.DIFFICULTY_ORDER`、`generate_dataset_newseed.py`、`scripts/injection/*`、`scripts/evaluation.py` | — | — |

评估预算与总步数（口径 8；M1(b) 下每档 `eval_max_steps` 预定值，生成后按实测复核）：

| 环境 | X1 | X2 | X3 | 最坏总步数（5000 内） |
|---|---|---|---|---|
| BinFill | 3100 | 3700 | 4400 | 2550 / 3080 / 3610 |
| PickXtimes | 4300 | 4900 | 5400 | 3524 / 4010 / 4496 |
| SwingXtimes | 1800 | 2300 | 2700 | 1480 / 1860 / 2240 |
| PH | 2000 | 2500 | 3000 | 1662 / 2058 / 2454 |
| VU / VUS（交换在演示段，不计） | 1300 | 1300 | 1300 | ≤1750 |
| BU | 1300 | 1300 | 1300 | ≤1100 |
| BUS | 1300 | 1400 | 1500 | 1063 / 1129 / 1195 |
| VR | 1800 | 2100 | 2400 | 2.7k / 3.1k / 3.6k（含演示） |
| PatternLock（M17(a)） | 1500 | 1900 | 2400 | 演示+执行 ≈ 2×段数×35+300 ⇒ X3 ≈ 4220 |
| RouteStick | 1650 | 2050 | 2500 | 100·L+327 ⇒ X3 ≈ 4427 |
| VPB / VPO | 1300 | 1300 | 1300 | VPO X3 ≈ 4360（M16） |

### 2.1 改动范围总表

| 环境 | 原版梯度 | V6 动作 | xhard 处置 |
|---|---|---|---|
| BinFill、PickXtimes、SwingXtimes、PH、PatternLock、RouteStick、VPB、VPO、VU、BU | 有 | 加 X1～X3 | 逐位复现 v5-01（X0） |
| VUS、BUS、VR | 有 | 加 X1～X3 + 均匀化 | 重冻（均匀化共用） |
| MoveCube | 无 | 只推 xhard | 重冻 |
| InsertPeg、StopCube | 无 | 不动 | 逐位复现 v5-01（X0） |

### 2.2 四个 Unmask 环境的共用事项（交换对象均匀化）

**现状（VUS/BUS 内环）**：发起者 `swap_initiator_indices=randperm(3)[:2]` + `swap_initiator_third`，第 k 次用 `swap_indices[k%3]`；搭档在 step 的 AST 锁定循环里按实际位姿取 XY 最近邻；reset 时 `predict_inner_windows`/`prejudge_inner_windows` 预判，运行时 `joint_sweep_from_actual` 复核。实测参与频率 VUS [.236,.283,.279,.201]、BUS [.218,.287,.287,.208]（p≈0）。

**要做（内环，S5）**：
1. reset 时对 4 个位姿槽的 6 个槽对各跑一次 `check_swap_sweep_prefiltered`，得可行槽对图 G；G 不连通 ⇒ 抛 `SceneGenerationError` 重抽（VUS 拒 4.6%、BUS 拒 33.5%）。
2. 在主流上**追加一次** `torch.rand(n_swaps)` 作平局打破，预规划整段交换序列：每次在 G 的可行对里选「两块已参与次数之和最小」的一对，平局按该随机数，禁止与上一次相同的对；整条极差 >1 时重排（≤20 次，仍不满足接受极差 2）。
3. 运行时锁定循环里的搭档分支改为读预规划结果（仿 VideoRepick `_xhard_planned_partner` 先例），仍做 `joint_sweep_from_actual` 复核；外环 H1 守卫改为覆盖 G 中全部可行槽对。
4. M7(a)：藏 cube 的容器改为从 4 个内环容器里 `randperm(4)[:pick]`，空容器位置随机。
5. 离线目标：边际 p>0.05，极差 ≤1 ≥ 89%，撤销率 0；单测锁定「S5 在 G 为完全图时的边际严格均匀」。

**要做（外环，O4）**：`plan_distractor_swaps` 改为均衡贪心（每窗在可行槽对里选参与次数和最小、禁止立即撤销），放置后追加一次 `randperm(count)` 重排序号以消除放置序偏差；候选评估 `evaluate_outer_candidate` 的 vis → btn → inner_clear → exact 四道判定不动（M10(a)）。离线目标：未参与对象 VUS ≤30%、BUS ≤45%，撤销率 ≤1%/≤7%，整局可行率 ≥99%/≥98%。

**pick 次数与颜色（M8）**：pick ≥4 时需第 4 色；VUS/BUS 内环 4 个容器 ⇒ pick 上限 4；VU/BU 藏 cube 的容器从 `spawned_bins[:3]` 改为 `[:pick]`。新色在 256 像素画面的可分辨性要在 S3 演示里目视核对。

**验收**：`UNMASK_INNER_UNIFORM=PASS env=<E> chi2_p>=0.05 range_le1>=0.89 undo=0`（离线 10000 局，S2 单测化）；`UNMASK_G_REJECT=REPORT env=<E> rejected=…`；`OUTER_SWAP_BALANCE=REPORT unvisited_mean=… undo=…`。

### 2.3 VideoUnmask / ButtonUnmask

| 字段 | xhard | X1 | X2 | X3 |
|---|---|---|---|---|
| VU 干扰 / 含 cube / pick | 15 / [7,8] / 3 | 20 / [10,10] / 4 | 24 / [12,12] / 5 | 28 / [14,14] / 6 |
| BU 干扰 / 含 cube / pick | 14 / [7,7] / 3 | 19 / [9,10] / 4 | 23 / [11,12] / 5 | 27 / [13,14] / 5 |
| 环带 | [0.2425,0.3289] | [0.2425,0.45]（M12） | 同 | 同 |

- 干扰含 cube 的颜色仍三色平衡轮转（L12）；被藏 cube 用 M8 新色。
- 帧数：每次 pick 最坏 125 + put down 52；VU X3 最坏非演示 1022，BU X3（pick 5）最坏 1004，都在 1301 内；BU pick 6 余量只剩 12%，故 X3 停在 5。
- 揭示段 36 个物体的每步耗时未实测（V5 15 个时 35～55 ms），S3 演示时记录。
- 验收：`UNMASK_RING=PASS n=<N> in_band=<N> visible=<N>`；`UNMASK_PICK_FRAMES=REPORT max_exec<=1301`。

### 2.4 VideoUnmaskSwap / ButtonUnmaskSwap

| 字段 | xhard | X1 | X2 | X3 |
|---|---|---|---|---|
| VUS swap / pick / 干扰 | [8,12] / 3 / 10 | [12,14] / 4 / 12 | [15,17] / 4 / 14 | [18,20] / 4 / 16 |
| BUS swap / pick / 干扰 | [6,8] / 3 / 10 | [9,10] / 4 / 12 | [11,12] / 4 / 14 | [13,14] / 4 / 16 |

- 外环环带沿 V4 [0.2675,0.45]，容量上界约 29，不是瓶颈；干扰 14/18 时整局可行率（O4）VUS 99.9%/100%、BUS 99.6%/98.6%，但零可行搭档的槽升到 37%/50%（VUS）、50%/61%（BUS），未参与数随档上升，按 M10(a) 如实报告。
- BUS 交换段计入评估步：X1/X2/X3 最坏 1063/1129/1195（M11）。VUS 演示段 n=20 时 726 帧。
- 内环不扩到 5/6 个（正五边形/六边形 G 100% 连通但外环更挤、BUS 锚点要另设、pick 还得再加色），留作后续。
- 验收：沿 V5（外环窗口数 = n_swaps、`bin_collision=0`）+ 2.2 的均匀性判定。

### 2.5 VideoRepick

**现状**：k%6 轮流发起 + reset 从 3 个最近可行里选搭档，规划失败 39.96%；跨局均匀、局内极差 ≤1 只有 14.7%。

**要做**：
1. 搭档规划改 S5：每次在全部可行对（不限最近 3 个）里选参与次数和最小的一对，平局随机（主流追加一次抽取得规划种子，平局与重试在局部生成器上做），禁止立即换回；整条极差 >1 重排 ≤20 次，仍不满足接受极差 2（6 块时 3.3% 的局）。reset 成功率不变（0.590），极差 ≤1 达 96.7%、撤销 0。
2. 5 mm 规划余量保留、按钮继续当障碍（否则重现 V5 P4 单帧跳变）。
3. 新档：

| 字段 | xhard | X1 | X2 | X3 |
|---|---|---|---|---|
| 块数 / swap / repick | 6 / [8,12] / [4,6] | 7 / [12,16] / [6,8] | 8 / [16,20] / [8,10] | 8 / [20,24] / [10,12] |
| reset 成功率（离线） | 0.59 | 0.52 | 0.40 | 0.40 |
| 抽签尝试上限 | 30 | 40 | 60 | 60 |
| 演示时长 | 22～28 s | 28～35 s | 35～42 s | 42～49 s |

- 每次 swap 恰 50 帧、每次 repick 约 125～140 帧；X3 最坏控制步约 3.6k。
- 淘汰的布局系统性偏向「块离按钮远」，只改选块规则去不掉，按 M14 决定要不要扩区。
- 7～8 块时可达与重拿碰邻块未验证，S3 每档至少 4 局演示。
- 验收：`VR_UNIFORM=PASS range_le1>=0.93 undo=0 all_participate=1`；`VR_RESET=REPORT rate=…`。

### 2.6 MoveCube（只推 xhard，重冻）

**现状**：方块、goal、杆根都拒绝落在 (0,0) R=0.05 圆内；exec goal 框半宽 0.06、demo goal 0.11、方块候选 0.10；2.7% 的局方块生成时压在杆身上。

**要做（M13 建议 T2）**：
1. goal 中心、方块候选中心与方块最终中心只许落在环带 [R_in, R_out]；杆根仍只查内半径。
2. 各采样框半宽放大到 R_out（demo/exec goal 统一），远端 +x 侧封顶 x ≤ 0.11（不向机器人对侧外扩）。
3. 方块到杆身距离 ≥ 0.04（候选与最终两处都查，候选处再多留 0.02）。
4. 参数放各档 decision 子键，不写进原三档共用的 `NATIVE_SAMPLING.positions`；`spawn_random_target/cube` 新增环带外半径、x 封顶、离杆距离三个显式可选参数（L4(b)），默认 None 整段跳过；回放按同一规则复核。

| 档 | 环带 | goal 框半宽 | 方块候选半宽 | 方块-goal 距离均值 | peg_push 路点 >0.80 m | 候选预算耗尽 |
|---|---|---|---|---|---|---|
| V5 xhard | [0.05,∞) | 0.11 / 0.06 | 0.10 | 0.156 / 0.136 | 3.6% | 3e-28 |
| T1 | [0.08,0.12] | 0.12 | 0.12 | 0.166 | 3.3% | 9e-11 |
| T2 | [0.10,0.14] | 0.14 | 0.14 | 0.189 | 4.4% | 3e-10 |
| T3 | [0.12,0.16] | 0.16 | 0.16 | 0.212 | 4.5% | 4e-8 |

- 相机不构成约束（front 相机桌面 x 可见 [-0.90,0.43]，三物体出画 0%）；演示最长估约 1100 帧；成功判据（0.048 / 0.05 水平距）不随位置变。
- 风险：外圈 peg_push 规划失败率未知（V5 失败本就集中在 peg_push），S3 先 smoke 再每档 12 局（三种 way 各 4 局）与 V5 对照。
- 验收：`MC_RING=PASS violations=0 layout_fail=0`（5000 局离线）+ `MC_DEMO=REPORT ok=…/12`。

### 2.7 BinFill

| 档 | 总块 | 投入 | 框 / 预算 | reset | 帧数（均值 / 最坏） |
|---|---|---|---|---|---|
| xhard | 12 | [5,7] | 现框 / 256 | 100% | 1195 / 2020 |
| X1 | 14 | [7,9] | 现框 / 256 | 100% | 1559 / 2550 |
| X2 | 16 | [9,11] | 现框 / 1024 | 100% | 1923 / 3080 |
| X3 | 18 | [11,13] | y 半宽 0.32 / 1024 | 100% | 2287 / 3610 |

- 干扰块（总块 − 投入）每档恒为 5～7；同色成团上限 T=3 沿用，重排比例 7.7% / 18.4% / 11.3%，兜底 0。
- 每色投入最多 13，`num2words` 不越界。y 半宽 0.32 远角 0.758 m，在 V5 验证的 0.765 m 内。
- 风险：2 cm 间距下块越多夹爪越易碰邻块，演示成功率未测。

### 2.8 PickXtimes / SwingXtimes

| 环境 | 档 | 次数 / 轮数 | 总块（有色 3 + 干扰） | reset | 帧数（均值 / 最坏） |
|---|---|---|---|---|---|
| PickXtimes | xhard | [6,15] | 6 | 100% | 1907 / 3767 |
| | X1 | [10,14] | 9 | 100% | 2165 / 3524 |
| | X2 | [13,16] | 12 | 100% | 2595 / 4010 |
| | X3 | [16,18] | 15 | 100% | 3025 / 4496 |
| SwingXtimes | xhard | [4,10] | 6 | 96.9% | 800 / 1290 |
| | X1 | [9,12] | 9 | ≈96% | 1070 / 1480 |
| | X2 | [12,16] | 12 | 96.2% | 1339 / 1860 |
| | X3 | [16,20] | 15 | ≈96% | 1647 / 2240 |

- 框不动（半宽 0.25、中心距 0.08，远角 0.780 m 已是可达边界）；PickXtimes 预算 1024、Swing 256 沿用。
- PickXtimes 次数上限定 18（20 次最坏 4982 帧）；X1 区间与 xhard 重叠但均值 12 > xhard 10.5 且干扰翻倍（口径 4）。
- 干扰块颜色按 M20；SwingXtimes 局部序数表扩到 twentieth（xhard 族分支内）。
- Swing 约 3% 圆盘放不下的失败原样带入。

### 2.9 PickHighlight

| 档 | pick | 总块 spawn | 干扰 = spawn − pick | 框 / 预算 | reset | 帧数最坏 |
|---|---|---|---|---|---|---|
| xhard | [5,7] | [8,10] | 1～5 | y 0.20 / 256 | 87% | ≈1250 |
| X1 | [7,8] | [11,12] | 3～5 | y 0.30 / 1024 | 100% | 1662 |
| X2 | [8,10] | [13,14] | 3～6 | 同 | ≈99.8% | 2058 |
| X3 | [10,12] | [15,16] | 3～6 | 同 | 91～97% | 2454 |

- 抽法改为「干扰数单独抽、spawn = pick + 干扰」，干扰下限 3；x 不动，y 半宽 0.30 远角 0.749 m。
- 目标文本无数字，不受数词限制；HSV 任意色沿用。

### 2.10 VideoPlaceButton / VideoPlaceOrder（实施方定维度）

**维度选择理由**：可用维度只有演示方块数 k（VPB 要求目标台 T ≥ 2k）、目标台数 T（reset 成功率主导：goal 移出后 T=5/6/7 为 86.8%/52.2%/14.2%）、交换次数 s（每次约 +50 帧，M15）、VPO 每块访问数 v（每 +1 约 +170 帧）。干扰方块需第 4 种颜色，不用。**前提**：新档把从不使用的 `goal_site` 移出布局障碍（只改新档）。

| 环境 | 档 | k | T | v | s | 演示帧 | reset |
|---|---|---|---|---|---|---|---|
| VPB | xhard | 2 | 4 | — | 1 | ≈1370 | 81.8% |
| | X1 | 2 | 5 | — | 2 | ≈1420 | 86.8% |
| | X2 | 3 | 6 | — | 2 | ≈2000 | 52.2% |
| | X3 | 3 | 6 | — | 3 | ≈2050 | 52.2% |
| VPO | xhard | 2 | 4 | [2,4] | 1 | 1520～1952 | 50.0% |
| | X1 | 2 | 5 | [4,5] | 1 | 1910～2250 | 86.8% |
| | X2 | 3 | 5 | [4,5] | 2 | 2810～3320 | 86.8% |
| | X3 | 3 | 6 | [5,6]（M16(b) 则 [4,5]、s=3） | 2 | 3320～3830 | 52.2% |

- 30 次抽签攒 10 条：单次 0.522 时 98.8%，抽签上限 X2/X3 提到 40。
- 执行段约 200 步，评估预算无压力；总步数 VPO X3 ≈ 4360 是全 V6 最接近 5000 的一格。

### 2.11 PatternLock

- M17(a)（随 M1(b)）：5×5、间距 0.1 布局不动；允许重访（禁止立即回头），段数 [30,34] / [38,44] / [48,56]；每段约 35 帧 ⇒ 演示 ≈1120 / 1435 / 1820 帧，执行段同长；搜索预算 20000 沿用。
- M17(b)（随 M1(a)）：6×6@0.08 [33,35] / 7×7@0.07 [38,40] / [42,44]，命中率约 1.0，执行余量 ≥20% / ≥15% / 4～6%；7×7 远排 44、46 号节点 screw 直达失败需 RRT 兜底，前视像素间距 9.5 px 几乎相接。
- 验收：`PL_DEMO=REPORT segments=… frames=… exec<=eval_max_steps`。

### 2.12 RouteStick

- 只剩段数 L（每段恒 50 帧；直线加长到 1×11 就 0.804 m 超可达）；X1/X2/X3 = [22,27] / [28,34] / [35,41]，演示 1100～2050 帧，总步数 100·L+327 ≤ 4427。
- M1(a) 下只能做 [22,26] 一档（L=27 第 1302 步超时）。
- 验收：`RS_DEMO_LEN=PASS rule=L*50`；`FAILSAFE_MARGIN=PASS max_elapsed<=4500`。

### 2.13 InsertPeg / StopCube（不动）

原三档逐字同值，不加档；xhard 逐位复现 v5-01（X0）。InsertPeg 若日后要加：杆数 5（第 5 根接受率外推约 0.56）或间隔 0.03 → 0.02，但 xhard 演示成功率仅约 40%，不建议。

## 三、改完怎么对拍

### 3.1 链路

源码 `configs` + `_native_decision` → `train_split_config.py extract --release newtask-v6` → `scripts/configs/newtask-v6/sampling_config.json`
→ 按档 `v4_specs draw --difficulty <tier>`（seed 偏移按档）→ `freeze` → `v4_rollout run` → 报告；推理 `v4_eval --max-steps` 从 header 读。
xhard 未改动的 12 个环境不重抽：从 v5-01 specs 复制行进 v6-01 的 xhard 档并重跑 3 正式局比 SHA（X0）。

### 3.2 验收判据

| 判据 | 查什么 | 判定行 |
|---|---|---|
| V0 | `config_easy/medium/hard` 与原三档消费的 `NATIVE_SAMPLING` 键零 diff；剥掉四个新值键后 decision 与 V5 快照逐字相同 | `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0` |
| LIGHTWEIGHT | `tests/lightweight/` 全量 ≤5 分钟，失败集合与 S0 基线（46 failed / 12 errors）相同；新增：族判断覆盖、S5 均匀性、环带、抽法单测 | `LIGHTWEIGHT=PASS failure_set_equal_baseline=1` |
| **V1（唯一硬闸门）** | 原三档 16×9 = 144 条与 `13e5151` 逐位比 | `NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0` |
| X0（M4(a)） | 12 个未改动环境的 xhard：v5-01 specs 行在 V6 代码重跑 3 局，h5 SHA 与 v5-01 相同 | `XHARD_REPLAY=PASS envs=12 compared=36 sha_equal=36` |
| FROZEN_FILES | 录像器 `git diff --quiet`；`evaluation.py` 与官方副本 diff；五入口 | `RECORDER_FROZEN=PASS EVAL_PY_UPSTREAM=PASS ENTRIES=5` |
| 生成报告（不设门槛） | 每格 draft/rollout/backfilled/shortfall；每局执行帧 vs `eval_max_steps`、总步数 vs 4500；均匀性统计（每局各对象参与次数、撤销数、外环未参与数）；MoveCube 环带违例；VP reset 率 | `V6_GENERATION=REPORT cells=43 draft_ok=… rollout_ok=… shortfall=… exec_over_budget=… elapsed_over_4500=… uniform_range_gt1=… undo=…` |

纪律沿 V5：V1 不过必须停下修；生成报告如实，攒不够记 shortfall 不降难度。

### 3.3 实施步骤

| 步 | 内容 | 产出 |
|---|---|---|
| S0 | 存 LIGHTWEIGHT 基线；V1 基线侧（`13e5151` worktree）开跑 | 基线失败集合、基线 h5 |
| S1 | 管道改造（2.0）：族判断、档位表、守卫、specs/rollout/eval 按档、tests 扩 7 档；此时三新档 config 先复制 xhard 值 | 12.135 + 报告 |
| S2 | 共用件：S5 内环/外环/VR 均衡贪心与离线均匀性单测；MoveCube 环带参数；VP `goal_site` 移出；PH 抽法；SwingXtimes 序数表 | 12.136～12.138 |
| S3 | 逐环境填新档值并做本机演示探针（每格 ≥4 局，MoveCube 12 局）；opus subagent 按环境组在独立 worktree 并行，主会话审核合并 | 12.139～12.147 + 逐环境报告 |
| S4 | 重导 `newtask-v6` 快照、测试改指 | 12.148 |
| S5 | V1 V6 侧 144 条 + X0 36 局回放 | 12.149 |
| S6 | 一次多 worker 生成 v6-01（43 格）；tmux 起、Monitor 挂 | 12.150 + 生成报告 |
| S7 | 总报告、scripts/README 更新、收尾只留正式产物 | 12.151 |

规模与时间（估）：v6-01 129 正式局 + 36 回放局，单局最长约 4400 步 ⇒ 生成约 3 h（本机 2 GPU 多 worker）；V1 两侧各约 3 h；产物 100～130 GB。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

N1 原三档路径不新增、不挪动任何随机抽样（V1 兜底）。N2 录像器、`evaluation.py`、五入口冻结。N3 待决项不自填。N4 新值流按 L1(a) 允许原地移位，但 xhard 未改动环境须过 X0。N5 共用函数新参数默认等价关闭，`NATIVE_SPEC_GOLDEN`/`NATIVE_AST_GOLDEN` 不动。N6 碰撞检测不为均匀让路。N7 每档最坏总步数 ≤4500。N8 文档禁硬编码行号。N9 subagent 一律 opus、并行不设上限、workflow 需逐次审批。N10 长任务 tmux + Monitor。

## 一、按阶段、按文件的逐项改动清单

见第一部分 2.0 表（文件/符号/改什么/风险四列即清单）；S3 逐环境的字段落点：

| 环境 | 新档 config 键 | decision 子树键 | 新增/改动方法 |
|---|---|---|---|
| BinFill | `configs[<tier>]`：色数、总块、投入色、投入数 | `<tier>.{layout_budget, region_half}` | `_spawn_cubes_xhard` 读档位 |
| PickXtimes / SwingXtimes | 次数区间、干扰数 | `<tier>.{distractor_count, min_center_gap}` | 干扰颜色轮转 helper；Swing `ordinals` 扩表 |
| PH | pick、干扰数 | `<tier>.{region_half_y, budget}` | 抽法「spawn = pick + 干扰」 |
| VU / BU | pick | `<tier>.distractor.{count, band, cube_range}` | 藏 cube 容器 `[:pick]`、新色表 |
| VUS / BUS | swap、pick、干扰 | `<tier>.{distractor, distractor_swap, inner_swap_policy}` | `_plan_inner_swaps_balanced`、G 连通判定、锁定循环内改读预规划 |
| VR | 块数、swap、repick | `<tier>.{min_center_gap, draw_attempts}` | `_plan_swap_partners_xhard` 改 S5 |
| MoveCube | — | `demo_layout.<tier>.{ring, x_cap, peg_clearance}` | `spawn_random_*` 三新参数 |
| PatternLock | 段数区间、允许重访 | `<tier>.path_search_max_attempts` | 路径搜索允许重访（禁立即回头） |
| RouteStick | `segment_count_range` | — | 缺键抛错 |
| VPB / VPO | k、T、v、s | `<tier>.{goal_in_avoid: false, swap_windows}` | 多窗口交换（M15） |

## 二、对拍闸门总表

V0 → LIGHTWEIGHT → V1 → X0 → FROZEN_FILES → 生成报告；判定行见 3.2。

## 三、runbook（参数名以 S1 实现为准）

```bash
# 只读核验
git diff --quiet 13e5151 -- src/robomme/env_record_wrapper/RecordWrapper.py && ls -1 scripts/*.py | wc -l
# 每次提交前
uv run python -m pytest tests/lightweight/ -q
# 单环境演示探针（S3）
uv run python scripts/parity/v4_rollout.py probe --env <Env> --difficulty <tier> --episodes 4
# V1
uv run python scripts/parity/train_split_runner.py --manifest scripts/configs/newtask-v3/subset_manifest.json --out artifacts/newtask-v6/v1/<side>
uv run --no-sync python scripts/parity/train_split_parity.py compare --run base=artifacts/newtask-v6/v1/base --run v6=artifacts/newtask-v6/v1/v6 --pair base/B:v6/B
# 生成（tmux 起）
tmux new-session -d -s v6gen "set -o pipefail; PYTHONUNBUFFERED=1 uv run python scripts/parity/v6_generation.py pipeline --run-id v6-01 --tiers xhard,X1,X2,X3 --workers 8 2>&1 | tee artifacts/newtask-v6/v6-01/run.log; echo \"EXIT_CODE=\$?\" >> artifacts/newtask-v6/v6-01/run.log"
```

## 四、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | 约 105 处 `"xhard"` 字面判断改族判断时漏掉一处，新档静默落进原三档或 xhard 路径 | grep 计数归零作 S1 验收；每环境每档一次 reset 断言 `spec_kind` 与档名 |
| 2 | BUS 内环 G 连通率 66.5%，reset 拒绝 1/3 | 抽签上限 60；如实报 shortfall |
| 3 | 外环局内不均匀（M10） | 报告逐局未参与数 |
| 4 | 新档演示成功率未测（抓放失败随次数累积；VR 8 块重拿碰邻块；MoveCube 外圈 peg_push） | S3 每格 ≥4 局演示，MoveCube 12 局 |
| 5 | PickXtimes X3 总步数 4496，离 5000 只剩 10% | 上限 18 不再上调；超时局记 shortfall |
| 6 | 评估预算放宽改变 benchmark 语义（M1） | 用户拍板；预算冻进 header 可追溯 |
| 7 | 新目标色可分辨性（M8） | S3 目视核对 256 像素画面 |
| 8 | AST 锁：内环预填搭档会跳过锁定循环的运行时复核分支 | 复核另挂在循环内读预规划处，锁定测试保持通过 |
| 9 | VPO X3 总步数 ≈4360 | M16 |
| 10 | 产物 100～130 GB、生成 3 h、V1 6 h | 本机 `/data` 余量核对后再起 |

## 五、盲区诚实清单

- 全部帧数与成功率来自离线副本/段均值外推，无一格跑过模拟器演示；离线模型比真实 h5 少约 2%。
- 揭示段 36 个物体、7×7 网格、VP 多窗口交换的碰撞安全、扩框后的腕部相机画面均未实测。
- NO RECORD 步数（约 330）是估计值。
- 蒙特卡洛用 numpy 随机数，只做统计，不与 torch 随机流逐位一致。

## 六、留档与 commit 纪律

沿 V5：每步一份 `docs/validation/newtask-v6/<日期>-<步>.md`；commit 只 add 本步文件；探针留 `artifacts/newtask-v6/plan-probes/`（不进 git）；收尾只保留正式 h5/视频与规格。

## 七、规划期证据索引（`artifacts/newtask-v6/plan-probes/`）

| 议题 | 目录 | 报告 | 关键脚本 |
|---|---|---|---|
| A 难度框架与四档总表 | `difficulty-framework/` | report.md | dump_configs.py、h5_frames.py |
| B MoveCube | `movecube/` | report.md | mc_v6.py、sweep_v6.py、budget_tail.py |
| C Unmask 四环境 | `unmask/` | report.md | p2_inner_mc.py、p2d_connected.py、p3_outer_mc.py、p4b_ring_wide.py、p5_inner_count.py |
| D VideoRepick | `videorepick/` | report.md | （见目录） |
| E 计数类四环境 | `count-tasks/` | report.md | mc_lib.py、run_mc.py、binfill_color.py、camera_reach.py、frames_analyze.py |
| F 路径/放置类六环境 | `path-place-tasks/` | report.md | pl_dfs_hit.py、pl_path_study_v6.py、rs_reach.py、vp_layout_mc.py |
