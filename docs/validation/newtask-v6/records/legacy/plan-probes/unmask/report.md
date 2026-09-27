# V6 规划期调查 C：四个 Unmask 环境——交换对象均匀性与 3 档更难参数

> 2026-09-25；分支 newtaskRelease-v5，HEAD da77662；只读调查，由主会话代 subagent 落盘。依据：V5 计划 1.3、1.4 L1、2.2～2.7；docs/validation/newtask-v5/ 的 s2b、s2c、s3b、s3h、s6；V5 探针 unmask_ring/、unmask_swap/（复用 unmask_swap/replica.py 内环复刻，V5 已 20/20 逐值核对）。探针脚本与输出在本目录（见末节）。

## 〇、结论先行

1. **内环（4 个容器）能做到对象层面严格均匀，代价小。** 每次交换在窗口末精确对换位姿，一局里 4 个位姿槽不变，一次交换可不可行只取决于两者所占的槽对。每局只需对 6 个槽对各跑一次仓库精确判定（`check_swap_sweep_prefiltered`）得到「可行槽对图 G」。长方形锚点两条对角线几乎总不可行：VUS 6.6%，BUS 9.0%。推荐 S5「计数均衡贪心」并把「G 连通」作 reset 级接受条件：10000 局下对象参与频率 VUS [.2502,.2498,.2501,.2500]（卡方 p=0.997），BUS p=0.966；局内参与次数极差 ≤2 的局 100%，≤1 的 95.7%（VUS）/ 89.4%（BUS），立即撤销率 0。代价：BUS 的 G 连通率只有 66.5%，约 1/3 BUS 内环布局要被拒（VUS 95.4%）。
2. **V5 现状不均匀，根源是发起者抽样而不是碰撞。** 参与频率 VUS [.236,.283,.279,.201]，BUS [.218,.287,.287,.208]，p≈0；bin_3 永不发起的概率约 50%（其余三个约 16%）。`swap_initiator_indices=randperm(3)[:2]` 被当生成序号用（U5 索引混用），只可能是 0/1/2；bin_3 在 xhard 下恒为空容器（`selected=randperm(3)` 只覆盖 bin_0..2，10000 局 0 例外）。
3. **外环在 V5 路径约束下，局内均匀与算法无关，做不到。** 每窗 45 个槽对里平均只有 5.6（VUS）/ 3.6（BUS）对可行；某窗无任何可行搭档的槽占 28% / 44%；任何算法下 10 个干扰容器「全员参与」的局 ≤4.3%。最近邻对被拒主因是路径出画（vis，24%）与内环净距；BUS 另有 59% 槽对因离按钮太近被拒。干扰数加到 14 / 18 时零可行搭档的槽升到 37% / 50%（VUS）、50% / 61%（BUS）。
4. **三档参数硬约束是 BUS 的评测预算。** `scripts/evaluation.py` 写死 `max_steps_without_demonstration=1302`，BU/BUS 全部步数计入，BUS 交换段（65+33n 帧）也计入；VU/VUS 的交换与揭示在演示段里不计入。fail-safe 5000 对四环境不构成约束（最大约 1750 步）。
5. **pick 超过 3 必须加新颜色或新语义。** 被藏 cube 只有 red/green/blue：VU/BU 只给 `spawned_bins[:3]` 藏 cube，VUS/BUS 是 `hidden_bin_count_max=3`；干扰色池 yellow/cyan/magenta 是全局 `xhard.DISTRACTOR_COLORS`，PickXtimes/SwingXtimes 也在用，不能动；VUS/BUS 内环只有 4 个容器，pick 上限 4。

## 一、现状

| 环境 | 字段 | easy | medium | hard | xhard |
|---|---|---|---|---|---|
| VU/BU | 容器数 `config['bin']` / pick 数 `config['pick']`（→ `decision.pick_count`，规格 `objects.n_picks`） | 3/1 | 5/1 | 15/2 | 8/3 |
| VU/BU | 干扰数（`decision.xhard.distractor`；贴身环带 [0.2425,0.3289]） | — | — | — | 15（含 cube [7,8]）/ 14（[7,7]） |
| VUS | 容器 / swap [min,max] / pick [min,max] / 每次交换步数 | 3/[1,2]/[1,2]/50 | 4/[1,2]/[1,1]/50 | 4/[2,3]/[2,2]/50 | 4/[8,12]/[3,3]/33 |
| BUS | 同上 | 3/[1,2]/[1,2]/50 | 4/[1,2]/[1,1]/50 | 4/[2,3]/[2,2]/50 | 4/[6,8]/[3,3]/33 |
| VUS/BUS | 干扰数与外环交换 | — | — | — | 10 个，V4 环带 [0.2675,0.45]，每窗配一次外环交换 |

