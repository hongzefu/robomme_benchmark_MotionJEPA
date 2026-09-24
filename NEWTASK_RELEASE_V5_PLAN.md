# 新值模式 V5：xhard 档去扎堆、Unmask 外环加密并随内环交换、演示时长校准

> 本方案以用户 2026-09-24 的要求为准，**只规划，不实施**。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，
> 分支 `newtaskRelease-v4`，代码锚点为本文件落盘时的 HEAD `0baff09`（12.96）。commit 编号沿用仓库现行
> `<大版本>.<小版本> <中文描述>` 体例（本文件入库为 12.97）。依赖锚点：`uv.lock` `ff0ffd847a55…` /
> `pyproject.toml` `d03537d6c77a…`。
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
> 实施后必须用闸门 `V5_REPLICA_PARITY` 重证，不能直接当验收结论。
>
> **授权边界**：本文是计划，不是实施授权，实施须用户另行批准。`src/robomme/` 的改动沿用 V4 的做法：
> 免逐项事前批准，但每步收尾必须在 `docs/validation/newtask-v5/` 出 md 报告，写明文件、锚点、改了什么、
> 为什么改、怎么验证。录像器 `src/robomme/env_record_wrapper/RecordWrapper.py` 全程冻结（V4 的
> `fail_safe_limit=5000` 保持）。1.4 的 **51 个待决项一个都不许在实施时自行取建议值**，必须先回来问用户。
>
> **简称**：VU = VideoUnmask，BU = ButtonUnmask，VUS = VideoUnmaskSwap，BUS = ButtonUnmaskSwap；
> 「内环」指原有参与揭示/交换的容器（`spawned_bins` / `bin_<i>`），「外环」「干扰容器」指 V4 新增的
> `distractor_bins`；正文里 `utils/…`、`<Env>.py` 等源码路径省略前缀 `src/robomme/robomme_env/`。

# 第一部分（给人看）

## 一、口径

**一句话方案**：在 V4 已落地的 xhard 档上做第二轮修订，原三档（easy/medium/hard）仍逐位不变。共八个议题：

1. 四个 Unmask 环境的干扰容器改成**贴着现生成范围的一圈环带**，数量**按内部密度推算**（15/14/15/16 个），一半含 cube；
2. 两个 Swap 环境的外环容器**随每一次内环交换同步交换**，搭档同样取**XY 最近邻**，并纳入**两对联合的连续碰撞证明**；
3. InsertPeg 四根杆改由**同一个采样器**生成，不给第 4 根单设约束，**两两轮廓间隔 > 3 cm**；
4. MoveCube 的**方块、目标圆盘、杆**，都拒绝落在**自身采样框的中心区**（占框面积 30%）；
5. PatternLock、RouteStick 的演示时长**校准到 30 s ± 5 s**；
6. BinFill 去掉同色扎堆；
7. PickXtimes、SwingXtimes 去掉扎堆；
8. VideoRepick 均匀摆放，**全部方块都参与交换**。

议题 6、7、8 修的是同一个**新发现的共用缺陷**：已放下的方块作障碍时，其 2D 包围框会退化成一条线段，最小间距因此失效。修完后再按各环境的具体情况去扎堆。

所有新值全部重新抽签，冻结为 `v5-01`，沿用 V4 的链路：抽签 → 冻结 → 实跑 → 推理，闸门也沿用 V4 的。

### 1.1 定死的口径

**实施中不得更改。** 每条注明依据。

| # | 口径 | 依据 |
|---|---|---|
| 1 | **只改 xhard 档**；easy/medium/hard 在定义、reset 取值、完整演示 h5 上都必须与改动前逐位相同；V1 是硬闸门 | V4 口径 7/12、H2、N4、N12 |
| 2 | **录像器冻结**；`scripts/evaluation.py`、`scripts/run_example.py`、`scripts/dataset_replay.py` 与上游逐字节相同这一性质要保住；`scripts/` 顶层只许五个入口 | V4 N2、口径 8/9；AGENTS.md 规则 11/12 |
| 3 | **改动内容以 1.2 的用户原文为准**；原文里的问句，在 1.3 给出直接回答 | 用户 2026-09-24 原文 |
| 4 | **外环交换只存在于有内环交换的两个环境**（VideoUnmaskSwap、ButtonUnmaskSwap）。**每一次**内环交换都配**恰好一次**外环交换，**同窗口同时进行**，因此不增加任何控制步 | 原话「每次内部swap 外部也swap」 |
| 5 | **外环交换规则与内环同构**：搭档是同一度量下的最近邻（XY 两轴欧氏距离），轨迹同为 `swap_flat_two_lane`（lane 0.07）；外环容器**永不与内环容器配对** | 原话「外部swap也要这样」 |
| 6 | **外环交换必须进碰撞检测**：reset 时做规划期证明，运行时从实际位姿复核 | 原话「也要支持碰撞检测」 |
| 7 | InsertPeg **四根杆走同一采样逻辑**，**第 4 根不加任何单独约束**，并**保证两两间隔** | 原话 |
| 8 | MoveCube 的**方块、目标（goal 圆盘）、杆三者都不能生成在中心**，**用直接拒绝，不用 bias** | 原话「不要以bias来设计 而是直接拒绝生成在中心区域」 |
| 9 | 演示时长目标 **25～35 s**，按录像器 30 fps 计，即 h5 中 `info/is_video_demo` 为真的帧数在 **750～1050** 之间 | 原话「30s上下浮动5s」；V4 A2 的口径延续 |
| 10 | VideoRepick **全部方块都能参与交换** | 原话「支持所有的cube都要swap」 |
| 11 | **传入即可生成**：xhard 每个声明参数的所有组合都要实测能生成，**判定以演示级为准**；任一组合生成不出来，就停下回报用户，由用户重新定参数 | V4 口径 14、N11、H3 |
| 12 | 规模、挑选与实跑纪律**全部沿用 V4**：<br>• 每环境 10 条 reset 成功候选，尝试上限 30；<br>• 按 index 0/3/6 选出正式局，全局 48 条（F1～F4）；演示失败时在这 10 条内递补（H4）；<br>• 不开 fail recover（I3）；V6 组合覆盖每组合 5 条（J8）；<br>• 48 条正式局保存视频与 h5（J9）；本机跑、允许多 worker，V2 只报告不设闸（K4/K5） | V4 1.3 |
| 13 | **V4 冻结产物只读**：`scripts/configs/newtask-v4/**`、`artifacts/newtask-v4/**` 不改不删；V5 新产物一律落新目录 | V4 N6 的同类纪律 |
| 14 | **待决项不许自填**：1.4 的 L1～L51 必须逐条问用户；实施中新发现的待决项追加进 1.4，同样先问 | V4 N3 |

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

### 1.3 用户提问的直接回答（结论先行）

| 问题 | 回答 | 详见 |
|---|---|---|
| 现在内部 swap 的机制是什么？最近 2 邻？ | **不是「最近的 2 个邻居」，而是用 x、y 两个轴量出来的最近 1 个邻居。**<br>• **发起者**：主流上抽两次，定下 3 个发起者 a、b、c，第 k 次交换用 `swap_indices[k % 3]`，固定按 a,b,c,a,b,c 轮转；4 个内环容器中恰有 1 个永不发起。<br>• **搭档**：每个窗口的第一步，按**实际位姿**取离发起者 XY 最近的另一个内环容器。比较用严格 `<`，平局取生成序靠前者。VUS 从 `swap_selection.partner.position_axes=[0,1]` 读轴，BUS 写死 `[:2]`。<br>• **死代码**：代码里唯一「取最近 2 个」的逻辑 `_compute_dynamic_swap_candidates`（`distances[:2]`）与 `_select_swap_pair_from_positions`，在 VUS、BUS、VideoRepick 三处都没有任何调用者 | 2.2 |
| insertpeg 现在怎么生成 4 个？ | • **前 3 根**：原生均匀拒绝采样，杆根离孔板 > 0.06、离已放杆根 > 0.075，最多 512 次，接受后再抽 yaw（±180°）。<br>• **中间**：抽 obj、dir。<br>• **第 4 根**：由**另一个采样器** `_xhard_place_near_target_peg` 生成，在目标杆 peg_0 周围 0.075～0.085 m 的圆环带里抽半径和方位角，最后覆盖 `peg_init_poses[3]`。<br>• **间距失效**：0.075 m 量的是**杆头中心距**，而单根杆轮廓长 0.10 m，所以这个判据挡不住穿插。V4 xhard 有 28.1% 的布局目标杆与别的杆重叠 | 2.3 |
| movecube 中心区定 30% 是否可以？ | **可以，前提是 30% 指「每个物体自身采样框面积的 30%」**，即中心正方形边长为采样框边长的 √0.3 = 0.548 倍，每次抽样恰好 30% 被拒。<br>• **可行性**：离线 2000 局全部生成成功；最坏情况预算耗尽概率 ≤ 2.5e-20；每局平均多抽约 10 个随机数。<br>• **演示**：本机 10 局演示 10/10 成功。<br>• **不宜按边长 30% 理解**：那只占面积 9%，中心区 1.5～3.9 cm，比 4 cm 的方块和 8 cm 的圆盘还小，效果是装饰性的 | 2.4 |
| PatternLock/RouteStick 长度校准到 30±5 s | **两者现在都偏短**：<br>• PatternLock ep0 演示 649 帧（21.6 s）；5×5 网格上简单路径最长 25 节点，平均够不到 25 s。<br>• RouteStick ep6 演示 600 帧（20.0 s）。<br>**改法**：<br>• RouteStick 段数 L 改为 [15,21]，每段恰好 50 帧，得 25.0～35.0 s，均值 30.0 s；<br>• PatternLock 建议改为 6×6 网格、间距 0.08（与 V4 的 5×5@0.1 物理占地相同）、节点 [30,33]，离线 300 局 100% 落带，均值 29.2 s | 2.5 |
| binfill 生成 cube 的位置均匀吗？为什么一堆红色在一起？ | **单局内均匀，跨局汇总不均匀；颜色与位置独立。**<br>• **单局**：每块在剩余空闲区域里均匀采样。<br>• **跨局**：按钮加孔板平均占去区域的 34%，各格密度在 0.65～1.38 之间。<br>**ep3 的红色成堆主要是偶然**：<br>• 12 块里有 7 块红色（出现 ≥7 的概率为 22%）；<br>• 按钮和板只留出靠机器人一侧的一条空带，红色恰好落在那里；<br>• 多重比较校正后，约 4% 的局至少有这么极端。<br>**另有真实缺陷把它压得更紧**：障碍框退化，使 red_0 与 red_2 只隔 8.4 mm，而名义最小间距是 20 mm | 2.6 |
| pickxtimes 为什么扎堆？generator 怎么定位置？有无 bias？ | **生成方式**：顺序拒绝采样，依次放按钮、目标圆盘、3 个有色方块、3 个干扰方块。<br>**有意的 bias**：`corner_push` 以 `corner_bias=0.5` 作用在**全部 3 个有色方块**上（V4 J5），每个轴单独推向两端，结果 91.3% 的有色方块落在 4 个角格。**44.5% 的局至少 2 块挤在同一角格**，均匀采样下只有 14.3%。<br>**无意的问题**：<br>• 障碍框退化，15.5% 的局出现中心距 < 6 cm 的方块对；<br>• 按钮占近机器人一侧，方块被挤向远侧；<br>• 整个区域在画面里只占 11% | 2.7 |
| swingxtimes 也是？ | **SwingXtimes 没有任何有意 bias。**<br>• 扎堆来自偶然、密度，以及同一个障碍框缺陷（7.3% 的局有 < 6 cm 的对）。<br>• ep3 的斜排三块是偶然布局，三块相距 12.7 cm 和 9.3 cm，没有违规 | 2.7 |
| videorepick 生成要均匀，所有 cube 都要 swap | **当前采样本身是均匀随机的，但均匀随机会扎堆**：26.9% 的局有 ≥3 块落在同一个六分之一区域。<br>**「不是所有 cube 都 swap」来自 B12**：3 个固定发起者，加上最近邻搭档。<br>• V4 只有 17.0% 的局 6 块都动过；<br>• ep3 里 bin_4↔bin_3 来回换了 4 次，bin_1 一次没动。<br>**建议**：<br>• 中心最小距 0.12 m；<br>• 6 块全部当发起者，目标每 3 次一轮；<br>• reset 时预先规划搭档 | 2.8 |

### 1.4 待决项（实施前逐条答复，不许自填）

「建议」一列是调查方给的推荐，**不是批准值**。每个议题的实测依据都在第二节对应小节。

**跨议题（先答这 5 项，其余议题依赖它们）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L1 | V4 红线 N5（新随机调用只许追加在既有取值点之后）在 V5 怎么读？ | (a) N5 只保护**原三档与已冻结产物**；xhard 流允许**原地**移位（拒绝循环、换序、次数变化），所有被改动环境重冻为 `v5-01`。V4 先例：MoveCube 的 corner_bias 就曾平移 cube 循环次数与 way_idx。<br>(b) 严格字面：只许追加。这会挡掉 InsertPeg、MoveCube、Pick/Swing/BinFill/VideoRepick 的间距规则 | (a) |
| L2 | 障碍框退化缺陷修到哪？ | (a) 只修 V5 动到的 xhard 环境：BinFill、PickXtimes、SwingXtimes；MoveCube 用 L34 顺带；VideoRepick 被 0.12 m 最小距覆盖。<br>(b) 连 PickHighlight、VideoPlaceButton/Order 的 xhard 一起修，这些环境也要重冻。<br>(c) 全局修，会破坏 V1，H2/N12 禁止 | (a)，(b) 留作后续 |
| L3 | K2 的 `SceneGenerationError` 遮蔽修复是否扩到 VideoRepick、SwingXtimes、PatternLock、VideoUnmaskSwap、ButtonUnmaskSwap 的 xhard？ | 是 / 否 | 是：否则 V5 新增的 xhard 拒绝会变成 TypeError，被当成代码错误 |
| L4 | 共用采样函数 `spawn_random_cube` / `spawn_random_target` 上的新规则怎么挂？ | (a) **只加一个**可选参数 `extra_reject=None`（可调用对象，不抽随机数，默认整段跳过）。<br>(b) 每个议题各加各的参数 | (a) |
| L5 | 快照、run id 与 V4 产物怎么处理？ | (a) 新目录 `scripts/configs/newtask-v5/`、run id `v5-01`，16 个环境全部重抽；未改动的 4 个环境必须逐位复现 v4-01；V4 推理钉在 `0baff09`（建议打 tag）。<br>(b) 加版本门，让 V4 快照在 V5 代码上仍可回放 | (a) |

**Unmask 干扰容器（2.1）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L6 | 「环绕一圈」的带宽 W | (a) W = 1/√ρ = 0.1414 m，即内部密度下一个平均间距格 → 15/14/15/16 个。<br>(b) 只放一排，W = 0.085 → 9/8/9/9 个。<br>(c) 其他 | (a) |
| L7 | 环带与现生成范围之间留多宽 | (a) g = 0.015（xhard 的 min_gap）。<br>(b) g = 0.04（沿用 B13 的内界，每环境多 1 个）。<br>(c) g = 0 | VU/BU 选 (a)；Swap 两环境与 L16 一起定 |
| L8 | Swap 两环境的「现在生成范围」与密度怎么取 | (a) 静态包络（VUS 为半宽 0.2114 的方形；BUS 为锚点框并集的外接矩形），按每局密度 ≈51/m² → 15/16 个。<br>(b) 按静态包络密度（24.8 / 37.9）→ 约 8/12 个。<br>(c) 每局动态环带 | (a) |
| L9 | ButtonUnmaskSwap 的按钮算不算内部范围 | (a) 算：内部矩形 x 从 -0.2625 起 → 16 个。<br>(b) 不算 → 10 个，且环带穿过按钮（21.5% 被挡） | (a) |
| L10 | 数量怎么取整 | (a) 在 1 mm 网格上 floor(ρA+0.5) → 15/14/15/16，冻成整数，并用测试锁定推导。<br>(b) floor → 15/14/15/15 | (a) |
| L11 | N 为奇数时几个含 cube | (a) 在 [floor(N/2), ceil(N/2)] 内随机，与 V4「3 个里 1～2 个」同义。<br>(b) 取 floor。<br>(c) 取 ceil | (a) |
| L12 | 含 cube 的超过 3 个时颜色怎么定 | (a) 仍用 B2 的三色，平衡轮转。<br>(b) 有放回独立抽。<br>(c) Unmask 专用新色板（推翻 B2/A5） | (a) |
| L13 | 两套干扰采样器是否统一成一套 | (a) 统一实现与统一 schema，各环境仍用各自的随机流。<br>(b) 最小改动 | (a) |
| L14 | 揭示/交换期间的停放点 | (a) 给每个干扰容器与每个被藏 cube 各配独立的画面外停放点（xhard 专用 helper，不改 `statechange.py`）。<br>(b) 维持全部停在 (10,10,10) | (a) |
| L15 | ButtonUnmaskSwap 内环 `except RuntimeError: break` 静默截断，在 xhard 是否改为报错 | 是 / 否 | 是 |

