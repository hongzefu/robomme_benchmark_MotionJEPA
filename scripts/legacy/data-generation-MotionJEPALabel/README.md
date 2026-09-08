# data-generation-MotionJEPALabel — 单事件 swap clip 数据集

对 VideoUnmaskSwap / ButtonUnmaskSwap 的 **train ep90-99 + test ep0-49 + val ep0-49**
三个 split 筛源（实际入选 **33 源**：train {91,95,98,99}、test 15 源、val 14 源），
每条产出 **110 帧 clip**（env step `[34,144)` = 第一次 swap 窗口 `[64,114)` 前后各 30 帧），
共 **153 条**（Video 80 + Button 73）。
机制细节、接触检测、动作泄露、十二条验收判据与全部实测记录见 [CLAUDE.md](CLAUDE.md)。

## 数据集口径

| 性质 | 是否成立 | 证据（实测，2026-08-19 三 split 全量） |
| --- | --- | --- |
| ① bin 初始位置与原版 dataset 一致 | **是，逐位一致** | 同 env_seed 播种、注入零 RNG 消耗；判据 2：每条 clip 的槽位 xy 与 Phase 0 基线逐位相同；train 8 源控制跑对官方 h5 的 joint_action 在 clip 区间严格 0.0（test/val 无官方 h5，逐位比对无对象，其真值即 Phase 0 控制跑自身，重跑逐位一致）；事件前 30 帧 `bins_pos` 跨变体最大差 0.000e+00 |
| ② 第二次 swap 恒定 | **是（1 源例外，已量化）** | 钉死为该源**原版 episode 实际发生的那次**（按槽位）：clip 末帧位置集合跨变体最大差 ≤1e-5，唯 Button/val/ep11 两条变体差 1.3e-2/6.5e-3 —— 该源对角对入选最近邻、事件窗口内容器互撞冲量 ~17 把旁观 bin 撞离未弹回，属第一次 swap 的物理余波，按「保留 + 量化」进告警不作废（`bystander_net_max` 逐条量化）；生成闸门断言同源尾部唯一 |
| ③ 第一次 swap 排列组合不同，但受最近邻约束 | **是** | 每源枚举 2~3 个组合、彼此不同；判据 12：153/153 条的事件对都满足「其一是另一的严格最近邻」（Phase 0 几何与 clip 自身事件前一帧实测几何两路复算一致）；原始首对 33/33 源命中，有方向判据（原版 idx2 == NN(idx1)）33/33 |

**源筛选**（逐 split 独立执行）：只看 **4-bin** 布局（easy 是 3-bin、模板与类别体系不同，
剔除），再要求 swap 次数 ≥2 且两 env 取**split 内**共同源号 ⇒
train ep90-99 剩 {91,95,98,99}、test ep0-49 剩 15 源、val ep0-49 剩 14 源。
seed 一律读所属 split 的 metadata（`src/robomme/env_metadata/{split}/`），**禁止公式反推**
—— train Button ep98 是 16801、val Button ep39/ep43 是 1073901/1074301（attempt 尾号）。

### 生成的排列组合：每个源 episode 出 2 或 3 条变体

第一次 swap 的可选组合 = 每个容器配上离它最近的邻居、去重
（`nearest_neighbor_pairs(slot_xy)`），**每个源 episode 的变体条数就等于这个集合的大小，
恒为 2 或 3**：全局最近的一对必互为最近邻、去重成 1 对 ⇒ 上界 3；每个槽位至少贡献
1 对 ⇒ 下界 2。理论全枚举 C(4,2)=6，被最近邻约束砍掉的主要是对角/长距对。
实测分布：66 个 (env, 源) 中 **45 个出 2 条、21 个出 3 条**（Video 19/14、Button 26/7），
45×2 + 21×3 = 153 与总数对账。
主标签 `event_slots` 全体分布 **03:63 / 12:63 / 01:11 / 23:14 / 02:2**；
33 源 × 2 env 的逐源合法对全表见 `verification_report.md` 的「逐源明细」，train 部分与
历史版本完全一致（Video 11 + Button 8 = 19 条）。

⚠ 对角组合首次真实出现：**Button/val/ep11 的合法集合含 (0,2)、val/ep31 含 (0,2)** ——
「对角进不了最近邻」只是 train 8 源的实测事实、不是几何必然，验收判据 10c-iii 对此
已从硬失败降级为**告警 + 计数**（本轮 cross_diagonal 2 条），正确性由 topo 分布的
两路对账硬判据兜底。

## 产物形态

三类产物 = **diagram / h5 / video**；另两项是映射与凭据。过程产物由 `prune_outputs.py`
在验收通过后清掉（它会先确认 Phase 0 索引完整、链路可再次跑生成，再动手）。

