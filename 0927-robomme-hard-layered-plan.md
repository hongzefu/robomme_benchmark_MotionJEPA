# 0927 方案：`robomme_hard` 分层继承双包 · 两阶段生成 · 单一 jsonl（只规划不实施）

> **权威性**：本文件是 [`0926-robomme-hard-split-plan.md`](0926-robomme-hard-split-plan.md) §〇′ 的精简定稿版，只写最新口径；两份冲突时以本文件为准。只规划，不实施；每一阶段须单独获批后才动手。
> **修订（2026-09-27 夜）**：吸收同日两份审计——Claude 对抗审查（7 维度 opus 审查、逐条 sonnet 反驳，91 条确认 87 条）与 Codex 审计（另派 3 个 sonnet 逐条核实）——以及用户四项裁决（§一 U-1～U-4）。两份审计锚点均为 `55f1b027`（12.204.10）。
> **代码锚点**：本仓库 `newtaskRelease-v5` @ `55f1b02776b55daaa39c20131d0ac0fa98f67b5c`（`66d9a424` 至此只有文档改动）。官方两个锚点分开钉（审计确认 `1fadc0ec` 里没有 `scripts/data-generation/`）：
> - **官方环境源码** `src_commit` = `RoboMME/robomme_benchmark` `main` @ `1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9`（tree `3006988f…`）；
> - **官方生成编排** `orchestration_commit` = `dataset-gen` @ `d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`（tree `1d4c1369…`，即隔离树 `artifacts/train-parity/local-smoke-01/official-src/` 的 `.official_tree`，也是 `scripts/parity/train_split_parity.py` 的 `DEFAULT_SOURCE_REF`）。两者 `src/robomme` 零 diff（阶段 0 留证）。
>
> 现行规格 `scripts/configs/newtask-v6/v6-02/<tier>/specs.jsonl`（四档 550 行、selected 165 行，其中 2 行不是实际交付局，见 §5.3）；S4 交付清单 `artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json`（`successes` 165 条，逐局记 h5 sha256／字节数／路径，`code_baseline=ca32e9b`）。
> **工作副本**：`/data/hongzefu/robomme_benchmark_MotionJEPANewTask`（环境 A，sled-vail）。
> **对拍硬件**：四个 A40 @ greatlakes `spgpu` 占位 job，三侧统一在 A40 上生成；本机 RTX 6000 Ada 只做开发冒烟。按用户裁决 U-1，对拍判定是「行为一致」而不是「字节一致」（理由见 §5.4）。占位 job（用户 2026-09-27「这四个你可以自由跑」「就用现有的占位job」，不新交）：`62126060` gl1517、`62126061` gl1504、`62126062` gl1506（`hs-hold-20260927-1/2/3`）、`62018665` gl1510（本方案不使用）。阶段 4 结束后按 U-7 释放 `62126060`、`62126061`、`62018665`，保留 `62126062`。JobID、驱动、剩余时长都是写作时的快照，阶段 4 起跑前重新核实。
> **第三次修订（2026-09-28，用户裁决 U-13～U-20，§一）**：记录点跨硬件浮点漂移按方案甲处理（回注点零差、记录点 ≤ 1e-5）；预算表一次性批准；阶段不再逐个放行、等用户「开工」后连续执行；xhard1 40 局带外告警照收；阶段 4 用 NFS 新 clone；网站与交付清单维持 165 局；对拍参考层升级为可配置容差层（动作／状态／图像／帧数四阈值，O:P 标定后经用户确认）；Codex 审计（锚点 `6608e38b`）12 条全部吸收，落点见第二部分 §七。
> **第二次修订（2026-09-27 深夜，用户六项追加裁决 U-5～U-10，§一）**：`test-hard` 每格从 3 局改为 **20 局**，规格从上次 SimpleMemVLA 评估用的 `smvla-0927`／`smvla-0927-fill` 快照迁移（不重新抽签，55 格全部有 h5）；评估步数上限沿用按档 1500/1700/2000/2600；新增阶段 6～8：两个策略仓库（官方 MME-VLA、官方 SimpleMemVLA）从官方切分支做最小改动，在 GL 10 × A40 上先各评 55 格 × 10 局、再评余下 10 局；阶段 4 结束后释放占位 job 只保留 `62126062`；20 局 h5（1.2 TB）先不进 bucket。用卡表见 §7.1。
> **评估接口**（用户 2026-09-27「dataset传入test-hard内部再分xhard1234」「只保留着一个接口哦」）：对外只新增 `dataset="test-hard"` 一个取值；builder 内部把 xhard1～xhard4 串成每任务 **80 局**（xhard4-only 的 `StopCube`、`InsertPeg`、`MoveCube` 为 20 局），每档局数由 jsonl header 的 `delivery_per_cell=20` 决定。`xhard1`～`xhard4` 不是合法 `dataset` 值。步数上限按档：`TIER_MAX_STEPS = {xhard1: 1500, xhard2: 1700, xhard3: 2000, xhard4: 2600}`（U-6），由调用方逐局传 `make_env_for_episode(ep, max_steps=…)`。
> **三侧**：O 侧官方（编排 `d53f21a7` + 环境源码 `1fadc0ec`）；P 侧本仓库 tag `pre-hard-split` → `7c7118fa`（生产代码基线 `ca32e9b`，两者 `src/` 零 diff）；H 侧拆包后 HEAD。持久化 bucket：`HongzeFu/robomme-hard-parity`。
> **计数体例（P5）**：原三档 = 16 任务 × 3 档（easy/medium/hard）× 3 局 = 144；S4 xhard 对拍集 = xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165（xhard1～3 缺 `require_xhard4_only` 的 `StopCube`、`InsertPeg`、`MoveCube`）；**`test-hard` 交付集 = xhard1/2/3 各 13 任务 × 20 局 + xhard4 16 任务 × 20 局 = 1100**；评估每轮每策略 = 55 格 × 10 局 = 550。
> **评估硬件**：GL 10 × A40，新交 10 个 48 h 占位 job（各 1 GPU / 1 CPU / 32 G，用户 2026-09-27「eval使用10卡并行 greatlake hold 48h 跑完eval的卡全关掉」）；只能在阶段 4 释放 3 个 192 G 占位 job 之后提交（chaijy2 内存配额 960 G，写作时已用 800 G，见 §7.1）。
> **commit 体例**：`<大>.<小>[.<修订>] <中文描述>`，实施从 12.205 起，预计到 12.213。
> **外部依赖**：`uv.lock` / `pyproject.toml` 的依赖不变，唯一改动是 wheel `packages` 增加 `src/robomme_hard`。bucket 操作用 sled-vail 上的一次性工具环境 `uvx --from huggingface_hub==1.8.0 hf …`，因为锁定的 `huggingface_hub` 1.4.1 没有 bucket API；不进项目依赖。
> **已完成、不再赘述**：V6 四档生成与 S0～S5 验收、审查修复、拆包阶段 0b 瘦身（12.200～12.203）。

---

# 第一部分（给人看）

## 一、总览

**一句话方案**：
- **双包并列**：`src/robomme/` 逐字节等于官方 `1fadc0ec`；`src/robomme_hard/` 只放差异。
- **复制、借用、子类化三种做法**：
  - 复制：16 个环境类，以及「改过、新增，或传递依赖改过模块」的 utils 与 wrapper；
  - 借用：依赖闭包干净的官方模块，用 shim 指过去；
  - 子类化：`BenchmarkEnvBuilder`，整段覆写构造环境的路径。
- **规格随包分发**：四档规格放在包内 `env_metadata/test-hard/xhardN/specs.jsonl`，每格 20 局，从上次 SimpleMemVLA 评估用的 `smvla-0927`／`smvla-0927-fill` 快照与其 `rollout/run1/results.jsonl` 迁移，逐局回填 h5 结果；不重新抽签（U-5、R16）。
- **生成链路两阶段**，放在 `scripts/injection-dev/`：第一阶段只落一份 jsonl；第二阶段只读这份 jsonl 生成 h5，按明确的状态机回写。
- **评估侧**：`BenchmarkEnvBuilder(env_id, dataset="test-hard")` 自己读包内 jsonl，包装链与官方 `test` 完全相同；评估步数上限按档 `TIER_MAX_STEPS`（1500/1700/2000/2600，U-6），逐局传给 `make_env_for_episode`。
- **评估阶段（阶段 6～8）**：官方 MME-VLA（`perceptual-framesamp-modul` 79999）与官方 SimpleMemVLA 各从官方 main 切分支做最小改动（§八），GL 10 × A40 并行，先各评 55 格 × 10 局，再评余下 10 局（U-9）。

**用户裁决（2026-09-27 夜，AskUserQuestion 原选项与原话逐字保留）**：

| 编号 | 问题 | 用户选择／原话 | 落到哪 |
|---|---|---|---|
| U-1 | 三侧对拍在 RRT 墙钟非确定性下怎么判 | 「C 维持 16 worker、全部降级」 | §5.4、§6.1 |
| U-2 | test-hard 评估步数上限 | 「test-hard 评估的步数上限 先定死一个上限 按照现在的h5生成结果 加上20%雨量」（已被 U-6 取代，只留历史） | §4.3 |
| U-3 | 阶段 1 的 `override=True` 与 builder 子类覆写属 P2「覆盖」，怎么批准 | 「现在一次批准这两项」 | §3.3、第二部分 R10 |
| U-4 | h5 从 GL 节点落到 /data 与 bucket | 「需要保存h5 ac都可以」→ 取 A：NFS 按片短暂中转（主代理按 memory「取整等细节自己定」选定） | §5.4、第二部分 §3.2 |
| U-5 | `test-hard` 20 局规格怎么来 | 「20局走迁移 问题是现在的20局全都有h5吗」→ 核实：`smvla-0927`＋`smvla-0927-fill` 合并后 55 格每格 selected 且有 h5 的行均 ≥ 20（xhard1 BinFill 17+23、VideoPlaceOrder 15+30、VideoRepick 19+30；xhard4 InsertPeg 14+22，其中 5 条同 seed），上次评估实际用的 1100 个身份全部有 h5 | §5.3、§6.3 |
| U-6 | 评估步数上限 | 「沿用上次按档 1500/1700/2000/2600 以便对比」（取代 U-2 的统一 2658） | §4.3 |
| U-7 | 占位 job 释放 | 「阶段 4 三侧对拍结束后释放gpu 但是保留1个 以供以后使用」→ 保留最新的 `62126062`（主代理选定），释放 `62126060`、`62126061`、`62018665` | §7.1、第二部分 §3.2 |
| U-8 | 两个策略仓库怎么切 | 「MME-VLA 官方基底选干净 main 检出」「MME-VLA 从官方policy learning库切出 再push到https://github.com/hongzefu/robomme_policy_learning_MotionJEPA/这里的一个branch」「branch命名和我之前约定一致」「simplemem也是这样官方切出 push到我要的地方！」；改动清单「同意 写回计划」 | §八 |
| U-9 | 评估顺序 | 「先各做55*10 然后在做10」 | §7.1、第二部分 §3.3 |
| U-10 | 20 局 h5 是否进 bucket | 「1.2 TB 的 20 局 h5 先不进bucket」 | §5.4 |
| U-11 | xhard 对拍与 20 局集的关系 | 主代理提出 B 方案，用户「维持b」：`PARITY_P_H`（xhard）仍重放 S4 的 165 个身份（P 侧同为 A40 产物，是唯一合法的同硬件 xhard 样本）；20 局集靠 `S4_SUBSET`（165 ⊂ 1100，纯 CPU）与评估侧逐局 `spec_binding`（`EVAL_BINDING`）覆盖，另加零算力的参考层 `EVAL_DEMO_FRAMES`（评估记录的演示帧数与旧 h5 逐局比）；不为 1100 局另生成 h5。A 方案（两侧各在 A40 重生成 1100 局、约 1.5 TB、5 小时以上）作废 | §5.4、§6.4 |
| U-13 | 记录点跨硬件浮点漂移 | 「1同意甲 但是计划全解释后报告」→ 方案甲：回注点零差，只记录不回注的观测值允许 1e-5 以内浮点差并单独计数（背景：S4 165 局与上次 1100 局同 seed 的 550 对里 34 对 spec 哈希不同，全在 VideoPlace 两任务的 `actions.return_pose_by_object_id`，最大差 1.19e-7，A40 抽签对 Ada 抽签；同一 Ada 上重复抽 59 对全同） | §5.3、§6.3、§6.4、第二部分 R22 |
| U-14 | 预算一次性授权（P3） | 「2同意」→ 第二部分 §3.1 的表即已批准口径：生成侧 rollout ≤ 635、reset ≤ 712；评估侧名义 2202 局，基础设施重跑硬上限每策略每轮 55 次、合计 220 | 第二部分 §3.1 |
| U-15 | 阶段 0 开工 | 「3现在不开工 统一开工」→ 各阶段不逐个放行，等用户一次说「开工」后按步骤表连续执行；P2 阶段 3 的逐文件批准与对拍 FAIL 裁决仍按规则单独请示 | §七 |
| U-16 | xhard1 40 局演示帧数带外告警 | 「4不管」→ 照收，留档写明数量与清单，不换局 | §5.3、盲区 ⑫ |
| U-17 | 阶段 4 的 GL 克隆脏改动 | 「5新clone」→ 在 NFS 上新 clone `robomme_benchmark-hs-gl` 专供对拍，旧克隆 `robomme_benchmark-newtask-gl` 一律不动 | 第二部分 §3.2 |
| U-18 | 网站与 `final-delivery.json` 是否改 1100 局 | 「6先不纳入」→ 本方案不改网站与交付清单，维持 165 局口径，另立任务 | §3.5 |
| U-19 | 对拍 PASS 的措辞与参考层 | 「7动作、状态、图像数值、帧数要容差可控」→ 判定层措辞改为「输入绑定、结构与任务成功一致」；原参考层升级为**容差层**：动作、状态、图像、帧数四项各有阈值，阈值写在 `scripts/configs/hard-parity-tolerances.json`，默认值由 O↔P 边实测标定后写入并经用户确认，超阈值即 FAIL | §5.4、§6.1、第二部分 R21 |
| U-20 | Codex 审计（锚点 `6608e38b`，12 条） | 用户「参考codex结果」→ 12 条全部吸收，逐条落点见第二部分 §七 | 第二部分 §七 |
| U-12 | SimpleMemVLA 官方切出点 | 2026-09-27 核实：`wadeKeith/SimpleMemVLA` main 已改为迁移提示（`ef72213`，只剩 README），项目迁到 `OpenBMB/SimpleMemVLA`，其 main `c564c17` 以 `9fce41c` 为祖先，之后两个提交（`404215d` 真机实验、`c564c17` robodojo 评测）只改 `assets/` 与 `README.md`，代码零改动。切出点定为 `OpenBMB/SimpleMemVLA@c564c17`（用户「核实simplememvla」后主代理选定，代码与 `9fce41c` 逐字节相同） | §八 |

**已定死口径**：

| 编号 | 口径 | 依据 |
|---|---|---|
| E-1 | 双包、分层继承：环境类，以及改过、新增或**传递依赖改过模块**的 utils／wrapper 一律复制；依赖闭包干净的借用；builder 子类化 | §3.1、§3.2 |
| E-2 | 环境类同 id，副本一律 `@register_env(<id>, override=True)`；包导入末尾断言注册表归属与命名空间归属 | §3.3（U-3 已批准） |
| E-3 | G1 用双锚点（`src_commit`／`orchestration_commit`）＋逐文件 sha256 清单＋守卫脚本＋导入时 cheap 校验；阶段 3 之前守卫输出 `PENDING` | §3.4 |
| E-4 | 生成链路两阶段，全部依赖放 `scripts/injection-dev/`；第一阶段只落一份 jsonl，首次落盘用排他发布 | §5.1 |
| E-5 | jsonl 行分「签」和「结果」两段：`identity_sha256` 只盖签；另设 `delivery_sha256` 盖正式交付集合；`selected` 只表示正式交付局 | §5.3 |
| E-6 | 包内 jsonl 迁移时从 S4 `final-delivery.json` 逐身份回填 `rollout` 与 `candidate`，selected 与实际交付对齐 | §5.3 |
| E-7 | 对外只新增 `dataset="test-hard"`；`scripts/evaluation.py` 原样不动；`evaluation_hard.py` 为第五入口，与它只差 import 行、`dataset`、按档 `max_steps` 逐局传入两处，共 4 行 | §四 |
| E-8 | h5 本体不写任何包指纹；来源、代码指纹、实际加载的环境类模块只进 results、manifest 和 jsonl `rollout` 块 | §3.3、§5.4 |
| E-9 | 官方 `scripts/data-generation` 四文件从 `d53f21a7` vendor 进 `scripts/parity/official/`；runner 显式传元数据根，不依赖官方脚本按 `__file__` 推出来的默认根 | §3.5 |
| E-10 | `tests/` 分三类逐文件处理，判据是可收集，并且残留的 `robomme.robomme_env` 引用清单为空或逐条注明 | 第二部分 R8 |
| E-11 | 预算表按乘式分别列 rollout 与 reset 的总尝试上限，含冒烟、阶段 3 后重跑、基础设施重跑上限、停止条件；实施前向用户一次性申请 | 第二部分 §3.1 |
| E-12 | 四个 Unmask 任务的 train 元数据 400 条放在 `robomme_hard`，builder 覆写元数据路径去读；`robomme` 回到官方 100 条 | §3.1、§4.2 |
| E-13 | 三侧统一在 A40@GL 上生成；原三档 S0 基线在 A40 重新生成，本机 Ada 产的 `artifacts/newtask-v6/v1/base` 不再作判据（用户 2026-09-27「123全部同意」） | §5.4 |
| E-14 | 三侧 O／P／H；对拍矩阵 `O↔P`、`P↔H`、`O↔H`（原三档）与 `P↔H`（xhard，P 侧复用 S4 交付存档） | §5.4 |
| E-15 | h5 全部持久化到 HF bucket `HongzeFu/robomme-hard-parity`，每侧附 `identities.jsonl`、`SHA256SUMS`、`manifest.json`；上传后逐对象读回核对 sha256，同源判定不用 xetHash | §5.4 |
| E-16 | **对拍判定为行为一致（U-1）**：身份集合、setup、结构、任务成功全等才算 PASS；sha 相等数与数值差异只作参考 | §5.4、§6.1 |
| E-17 | 单 GPU 16 worker（`--gpu_cmode=shared`，`OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`），进程池不加 `max_tasks_per_child`；不再做 `WORKER_INVARIANT` 探针 | 第二部分 §3.2 |
| E-18 | 跨硬件只作参考 `XHW_REFERENCE=INFO`，只用现存 Ada 原三档产物对比 A40 的 O 侧，不新增 rollout | §6.2 |
| E-19 | `TIER_MAX_STEPS = {xhard1: 1500, xhard2: 1700, xhard3: 2000, xhard4: 2600}`，与上次评估（benchmark `v4_eval.py::NEWVALUE_MAX_STEPS`、SimpleMemVLA `v6spec_eval.py`）同值，便于对比（U-6，取代 U-2 的 2658） | §4.3 |
| E-20 | `test-hard` 每格 20 局，身份真源是上次评估的 1100 条结果（SimpleMemVLA `aab093f` 留档），规格与 h5 结果从 `smvla-0927`／`smvla-0927-fill` 迁移；S4 的 165 局必须是其子集 | §5.3、§6.3 |
| E-21 | 两个策略仓库都从官方 main 切分支、只改环境入口／步数／分片／子模块四类文件，不改模型与推理代码；分支推到用户指定的两个 fork | §八 |
| E-22 | 评估在 GL 10 × A40，新交 10 个 1 GPU / 1 CPU / 32 G / 48 h 占位 job；先每策略 55 格 × 10 局，再余下 10 局；跑完 10 个评估 job 全部 `scancel`，`62126062` 保留 | §7.1、第二部分 §3.3 |
| E-23 | 20 局 h5（`/data` 上 1.2 TB）先不进 bucket；bucket 仍只放三侧对拍产物 | §5.4 |

