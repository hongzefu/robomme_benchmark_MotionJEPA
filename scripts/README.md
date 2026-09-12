# scripts/ 说明（newtask-v2）

本目录是数据生成侧的全部入口。

`BinFill` / `RouteStick` / `VideoUnmaskSwap` / `VideoRepick` 这四个任务**原来就在用**的
位置分布与参数候选，过去散落在源码里当字面量；现在被提取成一份冻结的显式配置
[configs/newtask-v2/native_sampling.json](configs/newtask-v2/native_sampling.json)，
可以检查、可以显式传入。**取值、抽样方式与整条执行链保持原版行为不变**，这一点用逐位对拍
验证过（第二节）。

---

## 一、固定了哪些

### 1.1 十五份难度字典（四任务 × 三难度，三任务另有第四档 xhard）

| 任务 | easy | medium | hard | xhard（2026-09-11 新增） |
| --- | --- | --- | --- | --- |
| `BinFill` | `color=1`<br>`spawn_cubes=[4,6]`<br>`put_in_color=[1,1]`<br>`put_in_numbers=[1,3]` | `color=2`<br>`[8,10]`<br>`[1,2]`<br>`[2,4]` | `color=3`<br>`[10,12]`<br>`[2,3]`<br>`[3,5]` | 无 |
| `RouteStick` | `length=[2,3]`<br>`backtrack=False` | `[4,5]`<br>`False` | `[4,7]`<br>`True` | `[8,10]`<br>`True`（其余同 hard） |
| `VideoUnmaskSwap` | `bin=3`<br>`swap 1–2`<br>`pick 1–2` | `bin=4`<br>`swap 1–2`<br>`pick 1–1` | `bin=4`<br>`swap 2–3`<br>`pick 2–2` | `bin=4`<br>`swap 4–5`<br>`pick 2–2`（其余同 hard；第 4/5 次发起者循环沿用前 3 个） |
| `VideoRepick` | `cube=3`<br>`swap 1–2` | `cube=3`<br>`swap 2–3` | `swap 0–0`<br>（`cluster`/`swap` 是死字段，源码从不读它们） | `cube=3`<br>`swap 4–5`（其余同 medium；发起者循环同上） |

区间语义按来源区分：写在难度字典里的 `[min,max]` 由 `torch.randint(low, high+1)` 消费，
**含两端**；直接写在源码里的 `torch.randint(a, b)` 是半开区间，不含 `b`。

### 1.2 构造期的其它抽样常量

| 任务 | 项 | 原值 |
| --- | --- | --- |
| `BinFill` | `dynamic` | `randint(0,2)` 转 bool，是 generator 播种后的**第一次**抽样 |
| `RouteStick` | 难度兜底档 | `easy`（对应 `self.configs.get(..., self.config_easy)`） |
| `VideoRepick` | `num_repeats` | `randint(1,4)`（半开，即 1/2/3） |
| `VideoRepick` | hard 生成轮数 | `5` 轮，每轮红蓝绿各一块 = 15 块 |

### 1.3 位置输入

| 任务／对象 | 固定的项 |
| --- | --- |
| `BinFill` 按钮 | 中心 `(-0.2, 0)`、随机范围 `(0.1, 0.4)`、缩放 `1.5` |
| `BinFill` 孔板 | 基准位 `[0.15, 0, 0]`；三组偏移运算元 x `u×0.2−0.2`、y `u×0.4−0.2`、yaw `u×40−20`（度）；板边长 `0.1`、孔边长 `0.08`、厚 `0.05` |
| `BinFill` 方块 | 区域中心 `[-0.1, 0]`、半边长 `[0.2, 0.25]`、随机 yaw、`include_existing=False`、`include_goal=False` |
| `RouteStick` 布局 | 网格中心 `[-0.1, 0]`、行列间距各 `0.07`、整体旋转 `u×60−30`（度）、障碍柱半径 `0.015` / 高 `0.1` |
| `VideoUnmaskSwap` 容器 | 三组锚点（三角 / 直线 / 四点）、锚点二选一的 `randint(0,2)`、整体旋转 `(0,180)` **弧度**、区域半边长 `0.07`、容器自转 `u×90`（度） |
| `VideoRepick` 按钮 | 中心 `(-0.2, 0)`、随机范围 `(0.1, 0.1)`、缩放 `1.5` |
| `VideoRepick` easy/medium 方块 | 同上三组锚点与二选一抽样、整体旋转 `(0,180)` 弧度、区域半边长 `0.07`、随机 yaw、`include_existing=True`、`include_goal=True` |
| `VideoRepick` hard 方块 | 区域中心 `[-0.1, 0]`、半边长 `[0.2, 0.25]`、随机 yaw、两个避让开关均 `False` |

