> **本方案包括接口接入、三模型并发测速和两新模型完整评估。** 按用户追加要求，接口完成后继续在 Great Lakes 上完成这些阶段。本轮仍只修改这份根目录文档，不改实现、不下载、不安装、不提交作业、不启动评估；下列运行方案和预算用于后续统一实施。
>
> **新增评估配置已明确**：**GroundSG + Oracle** 和 **GroundSG + QwenVL**。两组都使用官方 GroundSG 路线；本方案不再包含此前误写的 SimpleSG + Oracle。现有 FrameSamp + Modulation 仅保留为兼容默认入口。
>
> **用户已定方向**：①「不要下载，不要下载，你只写根目录的计划。」②「我不关心它是怎么具体实现的，这些实现都已经定下来了，我只关心怎么去改现在的这个 repo，让它和官方的这个 evaluation 是对齐的。」③「对的，你的方案里面只需要说这个接口到底是怎么接。然后现在呢，当前 repo 已经没有 XHeart0 了，XHeart0 做了对拍，所以你需要在目前官方的接口中，啊不是，你需要在当前 repo 的接口中除了这个 hard，就是 scripts evaluation hard 里面传入的这个 test hard 之外，再加入一个接口，可以传入 test hard 0，或者说 test hard 什么别的，让我可以去评估 XHeart0。」④「就按照我说的这些去改这个方案，你现在可以直接改。」下文把口述的 XHeart0 对应到现有代码的 xhard0。
>
> **本次模型纠正原话**：⑤「我还需要 evaluate grounded subgoal oracle 和 grounded subgoal 加 Q1 VL 这两个 model，不是你刚才说的这两个。为什么在计划里没有体现到这两点。」⑥「qwenvl不是q1vl」。以⑥的拼写纠正为准，正文统一写 QwenVL；前述原话保留原样。
>
> **完整评估与测速追加原话**：⑦「做完了这个改动之后，这个计划里还要包括对于这两个 model 的完整的评估，还是用之前一样的 Great Lakes Jobs 来完成。」⑧「但是要修复一个之前的问题，就是之前是一个卡对应一个卡一个GPU对应一个 job，这一个 job 只跑一串行的评估。但是现在呢，GPU 是占用不满的，你考虑一下是不是同时跑两个效率比较高，就是这个策速问题也要解决。」⑨「这个占用问题你要分三个 model 来都要测，就是原本的 model 也要测，然后新的 model 也要测。」⑩完整范围答复：「两套都评：每组992局」。⑪「然后新的两个模型要回头评估原有入口要保证完全一致。」⑫「就是说原有入口的hard也要评估。」
>
> **锚点与范围**：工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，规划依据 `b280428745098e63ff0f6b3b826dfe44995c771b`；官方 MME 参照为仓库已锁定子模块 `ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b` 的 `examples/robomme/`，不追随远端移动分支。现有 `third_party/SimpleMemVLA`、`runs/` 在途内容不动。实际实施与资源使用另行启动，本轮不执行；提交编号沿用 `12.<小版本>`。

# 第一部分（给人看）

## 一、要实现的目标

**这次交付包括：接好 xhard0 和两组 GroundSG 评估接口，验证原官方 hard 与新入口完全一致，测清三模型单卡一路／两路的实际收益，最后完成两新模型的整套评估。**

**目标1：增加 xhard0 的独立数据集接口。** 保留 `dataset="test-hard"` 选择当前 V9；新增 `dataset="test-hard0"` 选择已经做过环境对拍的 xhard0。新接口复用现有数据与环境路径，不重新生成场景，不把 xhard0 加回默认的 `test-hard`。

**目标2：接入两组指定模型的官方评估。** 新增 `--mme-variant ground-sg-oracle` 和 `--mme-variant ground-sg-qwenvl`，分别使用官方 Oracle、QwenVL 预测器及同一套 GroundSG VLA 配置。现有 FrameSamp + Modulation 继续作为兼容默认路线。模型实现已经存在，本次要完成的是当前仓库的调用接入。

**目标3：数据集与模型可以独立选择，并验证接入后行为与官方一致。** 最终应支持下面四种组合：

| 模型选择 | `test-hard`：当前 V9 | `test-hard0`：已有 xhard0 |
|---|---|---|
| GroundSG + Oracle：`ground-sg-oracle` | 可以评估 | 可以评估 |
| GroundSG + QwenVL：`ground-sg-qwenvl` | 可以评估 | 可以评估 |

记V9完整身份集为 **D9**，按 `hard_specs.py::_v9_cells` 为 `3任务×2档×17 + 3任务×1档×16 + 2任务×5档×10 + 2任务×2档×13 + 2任务×2档×12 + 7任务×2档×25 + 2任务×1档×50 = 800局`；记 **D0 = 16任务 × 1档（xhard0／官方hard）×12局 = 192局**。新接口与原官方入口用同一D0身份、不同调用路径。

**目标4：原入口 hard 也完整评估，并要求完全一致。** 两个新模型各运行原官方hard的D0，与各自新`test-hard0`的D0逐身份、逐决策对照；固定输入测试和真实闭环两项都要通过。原侧独立使用官方环境与单局流程，不能两边都调用新适配器。不以相近成功率、历史容差或已有其他模型结果代替。

**目标5：三个模型都测单卡一路与两路。** FrameSamp + Modulation、GroundSG + Oracle、GroundSG + QwenVL分别比较同一张GPU、同一个job内的1路与2路，两个dataset都覆盖代表负载。以每小时完整结束的局数、执行步吞吐和资源成本决定各模型并发度，不预设两路一定更快。旧FrameSamp纳入测速，不额外重跑其整套正式成绩。

**目标6：沿用 Great Lakes 作业形式完成两新模型正式评估。** 每模型包含D9 + 新入口D0 + 原官方入口D0，即 **800+192+192=1184局；两模型共2×(D9+D0+D0)=2368个正式回合**。用户确认的每模型992局是前两项，原官方hard是追加的192局；新入口D0同时充当对拍的一侧，只跑一次。测速、预热与重试另列在第二部分预算表。本轮只改计划，尚不执行。

## 二、两个当前仓库分别改哪些部分

### 2.1 两个仓库的分工

这里的两个仓库是 **benchmark 仓库**和 **MME-VLA 策略库**。MME-VLA 已通过本仓库的 `third_party/mme-vla` 子模块引用；其来源是 `hongzefu/robomme_policy_learning_MotionJEPA`，实际使用文首锁定的 gitlink。

| 仓库 | 目前负责什么 | 本方案要改什么 |
|---|---|---|
| **benchmark**：`robomme_benchmark_MotionJEPANewTask` | 场景、数据集选择、环境创建、评估启动和结果记录 | **新增接口与接入代码全部放在这里**：下面分别列 xhard0 改动和新模型评估改动 |
| **MME-VLA**：`third_party/mme-vla` | 官方评估循环、Oracle/QwenVL预测器、VLA推理服务 | **无需改源码或gitlink**。直接复用现有 `EpisodeEvaluator`、两种预测器及 `serve_policy.py`；由benchmark传入所需参数 |

因此，下面的“改哪些文件”都是 benchmark 内的改动。策略库不是漏改，它已经提供这两组评估的实现；本方案只把它们接到当前环境接口。SimpleMemVLA库本轮不涉及。

### 2.2 为了单独评估 xhard0，benchmark 要改什么

