# newtask-v2 重建方案：从 10.0 开始，仅显式控制原版采样输入

状态：**仅修订本计划。两个生成侧文件平铺方案及原值快照保留；新增五项重要对拍、可复现测试、实测文档与轻量证据留档要求，均未实施或实测。**

本方案依据 2026-09-08 对本地源码和 Git 引用的只读核查。任务范围已经用户确认：`BinFill`、`RouteStick`、`VideoUnmaskSwap`、`VideoRepick`。

用户已确定：生成侧只保留 `generate_dataset_newseed.py` 和 `seed_layout.py`，将实际需要的函数及依赖并入这两个文件，移到 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/`，与原有 `dataset_replay.py`、`evaluation.py`、`run_example.py` 平铺。`data-generation-newSeed/` 不作为最终目录保留。原版配置快照保持原样，见 [native_sampling.json](scripts/configs/newtask-v2/native_sampling.json)。

**用户最新范围限制：“只改这一份计划 我要的是修改计划！”因此本轮唯一修改文件为 `NEWTASK_V2_PLAN.md`。不修改 `AGENTS.md`、源码、测试或 JSON，不创建 `docs/`、证据包或目标分支，不执行生成、仿真和清理。下文写入 `AGENTS.md`、实现测试及保留 docs 的要求，全部是后续实施计划，不是本轮操作。**

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
| 本轮允许修改 | 仅根目录 `NEWTASK_V2_PLAN.md`；其余文件及原值 JSON 不变；沿源分支文档版本接续，不占用目标分支的首个 `10.0` 实现版本 |

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
| `tests/_shared/` 中拟新增的对拍工具 | 仅承载测试观察器、证据编码、实测报告及离线比较；不被产品生成器导入，不复用会换 seed 或改写执行链的测试工厂 |
| 拟新增的 `docs/` 文档与轻量证据 | 后续保存通用规则、实测报告、冻结用例、无损关键帧和压缩轨迹，逐路径纳入 Git；本轮不创建 |
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

### 第四步：实现可复现测试，逐层完成五项重要对拍

①关键帧目视、②变量与物体变化、③HDF5 内容由用户直接提出；④随机流和⑤连续 worker 隔离经用户确认加入。五项均为“用户关心的重要对拍”，独立编号、独立保留证据和结论，不能相互替代。以后如需新增其他重要对拍，先询问用户是否列入，不自行扩大验收范围。

#### 4.0 共用基准、调用位置与观察器校验

- **A：固定原版**，提交 `94449db0a068a6b454b55a13ebd48f0394d89cc8`；**B：新版不传配置**；**C：新版显式传入冻结原值配置**。同一用例固定任务、实际难度、episode、seed、attempt、GPU、依赖和原有参数，独立进程运行，分别比较 `A↔B`、`A↔C`、`B↔C`。
- 实际生成走各自原入口及原 worker，保留 `--workers 1 --max-attempts 1`，记录内部实际 attempt。不得改用会自动换 seed、另写求解循环或改变判定的测试工厂；不能只验证复制到测试中的生成逻辑。
- 观察器仅在测试代码中捕获原有调用的入参、返回值及前后状态，不新增 `evaluate()`、reset、随机抽样、渲染或物理步。逐步证据先缓存在内存，结束后写出，不改变产品 HDF5 格式或增加环境中间层。
- 每条证据记录“调用序号、环境实际步数、调用阶段、HDF5 记录编号”。原 `timestep_N` 来自记录缓冲区编号，不能直接当物理步数。任务在观测返回之后发生的变化，注明首次进入后续原有观测的位置，不归入已经返回的画面。
- 正式比较前，做原版重复运行及原版启用／关闭观察器的校准，比较动作、事件、完成状态和 HDF5。观察器改变结果时先修观察器；原版自身有差异时单独测量、记录并标记受阻，不预设宽松容差，不把“误差小”写成“逐位一致”。

#### 4.1 重要对拍①：关键帧目视检查无区别

**①.1 关键帧集合。** 分别提取 A、B、C 的首末帧、`is_subgoal_boundary`、演示切换、目标和完成／失败标志变化，以及物体创建、移除、抬起／回落、交换、显隐、高亮开始／结束等事件位置。三路取并集，每个边界保留前一帧、本帧、后一帧；越界明确标记，不只按新版选帧。不假设原版存在 `is_keyframe` 字段。初态使用原 reset 返回的观测，不额外渲染。

**①.2 对齐。** 先核对事件发生步、调用阶段和记录编号；缺帧、多帧、错位直接报差异，不平移时间轴、不找最近帧、不重采样以消除差异。

**①.3 出图与实际查看。** 从原始 RGB 数组导出原分辨率无损 PNG，正面和腕部相机分别排列 A／B／C 原图及差分图。标注任务、难度、seed、事件、步数和记录编号，逐图查看物体数量、颜色、身份、位姿、遮挡、机械臂及高亮效果。生成图版不代表已经目视。

**①.4 判据与证据。** 全部规定关键帧已查看、无可见区别，帧序和事件对应关系一致才通过。保留关键帧索引、图版、逐图目视记录和像素差异统计。目视记录绑定图片散列，图片变化后旧记录不能直接沿用。任何像素差异仍交③处理，不能以“看不出来”认定 HDF5 内容一致。

#### 4.2 重要对拍②：变量跳变、物体位置及产生／消失过程不变

**②.1 构造与初态。** 在原构造抽样、场景加载、内部初始化及外层 reset 对应边界，比较任务参数、对象集合与创建顺序、颜色和角色、位置与四元数、机器人状态、目标绑定及 `task_list` 顺序。对象按名称、角色、创建序号对应，不按位置排序，以免掩盖物体交换。

**②.2 逐步状态。** 在原任务 `step()`、内部 `BaseEnv.step()`、原有 `evaluate()` 和 `solve()` 调用前后，记录任务索引、子目标、演示／特殊／成功／失败标志、目标对象与列表顺序、交换计划和计数器，以及所有任务物体的位置、旋转、速度、存在状态。比较实际动作、求值次数、参数和返回值。先从四任务及调用工具的状态写入处形成明确字段清单；不可序列化的任务状态须补提取方式，不静默省略。

**②.3 事件。** 每个事件记录对象身份、类型、发生步、调用阶段及变化前后值。区分真实创建／删除、视觉隐藏／恢复、移到视野外和普通遮挡，至少覆盖：

| 任务 | 必验变量与事件 |
| --- | --- |
| `BinFill` | `dynamic` 两分支；各颜色生成数和目标数；抬起／回落及 `idx * 100` 边界；逐色投入和任务切换 |
| `RouteStick` | 路线节点与摆动方向顺序；目标按钮变化；轨迹标记、按钮高亮的创建／刷新／消失；失败锁存 |
| `VideoUnmaskSwap` | 容器与方块绑定；初始抬起／回落；交换对象、起止步和临时选定对象；方块随容器移动及目标选择 |
| `VideoRepick` | `static_flag`、`start_step`、交换计划、目标和重复次数；hard 原五轮各自的颜色打乱、创建顺序及位姿，总计 15 块 |

**②.4 判据与证据。** 初态、逐步状态、事件次序和发生步、动作、轨迹长度及终态全部一致。保留压缩状态轨迹、事件和调用序列；首个分歧定位到字段／对象／调用阶段，并附前后上下文。不能只比末帧、成功率或候选字典。

#### 4.3 重要对拍③：HDF5 生成产物内容与原版一致

**③.1 文件和结构。** 比较文件、episode、group、dataset、attribute 的全集，以及 timestep 集合和数量；逐项检查 dtype、shape、字符串编码类型及属性值。遍历实际落盘树，未知字段也比较，不只检查少数字段。

**③.2 全量内容。** 每个 timestep 的全部实际字段逐元素比较：`obs` 的正面／腕部 RGB、深度、关节、夹爪、末端和相机参数；`action` 的 joint／eef／waypoint／choice action；`info` 的子目标文本、完成、演示和边界；`setup` 的 seed、difficulty、任务目标、候选操作和内参。浮点同时核对原 dtype 下的位模式；字符串保留原值，不改写 JSON、不排序候选、不四舍五入。

**③.3 对应运行证据。** 将落盘记录与②捕获的原记录内容及阶段对应，检查漏帧、多帧、动作错位、事件标签提前／滞后或提前完成。末帧 `is_completed` 的严格布尔类型和值均一致。

**③.4 原始与合并文件。** 先比较每 episode 原始文件，再分别经原合并函数和新版迁入的同一逻辑生成任务文件，重复结构与内容检查。

**③.5 判据与证据。** 全部实际落盘内容一致才通过；仅结构相同、仅 joint action 相同或一次成功回放都不足。保存全字段结果、首个不同元素、差异数量及可量化字段的最大绝对差。不要求 HDF5 容器封装字节或带时间戳视频文件字节相同，但不得排除任何 HDF5 数据字段。原版失败而没有有效 HDF5，只能记失败行为对照，不能计产物一致通过。

#### 4.4 重要对拍④：随机抽样调用及随机流状态一致

**④.1 输入检查。** 四任务三难度原值与固定源码逐项一致，缺失／未知字段拒绝；加载、校验和复制配置前后已有随机流状态不变。

**④.2 调用检查。** 捕获实际随机调用的顺序、函数、上下界、shape、dtype、所属 generator、结果及前后状态。拒绝采样保留全部尝试，不只记录最终成功样本；单值区间仍消费原来的随机数。

**④.3 生命周期。** 比较 generator 创建、设 seed、重新创建及持续使用的位置，保留各任务局部／实例随机流边界、颜色和锚点顺序，不合并随机流。

**④.4 判据与证据。** 对应调用序列、参数、抽样结果和状态全部相同；保留去重状态快照及首个分歧调用。不用抽样频率或最终位置相同代替随机流一致。

#### 4.5 重要对拍⑤：同一 worker 连续生成时配置互不污染

**⑤.1 数据所有权。** 检查父配置、`EpisodeJob` 和环境实例的可变部分互不共享。轻量测试修改一个实例副本，其他实例、类默认值和冻结配置不变；改过的副本不用于真实生成。

**⑤.2 真实连续运行。** 同一实际 worker 执行“用例甲→不同任务或难度的用例乙→再次用例甲”，保持原 seed 公式。逐局与对应独立 worker 运行比较，并以原版连续运行作参照；覆盖不传配置和显式原值配置两路，不能用三个独立进程冒充连续 worker。

**⑤.3 判据与证据。** 后续 episode 的配置、随机流、初态、事件及 HDF5 与相应独立运行一致，父配置前后散列不变。保留 worker 标识、执行顺序和逐局结果；两个字典对象不同不能代替真实生成验证。

#### 4.6 必验矩阵、顺序与五分钟预算

用户已确认全部覆盖才完成，不采用“四任务 easy 即首版整体通过”的口径。

| 任务 | 完整生成必验格 |
| --- | --- |
| `BinFill` | easy／medium／hard，各覆盖 `dynamic=False`、`dynamic=True`，共 6 格 |
| `RouteStick` | easy／medium／hard，共 3 格 |
| `VideoUnmaskSwap` | easy／medium／hard，共 3 格 |
| `VideoRepick` | easy／medium／hard，共 3 格；hard 检查原构造中的五轮循环，不替换成五个独立 episode |

至少 **15 个成功场景格**，每格分别登记①—⑤。按实际生效的难度和分支计覆盖，不只看 CLI。由原版按原 seed 公式确认并冻结分支用例，不强制改写 `dynamic`；这仅用于选择覆盖用例，不用于反推原候选或位置分布。原版失败用例保留，另增独立成功用例补足产物覆盖，不删除失败记录或自动换 seed 替代。

顺序为：定向轻量检查 → 原版重复性及观察器校准 → `BinFill` easy 单局三路 → 其余 easy → 三难度及特殊分支 → 连续 worker → 清理后复验。先做三难度配置／初态覆盖，再按实际情况登记完整生成，不将初态覆盖当完整执行通过。

每轮验证累计不超过 5 分钟，先单任务、单 episode、单 worker。预算不足保留待验；单用例无法在预算内完成则记录受阻，不增加 worker、不缩短轨迹、不跳过原逻辑。全部必验项完成前不能标记整体通过。

同时保留配置提取、缺失／未知输入、同级 seed 独立导入、提取模式不加载仿真、`spawn` 传递、清理后无旧依赖等定向检查。运行相关 `tests/lightweight/`，预算允许再补全量；失败在固定基线复核，区分已有和新增问题，不通过整目录跳过隐藏失败。

#### 4.7 固化为可复现测试与三种操作

后续在 `tests/lightweight/` 实现配置、比较器和证据契约检查；`tests/dataset/` 实现原版重复性、观察器校准、三路及连续 worker 实测；`tests/_shared/` 只承载测试观察器、证据编码、报告和离线比较，不被产品生成器导入。

比较器必须包含反例：关键帧单像素变化、错位或缺帧；对象身份替换、位置跳变、遗漏产生／消失事件；HDF5 缺字段、dtype／shape 或数值变化；少一次随机调用或状态不同；跨 episode 污染；证据损坏、来源不匹配和目视记录引用旧图。证明测试能拒绝这些错误，不只证明自身输出可读回。

| 后续操作 | 输入与要证明的内容 |
| --- | --- |
| 从头复现 | 冻结用例和固定源码，在新目录完整运行 A／B／C 并比较 |
| 当前代码回归 | 指定 Git 中固定原版证据，重新运行当前 B／C 并直接比较；不自动重生成或刷新旧基准 |
| 纯离线比较 | 显式给两份已有证据和新结果目录，不加载仿真、不占用 GPU；结论只适用于对应历史运行 |

拟用入口为 `uv run python -m pytest tests/lightweight/test_native_sampling_config.py -q`、`uv run python -m pytest tests/lightweight/test_native_sampling_evidence.py -q` 和 `uv run python -m pytest tests/dataset/test_native_sampling_parity.py -q`。三路测试拟支持 `--parity-mode fresh|regression`、`--parity-cases`、`--parity-case`、`--parity-reference`、`--parity-output`；离线入口拟为 `uv run python -m tests._shared.native_sampling_parity compare --reference <证据包> --candidate <证据包> --output <新目录>`。文件与参数均未实现，本轮不执行；后续报告须填真实有效、可直接复制的完整命令，不能把占位符当复现记录。

以下仅保留 C 路原生成器的拟用单局命令；A、B 用对应入口并省略新增配置参数，三路输出独立。**本轮不执行**：

```bash
command -v uv
uv run python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/newtask-v2/10.0/parity-explicit-binfill \
  --env BinFill --episodes 1 --episode-start 0 \
  --workers 1 --gpus 0 --layout train --difficulty 100 --max-attempts 1 \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json