三组容器/方块锚点的实际坐标（按原顺序，不排序、不归一化、不平移）：

```text
三角  [[-0.05, -0.1], [-0.05, 0.1], [0.1, 0]]
直线  [[0, -0.15],    [0, 0.15],    [0, 0]]
四点  [[-0.05, -0.1], [-0.05, 0.1], [0.1, 0.1], [0.1, -0.1]]
```

### 1.4 按 episode 固定的对象与动作（schema 3）

配置仍通过 `load_sampling_config → EpisodeJob.sampling_config → gym.make` 传入，
由 episode 对应的 seed 在原调用点实例化；没有逐 episode 结果表。
相同任务、难度、layout、episode、attempt、配置及运行状态下，比较的是具体对象与动作。
重试增加 attempt 并改变 seed，允许产生不同结果。

| 任务 | 新增运行字段 | 固定的结果与消费位置 |
| --- | --- | --- |
| `VideoUnmaskSwap` | `parameters.VideoUnmaskSwap.object_selection`：`hidden_bin_permutation_size=3`、`hidden_bin_count_max=3`、`pickup_selected_indices=[0,1]`、`swap_seed_target_count=2` | `_load_scene` 保留原抽样顺序；抓取 `selected_bins` 的第一项或前两项，目标判定、求解、描述与 segment 同步绑定；保留交换发起对象原索引映射 |
| `VideoRepick` | `parameters.VideoRepick.object_selection`：`easy_medium_target_count=1`、`hard_target_low=0`、`swap_remaining_count=2` | easy/medium 仍用 randperm，hard 仍用 randint；抓取始终绑定同一 `target_cube_1`；交换发起顺序是目标加其余两块的随机排列，hard 无交换 |
| 两个视频任务 | 各自 `swap_selection` 的发起映射、剩余对象抽法与 `partner` 规则 | 原 step 中按交换开始时的位置选择完整对象对；XY 欧氏距离、排除自身、严格小于比较、等距取生成顺序靠前者，选中后复用 |
| `RouteStick` | `parameters.RouteStick.walk`：节点 `[0,2,4,6,8]`、随机起点、邻居偏移 `[-1,1]`、端点强制回退、`direction` | `_load_scene → generate_dynamic_walk` 生成 steps+1 个节点；每段一次 `torch.rand(1)`，小于 0.5 为顺时针；演示和执行复用节点与方向 |

新增策略、数量与索引映射只接受现行值；方向阈值是唯一开放的新增数值，须为 `[0,1]`
内有限数值。直接构造任务也做校验。交换搭档依赖交换开始时的实际位置，因此重复性检查
同时比较动作输入、状态和实际交换调用，不能只比较初始化时仍含 null 的 schedule。

schema 2 配置须用 `--extract-config` 重新导出为 schema 3；新增字段参与源码与历史 AST
检查，`_cross_check` 还确认字段确实接到原调用点。本轮以 `20260909-actions-v3`
独立重跑全部 15 格四路，五项对拍均有新证据，见第二节。

### 1.5 注入规格的取值域与分配：约定 JSON

新值注入专项（第四节）里「每个字段能取什么、怎么铺满 100 条」不再散落在生成器、补零类别表与事件表文案里，
而是一份版本化的契约 [`configs/newtask-v2/injection_contract_v1.json`](configs/newtask-v2/injection_contract_v1.json)
（= 现状口径，数值域由 `native_sampling.json` 派生）与
[`injection_contract_v2.json`](configs/newtask-v2/injection_contract_v2.json)（= v1 + BinFill 对齐 heldout 三处）。
谁定义什么：

| 文件 | 定义什么 | 谁消费 |
|---|---|---|
| `injection_contract_v*.json` | 11 组 × 每字段的事件名、取值域（`domain`／`domain_text`）、分配办法（`allocation`／`allocation_text`）、对原值的 `overrides` | `scripts/injection/specs.py::build_group`（候选分布的派生依据）、`categories.py::legal_categories`（补零）、`injection-before-2d/event_tables.py`（表格两列） |
| `native_sampling.json` | 几何常量（按钮盒尺寸、孔板边长、锚点坐标、避让间距、`region_half_size`）与结构性输入（节点表、邻接顺序），以及仿真运行时的原值 | 生成器的几何部分、`_static_problems` 的独立复核、`generate_dataset_newseed.py --sampling-config` |