| 文件／位置 | 具体改动 | 改完之后 |
|---|---|---|
| `src/robomme_hard/env_record_wrapper/hard_builder.py::BenchmarkEnvBuilder.__init__`、`_ALLOWED_DATASETS` | 增加 `test-hard0`；直接复用已有 `_xhard0_entries` 建立本地局号映射 | 可以单独获得xhard0，不需要打开旧的“前置xhard0”开关，不读取V9规格 |
| `src/robomme_hard/env_record_wrapper/__init__.py` | 导出新数据集常量 `TEST_HARD0` | 外部调用保持同一套builder接口 |
| `scripts/evaluation_hard.py` 的builder创建处 | 增加 `--dataset`；默认 `test-hard`，可选 `test-hard0`；按选择传1600或1300 | 同一示例入口可以切换两套场景，不新增顶层脚本 |
| `scripts/eval-official/env_client.py::EnvSession.builder/SeatRunner.builder_for` | 把两个位置硬编码的 `test-hard` 改成接收数据集参数；缓存、身份校验和结果同时记录dataset | 正式评估选了xhard0后，真正建出的也是xhard0环境 |
| `scripts/eval-official/v8_manifest.py::check_source` | 修正仍要求192个xhard0前缀的旧假设，使其支持当前无前缀V9清单 | V9与xhard0清单分开处理，不沿用错误的旧局号 |
| `scripts/README.md`、`src/robomme_hard/README.md` | 补两种dataset的用法、索引和边界 | 用户能明确知道如何切换及各自评哪些场景 |

**xhard0只增加选择入口，保留原路径。** 本地 `episode=0..11` 对应官方原 `source_episode=3,7,…,47`；seed照抄官方test元数据，标签为 `xhard0`，真正传给环境仍是 `difficulty="hard"`。复用现有 `resolve_identity/_hard_env_kwargs`，不加入规格回注或新seed公式。旧 `XHARD0_IN_TEST_HARD` 开关保留历史兼容、默认关闭；新接口与该开关独立。

实现后，示例入口这样选择：

```bash
# 以下是拟新增参数的用法，本轮不执行
uv run --no-sync python scripts/evaluation_hard.py --dataset test-hard
uv run --no-sync python scripts/evaluation_hard.py --dataset test-hard0
```

`evaluation_hard.py` 目前使用 `DummyModel`，上述命令展示数据集接口；真实模型评估使用下一节的接入与启动脚本。

### 2.3 为了增加两组 GroundSG 的评估，benchmark 要改什么

| 文件／位置 | 具体改动 | 接到策略库的什么能力 |
|---|---|---|
| **新增** `scripts/eval-official/mme_official_adapter.py` | 把当前 `EnvSession` 包装为官方评估需要的runner，提供 `get_init_obs/step/info` 等接口；调用官方单局流程 | `examples/robomme/eval.py::EpisodeEvaluator` 与 `env_runner.py::EnvRunner` 的原有行为 |
| `scripts/eval-official/env_client.py::build_parser/cmd_run/SeatRunner/run_one` | 解析模型变体与Qwen adapter路径，选择客户端路线，持有预测器上下文并记录所选配置 | Oracle或QwenVL预测器；两组均为 `grounded_subgoal` |
| `scripts/eval-official/run_seat.sh` | 接收并传递dataset、模型变体、VLA checkpoint及Qwen adapter；按变体检查对应配置 | 原 `scripts/serve_policy.py` 启动VLA；环境客户端调用对应官方预测器 |
| `scripts/eval-official/run_v8_gl.sh` | 在现有V9路线透传模型变体和Qwen adapter参数 | V9可选两组GroundSG；它继续只接受 `test-hard`，xhard0使用 `run_seat.sh` 非V8路线 |
| 对应轻量测试与上述两份README | 分别验证两种模型选择、参数传递、官方流程对齐与调用说明 | 同一组官方函数作为独立对照，不只验证“能跑完” |

两组的准确映射如下，**不需要在策略库里重新实现任何模型**：

| benchmark新增选择 | 复用的官方预测器 | 传给官方的关键参数 |
|---|---|---|
| `ground-sg-oracle` | `OracleSubgoalPredictor` | `use_oracle=True`、`use_qwenvl=False`、`subgoal_type="grounded_subgoal"` |
| `ground-sg-qwenvl` | `QwenVLSubgoalPredictor` → `Qwen3VLModel` | `use_oracle=False`、`use_qwenvl=True`、`subgoal_type="grounded_subgoal"`，另传 `qwenvl_groundSG_adapter_path` |

两组都给VLA server传 `symbolic-grounded-subgoal/79999` 与 `symbolic-grounded-subgoal.yaml`。QwenVL额外需要的 `--qwenvl-groundsg-adapter` 传到环境客户端的 `args.qwenvl_groundSG_adapter_path`；它和VLA的 `--mme-ckpt` 是两个参数，不能传混。预测器由客户端按官方生命周期复用，临时图像目录与正式录像分开。

官方单局循环在benchmark客户端进程内运行；客户端与策略库原有VLA server之间仍通过WebSocket通信。源码定义加载、依赖检查、连接收尾等具体接缝见第二部分，不改官方推理与子目标规则。QwenVL实际客户端依赖及本地缓存是否齐全仍待核实，本轮不补装或下载。

### 2.4 两项改动怎样连起来

`env_client.py` 同时接收“评哪个数据集”和“用哪组模型”，是上述两项改动的交汇点。xhard0改动决定环境来源；新模型改动决定官方评估选择哪个预测器，两者不会相互绑定。

```text
已有路线：
benchmark的test-hard → 现有FrameSamp客户端 → WebSocket → MME-VLA原服务

新增路线：
benchmark选择dataset与mme-variant
  → 创建所选数据集的EnvSession
  → mme_official_adapter进入官方EpisodeEvaluator循环
  → runner/EnvSession.reset取得初始观测
  → 需要新动作块时：所选官方预测器 → WebSocket请求GroundSG服务返回动作
  → runner/EnvSession.step执行动作，取得新观测
  → 按官方循环继续；动作块用完再请求下一块，直到本局结束
```

改动只发生在选择与接入层。图像、状态和动作沿用官方格式、不在适配层改数；无新增训练参数。图像 `uint8[H,W,3]`、每视角 `3HW` 字节，状态 `float32[8]`、32字节；动作沿用官方返回dtype、形状与截取规则，具体边界沿用第二部分合同。

**保留两套既定结束口径。** xhard0传 `max_steps=1300`，保持官方 `count > max_steps` 的原有顺序，可能执行到第1301步；V9正式评估保留 `step_cap=1600`，第1600步成功仍算成功。示例脚本只向builder传1300/1600，仍使用原包装器的计数方式，不把示例误写成正式严格截断入口。

输出根按 `<运行根>/<dataset>/<mme-variant>/` 分开，内部保持原有 `sNN/mme/` 或单席 `mme/` 格式，继续供现有报告和录像工具读取。两种模型的结果各自成列。

### 2.5 怎么确认这两项接线完成

已有xhard0环境对拍作为接口复用的依据；用户现已追加两新模型的原官方hard完整策略评估与严格对齐。下面先列接口判据，完整运行和性能判据在§2.7～2.9。所有判据均待实施。

| 要确认的目标 | 怎么查／通过说明什么 | 判定行 |
|---|---|---|
| 新入口选中原xhard0 | 静态比原episode、seed、difficulty及建环境参数；规格读取函数调用即失败 | `HARD0_INTERFACE=PASS tasks=16 per_task=12 total=192 specs_reads=0` |
| 原V9入口与新入口不串 | 对照同开关状态下的原身份；默认V9保持上文乘式800局，新接口始终只含xhard0 | `DATASET_ROUTING=PASS crossed=0 default_changed=0` |
| 两组模型接入官方流程 | 独立官方参照与新适配路径输入相同，比较请求、执行动作及终态；Qwen引擎用不加载权重的测试替身 | `OFFICIAL_ADAPTER=PASS variants=2 payload_diff=0 exec_diff=0 terminal_diff=0` |
| 步数及错误收尾未改变 | 分别核xhard0原终止行为、V9严格1600边界与异常收尾 | `EVAL_BOUNDARY=PASS hard0_changed=0 v9_over_cap=0` |
| 参数从入口传到底 | 覆盖两个dataset×两个新增模型的4种静态路由，核Qwen adapter到客户端、GroundSG checkpoint到server | `EVAL_WIRING=PASS routes=4 dataset_mismatch=0 variant_mismatch=0 predictor_mismatch=0` |

