# newtask-v2 重建方案：从 10.0 开始，仅显式控制原版采样输入

状态：**方案与原版配置快照已写入；未实现新入口、未执行重建、未生成新 dataset。**

本方案依据 2026-09-08 对本地源码和 Git 引用的只读核查。任务范围已经用户确认：`BinFill`、`RouteStick`、`VideoUnmaskSwap`、`VideoRepick`。

用户追加要求已纳入：所有面向用户的入口直接位于 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/`；提供配置提取和新 dataset 生成入口；原版配置在制定计划时就先简单提取。本轮已完成这项静态提取，见 [native_sampling.json](scripts/configs/newtask-v2/native_sampling.json)。

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
| 本轮允许修改 | 根目录本方案、`AGENTS.md` 账本和用户追加允许提取的原版 JSON 快照；沿当前基线提交版本接续，不占用目标分支的首个 `10.0` 实现版本 |

本轮不创建或切换分支、不修改运行源码或原任务取值、不运行生成、回放或仿真。新增 JSON 尚未接入运行，不改变当前生成器行为。下面的文件名、接口和命令凡标为“拟新增”均尚未实现。

## 二、原版实际调用链

基线入口是 [generate_dataset_newseed.py](scripts/data-generation-newSeed/generate_dataset_newseed.py)。它直接使用 `RobommeRecordWrapper`。模块导入了其他 wrapper，不代表生成过程中实例化了它们。

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

生成结束后，按需另行调用原 merge_episode_h5.py::merge_task()
  `--> 原 record_dataset_<Task>.h5
```

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
拟新增 scripts/generate_dataset.py
  `--> 直接转交原 main() -> 原 generate_dataset_newseed()
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
7. 纯配置模块放在 `src/robomme/sampling_config.py`，只用标准库。不能放在 `robomme_env/utils/` 后从父进程正常导入，否则包初始化会提前加载 task、`torch` 和 `sapien`，破坏原 `_pool_init()` 先绑卡再导入的顺序；不修改现有包初始化逻辑。

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

## 七、入口位置、已提取配置与后续文件范围

所有新版面向用户的脚本入口直接放在根目录 `scripts/`，子目录保留原实现模块，不要求用户进入子目录运行。

```text
scripts/
  |
  +-- extract_native_config.py        拟新增：读取固定原版源码，提取配置
  +-- generate_dataset.py             拟新增：直接调用原 newSeed 生成入口
  +-- merge_dataset.py                拟新增：按需直接调用原 HDF5 合并入口
  |
  +-- configs/newtask-v2/
  |     `-- native_sampling.json      本轮已提取：原值快照，尚未接入
  |
  `-- data-generation-newSeed/         保留原实现目录及函数调用链
        +-- generate_dataset_newseed.py
        +-- seed_layout.py
        `-- merge_episode_h5.py
