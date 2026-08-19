# data-generation-MotionJEPALabel — 单事件 swap clip 数据集

对 VideoUnmaskSwap / ButtonUnmaskSwap 的 train **ep91/95/98/99**，只保留**一个事件**——
**第一次 swap**：枚举它的**最近邻可达槽位对**（每源 2~3 个），其余全部钉死，每条产出一段
**110 帧 clip**（env step `[34,144)`，即第一次 swap 窗口 `[64,114)` 前后各 30 帧），
共 **19 条**。细节与全部实测记录见 [CLAUDE.md](CLAUDE.md)。

**宗旨：除了 bin 的初始位置和第一次 swap 的排列组合，其他全部保持一致。**

**★ 最近邻约束（2026-08-19 重构，48 条 → 19 条）**：原版 env 的 `swap_pair{k}_idx2` 是
进入窗口首帧时按**严格最近邻**回填的，所以旧口径 `C(4,2)=6` 全枚举里有 **29/48 条在原版
数据中结构上永不可能出现**（对角对从来不是任何 bin 的最近邻）。本轮放宽第一主角 `idx1`
为任意 bin，但 `idx2` 只能取它的严格最近邻 ⇒ **每条 clip 都落在原版可达空间内**。
约束只作用于第一次 swap；窗口 ≥2 仍按槽位固定，后 30 帧跨变体一致。

## 结论速览（2026-08-19 全量实测）

| 项 | 结果 |
| --- | --- |
| 生成 | **19/19 成功**，38.2 s（29.9 ep/min），**零重试、零闸门失败** |
| ★ 最近邻不变量 | 19/19 条事件对满足；原版 `idx2 == NN(idx1)` **有方向命中 8/8 源** |
| ★ 机器人动作恒定 | Video **逐位相同（严格 0.0）**；Button 有已知泄露，见下 |
| 事件前 30 帧 | `bins_pos` 跨同源变体**逐位相同**（0.0，14 次比较） |
| 事件后 30 帧 | clip 末帧位置集合跨变体最大差 **1.01e-6**（窗口 ≥2 按槽位固定生效） |
| 控制跑 ↔ 官方数据 | 8/8 源 joint_action 全程 ≤2.6e-17，**clip 区间严格 0.0** |
| 主标签分布 | `event_slots` 四类 **03:8 / 12:7 / 01:2 / 23:2**（不均衡，不做重采样） |
| 标签规则回归 | 对官方 ep90-99 复算，与 v7 人工资产 **319/319 全对** |
| 接触检测 | 机械臂 ↔ 容器 **0/19**；容器互撞 **1/19** |
| 验收 | **十二条判据全过** + 2 条告警 |
| 单测 | 66 passed, 1 skipped |
| 体量 | merged h5 共 **1.30 GiB**（Video 0.75 + Button 0.55） |

## 接触检测（物理引擎实测）

用 sapien `scene.get_contacts()` 逐帧扫全场接触，按三类统计（冲量 > 1e-9 才算「真的撞上」，
因为 PhysX 会把贴得很近但没使上力的物体也配成接触对）：

| 接触类型 | 结果 | 含义 |
| --- | --- | --- |
| **机械臂 ↔ 容器** | **0/19 条** | 机器人**从未**被 swap 中的容器碰到（验收判据 11） |
| **容器 ↔ 容器** | **1/19 条**（Video ep99/var5，1 帧、冲量 0.0012） | clip 内实际发生的物理接触 |
| 机械臂 ↔ 按钮 | Button 每条 17 帧 / Video 0 帧 | 任务本身的接触，对照基线 |

互撞几乎消失是最近邻约束的直接后果：**最近邻对总是短程对、路径不穿过第三个容器**。
全枚举版的 20/48 主要来自被删掉的对角/长距对（当时 `cross_diagonal` 13/16 会撞、
`cross_aligned` 0/16 从不撞）。这几个接触字段因此退化为近似常量，
**不再具备下游分层能力，价值转为回归守卫**（互撞条数明显上升 = 口径或几何变了）。

图：`diagrams/contact_overview.png`（谁撞了、多重、涉及哪些容器对）与
`diagrams/contact_timeline.png`（接触落在 clip 的哪些帧）。

## ⚠ 已知问题：ButtonUnmaskSwap 的动作通道泄露