契约里由几何算出的数值是**派生结果**，带 `derivation`（recipe + 依赖键），`check` 的 `CONTRACT_DERIVED`
每次拿 `native_sampling.json` 回算；想改这类数字要改 `native_sampling.json`，或登记 override。
**契约只作用于外部规格生成器（`scripts/injection/`），生产入口 `generate_dataset_newseed.py` 不读它。**
变化与用户决策见 [NEW_VALUE_CONTRACT_CHANGELOG.md](NEW_VALUE_CONTRACT_CHANGELOG.md)。

### 1.6 **没有**开放为可配的东西

物体尺寸、材质、碰撞几何、相机、速度、交换时序、失败恢复、成功阈值都属于原实现，没有动。

`cube_half_size`（= `0.02`）是个特例：它同时是四任务 `min_gap` 的实际值、容器半边长的
收缩量、方块可行域的收缩量 —— 不是纯尺寸参数。它被**冻结为派生输入记进快照**，
但**不开放为可配**。

源码里的若干旧问题（RouteStick 结尾无条件覆盖难度、创建后从未使用的局部 generator、
无调用者的死代码、`VideoRepick` 永不命中的 `region4` 分支、与实际不符的注释等）
按计划**原样保留、没有顺手修**，只在快照与计划文档里记录。

### 1.7 「固定」是怎么保证的

取值有两个落点，但**不是两套真值**：

- `configs/newtask-v2/native_sampling.json` —— 冻结快照，也是 `--sampling-config` 的输入；
- 每个任务模块顶层的 `NATIVE_SAMPLING` —— 既是**不传配置时的运行默认值**，
  也是快照的提取目标。难度字典则只在类属性 `config_easy/medium/hard` 一处。

三道闸拦住漂移：

1. **结构与类型校验** —— 字段缺失、多出未知字段、类型或数组长度不对，直接报错；
2. **来源指纹** —— 生成时核对七份源码文件的 SHA-256，改过源码就必须重新导出快照；
3. **表达形式约束** —— JSON 里只存源码里真实出现的运算元（`scale` / `subtract` /
   `base_position`），**不许**折算成 `[min,max]`：`0.15 + (u×0.2 − 0.2)` 与
   `−0.05 + u×0.2` 数学等价，但 float64 位模式不同，逐位对拍会挂。

配置值一律以 Python 标量参与运算，不要包成 `torch.tensor` —— 那会把下游的 float32 路径
提升成 float64。

初版只支持原来就存在的表达形式（区间、固定值、原抽取方式），**不支持**新增非连续候选、
权重或新拓扑。

---

## 二、对拍测试了哪些

### 2.1 四路独立运行

| 路 | 是什么 | 源码 |
| --- | --- | --- |
| **A** | 固定原版，跑两次（A1/A2）做重复性校准 | 基线提交 `94449db` 的 detached worktree |
| **B** | 新版**不传**配置 | 当前工作树 |
| **C** | 新版**显式传入**原值配置 | 当前工作树 |

逐格比较 `A1↔A2`、`A1↔B`、`A1↔C`、`B↔C` 四对。同一格固定任务、难度、episode、seed、
`attempt=0`、GPU 与全部参数，四路独立进程运行。

**比较口径：全字段、逐元素、浮点按位模式、不设容差。**

### 2.2 五项对拍

| 类别 | 比较对象 |
| --- | --- |
| ① 关键帧图像 | 首末帧、子目标边界、演示切换、完成标志变化和实际事件的正面／腕部原图，三路取并集并加前后邻帧；事件使用原 wrapper 的真实落盘编号映射，另保存 reset 返回的原始 RGB，不额外渲染 |
| ② 状态与物体事件 | 构造期与两次 `_initialize_episode` 的边界快照；每次原 step 前后的状态、actor 位姿与速度；抓取对象索引、实际交换双方及窗口、完整路线节点和演示／执行的方向绑定 |
| ③ HDF5 落盘产物 | 原始和逐格合并产物均遍历 group / dataset / attribute 全集、dtype、shape、字符串及全部元素；`obs`、`action`、`info`、`setup` 全部纳入 |
| ④ 随机流 | 每次 `torch.rand/randint/randperm` 的次序、参数、shape、dtype、源身份、抽样结果及调用前后状态；保留拒绝采样和单候选抽样的全部消费，单列 `np.random.seed` 事件 |
| ⑤ 连续 worker | 原版、默认配置、显式配置分别在同一实际 PID 内执行甲→乙→甲；逐局与独立运行比较 HDF5 和完整证据，并核验父配置、实际 worker 类配置与新环境缓存 |

