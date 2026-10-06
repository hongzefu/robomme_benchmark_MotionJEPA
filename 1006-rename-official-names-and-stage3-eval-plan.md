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
| 展示名 Astra | 3-tier Astra（用户 2026-10-06 裁决） | `astra` 不变：文件名 `run_astra.sh`／`astra_hard_runner.py`、策略标签、预算账本键、route、对比工具的 mode 都不动，只改展示名 | `astra` |

**改什么、不改什么**：

| 类别 | 做法 |
|---|---|
| 改：活代码与测试 | 约 91 个文件、900 处。文件名（`mme_client.py`→拟 `framesamp_modul_client.py`、`mmesg_client.py`→`groundsg_client.py`、`orig_observer/mme_*`、`run_orig_mme.sh`、`orig-mme-client-env/`、`test_mme_transport.py`）、CLI 参数（`--mme-variant`→`--groundsg-variant`、`--mme-ckpt`、`--mmesg-ckpt`、`--episode-wall-mme`）、环境变量（`MME_PY`、`MME_CKPT`、`MMESG_CKPT`、`MME_VARIANT`）、策略标签 `mme`／`mmesg`、测试名与契约条目 |
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
| GroundSG+Oracle | `mmesg_client.py`（改名后 `groundsg_client.py`） | 缺，同上 | 缺，服务固定 `--seed=7`；官方 `Args.model_seed` 默认 42 没显式设 | — |
| GroundSG+QwenVL | 同上 | 缺，同上 | 缺，同上，另要在 QwenVL 预测器构造前设种子 | — |
| MemER | **未接入** | 缺 | 缺 | 见下面展开 |
| 3-tier Astra（代码 ID `astra`） | 独立 `run_astra.sh`／`astra_hard_runner.py`，不走共享席位 | 缺，入口自己钉 1600 | 缺，服务固定 42 | 云端 API 无 seed 接口，不伪造；费用与两局守卫不动 |

**共同要补的三件事**：
- **1800 步**：席位脚本 `run_seat.sh::step_cap_pairing` 配对改 `test-hard ↔ 1800`、`strict_cap=1`，沿 `SeatRunner → EnvSession.step_cap → 客户端循环 → 结果／trace／报告` 全程传；第 1801 次 `step` 在进真实环境前被拒，第 1800 步成功仍记 success；Astra 在它自己的入口同改；`test-hard0 ↔ 1300` 与生成规格 `EXEC_CAP=1600` 不动。判据 `EVAL_CAP=PASS models=7 max_steps=1800 rejected_step=1801`。
- **模型 seed**：新增 `--policy-seed <int>`，从任务配置传到服务、客户端、子目标预测器，在模型构造前设该路线真正用的随机状态；结果行、trace、媒体 provenance 都记 `policy_seed`；每个 `(模型, policy_seed)` 独立输出目录与账本 route。七路线各在 CPU 夹具上验 0／7／42；判据 `POLICY_SEEDS=PASS models=7 seeds=0,7,42`。本版真实运行只传 7。
- **视频布局（用户 2026-10-06 选定「照上游 mme-vla」）**：现状是 `<模型标签>/<dataset>/new/<task>_<tier>_<环境seed>.a<attempt>/official/official-rerender__<task>_ep<源局>a<尝试>_<终态>_<task_goal>_<tier>.mp4`，没有模型 seed 层。改为每个运行根下按上游 `eval.py` 的层级发布一份：`<run 根>/<模型 ID>/seed<policy_seed>/[oracle｜qwenvl｜memer/]videos/<task>_ep<N>_<success｜fail｜timeout>_<task_goal>_<tier>.mp4`——GroundSG 三个变体多一层子目标目录（与官方同）；`ep<N>` 用局号（V9 用 builder 局号，hard0 用官方源局号），只发布账本接受的那一次 attempt，不带 `a<尝试>`；终态只允许三态，strict-cap 命中必须命名 `timeout`（旧口径超时局文件名带 `error`，本版不允许）；末尾用 tier（`xhard0`～`xhard5`）替官方的 difficulty；文件名超 255 字节沿用截断加哈希、完整名写 `render.json`。局目录里的 trace、arrays、`episode.mp4` 位置不动，只多一步「发布到上游布局」并出索引。MemER hard0 对拍的原侧由官方代码自己写出 `<save_dir>/symbolic-grounded-subgoal/ckpt79999/seed7/memer/videos/`，不改。判据 `VIDEO_LAYOUT=PASS model=<m> seed=7 videos=<n> error_named=0`。

