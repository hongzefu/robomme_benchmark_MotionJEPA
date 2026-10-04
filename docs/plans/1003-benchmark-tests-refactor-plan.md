benchmark 全部关键契约的测试重构计划（2026-10-03）

> 结论：当前测试没有完整覆盖 benchmark。目标是重新设计测试的正确性依据、覆盖范围和执行方式，而非只整理目录。
>
> 本文是 [代码与测试维护计划](../../1003-code-test-maintenance-todo.md) 第四节的详细方案；测试设计、资源预算和测试验收以本文为准。代码清理、HF 上传和批量生成继续属于原计划的独立事项，不因本次测试设计而启动。
>
> `PLAN_BASE=86e5a015b7ba3a85c2c03cc50f5de482b9476c1d`（12.377）；工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`。本轮只完成研究、CPU 探针和计划，尚未实施重构。测试可彻底重写，但生产修复不随测试授权自动获准；受保护源码仍按 P2 逐项处理。
>
> 外部锚点：MME gitlink `ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b`；SimpleMemVLA gitlink `c564c17d276d7294200122b286c21901a3bfb99f`；ManiSkill 依赖 `07be6fbc66350ddca200abfb0a11b692f078f7fd`。官方字节来源沿用 `src/robomme_hard/UPSTREAM.json`，实施时核全量指纹，不从移动分支刷新。当前 SimpleMemVLA 脏工作区、HF 发布留档在途内容均排除。
>
> 用户本轮原话：
> 「/data/hongzefu/robomme_benchmark_MotionJEPANewTask/1003-code-test-maintenance-todo.md现在的test是否完全覆盖了所有所有的内容就是你可以破坏性的对整个test进行修改我需要覆盖所有关键都是正确的。然后都尽可能不要跑GPU的任务如果有GPU任务就只做一个最简单的初始或者reset这样的 可以彻底重构这个test你可以派出SubAgent确定方案也可以实测然后再给我一个重构的计划我希望重构完的test能够覆盖这个benchmark的所有部分」
> 「就是你可以结合现在的test作为蓝本根据你对于一个正确项目的test应该怎么设计的一个思想完全重新设计这个test。」

# 第一部分（给人看）

## 一、总览与已定口径

一句话方案：从全部现行生产模块建立契约清单，用真实生产方法的 CPU 正反例、真实组件集成和定点破坏验证守住契约；保留旧测试里有价值的反例，删除自证和失效用例，真实 GPU 检查完全独立。

1. **范围覆盖整个 benchmark**：`src/robomme/`、`src/robomme_hard/`、四个公共脚本、生成与评估设施、对拍和噪声判据、`challenge_interface/`、站点与媒体、打包安装、元数据及依赖来源。详见第二节矩阵。第三方只核本仓库依赖的接口，不接管第三方全部测试。
2. **先证明测试有用，再谈全绿**：每项关键契约都有独立期望、正常输入、拒绝输入、边界或阶段切换，并有指定故障能让测试失败。详见第三、五节。
3. **默认 CPU，不创建真实仿真场景**：收集前隔离 GPU 目录，资源守卫覆盖运行及子进程。CPU 替身环境的 `reset/step` 不计为真实仿真；真实环境构造、原生 reset、规划、模型权重加载和外网均不属于核心档。详见第四节。
4. **旧测试是素材，不是需求上限**：旧 nodeid 去向只验证迁移，新增契约清单才判断此前漏掉的功能。按调用与契约裁决，不能按 `v7/v8/audit` 文件名删测试。详见第六节。
5. **测试失败不能靠降低要求消除**：区分错误期望、实际生产问题、官方兼容行为与任务语义冲突。受保护生产源码先保留红灯与证据，另列修复清单。详见第五节。
6. **不改正式身份与评估数据**：seed、场景、五份交付规格、main 评估口径、正式结果、步数上限保持既定值。当前代码没有独立 `test-hard0` dataset，它只是未来接口；现在测试的是默认关闭的 xhard0 前缀。
7. **不会用测试通过宣称物理和模型全部正确**：全部责任必须登记；CPU 可验证的责任要实测，依赖真实物理、GPU、模型权重的部分明确列未验证。详见第二部分盲区。

### 本轮已取得的证据

固定提交有 **109 个测试文件、1106 个 `test_` 函数定义**，后者不是参数展开后的用例数。生产 Python 范围为 `robomme` 54、`robomme_hard` 62、`scripts` 71、`challenge_interface` 9，共 196 个文件；实施时还要把 shell、HTML、JSON 和包内资产加入清单。

| 本轮检查 | 实测结果 | 意义 |
|---|---|---|
| 4 文件 CPU 冒烟 | 29 passed，0.82 秒，退出 0 | 合成 HDF5、seed、摘要比较、导入边界局部可用 |
| 7 文件 CPU 契约选集 | 192 passed，9.12 秒，退出 0 | 当前规格、builder、清单、报告、噪声已有局部回归 |
| 语言与错误处理 2 文件 | 27 passed、4 failed，1.01 秒，退出 1 | 过期期望和源码扫描问题仍存在 |
| 3 个 main-only 文件收集 | 0 项，0.17 秒，退出 5 | 完成标志、waypoint 生命周期、去重没有进入 pytest |
| 6 个独立反例 | 全部复现漏检 | 现有测试通过不足以证明判据正确 |

6 个反例：`noise_gate::classify_pair` 将两个空 `.h5` 判 `byte_equal`；`hard_specs::validate_specs` 接受 `candidate=True`、`attempt=0.5`、浮点 seed；`gate_set::check` 对零字节冻结 JSON 输出 `GATE_SET=PASS`；`compare_h5_pair` 漏掉 HDF5 根属性变化，`sha_equal=0` 但 `field_mismatch=0`。其中 `byte_equal` 是字节关系，不能单独作为合法产物判据；新测试应把有效性与比较关系分开。

本轮没有执行 GPU 初始化、真实 reset、轨迹或模型推理；没有全量运行旧套件，也没有测出全项目行／分支覆盖率。命令、退出码和原始小证据见 [本轮验证记录](../validation/test-reconstruction-20261003/README.md)。

## 二、把“所有部分”变成可检查的契约矩阵

`tests/contracts/benchmark_contracts.json` 是拟新增的需求清单，不能由现有测试文件反推生成后直接宣布完备。先从生产入口、模块、公共符号和分支登记，再由独立审查核对遗漏。每条记录包含 `id/source/symbol/oracle/positive/negative/boundaries/nodeids/resource/mutants/status`；状态区分 `planned/verified/blocked/conditional/not_run`，缺测试或缺执行证据不能填 `verified`。

| 编号 | 生产责任与符号锚点 | 新测试必须实际守住的内容 |
|---|---|---|
| C01 | 两包 `__init__`、注册表、shim | 官方独立进程、hard 独立进程、两种导入顺序；16 ID 精确集合、类与函数归属；错指向与污染拒绝 |
| C02 | 两个 `BenchmarkEnvBuilder`、`episode_config_resolver` | train/val/test/test-hard、16 任务；四个 Unmask train 覆盖；元数据优先级；非法 dataset/action/episode；真实传给构建边界的 seed、difficulty、spec 和开关 |
| C03 | `hard_specs`、`seed_layout`、`resolve_identity` | 类型、schema、canonical hash、未知键、重签后语义校验；candidate/attempt/seed 整数；身份双向映射、顺序、缓存隔离、跨档无碰撞 |
| C04 | `sampling_config`、各任务 `native_blocks`、`SpecRecorder/spec_binding` | 16 任务默认配置；native 冻结；合法收窄与非法范围；RNG 消费不漂移；冻结值实际消费、未消费拒绝、深拷贝、输入输出不别名 |
| C05 | 16 原生与 hard 任务 `evaluate/step`、任务列表 | 本节后面的逐任务真值表；原生与新值分别覆盖，不用 hard 用例冒充原生覆盖 |
| C06 | `sequential_task_check`、失败强制转换、计时与场景运动 | 失败优先、一次只推进一项、首末项、切换许可、缓存清除；CPU actor 姿态首中末帧，演示数据不污染执行 |
| C07 | `task_goal`、动作匹配、投影、route/adjacent、OBB/SAT | 目标语言与实际对象/次数/方向绑定；独立几何算例、阈值等号、对称与平移性质、不可达路径、可见性、非有限输入 |
| C08 | 四 action wrapper、`_augment_obs_and_info` | joint_angle/ee_pose/waypoint/multi_choice；真实 shape/dtype、CPU Tensor→NumPy；8 个开关全部256组合及强制相机交互；字段长度、无原地污染 |
| C09 | `DemonstrationWrapper`、`planner_denseStep` | reset 的演示与初始动作时序；NO RECORD、演示→在线、重复文案不同 index、终态额外底层步；异常恢复钩子；真实规划边界替换为 CPU spy |
| C10 | `RobommeRecordWrapper.step/close/reset` 及 `_video_*` | 真实写入→关闭→h5py→resolver；视频开关与H5独立性；is_completed、terminated/truncated、info.success、episode_success互不替代，不新增H5字段；跨局缓存、幂等关闭、FK失败；真实视频合成/overlay/命名/编码失败 |
| C11 | `EpisodeDatasetResolver`、`dataset_replay::_build_action_sequence/process_episode` | timestep数字排序、稀疏/缺失、演示过滤、joint/ee/choice/waypoint；相邻去重而非全局去重；序列与resolver同一独立夹具核验；真实process_episode的动作顺序、obs=None错误输出、终态/timeout、关闭异常与结果标签 |
| C12 | `_draw/_extract/_freeze/_rollout`、追加与子集 | 抽签预算、选签与采样来源、真实 run_batch 消费；重复/额外/错绑定拒绝；旧 tried＋新结果中断恢复；零计数字段序列化；累计预算与不重复执行 |
| C13 | 评估 client/server、`SeatRunner`、recorder、manifest/report、两个evaluation入口 | 真实packaged identity→清单→客户端→记录器→账本→报告；独立task_success与分母；动作转换、首推理、A→B→A隔离；普通失败不重试；唯一接受与必填身份；入口错误分支outcome和清理，以测试子进程实际执行 |
| C14 | `challenge_interface` 的 client/server、HTTP、codec、`Policy`、`phase1_eval` | 真实 WebSocket/HTTP handler；reset/infer 协议、断连/超时/非法回复；NumPy shape/dtype/端序；精确成功状态与固定分母；异常清理、reset 等待有限结束 |
| C15 | train/hard 比较器、`gate_set/noise_gate/hard_regression` | 空文件/空集拒绝；实际身份集合相等；逐帧结构、根与组属性、group↔dataset；动作与状态 finite；1 ULP、RGB/depth/完成字段；独立参照来源与有限噪声结论 |
| C16 | 席位与接续 shell、锁、watchdog | 真子进程＋假引擎；端口占用、server 先死、首推理超时、TERM/KILL、重启预算、收尾与接续幂等；真实 JSON 生产者到真实守卫，不能打印 PASS 替代 |
| C17 | site catalog/subgoal/semantic/transcode、HTTP、HTML | 独立身份表、连续段和演示过滤；语义标签与真实差异；微型媒体转换；HEAD/Range/白名单/路径；真实浏览器筛选、导航、错误态与播放 |
| C18 | `pyproject`、wheel、UPSTREAM、四入口、当前文档 | 构建 wheel、仓库外非 editable 安装与资源字节；固定来源、模块实际位置、生产不依赖 tests；严格官方对齐、入口白名单、当前链接不指删除脚本 |

这些是首版责任域，不是声称只有 18 个测试足够。每域须继续拆成可执行条目；196 个 Python 文件及现行其他资产逐个归类，纯导出/shim/只读第三方可注明理由，不准无记录排除。

### 16 个任务的最小行为真值表

每任务分别运行原生 `easy/medium/hard` 和该任务实际支持的新值档的 CPU 方法测试；输入只含所需的 actor/robot/时钟状态。它是方法调用组合，**不是 reset 或 rollout 的授权数量**。每项还共同要求：未完成不成功、失败终态稳定、演示→在线切换、重复帧去重、重建或 reset 后 episode 状态清零。

| 任务 | 正例 | 错误／边界 |
|---|---|---|
| BinFill | 逐色正确数量入箱，再按按钮 | 少/多一块、错色/错箱、提前按；相等数量与对象移出后计数 |
| PickXtimes | N 次完整拾放后按钮 | N−1/N/N+1、持续抓住、错对象、持物按按钮 |
| SwingXtimes | 右→左 N 轮后放下按钮 | 左右反序、重复停留、距离/高度阈值；xhard5 支持范围 |
| VideoRepick | 交换后仍拾同一 actor N 次 | 用原位置代替身份、交换窗口首尾、演示次数混入 |
| VideoUnmask | 演示后按目标颜色选择 | 错容器、双选顺序、两次选择间放下、揭示窗口 |
| ButtonUnmask | 首按钮揭示后选择 | 跳过按钮、错颜色、按钮深度等号、单/双选 |
| VideoUnmaskSwap | 交换后跟随被遮挡对象 | 原位置误选、1/2/3 次交换、干扰容器、交换首尾 |
| ButtonUnmaskSwap | 两个不同按钮后选正确对象 | 重复同一按钮、同帧两按钮、缺一步、跨局按钮列表残留 |
| VideoPlaceButton | 按按钮前后指定演示落点 | before/after 反转、错 cube、额外演示干扰、交换后 identity |
| VideoPlaceOrder | 演示第 k 次放置目标 | 空间序冒充时间序、首/末序数、按钮插入、闭包捕获错误 |
| PickHighlight | 各个目标拾取均满足 | 漏目标、错对象、重复同一目标；首按钮失败回调与末按钮语言冲突 |
| StopCube | 第 N 次窗口内停止并确认 | N−1/N+1、窗口两端、过期、锁存步不重写、成功后继续 |
| InsertPeg | 同 peg 同抓取端、正确端与方向 | 换 peg/换端/反向、等距端判定、方向近零、延迟成功 |
| MoveCube | 演示指定推/抓方式与区域 | 错方式/工具、区域完整物体边界、距离阈值、三种移动方式 |
| PatternLock | 同按钮序列完整重走 | 跳节点/错序、仅相同后缀、连续同按钮去抖、额外错误触碰 |
| RouteStick | 同节点且沿指定侧绕行 | 节点对但方向反、叉积正/负/零、无轨迹、退化线段、失败锁存 |

## 三、怎样使测试能判出错

### 3.1 独立正确值与真实生产方法

以 `RecordWrapper` 为例，当前部分用例手写 HDF5，再读取自己的文件，只证明 h5py 可以工作。重构后保留真实 `RobommeRecordWrapper.step/close`、真实读回与 resolver，只在引擎、robot、camera、planner 边界提供 CPU 状态。几何期望用手算坐标，身份用固定小表加独立集合运算，状态机用手写事件序列；不得调用被测算法生成期望。

```text
旧：测试手写 writer / FakeDemoWrapper.step → 自己的文件或状态 → 自己的预期
    生产逻辑可以没有执行；AST“存在某字段”也不能替代时序证明。