### 2.3 覆盖了 15 格

| 任务 | 格 |
| --- | --- |
| `BinFill` | easy / medium / hard × `dynamic=True` / `dynamic=False`，共 6 格 |
| `RouteStick` | easy / medium / hard，3 格 |
| `VideoUnmaskSwap` | easy / medium / hard，3 格 |
| `VideoRepick` | easy / medium / hard（hard 覆盖五轮循环共 15 块），3 格 |

本轮共 60 次 fresh 生成，全部首次尝试成功，编排耗时 2479.7 秒；每路合计
8,739 个 HDF5 timestep、676 次受监测的随机调用。单格 HDF5 对象 5008–23583 个、
随机调用 11–131 次、事件 748–17014 条、逐步状态 652–1886 条。

### 2.4 结论

| 项目 | 结果 |
| --- | --- |
| HDF5 全字段 | **15 格通过，原始及合并产物各 60 对比较，差异均为 0**；合并目录按格和路径隔离 |
| 随机流 | 15 格通过；观察器版本 3 记录完整调用前后状态，计数没有截断 |
| 内部状态与事件 | 15 格通过；实际抓取对象、交换双方、路线节点与方向均一致 |
| 同一 worker 连续生成互不污染 | 三路、共 9 局通过；每路同一 PID，逐局与独立运行零差异，父配置／类配置不变，新环境缓存为空 |
| 关键帧目视 | **15 格通过，852 张图版**（837 张 HDF5 关键帧与 15 张 reset）；本轮逐图查看，最终全量出图再按帧全集、图片散列和机检结果重新绑定目视记录 |
| 其余 12 任务生成能力 | `--env all` 加配置，16/16 成功 |
| attempt 重试分支 | 三路的失败分类与第二次 seed 完全一致，重试产物 0 差异 |

另有一条独立于生成的证据：`--check-config --source-ref 94449db` 用另一套提取器，
从**改造之前的源码**里还原 66 组运算元并与快照逐项比对 —— 这是「接入过程一个原值都没改」
的自动化证明，不靠人眼比 diff。

15 格的 30 次原版运行 `rrt_fallback_count` 全为 0，即全部落在「原版逐位可复现」的
适用范围内（screw→RRT\* 回退走 mplib/OMPL，种子接口未暴露且有 1 秒墙钟预算，
触发回退的局本就不具备逐位可复现性）。

### 2.5 记录边界与既有失败

- RouteStick 三格各有 48 条高亮事件发生在原 `NO RECORD` 步，没有对应 HDF5 图像。
  三路的未落盘事件清单相同，完整状态和事件参与②；不为这些不存在的图像伪造目视结论，
  不平移或重采样配帧。所有实际规定的关键帧均已出图并查看。
- 本 15 格的三种受监测 Torch 抽样函数全部使用显式 generator；全局 Torch 调用数为零，
  全局源的前后状态记录分支另有定向测试。不能把未发生的全局调用或 C++ 规划随机性说成已实跑覆盖。
- RRT\* 回退局未触发，不能据此保证跨依赖／硬件或回退路径逐位一致。
- 轻量全量测试仍有 4 个固定原基线已存在的失败；已在 `94449db` 复核，未跳过或改判据隐藏。
  具体测试名、命令和最新结果见本轮报告。

本轮完整报告、实际对象／动作实例、逐格结果与离线证据见
[20260909-actions-v3](../docs/validation/newtask-v2/20260909-actions-v3/README.md)。
[运行索引](../docs/validation/newtask-v2/README.md) 和
[原交付清单](../docs/validation/newtask-v2/DELIVERY.md) 保留旧轮次的历史结论。

### 2.6 schema 3 原值配置的多 GPU、多 worker 校准

**五轮 80 次生成及独立离线复核已完成：75 次成功，15 个可比样本在跨卡与并行模式下的 45 对比较全部严格一致；完整 16 条校准未整体通过。**

正式编号为 `20260909-schema3-parallel-v2`。固定 `BinFill hard`、`RouteStick hard`、
`VideoUnmaskSwap hard`、`VideoRepick medium` 各 episode `0～3`，显式传入原值配置，
使用 train seed、attempt 0、`--max-attempts 1 --max-tasks-per-child 8`、线程限制和
`--affinity none`。本次比较当前实现的不同运行配置，不替代前文原版接入的 A/B/C 对拍。

