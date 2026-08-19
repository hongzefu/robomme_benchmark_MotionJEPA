# data-generation-MotionJEPALabel — 单事件 swap clip 数据集

对 VideoUnmaskSwap / ButtonUnmaskSwap 的 train **ep91/95/98/99**，只保留**一个事件**——
第一次 swap：枚举它的**最近邻可达槽位对**（每源 2~3 个），其余全部钉死，每条产出
**110 帧 clip**（env step `[34,144)` = 第一次 swap 窗口 `[64,114)` 前后各 30 帧），共 **19 条**。
完整机制与实测记录见 [CLAUDE.md](CLAUDE.md)。

**宗旨：除了 bin 的初始位置和第一次 swap 的排列组合，其他全部保持一致。**

**最近邻约束（2026-08-19 重构，48 → 19 条）**：原版环境的第二个被交换容器恒取第一个的
**严格最近邻**（无随机），旧口径 6 种全枚举里 29/48 条原版结构上不可能出现（对角组合从来
不是任何容器的最近邻）。本轮放宽第一个容器、第二个仍取最近邻 ⇒ 每条事件都原版可达。
约束只作用于第一次 swap；第二次及以后按槽位钉死，保后 30 帧跨变体一致。

## 结论速览（2026-08-19 全量实测）

| 项 | 结果 |
| --- | --- |
| 生成 | **19/19 成功**，38.2 s，零重试、零闸门失败 |
| ★ 最近邻不变量 | 19/19 条事件换的都是一对最近邻；原版数据逐源反查（第二个容器 == 第一个的最近邻）**8/8 命中** |
| ★ 机器人动作恒定 | Video **逐位相同（严格 0.0）**；Button 有已知泄露，见下 |
| 事件前 30 帧 | `bins_pos` 跨同源变体逐位相同（0.0，14 次比较） |
| 事件后 30 帧 | clip 末帧容器位置集合跨变体最大差 **1.01e-6** |
| 控制跑 ↔ 官方数据 | 8/8 源 joint_action 全程 ≤2.6e-17，**clip 区间严格 0.0** |
| 主标签分布 | `event_slots` 四类 **03:8 / 12:7 / 01:2 / 23:2**（不均衡，不做重采样） |
| 标签规则回归 | 对官方 ep90-99 复算，与 v7 人工资产 **319/319 全对** |
| 接触检测 | 机械臂 ↔ 容器 **0/19**；容器互撞 **1/19** |
| 验收 | **十二条判据全过** + 2 条告警；单测 69 passed |
| 体量 | merged h5 **1.30 GiB**（Video 0.75 + Button 0.55） |

## 为什么恰好是 19 条

**第一次 swap 的合法对完全由容器初始摆位决定，没有自由度**：每个容器配上离它最近的邻居，
去重即全部可能；4 容器时恒 2~3 对（全场最近的两个互认、去重成一对，另两个各贡献至多一对）。
判定余量（次近减最近距离）最小 0.0089 m，比落位噪声高三个数量级，无平局风险。

| 源 | 合法对（槽位） | 条数 | 最小余量 (m) |
| --- | --- | ---: | ---: |
| Video ep91 | 0-3、1-2 | 2 | 0.0695 |
| Video ep95 | 0-1、0-3、1-2 | 3 | 0.0145 |
| Video ep98 | 0-3、1-2、2-3 | 3 | **0.0089** |
| Video ep99 | 0-1、0-3、2-3 | 3 | 0.0122 |
| Button ep91/95/98/99 | 均为 0-3、1-2 | 2 ×4 | 0.0551 / 0.0184 / 0.0207 / 0.0921 |

**第二次 swap 没有自由度，所以总数就是 19**：原版第二次 swap 的第一个容器在场景生成时
就定死，第二个仍取最近邻 ⇒ 第一次一确定，第二次唯一确定。钉死槽位是 19 条，改按原版规则
走也还是 19 条，差别只在下面 4 条第二次换哪对，不在数量。唯一能变多的是把第二次的第一个
容器也放开（每条 ×2~3），但后 30 帧就不再跨变体一致，与宗旨冲突，未采用。