## 二、要保证什么

| 保证 | 靠什么 | 判定行 |
|---|---|---|
| G1 `src/robomme/**` 与官方 `1fadc0ec` 逐字节相同 | §3.4 | `UPSTREAM_BYTES=PASS src_commit=1fadc0ec files=<n> diff=0 shims=18` |
| G2 `robomme_hard` 跑原三档，与官方、与修改前**输入绑定、结构与任务成功一致，且动作／状态／图像／帧数差异在标定容差内**（U-19） | 三侧对拍 §5.4 | `PARITY_O_P` / `PARITY_P_H` / `PARITY_O_H` `=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 tol=PASS action_max=<a>/<tol_a> state_max=<s>/<tol_s> image_mad=<i>/<tol_i> frames_max=<f>/<tol_f> sha_equal=<k>`（16 × 3 × 3） |
| G3 `robomme_hard` 跑 xhard，与 S4 交付输入绑定、结构与任务成功一致、差异在容差内；回注通道逐值一致 | §5.4 | `PARITY_P_H=PASS tier=xhard compared=165 … tol=PASS …`（13×3×3 + 16×3）、`HARD_RESET_REPLAY=PASS resets=55 injected_mismatch=0 recorded_drift=<n> max_abs=<d> goal_mismatch=0`（13×3 + 16，从 S4 每格取 candidate 最小的一局，经 `S4_SUBSET` 映射到 20 局集里的同一局） |
| G4 评估接口与 `dataset="test"` 同形，包装链相同，语言目标用的是 hard 版 | §四 | `EVAL_PY_UPSTREAM=PASS ENTRIES=5`、`EVAL_HARD_DIFF=PASS lines=8`、`WRAPPER_CHAIN=PASS action_spaces=4` |
| G8 `test-hard` 20 局集就是上次评估那 1100 局，规格与 h5 逐身份绑定，且包含 S4 165 局；评估评到的正是这 1100 个身份，每局回注点零差 | §5.3、§6.3、§6.4 | `SOURCE_POOL=PASS raw=1717 dedup=89 merged=1628 delivery=1100`、`DELIVERY_SET=PASS compared=1100 equal=1100 cells=55 shape=13x3x20+16x20`、`H5_BINDING=PASS compared=1100 mismatch=0 ambiguous=0`、`S4_SUBSET=PASS s4=165 seed_match=165 spec_exact=154 spec_within_tol=11 max_abs=1.2e-7`、`EVAL_IDENTITY_SET=PASS policy=<名> rounds=2 episodes=1100 missing=0 dup=0`、`EVAL_BINDING=PASS policy=<名> episodes=1100 replay=1100 injected_mismatch=0 recorded_drift=<n> max_abs=<d> unused=0`；参考层 `EVAL_DEMO_FRAMES=INFO …` |
| G5 同进程 16 个环境 id 与命名空间归属唯一可查；各侧实际加载的包可证 | §3.3 | `REGISTRY_OWNER=PASS envs=16 owner=robomme_hard`、`NAMESPACE_OWNER=PASS envs=16 stray=0`、`ENV_PACKAGE_BINDING=PASS` |
| G6 两阶段只依赖 jsonl；首次落盘排他；回写不破坏封存、不丢并发更新 | §五 | `FREEZE_ONLY_JSONL=PASS`、`ROLLBACK_WRITE=PASS`、`STATE_MACHINE=PASS` |
| G7 三侧 h5 在 bucket 里可按 sha 读回、可拉回重比 | §5.4 | `BUCKET_SYNC=PASS sides=3 objects=<n> readback_sha_equal=<n> mismatch=0` |

## 三、文件结构与分层继承

### 3.1 `src/` 目录：每个文件从哪来

```text
src/robomme/                          官方 1fadc0ec 原样；本仓库不再往里放任何自有文件
src/robomme_hard/
  __init__.py                         先注册自家 16 环境 → 断言注册表与命名空间归属 → 借用清单 cheap 校验（§3.3、§3.4）
  UPSTREAM.json                       双锚点、src/robomme 逐文件 sha256、shim 清单、自校验哈希
  README.md
  logging_utils.py                    借用 shim（复制文件里的 ..logging_utils／...logging_utils 相对导入落在这里）
  robomme_env/
    __init__.py                       复制；新增 ENV_IDS 16 元组
    <Task>.py × 16                    复制；装饰器改 @register_env("<id>", override=True)
    utils/
      __init__.py                     复制
      改过 8 个（difficulty object_generation route segmentation_utils subgoal_language
                task_goal subgoal_planner_func vqa_options）                              复制
      新增 9 个（bin_collision episode_spec sampling_config swap_uniform unmask_distractor_sampler
                unmask_distractors unmask_swap_xhard xhard xhard_home_site）              复制
      传递依赖改过模块的 2 个（subgoal_evaluate_func task4recovery）                      复制
      闭包干净的 13 个（adjacent choice_action_mapping constant obschange oracle_action_matcher
                planner_denseStep planner_fail_safe reset_panda rpy_util save_reset_video
                SceneGenerationError statechange generate_sample_action）                借用 shim
  env_record_wrapper/
    __init__.py                       from .RecordWrapper import *（含 FailsafeTimeout）＋自家 DemonstrationWrapper、
                                      BenchmarkEnvBuilder、hard_specs、TIER_MAX_STEPS ＋借用各项 re-export
    RecordWrapper.py                  复制（fail_safe_limit=5000 是 step() 内部字面量；改 import，不加 attrs）
    DemonstrationWrapper.py           复制（相对导入 task_goal／vqa_options，借用会绑到官方旧文本）
    OraclePlannerDemonstrationWrapper.py   复制（它 import 的 vqa_options 是改过的）
    EndeffectorDemonstrationWrapper.py FailAwareWrapper.py
    MultiStepDemonstrationWrapper.py episode_dataset_resolver.py            借用 shim × 4
    hard_builder.py                   class BenchmarkEnvBuilder(官方 BenchmarkEnvBuilder)（§四）
    hard_specs.py                     load_specs、封套校验、seed 规则、TIER_MAX_STEPS
  env_metadata/
    test-hard/xhard1/specs.jsonl … test-hard/xhard4/specs.jsonl      四档规格，每格 20 局 selected（§5.3）
    train/record_dataset_{ButtonUnmask,ButtonUnmaskSwap,VideoUnmask,VideoUnmaskSwap}_metadata.json   400 条（E-12）
pyproject.toml                        wheel packages 加 "src/robomme_hard"
```

按层归纳：

| 层 | 做法 | 数量 | 理由 |
|---|---|---|---|
| 环境类 | 复制 | 16 | xhard 改动交错在 `_load_scene`／`_initialize_episode` 等长方法里，继承只能整段覆写 |
| 改过／新增 utils | 复制 | 8 + 9 | 与官方不同 |
| 传递依赖改过模块的 utils | 复制 | 2 | 见下方 ⚠ |
| 闭包干净的 utils／wrapper／logging_utils | 借用 shim | 13 + 4 + 1 = 18 | 单一真源 |
| `RecordWrapper.py`、`DemonstrationWrapper.py`、`OraclePlannerDemonstrationWrapper.py` | 复制 | 3 | 前者是字面量改动；后两者依赖改过的 `task_goal`／`vqa_options` |
| `BenchmarkEnvBuilder` | 子类，整段覆写构造路径 | 1 | §4.2 |

自有 `.py` 44 个（包 `__init__` 1 + 环境层 1 + 16 + utils 1 + 8 + 9 + 2 + wrapper 层 6），shim 18 个。

⚠ **借用资格按传递闭包判定，不按单个文件字节**（审计实测反例）：
- 复制的 `utils/__init__.py` 先 `from .subgoal_planner_func import *`、`from .object_generation import *` 绑定自家版本，再 `from .subgoal_evaluate_func import *`。
- 官方 `subgoal_evaluate_func` 模块又 `from robomme.robomme_env.utils import *`，且全链路没有 `__all__`。于是官方 `spawn_random_cube`、`insert_peg` 等整批灌回 `robomme_hard.robomme_env.utils` 命名空间，覆盖自家版本：MoveCube 调用时带 `recorder=`／`spec_path=` 抛 TypeError，InsertPeg 静默丢掉 xhard 杆 yaw 分支。
- `task4recovery` 显式 `from .subgoal_planner_func import solve_pickup` 绑定官方版。
- 官方 `DemonstrationWrapper` 相对导入 `task_goal`／`vqa_options`，评估时 `info["task_goal"]` 会是官方旧文本。
- 阶段 1、2 期间 `src/robomme` 仍是改过的版本，灌回来的函数与自家版本字节相同，所有闸门都看不出问题；阶段 3 回退后才出事。所以 §6.3 的导入类闸门一律在「官方态」下跑（第二部分 §二）。

### 3.2 借用 shim 与 import 改写规则

**为什么借用必须和注册归属一起设计**：Python 导入子模块前先执行父包 `__init__`。`robomme/robomme_env/__init__.py` 就是 16 行 `from .BinFill import *`，所以任何一次借用都会顺带把官方 16 个环境注册进 ManiSkill 注册表。

shim（每个借用文件一个同名文件，不含逻辑）：

```python
# 借用：robomme 同名模块的别名，逻辑以官方为准；清单见 ../../UPSTREAM.json
import importlib, sys
sys.modules[__name__] = importlib.import_module("robomme.robomme_env.utils.rpy_util")
```

复制文件里的导入规则：
- **相对导入**：解析目标必须在 `robomme_hard` 内存在，靠复制或 shim 落地，`logging_utils` 就是这样补上的。
- **绝对导入**：`from robomme.<path>` 且 `<path>` 在 shim 清单内的，保持不动；`<path>` 是复制件的，一律改成 `robomme_hard.`。

AST 扫描同时解析相对与绝对导入，并对每个 shim 目标做传递闭包检查：
- `ABS_IMPORT=PASS files=44 retargeted=<k> kept=<m> unresolved=0`
- `BORROWED_DEPS=PASS shims=18 changed_hits=0`

### 3.3 注册表与命名空间归属

⚠ **实测语义**（`mani_skill/utils/registration.py::register_env`）：同一 uid 二次注册时，`override=False` 只 warn 并静默保留第一个；`override=True` 会把 `REGISTERED_ENVS` 与 gym registry 两处的旧登记一起弹出，再重新注册。

五道机制：

1. **16 个副本 `@register_env("<id>", override=True)`**：进程导入过 `robomme_hard.robomme_env` 后，16 个 id 一律归它，与导入顺序无关。
   - **P2 批准（U-3）**：这是对官方类的运行时替换，属于 P2「覆盖」。用户 2026-09-27 选「现在一次批准这两项」，另一项是 §4.2 的 builder 子类覆写。
2. **`robomme_hard/__init__.py` 的导入检查**：
   - 官方已先导入时 `warnings.warn`；
   - 注册期间压低 `mani_skill` logger 时用对象本身 `from mani_skill import logger`（它的名字带尾随空格 `"mani_skill "`，按名字取会拿到另一个 logger），在 `finally` 里恢复；
   - 导入自家 `robomme_env` 后遍历 `ENV_IDS`，`REGISTERED_ENVS[uid].cls.__module__` 不以 `robomme_hard.` 开头即 `raise ImportError`。
3. **命名空间归属**：
   - 对 16 个环境模块的全部全局可调用对象检查，凡名字在自家复制模块里有定义的，`__module__` 必须以 `robomme_hard.` 开头；
   - 判定行 `NAMESPACE_OWNER=PASS envs=16 stray=0`；
   - 这一条专挡 §3.1 ⚠ 的星号导入回灌，`REGISTRY_OWNER` 只看类的模块，对这类问题结构性失明。
4. **包来源不进 h5**：
   - `env_package`、`package_fingerprint`、`REGISTERED_ENVS[task].cls.__module__`、各 wrapper 类 `__module__` 写进每局 `results.jsonl`、`identities.jsonl` 与 jsonl `rollout` 块，不写进 h5 本体；
   - 原因：H 侧 h5 多写 attrs 会让字节必然与 O／P／S4 不同，而且 `compare_h5_pair` 用 `visititems` 遍历，看不到根节点 attrs。
5. **进程隔离**：同进程一旦导入 `robomme_hard`，16 个 id 全部归它；要官方行为另开进程只导入 `robomme`。runner 里需要 `robomme_hard` 的符号（xhard seed 规则）一律只在 xhard 分支里延迟导入，O／P 侧进程不得触发。

### 3.4 G1 强校验

- **`src/robomme_hard/UPSTREAM.json`**：
  - `src_commit`、`orchestration_commit` 各 40 位（禁 `main`）；
  - `robomme_files`：`git ls-tree -r 1fadc0ec -- src/robomme` 逐文件 sha256，含 `env_metadata`；
  - `shims`：18 项，每项记官方目标模块与目标文件 sha256；
  - `vendor`：四文件 sha256，来自 `d53f21a7`；
  - `manifest_sha256`：剔掉本键后 canonical JSON 的 sha256。
- **`scripts/parity/upstream_guard.py`**（纯 CPU、秒级，纳入核心短测）：
  - `src/robomme/**` 文件集合与 sha **相等**，多一个少一个都 FAIL；
  - 阶段 3 之前输出 `UPSTREAM_BYTES=PENDING diff=<n>`，不计作短测失败；
  - 网络可达时再 `git fetch <url> 1fadc0ec` 复核，不可达标 `net=skipped`；
  - 每个 shim 是 ≤ 3 行非注释行，目标命中清单；
  - `BORROWED_DEPS` 闭包检查。
- **导入时 cheap 校验**：对 shim 目标做 cheap 档（字节数 + 首尾 1 MiB blake2b），不符只 `warnings.warn`。显式声明 cheap 挡不住等长改中间字节，full 档由守卫负责。
- **源码指纹**：`base_fingerprint`（shim 目标总 sha）+ `hard_fingerprint`（`src/robomme_hard/**.py` 总 sha）放进 jsonl header 的 `provenance` 块，**不进 `identity_sha256`**；`load_specs` 不符只警告。

### 3.5 `scripts/` 目录

```text
scripts/
  seed_layout.py  dataset_replay.py  evaluation.py  run_example.py     四入口不动（后三者官方原样）
  evaluation_hard.py                                                    第五入口，与 evaluation.py 只差 4 行（§4.3）
  injection-dev/                V6 四档生产链路，不随包分发（§五）
    freeze_specs.py  generate_h5.py                                     两个入口（路径直跑，不 -m）
    _extract.py  _draw.py  _freeze.py  _rollout.py  _report.py           内部模块（包名参数化，默认 robomme_hard）
    site/                                                               v6_site*.py、v6_candidate_values.py 等只读出图 + _io.py
  parity/                       只做「与官方比」
    train_split_parity.py  train_split_runner.py  train_split_worker.py  train_split_config.py
    train_split_comparison.py  train_split_audit.py  comparator_fixtures.py     S0 基线对拍设施（runner／worker／config 有改动，见第二部分 1.3）
    hard_parity.py              三侧对拍入口：generate / publish / compare（§5.4）
    upstream_guard.py           G1 守卫
    hard_regression.py          reset-replay（经 builder 评估链）、eval-smoke、xhw-reference
    official/                   vendor d53f21a7 的 scripts/data-generation 四文件 + SOURCE.json
      scripts/data-generation/{generate_dataset,validate_generated_dataset_contract,
                               write_generation_report,compare_joint_actions}.py
    README.md
  configs/
    newtask-v3/                 parity 用，不动（subset_manifest.json 是原三档 144 局身份清单；official_train/ 是官方 16 份 train 元数据）
    newtask-v6/v6-02/           只读留档（S4 生成用的那份）；jsonl 真源改为包内。网站 site-v12 与 final-delivery.json 维持 165 局口径不动（U-18）
    hard-parity-tolerances.json 对拍容差层阈值（U-19），由 O:P 标定后写入并进 git
    newtask-v6/smvla-smoke-0927/  不动（不在本方案范围）
    其余（newtask-v4/ v5/ v6 的 sampling_config.json、v6-01/）  删（删前把 site/ 依赖改读包内 header）
```

- **vendor 四文件的原因**：`generate_dataset.py` import 同目录的 `validate_generated_dataset_contract` 与 `write_generation_report`，后者又 import `compare_joint_actions`，缺一个就 import 不了。
- ⚠ **元数据根**：官方 validator 用 `REPO_ROOT = Path(__file__).parents[2]` 推 `METADATA_ROOT`。vendor 之后它会指向不存在的 `scripts/parity/official/src/…`，runner 在默认 `identity_source=train_metadata` 下无参调用 `read_train_metadata()` 会抛 `DatasetContractError`。所以 runner 新增 `--metadata-root`（默认 `scripts/configs/newtask-v3/official_train`，并核对其 sha 与 `subset_manifest.json::records_sha256`），显式传参。
- `identities_16x3.txt`／`manifest_16x3.json` 只有 48 行，不作原三档清单，随阶段 2 删除。

## 四、评估过程中的 env make

### 4.1 合作者看到的

```python
from robomme_hard.env_record_wrapper import BenchmarkEnvBuilder, TIER_MAX_STEPS   # 与官方唯一不同的 import
builder = BenchmarkEnvBuilder(env_id="BinFill", dataset="test-hard", action_space="joint_angle", max_steps=1300)
for episode in range(builder.get_episode_num()):                       # BinFill 80 局：xhard1 二十局 → xhard4 二十局
    seed, tier = builder.resolve_episode(episode)                        # tier 用来取按档步数上限、分档统计
    env = builder.make_env_for_episode(episode, max_steps=TIER_MAX_STEPS[tier])   # 官方签名本来就有 max_steps 覆盖参数
```

**与官方 `dataset="test"` 的对应关系**：
- `test` 每任务 50 局，easy/medium/hard 混排，步数上限 1300 一个数；
- `test-hard` 每任务 80 局，xhard4-only 的 `StopCube`、`InsertPeg`、`MoveCube` 为 20 局；按 xhard1→xhard4 排列，档内按 `candidate` 升序；步数上限按档（§4.3），不逐局传就沿用构造时的 `max_steps`，builder 不替调用方改写。

### 4.2 builder 内部

```text
dataset ∈ {train,test,val}   → 官方父类逻辑；子类覆写 _resolve_metadata_path：
                                train × 四个 Unmask 任务读 robomme_hard/env_metadata/train（400 条），其余读官方
dataset == "test-hard"       → 对 tier in (xhard1..xhard4) 依次 hard_specs.load_specs(包内 test-hard/<tier>/specs.jsonl)
                                → 取 task==env_id and selected and rollout.status=="ok" 的行，按 candidate 升序
                                → 对照写死的 55 格表核行数：格在表内必须恰好 header.delivery_per_cell（=20）行，
                                  表外（xhard1～3 × StopCube/InsertPeg/MoveCube 共 9 格）必须恰好 0 行；其余任何组合 raise（Codex #1：不接受「20 或 0」的静默放行）
                                → 四档按序拼接编为 episode 0..79（或 0..19）
resolve_identity(episode)     → 新增只读方法，返回 {tier, candidate, seed, spec_sha256, source_run}；官方二元 resolve_episode 不动（Codex #6）
其他取值                      → ValueError（与官方一致）
make_env_for_episode 整段覆写 → runtime 四项、seed、difficulty 照抄官方拼法；test-hard 时在 gym.make 前加
                                sampling_config=header.sampling_config[env_id]、native_episode_spec=row.spec；
                                包装链与官方逐项相同：DemonstrationWrapper（用 robomme_hard 复制件）
                                → 按 action_space 选的 wrapper（OraclePlanner 用复制件）→ FailAwareWrapper；
                                wrapper 一律绝对导入；不套 RobommeRecordWrapper（它属于生成链）
```