本表`192`对应 `16任务×1档×12局` 的静态身份检查，4种路由也是零仿真检查；后续真实评估的数量按第二部分预算单独计，不将静态检查伪装成实跑，也不额外重做数据生成对拍。

### 2.6 子代理分工与合并（简述）

A负责xhard0数据集和示例，B负责官方单局适配及`env_client`，C负责启动器与单GPU双路编排，D负责测速与完整报告，E负责原官方hard参照和严格比对。共享文件`env_client.py`只由B修改、两个现有启动器只由C修改；按A→B→C→E→D整合。每次先审范围和定向测试，再检查接线。真实GPU作业、预算、两份README与最终验收由主会话统一控制；策略库只读，子代理不暂存、不提交、不推送。

| 顺序 | 内容 | 完成条件 |
|---|---|---|
| 1 | 增加独立 `test-hard0`，保留默认V9接口 | `HARD0_INTERFACE`、`DATASET_ROUTING` |
| 2 | 接入GroundSG + Oracle和GroundSG + QwenVL的官方流程 | `OFFICIAL_ADAPTER`、`EVAL_BOUNDARY` |
| 3 | 贯通启动参数、隔离结果、补使用说明 | `EVAL_WIRING`，旧默认FrameSamp路线回归通过 |
| 4 | GL最小冒烟；两新模型各完成原官方hard和新test-hard0的完整D0，单路逐项比对 | `HARD_REAL_ALIGNMENT`与两侧完整覆盖；新侧成绩直接保留作正式D0结果 |
| 5 | 三模型分别在两dataset上测单路／双路、监控自身影响与资源隔离 | 每模型每dataset的`CONCURRENCY_DECISION`，双路不可用也有完整失败证据 |
| 6 | 两新模型各完成V9的D9，按各自通过验证的并发度运行；收齐三套成绩和视频 | `FULL_EVAL_COVERAGE/REPORT/VIDEOS`；原入口一致性不能被运行成功替代 |
| 7 | 保存证据和留档，按本轮资源清单收尾 | `EVAL_BUDGET`、`EVAL_CLEANUP` |

### 2.7 原官方 hard 怎样评、怎样判“完全一致”

新增独立的`official_hard_runner.py`与`run_official_hard.sh`。它们只在外围选官方`test`元数据中`difficulty="hard"`的D0，并调用原`EnvRunner.make_env(source_episode)`、原`EpisodeEvaluator`和所选官方预测器。锁定版本原CLI没有hard/episode筛选参数，不能虚构`--hard`，也不能误跑完整test再把难度改成hard。

原侧独立进程只导入官方`robomme`；新侧走`robomme_hard`的`test-hard0`。对应关系为`(task, source_episode, seed)`，本地`0..11`与原`3,7,…,47`只是索引映射。两侧用同一GPU、同一客户端依赖环境、模型/配置/tokenizer和单路资源设置；分批串行跑两侧，不同侧不在同卡重叠运行。

**严格验收覆盖D0全量，包含演示与reset观测、每步状态、Oracle文本或Qwen真实请求/回复、发给VLA的内容、返回动作块、实际执行动作、停止步和最终成功字段。** 语义字段要求dtype/shape/字节相等；只允许预先声明的路径、时间戳、原局号表示映射。少帧、漏事件、重复身份、错误或不完整轨迹均不得PASS。固定输入对拍与真实模型闭环分别判定，真实任一身份不一致即`HARD_REAL_ALIGNMENT=FAIL`，记录首个差异，不改成容差通过、不重试挑一致结果。

已有记录不是新模型完全一致的证明：[V8结果](docs/validation/newtask-v8/result.md)中的旧MME曾有`status_diff=18 steps_diff=115`，当时是只报告的`INFO`。这说明本次“完全一致”必须实测，不能预先保证；出现差异时保存完整证据，停止受影响模型后续放量并定位，不能默默放宽要求。

### 2.8 三个模型怎样比较一路和两路

**一个占位job仍占一张GPU，但其唯一一个`srun --gpu_cmode=shared`内部可以有两条独立评估进程树。** 每路各有VLA server、client、环境，Qwen路线各自持有Qwen预测器；不共用有历史/RNG状态的服务。两路只分担同一份清单的互斥子集，不能用重复跑同一批身份冒充吞吐翻倍。

新增`run_concurrent_gl.sh --workers-per-gpu 1|2`统一管理；`run_seat.sh`参数化当前写死的`XLA_PYTHON_CLIENT_MEM_FRACTION=0.75`。两份服务不能各预占75%后假定显存足够。先依据实际加载、首次编译、Qwen历史与Vulkan峰值确定每路可用配置；单路与双路计时使用相同的每进程内存配置，且先确认相对原单路配置没有行为改变。不改权重、精度、attention、动作块或模型reset来换速度。

三模型×两dataset分别使用同一GPU、同一job的4 CPU/48 GiB配置做对照，双路从实际CPU亲和集合分成两组，录像编码也分开。同一模型在其对照期间不换GPU、依赖或存储。每模型每dataset锁定W：V9为`VideoUnmask 1任务×xhard1×1局 + MoveCube 1任务×xhard4×1局=2局`；xhard0为同两任务`2任务×1档×1局=2局`。这些是代表负载，不能声称覆盖所有任务性能。

对W按**单路→双路→双路→单路**执行；后半反转身份顺序/交换两路归属，每批始终完成相同W。每批每路先预热1局，最先的单任务、单局、单worker预热同时承担smoke，失败即停该候选。另以相同四批做监控开启对照，两套批次先后顺序预先固定并交错安排，不用同一局不同阶段充当监控开关实验。完整数量与预算见第二部分。

测速分开记录启动/JIT、预热、执行、录像核验与NFS收尾。吞吐分子是W中有完整正常终态的局数（success/fail/timeout均算，基础设施error不算有效完成），分母是外层共同开始至所有路录像同步及退出完成的墙钟；不能平均现有`episode_wall_s`代替，它未含`recorder.close`。同时报执行步/秒、模型推理和Qwen推理延迟、CPU占用、显存峰值。

GPU占用按三模型分别给出稳态均值、0%比例、慢步/非慢步分层值，不以中位数或单张截图作结论。只用本轮GPU上的一个持久采样进程，必要字段、500ms间隔；**间隔和持久进程都不代表零干扰**。监控关闭的批次作为速度决策基准；开启批次用于占用诊断和开销对照。若监控明显改变步时/吞吐或驱动锁等待，正式运行关闭它，报告占用数值来自有干扰的诊断条件。

每模型每dataset单独决策：双路必须无状态串扰、无漏重、无基础设施错误，固定输入行为检查通过，且两次无监控配对均至少有**10%端到端吞吐提升（建议采用门槛）**才选2路；否则选已验证的1路。窗口不足或波动太大写“收益未确定”，不自行扩样。原入口hard严格对齐固定单路，其完整新侧D0不为套用并发再重跑；正式V9使用各模型自己的已验证选择，不把FrameSamp的结论直接套给QwenVL。

### 2.9 Great Lakes 完整评估与交付

