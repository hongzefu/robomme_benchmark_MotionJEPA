# 清理「MME」自造名 + MemER 接入 + 第三阶段四模型评估（seed 7，1800 步）

> 状态（2026-10-06）：原计划曾获批并收到开工令，派出改名子代理 R1 后用户叫停（「先暂停把你的计画写入根目录」「不要再执行了」），R1 已停止、无提交，停止时主检出为 `3d0b8778`，GL 未起本计划任务。本次仅按用户追加要求修订此文档，实施继续暂停；恢复执行仍需用户再次明确下开工令，新增运行矩阵、预算与资产获取不因写入计划而自动获准。
>
> 本次代码核实锚点：`ca08c27621d3a9af83e27f6e4de7faf8672cfefa`，工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`；`third_party/SimpleMemVLA` 内他人在途改动排除、不改、不提交。提交体例接续 `12.<小版本> <中文描述>`。第三方来源保持现有 gitlink：MME-VLA `ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b`、SimpleMemVLA `c564c17d276d7294200122b286c21901a3bfb99f`、PonderPounce `723df35762bb641e1d520e4fa9359b98644adc21`；正式执行另记整合后的冻结提交与实际资产指纹。
>
> 用户追加原话：「还需要实现MemER和seed0/7/42，1800步的调整」「写入/data/hongzefu/robomme_benchmark_MotionJEPANewTask/1006-rename-official-names-and-stage3-eval-plan.md」。按此要求，计划保留用户指定的根目录位置。
>
> 后续纠正原话：「自己的只作为实现的功能，但是我们这一版不跑，这版还是跑自己的七，还是每一个难度跑两个。」「seed只作为实现的功能」。据此，seed 0／7／42 只作为实现能力；本版正式评估与最小 smoke 全部固定模型 seed 7，每个任务难度格仍取两局，不跑 seed 0／42。
>
> 功能范围追加原话：「给出现在所有支持模型的清单，都要支持1800步，都要支持不同seed，模型seed。」「但是我们现在实跑只跑这个。我们现在实跑只跑我说的这些模型。」因此全部模型路线统一补齐1800步与可配置模型seed，但实跑范围只保留本版指定四模型。

# 第一部分（给人看）

## 总览与已定口径

一句话方案：先完成官方命名整理，再接入官方 MemER、实现可选模型 seed 0／7／42 与 1800 步执行上限，最后在 GL A40 上只用 seed 7 跑四模型的第三档评估，每格两局。

1. 命名仍照官方，改活代码与现行文档，历史目录与归档保留（见第一、二节）。
2. 模型改为 FrameSamp+Modulation、SimpleMemVLA、PonderPounce、MemER；移除原计划「MemER 不跑」口径（见第三节）。
3. `seed 0/7/42` 指可选的**模型随机种子**，统一记 `policy_seed`，只实现功能并做 CPU 接线验证；本版运行固定 `policy_seed=7`。环境 `seed`、`candidate`、`spec_sha256` 与每格前两局的选法保留，不扩成三种子运行矩阵（见第三节）。
4. 下表全部模型路线的V9 `test-hard`评估功能都支持1800步和可配置模型seed；本版实际任务统一 `--max-steps 1800 --strict-cap --policy-seed 7`。不修改生成／交付规格的 `EXEC_CAP=1600`，不重生成数据，不启动第二档或其余模型评估（见第三节）。
5. 本轮产出只有这份计划文档；下列代码、资产与运行步骤均为待实施内容。

### 当前模型清单与本版运行范围

「当前已接入」仅指核实到本仓库生产入口已有该路线，不表示1800步／可配置seed已经实现或动态验过。当前已有六条路线，另加本计划待接入的MemER；不把上游文档中尚未接入本仓库的其他组合自动算入支持清单。

| 官方展示名 | 当前接入入口 | 本计划功能要求 | 本版实跑 |
|---|---|---|---|
| FrameSamp+Modulation | `env_client.py::POLICIES` 的现有 `mme` → `mme_client.py` | 1800步；可配置模型seed，CPU至少验0／7／42 | 是，seed7，每格2局 |
| SimpleMemVLA | `smvla` → `smvla_client.py`／`smvla_server.py` | 同上 | 是，seed7，每格2局 |
| PonderPounce | `pp` → `pp_client.py`／`pp_server_wrap.py` | 同上 | 是，seed7，每格2局 |
| GroundSG+Oracle | `mmesg`，`ground-sg-oracle` → `mmesg_client.py` | 同上，服务和客户端seed一致 | 否，只补功能与CPU验证 |
| GroundSG+QwenVL | `mmesg`，`ground-sg-qwenvl` → `mmesg_client.py` | 同上，另核QwenVL预测器seed | 否，只补功能与CPU验证 |
| Astra | 独立 `run_astra.sh`／`astra_hard_runner.py` | 同上，本地动作模型seed贯通；费用与两局守卫保留 | 否，只补功能与零外联CPU验证 |
| MemER | 当前未接入；拟新增内部变体 `ground-sg-memer` | 同上，官方MemER类与adapter真实接线 | 是，seed7，每格2局；须先过接入闸门 |

模型seed使用显式整数参数，0／7／42作为最少CPU验收取值。seed作用于各模型实际使用的本地随机状态，不修改环境seed；Astra的付费云端API若无seed接口，不伪造该接口，也不把本地模型seed描述为云端响应逐位复现保证。

### 一、命名（用户 2026-10-06 裁决：照官方；改活代码 + 现行文档）

| 模型 | 展示名（官方 `docs/manual_evaluation.md`） | 代码／参数／路径 ID（官方 `MODEL_TYPE`／权重名） | Python 标识符 | 仓库旧名 |
|---|---|---|---|---|
| 本次评估模型 | FrameSamp+Modulation | `perceptual-framesamp-modul` | `framesamp_modul` | `mme`、`mmevla` |
| GroundSG 两变体 | GroundSG+Oracle、GroundSG+QwenVL | `groundsg`（变体 `oracle`／`qwenvl`） | `groundsg` | `mmesg` |
| 新增评估模型 | MemER | 官方 `MODEL_TYPE=MemER`；服务权重 `symbolic-grounded-subgoal/79999`；客户端 `use_memer` | 接入现有 GroundSG 装配，新增内部变体 `ground-sg-memer` | 原计划未接入 |

MemER 展示名以锁定官方源码 `third_party/mme-vla/docs/manual_evaluation.md` 的 `MemER` 节及 `scripts/eval.sh` 的 `MODEL_TYPE == MemER` 分支为准；`ground-sg-memer` 只是本仓库拟新增的路线标识。不能将 MemER 展示为自造的「GroundSG+MemER」。

保留不改（官方名）：家族名 MME-VLA（Symbolic／Perceptual／Recurrent MME-VLA）、`third_party/mme-vla`、`.gitmodules`、上游类 `MMEVLAWebsocketClientPolicy`、上游配置 `mme_vla_suite`。

### 二、改名范围

- **改**：原计划盘点活代码与测试 91 个文件、约 900 处；这是改名范围的历史盘点，派发前按冻结提交重新列精确文件清单。
  - 文件名：`mme_client.py`、`mmesg_client.py`、`orig_observer/{mme_client_wrap,mme_proxy}.py`、`run_orig_mme.sh`、`orig-mme-client-env/`、`test_mme_transport.py`。
  - 参数：`--mme-variant`（实为 GroundSG 变体）、`--mme-ckpt`、`--mmesg-ckpt`、`--episode-wall-mme`。
  - 环境变量：`MME_PY`、`MME_CKPT`、`MMESG_CKPT`、`MME_VARIANT` 等。
  - 策略标签 `mme`、`mmesg`，以及测试名、契约条目。
- **现行文档也改**：`AGENTS.md`、`CLAUDE.md` 的项目段（标记块不动）、`readme.md`、`scripts/README.md`、`tests/README.md`。
- **不改**：`docs/validation/`、`docs/plans/` 历史留档（约 3200 处；里面有 NFS 真实路径和 SHA256SUMS）。指向磁盘或 NFS 真实目录的字符串（如 `sg-eval/ckpt/mme/...`、`mmevla-testhard*`）也保留原样，旁注「历史目录名」。新增 `docs/validation/legacy-names.md` 写旧名到新名的对照。
- **兼容**：读历史逐局行、预算账本、v7.5eval 留档的工具（`env_client.py`、`client_replay_eq.py`、`orig_results_adapter.py`、`observer_status.py`、`cap_probe.py`、`site_catalog.py`、报告类）读入时把旧标签映射到新名，写出只写新名，CLI 只接受新名。别名表只在 `official_defs.py` 放一份。
- **改名阶段行为零变化**：只改名字，不改任何逻辑和数值，独立过回放闸门后再接入 MemER、三种子和 1800 步；后三项属于有意新增或改变的行为，不能用改名回放通过声称全链等价。

### 三、MemER、可配置模型seed与1800步（改名合入后）

**MemER 接入。** 当前 `scripts/eval-official/official_defs.py::{VARIANTS,PREDICTOR_NAMES,load_groundsg,make_args,assert_one_predictor,build_predictor}` 仅支持 Oracle／QwenVL，而且显式拒绝 `use_memer`；需要扩展装配，摘取锁定上游的 `subgoal_predictor.py::MemERSubgoalPredictor` 与 `subgoal_prediction/qwenvl/api_memer.py::Qwen3VLModelMemER` 原文，保持官方键帧、历史子目标、推理请求与解析机制。传入 `subgoal_type="grounded_subgoal"`、`use_memer=True`，其余预测器开关关闭，服务仍加载 `symbolic-grounded-subgoal/79999`。

官方 `Args::memer_adapter_path` 默认指向 `vlm_subgoal_predictor/memer/grounded_subgoal/checkpoint-1300`。这不是已核实的本机／NFS 资产：实施前必须确定实际路径、来源提交、文件数、字节数与 SHA256，并纳入资产前置核验；不得用 QwenVL 的 `checkpoint-1200` 代替。现有 `client-env` 锁包含 ms-swift／transformers／peft，可作为复用起点，真实 adapter 和 `flash_attention_2` 加载尚未验证。新侧 `mmesg_client.py::{qwen_begin,qwen_end}`（改名后 `groundsg_client.py`）还要支持 MemER 每局临时目录、`ep*_MemER_log.jsonl` 归档及正常／异常清理；不能只给 QwenVL 换展示名。

**可配置模型seed只实现功能。** 当前 `run_seat.sh::build_server_cmd` 中 FrameSamp与GroundSG动作服务固定 `--seed=7`，`smvla_server.py::reseed` 使用 `EPISODE_SEED=0`，PonderPounce服务启动固定种子0，Astra的 `run_astra.sh` 服务固定seed42。拟新增显式 `--policy-seed`，支持模型seed整数参数、至少验 `0/7/42`，从任务配置同时传到服务、客户端与子目标预测器，在真实模型构造前初始化该路线使用的随机状态。结果行、服务元数据、trace和媒体provenance都记录 `policy_seed`。`official_defs.py::make_args` 要显式设置官方 `Args.model_seed`，不能沿用默认42；QwenVL／MemER构造前按实际使用的RNG设种子。**本版所有真实smoke／正式任务只传7**，不能让SimpleMemVLA／PonderPounce暗用旧默认0；0／42及不实跑路线的传递、随机流和隔离只用CPU夹具验证。

实现层每个 `(模型, policy_seed)` 使用独立 stage、尝试账本、trace、media 与报告目录，共享预算账本的 route 也包含模型种子。现有 `env_client.py::key_of` 与报告按环境身份去重；CPU夹具要验证更换seed不会误用其他组的accepted结果。本版只创建四个模型的seed7运行组。验收必须反向核对实际服务种子与配置，不能只看目录名。

**1800 步的真实执行。** `run_seat.sh::step_cap_pairing` 当前要求 `test-hard ↔ 1600`，需将本计划的新评估配对改为 `test-hard ↔ 1800` 且 `strict_cap=1`，沿 `env_client.py::SeatRunner → builder(max_steps) → EnvSession.step_cap → 客户端循环 → 结果／trace／报告` 全程传递。`test-hard0 ↔ 1300` 保持。执行段第 1801 次 `step` 必须在进入真实环境前被拒绝；第 1800 步成功仍记 success，未成功记 timeout，演示帧不占执行段额度。

此能力覆盖清单中的全部七条路线。Astra不经过 `EnvSession`，须同步改 `astra_hard_runner.py::{DATASET_STEP_PAIRING,check_pairing,TracedEnv,run_one,build_parser}` 与 `run_astra.sh`，在它自己的真实环境调用前实施相同1800执行上限、记录有效cap／模型seed；仅改共享席位脚本会漏掉Astra。Astra、GroundSG Oracle／QwenVL的改动本版只用CPU／零外联夹具验证，不启动GPU或付费smoke。

⚠ `src/robomme_hard/env_record_wrapper/hard_specs.py::EXEC_CAP=1600` 是冻结生成／交付规格的一部分，`_validate_specs` 与身份签名依赖它，本计划不改该值。`eval_report.py --cap 1800` 已有接口，但还需核对每条结果的实际 `max_steps`、有效 cap 与 trace 一致；单查 `exec_steps<=1800` 会让仍在 1600 步截断的旧路线误过。`scripts/evaluation_hard.py` 的 1600 示例也不属于本轮 GL 入口，不顺带更改；三个与上游逐字节一致的顶层入口保持冻结。

SimpleMemVLA 的 `smvla_client.py::hard_bound(1800)=115`，现有trace header记的是理论动作上界 `115×16=1840`，`end.episode_max_steps` 才是1800。验收区分理论循环上界与实际执行cap，不能要求所有header无条件改成1800；应检查 `exec_steps<=1800`、`episode_max_steps=1800` 及环境侧cap。同理PP自身循环在1800退出时未必 `cap_hit=true`，仍可合法记timeout。

改动前后链路（不涉及训练、可训练参数或权重内容改动；既有数组的 shape／dtype／字节数沿用实际协议，逐字段回放核验）：

```text
改前：V9 环境身份清单（含环境 seed/spec_sha256）→ 三模型固定服务种子（7/0/0）
      → SeatRunner(max_steps=1600) → EnvSession(strict cap=1600) → 三模型结果/媒体