- **回注**：`native_episode_spec` 是回注。reset 时抽样流程照常发生，但每个取值点用冻结值替换，原抽样只作核验，由 `SpecRecorder` 记 `mismatch/unused`。
- **绑定摘要放包内（Codex #5）**：`robomme_hard.env_record_wrapper.spec_binding(env)` 读 `env.unwrapped._spec`，返回 `{available, mode, spec_kind, spec_sha256, value_points, injected_mismatch, recorded_drift, recorded_max_abs, unused}`；`injected_mismatch` 只数 trace 里 `source="spec"` 路径上的不等，`recorded_drift` 数 `source="record"` 路径上浮点差 ≤ 1e-5 的条目，记录点差 > 1e-5 计入 `injected_mismatch`（U-13 方案甲）。策略仓库只调这一个函数，不自己拼。
- **`resolve_episode(episode)`**：返回 `(seed, tier)`，与官方二元组同形。候选序号、来源 run、`spec_sha256` 由只读的 `resolve_identity(episode)` 暴露，不另写 `info` 键。
- **runtime 比对**：四项与 header 逐字比对，`render_mode` 放行，所以 `gui_render=True` 可以用；其余不等即 raise。
- ⚠ **白名单绕行**：官方父类 `__init__` 的 `_ALLOWED_DATASETS` 只认 `train/test/val`，而官方代码不能改。子类对 `test-hard` 先喂 `dataset_for_parent="test"` 过校验，再把 `self.dataset` 改回原值；父类顺手读的 `test` 元数据不会被使用。
- **P2**：这组覆写（`__init__`、`_resolve_metadata_path`、`resolve_episode`、`get_episode_num`、`make_env_for_episode`）属于 P2「子类覆写方法」，已由 U-3 批准；README 写实现说明。

### 4.3 评估步数上限（U-6，取代 U-2）

- **怎么定的**：按档 `TIER_MAX_STEPS = {xhard1: 1500, xhard2: 1700, xhard3: 2000, xhard4: 2600}`，就是上次评估的口径（benchmark `scripts/eval/v4_eval.py::NEWVALUE_MAX_STEPS`、SimpleMemVLA `robomme_sim/v6spec_eval.py`），用户 U-6 原话「沿用上次按档 1500/1700/2000/2600 以便对比」。
- **与实测演示长度的关系（只作佐证）**：2026-09-27 统计 S4 交付 165 局 h5 中 `info/is_video_demo` 为假的执行步数，各档最长 xhard1 1209、xhard2 1390、xhard3 1663、xhard4 2215，都在对应档上限之内；U-2 的统一 2658 作废。
- **放在哪、谁来用**：字典定义在 `robomme_hard/env_record_wrapper/hard_specs.py`，从 `env_record_wrapper` 导出。builder 不改写调用方传入的值；调用方逐局 `make_env_for_episode(ep, max_steps=TIER_MAX_STEPS[tier])`，`tier` 来自 `resolve_episode`。`scripts/eval/v4_eval.py` 仍随 `scripts/eval/` 删除，字典下沉到包内。
- **判定行**：`TIER_MAX_STEPS_SOURCE=PASS tiers=4 values=1500/1700/2000/2600 same_as=v4_eval.NEWVALUE_MAX_STEPS max_exec=1209/1390/1663/2215`，命令与输出进 `stage1.md`。
- **`scripts/evaluation_hard.py` 与 `evaluation.py` 只差 4 行**：import 行、`dataset="test"` → `dataset="test-hard"`、循环里先 `seed, tier = env_builder.resolve_episode(episode)`、`make_env_for_episode(episode)` → `make_env_for_episode(episode, max_steps=TIER_MAX_STEPS[tier])`。按 `diff | grep -c '^[<>]'` 计是 8。

## 五、数据生成链条：两阶段

### 5.1 第一阶段 `freeze_specs.py`：定规则 → 抽签 → 封存，只落一份 jsonl

**本轮不执行完整抽签**：xhard 四档规格已由 S4 冻结，本轮只迁移。下面这条命令只示范将来重新生成时的调用方式，它本身意味着 13 任务 × 1 档 × 最多 30 次 = 390 次 reset，本轮不申请这笔预算。

```bash
uv run --no-sync python scripts/injection-dev/freeze_specs.py \
  --tier xhard3 --tasks all --candidates-per-env 10 --select default \
  --max-reset-attempts 30 --workers 4 --gpus 0,1 \
  --out <新路径>/specs.jsonl
```

| 步 | 做什么 | 实现来源（搬过去不改语义） | 起环境 | 去向 |
|---|---|---|---|---|
| ① 定规则 | 对 16 任务 `import <pkg>.robomme_env.<Task>`（`pkg` 默认 `robomme_hard`，显式参数），读 `native_blocks` → 合成 `sampling_config` dict | `train_split_config.extract_task`（包名参数化） | 否 | 内存 → header |
| ② 抽签 | 每任务每档 10 候选：seed = `offset(tier) + env_code×1e5 + episode×100 + attempt`；`max_reset_attempts` 是每任务共享的总预算；reset 失败计入 `draw_stats`；子进程初始化导入同一 `pkg` 并断言注册归属 | `v4_specs._draw_one` / `draw_task` / `_draw_worker_init`（包名参数化） | 是（只 reset） | 内存 |
| ③ 封存 | 按完整选签函数选正式局：默认 0/3/6，MoveCube 在新值档按运动方式分层；算 `spec_sha256`、`identity_sha256`；封套校验 | `v4_specs.cmd_freeze` 的选签与哈希逻辑 | 否 | **唯一落盘** `--out` |

- **首次落盘**：沿用 `v4_specs._write_jsonl` 的排他发布——同目录临时文件 + `os.link`，目标已存在就原子失败。不用 `os.replace`，它会静默覆盖。
- **不再产生的文件**：`sampling_config.json`、`drafts.jsonl`；10 个候选与 `draw_stats` 都在 jsonl 里。
- **中断**：第一阶段中断即整批重抽，重抽次数计入预算。

### 5.2 第二阶段 `generate_h5.py`：只读 jsonl → 生成 → 按状态机回写

两种模式分开：

- **`--mode continue`（正常生产）**：
  - **锁先于一切（Codex #9）**：进入 continue 模式的第一步就在 `<specs>.lock` 上 `O_EXCL` 取锁并持有到回写结束；取锁失败的进程启动 worker 数为零、直接退出。锁不再放在回写阶段。
  - **待跑集**：每个 `(task,tier)` 格里 `selected=true` 且 `rollout` 缺失的行；已 ok 的行不重跑（`--redo <身份>` 显式重跑）。
  - **失败处理**：某行失败时，它的 `selected` 置 `false`，`rollout.status="failed"` 保留作历史，`tried=true`；从同格 `tried=false` 且 `selected=false` 的候选里按 `candidate` 升序递补一个，置 `selected=true`。
  - **每格不变式**：`selected=true` 的行数 ≤ `header.delivery_per_cell`（本轮 20），恢复时一样（Codex #1：不再写死 3）。
  - **基础设施失败**（进程超时、Vulkan 建不了设备、节点被抢）每身份最多重跑 1 次，计入预算，并记原因与次数；**任务失败不重试挑成功**。
- **`--mode replay --identities <清单>`（对拍专用）**：
  - 只按给定身份清单逐局重放，不递补、不回写包内 jsonl，结果只写 `--output`；
  - 清单与调度集合必须全等，判定行 `REPLAY_SET=PASS scheduled=<n> equal=<n>`。

执行细节：

1. `load_specs` 读入并封套校验，记下整份文件 sha256、`identity_sha256`、`delivery_sha256`。
2. 分批写 `jobs.json / sampling.json / specs.json` 到 `--output/_rounds/round_NN/`，子进程调 `scripts/parity/train_split_runner.py`。
   - 传 `--sampling-config`，所以走镜像 worker；环境变量 `ROBOMME_ENV_PACKAGE=robomme_hard`。
   - worker 内：`gym.make(task, sampling_config=…, native_episode_spec=row.spec, …)` → 套 `robomme_hard` 的 `RobommeRecordWrapper` → 官方 `_planner_classes` / `_execute_tasks`（vendor 的 `generate_dataset.py`）→ h5 / mp4。
3. **逐局落盘**：runner 每完成一局就追加一行 `results.partial.jsonl` 并 `fsync`；`--resume` 跳过其中已完成的身份。中断恢复只跑没完成的局，不重复消耗预算。
   - **恢复的歧义窗口（Codex #9）**：worker 已写完 h5、runner 尚未追加 partial 行时中断，单看 partial 会重跑该局。恢复时联合核对 `jobs.json`、`results.partial.jsonl`、局目录与 h5 三者：局目录有完整 h5（sha 可算、`setup` 可读）但 partial 无记录的，标 `UNKNOWN` 并列清单交用户，不直接重跑、不直接采纳。
4. **回写**（continue 模式，全部批次结束后一次，仍持有第一步的锁）：
   - 锁文件记 pid、host、启动时间；锁已存在一律拒绝并交用户，不自动判陈旧。
   - 重读 `--specs`，**整份文件 sha256 必须等于第 1 步**，否则中止，防止两个不同 `--output` 的进程互相覆盖。
   - 只改 `selected`、`tried`、`rollout`；临时文件 + `os.replace`；写后再 `load_specs` 核对 `identity_sha256` 未变，并重算 `delivery_sha256`。

**递补闭合点**：评估侧只取 `selected && rollout.status=="ok"` 的行，而每格恰好 `delivery_per_cell` 行由 builder 对照 55 格表断言保证。S4 165 局的重播（`--mode replay --identities`）是独立只读模式，不参与递补，也不受 `delivery_per_cell` 约束。

### 5.3 jsonl 结构（`schema="hard-specs/2"`）

```json
{"task": "BinFill", "tier": "xhard3", "candidate": 3, "episode": 3, "seed": 12400300, "attempt": 0,
 "selected": true, "tried": true, "initial_selected": true, "spec": {…}, "spec_sha256": "…",
 "rollout": {"status": "ok", "h5_sha256": "…", "bytes": 806055656, "frames": 412, "round": 0,
             "env_package": "robomme", "code_baseline": "ca32e9b7058ac1744be55cc6841c3ec66814a184",
             "source": "s4-relaunch-02/final-delivery.json", "written_at": "…"}}
```

一行分成「签」和「结果」两段：

```text
  ├── 签（第一阶段封存，identity_sha256 覆盖，定死）──────┤├── 结果（第二阶段回写，不进 identity）──────────┤
  task tier candidate episode seed attempt spec spec_sha256   selected tried initial_selected rollout{…}
```

- **header 键**：`schema`、`difficulty`、`tasks`、`per_env`、`runtime`、`seed_rule`、`select_rule`、`sampling_config`（全文）、`sampling_config_sha256`、`recovery_rule`、`identity_source`、`run_id`、`draw_stats`（从 v6-02 四份 `drafts.jsonl` 重建：attempted 合计 153/152/166/220 = 691）、`drafts_sha256`（保留）、`legacy_identity_sha256`（v6-02 原值，顶层键）、`provenance`{`base_fingerprint`, `hard_fingerprint`, `env_package`}、`identity_sha256`、`delivery_sha256`。行判别符 `record` 仍是字符串 `"header"`／`"spec"`。
- **`identity_sha256`**：只盖 header 里的规格键（`schema difficulty tasks per_env runtime seed_rule select_rule sampling_config_sha256 recovery_rule identity_source`），加上每行 `{task, tier, candidate, episode, seed, attempt, spec_sha256}`。`provenance`、`draw_stats`、`run_id`、结果段都不进。
- **`delivery_sha256`**：盖排序后的 `[(task, tier, candidate, seed, spec_sha256, rollout.h5_sha256)]`，只取 `selected && rollout.status=="ok"` 的行，锁住「哪几局是正式交付」。只交换两行的 `selected`，它就会变。
- **迁移（阶段 1，U-5／E-20）**：来源是上次 SimpleMemVLA 评估用的快照，不是 S4。
  - **规格来源**：benchmark 分支 `PolicyEvalThirdParty-simplememvla-0927-0146`（`1fe2d185`）的 `scripts/configs/newtask-v6/smvla-0927/xhard{1..4}/specs.reselected.jsonl` 与 `smvla-0927-fill/xhard{1,4}/specs.reselected.jsonl` 六份文件（本机 `/data` 产物目录同名）。它们的 `src/robomme` 与当前 HEAD 零 diff（`git diff --stat 1fe2d185 HEAD -- src/robomme` 为空），seed 规则同为 v6。
  - **身份真源**：上次评估的 1100 条结果（SimpleMemVLA `aab093f` 的 `docs/eval-doc/v6xhard-0927/records/<run>/` 六个目录，按目录实际文件名取：`xhard1-main-0927`、`xhard1-fill-0927`、`xhard2-0927`、`xhard3-0927`、`xhard4-0927` 各 `results-shard00of12`～`11of12`，`xhard4-fill-0927` 是 `results-shard00of06`～`05of06`；行数 200+60+260+260+314+6 = 1100，Codex #2 指出原文按 12 片写会漏 6 条）。每行有 `task/difficulty/episode/seed/spec_sha256`。抽出 `(source_run, task, tier, episode, seed, spec_sha256)` 存为本仓库 `docs/validation/newtask-v6/hard-split/records/eval-identities-1100.jsonl` 并记 sha256，作为 `DELIVERY_SET` 与 `EVAL_IDENTITY_SET` 的比对对象。
  - **来源池合并算法（Codex #2）**：六份规格文件原始 1717 行；主集与补抽集之间完整身份（`task, tier, seed, spec_sha256`）重复 89 条（InsertPeg@xhard4 是 30 对同 seed 同哈希，其中 5 对两侧同时选中；xhard1 三任务的其余重复类似），合并后 1628 行；其中正式交付 1100 行，非交付候选 528 行也入库，供将来递补。header 的 `tasks` 取并集按官方任务序，`per_env` 逐任务合并 `attempted/candidates/selected`，`select_rule` 写明「以上次评估身份为准」，`sampling_config` 取主集 header 全文（补抽集只是任务子集，`sampling_config_sha256` 因子集而异，逐任务块必须逐字相等，否则 FAIL）。判定行 `SOURCE_POOL=PASS raw=1717 dedup=89 merged=1628 delivery=1100 nondelivery=528`。
  - **h5 结果来源与逐身份绑定（Codex #3）**：`artifacts/newtask-v6/smvla-0927{,-fill}/<tier>/rollout/run1/results.jsonl` 的 `ok=true` 行给出 h5 路径。迁移按 `(source_run, task, tier, 旧 episode, seed, spec_sha256)` 唯一连接「评估结果行 ↔ 规格行 ↔ 生成结果行」三份记录，连接不唯一即 `ambiguous`；再打开 h5 只读 `setup` 组核 seed、difficulty、`task_goal` 与规格一致；重算 `h5_sha256`、`bytes`、`frames`。判定行 `H5_BINDING=PASS compared=1100 mismatch=0 ambiguous=0 missing=0`。
  - **行的取舍**：1100 个身份 `selected=true`、`rollout.status="ok"`；其余 ok 行 `selected=false`、`tried=true`、`rollout` 如实写；失败行 `status="failed"`。`candidate ← 旧 episode`；`difficulty → tier`；来源如实写 `env_package="robomme"`、`code_baseline=57fe972`（12.191）、`source_run`。
  - **header 新键**：`delivery_per_cell=20`、`identity_source="smvla-0927+fill"`、`source_files`（六份文件的 sha256）、`eval_identities_sha256`、`dedup_dropped=89`、`demo_frames_out_of_band`（U-16：xhard1 那 40 局照收，清单写进 header 与 `stage1.md`）。
  - **S4 子集（U-13 方案甲）**：v6-02 与 smvla-0927 用同一 seed 公式且源码相同，S4 的 165 个 `(task, tier, seed)` 全部落在 1100 里；spec 逐叶比对时回注点必须逐位相等，记录点允许浮点差 ≤ 1e-5。已静态核实：seed 全匹配，spec 精确相等 154，容差内 11（全部是 VideoPlace 的 `actions.return_pose_by_object_id`，最大差 1.19e-7）。判定行 `S4_SUBSET=PASS s4=165 seed_match=165 spec_exact=154 spec_within_tol=11 max_abs=1.2e-7 injected_diff=0`。回注点出现任何不等即停，交用户。

### 5.4 三侧对拍：A40@greatlakes、16 worker、行为一致判定，h5 持久化到 bucket

**为什么不做字节级（U-1）**：
- 仓库自己的实测（`docs/validation/newtask-v3/20260921-worker-nondeterminism.md`、V3 步 5d）：mplib RRT 规划器有墙钟预算 `planning_time=1` 秒，1 秒内的迭代次数取决于 CPU 当时的负载。
  - 4 worker 并发时，同一身份重跑有 3064 处字段不同；
  - 单 worker 跨节点也会分叉：PickHighlight/ep3 在 gl1517 上 647 帧、在 gl1508 上 641 帧；
  - 只有「单 worker、同一次运行内」可以逐位复现。
- 原计划「16 worker 共卡、三侧分在不同节点、整文件 sha 全等」必然会出现与拆包无关的 FAIL。原计划引用的「sha 与 worker 数无关」是反着引的。
- 用户裁决维持 16 worker，把所有边降级为行为一致判定，sha 只作参考。

**三侧定义**：

| 侧 | 代码 | 原三档 16 × 3 × 3 = 144 | xhard 13×3×3 + 16×3 = 165 |
|---|---|---|---|
| O 官方 | 编排：vendor 的 `d53f21a7` 四文件；环境源码：GL 克隆上 `git worktree` 检出的 `1fadc0ec`（`--src-root`）；走官方 `_worker` | A40 现跑 → bucket `O-1fadc0e-a40/native/` | 无 |
| P 修改前 | 同一编排；`--src-root` = tag `pre-hard-split` 的 worktree；走官方 `_worker` | A40 现跑 → bucket `P-7c7118f-a40/native/` | **复用 S4 交付存档** → bucket `P-ca32e9b-s4/xhard/`（manifest 如实写 `code_baseline=ca32e9b`、`workers=16`、驱动：gl1517／gl1510 以当日探针佐证，gl1526 那一批 78 局写 `unknown`） |
| H 修改后 | 拆包后 HEAD；`--force-mirror` + `ROBOMME_ENV_PACKAGE=robomme_hard` 走镜像 worker | A40 现跑 → bucket `H-<sha7>-a40/native/` | `generate_h5.py --mode replay --identities <S4 交付 165 身份>` → bucket `H-<sha7>-a40/xhard/` |

**身份清单**：原三档用 `scripts/configs/newtask-v3/subset_manifest.json`（`rows_total=144`、`per_cell=3`、`source_ref=d53f21a7`，sha256 `035d3405…`），三侧 generate 与 compare 都显式传它，它的 sha 写进三侧 manifest。xhard 用 `final-delivery.json::successes`（165 局；U-11：它是 `test-hard` 1100 局的子集，20 局集不另生成 h5，靠评估侧 `EVAL_BINDING` 覆盖）。**20 局集的 h5**（`/data` 上 `smvla-0927{,-fill}` 共 1.2 TB）按 U-10 先不进 bucket，bucket 只放三侧对拍产物。

