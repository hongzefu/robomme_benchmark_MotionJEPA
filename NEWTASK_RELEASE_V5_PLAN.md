# 新值模式 V5：xhard 档去扎堆、Unmask 外环加密并随内环交换、演示时长校准

> 本方案以用户 2026-09-24 的要求为准，**只规划，不实施**。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，
> 分支 `newtaskRelease-v4`，代码锚点为本文件落盘时的 HEAD `0baff09`（12.96）。commit 编号沿用仓库现行
> `<大版本>.<小版本> <中文描述>` 体例。依赖锚点：`uv.lock` `ff0ffd847a55…` / `pyproject.toml` `d03537d6c77a…`。
>
> **前置文档**：V4 计划 [NEWTASK_RELEASE_V4_PLAN.md](NEWTASK_RELEASE_V4_PLAN.md)（决策 A1～K5 在其 1.3，
> 红线 N1～N12 在其第二部分〇）；V4 总报告 [docs/validation/newtask-v4/20260923-v4-final-report.md](docs/validation/newtask-v4/20260923-v4-final-report.md)；
> V4 正式快照 `scripts/configs/newtask-v4/v4-01/specs.jsonl`（160 候选、48 正式局）与实跑产物
> `artifacts/newtask-v4/v4-01/rollout/run1/`。**V4 决策除本文 1.5 明确推翻或修改的以外全部延续。**
>
> **规划期证据**：本文所有实测数字都来自 2026-09-24 的一次规划期调查（8 个议题并行调查 + 1 个跨议题汇总，
> 汇总方另做了 24 处抽查：22 处证实、1 处存疑、1 处推翻并由此发现新缺陷）。探针脚本、日志与原始调查记录
> 留在 `artifacts/newtask-v5/plan-probes/<议题>/`（本机留档、未进 Git，索引见第二部分七）。**大部分数字来自
> 与 V4 逐位对齐的离线副本**（每个议题都先用 v4-01 冻结规格证明副本逐位一致），模拟器实跑样本很小；
> 按用户 2026-09-24 的决定 V5 不再做副本对齐重证（口径 11、N16），这些数字一律只当规划期估计，不能当验收结论。
>
> **授权边界**：本文是计划，不是实施授权，实施须用户另行批准。`src/robomme/` 的改动沿用 V4 的做法：
> 免逐项事前批准，但每步收尾必须在 `docs/validation/newtask-v5/` 出 md 报告（文件／锚点／改什么／为什么／怎么验）。
> 录像器 `src/robomme/env_record_wrapper/RecordWrapper.py` 全程冻结（V4 的 `fail_safe_limit=5000` 保持）。
> 1.4 的待决项中 L1～L5 已于 2026-09-24 答复，**其余 L6～L51 一个都不许在实施时自行取建议值**，必须先回来问用户。
>
> **简称**：VU = VideoUnmask，BU = ButtonUnmask，VUS = VideoUnmaskSwap，BUS = ButtonUnmaskSwap；
> 「内环」指原有参与揭示/交换的容器（`spawned_bins` / `bin_<i>`），「外环」「干扰容器」指 V4 新增的
> `distractor_bins`；正文里 `utils/…`、`<Env>.py` 等源码路径省略前缀 `src/robomme/robomme_env/`。

# 第一部分（给人看）

## 一、用户决策

**一句话方案**：在 V4 已落地的 `xhard` 档上做第二轮修订，**只动 12 个环境的 xhard 分支**，原三档
（easy/medium/hard）与 4 个未动环境（StopCube、PickHighlight、VideoPlaceButton、VideoPlaceOrder）的 xhard
逐位不变；先修一个新发现的共用缺陷（放下的方块作障碍时 2D 包围框退化成线段、最小间距失效），再逐环境去扎堆、
加密外环、加外环交换、校准演示时长；所有新值重新抽签冻成 `v5-01`，链路（抽签 → 冻结 → 实跑 → 推理）与闸门沿用 V4。
按环境说就是：

| 环境 | 要改什么 |
|---|---|
| VU / BU | 干扰容器从「大外环里 3 个」改成**贴着现生成范围的一圈环带**，数量按内部密度推算（**15 / 14**），一半含 cube |
| VUS / BUS | 干扰容器仍放 V4 大环带，但从 3 个加到 **10 个**（L16 b），一半含 cube；并且**每一次内环交换都配一次外环交换**，搭档同为 XY 最近邻，纳入两对联合的连续碰撞证明 |
| InsertPeg | 四根杆改由**同一个采样器**生成，不给第 4 根单设约束，两两**轮廓**间隔 > 3 cm |
| MoveCube | 方块、目标圆盘、杆都**直接拒绝**落在桌面中心的共同禁区（R = 0.05 m 圆），不再用 bias |
| PatternLock / RouteStick | 不改布局，演示在现布局下**尽可能长**：PatternLock 节点 [24,25]（约 26～27.5 s），RouteStick L 拉长到 25～35 s 带内 |
| BinFill | 修障碍框缺陷，加同色成团上限 |
| PickXtimes / SwingXtimes | 修障碍框缺陷，加 8 cm 间距；PickXtimes 三个有色方块各占一个象限 |
| VideoRepick | 最小中心距 0.12 m 铺开；**全部 6 块都当发起者**，搭档在 reset 时规划 |

### 1.1 定死的口径

**实施中不得更改。** 每条注明依据。

| # | 口径 | 依据 |
|---|---|---|
| 1 | **只改 xhard 档**；easy/medium/hard 在定义、reset 取值、完整演示 h5 上都必须与改动前逐位相同；V1 是硬闸门 | V4 口径 7/12、H2、N4、N12 |
| 2 | **录像器冻结**；`scripts/evaluation.py`、`scripts/run_example.py`、`scripts/dataset_replay.py` 与上游逐字节相同这一性质要保住；`scripts/` 顶层只许五个入口 | V4 N2、口径 8/9；AGENTS.md 规则 11/12 |
| 3 | **改动内容以 1.2 的用户原文为准**；原文里的问句，在 1.3 给出直接回答 | 用户 2026-09-24 原文 |
| 4 | **外环交换只存在于有内环交换的两个环境**（VUS、BUS）。**每一次**内环交换都配**恰好一次**外环交换，**同窗口同时进行**，因此不增加任何控制步 | 原话「每次内部swap 外部也swap」 |
| 5 | **外环交换规则与内环同构**：搭档是同一度量下的最近邻（XY 两轴欧氏距离），轨迹同为 `swap_flat_two_lane`（lane 0.07）；外环容器**永不与内环容器配对** | 原话「外部swap也要这样」 |
| 6 | **外环交换必须进碰撞检测**：reset 时做规划期证明，运行时从实际位姿复核 | 原话「也要支持碰撞检测」 |
| 7 | InsertPeg **四根杆走同一采样逻辑**，**第 4 根不加任何单独约束**，并**保证两两间隔** | 原话 |
| 8 | MoveCube 的**方块、目标（goal 圆盘）、杆三者都不能生成在桌面中心**，**用直接拒绝，不用 bias**；禁区是共同的、以 (0,0) 为圆心的圆，半径由实施方定（2.9 定为 0.05 m） | 原话「不要以bias来设计 而是直接拒绝生成在中心区域」「我的意思是桌面中心 尽可能不要出现三个物体 定你觉得合适拒绝率的比例」 |
| 9 | 演示时长目标 **25～35 s**，按录像器 30 fps 计，即 h5 中 `info/is_video_demo` 为真的帧数在 **750～1050** 之间；**但两环境都不改布局**，PatternLock 在 5×5 上的物理上限约 27.4 s，取「现布局下尽可能长」 | 原话「30s上下浮动5s」「patternlock和routestick不要改布局 尽可能长对齐」 |
| 10 | VideoRepick **全部方块都能参与交换** | 原话「支持所有的cube都要swap」 |
| 11 | **不再跑 V6 组合覆盖**，也不再跑任何「完整跑完的对拍」（V2 两遍重放、V3g 规格反例、V5e 推理链路、副本逐位对齐）。可生成性只由正式那一次生成的结果如实报告；某环境攒不够 10 条候选或 3 条正式局就如实记 shortfall 回报用户 | 用户 2026-09-24「其他完整跑完的对拍都放弃 都不用了」（L5 答复）|
| 12 | **只做一次对拍、一次生成**：①对拍 = 原三档回归 V1，**16 任务 × 3 局与最原始基线逐位一致**；②生成 = **一次多 worker 运行**，每环境抽 10 条 reset 成功候选（尝试上限 30）+ 按 index 0/3/6 实跑 3 条正式局（演示失败在 10 条内递补，H4），落 h5 与视频（J9），**不跑第二遍**。不开 fail recover（I3）保留 | 用户 2026-09-24「我只需要做一次对拍 旧的16*3生成一致 之后就直接1次多worker生成10候选+3实际执行」 |
| 13 | **V4 作废**：不做版本门、不保证 V4 快照在 V5 代码上可回放、不用 v4-01 作对照；V4 已进 Git 的产物原样留着不删，V5 新产物一律落 `newtask-v5` 新目录 | 用户 2026-09-24「废弃v4 我只需要实现新生成的和最原始对拍」（L5 答复） |
| 14 | **待决项不许自填**：1.4 的 L 项必须逐条问用户；实施中新发现的待决项追加进 1.4，同样先问。**例外**：取整、边界取舍这类不改变设计意图的细节由实施方自决并在报告里注明，不上报 | V4 N3；用户 2026-09-24「以后四舍五入这种问题都不要来找我 自己决定」 |

### 1.2 用户原文（逐字保留）

```text
给出v5 plan 固定在根目录
对于unmask任务生成的distractor
改为在现在生成范围环绕一圈 现在的范围太大了 但也要确保在相机范围内 现在的生成数量太少了 改为和内部一样的密度 按照密度推断生成数量 还是有一半无cube
外部的也要支持swap 每次内部swap 外部也swap 现在内部swap的机制是什么 最近2邻？外部swap也要这样 也要支持碰撞检测

insertpeg现在是怎么生成4个的 改为同样的生成逻辑 不要为第四个增加不同的约束 但是要确保两两之间的间隔

movecube改为物体 target peg都不能生成在中心 不要以bias来设计 而是直接拒绝生成在中心区域 定个指标 30%是否可以

/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/v4-01/rollout/run1/episodes/PatternLock_episode_0
/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/v4-01/rollout/run1/episodes/RouteStick_episode_6长度校准为为video demo 30s上下浮动5s

/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/v4-01/rollout/run1/episodes/BinFill_episode_3/videos/BinFill_ep3_seed4400300_xhard_put_four_red_cubes_and_two_green_cubes_into_the_bin_then_press_the_button_to_stop__ALT__put_four_red_cubes_and_two_green_cubes_into_the_bin_and_press_the_button_to_stop.mp4
binfill现在生成cube的位置均匀吗 为什么会有一堆红色在一起的情况

/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/v4-01/rollout/run1/episodes/PickXtimes_episode_3/videos/PickXtimes_ep3_seed4100300_xhard_pick_up_the_green_cube_and_place_it_on_the_target_repeating_this_action_seven_times_then_press_the_button_to_stop__ALT__pick_up_the_green_cube_and_place_it_on_t__HASH__4a1f9140e68c.mp4
pickxtimes也是 为什么会扎堆生成在一起 现在的generator是怎么定位置的？是否有bias
swingxtimes也是

/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v4/v4-01/rollout/run1/episodes/VideoRepick_episode_3/videos/VideoRepick_ep3_seed4900300_xhard_watch_the_video_carefully_then_repeatedly_pick_up_and_put_down_the_same_block_that_was_previously_picked_up_for_five_times_finally_put_it_down_and_press_the_button_to_stop__HASH__ca4dcbd02e55.mp4
videorepick的生成也要均匀 并且支持所有的cube都要swap

启动workflow前用户批准
```

逐环境的字段落点、现值、新值与注入什么，见第二节的环境表；布局改动的俯视图见 2.17。

### 1.3 用户提问的直接回答（结论先行）

| 问题 | 回答 | 详见 |
|---|---|---|
| 现在内部 swap 的机制是什么？最近 2 邻？ | **不是「最近的 2 个邻居」，而是用 x、y 两个轴量出来的最近 1 个邻居。** 发起者：主流上抽两次定下 3 个发起者 a、b、c，第 k 次交换用 `swap_indices[k % 3]` 轮转，4 个内环容器中恰有 1 个永不发起。搭档：每个窗口第一步按**实际位姿**取离发起者 XY 最近的另一个内环容器，严格 `<`、平局取生成序靠前；VUS 从 `swap_selection.partner.position_axes=[0,1]` 读轴，BUS 写死 `[:2]`。代码里唯一「取最近 2 个」的 `_compute_dynamic_swap_candidates`（`distances[:2]`）与 `_select_swap_pair_from_positions` 在 VUS、BUS、VideoRepick 三处都**没有调用者**，是死代码 | 2.5 |
| insertpeg 现在怎么生成 4 个？ | 前 3 根走原生均匀拒绝采样（杆根离孔板 > 0.06、离已放杆根 > 0.075，最多 512 次，接受后再抽 yaw ±180°）；中间抽 obj、dir；**第 4 根由另一个采样器** `_xhard_place_near_target_peg` 在目标杆 peg_0 周围 0.075～0.085 m 圆环带里抽半径与方位角，最后覆盖 `peg_init_poses[3]`。**间距失效**：0.075 m 量的是杆头中心距，而单根杆轮廓长 0.10 m，判据挡不住穿插，V4 xhard 有 28.1% 的布局目标杆与别的杆重叠 | 2.8 |
| movecube 中心区定 30% 是否可以？ | 用户随后改口径为「桌面中心共同禁区、三个物体尽可能都不出现、比例由实施方定」。实施方定为 **(0,0) 为圆心、R = 0.05 m 的圆，按物体中心判**。解析拒绝率：demo goal 16%、exec goal 55%（采样框本来只有半宽 0.06）、方块候选 20%、杆 ≈0（杆身几何上离中心 ≥ 5 cm）；128 次预算下 exec goal 耗尽概率约 1e-33。不按轮廓判，否则 exec goal 无解 | 2.9 |
| PatternLock/RouteStick 长度校准到 30±5 s | **两者现在都偏短**：PatternLock ep0 演示 649 帧（21.6 s）；RouteStick ep6 演示 600 帧（20.0 s）。用户定「不改布局，尽可能长」。RouteStick 每段恰好 50 帧，L 改为 [15,21] 得 25.0～35.0 s（L37 已定）；PatternLock 5×5 上不重访路径最多 25 节点、每段平均 34.25 帧 ⇒ 上限约 27.4 s，取节点 [24,25] 并把搜索预算提到 20000、耗尽抛错，预计 26～27.5 s，**到不了 30 s** | 2.10 / 2.11 |
| binfill 生成 cube 的位置均匀吗？为什么一堆红色在一起？ | **单局内均匀，跨局汇总不均匀；颜色与位置独立。** 单局每块在剩余空闲区域里均匀采样；跨局按钮加孔板平均占去区域 34%，各格密度在 0.65～1.38 之间。**ep3 的红色成堆主要是偶然**：12 块里 7 块红色（≥7 的概率 22%）；按钮和板只留出靠机器人一侧一条空带，红色恰好落在那里；多重比较校正后约 4% 的局至少这么极端。**另有真实缺陷把它压得更紧**：障碍框退化使 red_0 与 red_2 只隔 8.4 mm，名义最小间距 20 mm | 2.12 |
| pickxtimes 为什么扎堆？generator 怎么定位置？有无 bias？ | 顺序拒绝采样：依次放按钮、目标圆盘、3 个有色方块、3 个干扰方块。**有意的 bias**：`corner_push` 以 `corner_bias=0.5` 作用在全部 3 个有色方块上（V4 J5），每个轴单独推向两端，91.3% 的有色方块落在 4 个角格，**44.5% 的局至少 2 块挤在同一角格**（均匀采样下 14.3%）。**无意的问题**：障碍框退化使 15.5% 的局出现中心距 < 6 cm 的方块对；按钮占近机器人一侧，方块被挤向远侧；整个区域在画面里只占 11% | 2.13 |
| swingxtimes 也是？ | **SwingXtimes 没有任何有意 bias。** 扎堆来自偶然、密度，以及同一个障碍框缺陷（7.3% 的局有 < 6 cm 的对）。ep3 的斜排三块相距 12.7 cm 和 9.3 cm，是偶然布局，没有违规 | 2.14 |
| videorepick 生成要均匀，所有 cube 都要 swap | **采样本身是均匀随机的，但均匀随机会扎堆**：26.9% 的局有 ≥3 块落在同一个六分之一区域。**「不是所有 cube 都 swap」来自 B12**：3 个固定发起者加最近邻搭档，V4 只有 17.0% 的局 6 块都动过；ep3 里 bin_4↔bin_3 来回换了 4 次，bin_1 一次没动。改法：中心最小距 0.12 m；6 块全部当发起者，目标每 3 次一轮；reset 时预先规划搭档 | 2.15 |

### 1.4 待决项（实施前逐条答复，不许自填）

「建议」一列是调查方给的推荐，**不是批准值**。编号按环境分组，与第二节各表里引用的 L 号一致。

**跨环境（先答这 5 项，其余依赖它们）**

