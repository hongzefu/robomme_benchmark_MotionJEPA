# V6 交换对象均匀化（S5 / O4）源码实现报告（副本草稿）

> 2026-09-25；副本 worktree `/data/hongzefu/v6-draft/swap`（分支 `v6-draft-swap`，从 newtaskRelease-v5 的 e1755f9 切出），主仓库源码未改一字。依据：NEWTASK_RELEASE_V6_PLAN 2.2 / 2.4 / 2.5、M5(a)、M6(a)、M7(a)；离线算法参照 `plan-probes/unmask/`（p2c_balanced、p2d_connected、p3_outer_mc）与 `plan-probes/videorepick/`（schemes.s5_balanced_retry）。只改 VUS / BUS / VR 的 xhard 分支，原三档逐位不变（见第四节 ④）。

## 〇、结论

| 验收 | 结果 |
|---|---|
| ① lightweight | 选相关子集 35 个文件 1020 项（全量在本机负载 45+ 下 25 分钟只跑到 5%，按规则改跑子集）：新 34 failed / 982 passed，旧（e1755f9 克隆）33 failed / 964 passed；**新增失败只有 1 项** `test_sampling_config_split.py::test_snapshot_matches_source`（V5 快照 `scripts/configs/newtask-v5/sampling_config.json` 与改后的 decision.xhard 不一致，属 V6 重冻时统一重导的快照，未改），其余失败集合与旧侧逐项相同 |
| ② 离线均匀性单测 | 新增 `tests/lightweight/test_v6_swap_uniform.py` 19 项全过（15 s）；10000 局：VUS 实测边际 G 抽样 p=0.998、极差 ≤1 100%；BUS p=0.937、≤1 99.83%（其余 2）；VR 6 槽随机图 p=0.994、≤1 95.7%；撤销全部 0 |
| ③ 真机 reset 200 次 | VUS：G 不连通拒绝 6/200（3.0%），其余 0 拒绝；极差 0/1 = 107/87（≤1 100%）、撤销 0、边际 [983,981,982,984] p=1.000。BUS：G 不连通拒绝 62/200（31.0%）；极差 0/1 = 99/39（100%）、撤销 0、p=0.999。VR：成功 118/200，与旧侧**逐 seed 成败完全一致**（200/200）；极差 0/1/2 = 41/69/8（≤1 93.2%）、撤销 0、全员参与 118/118；旧侧极差 ≤1 只有 15/118、撤销 128 次 |
| ③ 外环 O4 | VUS 未参与均值 2.57/10（25.7%，目标 ≤30%），撤销 9/1965 窗（0.46%，目标 ≤1%），跨局按序号边际 p=0.545；BUS 4.42/10（44.2%，目标 ≤45%），撤销 40/971（4.1%，目标 ≤7%），p=0.308 |
| ③ 真演示 4 局 | VUS 4/4 成功；BUS 3/4（1 局 reset 因 G 不连通被拒，属设计内拒绝，进演示的 3 局全成）；VR 3/4（1 局 reset 有孤立槽，与 V5 同一失败条件，进演示的 3 局全成）。h5 / 视频已删 |
| ④ 原三档逐字比 | 3 环境 × easy/medium/hard × 4 个 seed（11、12345、4500300、7800001）= 36 局，reset 后整份规格文档 + 交换调度 JSON **与主仓库同版源码逐字节相同** |
| 规格回放 | 三环境各导出一局 xhard 规格 → `native_episode_spec` 回放：mismatch 0、S5 序列与外环对一致；把第 1 次交换篡改成「立即换回」均被 `EpisodeSpecError` 拒绝 |

## 一、实现

### 1. 公共纯函数 `utils/swap_uniform.py`（新文件）
- `slot_pair_graph / graph_connected / isolated_slots / graph_edges`：可行槽对图 G。
- `plan_balanced_swaps`（S5）：候选 = G 的边 − 上一槽对（禁止立即撤销）；评分最小者平局均匀抽，再抽一次定发起方向；整条极差 > `accept_range`(1) 重排，最多 20 条，仍不满足取极差最小的第一条（不额外拒绝，保 reset 成功率）。评分口径两种：Unmask `max_sum`（p2c/p2d 口径），VR `sum_max`（schemes.s3_balanced 口径）；在 P2 实测 G 上两种口径结果逐局相同。
- `verify_swap_sequence`：回放复核（槽对可行、无立即撤销、越界 / 自换），同时给出 counts / range / undo 统计。
- `balanced_pair_groups`：外环 O4 的评分分组（上一对放最末，只在别无选择时用）。