**对拍矩阵**：

```text
原三档（tier=native，16 任务 × 3 档 × 3 局 = 144）
   O ──PARITY_O_P──▶ P      修改前 ≡ 官方（行为）
   P ──PARITY_P_H──▶ H      拆包不改原三档（行为；同时含官方 _worker → 镜像 worker 的差异，见盲区）
   O ──PARITY_O_H──▶ H      端到端
xhard（tier=xhard，xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165）
   P(S4) ──PARITY_P_H──▶ H  拆包不改 xhard（行为）
```

**compare 怎么比**：每侧旁写 `identities.jsonl`，每身份一行 `{task, tier, episode, seed, path, bytes, sha256, success, frames, env_module, wrapper_modules, worker}`。按身份键对齐后分三层（U-19、Codex #11）：

0. **每侧自检（前置）**：episode 在该侧唯一；h5 内 `setup` 的 seed／difficulty 与 `identities.jsonl` 一致；至少一个 `timestep_*` 组且编号连续；每个数据集的对象类型与 shape 可读；该侧全部局各自成功。任一不过，该侧不进入比对。
1. **判定层（全等才 PASS）**，结论措辞是「输入绑定、结构与任务成功一致」，不写「轨迹等价」：
   - 身份集合与清单全等；
   - 两侧 h5 都非空、可打开；
   - `setup` 相等：`seed`、`difficulty`、`task_goal`、`available_multi_choices`、相机内参；
   - 结构相等：`setup` 与每个 `timestep_*` 组的数据集名、dtype 与 shape 集合相同，不比帧数；
   - 任务成功相等且**双侧各自成功**（`both_success`）：h5 只在 `episode_success` 为真时落盘，用 `results` 的状态加 h5 是否存在来判；同失败不算相等；
   - 各侧 `env_module` 归属正确，即 `ENV_PACKAGE_BINDING`。
2. **容差层（超阈值即 FAIL，阈值可配置）**：四项指标逐身份计算、取整边最大值，与 `scripts/configs/hard-parity-tolerances.json` 里的阈值比：
   - `action_max`：共同前缀上 `joint_action` 的最大绝对差（rad）；
   - `state_max`：共同前缀上 `joint_state`／`gripper_state` 的最大绝对差；
   - `image_mad`：共同前缀上前视与腕视 RGB 的逐像素平均绝对差（0～255），取每身份均值的最大值；
   - `frames_max`：两侧帧数差的最大值。
   共同前缀 = 首个分叉时间步之前的部分；分叉步的分布另记参考层。**阈值怎么定**：O↔P 两侧源码相同（`src/robomme` 零 diff）、同硬件、同编排，其差异就是 16 worker 下 RRT 墙钟噪声的实测底线；先跑 `compare --pair O:P --calibrate`，输出四项的 p95 与最大值，默认阈值取最大值 × 1.5 写进配置文件并连同原始分布交用户确认，再跑 `P:H`、`O:H` 与 xhard 的 `P:H`。配置文件进 git，改阈值必须改文件、写进留档；命令行不允许临时覆盖（第二部分 R21）。
3. **参考层（INFO）**：`sha_equal` 计数；帧数相等计数；首个分叉时间步分布；`MEDIA_CHECK=INFO`（每侧每局 mp4 解码首帧与末帧成功计数；视频写入失败不阻止 h5 落盘，所以阶段 4 判定不涵盖 mp4，只记录）。

**bucket 持久化**（`HongzeFu/robomme-hard-parity`，U-4 取 A）：
- **流转**：
  1. 节点 `/tmp` 生成；
  2. 每局完成即 `sha256sum` 并 rsync 到 NFS 暂存 `<NFS>/hs-stage/<side>-<tier>/`；
  3. sled-vail 上的拉取进程逐局拉回 `/data/.../artifacts/newtask-v6/hard-split/h5/<side>-<tier>/`，重算 sha 一致后删掉该局 NFS 副本。NFS 上只有在途的局。
- **上传**：每片结束后，在 sled-vail 用 `uvx --from huggingface_hub==1.8.0 hf buckets sync` 从 `/data` 上传整片，连同 `identities.jsonl`、`SHA256SUMS`、`manifest.json`。manifest 记 `side, src_commit/orchestration_commit/tag/code_baseline, tier, gpu_model, driver, python/mani_skill/sapien/torch/cuda 版本, job_ids, nodes, workers, subset_manifest_sha256, generated_at`。
- **读回核对**：上传后逐对象从远端下载到临时目录，重算 sha256 与 `SHA256SUMS` 比对，比完即删临时副本，得出 `BUCKET_SYNC`。`hf buckets list -R` 的原始输出只作留档佐证，不代替读回核对。
- **收尾**：`/data` 上的 h5 在全部 compare 判定行产出后保留，删不删交用户决定；删时显式逐目录列出。

**跨硬件参考**（不进总判定）：`hard_regression.py xhw-reference` 只对现存 Ada 原三档产物 `artifacts/newtask-v6/v1/base`（16 × 3 × 3 = 144）与 A40 的 O 侧做同样两层比较，输出 `XHW_REFERENCE=INFO …`。xhard 没有 Ada 产物，不覆盖。

## 六、验收（查什么 / 怎么查 / 过了说明什么 / 判定行）

### 6.1 对拍结果（正式判定，全部 A40@greatlakes）

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| 容差标定 | `compare --pair O:P --tier native --calibrate`：输出四项指标 p95 与最大值，默认阈值 = 最大值 × 1.5 写入 `scripts/configs/hard-parity-tolerances.json`，原始分布交用户确认后才跑其余边 | 阈值有实测依据 | `PARITY_TOL_CALIB=PASS pair=O:P n=144 action_p95=<…> action_max=<…> state_max=<…> image_mad_max=<…> frames_max=<…> tol_file_sha=<…>` |
| 修改前 ≡ 官方（原三档） | O 侧与 P 侧各 16 任务 × 3 档 × 3 局，`hard_parity.py compare --pair O:P --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json` | 拆包前的代码在 A40 上原三档与官方输入绑定、结构、任务成功一致，差异在容差内 | `PARITY_O_P=PASS tier=native compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 tol=PASS action_max=<a>/<tol> state_max=<s>/<tol> image_mad=<i>/<tol> frames_max=<f>/<tol> sha_equal=<k> shape=16x3x3` |
| 拆包不改原三档 | P 侧 vs H 侧同上 | `robomme_hard` 原三档与修改前一致（同上四项 + 容差） | `PARITY_P_H=PASS tier=native compared=144 … tol=PASS … shape=16x3x3` |
| 端到端 | O 侧 vs H 侧同上 | `robomme_hard` 原三档与官方一致（同上四项 + 容差） | `PARITY_O_H=PASS tier=native compared=144 … tol=PASS … shape=16x3x3` |
| 拆包不改 xhard | S4 交付（P）vs H 侧 replay，xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 | `robomme_hard` xhard 产物与修改前交付一致（含 `task_goal` 文本；容差沿用 native 标定值） | `PARITY_P_H=PASS tier=xhard compared=165 … tol=PASS … shape=13x3x3+16x3` |
| 各侧实际加载的包 | 每局 `identities.jsonl` 的 `env_module`／`wrapper_modules` | H 侧真的跑了 `robomme_hard`，O／P 侧真的是 `robomme` | `ENV_PACKAGE_BINDING=PASS sides=3 O=robomme P=robomme H=robomme_hard mismatch=0` |
| 回注通道与评估文本 | 从 S4 每格取 candidate 最小的成功局（13×3 + 16 = 55），经 `S4_SUBSET` 映射到 20 局集里的同一身份，**经 builder 评估链** `make_env_for_episode` + reset；`spec_binding()` 摘要，`info["task_goal"]`、多选项与该局 S4 h5 `setup` 逐字比（GL 节点读不到 `/data`，比对用阶段 1 导出的带 sha 的 `s4-setup-manifest.json`，只含 `setup` 字段，Codex #12） | 新包下回注点不漂，评估链拿到的是 hard 版语言目标 | `HARD_RESET_REPLAY=PASS resets=55 replay=55 injected_mismatch=0 recorded_drift=<n> max_abs=<d> goal_mismatch=0 shape=13x3+16` |
| 三侧产物可复核 | 逐对象远端读回核对 sha | G7 | `BUCKET_SYNC=PASS sides=3 objects=<n> readback_sha_equal=<n> mismatch=0` |

- **FAIL 的读法**：
  - 判定层任一项不等时，`compare` 落 `compare/h5_pairs.jsonl`（逐身份差异项、首个分叉时间步）。
  - 只记证据链与候选修法，不放宽、不重试挑成功。
  - 先看差异是否落在 RRT 敏感身份上，并结合参考层判断是否属于墙钟非确定性；交用户裁决后才归因到驱动、编排或拆包。
  - `setup_equal` 或 `schema_equal` 不等基本不可能来自 RRT 噪声，优先查代码。

### 6.2 跨硬件参考（不进总判定）

| 查什么 | 怎么查 | 判定行 |
|---|---|---|
| Ada 原三档存档与 A40 O 侧行为一致程度 | `hard_regression.py xhw-reference`，两层比较同 §5.4 | `XHW_REFERENCE=INFO pairs=144 setup_equal=<n> success_equal=<n> sha_equal=<n> …` |

### 6.3 静态与结构判定（前置）

标 ★ 的导入类闸门在「官方态」下跑：阶段 1、2 期间用 `PYTHONPATH=<官方 1fadc0ec worktree>/src` 让 `robomme` 解析到官方树，阶段 3 之后直接跑。

| 查什么 | 怎么查 | 判定行 |
|---|---|---|
| `src/robomme` 逐字节同官方 | §3.4 守卫 | `UPSTREAM_BYTES=PASS …`（阶段 3 前为 `PENDING`） |
| vendor 四文件同源 | 与 `git show d53f21a7:scripts/data-generation/<f>` 及隔离树同名文件 `sha256sum` 比较 | `VENDOR_SAME=PASS files=4 orchestration_commit=d53f21a7` |
| ★ 导入落点无漏改 | AST 扫描相对与绝对导入 | `ABS_IMPORT=PASS files=44 unresolved=0` |
| ★ 借用闭包干净 | shim 目标传递依赖不含改过或新增的模块 | `BORROWED_DEPS=PASS shims=18 changed_hits=0` |
| ★ 注册表归属 | 三种导入顺序各起一个进程 | `REGISTRY_OWNER=PASS envs=16 owner=robomme_hard` |
| ★ 命名空间归属 | 16 个环境模块的全局可调用对象 | `NAMESPACE_OWNER=PASS envs=16 stray=0` |
| ★ 包装链同形 | 1 任务 × 4 个 action_space × `test`／`test-hard` 各 make 一个环境（不 reset），比较 wrapper 类名序列与所属包 | `WRAPPER_CHAIN=PASS action_spaces=4 chain_equal=4 hard_modules_ok=4` |
| 签不变 | 用 `git show 55f1b027:scripts/parity/v4_specs.py` 的原算法重算 legacy identity，逐位等于六份来源文件 header 已提交值；新口径对迁移投影重算自洽 | `SPECS_IDENTITY=PASS files=6 tiers=4 legacy_equal=6` |
| 来源池合并无遗漏 | 六份文件逐行计数、按完整身份去重、合并行数与交付／非交付拆分（§5.3） | `SOURCE_POOL=PASS raw=1717 dedup=89 merged=1628 delivery=1100 nondelivery=528` |
| 正式交付集合就是上次评估那 1100 局 | 包内 `selected && ok` 行与 `eval-identities-1100.jsonl` 逐身份比 `task/tier/seed/spec_sha256`；每格恰好 20 行 | `DELIVERY_SET=PASS compared=1100 equal=1100 cells=55 shape=13x3x20+16x20` |
| 规格与 h5 逐身份绑定 | 三份记录唯一连接 + h5 `setup` 内 seed／difficulty／`task_goal` 与规格一致 + sha／bytes／frames 重算（§5.3） | `H5_BINDING=PASS compared=1100 mismatch=0 ambiguous=0 missing=0` |
| S4 对拍集是交付集子集（U-13 甲） | 165 个 `(task, tier, seed)` 全在交付集；spec 回注点逐位相等，记录点浮点差 ≤ 1e-5 | `S4_SUBSET=PASS s4=165 seed_match=165 spec_exact=154 spec_within_tol=11 max_abs=1.2e-7 injected_diff=0` |
| 冻结逻辑等价 | 纯 CPU：新 `_freeze` 吃 v6-02 四份 `drafts.jsonl`，输出的候选、seed、spec、`initial_selected` 与 v6-02 逐行相同（不起环境） | `FREEZE_EQUIV=PASS tiers=4 rows=550 selected_equal=165` |
| 步数上限来源 | 字典与 `v4_eval.NEWVALUE_MAX_STEPS` 逐档相等；S4 165 局非演示执行步数各档最大值均小于对应上限 | `TIER_MAX_STEPS_SOURCE=PASS tiers=4 values=1500/1700/2000/2600 max_exec=1209/1390/1663/2215` |
| 冻结脚本未破 | `cmp` 三脚本；`ls -1 scripts/*.py \| wc -l` = 5 | `EVAL_PY_UPSTREAM=PASS ENTRIES=5` |
| 评估入口只差 4 行 | `diff scripts/evaluation.py scripts/evaluation_hard.py \| grep -c '^[<>]'` | `EVAL_HARD_DIFF=PASS lines=8` |
| 第一阶段只落一份文件 | 2 任务 × 1 档 × 1 候选、`--workers 2` smoke（本机）；前后用 `find -newer` 快照做差集 | `FREEZE_ONLY_JSONL=PASS files_written=1` |
| 回写不破坏封存 | 对 smoke jsonl 跑第二阶段 1 任务 × 1 档 × 1 局（本机） | `ROLLBACK_WRITE=PASS identity_unchanged=1` |
| 状态机 | 纯 CPU 夹具（不起仿真）：「失败 → 递补 → 中断 → 恢复」「两个不同 `--output` 争同一 specs」「锁已存在」「文件被他人改过」四个场景 | `STATE_MACHINE=PASS cases=4` |
| 原三档 A 路／镜像 worker 能起跑（开发冒烟，本机 Ada） | O 侧 A 路与 H 侧镜像各 1 任务 × 1 档 × 1 局；`hard_parity.py generate --dev-smoke` 时放行 Ada，正式 `generate` 仍写死 A40 断言（Codex #12） | `NATIVE_SMOKE=PASS sides=2 gpu=Ada mode=dev` |
| 片前冒烟（A40，阶段 4 每片起跑前） | 每片 1 局，计入预算（§3.1 已列 3 局） | `SHARD_SMOKE=PASS side=<O/P/H> gpu=A40` |
| 合作者入口可用 | `hard_regression.py eval-smoke` 限 1 任务 × 1 档 × 1 局（本机） | `HARD_EVAL_SMOKE=PASS` |
| tests 可收集且不测错包 | `--collect-only` + 残留 `robomme.robomme_env` 引用清单 | `TESTS_COLLECT=PASS errors=0 stray_official=0` |

### 6.4 评估阶段（阶段 6～8）

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| 两个策略分支只改清单内文件 | `git diff --stat <官方基点>..<分支>` 分两组统计：源码（`.py`）与依赖／仓库元数据（`pyproject.toml`、`.gitignore`、`.gitmodules`、脚本）；源码组只命中 §八 表内文件且行数不超上限（Codex #12） | 官方代码没有被顺手改 | `POLICY_DIFF=PASS repo=smvla src_files=3 src_lines<=60 meta_files=3`、`POLICY_DIFF=PASS repo=mmevla src_files=2 src_lines<=45 meta_files=1` |
| 子模块指向 | 两个策略分支的 gitlink（`git ls-tree <分支> third_party/robomme_benchmark`）都等于 benchmark `PolicyEvalThirdParty-*` 分支上的同一个 commit（拆包后 HEAD） | 两个策略评的是同一份 benchmark | `SUBMODULE_PIN=PASS commit=<sha7> repos=2` |
| 单局 smoke（每策略一局，GL） | 各在一个评估占位 job 里评 BinFill@xhard1 第 0 局，记单局耗时、主机 `MaxRSS`、GPU 峰值显存、`spec_binding`；**权重身份断言（Codex #4）**：MME-VLA 从 server 启动日志取实际 `Restoring checkpoint from <路径>` 并与 `perceptual-framesamp-modul/79999/params` 绝对路径逐字比，SimpleMemVLA 记 `--pretrained_checkpoint` 解析后的绝对路径与 `config.json` sha256；不符即 FAIL | 环境、权重、按档上限、回注都通 | `EVAL_SMOKE=PASS policy=<名> ckpt=<绝对路径> ckpt_ok=1 status=<…> steps=<n> max_steps=1500 wall_s=<…> rss_gb=<…> binding_available=1 injected_mismatch=0` |
| 第一轮 55 格 × 10 局 | 每策略 10 片各 55 局，合并后每格恰好 10 局有正常终态（success/fail/timeout）；基础设施 error 重跑每策略每轮 ≤ 55 次（U-14） | 第一轮完整 | `EVAL_ROUND1=PASS policy=<名> episodes=550 normal=550 error_left=0 retries=<n>/55 shape=55x10` |
| 第二轮余下 10 局 | 同上，合并两轮后每格恰好 20 局 | 两轮完整 | `EVAL_ROUND2=PASS policy=<名> episodes=550 normal=550 error_left=0 retries=<n>/55 total=1100` |
| 评到的正是指定身份（Codex #6） | 每局结果记 `resolve_identity` 的 `{tier, candidate, seed, spec_sha256}` 与 builder episode 号；两轮合并后与 `eval-identities-1100.jsonl` 双向全等、无重复；逐片核每片 55 局、每轮 550 局、两轮互斥 | 没有评错局、漏局、重复局 | `EVAL_IDENTITY_SET=PASS policy=<名> rounds=2 shards=10 per_shard=55 episodes=1100 missing=0 extra=0 dup=0` |
| 回注零漂移（G8，U-13 甲，Codex #5） | 每局结果记 `spec_binding()` 摘要：`available=true`、`mode=replay`、`spec_kind` 与 `spec_sha256` 等于该身份、`value_points>0`，再看 `injected_mismatch=0`、`recorded_drift` 与 `unused=0`；任一局 `mode!=replay` 直接 FAIL（export 模式三项也是零，不能当通过） | 20 局集在评估链上逐局真正回注且回注点一致 | `EVAL_BINDING=PASS policy=<名> episodes=1100 replay=1100 injected_mismatch=0 recorded_drift=<n> max_abs=<d> unused=0` |
| 演示回放未变（参考层，U-11「维持b」补的一层） | 每局评估结果记 reset 后的 `demo_frames`（`len(obs["front_rgb_list"]) - 1`）与 `demo_tasks`，与迁移时从旧 h5 读出的演示帧数逐局比；帧数受 RRT 墙钟噪声影响，只作参考不作判定 | reset 之后的演示回放在新包下没有系统性变化，补 165 局抽样看不到的 935 局 | `EVAL_DEMO_FRAMES=INFO policy=<名> episodes=1100 exact=<n> within_5=<n> max_diff=<k> demo_tasks_equal=<n>` |
| 步数上限按档生效 | 每局结果记 `max_steps`，与 tier 对应值逐局相等 | U-6 落地 | `EVAL_TIER_CAP=PASS episodes=1100 mismatch=0` |
| 占位 job 释放 | 只核本方案 JobID：删前删后 `squeue -u hongzefu` 的差集恰好等于本次要释放的清单，其他 job 一个不少（Codex #12：不要求整个队列只剩 `62126062`） | U-7、E-22 | `HOLD_RELEASE=PASS released=62126060,62126061,62018665 kept=62126062 others_unchanged=1`；`EVAL_HOLD_RELEASE=PASS released=<10 个 JobID> kept=62126062 others_unchanged=1` |

