# newtask-v2 重建方案：从 10.0 开始，仅显式控制原版采样输入

状态：**方案文档第四次修订（2.24）。两个生成侧文件平铺方案保留；原值快照按本轮审查补录缺项、不改已有值；五项重要对拍、可复现测试与留档要求按用户决策修订判据与退出路径。全部实施、生成与对拍仍未执行。**

本方案依据 2026-09-08 对本地源码和 Git 引用的只读核查，以及同日 11 路并行对抗审查的结果修订。任务范围已经用户确认：`BinFill`、`RouteStick`、`VideoUnmaskSwap`、`VideoRepick`。

用户已确定：生成侧只保留 `generate_dataset_newseed.py` 和 `seed_layout.py`，将实际需要的函数及依赖并入这两个文件，移到仓库根 `scripts/`，与原有 `dataset_replay.py`、`evaluation.py`、`run_example.py` 平铺。`data-generation-newSeed/` 不作为最终目录保留。原版配置快照见 [native_sampling.json](scripts/configs/newtask-v2/native_sampling.json)，本轮只增不改已有值。

**本轮（2.24）范围：修改 `NEWTASK_V2_PLAN.md`、补录 `scripts/configs/newtask-v2/native_sampling.json`、更新 `AGENTS.md` 账本，共三个文件。不修改源码、测试，不创建 `docs/`、证据包或目标分支，不执行生成、仿真和清理。下文写入实现测试及保留 docs 的要求，全部是后续实施计划。** 上一轮（2.23）用户曾限定"只改这一份计划"，本轮经用户逐项决策后扩大为三个文件。

## 一、目标与版本边界

从 `dataset-gen-NewSeed` 重新建立 `newtask-v2`，首个实现提交为 `10.0 <中文描述>`，后续常规实现从 `10.1` 接续。`10.0` 指此次重建的 Git 版本序列，不修改当前 Python 包的 `0.1.0` 版本。选用 `10.0` 而非接续 `2.x`/`3.x` 的理由：`3.0`–`3.4` 已被 `newtask-v1` 分支占用，且两条分支都用过 `2.20`，新分支从空档起号可避免再次碰撞；此为用户显式授权的例外，不改变 `AGENTS.md` 中"以 `git log` 最近一次为准"的常规规则。

本次唯一目标是：**把四个原任务已经使用的位置分布和参数候选提取出来，成为显式传入的配置；初始配置值、采样方式和完整执行链均保持原版行为。** "固定候选"是固定可以抽取哪些值及其原有抽法，每个 episode 仍由原 seed 在原位置抽样；不是把每局结果固定成一个值。"显式控制"是可检查、可传入这些输入。为承载提取、校验与按需合并，主文件会增加两个辅助入口模式（第七节），但不增加新的生成流程、环境包装层或第二套执行逻辑。

| 项目 | 已核对的基线与处理方式 |
| --- | --- |
| 用户所说的源分支 | 实际大小写为 `dataset-gen-NewSeed` |
| 固定源码基线 | `94449db0a068a6b454b55a13ebd48f0394d89cc8`，提交标题为 `2.20 忽略根目录 artifacts 产物` |
| 基线与当前源分支的差异 | 基线之后的 2.21–2.24 只新增或修改 `NEWTASK_V2_PLAN.md`、`AGENTS.md`、`scripts/configs/newtask-v2/native_sampling.json`；`src/`、`scripts/` 下 Python、`uv.lock`、`pyproject.toml` 与基线逐字节相同 |
| 远端跟踪引用 | 2.21 撰写时 `origin/dataset-gen-NewSeed` 曾等于基线；本计划每次提交并推送都会使远端前移，因此该引用不再作为基线依据，基线只以上面的提交散列为准 |
| 旧版参考 | `newtask-v1` / `origin/newtask-v1` 为 `be7a59db07ffd50011576dda9c432f81903e031b`；其分出点为 `b4fe428`（`2.19`），比基线早一个只改 `.gitignore` 的提交，故 v1 的 `src/robomme` 起点与基线一致；只读参考，不合并其实现 |
| 重建方式 | 后续从固定源码基线创建全新的 `newtask-v2`；不从 `newtask-v1` 接续。若目标分支已存在，停止创建并询问用户，不重置、不覆盖、不自行换名 |
| A 路原版源码来源 | 三路对拍开始前，在仓库内 `artifacts/` 下以 `git worktree add --detach <目录> 94449db0a068a6b454b55a13ebd48f0394d89cc8` 物化原版，不创建分支；A 路入口是原路径 `scripts/data-generation-newSeed/generate_dataset_newseed.py`。第三步改动任务源码后工作区不再等于基线，此后所有 A 路运行都必须来自该 worktree |
| 两份计划文本 | 本计划在源分支按 `2.x` 接续；创建 `newtask-v2` 时复制进目标分支并入 `10.0`。此后目标分支上的副本为实施权威，源分支副本不再修订 |
| 本轮允许修改 | `NEWTASK_V2_PLAN.md`、`native_sampling.json`（只增不改）、`AGENTS.md` 账本；沿源分支文档版本接续，不占用目标分支的首个 `10.0` 实现版本 |

本轮不创建或切换分支、不创建 worktree、不修改运行源码或原任务取值、不运行生成、回放或仿真。新增 JSON 尚未接入运行，不改变当前生成器行为。下面的文件名、接口和命令凡标为"拟新增"均尚未实现。

## 二、原版实际调用链

固定基线的原入口是 `scripts/data-generation-newSeed/generate_dataset_newseed.py`（该路径已在第五步清理中退出工作树，只在基线 worktree `artifacts/native-baseline` 与 Git 历史中存在；平铺后的入口是 [generate_dataset_newseed.py](scripts/generate_dataset_newseed.py)）。它直接实例化的 wrapper 只有 `RobommeRecordWrapper`；`robomme.env_record_wrapper` 包的 `__init__.py` 会连带导入 `DemonstrationWrapper` 等其他 wrapper，但生成过程中不实例化它们。下图函数顺序不因文件位置改变；共享的必要函数并入两个保留文件，具体分配见第七节。

下面按执行顺序画出 ASCII 调用图；缩进内是被调用方，返回后继续向下。

```text
generate_dataset_newseed.py::main()
  |
  +--> _args()
  |
  +--> generate_dataset_newseed()
         |
         +--> _ensure_layout()                        校验 uv.lock 与 src/
         +--> _prepare_output()                       输出目录须在仓库内
         +--> parse_tasks() / get_layout() / _parse_gpus()
         +--> parse_difficulty_ratio("211")           展开为 (easy, easy, medium, hard)
         +--> seed 天花板护栏                          最后一个 episode 的 attempt=99 不得撞下一个 env_code 块
         +--> 逐 episode：difficulty_for(episode, cycle) + layout.seed(task, episode, 0) -> EpisodeJob
         +--> 原子写 run_parameters.json
         |
         +--> _run_jobs()
         |      |
         |      +--> 每张 GPU 一个 spawn 进程池（max_tasks_per_child 默认 8）
         |      |      `--> _pool_init()：写 CUDA_VISIBLE_DEVICES，再 import torch / sapien
         |      |
         |      `--> _worker(job)                         每次 attempt 新建环境，finally 里 close
         |             |
         |             +--> _planner_classes()           定义原有规划器子类
         |             |
         |             +--> gym.make(job.task, obs_mode, control_mode, render_mode, reward_mode,
         |             |             seed=job.seed, difficulty=job.difficulty,
         |             |             [robomme_failure_recovery=True, robomme_failure_recovery_mode=job.recovery_mode])
         |             |      `--> 原任务类 __init__(seed=..., difficulty=..., **kwargs)
         |             |             +--> 原难度解析、参数抽样、随机流初始化（用形参 seed）
         |             |             `--> BaseEnv.__init__()                       无 **kwargs，未取走的新参数直接 TypeError
         |             |                    `--> 内部 reset(seed=2022, reconfigure=True)   ManiSkill 侧 seed 与 job.seed 无关
         |             |                           +--> _reconfigure()
         |             |                           |      `--> 原任务 _load_scene()
         |             |                           |             +--> 原对象生成工具
         |             |                           |             `--> RouteStick / VideoUnmaskSwap 构造 task_list
         |             |                           `--> 原任务 _initialize_episode()             第一次
         |             |                                  `--> BinFill / VideoRepick 构造 task_list
         |             |
         |             +--> RobommeRecordWrapper(base_env, ...)
         |             |      `--> use_demonstrationwrapper = False
         |             |
         |             +--> record_env.reset()                    无参；不 reconfigure，_load_scene 不再执行
         |             |      +--> 原环境 _initialize_episode()    第二次；BinFill/VideoRepick 的 task_list 以此次为准
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
         |      +--> 连续 MAX_NON_TASK_STRIKES=3 次非任务性失败：放弃该 episode
         |      +--> 池崩溃：合成失败记录，任务 appendleft 插队重入
         |      `--> 其余且 attempt+1 < max_attempts：原 seed 公式 -> 再次 _worker()
         |
         `--> _write_metadata() + run_summary.json

基线生成结束后，按需另行调用 merge_episode_h5.py::merge_task()
  `--> 原 record_dataset_<Task>.h5