沿用[上轮V9作业规格](docs/validation/v9-two-policy-gl10-20261002-01/launch.md)：**10个48小时占位job，每个1张A40、4 CPU、48 GiB，account=chaijy2、partition=spgpu**，总计10 GPU/40 CPU/480 GiB。一个job一个`srun`，并发发生在该step内。先用其中3席做三模型测速，其余按阶段分配；上限仍为10席，双路不等于再申请10个job。上一轮JobID已在结果留档中释放，实施时登记本轮新的JobID，不假定旧job可复用。本轮尚未申请任何作业。

两新模型各交付三张独立成绩表：V9 D9、新入口D0、原官方入口D0；原/新hard另交完整逐身份差异表。V9每模型完整800局，新模型不得套用旧两策略“复用720、只补80”的结果；测速、冒烟不混入正式分母。每条正式结果绑定dataset、入口、模型变体、身份、权重/配置指纹、attempt和所属lane；每个身份只接受一个终态，正常fail/timeout不重试。

三套正式结果都保留成功、失败、timeout的视频与日志，基础设施错误尝试已有视频也保留。完成要求是两新模型的`2×(D9+D0+D0)=2368`个正式身份有完整结果、每侧分母正确、视频齐全且可解码，以及独立的原入口严格对齐判定。报告明确区分“运行覆盖完成”“任务成功率”“原入口完全一致”“双路是否提速”，不能相互替代。

# 第二部分（技术细节，供 agent 追踪）

## 一、红线与稳定接口

- 本轮只改本计划。未来实施不修改 `src/robomme/**`、第三方源码与gitlink、环境任务和wrapper；不新增顶层脚本，不删除xhard0历史实现，不重新生成数据。受保护方法若确需新增覆盖，先明确具体锚点并取得相应授权，不用接入适配扩大范围。
- `BenchmarkEnvBuilder(..., dataset="test-hard0")` 是新增公共接口；builder仍不自动按档推断`max_steps`，示例与启动器显式给1300。新分支拒绝`specs_root`和`override_metadata_path`，不消费`ROBOMME_HARD_SPECS_ROOT`。
- `test-hard0` 的 `resolve_identity` 保留 `source_dataset="test"`、`source_episode=3,7,…,47`、`tier="xhard0"`、原seed；`candidate/spec_sha256/source_run`为None。本地索引`0..11`与官方原局号不能混用。
- 官方对照固定为上述MME gitlink中的`EpisodeEvaluator.eval_each_episode/get_action_chunk`、`EnvRunner.get_init_obs/step`、`OracleSubgoalPredictor`、`QwenVLSubgoalPredictor`与`subgoal_prediction/qwenvl/api.py::Qwen3VLModel`。两组只允许所选来源启用，`use_memer/use_gemini=False`；QwenVL 路线不能读取Oracle文字来替代预测。既有提示、历史、调用规则及回复解析均复用原实现，不自拟修词、回退或提前终止规则。
- 公开数据集与内部模式对应：`test-hard`→现有`--v8`身份与1600截断；`test-hard0`→现有非V8身份与1300配置。不匹配时启动前报错，禁止把xhard0伪装成带规格的新值局。

## 二、逐文件接线

| 文件／锚点 | 具体改动 | 默认／新增行为 |
|---|---|---|
| `src/robomme_hard/env_record_wrapper/hard_builder.py::_ALLOWED_DATASETS/BenchmarkEnvBuilder.__init__` | 加`TEST_HARD0`；两种hard入口都以`dataset="test"`初始化父类读元数据；新分支直接`enumerate(_xhard0_entries(...))`，不经过`_test_hard_entries/_root_specs` | 默认V9不变；新接口独立返回xhard0 |
| `src/robomme_hard/env_record_wrapper/__init__.py` | 导出`TEST_HARD0` | 原导出保留 |
| `scripts/evaluation_hard.py`的builder创建处 | 加`--dataset`参数；默认test-hard/1600，test-hard0/1300；视频目录含dataset，避免相同局号覆盖 | 不传参数仍跑原示例范围；显式可选xhard0 |
| 新`scripts/eval-official/mme_official_adapter.py` | 按变体接官方Oracle或QwenVL预测器与单局循环；管理预测器上下文，适配`EnvSession`；见下文合同 | GroundSG两种来源明确分开；原`mme_client.py`保持默认 |
| `scripts/eval-official/env_client.py::build_parser/cmd_run/EnvSession.builder/SeatRunner.builder_for/run_one` | 解析dataset/变体/Qwen adapter；两个建builder点均透传dataset；持有并传递按变体隔离的预测器上下文；记录模型选择 | 旧调用不传dataset时，按原模式推导：V8→test-hard，非V8→test-hard0 |
| `scripts/eval-official/v8_manifest.py::check_source` | V9源集的xhard0期望数跟随现有`xhard0_prefix()`，支持当前800源集；不把该工具改成xhard0导出器 | 修复当前无前缀源集仍被要求含192个xhard0的问题 |
| `scripts/eval-official/run_seat.sh`的解析、MME预检、server/client启动 | 新增dataset/variant/Qwen adapter；server加载两组共用的GroundSG配置；client按变体加载预测器，核Qwen实际运行解释器与本地依赖/缓存，透传离线约束和路径 | 不传variant仍为framesamp；缺Qwen依赖或资产直接报错，不下载或换Oracle |
| `scripts/eval-official/run_v8_gl.sh`参数解析与内层调用 | 透传variant与Qwen adapter、显式dataset=test-hard；拒绝test-hard0，避免无条件`--v8`误校验 | 继续只管V9路线，两组GroundSG均可选 |
| `scripts/README.md`、`src/robomme_hard/README.md` | 写两种dataset、示例命令、局号映射、官方接缝和步数边界；撤销“示例只差3处”的旧描述 | 使用说明与新增参数一致 |
| 新`scripts/eval-official/run_concurrent_gl.sh` | 一个现有占位job的一个srun内启动1或2个独立lane；固定总CPU/内存，分片、端口、PID/PGID、账本、媒体和超时分别管理；支持新入口和原官方hard驱动 | 不增加GPU数，不嵌套第二个srun，不共用有状态server |
| `run_seat.sh::start_server/run_policy/start_client`、`run_v8_gl.sh`参数透传 | 新增显式每进程JAX显存参数、lane标识、CPU子集及端口命名空间；默认旧单路仍0.75，双路必须给已验证资源配置；覆盖`.v8-pgids`和临时目录隔离 | 配置只改资源分配，不改模型算法；恢复不重置累计预算 |
| 新`scripts/eval-official/throughput_benchmark.py` | 固定三模型×两dataset的测速清单、批次顺序、预热/计时/监控状态、端到端时间和决策报告；消费实际终态与同步记录 | 不用成功局数充吞吐，不因失败换身份或自动补样 |
| 新`scripts/eval-official/official_hard_runner.py`、`run_official_hard.sh` | 独立官方原环境和单局流程，外围筛选D0与记录；不调用新适配器，不导入robomme_hard | 两新模型各新增原官方hard完整D0，替代错误的同适配器自证 |
| 新`scripts/eval-official/groundsg_parity.py` | 全D0固定输入和真实闭环的严格比较；独立读取原侧/新侧证据、核完整性与第一处差异 | 无容差自动放行，缺证据即FAIL |
| 新`scripts/eval-official/groundsg_eval_report.py` | 汇总两模型三条正式路线及测速结论；核分母、唯一accepted attempt、错误、视频、严格对齐与总预算 | 不使用`--partial`作终验，不将旧成绩或测速样本混入正式结果 |

### 官方适配对象如何交接