## 七、实施步骤表

| 阶段 | 内容 | 判据 | 改 `src/robomme` | commit |
|---|---|---|---|---|
| 0 准备（写文件、推 tag、建 bucket，不跑仿真） | fetch 官方两锚点并核 tree；生成 `UPSTREAM.json`；vendor 四文件 + `SOURCE.json`；导入全量扫描（相对 + 绝对 + 闭包）；打 tag `pre-hard-split` → `7c7118fa` 并 push；建 bucket（私有） | `VENDOR_SAME`；清单落 `docs/validation/newtask-v6/hard-split/stage0.md` | 否 | 12.205 |
| 1 建 `robomme_hard` | 按 §3.1 复制／shim／子类；20 局 jsonl 从 `smvla-0927{,-fill}` 迁移与回填（§5.3）；train 元数据 `cp`（不 `mv`）；`pyproject.toml` wheel packages 加 `src/robomme_hard`；`TIER_MAX_STEPS` | ★ `ABS_IMPORT`、★ `BORROWED_DEPS`、★ `REGISTRY_OWNER`、★ `NAMESPACE_OWNER`、★ `WRAPPER_CHAIN`、`SPECS_IDENTITY`、`DELIVERY_SET`、`S4_SUBSET`、`TIER_MAX_STEPS_SOURCE`、单局 `make_env_for_episode` 冒烟（官方态） | 否（U-3 已批覆盖项） | 12.206 |
| 2 `scripts/` 重组 | 按 §3.5 与第二部分 1.3；先迁移符号与调用方，再删旧文件；`tests/` 三类处理 | `FREEZE_EQUIV`、`FREEZE_ONLY_JSONL`、`ROLLBACK_WRITE`、`STATE_MACHINE`、`NATIVE_SMOKE`、`HARD_EVAL_SMOKE`、`EVAL_PY_UPSTREAM`、`EVAL_HARD_DIFF`、`TESTS_COLLECT`、`git grep -n 'v4_specs\|v4_rollout\|v5_generation\|scripts.eval' -- scripts src tests` 零命中 | 否 | 12.207 |
| 3 回退 `robomme` | 按固定 sha `1fadc0ec` 逐文件回退（清单逐文件批准，单独点名 `RecordWrapper.py` 5000→2000），删 9 个新增 utils，train 元数据回到 100 条 | `UPSTREAM_BYTES=PASS`；阶段 1、2 全部判定行在真实官方态下重跑仍 PASS（含本机冒烟，计入预算） | **是（P2 逐文件批准）** | 12.208 |
| 4 三侧对拍 | NFS 新 clone `robomme_benchmark-hs-gl`（U-17，旧克隆不动）→ 三个占位 job 分片（每片先 1 局 `SHARD_SMOKE`）→ NFS 中转回 `/data` → bucket 上传并读回 → `O:P --calibrate` 标定容差并交用户确认 → compare 四条边 → 回注 reset 13×3 + 16（S4 每格 candidate 最小局经 `S4_SUBSET` 映射）→ **释放 `62126060`、`62126061`、`62018665`，保留 `62126062`（U-7）** | `SHARD_SMOKE`、`PARITY_TOL_CALIB`、`PARITY_O_P`、`PARITY_P_H`（native／xhard）、`PARITY_O_H`、`ENV_PACKAGE_BINDING`、`HARD_RESET_REPLAY`、`BUCKET_SYNC`、`HOLD_RELEASE` | 否 | 12.209 |
| 5 拆包留档 | `robomme_hard/README.md`、`scripts/README.md`、`parity/README.md`、`docs/validation/newtask-v6/hard-split/`、`AGENTS.md` P1 五入口（阶段 2 起即为五入口）、`CLAUDE.md` 核实清单 | `git diff --check` | 否 | 12.210 |
| 6 评估准备 | benchmark 切两个 `PolicyEvalThirdParty-*` 分支并 push；两个策略仓库按 §八 从官方 main 切分支、改文件、push；NFS 上新 clone MME-VLA 并建两套环境；提交 10 个评估占位 job；每策略 1 局 GL smoke | `POLICY_DIFF` × 2、`SUBMODULE_PIN`、`EVAL_SMOKE` × 2 | 否 | 12.211（benchmark 侧只有分支与留档） |
| 7 评估执行 | 第一轮：两个策略各 55 格 × 10 局，10 片并行；第二轮：余下 10 局；合并、分档统计 | `EVAL_ROUND1` × 2、`EVAL_ROUND2` × 2、`EVAL_BINDING` × 2、`EVAL_TIER_CAP` | 否 | 12.212 |
| 8 评估留档与释放 | 两个策略仓库各自 `docs/eval-doc/`；本仓库 `docs/validation/newtask-v6/hard-split/stage7-eval.md`；`scancel` 10 个评估 job | `EVAL_HOLD_RELEASE`、`git diff --check` | 否 | 12.213 |

- **开工方式（U-15）**：用户「现在不开工 统一开工」。各阶段不再逐个请示放行；用户说「开工」后按本表 0→8 连续执行。仍须单独请示的只有三处：阶段 3 的 `src/robomme` 逐文件 P2 批准、阶段 4 容差标定值确认（`PARITY_TOL_CALIB`）、任一判定 FAIL 的裁决。
- 阶段 3 放在阶段 2 之后、阶段 4 之前：先让 `robomme_hard` 在官方态模拟下跑通，再回退 `robomme`；阶段 3 失败时只需回滚一个 commit。
- 阶段 6 的分支切出依赖阶段 5 的 HEAD（子模块要指最终版）；策略仓库的代码改动可以在阶段 4 对拍跑着的时候先写，push 与 gitlink 等 HEAD 定了再做。
- 实施完成后，实测结果以子节追加在本表之后，不改写原计划。

### 7.1 用卡表（用户 2026-09-27「每个阶段query的卡都说清楚」）

| 阶段 | 用哪些卡 | 说明 |
|---|---|---|
| 0～3（写代码、迁移 jsonl、冒烟） | 本机 1 × RTX 6000 Ada | GL 0 张；冒烟预算见第二部分 §3.1 |
| 4 三侧对拍 | GL 3 × A40：`62126060`（gl1517）、`62126061`（gl1504）、`62126062`（gl1506），各 16 worker | `62018665`（gl1510）不用 |
| 4 末 释放 | 释放 `62126060`、`62126061`、`62018665`；保留 `62126062` | 释放后 chaijy2 配额余量：GPU 19、MEM 736 G、CPU 56（写作时另有 rickzhao 0 GPU / 32 G / 8 CPU） |
| 5 拆包留档 | 0 张 | — |
| 6 评估准备 | 新交 10 个评估占位 job（各 1 GPU / 1 CPU / 32 G / 48 h）；两次 1 局 smoke 各用其中 1 张 | 10 × 32 G = 320 G，只有释放后才交得上；spgpu 全局写作时只剩 13 张空闲 A40 且空闲节点 CPU／内存紧，PENDING 可能数小时，所以阶段 4 一结束就提交 |
| 7 评估第一轮 | 10 × A40：SimpleMemVLA 55 格 × 10 局切 10 片，跑完同样 10 张卡串接 MME-VLA 55 格 × 10 局 | SimpleMemVLA 上次 12 卡 1100 局约 4 h，10 卡 550 局约 2.5 h；MME-VLA 单局耗时以 smoke 为准 |
| 7 评估第二轮 | 同 10 张卡，余下 10 局，顺序同上 | — |
| 8 收尾 | `scancel` 10 个评估 job；`62126062` 继续保留 | 释放清单以阶段 6 记的 JobID 为唯一依据 |

## 八、两个策略仓库的最小改动（U-8，用户「同意 写回计划」）

**共同前提**：两个仓库都不改模型、推理、server 代码；改动只落在「环境构建入口」「步数上限」「分片与断点续评」「子模块指向」四类文件；分支从官方 main 切出、推到用户指定的 fork；命名沿用既有模式（策略侧 `<对象>-eval-<MMDD>-<HHMM>`，benchmark 侧 `PolicyEvalThirdParty-<对象>-<MMDD>-<HHMM>`，时间取 `TZ=America/New_York`）。两个分支都没有 upstream，首次 `git push -u` 已由 U-8 授权。

| 仓库 | 官方切出点 | 分支名 | 推到 | 权重 |
|---|---|---|---|---|
| SimpleMemVLA | `OpenBMB/SimpleMemVLA@c564c17`（U-12；官方已从 `wadeKeith/SimpleMemVLA` 迁走，旧仓库 main 只剩迁移提示；`c564c17` 的代码与 `9fce41c` 逐字节相同，只多 `assets/` 与 README。NFS 检出 `/nfs/…/SimpleMemVLA` 的 `origin` 是 fork，加 `upstream` 指 OpenBMB 后在里面切） | `testhard-eval-<MMDD>-<HHMM>` | `hongzefu/SimpleMemVLA` | 未跟踪的 `checkpoints/simplememvla_robomme`、`.venv-robomme`、`third_party/ManiSkill` 留在磁盘上继续用 |
| MME-VLA | `RoboMME/robomme_policy_learning@ecf086c`（NFS 上新 clone；本机 `robomme_policy_learning-vqa-test` 有用户在途改动，不碰） | `official-testhard-eval-<MMDD>-<HHMM>` | `hongzefu/robomme_policy_learning_MotionJEPA` | `/nfs/…/robomme_policy_learning-frameSamp-continue/runs/ckpts/perceptual-framesamp-modul/79999`（14 G）按绝对路径引用，不拷贝 |
| benchmark | 拆包后 HEAD（阶段 5） | `PolicyEvalThirdParty-simplememvla-<MMDD>-<HHMM>`、`PolicyEvalThirdParty-mmevla-<MMDD>-<HHMM>` | `hongzefu/robomme_benchmark_MotionJEPA` | — |

**事实**：SimpleMemVLA 官方 `9fce41c`（`c564c17` 同）自带 `robomme_sim/`，其内嵌 `robomme_sim/robomme/` 与官方 benchmark `1fadc0ec` 逐文件比对，只差官方 benchmark 多一个杂散文件 `robomme_env/utils/vqa_options copy.py`，其余逐字节相同。所以它官方跑的环境就是本方案 G1 的锚点。`git diff --stat 9fce41c c564c17 -- robomme_sim pyproject.toml requirements.txt scripts` 为空（2026-09-27 核实）。

### 8.1 SimpleMemVLA（官方源码文件改 3 个，合计不超过 60 行；`pyproject.toml`、`.gitignore`、`.gitmodules` 为依赖／元数据改动另计；其余新增）

| # | 文件 | 改什么 | 量 | 为什么 |
|---|---|---|---|---|
| 1 | `robomme_sim/robomme_env.py` | `_setup_robomme_path(benchmark_root)`：把 benchmark 的 `src/` 放到 `sys.path` 最前并断言已加载的 `robomme` 来源一致；`RoboMMESimEnv.__init__` 在 `dataset_split == "test-hard"` 时从 `robomme_hard.env_record_wrapper` 导入 builder；`reset` 先 `resolve_episode` 取 tier，再 `make_env_for_episode(ep, max_steps=TIER_MAX_STEPS[tier])`，reset 之后调 `spec_binding(env)` 与 `resolve_identity(ep)`，把 `tier`、`max_steps`、`identity`、`spec_binding` 写进返回 info；**`SimEnvService.reset` 的返回字典同步透传这四个键，`max_steps` 用本局值而不是全局 `self.max_steps`（Codex #7）**；`SimEnvService.reset_retries` 置 0，重试只在外层计数 | ≤ 40 行 | 官方把 `sys.path` 指向内嵌副本，导不到 `robomme_hard`；按档步数只能逐局传；服务层原本重建返回字典会丢字段 |
| 2 | `robomme_sim/inproc_pool.py` | `InProcSimPool`、`SimEnvService` 透传 `benchmark_root`，`reset_retries=0` | 6 行 | 与 fork main 上的同 5 行加一处 |
| 3 | `robomme_sim/eval_success.py` | `--dataset_split` choices 加 `test-hard`；加 `--benchmark_root` | ≤ 6 行 | 只动参数解析，官方评估循环不碰 |
| 4 | 新增 `robomme_sim/testhard_eval.py` | 身份序按 `(task, tier序, candidate)`，`--round {1,2}` 取每格 candidate 最小的前 10 或后 10 局，`--shard i/10` 取排序后下标 ≡ i (mod 10)；逐条追加 `results-shardXXof10.jsonl`，每行记 `episode`（builder 号）、`identity{tier,candidate,seed,spec_sha256}`、`max_steps`、`status`、`task_success`、`error_class`、`attempt`、`spec_binding`、`demo_frames`、`demo_tasks`；`--resume` 按身份判；基础设施 error 重跑计入每轮 55 次上限，满即退出并打 `RETRY_CAP_HIT`；步数上限、绑定四项逐局核「环境阈值 = 服务返回 = 策略循环上限 = 落盘值」，不等即 FAIL 该局记 error（Codex #7） | 约 160 行 | 官方 `eval_success` 无跨卡分片与断点续评；就是上次 `v6spec_eval.py` 去掉 `load_specs`／`from_v4_specs` |
| 5 | 新增 `scripts/run_testhard.sh`、`scripts/gl_run_testhard.sh` | 两端共用启动包装（显式传 `--pretrained_checkpoint <绝对路径>`，Codex #4）、GL 占位 job 内 `srun` 包装（1 CPU、1 GPU、`--gpu_cmode=shared`、`--overlap --exact`） | 约 60 行 | 上次 `run_v6spec.sh`／`gl_run_v6spec.sh` 去掉 `SPECS` |
| 6 | 新增 `.gitmodules` + gitlink `third_party/robomme_benchmark` | 指向 `hongzefu/robomme_benchmark_MotionJEPA` 的 `PolicyEvalThirdParty-simplememvla-<MMDD>-<HHMM>` | 2 项 | 官方无子模块；钉死 benchmark 版本 |
| 7 | `pyproject.toml` | `robomme-sim` extra、ManiSkill fork 的 editable 源、`transformers==5.13.1` 约束 | 19 行 | 与 fork main 相同；不加则 `uv sync --exact` 会卸掉 ManiSkill，且 checkpoint 要求的 transformers 版本没钉死 |
| 8 | `.gitignore` | `logs/`、`checkpoints/`、`.venv-robomme/` | 7 行 | 工作区干净 |
| 9 | 新增 `docs/eval-doc/testhard-<MMDD>/` | 留档三件套 | 文档 | 规则 |

### 8.2 MME-VLA（官方源码文件改 2 个，合计不超过 45 行；`.gitmodules` 为元数据改动另计；其余新增）

| # | 文件 | 改什么 | 量 | 为什么 |
|---|---|---|---|---|
| 1 | `examples/robomme/env_runner.py` | 注册行 `from robomme.robomme_env import *` → `import robomme_hard.robomme_env`；builder、`TIER_MAX_STEPS`、`spec_binding` 从 `robomme_hard.env_record_wrapper` 导入；`dataset="test-hard"`；`make_env` 先 `resolve_episode` 取 tier，再 `make_env_for_episode(ep, max_steps=TIER_MAX_STEPS[tier])`，记 `self.tier`、`self.max_steps_for_episode`、`self.identity = resolve_identity(ep)`；**`get_init_obs` 在 `env.reset()` 之后才调 `spec_binding(self.env)`**（取值点发生在 reset，Codex #5） | ≤ 12 行 | 官方 `make_env_for_episode` 本来就有 `max_steps` 覆盖参数，只是 `env_runner` 没用 |
| 2 | `examples/robomme/eval.py` | 超时判断 `epstate.count > self.args.max_steps` → 读 `env_runner.max_steps_for_episode`；加 `episode_start`、`max_episodes`、`episode_stride` 三个参数与集号列表（MotionJEPA 仓库 `scripts/training/legacy-eval/robomme-remote/eval.py` 已有同样改法）；`progress.json` 旁另写 `episodes.jsonl`，每局一行 `{episode, identity, tier, max_steps, steps, status, task_success, error_class, attempt, spec_binding, demo_frames}`（Codex #8：终态与错误类别不压成布尔）；已有 `log.json` 时不跳过，续评按 `episodes.jsonl` 里的身份判；只有 `error_class` 属基础设施类才重试 | ≤ 30 行 | 官方无分片，步数上限是全局一个数，error 会被压成失败布尔且已有 `log.json` 会直接跳过 |
| 3 | `.gitmodules` + gitlink `third_party/robomme_benchmark` | url `RoboMME/robomme_benchmark` → `hongzefu/robomme_benchmark_MotionJEPA`，分支 `PolicyEvalThirdParty-mmevla-<MMDD>-<HHMM>`；**gitlink 必须显式移动**：`git submodule sync && git submodule update --init`，进子模块 `git checkout <拆包后 HEAD 40 位 sha>`，回到根 `git add third_party/robomme_benchmark` 提交（Codex #8：只改 `.gitmodules` 不会动官方旧 gitlink `856bc3a`） | 2 项 | 官方 gitlink 指 `856bc3a`，没有 `robomme_hard` |
| 4 | 新增 `scripts/gl_eval_shard.sh` | 同一张卡起 policy server 加仿真：端口占用守卫、`XLA_PYTHON_CLIENT_MEM_FRACTION=0.4`、`GLIBC_TUNABLES=glibc.rtld.optional_static_tls=16384`、`trap` 收 server、`EXIT_CODE=`；server 命令写全 `uv run scripts/serve_policy.py --seed=7 --port=$PORT policy:checkpoint --policy.dir=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-frameSamp-continue/runs/ckpts/perceptual-framesamp-modul/79999 --policy.config=mme_vla_suite`（Codex #4：不写 `policy:checkpoint` 会加载默认基础权重）；等端口时同时 `kill -0 $SERVER_PID`，server 就绪上限 20 分钟，首次推理单独放宽 10 分钟，单局无进展（`episodes.jsonl` mtime）30 分钟即杀掉重起并记基础设施 error（Codex #8） | 约 120 行 | 照搬 MotionJEPA `eval_shard.remote.sh`，去掉 motion sidecar |
| 5 | 新增 `scripts/merge_eval_shards.py` | 合并 10 片 `episodes.jsonl`，按 tier 分档统计；与 `eval-identities-1100.jsonl` 双向比对出 `EVAL_IDENTITY_SET`，逐片核 55 局、两轮互斥 | 约 80 行 | 每片独立输出目录 |
| 6 | 新增 `docs/eval-doc/…` | 留档 | 文档 | 规则 |

`scripts/serve_policy.py`、`src/` 下模型代码、`examples/robomme/utils.py` 一行不动。环境：新 clone 要在 NFS 上重建 uv 的 JAX 环境（续训检出实测 208 个包、约 3 分钟安装）与装了 benchmark editable 的 `robomme` Python 环境；benchmark 的 wheel packages 必须含 `src/robomme_hard`（阶段 1），否则 `pip install -e` 装出来导不到它。

---

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

