> **本方案只讲接口怎么接。** 本轮只修改这份根目录文档，不改实现、不下载、不安装、不启动评估。此前版本中的模型原理、下载清单、十卡排期和整批评估预算全部移出本方案。
>
> **新增评估配置已明确**：**GroundSG + Oracle** 和 **GroundSG + QwenVL**。两组都使用官方 GroundSG 路线；本方案不再包含此前误写的 SimpleSG + Oracle。现有 FrameSamp + Modulation 仅保留为兼容默认入口。
>
> **用户已定方向**：①「不要下载，不要下载，你只写根目录的计划。」②「我不关心它是怎么具体实现的，这些实现都已经定下来了，我只关心怎么去改现在的这个 repo，让它和官方的这个 evaluation 是对齐的。」③「对的，你的方案里面只需要说这个接口到底是怎么接。然后现在呢，当前 repo 已经没有 XHeart0 了，XHeart0 做了对拍，所以你需要在目前官方的接口中，啊不是，你需要在当前 repo 的接口中除了这个 hard，就是 scripts evaluation hard 里面传入的这个 test hard 之外，再加入一个接口，可以传入 test hard 0，或者说 test hard 什么别的，让我可以去评估 XHeart0。」④「就按照我说的这些去改这个方案，你现在可以直接改。」下文把口述的 XHeart0 对应到现有代码的 xhard0。
>
> **本次模型纠正原话**：⑤「我还需要 evaluate grounded subgoal oracle 和 grounded subgoal 加 Q1 VL 这两个 model，不是你刚才说的这两个。为什么在计划里没有体现到这两点。」⑥「qwenvl不是q1vl」。以⑥的拼写纠正为准，正文统一写 QwenVL；前述原话保留原样。
>
> **锚点与范围**：工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，规划依据 `733fa5000ee23ab06abc147b2097fe529cf76018`；官方 MME 参照为仓库已锁定子模块 `ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b` 的 `examples/robomme/`，不追随远端移动分支。现有 `third_party/SimpleMemVLA`、`runs/` 在途内容不动。实现另行授权；提交编号沿用 `12.<小版本>`。

# 第一部分（给人看）

## 一、要实现的目标

**这次实现两件事：让当前仓库能单独选择 xhard0；让 GroundSG + Oracle、GroundSG + QwenVL 都能通过官方评估流程运行。**

**目标1：增加 xhard0 的独立数据集接口。** 保留 `dataset="test-hard"` 选择当前 V9；新增 `dataset="test-hard0"` 选择已经做过环境对拍的 xhard0。新接口复用现有数据与环境路径，不重新生成场景，不把 xhard0 加回默认的 `test-hard`。

**目标2：接入两组指定模型的官方评估。** 新增 `--mme-variant ground-sg-oracle` 和 `--mme-variant ground-sg-qwenvl`，分别使用官方 Oracle、QwenVL 预测器及同一套 GroundSG VLA 配置。现有 FrameSamp + Modulation 继续作为兼容默认路线。模型实现已经存在，本次要完成的是当前仓库的调用接入。

**目标3：数据集与模型可以独立选择，并验证接入后行为与官方一致。** 最终应支持下面四种组合：

| 模型选择 | `test-hard`：当前 V9 | `test-hard0`：已有 xhard0 |
|---|---|---|
| GroundSG + Oracle：`ground-sg-oracle` | 可以评估 | 可以评估 |
| GroundSG + QwenVL：`ground-sg-qwenvl` | 可以评估 | 可以评估 |

“支持四种组合”是接口目标，不是本轮启动四批评估。xhard0 的接口范围为 **16任务 × 1档 × 12局 = 192局**；V9保留现有有效档位分配，按 `hard_specs.py::_v9_cells` 为 `3任务×2档×17 + 3任务×1档×16 + 2任务×5档×10 + 2任务×2档×13 + 2任务×2档×12 + 7任务×2档×25 + 2任务×1档×50 = 800局`。本轮只改计划，不下载、安装或执行评估。

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

已有xhard0环境对拍作为依据，本次只验证新入口与官方接入。下列均为实施后的判据，不是当前已通过的运行结果。

| 要确认的目标 | 怎么查／通过说明什么 | 判定行 |
|---|---|---|
| 新入口选中原xhard0 | 静态比原episode、seed、difficulty及建环境参数；规格读取函数调用即失败 | `HARD0_INTERFACE=PASS tasks=16 per_task=12 total=192 specs_reads=0` |
| 原V9入口与新入口不串 | 对照同开关状态下的原身份；默认V9保持上文乘式800局，新接口始终只含xhard0 | `DATASET_ROUTING=PASS crossed=0 default_changed=0` |
| 两组模型接入官方流程 | 独立官方参照与新适配路径输入相同，比较请求、执行动作及终态；Qwen引擎用不加载权重的测试替身 | `OFFICIAL_ADAPTER=PASS variants=2 payload_diff=0 exec_diff=0 terminal_diff=0` |
| 步数及错误收尾未改变 | 分别核xhard0原终止行为、V9严格1600边界与异常收尾 | `EVAL_BOUNDARY=PASS hard0_changed=0 v9_over_cap=0` |
| 参数从入口传到底 | 覆盖两个dataset×两个新增模型的4种静态路由，核Qwen adapter到客户端、GroundSG checkpoint到server | `EVAL_WIRING=PASS routes=4 dataset_mismatch=0 variant_mismatch=0 predictor_mismatch=0` |