```

上图末尾是原版已有的独立合并调用。后续只将合并函数迁入平铺主文件，由拟新增 `--merge-only` 模式显式调用；不改变原生成过程，不自动追加合并步骤。

**seed 的入口必须写明：** seed 是 `gym.make` 的 kwarg，被任务 `__init__` 的显式形参 `seed` 接住，任务自建 `torch.Generator().manual_seed(seed)` 承载全部任务级随机；`record_env.reset()` 不传 seed。ManiSkill 的 `_episode_rng` 与构造期 `fork_rng` 内的全局 torch 流由 `BaseEnv.__init__` 硬编码的 2022 驱动，外层 reset 时 `_set_episode_rng` 因 `_enhanced_determinism=False` 不执行。两条流正交；迁移时若把 seed 改挂到 `reset(seed=...)`，会同时改变 ManiSkill 的 `_main_seed`/`_episode_seed` 并触发 fork_rng 分支，原链立即失守。

`BaseEnv` 内部构造时 reset 的顺序已通过当前安装源码 `mani_skill/envs/sapien_env.py` 的 `BaseEnv.__init__`、`_reconfigure`、`reset` 核对。两次 reset 不等价，差异如下，两者都保留、不合并、不额外插入 reset：

| 项目 | 构造期内部 reset | 外层 `record_env.reset()` |
| --- | --- | --- |
| 是否 reconfigure | 是，执行 `_load_scene` | 否（`reconfiguration_freq` 默认 0），`_load_scene` 不执行 |
| ManiSkill 侧 seed | 2022，`_load_scene` 在 `torch.manual_seed(2022)` 的 fork 上下文内 | 无；`_initialize_episode` 不在 fork 内 |
| 任务级 generator | 用 `__init__` 刚播种的流 | BinFill/VideoRepick 用同一条 `self.generator` 的续状态；RouteStick/VideoUnmaskSwap 的 `_initialize_episode` 不消费任务随机 |
| 后果 | — | BinFill `_initialize_episode` 内的 `torch.randperm(3, generator=self.generator)` 与 recovery 模式下的 `inject_fail_grasp` 各执行两次，最终 `task_list` 以第二次为准；VideoRepick 同理 |

后续需同时固定依赖锁和运行环境；基线与当前 `uv.lock`、`pyproject.toml` 已确认相同。

`_planner_classes()` 中的 screw 三次、随后 RRTStar 三次回退保持原样。任务自己的 `step()` 中：BinFill、VideoUnmaskSwap、VideoRepick 的抬起／回落、交换等操作全部在 `super().step()` **之前**；RouteStick 的高亮刷新全部在 `super().step()` **之后**；没有任务是"前后各有"。这些位置保持原样，图中没有把这些事件迁移进 `BaseEnv`。

`recovery_mode` 由 `EpisodeJob` 按 episode 号硬分档：episode 0–2 为 `"z"`，3–5 为 `"xy"`，其余 `None`；非 `None` 时向 `gym.make` 追加两个 kwarg，并在 `_initialize_episode` 中触发 `inject_fail_grasp(..., generator=self.generator)`，额外消费任务随机流。

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

1. 在四个原任务的 `__init__()` 中接收并取走 `sampling_config`（`default=None`），在首次参数抽样及 `super().__init__()` 之前准备实例专属配置。硬约束与依据：`BaseEnv.__init__` 是纯显式形参、没有 `**kwargs`，漏 pop 直接 `TypeError`；gymnasium 会把传入 kwargs 字典的**引用**存进 `env.unwrapped.spec.kwargs`，独立副本只能由 task 侧 `copy.deepcopy` 保证；配置取走、校验、深拷贝阶段**禁止任何随机数调用**，且必须落在 `torch.Generator()` 创建之前。四任务的随机流边界不同：BinFill、VideoRepick 的 `__init__`、`_load_scene`、两次 `_initialize_episode` 共用同一条 `self.generator`，在 `__init__` 多抽或少抽一次会平移其后全部取值；VideoUnmaskSwap、RouteStick 在 `_load_scene` 重新播种另一条局部流。新参数必须带 `None` 默认值，因为这四个类还被 `episode_config_resolver.py` 与 `tests/_shared/dataset_generation.py` 构造。保留原类、原注册 ID 和原方法，不新增 ICL 子类或环境包装层。
2. 原 `configs` 中的整数区间仍交给原来的 `torch.randint(low, high + 1, ...)`；固定整数仍直接取值。不得把所有参数统一改成新的 `choice()` 抽样器。
3. 原 `torch.rand()` 表达式只替换字面常量来源，保留乘法、加减法和类型转换顺序。**升级为 schema 级硬约束：** JSON 只允许存源码里出现的运算元（如 `scale`、`subtract`、`base_position`），禁止折算成 `[min,max]` 区间。依据：BinFill 板位按源码形式 `0.15 + (u * 0.2 - 0.2)` 与折算形式 `-0.05 + u * 0.2` 的 float64 位模式不同（已实测）；当前 JSON 里三处 `*_range_*` 区间字段仅因下界为 0 而巧合安全，实施时须改写为运算元形式或在校验器中特判。配置值一律以 Python 标量参与运算，禁止包成 `torch.tensor` 传入，否则会把 `rotate_points_random`、`build_button` 内部的 float32 路径提升为 float64。
4. 位置参数仍传给原来的 `build_button`、`spawn_random_cube`、`spawn_random_bin`、`rotate_points_random`、`spawn_fixed_cube`、`build_board_with_hole`、`build_bin`、`build_gray_white_target` 及 RouteStick `_load_scene` 内联的障碍 builder。需要新增可选参数的具体位置：`spawn_random_bin` 内联的容器 yaw 常量 `* 90.0`（该函数被范围外任务共用，默认值必须保持）。`build_button.randomize_range` 的原值来源在两任务不同：BinFill 走被调函数默认值 `(0.1, 0.4)`，VideoRepick 在调用点显式传 `(0.1, 0.1)`。`build_button` 对 `generator=None` 无守卫、`spawn_random_bin` 与 `rotate_points_random` 亦默认 `generator=None`，新增签名时必须保留显式传参，并在④加"每个位置工具的 generator 实参非 None"断言。不替换工具、不事后移动已经生成的物体。
5. 不传配置时走原默认值。显式传入时必须校验完整性、字段、类型、单位和原区间表达形式；未知字段或缺失字段直接报错。**防漂移检查必须针对实际运行的源码：** `--check-config` 默认对当前工作树源码做 AST 提取并与 JSON 比对，`--source-ref` 仅作补充对照；生成时同时核对 JSON 内七份来源 SHA-256。只比对固定 ref 而不读工作树的检查发现不了运行源码被改坏。AST 不可直接达到的项需专用处理：BinFill 板位与 RouteStick 角度的 BinOp 表达式需专用模式匹配；`build_button` 默认值需跨文件解析；RouteStick `self.configs.get(..., self.config_easy)` 的兜底分支需显式记录。
6. 父进程读取一次配置，再把解析结果传给 worker；每个环境得到独立副本，不能修改类级共享 `configs`，不能影响同一进程的下一局。原版无实例级 config 属性，读点全部直接下标类级字典：BinFill 的 `_load_scene` 一处、RouteStick 的 `_load_scene` 一处、VideoUnmaskSwap 的 `__init__` 两处与 `_load_scene` 两处、VideoRepick 的 `__init__` 一处与 `_load_scene` 两处。实施时必须**全部**改为读实例副本，漏改任一处会产生"不传配置时相同、传配置时才发散"的隐性双真值，B/C 对拍抓不到。额外配置可作为运行目录中的独立 JSON 快照保存，原 HDF5、原 metadata 结构不改。
7. 配置读取、校验、提取和原子写入函数全部并入 `scripts/generate_dataset_newseed.py`，相关函数只使用标准库（`--source-ref` 允许通过 `subprocess` 调用 `git show`，`git` 不可用时报错退出，不降级）。四个 task 接收已校验的字典，在构造函数中取实例副本，不反向导入生成脚本。**导入顺序约束的正确因果链：** spawn 子进程会以 `__mp_main__` 重新执行主模块顶层，这早于 `_pool_init()` 写入 `CUDA_VISIBLE_DEVICES`；因此平铺后主文件的**顶层**以及被顶层 import 的任何模块都不得出现 `torch`、`sapien`、`cv2`、`robomme`，提取与合并所需的一切重依赖 import 必须放在函数体内。父进程是否导入并不直接影响子进程，但同样禁止父进程为提取配置导入 `robomme_env`。
8. `--sampling-config` 与 `--env` 的交叉行为：配置只含四任务时，其余 12 个任务走原默认值，不报错；配置内出现未知任务名或四任务缺失字段才报错。`--env all` 加 `--sampling-config` 必须可运行。

"位置分布"包含原锚点、偏移窗口和位置／旋转抽样输入。物体尺寸、材质、碰撞几何、相机、速度、交换时序、失败恢复和成功阈值属于原实现，不加入此次可改配置。**例外说明：** `cube_half_size`（来自 ManiSkill `PICK_CUBE_CONFIGS["panda"]`，四任务 `robot_uids` 均不在其键中故取 `panda` 项，值 0.02）同时是四任务 `min_gap` 的实际值、`bin_half_size` 收缩量与方块可行域收缩量的唯一来源，不是纯尺寸参数；本轮把它冻结为派生输入并记入快照，但不开放为可配。原有碰撞避让和重试仍决定最终位置分布，不能改成整场景筛选、分层采样或预先求好位置。

## 四、从当前四个 task 读出的参数候选

下表中 `{...}` 是为了便于人读而展开的候选集合，不意味着运行时改用集合采样。配置需保留源码的表示方式：`[min,max]` 区间、`*_min`/`*_max` 字段、固定值和原抽取方式。区间语义按来源区分：`configs` 内的 `[min,max]` 经原 `torch.randint(low, high + 1)` 消费，含两端点；直接写在源码里的 `torch.randint(a, b)` 为半开区间，不含 `b`。下表所有区间一律展开。

| 任务 | 难度 | 基线原字段与候选 |
| --- | --- | --- |
| BinFill | easy | `color=1`；`spawn_cubes=[4,6]` -> `{4,5,6}`；`put_in_color=[1,1]` -> `{1}`；`put_in_numbers=[1,3]` -> `{1,2,3}` |
| BinFill | medium | `color=2`；`spawn_cubes=[8,10]` -> `{8,9,10}`；`put_in_color=[1,2]` -> `{1,2}`；`put_in_numbers=[2,4]` -> `{2,3,4}` |
| BinFill | hard | `color=3`；`spawn_cubes=[10,12]` -> `{10,11,12}`；`put_in_color=[2,3]` -> `{2,3}`；`put_in_numbers=[3,5]` -> `{3,4,5}` |
| RouteStick | easy | `length=[2,3]` -> `{2,3}`；`backtrack=False` |
| RouteStick | medium | `length=[4,5]` -> `{4,5}`；`backtrack=False` |
| RouteStick | hard | `length=[4,7]` -> `{4,5,6,7}`；`backtrack=True` |
| VideoUnmaskSwap | easy | `bin=3`；`swap_min=1, swap_max=2` -> `{1,2}`；`pick_min=1, pick_max=2` -> `{1,2}` |
| VideoUnmaskSwap | medium | `bin=4`；`swap_min=1, swap_max=2` -> `{1,2}`；`pick_min=1, pick_max=1` -> `{1}` |
| VideoUnmaskSwap | hard | `bin=4`；`swap_min=2, swap_max=3` -> `{2,3}`；`pick_min=2, pick_max=2` -> `{2}` |
| VideoRepick | easy | `cube=3`；`swap_min=1, swap_max=2` -> `{1,2}`；`num_repeats` 来自源码 `randint(1,4)`（半开）-> `{1,2,3}` |
| VideoRepick | medium | `cube=3`；`swap_min=2, swap_max=3` -> `{2,3}`；`num_repeats={1,2,3}`，保留相同抽样表达式 |
| VideoRepick | hard | `cluster=True`、`swap=None`（两字段在源码中从未被读取，是死字段，不得赋予校验或运行语义）、`swap_min=0, swap_max=0` -> `{0}`；`num_repeats={1,2,3}`；原 `range(5)` 每轮红蓝绿各一块，总计 15 块 |

另有以下固定口径必须一起提取或记录，不能用旧版同名字段代替（"旧版"指 `newtask-v1` 的 `task_distribution.json`，其 `pick_count`、`spawn_count`、`target_color_count`、`swap_count` 等字段与原版同名不同义或折叠了 min/max 对）：

- `BinFill.dynamic` 在 `__init__()` 用 `bool(torch.randint(0,2,...).item())` 抽取，候选为 `False/True`。它是 `self.generator` 播种后的第一次抽样，先于场景抽样，完全由 seed 决定。目标颜色池的颜色允许分配到零次投入；原有逐色投入数和生成数分配逻辑继续执行。
- BinFill `_load_scene` 在配置字段之外还依次消费：`torch.randperm(3)` 选目标色池、`put_in_color`、逐色目标数或总目标数及其分配循环（变长 `randint`）、`spawn_cubes` 总数及分配循环、`torch.randperm(len(cube_tasks))` 打乱生成序。这些都在同一条 `self.generator` 上。
- `RouteStick.length` 是 `generate_dynamic_walk()` 的步数，结果包含起点，共 `steps+1` 个节点，不等同于转角数量。**起点本身是随机的**：调用不传 `start_idx`，`generate_dynamic_walk` 先 `torch.randint(0, len(indices))` 抽起点。原路线候选节点顺序为 `[0,2,4,6,8]`，障碍索引为 `[1,3,5,7]`；这些布局结构保持原样。
- RouteStick `_load_scene` 的随机消费顺序为：`theta` 一次 `torch.rand(1)` → 4 根障碍柱各一次 `torch.rand(3)` 随机颜色（共 12 个随机数）→ `steps` → 路线起点 → 路线各步 → `swing_directions`。障碍颜色这一段此前未被记录，漏掉会让其后全部取值错位。
- `RouteStick.swing_directions` 对每段依次执行 `torch.rand(1,...).item() < 0.5`，真时为 `clockwise`，否则为 `counterclockwise`。快照记录这一原方向候选与阈值，不改用 `randint` 或 `choice`。
- `VideoRepick` hard 的"15 块"是五轮原循环的结果；不能改成抽取 `spawn_count=[15]` 后统一生成 15 块，这会改变颜色排列与随机流。原颜色候选顺序为红、蓝、绿；每轮先 `randperm(3)` 打乱轮内顺序；easy/medium 仍保留原 `cube_colors` 长度为 4 的同色打乱操作，即使最后只生成 3 块。
- `VideoRepick.__init__` 含一行进程级全局副作用 `np.random.seed(seed)`，是全仓唯一的全局随机播种点，位于难度判定与 generator 创建之前。它必须原位保留、在快照登记、纳入④与⑤的检查面；第三节第 1 条的配置处理不得改变它相对其他语句的位置。
- `VideoUnmaskSwap` 的颜色顺序为红、绿、蓝；`_load_scene` 内有**两次独立**的 `randperm(3)`：一次打乱颜色顺序，一次选藏块容器索引（字面量 3 硬编码，`bin=4` 时第 4 个容器永远没有藏块）。其 generator 是 `__init__` 与 `_load_scene` 各自的局部变量，本类没有 `self.generator`，不得为统一接口提升为实例属性。BinFill 的生成颜色定义顺序为红、蓝、绿，`_initialize_episode()` 的任务颜色定义表为蓝、红、绿，随后各自由 `randperm` 决定实际顺序，定义表与 randperm 都保留。VideoRepick hard 由 `self.difficulty == "hard"` 分支进入，不能把原 `cluster` 字段重新解释成运行开关。
- 颜色、目标角色、目标顺序、最近邻交换对等继续由各 task 的原逻辑决定。它们可出现在来源清单中，但本轮不增加新的任务组合枚举器。

**疑似旧错误清单（只记录，不修复，实施时不得"顺手"改动）：**

- `RouteStick.__init__` 在按 `seed % 3` 推导难度的分支末尾无条件执行 `self.difficulty = "easy"`，覆盖刚算出的值；当前因生成器总是显式传 `difficulty` 而不生效，但任何不传 `difficulty` 的路径都会让 RouteStick 恒为 easy。
- `RouteStick.__init__` 创建了一个同 seed、创建后从未使用的局部 generator；真正使用的是 `_load_scene` 内另一个局部 generator。
- `VideoUnmaskSwap` 与 `VideoRepick` 的 `_select_swap_pair_from_positions` 是无调用者的死代码，内含 `torch.randint` 与惰性创建的 `self._swap_rng`，不影响当前随机流。
- VideoRepick `config_hard` 的 `cluster`、`swap` 从未被读取；VideoRepick `_load_scene` 中 `cube == 4` 的 `region4` 分支永不命中（easy/medium 均 `cube=3`）。
- `spawn_random_bin` 的碰撞检测把容器近似为轴对齐正方形，不使用刚抽出的 `z_rotation`。
- 源码注释 `3x3 grid`、`0-360 degrees`、`[-0.25, 0.25]` 均与实际不符，快照与本计划按实际记录。

来源锚点：四个任务文件的 `config_easy`、`config_medium`、`config_hard`、`__init__`、`_load_scene`、`_initialize_episode`，以及 [route.py](src/robomme/robomme_env/utils/route.py) 的 `generate_dynamic_walk`。

## 五、从当前 task 读出的位置分布

坐标单位为米。表中的连续区间按采样输入范围表示；`torch.rand` 的上界不包含在内。最终合法位置还要经过原对象尺寸收缩和原碰撞拒绝采样，不能把外框误当物体中心的最终均匀分布。

| 任务／对象 | 原位置与旋转输入 | 原消费位置 |
| --- | --- | --- |
| BinFill 按钮 | `center_xy=(-0.2,0)`；`randomize_range=(0.1,0.4)`（调用点未传，取 `build_button` 形参默认值）；`scale=1.5`；对应 x `[-0.25,-0.15)`、y `[-0.2,0.2)` | `_load_scene -> build_button`，`torch.rand(2)-0.5` 后逐轴乘范围 |
| BinFill 孔板 | x 按 `0.15+(u*0.2-0.2)`，范围 `[-0.05,0.15)`；y `u*0.4-0.2`；yaw `u*40-20` 度；几何 `board_side=0.1`、`hole_side=0.08`、`thickness=0.05` | `_load_scene` 内先 x、再 y、再 yaw 抽样，`build_board_with_hole` 只是位置接收方、内部无随机 |
| BinFill 方块 | `region_center=[-0.1,0]`；`region_half_size=[0.2,0.25]`；`min_gap=self.cube_half_size`（0.02）；`include_existing=False`、`include_goal=False`；yaw `[0,2*pi)` 弧度，每次拒绝采样尝试都抽 x、y、yaw 三个随机数 | `_load_scene -> spawn_random_cube` |
| RouteStick 标记与障碍布局 | 原布局为 `1 x 9`；中心 `[-0.1,0]`；x/y 间距各 `0.07`（`num_rows=1` 使 `grid_spacing_x` 对结果无影响，是死参数）；角度 `u*60-30` 度后转弧度；各点绕世界原点旋转 | `_load_scene` 的 `grid_center`、`grid_spacing_x/y`、`theta`；标记点经 `build_gray_white_target`，障碍柱经内联 `create_actor_builder` |
| VideoUnmaskSwap 容器布局 | 三角／直线三点候选或固定矩形四点；整体旋转参数 `(0,180)` **弧度**，绕坐标原点 (0,0)；每个锚点的 `region_half_size=0.07`；`min_gap=self.cube_half_size`（0.02，覆盖 `spawn_random_bin` 默认 0.05）；`spawn_random_bin` 没有 `include_existing`/`include_goal` 参数 | `_load_scene -> rotate_points_random -> spawn_random_bin` |
| VideoUnmaskSwap 容器自身 yaw | `[0,90)` 度；只在位置通过避让检测后抽取 | `spawn_random_bin -> build_bin` |
| VideoUnmaskSwap 藏块 | xy 直接复制对应容器的 xy（零偏移），z 取自身半边长 `cube_half_size/1.2`，yaw 固定 0，**不继承容器 yaw**；容器索引由 `randperm(3)` 决定 | `_load_scene -> spawn_fixed_cube`；不另加独立布局采样 |
| VideoRepick 按钮 | `center_xy=(-0.2,0)`；`randomize_range=(0.1,0.1)`（调用点显式传）；`scale=1.5`；对应 x `[-0.25,-0.15)`、y `[-0.05,0.05)` | `_load_scene -> build_button` |
| VideoRepick easy/medium 方块 | 原三角／直线锚点；整体旋转 `(0,180)` **弧度**，绕坐标原点；`region_half_size=0.07`；`min_gap=self.cube_half_size`（0.02）；`include_existing`/`include_goal` **未传，走默认 `True`**；方块自身 yaw `[0,2*pi)` 弧度 | `_load_scene -> rotate_points_random -> spawn_random_cube` |
| VideoRepick hard 方块 | `region_center=[-0.1,0]`；`region_half_size=[0.2,0.25]`；`min_gap=self.cube_half_size`（0.02）；`include_existing=False`、`include_goal=False`；yaw `[0,2*pi)` 弧度 | `_load_scene` 的五轮原生成循环 -> `spawn_random_cube` |

两个 Video task 当前定义的锚点按原顺序固定如下，不排序、不归一化、不平移：

```text
region3_tri  = [[-0.05,-0.1], [-0.05,0.1], [0.1,0]]
region3_line = [[0,-0.15], [0,0.15], [0,0]]
region4      = [[-0.05,-0.1], [-0.05,0.1], [0.1,0.1], [0.1,-0.1]]
```

位置实现来源：[object_generation.py](src/robomme/robomme_env/utils/object_generation.py) 的 `build_button`、`spawn_random_cube`、`spawn_random_bin`、`build_bin`、`build_board_with_hole`、`spawn_fixed_cube`、`build_gray_white_target`；[statechange.py](src/robomme/robomme_env/utils/statechange.py) 的 `rotate_points_random`；RouteStick `_load_scene` 内联的障碍 builder。这些工具内所有随机调用都带显式 `generator`，位置采样没有一处落到全局随机流。

方块中心区间由 `center - area_half + hs_new` 到 `center + area_half - hs_new` 计算；容器使用同形式的 `bin_half_size = (cube_half_size * 2.5 + 0.005) * 0.5` 收缩。`build_bin` 会无条件用 `cube_half_size * 2.5` 覆盖 `inner_side`/`wall_height` 入参，`spawn_random_bin` 又独立重算同一表达式，两处同源、必须同改。原 `avoid` 顺序、`min_gap` 实际值、`max_trials=256`、各调用点的 `include_existing`/`include_goal` 实际取值和失败处理全部逐调用点保留，不把这些判据改成位置配置的全局安全距离，也不按函数默认值统一填写。

`spawn_random_cube` 在 env 实例上维护 `self._spawned_cubes`、`self._spawned_count` 缓存，只在首次 `hasattr` 时初始化、从不清空；`include_existing=True`（VideoRepick easy/medium）且同一实例发生第二次 `_load_scene` 时，上一局的 actor 会留在避让集合中。这是真实的跨 episode 污染路径，纳入⑤的检查面。

## 六、保持原版行为的具体约束

1. **随机流及生命周期不变。** 完整表如下，不得合并成全局随机流或新增配置编译 seed：

   | 任务 | 创建位置 | seed 来源 | 形态 | 后续 |
   | --- | --- | --- | --- | --- |
   | BinFill | `__init__` | 形参 `seed` | `self.generator` 实例属性 | `dynamic` → `_load_scene` → 两次 `_initialize_episode`（含 recovery 的 `inject_fail_grasp`）连续消费，不重播种 |
   | RouteStick | `__init__`（死，未使用）；`_load_scene` | `seed` / `self.seed` | 均为局部变量 | `_load_scene` 内一次性消费完毕；`_initialize_episode` 不消费任务随机 |
   | VideoUnmaskSwap | `__init__`；`_load_scene` | `seed` / `self.seed` | 均为局部变量，同 seed 各自重播种 | `_initialize_episode` 主体不消费任务随机；另有死代码内惰性 `self._swap_rng` |
   | VideoRepick | `__init__` | 形参 `seed` | `self.generator` 实例属性；另有全局 `np.random.seed(seed)` | `num_repeats`/`swap_times` → `_load_scene` → 两次 `_initialize_episode`（recovery 时 `inject_fail_grasp`）连续消费 |

   **可复现前提必须写明：** ManiSkill 的 `_episode_rng` 与外层 reset 期的全局 torch 流不受 job.seed 控制；任务级结果可复现，完全依赖四任务与工具函数内**每一处** `torch.rand*` 都显式带 `generator=`，以及 `robot_init_qpos_noise=0` 使 `TableSceneBuilder.initialize` 的 `normal(0, 0, ...)` 恒为零。新增硬检查项：新代码中任何 `torch.rand`/`randint`/`randperm` 必须带 generator 且实参非 `None`；`task4recovery.py` 在 `torch_gen is None` 时走无 generator 分支，实施时必须保证传入。
2. **固定候选也照原方式消费随机数。** `randint(1,2)`、`randint(2,3)`、`randint(0,1)` 虽只可能返回一个值，仍照常调用。不能优化成常量赋值。VideoUnmaskSwap 即使最终使用四容器，也保留此前的 `region3_choice` 抽样；VideoRepick easy/medium 的长度 4 同色 `randperm(4)` 在语义上是空操作，同样保留。
3. **原版实际语义优先于注释。** `(0,180)` 不修成角度或 `[0,pi)`；BinFill 孔板位置按公式提取；RouteStick 按实际 `1 x 9` 和绕世界原点旋转记录。第四节"疑似旧错误清单"各项只说明，不顺手修复。
4. **执行期没有第二套逻辑。** 原 `task_list` 的 `func/solve/name`、示范与正式阶段、`NO RECORD`（task_list 内的记录门禁名称，不是 HDF5 字段）、求值次数、事件触发步、动作、失败恢复和记录策略保持不变。`recovery_mode` 是 episode 号的函数，其触发的 `inject_fail_grasp` 随机消费位置也保持不变。不得为比较方便新增 `evaluate()` 调用，它可能推进任务状态。
5. **原 seed 与难度调度不变。** 保留 `offset + env_code*env_block + episode*100 + attempt`（train 布局 `offset=0`、`env_block=1000`）、原难度循环默认 `211`、原 attempt 重试、`MAX_NON_TASK_STRIKES=3` 放弃规则、池崩溃插队及失败分类；保留 seed 天花板护栏（train 布局下单任务 episode 数超过约 10 即撞下一个 env_code 块并报错）。任务编号仍来自 16 任务规范序：四任务分别为 BinFill `4`、RouteStick `16`、VideoUnmaskSwap `5`、VideoRepick `9`，不能压缩成 1 到 4。其他 12 个任务不增加配置接入，但生成能力必须保留（第三节第 8 条）。
6. **原布局失败处理不变。** 不把逐物体避让替换成整场景重新采样；也不统一任务内部不同的 `break`（VideoUnmaskSwap）、跳过（BinFill）和 `SceneGenerationError`（VideoRepick）行为。三路对拍固定 `attempt=0`，attempt 重试分支不进 15 格，由单独的定向检查覆盖：用 `--max-attempts 2` 跑一个原版已知首次失败的用例，比较三路的失败分类与第二次 seed。

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

本轮只改文档与快照，上面的迁移与清理均未执行。保留原文件名，取消本计划 2.21 版曾设计的独立 `extract_native_config.py`、`generate_dataset.py`、`merge_dataset.py` 和 `src/robomme/sampling_config.py`（这四个文件从未创建，也不存在于 `newtask-v1`），不将辅助代码移到另一个新 Python 文件里。**恢复 2.21 版的护栏：不引入 `src/robomme_icl`，不迁移到 `scripts/legacy`，不复制 v1 的 suite、预生成场景、认证状态树或新的 HDF5 格式。** `src/robomme` 中原任务、规划器、wrapper 和测试目录不受"五个产品脚本"的数量约束；"无隐藏辅助实现"的判定口径为：`scripts/` 下除五个文件外无 `.py`，且产品生成路径不 import `tests/` 下任何模块。

### 两个文件的完整职责

| 最终文件 | 保留或迁入的内容 | 明确的依赖方向 |
| --- | --- | --- |
| `scripts/seed_layout.py` | 保留 `SeedLayout`、`LAYOUTS`、`env_code`、`get_layout`、`parse_difficulty_ratio`、`difficulty_for`、`plan_episodes`、`EPISODE_STRIDE`、`MAX_ATTEMPTS`；从旧 validator 迁入 `ALL_TASKS`、`MAX_EPISODES`、`DatasetContractError`、`parse_tasks` | 目标态仅依赖标准库；现状通过 `CONTRACT_DIR` 与 `sys.path.insert` 跨目录导入 `ALL_TASKS`（从而传递依赖 h5py/numpy），迁入后删除该段与随之失效的 `import sys`、`SCRIPT_DIR` |
| `scripts/generate_dataset_newseed.py` | 保留原 `EpisodeJob`、worker/进程池、规划回退、任务执行、metadata 与摘要；迁入下表的轨迹检查、原子写入和最小合并函数；新增同文件内的配置提取与校验 | 单向导入同级 `seed_layout`；保留原 NumPy/HDF5 顶层导入与线程设置顺序；仿真包仍在绑卡后由原 worker 路径导入 |

`ALL_TASKS` 必须保留原 16 任务顺序；`MAX_EPISODES=100`（现位于旧 validator）、`MAX_ATTEMPTS=100` 与 `EPISODE_STRIDE=100`（现位于 `seed_layout.py`）和原难度循环均不变，迁移时不得重复定义。只配置四任务不等于把规范序缩成四项；错误类型、任务排序和非法输入判定也照原函数保留。

| 旧来源 | 实际需要的内容 | 后续落点与处理 |
| --- | --- | --- |
| `data-generation/validate_generated_dataset_contract.py` | `ALL_TASKS`、`MAX_EPISODES`、`DatasetContractError`、`parse_tasks` | 迁入 `seed_layout.py`；主生成器从它导入。`DatasetContractError` 当前无主生成器消费者，只为 `parse_tasks` 保留原异常类型；不得把该模块的 `REPO_ROOT = ...parents[2]` 带入平铺文件 |
| 同一旧 validator | `TIMESTEP_RE`、`timestep_indices`、`inspect_episode_terminal` 及其 `re`、`h5py`、`numpy` 依赖 | 迁入主生成器，保持连续 timestep、`setup` 排除及末帧严格布尔完成检查；注意 RecordWrapper 冲突时会写 `timestep_N_dupK`，与 `TIMESTEP_RE` 不匹配，行为按原样保留 |
| `data-generation/write_generation_report.py` | `write_text_atomic` 及 `Path` | 只迁入这个函数体到主生成器；不搬完整报告器，不带入其顶层 `compare_joint_actions` 导入 |
| `data-generation-newSeed/merge_episode_h5.py` | `MergeError`、`_sources`、`merge_task(input_dir, output_dir, task, delete_source)`，其 `main()` 依赖 `parse_tasks` | 并入主生成器的 `--merge-only` 分支；保留按 metadata 找源文件、临时 HDF5 与原子替换、`--delete-source` 开关，不另保留合并脚本 |
| 原计划的配置辅助模块 | 纯源码提取、JSON 读取／校验、实例输入准备 | 实现在主生成器中；配置分支不导入环境，不采样；原四个 task 仅接收字典并取副本 |

原 `METADATA_ROOT`、完整官方数据审计／报告流程及历史 metadata 追加功能不属于这两个保留脚本的运行依赖，不因旧模块曾包含它们而整包迁入。可选合并仍在生成之后独立执行，默认不自动合并，不删除逐 episode 源文件。

### 同一个主文件提供三种入口模式

```text
scripts/generate_dataset_newseed.py::main()
  |
  +-- --extract-config <JSON>
  |      `--> 读取当前工作树源码（可选 --source-ref 对照固定提交）-> AST 原值提取 -> 检查或写出配置 -> 返回
  |
  +-- --merge-only
  |      `--> 原 _sources() -> 原 merge_task() -> 返回
  |
  `-- 常规生成（不指定上述模式）
         `--> 原 generate_dataset_newseed()
                +--> 同级 seed_layout.py
                `--> 原 _run_jobs / _worker / gym.make / reset / solve / close
```