- R1 `src/robomme/**` 从阶段 3 起是官方 `1fadc0ec` 原样，不放任何自有文件（`UPSTREAM.json`、README 补充一律放 `robomme_hard/` 或 `docs/`）。
- R2 `scripts/parity/official/` 四文件不改；shim 不含逻辑（≤ 3 行非注释行，守卫检查）。
- R3 `identity_sha256` 与 `delivery_sha256` 的覆盖范围（第一部分 §5.3）落地后不变；要变就换 `schema` 版本，并重跑 `SPECS_IDENTITY`／`DELIVERY_SET`。
- R4 第二阶段回写只改 `selected`、`tried`、`rollout`；锁在 `<specs>.lock`；回写前整份文件 sha 必须与读入时相同；`--force` 覆盖 jsonl 起跑前 `ls -ld` 并在回复里复述目标路径。
- R5 同进程导入 `robomme_hard` 后 16 个 id 归它；需要官方行为另开进程；O／P 侧进程不得导入 `robomme_hard`。
- R6 reset／rollout 按 §3.1 预算逐项计数，冒烟与重跑都计入；接近上限先停再补授权（P3）。
- R7 `injection-dev` 目录名保留连字符、各入口按路径直跑并自行 `sys.path.insert`；若实测 import 混乱，回来请示改名，不自行改。
- R8 `tests/` 分三类处理（第二部分 1.3），不做整目录 sed；判据 `TESTS_COLLECT`；语义未验证的测试在留档里标「未验证语义」（E-10）。
- R9 commit 只 add 本阶段文件；阶段 4 起跑前 HEAD 冻结，结果以子节追加；他人在途改动一律不碰，以实施时的 `git status --short` 为准。
- R10 **P2**：阶段 1 的两项覆盖（16 个 id `override=True` 接管；builder 子类覆写 `__init__`／`_resolve_metadata_path`／`resolve_episode`／`get_episode_num`／`make_env_for_episode`）已由用户 2026-09-27 选「现在一次批准这两项」批准，实施后出 md 报告。阶段 3 对 `src/robomme/` 的回退另列「文件 / 改什么 / 为什么」清单逐文件批准，冻结文件 `RecordWrapper.py` 单列（`fail_safe_limit` 5000 → 官方 2000；`robomme_hard` 副本保留 5000，原三档成功局都在 2000 步内）。shim 借用与复制 `RecordWrapper.py` 不改变 `robomme` 自身行为，不属于覆盖。
- R11 对拍只在 A40@greatlakes 上生成；各侧 manifest 如实记录硬件与驱动，P 侧 xhard 复用存档的驱动不明部分写 `unknown`，不得伪造；Ada 产物不混入 `PARITY_*`。
- R12 三侧 generate 的 src 来源必须能追溯到 commit／tag：O = `1fadc0ec` worktree + vendor `SOURCE.json`（`d53f21a7`）；P = tag worktree（不改动、不 commit）；H = 拆包后 HEAD。不得用带在途改动的工作区起跑。
- R13 bucket 只增不改：同一侧目录已存在时 `publish` 拒绝覆盖；需要重传先请示，并另起目录名（如 `-r2`）。
- R14 局数一律写乘式（P5）。
- R15 GL 执行：
  - 每个生成步骤 `export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`；
  - 生成步骤运行期间不另起申请 GPU 的 srun（S4 事故：shared 短步骤结束时会把卡切回 Exclusive_Process，导致 Vulkan 建不了设备）；辅助 srun 一律 `--gres=none`；
  - GPU 型号与驱动的断言放进生成步骤脚本开头；
  - sha 与 rsync 在生成步骤内完成，不另起 srun。
- R16 本轮不执行任何完整抽签（§5.1）；20 局规格只迁移不重抽（U-5）。
- R17 **策略仓库改动边界（E-21）**：两个策略分支只改第一部分 §八 列出的文件；不改模型、推理、server、训练代码；官方原有文件的改动行数不超过表中上限（`POLICY_DIFF`）；分支只推到 U-8 指定的两个 fork，不推官方远端；本机 `robomme_policy_learning-vqa-test` 的在途改动一律不碰。
- R18 **占位 job 释放清单（U-7、E-22）**：阶段 4 末只 `scancel 62126060 62126061 62018665`，逐个、名字写全、删前删后各 `squeue -u hongzefu` 一次；`62126062` 全程保留；评估 job 只按阶段 6 记入 `stage6-eval-prep.md` 的 10 个 JobID 逐个取消；禁止 `scancel -u`。
- R19 **步数上限按档（U-6）**：`TIER_MAX_STEPS` 四个值 1500/1700/2000/2600 不得在评估脚本里被覆盖或放宽；每局结果必须记录实际生效的 `max_steps`（`EVAL_TIER_CAP`）；上次的加长步数重测不在本方案范围。
- R20 **评估不重试挑成功**：fail／timeout 一律如实记录；只有基础设施 error（reset 抛错、Vulkan 建设备失败、server 断连、进程超时）允许重跑，每身份最多 3 次尝试、每策略每轮合计最多 55 次（U-14），并记原因与次数；两轮各 550 局跑完就算完，不补局（用户「这次20局跑完不补了」）。
- R21 **容差层阈值只认配置文件（U-19）**：对拍容差层的四个阈值只从 `scripts/configs/hard-parity-tolerances.json` 读，文件进 git；`compare` 不提供命令行覆盖；标定值由 `--calibrate` 写入后须经用户确认（原始分布一并交），确认后才跑 `P:H`、`O:H`；改阈值就是改文件并写进留档与 commit body。
- R22 **记录点容差（U-13 方案甲）**：`spec_binding()` 只对 trace 里 `source="record"` 的路径允许浮点差 ≤ 1e-5，`source="spec"` 的回注点必须逐位相等；容差常量定义在 `robomme_hard.env_record_wrapper.hard_specs.RECORDED_FLOAT_TOL = 1e-5`，不做参数。任何 `injected_mismatch > 0` 即 FAIL。
- R23 **统一开工（U-15）**：用户说「开工」前不执行任何写入仓库或集群的动作；开工后按步骤表连续执行，只在 R10 的 P2 批准、R21 的容差确认、任一 FAIL 三处停下请示。

## 一、逐阶段、逐文件改动清单

### 1.1 阶段 0（写文件、推 tag、建 bucket，不跑仿真）

| 动作 | 命令 / 产物 | 判定 |
|---|---|---|
| 取官方两锚点 | `git fetch https://github.com/RoboMME/robomme_benchmark 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9 d53f21a7947d2d8daf6e3e8bad9f59b4f89a77fa`；`git rev-parse <sha>^{tree}` 分别等于 `3006988f…`、`1d4c1369…`，**不等即停**；`git diff --quiet 1fadc0ec d53f21a7 -- src/robomme` 退出码 0 | 记入 `stage0.md` |
| `UPSTREAM.json` | `robomme_files` 用 `git ls-tree -r 1fadc0ec -- src/robomme` 列文件，逐个 `git cat-file blob \| sha256sum`；`shims` 按第一部分 §3.1；`manifest_sha256` 按 §3.4 | 文件就绪 |
| vendor | `git show d53f21a7:scripts/data-generation/<f>` × 4 → `scripts/parity/official/scripts/data-generation/`；`SOURCE.json`{`url, orchestration_commit, tree, path, files{sha256}, vendored_at`}；与隔离树同名文件逐个 `cmp` | `VENDOR_SAME=PASS files=4` |
| 导入扫描 | AST 遍历 `src/robomme/**.py`：相对、绝对、星号导入全部解析；对候选借用模块求传递闭包；分 copy／shim 两列写 `stage0.md`；预期结果即第一部分 §3.1 | 清单落盘 |
| tag | `git tag pre-hard-split 7c7118fa` 并 `git push origin pre-hard-split`（阶段 0 获批即含本项） | `git ls-remote --tags origin pre-hard-split` |
| bucket | sled-vail：`uvx --from huggingface_hub==1.8.0 hf buckets create HongzeFu/robomme-hard-parity --private`，沿用本机已登录凭据，不新落 token 文件 | `hf buckets list HongzeFu` 原文落 `stage0.md` |

### 1.2 阶段 1：`src/robomme_hard/`

| 文件 | 来源 | 改什么 |
|---|---|---|
| `robomme_env/<Task>.py` × 16 | `cp src/robomme/robomme_env/<Task>.py` | `@register_env("<id>")` → `@register_env("<id>", override=True)`；按 §3.2 改绝对导入 |
| `robomme_env/__init__.py` | cp | 追加 `ENV_IDS = ("BinFill", …)` 16 元组，顺序同导入顺序 |
| `robomme_env/utils/` 改过 8 + 新增 9 + `subgoal_evaluate_func`、`task4recovery` + `__init__.py` | cp | 按 §3.2 改绝对导入：`subgoal_planner_func.py` 两处（按 AST 扫描结果逐条列出）、`vqa_options.py` 一处，`subgoal_evaluate_func.py` 的 `from robomme.robomme_env.utils import *` → `robomme_hard.` |
| `robomme_env/utils/<借用>.py` × 13 | 新写 | 三行 shim；`planner-ref.py`、`vqa_options copy.py` 不可 import，不建 |
| `logging_utils.py` | 新写 | shim → `robomme.logging_utils` |
| `env_record_wrapper/RecordWrapper.py` | cp | `step()` 内延迟导入 `from robomme.robomme_env.utils.vqa_options import …` → `robomme_hard.`；**不加任何 h5 attrs** |
| `env_record_wrapper/DemonstrationWrapper.py` | cp | 相对导入不动，已落在 `robomme_hard` 复制件上 |
| `env_record_wrapper/OraclePlannerDemonstrationWrapper.py` | cp | 顶部 `from robomme.robomme_env.utils.vqa_options` → `robomme_hard.` |
| `env_record_wrapper/{EndeffectorDemonstrationWrapper,FailAwareWrapper,MultiStepDemonstrationWrapper,episode_dataset_resolver}.py` | 新写 | shim × 4 |
| `env_record_wrapper/hard_specs.py` | 从 `scripts/parity/v4_specs.py` 下沉 | 搬 `HEADER_KEYS`、`canonical_json`、`digest`、`identity_sha256`（按 §5.3 口径）、`delivery_sha256`（新增）、`seed_rule_for`、`_known_seed_rule`、`seed_for`、`DIFFICULTY`、`load_specs`、`RUNTIME`；新增 `base_fingerprint()`／`hard_fingerprint()`、`TIER_MAX_STEPS = {"xhard1": 1500, "xhard2": 1700, "xhard3": 2000, "xhard4": 2600}`（值抄自 `scripts/eval/v4_eval.py::NEWVALUE_MAX_STEPS`，删除前 `cmp`）；指纹不符只 `warnings.warn`；`draw`/`freeze` 不搬 |
| `env_record_wrapper/hard_builder.py` | 新写 | 第一部分 §4.2：`_ALLOWED = {train,test,val,test-hard}`；覆写 `__init__`、`_resolve_metadata_path`、`resolve_episode`、`get_episode_num`、`make_env_for_episode`（整段，包装链照官方、全部绝对导入 `robomme_hard` 的 wrapper；`max_steps` 覆盖参数语义与官方相同：传了就用 `max_steps+2`，不传用构造值）；行数断言对照模块常量 `EXPECTED_CELLS`（55 格表）：表内格 `== header.delivery_per_cell`，表外格 `== 0`；新增只读 `resolve_identity(episode) -> dict`；`from_v4_specs` 保留为薄包装 |
| `env_record_wrapper/hard_specs.py`（续） | 同上 | 新增 `RECORDED_FLOAT_TOL = 1e-5` 与 `spec_binding(env) -> dict`（R22；按 `SpecRecorder.trace` 的 `source` 分类 mismatch，输出 `available/mode/spec_kind/spec_sha256/value_points/injected_mismatch/recorded_drift/recorded_max_abs/unused`），从 `env_record_wrapper` 导出供策略仓库调用（Codex #5） |
| `env_metadata/test-hard/s4-setup-manifest.json` | 阶段 1 由 `migrate_smvla_specs.py --export-s4-setup` 生成 | S4 165 局 h5 的 `setup` 字段（seed、difficulty、`task_goal`、多选项、相机内参）与 h5 sha256，供 GL 节点上的 `HARD_RESET_REPLAY` 比对（GL 读不到 `/data`，Codex #12） |
| `env_record_wrapper/__init__.py` | 新写 | `from .RecordWrapper import *`、`from .DemonstrationWrapper import *`、`BenchmarkEnvBuilder`、`hard_specs`、`TIER_MAX_STEPS` + 借用 re-export |
| `__init__.py` | 新写 | 顺序：读 `UPSTREAM.json` → 检查官方是否已导入（warn）→ `from mani_skill import logger` 临时提到 ERROR → `from . import robomme_env` → `finally` 恢复 → 遍历 `ENV_IDS` 断言注册归属 → 命名空间归属断言 → shim cheap 校验（warn） |
| `env_metadata/test-hard/xhard{1..4}/specs.jsonl` | `git show 1fe2d185:scripts/configs/newtask-v6/smvla-0927{,-fill}/<tier>/specs.reselected.jsonl`（六份）迁移 | 第一部分 §5.3「迁移」：同档两份来源合并、同 seed 去重；`candidate ← episode`、`difficulty → tier`；从 `artifacts/newtask-v6/smvla-0927{,-fill}/<tier>/rollout/run1/results.jsonl` 回填 `rollout`（逐局核对 h5 存在并重算 sha256／bytes／frames）；`selected` 只对 `eval-identities-1100.jsonl` 里的身份为真，每格恰好 20；写 `tried`／`initial_selected`；header：`delivery_per_cell=20`、`identity_source`、`source_files`、`eval_identities_sha256`、`dedup_dropped`，`draw_stats` 从六份 `draft/drafts.jsonl` 重建，`legacy_identity_sha256` 放顶层（六个值列表），`provenance` 块；`schema` → `hard-specs/2`；新口径重算 `identity_sha256`／`delivery_sha256`。迁移脚本放 `scripts/injection-dev/migrate_smvla_specs.py`（一次性入口，路径直跑） |
| `docs/validation/newtask-v6/hard-split/records/eval-identities-1100.jsonl` | 从 NFS `SimpleMemVLA` 检出 `git show aab093f:docs/eval-doc/v6xhard-0927/records/<run>/results-shardXXof12.jsonl`（六个 run 目录）抽 `task/difficulty/episode/seed/spec_sha256` | 1100 行；文件 sha256 写进 jsonl header 与 `stage1.md` |
| `env_metadata/train/` 4 份 | **`cp`** 自 `src/robomme/env_metadata/train/`（阶段 3 才把 `robomme` 侧恢复为官方 100 条） | 不改 |
| `UPSTREAM.json`、`README.md` | 阶段 0 产物 / 阶段 5 写 | — |
| `pyproject.toml` | 现有 | `packages = ["src/robomme", "src/robomme_hard"]`；确认 wheel 带上包数据（`specs.jsonl`、`UPSTREAM.json`、train 元数据） |
| 统计脚本 | scratchpad 或 `artifacts/` 临时脚本，不进 `scripts/` 顶层 | `TIER_MAX_STEPS_SOURCE` 命令与输出进 `stage1.md` |

### 1.3 阶段 2：`scripts/`

**先迁移、后删除**：下表「删除」一行最后执行，执行前跑完 `git grep` 零命中闸门。

| 文件 | 来源 | 改什么 |
|---|---|---|
| `injection-dev/_extract.py` | 新写 | 调用 `train_split_config.extract_task(task, pkg=…)`；`build_sampling(tasks, pkg="robomme_hard", release="newtask-v6") -> dict` |
| `injection-dev/_draw.py` | `parity/v4_specs.py` 抽签部分 | `_draw_one`、`draw_task`、`_draw_worker_init(pkg)`、`_parse_gpus`、`parse_task_max_reset_attempts`、`env_kwargs`、`recovery_mode`；`seed_for` 改从 `hard_specs` 导入；输入是 sampling dict，不读文件；返回 rows + `draw_stats`；worker 初始化后断言注册归属 |
| `injection-dev/_freeze.py` | `parity/v4_specs.py` 封存部分 | `cmd_freeze` 改成纯函数 `freeze(rows, header_parts) -> (header, rows)`，保留完整选签函数（含 MoveCube 分层）与 `reselect` 语义；哈希用 `hard_specs`；首次落盘排他写 `_write_jsonl`（`os.link`）一并搬来 |
| `injection-dev/freeze_specs.py` | 新写 | CLI（第一部分 §5.1）；串 ①②③；`--pkg`（默认 `robomme_hard`）；`--dry-run`；`--self-check` |
| `injection-dev/_rollout.py` | `parity/v4_rollout.py` | `_run_batch` 的 runner 命令带 `ROBOMME_ENV_PACKAGE`；输入改为 jsonl 行；`--mode continue/replay`；状态机与 `write_back`（第一部分 §5.2）；`<specs>.lock` |
| `injection-dev/generate_h5.py` | 新写 | CLI（§5.2）；`--mode`、`--identities`、`--redo`、`--resume`；调 `_rollout` |
| `injection-dev/_report.py` | `parity/v5_generation.py` 报告部分 | 输入改为 jsonl `rollout` 块 + `results.jsonl`；去掉 drafts 依赖；计数字段显式输出零值（P4 教训）；输出 `HARD_GENERATION=REPORT …` |
| `injection-dev/site/` | `git mv parity/{v6_site.py,v6_site.html,v6_site_catalog.py,v6_candidate_values.py,v6_tier_monotone.py,v6_v0_native_definitions.py,v6_gt_lengths.py,v6_gt_lengths.json}` | 内部导入路径随之改；`v6_candidate_values` 依赖的 `_read_jsonl`、`_check_sources` 搬进 `site/_io.py`；`DEFAULT_CONFIG` 改读包内 jsonl header 的 `sampling_config` |
| `parity/train_split_config.py` | 现有 | `extract_task(task, pkg="robomme")` 包名参数化，默认值不变，S0 语义保持 |
| `parity/train_split_worker.py` | 现有 | `pkg = os.environ.get("ROBOMME_ENV_PACKAGE", "robomme")`，所有 `import robomme…`（含 `FailsafeTimeout`）改成 `importlib.import_module(f"{pkg}…")`；每局在结果里写 `env_module`（`REGISTERED_ENVS[task].cls.__module__`）与 `wrapper_modules` |
| `parity/train_split_runner.py` | 现有 | `--official-root` 默认 `scripts/parity/official`；`.official_tree` 校验改读 `official/SOURCE.json["tree"]`；新增 `--metadata-root`（默认 `scripts/configs/newtask-v3/official_train`，核 sha），显式传给 `read_train_metadata(metadata_root)`；`--src-root` 在 vendor 默认下必填；formula 分支的 `from scripts.parity.v4_specs import …` 改为在分支内延迟 `from robomme_hard.env_record_wrapper.hard_specs import DIFFICULTY, _known_seed_rule, seed_for`；透传 `ROBOMME_ENV_PACKAGE`；逐局追加 `results.partial.jsonl` 并 fsync，`--resume` |
| `parity/hard_parity.py` | 现有，重构为三侧入口 | 见下方三个子命令；运行前断言 `nvidia-smi` 型号 = A40、驱动与 manifest 所记一致，否则拒跑；子进程环境沿用现有 `child_env()` 的 `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1` |
| `parity/upstream_guard.py` | 新写 | 第一部分 §3.4；`--manifest-md` 输出 README ③表；阶段 3 前输出 `PENDING` |
| `parity/hard_regression.py` | 新写 | `reset-replay`（13×3 + 16 = 55 次，从 S4 每格取 candidate 最小的成功局，经 `S4_SUBSET` 映射到 20 局集的 builder episode 号，经 `hard_builder.make_env_for_episode` + reset，用包内 `spec_binding()` 摘要，`task_goal`、多选项与 `s4-setup-manifest.json` 逐字比）；`eval-smoke`（本机 1 任务 × 1 档 × 1 局）；`xhw-reference`（§6.2）；`s4-subset`（纯 CPU：seed 匹配 + 回注点逐位 + 记录点 ≤ `RECORDED_FLOAT_TOL`，输出 `S4_SUBSET` 与映射表 `s4-to-delivery.json`） |
| `evaluation_hard.py` | `cp scripts/evaluation.py` | import 行、`dataset="test-hard"`、循环里加 `resolve_episode` 取 tier、`make_env_for_episode(episode, max_steps=TIER_MAX_STEPS[tier])` 共 4 行（第一部分 §4.3） |
| 删除（最后执行） | `git rm` `parity/{v4_specs,v4_rollout,v5_generation,legacy_keep_list}.py`、`parity/{identities_16x3.txt,manifest_16x3.json}`、`scripts/eval/`、`configs/newtask-v4/`、`configs/newtask-v5/`、`configs/newtask-v6/{sampling_config.json,v6-01/}`；`rm -r` 未跟踪 `scripts/injection/`（先列清单）；`parity/results/`（被 ignore，内有 aspen 16x3 的 `run.log`、`B.log`）**本方案不删**，列清单交用户 | `ls -1 scripts/*.py` = 5；`git grep` 零命中 |
| `tests/**` | 现有 | 分三类逐文件列清单：① 模块级导入已删／已搬脚本（8 个文件、共 30 处）→ 改路径或删除该测试；② 子模块路径导入 wrapper → 改包级导入，或靠 4 个 wrapper shim 解析；③ `importlib.import_module("robomme.robomme_env.<Task>")` 字符串导入（34 处）与按路径读文件 → 逐条决定测 `robomme_hard` 还是有意测官方，有意测官方的加注释；不做整目录 sed |

