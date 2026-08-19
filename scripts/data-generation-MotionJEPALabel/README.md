# data-generation-MotionJEPALabel — 单事件 swap clip 数据集

对 VideoUnmaskSwap / ButtonUnmaskSwap 的 train **ep91/95/98/99**，只保留**一个事件**——
**第一次 swap**：枚举它的**最近邻可达槽位对**（每源 2~3 个），其余全部钉死，每条产出一段
**110 帧 clip**（env step `[34,144)`，即第一次 swap 窗口 `[64,114)` 前后各 30 帧），
共 **19 条**。细节与全部实测记录见 [CLAUDE.md](CLAUDE.md)。

**宗旨：除了 bin 的初始位置和第一次 swap 的排列组合，其他全部保持一致。**

**★ 最近邻约束（2026-08-19 重构，48 条 → 19 条）**：原版环境做一次 swap 时，先定下被交换
的第一个容器，第二个容器则是**当时离它最近的那一个**（严格取最近，没有随机成分）。所以旧
口径「穷举 4 个容器里的任意两两组合共 6 种」当中，有一大半在原版数据里**结构上永远不可能
出现** —— 对角线上的那两种组合，从来不是任何容器的最近邻。本轮放宽第一个容器（可以是任意
一个），但第二个仍必须取它的最近邻，于是**每条 clip 的事件都落在原版能产生的范围内**。