`--extract-config` 与 `--merge-only` 互斥（argparse 互斥组）。现有 `--output-dir` 为 `required=True`，须改为非 required，并在分流后由常规生成与合并模式各自校验其存在；配置提取不要求 `--output-dir`、GPU 或 worker 参数。常规生成保留旧参数及默认值，在常规生成模式下仅增加 `--sampling-config`；合并模式沿用原脚本参数：`--input-dir` 必填、`--output-dir` 可选（默认同 `--input-dir`）、`--env` 默认 `all`、`--delete-source` 默认关闭。配置提取支持 `--source-ref` 与只检查不写入的 `--check-config`。分流放在启动进程池和环境导入之前，不把提取或合并塞进每个 worker。

当前 [native_sampling.json](scripts/configs/newtask-v2/native_sampling.json) 包含四任务全部 12 份难度字典、额外构造参数、位置输入、原始锚点、单位和七份来源 SHA-256（口径为文件字节 SHA-256，非 git blob）；本轮按第四、五节补录 `min_gap`、`include_*` 取值、遗漏随机流、按钮 `scale`、板几何、死代码标注与 anchors。`parameters`、`positions` 是后续显式输入；`native_semantics` 仅记录原语义；表达式字符串只作核查，核查方式为 AST 结构比较而非字符串比较，不执行 `eval`。后续同文件提取分支必须可重复导出相同原值。

