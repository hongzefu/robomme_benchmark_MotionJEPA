# 新值规格的跑前分布：怎么生成、怎么看图

> 数据：`artifacts/injection/20260910-new-values-04/specs/<任务>/<难度>.json`，11 组 × 100 条 = 1100 条冻结规格，生成 seed `20260909`，`VideoRepick hard` 排除。
> 判定（`check_result.json`）：`SPEC_SCOPE=PASS specs=1100`、`COVERAGE_QUOTA=PASS batches=10 quota_gaps=0`、`STATIC_GEOMETRY=PASS rejected=0`、`COLLISION_SWEEP=PASS specs=500 rejected=0 min_g_m=0.00042638`、`SPEC_REPRODUCIBLE=PASS differences=0`。
> 本目录只新增只读出图脚本，不改 `tests/_shared/*`、不改 `src/robomme`、不写原 `plots/`；图只做**跑前**，PNG 不入库（`artifacts/` 被 gitignore）。
>
> 出图：`uv run python scripts/injection-before-2d/plot_injection_before_2d.py --run-id 20260910-new-values-04`（成功打 `PLOT2D_BEFORE=PASS groups=11 files=67`）；
> 核对本文档链接与产物：`uv run python scripts/injection-before-2d/check_doc_links.py`。

## 一、分布是怎么生成的

![图 D 机制](../../artifacts/injection/20260910-new-values-04/plots-2d/before/_mechanism.png)

**随机流**：每个随机量各自一条流，`derive_rng(20260909, 任务, 难度, 字段标识)` 把标识串做 SHA-256 取前 8 字节当子 seed（`tests/_shared/injection_sampling.py::derive_rng`），与进程、并行度、字典顺序无关，所以 `plan` 跑两遍 1100 条散列全同（`SPEC_REPRODUCIBLE`）。

一条规格的字段按性质分三类，各用一种办法铺满 100 条：

| 类 | 办法（锚点） | 保证 | 图 D 面板 |
|---|---|---|---|
| 能独立选的离散量（`dynamic`、布局型、次数、起点、颜色排列…） | `quota_series`：k 类各 `floor/ceil(100/k)` 条，再按 `floor(n·(t+1)/10) − floor(n·t/10)` 摊到 10 批，批内打乱 | 全局计数差 ≤ 1（`COVERAGE_QUOTA` 验的就是这一项）；每批按比例只对两类 50/50 严格成立，见下方 ⚠ | ③ |
| 连续量（位置、偏移、角度） | `stratify`：区间切 10 粗箱 × 10 细层；第 t 批从每个粗箱取一个细层点，每个变量各用独立排列 | 无几何拒绝时 10 箱各 10 条、每批覆盖全部 10 箱；各坐标不落在同一对角线 | ①② |
| 受几何／动作耦合的量（路线边、交换对、目标色池、藏物映射） | `balanced_choice`：只在**当前合法候选**里挑用得最少的，平局随机 | 只报实际频数与未覆盖组合，不声称严格均匀 | ④ |

⚠ **`quota_series` 的「每批按比例」在三类及以上并不严格成立**（本轮出图时发现，代码未改、规格已冻结，如实记录）：各类别按 `floor` 公式分到 10 个批桶时，桶大小是 9～11 条不等（34/33/33 时第 0 批 9 条、第 3 批 11 条），串接成 100 条后批边界与 episode `10t～10t+9` 错位，例如 `BinFill/easy` 的 `spawn_total` 第 4 批是 4/5/6 = 5/3/2（图 D ③ 已按实测标注）。两类 50/50 的字段（`dynamic`、`layout_type`、`n_swaps`）每批恰 5/5 不受影响。对实跑范围 ep0～29 的实际影响：独立类别的 30 条计数差多数为 0，最大 3（`BinFill/hard` 的 `put_in_total`）；逐组数字：BinFill easy `put_in_total` 2；medium `initialize_color_order` 2、`spawn_total` 2；hard `initialize_color_order` 2、`spawn_total` 2、`put_in_total` 3；RouteStick hard `L` 1；VideoUnmaskSwap easy `selected` 2、medium `selected`/`color_order` 各 2、hard `color_order` 2；VideoRepick easy `num_repeats`/`target` 各 2、medium `target` 2；其余全部为 0。全局 100 条的计数差 ≤ 1 不受影响。修法（待批，不在本轮）：把每个类别按批摊时先保证每批桶恰 10 条，再在桶内配置各类别。

**几何／碰撞拒绝后的重抽**（不改配额、不放宽阈值、不减物体）：