- VU/BU 没有任何交换字段。「pickup 次数」精确字段：VU/BU 是 `config_*["pick"]`，VUS/BUS 是 `pick_min/pick_max → self.pick_times`，都落到规格 `objects.n_picks`；揭示固定一次，窗口 [0,64)。
- VU/BU xhard 另有两项与原三档不同：`min_gap_factor` 0.75（原三档 2），揭示改用 `reveal_actors_parked` 独立停放。BU 构造器有一次 `constructor_rng` 抽 1～5 的 `num_repeats`，只占随机流位置。VUS 每次交换步数 = `scaled_window_steps(50, XHARD_SWAP_SPEED_MULTIPLIER=1.5)` = 33。
- **内环交换路径（VUS/BUS 相同）**：发起者：`_load_scene` 在主流上抽 `objects.swap_initiator_indices = randperm(3)[:2]`，再从其余生成序号抽 `objects.swap_initiator_third`；第 k 次发起者 `spawned_bins[swap_indices[k%3]]`。解析：bin_0..2 当发起者概率各 5/6，bin_3 为 1/2；实测「永不发起」VUS [.170,.159,.169,.502]，BUS [.169,.161,.164,.506]；发起次数占比 VUS [.283,.287,.282,.149]。搭档：在 step 里 AST 锁定的 `range(len(self.swap_schedule))` 循环中 idx2 为 None 时按实际位姿取 XY 最近邻（VUS 读 `swap_selection.partner.position_axes`，BUS 写死 `[:2]`；严格 <，平局取生成序靠前）。`_compute_dynamic_swap_candidates` 与 `_select_swap_pair_from_positions` 无调用者。碰撞检测：reset 时 `predict_inner_windows` 预演、`prejudge_inner_windows` 预判（L20），拒绝抛 `SceneGenerationError`；运行时 `_check_swap_sweep_from_actual → joint_sweep_from_actual`，用 `check_multi_swap_sweep` 对内环对与本窗外环对联合复核（认证预筛 L23）。锁定测试 `test_real_swap_resolution_matches_baseline_and_preserves_ties` 会抽出这段循环执行；VideoRepick 先例是在该分支里改调 `_xhard_planned_partner`。
- **外环交换路径（`utils/unmask_swap_xhard.py`）**：入口 `spawn_swap_distractors_v5 → plan_swap_distractors`，只用独立流 `distractor_generator(seed)`；`resample_distractor_layout` 整段重抽最多 16 次，每次放置后 accept 回调追加抽一次 `perm = randperm(count)`；`plan_distractor_swaps` 规划每窗外环对：发起者 `o = perm[(k+j)%count]` 顺延回退，搭档 `nearest_distractor`（XY 最近）；候选用 `evaluate_outer_candidate` 依次查 vis → btn → inner_clear → exact（干扰碰撞盒外扩 5 mm）。运行时 `run_outer_swaps` 在锁定循环之外，不增加控制步。随机流口径 L1(a)。
- **v5-01 实测帧数（12 条 h5）**：每次 pick 平均 100 帧（最多 126），每次 put down 平均 48（最多 53），每次交换恒 33。VUS 演示段 ≈ 66+33n（n=10 时 396）；BUS 前段 ≈ 65+33n（n=8 时 329）。总帧数：VU 441～507，BU 511～538，VUS 780～807，BUS 689～721。

## 二、均匀性

定义：U1 条件均匀 / U2 跨局边际均匀 / U3 局内均衡 / 每对等概率。

**内环（10000 局/环境）**。槽对可行率，顺序 (0,1),(0,2),(0,3),(1,2),(1,3),(2,3)：VUS [.863,.066,.994,.993,.066,.855]，BUS [.370,.092,.951,.957,.090,.362]；槽对中心距均值 VUS [.203,.255,.158,.158,.255,.203] m；G 连通率 VUS 95.4%，BUS 66.5%。