| 配置 | GPU／总 worker | 生成成功 | 与参考严格比较通过／计划条数 | 执行窗口检查 | 四批总耗时 |
| --- | --- | --- | --- | --- | --- |
| S0a | GPU 0／1 | 15/16 | 建立参考 | 串行 4/4 通过 | 758.01 秒 |
| S0b | GPU 0／1 | 15/16 | 15/16 | 串行 4/4 通过 | 756.44 秒 |
| S1 | GPU 1／1 | 15/16 | 15/16 | 串行 4/4 通过 | 754.58 秒 |
| P0 | GPU 0／2 | 15/16 | 15/16 | 同卡并发 4/4 通过 | 401.13 秒 |
| P01 | GPU 0、1／4，每卡 2 个 | 15/16 | 15/16 | 四 worker 共同并发 4/4 通过 | 262.59 秒 |

唯一失败是 `BinFill hard / episode 3 / seed 4300`，五轮均为
`DatasetGenerationError: BinFill/episode_3: 环境报告失败`。该条从未移出分母，
没有换 seed 或补样本；其余 15 条的 HDF5 全字段、初态、状态事件、实际对象动作和随机流
全部逐位一致。80 次均无规划回退、无批次超时。完整 16 条参考未建立，因此 S1、P0、P01
整体校准均未通过；生成主命令和独立 `compare` 的退出码均为 1。

**双卡每卡 2 worker 的实际并发已证实。** 检查实际 GPU／PCI／PID，以及首次至最后一次
step 的单调时钟窗口；P01 四任务的四 worker 共同重叠分别为 27.734、48.155、14.041、
22.700 秒。失败条虽然没有成功 HDF5，仍独立读取其时间证据；进程导入和视频编码时间
不计入窗口。上述耗时是带观察器的本次流程测量，不外推为其他任务、硬件或并行规模的性能保证。

入口为测试侧 [parallel_calibration.py](../tests/_shared/parallel_calibration.py)，复用原生产
CLI；任务、生产调度、`native_sampling.json` 和依赖均未修改。生成实现提交为 `91bacf9`，
独立数值复核工具为 `1f98324`；图版文本格式随后单独规范，比较结果不变。来源、结果和时间图见
[实测报告](../docs/validation/newtask-v2/20260909-schema3-parallel-v2/README.md)、
[结构化结果](../docs/validation/newtask-v2/20260909-schema3-parallel-v2/parallel_result.json)。
新报告使用 `parallel_result.json`，避免与旧 A/B/C 证据包的 `result.json` 发现规则混淆。

重新生成必须使用新编号；以下命令先执行自己的观察器开关冒烟，通过后才跑五轮：

```bash
command -v uv
mkdir -p artifacts/logs
PARALLEL_RUN_ID="schema3-parallel-$(date -u +%Y%m%dT%H%M%SZ)"
tmux new-session -d -s "$PARALLEL_RUN_ID" \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m tests._shared.parallel_calibration run --run-id $PARALLEL_RUN_ID 2>&1 | tee artifacts/logs/$PARALLEL_RUN_ID.log; code=\$?; echo EXIT_CODE=\$code | tee -a artifacts/logs/$PARALLEL_RUN_ID.log; exit \$code"
```

独立复核只读取既有重产物并刷新派生报告，不生成 episode；本轮全字段复核也超过五分钟，
同样用 tmux：

```bash
command -v uv
mkdir -p artifacts/logs
PARALLEL_RECHECK_ID="schema3-compare-$(date -u +%Y%m%dT%H%M%SZ)"
tmux new-session -d -s "$PARALLEL_RECHECK_ID" \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m tests._shared.parallel_calibration compare --run-id 20260909-schema3-parallel-v2 2>&1 | tee artifacts/logs/$PARALLEL_RECHECK_ID.log; code=\$?; echo EXIT_CODE=\$code | tee -a artifacts/logs/$PARALLEL_RECHECK_ID.log; exit \$code"
```

`--smoke-only` 只做单条开关校准；单批默认超时 600 秒。完整重产物与逐批记录位于
`artifacts/parallel-calibration/20260909-schema3-parallel-v2/`；主日志和独立复核日志分别为
`artifacts/logs/20260909-schema3-parallel-v2.log`、
`artifacts/logs/20260909-schema3-parallel-v2-offline.log`。

**这只覆盖原值配置。** 新值规格、注入、1100 条分布图和 110 条新值可行性测试均未执行，
不能用本轮可比样本的一致结论替代新值校准。`VideoRepick hard` 未参与本轮。

---

## 三、几个脚本入口分别做什么用

