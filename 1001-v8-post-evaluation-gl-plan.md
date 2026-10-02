> **用途与顺序**：本方案接在根目录 [V8 计划](1001-newtask-v8-xhard-gradient-plan.md)全部完成之后，规划在 Great Lakes 上评估 SimpleMemVLA 与 MME-VLA。本轮只新增这份方案，不提交占位作业、不启动评估、不修改原 V8 计划或在途实现。原计划中的 xhard0 两路线评估仍属于原计划，本方案不接管。
>
> **用户原话，按时间顺序**：①「把方案写在根目录，在V8 Plan Markdown之后，开始两个模型的 evaluation 在 Great Lakes 上进行。」②「这是 V8 Plan Markdown 结束之后开始进行。」③「然后告诉我预估的时间，如果我用十个卡去并行的话。」④（2026-10-02，问口径）「是所有的已经生成过验证过的eisde都要evaluate吗?注意我说的是XHARD1234」⑤（同日，定口径，语音转写原样保留）「修改计划凭X号的12345。Xhard0不评」——即只评 xhard1～xhard5，xhard0 不评。
>
> **规划锚点**：工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV8`，读取时 HEAD 为 `ae5b85762de69fbdba0728b4f333409a3047d2dd`（12.298）。这是规划依据，不是最终评估版本；实施时记录 V8 收尾提交、评估适配提交、两个 gitlink 的完整 SHA 与权重清单。提交编号沿用仓库 `12.<小版本>`，提交前重新核对。当前 `third_party/SimpleMemVLA` 有他人在途改动，本轮不读取其修改、不提交、不清理。
>
> **授权边界**：用户明确了后置顺序和 Great Lakes 环境。十卡是本次测算情景；下列具体局数、重试预算、新运行名称及十席申请组成执行前的一次确认清单，不能把 V8 原有生成预算挪来使用。本文件涉及后续代码适配，因此按规则保留两部分结构；本轮交付仍只有 Markdown。

# 第一部分（给人看）

## 1. 总览与已定口径

一句话方案：V8 全部收尾后，冻结 V8 新值档交付集（xhard1～xhard5，不含 xhard0），将同一批身份均衡分成十片；十张 A40 各运行一个环境客户端，每张卡先评 SimpleMemVLA、释放模型后再评 MME-VLA，两个模型各覆盖这批新值档身份一遍。

1. **开始时间**：必须等 V8 阶段 1、2、2b、3、3′、3b、4 全部完成并留档，包括换包、xhard0 原计划评估、二次生成及站点检查；不能以 gen1 已完成、站点已生成或 GPU 空闲代替。H2 若存在原计划允许保留 gen1 的正常失败，按原计划预定动作留档即可；不要求把已有 FAIL 改为 PASS，也不将未处理的身份、依赖或产物错误当作收尾。
2. **两个模型**：SimpleMemVLA 官方 RoboMME 权重与 MME-VLA `perceptual-framesamp-modul/79999`，依据现有 `scripts/eval-official/run_seat.sh`；不是 motion/50000 模型。执行前核实最终来源与权重字节，不能仅凭目录名认定相同。
3. **范围（用户 2026-10-02 定）**：只评 V8 新值档交付集 xhard1～xhard5（16 任务 × 43 格，1070 局），**xhard0 不评**；两模型各一遍、单一冻结身份集。xhard0 已由 V8 阶段 3′ 两路线评估覆盖（768 局全部取得终态，见 `docs/validation/newtask-v8/result.md`），本轮不复测、不进分母、不作对照列。此范围用于下述耗时估计，尚不启动。
4. **步数**：交付的 xhard1～5 一律 1600（本轮不评 xhard0，其 1300 不涉及），沿用 V8 最终 `hard_specs.TIER_MAX_STEPS` 和 builder 语义。交付专家 h5 不超过 1600 不代表策略能成功；按冻结的客户端与环境终止语义记录 timeout、`task_success=false`，不宣称严格截断外部动作数。
5. **分数**：每任务、每档分别报告成功率及固定分母，另报全局微平均、任务宏平均、错误数、超时数；缺失不得消失在分母里。记录独立 `task_success`，执行成功不等于任务成功。不为提高成功率重跑正常失败。
6. **范围不外溢**：不改官方 `src/robomme/`、录像器和模型实现；不启动额外采样生成；本次不含把评估视频填回 V8 网站的改造，结果先按留档与媒体索引交付。

### 1.1 每个模型的身份数

| 任务组 | 难度与每格局数 | 每模型局数 |
|---|---|---:|
| PickXtimes | 1 任务 × 3 档（xhard1～3，每档分别 17／17／16 局） | 50 |
| SwingXtimes、StopCube | 2 任务 × 5 档 × 10 局 | 100 |
| VideoUnmask、ButtonUnmask | 2 任务 × 4 档 × 20 局 | 160 |
| BinFill、VideoUnmaskSwap、ButtonUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、PickHighlight、VideoRepick | 7 任务 × 2 档 × 40 局 | 560 |
| RouteStick、PatternLock | 2 任务 × 3 档（每档分别 27／27／26 局） | 160 |
| MoveCube、InsertPeg | 2 任务 × 1 档（xhard4）× 20 局 | 40 |

记上述完整乘式为 **D**：`1×(17+17+16) + 2×5×10 + 2×4×20 + 7×2×40 + 2×(27+27+26) + 2×1×20 = 1070`。正式评估为 **2 模型 × D = 2140 个策略回合**，不是每模型重复两遍；43 个任务档位格，全部是新值格。按档拆分（取自包内 `hard_specs.EXPECTED_CELLS`）：xhard1 14 任务共 411、xhard2 14 任务共 411、xhard3 7 任务共 128、xhard4 6 任务共 100、xhard5 2 任务（SwingXtimes、StopCube）× 10 = 20，合计 1070。`round` 若在历史文件中出现，不解释为整套重复次数。

## 2. 十卡并行的时间估计

**十张 A40 同时可用、环境预装完毕后，评估运行预计 4～6 小时，排期预留 7 小时。** 不含集群排队、V8 剩余实施与生成时间；评估适配开发、依赖修复不在这个运行时长里。完整流程从现在起的结束时间尚不能确定。

依据是本仓库 [0929 评估提速方案](0929-eval-throughput-plan.md)第一部分的 A40 历史记录：V7 的十分片每轮 SimpleMemVLA 为 100～147 分钟、MME-VLA 为 40～58 分钟；每片共两段身份轮次。V7 单模型身份数为 `16×1×12 + 13×3×20 + 16×1×20 = 1292`，身份分布与 V8 不同。

```text
历史每卡累计时间 = 2 × [(100～147) + (40～58)] 分钟
                 = 280～410 分钟 = 4.67～6.83 小时