改后：同一 V9 环境身份清单（身份字节不变），本版 policy_seed=7
      → 四模型服务及预测器（模型随机流有意变化，MemER 为新增路线）
      → SeatRunner(max_steps=1800) → EnvSession(strict cap=1800)
      → 每(model,policy_seed=7)独立结果/trace/媒体 → 四模型报告
功能：policy_seed={0,7,42} 参数贯通与输出隔离仅做 CPU 夹具验证
```

**本版正式矩阵。** 只跑第三档 V9 `test-hard`，GL A40，模型seed固定7，环境每格仍取前两局。43 格来自 `hard_specs.py::_v9_cells`：`14 任务 × 2 档（xhard1/2）+ 7 任务 × 1 档（xhard3）+ 6 任务 × 1 档（xhard4）+ 2 任务 × 1 档（xhard5）=43格`。各档任务集合不同，按下列实际名单取局，未提供的格不计缺失：

- xhard1／2：除 MoveCube、InsertPeg 外的14任务。
- xhard3：PickXtimes、RouteStick、PatternLock、SwingXtimes、StopCube、VideoUnmask、ButtonUnmask。
- xhard4：SwingXtimes、StopCube、VideoUnmask、ButtonUnmask、MoveCube、InsertPeg。
- xhard5：SwingXtimes、StopCube。

```text
每模型：1 模型种子（7）×（14 任务 × 2 档 × 2 局 + 7 任务 × 1 档 × 2 局
          + 6 任务 × 1 档 × 2 局 + 2 任务 × 1 档 × 2 局）= 86 局
