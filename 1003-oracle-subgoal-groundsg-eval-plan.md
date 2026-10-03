> **用途**：补充 MME-VLA 的 Oracle 子目标评估方案。本轮只写本文档，不改代码、不下载资产、不提交作业、不启动仿真。用户原话：①「现在只eval了framesample modul我还需要去评估 oracle subgoal  groundSG 给出eval方案 写入根目录文档」。②「不要下载，不要下载，你只写根目录的计划。」本文件按本轮要求放在根目录，覆盖项目默认的 `docs/plans/` 落点；后续资产准备仅是计划，不构成本轮下载授权。
>
> **名称解释**：源码把 Oracle 定义为子目标来源；本方案暂按 **SimpleSG + Oracle、GroundSG + Oracle 两组**展开，等待用户对名称的澄清。这不是三个独立模型，也不包含环境专家轨迹、QwenVL、Gemini 或 MemER。现有 `framesample modul` 指一个组合 `perceptual-framesamp-modul`。
>
> **规划锚点**：主仓库 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，提交 `e01ec6a033bbef93f01801296ba59a8ade29f328`；MME 子模块 `ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b`。实施时另记实际执行提交。读取时有 ` m third_party/SimpleMemVLA` 与 `?? runs/`，本轮不读取其中在途内容、不提交、不清理。提交编号沿用 `12.<小版本>`。
>
> **授权边界**：下文的代码适配、运行名、资源、下载和尝试预算均是建议，需执行前一次性核定；以前两模型运行的授权不自动扩大到新策略。批准完整执行清单后连续执行，不逐阶段重复询问；新增范围或超预算才合并提出补充项。因方案包含后续代码适配，保留两部分结构。

# 第一部分（给人看）

## 一、总览与口径

在当前 V9 同一批场景上，新增 **SimpleSG + Oracle** 和 **GroundSG + Oracle** 两列；每列评完整的 **D = 800 个身份**，共 **2 策略 × D = 1600 个正式回合**。D 的任务、档位、局数乘式见下一节。沿用 1600 个执行步上限、逐回合录像和唯一有效尝试账本；既有 FrameSamp + Modulation 成绩作为历史对照列。

| 项目 | 本方案口径 | 依据 |
|---|---|---|
| 两个新增策略 | `mme_simple_sg_oracle`、`mme_ground_sg_oracle`，各用自己的 checkpoint、目录、账本 | MME `scripts/eval.sh` 的 `symbolic_simpleSG_oracle`、`symbolic_groundedSG_oracle` |
| 评估集 | 当前 `test-hard` 的 V9、43 个任务档位格；xhard1～5，不含 xhard0 | `hard_specs.py::_v9_cells`、`XHARD0_IN_TEST_HARD` |
| 动作与步数 | `joint_angle`；每次决策取前 16 个动作；只数执行段，1600 步未成功计 timeout，第 1600 步成功仍计成功 | 官方 `EpisodeEvaluator`；现有 `EnvSession.step`、`SeatRunner.run_one` |
| 模型设置 | `seed=7`、`obs_horizon=16`、`subgoal_keep_period=1`、`use_history=True` | MME `examples/robomme/eval.py::Args` 和两个 Oracle 启动别名 |
| 评估解释 | Oracle 提供当前在线子目标文字，动作仍由学习得到的 VLA 预测 | `OracleSubgoalPredictor.get_subgoal` |
| 对照 | 现有 FrameSamp + Modulation `39/800 = 4.875%`；SimpleMemVLA `178/800 = 22.25%` 可附列 | [V9 结果](docs/validation/v9-two-policy-gl10-20261002-01/result.md) |
| 不扩展部分 | 不训练、不重新生成数据、不改环境语义、不改网站、不重跑既有两列 | 本轮只要求新增评估方案 |

Oracle 使用环境信息，是带特权信息的参照条件；不能把它与仅靠视觉历史的 FrameSamp 列解释成同输入消融。两种 SG 也分别使用独立训练的权重，差值不是只替换一个文本字段的因果效果。

## 二、完整分母与身份对齐

以下就是 D，来自 [hard_specs.py](src/robomme_hard/env_record_wrapper/hard_specs.py) 的 `_v9_cells`。未列出的任务档位组合不存在，不补齐成 `16 × 5 × 10`。

