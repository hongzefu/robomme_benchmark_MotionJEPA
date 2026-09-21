# 全环境配置拆分与原始 train 对拍方案

> 本方案以用户本轮要求为准，只规划，不实施。工作副本为 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，核验代码为 `a4a6e9fab630e9399ca538ab2cc9d008e9638713`，当前分支为 `newtask-v2.1refractor`。方案于 `11.20` 首次落地，后续仅修订本文件及必要账本；本次 `11.23` 将固定项拆成用户决策、原规则抽样和规则派生，运行代码未变，不创建分支。**方案之后开始实施时，先从包含本方案的提交切出用户指定的 `newtaskRelease-v3`，再改代码。**
>
> 新分支的第一轮目标是：**十六个环境都能显式传入 `sampling_config` 与 `episode_spec`，按官方原始 train 的 16×100＝1600 条实际身份重放，与官方 `dataset-gen` 分支的生成及测试结果对拍，保留其中的 fail recover，证明注入前后保持一致。** 权威来源固定为 [RoboMME/robomme_benchmark 的 dataset-gen 分支](https://github.com/RoboMME/robomme_benchmark/tree/d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa)，本轮核验提交 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`；既有测试报告另记录其实际运行提交，见第三节。本文列出的更难布局、更多物体、更多动作及视频时长要求，只决定接口要留出什么能力，第一轮全部不启用。`src/robomme/` 的每一项源文件改动和运行时覆盖仍须按 [AGENTS.md](AGENTS.md) 强制规则第 11 条逐项批准，录像器保持冻结。

## 一、先拆清楚：用户改规则，外部给本局值

本方案把“固定内容”拆成具体字段，不再把“数量／布局／动作／时间”四句话当作接口。**用户决定可改字段的取值域或策略；外部供值器按照规则产生本局结果；环境按规格创建对象并执行动作。**

| 归属 | 存放位置 | 是否等待用户决定 | 例子 |
| --- | --- | --- | --- |
| 用户决策 | `sampling_config.tasks[env].decision` | 是；已给的未来值先写方案，第一轮仍填原值 | 交换次数范围、颜色池、布局模式、交换速度倍率 |
| 原规则保持 | `sampling_config.tasks[env].native` | 本轮没有要求修改；按固定官方分支提取 | 原随机算法与区间端点、按钮区域、目标选择规则、最近邻规则 |
| 本局输入 | `episode_spec` | 不逐局让用户指定；外部产生后冻结 | 本局交换次数、每块位置、目标ID、颜色排列、路线方向 |
| 派生结果 | `episode_spec` 中对应字段 | 由输入和规则计算，不能再独立抽签 | 藏物映射、目标补集、最近交换搭档、时间表 |
| 运行证据 | 独立结果记录 | 由实跑测量，不能预填 | 实际帧数、实际回位误差、成功／失败、运行时交换位置 |

**这些分类不是把 `sampling_config` 全部算成用户决策、把 `episode_spec` 全部算成随机数。** 同一参数分为两层：例如用户给 `swap_count_range=[8,12]`，按原规则抽出的某局次数才写进 `episode_spec.objects.n_swaps`；后面的交换对、窗口由这个次数和布局派生。这里的“某局”仅说明类型，不指定任何实际样本的新值。

下文统一使用简写，**全部是本次方案的目标接口，尚未实施**：

| 简写 | 完整路径／含义 |
| --- | --- |
| `U.x` | `sampling_config.tasks[env].decision.x`，用户后续会修改或须决定的字段 |
| `N.x` | `sampling_config.tasks[env].native.x`，维持原规则的字段，包括常量、抽样规则和派生规则 |
| `E.x` | `episode_spec.x`，本局具体输入；已存在的四环境字段在每节末尾单列映射，其余标为拟新增 |
| `O.x` | 独立运行结果中的观测字段，不作为可调配置 |
| `U1/R1/D1` | 表内编号，分别表示用户决策、原规则抽样、规则派生；同编号在下一张取值表中对应 |

第一轮原始 train 对拍时，**U 与 N 都采用官方 `dataset-gen` 原值**；未来只放开各节 U 行，不因字段进入配置就允许修改全部 N。U 字段的每局随机落点也由外部供值器产生，R 行则列出除此之外仍须外置的原随机量。D 行明确哪些字段根本不是随机选择。

原四环境已使用外部规格，但现有 `scripts/injection/candidates/sampling.py` 的 PCG64、`quota_series`、分层采样和 `balanced_choice` 是旧新值方案的一部分。它们改变随机流，有些还改变联合分布：例如 RouteStick 跨局平衡方向、BinFill 目标色至少一块。**这些旧用户决策不自动继承为“原规则不变”**；新分支的原值阶段仍按官方抽法复现，不能直接拿旧候选重新生成一批来对拍。

共用固定边界：实际 seed／difficulty 来自官方1600条身份；fail recover仍按dataset-gen的episode 0～2=z、3～5=xy，其余关闭，随机失败动作另记，未实现恢复的环境不伪造事件。尺寸、相机、机器人、控制器、成功阈值、录像器保持原口径；RouteStick尾迹恢复项沿后文单独审批。所有数值保留原dtype和运算顺序；`build_button` 的 `randomize_range` 是全宽，实际偏移公式为 `(u-0.5)*range`，不是直接±range。

## 二、逐环境字段拆分：先列归属，再列当前值与未来决策

每环境保留两张表。第一张只回答**拆哪些具体字段、哪些归用户决策、哪些仅外部供值**；第二张按同编号给当前值及后续处理。区间默认按表中注明的API或闭区间解释，不擅自改端点语义。字典中的 `d` 表示原难度；前三档数值顺序为 easy／medium／hard。

### 2.1 BinFill

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.layout_mode` → `E.layout.mode`、`E.layout.dynamic` | 布局模式；出现方式与密集度分开 |
| U2 | 用户决策 | `U.spawn_cubes` → `E.objects.spawn_total` | 闭区间 → 本局整数 |
| U3 | 用户决策 | `U.color` → `E.objects.colors_present` | 颜色数 → 选中色列表 |
| U4 | 用户决策 | `U.put_in_numbers` → `E.objects.put_in_total` | 闭区间 → 本局整数 |
| R1 | 规则不改，外部抽样 | `N.put_in_color`、`N.color_selection` → `E.objects.target_pool`、`E.objects.spawn_count`、`E.objects.target_count` | 抽颜色／分配计数；不能把全部目标色强制分到正数 |
| R2 | 规则不改，外部抽样 | `N.button`、`N.board`、`N.cube_pose` → `E.layout.button_xy`、`E.layout.board`、`E.layout.cubes[]` | 位置／朝向／创建顺序 |
| R3 | 规则不改，外部抽样 | `N.initialize_color_order` → `E.initializations[].color_order`；`N.recovery` → `E.actions.recovery` | 每次初始化排列、失败动作索引分别抽取 |
| D1 | 规则派生，不再抽签 | `N.put_in_order` → `E.actions.pick_place[]` 的 `pick/put_in` | 由颜色顺序与每色投入量展开动作 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | 原模式由 `dynamic=randint(0,2)` 决定；方块中心 `[-0.1,0]`、半边长 `[0.2,0.25]` | 全部 clutter；密集度／区域未定；开局全出现对应 dynamic=False，不能单凭此值认定 clutter |
| U2 | easy／medium／hard：`[4,6] / [8,10] / [10,12]` | 固定 12 块，即 `[12,12]` |
| U3 | easy／medium／hard：`1 / 2 / 3`；原池红、蓝、绿 | 颜色数 3；没有另行要求改颜色池 |
| U4 | easy／medium／hard：`[1,3] / [2,4] / [3,5]` | 投入总数 `[5,7]` |
| R1 | 投入颜色数 `[1,1] / [1,2] / [2,3]`；原颜色选择与分配顺序；选中目标色可分到 0 块 | 未要求修改 `put_in_color` 或分配规则；按 U2～U4 的最终参数生成结果 |
| R2 | 按钮中心 `[-0.2,0]`、randomize_range `[0.1,0.4]`、scale=1.5；板基位 `[0.15,0,0]`，偏移 `x=u×0.2−0.2,y=u×0.4−0.2,yaw=u×40−20` 度；板边0.1、孔边0.08、厚0.05；方块随机yaw | 按钮和孔板规则不变；方块区域仅受 U1 的后续决策改变 |
| R3 | 原 `_initialize_episode` 每次 `randperm`；fail recover 按 dataset-gen 原模式／原调用点 | 排列和恢复规则不改；新增按初始化序号存储，不复用一个排列 |
| D1 | 按初始化颜色顺序，取该色创建列表前 `target_count[color]` 块 | 保持原规则；`actions` 必须实际消费，不能仅写在规格里 |

现有配置映射：`U.color/spawn_cubes/put_in_numbers` 对应 `parameters.BinFill.configs[d].color/spawn_cubes/put_in_numbers`；`N.put_in_color` 对应同档 `put_in_color`；`N.button/board/cube_pose` 对应 `positions.BinFill.button/board/cubes`。现规格已有 `layout.dynamic/button_xy/board/cubes`、`objects.spawn_total/put_in_total/spawn_count/target_count/target_pool/colors_present` 及顶层 `actions[*]` 数组；新格式将此数组适配到 `E.actions.pick_place[]`，使 `E.actions` 能同时容纳恢复记录，不修改旧记录。`E.layout.mode`、按次保存的 `initializations`、完整恢复记录为拟新增；旧 `objects.initialize_color_order` 不能承载两次独立初始化。锚点：[BinFill.py](src/robomme/robomme_env/BinFill.py) 的 `__init__/_load_scene/_initialize_episode`、[specs.py](scripts/injection/candidates/specs.py) 的 `_binfill_group`。

### 2.2 PickXtimes

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.color` → `E.objects.color_order` | 原颜色池中的选色数 → 本局选中色排列 |
| U2 | 用户决策 | `U.number_range` → `E.objects.num_repeats` | 抓放循环数；不是块数 |
| U3 | 用户决策 | `U.target_cube_position_policy`、`U.goal_position_policy` → `E.layout.cubes[]`、`E.layout.goal` | 目标块／目标圆盘的位置策略分开 |
| U4 | 用户决策 | `U.distractor.{count,palette,placement}` → `E.objects.distractors[]` | 额外干扰物定义 → 每局实例 |
| R1 | 规则不改，外部抽样 | `N.color_and_target_selection` → `E.objects.color_order/target_cube_id`；`N.button` → `E.layout.button_xy` | 排列、目标索引、按钮xy |
| R2 | 规则不改，外部抽样 | `N.cube_pose/target_pose/recovery` → `E.layout`、`E.actions.recovery` | 原抽样调用／拒绝顺序、恢复随机动作 |
| D1 | 规则派生，不再抽签 | `N.task_expansion` → `E.objects.target_eligible_ids/distractor_ids/non_target_ids`、`E.actions.pick_place[]` | 按角色划分目标候选与干扰物；展开抓→放→最后按钮 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | `config_*['color']`：easy／medium／hard 为 `1/3/3`；选中颜色各1块 | color=3 |
| U2 | `number_min/max`：`[1,3]/[1,3]/[4,5]`，原 `torch.randint(min,max+1)` | num `[6,15]` |
| U3 | 两者中心 `[-0.1,0]`、半边长0.2；方块随机yaw，圆盘只抽xy | target 尽可能推向边角；`target_cube` 还是圆盘 `target` 待明确，边界退让／偏置强度未定 |
| U4 | 没有新增其他颜色干扰物；现有未选中的原色块为非目标 | 增加其他颜色 distractor；数量／颜色池／生成位置未定 |
| R1 | 保留 `shuffle_indices/target_color_idx/target_cube_idx` 原顺序，前置颜色抽样被覆盖也保留；按钮中心 `[-0.2,0]`、range `[0.1,0.4]`、scale=1.5 | 原目标索引抽法作用于target_eligible_ids；新增其他色distractor不能混入目标候选；位置按U3改变 |
| R2 | cube候选每次抽xy与yaw，目标圆盘只抽xy；圆盘radius=`2*cube_half_size`；保留原间距与恢复调用 | 采样器及恢复规则不变，使用已决策的区域 |
| D1 | 原所有生成块均为目标候选，额外distractor为空；选定目标后取候选补集；反复抓同一 `target_cube` 放到 `target`，末尾按按钮 | 未来non_target_ids=未选中原候选+distractor_ids；次数由U2变，新增干扰物不成为正确目标 |

以上 `U/N/E` 是拟接接口；源码现有 `config_*` 的 `color/number_min/number_max`，以及 `target_cube/target`、`shuffle_indices/target_cube_idx`。锚点：[PickXtimes.py](src/robomme/robomme_env/PickXtimes.py) 的 `__init__/_load_scene/_initialize_episode`。

### 2.3 SwingXtimes

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.number_range` → `E.objects.num_repeats` | 摆动轮数 → 本局轮数 |
| U2 | 用户决策 | `U.distractor.{count,palette,placement}` → `E.objects.distractors[]` | 额外其他颜色对象 |
| R1 | 规则不改，外部抽样 | `N.color_and_target_selection` → `E.objects.color_order/target_cube_id` | 颜色排列与目标选择 |
| R2 | 规则不改，外部抽样 | `N.cube_region/target_regions/button` → `E.layout.cubes[]/targets[]/button_xy` | 方块xy/yaw、两圆盘xy、按钮xy |
| R3 | 规则不改，外部抽样 | `N.recovery` → `E.actions.recovery` | 失败抓取动作索引 |
| D1 | 规则派生，不再抽签 | `N.side_order/task_expansion` → `E.objects.target_eligible_ids/distractor_ids/non_target_ids`、`E.actions.target_right/target_left/swings[]` | 候选与干扰物分角色；按y排左右，按轮数展开 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | `number_min/max`：`[1,3]/[1,2]/[3,3]` | number `[4,10]`；每轮右、左各一次，合计8～20次落点 |
| U2 | 原无新增其他颜色干扰物 | 增加其他颜色 distractor；具体数目／颜色池未定 |
| R1 | 颜色数仍 `1/3/3`，原红蓝绿池，每色1块；前置颜色选择被最终目标选择覆盖仍留消费 | 本次未要求改颜色数或目标抽法 |
| R2 | 方块中心 `[-0.1,0]`、半边长0.25；圆盘中心 `[-0.1,-0.2]` 和 `[-0.1,0.2]`、半边长0.1、radius=`2*cube_half_size`；按钮中心 `[-0.2,0]`、range `[0.1,0.4]` | 原区域、几何和位置抽法不改 |
| R3 | 按原 generator 与 train 恢复模式选任务 | 恢复规则不改 |
| D1 | `max_swings=2*num_repeats`；右→左；高度0.1；阈值 `distance=0.03,z=0.12`；原非目标取目标候选补集 | 新distractor_ids不进入target_eligible_ids，合并到non_target_ids；左右判定、动作与成功阈值不改 |

以上接口拟新增；现有规则锚点：[SwingXtimes.py](src/robomme/robomme_env/SwingXtimes.py) 的 `config_*`、`__init__/_load_scene/_initialize_episode`。`number` 表示一轮左右动作，不是方块数或单次摆动数。

### 2.4 StopCube

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.move_interval_choices` → `E.actions.move_interval` | 速度候选 → 本局间隔 |
| U2 | 用户决策 | `U.stop_time_range` → `E.actions.stop_time` | 第几次经过目标时停止 |
| R1 | 规则不改，外部抽样 | `N.target/button/color` → `E.layout.target_xy/button_xy`、`E.objects.cube_rgb` | 目标xy、按钮xy、RGB |
| R2 | 规则不改，外部抽样 | `N.route_rotation` → `E.actions.rotation_deg`；原无效抽样 → `E.sampling_trace` | 旋转角；被覆盖的提前量仅留随机消费 |
| D1 | 规则派生，不再抽签 | `N.motion_segments/time_rules` → `E.actions.segments[]/steps_press/stop_window` | 路线端点、往返段、时窗由输入计算 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | `_initialize_episode::move_interval_list=[60,80,120]` | 最快现有档，候选只留 `[60]` |
| U2 | `randint(2,6)`，即闭区间 `[2,5]` | number `[6,15]`，这里映射停止序号 |
| R1 | 目标xy各 `uniform(-0.1,0.1)`；cube色 `rand(3)`；按钮中心 `[-0.2,0]`、range `[0.1,0.4]`；目标姿态 `[0,90,0]` 度为固定输入 | 不改这些域与抽法 |
| R2 | 旋转 `uniform(-30,30)` 度；`randint(27,33)` 后把 interval 覆盖为30 | 不改旋转域；无效抽样不变成用户参数 |
| D1 | 路线 `[0,-0.3]→[0,0.3]` 旋转平移至目标；现5段；`steps_press=move_interval*(stop_time-0.5)`，窗口 `[move_interval*(stop_time-1),move_interval*stop_time]`；提前量30 | 增加停止序号时必须配套覆盖到所选段，最大15；不是再抽一次段数。StopCube 原无失败抓取注入 |

以上字段拟新增；源码锚点：[StopCube.py](src/robomme/robomme_env/StopCube.py) 的 `_load_scene/_initialize_episode/step/evaluate`。`step::range(5)` 是未来扩次数的真实限制；第一轮仍保持5段。

### 2.5 VideoUnmask

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.pick_count` → `E.objects.n_picks` | 拾取数量 |
| U2 | 用户决策 | `U.bin_layout_policy` → `E.layout.bins[]` | 容器布局策略 |
| U3 | 用户决策 | `U.distractor.{count,palette,placement}` → `E.objects.distractors[]` | 其他颜色干扰物 |
| R1 | 规则不改，外部抽样 | `N.bin_pose/color_order` → `E.layout.bins[]`、`E.objects.color_order` | 容器xy/yaw、三色排列 |
| R2 | 规则不改，外部抽样 | `N.recovery` → `E.actions.recovery` | 原失败动作选择 |
| D1 | 规则派生，不再抽签 | `N.hidden_rule/pick_rule/reveal_timing` → `E.objects.hidden/empty/pick_order`、`E.actions.reveal` | 颜色映射、固定前缀抓取、展示 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | `config_*['pick']`：`1/1/2` | pick=3 |
| U2 | `config_*['bin']`：`3/5/15`；center `[0,0]`、half_size0.2、min_gap0.04、max_trials256 | clutter bin；密度／区域／是否改容器数未定 |
| U3 | 前三容器藏原三色，其余空，没有新增其他颜色 | 增加其他颜色；数量及放容器内还是桌面上未定 |
| R1 | 每次先抽xy，通过拒绝检查才抽 `yaw=u×90` 度；`shuffle_indices=randperm(3)` | 保留原抽法；容器域由U2提供；不以固定配额替换randperm |
| R2 | 原恢复模式与随机流 | 保持原状 |
| D1 | 前3容器各藏一块，半边长 `cube_half_size/1.2`、yaw=0；抓 `bin_0`，pick>1再抓 `bin_1`；展示 `[0,64]` | 目标不是另抽的容器；未来pick3须扩完整列表。现step最多遍历15容器，U2若扩容须配套接入 |

以上接口拟新增；源键为 `configs[difficulty]['bin'/'pick']`，锚点：[VideoUnmask.py](src/robomme/robomme_env/VideoUnmask.py) 的 `_load_scene/step`。

### 2.6 ButtonUnmask

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.pick_count` → `E.objects.n_picks` | 拾取数量 |
| U2 | 用户决策 | `U.bin_layout_policy` → `E.layout.bins[]` | 容器布局策略 |
| U3 | 用户决策 | `U.distractor.{count,palette,placement}` → `E.objects.distractors[]` | 其他颜色干扰物 |
| R1 | 规则不改，外部抽样 | `N.button/bin_pose/color_order` → `E.layout`、`E.objects.color_order` | 按钮／容器位置、容器yaw、三色排列 |
| R2 | 规则不改，外部抽样 | `N.constructor_rng/recovery` → `E.sampling_trace`、`E.actions.recovery` | 无效num_repeats抽样、恢复动作 |
| D1 | 规则派生，不再抽签 | `N.hidden_rule/pick_rule/button_trigger` → `E.objects.hidden/empty/pick_order`、`E.actions` | 藏物与按按钮后的有序抓取 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | `config_*['pick']`：`1/1/2` | pick=3 |
| U2 | `bin=3/5/15`；center `[0,0]`、half_size0.2、min_gap0.04 | clutter bin；数量、密度与区域未定 |
| U3 | 没有额外其他颜色干扰物 | 增加；数量、颜色池与藏放位置未定 |
| R1 | 按钮中心 `[-0.2,0]`、range `[0.1,0.1]`、scale1.5；bin位置通过才抽yaw=`u×90`度；三色randperm | 原采样方法不改，容器区域由U2的未来决策提供 |
| R2 | 构造器 `randint(1,6)` 不决定抓数；其 `self.generator` 用于恢复；场景另有同seed局部generator | 两条流分开保持，不能合并；恢复模式由入口原episode规则给定 |
| D1 | 前三容器藏三色；按按钮→bin_0→可选bin_1；原展示窗口／最多15容器 | 保持按钮触发机制；未来第三抓只扩目标列表，不另抽拾取对象 |

以上接口拟新增；现有 `config_*::bin/pick` 与局部变量来自 [ButtonUnmask.py](src/robomme/robomme_env/ButtonUnmask.py) 的 `__init__/_load_scene/_initialize_episode/step`。

### 2.7 VideoUnmaskSwap

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.swap_count_range` → `E.objects.n_swaps` | 闭区间 → 本局交换次数 |
| U2 | 用户决策 | `U.pick_count_range` → `E.objects.n_picks` | 闭区间 → 本局拾取数 |
| U3 | 用户决策 | `U.swap_speed_multiplier` → `E.actions.swap_windows[]` | 倍率 → 派生时间表 |
| U4 | 用户决策 | `U.distractor.{count,palette,placement}` → `E.objects.distractors[]` | 其他颜色干扰物 |
| R1 | 规则不改，外部抽样 | `N.containers` → `E.layout.type/theta_rad/bins[]` | 布局型、整体角、局部xy/yaw |
| R2 | 规则不改，外部抽样 | `N.object_selection/recovery` → `E.objects.selected/color_order/swap_initiators/target_choice`、`E.actions.recovery` | 排列、发起者索引、辅助目标、恢复动作 |
| D1 | 规则派生，不再抽签 | `N.hidden_rule/pick_rule/partner_rule` → `E.objects.hidden/empty/pick_order`、`E.actions.swap_pairs[]` | 映射、拾取前缀、实际XY最近邻 |
| D2 | 规则派生，不再抽签 | `N.swap_path`、U3 → `E.actions.swap_windows[]` | 每次交换窗口与轨迹输入 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | 原 `swap_min/max`：`[1,2]/[1,2]/[2,3]` | swap `[8,12]` |
| U2 | 原 `pick_min/max`：`[1,2]/[1,1]/[2,2]` | pick=3，即 `[3,3]` |
| U3 | 倍率1；每次50步 | 倍率1.5；`50/1.5`非整数，离散时间处理尚待决定 |
| U4 | 无额外其他颜色干扰物 | 增加；数量、颜色池、藏放位置未定 |
| R1 | bin=`3/4/4`；三角／直线／四点原锚点；整体旋转 `[0,180]` **弧度**，局部half_size0.07、min_gap0.02、yaw=`u×90`度 | 本次未要求改变容器数或布局；与两个非Swap环境的clutter要求分开 |
| R2 | 前三容器randperm(3)，原三色排列，前两发起者局部索引映射保留，剩余发起者按原抽法 | 选择规则不改；`target_choice` 和完整恢复规格拟补，现代码仍内部抽取 |
| D1 | 第4容器为空；原pickup索引 `[0,1]`；partner排除自身，等距取创建顺序靠前者；pair实键 `initiator/partner/distance_m` | 最近搭档不另抽签；未来pick3扩前缀和动作绑定，不直接把旧count改3了事 |
| D2 | 第k次 `[64+50k,64+50(k+1)]`；lane_offset0.07、smooth=True、keep_upright=True | 路径参数不改；未来U3仅改变时间尺度；实际帧进入观测 |

现有配置映射：U1/U2 对应 `parameters.VideoUnmaskSwap.configs[d].swap_min/swap_max/pick_min/pick_max`；N映射 `parameters.VideoUnmaskSwap.object_selection/swap_selection` 与 `positions.VideoUnmaskSwap.containers`。`E.objects.selected/color_order/hidden/empty/pick_order/swap_initiators`、`E.layout.type/theta_rad/bins`、`E.actions.swap_pairs` 已存在；U3/U4、`target_choice`、时间表等为拟新增。当前 object_selection/swap_selection 只校验原值，不是已开放的任意参数。锚点：[VideoUnmaskSwap.py](src/robomme/robomme_env/VideoUnmaskSwap.py) 的 `__init__/_load_scene/_initialize_episode/_refresh_swap_schedule/step`、`_unmask_group`。

### 2.8 ButtonUnmaskSwap

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.swap_count_range` → `E.objects.n_swaps` | 闭区间 → 本局次数 |
| U2 | 用户决策 | `U.pick_count_range` → `E.objects.n_picks` | 闭区间 → 本局数量 |
| U3 | 用户决策 | `U.swap_speed_multiplier` → `E.actions.swap_windows[]` | 倍率 → 时间表 |
| U4 | 用户决策 | `U.distractor.{count,palette,placement}` → `E.objects.distractors[]` | 其他颜色干扰物 |
| R1 | 规则不改，外部抽样 | `N.buttons/container_offsets/bin_pose` → `E.layout.buttons[]/bins[]`、`E.sampling_trace` | 按钮xy、锚点偏移、bin位置／yaw |
| R2 | 规则不改，外部抽样 | `N.object_selection/recovery` → `E.objects.color_order/selected/swap_initiators/target_choice`、`E.actions.recovery` | 原独立随机源与索引选择 |
| D1 | 规则派生，不再抽签 | `N.hidden_rule/pick_rule/partner_rule` → `E.objects.hidden/empty/pick_order`、`E.actions.swap_pairs[]` | 藏物、selected前缀、最近邻 |
| D2 | 规则派生，不再抽签 | `N.button_order/swap_path`、U3 → `E.actions` | 按钮顺序、窗口、路径 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | `swap_min/max`：`[1,2]/[1,2]/[2,3]` | swap `[6,8]` |
| U2 | `pick_min/max`：`[1,2]/[1,1]/[2,2]` | pick=3，即 `[3,3]` |
| U3 | 倍率1、每段50步 | 倍率1.5；离散步长取整规则未定 |
| U4 | 无新增其他颜色干扰物 | 增加；数量、颜色池、位置未定 |
| R1 | 左按钮 `[-0.2,-0.1]`、右 `[-0.2,0.1]`，range各 `[0.05,0.05]`；bin=`3/4/4`，half_size0.07、gap0.02；锚点偏移 `u×0.1`，无整体旋转；未用分支仍消费随机数 | 本次未要求改按钮／容器布局；左按钮旧方案误写y=0，本轮按源码纠正 |
| R2 | 构造抽swap/pick；场景另建同seed流抽布局、三色、selected、target_choice、发起索引／剩余者；恢复沿原self.generator | 原抽法／索引映射保留，受U1/U2影响的次数由新范围产生 |
| D1 | 前三藏物、第四空；拾取selected_bins[0]及count=2时的[1]；发起者局部索引历史行为保留；partner为实际XY最近邻 | 未来补第三抓和完整交换列表；当前schedule只有1/2/3分支，设pick=3反而只生成第一抓 |
| D2 | 右按钮→左按钮；第k次 `[64+50k,64+50(k+1)]`；lane_offset0.07、smooth=True、keep_upright=True | 按钮／路径不变，窗口按U3未来决策统一计算 |

以上接口拟新增；原键为 `config_*::bin/swap_min/swap_max/pick_min/pick_max`，源锚点：[ButtonUnmaskSwap.py](src/robomme/robomme_env/ButtonUnmaskSwap.py) 的 `__init__/_load_scene/_initialize_episode/_refresh_swap_schedule/step`。N中的三角基位 `[[-0.05,-0.15],[-0.05,0.15],[0.05,0]]`，直线第三点改 `[-0.05,0]`；四点 `[[0,-0.1],[0,0.1],[0.1,0.1],[0.1,-0.1]]`；三点各自x、四点分组y加 `u×0.1`，保持原抽样顺序。

### 2.9 PickHighlight

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.layout_mode/cube_region` → `E.layout.cubes[]` | 布局与区域 |
| U2 | 用户决策 | `U.highlight_count_range` → `E.objects.highlight_count` | 闭区间 → 目标数 |
| U3 | 用户决策 | `U.spawn_count` → `E.objects.n_cubes` | 总块数 |
| U4 | 用户决策 | `U.block_color_policy/palette` → `E.layout.cubes[].color` | 逐块颜色 |
| R1 | 规则不改，外部抽样 | `N.color_draw/cube_pose/target_selection` → `E.layout.cubes[]`、`E.objects.highlight_ids` | 逐块抽色／位置／yaw；randperm目标ID |
| R2 | 规则不改，外部抽样 | `N.button/recovery` → `E.layout.button_xy`、`E.actions.recovery` | 按钮xy与原恢复选择 |
| D1 | 规则派生，不再抽签 | `N.highlight_window/task_expansion` → `E.actions.highlight_windows/pick_order` | 高亮时窗、动作展开、非目标补集 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | center `[-0.1,0]`、half_size0.2、min_gap=`2*cube_half_size`、随机yaw | clutter；具体区域和密度未定 |
| U2 | `config_*['pickup']`：`1/2/3` | highlight number `[5,7]` |
| U3 | `config_*['spawn']`：`3/4/6` | 未定；必须至少容纳本局高亮数，上限7不等于已决定总共7块 |
| U4 | 每块独立从红／蓝／绿选 | block颜色任意；离散池或连续RGB及分布未定 |
| R1 | 原 `color_choice_idx`、spawn拒绝顺序、`randperm(len(all_cubes))[:pickup]`；生成失败break，保存实际数量 | 抽法按已决策的域运行，目标仍按对象ID识别，不改为颜色唯一身份 |
| R2 | 按钮 `[-0.2,0]`、range `[0.1,0.4]`、scale1.5 | 保持原状 |
| D1 | 所有目标共用 `[10,100]` 窗口，**同时高亮**；抓取才按target列表有序执行 | 保持原时间规则；原方案“依次高亮”表述本轮纠正 |

以上接口拟新增；现有 `spawn/pickup`、`color_choice_idx/target_cube_indices` 来自 [PickHighlight.py](src/robomme/robomme_env/PickHighlight.py) 的 `config_*`、`_load_scene/step`。

### 2.10 VideoRepick

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.layout_mode` → `E.layout.mode/cubes[]` | 布局模式 |
| U2 | 用户决策 | `U.num_repeats_range` → `E.objects.num_repeats` | 闭区间 → 抓放次数 |
| U3 | 用户决策 | `U.block_color_policy/palette` → `E.layout.cubes[].color` | 逐块颜色 |
| U4 | 用户决策 | `U.swap_enabled/swap_count_range` → `E.objects.n_swaps` | 交换开关与次数 |
| R1 | 规则不改，外部抽样 | `N.button/layout_draw/cube_pose` → `E.layout.button_xy/type/theta_rad/cubes[]` | 按钮位置、布局型／角度、方块位置／yaw |
| R2 | 规则不改，外部抽样 | `N.object_selection/recovery` → `E.objects.target/swap_initiators`、`E.actions.recovery` | 目标与剩余对象顺序、恢复 |
| D1 | 规则派生，不再抽签 | `N.partner_rule/swap_timing/task_expansion` → `E.actions.swap_pairs[]/swap_windows[]/pick_place[]` | 最近邻、触发相对时窗、重复动作 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | easy/medium原锚点局部half_size0.07；hard中心 `[-0.1,0]`、half_size `[0.2,0.25]` | clutter，独立于是否swap |
| U2 | `num_repeats.low=1,high_exclusive=4`，实际1～3 | pick times `[4,6]`；若沿randint则low=4、high_exclusive=7 |
| U3 | 非hard整局单色 `E.objects.color`；hard红蓝绿各5块 | block颜色任意；逐块池／分布待定 |
| U4 | easy `[1,2]`、medium `[2,3]`、hard0；现xhard `[4,5]`不进入原train | 是否启用swap待决；若启用则 `[8,12]`；clutter不意味着禁止swap |
| R1 | 按钮中心 `[-0.2,0]`、range `[0.1,0.1]`、scale1.5；非hard原三块锚点整体 `[0,180]`弧度；hard5轮每轮三色洗牌共15块 | 按钮与抽法不改，U1/U3改变的域单独标明；用户未明确新的总块数 |
| R2 | 非hard用原randperm选目标，hard用原randint；重复抓同一目标，剩余两块原乱序 | 不把目标选择或恢复当新增用户调参 |
| D1 | 交换开始时按实际XY取最近搭档；每次50步；方向／轨迹沿原规则 | 用户本次未要求VideoRepick交换速度×1.5；仅U4次数改变，时间公式随长度展开 |

现有映射：U2对应 `parameters.VideoRepick.num_repeats.low/high_exclusive`；U4对应 `configs[d].swap_min/max`；N对应 `object_selection/swap_selection`、`positions.VideoRepick.button/easy_medium_cubes/hard_cubes`。`E.objects.target/num_repeats/color/n_cubes/n_swaps/swap_initiators`、`E.layout.type/theta_rad/button_xy/cubes`、`E.actions.swap_pairs` 已存在；逐块颜色、模式、完整hard规格为拟新增。`_repick_group` 现拒绝hard，hard分支仍内部随机生成，不能假定已经外置。锚点：[VideoRepick.py](src/robomme/robomme_env/VideoRepick.py) 的 `_load_scene/_initialize_episode/_refresh_swap_schedule/step`、`_repick_group`。

### 2.11 VideoPlaceButton

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.demo_object_count` → `E.objects.demo_ids[]` | 演示对象数 → 有序对象列表 |
| U2 | 用户决策 | `U.demo_return_policy` → `E.actions.return_pose_by_object_id` | 返回策略 → 每对象目标位姿 |
| R1 | 规则不改，外部抽样 | `N.color/object_pose/target_selection` → `E.objects.color_order/demo_ids`、`E.layout.cubes[]` | 颜色排列、方块位置／yaw、目标索引 |
| R2 | 规则不改，外部抽样 | `N.targets/button/goal/task_flag/swap_selection` → `E.layout`、`E.objects.task_flag/swap_pair_ids` | 台与按钮xy、before/after、随机交换两台 |
| R3 | 规则不改，外部抽样 | `N.recovery` → `E.actions.recovery` | 原失败动作索引 |
| D1 | 规则派生，不再抽签 | `N.task_mapping/demo_template` → `E.actions.demo_by_object/execution_by_object/return_pose_by_object_id` | flag映射答案、复制动作模板、对象原位映射 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | 当前唯一 `target_cube`，演示对象数1；easy场上也只有1块 | video完成2个block；easy是否补块或限制档位未定 |
| U2 | 当前最后放同一个随机 `goal_site` | 各自回原位；原位取各对象演示开始的实际位姿，不再随机抽返回位置 |
| R1 | easy/medium/hard：color=`1/3/3`，每色1块；方块center `[0,0]`、half_size0.2；原目标选择调用 | 其余不变；两对象的选择／顺序由扩展后的同类规则明确，不能自行新增任务语义 |
| R2 | targets=`3/4/4`；台center `[0,0]`、half_size0.2、radius=`2*cube_half_size`；按钮center `[0.1,0]`、range `[0.05,0.3]`；goal center `[-0.1,0]`、half_size0.1、radius=`3*cube_half_size`；hard交换 | 目标台、按钮、before/after及交换规则按“其余不变”保留 |
| R3 | 原dataset-gen恢复模式与抽法 | 不变 |
| D1 | before→target_0，after→target_1；演示 target_0→按钮→target_1→goal_site；additional_place=False；hard交换50步；原初始化goal的z改为-0.05 | 未来按U1扩两块，按U2替换返回目标；保留其余语义；实际回位误差单独观测 |

以上接口拟新增；现键 `color/targets/swap/additional_place`、`target_cube/task_flag/goal_site` 来自 [VideoPlaceButton.py](src/robomme/robomme_env/VideoPlaceButton.py) 的 `_load_scene/_initialize_episode/step`。每块独立保存起始位姿，不能两块共用一个随机goal_site；也不能把实际回位结果提前写成输入事实。

### 2.12 VideoPlaceOrder

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.demo_object_count` → `E.objects.demo_ids[]` | 演示对象数 |
| U2 | 用户决策 | `U.demo_return_policy` → `E.actions.return_pose_by_object_id` | 返回策略 |
| R1 | 规则不改，外部抽样 | `N.color/object_pose/targets/button/goal` → `E.layout`、`E.objects.color_order/demo_ids` | 方块、台、按钮、目标位置及颜色／目标选择 |
| R2 | 规则不改，外部抽样 | `N.visit_selection/answer_selection/button_insertion/swap_selection` → `E.objects.visit_ids/which_in_subset/button_after_pair_index/swap_pair_ids` | 访问序列、答案序号、插按钮的k、交换台 |
| R3 | 规则不改，外部抽样 | `N.recovery` → `E.actions.recovery` | 原失败动作选择 |
| D1 | 规则派生，不再抽签 | `N.answer_mapping/action_expansion` → `E.actions.demo_by_object/target_target_id/button_task_index/return_pose_by_object_id` | 序号转对象、插入位置、每对象返回目标 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | 当前1块target_cube；easy1块、medium/hard各3块 | video完成2个block；easy数量冲突待决定 |
| U2 | 演示结束放随机goal_site | 各自回演示开始的原位；其余不变 |
| R1 | color=`1/3/3`、targets各4；cube/台center `[0,0]`、half_size0.2；按钮 `[0.1,0]`、range `[0.05,0.3]`；goal center `[-0.1,0]`、half_size0.1、radius=`5*cube_half_size` | 按其余不变保留；目标台只抽xy，方块另抽yaw |
| R2 | 抽2～4个有序台；which_in_subset取1～序列长度；k取0～长度−1；hard随机交换两台 | 原抽法保持；两演示对象是否共享访问序列尚未指定，不能擅自决定 |
| R3 | 按dataset-gen原流 | 不变 |
| D1 | answer=`visit_ids[which_in_subset-1]`；button_task_index=`k*2+2`；每台抓→放，最后goal_site；hard交换50步；原初始化将goal_site.z设为-0.05 | U1/U2启用后按对象分别保存；button_task_index不再独立抽一次；其他顺序逻辑保留 |

以上接口拟新增；现有 `color/targets/swap`、`num_targets_to_pick/indices/which_in_subset/k/button_task_index` 来自 [VideoPlaceOrder.py](src/robomme/robomme_env/VideoPlaceOrder.py) 的 `_load_scene/_initialize_episode/step`。

### 2.13 MoveCube

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.demo_layout.{cube,peg}_position_policy` → `E.layout.demo` | 演示布局的位置策略 |
| U2 | 用户决策 | `U.execution_layout.{cube,peg}_position_policy` → `E.layout.execution` | 执行布局独立位置策略 |
| U3 | 用户决策 | `U.peg_yaw_range` → `E.layout.demo.peg_pose/execution.peg_pose` | 桌面内转角 |
| R1 | 规则不改，外部抽样 | `N.goal_regions/cube_rejection/pose_draw` → `E.layout.demo/execution` | 两套goal位置、杆／cube候选与拒绝记录 |
| R2 | 规则不改，外部抽样 | `N.way_selection/obj_selection` → `E.initializations[].way`、`E.objects.obj_flag` | 每次初始化的方法选择、场景头尾相关±1选择 |
| D1 | 规则派生，不再抽签 | `N.direction_rule/reset_rule` → `E.actions.direction1/direction2/layout_switch` | 方向按目标与块的y差决定，切第二套场景 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | peg：x±0.05、y在±0.2上扰动±0.05；cube候选中心xy各±0.1，再在half_size0.05区生成 | cube和stick尽可能边角；可行域／退让／偏置强度未定 |
| U2 | 与演示分开抽一套，原同类区域 | 执行布局也预留边角控制，不能两套误合并 |
| U3 | yaw=`[-π/4,π/4]`，即±45° | 转角更大，范围未定；原杆已与桌面平行，若要俯仰需另定 |
| R1 | goal半边长0.15／0.1；cube候选中心距goal>`5*cube_half_size`，最多128次；length0.1、radius0.01 | 用户没要求改goal／尺寸／距离判据；采样域仅按U1～U3变化 |
| R2 | 每次初始化way从peg_push/gripper_push/grasp_putdown选；场景obj_sample映射±1；尺寸先rand再乘0，dir_sample抽而未用，留trace | 不能因“更难抓”只留peg_push；无效消费不删；本环境仅接收入口恢复模式，没有inject_fail_grasp，实际恢复动作为null，不新增抽样 |
| D1 | `evaluate`按两套实际y差给±1；`step`切换已生成执行位姿 | 方向不再随机抽；难抓程度、可达性和实际切换帧属于运行观测 |

以上接口拟新增；现变量 `peg_init_poses/peg_init_poses_2`、`cube_init_pose/cube_init_pose_2`、`goal_site_1_pose_p/q`、`goal_site_2_pose_p/q`、`way_idx/obj_sample` 来自 [MoveCube.py](src/robomme/robomme_env/MoveCube.py) 的 `_load_scene/_initialize_episode/evaluate/step`。`build_peg` 的长轴原在局部x轴，现只加yaw，不应把“平行桌面”写成新功能。

### 2.14 InsertPeg

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.peg_count` → `E.objects.n_pegs` | 杆数 |
| U2 | 用户决策 | `U.near_target_distractor.{reference_id,radial_range,azimuth_policy}` → `E.initializations[].pegs[].pose` | 每次初始化中新杆相对目标杆的位置约束 |
| U3 | 用户决策 | `U.peg_yaw_range` → `E.initializations[].pegs[].pose` | 杆转角 |
| R1 | 规则不改，外部抽样 | `N.box_pose/peg_pose/rejection` → `E.initializations[].box_pose/pegs[]` | 每次初始化分别抽孔／各杆 |
| R2 | 规则不改，外部抽样 | `N.color/obj_selection/direction_selection` → `E.objects.head_rgb`、`E.initializations[].obj_flag/direction` | 场景共享头色、每次初始化两个±1选择 |
| D1 | 规则派生，不再抽签 | `N.tail_color_rule/target_rule/box_geometry` → `E.objects.tail_rgb/target_peg_id`、`E.layout.box_geometry` | 互补色、固定目标、派生孔尺寸 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | 现 `offsets=[0.1,0,-0.1]` 生成3根 | 多一根，总共4根 |
| U2 | 无近目标专用生成策略；原杆间距离>0.075 | 新增stick更近target stick；具体距离／方位未定，不擅自放松碰撞间距 |
| U3 | yaw±45°，原长轴已平行桌面 | 更大转角，具体范围未定；俯仰需求若有则另定 |
| R1 | 孔xy±0.1、yaw90°±20°；杆x±0.2、y±0.3；距孔>0.06，杆间>0.075，最多512次 | 孔／原抽样和拒绝规则不改；新增杆按U2约束，姿态按U3 |
| R2 | head=rand(3)；每次初始化obj_sample/dir_sample由randint(0,2)映射±1；尺寸length0.05、radius0.01先随机再乘0；random_peg_idx抽后覆盖为0 | 保留原流及被覆盖值；目标仍peg_0；只记录入口恢复模式，本环境无inject_fail_grasp，实际恢复动作为null，不新增抽样 |
| D1 | tail=`1-head`；目标恒peg_0；孔尺寸由length/radius计算 | 这些规则不变，不再给尾色、目标ID各抽一次；实际抓取／插入结果单列观测 |

以上接口拟新增；源变量及规则见 [InsertPeg.py](src/robomme/robomme_env/InsertPeg.py) 的 `_load_scene/_initialize_episode` 与 `utils/object_generation.py::build_peg`。不能只保存构造期临时杆位姿，必须保存每次初始化的真实输入。

### 2.15 PatternLock

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.demo_duration_seconds_range`、`U.demonstration_duration_policy` → `E.actions.demo_duration_target` | 演示时长目标及实现策略 |
| R1 | 规则不改，外部抽样 | `N.path_selection` → `E.actions.path_nodes`、`E.sampling_trace.path_attempts` | 起终点、DFS邻居乱序及拒绝过程 |
| D1 | 规则派生，不再抽签 | `N.grid_geometry/path_binding` → `E.layout.nodes[]`、`E.actions.demo_nodes/execution_nodes` | 规则网格位置、索引映射、动作列表 |
| D2 | 规则派生／运行观测 | `N.motion_template` → `E.actions.demo_actions`；`O.demo_frames/fps/duration_s` | 动作由路径展开；秒数由实录帧数计算 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | 目前没有秒数目标，由原路径与求解运动形成 | 最难情形video演示20～30s；如何调节节奏未定 |
| R1 | easy/medium/hard：grid=`3/4/5`，节点数 `[2,4]/[3,5]/[4,8]`；起终点randperm，允许对角线的随机DFS；最多1000次，耗尽用最后路径 | 用户只指定最难视频时长，未指定改grid/length/拓扑；不换成所有路径均匀抽样 |
| D1 | center `[-0.1,0]`，间距0.1；节点由行列公式定位，演示和执行复用路径，首目标保留NO RECORD | 网格位置不是随机值；U1不自动授权改路径长度或加重复帧 |
| D2 | 每目标solve_swingonto两次screw运动并close_gripper；实际fps按交付录像器30 | 未来验证20～30秒要实际600～900演示帧；不能改fps或伪造帧数；时长实测进入O |

以上接口拟新增；源锚点：[PatternLock.py](src/robomme/robomme_env/PatternLock.py) 的 `config_*`、`_load_scene/step`，`utils/adjacent.py::find_path_0_to_8/dfs_path`。默认最难档按官方hard，不先添加新档；未来若要另一种“最难”配置再单独决定。

### 2.16 RouteStick

**先列字段与归属**

| 编号 | 归属 | 配置字段 → 本局字段 | 类型／生成方式 |
| --- | --- | --- | --- |
| U1 | 用户决策 | `U.demo_duration_seconds_range`、`U.demonstration_duration_policy` → `E.actions.demo_duration_target` | 演示时长目标与策略 |
| R1 | 规则不改，外部抽样 | `N.length/walk` → `E.objects.L`、`E.actions.nodes/directions` | 段数、起点、合法邻居选择、每段方向 |
| R2 | 规则不改，外部抽样 | `N.yaw/obstacle_color` → `E.layout.rotation_deg/obstacle_rgb` | 整体旋转与柱RGB |
| D1 | 规则派生，不再抽签 | `N.grid_geometry/node_mapping` → `E.layout.node_poses/obstacle_poses`、`E.actions.node_slots`、`E.objects.allow_backtracking` | 网格与索引映射；backtrack从难度配置复制，不抽签 |
| D2 | 规则派生／运行观测 | `N.motion_template/trail_steps` → `E.actions`；`O.demo_frames/fps/duration_s` | 路径动作；实际演示时长 |

**再列当前值与未来决策**

| 编号 | 当前原值／规则 | 用户之后会改什么／哪些不改 |
| --- | --- | --- |
| U1 | 无秒数目标；官方hard段数 `[4,7]`、backtrack=True；现xhard `[8,10]`不属原train | 最难情形video演示20～30s；速度／等待等实现方式未定，不能直接把长度改为xhard代替 |
| R1 | easy/medium/hard：length=`[2,3]/[4,5]/[4,7]`，backtrack=`False/False/True`；节点0/2/4/6/8，邻居±1，端点强制反向；方向每段独立rand<0.5 | 用户本次没有决定新段数／拓扑／方向分布；保留原抽法，禁用旧候选的跨局方向均衡 |
| R2 | yaw=`u×60−30`度，4柱RGB各rand(3) | 不改旋转域、颜色池或抽法 |
| D1 | 1×9网格，center `[-0.1,0]`、间距0.07，柱位1/3/5/7、半径0.015高0.1；L段→L+1节点；allow_backtracking直接取difficulty的backtrack | 按原几何和旋转计算，不再独立随机摆节点或柱；回退开关保持原值 |
| D2 | 每段45曲线点+5末端保持，IK失败可跳点；官方尾迹40步，当前10步须恢复 | U1只规定最终演示20～30s；不拿理论50点当实际50帧，不倍速改编码凑时长 |

现有映射：N.length/walk 对应 `parameters.RouteStick.configs[d].length/backtrack`、`parameters.RouteStick.walk`；几何与颜色来自 `positions.RouteStick`。现E已有 `layout.rotation_deg/obstacle_rgb`、`objects.L/allow_backtracking`、`actions.nodes/node_slots/directions`；U1、显式node/obstacle位姿及视频观测为拟新增。锚点：[RouteStick.py](src/robomme/robomme_env/RouteStick.py) 的 `_load_scene/step`、`utils/route.py::generate_dynamic_walk`、`_routestick_group`。

### 2.17 未来决策只开放 U 字段，派生关系必须同步

| 用户决策 | 对应规则／派生关系 | 仍需决定或保持的边界 |
| --- | --- | --- |
| 增加次数或对象数 | 更新完整对象列表、拾取列表、交换列表与动作展开 | 不把新数值塞进现有 `if count==2` 后就认为功能成立；StopCube运动段须覆盖选定次数 |
| corner／clutter | 用户改区域或布局策略，外部生成具体xy／yaw | 桌面可行域、可达性、原碰撞约束保留；未定边界、密度、距离不编造默认值 |
| distractor／任意颜色 | 用户给颜色策略，外部产生逐对象颜色与角色 | “其他颜色”相对目标池定义；颜色不是对象ID；池、数量、放置位置未定时保留待决 |
| 两块演示，各自回原位 | 每对象起始位姿 → 每对象返回目标，不再随机抽返回点 | easy原只有一块；两对象共享还是分别抽动作序列，须未来明确；其余语义保持 |
| 交换速度×1.5 | 时间倍率统一派生动作、藏块跟随和交换窗口 | 只适用于两个UnmaskSwap；不自动用于VideoRepick；离散步取整须决定 |
| PatternLock／RouteStick演示20～30秒 | 先决定时长策略，再按实际录制帧数／fps验收 | 现录像器30fps对应600～900实际演示帧；`save_robomme_video`默认20fps不能混算；不改fps／补重复帧凑长度 |

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

拟新增 `scripts/configs/newtask-v3/native_sampling.json`，覆盖十六环境。新快照按 `tasks[env].decision` 与 `tasks[env].native` 分块：前者是第二节的 U 字段，后者是维持原状的规则与常量。传给 `gym.make(..., sampling_config=...)` 的是本环境的这两个子块。**这是拟定的新格式，不是现有 schema 3 的真实键。** 现有四环境的 `parameters[task]/positions[task]` 按第二节映射转换，其余十二环境从源码变量提取；旧快照与旧候选保持原版本、原内容，不就地改写。

原生源码是默认值的依据，两块原值都从固定来源提取并校验，不维护两套手填默认值。原值对拍模式下，U也不可改；未来新值模式才允许修改U。N任一取值域、选择规则、单位、dtype、随机源、端点语义或拒绝条件改变，都必须显式列为新的用户决策，不能混在“仅随机外移”中。缺失／未知键、类型错误、跨任务规格、来源不匹配直接报错；每任务解析结果深拷贝，禁止污染类级配置。

```text
sampling_config.tasks[env]
  decision   ← 用户可改的范围／策略；首轮填原值
  native     ← 原抽样、几何、派生和恢复规则
        ↓ 外部供值器
episode_spec
  layout / objects / actions / initializations
        ↓ 冻结记录作为真实输入
环境按固定对象和动作运行
        ↓ 只读记录
运行证据：实际位置、时间、成功失败、RNG核验
```

例如 VideoUnmaskSwap 的 `decision.swap_count_range` 是配置；`objects.n_swaps` 是抽出的本局值；`actions.swap_pairs` 是按布局、发起者及最近邻规则派生的序列。不能让用户分别填写这三处形成冲突的真值。`partner` 必须在原规则规定的交换时点解析；第一轮由完整原生运行导出，回注时在同一时点核验，不在reset时按旧位置猜搭档。

拟用带版本的新记录保存完整 `episode_spec`，至少含以下内容：

| 字段 | 固定什么 | 不允许的替代 |
| --- | --- | --- |
| `identity` | `split=train`、task、原 episode、实际 seed、difficulty、metadata 散列、历史基线提交 | 从 episode 重新计算 seed 或 difficulty |
| `layout` | 对象创建顺序、稳定 ID、位置与完整姿态、目标区域、初始位置与演示后重置位置 | 只记最终画面，遗漏创建输入和第二次初始化 |
| `objects` | 颜色、目标／干扰物角色、容器藏物映射、实际数量与重复次数 | 只记数量，不记具体是哪几个对象 |
| `actions` | 抓放目标序列、交换双方、路线与方向、事件窗口、失败恢复动作索引 | 由颜色名称或最近对象再次猜目标 |
| `initializations` | 以初始化序号保存每次颜色排列、孔／杆位姿及输入边界；即第二节的 `E.initializations` | 构造期和显式reset共用一条抽样结果 |
| `sampling_trace` | 按原调用阶段编号的随机源、调用签名、原始结果、拒绝尝试、调用前后状态指纹 | 只在结尾恢复 generator 状态，忽略中间随机消费 |
| `provenance` | 配置／源码／依赖／规格内容散列及数组 dtype、shape、编码约定 | 用四舍五入的浮点文本承诺逐位相同 |

数组记录原 dtype 与 shape，采用可无损往返的表示；浮点比较按原始位模式，Python 标量保留原类型与运算次序。坐标以米计，角度字段必须明确度或弧度，四元数明确原 API 分量顺序。这里没有训练模型或可训练参数，不能用张量形状一致代替仿真行为一致。

逐局唯一数据文件仍采用 Git 跟踪的 `candidates.jsonl`，但为原始 train 新增显式版本和 `identity_source=train_metadata`。它只是承载固定记录，**不能复用旧封套的公式 seed、100 条 block、train/test 配额和碰撞必须 PASS 规则**。`scripts/injection/candidates/io.py::validate_candidates` 当前把这些规则写死，必须按版本分流校验；旧运行十保持原版本和原字节。生成、reset 核验都从同一记录投影参数；未来策略端若接入也消费同一身份，不另手填 seed。候选导出失败的身份保留在全集账本中，不伪造完整规格。

### 4.2 外部供值与原始 train 对拍怎样兼容

“外部”指环境接收到冻结的本局值，不在消费规格时临时决定一个新目标、新布局或新交换搭档。第一轮不能用独立新seed重抽原train，因此外部记录来源固定为原生C路的只读导出；后续新值模式才按已批准的U字段由外部生成器生成新样本。两种模式明确区分：

| 模式 | 外部规格怎样产生 | 原随机规则怎样处理 | 能宣称什么 |
| --- | --- | --- | --- |
| 原值对拍 | 原官方身份驱动C路，把每个原取值点的结果导出至外部规格，完整事件后封存 | D路按原位置消费冻结值；原RNG仍照原次序运行作兼容与核验，其返回值不得替代E作为场景输入 | 同一官方样本注入前后相同 |
| 未来改值 | 外部供值器读U新值和N原规则，生成新的随机输入，再派生D类字段；延迟依赖实际状态的字段须经过原事件时点解析／冻结流程 | 未改的N不变；不继承旧配额／分层／方向均衡。算法或分布若要改，另列用户决策 | 固定新规格可重放；不声称与原train逐条相同 |

因此“运行中仍有RNG核验”不表示场景输入仍可忽略外部规格。拒绝采样的失败尝试、单候选抽样、被后续语句覆盖的抽样全部保留；只读导出不额外抽随机数、不增加物理step。完成对拍前，不删除兼容抽样来做性能优化，也不以末尾set_state掩盖中途漏抽。

```text
原来：原 generator → 原调用点抽样 → 建对象／生成动作
导出：原 generator → 同一调用点抽样 → 只读记下结果 → 原对象／动作
回注：外部冻结值 → 对应调用点赋值／绑定 → 同一对象／动作
      原 generator → 同序抽样作兼容核验 ────┘（只校验，不替代冻结值）
```

这不是减少抽样次数的优化；目的是第一轮同时做到完整冻结、原始随机流不漂移。一个 `(阶段, 初始化序号, 对象ID, 事件序号)` 只消费一次对应记录。交换搭档在交换发生时才知道的，导出完整运行中当时的实际绑定；D 路在同一时点核验并使用该绑定，不在构造时按初始坐标重选。第一次导出必须完成相关事件后才能把规格标为完整。

特别要覆盖 `BinFill` 两次初始化各自的颜色排列、`VideoRepick/hard` 的十五块原生路径、`InsertPeg` 乘零却仍消费随机数的尺寸抽样、被强制改为 0 的目标索引抽样，以及 `inject_fail_grasp` 的真实选择。现有“注入后跳过一部分抽样”分支不能直接沿用为 D 路。

未来更改数量、布局和动作次数后，每局结果可能不同；使用同一抽样规则也不意味着得到相同随机流轨迹。第一轮只实现原值导出／消费、U与N的结构与校验，不实现角落加权、额外干扰物生成、三次抓取、多对象视频或时长调节算法。第二节列出的未来值只进入方案，不提前写进生效配置。

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
| 字段归属完整 | 第二节每项都能映射至U或N，以及对应E或O；用户新值仅在U，原值阶段U/N均为原值；最近邻／补集／时间表等不独立抽签 | `FIELD_OWNERSHIP=PASS tasks=16 unmapped=0 native_rule_overrides=0` |
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
| 3 | 十六环境逐个切出 `sampling_config` 的decision／native，按第二节映射；每环境先 B↔C，再进入下一环境 | `FIELD_OWNERSHIP`、`SAMPLING_ORIGINAL`；对应原始样本 B↔C 通过 |
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
| `scripts/generate_dataset_newseed.py::EpisodeJob`、`extract_native_sampling`、`load_sampling_config`、`load_episode_specs`、`_worker` | 按decision／native提取十六环境快照，适配已有四环境原键；扩展带实际身份的新规格版本，提供原train作业与恢复证据 | 原值模式两块都锁原值，默认旧入口兼容；保留前六条失败恢复，不调用公式补位及BinFill复制 |
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

首次方案落地（11.20）的静态验证退出 0：`PLAN_STRUCTURE=PASS environments=16 fixed_rows=64 local_links=23 code_line_refs=0`；当时从固定 `dataset-gen` Git 对象重读十六份 metadata，`PLAN_BASELINE=PASS train=1600 recovery_z=48 recovery_xy=48 recovery_off=1504`。`git diff --check` 通过；相对初始提交的 `src/`、`scripts/`、`pyproject.toml`、`uv.lock` 零改动。这里是首次版本的核验记录，不把其64组概括项当作本次字段清单。

本次字段拆分（11.23）共16环境、32张表、101个字段组：U用户决策46组，R原规则外部抽样35组，D规则派生／观测20组。每组在当前值表中有同编号对应；已复核四环境的旧键与新格式映射，其余十二环境标为拟新增接口。只读源码核对纠正了ButtonUnmaskSwap左按钮位置和PickHighlight高亮时序，并明确MoveCube／InsertPeg仅接收恢复模式、没有随机失败抓取注入；不会因新增字段补出原来不存在的事件。

文档核验退出0：`FIELD_SPLIT=PASS environments=16 tables=32 field_groups=101 user_groups=46 random_groups=35 derived_groups=20`、`DOC_CHECK=PASS matching_rows=101 local_links=20 baseline_section_unchanged=1 code_line_refs=0`。只改方案与账本；本次没有生成配置、候选或数据，没有运行代码测试或真实仿真，文档核验不代表未来对拍已经通过。
