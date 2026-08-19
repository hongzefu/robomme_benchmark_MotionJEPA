# data-generation-MotionJEPALabel — 单事件 swap clip 数据集

对 VideoUnmaskSwap / ButtonUnmaskSwap 的 train **ep91/95/98/99**，每条产出 **110 帧 clip**
（env step `[34,144)` = 第一次 swap 窗口 `[64,114)` 前后各 30 帧），共 **19 条**。
机制细节、接触检测、动作泄露、十二条验收判据与全部实测记录见 [CLAUDE.md](CLAUDE.md)。

## 数据集口径

| 性质 | 是否成立 | 证据（实测） |
| --- | --- | --- |
| ① bin 初始位置与原版 dataset 一致 | **是，逐位一致** | 同 env_seed 播种、注入零 RNG 消耗；判据 2：每条 clip 的槽位 xy 与 Phase 0 基线逐位相同；控制跑对官方 h5 的 joint_action 在 clip 区间严格 0.0；事件前 30 帧 `bins_pos` 跨变体逐位相同（差 0.0） |
| ② 第二次 swap 恒定 | **是** | 钉死为该源**原版 episode 实际发生的那次**（按槽位）：同源全部变体的第二次 swap 移动同样两个槽位，clip 末帧位置集合跨变体最大差 1.01e-6；生成闸门断言同源尾部唯一 |
| ③ 第一次 swap 排列组合不同，但受最近邻约束 | **是** | 每源枚举 2~3 个组合、彼此不同；判据 12：19/19 条的事件对都满足「其一是另一的严格最近邻」（用该源实测摆位复算，且用 clip 自身事件前一帧的位置交叉复核过） |

**源筛选**：目前只看 **4-bin** 布局（easy 是 3-bin、模板与类别体系不同，剔除），再要求
swap 次数 ≥2 且两 env 取共同源号 ⇒ **ep90-99 里只剩 {91, 95, 98, 99} 这 4 个 seed**
（Video 14100/14500/14800/14900；Button 16100/16500/16801/16900，ep98 是历史 attempt
探针值、必须读表不能公式反推）。

### 生成的排列组合

第一次 swap 的可选组合 = 每个容器配上离它最近的邻居、去重（4 容器时恒 2~3 对）。
★ = 该源原版实际发生的那对（is_original，逐位复现官方 episode）：

| 源 | 第一次 swap 的槽位组合 | 条数 |
| --- | --- | ---: |
| Video ep91 | 0-3★、1-2 | 2 |
| Video ep95 | 0-1★、0-3、1-2 | 3 |
| Video ep98 | 0-3★、1-2、2-3 | 3 |
| Video ep99 | 0-1★、0-3、2-3 | 3 |
| Button ep91 | 0-3、1-2★ | 2 |
| Button ep95 | 0-3★、1-2 | 2 |
| Button ep98 | 0-3、1-2★ | 2 |
| Button ep99 | 0-3★、1-2 | 2 |

合计 **19 条**（Video 11 + Button 8）；主标签 `event_slots` 分布 **03:8 / 12:7 / 01:2 / 23:2**。
对角组合 0-2 / 1-3 从来不是任何容器的最近邻，结构上进不了枚举——这正是旧口径 6 种全枚举
（48 条）收敛到 19 条的原因。

## 产物形态

三类产物 = **diagram / h5 / video**；另两项是映射与凭据。过程产物由 `prune_outputs.py`
在验收通过后清掉（它会先确认 Phase 0 索引完整、链路可再次跑生成，再动手）。

```
outputs/event1/
  record_dataset_{Task}.h5                ← 三类之一（Video 0.75 GiB / Button 0.55 GiB）
  record_dataset_{Task}_metadata.json     ← 随 h5（官方格式配套，seed = variant_seed）
  videos/                                 ← 三类之一（19 条截断 rollout 录像，39 MiB）
  diagrams/                               ← 三类之一（每源一张 + 接触矩阵 + 接触时间轴）
  episode_map_{Task}.json                 ← 新旧编号 ↔ 源ep/变体/几何全映射 + **全部派生
                                             标签与协变量**（唯一标签载体）
  verification_report.md                  ← 验收唯一产物：十二条判据 + 告警段
outputs/phase0/
  original_index.json                     ← 只留它（★ 唯一不可静态重算，见下）
```

