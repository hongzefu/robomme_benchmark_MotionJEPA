# 新值注入测试方案：生成 1100 条固定规格，实跑其中 110 条

> **权威与状态：**本文件按 [AGENTS.md](AGENTS.md) 强制规则第 10 条重构，承接 `cfca77d`（`10.17`）保存的已确认范围；本次仅重构文档。以下新值注入接口、规格、图表和验收均为待实施设计，不是已有功能或测试结果。每个实施阶段须单独获批；后续授权明确覆盖多个阶段时按该授权执行。
>
> **代码锚点：**本次只读核查的已提交基线为 `c0cb3ee38a702738536b83c4718a495bcba148a0`，工作副本为 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`；原值来源固定为 `94449db0a068a6b454b55a13ebd48f0394d89cc8`。工作区原值并行校准的在途修改不计入此代码基线。提交编号沿用 `10.<小版本> <中文描述>`，实施时按当时最新 `git log` 递增，不预占其他任务编号。
>
> **依赖锚点：**以仓库 [pyproject.toml](pyproject.toml) 和 [uv.lock](uv.lock) 为准；本次核查的 SHA-256 分别为 `bc2346e4526c2b5c2177fe5191710c81f883c21017d45928e615327cf29cb21a`、`983de83f7b22c98b96c3c25a39958b4f5920e3232cfaa209c89542ef5639ac03`。不新增外部服务；“外部生成器”指独立 CPU 进程。历史软件版本与测量见第一部分第六节，实施前另存实际环境指纹。

## 第一部分（给人看）

### 一、总览：先固定规格，再验证执行

一句话方案：**在原难度和空间约束内均衡生成 11 组、每组 100 条固定规格，画图并静态检查全部 1100 条，再对每组前 10 条做实际注入与执行验收。**

已定死的口径如下，各节负责解释机制与判据：

1. 只覆盖四任务的 11 个难度组；`VideoRepick hard` 完全排除，990 条不作物理可行性结论（第二节）。
2. 原值配置定义合法域，外部规格固定布局、对象身份和动作；不改变尺寸、速度与时序（第三节）。
3. 独立类别按配额平衡，连续变量分层采样；受几何和动作耦合的组合报告真实频数，不声称严格均匀（第四节）。
4. 交换双方预写，执行时核验实际最近邻；不匹配直接失败。正式样本固定 `attempt=0`，失败不换 seed、不补位（第五节）。
5. 先单条冒烟，再对 16 个固定新值样本做四种运行配置校准；并行不通过时保留失败结论并用已验证串行配置完成其余样本（第六节）。
6. 规格覆盖、注入一致、可行性、并行一致性分别判定，最终逐项列出结果，不用一个总成功率替代（第七节）。

原始决策依据保存在 `cfca77d` 的提交正文，以下逐字保留关键用户原话；其余字段细化是本计划的技术设计，不冒充新增用户决策：

> 给出方案 注入新值的测试
> 根据easy medium hard的定义 测试不同的位置布局和按 episode 固定的对象与动作
> 相当于用外部的生成机器来注入 需要做到根据easy medium hard的定义尽可能均匀
> 外部的生成机器生成每个难度100个并且画图来保证均匀性
> 只测试前10是否可行 现在的测试必须单gpu单进程？还是可以多gpu 每个gpu多进程？这个验证过了吗
> 用户约定 VideoRepick hard不再测试 放弃

> 计划中要明确 你根据那些约定 生成哪些固定值
>
> 让用户一眼看懂
>
> 把plan写在根目录 不执行

### 二、目标与规模

**先由独立的外部生成器确定每条 episode 的布局、对象和动作，再交给仿真环境执行。** 外部生成器可在本机独立 CPU 进程运行，不需要先启动仿真。

| 任务 | 生成固定规格 | 实跑可行性测试 |
|---|---:|---:|
| `BinFill` | easy、medium、hard 各 100 条 | 每档前 10 条 |
| `RouteStick` | easy、medium、hard 各 100 条 | 每档前 10 条 |
| `VideoUnmaskSwap` | easy、medium、hard 各 100 条 | 每档前 10 条 |
| `VideoRepick` | easy、medium 各 100 条 | 每档前 10 条 |
| **合计** | **1100 条** | **110 条** |

**`VideoRepick hard` 放弃：本轮不生成规格、不画图、不实跑。**

其余 990 条只做规格与几何静态检查，不能据此前 110 条通过就宣称全部物理可行。

### 三、根据哪些约定，生成哪些固定值

难度与空间范围以 [native_sampling.json](scripts/configs/newtask-v2/native_sampling.json) 为依据；字段实际含义以四个任务的 `config_easy/medium/hard`、`_load_scene`、`_initialize_episode` 和 `step` 为准。

#### 3.1 难度约定 → 每条 episode 的固定内容

表中的区间都是整数，包含两端。

| 任务 | easy 约定 | medium 约定 | hard 约定 | 外部生成器最终写死什么 |
|---|---|---|---|---|
| `BinFill` | 出现 1 色；4–6 块；目标颜色池 1 色；投入 1–3 块 | 出现 2 色；8–10 块；目标颜色池 1–2 色；投入 2–4 块 | 出现 3 色；10–12 块；目标颜色池 2–3 色；投入 3–5 块 | `dynamic`；每块的颜色、位置、朝向、生成顺序；各色生成数与目标数；具体抓取、投入顺序 |
| `RouteStick` | 走 2–3 段；不主动立即回退 | 走 4–5 段；不主动立即回退 | 走 4–7 段；允许立即回退 | 布局旋转、障碍颜色、起点、完整节点序列、每段顺／逆时针方向 |
| `VideoUnmaskSwap` | 3 容器；交换 1–2 次；抓取 1–2 个 | 4 容器；交换 1–2 次；抓取 1 个 | 4 容器；交换 2–3 次；抓取 2 个 | 每个容器的位姿；红绿蓝分别藏在哪个容器；抓取顺序；每次交换的两个对象 |
| `VideoRepick` | 3 个同色方块；交换 1–2 次 | 3 个同色方块；交换 2–3 次 | **排除** | 按钮及方块位姿；统一颜色；唯一目标对象；重复抓放 1–3 次；每次交换的两个对象 |

必须保留的具体语义：

- **BinFill：**目标颜色池中的某色可以最终分到 0 块；同色抓取对象仍取该颜色生成列表的前若干块。`dynamic` 的出现时序沿用原实现。
- **RouteStick：**段数是边数，节点数等于段数加 1；只能走相邻节点。easy、medium 在端点仍允许被迫回退。
- **VideoUnmaskSwap：**只有前 3 个容器藏物，第 4 个恒空；保留现有对象索引映射。
- **VideoRepick：**同一局 3 块颜色相同；重复抓取始终指向同一个对象；首次交换由目标方块发起。

例如，一条 `RouteStick easy` 规格可以明确写成：**旋转 −12°，路线 `0→2→4`，两段方向分别为顺时针、逆时针。** 这是规格示意；是否可执行由后续实跑判断。

#### 3.2 位置约定 → 每条 episode 的具体坐标

沿用原有区域和布局类型。位置单位为米。

| 对象 | 在什么范围内生成固定值 |
|---|---|
| `BinFill` 按钮 | 中心 x：−0.25～−0.15；y：−0.20～0.20 |
| `BinFill` 孔板 | 中心 x：−0.05～0.15；y：−0.20～0.20；旋转：−20°～20° |
| `BinFill` 方块 | 中心 x：−0.28～0.08；y：−0.23～0.23；自身朝向一整圈；满足原避让规则 |
| `RouteStick` | 保留 1×9、间距 0.07 的排列；整体绕世界原点旋转 −30°～30° |
| `VideoUnmaskSwap` 容器 | easy 使用三角／直线布局，其他两档使用四点布局；旋转后锚点周围，x、y 各偏移不超过 0.0425；自身旋转 0°～90° |
| `VideoRepick` 方块 | 三角／直线布局；旋转后锚点周围，x、y 各偏移不超过 0.05；自身朝向一整圈 |
| `VideoRepick` 按钮 | 中心 x：−0.25～−0.15；y：−0.05～0.05 |

两个视频任务的**布局整体旋转沿用原值 0～180 弧度**；只旋转锚点，之后的位置偏移仍沿世界坐标轴。高度、物体尺寸、碰撞几何、动作速度和时序沿用原实现。

#### 3.3 代码落点与反例

难度字段位于 `native_sampling.json::parameters.<任务>.configs.<难度>`；构造期的 `dynamic`、`num_repeats`，以及 `object_selection`、`swap_selection`、`walk` 也位于各任务的 `parameters` 下。空间配置位于 `positions.<任务>`。实际消费分别见 [BinFill.py](src/robomme/robomme_env/BinFill.py)、[RouteStick.py](src/robomme/robomme_env/RouteStick.py)、[VideoUnmaskSwap.py](src/robomme/robomme_env/VideoUnmaskSwap.py)、[VideoRepick.py](src/robomme/robomme_env/VideoRepick.py) 的 `__init__`、`_load_scene`、`_initialize_episode` 和 `step`。新增规格在这些原创建点和动作绑定点接入，不通过创建后整体挪动物体实现。

视频布局遵循 `p_xy = R(theta) × anchor_xy + delta_world`，其中 `theta ∈ [0,180)` 弧度；画图另列 `theta mod 2π`。例如 `theta=90` 是 90 弧度，不能按 90° 消费。有效 XY 范围是原区域扣除物体半尺寸后的范围，不能直接把区域边界当作物体中心边界。表中的范围表示可行域边界；实际随机采样保持原半开区间，有限精度边界在静态检查中单列。

路线合法性使用 [route.py](src/robomme/robomme_env/utils/route.py)::`generate_dynamic_walk` 的线性邻接语义：

```text
节点拓扑：0 ── 2 ── 4 ── 6 ── 8
2 段路线：0 → 2 → 4       节点数 = 段数 + 1 = 3
端点回退：2 → 0 → 2       easy / medium 合法，被迫回退
主动回退：2 → 4 → 2       easy / medium 不合法，hard 可合法
```

⚠ `RouteStick::__init__` 仅在未显式传难度的 seed 推导分支末尾将难度覆盖成 `easy`；当前生成器显式传入 `difficulty`，不进入该分支。须分别记录请求难度、实际配置和最终 `task_state.difficulty`，用实际段数／回退约束核对难度覆盖，不顺手修旧行为。两个视频任务的 `step` 才决定实际交换搭档，初始化 schedule 里的空值不能充当完整动作证据。

上述细化把“固定动作”落实为可核对的对象身份、路线和执行位置。历史 schema 3 已核对 66 组原值操作元；新规格是否真正消费仍须通过 `INJECTION_BINDING`，目前没有新值实测收益数字。

### 四、如何均匀分配，画什么图证明

每组 100 条采用固定生成 seed `20260909`，按任务、难度独立派生随机流；生成结果不受进程调度影响。

拟由 `tests._shared.injection_campaign::plan` 负责配额与采样，`check` 独立从最终规格重算计数。对于有 `k` 个可独立分配候选的变量，配额满足 `n_i ∈ {floor(100/k), ceil(100/k)}` 且 `sum(n_i)=100`；因此两类为 `50/50`，三类为 `34/33/33`。派生随机流使用稳定任务／难度标识，不用受进程影响的 Python `hash()`。规格生成 seed 与仿真 `seed_layout::SeedLayout.seed` 是两套用途，均须留档。

| 覆盖项 | 分配方法 |
|---|---|
| `BinFill dynamic` | 每档 `True`、`False` 各 50 条；前 10 条各 5 条 |
| 三角／直线布局 | 适用的每组各 50 条；前 10 条各 5 条 |
| 两种合法整数取值 | 各 50 条，例如交换次数 1／2 |
| 三种合法整数取值 | 按 34／33／33 分配，例如重复数 1／2／3 |
| `RouteStick` 起点 | 5 个起点各 20 条；前 10 条各 2 条 |
| `RouteStick hard` 长度 | 4、5、6、7 段各 25 条 |
| 颜色、目标对象、合法顺序 | 在合法候选集合内尽量平衡；可独立分配的类别计数差不超过 1 |
| 连续位置与角度 | 分层采样；将 100 条组织成 10 个均衡小组，让前 10 条也分散覆盖各区间 |
| 路线方向、交换对象对 | 在合法路线、最近邻和对象身份约束下平衡，报告实际频数及未覆盖组合 |

先分配类别配额，再检查几何约束。不通过避让检查时，在相同配额内重新采样；不能靠减少物体、改成更简单的动作或扩大区域凑足数量。若仍不能满足，报告具体缺口。

**“均匀”针对合法采样变量及对象选择；碰撞避让后的整体空间分布不承诺严格均匀。**

每组保存以下图与对应计数表：

1. **100 条布局总览：**每条一个俯视小图，标出对象编号、目标和动作；突出前 10 条。
2. **空间覆盖图：**实际 XY 散点、占用格、位置与角度分箱计数；视频任务同时展示原始弧度和实际物理朝向。
3. **对象与动作分布图：**颜色、目标索引、数量、交换对象对、路线长度、起点及方向频数。

验收以计数和约束检查为依据，图用于直观复核。不能仅凭“看起来均匀”判通过，也不要求 100 条穷举全部组合。

连续变量可按十个粗分箱、每箱十个细分层组织为十批；每批从每个粗分箱取一个细分层点，首批即 episode `0～9`。不同变量使用独立排列，避免所有坐标落在一条对角线上：

```text
原区间：[a,b)
粗分箱：| 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
前10条：每箱1个；全部100条：每箱10个（无几何拒绝时）
几何拒绝：留在原类别和原分层内重采样 → 不足则登记缺口
```

⚠ 对每局物体数变化的对象位置，分别报告“每 episode 的采样输入配额”和“全部对象的实际位置频数”，不能要求二者都恰好每箱 10 个。几何耦合变量须列明条件与拒绝数；只有独立类别才适用计数差不超过 1。`COVERAGE_QUOTA` 的收益是可复算配额，`STATIC_GEOMETRY` 仅证明静态初筛通过；本轮尚未生成图或统计结果。

### 五、如何注入，以及前 10 条怎样验收

#### 5.1 接口与固定规则

当前 schema 3 只有采样规则，尚无逐 episode 结果表。因此：

- 保留 `native_sampling.json` 作为原值依据；新增独立 `--episode-specs` 输入。源码调整后刷新来源指纹，原值参数不变。
- 每个任务／难度保存一份含 100 条记录的规格文件，episode 编号为 `0～99`。每条包含任务、难度、稳定对象标识、生成顺序、位姿、动作及规格散列。
- 在 [生成入口](scripts/generate_dataset_newseed.py) 中由父进程校验，再通过 `EpisodeJob.episode_spec` 传入环境。
- 在原来的对象创建和动作构造位置消费规格；构造初始化与随后正式 `reset()` 都使用同一份内容。未传规格时保留原有随机调用路径。
- 外部采样、出图和专项编排放入测试工具 `tests._shared.injection_campaign`，提供 `plan/check/plot/run` 子命令。

**交换双方采用已确认的规则：外部预写两个对象；交换开始时检查指定搭档是否为当时实际最近邻，不符直接失败，禁止换搭档。** 图中的预定交换对须标明是否经过实跑核验。

实际最近邻必须复用两个视频任务 `step` 的比较语义：以交换开始时 actor 的 XY 欧氏距离扫描生成列表，排除自身，只有 `dist < closest_dist` 才更新，因此等距时生成顺序靠前者胜出。记预定发起对象为 `a`、预定搭档为 `b_spec`，运行时计算 `b_actual`；仅 `b_spec == b_actual` 才调用原交换动作。检查不能被“提前把搭档字段填成非空”绕开。外部模拟的理想交换位置只可用于设计规格，不能替代这个运行时检查。

#### 5.2 改动前后链路与数值边界

```text
现状：native_sampling.json（采样规则，JSON 字节数以文件实测）
  → load_sampling_config（dict；只校验和复制，不改采样数值）
  → EpisodeJob.sampling_config → _run_jobs → _worker → gym.make
  → 任务 __init__ / _load_scene（原 RNG 产生位置、对象和路线）
  → _initialize_episode → RobommeRecordWrapper.reset 再次初始化
  → _execute_tasks / 任务 step（运行时选择最近邻，执行物理动作）
  → RobommeRecordWrapper（原 HDF5 / 视频）

