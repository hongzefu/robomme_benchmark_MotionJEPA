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

## 一、最终要得到的接口

**GroundSG + Oracle、GroundSG + QwenVL 两组各自接入官方评估流程；每组都能选择 `test-hard` 或 `test-hard0`。** 模型配置与数据集是两个独立参数。

| 参数 | 评估哪些场景 | 每任务局号 | 步数参数 |
|---|---|---|---|
| `dataset="test-hard"` | 当前 V9 的 xhard1～5，有效任务档位格保持现状 | `0..49`，跨该任务的有效档位共50局 | 1600，沿用当前 V9 设置 |
| **`dataset="test-hard0"`，新增** | 已有、已做过对拍的 xhard0，即官方 test 中的 hard 子集 | `0..11`，对应官方原 episode `3,7,…,47` | 1300，沿用官方 hard 评估设置 |

`test-hard0` 是本方案选定的新接口名；不再增加同义别名。它独立取 xhard0，不把 xhard0 塞回默认的 `test-hard`，也不需要重新生成数据。

接口覆盖范围：xhard0 为 **16任务 × 1档 × 12局 = 192局**。V9 按现有有效档位分配，完整乘式为 `3任务×2档×17 + 3任务×1档×16 + 2任务×5档×10 + 2任务×2档×13 + 2任务×2档×12 + 7任务×2档×25 + 2任务×1档×50 = 800局`，分组依据 `hard_specs.py::_v9_cells`。这些数字说明接口返回范围，**不构成本轮实跑任务**。

使用方式如下，均为实现后的接口示例：

```python
from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder

# 现有 V9 接口，保持默认行为
v9 = BenchmarkEnvBuilder(
    env_id="MoveCube", dataset="test-hard",
    action_space="joint_angle", max_steps=1600,
)

# 新增 xhard0 接口，复用原来的官方 hard 子集
hard0 = BenchmarkEnvBuilder(
    env_id="MoveCube", dataset="test-hard0",
    action_space="joint_angle", max_steps=1300,
)
```

## 二、从哪里接到哪里

修改分成两条接线，它们在同一个 builder 汇合：

```text
使用示例：
scripts/evaluation_hard.py --dataset test-hard 或 test-hard0
  → robomme_hard.BenchmarkEnvBuilder(dataset=所选值)
  → 对应场景

真实 MME 评估：
run_seat.sh --dataset ... --mme-variant ...
  → env_client：选择数据集、校验本局身份、创建 EnvSession
  → 官方单局评估流程 EpisodeEvaluator.eval_each_episode
  → 本仓库的 EnvRunner 适配对象
  → EnvSession.reset/step
  → 同一个 BenchmarkEnvBuilder 对应的场景
```

[当前 evaluation_hard.py](scripts/evaluation_hard.py) 是带 `DummyModel` 的用法示例；给它加数据集选择，展示用户如何切换场景。真实 MME 评估仍经 `scripts/eval-official/` 启动，不把示例脚本误当成已经接好的 MME 客户端。

### 2.1 数据集接线：复用保留的 xhard0 路径

[hard_builder.py](src/robomme_hard/env_record_wrapper/hard_builder.py) 已保留 `_xhard0_entries`、`resolve_identity` 和 `_hard_env_kwargs` 的 xhard0 分支。只在 `BenchmarkEnvBuilder.__init__` 新增选择：

- `test-hard` 保持现有 V9 分支。
- `test-hard0` 读取官方 test 元数据，直接将 `_xhard0_entries` 枚举为 `0..11`，随后复用现有解析、建环境和包装链。
- 对外身份记 `tier="xhard0"`；真正传给环境仍为 `difficulty="hard"`，seed 原样使用官方元数据。不附加 `sampling_config`、`native_episode_spec` 或新 seed 偏移。

新分支不读取 V9 的 specs；即使 V9 规格目录不可用，xhard0 仍应能构建。旧 `XHARD0_IN_TEST_HARD` 开关保留作历史兼容，默认继续关闭；**新 `test-hard0` 不受它影响**。当前 V9 正式入口固定关闭旧开关，避免两种数据集混在一起。

### 2.2 模型接线：使用官方已有单局评估流程

当前 [mme_client.py](scripts/eval-official/mme_client.py) 的 `run_loop` 为 FrameSamp 裁掉了子目标分支。新增两组都复用官方 `EpisodeEvaluator`：`ground-sg-oracle` 选择官方 `OracleSubgoalPredictor`，`ground-sg-qwenvl` 选择官方 `QwenVLSubgoalPredictor`。二者都设 `subgoal_type="grounded_subgoal"`，与官方 `scripts/eval.sh` 的 `symbolic_groundedSG_oracle`、`symbolic_groundedSG_qwenvl` 对应。

拟新增 `scripts/eval-official/mme_official_adapter.py`：入口仍是本仓库已有的 `run_episode(session, identity, conn_info, recorder)`，内部使用所选预测器、官方参数和环境适配对象调用官方单局评估。两组动作策略都接 `symbolic-grounded-subgoal/79999` 与 `symbolic-grounded-subgoal.yaml`；QwenVL 路线另透传官方 GroundSG 预测器 adapter 路径。现有 FrameSamp 客户端作为默认路线保留，不加入 SimpleSG 路线。

适配对象把 `get_init_obs()`、`step(action)`、当前 `info`、任务与局号等接口接到 `EnvSession`。官方代码继续负责一局内部的调用顺序；本仓库负责选哪一局、结果放哪里以及已有的运行监督。具体字段和导入接缝列在第二部分。

### 2.3 对齐边界：沿用已定步数口径