| 规则 | VUS 卡方 p | VUS 局内极差 | VUS 撤销率 | BUS 卡方 p | BUS 局内极差 | BUS 撤销率 | 整局可行 VUS / BUS |
|---|---|---|---|---|---|---|---|
| S0 现状 | ≈0 | 4.36 | .270 | ≈0 | 2.57 | .320 | 98.4% / 90.3% |
| S1 可行对均匀 | .285 | 3.79 | .270 | .506 | 3.23 | .393 | 99.97% / 99.0% |
| S1n 不许撤销 | .638 | 2.63 | 0 | .941 | 1.72 | 0 | 99.8% / 94.1% |
| S2 先发起者后搭档 | .854 | 3.71 | .275 | .762 | 3.12 | .403 | 99.97% / 99.0% |
| S2n 不许撤销 | .493 | 2.80 | 0 | .758 | 1.77 | 0 | 99.8% / 94.1% |
| S3 匹配牌堆 | .587 | 1.82 | .140 | .300 | 2.38 | .299 | 99.97% / 99.0% |
| S4 先定序列再拒布局 | .995 | 0.41 | — | .997 | 0.33 | — | 17.5% / 23.3% |
| S5 计数均衡贪心 | .967 | 0.54 | .002 | .518 | 0.91 | .050 | 99.97% / 99.0% |

S3 平均每局 2.57（VUS）/ 3.89（BUS）次「失衡事件」。S5 叠加 G 连通后：局内极差 VUS 0/1/2 = 5264/3871/407（p=.997），BUS 3618/2320/702（p=.966），撤销率 0。S4 把偏差转嫁到布局分布上，不推荐。结论：碰撞拒绝之后，对编号对称的规则在内环仍保持跨局边际均匀，因为 G 约束的是槽而不是对象；S0 的偏差来自发起者抽样。

**外环（count=10，10000 局/环境）**。放开「只找最近邻」后：第 2 近邻可行率 23% / 12%，第 3 近邻 8% / 2%；平均交换距离 0.170→0.227 m，整局可行率升到 99.9% / 98.3%。O4（计数均衡贪心）最好：未参与对象 28% / 43%（V5 现状 40% / 54%），撤销率 0.5% / 6.7%（现状 42% / 56%）。「全员参与」比例 VUS：O0 1.3%、O1 0.9%、O4 4.3%；BUS O4 0.9%。按序号边际有约 ±4% 单调偏差（后放置更挤），放置后序号随机重排可严格消除。放宽约束：去掉「路径全程可见」后零可行搭档槽 31.7%→15.0%（VUS）；再去内环净距为 9.3%（BUS 24.5%）。count 14 / 18 整局可行率（O4）VUS 99.9% / 100%，BUS 99.6% / 98.6%；全量枚举规划墙钟 p50 VUS 1.6 → 3.8 → 6.4 s。

**推荐**：内环 S5，在 reset 预规划整段序列（仿 VideoRepick，追加一次 `u=torch.rand(n_swaps)` 作并列打破），以 G 连通作接受条件；外环 O4，放置后序号随机重排，保留「不许立即撤销」。

## 三、三档参数建议（同步递增）

| 环境 | xhard（现） | X1 | X2 | X3 |
|---|---|---|---|---|
| VU | 干扰 15 / pick 3 | 20 / 4 | 24 / 5 | 28 / 6 |
| BU | 干扰 14 / pick 3 | 19 / 4 | 23 / 5 | 27 / 5（pick 6 时最坏余量 12%） |
| VUS | swap [8,12] / pick 3 / 干扰 10 | [12,14] / 4 / 12 | [15,17] / 4 / 14 | [18,20] / 4 / 16 |
| BUS | swap [6,8] / pick 3 / 干扰 10 | [9,10] / 4 / 12 | [11,12] / 4 / 14 | [13,14] / 4 / 16 |

- VU/BU 环带：现贴身环带 N=18 一次放满率 95% / 91%，N=20 只有 58% / 48%；放宽到 [0.2425,0.45] 后 28 个 100%、32 个 97.5% 以上。
- VUS/BUS 环带容量约 29 个（上界），不是瓶颈。
- BUS 最坏帧数：X1 1063（余量 18%），X2 1129（13%），X3 1195（8%）。VUS/VU：pick 6 最坏 1022；VUS 演示段 n=20 时 726 帧（24 s），不计预算。
- 帧数公式（最坏，每次 pick 125 + put down 52）：VU/VUS 非演示 177p−40；BU 119+177p−40；BUS 65+33n+177p−40。评测预算上限 1302。