**两个 Swap 环境的外环交换（2.2）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L16 | 有外环交换后，Swap 两环境的干扰数量与环带（与 L6～L10 联动） | (a) 采用 2.1 的贴身环带与 15/16 个，前提是实现后 `V5_SWAP_JOINT_FEASIBILITY` 首次可行率 ≥ 0.95。<br>(b) V4 环带放 10 个（实测 100%，但密度不到内部）。<br>(c) 贴身环带取 g=0.04，或外环 lane 0.05（(a) 不过时的杠杆） | (a)，不过闸就回报用户，改走 (c) |
| L17 | 外环发起者怎么定 | (a) randperm(count)[:3]，按 k%3 轮转。<br>(b) randperm(count) 全体轮转。<br>(c) 每窗重新 randint | (b)：count=3 时与 (a) 等价 |
| L18 | 某窗第一候选外环交换不可行时怎么办 | (a) 按排列确定性换下一个发起者，全不行才整段重抽干扰布局。<br>(b) 只整段重抽。<br>(c) 跳过该窗的外环交换 | (a)：(c) 违背口径 4 |
| L19 | 「外环车道不进内部」的含义 | (a) 只要无碰撞。<br>(b) 无碰撞，且离每个内环容器圆距 ≥ 0.04 m，BUS 还要离按钮中心 ≥ 0.122 m。<br>(c) 中心路径不越过环带内界 | (b)：(c) 在 ±0.07 的车道下几乎无解 |
| L20 | reset 时是否也拒绝**内环对内环**的扫掠碰撞 | 是 / 否 | 是：V4 观测到的 8 次 BinCollisionError 全属此类，8/8 可在 reset 时预判 |
| L21 | 外环 lane offset | 0.07（同内环） / 0.05 | 0.07 |
| L22 | xhard 内环搭档在哪定 | (a) 维持 V4：运行时解析，加联合复核与不一致日志。<br>(b) 钉死为 reset 时的规划 | (a) |
| L23 | 是否加认证预筛（只跳过已证明分离的对，判定不变） | 是 / 否 | 是：单窗检查 0.4～1.8 s 降到 3～55 ms |

**InsertPeg（2.3）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L24 | 两两间隔阈值 g（`peg_min_pair_gap_m`） | 0.02 / 0.03 / 0.045 / 0.055 m | 0.03：能保证张开的夹爪闭合区里没有别的杆的最小值 |
| L25 | 间隔的度量，是否保留原生杆根 > 0.075 规则 | 精确轮廓（有向矩形）距离＋保留原生 / 胶囊体＋保留原生 / 只用中心距 | 精确轮廓，保留原生规则 |
| L26 | 杆与孔板之间是否也加轮廓间隔（`peg_box_min_gap_m`） | 否 / 是，取 0 / 是，取 0.01 m | 是，0.01 m。超出「两两之间」的字面，单独问：孔板重叠会把杆弹飞 8 m |
| L27 | xhard 流里的抽样顺序与 yaw 策略 | (a) 4 根一个循环、放在 obj/dir 之前，yaw 在通过原生判据后才抽（lazy）。<br>(b) 0～2 原位，obj/dir 之后再用同一函数抽第 4 根 | (a)（依赖 L1） |
| L28 | 确认放弃 V4「新杆贴近目标杆」的意图，删除 `decision.xhard.near_target_distractor` | 确认 / 以其他形式保留贴近压力 | 确认：目标杆到最近干扰杆的中位距离将由 0.080 m 升到 0.178 m |
| L29 | 回放冻结规格时是否复核间隔 | 是 / 否 | 是 |

**MoveCube（2.4）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L30 | 「30%」指什么 | (1) 各物体自身采样框**面积**的 30%，取中心正方形。<br>(2) 边长的 30%（面积 9%）。<br>(3) 面积 30% 的圆。<br>(4) 十字形，只留四角。<br>(5) 共同的绝对中心 | (1) |
| L31 | 「杆不在中心」的含义 | (A) 杆根不在**自身抖动框**中心（2.74 cm）。<br>(B) 另加：杆身不得进入工作区中心，约多 8.5% 重抽。<br>(C) 不另加（杆根本来就在 \|y\|≥0.15） | (A)；若用户指杆身再加 (B) |
| L32 | 方块中心区以哪个框为基准 | 候选框（w=0.0548，候选与最终位置都查） / 最终支撑框（w=0.0712） | 候选框，两处都查 |
| L33 | MoveCube xhard 的 `corner_bias` 键怎么处理 | 保留、取 0.0 并标注废弃 / 删键 | 保留取 0.0 |
| L34 | xhard 下执行段方块是否不再避让演示段方块（`include_existing=False`） | 是 / 否 | 是：两块从不同时在场；仿真已复现 seed 1000442/1000446 因此 reset 失败 |

**PatternLock / RouteStick（2.5）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L35 | PatternLock 用哪个杠杆达到 25～35 s | A) 6×6、间距 0.08（占地同 V4），节点 [30,33]。<br>B) 5×6、间距 0.1，节点 [25,28]。<br>C) 保留 5×5 [20,24]，只把演示放慢 ×1.3，或每段停 11 帧（唯一保住 B8/K1 与 V4 规格的方案）。<br>D) 5×5 允许重访节点 | A |
| L36 | 选 A 时的节点范围，以及搜索耗尽是否显式报错 | [30,33] / [30,32] / [31,33]；耗尽时 xhard 抛错：是 / 否 | [30,33] 并抛错（依赖 L3） |
| L37 | RouteStick 的 L 范围 | [15,21]（25.0～35.0 s） / [16,20]（26.7～33.3 s） | [15,21] |
| L38 | RouteStick 的 L 范围是否冻进 decision 与规格 header（现在从类属性读、未冻结） | 是 / 否 | 是 |
| L39 | 「30 s」怎么量 | h5 中 `is_video_demo` 帧数 ÷ 30（A2） / 物理仿真时间 | A2 |

**BinFill（2.6）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L40 | 「均匀」指什么 | (a) 空闲区内均匀：已成立，无需改。<br>(b) 颜色充分混合，没有大块同色团。<br>(c) 蓝噪声式铺开。<br>(d) 整个矩形密度拉平（需挪按钮/板） | (b) 加 L2 的缺陷修复 |
| L41 | 同色成团上限参数 | T = 3 / 2；连通距离 0.08 / 0.09 / 0.10；最多重排 64 次，失败时取最优 | T=3、0.09、64 |
| L42 | 是否限制每色生成块数（避免 7+ 同色） | 不限 / 上限 max(target, 6) | 不限：它会改配额规则并平移整条流 |

**PickXtimes / SwingXtimes（2.7）**

| 编号 | 问题 | 选项 | 建议 |
|---|---|---|---|
| L43 | PickXtimes 边角语义（含 MoveCube 方提出的「是否也改为拒绝而非 bias」） | (a) 保留 J5（3 块都 corner_bias 0.5），另加「3 个有色方块各占不同象限」。<br>(b) 只推目标（推翻 J5）。<br>(c) 取消边角（推翻 V4 1.2 原文与 J5）。<br>(d) 只加间距 | (a) |
| L44 | 6 块之间的最小中心距（xhard） | 0.06 / 0.08 / 0.10 | 两环境都取 0.08 |
| L45 | PickXtimes xhard 放置 max_trials | 256 / 1024 | 1024 |
| L46 | 是否把 PickXtimes xhard 的方块区域扩到半宽 0.25 | 是 / 否 / 先做演示探针再定 | 先探针再定 |

**VideoRepick（2.8）**

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
| B13 | 干扰容器放外环 `max(\|x\|,\|y\|) ∈ [0.2675,0.45]`，3 个里 1～2 个含 cube | 紧贴各环境生成范围、一个密度格宽的环带；数量按密度推算为 15/14/15/16；含 cube 数取 [floor(N/2), ceil(N/2)]；四环境统一用精确 8 角点可见性 | 2.1 |
| B3 | 干扰做成额外容器，**不参与 swap**，隐含 3 个 | 数量按密度定；Swap 两环境里干扰容器之间互相交换，但仍永不与内环配对、不进 `spawned_bins` | 2.1 / 2.2 |
| J1（「仍不参与 swap」一句） | 揭示＋误抓即失败＋不交换 | 揭示与误抓保留；Swap 两环境改为交换；可选的独立停放点（L14） | 2.2 |
| H1 | 干扰容器只作静止旁观者进碰撞检查 | 干扰容器成为外环交换中的移动者；碰撞改为两对联合的连续证明（`check_multi_swap_sweep`），reset 规划与运行时复核都做；内环对内环也改在 reset 预判拒绝（L20） | 2.2 |
| 实现细节（未编号） | 颜色无放回，因此最多 3 个 cube；Swap 两环境用圆间距 0.04、线性可见性近似、512 次；cube 命名 `distractor_cube_<colour>` | 三色平衡轮转；统一 OBB 间距；精确可见性；1024 次；cube 名带序号 | 2.1 |
| B6 / I2 / K3 | 杆间距判据不动；第 4 根贴近 0.075～0.085；开局重叠 31.6% 维持现状 | 四根一个采样器；精确轮廓间隔 > 0.03；重叠降为 0；删除贴近目标的圆环带 | 2.3 |
| B7 / G3 | MoveCube 用 `corner_bias ∈ [0,1]`，定为 0.5 | `corner_bias=0`；各物体自身框中心 30% 面积直接拒绝 | 2.4 |
| 2.17 表「goal 区域不动」（部分） | goal 不受偏置 | 区域尺寸不变，但 goal 也有中心拒绝区 | 2.4 |
| A2（范围） | 20～30 s（600～900 帧） | 25～35 s（750～1050 帧）；30 fps 与 `is_video_demo` 的计法不变 | 2.5 |
| B8（布局部分）/ K1 | PatternLock 不改布局；节点 [20,24] | 推荐 6×6@0.08、节点 [30,33]、搜索耗尽即抛错；若选 L35-C 则 B8/K1 保留 | 2.5 |
| B9 | RouteStick 的 L 为 [12,15] | [15,21] | 2.5 |
| V4 计划 2.20 与风险 #6（陈述错误） | 「执行段 = L×50+200，L>≈22 必被截断」 | 更正：强制复位是演示态 NO RECORD，不计预算；执行段为 50·L（+1 初始帧）；截断点是 L≥27 | 2.5 |
| V4 计划 2.19（陈述错误） | 「每段约 31 帧、上限约 24.8 s」 | 更正：实测平均每段 34.25 帧，随方向变化；24 段平均约 27.4 s | 2.5 |
| B1（修改执行） | BinFill 区域与间距不动 | 数值不动，但名义 2 cm 间距在 xhard 真正生效；加同色成团上限 | 2.6 |
| J5（修改） | PickXtimes 3 个有色方块都 corner_bias 0.5 | 保留 0.5，另加「不同象限」、8 cm 间距、精确 OBB、1024 次 | 2.7 |
| B12 / J2 | VideoRepick 发起者仍 3 个；接受约 45% 的 D5 演示期拒绝、靠 H4 递补 | 6 块全当发起者；最小距 0.12 m 加 reset 规划可行搭档；D5 保留作运行时守卫，H4 保留作兜底 | 2.8 |
| K2（扩展） | 只在 VideoPlaceOrder 的 xhard 修异常遮蔽 | 同样修到 5 个环境的 xhard | 2.0 |

## 二、逐议题方案

**怎么读这一节**：2.0 是跨议题的共用改动，只写一次；2.1～2.8 每个议题一节，都按「现状（带锚点）→ 为什么 → 改法（配置键、公式）→ 陷阱 → 实测收益」展开。2.9 是改动后的俯视简图，2.10 是改动一览表。

### 2.0 先修的四件共用事

#### ① 新发现的共用缺陷：放下的方块作障碍时 2D 包围框退化

**定义**：`spawn_random_cube` / `spawn_random_target` 把 `avoid` 里的 actor 转成 2D 障碍框，路径是
mani_skill 的 `get_actor_obb`（trimesh `bounding_box_oriented`）→ `utils/object_generation.py::_trimesh_box_to_obb2d`。
后者取旋转矩阵前两列的 xy 分量 `R[:2,0]`、`R[:2,1]` 当作 2D 轴。问题有两层：

- 对正方体，trimesh 返回的三个轴**顺序是任意的**；
- 竖直轴落在第 0 或第 1 列时，该列投影 ≈ 0，而 `_safe_unit` 会把近零向量**原样返回**。

结果这块方块的 2D 障碍**退化成一条 4 cm 线段**，`min_gap` 在其法向上失效。

**实测**：

| 口径 | 退化率 | 后果 |
|---|---|---|
| BinFill xhard 离线副本（与 v4-01 逐位一致），36000 块 | 66.45% | 23.3% 的方块离最近邻不到 2 cm（名义下限 20 mm）；ep3 的 red_0 与 red_2 只隔 8.4 mm |
| PickXtimes 离线副本，4000 次随机 yaw | 66.1% | 15.5% 的局有中心距 < 6 cm 的方块对，最近 4.1 cm，已贴面 |
| SwingXtimes 离线副本 | 同上 | 7.3% 的局有 < 6 cm 的对 |
| 汇总方用 float64 trimesh 复算 | 49.8% | 退化率随数值路径变化，但缺陷真实存在 |
| 真实模拟器（BinFill seed 4400100） | 11 块中 5 块退化 | 副本与模拟器 11/11 对上 |

V4 的 G2 报告（[20260922-step0-g2-capacity.md](docs/validation/newtask-v4/20260922-step0-g2-capacity.md) 第 3 条）已经在 VideoRepick 上发现过这个现象，当时未修。

**改法（xhard 专用，L2）**：

- 新增纯函数 `utils/xhard.py::cube_obb2d_exact(pose, half)`，不抽随机数，按方块真实 yaw 给出 `(c, A, h)`；
- xhard 分支把放下的方块以这个**预制三元组**放进 `avoid`（`spawn_random_cube` 本来就接受预制三元组），不再放 actor 本身；
- **不改** `_trimesh_box_to_obb2d` / `_safe_unit`：改了会让原三档的拒绝结果变化，V1 必挂（H2/N12）。

⚠ 修复只在被 V5 改动的环境生效。PickHighlight、VideoPlaceButton、VideoPlaceOrder 的 xhard 仍带这个缺陷（L2 (b) 留作后续）。

#### ② 共用采样钩子 `extra_reject`（L4）

**为什么需要**：MoveCube 中心区、Pick/Swing 的 8 cm 间距、PickXtimes 的不同象限、VideoRepick 的 0.12 m 最小距，都要在 `utils/object_generation.py::spawn_random_cube` / `spawn_random_target` 的拒绝循环里加判据。这两个函数被 12 个布局环境、所有档共用。若三个议题各加各的参数，V1 的暴露面会变成三倍。