Button 侧 clip 全程 `joint_action` 跨同源变体最大差 **3.2e-2 rad**；Video 侧严格 0.0。
（全枚举版是 1.6e-1 rad —— 最近邻约束删掉了互撞最剧烈的对角/长距对，量级随之下降。）

**根因（实测定位，注意不是机械臂被碰）**：机械臂从未接触容器（上表 0/19）。真正的链条是
**交换中的两个容器互撞** → 改变 PhysX 的接触求解规模与顺序 → 机械臂-按钮的接触力数值解
发生变化 → 关节角偏离 → 后续规划以偏离的关节角为起点而分叉。ep95/var2 逐帧实证：
env 70 起 `bin_0↔bin_3` 持续接触 → env 79 `button_cap↔panda_finger` 冲量出现差异、
关节角从严格 0.0 突跳到 4.7e-5 并指数增长 → env 88 时 `solve_button` 的第 2/3 段规划分叉。
Video 不受影响：demo 段 `solve_hold_obj` 开环发同一 qpos、**不做任何运动规划**。

零 src 改动无法消除。**处置（用户拍板）：全部保留并逐条量化。** 标签里三个可过滤字段：

- `action_dev_max`：与同源其他变体的 `joint_action` 最大绝对差（rad）；
- `action_group`：同源内按 `joint_action` **逐位相同**划分的等价组 id；
- `action_group_identifies_label`：该源等价组数 == 变体数 ⇒ 关节角可完全反推标签。

⚠⚠ **最近邻约束把同源变体压到 2~3 条之后，旧口径「取同一 `action_group` 即得无泄露
子集」已名存实亡** —— `ButtonUnmaskSwap/ep91` 与 `ep99` 各只有 2 条且分成 2 组，
「同一组」只剩 1 条，等于关节角 100% 反推标签（验收报告的告警段会列名）。
**下游一律用 `action_dev_max == 0` 筛选**，本轮得 **15/19 条**：Video 全部 11 条
+ Button ep95/ep98 各 2 条。

## 产物（`outputs/event1/`，已 gitignore）

```
record_dataset_{Task}.h5              官方格式，episode 密集 0..N-1（Video 0..10、
                                      Button 0..7），每条恰 110 帧；
                                      每 timestep 内嵌 swap_gt/（是否在 swap、哪对槽位/
                                      哪对 bin、进度、全部 bin 与 cube 逐帧位置、env_step），
                                      setup/swap_gt/ 存事件标签与槽位几何，
                                      setup/meta/ 存颜色等纯 metadata（不进标签）
record_dataset_{Task}_metadata.json   seed 字段 = variant_seed
episode_map_{Task}.json               dense ↔ 源ep/变体号/seed/槽位序列/事件标签/
                                      几何/质量指标 的完整映射
clip_events.json                      ★ 主标签：clip 级事件，主轴 event_slots；
                                      meta 里带 constraint（最近邻规则与死代码警告）、
                                      per_source_legal_pairs、class_counts、
                                      action_leak_sources
swap_labels_clip.json                 chunk 级二值，与 MotionJEPA v7 同 schema
swap_events_clip.json                 chunk 级富标签
verification_report.{json,md}         十二条判据的验收报告（含告警段）
diagrams/{Task}_ep{N}_clips.png       每源一张、每变体一子图的 2D 简图
                                      （红框 = 检测到容器互撞）
diagrams/contact_overview.png         全部 clip 的接触矩阵（列 = var0..5，
                                      var1/var4 恒为空列 = 两个对角对进不来）
diagrams/contact_timeline.png         接触发生在 clip 哪些帧的时间轴
（Phase 0 产物在 outputs/phase0/original_index.json：原始槽位序列、布局基线、
  原版 idx1 读回、逐源最近邻合法对 —— 复现所需，不可随 event1 一起删）
logs/                                 各阶段运行日志
traces/ videos/                       clip 区间位姿 npz 与截断 rollout 录像
```

## 关键口径（详见 CLAUDE.md）

- **源三重筛选**：4-bin（剔 easy）→ k≥2 → 两 env 共同源号 ⇒ 恒为 `{91,95,98,99}`。
  每源条数由最近邻结构决定（Video 2/3/3/3、Button 全 2），共 19 条。
  ⚠ 「共同源号」不再保证两 env 条数对称（Video 11 vs Button 8）。