```

Python 命令前先确认 `command -v uv`，不变更正式依赖。对照工作副本、生成数据与报告均放仓库内，官方参考保持只读，输出不复用旧实验。

#### 4.8 后续重要测试／生成统一写 docs，保留实测与轻量证据

**后续实施时才将本小节的通用约定写入 `AGENTS.md` 并建立 docs。本轮只改本计划，不创建这些文件。** 以后用于重要验收、回归、一致性判断的测试和生成，都须保留可复现入口、实测文档及轻量证据；成功、失败、中断、超时和未覆盖项如实记录。只有聊天、终端输出或临时缓存不算留档完成。不追补所有历史实验，不扩大旧产物清理范围。

用户已确认**文档及轻量证据一并纳入 Git**，以后其他 checkout 可直接比较。完整 HDF5、视频和详细日志留在仓库内 `artifacts/`，不提交大型产物。目标结构如下，当前未创建：

```text
docs/
  README.md
  validation/
    README.md                       通用记录与比较规范
    newtask-v2/
      README.md                     用例说明与运行索引
      cases.json                    实际用例与覆盖，不提前伪造
      <运行编号>/
        README.md                   中文实测报告
        result.json                 逐项机器结果
        manifest.json               来源、编码版本、大小与 SHA-256
        evidence/                   去重后的轻量证据