`mme_official_adapter.run_episode(session, identity, conn_info, recorder)`接收当前repo已经选好的环境会话；`conn_info`增加`dataset/mme_variant/qwenvl_groundSG_adapter_path`及仅进程内使用的`policy_context`，继续带host/port/max_steps。构造的runner提供官方所需的`env_id/episode_id/difficulty/task_goal/info`、`get_init_obs()/step(action)`及原Oracle属性；QwenVL分支通过官方预测器的观测接口运行。环境由本repo的builder创建，不由官方runner再建第二个环境。

| `mme_variant` | 客户端路由 | 官方参数／配置配对 |
|---|---|---|
| `framesamp-modul` | 原`mme_client.run_episode` | 原`perceptual-framesamp-modul.yaml`及对应checkpoint，默认行为不变 |
| **`ground-sg-oracle`** | 新适配器→`OracleSubgoalPredictor`→官方`EpisodeEvaluator` | `use_oracle=True`、`use_qwenvl=False`、`subgoal_type="grounded_subgoal"`；`symbolic-grounded-subgoal.yaml`及对应`79999` checkpoint |
| **`ground-sg-qwenvl`** | 新适配器→`QwenVLSubgoalPredictor`→官方`EpisodeEvaluator` | `use_oracle=False`、`use_qwenvl=True`、`subgoal_type="grounded_subgoal"`；同一GroundSG VLA配置与checkpoint，另设`qwenvl_groundSG_adapter_path` |

其余参数沿用官方启动脚本传值和单局默认值，包括`model_seed=7`、`use_history=True`、`obs_horizon=16`、`subgoal_keep_period=1`；host/port由当前启动器提供，max_steps只按所选数据集传入。新增两组在调用官方`build_subgoal_predictor`前检查来源开关互斥，不能让它的优先级选择掩盖多开参数。适配器把官方返回的状态字符串封装成当前`run_episode`结果字典，执行步数取session计数，异常另记；不重判官方的正常成功／失败状态。

Qwen路径透传固定为：`run_v8_gl.sh`（若使用）→`run_seat.sh`→`env_client`→`args.qwenvl_groundSG_adapter_path`→官方`QwenVLSubgoalPredictor.setup_api`。官方参考位置为`runs/ckpts/vlm_subgoal_predictor/qwenvl/grounded_subgoal/checkpoint-1200`，实际传入已核实的本地绝对路径，不读取本仓库在途`runs/`来猜测。官方`Qwen3VLModel`调用`swift.llm.PtEngine`，底座名固定`Qwen/Qwen3-VL-4B-Instruct`，`attn_impl='flash_attention_2'`；保持这些选择，不把普通QwenVL底座当作已加载GroundSG adapter。

预测器运行在环境客户端进程。现有客户端使用`BENCH_PY`，所以必须核实该解释器能加载官方Qwen/Swift及其原有依赖，不能只检查MME server环境。官方当前没有底座本地路径参数；启动前须验证固定底座标识的实际缓存解析和离线加载机制，不能假装新增参数已经能透传。本轮尚未验证该机制；离线缓存或依赖缺失即报告阻塞，不实例化后让库自动联网下载，不回退Oracle。此处只列接入前置条件，不安排安装、下载或变更第三方依赖。

官方顶层`evaluate`在逐局循环之外创建预测器和evaluator；适配层同样由`SeatRunner`持有一次创建的`policy_context`，逐局交给官方`start_episode/step/get_subgoal/end_episode`，进程结束时释放。上下文对象不写入JSON，记录其类型、配置和路径摘要即可。Qwen临时图像根每次绑定到本次尝试独立目录，和最终评估录像分开：官方`start_new_episode`可能清空该目录，`end_episode`会删除局目录，不能传入已有录像或他人目录。`*_QwenVL_log.jsonl`位于局目录父层，应保留；异常或`unknown`早退绕过原生清理时，外层只清理本次登记的临时局目录。跨局状态重置、保持周期、历史与回复转换沿用官方，不额外添加规则。

适配保留官方`get_init_obs/step`的打包和更新顺序，将其环境对象绑定到session；不调用官方顶层`evaluate()`的任务枚举、覆盖目录、续跑与汇总逻辑。本repo继续按自己的清单逐局驱动。第一局和后续局都从本次reset的info开始，场景接线不改图像或动作数值。

官方`eval.py`有裸导入。接缝按变体加载固定源码中需要的原定义，复用本repo `policy_replay.py::extract_defs`已有机制；Oracle分支只需Oracle依赖，**QwenVL分支必须包含`QwenVLSubgoalPredictor`、`Qwen3VLModel`及Swift等实际依赖，不能再把Qwen当成“未用导入”剔除**。加载同时保留官方预处理环境设置`IMAGE_MAX_TOKEN_NUM=256`、`VIDEO_MAX_TOKEN_NUM=64`、`FPS_MAX_FRAMES=10`；Gemini/MemER继续不加载。记录来源摘要并核依赖闭合，不重写函数体、推理参数或回复解析；缺依赖直接报告，不下载或换实现。

官方单局函数会自己创建WebSocket客户端和`RolloutRecorder`，目前没有`client_factory`参数。本方案保留它们，录像目录显式放入本次dataset/variant/episode目录；session继续保留本repo环境侧记录。不修改官方记录器来迁就既有回放器，不声称旧`make_recording_client`自动覆盖新路线。

官方单局函数不返回或关闭客户端实例。适配器只在本次加载的局部命名空间里，用“登记实例后原样返回”的工厂调用官方原生客户端构造器，每局`finally`关闭已登记的`_ws`；不修改第三方模块全局、不改网络协议或循环。网络异常时同样回收连接和环境，完成本仓库记录器收尾，验收覆盖这三项。

```text
原来：env_client → mme_client裁剪循环 → EnvSession → builder(test-hard)
新增：env_client → 官方EpisodeEvaluator原循环 ← 所选官方预测器
                                               ├─ OracleSubgoalPredictor
                                               └─ QwenVLSubgoalPredictor → Qwen3VLModel
                          → runner适配器 → EnvSession → builder(所选dataset)
```

边界不改数：RGB为`uint8[H,W,3]`、每视角`3HW`字节；状态沿用官方`float32[8]`、32字节；子目标原字符串传递；动作形状与dtype保持官方返回和截取规则，运行时记录实值。无新增训练参数，不要求不同模型输出相等。

### 两种身份与结束结果如何分流

xhard0直接沿用已有清单的`task/source_episode/seed/builder_episode`，走`check_identity(v8=False)`；不要求`spec_sha256`，也不走`v8_manifest`。V9继续核规格指纹，重新生成符合当前无前缀builder的索引，不能复用旧含`+12`的992行清单。

xhard0的session设`step_cap=None`，由官方循环和原wrapper结束；V9保留1600截断及`cap_hit`归类。官方runner可能把session抛出的上限异常转换为普通错误，适配入口须先收住该异常/返回值并交回外层，再由`run_one`按既有`cap_hit`认定timeout；`session.close()`和记录收尾必须在finally路径执行，避免原循环异常绕过清理。只改变这条外层交接，不改官方循环的正常执行顺序。

## 三、子代理分配表

仅用于后续获准实施；本轮各代理只读。公共禁触为`src/robomme/**`、第三方及gitlink、其他组文件、真实产物、既有运行和用户在途内容。所有测试在本机已有uv环境执行，不下载依赖。

