# CLAUDE.md — data-generation-MotionJEPALabel 完整参考

本文件供 agent 阅读：单事件 swap clip 数据集的机制原理、口径约束、命令用法与实测记录。
人类可读的结论摘要见 [README.md](README.md)。

任务背景：MotionJEPA（/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA）以 train
ep90-99 为 eval 集，2026-08-15 删 linear probe 的弃用理由是「缺 swap 子事件粒度标签」。
上一版链路（commit `a90f071`）对 ep90-93 穷举**整条 swap 序列**产出 318 条完整 episode、
89 GiB —— 但那把「第一次换哪对/第二次换哪对/第三次换哪对」三个因子搅在一起，还捎带了
抓取段的机器人动作差异与 easy/medium/hard 三套布局模板。本轮彻底重构，只留一个事件。

**宗旨（用户 2026-08-18 拍板）：除了 bin 的初始位置和第一次 swap 的排列组合，
其他全部保持一致。**

**★ 2026-08-19 重构：第一次 swap 的可选对收敛到「最近邻可达对」（48 条 → 19 条）。**
理由与口径见 [§三 A 最近邻约束](#三a最近邻约束2026-08-19-重构)。一句话：原版 env 的
`idx2` 是运行时按**严格最近邻**回填的，所以旧口径 `C(4,2)=6` 全枚举里有一大半的对在
原版数据中**结构上永不可能出现**；本轮只保留原版可达的那 2~3 对，主标签轴同时从
`topo_class` 换成 `event_slots`。

---

## 一、clip 区间与两条时间线

第一次 swap 窗口恒为 env step `[64,114)`（`_refresh_swap_schedule` 硬编码 `64+50i`）。
clip = 窗口 ±30 帧 = **env step `[34,144)`，共 110 帧**，落盘时帧号重编号 `0..109`。

clip 内帧号换算：`clip 帧 = env step − 34`。窗口 1 = clip `[30,80)`；
窗口 2 = clip `[80,130)`（只露出前 30 帧）；窗口 3 = clip `[130,180)`（完全不可见）。

env 侧关键时刻（`VideoUnmaskSwap.step` / `statechange.py`）：

| env step | 发生什么 | 出处 |
| --- | --- | --- |
| 0-31 | **全部 bin 藏到 (10,10,10)**，露出彩色 cube（unmask 揭示阶段） | `lift_and_drop_objects_back_to_original(bin, 0, 64)`，`drop_step = 0 + 64//2 = 32` |
| 32 | bin 落回原位，盖住 cube | 同上 |
| 34 | **clip 起点** —— 已在容器落回之后，所以 clip 内 cube 从头就被遮挡 | 本链路 |
| 64 | 第一次 swap 开始；同时 cube 被藏到 (10,10,10) | `lift_and_drop_objectA_onto_objectB(cube, 64, swap_end)` |
| 114 | 第一次 swap 结束、第二次开始 | `_refresh_swap_schedule` |
| 143 | **clip 末帧** | 本链路 |

⇒ clip 内 cube 要么被容器遮挡（帧 0-29）、要么已藏走（帧 30-109），**颜色根本不进画面**。

机器人在 clip 内做什么：

| env | clip 内行为 | 段边界（Phase 0 实测） |
| --- | --- | --- |
| VideoUnmaskSwap | static 子目标，`solve_hold_obj` 开环 hold，**不做任何运动规划** | demo 段恒 168 帧（k=2） |
| ButtonUnmaskSwap | press1 + press2，两者 `failure_func` 均为 `None` | press1 → 110/121/115/117，press2 → 200~211 |

## 二、源三重筛选（缺一不可）

1. **4-bin（medium/hard），剔除全部 easy**：easy 是 3-bin，且 `region3_tri` /
   `region3_line` 两套模板随 seed 二选一，类别体系（半程/全程 vs 腰/底边）与 4-bin 的
   互不相通 —— 三套几何无法合成统一的多类判别标签空间。只留 4-bin 后**模板唯一、
   槽位角色统一**（每源的实际条数由最近邻约束决定，见 §三A，恒为 2~3 条）。
2. **swap_times ≥ 2**：Video 的 demo 段长 = 最后一次 swap 结束（+0~4 帧），k=1 时 demo
   只到 env 114，clip 的后 30 帧会跌出 demo、机器人开始朝目标 bin 移动。
3. **两 env 取共同源号**：口径保留不变（用户 2026-08-19 明确要求筛选不动）。
   ⚠ 共同源号 **不等于**共同布局 —— 两 env 的 seed 不同（ep91 是 14100 vs 16100），
   bin 位置本就不同。⚠ 最近邻约束下这条筛选**不再保证两边条数对称**（实测 Video 11 条
   vs Button 8 条），因为条数取决于各自布局的最近邻结构。

结果恒为 `{91, 95, 98, 99}`，Video 11 条 + Button 8 条、合计 **19 条**：

| env | ep | seed | 难度 | k | 原始 bin 序列 | 原始槽位序列 | 合法对（最近邻） | 条数 | 最小 argmin 余量 |
| --- | ---: | ---: | --- | ---: | --- | --- | --- | ---: | ---: |
| Video | 91 | 14100 | hard | 2 | 03\|12 | 03\|12 | 03,12 | 2 | 0.0695 |
| Video | 95 | 14500 | hard | 2 | 01\|02 | 01\|12 | 01,03,12 | 3 | 0.0145 |
| Video | 98 | 14800 | medium | 2 | 03\|12 | 03\|12 | 03,12,23 | 3 | **0.0089** |
| Video | 99 | 14900 | hard | 2 | 01\|01 | 01\|01 | 01,03,23 | 3 | 0.0122 |
| Button | 91 | 16100 | hard | 3 | 12\|12\|03 | 12\|12\|03 | 03,12 | 2 | 0.0551 |
| Button | 95 | 16500 | hard | 2 | 03\|12 | 03\|12 | 03,12 | 2 | 0.0184 |
| Button | 98 | **16801** | medium | 2 | 12\|12 | 12\|12 | 03,12 | 2 | 0.0207 |
| Button | 99 | 16900 | hard | 3 | 03\|12\|03 | 03\|12\|03 | 03,12 | 2 | 0.0921 |

全局最小 argmin 余量 **0.0089 m**（Video ep98），比 teleport 落定噪声（~1e-6）高三个
数量级 —— 最近邻判定在数值上是稳的。低于 `NN_MARGIN_WARN`=0.005 会进验收报告的告警段。

⚠ Button/ep98 的 seed 是 **16801**（历史 attempt 探针，非 `16000+100e` 规则值）——
seed 一律从 train metadata 读表，**禁止公式反推**。
Video/ep95 是槽位换算的活样本：bin 序列 `01|02` → 槽位序列 `01|12`（第一次换完后 bin0
落在 slot1，所以第二次动的是 slot1↔slot2）。

## 三A、最近邻约束（2026-08-19 重构）

### 原版是怎么选 swap 对的

两步，两个 env 逐字同构：

1. **`idx1` 在 `_load_scene` 里定死**，且**绑死在任务目标上** —— `swap_pair{1,2,3}_idx1`
   取自 `swap_indices = cat([target_indices, [third_idx]])`，`target_indices` 就是任务要
   操作的那两个 bin。另有两处上游 quirk：`selected_bin_indices = torch.randperm(3, ...)`
   **硬编码 3**（即便 4-bin 配置也只在前 3 个 bin 里选藏 cube 的），且赋 swap 时用
   `spawned_bins[swap_indices[0]]` 把「`selected_bins` 的下标」当成了「bin 全局下标」
   ⇒ **bin 3 永远当不了 `idx1`**。
2. **`idx2` 留 `None`，进入窗口首帧才在 `step()` 里回填**：对全部 `spawned_bins` 取距
   `idx1` 最近的那一个（严格单个 argmin，见 `pair_idx2 is None` 分支的 `closest_actor`
   扫描）。按 `spawned_bins` 升序遍历 + 严格 `dist < closest_dist` ⇒ **平局取下标最小**。

⚠⚠ 同一份 env 源码里还有 `_compute_dynamic_swap_candidates` /
`_select_swap_pair_from_positions`（取最近**两个**再随机挑一个），看起来像设计意图，
但**全仓没有任何调用点、是死代码**。按 top-2 口径复算会得到每源 4~5 对，与真实机制不符。
任何人再看到它都不要采信。

### 本轮口径

**第一主角 `idx1` 放宽为任意 bin**（不受 `randperm(3)` 与任务耦合的限制），
**但 `idx2` 只能是 `idx1` 当时的严格最近邻**。于是变体空间 =
`clip_plan.nearest_neighbor_pairs(slot_xy)` = `{(i, NN(i))}` 去重，n=4 时恒为 2~3 对
（证明：全局最近的一对必然互为最近邻、去重成 1 对 ⇒ 上界 3；每槽位至少贡献 1 对 ⇒ 下界 2）。

**约束只作用于第一次 swap**（用户 2026-08-19 拍板）。窗口 ≥2 沿用 §三 的「按槽位固定」
注入 —— 那是后 30 帧跨变体一致（判据 5）的前提，与最近邻回填不可兼得，选了前者。

### 窗口 ≥2 的口径对账：实测 4/19 条不重合

原版窗口 ≥2 的 `idx1` 是一个**固定的 bin**，而窗口 1 可能已经把它挪到了别的槽位；
我们钉死的却是**槽位对**。两者何时重合、何时不重合，可以精确算出来 ——
关键前提：`swap_flat_two_lane` 是两个 bin **互换位置**，所以被占用的位置集合恒不变
⇒ **槽位层面的最近邻图整条 episode 不变**，直接用初始 `slot_xy` 复算即可
（`clip_plan.native_window_slots`）。

实测（19 条全查）：

| 变体 | 事件（w1） | 本链路钉死的 w2 | 原版规则的 w2 | |
| --- | --- | --- | --- | :-: |
| Button 全 8 条 | (0,3) / (1,2) | (1,2) | (1,2) | ✓ 重合 |
| Video ep91 2 条、ep95 var0/var2、ep98 var2/var5、ep99 var0 | — | — | — | ✓ 重合 |
| **Video ep95/var3** | (1,2) | (1,2) | **(0,1)** | ✗ |
| **Video ep98/var3** | (1,2) | (1,2) | **(2,3)** | ✗ |
| **Video ep99/var2** | (0,3) | (0,1) | **(0,3)** | ✗ |
| **Video ep99/var5** | (2,3) | (0,1) | **(0,3)** | ✗ |

**Button 8 条全部重合**，因为它的 NN 图是 0↔3、1↔2 的**完美配对** —— 无论 w1 把 bin 挪到
哪个槽位，最近邻关系都对称，w2 恒为 (1,2)。Video 侧 NN 图不总是配对（ep99 是
`NN=[3,0,3,0]`），才会出现偏离。

⇒ **事件本身（第一次 swap）19/19 严格落在原版可达空间内**；不重合的只是后 30 帧露出的
第二次 swap 换了哪一对。这是「约束只作用于第一次 swap」这个决定的直接后果，不作废数据，
逐条量化在 `clip_events.json` 的 `later_windows_follow_native_nn` /
`later_windows_native_slots` 字段与 meta 的 `later_windows_deviating_from_native_nn`。
下游若要求**整条 clip 都原版可达**，按 `later_windows_follow_native_nn == true` 过滤，
可得 **15/19 条**（Button 8 + Video 7）。

### 窗口 1 的合法对只由初始布局决定

窗口 1 开在 env step 64，而容器已于 env step 32 由
`lift_and_drop_objects_back_to_original` 落回**原始位置**。所以

```
窗口 1 合法对 = { (b, argmin_{j≠b} ‖slot_xy[b] − slot_xy[j]‖) : b } （无序去重）
```

只依赖 reset 之后的 `slot_xy`，不依赖任何一步 step —— Phase 0 的 `geometry.slot_xy`
就够了，不需要新探针。验收判据 12b 还会用 clip **自己**在事件前一帧（clip 帧 29 =
env 63）的实测位置复算一遍，确保「计划所用的几何」与「环境当时真正看到的几何」一致。

### 被这条约束排除掉的是什么

实测 8 个源：**对角对 `(0,2)`/`(1,3)` 从来不是任何 bin 的最近邻** ⇒ `cross_diagonal`
整类消失（16/48 条）；Button 四个源的合法集合恒为 `{(0,3),(1,2)}`（全 `cross_aligned`）。
48 条里有 **29 条**是原版结构上不可能出现的，本轮全部删除。

⚠ 「对角进不了最近邻」是**本 8 源的实测事实、不是几何必然** —— Button 的 region4 带列内
随机 y 偏移、各 bin 还有 ±0.07 的 rejection 抖动，理论上对角可以成为最近邻
（单测 `test_diagonal_can_be_nearest_neighbor_in_principle` 用合成布局构造了反例）。
所以 `topo_class` 字段与三类映射一律保留，判据 10c-iii 只是把「恒为 0」做成回归守卫。

### 有方向的正确性证据（Phase 0 实测 8/8）

`probe_original.py` 现在会读回原版的 `swap_pair{k}_idx1`（`swap_inject.readback_idx1`），
于是可以做**有方向**的判据而不只是「原始首对是某个 `(i,NN(i))`」：

| 源 | 原版 idx1 | 原版 idx2 | NN(idx1) | 命中 |
| --- | ---: | ---: | ---: | :-: |
| Button ep91 | 2 | 1 | 1 | ✓ |
| Button ep95 | 0 | 3 | 3 | ✓ |
| Button ep98 | 2 | 1 | 1 | ✓ |
| Button ep99 | 0 | 3 | 3 | ✓ |
| Video ep91 | 0 | 3 | 3 | ✓ |
| Video ep95 | 0 | 1 | 1 | ✓ |
| Video ep98 | 0 | 3 | 3 | ✓ |
| Video ep99 | 1 | 0 | 0 | ✓ |

**8/8 命中**，坐实 `clip_plan.nearest_neighbor` 与 env 实际行为逐字一致。

### 编号方案：稀疏的 `C(4,2)` 字典序下标

`variant_idx = pair_index(event_slots)`，取值只出现 `0=(0,1)`、`2=(0,3)`、`3=(1,2)`、
`5=(2,3)`；`1=(0,2)` 与 `4=(1,3)` 恒缺席（正是两个对角对）。选稀疏不选稠密的理由：
`variant_idx ↔ event_slots` 是双射且**跨源可比**（Button ep91 的 var2 与 Video ep98 的
var2 都是 (0,3)）；`draw_contact_overview` 的 6 列布局与 `_scan_jsonl` 的断点续跑 key
语义都保持不变。稠密编号会让 `var0` 在不同源指向不同槽位对，一切按编号的对齐都成陷阱。

## 三、核心机制：零 src 改动的 swap 注入 + 窗口 ≥2 按槽位固定

环境侧事实（两个 env 同构）：swap 的对象是 **bin**，`swap_flat_two_lane` 做 kinematic
teleport 位置互换；swap 对象选择位于 `_load_scene` RNG 流**最末尾**，`swap_pair{k}_idx2`
本就留 None、运行时进窗口首帧取最近邻回填。**注入 = reset 后覆写
`swap_pair{1,2,3}_idx1/idx2` 六个属性再 `_refresh_swap_schedule()`**，零 RNG 消耗 ⇒
布局/颜色/任务目标逐比特不变。idx2 必须显式给，否则被最近邻覆盖。

### 槽位（slot）语义

bin `i` 的**初始位置**定义为 slot `i`。维护 `slot[b]` = bin b 当前槽位，初始
`slot[b]=b`；窗口交换 bin (u,v) 即 `slot[u], slot[v] = slot[v], slot[u]`。
**窗口 i 实际移动的槽位对** `S_i = (slot_before[u], slot_before[v])`。
`clip_plan.slot_pairs_from_bin_pairs` / `bin_pairs_from_slot_pairs` 是互逆的换算
（单测对全部长度 ≤3 的序列穷举验证过）。

### 注入语义

- **窗口 1**：枚举该源的**最近邻可达对**（`nearest_neighbor_pairs`，每源 2~3 个，见 §三A）。
  窗口 1 之前 slot 是 identity，所以槽位对 == bin 对。
- **窗口 i≥2**：从 Phase 0 原始跑复算出原始槽位对 `S_i^orig`，变体里注入「**当前占据
  `S_i^orig` 两槽的那两个 bin**」。于是窗口 i≥2 的 teleport 起止位置、被锁定旁观 bin 的
  位置集合，跨同源全部变体一致 —— 后 30 帧不是第二个变化因子。
  推论：窗口 1 取原始槽位对时整条序列退化为原始 bin 对序列 ⇒ `is_original` 变体仍逐位
  复现官方 episode。

⚠ **窗口 ≥2 的原始槽位对只能实测拿到**：`idx2` 是运行时进窗口那一刻按最近邻回填的，
静态算不出。这就是 Phase 0 必须跑**完整** rollout 的原因（Button 的 k=3 源第三个窗口到
env 214 才结束，而正式产物的截断点在 press2 结束 ~200，够不着）。

## 四、截断 rollout（正式产物）与 `episode_success` 置位

clip 只到 env 143，抓取段完全用不上：

- **Video**：只 solve `task_list[0]`（static，hold 到最后一次 swap 结束 ≥164）；
- **Button**：只 solve `task_list[0..1]`（两个按钮，跑到 ≥198）。

硬断言：录到的帧数 ≥ 144（`CLIP_END`），否则 fail-loud。

⚠ `RecordWrapper.close()` 里是 `if self.episode_success:` 才落盘，而 `episode_success`
只在 `terminated` 时置真 —— 截断跑必须在 close 前**显式** `record_env.episode_success = True`
（实例属性赋值，零 src 改动）。这是有意为之的「录制部分轨迹」，**不是绕过失败判定**：
截断点之前的两个子目标 `failure_func` 都是 `None`，这段里根本不存在失败条件。

收益（实测）：旧链路 318 条里有 85 条撞上「抓取子目标 step≈200 开始 vs 第三个 swap 窗口
到 214 才结束」的时序冲突、必须加 hold 补救；本轮 **19/19 零重试**。速度约 2 倍。

## 五、与 newSeed 骨架的三处刻意偏离（⚠ 改动前必读）

`clip_worker.py` 的 rollout 骨架照抄 `scripts/data-generation-newSeed/generate_dataset_newseed.py`，除三处：

1. **FailRecover 恒不启用**：骨架按 episode 号分档，本链路的 staging 编号会让分档乱套；
   源 ep91-99 全部 ≥6，原始行为就是不启用。
2. **失败重试不换 seed**：骨架 `bump` 会按公式换 seed —— 换 seed 即换布局，摧毁前提。
   `ClipJob.bump()` 只加 attempt。
3. **difficulty 读 train metadata**，不用 `difficulty_for()` 循环。

另有一条硬规则：**每变体新建 env，禁止复用** —— `statechange.py` 的 `_two_lane_swaps` /
`_lift_drop_onto_cache` 按 `id(actor)` 做键且 reset 不清理，跨变体复用会静默读旧缓存。

## 六、clip 裁剪与 h5 结构

worker 在 `close()` 后把 raw 的 `timestep_34..143` 拷成 clip h5、帧号重编号 `0..109`，
并**改写 `info`** 让整段 clip 恰好构成该 env 的 scope 段（口径与 `segment_lengths` /
MotionJEPA `build_data_raw_from_h5` 对齐）：

- Video（scope=demo）：全部 `is_video_demo=True` → `demo_prefix=110`、`exec_len=0`；
- Button（scope=exec）：全部 `is_video_demo=False` + **末帧 `is_completed=True`**
  → `exec_len = min(109+2, 110) = 110`。

⚠ Button 末帧的 `is_completed=True` 是**人为置位**，语义是「clip 到此为止」而**不是**
「任务完成」—— 截断 rollout 时任务确实没做完。下游只把它当段尾标记用。

裁剪后删除 raw h5（clip 是唯一产物）。

### h5 内嵌标注

```
episode_N/timestep_t/swap_gt/   swap_active, swap_window_idx, swap_slots(int8[2]),
                                swap_bins(int8[2]), swap_pair_pos(f32[2,3]),
                                swap_progress, bins_pos(f32[n,3]), cubes_pos(f32[3,3]),
                                env_step(int32),
                                contact_{robot_bin,bin_bin,robot_button}_{count,impulse}
episode_N/setup/swap_gt/        env_seed, variant_seed, src_episode, variant_idx,
                                is_original, difficulty, signature,
                                slot_pairs/bin_pairs(int8[k,2]),
                                windows_clip/windows_env(int32[k,2]),
                                clip_start_env_step, clip_len,
                                ★ event_slots(int8[2]), topo_class,
                                pair_distance, pair_azimuth, pair_azimuth_local,
                                slot_xy(f32[n,2]), reference_axis_deg,
                                net_permutation, min_clearance,
                                bystander_net_max/path_max, disturbed_bins,
                                contact_*_frames / *_forceful_frames /
                                *_event_forceful_frames / *_impulse_max /
                                *_onset_clip_frame / bin_bin_(forceful_)pairs,
                                bins_pos_traj(f32[110,n,3]), cubes_pos_traj
episode_N/setup/meta/           bin_colors, color_names, task_goal_color,
                                button_left, button_right   ← 纯 metadata，不进标签
```

合并（`raw.copy` 整组拷贝）自动带走全部标注，合并逻辑零改动。

## 七、标签设计

**主标签轴 = `event_slots`**（`clip_events.json`，每条 clip 恰含一个事件）：窗口 1 移动的
槽位对，取值域 4 类 —— 实测分布 `03:8 / 12:7 / 01:2 / 23:2`。**不含任何颜色字段。**

协变量（非主轴）：`topo_class`、`pair_distance`、`pair_azimuth`、`pair_azimuth_local`、
`slot_xy`、`reference_axis_deg`、`difficulty`、`buttons`。
最近邻约束自证字段：`is_nn_pair`（恒 1）、`legal_event_slots`（该源合法集合）、
`slot_nearest_neighbor`、`nn_margin`、`event_pair_index`。

⚠ **`topo_class` 已从主标签降级为协变量**：最近邻约束下 `cross_diagonal` 恒为空、
Button 侧 8 条更是全部 `cross_aligned`（任务内零方差），实测分布 `cross_aligned 15 /
same_column 4`。类别严重不均衡是**约束的结构性后果**，本数据集**不做重采样、不做类别
平衡**（`clip_events.json` 的 meta 里有 `class_balance_note` 显式声明），下游若要平衡
须自行处理，可按 `per_source_legal_pairs` 做源内分层。

### 拓扑类别按槽位角色定义，不按距离

两个 env 的 region4 模板写法不同，但槽位角色完全同构（`SLOT_ROLE`）：

```
Video （_load_scene:196-202）：模板固定，再整体随机旋转 α∈[0,180°)
    region4 = [[-0.05,-0.1], [-0.05,0.1], [0.1,0.1], [0.1,-0.1]]
Button（_load_scene:234-267）：两列各带一个 seed 随机 y 偏移，
    且 rotate_points_random 那行**被注释掉了**（α 恒为 0）
    region4 = [[0,-0.1+y1], [0,0.1+y1], [0.1,0.1+y2], [0.1,-0.1+y2]]
⇒ slot 0/1 = 左列的下/上，slot 2/3 = 右列的上/下

same_column    (0,1) (2,3)  同一列内上下互换
cross_aligned  (1,2) (0,3)  跨列、同侧
cross_diagonal (0,2) (1,3)  跨列、异侧
```

Video 下三类恰好对应 0.15 / 0.20 / 0.25 三档名义距离（单测交叉验证过）；
**Button 下距离序不成立** —— 跨列同侧 ∈[0.100,0.141]、跨列对角 ∈[0.141,0.316]，对角可比
同列的 0.20 还短。ep95 实测：`cross_aligned` d=0.104 m **短于** `same_column` d=0.169 m。
所以 `topo_class` 是**生成机制的真值**，`pair_distance` / `pair_azimuth_local` 是连续
协变量，下游要按几何分类必须用后者。

`reference_axis_deg` 取「列方向」的实测均值（slot0→slot1 与 slot3→slot2 的平均），
不去拟合 `rotate_points_random` 的角度 —— Video 的 angle 是 `_load_scene` 局部变量取不到，
Button 压根没旋转。实测均值对两 env 都成立，且天然吸收 ±0.07 的 rejection 抖动。

### chunk 级标签（兼容层）

`swap_labels_clip.json`（v7 同构，`load_manual_swap` 可直接读）与 `swap_events_clip.json`
（富标签）。判正规则与旧链路逐字相同：chunk `[s,s+32]` 在任一窗口内推进的 smoothstep
进度增量 > ε=0.10。**不能用简单窗口重叠** —— smooth 让窗口末尾几帧几乎不动，几何重叠
会在窗口尾部多打假正例。规则须先过 `--regression`（对官方 ep90-99 复算、与 v7 人工资产
逐条比对）。

⚠ 在 clip 上区分度很低：`grid_starts(110) = [0,16,32,48,64]` 只有 5 个 chunk，
按 ε=0.10 第 0 个为负、其余 4 个为正（19 clip → 95 条、76 正）。主用途是 clip 级多类判别。

## 八、接触检测与 ButtonUnmaskSwap 的动作通道泄露

### 8.1 接触检测（物理引擎实测，`swap_inject._contact_snapshot`）

逐帧调 sapien `scene.get_contacts()` 扫全场，按三类归并。两个实现坑：

1. **实体名带子场景前缀**：`entity.name` 是 `scene-0_bin_0`，而 `spawned_bins` 的 `.name`
   是裸名 `bin_0` —— 不剥前缀（`_strip_scene`）就永远匹配不上，统计会恒为 0；
2. **零冲量接触候选**：PhysX 会把贴得很近但没使上力的物体也配成接触对（实测容器之间
   几乎每帧都有），所以 `*_frames` 没有判别力，**判「真的撞上了」必须用
   `*_forceful_frames`**（冲量 > `FORCEFUL_IMPULSE_EPS` = 1e-9）。

全量实测结果：

| 接触类型 | 结果 |
| --- | --- |
| **robot_bin**（机械臂连杆 ↔ 容器） | **0/19 条** —— 机器人从未被 swap 中的容器碰到 |
| **bin_bin**（容器 ↔ 容器） | **1/19 条**（Video ep99/var5，1 帧、冲量 0.0012）。最近邻对总是短程对、路径不穿过第三个容器，所以互撞几乎消失 —— 旧口径的 20/48 主要来自被删掉的对角/长距对 |
| robot_button（机械臂 ↔ 按钮） | Button 每条 17 帧、Video 0 帧（任务本身的接触） |

容器互撞与拓扑类别强相关：`cross_aligned` **0/16**（跨列同侧路径最短，从不撞）、
`same_column` 7/16、`cross_diagonal` **13/16**（对角路径最长、最容易穿过别的容器）。

### 8.2 动作通道泄露的正确因果链

**现象**：Button 侧 clip 全程 `joint_action` 跨同源变体最大差 5.8e-3 ~ **1.6e-1 rad（≈9°）**；
Video 侧严格 0.0。

⚠ **不要归因成「容器擦碰机械臂」** —— 那是本轮一度做出的错误推断，已被接触检测推翻
（robot_bin 实测 0/19；末端与最近容器的中心距 0.12~0.21 m）。正确链条是：

```
交换中的两个容器互撞（bin_bin 接触）
  → 改变 PhysX 的接触求解规模与顺序
  → 机械臂-按钮的接触力数值解发生变化
  → 关节角偏离
  → solve_button 的第 2/3 段规划以偏离的关节角为起点 → 指令分叉
```

ep95/var2 的逐帧实证（对照 var0）：

| env step | 观察到什么 |
| --- | --- |
| 70 | `bin_0↔bin_3` 开始持续接触（var0 无此接触） |
| 79 | `button_cap↔panda_leftfinger/rightfinger` 冲量出现差异（var0 左 0.0648/右 0.0029，var2 左 0.0234/右 0.0438）；qpos 从严格 0.0 突跳到 **4.7e-5** |
| 82 | 按钮接触冲量差已达 1.29；qpos 差 1.4e-3 |
| 88 | 指令 `joint_action` 首次分叉 |

Video 不受影响：demo 段 `solve_hold_obj` 开环发同一 qpos、**不做任何运动规划**，
所以即便容器互撞（Video 侧也有 8/24 条），指令仍逐位相同。
**这正说明泄露的必要条件是「clip 内存在运动规划」，而不是「有没有接触」。**

排除项：不是浮点噪声（ulp 是 1e-15 量级，实测起步 4.7e-5）；不是 RRT* 随机性
（同源分组稳定、Phase 0 与官方逐位一致）。零 src 改动无法消除。

### 8.3 处置：全部保留并逐条量化（用户 2026-08-18 拍板）

标签里三个可过滤字段：`action_group`（同源内按 `joint_action` 逐位相同划分的等价组 id）、
`action_dev_max`（与同源其他变体的最大绝对差）、`action_group_identifies_label`
（该源等价组数 == 变体数 ⇒ 关节角可完全反推标签）。

最近邻约束后的实测分组（2026-08-19，19 条）：

| env / 源 ep | 变体数 | 动作组数 | 各变体所属组 | 组间最大差 (rad) | 可完全判别标签 |
| --- | ---: | ---: | --- | ---: | :-: |
| Video 91/95/98/99 | 2/3/3/3 | 1 | 全部 → 0 | 0.000e+00 | 否 |
| Button 91 | 2 | 2 | var2→0，var3→1 | 5.842e-03 | **⚠ 是** |
| Button 95 | 2 | 1 | var2/3→0 | 0.000e+00 | 否 |
| Button 98 | 2 | 1 | var2/3→0 | 0.000e+00 | 否 |
| Button 99 | 2 | 2 | var2→0，var3→1 | 3.245e-02 | **⚠ 是** |

⚠⚠ **旧口径「取同一 `action_group` 即得无泄露子集」在 2 变体源上已名存实亡** —— Button
ep91/ep99 各只有 2 条且分成 2 组，「同一组」只剩 1 条，等于关节角 100% 反推标签。
**下游一律改用 `action_dev_max == 0` 筛选**，本轮可得 **15/19 条**（Video 全部 11 条
+ Button ep95/ep98 各 2 条）。验收报告会把这类源写进告警段并在
`clip_events.json` 的 `meta.action_leak_sources` 里列名。

（对照：全枚举版 48 条时 Button 四个源都是 2 组、每组 3 条，最大差 1.598e-01；
最近邻约束删掉了互撞最剧烈的对角/长距对，所以偏差量级也从 1.6e-1 降到 3.2e-2。）

## 九、命令用法（按 Phase 顺序）

```bash
# P0a 纯函数单测（秒级，39 passed）
uv run python -m pytest tests/lightweight/test_swap_clip_plan.py -q
# P0b 计划表（不生成数据）
uv run python scripts/data-generation-MotionJEPALabel/clip_plan.py
# P0c 控制跑（8 条完整 rollout，约 35 s；含与官方 h5 的红线比对）
uv run python scripts/data-generation-MotionJEPALabel/probe_original.py --gpus 0,1 --workers 8
# 标签规则回归（只读，约 1 min）
uv run python scripts/data-generation-MotionJEPALabel/make_clip_labels.py --regression
# P1 smoke（单源 2~3 条；Video ep95 合法集合大小为 3）
uv run python scripts/data-generation-MotionJEPALabel/generate_swap_clips.py \
  --output-dir scripts/data-generation-MotionJEPALabel/outputs/smoke \
  --tasks VideoUnmaskSwap --only-episodes 95 --gpus 0,1 --workers 6
# P2 全量（19 条，约 40 s；>5 min 的任务才需要 tmux）
uv run python scripts/data-generation-MotionJEPALabel/generate_swap_clips.py \
  --output-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --gpus 0,1 --workers 16
# P3 合并 + 密集重编号 + episode_map
uv run python scripts/data-generation-MotionJEPALabel/merge_clip_h5.py \
  --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --delete-source
# P4 标签 + 验收 + 简图
uv run python scripts/data-generation-MotionJEPALabel/make_clip_labels.py \
  --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1
uv run python scripts/data-generation-MotionJEPALabel/verify_clips.py \
  --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
uv run python scripts/data-generation-MotionJEPALabel/draw_clip_diagrams.py \
  --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
```

## 十、验收判据（`verify_clips.py`，十二条全过才算数）

1. **枚举完整度（最近邻口径）**：逐源，事件槽位对集合**恰等于**
   `nearest_neighbor_pairs(该源 Phase 0 实测 slot_xy)`（不多不少、无重复）；
   `is_original` 每源恰 1 条；bin 数恒 4；`variant_idx == pair_index(event_slots)`（编号自洽）；
2. 槽位 xy 与 Phase 0 布局基线逐位相同；
3. **前 30 帧不变性**：clip 帧 0-29 的 `bins_pos` 跨同源变体逐位相同；
4. **★ 机器人动作恒定**：clip 全程 `joint_action` 跨同源变体逐位相同 ——
   `ACTION_BITWISE_REQUIRED` 只对 Video 硬断言，Button 量化报告（见 §八）；
5. **后 30 帧受控性**：clip 末帧的 `bins_pos` 排序后位置集合跨变体差 < 1e-5。
   ⚠ 口径是**窗口 2 的端点位置**而非整段逐位相同：窗口 1 的对角交换会擦碰被锁定的旁观
   bin（实测 `min_clearance` 低到 0.0045 m），把它挤开几毫米再弹回 —— 那是第一次 swap 的
   物理余波、是允许变化维度的直接后果，由 `bystander_net_max` 逐条量化；
6. **窗口 1 生效**：clip 帧 30→79 的净位移恰为计划的两个 bin 且 ≥0.03 m。
   **必须用净位移，不能用路径长** —— 对角交换会擦碰旁观 bin，路径长可达 0.11 m 却净位移
   近零，用路径长会确定性误杀；
7. **变体互异**：(a) 同源变体在事件末帧（clip 79）的 `front_rgb` md5 两两不同；
   (b) 同源变体在事件末帧的 `bins_pos` **逐 bin 必有差异**（几何本质，不依赖渲染副产物）。
   ⚠ 7b 只比「逐 bin 有无差异」，**不比位置集合是否相等** —— 事件末帧 teleport 刚结束、
   物体仍在沉降，实测同源位置集合差约 3e-4，要再过 30 帧才收敛；位置集合的一致性由判据 5
   在 clip **末帧**断言（实测 ~1e-6）。加 7b 是因为最近邻约束把同源压到 2~3 条后，
   7a 的比较对数从 15/源 降到 1~3/源，判别力下降；
8. **cube 可见性分段**：clip 帧 0-29 全部 z < 0.1（在容器内），帧 30-109 全部 z > 5（已藏走）；
9. merged h5 结构：episode/timestep 密集连续、每条恰 110 帧、scope 段 == 110、swap_gt 齐全；
10. **标签对账**：(a) clip 级标签数 == clip 总数；(b) `event_slots` 与 `topo_class`
    **双轴**分布均与 h5 实测逐项相等；(c) 三条替代旧「三类均衡」的确定性判据 ——
    **i** 标签侧逐源覆盖（从 `clip_events.json` 独立复核判据 1，防漏条/串源）；
    **ii** 全局 `event_slots` 分布与「各源合法集合求并」的期望**逐项相等**
    （期望值代码现算，绝不写死数字）；**iii** `cross_diagonal == 0` 的回归守卫
    （notes 里注明这是实测事实、不是几何必然，非 0 即说明布局或源集合已变）；
    (d) chunk 标签数 == 网格期望；
11. **机械臂 ↔ 容器接触必须为 0**（物理引擎 `get_contacts` 实测）。本链路的前提是
    「机器人动作只由任务本身决定」；若机械臂真被 swap 中的容器碰到，clip 里就多了一条
    swap → 机器人的**直接**因果通路。实测 0/19；
12. **★ 最近邻不变量**（本轮重构的核心判据）：
    **a** 逐条 clip，`event_slots = (a,b)` 满足 `b == NN(a)` 或 `a == NN(b)`（用 Phase 0
    实测几何复算），且 h5 内嵌的 `is_nn_pair` 为 1、`legal_event_slots` 与之一致；
    **b** **物理侧交叉复核** —— 改用这条 clip **自己**在事件前一帧（clip 帧 29 = env 63）
    的实测 `bins_pos` 复算合法集合，必须与 Phase 0 基线一致。判据 2 只保证 reset 时刻，
    12b 保证进入 swap 窗口那一刻环境真正看到的几何仍给出同一组合法对；
    **c** argmin 余量 < `NN_MARGIN_WARN`(0.005 m) 进**告警**（不判失败 —— 余量小只说明
    接近平局，是需要人看一眼的信号，不是数据错误）；
    **d** 原始首对必落在合法集合内；Phase 0 读回了 `original_idx1` 时升级为**有方向**的
    精确判据 `NN(idx1_orig) == idx2_orig`（实测 8/8 命中）。

另有**告警段**（不判失败）：判据 4 发现某源的动作等价组数 == 变体数（每组只剩 1 条）时
写入告警 —— 那意味着关节角可完全反推标签，见 §八。

---

# 实测记录（2026-08-18）

## 十一、Phase 0 控制跑（8/8 成功，32.4 s，GPU 0+1，workers=8）

与官方 `/data/hongzefu/robomme_data_h5` 的 joint_action 偏差全部在机器精度，
**clip 区间 `[34,144)` 严格 0.0**：

| task/ep | T | demo | exec | 全程 max_diff | clip 区间 max_diff |
| --- | ---: | ---: | ---: | ---: | ---: |
| Button/ep91 | 464 | 0 | 455 | 2.02e-18 | **0.0** |
| Button/ep95 | 479 | 0 | 474 | 1.90e-18 | **0.0** |
| Button/ep98 | 320 | 0 | 316 | 2.30e-18 | **0.0** |
| Button/ep99 | 453 | 0 | 447 | 2.57e-18 | **0.0** |
| Video/ep91 | 407 | 168 | 234 | 1.06e-17 | **0.0** |
| Video/ep95 | 427 | 168 | 254 | 1.65e-17 | **0.0** |
| Video/ep98 | 278 | 168 | 102 | 9.32e-18 | **0.0** |
| Video/ep99 | 429 | 168 | 253 | 1.54e-17 | **0.0** |

Video 的 demo 段恒 168（k=2 ⇒ 164+4 帧子目标切换延迟），完整覆盖 clip 的 `[34,144)`。
Button 的 press1 结束于 110/121/115/117、press2 结束于 200~211，clip 全落在两次 press 内。

## 十二、smoke（Video ep91 六条，6/6，17.3 s）

跨变体自检（clip 帧口径）：帧数恒 110；全部 `is_video_demo=True`、`is_completed` 全 False；
**clip 全程 `joint_action` 最大差 0.0**；前 30 帧 `bins_pos` 最大差 0.0；
事件末帧 `front_rgb` md5 六者互异；cube 在帧 0-29 全部 z=0.0167、帧 30-109 全部藏走。
关键帧拼图肉眼确认：事件前两列六行完全一致、画面里只有 4 个白色容器无任何彩色 cube。

## 十三、全量 19 条（2026-08-19，最近邻约束重构后）

| 阶段 | 结果 |
| --- | --- |
| Phase 0 重跑 | **8/8 成功，31.8 s**；与旧索引的 `slot_xy`/`original_bin_pairs`/`fingerprint` **逐位相同**（确定性验证）；官方红线 clip 区间严格 0.0 |
| 生成 | **19/19 成功，38.2 s（29.9 ep/min），零重试、零闸门失败**（含新增的最近邻闸门） |
| 合并 | Video 11 条 0.75 GiB + Button 8 条 0.55 GiB = **1.30 GiB**；结构校验全过 |
| 标签规则回归 | 对官方 ep90-99 复算，与 v7 人工资产 **319/319 全对**（ε=0.10，不受本次改动影响） |
| clip 级标签 | 19 条；主轴 `event_slots` = `03:8 / 12:7 / 01:2 / 23:2`；协变量 `topo_class` = `cross_aligned 15 / same_column 4 / cross_diagonal 0` |
| chunk 级标签 | 95 条（swap=1 共 76 条） |
| 接触检测 | 机械臂 ↔ 容器 **0/19**；容器互撞 **1/19**（Video ep99/var5，1 帧、冲量 0.0012） |
| 验收 | **十二条判据全过**（退出码 0），另有 2 条告警 |
| 单测 | `test_swap_clip_plan.py` **66 passed, 1 skipped**（原 39 项） |

关键判据实测值：

- 判据 12（★ 最近邻不变量）：19/19 条事件对满足最近邻关系；clip 自身事件前一帧几何复算
  与 Phase 0 基线一致；原始首对命中 **8/8** 源，**有方向**判据（原版 `idx2 == NN(idx1)`）
  同样 **8/8**；全局最小 argmin 余量 **0.00893 m**（远高于 0.005 告警阈）；
- 判据 4：Video **0.0（逐位相同）**；Button 最大 **3.245e-02**（旧口径 1.598e-01）；
- 判据 3（前 30 帧 `bins_pos`）：**0.000e+00**（14 次同源两两比较）；
- 判据 5（clip 末帧位置集合）：**1.006e-06**（阈值 1e-05，同 14 次比较）；
- 判据 11（机械臂 ↔ 容器接触）：**0/19**；
- 质量：`min_clearance < 0.055 m` 的 clip **0/19** 条，全体最小 **0.0800 m**；
  `bystander_net_max` 全 0、`disturbed_bins` 全空。

⚠ **告警两条**（不判失败，已写进验收报告的告警段）：`ButtonUnmaskSwap/ep91` 与
`ButtonUnmaskSwap/ep99` 的 2 条变体分成 2 个动作等价组（每组 1 条）⇒ **关节角可完全反推
标签**。下游一律用 `action_dev_max == 0` 筛（15/19 条），**不要**沿用旧口径「取同一
`action_group`」—— 同源只有 2 条时那会退化成 1 条。

⚠ **必须如实记录的退化**（不是缺陷，是约束的结构性后果）：同源变体从 6 条降到 2~3 条，
判据 3/4/5/7 的比较对数从 15/源 降到 1~3/源（全局 14 次），结论仍成立但覆盖面变窄；
`min_clearance` / `bystander_*` / `disturbed_bins` / `contact_bin_bin_*` 全部退化为近似
常量（最近邻对总是短程对、路径不穿过第三个容器），**不再具备下游分层能力**，价值转为
**回归守卫** —— 一旦低净空样本重新出现、旁观 bin 被扰动、或互撞条数明显上升，就说明
几何、注入口径或源集合发生了变化，必须停下来查。

## 十四、与上一版（318 条穷举）的对比

| 项 | 上一版 `a90f071` | 全枚举版（2026-08-18） | **本轮（最近邻约束）** |
| --- | --- | --- | --- |
| 条数 / 体量 | 318 条 / 89 GiB | 48 条 / 3.28 GiB | **19 条 / 1.30 GiB** |
| 源 | ep90-93 × 2 env（含 easy 3-bin） | ep91/95/98/99 × 2 env | 同左（筛选口径未变） |
| 枚举 | 整条 swap 序列（`P^k`） | 只第一次 swap 的 `C(4,2)=6` | **只第一次 swap 的最近邻可达对（2~3）** |
| 与原版的关系 | — | 6 个对里 **29/48 条原版结构上不可能出现** | **全部落在原版可达空间内** |
| rollout | 完整（含抓取） | 截断 | 同左 |
| 落盘 | 完整 episode（221-465 帧） | 110 帧 clip | 同左 |
| 失败 | 85/318 条需 hold 补救 | 零重试 | **零重试** |
| 类别 | 3 套互不相通的几何 | 1 套，三类各 16 条 | **1 套，两类 15/4（对角结构性消失）** |
| 主标签 | chunk 级二值 | `topo_class` 三类 | **`event_slots` 四类（8/7/2/2）** |
| 判据数 | — | 十一条 | **十二条 + 告警段** |