**改法**：两个函数只各加一个可选参数 `extra_reject=None`，签名为 `callable(x, y, yaw) -> bool`：

- 在既有 OBB/圆判据之后、`recorder.value` 之前求值；
- 自身不抽随机数；
- 默认 `None` 时整段跳过，沿用 V4 `corner_bias` 默认 0 即原样返回的先例；
- 各议题的规则都写成闭包传入。

**闸门**：`RESET_REGRESSION=PASS compared=144 diff=0`；`V5_UNTOUCHED_XHARD_PARITY`：StopCube、PickHighlight、VideoPlace×2 的 40 行 xhard 规格逐位复现；V1。

#### ③ `SceneGenerationError` 被遮蔽成子模块（K2 扩展，L3）

**现象**：7 个环境模块先 `from .utils.SceneGenerationError import SceneGenerationError`，随后 `from .utils import *`，这个名字就被覆盖成了**子模块**。汇总方用 import 自省核实，涉及 VideoRepick、SwingXtimes、PatternLock、RouteStick、StopCube、VideoUnmaskSwap、ButtonUnmaskSwap。VideoPlaceOrder 已按 K2 用 `_RealSceneGenerationError` 别名修过。

**后果**：`raise SceneGenerationError(...)` 与 `except SceneGenerationError:` 都会抛 TypeError。生成器把 TypeError 归为不可重试的代码错误。V4 抽签循环捕获所有 Exception，所以仍会重抽，但**失败分类是错的**。反例：SwingXtimes 圆盘放不下时，已被证实走的是 TypeError，汇总方把原调查「会作为 SceneGenerationError 重抽」的说法判为推翻。

**为什么 V5 必须先修**：V5 新增的 xhard 拒绝几乎都会走到这个名字：

- VideoRepick 搭档规划失败，约 8.4%；
- SwingXtimes 圆盘失败，约 3.6%；
- PatternLock 搜索耗尽改为抛错；
- Unmask 内环预判拒绝。

**改法**：按 K2 模式只修 xhard，在 raise 与 except 两处按 difficulty 选类，原三档保留现状（H2）。RouteStick、StopCube 在 V5 没有新增抛错点，不在清单里。

**闸门**：`V5_SCENEGEN_CLASS=PASS envs=5 raised=SceneGenerationError typeerror=0`。

#### ④ N5 的读法与新快照（L1、L5）

**哪些设计触及 N5**：几乎每个议题的推荐设计都会让 xhard 流**原地**移位，没法只在末尾追加：

- InsertPeg：lazy yaw，peg_3 提前到 obj/dir 之前；
- MoveCube：原位拒绝重抽；
- Pick/Swing/BinFill/VideoRepick：间距规则改变 trial 次数。

原三档不受影响，由 V0、V1、`RESET_REGRESSION` 守住。按 L1 (a) 读 N5，这些环境重冻为 `v5-01` 即可。
例外：VideoUnmask/ButtonUnmask 的新抽样本来就在所有既有取值点之后，Swap 两环境走独立流，所以这 4 个环境在 xhard 下内环取值**与 V4 同 seed 完全相同**，这一点由 `V5_UNMASK_INNER_PARITY` 验证。

**新快照（L5）**：每个议题都会增删 `decision.xhard` 的键，`assert_native_decision` 的 xhard 形状检查因此会拒绝 V4 快照。RouteStick 的 L 范围从类属性读、V4 header 没冻结它，V4 规格在 V5 代码上会直接 `ValueError`（L38）。所以：

- 新建 `scripts/configs/newtask-v5/`，全部改完后**只重导一次** `sampling_config.json` 并重建 `combos.json`；
- run id 用 `v5-01`；
- V4 推理钉在 `0baff09`。

### 2.1 Unmask 干扰容器：贴身环带、按密度定数、半数含 cube（四环境）

**现状**：两套实现，四环境共用同一组参数：3 个，外环 `[0.2675, 0.45]`，1～2 个含 cube。

| 项 | VideoUnmask / ButtonUnmask | VideoUnmaskSwap / ButtonUnmaskSwap |
|---|---|---|
| 入口 | `utils/unmask_distractors.py::spawn_ring_distractor_bins`（`XHARD_DISTRACTOR` 在各环境文件） | `utils/unmask_swap_xhard.py::sample_distractors` / `build_distractors`，经 `_spawn_xhard_distractors` 调用 |
| 随机流 | 主场景 generator，排在所有既有取值点之后 | 独立流 `distractor_generator(seed)` = seed + `DISTRACTOR_STREAM_SALT`（0x5D157AC7） |
| 可见性 | 精确：8 个角点都投进 256×256 画面（`visible_in_camera`） | **线性近似** `visible_on_camera`，比精确判据宽：20000 个随机点里有 2358 个只被近似判为可见；V4 冻结的 60 个 Swap 干扰容器里有 4 个实际被裁出画面 3.8～8.8 px（VUS ep5/ep8、BUS ep5/ep7，都是未选中的候选） |
| 间距 | OBB 避让，min_gap 系数 0.75（0.015），256 次 | 圆间距 min_gap 0.04（中心距 0.1178），512 次，另对预测的内环扫掠做精确拒绝（H1） |
| cube 颜色 | 三色**无放回**（`high > len(DISTRACTOR_COLORS)` 即 ValueError） | 三色切片到 3 个，超过就**静默截断**；cube 名 `distractor_cube_<colour>`，**颜色一重复就重名崩溃**（原型 2/2 复现 AssertionError） |

**密度对比**：

- 内部：VU/BU 有 8 个容器，区域 0.4×0.4，密度 50 个/m²（G2）。Swap 两环境是 4 个容器、每个锚点框 0.14×0.14，密度 51 个/m²。
- V4 外环：3 个 / 0.486 m² 可见占位 = **6.2 个/m²**。按内部密度，V4 外环应放 **24 个**。

用户说的「范围太大、数量太少」都成立。

**「现在生成范围」逐环境**（代码推导，并用 10 条冻结规格核对）：

| 环境 | 内部范围 | 备注 |
|---|---|---|
| VideoUnmask | region `[-0.2,0.2]²`，中心 ±0.1725 | — |
| ButtonUnmask | 同上；按钮 OBB 伸到 x = -0.306 | 按钮挡住环带 5.7% |
| VideoUnmaskSwap | 4 个锚点框随角度 U[0,180) 整体旋转；旋转包络的 Chebyshev 半宽 **0.2114** | 单局实际只占 0.08～0.10 m² |
| ButtonUnmaskSwap | 不旋转；中心 x∈[-0.0425,0.1425]、y∈[-0.1425,0.2425]；把两个按钮算进来，x 从 **-0.2625** 起 | 偏向 +y |

**改法（L6～L13）**：取中心带作为环带，其内界与外界为

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
| VideoUnmask | 0.3027 | 15.14 | **15** | [7,8] |
| ButtonUnmask | 0.2853（按钮挡 5.7%） | 14.27 | **14** | [7,7] |
| VideoUnmaskSwap | 0.3081 | 15.40（2 mm 网格为 15.52，**贴近取整边界**） | **15** | [7,8] |
| ButtonUnmaskSwap（按钮算内部） | 0.3115 | 15.58 | **16** | [8,8] |
| ButtonUnmaskSwap（按钮不算） | 0.2039（21.5% 被挡） | 10.19 | 10 | — |

**可行性与画面**：

- **放置成功率**：每环境 ≥ 500 个随机内部布局。VU N=15 在 256 次下 99.4%、1024 次下 100%。BU N=14 为 100%。Swap 两环境改用统一 OBB 规则后 N ≤ 16 都是 100%；若沿用 V4 圆规则，N=16 只有 50.8%（VUS）/ 45.5%（BUS），所以 Swap 两环境必须换规则。
- **余量**：饱和容量 21～22 个（最少 17～18），约 30% 余量。
- **冻结布局复核**：v4-01 冻结内部布局 × 100 条干扰流，放置结果为 1000/1000、1000/1000、1000/1000、998/1000，因此四环境都用 1024 次。
- **可见比例**：环带中心带可见 90.2%（VU/BU）、86.8%（VUS）、87.1%（BUS）。靠近相机的两个角只有 29～44% 可见，精确判据会自动排除。
- **遮挡**：机器人初始位姿只遮挡 x∈[-0.892,-0.557]、|y|≤0.094 这一块，碰不到环带。
- **像素尺寸**：环带上容器最小约 13.7×19.0 px，都不小于 V4 远侧的 12.1×17.5 px。
- **本机模拟器**（进程内补丁，不落盘）：VU 3 次 reset 加 2 局演示全部成功（482/458 步）；BU 3+2 成功（521/513 步）；VUS 3+1 成功（854 步）；BUS 原型 2+1 成功（704 步）。

**⚠ 陷阱与代价**：

1. **揭示段变慢**：0～31 步里 22～24 个容器同时停在 (10,10,10)，单步耗时从 38 ms 变为 108～197 ms（VU），45 ms 变为 184～417 ms（BU），每局多 3～13 s 墙钟。落回精度不受影响（误差 0.04～0.05 mm）。对策见 L14 的独立停放点。
2. **Swap 两环境 reset 变慢**：VUS 从 15.5 s 变为 33～66 s，BUS 原型约 24～26 s，基本都花在精确扫掠二分上。45～91% 的环带候选落进粗筛球，但真正碰到车道的只有 0.2～0.9%。对策见 2.2 的认证预筛（L23）。
3. **ButtonUnmaskSwap 静默截断**：它的内环 `spawn_random_bin` 失败时走 `except RuntimeError: break`，在 xhard 下也会静默截断（约 1/500），截断后环带障碍与交换对都会变。按 2.2④ 应改为抛真 `SceneGenerationError`（L15）。
4. **数量对口径敏感**：VUS 的 15.40 贴着取整边界，所以数量冻成整数，并在测试里锁定参考网格上的推导（`V5_UNMASK_DENSITY`）。
5. **不能直接改全局色板**：`xhard.DISTRACTOR_COLORS` 也被 PickXtimes/SwingXtimes 导入，改它会连带改动这两个环境。

### 2.2 两个 Swap 环境：外环随内环同步交换，加两对联合碰撞证明

**现状：内环交换机制**（回答用户「现在内部 swap 的机制是什么，最近 2 邻？」）：

1. **次数与窗口**：VUS 的 xhard `[8,12]` 读 native `parameters.configs.xhard`；BUS 的 `[6,8]` 读 `decision.swap_count_range.xhard`。
   第 k 次交换的窗口为 `[64+33k, 64+33(k+1))`，其中 33 = `utils/unmask_swap_xhard.py::scaled_window_steps(50, 1.5)`，窗口首尾相接。
   最后一次结束于 64+33n：VUS 为 328～460 步，BUS 为 262～328 步。
2. **发起者**：`_load_scene` 在主流上抽两次（`objects.swap_initiator_indices` 加 `objects.swap_initiator_third`），定下 3 个发起者 a、b、c。第 k 次交换的发起者是 `spawned_bins[swap_indices[k % 3]]`，固定按 a,b,c,a,b,c 轮转；4 个容器里**恰有 1 个永不发起**。
3. **搭档**：`step` 在窗口第一步、`idx2` 为空时，用**实际位姿**扫描所有其他内环容器，取 `np.linalg.norm(reference_pos[axes] - candidate_pos[axes])` 最小者，比较用严格 `<`，平局取生成序靠前。
   VUS 的 axes 读 `NATIVE_SAMPLING.parameters.swap_selection.partner.position_axes = [0,1]`；BUS 写死 `reference_pos[:2] - candidate_pos[:2]`。
   **所以「最近 2 邻」不是「最近的 2 个邻居」，而是「用 x、y 两个轴量出来的最近 1 个邻居」。**
   唯一的「取最近 2 个」逻辑是 `_compute_dynamic_swap_candidates`（`distances[:2]`）加上 `_select_swap_pair_from_positions`，两者在 VUS、BUS、VideoRepick 都**没有任何调用者**，是死代码。
4. **轨迹**：`utils/statechange.py::swap_flat_two_lane`，按 smoothstep 推进。两个容器沿弦线各向相反一侧鼓出 `0.07·sin(πα)`，中点处相距 0.14 m；窗口结束时精确对换位姿；其余容器每步都被钉住。
5. **藏着的 cube 不随容器走**：`lift_and_drop_objectA_onto_objectB` 在 `[64, last_end)` 期间把 cube 传送到 (10,10,10)，到 last_end 再放到它那只容器最终的 XY 下方。
6. **结果结构**：因为搭档互为最近邻，VUS 60.7%、BUS 81.9% 的局只在 2 个不相交的对之间来回换；23.9% / 26.7% 的交换会直接撤销上一次。
7. **碰撞检测**：
   - reset 时，`_check_state_readonly('initial')` 对内环加干扰容器做静态 SAT；
   - 每个窗口起点，`_check_swap_sweep_from_actual` 调 `utils/bin_collision.py::check_swap_sweep`：只支持**一对**移动，其余视为静止，用区间二分做证明，`LANE_OFFSET 0.07`。证不出就抛 BinCollisionError，演示判失败，靠 H4 递补。
   - **V4 观测到的 8 次 BinCollisionError**（实跑 VUS ep3 seed 4500300 的 sweep#1，bin_2 撞 bin_1，g = -0.00207；另有 V6 中 VUS 1 次、BUS 6 次）**全部是内环对内环**，没有一次涉及干扰容器，而且 **8/8 都能在 reset 时预判**。离线副本对 20 行 Swap 规格逐位一致。

**为什么不能照抄**：若把外环完全照抄内环（V4 环带、3 个干扰、最近邻、无回退）：

- 最近的干扰常在场地对面，路径中位长度 0.46～0.49 m，会横穿内部；
- 只有 31%（VUS）/ 29%（BUS）的局全程无碰撞且在画面内；
- BUS 有 787/2084 个窗口会让外环容器进入按钮禁区。

**改法（L16～L23，推荐 P1）**：

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
    放置干扰容器（2.1 的规则；recorder.value 推迟到本次尝试被接受之后）
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

- **联合证明不需要新数学**：`check_multi_swap_sweep` 直接复用 `_prove_pair`（它本来就能证两个都在动的物体）。单对时与 `check_swap_sweep` 逐位相同（15/15，含 3 个接触拒绝），远处加第二对也不改变结果。
- **外环在 reset 时预先规划**，不在运行时解析：窗口起点时，上一次交换只完成到 99.7%，实际位姿与名义差 0.686 mm，近平局会因此翻转（VUS 7/8969、BUS 11/5982 个窗口）。外环规划再借用 VideoRepick 的 5 mm 余量，吸收这个偏差。
- **认证预筛（L23）**：采样 401 个 s 值，只跳过已证明分离的对，判定结果不变（40/40）。单窗联合检查从 0.8～1.8 s 降到 3～55 ms；V4 干扰采样本身也从 4.75 s 降到 0.0025 s。
- **内环对内环在 reset 预判（L20）**：VUS 1.3%、BUS 10.7% 的局会从演示级失败挪成候选级拒绝。
- **不增加控制步**：外环与内环同窗口，`swap_schedule[-1][3]` 与所有等待点都不变。

**与 2.1 贴身环带合起来能不能成**：两个调查方各自只测了自己那一半，汇总方用 `joint_probe.py`（每环境 300 个布局、圆近似、`evc` 判据）试算了两者合并的情形：

| 设置 | 首次布局可行（VUS / BUS） | 第一候选发起者就可行的窗口 |
|---|---|---|
| V4 环带，3 个，带回退 | 63.3% / 45.2% | — |
| V4 环带，6 个，带回退 | 99.0% / 96.7% | 73%（VUS） |
| V4 环带，10 个，带回退 | 100% / 100% | — |
| **贴身环带，15 / 16 个，带回退** | **99.67% / 96.99%** | **44% / 29%**（回退很多） |

