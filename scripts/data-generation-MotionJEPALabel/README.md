# data-generation-MotionJEPALabel — 单事件 swap clip 数据集

对 VideoUnmaskSwap / ButtonUnmaskSwap 的 train **ep91/95/98/99**，只保留**一个事件**——
**第一次 swap**：穷举它的 6 种槽位对，其余全部钉死，每条产出一段 **110 帧 clip**
（env step `[34,144)`，即第一次 swap 窗口 `[64,114)` 前后各 30 帧），共 **48 条**。
细节与全部实测记录见 [CLAUDE.md](CLAUDE.md)。

**宗旨：除了 bin 的初始位置和第一次 swap 的排列组合，其他全部保持一致。**

## 结论速览（2026-08-18 全量实测）

| 项 | 结果 |
| --- | --- |
| 生成 | **48/48 成功**，59.5 s（48.4 ep/min），**零重试、零闸门失败** |
| ★ 机器人动作恒定 | Video **逐位相同（严格 0.0）**；Button 有已知泄露，见下 |
| 事件前 30 帧 | `bins_pos` 跨同源变体**逐位相同**（0.0） |
| 事件后 30 帧 | clip 末帧位置集合跨变体最大差 **1.19e-6**（窗口 ≥2 按槽位固定生效） |
| 控制跑 ↔ 官方数据 | 8/8 源 joint_action 全程 ≤2.6e-18，**clip 区间严格 0.0** |
| 类别均衡 | 三个拓扑类**各 16 条**（剔除 3-bin 源换来的一致性） |
| 标签规则回归 | 对官方 ep90-99 复算，与 v7 人工资产 **319/319 全对** |
| 接触检测 | 机械臂 ↔ 容器 **0/48**；容器互撞 20/48（全在事件窗口内） |
| 单测 | 39 passed |
| 体量 | merged h5 共 **3.28 GiB**（每 env 1.64 GiB） |

## 接触检测（物理引擎实测）

用 sapien `scene.get_contacts()` 逐帧扫全场接触，按三类统计（冲量 > 1e-9 才算「真的撞上」，
因为 PhysX 会把贴得很近但没使上力的物体也配成接触对）：

| 接触类型 | 结果 | 含义 |
| --- | --- | --- |
| **机械臂 ↔ 容器** | **0/48 条** | 机器人**从未**被 swap 中的容器碰到（验收判据 11） |
| **容器 ↔ 容器** | **20/48 条**，全部落在第一次 swap 窗口内 | clip 内实际发生的物理接触 |
| 机械臂 ↔ 按钮 | Button 每条 17 帧 / Video 0 帧 | 任务本身的接触，对照基线 |

容器互撞与拓扑类别强相关：**`cross_aligned`（跨列同侧）0/16 从不撞**、
`same_column` 7/16、`cross_diagonal`（对角）13/16 —— 对角路径最长、最容易穿过别的容器。

图：`diagrams/contact_overview.png`（谁撞了、多重、涉及哪些容器对）与
`diagrams/contact_timeline.png`（接触落在 clip 的哪些帧）。

## ⚠ 已知问题：ButtonUnmaskSwap 的动作通道泄露

Button 侧 clip 全程 `joint_action` 跨同源变体最大差 **1.6e-1 rad（≈9°）**；Video 侧严格 0.0。

**根因（实测定位，注意不是机械臂被碰）**：机械臂从未接触容器（上表 0/48）。真正的链条是
**交换中的两个容器互撞** → 改变 PhysX 的接触求解规模与顺序 → 机械臂-按钮的接触力数值解
发生变化 → 关节角偏离 → 后续规划以偏离的关节角为起点而分叉。ep95/var2 逐帧实证：
env 70 起 `bin_0↔bin_3` 持续接触 → env 79 `button_cap↔panda_finger` 冲量出现差异、
关节角从严格 0.0 突跳到 4.7e-5 并指数增长 → env 88 时 `solve_button` 的第 2/3 段规划分叉。
Video 不受影响：demo 段 `solve_hold_obj` 开环发同一 qpos、**不做任何运动规划**。

零 src 改动无法消除。**处置（用户拍板）：保留 48 条并逐条量化。** 标签里两个可过滤字段：

- `action_group`：同源内按 `joint_action` **逐位相同**划分的等价组 id；
- `action_dev_max`：与同源其他变体的 `joint_action` 最大绝对差（rad）。

下游**取同一 `action_group` 即得动作完全无泄露的子集**。Video 侧 4 个源全部只有 1 组
（24/24 条 `action_dev_max == 0`）；Button 侧 4 个源各 2 组。

## 产物（`outputs/event1/`，已 gitignore）

```
record_dataset_{Task}.h5              官方格式，episode 密集 0..23，每条恰 110 帧；
                                      每 timestep 内嵌 swap_gt/（是否在 swap、哪对槽位/
                                      哪对 bin、进度、全部 bin 与 cube 逐帧位置、env_step），
                                      setup/swap_gt/ 存事件标签与槽位几何，
                                      setup/meta/ 存颜色等纯 metadata（不进标签）
record_dataset_{Task}_metadata.json   seed 字段 = variant_seed
episode_map_{Task}.json               dense ↔ 源ep/变体号/seed/槽位序列/事件标签/
                                      几何/质量指标 的完整映射
clip_events.json                      ★ 主标签：clip 级事件（每条 clip 一个事件）
swap_labels_clip.json                 chunk 级二值，与 MotionJEPA v7 同 schema
swap_events_clip.json                 chunk 级富标签
verification_report.{json,md}         十一条判据的验收报告
diagrams/{Task}_ep{N}_clips.png       每源一张、每变体一子图的 2D 简图
                                      （红框 = 检测到容器互撞）
diagrams/contact_overview.png         48 条 clip 的接触矩阵
diagrams/contact_timeline.png         接触发生在 clip 哪些帧的时间轴
original_index.json                   Phase 0 控制跑的原始槽位序列与布局基线（复现所需）
logs/                                 各阶段运行日志
traces/ videos/                       clip 区间位姿 npz 与截断 rollout 录像
```

## 关键口径（详见 CLAUDE.md）

- **源三重筛选**：4-bin（剔 easy）→ k≥2 → 两 env 共同源号 ⇒ 恒为 `{91,95,98,99}`，每源 6 条。
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
- **数据质量**：对角/远距交换会擦过被锁定的旁观 bin —— 14/48 条 `min_clearance < 0.055 m`
  （最小 0.0045）。这是环境原行为，不修改，逐条量化在 `min_clearance` /
  `bystander_net_max` / `disturbed_bins`。

## 复现命令

```bash
uv run python -m pytest tests/lightweight/test_swap_clip_plan.py -q
```

```bash
uv run python scripts/data-generation-MotionJEPALabel/probe_original.py --gpus 0,1 --workers 8
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
uv run python scripts/data-generation-MotionJEPALabel/verify_clips.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --phase0-index scripts/data-generation-MotionJEPALabel/outputs/event1/original_index.json
```

```bash
uv run python scripts/data-generation-MotionJEPALabel/draw_clip_diagrams.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
```

MotionJEPA 侧适配提示：merged h5 已满足其 `build_data_raw_from_h5` 的「episode 0-based
密集连续」断言，且**整段 110 帧 clip 恰好构成 scope 段**（Video 全 demo、Button 全 exec
且末帧 `is_completed=True`）。chunk 标签主键与 `swap_labels_v7.json` 完全同构，但
`grid_starts(110)` 只有 5 个 chunk、按 ε=0.10 规则 4 正 1 负 —— **真正有信息量的是
`clip_events.json` 里的 clip 级多类事件标签**。