### MemER 要改什么（展开）

**官方是怎么跑 MemER 的**（锁定提交 `ecf086c3` 的 `examples/robomme/`）：`scripts/eval.sh` 的 `MODEL_TYPE == MemER` 分支只加两个参数 `--args.use-memer --args.subgoal-type=grounded_subgoal`，动作服务照旧加载 GroundSG 的权重 `symbolic-grounded-subgoal/79999`——所以 MemER 不是新的动作模型，是 GroundSG 换了一个子目标预测器。这个预测器 `subgoal_predictor.py::MemERSubgoalPredictor` 包着 `subgoal_prediction/qwenvl/api_memer.py::Qwen3VLModelMemER`：基座 `Qwen/Qwen3-VL-4B-Instruct` 加一个 LoRA adapter（官方默认路径 `runs/ckpts/vlm_subgoal_predictor/memer/grounded_subgoal/checkpoint-1300`，`flash_attention_2`），每局开始把演示视频帧存进局目录、每一步把当前帧存成 png、每次问子目标时把「历史关键帧 + 最近执行帧」一起送进模型，模型回 JSON（`current_subtask` + `keyframe_positions`），它据此更新关键帧记忆（`merge_key_frame_paths` 合并近邻帧）；每次请求与回复追加写到局目录旁的 `ep<N>_MemER_log.jsonl`；局末 `rmtree` 局目录。

**我们这边现在的状态**：GroundSG 装配 `scripts/eval-official/official_defs.py` 只认两个变体（`VARIANTS = (oracle, qwenvl)`），`PREDICTOR_NAMES` 只摘 Oracle／QwenVL 两个类，`load_groundsg` 只在 QwenVL 变体时才摘 `qwenvl/api.py`，`make_args` 只会置 `use_oracle`／`use_qwenvl`，`assert_one_predictor` 明确把 `use_memer=True` 当错误抛出，`build_predictor` 只给 QwenVL 导入 swift。客户端 `mmesg_client.py::make_policy_context` 先检查变体必须在 `VARIANTS` 里，adapter 只认 `qwenvl_groundSG_adapter_path` 一个键；席位脚本 `run_seat.sh` 的变体配对只放行 `ground-sg-oracle`／`ground-sg-qwenvl`，adapter 只有 `--qwenvl-groundsg-adapter` 一个参数。也就是说现在任何一层都进不去 MemER。

**要改的五处**：

| 处 | 文件与锚点 | 改什么 |
|---|---|---|
| 1 装配 | `official_defs.py::{VARIANTS,PREDICTOR_NAMES,load_groundsg,make_args,assert_one_predictor,build_predictor}` | 加第三个变体 `ground-sg-memer`；`PREDICTOR_NAMES` 加 `MemERSubgoalPredictor`；`load_groundsg` 在该变体下摘 `qwenvl/api_memer.py::Qwen3VLModelMemER` 原文（它和 `api.py` 一样在导入时设 `IMAGE_MAX_TOKEN_NUM` 等三个环境变量，摘取时要一并落实）；`make_args` 置 `use_memer=True`、`subgoal_type="grounded_subgoal"`、`memer_adapter_path`，并显式传 `model_seed`；互斥断言改成「oracle／qwenvl／memer 恰一个为真」；`build_predictor` 对 memer 也设离线运行约束并导入 swift。摘的是官方原文，键帧、历史子目标、请求格式与解析一行不改 |
| 2 客户端 | `mmesg_client.py`（改名后 `groundsg_client.py`）`::{make_policy_context,qwen_begin,qwen_end,run_episode}` | 变体检查放行 memer；adapter 多认一个 `memer_adapter_path` 键；`qwen_begin`／`qwen_end` 现在只管 QwenVL 的 `qwen-tmp` 局目录，要让 MemER 的局目录与旁边的 `ep*_MemER_log.jsonl` 一样被指到 `<trace_dir>` 下的临时目录、局末归档到该局 trace 目录、异常退出也清理；结果行 `policy_variant` 记 memer |
| 3 席位脚本 | `run_seat.sh::{variant_pairing,build_server_cmd,start_client}`、`run_eval_gl.sh` 参数转发 | 变体配对放行 `ground-sg-memer`，新增 `--memer-adapter <dir>`（给了变体不给 adapter、或 adapter 目录不存在即 `RUN_BLOCKED`）；动作服务命令与 GroundSG 相同（同一份 `symbolic-grounded-subgoal/79999`，同一个 `--policy-seed`） |
| 4 资产 | 资产清单与 `ASSETS` 前置核验 | adapter `checkpoint-1300` 按文件名在本机 `artifacts/` 与 NFS 下初查没有找到（只找到源码，没有权重），实施前要先定来源、落点、文件数、字节数与 SHA256，纳入起跑前核验；不得拿 QwenVL 的 `checkpoint-1200` 顶替；大下载先问落点 |
| 5 依赖与验证 | `scripts/eval-official/client-env/{pyproject.toml,uv.lock}`（仅确有缺口时）；`tests/pipeline/evalx/groundsg/` | 现有客户端锁已含 ms-swift／transformers／peft，优先复用；CPU 夹具用假 `PtEngine` 验三预测器互斥、adapter 误配、键帧合并、日志序列化、空键帧与首个坏 JSON、异常清理；然后 GL 上 1 局真实 smoke（真 adapter + `flash_attention_2` 加载尚未验过） |

