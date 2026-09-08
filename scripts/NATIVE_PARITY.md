# RoboMME-ICL 固定参数与原版一致性检查清单

**结论：重构代码已落地，但当前原版一致性验收未通过。计划中的 12 局实际只完成 3 局新版自身重复运行认证；这不能证明四任务的全部素材、subgoal 和事件与原版一致。按用户最新指令，不运行 96 局，不追加仿真批次。**

本报告日期为 2026-09-08。原版固定为 `76ae12bf1e71f79e1c3f608eede10ac7430b406f` 的 `src/robomme`；12 局运行基线为 `6010daa58da05591e045b78ea62f195a95287877`。以下严格区分配置覆盖、源码复用、真实运行证据和未验证项。

## 清单一：新版额外固定的输入

### 任务分布

来源：[task_distribution.json](../src/robomme_icl/configs/task_distribution.json)。这些是用户要求保留的新版输入，不声称与原版默认随机分布相同。

| 配置键 | 当前值及作用 |
| --- | --- |
| `schema_version` | `1`，任务配置格式版本 |
| `compiler_seed` | `20260907`，任务组合与配额随机流 |
| `episode_seed_start` | `2000000000`，episode seed 起点 |
| `task_order` | BinFill → RouteStick → VideoUnmaskSwap → VideoRepick |
| `episodes_by_difficulty` | 每任务 easy/medium/hard 各 8 条，默认共 96 条；本次命令覆盖为每任务总计 3 条，共 12 条。默认配置未改，但不运行默认批次 |

候选数组中的每个值均保留；合法组合筛选与次数配额在 [sampling/tasks.py](../src/robomme_icl/sampling/tasks.py) 中完成。

| 任务／难度 | 固定的参数候选 |
| --- | --- |
| BinFill easy | `pick_count=[1,2,3]`；`spawn_count=[4,5,6]`；`target_color_count=[1]`；`scene_color_count=[1]`；`dynamic=[false,true]` |
| BinFill medium | `pick_count=[2,3,4]`；`spawn_count=[8,9,10]`；`target_color_count=[1,2]`；`scene_color_count=[2]`；`dynamic=[false,true]` |
| BinFill hard | `pick_count=[3,4,5]`；`spawn_count=[10,11,12]`；`target_color_count=[2,3]`；`scene_color_count=[3]`；`dynamic=[false,true]` |
| RouteStick easy | `walk_steps=[2,3]`；`allow_backtracking=[false]` |
| RouteStick medium | `walk_steps=[4,5]`；`allow_backtracking=[false]` |
| RouteStick hard | `walk_steps=[4,5,6,7]`；`allow_backtracking=[true]` |
| VideoUnmaskSwap easy | `container_count=[3]`；`pick_count=[1,2]`；`swap_count=[1,2]` |
| VideoUnmaskSwap medium | `container_count=[4]`；`pick_count=[1]`；`swap_count=[1,2]` |
| VideoUnmaskSwap hard | `container_count=[4]`；`pick_count=[2]`；`swap_count=[2,3]` |
| VideoRepick easy | `spawn_count=[3]`；`repeat_count=[1,2,3]`；`swap_count=[1,2]` |
| VideoRepick medium | `spawn_count=[3]`；`repeat_count=[1,2,3]`；`swap_count=[2,3]` |
| VideoRepick hard | `spawn_count=[15]`；`repeat_count=[1,2,3]`；`swap_count=[0]` |

BinFill 的 `target_color_count` 是选中的目标颜色池大小；各色次数由原版分配，可以为零，不能等同于实际非零目标颜色数。新版“每个选中颜色至少投一个”的额外规则已经删除。

### 位置分布

来源：[position_distribution.json](../src/robomme_icl/configs/position_distribution.json)。坐标与距离单位为米，角度为度。