| 任务组 | 任务数 × 档位 × 每格局数 | 每策略局数 |
|---|---|---:|
| PickXtimes、RouteStick、PatternLock | `3 × 2 档（xhard1/2）× 17 + 3 × 1 档（xhard3）× 16` | 150 |
| SwingXtimes、StopCube | `2 × 5 档 × 10` | 100 |
| VideoUnmask、ButtonUnmask | `2 × 2 档（xhard1/2）× 13 + 2 × 2 档（xhard3/4）× 12` | 100 |
| BinFill、VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、VideoRepick | `7 × 2 档（xhard1/2）× 25` | 350 |
| MoveCube、InsertPeg | `2 × 1 档（xhard4）× 50` | 100 |
| 合计 D | 上述五个乘式之和；每任务跨其有效档位共 50 局 | **800** |

五档分母依次为 **272、272、92、144、20**。各档任务组成不同，不能把跨档总体成功率直接当作难度单调性的证明。

**必须先修清单衔接。** 当前 `export_eval_identities.py::expected_total` 已随 `hard_specs.xhard0_prefix()` 导出无 xhard0 的源集，但 `v8_manifest.py::check_source` 仍要求 `len(ALL_TASKS) * XHARD0_PER_TASK = 16 任务 × 1 档 × 12 局 = 192` 个 xhard0。这使新源集被拒绝。旧 `eval-identities-992.jsonl` 又带每任务 `+12` 的 `builder_episode` 偏移，不能直接传给当前每任务 50 局的 builder。

适配后重新从当前交付规格导出 D，设 `ROBOMME_HARD_XHARD0_IN_TEST_HARD=0`；逐行调用不启动仿真的 `BenchmarkEnvBuilder.resolve_identity` 核对 `task/tier/seed/candidate`，再由交付清单核 `spec_sha256`。新 `builder_episode` 是当前入口索引，不是跨版本身份。历史对照按 **`(task, tier, seed, spec_sha256)`** 一一连接，要求两侧 D 完整相等；不能只按 episode 或 seed 连接。

现有 V9 两模型结果由相同策略的旧 V8 子集与新评子集合成；新 SG 策略没有既有终态。因此本次 **不传 `--exclude-evaluated` 或 `--reuse`**，完整评 D，不能套用旧“只补新场景”的清单。

## 三、Oracle 到动作的机制

### 3.1 权重与子目标必须配对

| 新策略标识 | checkpoint 相对模型根 | `history_config.txt` 的精确内容 | 每次决策读取 |
|---|---|---|---|
| `mme_simple_sg_oracle` | `symbolic-simple-subgoal/79999` | `symbolic-simple-subgoal.yaml` | `info['simple_subgoal_online']` |
| `mme_ground_sg_oracle` | `symbolic-grounded-subgoal/79999` | `symbolic-grounded-subgoal.yaml` | `info['grounded_subgoal_online']` |

服务端仍用 `scripts/serve_policy.py --seed=7 ... policy:checkpoint --policy.config=mme_vla_suite`。`create_trained_policy` 从 checkpoint 父目录读 `history_config.txt`，配置是 `representation_type: symbolic`、`integration_type: context`；后者只是 YAML 字段，`HistoryPi0.__init__` 在 symbolic 路线将实际 integration_type 置为 None，由 `embed_prefix` 使用符号文本输入，不表示仍做视觉记忆的 context 融合。不能保留 framesamp 的 YAML 再换权重。

目前 [mme_client.py](scripts/eval-official/mme_client.py) 的 `run_loop` 已去掉子目标分支，`infer` 只传图像、状态和任务提示。因此新增独立 `scripts/eval-official/mme_sg_client.py`，保留旧客户端，复用其无副作用的打包、WebSocket、录像接口；不直接导入官方 `subgoal_predictor.py`，避免 Oracle 路线引入未用的 Qwen/Gemini 依赖。

### 3.2 取值时序与输入合同

首个决策保留 `session.reset()` 返回的完整 `info`；之后每次 `session.step()` 更新它。**只在动作队列为空、下一次 `infer` 之前**读取对应在线字段，默认每块最多执行 16 个动作。块中子目标改变时仍执行剩余动作，下一决策再更新，和官方 `EpisodeEvaluator.eval_each_episode/get_action_chunk` 一致；不擅自清空动作块或提前重规划。

```text
reset 得到 info₀ → 决策₀ 读取 SG₀ → 执行最多16动作并持续更新 info
               → 决策₁ 读取最新 SG → 下一块动作 → …… → 成功/失败/1600步上限
```

官方协议将选中的同一个字符串同时写入 `simple_subgoal`、`grounded_subgoal` 两键；`TokenizePromptWithSymbolicMemory` 再按 YAML 的 `symbolic_memory.type` 选择。保留这一协议与任务 `prompt`，不把子目标拼接到任务文本代替专用字段。缺键、None 或非字符串必须在推理前报 `ORACLE_INPUT_INVALID` 并停止受影响分支；否则现有 tokenizer 可能静默退回普通任务提示。