### 平铺时必须调整的位置

1. 主文件从子目录移到 `scripts/` 后，`SCRIPT_DIR` 指向根 `scripts/`，`REPO_ROOT` 应由原 `SCRIPT_DIR.parents[1]` 改为 `SCRIPT_DIR.parent`；`SRC_ROOT = REPO_ROOT / "src"` 继续指向当前仓库源码。
2. 删除两文件的 `CONTRACT_DIR` 和旧 `data-generation` 路径插入，改为同级模块导入。现有循环同时把 `SCRIPT_DIR` 插入 `sys.path`，该插入保留，以便非脚本入口（测试的 `importlib`、`python -m`）也能解析同级 `seed_layout`。不能保留指向已删除目录的兼容分支，也不能让缓存模块遮掩缺失依赖。
3. `spawn` 继续从主生成器模块解析 `EpisodeJob`、`_worker`、`_pool_init`；入口保持 `if __name__ == "__main__"` 保护。主生成器只导入 seed 模块，seed 模块不反向导入。`EpisodeJob` 是 `frozen=True` 的 dataclass，新增配置字段后实例不可哈希；当前无哈希用法，字段以普通 dict 传递并在文档注明不得用作 dict key。
4. 四个 task 不导入 `scripts` 或主生成器。父进程检查配置后经 `EpisodeJob` 传普通字典，task 在原构造位置通过标准库复制为实例配置。
5. 原线程环境设置继续早于 NumPy 导入；绑卡继续早于 Torch/SAPIEN 导入，约束口径见第三节第 7 条。配置提取使用源码的 AST，不通过导入全部 task 读取默认值。
6. `parse_tasks` 抛出 `DatasetContractError`，而主生成器 `main()` 只捕获 `DatasetGenerationError`，`--env` 打错时当前为裸 traceback。迁移保持原样，不统一异常类型；若后续决定统一，须作为显式行为变更单列。