```

`extract_native_config.py` 通过固定提交的源码与 AST 字面量读取提取，不导入仿真环境；遇到未支持的源码形态直接报告，不能猜测缺失值。提取后的 JSON 交由 `generate_dataset.py --sampling-config` 消费。`generate_dataset.py` 只转交原生成器，不建立新的 worker、规划器或记录器；`merge_dataset.py` 同样只转交原合并器，合并保持独立步骤，不自动删除逐 episode 源文件。

当前 [native_sampling.json](scripts/configs/newtask-v2/native_sampling.json) 已包含四任务全部 12 份难度字典、额外构造参数、位置输入、原始锚点、单位，以及七份来源文件的 SHA-256。`parameters` 和 `positions` 是后续接入的输入；`native_semantics` 只记录原分配、角色、几何和随机流约束，不产生新开关；表达式字符串仅用于核查，不执行 `eval`。

本轮用标准库 AST 直接提取了难度字典、网格与锚点字面量；其余位置公式、构造参数和工具默认值结合源码逐项补齐。提取和静态检查通过 `uv run --no-sync python -` 运行，没有导入 task、创建环境或执行采样。正式可重复使用的提取入口留待实施阶段创建。

除上述 JSON 已落盘外，下表中的实现均仅列入计划：

| 文件 | 计划改动 |
| --- | --- |
| `scripts/configs/newtask-v2/native_sampling.json`（已提取） | 原版参数与位置输入的冻结快照；后续提取入口必须复现这份原值，并补充对应自动检查 |
| `scripts/extract_native_config.py`（拟新增） | 顶层提取入口；支持 `--source-ref`、`--output` 和只校验不写入的 `--check`；固定原版提交，不读取 v1 配置 |
| `scripts/generate_dataset.py`（拟新增） | 顶层生成入口；直接转交原生成器的 `main()`，现有参数原样传递 |
| `scripts/merge_dataset.py`（拟新增） | 顶层合并入口；直接转交原 `merge_episode_h5.py::main()`，保留原参数和按 metadata 定位源文件方式 |
| `src/robomme/sampling_config.py`（拟新增） | 纯配置读取、结构校验与实例副本；仅用标准库，避免父进程经环境包初始化提前导入仿真依赖 |
| `scripts/data-generation-newSeed/generate_dataset_newseed.py` | 仅增加 CLI 配置加载、`EpisodeJob` 配置传递和 `gym.make` 的可选入参；运行目录可附配置副本 |
| `src/robomme/robomme_env/BinFill.py` | 在原参数及位置读取处接入配置，不重写其采样、场景或执行方法 |
| `src/robomme/robomme_env/RouteStick.py` | 同上，保留原网格构建和 `generate_dynamic_walk` |
| `src/robomme/robomme_env/VideoUnmaskSwap.py` | 同上，保留藏块角色、动态最近邻交换和调度 |
| `src/robomme/robomme_env/VideoRepick.py` | 同上，保留各难度生成循环、示范及正式重复动作 |
| `src/robomme/robomme_env/utils/object_generation.py` | 仅在显式旋转范围确有需要时增加可选参数；旧默认表达式与其他调用者保持不变 |
| `tests/lightweight/test_native_sampling_config.py`（拟新增） | 配置来源、取值、随机流、实例隔离与入口传递的定向验证 |
| `tests/dataset/test_native_sampling_parity.py`（拟新增） | 固定原版与显式配置版的真实生成对照，独立于产品执行链 |
| `scripts/data-generation-newSeed/README.md`、根目录账本与本方案 | 记录接口、验证证据和版本状态 |

原 `seed_layout.py`、规划工具、`RecordWrapper.py`、`DemonstrationWrapper.py`、各任务 `step/evaluate/_initialize_episode`、合并实现和回放入口均不在计划修改范围。保留现有目录，不引入 `src/robomme_icl`，不迁移到 `scripts/legacy`，不复制 v1 的 suite、预生成场景、认证状态树或新的 HDF5 格式。

## 八、实施步骤与验收判据

以下是用户后续允许实施后才执行的步骤，本轮止于方案交付。

### 第一步：固定基线并建立目标分支

复核源提交、目标分支是否存在及工作区状态，记录 `uv.lock` 的散列与实际依赖环境。从本方案固定提交创建 `newtask-v2`；如目标已经存在，停止创建动作，不重置、不覆盖。仅将本方案、配置快照和本轮账本记录带入目标分支，并入首个 `10.0` 实现提交，不把源分支的文档提交直接合并为目标首个版本。保留源分支和旧版分支。

### 第二步：复核已提取原值，实现可重复提取入口

本轮已简单提取原值；实施时让 `scripts/extract_native_config.py` 可重复导出同样的快照。逐项覆盖四任务配置字典、构造函数的参数常量、场景位置表达式和工具默认值。`configs` 已有字段保持原名；原本散落的常量使用快照中的明确名称与单位。不得通过生成一批 episode 的观测频率反推“原候选”，也不得把历史生成 metadata 当作位置分布来源。

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

首轮从四任务之一的 easy 单局三路对照开始，`--max-attempts 1` 防止换 seed 掩盖差异。通过后逐个覆盖其余三任务，再补 easy/medium/hard、BinFill dynamic 两分支和 VideoRepick hard 的五轮生成。先做三难度配置／初态覆盖，完整生成覆盖多少明确报告多少；四个 easy 通过不代表所有难度通过。

下面仅展示拟用的单局命令；`--sampling-config` 尚不存在，**本轮不执行**。A、B 分别使用原版、新版入口并省略新增参数，输出到各自独立目录；C 的示意如下：

```bash
command -v uv
uv run python scripts/generate_dataset.py \
  --output-dir artifacts/generated/newtask-v2/10.0/parity-explicit-binfill \
  --env BinFill --episodes 1 --episode-start 0 \
  --workers 1 --gpus 0 --layout train --difficulty 100 --max-attempts 1 \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json