| 子任务／目标 | 可写文件集合 | 禁触 | 接口契约与依赖 | 整合顺序 | 验收命令与判定 | 资源 | 共享归属 |
|---|---|---|---|---|---|---|---|
| A 数据集 | `hard_builder.py`、对应`__init__.py`、`scripts/evaluation_hard.py`；`test_hard_builder_xhard0.py`、新`test_evaluation_hard_dataset.py` | 公共禁触及其他脚本 | 提供test-hard0与稳定身份；B/C只消费接口 | 1 | `uv run --no-sync python -m pytest tests/lightweight/test_hard_builder_xhard0.py tests/lightweight/test_evaluation_hard_dataset.py -q`；`HARD0_INTERFACE/DATASET_ROUTING` | CPU；无端口/GPU/tmux | builder与示例仅A写 |
| B 官方接缝与环境驱动 | 新`mme_official_adapter.py`、`env_client.py`、`v8_manifest.py`；新`test_mme_official_adapter.py`、新`test_eval_dataset_routing.py`、`test_v8_eval_manifest.py` | 公共禁触；旧mme_client只读 | 消费A；接Oracle/QwenVL两预测器、路径透传、policy_context生命周期、身份分流与异常收尾 | 2 | 三个对应测试；`OFFICIAL_ADAPTER/EVAL_BOUNDARY` | CPU；测试网络及Qwen引擎仅替身 | env_client仅B写 |
| C 启动接线 | `run_seat.sh`、`run_v8_gl.sh`；`test_eval_official_run_seat.py`、`test_v8_eval_orchestration.py` | 公共禁触；不改客户端 | 消费B参数，透传Qwen adapter；预检实际客户端依赖与离线缓存；V9包装器不接xhard0；按dataset/variant隔离输出 | 3 | `bash -n`两脚本；两个对应测试；`EVAL_WIRING` | CPU；假服务随机空闲端口，不加载权重 | 两启动器仅C写 |
| C追加：同GPU多路 | 新`run_concurrent_gl.sh`；新`test_eval_concurrent_gl.py`；C原有启动器和测试 | 公共禁触及B/D/E文件 | 独立lane和资源参数，消费全局预算分配表，不共享server或账本 | 3，与C一起整合 | 假服务验分片无缺重、端口和CPU不冲突、双路退出、单路异常不误杀另路、恢复不增额；`LANE_ISOLATION` | CPU，无真实GPU；随机端口 | 所有启动器与PGID管理归C |
| E 原官方hard与严格对拍 | 新`official_hard_runner.py`、`run_official_hard.sh`、`groundsg_parity.py`；新`test_groundsg_official_hard.py`、`test_groundsg_parity.py` | 公共禁触；B适配器不得作为原侧依赖；旧official_observer只读借用 | 独立官方源与D0；提供原侧完整事件格式、唯一终态与比对判定，异常必须保存证据 | 4 | 源导入与筛选测试、漏帧/重复/动作1bit改变必FAIL；`OFFICIAL_HARD_SOURCE/HARD_FIXED_INPUT_ALIGNMENT` | CPU，模型/仿真均替身 | 原侧驱动与严格比较器归E |
| D 测速与完整报告 | 新`throughput_benchmark.py`、`groundsg_eval_report.py`；新`test_eval_throughput.py`、`test_groundsg_eval_report.py` | 公共禁触；B/C/E文件 | 消费C的lane清单和时间边界、B/E的结果/账本；实现预算、逐路线覆盖与性能决策 | 5 | 批次固定量、预热排除、录像等待、重复/漏记/错误/partial与混模型夹具；`PERF_ACCOUNTING/FULL_REPORT_CONTRACT` | CPU，临时假数据 | 所有总预算、汇总及选并发规则归D |
| 主会话 | 本计划、两份README、`docs/validation/<run_name>/`与索引、本轮运行产物 | 公共禁触 | 统一申请GL资源、固定执行版本与资产、最小smoke、严格hard对拍、测速与正式全量，处理既定停止条件 | 6，实施代码合入并验收后 | 本文全部静态/动态判定；提交和资源收尾 | 后续至多10席A40；tmux前缀`ev-sg-`；预算见§五 | 资源、全局运行清单和提交只归主会话 |

表中未写全的源码文件：builder及`__init__.py`位于`src/robomme_hard/env_record_wrapper/`；评估脚本位于`scripts/eval-official/`；测试均在`tests/lightweight/`。B/C的pytest同样用`UV_CACHE_DIR=<本地缓存> uv run --no-sync python -m pytest <表内对应路径> -q`，不执行裸python/pytest。所有代理不提交、不推送，由主会话核对范围和接口后统一整合。

## 四、验证闸门与实施顺序

1. **静态身份验收**：对新dataset枚举全部`16任务×1档×12局=192`个身份，与已有xhard0清单逐项一致；伪造specs读取函数为“调用即失败”，验证该入口不依赖V9规格。分别检查旧开关开/关下新入口仍为12局，原入口与对应旧行为一致。
2. **独立官方参照**：两组分别运行锁定官方`EpisodeEvaluator`原循环、原runner及所选预测器；另一侧运行本repo新适配路径，不能两边共同调用新适配器。固定同一观测/info/动作回复序列；Qwen测试在测试进程的官方定义命名空间中注入不加载权重的`PtEngine`替身，构造时记录底座/adapter/attention参数、`infer`返回固定回复，保留`Qwen3VLModel`其余原定义、请求构造、历史、保持周期和解析函数。不能只替换真实引擎的`infer`而让构造阶段加载权重。覆盖首帧、演示、子目标跨动作块变化、跨回合reset、异常与结束边界；比较实际序列化后的请求、执行动作dtype/形状/次序/数量及终态。
3. **接线回归**：核两dataset×两新增变体共4种参数路由（零仿真），包括Qwen adapter从启动器到预测器的准确映射、Oracle分支不加载Qwen、Qwen分支不读取Oracle文字代替预测。结果至少记`dataset/mme_variant/subgoal_source`及实际GroundSG checkpoint、预测器adapter身份；不同来源不能混为一列。观测/info、Qwen请求及原始/解析后回复、发给VLA的两项SG字段须可观察，旧FrameSamp记录不能替代。验证预测器只在上下文初始化时加载、跨局原生重置、缺本地资产不联网、临时目录清理不触及录像。
4. **边界验收**：xhard0保持官方1300配置原语义；V9核第1599/1600步成功及第1600步未成功、禁止第1601个真实环境动作；异常也能关闭环境、保存结果。既有`policy_replay.old_mme_module`共享本库循环，不能单独作为新SG官方独立对照。
5. **代码验收**：定向测试及旧默认FrameSamp、V9路线回归总计控制在280秒；超时或缺依赖如实记未完成。还需C/D/E的并发、预算和严格报告夹具；这一阶段不用真实模型。通过后按下面已列的完整动态流程实施，本轮仍不运行。

## 五、真实运行清单与累计预算

建议档案名`v9-groundsg-full-concurrency-gl10-20261003-01`，实施时核未被使用；若改日期或名称，全部路径统一更新，不覆盖旧目录。产物根为本机`artifacts/sg-evaluation/<run_name>/`，GL执行副本与NFS暂存均在已声明共享根的本轮仓库`artifacts/`下。正式三路线、测速、预热、smoke、重试分开，所有计数累加；运行名、资源包络、下表上限在开跑前一次性核定，不分阶段重复申请。

测速W定义见第一部分§2.8：V9为`1任务×xhard1×1局 + 1任务×xhard4×1局=2局`；xhard0为`2任务×1档×1局=2局`。每模型每dataset，监控关和开各做一套ABBA：单路、双路、双路、单路。每套测量`4批×W=8局`，预热为`1任务×1档×1局×(1+2+2+1)=6局`。每模型两dataset均执行，两种监控条件都算预算；不因监控验证而加隐藏回合。