| 配置键／对象 | 当前固定值 |
| --- | --- |
| 全局 | `schema_version=2`；`compiler_seed=20260908`；`sampling="stratified"`；`max_candidates=1024`；`safety_clearance=0.005` |
| `table_bounds` | x、y 均为 `[-0.6,0.6]`，用于候选布局边界 |
| BinFill button | x `[-0.25,-0.15]`；y `[-0.2,0.2]` |
| BinFill board | x `[-0.05,0.15]`；y `[-0.2,0.2]`；yaw `[-20,20]` |
| BinFill cubes | x `[-0.3,0.1]`；y `[-0.25,0.25]`；yaw `[0,360]` |
| RouteStick | `center=[-0.1,0]`；`spacing=0.07`；yaw `[-30,30]`；这里只改变布局，不定义标记半径或形状 |
| 三物体拓扑候选 | `triangle`、`line` |
| triangle 锚点 | `[[-0.05,-0.1],[-0.05,0.1],[0.1,0]]` |
| line 锚点 | `[[0,-0.15],[0,0.15],[0,0]]` |
| rectangle 锚点 | `[[-0.05,-0.1],[-0.05,0.1],[0.1,0.1],[0.1,-0.1]]` |
| video_layouts | `window_half_size=0.07`；整体 yaw `[0,180]`；容器 yaw `[0,90]`；方块 yaw `[0,360]` |
| VideoRepick button | x `[-0.25,-0.15]`；y `[-0.05,0.05]` |
| VideoRepick hard_cubes | x `[-0.3,0.1]`；y `[-0.25,0.25]`；yaw `[0,360]` |

[sampling/positions.py](../src/robomme_icl/sampling/positions.py) 保存分层分位数；[NativePlacements](../src/robomme_icl/native/parameters.py) 读取原版真实碰撞形状，解析物体能放入窗口的中心范围，并同时更新原版 `initial_pose` 和实际位姿。`safety_clearance` 只用于初始候选筛选，不作为运行时任务失败条件。

`geometry.*`、`schedule.*` 已从位置配置删除。尺寸、材质、局部坐标、碰撞组件、显隐及交换时序不再是新版可修改配置；真实结果作为记录快照保存。角色、目标顺序和最近邻交换选择交给原版。

## 清单二：沿用原版的逻辑与检查范围

### 已落实的复用关系

| 新版入口 | 原版父类及复用机制 | 本次证据边界 |
| --- | --- | --- |
| [ICLBinFill](../src/robomme_icl/envs/bin_fill.py) | 原版 `BinFill`；复用孔板、黑孔底、按钮、方块构建及 `_initialize_episode()`，逐色动态显隐、投入计数、移至 `[10,10,0]`、按钮结束 | 源码检查通过；12 局中的 easy/hard 自身重复运行通过；medium 布局失败 |
| [ICLRouteStick](../src/robomme_icl/envs/route_stick.py) | 原版 `RouteStick`；九个灰白圆标记、四个彩色障碍，示范／正式绕行、收棒、强制复位、恢复起点、棒端轨迹、高亮和错误方向判定 | 源码检查通过；12 局中 easy 自身重复运行通过，medium 超时，hard 未执行 |
| [ICLVideoUnmaskSwap](../src/robomme_icl/envs/video_unmask_swap.py) | 原版 `VideoUnmaskSwap`；全部容器组件、藏块映射，继承 `_refresh_swap_schedule()`、`step()`，最近邻交换、两轨道及旁观物体处理 | 源码检查通过；此前 easy 单局运行通过；本次 12 局未执行该任务 |
| [ICLVideoRepick](../src/robomme_icl/envs/video_repick.py) | 原版 `VideoRepick`；复用 `_initialize_episode()`、`step()`，原版颜色规则、演示抓放、等待、复位、`specialflag=="swap"` 触发及正式重复抓放／按钮结束 | 源码检查通过；此前 easy 单局运行通过；本次 12 局未执行该任务 |

源码验证入口：[test_native_source.py](../tests/robomme_icl/test_native_source.py)。四任务 `step`、`evaluate`、`_initialize_episode`、`_refresh_swap_schedule` 中存在的方法与固定原版 AST 一致；含 `func/solve/name` 的 subgoal 字典 AST 多重集合一致；六份共用工具文件逐字节一致。**字典集合相同不能单独证明运行时 subgoal 顺序、触发步和事件都相同。**