开启后：CPU plan → 11份JSON × 100条 → check / plot
  → --episode-specs → 父进程校验与索引（新增，不采样）
  → EpisodeJob.episode_spec（每 job 独立 dict；pickle 实际字节数留档）
  → _worker → gym.make(episode_spec=...)（传同一内容，不改数）
  → 原创建点消费位姿 / 对象 / 路线（替代指定随机结果；这里有意改数）
  → 两次初始化消费同一规格（深拷贝工作态，散列不变）
  → 原动作构造与 step（校验身份及最近邻；速度与时序不变）
  → 原记录器 + 测试侧证据（只读记录，记录开关须校准）

关闭后：没有 --episode-specs → 不额外传 kwarg → 保留上面的现状链路
```

规格里位置为长度 3 的有限数数组，四元数为长度 4，单对象共 7 个标量；JSON 本身没有 tensor dtype 或固定字节数，不能写成“每对象 28 字节”。进入环境时沿用各创建点的原转换；若该点是 `float32[3]`／`float32[4]`，其纯数值载荷才分别为 12／16 字节。记录实际 shape、dtype、转换前值和转换后位模式；不要求 JSON 十进制文本等于仿真存储字节。

路线为 `L+1` 个整数节点和 `L` 个方向标签；`L` 由难度决定。HDF5 每个 dataset 的 shape、dtype 与字节量由实际产物统计，不假设固定轨迹长度。本链路不训练模型，可训练参数为 0；JSON、pickle、actor 和 HDF5 四个边界分别记录规格身份及数值转换，关闭态不新增 dtype 转换。

#### 5.3 验收范围

| 检查 | 全部 1100 条 | 每组前 10 条，共 110 条 |
|---|---|---|
| 难度、数量、索引、动作合法性 | 检查 | 检查 |
| 均匀配额、位置范围、几何静态初筛 | 检查 | 单列前 10 条统计 |
| 创建出的对象、位姿与规格一致 | — | 检查 |
| 两次初始化及实际动作绑定一致 | — | 检查 |
| 抓取对象、交换双方、路线和方向 | — | 按实际执行事件检查 |
| 最终成功及 HDF5 契约 | — | 检查并保存视频 |

正式实跑固定 `attempt=0`、`--max-attempts 1`。失败保留原条目，**不能换 seed，也不能拿第 11 条补位**。

报告分别统计：通过、规格拒绝、实际对象／动作不符、规划失败、超时、未运行。失败即使没有 HDF5，也必须保留规格、日志和失败位置。

产物按运行编号、任务、难度分目录，避免三个难度相同 episode 编号互相覆盖；规格与结果通过散列关联。历史证据保持只读。

### 六、GPU 与进程：现状和本轮执行顺序

**可以多 GPU、每个 GPU 多 worker；完整对拍目前采用单 GPU、单生成 worker。**

| 问题 | 已核实的结论 |
|---|---|
| 生成器支持什么？ | 每 GPU 一个 `spawn` 进程池。`--gpus 0,1 --workers 4` 表示每卡 2 个 worker；`--workers 8` 表示每卡 4 个 |
| 多卡多进程以前验证过吗？ | [早期报告](docs/validation/newtask-v2/20260909T1441Z-postclean/README.md) 记录 schema 2 使用双卡、每卡 4 worker，16 个 easy 任务全部成功，耗时 72.7 秒；原始重产物已清理 |
| 最新 schema 3 验证过什么？ | [完整对拍报告](docs/validation/newtask-v2/20260909-actions-v3/README.md) 的 60 次生成全部使用 GPU 0、单 worker；同 worker 连续生成也已验证 |
| 当前原值并行校准是什么状态？ | 本次读取 `AGENTS.md` 时仍为进行中：四任务 16 个原值样本、五轮 80 次；首次核查时测试工具尚未提交，重构期间已提交为 `91bacf9`，账本登记正式编号 `20260909-schema3-parallel-v2` 正在运行。此处仅核对账本状态，未独立复验该运行；它不包含新值注入，不能作为下述四轮校准已通过的证据；完成后在本节追加来源和结果 |
| 还缺什么？ | **逐 episode 新值注入的多卡并行，以及并行与串行结果的一致性尚未验证** |

本轮执行顺序固定为：

1. **代码检查与最小冒烟：**定向轻量测试，加单任务、单 episode、单 GPU、单 worker 的新值测试；代码验收总耗时控制在 5 分钟内。
2. **并行校准：**从四任务各取前 4 条；前三任务用 hard，`VideoRepick` 用 medium，共 16 条。依次比较：
   - GPU 0，1 worker；
   - GPU 1，1 worker；
   - GPU 0，2 workers；
   - GPU 0、1，共 4 workers。
3. **验证真实并发：**记录 GPU、PID 和运行时间区间，确认双卡每卡确有两个 worker 重叠执行；比较注入内容、对象动作事件及完整 HDF5，并记录显存和耗时。生成成功与逐位一致分别报告，规划回退或差异不自动放宽判据。
4. **校准通过后：**前 10 条可行性测试采用双卡、每卡 2 worker。校准样本均来自这 110 条之内，重复运行不扩大样本范围；校准失败则保留原因，使用已通过校准的串行配置完成其余测试。
5. **留档与收尾：**预计超过 5 分钟的专项生成用 detached `tmux` 保存日志和退出码；记录全部 1100 条的静态结果及 110 条的实跑结果，更新账本，只提交本轮代码和轻量证据。

最终结论必须明确区分：**规格是否均匀、注入是否生效、前 10 条是否可执行、并行是否与串行一致。**

四种配置依次记为 `S0`（GPU 0／1 worker）、`S1`（GPU 1／1 worker）、`P0`（GPU 0／2 workers）、`P01`（GPU 0、1／4 workers）。校准总计 `16×4=64` 次执行、16 个唯一规格；其余 `110−16=94` 个唯一样本在校准后执行。因此不含最小冒烟及另行批准的诊断重跑时，计划执行次数为 `64+94=158`，物理覆盖仍只有 110 条。保留 64 次的逐轮结果，不能只保存最后一次。

生产调度依据 `generate_dataset_newseed.py::_run_jobs` 的 `per_gpu=max(1, workers//len(gpu_ids))`。上述配置均能整除；`--workers` 在这里是总数，不能误读为每卡数。真实并发判据使用同一主机的单调时钟，比较两个不同 PID 的实际仿真窗口 `[first_step,last_step]`，要求 `min(end_a,end_b)−max(start_a,start_b)>0`；双卡还需存在跨卡共同执行窗口。只记录进程存活、导入或排队重叠不算通过。

⚠ 158 次是预算推导，不是实测。历史 schema 3 的 60 次生成耗时 2479.7 秒，不能按比例承诺新布局耗时或并行加速。报告必须保存每种配置的墙钟时间、显存峰值、实际重叠时长和完整差异；有规划回退或逐位差异时不自动放宽容差。

### 七、验收与阶段安排

以下大写标识为**拟新增的判定协议**，不是当前工具已经打印的结果。每项须报告 `PASS`、`FAIL` 或 `NOT_RUN` 及分子／分母；表中的数字是目标值。实现后由独立检查器从规格、事件或原始产物推导，不能只读报告的布尔标记。

| 判定项 | 查什么／怎么查 | 通过说明什么／目标判定行 |
| --- | --- | --- |
| `SPEC_SCOPE` | 枚举 11 个组、每组 episode 0～99，检查缺号、重复、越界和排除项 | 范围齐全；`SPEC_SCOPE=PASS groups=11 specs=1100 excluded=VideoRepick-hard` |
| `SPEC_REPRODUCIBLE` | 同 seed 独立生成两次，改变组调度顺序，逐记录比较规范化内容及散列 | 外部生成不依赖调度；`SPEC_REPRODUCIBLE=PASS compared=1100 differences=0` |
| `COVERAGE_QUOTA` | 重算全量与前 10 配额、分层计数、条件频数和缺口 | 声明的独立配额满足，耦合限制已披露；`COVERAGE_QUOTA=PASS groups=11 prefix=10 quota_gaps=0` |
| `STATIC_GEOMETRY` | 逐条检查难度、索引、范围、避让、路线与动作长度，报告失败位置 | 全部静态合法，不代表物理可行；`STATIC_GEOMETRY=PASS checked=1100 rejected=0` |
| `PLOT_EVIDENCE` | 检查每组 100 个小图及三类图表，核对图与计数表的规格散列 | 图表可追溯，目视结论另记；`PLOT_EVIDENCE=PASS groups=11 thumbnails=1100` |
| `DEFAULT_PARITY` | 修改前后关闭注入、相同 seed／配置，比较原调用流、对象动作及完整 HDF5 | 被测关闭路径不变；`DEFAULT_PARITY=PASS cases=<实际数> differences=0`，不得省略样本清单 |
| `SMOKE` | 单任务、单 episode、单 GPU、单 worker，检查注入、终态、HDF5 和视频；对观察器做开关对照 | 核心链路可进入矩阵；`SMOKE=PASS episodes=1 attempt=0 observer_differences=0` |
| `INJECTION_BINDING` | 检查创建前输入与创建后规范化位姿、两次初始化、所有目标／方向／交换事件 | 规定内容实际被消费；`INJECTION_BINDING=PASS unique=110 mismatches=0` |
| `PARALLEL_CONTENT` | `S1/P0/P01` 各与同规格 `S0` 比较完整 HDF5 与对象动作证据，共 48 对 | 被测新值样本跨配置逐位一致；`PARALLEL_CONTENT=PASS unique=16 pairs=48 differences=0` |
| `PARALLEL_OVERLAP` | 核对卡身份、不同 PID 与真实 step 时间区间，逐组给重叠证据 | 并发确实发生；`PARALLEL_OVERLAP=PASS mode=P01 gpus=2 workers_per_gpu=2`，同时报告 `P0` 检查结果 |
| `FEASIBILITY` | 110 个唯一规格逐条核验最终严格布尔成功、`inspect_episode_terminal` 契约及视频存在 | 仅这 110 条物理可行；`FEASIBILITY=PASS unique=110 succeeded=110 attempt=0` |
| `DELIVERY` | 离线重算清单散列，检查所有规格和 110 行结果、命令、退出码及六类状态计数 | 报告完整可复核；`DELIVERY=PASS specs=1100 result_rows=110 missing=0`，不等于前面所有项目通过 |

失败处理：任何样本不得被移出分母；没有成功 HDF5 的执行保留失败证据，并将依赖该产物的比较列为未完成。只有所有具名项目实际通过才称全方案验收通过。若走串行回退，仍应完成交付，但并行项目保持 `FAIL`／`NOT_RUN`，不改写成整体通过。

| 阶段 | 内容 | 判据与推进条件 |
| --- | --- | --- |
| 0 | 核对授权、代码／配置／环境和在途原值校准；冻结实现基线 | 第二部分前置红线满足，记录所有未验证项 |
| 1 | 实现独立规格生成、静态检查与三类图表 | `SPEC_SCOPE`、`SPEC_REPRODUCIBLE`、`COVERAGE_QUOTA`、`STATIC_GEOMETRY`、`PLOT_EVIDENCE` |
| 2 | 接入规格、错误分类、事件证据，验证关闭态和单条冒烟 | `DEFAULT_PARITY`、`SMOKE`；短验证累计不超过 5 分钟，失败不放大 |
| 3 | 固定 16 个规格，按四配置执行 64 次新值校准 | `PARALLEL_CONTENT`、`PARALLEL_OVERLAP`；失败按第六节串行回退，不替换规格 |
| 4 | 完成其余 94 条，汇总 110 个唯一样本及全部重复执行 | `INJECTION_BINDING`、`FEASIBILITY`；拒绝／失败／超时／未运行全部列出 |
| 5 | 保存轻量证据、独立离线复核、更新说明与账本并提交 | `DELIVERY`；逐项报告此前所有判定，不覆盖历史证据 |

#### 7.1 实施后实测追加区

目前为空：本次只读检查和文档重构没有执行阶段 1～5。后续在这里追加运行编号、提交、环境、命令、退出码、实测数字与逐项结论；不回写上述原计划来适配失败结果。

## 第二部分（技术细节，供 agent 追踪）

### 〇、前置声明与红线

1. **授权：**本轮只改文档；阶段表是未来工作说明。不得据此启动实现、规格生成、仿真、清理、分支创建或推送。
2. **范围：**第一部分第二节的 11 组是唯一规格集合；episode `0～9` 是唯一实跑样本集合，`VideoRepick hard` 不生成、不画图、不实跑。
3. **原值：**`native_sampling.json` 的 `parameters`、`positions` 和原值操作元不变；仅源码接入后按原提取流程刷新必要来源指纹。不得借机改变碰撞几何、速度、时序、成功阈值、默认随机调用或旧难度行为。
4. **失败：**正式执行固定 `--max-attempts 1`；加载器拒绝新值专项中 `max_attempts != 1`。不能换 seed、换搭档、换难度、改规格补跑或使用第 11 条补位。
5. **存储：**规格、数据、日志、图像全部落本仓库；官方参考集与历史保留产物只读。运行编号不可复用，文件和目录按任务／难度分隔。
6. **证据：**新增接口和命令须先实现才能运行；本文件 `PASS` 行全是目标。历史原值证据与新值证据分开归因，禁止借用在途原值校准的通过标记。
7. **环境与协作：**先 `command -v uv`，全部 Python 入口由 `uv run` 启动；依赖变更写回 `pyproject.toml` 并锁定。不得把其他任务的未提交文件纳入本轮提交或覆盖其结果。

### 一、按阶段与文件的改动清单

下表是待实施范围，不是本次已修改文件表。生产侧继续使用已有生成文件，不增加第三个生成侧脚本，不从生产代码导入 `tests`。

| 文件 | 锚点 | 改什么 | 关闭态 | 开启态 |
| --- | --- | --- | --- | --- |
| `scripts/generate_dataset_newseed.py` | `_args`、`generate_dataset_newseed`、`EpisodeJob`、`_worker` | 新增 `--episode-specs`、只读加载与校验、每 job 深拷贝、条件传环境参数，记录规格散列 | 原 kwargs 和 RNG 调用不变 | 父进程建池前拒绝错误输入，两次初始化共享内容而不共享可变缓存 |
| 同上 | 拟新增 `load_episode_specs`、`validate_episode_spec`；`_synth_failure` 与结果元数据 | 独立格式校验与错误定位，补规格身份及失败阶段 | 保留原失败逻辑 | 规格拒绝不进入 worker；运行拒绝不触发换 seed |
| 四任务模块 | `__init__`、`_load_scene`、`_initialize_episode` | 可选 `episode_spec`；原创建点消费位置、颜色、顺序、目标和动作 | 保留原配置与抽样路径 | 创建后观测并对照；构造初始化与正式 reset 都从规格重建工作态 |
| 两个视频任务模块 | `step`、`_refresh_swap_schedule` | 每次交换开始核验预定对象对与实际最近邻，绑定后复用 | 保留原最近邻扫描 | 不符立即报错，原交换动作和时间窗不变 |
| `RouteStick.py` | `_load_scene`、`_initialize_episode` | 消费固定节点与逐段方向，绑定演示、求解、目标判定和 segment | 保留 `generate_dynamic_walk` 调用 | 校验拓扑后直接使用给定路线；记录真实难度与有效配置 |
| `scripts/configs/newtask-v2/native_sampling.json` | `sources.sha256` 及来源描述 | 接入后刷新必要指纹，提取与历史操作元复核 | 原值不变 | 仍是合法域依据，不承担逐 episode 表 |
| `tests/_shared/injection_campaign.py`（拟新增） | `plan/check/plot/run`，拟新增 `compare/report` | 外部采样、出图、专项编排和独立检查报告 | 不被生产导入 | 输出完整规格和逐次证据，复用原生产入口 |
| `tests/_shared/parity_observer.py` | 原事件、初始化和运行时记录位置 | 仅在确有缺字段时扩充只读证据；先检查在途原值校准最终版本 | 默认证据兼容 | 记录规格散列、实际绑定与两次初始化，不额外采样 |
| `tests/lightweight/test_episode_specs.py`、`test_injection_campaign.py`（拟新增） | 格式、约束、配额、隔离与篡改反例 | 定向验证第七节协议，避免只测实现镜像 | 无规格路径回归 | 缺字段、改散列、非法动作、假并发均拒绝 |
| `scripts/README.md`、`AGENTS.md`、本计划及 `docs/validation/newtask-v2/<运行编号>/` | 用法、状态、实测追加区、交付包 | 实施后更新真实结果 | 历史结果不覆盖 | 实测与未覆盖项分别留档 |

`scripts/seed_layout.py::SeedLayout.seed`、`RobommeRecordWrapper` 和 `utils/route.py::generate_dynamic_walk` 作为既有语义锚点，当前不计划修改。HDF5 对拍复用 `tests/_shared/native_sampling_parity.py::compare_h5`，其 `_walk` 显式遍历 group、dataset 及各层 attribute，`_dataset_signature` 和 `_first_element_difference` 检查类型、形状与内容；保持此全集覆盖，不能只挑动作字段比较。

### 二、规格契约、生成与消费细节

拟新增规格格式独立于 schema 3，每组一个 JSON，顶层至少包含 `spec_schema_version`、`task`、`difficulty`、`generator_seed`、`derived_seed`、`generator_version`、`sampling_config_sha256` 和 `episodes`。任务／难度与 CLI 请求必须一致；未知字段、重复 episode、非有限数、缺记录和散列不符均在父进程报错。每个文件恰好 100 条，执行时按 episode 键取子集，不因排序或列表截取错配。

每条记录至少含 `episode`、`layout`、`objects`、`actions`、`spec_sha256`。`objects` 的稳定 `object_id` 与 `spawn_order` 分离；包含对象类型、颜色和完整 `position_xyz`／`quaternion_wxyz`。JSON 四元数采用 SAPIEN 的 `wxyz` 顺序；yaw 与布局角度另外保存单位清晰的原始参数，并校验与最终位姿一致。固定高度从原创建规则派生，不开放为任意新值。

| 任务 | 拟定任务字段／必须检验的关系 |
| --- | --- |
| `BinFill` | `dynamic`、各色生成数／目标数、对象创建顺序及抓取列表；目标池某色允许分到 0，实际抓取须是同色生成列表前若干块，投入动作总数与目标数相符 |
| `RouteStick` | `rotation_deg`、障碍颜色、`nodes`、`directions`；`len(nodes)=L+1`、`len(directions)=L`，方向仅 `clockwise/counterclockwise`，逐段绑定相同演示和执行对象 |
| `VideoUnmaskSwap` | 前三容器的红绿蓝映射、抓取对象顺序、`swap_pairs`；第 4 容器恒空，交换发起索引沿用现有映射，搭档预写并在执行开始复核 |
| `VideoRepick` | 三块同色、`target_object_id`、`num_repeats`、`swap_pairs`；目标唯一且重复抓放不变，首次交换由目标发起 |

散列设计：对不含 `spec_sha256` 的记录按固定 UTF-8、键排序、固定分隔符、禁止 NaN 的规范 JSON 序列化取 SHA-256；整个文件另保存字节散列。加载后不得改写规范记录；任务内只修改深拷贝工作态。两次初始化均重新建立 `object_id → actor` 映射，不复用前一次的 actor 引用或已完成交换缓存；检查同 worker 连续两局，防止内容泄漏。

生成器的重采样只发生在规格冻结之前，同配额、同分层内有界重试；重试上限由实现时的显式参数记录，耗尽则报告缺口并停止推进。规格冻结后禁止靠继续采样处理仿真失败。外部预定交换对要记录静态预测状态，实跑报告另存实际时刻的位置、距离、候选顺序、选中对象和调用窗口。

位姿检查分两层：创建输入按原转换后目标 dtype 的数值／位模式核对；创建后与两次初始化的 actor 位姿记录实际值及误差。重力、接触后的轨迹不能要求始终等于静态规格。任何因引擎四元数规范化等需要的比较口径必须在实跑前固定，不能在出现失败后临时加容差；跨运行 HDF5 比较始终保持逐位判据。

### 三、对拍闸门总表

| 闸门 | 输入与比较双方 | 必须覆盖的反例／失败处置 | 对应判定 |
| --- | --- | --- | --- |
| 配置来源 | 当前提取值与冻结快照、原值基线 | 来源指纹变动但操作元不得漂移；不静默接受缺字段 | `DEFAULT_PARITY` 的前置条件 |
| 规格重现与静态检查 | 同一输入的两次 CPU 生成、独立重算全部规格 | 组缺失、排除难度、错误单位、非法节点／对象索引、配额缺口、散列篡改 | `SPEC_SCOPE` 至 `PLOT_EVIDENCE` |
| 关闭态与观察器 | 修改前后关闭注入；观察器关闭／开启 | 原 RNG 流被多消费、配置污染、观察器改变 HDF5 | `DEFAULT_PARITY`、`SMOKE` |
| 注入与初始化 | 规格 → 创建输入 → 实际 actor → 两次初始化 → 每个动作 | 错目标、错方向、只改描述、第二次 reset 重新抽样、同 worker 缓存残留 | `INJECTION_BINDING` |
| 最近邻 | 预写对象对与执行开始时真实扫描结果 | 等距顺序错、把初态当执行时状态、预填字段导致跳过检查 | `INJECTION_BINDING` |
| 四配置校准 | 同一 16 规格的 `S0` 对 `S1/P0/P01` | 少产物、不同 timestep、数值／图像差异、规划回退、只有排队重叠 | `PARALLEL_CONTENT`、`PARALLEL_OVERLAP` |
| 最终样本与交付 | 110 个唯一规格、每次执行记录、结果表及文件清单 | 无 HDF5 的失败被丢弃、第 11 条补位、未运行被记成功、仅保存通过标记 | `FEASIBILITY`、`DELIVERY` |

六类最终状态互斥：通过、规格拒绝、实际对象／动作不符、规划失败、超时、未运行；对应计数之和为 110。基础设施或代码错误另有 `error_type`／`failure_class`／阶段明细，阻塞受影响样本并计入未完成项，不冒充物理不可行。64 次校准重复执行单独列逐轮结果；唯一规格的可行性结论与跨配置一致性结论分开，不能用重复成功次数扩大分子。

### 四、运行手册

以下命令是后续获批实施的入口约定，**本次不执行**。现有命令可只读检查；`injection_campaign`、`--episode-specs` 及两个新测试文件目前尚不存在，须实现并核对 `--help` 后才能运行。命令均从仓库根目录执行，`--difficulty` 用现有三位比例：easy=`100`、medium=`010`、hard=`001`。

现有只读预检：

```bash
command -v uv
git status --short
git rev-parse HEAD
sha256sum pyproject.toml uv.lock scripts/configs/newtask-v2/native_sampling.json
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config \
  --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8
```

拟新增 CPU 入口约定；`plan` 固定第一部分范围并拒绝已存在的运行根目录，`check` 和 `plot` 从该编号的冻结清单读取输入：

```bash
command -v uv
INJECTION_RUN_ID=20260909-new-values-01
uv run --no-sync python -m tests._shared.injection_campaign plan \
  --run-id "$INJECTION_RUN_ID" --seed 20260909 --per-group 100
uv run --no-sync python -m tests._shared.injection_campaign check --run-id "$INJECTION_RUN_ID"
uv run --no-sync python -m tests._shared.injection_campaign plot --run-id "$INJECTION_RUN_ID"
```

拟新增最小冒烟入口如下。选择固定 `BinFill hard` episode 0，属于 110 个目标样本；观察器对照使用另一个子目录，不能覆盖首条产物。冒烟失败停止矩阵，保留该规格：

```bash
command -v uv
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir "artifacts/injection/$INJECTION_RUN_ID/smoke/BinFill/hard" \
  --env BinFill --episodes 1 --episode-start 0 --difficulty 001 \
  --gpus 0 --workers 1 --layout train --max-attempts 1 --max-tasks-per-child 8 \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json \
  --episode-specs "artifacts/injection/$INJECTION_RUN_ID/specs/BinFill/hard.json"
```

代码改动后的短测用 `uv run --no-sync python -m pytest tests/lightweight/test_episode_specs.py tests/lightweight/test_injection_campaign.py tests/lightweight/test_native_sampling_config.py -q`，随后执行上述核心端到端冒烟，总预算不超过 300 秒；预计超出时选取覆盖关键拒绝分支与成功链的定向子集，剩余预算再补轻量全量。不以语法检查代替端到端，也不因五分钟限制跳过冒烟。长矩阵属于另行获批的实验阶段。

拟新增 `run --phase calibration` 固定 16 条和四种配置，按任务／难度／配置拆目录并调用原生产入口；`run --phase feasibility` 先读取校准报告，再执行剩余 94 条。`compare` 独立检查原始数据；`report` 无论此前通过与否都保存完整状态，不得因某条失败遗失剩余样本。

超过五分钟时，校准命令按下面模板启动。运行编号须为已由 `plan` 新建的编号；后续阶段复用其冻结规格，但每次执行使用全新子目录。只有校准结果和阶段授权均允许后，才把子命令改成可行性阶段并另起日志：

```bash
mkdir -p artifacts/logs
tmux new-session -d -s "$INJECTION_RUN_ID-calibration" \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m tests._shared.injection_campaign run --run-id $INJECTION_RUN_ID --phase calibration 2>&1 | tee artifacts/logs/$INJECTION_RUN_ID-calibration.log; code=\$?; echo EXIT_CODE=\$code | tee -a artifacts/logs/$INJECTION_RUN_ID-calibration.log; exit \$code"
tmux has-session -t "$INJECTION_RUN_ID-calibration"
tmux attach -t "$INJECTION_RUN_ID-calibration"
```

记录每次生产子命令的退出码，完整命令中的 `--gpus`、`--workers`、线程限制、`--affinity`、`--layout`、难度、attempt、规格散列和 seed 必须可追溯。卡号之外另存 GPU UUID／PCI 地址；父进程与各 worker 的实际参数必须一致。原值并行校准工具可在其完成提交后复用只读计时／资源采样方法，但不能将原值样本表当作新值规格表。

### 五、风险登记

| 风险 | 识别方式 | 处置与保留边界 |
| --- | --- | --- |
| 0～180 弧度被误写为角度 | 比较原参数、旋转矩阵及实际朝向图 | 保留原值，原始弧度与模 `2π` 朝向同时留档 |
| 类别配额与几何约束耦合 | 记录各配额格的提议／拒绝／接受数 | 同配额内有界重采样，缺口明确失败，不降难度 |
| 动态交换导致预定搭档失效 | 在真实交换开始时记录完整距离和候选序 | 直接报错并保留样本，不现场改搭档 |
| 两次初始化或连续 worker 污染 | 规格散列、actor 映射与工作态前后检查 | 每次从独立副本重建，不修改类配置 |
| GPU／规划器数值差异 | 全 HDF5、事件与回退记录对照 | 逐位失败原样报告；仅用已校准串行配置推进剩余样本 |
| 专项比较只取部分字段 | 核对调用原比较器及其完整差异清单 | 保持全部 group／dataset／attribute 和类型覆盖，不能把缺测视作一致 |
| 其他任务同期更新工具或文档 | 每阶段前记录 `git status` 与文件散列 | 以完成提交为依赖，保留他人 hunk；追加真实证据时再合并文档 |
| 既有轻量测试失败混淆本轮结果 | 与原值报告中四个具名失败逐项比较 | 新失败必须处理；旧失败单列，不宣称全量全绿 |

### 六、盲区诚实清单

- 990 条规格不运行物理仿真，静态合法不代表抓取、交换或整条路线可执行。
- 100 条不穷举对象、顺序、路线和连续位置的笛卡尔积；约束过滤后的空间分布不承诺严格均匀。
- 新值注入无需与旧随机生成的不同场景逐位相等；逐位要求适用于相同固定规格的不同运行配置，以及关闭注入的回归。
- 原值 schema 2 双卡成功、schema 3 单卡完整对拍和当前在途原值并行校准，均不能代替本方案的新值并行证据。
- 未实际发生的规划回退、C++ 随机分支、其他硬件／驱动组合不算已覆盖。
- 图表生成不等于逐图目视完成，视频文件存在不等于已人工观看；有实际复核时记录查看对象与结论，否则写未目视。
- 原 HDF5 没有记录的事件不能伪造对应图像；状态事件证据与视频证据分别说明覆盖范围。
- 本次只读锚点核查没有生成新规格、测试注入、测量新值性能或验证本计划新增命令。

### 七、留档与提交纪律

重产物按 `artifacts/injection/<运行编号>/` 存储，规格为 `specs/<任务>/<难度>.json`，生成结果为 `<阶段>/<运行配置>/<任务>/<难度>/`；每个 episode 和每次重复执行另有身份记录。图表、原始观察器证据、HDF5 和视频留在该运行根目录，主日志位于 `artifacts/logs/`。不同难度、配置或重复运行绝不写同一输出目录。

轻量包拟放 `docs/validation/newtask-v2/<运行编号>/`：中文 `README.md`、11 份规格及规范化散列、全量／前 10 计数表、静态拒绝清单、110 行唯一样本结果、64 次校准记录、命令与退出码、HDF5 全字段聚合指纹、动作绑定摘要、资源／时间区间、环境与源码指纹、完整清单散列。轻量不表示只留成功条目；没有 HDF5 的失败也必须能定位到规格与错误阶段。

提交前按 `AGENTS.md` 强制规则第 7 条检查状态，只暂存本轮明确路径；同文件有他人 hunk 时只暂存本轮差异，不 stash 或回退。中文提交正文保存用户原话、完整计划、实施过程、意外、命令／实测数字／退出码及下一步。文档引用使用文件与稳定符号，不使用代码行号；HDF5、PNG、视频和完整日志不纳入提交。只有后续实际完成对应阶段，才更新第一部分实测追加区、`scripts/README.md` 与账本的执行状态。