| 编号 | 问题 | 选项 | 建议 | 结论（用户答复） |
|---|---|---|---|---|
| L1 | V4 红线 N5（新随机调用只许追加在既有取值点之后）在 V5 怎么读？ | (a) N5 只保护**原三档与已冻结产物**；xhard 流允许**原地**移位（拒绝循环、换序、次数变化），所有被改动环境重冻为 `v5-01`。V4 先例：MoveCube 的 corner_bias 就曾平移 cube 循环次数与 way_idx。<br>(b) 严格字面：只许追加。这会挡掉 InsertPeg、MoveCube、Pick/Swing/BinFill/VideoRepick 的间距规则 | (a) | **(a)**（2026-09-24「L1 a」）：N5 只保护原三档，xhard 流允许原地移位 |
| L2 | 障碍框退化缺陷修到哪？ | (a) 只修 V5 动到的 xhard 环境：BinFill、PickXtimes、SwingXtimes；MoveCube 用 L34 顺带；VideoRepick 被 0.12 m 最小距覆盖。<br>(b) 连 PickHighlight、VideoPlaceButton/Order 的 xhard 一起修，这些环境也要重冻。<br>(c) 全局修，会破坏 V1，H2/N12 禁止 | (a)，(b) 留作后续 | **(b)**（2026-09-24「L2 b」）：PickHighlight、VideoPlaceButton、VideoPlaceOrder 的 xhard 一并修，随其他环境一起重抽；见 2.16 |
| L3 | K2 的 `SceneGenerationError` 遮蔽修复是否扩到 VideoRepick、SwingXtimes、PatternLock、VUS、BUS 的 xhard？ | 是 / 否 | 是：否则 V5 新增的 xhard 拒绝会变成 TypeError，被当成代码错误 | **是，且扩到所有存在遮蔽的环境的 xhard**（2026-09-24「对xhard都修」）：VideoRepick、SwingXtimes、PatternLock、RouteStick、StopCube、VUS、BUS 七个都修，原三档仍不动 |
| L4 | 共用采样函数 `spawn_random_cube` / `spawn_random_target` 上的新规则怎么挂？ | (a) **只加一个**可选参数 `extra_reject=None`（可调用对象，不抽随机数，默认整段跳过）。<br>(b) 每个环境各加各的参数 | (a) | **(b)**（2026-09-24「L4 b」）：不加共用 `extra_reject` 钩子，各环境各加各的显式参数；共用函数的暴露面靠 V1 与单测守住 |
| L5 | 快照、run id 与 V4 产物怎么处理？ | (a) 新目录 `scripts/configs/newtask-v5/`、run id `v5-01`，16 个环境全部重抽；未改动的 4 个环境必须逐位复现 v4-01；V4 推理钉在 `0baff09`（建议打 tag）。<br>(b) 加版本门，让 V4 快照在 V5 代码上仍可回放 | (a) | **废弃 V4**（2026-09-24「废弃v4 我只需要实现新生成的和最原始对拍」）：不做版本门、不用 v4-01 对照、不打 tag；新目录 `newtask-v5`、run id `v5-01`；对拍只剩 V1，见口径 12/13 与第三节 |

**四个 Unmask 环境的干扰容器（2.2～2.4）**（2026-09-24 用户答复原话「l6a l7a l8 a l9a l10a / l11 a l12a l12 a l14a l15是」；L13 未单独点名，按第二个「l12 a」理解为 L13 (a)）

| 编号 | 问题 | 选项 | 建议 | 结论（用户答复） |
|---|---|---|---|---|
| L6 | 「环绕一圈」的带宽 W | (a) W = 1/√ρ = 0.1414 m，即内部密度下一个平均间距格 → 15/14/15/16 个。<br>(b) 只放一排，W = 0.085 → 9/8/9/9 个。<br>(c) 其他 | (a) | **(a)** W = 0.1414 |
| L7 | 环带与现生成范围之间留多宽 | (a) g = 0.015（xhard 的 min_gap）。<br>(b) g = 0.04（沿用 B13 的内界，每环境多 1 个）。<br>(c) g = 0 | VU/BU 选 (a)；Swap 两环境与 L16 一起定 | **(a)** g = 0.015（VU/BU；Swap 两环境随 L16） |
| L8 | Swap 两环境的「现在生成范围」与密度怎么取 | (a) 静态包络（VUS 为半宽 0.2114 的方形；BUS 为锚点框并集的外接矩形），按每局密度 ≈51/m² → 15/16 个。<br>(b) 按静态包络密度（24.8 / 37.9）→ 约 8/12 个。<br>(c) 每局动态环带 | (a) | **(a)** 静态包络、每局密度 51/m² |
| L9 | BUS 的按钮算不算内部范围 | (a) 算：内部矩形 x 从 -0.2625 起 → 16 个。<br>(b) 不算 → 10 个，且环带穿过按钮（21.5% 被挡） | (a) | **(a)** 按钮算内部 → 16 |
| L10 | 数量怎么取整 | (a) 在 1 mm 网格上 floor(ρA+0.5) → 15/14/15/16，冻成整数，并用测试锁定推导。<br>(b) floor → 15/14/15/15 | (a) | **(a)** floor(ρA+0.5) → 15/14/15/16，冻成整数；用户另示：取整一类细节以后由实施方自决，不再上报 |
| L11 | N 为奇数时几个含 cube | (a) 在 [floor(N/2), ceil(N/2)] 内随机，与 V4「3 个里 1～2 个」同义。<br>(b) 取 floor。<br>(c) 取 ceil | (a) | **(a)** [floor(N/2), ceil(N/2)] 随机 |
| L12 | 含 cube 的超过 3 个时颜色怎么定 | (a) 仍用 B2 的三色，平衡轮转。<br>(b) 有放回独立抽。<br>(c) Unmask 专用新色板（推翻 B2/A5） | (a) | **(a)** 三色平衡轮转 |
| L13 | 两套干扰采样器是否统一成一套 | (a) 统一实现与统一 schema，各环境仍用各自的随机流。<br>(b) 最小改动 | (a) | **(a)** 统一成一套（按用户第二个「l12 a」理解，待用户如有异议再改） |
| L14 | 揭示/交换期间的停放点 | (a) 给每个干扰容器与每个被藏 cube 各配独立的画面外停放点（xhard 专用 helper，不改 `statechange.py`）。<br>(b) 维持全部停在 (10,10,10) | (a) | **(a)** 独立停放 helper |
| L15 | BUS 内环 `except RuntimeError: break` 静默截断，在 xhard 是否改为报错 | 是 / 否 | 是 | **是**，xhard 抛 SceneGenerationError |

**两个 Swap 环境的外环交换（2.5～2.7）**（2026-09-24 用户答复原话「l16b l17b l18a l19b l20是 l21 0.07 l22 a l23是」）

| 编号 | 问题 | 选项 | 建议 | 结论（用户答复） |
|---|---|---|---|---|
| L16 | 有外环交换后，Swap 两环境的干扰数量与环带（与 L6～L10 联动） | (a) 采用 2.2 的贴身环带与 15/16 个，前提是实现后 `V5_SWAP_JOINT_FEASIBILITY` 首次可行率 ≥ 0.95。<br>(b) V4 环带放 10 个（实测 100%，但密度不到内部）。<br>(c) 贴身环带取 g=0.04，或外环 lane 0.05（(a) 不过时的杠杆） | (a)，不过闸就回报用户，改走 (c) | **(b)** Swap 两环境沿用 V4 环带 `[0.2675, 0.45]`，放 **10 个**（含 cube [5,5]）；2.2 里 VUS/BUS 的 15/16 作废，L7～L9 对 Swap 两环境不再适用 |
| L17 | 外环发起者怎么定 | (a) randperm(count)[:3]，按 k%3 轮转。<br>(b) randperm(count) 全体轮转。<br>(c) 每窗重新 randint | (b)：count=3 时与 (a) 等价 | **(b)** randperm(count) 全体轮转 |
| L18 | 某窗第一候选外环交换不可行时怎么办 | (a) 按排列确定性换下一个发起者，全不行才整段重抽干扰布局。<br>(b) 只整段重抽。<br>(c) 跳过该窗的外环交换 | (a)：(c) 违背口径 4 | **(a)** 按排列换下一个发起者，全不行才整段重抽 |
| L19 | 「外环车道不进内部」的含义 | (a) 只要无碰撞。<br>(b) 无碰撞，且离每个内环容器圆距 ≥ 0.04 m，BUS 还要离按钮中心 ≥ 0.122 m。<br>(c) 中心路径不越过环带内界 | (b)：(c) 在 ±0.07 的车道下几乎无解 | **(b)** 无碰撞 + 离内环容器圆距 ≥ 0.04 + BUS 离按钮中心 ≥ 0.122 |
| L20 | reset 时是否也拒绝**内环对内环**的扫掠碰撞 | 是 / 否 | 是：V4 观测到的 8 次 BinCollisionError 全属此类，8/8 可在 reset 时预判 | **是** |
| L21 | 外环 lane offset | 0.07（同内环） / 0.05 | 0.07 | **0.07** |
| L22 | xhard 内环搭档在哪定 | (a) 维持 V4：运行时解析，加联合复核与不一致日志。<br>(b) 钉死为 reset 时的规划 | (a) | **(a)** 内环维持运行时解析 |
| L23 | 是否加认证预筛（只跳过已证明分离的对，判定不变） | 是 / 否 | 是：单窗检查 0.4～1.8 s 降到 3～55 ms | **是** |

**InsertPeg（2.8）**（2026-09-24 用户答复原话「l24 0.03 l25 精确轮廓距离 + 保留原生规则 l26 0.01 l27a l28确认放弃 l29是」）

| 编号 | 问题 | 选项 | 建议 | 结论（用户答复） |
|---|---|---|---|---|
| L24 | 两两间隔阈值 g（`peg_min_pair_gap_m`） | 0.02 / 0.03 / 0.045 / 0.055 m | 0.03：能保证张开的夹爪闭合区里没有别的杆的最小值 | **0.03** |
| L25 | 间隔的度量，是否保留原生杆根 > 0.075 规则 | 精确轮廓（有向矩形）距离＋保留原生 / 胶囊体＋保留原生 / 只用中心距 | 精确轮廓，保留原生规则 | **精确轮廓距离 + 保留原生规则** |
| L26 | 杆与孔板之间是否也加轮廓间隔（`peg_box_min_gap_m`） | 否 / 是，取 0 / 是，取 0.01 m | 是，0.01 m。超出「两两之间」的字面，单独问：孔板重叠会把杆弹飞 8 m | **是，0.01 m** |
| L27 | xhard 流里的抽样顺序与 yaw 策略 | (a) 4 根一个循环、放在 obj/dir 之前，yaw 在通过原生判据后才抽（lazy）。<br>(b) 0～2 原位，obj/dir 之后再用同一函数抽第 4 根 | (a)（依赖 L1） | **(a)** |
| L28 | 确认放弃 V4「新杆贴近目标杆」的意图，删除 `decision.xhard.near_target_distractor` | 确认 / 以其他形式保留贴近压力 | 确认：目标杆到最近干扰杆的中位距离将由 0.080 m 升到 0.178 m | **确认放弃**，删 `near_target_distractor` |
| L29 | 回放冻结规格时是否复核间隔 | 是 / 否 | 是 | **是** |

**MoveCube（2.9）**（2026-09-24 用户答复原话「l30 3  我的意思是桌面中心 尽可能不要出现三个物体 定你觉得合适拒绝率的比例 可以不是30%的面积」）

| 编号 | 问题 | 选项 | 建议 | 结论（用户答复） |
|---|---|---|---|---|
| L30 | 「30%」指什么 | (1) 各物体自身采样框**面积**的 30%，取中心正方形。<br>(2) 边长的 30%（面积 9%）。<br>(3) 面积 30% 的圆。<br>(4) 十字形，只留四角。<br>(5) 共同的绝对中心 | (1) | **用户改口径：桌面中心一个共同禁区，三个物体都不许出现；比例由实施方定。** 实施方定为：以 (0,0) 为圆心、**R = 0.05 m 的圆**，按物体中心判（杆按轴线最近点）；见 2.9 |
| L31 | 「杆不在中心」的含义 | (A) 杆根不在**自身抖动框**中心（2.74 cm）。<br>(B) 另加：杆身不得进入工作区中心，约多 8.5% 重抽。<br>(C) 不另加（杆根本来就在 \|y\|≥0.15） | (A)；若用户指杆身再加 (B) | 随 L30 定死：杆按轴线离圆心最近点判；杆根 \|y\|≥0.15、杆长 0.10，杆身几何上进不了 5 cm 圆，实际几乎不拒 |
| L32 | 方块中心区以哪个框为基准 | 候选框（w=0.0548，候选与最终位置都查） / 最终支撑框（w=0.0712） | 候选框，两处都查 | 随 L30 定死：方块候选中心与最终中心两处都按同一个圆判 |
| L33 | MoveCube xhard 的 `corner_bias` 键怎么处理 | 保留、取 0.0 并标注废弃 / 删键 | 保留取 0.0 | **删键，删干净**（2026-09-24「l33删除干净」）：`config_xhard.corner_bias` 与 `_xhard_corner_bias`、`corner_push` 在 MoveCube 的调用、相关单测一并删除；`utils/xhard.py::corner_push` 本身保留（PickXtimes 仍用） |
| L34 | xhard 下执行段方块是否不再避让演示段方块（`include_existing=False`） | 是 / 否 | 是：两块从不同时在场；仿真已复现 seed 1000442/1000446 因此 reset 失败 | **是**（2026-09-24「l34 是」） |

**PatternLock / RouteStick（2.10 / 2.11）**（2026-09-24 用户答复原话「l35 patternlock和routestick不要改布局 尽可能长对齐」）

| 编号 | 问题 | 选项 | 建议 | 结论（用户答复） |
|---|---|---|---|---|
| L35 | PatternLock 用哪个杠杆达到 25～35 s | A) 6×6、间距 0.08（占地同 V4），节点 [30,33]。<br>B) 5×6、间距 0.1，节点 [25,28]。<br>C) 保留 5×5 [20,24]，只把演示放慢 ×1.3，或每段停 11 帧（唯一保住 B8/K1 与 V4 规格的方案）。<br>D) 5×5 允许重访节点 | A | **两者都不改布局，在现布局下尽可能长**。A/B/D 作废。实施方定：PatternLock 5×5@0.1 不动，节点 **[24,25]**（5×5 简单路径的物理上限），xhard 搜索预算 1000 → **20000**（25 节点命中率约 99.9%），预计演示 26～27.5 s |
| L36 | 选 A 时的节点范围，以及搜索耗尽是否显式报错 | [30,33] / [30,32] / [31,33]；耗尽时 xhard 抛错：是 / 否 | [30,33] 并抛错（依赖 L3） | 随 L35 定：节点 [24,25]；搜索耗尽**抛错**（依赖 L3，已定） |
| L37 | RouteStick 的 L 范围 | [15,21]（25.0～35.0 s） / [16,20]（26.7～33.3 s） | [15,21] | **[15,21]**（2026-09-24「L 取 [15, 21] 的话是 25～35 s 均值 30 用这个」「不用对齐patternlock」） |
| L38 | RouteStick 的 L 范围是否冻进 decision 与规格 header（现在从类属性读、未冻结） | 是 / 否 | 是 | **是** |
| L39 | 「30 s」怎么量 | h5 中 `is_video_demo` 帧数 ÷ 30（A2） / 物理仿真时间 | A2 | **A2** |

**BinFill（2.12）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L40 | 「均匀」指什么 | (a) 空闲区内均匀：已成立，无需改。<br>(b) 颜色充分混合，没有大块同色团。<br>(c) 蓝噪声式铺开。<br>(d) 整个矩形密度拉平（需挪按钮/板） | (b) 加 L2 的缺陷修复 |
| L41 | 同色成团上限参数 | T = 3 / 2；连通距离 0.08 / 0.09 / 0.10；最多重排 64 次，失败时取最优 | T=3、0.09、64 |
| L42 | 是否限制每色生成块数（避免 7+ 同色） | 不限 / 上限 max(target, 6) | 不限：它会改配额规则并平移整条流 |

**PickXtimes / SwingXtimes（2.13 / 2.14）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L43 | PickXtimes 边角语义（含 MoveCube 方提出的「是否也改为拒绝而非 bias」） | (a) 保留 J5（3 块都 corner_bias 0.5），另加「3 个有色方块各占不同象限」。<br>(b) 只推目标（推翻 J5）。<br>(c) 取消边角（推翻 V4 1.2 原文与 J5）。<br>(d) 只加间距 | (a) |
| L44 | 6 块之间的最小中心距（xhard） | 0.06 / 0.08 / 0.10 | 两环境都取 0.08 |
| L45 | PickXtimes xhard 放置 max_trials | 256 / 1024 | 1024 |
| L46 | 是否把 PickXtimes xhard 的方块区域扩到半宽 0.25 | 是 / 否 / 先做演示探针再定 | 先探针再定 |

