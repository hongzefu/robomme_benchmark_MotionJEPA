# newtask-v2 重建方案：从 10.0 开始，仅显式控制原版采样输入

状态：**方案已按最新要求改为两个生成侧 Python 文件直接平铺在 `scripts/`；原版配置快照已提取，尚未执行迁移、清理、重建或生成。**

本方案依据 2026-09-08 对本地源码和 Git 引用的只读核查。任务范围已经用户确认：`BinFill`、`RouteStick`、`VideoUnmaskSwap`、`VideoRepick`。

用户最新确定：生成侧只保留 `generate_dataset_newseed.py` 和 `seed_layout.py`，将实际需要的函数及依赖并入这两个文件，移到 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/`，与原有 `dataset_replay.py`、`evaluation.py`、`run_example.py` 平铺。`data-generation-newSeed/` 不作为最终目录保留。本轮只修改方案和账本，原版配置快照保持原样，见 [native_sampling.json](scripts/configs/newtask-v2/native_sampling.json)。

## 一、目标与版本边界

从 `dataset-gen-NewSeed` 重新建立 `newtask-v2`，首个实现提交为 `10.0 <中文描述>`，后续常规实现从 `10.1` 接续。`10.0` 指此次重建的 Git 版本序列，不修改当前 Python 包的 `0.1.0` 版本。

本次唯一目标是：**把四个原任务已经使用的位置分布和参数候选提取出来，成为显式传入的配置；初始配置值、采样方式和完整执行链均保持原版行为。** “固定候选”是固定可以抽取哪些值及其原有抽法，每个 episode 仍由原 seed 在原位置抽样；不是把每局结果固定成一个值。“显式控制”是可检查、可传入这些输入，不增加界面或新的生成流程。

| 项目 | 已核对的基线与处理方式 |
| --- | --- |
| 用户所说的源分支 | 实际大小写为 `dataset-gen-NewSeed` |
| 固定源码基线 | `94449db0a068a6b454b55a13ebd48f0394d89cc8`，当前提交标题为 `2.20 忽略根目录 artifacts 产物` |
| 本地远端跟踪引用 | 核查时 `origin/dataset-gen-NewSeed` 与上述提交相同；本轮没有联网刷新远端，不能据此声称远端服务器未发生变化 |
| 旧版参考 | `newtask-v1` / `origin/newtask-v1` 为 `be7a59db07ffd50011576dda9c432f81903e031b`；只读参考，不合并其实现 |
| 重建方式 | 后续从固定源码基线创建全新的 `newtask-v2`；不从 `newtask-v1` 接续，不覆盖已有分支 |
| 本轮允许修改 | 根目录本方案和 `AGENTS.md` 账本；先前提取的 JSON 不变；沿当前基线提交版本接续，不占用目标分支的首个 `10.0` 实现版本 |

本轮不创建或切换分支、不修改运行源码或原任务取值、不运行生成、回放或仿真。新增 JSON 尚未接入运行，不改变当前生成器行为。下面的文件名、接口和命令凡标为“拟新增”均尚未实现。

## 二、原版实际调用链

固定基线的原入口是 [generate_dataset_newseed.py](scripts/data-generation-newSeed/generate_dataset_newseed.py)，后续直接迁到 `scripts/generate_dataset_newseed.py`。它直接使用 `RobommeRecordWrapper`。模块导入了其他 wrapper，不代表生成过程中实例化了它们。下图函数顺序不因文件位置改变；共享的必要函数并入两个保留文件，具体分配见第七节。

下面按执行顺序画出 ASCII 调用图；缩进内是被调用方，返回后继续向下。

```text
generate_dataset_newseed.py::main()
  |
  +--> _args()
  |
  +--> generate_dataset_newseed()
         |
         +--> parse_tasks() + seed_layout.get_layout()
         |      +--> difficulty_for(episode, cycle)
         |      +--> SeedLayout.seed(task, episode, attempt=0)
         |      `--> EpisodeJob
         |
         +--> _run_jobs()
         |      |
         |      +--> 每张 GPU 一个 spawn 进程池
         |      |      `--> _pool_init()：原有绑卡、线程与导入顺序
         |      |
         |      `--> _worker(job)                         每次 attempt
         |             |
         |             +--> _planner_classes()           定义原有规划器子类
         |             |
         |             +--> gym.make(job.task, **kwargs)
         |             |      `--> 原任务类 __init__()
         |             |             +--> 原难度解析、参数抽样、随机流初始化
         |             |             `--> BaseEnv.__init__()
         |             |                    `--> 内部 reset(reconfigure=True)
         |             |                           +--> _reconfigure()
         |             |                           |      `--> 原任务 _load_scene()
         |             |                           |             +--> 原对象生成工具
         |             |                           |             `--> RouteStick / VideoUnmaskSwap 构造 task_list
         |             |                           `--> 原任务 _initialize_episode()
         |             |                                  `--> BinFill / VideoRepick 构造 task_list
         |             |
         |             +--> RobommeRecordWrapper(base_env, ...)
         |             |      `--> use_demonstrationwrapper = False
         |             |
         |             +--> record_env.reset()
         |             |      +--> 原环境 reset / _initialize_episode()
         |             |      `--> 原记录器 _init_fk_planner()
         |             |
         |             +--> 实例化原规划器
         |             |      +--> RouteStick：NoPatchStick，joint_vel_limits=0.3
         |             |      `--> 其余三任务：NoPatchArm
         |             |
         |             +--> _execute_tasks(record_env, planner, torch, job)
         |             |      +--> 按原 task_list 顺序逐项执行
         |             |             +--> evaluate(solve_complete_eval=True)
         |             |             +--> entry["solve"](record_env, planner)
         |             |             |      `--> 原 subgoal_planner_func / reset_panda
         |             |             |             `--> planner 原规划与动作执行
         |             |             |                    `--> record_env.step(action)
         |             |             |                           +--> 原任务 step()
         |             |             |                           |      `--> BaseEnv.step()
         |             |             |                           |          原物理、求值与观察
         |             |             |                           `--> 原记录与完成标志
         |             |             `--> evaluate(solve_complete_eval=True)
         |             |                    `--> 原 success / fail 判定
         |             |      `--> 若循环结束且未提前返回，再 evaluate 一次检查 success
         |             |
         |             +--> finally: record_env.close()
         |             |      `--> 原 HDF5 写入与视频编码
         |             |
         |             `--> 按原 caught 分支返回
         |                    +--> 已捕获异常：_discard_empty_h5() -> 返回失败
         |                    `--> 无异常：_raw_summary() 检查轨迹末帧契约
         |                           +--> 通过：返回成功
         |                           `--> 异常：_discard_empty_h5() -> 返回失败
         |
         +--> 父进程沿用原重试规则
         |      +--> 成功：收集结果
         |      `--> 允许重试：attempt+1 -> 原 seed 公式 -> 再次 _worker()
         |
         `--> _write_metadata() + run_summary.json

基线生成结束后，按需另行调用 merge_episode_h5.py::merge_task()
  `--> 原 record_dataset_<Task>.h5