| 用途 | 轨迹尝试上限与乘式 | reset预算 |
|---|---|---:|
| 两新模型V9正式 | `2模型×D9=1600`；D9任务×档位×局数乘式见第一部分 | 3200 |
| 两新模型新test-hard0正式兼对拍侧 | `2模型×16任务×1档×12局=384` | 768 |
| 两新模型原官方hard正式对照侧 | `2模型×16任务×1档×12局=384` | 768 |
| 三模型测速的计时回合 | `3模型×[4批×W(V9)+4批×W(xhard0)]×2监控条件=96` | 192 |
| 测速预热兼新入口smoke | `3模型×2dataset×1任务×1档×1局×(1+2+2+1)×2监控条件=72` | 144 |
| 原官方入口最小smoke | `2新模型×1任务(VideoUnmask)×1档(hard)×1局=2` | 4 |
| 正式基础设施重试 | 在上述正式身份内每新模型全局至多10次、每身份至多追加1次，`2模型×10=20`；不增加新身份 | 40 |
| **总计** | **2368正式 + 168测速/预热 + 2原入口smoke + 20重试 = 2558次** | **5116** |

reset预算以现有正常一局build/reset各1次为基准；原官方runner也要在外围记录实际构造/reset调用，内层多一次就多计一次。模型的reset RPC另记，不冒充环境reset。构造失败、半局、超时、重跑和所有侧均消耗相应上限；固定输入离线回放不调用环境reset，因此不额外占仿真预算，但记录次数和耗时。若正常调用链超出预计2次，停止放量并统一修正预算，不能藏在官方顶层重试里。

测速和监控对照自动重试为0；失败原样记录，该候选停止，不为得到好看时间重跑。正式仅基础设施故障可在20次全局额度内重试；任务fail、执行步timeout、原/新数值不一致不重试。两模型的正式身份、原侧/新侧、预热和测速有独立标识，不拿smoke或最好一次计正式成绩；预算持久化，跨进程重启、换lane不刷新。

预算是本轮后续工作的建议上限；用户已确定两模型完整范围、三模型测速及原hard对齐，本轮尚未发起运行。正式开跑前将所有已知资源、执行名、重试和尝试上限一次核定，不重新询问已经明确的模型和数据集范围。

## 六、同GPU两路的实现合同与测速判据

1. **进程与端口**：`run_concurrent_gl.sh`在一个`srun`内管理`lane0/1`；每lane独立VLA server、client、Qwen上下文与环境。当前官方server全连接共享`self._policy`，reset会改全局RNG和历史，所以两client共连一个server不合格。端口及可选录制代理端口由本轮命名空间分配，启动前探测并校验连接对象；lane、模型、dataset与入口都写入结果。
2. **目录与清理**：路径至少含`<run>/<stage>/<dataset>/<variant>/sNN/laneK/`，独立`.v8-pgids`、ledger、progress、results、录制、Qwen临时文件和同步清单；节点本地目录同样含lane。现有`run_v8_gl.sh`是单个PID/目录状态，不能直接两次后台调用同一个stage。只按登记的PID/PGID及启动身份回收本轮进程；一路错误不误杀另一条，父进程退出要收齐本轮全部子树。禁止按GPU、用户名或程序名全局杀进程。
3. **资源**：旧job每席4 CPU/48 GiB不变；单路用现有合法CPU集合，双路各2核并限制模型/编码线程到其集合，记录原始亲和。显存配置参数要透传到真正的server环境，固定默认0.75但双路不得隐式采用。先在无仿真的已记录输入回放中核同一模型分配变化前后的行为与加载/首推理峰值，再跑预算内smoke；给Qwen、KV、Vulkan、录像余量，不能以两份JAX比例和小于1代替实测。内存不够时报告该双路方案不可用，使用已通过的一路，不擅自扩job规格、量化或改attention。
4. **固定工作量**：每批W的并集完全相同，双路每路分一个身份，后半互换归属；两路的预热各1局，和正式统计隔离。ABBA监控关/开两套的相对顺序按模型/dataset预先交错固化，不能事后择最快批次。需要进程重启时编译/预热成本单列；每个批次所有编码/解码核验与NFS同步完成、子进程退出后才记结束，不能只取环境循环计时。
5. **并发行为**：各模型独立验证固定观测/状态/回复序列及模型返回、执行动作；同一lane的reset/历史不能被另一路改变。真实批次同身份的初始化、执行轨迹和终态差异必须列出；若两路仅因更早失败而显得快，不采纳该提速结论。出现状态污染、缺证据或新增行为差异即`PERF_VALID=FAIL`，不通过扩大容差使双路过关。
6. **监控影响**：关/开是同模型、同dataset、同并发数、同W的独立匹配批次；记录步时、吞吐、CPU时间及驱动锁等待，没有可用采样的字段标未采集。不得仅在不同负载阶段切监控或重复启动全卡nvidia-smi。计时决策使用关闭监控的批次；占用曲线来自开启批次，并附两者差异。启用造成显著退化或无法排除干扰时，正式主线关闭监控，不能宣称诊断曲线为无扰动实况。
7. **逐模型选择**：`speedup = 相同W的单路完整墙钟 / 双路完整墙钟`。两次无监控配对均`speedup>=1.10`、有效性/资源/行为闸门通过，才记录选择2；否则选择已通过的1。每模型每dataset都写`CONCURRENCY_DECISION model=... dataset=... selected=1|2 reason=...`及原始时间；数据不足写`uncertain`并选1保守执行，不自动加测。若单路也不可用则该模型阻塞，不发布可运行结论。即使测得xhard0两路更快，严格原入口D0证据仍用事先规定的单路完整运行，不补跑一套正式分母。

## 七、原官方 hard 的独立执行与完全一致

**来源钉死。** 原官方环境取已有官方源码`856bc3a189d4172f3f47dbee4424d585f8d78db3`；部署前核其`src/robomme`与既有对拍锚点`1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`逐字节一致。[旧预检](docs/validation/v7.5eval/preflight.md)曾验证这两者相同，但本轮仍重新核源，不能只引用历史PASS。不初始化主子模块中被要求为空的第二份benchmark；使用本轮专用只读官方源码根，已有源缺失就阻塞，不下载。

`official_hard_runner.py`是外围身份驱动，不是模型实现：按原metadata筛D0，原侧调用官方`EnvRunner(dataset="test")`与原局号；新侧调用新builder本地局号。官方原方法/参数和源码摘要进入记录。原侧单独进程，启动前和注册环境后都断言`robomme.__file__`来自官方根、`robomme_hard`不在模块中；不能在同一个已注册hard环境的进程里换父类冒充原侧。两侧使用相同客户端依赖栈，不能拿历史sapien3.0.3旧venv与本库3.0.2直接声称全一致。

原侧不能依赖`mme_official_adapter.py`或`policy_replay.old_mme_module`；后者共享本库循环，只换打包函数，无法构成独立参照。历史`official_observer/run_official_mme.sh`硬编码FrameSamp及旧目录，`v75-lanes`也是一次性历史脚本，本轮只借鉴其来源守卫/透明记录机制，不直接复跑。新观测只能包策略客户端与通信接口，不对受保护环境源码做运行时覆盖。

对两新模型的每个D0身份分别核：环境和模型身份；演示/初始观测、state、task_goal与起点；Oracle在线文字，或Qwen原始图像、请求、生成参数、原始及解析后文本；VLA完整请求与返回动作；实际env.step动作；后续观测与终态。原始字节或可还原的无损记录必须可定位，不只留丢失后无法复核的汇总哈希。Qwen路径等非语义差异按预声明映射规范化，但媒体内容、文字、数值与时序不得排除；记录器自身异常、缺帧和少事件直接FAIL。