**VideoRepick（2.15）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L47 | 「所有 cube 都 swap」指什么 | (a) 每块都当发起者：目标每 3 次一轮，其余 5 块按 randperm 顺序轮转。<br>(a') 纯 k%6 轮转。<br>(b) 只要求覆盖。<br>(c) 每次随机一对 | (a) |
| L48 | 搭档规则 | 最近邻 / 在 2 个最近且扫掠可行的候选中均匀选、不立即重复上一对 / 3 个最近或任一可行 | 2 个最近可行、不立即重复 |
| L49 | 搭档在哪决定 | reset 时规划，留 5 mm 余量 / 运行时按实际状态 | reset 规划 |
| L50 | 摆放的最小中心距 | 0.10 / 0.12 / 0.13 / 0.14 m | 0.12 |
| L51 | 是否改区域或按钮，让方块铺满更多画面 | 不改 / 向 +x 扩 / 移动或缩小按钮禁区 | 不改 |

### 1.5 本计划推翻或修改的 V4 决策

| V4 编号 | V4 内容 | V5 改为 | 触发 |
|---|---|---|---|
| B13 | 干扰容器放外环 `max(\|x\|,\|y\|) ∈ [0.2675,0.45]`，3 个里 1～2 个含 cube | VU/BU：紧贴生成范围、一个密度格宽的环带，数量按密度推算为 15/14；VUS/BUS：环带不变、数量 3 → 10（L16 b）；含 cube 数取 [floor(N/2), ceil(N/2)]；四环境统一用精确 8 角点可见性 | 2.2 |
| B3 | 干扰做成额外容器，**不参与 swap**，隐含 3 个 | 数量按密度定；Swap 两环境里干扰容器之间互相交换，但仍永不与内环配对、不进 `spawned_bins` | 2.2 / 2.5 |
| J1（「仍不参与 swap」一句） | 揭示＋误抓即失败＋不交换 | 揭示与误抓保留；Swap 两环境改为交换；可选的独立停放点（L14） | 2.5 |
| H1 | 干扰容器只作静止旁观者进碰撞检查 | 干扰容器成为外环交换中的移动者；碰撞改为两对联合的连续证明（`check_multi_swap_sweep`），reset 规划与运行时复核都做；内环对内环也改在 reset 预判拒绝（L20） | 2.5 |
| 实现细节（未编号） | 颜色无放回，因此最多 3 个 cube；Swap 两环境用圆间距 0.04、线性可见性近似、512 次；cube 命名 `distractor_cube_<colour>` | 三色平衡轮转；统一 OBB 间距；精确可见性；1024 次；cube 名带序号 | 2.2 |
| B6 / I2 / K3 | 杆间距判据不动；第 4 根贴近 0.075～0.085；开局重叠 31.6% 维持现状 | 四根一个采样器；精确轮廓间隔 > 0.03；重叠降为 0；删除贴近目标的圆环带 | 2.8 |
| B7 / G3 | MoveCube 用 `corner_bias ∈ [0,1]`，定为 0.5 | 删掉 `corner_bias`；桌面中心 R=0.05 圆形共同禁区直接拒绝 | 2.9 |
| V4 2.17 表「goal 区域不动」（部分） | goal 不受偏置 | 区域尺寸不变，但 goal 中心也不得进桌面中心圆 | 2.9 |
| A2（范围） | 20～30 s（600～900 帧） | 25～35 s（750～1050 帧）；30 fps 与 `is_video_demo` 的计法不变 | 2.10 / 2.11 |
| K1 | PatternLock 节点 [20,24]（25 在 1000 次预算内搜不到） | 节点 [24,25]，搜索预算 20000、耗尽即抛错；B8「不改布局」保留 | 2.10 |
| B9 | RouteStick 的 L 为 [12,15] | [15,21] | 2.11 |
| V4 计划 2.20 与风险 #6（陈述错误） | 「执行段 = L×50+200，L>≈22 必被截断」 | 更正：强制复位是演示态 NO RECORD，不计预算；执行段为 50·L（+1 初始帧）；截断点是 L≥27 | 2.11 |
| V4 计划 2.19（陈述错误） | 「每段约 31 帧、上限约 24.8 s」 | 更正：实测平均每段 34.25 帧，随方向变化；24 段平均约 27.4 s，这也是不改布局时的上限 | 2.10 |
| B1（修改执行） | BinFill 区域与间距不动 | 数值不动，但名义 2 cm 间距在 xhard 真正生效；加同色成团上限 | 2.12 |
| J5（修改） | PickXtimes 3 个有色方块都 corner_bias 0.5 | 保留 0.5，另加「不同象限」、8 cm 间距、精确 OBB、1024 次 | 2.13 |
| B12 / J2 | VideoRepick 发起者仍 3 个；接受约 45% 的 D5 演示期拒绝、靠 H4 递补 | 6 块全当发起者；最小距 0.12 m 加 reset 规划可行搭档；D5 保留作运行时守卫，H4 保留作兜底 | 2.15 |
| K2（扩展） | 只在 VideoPlaceOrder 的 xhard 修异常遮蔽 | 同样修到 5 个环境的 xhard | 2.0 |

## 二、逐环境改动

**怎么读这一节**：2.0 是跨环境的公共改动（只写一次，各环境表里不重复）；2.1 是十六个环境的改动范围总表；
2.2 与 2.5 是两个族的共用事项（四个 Unmask 的环带、两个 Swap 的外环交换），不对应单个环境；其余是**十二张环境表**，
每张四列（字段 / 含义 / V4 xhard 现值 / V5 新值与注入什么），**只列要改的字段，不改的一律不列**，表后跟该环境的「实施要点」。
2.16 是三个只修缺陷的环境，2.17 是改动后的布局简图。各环境「验收」行里的判定项按口径 11/12 **只作为轻量单测或单次 reset 检查**实现，
不再作为独立的对拍运行。

### 2.0 全局要改什么

下面是**跨环境的公共改动**，按「改完才能往下走」的依赖顺序排。最后一列是这处改动在不启用新值时必须表现成什么样——
代码改了，但原三档跑出来的东西不许变，这正是 V0／V1 要验的内容。

| 文件::锚点 | 改什么 | 为什么 | 不启用新值时必须 |
|---|---|---|---|
| `utils/xhard.py`（新增 `cube_obb2d_exact(pose, half)`） | 纯函数，按方块真实 yaw 给出 2D 障碍三元组 `(c, A, h)`，不抽随机数；xhard 分支把放下的方块以**预制三元组**放进 `avoid`，不再放 actor 本身 | ① 新发现的共用缺陷（见下） | 不被调用；`_trimesh_box_to_obb2d` / `_safe_unit` **不改** |
| `utils/object_generation.py::spawn_random_cube` / `spawn_random_target` | **按 L4 (b)**：各环境各加各的显式可选参数（如 `center_zone_half=None`、`min_center_dist=None`、`quadrant_of=None`），都在既有 OBB/圆判据之后、`recorder.value` 之前求值，自身不抽随机数 | ② MoveCube 中心区、Pick/Swing 8 cm、PickXtimes 象限、VideoRepick 0.12 m 都要在这两个被 12 个环境共用的拒绝循环里加判据 | 每个新参数默认 `None` 时整段跳过，沿用 V4 `corner_bias` 默认 0 即原样返回的先例；每个参数各配一条「默认值下逐位不变」单测 |
| VideoRepick、SwingXtimes、PatternLock、RouteStick、StopCube、VUS、BUS 七个模块头部 | 仿 `VideoPlaceOrder.py` 加 `_RealSceneGenerationError` 别名，raise 与 except 两处按 `difficulty == "xhard"` 选类 | ③ `SceneGenerationError` 被 `from .utils import *` 遮蔽成子模块（见下，L3：所有存在遮蔽的环境的 xhard 都修） | 原三档仍是 TypeError（H2） |
| `utils/bin_collision.py`（新增 `check_multi_swap_sweep` 与认证预筛） | 复用 `_prove_pair` 证两对同时移动；预筛只跳过已证明分离的对 | 2.5 的外环交换与 VideoRepick 的 reset 规划都要用 | `check_swap_sweep` 判定不变；单对时新函数与旧函数逐位相同（`MULTI_SWEEP_EQUIV`） |
| `scripts/configs/newtask-v5/`（新目录） | 全部改完后**只重导一次** `sampling_config.json`；run id `v5-01`；不再生成 `combos.json`（口径 11） | ④ 每个环境都会增删 `decision.xhard` 键，`assert_native_decision` 的形状检查会拒绝 V4 快照；RouteStick 的 L 范围 V4 header 没冻结，V4 规格在 V5 代码上会直接 `ValueError`（L5、L38）。**V4 作废**，不做兼容 | V4 配置目录原样留着不引用 |

**① 新发现的共用缺陷：放下的方块作障碍时 2D 包围框退化。** `spawn_random_cube` / `spawn_random_target` 把 `avoid`
里的 actor 转成 2D 障碍框，路径是 mani_skill 的 `get_actor_obb`（trimesh `bounding_box_oriented`）→
`utils/object_generation.py::_trimesh_box_to_obb2d`，后者取旋转矩阵前两列的 xy 分量当作 2D 轴。两层问题：对正方体
trimesh 返回的三个轴**顺序是任意的**；竖直轴落在第 0 或第 1 列时该列投影 ≈ 0，而 `_safe_unit` 会把近零向量**原样返回**。
结果这块方块的 2D 障碍**退化成一条 4 cm 线段**，`min_gap` 在其法向上失效。

| 口径 | 退化率 | 后果 |
|---|---|---|
| BinFill xhard 离线副本（与 v4-01 逐位一致），36000 块 | 66.45% | 23.3% 的方块离最近邻不到 2 cm（名义下限 20 mm）；ep3 的 red_0 与 red_2 只隔 8.4 mm |
| PickXtimes 离线副本，4000 次随机 yaw | 66.1% | 15.5% 的局有中心距 < 6 cm 的方块对，最近 4.1 cm，已贴面 |
| SwingXtimes 离线副本 | 同上 | 7.3% 的局有 < 6 cm 的对 |
| 汇总方用 float64 trimesh 复算 | 49.8% | 退化率随数值路径变化，但缺陷真实存在 |
| 真实模拟器（BinFill seed 4400100） | 11 块中 5 块退化 | 副本与模拟器 11/11 对上 |

V4 的 G2 报告（[20260922-step0-g2-capacity.md](docs/validation/newtask-v4/20260922-step0-g2-capacity.md) 第 3 条）已在
VideoRepick 上发现过这个现象，当时未修。按 L2 (b)，**所有用到方块障碍的 xhard 环境都修**（含 PickHighlight、VideoPlaceButton、VideoPlaceOrder，见 2.16）；原三档不修（H2）。

**③ `SceneGenerationError` 被遮蔽。** 7 个环境模块先 `from .utils.SceneGenerationError import SceneGenerationError`，
随后 `from .utils import *` 把这个名字覆盖成**子模块**（汇总方用 import 自省核实：VideoRepick、SwingXtimes、PatternLock、
RouteStick、StopCube、VUS、BUS；VideoPlaceOrder 已按 K2 修过）。后果：`raise` 与 `except` 都抛 TypeError，生成器把它归为
不可重试的代码错误；V4 抽签循环捕获所有 Exception 所以仍会重抽，但**失败分类是错的**（反例：SwingXtimes 圆盘放不下时实际走的
是 TypeError）。V5 新增的 xhard 拒绝几乎都会走到这个名字（VideoRepick 搭档规划失败约 8.4%、SwingXtimes 圆盘失败约 3.6%、
PatternLock 搜索耗尽改为抛错、Unmask 内环预判拒绝），所以必须先修。RouteStick、StopCube 在 V5 没有新增抛错点，但按 L3 一并修掉遮蔽。
闸门 `V5_SCENEGEN_CLASS=PASS envs=5 raised=SceneGenerationError typeerror=0`。

**④ N5 怎么读。** 几乎每个环境的推荐设计都会让 xhard 流**原地**移位（InsertPeg 的 lazy yaw 与 peg_3 提前；MoveCube 原位拒绝
重抽；Pick/Swing/BinFill/VideoRepick 的间距规则改变 trial 次数），没法只在末尾追加。原三档不受影响，由 V0、V1、`RESET_REGRESSION`
守住；按 L1 (a) 读 N5，这些环境重冻为 `v5-01` 即可。例外：VU/BU 的新抽样本来就在所有既有取值点之后，Swap 两环境走独立流，
所以这 4 个环境在 xhard 下内环取值与 V4 同 seed 完全相同（V4 已作废，这一点只作理解，不再单独验证）。

### 2.1 改动范围总表

| 环境 | V5 动不动 | 要改什么（一句话） | 详见 |
|---|---|---|---|
| VideoUnmask | 改 | 干扰容器 3 → **15**，贴身环带 `[0.2425, 0.3289]`，含 cube [7,8]，三色平衡轮转，1024 次 | 2.3 |
| ButtonUnmask | 改 | 同上，**14** 个，含 cube [7,7]（按钮挡住环带 5.7%） | 2.4 |
| VideoUnmaskSwap | 改 | 干扰 3 → **10**（环带沿用 V4，L16 b）；**外环随内环同步交换**；两对联合碰撞证明；内环对内环 reset 预判 | 2.6 |
| ButtonUnmaskSwap | 改 | 干扰 3 → **10**（环带沿用 V4，L16 b）；外环交换加按钮中心距约束；内环静默截断改报错 | 2.7 |
| InsertPeg | 改 | 删第 4 根的专用采样器与贴近带；四根一个循环；轮廓间隔 > 0.03、离孔板 > 0.01 | 2.8 |
| MoveCube | 改 | 删掉 `corner_bias`；杆/goal/方块都不得落进桌面中心 R=0.05 圆；执行段方块不避让演示段方块 | 2.9 |
| PatternLock | 改 | 布局不动；节点 [20,24] → **[24,25]**；搜索预算 1000 → 20000；搜索耗尽即抛错 | 2.10 |
| RouteStick | 改 | L [12,15] → **[15,21]**；L 范围冻进 decision | 2.11 |
| BinFill | 改 | 障碍框用精确 OBB；同色成团上限（T=3、0.09 m、最多重排 64 次） | 2.12 |
| PickXtimes | 改 | 3 个有色方块各占不同象限；6 块两两 ≥ 8 cm；精确 OBB；1024 次 | 2.13 |
| SwingXtimes | 改 | 共用循环加显式 xhard 分支；8 cm 间距；精确 OBB | 2.14 |
| VideoRepick | 改 | 最小中心距 0.12 m；6 块全部发起；搭档 reset 规划 | 2.15 |
| PickHighlight / VideoPlaceButton / VideoPlaceOrder | 改（只修缺陷） | xhard 分支的方块障碍改用精确 OBB（L2 b）；异常类不涉及 | 2.16 |
| StopCube | 改（只修异常类） | 不用 `spawn_random_cube`，无扎堆问题；只按 L3 修 `SceneGenerationError` 遮蔽 | 2.0③ |

### 2.2 四个 Unmask 环境的共用事项（干扰容器环带）

**现状**：两套实现，四环境共用同一组参数（3 个，外环 `[0.2675, 0.45]`，1～2 个含 cube）。

| 项 | VU / BU | VUS / BUS |
|---|---|---|
| 入口 | `utils/unmask_distractors.py::spawn_ring_distractor_bins`（`XHARD_DISTRACTOR` 在各环境文件） | `utils/unmask_swap_xhard.py::sample_distractors` / `build_distractors`，经 `_spawn_xhard_distractors` 调用 |
| 随机流 | 主场景 generator，排在所有既有取值点之后 | 独立流 `distractor_generator(seed)` = seed + `DISTRACTOR_STREAM_SALT`（0x5D157AC7） |
| 可见性 | 精确：8 个角点都投进 256×256 画面（`visible_in_camera`） | **线性近似** `visible_on_camera`，比精确判据宽：20000 个随机点里 2358 个只被近似判为可见；V4 冻结的 60 个 Swap 干扰容器里 4 个实际被裁出画面 3.8～8.8 px |
| 间距 | OBB 避让，`min_gap_factor` 0.75（0.015），256 次 | 圆间距 `min_gap` 0.04（中心距 0.1178），512 次，另对预测的内环扫掠做精确拒绝（H1） |
| cube 颜色 | 三色**无放回**（`high > len(DISTRACTOR_COLORS)` 即 ValueError） | 三色切片到 3 个，超过就**静默截断**；cube 名 `distractor_cube_<colour>`，**颜色一重复就重名崩溃**（原型 2/2 复现 AssertionError） |

**密度对比**：内部 VU/BU 8 个容器 / 0.4×0.4 = 50 个/m²（G2），Swap 两环境 4 个容器 / 每个锚点框 0.14×0.14 = 51 个/m²；
V4 外环 3 个 / 0.486 m² 可见占位 = **6.2 个/m²**，按内部密度应放 **24 个**。用户说的「范围太大、数量太少」都成立。

**「现在生成范围」逐环境**（代码推导，并用 10 条冻结规格核对）：

| 环境 | 内部范围 | 备注 |
|---|---|---|
| VU | region `[-0.2,0.2]²`，中心 ±0.1725 | — |
| BU | 同上；按钮 OBB 伸到 x = -0.306 | 按钮挡住环带 5.7% |
| VUS | 4 个锚点框随角度 U[0,180) 整体旋转；旋转包络的 Chebyshev 半宽 **0.2114** | 单局实际只占 0.08～0.10 m² |
| BUS | 不旋转；中心 x∈[-0.0425,0.1425]、y∈[-0.1425,0.2425]；把两个按钮算进来，x 从 **-0.2625** 起 | 偏向 +y |

**环带公式（L6～L13）**：取中心带作为环带

```text
r_in  = R_inner + g + 0.0275
r_out = R_inner + g + W − 0.0275
其中 g = 0.015（xhard min_gap），W = 1/√ρ = 0.1414（内部密度下一个平均间距格），0.0275 是容器采样半宽

VU/BU：ring_max_abs_xy = [0.2425, 0.3289]
VUS  ：max-norm 带 [0.2539, 0.3403]（内部为半宽 0.2114 的方形）
BUS  ：内部矩形 [-0.2625, 0.17]×[-0.17, 0.27] 之外的 Chebyshev 带 [0.0425, 0.1289]

数量 N = floor(ρ·A_usable + 0.5)，ρ = 50/m²
A_usable = 在 1 mm 网格上，「环带 ∩ 精确可见的中心」的占位面积 × (1 − 固定物体平均遮挡)
含 cube 数 ∈ [floor(N/2), ceil(N/2)] 随机
颜色：order = randperm(3)（VU/BU 本来就抽这一次），第 j 个 cube 用 DISTRACTOR_COLORS[order[j % 3]]
cube_bins = randperm(N)[:n]；cube 名 distractor_cube_<j>_<colour>
```

| 环境 | A_usable（m²） | ρ·A | N | 含 cube |
|---|---|---|---|---|
| VU | 0.3027 | 15.14 | **15** | [7,8] |
| BU | 0.2853（按钮挡 5.7%） | 14.27 | **14** | [7,7] |
| VUS | 0.3081 | 15.40 | ~~15~~ → **按 L16 (b) 改为 10**，环带沿用 V4 `[0.2675, 0.45]` | [5,5] |
| BUS | 0.3115 | 15.58 | ~~16~~ → **按 L16 (b) 改为 10**，环带沿用 V4 | [5,5] |

> **L16 (b) 之后 Swap 两环境不用贴身环带**：上表 VUS/BUS 的贴身推导只留作记录；实际取 V4 环带放 10 个（联合可行性试算 100% / 100%，见 2.5）。VU/BU 的 15/14 不变。统一采样器（L13）、精确可见性、三色轮转、1024 次、带序号命名对四环境仍一律生效。

**可行性与画面**（每环境 ≥ 500 个随机内部布局）：

- **放置成功率**：VU N=15 在 256 次下 99.4%、1024 次下 100%；BU N=14 为 100%；Swap 两环境改用统一 OBB 规则后 N ≤ 16 都是 100%，
  若沿用 V4 圆规则 N=16 只有 50.8%（VUS）/ 45.5%（BUS）⇒ **Swap 两环境必须换规则**。
- **余量**：饱和容量 21～22 个（最少 17～18），约 30% 余量。
- **冻结布局复核**：v4-01 冻结内部布局 × 100 条干扰流，放置结果 1000/1000、1000/1000、1000/1000、998/1000 ⇒ 四环境都用 1024 次。
- **可见比例**：环带中心带可见 90.2%（VU/BU）、86.8%（VUS）、87.1%（BUS）；靠近相机的两个角只有 29～44% 可见，精确判据自动排除。
- **遮挡**：机器人初始位姿只遮挡 x∈[-0.892,-0.557]、|y|≤0.094，碰不到环带。
- **像素尺寸**：环带上容器最小约 13.7×19.0 px，不小于 V4 远侧的 12.1×17.5 px。
- **本机模拟器**（进程内补丁，不落盘）：VU 3 次 reset 加 2 局演示全部成功（482/458 步）；BU 3+2 成功（521/513 步）；
  VUS 3+1 成功（854 步）；BUS 原型 2+1 成功（704 步）。

**⚠ 陷阱与代价**：

1. **揭示段变慢**：0～31 步里 22～24 个容器同时停在 (10,10,10)，单步耗时从 38 ms 变为 108～197 ms（VU），45 ms 变为
   184～417 ms（BU），每局多 3～13 s 墙钟；落回精度不受影响（误差 0.04～0.05 mm）。对策见 L14 的独立停放点。
2. **数量对口径敏感**：VUS 的 15.40 贴着取整边界 ⇒ 数量冻成整数，并在测试里锁定参考网格上的推导（`V5_UNMASK_DENSITY`）。
3. **不能直接改全局色板**：`xhard.DISTRACTOR_COLORS` 也被 PickXtimes/SwingXtimes 导入，改它会连带改动这两个环境。

### 2.3 VideoUnmask（在 V4 xhard 上改）

**要做**：干扰容器改成贴身环带、按密度定数、半数含 cube。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `XHARD_DISTRACTOR.count` | 干扰容器个数 | `3` | **`15`**（2.2 表；L6/L10）；注入 `objects.distractors[]`，请求数 = 放下数 = 配置数 |
| `XHARD_DISTRACTOR.ring_max_abs_xy` | 环带 `max(\|x\|,\|y\|)` 内外界 | `[0.2675, 0.45]` | **`[0.2425, 0.3289]`**（L7 取 g=0.015）；注入逐容器 `xy/yaw` |
| `XHARD_DISTRACTOR.cube_count_range` | 含 cube 的个数（闭） | `[1, 2]` | **`[7, 8]`**（L11）；注入 `objects.distractor_cube_bins` |
| 颜色规则（新增 `color_rule`） | 超过 3 个 cube 时颜色怎么定 | 三色无放回，`high > 3` 即 ValueError | **`balanced_cycle`**：`order = randperm(3)`，第 j 个 cube 用 `order[j % 3]`（L12）；cube 名 `distractor_cube_<j>_<colour>` |
| `XHARD_DISTRACTOR.max_trials` | 每个容器的拒绝采样预算 | `256` | **`1024`**（N=15 在 256 次下 99.4%，1024 次 100%） |
| `spawn_ring_distractor_bins` 的校验 | 含 cube 数范围合法性 | `high > len(colors)` 即拒 | 改为 `0 ≤ lo ≤ hi ≤ count` |
| 揭示期间停放点（L14） | 干扰容器与被藏 cube 在揭示窗口停哪 | 全部停在 (10,10,10) | xhard 专用停放 helper：每个物体一个画面外停放点；窗口与落回步不变 |

**实施要点**

- 新抽样仍在**所有既有取值点之后**（N5 字面成立），内环取值与 V4 同 seed 逐位相同（`V5_UNMASK_INNER_PARITY`）。
- `min_gap_factor` 0.75 不变；可见性沿用精确的 `visible_in_camera`。
- 验收：`V5_UNMASK_RING=PASS VU=15 … out_of_ring=0 not_visible=0 shortfall=0`；`V5_UNMASK_HALF_CUBE=PASS range_ok=1 color_imbalance_max=1`；
  `V5_UNMASK_NAMES=PASS duplicate_actor_names=0`；揭示段 `V5_UNMASK_REVEAL=PASS max_return_err_mm<=0.1`。

### 2.4 ButtonUnmask（在 V4 xhard 上改）

**要做**：与 2.3 相同。字段表同构，差异只有两处：

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `XHARD_DISTRACTOR.count` | 干扰容器个数 | `3` | **`14`**（按钮 OBB 伸到 x=-0.306，挡住环带 5.7%，A_usable 0.2853） |
| `XHARD_DISTRACTOR.cube_count_range` | 含 cube 的个数 | `[1, 2]` | **`[7, 7]`** |

**实施要点**

- 环带、颜色规则、1024 次、校验、停放 helper 与 2.3 逐字相同（同一份 `spawn_ring_distractor_bins`）。
- 揭示段单步耗时增幅比 VU 更大（45 ms → 184～417 ms），L14 的停放点在本环境收益最大。

### 2.5 两个 Swap 环境的共用事项（外环随内环同步交换）

**现状：内环交换机制**（用户问「现在内部 swap 的机制是什么，最近 2 邻？」的完整回答）：

1. **次数与窗口**：VUS 的 xhard `[8,12]` 读 native `parameters.configs.xhard`；BUS 的 `[6,8]` 读 `decision.swap_count_range.xhard`。
   第 k 次交换的窗口为 `[64+33k, 64+33(k+1))`，33 = `utils/unmask_swap_xhard.py::scaled_window_steps(50, 1.5)`，窗口首尾相接。
   最后一次结束于 64+33n：VUS 为 328～460 步，BUS 为 262～328 步。
2. **发起者**：`_load_scene` 在主流上抽两次（`objects.swap_initiator_indices` 加 `objects.swap_initiator_third`），定下 3 个发起者
   a、b、c；第 k 次的发起者是 `spawned_bins[swap_indices[k % 3]]`，固定按 a,b,c,a,b,c 轮转；4 个容器里**恰有 1 个永不发起**。
3. **搭档**：`step` 在窗口第一步、`idx2` 为空时，用**实际位姿**扫描所有其他内环容器，取
   `np.linalg.norm(reference_pos[axes] - candidate_pos[axes])` 最小者，严格 `<`，平局取生成序靠前。VUS 的 axes 读
   `NATIVE_SAMPLING.parameters.swap_selection.partner.position_axes = [0,1]`；BUS 写死 `reference_pos[:2] - candidate_pos[:2]`。
   **所以「最近 2 邻」不是「最近的 2 个邻居」，而是「用 x、y 两个轴量出来的最近 1 个邻居」。** 唯一的「取最近 2 个」逻辑
   `_compute_dynamic_swap_candidates`（`distances[:2]`）加 `_select_swap_pair_from_positions` 在 VUS、BUS、VideoRepick 都没有调用者。
4. **轨迹**：`utils/statechange.py::swap_flat_two_lane`，按 smoothstep 推进；两个容器沿弦线各向相反一侧鼓出 `0.07·sin(πα)`，
   中点处相距 0.14 m；窗口结束时精确对换位姿；其余容器每步都被钉住。
5. **藏着的 cube 不随容器走**：`lift_and_drop_objectA_onto_objectB` 在 `[64, last_end)` 期间把 cube 传送到 (10,10,10)，
   到 last_end 再放到它那只容器最终的 XY 下方。
6. **结果结构**：因为搭档互为最近邻，VUS 60.7%、BUS 81.9% 的局只在 2 个不相交的对之间来回换；23.9% / 26.7% 的交换会直接撤销上一次。
7. **碰撞检测**：reset 时 `_check_state_readonly('initial')` 对内环加干扰容器做静态 SAT；每个窗口起点
   `_check_swap_sweep_from_actual` 调 `utils/bin_collision.py::check_swap_sweep`，只支持**一对**移动、其余视为静止，用区间二分做证明
   （`LANE_OFFSET 0.07`），证不出就抛 BinCollisionError，演示判失败，靠 H4 递补。**V4 观测到的 8 次 BinCollisionError**
   （实跑 VUS ep3 seed 4500300 的 sweep#1，bin_2 撞 bin_1，g = -0.00207；另有 V6 中 VUS 1 次、BUS 6 次）**全部是内环对内环**，
   且 **8/8 都能在 reset 时预判**。离线副本对 20 行 Swap 规格逐位一致。

**为什么不能照抄内环**：若把外环完全照抄（V4 环带、3 个干扰、最近邻、无回退），最近的干扰常在场地对面，路径中位长度
0.46～0.49 m 会横穿内部；只有 31%（VUS）/ 29%（BUS）的局全程无碰撞且在画面内；BUS 有 787/2084 个窗口会让外环容器进入按钮禁区。

**改法（L16～L23）**：

```text
配置 decision.xhard.distractor_swap（只在 xhard 声明）：
  {enabled, initiator_rule: permutation_cycle, fallback: next_in_permutation,
   partner: {selection: nearest, position_axes: [0,1], tie_break: first_in_index_order,
             population: distractor_bins, resolve_at: reset_plan},
   lane_offset: 0.07, smooth: true,
   path_constraints: {camera_visible, min_inner_circle_clearance_m: 0.04, min_button_center_dist_m: 0.122},
   layout_max_attempts: 16}

reset，仍在 _spawn_xhard_distractors 里，仍是 _load_scene 的最后一句；只用独立流：
  for attempt in 1..16:
    放置干扰容器（2.2 的规则；recorder.value 推迟到本次尝试被接受之后）
    perm = randperm(count)                                ← 追加的一次抽样
    对每个窗口 k（内环对与起始状态按 predict_swap_sweeps 预测）：
      for j in 0..count-1:
        o = perm[(k+j) % count]
        p = 在干扰容器中取 XY 最近邻（严格 <，平局取序号小）
        若同时满足以下四条，接受 (o,p)：
          · check_multi_swap_sweep([(内环对k), (o,p)], 其余全部静止) 通过
          · o、p 两条中心路径全程在画面内
          · 离每个内环容器圆距 ≥ 0.04
          · （仅 BUS）离两个按钮中心 ≥ 0.122
      名义上对换 o、p 的位姿
    某个窗口所有 j 都不可行 → 本次尝试作废，整段重抽
  16 次都失败 → 抛 SceneGenerationError（候选级重抽，依赖 L3）
  记录：objects.distractors.swap_order（value）；actions.distractor_swap_pairs、
        actions.distractor_swap_fallback、layout.distractor_layout_attempts（record）

运行时（step）：
  内环搭档照旧在运行时解析（L22）
  xhard 的 _check_swap_sweep_from_actual 改为两对联合检查，用实际位姿
  外环 swap_flat_two_lane 循环与外环 cube 的 lift_and_drop 循环
    放在 AST 锁定的那一个 `for i in range(len(self.swap_schedule))` 循环之外
```

**关键设计点**：

- **联合证明不需要新数学**：`check_multi_swap_sweep` 直接复用 `_prove_pair`（它本来就能证两个都在动的物体）。单对时与
  `check_swap_sweep` 逐位相同（15/15，含 3 个接触拒绝），远处加第二对也不改变结果。
- **外环在 reset 时预先规划**，不在运行时解析：窗口起点时上一次交换只完成到 99.7%，实际位姿与名义差 0.686 mm，近平局会因此
  翻转（VUS 7/8969、BUS 11/5982 个窗口）；外环规划借用 VideoRepick 的 5 mm 余量吸收这个偏差。
- **认证预筛（L23）**：采样 401 个 s 值，只跳过已证明分离的对，判定结果不变（40/40）。单窗联合检查从 0.8～1.8 s 降到 3～55 ms；
  V4 干扰采样本身也从 4.75 s 降到 0.0025 s。不加预筛时 VUS reset 从 15.5 s 变为 33～66 s，BUS 原型约 24～26 s。
- **内环对内环在 reset 预判（L20）**：VUS 1.3%、BUS 10.7% 的局会从演示级失败挪成候选级拒绝。
- **不增加控制步**：外环与内环同窗口，`swap_schedule[-1][3]` 与所有等待点都不变（`STEP_BUDGET=PASS added_steps=0`）。

**与 2.2 贴身环带合起来能不能成**：两个调查方各自只测了自己那一半，汇总方用 `joint_probe.py`（每环境 300 个布局、圆近似、
`evc` 判据）试算了合并情形：

| 设置 | 首次布局可行（VUS / BUS） | 第一候选发起者就可行的窗口 |
|---|---|---|
| V4 环带，3 个，带回退 | 63.3% / 45.2% | — |
| V4 环带，6 个，带回退 | 99.0% / 96.7% | 73%（VUS） |
| V4 环带，10 个，带回退 | 100% / 100% | — |
| **贴身环带，15 / 16 个，带回退** | **99.67% / 96.99%** | **44% / 29%**（回退很多） |

**用户已定 L16 (b)：Swap 两环境取「V4 环带、10 个、带回退」这一行**（圆近似试算 100% / 100%），不用贴身环带。S1 离线复核只需用最终规则复跑这一行确认。

**⚠ 陷阱**：

1. **AST 锁**：`tests/lightweight/test_episode_action_sampling.py::test_real_swap_resolution_matches_baseline_and_preserves_ties`
   会把唯一那段 `range(len(self.swap_schedule))` 循环抽出来放到 SimpleNamespace 上执行。新代码必须写在循环之外，或一律用 `getattr` 带默认值。
2. **末句约束**：`_spawn_xhard_distractors` 必须仍是 `_load_scene` 的最后一句（`test_干扰容器在load_scene末尾且不用主流` 会检查）。
3. **规格回放**：在拒绝循环里调用 `SpecRecorder.value`，回放时会在早期尝试就返回冻结值 ⇒ 只对被接受的那次尝试调用 `value()`，
   尝试次数与配对用 `record()` 留痕（N18）。
4. **来回撤销仍在**：最近邻规则下外环也会来回撤销（count = 6～10 时 25～32%），这是有意镜像内环（24～27%）的结果。
5. **停放点堆叠**：外环 cube 也停在 (10,10,10)，会与内环 cube 叠放数百步，**尚未实测**，见 L14。
6. **按钮与手臂不在碰撞模型里**：碰撞模型只有容器；BUS 演示时机器人会在交换期间去按按钮，按钮风险目前只用中心距阈值近似，
   演示级影响要看 V6。

### 2.6 VideoUnmaskSwap（在 V4 xhard 上改）

**要做**：干扰容器贴身环带 15 个、统一采样器；外环随内环同步交换；两对联合碰撞证明；内环对内环 reset 预判。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `unmask_swap_xhard.py::XHARD_DISTRACTOR.count` | 干扰容器个数 | `3` | **`10`**（L16 b）；注入 `objects.distractors[]` |
| `XHARD_DISTRACTOR.ring_half_extent` | 环带 | `[0.2675, 0.45]` | **不变**（L16 b：沿用 V4 环带，不用贴身带）；注入逐容器 `xy/yaw` |
| `XHARD_DISTRACTOR.with_cube_range` | 含 cube 个数 | `[1, 2]` | **`[5, 5]`**；注入 `objects.distractor_cube_bins` |
| `XHARD_DISTRACTOR.min_gap`（间距规则） | 干扰容器与其他对象的间距 | 圆间距 `0.04`（中心距 0.1178） | **统一 OBB 规则**（与 VU/BU 同一采样器与 schema，L13） |
| 可见性判据 | 采样点是否在画面内 | `visible_on_camera` 线性近似 | **精确 8 角点 `visible_in_camera`** |
| `DISTRACTOR_MAX_TRIALS` | 每个容器预算 | `512` | **`1024`** |
| cube 命名与颜色 | — | `distractor_cube_<colour>`，三色切片、重复即重名崩溃 | 带序号 `distractor_cube_<j>_<colour>`，三色平衡轮转；新增 `cube_bins` 映射 |
| `decision.xhard.distractor_swap`（新增） | 外环交换规则 | 无（干扰容器不交换） | 2.5 的配置块；注入 `objects.distractors.swap_order`（value）、`actions.distractor_swap_pairs` / `actions.distractor_swap_fallback` / `layout.distractor_layout_attempts`（record） |
| `_spawn_xhard_distractors` | reset 时的干扰容器放置 | 放置 + H1 静态/扫掠拒绝 | 放置 + 外环规划（`plan_distractor_swaps`：发起者 `randperm(count)` 全体轮转 L17、失败按排列换下一个 L18、路径离内环 ≥ 0.04 L19、lane 0.07 L21，最多 16 次整段重抽）+ **内环对内环扫掠预判**（L20）；失败抛 `SceneGenerationError`（L3） |
| `_check_swap_sweep_from_actual` | 窗口起点的运行时复核 | 单对 `check_swap_sweep` | **两对联合** `check_multi_swap_sweep`（实际位姿）+ 认证预筛（L23） |
| `step` | 交换执行 | 只有内环 `swap_flat_two_lane` 循环 | **在 AST 锁定循环之外**新增外环 `swap_flat_two_lane` 循环与外环 cube 的 `lift_and_drop` 循环；不增加步数 |

**实施要点**

- 内环发起者、搭档解析、窗口 `[64+33k, …)`、速度 ×1.5 全部不动；`_resolve_sampling_config` 对 `object_selection` / `swap_selection` / `xhard`
  的 JSON 全等铁闸不动。
- 干扰容器仍**不进 `spawned_bins`、不用 `bin_<i>` 命名** ⇒ 内环最近邻搜索与 `_verify_swap_binding` 天然不受影响。
- 外环规划只用独立流 `distractor_generator`，主流取值与 V4 同 seed 逐位相同（`V5_UNMASK_INNER_PARITY`）。
- 验收：`OUTER_SWAP_PLAN=PASS resets=100 windows_planned_eq_n_swaps=100`；`OUTER_SWAP_CERT=PASS specs=N windows=W rejected=0`；
  `OUTER_SWAP_EXEC=PASS max_err_m<1e-3`；`CUBE_FOLLOW=PASS max_err_m<2e-3`；`OUTER_VISIBLE=PASS frames=F missing=0`；
  `INNER_SWEEP_RESET_REJECT`（用 V4 实跑失败局 seed 4500300 作反例）。

### 2.7 ButtonUnmaskSwap（在 V4 xhard 上改）

**要做**：与 2.6 相同。字段表同构，差异四处：

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `XHARD_DISTRACTOR.count` | 干扰容器个数 | `3` | **`10`**（L16 b；与 VUS 相同，含 cube `[5,5]`） |
| `distractor_swap.path_constraints.min_button_center_dist_m` | 外环路径离按钮中心的下限 | 无 | **`0.122`**（照抄内环时 787/2084 个窗口会进按钮禁区，L19） |
| `_load_scene` 内环 `spawn_random_bin` 失败分支 | 放不下时的行为 | `except RuntimeError: break` 静默截断（约 1/500，截断后环带障碍与交换对都会变） | xhard 下抛真 `SceneGenerationError`（L15） |

**实施要点**

- 环带沿用 V4，与 VUS 完全相同。
- 本环境**所有任务 `demonstration=False`**，交换段计入 1302 预算；外环与内环同窗口不增加步数，预算余量与 V4 相同。
- 本环境**没有 `_verify_swap_binding`**，干扰容器若混进 `spawned_bins` 会静默改变交换对 ⇒ 统一采样器仍必须单独存 `distractor_bins`。
- 搭档解析写死 `[:2]` 不动；外环规划的 `position_axes: [0,1]` 与之等价。

### 2.8 InsertPeg（在 V4 xhard 上改）

**要做**：四根杆同一采样器，不给第 4 根单设约束，两两轮廓间隔 > 3 cm。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `config_xhard.near_target_distractor` | 第 4 根杆贴近目标杆的圆环带 | `{anchor_peg_index: 0, max_center_distance_m: 0.085}`（下限 0.075） | **删除**（L28）；`InsertPeg._xhard_place_near_target_peg` 一并删除 |
| `config_xhard.peg_min_pair_gap_m`（新增） | 任意两根杆**轮廓**的最小间隔 | 无（只有杆根中心距 > 0.075） | **`0.03`**，严格不等号（L24）；注入 `min_pair_gap_m` |
| `config_xhard.peg_box_min_gap_m`（新增） | 杆轮廓与孔板轮廓的最小间隔 | 无（只有杆根离孔板中心 > 0.06） | **`0.01`**（L26）；注入 `min_box_gap_m` |
| 抽样顺序（`_initialize_episode` xhard 分支，新增 `_xhard_sample_pegs`） | 4 根杆何时、怎么抽 | `pegs[:-1]` 3 根原生循环 → obj/dir → 第 4 根另一个采样器覆盖 `peg_init_poses[3]` | **4 根一个循环、放在 obj/dir 之前、同一套规则**；yaw 在通过原生判据后才抽（lazy，L27）；注入 `peg_attempts` |
| 间隔度量 | 怎么量「两两之间」 | 杆根中心距 | 保留原生杆根规则 + **有向矩形精确距离 `footprint_gap`**（L25）：杆 = 中心 `root − 0.025u`、半尺寸 (0.05, 0.01)；孔板半尺寸 (0.05, 0.04)；SAT 判重叠时为 0，否则取 32 个顶点到边距离的最小值 |
| 回放守卫（L29） | 回放冻结规格时是否复核 | 不复核（`SpecRecorder.value` 直接返回冻结值） | **复核两种间隔**，不合格报错；V4 header 被形状检查拒绝 |

```text
for i in 0..3:
  for attempt in 1..512:
    x, y = rand, rand（与原生相同）
    若 |xy − box| ≤ 0.06 或 |xy − root_j| ≤ 0.075 → 重抽              ← 原生规则保留
    yaw = (rand·2 − 1)·π                                                ← lazy：通过原生规则后才抽
    若 footprint_gap(peg, box) ≤ 0.01 → 重抽                            ← L26
    若对任一已放杆 j 有 footprint_gap(peg, peg_j) ≤ 0.03 → 重抽          ← L24，严格不等号
    接受
```

**实施要点**

- **为什么 0.075 m 不保证间隔**：`utils/object_generation.py::build_peg` 的根是杆头中心，整根杆轮廓 0.10×0.02 m，从 `root − 0.075u`
  伸到 `root + 0.025u`，0.075 m 的杆根距离允许穿插；只靠中心距要保证不重叠得 > 0.1513 m。V4 xhard 目标杆可见轮廓与别的杆重叠 28.1%，
  任意一对 30.7%；重叠的目标杆在 20 步沉降里被挤动 2.5 / 5.4 / 11.8 / 68.8 mm，最多转 55.8°。V4 正式局成功 2/10，8 局失败里 3 局目标重叠、
  2 局邻杆在夹爪闭合区、1 局目标压孔板、2 局抓取点离基座 ≥ 0.81 m。
- **为什么是 0.03**：夹爪张开时每指 0.04，指尖沿杆向宽 17.5 mm；`0.01 + g ≥ 0.04` 时邻杆不可能落在指间闭合区，g = 0.03 是满足
  这一点的最小值；执行段 `failure_func`（抓起任何非目标杆即失败）恰好惩罚这种情况。夹入风险从 21.5% 降到 0，指垫压到邻杆从 29.5% 降到 2.1%。
- **实测收益**（离线 10000 布局 + torch 原型 1000 seed，原型用精确的 V5 抽样顺序）：4 根杆每次尝试接受率均值 [0.875, 0.779, 0.688, 0.603]，
  最多尝试 [4, 7, 9, 10] 次；512 次耗尽概率约 0（MC 0/10000、原型 0/1000，最小实测间隔 0.0301）；杆与杆、杆与孔板重叠都是 0
  （V4 分别 28.1% 与约 21%）；点选歧义（邻杆离目标杆 < 10 px）19.3% → 0。代价：目标杆到最近干扰杆的中位距离 0.080 → 0.178 m，
  V4「新杆贴近目标」的难度意图随之消失（L28）。孔板规则的证据：没有它的 V5 原型里一根杆压到孔板被弹飞 7986 mm。
- 目标恒为 peg_0（`randint(0,4)` 立刻被 `overridden_to=0` 覆盖）、4 根同色、`peg_count`/`peg_offsets` 都不动；peg_0 只是第一个被抽的。
- ⚠ 不等号必须严格：矩形重叠时距离为 0，写成 `gap ≥ 0` 等于没有约束（MC 里仍有 25% 重叠）。
- ⚠ 可达极限不在本议题：约 16% 的布局抓取点离基座 > 0.78 m，间隔规则管不到；**演示成功率尚未实测**。
- 验收：`INSERTPEG_V5_SPACING=PASS min_pair_gap_m>0.03 min_box_gap_m>0.01`（20 次真实 reset）；`INSERTPEG_V5_RNG_ORDER=PASS exact=20`；
  `INSERTPEG_V5_SETTLE=PASS max_dxy_mm<1.0`（静置 20 步）；`INSERTPEG_V4_SPEC_REJECTED=PASS`。

### 2.9 MoveCube（在 V4 xhard 上改）

**要做**：方块、目标圆盘、杆都不得落在**桌面中心的共同禁区**，用直接拒绝，不再用 bias（用户口径：「桌面中心尽可能不要出现三个物体，
比例由实施方定」）。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `config_xhard.corner_bias` | 边角偏置（经 `utils/xhard.py::corner_push`） | `0.5`（作用于杆抖动、方块候选中心与局部偏移；goal 从未被偏置） | **删键、删干净**（L33）：`_native_decision` 的 `demo_layout.xhard.corner_bias` / `execution_layout.xhard.corner_bias`、`_xhard_corner_bias`、`_load_scene` 里对 `corner_push` 的调用、`spawn_random_cube(..., corner_bias=)` 的传参、`layout.*.corner_bias` 记录、对应单测一并删除；`utils/xhard.py::corner_push` 与 `spawn_random_cube` 的 `corner_bias` 形参保留（PickXtimes 仍用） |
| `config_xhard.center_exclusion`（新增） | 桌面中心禁区 | 无 | **`{shape: circle, center: [0, 0], radius_m: 0.05, judge: object_center, max_trials: 128}`**；`_native_decision` 按 segment 暴露 `demo_layout.xhard` / `execution_layout.xhard`；注入 `layout.{demo,execution}.center_exclusion` |
| 杆根抖动（`_load_scene` 的 `x_jitter/y_jitter`）与 yaw | 杆的位姿 | `corner_push` 后直接用 | 抖动与 yaw 抽完后，判杆轴线段离 (0,0) 的最近点 `< 0.05` 即原地重抽（上限 128，超出抛 `SceneGenerationError`）；几何上几乎不触发（见要点） |
| goal（`spawn_random_target`） | 目标圆盘中心 | 无拒绝（demo 半宽 0.11、exec 0.06 内均匀） | 加显式参数（L4 b）：圆盘**中心**离 (0,0) `< 0.05` 即拒绝 |
| 方块候选（局部函数 `_sample_cube_center`） | 方块候选中心 | 接受条件 `\|c − g\| > 0.1` | 加「候选中心离 (0,0) ≥ 0.05」 |
| 方块最终（`spawn_random_cube`） | 方块最终中心 | 默认 `include_existing=True` | 加显式参数：最终中心离 (0,0) `< 0.05` 即拒绝；**执行段 `cube_2` 改 `include_existing=False`**（L34 已定：是） |

```text
禁区：圆心 (0,0)，R = 0.05 m；判据一律按物体中心（杆按轴线段最近点）
  goal：  |c_goal| < R  → 重抽
  方块：  |c_cand| < R 或 |c_final| < R → 重抽
  杆：    dist(segment(root − 0.075u, root + 0.025u), (0,0)) < R → 重抽
不按轮廓判：exec goal 只在半宽 0.06 的框里抽、圆盘半径 0.04，要求轮廓不进圆时无解
```

**实施要点**

- **为什么是 R = 0.05**：比方块边长 0.04 与 goal 圆盘半径 0.04 都略大，中心一块直径 10 cm 的空地在 256×256 画面里约 14 px 宽，
  肉眼可辨「中间是空的」；再大会把执行段 goal 的采样框（半宽 0.06）几乎吃光。
- **杆物理上本来就进不了中心**：杆根 |y| ≥ 0.15，杆身从根向内最多伸 0.10（`build_peg`：root − 0.075u … root + 0.025u，
  两端合计 0.10），最近只能到 y = 0.05，恰好与 R 相切；这条规则对杆几乎不拒，写上只为三者同一条规则。
  若用户要杆离中心更远，只能缩小杆根的 `base_y_abs`/`jitter_span` 采样带，那是另一个决策。
- **每次抽样的拒绝率**（解析值，采样框内均匀）：demo goal `π·0.05²/0.22²` = 16.2%；exec goal `π·0.05²/0.12²` = 54.5%；
  方块候选 `π·0.05²/0.2²` = 19.6%；杆 ≈ 0。exec goal 在 128 次预算下耗尽概率 0.545^128 ≈ 1e-33。
  ⚠ 2.9 原来那套「各物体自身框 30% 面积」的 MC 数字（2000 局全成功、每局多抽约 10 个随机数、本机演示 10/10）**不再适用**，
  S1 离线复核时按本规则重跑；演示成功率仍要靠 S3c 的本机演示探针。
- **偏置不等于排除**：V4 的 goal 从未被偏置，demo goal 有 26% 的中心落在 5 cm 圆内、exec goal 约 55%；方块最终位置约 6%。
- **既有缺陷（L34）**：执行段 `cube_2` 用默认 `include_existing=True`，把演示段方块的（退化）OBB 当障碍；两块在物理上**从不同时在场**
  （`cube_2` 被传送到 (10,10,1)，阶段切换时 `step` 再把 `self.cube` 挪到 `cube_init_pose_2`），但候选落在演示方块附近时 256 次会全部失败。
  V4 xhard 失败率 0.33～0.60%（seed 1000442、1000446 已在真实模拟器复现）；改 `include_existing=False` 后 0/3000。原三档同样有此缺陷
  （0.60～1.07%，抛 RuntimeError），H2 下不修。
- `peg_yaw_range` ±π、三条 way、goal 区域尺寸都不动。
- 验收（落成单测与单次 reset 检查）：`MOVECUBE_CENTER_EXCLUSION=PASS seeds=5000 zone_violations=0 layout_fail=0`；
  `MOVECUBE_REJECTION_BUDGET=PASS exhausted=0`；`MOVECUBE_EXEC_SPAWN=PASS seeds=2 ok=2`。

### 2.10 PatternLock（在 V4 xhard 上改）

**要做**：不改布局，演示在 5×5 上尽可能长（用户 L35）。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `config_xhard.length` | **节点数** | `[20, 24]` | **`[24, 25]`**（5×5 不重访路径的上限是 25）；注入 `actions.path_nodes` |
| `native.path_selection.max_attempts` 的 xhard 值 | 路径搜索预算 | `1000`（所有档共用） | xhard **`20000`**（25 节点单次命中率 0.035%，20000 次内约 99.9%；DFS 单次毫秒级）；原三档仍 1000 |
| 路径搜索耗尽 | 搜不到时 | 静默沿用最后一条错误长度的路径（K1 的根因） | xhard 下抛 `SceneGenerationError`（依赖 L3） |
| 运行记录 | 实际演示帧数 | ep0/3/6 实测 649 / 683 / 757 帧 = 21.6 / 22.8 / 25.2 s | 预计 23～24 段 × 平均 34.25 帧 ≈ 788～822 帧 ≈ **26.3～27.4 s**；记 `demo_frames` |

**实施要点**

- **每段帧数不恒定**：`solve_swingonto` 在关节空间做时间参数化，左右移动约 25.7 帧，前后 37.4，斜向 37.2，靠远排 x=0.1 的约 46，
  平均 **34.25**（V4 当时假设 31）。5×5 上是简单路径 DFS（`utils/adjacent.py::dfs_path` 带 visited），最多 25 节点 ⇒
  **不改布局时上限约 27.4 s，到不了 30 s**；这是用户接受的代价（「尽可能长」）。
- **单次命中率**（20000 次随机 DFS 的节点数分布）：24 节点 52/20000、25 节点 7/20000；1000 次预算下 25 节点只有约 30% 能搜到，
  所以 V4 K1 把上限收到 24。提到 20000 次后 24 节点约 100%、25 节点约 99.9%；搜索是纯 Python DFS，单次毫秒级，20000 次约十几秒，
  S1 离线复核时实测一次并记录。
- 网格 5×5、中心 `[-0.1,0]`、间距 0.1、搜索算法（`find_path_0_to_8`、8 邻接）都不动（B8 保留）。
- 执行段与演示段等长，最长约 822 步，对 1301 预算余量约 480。
- 曾评估过的其他杠杆（6×6@0.08 节点 [30,33]、5×6@0.1、演示放慢 ×1.3、允许重访）均因「不改布局」作废，离线数字留在
  `artifacts/newtask-v5/plan-probes/long_demo/`。
- ⚠ 帧数模型只是预测（离线 mplib screw 模型与真实 h5 误差 −1.3%～+0.1%），验收一律以真实 h5 的 `is_video_demo` 帧数为准。
- 验收（落成单测与单次 reset 检查）：`PL_LEN_EXACT=PASS wrong_length=0`；生成报告里报每局 `demo_frames`。

### 2.11 RouteStick（在 V4 xhard 上改）

**要做**：演示时长校准到 25～35 s。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `config_xhard.length` | **段数 L**（节点数 = L+1） | `[12, 15]` | **`[15, 21]`**（25.0～35.0 s，均值 30.0 s；L37 已定，不与 PatternLock 对齐）；注入 `objects.L` |
| decision 新增 xhard 的 L 范围键（L38） | L 范围是否冻进 header | 从类属性读，V4 header 未冻结 | **冻进 decision 与规格 header**；V4 规格在 V5 代码上直接被拒 |
| 运行记录 | 实际演示帧数 | ep0/3/6 实测 650 / 600 / 600 帧 = 21.7 / 20.0 / 20.0 s | **每段恰好 50 帧** ⇒ 750～1050 帧；记 `demo_frames` |

**实施要点**

- 每段恰好 50 帧来自 `solve_swingonto_withDirection` 的 45 个贝塞尔点 + 末端 5 个保持点；L = 15～21 ⇒ 25.0 / 26.7 / 28.3 / 30.0 /
  31.7 / 33.3 / 35.0 s，均匀抽样时均值恰为 30.0 s。抽样点与顺序都不变，只改 L 值域，满足 N5 字面。
- **更正 V4 计划 2.20 的错误陈述**：`scripts/evaluation.py` 写死 `max_steps=1300`，`max_steps_without_demonstration=1302`，
  DemonstrationWrapper **只计非演示步**，reset 初始步已计 1，策略实际有 **1301 步**；`solve_strong_reset(timestep=200)` 是
  `demonstration=True` 的 NO RECORD 任务，在 reset() 里跑完，**不计入预算**；执行段 = 50·L（+1 初始帧），**截断点为 L ≥ 27**
  （模拟器里 L=26 在第 1296 步成功，L=27 在第 1302 步超时）。L=21 时执行段 1050，余量 255 步（19.6%）。
- 数据生成 fail-safe 5000，已用步数约 100·L + 327，L=21 时约 2427。
- 验收：`RS_DEMO_LEN=PASS rule=L*50 mismatches=0 min_frames=750 max_frames=1050`；`EXEC_BUDGET=PASS timeouts=0 max_success_count<=1100`；
  `FAILSAFE_MARGIN=PASS max_elapsed<=2500`。

### 2.12 BinFill（在 V4 xhard 上改）

**要做**：修障碍框缺陷，加同色成团上限；位置采样规则不动。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| xhard clutter 分支的障碍框（`_load_scene`） | 已放方块如何进 `avoid` | actor 本身（66.45% 退化成线段，23.3% 的方块离邻居 < 2 cm） | **`cube_obb2d_exact` 预制三元组**（2.0①）；名义 2 cm 间距真正生效 |
| `decision.configs.xhard.color_mix`（新增） | 同色成团上限 | 无 | **`{max_component: 3, link_m: 0.09, max_redraws: 64}`**（L41）；注入 `objects.color_redraws`、`objects.color_mix_fallback` |
| `_load_scene` xhard clutter 分支结构 | 位置与颜色怎么定 | 逐块抽位置、颜色按 `spawn_order` 交错 | 拆成三段：**先放 12 个槽位只做几何 → 按 V4 语义分配颜色 → 建 actor**；最大同色连通团（阈值 0.09 m）> 3 块时**追加**一次 `randperm(12)` 重排颜色，最多 64 次；注入 `layout.slots.<k>`、`objects.slot_assignment`；`layout.cubes.*` 保留改由 `record()` 写入 |

**实施要点**

- **位置本就均匀**：单局每块在剩余空闲区均匀；跨局按钮加板平均占去 34%（12.5～49.5%），6×6 格相对密度 0.65～1.38（KS p < 1e-43），
  靠墙靠角 1.2～1.46 倍是逐个放置的正常副作用；颜色与位置独立（2000 局置换检验触发率 4.9%）。ep3 的红色成堆：7 块红（≥7 概率 22%），
  按钮 (-0.155, 0.178)、板 (0.050, -0.006) 只剩 x ≈ -0.25 一条空带，多重校正后 p = 0.0086，约 4.0% 的局至少这么极端；
  障碍框缺陷再让 red_0 与 red_2 只隔 8.4 mm。
- **A（修缺陷）的收益**：离邻居 < 20 mm 的方块 23.3% → 0；最近邻中位距离 80.0 → 85.8 mm；同色 9 cm 连通团 ≥ 4 块的局 6.3% → 3.8%；0/3000 失败。
- **B（成团上限）的收益**：只有 3.8% 的局需要重排，平均 0.047 次，0 次用到兜底；团 ≥ 4 块降到 0；过度混匀只有 2.8%；**位置完全不变**，只换颜色标签。
- **不推荐**：放置后打乱颜色、交错生成序（标签本来就可交换，统计上无效）；蓝噪声铺点（汇总密度反而更不均匀，CV 0.28～0.33，随机数多 3～6 倍）；
  限制每色块数（改配额规则，平移整条流，L42）。
- 配额规则（`color_pool=randperm(3)`、投入色数 [2,3]、投入总数 [5,7]）、按钮/板采样、`native_dynamic` 分支都不动。
- 验收：`BINFILL_MIN_GAP=PASS violations=0`；`BINFILL_COLOR_MIX=PASS T=3 violations=0 fallback=0`；
  `BINFILL_REDRAW_APPEND_ONLY=PASS pos_equal=2000/2000`；`BINFILL_NOT_OVERMIXED=PASS anti_p05_frac<=0.06`。

### 2.13 PickXtimes（在 V4 xhard 上改）

**要做**：去扎堆——3 个有色方块各占不同象限、6 块两两 ≥ 8 cm、修障碍框缺陷。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `XHARD_DECISION.target_cube_position_policy`（新增 `quadrant_distinct`） | 3 个有色方块的象限约束 | 无（`corner_bias 0.5` 保留，91.3% 落角格，44.5% 的局 ≥2 块同角格） | **各占不同象限**，象限以 `(-0.1, 0)` 划分，经 `extra_reject` 实现（L43-a）；注入 `layout.cube_dispersion` |
| `XHARD_DECISION` 新增 `min_center_dist_m` | 6 块（3 有色 + 3 干扰）两两最小中心距 | 无（只有 OBB `min_gap`，且退化） | **`0.08`**（L44）；注入 `layout.cube_min_center_dist` |
| 障碍框（`_spawn_scene_objects_xhard` / `_spawn_distractors_xhard`） | 已放方块如何进 `avoid` | actor（15.5% 的局有 < 6 cm 的对） | `cube_obb2d_exact` 预制三元组 |
| `max_trials` | 每块的拒绝预算 | `256` | **`1024`**（L45；256 次时 reset 失败 3.53%，1024 次 0.97%） |

**实施要点**

- **归因**：同角挤压的约 30 个百分点来自 `corner_bias`（`corner_push` 对每个轴 `t' = sign(t)|t|^p`，p = 1/(1+4b)，b=0.5 时 p=1/3，
  联合分布集中在 4 个角格：拒绝前 92.7%、拒绝后 91.3%）；< 6 cm 的对 100% 来自障碍框缺陷；松散的 10 cm 团主要由密度决定
  （理想 Poisson 6 cm 过程也有 41%）。按钮总在靠机器人一边，有色方块远侧 56.8%、近侧 38.9%；整个区域只占画面 11.0%。
- **改后效果**（3000 局）：同角格 44.5% → 0，同象限 58.9% → 0，< 8 cm 的对 → 0，10 cm 三块团 45.3% → 19.9%；目标到边缘的中位距离
  1.75 → 1.63 cm（推向边角的意图保住）。
- 抽样顺序（按钮 → `randperm(3)` → 占位 `randint(3)` → 圆盘 → 3 有色 → `randint(3)` 选目标 → 3 干扰）不变；G1 先放盘不变。
- **可选（L46）**：把方块区扩到半宽 0.25，RMS 分散度 +36%、10 cm 团降到 4.3%；但远角离基座约 0.78 m，最多 15 次抓放的可达性没测过，先做演示探针。
- ⚠ **位置捷径**：J5 + 象限规则下有色候选块都在角上、干扰块在中间，仅凭位置就能区分候选与干扰；若这对基准有影响，需用户另行决策。
- 验收：`V5_EXACT_OBB=PASS degenerate=0`；`V5_PICK_DISPERSION=PASS same_cornercell_ge2=0.000 min_pair_lt_0p08=0.000 in_corner_cell>=0.85`；
  `V5_RESET_FEASIBILITY=PASS pick_fail<=0.010`。

### 2.14 SwingXtimes（在 V4 xhard 上改）

**要做**：去扎堆——6 块两两 ≥ 8 cm、修障碍框缺陷；本环境没有任何 `corner_bias`。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `_load_scene` 有色方块循环 | 3 有色方块的放置 | **被所有档共用**的一段循环（在 `[-0.1,0]±0.25` 均匀抽） | 加显式 difficulty 分支：非 xhard 一支逐字保留原代码；xhard 一支加下面两条 |
| `XHARD_DECISION` 新增 `min_center_dist_m` | 6 块两两最小中心距 | 无 | **`0.08`**（L44）；注入 `layout.cube_min_center_dist` |
| 障碍框 | 已放方块如何进 `avoid` | actor（7.3% 的局有 < 6 cm 的对；冻结规格 2/10，4.8 / 5.4 cm） | `cube_obb2d_exact` 预制三元组 |
| 异常类（2.0③） | 圆盘放不下时抛什么 | TypeError（遮蔽） | xhard 抛真 `SceneGenerationError`（L3） |

**实施要点**

- 改后效果：< 6 cm 的对 7.3% → 0，< 7 cm 的对 23% → 0，10 cm 三块团 22.2% → 10.3%；圆盘放不下的失败率 1.9% → 3.6%（由 F2 重抽吸收）。
- ep3 的斜排三块相距 12.7 cm 和 9.3 cm 是偶然，近机器人处透视把间距压缩了一半。
- 验收：`V5_SWING_SPACING=PASS min_pair_lt_0p08=0.000`；`V5_RESET_FEASIBILITY=PASS swing_fail<=0.040`。

### 2.15 VideoRepick（在 V4 xhard 上改）

**要做**：均匀摆放，全部方块参与交换。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| `config_xhard` 新增 `min_center_dist_m` | 6 块两两最小中心距 | 无（最近一对中位 0.079 m；26.9% 的局 ≥3 块挤在同一六分之一区域） | **`0.12`**（L50），经 `spawn_random_cube(..., extra_reject=…)`，每次 trial 仍是 3 个 rand；注入逐块 `xy` |
| 发起者（`objects.swap_initiators_remaining`） | 谁发起第 k 次交换 | `[目标] + randperm(5)[:2]`（B12），`swap_indices[k % 3]` | **6 块全部发起**（L47-a）：`randperm(5)` 原本就抽了、只是 V4 只取 `[:2]`，现在用满；`seq[k] = 目标`（k % 3 == 0），否则按 perm 顺序轮转其余 5 块；不新增抽样；`swap_initiators_remaining` 变为长度 5 |
| 搭档（新增 `VideoRepick._plan_swaps_xhard`） | 第 k 次和谁换、在哪定 | `step` 里运行时按实际 XY 取最近邻（`position_axes [0,1]`） | **reset 时规划**（L49）：在名义槽位上用 `cube_shape_specs(hs + 0.005)` 按距离排序其余槽位，过滤扫掠不可行的（`check_swap_sweep`，按无序对缓存）与「重复上一对」的，取前 2 个、用 `u[k]` 均匀选一个（L48）；某步没有可行搭档抛真 `SceneGenerationError`（L3）；注入 `actions.swap_pairs.<k>`（value） |
| 新增取值点 `objects.swap_partner_u` | 搭档选择的随机数 | 无 | **追加**一次 `u = torch.rand(n_swaps)` |
| `step` 的搭档分支 | 运行时用哪个搭档 | 最近邻循环 | xhard 用规划好的搭档；**D5 的 `_check_swap_sweep_from_actual` 保留**作运行时守卫与回放交叉核对 |

**实施要点**

- **为什么不是所有 cube 都动**：3 个固定发起者加最近邻搭档，槽位集合在交换中从不改变，每个发起者只能在自己的最近邻链上来回。
  V4 6 块全部动过的局只有 **17.0%**，目标回原位 35.7%，单局同一对最多重复 5.77 次；ep3（seed 4900300，12 次，发起者 bin_5/bin_4/bin_0）
  的交换序列 (5,2),(4,3),(0,2),(5,0),(4,3),(0,5),(5,0),(4,3),(0,5),(5,0),(4,3),(0,5)，bin_4↔bin_3 来回 4 次净效果为零，**bin_1 一次没动**。
- **实测**（离线 1500～2400 局；最小距 0.12、余量 5 mm、k = 2、交错发起）：

  | 指标 | V4 | V5 |
  |---|---|---|
  | 摆放成功 | 100% | 100%（2400/2400） |
  | ≥3 块同在一个六分之一区域 | 26.9% | 3.8% |
  | 一侧 ≤ 1 块 | 13.5% | 1.5% |
  | 最近一对中心距 | 中位 0.079 | ≥ 0.12（中位 0.127） |
  | 6 块全部参与 | 17.0% | **100%** |
  | 目标回原位 | 35.7% | 16.3%（≈1/6） |
  | 目标移动次数 | 5.8 | 4.91，且 P(≤2) = 0 |
  | 单局同一对最多重复 | 5.77 | 2.92 |
  | 不同对的个数 | 2.84 | 5.62 |
  | D5 拒绝 | 演示期约 35～45% | reset 期 8.4%（抽签时重抽，代价低）；运行时残余 0.00%（目标落放偏移 ≤ 12 mm），偏移 ≤ 20 mm 时 0.27% |

  最小替代方案（只加间距与全员发起，搭档仍运行时最近邻）：全员参与 100%、D5 3.3%，但目标回原位 37.2%、同一对最多重复 3.38 次。
- ⚠ 规划出的路径更长（均值 0.19 m，最大约 0.30 m，V4 约 0.12～0.16 m），窗口固定 50 步，方块移动速度快到约 1.5 倍，要人工看片。
- ⚠ `_resolve_sampling_config` 对 native 的 `object_selection` / `swap_selection` 的 JSON 全等检查**不改**；新规则全部挂 `decision.xhard`，
  xhard 代码不再读 native 的 `swap_remaining_count` 与 `position_axes`。
- ⚠ **完整方案没有在模拟器里跑过**，只跑过最小方案（3 个 seed：1 成功，2 次 D5 拒绝都被离线预测到）。
- 验收：`VR_MIN_CENTER_DIST=PASS min_d>=0.120`；`VR_ALL_CUBES_SWAP=PASS min_participants=6`；`VR_PLAN_D5=PASS rejected=0`；
  `VR_RNG_ORDER=PASS`；`VR_DEMO_D5=REPORT d5_rejected=k`。

### 2.16 PickHighlight / VideoPlaceButton / VideoPlaceOrder（只修障碍框缺陷，L2 b）

**要做**：xhard 分支里已放方块作障碍时改用精确 OBB；其他一个数都不动。

| 字段 | 含义 | V4 xhard 现值 | V5 新值 / 注入什么 |
|---|---|---|---|
| xhard 分支的方块障碍（`_load_scene` 里调 `spawn_random_cube` / `spawn_random_target` 的 `avoid`） | 已放方块如何进 `avoid` | actor 本身（约 2/3 退化成线段，`min_gap` 在其法向失效） | `cube_obb2d_exact` 预制三元组（2.0①）；名义间距真正生效；这三个环境随其他环境一起重抽进 `v5-01` |

**实施要点**

- PickHighlight 用 1 处、VideoPlaceButton / VideoPlaceOrder 各 4 处 `spawn_random_*` 调用，逐处核对 xhard 分支的 `avoid` 传入。
- 这三个环境的 clutter 密度没有重新评估过（原盲区），修完后要在正式生成里看 reset 成功率有无变化并如实报告。
- 原三档的调用逐字不动（H2）。

### 2.17 布局简图（V5 改动后）

**记号**：俯视，**横轴 y、纵轴 x**，机器人在下方（x ≈ −0.615）。`▒` 原区域（不动），`░` V5 新增或改变的区域，`▣` 容器，`●` 方块。

#### VideoUnmask / ButtonUnmask：贴身环带（与 V4 外环对比）

```text
              -0.45  -0.33 -0.24  -0.2          0          +0.2  +0.24 +0.33  +0.45
   x=+0.45  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┐  V4 外环外界 0.45（作废）
   x=+0.33  │      ┌──────────────────────────────────────────────────┐      │  V5 中心带外界 0.3289
            │      │ ░░░░ ▣ ░░░░░ ▣ ░░░░░ ▣ ░░░░ ▣ ░░░░░ ▣ ░░░░░░░ │      │
   x=+0.24  │      │ ░░ ┌──────────────────────────────────────┐ ░░ │      │  V5 中心带内界 0.2425
   x=+0.2   │      │ ▣░ │ ▒ 现生成区 [-0.2,0.2]²：8 个内环容器 ▒  │ ░▣ │      │
   x= 0     │      │ ░░ │ ▒      ▣   ▣      ▣    ▣   ▣   ▣   ▒  │ ░░ │      │
   x=-0.2   │      │ ▣░ │ ▒  (BU 的按钮在 x≈-0.2 的一侧)      ▒  │ ░▣ │      │
   x=-0.24  │      │ ░░ └──────────────────────────────────────┘ ░░ │      │
   x=-0.33  │      │ ░░░░ ▣ ░░░░░ ▣ ░░░░░ ▣ ░░░░ ▣ ░░░░░ ▣ ░░░░░░░ │      │
            │      └──────────────────────────────────────────────────┘      │
   x=-0.45  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┘
   VU 15 个（7～8 个含 cube）／BU 14 个（7 个含 cube）；四角中靠相机一侧（+x）只有 29～44% 可见，由精确判据自动排除
   V4：3 个散落在 [0.2675, 0.45] 的大方环里，密度 6.2 个/m²；V5：约 50 个/m²，与内部相同
```

#### ButtonUnmaskSwap：按钮算进内部后的矩形带（**已被 L16 (b) 作废**，仅留作记录；实际沿用 V4 环带放 10 个，形状同 V4 计划 2.21 的外环图）

```text
           y=-0.30        -0.17                        +0.27        +0.40
   x=+0.30  ┌──────────────────────────────────────────────────────┐
            │ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░ │  带宽：离内部矩形 Chebyshev 距离 [0.0425, 0.1289]
   x=+0.17  │ ░░ ┌──────────────────────────────────────────┐ ░░░ │
            │ ▣░ │ ▒ 4 个锚点框（偏 +y，不旋转）▒            │ ░▣░ │
   x= 0     │ ░░ │ ▒      ▣      ▣                         │ ░░░ │
            │ ▣░ │ ⊕按钮1(-0.2,-0.1)   ⊕按钮2(-0.2,+0.1)    │ ░▣░ │
   x=-0.26  │ ░░ └──────────────────────────────────────────┘ ░░░ │  内部矩形 x∈[-0.2625,0.17]、y∈[-0.17,0.27]
   x=-0.39  │ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░░ ▣ ░░ │  远侧落在机器人与按钮之间：按按钮时手臂会经过附近
            └──────────────────────────────────────────────────────┘
   16 个（8 个含 cube）；每个内环窗口同时有一对外环容器沿 ±0.07 的车道对换（2.5）
```

#### MoveCube：桌面中心 R = 0.05 圆形共同禁区

```text
                 -0.3   -0.2   -0.1    0.0   +0.1   +0.2   +0.3
   x=+0.15 │           ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒           │ ▒ = demo goal 区（半宽 0.11，不动）
   x=+0.05 │  ═══      ▒▒▒▒▒▒▒▒░░░░░░▒▒▒▒▒▒▒      ═══    │ ═ = 杆（根 x∈±0.05，y∈±[0.15,0.25]），杆身最近只到 y=0.05
   x= 0.0  │           ▒▒▒▒▒▒▒░░ 禁区 ░░▒▒▒▒▒▒▒           │ ░ = 圆心 (0,0)、R 0.05 的圆：goal/方块中心不得进入
   x=-0.05 │  ═══      ▒▒▒▒▒▒▒▒░░░░░░▒▒▒▒▒▒▒      ═══    │ exec goal 区半宽 0.06 ⇒ 55% 抽样落进禁区被拒
   x=-0.15 │           ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒           │ 方块候选区半宽 0.10 ⇒ 20% 被拒
   corner_bias 删除；三个物体同一个圆、同一条按中心判的规则
```

#### PickXtimes：3 个有色方块各占一个象限，6 块两两 ≥ 8 cm

```text
                 y=-0.18                 0                  +0.18
   x=+0.08   ┌──────────────────────────┬──────────────────────────┐
             │ ●红（被推到角）            │             ●蓝（被推到角） │  象限以 (-0.1, 0) 划分；corner_bias 0.5 保留
             │          ◇青              │      ◇品红                │  ◇ = 干扰，均匀抽
   x=-0.10   ├──────────────────────────┼──────────────────────────┤
             │  ◇黄      ◯圆盘可在中间    │                          │
             │ ⊕按钮                     │               ●绿（第三象限）│  V4：44.5% 的局有 2 块挤在同一角格 → V5：0
   x=-0.28   └──────────────────────────┴──────────────────────────┘
```

#### 布局**不变**、只改规则的环境

| 环境 | 说明 |
|---|---|
| VideoUnmaskSwap / ButtonUnmaskSwap | 内环锚点框不动；干扰容器环带沿用 V4 `[0.2675, 0.45]`（L16 b），只从 3 个加到 10 个并加外环交换 |
| InsertPeg | 杆区 `x∈[-0.2,0.2]、y∈[-0.3,0.3]`、孔板 xy ±0.1 都不动；只把第 4 根从「贴近目标杆的圆环带」改成与其他三根同一采样器 |
| PatternLock / RouteStick | 5×5 网格与 1×9 网格都不动（用户 L35）；只把节点数 / 段数拉到现布局允许的最长 |
| BinFill / SwingXtimes / VideoRepick | 区域与按钮不动（L51）；只加间距规则、精确障碍框与颜色/发起者规则 |

## 三、改完怎么对拍

按用户 2026-09-24 的决定（口径 11～13），V5 只做**一次对拍**加**一次生成**，V4 那套六条判据与 V5 原拟的逐环境闸门、副本对齐、
两遍重放、组合覆盖、推理链路全部**不跑**。剩下的验证分三层：静态检查、轻量测试、一次 V1 对拍；生成本身只出报告。

### 3.1 链路与哪几跳改数

链路沿用 V4 的抽签 → 冻结 → 实跑，但**合并成一次多 worker 运行**，去掉第二遍与推理：

| 跳 | 产物 | 规模 / 形状 | V5 改动 | 这一跳改不改数 |
|---|---|---|---|---|
| ① 快照 | `scripts/configs/newtask-v5/sampling_config.json`（16 任务 `{decision, native}`） | 一份 JSON，内嵌进规格 header | 15 个环境的 `decision.xhard` 键形状改变；原三档部分逐字不变（V0） | 改（只改 xhard 键） |
| ② 抽签 | `artifacts/newtask-v5/v5-01/draft/drafts.jsonl` | 每环境攒 10 条 reset 成功、最多 30 次，**多 worker** | xhard 取值改变（值、个数、次序），新增规格字段见各表；reset 拒绝率上升（VideoRepick 约 8.4%、SwingXtimes 约 3.6%、PickXtimes 约 1%、Swap 两环境 1.3～10.7% 加外环重抽） | 改 |
| ③ 冻结 | `scripts/configs/newtask-v5/v5-01/specs.jsonl` | 160 行，48 条 selected | 代码只做参数化；键集按新 schema 精确比对 | 不改（沿用封套契约） |
| ④ 实跑 | `artifacts/newtask-v5/v5-01/rollout/run1/` | 48 条加 H4 递补，**只跑一遍**，多 worker，保存 h5 与视频 | Swap 两环境的 `step` 多一条外环交换循环（不增加步数）；VideoRepick 用预规划的搭档；PatternLock/RouteStick 每局帧数约增 40～50% | 改（演示内容变化） |

②③④ 由一条命令串起来（`v4_specs draw` → `freeze` → `v4_rollout run`），中间不停下来做任何比对。

### 3.2 验收判据

| 判据 | 查什么 / 怎么查 | 为什么能成立 | 判定行 |
|---|---|---|---|
| V0 | 静态 `git diff`：`config_easy/medium/hard`，以及原三档消费的 `NATIVE_SAMPLING` 键；另对剥掉 xhard 的 decision 跑 `assert_native_decision` | V5 的改动只许落在 `decision.xhard` 或 xhard 分支，这些块里出现任何 diff 都直接违反 H2/N12 | `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0` |
| LIGHTWEIGHT | `tests/lightweight/` 全量（≤5 分钟），失败集合与 S0 存档的基线相同；各环境「验收」行里的判定项在这里落成单测或单次 reset 检查（纯函数：`cube_obb2d_exact` 无退化、`footprint_gap` 严格、`check_multi_swap_sweep` 单对等价、Unmask 密度推导锁定；单次 reset：InsertPeg 间隔、MoveCube 中心区、VideoRepick 最小距、Unmask 环带内与可见） | 这些是几何保证的直接编码，一次 reset 就能量到，不需要跑完整局 | `LIGHTWEIGHT=PASS failure_set_equal_baseline=1` |
| **V1（唯一的对拍）** | 原三档回归：**16 任务 × 3 局**（按「旧的 16×3」理解为 easy/medium/hard 各 1 局；若用户指其他口径以用户为准），本机、单 worker、相近负载，用**最原始基线**与 V5 代码各跑一遍，HDF5 逐位比（`compare_h5_pair`：先整文件 SHA-256，不同再逐路径比 dtype/shape/attribute/`tobytes()`，不设容差）。V4 的 V1 基线 h5 已在 12.95 清理，基线侧要重新生成 | 硬闸门（N4）。它同时覆盖 L4 (b) 加在共用函数上的每个新参数、SwingXtimes 共用循环的分支、AST 锁定循环之外的新代码：任何一处泄漏到原三档都会在这里逐位暴露 | `NATIVE_REGRESSION=PASS compared=48 sha_equal=48 field_mismatch=0` |
| FROZEN_FILES | `git diff --quiet` 录像器；`scripts/evaluation.py` 与官方副本 diff；`ls -1 scripts/*.py` 恰好五个 | N2，以及不得通过挪动评估预算常量来吸收变长的局 | `RECORDER_FROZEN=PASS EVAL_PY_UPSTREAM=PASS ENTRIES=5` |
| 生成报告（不设门槛） | 一次运行的结果：每环境 `draft_attempted / draft_ok / candidate_shortfall`；实跑 `rollout_attempted / rollout_ok / backfilled / selected_shortfall / by_class`；PatternLock/RouteStick 每局 `is_video_demo` 帧数是否落在 750～1050；Swap 两环境每局外环交换窗口数是否等于 n_swaps 与 BinCollisionError 计数；VideoRepick 每局参与交换的方块数 | 新值局没有官方原版可比，只能如实报告；某环境攒不够 10 条候选或 3 条正式局、某项几何保证在实跑里被违反，都回报用户 | `V5_GENERATION=REPORT tasks=16 draft_ok=… rollout_ok=… backfilled=… selected_shortfall=… demo_frames_out_of_band=… outer_swap_mismatch=… bin_collision=… vr_min_participants=…` |

**不再跑的**（用户 2026-09-24 决定）：V2 两遍重放、V3g 规格绑定与反例、V6 组合覆盖、V5e 推理链路、RESET_REGRESSION 探针、
`V5_REPLICA_PARITY`、`V5_UNTOUCHED_XHARD_PARITY`、`V5_UNMASK_INNER_PARITY`、`V5_SWAP_JOINT_FEASIBILITY` 的实现后复跑、以及所有
以 v4-01 为对照的比较。第二节各表末尾「验收」行里带这些名字的判定项，按 LIGHTWEIGHT 一行的口径降级为单测或单次 reset 检查。

两条纪律：

1. **V1 是唯一硬闸门。** 不通过说明为了做新值把原路径改坏了，必须停下修。
2. **生成报告不设门槛，但要如实。** 成功率下降是预期结果，由用户看完数字再决定要不要回调难度；攒不够就记 shortfall，不降难度去凑。

### 3.3 实施步骤

从易到难排序；**每组合并后只跑 V0 与轻量测试**，不再跑 reset 探针；V1 放在收尾一次跑完。

| 步 | 内容 | 闸门 |
|---|---|---|
| S0 | 用户答复 L6～L51，写回 1.4；存档轻量测试失败集合基线 | 决策齐备 |
| S1 | 离线复核（纯 CPU，不改代码，**不是对拍**）：用最终定数重跑 2.2×2.5 的联合可行性（≥ 300 布局/环境）与各环境 MC；有数字不达标就停下回报 | 各环境的放置 MC；`V5_SWAP_JOINT_FEASIBILITY` 的离线版 |
| S2 | 共用基础设施，只加不改（2.0）：`utils/xhard.py` 新纯函数、`check_multi_swap_sweep` 与预筛、共用采样函数的各环境显式参数（L4 b）、7 个环境的 K2 别名、xhard 专用停放 helper；**还不接入任何环境** | V0；LIGHTWEIGHT（含每个新参数的「默认值下逐位不变」单测） |
| S3a | PatternLock（2.10）加 RouteStick（2.11） | V0；LIGHTWEIGHT；本机 oracle 探针 ≥ 3 seed |
| S3b | VideoUnmask 与 ButtonUnmask（2.3 / 2.4） | V0；LIGHTWEIGHT；每环境 2 局本机演示 |
| S3c | MoveCube（2.9） | V0；LIGHTWEIGHT |
| S3d | InsertPeg（2.8） | V0；LIGHTWEIGHT |
| S3e | BinFill（2.12） | V0；LIGHTWEIGHT |
| S3f | PickXtimes 加 SwingXtimes（2.13 / 2.14） | V0；LIGHTWEIGHT |
| S3g | VideoRepick（2.15） | V0；LIGHTWEIGHT（含 AST 锁测试） |
| S3h | VideoUnmaskSwap 加 ButtonUnmaskSwap（2.6 / 2.7） | V0；LIGHTWEIGHT（含 AST 锁与 swap 测试） |
| S3i | PickHighlight / VideoPlaceButton / VideoPlaceOrder 的障碍框修复，StopCube 的异常类（2.16 / 2.0③） | V0；LIGHTWEIGHT |
| S4 | 一次性重导 `scripts/configs/newtask-v5/sampling_config.json`，跑消费审计；README 补 V5 节 | `SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0`；V0 |
| S5 | **V1**：基线侧与 V5 侧各生成 16×3 原三档局，逐位比 | `NATIVE_REGRESSION=PASS compared=48 sha_equal=48 field_mismatch=0` |
| S6 | **一次多 worker 生成**：抽 10 候选 → 冻结 `v5-01` → 实跑 48 条（含 H4 递补），保存 h5 与视频；出生成报告 | `V5_GENERATION=REPORT …`；FROZEN_FILES |
| S7 | 留档与提交：`docs/validation/newtask-v5/` 逐步报告 + 总报告；本节 3.4 追加实测 | 每步 md 报告齐备 |

**测试预算**沿用 V4：每次提交前在 5 分钟内跑 `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q`，
失败集合须与 S0 存档的基线相同。长任务一律用 detached tmux（第二部分三）。

### 3.4 实施后实测结果

（实施完成后在此追加，原计划不改写。）

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

以下编号可被正文引用；与 [AGENTS.md](AGENTS.md) 的强制规则冲突时，以 AGENTS.md 为准。**V4 的 N1～N12 全部延续**：N1 改动须留证，
报告落 `docs/validation/newtask-v5/`；N2 录像器冻结；N3 不自填；N4 原值路径不许改坏；N5 按 L1 的答复读；N6 甲的产物只读；
N7～N10、N11 传入即可生成；N12 既有缺陷只在 xhard 修。V5 新增：

- **N13 共用代码只加不改。** `utils/object_generation.py::_trimesh_box_to_obb2d` / `_safe_unit`、`utils/statechange.py`
  （`swap_flat_two_lane`、`lift_and_drop_*`）、`utils/bin_collision.py::check_swap_sweep` 的判定，以及 `spawn_random_bin` 都不得改语义。
  新能力一律通过默认关闭的参数或新函数引入。
- **N14 AST 锁定循环不动。** `test_real_swap_resolution_matches_baseline_and_preserves_ties` 抽取的 `for i in range(len(self.swap_schedule))`
  循环不得插入外环逻辑；`_spawn_xhard_distractors` 必须仍是 `_load_scene` 的最后一句；`generate_dataset_newseed._require_ast` 检查的表达式不得变。
- **N15 V4 作废但不删。** `scripts/configs/newtask-v4/**`、`artifacts/newtask-v4/**` 原样留在 Git，不再被任何 V5 代码或判据引用；不做版本门、不打 tag（L5）。
- **N16 规划期数字只是规划期数字。** 本计划的统计数字多数来自离线副本，V5 不再用副本对齐重证；写报告时一律标明「规划期离线估计」，不得写成验收结论；验收结论只来自 V1 与那一次生成的报告。
- **N17 回放必须复核。** 凡是新增了几何保证的环境（InsertPeg 间隔、MoveCube 中心区、VideoRepick 最小距），回放冻结规格时都要重查规则，
  违反即报错或记入 mismatch。原因是 `SpecRecorder.value` 回放时直接返回冻结值、不复核。
- **N19 只做一次对拍、一次生成（口径 11～13）。** 除 V0、轻量测试、V1、FROZEN_FILES 与生成报告外，不新增任何需要完整跑局的比对；实施方不得以「顺手」为由复活 V2 / V3g / V6 / V5e。
- **N18 拒绝循环里的记录纪律。** 带整段重抽的采样器（Unmask 外环、BinFill 配色）只在被接受的那次调用 `recorder.value`，尝试次数与配对用 `record()` 留痕。

## 一、按阶段、按文件的逐项改动清单

**这是待实施清单，不是修改记录。** 每步动手前把该步实际涉及的函数与改法列出来，与报告一并留证。
**关闭态**指 easy/medium/hard 与 4 个未动环境的 xhard 在 V5 代码下的行为，必须与 `0baff09` 逐位相同。

| 阶段 | 文件 / 锚点 | 拟改什么、为什么 | 关闭态 | 开启态（xhard） |
|---|---|---|---|---|
| S2 | `utils/object_generation.py::spawn_random_cube`、`spawn_random_target` | 按 L4 (b) 各加显式可选参数（`center_zone_half`、`min_center_dist`、`quadrant_of` 等，名字以实现为准）：在 OBB/圆判据之后、`recorder.value` 之前求值，为真即 continue；不抽随机数 | 每个参数 `None` 时不执行任何新增语句，各配一条逐位不变单测 | 各环境按需传入 |
| S2 | `utils/xhard.py` | 新增 `cube_obb2d_exact(pose, half) -> (c, A, h)`；`footprint_gap(rect_a, rect_b)`（有向矩形精确距离，重叠为 0）；`center_zone_half(area_ratio, half)`；`balanced_color_cycle(order, n)`；`max_same_color_component(xy, colors, link)`；各配单测 | 纯函数，不被原三档调用 | 被各环境 xhard 分支调用 |
| S2 | `utils/bin_collision.py` | 新增 `check_multi_swap_sweep(pairs, bystanders)`：对每对自身、跨对的移动者两两、移动者对静止物，复用 `_prove_pair`；新增认证预筛（401 个 s 采样，并以 Lipschitz 界证明分离），只在新函数与显式开关的包装里使用 | `check_swap_sweep` 判定不变 | Swap 两环境与 VideoRepick 的规划期/运行时用 |
| S2 | VideoRepick、SwingXtimes、PatternLock、RouteStick、StopCube、VUS、BUS 七个模块头部 | 仿 `VideoPlaceOrder.py` 加 `_RealSceneGenerationError` 别名；raise 与 except 两处按 `difficulty == "xhard"` 选类（L3） | 原三档仍是 TypeError（H2） | 抛真 `SceneGenerationError` |
| S2 | `utils/unmask_distractors.py` | 新增 xhard 专用停放 helper（L14）：每个物体一个画面外停放点，窗口与落回步不变 | 原三档不进此模块 | 2.3 / 2.4 / 2.6 / 2.7 |
| S3a | `PatternLock.py::config_xhard`、`_native_decision`、`_load_scene` | `length [24,25]`；xhard 的 `max_attempts` 20000（decision 键冻进 header）；`for … else` 分支在 xhard 下抛真异常；网格与间距不动 | 1000 次、静默兜底都不变 | 2.10 |
| S3a | `RouteStick.py::config_xhard`、`_native_decision` / `_resolve_sampling_config` | `length [15,21]`；新增 xhard 的 L 范围 decision 键，由 header 冻结 | 原三档不变 | 2.11 |
| S3b | `VideoUnmask.py` / `ButtonUnmask.py::XHARD_DISTRACTOR`；`unmask_distractors.py::spawn_ring_distractor_bins` | 配置改为 15 / 14 个、环带 `[0.2425,0.3289]`、cube `[7,8]` / `[7,7]`、`color_rule balanced_cycle`、`max_trials 1024`；校验改为 `0≤lo≤hi≤count`；`reveal_distractor_bins` 接入停放 helper | 原三档不进此模块 | 2.3 / 2.4 |
| S3c | `MoveCube.py::config_xhard`、`_native_decision`、`_load_scene`（杆抖动、goal、`_sample_cube_center`、`cube_2` 生成）、`_xhard_corner_bias`（或新的校验器） | 按 2.9 的伪码；删掉 `corner_bias` 键与 MoveCube 内全部消费点（L33）；桌面中心 R=0.05 圆 `center_exclusion`，按物体中心判；执行段 `include_existing=False` | 原三档 27 次抽样的路径不变（原三档本来就不传 corner_bias） | 2.9 |
| S3d | `InsertPeg.py::config_xhard`、`_initialize_episode`，新增 `_xhard_sample_pegs`，删除 `_xhard_place_near_target_peg` | 按 2.8 的伪码；新记录与回放守卫 | 原生循环逐字不动 | 2.8 |
| S3e | `BinFill.py::_load_scene`（xhard clutter 分支）、`_resolve_sampling_config`，新增 `decision.configs.xhard.color_mix` 与 `cube_obstacle_obb` | 槽位 → 配色 → `spawn_random_cube(fixed_xy, fixed_yaw)` 建 actor；配色重排只在末尾追加 `randperm(12)` | `native_dynamic` 分支不动 | 2.12 |
| S3f | `PickXtimes.py::XHARD_DECISION`、`_spawn_scene_objects_xhard`、`_spawn_distractors_xhard`；`SwingXtimes.py::XHARD_DECISION`、`_load_scene` 有色方块循环、`_spawn_distractors_xhard` | 象限与 8 cm 规则经 `extra_reject`；放下的方块用 `cube_obb2d_exact` 作障碍；`max_trials` 1024（Pick）；新记录 `layout.cube_dispersion`、`layout.cube_min_center_dist` | `_spawn_scene_objects_native` 不动；Swing 共用循环的非 xhard 一支逐字保留 | 2.13 / 2.14 |
| S3g | `VideoRepick.py::config_xhard`、`_native_decision`、`_load_cubes_xhard`，新增 `_plan_swaps_xhard`，`step`（`if pair_idx2 is None` 内的 xhard 分支，并用 getattr 取默认值） | 按 2.15 的伪码；新规格路径 `objects.swap_partner_u`、reset 时写入的 `actions.swap_pairs.<k>`；`swap_initiators_remaining` 变为长度 5 | `NATIVE_SAMPLING` 与 JSON 全等守卫都不动 | 2.15 |
| S3h | `unmask_swap_xhard.py`（统一采样器、`plan_distractor_swaps`、带序号命名、`cube_bins`）；`VideoUnmaskSwap.py` / `ButtonUnmaskSwap.py::_spawn_xhard_distractors`、`_check_swap_sweep_from_actual`、`step`（锁定循环之外的两条新循环）、`_native_decision`；`ButtonUnmaskSwap._load_scene` 的截断修复 | 按 2.5 的伪码 | AST 锁绿；原三档不进 xhard 分支 | 2.6 / 2.7 |
| S3i | `PickHighlight.py` / `VideoPlaceButton.py` / `VideoPlaceOrder.py` 的 `_load_scene` xhard 分支 | 方块障碍改用 `cube_obb2d_exact` 预制三元组（L2 b） | 原三档调用逐字不动 | 2.16 |
| S4 | `scripts/configs/newtask-v5/sampling_config.json`（新建）；`scripts/README.md` 的 V5 节 | 一次性重导；消费审计；不再生成 `combos.json` | V4 的配置目录原样留着不引用 | — |
| S5～S6 | `scripts/parity/v4_specs.py`、`v4_rollout.py`、`v4_demo_probe.py`、`train_split_parity.py` | 以新参数（配置目录、run id）支持 V5，默认值不变；`draw → freeze → run` 串成一条多 worker 命令；V1 用 `train_split_parity` 的既有比较器跑 16×3；`v4_combos.py`、`v4_reset_probe.py`、`scripts/eval/v4_eval.py` 在 V5 不用、不改（**不在 `scripts/` 顶层新增文件**） | V4 命令照旧 | V5 用新参数 |
| 全程 | `tests/lightweight/test_v4_xhard_{videounmask_buttonunmask,unmaskswap,insertpeg,movecube,videorepick,pickxtimes,swingxtimes,binfill}.py`、`test_swap_schedule_generic.py`、`test_window_timeline.py`、`test_v4_xhard_unmask_distractor_reveal.py`、`test_bin_collision.py`、`test_TaskGoal.py`（若 Unmask 文本受影响） | 断言改为 V5 语义；第二节各表「验收」行的判定项落成单测或单次 reset 检查（3.2 LIGHTWEIGHT）；`test_real_swap_resolution_matches_baseline_and_preserves_ties` 必须保持绿 | 原三档断言不放宽 | — |

## 二、对拍闸门总表

| 闸门 | 前置条件 | 判定行 |
|---|---|---|
| V0 | 无（静态，每步收尾都跑） | `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0` |
| LIGHTWEIGHT | 每次提交前；S0 已存档基线失败集合 | `LIGHTWEIGHT=PASS failure_set_equal_baseline=1` |
| SAMPLING_SNAPSHOT | S4 | `SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0` |
| V1（唯一对拍） | S5；基线侧与 V5 侧同机、单 worker、相近负载 | `NATIVE_REGRESSION=PASS compared=48 sha_equal=48 field_mismatch=0` |
| FROZEN_FILES | 每次提交前 | `RECORDER_FROZEN=PASS EVAL_PY_UPSTREAM=PASS ENTRIES=5` |
| 生成报告 | S6 一次运行完成 | `V5_GENERATION=REPORT tasks=16 draft_ok=… rollout_ok=… backfilled=… selected_shortfall=… demo_frames_out_of_band=… outer_swap_mismatch=… bin_collision=… vr_min_participants=…`（不设门槛，N10） |

比较器复用 `scripts/parity/train_split_parity.py::compare_h5_pair`（先比整文件 SHA-256，不同再逐路径比），V4 已在外层加了根属性与空文件前置检查，照用。

## 三、runbook

```bash
# 只读核验：录像器未改、五入口未增
git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py && echo RECORDER_FROZEN=PASS
ls -1 scripts/*.py    # 应恰好五个

# 每次提交前（≤5 分钟）
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q

# 单环境演示探针（本机，≤5 分钟一条命令；S3 各步用）
CUDA_VISIBLE_DEVICES=0 timeout 290 uv run --no-sync python -m scripts.parity.v4_demo_probe --task MoveCube --n 4 \
  --sampling-config <v5 单任务配置> --out artifacts/newtask-v5/demo-probe/<name>

# V1：原三档 16×3 与最原始基线逐位比（S5；基线侧在基线提交的工作树里跑同一命令，单 worker）
tmux new-session -d -s v5-v1 \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.train_split_parity run \
   --subset 16x3 --workers 1 --output artifacts/newtask-v5/v1/<side> 2>&1 | tee artifacts/logs/v5-v1-<side>.log; \
   echo \"EXIT_CODE=\$?\" >> artifacts/logs/v5-v1-<side>.log"
uv run --no-sync python -m scripts.parity.train_split_parity compare artifacts/newtask-v5/v1/base artifacts/newtask-v5/v1/v5

# 一次多 worker 生成：抽 10 候选 → 冻结 → 实跑 48 条（S6；参数名以 S4 参数化后的实现为准）
tmux new-session -d -s v5-gen \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.v4_specs draw --run-id v5-01 \
   --sampling-config scripts/configs/newtask-v5/sampling_config.json --candidates-per-env 10 --max-reset-attempts 30 --workers <n> \
   --out artifacts/newtask-v5/v5-01/draft/drafts.jsonl \
   && uv run --no-sync python -m scripts.parity.v4_specs freeze --drafts artifacts/newtask-v5/v5-01/draft/drafts.jsonl \
   --sampling-config scripts/configs/newtask-v5/sampling_config.json --out scripts/configs/newtask-v5/v5-01/specs.jsonl \
   && uv run --no-sync python -m scripts.parity.v4_rollout run --specs scripts/configs/newtask-v5/v5-01/specs.jsonl --label run1 \
   --official-root artifacts/train-parity/local-smoke-01/official-src --workers <n> --output artifacts/newtask-v5/v5-01/rollout \
   2>&1 | tee artifacts/logs/v5-gen-v5-01.log; echo \"EXIT_CODE=\$?\" >> artifacts/logs/v5-gen-v5-01.log"
```

等待 tmux 任务一律挂 Monitor 在日志上，按 CLAUDE.md 的写法过滤 `EXIT_CODE=|Error|Traceback`，管道各级都要行缓冲，不得用 sleep 轮询。
不跑第二遍、不跑 compare、不跑 V6、不跑推理。

## 四、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | 大多数推荐设计的**演示级成功率没测**（InsertPeg 只到 reset 与静置；BinFill、Pick/Swing 只有副本；VideoRepick 只跑过最小方案 3 个 seed；外环交换 0 局演示；PatternLock 6×6 只有 3 个 seed），且 V6 已不跑 | S3 各步先跑本机演示探针；正式那一次生成的 shortfall 与 by_class 如实回报用户，由用户决定是否回调 |
| 2 | 贴身环带加 15/16 个干扰加外环交换，其联合可行性只做过圆近似的试算；首选发起者仅 44% / 29% 可行，回退很多，对布局分布的偏置未刻画 | S1 离线版 `V5_SWAP_JOINT_FEASIBILITY`（纯 CPU）；在规格里记录回退次数与重抽次数；正式生成里 Swap 两环境攒不够 10 条就回到 L16 |
| 3 | 停放点堆叠：揭示段 22～24 个容器，交换段最多 11 个 cube，都在 (10,10,10) 停数百步；物理稳定性只测了 9 局揭示段 | L14 的独立停放点；`V5_UNMASK_REVEAL` 报告 |
| 4 | Swap 两环境 reset 墙钟上升（不加预筛 33～66 s）；抽签最多 30 次，V6 被放大 | L23 认证预筛（判定不变）；`V5_UNMASK_RESET_TIME=REPORT` |
| 5 | 共用函数按 L4 (b) 加多个参数，或 SwingXtimes 共用循环加分支，泄漏到原三档 | N13；每个参数默认惰性并配逐位不变单测；V1 唯一硬闸 |
| 6 | AST 锁、末句约束被新代码破坏 | N14；每次提交跑对应测试 |
| 7 | 回放不复核规则，使旧规格悄悄带回重叠或中心布局 | N17 回放守卫；V4 快照被形状检查拒绝（V4 已作废，不做兼容） |
| 8 | 多个环境的 reset 拒绝率同时上升，逼近「10 条成功、上限 30 次」 | 各环境都估计了尝试次数（VideoRepick 约 11 次得 10 条）；FREEZE 如实报 `candidate_shortfall` |
| 9 | RouteStick 的执行段用掉 1301 步预算的最多 81%，学习策略余量变小 | 上界不取到实测最大（L=21 而非 26）；报告逐局执行帧与预算；`evaluation.py` 不改 |
| 10 | PatternLock 不改布局时演示上限约 27.4 s，到不了 30 s；25 节点依赖 20000 次搜索预算，reset 墙钟增加未实测 | 用户已接受「尽可能长」；S1 实测搜索耗时并记录 |
| 11 | VideoRepick 规划路径更长，窗口固定 50 步，方块移动速度快到约 1.5 倍 | k = 2 而不是「任一可行」；可选路径上限 0.25 m；冻结前人工看片 |
| 12 | 画面与机型：所有模拟器证据来自本机 sm_89，且负载时高时低（load 35～600），墙钟数字只作参考 | 沿用 K4/K5；时间类指标一律只报告、不设闸 |
| 13 | PickXtimes 的位置捷径：候选块在角、干扰块在中间 | 列为用户可另行决策的事项；V5 不默认处理 |
| 14 | V4 推理与 V4 规格在 V5 代码上不可回放 | N15：V4 作废，接受不可回放；产物留在 Git 不删 |
| 15 | 只跑一遍、不做 V2，可重放性（同规格两次一致）在 V5 无证据；多 worker 下 mplib RRT 墙钟预算会让同一规格搜出不同路径（V3/V4 已证实） | 用户决定接受（口径 12）；报告里注明 v5-01 的 h5 是单次产物 |

## 五、盲区诚实清单

- **演示级**：见风险 1。本计划里的成功率都是本机小样本或离线推断，没有一条是判据级结果。
- **离线副本**：所有副本都在 V4 规则下与冻结规格逐位一致，但 V5 规则的副本是否等于 V5 实现**不再验证**（N16），本计划里的可行性 / 均匀性数字只能当规划期估计。
- **不做 V2 / V3g / V6 / V5e**：可重放性、规格真被消费、组合可生成性、推理链路在 V5 都没有证据，是用户明确放弃的。
- **障碍框退化率随数值路径变化**：float32 路径 66%，float64 为 49.8%，真实模拟器 5/11。Unmask 内环 `spawn_random_bin` 的容器 OBB 是否也退化，没有查过。
- **K2 遮蔽的路径**：汇总方只对 MoveCube（类）实际强制抛过一次；VideoRepick、SwingXtimes、PatternLock、Swap 两环境的 TypeError 路径是根据代码推断的。
- **按钮与手臂**：两者都不在碰撞模型里。BUS 在交换期间按按钮的风险，只用中心距阈值近似。
- **「扎堆」的主观性**：扎堆与均匀用的是代理指标（同角格、最近邻、连通团、覆盖半径、分侧计数），人眼观感只看了少量帧。
- **ButtonUnmask 的 14 个**：汇总方没有独立复算（需要按钮遮挡的期望）；BinFill 多重校正后的 4.0% 尾部、VideoRepick 在 0.12 m 下的放置率、MoveCube 的 10/10，也都没有第二方复算。
- **recovery 未建模**：I3 下 recovery 关闭，没有环境对它建模；若日后打开，Unmask 与 Pick 的 xhard 流都会移位。
- **三个只修缺陷的环境**：PickHighlight、VideoPlaceButton、VideoPlaceOrder 修完障碍框后 clutter 布局的 reset 成功率没有重新评估，只能在正式生成里看。

## 六、留档与 commit 纪律

- commit subject 沿用 `12.<n> <中文描述>`；body 按 AGENTS.md 规则 7 的六项写全，并按规则 7 只 `git add` 本轮明确路径；提交后立即 `git push`。
- 每步收尾在 `docs/validation/newtask-v5/` 出 md 报告（N1）。
- 本计划的实测结果在实施后以 3.4 子节追加，**不改写原计划**。
- 用户对 L 项的答复写回 1.4 的「结论（用户答复）」列：原问题保留，只追加结论与日期原话。
- 规划期用到的调查脚本若要转成正式闸门，须改写成中文注释后，收进 `scripts/parity/` 或 `docs/validation/newtask-v5/*-scripts/`。

## 七、规划期证据索引

全部位于 `artifacts/newtask-v5/plan-probes/`（本机留档、未进 Git；由 2026-09-24 的会话 scratchpad 复制而来，已剔除 h5/mp4/pkl 等大件）。
`out/` 存放 8 个议题与汇总方的原始结构化记录（英文内部记录，`<议题>.json` 与渲染后的 `.txt`）。

| 议题 | 目录 | 关键脚本（副本校验 → 统计 → 模拟器） |
|---|---|---|
| Unmask 环带 | `unmask_ring/` | `s1_validate_extent.py`、`s1b_swapvis.py`、`s2_area_density.py`、`s9_count_stability.py`、`s3_feasibility_vubu.py`、`s3_feasibility_swap.py`、`s3a_sweep_validate.py`、`s4_occlusion.py`、`s5_sectors_overlay.py`、`s7_spec_layouts.py`、`s6_sim_v5.py`、`s8_swap_proto.py`（带日志与 overlay 图） |
| 外环交换 | `unmask_swap/` | `m0_verify_replica.py`、`m0b_verify_ring_sampler.py`、`m0c_multi_sweep_equiv.py`、`multi_sweep.py`、`m1_inner_stats.py`、`m1c_tie.py`、`m2_outer_sim.py`、`m2b_fallback.py`、`m2c_spec_rows.py`、`m2d_where.py`、`m3_sim_probe.py`、`m4_timing.py` |
| InsertPeg | `insertpeg/` | `replicate_v4.py`、`peggeom.py`、`mc.py`、`run_mc.sh`、`finger_hazard.py`、`settle_test.py`、`v4_spec_geometry.py`、`pixel_ambiguity.py`、`v5_prototype.py` |
| MoveCube | `movecube/` | `mc_layout.py`、`validate.py`、`marginals.py`、`joint.py`、`sweep.py`、`worstcase.py`、`exec_fail.py`、`sim_verify.py`、`patch_v5.py`、`probe_v5_reset.py`、`demo_v5.py`、`hist_joint.py`、`g3_calib.py` |
| 演示时长 | `long_demo/` | `h5_segments.py`、`mp4_frames.py`、`screw_model.py`、`pl_candidates.py`、`pl_dir_stats.py`、`dfs_len_dist.py`、`singleton_hit.py`、`grid_geometry.py`、`pixel_spacing.py`、`pl_path_study.py`、`hold_calc.py`、`sim_reset_budget.py`、`sim_oracle_eval.py` |
| BinFill | `binfill_cluster/` | `binfill_sampler.py`、`verify_replication.py`、`sim_obb_probe.py`、`simulate.py`、`analyze.py`、`tailprob.py`、`v5_options.py`、`v5b_by_count.py`、`ep3_frame.py` |
| Pick/Swing | `pick_swing_cluster/` | `replica.py`、`validate_replica.py`、`obb_degen_rate.py`、`obb_check.py`、`cluster_stats.py`、`cluster_stats2.py`、`cluster_stats3.py`、`replica_v5b.py`、`spec_metrics.py`、`projection.py` |
| VideoRepick | `videorepick/` | `v4rep.py`、`validate_rep.py`、`check_rollout_pairs.py`、`button_hole.py`、`project_region.py`、`big_sim.py`、`analyze.py`、`extra_sim.py`、`specs_stats.py`、`demo_probe_log.py`、`demo_probe_v5min.py`、`perturb_check.py`、`perturb_check2.py`、`final_design_sim.py`、`final_design_sim2.py` |
| 跨议题抽查 | `synthesis/` | `sc_density.py`、`sc_obb.py`、`sc_corner.py`、`sc_peg.py`、`sc_binfill_quota.py`、`sc_demo_frames.py`、`sc_sge.py`、`sc_movecube_reset.py`、`joint_probe.py` |

这些脚本里的路径常量写的是会话 scratchpad，重跑前需要把 `<scratch>` 换成本目录。脚本注释是调查方写的英文，属于规划期的临时产物，不作为仓库文档。