结论可行，但这只是圆近似下的试算。因此设硬闸门 `V5_SWAP_JOINT_FEASIBILITY`：用实现后的采样器重跑，每环境 ≥ 300 布局，**首次可行 ≥ 0.95** 才冻结数量。不过闸就回报用户，可用的杠杆有：g = 0.04 的环带 C、外环 lane 0.05、只让部分干扰容器交换（L16）。

**⚠ 陷阱**：

1. **AST 锁**：`tests/lightweight/test_episode_action_sampling.py::test_real_swap_resolution_matches_baseline_and_preserves_ties` 会把唯一那段 `range(len(self.swap_schedule))` 循环抽出来，放到 SimpleNamespace 上执行。新代码必须写在循环之外，或者一律用 `getattr` 带默认值。
2. **末句约束**：`_spawn_xhard_distractors` 必须仍是 `_load_scene` 的最后一句（`test_干扰容器在load_scene末尾且不用主流` 会检查）。
3. **规格回放**：在拒绝循环里调用 `SpecRecorder.value`，回放时会在早期尝试就返回冻结值。所以只对被接受的那次尝试调用 value()，尝试次数与配对用 record() 留痕。
4. **来回撤销仍在**：最近邻规则下外环也会来回撤销（count = 6～10 时 25～32%），这是有意镜像内环（内环 24～27%）的结果。
5. **停放点堆叠**：外环 cube 也停在 (10,10,10)，会与内环 cube 叠放数百步，这一点**尚未实测**，见 L14。
6. **按钮与手臂不在碰撞模型里**：碰撞模型只有容器。BUS 演示时机器人会在交换期间去按按钮，按钮风险目前只用中心距阈值近似，演示级影响要看 V6。

### 2.3 InsertPeg：四根杆同一采样器，两两轮廓间隔

**现状**（回答「现在怎么生成 4 个」；离线 torch 副本与 v4-01 的 10 行逐位一致）：

1. `_load_scene` 只跑一次：
   - 抽 length、radius（两次都乘 0，R8），再抽 `head_rgb` rand(3)，4 根杆共用同一个颜色，tail = 1 − head；
   - 按 `peg_offsets` 的 4 个元素建 4 根外观完全相同的杆；
   - 抽一次 `randint(0,4)`，但立刻被 `overridden_to=0` 覆盖，所以**目标恒为 peg_0**。
2. `_initialize_episode` 跑两次（`gym.make` 内一次、reset 一次），只有最后一次生效；**演示段与执行段共用同一布局**。演示后 `solve_strong_reset` 加上 `step` 会把所有杆传送回 `peg_init_poses`，持续 30 步。
3. 每次初始化依次做：
   - 抽孔板 x、y 抖动和 yaw；
   - `pegs[:-1]` 这 3 根走原生均匀拒绝：x∈[-0.2,0.2]、y∈[-0.3,0.3]，杆根离孔板中心 > 0.06、离已放杆根 > 0.075，最多 512 次，接受后才抽 yaw（±180°）；
   - 抽 obj、dir 的 randint；
   - **最后由 `InsertPeg._xhard_place_near_target_peg` 放第 4 根**：半径 r∈(0.075, 0.085]、方位角 θ 在目标杆根周围均匀抽，同样查原生判据、最多 512 次，再抽 yaw，最后覆盖 `peg_init_poses[3]`。

**为什么 0.075 m 不保证间隔**：`utils/object_generation.py::build_peg` 的根是杆头中心，整根杆的轮廓是 0.10×0.02 m，从 root − 0.075u 伸到 root + 0.025u。所以 0.075 m 的杆根距离允许两根杆穿插；只靠中心距要保证不重叠，杆根距离得 > 0.1513 m。

**实测**：

- **重叠率**：V4 xhard 目标杆可见轮廓与别的杆重叠 28.1%，任意一对重叠 30.7%；碰撞盒口径 25.9% / 28.2%；按 I2 的口径复算为 31.7%，报告值 31.6%。
- **物理沉降**（20 步）：重叠的目标杆被挤动 2.5 / 5.4 / 11.8 / 68.8 mm，最多转 55.8°；不重叠的杆 0.0 mm。
- **V4 正式局**：成功 2/10（ep4、ep5），`selected_shortfall=1`。8 局失败的几何诱因：3 局目标重叠（ep3/6/7）；2 局邻杆在夹爪闭合区内（ep0/8）；1 局目标压孔板（ep6）；2 局抓取点离基座 ≥ 0.81 m，接近可达极限（ep0/1）；2 局无几何解释。

**改法（L24～L29）**：4 根杆在**一个循环**里生成，放在 obj/dir 之前，用**同一套规则**。目标 peg_0 只是第一个被抽的，没有任何特殊规则。

```text
for i in 0..3:
  for attempt in 1..512:
    x, y = rand, rand（与原生相同）
    若 |xy − box| ≤ 0.06 或 |xy − root_j| ≤ 0.075 → 重抽              ← 原生规则保留
    yaw = (rand·2 − 1)·π                                                ← lazy：通过原生规则后才抽
    若 footprint_gap(peg, box) ≤ 0.01 → 重抽                            ← L26
    若对任一已放杆 j 有 footprint_gap(peg, peg_j) ≤ 0.03 → 重抽          ← L24，严格不等号
    接受
轮廓：杆 = 中心 root − 0.025u、半尺寸 (0.05, 0.01) 的有向矩形；孔板 = 半尺寸 (0.05, 0.04)
footprint_gap = 有向矩形精确距离（SAT 判重叠时为 0，否则取 32 个顶点到边距离的最小值）
```

- **新配置**：删除 `InsertPeg._xhard_place_near_target_peg` 与 `decision.xhard.near_target_distractor`；新增键 `peg_min_pair_gap_m=0.03`、`peg_box_min_gap_m=0.01`。
- **新记录**：`peg_attempts`、`min_pair_gap_m`、`min_box_gap_m`。
- **回放守卫**（L29）：回放冻结规格时复核两种间隔，不合格就报错，防止 V4 规格把重叠带回来。

**为什么是 0.03**：

- 夹爪张开时每指 0.04，指尖沿杆向宽 17.5 mm；
- 0.01 + g ≥ 0.04 时，邻杆**不可能**落在指间闭合区，g = 0.03 是满足这一点的最小值；
- 执行段的 `failure_func`（抓起任何非目标杆即失败）恰好惩罚这种情况；
- 结果：夹入风险从 V4 的 21.5% 降到 0，指垫压到邻杆从 29.5% 降到 2.1%（g = 0.055 时两者都为 0）。

**实测收益**（离线 10000 布局 + torch 原型 1000 seed；原型用精确的 V5 抽样顺序）：

- **放置难度**：4 根杆每次尝试的接受率均值为 [0.875, 0.779, 0.688, 0.603]，最坏状态 [0.827, 0.700, 0.585, 0.475]；最多尝试 [4, 7, 9, 10] 次。
- **预算耗尽**：512 次耗尽的概率约为 0（MC 0/10000、原型 0/1000，最小实测间隔 0.0301）。
- **重叠**：杆与杆、杆与孔板的重叠都是 0（V4 分别为 28.1% 与约 21%）。
- **画面可辨**：点选歧义（邻杆离目标杆 < 10 px）从 19.3% 降到 0。
- **代价**：目标杆到最近干扰杆的中位距离从 0.080 m 升到 0.178 m（原生 3 根杆时为 0.198 m），V4「新杆贴近目标」的难度意图随之消失（L28）。
- **孔板规则的证据**：没有孔板规则的 V5 原型里，一根杆因压到孔板被弹飞 7986 mm；V4 ep6 的目标杆被推开 69 mm、转了 56°。

**⚠ 陷阱**：

1. **不等号必须严格**：矩形重叠时距离为 0，写成 `gap ≥ 0` 等于没有约束（MC 里仍有 25% 重叠）。
2. **可达极限不在本议题**：约 16% 的布局抓取点离基座 > 0.78 m，这类失败间隔规则管不到；**演示成功率尚未实测**。
3. **回放不复核**：`SpecRecorder.value` 回放时直接返回冻结值、不复核规则，所以必须靠回放守卫。

### 2.4 MoveCube：方块、目标、杆按自身采样框的中心 30% 面积直接拒绝

**现状**：

- 「target」是目标圆盘 `goal_site`（任务文本为 "move the cube to the target"），半径 0.04，无碰撞体。
- 每个 segment（演示、执行各一套，独立抽）要抽 5 项：杆根（base_y 取正负号，再加 x、y 抖动）、杆 yaw、goal xy、方块候选中心、方块最终 xy。
- V4 的 `corner_bias=0.5`（经 `utils/xhard.py::corner_push`）**只作用于**杆抖动、方块候选中心与方块局部偏移，**goal 从未被偏置**。
- 离线副本与 v4-01 的 10 行逐位一致（误差 ≤ 3.6e-9，way_idx 也一致）。

| 物体 | 自身采样框（中心、半宽） | V4 仍落在「30% 面积中心区」的比例 |
|---|---|---|
| 杆根 | `(0, ±0.2)`，半宽 0.05（`jitter_span 0.1`） | 2.8% |
| demo goal | `(0,0)`，半宽 0.15 − 0.04 = 0.11 | **29.1%**（未偏置） |
| exec goal | `(0,0)`，半宽 0.10 − 0.04 = 0.06 | **29.2%** |
| 方块候选 | `(0,0)`，半宽 0.1（`center_span 0.2`、`center_offset -0.1`） | 方块最终位置 4.5% |

可见**偏置不等于排除**。另外，杆根在 |y| ≥ 0.15，以工作区中心为准的任何定义都不会拒绝它；「杆不在中心」只有相对它**自身抖动框**的中心才有意义（L31）。

**30% 的几种定义**（每物体 40 万次抽样，外加联合布局 3000 局）：