`192`对应 `16任务×1档×12局` 的静态身份检查，4种路由也是零仿真检查，不安排批量reset或重做已有环境对拍。

### 2.6 子代理分工与合并（简述）

A负责xhard0的数据集和示例入口，B负责官方单局适配及 `env_client`，C负责启动参数。共享文件 `env_client.py` 只由B修改；三组按约定接口并行，按A→B→C整合。每次整合前检查文件范围和定向测试，整合后检查真实调用位置是否完整接上；两份README、最终验收和提交归主会话。策略库全程只读，子代理不暂存、不提交、不推送。

| 顺序 | 内容 | 完成条件 |
|---|---|---|
| 1 | 增加独立 `test-hard0`，保留默认V9接口 | `HARD0_INTERFACE`、`DATASET_ROUTING` |
| 2 | 接入GroundSG + Oracle和GroundSG + QwenVL的官方流程 | `OFFICIAL_ADAPTER`、`EVAL_BOUNDARY` |
| 3 | 贯通启动参数、隔离结果、补使用说明 | `EVAL_WIRING`，旧默认FrameSamp路线回归通过 |

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
| 主会话 | 本计划、两份README；如实施需要的验证记录 | 公共禁触 | 协调字段、审查、整合及提交；不另起批量评估 | 4 | 文档检查、定向回归、范围核对 | CPU，无run_name/作业 | 文档及提交归主会话 |

表中未写全的源码文件：builder及`__init__.py`位于`src/robomme_hard/env_record_wrapper/`；评估脚本位于`scripts/eval-official/`；测试均在`tests/lightweight/`。B/C的pytest同样用`UV_CACHE_DIR=<本地缓存> uv run --no-sync python -m pytest <表内对应路径> -q`，不执行裸python/pytest。所有代理不提交、不推送，由主会话核对范围和接口后统一整合。

## 四、验证闸门与实施顺序

1. **静态身份验收**：对新dataset枚举全部`16任务×1档×12局=192`个身份，与已有xhard0清单逐项一致；伪造specs读取函数为“调用即失败”，验证该入口不依赖V9规格。分别检查旧开关开/关下新入口仍为12局，原入口与对应旧行为一致。
2. **独立官方参照**：两组分别运行锁定官方`EpisodeEvaluator`原循环、原runner及所选预测器；另一侧运行本repo新适配路径，不能两边共同调用新适配器。固定同一观测/info/动作回复序列；Qwen测试在测试进程的官方定义命名空间中注入不加载权重的`PtEngine`替身，构造时记录底座/adapter/attention参数、`infer`返回固定回复，保留`Qwen3VLModel`其余原定义、请求构造、历史、保持周期和解析函数。不能只替换真实引擎的`infer`而让构造阶段加载权重。覆盖首帧、演示、子目标跨动作块变化、跨回合reset、异常与结束边界；比较实际序列化后的请求、执行动作dtype/形状/次序/数量及终态。
3. **接线回归**：核两dataset×两新增变体共4种参数路由（零仿真），包括Qwen adapter从启动器到预测器的准确映射、Oracle分支不加载Qwen、Qwen分支不读取Oracle文字代替预测。结果至少记`dataset/mme_variant/subgoal_source`及实际GroundSG checkpoint、预测器adapter身份；不同来源不能混为一列。观测/info、Qwen请求及原始/解析后回复、发给VLA的两项SG字段须可观察，旧FrameSamp记录不能替代。验证预测器只在上下文初始化时加载、跨局原生重置、缺本地资产不联网、临时目录清理不触及录像。
4. **边界验收**：xhard0保持官方1300配置原语义；V9核第1599/1600步成功及第1600步未成功、禁止第1601个真实环境动作；异常也能关闭环境、保存结果。既有`policy_replay.old_mme_module`共享本库循环，不能单独作为新SG官方独立对照。
5. **实施收官**：定向测试及旧默认FrameSamp、V9路线回归总计控制在280秒；超时或缺依赖如实记未完成。真实模型闭环仍需后续明确执行范围，本轮不运行，不因新增入口重做既有环境对拍。

## 五、风险、盲区与留档

- 当前源码还不接受`test-hard0`、`--dataset`或`--mme-variant`这些新增接口；本文所有示例都要等实施后才能使用。
- xhard0已有环境对拍支持复用原路径，但不能替代新增接口的映射检查，也不能直接证明新增SG客户端已对齐。
- 官方原生录像与本repo环境记录会并存；是否增加录像开销需实施时如实记录，不能为提速修改官方循环。
- 官方源码定义加载需要依赖闭合与来源校验；目前只有静态可行性，未运行新接缝。不得把计划中的复用说成已经完成。
- QwenVL还需要客户端侧的官方Qwen底座、GroundSG adapter及依赖；本轮只读源码，没有检查或补齐这些运行资产。能通过零仿真接线测试，不等于真实Qwen推理已验证。
- 本轮只对根计划做结构、链接、源码锚点、命令语法与`git diff --check`核对，动态判定全部待执行。只提交这一个文件，保留他人在途状态，按既有upstream推送；若以后实施，在提交正文记录用户原话、接口差异和测试结果，必要验证记录放`docs/validation/`，不在规则文件追加进度。