```

上图末尾是原版已有的独立合并调用。后续只将合并函数迁入平铺主文件，由拟新增 `--merge-only` 模式显式调用；不改变原生成过程，不自动追加合并步骤。

`BaseEnv` 内部构造时 reset 的顺序已通过当前安装源码 `mani_skill/envs/sapien_env.py` 的 `BaseEnv.__init__`、`_reconfigure`、`reset` 核对。后续需同时固定依赖锁和运行环境。构造时的内部 reset 与外层 `record_env.reset()` 都保留，不合并，不额外插入 reset。

`_planner_classes()` 中的 screw 三次、随后 RRTStar 三次回退保持原样。任务自己的 `step()` 中，在 `super().step()` 前后发生的交换、显隐等操作也保持原位置；图中没有把这些事件迁移进 `BaseEnv`。

## 三、新版只增加一条配置输入支路

拟新增一个 `--sampling-config` 参数，加载一份含 `positions` 和 `parameters` 两块内容的 JSON。配置加载只检查和复制数据，不采样、不创建环境、不执行物理。

```text
已提取 scripts/configs/newtask-v2/native_sampling.json
  |
  +--> parameters：四任务原有难度参数、候选与抽取规则
  `--> positions ：四任务原有位置范围、锚点与旋转范围
          |
          v
平铺后的 scripts/generate_dataset_newseed.py
  `--> 原 main() -> 原 generate_dataset_newseed()
                 |
                 +--> 拟新增 load_sampling_config()      只读、校验、零随机数
                 |      `--> 通过 EpisodeJob 传递已解析的任务配置
                 |
                 `--> 原 _run_jobs() -> 原 _worker()
                                         |
                                         `--> 原 gym.make(task, ...,
                                               sampling_config=任务配置)
                                                  |
                                                  v
                                          原任务 __init__()
                                                  |
                            +---------------------+---------------------+
                            |                                           |
                            v                                           v
                   原参数抽样表达式                              原 _load_scene()
                   只替换候选/区间的来源                         只替换位置输入来源
                            |                                           |
                            +---------------------+---------------------+
                                                  |
                                                  v
                           原对象生成、task_list、reset、solve、step、记录
```

具体改法限定如下：