```

每次重要运行用独立 `<UTC时间>-<主题>-<短源码版本>` 编号，冲突加序号，非空输出拒绝覆盖。显式指定基准，不默认选最新；更新另建版本并解释原因，测试失败不能自动刷新期望值。`cases.json` 在原版选定用例后冻结实际 seed、episode、difficulty、分支和覆盖关系，不以候选版结果挑选有利样本。

清单记录源码提交、实际导入源码、测试实现、未提交差异、配置及输入指纹，实际依赖与锁散列、设备和必要环境。证据内部用包内或仓库相对路径；绝对工作目录只作执行记录，不成为读取依赖。来源和环境不匹配必须明确报告，不能把环境变化直接归因于代码。

每份实测报告必须写清：

1. 目的、重要对拍编号、参考与候选、与上一轮的关系。
2. 源码和差异指纹、配置、输入、实际依赖及设备。
3. 完整命令、工作目录、起止时间、耗时、退出码与输出目录。
4. 实际 seed、attempt、难度、分支、worker、GPU 及执行顺序。
5. ①—⑤逐用例结果和实测帧数、事件数、字段数、差异数。
6. 首个分歧、必要上下文、原因是否确认、失败或受阻及未覆盖项。
7. 证据索引、实际文件数与体积、完整产物位置、重跑和离线比较命令。

未运行不填预期数字，不能从候选配置或打印的成功消息推断数据一致。后续实际命令从运行记录写入报告，而非只保留泛化模板。

| 轻量证据 | 保存方式 | 后续可直接比较的内容 |
| --- | --- | --- |
| 配置、用例和来源 | JSON | 输入与运行条件 |
| 数值状态、位姿、动作 | 原 dtype 的压缩数组 | 逐元素差异、首个分歧及幅度 |
| 任务与物体事件、调用次序 | 压缩结构化序列 | 身份、类型、发生步、阶段和前后值 |
| 随机流 | 调用记录及去重状态快照 | 抽样次序、参数、结果和状态 |
| HDF5 全字段 | 结构、属性和内容指纹；小型字段另存原值 | 全字段相等性及差异字段／记录定位 |
| 全部规定关键帧 | 原分辨率无损 PNG，内容去重 | 目视和逐像素比较 |
| 目视记录 | 检查人、结论及绑定图片散列 | 是否检查本次证据 |
| 失败信息 | 首个差异、必要上下文和关键日志摘录 | 复现与定位 |

只用无损压缩、内容去重及去掉完整视频／重复全帧图像实现轻量化，不降低精度、不遗漏必验事件、不删除规定关键帧。A、B、C 相同内容引用同一份证据。HDF5 指纹按版本化规则纳入字段路径、dtype、shape、属性和原始内容；浮点保留位模式，字符串逐元素编码，不散列对象地址或容器封装字节。

**能力边界必须写明：** 指纹能判断未保留原像素的非关键帧是否相同并定位字段／记录，但不能还原画面或计算其像素差幅度；需要展开时按冻结命令重跑原版。轻量包不能称作完整 HDF5 备份。

状态区分“通过、失败、受阻、未验证、待目视”。原版不稳定、缺证据或未目视时不得整体通过；历史包比较通过不得写成当前代码回归通过。最后将 Git 中的文档和证据复制到另一个仓库内目录，不访问原运行目录、不加载仿真，完成离线比较以证明不依赖临时缓存或绝对路径。

### 第五步：按清单清理旧目录并验证最终结构

两个平铺文件的导入、配置检查和最小生成对照通过后，再执行第七节的具体清理清单。先迁入必要函数和说明，更新保留测试的导入，再删除退出的旧链路和它们专用的孤立测试；不先删目录后靠逐个报错找依赖。

清理后核对 `scripts/` 下产品 Python 文件集合恰为 `dataset_replay.py`、`evaluation.py`、`run_example.py`、`generate_dataset_newseed.py`、`seed_layout.py`；无旧目录运行依赖，无新包装入口，无隐藏到其他新 Python 文件里的辅助实现。配置 JSON 保留。运行相关测试和核心单局验证，仍按每轮五分钟预算记录通过与未覆盖项。最终证据必须对应清理后的源码；清理前证据不能直接充当最终版本实测，报告须记录复验来源。

### 第六步：核对范围并提交 10.0

15 格五项重要对拍完成、目视记录齐全、证据完整可读、离线比较可复现，且实测文档对应清理后的源码后，才完成实施验收。随后以 `10.0 显式接入四任务原版位置分布与参数候选` 作为首个实现提交标题；提交正文保留用户要求、完整计划、实施差异、测试命令与结果。仅逐路径提交本轮源码、测试、文档与轻量证据，不提交完整 HDF5 或视频。未完成验证保留待验或受阻，不降低标准宣称完成。

交付时给出：冻结配置、与固定基线的最小 diff、最终五脚本清单、函数迁入对应表、更新后的 ASCII 图、15 格覆盖矩阵；①关键帧图版及逐图记录、②状态／事件对照、③原始与合并 HDF5 全字段比较、④随机流报告、⑤连续 worker 隔离报告；真实命令、退出码、轻量证据索引、全部失败证据和未覆盖项。首版验收覆盖原值显式注入、原链保持及用户确定的平铺清理，不包含修改分布、扩大候选或全量数据生成。

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

历史静态检查：原版 JSON 已提取，曾核对 12 份难度字典、6 个布局数组和 7 份来源散列；前一轮平铺计划检查了 4 条主文件命令、2 个命令围栏及 6 个文件链接，退出码 0。这些是历史文档／配置核查，不能作为新对拍已实施的证据。

本轮最终只修改 `NEWTASK_V2_PLAN.md`，不保留对其他文件的改动、新 docs、代码、测试产物或目标分支。没有执行新生成器、真实对拍、仿真、合并或旧目录清理。五项测试、15 格实测、docs 和轻量证据均仍未实施；本计划交付不代表实现或验收完成。

本轮文档核对项：只有本计划的差异；五项编号、15 格覆盖、未来测试入口和证据留档相互一致；现有文件链接、围栏、命令语法及 `git diff --check`；原值 JSON、源码、测试、依赖和 `AGENTS.md` 不变。静态检查仅验证文档，不能计入五项重要对拍的通过数量。

2026-09-08 本轮静态检查实测通过，退出码 0，耗时 0.046 秒：6 个文件链接有效、2 个 Bash 命令围栏通过 `bash -n`、4 条生成示例指向同一拟平铺入口；5 个重要对拍和 6 个实施步骤齐全；第二至第六节原链说明逐字未变；7 份来源文件散列及冻结 JSON 未变；非计划文件改动为 0，临时目标分支和新文件均未保留。检查先执行 `command -v uv`，随后以 `uv run --no-sync python -` 运行只读标准库程序，完整检查程序随文档提交正文保存；没有执行生成示例或真实对拍。