- `BinFill` 方块：第 0 块的首次尝试用本条的分层点（这一次计入连续量配额），其余块粗箱轮转散开；候选与按钮／孔板／已放方块（扩 0.02 间隙）相交即照原 `spawn_random_cube` 在**整个区域**重抽，最多 256 次。实测候选／几何拒绝：easy 1136/637、medium 2600/1701、hard 4423/3324。
- 两个视频任务：初态 + 每段交换路径过真实碰撞盒的连续检查（接触即拒，容限 1e-6 m）；被拒后 θ 与每个偏移、朝向都在**同一粗箱**内重抽。实测候选／接触拒绝／单条最多用到第几个候选：`VideoUnmaskSwap` easy 104/4/3、medium 107/7/3、hard 109/9/3；`VideoRepick` easy 191/2/11（另 89 次方块间距或按钮避让拒绝）、medium 239/7/33（另 132 次）。
- `RouteStick` 无几何拒绝（候选 0）。

## 二、四个任务各随机了什么（事件清单）

「分配」列即第一节的三种办法；「推出」表示由前面的随机量确定性算出、本身不再随机。事件都能在图 B 的计数面板与图 C 的每格文字里逐条查到。

**BinFill**（`_binfill_group`）

| 事件 | 取值域 | 分配 |
|---|---|---|
| `dynamic` | True / False | 配额 50/50 |
| `colors_present` | 从红蓝绿取 1／2／3 种（按难度） | 配额 |
| `put_in_color` 目标色种数 → `target_pool` | 场上颜色的子集 | 种数配额；子集在合法候选内平衡 |
| `spawn_total`、`put_in_total` | easy 4～6 / 1～3，medium 8～10 / 2～4，hard 10～12 / 3～5 | 配额 34/33/33 |
| `initialize_color_order` | 蓝红绿 6 种排列 | 配额 |
| `target_count[颜色]`、`spawn_count[颜色]` | 投入数逐个随机分给目标色（允许 0）；生成数每色至少 max(目标,1)，余量随机摊 | `rng_ep` 逐条随机（耦合，只报频数） |
| 方块生成顺序 | (颜色, 序号) 的排列 | `rng_ep.permutation`（等价源码 `randperm`） |
| `button_xy` | x∈[-0.25,-0.15] y∈[-0.2,0.2] | 分层 |
| `board.xy`、`board.yaw_deg` | x∈[-0.05,0.15] y∈[-0.2,0.2]，yaw∈[-20°,20°] | 分层 |
| `cubes[i].xy / yaw_rad` | x∈[-0.28,0.08] y∈[-0.23,0.23]，yaw 0～2π | 第 0 块分层；其余粗箱轮转；被拒整域重抽 |
| `actions`（抓哪块） | 按 `initialize_color_order` 遍历，每色取生成列表最前 `target_count` 块 | 推出 |

**RouteStick**（`_routestick_group`）

| 事件 | 取值域 | 分配 |
|---|---|---|
| `L` 段数 | easy 2～3，medium 4～5，hard 4～7 | 配额 |
| 起点 `nodes[0]` | 0/2/4/6/8 | 配额各 20 |
| `rotation_deg` 整排旋转 | [-30°, 30°]，绕世界原点 | 分层 |
| 每段去哪 `edge` | 线性邻接 ±1；不许回退时剔除上一步，端点被迫掉头 | 合法候选内平衡 |
| 每段绕行 `directions` | clockwise / counterclockwise | 合法候选内平衡 |
| `obstacle_rgb[4]` | 4 根障碍柱各一个随机 RGB | `rng_ep` 随机（只影响观感） |
| 9 个格点位置 | 由 `rotation_deg` 唯一确定 | 推出 |

**VideoUnmaskSwap**（`_unmask_group`）

| 事件 | 取值域 | 分配 |
|---|---|---|
| `n_swaps`、`n_picks` | easy 1～2 / 1～2，medium 1～2 / 1，hard 2～3 / 2 | 配额 |
| `layout_type` | easy 三角／直线，medium／hard 四点 | 配额（四点固定） |
| `selected` 藏物容器排序 | 前三个容器的 6 种排列 | 配额 |
| `color_order` | 红绿蓝 6 种排列 | 配额 |
| 前两个发起者 | 3 取 2 的 6 种有序对（原代码把藏物序号当生成序号用，照抄） | 配额 |
| 第三个发起者 | 其余生成序号 | 合法候选内平衡 |
| `theta_rad` 整组旋转 | **[0, 180] 弧度**（原单位，不是度；图里另给 mod 2π） | 分层；被拒同粗箱重抽 |
| `bins[i].xy`、`yaw_deg` | 锚点旋转后各偏移 ≤ 0.0425，yaw 0～90° | 分层；被拒同粗箱重抽 |
| `hidden`、`empty`、`pick_order` | 由 `selected` + `color_order` + `pickup_selected_indices=[0,1]` 算出 | 推出 |
| `swap_pairs[k].partner` | 交换开始时的水平最近邻，等距取序号小者 | 推出（执行时核验，不符即失败） |

