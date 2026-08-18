# CLAUDE.md — data-generation-MotionJEPALabel 完整参考

本文件供 agent 阅读：swap 变体派生数据集的机制原理、口径约束、命令用法与实测记录。
人类可读的结论摘要见 [README.md](README.md)。

任务背景：MotionJEPA（/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA）以
train ep90-99 为 eval 集，2026-08-15 删 linear probe 的弃用理由是「缺 swap 子事件粒度
标签」。本链路对 VideoUnmaskSwap / ButtonUnmaskSwap 的 train ep90-93 做「布局不变、
只穷举 swap 对象」的派生，产出带完整 ground truth 标注的专用评估数据集。

---

## 一、核心机制：零 src 改动的 swap 注入

环境侧事实（`src/robomme/robomme_env/{VideoUnmaskSwap,ButtonUnmaskSwap}.py`，两者同构）：

1. swap 的对象是 **bin（容器）**，`swap_flat_two_lane`（`utils/statechange.py:45`）做
   kinematic teleport 位置互换；cube 在窗口内藏到 (10,10,10)，结束后落回**自己 bin 的
   新位置** —— cube↔bin 绑定不变（三仙归洞语义）。
2. swap 次数 k 由 `__init__` 里独立 `torch.Generator(manual_seed(seed))` 的第一笔
   `randint(swap_min, swap_max+1)` 决定（`VideoUnmaskSwap.py:141-143`）——可离线复算。
3. 帧窗口硬编码：第 i 次交换占 env step `[64+50i, 64+50(i+1))`（`_refresh_swap_schedule`）。
4. swap 对象选择位于 `_load_scene` RNG 流**最末尾**（`VideoUnmaskSwap.py:341-347`）：
   抽 `swap_pair{k}_idx1`，`idx2` 留 None、运行时进窗口首帧取 xy 最近邻回填。
5. **注入方法**：`env.reset()` 后覆写 `swap_pair{1,2,3}_idx1/idx2` 六个属性（idx2 必须
   显式给，否则被最近邻覆盖）再调 `_refresh_swap_schedule()`。零 RNG 消耗 ⇒ 布局/颜色/
   任务目标逐比特不变（`verify_variants.py` 用布局指纹逐位断言）。
6. 注入路径与原始路径行为等价：窗口前两条路径都是 no-op（原始因 `idx_b is None`
   continue，注入因 `cur_step < start` 返回），端点捕获都发生在窗口首帧。

由此的枚举空间：每次交换是 bin 的**无序对**（对 `swap_flat_two_lane` 逐项代入可证
(i,j)/(j,i) 轨迹逐位相同），P = C(bin数,2)，k 次交换共 P^k 种序列（含相邻重复 ——
Phase 0 实测 ButtonUnmaskSwap/ep91 的原始序列就是 `12|12|03`，相邻重复天然存在）。

## 二、编号与 seed（派生 episode ↔ seed 一一对应）

```
staging_episode = src_episode × 1000 + variant_idx     （生成期文件名用）
variant_seed    = env_seed    × 1000 + variant_idx     （metadata/文件名的唯一标识）
反解：// 1000 与 % 1000
```

- **环境实际播种用 env_seed**（train metadata 里的原始 seed；同源变体共享，布局不变之源）。
  直接拿 variant_seed 去 `gym.make` 复现不了 —— 复现须 env_seed + 注入 pairs。
- 合并后官方 h5 内重编号为**密集 0..M-1**（下游普遍假设 episode 0-based 连续），
  `episode_map_{Task}.json` 记录 dense ↔ staging ↔ seed ↔ pairs 的完整映射。

## 三、与 newSeed 骨架的三处刻意偏离（⚠ 改动前必读）

`variant_worker.py` 的 rollout 骨架（env kwargs、planner screw×3→RRT*×3、成功判定、
线程压 1、每卡一池绑卡、BrokenProcessPool 重建）照抄
`scripts/data-generation-newSeed/generate_dataset_newseed.py`，除三处：