## 四、内环 4→5/6（合成锚点，每种 1000 局）

正五边形 / 正六边形：G 100% 连通，最近邻距 0.16 / 0.15 m，全部在画面内；2×3 网格连通只有 65.7%，不可用。代价：内环最大半宽 0.236 贴近外环内界 0.2675，外环更挤（未测）；BUS 锚点需单独设计；pick 到 5/6 还得加颜色；`region4` 分支、`hidden_bin_permutation_size`、U5 索引混用都要在新档另写。

## 五、风险

R1 BUS X3 预算余量 8%；R2 BUS 的 G 连通率 66.5%；R3 AST 锁：reset 预填搭档会跳过锁定循环里的运行时复核分支，复核需另挂；R4 外环局内均匀需放宽约束或改布局，放宽会带回出画风险；R5 新颜色在 256 像素画面上可分辨性未验证；R6 揭示段 36 个物体的性能未实测；R7 近似口径：VU/BU 内部布局用 replica 复刻、障碍 OBB 近似；外环 H1 守卫按 V5 现状内环序列建立，内环改 S5 后建议把守卫改为覆盖 G 中全部可行槽对；R8 探针期间本机负载最高约 78，只影响墙钟。

## 六、待决项（调查方建议）

- D1「均匀」定义：(a) 可行者中均匀选发起者；(b) 跨局边际均匀；(c) 局内参与次数均衡；(d) 每对等概率。建议内环 (c)（含 b），外环 (b)。
- D2 内环算法：(a) S5 + G 连通；(b) S2；(c) S1；(d) S4。建议 (a)。
- D3 外环局内做不到均匀时：(a) 接受「边际均匀 + O4 尽量均衡」；(b) 去掉「路径全程可见」；(c) 沿环切向成对放置；(d) 不再加外环干扰数。建议 (a)。
- D4 维度组合：(a) 同步递增；(b) 分维度累加。建议 (a)。
- D5 pick 超过 3：(a) 新增第 4～6 种目标色（orange / purple / white）；(b) 允许重复目标色；(c) pick 止步于 3。建议 (a)。
- D6 VUS/BUS 内环扩到 5/6：(a) 不扩，pick 上限 4；(b) X2 正五边形、X3 正六边形。建议 (a)。
- D7 BUS X3 余量 8%：(a) 接受；(b) X3 pick 保持 3；(c) BUS 新档交换改 ×2 速（余量 17%）；(d) swap 降到 [12,13]。建议 (c) 或 (b)。
- D8 VU/BU 环带：(a) 放宽到 [0.2425,0.45]；(b) 保持贴身环带，上限约 16～17。建议 (a)。
- D9 新档用新难度键；xhard 与原三档逐位冻结，新档随机流按 L1(a) 允许原地移位。

## 七、探针文件

| 编号 | 脚本 | 输出 | 内容 |
|---|---|---|---|
| — | mclib.py | — | 公共库 |
| P1 | p1_h5_frames.py | .log / .json | v5-01 分段帧数 |
| P2 | p2_inner_mc.py、p2_analyze.py | p2_vus_summary.txt、p2_bus_summary.txt、p2_inner_*.json | 内环蒙特卡洛 |
| P2b | p2b_v5_initiators.py | p2b.log | V5 现状发起者分布 |
| P2c / P2d | p2c_balanced.py、p2d_connected.py | p2d.log | S5 与 G 连通 |
| P3 | p3_outer_mc.py、p3_analyze.py、p3c_coverage.py | p3*_summary.txt、p3c_vus.txt、p3_outer_*.json | 外环蒙特卡洛 |
| P3b | p3b_reasons.py | p3b.log | 外环拒绝原因与放宽约束 |
| P4 / P4b | p4_ring_capacity.py、p4b_ring_wide.py | p4.log、p4b.log | 环带容量 |
| P5 | p5_inner_count.py | p5.log | 内环 5 / 6 个容器 |
| — | t_timing.py | — | 单局判定耗时 |