新：独立事件表 → CPU 外部接口 → 真实 wrapper.step → 真实 close → HDF5 → 真实 resolver
    actor位置 (3,) float64 = 24 B；微型 RGB (4,4,3) uint8 = 48 B，逐帧不同。
    状态表→接口：只交付已知输入；wrapper：按生产语义转换；H5写读：逐键保留值。
    action_t 对应 obs_after_t；reset帧不入记录，不能机械套 T+1。
    测试没有可训练参数，不加载模型权重。
```

HDF5 真实文件只需少量帧；完整身份核验用 `16 任务 × 每任务跨档合计 50 个身份 = 800` 的纯 JSON/规格遍历，不生成 800 条轨迹。xhard0 开关兼容映射可读取 `16 任务 × 1 档 × 12 个身份 = 192`，同样真实 reset 为零。

录像本身另用至少64×64的合成帧，内部像素与10像素红边分开断言，不能用4×4图冒充边框验证。实际调用 `_video_prepare_step_frames/_video_apply_overlays/_video_append_step_frame/_video_flush_episode_files`，核H5原像素不被overlay修改、文本导致尺寸变化时归一、NO RECORD过滤、不补reset帧、成功/FAILED/NO_OBJECT/FailRecover命名、长目标哈希、编码失败与全部短视频帧读回。

C08的8个布尔开关是 `include_maniskill_obs/include_front_depth/include_wrist_depth/include_front_camera_extrinsic/include_wrist_camera_extrinsic/include_available_multi_choices/include_front_camera_intrinsic/include_wrist_camera_intrinsic`。完整CPU档对四种动作空间各穷举256种组合，共1024个CPU输入组合；每项独立按字段表判断，multi_choice额外核front参数强制开启。核心先含全关、全开、8项单开、8项单关的18组合及明确交互；完整组合执行证据另验收，18项不能代表全组合。

### 3.2 正反例、边界与变异分别验收

每个关键契约登记以下四类证据，不用全项目一个覆盖百分比代替：

- 正常输入产出独立期望，调用计数证明目标生产函数执行过。
- 非法/缺失/重复/非有限输入被拒绝，并检查错误原因或具体差异路径。
- 阈值两侧和恰好等号、首末项、阶段切换、第二局、恢复前后具有明确预期。
- 对真实生产副本或输入植入一个具名故障，对应测试必须失败。

非受保护源码变异在临时隔离副本运行，不改主检出或正式数据；`src/robomme/`及三个冻结入口仅允许tests进程内可恢复、不落盘的内存变异，记录原函数与变异函数的源码hash及具体运算符差异，不能自行给磁盘副本打补丁。确需落盘的受保护变异另按P2逐文件/符号批准。

语法错误、无法导入、无关环境失败不算“杀死变异”；先确认原版同环境通过，再证明指定断言因对应语义故障失败。原版拒绝坏输入是负例证据，只有删除校验/忽略字段等错误实现被指定测试抓住才计源码变异；两种计数分开。等价变异只能经独立审查说明后排除。

### 3.3 当前必须先暴露的生产候选问题

本轮已复现的六项作为首批负例，其中“字节关系”与“产物合法性”分开建契约。以下仅静态候选，实施时先执行真实方法验证，不能直接记为已证缺陷：

| 位置 | 先写的拒绝／行为测试 |
|---|---|
| `RecordWrapper.step/reset/close` | save_video=False 仍应有有效 H5 步记录；跨局状态不残留；二次 close 行为明确 |
| `PickHighlight._load_scene/evaluate`、其他任务 evaluate | 失败回调动态消费；成功/失败不能非法同时成立；语言与任务阶段冲突有独立记录 |
| `_rollout.run_batch/run_continue` | 错 seed/重复结果拒绝；旧 tried 与新增已落账本结果恢复不重复执行 |
| `v8_report.build_report`、`SeatRunner.run_one` | 必备 candidate/task/episode/cap 严格核对；意外异常仍关闭环境/记录器 |
| `challenge_interface/scripts/phase1_eval` | `unsuccessful/not_success/success_pending` 不得计成功；reset未就绪有截止条件；异常仍清理 |
| site HTTP/HTML | 启动后 API 文件越界 symlink、加载后未知 hash、媒体长度不一致有明确错误 |

## 四、CPU 默认执行与最小 GPU 边界

### 4.1 目录和执行档

| 目录 | 职责 | 执行档 |
|---|---|---|
| `tests/unit/native/`、`unit/hard/`、`unit/common/` | 16 任务、公共状态/几何/语言/动作 | 核心 CPU |
| `tests/contracts/`、`tests/upstream/` | 身份/规格/观测/报告/资产/官方兼容 | 核心 CPU |
| `tests/integration_cpu/recording/`、`generation/`、`evaluation/`、`challenge/` | 小型真实组件闭环；关键身份、预算、终态、分母不能整块排除 | 核心 CPU；长进程场景标 slow_cpu |
| `tests/parity/`、`tests/site/` | 有效性与比较器、目录/段/语义纯逻辑 | 核心 CPU |
| `tests/process/`、`http/`、`browser/`、`package/` | 真进程、协议、浏览器、安装交付 | 扩展 CPU，按依赖执行 |
| `tests/mutation/` | 关键定点破坏的执行与证据 | 少量哨兵进核心，完整清单进扩展 CPU |
| `tests/gpu_smoke/` | 一次裸环境初始化或原生 reset | 显式可选；默认不收集 |
| `tests/_support/`、`fixtures/` | CPU actor/robot/clock、独立期望、极小真实文件 | 公共支持；不得复刻被测算法 |

核心目标 ≤120 秒，硬上限 280 秒；这是待实测目标，不是已有性能保证。扩展 CPU 包括全部慢测试、packaging/HTTP/浏览器和关键变异；超过 5 分钟按 detached tmux 留档，按资源场景定向短测仍需先过最小冒烟。

### 4.2 收集前与运行时的资源限制

`pyproject.toml`拟设置 `addopts` 为 `-p tests._support.resource_policy --strict-markers --strict-config -m 'not slow_cpu'`；资源档默认core_cpu，裸pytest也受限。核心testpaths固定为 `tests/unit tests/contracts tests/upstream tests/integration_cpu tests/parity tests/site tests/mutation/core`；完整CPU显式再选 `tests/process tests/http tests/browser tests/package tests/mutation/full`，解除slow_cpu过滤。插件保存每档预期目录和必验nodeid集合，并与实际收集对照，少一域不能PASS。GPU目录只有显式选择且给 `--allow-gpu-reset` 才收集；根conftest不导入其夹具。只按gpu marker过滤不够，因为pytest先导入模块。

裸pytest未指定basetemp时，插件分配全新artifacts运行根，并把pytest临时目录、cache_dir和事件文件全部指向它；缓存不能落源码根。每个允许的子进程沿用同一归属根下不同子目录，不共享进度文件。

拟新增提前加载的 `tests._support.resource_policy` pytest 插件，在收集前拒绝真实 scene/GPU 初始化、真实引擎构造/reset、模型权重读取及外网；CPU 替身的 reset/step 允许。OS/网络测试只开放本次声明的本地进程、loopback 端口和夹具目录，子进程继承同一资源档。拒绝入口须按实际 torch/SAPIEN/ManiSkill API 核对，不把 `CUDA_VISIBLE_DEVICES` 当 Vulkan 的守卫。守卫是测试执行约束，不宣称能抵抗任意恶意 FFI 绕过。

资源守卫本身要实测：故意调用被禁边界必须先抛出拒绝，确认原生调用没有被执行；外网和未授权子进程也要覆盖。故意守卫用例的expected_denial与业务unexpected_denial分别记账；即使业务try/except吞掉拒绝，事件账本仍使会话失败，violations=0指unexpected_denial为零。必验套件选空、collect error、关键skip、未批准xfail、XPASS均失败。缺浏览器/ffmpeg/第三方环境只能标条件项未验证，不能计作全量PASS。

### 4.3 可选 GPU 探针

默认整项测试重构真实 reset/轨迹预算为零；仅当实施时确需验证初始化，拟定上限为 **1 任务（BinFill）× 1 档（easy）× 1 个实例**，只裸环境构造，必要时一次原生 reset，然后 close。构造期 reset 与显式 reset 分别计数，总真实 reset 封顶 2，轨迹生成为零，不自动扩到 16 任务、不重试、不加载真实策略。

`DemonstrationWrapper.reset` 会 `get_demonstration_trajectory()` 并执行初始动作，`OraclePlannerDemonstrationWrapper.reset` 还创建规划器，均不属于该探针。若裸环境构造也存在演示/规划等行为，立即停止受影响探针。wrapper reset 时序由 CPU 替身测。

这个可选探针只证明抽查实例初始化可用，不能证明所有任务的真实物理、规划、成功率或完整视频。是否执行与实际次数在结果单列 `TEST_GPU_RESET=PASS|NOT_RUN`。

## 五、验收：哪些结果才足以交付

| 查什么 | 怎么查 | 过了说明什么 | 拟定判定行 |
|---|---|---|---|
| 生产范围没有遗漏 | 固定树清单＋独立人工审查＋新增文件/入口未登记反例 | 全部责任有明确去向，未登记为零 | `TEST_INVENTORY=PASS unclassified=0` |
| 每个关键契约真有测试 | 清单 nodeid 与实际收集/执行报告连接，正反/边界标记检查 | 没有用目录或空 nodeid 冒充覆盖 | `TEST_CONTRACTS=PASS missing=0 pending=0` |
| 不出现假测试和隐形跳过 | main-only/空选择/坏导入/关键skip夹具 | 必验内容确实执行 | `TEST_DISCOVERY=PASS empty_files=0`；`TEST_REQUIRED_EXECUTION=PASS skipped=0 xfailed=0` |
| CPU 资源约束成立 | 早加载守卫＋违规反证＋父子进程事件 | 默认没有真实仿真或模型任务 | `TEST_RESOURCE=PASS native_reset=0 gpu_init=0 external_network=0 violations=0` |
| 16 任务有行为证据 | C05逐任务原生/hard真值表与调用事件 | Python成功/失败/阶段/记忆逻辑已覆盖 | `TEST_TASKS_CPU=PASS tasks=16 missing_contracts=0` |
| 记录与读取闭环 | 真实 step/close/resolver，小H5逐键独立比较 | 写入/读回时序和内容合约通过 | `RECORD_H5_ROUNDTRIP=PASS`；`OBS_CONTRACT=PASS`；`REPLAY_CONTRACT=PASS` |
| 生成与评估真实接线 | 生产序列化/守卫/账本/报告的最小集成 | 身份、预算、恢复和分母传递正确 | `GENERATION_CPU_CHAIN=PASS`；`EVALUATION_CPU_CHAIN=PASS`；`CHALLENGE_PROTOCOL=PASS` |
| 比较器与闸门不误接受坏输入 | 六个已证反例及C15扩展矩阵 | 有效性、身份和字节/数值关系分别成立 | `PARITY_VALIDITY=PASS false_accept=0` |
| 测试能抓关键错误实现 | 指定真实副本变异→对应断言失败 | 正例没有掩盖弱断言 | `TEST_MUTATION=PASS survived_critical=0 invalid=0` |
| 覆盖测量真实 | 原版branch报告＋逐契约分支映射 | 漏分支显式可见，不以百分比代替正确性 | `TEST_BRANCHES=PASS critical_uncovered=0` |
| 默认门禁够快 | 无缓存掩盖的完整核心运行，保留耗时 | 可日常执行全部关键CPU契约 | `TEST_CORE=PASS failed=0 wall_s=<实测>`（≤280） |
| 扩展责任实跑 | CPU进程、HTTP、浏览器、安装和完整变异 | 扩展环境验证通过 | `TEST_CPU_FULL=PASS missing_required=0`，各域另有具名结果 |
| 不丢旧有效契约 | 旧nodeid→契约→新nodeid/审查后的删除理由 | 历史故障经验保留 | `TEST_MIGRATION=PASS unmapped=0` |
| 官方和正式资产未改 | 固定来源全量字节核验、五规格与元数据hash | 测试重构没有暗改benchmark | `UPSTREAM_GUARD=PASS`（严格模式）；`TEST_FROZEN_ASSETS=PASS changed=0` |

**覆盖率不设一个任意 90%/100% 总线就结束。** 全源码 branch 结果用于定位遗漏；所有具名关键分支必须命中。无法在 CPU 触达的真实引擎路径单列条件清单，不从报告隐藏，也不宣称全部行为正确。关键变异没有被杀死，或已发现生产契约仍 FAIL，就不能交付“所有关键正确”。

官方行为回归与语义要求冲突时，`UPSTREAM_COMPAT=PASS` 可以与 `TASK_SEMANTICS=FAIL` 同时出现。已知问题允许发布研究报告或阶段结果，不允许把 xfail 计作已满足契约。

## 六、实施步骤与旧测试处置

| 阶段 | 内容 | 判据 |
|---|---|---|
| S0 | 保存固定生产/旧测试树、当前结果；先小CPU再分域测，不裸跑旧全集 | `TEST_INVENTORY`，资源预算清楚 |
| S1 | 主会话建立契约清单格式、默认收集、资源/执行守卫、公共CPU接口 | `TEST_RESOURCE`、`TEST_DISCOVERY` |
| S2 | 分域并行编写真实方法正反例、补6个已证漏检；生产错误分列阻塞清单 | 各域定向测试、实际函数调用证据 |
| S3 | 连接记录、生成、评估、challenge真实组件；小HTTP/媒体/安装与浏览器 | C09～C18逐域结果 |
| S4 | 故障审查＋真实副本关键变异＋branch缺口补齐 | `TEST_MUTATION`、`TEST_BRANCHES` |
| S5 | 旧nodeid和契约逐项迁移；新版验证后再删旧壳/旧生成夹具 | `TEST_MIGRATION`，有效契约无遗漏 |
| S6 | 核心完整CPU、扩展CPU和独立审查；可选单实例GPU探针 | `TEST_CORE`、`TEST_CPU_FULL`，缺陷/盲区单列 |
| S7 | README与AGENTS标记块外短测口径同步；具名验收、逐文件commit/push | 所有适用判定行，提交范围核对 |

以下旧文件先提取契约后改名，撤销原计划“按文件整删”的做法：`test_audit_fix`、`test_audit_fix_scripts`、`test_native_restore_step2`、`test_v8_native_blocks_unchanged`。`test_v7_tier_values`、`test_v8_specs_schema/delivery_flow/eval_client/eval_report` 中的现行 V9 断言继续保留。

3 个 main-only 文件改成真实 pytest 入口并增加生产闭环；错误标 GPU 的 CPU 用例迁回核心；`FakeDemoWrapper.step` 自证用例换成真实方法；裸写 `sys.modules` 改为可恢复局部替身或独立子进程。两个 `test_zz_summary_line` 删除会话失败数断言，由 runner 退出码报告。

dataset 自动生成夹具不搬过去继续用：删除失败换 seed、规划器运行时改写与完整 rollout 依赖，读写/obs/重放用微型独立H5和CPU接口重写。纯历史契约仅在对应生产能力已经按授权清理、且没有现行调用后删除。

原四个已实测失败逐项重审：未知环境和语言连接符是错误期望；错误处理用例必须真实调用官方方法确认异常传播，单独记录文档承诺冲突，不能仅改 AST 检查就写“错误处理正确”。

## 七、子代理分工与合并（简述）

主会话先完成共享契约格式、资源守卫与CPU接口；原生任务、hard配置、记录读回、生成、评估/challenge、对拍、站点/包交付各用持久代理负责互不重叠的新目录。独立审查代理核测试是否调用真实算法、预期是否独立、哪些错误实现仍能通过。

完成一域先核对可写范围和契约，再定向CPU验证；整合后跑核心与资源守卫。共享 conftest、pyproject、契约总清单、旧文件删除由主会话唯一写入，不让各域并行改。先让新测试落地并验证，再按迁移表删除旧文件；测试实施无需等待HF上传或批量生成。生产清理若先发生，各域据新固定锚点重新核接口，而非盲套旧名称。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线与实施前置

- R1：本轮交付仅计划与小证据；没有测试重构实现，也没有生产修复。后续用户授权实施时按此分配表派写入任务。
- R2：子代理不暂存、不commit、不push；有并行修改，不回滚他人文件。优先当前合适检出；隔离源码变异副本落本轮artifacts，固定BASE并核实际模块来源。
- R3：`src/robomme/` 和三个上游脚本冻结；只在tests进程内做被批准范围的边界替身。生产覆盖与修复另列文件/符号/原因，遵守P2。
- R4：规格、metadata、评估seed/scene/身份、正式结果、步数上限不改；本轮不执行原计划的批量生成、HF上传、数据删除或集群任务。
- R5：CPU套件真实reset/轨迹为0；可选GPU只按第一部分4.3上限。不用wrapper reset冒充简单reset，不自动扩大。
- R6：不改变参照来消除FAIL，不扩大数值容差；known jitter的身份/结构/finite/来源也必须验证。噪声重跑观察不能单次确定因果。
- R7：Python只用uv，显式 `UV_CACHE_DIR`；NFS用copy，测试临时文件统一在本轮artifacts，不写正式产物。
- R8：新目录/文件不进入scripts顶层。生产源码不import测试；测试可以依赖生产；独立oracle不能依赖目标算法生成答案。

## 一、逐文件改动清单与接口

| 文件集合 | 锚点／改动 | 默认关闭态／执行态 |
|---|---|---|
| `tests/conftest.py` | 资源档、basetemp、选中必验skip与零收集治理；GPU夹具延迟导入 | CPU默认；显式GPU参数才允许其目录 |
| `tests/_support/resource_policy.py`（新） | 提前加载、入口拒绝、事件记录、子进程策略；loopback仅声明测试开放 | CPU拒绝原生引擎/权重/外网；process/http档限定放行 |
| `tests/_support/{actors,robot,clock,fixtures_io}.py`（新） | 仅外部接口；每帧哨兵、独立数据表、可pickle边界 | 无仿真；无生产算法复刻 |
| `tests/contracts/benchmark_contracts.json`、对应测试 | C01～C18继续细拆；生产模块和公共符号登记、nodeid与执行报告绑定 | planned不算覆盖；只有真实结果verified |
| 第一部分4.1各新测试目录 | 真实方法与各域正/负/边界、集成、变异 | 核心CPU＋显式扩展CPU，不自动GPU |
| `tests/fixtures/current/` | T0唯一写入；各域交需求与独立期望，微型H5/JSON/短媒体及来源摘要 | 不生成真实轨迹，不依赖正式大数据 |
| `tests/lightweight/`、`tests/dataset/`、旧_shared | 迁移后逐文件删壳；保留有效负例与历史故障；旧自动生成删除 | 新契约未通过前不先清空旧树 |
| `pyproject.toml`、`uv.lock` | 默认插件、testpaths、strict与markers；dev coverage；branch/parallel/子进程启动及路径映射配置 | 不更改运行依赖/第三方pin；依赖差异单独审查 |
| `tests/README.md`、`AGENTS.md`标记块外 | 中文职责、CPU核心/完整/条件命令、证据与盲区；更新核心短测 | 不手改common-agents块 |
| `docs/validation/test-refactor-<run_name>/` | 迁移表、契约执行与变异报告、轻量日志、缺陷裁决 | 不存权重/全轨迹/bash/yaml拷贝 |

本轮发现环境缺 `coverage/pytest_cov`，没有安装。若实施采用branch采集，使用 `uv add --optional dev coverage`，核锁文件差异并 `uv sync --extra dev`；不得漂移正式torch/ManiSkill等依赖。现原计划的uv.lock冻结在该测试dev依赖变更上需要采用本文这一明确例外，除此不动。

契约执行报告必须包含 `contract_id/source_hash/nodeids/collected/passed/failed/skipped/xfail/resource/target_calls/oracle_kind/mutation_results`。缺字段不能默认零，0值必须实际序列化再读回核对；具名判定由报告器读取pytest退出状态与明细生成，不在测试里复制整会话失败数。

## 二、子代理分配表

所有可写集合仅为后续实施分配，当前研究代理均只读。资源默认CPU、无GPU、无外网；各任务run_name前缀 `test-refactor-T<n>`，长任务tmux前缀 `test-refactor-`，不触碰既有任务。每代理只写自己的新测试目录与对应变异定义，旧树读而不删。

| 编号 | 目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖／整合顺序 | 验收（本机uv CPU） | 资源与共享归属 |
|---|---|---|---|---|---|---|
| T0 主会话 | 共享运行框架与清单 | conftest、_support、contracts总清单、pyproject/lock、文档 | 正式数据/受保护源码/他人改动 | 先定资源档与接口；合各域增量清单 | discovery/resource负例、核心最小冒烟 | 共享文件唯一写者；无端口 |
| T1 | 16原生任务与公共逻辑 | `tests/unit/native/`、`tests/unit/common/` | hard目录、共享文件、所有生产文件 | T0后；C05～C07，先整合 | 逐任务真值表；`TEST_TASKS_CPU`原生部分 | CPU；无端口 |
| T2 | hard行为/规格/builder | `tests/unit/hard/`、`tests/contracts/hard/` | T1/T3等目录、共享文件、生产文件 | T0后；C01～C05；第二整合 | 类型/重签/冻结值消费；800身份纯读取 | CPU；无端口 |
| T3 | wrapper、记录、obs、重放 | `tests/integration_cpu/recording/`、`tests/contracts/recording/` | shared和所有生产文件 | 用T0接口；C08～C11；第三整合 | `OBS_CONTRACT`、`RECORD_H5_ROUNDTRIP`、`REPLAY_CONTRACT` | CPU；H5/codec各用本轮临时根 |
| T4 | 生成与续行 | `tests/integration_cpu/generation/` | parity/eval/共享与生产文件 | C12；T2规格夹具契约；第四整合 | 真run_batch/JSON/聚合/守卫故障链 | CPU；进程端口按夹具声明 |
| T5 | 评估与challenge | `tests/integration_cpu/evaluation/`、`tests/integration_cpu/challenge/`、`tests/contracts/evaluation/` | production/third_party共享文件 | C13～C14；T2identity/T3recorder；第五整合 | 真handler、A→B→A、唯一accept/分母/计分反例 | CPU；仅loopback临时端口；不加载权重 |
| T6 | 对拍与噪声 | `tests/parity/` | 其他测试域、生产比较器与基线 | C15；第六整合 | 六漏检＋扩展坏输入、集合/finite/类型 | CPU；微型H5，无端口 |
| T7 | 进程/HTTP/站点/浏览器 | `tests/process/`、`tests/http/`、`tests/site/`、`tests/browser/` | package与生产/共享文件 | C16～C17；核心pure场景可先；第七整合 | 真OS监督/Range/路径/浏览器交互 | CPU；独立临时端口及精确PID清理 |
| T8 | 安装与官方边界 | `tests/package/`、`tests/upstream/`、`tests/contracts/repository/` | 源码/第三方工作树/共享文件 | C18；第八整合 | wheel仓库外导入、来源/资源指纹、严格upstream | CPU；临时uv环境，不sync主在用环境 |
| T9 独立审查 | 契约遗漏、弱assert、关键变异 | 只读；修订建议交责任人 | 禁止写任何共享/生产文件 | 与T1～T8并行；最终整合前后各审 | 契约→真实调用→独立oracle→故障失败 | CPU只读；变异执行由主会话统一排程 |
| 主会话收尾 | 迁移/删除/变异执行/可选GPU/文档 | 旧tests逐文件、`tests/mutation/`框架、gpu_smoke | 正式数据/未经批准生产文件 | T1～T8通过后；不可并行删除旧文件 | `TEST_MIGRATION/TEST_CORE/TEST_CPU_FULL` | 共享裁决、运行预算与commit由主会话负责 |

某域需要改共享接口时先发需求，由T0写；不临时在本域复制同名helper。各域具名变异定义落自身目录，由主会话的mutation框架读取，避免多人写同一变异总表。

## 三、关键破坏闸门

| 变异编号 | 破坏内容 | 指定必须失败的契约 |
|---|---|---|
| M01 | candidate/attempt/seed非整数，重算所有签名 | C03类型，不得只靠hash拒绝 |
| M02 | 删除spec注入或消费错误路径 | C04冻结值实际消费 |
| M03 | 交换两个身份但总数相同 | C03/C13/C15集合绑定 |
| M04 | 成功次数提前一步、失败优先级反转 | C05/C06完成与失败 |
| M05 | `<`/`<=`反转、before/after互换 | C05/C07等号与序列 |
| M06 | 删除跨局缓存清理或policy reset | C09/C10/C13连续A→B→A |
| M07 | 丢H5字段、根属性、group↔dataset、非有限动作 | C10/C11/C15有效性与全字段 |
| M08 | 空冻结文件、空范围、遗漏身份补重复 | C03/C12/C15空集和独立集合 |
| M09 | 正常失败按基础设施重试或分母只计成功 | C12/C13/C14计分与预算 |
| M10 | counts缺项默认0、JSON中间损坏静默忽略 | C12/C13真实序列化与恢复 |
| M11 | 回写前中断后重复派已完成身份 | C12恢复幂等 |
| M12 | fake handler代替真实handler、错误状态包含success即成功 | C13/C14真实协议和精确状态 |
| M13 | HTTP越界路径或Range返回全部文件 | C17协议与文件边界 |
| M14 | wheel缺规格、shim指向错误检出、生产import tests | C01/C18独立安装与来源 |

每个编号继续分小变异，完整清单逐项要求 killed；不能用平均mutation分数掩盖任一关键存活者。对比器原本只提供字节关系的地方，不强迫它承担所有schema责任，而在业务接受边界增加对应有效性契约。

## 四、runbook（拟新增接口，当前不能直接当已可用命令）

以下目录、插件和自定义选项均在S1～S6实现后可用；本轮没有执行这些拟定命令。

```bash
export UV_CACHE_DIR=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/.cache/uv
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export CUDA_VISIBLE_DEVICES=''