### 2. VUS / BUS（`utils/unmask_swap_xhard.py` + 两环境）
- `decision.xhard.swap_plan_v6`（新键）：S5 申报值；`require_connected_graph=True`；`hidden_bin_permutation_size=4` 是 M5 的**独立开关**（删掉该键即回退 V5 的 `randperm(3)`）。
- `decision.xhard.distractor_swap` 换成 `v6_distractor_swap_cfg`：只换 `initiator_rule=balanced_greedy_o4` / `fallback=undo_only_if_no_other_feasible` / `partner`（均衡贪心、放置后 randperm 重排）三键，路径约束与其余数值逐项沿用 V5（M7(a)）。`parse_distractor_swap_cfg` 同时接受 V5 与 V6 两套规则，V5 纯函数与其单测不动。
- `_load_scene`：M5 `objects.selected = randperm(4)[:3]`（原表达式作为第一分支逐字保留，供历史抽取与对拍）；V5 发起者取值点照旧抽（主流位置不变），随后 `plan_inner_swaps_v6`：读实际位姿算 G（6 次 `check_swap_sweep_prefiltered`）→ `record layout.inner_swap_graph / inner_swap_graph_connected` → 不连通抛真 `SceneGenerationError` → 主流**追加一次** `objects.swap_plan_seed = randint(0, 2**62)`（value）→ 局部流上 S5 → 逐次 `value actions.swap_pairs.<k> = {"initiator","partner"}` → 复核 → `record objects.swap_plan = {counts, range, tries, undo}`；覆盖 `swap_pair{k}_idx1`，搭档存 `_xhard_swap_partners`。
- `step` 锁定循环：`if getattr(self, "_is_xhard", False): closest_actor = self._xhard_planned_partner(i, pair_idx1)`（仿 VR 先例），原三档分支缩进一层、表达式逐字不变；两对联合复核 `joint_sweep_from_actual` 照旧跑。
- 外环：内环窗口改由 `planned_inner_windows`（按 S5 序列预演）给出；H1 守卫改用 `graph_guard_windows`（G 的全部可行边，内环盒体相同，是实际序列扫掠的超集，R7）。`_plan_swap_distractors_balanced`：每次放置后独立流追加 `randperm(count)`（序号重排）+ 一个规划种子 → 重排后的公开布局上跑 O4（每窗按评分分组，首个含可行者的组里均匀抽）→ 被接受那次才 value：放置序布局仍由 `commit_distractor_layout` 落 `objects.distractors.*`（回放复核判据与 V5 相同，避免重排后点对 OBB 判据不对称），新取值点 `objects.distractors.label_perm`、`objects.distractors.swap_plan_seed`；`record objects.distractors.public`（重排后布局）与 `actions.distractor_swap_balance = {counts, unvisited, range, undo}`。建 actor、交换对、运行时一律用公开序号。

### 3. VR（`VideoRepick.py`）
- `decision.xhard.swap_plan` 换成 `initiator_rule=s5_balanced_pair`、`partner_rule=s5_balanced_greedy`、`s5`（`sum_max`、不要求连通），5 mm 余量与按钮障碍沿用 V5。
- `_load_cubes_xhard`：V5 的 `objects.swap_initiators_remaining` 照旧抽（位置不变、不再决定发起者），`objects.swap_partner_u`（rand(n)）换成 `objects.swap_plan_seed`；新 `_plan_swaps_xhard_v6` 一次算全 15 个槽位对得可行图 M（`record layout.swap_graph`），有孤立槽即 `SceneGenerationError`（与 V5 失败条件同口径，实测逐 seed 成败一致），S5 规划、逐次 value `actions.swap_pairs.<k>`、N17 复核、`record objects.swap_plan`；`objects.swap_initiators` 改为 record 实际发起序列。V5 的 `_plan_swaps_xhard` / `_plan_swap_partners_xhard` 保留（单测仍锁纯函数语义），xhard 不再调用。