`hard_parity.py` 三个子命令：

- **`generate --side {O,P,H} --tier {native,xhard} --manifest <清单> --workers 16 --gpu 0 --out <节点 /tmp>`**：
  - O 侧：`--official-root scripts/parity/official --src-root <1fadc0ec worktree>`；
  - P 侧：`--src-root <tag worktree>`；
  - H 侧：`--force-mirror` + `ROBOMME_ENV_PACKAGE=robomme_hard`；
  - xhard 走 `injection-dev/generate_h5.py --mode replay --identities <S4 交付>`；
  - 每局写 `identities.jsonl` 行，完成即 sha + rsync 到 NFS 暂存。
- **`publish --side … --bucket HongzeFu/robomme-hard-parity`**：在 sled-vail 上跑，从 `/data` 上传，写 `SHA256SUMS`、`manifest.json`，逐对象读回核对。
- **`compare --pair {O:P,P:H,O:H} --tier … --manifest <清单> [--calibrate]`**：先做每侧自检，再按身份键对齐做判定层、容差层、参考层（第一部分 §5.4），落 `compare/h5_pairs.jsonl`（逐身份四项指标与首个分叉步）。`--calibrate` 只允许 `O:P`：不判容差层，输出四项指标的 p95／最大值，把「最大值 × 1.5」写入 `scripts/configs/hard-parity-tolerances.json`（键 `action_max_rad`、`state_max`、`image_mad`、`frames_max`、`calibrated_from`、`n`、`raw_p95`、`raw_max`），打印 `PARITY_TOL_CALIB`；非 calibrate 模式读该文件，缺文件即拒跑（R21）。

### 1.4 阶段 3：`src/robomme/`（P2）

1. **出清单交批**：`git diff --name-status 1fadc0ec HEAD -- src/robomme`，预期 30 M + 9 A：
   - 30 M = 16 个环境 + 8 个 utils + `RecordWrapper.py` + `episode_config_resolver.py` + 4 个 train json；
   - 9 A = 新增 utils。
   - 清单中单列 `RecordWrapper.py` 的改动内容与理由。
2. **批准后执行**：对批准的文件逐个 `git checkout 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9 -- <文件>`（固定 sha，不用会变的 `FETCH_HEAD`，不整树 checkout），再 `git rm` 9 个新增 utils。
3. **提交前核对**：`git status --short -- src/robomme` 与清单逐项对上才 commit。

### 1.5 阶段 6：benchmark 分支与两个策略仓库

| 仓库 / 文件 | 动作 |
|---|---|
| benchmark：`PolicyEvalThirdParty-simplememvla-<MMDD>-<HHMM>`、`PolicyEvalThirdParty-mmevla-<MMDD>-<HHMM>` | 从阶段 5 HEAD `git branch` 两个分支并 `git push -u origin <分支>`；不加任何提交（两个策略的子模块指同一个 commit） |
| SimpleMemVLA（NFS 检出，`origin` = `hongzefu/SimpleMemVLA`） | `git remote add upstream https://github.com/OpenBMB/SimpleMemVLA.git && git fetch upstream main`；确认 `upstream/main == c564c17`（`git ls-remote` 复核，不一致即停交用户）；`git checkout -b testhard-eval-<MMDD>-<HHMM> c564c17`；按第一部分 §8.1 的 9 项改；`git submodule add -b PolicyEvalThirdParty-simplememvla-<MMDD>-<HHMM> https://github.com/hongzefu/robomme_benchmark_MotionJEPA.git third_party/robomme_benchmark`（目录已存在时先 `git submodule deinit`／移走旧目录，不删 `.venv-robomme`）；`git push -u origin <分支>` |
| MME-VLA（NFS 新 clone `<NFS>/robomme_policy_learning-official-testhard/`） | `git clone https://github.com/RoboMME/robomme_policy_learning.git` 并核 `origin/main == ecf086c`；`git remote add fork https://github.com/hongzefu/robomme_policy_learning_MotionJEPA.git`；`git checkout -b official-testhard-eval-<MMDD>-<HHMM> ecf086c`；按 §8.2 的 6 项改；`.gitmodules` url／branch 改后 `git submodule sync && git submodule update --init`，进 `third_party/robomme_benchmark` 执行 `git checkout <拆包后 HEAD 40 位 sha>`，回根目录 `git add .gitmodules third_party/robomme_benchmark` 提交，`git ls-tree HEAD third_party/robomme_benchmark` 必须等于该 sha（Codex #8）；`git push -u fork <分支>` |
| MME-VLA 环境 | `UV_LINK_MODE=copy uv sync`（JAX 侧，参照续训检出 `.venv` 的 208 包）；`robomme` 环境：`uv venv --python 3.11 robomme_env && uv pip install -r examples/robomme/requirements.txt -e third_party/robomme_benchmark -e packages/openpi-client`，随后 `uv pip freeze > robomme_env.lock.txt` 提交到分支作为可复现依赖声明（临时评估环境，按第 3 条例外不改根 `pyproject.toml`）；预检一律用 **`robomme_env/bin/python -c "import robomme_hard, robomme; print(robomme_hard.__file__)"`**，不用根项目 `uv run`（Codex #8：那是另一个解释器） |
| 评估占位 job × 10 | `sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:1 --gpu_cmode=shared --cpus-per-task=1 --mem=32G --time=48:00:00 --job-name=hs-eval-<k> --wrap='sleep infinity'`，k=1..10；JobID 逐个记入 `stage6-eval-prep.md`；只在 `HOLD_RELEASE=PASS` 之后提交（配额），超过 4 个属第 8 条「数量超默认」，本方案已由用户「eval使用10卡并行 greatlake hold 48h」授权 |
| smoke | 每策略 1 局（BinFill@xhard1 第 0 局）在第一个到 RUNNING 的评估 job 里跑，记 `EVAL_SMOKE` |

## 二、闸门总表

判定行见第一部分 §六，此处只补实现位置：

| 判定 | 实现位置 |
|---|---|
| `UPSTREAM_BYTES`、`VENDOR_SAME`、`ABS_IMPORT`、`BORROWED_DEPS` | `upstream_guard.py` |
| `REGISTRY_OWNER`、`NAMESPACE_OWNER` | `tests/lightweight/test_registry_owner.py`（三种导入顺序各用 `subprocess` 起一个进程） |
| `WRAPPER_CHAIN` | `tests/lightweight/test_wrapper_chain.py`（需要 GPU，标 `gpu`） |
| `SPECS_IDENTITY`、`SOURCE_POOL`、`DELIVERY_SET`、`H5_BINDING`、`S4_SUBSET`、`FREEZE_EQUIV`、`TIER_MAX_STEPS_SOURCE` | 阶段 1、2 一次性核对脚本（`migrate_smvla_specs.py --check`、`hard_regression.py s4-subset`），命令与输出进 `stage1.md`／`stage2.md` |
| `SHARD_SMOKE`、`PARITY_TOL_CALIB` | `hard_parity.py generate --smoke 1`、`compare --pair O:P --calibrate`，原文进 `stage4.md`，标定分布交用户确认 |
| `POLICY_DIFF`、`SUBMODULE_PIN` | 阶段 6 在两个策略检出里跑 `git diff --stat` 与 `git ls-tree`，原文进 `stage6-eval-prep.md` |
| `EVAL_SMOKE`、`EVAL_ROUND1`、`EVAL_ROUND2`、`EVAL_IDENTITY_SET`、`EVAL_BINDING`、`EVAL_TIER_CAP`、`EVAL_DEMO_FRAMES` | SimpleMemVLA `testhard_eval.py` 与 MME-VLA `merge_eval_shards.py` 各自输出；汇总进 `stage7-eval.md` |
| `HOLD_RELEASE`、`EVAL_HOLD_RELEASE` | 删前删后 `squeue -u hongzefu` 原文进 `stage4.md`／`stage7-eval.md` |
| `FREEZE_ONLY_JSONL`、`ROLLBACK_WRITE` | `injection-dev` 入口的 `--self-check` |
| `STATE_MACHINE` | `tests/lightweight/test_hard_state_machine.py`（纯 CPU 夹具） |
| `NATIVE_SMOKE`、`PARITY_*`、`ENV_PACKAGE_BINDING`、`BUCKET_SYNC`、`REPLAY_SET` | `hard_parity.py` |
| `HARD_RESET_REPLAY`、`HARD_EVAL_SMOKE`、`XHW_REFERENCE` | `hard_regression.py` |
| `TESTS_COLLECT` | `pytest --collect-only` + `git grep` 残留清单 |

★ 类闸门在阶段 1、2 用 `PYTHONPATH=<1fadc0ec worktree>/src` 模拟官方态运行。

## 三、预算与 runbook

### 3.1 预算（P3；**用户 2026-09-28「2同意」已一次性批准（U-14）**；全部按乘式；reset 与 rollout 分别列上限、分别与阈值比较，每次 rollout 尝试计一次 reset，Codex #10）

| 项 | 乘式 | rollout 上限 | reset 上限 | worker | 硬件 |
|---|---|---|---|---|---|
| 阶段 1 单局 `make_env_for_episode` 冒烟（官方态） | 1 任务 × 1 档 × 1 局 | 0 | 1 | 1 | 本机 Ada |
| `WRAPPER_CHAIN` | 1 任务 × 4 action_space × 2 dataset，只 make 不 reset | 0 | 0 | 1 | 本机 Ada |
| `FREEZE_ONLY_JSONL` smoke | 2 任务 × 1 档（xhard1）× 1 候选，`--max-reset-attempts 5` | 0 | 2 × 5 = 10 | 2 | 本机 Ada |
| `ROLLBACK_WRITE` smoke | 1 任务 × 1 档 × 1 局 | 1 | 0 | 1 | 本机 Ada |
| `NATIVE_SMOKE` | 1 任务 × 1 档 × 1 局 × 2 侧（O A 路、H 镜像） | 2 | 0 | 1 | 本机 Ada |
| `HARD_EVAL_SMOKE` | 1 × 1 × 1 | 1 | 0 | 1 | 本机 Ada |
| 阶段 3 后重跑以上五项 | 同上 | 1 + 2 + 1 = 4 | 1 + 10 = 11 | 同上 | 本机 Ada |
| O 侧原三档 | 16 任务 × 3 档 × 3 局 | 144 | 0 | 16 | A40 |
| P 侧原三档 | 16 × 3 × 3 | 144 | 0 | 16 | A40 |
| H 侧原三档 | 16 × 3 × 3 | 144 | 0 | 16 | A40 |
| H 侧 xhard（按 S4 交付身份重放，不递补） | 13 × 3 × 3 + 16 × 3 | 165 | 0 | 16 | A40 |
| 片前冒烟 `SHARD_SMOKE` | 3 片 × 1 局 | 3 | 0 | 16 | A40 |
| 基础设施重跑上限 | 每身份最多 1 次，合计上限 | 30 | 0 | 16 | A40 |
| `HARD_RESET_REPLAY` | 13 × 3 + 16（经评估链，含演示回放） | 0 | 55 | 1 | A40 |
| **生成侧合计** | | **本机 8 + A40 600 + 基础设施重跑 30 = 最多 638** | **纯 reset 77 + 每次 rollout 尝试各一次 638 = 最多 715** | | |

**评估侧（策略 rollout；U-14 已批准；不是数据生成，单列不并入上表；服务内部 reset 重试关闭，一局一次 reset）**：

| 项 | 乘式 | 评估局数 | reset | 卡 |
|---|---|---|---|---|
| smoke | 2 策略 × 1 任务 × 1 档 × 1 局 | 2 | 2 | 评估 job 各 1 张 |
| 第一轮 | 2 策略 × 55 格 × 10 局 | 1100 | 1100 | 10 × A40 |
| 第二轮 | 2 策略 × 55 格 × 10 局 | 1100 | 1100 | 10 × A40 |
| 基础设施 error 重跑硬上限 | 每策略每轮 ≤ 55 次（10%），2 策略 × 2 轮 | 220 | 220 | 同上 |
| **评估合计** | | **最多 2422** | **最多 2422** | |

- 重跑硬上限用满即 `RETRY_CAP_HIT`，该片停下交用户，不自动扩到「每身份 3 次」推出的 4400。

- **不另计的**：`STATE_MACHINE`、`FREEZE_EQUIV`、`SPECS_IDENTITY`、`DELIVERY_SET`、`S4_SUBSET`、`TIER_MAX_STEPS_SOURCE`、`XHW_REFERENCE` 都不起仿真；P 侧 xhard 复用 S4 存档；20 局 jsonl 迁移不起仿真（U-5）。
- **原 0926 计划 D 项授权的 V1′ 144 局**（Ada 侧 vs S0 基线）作废不跑。
- **停止条件**：
  - 任一冒烟判定 FAIL 即停；
  - 基础设施重跑用满 30 即停；
  - 任一占位 job 剩余不足 6 小时即停，交用户决定；
  - 判定层 FAIL 不停止其他分片，但不做任何重试挑成功。
- **预计耗时**：每片 16 worker 原三档约 30 分钟；xhard 165 局约 30～60 分钟（relaunch-02 实测 16 worker 下 39 局 210～329 s、48 局 392 s）；回注 55 次在 H 原三档之后串行。
- **授权方式**：实施前把本表原样交用户，取得一次明确批准；没有批准不得起跑，不以代理复述数字代替授权。

### 3.2 GL 分片 runbook（阶段 4）

**前置**：

1. 三个 `hs-hold` job 存活，且剩余 ≥ 6 小时（`squeue -u hongzefu -o '%i %L'`）；任一到期即停下交用户，不自行 sbatch。
2. **GL 克隆准备（U-17「新clone」）**：旧克隆 `robomme_benchmark-newtask-gl`（`1bb4190`，93 处脏改动）一律不动。新 clone `<NFS>/robomme_benchmark-hs-gl`：`git clone https://github.com/hongzefu/robomme_benchmark_MotionJEPA.git -b newtaskRelease-v5`，`git checkout <拆包后 HEAD 40 位 sha>`，`UV_LINK_MODE=copy UV_CACHE_DIR=$HOME/.cache/uv uv sync`（解释器用 NFS 上已有的 uv managed Python），`git worktree add <NFS>/robomme_benchmark-hs-gl-p pre-hard-split`、`git worktree add <NFS>/robomme_benchmark-hs-gl-o 1fadc0ec…`；`git status --short` 必须为空才起跑（R12）。
3. `.venv` 的 editable `.pth` 是纯路径条目，`src/robomme_hard` 自动可导入；在计算节点上用 `uv run --frozen --no-sync python -c "import robomme_hard"` 核对，不在计算节点装依赖。
4. `df` 断言：节点 `/tmp` ≥ 160 GB；NFS 暂存余量 ≥ 100 GB（在途最多 16 worker × 约 1.5 GB × 3 片）；`/data` ≥ 400 GB。

**容量**（实测均值）：原三档约 349 MB／局 × 144 ≈ 50 GB／侧；xhard 约 706 MB／局 × 165 ≈ 116 GB。本轮新生成 3 × 50 + 116 ≈ 267 GB 落 `/data`；bucket 另加 P 侧 xhard 存档 116 GB，合计约 383 GB。

**启动方式**：每片在 GL 登录节点起 detached tmux，会话 `hs-<side>-<tier>`，记下登录节点主机名；会话内执行 `srun --jobid=<id> --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared bash <片脚本>`，片脚本自己 `tee` 日志到 NFS `<NFS>/hs-logs/<side>-<tier>.log`。本机 Monitor 直接 tail NFS 上的日志，一份日志一个 Monitor，所以 ssh 掉线不影响分片。sled-vail 上另起 tmux `hs-pull` 跑逐局拉取进程。

| job | 节点 | 片（同一 job 内的两段写进同一个片脚本，逐段写 `EXIT_CODE=`） |
|---|---|---|
| 62126060 | gl1517 | O 原三档 16×3×3 → H xhard 13×3×3 + 16×3（replay） |
| 62126061 | gl1504 | P 原三档 16×3×3 |
| 62126062 | gl1506 | H 原三档 16×3×3 → 回注 reset 13×3 + 16 = 55 |

- **片脚本固定动作**：
  - 开头：断言 GPU 型号与驱动，`export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`；
  - 每局：`sha256sum` 追加 `SHA256SUMS`，rsync 到 NFS 暂存，删掉节点 `/tmp` 副本；
  - 片结束：写 `EXIT_CODE=`。
- **接续夹具**：跑之前先用不起仿真的夹具验证「第一段完成 → 读真实格式报告 → 第二段」与「第一段失败 → 停止」（P4）。
- **Monitor 过滤词**：`NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT|EXIT_CODE=|Traceback|=PASS|=FAIL|RUNNER_DONE`。

四片跑完并拉回 `/data` 后，在本机执行：

```bash
uv run --no-sync python -m scripts.parity.hard_parity publish --side O --tier native
uv run --no-sync python -m scripts.parity.hard_parity publish --side P --tier native
uv run --no-sync python -m scripts.parity.hard_parity publish --side H --tier native
uv run --no-sync python -m scripts.parity.hard_parity publish --side H --tier xhard
uv run --no-sync python -m scripts.parity.hard_parity publish --side P --tier xhard   # S4 存档，manifest 记 ca32e9b
uv run --no-sync python -m scripts.parity.hard_parity compare --pair O:P --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json
uv run --no-sync python -m scripts.parity.hard_parity compare --pair P:H --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json
uv run --no-sync python -m scripts.parity.hard_parity compare --pair O:H --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json
uv run --no-sync python -m scripts.parity.hard_parity compare --pair P:H --tier xhard  --manifest artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json
```

- **产物去向**：bucket 是权威归档；NFS 暂存逐局即删，片结束后确认目录为空再 `rmdir`；`/data` 上的 h5 保留到用户决定。
- **tmux 会话清单**：本机 `hs-pull`，GL 登录节点三个 `hs-*`，写进 `stage4.md`；清理时按清单逐个 `kill-session -t '=名'`。
- **FAIL 处置**：只记证据链与候选修法，不放宽、不重试挑成功；基础设施失败按 §3.1 上限重跑，先停对应会话、核对没有残留 worker，按 `results.partial.jsonl` 续跑。
- **阶段 4 末释放（U-7、R18）**：全部 compare 判定行与 `HARD_RESET_REPLAY` 产出、`/data` 拉回核对完成后，确认三个 job 内无活动 `srun` 步（`squeue -s -j <id>`），再逐个 `scancel 62126060`、`scancel 62126061`、`scancel 62018665`；删前删后 `squeue -u hongzefu` 原文进 `stage4.md`，差集必须恰好是这三个；`62126062` 保留。随后立即按 §1.5 提交 10 个评估占位 job。