**两种口径在 4 条上不重合**（本链路认槽位，原版认那个固定的容器——第一次 swap 可能已把它
挪到别的槽位）：

| 变体 | 第一次换的槽位 | 本链路第二次换的 | 原版规则会换的 |
| --- | --- | --- | --- |
| Video ep95/var3 | 1-2 | 1-2 | **0-1** |
| Video ep98/var3 | 1-2 | 1-2 | **2-3** |
| Video ep99/var2 | 0-3 | 0-1 | **0-3** |
| Video ep99/var5 | 2-3 | 0-1 | **0-3** |

Button 8 条全部重合：其最近邻关系恰好两两配对（0 与 3 互认、1 与 2 互认），容器怎么挪都
对称。事件本身 19/19 原版可达；要求整条 clip 都原版可达，按标签字段
`later_windows_follow_native_nn` 筛，得 **15/19 条**。

## 接触检测（物理引擎实测）

sapien `get_contacts()` 逐帧扫描，冲量 > 1e-9 才算真撞（PhysX 会把贴近未受力的也配成接触对）：

| 接触类型 | 结果 |
| --- | --- |
| 机械臂 ↔ 容器 | **0/19**（判据 11：机器人从未被 swap 中的容器碰到） |
| 容器 ↔ 容器 | **1/19**（Video ep99/var5，1 帧、冲量 0.0012） |
| 机械臂 ↔ 按钮 | Button 每条 17 帧 / Video 0 帧（任务本身，对照基线） |

互撞几乎消失是最近邻约束的直接后果：最近邻对都是短程对、路径不穿过第三个容器（全枚举版
20/48 主要来自被删的对角/长距对）。接触与净空字段因此退化为近似常量，价值转为**回归守卫**。

## ⚠ 已知问题：ButtonUnmaskSwap 的动作通道泄露

Button 侧 `joint_action` 跨同源变体最大差 **3.2e-2 rad**（全枚举版 1.6e-1）；Video 严格 0.0。
根因链（实测定位，非机械臂被碰）：交换中的容器互撞 → PhysX 接触求解变化 → 机械臂-按钮
接触力数值解偏移 → 关节角偏离 → 后续规划分叉。零 src 改动无法消除，逐帧实证见 CLAUDE.md §八。

处置（用户拍板）：全部保留并逐条量化，标签三个可过滤字段——

- `action_dev_max`：与同源其他变体的最大绝对差；**要无泄露子集就筛它 == 0，得 15/19 条**；
- `action_group`：同源内逐位相同的等价组 id；⚠ 同源仅 2 条时「取同一组」退化成 1 条，勿用旧口径；
- `action_group_identifies_label`：等价组数 == 变体数 ⇒ 关节角可完全反推标签（Button ep91/ep99 命中）。

## 生成链路与产物

七步，每步的产物是下一步的输入；全链路（不含 Phase 0）约 1 分钟。