1. **FailRecover 恒不启用**：骨架按 episode 号分档（ep≤2→z、≤5→xy），本链路的
   staging/dense 编号会让分档乱套；源 ep90-93 全部 ≥6，原始行为就是不启用。
2. **失败重试不换 seed**：骨架 `bump` 会按公式换 seed —— 本链路换 seed 即换布局，
   摧毁「其他配置不变」前提。`VariantJob.bump()` 只加 attempt。
3. **difficulty 读 train metadata**：不用 `difficulty_for()` 循环（对 staging 号无意义）。

另有两条硬规则：

- **每变体新建 env，禁止复用**：`statechange.py` 的 `_two_lane_swaps` /
  `_lift_drop_onto_cache` 按 `id(actor)` 做键且 reset 不清理，跨变体复用会静默读旧缓存。
- **swap_times 不改**：VideoUnmaskSwap 的 static 子目标时长在 `_load_scene` 建 task_list
  时取 `swap_schedule[-1][3]`，改次数会造成 task_list 与 schedule 不一致。

## 三之二、ButtonUnmaskSwap 的抓取/swap 时序冲突与 hold 补救（踩坑记录）

ep91（hard，k=3）的第三个 swap 窗口到 step 214 才结束，而抓取子目标实测 step≈200
就开始（子目标边界：按钮1 0-109、按钮2 110-199、抓红 200-314、放下 315、抓蓝 356-453）。
原始序列恰好最后窗口动的是 (0,3)（目标 bin2 静止）所以官方数据成立；穷举变体则撞上
两种确定性失败（85/216 条）：

- **(a) 抓取规划读到移动中的位置**（83 条）：最后窗口在动目标 bin，oracle 按 step 200
  时的位置规划抓取，teleport 继续走 → 抓错 bin → 环境判 fail。
- **(b) 旁观 bin 被瞬时挤高**（var61/var191）：按钮 2 完成的那次 evaluate 把子目标推进
  到抓取并即刻激活 failure_func（其他 bin z>0.15 即败），恰逢对角 teleport 深度穿越
  旁观 bin（var61 实测 min_clearance=0.0062 m）把它挤过阈值 → episode 在 step≈200
  终止，还没走到抓取 entry。

补救（零 src 改动）：**仅重试 attempt（≥1）时**，在最后一个按钮 solve 完成后、其
post-solve evaluate 之前，用环境自带的 `solve_hold_obj_absTimestep`（VideoUnmaskSwap
static 子目标同款机制）hold 到 `swap_schedule[-1][3]+10`（+10 为被挤高 bin 的自由落体
沉降余量）。attempt 0 一律不 hold —— 天然可成功的变体（含全部 is_original）轨迹与
官方逐位可比；hold 变体的 `attempt`/`pickup_hold_step` 逐条记录在 manifest/episode_map/
富标签里（83 条 hold 到 214（第一版实现，无余量已够）、2 条 hold 到 224）。

## 四、两道对账闸 + 净位移判据（踩坑记录）

1. 注入后立即 `readback_pairs` == 计划（第一道闸）；rollout 后再读回仍 == 计划
   （防最近邻覆写）。
2. 位姿探针（实例级替换 `task_env.step`，trace[t] 与 h5 timestep_t 同一次调用）反解
   实测事件（第二道闸）。**判定「谁真的交换了」必须用窗口首末净位移（>0.03 m），
   不能用路径长**：对角交换会擦碰被 `other_cube` 锁定的旁观 bin，旁观者被来回抖动
   （实测路径长可达 0.11 m）但净位移近乎零 —— smoke 首跑用路径长阈值 0.02 时，
   VideoUnmaskSwap/ep90 的两条对角变体 (0,2)/(1,3) 被确定性误杀（三次 attempt 的
   path_len 逐位相同）。旁观扰动降级为质量指标：`bystander_net_max` /
   `bystander_path_max` / `disturbed_bins`（净位移 >0.02 记入），写进 h5 与富标签。

