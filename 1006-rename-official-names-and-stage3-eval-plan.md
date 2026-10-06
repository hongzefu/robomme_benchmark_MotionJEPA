# 清理「MME」自造名 + MemER 接入 + 第三阶段四模型评估（seed 7，1800 步）

> 状态（2026-10-06）：原计划曾获批并收到开工令，派出改名子代理 R1 后用户叫停（「先暂停把你的计画写入根目录」「不要再执行了」），R1 已停止、无提交，停止时主检出为 `3d0b8778`，GL 未起本计划任务。本次仅按用户追加要求修订此文档，实施继续暂停；恢复执行仍需用户再次明确下开工令，新增运行矩阵、预算与资产获取不因写入计划而自动获准。
>
> 本次代码核实锚点：`ca08c27621d3a9af83e27f6e4de7faf8672cfefa`，工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`；`third_party/SimpleMemVLA` 内他人在途改动排除、不改、不提交。提交体例接续 `12.<小版本> <中文描述>`。第三方来源保持现有 gitlink：MME-VLA `ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b`、SimpleMemVLA `c564c17d276d7294200122b286c21901a3bfb99f`、PonderPounce `723df35762bb641e1d520e4fa9359b98644adc21`；正式执行另记整合后的冻结提交与实际资产指纹。
>
> 用户追加原话：「还需要实现MemER和seed0/7/42，1800步的调整」「写入/data/hongzefu/robomme_benchmark_MotionJEPANewTask/1006-rename-official-names-and-stage3-eval-plan.md」。按此要求，计划保留用户指定的根目录位置。
>
> 后续纠正原话：「自己的只作为实现的功能，但是我们这一版不跑，这版还是跑自己的七，还是每一个难度跑两个。」「seed只作为实现的功能」。据此，seed 0／7／42 只作为实现能力；本版正式评估与最小 smoke 全部固定模型 seed 7，每个任务难度格仍取两局，不跑 seed 0／42。
>
> 2026-10-06 再追加原话：「三、这一版跑什么只跑这四个模型的V9。再加上memer的hard0对拍新老接口 memer的hard0对拍新老接口最后再跑」「现在的GreatLakeSJ0B是单卡的对这个有影响吗?」——据此第三段加 MemER `test-hard0` 原侧 vs 新侧对拍，排在四模型 V9 之后最后跑；单卡占位 job 沿用上一轮 GroundSG+QwenVL 的同卡布局，不需要多卡。
>
> 2026-10-06 再追加原话：「astra这个改名叫 3-tier Astra 也放入」——Astra 展示名改为 3-tier Astra；代码／参数／路径 ID `astra` 不动（见第一部分一）。
>
> 2026-10-06 再追加原话：「每个模型 保存的 rollout video 按照 task suite / task name / model seed 存放，命名 <ep_num>_<task_goal>_<success/fail/timout> .mp4, 我记得我好像是这样的，你 check下」「参考https://robomme.github.io/官方的实现方法 用subagent调研」「先不做打包上传的问题」。两个只读子代理查实：官方没有规定视频目录或文件名，用户记的布局在任何来源都不存在，最接近的是上游 mme-vla `eval.py`；用户随后选定「照上游 mme-vla」布局（第一部分二第 ③ 件、第二部分八.7）。HF 打包上传本轮不做。
>
> 2026-10-06 再追加原话：「总结一下现在现在这个所有的这些模型都跑过对开吗应该是只有MER没跑过就是第二阶段的对拍拟仓库的预算上限和reset上限到底有哪些我现在应该不再需要reset上限了。依旧你要加入一个机制防止卡死或者说生成失败之后从重复生成。」——核实：上一轮第二档五模型（GroundSG Oracle／QwenVL、PonderPounce、SimpleMemVLA、FrameSamp+Modulation）各 192 局对拍已完成，只差 MemER；本版去掉每片 `--reset-budget` 硬拦截，reset 只计量；保留轨迹硬上限、每身份 2 次、共享重试 50 次与席位脚本的卡死检测（第一部分三、第二部分八.9）。
>
> 2026-10-06 再追加原话（本轮增量，经 AskUserQuestion 确认后写入）：「GroundSG+QwenVL也要跑每模型 43 格 × 2 局 = 86 局」「GroundSG+Oracle现在是不是已经跑过了不需要再跑」→ 选「不再跑，沿用 1600 步成绩」；「所有跑Evaluation的模型在第三第三阶段V9的模型是否能保留元数据就是元数据的image goal subgoal action等」→ 选 A 档「只补数值」；「另外还需要加上一个 把hard v9改名为ood」「现在的EvaluationHard传入哪两个接口。？…需要改成hard-verify对应现在第二阶段 和ood对应第三阶段」「然后这两个一个选择一千800步一个选择之前一样」→ 数据集接口 `test-hard0` → `hard-verify`（1300 步不变）、`test-hard` → `ood`（1800 步）。
>
> 2026-10-06 再追加原话：「MemER 接入与 hard-verify 对拍在本机进行可以同步。其他不能在本机。」——MemER 接入的真实 smoke 与 hard-verify 原侧 vs 新侧对拍（192 + 192）在本机 sled-vail（2 × RTX 6000 Ada）做，与 GL 上的五模型 OOD 实跑并行；五模型 OOD 86 局只在 GL A40，不在本机跑。
>
> 2026-10-06 再追加原话：「加入一个新的要求现在的J0BS永远以站位J0B的形式实现然后每次最多只能同时quy4张卡」——GL 上一切任务永远经 48 h 占位 job（`sleep infinity` + `srun --overlap`）运行，不直接 `sbatch` 工作负载；**全局**同一时刻占住或排队的占位 job 合计最多 4 张卡（所有 job 加起来 4 张，不是每个 job 4 张）；此前「最多 10 卡」授权作废。随后原话：「全局最多4张卡不是单个J0B。」「我授权你自己来管理J0B。尽可能让我少排队」——占位 job 的提交、保活、到期前续排、`scancel` 自己的 job 由主会话自行管理，目标是席位尽量不空、用户不被排队拖住；该授权不是开工令，开工仍等用户明确说「开工」。
>
> 2026-10-06 Codex 对固定提交 `894fa97f` 的静态审计（`STATIC_AUDIT=FAIL`，10 条正确性问题）经九个只读子代理逐条对源码核实：第 1、2、3、5、6、7、8 条属实，第 4 条新侧属实、原侧驳回，第 9 条前半属实（已裁决的具名例外）、a1／a2 争名驳回，第 10 条属实但 Astra「多落一行」驳回。用户原话「核实完了告诉我哪些地方用户决策重新调整其他的地方也可以自己改」：待用户裁决 5 项见八.10 末尾；其余由主会话改入本计划（八.10 逐条登记）。
>
> 2026-10-06 用户对八.10 五项裁决原话：「345同意 4可以接续 2报告 1没看懂如果模型第一次回复的关键帧为空的话你现在改完之后是怎么处理的」——第 2 项：保留无帧 error 具名例外、报告单列；第 3 项：批准按只读核验清单从 HF 下载 MemER adapter `checkpoint-1300`；第 4 项：到期中断的局允许接续，每身份最多 1 次、计入 870；第 5 项：本轮预算 870 局一口气授权（reset 只计量）。第 1 项待用户看完兼容层说明后再定。
>
> 2026-10-06 用户对第 1 项裁决原话：「同意兼容层把这个写入计划详细说这个问题。把你兜底的这个情形修改之前修改之后的这个prompt完整的英文版给我然后加上中文注释不要做翻译 原始的prompt。」——MemER 兼容层方案、原始 prompt 原文与修改前后的处理流程见八.3「MemER 兼容层」。
>
> 功能范围追加原话：「给出现在所有支持模型的清单，都要支持1800步，都要支持不同seed，模型seed。」「但是我们现在实跑只跑这个。我们现在实跑只跑我说的这些模型。」因此全部模型路线统一补齐1800步与可配置模型seed，但实跑范围只保留本版指定四模型。

# 第一部分（给人看）

本轮产出只有这份计划，实施保持暂停，恢复要再等用户明确说「开工」。下面分三段：一、改名怎么改；二、现在有哪些模型、每个还缺什么（MemER 单独展开）；三、这一版到底跑什么。

## 一、改名怎么改

**要改的原因**：仓库里 `mme`／`mmevla` 指的其实是官方的 FrameSamp+Modulation，`mmesg` 指的是官方的 GroundSG，都是自造名；用户裁决「照官方」。

| 仓库旧名 | 官方展示名 | 新的代码／参数 ID | Python 标识符 |
|---|---|---|---|
| `mme`、`mmevla` | FrameSamp+Modulation | `perceptual-framesamp-modul` | `framesamp_modul` |
| `mmesg` | GroundSG+Oracle、GroundSG+QwenVL | `groundsg`，变体 `oracle`／`qwenvl` | `groundsg` |
| （无） | MemER | 本仓库新增路线标识 `ground-sg-memer` | 复用 `groundsg` 装配 |
| 数据集接口 `test-hard0`（第二阶段，官方 hard 12 局） | `hard-verify`（用户 2026-10-06 裁决） | `hard-verify`，步数照旧 1300 | `HARD_VERIFY` |
| 数据集接口 `test-hard`（第三阶段 V9） | `ood`（用户 2026-10-06 裁决，文档里「hard V9」改称 OOD） | `ood`，步数 1800 | `OOD` |
| 展示名 Astra | 3-tier Astra（用户 2026-10-06 裁决） | `astra` 不变：文件名 `run_astra.sh`／`astra_hard_runner.py`、策略标签、预算账本键、route、对比工具的 mode 都不动，只改展示名 | `astra` |

**改什么、不改什么**：

| 类别 | 做法 |
|---|---|
| 改：活代码与测试 | 约 91 个文件、900 处，另加数据集接口两个名字（`hard_builder.py::{TEST_HARD,TEST_HARD0,_ALLOWED_DATASETS}`、`env_client.py::{TEST_HARD,TEST_HARD0}` 与席位脚本配对表、`astra_hard_runner.py::DATASET_STEP_PAIRING`、`env_metadata/test-hard/` 目录名、`scripts/evaluation_hard.py` 示例改成 `hard-verify`／`ood` 两段；`spec_sha256` 不含数据集名，交付身份不变；读历史结果时旧名映射）。文件名（`mme_client.py`→拟 `framesamp_modul_client.py`、`mmesg_client.py`→`groundsg_client.py`、`orig_observer/mme_*`、`run_orig_mme.sh`、`orig-mme-client-env/`、`test_mme_transport.py`）、CLI 参数（`--mme-variant`→`--groundsg-variant`、`--mme-ckpt`、`--mmesg-ckpt`、`--episode-wall-mme`）、环境变量（`MME_PY`、`MME_CKPT`、`MMESG_CKPT`、`MME_VARIANT`）、策略标签 `mme`／`mmesg`、测试名与契约条目 |
| 改：现行文档 | `AGENTS.md`、`CLAUDE.md` 的项目段（标记块不动）、`readme.md`、`scripts/README.md`、`tests/README.md`；报告与成绩表里的展示名（含 Astra → 3-tier Astra） |
| 不改：历史留档 | `docs/validation/`、`docs/plans/` 约 3200 处不动（里面有 NFS 真实路径与 SHA256SUMS）；指向磁盘真实目录的字符串（`sg-eval/ckpt/mme/…`、`mmevla-testhard*`）原样保留，旁注「历史目录名」；另写 `docs/validation/legacy-names.md` 旧名对照（含 Astra → 3-tier Astra） |
| 不改：官方名 | MME-VLA 家族名、`third_party/mme-vla`、`.gitmodules`、上游类 `MMEVLAWebsocketClientPolicy`、上游配置 `mme_vla_suite` |
| 兼容旧数据 | 读历史逐局行、预算账本、v7.5eval 留档的工具读入时把旧标签映射成新名，写出只写新名，CLI 只接受新名；别名表只在 `official_defs.py` 放一份 |

**保证只改名、不改行为**：改名单独成一步，先合入、过回放闸门 `CLIENT_REPLAY_EQ=PASS`（三条旧路线固定请求／回包逐字节相同）与残留检查 `OFFICIAL_NAMES=PASS`，之后才动第二段的功能。

## 二、模型清单：现在有什么、每个还缺什么

| 官方展示名 | 本仓库入口 | 缺 1800 步 | 缺可配置模型 seed（现在钉死的值） | 其他缺口 |
|---|---|---|---|---|
| FrameSamp+Modulation | `mme_client.py`（改名后 `framesamp_modul_client.py`） | 缺，席位脚本钉 `test-hard ↔ 1600` | 缺，服务固定 `--seed=7` | — |
| SimpleMemVLA | `smvla_client.py`／`smvla_server.py` | 缺，同上 | 缺，每局 reseed 固定 0 | trace header 记的是理论动作上界 1840，验收要看 `episode_max_steps` |
| PonderPounce | `pp_client.py`／`pp_server_wrap.py` | 缺，同上 | 缺，服务启动固定 0 | 自身循环到 1800 退出时未必 `cap_hit=true`，合法记 timeout |
| GroundSG+Oracle | `mmesg_client.py`（改名后 `groundsg_client.py`） | 缺，同上（本版不跑：V9 已有 1004 轮 1600 步、每任务 50 局的 800 局成绩 52.9%，沿用并注明口径不同） | 缺，服务固定 `--seed=7`；官方 `Args.model_seed` 默认 42 没显式设 | — |
| GroundSG+QwenVL | 同上 | 缺，同上 | 缺，同上，另要在 QwenVL 预测器构造前设种子 | 本版实跑 86 局（用户 2026-10-06 追加） |
| MemER | **未接入** | 缺 | 缺 | 见下面展开 |
| 3-tier Astra（代码 ID `astra`） | 独立 `run_astra.sh`／`astra_hard_runner.py`，不走共享席位 | 缺，入口自己钉 1600 | 缺，服务固定 42 | 云端 API 无 seed 接口，不伪造；费用与两局守卫不动 |

**共同要补的三件事**：
- **1800 步**：席位脚本 `run_seat.sh::step_cap_pairing` 配对改 `test-hard ↔ 1800`、`strict_cap=1`，沿 `SeatRunner → EnvSession.step_cap → 客户端循环 → 结果／trace／报告` 全程传；第 1801 次 `step` 在进真实环境前被拒，第 1800 步成功仍记 success；Astra 在它自己的入口同改；`test-hard0 ↔ 1300` 与生成规格 `EXEC_CAP=1600` 不动。判据 `EVAL_CAP=PASS models=7 max_steps=1800 rejected_step=1801`。
- **模型 seed**：新增 `--policy-seed <int>`，从任务配置传到服务、客户端、子目标预测器，在模型构造前设该路线真正用的随机状态；结果行、trace、媒体 provenance 都记 `policy_seed`；每个 `(模型, policy_seed)` 独立输出目录与账本 route。七路线各在 CPU 夹具上验 0／7／42；判据 `POLICY_SEEDS=PASS models=7 seeds=0,7,42`。本版真实运行只传 7。
- **元数据（用户 2026-10-06 选 A 档「只补数值」）**：现状每步只记 action／state 的 sha256 与前 8 个值，完整数值只在非 float32 时写 `arrays.npz`；改为所有路线每个执行步的 action 与 state 完整数组一律写 `arrays.npz`（键 `exec_action__%05d`、`exec_state__%05d`），goal 与 subgoal 原文已有不动，图像仍只留 mp4 加每帧 sha256。归 R3，判据 `TRACE_ARRAYS=PASS episodes=<n> missing=0`。
- **执行机制补强（Codex 2026-10-06 审计核实后，主会话自定，细节见第二部分八.10）**：回放闸门改为传两个检出目录并校 sha、四条旧路线 × 三场景、两侧同样崩溃判 FAIL、强制自检；原侧驱动接共享预算与模型 seed 链、保留官方视频、trace 补 attempt 与帧计数；新侧上下文加载加绝对期限、无进展监督看具名阶段不看日志、恢复次数按运行组持久化；重试领取与预约用同一 token 幂等、分片排他锁、账本坏行即拒；比较器加「预期主机 sled-vail」来源模式；每步 action／state 由唯一收尾者合并写 NPZ；改名阶段先保持 `ood ↔ 1600` 旧行为过回放，功能阶段再改 1800。
- **视频布局（用户 2026-10-06 选定「照上游 mme-vla」）**：现状是 `<模型标签>/<dataset>/new/<task>_<tier>_<环境seed>.a<attempt>/official/official-rerender__<task>_ep<源局>a<尝试>_<终态>_<task_goal>_<tier>.mp4`，没有模型 seed 层。改为每个运行根下按上游 `eval.py` 的层级发布一份：`<run 根>/<模型 ID>/seed<policy_seed>/[oracle｜qwenvl｜memer/]videos/<task>_ep<N>_<success｜fail｜timeout>_<task_goal>_<tier>.mp4`——GroundSG 三个变体多一层子目标目录（与官方同）；`ep<N>` 用局号（V9 用 builder 局号，hard0 用官方源局号），只发布账本接受的那一次 attempt，不带 `a<尝试>`；终态只允许三态，strict-cap 命中必须命名 `timeout`（旧口径超时局文件名带 `error`，本版不允许）；末尾用 tier（`xhard0`～`xhard5`）替官方的 difficulty；文件名超 255 字节沿用截断加哈希、完整名写 `render.json`。局目录里的 trace、arrays、`episode.mp4` 位置不动，只多一步「发布到上游布局」并出索引。MemER hard0 对拍的原侧由官方代码自己写出 `<save_dir>/symbolic-grounded-subgoal/ckpt79999/seed7/memer/videos/`，不改。判据 `VIDEO_LAYOUT=PASS model=<m> seed=7 videos=<n> error_named=0`。

### MemER 要改什么（展开）

**官方是怎么跑 MemER 的**（锁定提交 `ecf086c3` 的 `examples/robomme/`）：`scripts/eval.sh` 的 `MODEL_TYPE == MemER` 分支只加两个参数 `--args.use-memer --args.subgoal-type=grounded_subgoal`，动作服务照旧加载 GroundSG 的权重 `symbolic-grounded-subgoal/79999`——所以 MemER 不是新的动作模型，是 GroundSG 换了一个子目标预测器。这个预测器 `subgoal_predictor.py::MemERSubgoalPredictor` 包着 `subgoal_prediction/qwenvl/api_memer.py::Qwen3VLModelMemER`：基座 `Qwen/Qwen3-VL-4B-Instruct` 加一个 LoRA adapter（官方默认路径 `runs/ckpts/vlm_subgoal_predictor/memer/grounded_subgoal/checkpoint-1300`，`flash_attention_2`），每局开始把演示视频帧存进局目录、每一步把当前帧存成 png、每次问子目标时把「历史关键帧 + 最近执行帧」一起送进模型，模型回 JSON（`current_subtask` + `keyframe_positions`），它据此更新关键帧记忆（`merge_key_frame_paths` 合并近邻帧）；每次请求与回复追加写到局目录旁的 `ep<N>_MemER_log.jsonl`；局末 `rmtree` 局目录。

**我们这边现在的状态**：GroundSG 装配 `scripts/eval-official/official_defs.py` 只认两个变体（`VARIANTS = (oracle, qwenvl)`），`PREDICTOR_NAMES` 只摘 Oracle／QwenVL 两个类，`load_groundsg` 只在 QwenVL 变体时才摘 `qwenvl/api.py`，`make_args` 只会置 `use_oracle`／`use_qwenvl`，`assert_one_predictor` 明确把 `use_memer=True` 当错误抛出，`build_predictor` 只给 QwenVL 导入 swift。客户端 `mmesg_client.py::make_policy_context` 先检查变体必须在 `VARIANTS` 里，adapter 只认 `qwenvl_groundSG_adapter_path` 一个键；席位脚本 `run_seat.sh` 的变体配对只放行 `ground-sg-oracle`／`ground-sg-qwenvl`，adapter 只有 `--qwenvl-groundsg-adapter` 一个参数。也就是说现在任何一层都进不去 MemER。

**要改的五处**：

| 处 | 文件与锚点 | 改什么 |
|---|---|---|
| 1 装配 | `official_defs.py::{VARIANTS,PREDICTOR_NAMES,load_groundsg,make_args,assert_one_predictor,build_predictor}` | 加第三个变体 `ground-sg-memer`；`PREDICTOR_NAMES` 加 `MemERSubgoalPredictor`；`load_groundsg` 在该变体下摘 `qwenvl/api_memer.py::Qwen3VLModelMemER` 原文（它和 `api.py` 一样在导入时设 `IMAGE_MAX_TOKEN_NUM` 等三个环境变量，摘取时要一并落实）；`make_args` 置 `use_memer=True`、`subgoal_type="grounded_subgoal"`、`memer_adapter_path`，并显式传 `model_seed`；互斥断言改成「oracle／qwenvl／memer 恰一个为真」；`build_predictor` 对 memer 也设离线运行约束并导入 swift。摘的是官方原文；**另加两侧一致的兼容层（用户 2026-10-06 同意）**：空关键帧不做合并、合法子目标真正存入兜底列表、执行帧不足 15 张时有几张取几张；提问模板、关键帧选取与合并规则、动作模型输入一字不改；记录实现指纹，不改 gitlink，成绩表注明「MemER 用修了三处越界的官方实现」（细节与原始 prompt 见第二部分八.3） |
| 2 客户端 | `mmesg_client.py`（改名后 `groundsg_client.py`）`::{make_policy_context,qwen_begin,qwen_end,run_episode}` | 变体检查放行 memer；adapter 多认一个 `memer_adapter_path` 键；`qwen_begin`／`qwen_end` 现在只管 QwenVL 的 `qwen-tmp` 局目录，要让 MemER 的局目录与旁边的 `ep*_MemER_log.jsonl` 一样被指到 `<trace_dir>` 下的临时目录、局末归档到该局 trace 目录、异常退出也清理；结果行 `policy_variant` 记 memer |
| 3 席位脚本 | `run_seat.sh::{variant_pairing,build_server_cmd,start_client}`、`run_eval_gl.sh` 参数转发 | 变体配对放行 `ground-sg-memer`，新增 `--memer-adapter <dir>`（给了变体不给 adapter、或 adapter 目录不存在即 `RUN_BLOCKED`）；动作服务命令与 GroundSG 相同（同一份 `symbolic-grounded-subgoal/79999`，同一个 `--policy-seed`） |
| 4 资产 | 资产清单与 `ASSETS` 前置核验 | adapter `checkpoint-1300` 按文件名在本机 `artifacts/` 与 NFS 下初查没有找到（只找到源码，没有权重），实施前要先定来源、落点、文件数、字节数与 SHA256，纳入起跑前核验；不得拿 QwenVL 的 `checkpoint-1200` 顶替；大下载先问落点 |
| 5 依赖与验证 | `scripts/eval-official/client-env/{pyproject.toml,uv.lock}`（仅确有缺口时）；`tests/pipeline/evalx/groundsg/` | 现有客户端锁已含 ms-swift／transformers／peft，优先复用；CPU 夹具用假 `PtEngine` 验三预测器互斥、adapter 误配、键帧合并、日志序列化、空键帧与首个坏 JSON、异常清理；然后 GL 上 1 局真实 smoke（真 adapter + `flash_attention_2` 加载尚未验过） |

**官方代码的坑在哪、兜底兜的是什么**（用户 2026-10-06 同意加兼容层）

MemER 的子目标模型每一步被问同一个问题：「任务目标是 X，这是以前挑出来的重要画面（关键帧），这是最近几张画面，现在该做哪个子任务？哪几张是关键帧？」它回一个 JSON：`current_subtask`（子任务文字，直接交给动作模型）和 `keyframe_positions`（挑中的帧序号，程序据此把画面存进「关键帧记忆」）。

第一次提问时记忆是空的，模型看到的关键帧栏是字面上的 `[]`，画面只有 1 张，所以它最自然的回答就是「关键帧为空」。官方代码收到这个回答后：

1. 关键帧为空，存记忆这一步跳过了——没问题；
2. 紧接着无条件做一次「合并相邻关键帧」，在空记忆上取第一个元素——报错；
3. 报错后走兜底「用上一次的子任务」，但存上一次子任务的那个列表在整个文件里从来没被写入过，永远是空的——兜底再报错。

结果：这一局在机器人动第一步之前就崩了，记 error，动作模型连那句「move cube」都没收到。这不是模型答错，是官方代码自己的越界。另有一处同类问题：第二次提问起固定往前隔一张取 8 张画面，画面不够 15 张时也越界。

兼容层只做三件事：空记忆不合并；每次合法的子任务真的存进兜底列表，模型回坏 JSON 时沿用上一次，一次都没有就把这局记成具名错误 `model_response_error`，不编造子任务；画面不够 15 张时有几张取几张。两个模型看到的输入一个字不变：子目标模型的提问原文、动作模型收到的子目标文字都和官方相同（原文与六种情形的前后对照见第二部分八.3）。两侧对拍用同一份补丁、同一个指纹，成绩表注明「MemER：官方实现 + 三处越界兼容补丁」。

判据：`MEMER_WIRING=PASS predictor=MemERSubgoalPredictor`、`MEMER_COMPAT=PASS cases=6 fingerprint=<sha256>`、`ASSETS=PASS`、`MEMER_SMOKE=PASS`。

## 三、这一版跑什么

两条线并行：GL A40 上跑五个模型的 OOD（原 V9 `test-hard`，改名 `ood`）第三档；本机 sled-vail（2 × RTX 6000 Ada）上做 MemER 接入的真实 smoke 与 `hard-verify`（原 `test-hard0`）原侧 vs 新侧对拍。OOD 只在 GL、不在本机；对拍两侧都在本机、不跨机比。不跑 seed 0／42；GroundSG+Oracle 沿用 1600 步旧成绩不跑；3-tier Astra 只改代码、不实跑。

| 跑什么 | 规模 | 怎么跑 |
|---|---|---|
| 五模型 OOD 第三档：FrameSamp+Modulation、SimpleMemVLA、PonderPounce、MemER、GroundSG+QwenVL | 每模型 43 格 × 2 局 = 86 局，共 430 局 | 1800 步、模型 seed 7；10 片排进 4 个单卡占位席位（单卡够用：MemER 与 QwenVL 一样和动作服务同卡） |
| GL 资源硬规则（用户 2026-10-06） | — | 永远经 48 h 占位 job 跑（`sleep infinity` + `srun --overlap`），不直接 `sbatch` 工作负载；**全局**占住 + 排队的占位 job 合计最多 4 张卡（不是每个 job 4 张）；job 由主会话自管：到期前提前续排、空席立即补片、跑完按清单 `scancel` 自己的 job，尽量让用户少排队 |
| 本机并行：MemER hard-verify 对拍 | 原侧 192 局 + 新侧 192 局 | 本机两张卡各一席，1300 步，两侧同一批局、同一份 adapter、seed 7，两侧同机；出差异报告，不证明等价 |

预算：轨迹硬上限 870 局（430 + 5 局 smoke + 384 + 2 局 smoke + 50 次重试；到期接续的局也从这 870 里出），用户 2026-10-06「345同意」已一口气授权；历史累计 2934，在 6366 内；**reset 不再设硬上限**（去掉每片 `--reset-budget` 拦截，共享账本只计量告警，预计约 2166 次）。耗时等 MemER 跑完 1 局 smoke 再估。run_name 拟 `sg-eval-gl-20261006-03`。

防卡死、防重复生成（现有机制，本版保留）：每局墙钟 + `progress.json` 超时不更新即 `NO_PROGRESS` 重起服务一次、第二次停这一片；客户端最多重启 8 次、服务 2 次；每个身份最多 2 次尝试，只有基础设施错误才重试，正常 fail／timeout 一律接受不重跑，续跑时已接受的身份跳过，重试名额从共享账本原子领取。

验收：

| 阶段 | 判定行 |
|---|---|
| 改名只改名 | `OFFICIAL_NAMES=PASS`、`CLIENT_REPLAY_EQ=PASS` |
| 七路线功能（CPU） | `POLICY_SEEDS=PASS models=7`、`EVAL_CAP=PASS max_steps=1800`、`MEMER_WIRING=PASS` |
| 五模型 OOD | 每组 `EVAL_COVERAGE=PASS expected=86`、`OFFICIAL_MEDIA=PASS`、`VIDEO_LAYOUT=PASS`、`TRACE_ARRAYS=PASS`；总 `STAGE3_MATRIX=PASS combinations=5 unique_terminal=430`、`BUDGET_ENFORCEMENT=PASS trajectories=<n>/870`（reset 只报计量） |
| MemER 对拍（本机） | `GATE2_PROVENANCE=PASS`（两侧同为 sled-vail）、`GATE2=INFO compared=192` |

步骤：0 等用户说「开工」→ 1 改名（含数据集接口改名）→ 2 功能 → 3 冻结提交、核 MemER 资产、五模型各 1 局 smoke（MemER 的在本机）→ 4 并行：GL 跑 OOD 10 片 ｜ 本机跑 MemER hard-verify 对拍 → 5 两边各自验收汇总 → 6 留档、commit、push。

子代理：R1 改名先做完、审两次、合入；主会话冻结共享接口（CLI、seat_info、seed／cap、预算 token、trace／NPZ 与发布索引字段）；再同时派 R2（MemER 与原侧）、R3（共享入口、预算、服务）、R6（trace 与完整数值）、R7（媒体、报告、对拍比较器）、R5（Astra）、R4（测试），各在自己的 worktree 写互不重叠的文件，按 R1 → R2 → R3 → R6 → R7 → R5 → R4 合回，每合一个审一次。

用户原话、口径表、单卡布局、预算细则、完整判定行、完整步骤表与子代理分工见第二部分八.8。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

1. 仅规划，保持暂停。seed0／7／42只实现功能，本版只跑seed7、每格两局，实跑五模型（含 GroundSG+QwenVL），Oracle 沿用旧成绩；MemER `hard-verify`（原 `test-hard0`）原侧 vs 新侧对拍（192 + 192）在本机 sled-vail 两张卡上做、与 GL 的 OOD 并行（用户 2026-10-06「MemER 接入与 hard-verify 对拍在本机进行可以同步。其他不能在本机。」），OOD 五模型只在 GL；对拍同样待运行授权；旧审批不能自动扩展到新增MemER路线或额外真实运行。
2. `src/robomme/**`、录像器、三方源码和 gitlink 不改、不覆盖；`third_party/SimpleMemVLA` 在途内容不纳入本轮。
3. 不改生成 `EXEC_CAP=1600`、交付 spec／manifest；不增加 reset 对拍或 rollout 采样。实际模型评估按第一部分第三节与本部分八节的完整预算累计；reset 自 2026-10-06 起只计量不拦截（用户「我现在应该不再需要reset上限了」），P3 授权仍按乘式报 reset 预计数。
4. 所有 Python／测试通过 uv，显式设置 `UV_CACHE_DIR`；NFS 配置 `UV_LINK_MODE=copy`，计算节点 `uv run --frozen --no-sync`，不现场装包。新增正式依赖只落独立客户端子项目及其 lock。
5. MemER adapter 获取已获用户 2026-10-06 批准（「345同意」）：只读核 HF `Yinpei/vlm_subgoal_predictor` 的 40 位 revision、`memer/grounded_subgoal/checkpoint-1300` 的文件数、字节数、SHA 与本机缓存缺口后，只取该目录，落 `artifacts/sg-eval/ckpt/memer/grounded_subgoal/checkpoint-1300/`，逐文件 sha256 进 `ASSETS` 清单，再 rsync 到 NFS 供 GL；超出该目录的下载仍须另问。真实加载失败不降级成 QwenVL 或其他预测器。
6. 改名阶段（R1）保持 `ood ↔ 1600`、`hard-verify ↔ 1300` 的旧行为过回放闸门，功能阶段（R3）才改 `ood ↔ 1800`；原侧驱动与新侧一样经共享预算账本预约、领取重试、计量 reset，cap `870／50／50`（轨迹／基础设施重试／到期接续）由启动脚本显式传入，缺失或不一致即拒跑，不回落账本常量默认值。

## 一、逐文件改动清单

| 文件／稳定锚点（路径随 R1 改名更新） | 拟改什么 | 关闭／旧路线与本轮开启行为 |
|---|---|---|
| 本部分八节的改名集合；`official_defs.py` 别名表 | 文件名、参数、标签、兼容读历史 | 原行为不变；旧 CLI 不再写新结果 |
| `scripts/eval-official/official_defs.py::{VARIANTS,PREDICTOR_NAMES,load_groundsg,make_args,assert_one_predictor,build_predictor}` | 新增 `ground-sg-memer`，官方类／独立adapter；Oracle／QwenVL／MemER显式 `model_seed` | 不改预测器机制；每次恰一个预测器开关为真，seed真实传递 |
| `scripts/eval-official/official_hard_runner.py::{make_context,build_parser}`、`run_official_hard.sh` | 原侧驱动放行 `ground-sg-memer`，新增 `--memer-adapter`（与 `--qwenvl-groundsg-adapter` 互斥配对），route `mmesg/<variant>/orig`（改名后 `groundsg/…`）照旧 | 官方 `eval.py` MemER 分支原文经同一驱动跑 hard0 192 局，与 GroundSG 原侧同一套清单／重试／trace |
| `scripts/eval-official/mmesg_client.py::{make_policy_context,qwen_begin,qwen_end,run_episode}` → `groundsg_client.py` | MemER临时目录／日志，全部GroundSG预测器模型seed，结果／trace身份 | 不篡改官方请求与键帧机制；日志不落公共目录 |
| `scripts/eval-official/run_seat.sh::{step_cap_pairing,variant_pairing,build_server_cmd,start_client}`、`run_eval_gl.sh` 参数转发 | 拟新增 `--policy-seed` 与 `--memer-adapter`；MemER变体配对、服务／客户端seed、test-hard cap=1800 | test-hard0仍1300；支持0／7／42，本版任务只传7；错配直接拒跑 |
| `scripts/eval-official/smvla_server.py::{reseed,SMVLAPolicyHost,cmd_serve,main}`、`pp_server_wrap.py` 与PP启动参数 | 将固定种子变成显式传入并保留各路线官方生命周期 | SimpleMemVLA每局reseed；PP按原SID随机流；FrameSamp `MME_VLA_Policy.reset` 每局重设同一seed的PRNG |
| `scripts/eval-official/env_client.py::SeatRunner`、`trace_writer.py`、`eval_report.py`、`model_eval_report.py`、`official_media_check.py` | 传 `policy_seed`／adapter，结果与trace/provenance对齐；报告核实际1800；逐组验收和总汇总 | 环境身份 key 保留，通过独立根隔离模型种子；不把历史缺字段补成已证种子 |
| `scripts/eval-official/run_seat.sh::{finish_episode_dir,publish_dir}`、`render_official_video.py::render_episode`、`official_media_check.py`、`video_check.py`（新增发布与布局核验） | 局目录收尾后把官方版式视频按上游 `eval.py` 布局发布到 `<run 根>/<模型 ID>/seed<policy_seed>/[变体/]videos/<task>_ep<N>_<终态>_<task_goal>_<tier>.mp4`，终态三态、strict-cap 一律 `timeout`；出索引 tsv；核验 `VIDEO_LAYOUT` | 局目录与 `official/` 原位不动；旧 `error` 命名不再出现；GroundSG 原生视频改名发布、重绘视频去 `official-rerender__` 前缀 |
| `scripts/eval-official/client_replay_eq.py::{worker,compare,run_route,main}`（R1） | `--base`／`--candidate` 传检出目录并核 `git rev-parse HEAD` 等于计划冻结 sha；按两侧接口分别选模块名、数据集名、配置键；路线四条（mmesg oracle、smvla、mme、pp）× 三场景（成功、预期环境异常、timeout）；两侧同 crash 或零事件一律 FAIL；`--self-test` 强制 | 现状：同 crash 跳过仍 PASS、无事件下限、旧名写死、sha 当目录 |
| `scripts/eval-official/env_client.py::{SeatRunner.policy_context,run_one,run_identities_v8,AttemptLedger}`、`budget_ledger.py::{reserve,claim_retry,_read,_append}`、`run_seat.sh::{policy_loop,idle_s}`、`run_eval_gl.sh`（R3） | 上下文加载、首推、单局、媒体收尾各有绝对 deadline；无进展监督读具名 phase／identity／实际步数，不看 `client.log` mtime；恢复次数按运行组持久化到文件；retry／trajectory／attempt_start 共用一个 token 幂等恢复；分片排他 lease（flock）在读 pending 前取得；`_append` 先补换行、所有写前检查 `bad_rows` 与不可变配置，坏行即拒；启动脚本显式传 `--budget-ledger` 与 `--trajectory-cap 870 --shared-infra-cap 50 --expired-cap 0` | 现状：加载期无期限、计数局部变量、领取非幂等、无跨进程锁、坏行只在收尾判 FAIL、cap 全是常量默认 |
| `scripts/eval-official/gate2_compare.py::{compare_ext,is_gl_node,main}`（R7） | 新增 `--expect-host <name>` 来源模式：逐行核两侧 `node`／`host` 均等于预期主机，未知或跨机仍 FAIL；GL 模式原检查不变 | 现状：只认 `glNNNN`，本机对拍必 INVALID |
| `scripts/eval-official/trace_writer.py::{TraceWriter.log_step,close}`、`recorder.py::EpisodeRecorder.close`、`smvla_client.py`、`pp_client.py`、`framesamp_modul_client.py`（R6） | TraceWriter 统一收集每步 action／state 完整数组，唯一收尾者按键合并、原子写 `arrays.npz`，重复键须 dtype／shape／sha 一致；各客户端与 recorder 的直接 `np.savez` 改为委托；步号到数组键映射显式记录；缺观测步独立计数不补零 | 现状：各处 `np.savez` 覆盖写、recorder 后关会盖掉新增键、rsync 合并可致索引不符 |
| `scripts/eval-official/official_hard_runner.py::{make_context,run_identity,build_parser}`、`run_official_hard.sh::{plan_round,orig_loop}`（R2） | 原侧接共享账本（reserve／claim_retry／claim_reset／settle）；`--policy-seed` 解析、转发到服务与官方 `Args.model_seed`／预测器、写进 trace 与结果；`run_official_episode(..., keep_official=True, official_provenance=...)` 保留官方视频进 `official/`、归档先于清理；identity 补 `attempt`，end 补 `steps_attempted／steps_observed／frames_recorded` | 现状：不接账本、无 seed、删官方视频、trace 缺字段致媒体验收必拒 |
| `scripts/eval-official/run_astra.sh`、`astra_hard_runner.py::{DATASET_STEP_PAIRING,check_pairing,TracedEnv,run_one,build_parser}` | Astra独立路线cap1800／模型seed转发、真实调用前守卫（守卫置于 `TracedEnv.step` 的计数与动作追加之前，拒第 1801 步不多落一行）、结果／trace记录 | 本版仅CPU／零外联验收；费用、两局硬守卫与test-hard0口径不变 |
| `scripts/eval-official/budget_ledger.py` 与 `env_client.py`／任务编排的预算构造；`env_client.py::{EnvSession.build,EnvSession.reset,AttemptLedger.start}` 与 `run_eval_gl.sh` 的 `--reset-budget` 必填校验 | 本轮cap870、infra50、expired0在每个消费者一致读取；**去掉每片 reset 硬拦截**：`--reset-budget` 改为可选，不给则只计量不抛 `ResetBudgetExhausted`（退出码 5 路径不再触发），共享账本 `reset_soft_cap` 维持只告警 | 历史默认不改；本轮实际守卫与报告同口径 |
| `scripts/eval-official/client-env/{pyproject.toml,uv.lock}`（仅确有依赖缺口时） | 真实 MemER 所需依赖声明与锁 | 优先复用现锁，根环境不动，不临时 pip 补正式依赖 |
| `tests/pipeline/eval/`、`tests/pipeline/evalx/{groundsg,astra,report}/` 的下表明确测试及契约登记 | 七路线接线、MemER装配／异常、seed反查、cap边界、恢复／媒体串组反例 | 纯CPU，不加载权重、不开外网、不做真实reset |
| `AGENTS.md`／`CLAUDE.md` 项目段、`readme.md`、`scripts/README.md`、`tests/README.md`、`docs/validation/legacy-names.md` | 主会话更新现行术语与对照 | 标记块及历史档案不改；本轮当前只写用户指定计划 |

表中新增 flag 与字段是拟新增接口，不是当前可运行参数；`eval_report.py --cap 1800` 为已有接口。

## 二、子代理分配表

派发前核对实施 BASE、主检出与各 worktree 状态；子模块在途改动绕开，执行副本必须另建且 clean。主会话负责暂存、提交、推送及资源操作。测试／契约文件先逐项落实归属，不能靠通配集合让两代理同时写同一文件。

| 子任务 | 目标／可写文件集合 | 禁触路径 | 接口契约与依赖／整合顺序 | 验收命令与判定行（工作副本 CPU） | 资源／共享文件裁决 |
|---|---|---|---|---|---|
| R1 | 本部分八节改名范围的 `scripts/**`、`src/robomme_hard/**`（含数据集接口 `test-hard`→`ood`、`test-hard0`→`hard-verify`、`env_metadata/test-hard/`→`env_metadata/ood/`）、`scripts/evaluation_hard.py` 示例、`tests/**`；现有子项目 lock 仅改项目名 | `src/robomme/**`、`third_party/**`、`docs/**`、规则文档、根依赖；不新增顶层入口 | 先完成改名及别名表，之后才派写入 R2／R3；顺序1 | 核心短测、命名残留检查、`CLIENT_REPLAY_EQ`、`TEST_INVENTORY` | GPU=0；独立worktree；R1完成前他人不写该集合 |
| R2 | `official_defs.py`、改名后 `groundsg_client.py`、原侧驱动 `official_hard_runner.py`／`run_official_hard.sh`、客户端子项目两依赖文件（必要时）；测试 `tests/pipeline/evalx/groundsg/{test_groundsg_context.py,test_groundsg_orig_runner.py}`（现硬断言两个变体，须随 MemER 改） | 上游源码、运行入口、其他客户端／报告／测试／文档 | MemER变体、adapter、预测器seed及日志接口交给R3；顺序2 | `uv run --no-sync python -m pytest tests/pipeline/evalx/groundsg -q`；`MEMER_WIRING` | GPU=0、端口=无；独立worktree；R2独占这三个对象 |
| R3 | `run_seat.sh`、`run_eval_gl.sh`、`env_client.py`、`budget_ledger.py`、`smvla_server.py`、`pp_server_wrap.py` | R2／R5／R6／R7 集合、三方源码、生成规格、测试／文档 | 共享入口、预算 token／lease／cap 注入、服务 seed、cap1800、deadline 与恢复计数持久化；只调用 R6／R7 冻结接口，不写媒体与 trace 文件；顺序3 | `uv run --no-sync python -m pytest tests/pipeline/eval -q`；`POLICY_SEEDS`、`EVAL_CAP`、`BUDGET_ENFORCEMENT` 反例 | GPU=0；独立worktree；共享运行入口／预算／身份归R3 |
| R6 | `trace_writer.py`、`recorder.py`、`smvla_client.py`、`pp_client.py`、`framesamp_modul_client.py`（改名后） | R2／R3／R5／R7 集合、上游源码 | trace 与完整数值接口先由主会话冻结（字段名、NPZ 键、合并规则）；R2／R5 的客户端按该接口接线，不由 R6 代写；顺序4 | `uv run --no-sync python -m pytest tests/pipeline/evalx/report -q -k "trace or arrays"`；`TRACE_ARRAYS=PASS` 反例（float32／float64、共／分目录、缺观测步、篡改字节） | GPU=0；独立worktree |
| R7 | `render_official_video.py`、`official_media_check.py`、`video_check.py`、`eval_report.py`、`model_eval_report.py`、`gate2_compare.py`；确需改 `seat_media_lib.sh` 归此 | R2／R3／R5／R6 集合；不与 R3 同写 `run_seat.sh` | 上游布局发布只发账本接受的 attempt、索引含模型／seed／dataset／side／key／accepted_attempt_id／源 sha、同名同 sha 幂等；`--expect-host` 来源模式；三个检查器对无帧 error 口径统一；顺序5 | `uv run --no-sync python -m pytest tests/pipeline/evalx/report -q -k "media or video or gate2 or report"`；`VIDEO_LAYOUT`、`OFFICIAL_MEDIA`、`GATE2_PROVENANCE` 反例（86 身份全无帧、infra a1＋accepted a2、重复发布、一侧异主机） | GPU=0；独立worktree |
| R5 | `scripts/eval-official/run_astra.sh`、`astra_hard_runner.py`、`tests/pipeline/evalx/astra/{test_astra_wiring.py,test_astra_stop_rules.py,test_run_astra_script.py,astra_fakes.py,contracts.delta.json}` | R2／R3／R4／R6／R7集合、受保护／三方源码、付费与GPU运行 | 按 R3／R6 冻结的字段契约只改Astra独立入口；cap 守卫放在计数与动作追加之前；顺序6 | `uv run --no-sync python -m pytest tests/pipeline/evalx/astra -q`；Astra的 `POLICY_SEEDS`／`EVAL_CAP` 和费用守卫 | GPU=0、外联=0、费用=0；Astra入口与测试唯一归R5 |
| R4 | `tests/pipeline/eval/{test_seat_scripts.py,test_env_session.py,test_policy_clients.py,test_smvla_server_units.py,test_eval_report.py,test_official_media_check.py,test_budget_ledger.py,test_identity_contract.py,test_seat_runner_e2e.py,test_eval_wiring.py,test_gate2_inputs.py,contracts.delta.json}`、`tests/pipeline/evalx/groundsg/{test_groundsg_official_adapter.py,groundsg_fakes.py,contracts.delta.json}`、`tests/pipeline/evalx/report/{test_sgx_trace_writer.py,test_trace_contract.py,trace_contract.py,test_sgx_render_official_video.py,test_sgx_video_check.py,test_sgx_model_eval_report.py,test_sgx_gate2_compare.py,contracts.delta.json}` 及对应 fixture（可按 GroundSG／共享执行与预算／trace 与媒体三类拆三个 R4 子代理，fixture 与 `contracts.delta.json` 各只有一个写者） | 生产代码、上游源码、Astra 测试与 R2 名下两个测试；不写R1改名未完成文件 | R1完成后按冻结接口并行准备；测试必须真实触发缺 seed、少 state、篡改数组字节、坏账本、重复启动、错 attempt 发布，不只改预期字符串；全部交付后整合，顺序7 | 定向CPU测试＋核心短测；7路线×3seed功能反例及cap、预算守卫必须实际执行 | GPU=0；独立worktree；这批测试由R4唯一写入，新增文件先列确切路径 |
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

定向测试先跑与修改链路对应的目录；预计超过5分钟的验证按tmux纪律执行。回放用两个检出目录：`git worktree add <BASE_DIR> 80a402cc`、`git worktree add <CAND_DIR> <仅改名冻结sha>`，`client_replay_eq.py --base <BASE_DIR> --candidate <CAND_DIR> --self-test`，工具校验两目录 `git rev-parse HEAD` 等于计划写的 sha，再验四条既有路线（GroundSG oracle、SimpleMemVLA、FrameSamp+Modulation、PonderPounce）× 三场景，不把种子／cap新增后的结果与旧1600结果要求逐位一致。MemER CPU测试使用真实摘取的官方类和假的PtEngine，覆盖三预测器互斥、adapter误配、键帧合并、日志序列化、空键帧／首个坏JSON、异常退出清理；原实现有缺陷时保留失败证据，不静默改上游。

全部模型清单的七路线都必须进入1800边界与0／7／42模型seed的CPU参数化测试，Astra走假服务、假planner／monitor的零外联夹具；功能实现通过不扩展本版实跑清单。测试另覆盖预算cap在reserve／retry／report三个入口一致读取、拒到期重试、局部reset耗尽即停。

## 四、运行 runbook（恢复后才执行）

1. 合并前后完成上述验收与命名整理，逐文件提交并按现有upstream推送。锁定最终sha，不复用旧执行副本／旧stage，不提交他人在途内容。
2. 先登记完整预算、新run_name、四个席位与资源处置口径；实际预算 `trajectory_cap=870, shared_infra_cap=50, expired_cap=50`（到期接续每身份 ≤1 次、占每身份 2 次名额、计入 870，不借 infra 的 50）由 `run_eval_gl.sh`／`run_official_hard.sh` 显式传给每个消费者（新侧与原侧），缺失即拒跑，不沿账本常量默认。再核本版五模型（含 GroundSG+QwenVL）资产与客户端依赖实际指向，`RUN_INPUTS`、`ASSETS`失败即停；`SMVLA_PY`／`PP_PY`／FrameSamp解释器及MemER客户端须实际核实。不为本版不跑模型新增下载、GPUsmoke或付费调用。
3. 清单参考 `docs/validation/sg-eval-gl-20261006-02/records/scripts/gl-scripts_build_manifests.py.txt`，从 `_v9_cells` 各格按局号升序取前2局，连交付spec逐项校验：共86个唯一环境身份。五模型seed7复用同一manifest指纹；每模型两片、43局／片。每模型先过其seed7单局最小smoke再启动该路线正式评估；失败停止受影响路线，不额外重跑来挑成功局，不跑seed0／42的smoke。
4. 新根 `R3=$N/sgeval-<确认日期>-03`，五组 `$R3/<模型>/seed7/` 下分别放stage／trace／media／report。全部任务明确指定 `--dataset ood --max-steps 1800 --strict-cap --policy-seed 7`（不再传 `--reset-budget`，reset 只计量）；MemER另指定新 `--groundsg-variant ground-sg-memer --memer-adapter <已核实路径>`，实际flag以R1／R3整合后接口为准。任务配置守卫拒绝本版seed0／42运行。
5. 10片入队，仍最多4席；**GL 永远经占位 job 运行、全局占住 + 排队的占位 job 合计最多 4 张卡（不是每个 job 4 张）**（用户 2026-10-06），job 由主会话自管（用户「我授权你自己来管理J0B。尽可能让我少排队」）：现有 4 个 job（63188714／15／16／19）到期前约 2 h 先提交接替 job 排队（此时 RUNNING + PENDING 仍 ≤ 4 张：到期 job 的卡在接替 job 排到前不重复计），席位空出立即补下一片，跑完按清单逐个 `scancel` 自己的 job，不动他人 job；沿原顺序 SimpleMemVLA → PonderPounce → FrameSamp+Modulation，再加入 GroundSG+QwenVL（`--episode-wall 3600`、`SEAT_XLA_MEM_FRACTION=0.65`、adapter 沿上一轮 `checkpoint-1200`）与 MemER，组内按固定分片／清单顺序运行。每席一次只起一个任务，服务起前探端口，记实际端口、节点、server_epoch、服务argv与种子，健康检查和首推分别验收；srun使用 `--gpu_cmode=shared`。共享预算 `$R3/budget-ledger.jsonl` 的route含模型和模型seed7，任务独立attempt账本记录 `accepted_attempt_id`；各片 `--reset-budget 106`，共享infra上限50，每身份重试最多1次。
6. 登录节点tmux会话前缀 `p3-`，smoke前缀 `p3-smoke-`；完整名、JobID与日志路径写launch.md。日志三件套与 `EXIT_CODE=` 尾行必须保留，监听完成／异常／无进展，不因tmux启动成功承诺代理会自动唤醒。
7. 每模型seed7单独运行报告和媒体验收（已有报告参数 `--cap 1800 --expect-total 86`），另按八.7 布局发布视频并核 `VIDEO_LAYOUT`（strict-cap 局文件名必须 `timeout`），校验权威身份集合、真实1800上限、视频唯一性／完整解码与来源；官方自产视频与重绘互斥，原始帧按现行验收后清理规则保留。4组各过覆盖、视频与官方媒体闸门后才汇总344局。
8. **MemER hard-verify 对拍（本机，与 GL 并行）**：不等 OOD 跑完；MemER 接入合入并过 `MEMER_WIRING` 后即可在本机 sled-vail 起，`CUDA_VISIBLE_DEVICES=0` 跑原侧席、`=1` 跑新侧席（或两侧串行同卡），tmux 前缀 `p3-local-`；两侧同机，`GATE2_PROVENANCE` 以同主机为准。局清单沿用上一轮第二档 `test-hard0` 的 16 任务 × 12 局 = 192（`$I/qwenvl/gate2/` 同式清单，重新生成并核指纹）；两侧各先 1 局 smoke（原侧经 `run_official_hard.sh --dataset hard-verify --max-steps 1300 --variant ground-sg-memer --memer-adapter <路径> --budget-ledger <共享账本>`，新侧经 `run_seat.sh` 同参数），再原侧 8 片 + 新侧 8 片进同样 4 席，`SEAT_XLA_MEM_FRACTION=0.65`、`--episode-wall 3600` 沿 QwenVL 口径；两侧都 `--policy-seed 7`。跑完用上一轮的对比工具（1005 计划 S6）出 `GATE2_INPUTS`／`GATE2_PROVENANCE`／`GATE2=INFO compared=192`，两侧 `OFFICIAL_MEDIA` 各过。是差异报告，不证明等价。
9. 留档结果与预算后提交、推送。原计划自动scancel改为按恢复时最新资源指令处理：此前用户要求保留四个最新job，未经新释放指令不自动取消它们；只停止本轮明确记录的任务步骤／tmux会话，禁止全局清理。

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

## 八、机制细节（从第一部分移入，2026-10-06 重构；第一部分只留决策信息）

### 八.1 模型清单说明与命名对照

「当前已接入」仅指核实到本仓库生产入口已有该路线，不表示1800步／可配置seed已经实现或动态验过。当前已有六条路线，另加本计划待接入的MemER；不把上游文档中尚未接入本仓库的其他组合自动算入支持清单。

模型seed使用显式整数参数，0／7／42作为最少CPU验收取值。seed作用于各模型实际使用的本地随机状态，不修改环境seed；Astra的付费云端API若无seed接口，不伪造该接口，也不把本地模型seed描述为云端响应逐位复现保证。

**命名对照（用户 2026-10-06 裁决：照官方；改活代码 + 现行文档）**

| 模型 | 展示名（官方 `docs/manual_evaluation.md`） | 代码／参数／路径 ID（官方 `MODEL_TYPE`／权重名） | Python 标识符 | 仓库旧名 |
|---|---|---|---|---|
| 本次评估模型 | FrameSamp+Modulation | `perceptual-framesamp-modul` | `framesamp_modul` | `mme`、`mmevla` |
| GroundSG 两变体 | GroundSG+Oracle、GroundSG+QwenVL | `groundsg`（变体 `oracle`／`qwenvl`） | `groundsg` | `mmesg` |
| 新增评估模型 | MemER | 官方 `MODEL_TYPE=MemER`；服务权重 `symbolic-grounded-subgoal/79999`；客户端 `use_memer` | 接入现有 GroundSG 装配，新增内部变体 `ground-sg-memer` | 原计划未接入 |
| Astra | 3-tier Astra（用户 2026-10-06 裁决，非官方文档名） | `astra`（不改） | `astra` | 展示名 Astra |

MemER 展示名以锁定官方源码 `third_party/mme-vla/docs/manual_evaluation.md` 的 `MemER` 节及 `scripts/eval.sh` 的 `MODEL_TYPE == MemER` 分支为准；`ground-sg-memer` 只是本仓库拟新增的路线标识。不能将 MemER 展示为自造的「GroundSG+MemER」。

保留不改（官方名）：家族名 MME-VLA（Symbolic／Perceptual／Recurrent MME-VLA）、`third_party/mme-vla`、`.gitmodules`、上游类 `MMEVLAWebsocketClientPolicy`、上游配置 `mme_vla_suite`。
### 八.2 改名范围

- **改**：原计划盘点活代码与测试 91 个文件、约 900 处；这是改名范围的历史盘点，派发前按冻结提交重新列精确文件清单。
  - 文件名：`mme_client.py`、`mmesg_client.py`、`orig_observer/{mme_client_wrap,mme_proxy}.py`、`run_orig_mme.sh`、`orig-mme-client-env/`、`test_mme_transport.py`。
  - 参数：`--mme-variant`（实为 GroundSG 变体）、`--mme-ckpt`、`--mmesg-ckpt`、`--episode-wall-mme`。
  - 环境变量：`MME_PY`、`MME_CKPT`、`MMESG_CKPT`、`MME_VARIANT` 等。
  - 策略标签 `mme`、`mmesg`，以及测试名、契约条目。
- **现行文档也改**：`AGENTS.md`、`CLAUDE.md` 的项目段（标记块不动）、`readme.md`、`scripts/README.md`、`tests/README.md`。
- **不改**：`docs/validation/`、`docs/plans/` 历史留档（约 3200 处；里面有 NFS 真实路径和 SHA256SUMS）。指向磁盘或 NFS 真实目录的字符串（如 `sg-eval/ckpt/mme/...`、`mmevla-testhard*`）也保留原样，旁注「历史目录名」。新增 `docs/validation/legacy-names.md` 写旧名到新名的对照。
- **兼容**：读历史逐局行、预算账本、v7.5eval 留档的工具（`env_client.py`、`client_replay_eq.py`、`orig_results_adapter.py`、`observer_status.py`、`cap_probe.py`、`site_catalog.py`、报告类）读入时把旧标签映射到新名，写出只写新名，CLI 只接受新名。别名表只在 `official_defs.py` 放一份。
- **改名阶段行为零变化**：只改名字，不改任何逻辑和数值，独立过回放闸门后再接入 MemER、三种子和 1800 步；后三项属于有意新增或改变的行为，不能用改名回放通过声称全链等价。

### 八.3 MemER、可配置模型 seed 与 1800 步（改名合入后）

**MemER 接入。** 当前 `scripts/eval-official/official_defs.py::{VARIANTS,PREDICTOR_NAMES,load_groundsg,make_args,assert_one_predictor,build_predictor}` 仅支持 Oracle／QwenVL，而且显式拒绝 `use_memer`；需要扩展装配，摘取锁定上游的 `subgoal_predictor.py::MemERSubgoalPredictor` 与 `subgoal_prediction/qwenvl/api_memer.py::Qwen3VLModelMemER` 原文，保持官方键帧、历史子目标、推理请求与解析机制。传入 `subgoal_type="grounded_subgoal"`、`use_memer=True`，其余预测器开关关闭，服务仍加载 `symbolic-grounded-subgoal/79999`。

官方 `Args::memer_adapter_path` 默认指向 `vlm_subgoal_predictor/memer/grounded_subgoal/checkpoint-1300`。这不是已核实的本机／NFS 资产：实施前必须确定实际路径、来源提交、文件数、字节数与 SHA256，并纳入资产前置核验；不得用 QwenVL 的 `checkpoint-1200` 代替。现有 `client-env` 锁包含 ms-swift／transformers／peft，可作为复用起点，真实 adapter 和 `flash_attention_2` 加载尚未验证。新侧 `mmesg_client.py::{qwen_begin,qwen_end}`（改名后 `groundsg_client.py`）还要支持 MemER 每局临时目录、`ep*_MemER_log.jsonl` 归档及正常／异常清理；不能只给 QwenVL 换展示名。

**MemER 兼容层（用户 2026-10-06 裁决「同意兼容层」；两侧同一实现，记录指纹，不改 gitlink）。**

官方 `subgoal_prediction/qwenvl/api_memer.py::Qwen3VLModelMemER` 核实到三处确定越界（2026-10-06 只读子代理对锁定提交 `ecf086c3` 逐行核实）：

| # | 位置 | 缺陷 | 触发条件 |
|---|---|---|---|
| 1 | `update_history_subgoals` 末尾无条件调用 `merge_key_frame_paths`，后者 `cur = [nums[0]]` | 关键帧记忆为空时访问空列表首项，IndexError | 任一次回复 `keyframe_positions` 为空且此前记忆仍空；首次提问输入只有 1 张画面、关键帧栏为 `[]`，模型答空列表是最自然的结果 |
| 2 | `call` 的 `except` 分支 `subgoal = self.subgoals[-1]` | `self.subgoals` 在 `start_new_episode` 置空后全文无任何写入，永远为空，兜底本身再抛 IndexError | 任何轮次解析异常（含缺陷 1 抛出的异常、坏 JSON、缺键） |
| 3 | `_get_current_execution_frame_paths` 从末帧起隔一张取 8 张 | 执行帧少于 15 张时下标越界 | 第二次提问时帧数不足（官方默认一次执行 16 步通常够，提前提问或短局可能不够） |

兼容层改法（只动我们摘出来的那份副本，`official_defs.load_groundsg` 摘取后用 AST 级补丁落地，补丁内容 sha256 作为「实现指纹」写进 `MEMER_COMPAT` 判定行、结果行与媒体 provenance）：

1. `merge_key_frame_paths` 开头加「记忆为空则直接返回」；非空时逻辑原样。
2. `call` 里每次成功解析出 `current_subtask` 后 `self.subgoals.append(current_subtask)`；`except` 分支改为「有上一次合法子目标则沿用，否则抛出具名异常 `MemERResponseError`」，由客户端把该局记成 `status=error, terminal_reason=error, error_kind=model_response_error`，不伪造子目标、不重跑。
3. `_get_current_execution_frame_paths` 改为「不足 15 张时从现有帧里按同样间隔能取几张取几张」，够 15 张时与官方逐字相同。

**原始 prompt 原文（英文照抄官方，中文为注释不是翻译；修改前后两个模型看到的内容完全相同）**

system prompt（`__init__` 里的 `self.system_prompt`，逐字）：

```text
You are a robot program that predicts actions. The current input images from the front-view camera shows the most recent actions the robot has executed. The past keyframes are selected frames of particular importance from all the actions the robot has executed so far. Based on these, output the current subtask the robot should execute and nothing else. Some tasks may have a video input for initial setup, some may not.

Return a JSON with:
- current_subtask: the action that should be executed at the current timestep
- keyframe_positions: list of frame positions (1-indexed) from the current input images where actions change
```

注释：`current subtask` 就是交给动作模型的子目标文字；`keyframe_positions` 是模型从「当前输入图像列表」里挑出的帧序号（从 1 数），代码据此把对应画面存进关键帧记忆；提示词没有要求列表非空，也没规定空列表怎么办。

user prompt 模板（`prepare_infer_request` 里的 `user_prompt`，逐字；`{...}` 为运行时填入）：

```text
{video_prefix}The task goal is: {task_goal}
Here are the selected frames from the entirety of the full execution that are of particular importance:{keyframes}
Here is current input image list from the front-view camera: {current_frames}

What subtask should the robot execute and what is the keyframe position?
```

注释：`{video_prefix}` 在任务带演示视频时为 `The task has a video input for initial setup: <video>\n`，否则为空串；`{task_goal}` 是任务目标全文；`{keyframes}` 与 `{current_frames}` 由 `_wrap_images` 生成——列表为空时是字面 `[]`，非空时是 `[<image>, <image>, …]`，每个 `<image>` 对应 `images` 字段里的一张 png；请求的 `images` = 关键帧图片 + 当前执行帧图片，按此顺序。推理参数 `max_tokens=128, temperature=0`（贪心解码，模型 seed 对该预测器无影响）。

首次提问（关键帧记忆为空、只有 1 张执行帧）实际送出的 user prompt：

```text
The task goal is: <任务目标全文>
Here are the selected frames from the entirety of the full execution that are of particular importance:[]
Here is current input image list from the front-view camera: [<image>]

What subtask should the robot execute and what is the keyframe position?
```

注释：关键帧栏是字面 `[]`、没有图片；执行帧栏 1 张图。这段文字在修改前后一字不差——兼容层不碰 `prepare_infer_request`、不碰 system prompt、不碰 `images` 的拼法。

**兜底情形：修改前 vs 修改后**

| 情形 | 模型回复 | 修改前（官方原文） | 修改后（兼容层） |
|---|---|---|---|
| A 首次回复关键帧为空 | `{"current_subtask":"move cube","keyframe_positions":[]}` | 跳过存记忆 → 无条件合并 → `nums[0]` IndexError → except → `self.subgoals[-1]` 再 IndexError → 异常逃出 `call` → 该局在第一步动作前崩，记 error | 跳过存记忆 → 合并发现记忆为空直接返回 → 取出 `move cube` 交给动作模型 → `subgoals=["move cube"]` → 局继续；下一次提问关键帧栏仍是 `[]` |
| B 后续回复关键帧为空、记忆已非空 | 同上 | 存记忆跳过 → 合并在已有记忆上正常执行 → 不崩（官方可用） | 同官方，逐字相同 |
| C 坏 JSON，此前已有合法子目标 | 非 JSON 文本 | `json.loads` 抛错 → except → `subgoals[-1]` IndexError → 崩 | 沿用上一次合法子目标，记 `fallback_used=1`，局继续 |
| D 坏 JSON，此前没有合法子目标 | 非 JSON 文本 | 同 C，崩 | 抛 `MemERResponseError` → 该局 `status=error, error_kind=model_response_error`，不伪造子目标、不重跑 |
| E 缺 `keyframe_positions` 键 | `{"current_subtask":"…"}` | KeyError → except → 崩 | 与 C／D 同一兜底路径 |
| F 第二次提问时执行帧少于 15 张 | — | `_get_current_execution_frame_paths` 下标越界，在 try 之外，崩 | 有几张取几张，提问照常；够 15 张时与官方逐字相同 |

动作模型（GroundSG 动作服务 `symbolic-grounded-subgoal/79999`）在所有情形下看到的都只有：当前前视图、腕部图、机器人状态、子目标文字（`current_subtask` 经 `_parse_subgoal_for_vla` 把 `<|box_start|>(x,y)<|box_end|>` 换成画面坐标后的字符串）；它看不到关键帧、看不到提问、看不到回复原文。兼容层对它的输入没有任何改变，差别只在「官方原文下它根本收不到那条子目标（程序已崩）」。

验收 `MEMER_COMPAT=PASS cases=6 fingerprint=<补丁 sha256>`：CPU 夹具用真实摘取的类配假 `PtEngine`，逐一跑 A～F 六种回复，断言修改后的子目标输出、记忆内容、日志行与异常类型；另断言「记忆非空且回复合法」时兼容层与官方原函数输出逐字节相同（B 情形回归）。两侧（本机对拍原侧与新侧）同一补丁、同一指纹，`GATE2` 报告与成绩表注明「MemER：官方实现 + 三处越界兼容补丁（指纹 …）」。

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
五模型：5 模型 × 上述每模型86局 = 430 局（2026-10-06 加 GroundSG+QwenVL；Oracle 沿用 1004 轮 1600 步 800 局成绩不跑）
分片：5 模型 × 1 模型种子（7）× 2 片 = 10 片，每片 43 局
```

执行副本用全部改动整合后的冻结提交新建（拟名 `robomme_benchmark-sgeval3`，存在则另取新名）；新 `run_name` 拟为 `sg-eval-gl-20261006-03`，正式启动前确认未使用。1800 步的新结果不复用旧 1600 步 accepted 终态；旧成绩只作注明步数口径的参照。

### 八.4 耗时估算与待验证项

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

### 八.5 完整预算细则（待运行授权）

第二阶段结束快照见 `docs/validation/sg-eval-gl-20261006-02/result.md` 第⑦节：`BUDGET_ENFORCEMENT=PASS trajectories=2064/6366 resets=4908/141430 astra=0/2 shared_infra=0/50`；其中 4302 是**轨迹**余额，不能当 reset 余额或本轮批准规模。恢复前只读核对账本，保留中断预约的处理证据，不回滚历史消耗。

| 项目 | 轨迹尝试上限 | reset 额度／实际调用口径 |
|---|---|---|
| 正式首试（2026-10-06 五模型） | `5 模型 × 1 模型种子（7）×（14 任务 × 2 档 × 2 局 + 7 任务 × 1 档 × 2 局 + 6 任务 × 1 档 × 2 局 + 2 任务 × 1 档 × 2 局）=430` | 正常链每 attempt 的 build 1 次 + reset 1 次，基线 `430×2=860`；10 片每片 `2×43+20=106` 只作计量参考（共 1060），不再硬拦截 |
| 最小 smoke | `5 模型 × 1 模型种子（7）× 1 任务 × 1 档 × 1 局=5`；逐模型先做单局最小验证，不跑seed0／42 | 每局计量3，共15；正常调用 `5×2=10`。不额外做cap实跑探针，用CPU环境调用计数夹具验证 |
| 基础设施重试 | 全阶段共享最多 50 次，且每 `(模型,policy_seed,环境身份)` 最多 1 次 | 消耗上述分片／smoke 既有 reset 额度，双侧任一额度不足即停；任务正常失败或 timeout 不重试 |
| 到期接续（用户 2026-10-06「4可以接续」） | 每身份最多 1 次，全局 `expired_cap=50`，计入 870 总上限 | 用接替占位 job 在同一机器分工下续跑；不借 infra 50 次；不继承旧账本默认 500 |
| MemER hard-verify 对拍（本机，与 GL 并行） | `2 侧 × 16 任务 × 1 档 × 12 局 = 384` | 两侧各 8 片，每片 `2×24+20=68` 只作计量，16 片共 1088；正常基线 `384×2=768`；原侧同样经共享账本预约 |
| 对拍 smoke | `2 侧 × 1 局 = 2` | 每局额度 3，共 6；正常 `2×2=4` |
| **本轮合计上限（2026-10-06 加 QwenVL 后）** | **`430+5+384+2+50=870`** | **reset 自 2026-10-06 起只计量不拦截：预计 `(2×43+20)×10 + 15 + 1088 + 6 = 2169` 量级；正常首试基线 `860+10+768+4=1642`** |

CPU 回放／夹具消耗真实 reset／轨迹均为 0。新预算账本同时保留旧消耗的只读快照，以「旧消耗 + 本轮消耗」核对此前总授权；新根目录不能重置整项工作的累计计数。`budget_ledger.py` 的全局 reset 软阈值不等于硬拦截；本轮硬边界来自每个 runner 启动前明确的 reset 额度，禁止追加 runner 绕过总和。上述是拟申请的完整新增上限，实际重试亦受共享 50 次限制。

所有实际领取消费者统一注入本轮 `trajectory_cap=870, shared_infra_cap=50, expired_cap=50`，不能只在收尾报告写上限；若沿历史累计账本则轨迹上限为 `2064+870=2934`，相对原6366余额3432。历史 `open=8` 已包含在2064，不能再次扣除或擅自释放。单smoke额度3不足两次完整attempt的4次领取，每片额外20仅够该片10次完整重试；50是全局上限，不保证任意分布的50次重试均能完成，局部额度耗尽直接停止。

### 八.6 成绩报告口径

成绩只报告本版seed7的逐格／任务／档位与总成功率，每个任务难度格 `n=2`；没有三种子运行，不产出三种子均值／标准差或冒称已验证多种子成绩。与旧1600步成绩的差异注明条件已变，不宣称等价或无回归。

### 八.7 视频目录与命名（2026-10-06 两个只读子代理查实；用户选定「照上游 mme-vla」）

用户记忆的「task suite / task name / model seed 三层 + `<ep_num>_<task_goal>_<success/fail/timeout>.mp4`」在任何来源都不成立。各来源实际规则：

| 来源 | 目录层级 | 文件名 | 终态字面量 |
|---|---|---|---|
| 官方网站 robomme.github.io、README、`doc/submission/model_example.md`、challenge 提交说明 | 未规定；提交只是向 `doc/submission/<model>.md` 提 PR 附成绩表（列名 Suite / Task / Seed 7 / Seed 42 / Seed 0 / Avg），不含视频 | 未规定 | 未规定 |
| 上游 mme-vla `examples/robomme/eval.py` + `utils.py::RolloutRecorder` | `<save_dir>/<policy_name>/ckpt<model_ckpt_id>/seed<model_seed>/[gemini｜qwenvl｜memer｜oracle]/videos/`（子目标层只在 `subgoal_type in SUBGOAL_TYPES` 时存在） | `{env_id}_ep{episode_id}_{success_flag}_{task_goal}_{difficulty}.mp4` | `success`／`fail`／`timeout`（`epstate.count > max_steps`）；`unknown` 不存盘 |
| 官方 `scripts/evaluation.py`（与上游逐字节相同） | `runs/saved_videos/` 平铺 | `{task}_ep_{episode}_{outcome}_{task_goal}.mp4` | `info.get("status","unknown")` |
| `src/robomme` `RobommeRecordWrapper`（冻结） | `<output_root>/videos/` | `{env_id}_ep{episode}_seed{seed}[_FailRecover*]_{difficulty}_{goal}.mp4`，失败前缀 `FAILED_` | 成功无标记、失败 `FAILED_`、无 timeout |
| SimpleMemVLA `robomme_sim/eval_success.py` | `<video_dir>/<task>/` | `{task}__ep{episode}__{succ｜fail}.mp4` | `succ`／`fail` |
| PonderPounce | 自身无录像代码，由 vla_eval 框架按 yaml 录到 `<out>/shard_<gpu>_<sim>/` | 本仓库内未找到 | 未找到 |
| 我们新侧现状（`run_eval_gl.sh::pub_root`、`run_seat.sh::publish_dir`、`render_official_video.py::render_episode`、`env_client.py::v8_key`） | `<media-root>/<模型标签>/<dataset>/new/<task>_<tier>_<环境seed>.a<attempt>/official/`（无模型 seed 层；路径里的 seed 是环境构造 seed） | `official-rerender__<task>_ep<源局或builder局>a<attempt>_<terminal_reason>_<task_goal>_<tier>.mp4`；GroundSG QwenVL 保留官方原生名（尾部 `hard`）；超 255 字节截断加哈希，完整名在 `official/render.json` | `success`／`fail`／`timeout`／`error`；旧口径 strict-cap 超时局 `status=timeout` 但 `terminal_reason=error`，文件名带 `error` |

本计划采用的布局（第一部分二第 ③ 件）：`<run 根>/<模型 ID>/seed<policy_seed>/[oracle｜qwenvl｜memer/]videos/<task>_ep<N>_<success｜fail｜timeout>_<task_goal>_<tier>.mp4`，与上游 `eval.py` 的差别只有三处并写明：没有 `ckpt<id>` 层（本仓库权重由 `RUN_INPUTS` 记录）、`ep<N>` 后不带 attempt（只发布账本接受的那一次）、末尾用 tier 替 difficulty。本机现存视频产物：上一轮 5 × 192 在 NFS `$R2/gate2-new-*/media/`；本机 `artifacts/sg-evaluation/` 下只有各路线 1 局冒烟与 1004 的本机 800 局。HF 打包上传按用户 2026-10-06「先不做打包上传的问题」不纳入本计划（仓库现无按模型打包评估视频上传 HF 的脚本；已有 bucket 流程与 greatlakes 纯 CPU 校验 job 的要点留待以后另立计划）。

### 八.8 本版运行口径全文（2026-10-06 从第一部分三移入；第一部分只留一屏。⚠ 本节为移入时的快照：之后用户追加「加 GroundSG+QwenVL 实跑」「Oracle 不跑」「hard-verify 对拍改在本机并行」，以第一部分三与八.5、八.9 为准）

两件事，按顺序：先四个模型的 V9 第三档；最后再跑 MemER 的 `test-hard0` 原侧 vs 新侧对拍。

```
 开工 ─┬─ 1 改名（R1）→ CLIENT_REPLAY_EQ、OFFICIAL_NAMES
       ├─ 2 功能（R2 MemER ｜ R3 共享入口 seed+1800 ｜ R5 Astra 入口 ｜ R4 CPU 测试）→ 七路线 CPU 夹具
       ├─ 3 冻结执行提交、核 MemER 资产、四模型各 1 局 smoke（seed 7）
       ├─ 4 GL A40：4 模型 × 2 片 = 8 片进 4 个占位席位，每片 43 局
       ├─ 5 四组各自验收 → 344 局汇总
       ├─ 6 最后：MemER test-hard0 对拍，原侧 192 局 + 新侧 192 局（GL A40，同一批局清单）→ 差异报告
       └─ 7 留档、commit、push
 本版不跑 seed 0／42；GroundSG+Oracle／QwenVL 与 Astra 只补功能、只 CPU 验证，不实跑。