- **最近邻约束**：变体空间 = `{(i, NN(i))}` 去重，n=4 时恒 2~3 对。判定只依赖 reset 后的
  `slot_xy`（窗口 1 开在 env 64，容器已于 env 32 落回原位），所以 Phase 0 的几何就够，
  不需要新探针。⚠ 死代码警告：env 里的 `_compute_dynamic_swap_candidates` /
  `_select_swap_pair_from_positions`（取最近**两个**再随机）**全仓无调用点**，不是真实机制。
- **窗口 ≥2 按槽位固定**：交换的是「当前占据原始槽位对的那两个 bin」，所以后 30 帧的
  teleport 起止位置与被锁定 bin 的位置集合跨变体一致，事件被严格隔离在中间 50 帧。
- **截断 rollout**：Video 只 solve static 子目标、Button 只 solve 两个按钮，不要求任务
  成功（这两段 `failure_func` 均为 `None`，不存在失败条件）。旧链路 318 条里 85 条要
  hold 补救的时序冲突在此彻底消失。
- **cube 颜色不进画面**：clip 起点 env 34 落在容器落回原位（env 32）之后，
  env 64 起 cube 更被藏到 (10,10,10) —— 全程被遮挡，与「颜色不管」天然吻合。
- **拓扑类别按槽位角色定义，不按距离**：Video 的三档名义距离确实分明（0.15/0.20/0.25），
  但 Button 的 region4 带 seed 随机 y 偏移，实测「跨列同侧」可比「同列」还短
  （ep95：0.104 m vs 0.169 m）。`topo_class` 是生成机制的真值，
  `pair_distance` / `pair_azimuth_local` 是连续协变量，两者在 Button 上不同序。
- **数据质量**：全枚举版里对角/远距交换会擦过被锁定的旁观 bin（14/48 条
  `min_clearance < 0.055 m`，最小 0.0045）。最近邻约束删掉了这些对，本轮
  **0/19 条低净空、全体最小 0.0800 m**，`bystander_net_max` 全 0、`disturbed_bins` 全空。
  这几个字段因此退化为近似常量，作用转为回归守卫。
- **证据强度如实记录**：同源变体从 6 条降到 2~3 条，判据 3/4/5/7 的比较对数从 15/源
  降到 1~3/源（全局 14 次）。结论仍成立，但覆盖面比全枚举版窄 —— 验收报告里一律写
  「N 次比较全部通过」而不是「跨全部变体逐位相同」。

## 复现命令

```bash
uv run python -m pytest tests/lightweight/test_swap_clip_plan.py -q
```

```bash
uv run python scripts/data-generation-MotionJEPALabel/probe_original.py --gpus 0,1 --workers 8
```

```bash
uv run python scripts/data-generation-MotionJEPALabel/clip_plan.py --original-index scripts/data-generation-MotionJEPALabel/outputs/phase0/original_index.json
```

```bash
uv run python scripts/data-generation-MotionJEPALabel/make_clip_labels.py --regression
```

```bash
uv run python scripts/data-generation-MotionJEPALabel/generate_swap_clips.py --output-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --gpus 0,1 --workers 16
```

```bash
uv run python scripts/data-generation-MotionJEPALabel/merge_clip_h5.py --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --delete-source
```

```bash
uv run python scripts/data-generation-MotionJEPALabel/make_clip_labels.py --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1
```

```bash
uv run python scripts/data-generation-MotionJEPALabel/verify_clips.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
```

```bash
uv run python scripts/data-generation-MotionJEPALabel/draw_clip_diagrams.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
```

MotionJEPA 侧适配提示：merged h5 已满足其 `build_data_raw_from_h5` 的「episode 0-based
密集连续」断言，且**整段 110 帧 clip 恰好构成 scope 段**（Video 全 demo、Button 全 exec
且末帧 `is_completed=True`）。chunk 标签主键与 `swap_labels_v7.json` 完全同构，但
`grid_starts(110)` 只有 5 个 chunk、按 ε=0.10 规则 4 正 1 负（19 clip → 95 条、76 正）
—— **真正有信息量的是 `clip_events.json` 里的 clip 级多类事件标签**（主轴 `event_slots`）。

⚠ 下游取子集时注意两点：① 类别分布不均衡（8/7/2/2）是最近邻约束的结构性后果，本数据集
不做重采样；② 要动作无泄露的子集请筛 `action_dev_max == 0`（15/19 条），不要用旧口径的
`action_group`。