1. 在四个原任务的 `__init__()` 中接收并取走 `sampling_config`，在首次参数抽样及 `super().__init__()` 之前准备实例专属配置，不能把新参数漏传给 `BaseEnv`。保留原类、原注册 ID 和原方法，不新增 ICL 子类或环境包装层。
2. 原 `configs` 中的整数区间仍交给原来的 `torch.randint(low, high + 1, ...)`；固定整数仍直接取值。不得把所有参数统一改成新的 `choice()` 抽样器。
3. 原 `torch.rand()` 表达式只替换字面常量来源，保留乘法、加减法和类型转换顺序。比如 BinFill 板位置仍按 `0.15 + (u * 0.2 - 0.2)` 计算，不改写为看似等价的 `-0.05 + u * 0.2`。
4. 位置参数仍传给原来的 `build_button`、`spawn_random_cube`、`spawn_random_bin`、`rotate_points_random`。若工具内部的旋转常量需要显式化，只增加可选参数且保持旧调用默认值和原运算顺序；不替换工具、不事后移动已经生成的物体。
5. 不传配置时走原默认值。显式传入时必须校验完整性、字段、类型、单位和原区间表达形式；未知字段或缺失字段直接报错。默认值与冻结快照通过对照检查防止漂移，不在运行时悄悄导出或刷新快照。
6. 父进程读取一次配置，再把解析结果传给 worker；每个环境得到独立副本，不能修改类级共享 `configs`，不能影响同一进程的下一局。额外配置可作为运行目录中的独立 JSON 快照保存，原 HDF5、原 metadata 结构不改。
7. 配置读取、校验、提取和原子写入函数全部并入 `scripts/generate_dataset_newseed.py`，相关函数只使用标准库。四个 task 接收已校验的字典，在构造函数中取实例副本，不反向导入生成脚本。父进程不能为提取配置导入 `robomme_env`，否则会提前加载 task、`torch` 和 `sapien`，破坏原 `_pool_init()` 先绑卡再导入的顺序。

“位置分布”包含原锚点、偏移窗口和位置／旋转抽样输入。物体尺寸、材质、碰撞几何、相机、速度、交换时序、失败恢复和成功阈值属于原实现，不加入此次可改配置。原有碰撞避让和重试仍决定最终位置分布，不能改成整场景筛选、分层采样或预先求好位置。

## 四、从当前四个 task 读出的参数候选

下表中 `{...}` 是为了便于人读而展开的候选集合，不意味着运行时改用集合采样。配置需保留源码的表示方式：`[min,max]` 区间、`*_min`/`*_max` 字段、固定值和原抽取方式。整数区间均包含两个端点。

| 任务 | 难度 | 基线原字段与候选 |
| --- | --- | --- |
| BinFill | easy | `color=1`；`spawn_cubes=[4,6]` -> `{4,5,6}`；`put_in_color=[1,1]`；`put_in_numbers=[1,3]` -> `{1,2,3}` |
| BinFill | medium | `color=2`；`spawn_cubes=[8,10]` -> `{8,9,10}`；`put_in_color=[1,2]`；`put_in_numbers=[2,4]` -> `{2,3,4}` |
| BinFill | hard | `color=3`；`spawn_cubes=[10,12]` -> `{10,11,12}`；`put_in_color=[2,3]`；`put_in_numbers=[3,5]` -> `{3,4,5}` |
| RouteStick | easy | `length=[2,3]`；`backtrack=False` |
| RouteStick | medium | `length=[4,5]`；`backtrack=False` |
| RouteStick | hard | `length=[4,7]` -> `{4,5,6,7}`；`backtrack=True` |
| VideoUnmaskSwap | easy | `bin=3`；`swap_min=1, swap_max=2`；`pick_min=1, pick_max=2` |
| VideoUnmaskSwap | medium | `bin=4`；`swap_min=1, swap_max=2`；`pick_min=1, pick_max=1` |
| VideoUnmaskSwap | hard | `bin=4`；`swap_min=2, swap_max=3`；`pick_min=2, pick_max=2` |
| VideoRepick | easy | `cube=3`；`swap_min=1, swap_max=2`；`num_repeats` 来自 `randint(1,4)` -> `{1,2,3}` |
| VideoRepick | medium | `cube=3`；`swap_min=2, swap_max=3`；`num_repeats={1,2,3}`，保留相同抽样表达式 |
| VideoRepick | hard | `cluster=True`、`swap=None`、`swap_min=0, swap_max=0`；`num_repeats={1,2,3}`；原 `range(5)` 每轮红蓝绿各一块，总计 15 块 |

另有以下固定口径必须一起提取或记录，不能用旧版同名字段代替：

- `BinFill.dynamic` 在 `__init__()` 用 `bool(torch.randint(0,2,...).item())` 抽取，候选为 `False/True`。它先于场景抽样。目标颜色池的颜色允许分配到零次投入；原有逐色投入数和生成数分配逻辑继续执行。
- `RouteStick.length` 是 `generate_dynamic_walk()` 的步数，结果包含起点，共 `steps+1` 个节点，不等同于转角数量。原路线候选节点顺序为 `[0,2,4,6,8]`，障碍索引为 `[1,3,5,7]`；这些布局结构保持原样。
- `RouteStick.swing_directions` 对每段依次执行 `torch.rand(1,...).item() < 0.5`，真时为 `clockwise`，否则为 `counterclockwise`。快照记录这一原方向候选与阈值，不改用 `randint` 或 `choice`。
- `VideoRepick` hard 的“15 块”是五轮原循环的结果；不能改成抽取 `spawn_count=[15]` 后统一生成 15 块，这会改变颜色排列与随机流。原颜色候选顺序为红、蓝、绿；easy/medium 仍保留原 `cube_colors` 长度为 4 的打乱操作，即使最后只生成 3 块。
- `VideoUnmaskSwap` 的颜色顺序为红、绿、蓝，藏块容器索引仍使用原 `randperm(3)`；BinFill 的生成颜色顺序与 `_initialize_episode()` 中的蓝、红、绿任务颜色顺序分别保留。VideoRepick hard 由难度分支进入，不能把原 `cluster` 字段重新解释成运行开关。
- 颜色、目标角色、目标顺序、最近邻交换对等继续由各 task 的原逻辑决定。它们可出现在来源清单中，但本轮不增加新的任务组合枚举器。