四模型：4 模型 × 上述每模型86局 = 344 局
分片：4 模型 × 1 模型种子（7）× 2 片 = 8 片，每片 43 局
```

执行副本用全部改动整合后的冻结提交新建（拟名 `robomme_benchmark-sgeval3`，存在则另取新名）；新 `run_name` 拟为 `sg-eval-gl-20261006-03`，正式启动前确认未使用。1800 步的新结果不复用旧 1600 步 accepted 终态；旧成绩只作注明步数口径的参照。

### 四、耗时估算与待验证项

原计划记录第二档单局耗时，并用 ×1.5 估第三档；本轮未找到这些计时数的原始行，保留为原计划估算来源，不当作重新核实的实测。本次再乘 `1800/1600=1.125` 作粗估；这不是1800步实测，提前终止、预测器成本和模型seed变化均可能改变耗时：

| 模型 | 原计划所记第二档耗时（分钟/局，未重核） | 1800 步粗估（分钟/局） | 本版 seed7 86 局席位分钟 |
|---|---|---|---|
| FrameSamp+Modulation | 0.63 | 约 1.07 | 约 92 |
| PonderPounce | 1.13 | 约 1.91 | 约 164 |
| SimpleMemVLA | 1.39 | 约 2.36 | 约 203 |
| MemER | 本轮无实测 | 待最小 smoke 核实，不用 QwenVL 速度冒充 | `86 × MemER 单局分钟数` |

| 阶段 | 墙钟估算与边界 |
|---|---|
| 改名：1 个写入型子代理 + 合并前审查 + 合并 + 合并后核心短测与闸门 | 约 2–2.5 小时 |
| MemER／seed／cap 接入、CPU 验收与起跑前核实 | 待实施盘点；MemER 资产未核实，不承诺固定耗时 |
| GL 跑：8 片，4 个保留占位 job（63188714／15／16／19） | 粗估理想均摊下限约 `(459 + 86 × MemER 单局分钟数)/4` 分钟；排队、分片不均和转码另计 |
| 收尾：四模型覆盖与视频核对、seed7成绩表、result.md、提交 | 原计划约 0.5–1 小时，新规模须重估 |
| **合计** | **原 5–6 小时结论失效；MemER 最小 smoke 后更新，不追加用于测速度的批量 rollout** |

四个job及其剩余时长只来自本轮前的资源记录，不代表恢复时仍可用；资源动作须按最新授权执行。本轮不做资源查询、不提交作业、不释放保留资源。本版实跑无Astra、无付费接口。

### 五、完整预算（待运行授权）

第二阶段结束快照见 `docs/validation/sg-eval-gl-20261006-02/result.md` 第⑦节：`BUDGET_ENFORCEMENT=PASS trajectories=2064/6366 resets=4908/141430 astra=0/2 shared_infra=0/50`；其中 4302 是**轨迹**余额，不能当 reset 余额或本轮批准规模。恢复前只读核对账本，保留中断预约的处理证据，不回滚历史消耗。

| 项目 | 轨迹尝试上限 | reset 额度／实际调用口径 |
|---|---|---|
| 正式首试 | `4 模型 × 1 模型种子（7）×（14 任务 × 2 档 × 2 局 + 7 任务 × 1 档 × 2 局 + 6 任务 × 1 档 × 2 局 + 2 任务 × 1 档 × 2 局）=344` | 正常链每 attempt 的 build 1 次 + reset 1 次，基线 `344×2=688`；8 片沿用每片 `2×43+20=106` 硬额度，共848，已含重试余量，不再额外加重试reset |
| 最小 smoke | `4 模型 × 1 模型种子（7）× 1 任务 × 1 档 × 1 局=4`；逐模型先做单局最小验证，不跑seed0／42 | 每局额度3，共12；正常调用 `4×2=8`。不额外做cap实跑探针，用CPU环境调用计数夹具验证 |
| 基础设施重试 | 全阶段共享最多 50 次，且每 `(模型,policy_seed,环境身份)` 最多 1 次 | 消耗上述分片／smoke 既有 reset 额度，双侧任一额度不足即停；任务正常失败或 timeout 不重试 |
| 到期重试 | 本轮0次 | 不继承旧账本默认500次到期重试；占位到期停任务并报告，追加恢复预算另定 |
| **本轮合计上限** | **`344+4+50=398`** | **各 runner reset 硬额度合计 `848+12=860`；正常首试基线 `688+8=696`** |

CPU 回放／夹具消耗真实 reset／轨迹均为 0。新预算账本同时保留旧消耗的只读快照，以「旧消耗 + 本轮消耗」核对此前总授权；新根目录不能重置整项工作的累计计数。`budget_ledger.py` 的全局 reset 软阈值不等于硬拦截；本轮硬边界来自每个 runner 启动前明确的 reset 额度，禁止追加 runner 绕过总和。上述是拟申请的完整新增上限，实际重试亦受共享 50 次限制。

所有实际领取消费者统一注入本轮 `trajectory_cap=398, shared_infra_cap=50, expired_cap=0`，不能只在收尾报告写上限；若沿历史累计账本则轨迹上限为 `2064+398=2462`，相对原6366余额3904。历史 `open=8` 已包含在2064，不能再次扣除或擅自释放。单smoke额度3不足两次完整attempt的4次领取，每片额外20仅够该片10次完整重试；50是全局上限，不保证任意分布的50次重试均能完成，局部额度耗尽直接停止。

### 六、验收表

下表为待实施判据，本轮不将它们写成已通过。

| 查什么 | 怎么查 | 通过说明什么／判定行 |
|---|---|---|
| 官方命名与原有行为 | 排除别名／历史路径／上游符号后检查残留；三条旧路线固定请求／回包回放 | `OFFICIAL_NAMES=PASS`、`CLIENT_REPLAY_EQ=PASS`；仅证明改名阶段未改行为 |
| MemER 真接入 | CPU 夹具调用摘取的官方 MemER 类，核对 `use_memer` 互斥、adapter、键帧请求、日志与异常清理；随后限定 smoke | `MEMER_WIRING=PASS predictor=MemERSubgoalPredictor`、`ASSETS=PASS`、`MEMER_SMOKE=PASS`；任务成功单独报告 |
| 全部模型可选seed与本版真实seed | 7路线CPU夹具各参数化0／7／42，检验传递／随机流／目录隔离；本版实际服务、结果、trace、媒体只核7 | 功能 `POLICY_SEEDS=PASS models=7 seeds=0,7,42 cases=21 cpu_only=1`；运行 `RUN_POLICY_SEED=PASS seed=7 combinations=4`，其他模型／seed无真实任务 |
| 全部模型1800真截断 | 7路线CPU夹具统计实际step调用，含Astra独立入口；覆盖1600→1601、1799→1800、拒第1801步及第1800步成功；报告反查有效cap | `EVAL_CAP=PASS models=7 dataset=test-hard max_steps=1800 rejected_step=1801`；Astra费用守卫亦须原样通过零外联测试 |
| 规格未动 | 相对实施 BASE 核对冻结规格、环境身份 manifest 与第三方来源 | `DELIVERY_UNCHANGED=PASS`、`UPSTREAM_GUARD=PASS` |
| 每模型结果与视频 | 四个seed7组各按accepted_attempt_id核对同一86局集合、官方视频唯一性与完整解码；不得只数mp4 | 每组 `EVAL_COVERAGE=PASS expected=86 missing=0`、`EVAL_VIDEOS=PASS videos=86`、`OFFICIAL_MEDIA=PASS total=86 fail=0`；另核 `skip=0 no_frame_error=0` |
| 完整矩阵与预算 | 汇总4组清单／终态／媒体，查真实领取与重试账本 | `STAGE3_MATRIX=PASS policy_seed=7 combinations=4 unique_terminal=344`、`BUDGET_ENFORCEMENT=PASS`；成功数与失败数另报 |

成绩只报告本版seed7的逐格／任务／档位与总成功率，每个任务难度格 `n=2`；没有三种子运行，不产出三种子均值／标准差或冒称已验证多种子成绩。与旧1600步成绩的差异注明条件已变，不宣称等价或无回归。

### 七、子代理分工与合并（简述）

改名代理R1先完成并经合入前后审查，主会话整合现行文档，再派MemER装配代理R2、共享种子与cap代理R3、Astra独立入口代理R5；CPU测试代理R4并行准备与R5不重叠的测试。R2管预测器装配与日志，R3管共享运行入口和结果分组，R5只管Astra两入口及其测试；接口未定部分不并行写。整合顺序R1 → R2 → R3 → R5 → R4，每步核禁触路径和定向测试，全部通过后冻结执行提交。Codex子代理不暂存、不提交、不push；其他宿主的隔离提交沿各自规则执行，不把Claude的模型档位或提交例外施加给Codex。

### 八、实施步骤表

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 等恢复开工令，核对新增范围／完整预算／MemER 资产获取边界与新 run_name | 授权记录、资产盘点与 BASE 明确 |
| 1 | R1 改名、整合现行文档与旧名对照表 | `OFFICIAL_NAMES`、三路线 `CLIENT_REPLAY_EQ`、核心短测 |
| 2 | R2接MemER，R3／R5让全部7路线支持模型seed与1800，R4补CPU契约 | `MEMER_WIRING`、7路线 `POLICY_SEEDS`／`EVAL_CAP`、`DELIVERY_UNCHANGED` |
| 3 | 核实资产、冻结副本、生成同一份环境清单与4个seed7任务组；限定smoke | `RUN_INPUTS`、`ASSETS`、`MEMER_SMOKE`、`RUN_POLICY_SEED`，4组最小smoke均验结果与媒体 |
| 4 | GL A40，8片进入4席队列，各组独立目录，共享预算 | 任务退出码、进度与预算；异常只停受影响范围 |
| 5 | 四模型seed7验收、成绩汇总、留档与提交；资源按最新指令处置 | `EVAL_COVERAGE`、`EVAL_VIDEOS`、`OFFICIAL_MEDIA`、`STAGE3_MATRIX`、`BUDGET_ENFORCEMENT` |

实测结果在实施完成后另增子节，本轮所有动态结论为未验证。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

1. 仅规划，保持暂停。seed0／7／42只实现功能，本版只跑seed7、每格两局；旧审批不能自动扩展到新增MemER路线或额外真实运行。
2. `src/robomme/**`、录像器、三方源码和 gitlink 不改、不覆盖；`third_party/SimpleMemVLA` 在途内容不纳入本轮。
3. 不改生成 `EXEC_CAP=1600`、交付 spec／manifest；不增加 reset 对拍或 rollout 采样。实际模型评估按第一部分第五节完整预算累计。
4. 所有 Python／测试通过 uv，显式设置 `UV_CACHE_DIR`；NFS 配置 `UV_LINK_MODE=copy`，计算节点 `uv run --frozen --no-sync`，不现场装包。新增正式依赖只落独立客户端子项目及其 lock。
5. MemER 缺资产先报告来源与缺口；大下载须另获落点／规模授权。真实加载失败不降级成 QwenVL 或其他预测器。

## 一、逐文件改动清单

| 文件／稳定锚点（路径随 R1 改名更新） | 拟改什么 | 关闭／旧路线与本轮开启行为 |
|---|---|---|
| 第一部分第二节的改名集合；`official_defs.py` 别名表 | 文件名、参数、标签、兼容读历史 | 原行为不变；旧 CLI 不再写新结果 |
| `scripts/eval-official/official_defs.py::{VARIANTS,PREDICTOR_NAMES,load_groundsg,make_args,assert_one_predictor,build_predictor}` | 新增 `ground-sg-memer`，官方类／独立adapter；Oracle／QwenVL／MemER显式 `model_seed` | 不改预测器机制；每次恰一个预测器开关为真，seed真实传递 |
| `scripts/eval-official/mmesg_client.py::{make_policy_context,qwen_begin,qwen_end,run_episode}` → `groundsg_client.py` | MemER临时目录／日志，全部GroundSG预测器模型seed，结果／trace身份 | 不篡改官方请求与键帧机制；日志不落公共目录 |
| `scripts/eval-official/run_seat.sh::{step_cap_pairing,variant_pairing,build_server_cmd,start_client}`、`run_eval_gl.sh` 参数转发 | 拟新增 `--policy-seed` 与 `--memer-adapter`；MemER变体配对、服务／客户端seed、test-hard cap=1800 | test-hard0仍1300；支持0／7／42，本版任务只传7；错配直接拒跑 |
| `scripts/eval-official/smvla_server.py::{reseed,SMVLAPolicyHost,cmd_serve,main}`、`pp_server_wrap.py` 与PP启动参数 | 将固定种子变成显式传入并保留各路线官方生命周期 | SimpleMemVLA每局reseed；PP按原SID随机流；FrameSamp `MME_VLA_Policy.reset` 每局重设同一seed的PRNG |
| `scripts/eval-official/env_client.py::SeatRunner`、`trace_writer.py`、`eval_report.py`、`model_eval_report.py`、`official_media_check.py` | 传 `policy_seed`／adapter，结果与trace/provenance对齐；报告核实际1800；逐组验收和总汇总 | 环境身份 key 保留，通过独立根隔离模型种子；不把历史缺字段补成已证种子 |
| `scripts/eval-official/run_astra.sh`、`astra_hard_runner.py::{DATASET_STEP_PAIRING,check_pairing,TracedEnv,run_one,build_parser}` | Astra独立路线cap1800／模型seed转发、真实调用前守卫、结果／trace记录 | 本版仅CPU／零外联验收；费用、两局硬守卫与test-hard0口径不变 |
| `scripts/eval-official/budget_ledger.py` 与 `env_client.py`／任务编排的预算构造 | 本轮cap398、infra50、expired0在每个消费者一致读取 | 历史默认不改；本轮实际守卫与报告同口径 |
| `scripts/eval-official/client-env/{pyproject.toml,uv.lock}`（仅确有依赖缺口时） | 真实 MemER 所需依赖声明与锁 | 优先复用现锁，根环境不动，不临时 pip 补正式依赖 |
| `tests/pipeline/eval/`、`tests/pipeline/evalx/{groundsg,astra,report}/` 的下表明确测试及契约登记 | 七路线接线、MemER装配／异常、seed反查、cap边界、恢复／媒体串组反例 | 纯CPU，不加载权重、不开外网、不做真实reset |
| `AGENTS.md`／`CLAUDE.md` 项目段、`readme.md`、`scripts/README.md`、`tests/README.md`、`docs/validation/legacy-names.md` | 主会话更新现行术语与对照 | 标记块及历史档案不改；本轮当前只写用户指定计划 |

表中新增 flag 与字段是拟新增接口，不是当前可运行参数；`eval_report.py --cap 1800` 为已有接口。

## 二、子代理分配表

派发前核对实施 BASE、主检出与各 worktree 状态；子模块在途改动绕开，执行副本必须另建且 clean。主会话负责暂存、提交、推送及资源操作。测试／契约文件先逐项落实归属，不能靠通配集合让两代理同时写同一文件。

| 子任务 | 目标／可写文件集合 | 禁触路径 | 接口契约与依赖／整合顺序 | 验收命令与判定行（工作副本 CPU） | 资源／共享文件裁决 |
|---|---|---|---|---|---|
| R1 | 第一部分第二节改名的 `scripts/**`、`src/robomme_hard/**`、`tests/**`；现有子项目 lock 仅改项目名 | `src/robomme/**`、`third_party/**`、`docs/**`、规则文档、根依赖；不新增顶层入口 | 先完成改名及别名表，之后才派写入 R2／R3；顺序1 | 核心短测、命名残留检查、`CLIENT_REPLAY_EQ`、`TEST_INVENTORY` | GPU=0；独立worktree；R1完成前他人不写该集合 |
| R2 | `official_defs.py`、改名后 `groundsg_client.py`、客户端子项目两依赖文件（必要时） | 上游源码、运行入口、其他客户端／报告／测试／文档 | MemER变体、adapter、预测器seed及日志接口交给R3；顺序2 | `uv run --no-sync python -m pytest tests/pipeline/evalx/groundsg -q`；`MEMER_WIRING` | GPU=0、端口=无；独立worktree；R2独占这三个对象 |
| R3 | `run_seat.sh`、`run_eval_gl.sh`、`env_client.py`、`smvla_server.py`、`pp_server_wrap.py`、`trace_writer.py`、`eval_report.py`、`model_eval_report.py`、`official_media_check.py`、`budget_ledger.py` | R2／R5集合、三方源码、生成规格、测试／文档 | 按R2接口转seed／adapter，cap1800／逐组输出／预算配置；顺序3 | `uv run --no-sync python -m pytest tests/pipeline/eval tests/pipeline/evalx/report -q`；`POLICY_SEEDS`、`EVAL_CAP` | GPU=0；独立worktree；共享运行入口／trace／身份归R3 |
| R5 | `scripts/eval-official/run_astra.sh`、`astra_hard_runner.py`、`tests/pipeline/evalx/astra/{test_astra_wiring.py,test_astra_stop_rules.py,test_run_astra_script.py,astra_fakes.py,contracts.delta.json}` | R2／R3／R4集合、受保护／三方源码、付费与GPU运行 | 复用R3的字段契约，只改Astra独立入口；顺序4 | `uv run --no-sync python -m pytest tests/pipeline/evalx/astra -q`；Astra的 `POLICY_SEEDS`／`EVAL_CAP` 和费用守卫 | GPU=0、外联=0、费用=0；Astra入口与测试唯一归R5 |
| R4 | `tests/pipeline/eval/test_seat_scripts.py`、`test_env_session.py`、`test_policy_clients.py`、`test_smvla_server_units.py`、`test_eval_report.py`、`test_official_media_check.py`、`test_budget_ledger.py`、`test_identity_contract.py`、`test_seat_runner_e2e.py`、`test_eval_wiring.py`、`tests/pipeline/evalx/groundsg/{test_groundsg_official_adapter.py,groundsg_fakes.py,contracts.delta.json}`、`tests/pipeline/eval/contracts.delta.json`、`tests/pipeline/evalx/report/contracts.delta.json` | 生产代码、上游源码、Astra／其他测试；不写R1改名未完成文件 | R1完成后按R2／R3／R5契约并行准备；全部交付后整合，顺序5 | 定向CPU测试＋核心短测；7路线×3seed功能反例及cap、预算守卫必须实际执行 | GPU=0；独立worktree；这批测试由R4唯一写入，新增文件先列确切路径 |
| 主会话自做 | 现行文档、旧名表、资产／运行清单、报告汇总与GL编排 | 标记块、受保护代码、他人在途内容 | 共享规格/运行配置唯一负责人；runbook最终核实 | `RUN_INPUTS`、`ASSETS`、四入口与禁触检查、完整矩阵验收 | 正式运行4席，每席1GPU；`p3-`、`p3-smoke-`前缀，run_name与JobID进launch.md |
| 只读审查代理 | 审合入前后的精确差异与证据，不写文件 | 所有写入／执行资源动作 | 每块整合前后审，异常交原职责持久代理续改 | 按该块具名判据审证据，静态审查不冒称动态通过 | GPU=0、端口=无 |

超5分钟任务由主会话在 detached tmux／占位job中启动与监听；本表未派发运行型子代理。R1采用文件重命名保留Git历史，契约／`TEST_INVENTORY`同步登记。Codex子代理不提交；其他宿主使用 `sub/<编号>:` 提交及合并方式时按其已授权规则保留历史。

## 三、闸门与 CPU runbook

实施前后分别查 `git status --short`、四顶层入口、受保护目录和三方来源零差异，`sync_rules.py check` 检查通用块未漂移；所有检查相对本阶段 BASE，绕开既有脏子模块。

```bash
export UV_CACHE_DIR=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/cache/uv
timeout 280s uv run --no-sync python -m pytest -m 'not slow' -q
uv run --no-sync python -m pytest -m slow tests/pipeline/eval tests/pipeline/evalx -q
ls -1 scripts/*.py
```

定向测试先跑与修改链路对应的目录；预计超过5分钟的验证按tmux纪律执行。`client_replay_eq.py --base 80a402cc --candidate <仅改名冻结sha>` 先核对该基线具备回放所需证据，再验三条既有路线，不把种子／cap新增后的结果与旧1600结果要求逐位一致。MemER CPU测试使用真实摘取的官方类和假的PtEngine，覆盖三预测器互斥、adapter误配、键帧合并、日志序列化、空键帧／首个坏JSON、异常退出清理；原实现有缺陷时保留失败证据，不静默改上游。

全部模型清单的七路线都必须进入1800边界与0／7／42模型seed的CPU参数化测试，Astra走假服务、假planner／monitor的零外联夹具；功能实现通过不扩展本版实跑清单。测试另覆盖预算cap在reserve／retry／report三个入口一致读取、拒到期重试、局部reset耗尽即停。

## 四、运行 runbook（恢复后才执行）

1. 合并前后完成上述验收与命名整理，逐文件提交并按现有upstream推送。锁定最终sha，不复用旧执行副本／旧stage，不提交他人在途内容。
2. 先登记完整预算、新run_name、四个席位与资源处置口径；实际预算统一trajectory398／infra50／expired0，不沿旧默认重试。再核本版四模型资产与客户端依赖实际指向，`RUN_INPUTS`、`ASSETS`失败即停；`SMVLA_PY`／`PP_PY`／FrameSamp解释器及MemER客户端须实际核实。不为本版不跑模型新增下载、GPUsmoke或付费调用。
3. 清单参考 `docs/validation/sg-eval-gl-20261006-02/records/scripts/gl-scripts_build_manifests.py.txt`，从 `_v9_cells` 各格按局号升序取前2局，连交付spec逐项校验：共86个唯一环境身份。四模型seed7复用同一manifest指纹；每模型两片、43局／片。每模型先过其seed7单局最小smoke再启动该路线正式评估；失败停止受影响路线，不额外重跑来挑成功局，不跑seed0／42的smoke。
4. 新根 `R3=$N/sgeval-<确认日期>-03`，四组 `$R3/<模型>/seed7/` 下分别放stage／trace／media／report。全部任务明确指定 `--dataset test-hard --max-steps 1800 --strict-cap --policy-seed 7`；MemER另指定新 `--groundsg-variant ground-sg-memer --memer-adapter <已核实路径>`，实际flag以R1／R3整合后接口为准。任务配置守卫拒绝本版seed0／42运行。
5. 8片入队，仍最多4席，不增加占位job数量；沿原顺序 SimpleMemVLA → PonderPounce → FrameSamp+Modulation，再加入MemER，组内按固定分片／清单顺序运行。每席一次只起一个任务，服务起前探端口，记实际端口、节点、server_epoch、服务argv与种子，健康检查和首推分别验收；srun使用 `--gpu_cmode=shared`。共享预算 `$R3/budget-ledger.jsonl` 的route含模型和模型seed7，任务独立attempt账本记录 `accepted_attempt_id`；各片 `--reset-budget 106`，共享infra上限50，每身份重试最多1次。
6. 登录节点tmux会话前缀 `p3-`，smoke前缀 `p3-smoke-`；完整名、JobID与日志路径写launch.md。日志三件套与 `EXIT_CODE=` 尾行必须保留，监听完成／异常／无进展，不因tmux启动成功承诺代理会自动唤醒。
7. 每模型seed7单独运行报告和媒体验收（已有报告参数 `--cap 1800 --expect-total 86`），校验权威身份集合、真实1800上限、视频唯一性／完整解码与来源；官方自产视频与重绘互斥，原始帧按现行验收后清理规则保留。4组各过覆盖、视频与官方媒体闸门后才汇总344局。
8. 留档结果与预算后提交、推送。原计划自动scancel改为按恢复时最新资源指令处理：此前用户要求保留四个最新job，未经新释放指令不自动取消它们；只停止本轮明确记录的任务步骤／tmux会话，禁止全局清理。

## 五、风险登记

| 风险 | 处理与停止条件 |
|---|---|
| MemER adapter来源／缓存／加载缺口 | 先身份核验；缺文件或flash_attention加载失败停MemER，资产获取不自行扩大授权 |
| 官方MemER空键帧／坏JSON | `Qwen3VLModelMemER::merge_key_frame_paths` 可能在空列表访问首项，首个坏响应的回退可能访问空subgoals；CPU先复现。真实阻塞列具体上游文件／符号及候选修法请用户裁决，不私改锁定来源 |
| 模型seed只改标签或扩大运行范围 | CPU覆盖0／7／42功能；本版四组实际seed只为7，任务守卫拒0／42；共享预算route带seed，错配直接拒跑 |
| 1800只改报告／旧1600终态被复用 | 各层cap逐项核对，第1801次step前拦截；全新根，拒绝旧口径的resume |
| 服务重启／切片改变数值或重试流 | FrameSamp官方reset与SimpleMemVLA每局reseed，PP按SID和重复计数派生流；固定片与顺序、记录server_epoch／sid／计数，不据同seed宣称跨进程／重试逐位一致 |
| 规模与资源时效 | 总预算一次明确，8片不等于8张卡；恢复前核4席是否仍可用，MemER速度未知不承诺5–6小时 |

## 六、盲区诚实清单

本轮只读核实了代码和既有留档，没有运行Python、测试、仿真、模型加载、GPU、下载或GL任务。MemER资产落点／真实加载、可选seed功能、1800实际运行、动态耗时与当前job状态均未验证。本版没有seed0／42真实运行；CPU夹具只能证明接线与边界。正式成绩按 `task_success`／权威终态独立报告。扩大执行上限，以及SimpleMemVLA／PonderPounce从旧实际seed0改为明确seed7，均有意改变实验条件，不能声称与旧评估等价。

## 七、留档与 commit 纪律

正式档案拟为 `docs/validation/sg-eval-gl-20261006-03/`：起跑时写 `launch.md`（用户全部原话及纠正、范围、冻结sha、固定seed7／cap1800、manifest／资产指纹、完整命令、四组目录、预算与会话／JobID清单）；结束写 `result.md`（四模型seed7成绩、具名验收、实际重试／资源／费用、限制），可选seed0／42仅报告CPU功能验收；`records/`只放Git无法还原的清洗日志与实测记录，更新上级索引。启动配置以冻结提交＋文档覆盖项还原，不拷贝sh／yaml进档案，不维护规则文件追加日志。

本轮仅逐文件提交用户指定计划，至少验 `git diff --check`、两部分标题恰好2个、链接与最终文件范围；commit body保留本轮用户原话与验证结果，提交后按仓库既有upstream立即push。后续实施提交逐块验收、逐路径暂存；他人在途内容不暂存、不stash、不回滚。本轮不更新记忆文件。