```
① Phase 0 控制跑  probe_original.py        8 条完整 rollout（不注入），~32 s
   └→ outputs/phase0/original_index.json   ★ 唯一不可静态重算的产物：
        · 原始 swap 序列（容器/槽位两口径）——第二次及以后钉死成什么的唯一来源
        · 原版被交换的第一个容器——「第二个 == 它的最近邻」带方向核对用
        · 容器摆位 / 各自最近邻 / 判定余量 / 合法对；布局指纹；对官方数据的红线比对
② 计划表  clip_plan.py                     纯函数，不产数据
   └→ 读①的摆位 → 逐源 2/3 条、合计 19（没有①只给 ≤48 上界，绝不冒充真值）
③ 生成    generate_swap_clips.py           19 条截断 rollout，~38 s
   └→ clips/*.h5（每变体 110 帧）  clips_manifest.json  clip_results.jsonl
      traces/ videos/ logs/
      收尾闸门：指纹与①一致、每源恰 1 条原始变体、实际换的组合 == 合法对集合
④ 合并    merge_clip_h5.py --delete-source
   └→ record_dataset_{Task}.h5             官方格式，episode 密集重编号（Video 0-10、Button 0-7）
      record_dataset_{Task}_metadata.json   seed = variant_seed
      episode_map_{Task}.json               新旧编号 ↔ 源ep/变体/标签/几何 全映射
⑤ 标签    make_clip_labels.py
   └→ clip_events.json                     ★ 主标签（主轴 event_slots + 协变量 + 约束说明）
      swap_labels_clip.json                 chunk 级二值（v7 同 schema）
      swap_events_clip.json                 chunk 级富标签
⑥ 验收    verify_clips.py                  读①④⑤三方对账
   └→ verification_report.{json,md}        十二条判据 + 告警段（退出码非 0 = 有判据未过）
⑦ 出图    draw_clip_diagrams.py
   └→ diagrams/{Task}_ep{N}_clips.png      每源一张，进不来的组合留空并标注原因
      diagrams/contact_overview.png         接触矩阵（对角两列恒空）
      diagrams/contact_timeline.png         接触落在哪些帧
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
```

两条硬顺序约束：**①必须早于删除任何旧产物**（第二次及以后 swap 换的是谁只能实跑读回，
静态算不出）；**③④⑤必须同批**（④删源，源没了无法只重跑④）。
磁盘：`outputs/phase0/` 2.1 GiB（索引产出后 h5/录像可删、索引要留）+ `outputs/event1/` 1.4 GiB，均已 gitignore。

## 关键口径（详见 CLAUDE.md）

- **源三重筛选**：4-bin → k≥2 → 两 env 共同源号 ⇒ 恒 `{91,95,98,99}`；条数由最近邻结构
  决定，不再对称（Video 11 vs Button 8）。
- **最近邻判定只看初始摆位**：第一次 swap 在第 64 步，容器第 32 步已落回原位，Phase 0 的
  摆位即够。⚠ env 源码里的 `_compute_dynamic_swap_candidates` /
  `_select_swap_pair_from_positions`（取最近两个再随机）是**全仓无调用点的死代码**，勿采信。
- **第二次及以后按槽位钉死**：换「此刻占着原来那两个槽位的容器」，后 30 帧跨变体一致；
  与原版规则 4 条不重合，见上。
- **截断 rollout**：Video 只 solve static、Button 只按两个按钮；这两段 `failure_func` 均为
  `None`，不存在失败条件，19/19 零重试。
- **cube 颜色不进画面**：clip 起点在容器落回原位之后，第 64 步起 cube 更被藏走——全程遮挡。
- **拓扑类别按槽位角色定义，不按距离**（Button 的跨列距离可比同列短）；最近邻子集里
  `cross_diagonal` 恒空、Button 侧恒 `cross_aligned`，`topo_class` 已降级为协变量。
- **质量字段退化为回归守卫**：本轮 `min_clearance` 全 ≥0.0800、`bystander_net_max` 全 0、
  `disturbed_bins` 全空——一旦不再如此，说明几何或口径变了。
- **证据强度如实记录**：同源仅 2~3 条，判据 3/4/5/7 的比较从 15/源 降到 1~3/源（全局 14 次）。

## 下游使用提示

merged h5 满足 MotionJEPA `build_data_raw_from_h5` 的密集编号断言，整段 110 帧恰构成
scope 段（Video 全 demo、Button 全 exec 且末帧 `is_completed=True`）。chunk 标签与
`swap_labels_v7.json` 同构但仅 5 chunk/条（95 条、76 正）——真正有信息量的是
`clip_events.json` 的 clip 级事件标签。取子集：

1. 类别不均衡（8/7/2/2）是约束的结构性后果，不做重采样，需平衡自行按源分层；
2. 要动作无泄露：筛 `action_dev_max == 0`（15/19），勿用旧口径 `action_group`；
3. 要整条 clip 原版可达：筛 `later_windows_follow_native_nn`（15/19）；只看事件则 19 条全可用。