来源锚点：四个任务文件的 `config_easy`、`config_medium`、`config_hard`、`__init__`、`_load_scene`，以及 [route.py](src/robomme/robomme_env/utils/route.py) 的 `generate_dynamic_walk`。

## 五、从当前 task 读出的位置分布

坐标单位为米。表中的连续区间按采样输入范围表示；`torch.rand` 的上界不包含在内。最终合法位置还要经过原对象尺寸收缩和原碰撞拒绝采样，不能把外框误当物体中心的最终均匀分布。

| 任务／对象 | 原位置与旋转输入 | 原消费位置 |
| --- | --- | --- |
| BinFill 按钮 | `center_xy=(-0.2,0)`；`randomize_range=(0.1,0.4)`；对应 x `[-0.25,-0.15)`、y `[-0.2,0.2)` | `_load_scene -> build_button`，`torch.rand(2)-0.5` |
| BinFill 孔板 | x 按 `0.15+(u*0.2-0.2)`，范围 `[-0.05,0.15)`；y `u*0.4-0.2`；yaw `u*40-20` 度 | `_load_scene -> build_board_with_hole`，先 x、再 y、再 yaw |
| BinFill 方块 | `region_center=[-0.1,0]`；`region_half_size=[0.2,0.25]`；yaw `[0,2*pi)` 弧度 | `_load_scene -> spawn_random_cube` |
| RouteStick 标记与障碍布局 | 原布局为 `1 x 9`；中心 `[-0.1,0]`；x/y 间距各 `0.07`；角度 `u*60-30` 度后转弧度；各点绕世界原点旋转 | `_load_scene` 的 `grid_center`、`grid_spacing_x/y`、`theta` 和原对象构建 |
| VideoUnmaskSwap 容器布局 | 三角／直线三点候选或固定矩形四点；整体旋转参数 `(0,180)` **弧度**；每个锚点的 `region_half_size=0.07` | `_load_scene -> rotate_points_random -> spawn_random_bin` |
| VideoUnmaskSwap 容器自身 yaw | `[0,90)` 度；只在位置通过避让检测后抽取 | `spawn_random_bin -> build_bin` |
| VideoUnmaskSwap 藏块 | 从对应容器位姿派生，保持原来的局部偏移与姿态 | `_load_scene` 的藏块构造；不另加独立布局采样 |
| VideoRepick 按钮 | `center_xy=(-0.2,0)`；`randomize_range=(0.1,0.1)`；对应 x `[-0.25,-0.15)`、y `[-0.05,0.05)` | `_load_scene -> build_button` |
| VideoRepick easy/medium 方块 | 原三角／直线锚点；整体旋转 `(0,180)` **弧度**；`region_half_size=0.07`；方块自身 yaw `[0,2*pi)` 弧度 | `_load_scene -> rotate_points_random -> spawn_random_cube` |
| VideoRepick hard 方块 | `region_center=[-0.1,0]`；`region_half_size=[0.2,0.25]`；yaw `[0,2*pi)` 弧度 | `_load_scene` 的五轮原生成循环 |

两个 Video task 当前定义的锚点按原顺序固定如下，不排序、不归一化、不平移：

```text
region3_tri  = [[-0.05,-0.1], [-0.05,0.1], [0.1,0]]
region3_line = [[0,-0.15], [0,0.15], [0,0]]
region4      = [[-0.05,-0.1], [-0.05,0.1], [0.1,0.1], [0.1,-0.1]]
```

位置实现来源：[object_generation.py](src/robomme/robomme_env/utils/object_generation.py) 的 `build_button`、`spawn_random_cube`、`spawn_random_bin`；[statechange.py](src/robomme/robomme_env/utils/statechange.py) 的 `rotate_points_random`。

方块中心区间由 `center - area_half + hs_new` 到 `center + area_half - hs_new` 计算；容器使用同形式的 `bin_half_size` 收缩。原 `avoid` 顺序、`min_gap`、`max_trials=256`、`include_existing`、`include_goal` 和失败处理全部保留，不把这些判据改成位置配置的全局安全距离。

## 六、保持原版行为的具体约束