判据：`MEMER_WIRING=PASS predictor=MemERSubgoalPredictor`、`ASSETS=PASS`、`MEMER_SMOKE=PASS`。已知上游隐患：`merge_key_frame_paths` 在空列表上可能访问首项、首个坏 JSON 的回退可能访问空 subgoals——CPU 先复现，真阻塞时列出上游文件与候选修法交用户裁决，不私改锁定来源。

## 三、这一版跑什么

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
| 跑哪四个 | FrameSamp+Modulation、SimpleMemVLA、PonderPounce、MemER |
| 数据与档位 | V9 `test-hard` 第三档，43 格 = 14 任务 × 2 档（xhard1/2）+ 7 任务 × 1 档（xhard3）+ 6 任务 × 1 档（xhard4）+ 2 任务 × 1 档（xhard5） |
| 每模型局数 | 1 模型种子（7）× 43 格 × 2 局 = 86 局（环境每格仍取前两局，环境 seed／spec 不动） |
| 合计 | 4 模型 × 86 = 344 局；8 片 × 43 局；4 个占位 job（63188714／15／16／19，可用性以恢复时为准） |
| 最后再跑：MemER hard0 对拍 | `test-hard0`，1300 步，两侧同一批 16 任务 × 1 档 × 12 局 = 192 局（沿用上一轮第二档的局清单）；原侧 = 官方 `eval.py` 的 MemER 分支经我们的 `official_hard_runner.py` 驱动（与 GroundSG 原侧同一套驱动），新侧 = 我们的 `groundsg_client.py` 走 `ground-sg-memer`；两侧动作服务都 `--policy-seed 7`、同一份 adapter；两侧各 8 片 × 24 局；产出差异报告 `GATE2=INFO`，不证明等价 |
| 占位 job 单卡 | 每席 1 张 A40，与上一轮相同。MemER 与 GroundSG+QwenVL 一样「动作服务 + 4B 预测器同卡」：服务取 `SEAT_XLA_MEM_FRACTION=0.65`，Qwen3-VL-4B + LoRA 用剩余显存（上一轮 QwenVL 实跑通过）；MemER 每次请求多带关键帧，激活显存略大，1 局 smoke 时核实。单卡不影响可行性，只影响吞吐（8 片排 4 席）|
| 运行参数 | `--max-steps 1800 --strict-cap --policy-seed 7`；MemER 另加 `--groundsg-variant ground-sg-memer --memer-adapter <已核实路径>` |
| run_name | 拟 `sg-eval-gl-20261006-03`，执行副本拟 `robomme_benchmark-sgeval3`，起跑前确认未用 |

**用户原话（2026-10-06）**：「还需要实现MemER和seed0/7/42，1800步的调整」；「seed只作为实现的功能」「这版还是跑自己的七，还是每一个难度跑两个」；「给出现在所有支持模型的清单，都要支持1800步，都要支持不同seed，模型seed」「我们现在实跑只跑我说的这些模型」。