**VideoRepick**（`_repick_group`）

| 事件 | 取值域 | 分配 |
|---|---|---|
| `n_swaps` | easy 1～2，medium 2～3 | 配额 |
| `num_repeats` | 1～3 | 配额 34/33/33 |
| `layout_type` | 三角／直线 | 配额 |
| `color` | 红／蓝／绿（三块同色） | 配额 |
| `target` | 三块之一 | 配额 |
| 后续发起者顺序 `tail` | 另外两块的 2 种排列 | 配额 |
| `theta_rad`、`button_xy` | [0,180] 弧度；x∈[-0.25,-0.15] y∈[-0.05,0.05] | 分层 |
| `cubes[i].xy`、`yaw_rad` | 锚点旋转后各偏移 ≤ 0.05，yaw 0～2π | 分层；方块间距 < 0.02 或压按钮、或碰撞拒绝后同粗箱重抽 |
| `swap_pairs[k].partner` | 同上最近邻 | 推出 |

## 三、图怎么看

- **图 A 初始位置叠加**：一张图叠 100 条，按对象角色分面（按钮／孔板／方块；格点；`bin_0～3`；按钮／`cube_0～2`），虚线框＝合法区，矩形＝真实尺寸与朝向，实心＝实跑 ep0～29、半透明＝ep30～99；右下热图每行一个连续量、每格是落入该粗箱的条数，全 10 即 `COVERAGE_QUOTA` 通过；视频任务另给 θ 原始弧度分箱与 mod 2π 玫瑰图。
- **图 B 随机事件 2D 图**：左边把动作画进桌面坐标（BinFill 抓取箭头→孔板、RouteStick 按 L 分面的路线、视频任务三次交换的发起者→搭档箭头），右边一列面板是每个离散事件的计数条，标题给类数与计数差。
- **图 C 逐条记录卡**：4 页 × 25 条，每格是该条的俯视布局（编号、朝向、箭头、目标标记），格下文字逐项列出这条 episode 的全部随机事件与位姿数值；绿框＝实跑范围。

| 组 | A | B | C（4 页） |
|---|---|---|---|
| BinFill/easy | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/easy/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/easy/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/easy/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/easy/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/easy/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/easy/C_episodes_p4.png) |
| BinFill/medium | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/medium/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/medium/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/medium/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/medium/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/medium/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/medium/C_episodes_p4.png) |
| BinFill/hard | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/hard/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/hard/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/hard/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/hard/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/hard/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/BinFill/hard/C_episodes_p4.png) |
| RouteStick/easy | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/easy/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/easy/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/easy/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/easy/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/easy/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/easy/C_episodes_p4.png) |
| RouteStick/medium | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/medium/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/medium/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/medium/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/medium/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/medium/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/medium/C_episodes_p4.png) |
| RouteStick/hard | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/hard/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/hard/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/hard/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/hard/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/hard/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/RouteStick/hard/C_episodes_p4.png) |
| VideoUnmaskSwap/easy | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/easy/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/easy/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/easy/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/easy/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/easy/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/easy/C_episodes_p4.png) |
| VideoUnmaskSwap/medium | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/medium/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/medium/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/medium/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/medium/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/medium/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/medium/C_episodes_p4.png) |
| VideoUnmaskSwap/hard | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/hard/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/hard/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/hard/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/hard/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/hard/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/hard/C_episodes_p4.png) |
| VideoRepick/easy | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/easy/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/easy/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/easy/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/easy/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/easy/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/easy/C_episodes_p4.png) |
| VideoRepick/medium | [A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/medium/A_positions.png) | [B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/medium/B_events.png) | [1](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/medium/C_episodes_p1.png) [2](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/medium/C_episodes_p2.png) [3](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/medium/C_episodes_p3.png) [4](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoRepick/medium/C_episodes_p4.png) |

示例（VideoUnmaskSwap/medium 的图 A 与图 B）：

![A](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/medium/A_positions.png)
![B](../../artifacts/injection/20260910-new-values-04/plots-2d/before/VideoUnmaskSwap/medium/B_events.png)

⚠ 均匀性的承诺范围：只对「采样输入」（每 episode 的分层点、独立类别配额）承诺；`BinFill` 每局方块数不同、被拒后整域重抽，全部对象的实际位置只报频数；耦合量只报实际频数与未覆盖组合。验收看 `check` 的计数表，图用于目视。