1. **随机流及生命周期不变。** BinFill 与 VideoRepick 使用 `self.generator` 继续抽样；VideoUnmaskSwap 的构造函数与 `_load_scene()` 各自创建同 seed 的 generator；RouteStick 在 `_load_scene()` 重新创建 generator。不得合并成全局随机流或新增配置编译 seed。
2. **固定候选也照原方式消费随机数。** `randint(1,2)`、`randint(2,3)`、`randint(0,1)` 虽只可能返回一个值，仍照常调用。不能优化成常量赋值。VideoUnmaskSwap 即使最终使用四容器，也保留此前的 `region3_choice` 抽样。
3. **原版实际语义优先于注释。** `(0,180)` 不修成角度或 `[0,pi)`；BinFill 孔板位置按公式提取；RouteStick 按实际 `1 x 9` 和绕世界原点旋转记录。发现疑似旧错误只说明，不顺手修复。
4. **执行期没有第二套逻辑。** 原 `task_list` 的 `func/solve/name`、示范与正式阶段、`NO RECORD`、求值次数、事件触发步、动作、失败恢复和记录策略保持不变。不得为比较方便新增 `evaluate()` 调用，它可能推进任务状态。
5. **原 seed 与难度调度不变。** 保留 `offset + env_code*env_block + episode*100 + attempt`、原难度循环默认 `211`、原 attempt 重试及失败分类。任务编号仍来自 16 任务规范序：四任务分别为 BinFill `4`、RouteStick `16`、VideoUnmaskSwap `5`、VideoRepick `9`，不能压缩成 1 到 4。其他 12 个任务不增加配置接入。
6. **原布局失败处理不变。** 不把逐物体避让替换成整场景重新采样；也不统一任务内部不同的 `break`、跳过和 `SceneGenerationError` 行为。首次同 seed 对照必须记录失败 attempt，不能只比较重试后成功的两条轨迹。

## 七、最终平铺结构、两文件分工与清理范围

生成侧 Python 只保留两个文件，直接放在根目录 `scripts/`；加上用户此前指定保留的三个原脚本，最终此目录中的产品 Python 文件恰为以下五个：

```text
scripts/
  |
  +-- dataset_replay.py               原有回放脚本，保留
  +-- evaluation.py                   原有评估示例，保留
  +-- run_example.py                  原有运行示例，保留
  |
  +-- generate_dataset_newseed.py     从原子目录迁出；生成、配置提取、按需合并
  +-- seed_layout.py                  从原子目录迁出；原 seed/难度与任务规范
  |
  `-- configs/newtask-v2/
        `-- native_sampling.json      已提取的原值 JSON，不是 Python 文件
```

本轮只改计划，上面的迁移与清理均未执行。保留原文件名，取消此前独立的 `extract_native_config.py`、`generate_dataset.py`、`merge_dataset.py` 和 `src/robomme/sampling_config.py` 设计，不将辅助代码移到另一个新 Python 文件里。`src/robomme` 中原任务、规划器、wrapper 和测试目录不受“五个产品脚本”的数量约束。

### 两个文件的完整职责

| 最终文件 | 保留或迁入的内容 | 明确的依赖方向 |
| --- | --- | --- |
| `scripts/seed_layout.py` | 保留 `SeedLayout`、`LAYOUTS`、`env_code`、`get_layout`、`parse_difficulty_ratio`、`difficulty_for`、`plan_episodes`；从旧 validator 迁入 `ALL_TASKS`、`MAX_EPISODES`、`DatasetContractError`、`parse_tasks` | 仅依赖标准库；不导入主生成器、HDF5、NumPy 或仿真包 |
| `scripts/generate_dataset_newseed.py` | 保留原 `EpisodeJob`、worker/进程池、规划回退、任务执行、metadata 与摘要；迁入下表的轨迹检查、原子写入和最小合并函数；新增同文件内的配置提取与校验 | 单向导入同级 `seed_layout`；保留原 NumPy/HDF5 导入与线程设置顺序；仿真包仍在绑卡后由原 worker 路径导入 |

`ALL_TASKS` 必须保留原 16 任务顺序，`MAX_EPISODES=100`、`MAX_ATTEMPTS=100`、`EPISODE_STRIDE=100` 和原难度循环均不变。只配置四任务不等于把规范序缩成四项；错误类型、任务排序和非法输入判定也照原函数保留。

| 旧来源 | 实际需要的内容 | 后续落点与处理 |
| --- | --- | --- |
| `data-generation/validate_generated_dataset_contract.py` | `ALL_TASKS`、`MAX_EPISODES`、`DatasetContractError`、`parse_tasks` | 迁入 `seed_layout.py`；主生成器从它导入 |
| 同一旧 validator | `TIMESTEP_RE`、`timestep_indices`、`inspect_episode_terminal` 及其 `re`、`h5py`、`numpy` 依赖 | 迁入主生成器，保持连续 timestep、`setup` 排除及末帧严格布尔完成检查 |
| `data-generation/write_generation_report.py` | `write_text_atomic` 及 `Path` | 只迁入这个函数到主生成器；不搬完整报告器，解除其顶层 `compare_joint_actions` 导入 |
| `data-generation-newSeed/merge_episode_h5.py` | `MergeError`、`_sources`、`merge_task` | 并入主生成器的 `--merge-only` 分支；保留按 metadata 找源文件、临时 HDF5 与原子替换，不另保留合并脚本 |
| 原计划的配置辅助模块 | 纯源码提取、JSON 读取／校验、实例输入准备 | 实现在主生成器中；配置分支不导入环境，不采样；原四个 task 仅接收字典并取副本 |

原 `METADATA_ROOT`、完整官方数据审计／报告流程及历史 metadata 追加功能不属于这两个保留脚本的运行依赖，不因旧模块曾包含它们而整包迁入。可选合并仍在生成之后独立执行，默认不自动合并，不删除逐 episode 源文件。