# 核心：testpaths为CPU白名单；插件先于收集加载。
timeout 280s uv run --frozen --no-sync python -m pytest \
  -p tests._support.resource_policy --resource-tier=core_cpu \
  -m 'not slow_cpu' -q --durations=20 \
  --basetemp=artifacts/test-refactor-<run_name>/core-tmp \
  --junitxml=artifacts/test-refactor-<run_name>/core.xml

# 某域定向扩展：-o addopts取消默认slow过滤，显式保留早加载插件。
uv run --frozen --no-sync python -m pytest tests/integration_cpu/challenge \
  -o addopts='' --strict-markers --strict-config \
  -p tests._support.resource_policy --resource-tier=process_cpu -q \
  --basetemp=artifacts/test-refactor-<run_name>/challenge-tmp

# branch采集需要先装已声明dev依赖；扩展全量如超5分钟进tmux。
export COVERAGE_FILE=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/test-refactor-<run_name>/coverage/.coverage
uv run --frozen --no-sync python -m coverage run --branch --parallel-mode \
  --source=src/robomme,src/robomme_hard,scripts,challenge_interface \
  -m pytest tests/unit tests/contracts tests/upstream tests/integration_cpu \
  tests/parity tests/site tests/process tests/http tests/browser tests/package tests/mutation \
  -o addopts='' --strict-markers --strict-config \
  -p tests._support.resource_policy --resource-tier=full_cpu -q \
  --basetemp=artifacts/test-refactor-<run_name>/full-tmp \
  --junitxml=artifacts/test-refactor-<run_name>/full.xml