**预算**：

| 项目 | 轨迹上限 | reset 口径 |
|---|---|---|
| 正式首试 | 4 模型 × 1 种子 × 43 格 × 2 局 = 344 | 每片硬额度 2 × 43 + 20 = 106，8 片共 848 |
| 最小 smoke | 4 模型 × 1 局 = 4 | 每局 3，共 12 |
| MemER hard0 对拍（最后） | 2 侧 × 16 任务 × 1 档 × 12 局 = 384 | 两侧各 8 片，每片硬额度 2 × 24 + 20 = 68，16 片共 1088 |
| 对拍前两侧各 1 局 smoke | 2 | 每局 3，共 6 |
| 基础设施重试 | 全阶段共享 ≤ 50，每身份 ≤ 1 次；到期重试 0 | 消耗上面的既有额度 |
| **合计** | **344 + 4 + 384 + 2 + 50 = 784**（历史累计 2064 + 784 = 2848，在 6366 内） | **860 + 1088 + 6 = 1954** |

**耗时**：改名约 2～2.5 小时；三个老模型按旧第二档单局耗时 × 1.5 × 1.125 粗估共约 459 席位分钟；MemER 无实测，等它 1 局 smoke 后再估整体，原「5～6 小时」结论作废。

**验收**：

| 查什么 | 判定行 |
|---|---|
| 改名只改名 | `OFFICIAL_NAMES=PASS`、`CLIENT_REPLAY_EQ=PASS`（三条旧路线） |
| MemER 真接入与资产 | `MEMER_WIRING=PASS predictor=MemERSubgoalPredictor`、`ASSETS=PASS`、`MEMER_SMOKE=PASS` |
| 七路线种子与 cap（CPU） | `POLICY_SEEDS=PASS models=7 seeds=0,7,42 cases=21 cpu_only=1`、`EVAL_CAP=PASS models=7 dataset=test-hard max_steps=1800 rejected_step=1801` |
| 规格与上游未动 | `DELIVERY_UNCHANGED=PASS`、`UPSTREAM_GUARD=PASS` |
| 每组结果与视频 | 每组 `EVAL_COVERAGE=PASS expected=86 missing=0`、`EVAL_VIDEOS=PASS videos=86`、`OFFICIAL_MEDIA=PASS total=86 fail=0`、`VIDEO_LAYOUT=PASS model=<m> seed=7 videos=86 error_named=0`（上游 mme-vla 布局，三态命名） |
| 完整矩阵与预算 | `RUN_POLICY_SEED=PASS seed=7 combinations=4`、`STAGE3_MATRIX=PASS policy_seed=7 combinations=4 unique_terminal=344`、`BUDGET_ENFORCEMENT=PASS` |
| MemER hard0 对拍（最后） | 两侧各 `EVAL_COVERAGE=PASS expected=192 missing=0`、`OFFICIAL_MEDIA=PASS total=192 fail=0`；`GATE2_INPUTS=PASS expected=192 missing=0 extra=0`、`GATE2_PROVENANCE=PASS local_rows=0`、`GATE2=INFO compared=192 …`（两侧成功率、终态相同数、翻转数、McNemar p、逐步一致数） |

成绩只报 seed 7 的逐格／任务／档位与总成功率，每格 n=2；与旧 1600 步成绩的差异注明条件已变，不宣称等价。

**步骤**：

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 等用户再次说「开工」；核对预算、MemER 资产边界、新 run_name | 授权记录与 BASE 明确 |
| 1 | R1 改名；主会话改现行文档与旧名对照表 | `OFFICIAL_NAMES`、`CLIENT_REPLAY_EQ`、核心短测 |
| 2 | R2 接 MemER，R3／R5 让七路线支持种子与 1800，R4 补 CPU 测试 | `MEMER_WIRING`、`POLICY_SEEDS`、`EVAL_CAP`、`DELIVERY_UNCHANGED` |
| 3 | 核资产、冻结执行副本、生成清单与四个 seed 7 任务组、每模型 1 局 smoke | `RUN_INPUTS`、`ASSETS`、`MEMER_SMOKE`、`RUN_POLICY_SEED` |
| 4 | GL A40 跑 8 片 | 退出码、进度、预算 |
| 5 | 四组验收、汇总 | `EVAL_COVERAGE`、`EVAL_VIDEOS`、`OFFICIAL_MEDIA`、`STAGE3_MATRIX` |
| 6 | 最后：MemER hard0 对拍——两侧各 1 局 smoke 后，原侧 8 片 + 新侧 8 片进 4 席，跑对比工具 | `GATE2_INPUTS`、`GATE2_PROVENANCE`、`GATE2=INFO compared=192` |
| 7 | 留档、commit、push；资源按最新指令处置 | `BUDGET_ENFORCEMENT`、`result.md` 落盘 |