`test-hard0` 使用官方 hard 的 `max_steps=1300` 和原有终止顺序，不套 V9 的严格1600步截断。官方客户端按 `count > max_steps` 判断超时，因此1300是配置值，可能执行到第1301步；不在此次接线中改掉已对拍的行为。

`test-hard` 的正式评估继续使用现有 `EnvSession.step_cap=1600`，第1600步成功仍记成功。示例 `evaluation_hard.py` 只按数据集向 builder 传1300或1600，保留其原有包装器计数方式；示例不是正式评估的严格截断实现。这几种既有边界分别标注，不把它们宣称为同一终止协议。

## 三、用户最后怎样调用

只改现有 `scripts/evaluation_hard.py`，新增可选参数 `--dataset`，默认 `test-hard`，允许 `test-hard0`；不新建第五个 `scripts/` 顶层入口。

```bash
# 实现后的示例命令，本轮不执行
uv run --no-sync python scripts/evaluation_hard.py --dataset test-hard
uv run --no-sync python scripts/evaluation_hard.py --dataset test-hard0
```

真实 MME 启动参数拆成两个独立选择：

| 参数 | 拟支持值 | 作用 |
|---|---|---|
| `--dataset` | `test-hard`、`test-hard0` | 选择评估场景 |
| `--mme-variant` | `framesamp-modul`（默认）、**`ground-sg-oracle`、`ground-sg-qwenvl`** | 新增的两组正是 GroundSG + Oracle、GroundSG + QwenVL |
| `--mme-ckpt` | 已有、已核实的对应权重路径 | 交给官方 server；配置与变体不符即报错 |
| `--qwenvl-groundsg-adapter` | 已有本地 GroundSG adapter 的绝对路径，仅 QwenVL 路线必填 | 映射到官方 `args.qwenvl_groundSG_adapter_path`，不是传给 VLA server 的 checkpoint |

`run_seat.sh` 支持这两种数据集。现有 `run_v8_gl.sh` 保持 V9 专用，只允许 `test-hard` 并透传变体；xhard0 使用 `run_seat.sh` 的非 V8 路线。结果按数据集和变体分目录，避免相互覆盖；这里不安排下载、集群席位或正式批次。

目录隔离放在调用方指定的运行根：`<运行根>/<dataset>/<mme-variant>/`；其内保留现有 `sNN/mme/` 或单席 `mme/` 布局，使现有汇总和录像搬运仍能读取。不同变体分别调用一次入口，不将它们共写进同一份 `mme/results.jsonl`。

具体选择组合是 `--dataset test-hard --mme-variant ground-sg-oracle`、`--dataset test-hard --mme-variant ground-sg-qwenvl`；需要评 xhard0 时，两组均把 dataset 换为 `test-hard0`。以上是参数片段，其余已有必需参数仍按入口传入，不能直接当完整启动命令执行。

## 四、怎样确认接线正确

xhard0 的已有环境对拍结论继续作为依据，不重做大规模 reset、生成或全量策略评估。新验证只覆盖本次增加的入口、参数传递和官方评估接线。

| 查什么 | 怎么查／通过说明什么 | 拟用判定行 |
|---|---|---|
| 新入口返回已有 xhard0 | 不启动仿真，逐任务比较原 episode、seed、difficulty、环境参数与已有清单；规格读取函数被调用即失败 | `HARD0_INTERFACE=PASS tasks=16 per_task=12 total=192 specs_reads=0` |
| 原 V9 入口保持现状 | 与实施前同开关状态比较任务局数和逐局身份，默认仍为上文乘式800局；新入口不受旧开关影响 | `DATASET_ROUTING=PASS crossed=0 default_changed=0` |
| 官方流程接入不改内容 | 两组分别对照官方原预测器；相同观测/info、固定Qwen底层回复与动作回复，比较完整请求、执行动作及终止结果 | `OFFICIAL_ADAPTER=PASS variants=2 payload_diff=0 exec_diff=0 terminal_diff=0` |
| 边界与错误分支 | 验xhard0原有1300配置的终止行为、V9严格1600边界、缺失字段/网络/记录异常的官方返回与外层归类 | `EVAL_BOUNDARY=PASS hard0_changed=0 v9_over_cap=0` |
| 数据集与模型选择传到底 | 两dataset×两新增变体的4种静态路由全覆盖；Qwen adapter到客户端、GroundSG checkpoint到server，预测器类型和结果标签正确 | `EVAL_WIRING=PASS routes=4 dataset_mismatch=0 variant_mismatch=0 predictor_mismatch=0` |

第一行的192是 `16任务×1档×12局` 的静态身份检查数量，不是192次 reset。上述判定均待实施，不是本轮已完成的动态验证。需要真实冒烟时另定最小执行范围，本方案不自行增加实跑预算。

### 子代理分工与合并（简述）

实施时分三块：A负责数据集与示例入口，B负责官方单局评估适配及环境接线，C负责启动参数透传。先固定字段，再并行修改互不重叠的文件；按A→B→C整合，每次先审写入范围和定向测试，再检查整合后的接线。文档、最终检查和提交由主会话负责，子代理不暂存、不提交、不推送。

| 阶段 | 内容 | 完成条件 |
|---|---|---|
| 1 | 增加独立`test-hard0`与示例参数 | `HARD0_INTERFACE`、`DATASET_ROUTING` |
| 2 | 接入官方单局评估；补dataset透传与身份分流 | `OFFICIAL_ADAPTER`、`EVAL_BOUNDARY` |
| 3 | 补启动参数、输出隔离和使用说明 | `EVAL_WIRING`；旧默认路线回归通过 |

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