约束只作用于第一次 swap，第二次及以后的 swap 仍按槽位钉死，以保证后 30 帧跨变体一致。
条数为什么恰好是 19、以及这两条口径在哪 4 条上不重合，见下面[为什么恰好是 19 条](#为什么恰好是-19-条)。

## 结论速览（2026-08-19 全量实测）

| 项 | 结果 |
| --- | --- |
| 生成 | **19/19 成功**，38.2 s（29.9 ep/min），**零重试、零闸门失败** |
| ★ 最近邻不变量 | 19/19 条事件换的都是一对最近邻；原版数据本身也逐源验过：被交换的第二个容器确实是第一个的最近邻，**8/8 源命中** |
| ★ 机器人动作恒定 | Video **逐位相同（严格 0.0）**；Button 有已知泄露，见下 |
| 事件前 30 帧 | `bins_pos` 跨同源变体**逐位相同**（0.0，14 次比较） |
| 事件后 30 帧 | clip 末帧的容器位置集合跨变体最大差 **1.01e-6**（第二次 swap 按槽位钉死的效果） |
| 控制跑 ↔ 官方数据 | 8/8 源 joint_action 全程 ≤2.6e-17，**clip 区间严格 0.0** |
| 主标签分布 | `event_slots` 四类 **03:8 / 12:7 / 01:2 / 23:2**（不均衡，不做重采样） |
| 标签规则回归 | 对官方 ep90-99 复算，与 v7 人工资产 **319/319 全对** |
| 接触检测 | 机械臂 ↔ 容器 **0/19**；容器互撞 **1/19** |
| 验收 | **十二条判据全过** + 2 条告警 |
| 单测 | 69 passed |
| 体量 | merged h5 共 **1.30 GiB**（Video 0.75 + Button 0.55） |

## 为什么恰好是 19 条

### 第一次 swap 能换哪两个，完全由容器的初始摆位决定

每个容器认一个「离它最近的邻居」，这就给出 4 个配对；去掉重复的，剩下的就是第一次 swap
的全部可能。4 个容器时**结果必然是 2 对或 3 对**：全场距离最近的那两个容器一定互认对方、
去重后只剩一对，另外两个容器各自最多再贡献一对。

判定有多稳，看「余量」——即某个容器到次近邻居的距离减去到最近邻居的距离。余量越大，
说明最近邻是谁越没有悬念。全部 8 个源里最小的余量是 0.0089 m，比容器落位的物理噪声
（约百万分之一米）高三个数量级，所以这个判定不存在模棱两可的情况。

| 源 | 能换的组合 | 条数 | 最小余量 (m) |
| --- | --- | ---: | ---: |
| VideoUnmaskSwap ep91 | 槽位 0-3、槽位 1-2 | 2 | 0.0695 |
| VideoUnmaskSwap ep95 | 槽位 0-1、0-3、1-2 | 3 | 0.0145 |
| VideoUnmaskSwap ep98 | 槽位 0-3、1-2、2-3 | 3 | **0.0089** |
| VideoUnmaskSwap ep99 | 槽位 0-1、0-3、2-3 | 3 | 0.0122 |
| ButtonUnmaskSwap ep91/95/98/99 | 均为 槽位 0-3、1-2 | 2 ×4 | 0.0551 / 0.0184 / 0.0207 / 0.0921 |

合计 **19 条**（Video 11 + Button 8）。这不是挑出来的数量，是几何算出来的。

### 第二次 swap 没有自由度，所以总数就是 19

这是「在只控制第一次 swap 的前提下，是不是只有这些」的正面回答。

原版环境里，**第二次 swap 的第一个容器在场景生成时就已经定死**（和任务目标绑在一起），
第二个容器仍然取当时的最近邻。也就是说：**第一次 swap 一旦确定，第二次 swap 随之唯一确定，
中间没有任何可选项。**

结论：无论第二次 swap 按哪种口径处理，条数都是 19，不会更多。差别只在那 4 条（见下）
第二次换的是哪一对，不在数量上。

唯一能让组合变多的做法，是把**第二次 swap 的第一个容器也放开**成任意容器 —— 那样每条
再乘 2~3 倍。但代价是后 30 帧不再跨变体一致，与「只控制第一次 swap、其余全部钉死」的
宗旨直接冲突，所以没有采用。

### 两种口径在 4 条上不重合（已逐条量化）

本链路把第二次 swap 钉死成「换原来那两个**槽位**」，而原版认的是「那个**固定的容器**」。
第一次 swap 有可能已经把那个容器挪到别的槽位上去了，于是两者分岔。

分岔发生在哪里可以精确算出来：容器交换是两两互换位置，被占用的 4 个位置始终是那 4 个，
所以「谁离谁最近」这层关系在整条 episode 里不变，直接用初始摆位就能复算。实测结果：

| 变体 | 第一次 swap 换的槽位 | 本链路第二次换的槽位 | 原版规则会换的槽位 |
| --- | --- | --- | --- |
| Video ep95 / var3 | 1-2 | 1-2 | **0-1** |
| Video ep98 / var3 | 1-2 | 1-2 | **2-3** |
| Video ep99 / var2 | 0-3 | 0-1 | **0-3** |
| Video ep99 / var5 | 2-3 | 0-1 | **0-3** |

其余 15 条完全重合。**Button 侧 8 条无一例外**，因为它的最近邻关系恰好是两两配对
（槽位 0 与 3 互为最近邻、1 与 2 互为最近邻）—— 不管第一次 swap 把容器挪到哪个槽位，
配对关系都对称，第二次换的槽位恒定。Video 侧的最近邻关系不总是配对（例如 ep99 是
「0 认 3、1 认 0、2 认 3、3 认 0」），才会出现分岔。

怎么看待这 4 条：**它们的事件本身（第一次 swap）19/19 都严格落在原版能产生的范围内**，
不一致的只是后 30 帧里露出来的第二次 swap 换了哪一对。这是「约束只作用于第一次 swap」
这个决定的直接后果，不作废数据，而是逐条量化在标签的 `later_windows_follow_native_nn`
字段里。下游若要求**整条 clip 从头到尾都是原版能产生的**，按该字段筛即可，得 **15/19 条**
（Button 8 + Video 7）。

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

## 生成链路与产物

七步，每步的产物就是下一步的输入。全链路（不含 Phase 0）约 1 分钟。

### 0. 纯函数自检（秒级，任何机器都能跑）

```bash
uv run python -m pytest tests/lightweight/test_swap_clip_plan.py -q
```

在花掉任何 GPU 时间之前先排除源筛选、槽位换算、最近邻复刻、编号公式写错。69 passed。

### 1. Phase 0 控制跑 — 拿基线（8 条完整 rollout，约 32 s）

```bash
uv run python scripts/data-generation-MotionJEPALabel/probe_original.py --gpus 0,1 --workers 8
```

不做任何注入，照原样跑完 8 个源，产出 `outputs/phase0/original_index.json`：

- **原始的 swap 序列**（容器口径与槽位口径各一份）—— 第二次及以后的 swap 钉死成什么，
  唯一来源就是这里；
- **原版被交换的第一个容器**（每个 swap 窗口一个）—— 验收用它做「原版第二个容器确实是
  第一个的最近邻」这条带方向的核对；
- **容器初始摆位**（各槽位 xy、各自的最近邻、判定余量、该源能换的组合）；
- **布局指纹**（后续每条变体都要和它逐位比对）；
- **与官方数据的红线比对**（clip 区间内 joint_action 必须严格为 0）。

⚠ **这份索引不能靠计算重来**：第二次及以后的 swap 换的是谁，是运行到那一帧才由环境按最近
邻填进去的，静态推不出来。所以它必须早于任何删除动作产生 —— 删 `outputs/event1/` 之前先
确认这份索引在别处存好了。

### 2. 计划表 — 只看不生成

```bash
uv run python scripts/data-generation-MotionJEPALabel/clip_plan.py --original-index scripts/data-generation-MotionJEPALabel/outputs/phase0/original_index.json
```

读上一步的容器摆位，打印逐源的可换组合与条数（应为逐源 2/3 条、合计 19）。
**不给 `--original-index` 时它只会打印「≤6 / ≤48」的上界并明确提示**——因为真实条数依赖
实测摆位，没有基线就算不出来，此时绝不会给出一个看着像真值的数字。

### 3. 生成 — 19 条截断 rollout（约 38 s）

```bash
uv run python scripts/data-generation-MotionJEPALabel/generate_swap_clips.py --output-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --gpus 0,1 --workers 16
```

每条变体单独建环境、reset 后注入、跑到够 clip 用为止，产出：

```
clips/*.h5              每条变体一个中间 h5（110 帧）
clips_manifest.json     逐条元数据：swap 序列、槽位几何、接触统计、质量指标
clip_results.jsonl      断点续跑账本（成功/失败/重试次数）
traces/ videos/ logs/   位姿 npz、截断 rollout 录像、运行日志
```

收尾会跑一组闸门：布局指纹与基线一致、每源恰 1 条原始变体、第二次及以后的 swap 跨变体
唯一、**每源实际换的组合恰等于该源能换的组合**。任一条不过就报错退出。

### 4. 合并 — 归成官方格式（数秒）

```bash
uv run python scripts/data-generation-MotionJEPALabel/merge_clip_h5.py --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1 --delete-source
```

```
record_dataset_{Task}.h5              官方格式，episode 密集重编号（Video 0-10、Button 0-7）
record_dataset_{Task}_metadata.json   seed 字段 = 该变体的专属 seed
episode_map_{Task}.json               新旧编号 ↔ 源 episode / 变体 / 标签 / 几何 的完整映射
```

⚠ 带 `--delete-source`，中间 h5 会被删掉。所以**第 3、4、5 步必须同一批跑完** ——
源没了就无法单独重跑合并。

### 5. 标签（数秒）

```bash
uv run python scripts/data-generation-MotionJEPALabel/make_clip_labels.py --input-dir scripts/data-generation-MotionJEPALabel/outputs/event1
```

```
clip_events.json         ★ 主标签：每条 clip 一个事件；主轴是「换了哪两个槽位」，
                         附协变量、逐源可换组合、类别分布、动作泄露源清单、
                         以及第二次 swap 与原版规则的对账结果
swap_labels_clip.json    chunk 级二值，与 MotionJEPA v7 同 schema
swap_events_clip.json    chunk 级富标签
```

标签规则本身另有一条独立回归（只读官方数据，不碰产物），改过判正规则就必须先跑通：

```bash
uv run python scripts/data-generation-MotionJEPALabel/make_clip_labels.py --regression
```

对官方 ep90-99 复算并与人工标注逐条比对，应为 319/319 全对。

### 6. 验收（数秒）

```bash
uv run python scripts/data-generation-MotionJEPALabel/verify_clips.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
```

同时读 Phase 0 基线、merged h5、标签三方对账，产出
`verification_report.{json,md}` —— 十二条判据加一个告警段。退出码非 0 即有判据未过。

### 7. 出图（数秒）

```bash
uv run python scripts/data-generation-MotionJEPALabel/draw_clip_diagrams.py --gen-dir scripts/data-generation-MotionJEPALabel/outputs/event1
```

```
diagrams/{Task}_ep{N}_clips.png   每源一张：6 个格子按「换了哪两个槽位」排布，
                                  实际存在的变体画简图，进不来的组合留空并标注原因
diagrams/contact_overview.png     全部 clip 的接触矩阵（对角那两列恒为空）
diagrams/contact_timeline.png     接触发生在 clip 哪些帧的时间轴
```

### h5 里带了什么

每一帧内嵌：是否正在 swap、换的是哪两个槽位/哪两个容器、进度、全部容器与 cube 的逐帧
位置、对应的原始步号、三类接触的计数与冲量。
每条 clip 的 setup 里另存事件标签、槽位几何、最近邻自证信息与质量指标；颜色等纯 metadata
单独放在 `setup/meta/`，**不进标签**。

### 磁盘

`outputs/event1/` 约 1.4 GiB（其中 merged h5 1.30 GiB），`outputs/phase0/` 约 2.1 GiB
（含控制跑的完整 h5 与录像，索引产出后即可删，但索引本身要留）。两者都已 gitignore。

## 关键口径（详见 CLAUDE.md）

- **源三重筛选**：4-bin（剔 easy）→ k≥2 → 两 env 共同源号 ⇒ 恒为 `{91,95,98,99}`。
  每源条数由最近邻结构决定（Video 2/3/3/3、Button 全 2），共 19 条。
  ⚠ 「共同源号」不再保证两 env 条数对称（Video 11 vs Button 8）。
- **最近邻约束**：可选的组合就是「每个容器配上离它最近的邻居」去重后的结果，4 个容器时
  恒为 2~3 对。判定只看容器的初始摆位 —— 第一次 swap 发生在第 64 步，而容器早在第 32 步就
  已落回原位，所以 Phase 0 拿到的摆位就够用，不需要额外探针。
  ⚠ 死代码警告：环境源码里另有 `_compute_dynamic_swap_candidates` /
  `_select_swap_pair_from_positions`（取最近**两个**再随机挑一个），看着像真机制，但
  **全仓没有任何调用点**，按它复算会得到每源 4~5 对，与实际不符。
- **第二次及以后的 swap 按槽位钉死**：换的是「此刻占据着原来那两个槽位的两个容器」，
  于是后 30 帧里搬运的起止位置、以及被锁住不动的容器的位置集合，跨变体完全一致 ——
  事件被严格隔离在中间 50 帧。这与原版规则在 4 条上不重合，见上文。
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

## 下游使用提示

**MotionJEPA 侧适配**：merged h5 已满足其 `build_data_raw_from_h5` 的「episode 0-based
密集连续」断言，且**整段 110 帧 clip 恰好构成 scope 段**（Video 全 demo、Button 全 exec
且末帧 `is_completed=True`）。chunk 标签主键与 `swap_labels_v7.json` 完全同构，但
`grid_starts(110)` 只有 5 个 chunk、按 ε=0.10 规则 4 正 1 负（19 clip → 95 条、76 正）
—— **真正有信息量的是 `clip_events.json` 里的 clip 级多类事件标签**（主轴 `event_slots`）。

**取子集时注意三点**：

1. 类别分布不均衡（8/7/2/2）是最近邻约束的结构性后果，本数据集**不做重采样**，需要平衡请
   自行处理（标签 meta 里有逐源的可换组合，可按源分层）；
2. 要**动作无泄露**的子集请筛 `action_dev_max == 0`（15/19 条），**不要**用旧口径的
   `action_group` —— 同源只有 2 条时那会退化成 1 条；
3. 要**整条 clip 从头到尾都是原版能产生的**，请筛 `later_windows_follow_native_nn`
   （15/19 条）。只关心事件本身是否原版可达的话，19 条全部可用。