## 五、h5 内嵌 swap_gt 标注（RecordWrapper 落盘后追加写）

```
episode_N/timestep_t/swap_gt/   swap_active, swap_window_idx, swap_pair(int8[2]),
                                swap_pair_pos(f32[2,3]), swap_progress,
                                bins_pos(f32[n,3]), cubes_pos(f32[3,3])
episode_N/setup/swap_gt/        env_seed, variant_seed, src_episode, variant_idx,
                                is_original, difficulty, signature, pairs(int8[k,2]),
                                windows(int32[k,2]), candidates(int8[n]),
                                bin_colors(str[n]), net_permutation(int8[n]),
                                task_goal_color, min_clearance, bystander_net_max,
                                bystander_path_max, disturbed_bins,
                                bins_pos_traj(f32[T,n,3]), cubes_pos_traj(f32[T,3,3])
```

合并（`raw.copy` 整组拷贝）自动带走全部标注，合并逻辑零改动。`swap_progress` 用
smoothstep（与 `swap_flat_two_lane` 的 smooth=True 同型），`swap_active` 按
`start <= t < end` 归窗。

## 六、chunk 标签口径（与 MotionJEPA v7 对齐）

- 网格：scope 段（Video→demo、Button→exec）内 `range(0, T_seg-32, 16)`；
  段长口径与 MotionJEPA `build_data_raw_from_h5` 同源：demo = `is_video_demo` 前缀长、
  exec = 段内首个 `is_completed` 真 + 2；**两个 scope 段段内帧号 == env step**（实测）。
- 判正：chunk `[s, s+32]` 内任一窗口的 smoothstep 进度增量最大值 > ε=0.10。
  **不能用简单窗口重叠**：smooth 让窗口末尾几帧几乎不动，人眼判「没在 swap」，
  几何重叠会在 ButtonUnmaskSwap 每个 episode 的窗口尾部多打一个假正例。
- **回归验证（必跑）**：`make_chunk_labels.py --regression` 对官方 train ep90-99 复算
  标签与 `swap_labels_v7.json` 人工资产逐条比对 —— 2026-08-18 实测 **319/319 全对**，
  网格主键完全对齐（ε 在 [0.05, 0.24] 区间均全对，取 0.10）。
- 产物两份：`swap_labels_swapvar.json`（v7 同构 schema，`load_manual_swap` 可直接读）
  与 `swap_events_swapvar.json`（富标签：pair、progress 连续值、swap_kind、
  episode_signature、net_permutation、is_identity_net、is_original、min_clearance、
  bystander 指标）。

## 七、命令用法（按 Phase 顺序）

```bash
# P0a 枚举单测（秒级）
uv run python -m pytest tests/lightweight/test_swap_variant_plan.py -q
# P0b 控制跑（8 条，约 2 min；含与官方 h5 的逐元素比对红线）
uv run python scripts/data-generation-MotionJEPALabel/probe_original.py --gpus 0 --workers 8
# 标签规则回归（只读，约 1 min）
uv run python scripts/data-generation-MotionJEPALabel/make_chunk_labels.py --regression
# P1 smoke（9 条变体）
uv run python scripts/data-generation-MotionJEPALabel/generate_swap_variants.py \
  --tasks VideoUnmaskSwap --src-episodes 92,90 \
  --output-dir scripts/data-generation-MotionJEPALabel/outputs/smoke --gpus 0 --workers 9
# P2 全量（318 条，>5 min 必须 tmux）
tmux new-session -d -s swapvar-full \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run python \
   scripts/data-generation-MotionJEPALabel/generate_swap_variants.py \
   --output-dir scripts/data-generation-MotionJEPALabel/outputs/full --gpus 0 --workers 32 \
   2>&1 | tee scripts/data-generation-MotionJEPALabel/outputs/full_run.log; \
   echo \"EXIT_CODE=\$?\" >> scripts/data-generation-MotionJEPALabel/outputs/full_run.log"
# P3 合并 + 密集重编号 + episode_map
uv run python scripts/data-generation-MotionJEPALabel/merge_variant_h5.py \
  --input-dir scripts/data-generation-MotionJEPALabel/outputs/full --delete-source
# P4 标签 + 验收
uv run python scripts/data-generation-MotionJEPALabel/make_chunk_labels.py \
  --input-dir scripts/data-generation-MotionJEPALabel/outputs/full --dataset-name dataset-swapvar
uv run python scripts/data-generation-MotionJEPALabel/verify_variants.py \
  --gen-dir scripts/data-generation-MotionJEPALabel/outputs/full
```