| 文件 | 干什么 |
| --- | --- |
| `generate_dataset_newseed.py` | **主入口**，三种模式：生成数据集 / 核对导出原值快照 / 按需合并 |
| `seed_layout.py` | seed 公式、难度循环、16 任务规范序。纯标准库，被主入口导入 |
| `dataset_replay.py` | 回放已生成的数据集（未改动） |
| `evaluation.py` | 评估示例（未改动） |
| `run_example.py` | 单环境运行示例（未改动） |

主入口的三种模式互斥，靠参数区分；命令都在仓库根目录执行。

### 3.1 生成数据集（默认模式）

```bash
# 最小例子：BinFill 一局
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/binfill-smoke \
  --env BinFill --episodes 1 --workers 1 --gpus 0 \
  --layout train --difficulty 100 --max-attempts 1

# 全量例子：16 任务 × 100 局，双卡
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/full-16x100 \
  --env all --episodes 100 --workers 20 --gpus 0,1 \
  --layout train --difficulty 211

# 显式传入原值配置（结果与不传时逐位相同，已验证）
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/binfill-explicit \
  --env BinFill --episodes 1 --workers 1 --gpus 0 --difficulty 100 \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json
```

配置只覆盖那四个任务；`--env all` 时其余 12 个任务照原默认值生成，不报错。

**常用参数**

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--output-dir` | 必填 | 输出目录，**必须在仓库内** |
| `--env` | `all` | `all` 或逗号分隔的任务名 |
| `--episodes` / `--episode-start` | `100` / `0` | 条数与起始 episode 号（接续生成用后者） |
| `--workers` / `--gpus` | `20` / `0` | 总 worker 数；`--gpus 0,1` 为每卡一个进程池 |
| `--layout` | `train` | seed 布局代：`train` / `test` / `val` / `heldout` |
| `--difficulty` | `211` | **三位数字的难度配额**，见下 |
| `--max-attempts` | `100` | 单个 episode 最多尝试几次 |
| `--max-tasks-per-child` | `8` | 每个池进程跑多少 job 后回收 |
| `--sampling-config` | 不传 | 显式传入四任务的采样输入 |

> ⚠️ `--difficulty` 是 easy/medium/hard 的**循环配额**，不是难度值。
> `211` = 每 4 局里 2 easy + 1 medium + 1 hard；`100` = 全 easy，`010` = 全 medium，
> `001` = 全 hard。它不是「难度 100」。
> 第四档 `xhard` **不进这个配额**：它只经 `--episode-specs` 清单里每组的 `difficulty` 字段进入（环境侧显式 `difficulty="xhard"`），
> 随机路径的 `seed % 3` 兜底也不会落到它。

**seed 不读表，由公式现算**（`seed_layout.py`）：

```text
seed = offset + env_code × env_block + episode × 100 + attempt
```

`env_code` 是任务在 16 任务规范序里的 1-indexed 位置：
`BinFill=4`、`VideoUnmaskSwap=5`、`VideoRepick=9`、`RouteStick=16`。
train 布局是 `offset=0, env_block=1000`，所以 BinFill 的 episode 0 首次尝试是 `4000`，
失败重试变 `4001`。难度只由 `--difficulty` 决定，**不进入 seed**。

**输出目录长这样：**

```text
<--output-dir>/
├── hdf5_files/
│   └── BinFill_ep0_seed4000.h5              逐 episode 轨迹，文件名含 任务_ep号_seed
├── videos/
│   └── BinFill_ep0_seed4000_<难度与目标描述>.mp4
├── episode_results.jsonl                    边跑边写，一行一次 attempt
├── record_dataset_BinFill_metadata.json     每任务一份：episode / seed / difficulty
├── run_parameters.json                      本次运行的全部参数
├── run_summary.json                         成功数、放弃数、耗时、吞吐、峰值内存
└── sampling_config_used.json                仅在传了 --sampling-config 时才有
```

- 文件名天然唯一（含任务、episode、seed），多 worker 共享同一输出根不会打架。
- `episode_results.jsonl` 每行含 `ok` / `attempt` / `seed` / `failure_class` / `error_type` /
  各阶段耗时 / 峰值 RSS / 绑到哪张卡，中途崩溃不丢已完成的部分。
- 失败的 attempt 不留空 h5（会被删掉），但 `FAILED_` 视频保留作为失败演进的证据。
- 体量：单局 BinFill 约 350 MB（h5）+ 11 MB（视频）。`artifacts/` 已整体 gitignore。

### 3.2 核对／导出原值快照（`--extract-config`）

只读源码 AST，**不加载仿真、不占 GPU、不采样**。

```bash
# 只核对：快照必须与当前工作树源码逐项一致
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config

# 再加一层：与固定基线提交的原版取值对照（第二节末尾说的那 61 项）
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config \
  --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8