执行使用原版 `DemonstrationWrapper`、`task_list[*]["solve"]` 及规划重试／回退。[execution/recording.py](../src/robomme_icl/execution/recording.py) 记录原版执行，不额外调用 `evaluate()` 获取信息；`NO RECORD` 仍真实执行，只有交付帧过滤。原版内部终止额外一步保留完整记录。旧独立 `TaskEvaluator`、Oracle 四任务动作分支及交换动画已删除。

### 具体判定与事件检查

下表属于源码／定向测试已检查的规则，不等于四任务全分支真实仿真已经验收。

| 检查项 | 沿用原版的口径 | 验证方式 |
| --- | --- | --- |
| 抓起容器 | `is_bin_pickup` 检查 z 大于 `0.15`，不额外增加 grasp 条件 | [test_native_subgoals.py](../tests/robomme_icl/test_native_subgoals.py) 调用原版函数 |
| 放下判定 | 沿用 `use_demonstrationwrapper` 控制的分支；对应阈值 `0.035`，另一分支 `0.2` 并检查 tcp 距离 `>0.05`，不重新解释为当前是否处于演示阶段 | 同上，保留原版语义 |
| BinFill 投入及消失 | 孔板中心距离 `<=0.05`，结合原版放下／夹爪条件；成功后计数并移至 `[10,10,0]` | 同上，函数级计数／位置检查 |
| 按钮结束 | 按压深度 `>0.005` | 同上，原版阈值边界检查 |
| Unmask 显隐与交换 | 容器返回窗口 `0..64` 中点 `32`；交换开始 `64`；藏块按原版交换窗口隐藏／返回 | 同上及源码 AST 检查；全轨迹边界事件尚未独立对照 |
| 规划失败 | 保留原版三次 screw 与三次 RRT 回退流程 | 定向测试；所有真实错误动作分支尚未对照 |
| 素材与记录检查器 | 比较 visual/collision 组件、尺寸、位姿、材质、状态、任务清单、传感器及事件；人为缺组件、改 subgoal、事件错步等负例必须失败 | [test_native_assets.py](../tests/robomme_icl/test_native_assets.py)、[test_parity_checker.py](../tests/robomme_icl/test_parity_checker.py)；检查器通过不等于被检查的所有任务通过 |

### 已有历史证据及限制

- BinFill 原版提取前后：seed 0 的 26 个对象／链接及双相机 RGB 逐位相同。证据位于 `artifacts/generated/robomme-icl/native-parity/baseline-original-binfill-v3/` 和 `extracted-original-binfill/`。只覆盖这一初态。
- 此前四任务 easy 独立 smoke 通过：BinFill `481` 操作／`470` 物理步；RouteStick `641/622`；VideoUnmaskSwap `292/287`；VideoRepick `894/867`，总耗时 `33.82 s`。它们不是此次 12 局的四个 easy 槽，也不构成原版逐帧对照。
- 中间版本有 BinFill 新旧完整操作对照通过，报告为 `artifacts/reports/robomme-icl/native-parity/binfill-parity-v2.json`。它早于最后一次观察器修正，不能作为当前提交的最终认证。
- 全仓轻量测试此前为 `203 passed, 4 failed, 2 skipped`；4 项失败已在固定原版快照复现，日志为 `artifacts/reports/robomme-icl/native-parity/baseline-known-failures.log`。不能报告为全仓测试全部通过。
- 收尾执行 `command -v uv` 后运行 `uv run --no-sync python -m pytest tests/robomme_icl/ -q`，结果为 **189 passed、8 skipped，35.07 s，退出码 0**。包括打包状态完整 HDF5 写入／摘要校验／读取测试；8 项跳过是需显式开启的真实 smoke 和套件 reset，本次没有追加仿真。

## 这次 12 局的实际结果