### h5 新增字段

相对官方格式只加两处组（`setup/swap_gt` 与 `timestep_t/swap_gt`），**其余官方字段一字未动**；
实测新增部分 11.7 KiB/episode，占文件 **0.017%**。口径是**只留不可复算的**：

`setup/swap_gt` 10 个 ——

| 字段 | 作用 | 为什么不能删 |
| --- | --- | --- |
| `env_seed` | 建环境的种子 | 复现这条 clip 的唯一入口。`variant_seed` 复现不了（它只是编号），必须用 `env_seed` 建环境再按 `bin_pairs` 注入 |
| `bin_pairs` | 完整交换序列的 bin 口径 `(k,2)` | 复现时直接喂给 `swap_inject.inject_pairs`；`slot_pairs` 由它互逆换算 |
| `event_slots` | ★ 主标签轴 —— 第一次 swap 移动的槽位对 | 数据集存在的理由。虽然 = `slot_pairs[0]`，但标签不能靠推，必须显式 |
| `slot_xy` | 4 个槽位的初始 xy `(4,2)` | 全部几何的复算根：最近邻集合、`topo_class`、`pair_distance/azimuth`、`reference_axis_deg` 全从它算。它本身来自 env 布局，静态算不出 |
| `src_episode` | 来自 train 的哪条（91/95/98/99） | 同源分组的键 —— 判据 3/4/5/7 全是「同源变体之间」的比较，没它没法分组 |
| `variant_idx` | 变体编号（稀疏 `C(4,2)` 下标） | 跨源可比的对齐键（Button ep91 的 var2 与 Video ep98 的 var2 都是 (0,3)）；文件名、断点续跑 key 都用它 |
| `is_original` | 这条是否逐位复现官方 episode | 需与原版序列比对才知道，h5 里没有原版序列 ⇒ 不可复算。每源恰 1 条，是判据 1 的检查项 |
| `difficulty` | medium / hard | 读 train metadata 得来（ep98 的 seed 是历史 attempt 值 16801，公式反推不出），纯读表 |
| `clip_start_env_step` | 34 | clip 帧 ↔ env step 的换算基准。没它 h5 不自解释，得回头查文档 |
| `clip_len` | 110 | 同上，段长自解释 |

`timestep_t/swap_gt` 8 个 —— 全是物理引擎实测，一个都推不出来：

| 字段 | 作用 |
| --- | --- |
| `bins_pos` `(4,3)` | 逐帧 4 个容器位置 —— 事件的物理真值。判据 3（前 30 帧不变）、判据 5（末帧位置集合）、判据 6（窗口净位移 ≥0.03 m）、判据 12b（事件前一帧几何交叉复核）全靠它；`min_clearance`/`bystander_*`/`disturbed_bins` 也从它现算 |
| `cubes_pos` `(3,3)` | 逐帧 3 个 cube 位置 —— 判据 8 的可见性分段（帧 0-29 在容器内 z<0.1、帧 30-109 已藏走 z>5），证明颜色从不进画面 |
| `contact_robot_bin_{count,impulse}` | 判据 11 的原始数据：机械臂有没有被 swap 中的容器碰到（实测 0/19）。这是「机器人动作只由任务本身决定」这个前提的守卫 |
| `contact_bin_bin_{count,impulse}` | 容器互撞 —— Button 关节角泄露因果链的第一环（互撞 → PhysX 求解顺序变 → 按钮接触力变 → 关节角偏离） |
| `contact_robot_button_{count,impulse}` | 任务本身的接触（Button 每条 17 帧、Video 0 帧），是上面那条因果链的第二环 |

另有 `setup/meta/`（`bin_colors` / `color_names` / `task_goal_color`，Button 多两个按钮位置）——
来自 env、不可复算，但**明确是纯 metadata、不进标签**（数据集刻意不含颜色轴）。

被删掉的 37 + 7 个字段（`topo_class` / `pair_*` / `legal_event_slots` / `slot_nn_margin` /
`net_permutation` / `signature` / `variant_seed` / `windows_*` / `slot_pairs` / `*_traj` /
`min_clearance` / `bystander_*` / 15 个 contact 聚合量 / `swap_active` / `swap_progress` / …）
全部可由上表字段 + `clip_plan.py` 的纯函数复算，逐项复算路径见 [CLAUDE.md](CLAUDE.md) §六；
派生标签与协变量一律去 `episode_map_{Task}.json` 取，那里是齐的。