### 后续清理清单及顺序

| 现有路径 | 计划处理 |
| --- | --- |
| `scripts/data-generation-newSeed/` | 迁出两个核心文件；最小合并函数并入主文件；必要使用说明整理到根 `readme.md` 和本方案。目录内 `utils/` 三个辅助工具（`append_train_metadata.py`、`compare_with_metadata.py`、`calibrate_parallelism.py`，主生成器不依赖它们）、独立合并脚本、旧说明副本与 `reports/` 历史报告随旧目录退出当前工作树；退出前把 `reports/joint_action_diff_full.md` 中的一致性实测数字摘录进本计划附录或 docs |
| `scripts/data-generation/` | 先完成上表最小函数迁入、导入与轨迹检查验证，再删除旧复现／比较／报告链目录；同步修正根 `readme.md` 中指向 `scripts/data-generation/README.md` 的链接与 `scripts/data-generation/generate_dataset.py` 的示例命令 |
| `scripts/400ep-dataset/` | 清理旧扩展生成实录与辅助脚本；退出前把 `run-log.md` 中的单局耗时与 attempt 统计摘录进附录或 docs；指向它的引用只存在于同被删除的文件内 |
| `scripts/data-generation-MotionJEPALabel/` | 清理旧变体生成链；同步处理只服务该旧链路的测试与引用；`AGENTS.md` 中引用该目录下已不存在文件的举例一并修正 |
| `scripts/patternlock-routestick-params/` | 清理旧参数统计／可视化链及其报告 |
| `scripts/_icl/`、`scripts/legacy/`、`scripts/__pycache__/` | 三者均未被 Git 跟踪、内容全部为 `.pyc`，是切换分支遗留的编译缓存；核查实际清单后清理；不创建新的归档目录 |
| `.gitignore` | 删除指向 `scripts/data-generation-newSeed/outputs/`、`scripts/data-generation-MotionJEPALabel/outputs/`、`scripts/patternlock-routestick-params/outputs/` 的三条失效规则 |
| `scripts/configs/newtask-v2/native_sampling.json` | 保留，已有值不改；不是待删的旧目录或 Python 入口 |
| `scripts/dataset_replay.py`、`scripts/evaluation.py`、`scripts/run_example.py` | 保留在原位置，不重写运行逻辑；三者只依赖 `robomme.*` 与第三方包，不引用任何待删目录 |

清理限定于上述旧脚本和配套引用，不清理仓库外目录，也不扩大为根 `data/`、`artifacts/`、`runs/` 的数据清理。执行时先核对文件类型、符号链接、跟踪状态与实际产物；若清单中出现新的用户修改或未列出的生成数据，单列说明，不用递归删除顺带处理。已跟踪的旧脚本与报告可从固定 Git 历史追溯，历史账本不删除。

相关测试不能留下悬空导入：`test_seed_layout.py` 改为导入平铺的 seed 模块（顶层与 `difficulty_for` 的函数内二次导入两处都要改）；涉及保留生成路径的检查改为主文件中的对应函数。`test_append_train_metadata.py`、`test_no_patch_report_debug_environment.py`（同时导入 `generate_dataset`、`validate_generated_dataset_contract`、`write_generation_report` 三个待删模块）、`test_swap_clip_plan.py` 仅服务已删除功能，逐项核对后随旧功能退出；混合覆盖文件只调整失效部分，保留其他有效断言。不能通过整体跳过测试目录隐藏导入失败。`tests/_shared/dataset_generation.py` 及依赖它的 `tests/dataset/` 五个现有测试**保留不动**；它是会自动换 seed、另写求解循环的测试工厂，新增对拍测试不得使用它。

### 实施文件白名单

| 文件 | 计划改动 |
| --- | --- |
| `scripts/generate_dataset_newseed.py`、`scripts/seed_layout.py` | 从旧目录迁出，按本节分配并入必要函数；原 seed、执行和记录语义不变 |
| `scripts/configs/newtask-v2/native_sampling.json` | 本轮补录缺项；后续仅按源码校验，不改分布或候选 |
| `src/robomme/robomme_env/BinFill.py`、`RouteStick.py`、`VideoUnmaskSwap.py`、`VideoRepick.py` | 在原参数及位置读取处接入字典，不重写任务执行方法，不新增辅助源码文件 |
| `src/robomme/robomme_env/utils/object_generation.py` | 若旋转范围显式化确有需要，仅给 `spawn_random_bin` 增加保持原默认表达式的可选参数 |
| 对应 `tests/lightweight/` 与 `tests/dataset/` 测试 | 调整保留功能的导入，补必要的提取／输入／生成对照测试，处理删除功能的孤立测试 |
| `tests/_shared/` 中拟新增的对拍工具 | 新增文件仅承载测试观察器、证据编码、实测报告及离线比较；不被产品生成器导入，不复用现有 `dataset_generation.py` |
| 拟新增的 `docs/` 文档与轻量证据 | 后续保存通用规则、实测报告、冻结用例、指纹与压缩轨迹，逐路径纳入 Git；关键帧 PNG 不入 Git；本轮不创建。仓库现有 `doc/`（安装说明）与拟新增 `docs/`（验证留档）并存，用途不同 |
| 根 `readme.md`、`AGENTS.md`、`.gitignore`、本方案 | 更新平铺命令、说明、调用图、清理证据与失效规则 |

原规划工具、`RecordWrapper.py`、`DemonstrationWrapper.py`、各任务 `step/evaluate/_initialize_episode` 均保持原实现，不引入新的 ICL 层或记录格式。

## 八、实施步骤与验收判据

以下是用户后续允许实施后才执行的步骤，本轮止于方案交付。

### 第一步：固定基线并建立目标分支

复核源提交、目标分支是否存在及工作区状态，记录 `uv.lock` 的散列与实际依赖环境。从本方案固定提交创建 `newtask-v2`；如目标已经存在，停止创建并询问用户，不重置、不覆盖、不自行换名。带入目标分支的内容为：本方案、配置快照、`AGENTS.md` 中与 newtask-v2 相关的账本条目，方式为逐文件复制后并入首个 `10.0` 实现提交，不 cherry-pick、不合并源分支的文档提交。保留源分支和旧版分支。

### 第二步：平铺两个文件、并入必要依赖和提取功能

先将两个核心文件迁到根 `scripts/`，按第七节分配迁入所需函数并修正根路径、同级导入和进程启动。随后在 `scripts/generate_dataset_newseed.py` 内实现提取分支，可重复导出已提取的原值快照；按需合并也复用同文件内的原函数。此时先保留待删目录，以便做原版对照和核对依赖。

提取逐项覆盖四任务配置字典、构造函数的参数常量、场景位置表达式和工具默认值。`configs` 已有字段保持原名；原本散落的常量使用快照中的明确名称与单位。不得通过生成一批 episode 的观测频率反推"原候选"，也不得把历史生成 metadata 当作位置分布来源。

校验快照与当前源码的一致性。候选范围、布尔值、颜色顺序、锚点顺序和公式常量必须逐项相同。初版仅支持原来已经存在的区间／固定值表达方式；非连续新候选、额外权重和新拓扑不在本次实现范围。

### 第三步：接入原采样位置

按第七节白名单做最小修改，新增的数据流只走"入口配置 -> `EpisodeJob` -> 原任务配置"。不重排原采样语句和分支，不添加环境中间层。确认配置在原构造抽样前生效，且 worker 重用时没有跨 episode 共享可变数据。**此步之后工作区不再等于基线，A 路必须改用第一节所述 worktree。**

### 第四步：实现可复现测试，逐层完成五项重要对拍

①关键帧目视、②变量与物体变化、③HDF5 内容由用户直接提出；④随机流和⑤连续 worker 隔离经用户确认加入。五项均为"用户关心的重要对拍"，独立编号、独立保留证据和结论，不能相互替代。执行顺序上①依赖③：③ 通过的格才做①，③ 未通过的格不做目视。以后如需新增其他重要对拍，先询问用户是否列入，不自行扩大验收范围。

#### 4.0 共用基准、调用位置与观察器校验