| 任务 | 难度 | seed | 实际结果 |
| --- | --- | --- | --- |
| BinFill | easy | 2000000000 | 候选 1，两遍均完成，481 个记录操作；自身逐位重复认证通过 |
| BinFill | medium | 2000000001 | 32 个候选全部因初始几何净距／碰撞拒绝；无完整轨迹 |
| BinFill | hard | 2000000002 | 候选 22，两遍均完成，674 个记录操作；自身逐位重复认证通过 |
| RouteStick | easy | 2000000003 | 候选 0，两遍均完成，653 个记录操作；自身逐位重复认证通过 |
| RouteStick | medium | 2000000004 | 子进程达到 180 秒超时；留下一份无法完整读取的 HDF5，不能计为通过 |
| RouteStick | hard | 2000000005 | 未执行 |
| VideoUnmaskSwap | easy | 2000000006 | 未执行 |
| VideoUnmaskSwap | medium | 2000000007 | 未执行 |
| VideoUnmaskSwap | hard | 2000000008 | 未执行 |
| VideoRepick | easy | 2000000009 | 未执行 |
| VideoRepick | medium | 2000000010 | 未执行 |
| VideoRepick | hard | 2000000011 | 未执行 |

合计：**3 局自身复现通过、1 局布局失败、1 局超时未完成、7 局未执行。** 批次在 prepare 阶段退出，`EXIT_CODE=1`，没有发布 `suite/suite.json`。后续独立原版对照、正式生成、回放、连续 reset 和错误动作对照均未开始。操作数包含显式求值与边界标记，不等于物理步数或交付视频帧数。

运行会话 `eval-native-parity-smoke-12` 已退出。原始日志：[smoke-12.log](../artifacts/reports/robomme-icl/native-parity/smoke-12.log)；槽位与拒绝原因：[prepare_state.json](../artifacts/generated/robomme-icl/native-parity/smoke-12/suite/prepare_state.json)。HDF5 保存在同目录的 `certification/<task>/<difficulty>/0/candidate_XXXX/` 下，失败文件保留，不覆盖旧数据。

启动基线 `6010daa58da05591e045b78ea62f195a95287877`；`uv.lock` SHA-256 为 `983de83f7b22c98b96c3c25a39958b4f5920e3232cfaa209c89542ef5639ac03`；本机 `/data` NVMe/ext4，GPU 0/1 均为 RTX 6000 Ada，4 workers。失败阶段的实际命令如下，供追溯，**本次不重跑**：

```bash
command -v uv
uv run --no-sync scripts/prepare_suite.py \
  --episodes-per-task 3 --workers 4 --gpus 0,1 \
  --max-candidates 32 --timeout-seconds 180 \
  --output-dir artifacts/generated/robomme-icl/native-parity/smoke-12
```

这里的 `32` 是本次命令覆盖，不是 JSON 默认的 `1024`。当前证据只说明这 32 个候选失败，不能推断 1024 个候选也必然失败。

## 未通过的原因与交付边界

1. **密集布局筛选效率不足。** 当前布局注入没有完整利用原版逐对象避让，整场景的净距筛选导致 BinFill medium 连续 32 次被拒绝。本次没有放宽 `0.005 m` 筛选，也没有为通过而改原版素材。
2. **RouteStick 状态记录过重。** easy 的构建加执行为 `17.64 s`，HDF5 写入为 `131.44 s`，逐位认证为 `262.20 s`。轨迹对象累积令状态树庞大；medium 存在超时和不完整文件。保留原版对象生命周期，不能通过删除原版对象或少记动作伪造通过。
3. **收尾仅增加状态树无损打包。** [io/packed.py](../src/robomme_icl/io/packed.py) 与 [io/hdf5.py](../src/robomme_icl/io/hdf5.py) 将 `native_state` 保存为类型化数据块，读回还原类型、dtype、shape 和数组字节，减少小 HDF5 节点。该修改晚于 12 局运行，未重新跑仿真；不得声称已解决真实超时或有已测得的性能提升。旧记录仍可读取。

源码继承和函数级检查已提供证据；**四任务全部素材、subgoal 顺序、事件边界、错误操作及新旧逐帧图像一致，仍未验证完成。** 本报告按现有记录收尾，不把未执行项目标为通过，不启动 96 局。