`training/config.py::PaligemmaTokenizer.tokenize` 原生会清理首尾空白，将下划线和换行替为空格，再拼接任务、`Current Subgoal` 与动作提示；symbolic 当前上限为 `64×2=128 token`，超长右侧截断并警告。保留这套规则，不扩长或补词；记录 `token_truncated` 及 SG 被部分／全部截断的计数。客户端字段未丢不等于完整子目标都进入模型，截断也不能伪装成运输错误。

`use_history=True` 下仍按官方顺序发送 `add_buffer`；服务端 `MME_VLA_Policy._prepare_mem_buffer/add_buffer` 在 symbolic 模式令 `mem_buffer=None`，历史图像不被编码为视觉记忆。**保留发送行为与“模型没有使用视觉历史记忆”是两件事。** 不加 `--no-use-history`，也不改变观测缓存和 `exec_start_idx`。

GroundSG 取原生在线字符串。`DemonstrationWrapper._compute_segmentation_and_fill_subgoal` 使用分割掩码的**像素整数中心 `<y, x>`**填词，替换值随子目标锁存；不能解释成世界坐标、归一化坐标或每帧最新物体位置。原生空串、`Unknown`、`NO RECORD`、未填模板与 simple 回退都需原样记录、分别统计；不补词、不根据离线 HDF5 或专家未来轨迹替换。若初始或持续异常使分支无法代表有效 SG 条件，停止该分支并保留证据，不能悄悄转成普通提示运行。

### 3.3 改动前后的链路

```text
已有：V9规格 → reset/step → RGB、机器人状态、任务prompt
     → mme_client（无SG）→ FrameSamp+Modulation权重 → 动作块 → EnvSession.step

新增：同一V9规格 → reset/step → 同样的观测 + 最新在线info
     → mme_sg_client按策略取SG → add_buffer → infer（两SG键同值）
     → 对应symbolic权重与tokenizer → 动作块 → 同一个EnvSession.step截断
```

输入边界可直接核验：单帧 RGB 为 `uint8[H,W,3]`，前视与腕视合计 `6HW` 字节；历史前视为 `uint8[T,1,H,W,3]`，`3THW` 字节；`pack_state` 为 `float32[8]`、32 字节，历史状态 `float32[T,8]`、`32T` 字节。图像实际 H/W 和返回动作 dtype/shape 在冒烟记录，不伪造未测值。SG 为 UTF-8 字符串，记原文、字节数与摘要。适配不缩放图像、不改动作值；只新增预期的 SG 输入。模型输出数值与 framesamp 不要求一致，可训练参数改动为 0。

每次决策记录 `policy_id/attempt_id/decision/exec_step`、最新在线字段原文、所选键、两项实际发出的 SG、任务 prompt 摘要、模型返回与实际执行动作摘要。旧 `mme_client.payload_digest` 未覆盖 SG 两键，不能用原运输检查的 PASS 证明 SG 已被发送或消费；新检查要同时核配置选择和服务端 tokenizer 输入。

## 四、资产、并行、预算与时间

### 4.1 资产准备

本轮仅检查了已知本机目录 `/data/hongzefu/robomme_policy_learning_MotionJEPA/v1-store/models/official-mme-vla/`，看到 framesamp-context/modul；未证明全机没有 SG 权重。先核已有可信副本，缺失时仅获取上述两个模型，不下载整个套件。