## 生成链路

八步，每步的产物是下一步的输入；全链路（不含 Phase 0）约 1 分钟。

```
① Phase 0 控制跑  probe_original.py        8 条完整 rollout（不注入），~32 s
   └→ outputs/phase0/original_index.json   ★ 唯一不可静态重算的产物：
        · 原始 swap 序列（容器/槽位两口径）——第二次及以后钉死成什么的唯一来源
        · 原版被交换的第一个容器——「第二个 == 它的最近邻」带方向核对用
        · 容器摆位 / 各自最近邻 / 判定余量 / 合法对；布局指纹；对官方数据的红线比对
② 计划表  clip_plan.py                     纯函数，不产数据
   └→ 读①的摆位 → 逐源 2/3 条、合计 19（没有①只给 ≤48 上界，绝不冒充真值）
③ 生成    generate_swap_clips.py           19 条截断 rollout，~40 s
   └→ videos/（留）；clips/*.h5、traces/、clips_manifest.json、clip_results.jsonl、
      run_*.json 都是**过程产物**，⑧ 清掉
      收尾闸门：指纹与①一致、每源恰 1 条原始变体、实际换的组合 == 合法对集合
④ 合并    merge_clip_h5.py --delete-source
   └→ record_dataset_{Task}.h5             官方格式，episode 密集重编号（Video 0-10、Button 0-7）
      record_dataset_{Task}_metadata.json   seed = variant_seed
      episode_map_{Task}.json               新旧编号 ↔ 源ep/变体/标签/几何 全映射
⑤ 标签    make_clip_labels.py              不新增文件，把 6 个不可复算的派生字段
   └→ 增补进 episode_map_{Task}.json        （action_group/action_dev_max ×4、
                                             later_windows_follow_native_nn ×2）+ 标签 meta 块
⑥ 验收    verify_clips.py                  读①④⑤三方对账；h5 侧的类别/接触/最近邻全部**现算**
   └→ verification_report.md               十二条判据 + 告警段（退出码非 0 = 有判据未过）
⑦ 出图    draw_clip_diagrams.py
   └→ diagrams/{Task}_ep{N}_clips.png      每源一张，进不来的组合留空并标注原因
      diagrams/contact_overview.png         接触矩阵（对角两列恒空）
      diagrams/contact_timeline.png         接触落在哪些帧
⑧ 清理    prune_outputs.py --yes           先确认①的索引完整（= 链路可再次跑生成），
                                            再删③的过程产物与 Phase 0 的 h5/录像/trace
```

```bash
uv run python -m pytest tests/lightweight/test_swap_clip_plan.py -q
uv run python scripts/data-generation-MotionJEPALabel/probe_original.py --gpus 0,1 --workers 8
uv run python scripts/data-generation-MotionJEPALabel/clip_plan.py --original-index scripts/data-generation-MotionJEPALabel/outputs/phase0/original_index.json
uv run python scripts/data-generation-MotionJEPALabel/generate_swap_clips.py --output-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --gpus 0,1 --workers 16
uv run python scripts/data-generation-MotionJEPALabel/merge_clip_h5.py --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --delete-source
uv run python scripts/data-generation-MotionJEPALabel/make_clip_labels.py --regression   # 改判正规则后必跑，319/319
uv run python scripts/data-generation-MotionJEPALabel/make_clip_labels.py --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1
uv run python scripts/data-generation-MotionJEPALabel/verify_clips.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
uv run python scripts/data-generation-MotionJEPALabel/draw_clip_diagrams.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
uv run python scripts/data-generation-MotionJEPALabel/prune_outputs.py --yes
```

两条硬顺序约束：**①必须早于删除任何旧产物**（第二次及以后 swap 换的是谁只能实跑读回，
静态算不出）；**③④⑤必须同批**（④删源，源没了无法只重跑④）。
磁盘：清理后 `outputs/phase0/` 64 KiB + `outputs/event1/` 1.33 GiB，均已 gitignore。