## 八、验收判据（`verify_variants.py`，全部过才算数）

覆盖完整度 == 枚举期望；布局指纹与 Phase 0 基线逐位相同；is_original 每源恰一条且与
官方 h5 joint_action 逐元素 <1e-5（见下）；同源变体 swap 窗口中点帧哈希两两互异；
scope 段长 ≥ swap 结束帧；merged h5 结构（episode/timestep 连续、末帧 is_completed、
swap_gt 齐全）；min_clearance < 0.055 m 者单列；标签主键集合 == 网格集合。

**is_original 的等价判据（数值 1e-2 兜底 + 结构检查才是主判据）**：控制跑（无注入）
与官方逐位一致（1e-17 级）；is_original 变体因注入把交换对角色规范化为 (小,大)，
与原始随机角色的浮点运算顺序不同（ep91 已静态实证：原始 window1 的 idx1=bin_2，
规范化后翻转），bin 终态 ulp 级差异在**接触链**上混沌放大——接触链越长放大越多：

| episode | 角色 | max_abs_diff | 定性 |
| --- | --- | ---: | --- |
| 6/8 个 episode | 恰与原始一致 | ≤1.1e-17 | 逐位相同 |
| Video/ep92 | 翻转 | 1.363e-06 | 短接触链（一次抓取） |
| Button/ep91 | window1 翻转 | 1.553e-03 | 最长接触链（抓-放-抓）；按钮段严格为 0，
差异从 step 295（首次抓取接触后半程）起指数增长 |

1.5e-3 rad ≈ 0.09°，在环境自身复现包络内（官方历史自复现记录 7.86e-3）。真正证明
「无逻辑分叉」的是结构检查：帧数相等 + simple_subgoal 名称序列完全相同 + 每个切换步
差 ≤2（ep91 实测五个子目标切换步 0/110/200/315/356 完全一致，唯一偏差是「全部完成」
落位 452 vs 453 —— 尾段噪声让完成判定早了一步）。

---

# 实测记录（2026-08-18）

## 九、Phase 0 控制跑（8/8 成功，123.8 s，GPU0，workers=8）

与官方 `/data/hongzefu/robomme_data_h5` 的 joint_action 最大偏差全部在机器精度：

| task/ep | 原始 pairs | T | demo | exec | max_abs_diff |
| --- | --- | ---: | ---: | ---: | ---: |
| ButtonUnmaskSwap/ep90 | 03\|12 | 321 | 0 | 316 | 2.36e-18 |
| ButtonUnmaskSwap/ep91 | 12\|12\|03 | 464 | 0 | 455 | 2.02e-18 |
| ButtonUnmaskSwap/ep92 | 02 | 453 | 0 | 448 | 2.40e-18 |
| ButtonUnmaskSwap/ep93 | 02\|02 | 465 | 0 | 460 | 1.89e-18 |
| VideoUnmaskSwap/ep90 | 12 | 221 | 114 | 98 | 4.81e-19 |
| VideoUnmaskSwap/ep91 | 03\|12 | 407 | 168 | 234 | 1.06e-17 |
| VideoUnmaskSwap/ep92 | 12 | 376 | 114 | 254 | 7.10e-18 |
| VideoUnmaskSwap/ep93 | 12\|12 | 276 | 168 | 103 | 1.15e-17 |