### 同一个主文件提供三种入口模式

```text
scripts/generate_dataset_newseed.py::main()
  |
  +-- --extract-config <JSON>
  |      `--> 读取固定源码 -> AST 原值提取 -> 检查或写出配置 -> 返回
  |
  +-- --merge-only
  |      `--> 原 _sources() -> 原 merge_task() -> 返回
  |
  `-- 常规生成（不指定上述模式）
         `--> 原 generate_dataset_newseed()
                +--> 同级 seed_layout.py
                `--> 原 _run_jobs / _worker / gym.make / reset / solve / close
```

`--extract-config` 与 `--merge-only` 互斥；配置提取不要求生成用的 `--output-dir`、GPU 或 worker 参数。常规生成保留旧参数及默认值，仅增加 `--sampling-config`；合并需要 `--input-dir` 和明确输出目录。配置提取支持 `--source-ref` 与只检查不写入的 `--check-config`。分流放在启动进程池和环境导入之前，不把提取或合并塞进每个 worker。

当前 [native_sampling.json](scripts/configs/newtask-v2/native_sampling.json) 已包含四任务全部 12 份难度字典、额外构造参数、位置输入、原始锚点、单位和七份来源 SHA-256。`parameters`、`positions` 是后续显式输入；`native_semantics` 仅记录原语义；表达式字符串只作核查，不执行 `eval`。后续同文件提取分支必须可重复导出相同原值。

### 平铺时必须调整的位置

1. 主文件从子目录移到 `scripts/` 后，`SCRIPT_DIR` 指向根 `scripts/`，`REPO_ROOT` 应由原 `SCRIPT_DIR.parents[1]` 改为 `SCRIPT_DIR.parent`；`SRC_ROOT = REPO_ROOT / "src"` 继续指向当前仓库源码。
2. 删除两文件的 `CONTRACT_DIR` 和旧 `data-generation` 路径插入，改为同级模块导入。不能保留指向已删除目录的兼容分支，也不能让缓存模块遮掩缺失依赖。
3. `spawn` 继续从主生成器模块解析 `EpisodeJob`、`_worker`、`_pool_init`；入口保持 `if __name__ == "__main__"` 保护。主生成器只导入 seed 模块，seed 模块不反向导入。
4. 四个 task 不导入 `scripts` 或主生成器。父进程检查配置后经 `EpisodeJob` 传普通字典，task 在原构造位置通过标准库复制为实例配置。
5. 原线程环境设置继续早于 NumPy 导入；绑卡继续早于 Torch/SAPIEN 导入。配置提取使用固定源码的 AST，不通过导入全部 task 读取默认值。

### 后续清理清单及顺序

| 现有路径 | 计划处理 |
| --- | --- |
| `scripts/data-generation-newSeed/` | 迁出两个核心文件；最小合并函数并入主文件；必要使用说明整理到根 `readme.md` 和本方案。目录内三个辅助工具、独立合并脚本、旧说明副本与历史报告随旧目录退出当前工作树 |
| `scripts/data-generation/` | 先完成上表最小函数迁入、导入与轨迹检查验证，再删除旧复现／比较／报告链目录 |
| `scripts/400ep-dataset/` | 清理旧扩展生成实录与辅助脚本，修正仍指向这里的活动文档链接 |
| `scripts/data-generation-MotionJEPALabel/` | 清理旧变体生成链；同步处理只服务该旧链路的测试与引用 |
| `scripts/patternlock-routestick-params/` | 清理旧参数统计／可视化链及其报告 |
| `scripts/_icl/`、`scripts/legacy/`、`scripts/__pycache__/` | 核查实际清单后清理旧版本缓存残留；不创建新的归档目录 |
| `scripts/configs/newtask-v2/native_sampling.json` | 保留，原值不改；不是待删的旧目录或 Python 入口 |
| `scripts/dataset_replay.py`、`scripts/evaluation.py`、`scripts/run_example.py` | 保留在原位置，不重写运行逻辑 |

清理限定于上述旧脚本和配套引用，不清理仓库外目录，也不扩大为根 `data/`、`artifacts/`、`runs/` 的数据清理。执行时先核对文件类型、符号链接、跟踪状态与实际产物；若清单中出现新的用户修改或未列出的生成数据，单列说明，不用递归删除顺带处理。已跟踪的旧脚本与报告可从固定 Git 历史追溯，历史账本不删除。

相关测试不能留下悬空导入：`test_seed_layout.py` 改为导入平铺的 seed 模块；涉及保留生成路径的检查改为主文件中的对应函数。`test_append_train_metadata.py`、`test_no_patch_report_debug_environment.py`、`test_swap_clip_plan.py` 等仅服务已删除功能的测试，逐项核对后随旧功能退出；混合覆盖文件只调整失效部分，保留其他有效断言。不能通过整体跳过测试目录隐藏导入失败。

### 实施文件白名单

| 文件 | 计划改动 |
| --- | --- |
| `scripts/generate_dataset_newseed.py`、`scripts/seed_layout.py` | 从旧目录迁出，按本节分配并入必要函数；原 seed、执行和记录语义不变 |
| `scripts/configs/newtask-v2/native_sampling.json` | 继续使用已提取快照；仅按源码校验，不改分布或候选 |
| `src/robomme/robomme_env/BinFill.py`、`RouteStick.py`、`VideoUnmaskSwap.py`、`VideoRepick.py` | 在原参数及位置读取处接入字典，不重写任务执行方法，不新增辅助源码文件 |
| `src/robomme/robomme_env/utils/object_generation.py` | 若旋转范围显式化确有需要，仅增加保持原默认表达式的可选参数 |
| 对应 `tests/lightweight/` 与 `tests/dataset/` 测试 | 调整保留功能的导入，补必要的提取／输入／生成对照测试，处理删除功能的孤立测试 |
| 根 `readme.md`、`AGENTS.md`、本方案 | 更新平铺命令、说明、调用图和清理证据 |

原规划工具、`RecordWrapper.py`、`DemonstrationWrapper.py`、各任务 `step/evaluate/_initialize_episode` 均保持原实现，不引入新的 ICL 层或记录格式。

## 八、实施步骤与验收判据

以下是用户后续允许实施后才执行的步骤，本轮止于方案交付。

### 第一步：固定基线并建立目标分支

复核源提交、目标分支是否存在及工作区状态，记录 `uv.lock` 的散列与实际依赖环境。从本方案固定提交创建 `newtask-v2`；如目标已经存在，停止创建动作，不重置、不覆盖。仅将本方案、配置快照和本轮账本记录带入目标分支，并入首个 `10.0` 实现提交，不把源分支的文档提交直接合并为目标首个版本。保留源分支和旧版分支。

### 第二步：平铺两个文件、并入必要依赖和提取功能

先将两个核心文件迁到根 `scripts/`，按第七节分配迁入所需函数并修正根路径、同级导入和进程启动。随后在 `scripts/generate_dataset_newseed.py` 内实现提取分支，可重复导出已提取的原值快照；按需合并也复用同文件内的原函数。此时先保留待删目录，以便做原版对照和核对依赖。

提取逐项覆盖四任务配置字典、构造函数的参数常量、场景位置表达式和工具默认值。`configs` 已有字段保持原名；原本散落的常量使用快照中的明确名称与单位。不得通过生成一批 episode 的观测频率反推“原候选”，也不得把历史生成 metadata 当作位置分布来源。

校验快照与固定源码的一致性。候选范围、布尔值、颜色顺序、锚点顺序和公式常量必须逐项相同。初版仅支持原来已经存在的区间／固定值表达方式；非连续新候选、额外权重和新拓扑不在本次实现范围。

### 第三步：接入原采样位置

按第七节白名单做最小修改，新增的数据流只走“入口配置 -> `EpisodeJob` -> 原任务配置”。不重排原采样语句和分支，不添加环境中间层。确认配置在原构造抽样前生效，且 worker 重用时没有跨 episode 共享可变数据。

### 第四步：运行有针对性的对照

每轮代码验证总耗时上限 5 分钟。优先执行定向轻量检查和覆盖核心链的真实单任务、单 episode、单 worker 对照；通过后才扩展。预算不足则报告具体未验证项并保留未完成状态，不用增加 worker 或跳过原逻辑换取“通过”。

| 验证层 | 实际要证明的内容 |
| --- | --- |
| 配置与随机流 | 四任务三难度原值一致；读配置不消费随机数；单值区间仍消费；原 generator 边界一致；缺失／未知字段拒绝；连续两个环境实例不互相污染 |
| 原版三路对照 | A：固定原版；B：新版不传配置；C：新版显式传入原值。相同 seed、episode、attempt、difficulty、GPU 和依赖环境，分别在独立进程中运行 |
| 初始场景 | 比较对象集合、颜色与角色、完整初始位姿、任务参数、`task_list` 顺序、抽样后的 generator 状态；不只比较候选字典 |
| 完整执行 | 比较实际 `solve` 顺序、原有 evaluate 调用次数、动作、任务切换和事件发生步、完成／失败状态及原始记录；测试观察器只捕获已有调用，不新增求值或物理步 |
| 记录契约 | HDF5 原 group/dataset/attribute、dtype/shape、timestep 数和末帧完成标志保持一致；比较数值内容，不要求含时间戳的视频文件或 HDF5 文件封装字节相同 |
| 既有回归 | 运行相关 `tests/lightweight/`；预算允许再补全量轻量测试。遇到失败在固定基线复核，区分基线已有失败与本次新增失败 |
| 平铺与导入 | 同级 seed 模块可独立导入且不加载生成器；提取模式不要求生成参数、不启动仿真；`spawn` 可解析 worker 和配置字典；清理后不再引用旧目录 |

首轮从四任务之一的 easy 单局三路对照开始，`--max-attempts 1` 防止换 seed 掩盖差异。通过后逐个覆盖其余三任务，再补 easy/medium/hard、BinFill dynamic 两分支和 VideoRepick hard 的五轮生成。先做三难度配置／初态覆盖，完整生成覆盖多少明确报告多少；四个 easy 通过不代表所有难度通过。

下面仅展示拟用的单局命令；`--sampling-config` 尚不存在，**本轮不执行**。A、B 分别使用原版、新版入口并省略新增参数，输出到各自独立目录；C 的示意如下：

```bash
command -v uv
uv run python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/newtask-v2/10.0/parity-explicit-binfill \
  --env BinFill --episodes 1 --episode-start 0 \
  --workers 1 --gpus 0 --layout train --difficulty 100 --max-attempts 1 \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json