### 4. 测试改动（AST / 申报值锁）
- `test_v4_xhard_unmaskswap::test_decision去掉xhard后与原值相同`、`test_v5_xhard_unmaskswap::test_decision_xhard为统一预设与外环交换配置块`：外环规则名改锁 V6 申报值，并锁 `swap_plan_v6`。
- `test_v4_xhard_videorepick::test_xhard_新值只挂在xhard子键下`：swap_plan 改锁 V6 申报值。
- `test_v5_xhard_videorepick`：`_reset` 绑定 `_plan_swaps_xhard_v6`；ALL_CUBES_SWAP 改为「发起者 = 实际序列、全员参与、极差 ≤2、撤销 0」；D5 去掉 nearest_k 候选池断言；按钮障碍改比可行图的边；RNG_ORDER 末项 `rand(n)` → `randint(0, 2**62)`、取值点 `swap_partner_u` → `swap_plan_seed`；篡改发起者 / 自换改为匹配 S5 复核的「越界或重复」。
- 锁定循环的历史对拍 `test_episode_action_sampling::test_real_swap_resolution_matches_baseline_and_preserves_ties` 与 `generate_dataset_newseed` 的 AST 抽取均未改、照过（xhard 判断用 `getattr(self, "_is_xhard", False)`，假环境无该属性时走原分支）。

## 二、计划到实施中的意外
1. **固定非对称 G 上跨局边际不均匀**：单测初版用固定「三边路径」G（BUS 常见形状）跑 10000 局，p=1e-4——2n 不能被 4 整除时多出的那次参与系统地落在固定位置。实际环境 G 逐局变化，改用 P2 实测的槽对可行率逐局抽 G（按连通接受），p=0.937；另留一条单测把「固定非对称图边际偏、但极差仍 ≤1」作为已知性质锁住。
2. **外环重排不能直接改写已提交布局**：`verify_distractor_layout` 按放置序逐个做点对 OBB（外扩）判定，不对称；若把重排后的顺序写回 `objects.distractors.bins`，回放复核可能误拒。改为「放置序照旧提交 + 新取值点记重排排列 + record 公开布局」。
3. **全量 lightweight 超时**：本机负载 45+，全量 1506 项 25 分钟只到 5%，改跑 35 个相关文件的子集（2 分 54 秒）并与 e1755f9 克隆逐项比失败集合。旧侧克隆放在会话 scratchpad，避免在主仓库建 worktree。
4. **snapshot 测试**：`scripts/configs/newtask-v5/sampling_config.json` 是 V5 冻结快照，decision.xhard 改动后必然不一致；草稿阶段不改 V5 快照，留待 V6 定稿统一重导（新增失败 1 项的来源）。

## 三、真机数字明细
- reset 统计脚本：逐 seed `gym.make(..., obs_mode="state", difficulty="xhard")` + reset，seed 7800000～7800199，10 进程分 GPU 0/1。
- VUS 被藏 cube 所在容器（M5）：{0:137, 1:153, 2:138, 3:154}（bin_3 不再恒空）；BUS：{0:95, 1:107, 2:105, 3:107}。
- VUS S5 重排平均 1.08 条、BUS 1.14 条、VR 2.68 条；reset 墙钟（10 进程并跑、机器负载 45+）VUS p50 12.7 s / 最大 63 s，BUS p50 11.0 s / 最大 54 s（外环 O4 每窗按组评估，比 V5 最近邻多做判定）。
- VUS 外环未参与分布 {0:13, 1:33, 2:53, 3:51, 4:24, 5:12, 6:7, 8:1}；BUS {0:1, 1:2, 2:14, 3:21, 4:37, 5:29, 6:20, 7:8, 8:6}——外环局内做不到均匀，与 M7(a) 预期一致。
- 真演示（`scripts.parity.v4_demo_probe`，seed 7900000 + 101i）：VUS 帧数 851/775/767/790；BUS 718/714/693；VR 1719/1946/1305。

## 四、当前状态与下一步
- 副本已 commit（`12.139-draft-swap`，未 push）；主仓库未动。
- 待办：V6 定稿时重导 sampling_config 快照；xhard1/2/3 新档接入时直接复用 `swap_plan_v6` / `v6_distractor_swap_cfg`；A40 上正式验收（本机 sm_89 只作调试）。
- 判定行：`UNMASK_INNER_UNIFORM=PASS env=VideoUnmaskSwap chi2_p=1.000 range_le1=1.000 undo=0`；`UNMASK_INNER_UNIFORM=PASS env=ButtonUnmaskSwap chi2_p=0.999 range_le1=1.000 undo=0`；`UNMASK_G_REJECT=REPORT VUS=0.030 BUS=0.310`；`OUTER_SWAP_BALANCE=REPORT VUS unvisited_mean=2.57 undo=0.0046 / BUS unvisited_mean=4.42 undo=0.041`；`VR_UNIFORM=PASS range_le1=0.932 undo=0 all_participate=1`（200 局样本，离线 10000 局随机图 0.957）。