实测 bin 数（4/4/3/3 按难度）与离线复算的 swap_times（Video [1,2,1,2]、Button
[2,3,1,2]）逐条一致；原始序列 min_clearance 全部 ≥0.0699。demo 前缀有 +0~+4 帧
子目标切换延迟（ep91/93 为 168 = 164+4），所以段长必须从产物读、不能纯公式算。

## 十、规模（离线复算 + 单测钉死）

| ep | Video seed/难度/k/变体 | Button seed/难度/k/变体 |
| --- | --- | --- |
| 90 | 14000 medium k=1 → 6 | 16000 medium k=2 → 36 |
| 91 | 14100 hard k=2 → 36 | 16100 hard k=3 → 216 |
| 92 | 14200 easy k=1 → 3 | 16200 easy k=1 → 3 |
| 93 | 14300 easy k=2 → 9 | 16300 easy k=2 → 9 |

Video 小计 54，Button 小计 264，**合计 318**（禁相邻重复则 234，未采用）。
涉及的 8 个 seed 全是规则值（attempt 探针 16401/16801 在 ep94/98，不在本轮范围）。

## 十一、P1 smoke（VideoUnmaskSwap ep92×3 + ep90×6，9/9 成功，83.2 s，验收 PASS）

- 布局指纹与基线逐位一致 9/9；注入读回一致 9/9；净位移对账 9/9；
- 变体互异（swap 窗口中点帧 md5 两两不同）9/9；
- is_original：ep90 var3 ↔ 官方 4.8e-19、ep92 var2 ↔ 官方 1.363e-06（角色顺序效应，见§八）；
- min_clearance 分布：min 0.0561 / 中位 0.1002，0 条低于 0.055；
- 标签 54 条 chunk（27 正例），主键集合与网格完全对齐。

## 十二、全量 318 条（2026-08-18，最终）

生成分三轮（后两轮为 hold 机制迭代，断点续跑自动跳过已成功者）：

| 轮 | 代码状态 | 结果 |
| --- | --- | --- |
| 第一轮（tmux swapvar-full） | 无 hold | 233/318 成功，1599.6 s（8.74 ep/min，GPU0 与他人任务共卡）；85 条 ButtonUnmaskSwap/ep91 耗尽（§三之二 的时序冲突） |
| 续跑一（第一版 hold：挂抓取 entry 前，hold 到 214） | 83/85 成功 | var61/var191 仍败（失败类型 (b)，fail 在按钮 2 的 evaluate 就触发，走不到抓取 entry） |
| 续跑二（第二版 hold：前置到按钮 post-solve evaluate 之前，hold 到 224） | 2/2 成功 | **最终 318/318，穷举无缺口** |

- 事后闸门：布局指纹与 Phase 0 基线逐位一致 **0 失配**；is_original 每源恰 1 条。
- 合并（`--delete-source`）：Video 54 条 → 12.7 GiB，Button 264 条 → 72.3 GiB，共 **85 GiB**；
  episode/timestep 连续、末帧 is_completed、swap_gt 齐全校验全过。
- 标签：**7268 条 chunk，swap=1 共 2784 条**；主键网格与 merged h5 完全对账；
  规则先过 319/319 人工资产回归。
- is_original 八条明细见 §八表格。
- **数据质量分布（下游过滤依据）**：min_clearance min=0.0007 / p05=0.0045 /
  中位=0.0504；**193/318 条 < 0.055 m**（对角/远距交换穿过被锁定的旁观 bin ——
  原始数据因最近邻配对天然避开，穷举必然引入；环境原行为，不修改，逐条量化在
  episode_map 与富标签）。hold 补救 85 条（83 条 hold→214、2 条 hold→224），
  `attempt`/`pickup_hold_step` 逐条可查。