```

定向轻量验证拟使用 `uv run python -m pytest tests/lightweight/test_native_sampling_config.py -q`；真实对照入口拟使用 `uv run python -m pytest tests/dataset/test_native_sampling_parity.py -q`。先执行 `command -v uv`，不使用裸 Python，不变更正式依赖。对照工作副本、生成数据与报告全部放在本仓库内的独立目录，官方参考集保持只读；输出路径不复用旧实验。

逻辑判据要求完全一致：参数、随机流状态、对象角色、子目标／事件顺序、轨迹长度和成功／失败必须相同。数值逐位对照为首要目标；若原版自身重复运行就存在浮点差异，先测量并单独记录，不能预设宽松容差掩盖新版差异，更不能把“误差小”写成“逐位一致”。

### 第五步：按清单清理旧目录并验证最终结构

两个平铺文件的导入、配置检查和最小生成对照通过后，再执行第七节的具体清理清单。先迁入必要函数和说明，更新保留测试的导入，再删除退出的旧链路和它们专用的孤立测试；不先删目录后靠逐个报错找依赖。

清理后核对 `scripts/` 下产品 Python 文件集合恰为 `dataset_replay.py`、`evaluation.py`、`run_example.py`、`generate_dataset_newseed.py`、`seed_layout.py`；无旧目录运行依赖，无新包装入口，无隐藏到其他新 Python 文件里的辅助实现。配置 JSON 保留。运行相关测试和核心单局验证，仍按每轮五分钟预算记录通过与未覆盖项。

### 第六步：核对范围并提交 10.0

通过约定的定向验证后，以 `10.0 显式接入四任务原版位置分布与参数候选` 作为首个实现提交标题；提交正文保留用户要求、完整计划、实施差异、测试命令与结果。仅逐路径提交本轮改动。

交付时给出：冻结配置、与固定基线的最小 diff、最终五脚本清单、函数迁入对应表、更新后的 ASCII 图、已运行测试与未覆盖项。首版验收覆盖原值显式注入、原链保持及用户确定的平铺清理，不包含修改分布、扩大候选或全量数据生成。

## 九、后续使用方式：提取配置，再生成 dataset

下列平铺与新增模式尚未实现，命令仅供审阅完整操作流程，**本轮不执行**。三种操作均使用同一个主文件；生成示例是最小单任务单局，通过后才能按第四步的验证覆盖逐步扩大为四任务数据集，不预设全量条数。

```bash
command -v uv
uv run python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json \
  --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8 \
  --check-config