# 不带 --check-config 就是重新导出快照（改过源码之后必须做）
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json
```

### 3.3 按需合并（`--merge-only`）

生成期**不会**自动合并（避免体量翻倍，也让单条失败不牵连其它产物）。需要每任务一个文件时
单独跑：

```bash
uv run --no-sync python scripts/generate_dataset_newseed.py --merge-only \
  --input-dir artifacts/generated/binfill-smoke \
  --output-dir artifacts/generated/binfill-merged \
  --env BinFill
```

产物是 `record_dataset_<Task>.h5`。`--output-dir` 不给时默认写回 `--input-dir`；
加 `--delete-source` 会在合并成功后删掉逐 episode 源文件（默认保留；合并期间两份并存，
需要双倍空间）。源文件按生成期写出的 metadata 逐条定位、不 glob，所以目录里混有失败残留
也不会被误吸。

### 3.4 新值注入（`--episode-specs`）

把「每条 episode 取什么值」从环境内部的随机采样搬到外部的固定规格，用于
[NEW_VALUE_INJECTION_TEST_PLAN.md](../NEW_VALUE_INJECTION_TEST_PLAN.md) 的专项。
**不传这个参数时链路与改动前逐字相同**：`gym.make` 不多这个 kwarg，四个任务模块的每个
消费点都退回原随机路径——`DEFAULT_PARITY` 验的就是这条。

参数接受两种输入，按顶层字段自动区分：

| 输入 | 顶层字段 | 用法 |
|---|---|---|
| 单份规格 | `spec_schema_version` | 配合 `--env` 与 `--episodes/--episode-start`，产物落 `--output-dir` 本身 |
| 混跑清单 | `manifest_version` | 一次调用把多个任务／难度的 job 混进同一套进程池，每组落 `<输出根>/<任务>/<难度>` |

清单必须分目录：同一任务不同难度的 seed 与 HDF5 文件名相同，不分会互相覆盖。
清单里的 `spec_path` 相对清单文件所在目录：

```json
{
  "manifest_version": 1,
  "groups": [
    {"task": "BinFill", "difficulty": "hard", "spec_path": "../specs/BinFill/hard.json", "episodes": [0, 1, 2]}
  ]
}
```

父进程在**建池之前**就把规格读完并逐条校验：必备字段、任务／难度一致、非有限数、
`spec_sha256` 自洽、episode 不重复、未知顶层字段一律拒绝，错误输入绝不带进 worker。
每个 job 拿一份独立深拷贝，worker 之间、同一 worker 的前后两局之间不共享可变缓存。

**视频核验**在 `close()` 之后做，纯观测：按 `RobommeRecordWrapper` 的
`video_prefix`（`<任务>_ep<k>_seed<s>[_FailRecover*]`）找文件、`ffprobe -count_frames`
数帧、算 SHA-256，四态写进每条结果的 `video` 字段：

| 状态 | 含义 |
|---|---|
| `complete` | 成功局帧数等于 HDF5 的 timestep 数；`FAILED_` 视频帧数 > 0 且可解码 |
| `frame_mismatch` | 帧数对不上，或不可解码 |
| `missing` | `videos/` 下没有匹配前缀的主视频 |
| `no_close` | worker 没能返回结果（池崩溃／被杀），根本没走到 `close()` |

⚠ 录像器本身**冻结**，不改、不覆盖、不打补丁（[AGENTS.md](../AGENTS.md) 强制规则第 11 条）。
视频判定失败**不改变**任务结果，也不删已落盘的 HDF5，但 `VIDEO_INDEX`／`VIDEO_DECODE`
必须如实记失败。

## 四、新值注入专项的编排入口

工具在 `scripts/injection/`（包入口 `scripts.injection.campaign`，须在仓库根目录以 `python -m` 运行；不依赖 `tests/`），**生产入口 `generate_dataset_newseed.py` 不导入它**。
五个子命令，按执行顺序：

```bash
command -v uv
INJECTION_RUN_ID=20260911-contract-v2-05

# 步骤 0：冻结 11 组 × 100 条规格（运行编号不可复用，目录已存在直接拒绝；--contract 必填）
uv run --no-sync python -m scripts.injection.campaign plan --run-id "$INJECTION_RUN_ID" \
  --contract scripts/configs/newtask-v2/injection_contract_v2.json

# 步骤 0：从冻结规格独立重算全部计数与几何
uv run --no-sync python -m scripts.injection.campaign check --run-id "$INJECTION_RUN_ID"