| 定义 | 每次抽样拒绝率 | 评价 |
|---|---|---|
| (a) 边长 30%，面积 9% | 0.090 | 中心区只有 1.5～3.9 cm，比 4 cm 方块、8 cm 圆盘还小；13.9% 的方块仍盖住中心 5.48 cm |
| **(b) 面积 30% 的中心正方形，边长比 √0.3 = 0.548** | **0.300** | **推荐**：对杆、goal、方块都是同一个 30% |
| (b') 面积 30% 的圆 | 0.300 | 对角方向留缝：3.2% 的方块、4.1% 的 goal 仍在方形区内 |
| (a') 十字形（任一轴在 30% 内就拒，只留四角） | 0.51 | 最接近旧的推向四角意图，但不是用户说的「不在中心」 |
| (c) 共同的绝对中心 (0,0)，w = 0.045 | 杆 0、demo goal 0.17、exec goal **0.56**、方块 0.20 | 各物体不一致，杆的要求实际上失效 |

**改法（L30～L34）**：

```text
config_xhard = {peg_yaw_range: ±π（不变）, corner_bias: 0.0,
                center_exclusion: {shape: square, area_ratio: 0.3, max_trials: 128}}
_native_decision 按 segment 暴露：demo_layout.xhard / execution_layout.xhard

w = √area_ratio × 自身框半宽：
  杆 0.0274（相对 (0, base_y)）
  demo goal 0.0602、exec goal 0.0329（相对 region_center）
  方块 0.0548（相对候选框中心 0；候选中心与最终 xy 两处都查）
判据：max(|dx|, |dy|) < w 即拒绝，在原取值点原地重抽

各取值点：
  杆：抖动两次抽样后判中心区，不过就原地重抽（上限 128，超出抛 SceneGenerationError）
  goal：spawn_random_target(..., extra_reject=goal_zone)
  方块候选：_sample_cube_center 的接受条件改为 |c − g| > 0.1 且不在中心区
  方块最终：spawn_random_cube(..., extra_reject=cube_zone)，执行段另设 include_existing=False（L34）
记录：layout.{demo,execution}.center_exclusion = {area_ratio, shape, w_peg, w_goal, w_cube}
      可选 objects.sampling_trace.center_rejections
```

**「30% 是否可以」的实测结论**：可以。

- **生成**：2000 局全部成功。每局平均重抽 2.46 次，随机数总数均值 37.08（最少 27，p99 59，最大 84）。
- **最坏情况**：各循环最坏接受率在候选循环为 0.358（demo）/ 0.297（exec），最终循环为 0.496；预算耗尽 ≤ 2.5e-20。
- **余量**：面积比取到 0.5 仍可行（最坏耗尽 3e-17）。
- **可达性代理**：P(peg_push 起点离基座 > 0.80 m) 为 4.2%，介于均匀采样（3.8%）与 V4 b=0.5（6.6%）之间。
- **本机演示**：10/10 成功（peg_push 5/5、gripper_push 3/3、grasp_putdown 2/2），Wilson 95% 区间 [0.72, 1.0]，**不是判据级结果**。
- **分布形状**：方块 Chebyshev 半径 0～5 cm 的区间里为 0，其余较平；V4 则堆在最外缘（11～13 cm 占 34.8%）。

**⚠ 既有缺陷，原三档同样存在**：执行段方块 `cube_2` 用默认 `include_existing=True`，会把演示段方块的 OBB（本身又是退化的）当成障碍。两块在物理上**从不同时在场**：`cube_2` 被传送到 (10,10,1)，阶段切换时 `step` 再把 `self.cube` 挪到 `cube_init_pose_2`。但候选落在演示方块附近时，256 次会全部失败。

- 失败率：V4 xhard 约 0.33～0.60%（抛 SceneGenerationError，seed 1000442、1000446 已在真实模拟器复现）；原三档约 0.60～1.07%（抛 RuntimeError，H2 下不修）。
- 加上中心拒绝后，失败率会升到 0.97～1.83%。
- xhard 改为 `include_existing=False` 后为 0/3000，还顺带把 V4 最坏 725 次抽样的长尾砍到 51 次。

### 2.5 PatternLock / RouteStick：演示校准到 30±5 s

**现状实测**：对 h5 数 `is_video_demo` 帧，mp4 帧数与之一致，30 fps：

| 局 | 路径 | 演示帧 | 演示秒数 | 执行帧 | 总帧 |
|---|---|---|---|---|---|
| PatternLock ep0 | 21 节点 / 20 段 | 649 | 21.6 | 649 | 1298 |
| PatternLock ep3 | 21 / 20 | 683 | 22.8 | 683 | 1366 |
| PatternLock ep6 | 22 / 21 | 757 | 25.2 | 757 | 1514 |
| RouteStick ep0 | L=13 | 650 | 21.7 | 650 | 1300（**未截断，成功**） |
| RouteStick ep3 | L=12 | 600 | 20.0 | 600 | 1200 |
| RouteStick ep6 | L=12 | 600 | 20.0 | 600 | 1200 |

执行段与演示段逐段等长，总帧数就是演示帧数的两倍。V4 的 10 条候选里，达到 25 s 的 RouteStick 只有 2/10，PatternLock 也只有 2/10。

**评估预算（更正 V4 计划 2.20 的错误陈述）**：

- `scripts/evaluation.py` 写死 `max_steps=1300`，据此 `max_steps_without_demonstration=1302`，DemonstrationWrapper **只计非演示步**；reset 的初始步已计 1，所以策略实际有 **1301 步**。
- RouteStick 的 `solve_strong_reset(timestep=200)` 是 `demonstration=True` 的 NO RECORD 任务，在 reset() 里跑完，**不计入预算**。
- 执行段 = 50·L（另加 1 个初始帧），**截断点为 L ≥ 27**：模拟器里 L=26 在第 1296 步成功，L=27 在第 1302 步超时。
- 数据生成的 fail-safe 为 5000，已用步数约 100·L + 327，L=21 时约 2427。

**RouteStick（L37、L38）**：每段**恰好 50 帧**：`solve_swingonto_withDirection` 生成 45 个贝塞尔点，再加末端 5 个保持点。取 `config_xhard.length = [15,21]`：

- 演示 750～1050 帧，即 25.0 / 26.7 / 28.3 / 30.0 / 31.7 / 33.3 / 35.0 s，均匀抽样时均值恰为 30.0 s；
- 执行段最长 1050，比 1301 还多 255 步余量（19.6%）；
- 抽样点与顺序都不变，只改 L 的值域，满足 N5；
- 另加一个 xhard decision 键，把 L 范围冻进 header（L38）。

**PatternLock（L35、L36）**：每段帧数**不恒定**：`solve_swingonto` 在关节空间做时间参数化，左右移动约 25.7 帧，前后 37.4，斜向 37.2，靠远排 x=0.1 的约 46，平均 **34.25**（V4 当时假设 31）。

5×5 网格上是简单路径 DFS（`utils/adjacent.py::dfs_path` 带 visited），最多 25 节点。现行 [20,24] 离线 300 局只有 **11.3%** 落在 25～35 s；5×5 上**任何**范围都填不满这条带（最好的 [23,25] 也只有 63%）。

| 方案 | 落带率（300 局离线） | 时长范围 / 均值 | 模拟器 | 代价 |
|---|---|---|---|---|
| **A：6×6、间距 0.08、节点 [30,33]** | **100%** | 25.4～33.5 s / 29.2 | 3/3 成功（28.8 / 28.3 / 30.4 s） | 占地与 V4 相同（x∈[-0.3,0.1]、y∈[-0.2,0.2]，不影响可达与画面）；相邻节点在画面中的最小间距从 14.1 px 降到 11.1 px；推翻 B8/K1 |
| B：5×6、间距 0.1、节点 [25,28] | 99% | 24.5～33.0 / 28.6 | 2/2（32.1 / 29.8 s） | 像素密度保持 V4 水平（14.2 px） |
| C：5×5 [20,24] 不动，只把演示放慢 ×1.3（或每段停 11 帧） | 100% | 25.1～34.6 / 30.0 | 2/2（28.4 / 33.4 s） | 保住 B8/K1 与 V4 规格；内容不增加，演示速度不再等于执行速度 |
| D：5×5 允许重访节点 | 95% | 23.6～35.9 / 29.7 | — | 破坏「图案锁」不重访的语义，并替换搜索 |

方案 A 的实现：

- `config_xhard = {'grid': 6, 'length': [30,33], 'spacing': 0.08}`；
- `_native_decision` 新增 `decision['grid_spacing'] = {'xhard': 0.08}`；
- `_load_scene` 取间距时，原三档回落到 native 的 0.1；
- 搜索（`find_path_0_to_8`、8 邻接、`max_attempts=1000`）不变。

单值命中（1000 次内）：30～32 为 40/40，33 为 36/40，所以要配 **PL-E**：xhard 下 1000 次搜不到就抛 SceneGenerationError，不再静默沿用最后一条错误长度的路径（这正是 K1 的根因；依赖 L3）。

执行段估计最长约 1005 步，余量 ≥ 296（22.8%）。

**⚠ 陷阱**：

1. **帧数模型只是预测**：离线的 mplib screw 帧数模型与真实 h5 的误差在 −1.3%～+0.1%。验收一律以真实 h5 的 `is_video_demo` 帧数为准。
2. **学习策略的余量变小**：oracle 执行段最多用掉 1301 步预算的 77～81%，比 oracle 慢 20% 以上的策略会在最长局超时。`evaluation.py` 的 1300 是 MME-VLA 常量，**不改**。
3. **画面更密**：6×6 在画面里更密，靠机器人一侧的节点间距约 11 px。若用户更在意画面密度，选 B 或 C。

### 2.6 BinFill：位置本就均匀，同色扎堆是偶然加缺陷

**现状**（离线副本与 v4-01 的 10 局、120 块逐位一致）：

- 按钮 `rand(2)` → 中心 x∈[-0.25,-0.15]、y∈[-0.2,0.2]，完全在方块区内；
- 孔板抽 3 次（x∈[-0.05,0.15]、y∈[-0.2,0.2]、yaw ±20°）；
- 颜色配额在放置**之前**就定好：`color_pool=randperm(3)`，投入色数 [2,3]，投入总数 [5,7]，其余块逐个随机分色；
- 生成序为 `objects.spawn_order = randperm(12)`，颜色是随机交错的，**不是先放全部红色**；
- 每块用 `spawn_random_cube`：候选在 x∈[-0.28,0.08]、y∈[-0.23,0.23] 均匀抽，撞到按钮、板或已放方块就拒绝（平均 3.12 次，p99 17，最大 75；3000 局 0 失败）。

**回答「均匀吗」**：

- **单局内**：每块在剩余空闲区里均匀。
- **跨局汇总**：不均匀。按钮加板平均占去区域 34%（12.5～49.5%）；6×6 格的相对密度在 0.65～1.38 之间（KS p < 1e-43）；靠墙、靠角是均匀水平的 1.2～1.46 倍，这是逐个放置不重叠方块的正常副作用；按钮带只有 0.65～0.74。
- **颜色与位置独立**：2000 局置换检验在 α=0.05 下的触发率为 4.9%，正是名义水平。

**回答「为什么一堆红色在一起」**（ep3，seed 4400300）：

1. 12 块里 7 块红色：出现 ≥ 7 块同色的局占 22%。
2. 按钮在 (-0.155, 0.178)、板在 (0.050, -0.006)，只剩靠机器人一侧 x ≈ -0.25 的一条空带；6 块红色落在 x∈[-0.26,-0.18]，也就是画面上方靠机器人那一侧。
3. 事后挑出红色做的检验 p = 0.028 / 0.009，按选色、选轴做多重校正后 p = 0.0086。约 **4.0%** 的 V4 局至少这么极端，3 个选中局里至少出现一次的概率为 11.5%。
4. 障碍框缺陷让 red_0 与 red_2 只隔 **8.4 mm**；远侧的透视又压缩了 15～27%，看起来更挤。

**改法（L40～L42）**：

- **A（修缺陷）**：xhard 下放下的方块改用 `cube_obb2d_exact` 预制框。
  - 离邻居不到 20 mm 的方块从 23.3% 降到 0；
  - 最近邻中位距离从 80.0 mm 升到 85.8 mm；
  - 同色 9 cm 连通团 ≥ 4 块的局从 6.3% 降到 3.8%；
  - 0/3000 失败。
- **B（同色成团上限）**：先放 12 个槽位，只做几何；再按 V4 的语义分配颜色；如果最大同色连通团（连通阈值 0.09 m）超过 3 块，就**追加**一次 `randperm(12)` 重排颜色，最多 64 次。
  - 只有 3.8% 的局需要重排，平均 0.047 次，0 次用到兜底；
  - 团 ≥ 4 块降到 0；
  - 过度混匀只有 2.8%（反向置换检验 p < 0.05 的比例），没有变得不自然地规整；
  - **位置完全不变**，只换颜色标签。
- **不推荐**：放置后打乱颜色、交错生成序：V4 的标签本来就可交换，统计上无效。蓝噪声铺点：汇总密度反而更不均匀（CV 0.28～0.33），随机数多 3～6 倍。限制每色块数：会改配额规则，平移整条流。

新规格键：`layout.slots.<k>`、`objects.slot_assignment`、`objects.color_redraws`、`objects.color_mix_fallback`；`layout.cubes.*` 保留，改由 record() 写入。

### 2.7 PickXtimes / SwingXtimes：边角偏置与障碍框缺陷是主因

**PickXtimes 的 generator**（离线副本与 20 行规格逐位一致，包括 `target_cube_idx`）。一个 `torch.Generator(seed)` 依次抽：

1. 按钮 `rand(2)`；
2. `randperm(3)` 颜色顺序；
3. 一次占位用的 `randint(3)`；
4. **目标圆盘**（G1：先放盘）：在 x∈[-0.26,0.06]、y∈[-0.16,0.16] 均匀抽，离按钮至少 8 cm；
5. **3 个有色方块**：`spawn_random_cube`，region [-0.1,0]±0.2，`corner_bias=0.5`，256 次；
6. 在有色方块中 `randint(3)` 选目标；
7. **3 个干扰方块**：同一区域均匀抽，不加偏置。

**bias 在哪**：`corner_push` 对**每个轴分别**做 `t = 2u−1`、`t' = sign(t)|t|^p`，其中 `p = 1/(1+4b)`，b = 0.5 时 p = 1/3。联合分布的质量因此集中在 4 个角格：拒绝前 92.7%，拒绝后 91.3%（均匀采样为 50.6%）。按钮通常堵住一个近机器人角，圆盘可能再堵一个，被堵角上的抽样会被拒绝、改落到剩下的角，于是：

| 指标（3000 局） | V4 | 同规则、均匀 | 同规则、均匀、精确 OBB |
|---|---|---|---|
| ≥2 个有色方块挤在同一角格 | **44.5%** | 14.3% | 12.3% |
| 有中心距 < 6 cm 的对 | **15.5%** | 15.8% | 0 |
| 有中心距 < 7 cm 的对 | 40.5% | 43.8% | 11.3% |
| 8 cm 连通的三块团 | 13.7% | 18.6% | 6.7% |
| 10 cm 连通的三块团 | 45.3% | 56.3% | 46.2% |

**归因**：

- 同角挤压的约 30 个百分点来自 corner_bias；
- < 6 cm 的对 100% 来自障碍框缺陷；
- 松散的 10 cm 团主要由密度决定：理想 Poisson 6 cm 过程也有 41%。

**其他加重因素**：按钮总在靠机器人那一边，有色方块远侧占 56.8%、近侧 38.9%；整个区域在 256×256 画面里只占 **11.0%**；近机器人处 6 cm 只有 8.5 px（近相机处 16.2 px）。

**ep3（seed 4100300）**：两个近机器人角被按钮和圆盘堵死，推力只能把有色方块推到远侧。红、蓝挤在远右角格（相距 10.3 cm），再加上青色干扰，在 x∈[-0.01,0.07] 排成一行 4 块。**ep6** 则是 3 个有色方块同在一个象限（V4 下 1.4% 的事件），蓝绿只隔 5.5 cm，只有在蓝色障碍框退化时才可能出现。

**SwingXtimes**：**没有任何 corner_bias**。

- 有色方块循环**被所有档共用**：在 [-0.1,0]±0.25 均匀抽，之后再放两个圆盘，最后放 3 个干扰（避开圆盘，所以 x 向呈 U 形分布）；
- 障碍框缺陷使 7.3% 的局有 < 6 cm 的对（冻结规格中 2/10，分别 4.8 cm、5.4 cm）；
- 它比 PickXtimes 松：10 cm 三块团 22.2%，对比 45.3%；
- ep3 的斜排三块相距 12.7 cm 和 9.3 cm，是偶然布局，加上近机器人处透视把间距压缩了一半。

**改法（L43～L46）**：

- **PickXtimes（推荐 P1）**：
  - 保留 J5（3 块都用 corner_bias 0.5），另加「3 个有色方块各占不同象限」，象限以 (-0.1, 0) 划分；
  - 6 块之间中心距 ≥ 0.08；
  - 精确 OBB；
  - `max_trials` 设为 1024。

  效果：同角格 44.5% → 0，同象限 58.9% → 0，< 8 cm 的对 → 0，10 cm 三块团 45.3% → 19.9%；目标到边缘的中位距离 1.75 → 1.63 cm（推向边角的意图保住）；reset 失败 0.97%（256 次时为 3.53%）。
- **SwingXtimes（P2）**：共用的有色方块循环加显式的 difficulty 分支，非 xhard 一支逐字保留原代码；xhard 加精确 OBB 与 8 cm 间距。

  效果：< 6 cm 的对 7.3% → 0，< 7 cm 的对 23% → 0，10 cm 三块团 22.2% → 10.3%；圆盘放不下的失败率 1.9% → 3.6%（由 F2 重抽吸收）。
- **可选（L46）**：把 PickXtimes 方块区扩到半宽 0.25。RMS 分散度 +36%，10 cm 团降到 4.3%；但远角离基座约 0.78 m，最多 15 次抓放循环下的可达性没测过，要先做演示探针。

**⚠ 位置捷径风险**：在 J5 与 P1 下，有色候选块都在角上、干扰块在中间，仅凭位置就能区分候选与干扰。若这对基准有影响，需要用户另行决策。

### 2.8 VideoRepick：均匀摆放，全部方块参与交换

**现状**（离线副本与 10 行规格逐位一致；离线 D5 预测与模拟器 37/37 一致，搭档 36/37 一致，唯一的不一致是近平局）：

- 从 medium 派生，clutter 6 块（G2），区域 [-0.1,0]±[0.2,0.25]，每局同色、色值任意（C2/J3）；
- 按钮挖掉采样矩形的 **22.6%**；
- 目标 `randint(0,6)`；
- 发起者 = [目标] + `randperm(5)[:2]`（B12），第 k 次用 `swap_indices[k % 3]`；
- 搭档在窗口起点按实际 XY 取最近邻（`position_axes [0,1]`）；
- D5 扫掠检查在 xhard 生效。

**回答「生成要均匀」**：V4 采样本身没有生成序漂移，但**均匀随机不等于铺得开**。2400 局中：

- ≥3 块挤在同一个六分之一区域的有 26.9%；
- 画面某一侧 ≤ 1 块的有 13.5%；
- 最近一对的中心距中位只有 0.079 m；
- 按钮使边际分布呈 U 形；
- 整个区域只占画面桌面像素的 14.3%（第 56～128 行）。

**回答「所有 cube 都要 swap」**：3 个固定发起者加最近邻搭档，而槽位集合在交换中从不改变，每个发起者只能在自己的最近邻链上来回。

- 6 块全部动过的局只有 **17.0%**，只动到 3 块的有 9.4%；
- 目标最终回到原位的有 35.7%；
- 单局内同一对最多重复 5.77 次。
- **ep3**（seed 4900300，12 次交换，发起者 bin_5、bin_4、bin_0）：(5,2),(4,3),(0,2),(5,0),(4,3),(0,5),(5,0),(4,3),(0,5),(5,0),(4,3),(0,5)。bin_4↔bin_3 来回 4 次，净效果为零；**bin_1 一次没动**。

**改法（推荐 R，L47～L51）**：

```text
(1) 摆放：spawn_random_cube(..., extra_reject=「离已放方块中心 < 0.12」)，每次 trial 仍是 3 个 rand
(2) 发起者：randperm(5) 原本就抽了，只是 V4 只取 [:2]，现在用满
    seq[k] = 目标（当 k % 3 == 0），否则按 perm 顺序轮转其余 5 块  → 6 块全部发起，不新增抽样
(3) 追加一次抽样：u = torch.rand(n_swaps)，记为 objects.swap_partner_u
(4) 新增 VideoRepick._plan_swaps_xhard：
    在名义槽位上，用 cube_shape_specs(hs + 0.005) 按距离排序其余槽位
    过滤掉扫掠不可行的（check_swap_sweep，按无序对缓存）和「重复上一对」的
    取前 2 个，用 u[k] 在其中均匀选一个
    记 actions.swap_pairs.<k>（value，在 reset 时进规格）
    某步没有可行搭档 → 抛真 SceneGenerationError（依赖 L3）
(5) step：xhard 用规划好的搭档替代最近邻循环；
    D5 的 _check_swap_sweep_from_actual 保留，作为运行时守卫与回放交叉核对
```

**实测**（离线 1500～2400 局；最小距 0.12、余量 5 mm、k = 2、交错发起）：

| 指标 | V4 | V5 R |
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

**最小替代方案 M**（只加间距与全员发起，搭档仍用运行时最近邻）：全员参与 100%、D5 3.3%，但交换仍很重复：目标回原位 37.2%，同一对最多重复 3.38 次。

**⚠ 陷阱**：

1. 规划出的路径更长（均值 0.19 m，最大约 0.30 m，V4 约 0.12～0.16 m），而窗口固定 50 步，方块移动速度会快到约 1.5 倍，要人工看片。
2. `_resolve_sampling_config` 对 native 的 `object_selection` / `swap_selection` 做 JSON 全等检查，这些检查**不改**（它们保护原三档）。新规则全部挂在 `decision.xhard` 下，xhard 代码不再读 native 的 `swap_remaining_count` 与 `position_axes`。
3. **完整方案 R 没有在模拟器里跑过**，只跑过最小方案（3 个 seed：1 成功，2 次 D5 拒绝都被离线预测到）。

### 2.9 布局简图（V5 改动后）

**记号**：俯视，**横轴 y、纵轴 x**，机器人在下方（x ≈ −0.615）。`▒` 表示原区域（不动），`░` 表示 V5 新增或改变的区域，`▣` 表示容器，`●` 表示方块。

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

#### ButtonUnmaskSwap：按钮算进内部后的矩形带

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
   16 个（8 个含 cube）；每个内环窗口同时有一对外环容器沿 ±0.07 的车道对换（2.2）
```

#### MoveCube：各物体自身框的 30% 面积中心区（禁区）

```text
   杆根（每侧一个抖动框，半宽 0.05）      goal（demo 半宽 0.11 / exec 半宽 0.06）   方块候选（半宽 0.10）
   ┌──────────────┐                      ┌──────────────────┐                     ┌────────────────┐
   │ ░░░░░░░░░░░░ │                      │ ░░░░░░░░░░░░░░░░ │                     │ ░░░░░░░░░░░░░░ │
   │ ░░ ┌──────┐ ░░ │                    │ ░░ ┌──────────┐ ░░ │                   │ ░ ┌──────────┐ ░ │
   │ ░░ │ 禁区 │ ░░ │ 半宽 0.0274         │ ░░ │   禁区   │ ░░ │ 0.0602 / 0.0329   │ ░ │   禁区   │ ░ │ 0.0548（候选与最终都查）
   │ ░░ └──────┘ ░░ │ 中心 (0, ±0.2)      │ ░░ └──────────┘ ░░ │ 中心 (0,0)        │ ░ └──────────┘ ░ │ 中心 (0,0)
   │ ░░░░░░░░░░░░ │                      │ ░░░░░░░░░░░░░░░░ │                     │ ░░░░░░░░░░░░░░ │
   └──────────────┘                      └──────────────────┘                     └────────────────┘
   禁区边长 = 框边长 × √0.3 = 0.548；每次抽样恰有 30% 落进禁区被拒；corner_bias 归零
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

#### PatternLock：5×5@0.1 → 6×6@0.08（占地不变）

```text
   V4 5×5，间距 0.1                         V5 6×6，间距 0.08
   x=+0.1  o   o   o   o   o                x=+0.10  o  o  o  o  o  o
   x= 0    o   o   o   o   o                x=+0.02  o  o  o  o  o  o
   x=-0.1  o   o   o   o   o                x=-0.06  o  o  o  o  o  o
   x=-0.2  o   o   o   o   o                x=-0.14  o  o  o  o  o  o
   x=-0.3  o   o   o   o   o                x=-0.22  o  o  o  o  o  o
          y=-0.2 … +0.2                     x=-0.30  o  o  o  o  o  o
   节点 [20,24]，11% 落在 25～35 s            y=-0.2 … +0.2；节点 [30,33]，100% 落在 25～35 s
```

### 2.10 改动一览

**关闭态**是指 easy/medium/hard 在 V5 代码下的行为，必须与 `0baff09` 逐位相同。

| 文件 | 锚点 | 改什么 | 关闭态 | 开启态（xhard） |
|---|---|---|---|---|
| `utils/object_generation.py` | `spawn_random_cube` / `spawn_random_target` | 新增参数 `extra_reject=None` | 默认 None 整段跳过，逐位不变 | 各议题传入闭包 |
| `utils/xhard.py` | 新增 `cube_obb2d_exact`、`footprint_gap`、`center_zone_half`、平衡色轮转、同色连通团 | 纯函数，无随机数 | 不被调用 | 被各环境 xhard 分支调用 |
| `utils/bin_collision.py` | 新增 `check_multi_swap_sweep` 与认证预筛 | 只新增，`check_swap_sweep` 的判定不变 | 不被调用 | Swap 两环境与 VideoRepick 的规划期/运行时用 |
| `utils/unmask_distractors.py` | `spawn_ring_distractor_bins` 的校验与颜色；新增独立停放 helper | 校验改为 `0≤lo≤hi≤count`；三色平衡轮转；1024 次 | 原三档不进此模块 | 2.1 / L14 |
| `utils/unmask_swap_xhard.py` | `XHARD_DISTRACTOR`、`sample_distractors`、`build_distractors`、`predict_swap_sweeps`，新增 `plan_distractor_swaps` | 统一采样器、带序号命名、`cube_bins` 映射、外环规划 | 原三档不进此模块 | 2.1 / 2.2 |
| `VideoUnmask.py` / `ButtonUnmask.py` | `XHARD_DISTRACTOR`、`_native_decision` | 环带 / 数量 / 含 cube 范围 | 不变 | 15 / 14 个 |
| `VideoUnmaskSwap.py` / `ButtonUnmaskSwap.py` | `_spawn_xhard_distractors`、`_check_swap_sweep_from_actual`、`step`（在锁定循环之外）、`_native_decision`；BUS `_load_scene` 的截断 | 外环规划与执行、联合检查、内环预判拒绝、异常类 | 不变（AST 锁仍绿） | 2.2 |
| `InsertPeg.py` | `config_xhard`、`_initialize_episode` 的 xhard 分支；删除 `_xhard_place_near_target_peg` | 四根同一采样器、轮廓间隔 | 原生循环逐字不动 | 2.3 |
| `MoveCube.py` | `config_xhard`、`_native_decision`、`_load_scene` 的各取值点、`_sample_cube_center` | 中心区拒绝；`corner_bias=0`；执行段方块不避让演示段方块 | 不变 | 2.4 |
| `PatternLock.py` | `config_xhard`、`_native_decision`（`grid_spacing`）、`_load_scene`（取间距、耗尽即抛错） | 6×6@0.08、[30,33] | 回落 native 0.1，逐位不变 | 2.5 |
| `RouteStick.py` | `config_xhard`，新增冻结 L 范围的 decision 键 | L = [15,21] | 不变 | 2.5 |
| `BinFill.py` | `_load_scene` 的 xhard clutter 分支拆成槽位、配色、建 actor 三段；`_resolve_sampling_config` | 精确 OBB、同色成团上限 | `native_dynamic` 逐字不动 | 2.6 |
| `PickXtimes.py` | `XHARD_DECISION`、`_spawn_scene_objects_xhard`、`_spawn_distractors_xhard` | 不同象限、8 cm、精确 OBB、1024 次 | `_spawn_scene_objects_native` 不动 | 2.7 |
| `SwingXtimes.py` | `XHARD_DECISION`、`_load_scene` 共用循环加显式 difficulty 分支、`_spawn_distractors_xhard` | 8 cm、精确 OBB、异常类 | 非 xhard 一支为原代码 | 2.7 |
| `VideoRepick.py` | `config_xhard`、`_native_decision`、`_load_cubes_xhard`；新增 `_plan_swaps_xhard`；`step` 的 xhard 搭档分支；`_load_scene` 的异常类 | 0.12 m、全员发起、规划搭档 | 不变 | 2.8 |
| `scripts/parity/v4_*.py`、`scripts/eval/v4_eval.py` | `DEFAULT_SAMPLING`、组合循环等 | 以参数化方式支持 `newtask-v5` 与 `v5-01`，默认值不变 | V4 命令照旧可用 | V5 用新参数 |
| `scripts/configs/newtask-v5/` | 新目录 | `sampling_config.json`、`combos.json`、`v5-01/specs.jsonl` | — | — |
| `tests/lightweight/` | `test_v4_xhard_*` 八个文件，以及 swap 调度/窗口测试 | 断言改为 V5 语义，并加第四节各判据对应的单测 | 原三档断言不放宽 | — |

## 三、改动前后链路

链路沿用 V4：`sampling_config` → 抽签（只 reset）→ `drafts.jsonl` → 冻结 `specs.jsonl` → 实跑（h5 + mp4 + `results.jsonl`）→ 推理（`eval_results.jsonl`）。下表逐跳说明 V5 **改不改数**：

| 跳 | 产物 | 规模 / 形状 | V5 改动 | 这一跳改不改数 |
|---|---|---|---|---|
| ① 快照 | `scripts/configs/newtask-v5/sampling_config.json`（16 任务 `{decision, native}`） | 一份 JSON，内嵌进规格 header | 12 个环境的 `decision.xhard` 键形状改变；原三档部分逐字不变（V0） | 改（只改 xhard 键） |
| ② 抽签 | `artifacts/newtask-v5/v5-01/draft/drafts.jsonl` | 每环境攒 10 条 reset 成功、最多 30 次 | 12 个环境的 xhard 取值改变（值、个数、次序），新增规格字段见各节；4 个未动环境与 v4-01 逐位相同；reset 拒绝率上升（VideoRepick 约 8.4%、SwingXtimes 约 3.6%、PickXtimes 约 1%、Swap 两环境 1.3～10.7% 加上外环重抽） | 改 |
| ③ 冻结 | `scripts/configs/newtask-v5/v5-01/specs.jsonl` | 160 行，48 条 selected | 代码只做参数化；键集按新 schema 精确比对 | 不改（沿用封套契约） |
| ④ 实跑 | `artifacts/newtask-v5/v5-01/rollout/<label>/` | 48 条加递补，跑两遍 | Swap 两环境的 `step` 多一条外环交换循环（不增加步数）；VideoRepick 用预规划的搭档；PatternLock/RouteStick 每局帧数约增 40～50%，视频与 h5 体积随之增加 | 改（演示内容变化） |
| ⑤ 推理 | `artifacts/newtask-v5/eval/<run>/eval_results.jsonl` | 16 局冒烟加 48 局全量 | 代码不改；预算仍为 1301 步；RouteStick/PatternLock 的 oracle 余量降到约 20% | 不改 |

## 四、验收判据

每条都写明：查什么、怎么查、为什么这条判据能成立、判定行。**最终验收看具名判定项，不用一条笼统的 PASS 代替。**

| 判据 | 查什么 / 怎么查 | 为什么能成立 | 判定行 |
|---|---|---|---|
| V0 | 静态 `git diff`：`config_easy/medium/hard`，以及原三档消费的 `NATIVE_SAMPLING` 键；另对剥掉 xhard 的 decision 跑 `assert_native_decision` | V5 的改动只许落在 `decision.xhard` 或 xhard 分支，这些块里出现任何 diff 都直接违反 H2/N12 | `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0` |
| RESET_REGRESSION | `scripts.parity.v4_reset_probe probe`（原三档 144 条），与 `artifacts/newtask-v4/probe/base-13e.json` 逐字节 diff；每合并一组环境跑一次 | 共用钩子 `extra_reject` 与新的 bin_collision 函数，只有默认路径完全惰性才安全；reset 级取值能廉价暴露任何随机流或接受判据的漂移 | `RESET_REGRESSION=PASS compared=144 diff=0` |
| V1 | V3 的 144 条子集，本机、单 worker、相近负载，基线提交与 V5 各跑一遍，HDF5 逐位比。V4 的 V1 基线 h5（117 GB）已在 12.95 清理，**两边都要重新生成** | 硬闸门（N4）。reset 探针看不到求解器与 `step` 路径（例如 AST 锁定的交换循环） | `NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0` |
| V5_UNTOUCHED_XHARD_PARITY | 用 v4-01 的 seed 重抽 StopCube、PickHighlight、VideoPlaceButton、VideoPlaceOrder，逐值比对规格 | 这 4 个环境在 xhard 下也调用共用的 `spawn_random_*`；逐位相同就证明新参数和新 helper 在不该生效的地方完全惰性，它们的 V4 V6 证据也可以沿用 | `V5_UNTOUCHED_XHARD_PARITY=PASS envs=4 rows=40 diff=0` |
| V5_SCENEGEN_CLASS | 对 5 个环境强制一个不可行的 xhard 配置后 reset | 遮蔽已经靠 import 自省证实，只有真的抛一次才能证明 raise 与 except 两处都换过来了 | `V5_SCENEGEN_CLASS=PASS envs=5 raised=SceneGenerationError typeerror=0` |
| V5_REPLICA_PARITY | 12 个被改动的环境，各导出 ≥ 10 个 xhard seed 的规格，与更新后的离线副本逐值比对 | 本计划的可行性、均匀性、D5 数字全部来自与 V4 逐位一致的副本；只有新副本也等于新代码，这些数字才能迁移到 V5 | `V5_REPLICA_PARITY=PASS envs=12 seeds>=120 exact=all` |
| SAMPLING_SNAPSHOT | `tests/lightweight/test_sampling_config_split.py::test_snapshot_matches_source`，加上 `scripts/parity/train_split_audit.py` 的 config-map | header 内嵌快照；未被消费的键（例如残留的 `near_target_distractor`）会让 V3g 的归因失去意义 | `SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0` |
| V5_UNMASK_RING / DENSITY / HALF_CUBE / NAMES | 对每个 V5 候选检查：请求数 = 放下数 = 配置数；中心都在环带内；`visible_in_camera(bin_corners)` 为真。单测在 1 mm 网格上复算 N；含 cube 数在 [floor, ceil] 内，每色数量差 ≤ 1；n_cube=8 时 reset 无重名 | 直接编码用户要求（一圈、可见、同密度、一半无 cube），同时消除 V4 的线性可见性漏洞与重名崩溃 | `V5_UNMASK_RING=PASS VU=15 BU=14 VUS=15 BUS=16 out_of_ring=0 not_visible=0 shortfall=0`；`V5_UNMASK_DENSITY=PASS envs=4 count_diff=0`；`V5_UNMASK_HALF_CUBE=PASS range_ok=1 color_imbalance_max=1`；`V5_UNMASK_NAMES=PASS duplicate_actor_names=0` |
| V5_UNMASK_INNER_PARITY | 用 V5 代码 reset v4-01 的 40 个 Unmask 身份，比较所有非干扰容器的规格路径 | 直接验证「新抽样只在末尾或在独立流上」这一 N5 主张 | `V5_UNMASK_INNER_PARITY=PASS rows=40 inner_diff=0` |
| V5_UNMASK_REVEAL | 揭示 72 步加完整交换段：检查落回精度，并报告单步耗时 | 22～24 个物体停在同一点已使单步变慢 3～10 倍；外环 cube 的堆叠尚未测 | `V5_UNMASK_REVEAL=PASS max_return_err_mm<=0.1 reveal_step_ms_p95=<r> swap_span_step_ms_p95=<s>` |
| V5_SWAP_JOINT_FEASIBILITY | 用实现后的采样器与规划器重跑 ≥ 300 布局/环境（`evc` 判据） | 这是两个议题各自都没测过的组合；汇总方的试算只是圆近似（0.997 / 0.970） | `V5_SWAP_JOINT_FEASIBILITY=PASS VUS_first_attempt>=0.95 BUS_first_attempt>=0.95 redraw_fail_B16<=1e-4 first_initiator_share=<report>` |
| MULTI_SWEEP_EQUIV / PREFILTER_EQUIV | 联合证明在单对时与 `check_swap_sweep` 比对（含 seed 4500300 sweep#1 这类接触案例）；预筛开/关各跑 ≥ 1000 个随机窗口 | H1 与 D5 的安全都建立在认证证明上；预筛只跳过已证明分离的对，所以判定必须完全相等 | `MULTI_SWEEP_EQUIV=PASS cases>=100 diff=0`；`PREFILTER_EQUIV=PASS cases=1000 diff=0` |
| OUTER_SWAP_PLAN / CERT / EXEC / CUBE_FOLLOW / STEP_BUDGET / VISIBLE | 每环境 50 次 reset，加上全部冻结行：规划窗口数 = n_swaps，逐窗复证；保持 qpos 跑完所有窗口，量外环终点误差与 cube 跟随误差；与 V4 比步数；在分割图中逐帧检查外环容器可见 | 把「每次内部 swap 外部也 swap」「也要支持碰撞检测」写成可核对的事实；渲染检查能抓到手臂遮挡与几何模型误差 | `OUTER_SWAP_PLAN=PASS resets=100 windows_planned_eq_n_swaps=100`；`OUTER_SWAP_CERT=PASS specs=N windows=W rejected=0`；`OUTER_SWAP_EXEC=PASS max_err_m<1e-3`；`CUBE_FOLLOW=PASS max_err_m<2e-3`；`STEP_BUDGET=PASS added_steps=0`；`OUTER_VISIBLE=PASS frames=F missing=0` |
| INNER_SWEEP_RESET_REJECT | 在 xhard 下 reset VUS seed 4500300（V4 实跑失败局）与一个 V6 BUS 失败 seed | V4 观测到的 8 次碰撞全部是内环对内环，这两个 seed 是真实反例 | `INNER_SWEEP_RESET_REJECT=PASS seeds=2 rejected_at_reset=2 class=SceneGenerationError` |
| INSERTPEG_V5 | 20 次真实 reset：6 对轮廓间隔都 > 0.03，杆与孔板间隔 > 0.01；20 个 seed 副本与环境逐值一致；静置 20 步横向位移 < 1 mm；V4 header 被拒 | 杆根距离判据挡不住重叠（汇总方复算目标杆与第 4 根重叠 26%）；只有在真实 reset 上量出的轮廓间隔才能证明保证成立 | `INSERTPEG_V5_SPACING=PASS min_pair_gap_m>0.03 min_box_gap_m>0.01`；`INSERTPEG_V5_RNG_ORDER=PASS exact=20`；`INSERTPEG_V5_SETTLE=PASS max_dxy_mm<1.0`；`INSERTPEG_V4_SPEC_REJECTED=PASS` |
| MOVECUBE_V5 | CPU 副本 ≥ 5000 seed 加 10 次真实 reset；记录拒绝次数；reset seed 1000442、1000446 | 这两个 seed 在真实模拟器里复现过执行段方块生成失败，能通过就证明修好了；中心区判据是用户的字面要求 | `MOVECUBE_CENTER_EXCLUSION=PASS seeds=5000 zone_violations=0 layout_fail=0`；`MOVECUBE_REJECTION_BUDGET=PASS exhausted=0`；`MOVECUBE_EXEC_SPAWN=PASS seeds=2 ok=2` |
| LONG_DEMO | 每个候选的 h5 `is_video_demo` 帧数；每个组合 `len(path_nodes)` 在范围内；oracle 速度执行（`DemonstrationWrapper`，max_steps=1300）；最大 elapsed_steps | 帧数与预算计法已由 h5 和代码双重证实；PatternLock 的数字来自离线模型（±1.3%），以真实 h5 为准 | `RS_DEMO_LEN=PASS rule=L*50 mismatches=0 min_frames=750 max_frames=1050`；`PL_DEMO_LEN=PASS in_band=all`；`PL_LEN_EXACT=PASS wrong_length=0`；`EXEC_BUDGET=PASS timeouts=0 max_success_count<=1100`；`FAILSAFE_MARGIN=PASS max_elapsed<=2500` |
| BINFILL_V5 | ≥ 2000 副本布局加全部候选：精确多边形面间隙；0.09 m 最大同色连通团；上限开/关时位置是否相同；反向置换检验 | 扎堆是偶然加缺陷（汇总方复算红色 NN p = 0.027、P(同色 ≥ 7) = 21%），所以修法是颜色约束加 OBB 修复，且不能挪动位置或把颜色排得过于规整 | `BINFILL_MIN_GAP=PASS violations=0`；`BINFILL_COLOR_MIX=PASS T=3 violations=0 fallback=0`；`BINFILL_REDRAW_APPEND_ONLY=PASS pos_equal=2000/2000`；`BINFILL_NOT_OVERMIXED=PASS anti_p05_frac<=0.06` |
| PICK_SWING_V5 | `cube_obb2d_exact` 在 1000 个 yaw 上的单测；3000 个副本布局；每环境 20 个 seed 的 reset 冒烟 | 同角挤压由 corner_bias 驱动（无障碍 MC：54.5% 对 13.7%），贴面由 OBB 缺陷驱动；每条指标对应一个机制，同时核对推向边角的意图仍在 | `V5_EXACT_OBB=PASS degenerate=0`；`V5_PICK_DISPERSION=PASS same_cornercell_ge2=0.000 min_pair_lt_0p08=0.000 in_corner_cell>=0.85`；`V5_SWING_SPACING=PASS min_pair_lt_0p08=0.000`；`V5_RESET_FEASIBILITY=PASS pick_fail<=0.010 swing_fail<=0.040` |
| VIDEOREPICK_V5 | 冻结行：两两距离、`actions.swap_pairs` 的覆盖；逐对复证；SpecRecorder trace 顺序单测；V6 与实跑中的 BinCollisionError 计数 | 用户的抱怨（ep3 的 bin_1 从未动过，已由 rng_trace 证实）与 J2 的 45% 长尾，都能在冻结规格和运行时直接量到 | `VR_MIN_CENTER_DIST=PASS min_d>=0.120`；`VR_ALL_CUBES_SWAP=PASS min_participants=6`；`VR_PLAN_D5=PASS rejected=0`；`VR_RNG_ORDER=PASS`；`VR_DEMO_D5=REPORT d5_rejected=k` |
| V6 | V5 的 `combos.json`（约 88 个组合），每组合 5 局，reset 级与演示级两级都报 | 口径 11。每个改了的范围（cube 数、L、节点数）都会新增或改变组合 | `COMBO_COVERAGE=PASS combos=C missing_combinations=0 zero_success_combinations=0` |
| FREEZE / V2 / V3g / V4f / V5e | 沿用 V4；V3g 的反例扩展到新叶子（`swap_partner_u`、`distractor_swap_pairs`、`slot_assignment`、`center_exclusion`、杆间隔） | reset 时的规划与推迟的 value() 必须确定性重放；新叶子没有反例会让死键漏过 | `FREEZE_DONE per_env_candidates=10 selected_total=48 candidate_shortfall=s`；`NEWVALUE_REPLAY=REPORT …`（K5）；`SPEC_BINDING=PASS missing=0 unused=0 unattributed_mismatch=0`；`SPEC_NEGATIVE=PASS cases=M diff_zero=0`；`NEWVALUE_FEASIBILITY=REPORT …`；`EVAL_PIPELINE=PASS episodes=N runtime_ok=N join_missing=0` |
| FROZEN_FILES | `git diff --quiet` 录像器；`scripts/evaluation.py` 与官方副本 diff；轻量测试的失败集合与基线比 | N2，以及不得通过挪动评估预算常量来吸收变长的局 | `RECORDER_FROZEN=PASS EVAL_PY_UPSTREAM=PASS LIGHTWEIGHT=PASS failure_set_equal_baseline=1` |

## 五、实施步骤

从易到难排序：先把只改范围的 PatternLock/RouteStick、近乎只改配置的 VU/BU 落地，最复杂的 Swap 两环境放最后。**每组合并后都要先过 V0 与 RESET_REGRESSION，才能进下一组。**

| 步 | 内容 | 闸门 |
|---|---|---|
| S0 | 用户答复 L1～L51，写回 1.4；打 V4 的 tag；记录三份基线：原三档 reset 探针（已有 `base-13e.json`）、v4-01 的 160 行 xhard 参考、轻量测试失败集合 | 决策齐备；基线失败集合已存档 |
| S1 | 离线联合复核（纯 CPU，不改代码）：用最终规则重跑 2.1×2.2 的联合可行性（≥ 300 布局/环境），并用最终定数重跑各议题 MC；有任何数字不达标就停下回报（N11） | `V5_SWAP_JOINT_FEASIBILITY` 与各议题的放置 MC |
| S2 | 共用基础设施，只加不改：`extra_reject`、`utils/xhard.py` 的新纯函数、`check_multi_swap_sweep` 与预筛、5 个环境的 K2 别名、xhard 专用停放 helper；**还不接入任何环境** | V0；RESET_REGRESSION；`V5_UNTOUCHED_XHARD_PARITY`（160 行全部相同，因为尚未接入）；MULTI_SWEEP_EQUIV；PREFILTER_EQUIV；V5_SCENEGEN_CLASS；轻量测试 |
| S3a | PatternLock（6×6@0.08、[30,33]、耗尽即抛错）加 RouteStick（[15,21]、L 范围进 decision） | V0 与 reset 探针；PL_LEN_EXACT；本机 oracle 探针 ≥ 3 seed |
| S3b | VideoUnmask 与 ButtonUnmask：环带配置、校验、颜色、停放（若 L14 通过）、密度单测 | V5_UNMASK_*；reset 探针；每环境 2 局本机演示 |
| S3c | MoveCube：中心区、`corner_bias=0`、执行段方块不避让、回放复核 | MOVECUBE_*；reset 探针；V5_REPLICA_PARITY（MoveCube） |
| S3d | InsertPeg：单一采样器、轮廓间隔、删除贴近带、回放守卫 | INSERTPEG_V5_*；reset 探针 |
| S3e | BinFill：槽位、配色、建 actor 三段，精确 OBB，同色成团上限 | BINFILL_*；V5_REPLICA_PARITY；reset 探针 |
| S3f | PickXtimes 加 SwingXtimes：不同象限、8 cm、精确 OBB、1024 次；Swing 共用循环加显式分支 | PICK_SWING_V5；reset 探针 |
| S3g | VideoRepick：0.12 m、全员发起、`_plan_swaps_xhard`、`step` 的 xhard 分支、异常类 | VIDEOREPICK_V5；AST 锁测试；reset 探针 |
| S3h | VideoUnmaskSwap 加 ButtonUnmaskSwap：统一采样器、外环规划与执行、联合检查、内环预判拒绝、BUS 截断修复 | OUTER_SWAP_*；INNER_SWEEP_RESET_REJECT；V5_UNMASK_NAMES；AST 锁与 swap 测试；reset 探针；`V5_UNMASK_RESET_TIME=REPORT` |
| S4 | 一次性重导 `scripts/configs/newtask-v5/sampling_config.json`，跑消费审计；README 补 V5 节 | SAMPLING_SNAPSHOT；V0 |
| S5 | 建 V5 `combos.json`，每组合 5 局，本机多 worker（J8）；有演示级零成功的组合就停下回报 | V6 |
| S6 | 抽签并冻结 `v5-01`：16 个环境，每环境 10 条，选 0/3/6 | FREEZE 自检；V5_UNTOUCHED_XHARD_PARITY（冻结行）；各议题的规格级闸门 |
| S7 | 实跑 48 条（含 H4 递补）× 2 遍，本机，保存视频与 h5 | V2（只报告）；V3g；V4f；RS/PL_DEMO_LEN；OUTER_VISIBLE；各类 REPORT |
| S8 | 推理：16 局冒烟加 48 局全量；RouteStick/PatternLock 的 oracle 预算核对 | V5e；EXEC_BUDGET |
| S9 | 重新生成 V1 的 144 条两侧基线并逐位比较；冻结文件核对；总报告与逐步报告；按步 commit | NATIVE_REGRESSION；FROZEN_FILES |

**测试预算**沿用 V4：每次提交前在 5 分钟内跑 `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q`，失败集合须与 S0 存档的基线相同。长任务一律用 detached tmux（第二部分三）。

### 5.1 实施后实测结果

（实施完成后在此追加，原计划不改写。）

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

以下编号可被正文引用；与 [AGENTS.md](AGENTS.md) 的强制规则冲突时，以 AGENTS.md 为准。**V4 的 N1～N12 全部延续**：N1 改动须留证，报告落 `docs/validation/newtask-v5/`；N2 录像器冻结；N3 不自填；N4 原值路径不许改坏；N5 按 L1 的答复读；N6 甲的产物只读；N7～N10、N11 传入即可生成；N12 既有缺陷只在 xhard 修。V5 新增：

- **N13 共用代码只加不改。** `utils/object_generation.py::_trimesh_box_to_obb2d` / `_safe_unit`、`utils/statechange.py`（`swap_flat_two_lane`、`lift_and_drop_*`）、`utils/bin_collision.py::check_swap_sweep` 的判定，以及 `spawn_random_bin` 都不得改语义。新能力一律通过默认关闭的参数或新函数引入。
- **N14 AST 锁定循环不动。** `test_real_swap_resolution_matches_baseline_and_preserves_ties` 抽取的 `for i in range(len(self.swap_schedule))` 循环不得插入外环逻辑；`_spawn_xhard_distractors` 必须仍是 `_load_scene` 的最后一句；`generate_dataset_newseed._require_ast` 检查的表达式不得变。
- **N15 V4 冻结产物只读。** `scripts/configs/newtask-v4/**`、`artifacts/newtask-v4/**` 不改不删。V4 推理钉在 `0baff09`；tag 名与是否推送待 S0 问用户。
- **N16 规划期数字须重证。** 本计划的统计数字多数来自离线副本；实施后未过 `V5_REPLICA_PARITY` 的，一律不得写成验收结论。
- **N17 回放必须复核。** 凡是新增了几何保证的环境（InsertPeg 间隔、MoveCube 中心区、VideoRepick 最小距），回放冻结规格时都要重查规则，违反即报错或记入 mismatch。原因是 `SpecRecorder.value` 回放时直接返回冻结值、不复核。
- **N18 拒绝循环里的记录纪律。** 带整段重抽的采样器（Unmask 外环、BinFill 配色）只在被接受的那次调用 `recorder.value`，尝试次数与配对用 `record()` 留痕。

## 一、按阶段、按文件的逐项改动清单

**这是待实施清单，不是修改记录。** 每步动手前把该步实际涉及的函数与改法列出来，与报告一并留证。

| 阶段 | 文件 / 锚点 | 拟改什么、为什么 | 关闭态行为 |
|---|---|---|---|
| S2 | `src/robomme/robomme_env/utils/object_generation.py::spawn_random_cube`、`spawn_random_target` | 新增参数 `extra_reject=None`：在 OBB/圆判据之后、`recorder.value` 之前调用 `extra_reject(x, y, yaw)`，为真即 continue；不抽随机数 | None 时不执行任何新增语句 |
| S2 | `utils/xhard.py` | 新增 `cube_obb2d_exact(pose, half) -> (c, A, h)`；`footprint_gap(rect_a, rect_b)`（有向矩形精确距离，重叠为 0）；`center_zone_half(area_ratio, half)`；`balanced_color_cycle(order, n)`；`max_same_color_component(xy, colors, link)`；各配单测 | 不被原三档调用 |
| S2 | `utils/bin_collision.py` | 新增 `check_multi_swap_sweep(pairs, bystanders)`：对每对自身、跨对的移动者两两、移动者对静止物，复用 `_prove_pair`；新增认证预筛（401 个 s 采样，并以 Lipschitz 界证明分离），只在新函数与显式开关的包装里使用 | `check_swap_sweep` 判定不变 |
| S2 | VideoRepick、SwingXtimes、PatternLock、VideoUnmaskSwap、ButtonUnmaskSwap 的模块头部 | 仿 `VideoPlaceOrder.py` 加 `_RealSceneGenerationError` 别名；raise 与 except 两处按 `difficulty == "xhard"` 选类 | 原三档仍是 TypeError（H2） |
| S2 | `utils/unmask_distractors.py` | 新增 xhard 专用停放 helper（L14）：每个物体一个画面外停放点，窗口与落回步不变 | 原三档不进此模块 |
| S3a | `PatternLock.py::config_xhard`、`_native_decision`、`_load_scene` | `grid 6`、`length [30,33]`、`spacing 0.08`；`decision['grid_spacing']={'xhard':0.08}`；取间距时回落 native；`for … else` 分支在 xhard 下抛真异常 | 间距 0.1、静默兜底都不变 |
| S3a | `RouteStick.py::config_xhard`、`_native_decision` / `_resolve_sampling_config` | `length [15,21]`；新增 xhard 的 L 范围 decision 键，由 header 冻结 | 原三档不变 |
| S3b | `VideoUnmask.py` / `ButtonUnmask.py::XHARD_DISTRACTOR`；`unmask_distractors.py::spawn_ring_distractor_bins` | 配置改为 15 / 14 个、环带 `[0.2425,0.3289]`、cube `[7,8]` / `[7,7]`、`color_rule balanced_cycle`、`max_trials 1024`；校验改为 `0≤lo≤hi≤count`；`reveal_distractor_bins` 接入停放 helper | — |
| S3c | `MoveCube.py::config_xhard`、`_native_decision`、`_load_scene`（杆抖动、goal、`_sample_cube_center`、`cube_2` 生成）、`_xhard_corner_bias`（或新的校验器） | 按 2.4 的伪码；`corner_bias 0.0`；`center_exclusion`；执行段 `include_existing=False` | 原三档 27 次抽样的路径不变 |
| S3d | `InsertPeg.py::config_xhard`、`_initialize_episode`，新增 `_xhard_sample_pegs`，删除 `_xhard_place_near_target_peg` | 按 2.3 的伪码；新记录与回放守卫 | 原生循环逐字不动 |
| S3e | `BinFill.py::_load_scene`（xhard clutter 分支）、`_resolve_sampling_config`，新增 `decision.configs.xhard.color_mix` 与 `cube_obstacle_obb` | 槽位 → 配色 → `spawn_random_cube(fixed_xy, fixed_yaw)` 建 actor；配色重排只在末尾追加 `randperm(12)` | `native_dynamic` 分支不动 |
| S3f | `PickXtimes.py::XHARD_DECISION`、`_spawn_scene_objects_xhard`、`_spawn_distractors_xhard`；`SwingXtimes.py::XHARD_DECISION`、`_load_scene` 有色方块循环、`_spawn_distractors_xhard` | 象限与 8 cm 规则经 `extra_reject`；放下的方块用 `cube_obb2d_exact` 作障碍；`max_trials` 1024（Pick）；新记录 `layout.cube_dispersion`、`layout.cube_min_center_dist` | `_spawn_scene_objects_native` 不动；Swing 共用循环的非 xhard 一支逐字保留 |
| S3g | `VideoRepick.py::config_xhard`、`_native_decision`、`_load_cubes_xhard`，新增 `_plan_swaps_xhard`，`step`（`if pair_idx2 is None` 内的 xhard 分支，并用 getattr 取默认值） | 按 2.8 的伪码；新规格路径 `objects.swap_partner_u`、reset 时写入的 `actions.swap_pairs.<k>`；`swap_initiators_remaining` 变为长度 5 | `NATIVE_SAMPLING` 与 JSON 全等守卫都不动 |
| S3h | `unmask_swap_xhard.py`（统一采样器、`plan_distractor_swaps`、带序号命名、`cube_bins`）；`VideoUnmaskSwap.py` / `ButtonUnmaskSwap.py::_spawn_xhard_distractors`、`_check_swap_sweep_from_actual`、`step`（锁定循环之外的两条新循环）、`_native_decision`；`ButtonUnmaskSwap._load_scene` 的截断修复 | 按 2.2 的伪码 | AST 锁绿；原三档不进 xhard 分支 |
| S4 | `scripts/configs/newtask-v5/sampling_config.json`（新建）；`scripts/README.md` 的 V5 节 | 一次性重导；消费审计 | V4 的配置目录只读 |
| S4～S8 | `scripts/parity/v4_specs.py`、`v4_combos.py`、`v4_rollout.py`、`v4_reset_probe.py`、`v4_demo_probe.py`、`scripts/eval/v4_eval.py` | 以新参数（配置目录、run id）支持 V5，默认值不变；V5 的组合循环写进 `v4_combos` 的 V5 分支，或新建 `scripts/parity/v5_*.py`（**不在 `scripts/` 顶层新增文件**） | V4 命令照旧 |
| 全程 | `tests/lightweight/test_v4_xhard_{videounmask_buttonunmask,unmaskswap,insertpeg,movecube,videorepick,pickxtimes,swingxtimes,binfill}.py`、`test_swap_schedule_generic.py`、`test_window_timeline.py`、`test_v4_xhard_unmask_distractor_reveal.py`、`test_bin_collision.py`、`test_TaskGoal.py`（若 Unmask 文本受影响） | 断言改为 V5 语义；新增第四节各判据对应的单测；`test_real_swap_resolution_matches_baseline_and_preserves_ties` 必须保持绿 | 原三档断言不放宽 |

## 二、对拍闸门总表

| 闸门 | 前置条件 | 判定行 |
|---|---|---|
| V0 | 无（静态，每步收尾都跑） | `NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0` |
| RESET_REGRESSION | `artifacts/newtask-v4/probe/base-13e.json` 存在 | `RESET_REGRESSION=PASS compared=144 diff=0` |
| V5_UNTOUCHED_XHARD_PARITY | S2 之后 | `V5_UNTOUCHED_XHARD_PARITY=PASS envs=4 rows=40 diff=0` |
| V5_SCENEGEN_CLASS | S2 | `V5_SCENEGEN_CLASS=PASS envs=5 raised=SceneGenerationError typeerror=0` |
| MULTI_SWEEP_EQUIV / PREFILTER_EQUIV | S2 | `MULTI_SWEEP_EQUIV=PASS cases>=100 diff=0`；`PREFILTER_EQUIV=PASS cases=1000 diff=0` |
| V5_SWAP_JOINT_FEASIBILITY | S1 用最终规则；S3h 后用实现复跑 | `V5_SWAP_JOINT_FEASIBILITY=PASS VUS_first_attempt>=0.95 BUS_first_attempt>=0.95 …` |
| 各议题闸门 | 对应的 S3x | 见第一部分第四节 |
| V5_REPLICA_PARITY | S3 全部完成 | `V5_REPLICA_PARITY=PASS envs=12 seeds>=120 exact=all` |
| SAMPLING_SNAPSHOT | S4 | `SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0` |
| V6 | S4；组合清单冻结 | `COMBO_COVERAGE=PASS combos=C missing_combinations=0 zero_success_combinations=0` |
| FREEZE | S5 通过 | `FREEZE_DONE per_env_candidates=10 selected_total=48 candidate_shortfall=s` |
| V2 / V3g / V4f | S7 两遍完成 | `NEWVALUE_REPLAY=REPORT …`；`SPEC_BINDING=PASS …`＋`SPEC_NEGATIVE=PASS …`；`NEWVALUE_FEASIBILITY=REPORT …` |
| V5e / EXEC_BUDGET | S8 | `EVAL_PIPELINE=PASS episodes=N runtime_ok=N join_missing=0`；`EXEC_BUDGET=PASS timeouts=0 …` |
| V1 | S9；两侧基线同机、相近负载 | `NATIVE_REGRESSION=PASS compared=144 sha_equal=144 field_mismatch=0` |
| FROZEN_FILES | 每次提交前 | `RECORDER_FROZEN=PASS EVAL_PY_UPSTREAM=PASS LIGHTWEIGHT=PASS failure_set_equal_baseline=1` |

比较器复用 `scripts/parity/train_split_parity.py::compare_h5_pair`（先比整文件 SHA-256，不同再逐路径比），V4 已在外层加了根属性与空文件前置检查，照用。

## 三、runbook

```bash
# 只读核验：录像器未改、五入口未增
git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py && echo RECORDER_FROZEN=PASS
ls -1 scripts/*.py    # 应恰好五个

# 每次提交前（≤5 分钟）
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q

# 原三档 reset 探针（每合并一组环境跑一次）
uv run --no-sync python -m scripts.parity.v4_reset_probe probe --out artifacts/newtask-v5/probe/<step>.json
uv run --no-sync python -m scripts.parity.v4_reset_probe diff artifacts/newtask-v4/probe/base-13e.json artifacts/newtask-v5/probe/<step>.json

# 单环境演示探针（本机，≤5 分钟一条命令）
CUDA_VISIBLE_DEVICES=0 timeout 290 uv run --no-sync python -m scripts.parity.v4_demo_probe --task MoveCube --n 4 \
  --sampling-config <v5 单任务配置> --out artifacts/newtask-v5/demo-probe/<name>

# 长任务（V6 / 抽签 / 实跑）一律 detached tmux；参数名以 S4 参数化后的实现为准
tmux new-session -d -s v5-draw \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.v4_specs draw --run-id v5-01 \
   --sampling-config scripts/configs/newtask-v5/sampling_config.json --candidates-per-env 10 --max-reset-attempts 30 \
   --out artifacts/newtask-v5/v5-01/draft/drafts.jsonl 2>&1 | tee artifacts/logs/v5-draw-v5-01.log; \
   echo \"EXIT_CODE=\$?\" >> artifacts/logs/v5-draw-v5-01.log"
# 冻结（纯 CPU）
uv run --no-sync python -m scripts.parity.v4_specs freeze --drafts artifacts/newtask-v5/v5-01/draft/drafts.jsonl \
  --sampling-config scripts/configs/newtask-v5/sampling_config.json --out scripts/configs/newtask-v5/v5-01/specs.jsonl
# 实跑两遍与比较（K4/K5：本机多 worker，只报告）
uv run --no-sync python -m scripts.parity.v4_rollout run --specs scripts/configs/newtask-v5/v5-01/specs.jsonl --label run1 \
  --official-root artifacts/train-parity/local-smoke-01/official-src --workers <n> --output artifacts/newtask-v5/v5-01/rollout
uv run --no-sync python -m scripts.parity.v4_rollout compare artifacts/newtask-v5/v5-01/rollout/run1 artifacts/newtask-v5/v5-01/rollout/run2 --report-only
# 推理
uv run --no-sync python -m scripts.eval.v4_eval --specs scripts/configs/newtask-v5/v5-01/specs.selected.jsonl \
  --out artifacts/newtask-v5/eval/<run> --max-steps 1300
```

等待 tmux 任务一律挂 Monitor 在日志上，按 CLAUDE.md 的写法过滤 `EXIT_CODE=|Error|Traceback`，管道各级都要行缓冲，不得用 sleep 轮询。

## 四、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | 大多数推荐设计的**演示级成功率没测**（InsertPeg 只到 reset 与静置；BinFill、Pick/Swing 只有副本；VideoRepick 只跑过最小方案 3 个 seed；外环交换 0 局演示；PatternLock 6×6 只有 3 个 seed） | S3 各步先跑本机演示探针；V6 每组合 5 局；演示级零成功的组合回报用户（N11） |
| 2 | 贴身环带加 15/16 个干扰加外环交换，其联合可行性只做过圆近似的试算；首选发起者仅 44% / 29% 可行，回退很多，对布局分布的偏置未刻画 | S1 与 S3h 两次 `V5_SWAP_JOINT_FEASIBILITY`；在规格里记录回退次数与重抽次数；不过闸就回到 L16 |
| 3 | 停放点堆叠：揭示段 22～24 个容器，交换段最多 11 个 cube，都在 (10,10,10) 停数百步；物理稳定性只测了 9 局揭示段 | L14 的独立停放点；`V5_UNMASK_REVEAL` 报告 |
| 4 | Swap 两环境 reset 墙钟上升（不加预筛 33～66 s）；抽签最多 30 次，V6 被放大 | L23 认证预筛（判定不变）；`V5_UNMASK_RESET_TIME=REPORT` |
| 5 | 共用函数加钩子，或 SwingXtimes 共用循环加分支，泄漏到原三档 | N13；默认惰性；RESET_REGRESSION、V5_UNTOUCHED_XHARD_PARITY、V1 三道闸 |
| 6 | AST 锁、末句约束被新代码破坏 | N14；每次提交跑对应测试 |
| 7 | 回放不复核规则，使旧规格悄悄带回重叠或中心布局 | N17 回放守卫；V4 快照被形状检查拒绝 |
| 8 | 多个环境的 reset 拒绝率同时上升，逼近「10 条成功、上限 30 次」 | 各议题都估计了尝试次数（VideoRepick 约 11 次得 10 条）；FREEZE 如实报 `candidate_shortfall` |
| 9 | RouteStick/PatternLock 的执行段用掉 1301 步预算的 77～81%，学习策略余量变小 | 上界不取到实测最大（L=21 而非 26）；报告逐局执行帧与预算；`evaluation.py` 不改 |
| 10 | PatternLock 6×6 在画面中节点间距只有约 11 px，难度可能部分来自感知 | L35 可改选 B（14.2 px）或 C |
| 11 | VideoRepick 规划路径更长，窗口固定 50 步，方块移动速度快到约 1.5 倍 | k = 2 而不是「任一可行」；可选路径上限 0.25 m；冻结前人工看片 |
| 12 | 画面与机型：所有模拟器证据来自本机 sm_89，且负载时高时低（load 35～600），墙钟数字只作参考 | 沿用 K4/K5；时间类指标一律只报告、不设闸 |
| 13 | PickXtimes 的位置捷径：候选块在角、干扰块在中间 | 列为用户可另行决策的事项；V5 不默认处理 |
| 14 | V4 推理与 V4 规格在 V5 代码上不可回放 | N15：V4 推理钉在 `0baff09` 或 tag |

## 五、盲区诚实清单

- **演示级**：见风险 1。本计划里的成功率都是本机小样本或离线推断，没有一条是判据级结果。
- **离线副本**：所有副本都在 V4 规则下与冻结规格逐位一致，但 V5 规则的副本是否等于 V5 实现，要到 S3 以后才能证明（`V5_REPLICA_PARITY`）。
- **障碍框退化率随数值路径变化**：float32 路径 66%，float64 为 49.8%，真实模拟器 5/11。Unmask 内环 `spawn_random_bin` 的容器 OBB 是否也退化，没有查过。
- **K2 遮蔽的路径**：汇总方只对 MoveCube（类）实际强制抛过一次；VideoRepick、SwingXtimes、PatternLock、Swap 两环境的 TypeError 路径是根据代码推断的。
- **按钮与手臂**：两者都不在碰撞模型里。BUS 在交换期间按按钮的风险，只用中心距阈值近似。
- **「扎堆」的主观性**：扎堆与均匀用的是代理指标（同角格、最近邻、连通团、覆盖半径、分侧计数），人眼观感只看了少量帧。
- **ButtonUnmask 的 14 个**：汇总方没有独立复算（需要按钮遮挡的期望）；BinFill 多重校正后的 4.0% 尾部、VideoRepick 在 0.12 m 下的放置率、MoveCube 的 10/10，也都没有第二方复算。
- **recovery 未建模**：I3 下 recovery 关闭，没有议题对它建模；若日后打开，Unmask 与 Pick 的 xhard 流都会移位。
- **未动环境仍带缺陷**：PickHighlight、VideoPlaceButton、VideoPlaceOrder 的 xhard 仍有障碍框退化，这 3 个环境的 clutter 布局没有重新评估（L2 (b)）。

## 六、留档与 commit 纪律

- commit subject 沿用 `12.<n> <中文描述>`；body 按 AGENTS.md 规则 7 的六项写全，并按规则 7 只 `git add` 本轮明确路径；提交后立即 `git push`。
- 每步收尾在 `docs/validation/newtask-v5/` 出 md 报告（N1）。
- 本计划的实测结果在实施后以 5.1 子节追加，**不改写原计划**。
- 用户对 L 项的答复写回 1.4：原问题保留，只追加「结论与落点」，做法同 V4 的 1.3。
- 规划期用到的调查脚本若要转成正式闸门，须改写成中文注释后，收进 `scripts/parity/` 或 `docs/validation/newtask-v5/*-scripts/`。

## 七、规划期证据索引

全部位于 `artifacts/newtask-v5/plan-probes/`（本机留档、未进 Git；由 2026-09-24 的会话 scratchpad 复制而来，已剔除 h5/mp4/pkl 等大件）。`out/` 存放 8 个议题与汇总方的原始结构化记录（英文内部记录，`<议题>.json` 与渲染后的 `.txt`）。

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