uv run python scripts/generate_dataset_newseed.py \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json \
  --output-dir artifacts/generated/newtask-v2/10.0/smoke-binfill \
  --env BinFill --episodes 1 --workers 1 --gpus 0 \
  --layout train --difficulty 100 --max-attempts 1

uv run python scripts/generate_dataset_newseed.py --merge-only \
  --input-dir artifacts/generated/newtask-v2/10.0/smoke-binfill \
  --output-dir artifacts/generated/newtask-v2/10.0/smoke-binfill-merged \
  --env BinFill
```

提取命令不带 `--check-config` 时导出快照；带此参数时只核对既有快照。常规生成沿用原格式输出 `hdf5_files/`、`videos/`、`episode_results.jsonl`、各任务 metadata、`run_parameters.json` 和 `run_summary.json`；需要每任务一个文件时，再显式调用同文件的 `--merge-only`，得到 `record_dataset_BinFill.h5` 等文件。合并保持按需，不在生成后自动执行。生成 seed 仍来自原 `--layout` 公式，不自行创建新 seed 体系或改变位置、候选数值。

## 十、本轮交付检查

前一轮已写入原版配置 JSON，并核对 12 份难度字典、6 个原始布局数组和 7 份来源散列，静态检查退出码为 0；这些数值保持不变。本轮只修改本方案与 `AGENTS.md`，检查平铺结构、两文件职责、清理范围、ASCII 图与命令是否相互一致，以及 Markdown 链接、围栏、命令语法和 `git diff --check`。

本轮没有移动两个 Python 文件，没有删除旧目录，没有改动配置、运行源码、依赖或测试，没有执行生成、合并或仿真。实施及清理仍待后续用户指令，文档交付不代表实施已经完成。

本轮文档检查已通过，退出码 0：4 条主文件命令统一指向 `scripts/generate_dataset_newseed.py`，2 个命令围栏语法通过，6 个文档文件链接有效；原值 JSON、七份来源源码、三个原脚本与历史账本均保持原样。完整静态检查程序随本轮文档提交正文保存。