按身份数粗缩放   = 上式 × 1070 / 1292
                 ≈ 3.87～5.66 小时
加模型启动、尾片不均衡与结果核验余量：约 4～6 小时，预留 7 小时。
```

交叉核对：同一历史文档记 SimpleMemVLA 累计 146146 秒，即约 40.6 GPU 小时；按 1070/1292 粗缩放后十卡均衡为约 3.36 小时。MME 历史分片累计约 1.33～1.93 小时，同比例缩放为约 1.10～1.60 小时，两者相加约 4.5～5.0 小时，与上述范围同量级。这两种算法共用历史来源，不是两次独立实测。

V8 将新值档上限由历史最高 3800 降到 1600，长失败局可能缩短；同时任务配比、演示长度、编译、reset 与录像成本会改变。**不按 1600/3800 直接缩放整轮，不承诺接近十倍加速。** 10 卡共读 NFS 也可能让加载和录像更慢。正常错误和基础设施重试偏多时可能超出 8 小时。

实施时使用正式运行首批已预算的回合计时，不额外生成测速局。按模型与任务档位统计已完成耗时和剩余身份，报告 `预计剩余时间 = 最慢席位的剩余预计工作秒数 + 收尾余量`；标明尚未观测的格，不拿最快的一局代表全体。

## 3. 为什么需要适配，怎样保持模型行为

现有 `scripts/eval-official/env_client.py::check_identity` 明确只接受 `XHARD0`，`SeatRunner.base_record` 也把档位写死，`source_episode` 必须转整数；新值局这个字段可以为空。V8 的 `export_eval_identities.py::main` 输出 JSONL 的 `episode`，现有客户端 `cmd_run` 读取 JSON 数组并期待 `builder_episode`。因此不能把 V8 清单直接传给旧启动器。

规划的适配只发生在 benchmark 侧：把 JSONL 中的 `episode` 显式映射到 `builder_episode`，保留 `tier/seed/candidate/source_episode` 与规格指纹；构造环境前用 `builder.resolve_identity` 逐键核对，按档位获取步数上限，随后由现有模型客户端推理。xhard0 旧身份格式仍须兼容。每局模型 reset 沿用已验证路径；未有证据时不能声称常驻与重启逐位一致，也不为提速新增 batch 推理或更换模型精度。

```text
当前：xhard0 JSON 数组 → 固定档身份检查 → 1300 步客户端 → 原模型 → 动作 → env.step
后续：V8 JSONL → 十片身份 JSON → 逐格身份和规格检查 → 按档 1600（清单出现 xhard0 即拒绝）→ 原模型 → 动作 → env.step
```

这一变化改变身份路由和预算，不新增可训练参数；模型输入输出的数据格式、dtype、形状及动作值不应在适配层改动。具体张量形状与字节量沿用两策略原接口，在适配测试和运行记录核实，不凭规划填写未测数字。不同 V8 场景导致不同观测是预期行为，不要求与旧场景逐位相同。

**步数语义边界**：`mme_client.py` 沿用的循环按 `count > max_steps` 判停，`smvla_client.py` 按 `ceil(max_steps/16)+2` 控制动作块。这里的1600指传给 V8 builder 与客户端的约定预算，不宣称客户端外部动作数或底层 `env.step` 次数严格不超过同一数字。本方案保留原循环与 V8 wrapper 语义，记录三者实际计数、验证终止边界；若要严格截断动作块，属于评估协议变化，须另作明确决定，不能悄悄改模型客户端。

十席各一张 A40、4 CPU、48 GiB，合计 10 GPU／40 CPU／480 GiB，均为 `chaijy2/spgpu` 的 48 小时占位作业。每席先 smvla 后 mme，任何时刻该卡只有一条评估链；server、client、Vulkan 在同一共享模式步骤内运行。分片按历史任务耗时做贪心均衡，两模型使用相同身份分片。不复用旧 V8 JobID，不擅自取消旧席位；到启动时再核实是否已有明确可转交资源，否则申请本轮新席位。

### 3.1 子代理分工与合并（简述）

身份与结果适配、十席编排可以按不同文件并行；汇总依赖身份字段契约，测试跟随各自责任文件。先整合身份适配，再整合编排，最后整合汇总。每块先检查越界与定向测试，整合后再检查跨模块契约；主会话负责真实冒烟、作业清单、最终验收和提交。子代理不提交、不推送。具体写入边界见第二部分分配表，本轮不派实施型子代理。

## 4. 验收与实施顺序

以下是拟新增的验收契约，尚未执行，不能把表内期望行当作已有 PASS。

| 查什么 | 怎么查、通过意味着什么 | 期望判定行 |
|---|---|---|
| V8 真正收尾 | 核对原计划全部阶段报告、换包提交、H2 预定处置和站点证据，不能只匹配完成字符串 | `V8_PREREQUISITE=PASS unresolved=0` |
| 模型与数据身份 | 比较可信权重清单、gitlink、规格哈希与实际导入路径，钉死运行对象 | `V8_EVAL_INPUTS=PASS policies=2 identity_count=1070` |
| 分片完整 | 按 D 核对43格（xhard0 身份数必须为 0），十片两两不交且并集等于原集 | `V8_EVAL_SHARDS=PASS shards=10 missing=0 extra=0 duplicate=0` |
| 适配与小规模实跑 | JSONL 往返、nullable 字段、xhard5、上限边界和单 worker 真推理；不要求策略成功 | `V8_EVAL_SMOKE=PASS infra_errors=0 identity_errors=0` |
| 两模型覆盖 | 每模型按 D 核对逐身份唯一终态，错误单列；覆盖通过不表示所有任务成功 | `V8_EVAL_COVERAGE=PASS policies=2 missing=0 extra=0 duplicate=0` |
| 结果与媒体 | 对独立成功字段、退出码、视频终态/解码、报告分母交叉核对；无录像的错误行须明确说明 | `V8_EVAL_REPORT=PASS count_mismatch=0 media_unexplained=0` |

| 阶段 | 内容 | 进入下一步的条件 |
|---|---|---|
| E0 | 等 V8 全部结束，冻结输入；一次确认执行清单 | `V8_PREREQUISITE`、运行名和预算获准 |
| E1 | 申请十席并记录 JobID；实施客户端、启动器、汇总适配 | 定向测试与范围审查通过 |
| E2 | 最小单 worker 冒烟，再检查十席运行环境与端口 | `V8_EVAL_INPUTS`、`V8_EVAL_SMOKE`、`V8_EVAL_SHARDS` |
| E3 | 十席正式评估；失败按类型记账，保留固定分母 | 每身份最终状态与实际尝试账本齐全 |
| E4 | 结果、视频、退出码与预算核验；留档提交 | `V8_EVAL_COVERAGE`、`V8_EVAL_REPORT` |
| E5 | 按本轮清单释放自己的 JobID | 原作业和他人资源不受影响 |

# 第二部分（技术细节，供 agent 追踪）

## 1. 红线、来源与待验证项

- 不修改原 V8 计划、V8 在途源文件、`src/robomme/**` 或两个策略子模块。受保护目录需要改动时另列具体锚点，不能通过运行时覆盖绕过。
- 不执行旧 `v75-lanes/gl/seat_run.sh`：它硬编码旧 worktree、旧产物位置并包含裸 `python3`。新编排必须使用显式 V8 锚点、当前存储边界和 uv。
- MME 候选 NFS 权重为 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v75eval/ckpt/mme/perceptual-framesamp-modul/79999`；SimpleMemVLA 候选为 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA/checkpoints/simplememvla_robomme`。依据现有 GL 启动脚本，**本轮未验证路径存在、完整性或最终可加载性**。MME 同时核对父目录 `history_config.txt` 与 `params/assets`，指纹须有独立可信期望值，现场自算仅能记录当前字节。
- GL 工作副本以仓库约定 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl` 为基准；执行前确认其归属与状态，不能覆盖其他会话改动。产物落该工作副本 `artifacts/v8-evaluation/<run_name>/`，本机收回到本仓库同一相对根。
- 建议新运行名 `v8-two-policy-gl10-20261001-01`，执行前确认未占用并在一次清单中批准；不能覆盖已有目录。档案放 `docs/validation/<run_name>/`，首次实际启动前记录代码、权重、规格、资源和命令。

## 2. 按文件的拟改动清单

| 文件与稳定锚点 | 拟改动 | 保留行为／依赖 |
|---|---|---|
| 新增 `scripts/eval-official/v8_manifest.py` | 读取 V8 JSONL、映射 `episode`、核43格与规格指纹、拒绝 xhard0 身份、输出十片 JSON 和总清单 | 原 `export_eval_identities.py` 不改，原清单 round/shard 为空不受影响 |
| `env_client.py::check_identity`、`SeatRunner.base_record`、`builder_for`、`run_one`、`parse_canary` | 新增显式 V8 模式；档位不写死、nullable 字段严格匹配、按档步数、结果保留完整身份 | 旧 xhard0 默认行为和旧 CLI 保留；builder 缓存须按有效上限区分，避免跨档沿用旧值 |
| `smvla_client.py::run_episode` 的 reset 重试入口 | V8 模式下禁用内部自动重试（`retries=0`），每次实际 reset 前领持久额度并记录；异常返回外层统一分类 | 当前 `RESET_RETRIES=2` 代表首试加两次重试，共最多3次；旧模式保持原值；不修改模型推理与动作块循环 |
| `run_seat.sh` 参数解析与客户端启动段 | 透传 V8 模式与重试额度；整合预算不能因进程重启清零 | 原模型启动、reset、清理逻辑保持；新值冒烟不走官方 episode 推导公式 |
| 新增 `scripts/eval-official/run_v8_gl.sh` | 读取固定清单，十席独立输出、tmux 与 srun 编排、进度监督、退出记录 | 不嵌入旧 JobID、工作副本 SHA 或 `/data` 权重默认路径 |
| 新增 `scripts/eval-official/v8_report.py` | 固定身份去重与终态检查，任务×档成功率、错误与预算报告、视频索引 | 不用缺失默认零制造成功；每次尝试保留、不覆盖原错误 |
| 新增 `tests/lightweight/test_v8_eval_{manifest,client,report}.py` | 格表/身份/上限/错误/媒体合同测试及真实 JSON 往返 | CPU 合成夹具不触发仿真，不改变受保护目录 |

## 3. 子代理分配表

表中是后续实施分工，不是本轮写入授权。全部禁触 `src/robomme/**`、`src/robomme_hard/**`、子模块、依赖配置和 V8 原计划；每个共享文件只有一个负责人。

| 编号／目标 | 可写文件集合 | 接口契约与依赖 | 整合顺序 | 验收地点、命令与判定 | 资源及共享归属 |
|---|---|---|---|---|---|
| E-A 身份及客户端 | `v8_manifest.py`、`env_client.py`、`smvla_client.py`（只限reset重试记账）、`test_v8_eval_manifest.py`、`test_v8_eval_client.py` | JSONL→JSON；完整身份、nullable 字段、逐档上限和持久尝试账本；依赖最终 V8 包 | 1 | 本机 uv 定向 pytest；`V8_EVAL_ADAPTER_TESTS=PASS` | CPU，无端口；env_client与smvla_client唯一负责人 |
| E-B GL 编排 | `run_seat.sh`、`run_v8_gl.sh` | 先冻结 E-A 的 CLI 契约；持久尝试额度；与 E-A 可并行开发 | 2 | 本机 `bash -n`，零仿真假服务覆盖成功、超时、server死、监督进程死；`V8_EVAL_ORCHESTRATION=PASS` | CPU；真实端口由主会话分配；run_seat 唯一负责人 |
| E-C 汇总 | `v8_report.py`、`test_v8_eval_report.py` | 消费 E-A 的身份与结果协议；零缺失/正常失败/错误/重复/迟到均覆盖 | 3 | 本机 uv 定向 pytest；`V8_EVAL_REPORT_TESTS=PASS` | CPU；报告文件唯一负责人 |
| 主会话 | 本计划、`docs/validation/<run_name>/` 和索引；运行产物 | 顺序接收 E-A/B/C，审查文件范围、测试、提交后再真实运行 | 4 | 定向短测及第一部分验收表 | 十张 A40；tmux 前缀 `ev-v8-`；同一卡只有一个 srun 评估步骤 |

## 4. 尝试预算与一次确认清单

这是**本轮后续评估的建议预算**，不与 V8 原预算混用。D 的任务×档位×数量乘式见第一部分；策略评估回合按 rollout 记账，回合内 reset 同时计入 reset 预算，两类计数分别核算。

| 用途 | 回合尝试上限 | reset 上限 |
|---|---:|---:|
| 冒烟：2 模型 × 1 任务（SwingXtimes）× 2 档（xhard1、xhard5）× 1 局 | 4 | 8，暂按每回合最多2次底层 reset |
| 正式：2 模型 × D（D = 1070，乘式见第一部分 §1.1） | 2140 | 4280，同口径 |
| 基础设施重试：2 模型 × 每模型全局最多10次；每身份至多重试1次 | 20 | 40，同口径 |
| 合计 | 2164 | 4328 |

上表以 **V8 模式关闭内部 reset 自动重试（`retries=0`）** 为前提；现有 `RESET_RETRIES=2` 实际最多调用3次，不能原样带入本表。现有 reset 捕获所有异常的重试改为 V8 模式返回外层分类：正常场景失败不得重试，只有明确的基础设施故障可消费全局20次额度。底层 reset 的两倍系数仍是**待验证的设计限额，不是当前代码的实测事实或已证上界**；最小冒烟先记真实嵌套调用，若单次正常回合会超2次，先修正预算并一次说明，不能直接放量。现有启动器客户端重启8次／server重启2次、客户端 infra retry 均不能各自放大本表；它们必须受同一持久账本约束，达到上限立即停受影响部分，重启不得刷新次数。模型加载失败但未开环境，不算 rollout/reset，仍记录启动次数；初始化最多每席每模型首启加一次重启，不无限等待。

冒烟独立于正式统计，不把冒烟成绩当作额外正式样本。额外金丝雀预算为零；十席先做不触发 reset 的输入与服务检查，再执行其分配的正式首局。正常终止、策略失败、到步数上限不重试；基础设施故障只重试原身份，不换 seed，不递补新场景。

执行前一次确认：①两模型和权重版本；②完整 D、两模型各一遍及上述尝试上限；③十张 A40、每席4 CPU/48 GiB/48小时；④新 run_name；⑤适配文件清单与子代理写入边界。旧 V8 已批准预算不自动覆盖本表。此时再集中提出未知项，不分阶段重复申请同一授权。

## 5. 运行手册与闸门

下列是未来执行步骤，本轮未运行。先按 `AGENTS.md` 做环境核对，读取最终 V8 报告；确认完成且预算获准后，按 `greatlakes.md` 复用已认证连接、申请占位席。十席超过默认四席，须包含在上述一次确认中。

```bash
# 在 Great Lakes 登录侧，每席一次；名称带本轮 run_name 和席号，记录 sbatch 返回的 JobID。
sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 \
  --gres=gpu:a40:1 --gpu_cmode=shared --cpus-per-task=4 --mem=48G \
  --time=48:00:00 --wrap='sleep infinity'
# 占位得到后才派工作负载；实际脚本及参数在适配完成时固化到 launch.md。
srun --jobid=<本轮JobID> --overlap --exact --ntasks=1 \
  --cpus-per-task=4 --gpu_cmode=shared bash <已验证的V8运行器> <本席参数>
```

1. 清点真实工作副本、uv 管理的解释器与权重路径。`UV_LINK_MODE=copy`，显式 `UV_CACHE_DIR=$HOME/.cache/uv`；模型及其他持久缓存落本轮 `artifacts`。计算节点只用 `uv run --frozen --no-sync` 或已核验的 uv venv 解释器，不现场安装。若从编排作业派发，清除继承的 `SLURM_*` 后再显式指定目标 JobID。
2. 在 clean、固定提交的执行副本运行；主检出的子模块在途修改不能带入，不能替别人提交或清理。本机与 NFS 通过 rsync 同步输入，核 SHA256；记录实际 import 路径，不能误用旧包。
3. E-A 输出十片及 manifest，并保留原 JSONL 哈希。每模型身份集合必须等于 D（1070，43 格）；清单含任何 xhard0 身份即停。不重新生成或重新抽签。xhard0 本轮不评。
4. 先跑冒烟表的第一项（1 模型×1任务×1档×1局、单worker），通过后串行完成剩余三项。核对真实 reset 次数、上限、模型 reset 和结果格式；失败不直接启十卡。
5. 十席 tmux 命名 `ev-v8-<run_name>-s00`～`s09`；独立输出 `<root>/sNN/<policy>/`。端口按 `18000 + 100×席号 + 10×策略号` 起，先探服务与相邻端口，冲突有限次换位。server就绪与首次推理分别设超时，不能把监听成功当作首次推理可用。
6. 每任务命令用 `PYTHONUNBUFFERED=1`、`set -o pipefail` 和 `tee`；结果持久化后写 `EXIT_CODE`。持久监督器覆盖主进程死亡、无进展、日志/报告写失败；独立测试监督器自身崩溃的通知路径。不得仅凭 tmux 存活宣称有自动唤醒；本轮未注册后台启动或唤醒。
7. 结果齐全后运行汇总，核每格分母、终态、退出码、预算及媒体；录像结束后再解码检查。若回传本机，用 rsync 并比 SHA256，源文件删除须有明确授权，本方案不预授权删除。
8. 留档后只释放本轮 JobID，tmux 只按精确名称逐个清理；禁止全用户取消和全局杀 tmux。

测试命令模板：核实 `command -v uv`、`pyproject.toml`、`uv.lock` 后，以显式缓存目录运行 `uv run --no-sync python -m pytest tests/lightweight/test_v8_eval_manifest.py tests/lightweight/test_v8_eval_client.py tests/lightweight/test_v8_eval_report.py -q`；这些测试文件是拟新增项，当前不能直接运行。真实冒烟只在 E2 进行，计入上表。

## 6. 风险与盲区

- **耗时不是实测保证**：4～6小时来自 V7/A40 历史分片；排队未知、V8 分布变化和 NFS 争用尚未测。本轮没有登录 GL 查询空卡。
- **推理等价未扩大承诺**：沿用现有模型实现不自动证明不同机器、常驻与重启逐位相同；如缺必要验证则在 E2 阻塞相应优化，不用成功率一致替代动作一致。
- **reset预算须落到实际入口**：底层演示生成可能含额外 reset；入口隐含重试也可能放大次数，必须在冒烟实测并限制。
- **运行器能力缺口**：当前 xhard0 客户端不能直接评新值档；拟新增判定行、十席控制器、完整媒体汇总尚未实现。
- **原计划在执行**：读取锚点是阶段2收尾提交，不能由此认定V8完成；后续一定重新核实阶段3、3′、3b、4的证据。
- **十卡资源只是情景**：不将旧7个占位作业视为本轮十张可用卡；排队、到期、配额和转交都需到执行时核实。

## 7. 留档与提交纪律

本轮只提交本文件，执行 `git diff --check`、链接/章节/乘式核对与明确路径暂存；不运行 Python、仿真、测试或集群任务。后续代码适配按各块定向测试，整合后冻结正式执行提交。

正式运行档案保存 `launch.md`、`result.md` 与 `records/`：启动版本、模型/数据指纹、用户确认原话、十席清单、完整命令、实际 reset 与 rollout 尝试、时间估计更新、成功率、错误、视频索引与退出码。更新 `docs/validation/` 的现有索引入口；只保存 Git 无法还原的结果，不拷贝脚本、配置、权重。任何 PASS 均附实际命令、退出状态、输出路径和审查范围；没有执行的项目写未验证。