**子代理分工与合并（简述）**：R1 改名先单独做完、审两次、合入；之后同一时刻派 R2（MemER 装配：`official_defs.py`、GroundSG 新侧客户端与原侧驱动 `official_hard_runner.py`／`run_official_hard.sh`）、R3（共享入口：席位脚本、`env_client.py`、各服务端、报告与预算）、R5（Astra 两入口及其测试），R4 并行准备与 R5 不重叠的 CPU 测试。各管互不重叠的文件、各在自己的 worktree 写；合回顺序 R1 → R2 → R3 → R5 → R4，每合一个审禁触路径与定向测试，全部过后冻结执行提交。主会话自做现行文档、资产清单与 GL 编排。

改名范围明细、种子与 cap 的逐层传递、链路图、各档任务名单、耗时推导与预算细则见第二部分八节。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

1. 仅规划，保持暂停。seed0／7／42只实现功能，本版只跑seed7、每格两局；MemER `test-hard0` 原侧 vs 新侧对拍（192 + 192）排在四模型 V9 之后最后跑，同样待运行授权；旧审批不能自动扩展到新增MemER路线或额外真实运行。
2. `src/robomme/**`、录像器、三方源码和 gitlink 不改、不覆盖；`third_party/SimpleMemVLA` 在途内容不纳入本轮。
3. 不改生成 `EXEC_CAP=1600`、交付 spec／manifest；不增加 reset 对拍或 rollout 采样。实际模型评估按第一部分第三节与本部分八节的完整预算累计。
4. 所有 Python／测试通过 uv，显式设置 `UV_CACHE_DIR`；NFS 配置 `UV_LINK_MODE=copy`，计算节点 `uv run --frozen --no-sync`，不现场装包。新增正式依赖只落独立客户端子项目及其 lock。
5. MemER 缺资产先报告来源与缺口；大下载须另获落点／规模授权。真实加载失败不降级成 QwenVL 或其他预测器。

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
| `scripts/eval-official/run_astra.sh`、`astra_hard_runner.py::{DATASET_STEP_PAIRING,check_pairing,TracedEnv,run_one,build_parser}` | Astra独立路线cap1800／模型seed转发、真实调用前守卫、结果／trace记录 | 本版仅CPU／零外联验收；费用、两局硬守卫与test-hard0口径不变 |
| `scripts/eval-official/budget_ledger.py` 与 `env_client.py`／任务编排的预算构造 | 本轮cap784、infra50、expired0在每个消费者一致读取 | 历史默认不改；本轮实际守卫与报告同口径 |
| `scripts/eval-official/client-env/{pyproject.toml,uv.lock}`（仅确有依赖缺口时） | 真实 MemER 所需依赖声明与锁 | 优先复用现锁，根环境不动，不临时 pip 补正式依赖 |
| `tests/pipeline/eval/`、`tests/pipeline/evalx/{groundsg,astra,report}/` 的下表明确测试及契约登记 | 七路线接线、MemER装配／异常、seed反查、cap边界、恢复／媒体串组反例 | 纯CPU，不加载权重、不开外网、不做真实reset |
| `AGENTS.md`／`CLAUDE.md` 项目段、`readme.md`、`scripts/README.md`、`tests/README.md`、`docs/validation/legacy-names.md` | 主会话更新现行术语与对照 | 标记块及历史档案不改；本轮当前只写用户指定计划 |

表中新增 flag 与字段是拟新增接口，不是当前可运行参数；`eval_report.py --cap 1800` 为已有接口。

## 二、子代理分配表

派发前核对实施 BASE、主检出与各 worktree 状态；子模块在途改动绕开，执行副本必须另建且 clean。主会话负责暂存、提交、推送及资源操作。测试／契约文件先逐项落实归属，不能靠通配集合让两代理同时写同一文件。