# 步骤 0 / 6：跑前、跑后各一套三类图
uv run --no-sync python -m scripts.injection.campaign plot --run-id "$INJECTION_RUN_ID" --phase before

# 步骤 3 + 4：串行参考两遍，再把每卡 worker 一路往上探到 OOM／超时
uv run --no-sync python -m scripts.injection.campaign run --run-id "$INJECTION_RUN_ID" --phase calibration

# 步骤 5：用校准选出的档跑 330 条
uv run --no-sync python -m scripts.injection.campaign run --run-id "$INJECTION_RUN_ID" --phase feasibility

# 步骤 6：汇总各阶段判定与计数，写轻量包到 docs/validation/newtask-v2/<运行编号>/
uv run --no-sync python -m scripts.injection.campaign report --run-id "$INJECTION_RUN_ID"
```

机器被别人占用、吞吐测不准时，改走这条：

```bash
# 只做串行参考，并行三项记 NOT_RUN
uv run --no-sync python -m scripts.injection.campaign run \
  --run-id "$INJECTION_RUN_ID" --phase calibration --skip-ladder
# 用显式指定的档直接实跑（结果里标 tier_measured=false）
uv run --no-sync python -m scripts.injection.campaign run \
  --run-id "$INJECTION_RUN_ID" --phase feasibility --tier 12
```

`compare` 单独做两个运行目录的完整 HDF5 逐位对拍，复用
`scripts/injection/h5_compare.py::compare_h5`（显式遍历全部 group、dataset 及
各层 attribute，检查类型、形状与内容）：

```bash
uv run --no-sync python -m scripts.injection.campaign compare \
  --left  artifacts/injection/$INJECTION_RUN_ID/parity/baseline \
  --right artifacts/injection/$INJECTION_RUN_ID/parity/current \
  --label DEFAULT_PARITY
```

`--subset-only` 只判交集（负载阶梯拿 120 条清单里的 16 条固定样本比串行参考时用）；
该开关只放宽「一侧多出」，交集内的任何差异照样是 FAIL。

`--skip-ladder` 让 `calibration` 只做串行参考、跳过档位阶梯，并行三项如实记 `NOT_RUN`；
`--episodes <N>`（2026-09-12 加，默认 30）让 `feasibility` 每组只实跑 episode 0～N-1（08 RouteStick 四档各 5 条用 5），清单文件名随总条数变（`manifests/feasibility20.json`），`summarize` 的分母也按该清单各组 `episodes` 求和。配套的 `--tier <n>` 让 `feasibility` 在没有校准结果时也能跑，但结果里打
`tier_measured=false`，报告不得把它说成「校准选出的档」。机器被别人重度占用、
吞吐测量必然失真时走这条路径，比测一组没有意义的数字诚实。

**档位选择的口径**：不设 RSS／`free`／swap 三条软守卫，每卡 worker 从 12 一路加到 32
（`--tiers` 可改），**实测到 OOM／池崩溃／超时为止**，用最后一个可用且吞吐最高的档做全量。
吞吐的分子只数「成功且视频完整」的条数，同时另报失败数——否则一档跑得快只是因为大量
样本快速失败，会被误当成加速。任务性失败（规划失败、碰撞拒绝）不算该档不可用，
那是样本本身的问题，与并发规模无关。

⚠ 超过五分钟的阶段按 [AGENTS.md](../AGENTS.md) 强制规则第 4 条用 detached tmux 起：

```bash
mkdir -p artifacts/logs
tmux new-session -d -s "$INJECTION_RUN_ID-calibration" \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.injection.campaign run \
     --run-id $INJECTION_RUN_ID --phase calibration 2>&1 \
     | tee artifacts/logs/$INJECTION_RUN_ID-calibration.log; \
   echo \"EXIT_CODE=\$?\" >> artifacts/logs/$INJECTION_RUN_ID-calibration.log"
tmux has-session -t "$INJECTION_RUN_ID-calibration"   # 判死活
tmux attach -t "$INJECTION_RUN_ID-calibration"        # 围观，Ctrl-b d 脱开
```

⚠ **依据散列的口径**：规格里冻结的 `sampling_config_sha256` 是
`native_sampling.json` 里 `parameters` + `positions` 的规范化散列（`operand_sha256`），
**不是整个文件的字节散列**。该文件还带 `sources.sha256`（四个任务模块的源码指纹），
接入新值后每改一次源码就得 `--extract-config` 刷新一次；拿文件散列当验收依据，会在一次
纯源码改动之后把已冻结的规格全部误判成「依据漂移」。文件散列另存为
`sampling_config_file_sha256`，变了只提示、不拦。