```
outputs/event1/
  record_dataset_{Task}.h5                ← 三类之一（Video 5.46 GiB / Button 4.98 GiB）
  record_dataset_{Task}_metadata.json     ← 随 h5（官方格式配套，seed = variant_seed，
                                             每条记录带 split 溯源字段）
  videos/                                 ← 三类之一（153 条截断 rollout 录像）
  diagrams/                               ← 三类之一（79 张：66 张逐源
                                             {Task}_{split}_ep{N}_clips.png +
                                             contact_summary.png 总表 +
                                             contact_overview / contact_timeline
                                             按 (task, split) 各 6 页）
  episode_map_{Task}.json                 ← 新旧编号 ↔ split/源ep/变体/几何全映射 + **全部
                                             派生标签与协变量**（唯一标签载体）
  verification_report.md                  ← 验收唯一产物：十二条判据 + 分 split 汇总 + 告警段
outputs/phase0/
  original_index.json                     ← 只留它（★ 唯一不可静态重算，见下）
```

### h5 新增字段

相对官方格式只加两处组（`setup/swap_gt` 与 `timestep_t/swap_gt`），**其余官方字段一字未动**。
口径是**只留不可复算的**：

`setup/swap_gt` 11 个 ——

| 字段 | 作用 | 为什么不能删 |
| --- | --- | --- |
| `env_seed` | 建环境的种子 | 复现这条 clip 的唯一入口。`variant_seed` 复现不了（它只是编号），必须用 `env_seed` 建环境再按 `bin_pairs` 注入 |
| `bin_pairs` | 完整交换序列的 bin 口径 `(k,2)` | 复现时直接喂给 `swap_inject.inject_pairs`；`slot_pairs` 由它互逆换算 |
| `event_slots` | ★ 主标签轴 —— 第一次 swap 移动的槽位对 | 数据集存在的理由。虽然 = `slot_pairs[0]`，但标签不能靠推，必须显式 |
| `slot_xy` | 4 个槽位的初始 xy `(4,2)` | 全部几何的复算根：最近邻集合、`topo_class`、`pair_distance/azimuth`、`reference_axis_deg` 全从它算。它本身来自 env 布局，静态算不出 |
| `split` | 源属于哪个 split（train/test/val） | episode 号只在 split 内可比；env_seed 反查 split 要翻三份 metadata ⇒ 不可复算 |
| `src_episode` | 来自该 split 的哪条 | 同源分组的键（判据 3/4/5/7 全是「同源变体之间」的比较）—— 配 `split` 才唯一 |
| `variant_idx` | 变体编号（稀疏 `C(4,2)` 下标） | 跨源可比的对齐键（任意源的 var2 都是 (0,3)）；文件名、断点续跑 key 都用它 |
| `is_original` | 这条是否逐位复现原版 episode | 需与原版序列比对才知道，h5 里没有原版序列 ⇒ 不可复算。每源恰 1 条，是判据 1 的检查项 |
| `difficulty` | medium / hard | 读所属 split 的 metadata 得来（attempt 尾号 seed 公式反推不出），纯读表 |
| `clip_start_env_step` | 34 | clip 帧 ↔ env step 的换算基准。没它 h5 不自解释，得回头查文档 |
| `clip_len` | 110 | 同上，段长自解释 |

`timestep_t/swap_gt` 8 个 —— 全是物理引擎实测，一个都推不出来：

| 字段 | 作用 |
| --- | --- |
| `bins_pos` `(4,3)` | 逐帧 4 个容器位置 —— 事件的物理真值。判据 3（前 30 帧不变）、判据 5（末帧位置集合）、判据 6（窗口净位移 ≥0.03 m）、判据 12b（事件前一帧几何交叉复核）全靠它；`min_clearance`/`bystander_*`/`disturbed_bins` 也从它现算 |
| `cubes_pos` `(3,3)` | 逐帧 3 个 cube 位置 —— 判据 8 的可见性分段（帧 0-29 在容器内 z<0.1、帧 30-109 已藏走 z>5），证明颜色从不进画面 |
| `contact_robot_bin_{count,impulse}` | 判据 11 的原始数据：机械臂有没有被 swap 中的容器碰到（实测 0/153）。这是「机器人动作只由任务本身决定」这个前提的守卫 |
| `contact_bin_bin_{count,impulse}` | 容器互撞 —— Button 关节角泄露因果链的第一环（互撞 → PhysX 求解顺序变 → 按钮接触力变 → 关节角偏离） |
| `contact_robot_button_{count,impulse}` | 任务本身的接触（Button 侧 press、Video 0 帧），是上面那条因果链的第二环 |

另有 `setup/meta/`（`bin_colors` / `color_names` / `task_goal_color`，Button 多两个按钮位置）——
来自 env、不可复算，但**明确是纯 metadata、不进标签**（数据集刻意不含颜色轴）。

其余被删掉的字段全部可由上表字段 + `clip_plan.py` 的纯函数复算，逐项复算路径见
[CLAUDE.md](CLAUDE.md) §六；派生标签与协变量一律去 `episode_map_{Task}.json` 取，那里是齐的。

### 编号与 seed（split 扩源后的口径）

* `staging_episode = split_code*1_000_000 + src_episode*1000 + variant_idx`
  （`split_code`: train=0 / test=1 / val=2）；merge 后密集重编号按
  `(split 序, src_episode, variant_idx)`，train 块在前。