### 3.3 评估 runbook（阶段 6～8）

**前置**：`HOLD_RELEASE=PASS`；10 个评估 job 至少 1 个 RUNNING 才能 smoke，全部 RUNNING 才起第一轮；两个策略分支已 push，`SUBMODULE_PIN=PASS`；GL 计算节点上 `uv run --frozen --no-sync python -c "import robomme_hard"`（SimpleMemVLA 用 `.venv-robomme`，MME-VLA 用 `robomme_env`）通过。

**分片与轮次**：
- 身份序：builder 给每任务的 episode 号是 tier 主序（xhard1 的 20 局是 0..19，xhard2 是 20..39，依此类推；xhard4-only 任务只有 0..19），档内按 candidate 升序。第一轮取每档前 10（每任务 episode `{0..9, 20..29, 40..49, 60..69}`），第二轮取每档后 10。
- SimpleMemVLA：`testhard_eval.py --round <轮> --shard <i>/10`，片 `i` 取该轮身份按 `(task, episode)` 排序后下标 ≡ i (mod 10) 的局；GL 登录节点 tmux `hs-eval-smvla-r<轮>-s<i>`，会话内 `bash scripts/gl_run_testhard.sh <JobID_i> <i>/10 <RUN_TAG> --round <轮>`；每片写 `logs/testhard/<RUN_TAG>/results-shard<i>of10.jsonl`；片内 error 身份靠 `--resume` 下一轮重跑，`gl_run_testhard.sh` 最多 3 轮，受每轮 55 次重跑上限约束。
- MME-VLA：同一批 10 个 job，SimpleMemVLA 某轮 10 片全部 `EXIT_CODE=0` 后再起（同卡串接，不并发）；片 `i`（0..9）、轮 `r`（1..2）用官方 `eval.py` 新增的三个参数表达：`episode_start = 10 × (r − 1) + i`、`episode_stride = 20`、`max_episodes = 0`；于是每片每任务在 80 局的任务里取 `{i, i+20, i+40, i+60}`（第一轮）或 `{10+i, 30+i, 50+i, 70+i}`（第二轮），在 20 局的任务里取 `{i}` 或 `{10+i}`，每片 13 × 4 + 3 × 1 = 55 局（Codex #6）；tmux `hs-eval-mmevla-r<轮>-s<i>`，会话内 `srun --jobid=<JobID_i> --overlap --exact --ntasks=1 --cpus-per-task=1 --gpu_cmode=shared bash scripts/gl_eval_shard.sh`，环境变量 `SHARD=<i> ROUND=<r> PORT=$((8100+i))`；server 命令按 §8.2 第 4 项写全，eval `--args.model_seed=7 --args.model_ckpt_id=79999 --args.episode_start=$((10*(ROUND-1)+SHARD)) --args.episode_stride=20 --args.max_episodes=0 --args.save_dir=<NFS>/eval-out/mmevla-r<轮>-s<i>`。
- 逐片验收：每片结束核 `episodes.jsonl` 行数 = 55 且身份互不重复；每轮 10 片并集 = 550；两轮并集 = 1100 且与 `eval-identities-1100.jsonl` 双向全等（`EVAL_IDENTITY_SET`）。
- 顺序：SimpleMemVLA 第一轮 → MME-VLA 第一轮 → SimpleMemVLA 第二轮 → MME-VLA 第二轮（U-9）。第一轮两策略都出 `EVAL_ROUND1=PASS` 后才起第二轮。
- **Monitor**：一份日志一个 Monitor，过滤词 `EPISODE_START|status=|EXIT_CODE=|Traceback|out of memory|svulkan2|EXCLUSIVE|ErrorIncompatibleDriver|API calling error|did not receive a valid HTTP response|=PASS|=FAIL`。
- **产物回收**：结果 jsonl／`progress.json`／`episodes.jsonl` 从 NFS `cp` 回本机两个策略仓库留档目录后删 NFS 副本；评估视频只留每格 1 条（SimpleMemVLA `--video_max_per_task 1`；MME-VLA 官方每局都存视频，片结束后只保留每格第一条、其余删除并记数）。
- **收尾**：两轮四组判定行齐全 → 逐个 `scancel` 10 个评估 job（删前删后 `squeue -u hongzefu`，差集恰为 10 个）→ `EVAL_HOLD_RELEASE`；`62126062` 保留。
- **停止条件**：任一评估 job 剩余不足 6 小时而该片未完成 → 停下交用户；MME-VLA smoke 主机 `MaxRSS` > 28 G → 停下交用户决定是否重交 48 G 的评估 job；spgpu 全局排队使 10 个 job 超过 12 小时未全部 RUNNING → 汇报用户，不自行改规格。

## 四、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | RRT 墙钟非确定性让判定层（任务成功）在个别身份上不等 | 已降级为行为判定（U-1）；成功不等仍判 FAIL，交用户裁决；参考层帮助判断是否属于噪声 |
| 2 | shim 借用触发官方 16 环境注册，日志 16 条 `Override registered env` | 接受；只在自家注册段用 logger 对象临时压低 |
| 3 | 官方 `main` 前进，借用文件变化悄悄改 xhard 行为 | 双锚点钉 commit，守卫 FAIL 即停；升级是显式动作，要重跑全部闸门 |
| 4 | 父类 `__init__` 白名单绕行在官方改签名时断裂 | 属于风险 3 的升级流程 |
| 5 | 新增的复制件或官方改动让借用闭包变脏 | `BORROWED_DEPS` 与 `NAMESPACE_OWNER` 在官方态下跑 |
| 6 | 两个 `generate_h5.py` 同时回写同一 jsonl | `<specs>.lock` + 整份文件 sha 比对 + `STATE_MACHINE` 夹具 |
| 7 | `tests/` 替换后假 PASS／假 FAIL | R8 三类处理 + 残留清单 |
| 8 | 连字符目录名与 `-m` 不兼容 | R7 |
| 9 | GL 驱动升级后参考层数字漂移 | manifest 记驱动；判定层不依赖字节 |
| 10 | `O↔P` 判定层 FAIL | 不是拆包问题；先用 `compare/h5_pairs.jsonl` 定位，查编排、src 或 RRT 噪声，交用户裁决后再看 `P↔H` |
| 11 | 16 worker 共卡时 `svulkan2`／`EXCLUSIVE` 建设备失败 | `--gpu_cmode=shared` 写死；R15 不另起 GPU srun；Monitor 过滤词覆盖 |
| 12 | 登录节点重启导致远端 tmux 丢失 | 片脚本在 srun 步骤内独立运行；日志在 NFS；按 `results.partial.jsonl` 续跑 |
| 13 | bucket 上传或读回中断 | `publish` 可重入（只补缺对象）；只增不改（R13） |
| 14 | `P↔H` native 同时含官方 `_worker` 与镜像 worker 的差异 | 列入盲区；判定层 FAIL 时先对比同侧两种 worker 再归因 |
| 15 | chaijy2 内存配额：10 个评估 job 需 320 G，释放前只剩 160 G | 顺序写死：阶段 4 释放 3 个 job 后才 `sbatch`；`(AssocGrpMemLimit)` 出现即停，不改 account／partition |
| 16 | spgpu 全局只剩十几张空闲 A40，评估 job 长时间 PENDING | 阶段 4 一结束即提交让排队与阶段 5、6 并行；超 12 小时未全部 RUNNING 汇报用户 |
| 17 | MME-VLA server 与仿真同卡：JAX 预分配显存、首次推理 JIT 数分钟、主机内存未实测 | `XLA_PYTHON_CLIENT_MEM_FRACTION=0.4`；client 首次调用超时单独放宽；smoke 记 `MaxRSS`，> 28 G 停下交用户 |
| 18 | 单进程连续 `make_env` 超过约 27 次触发 Vulkan 静态 TLS 泄漏（`ErrorIncompatibleDriver`） | MME-VLA 片脚本 `GLIBC_TUNABLES=glibc.rtld.optional_static_tls=16384`（每片每轮 55 局）；SimpleMemVLA 上次每片 90+ 局未触发，沿用其 `InProcSimPool` |
| 19 | S4 165 局不是 1100 局的子集（seed 公式或源码差异） | `S4_SUBSET` FAIL 即停交用户，不改判据 |
| 20 | 官方 `pip install -e third_party/robomme_benchmark` 装不出 `robomme_hard` | 阶段 1 wheel packages 加 `src/robomme_hard`；阶段 6 `robomme_env/bin/python -c "import robomme_hard"` 不过即停 |
| 21 | 两个策略分支 push 到 fork 的远端已有同名分支 | 名字带 `<MMDD>-<HHMM>`，push 前 `git ls-remote` 核对不存在；被拒即停，不 force |
| 22 | `OpenBMB/SimpleMemVLA` main 在阶段 6 前再前进 | 切出点钉死 `c564c17`（40 位 sha 写进留档），不追 tip；tip 前进只记录，不改切出点 |
| 23 | 记录点浮点漂移超过 1e-5（新的硬件或驱动） | 会被 `spec_binding()` 计入 `injected_mismatch` 判 FAIL，交用户；不放宽 `RECORDED_FLOAT_TOL` |
| 24 | 容差层阈值标定自单次 O:P 实现，过宽会漏真差异、过窄会误杀 RRT 噪声 | 标定输出 p95 与最大值两组数交用户确认；PASS 判定行同时打印实测值与阈值，留档保留 `compare/h5_pairs.jsonl` 全部逐身份指标供事后复核 |
| 25 | 评估重跑硬上限 55／轮用满 | `RETRY_CAP_HIT` 停该片交用户，不自动加码 |

## 五、盲区诚实清单

- **①（已查清，关闭）**：官方 builder 只有 `__init__`、`get_task_list`、`_resolve_metadata_path`、`resolve_episode`、`get_episode_num`、`make_env_for_episode` 六个成员；`evaluation.py` 只用其中四个；`self.dataset` 只在 `_resolve_metadata_path` 里用；`resolve_episode` 返回二元组。
- **②（已查清，关闭）**：`MultiStepDemonstrationWrapper` 只依赖闭包干净的 utils；真正的问题在 `DemonstrationWrapper`，已改为复制。
- **③**：官方 `_worker`（O／P 侧）与镜像 worker（H 侧）在 A40 原三档上是否行为一致，没有直接证据；`P↔H` native 的差异可能混有 worker 差异。
- **④（已查清，关闭）**：v6-02 四份 `drafts.jsonl` 都在，sha 与 header 一致，`draw_stats` 可以精确重建。
- **⑤**：A40 与 Ada／A6000 分叉的根因（驱动 595 vs 570、PhysX GPU 内核、渲染器）没有拆分；判定层不依赖字节，影响有限。
- **⑥**：P 侧 xhard 存档在 gl1526 上生成的 78 局（xhard1/2），驱动版本无记录。
- **⑦（已查清，关闭）**：`final-delivery.json` 记录了全部 165 局 h5 的 sha256 与字节数，文件都在 `/data`，`code_baseline=ca32e9b`，含 2 局递补（InsertPeg@xhard4 ep2、ep4）。
- **⑧**：`HARD_RESET_REPLAY` 经评估链时会回放演示，单次耗时未实测。
- **⑨**：MME-VLA 在 xhard 上的单局耗时、主机内存、显存峰值都没有实测；上次只有 SimpleMemVLA 的数字（A40 单局 1.5～3 分钟、`MaxRSS` 26.4 GB）。第一轮耗时估算只对 SimpleMemVLA 成立。
- **⑩（已查清，关闭）**：官方仓库已迁到 `OpenBMB/SimpleMemVLA`，main `c564c17` 相对 `9fce41c` 代码零改动（U-12）；阶段 6 起步时只需 `git ls-remote` 复核 tip 未再前进。
- **⑪**：上次评估的 1100 个身份里，xhard1 三格与 xhard4 InsertPeg 取自补抽快照，其余取本体快照前 20；迁移脚本以评估结果文件为真源而不是重算取法，取法差异不影响集合定义。
- **⑫（已裁决，U-16「不管」）**：上次评估报告的 `demo_frames_out_of_band=40`（xhard1 演示帧数落在 750～1050 带外）照收进 20 局集，清单写进 jsonl header 与 `stage1.md`；不影响回注一致性。
- **⑬**：`GLIBC_TUNABLES` 16384 字节能支撑的 `make_env` 次数按 8192 → 约 147 轮线性外推，未实测。
- **⑭**：容差层阈值来自单次 O:P 实现（144 对），RRT 噪声的真实分布只有这一份样本；`P:H`、`O:H` 若在个别身份上略超阈值，无法区分是拆包差异还是噪声尾部，只能交用户裁决（风险 24）。
- **⑮**：S4 165 局与 1100 局的 spec 差异只查到记录点 `return_pose_by_object_id`；评估在 A40 上是否还有别的记录点漂移（如其他任务的落稳位姿）要到 `EVAL_BINDING` 的 `recorded_drift` 明细才知道，方案甲已把 ≤ 1e-5 的都纳入。

## 六、留档与 commit 纪律

- 每阶段一个 commit（12.205～12.213），subject 接体例，body 按 `AGENTS.md` 第 11 条六项；只 `git add` 本阶段文件。
- 判定行原文与命令进 `docs/validation/newtask-v6/hard-split/stage<n>.md`；阶段 1 另出 P2 覆盖项 md 报告（U-3「改完出报告」）；阶段 4 的 reset／rollout 逐项计数表与 `HOLD_RELEASE` 前后 `squeue` 原文进 `stage4.md`；阶段 6 的 10 个评估 JobID、`POLICY_DIFF`／`SUBMODULE_PIN` 原文进 `stage6-eval-prep.md`；阶段 7 的两轮四组判定行、分档成功率表（每策略 4 档 × 每格 20 局）、`EVAL_HOLD_RELEASE` 进 `stage7-eval.md`。
- 两个策略仓库各自留档：SimpleMemVLA `docs/eval-doc/testhard-<MMDD>/`、MME-VLA `docs/eval-doc/testhard-<MMDD>/`，按第 12 条三件套（`launch.md`／`result.md`／`records/`），records 只放结果 jsonl 与汇总表，不放视频与权重；每个策略分支的 commit 按该仓库自身体例。
- 评估成功率与上次 SimpleMemVLA 20 局结果（`aab093f` 留档）可直接对比：同身份、同按档步数上限；差异来源只剩 benchmark 从 `robomme`（12.191）换成 `robomme_hard`（拆包后）与演示回放的 RRT 墙钟噪声，留档里要把这两点写明。
- 容差层：`scripts/configs/hard-parity-tolerances.json` 进 git；`stage4.md` 记 `PARITY_TOL_CALIB` 原文、四项指标的 p95／最大值分布、用户确认原话；`compare/h5_pairs.jsonl` 全部逐身份指标进 `records/`。
- 用户本轮裁决原话（2026-09-28）：「1同意甲 但是计划全解释后报告 2同意 4不管 5新clone 6先不纳入 7动作、状态、图像数值、帧数要容差可控 3现在不开工 统一开工」，逐条落点见 §一 U-13～U-19。

## 七、Codex 审计（`AUDIT_BASE=6608e38b`）十二条的落点（U-20）

| # | Codex 发现 | 落点 |
|---|---|---|
| 1 | 20 局交付仍接着 3 局状态机；「20 或 0」静默放行 | 第一部分 §4.2（55 格表 `EXPECTED_CELLS`）、§5.2（`delivery_per_cell`、S4 重播独立只读） |
| 2 | 迁移命令漏 6 条（xhard4-fill 是 6 片）；合并口径未定义；InsertPeg 计数不准 | §5.3 身份真源与来源池合并算法；`SOURCE_POOL` |
| 3 | 规格与 h5 未逐身份绑定 | §5.3 三份记录唯一连接 + h5 `setup` 核；`H5_BINDING` |
| 4 | MME-VLA 可能加载默认权重；SimpleMemVLA 依赖默认权重路径 | §8.2 第 4 项 server 命令写全；§8.1 第 5 项显式传权重；`EVAL_SMOKE` 权重身份断言 |
| 5 | `EVAL_BINDING` 在 export 模式也全零；绑定读取时点在 reset 之后；摘要函数须在包内 | §4.2 `spec_binding()` 进包；§6.4 `mode=replay`、`value_points>0`、`available=true`；§8.2 第 1 项 `get_init_obs` 之后取 |
| 6 | 未证明评到指定身份；`resolve_episode` 不暴露候选号；MME-VLA 分片公式缺 | §4.2 `resolve_identity`；§6.4 `EVAL_IDENTITY_SET`；第二部分 §3.3 分片公式与逐片验收 |
| 7 | SimpleMemVLA 服务层丢按档上限与绑定字段；内部重试叠加 | §8.1 第 1、2、4 项：服务返回契约、`reset_retries=0`、四者一致核 |
| 8 | MME-VLA gitlink 未移动；预检解释器不对；错误续评未闭合；server 等待无期限 | §8.2 第 2、3、4 项；第二部分 §1.5 两行 |
| 9 | 生成锁取得太晚；恢复漏记窗口 | §5.2 锁先于一切、`UNKNOWN` 标记 |
| 10 | 预算漏计 reset；评估额外尝试未授权 | 第二部分 §3.1 重算（生成 reset ≤ 715；评估重跑硬上限 220）；U-14 批准 |
| 11 | 对拍 PASS 含义比「行为一致」窄；缺每侧自检；同失败算相等；MP4 不在闸门内 | §5.4 三层重写、每侧自检、`both_success`、`MEDIA_CHECK=INFO`；U-19 措辞与容差层 |
| 12 | 回注抽检取错局且 GL 读不到 `/data`；`NATIVE_SMOKE` 与 A40 断言冲突；`HOLD_RELEASE` 口径；`POLICY_DIFF` 混计 | §6.1 `HARD_RESET_REPLAY` 经 `S4_SUBSET` 映射 + `s4-setup-manifest.json`；§6.3 `--dev-smoke` 与 `SHARD_SMOKE`；§6.4 两行改写 |

Codex 的核验限制（`c564c17` 不在其对象库）已由主代理在 scratchpad 取官方 main 比对关闭（U-12）。
- 实施完成后，实测结果以子节追加在第一部分 §七步骤表之后，不改写原计划。
- `robomme_hard/README.md` 必含：
  - ① 一句话说明，以及三条 `PARITY_*`（native）+ 一条 `PARITY_P_H`（xhard）判定行原文，注明是行为一致判定；
  - ② 四档定稿表（从 `0925-newtask-release-v6-plan.md` 第一部分 §三逐字搬）；
  - ③ 复制／借用／子类／新增逐文件表（`upstream_guard.py --manifest-md` 生成）；
  - ④ 机制：`sampling_config` 两块、`SpecRecorder` 导出与回注、jsonl 签与结果两段及两个哈希、seed 偏移、注册表与命名空间归属、借用闭包规则；
  - ⑤ 使用：`dataset="test-hard"` 示例与 `test` 的对应关系（每任务 80 或 20 局、档序、候选序）、`TIER_MAX_STEPS` 按档上限的来源与逐局传法、`resolve_episode` 取 tier、`override_metadata_path`、两阶段生产命令（注明不随包分发）；
  - ⑥ 红线 R1～R5、R11；
  - ⑦ `dataset_for_parent="test"` 绕行说明。