- **A：固定原版**，来自第一节所述 detached worktree（提交 `94449db0a068a6b454b55a13ebd48f0394d89cc8`），入口为原路径脚本；**B：新版不传配置**；**C：新版显式传入冻结原值配置**。三路共用同一 `.venv`（基线与当前 `uv.lock` 相同）。同一用例固定任务、实际难度、episode、seed、attempt=0、GPU、依赖和原有参数，独立进程运行，分别比较 `A↔B`、`A↔C`、`B↔C`。
- 实际生成走各自原入口及原 worker，保留 `--workers 1 --max-attempts 1 --max-tasks-per-child 8`，记录内部实际 attempt。不得改用会自动换 seed、另写求解循环或改变判定的测试工厂（现有 `tests/_shared/dataset_generation.py` 即属此类，保留但不用于对拍）；不能只验证复制到测试中的生成逻辑。
- 观察器只在测试代码中包装原有调用，不新增 `evaluate()`、reset、随机抽样、渲染或物理步。**实际需要打桩的位置必须写明：** `torch.rand`/`torch.randint`/`torch.randperm` 的模块级包装（④）；各任务模块命名空间内的 `swap_flat_two_lane`、`highlight_obj`、`lift_and_drop_objects_back_to_original`、`lift_and_drop_objectA_onto_objectB`（②.3 事件，四任务用 `from .utils import *` 引入裸名，必须打在任务模块属性上，打在 `statechange` 上不生效且会静默产出零事件）；`subgoal_evaluate_func.sequential_task_check`（②.2 的求值返回细节，`evaluate()` 内部的 `current_task_name`、`task_failed` 不存到实例上）；`RobommeRecordWrapper.reset` 的返回值（①.1 初态，生成器丢弃了它）。显隐通过闭包内 `set_visibility` 实现、无持久状态，只能由外层函数入参推断。仿真为 PhysX CPU 单线程，读取 actor 位姿与速度无 GPU 同步副作用。逐步证据先缓存在内存，结束后写出，不改变产品 HDF5 格式或增加环境中间层。
- 每条证据记录"调用序号、环境实际步数、调用阶段、HDF5 记录编号"。原 `timestep_N` 来自记录缓冲区编号，不能直接当物理步数。`RobommeRecordWrapper.reset()` 不写入记录缓冲区，`timestep_0` 是第一次 `step()` 的产物，初态观测在 HDF5 中没有对应帧，只存在于②的构造期证据里。任务在观测返回之后发生的变化，注明首次进入后续原有观测的位置，不归入已经返回的画面。
- **每局登记规划器回退：** 观察器包住 `_planner_classes()` 生成类的 `move_to_pose_with_RRTStar` 入口，记录每局 `rrt_fallback_count`。依据：screw→RRTStar 回退在正常生成中常态触发；RRTStar 走 mplib/OMPL，`planning_time=1` 秒墙钟预算，且 mplib 的全局种子接口未暴露、IK 初值用未播种的 C++ 随机；历史记录显示同机同 seed 重跑约 1/20 的 episode 分叉。因此原版逐位可复现只对未触发回退的局成立。
- 正式比较前，做原版重复运行（同用例 A 路独立跑两次）及原版启用／关闭观察器的校准，比较动作、事件、完成状态和 HDF5。观察器改变结果时先修观察器。**确定性判据的退出路径（用户决策）：** A 路两次运行均 `rrt_fallback_count=0` 且逐位一致的用例，按逐位判据比较三路；任一次触发回退的用例标记"受阻-规划器非确定"，换同任务同难度同分支的其他 episode 补足，受阻用例保留记录不删除；若该格可用 episode 穷尽仍无未触发回退的用例，再由用户另定容差口径（本轮不预设容差，也不把"误差小"写成"逐位一致"）。

#### 4.1 重要对拍①：关键帧目视检查无区别

**①.0 前置。** 仅对③已通过的格执行；③未通过的格记"未验证"，不做目视。

**①.1 关键帧集合。** 分别提取 A、B、C 的首末帧、`is_subgoal_boundary`、演示切换、目标和完成／失败标志变化，以及物体创建、移除、抬起／回落、交换、显隐、高亮开始／结束等事件位置。三路取并集，每个边界保留前一帧、本帧、后一帧；越界明确标记，不只按新版选帧。不假设原版存在 `is_keyframe` 字段。初态使用观察器捕获的原 reset 返回观测，不额外渲染，并标注它不对应任何 HDF5 帧。

**①.2 对齐。** 先核对事件发生步、调用阶段和记录编号；缺帧、多帧、错位直接报差异，不平移时间轴、不找最近帧、不重采样以消除差异。

**①.3 出图与实际查看。** 从原始 RGB 数组（正面与腕部相机均为 256×256×3）导出原分辨率无损 PNG 到 `artifacts/`，正面和腕部相机分别排列 A／B／C 原图及差分图。标注任务、难度、seed、事件、步数和记录编号，逐图查看物体数量、颜色、身份、位姿、遮挡、机械臂及高亮效果。生成图版不代表已经目视。

**①.4 判据与证据。** 全部规定关键帧已查看、无可见区别，帧序和事件对应关系一致才通过。保留关键帧索引、逐图目视记录和像素差异统计入 Git；图版 PNG 留在 `artifacts/`，目视记录绑定图片散列，图片变化后旧记录不能直接沿用。任何像素差异仍交③处理，不能以"看不出来"认定 HDF5 内容一致。

#### 4.2 重要对拍②：变量跳变、物体位置及产生／消失过程不变

**②.1 构造与初态。** 在原构造抽样、场景加载、内部初始化及外层 reset 对应边界，比较任务参数、对象集合与创建顺序、颜色和角色、位置与四元数、机器人状态、目标绑定及 `task_list` 顺序。对象按名称、角色、创建序号对应，不按位置排序，以免掩盖物体交换。两次 `_initialize_episode` 分别记录。

**②.2 逐步状态。** 在原任务 `step()`、内部 `BaseEnv.step()`、原有 `evaluate()` 和 `solve()` 调用前后，记录任务索引、子目标、演示／特殊／成功／失败标志、目标对象与列表顺序、交换计划和计数器，以及所有任务物体的位置、旋转、速度、存在状态。比较实际动作、求值次数、参数和返回值。先从四任务及调用工具的状态写入处形成明确字段清单；不可序列化的任务状态须补提取方式，不静默省略。

**②.3 事件。** 每个事件记录对象身份、类型、发生步、调用阶段及变化前后值。区分真实创建／删除、视觉隐藏／恢复、移到视野外和普通遮挡，至少覆盖：

| 任务 | 必验变量与事件 |
| --- | --- |
| `BinFill` | `dynamic` 两分支；各颜色生成数和目标数；两次 `_initialize_episode` 的颜色顺序；抬起／回落及 `idx * 100` 边界；逐色投入和任务切换 |
| `RouteStick` | 路线起点、节点与摆动方向顺序；障碍颜色；目标按钮变化；轨迹标记、按钮高亮的创建／刷新／消失；失败锁存 |
| `VideoUnmaskSwap` | 容器与方块绑定（含无藏块的第 4 个容器）；初始抬起／回落；交换对象、起止步和临时选定对象；方块随容器移动及目标选择 |
| `VideoRepick` | `static_flag`、`start_step`、交换计划、目标和重复次数；hard 原五轮各自的颜色打乱、创建顺序及位姿，总计 15 块 |

**②.4 判据与证据。** 初态、逐步状态、事件次序和发生步、动作、轨迹长度及终态全部一致。保留压缩状态轨迹、事件和调用序列；首个分歧定位到字段／对象／调用阶段，并附前后上下文。不能只比末帧、成功率或候选字典。

#### 4.3 重要对拍③：HDF5 生成产物内容与原版一致

**③.1 文件和结构。** 比较文件、episode、group、dataset 的全集，以及 timestep 集合和数量（含可能出现的 `timestep_N_dupK`）；逐项检查 dtype、shape、字符串编码类型。原版 RecordWrapper 不写任何 HDF5 attribute，attribute 全集为空，比较时仍遍历以确认新版也为空。遍历实际落盘树，未知字段也比较，不只检查少数字段。

**③.2 全量内容。** 每个 timestep 的全部实际字段逐元素比较：`obs` 的 `front_rgb`/`wrist_rgb`、`front_depth`/`wrist_depth`、`joint_state`、`gripper_state`、`is_gripper_close`、`eef_state`、相机外参；`action` 的 `joint_action`/`eef_action`/`waypoint_action`/`choice_action`；`info` 的 `simple_subgoal`、`simple_subgoal_online`、`grounded_subgoal`、`grounded_subgoal_online`、`is_completed`、`is_video_demo`、`is_subgoal_boundary`；`setup` 的 `seed`、`difficulty`、`task_goal`、`available_multi_choices`、两相机内参。浮点同时核对原 dtype 下的位模式；字符串保留原值，不改写 JSON、不排序候选、不四舍五入。原版产物不含时间戳、路径、主机名等随运行变化的字段，视频编码也不写 `creation_time`。

**③.3 对应运行证据。** 将落盘记录与②捕获的原记录内容及阶段对应，检查漏帧、多帧、动作错位、事件标签提前／滞后或提前完成。末帧 `is_completed` 的严格布尔类型和值均一致。

**③.4 原始与合并文件。** 先比较每 episode 原始文件，再分别经原合并函数和新版迁入的同一逻辑生成任务文件，重复结构与内容检查。合并只做整组拷贝，不写自有字段。

**③.5 判据与证据。** 全部实际落盘内容一致才通过；仅结构相同、仅 joint action 相同或一次成功回放都不足。保存全字段结果、首个不同元素、差异数量；可量化字段的最大绝对差只作差异描述统计，不参与判定。不要求 HDF5 容器封装字节（group 默认 `track_times=True`）或带时间戳视频文件字节相同，但不得排除任何 HDF5 数据字段。原版失败而没有有效 HDF5，只能记失败行为对照，不能计产物一致通过。

#### 4.4 重要对拍④：随机抽样调用及随机流状态一致

**④.1 输入检查。** 四任务三难度原值与当前源码逐项一致，缺失／未知字段拒绝；加载、校验和复制配置前后已有随机流状态不变。

**④.2 调用检查。** 捕获实际随机调用的顺序、函数、上下界、shape、dtype、所属随机源、结果及前后状态。随机源口径覆盖三类：任务级 `torch.Generator`（含局部与实例）、全局 numpy 流（VideoRepick 的 `np.random.seed`）、全局 torch 默认流（`task4recovery.py` 无 generator 分支）。拒绝采样保留全部尝试，不只记录最终成功样本；单值区间仍消费原来的随机数。**盲区必须声明：** mplib/OMPL 规划器内部随机在 C++ 侧，Python 层不可捕获、不可播种，由 4.0 的 `rrt_fallback_count` 单独登记。

**④.3 生命周期。** 按第六节第 1 条的表比较 generator 创建、设 seed、重新创建及持续使用的位置，保留各任务局部／实例随机流边界、颜色和锚点顺序，不合并随机流；同时断言每个位置工具的 `generator` 实参非 `None`。

**④.4 判据与证据。** 对应调用序列、参数、抽样结果和状态全部相同；保留去重状态快照及首个分歧调用。不用抽样频率或最终位置相同代替随机流一致。

#### 4.5 重要对拍⑤：同一 worker 连续生成时配置互不污染

**⑤.1 类级与进程级状态。** 每次 attempt 都新建环境并 close，`EpisodeJob` 经 pickle 逐条送入 worker，实例级副本天然隔离；因此本项不验证"改一个副本其他不变"这种在多进程链路下恒真的断言，而是断言：四个任务类的类级 `configs`（及其三份难度字典）对象在整轮生成前后内容散列不变；父进程配置散列不变；`spawn_random_cube` 挂在 env 实例上的 `_spawned_cubes` 缓存在每个新实例上为空。