uv run --frozen --no-sync python -m coverage combine --keep \
  artifacts/test-refactor-<run_name>/coverage
uv run --frozen --no-sync python -m coverage json \
  -o artifacts/test-refactor-<run_name>/coverage/branches.json
```

`<run_name>`必须替换为本次唯一新名；先核父目录真实落点并创建全新、非symlink的本轮根，所有basetemp初次必须不存在，避免pytest清空复用目录。coverage缓存、分进程数据和报告均落同一artifacts根，不产生根目录`.coverage`。

父进程的coverage run不会自动证明子进程覆盖。T0需在配置中启用所锁coverage版本支持的subprocess启动机制、parallel输出和multiprocessing采集；仓库外安装环境也安装同版dev coverage，进程初始化先开始采集，按来源hash将wheel/副本路径映射回同版源码后combine。分别用子进程独有函数、spawn独有分支、仓库外wheel独有调用的夹具证明每类数据实际进入报告；SIGKILL来不及落盘的数据不能视为已覆盖，对相关关键逻辑另用可正常退出的测试补测。机制依据 [coverage进程采集文档](https://coverage.readthedocs.io/en/latest/subprocess.html) 与 [分进程合并文档](https://coverage.readthedocs.io/en/latest/commands/cmd_combine.html)，本轮只核文档未安装执行。

完整CPU档不得仅以marker选择后忽略缺工具的skip。浏览器用CPU Chromium＋极小本地站点；正式浏览器安装/额外下载先核当前能力，本轮没有安装。测试媒体用2帧本地合成输入，无仿真。

GPU探针不写可复制的裸通用命令：实施时先核具体创建/reset路径、构造期reset计数和GPU归属，再给显式单实例入口。无需向用户反复请求同一预算；超本文上限才汇总变更。

## 五、风险与生产缺陷裁决

| 风险 | 处置 |
|---|---|
| “覆盖全库”被解释成每行都能CPU真实执行 | 关键Python语义实测；真实引擎/模型路径条件登记，不伪造证据 |
| 预期由生产常量动态生成导致共同改错 | 独立固定表、数学算例、来源fingerprint；改生产表的mutant必须触发差异 |
| 提取AST重建函数掩盖真实import/调用链 | AST只守结构；行为测正常导入真实方法或隔离固定模块 |
| 受保护官方实现确实违背语义契约 | 记录FAIL和最小反例，分别报官方兼容与语义；修复另行逐项审批 |
| 旧名称整删让V9负例消失 | 先契约迁移再删除，T9复核四个撤销整删文件 |
| 依赖缺失导致测试整域skip | 缺环境列未验证；必验门禁不能PASS，第三方用固定子项目CPU环境 |
| 资源守卫安装太晚/子进程逃逸 | 提前插件、GPU目录不收集、允许的子进程继承，违规反证实际执行 |
| 代码清理与测试重构同时移动目标 | 各阶段固定锚点，接口改名只由共享负责人维护；先保留行为合同 |
| 噪声表确定归因与已知抖动整局豁免 | 只记录观察/待复核；结构/身份/finite不豁免。本轮不执行其批量生成 |

## 六、盲区诚实清单

CPU真方法测试不能证明真实物理接触、IK/FK正确、RRT墙钟行为、真实渲染完整性、完整演示成功或模型权重输出；单实例GPU初始/reset不能覆盖16任务物理闭环；官方字节相同不能证明官方算法正确；branch=100%和全部具名mutant被杀死也不是数学上的完全正确证明。

能够承诺的交付是：全部现行责任完成登记；CPU可验证的全部关键契约有独立正反/边界证据、关键破坏能被抓到；条件项、生产失败和未验证范围单列。任何必需生产契约仍FAIL时，交付研究/阶段成果并列阻塞，不声称重构目标全部实现。

## 七、留档、验证与commit纪律

每阶段保留来源hash、独立期望依据、pytest实际选择/退出/skip、定向耗时、资源事件、branch与mutation明细、旧契约去向和缺陷处置。日志/JSON/截图等Git无法还原的小证据入docs；大临时H5、wheel/venv和变异副本留artifacts。

主会话逐文件暂存本轮内容；subject接续 `<大>.<小> 中文描述`，body含用户原话、设计、已证/静态问题、命令数字和盲区。每阶段改测试后跑对应短测及核心，成功后commit立即push当前upstream；生产FAIL未获修复时明确报告，不能靠删断言交付。docs修改至少 `git diff --check`、链接/两部分/范围核验。

本轮文档提交只含本文、原维护计划第四节衔接及测试验收修订、本轮验证记录；不提交SimpleMemVLA和其他会话内容。研究期间其他会话把HEAD推进到 `8865220627f25536498f0daa9f20f386b09c6c4f`，新增另一份测试设计与运行留档；本文生产事实仍锚定PLAN_BASE，未合并那份后续证据。源码/测试/配置与PLAN_BASE的差异检查仍为零。实施完成后的结果另加子节，不能把本文“拟定”命令与目标数改写成历史已通过。