先做已预算的原入口单任务smoke与固定输入验证；原侧和新侧完整D0都以独立单路采集，分片配对安排在同GPU，不混原/新两侧共驻。比较全量通过才能写`HARD_REAL_ALIGNMENT=PASS`。固定回复夹具只能证明接线，不能代替真实Qwen/VLA一致性；`temperature=0`、同seed或同权重也不自动保证逐位。原/新差异不能用旧MME噪声带免责；保存首个观测/预测器请求/文本/VLA动作/实际执行动作分叉，按真实失败处理，不擅改确定性配置或阈值。

## 八、Great Lakes 运行手册与完整报告

1. 执行获准后，先按[greatlakes.md](greatlakes.md)申请至多10个本轮占位job，让排队与实施并行，登记每个JobID、资源和用途。规格沿用上轮的1 A40/4 CPU/48 GiB/48小时；不复用历史释放清单，不取消其他会话资源。新占位不代表能立刻起模型，代码/资产闸门通过后才运行。
2. 将已提交的实现冻结到NFS执行副本，记录主SHA、MME gitlink、官方环境SHA、两模型及tokenizer身份、Qwen底座/adapter身份和客户端/server依赖指纹。资产只使用已核本地副本，实际导入路径必须匹配；缺失阻塞，不自动下载。计算节点只通过已安装uv环境`--frozen --no-sync`运行。
3. 固化D9、D0和测速W的身份文件、每route/model/lane的互斥分片与预算分配。每份清单保存哈希，配对hard记录`source_episode↔builder_episode`。新模型没有可复用的旧成绩，禁止`--exclude-evaluated/--reuse`把它缩成80局；测速样本不并入正式分母。
4. 一个job只运行一个srun；在其内部串行执行相应阶段，或由`run_concurrent_gl.sh`管理2条lane。原hard参照与新test-hard0严格对照固定1路；三模型性能各在同GPU上比较1/2路；V9正式用每模型通过的选择。`run_v8_gl.sh`仍仅服务V9内层，原hard和新test-hard0由统一外层按route调度各自入口，不给它们强行加`--v8`。
5. 先单任务、单局、单worker的最小smoke，再按预算执行原官方hard完整对照、三模型测速、两新模型V9完整评估。原hard对齐FAIL停止受影响模型后续放量，保存已开始部分和所有差异；正常任务fail/timeout只入分数，不重试。候选双路OOM等失败停止该候选，保留单路已验证选择。任何扩大资源、场景或重跑超预算，统一列变更，不先执行后补记。
6. 所有超过5分钟的阶段进入带`ev-sg-`前缀的detached tmux，保持`PYTHONUNBUFFERED=1`、`pipefail`、`tee`和`EXIT_CODE`；每路监督服务生死与无进度，不只探端口。用零仿真夹具验证成功→下一阶段、失败/监督器崩溃→停止并通知；主会话持续处理宿主等待事件，未建立自动唤醒不得承诺无人值守自动接续。通知只报有意义变化、完成、失败或需处理事项。
7. 汇总按`(route,dataset,model,identity)`接受唯一终态，以持久`accepted_attempt_id`为准，弃用和迟到attempt单列；启动器恢复不得清掉ledger，预先分配预算之和不超总表。原hard及非V8新test-hard0补同等账本，不改变其1300停止语义。禁止原顶层无限重评，所有外层重启也受本表20次基础设施额度约束。
8. `groundsg_eval_report.py`分别输出六个正式结果集合（2模型×3路线），固定分母、逐任务/档位成功率、error/missing/timeout、原hard严格差异及三模型测速选择。现`v8_report.py`基础coverage可在`error_final>0`时PASS，故不能只复用其判定；新终验要求`partial=false`、无缺重冲突、`error_final=0`、成功字段一致、步数边界正确、媒体全量可解码和传输SHA匹配。正常任务失败是有效0分，不影响完整覆盖的通过。
9. 所有正式和已产生的失败尝试视频保留，测速/预热视频独立保存。跨节点搬运以原子完成标记和逐文件SHA核同源，未核前不删除源；NFS只清本轮已核临时副本，本机正式产物不删。执行结束、异常和中断都保存账本/日志/部分报告，再按本轮精确清单收server、lane、tmux与JobID，禁止全局kill或scancel。

拟运行参数示意（仅表达调度方式，未执行；变量必须是核实的本轮绝对路径）：

```bash
# 一席一GPU的48小时占位；工作负载另经srun进入
sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 \
  --gres=gpu:a40:1 --gpu_cmode=shared --cpus-per-task=4 --mem=48G \
  --time=48:00:00 --wrap='sleep infinity'
# 一个step内由新编排器管理1或2路；完整参数在实施CLI和launch.md中固化
srun --jobid="$HOLD_JOB" --overlap --exact --ntasks=1 \
  --cpus-per-task=4 --gpu_cmode=shared \
  bash "$GL_REPO/scripts/eval-official/run_concurrent_gl.sh" \
  --workers-per-gpu "$SELECTED_WORKERS" --run-manifest "$RUN_MANIFEST"
```

| 最终判定 | 必须核对的内容 |
|---|---|
| `OFFICIAL_HARD_SOURCE=PASS` | 原侧官方源、依赖、导入与D0筛选正确，未导入新adapter/robomme_hard |
| `HARD_FIXED_INPUT_ALIGNMENT=PASS` | 两新模型固定输入全链一致；不替代真实运行 |
| `HARD_REAL_ALIGNMENT=PASS models=2 compared_per_model=192` | 每模型`16任务×1档×12局`原/新全量字节与终态一致，缺证据为FAIL |
| `LANE_ISOLATION=PASS` | server/client/状态/端口/目录/预算/清理相互独立，分片无缺重 |
| `PERF_ACCOUNTING=PASS models=3 datasets=2` | 全部既定批次或明确停止原因齐全，分开记录无监控计时、监控诊断和开销 |
| `CONCURRENCY_DECISION` | 三模型各自选择与证据，不把2路设成无条件默认 |
| `FULL_EVAL_COVERAGE=PASS formal=2368 error_final=0 missing=0 extra=0 duplicate=0 partial=0` | 两模型×(D9+D0+D0)，新test-hard0同一份正式结果复用于严格对照 |
| `FULL_EVAL_REPORT=PASS`、`FULL_EVAL_VIDEOS=PASS` | 六集合分母、success字段、步数、视频完整解码/搬运SHA和入口标签正确 |
| `EVAL_BUDGET=PASS attempts<=2558 resets<=5116`、`EVAL_CLEANUP=DONE` | 预算包含所有阶段、错误和重试，资源按归属精确回收 |

## 九、风险、盲区与留档

- 当前源码还不接受`test-hard0`、`--dataset`或`--mme-variant`这些新增接口；本文所有示例都要等实施后才能使用。
- xhard0已有环境对拍支持复用原路径，但不能替代新增接口的映射检查，也不能直接证明新增SG客户端已对齐。
- 官方原生录像与本repo环境记录会并存；是否增加录像开销需实施时如实记录，不能为提速修改官方循环。
- 官方源码定义加载需要依赖闭合与来源校验；目前只有静态可行性，未运行新接缝。不得把计划中的复用说成已经完成。
- QwenVL还需要客户端侧的官方Qwen底座、GroundSG adapter及依赖；本轮只读源码，没有检查或补齐这些运行资产。能通过零仿真接线测试，不等于真实Qwen推理已验证。
- 本轮只对根计划做结构、链接、源码锚点、命令语法与`git diff --check`核对，动态判定全部待执行。只提交这一个文件，保留他人在途状态，按既有upstream推送；若以后实施，在提交正文记录用户原话、接口差异和测试结果，必要验证记录放`docs/validation/`，不在规则文件追加进度。