**⑤.2 真实连续运行。** 同一实际 worker（固定 `--max-tasks-per-child 8`）执行"用例甲→不同任务或难度的用例乙→再次用例甲"，保持原 seed 公式；乙至少含一局 VideoRepick 以覆盖 `np.random.seed` 的进程级副作用。逐局与对应独立 worker 运行比较，并以原版连续运行作参照；覆盖不传配置和显式原值配置两路，不能用三个独立进程冒充连续 worker。

**⑤.3 判据与证据。** 后续 episode 的配置、随机流、初态、事件及 HDF5 与相应独立运行一致，父配置前后散列不变。保留 worker 标识、执行顺序和逐局结果。

#### 4.6 必验矩阵、顺序与预算

用户已确认全部覆盖才完成，不采用"四任务 easy 即首版整体通过"的口径。

| 任务 | 完整生成必验格 |
| --- | --- |
| `BinFill` | easy／medium／hard，各覆盖 `dynamic=False`、`dynamic=True`，共 6 格 |
| `RouteStick` | easy／medium／hard，共 3 格 |
| `VideoUnmaskSwap` | easy／medium／hard，共 3 格 |
| `VideoRepick` | easy／medium／hard，共 3 格；hard 检查原构造中的五轮循环，不替换成五个独立 episode |

恰为 **15 个场景格**，每格分别登记①—⑤。按实际生效的难度和分支计覆盖，不只看 CLI。

**用例选择方法：** BinFill `dynamic` 可离线预判，不需要仿真：seed 为 `4000 + episode*100`（train 布局），`dynamic = bool(torch.randint(0, 2, (1,), generator=torch.Generator().manual_seed(seed)).item())`。难度不进入 seed，同一 episode 号的 `dynamic` 在三难度下恒定，因此 6 格须选两个 `dynamic` 取值相反的 episode，各以 `--difficulty 100`、`010`、`001` 跑三次。`--difficulty` 是三位数字的 easy/medium/hard 循环配额，`100` 表示全 easy，不是"难度 100"。用例先由 A 路按 4.0 的回退登记与重复性校准确认，再冻结进 `cases.json`；这仅用于选择覆盖用例，不用于反推原候选或位置分布。原版失败或触发回退的用例保留记录，另选同格其他 episode 补足，不自动换 seed 替代。

顺序为：定向轻量检查 → 原版重复性、回退登记及观察器校准 → `BinFill` easy 单局三路 → 其余 easy → 三难度及特殊分支 → 连续 worker。清理后复验放在第五步。先做三难度配置／初态覆盖，再登记完整生成，不将初态覆盖当完整执行通过。

**预算口径（用户决策，与 `AGENTS.md` 强制规则 3、4 对齐）：** 每次代码改动后的 smoke（单任务、单 episode、单 worker，加相关 `tests/lightweight/` 子集）总耗时不超过 5 分钟。15 格三路全量对拍、校准与连续 worker 视为长任务，按 `AGENTS.md` 规则 4 的模板以 tmux detached session 运行，日志经 `tee` 落仓库内 `artifacts/`，尾行写 `EXIT_CODE=`，用 Monitor 等待完成；按历史实测速率估算纯生成约 50–70 分钟。`tests/lightweight/` 全量实测 239–710 秒、`tests/dataset/` 约 880 秒，均超过单轮 smoke 预算，只在长任务窗口内运行。预算不足保留待验；单用例无法完成则记录受阻，不增加 worker、不缩短轨迹、不跳过原逻辑。

定向检查清单：配置提取与 `--check-config`、缺失／未知输入、同级 seed 独立导入、提取模式不加载仿真、`spawn` 传递、attempt 重试分支（第六节第 6 条）、`--env all` 加 `--sampling-config` 下其余 12 任务各一局 smoke、清理后无旧依赖。失败在固定基线复核，区分已有和新增问题（历史记录中全仓轻量测试存在 4 项固定基线上即失败的用例，须先列出清单），不通过整目录跳过隐藏失败。

#### 4.7 固化为可复现测试与三种操作

后续在 `tests/lightweight/` 实现配置、比较器和证据契约检查；`tests/dataset/` 实现原版重复性、观察器校准、三路及连续 worker 实测；`tests/_shared/` 新增文件只承载测试观察器、证据编码、报告和离线比较，不被产品生成器导入，不使用现有 `dataset_generation.py`。

比较器必须包含反例：关键帧单像素变化、错位或缺帧；对象身份替换、位置跳变、遗漏产生／消失事件；HDF5 缺字段、dtype／shape 或数值变化；少一次随机调用或状态不同；跨 episode 污染；证据损坏、来源不匹配和目视记录引用旧图。证明测试能拒绝这些错误，不只证明自身输出可读回。

| 后续操作 | 输入与要证明的内容 |
| --- | --- |
| 从头复现 | 冻结用例和固定源码，在新目录完整运行 A／B／C 并比较 |
| 当前代码回归 | 指定 Git 中固定原版证据，重新运行当前 B／C 并直接比较；不自动重生成或刷新旧基准 |
| 纯离线比较 | 显式给两份已有证据和新结果目录，不加载仿真、不占用 GPU；结论只适用于对应历史运行 |

拟用入口为 `uv run --no-sync python -m pytest tests/lightweight/test_native_sampling_config.py -q`、`uv run --no-sync python -m pytest tests/lightweight/test_native_sampling_evidence.py -q` 和 `uv run --no-sync python -m pytest tests/dataset/test_native_sampling_parity.py -q`。三路测试拟支持 `--parity-mode fresh|regression`、`--parity-cases`、`--parity-case`、`--parity-reference`、`--parity-output`，这些自定义选项须在 `tests/conftest.py` 通过 `pytest_addoption` 注册（现有两个 conftest 均无自定义选项）；离线入口拟为 `uv run --no-sync python -m tests._shared.native_sampling_parity compare --reference <证据包> --candidate <证据包> --output <新目录>`，须在仓库根目录执行（`tests/` 为命名空间包）。文件与参数均未实现，本轮不执行；后续报告须填真实有效、可直接复制的完整命令，不能把占位符当复现记录。

以下仅保留 C 路原生成器的拟用单局命令；A 路用 worktree 内的原路径入口、B 路用平铺入口，二者省略 `--sampling-config`，三路输出独立。**本轮不执行**：

```bash
command -v uv
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --output-dir artifacts/generated/newtask-v2/10.0/parity-explicit-binfill \
  --env BinFill --episodes 1 --episode-start 0 \
  --workers 1 --gpus 0 --layout train --difficulty 100 --max-attempts 1 \
  --max-tasks-per-child 8 \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json
```

Python 命令前先确认 `command -v uv`；所有 `uv run` 一律带 `--no-sync`，避免隐式同步 `.venv` 污染报告中的依赖指纹。对照工作副本、生成数据与报告均放仓库内，官方参考保持只读，输出不复用旧实验。

#### 4.8 后续重要测试／生成统一写 docs，保留实测与轻量证据

**后续实施时才将本小节的通用约定写入 `AGENTS.md` 并建立 docs。本轮只改本计划，不创建这些文件。** 以后用于重要验收、回归、一致性判断的测试和生成，都须保留可复现入口、实测文档及轻量证据；成功、失败、中断、超时和未覆盖项如实记录。只有聊天、终端输出或临时缓存不算留档完成。不追补所有历史实验，不扩大旧产物清理范围。

用户已确认**文档及轻量证据纳入 Git，关键帧 PNG 全部不入 Git**。完整 HDF5、视频、详细日志与全部 PNG 图版留在仓库内 `artifacts/`，Git 只入指纹、目视记录与压缩数值证据，不提交大型产物（与 `AGENTS.md` 禁止提交图片、视频、HDF5 的规则一致）。目标结构如下，当前未创建：

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
        evidence/                   去重后的轻量证据（无 PNG）