官方来源为 [Yinpei/mme_vla_suite](https://huggingface.co/Yinpei/mme_vla_suite)，本轮只读元数据核得 revision **`5db4d53ddb98c7f80cab08792dd53d985d712ab1`**。两模型发布为 `79999.zip`：

| 模型 | 下载字节数 | 官方 Git LFS `oid sha256` |
|---|---:|---|
| SimpleSG | 11,551,439,116 | `b90aa063a889cf95c33fdf682f47d4082ae826738e037b68f8a471cd52d272a2` |
| GroundSG | 11,551,449,841 | `4a9577f5afa8e5225cb2e69e3820d4c7e5c7deb18f2ef00c10b4401eab575f94` |

来源为固定 revision 的 [SimpleSG LFS 指针](https://huggingface.co/Yinpei/mme_vla_suite/raw/5db4d53ddb98c7f80cab08792dd53d985d712ab1/symbolic-simple-subgoal/79999.zip)、[GroundSG LFS 指针](https://huggingface.co/Yinpei/mme_vla_suite/raw/5db4d53ddb98c7f80cab08792dd53d985d712ab1/symbolic-grounded-subgoal/79999.zip)。合计 **23,102,888,957 字节，约 23.10 GB**，未下载；解压大小尚未核实。

建议落 `artifacts/sg-evaluation/assets/`，保留可信 ZIP 校验、配置来源和解压后的逐文件 SHA256。拟新增进 Git 的 `scripts/eval-official/sg-assets-lock.json` 绑定 revision、两模型与配置、ZIP 指纹、解压清单与 tokenizer；清单以剔除顶层摘要后的 canonical JSON 自校验。完整校验先验证官方 ZIP 指纹再建立解压清单，不把现场未知权重的自算哈希当成可信来源。后续启动做 size＋首尾各 1 MiB 的 cheap 校验，首次部署做 full SHA256；cheap 不能检测等长文件的中间篡改。

tokenizer 沿用既有可信值 `8986bb4f423f07f8c7f70d0dbe3526fb2316056c17bae71b1ea975e77a168fc6`，固定 `OPENPI_DATA_HOME`，服务启动前核对真正读取的 `big_vision/paligemma_tokenizer.model`。权重、配置、tokenizer 和客户端代码的身份摘要进入每个结果行并由最终报告校验；日志里模型“启动成功”不代替资产身份核验。

### 4.2 资源建议与完整尝试预算

建议与旧 V9 保持 **Great Lakes 10 张 A40，每席 1 GPU／4 CPU／48 GiB／48 小时占位 job**，共 40 CPU／480 GiB。每席固定互斥分片，先 SimpleSG、完全释放后 GroundSG；同卡仅一个 `srun` 评估步骤，server/client/Vulkan 在共享模式内。十席是本次建议，尚未申请；四席可作较慢的资源选项，不通过同卡堆 worker 加速。

建议运行名 `v9-oracle-sg-gl10-20261003-01`，批准时核实未占用，若执行日期变化另定新名。产物用 `artifacts/sg-evaluation/<run_name>/`，正式、冒烟、每席、每策略目录分开。集群副本与 NFS 暂存均在已声明共享根下的执行仓库 `artifacts/` 内；不复用历史 JobID，不覆盖旧运行。

| 用途 | 轨迹尝试上限 | reset 尝试预算 |
|---|---:|---:|
| 正式：2 策略 × D（第二节五个任务×档位×局数乘式） | 1600 | 3200 |
| 冒烟：2 策略 ×〔VideoUnmask × xhard1 × 1 + MoveCube × xhard4 × 1 + SwingXtimes × xhard5 × 1〕 | 6 | 12 |
| 基础设施重试：在上述已列任务／档位原身份内，2 策略各全局最多 10 次，每身份最多追加 1 次 | 20 | 40 |
| **整项累计上限** | **1626** | **3252** |

reset 预算依据现有 `EnvSession.build/reset` 每回合两次配额领取，与旧 V9 实测一致；它不是对所有嵌套调用的无条件证明。冒烟先核真实调用链：构造、显式 reset、内部重试都计入；发现未覆盖的额外 reset，停止放量并修正一次性预算，不偷偷十倍扩容。按席、按策略固定预分配额度，其和不得超表；不转交未用额度，不跨席新建ledger恢复。进程重启必须沿用原分片的持久账本和原预算分配；启动器核对分配摘要，拒绝用新命令行增额，不能重新获得预算。

先跑 `1 任务（VideoUnmask）×1 档（xhard1）×1 局×1 worker`，通过后串行完成其余已列冒烟；正常 fail/timeout 允许通过基础设施冒烟，不挑成功局重试。真实冒烟要求有演示任务的 `demo_frames>0`，且两类 SG 字段经过完整推理链。除表中冒烟外不加额外 reset 对拍、专家 rollout、测速局或 framesamp 桥接重跑。正常失败与1600步 timeout 不重试，只有已分类的基础设施故障可消耗重试额度。

### 4.3 排期估计

旧 V9 的 MME 每席 `MoveCube 1 任务 × 1 档（xhard4）× 5 局 + InsertPeg 1 任务 × 1 档（xhard4）× 3 局 = 8 局` 用时约 5～15 分钟，只是两类任务的历史测量。按此作粗略量级：新两策略各 D、十席平均每席每策略约 80 局，相当于旧每席工作量的 10 倍，两策略串行约 **100～300 分钟**。因此十卡同时可用后建议先预留 **2～6 小时**，不含排队、开发、约23 GB下载和解压；这不是 SG 实测耗时或完成承诺。

SG 的成功率、执行步数及模型计算方式都会改变耗时。实施后只用预算内冒烟与正式前段更新按任务档位的剩余时间，不额外生成测速样本。历史 V9 两模型新评录像约 30.5 GB／160 个回合；按相同平均录像成本，`2×D` 约 305 GB，只作容量量级，建议视频先预留至少 400 GB 并持续核剩余空间，timeout 较多时可能超出。权重压缩包、解压文件及 NFS 暂存另计，不能把400 GB当上界。

## 五、验收与实施顺序

以下是**拟实现并执行的判据**，不是本轮已获 PASS。成功率独立报告，基础设施验收通过不代表任务成功。

| 查什么 | 怎么查／通过说明什么 | 期望判定行 |
|---|---|---|
| 身份与分片 | D、43格、每任务50；逐行resolve与规格指纹相等；两策略同集，分片并集无缺重；历史对照四元组一对一 | `SG_IDENTITIES=PASS per_policy=800 cells=43 xhard0=0 missing=0 extra=0 duplicate=0` |
| 模型确实配对 | 官方来源→本机full校验→节点实际加载→结果行模型摘要，全链匹配 | `SG_ASSETS=PASS policies=2 config_mismatch=0 tokenizer_mismatch=0` |
| Oracle 输入消费 | 序列化后核 reset首帧、跨块变化、两键同值、YAML选键，实际token序列符合原生清洗／拼接／128token截断；甲→乙→甲清除上局状态。dropped只数客户端丢字段，截断另报 | `SG_INPUT_CONTRACT=PASS dropped=0 stale=0 wrong_key=0 cross_episode=0 token_mismatch=0` |
| 截断与冒烟 | CPU夹具验1599/1600成功、1600不成功、1601不进入env；预算内三格实跑，记录动作shape/finite与SG异常统计 | `SG_SMOKE=PASS policies=2 cases_per_policy=3 infra_errors=0 exec_over_cap=0` |
| 唯一完整终态 | 每策略D个accepted；取账本accepted_attempt_id；拒绝冲突、缺失、最终error、partial报告及策略身份不匹配 | `SG_COVERAGE=PASS per_policy=800 error_final=0 missing=0 extra=0 duplicate=0 conflicting_terminal=0 partial=0` |
| 分数正确 | success+fail+timeout=D；task_success与status一致；逐任务／档位／格和总表分母正确，另报历史对照与差值 | `SG_REPORT=PASS count_mismatch=0 success_field_mismatch=0 policy_mismatch=0` |
| 视频保留 | 对2×D个正式终态逐个查完整解码、搬运SHA；失败/timeout也保留，冒烟和废弃尝试另列 | `SG_VIDEOS=PASS expected=1600 missing=0 decode_fail=0 sha_mismatch=0` |
| 预算与收尾 | 汇总全部席位、两策略、冒烟、重试；核日志退出码和本轮进程／JobID清单 | `SG_BUDGET=PASS rollout_used<=1626 reset_used<=3252`；`SG_CLEANUP=DONE outcome=<状态>` |

现有 `v8_report.py::build_report` 的 coverage PASS 未要求 `error_final=0`，且 `--partial` 会放宽缺失；新终验必须显式拒绝这两种情况。仅输出旧 `V8_EVAL_COVERAGE=PASS` 不算本方案完成。

### 子代理分工与合并（简述）

拆成客户端与身份、启动与资产、报告三块，文件不重叠。主会话先固定策略标识与接口，三块并行开发；按客户端→启动→报告顺序整合，每次先审范围和定向测试，整合后再审实际路由及旧策略回归。GPU、预算、集群提交与最终留档由主会话统一负责。Codex 子代理不暂存、提交或推送，不套用其他宿主的模型与提交规则。

| 阶段 | 内容 | 下一步条件 |
|---|---|---|
| S0 | 一次核定两组名称、资产获取、运行名、十席与完整预算；冻结规格和历史对照 | 执行清单获准，输入可追溯 |
| S1 | 确定上GL后先按规约申请本轮占位并记JobID；并行实现三块及资产准备 | 适配定向测试、来源锁、整合审查通过 |
| S2 | CPU合同与接续夹具；最小冒烟后完成表内其余冒烟 | `SG_IDENTITIES/ASSETS/INPUT_CONTRACT/SMOKE` |
| S3 | 固定分片两策略完整评估；逐次记录终态，有限基础设施恢复 | D完整覆盖，未耗尽预算 |
| S4 | 结果、视频、预算核验，输出新增两列与历史参照；留档提交 | `SG_COVERAGE/REPORT/VIDEOS/BUDGET` |
| S5 | 成功、失败、中断均保存证据；只释放本轮资源 | `SG_CLEANUP`，他人资源未动 |

# 第二部分（技术细节，供 agent 追踪）

## 一、红线与接口合同

1. 本轮只创建本文档。后续不修改 `src/robomme/**`、`src/robomme_hard/**`、`third_party/**` 与 gitlink、四个 `scripts/*.py` 顶层入口；不通过 monkeypatch 覆盖环境或子目标生成。不改数据或步数上限。
2. 固定 `policy_id` 为第一部分两值；对应 `subgoal_source=oracle`、`subgoal_type=simple_subgoal|grounded_subgoal`、精确 YAML 与权重。客户端入口 `run_episode(session, identity, conn_info, recorder)`，从 `conn_info['policy']` 选择字段，`max_steps` 读取1600；所有新字段命名在派发前锁定。
3. 新结果增加 `policy_fingerprint`（绑定 checkpoint、YAML、tokenizer、MME gitlink、客户端提交、seed、horizon与来源类型）、`subgoal_type`、`subgoal_source`、`oracle_decisions`、`oracle_trace_sha256`；trace路径单独记录。保留 `attempt_id/accepted_attempt_id/exec_steps/reset_calls/task_success`。身份与策略两种指纹分别核，不能拿其中之一替代另一个。
4. `env_client` 的 V8模式沿用固定分片＋持久ledger，不使用它明确不支持的 `--queue`；不修改 `claim_queue.py`、旧xhard0对拍或旧模型推理循环。
5. 沿用共享环境截断并测试真实调用链。新客户端读到第1600步success即返回；未成功则结束为timeout，绝不调用第1601次底层env.step，不依赖动作块数间接推测。
6. 所有新增命令和判定名是后续接口合同，当前不存在者不得写成现成能力。正式起跑用干净的隔离执行副本；主副本中的两处在途内容保留，不能为求clean而清理它们。
7. SG输入阻塞须贯穿客户端、席位和恢复：`ORACLE_INPUT_INVALID` 返回`run_blocked=True, infra=False`，`SeatRunner.run_identities_v8`先保存错误、录像和持久阻塞类别，关闭环境后退出3，**不accept、不reset下一身份**。启动器收到3不重试该策略；恢复先核策略目录的阻塞标记，不能将它当普通非基础设施终态跳过。修复后明确恢复版本与剩余预算，禁止自动清标记续跑；报告保留阻塞原因并拒绝完整覆盖。

## 二、逐文件改动清单

| 文件／稳定锚点 | 拟改内容 | 旧行为／新行为 |
|---|---|---|
| `scripts/eval-official/v8_manifest.py::check_source` | xhard0期望数跟随`xhard0_prefix()`；明确当前800源集，旧开启模式仍验证192前缀；保留逐格强校验 | 旧模式仍支持；当前关闭模式可生成完整D，不启用exclude |
| 新 `scripts/eval-official/mme_sg_client.py` | 独立SG循环，读取最新info，原生双键协议，异常分类、决策trace与payload校验 | 原`mme_client.py`不改；新策略新增SG |
| `scripts/eval-official/env_client.py::build_parser/cmd_run/SeatRunner` | 新策略枚举与显式模块映射、conn_info和模型来源记录；返回结果绑定新trace；`run_identities_v8`按§一阻塞合同停分支并持久化 | smvla/mme路由不变；两SG不会误入smvla分支，阻塞不会被accept或在重启后跳过 |
| `scripts/eval-official/run_seat.sh::preflight_mme/start_server/run_policy/wall_of/main` | 明确MME家族映射，按policy选checkpoint/YAML/端口；server配置、tokenizer、资产闸门适用于所有MME；核固定预算分配；阻塞退出3不重试、恢复先查持久阻塞 | 不放宽旧framesamp守卫；新两策略独立目录、账本 |
| `scripts/eval-official/run_v8_gl.sh` 参数解析及策略循环 | 扩展policy枚举，显式`--simple-sg-ckpt`和`--ground-sg-ckpt`，将当前分支所选ckpt传给内层；传固定身份源、预算及资产锁 | 原两策略仍可运行；新增两策略同卡串行 |
| 新 `scripts/eval-official/sg-assets-lock.json`、`sg_assets.py` | 可信ZIP/配置来源锁、提取清单、cheap/full校验；启动器调用并把实际摘要传入客户端 | 未锁定或不符即停，不用目录名自证 |
| 新 `scripts/eval-official/sg_report.py` | 调用现有`v8_report`的加载/账本/媒体能力，补两策略指纹、SG trace、error_final=0、partial=false及D校验，生成最终两列/历史配对表 | 不改变旧报告；新终验有独立具名判定 |
| 新／补定向测试 | 下一节各文件集合 | 无仿真测试先过，再跑已预算真实冒烟 |
| `docs/validation/<run_name>/{launch.md,result.md,records/}` 与总索引 | 获准实施后的输入、预算、命令、结果、视频索引、资源清单 | 本轮不建运行档案、不制造实测结果 |

`eval_video_mover.py` 已有 `--policies` 参数，可传新列表，优先直接复用；验证覆盖两新策略路径。网站的策略枚举另有硬编码，本方案不扩展网站。

## 三、子代理分配表

以下是后续获准实施时的写入边界。本轮只派只读探索与文档复核。所有子代理不得触碰其他组文件、真实数据、既有运行和未授权外部仓库；共享文件只有一个负责人。

| 编号／目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖 | 整合顺序 | 验收位置、命令与判定 | 资源占用 | 共享文件归属 |
|---|---|---|---|---|---|---|---|
| A 客户端与身份 | `v8_manifest.py`、`env_client.py`、新`mme_sg_client.py`；测试`test_v8_eval_manifest.py`、新`test_eval_sg_client.py` | 公共红线及B/C文件 | 按§一提供新policy路由、trace、结果字段；消费B提供的锁摘要 | 1 | 本机uv环境，`pytest tests/lightweight/test_v8_eval_manifest.py tests/lightweight/test_eval_sg_client.py -q`；`SG_INPUT_CONTRACT` | CPU，无GPU/端口/tmux | env_client仅A写 |
| B 启动与资产 | `run_seat.sh`、`run_v8_gl.sh`、新`sg_assets.py`、`sg-assets-lock.json`；新`test_eval_sg_launch.py`、`test_eval_sg_assets.py` | 公共红线及A/C文件 | 消费A的policy/conn_info；产可信资产摘要，按策略分预算与端口 | 2 | 本机uv环境，两个新测试；`bash -n scripts/eval-official/run_seat.sh scripts/eval-official/run_v8_gl.sh`；`SG_LAUNCH_CONTRACT` | CPU；假服务使用随机空闲端口，无GPU；不自行下载 | 两启动器仅B写 |
| C 汇总 | 新`sg_report.py`、`test_eval_sg_report.py` | 公共红线及A/B文件；旧报告只读复用 | 消费A/B固定字段，拒绝错误模型、残缺trace、冲突终态与partial | 3 | 本机uv环境，新报告测试；`SG_REPORT_CONTRACT` | CPU，无真实媒体搬运/端口/tmux | 新报告仅C写 |
| 主会话自做 | 本计划、获准运行档案与索引、运行产物 | 受保护源、他人在途内容 | 统一调度、资产获取、CPU整合验收、GPU冒烟、预算与收尾，不能拆成各组独立超量运行 | 4 | 下节运行手册与第一部分验收表 | 拟10GPU；端口从空闲探测分配并记档；tmux `ev-sg-<run_name>-sNN` | 提交、推送、运行总预算归主会话 |

表中相对脚本文件均在 `scripts/eval-official/`，测试文件均在 `tests/lightweight/`。所有pytest都通过 `UV_CACHE_DIR=<本地缓存> uv run --no-sync python -m pytest ...`，不执行裸pytest/python。主会话整合前检查文件白名单、接口和定向测试，整合后复核实际调用链与旧`mme/smvla`测试；只提交本轮内容。发现环境源必须改动时，先交具体阻塞与锚点，不擅自扩大可写集合。

## 四、闸门与运行手册

**CPU必测反例**：800源集可过、打开开关的旧源集仍可过、错用旧episode失败；初始SG不丢、块中SG变化下一块才生效；两配置选键正确；缺字段/None阻塞后下一身份未reset、无重试、无accept、重启仍阻止执行；原生特殊文本和128token截断可追溯；上局SG不串到下局；错误checkpoint/YAML/tokenizer/策略指纹拒绝；1600边界；原样写JSON再读的零计数和trace哈希；重复/迟到/冲突attempt、预算耗尽、进程重启不刷新额度且拒绝修改分配；假服务完成→下一策略与异常→停止/收尾两条完整链。

开发时分别跑上表定向测试，整合后补既有 `test_eval_official_mme_client.py`、`test_v8_eval_client.py`、`test_v8_eval_orchestration.py`、`test_v8_eval_report.py`、`test_v8_eval_video_mover.py`，总计控制在280秒；超时诚实记未完成，不写全量PASS。检查四入口与受保护目录相对实施BASE零diff。

以下命令是**适配完成后的示例**，本轮未执行。先核输出根为本轮实体目录；所有变量在启动留档中换成核实过的绝对路径，禁止覆盖已有输出。NFS安装环境时显式`UV_LINK_MODE=copy`，计算节点仅用预装环境与`--frozen --no-sync`。

```bash
# 本机：从当前V9导出，不使用旧992索引；exporter现有参数。
export ROBOMME_HARD_XHARD0_IN_TEST_HARD=0
export UV_CACHE_DIR=/home/hongzefu/.cache/uv
uv run --no-sync python scripts/injection-dev/export_eval_identities.py \
  --specs-root artifacts/newtask-v9/specs-root \
  --delivery artifacts/newtask-v9/delivery/delivery.local.json \
  --out "$SG_INPUTS/eval-identities-800.jsonl"
# 需先完成check_source适配；不加exclude/reuse。
uv run --no-sync python scripts/eval-official/v8_manifest.py \
  --identities "$SG_INPUTS/eval-identities-800.jsonl" \
  --delivery artifacts/newtask-v9/delivery/delivery.local.json \
  --shards 10 --out-dir "$SG_MANIFEST"
```

身份转换后，另做第一部分第二节的逐行builder与历史对照连接校验，保存源清单、执行清单、交付与规格哈希。`--out`和报告的`--expect-total`已对当前源码核实；拟新增接口由对应子代理实现并测试后才能运行。

GL 严格遵循 [greatlakes.md](greatlakes.md)：核已授权连接；占位用 `--account=chaijy2 --partition=spgpu --gres=gpu:a40:1 --gpu_cmode=shared --cpus-per-task=4 --mem=48G --time=48:00:00 --wrap='sleep infinity'`；负载用 `srun --jobid=<本轮JobID> --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared ...`。十席获准后才提交，不把计划例子当已有资源。

适配后的席位调用固定 `--policies mme_simple_sg_oracle,mme_ground_sg_oracle`，两项专用ckpt参数、资产锁、tokenizer、无xhard0开关和逐席预算必须透传；不能将两个新策略都改名为`mme`。服务健康检查与首个真实推理分开验证，首个推理允许既有编译宽限；持续检查服务PID和进度文件，无进展超时后只在剩余预算内恢复。模型启动最多首启加一次重启；客户端恢复也受持久attempt/infra账本限制，不能用外层重启次数乘大表内预算。

长任务落独立tmux，保留`PYTHONUNBUFFERED=1`、`pipefail`、`tee`和`EXIT_CODE`；资源清单写`launch.md`。结束主回合前若仍有已授权工作，继续使用宿主等待；若依靠自动唤醒，必须有注册成功的证据。没有唤醒不得承诺无人值守自动接续。通知只报完成、失败、需处理事项或有意义变化。

最终报告可复用 `v8_report.py --manifest ... --stage ... --videos ... --out ... --policies <两新标识> --expect-total 800` 的底层统计，但以新`sg_report.py`严格终验为准，不使用`--partial/--reuse`。视频按原有协议完整搬运、核SHA和解码；本轮默认保留本机视频，NFS临时副本只有核实同源与归属后才清。失败同样保存已产出证据，精确回收本轮server、tmux、JobID，禁止全局kill/scancel。

## 五、风险、盲区与留档纪律

| 风险或未验证项 | 处置／停止条件 |
|---|---|
| 用户模型名称尚未确认 | 暂按两组Oracle SG；只影响计划分支，本轮不执行；若另指预测SG或专家Oracle，另核来源和预算 |
| 权重仅查元数据，未加载或解压 | 先核可信来源、实际大小与加载结果；资产闸门失败停，不换模型或回退framesamp |
| GroundSG原生特殊文本／填充回退 | 保留原文、按任务档位统计；不靠客户端修环境，异常不可解释则停该分支 |
| 新客户端的输入正确但模型未消费SG | CPU序列化及服务端transform/tokenizer检查共同证明；真实冒烟补端到端证据 |
| 新旧结果不是同时间同进程测量 | 标签写“历史同身份对照”；不声称逐位复现或严格单因素因果；本轮桥接重跑预算为0 |
| 多卡排队、NFS、编译和录像长尾 | 用实际任务分层耗时更新预测，不承诺十倍加速；不得为提速改dtype、阈值或视频保留范围 |
| 同步或监督器自身失败 | 零仿真夹具验证失败也能停止/收尾；不要把tmux存活当代理自动唤醒 |

启动时在 `docs/validation/<run_name>/launch.md` 固定主仓库完整SHA、子模块SHA、权重与配置锁、tokenizer、规格清单、环境/硬件、完整命令、预算分配与资源清单；结束后在`result.md`写独立成功率、失败/timeout/error计数、Oracle特殊文本计数、耗时、原话、意外与判定行，`records/`只留Git无法恢复的指标、清洗日志和索引，不复制脚本/YAML/权重/视频。更新总索引。

本轮文档验收只做结构、源码参数与链接核对、预算算术、`git diff --check`和改动范围检查，不运行项目测试或仿真。提交仅含本文档，中文标题接续当前版本，按仓库既有upstream推送；现有子模块和`runs/`在途状态保留。所有动态验收仍标为待执行。
