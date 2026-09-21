# 全环境配置拆分与原始 train 对拍方案

> 本方案以用户本轮要求为准，只规划，不实施。工作副本为 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，核验代码为 `a4a6e9fab630e9399ca538ab2cc9d008e9638713`，当前分支为 `newtask-v2.1refractor`。本轮只新增本文件、更新必要账本并提交，提交编号接续 `11.19`；不创建分支。**方案之后开始实施时，先从包含本方案的提交切出用户指定的 `newtaskRelease-v3`，再改代码。**
>
> 新分支的第一轮目标是：**十六个环境都能显式传入 `sampling_config` 与 `episode_spec`，按官方原始 train 的 16×100＝1600 条实际身份重放，与官方 `dataset-gen` 分支的生成及测试结果对拍，保留其中的 fail recover，证明注入前后保持一致。** 权威来源固定为 [RoboMME/robomme_benchmark 的 dataset-gen 分支](https://github.com/RoboMME/robomme_benchmark/tree/d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa)，本轮核验提交 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`；既有测试报告另记录其实际运行提交，见第三节。本文列出的更难布局、更多物体、更多动作及视频时长要求，只决定接口要留出什么能力，第一轮全部不启用。`src/robomme/` 的每一项源文件改动和运行时覆盖仍须按 [AGENTS.md](AGENTS.md) 强制规则第 11 条逐项批准，录像器保持冻结。

## 一、这次拆什么，先固定什么

一句话方案：**`sampling_config` 固定“怎么抽”，`episode_spec` 固定“这一局抽到了什么、接下来操作谁”；先把原始值完整地拿出来、原样放回去，再考虑改值。**

例如 `PickXtimes` 的原始 hard 是三种颜色、抓放次数从 4～5 抽取，这是 `sampling_config`；某条 train 记录实际生成了哪些方块、目标是哪一块、抓放了几次、按钮和方块分别在哪里，这是 `episode_spec`。本阶段仍然是原来的那一局，不把次数改成用户未来希望的 6～15。

当前 [scripts/README.md](scripts/README.md) 的「一、固定了哪些」只覆盖 `BinFill`、`RouteStick`、`VideoUnmaskSwap`、`VideoRepick` 四个环境。现行 [native_sampling.json](scripts/configs/newtask-v2/native_sampling.json) 是 schema 3，当前候选规格是另一套 schema 1；**“已经有两个参数”不代表已经支持原始 train 逐条回注**，更不代表另外十二个环境已经接入。本方案把覆盖面扩大到全部十六个环境。

固定范围分四层，下面每个环境都按相同的四项说明：

1. **数量与任务规则**：颜色池、物体数、目标数、重复次数、交换次数、路线长度及难度分支；次数与物体数量分别命名。
2. **布局与外观**：采样区域、锚点、坐标运算、姿态、颜色、物体创建顺序；`episode_spec` 保存每个对象的稳定编号和实际输入位姿。
3. **动作与对象绑定**：目标列表、抓放顺序、藏物容器、交换双方、路线节点与方向、演示后的回放位置、失败恢复选中的动作。
4. **运行中的随机过程与时间**：构造、每次初始化和延迟事件各自的抽样顺序；速度、事件窗口和原有等待。原始输入是配置，实际事件与帧范围是规格或运行证据，不能用运行后的测量结果反过来改变这一局。**fail recover 按官方 `dataset-gen` 入口保留：每环境 episode 0～2 为 z，3～5 为 xy，6～99 关闭**；模式和实际被选中的失败动作都纳入规格及对拍。

所有区间都保留原 API 语义：难度字典中的 `min/max` 常由 `torch.randint(min,max+1)` 消费，含两端；源码直接写的 `torch.randint(a,b)` 不含 `b`。保留原运算次序、Python 标量和张量 dtype，例如不把 `0.15 + (u×0.2−0.2)` 改写为 `−0.05 + u×0.2`。尺寸、相机、控制器、求解器、成功阈值和录像协议只记录来源指纹，本阶段不开放新的行为。

## 二、逐环境：约定、固定值和未来接口

本节中的原值来自现行源码与官方固定提交的核对；其中需要恢复到官方原版的差异单独指出。**表中的拟新增字段是接口设计，当前还不存在；它们不是已经落地的新配置。** easy／medium／hard 按官方 metadata 选择，每环境 50／25／25，不重新分配难度，不新增 xhard 样本。

### 2.1 BinFill

**约定**：① 总生成数、颜色数、投入总数、投入颜色数是四件事；② 开局全出现与更密集的 clutter 分开；③ 每块方块与孔板明确绑定；④ 初始化和执行时的颜色顺序分别固定。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 数量 | easy：颜色 1、生成 4～6、投入色数 1、投入 1～3；medium：2、8～10、1～2、2～4；hard：3、10～12、2～3、3～5 | 每色生成数、每色投入数、选中的颜色池、实际投入总量；保留原来目标色可分得 0 块的情况 |
| ② 布局 | `dynamic=bool(randint(0,2))`；方块中心 `[-0.1,0]`、半边长 `[0.2,0.25]`、随机 yaw；按钮中心 `[-0.2,0]`、扰动 `[0.1,0.4]`、scale 1.5 | dynamic 值、全部方块创建顺序／颜色／位姿、按钮位姿；不只存最终计数 |
| ③ 投入对象 | 孔板基位 `[0.15,0,0]`；偏移 `x=u×0.2−0.2`、`y=u×0.4−0.2`、yaw `u×40−20` 度；板边 0.1、孔边 0.08、厚 0.05 | 孔板完整姿态、每一步 `pick` 的方块 ID 与 `put_in` 目标；任务执行必须实际使用该顺序 |
| ④ 生命周期 | 保留 `__init__`、`_load_scene`、每次 `_initialize_episode` 的随机源和顺序 | 两次初始化分别保存颜色排列、出现次序、恢复注入动作；不能两次共用一个排列 |

**未来接口与值**：总块数 12、颜色 3、投入总数 `[5,7]`；增加独立 `layout_mode=clutter`，需要开局全部出现时由该模式明确映射 `dynamic=False`。clutter 的密度不由 dynamic 推导；`put_in_color` 未指定，保留为独立配置，不擅自定成 3。本阶段保留上表原值。

锚点：[BinFill.py](src/robomme/robomme_env/BinFill.py) 的 `NATIVE_SAMPLING`、`BinFill::__init__/_load_scene/_initialize_episode`。现有规格分支仍有 `color_pool/put_in_color` 未冻结抽样，`actions` 也不能只写进文件而不核验真正消费。

### 2.2 PickXtimes

**约定**：① `number` 是抓放循环数，方块数单列；② `target_cube` 与放置圆盘 `target` 分开；③ 每个对象有独立颜色和角色；④ 抓放循环及末尾按钮都固定。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 颜色与次数 | easy：颜色 1、循环 1～3；medium：颜色 3、循环 1～3；hard：颜色 3、循环 4～5；选中颜色各 1 块 | 实际颜色列表、全部方块、`num_repeats` |
| ② 布局 | 方块与圆盘中心 `[-0.1,0]`、半边长 0.2；方块随机 yaw；圆盘半径 `2*cube_half_size`；按钮中心 `[-0.2,0]` | 方块／圆盘／按钮完整位姿，以及最终目标方块 ID |
| ③ 角色 | 原红蓝绿颜色表、洗牌与目标索引抽法 | `target_cube_id`、`non_target_ids`；保留先抽目标颜色又被方块选择覆盖的随机消费 |
| ④ 动作 | 反复“抓同一目标块→放到圆盘”，最后按按钮 | 完整有序动作列表与恢复动作索引 |

**未来接口与值**：颜色 3、循环 `[6,15]`；独立 `target_cube_position_policy`、`goal_position_policy` 与 `distractor_color_palette/count`。用户“target 生成的位置尽可能推向边角”未区分方块和圆盘，方案同时预留两个位置接口，未来启用前明确移动谁；本阶段两个都保留原位分布。“其他颜色”的颜色池与数量也不擅自赋值。

锚点：[PickXtimes.py](src/robomme/robomme_env/PickXtimes.py) 的 `config_*`、`__init__`、`_load_scene`、`_initialize_episode`。

### 2.3 SwingXtimes

**约定**：① 一轮为右、左各一次；② 方块和两处摆动目标分别冻结；③ 干扰物不参加目标动作；④ 左右按实际位置绑定。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 轮数 | easy：颜色 1、轮数 1～3；medium：3、1～2；hard：3、3；`max_swings=2*num_repeats` | 实际轮数及左右共几次，不把轮数写成方块数 |
| ② 布局 | 方块中心 `[-0.1,0]`、半边长 0.25；左右区域中心 `[-0.1,-0.2]`／`[-0.1,0.2]`、半边长 0.1；按钮中心 `[-0.2,0]` | 全部对象、颜色、目标方块、两个落点与按钮位姿 |
| ③ 选择 | 红蓝绿洗牌，每色 1 块；保留两次目标选择的原随机消费 | 最终目标与非目标 ID 列表 |
| ④ 动作 | 按实际 y 排左右；摆动高度 0.1；原判断阈值 `distance=0.03,z=0.12` | 按右→左展开的完整循环及左右对象绑定 |

**未来接口与值**：轮数 `[4,10]`，对应左右落点总次数 `[8,20]`；增加其他颜色干扰物配置，数量和颜色池待未来指定，生成后须同步 `non_target_cubes` 及原失败判定。本阶段轮数、颜色和动作高度不变。

锚点：[SwingXtimes.py](src/robomme/robomme_env/SwingXtimes.py) 的 `config_*`、`__init__/_load_scene/_initialize_episode`。

### 2.4 StopCube

**约定**：① 速度档与停止第几次经过目标分开；② 运动路线与目标一起固定；③ 完整运动段列表可表达；④ 保留准备动作与运动窗口的对应关系。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 速度与次数 | 无有效难度字典；`move_interval∈{60,80,120}`；`stop_time=randint(2,6)`，即第 2～5 次 | 选中的速度档、实际 stop_time |
| ② 路线 | 目标 xy 各在 `[-0.1,0.1]`；路线 `[0,-0.3]→[0,0.3]`，整体旋转 ±30° 后平移至目标；块色为随机 RGB | 起终点、目标、按钮、RGB 和完整姿态 |
| ③ 运动段 | `step` 当前只循环 `range(5)` | 五段实际方向、起止步及停止所在段 |
| ④ 时间 | `steps_press=move_interval*stop_time-move_interval/2`；准备提前量 30 | 每个停止／准备窗口；保留先 `randint(27,33)` 再覆盖为 30 的随机消费 |

**未来接口与值**：最快现有档 `move_interval=60`，`stop_time=[6,15]`；另留 `motion_segments`，未来必须覆盖到选中的第 15 次，否则只改次数会得到不存在的运动窗口。本阶段仍从三档抽取、只用原五段。

锚点：[StopCube.py](src/robomme/robomme_env/StopCube.py) 的 `_load_scene/_initialize_episode/step/evaluate`。

### 2.5 VideoUnmask

**约定**：① 容器总数与拾取数分开；② 容器布局与藏物映射分开；③ 颜色与干扰角色分开；④ 展示和拾取使用明确列表。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 数量 | easy：3 容器、拾取 1；medium：5、1；hard：15、2 | 实际容器数、拾取数、目标容器顺序 |
| ② 布局 | 中心 `[0,0]`、半边长 0.2、间距 0.04、最多 256 次位置尝试、自转 `u×90` 度 | 每个容器和藏块的完整位姿、创建顺序、空容器列表 |
| ③ 藏物 | 前 3 个容器各藏红／绿／蓝一块，颜色 `randperm(3)`；块半边长 `cube_half_size/1.2`、yaw 0 | 颜色→方块→容器的完整映射 |
| ④ 动作 | 展示升降窗口 `[0,64]`；先抓 `bin_0`，pick>1 时再抓 `bin_1` | 展示对象列表、每次抓取的容器及其中方块 ID |

**未来接口与值**：`pick_count=3`、clutter bin、其他颜色 distractor；独立配置容器布局、容器数量、藏物与干扰物。现有代码最多构造两抓，`step` 又只遍历 15 个容器；第一轮只把原列表显式化，未来再扩展第三抓和展示列表。干扰物放在容器内还是桌面上、clutter 的容器数量和密度留待未来明确。

锚点：[VideoUnmask.py](src/robomme/robomme_env/VideoUnmask.py) 的 `config_*`、`_load_scene`、`step`。

### 2.6 ButtonUnmask

**约定**：① 原数量沿自身难度字典；② 按钮纳入布局避让；③ 固定藏物、空容器和目标身份；④ 按钮触发机制保留。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 数量 | easy：3 容器、拾取 1；medium：5、1；hard：15、2 | 容器数与抓取顺序 |
| ② 布局 | 容器中心 `[0,0]`、半边长 0.2、间距 0.04；按钮中心 `[-0.2,0]`、扰动 `[0.1,0.1]`、scale 1.5 | 全部容器、藏块、按钮位姿和创建顺序 |
| ③ 藏物 | 前三容器各藏一块，原三色排列；其余为空 | 具体颜色／藏块／容器映射、空容器与非目标集合 |
| ④ 动作 | 按按钮，再按原逻辑抓第一／第二个容器；原升降窗口不变 | 按钮动作和抓取对象的有序列表、真实展示窗口 |

**未来接口与值**：`pick_count=3`、clutter bin、其他颜色 distractor；保留与 `VideoUnmask` 不同的按钮触发入口。第三抓、干扰物数量／位置与容器布局算法均不在原值阶段启用。

锚点：[ButtonUnmask.py](src/robomme/robomme_env/ButtonUnmask.py) 的 `config_*`、`_load_scene/_initialize_episode/step`。局部 `generator` 与恢复分支 `self.generator` 的关系需要在原 train 样本实测，不为切接口顺手改错。

### 2.7 VideoUnmaskSwap

**约定**：① 容器、交换、拾取三种数量独立；② 布局与颜色映射完整保存；③ 每次交换固定双方；④ 交换速度与次数分开。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 数量 | easy：3 容器、swap 1～2、pick 1～2；medium：4、1～2、1；hard：4、2～3、2 | `n_bins/n_swaps/n_picks`、拾取有序列表；现行 xhard 不进入原 train |
| ② 布局 | 三点三角／直线或四点锚点；整体旋转 `[0,180]` **弧度**；局部半边长 0.07、间距 0.02、自转 `u×90` 度 | 每个容器位姿、颜色顺序、藏物／空容器、目标选择 |
| ③ 交换绑定 | 三名原始发起者；开始交换时按实际 XY 选最近搭档，排除自身，等距按创建顺序 | 每次 `initiator_id/partner_id`、当时位置与距离、藏块跟随映射 |
| ④ 时间 | 第 k 次交换窗口 `[64+50k,64+50(k+1)]`；`lane_offset=0.07,smooth=True,keep_upright=True` | 完整窗口和轨迹输入；实际帧边界另留证据 |

**未来接口与值**：swap `[8,12]`、pick 3、其他颜色 distractor、速度倍率 1.5。留 `swap_count_range`、`pickup_order`、`swap_pairs`、`swap_speed_multiplier` 与统一时间表；原值阶段倍率为 1。`50/1.5` 不是整数，未来需统一时间离散策略，不能一处取 33、另一处取 34。不能自动沿用 xhard 三发起者循环作为新需求的唯一交换规则。

锚点：[VideoUnmaskSwap.py](src/robomme/robomme_env/VideoUnmaskSwap.py) 的 `NATIVE_SAMPLING`、`__init__/_load_scene/_initialize_episode/_refresh_swap_schedule/step`。现有 `target_choice` 仍随机抽取、容器循环仍读难度字典；本阶段须让数量、目标和实际动作真正受统一规格约束。原 `randperm(3)` 只向前三容器藏三色，四容器档的第四个为空；前两名交换发起者存在将 selected 局部下标直接用于生成列表的历史行为，按基线结果保留，不在切接口时纠正。

### 2.8 ButtonUnmaskSwap

**约定**：① 三种数量独立；② 两个按钮与本环境自己的布局算法固定；③ 交换与藏物映射固定；④ 两按钮的操作顺序固定。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 数量 | easy：3 容器、swap 1～2、pick 1～2；medium：4、1～2、1；hard：4、2～3、2 | 实际容器数、交换数、抓取数 |
| ② 布局 | 按钮中心 `[-0.2,0]`／`[-0.2,0.1]`、扰动各 `[0.05,0.05]`；容器局部半边长 0.07、间距 0.02；三点各加独立 x 偏移，四点分组加 y 偏移；没有生效的整体旋转 | 两按钮与容器位姿；所有原随机偏移，包括抽取后未使用的布局分支 |
| ③ 绑定 | 原颜色排列／藏物排列、发起者、运行时最近搭档 | 容器、藏块、目标、每次实际交换双方 |
| ④ 动作时间 | 按钮操作顺序右→左；每次交换原 50 步，原路径参数不变 | 两按钮动作、全部交换窗口、拾取顺序 |

**未来接口与值**：swap `[6,8]`、pick 3、其他颜色 distractor、速度倍率 1.5。`_refresh_swap_schedule` 当前只有 1／2／3 分支；`pick_times==2` 才加第二抓，直接设 3 反而只剩第一抓。因此先切完整序列接口，未来再增次数，不以修改几个数值宣称功能就绪。

三角基位为 `[[-0.05,-0.15],[-0.05,0.15],[0.05,0]]`，直线第三点改为 `[-0.05,0]`；四点基位为 `[[0,-0.1],[0,0.1],[0.1,0.1],[0.1,-0.1]]`，上述 x／y 随机偏移幅度均为 `u×0.1`。前三容器藏物、第四容器为空，以及 selected 局部下标用于生成列表的历史行为，同样按原结果保留。

锚点：[ButtonUnmaskSwap.py](src/robomme/robomme_env/ButtonUnmaskSwap.py) 的 `config_*`、`__init__/_load_scene/_initialize_episode/_refresh_swap_schedule/step`。

### 2.9 PickHighlight

**约定**：① 场上块数与高亮块数独立；② 每块颜色独立；③ 高亮序列与抓取序列绑定；④ 高亮时间固定。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 数量 | easy：生成 3、高亮 1；medium：4、2；hard：6、3 | 实际生成数量、有序高亮目标列表 |
| ② 外观与位置 | 每块从红／蓝／绿独立抽色；中心 `[-0.1,0]`、半边长 0.2、随机 yaw、间距 `2*cube_half_size`；按钮中心 `[-0.2,0]` | 每块颜色／姿态、按钮位姿与创建顺序 |
| ③ 对象选择 | `randperm` 选目标；原目标／非目标失败规则 | 高亮 ID、抓取／放下 ID、非目标集合 |
| ④ 时间 | 高亮发生在 step 10～100 | 每个高亮事件与动作边界 |

**未来接口与值**：clutter、高亮数 `[5,7]`、block 颜色任意；独立 `spawn_count`、`highlight_count` 与逐物体颜色。未来生成数至少能容纳 7 个目标，但用户未指定场上总块数，不擅自定成 7 或其他值。当前生成失败会中断后续生成，原值回注保存实际数量，不悄悄补块。

锚点：[PickHighlight.py](src/robomme/robomme_env/PickHighlight.py) 的 `config_*`、`_load_scene`、`step`。

### 2.10 VideoRepick

**约定**：① clutter、交换开关、交换数分别表达；② 重复抓放与块数分开；③ 每块可有独立颜色；④ 保留同一目标对象和完整演示／执行绑定。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 模式与数量 | easy：3 块、swap 1～2；medium：3 块、swap 2～3；hard：红蓝绿各 5 块，共 15 块、swap 0 | 实际物体列表与交换数；hard 必须有完整规格 |
| ② 次数 | `num_repeats=randint(1,4)`，即 1／2／3 | 实际重复抓放次数、每次目标 ID |
| ③ 颜色与布局 | 非 hard 三块同色，原锚点、整体旋转、半边长 0.07；hard 每轮三色洗牌，中心 `[-0.1,0]`、半边长 `[0.2,0.25]` | 逐块颜色／姿态、按钮、创建顺序、目标方块与非目标列表 |
| ④ 动作 | 原发起者顺序、运行时最近搭档、每次 50 步窗口、原重复抓放 | 完整交换双方、动作序列和两次初始化结果 |

**未来接口与值**：clutter、抓放 `[4,6]`、逐块颜色任意；若启用 swap，次数 `[8,12]`。`layout_mode` 与 `swap_enabled` 必须拆开，才能表达 clutter＋swap。当前 `difficulty==hard` 把 clutter 和零交换绑在一起，现有 `_repick_group` 甚至拒绝 hard；第一轮先补齐原 hard，不能用三块 xhard 替代十五块 hard。

锚点：[VideoRepick.py](src/robomme/robomme_env/VideoRepick.py) 的 `NATIVE_SAMPLING`、`__init__/_load_scene/_initialize_episode/_refresh_swap_schedule/step`，以及 [specs.py](scripts/injection/candidates/specs.py) 的 `_repick_group`。

### 2.11 VideoPlaceButton

**约定**：① 方块、目标台、演示对象三种数量独立；② 按钮前后语义保留；③ 每块演示动作独立；④ 出生原位与随机 `goal_site` 明确区分。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 数量 | easy：1 块、3 台；medium：3 色各 1 块、4 台；hard：3 色各 1 块、4 台；三档 `additional_place=False` | 每块／台／按钮／goal_site 位姿和颜色、唯一目标方块 |
| ② 任务语义 | 随机 before／after | 具体答案、前后台绑定 |
| ③ 演示 | 当前同一块依次放 target_0→按按钮→放 target_1→放随机 goal_site | 完整演示列表和执行目标 |
| ④ 交换与重置 | 仅 hard 交换两块目标台，50 步 | 交换台 ID、窗口、每块演示开始位姿及原重置位置 |

**未来接口与值**：视频里完成 2 个 block，各自放回原位，其余不变；预留有序 `demo_objects`、每对象 `demo_actions`、`return_pose_by_object_id`。原位必须逐块保存，不能拿同一个 `goal_site` 当两块的原位。easy 原来只有 1 块，与“两块且其余不变”存在数量冲突，未来明确适用档位或增块规则后再启用；本阶段仍保留单块演示。改变的是视频对象数和回位，其他按钮前后语义、目标台、交换规则不随之重设计。

布局原值一并外提：方块和目标台中心 `[0,0]`、半边长 0.2，方块随机 yaw；按钮中心 `[0.1,0]`、扰动 `[0.05,0.3]`、scale 1.5；`goal_site` 中心 `[-0.1,0]`、半边长 0.1、半径 `3*cube_half_size`。锚点：[VideoPlaceButton.py](src/robomme/robomme_env/VideoPlaceButton.py) 的 `config_*`、`_load_scene`、`_initialize_episode`、`step`。

### 2.12 VideoPlaceOrder

**约定**：① 方块与目标台数量独立；② 台的有序列表固定；③ 每块的演示、答案和按钮插入位置独立；④ 每块原位独立。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 数量 | easy：1 块；medium／hard：3 色各 1 块；三档均 4 台 | 方块／目标台／按钮／goal_site 列表与位姿 |
| ② 次序 | 随机选 2～4 个有序目标台；随机选第几个为答案 | 台 ID 序列、`which_in_subset` |
| ③ 演示 | 随机选一块；按钮插入位置随机；该块经过有序目标台后放随机 goal_site | 目标块 ID、`button_task_index`、完整演示与执行动作 |
| ④ 交换与重置 | hard 交换两块目标台，50 步 | 交换台 ID、窗口、每块演示开始位姿和原重置位置 |

**未来接口与值**：视频完成 2 个 block、各自回出生原位，其余不变；每块保存自己的有序台列表、答案、按钮位置及回位映射。easy 单块的冲突同上一环境，未来单独决定；本阶段不改台数、不改按钮逻辑、不增加第二演示块。

布局原值一并外提：方块和目标台中心 `[0,0]`、半边长 0.2，方块随机 yaw；按钮中心 `[0.1,0]`、扰动 `[0.05,0.3]`、scale 1.5；`goal_site` 中心 `[-0.1,0]`、半边长 0.1、半径 `5*cube_half_size`。锚点：[VideoPlaceOrder.py](src/robomme/robomme_env/VideoPlaceOrder.py) 的 `config_*`、`_load_scene/_initialize_episode/step`。

### 2.13 MoveCube

**约定**：① 演示与执行有两套布局；② 杆与方块分别定位；③ 杆姿态与执行方法分别配置；④ 原拒绝采样与随机消费保留。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 两套布局 | 演示和执行各抽一次；goal 区域半边长分别 0.15、0.1 | `demo_layout` 与 `execution_layout` 的杆／cube／goal 全部位姿 |
| ② 区域 | 杆 x±0.05，y 在 ±0.2 上扰动 ±0.05；cube 候选中心 xy 为 `u×0.2−0.1`，距 goal 大于 `5*cube_half_size` 后在半边长 0.05 区域生成 | 位置输入、最终接受位置和拒绝序列 |
| ③ 姿态与方法 | 杆 length 0.1、radius 0.01、yaw±45°；`way` 从 `peg_push/gripper_push/grasp_putdown` 选择 | 两套杆完整姿态、实际 way、目标对象和执行动作 |
| ④ 随机流 | length／radius 各先随机再乘 0；difficulty 不控制布局 | 原抽样消费、每次初始化与 reset 切换身份 |

**未来接口与值**：cube 和 stick 尽可能靠边角，杆转角更大、更难抓。分别预留演示／执行的边角策略、可行域、杆 yaw 范围；不擅自把三种方法改成只允许抓杆。`build_peg` 的长轴本来就在桌面平面内，当前只加 yaw，已经与桌面平行；若未来要的是新增俯仰姿态，需明确角轴和范围，不能误把现有平面姿态当作尚未支持。

锚点：[MoveCube.py](src/robomme/robomme_env/MoveCube.py) 的 `_load_scene/_initialize_episode/step`；[object_generation.py](src/robomme/robomme_env/utils/object_generation.py) 的 `build_peg`。

### 2.14 InsertPeg

**约定**：① 杆数与目标杆独立；② 孔位与所有杆的位置分别冻结；③ 干扰杆与目标杆的相对关系可表达；④ 姿态和碰撞约束分开。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 对象 | 3 根杆；length 0.05、radius 0.01；目标索引随机抽后强制改为 0 | 三根杆 ID、目标 `peg_0`、共享头色 RGB 和互补尾色；保留被覆盖的抽样 |
| ② 孔与布局 | 孔 xy±0.1、yaw 90°±20°；每杆 x±0.2、y±0.3、yaw±45° | 每次 `_initialize_episode` 的孔与三杆完整位姿，不只保存构造临时位置 |
| ③ 距离 | 杆距孔 >0.06，杆间距离 >0.075，最多 512 次 | 实际距离、接受顺序和全部拒绝消费 |
| ④ 生命周期 | 尺寸先抽样再乘 0；每次 reset 原顺序不变 | 随机源状态、每次重置的杆列表和任务绑定 |

**未来接口与值**：多生成一根，即总共 4 根，其中新增干扰杆更靠近 target stick；转角更大。预留 `peg_count`、`target_peg_id`、`near_target_distractor` 的相对距离／方位，以及 yaw／完整姿态输入。“更近”没有给具体距离，不能擅自降低原 0.075 间距或放宽碰撞。当前杆已与桌面平行，俯仰需求与 `MoveCube` 同样需未来明确。

锚点：[InsertPeg.py](src/robomme/robomme_env/InsertPeg.py) 的 `_load_scene/_initialize_episode`，`object_generation.py::build_peg`。

### 2.15 PatternLock

**约定**：① 网格与路线长度独立；② length 表示节点数；③ 演示与执行复用同一路径；④ 视频秒数以实际录制段测量。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 网格 | easy：3×3；medium：4×4；hard：5×5；中心 `[-0.1,0]`、间距 0.1 | 所有节点位姿与创建编号 |
| ② 路线 | 节点数 easy 2～4、medium 3～5、hard 4～8；随机起终点；允许对角线的随机 DFS；最多 1000 次，耗尽沿用最后一次 | 起终点、完整节点序列、抽样／拒绝过程、是否用最后一次兜底 |
| ③ 动作 | 演示与执行按同一节点列表；首目标保留原 NO RECORD 处理 | 各段对象绑定、高亮和阶段边界 |
| ④ 时间 | 原求解速度与等待不变；每目标由 `solve_swingonto` 调两次 screw 运动并关闭夹爪 | 实际演示帧范围、录制帧数、写出 fps；不由节点数臆算秒数 |

**未来接口与值**：最难情形的视频演示部分 20～30 秒；留 `demonstration_duration_policy` 和实际帧证据，不改变本阶段网格、路径、速度或尾迹。不用重复帧或修改 MP4 fps 冒充任务演示变长。

锚点：[PatternLock.py](src/robomme/robomme_env/PatternLock.py) 的 `config_*`、`_load_scene`、`step`；`utils/adjacent.py::find_path_0_to_8/dfs_path`。

### 2.16 RouteStick

**约定**：① length 表示运动段数，节点数比它多 1；② 网格位置与路线拓扑独立；③ 每段方向按原独立抽样；④ 演示时长由实际动作与录制共同确定。

| 固定项 | `sampling_config` 的原值／规则 | `episode_spec` 固定的本局结果 |
| --- | --- | --- |
| ① 路线 | easy：2～3 段、不主动回退；medium：4～5、不主动回退；hard：4～7、允许回退；端点强制反向 | 实际 L、L+1 节点、有序节点槽位、是否回退 |
| ② 几何 | 节点 `[0,2,4,6,8]`；中心 `[-0.1,0]`、间距 0.07；yaw `u×60−30` 度；四障碍柱 RGB 各独立抽样 | 实际节点／柱位姿、整体旋转、柱颜色 |
| ③ 方向 | 每段独立 `torch.rand(1)<0.5` | L 个顺／逆时针方向，演示与执行的绑定；不做跨 episode 配额 |
| ④ 事件 | 原曲线求解、末端保持及高亮时序；当前分支尾迹 10 步与历史 40 步需单列处理 | 完整路线事件、实际段边界与帧数；原 train 恢复核验不排除尾迹 |

**未来接口与值**：最难情形的视频演示部分 20～30 秒。保留 `route_length` 与 `demonstration_duration_policy` 两个接口；现行 xhard 的 8～10 段不是自动满足时长的保证。`solve_swingonto_withDirection` 每段有 45 个曲线点和 5 次末端保持，但 IK 失败可能跳点，不能直接说每段必为 50 帧。本阶段不延长路线，不加入“禁止连续三段同方向”的新值约束。

锚点：[RouteStick.py](src/robomme/robomme_env/RouteStick.py) 的 `NATIVE_SAMPLING`、`_load_scene/step`；`utils/route.py::generate_dynamic_walk`、`utils/subgoal_planner_func.py::solve_swingonto_withDirection`。

### 2.17 所有未来布局接口共同遵守的规则

边角策略要能描述目标对象、桌面可行域、边界退让和偏置强度；“尽可能靠边角”保留在可达且不穿模的原约束内，不等于把坐标直接放到桌沿。clutter 要能描述对象集合、空间范围与间距，不能只换名字。任意颜色与其他颜色干扰物分别配置：前者不再用颜色当唯一身份，后者必须明确相对哪个目标颜色池。

所有视频任务都留独立的演示对象、动作序列、恢复位置与运行时间表，避免对象数量一增加就依赖 `if count==2`。但第一轮只表达当前原始序列，新增行为放到后续任务。PatternLock／RouteStick 的 20～30 秒按最终交付视频中实际演示帧计；当前 `RecordWrapper::_video_write_mp4` 为 30 fps，`save_robomme_video` 默认 20 fps，必须固定选用的产物和帧率，不能混算。若按现录像器交付，20～30 秒对应 600～900 个实际演示帧，这是未来验收范围，不是本阶段新增的录制行为。

## 三、原始 train 的身份与代码基线

### 3.1 逐条采用 metadata，不能只指定 `--layout train`

用户先明确「我说的是原始的[https://github.com/RoboMME/robomme_benchmark](https://github.com/RoboMME/robomme_benchmark) train16*100」，随后指定「[https://github.com/RoboMME/robomme_benchmark/tree/dataset-gen](https://github.com/RoboMME/robomme_benchmark/tree/dataset-gen)和这个branch的测试结果对拍」「这个里面也有fail recover」。因此**身份和生成行为均以官方 `dataset-gen` 为准**，固定本轮联网核验提交 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`；不把本地 fork 的扩展 metadata 或官方 main 的无恢复 Builder 路径当对拍基线。

实读官方十六份 JSON，每环境恰好 episode 0～99，共 **1600 条**，各环境 easy／medium／hard 为 50／25／25。官方 1600 条完整记录与当前各环境前 100 条的差异为 **0**；12 份文件全文字节相同，四个 Unmask 环境在本地扩为 400 条，只有记录扩展及 `record_count` 不同。本方案不使用扩展出的 1200 条，也不需要修改本地 `src` 下的 metadata；后续在 `scripts/configs/newtask-v3/official_train/` 单独保存官方十六份原文及来源散列。

官方 records 按 `scripts/seed_layout.py::ALL_TASKS` 的环境顺序、各文件原 records 顺序串接，以 `json.dumps(records, sort_keys=True, separators=(',', ':')).encode()` 计算，SHA-256 为 `a57655d601c7e974c688b2b5c3602e7eb8606e2bd312dcc4ba00a1abb29d73bf`。这 **1600 条中有 170 条**实际 seed 不等于 `SeedLayout.base_seed` 的 attempt 0 公式。例如 `BinFill/episode_3` 是 `difficulty=hard, seed=4301`，公式却是 `4300`。新增入口严格读取官方 `(task, episode, seed, difficulty)`；保留原记录，不重算 seed。运行尝试序号与官方历史 seed 分开记录，每条只运行该 seed 一次，失败不调用 `EpisodeJob.bump`、不换 seed、不补样本。

该分支的正式入口为 `scripts/data-generation/generate_dataset.py::generate_dataset/_worker`，按 metadata 的实际 seed、difficulty 各生成一次。`EpisodeJob.recovery_mode` 在每环境 episode 0～2 返回 z、3～5 返回 xy，其余返回 None；`_worker` 据此传 `robomme_failure_recovery=True` 和对应 mode。五路对拍必须保持这些参数及 `inject_fail_grasp` 真实选择相同，不能关掉恢复后宣称对齐。共 96 个任务身份配置恢复模式，其中 z、xy 各 48；是否实际触发及选中哪个动作，逐条记录，不仅比较这个开关。

现行 `generate_dataset_newseed.py` 默认按公式建任务，需要在 `scripts/` 侧增加严格官方清单模式，复用既有生成链路并与该分支逐函数核对：`_planner_classes` 的三次 screw 后三次 RRTStar 回退、`_execute_tasks` 的真实动作顺序、`_worker` 的恢复与录像参数、合并和 metadata 输出。原分支限定物理 GPU 0，历史全量为 20 worker；第一轮单 worker 对拍使用 GPU 0，之后另核验 20 worker 的结果，不改变其 seed 规则和 fail recover。

### 3.2 从 dataset-gen 原版到注入版，必须有两段证据

```text
dataset-gen 固定提交 + 官方 train 1600 条身份 + 原 fail recover
          │ 正常生成，重复两次：A1、A2
          ▼
新分支恢复后的默认路径 B
          │ 显式传原 sampling_config：C
          ▼
从 C 的原生过程导出完整 episode_spec
          │ 同一身份原值回注：D
          ▼
比较对象、动作、随机流、HDF5、图像及实际视频事件
```

`A↔B` 证明恢复到官方 `dataset-gen` 生成行为；`B↔C↔D` 证明接口拆分及原值回注没有改数。A1／A2 必须执行该分支的原 `_worker`、原求解与 fail recover 链；B／C／D 执行本分支接入后的链路，不能让两边都改用一套未验证的新生成循环。编排器只负责显式原身份、隔离输出与结果收集。只比较当前新代码的默认路径与注入路径，会漏掉继承下来的旧改动。例如 `RouteStick.py::step` 的白球尾迹当前为 **10 步**，该官方分支为 **40 步**；此项须单列审批恢复原值，不把 10 步冒充原始行为。

同样，第一轮必须关闭 `_binfill_demo_deliverable` 的轨迹复制，不消费 `injection_contract_v3.json` 的新值分布，不做跨 episode 的方向平衡，不按现行 400 条交付配额筛选样本，不把 `VideoRepick/hard` 替换成 xhard。现行碰撞检查新增的拒绝条件先作为只读诊断单列，不允许它们偷偷改变原 train 的保留集合；涉及环境内调用分支的调整也要逐项批准。原版的碰撞约束和任务失败规则继续执行。

官方文件通过仓库内隔离源码目录读取，A 路用独立进程加载官方固定源码，显式传官方 metadata 的 seed。本轮还用 Git blob 核对：官方的 **54 个 Python 源文件**与本地历史 `3a5951a834ea014f63724647ab0bc091eb9f109d` 完全相同，官方 `pyproject.toml/uv.lock` 也与该提交字节相同；此提交只可作为已验证的技术参考，不能替代官方身份来源。当前工作树、旧运行产物和官方数据都不覆盖。不能通过给 A 和 D 同时打补丁来制造一致，也不能把观察器接到冻结录像器上改变其行为。

### 3.3 当前已有证据和缺失证据

该分支已跟踪 [generation_report.json](https://github.com/RoboMME/robomme_benchmark/blob/d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa/scripts/data-generation/reports/generation_report.json) 和 [generation_report.md](https://github.com/RoboMME/robomme_benchmark/blob/d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa/scripts/data-generation/reports/generation_report.md)。既有报告标称运行提交 `9430e20bfcf59116d525778b60663520b22f63e6`、报告时间 `2026-07-15T04:14:21.522575+00:00`。**此标称 HEAD 不能单独作为完整运行源码**：该提交的校验器还限制 9 条，至 d53 才改成 100 条；父编排也改变了默认 worker 和 GPU 限制，而 `_worker`、`EpisodeJob`、求解与任务执行、合并、动作比较器、环境源码与锁均未变。因此本方案固定 d53 为可重跑源码，历史报告单独冻结其原文、参数与标称 HEAD，并登记运行源码来源不完整的边界，不把它写成 clean 9430e20 已可复现的结果。

**这份既有结果不是全通过**：1600 条全部成功生成，生成与官方 HDF5 结构错误均为 0；但 `joint_action` 对官方发布 HDF5 的比较记录 761885 个向量、6095080 个元素，其中 **217242 个元素存在非零差异**，10 条时间步集合不符，最大绝对差为 `0.007857919612339614`，超过原阈值 `1e-8`，报告 `status=failed`，完整验收未通过。`different_element_count` 统计的是 `delta!=0.0`，报告未提供“超过 1e-8 的元素总数”，不能混称。方案要保留并逐条对齐这些历史测试结论，不能为得到 PASS 先改阈值、关恢复或换样本。

历史十条时间步差异如下，它们都成功生成，差异是相对发布参考集而言：

| 环境／episode | dataset-gen 生成帧数 | 发布参考帧数 |
| --- | --- | --- |
| BinFill／11 | 576 | 584 |
| BinFill／94 | 590 | 628 |
| PickHighlight／3 | 648 | 652 |
| PickHighlight／38 | 347 | 369 |
| VideoPlaceButton／58 | 987 | 952 |
| VideoPlaceButton／83 | 999 | 996 |
| VideoPlaceOrder／46 | 1000 | 984 |
| VideoPlaceOrder／50 | 992 | 991 |
| VideoRepick／39 | 521 | 445 |
| VideoRepick／59 | 407 | 411 |

对照分三项：**历史结果对照**比较 A 的 1600 条身份、恢复模式、成功状态、逐条帧数与原报告；**注入前后对拍**使用 d53 重跑的 A1／A2，对 B／C／D 做严格比较；**发布参考集比较**用该分支原 `validate_generated_dataset_contract.py` 与 `compare_joint_actions.py` 重跑审查，比较逐条结果、失败位置及数值摘要是否出现新增漂移。原结果对发布 HDF5 的既有不一致，不等于新接口的注入差异；同样也不能只让汇总失败数相同就算结果对齐。历史报告实际保存到哪一层就比较到哪一层，新增运行保存全量逐值证据，不能虚构报告里没有的完整元素差异表。

当前工作副本**没有 `data/` 目录**，也没有 `artifacts/native-baseline/`；报告所指 `/data/hongzefu/robomme_benchmark-restore-DataGen/` 及其中生成、参考目录本轮检查也均不存在。历史报告和 32 文件散列清单可读，历史 HDF5 目前不可直接读取。主方案以 d53 独立重跑 A1／A2，并与现有历史报告所存结果逐条对照；历史原文件的全内容比较额外记 `HISTORICAL_ARTIFACT_PARITY=NOT_RUN`。若后续找到原文件，先核验清单再只读复制进本仓库追加比较，不冒称已完成。官方发布数据按报告 revision `a5e4e25ffe8af34f64944f9533d06455ce5f8337` 恢复至 `data/robomme_data_h5/` 后，才能重跑原发布集比较器。

历史 [原值对拍报告](docs/validation/newtask-v2/20260909-actions-v3/README.md) 记录四环境 15 格、60 次生成、2479.7 秒；它可用于估计成本，不能作为本次十六环境或完整规格回注的通过证据。[非布局差异审计](docs/validation/newtask-v2/20260912-train-nonlayout-audit.md) 已指出 seed、规格分布和模拟演示等区别，本轮又核对了相关现行源码。

当前依赖指纹：`uv.lock` 为 `ff0ffd847a55f77d61c3d11efe4ad11e8776534e044f0ddb2b22396d838fa5f3`，`pyproject.toml` 为 `d03537d6c77a8d8213bc881da6ac470b2d8a80cf5f883df587d9df634374db36`。官方对应指纹分别为 `983de83f7b22c98b96c3c25a39958b4f5920e3232cfaa209c89542ef5639ac03`、`bc2346e4526c2b5c2177fe5191710c81f883c21017d45928e615327cf29cb21a`。两锁的包名／版本差异只有当前新增 `pebble==5.2.2`。后续各路仍必须记录实际 Python、Torch、SAPIEN、ManiSkill、mplib、驱动及设备；本轮没有重建仿真环境，不能由锁文件指纹推出仿真已经可复现。

## 四、两个接口怎样组织，怎样保证原样回注

### 4.1 配置快照与每局规格分别负责什么

拟新增 `scripts/configs/newtask-v3/native_sampling.json`，完整覆盖十六环境。环境侧的原生配置是默认值来源，文件是从源码提取并校验的快照；不维护两套手填默认值。延续当前 `parameters[task]`、`positions[task]` 的结构，补充明确的 `actions[task]` 时间和对象选择规则。未知字段、缺字段、类型错误、跨任务规格、来源不匹配均直接报错。每任务解析结果深拷贝，禁止改类级字典造成连续 worker 污染。

拟用带版本的新记录保存完整 `episode_spec`，至少含以下内容：

| 字段 | 固定什么 | 不允许的替代 |
| --- | --- | --- |
| `identity` | `split=train`、task、原 episode、实际 seed、difficulty、metadata 散列、历史基线提交 | 从 episode 重新计算 seed 或 difficulty |
| `layout` | 对象创建顺序、稳定 ID、位置与完整姿态、目标区域、初始位置与演示后重置位置 | 只记最终画面，遗漏创建输入和第二次初始化 |
| `objects` | 颜色、目标／干扰物角色、容器藏物映射、实际数量与重复次数 | 只记数量，不记具体是哪几个对象 |
| `actions` | 抓放目标序列、交换双方、路线与方向、事件窗口、失败恢复动作索引 | 由颜色名称或最近对象再次猜目标 |
| `sampling_trace` | 按原调用阶段编号的随机源、调用签名、原始结果、拒绝尝试、调用前后状态指纹 | 只在结尾恢复 generator 状态，忽略中间随机消费 |
| `provenance` | 配置／源码／依赖／规格内容散列及数组 dtype、shape、编码约定 | 用四舍五入的浮点文本承诺逐位相同 |

数组记录原 dtype 与 shape，采用可无损往返的表示；浮点比较按原始位模式，Python 标量保留原类型与运算次序。坐标以米计，角度字段必须明确度或弧度，四元数明确原 API 分量顺序。这里没有训练模型或可训练参数，不能用张量形状一致代替仿真行为一致。

逐局唯一数据文件仍采用 Git 跟踪的 `candidates.jsonl`，但为原始 train 新增显式版本和 `identity_source=train_metadata`。它只是承载固定记录，**不能复用旧封套的公式 seed、100 条 block、train/test 配额和碰撞必须 PASS 规则**。`scripts/injection/candidates/io.py::validate_candidates` 当前把这些规则写死，必须按版本分流校验；旧运行十保持原版本和原字节。生成、reset 核验都从同一记录投影参数；未来策略端若接入也消费同一身份，不另手填 seed。候选导出失败的身份保留在全集账本中，不伪造完整规格。

### 4.2 第一轮只接受原值回注，随机调用仍走原位置

采用“原生抽样、原位记录、严格回注”的方式：把原调用点的抽样结果显式化；D 路仍按原次序调用原随机源，以已记录规格作为实际消费值，并逐项核验原生抽样与冻结值相等。拒绝采样的失败尝试、单候选抽样、被后续语句覆盖的抽样也全部保留。只读导出不得再调用一次 RNG，也不得再执行一次物理 step。

```text
原来：原 generator → 原调用点抽样 → 建对象／生成动作
导出：原 generator → 同一调用点抽样 → 只读记下结果 → 原对象／动作
回注：原 generator → 同一调用点抽样 → 对照记录并消费冻结值 → 同一对象／动作
```

这不是减少抽样次数的优化；目的是第一轮同时做到完整冻结、原始随机流不漂移。一个 `(阶段, 初始化序号, 对象ID, 事件序号)` 只消费一次对应记录。交换搭档在交换发生时才知道的，导出完整运行中当时的实际绑定；D 路在同一时点核验并使用该绑定，不在构造时按初始坐标重选。第一次导出必须完成相关事件后才能把规格标为完整。

特别要覆盖 `BinFill` 两次初始化各自的颜色排列、`VideoRepick/hard` 的十五块原生路径、`InsertPeg` 乘零却仍消费随机数的尺寸抽样、被强制改为 0 的目标索引抽样，以及 `inject_fail_grasp` 的真实选择。现有“注入后跳过一部分抽样”分支不能直接沿用为 D 路。

未来更改数量、布局和动作次数后，原生抽样结果当然可能不同；届时另开明确的新值模式，由新配置生成新规格。第一轮只预留版本、字段和验证分支，不实现角落加权、额外干扰物生成、三次抓取、多对象视频或时长调节算法；也不把未来新值的随机流称为与原 train 相同。

## 五、怎样对拍，什么才算完成

### 5.1 每条身份走五次独立生成

| 路径 | 输入 | 比较目的 |
| --- | --- | --- |
| A1、A2 | 固定 `dataset-gen` 源码＋官方 metadata＋原 fail recover | 独立重跑该分支原 worker；先检查自身是否可重复，并与可取得的历史成品及报告比较 |
| B | 新分支恢复后的默认值，不传两个接口 | 与 A1 比，定位历史行为未恢复的差异 |
| C | B＋显式原值 `sampling_config`，只读导出规格 | 与 A1、B 比，证明配置外提不改值 |
| D | 同一配置＋C 导出的原值 `episode_spec` | 与 A1、C 比，证明对象、动作及随机流回注一致 |

各路使用同一物理 GPU、单 worker、相同求解器配置，单条失败保留原身份。A1／A2 若因 RRT 回退等因素不逐位一致，该条列为 `BASELINE_NONDETERMINISTIC`，不能偷偷设置新种子、给 A 加补丁或自动放宽容差。各路同样失败也不能写成“该样本成功生成”，只能作为失败分类一致。

先选 `BinFill/easy/episode_0` 做单任务、单 episode、单 worker 冒烟，保留该条 z 恢复；检查每个阶段退出状态，再扩到十六环境各一个原始 episode。随后覆盖全部 48 个 task／difficulty 格及实际分支：`BinFill` 两种 dynamic、`VideoRepick/hard`、单双拾取、零／非零交换、延迟搭档选择；每环境原 episode 0～5 全部纳入，覆盖 z／xy 的原恢复选择，另选恢复关闭样本。用例只能从官方固定身份中选；未出现的分支列出覆盖缺口，额外构造测试不能冒充 train 数据。

完整 train 的验收分母固定 **1600 条**，A1／A2／B／C／D 共 **8000 次生成**。这是方案中的工作量，不是本轮已经执行的数量。48 格验证和全集验证是两个状态：通过子集只能报告子集通过；任一未完成、不可比或异常条目都留在全集分母，不能据此宣布 1600 条逐位一致。

### 5.2 具名判据

| 查什么 | 怎么查、为什么能证明 | 通过判定行 |
| --- | --- | --- |
| 原身份完整 | manifest 与官方固定 metadata 逐条双向比较；拒绝重复、漏项、额外项和实际 seed 被公式替代 | `TRAIN_IDENTITY=PASS tasks=16 rows=1600 mismatch=0` |
| 配置外提完整 | 十六环境配置键映射到源码消费点；原运算元、dtype、区间边界及有效／死字段分别核查 | `SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0` |
| 规格完整且真正消费 | 逐局比对象 ID、布局、目标、动作、恢复和初始化编号；记录最终赋值／对象绑定消费，校验读取不计消费；反例保留校验但绕开规格赋值时必须被发现 | `SPEC_BINDING=PASS missing=0 unused=0 mismatch=0` |
| 原版自身重复 | A1↔A2 的原始 HDF5、图像、状态与事件；不可重复的身份单列 | `BASELINE_REPEAT=PASS compared=N different=0` |
| 随机流不漂移 | B／C／D 比调用序号、源身份、签名、结果、拒绝记录与前后状态；A 路以未覆盖生成作输出锚点，历史内部随机观察范围另列 | `RNG_PARITY=PASS compared=N calls_mismatch=0 state_mismatch=0` |
| 原始行为已恢复 | A1↔B 全字段比；不能排除 RouteStick 尾迹、演示标志或恢复事件来求通过 | `TRAIN_RESTORE=PASS compared=N mismatch=0` |
| 原值注入等价 | B↔C、C↔D、A1↔D；逐元素比较 dtype、shape、数值位模式、所有 group/dataset/attribute | `INJECTION_PARITY=PASS compared=N mismatch=0` |
| 图像与录像事件 | 比实际落盘 RGB 与演示／执行标志、真实帧索引；MP4 比完整解码帧数与像素，并单列编码容器散列 | `VIDEO_PARITY=PASS compared=N frames_mismatch=0 pixels_mismatch=0` |
| 连续 worker 不污染 | 每环境选不同原身份，甲→乙→甲在同一 PID 运行，各自与独立进程比；原配置、规格输入散列不变 | `WORKER_ISOLATION=PASS tasks=16 mismatch=0 input_mutation=0` |
| fail recover 保持原样 | 原分支与各新路径逐条比恢复开关、z／xy、实际失败动作索引、恢复任务与结果；不是只比模式名 | `RECOVERY_PARITY=PASS configured=96 mode_mismatch=0 event_mismatch=0` |
| 原测试结果对拍 | A 的身份、恢复、成功与帧数逐条比原报告；取得发布参考集后再复跑原合同和动作比较器，比报告实际保存的细节；保留既有失败和 `1e-8` | `DATASET_GEN_REPORT_PARITY=PASS compared=1600 outcome_mismatch=0 detail_mismatch=0` |
| 历史成品额外比较 | 仅在找回且散列核验通过时比历史原 HDF5；本轮已知文件缺失，不能当作默认能通过的项 | `HISTORICAL_ARTIFACT_PARITY=NOT_RUN reason=historical_files_missing` |
| 失败与全集覆盖 | 所有原身份都有终态；missing、timeout、error、不可重复、不可比和成功分别计数，失败保留退出码与阶段 | `TRAIN_COVERAGE=PASS expected=1600 terminal=1600 missing=0` |

表中 `N` 必须替换为实测条数，不能原样填在结果里。`TRAIN_COVERAGE` 仅说明执行完整，不说明全部一致；总体完成还要求每条身份有完整适用的对拍结论，存在未解决差异就如实保留未通过。历史成品缺失是单独边界，不能因此取消对 d53 新跑结果和历史报告已有字段的比较。HDF5 文件 SHA 相同可以证明字节相同；SHA 不同则继续比所有内容，分别报告“字节相同”“全字段逐位相同”“视频像素相同”。注入前后的容差结果只能作为诊断；发布参考集比较保留原有 `1e-8` 验收口径，两者不混用。

录像器 `RecordWrapper.py` 全程冻结：不补 reset 帧，不录制原 `NO RECORD` 帧，不改变命名和输出位置。需要 reset 图像时在入口侧读取已有 reset 返回值，事件时间使用实际编号。旧 `tests/_shared/parity_observer.py` 会覆盖录像器方法，不能直接作为本次生产对拍观察器。测试内可做隔离反例，但不能将覆盖后的生成结果作为无覆盖 A 基线。

## 六、后续实施顺序与逐项审批清单

### 6.1 实施顺序

| 阶段 | 要做什么 | 结束判据 |
| --- | --- | --- |
| 0 | **实施开始前**切 `newtaskRelease-v3`；冻结父提交、官方源码、官方 1600 条 metadata、锁文件、设备与用例清单，核验输出路径与存储空间 | 分支正确；`TRAIN_IDENTITY`；来源散列齐全 |
| 1 | 冻结 `dataset-gen` 原报告与逐文件散列，定位历史成品和官方参考数据；在 `scripts/` 新增严格原 train manifest 与对拍编排；A1／A2 单条试跑 | 原结果可用性如实记录；原 worker 含 fail recover；不以公式替换 seed |
| 2 | 按逐项批准的范围恢复历史原值默认路径，先做 A↔B；RouteStick 尾迹等逐项验收 | `TRAIN_RESTORE` 在指定样本通过；未解决项不隐藏 |
| 3 | 十六环境逐个切出 `sampling_config`；每个环境先 B↔C，再进入下一环境 | `SAMPLING_ORIGINAL`；对应原始样本 B↔C 通过 |
| 4 | 按同一顺序切出完整 `episode_spec`，支持原位抽样记录与原值回注，包括两次初始化和动态事件 | `SPEC_BINDING`、`RNG_PARITY`、`INJECTION_PARITY` |
| 5 | 16 环境冒烟、48 格与恢复分支、连续 worker；分批执行全集五路对拍，复跑原比较器；另核验原 20 worker 配置 | 包括 `RECOVERY_PARITY`、历史成品与原报告对拍；各项按实际范围输出，未齐前不标完成 |
| 6 | 保存逐条身份、配置／规格、差异、命令、退出码、原始结果及图像索引；更新使用说明并提交 | 源文件和原产物未被覆盖；状态与证据一一对应 |
| 后续新任务 | 用户另行启动布局／难度改动后，启用第二节的未来值和算法 | 单独定义新值验收，不能复用原 train 相等结论 |

每次代码提交前的测试预算不超过 5 分钟：先跑相关定向测试和核心路径；完整五路矩阵属于独立的长时实验，按批次用 detached tmux 管理，日志采用 `PYTHONUNBUFFERED=1`、`set -o pipefail`、`tee` 与 `EXIT_CODE=`。单条冒烟失败先定位，不能直接放大全集。第一次实测后再估算耗时和磁盘，不能用历史四任务的耗时线性外推作保证。

### 6.2 具体文件与改动锚点

下面是**待实施清单**，不是本轮修改记录，也不是整表已经获批。每个环境的具体固定项见第二节；实施前须将该环境实际涉及的函数与改法单独提交审批。

| 文件／锚点 | 拟改什么、为什么 | 原值阶段的行为 |
| --- | --- | --- |
| `scripts/train_split_parity.py`（拟新增） | 严格构建原 metadata manifest；按 A1／A2／B／C／D 编排；读取原报告、调用固定原比较器并逐条比结果 | 使用原实际 seed，只尝试一次；A 执行原 worker，含原 fail recover |
| `scripts/generate_dataset_newseed.py::EpisodeJob`、`extract_native_sampling`、`load_sampling_config`、`load_episode_specs`、`_worker` | 扩展十六环境快照与带实际身份的新规格版本；提供原 train 作业构建和恢复事件证据 | 默认旧入口兼容；原 train 模式保留前六条失败恢复，不调用公式补位及 BinFill 复制 |
| `scripts/injection/candidates/io.py::validate_candidates`、`project_spec` | 新版原 train 记录独立校验；统一生成与 reset 的投影 | 不覆盖旧四任务封套和旧运行十文件 |
| `scripts/injection/rollout/reset_check.py` 的环境构建入口 | 消费同一原 train 身份与两类配置，输出 reset 核验 | 不另抽 seed，不重新分配 split |
| `src/robomme/robomme_env/BinFill.py::__init__`、`_load_scene`、`_initialize_episode` | 补齐两次颜色抽样、布局、目标数与恢复动作冻结 | 原数目、原目标规则、原随机消费不变 |
| `src/robomme/robomme_env/PickXtimes.py::__init__`、`_load_scene`、`_initialize_episode` | 外提颜色／次数／生成区域，冻结对象与循环动作 | 不移向角落，不加干扰物，不增次数 |
| `src/robomme/robomme_env/SwingXtimes.py::__init__`、`_load_scene`、`_initialize_episode` | 外提轮数、颜色、摆动动作与对象绑定 | 一轮左右各一次的语义不变 |
| `src/robomme/robomme_env/StopCube.py::__init__`、`_load_scene`、`_initialize_episode`、`step` | 外提速度候选、停点序号与原往返窗口 | 保持原速度抽法及五段上限；未来多段另实施 |
| `src/robomme/robomme_env/VideoUnmask.py` 的构造／场景／初始化／`step` | 外提容器、颜色、藏物、拾取和时间输入 | 原单双抓取与容器布局不变 |
| `src/robomme/robomme_env/ButtonUnmask.py` 的构造／场景／初始化／`step` | 同上并冻结按钮及触发顺序 | 不启用第三次抓取 |
| `src/robomme/robomme_env/VideoUnmaskSwap.py` 的构造／场景／初始化／`_refresh_swap_schedule`／`step` | 补齐原始随机消费、交换实际绑定与窗口 | 原次数、速度和对象映射不变 |
| `src/robomme/robomme_env/ButtonUnmaskSwap.py` 的构造／场景／初始化／`_refresh_swap_schedule`／`step` | 新接两类接口，冻结按钮、藏物和交换序列 | 原 1／2／3 次分支原样展开为记录，不启用 6～8 次 |
| `src/robomme/robomme_env/PickHighlight.py` 的构造／场景／初始化／`step` | 外提数量、颜色池、目标选择和高亮时序 | 不增加目标数 |
| `src/robomme/robomme_env/VideoRepick.py` 的构造／场景／初始化／交换相关方法／`step` | 补齐 hard 分支与完整规格回注 | 保留 hard 15 块、零交换；不以 xhard 替代 |
| `src/robomme/robomme_env/VideoPlaceButton.py` 的构造／场景／初始化／`step` | 外提对象、目标区域、演示动作与重置绑定 | 保留单目标演示、原放置目标和按钮逻辑 |
| `src/robomme/robomme_env/VideoPlaceOrder.py` 的构造／场景／初始化／`step` | 同上并冻结顺序目标和区域交换 | 保留原单目标与操作顺序 |
| `src/robomme/robomme_env/MoveCube.py` 的构造／场景／初始化 | 外提方块、杆、目标位姿及原抽样调用 | 原平面姿态和区域不变 |
| `src/robomme/robomme_env/InsertPeg.py` 的构造／场景／初始化 | 外提杆列表、目标杆与孔位绑定 | 保留原杆数、强制索引和随机消费 |
| `src/robomme/robomme_env/PatternLock.py` 的构造／场景／初始化／`step` | 外提网格、路径抽样与原演示事件参数 | 原路线和速度不变，不凑 20～30 秒 |
| `src/robomme/robomme_env/RouteStick.py::_load_scene`、`step` | 补齐原生节点／方向／颜色；尾迹恢复原值单独批准 | 不做方向配额，不延长视频 |
| `tests/lightweight/`、`tests/dataset/`、`tests/_shared/native_sampling_parity.py` | 新增身份、配置／规格绑定反例；复用和补齐全字段离线比较；新增真实原 train 矩阵 | 测试观察器不得改变作为结论依据的生产行为 |

如 `object_generation.py`、`route.py`、`task4recovery.py` 或求解器确实还需要改动，必须再列出具体函数与理由，不能由环境文件获批推导出工具文件也获批。预留未来功能不等于现在重写这些公共函数。`src/robomme/env_record_wrapper/RecordWrapper.py` 不在改动清单内。

### 6.3 命令与留档约定

以下为现有可执行的只读核验；本轮联网读取固定官方 SHA 的源码和 metadata 并完成比较。切分支命令只在后续实施开始时执行。

```bash
git ls-remote https://github.com/RoboMME/robomme_benchmark.git refs/heads/dataset-gen
git show d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa:scripts/data-generation/reports/generation_report.md
git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py
sha256sum pyproject.toml uv.lock
```

```bash
# 后续实施第一步；本轮不执行。
git switch -c newtaskRelease-v3
```

拟新增的命令接口如下，**当前尚不可执行**；开发时先实现 `--help` 与参数校验，再写实测命令及退出结果。`freeze-identities` 只固定官方身份，`run` 按五路运行并在 C 路完成后导出相应原值规格，`compare` 只读比较；不另建第二份生成逻辑。

```bash
command -v uv
uv run --no-sync python scripts/train_split_parity.py freeze-identities --source-repo https://github.com/RoboMME/robomme_benchmark.git --source-ref d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa --expected-per-task 100 --output artifacts/train-parity/v3-native
uv run --no-sync python scripts/train_split_parity.py run --manifest artifacts/train-parity/v3-native/train_manifest.json --env BinFill --episode 0 --paths A1,A2,B,C,D --workers 1 --gpus 0 --output artifacts/train-parity/v3-smoke
uv run --no-sync python scripts/train_split_parity.py compare --run artifacts/train-parity/v3-smoke
```

`freeze-identities` 读取官方原文并保存身份，不启动仿真；C 路完整规格导出需要真实运行，必须在阶段 1 的 A 冒烟及阶段 3 的 C 冒烟通过后才分批启动，不能第一次执行命令就直接展开全部 1600 条。第一次 `run` 只覆盖显式选择的单条；候选规格来自已完成的 C 路，不接受重新抽取的候选填补。

每次代码改动后先运行 5 分钟内的相关测试；可以参考现有入口：

```bash
command -v uv
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
```

新命令的真实仿真、日志、大文件输出均置于 `artifacts/train-parity/` 的独立运行目录；轻量结果置于 `docs/validation/newtask-v3/`，原值配置和完整候选记录逐个明确加入 Git。媒体不提交；存储不足时先汇报明确的占用与处理范围，不清理旧产物腾空间。每步提交只暂存自己的路径，提交中文说明包含用户原话、计划、实施取舍、异常、实测结果与剩余边界。

## 七、本轮方案的状态

本轮只做源码、metadata、分支与依赖指纹的只读核验，新增方案并更新账本。没有创建 `newtaskRelease-v3`，没有生成新的配置或候选，没有运行十六环境仿真，也没有宣称原 train 对拍通过。未来取值全部停留在第二节的接口需求中。

文档验收检查十六环境是否逐个列出、未来需求是否全部有落点、原值与新值是否混淆、引用文件和函数是否存在、是否误用硬编码代码行号、是否误把待实现命令说成已有能力，并运行 `git diff --check`。纯文档改动不启动数据生成；后续实施结果追加在本节之后，保留原计划和本轮核验边界。

本轮最终静态验证退出 0：`PLAN_STRUCTURE=PASS environments=16 fixed_rows=64 local_links=23 code_line_refs=0`；从固定 `dataset-gen` Git 对象重读十六份 metadata，`PLAN_BASELINE=PASS train=1600 recovery_z=48 recovery_xy=48 recovery_off=1504`。`git diff --check` 通过；相对初始提交的 `src/`、`scripts/`、`pyproject.toml`、`uv.lock` 零改动。三项独立只读复核完成，原值、未来需求、官方分支与历史报告口径一致。本次只有文档验证，没有代码测试或真实仿真；方案本身不是任何未来对拍判据的通过证据。