* `variant_seed = env_seed*1000 + variant_idx` **刻意不编码 split**（它是 metadata 的
  `seed` 字段、须可逆到 env_seed）；跨 split 唯一性来自三个 split 的 env_seed 数值域
  不相交，由三重守卫断言（单测全组合、生成闸门、merge 闸门），不靠默认成立。

## 生成链路

八步，每步的产物是下一步的输入；全链路（不含 Phase 0）约 5 分钟。

```
① Phase 0 控制跑  probe_original.py        66 条完整 rollout（不注入），~2.5 min
   └→ outputs/phase0/original_index.json   ★ 唯一不可静态重算的产物：
        · 原始 swap 序列（容器/槽位两口径）——第二次及以后钉死成什么的唯一来源
        · 原版被交换的第一个容器——「第二个 == 它的最近邻」带方向核对用
        · 容器摆位 / 各自最近邻 / 判定余量 / 合法对；布局指纹；train 源对官方数据的
          红线比对（test/val 无官方 h5，记入 comparison_skipped 显式呈现、不判失败）
② 计划表  clip_plan.py                     纯函数，不产数据
   └→ 读①的摆位 → 逐源 2/3 条、合计 153（没有①只给 ≤396 上界，绝不冒充真值）
③ 生成    generate_swap_clips.py           153 条截断 rollout，~3 min
   └→ videos/（留）；clips/*.h5、traces/、clips_manifest.json、clip_results.jsonl、
      run_*.json 都是**过程产物**，⑧ 清掉
      收尾闸门：指纹与①一致、每源恰 1 条原始变体、实际换的组合 == 合法对集合、
      variant_seed 全局唯一（split 不编码进 seed 的守卫）
④ 合并    merge_clip_h5.py --delete-source
   └→ record_dataset_{Task}.h5             官方格式，episode 密集重编号（Video 0-79、Button 0-72）
      record_dataset_{Task}_metadata.json   seed = variant_seed，每条带 split
      episode_map_{Task}.json               新旧编号 ↔ split/源ep/变体/标签/几何 全映射
⑤ 标签    make_clip_labels.py              不新增文件，把 6 个不可复算的派生字段
   └→ 增补进 episode_map_{Task}.json        （action_group/action_dev_max ×4、
                                             later_windows_follow_native_nn ×2）+ 标签 meta 块
⑥ 验收    verify_clips.py                  读①④⑤三方对账；h5 侧的类别/接触/最近邻全部**现算**
   └→ verification_report.md               十二条判据 + 分 split 汇总 + 告警段（退出码非 0 = 有判据未过）
⑦ 出图    draw_clip_diagrams.py
   └→ diagrams/{Task}_{split}_ep{N}_clips.png  每源一张（66 张），进不来的组合留空并标注原因
      diagrams/contact_summary.png              一张总表（每 (task,split) 一行）
      diagrams/contact_overview_{Task}_{split}.png   接触矩阵分页（色深刻度全局统一）
      diagrams/contact_timeline_{Task}_{split}.png   接触落在哪些帧（分页）
⑧ 清理    prune_outputs.py --yes           先确认①的索引完整（= 链路可再次跑生成），
                                            再删③的过程产物与 Phase 0 的 h5/录像/trace
```

```bash
uv run python -m pytest tests/lightweight/test_swap_clip_plan.py -q
uv run python scripts/legacy/data-generation-MotionJEPALabel/probe_original.py --gpus 0,1 --workers 16
uv run python scripts/legacy/data-generation-MotionJEPALabel/clip_plan.py --original-index scripts/data-generation-MotionJEPALabel/outputs/phase0/original_index.json
uv run python scripts/legacy/data-generation-MotionJEPALabel/generate_swap_clips.py --output-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --gpus 0,1 --workers 16
uv run python scripts/legacy/data-generation-MotionJEPALabel/merge_clip_h5.py --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --delete-source
uv run python scripts/legacy/data-generation-MotionJEPALabel/make_clip_labels.py --regression   # 改判正规则后必跑，319/319
uv run python scripts/legacy/data-generation-MotionJEPALabel/make_clip_labels.py --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1
uv run python scripts/legacy/data-generation-MotionJEPALabel/verify_clips.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
uv run python scripts/legacy/data-generation-MotionJEPALabel/draw_clip_diagrams.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
uv run python scripts/legacy/data-generation-MotionJEPALabel/prune_outputs.py --yes
```

三条 split 全选是默认值；`--splits train`、`--only-sources test:3,val:3` 可做子集调试。
⚠ ①与③均已超 5 分钟量级的边缘，按仓库规约用 tmux detached + Monitor 跑（模板见根
`AGENTS.md` 规则 4）。两条硬顺序约束：**①必须早于删除任何旧产物**（第二次及以后 swap
换的是谁只能实跑读回，静态算不出）；**③④⑤必须同批**（④删源，源没了无法只重跑④）。
另：全量重生成前必须删掉旧 `clip_results.jsonl` —— 旧键形（无 split）会污染断点续跑。
磁盘：清理后 `outputs/phase0/` 约 0.4 MiB + `outputs/event1/` 约 10.8 GiB，均已 gitignore。
