# 全环境配置拆分与原始 train 对拍方案

> 本方案以用户本轮要求为准，只规划，不实施。工作副本为 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，核验代码为 `a4a6e9fab630e9399ca538ab2cc9d008e9638713`，当前分支为 `newtask-v2.1refractor`，commit 编号沿用仓库现行 `<大版本>.<小版本> <中文描述>` 体例。方案于 `11.20` 首次落地，后续仅修订本文件及必要账本；`11.24` 将逐环境字段合并为四列单表；本次 `11.25` 按 [AGENTS.md](AGENTS.md) 强制规则第 10 条把全文重排为「第一部分（给人看）／第二部分（技术细节，供 agent 追踪）」，第二节字段表原样保留，运行代码未变，不创建分支。**方案之后开始实施时，先从包含本方案的提交切出用户指定的 `newtaskRelease-v3`，再改代码；每一步都须单独获批。**
>
> 新分支的第一轮目标是：**十六个环境都能显式传入 `sampling_config` 与 `episode_spec`，从官方原始 train 的 16×100＝1600 条实际身份中按每个 task 每个难度约 3 条抽 144 条重放，与官方 `dataset-gen` 分支的生成及测试结果对拍，保留其中的 fail recover，证明注入前后保持一致。** 权威来源固定为 [RoboMME/robomme_benchmark 的 dataset-gen 分支](https://github.com/RoboMME/robomme_benchmark/tree/d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa)，本轮核验提交 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`；既有测试报告另记录其实际运行提交，见第四节及第二部分 9.5。外部依赖锚点为当前 `uv.lock`／`pyproject.toml` 指纹与官方对应指纹，见第二部分 9.5 末段。本文列出的更难布局、更多物体、更多动作及视频时长要求，只决定接口要留出什么能力，第一轮全部不启用。`src/robomme/` 的每一项源文件改动和运行时覆盖仍须按 [AGENTS.md](AGENTS.md) 强制规则第 11 条逐项批准，录像器保持冻结。

# 第一部分（给人看）

## 一、总览、已定死口径与读表说明

**一句话方案**：把每个环境的随机规则拆成「配置快照 `sampling_config`（`decision` 可改参数＋`native` 原规则）」和「每局规格 `episode_spec`（冻结的本局值）」两个显式接口，先从官方 `dataset-gen` 的1600条原身份中固定144条，走 A1／A2／B／C／D 五路生成并逐位对拍，证明该子集的拆接口与原值回注不改数，之后才允许在 `decision` 里启用第二节的拟修改值。

**已定死口径**（每条注明依据所在小节；用户原话逐字保留）：

1. 身份与生成行为以官方 `dataset-gen` 提交 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa` 为准。用户原话：「我说的是原始的[https://github.com/RoboMME/robomme_benchmark](https://github.com/RoboMME/robomme_benchmark) train16*100」「[https://github.com/RoboMME/robomme_benchmark/tree/dataset-gen](https://github.com/RoboMME/robomme_benchmark/tree/dataset-gen)和这个branch的测试结果对拍」「这个里面也有fail recover」。依据第四节，细节见第二部分 9.1。
2. 身份逐条读官方 metadata 的 `(task, episode, seed, difficulty)`，170 条 seed 不等于公式值也照原记录用，每条只跑该 seed 一次、失败不换 seed。依据第四节，细节见第二部分 9.1。
3. fail recover 保持原样：每环境 episode 0～2 为 z、3～5 为 xy；官方1600条全集有96条配置恢复，本次144条子集实际为80条（z48、xy32、关闭64），不关闭所选身份的恢复，也不把配置恢复等同于实际触发。依据第四节，细节见第二部分9.1、9.4；xy方向与偏移消费见8.2。
4. 五路对拍 A1／A2／B／C／D，验收分母按用户 11.28 拍板「不用全部验证 每个task每个难度验证3条左右即可」固定为 16×3×3＝144 条、共 720 次生成，全集 1600 条改为可选后续；算力按用户 11.29 拍板「改为使用这4个spgpu来跑不要在本机」「改为4*4 16worker」：greatlakes spgpu 4 个占位 job × 4 worker，本机不跑，前提见第四节 P0；`A↔B` 证恢复原行为，`B↔C↔D` 证接口拆分与回注不改数。依据第四节，细节见第二部分 9.2、9.3。
5. 两个接口的分工：`sampling_config.tasks[env]` 分 `decision`／`native` 两块，`episode_spec` 带版本记录 `identity/layout/objects/actions/initializations/sampling_trace/provenance`；原值对拍模式下 `decision` 也不可改。依据第三节，细节见第二部分 8.1。
6. 第一轮只做原值导出／消费，第二节「拟修改」列的值全部不启用；外部记录来源固定为 C 路只读导出，不用新 seed 重抽。依据第二节与第三节，细节见第二部分 8.2。
7. 既有 `dataset-gen` 报告 `status=failed`（217242 个元素非零差异、10 条帧数不符、阈值 `1e-8`）原样保留，不为得到 PASS 改阈值、关恢复或换样本。依据第四节，细节见第二部分 9.5。
8. `RouteStick.py::step` 白球尾迹现为 10 步、官方为 40 步，恢复原值须单列审批，不把 10 步冒充原始行为。依据第四节，细节见第二部分 9.2。
9. 录像器 `RecordWrapper.py` 全程冻结；`src/robomme/` 每处改动逐项批准，计划中的改动清单不等于批准。依据第二部分〇。
10. 实施开始前先切 `newtaskRelease-v3`，本轮不切分支、不生成配置或数据、不跑仿真。依据第五节步 0、第六节。
11. 用户对审查后的验收选择原话：「允许完成：本次144条严格对拍通过，缺失的历史核对明确写“未验证”（推荐）」。本次严格对拍及历史可投影字段仍须通过；历史动作数值缺证单列 `NOT_RUN`，不计为通过，也不阻塞完成。依据第四节R1a～R1c与第二部分9.5。

**读表说明**：
每个环境只使用四列：**修改后的字段｜什么含义｜现在的值｜是否修改／拟定修改后的值**。最后一列直接说明以后要改什么，或注明规则不改、只由外部生成本局值；不再用分类编号前后查表。

表中的 `sampling_config` 是传给当前环境的配置，即总文件 `tasks[env]` 下的内容；`episode_spec` 是这一局的具体输入。`decision` 保存后续可改参数，`native` 保存原规则。箭头后的字段是配置产生的本局结果；成组字段沿用斜线或花括号表示，未给出的具体范围仍标待定。这些是拟定字段，本轮不改代码或生效值。

第一轮仍按官方 `dataset-gen` 的身份（每 task 每难度约 3 条，共 144 条）和原fail recover对拍。表中写“拟修改”的值都留到后续启用；原随机规则、派生计算和实际运行观测的技术边界见第三节，字段到源码的映射见第二部分「二」。

## 二、各环境字段表

每个环境只列一张表。“是否修改”指之后的布局与难度调整；第一轮原始 train 对拍仍全部使用现在的值。字段名是拟定接口，尚未实施。

### 2.1 BinFill

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.layout_mode`<br>→ `episode_spec.layout.mode`、`episode_spec.layout.dynamic` | 方块的摆放模式及开局是否全部出现 | 原模式由 `dynamic=randint(0,2)` 决定；方块中心 `[-0.1,0]`、半边长 `[0.2,0.25]` | **是，拟修改**：全部 clutter；密集度／区域未定；开局全出现对应 dynamic=False，不能单凭此值认定 clutter |
| `sampling_config.decision.spawn_cubes`<br>→ `episode_spec.objects.spawn_total` | 本局生成的方块总数范围 | easy／medium／hard：`[4,6] / [8,10] / [10,12]` | **是，拟修改**：固定 12 块，即 `[12,12]` |
| `sampling_config.decision.color`<br>→ `episode_spec.objects.colors_present` | 本局可出现的颜色数量 | easy／medium／hard：`1 / 2 / 3`；原池红、蓝、绿 | **是，拟修改**：颜色数 3；没有另行要求改颜色池 |
| `sampling_config.decision.put_in_numbers`<br>→ `episode_spec.objects.put_in_total` | 本局需要投入孔板的方块总数范围 | easy／medium／hard：`[1,3] / [2,4] / [3,5]` | **是，拟修改**：投入总数 `[5,7]` |
| `sampling_config.native.put_in_color`、`sampling_config.native.color_selection`<br>→ `episode_spec.objects.target_pool`、`episode_spec.objects.spawn_count`、`episode_spec.objects.target_count` | 投入哪些颜色，以及每种颜色生成和投入多少块 | 投入颜色数 `[1,1] / [1,2] / [2,3]`；原颜色选择与分配顺序；选中目标色可分到 0 块 | **规则不改，只外部生成本局值**：未要求修改 `put_in_color` 或分配规则；按最终的方块总数、颜色数和投入总数生成结果 |
| `sampling_config.native.button`、`sampling_config.native.board`、`sampling_config.native.cube_pose`<br>→ `episode_spec.layout.button_xy`、`episode_spec.layout.board`、`episode_spec.layout.cubes[]` | 按钮、孔板与方块的位置、朝向及方块创建顺序 | 按钮中心 `[-0.2,0]`、randomize_range `[0.1,0.4]`、scale=1.5；板基位 `[0.15,0,0]`，偏移 `x=u×0.2−0.2,y=u×0.4−0.2,yaw=u×40−20` 度；板边0.1、孔边0.08、厚0.05；方块随机yaw | **规则不改，只外部生成本局值**：按钮和孔板规则不变；方块区域随后续布局模式调整 |
| `sampling_config.native.initialize_color_order`<br>→ `episode_spec.initializations[].color_order`；`sampling_config.native.recovery`<br>→ `episode_spec.actions.recovery` | 每次初始化的颜色顺序，以及原失败恢复选中的动作 | 原 `_initialize_episode` 每次 `randperm`；fail recover 按 dataset-gen 原模式／原调用点 | **规则不改，只外部生成本局值**：排列和恢复规则不改；新增按初始化序号存储，不复用一个排列 |
| `sampling_config.native.put_in_order`<br>→ `episode_spec.actions.pick_place[]` 的 `pick/put_in` | 每一步抓哪块方块、按什么顺序投入孔板 | 按初始化颜色顺序，取该色创建列表前 `target_count[color]` 块 | **不单独修改，按规则计算**：保持原规则；`actions` 必须实际消费，不能仅写在规格里 |

### 2.2 PickXtimes

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.color`<br>→ `episode_spec.objects.color_order` | 从原颜色池中选几种颜色 | `config_*['color']`：easy／medium／hard 为 `1/3/3`；选中颜色各1块 | **是，拟修改**：color=3 |
| `sampling_config.decision.number_range`<br>→ `episode_spec.objects.num_repeats` | 同一目标方块重复抓放多少次 | `number_min/max`：`[1,3]/[1,3]/[4,5]`，原 `torch.randint(min,max+1)` | **是，拟修改**：num `[6,15]` |
| `sampling_config.decision.target_cube_position_policy`、`sampling_config.decision.goal_position_policy`<br>→ `episode_spec.layout.cubes[]`、`episode_spec.layout.goal` | 目标方块与放置圆盘各自的位置采样规则 | 两者中心 `[-0.1,0]`、半边长0.2；方块随机yaw，圆盘只抽xy | **是，拟修改**：target 尽可能推向边角；`target_cube` 还是圆盘 `target` 待明确，边界退让／偏置强度未定 |
| `sampling_config.decision.distractor.{count,palette,placement}`<br>→ `episode_spec.objects.distractors[]` | 额外干扰物的数量、颜色和放置位置 | 没有新增其他颜色干扰物；现有未选中的原色块为非目标 | **是，拟修改**：增加其他颜色 distractor；数量／颜色池／生成位置未定 |
| `sampling_config.native.color_and_target_selection`<br>→ `episode_spec.objects.color_order/target_cube_id`；`sampling_config.native.button`<br>→ `episode_spec.layout.button_xy` | 颜色排列、目标方块选择和按钮位置 | 保留 `shuffle_indices/target_color_idx/target_cube_idx` 原顺序，前置颜色抽样被覆盖也保留；按钮中心 `[-0.2,0]`、range `[0.1,0.4]`、scale=1.5 | **规则不改，只外部生成本局值**：原目标索引抽法作用于target_eligible_ids；新增其他色distractor不能混入目标候选；位置按目标方块与放置圆盘各自的位置采样规则改变 |
| `sampling_config.native.cube_pose/target_pose/recovery`<br>→ `episode_spec.layout`、`episode_spec.actions.recovery` | 方块和圆盘的具体位置、方块朝向及原失败恢复选择 | cube候选每次抽xy与yaw，目标圆盘只抽xy；圆盘radius=`2*cube_half_size`；保留原间距与恢复调用 | **规则不改，只外部生成本局值**：采样器及恢复规则不变，使用已决策的区域 |
| `sampling_config.native.task_expansion`<br>→ `episode_spec.objects.target_eligible_ids/distractor_ids/non_target_ids`、`episode_spec.actions.pick_place[]` | 哪些对象可以成为目标、哪些是干扰物，以及完整抓放顺序 | 原所有生成块均为目标候选，额外distractor为空；选定目标后取候选补集；反复抓同一 `target_cube` 放到 `target`，末尾按按钮 | **不单独修改，按规则计算**：未来non_target_ids=未选中原候选+distractor_ids；重复次数随 `number_range` 调整，新增干扰物不成为正确目标 |

### 2.3 SwingXtimes

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.number_range`<br>→ `episode_spec.objects.num_repeats` | 摆动多少轮；一轮右、左各一次 | `number_min/max`：`[1,3]/[1,2]/[3,3]` | **是，拟修改**：number `[4,10]`；每轮右、左各一次，合计8～20次落点 |
| `sampling_config.decision.distractor.{count,palette,placement}`<br>→ `episode_spec.objects.distractors[]` | 额外其他颜色干扰物的数量、颜色池和位置 | 原无新增其他颜色干扰物 | **是，拟修改**：增加其他颜色 distractor；具体数目／颜色池未定 |
| `sampling_config.native.color_and_target_selection`<br>→ `episode_spec.objects.color_order/target_cube_id` | 颜色排列和目标方块选择 | 颜色数仍 `1/3/3`，原红蓝绿池，每色1块；前置颜色选择被最终目标选择覆盖仍留消费 | **规则不改，只外部生成本局值**：本次未要求改颜色数或目标抽法 |
| `sampling_config.native.cube_region/target_regions/button`<br>→ `episode_spec.layout.cubes[]/targets[]/button_xy` | 方块、两个圆盘和按钮的位置及方块朝向 | 方块中心 `[-0.1,0]`、半边长0.25；圆盘中心 `[-0.1,-0.2]` 和 `[-0.1,0.2]`、半边长0.1、radius=`2*cube_half_size`；按钮中心 `[-0.2,0]`、range `[0.1,0.4]` | **规则不改，只外部生成本局值**：原区域、几何和位置抽法不改 |
| `sampling_config.native.recovery`<br>→ `episode_spec.actions.recovery` | 原失败恢复选中的抓取动作 | 按原 generator 与 train 恢复模式选任务 | **规则不改，只外部生成本局值**：恢复规则不改 |
| `sampling_config.native.side_order/task_expansion`<br>→ `episode_spec.objects.target_eligible_ids/distractor_ids/non_target_ids`、`episode_spec.actions.target_right/target_left/swings[]` | 左右目标、正确目标候选、干扰物和完整摆动顺序 | `max_swings=2*num_repeats`；右→左；高度0.1；阈值 `distance=0.03,z=0.12`；原非目标取目标候选补集 | **不单独修改，按规则计算**：新distractor_ids不进入target_eligible_ids，合并到non_target_ids；左右判定、动作与成功阈值不改 |

### 2.4 StopCube

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.move_interval_choices`<br>→ `episode_spec.actions.move_interval` | 方块运动速度的候选档位 | `_initialize_episode::move_interval_list=[60,80,120]` | **是，拟修改**：最快现有档，候选只留 `[60]` |
| `sampling_config.decision.stop_time_range`<br>→ `episode_spec.actions.stop_time` | 方块第几次经过目标时停止 | `randint(2,6)`，即闭区间 `[2,5]` | **是，拟修改**：number `[6,15]`，这里映射停止序号 |
| `sampling_config.native.target/button/color`<br>→ `episode_spec.layout.target_xy/button_xy`、`episode_spec.objects.cube_rgb` | 目标和按钮位置，以及方块颜色 | 目标xy各 `uniform(-0.1,0.1)`；cube色 `rand(3)`；按钮中心 `[-0.2,0]`、range `[0.1,0.4]`；目标姿态 `[0,90,0]` 度为固定输入 | **规则不改，只外部生成本局值**：不改这些域与抽法 |
| `sampling_config.native.route_rotation`<br>→ `episode_spec.actions.rotation_deg`；原无效抽样<br>→ `episode_spec.sampling_trace` | 运动路线的整体旋转角和需保留的原随机消费 | 旋转 `uniform(-30,30)` 度；`randint(27,33)` 后把 interval 覆盖为30 | **规则不改，只外部生成本局值**：不改旋转域；无效抽样不变成用户参数 |
| `sampling_config.native.motion_segments/time_rules`<br>→ `episode_spec.actions.segments[]/steps_press/stop_window` | 路线端点、往返段数、按按钮时刻和停止窗口 | 路线 `[0,-0.3]→[0,0.3]` 旋转平移至目标；现5段；`steps_press=move_interval*(stop_time-0.5)`，窗口 `[move_interval*(stop_time-1),move_interval*stop_time]`；提前量30 | **随停止次数配套修改**：增加停止序号时必须配套覆盖到所选段，最大15；不是再抽一次段数。StopCube 原无失败抓取注入 |

### 2.5 VideoUnmask

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.pick_count`<br>→ `episode_spec.objects.n_picks` | 需要拾取的目标数量 | `config_*['pick']`：`1/1/2` | **是，拟修改**：pick=3 |
| `sampling_config.decision.bin_layout_policy`<br>→ `episode_spec.layout.bins[]` | 容器怎样摆放、摆放区域多大 | `config_*['bin']`：`3/5/15`；center `[0,0]`、half_size0.2、min_gap0.04、max_trials256 | **是，拟修改**：clutter bin；密度／区域／是否改容器数未定 |
| `sampling_config.decision.distractor.{count,palette,placement}`<br>→ `episode_spec.objects.distractors[]` | 额外干扰物的数量、颜色和藏放位置 | 前三容器藏原三色，其余空，没有新增其他颜色 | **是，拟修改**：增加其他颜色；数量及放容器内还是桌面上未定 |
| `sampling_config.native.bin_pose/color_order`<br>→ `episode_spec.layout.bins[]`、`episode_spec.objects.color_order` | 每个容器的具体位置与朝向、藏块颜色排列 | 每次先抽xy，通过拒绝检查才抽 `yaw=u×90` 度；`shuffle_indices=randperm(3)` | **规则不改，只外部生成本局值**：保留原抽法；容器采样区域采用拟定布局规则；不以固定配额替换randperm |
| `sampling_config.native.recovery`<br>→ `episode_spec.actions.recovery` | 原失败恢复选择的动作 | 原恢复模式与随机流 | **规则不改，只外部生成本局值**：保持原状 |
| `sampling_config.native.hidden_rule/pick_rule/reveal_timing`<br>→ `episode_spec.objects.hidden/empty/pick_order`、`episode_spec.actions.reveal` | 每种颜色藏在哪个容器、拾取顺序和容器展示时间 | 前3容器各藏一块，半边长 `cube_half_size/1.2`、yaw=0；抓 `bin_0`，pick>1再抓 `bin_1`；展示 `[0,64]` | **随拾取数量配套修改**：目标不是另抽的容器；未来pick3须扩完整列表。现step最多遍历15容器，若增加容器数量须配套接入 |

### 2.6 ButtonUnmask

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.pick_count`<br>→ `episode_spec.objects.n_picks` | 需要拾取的目标数量 | `config_*['pick']`：`1/1/2` | **是，拟修改**：pick=3 |
| `sampling_config.decision.bin_layout_policy`<br>→ `episode_spec.layout.bins[]` | 容器怎样摆放、摆放区域多大 | `bin=3/5/15`；center `[0,0]`、half_size0.2、min_gap0.04 | **是，拟修改**：clutter bin；数量、密度与区域未定 |
| `sampling_config.decision.distractor.{count,palette,placement}`<br>→ `episode_spec.objects.distractors[]` | 额外干扰物的数量、颜色和藏放位置 | 没有额外其他颜色干扰物 | **是，拟修改**：增加；数量、颜色池与藏放位置未定 |
| `sampling_config.native.button/bin_pose/color_order`<br>→ `episode_spec.layout`、`episode_spec.objects.color_order` | 按钮与容器的位置、容器朝向和藏块颜色顺序 | 按钮中心 `[-0.2,0]`、range `[0.1,0.1]`、scale1.5；bin位置通过才抽yaw=`u×90`度；三色randperm | **规则不改，只外部生成本局值**：原采样方法不改，容器区域由容器怎样摆放、摆放区域多大的未来决策提供 |
| `sampling_config.native.constructor_rng/recovery`<br>→ `episode_spec.sampling_trace`、`episode_spec.actions.recovery` | 构造期原随机消费，以及失败恢复选择 | 构造器 `randint(1,6)` 不决定抓数；其 `self.generator` 用于恢复；场景另有同seed局部generator | **规则不改，只外部生成本局值**：两条流分开保持，不能合并；恢复模式由入口原episode规则给定 |
| `sampling_config.native.hidden_rule/pick_rule/button_trigger`<br>→ `episode_spec.objects.hidden/empty/pick_order`、`episode_spec.actions` | 按按钮后展示和拾取哪些容器、按什么顺序 | 前三容器藏三色；按按钮→bin_0→可选bin_1；原展示窗口／最多15容器 | **随拾取数量配套修改**：保持按钮触发机制；未来第三抓只扩目标列表，不另抽拾取对象 |

### 2.7 VideoUnmaskSwap

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.swap_count_range`<br>→ `episode_spec.objects.n_swaps` | 容器交换次数的范围 | 原 `swap_min/max`：`[1,2]/[1,2]/[2,3]` | **是，拟修改**：swap `[8,12]` |
| `sampling_config.decision.pick_count_range`<br>→ `episode_spec.objects.n_picks` | 交换后需要拾取的目标数量范围 | 原 `pick_min/max`：`[1,2]/[1,1]/[2,2]` | **是，拟修改**：pick=3，即 `[3,3]` |
| `sampling_config.decision.swap_speed_multiplier`<br>→ `episode_spec.actions.swap_windows[]` | 相对原交换动作的速度倍数，决定每次交换用时 | 倍率1；每次50步 | **是，拟修改**：倍率1.5；`50/1.5`非整数，离散时间处理尚待决定 |
| `sampling_config.decision.distractor.{count,palette,placement}`<br>→ `episode_spec.objects.distractors[]` | 额外干扰物的数量、颜色和藏放位置 | 无额外其他颜色干扰物 | **是，拟修改**：增加；数量、颜色池、藏放位置未定 |
| `sampling_config.native.containers`<br>→ `episode_spec.layout.type/theta_rad/bins[]` | 容器布局形状、整体旋转、每个容器的位置与朝向 | bin=`3/4/4`；三角／直线／四点原锚点；整体旋转 `[0,180]` **弧度**，局部half_size0.07、min_gap0.02、yaw=`u×90`度 | **规则不改，只外部生成本局值**：本次未要求改变容器数或布局；与两个非Swap环境的clutter要求分开 |
| `sampling_config.native.object_selection/recovery`<br>→ `episode_spec.objects.selected/color_order/swap_initiators/target_choice`、`episode_spec.actions.recovery` | 藏物与颜色顺序、交换发起者、辅助目标和原恢复选择 | 前三容器randperm(3)，原三色排列，前两发起者局部索引映射保留，剩余发起者按原抽法 | **规则不改，只外部生成本局值**：选择规则不改；`target_choice` 和完整恢复规格拟补，现代码仍内部抽取 |
| `sampling_config.native.hidden_rule/pick_rule/partner_rule`<br>→ `episode_spec.objects.hidden/empty/pick_order`、`episode_spec.actions.swap_pairs[]` | 藏块和容器的对应关系、拾取顺序、每次谁和谁交换 | 第4容器为空；原pickup索引 `[0,1]`；partner排除自身，等距取创建顺序靠前者；pair实键 `initiator/partner/distance_m` | **随拾取数量配套修改**：最近搭档不另抽签；未来pick3扩前缀和动作绑定，不直接把旧count改3了事 |
| `sampling_config.native.swap_path`、`sampling_config.decision.swap_speed_multiplier`<br>→ `episode_spec.actions.swap_windows[]` | 每次交换的起止时间和移动轨迹参数 | 第k次 `[64+50k,64+50(k+1)]`；lane_offset0.07、smooth=True、keep_upright=True | **不单独修改，按规则计算**：路径参数不改；未来速度倍率仅改变交换时间尺度；实际帧进入观测 |

### 2.8 ButtonUnmaskSwap

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.swap_count_range`<br>→ `episode_spec.objects.n_swaps` | 容器交换次数的范围 | `swap_min/max`：`[1,2]/[1,2]/[2,3]` | **是，拟修改**：swap `[6,8]` |
| `sampling_config.decision.pick_count_range`<br>→ `episode_spec.objects.n_picks` | 交换后需要拾取的目标数量范围 | `pick_min/max`：`[1,2]/[1,1]/[2,2]` | **是，拟修改**：pick=3，即 `[3,3]` |
| `sampling_config.decision.swap_speed_multiplier`<br>→ `episode_spec.actions.swap_windows[]` | 相对原交换动作的速度倍数，决定每次交换用时 | 倍率1、每段50步 | **是，拟修改**：倍率1.5；离散步长取整规则未定 |
| `sampling_config.decision.distractor.{count,palette,placement}`<br>→ `episode_spec.objects.distractors[]` | 额外干扰物的数量、颜色和藏放位置 | 无新增其他颜色干扰物 | **是，拟修改**：增加；数量、颜色池、位置未定 |
| `sampling_config.native.buttons/container_offsets/bin_pose`<br>→ `episode_spec.layout.buttons[]/bins[]`、`episode_spec.sampling_trace` | 两个按钮与容器的位置、朝向及布局偏移 | 左按钮 `[-0.2,-0.1]`、右 `[-0.2,0.1]`，range各 `[0.05,0.05]`；bin=`3/4/4`，half_size0.07、gap0.02；锚点偏移 `u×0.1`，无整体旋转；未用分支仍消费随机数 | **规则不改，只外部生成本局值**：本次未要求改按钮／容器布局；左按钮旧方案误写y=0，本轮按源码纠正 |
| `sampling_config.native.object_selection/recovery`<br>→ `episode_spec.objects.color_order/selected/swap_initiators/target_choice`、`episode_spec.actions.recovery` | 颜色顺序、藏物容器、交换发起者、辅助目标和原恢复选择 | 构造抽swap/pick；场景另建同seed流抽布局、三色、selected、target_choice、发起索引／剩余者；恢复沿原self.generator | **规则不改，只外部生成本局值**：选择规则和索引映射不变；交换次数、拾取数量按新范围产生 |
| `sampling_config.native.hidden_rule/pick_rule/partner_rule`<br>→ `episode_spec.objects.hidden/empty/pick_order`、`episode_spec.actions.swap_pairs[]` | 藏物关系、拾取顺序和每次交换搭档 | 前三藏物、第四空；拾取selected_bins[0]及count=2时的[1]；发起者局部索引历史行为保留；partner为实际XY最近邻 | **随拾取数量配套修改**：未来补第三抓和完整交换列表；当前schedule只有1/2/3分支，设pick=3反而只生成第一抓 |
| `sampling_config.native.button_order/swap_path`、`sampling_config.decision.swap_speed_multiplier`<br>→ `episode_spec.actions` | 两个按钮的操作顺序、交换时间和移动方式 | 右按钮→左按钮；第k次 `[64+50k,64+50(k+1)]`；lane_offset0.07、smooth=True、keep_upright=True | **不单独修改，按规则计算**：按钮／路径不变，窗口按未来确定的速度倍率统一计算 |

### 2.9 PickHighlight

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.layout_mode/cube_region`<br>→ `episode_spec.layout.cubes[]` | 方块摆放模式及采样区域 | center `[-0.1,0]`、half_size0.2、min_gap=`2*cube_half_size`、随机yaw | **是，拟修改**：clutter；具体区域和密度未定 |
| `sampling_config.decision.highlight_count_range`<br>→ `episode_spec.objects.highlight_count` | 同时高亮并需要抓取的目标块数范围 | `config_*['pickup']`：`1/2/3` | **是，拟修改**：highlight number `[5,7]` |
| `sampling_config.decision.spawn_count`<br>→ `episode_spec.objects.n_cubes` | 场上方块总数 | `config_*['spawn']`：`3/4/6` | **须配套修改，具体值待定**：必须至少容纳本局高亮数，上限7不等于已决定总共7块 |
| `sampling_config.decision.block_color_policy/palette`<br>→ `episode_spec.layout.cubes[].color` | 每块方块的颜色选择规则和颜色池 | 每块独立从红／蓝／绿选 | **是，拟修改**：block颜色任意；离散池或连续RGB及分布未定 |
| `sampling_config.native.color_draw/cube_pose/target_selection`<br>→ `episode_spec.layout.cubes[]`、`episode_spec.objects.highlight_ids` | 每块的具体颜色与位姿、被选中的高亮目标 | 原 `color_choice_idx`、spawn拒绝顺序、`randperm(len(all_cubes))[:pickup]`；生成失败break，保存实际数量 | **规则不改，只外部生成本局值**：抽法按已决策的域运行，目标仍按对象ID识别，不改为颜色唯一身份 |
| `sampling_config.native.button/recovery`<br>→ `episode_spec.layout.button_xy`、`episode_spec.actions.recovery` | 按钮位置和原失败恢复选择 | 按钮 `[-0.2,0]`、range `[0.1,0.4]`、scale1.5 | **规则不改，只外部生成本局值**：保持原状 |
| `sampling_config.native.highlight_window/task_expansion`<br>→ `episode_spec.actions.highlight_windows/pick_order` | 高亮窗口、抓取顺序和非目标集合 | 所有目标共用 `[10,100]` 窗口，**同时高亮**；抓取才按target列表有序执行 | **不单独修改，按规则计算**：保持原时间规则；原方案“依次高亮”表述本轮纠正 |

### 2.10 VideoRepick

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.layout_mode`<br>→ `episode_spec.layout.mode/cubes[]` | 方块摆放模式；与是否交换分开 | easy/medium原锚点局部half_size0.07；hard中心 `[-0.1,0]`、half_size `[0.2,0.25]` | **是，拟修改**：clutter，独立于是否swap |
| `sampling_config.decision.num_repeats_range`<br>→ `episode_spec.objects.num_repeats` | 同一目标块重复抓放的次数范围 | `num_repeats.low=1,high_exclusive=4`，实际1～3 | **是，拟修改**：pick times `[4,6]`；若沿randint则low=4、high_exclusive=7 |
| `sampling_config.decision.block_color_policy/palette`<br>→ `episode_spec.layout.cubes[].color` | 每块方块的颜色选择规则和颜色池 | 非hard整局单色 `episode_spec.objects.color`；hard红蓝绿各5块 | **是，拟修改**：block颜色任意；逐块池／分布待定 |
| `sampling_config.decision.swap_enabled/swap_count_range`<br>→ `episode_spec.objects.n_swaps` | 是否交换方块，以及交换多少次 | easy `[1,2]`、medium `[2,3]`、hard0；现xhard `[4,5]`不进入原train | **是，拟修改**：是否启用swap待决；若启用则 `[8,12]`；clutter不意味着禁止swap |
| `sampling_config.native.button/layout_draw/cube_pose`<br>→ `episode_spec.layout.button_xy/type/theta_rad/cubes[]` | 按钮位置、布局角度和各方块具体位姿 | 按钮中心 `[-0.2,0]`、range `[0.1,0.1]`、scale1.5；非hard原三块锚点整体 `[0,180]`弧度；hard5轮每轮三色洗牌共15块 | **规则不改，只外部生成本局值**：按钮与抽法不改，布局模式和逐块颜色规则的修改单独标明；用户未明确新的总块数 |
| `sampling_config.native.object_selection/recovery`<br>→ `episode_spec.objects.target/swap_initiators`、`episode_spec.actions.recovery` | 目标方块、交换发起者顺序和原失败恢复选择 | 非hard用原randperm选目标，hard用原randint；重复抓同一目标，剩余两块原乱序 | **规则不改，只外部生成本局值**：不把目标选择或恢复当新增用户调参 |
| `sampling_config.native.partner_rule/swap_timing/task_expansion`<br>→ `episode_spec.actions.swap_pairs[]/swap_windows[]/pick_place[]` | 每次交换搭档、交换窗口及完整重复抓放动作 | 交换开始时按实际XY取最近搭档；每次50步；方向／轨迹沿原规则 | **不单独修改，按规则计算**：用户本次未要求VideoRepick交换速度×1.5；仅交换开关和次数改变，时间公式随长度展开 |

### 2.11 VideoPlaceButton

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.demo_object_count`<br>→ `episode_spec.objects.demo_ids[]` | 视频中演示操作多少个方块 | 当前唯一 `target_cube`，演示对象数1；easy场上也只有1块 | **是，拟修改**：video完成2个block；easy是否补块或限制档位未定 |
| `sampling_config.decision.demo_return_policy`<br>→ `episode_spec.actions.return_pose_by_object_id` | 每个方块演示完成后返回哪里 | 当前最后放同一个随机 `goal_site` | **是，拟修改**：各自回原位；原位取各对象演示开始的实际位姿，不再随机抽返回位置 |
| `sampling_config.native.color/object_pose/target_selection`<br>→ `episode_spec.objects.color_order/demo_ids`、`episode_spec.layout.cubes[]` | 方块颜色、位置、朝向和演示目标选择 | easy/medium/hard：color=`1/3/3`，每色1块；方块center `[0,0]`、half_size0.2；原目标选择调用 | **规则不改，只外部生成本局值**：其余不变；两对象的选择／顺序由扩展后的同类规则明确，不能自行新增任务语义 |
| `sampling_config.native.targets/button/goal/task_flag/swap_selection`<br>→ `episode_spec.layout`、`episode_spec.objects.task_flag/swap_pair_ids` | 目标台、按钮与终点位置，按钮前后答案及交换目标台 | targets=`3/4/4`；台center `[0,0]`、half_size0.2、radius=`2*cube_half_size`；按钮center `[0.1,0]`、range `[0.05,0.3]`；goal center `[-0.1,0]`、half_size0.1、radius=`3*cube_half_size`；hard交换 | **规则不改，只外部生成本局值**：目标台、按钮、before/after及交换规则按“其余不变”保留 |
| `sampling_config.native.recovery`<br>→ `episode_spec.actions.recovery` | 原失败恢复选中的动作 | 原dataset-gen恢复模式与抽法 | **规则不改，只外部生成本局值**：不变 |
| `sampling_config.native.task_mapping/demo_template`<br>→ `episode_spec.actions.demo_by_object/execution_by_object/return_pose_by_object_id` | 每块演示动作、任务答案和各自返回位姿 | before→target_0，after→target_1；演示 target_0→按钮→target_1→goal_site；additional_place=False；hard交换50步；原初始化goal的z改为-0.05 | **随演示对象数和返回规则配套修改**：未来扩展到两块演示，并分别改为返回各自原位；保留其余语义；实际回位误差单独观测 |

### 2.12 VideoPlaceOrder

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.demo_object_count`<br>→ `episode_spec.objects.demo_ids[]` | 视频中演示操作多少个方块 | 当前1块target_cube；easy1块、medium/hard各3块 | **是，拟修改**：video完成2个block；easy数量冲突待决定 |
| `sampling_config.decision.demo_return_policy`<br>→ `episode_spec.actions.return_pose_by_object_id` | 每个方块演示完成后返回哪里 | 演示结束放随机goal_site | **是，拟修改**：各自回演示开始的原位；其余不变 |
| `sampling_config.native.color/object_pose/targets/button/goal`<br>→ `episode_spec.layout`、`episode_spec.objects.color_order/demo_ids` | 方块、目标台、按钮、终点的布局及演示对象选择 | color=`1/3/3`、targets各4；cube/台center `[0,0]`、half_size0.2；按钮 `[0.1,0]`、range `[0.05,0.3]`；goal center `[-0.1,0]`、half_size0.1、radius=`5*cube_half_size` | **规则不改，只外部生成本局值**：按其余不变保留；目标台只抽xy，方块另抽yaw |
| `sampling_config.native.visit_selection/answer_selection/button_insertion/swap_selection`<br>→ `episode_spec.objects.visit_ids/which_in_subset/button_after_pair_index/swap_pair_ids` | 访问目标台的顺序、任务答案、按钮插入位置和交换台 | 抽2～4个有序台；which_in_subset取1～序列长度；k取0～长度−1；hard随机交换两台 | **规则不改，只外部生成本局值**：原抽法保持；两演示对象是否共享访问序列尚未指定，不能擅自决定 |
| `sampling_config.native.recovery`<br>→ `episode_spec.actions.recovery` | 原失败恢复选中的动作 | 按dataset-gen原流 | **规则不改，只外部生成本局值**：不变 |
| `sampling_config.native.answer_mapping/action_expansion`<br>→ `episode_spec.actions.demo_by_object/target_target_id/button_task_index/return_pose_by_object_id` | 每块的演示动作、答案目标、按钮步骤和返回位姿 | answer=`visit_ids[which_in_subset-1]`；button_task_index=`k*2+2`；每台抓→放，最后goal_site；hard交换50步；原初始化将goal_site.z设为-0.05 | **随演示对象数和返回规则配套修改**：未来两块演示和各自回原位启用后，按对象分别保存；button_task_index不再独立抽一次；其他顺序逻辑保留 |

### 2.13 MoveCube

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.demo_layout.{cube,peg}_position_policy`<br>→ `episode_spec.layout.demo` | 演示阶段方块与杆的位置采样规则 | peg：x±0.05、y在±0.2上扰动±0.05；cube候选中心xy各±0.1，再在half_size0.05区生成 | **是，拟修改**：cube和stick尽可能边角；可行域／退让／偏置强度未定 |
| `sampling_config.decision.execution_layout.{cube,peg}_position_policy`<br>→ `episode_spec.layout.execution` | 执行阶段方块与杆的位置采样规则 | 与演示分开抽一套，原同类区域 | **是，拟修改**：执行布局也预留边角控制，不能两套误合并 |
| `sampling_config.decision.peg_yaw_range`<br>→ `episode_spec.layout.demo.peg_pose/execution.peg_pose` | 杆在桌面内的转角范围 | yaw=`[-π/4,π/4]`，即±45° | **是，拟修改**：转角更大，范围未定；原杆已与桌面平行，若要俯仰需另定 |
| `sampling_config.native.goal_regions/cube_rejection/pose_draw`<br>→ `episode_spec.layout.demo/execution` | 演示和执行两套布局中的具体位置及位置重抽记录 | goal半边长0.15／0.1；cube候选中心距goal>`5*cube_half_size`，最多128次；length0.1、radius0.01 | **规则不改，只外部生成本局值**：用户没要求改goal／尺寸／距离判据；采样域仅按演示阶段方块与杆的位置采样规则、执行阶段方块与杆的位置采样规则、杆在桌面内的转角范围变化 |
| `sampling_config.native.way_selection/obj_selection`<br>→ `episode_spec.initializations[].way`、`episode_spec.objects.obj_flag` | 每次初始化使用哪种操作方法、杆头尾相关选择 | 每次初始化way从peg_push/gripper_push/grasp_putdown选；场景obj_sample映射±1；尺寸先rand再乘0，dir_sample抽而未用，留trace | **规则不改，只外部生成本局值**：不能因“更难抓”只留peg_push；无效消费不删；本环境仅接收入口恢复模式，没有inject_fail_grasp，实际恢复动作为null，不新增抽样 |
| `sampling_config.native.direction_rule/reset_rule`<br>→ `episode_spec.actions.direction1/direction2/layout_switch` | 推动方向、两套布局切换，以及实际运行观测 | `evaluate`按两套实际y差给±1；`step`切换已生成执行位姿 | **不单独修改，按规则计算**：方向不再随机抽；难抓程度、可达性和实际切换帧属于运行观测 |

### 2.14 InsertPeg

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.peg_count`<br>→ `episode_spec.objects.n_pegs` | 场上杆的总数 | 现 `offsets=[0.1,0,-0.1]` 生成3根 | **是，拟修改**：多一根，总共4根 |
| `sampling_config.decision.near_target_distractor.{reference_id,radial_range,azimuth_policy}`<br>→ `episode_spec.initializations[].pegs[].pose` | 新增干扰杆相对目标杆的距离与方位约束 | 无近目标专用生成策略；原杆间距离>0.075 | **是，拟修改**：新增stick更近target stick；具体距离／方位未定，不擅自放松碰撞间距 |
| `sampling_config.decision.peg_yaw_range`<br>→ `episode_spec.initializations[].pegs[].pose` | 杆在桌面内的转角范围 | yaw±45°，原长轴已平行桌面 | **是，拟修改**：更大转角，具体范围未定；俯仰需求若有则另定 |
| `sampling_config.native.box_pose/peg_pose/rejection`<br>→ `episode_spec.initializations[].box_pose/pegs[]` | 每次初始化时孔板与全部杆的具体位姿 | 孔xy±0.1、yaw90°±20°；杆x±0.2、y±0.3；距孔>0.06，杆间>0.075，最多512次 | **规则不改，只外部生成本局值**：孔／原抽样和拒绝规则不改；新增杆按拟定距离与方位约束生成，姿态按拟定的杆转角范围 |
| `sampling_config.native.color/obj_selection/direction_selection`<br>→ `episode_spec.objects.head_rgb`、`episode_spec.initializations[].obj_flag/direction` | 杆头颜色、每次初始化的头尾和方向选择 | head=rand(3)；每次初始化obj_sample/dir_sample由randint(0,2)映射±1；尺寸length0.05、radius0.01先随机再乘0；random_peg_idx抽后覆盖为0 | **规则不改，只外部生成本局值**：保留原流及被覆盖值；目标仍peg_0；只记录入口恢复模式，本环境无inject_fail_grasp，实际恢复动作为null，不新增抽样 |
| `sampling_config.native.tail_color_rule/target_rule/box_geometry`<br>→ `episode_spec.objects.tail_rgb/target_peg_id`、`episode_spec.layout.box_geometry` | 杆尾颜色、固定目标杆、孔尺寸和实际运行观测 | tail=`1-head`；目标恒peg_0；孔尺寸由length/radius计算 | **不单独修改，按规则计算**：这些规则不变，不再给尾色、目标ID各抽一次；实际抓取／插入结果单列观测 |

### 2.15 PatternLock

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.demo_duration_seconds_range`、`sampling_config.decision.demonstration_duration_policy`<br>→ `episode_spec.actions.demo_duration_target` | 演示视频目标时长及调节时长的方式 | 目前没有秒数目标，由原路径与求解运动形成 | **是，拟修改**：最难情形video演示20～30s；如何调节节奏未定 |
| `sampling_config.native.path_selection`<br>→ `episode_spec.actions.path_nodes`、`episode_spec.sampling_trace.path_attempts` | 路径起点、终点、搜索顺序和最终节点序列 | easy/medium/hard：grid=`3/4/5`，节点数 `[2,4]/[3,5]/[4,8]`；起终点randperm，允许对角线的随机DFS；最多1000次，耗尽用最后路径 | **规则不改，只外部生成本局值**：用户只指定最难视频时长，未指定改grid/length/拓扑；不换成所有路径均匀抽样 |
| `sampling_config.native.grid_geometry/path_binding`<br>→ `episode_spec.layout.nodes[]`、`episode_spec.actions.demo_nodes/execution_nodes` | 网格节点位姿，以及演示和执行共用的路径 | center `[-0.1,0]`，间距0.1；节点由行列公式定位，演示和执行复用路径，首目标保留NO RECORD | **不单独修改，按规则计算**：网格位置不是随机值；演示视频目标时长及调节时长的方式不自动授权改路径长度或加重复帧 |
| `sampling_config.native.motion_template`<br>→ `episode_spec.actions.demo_actions`；`运行记录.demo_frames/fps/duration_s` | 路径对应的动作，以及实际演示帧数、帧率和时长 | 每目标solve_swingonto两次screw运动并close_gripper；实际fps按交付录像器30 | **不单独修改，按规则计算**：未来验证20～30秒要实际600～900演示帧；不能改fps或伪造帧数；时长实测写入运行记录 |

### 2.16 RouteStick

| 修改后的字段 | 什么含义 | 现在的值 | 是否修改／拟定修改后的值 |
| --- | --- | --- | --- |
| `sampling_config.decision.demo_duration_seconds_range`、`sampling_config.decision.demonstration_duration_policy`<br>→ `episode_spec.actions.demo_duration_target` | 演示视频目标时长及调节时长的方式 | 无秒数目标；官方hard段数 `[4,7]`、backtrack=True；现xhard `[8,10]`不属原train | **是，拟修改**：最难情形video演示20～30s；速度／等待等实现方式未定，不能直接把长度改为xhard代替 |
| `sampling_config.native.length/walk`<br>→ `episode_spec.objects.L`、`episode_spec.actions.nodes/directions` | 运动段数、路线起点、经过节点和每段绕行方向 | easy/medium/hard：length=`[2,3]/[4,5]/[4,7]`，backtrack=`False/False/True`；节点0/2/4/6/8，邻居±1，端点强制反向；方向每段独立rand<0.5 | **规则不改，只外部生成本局值**：用户本次没有决定新段数／拓扑／方向分布；保留原抽法，禁用旧候选的跨局方向均衡 |
| `sampling_config.native.yaw/obstacle_color`<br>→ `episode_spec.layout.rotation_deg/obstacle_rgb` | 路线整体旋转角与障碍柱颜色 | yaw=`u×60−30`度，4柱RGB各rand(3) | **规则不改，只外部生成本局值**：不改旋转域、颜色池或抽法 |
| `sampling_config.native.grid_geometry/node_mapping`<br>→ `episode_spec.layout.node_poses/obstacle_poses`、`episode_spec.actions.node_slots`、`episode_spec.objects.allow_backtracking` | 网格和障碍柱位姿、节点索引及回退开关 | 1×9网格，center `[-0.1,0]`、间距0.07，柱位1/3/5/7、半径0.015高0.1；L段→L+1节点；allow_backtracking直接取difficulty的backtrack | **不单独修改，按规则计算**：按原几何和旋转计算，不再独立随机摆节点或柱；回退开关保持原值 |
| `sampling_config.native.motion_template/trail_steps`<br>→ `episode_spec.actions`；`运行记录.demo_frames/fps/duration_s` | 曲线路径、高亮、尾迹，以及实际演示帧数和时长 | 每段45曲线点+5末端保持，IK失败可跳点；官方尾迹40步，当前10步须恢复 | **原值阶段先恢复官方尾迹；时长之后修改**：演示视频目标时长及调节时长的方式只规定最终演示20～30s；不拿理论50点当实际50帧，不倍速改编码凑时长 |

## 三、两个接口怎样组织

**结论**：每个环境只多接两样东西。`sampling_config` 是配置快照，按 `tasks[env].decision`（以后允许改的参数）和 `tasks[env].native`（原随机规则与常量）分块，传给 `gym.make(..., sampling_config=...)`；`episode_spec` 是这一局的冻结输入，带版本记录 `identity / layout / objects / actions / initializations / sampling_trace / provenance` 七块。配置只决定「从什么范围里抽」，规格只记录「这局抽到了什么」，环境按规格里的固定对象和动作运行，不在消费时再临时决定目标、布局或交换搭档。

**两种模式**：第一轮是原值对拍，`decision` 也锁原值，规格来源固定为 C 路原生运行的只读导出，原 RNG 仍按原次序跑作兼容核验但不替代规格。以后是新值模式，外部供值器读 `decision` 新值加 `native` 原规则生成新样本，只能宣称可重放，不能宣称与原 train 逐条相同。

```text
sampling_config.tasks[env]  decision / native
        ↓ 外部供值器（第一轮＝C 路只读导出）
episode_spec  layout / objects / actions / initializations
        ↓ 冻结记录作为真实输入
环境按固定对象和动作运行 → 只读运行证据（位置、时间、成败、RNG 核验）
```

**⚠ 三条边界**：`native` 里任一取值域、单位、dtype、随机源或拒绝条件变了都算新用户决策，不能混在「仅随机外移」里；导出与回注都在原调用点做，拒绝采样的失败尝试、单候选抽样、被覆盖的抽样全部保留，不减少抽样次数；延迟到事件时点才知道的值（如交换搭档）在同一时点导出与核验，不在 reset 时按初始坐标猜。未来改数量、布局、速度倍率、演示时长时各自要补的派生关系见第二部分 8.3。字段落到现有源码键的逐环境映射见第二部分「二」，完整展开见第二部分「八」。

## 四、原始对拍这么比

**对拍的基线是谁**：官方 `dataset-gen` 分支固定提交 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`，用它自己的 `generate_dataset.py::_worker`、原求解链和原 fail recover，按官方十六份metadata冻结全部1600条身份，再仅对选定144条 `(task, episode, seed, difficulty)` 独立重跑两次，得到 A1、A2。这就是全部比较的锚点，不是本地 fork 的默认路径，也不是官方 main 的无恢复路径。历史报告标称的 `9430e20…` 源码不完整，只冻结其结果用于对照；历史 HDF5 成品当前缺失，不作为基线。

**拿什么跟基线比**：B 是新分支恢复后的默认路径，C 是 B 加显式原值 `sampling_config`，D 是 C 导出的 `episode_spec` 原值回注。`A1↔A2` 先证明基线自身可重复；`A1↔B` 证明恢复到了官方行为（会抓出继承的旧改动，如 `RouteStick.py::step` 尾迹 10 步对官方 40 步）；`B↔C↔D` 与 `A1↔D` 证明接口拆分和回注没有改数。

**在哪跑、怎么并行**：全部在 greatlakes `spgpu` 分区（A40）上跑，本机不跑。用户拍板 4 个占位 job、每 job 4 worker、共 16 worker。理由：greatlakes 规约实测 A40（sm_86）与本机 RTX 6000 Ada（sm_89）不逐位一致，所以五路必须同在 A40 上；官方 `dataset-gen` 的 `_parse_gpus` 只接受 `"0"`，Slurm job 内 `CUDA_VISIBLE_DEVICES=0` 正好满足；worker 默认单线程（`limit_threads=true`），集群实测每 worker 每局 RSS 峰值 3.0～5.6 GB、显存 0.6 GB，所以 job 形状定为 **1 GPU / 4 CPU / 32G / 48h**。分片按 task 切：16 个环境分 4 组、每 job 4 个环境 × 每环境 9 条 = 36 条身份，五路 180 次生成都在本 job 内完成，A1／A2 用官方脚本 `--workers 4`，B／C／D 用新入口 `--workers 4`；同一身份内 C→D 串行，身份之间并行。放开条件 P0：同一身份的 A1 在 4 个 job（可能落在不同节点）各跑一次，逐位相同；不同则四个 job 只能串成一路。占位 job 到期或被回收时重新申请，任何时刻不超过 4 个。集群实测数字、job 脚本与分片表见第二部分「十」。

**抽样规模**：用户拍板「不用全部验证 每个task每个难度验证3条左右即可」。每个task每个难度按固定官方metadata顺序取该难度前3条，共16×3×3＝144条。已实读十六环境：easy均为episode `[0,1,4]`，medium为 `[2,6,10]`，hard为 `[3,7,11]`；每环境z3条、xy2条、关闭4条，合计z48、xy32、关闭64。三模式已经齐全，不再设隐式换样分支；冻结manifest与此规则不符直接报错。每环境episode 5未纳入，不能宣称全部96条恢复覆盖；全集1600条仍为可选后续步7。

**历史缺证怎样处理**：用户已选择允许完成。R1拆成历史可比字段R1a、本次发布集审计R1b、历史动作数值核对R1c；最后一项当前明确“未验证”，不阻塞完成，不能用前两项的通过替它填零差异。新生成五路之间的144条严格对拍保持硬条件。

**判据表**：判据行全部摘进运行目录的 `compare` 输出；必需判据FAIL即停，不放宽判据。R1c及R2明确允许缺证时为 `NOT_RUN`；R1b的“审计完整”与其记录的原 `1e-8` 数值结果分开，原失败不能改写成PASS。`N`替换为实测条数；单条冒烟与分批进度只报告当次范围，不冒填144／80。步骤对应第五节，完整展开见9.4。

| # | 验证 | 步骤 | 证明什么 | 判据行 | 耗时／资源 |
|---|---|---|---|---|---|
| G1 | 原身份完整 | 0 | 全量 manifest 与官方固定 metadata 逐条双向相等；无重复、漏项、额外项，170 条非公式 seed 未被公式替代；再从中按每 task 每难度 3 条抽出 144 条子集，子集每条都能回指全量行 | `TRAIN_IDENTITY=PASS tasks=16 rows=1600 mismatch=0` ＋ `TRAIN_SUBSET=PASS tasks=16 per_cell=3 rows=144` | 秒级／CPU，不启动仿真 |
| P0 | 跨 job／跨节点等价 | 1b | 同一身份 A1 在 4 个占位 job 各跑一次，HDF5、图像、状态与事件逐位相同；不同则不能分片，只能单 job 串行 | `NODE_PARITY=PASS identities=N jobs=4 mismatch=0` | 4 条生成／4 job |
| G2 | 配置外提完整 | 3 | 十六环境 `decision`／`native` 每个键映射到源码消费点；原运算元、dtype、区间边界及有效／死字段逐一核对 | `SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0` | 分钟级／CPU |
| G3 | 字段归属完整 | 3 | 第二节 101 行每项落到 `decision` 或 `native` 及其本局输入／运行观测；原值阶段两块均原值；最近邻／补集／时间表不独立抽签 | `FIELD_OWNERSHIP=PASS tasks=16 unmapped=0 native_rule_overrides=0` | 分钟级／CPU |
| G4 | 规格真正被消费 | 4 | 逐局比对象ID、布局、目标、动作、恢复与初始化编号；恢复含xy符号、派生偏移及实际抓取位置绑定；保留原重抽却绕过规格赋值的反例必须被抓到 | `SPEC_BINDING=PASS missing=0 unused=0 mismatch=0` | 单条秒级／集群 A40 |
| G5 | 比较器支持原稀疏身份 | 1b、5e | 新适配器保留原字段及数值比较核心，仅替换范围与预期集合；连续范围对原函数结果相同，稀疏／重复／缺失／额外身份反例全覆盖，详见9.6 | `COMPARATOR_SCOPE=PASS contiguous_mismatch=0 sparse_mismatch=0 invalid_accepts=0` | 秒级／CPU夹具，不启动仿真 |
| P1 | 原版自身重复 | 1b | A1↔A2 的 HDF5、图像、状态与事件逐位相同；不可重复的身份单列 `BASELINE_NONDETERMINISTIC`，不设新种子 | `BASELINE_REPEAT=PASS compared=N different=0` | 集群实测 1 worker 约 42 s/条、8 worker 3.5 条/分（第二部分「十」）／A40 |
| P2 | 原始行为已恢复 | 2 | A1↔B 全字段相同；不能排除 RouteStick 尾迹、演示标志或恢复事件来求通过 | `TRAIN_RESTORE=PASS compared=N mismatch=0` | 同 P1／A40 |
| P3 | 随机流不漂移 | 4 | B／C／D 比调用序号、源身份、签名、结果、拒绝记录与前后状态 | `RNG_PARITY=PASS compared=N calls_mismatch=0 state_mismatch=0` | 同 P1／A40 |
| P4 | 原值注入等价 | 4 | B↔C、C↔D、A1↔D 逐元素比 dtype、shape、位模式与全部 group／dataset／attribute；SHA 相同即字节相同，不同则继续逐字段比 | `INJECTION_PARITY=PASS compared=N mismatch=0` | 同 P1／A40 |
| P5 | 图像与录像事件 | 5a | 落盘 RGB、演示／执行标志、真实帧索引相同；MP4 比完整解码帧数与像素，编码容器散列单列 | `VIDEO_PARITY=PASS compared=N frames_mismatch=0 pixels_mismatch=0` | 同 P1／A40 |
| P6 | 连续 worker 不污染 | 5b | 每环境选不同原身份，甲→乙→甲在同一 PID 运行，各自与独立进程相同；配置、规格输入散列不变 | `WORKER_ISOLATION=PASS tasks=16 mismatch=0 input_mutation=0` | 48 条生成／A40 |
| P7 | fail recover 原样 | 5a、5d | 对选定144条逐条比恢复开关、模式、实际失败动作索引、xy方向／偏移、触发与结果；实际无恢复事件记null，不新增事件 | `RECOVERY_PARITY=PASS compared=144 configured=80 z=48 xy=32 off=64 mode_mismatch=0 event_mismatch=0` | 冒烟仅报实际条数；完整计数随5d产出 |
| R1a | 历史可比字段对照 | 1b、5e | 按144条原身份投影旧报告，只比身份、恢复模式、成功与逐条帧数；不包含历史动作数值 | `DATASET_GEN_REPORT_PARITY=PASS compared=144 fields=identity,recovery_mode,success,timestep_count outcome_mismatch=0 detail_mismatch=0` | 单条先报N；完整范围随5e汇总 |
| R1b | 本次发布集审计完整 | 5e | 恢复发布集后经9.6适配器审计144条；合同无错、身份无漏，动作原 `1e-8` 结果与逐条差异完整留存；此项不代表发布集动作数值相等 | `REFERENCE_AUDIT_COMPLETE=PASS compared=144 contract_errors=0 missing=0`；另列动作比较原始 `passed/max_abs_diff/errors` | 需恢复 `data/robomme_data_h5/` |
| R1c | 历史动作数值核对 | 1a、5e | 原报告无逐局数值摘要，旧HDF5缺失；明确未验证，用户已选择不阻塞完成 | `HISTORICAL_ACTION_PARITY=NOT_RUN reason=historical_per_episode_evidence_missing blocking=0` | 不得伪造 `detail_mismatch=0` |
| R2 | 历史成品额外比较 | 1a | 历史原 HDF5 当前缺失；找回且散列核验通过后才实跑 | `HISTORICAL_ARTIFACT_PARITY=NOT_RUN reason=historical_files_missing` | 无 |
| C1 | 失败与子集覆盖 | 5d | 144 条全部有终态；missing、timeout、error、不可重复、不可比、成功分别计数并留退出码与阶段 | `TRAIN_COVERAGE=PASS expected=144 terminal=144 missing=0` | 720 次生成／4 job 各 180 次，估 1.5 h |

**完成条件**：G1～G5、P1～P7、R1a、R1b、C1全部通过；并行资源安排另须满足P0或其明确的单路回退条件。C1只表示144条执行完整，各条仍须通过适用的严格对拍，不能因双方同样失败或缺失就算一致。R1c历史动作数值和R2历史成品当前缺证可保留 `NOT_RUN`，不阻塞完成，最终结论必须同时写“144条子集通过”和“历史动作数值未验证”，不能外推1600条。旧报告对发布HDF5的 `1e-8` 失败原文保留；R1b记录本次发布比较的原始数值失败不等于新接口的注入差异，也不冒称已与旧数值摘要对齐。

## 五、实施顺序（十三步，全文以本表为准）

主副本上顺序执行；每步 commit 后按仓库规则 push。算力：greatlakes 4 个占位 job（1 GPU / 4 CPU / 32G / 48h），代码副本在 NFS `robomme_benchmark-newtask-gl`，所有生成用 `srun --jobid=<占位> --overlap` 塞进 job，本机不跑仿真；步 1b 先在一个 job 单 worker 定基线并在 4 个 job 跑 P0，P0 通过后按第二部分「十」分片。「闸门」列引用第四节判据表编号；任一 FAIL 停下交用户，不放大范围。涉及 `src/robomme/` 的步骤须先按第二部分「一」逐项获批。会话名、命令与失败分流见第二部分「四」。

| # | 步骤 | 做什么 | 闸门 | 失败处置 |
|---|---|---|---|---|
| 0 | 切分支与冻结 | 从含本方案的提交切 `newtaskRelease-v3`；冻结父提交、官方源码、1600 条 metadata、锁文件、设备与用例清单；核验输出路径与存储 | G1、来源散列齐全 | 分支或散列不对即停，不改代码 |
| 1a | 冻结历史证据 | 冻结 `dataset-gen` 原报告与逐文件散列；明确历史可投影字段和数值缺证；定位历史成品与官方参考数据 | 缺证时R1c、R2记 `NOT_RUN` | 缺证不冒称通过；按用户决定不阻塞当前严格对拍 |
| 1b | A 路单条试跑与跨 job 核验 | 在 `scripts/` 新增严格manifest、144条抽样与五路编排；比较器范围适配先过离线反例G5；`BinFill/easy/episode_0` 单任务、单episode、单worker在 job 1 跑A1、A2，保留z恢复；同一条在其余 3 个 job 各跑一次A1 | G5、P0、P1、R1a（单条帧数／成功／恢复） | 不以公式替换seed，不重编号episode；不一致先定位 |
| 2 | 恢复原值默认路径 | 按逐项批准恢复历史原值（含 RouteStick 尾迹 40 步），只做 A↔B | P2 在指定样本通过 | 未解决项不隐藏；数值 FAIL 只 revert 该项 |
| 3 | 逐环境切出 `sampling_config` | 十六环境逐个拆 `decision`／`native`，按第二节字段表与第二部分「二」映射；每环境先 B↔C 再进下一环境 | G2、G3；该环境 B↔C 过 P4 | 一环境未过不进下一环境 |
| 4 | 逐环境切出 `episode_spec` | 同顺序实现原位抽样记录与原值回注，含两次初始化、动态事件、执行时xy恢复独立流及符号实际消费；公共工具按清单单列审批；每环境B↔C↔D | G4、P3、P4 | 现有「注入后跳过抽样」分支不得沿用为D；重抽相同但不消费规格必须被G4拒绝 |
| 5a | 16 环境冒烟 | 每环境各一条原 episode 走五路，比全部字段、图像与恢复 | P5、P7 | 单条失败先定位 |
| 5b | 48 格与恢复分支 | 用 144 条子集覆盖 48 个 task／difficulty 格、`BinFill` 两种 dynamic、`VideoRepick/hard`、单双拾取、零／非零交换、延迟搭档与 z／xy／关闭三种恢复；连续 worker 甲→乙→甲 | P6 及 P1～P5、P7 在子集通过 | 未出现的分支列覆盖缺口，不另造用例 |
| 5c | 多 worker 核验 | 在一个 job 内用 `--workers 4` 重跑 5b 子集，与单 worker 结果比；同时记录 4 worker 实际吞吐 | P4、P6 在子集通过 | 不一致回单 worker，不改 seed 与恢复 |
| 5d | 144 条五路 | 按第二部分「十」分片，4 个 job 各 36 条 × 5 路 = 180 次，每 job 4 worker，独立输出目录；`compare` 在登录节点只读汇总 | C1 及 P1～P7 在 144 条 | 任一未完成留在分母，不宣布 144 条一致 |
| 5e | 原比较核心的子集审计 | 恢复发布集至 `data/robomme_data_h5/`，用9.6适配器按144条原身份跑合同与动作比较；历史可比字段单独核对，原数值结果完整留档 | G5、R1a、R1b；R1c允许缺证 `NOT_RUN` | 缺文件或合同错误仍阻塞；动作原 `1e-8` 失败照记，不把缺失历史数值写成相同 |
| 6 | 留档提交 | 保存逐条身份、配置／规格、差异、命令、退出码、原始结果与图像索引；更新使用说明；提交并 push | 源文件与原产物未覆盖；状态与证据一一对应 | 存储不足先汇报占用，不清理旧产物 |
| 7（可选） | 全集1600条 | 用户另行要求时才把5d放大到1600×5＝8000次；各判据按全集身份计算，不改比较规则 | C1换 `expected=1600`；P7换 `compared=1600 configured=96 z=48 xy=48 off=1504`；其他条数随范围更新 | 未做之前一切结论只限144条 |
| 后续 | 新值模式 | 用户另行启动布局／难度改动后，才在 `decision` 启用第二节拟修改值与新算法 | 单独定义新值验收 | 不复用原 train 相等结论 |

每次代码提交前的测试预算不超过 5 分钟：先跑相关定向测试和核心路径；完整五路矩阵属于独立的长时实验，按批次用 detached tmux 管理，日志采用 `PYTHONUNBUFFERED=1`、`set -o pipefail`、`tee` 与 `EXIT_CODE=`。第一次实测后再估算耗时和磁盘，不能用历史四任务的耗时线性外推作保证。

## 六、本轮方案的状态

本次对抗审查修订按用户原话「有哪些需要我决策的 让我一个个决策 其他的可以修改md」执行；用户要求先解释再选择，最终选择「允许完成：本次144条严格对拍通过，缺失的历史核对明确写“未验证”（推荐）」。修订恢复子集计数、比较器范围适配、xy恢复符号消费和R1a／R1b／R1c拆分；16环境101行原表及历史审查报告保留。本次只改文档，未实现新接口或运行仿真；没有把技术修订写成已经通过运行验收。

本轮只做源码、metadata、分支与依赖指纹的只读核验，新增方案并更新账本。没有创建 `newtaskRelease-v3`，没有生成新的配置或候选，没有运行十六环境仿真，也没有宣称原 train 对拍通过。未来取值全部停留在第二节的接口需求中。

文档验收检查十六环境是否逐个列出、未来需求是否全部有落点、原值与新值是否混淆、引用文件和函数是否存在、是否误用硬编码代码行号、是否误把待实现命令说成已有能力，并运行 `git diff --check`。纯文档改动不启动数据生成；后续实施结果追加在本节之后，保留原计划和本轮核验边界。

首次方案落地（11.20）的静态验证退出 0：`PLAN_STRUCTURE=PASS environments=16 fixed_rows=64 local_links=23 code_line_refs=0`；当时从固定 `dataset-gen` Git 对象重读十六份 metadata，`PLAN_BASELINE=PASS train=1600 recovery_z=48 recovery_xy=48 recovery_off=1504`。`git diff --check` 通过；相对初始提交的 `src/`、`scripts/`、`pyproject.toml`、`uv.lock` 零改动。这里是首次版本的核验记录，不把其64组概括项当作本次字段清单。

上一版字段拆分（11.23）共16环境、32张表、101个字段组：U用户决策46组，R原规则外部抽样35组，D规则派生／观测20组。每组在当前值表中有同编号对应；已复核四环境的旧键与新格式映射，其余十二环境标为拟新增接口。只读源码核对纠正了ButtonUnmaskSwap左按钮位置和PickHighlight高亮时序，并明确MoveCube／InsertPeg仅接收恢复模式、没有随机失败抓取注入；不会因新增字段补出原来不存在的事件。

文档核验退出0：`FIELD_SPLIT=PASS environments=16 tables=32 field_groups=101 user_groups=46 random_groups=35 derived_groups=20`、`DOC_CHECK=PASS matching_rows=101 local_links=20 baseline_section_unchanged=1 code_line_refs=0`。只改方案与账本；本次没有生成配置、候选或数据，没有运行代码测试或真实仿真，文档核验不代表未来对拍已经通过。

本次四列单表调整（11.24）保留全部101行，将十六环境改为16张表；当前值逐行与上一版核对一致（仅展开字段简写），旧键映射移至4.3，共用约束移至4.4。静态核验退出0：`SINGLE_TABLE=PASS environments=16 tables=16 columns=4 rows=101`、`CONTENT_CHECK=PASS current_values_unchanged=101 baseline_unchanged=1 local_links=20`；只读复核确认未来数值和待定事项保留，未修改任何生效配置或代码。

本次算力改为集群（11.29）按用户原话「改为使用这4个spgpu来跑不要在本机 如果没了再申请 不要超过4个」「本地被占用了 先申请一个多cpu但是单个gpu job测试一下」「还是用sleep先占用48小时 这个1gpu8cpu」「我的目标同时启动20个worker 给出job分片方案 写入md」「改为4*4 16worker」：仓库克隆到 NFS 并 uv sync 成功；在占位 job 61665377 内实测 1 worker 与 8 worker 的 CPU／RSS／显存／吞吐（第二部分「十」）；据此定 job 形状 1 GPU / 4 CPU / 32G / 48h × 4、按 task 分 4 片各 36 条；P0 由两卡等价改为跨 job 等价 `NODE_PARITY`；本机不再跑仿真。

本次规模与并行调整（11.28）按用户原话「你预计都只能用gpu0吗 是否可以并行？ 不用全部验证 每个task每个难度验证3条左右即可」：验收分母由 1600 条改为每 task 每难度 3 条共 144 条（全集改可选步 7）；查实本机两张同型号 RTX 6000 Ada、官方 `_parse_gpus` 仅限定字符串 `"0"`、现行入口已支持多卡，新增 P0 `GPU_PARITY` 两卡逐位核验，通过后 A 路钉 GPU 0、B／C／D 用 GPU 1，同卡 worker 按官方 20 起步。

本次格式对齐（11.27）参照 `robomme_policy_learning_MotionJEPA@v2-motionmem` 的 `0920-32frame-8x8-modul-2048-plan.md`：第四节改为带编号（G1～G4、P1～P7、R1～R2、C1）的六列判据表并保留基线／比什么／能否并行三段结论，第五节改为十二步编号步骤表（0、1a、1b、2、3、4、5a～5e、6、后续），第二部分「三」改为闸门前置条件表，所有阶段引用改为步号。内容仍取自原文，未新增事实。

本次两部分重排（11.25）不改第二节的 16 张表与 101 行；原「三、原始 train 的身份与代码基线」与「五、怎样对拍」合并为第四节「原始对拍这么比」，原「四、两个接口」去掉字段映射后成为第三节，三、四两节按用户要求只留高层结论，完整展开下沉为第二部分「八」「九」，原 4.3 字段映射、6.2 改动清单、6.3 命令与留档移入第二部分，并新增前置红线、对拍闸门总表、风险登记与盲区清单，内容均取自原文，未新增事实。静态核验退出0：`TWO_PART=PASS environments=16 tables=16 rows=101 local_links_missing=0 code_line_refs=0`，`git diff --check` 通过；本次同样没有生成配置、候选或数据，没有运行仿真。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

以下编号可被正文引用；与 [AGENTS.md](AGENTS.md) 强制规则冲突时以后者为准。

- **R1 只规划不实施**：本文件任何改动清单都不等于批准；`src/robomme/` 每处源文件改动与运行时覆盖须按 AGENTS.md 第 11 条逐项提交「文件／锚点／改什么／为什么」并获准后才动。
- **R2 录像器冻结**：`src/robomme/env_record_wrapper/RecordWrapper.py` 不改、不覆盖；不补 reset 帧，不录制 `NO RECORD` 帧，不改命名与落盘位置。验证命令 `git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`。旧 `tests/_shared/parity_observer.py` 覆盖录像器方法，不得作为生产对拍观察器。
- **R3 身份不重算**：严格读取官方 `(task, episode, seed, difficulty)`，不用 `SeedLayout.base_seed` 公式替换 170 条不一致 seed；失败不调用 `EpisodeJob.bump`、不换 seed、不补样本。
- **R4 A 路必须是原链路**：A1／A2 用独立进程加载固定 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa` 源码，执行原 `_worker`、原求解与原 fail recover；不能给 A 和 D 同时打补丁制造一致。
- **R5 不改验收口径**：发布参考集比较保留 `1e-8`；不关恢复、不换样本、不放宽容差；A1／A2 不逐位一致的条目记 `BASELINE_NONDETERMINISTIC`，不设新种子。
- **R6 第一轮禁用项**：关闭 `_binfill_demo_deliverable` 轨迹复制；不消费 `injection_contract_v3.json` 新值分布；不做跨 episode 方向平衡；不按 400 条配额筛样本；不把 `VideoRepick/hard` 换成 xhard；现行碰撞检查新增拒绝条件只作只读诊断；不继承 `scripts/injection/candidates/sampling.py` 的 PCG64／配额／分层／方向平衡。
- **R7 原值模式两块都锁原值**：`decision` 与 `native` 均从固定来源提取并校验；`native` 任一取值域、选择规则、单位、dtype、随机源、端点语义或拒绝条件改变都须显式列为用户决策。
- **R8 随机流不漂移**：导出与回注均在原调用点进行；拒绝采样失败尝试、单候选抽样、被覆盖的抽样全部保留；不删兼容抽样做优化，不用末尾 `set_state` 掩盖漏抽；一个 `(阶段, 初始化序号, 对象ID, 事件序号)` 只消费一次记录。
- **R9 旧产物不覆盖**：旧快照、旧候选（含运行十）、当前工作树、旧运行产物与官方数据保持原版本原字节；`validate_candidates` 按版本分流校验。
- **R10 测试预算**：每次代码提交前测试不超过 5 分钟；完整五路矩阵按批次用 detached tmux 起，日志用 `PYTHONUNBUFFERED=1`、`set -o pipefail`、`tee`、`EXIT_CODE=`；单条冒烟失败不得放大全集。
- **R11 文档禁硬编码行号**：引用代码只用函数／类／配置键等稳定锚点。
- **R12 状态如实**：本次五路未完成、不可比或异常身份留在144条分母（可选步7时为1600），子集通过不外推全集。历史缺证分别记 `HISTORICAL_ARTIFACT_PARITY=NOT_RUN` 与 `HISTORICAL_ACTION_PARITY=NOT_RUN`；按用户决定不阻塞本次验收，但不得宣称历史核对已经完成。

## 一、按文件的逐项改动清单

下面是**待实施清单**，不是本轮修改记录，也不是整表已经获批。每个环境的具体固定项见第二节；实施前须将该环境实际涉及的函数与改法单独提交审批。

| 文件／锚点 | 拟改什么、为什么 | 原值阶段的行为 |
| --- | --- | --- |
| `scripts/train_split_parity.py`（拟新增） | 严格构建1600条来源manifest与144条运行子集；按A1／A2／B／C／D编排；按身份投影原报告可比字段，调用范围适配后的比较器 | 使用原实际seed和episode，只尝试一次；A执行原worker，含原fail recover |
| `scripts/train_split_comparison.py::validate_manifest_scope/validate_generated_subset/compare_joint_actions_subset`（拟新增） | 从固定官方版本保留合同和动作比较核心，只适配manifest范围、预期group集合与元数据投影；保留原源码及最小差异证据 | 允许稀疏原episode，不改编号、不补样本；保留dtype／shape、终态、非零计数和 `1e-8`，须过G5 |
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
| `src/robomme/robomme_env/utils/subgoal_planner_func.py::_get_fail_recover_rng/_sample_fail_recover_xy_signs/solve_pickup_fail` | 逐函数单独审批：标识执行时恢复独立流，原位导出／消费xy符号，派生偏移并绑定实际抓取位置；见8.2 | 原seed、抽样次数和 `[0,0]` 拒绝规则不变；D用规格符号驱动偏移，原抽样只核验；不改z恢复原值 |
| `tests/lightweight/`、`tests/dataset/`、`tests/_shared/native_sampling_parity.py` | 新增稀疏范围、身份与配置／规格绑定反例，含恢复方向重抽相同却绕过规格；复用和补齐全字段离线比较；新增真实原train矩阵 | 测试观察器不得改变作为结论依据的生产行为；纯夹具不能冒充train覆盖 |

如 `object_generation.py`、`route.py`、`task4recovery.py` 或求解器确实还需要改动，必须再列出具体函数与理由，不能由环境文件获批推导出工具文件也获批。预留未来功能不等于现在重写这些公共函数。`src/robomme/env_record_wrapper/RecordWrapper.py` 不在改动清单内。

## 二、现有字段映射与实现约束

以下为第二节字段的代码来源，不另增加用户要填写的参数。

**BinFill**：现有配置映射：`sampling_config.decision.color/spawn_cubes/put_in_numbers` 对应 `parameters.BinFill.configs[d].color/spawn_cubes/put_in_numbers`；`sampling_config.native.put_in_color` 对应同档 `put_in_color`；`sampling_config.native.button/board/cube_pose` 对应 `positions.BinFill.button/board/cubes`。现规格已有 `layout.dynamic/button_xy/board/cubes`、`objects.spawn_total/put_in_total/spawn_count/target_count/target_pool/colors_present` 及顶层 `actions[*]` 数组；新格式将此数组适配到 `episode_spec.actions.pick_place[]`，使 `episode_spec.actions` 能同时容纳恢复记录，不修改旧记录。`episode_spec.layout.mode`、按次保存的 `initializations`、完整恢复记录为拟新增；旧 `objects.initialize_color_order` 不能承载两次独立初始化。锚点：[BinFill.py](src/robomme/robomme_env/BinFill.py) 的 `__init__/_load_scene/_initialize_episode`、[specs.py](scripts/injection/candidates/specs.py) 的 `_binfill_group`。

**PickXtimes**：以上字段是拟接接口；源码现有 `config_*` 的 `color/number_min/number_max`，以及 `target_cube/target`、`shuffle_indices/target_cube_idx`。锚点：[PickXtimes.py](src/robomme/robomme_env/PickXtimes.py) 的 `__init__/_load_scene/_initialize_episode`。

**SwingXtimes**：以上接口拟新增；现有规则锚点：[SwingXtimes.py](src/robomme/robomme_env/SwingXtimes.py) 的 `config_*`、`__init__/_load_scene/_initialize_episode`。`number` 表示一轮左右动作，不是方块数或单次摆动数。

**StopCube**：以上字段拟新增；源码锚点：[StopCube.py](src/robomme/robomme_env/StopCube.py) 的 `_load_scene/_initialize_episode/step/evaluate`。`step::range(5)` 是未来扩次数的真实限制；第一轮仍保持5段。

**VideoUnmask**：以上接口拟新增；源键为 `configs[difficulty]['bin'/'pick']`，锚点：[VideoUnmask.py](src/robomme/robomme_env/VideoUnmask.py) 的 `_load_scene/step`。

**ButtonUnmask**：以上接口拟新增；现有 `config_*::bin/pick` 与局部变量来自 [ButtonUnmask.py](src/robomme/robomme_env/ButtonUnmask.py) 的 `__init__/_load_scene/_initialize_episode/step`。

**VideoUnmaskSwap**：现有配置映射：容器交换次数的范围与交换后需要拾取的目标数量范围 对应 `parameters.VideoUnmaskSwap.configs[d].swap_min/swap_max/pick_min/pick_max`；native原规则映射 `parameters.VideoUnmaskSwap.object_selection/swap_selection` 与 `positions.VideoUnmaskSwap.containers`。`episode_spec.objects.selected/color_order/hidden/empty/pick_order/swap_initiators`、`episode_spec.layout.type/theta_rad/bins`、`episode_spec.actions.swap_pairs` 已存在；交换速度倍率、额外干扰物、`target_choice`、时间表等为拟新增。当前 object_selection/swap_selection 只校验原值，不是已开放的任意参数。锚点：[VideoUnmaskSwap.py](src/robomme/robomme_env/VideoUnmaskSwap.py) 的 `__init__/_load_scene/_initialize_episode/_refresh_swap_schedule/step`、`_unmask_group`。

**ButtonUnmaskSwap**：以上接口拟新增；原键为 `config_*::bin/swap_min/swap_max/pick_min/pick_max`，源锚点：[ButtonUnmaskSwap.py](src/robomme/robomme_env/ButtonUnmaskSwap.py) 的 `__init__/_load_scene/_initialize_episode/_refresh_swap_schedule/step`。原三角基位 `[[-0.05,-0.15],[-0.05,0.15],[0.05,0]]`，直线第三点改 `[-0.05,0]`；四点 `[[0,-0.1],[0,0.1],[0.1,0.1],[0.1,-0.1]]`；三点各自x、四点分组y加 `u×0.1`，保持原抽样顺序。

**PickHighlight**：以上接口拟新增；现有 `spawn/pickup`、`color_choice_idx/target_cube_indices` 来自 [PickHighlight.py](src/robomme/robomme_env/PickHighlight.py) 的 `config_*`、`_load_scene/step`。

**VideoRepick**：现有映射：`num_repeats_range` 对应 `parameters.VideoRepick.num_repeats.low/high_exclusive`；`swap_enabled/swap_count_range` 对应 `configs[d].swap_min/max`；原规则对应 `object_selection/swap_selection`、`positions.VideoRepick.button/easy_medium_cubes/hard_cubes`。`episode_spec.objects.target/num_repeats/color/n_cubes/n_swaps/swap_initiators`、`episode_spec.layout.type/theta_rad/button_xy/cubes`、`episode_spec.actions.swap_pairs` 已存在；逐块颜色、模式、完整hard规格为拟新增。`_repick_group` 现拒绝hard，hard分支仍内部随机生成，不能假定已经外置。锚点：[VideoRepick.py](src/robomme/robomme_env/VideoRepick.py) 的 `_load_scene/_initialize_episode/_refresh_swap_schedule/step`、`_repick_group`。

**VideoPlaceButton**：以上接口拟新增；现键 `color/targets/swap/additional_place`、`target_cube/task_flag/goal_site` 来自 [VideoPlaceButton.py](src/robomme/robomme_env/VideoPlaceButton.py) 的 `_load_scene/_initialize_episode/step`。每块独立保存起始位姿，不能两块共用一个随机goal_site；也不能把实际回位结果提前写成输入事实。

**VideoPlaceOrder**：以上接口拟新增；现有 `color/targets/swap`、`num_targets_to_pick/indices/which_in_subset/k/button_task_index` 来自 [VideoPlaceOrder.py](src/robomme/robomme_env/VideoPlaceOrder.py) 的 `_load_scene/_initialize_episode/step`。

**MoveCube**：以上接口拟新增；现变量 `peg_init_poses/peg_init_poses_2`、`cube_init_pose/cube_init_pose_2`、`goal_site_1_pose_p/q`、`goal_site_2_pose_p/q`、`way_idx/obj_sample` 来自 [MoveCube.py](src/robomme/robomme_env/MoveCube.py) 的 `_load_scene/_initialize_episode/evaluate/step`。`build_peg` 的长轴原在局部x轴，现只加yaw，不应把“平行桌面”写成新功能。

**InsertPeg**：以上接口拟新增；源变量及规则见 [InsertPeg.py](src/robomme/robomme_env/InsertPeg.py) 的 `_load_scene/_initialize_episode` 与 `utils/object_generation.py::build_peg`。不能只保存构造期临时杆位姿，必须保存每次初始化的真实输入。

**PatternLock**：以上接口拟新增；源锚点：[PatternLock.py](src/robomme/robomme_env/PatternLock.py) 的 `config_*`、`_load_scene/step`，`utils/adjacent.py::find_path_0_to_8/dfs_path`。默认最难档按官方hard，不先添加新档；未来若要另一种“最难”配置再单独决定。

**RouteStick**：现有映射：`sampling_config.native.length/walk` 对应 `parameters.RouteStick.configs[d].length/backtrack`、`parameters.RouteStick.walk`；几何与颜色来自 `positions.RouteStick`。现episode_spec已有 `layout.rotation_deg/obstacle_rgb`、`objects.L/allow_backtracking`、`actions.nodes/node_slots/directions`；演示视频目标时长及调节时长的方式、显式node/obstacle位姿及视频观测为拟新增。锚点：[RouteStick.py](src/robomme/robomme_env/RouteStick.py) 的 `_load_scene/step`、`utils/route.py::generate_dynamic_walk`、`_routestick_group`。

## 三、对拍闸门总表

闸门编号、判定行、步号与「证明什么」以第一部分第四节判据表为准，定义与「为什么能逐位」见 9.4；本表只补每个闸门的前置条件。

| # | 判定行 | 步号 | 前置条件 |
|---|---|---|---|
| G1 | `TRAIN_IDENTITY`、`TRAIN_SUBSET` | 0 | `freeze-identities` 完成，不启动仿真 |
| P0 | `NODE_PARITY` | 1b | job 1 上 A1 已过 P1；4 个占位 job 均 RUNNING |
| G2、G3 | `SAMPLING_ORIGINAL`、`FIELD_OWNERSHIP` | 3 | 该环境 `decision`／`native` 已按第二部分「二」映射提取 |
| G4 | `SPEC_BINDING` | 4 | 该环境 C 路完整规格已导出并封存 |
| G5 | `COMPARATOR_SCOPE` | 1b、5e | 官方两个比较器源码冻结；连续与稀疏夹具、缺失／额外／重复身份反例就绪 |
| P1 | `BASELINE_REPEAT` | 1b | 官方源码隔离目录与 manifest 就绪 |
| P2 | `TRAIN_RESTORE` | 2 | RouteStick 尾迹等恢复项逐项获批 |
| P3、P4 | `RNG_PARITY`、`INJECTION_PARITY` | 4 | G4 通过 |
| P5、P7 | `VIDEO_PARITY`、`RECOVERY_PARITY` | 5a | 16 环境各一条五路完成 |
| P6 | `WORKER_ISOLATION` | 5b | 48 格子集完成 |
| R1a | `DATASET_GEN_REPORT_PARITY` | 1b、5e | 按选定身份投影旧报告的身份／恢复模式／成功／帧数 |
| R1b | `REFERENCE_AUDIT_COMPLETE` | 5e | G5通过，发布集按revision `a5e4e25ffe8af34f64944f9533d06455ce5f8337` 恢复至 `data/robomme_data_h5/` |
| R1c | `HISTORICAL_ACTION_PARITY` | 1a、5e | 当前缺逐局旧数值证据，记 `NOT_RUN blocking=0`；找回并核验后才追加比较 |
| R2 | `HISTORICAL_ARTIFACT_PARITY` | 1a | 找回历史 HDF5 并散列核验通过后才改为实跑 |
| C1 | `TRAIN_COVERAGE` | 5d | 5a～5c 全部通过 |

## 四、runbook：命令与留档

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

`freeze-identities` 读取官方原文并保存1600条 `train_manifest.json`，同时按第四节规则输出144条 `subset_manifest.json`，各含来源散列与原身份；不启动仿真。单条命令中的 `--env/--episode` 须同时属于全量来源与子集，批量运行及比较都显式消费 `subset_manifest.json`，不得由 `--episodes 9` 推导连续编号。C路完整规格导出必须在步1b的A冒烟及步3的C冒烟通过后才分批启动，不能首次直接展开144条或可选1600条。候选规格来自已完成的C路，不接受重抽补位；比较器范围适配见9.6，正式比较前必须过G5。

每次代码改动后先运行 5 分钟内的相关测试；可以参考现有入口：

```bash
command -v uv
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
```

新命令的真实仿真、日志、大文件输出均置于 `artifacts/train-parity/` 的独立运行目录；轻量结果置于 `docs/validation/newtask-v3/`，原值配置和完整候选记录逐个明确加入 Git。媒体不提交；存储不足时先汇报明确的占用与处理范围，不清理旧产物腾空间。每步提交只暂存自己的路径，提交中文说明包含用户原话、计划、实施取舍、异常、实测结果与剩余边界。

## 五、风险登记

| 风险 | 来源 | 处置 |
| --- | --- | --- |
| A1↔A2 因 RRTStar 回退等因素不逐位一致 | `_planner_classes` 三次 screw 后三次 RRTStar 回退 | 该条记 `BASELINE_NONDETERMINISTIC`，不设新种子、不放宽容差（R5） |
| 历史报告标称 HEAD `9430e20bfcf59116d525778b60663520b22f63e6` 不是完整运行源码 | 校验器至 d53 才改为 100 条；父编排改过 worker 与 GPU 限制 | 固定 d53 为可重跑源码，历史报告单独冻结原文、参数与标称 HEAD，登记来源不完整边界 |
| 继承下来的旧改动被误当原始行为 | 如 `RouteStick.py::step` 尾迹 10 步 vs 官方 40 步 | 只比新代码默认路径与注入路径会漏掉，故必须先做 A↔B；此类项单列审批恢复 |
| 现有「注入后跳过一部分抽样」分支被直接当 D 路 | 现行注入代码 | 不得沿用；D 路必须原位消费冻结值并同序跑兼容核验（R8） |
| 跨节点、多 worker 结果差异 | 4 个占位 job 可能落在不同 A40 节点；原分支历史为 20 worker | 步 1b 的 P0 证 4 job 逐位等价、步 5c 证 4 worker 与单 worker 等价后才分片；不一致则单 job 串行，不改 seed 规则与 fail recover |
| 占位 job 到期或被抢占 | 48h walltime；chaijy2 池 80 CPU / 20 GPU / 960G 与他人共用，2026-09-21 观察到他人占 95 CPU / 23 GPU（配额执行口径待核） | 每 job 只领自己那一片 36 条，产物落 NFS 独立目录，重申请后从缺失身份续跑；任何时刻不超过 4 个 job |
| A40 与本机 Ada 不逐位一致 | greatlakes 规约实测 sm_86 对 sm_89 max\|Δ\|≈1.2e-5（另一负载） | 五路全部在 A40 上跑；本机结果只作调试参考，不进判据 |
| 耗时与磁盘无法预估 | 历史四环境 15 格 60 次生成 2479.7 秒只能估成本 | 第一次实测后再估算，不线性外推；存储不足时先汇报占用与范围，不清理旧产物 |
| 旧封套规则误校验新记录 | `io.py::validate_candidates` 写死公式 seed、100 条 block、配额、碰撞必须 PASS | 新版 `identity_source=train_metadata` 按版本分流校验（R9） |
| 原比较器把稀疏子集拒绝或误当连续前九条 | 两个原函数要求episode从0连续，CLI的 `--episodes 9` 不等于选定九条 | 采用9.6的范围适配与G5，保留原身份；缺失、重复、额外group都须拒绝 |
| 恢复动作相同但xy方向仍从内部抽样驱动 | `subgoal_planner_func.py::_sample_fail_recover_xy_signs/solve_pickup_fail` | 规格、随机流和实际偏移三者分别核验；G4必须识别重抽相同却不消费规格的反例 |
| 工具文件被顺手改动 | `object_generation.py`、`route.py`、`task4recovery.py`、求解器 | 环境文件获批不推导出工具文件获批；确需改动另列函数与理由 |

## 六、盲区诚实清单

- 当前工作副本没有 `data/` 目录与 `artifacts/native-baseline/`；报告所指 `/data/hongzefu/robomme_benchmark-restore-DataGen/` 及其生成、参考目录均不存在，历史 HDF5 不可直接读取，只能与报告已保存的字段比较。
- 既有报告 `different_element_count` 统计的是 `delta!=0.0`，没有「超过 `1e-8` 的元素总数」，两者不能混称，也不能虚构完整元素差异表。
- 历史动作数值只有1600条全局汇总，不能投影144条；R1c明确“未验证”。用户已选择不以此缺证阻塞本轮完成，不能将其改写为通过；R1a的可比字段仍必须对齐。
- 依赖指纹只证明锁文件字节关系（当前 `uv.lock` `ff0ffd84…`、`pyproject.toml` `d03537d6…` 对官方 `983de83f…`、`bc2346e4…`，差异仅 `pebble==5.2.2`），本轮没有重建仿真环境，不能由此推出仿真可复现；各路仍须记录实际 Python、Torch、SAPIEN、ManiSkill、mplib、驱动及设备。
- 历史内部随机观察范围另列：A 路以未覆盖生成作输出锚点，`RNG_PARITY` 只在 B／C／D 之间逐调用比较。
- 覆盖缺口：144条子集不含每环境episode 5，共16条配置xy恢复的身份未验证；只能按冻结清单报告80条恢复配置覆盖。其他未出现的分支（如某些交换次数或恢复组合）逐项列为缺口，不得额外构造测试冒充train数据。
- `VideoRepick/hard` 分支目前仍内部随机生成，`_repick_group` 拒绝 hard，不能假定已外置。
- 本地 `3a5951a834ea014f63724647ab0bc091eb9f109d` 与官方 54 个 Python 源文件及锁文件字节相同，只可作技术参考，不能替代官方身份来源。

## 七、留档与 commit 纪律

- 真实仿真、日志、大文件输出置于 `artifacts/train-parity/` 的独立运行目录；轻量结果置于 `docs/validation/newtask-v3/`；原值配置与完整候选记录逐个明确加入 Git；媒体不提交；官方十六份 metadata 原文及来源散列保存在 `scripts/configs/newtask-v3/official_train/`。
- 每次提交只暂存自己的路径；commit subject 沿用 `<大版本>.<小版本> <中文描述>` 体例，body 含用户原话、计划、实施取舍、异常、实测结果与剩余边界；提交后立即 `git push`。
- 文档验收：十六环境逐个列出、未来需求有落点、原值与新值不混淆、引用文件与函数存在、无硬编码行号、不把待实现命令写成已有能力；运行 `git diff --check`。
- 实施结果以子节追加在第一部分第五节的步骤表之后与第六节之后，保留原计划与本轮核验边界。

## 八、接口组织细节

第一部分第三节的完整展开；小节编号 8.x 与原 3.x 一一对应。

### 8.1 配置快照与每局规格分别负责什么

拟新增 `scripts/configs/newtask-v3/native_sampling.json`，覆盖十六环境。新快照按 `tasks[env].decision` 与 `tasks[env].native` 分块：前者是第二节中标明拟修改的参数，后者是维持原状的规则与常量。传给 `gym.make(..., sampling_config=...)` 的是本环境的这两个子块。**这是拟定的新格式，不是现有 schema 3 的真实键。** 现有四环境的 `parameters[task]/positions[task]` 按第二节映射转换，其余十二环境从源码变量提取；旧快照与旧候选保持原版本、原内容，不就地改写。

原生源码是默认值的依据，两块原值都从固定来源提取并校验，不维护两套手填默认值。原值对拍模式下，decision也不可改；未来新值模式才允许修改decision。native中任一取值域、选择规则、单位、dtype、随机源、端点语义或拒绝条件改变，都必须显式列为新的用户决策，不能混在“仅随机外移”中。缺失／未知键、类型错误、跨任务规格、来源不匹配直接报错；每任务解析结果深拷贝，禁止污染类级配置。

原四环境的旧外部生成器位于 `scripts/injection/candidates/sampling.py`，使用PCG64、配额、分层和方向平衡；这些旧策略不自动继承到原train对拍。`build_button` 的 `randomize_range` 是全宽，偏移公式为 `(u-0.5)*range`；位置单位、dtype、运算顺序、相机、尺寸、控制器与成功阈值保持原口径，未声明的常量不因外提配置而获得新语义。

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
| `actions` | 抓放目标序列、交换双方、路线与方向、事件窗口；`recovery`含失败动作索引、模式与执行事件的 `xy_signs`，派生偏移和实际绑定按8.2核验 | 由颜色名称或最近对象再次猜目标；仅保存失败动作索引、仍用内部重抽方向驱动偏移 |
| `initializations` | 以初始化序号保存每次颜色排列、孔／杆位姿及输入边界；即第二节的 `episode_spec.initializations` | 构造期和显式reset共用一条抽样结果 |
| `sampling_trace` | 按原调用阶段编号的随机源、调用签名、原始结果、拒绝尝试、调用前后状态指纹，包含执行时独立恢复流及 `[0,0]` 拒绝重抽 | 只在结尾恢复generator状态，忽略中间随机消费；把trace记录当成实际规格赋值 |
| `provenance` | 配置／源码／依赖／规格内容散列及数组 dtype、shape、编码约定 | 用四舍五入的浮点文本承诺逐位相同 |

数组记录原 dtype 与 shape，采用可无损往返的表示；浮点比较按原始位模式，Python 标量保留原类型与运算次序。坐标以米计，角度字段必须明确度或弧度，四元数明确原 API 分量顺序。这里没有训练模型或可训练参数，不能用张量形状一致代替仿真行为一致。

逐局唯一数据文件仍采用 Git 跟踪的 `candidates.jsonl`，但为原始 train 新增显式版本和 `identity_source=train_metadata`。它只是承载固定记录，**不能复用旧封套的公式 seed、100 条 block、train/test 配额和碰撞必须 PASS 规则**。`scripts/injection/candidates/io.py::validate_candidates` 当前把这些规则写死，必须按版本分流校验；旧运行十保持原版本和原字节。生成、reset 核验都从同一记录投影参数；未来策略端若接入也消费同一身份，不另手填 seed。候选导出失败的身份保留在全集账本中，不伪造完整规格。

### 8.2 外部供值与原始 train 对拍怎样兼容

“外部”指环境接收到冻结的本局值，不在消费规格时临时决定一个新目标、新布局或新交换搭档。第一轮不能用独立新seed重抽原train，因此外部记录来源固定为原生C路的只读导出；后续新值模式才按已批准的decision参数由外部生成器生成新样本。两种模式明确区分：

| 模式 | 外部规格怎样产生 | 原随机规则怎样处理 | 能宣称什么 |
| --- | --- | --- | --- |
| 原值对拍 | 原官方身份驱动C路，把每个原取值点的结果导出至外部规格，完整事件后封存 | D路按原位置消费冻结值；原RNG仍照原次序运行作兼容与核验，其返回值不得替代episode_spec作为场景输入 | 同一官方样本注入前后相同 |
| 未来改值 | 外部供值器读取decision新值和native原规则，生成本局随机输入，再计算派生字段；延迟依赖实际状态的字段须经过原事件时点解析／冻结流程 | native的原规则不变；不继承旧配额／分层／方向均衡。算法或分布若要改，另列用户决策 | 固定新规格可重放；不声称与原train逐条相同 |

因此“运行中仍有RNG核验”不表示场景输入仍可忽略外部规格。拒绝采样的失败尝试、单候选抽样、被后续语句覆盖的抽样全部保留；只读导出不额外抽随机数、不增加物理step。完成对拍前，不删除兼容抽样来做性能优化，也不以末尾set_state掩盖中途漏抽。

```text
原来：原 generator → 原调用点抽样 → 建对象／生成动作
导出：原 generator → 同一调用点抽样 → 只读记下结果 → 原对象／动作
回注：外部冻结值 → 对应调用点赋值／绑定 → 同一对象／动作
      原 generator → 同序抽样作兼容核验 ────┘（只校验，不替代冻结值）
```

这不是减少抽样次数的优化；目的是第一轮同时做到完整冻结、原始随机流不漂移。一个 `(阶段, 初始化序号, 对象ID, 事件序号)` 只消费一次对应记录。交换搭档在交换发生时才知道的，导出完整运行中当时的实际绑定；D 路在同一时点核验并使用该绑定，不在构造时按初始坐标重选。第一次导出必须完成相关事件后才能把规格标为完整。

特别要覆盖 `BinFill` 两次初始化各自的颜色排列、`VideoRepick/hard` 的十五块原生路径、`InsertPeg` 乘零却仍消费随机数的尺寸抽样、被强制改为 0 的目标索引抽样，以及 `inject_fail_grasp` 的真实选择。现有“注入后跳过一部分抽样”分支不能直接沿用为 D 路。

**恢复规格的共同定义**适用于第二节所有 `episode_spec.actions.recovery` 字段。选择失败动作和执行xy偏移是两个不同的随机事件：`task4recovery.py::inject_fail_grasp` 先选动作；真正执行时 `subgoal_planner_func.py::_get_fail_recover_rng` 用env.seed建立独立Torch generator，`_sample_fail_recover_xy_signs` 抽 `torch.randint(-1,2,(2,),dtype=torch.int64)` 并拒绝 `[0,0]`，`solve_pickup_fail` 才将符号乘偏移量加到抓取位置。必须在各自原调用点导出和消费，不能只冻结前一个索引。

拟定 `actions.recovery` 保存入口 `configured_mode`、原失败动作 `selected_action_index` 和 `events[]`；每个执行事件以原动作索引及 `event_index` 标识，并保存 `mode/seed_anchor/rng_source_id/xy_signs`。xy符号保持原 `int32[2]`；z事件的符号为null，没有实际恢复的身份保存空事件列表和明确null动作，不因配置开关造出事件。`sampling_trace` 按同一随机源和调用编号记录全部 `int64[2]` 原始抽样、拒绝尝试及前后状态。

`xy_offset` 是原求解器调用参数，保留原取值、float32转换、标量扩展和乘法顺序；`signed_offset=xy_offset*xy_signs.astype(float32)` 按冻结符号派生，不作为可独立填写的第二真值。C导出派生偏移及 `fail_pose_p` 实际绑定证据；D用规格符号计算并赋值，兼容抽样结果只核验，z原偏移不变。只读证据逐项关联到规格路径和最终赋值，录像器保持冻结。

G4须增加明确反例：保留原随机重抽、校验和相同输出，却绕过规格符号驱动 `fail_pose_p` 时判失败。审查中seed4301的 `[1,-1]` 已证明重抽相同且RNG状态相同仍可零读取规格；原身份seed11401、5300均出现先拒绝 `[0,0]` 的过程，须纳入拒绝轨迹核验。这些是现有原行为的消费要求，不改分布；公共工具源文件或运行时覆盖仍须逐函数批准。

未来更改数量、布局和动作次数后，每局结果可能不同；使用同一抽样规则也不意味着得到相同随机流轨迹。第一轮只实现原值导出／消费、decision与native的结构及校验，不实现角落加权、额外干扰物生成、三次抓取、多对象视频或时长调节算法。第二节列出的未来值只进入方案，不提前写进生效配置。

### 8.3 后续修改的配套约束

| 用户决策 | 对应规则／派生关系 | 仍需决定或保持的边界 |
| --- | --- | --- |
| 增加次数或对象数 | 更新完整对象列表、拾取列表、交换列表与动作展开 | 不把新数值塞进现有 `if count==2` 后就认为功能成立；StopCube运动段须覆盖选定次数 |
| corner／clutter | 用户改区域或布局策略，外部生成具体xy／yaw | 桌面可行域、可达性、原碰撞约束保留；未定边界、密度、距离不编造默认值 |
| distractor／任意颜色 | 用户给颜色策略，外部产生逐对象颜色与角色 | “其他颜色”相对目标池定义；颜色不是对象ID；池、数量、放置位置未定时保留待决 |
| 两块演示，各自回原位 | 每对象起始位姿 → 每对象返回目标，不再随机抽返回点 | easy原只有一块；两对象共享还是分别抽动作序列，须未来明确；其余语义保持 |
| 交换速度×1.5 | 时间倍率统一派生动作、藏块跟随和交换窗口 | 只适用于两个UnmaskSwap；不自动用于VideoRepick；离散步取整须决定 |
| PatternLock／RouteStick演示20～30秒 | 先决定时长策略，再按实际录制帧数／fps验收 | 现录像器30fps对应600～900实际演示帧；`save_robomme_video`默认20fps不能混算；不改fps／补重复帧凑长度 |


## 九、原始对拍细节

第一部分第四节的完整展开；本节统一现行144条子集、80条恢复和历史缺证不阻塞的口径，判据与第一部分一致。1600条是身份来源全集，8000次只属于可选步7；旧版本记录保留在第一部分第六节。并行条件依第一部分P0和步骤表，不在本节另立旧资源口径。

### 9.1 逐条采用 metadata，不能只指定 `--layout train`

用户先明确「我说的是原始的[https://github.com/RoboMME/robomme_benchmark](https://github.com/RoboMME/robomme_benchmark) train16*100」，随后指定「[https://github.com/RoboMME/robomme_benchmark/tree/dataset-gen](https://github.com/RoboMME/robomme_benchmark/tree/dataset-gen)和这个branch的测试结果对拍」「这个里面也有fail recover」。因此**身份和生成行为均以官方 `dataset-gen` 为准**，固定本轮联网核验提交 `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`；不把本地 fork 的扩展 metadata 或官方 main 的无恢复 Builder 路径当对拍基线。

实读官方十六份 JSON，每环境恰好 episode 0～99，共 **1600 条**，各环境 easy／medium／hard 为 50／25／25。官方 1600 条完整记录与当前各环境前 100 条的差异为 **0**；12 份文件全文字节相同，四个 Unmask 环境在本地扩为 400 条，只有记录扩展及 `record_count` 不同。本方案不使用扩展出的 1200 条，也不需要修改本地 `src` 下的 metadata；后续在 `scripts/configs/newtask-v3/official_train/` 单独保存官方十六份原文及来源散列。

官方 records 按 `scripts/seed_layout.py::ALL_TASKS` 的环境顺序、各文件原 records 顺序串接，以 `json.dumps(records, sort_keys=True, separators=(',', ':')).encode()` 计算，SHA-256 为 `a57655d601c7e974c688b2b5c3602e7eb8606e2bd312dcc4ba00a1abb29d73bf`。这 **1600 条中有 170 条**实际 seed 不等于 `SeedLayout.base_seed` 的 attempt 0 公式。例如 `BinFill/episode_3` 是 `difficulty=hard, seed=4301`，公式却是 `4300`。新增入口严格读取官方 `(task, episode, seed, difficulty)`；保留原记录，不重算 seed。运行尝试序号与官方历史 seed 分开记录，每条只运行该 seed 一次，失败不调用 `EpisodeJob.bump`、不换 seed、不补样本。

该分支的正式入口为 `scripts/data-generation/generate_dataset.py::generate_dataset/_worker`，按metadata实际seed、difficulty各生成一次。`EpisodeJob.recovery_mode` 在每环境episode 0～2返回z、3～5返回xy，其余返回None；worker据此传恢复开关和模式。1600条全集配置恢复96条（z48、xy48），144条子集配置恢复80条（z48、xy32、关闭64），P7按实际运行manifest核对。五路必须保留原开关、`inject_fail_grasp` 动作选择和8.2规定的执行时xy方向消费；是否实际触发另记事件，不能只比较开关或把80当成实际触发数。

现行 `generate_dataset_newseed.py` 默认按公式建任务，需要在 `scripts/` 侧增加严格官方清单模式，复用既有生成链路并与该分支逐函数核对：`_planner_classes` 的三次screw后三次RRTStar回退、`_execute_tasks` 的真实动作顺序、`_worker` 的恢复与录像参数、合并和metadata输出。原分支CLI限定GPU字符串 `"0"`、历史全量20 worker是来源事实；本次资源及worker数量以第一部分P0与步骤表为准，不改变seed规则和fail recover。

### 9.2 从 dataset-gen 原版到注入版，必须有两段证据

```text
dataset-gen 固定提交 + 官方 train 1600 条来源身份
          │ 冻结144条子集 + 所选身份的原 fail recover
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

### 9.3 每条身份走五次独立生成

| 路径 | 输入 | 比较目的 |
| --- | --- | --- |
| A1、A2 | 固定 `dataset-gen` 源码＋官方 metadata＋原 fail recover | 独立重跑该分支原 worker；先检查自身是否可重复，并与可取得的历史成品及报告比较 |
| B | 新分支恢复后的默认值，不传两个接口 | 与 A1 比，定位历史行为未恢复的差异 |
| C | B＋显式原值 `sampling_config`，只读导出规格 | 与 A1、B 比，证明配置外提不改值 |
| D | 同一配置＋C 导出的原值 `episode_spec` | 与 A1、C 比，证明对象、动作及随机流回注一致 |

各路先在同一设备单worker、相同求解器配置下建立锚点，再按第一部分P0及步5c核验后放开并行。单条失败保留原身份；A1／A2若因RRT回退等因素不逐位一致，该条列为 `BASELINE_NONDETERMINISTIC`，不能设置新种子、给A加补丁或放宽容差。各路同样失败只能报告失败分类一致，不能计作成功生成或144条严格对拍通过。

先选 `BinFill/easy/episode_0` 做单任务、单episode、单worker冒烟，保留z恢复；逐阶段检查退出状态，再扩到十六环境各一条。正式子集每环境固定episode `[0,1,2,3,4,6,7,10,11]`，覆盖48个task／difficulty格及z／xy／关闭三模式；每环境episode 5不在本轮。逐项核对 `BinFill` 两种dynamic、`VideoRepick/hard`、单双拾取、零／非零交换及延迟搭档的实际覆盖，未出现者列缺口，不换样、不另造train身份。额外隔离反例只证明比较器能抓错，不算train覆盖。

当前验收分母固定 **144条**，A1／A2／B／C／D共 **720次生成**；未完成、不可比或异常身份均留在144条分母。只有用户另行启动可选步7才改为1600条、8000次。上述都是未来工作量，本轮没有执行仿真；通过144条不得外推1600条。

### 9.4 具名判据

| 查什么 | 怎么查、为什么能证明 | 通过判定行 |
| --- | --- | --- |
| 原身份完整 | manifest 与官方固定 metadata 逐条双向比较；拒绝重复、漏项、额外项和实际 seed 被公式替代 | `TRAIN_IDENTITY=PASS tasks=16 rows=1600 mismatch=0` |
| 配置外提完整 | 十六环境配置键映射到源码消费点；原运算元、dtype、区间边界及有效／死字段分别核查 | `SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0` |
| 字段归属完整 | 第二节每项都能映射到decision或native及其本局输入／运行观测；用户新值仅在decision，原值阶段两块均采用原值；最近邻／补集／时间表等不独立抽签 | `FIELD_OWNERSHIP=PASS tasks=16 unmapped=0 native_rule_overrides=0` |
| 规格完整且真正消费 | 逐局核对对象、布局、目标、动作、初始化及恢复；xy恢复必须由规格符号派生偏移并绑定实际抓取位置，原重抽相同却绕开规格的反例也必须被发现 | `SPEC_BINDING=PASS missing=0 unused=0 mismatch=0` |
| 比较器范围适配 | 连续范围与官方原函数同结果；稀疏原身份不改编号，缺失／额外／重复输入必须拒绝；具体夹具见9.6 | `COMPARATOR_SCOPE=PASS contiguous_mismatch=0 sparse_mismatch=0 invalid_accepts=0` |
| 原版自身重复 | A1↔A2 的原始 HDF5、图像、状态与事件；不可重复的身份单列 | `BASELINE_REPEAT=PASS compared=N different=0` |
| 随机流不漂移 | B／C／D 比调用序号、源身份、签名、结果、拒绝记录与前后状态；A 路以未覆盖生成作输出锚点，历史内部随机观察范围另列 | `RNG_PARITY=PASS compared=N calls_mismatch=0 state_mismatch=0` |
| 原始行为已恢复 | A1↔B 全字段比；不能排除 RouteStick 尾迹、演示标志或恢复事件来求通过 | `TRAIN_RESTORE=PASS compared=N mismatch=0` |
| 原值注入等价 | B↔C、C↔D、A1↔D；逐元素比较 dtype、shape、数值位模式、所有 group/dataset/attribute | `INJECTION_PARITY=PASS compared=N mismatch=0` |
| 图像与录像事件 | 比实际落盘 RGB 与演示／执行标志、真实帧索引；MP4 比完整解码帧数与像素，并单列编码容器散列 | `VIDEO_PARITY=PASS compared=N frames_mismatch=0 pixels_mismatch=0` |
| 连续 worker 不污染 | 每环境选不同原身份，甲→乙→甲在同一 PID 运行，各自与独立进程比；原配置、规格输入散列不变 | `WORKER_ISOLATION=PASS tasks=16 mismatch=0 input_mutation=0` |
| fail recover保持原样 | 比144条的原模式、实际动作、xy方向／偏移和运行事件；配置计数与触发计数分开，未触发不得造事件 | `RECOVERY_PARITY=PASS compared=144 configured=80 z=48 xy=32 off=64 mode_mismatch=0 event_mismatch=0` |
| 历史可投影字段 | 只投影144条身份、恢复模式、成功、帧数；字段范围显式声明，不包含历史动作数值 | `DATASET_GEN_REPORT_PARITY=PASS compared=144 fields=identity,recovery_mode,success,timestep_count outcome_mismatch=0 detail_mismatch=0` |
| 本次发布集审计完整 | 经9.6适配器审计144条，合同无错、身份无漏；原动作 `1e-8` 结果单列，不把审计完整写成数值相等 | `REFERENCE_AUDIT_COMPLETE=PASS compared=144 contract_errors=0 missing=0` |
| 历史动作数值核对 | 当前缺逐局旧数值证据，明确未验证；用户已选择不阻塞完成 | `HISTORICAL_ACTION_PARITY=NOT_RUN reason=historical_per_episode_evidence_missing blocking=0` |
| 历史成品额外比较 | 仅在找回且散列核验通过时比历史原 HDF5；本轮已知文件缺失，不能当作默认能通过的项 | `HISTORICAL_ARTIFACT_PARITY=NOT_RUN reason=historical_files_missing` |
| 失败与子集覆盖 | 全部144条都有终态；missing、timeout、error、不可重复、不可比和成功分别计数，失败保留退出码与阶段 | `TRAIN_COVERAGE=PASS expected=144 terminal=144 missing=0` |

表中N及单条／分批统计均按实际范围输出，完整子集才使用144／80。完成条件以第一部分第四节为准：本次严格对拍不能存在未解决差异；R1c、R2缺证允许 `NOT_RUN`，不取消d53新跑对拍及历史已有字段核对。HDF5散列相同证明字节相同，散列不同继续比全部字段，视频另比像素；注入前后不设容差，发布参考集动作审计仍使用原 `1e-8` 并保留原始失败结果。不能把历史缺证不阻塞解释成允许本次五路差异。

录像器 `RecordWrapper.py` 全程冻结：不补 reset 帧，不录制原 `NO RECORD` 帧，不改变命名和输出位置。需要 reset 图像时在入口侧读取已有 reset 返回值，事件时间使用实际编号。旧 `tests/_shared/parity_observer.py` 会覆盖录像器方法，不能直接作为本次生产对拍观察器。测试内可做隔离反例，但不能将覆盖后的生成结果作为无覆盖 A 基线。

### 9.5 当前已有证据和缺失证据

该分支已跟踪 [generation_report.json](https://github.com/RoboMME/robomme_benchmark/blob/d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa/scripts/data-generation/reports/generation_report.json) 和 [generation_report.md](https://github.com/RoboMME/robomme_benchmark/blob/d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa/scripts/data-generation/reports/generation_report.md)。既有报告标称运行提交 `9430e20bfcf59116d525778b60663520b22f63e6`、报告时间 `2026-07-15T04:14:21.522575+00:00`。**此标称 HEAD 不能单独作为完整运行源码**：该提交的校验器还限制 9 条，至 d53 才改成 100 条；父编排也改变了默认 worker 和 GPU 限制，而 `_worker`、`EpisodeJob`、求解与任务执行、合并、动作比较器、环境源码与锁均未变。因此本方案固定 d53 为可重跑源码，历史报告单独冻结其原文、参数与标称 HEAD，并登记运行源码来源不完整的边界，不把它写成 clean 9430e20 已可复现的结果。

**这份既有结果不是全通过**：1600 条全部成功生成，生成与官方 HDF5 结构错误均为 0；但 `joint_action` 对官方发布 HDF5 的比较记录 761885 个向量、6095080 个元素，其中 **217242 个元素存在非零差异**，10 条时间步集合不符，最大绝对差为 `0.007857919612339614`，超过原阈值 `1e-8`，报告 `status=failed`，完整验收未通过。`different_element_count` 统计的是 `delta!=0.0`，报告未提供“超过1e-8的元素总数”，不能混称。原报告及上述全集统计原样保留；逐条只对齐R1a可投影字段，历史动作数值按R1c记未验证，不能为得到PASS改阈值、关恢复或换样本。

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

历史报告的 `generation.results` 和合同逐局记录可按144条投影身份、恢复模式、成功和帧数，作为R1a；`validation.joint_action_comparison` 只有1600条总计，没有逐局动作数值摘要。217242个非零元素不能拆出子集贡献，唯一最大差位置BinFill/99也不在子集；十条时间步错误只有BinFill/11和PickHighlight/3被本次选中。因此历史动作数值不能按144条判零漂移，不能用错误总数相同代替逐条证据。

本次三组证据分别保存：R1a比上述历史可读字段；P1～P7以d53重跑A1／A2对B／C／D做严格比较；R1b经9.6范围适配器对144条重跑原合同和动作比较核心，记录本次逐条结果、错误、数值摘要及原 `1e-8` 状态。R1b的审计完成不代表数值相等，也不代表与历史数值对齐。历史动作数值核对单列R1c为 `HISTORICAL_ACTION_PARITY=NOT_RUN reason=historical_per_episode_evidence_missing blocking=0`；用户已选择此缺证不阻塞本轮完成，不能虚构历史逐值明细。

当前工作副本**没有 `data/` 目录**，也没有 `artifacts/native-baseline/`；报告所指 `/data/hongzefu/robomme_benchmark-restore-DataGen/` 及其中生成、参考目录本轮检查也均不存在。历史报告和 32 文件散列清单可读，历史 HDF5 目前不可直接读取。主方案以 d53 独立重跑 A1／A2，并与现有历史报告所存结果逐条对照；历史原文件的全内容比较额外记 `HISTORICAL_ARTIFACT_PARITY=NOT_RUN`。若后续找到原文件，先核验清单再只读复制进本仓库追加比较，不冒称已完成。官方发布数据按报告 revision `a5e4e25ffe8af34f64944f9533d06455ce5f8337` 恢复至 `data/robomme_data_h5/` 后，才能重跑原发布集比较器。

历史 [原值对拍报告](docs/validation/newtask-v2/20260909-actions-v3/README.md) 记录四环境 15 格、60 次生成、2479.7 秒；它可用于估计成本，不能作为本次十六环境或完整规格回注的通过证据。[非布局差异审计](docs/validation/newtask-v2/20260912-train-nonlayout-audit.md) 已指出 seed、规格分布和模拟演示等区别，本轮又核对了相关现行源码。

当前依赖指纹：`uv.lock` 为 `ff0ffd847a55f77d61c3d11efe4ad11e8776534e044f0ddb2b22396d838fa5f3`，`pyproject.toml` 为 `d03537d6c77a8d8213bc881da6ac470b2d8a80cf5f883df587d9df634374db36`。官方对应指纹分别为 `983de83f7b22c98b96c3c25a39958b4f5920e3232cfaa209c89542ef5639ac03`、`bc2346e4526c2b5c2177fe5191710c81f883c21017d45928e615327cf29cb21a`。两锁的包名／版本差异只有当前新增 `pebble==5.2.2`。后续各路仍必须记录实际 Python、Torch、SAPIEN、ManiSkill、mplib、驱动及设备；本轮没有重建仿真环境，不能由锁文件指纹推出仿真已经可复现。

### 9.6 原比较核心的稀疏范围适配

固定官方 `validate_generated_dataset_contract.py::validate_generated_dataset_contract` 和 `compare_joint_actions.py::compare_joint_actions` 均要求episode从0连续。子集 `[0,1,2,3,4,6,7,10,11]` 会在读取HDF5前被拒绝；原CLI的 `--episodes 9` 会误选0～8，不能直接使用。正式运行仍保留原身份，禁止重编号、填补样本或为绕过守卫扩大生成范围。

拟新增 `scripts/train_split_comparison.py`，冻结官方原文件及散列；适配器从固定版本保留原合同与动作比较实现，只调整范围、预期集合及元数据投影，保存逐函数最小diff。`validate_manifest_scope` 接收按task分组的显式原episode列表并逐条回查官方metadata，拒绝重复、额外、跨任务及身份不符；`validate_generated_subset` 要求生成文件的episode集合恰为所选集合，发布参考文件仍按原完整集合检查后只比较所选条目；`compare_joint_actions_subset` 仅遍历显式选定键。

原字段／终态检查、时间步连续性、dtype／shape、逐动作比较顺序、`delta!=0` 计数、最大差定位和 `1e-8` 阈值不变。审计结果按task／episode留存，并可附子集汇总；历史缺失的逐局摘要不能用本次新结果补造。适配器不改官方原文件，不给环境或录像器打运行时补丁。

G5的离线夹具分三组：连续前缀输入同时调用原函数和适配器，除明确声明的文件根路径与新增逐局包装外结果相同；稀疏夹具保留真实编号，预先构造各条已知动作差、帧数错配及最大差位置，断言选择集合和数值统计精确对应；重复、缺失、额外episode、身份不符、dtype／shape变化、非有限数、超过 `1e-8` 的变化分别验证拒绝或保留原失败结果。全通过才输出 `COMPARATOR_SCOPE=PASS contiguous_mismatch=0 sparse_mismatch=0 invalid_accepts=0`，其中invalid仅指无效范围被接受；比较器对数值差异返回原失败也是正确结果，不能混算。测试夹具不算官方train覆盖。

## 十、集群算力实测与 job 分片

**副本与环境**：`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl`，2026-09-21 从 `newtask-v2.1refractor` 提交 74dc5ce 克隆；venv 解释器为 NFS 上的 `uv-python/cpython-3.11.14`，`UV_LINK_MODE=copy uv sync --frozen` 装 109 个包约 4 分钟，退出 0。实施开始后该副本须切到 `newtaskRelease-v3` 并与主副本同 HEAD。

**探针实测**（2026-09-21，job 61665377，gl1502，1×A40，8 CPU，48G，`BinFill --layout train`，产物在副本 `artifacts/gl-probe/61665377/`）：

| 轮次 | worker | 条数 | 总耗时 | 吞吐 | 单局 RSS 峰 | 进程组 RSS 峰 | 显存峰 | CPU% 总和峰 |
|---|---|---|---|---|---|---|---|---|
| w1 | 1 | 2 | 85 s | 1.42 条/分 | 3.9 GB | 7.5 GB | 0.6 GB | 56% |
| w8 | 8 | 8（episode 3 重试 1 次） | 136 s | 3.52 条/分 | 5.6 GB | 38.5 GB | 5.0 GB | 428% |

三点结论：SAPIEN 在 A40 上可用（有 Vulkan ICD 警告，不致命）；内存是硬约束，每 worker 按 6 GB 预留，CPU 每 worker 1 核（`limit_threads=true`）；8 worker 只得 2.5 倍加速，短批里启动与场景编译占大头，真实并行效率以步 5c 长批为准。`ps` 的 CPU% 为进程生命周期均值，偏低。w8 的 `video_status` 全为 `frame_mismatch`，须在步 1b 与本机同一身份对照确认是否为既有行为。

**占位 job**（形状 1 GPU / 4 CPU / 32G / 48h，`sleep infinity` 挂住分配，任何时刻不超过 4 个）：

```bash
sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 \
  --cpus-per-task=4 --gpus-per-node=1 --gpu_cmode=shared --mem=32G --time=2-00:00:00 \
  --job-name=hold-4cpu-<n> --output=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/slurm-holds/logs/hold-4cpu-%j.log \
  --wrap='echo NODE=$(hostname) CVD=$CUDA_VISIBLE_DEVICES; sleep infinity'
```

往 job 里塞任务，在登录节点 tmux 内执行，日志落 NFS：

```bash
srun --jobid=<占位JOBID> --account=chaijy2 --partition=spgpu --gpu_cmode=shared \
  --overlap --exact --nodes=1 --ntasks=1 --cpus-per-task=4 --gpus-per-node=1 --time=<步骤时限> \
  --chdir=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl \
  bash -c 'set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python scripts/train_split_parity.py run --manifest <manifest> --shard <k>/4 --paths A1,A2,B,C,D --workers 4 --gpus 0 --output artifacts/train-parity/<run>/shard<k> 2>&1 | tee artifacts/train-parity/<run>/shard<k>.log'
```

**分片表**（按 `scripts/seed_layout.py::ALL_TASKS` 顺序切 4 组，每 job 4 环境 × 9 条 = 36 条身份，五路 180 次；4 worker 按约 2 条/分估 1.5 h，48h 裕度充足）：

| job | 环境 | 身份数 | 生成次数 |
|---|---|---|---|
| 1 | ALL_TASKS[0:4] | 36 | 180 |
| 2 | ALL_TASKS[4:8] | 36 | 180 |
| 3 | ALL_TASKS[8:12] | 36 | 180 |
| 4 | ALL_TASKS[12:16] | 36 | 180 |

规则：每 job 只处理自己的分片，产物目录按 shard 隔离；P0 用同一身份在 4 个 job 各跑 A1；job 被回收后重申请同形状 job，从缺失身份续跑，不重跑已完成身份；`compare` 在登录节点只读汇总，不占 GPU。当前在跑的 61665377 是 1 GPU / 8 CPU / 48G 的探针 job，正式分片前换成 4 个 4 CPU job。