```

| 项 | 本版口径 |
|---|---|
| 跑哪五个（2026-10-06 加 QwenVL） | FrameSamp+Modulation、SimpleMemVLA、PonderPounce、MemER、GroundSG+QwenVL；Oracle 沿用 1600 步旧成绩 |
| 数据与档位 | V9 `test-hard` 第三档，43 格 = 14 任务 × 2 档（xhard1/2）+ 7 任务 × 1 档（xhard3）+ 6 任务 × 1 档（xhard4）+ 2 任务 × 1 档（xhard5） |
| 每模型局数 | 1 模型种子（7）× 43 格 × 2 局 = 86 局（环境每格仍取前两局，环境 seed／spec 不动） |
| 合计 | 5 模型 × 86 = 430 局；10 片 × 43 局；4 个占位 job（63188714／15／16／19，可用性以恢复时为准） |
| 最后再跑：MemER hard0 对拍 | `test-hard0`，1300 步，两侧同一批 16 任务 × 1 档 × 12 局 = 192 局（沿用上一轮第二档的局清单）；原侧 = 官方 `eval.py` 的 MemER 分支经我们的 `official_hard_runner.py` 驱动（与 GroundSG 原侧同一套驱动），新侧 = 我们的 `groundsg_client.py` 走 `ground-sg-memer`；两侧动作服务都 `--policy-seed 7`、同一份 adapter；两侧各 8 片 × 24 局；产出差异报告 `GATE2=INFO`，不证明等价 |
| 占位 job 单卡 | 每席 1 张 A40，与上一轮相同。MemER 与 GroundSG+QwenVL 一样「动作服务 + 4B 预测器同卡」：服务取 `SEAT_XLA_MEM_FRACTION=0.65`，Qwen3-VL-4B + LoRA 用剩余显存（上一轮 QwenVL 实跑通过）；MemER 每次请求多带关键帧，激活显存略大，1 局 smoke 时核实。单卡不影响可行性，只影响吞吐（8 片排 4 席）|
| 运行参数 | `--max-steps 1800 --strict-cap --policy-seed 7`；MemER 另加 `--groundsg-variant ground-sg-memer --memer-adapter <已核实路径>` |
| run_name | 拟 `sg-eval-gl-20261006-03`，执行副本拟 `robomme_benchmark-sgeval3`，起跑前确认未用 |

**用户原话（2026-10-06）**：「还需要实现MemER和seed0/7/42，1800步的调整」；「seed只作为实现的功能」「这版还是跑自己的七，还是每一个难度跑两个」；「给出现在所有支持模型的清单，都要支持1800步，都要支持不同seed，模型seed」「我们现在实跑只跑我说的这些模型」。

**预算**：

| 项目 | 轨迹上限 | reset 口径 |
|---|---|---|
| 正式首试 | 5 模型 × 1 种子 × 43 格 × 2 局 = 430 | 每片计量 2 × 43 + 20 = 106，10 片共 1060（只计量） |
| 最小 smoke | 5 模型 × 1 局 = 5 | 每局 3，共 15 |
| MemER hard0 对拍（最后） | 2 侧 × 16 任务 × 1 档 × 12 局 = 384 | 两侧各 8 片，每片硬额度 2 × 24 + 20 = 68，16 片共 1088 |
| 对拍前两侧各 1 局 smoke | 2 | 每局 3，共 6 |
| 基础设施重试 | 全阶段共享 ≤ 50，每身份 ≤ 1 次；到期重试 0 | 消耗上面的既有额度 |
| **合计** | **430 + 5 + 384 + 2 + 50 = 870**（历史累计 2064 + 870 = 2934，在 6366 内） | **约 2169，只计量不拦截** |

**耗时**：改名约 2～2.5 小时；三个老模型按旧第二档单局耗时 × 1.5 × 1.125 粗估共约 459 席位分钟；MemER 无实测，等它 1 局 smoke 后再估整体，原「5～6 小时」结论作废。

**验收**：

| 查什么 | 判定行 |
|---|---|
| 改名只改名 | `OFFICIAL_NAMES=PASS`、`CLIENT_REPLAY_EQ=PASS`（三条旧路线） |
| MemER 真接入与资产 | `MEMER_WIRING=PASS predictor=MemERSubgoalPredictor`、`ASSETS=PASS`、`MEMER_SMOKE=PASS` |
| 七路线种子与 cap（CPU） | `POLICY_SEEDS=PASS models=7 seeds=0,7,42 cases=21 cpu_only=1`、`EVAL_CAP=PASS models=7 dataset=test-hard max_steps=1800 rejected_step=1801` |
| 规格与上游未动 | `DELIVERY_UNCHANGED=PASS`、`UPSTREAM_GUARD=PASS` |
| 每组结果与视频 | 每组 `EVAL_COVERAGE=PASS expected=86 missing=0`、`EVAL_VIDEOS=PASS videos=86`、`OFFICIAL_MEDIA=PASS total=86 fail=0`、`VIDEO_LAYOUT=PASS model=<m> seed=7 videos=86 error_named=0`（上游 mme-vla 布局，三态命名）、`TRACE_ARRAYS=PASS episodes=86 missing=0`（每步 action／state 完整数组） |
| 完整矩阵与预算 | `RUN_POLICY_SEED=PASS seed=7 combinations=5`、`STAGE3_MATRIX=PASS policy_seed=7 combinations=5 unique_terminal=430`、`BUDGET_ENFORCEMENT=PASS` |
| MemER hard0 对拍（最后） | 两侧各 `EVAL_COVERAGE=PASS expected=192 missing=0`、`OFFICIAL_MEDIA=PASS total=192 fail=0`；`GATE2_INPUTS=PASS expected=192 missing=0 extra=0`、`GATE2_PROVENANCE=PASS local_rows=0`、`GATE2=INFO compared=192 …`（两侧成功率、终态相同数、翻转数、McNemar p、逐步一致数） |

成绩只报 seed 7 的逐格／任务／档位与总成功率，每格 n=2；与旧 1600 步成绩的差异注明条件已变，不宣称等价。

**步骤**：

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 等用户再次说「开工」；核对预算、MemER 资产边界、新 run_name | 授权记录与 BASE 明确 |
| 1 | R1 改名；主会话改现行文档与旧名对照表 | `OFFICIAL_NAMES`、`CLIENT_REPLAY_EQ`、核心短测 |
| 2 | R2 接 MemER，R3／R5 让七路线支持种子与 1800，R4 补 CPU 测试 | `MEMER_WIRING`、`POLICY_SEEDS`、`EVAL_CAP`、`DELIVERY_UNCHANGED` |
| 3 | 核资产、冻结执行副本、生成清单与五个 seed 7 任务组、每模型 1 局 smoke | `RUN_INPUTS`、`ASSETS`、`MEMER_SMOKE`、`RUN_POLICY_SEED` |
| 4 | GL A40 跑 10 片 | 退出码、进度、预算 |
| 5 | 五组验收、汇总 | `EVAL_COVERAGE`、`EVAL_VIDEOS`、`OFFICIAL_MEDIA`、`TRACE_ARRAYS`、`STAGE3_MATRIX` |
| 6 | 最后：MemER hard0 对拍——两侧各 1 局 smoke 后，原侧 8 片 + 新侧 8 片进 4 席，跑对比工具 | `GATE2_INPUTS`、`GATE2_PROVENANCE`、`GATE2=INFO compared=192` |
| 7 | 留档、commit、push；资源按最新指令处置 | `BUDGET_ENFORCEMENT`、`result.md` 落盘 |

**子代理分工与合并（简述）**：R1 改名先单独做完、审两次、合入；之后同一时刻派 R2（MemER 装配：`official_defs.py`、GroundSG 新侧客户端与原侧驱动 `official_hard_runner.py`／`run_official_hard.sh`）、R3（共享入口：席位脚本、`env_client.py`、各服务端、报告与预算）、R5（Astra 两入口及其测试），R4 并行准备与 R5 不重叠的 CPU 测试。各管互不重叠的文件、各在自己的 worktree 写；合回顺序 R1 → R2 → R3 → R5 → R4，每合一个审禁触路径与定向测试，全部过后冻结执行提交。主会话自做现行文档、资产清单与 GL 编排。

改名范围明细、种子与 cap 的逐层传递、链路图、各档任务名单、耗时推导与预算细则见第二部分八节。

### 八.9 预算上限清单与防卡死／防重复生成机制（2026-10-06 核实；用户「不再需要reset上限」）

**代码里现有的上限**（`scripts/eval-official/budget_ledger.py`、`env_client.py`）：

| 上限 | 位置 | 性质 | 本版处置 |
|---|---|---|---|
| `trajectory_cap` | 共享账本 `BudgetLedger.__init__`／`claim`，领不到抛 `BudgetExhausted` | 硬 | 保留，870 |
| `reset_soft_cap` | 共享账本，超过只打 `BUDGET_WARN …（软上限，只告警不拦）` | 软 | 保留为计量，预计约 1954 |
| 每片 `--reset-budget` | `env_client.py::EnvSession.build/reset` 每次真实调用前领一次，耗尽抛 `ResetBudgetExhausted` → 退出码 5，`run_seat.sh` 不重启 | 硬 | **去掉**：参数改可选，缺省只计量（R3） |
| `shared_infra_cap` | 共享账本 `claim_retry`，跨原侧／新侧、跨席位原子领取 | 硬 | 保留，50 |
| `V8_MAX_ATTEMPTS = 2` | `env_client.py`，每身份最多两次尝试（infra 与 expired 都占名额） | 硬 | 保留 |
| `expired_cap` | 共享账本，Slurm 到期中断的重试 | 硬 | 0 |
| `astra_cap` | 共享账本 | 硬 2 | 本版不用 |

**上一轮第二档对拍覆盖**（`docs/validation/sg-eval-gl-20261006-02/result.md` ③ 节）：GroundSG Oracle（188/192 终态相同）、GroundSG QwenVL（177/192）、PonderPounce（192/192）、SimpleMemVLA（192/192）、FrameSamp+Modulation 即旧名 MME（174/192）五模型各 192 局均已出 `GATE2=INFO`；Astra 只有 ≤2 局 smoke；MemER 未跑过，本版第 6 步补。

**防卡死（`run_seat.sh`，现有，本版保留）**：服务就绪超时 `READY_TIMEOUT=1200` 秒并 `kill -0` 查存活；客户端首局另放宽 `FIRST_EXTRA=600` 秒；单局墙钟 `wall_of`（smvla 900、mme 1200、mmesg／pp 1800 秒，`--episode-wall*` 可覆盖，QwenVL／MemER 用 3600）；`idle_s` 取 `progress.json`（无则 `client.log`）mtime，超过「墙钟 + 600 + 600」秒（不小于 `NOPROG_S=1200`）不更新即打印 `NO_PROGRESS`，杀掉并 `restart_server` 一次，第二次 `INFRA_EXHAUSTED … no_progress_twice` 退出码 4 停这一片；`MAX_CLIENT_RESTARTS=8`、`MAX_SERVER_RESTARTS=2` 超过同样 `INFRA_EXHAUSTED`。退出码 4 的片由主会话按共享重试额度决定是否重起，不自动无限重起。

**防重复生成（`env_client.py`，现有，本版保留）**：权威终态 = 每身份第一条 `accept` 行的 `accepted_attempt_id`；success／fail／timeout 与非 infra 的 error 都 accept、永不重跑；只有 infra 错误才重试，且每身份总尝试 ≤2、重试名额经共享账本 `claim_retry` 原子领取（并发只有一方成功）；续跑 `pending_identities` 打印 `resume_skip= accepted= attempts_full= todo=`，已接受或已用满 2 次的身份跳过；每片输出独立目录、发布用 sha256 核对后 `mv -T`，重复发布落 `.dupN` 不覆盖；最终 `EVAL_COVERAGE expected=86 missing=0` 与 `STAGE3_MATRIX unique_terminal=344` 断言完整性。去掉 reset 硬上限后，重复生成的边界由「轨迹硬上限 870 + 每身份 2 次 + 共享重试 50」三道承担，任一耗尽即停受影响范围并报告。

### 八.10 Codex 审计（2026-10-06，固定提交 `894fa97f`）逐条核实与处置

九个只读子代理（sonnet）各核一条，对照 `git show 894fa97f:<path>` 原文；未运行任何代码。

| 条 | 审计意见 | 核实 | 处置（归属） |
|---|---|---|---|
| 1 | runbook／八.5 仍写四模型、`test-hard`、`--reset-budget 106`、344 | 属实 | 本轮已统一（runbook 2～5、八.5、红线 6：改名阶段保持 `ood ↔ 1600`） |
| 2 | 回放闸门两侧同 crash 仍 PASS；参数要目录；旧名写死；路线四条 | 属实（`compare` 对同 crash `continue`；无事件下限；`Path(args.base)` 当目录；`ROUTES=("mmesg","smvla","mme","pp")`） | R1 交付：目录 + sha 校验、四路线 × 三场景、同 crash／零事件 FAIL、强制 `--self-test` |
| 3 | 原侧不接共享预算；cap 870／0 未落地；原侧无模型 seed | 属实（原侧 grep `BudgetLedger` 零命中；`_open_shared` 只传路径，常量 6366／50／500；runner 无 seed 参数） | R2 原侧接账本与 seed 链；R3 启动脚本显式传 cap；红线 6 |
| 4 | 加载期日志刷新骗过无进展检测；重启计数不持久 | 新侧属实（`policy_context` 无期限，`idle_s` 看 `client.log`）；原侧驳回（看 `results.jsonl`） | R3：绝对 deadline、具名 phase 监督、计数持久化 |
| 5 | 重试领取非幂等；无跨进程排他；坏行不拦 | 属实（`claim_retry` 先于 `attempt_start`；`threading.Lock` 仅进程内；`_read` 坏行只在 report 判 FAIL；`_append` 不补换行） | R3：同一 token、flock lease、写前查坏行 |
| 6 | 本机对拍被来源闸门判 INVALID | 属实（`GL_NODE_RE=^gl\d{4}$`，无开关） | R7：`--expect-host sled-vail` |
| 7 | MemER 首次空键帧必崩、回退必崩 | 属实（`merge_key_frame_paths` 无条件调用访问 `nums[0]`；`self.subgoals` 永远为空） | **待用户裁决**（见下） |
| 8 | 原侧删官方视频、trace 缺 attempt 与帧计数 | 属实（`keep_official` 未传；两处 `rmtree`；identity 无 attempt；end 无 C8 计数） | R2：`keep_official=True` + provenance + attempt + 三分计数 |
| 9 | 无帧 error 全 PASS；a1／a2 争名 | 前半属实（已裁决具名例外，`no_frame_error` 不设上限）；争名驳回（目录带 attempt，发布步按计划只发 accepted） | R7：发布索引含 accepted_attempt_id；无帧口径**待用户裁决** |
| 10 | NPZ 覆盖写；rsync 合并索引不符；缺观测步；Astra 多落一行 | 前三项属实；Astra 驳回（入口现无 cap 守卫） | R6：唯一收尾者合并写；R5：守卫置于计数前 |

分工重拆（采纳）：R3 拆为 R3（入口／预算／服务）、R6（trace／数值）、R7（媒体／报告／比较器）；测试文件逐个定归属（二节分配表）；主会话在 R1 合入后先冻结共享接口再派功能写入；worktree 内第三方源码一律用 `SGEVAL_THIRD_PARTY` 指向已核 gitlink 的洁净检出，不取脏 `third_party/SimpleMemVLA`。

**用户裁决（2026-10-06「345同意 4可以接续 2报告」）**：第 2 项保留例外、报告单列（R7 三个检查器统一口径，判定行与成绩表单列 `no_frame_error`）；第 3 项批准下载（红线 5）；第 4 项允许接续（`expired_cap=50`、每身份 1 次、计入 870）；第 5 项预算 870 已授权。第 1 项用户 2026-10-06「同意兼容层」，方案见八.3「MemER 兼容层」。原五项如下留档：
1. MemER 已知缺陷：坚持官方原文（首局可能崩、记 error、媒体验收不过），或加两侧一致的兼容层（空键帧不合并、坏 JSON 取上一次合法子目标、没有则具名错误），记录实现指纹、不改 gitlink、不再称逐字原文。主会话推荐兼容层。
2. 真实模型 error 局的交付口径：保留无帧 error 具名例外并在报告单列数量（推荐），或加硬闸门要求每组视频数等于 86。
3. MemER adapter 获取：来源 HF `Yinpei/vlm_subgoal_predictor` 的 `memer/grounded_subgoal/checkpoint-1300`，先只读核 40 位 revision、文件数、字节数、SHA 与缓存缺口，再提交获取清单；落本机 `artifacts/sg-eval/ckpt/` 并同步 NFS；是否批准下载。
4. 占位 job 到期后的恢复：保持 `expired_cap=0`（到期停、报告），或允许有限次到期接续并计入 870。
5. 本轮预算 870 的一口气授权（数字已确认，授权未给）。