```

每次重要运行用独立 `<UTC时间>-<主题>-<短源码版本>` 编号，冲突加序号，非空输出拒绝覆盖。显式指定基准，不默认选最新；更新另建版本并解释原因，测试失败不能自动刷新期望值。`cases.json` 在原版选定用例后冻结实际 seed、episode、difficulty、分支、`rrt_fallback_count` 和覆盖关系，不以候选版结果挑选有利样本。

清单记录源码提交、实际导入源码、测试实现、未提交差异、配置及输入指纹，实际依赖与锁散列、设备和必要环境。证据内部用包内或仓库相对路径；绝对工作目录只作执行记录，不成为读取依赖。来源和环境不匹配必须明确报告，不能把环境变化直接归因于代码。

每份实测报告必须写清：

1. 目的、重要对拍编号、参考与候选、与上一轮的关系。
2. 源码和差异指纹、配置、输入、实际依赖及设备。
3. 完整命令、工作目录、tmux 会话名、起止时间、耗时、退出码与输出目录。
4. 实际 seed、attempt、难度、分支、`rrt_fallback_count`、worker、GPU 及执行顺序。
5. ①—⑤逐用例结果和实测帧数、事件数、字段数、差异数。
6. 首个分歧、必要上下文、原因是否确认、失败或受阻及未覆盖项。
7. 证据索引、实际文件数与体积、完整产物与 PNG 位置、重跑和离线比较命令。

未运行不填预期数字，不能从候选配置或打印的成功消息推断数据一致。后续实际命令从运行记录写入报告，而非只保留泛化模板。

| 轻量证据 | 保存方式 | 后续可直接比较的内容 |
| --- | --- | --- |
| 配置、用例和来源 | JSON | 输入与运行条件 |
| 数值状态、位姿、动作 | 原 dtype 的压缩数组 | 逐元素差异、首个分歧及幅度 |
| 任务与物体事件、调用次序 | 压缩结构化序列 | 身份、类型、发生步、阶段和前后值 |
| 随机流 | 调用记录及去重状态快照 | 抽样次序、参数、结果和状态 |
| HDF5 全字段 | 结构和内容指纹；小型字段另存原值 | 全字段相等性及差异字段／记录定位 |
| 全部规定关键帧 | 每帧内容 SHA-256 与像素差异统计入 Git；原分辨率无损 PNG 留 `artifacts/` | 相等性判断；目视需回到 `artifacts/` |
| 目视记录 | 检查人、结论及绑定图片散列 | 是否检查本次证据 |
| 失败信息 | 首个差异、必要上下文和关键日志摘录 | 复现与定位 |

只用无损压缩、内容去重及去掉完整视频／全帧图像实现轻量化，不降低精度、不遗漏必验事件。A、B、C 相同内容引用同一份证据。HDF5 指纹按版本化规则纳入字段路径、dtype、shape 和原始内容；浮点保留位模式，字符串逐元素编码，不散列对象地址或容器封装字节。

**能力边界必须写明：** 指纹能判断帧是否相同并定位字段／记录，但不能还原画面或计算像素差幅度；需要展开时按冻结命令重跑原版，或从 `artifacts/` 中按散列取回 PNG。轻量包不能称作完整 HDF5 备份。

状态区分"通过、失败、受阻、未验证、待目视"五态；"待验"统一写作"未验证"。原版不稳定（且无法按 4.0 退出路径补足）、缺证据或未目视时不得整体通过；历史包比较通过不得写成当前代码回归通过。最后将 Git 中的文档和证据复制到同一仓库内的另一个目录，不访问原运行目录、不加载仿真，完成离线比较以证明不依赖临时缓存或绝对路径。

### 第五步：按清单清理旧目录并验证最终结构

两个平铺文件的导入、配置检查和最小生成对照通过后，再执行第七节的具体清理清单。先迁入必要函数和说明，更新保留测试的导入，摘录待删报告中的历史实测数字，再删除退出的旧链路和它们专用的孤立测试；不先删目录后靠逐个报错找依赖。

清理后核对 `scripts/` 下产品 Python 文件集合恰为 `dataset_replay.py`、`evaluation.py`、`run_example.py`、`generate_dataset_newseed.py`、`seed_layout.py`；无旧目录运行依赖，无新包装入口，产品路径不 import `tests/`。配置 JSON 保留。**清理后复验范围（用户决策：抽样复验）：** 每任务 easy 一格 B/C 重跑并与清理前证据比较，加定向检查（导入、提取、`--check-config`、无旧依赖、12 任务 smoke）；其余 11 格沿用清理前证据，报告逐格记录证据来源与对应源码版本。仍按 smoke 预算与长任务口径记录通过与未覆盖项。

### 第六步：核对范围并提交 10.0

15 格五项重要对拍逐格登记完成（通过，或按 4.0 退出路径记为"受阻-规划器非确定"并附补足用例）、目视记录齐全、证据完整可读、离线比较可复现，且抽样复验对应清理后的源码后，完成实施验收。受阻清单齐全即可提交，不因存在受阻格阻塞 10.0。随后以 `10.0 显式接入四任务原版位置分布与参数候选` 作为首个实现提交标题；提交正文保留用户要求、完整计划、实施差异、测试命令与结果。仅逐路径提交本轮源码、测试、文档与轻量证据，不提交完整 HDF5、视频或 PNG。未完成验证保留未验证或受阻，不降低标准宣称完成。

交付时给出：冻结配置、与固定基线的最小 diff、最终五脚本清单、函数迁入对应表、更新后的 ASCII 图、15 格覆盖矩阵及每格 `rrt_fallback_count`；①关键帧目视记录、②状态／事件对照、③原始与合并 HDF5 全字段比较、④随机流报告、⑤连续 worker 隔离报告；真实命令、tmux 会话、退出码、轻量证据索引、全部失败与受阻证据和未覆盖项。首版验收覆盖原值显式注入、原链保持及用户确定的平铺清理，不包含修改分布、扩大候选或全量数据生成。

## 九、后续使用方式：提取配置，再生成 dataset

下列平铺与新增模式尚未实现，命令仅供审阅完整操作流程，**本轮不执行**。三种操作均使用同一个主文件；生成示例是最小单任务单局，通过后才能按第四步的验证覆盖逐步扩大为四任务数据集，不预设全量条数。`--difficulty` 为三位 easy/medium/hard 循环配额，`100` 表示全 easy，medium、hard 分别用 `010`、`001`。

```bash
command -v uv
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json \
  --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8 \
  --check-config

uv run --no-sync python scripts/generate_dataset_newseed.py \
  --sampling-config scripts/configs/newtask-v2/native_sampling.json \
  --output-dir artifacts/generated/newtask-v2/10.0/smoke-binfill \
  --env BinFill --episodes 1 --workers 1 --gpus 0 \
  --layout train --difficulty 100 --max-attempts 1

uv run --no-sync python scripts/generate_dataset_newseed.py --merge-only \
  --input-dir artifacts/generated/newtask-v2/10.0/smoke-binfill \
  --output-dir artifacts/generated/newtask-v2/10.0/smoke-binfill-merged \
  --env BinFill
```

提取命令不带 `--check-config` 时导出快照；带此参数时只核对既有快照（默认对当前工作树源码，`--source-ref` 额外对照固定提交）。常规生成沿用原格式输出 `hdf5_files/`、`videos/`、`episode_results.jsonl`、各任务 `record_dataset_<Task>_metadata.json`、`run_parameters.json` 和 `run_summary.json`；需要每任务一个文件时，再显式调用同文件的 `--merge-only`，得到 `record_dataset_BinFill.h5` 等文件。合并保持按需，不在生成后自动执行。生成 seed 仍来自原 `--layout` 公式，不自行创建新 seed 体系或改变位置、候选数值。

## 十、本轮交付检查

历史静态检查：原版 JSON 已提取，曾核对 12 份难度字典、6 个布局数组和 7 份来源散列；前两轮平铺与对拍计划检查了 4 条主文件命令、2 个命令围栏及 6 个文件链接，退出码 0。这些是历史文档／配置核查，不能作为新对拍已实施的证据。

本轮（2.24）依据 11 路对抗审查修订：补齐随机流清单与疑似旧错误清单、改写 seed 入口与两次 reset 的说明、修正第三节导入顺序因果链与防漂移检查对象、补录快照缺项、按用户决策改写确定性退出路径、预算口径、PNG 留档、①与③顺序、旧测试工厂去留、12 任务保留范围、A 路来源与清理后复验范围。本轮修改 `NEWTASK_V2_PLAN.md`、`native_sampling.json`（只增不改）、`AGENTS.md` 三个文件；没有执行新生成器、真实对拍、仿真、合并或旧目录清理，未创建分支或 worktree。五项测试、15 格实测、docs 和轻量证据均仍未实施；本计划交付不代表实现或验收完成。

本轮文档核对项：差异仅限三个文件；五项编号、15 格覆盖、未来测试入口和证据留档相互一致；现有文件链接、围栏、命令语法及 `git diff --check`；JSON 可解析、七份来源散列与 12 份难度字典未变、新增字段与本计划第四、五节一致；计划正文无绝对路径、第一节不含以远端引用为基线的断言；源码、测试、依赖不变。静态检查仅验证文档与快照，不能计入五项重要对拍的通过数量。检查程序随本轮提交正文保存，实测结果在提交正文记录。

## 十一、实施记录（目标分支副本，随实施更新）

本节只在 `newtask-v2` 上追加，源分支副本不再修订。

### 10.0 与计划的差异

1. **提交编号拆分。** 计划第六步要求 15 格对拍验收后才提交 `10.0`；`AGENTS.md` 强制规则要求每次改动跑过测试即提交，不得把数小时工作堆在工作区。按后者执行：`10.0` = 平铺 + 四任务接入（smoke 通过后提交），`10.1` 起承接对拍框架、实测证据、清理与范围核对。首个实现提交仍是 `10.0`，验收结论落在最后一个提交。
2. **快照按第三节第 3 条改写折算字段。** `positions.VideoUnmaskSwap.containers.yaw_range_deg: [0, 90]` 是把源码 `u * 90.0` 折算成的区间，已改写为运算元形式 `yaw_scale_deg: 90.0`，并作为 `spawn_random_bin` 新增可选形参的默认值。另两处 `yaw_range_rad` 是 `spawn_random_cube` 内部硬编码的 `2 * np.pi`，运行时不被消费，保留为说明性字段并在校验器中按说明字段处理。
3. **新增 `parameters.RouteStick.configs_fallback_difficulty`。** 原 `self.configs.get(..., self.config_easy)` 的兜底分支按第三节第 5 条显式记录，取值 `"easy"`。
4. **两处 `*_origin` 说明更新。** BinFill 按钮的 `randomize_range` 与 VideoRepick easy/medium 的 `include_existing`/`include_goal` 原本走被调函数默认值、调用点未传；接入后由快照显式传入（取值不变），说明文字随之更新。
5. **原值提取的落点。** 四个任务模块顶层各有一份 `NATIVE_SAMPLING` 字面量，它同时是不传配置时的运行默认值与 `--extract-config` 的 AST 提取目标，因此不存在「提取值」与「运行值」两套真值；难度字典仍只在类属性 `config_easy/medium/hard` 一处。`--source-ref` 走独立的旧式提取器，从基线的内联源码还原操作元子集（61 项），用于证明接入没有改动原值。

### 10.3 第五步清理的实际范围

按第七节清单执行，`scripts/` 下的产品 Python 文件集合已恰为
`dataset_replay.py`、`evaluation.py`、`run_example.py`、`generate_dataset_newseed.py`、
`seed_layout.py` 五个，加上 `configs/newtask-v2/native_sampling.json`，目录内再无其它 `.py`。

| 处理对象 | 实际处理 |
| --- | --- |
| `scripts/data-generation-newSeed/`、`scripts/data-generation/`、`scripts/400ep-dataset/`、`scripts/data-generation-MotionJEPALabel/`、`scripts/patternlock-routestick-params/` | `git rm -r` 删除（合计 72 个被跟踪文件），残留的 `__pycache__` 一并 `rm -rf` |
| `scripts/_icl/`、`scripts/legacy/`、`scripts/__pycache__/` | 未被 Git 跟踪、内容全部为 `.pyc`（共 26 个），核查后 `rm -rf` |
| `.gitignore` | 删除三条失效规则及随之孤立的注释 |
| 根 `readme.md` | Data Generation 一节改指平铺入口，补上 `--extract-config` / `--merge-only` / `--sampling-config` 三种用法与 `--difficulty` 语义说明 |
| `tests/lightweight/test_append_train_metadata.py`、`test_no_patch_report_debug_environment.py`、`test_swap_clip_plan.py` | 三者在模块导入期就依赖已删目录（分别是 `utils/append_train_metadata.py`、`generate_dataset`/`validate_generated_dataset_contract`/`write_generation_report`、`clip_plan`），随旧功能退出 |
| `tests/_shared/dataset_generation.py` 与 `tests/dataset/` 现有测试 | 按方案保留不动；`tests/dataset/test_record_stick.py` 只在注释里提过旧脚本，无导入依赖 |
| 历史实测数字 | `reports/joint_action_diff_full.md` 与 `400ep-dataset/run-log.md` 的关键数字退出前已摘录进 [docs/validation/newtask-v2/legacy-measurements.md](docs/validation/newtask-v2/legacy-measurements.md) |

`tests/_shared/parity_runner.py` 里的 `BASELINE_ENTRY` 仍是旧路径，这是**基线 worktree 内**
（固定在 `94449db`）的入口，不随当前工作树的清理失效，已在源码注释里写明。
`scripts/generate_dataset_newseed.py` 与 `seed_layout.py` 的文档字符串保留了迁移出处说明，
属于沿革记录，不是运行依赖（`seed_layout.py` 的实际 import 已由测试按 AST 断言只有标准库）。