| 子任务 | 目标／可写文件集合 | 禁触路径 | 接口契约与依赖／整合顺序 | 验收命令与判定行（工作副本 CPU） | 资源／共享文件裁决 |
|---|---|---|---|---|---|
| R1 | 本部分八节改名范围的 `scripts/**`、`src/robomme_hard/**`、`tests/**`；现有子项目 lock 仅改项目名 | `src/robomme/**`、`third_party/**`、`docs/**`、规则文档、根依赖；不新增顶层入口 | 先完成改名及别名表，之后才派写入 R2／R3；顺序1 | 核心短测、命名残留检查、`CLIENT_REPLAY_EQ`、`TEST_INVENTORY` | GPU=0；独立worktree；R1完成前他人不写该集合 |
| R2 | `official_defs.py`、改名后 `groundsg_client.py`、原侧驱动 `official_hard_runner.py`／`run_official_hard.sh`、客户端子项目两依赖文件（必要时） | 上游源码、运行入口、其他客户端／报告／测试／文档 | MemER变体、adapter、预测器seed及日志接口交给R3；顺序2 | `uv run --no-sync python -m pytest tests/pipeline/evalx/groundsg -q`；`MEMER_WIRING` | GPU=0、端口=无；独立worktree；R2独占这三个对象 |
| R3 | `run_seat.sh`、`run_eval_gl.sh`、`env_client.py`、`smvla_server.py`、`pp_server_wrap.py`、`trace_writer.py`、`eval_report.py`、`model_eval_report.py`、`official_media_check.py`、`render_official_video.py`、`video_check.py`、`budget_ledger.py` | R2／R5集合、三方源码、生成规格、测试／文档 | 按R2接口转seed／adapter，cap1800／逐组输出／预算配置；顺序3 | `uv run --no-sync python -m pytest tests/pipeline/eval tests/pipeline/evalx/report -q`；`POLICY_SEEDS`、`EVAL_CAP` | GPU=0；独立worktree；共享运行入口／trace／身份归R3 |
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
2. 先登记完整预算、新run_name、四个席位与资源处置口径；实际预算统一trajectory784／infra50／expired0，不沿旧默认重试。再核本版四模型资产与客户端依赖实际指向，`RUN_INPUTS`、`ASSETS`失败即停；`SMVLA_PY`／`PP_PY`／FrameSamp解释器及MemER客户端须实际核实。不为本版不跑模型新增下载、GPUsmoke或付费调用。
3. 清单参考 `docs/validation/sg-eval-gl-20261006-02/records/scripts/gl-scripts_build_manifests.py.txt`，从 `_v9_cells` 各格按局号升序取前2局，连交付spec逐项校验：共86个唯一环境身份。四模型seed7复用同一manifest指纹；每模型两片、43局／片。每模型先过其seed7单局最小smoke再启动该路线正式评估；失败停止受影响路线，不额外重跑来挑成功局，不跑seed0／42的smoke。
4. 新根 `R3=$N/sgeval-<确认日期>-03`，四组 `$R3/<模型>/seed7/` 下分别放stage／trace／media／report。全部任务明确指定 `--dataset test-hard --max-steps 1800 --strict-cap --policy-seed 7`；MemER另指定新 `--groundsg-variant ground-sg-memer --memer-adapter <已核实路径>`，实际flag以R1／R3整合后接口为准。任务配置守卫拒绝本版seed0／42运行。
5. 8片入队，仍最多4席，不增加占位job数量；沿原顺序 SimpleMemVLA → PonderPounce → FrameSamp+Modulation，再加入MemER，组内按固定分片／清单顺序运行。每席一次只起一个任务，服务起前探端口，记实际端口、节点、server_epoch、服务argv与种子，健康检查和首推分别验收；srun使用 `--gpu_cmode=shared`。共享预算 `$R3/budget-ledger.jsonl` 的route含模型和模型seed7，任务独立attempt账本记录 `accepted_attempt_id`；各片 `--reset-budget 106`，共享infra上限50，每身份重试最多1次。
6. 登录节点tmux会话前缀 `p3-`，smoke前缀 `p3-smoke-`；完整名、JobID与日志路径写launch.md。日志三件套与 `EXIT_CODE=` 尾行必须保留，监听完成／异常／无进展，不因tmux启动成功承诺代理会自动唤醒。
7. 每模型seed7单独运行报告和媒体验收（已有报告参数 `--cap 1800 --expect-total 86`），另按八.7 布局发布视频并核 `VIDEO_LAYOUT`（strict-cap 局文件名必须 `timeout`），校验权威身份集合、真实1800上限、视频唯一性／完整解码与来源；官方自产视频与重绘互斥，原始帧按现行验收后清理规则保留。4组各过覆盖、视频与官方媒体闸门后才汇总344局。
8. **最后跑 MemER hard0 对拍**：四模型 V9 全部验收通过后才起。局清单沿用上一轮第二档 `test-hard0` 的 16 任务 × 12 局 = 192（`$I/qwenvl/gate2/` 同式清单，重新生成并核指纹）；两侧各先 1 局 smoke（原侧经 `run_official_hard.sh --dataset test-hard0 --max-steps 1300 --variant ground-sg-memer --memer-adapter <路径>`，新侧经 `run_seat.sh` 同参数），再原侧 8 片 + 新侧 8 片进同样 4 席，`SEAT_XLA_MEM_FRACTION=0.65`、`--episode-wall 3600` 沿 QwenVL 口径；两侧都 `--policy-seed 7`。跑完用上一轮的对比工具（1005 计划 S6）出 `GATE2_INPUTS`／`GATE2_PROVENANCE`／`GATE2=INFO compared=192`，两侧 `OFFICIAL_MEDIA` 各过。是差异报告，不证明等价。
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
| 正式首试 | `4 模型 × 1 模型种子（7）×（14 任务 × 2 档 × 2 局 + 7 任务 × 1 档 × 2 局 + 6 任务 × 1 档 × 2 局 + 2 任务 × 1 档 × 2 局）=344` | 正常链每 attempt 的 build 1 次 + reset 1 次，基线 `344×2=688`；8 片沿用每片 `2×43+20=106` 硬额度，共848，已含重试余量，不再额外加重试reset |
| 最小 smoke | `4 模型 × 1 模型种子（7）× 1 任务 × 1 档 × 1 局=4`；逐模型先做单局最小验证，不跑seed0／42 | 每局额度3，共12；正常调用 `4×2=8`。不额外做cap实跑探针，用CPU环境调用计数夹具验证 |
| 基础设施重试 | 全阶段共享最多 50 次，且每 `(模型,policy_seed,环境身份)` 最多 1 次 | 消耗上述分片／smoke 既有 reset 额度，双侧任一额度不足即停；任务正常失败或 timeout 不重试 |
| 到期重试 | 本轮0次 | 不继承旧账本默认500次到期重试；占位到期停任务并报告，追加恢复预算另定 |
| MemER hard0 对拍（最后跑） | `2 侧 × 16 任务 × 1 档 × 12 局 = 384` | 两侧各 8 片，每片 `2×24+20=68` 硬额度，16 片共 1088；正常基线 `384×2=768` |
| 对拍 smoke | `2 侧 × 1 局 = 2` | 每局额度 3，共 6；正常 `2×2=4` |
| **本轮合计上限** | **`344+4+384+2+50=784`** | **各 runner reset 硬额度合计 `848+12+1088+6=1954`；正常首试基线 `688+8+768+4=1468`** |

CPU 回放／夹具消耗真实 reset／轨迹均为 0。新预算账本同时保留旧消耗的只读快照，以「旧消耗 + 本轮消耗」核对此前总授权；新根目录不能重置整项工作的累计计数。`budget_ledger.py` 的全局 reset 软阈值不等于硬拦截；本轮硬边界来自每个 runner 启动前明确的 reset 额度，禁止追加 runner 绕过总和。上述是拟申请的完整新增上限，实际重试亦受共享 50 次限制。

所有实际领取消费者统一注入本轮 `trajectory_cap=784, shared_infra_cap=50, expired_cap=0`，不能只在收尾报告写上限；若沿历史累计账本则轨迹上限为 `2064+784=2848`，相对原6366余额3518。历史 `open=8` 已包含在2064，不能再次扣除或擅自释放。单smoke额度3不足两次完整attempt的4次领取，每片额外20仅够该片10次完整重试；50是全局上限，不保证任意分布的50次重试均能完成，局部额度耗尽直接停止。

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