```

定向轻量验证拟使用 `uv run python -m pytest tests/lightweight/test_native_sampling_config.py -q`；真实对照入口拟使用 `uv run python -m pytest tests/dataset/test_native_sampling_parity.py -q`。先执行 `command -v uv`，不使用裸 Python，不变更正式依赖。对照工作副本、生成数据与报告全部放在本仓库内的独立目录，官方参考集保持只读；输出路径不复用旧实验。

逻辑判据要求完全一致：参数、随机流状态、对象角色、子目标／事件顺序、轨迹长度和成功／失败必须相同。数值逐位对照为首要目标；若原版自身重复运行就存在浮点差异，先测量并单独记录，不能预设宽松容差掩盖新版差异，更不能把“误差小”写成“逐位一致”。

### 第五步：核对范围并提交 10.0

通过约定的定向验证后，以 `10.0 显式接入四任务原版位置分布与参数候选` 作为首个实现提交标题；提交正文保留用户要求、完整计划、实施差异、测试命令与结果。仅逐路径提交本轮改动。

交付时给出：冻结配置、与固定基线的最小 diff、更新后的 ASCII 图、已运行测试与未覆盖项。首版验收只针对“原值显式注入且原链保持”，不包含修改分布、扩大候选或全量数据生成。

## 九、后续使用方式：提取配置，再生成 dataset

下列入口尚未实现，命令仅供审阅完整操作流程，**本轮不执行**。生成示例是最小单任务单局；通过后才能按第四步的验证覆盖逐步扩大为四任务数据集，不预设全量条数。

```bash
command -v uv
uv run python scripts/extract_native_config.py \
  --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8 \
  --output scripts/configs/newtask-v2/native_sampling.json \
  --check

uv run python scripts/generate_dataset.py \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json \
  --output-dir artifacts/generated/newtask-v2/10.0/smoke-binfill \
  --env BinFill --episodes 1 --workers 1 --gpus 0 \
  --layout train --difficulty 100 --max-attempts 1

uv run python scripts/merge_dataset.py \
  --input-dir artifacts/generated/newtask-v2/10.0/smoke-binfill \
  --output-dir artifacts/generated/newtask-v2/10.0/smoke-binfill-merged \
  --env BinFill
```

提取命令不带 `--check` 时导出快照；带 `--check` 时只核对既有快照。生成沿用原格式输出 `hdf5_files/`、`videos/`、`episode_results.jsonl`、各任务 metadata、`run_parameters.json` 和 `run_summary.json`；独立合并后得到 `record_dataset_BinFill.h5` 等正式任务文件。生成使用的 seed 仍来自原 `--layout` 公式；计划不自行创建新 seed 体系或替用户改变位置、候选数值。

## 十、本轮交付检查

本轮只读查看分支和源码，写入本文件、原版配置 JSON 与 `AGENTS.md`。检查 JSON 解析、12 份难度字典和原源码一致、锚点和网格字面量一致、来源 SHA-256、Markdown 围栏与文件链接、命令参数、符号锚点、`git diff --check` 和最终改动范围；不运行实现测试或真实生成。运行时一致性须在后续实施阶段以实际对照报告证明。

静态检查已通过，退出码为 0：12 份难度字典、6 个原始布局数组、7 份来源文件散列、6 个文档文件链接、2 个命令围栏语法均通过；原账本历史正文保留，三个拟建入口均尚不存在。完整静态检查命令随本轮提交正文保存，检查没有启动仿真或生成。
