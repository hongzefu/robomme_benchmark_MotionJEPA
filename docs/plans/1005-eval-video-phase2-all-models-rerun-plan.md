# 1005-eval-video-phase2-all-models-rerun-plan.md — 第二阶段：新接口直出官方版式视频，然后在 GL A40 上跑第一、二、三档

> **权威与授权**：只规划不实施。开工须用户明确说「开工」（`AGENTS.md` 第 2 条）。本版 2026-10-06 按用户「写的我还是看不懂你要重新说……」「彻底重构第一部分给人看的部分」重写第一部分（顺序：全部运行一览图 → 第二档逐模型两侧 → 我们这一侧要改什么），再按「第一部分内容太多了我不需要那么多内容」压成只留决策信息，逐模型细节移到第二部分八节；事实由四个只读子代理逐文件核对；取代 12.463～12.468 各版；12.473 按 2026-10-06 Codex 静态审计（21 条）与用户三项裁决修订；口径以本文为准。
> **代码锚点**：`bf7dddf3`（12.462，第一阶段重绘工具 `scripts/eval-official/render_official_video.py` 已合入）。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，提交编号 `12.<小版本>`。
> **外部锚点**：MME-VLA 子模块 `ecf086c3`、PonderPounce `723df357`、SimpleMemVLA `c564c17`（本阶段都不改）。上一轮三档见 `docs/validation/sg-eval-gl-20261004-01/`；SimpleMemVLA、MME 原侧来自 v7.5eval（`docs/validation/v7.5eval/official-rerun.md`）。
> **已批准**（2026-10-06）：开工后无人值守跑到计划结束、不设截止、≤10 卡、占位 job 自管（02:22 EDT 授权，开工令仍未下）；第二部分六节预算（含 SimpleMemVLA、MME 原侧重跑 384 局增量，合计轨迹 ≤6364、reset ≤12927）；Astra 本机 smoke ≤2 局、5 美元；集群操作预授权；占位 job ≤10 卡自行提交／取消、48 h、尽早排队。**未批**：计划本身、开工令。

# 第一部分（给人看）

## 一、要做什么与全部运行一览

**一句话**：给六条新接口路线补「官方版式视频 + 统一逐步记录」（原版代码一行不改），然后在 GL A40 上跑三档：第一档生成对拍；第二档五个模型「原侧 vs 新侧」各 16 任务 × 1 档 × 12 局 = 192 局；第三档五个模型 V9 各 800 局。Astra 只做本机 smoke。

```
 开工 ─┬─ 批次 1（有卡即跑）  第一档 177 局 ｜ QwenVL 原侧补跑 153 局 ｜ PonderPounce 原侧补跑 96 局
       │   本机改代码：S0 → 9 个子代理并行 → 逐个合并
       ├─ 批次 2（GroundSG 代码合入）   GroundSG Oracle/QwenVL 新侧：第二档 2×192，第三档 2×800
       ├─ 批次 3a（S7 合入）           SimpleMemVLA/MME 原侧重跑 2×192（原版入口 + 只读观测器）
       ├─ 批次 3b（S4 合入）           SimpleMemVLA/MME 新侧：第二档 2×192，第三档 2×800
       ├─ 批次 4（PonderPounce 合入）    PonderPounce 新侧：第二档 192，第三档 800
       └─ 批次 5（Astra 合入）          Astra 本机 smoke ≤2 局
 批次之间不互相等待；第二档与第三档不互相等待；第二档对比另等 S6 合入与两侧结果齐。
 每批起跑前三件事：核依赖集合与冻结 sha（RUN_INPUTS）、对该批路线做 CPU 客户端回放（CLIENT_REPLAY_EQ）、本机 1 局 smoke。
```

| 批次 | 档 | 模型 | 侧 | 规模 | 机器 |
|---|---|---|---|---|---|
| 1 | 第一档 | 全部共用 | — | V9 43 格 × 3 局 + xhard0 16 任务 × 3 局 = 177 局 | GL A40 |
| 1 | 第二档 | GroundSG QwenVL | 原侧补跑 | 192 − 已有 39 = 153 局 | GL A40 |
| 1 | 第二档 | PonderPounce | 原侧补跑 | 分片 1 共 96 局 | GL A40 |
| 2 | 第二、三档 | GroundSG Oracle、QwenVL | 新侧 | 2 × 192 + 2 × 800 | GL A40 |
| 3a | 第二档 | SimpleMemVLA、MME | 原侧重跑（原版入口 + 只读观测器） | 2 × 192 | GL A40 |
| 3b | 第二、三档 | SimpleMemVLA、MME | 新侧 | 2 × 192 + 2 × 800 | GL A40 |
| 4 | 第二、三档 | PonderPounce | 新侧 | 192 + 800 | GL A40 |
| 5 | smoke | Astra | 新侧 | ≤2 局（付费） | 本机 |

**已定口径（用户原话，2026-10-05～06）**：只改新接口，原版接口「尽可能保存」；所有模型都改、都做三档（不含 Astra）；第二档「原版是原版robomme 只跑hard 和修改后的xhard0对拍」；SimpleMemVLA、MME 原侧「不接受只能对比success fail 你需要重跑」；缺的原侧 GL 补跑；「不允许进行跨机的对比」；三档全部在 GL；Astra 只跑 smoke；第一、二档只出结论不阻塞；批次同号并行；GroundSG 每局都是官方录像器写的视频；上一轮产物与 v7.5eval 结果保留到本轮结束。**2026-10-06 Codex 静态审计（`STATIC_AUDIT=FAIL`，21 条，13 条代码断言已由只读子代理逐条核实）后用户裁决**：无帧错误局允许具名例外；原侧逐步比较只比共同可观察字段；预算总额改为轨迹 6366、reset 计量 14143（「Reset额度可以。提高到现在的十倍左右不用作为硬边界。」→ 账本软上限约 141430）；「唯一需要注意的就是astra还是只跑两次。」

## 二、第二档：每个模型的原侧是什么、和官方 repo 的 `main` 差在哪

两侧跑同一批 192 局（官方 test 集里 hard 难度的 12 局 × 16 任务）。**原侧** = 官方 `robomme` 环境 + 模型自己的原版评估代码；**新侧** = 我们的 `robomme_hard`（`test-hard0`）+ 我们的客户端。模型服务进程两侧一条命令。

**总结论**（2026-10-06 实际克隆四个官方仓库的 `main` 比对，不是和我们 fork 的 `main` 比）：三个模型仓库的 `main` HEAD 恰好就是我们钉死的提交，环境仓库的 `main` 之后只有文档提交。所以「原侧 vs 官方 main」的差别没有一条来自版本漂移，全部是我们自己加的驱动、清单模式和观测。

**1. GroundSG Oracle／QwenVL**（官方 `RoboMME/robomme_policy_learning`）

- 官方 `main` = `ecf086c`（2026-04-08 之后没有新提交）。原侧执行的就是这个提交里 `examples/robomme` 的类原文，用 ast 摘出来、整文件 sha256 写进结果行。**代码零差异**。
- 差别全在我们包在外面的驱动 `official_hard_runner.py`：只跑 192 局清单而不是每任务 50 局；遇 `unknown` 记 error 继续而不是中止整个评估；服务连不上探测 300 秒后停而不是无限重试；用 `results.jsonl` 加我们的重试调度代替官方 `progress.json`；加只读观测写逐步记录和帧；官方叠字 mp4 局末被删（本阶段 S1 要在新侧改回保留）。
- 环境、`max_steps=1300`、服务端 `--seed=7` 都和官方一样。
- 原侧来源：上一轮 GL 结果（Oracle 192 局齐，成功 144/192；QwenVL 只有 39 局，缺 153 局批次 1 补跑）。

**2. MME**（同一个官方仓库）

- 原侧分支 `927c56d` 的父提交就是官方 `main` 的 `ecf086c`。它只增不删，4 个文件共 299 行：`eval.py` 加 81 行清单模式，新增 `xhard0_manifest.py`、它的单测、GL 启动脚本。
- 清单模式由 `--args.episode_manifest` 开关门控，不给就是官方原来的循环。开了之后和官方不同的只有三件事：每局追加一行终态到 `episodes.jsonl`、视频在终态之后再写、支持续评。脚本层另设了 `XLA_PYTHON_CLIENT_MEM_FRACTION=0.75`。
- 这就是产出官方成绩 E0（50/192）的代码；本轮重跑 192 局，再在进程外挂只读观测器和透明代理，这些不在分支里。

**3. SimpleMemVLA**（官方 `OpenBMB/SimpleMemVLA`）

- 官方 `main` = `c564c17`（2026-09-24，整条历史只有 3 个提交）。原侧分支 `4e0c04f` 的父提交就是它，3 个文件 +324／−1，评估核心、内置环境 `robomme_sim/robomme`、`batched_policy.py`、`inproc_pool.py` 全部零差异。
- 清单模式与官方默认跑法有三处实质不同：组大小恒为 1（官方默认 2 局一组 batched 推理）；每局开头重设种子（官方整轮只设一次）；每局必录像（官方每任务只抽 1 成功 1 失败）。另加逐局终态 jsonl 和两个启动脚本。不给清单就走官方路线。
- 这就是产出官方成绩 E0（141/192）的代码；本轮重跑 192 局，再外挂观测器。

**4. PonderPounce**（官方 `worv-ai/ponderpounce`）

- 官方 `main` = `723df357`（2026-09-29，3 个提交），和子模块 gitlink 一致。vla-eval 在官方锁文件、我们的锁文件、实装 venv 三处都是 0.7.0。**代码零差异**。
- 差别全在运行方式。最实质的一条是渲染：官方一键跑用 docker 镜像里的 CPU lavapipe，我们原侧用本机 GPU 渲染，像素不会逐位一致。其余：只跑 192 局清单；固定 sid 的空操作 recorder；`EnvProxy` 和 `TracedConnection` 只读观测；我们的重试加重启服务；单连接串行而不是官方的多模拟器分片。
- 原侧来源：上一轮 GL 分片 0 共 96 局（39 成功）；分片 1 共 96 局批次 1 补跑。

**环境（四个模型共用，官方 `RoboMME/robomme_benchmark`）**

- 官方 `main` = `016ac1c`（10 月 3 日）。从我们钉的 `1fadc0ec` 到 `main` 只有 4 个提交，改的是微信二维码图和一份 PonderPounce 提交说明文档。
- `src/robomme` 目录树 sha 在 `856bc3a`（MME 子模块）、`1fadc0ec`（我们）、`main` 三点完全相同，对本仓库 `src/robomme` 做 `diff -rq` 为空。环境逻辑、test 元数据、wrapper 链官方从未改过。`vqa_options copy.py` 是官方仓库自带的杂散文件。

**一句话**：模型代码和环境代码四处都与官方 `main` 同一版本；原侧和官方一键跑的差别只有「跑哪些局、怎么记、怎么重试、怎么渲染」。

**为什么 SimpleMemVLA、MME 要外挂观测器**：GroundSG、PonderPounce 的原侧驱动是我们写的，逐步记录本来就在驱动里。SimpleMemVLA、MME 的原侧是模型自己仓库的完整入口，每局只写一行成功／失败，不许改它又要逐步对比，只能从进程外挂只读钩子复制每步数据（v7.5eval 做过、已删，本轮恢复）。观测器不改结果的证据：同一局有无观测器视频逐字节相同；MME 代理逐条消息对账 `mismatch=0`；本轮再查 SimpleMemVLA 重跑对 E0 应 0 翻转。

**交付**：每模型一行——两侧成功率、终态相同数、翻转数、McNemar p；GroundSG、PonderPounce 另给逐步一致数；SimpleMemVLA、MME 另与官方噪声带（E0／O1／O2 两两翻转：SimpleMemVLA 0、MME 7～19 局）并列。第二档是差异报告，不证明等价。

## 三、我们这一侧要改什么

现状：只有 GroundSG 的记录能直出官方版式视频；PonderPounce、Astra 格式不合；SimpleMemVLA、MME 新侧没有逐步记录。2026-10-06 Codex 静态审计另指出一批会让「跑不起来、跑到旧版本、验收假通过」的接线缺口，已核实的全部并入下表（条号指审计编号）。

| 块 | 改什么 |
|---|---|
| S0 共享契约 | 定统一的每步记录格式；动作按交给环境的原 dtype 记（审计表「动作 dtype」）；错误步计数三分：尝试步数／有效观测步数／官方录制帧数（第 7 条）；不可观察字段写「未知」且不算相同（第 11、16 条）；共享函数新参数用哨兵，`None` 只表示「模型等待中」（第 15 条） |
| S2a 重绘工具 | 改读无损原始帧，逐帧核对哈希；放行 `status=error` 的局（无帧 error 局记无视频原因） |
| S2b 席位脚本 | 解释器 `MME_PY`／`SMVLA_PY` 改成可被外部覆盖（第 1 条）；官方重绘插在合并 trace 之后、转码之前，失败则不删原始帧（第 5 条）；已有官方 mp4 要完整解码核帧数才算 `KEPT`（第 6 条）；媒体验收从冻结清单枚举、按账本接受的 attempt 定位、核来源凭据（第 9 条） |
| S1 GroundSG | 官方叠字 mp4 不删、搬进 `official/`；超时、报错、`unknown` 局补调官方 `save_video`；每份视频带来源凭据 |
| S5 PonderPounce | 服务端套外壳回传模型自己的子目标（现在记的是环境标准答案），客户端换算坐标；外壳对原类做动作、随机数、游标等价测试 |
| S4 SimpleMemVLA、MME | 补逐步记录（SimpleMemVLA 子目标写当前子任务文本；MME 子目标为空）；按三分计数 |
| S3 Astra | 接无损录像器，记录改合契约；收尾显式走重绘 → 转码 → 验收（第 10 条）；费用守卫改硬上限 5 美元：发送前同步预留、未知 usage 或守卫失联即停（第 19 条）；**仍只跑 2 局** |
| S6 对比工具 | 读 E0／O1／O2 出官方噪声带；输入绑定冻结清单、账本接受的 attempt、trace 身份与节点来源（第 14 条）；跨格式投影，执行字段与展示文本分列（第 15 条）；统计给两方向翻转、成功率差、终态矩阵、McNemar（第 21 条）；192 局全部逐步比，不再只看首局（第 20 条） |
| S7 原侧观测器 | 恢复 v7.5eval 观测器，写出与 GroundSG 原侧同格式的逐步记录；补逐步原数组与唯一 attempt 映射（第 12 条）；透明检查失败独立传播、日志封口后再对账（第 13 条）；只记共同可观察字段 |
| S8 预算与额度（新） | 账本跨原侧／新侧共享基础设施重试额度；到期中断与真实故障分别记账、仍占每身份 2 次名额（第 18 条）；原侧 SimpleMemVLA 每局按 6 次 reset 预约（第 17 条）；判定行 `BUDGET_ENFORCEMENT=` |

批次依赖也按审计第 2、3 条改：批次 3 拆成 3a（原侧重跑，等 S7）与 3b（新侧，等 S4）；每批起跑前对该批冻结提交做 CPU 客户端回放，不拿最终 HEAD 的通过覆盖早期批次。原侧代码、`third_party/`、两个原版分支零改动；共享函数的新行为默认关闭，CPU 测试证明关闭时原侧输出逐字节不变。

**逐步分叉的解释订正**（审计第 20 条，已核实）：上一轮留档写「服务端随机数跨局累积、只有起服务后第一局可逐步判」。MME 服务端每局 reset 都重置随机数，该机理不成立；实测分叉全在第 0 步动作块、输入哈希相同、连首局也只有 1/3 一致，更可能是 XLA 自动调优与 JIT 的数值非确定性（两侧确定性开关与编译缓存都默认关）。本轮五个模型 192 局全部逐步比，分叉按数值噪声报告。

## 四、验收

| 查什么 | 判定行 |
|---|---|
| 每批起跑输入（依赖集合、冻结 sha、解释器与导入路径、清单） | `RUN_INPUTS=PASS batch=<n> frozen=<sha> deps=<S…>`；缺依赖 `RUN_BLOCKED reason=missing_dependency` |
| 预算执行 | `BUDGET_ENFORCEMENT=PASS`（原侧每局预约 6；共享 infra 额度；到期与故障分账） |
| 记录格式 | `TRACE_CONTRACT=PASS routes=6` |
| 原侧不变 | `ORIG_SIDE_UNCHANGED=PASS`、`ORIG_FILES_UNCHANGED=PASS`、`ORIG_BRANCH_PIN=PASS` |
| 接线不改策略行为（每批、对该批冻结提交） | `CLIENT_REPLAY_EQ=PASS base=<sha> candidate=<sha> route=<r> request_diff=0 action_diff=0 control_diff=0 terminal_diff=0` |
| PonderPounce 外壳不改动作 | `PP_SERVER_ACTION_EQ=PASS` |
| 观测器完整且不改结果 | `OBSERVER_COMPLETE=PASS`（MME 每片，含透明对账）；`ORIG_RERUN_VS_E0 … flips=0`（SimpleMemVLA） |
| 逐步证据齐全 | `TRACE_COMPLETE=PASS`（已接受身份全有合规 trace） |
| 第二档输入与来源 | `GATE2_INPUTS=PASS expected=192 missing=0 extra=0 unaccepted=0 trace_binding_mismatch=0`；`GATE2_PROVENANCE=PASS local_rows=0 unknown_rows=0` |
| 每局一份官方视频 | `OFFICIAL_MEDIA_INPUTS=PASS missing=0 extra=0 identity_mismatch=0 attempt_mismatch=0 provenance_missing=0`；`OFFICIAL_MEDIA=PASS total=<n> skip=0 fail=0 no_frame_error=<n>`（无帧 error 局具名例外，用户 2026-10-06 裁决） |
| 第一档 | `GEN_REGRESS=PASS|FAIL`（不阻塞） |
| 第二档 | 每模型 `GATE2=INFO compared=192 …`（差异报告） |
| 第三档 | 每模型 `EVAL_COVERAGE=PASS unique_terminal=800`、`VIDEO_SAVED=PASS`、`OFFICIAL_MEDIA=PASS total=800` |

## 五、步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 用户说「开工」 | — |
| 1 | 批次 1 上 GL（QwenVL 命令带 `--episode-wall 3600`） | `GEN_REGRESS=`；补跑分片 `outcome=pass` 且补集合恰等于差集 |
| 2 | 本机改代码：S0 → 9 个子代理 → 逐个合并、审两次、push | `PRE_MERGE_REVIEW=PASS`、`POST_MERGE_REVIEW=PASS` |
| 3 | 每批起跑前：`RUN_INPUTS`、该批路线 `CLIENT_REPLAY_EQ`、本机 1 局 smoke | 三项 PASS 才起 |
| 4～6 | 批次 2、3a、3b、4 依次上 GL | 每模型 `GATE2_INPUTS`、`GATE2=INFO`、`OFFICIAL_MEDIA=PASS` |
| 7 | 批次 5 Astra 本机 smoke | ≤2 局、≤5 美元硬上限 |
| 8 | 留档、commit、push、按清单 `scancel` | `result.md` 落盘 |

## 六、子代理分工与合并（简述）

主会话写 S0 后同一时刻派九个写入型子代理（S2a、S2b、S8、S1、S6、S7、S4、S5、S3），各管互不重叠的文件、各在自己的 worktree 写；合回顺序 S2a → S2b → S8 → S1 → S6 → S7 → S4 → S5 → S3，每合一个审两次、push 一次。S1 合完即可开批次 2，不等后面几块。

逐模型的原侧来源、与上游原版的逐项差异、观测器怎么挂、六条路线现状、官方 `main` 比对等细节见第二部分八节。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线与共享契约

**红线**

- R1 原侧零改动：`scripts/eval-official/{official_hard_runner.py,official_defs.py,pp_official_runner.py,run_official_hard.sh,pair_seat.sh}`、`third_party/**`、SimpleMemVLA 分支 `official-xhard0-0929`（`4e0c04f`）与 MME 分支 `official-xhard0-0929`（`927c56d`）的文件（检出后 `git status --porcelain` 必须为空）、`src/robomme/`（P2）、`scripts/` 顶层四入口（P1）零 diff。
- R2 共享代码（`mmesg_client.py`、`pp_client.py`、`trace_writer.py`、`recorder.py`、`run_seat.sh`、`env_client.py`）的新行为一律由显式参数或环境变量打开，默认保持 `BASE` 行为；新增可选参数用哨兵 `_UNSET`，不得用 `None` 同时表示「未提供」与「模型等待中」。
- R3 官方 `RolloutRecorder` 不复制、不改写；GroundSG 只调用官方实例的 `save_video`；其余路线经 `render_official_video.py` 以 `importlib` 加载官方类。
- R4 `episode.mp4` 口径、`video_check.py`、`eval_video_mover.py` 不改；官方版式文件一律放 `official/`。
- R5 第一阶段产物（重绘工具既有 16 个用例、站点、`sg-eval-gl-20261004-01/` 留档）不回滚；重绘工具只做向后兼容的重构。
- R6 预算按六节：轨迹 ≤6366；reset 软上限约 14 万（用户 2026-10-06：「Reset额度可以。提高到现在的十倍左右不用作为硬边界。」），账本以它做失控保护、不做精确闸门；**Astra 只许本机 smoke ≤2 局、5 美元硬上限**（用户同日：「唯一需要注意的就是astra还是只跑两次。」）。
- R7 只读输入，到本轮结束不删不移：`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/sgeval-20261004/`、`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v7-eval/`（E0）、`artifacts/v7.5eval/`（O1、O2 与身份清单）。
- R8 第二档原侧只取 GL A40 结果（物理节点可不同，环境指纹与节点名入表）；合表逐行核来源节点，出现非 GL 来源即 `GATE2_PROVENANCE=FAIL`，该模型 `GATE2=INVALID reason=cross_machine`。
- R9 子代理 worktree 内只跑 CPU 定向测试：`UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <定向> -q`，先打印 `robomme_hard.__file__` 确认在 `<worktree>/src/`。
- R10 每批起跑绑定依赖集合与冻结 sha：批次 2 需 {S0,S2a,S2b,S8,S1}，3a 需 {S0,S2a,S2b,S8,S7}，3b 需 {S0,S2a,S2b,S8,S4}，4 需 {…,S5}，5 需 {…,S3}；第二档对比另需 S6。启动检查缺任一即 `RUN_BLOCKED reason=missing_dependency missing=<S…>`；每批起跑前对该批路线做 `CLIENT_REPLAY_EQ base=<BASE> candidate=<该批冻结 sha>`，最终 HEAD 的通过不覆盖早期批次。
- R11 原侧 SimpleMemVLA 内部 reset 重试（`SimEnvService` 默认 `reset_retries=2`）不关闭、不改 E0 口径；账本按每局 build+reset 各 1 次 × 最多 3 次尝试 = 6 次预约。

**共享契约 C1～C11**（S0 写进 `trace_writer.py` 文档串与测试助手；字段以 `render_official_video.load_trace` 现行要求为准，S2a 按 C3、C4、C8 扩展）

- C1 新侧 `route` 一律 `<模型>/new`：`mmesg/<variant>/new`（已符合）、`pp/new`、`astra/new`、`smvla/new`、`mme/new`；原侧 `<模型>/orig`。
- C2 演示段记全部 reset 帧（含最后一帧初始画面），`len(states) == frames`；收尾 `close(..., demo_frames=<演示帧数，不含初始帧>)`，满足 `demo.frames == end.demo_frames + 1`。
- C3 `status` 与 `terminal_reason` 取 `success`／`fail`／`timeout`／`error`；strict-cap 命中一律 `timeout`；`error` 局允许无帧（`no_frame=true`），重绘器对无帧局记原因不出视频。
- C4 每步记执行后的画面、状态、动作与当步子目标；动作按**实际交给环境的原 dtype／shape／bytes** 记录，不为契约转换；非 float32 动作原值写同目录 `arrays.npz`（键 `exec_action__%05d`，按步编号）。
- C5 `trace.jsonl`、`arrays.npz`、原始帧同一目录。
- C6 identity 含 `source_episode` 或 `builder_episode`、与局目录名 `<key>.a<N>` 一致的 `key`，以及 `attempt`；`attempt` 必须等于账本 `accepted_attempt_id` 对应的尝试号。
- C7 子目标为 `None`（模型等待中）的等待帧在官方录像时以 `[initializing...]` 占位；轨迹里保留原始 `None`；没有子目标功能的路线（MME）不出现子目标栏。
- C8 计数三分：`steps_attempted`（交给环境的步数，含异常步）、`steps_observed`（返回有效观测的步数）、`frames_recorded`（官方实际录制帧数 = demo + 1 + observed − omitted）；三者分别写 `end`，与结果行 `exec_steps`（= attempted）对账；缺观测步保留步号、动作与原因，不删不补。
- C9 两侧不可同时观察的字段（原侧的 `terminated`／`truncated`、请求与完整动作块等）写 `NOT_OBSERVED`；比较器不把双 `NOT_OBSERVED` 算相同，按维度报 `not_observed=<n>`（用户 2026-10-06 裁决「只比共同可观察字段」）。
- C10 请求／响应／历史边界行按模型定义「共同逻辑输入」：GroundSG、PonderPounce、MME 两侧同协议可比原始哈希；SimpleMemVLA 原侧内嵌、新侧 websocket，只比逻辑输入（指令、状态、帧哈希序列）与完整动作块，不比原始通信字节。
- C11 `end` 带 `observer_hook_errors=<n>`；大于 0 时该局 `TRACE_COMPLETE` 计失败，但不影响任务成绩。

S0 同时提交测试助手 `tests/pipeline/evalx/report/trace_contract.py::assert_renderable(ep_dir)` 与 `assert_counts_consistent(ep_dir, result_row)`。

## 一、逐文件改动清单

**S1 GroundSG 新侧**（`scripts/eval-official/mmesg_client.py`）
- 新增 `OFFICIAL_VIDEO_SUBDIR = "official"`、`keep_official_videos(video_dir, dst) -> list[str]`：搬入前完整解码、核帧数等于 `frames_recorded`、核恰一个文件；写 `official/provenance.json`（identity、route、dataset、attempt、终态、`official_sha256`、视频 sha256、帧数依据、`official_source`）。
- `run_official_episode` 新增 `keep_official=_UNSET`：开启时调用前包一层 `evaluator.init_episode` 捕获 `(task_goal, recorder)`；`except` 分支与 `flag == "unknown"` 时若 `video_dir` 无 mp4，按 `f"{runner.env_id}_ep{runner.episode_id}_{flag}_{task_goal}_{runner.difficulty}.mp4"`（`safe_filename` 同款截断）调用 `recorder.save_video`，成功后同样解码核帧；失败只记 `official_save_error`，保留原始帧；`init_episode` 中途失败已录的部分帧按 `partial` 记原因（审计第 8 条），不冒充完整视频；`finally` 在 `rmtree(video_dir)` 前搬入 `archive_dir/official/`；返回加 `official_videos`、`official_source`（`official`／`official-salvaged`／`partial`／`none`）；包装在 `finally` 还原。
- 新侧 `run_episode` 传 `keep_official=True`；原侧不传（R1、R2）。
- 测试 `tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py`：正常局 1 个 mp4 含 `ep3a1_` 且 provenance 齐；strict-cap、异常、`unknown` 各 1 个且 `official-salvaged`；截断 mp4、错帧数、多片必须拒绝 `KEPT`；`init_episode` 前失败为 `none`；`keep_official` 不传时与 `BASE` 逐字节一致。

**S2a 重绘工具**（`scripts/eval-official/render_official_video.py`）
- `render_episode` 重构为「来源选择 → 解码 → 核验 → 录像 → 复核」：来源 `mp4`／`raw-new`（`front.mkv`、`wrist.mkv` + `frames-<stream>.jsonl` 的 `enc` 展开）／`raw-orig`（`frames/{front,wrist}.rgb24` + `frames.json`），展开规则照 `run_seat.sh::transcode_episode_dir` 文档串；CLI 新增 `--source {auto,mp4,raw}`、`--key <key>`（Astra 等目录名不含 key 时显式给）；`raw` 模式下缺流、索引损坏、重复索引、有损降级一律失败、不退回 mp4。
- `load_trace` 按 C3、C4、C8 扩展：放行 `status=error`；帧数由 `frames_recorded` 与真实索引推导，缺观测步不补帧；动作 dtype 按原值核对 `arrays.npz`；无帧 error 局返回 `no_frame` 结果、不出视频、`render.json` 记原因。
- 每路流与索引文件算 sha256 进 `render.json` 与复用上下文（相对路径记录，目录搬到 NFS 后仍可核）；逐帧比对解码画面哈希与 `trace` 记录哈希；`PASS` 行加 `source_kind=`。
- 测试 `tests/pipeline/evalx/report/test_sgx_render_official_video.py`：无 mp4 的无损夹具通过；调包流、错 `enc`、缺帧、重复索引、改 raw 后复用五个反例失败；raw 删除后重入走复用；普通异常、无观测返回、自然超时、strict-cap 四种局的结果、trace、媒体计数一致；既有 16 个用例不变。

**S2b 席位与官方视频验收**
- `run_eval_gl.sh`：`BENCH_PY`／`MME_PY`／`SMVLA_PY` 改为 `"${X:-默认}"`（审计第 1 条，现为无条件覆盖）；起跑打印五个解释器与 `python -c "import robomme_hard,sys;print(robomme_hard.__file__)"`、各服务 venv 的 editable 指向，写 `RUN_INPUTS=` 行；导出 `SGEVAL_OFFICIAL_RENDER=1`、`SGEVAL_PP_SERVER_WRAP=1`；`--episode-wall` 三参数透传已存在，不改。
- 新文件 `scripts/eval-official/seat_media_lib.sh`（只含函数）：从 `run_seat.sh` 移入 `transcode_episode_dir`；新增 `render_official_dir`（`--source raw --jobs 1`，ffmpeg 与转码同源解析；已有 `official/*.mp4` 时先完整解码、核帧数与 provenance，通过才打印 `OFFICIAL_RENDER=KEPT`，否则重绘到临时名后原子替换）。
- `run_seat.sh`：`source seat_media_lib.sh`；在 `finish_episode_dir` 合并 trace 之后、`transcode_episode_dir` 之前，仅当 `SGEVAL_OFFICIAL_RENDER=1` 调 `render_official_dir`（审计第 5 条）；失败则本局**跳过删 raw 的分支**（给 `transcode_episode_dir` 传 `--keep-raw`）、写 `official-render.failed`、照常发布成绩；`start_server` 的 pp 分支在 `SGEVAL_PP_SERVER_WRAP=1` 时以**绝对路径**起 `scripts/eval-official/pp_server_wrap.py`（cwd 在第三方目录，审计表「外壳启动路径」）。
- 新文件 `scripts/eval-official/official_media_check.py`：从冻结清单枚举全部身份，按账本 `accepted_attempt_id` 定位局目录，核 `official/` 恰 1、可解码、帧数等于 `frames_recorded`、provenance 的 identity／route／dataset／attempt／视频 sha 一致；输出 `OFFICIAL_MEDIA_INPUTS=PASS missing=0 extra=0 ambiguous=0 identity_mismatch=0 attempt_mismatch=0 provenance_missing=0` 与 `OFFICIAL_MEDIA=PASS total=<n> skip=0 fail=0 no_frame_error=<n>`，另写 `official-media.jsonl`。
- 测试：`tests/pipeline/eval/test_seat_scripts.py`（真实小型无损帧夹具走完整收尾链：调用顺序、重绘失败后原帧指纹保留、重入恢复、`official/*.mp4` 出现、`episode.mp4` 仍恰一个；解释器环境变量经 `source` 与参数解析后原样保留）；新文件 `tests/pipeline/eval/test_official_media_check.py`（缺失、重复、失败、帧数不符、调换两局视频、换成普通录像、错 attempt、等数量替换身份均 FAIL；无帧 error 局计入 `no_frame_error` 不计 `fail`）。

**S3 Astra 新侧**（`scripts/eval-official/astra_hard_runner.py`、`run_astra.sh`、`astra_cost_guard.py`）
- route `astra/new`，identity 补 `builder_episode`、`key`、`attempt=1`，演示与收尾按 C2、C3、C8。
- 目录：保留 Astra 原有 `<RUN>/results/<task>/ep<NNN>/`，在其下新建 `<key>.a1/`（`media/`、`trace.jsonl`、`arrays.npz`、`official/`），`result.json` 加 `media_dir` 映射；`run_one` 首次 reset 时建 `recorder.EpisodeRecorder(<key>.a1/media, meta)`（`media/` 新建且为空，禁止 `overwrite=True`；meta 取 `env_client.SeatRunner` 同款字段并 `never_degrade=True`）；`TracedEnv` 只 `add_frames`／`add_array`；`run_one` 的 `try/finally` 统一 `close(summary)`。
- `run_astra.sh`：`source seat_media_lib.sh` 后在每局收尾**显式**调 `render_official_dir` → `transcode_episode_dir` → `official_media_check.py`（审计第 10 条）；显式设 `BENCH_PY`／`TOOL_PY`。
- 费用硬上限（审计第 19 条）：`astra_cost_guard.py` 加 `--cap 5` 为本轮固定值、`--interval 2`、缺 usage 视为超限并写 STOP；`astra_hard_runner.py` 内子类化 `ResponsesClient`（第三方文件零改动），覆写 `_send`：发送前同步读守卫状态文件并原子预留「单次最坏费用」（输入按本次实际 token 估、输出按 `max_output_tokens`），预留失败、守卫心跳超时 10 秒、STOP 存在三者任一即拒发；等待间隔结束后再检一次 STOP；**局数硬上限 2**（R6）。
- 测试 `tests/pipeline/evalx/astra/test_astra_wiring.py`：帧数口径、`assert_renderable`、`--key` 映射、source 后 `MAX_STEPS` 与 `trap` 不变；零外联夹具覆盖首次大输入、输入增长、usage 缺失、STOP 在等待中到达、守卫崩溃，被拒请求不得触发实际发送；CPU 夹具驱动真实启动器收尾生成一份官方视频与一份普通视频，失败时保留原帧。

**S4 SimpleMemVLA 与 MME 新侧**
- `smvla_client.py`：`step_chunk` 新增 `on_obs(step, front, wrist, state, terminated, truncated)` 回调（一步多帧取最后一帧）；`run_episode` 建 `TraceWriter(route="smvla/new")`，演示按 C2；决策回包的子任务文本（`smvla_server.py` `infer` 回包键 `subtask`，2026-10-06 已逐字核对）作当前子目标，在 `on_obs` 里 `log_step`；逻辑输入（指令、状态、帧哈希序列）与完整动作块 `actions_full` 按 C10 记 `request`／`response` 行；strict-cap 按 `timeout` 关闭；异常步按 C8 记 `steps_attempted` 不记观测。
- `mme_client.py`：在 `run_episode` 内包一层 `session.step` 钩子拿完整五元组，`reset_fn` 外包一层记演示；`TraceWriter(route="mme/new")`、`subgoal=None`（无子目标功能，C7）；`EnvRunnerShim` 返回 `(None, None, None)` 的步记为缺观测步（步号、动作、原因），不删；`add_buffer`／`infer` 请求与回包按 C10 记原始哈希；收尾按 C2、C3、C8。
- 测试 `tests/pipeline/eval/test_policy_clients.py`：两路线 `assert_renderable`、`assert_counts_consistent`；smvla 步数行 = 执行步数且子目标非空；mme 子目标全 `None`；strict-cap 局 `timeout`；异常步三分计数一致。

**S5 PonderPounce 新侧**
- 新文件 `scripts/eval-official/pp_server_wrap.py`：子类化 `ponderpounce.eval.robomme_server.PonderPounceRoboMMEServer`（不改原文件）；覆写 `_fire_s1`：调用父类前取 `_visible_cognition(ep, now)`，维护本局「最近一个已可见且非空的子目标」，父类生成 `ep.chunk` 后挂到 chunk 上；覆写 `_dispense`：结果加 `"subgoal": <chunk 上的子目标> or None`（hold 为 `None`）；入口 `run_server(<子类>)`。
- `pp_client.py`：新增 `pp_subgoal_to_official(text)`：每组 `at [x, y]`（0～1000）→ `at <round(y*255/1000), round(x*255/1000)>`，夹到 0～255；`TracedConnection.act` 存 `last_subgoal`；新侧 `trace_step` 加 `subgoal=_UNSET`（R2，默认不写新字段）；新侧 `subgoal` 写模型文本，环境标准答案改记 `history` 行 `note=oracle_simple_subgoal:<文本>`；route、演示、收尾按 C1～C3、C8；原侧不传新参数。
- 测试：`tests/pipeline/evalx/pp/test_pp_protocol_wire.py`（`at [612, 247]` → `at <63, 156>`、0～255 全量往返、多组坐标、越界、`None`、回包 `subgoal` 进轨迹、`assert_renderable`、原侧不传参数时序列化输出与 `BASE` 逐字节一致）；新文件 `tests/pipeline/evalx/pp/test_pp_server_wrap.py`（`ready_at_ns` 之前回旧子目标、chunk 耗尽时不变、首个子目标前 `None`；锁定父类真实方法配 CPU backend，对原类与外壳比较动作、RNG 消耗、`cursor`、触发计数，除新增 `subgoal` 字段外一致，输出 `PP_SERVER_ACTION_EQ=PASS`）。

**S6 第二档对比工具扩展**（`scripts/eval-official/gate2_compare.py`）
- 输入绑定（审计第 14 条）：新增 `--manifest <冻结清单>`、`--new-ledger <账本>`、`--orig-attempts <原侧 attempt 映射>`；每侧每身份只取账本接受的 attempt（新侧 `accepted_attempt_id`，原侧 S7 适配器给出的唯一 attempt）；`TraceIndex.lookup` 核 trace header 的 identity 与 `attempt` 等于结果行；节点来源读结果行 `node`，非 GL 节点计 `local_rows`；输出 `GATE2_INPUTS=PASS expected=192 missing=0 extra=0 unaccepted=0 ambiguous=0 trace_binding_mismatch=0` 与 `GATE2_PROVENANCE=PASS local_rows=0 unknown_rows=0`，任一 FAIL 则 `GATE2=INVALID`。
- 补集合核对：旧原侧合表 + 本轮补跑按身份集合与清单比，QwenVL 补 153 局、PonderPounce 补 96 局必须恰等于差集，不凭条数。
- 跨格式投影（审计第 15、16 条）：执行动作、画面、状态、逻辑输入、展示文本分维度各报 `same/diff/not_observed`，不在首个差异处停止；`NOT_OBSERVED` 不算相同（C9）。
- 统计（审计第 21 条）：每模型输出 `s2f`、`f2s`、`sr_orig`、`sr_new`、`sr_diff_pp`、终态 3×3 矩阵、McNemar p；`--orig-format v75` 读 E0 逐局文件（读前按 `artifacts/v7.5eval/input-manifest.json` 核 sha256），`--noise-runs <O1> <O2>` 输出 E0／O1／O2 三对的两方向翻转作**描述性历史观测**，不写「相当」。
- 去掉「只有首局可逐步判」的设计假设（审计第 20 条）：`--groundsg` 改为诊断列 `server_epoch_first=<bool>`，192 局全比。
- 测试新文件 `tests/pipeline/eval/test_gate2_v75.py`、`tests/pipeline/eval/test_gate2_inputs.py`（假清单／账本／两侧结果：对齐、缺对 `INCOMPLETE`、未接受行 `unaccepted`、trace 身份不符、非 GL 行 `INVALID`、sha 不符报错、「执行相同记录格式不同」零误报、「文本不同且动作错」仍报动作差异、默认格式输出与 `BASE` 逐字节相同）。

**S7 SimpleMemVLA、MME 原侧观测器**（新目录 `scripts/eval-official/orig_observer/`）
- 从 `27d209d5^:scripts/eval-official/official_observer/` 恢复全部 8 个文件：`_v75_obs_common.py`（改名 `_obs_common.py`）、`smvla_wrap.py`、`mme_client_wrap.py`、`mme_proxy.py`、`transparency_check.py`、`official_rerun_shard.sh`、`run_official_smvla.sh`（改名 `run_orig_smvla.sh`）、`run_official_mme.sh`（改名 `run_orig_mme.sh`）。恢复后先 `git diff 27d209d5^:<原路径> <新路径>` 记录逐处改动。**允许修改范围**（放宽旧「只改输出目录」，审计第 13 条）：输出目录与格式、身份／完整性绑定、日志封口、失败传播、attempt 映射、预算预约；**不许**改转发载荷与原版调用参数。
- 钩子写出改为本仓库 `trace_writer.TraceWriter`（route `smvla/orig`、`mme/orig`，identity 取清单行的 `task`、`source_episode`、`seed`，`key` 按上一轮 xhard0 分片的 key 对上，`dataset="test-hard0"`，`attempt` 按下条映射）与 `mmesg_client.RawFrameWriter`，局目录 `<out>/<key>.a<N>/`，字段与 `official_hard_runner.run_identity` 写出的原侧一致（C2、C3、C8）；原侧不可见字段（`terminated`／`truncated`）写 `NOT_OBSERVED`（C9）。
- 新增 `step_arrays.py`（审计第 12 条）：在 `InProcSimPool.step`／`EnvRunner.step` 钩子里只复制主机端 numpy，把每步实际交给环境的动作行按 `exec_action__%05d` 累积，局末 `np.savez` 到 `arrays.npz`；SimpleMemVLA 按 `consumed` 截取动作块的前 `consumed` 行逐步落键。
- 新增 `orig_results_adapter.py`：读原版 `episode_log`（SimpleMemVLA）／`episodes.jsonl`（MME），对每个 `(task, source_episode)` 取**最后一条终态行**为权威，分配唯一 attempt（按该身份出现顺序编号），输出 `orig-attempts.json` 供 S6 `--orig-attempts`；孤儿目录（有目录无终态行）记 `orphan`，不进比较。
- 钩子铁律照旧：只复制主机端 numpy、不调随机函数、不做 GPU 运算、不改参数与返回值，钩子内异常只记 `OBSERVER_HOOK_ERROR` 并累加 `observer_hook_errors`（C11）。
- `run_orig_mme.sh`：代理收尾改为 `kill -TERM` 后等到进程退出（上限 900 秒，超时 `kill -9` 并记 `proxy_force_killed`）、PID 不清空直到确认退出；日志封口（代理写 `proxy-<pid>.done`）后才跑 `transparency_check.py`；对账结果写 `observer-status.json`，与评估退出码分开：末行 `OBSERVER_COMPLETE=PASS|FAIL episodes=<n> conns=<n> mismatch=<n> hook_errors=<n> report=<ok|missing|crashed>`，评估 `EXIT_CODE=` 保持原语义。`transparency_check.py` 加 `--manifest`、`--episodes`：每个清单身份必须对应到至少一条连接与一局 `trace.jsonl`，缺即 FAIL。
- `run_orig_smvla.sh`：`REPO` 默认 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA-official-xhard0`（本轮由主会话 `git worktree add` 检出 `4e0c04f`；该 NFS 仓库工作区当前在 `testhard-eval-v7-0929` 分支，旧工作树已不存在，不得直接用工作区文件），解释器 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA/.venv-robomme/bin/python`，权重 `.../SimpleMemVLA/checkpoints/simplememvla_robomme`；起跑断言 `git -C $REPO rev-parse HEAD` = `4e0c04f…`、工作树干净；每局起跑前调 S8 的 `budget_ledger.py reserve --resets 6`（R11），余额不足即 `RUN_BLOCKED reason=budget`。
- `run_orig_mme.sh` 环境：`REPO` 默认 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-official-xhard0`（本轮由主会话从 `/data/hongzefu/robomme_policy_learning_MotionJEPA` 的 `origin/official-xhard0-0929` 克隆到 NFS，`git submodule update --init third_party/robomme_benchmark`）；客户端解释器取环境变量 `ORIG_MME_CLIENT_PY`（默认本轮执行副本 `scripts/eval-official/client-env` 的 venv），服务端取 `MME_PY`；起跑断言提交 `927c56d…`、子模块 `856bc3a…`、`robomme.__file__` 在原版子模块 `src/` 下、`robomme_hard` 未导入；每局预约 `--resets 2`。
- 测试新文件 `tests/pipeline/evalx/orig_observer/test_orig_observer.py`（假 `InProcSimPool`、假 `EnvRunner`、假 websocket：钩子不改返回值、写出的 trace 与 `arrays.npz` 过 `load_trace` 与 `gate2_compare` 读取、float64 精度、部分动作块、错误后成功、孤儿目录、重复终态、续跑；钩子异常不外抛但 `observer_hook_errors` 递增；注入对账 FAIL／检查器崩溃／缺报告／封口超时时任务成绩不变而 `OBSERVER_COMPLETE=FAIL`；启动器在提交不符或工作树脏时 `RUN_BLOCKED`）。

**S8 预算与额度**（`scripts/eval-official/env_client.py`、新文件 `scripts/eval-official/budget_ledger.py`）
- `AttemptLedger`：基础设施重试额度改为**跨原侧／新侧共享**的持久账本（文件锁，原子领取，并发只一方成功）；新增中断分类 `expired`（有 Slurm 到期证据）与 `infra`（其他），两者都占每身份 `V8_MAX_ATTEMPTS=2` 名额、分别计数，`recover_dangling` 按证据分类而不是一律 infra；重启、换节点不刷新额度；正常 `fail`／`timeout`／`error` 不重评。
- 新文件 `budget_ledger.py`（CLI）：`reserve --resets <n>`／`commit`／`release`／`report`；账本总量：轨迹 6366 硬上限、reset 软上限 141430（R6，超过只告警不拦）、Astra 局数 2 硬上限；S7 启动器与新侧 `EnvSession._claim` 都经它领取；末行 `BUDGET_ENFORCEMENT=PASS trajectories=<used>/<cap> resets=<used>/<soft> astra=<used>/2 shared_infra=<used>/<cap>`。
- 第一档 `noise_run_gl.sh` 的预算参数只作预约；留档写明实际 reset 计数口径为 `unknown` 时不写成「已测量」。
- 测试新文件 `tests/pipeline/eval/test_budget_ledger.py`：并发争抢最后一个额度仅一方成功；前两次 reset 失败第三次成功的夹具记满 6；余额不足进入 attempt 前拒绝；到期与故障分账；Astra 第 3 局拒绝；默认不传新参数时 `AttemptLedger` 行为与 `BASE` 逐字节相同。

**主会话**：S0；新增测试文件如需登记 `tests/contract/benchmark_contracts.json` 由主会话改；回放脚本 `scripts/eval-official/client_replay_eq.py`（固定观测与固定服务回包下比较 `base` 与 `candidate` 两个 worktree 的客户端：完整请求、交给环境的动作 dtype／shape／bytes、调用顺序、步数、终态；新增记录与媒体字段列入允许差异；每批对该批路线跑，另证明故意改动作／请求／顺序会 FAIL）；留档。

## 二、子代理分配表

`BASE` = S0 提交后的 HEAD。

| 子任务 | 目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖 | 合并顺序 | 验收命令与判定行（worktree 内，R9 环境） | 资源 | 共享文件归属 |
|---|---|---|---|---|---|---|---|---|
| S0 | 共享契约与测试助手 | `trace_writer.py`（仅文档串）、`tests/pipeline/evalx/report/trace_contract.py` | R1 | C1～C11 | 派发前 | 主会话自做：`pytest tests/pipeline/evalx/report -q` | CPU | 主会话 |
| S2a | 重绘工具重构 | `render_official_video.py`、`tests/pipeline/evalx/report/test_sgx_render_official_video.py` | R1、其余 `scripts/eval-official/*` | CLI 向后兼容；`--source`、`--key`、`source_kind`；C3、C4、C8 | 1 | `pytest tests/pipeline/evalx/report -q` passed | CPU ≤5 分钟 | 无 |
| S2b | 席位函数库、解释器覆盖与视频验收 | `seat_media_lib.sh`（新）、`run_seat.sh`、`run_eval_gl.sh`、`official_media_check.py`（新）、`tests/pipeline/eval/test_seat_scripts.py`、`tests/pipeline/eval/test_official_media_check.py`（新） | 同上 | `render_official_dir`、`transcode_episode_dir --keep-raw`；`SGEVAL_OFFICIAL_RENDER`、`SGEVAL_PP_SERVER_WRAP`；`${X:-}` 解释器 | 2 | `pytest tests/pipeline/eval/test_seat_scripts.py tests/pipeline/eval/test_official_media_check.py -q` passed | CPU | `run_seat.sh`、`run_eval_gl.sh` 唯一写者 |
| S8 | 预算与额度 | `env_client.py`、`budget_ledger.py`（新）、`tests/pipeline/eval/test_budget_ledger.py`（新） | 同上 | `AttemptLedger` 共享额度、`expired`／`infra` 分类；CLI `reserve/commit/release/report` | 3 | `pytest tests/pipeline/eval/test_budget_ledger.py tests/pipeline/eval/test_env_client*.py -q` passed | CPU | `env_client.py` 唯一写者 |
| S1 | GroundSG 新侧 | `mmesg_client.py`、`tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py` | 同上 | `keep_official=_UNSET`；provenance.json | 4 | `pytest tests/pipeline/evalx/groundsg -q` passed | CPU | 无 |
| S6 | 第二档对比工具 | `gate2_compare.py`、`tests/pipeline/eval/test_gate2_v75.py`（新）、`tests/pipeline/eval/test_gate2_inputs.py`（新） | 同上 | `--manifest`、`--new-ledger`、`--orig-attempts`、`--orig-format`、`--noise-runs`；C9、C10 | 5 | `pytest tests/pipeline/eval/test_gate2_v75.py tests/pipeline/eval/test_gate2_inputs.py -q` passed | CPU | 无 |
| S7 | 原侧观测器 | `scripts/eval-official/orig_observer/**`（新）、`tests/pipeline/evalx/orig_observer/test_orig_observer.py`（新） | 同上 + 两个原版分支的所有文件 | trace 格式同 `official_hard_runner.run_identity`；`orig-attempts.json`；`OBSERVER_COMPLETE`；调用 S8 CLI（只读接口） | 6 | `pytest tests/pipeline/evalx/orig_observer -q` passed | CPU | 无 |
| S4 | SimpleMemVLA、MME 新侧 | `smvla_client.py`、`mme_client.py`、`tests/pipeline/eval/test_policy_clients.py` | 同上 | 只读 `trace_writer`、`mmesg_client.trace_location`；C8、C10 | 7 | `pytest tests/pipeline/eval/test_policy_clients.py -q` passed | CPU | 无 |
| S5 | PonderPounce 新侧 | `pp_client.py`、`pp_server_wrap.py`（新）、`tests/pipeline/evalx/pp/test_pp_protocol_wire.py`、`tests/pipeline/evalx/pp/test_pp_server_wrap.py`（新） | 同上 | 回包键 `subgoal`；`pp_subgoal_to_official`；`subgoal=_UNSET`；`PP_SERVER_ACTION_EQ` | 8 | `pytest tests/pipeline/evalx/pp -q` passed | CPU | 无 |
| S3 | Astra 新侧 | `astra_hard_runner.py`、`run_astra.sh`、`astra_cost_guard.py`、`tests/pipeline/evalx/astra/test_astra_wiring.py` | 同上 | `<key>.a1/` 映射；显式收尾链；`--cap 5` 硬上限；≤2 局 | 9 | `pytest tests/pipeline/evalx/astra -q` passed | CPU | 无 |
| 运行型 R1～Rn | 按三节批次在 GL 席位启动 `run_eval_gl.sh`／`run_official_hard.sh`／`run_orig_*.sh` | 无 | 一切代码 | 命令原文照四节 runbook；起跑前主会话已出 `RUN_INPUTS=PASS` 与该批 `CLIENT_REPLAY_EQ=PASS` | 开工后 | 起跑判据 `SEAT_START`／`ROUTE_START` + 首局 `REC_TRANSCODE … result=ok` + 首局 `OFFICIAL_RENDER=` | GL 席位 | 账目归主会话 |

派发前核对：`worktree.baseRef=head`；`git check-ignore -q .claude/worktrees/probe`；`git worktree list` 存档，既有 worktree 不动；`git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'` 为空。

## 三、闸门总表

| 闸门 | 命令 | 判定行 |
|---|---|---|
| 核心短测（每次合并后） | `timeout 280s uv run --no-sync python -m pytest -m 'not slow' -q` | passed、`TEST_RESOURCE=PASS`、`TEST_INVENTORY=PASS` |
| 项目闸门 | `ls -1 scripts/*.py`；`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`；`uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | 四入口；零 diff；`UPSTREAM_GUARD=PASS` |
| 原侧零改动 | `git diff --quiet <BASE> HEAD -- scripts/eval-official/{official_hard_runner.py,official_defs.py,pp_official_runner.py,run_official_hard.sh,pair_seat.sh} third_party`；两个原版工作树 `git rev-parse HEAD` 与 `git status --porcelain`；原侧入口关闭态夹具的返回键、序列化 trace、argv／env、媒体与清理行为对 `BASE` 逐字节比 | `ORIG_FILES_UNCHANGED=PASS`、`ORIG_BRANCH_PIN=PASS smvla=4e0c04f mme=927c56d dirty=0`、`ORIG_SIDE_UNCHANGED=PASS` |
| 每批起跑输入 | `run_eval_gl.sh` 起跑段 + 主会话脚本核依赖集合与冻结 sha | `RUN_INPUTS=PASS batch=<n> frozen=<sha> deps=<S…> interpreters=ok imports=ok`；缺依赖 `RUN_BLOCKED reason=missing_dependency` |
| 预算执行 | `budget_ledger.py report` | `BUDGET_ENFORCEMENT=PASS trajectories=<u>/6366 resets=<u>/141430(soft) astra=<u>/2 shared_infra=<u>/<cap>` |
| 客户端回放（每批） | `client_replay_eq.py --base <BASE> --candidate <该批冻结 sha> --routes <该批路线>` | `CLIENT_REPLAY_EQ=PASS base=<sha> candidate=<sha> route=<r> request_diff=0 action_diff=0 control_diff=0 terminal_diff=0`；另一行证明故意改动 FAIL |
| PonderPounce 外壳 | `pytest tests/pipeline/evalx/pp/test_pp_server_wrap.py -q` | `PP_SERVER_ACTION_EQ=PASS` |
| 观测器完整且不改结果 | MME 每片 `run_orig_mme.sh` 末行；`gate2_compare.py --orig-format v75` 对 E0 比 SimpleMemVLA 原侧重跑 | `OBSERVER_COMPLETE=PASS episodes=<n> mismatch=0 hook_errors=0 report=ok`；`ORIG_RERUN_VS_E0=INFO policy=smvla compared=192 flips=<n>`（应为 0；不为 0 先查观测器与环境指纹） |
| 记录契约与完整性 | 各子任务测试的 `assert_renderable`、`assert_counts_consistent`；正式产物逐已接受身份核 trace | `TRACE_CONTRACT=PASS routes=6`；`TRACE_COMPLETE=PASS accepted=<n> missing=0 hook_errors=0` |
| 第二档输入与来源 | `gate2_compare.py --manifest … --new-ledger … --orig-attempts …` | `GATE2_INPUTS=PASS expected=192 missing=0 extra=0 unaccepted=0 ambiguous=0 trace_binding_mismatch=0`；`GATE2_PROVENANCE=PASS local_rows=0 unknown_rows=0` |
| 本机 smoke | 每批每路线 1 局（新 run 名、新 preflight 目录） | `OFFICIAL_MEDIA=PASS total=1 skip=0 fail=0`、`VIDEO_SAVED=PASS multi_mp4=0` |
| 第一档 | `noise_gate.py gen-regress check --set {v9,xhard0}` | `GEN_REGRESS=` 如实记录 |
| 第二档 | 五模型各跑 `gate2_compare.py`（GroundSG、PonderPounce 对上一轮 GL 原侧 + 补跑合表；SimpleMemVLA、MME 对本轮原侧重跑，另 `--orig-format v75 --noise-runs <O1> <O2>` 出历史观测） | 5 模型各 `GATE2=INFO compared=192 same_terminal=<n> s2f=<n> f2s=<n> sr_orig=<x> sr_new=<y> sr_diff_pp=<d> mcnemar_p=<p> not_observed=<n> …` |
| 第三档 | `eval_report.py`、`video_check.py`、`official_media_check.py` | 每模型 `EVAL_COVERAGE=PASS unique_terminal=800 error_final=<n>`、`VIDEO_SAVED=PASS`、`OFFICIAL_MEDIA_INPUTS=PASS`、`OFFICIAL_MEDIA=PASS total=800 skip=0 fail=0 no_frame_error=<n>` |

## 四、runbook（主会话）

1. **占位 job**（已获授权，不是开工令）：同时请求 ≤10 张单卡 `--account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:a40:1 --gpu_cmode=shared --cpus-per-task=4 --mem=64G --time=48:00:00 --wrap='sleep infinity'`，到期立即同规格续交。现有：`sgev-hold-00～07` = 63188711～16、63188719、63188720，`sgev-hold-08`、`09` = 63325534、63325535；清单 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/gl-hold-logs/hold-jobs-sgeval-20261004.txt`；收尾按清单逐个 `scancel`。**单 job 一个串行席位 owner**，stage／local-root／ledger 目录按 `<model>/<dataset>/<side>/<shard>` 唯一，冲突启动拒绝。
2. **批次 1**：第一档沿用根目录 `1003-noise-baseline-plan.md` 第二部分五节 runbook 的第一档做法（执行副本 `robomme_benchmark-noise` 检出开工时 HEAD；`--attempts n --resets 3n --retries 0`）；原侧补跑用上一轮执行副本 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-sgeval`（不同步、不改，起跑记录其 HEAD），`run_official_hard.sh` 跑 PonderPounce 分片 1 与 QwenVL 未跑分片（**QwenVL 一律 `--episode-wall 3600`**，用上一轮 `launch_seat_v2.sh` 体例），结果写本轮新 stage，合表时与上一轮原侧按身份并起，补集合必须恰等于清单差集。
3. **改代码**：S0 提交 → 同一消息派 S2a、S2b、S8、S1、S6、S7、S4、S5、S3（`model: "opus"`、`isolation: "worktree"`）→ 按合并顺序逐个第一次审查、`git merge --no-ff <TIP sha> -F <消息文件>`、第二次审查、push。
4. **每批起跑前三件事**：① 主会话核依赖集合与冻结 sha，出 `RUN_INPUTS=`；② 对该批路线跑 `client_replay_eq.py --base <BASE> --candidate <冻结 sha>`；③ 本机 smoke（tmux 前缀 `ovl2-`）。三项 PASS 才建 NFS 执行副本 `robomme_benchmark-sgeval2-<批次>`（`git clone --no-hardlinks` + `git submodule update --init`，检出冻结 sha；主 `.venv` 用 `UV_LINK_MODE=copy uv sync --frozen --group eval-client`；三方服务 venv 经环境变量 `MME_PY`／`PP_PY`／`SMVLA_PY`／`SGEVAL_CLIENT_PY` 指向上一轮执行副本中的对应 venv，起跑段打印并核 editable 指向属于本批冻结源码）→ 第二档与第三档分片各占席位同时起 `run_eval_gl.sh`（`--dataset test-hard0 --max-steps 1300`／`--dataset test-hard --max-steps 1600 --strict-cap`；**QwenVL 席位加 `--episode-wall 3600`**）。
   - **批次 2**（{S0,S2a,S2b,S8,S1}）：GroundSG Oracle、QwenVL 新侧第二、三档。
   - **批次 3a**（{S0,S2a,S2b,S8,S7}）：主会话检出两个原版工作树（`git -C /nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA worktree add /nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA-official-xhard0 4e0c04f`；`git clone --no-hardlinks -b official-xhard0-0929 /data/hongzefu/robomme_policy_learning_MotionJEPA /nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-official-xhard0` 后初始化子模块），本机各跑 1 局 smoke 核 `ORIG_BRANCH_PIN` 与 trace／arrays 可读（计入预算：2 局，reset 6+2），再在 GL 按清单 10 片起 `run_orig_smvla.sh`／`run_orig_mme.sh`（`srun --overlap --gpu_cmode=shared`，4 CPU），2 模型 × 16 任务 × 1 档 × 12 局 = 384 局。
   - **批次 3b**（{S0,S2a,S2b,S8,S4}）：SimpleMemVLA、MME 新侧第二、三档。
   - **批次 4**（再加 S5）：PonderPounce 新侧第二、三档。
   - 第二档对比在 S6 合入且两侧结果齐后跑；批次之间不互相等待。
5. **批次 5**：S3 合入后本机 Astra smoke **≤2 局**，`astra_cost_guard.py --cap 5` 先起并确认心跳，runner 同步预留；5 美元硬上限。
6. **本轮全新目录**：run 名 `sg-eval-gl-<开工日期>-02`；stage、账本、media、trace、日志全部新建，命令逐条写进 `launch.md`，不复用上一轮 stage；起跑后核对每条路线首局确有新 attempt。
7. **监听**：每份日志一个 Monitor，过滤 `EXIT_CODE=|RUN_BLOCKED|INFRA|OFFICIAL_RENDER=FAIL|OFFICIAL_MEDIA=|OBSERVER_COMPLETE=|BUDGET_|Traceback|CUDA|svulkan2|EXCLUSIVE|NO RECORD|reset 拒绝`；开工后按根目录 `1003-oracle-subgoal-groundsg-eval-plan.md` 第二部分五节「排到卡即唤醒」「到期与续交」处理（自动唤醒须有创建成功回执，不以 tmux 存活代替）。
8. **收尾**：各模型第二档对比表（第一部分二节交付格式）、第三档成绩表、`OFFICIAL_MEDIA` 汇总、视频索引、`BUDGET_ENFORCEMENT` 终报；留档 `docs/validation/sg-eval-gl-<日期>-02/{launch.md,result.md,records/}`；commit、push；按清单 `scancel`。本轮成本（逐模型席位小时、CPU 重绘耗时、失败 raw 保留空间）用已批 smoke 实测更新进 `launch.md`，不另扩采；空间低于 150 GiB 停止新局。

## 五、风险与盲区

| 项 | 说明 | 处置 |
|---|---|---|
| MME 官方本身不可复现 | 官方三对两两翻转 7～19 局（方向：4/3、9/7、10/9） | 报告两方向翻转与成功率差，历史观测只作描述，不写「相当」或「一致」 |
| 逐步分叉机理 | 上一轮写「随机数跨局累积」，核实不成立（每局 reset 重置 rng）；现象更像 XLA 自动调优／JIT 数值非确定性 | 192 局全比；分叉按维度与量级报告；留档订正措辞；两侧服务端 `DET`／`COMPILE_CACHE` 设置与 server 日志 XLA flags 入 `launch.md` |
| MME 原侧客户端环境 | E0 当时用的 `robomme_policy_learning-testhard-v7/robomme_env` 已删 | 改用本轮客户端环境 + 原版子模块 `src` 置前；起跑断言导入路径；环境指纹（sapien、torch、驱动）与 E0 不同处写明，E0／O1／O2 作带条件参照 |
| SimpleMemVLA 原侧 0 步 Vulkan 错误 | v7.5eval 事故 6：部分片首遍 0 步 `createDeviceUnique` | 记 `infra=True`，按启动器自带 3 遍重评补齐，计入共享基础设施重试额度 |
| 原侧观测器依赖原版内部名 | `run_group`、`InProcSimPool`、`EnvRunner`、`EpisodeEvaluator` 等 | 原版分支钉死提交，测试钉死；不符即停交用户 |
| 原侧不可见字段 | `terminated`／`truncated` 两个原版入口都不向上返回 | 按 C9 记 `NOT_OBSERVED`；不新增更低层钩子（用户 2026-10-06 裁决） |
| GroundSG 补存视频的帧数口径 | 官方超时先 break 后 record；异常步无观测 | 按 C8 三分计数，`official_source` 记来源 |
| PonderPounce 外壳依赖私有方法 | `_fire_s1`、`_dispense`、`_visible_cognition` 属锁定提交 `723df357` | `PP_SERVER_ACTION_EQ` 钉死；改不通即停交用户 |
| Astra 守卫窗口 | 第三方 `_send` 在检查 STOP 后仍有最长 20 秒等待再发送 | runner 子类同步预留 + 等待后复检；Astra ≤2 局硬上限兜底 |
| 跨时间对照 | GroundSG、PonderPounce 新侧与上一轮原侧不同时跑 | 只出差异报告，留档写明 |
| QwenVL 墙钟 | V9 1600 步单局最长约 40 分钟；`wall_of` 默认 1800 秒 | 所有 QwenVL 命令显式 `--episode-wall 3600`；48 h 到期按 `1003-oracle-subgoal-groundsg-eval-plan.md`「到期与续交」 |
| GL 配额 | 账户 GPU 20 张已满，cokite 12 张到 10-13 后 | 现有 7 张 RUNNING 先用；批次按前提自动排开 |
| 第一档锚点早于最终代码 | 第一档在改代码期间跑 | 留档附 `git diff --stat <第一档冻结>..<各批冻结> -- src scripts/parity scripts/injection-dev` 为空 |
| 本计划判定行 | 全部待实施 | — |

## 六、预算（2026-10-06 已批；同日按 Codex 审计第 17 条修正 SimpleMemVLA 原侧 reset 口径，用户选「提高总额」并追加「Reset额度可以。提高到现在的十倍左右不用作为硬边界。」「唯一需要注意的就是astra还是只跑两次。」）

评估每局 build 与 reset 各 1 次计 2 次 reset；**原侧 SimpleMemVLA 每局最多 3 次尝试，计 6 次**（R11）；生成每条轨迹 reset 上限 3 次。V9 每模型 800 局 = `3任务×2档×17 + 3任务×1档×16 + 2任务×5档×10 + 2任务×2档×13 + 2任务×2档×12 + 7任务×2档×25 + 2任务×1档×50`（`hard_specs.py::_v9_cells`）。

| 用途 | 乘式 | 轨迹 | reset 计量 |
|---|---|---:|---:|
| GL 第一档首跑 | V9 43 格 × 3 局 + xhard0 16 任务 × 3 局 | 177 | 531 |
| GL 第一档 smoke 与重跑 | 2 + ≤20（两集合共用，V9 优先） | 22 | 66 |
| 本机 smoke（非 Astra 新侧） | 5 路线 × 1 局 | 5 | 10 |
| 本机 smoke 修复后重跑 | 5 路线 × ≤2 局 | 10 | 20 |
| 本机 smoke（原侧重跑入口） | SimpleMemVLA 1 局 × 6 + MME 1 局 × 2 | 2 | 8 |
| 本机 smoke（Astra，付费） | **≤2 局（硬上限）** | 2 | 4 |
| GL smoke（新侧） | 5 路线 × 1 局 | 5 | 10 |
| GL 第二档新侧 | 5 模型 × 16 任务 × 1 档 × 12 局 | 960 | 1920 |
| GL 第二档原侧重跑 | SimpleMemVLA 16 任务 × 1 档 × 12 局 × 6 + MME 16 任务 × 1 档 × 12 局 × 2 | 384 | 1536 |
| GL 第二档原侧补跑 | PonderPounce 分片 1 共 96 局 + QwenVL（16 任务 × 1 档 × 12 局 − 已有 39）= 153 局 | 249 | 498 |
| GL 第三档 | 5 模型 × 800 局 | 4000 | 8000 |
| 基础设施重试（共享） | 非 Astra 5 模型 × ≤10 次（其中 SimpleMemVLA 原侧份额按 6 计） | 50 | 140 |
| 到期续跑 | 5 模型 × ≤100 局（SimpleMemVLA 原侧份额按 6 计） | 500 | 1400 |
| **合计（计量）** | | **6366** | **14143** |
| **账本上限** | | **6366（硬）** | **约 141430（软，十倍）** |

审批记录：用户 2026-10-06「234都同意 计划我在看」批准预算、Astra 本机 smoke ≤2 局与 5 美元、集群操作预授权（清理自己 job 内卡死的 `srun` 步骤、按清单精确 JobID 取消自己的 job）；随后批准 SimpleMemVLA、MME 新原侧 384 局增量；同日 Codex 审计后用户在三选项中选「提高总额到 14143」，随后补充「Reset额度可以。提高到现在的十倍左右不用作为硬边界。」「唯一需要注意的就是astra还是只跑两次。」；同日 02:22 EDT 用户再授权「你可以尽情的去跑最多可以占10张卡自己来搞这个slurm的J0B」「你在不作为限制」（读作：开工后无人值守一路跑到计划结束、不设截止时间、最多 10 张卡、占位 job 由主会话自行提交与取消；AskUserQuestion 确认「还不开工」「不设截止，跑到计划结束」）——轨迹 6366 为硬上限，reset 以 14143 为计量、约 141430 为账本软上限（超过只告警），Astra 2 局与 5 美元为硬上限。正常 fail／timeout 不重试；smoke 不进正式分母；账本持久化。

## 七、留档与 commit 纪律

- S2a、S2b、S8、S1、S6、S7、S4、S5、S3 各经 `--no-ff` 合并占一个项目号，子代理提交前缀 `sub/<编号>: `；S0、回放脚本、留档由主会话按第 11 条六项 body 提交，含第一部分二节的用户原话。
- 留档 `docs/validation/sg-eval-gl-<日期>-02/`：`launch.md` 起跑即写（执行副本 sha、各批冻结 sha、JobID、tmux 会话清单、完整命令）；`result.md` 跑完写（四节格式的第二档对比表、第三档成绩表、`OFFICIAL_MEDIA` 汇总、结论边界）；`records/` 只归档判定行、差异表、视频索引与一次性脚本逐字副本；不归档 mp4。
- `docs/validation/sg-eval-gl-20261004-01/`、`docs/validation/v7.5eval/` 不改；R7 所列输入到本轮结束前不动。

## 八、第二档逐模型原侧来源与上游差异、新侧现状（2026-10-06 四个只读子代理逐文件查实；从第一部分移入）

#### 2.0 共同背景：两侧跑同一批局，差别在「环境包」与「驱动代码」

**局是什么。** 官方 RoboMME `test` 集每任务 50 局，元数据里 `difficulty=="hard"` 的恰好 12 局，原局号 3、7、…、47。16 任务 × 12 = 192 局，这就是 xhard0。我们的 `robomme_hard` 包把这 12 局重新编号为 0..11，取名 `dataset="test-hard0"`（`src/robomme_hard/env_record_wrapper/hard_builder.py`）：它只读官方 test 元数据，只传官方原 seed 与 `difficulty="hard"`，不加任何采样规格，起法与官方相同。两侧的身份清单由 `eval_manifest.py --mode hard0` 产出，每行同时带原局号 `source_episode` 与新编号 `builder_episode`，与 `artifacts/v7.5eval/identities-full192.json` 逐个相同。

**原侧环境 vs 新侧环境。**

```
         原侧（原版 RoboMME hard）                          新侧（xhard0 + 新接口）
  ┌──────────────────────────────────┐            ┌──────────────────────────────────┐
  │ 模型服务进程（命令两侧完全相同）   │            │ 模型服务进程（命令两侧完全相同）   │
  └───────────────▲──────────────────┘            └───────────────▲──────────────────┘
                  │ websocket                                     │ websocket
  ┌───────────────┴──────────────────┐            ┌───────────────┴──────────────────┐
  │ 模型原版评估循环                  │            │ 同一份循环（GroundSG）或逐行复刻   │
  │ + 我们的只读观测（写 trace/帧）    │            │ + 我们的 TraceWriter / 录像器      │
  └───────────────┬──────────────────┘            └───────────────┬──────────────────┘
                  │                                               │
  ┌───────────────┴──────────────────┐            ┌───────────────┴──────────────────┐
  │ 官方 robomme 包（src/robomme）     │            │ robomme_hard 包（src/robomme_hard） │
  │ BenchmarkEnvBuilder(dataset="test")│            │ BenchmarkEnvBuilder(dataset=        │
  │ make_env_for_episode(3,7,…,47)     │  同一批局  │   "test-hard0") 编号 0..11          │
  └──────────────────────────────────┘            └──────────────────────────────────┘
```

- 原侧导入 `robomme`（本仓库 `src/robomme`，与官方 `1fadc0ec` 逐字节相同，`UPSTREAM_GUARD=PASS`），启动与每局结束都断言 `robomme_hard` 不在 `sys.modules`。新侧导入 `robomme_hard`，它是官方 `BenchmarkEnvBuilder` 的子类，`make_env_for_episode` 整段覆写，wrapper 链与官方逐项相同但全是 `robomme_hard` 下的复制件。
- 模型服务两侧一条命令：GroundSG 与 MME 都是 `third_party/mme-vla` 的 `scripts/serve_policy.py --seed=7 ... --policy.config=mme_vla_suite`（GroundSG 用 symbolic-grounded-subgoal 权重，MME 用 perceptual-framesamp-modul 权重）；PonderPounce 是 `python -m ponderpounce.eval.robomme_server --args.seed 0`；SimpleMemVLA 原版没有服务进程（单进程内嵌），新侧由我们的 `smvla_server.py` 包一层，见 2.3。
- 两侧 `max_steps=1300`、不带 strict cap，与官方默认一致。官方循环 `count > max_steps` 才判超时，所以超时局执行第 1301 步。

**「原侧」也不是「上游一键跑」。** 四个模型的原侧都在上游原版之上做了四类事：① 只跑清单里的 192 局，不跑每任务 50 局；② 加只读观测（逐步 trace 与帧），原版代码路径不改；③ 用我们的重试与服务重启调度代替官方的 `progress.json` 续跑；④ 渲染或解释器环境按 GL 席位配置。单局的环境起法、策略循环、模型服务与官方相同。下面逐模型说清各自「原侧 = 上游 + 什么」。

#### 2.1 GroundSG Oracle / QwenVL

**上游原版入口**：`third_party/mme-vla/examples/robomme/eval.py` 的 `evaluate()`（子模块锁定 `ecf086c3`，与 fork 的 `main` 在 `examples/robomme` 下零 diff）。流程：每任务建 `EnvRunner`（内部写死 `BenchmarkEnvBuilder(dataset="test")`），`range(50)` 逐局 `make_env` → `eval_each_episode` → 写 `progress.json`；每局官方 `RolloutRecorder` 存一份叠字 mp4；遇 `unknown` 整个评估 abort。

**原侧 = `scripts/eval-official/official_hard_runner.py` + `official_defs.py`**（我们写的驱动，调官方循环原文）：

| 做了什么 | 怎么做的 | 改不改行为 |
|---|---|---|
| 取官方代码原文 | `official_defs.extract_defs` 用 ast 从官方 `utils.py`、`env_runner.py`、`eval.py`、`subgoal_predictor.py` 摘出 `EpisodeEvaluator`、`EnvRunner`、`RolloutRecorder`、`OracleSubgoalPredictor`／`QwenVLSubgoalPredictor` 等类的原文执行，整文件 sha256 写进结果行 `official_sha256` | 不改 |
| 环境 | 给官方 `EnvRunner` 注入 `robomme.env_record_wrapper.BenchmarkEnvBuilder`（`src/robomme`），`dataset="test"`，每局 `make_env(source_episode)` | 不改（单局与官方相同） |
| 只读观测 | `TapRunner` 包官方 `EnvRunner`（先调原方法再记）、`EnvTap` 包 `runner.env`、`TracingClient` 包真实 websocket 客户端（先记请求 sha256 再原样转发）；写 `trace.jsonl`（route `mmesg/<variant>/orig`）与 `frames/{front,wrist}.rgb24` | 不改 |
| 只跑 192 局 | `load_shard` 只收 `tier=="xhard0"` 的身份清单 | 改选局，不改单局 |
| 结果与重试 | 不用 `progress.json`／`log.json`，改 `results.jsonl` + `.a<N>` 尝试目录；`run_official_hard.sh` 第 1 轮跑全部，之后只重跑无非 infra 结果的身份，重试前重启服务 | 改调度 |
| `unknown` | 官方 abort 整个评估；这里记 `status=error`、`error=success_flag=unknown` 继续下一局 | 改（有记录的偏离） |
| 服务不可达 | 每局前 TCP 探测最多 300 s，连不上停分片；官方客户端无限重试 | 改失败处置 |
| 官方叠字 mp4 | 局末 `shutil.rmtree(video_dir)` 删掉，交付视频由 rgb24 帧转码 | 改交付物（本阶段 S1 要在新侧改回保留） |

种子：客户端未改种子，服务端 `--seed=7` 两侧一致。上一轮留档写「服务端随机数跨局累积、只有起服务后第一局能逐步对拍」；2026-10-06 核实官方 `MME_VLA_Policy.reset` 每局都执行 `self._rng = jax.random.key(self._seed)`，该机理不成立，实测分叉（全在第 0 步动作块、输入哈希相同、首局也只 1/3 一致）更可能来自 XLA 自动调优与 JIT 的数值非确定性；本轮 192 局全比，分叉按数值噪声报告。

**新侧 = `scripts/eval-official/mmesg_client.py`**：仍调同一份官方 `EpisodeEvaluator.eval_each_episode` 原文；差别只在 `SessionRunner` 实现官方 `EnvRunner` 的接口（`get_init_obs`、`step` 与官方逐行同式，只把 `self.env` 换成 `env_client.EnvSession`，即 `robomme_hard` 的 `test-hard0`）；录制客户端 `RecordingClient` 与父类逐行相同只加 sha256；`EpisodeRecorder` 写无损帧；trace route `mmesg/<variant>/new`；传给官方循环的 `episode_id` 用短号（SwingXtimes 任务目标太长，叠字 mp4 文件名超 255 字节写不出，12.453 修）。官方叠字 mp4 同样局末被删。

**oracle 与 qwenvl 的区别**只在子目标来源，策略权重相同：oracle 的 `OracleSubgoalPredictor.get_subgoal` 直接返回环境 `info["grounded_subgoal_online"]`（环境给的真值子目标）；qwenvl 用微调的 Qwen3-VL-4B + groundSG 适配器看视频缓冲预测。命令行 `--variant ground-sg-oracle|ground-sg-qwenvl` 切换，qwenvl 必须带 `--qwenvl-groundsg-adapter`。

**上一轮 GL 结果与本轮缺口**：Oracle 原侧 192 局齐（成功 144/192 = 75.0%），新侧 192 局终态 192/192 相同、逐步一致 180（其余 12 局是单独起服务的 SwingXtimes 补跑局，只比终态）。QwenVL 原侧只跑完分片 00 共 39 局（9 成功），新侧 37 局有终态且 37/37 逐步一致（另 2 局撞 30 分钟墙钟记 error）；分片 01～04 共 153 局缺，批次 1 补跑。

#### 2.2 PonderPounce

**上游原版入口**：服务端 `third_party/PonderPounce/ponderpounce/eval/robomme_server.py`（子模块锁定 `723df357`，vla-eval 的 `ModelServer` 子类）；客户端上游没自己写，用 vla-eval 0.7.0 自带的 `vla-eval run`（`RoboMMEBenchmark` + `SyncEpisodeRunner`），配置 `configs/robomme.yaml`：`dataset` 默认 `test`、每任务 50 局、`max_steps 1300`，渲染走 docker 镜像里的 CPU lavapipe。服务端两套节拍：Ponder（System 2）每 1000 ms 用当前观测产出一个 cognition，门控切换时附子目标文本，经模拟计算延迟后才「可见」（`_visible_cognition`）；Pounce（System 1）每 1000 ms 用最新可见 cognition 做 flow matching 预测一个约 20 步的动作 chunk（`_fire_s1`）；`_dispense` 每控制步取 chunk 一行，没有 chunk 时手臂 hold。噪声种子 `crc32(f"{seed}:{sid}:{n}")`，同一 sid 在一个服务进程内第几次开局决定 `n`。**子目标文本只写服务端日志**，协议里不回传。

**原侧 = `scripts/eval-official/pp_official_runner.py`**：服务端原样（同一条命令 `--args.seed 0`）；客户端直接用 vla-eval 的 `RoboMMEBenchmark` 与 `SyncEpisodeRunner().run_episode(...)`，是上游循环。在它之上：环境是 `src/robomme`、`dataset` 走 vla-eval 默认 `test`、`episode_idx = source_episode`；渲染改本机 GPU（`configure_render("gpu")`）而不是 docker CPU；只跑清单 192 局；`FixedSidRecorder` 让 EPISODE_START 载荷带固定 sid `<task>|<source_episode>|<seed>`，与新侧完全相同；观测用 `make_tracing_bench_class`（只覆写 `reset`，之后把 `self._env` 换成 `EnvProxy`，`step` 原样转发再记五元组）与 `TracedConnection`（记每个协议帧的规范化 sha256）；写 `trace.jsonl`（route `pp-orig`）与 rgb24 帧；重试前重启服务，因为固定 sid 一个进程只能用一次。

**新侧 = `scripts/eval-official/pp_client.py`**：客户端是我们对 vla-eval 0.7.0 `SyncEpisodeRunner.run_episode`、`RoboMMEBenchmark`、`make_obs` 的逐项复刻，不再用 vla-eval 的类；环境换 `robomme_hard` 的 `EnvSession`；服务端同一条命令；协议帧与动作块的哈希口径与原侧同一批辅助函数；局内 `ConnectionClosed` 可重连 1 次（原侧不重连）。trace 的 `subgoal` 字段两侧都记 `info["simple_subgoal_online"]`，这是环境 `DemonstrationWrapper` 按任务脚本给的「标准答案」子任务名，**不是 PonderPounce 自己产出的子目标**——这就是 3.3 里 S5 要改的原因。

**上一轮 GL 结果与本轮缺口**：分片 0 共 96 局，两侧 39/96 成功（40.6%），终态 96/96 相同、逐步 96/96 一致（本机 192 局也是 192/192 逐步一致）。分片 1 共 96 局未开跑，批次 1 补跑。

#### 2.3 SimpleMemVLA

**上游原版入口**：`third_party/SimpleMemVLA/robomme_sim/eval_success.py`（子模块锁定 `c564c17`）。它是**单进程内嵌**：没有服务进程，`InProcSimPool` 在线程池里并行 reset／step 多个环境，`BatchedEvalPolicy.generate_batch` 一次 batched 前向同时返回动作与子任务文本，取前 16 步执行；`--group_size` 默认 2（两局一组），每任务 `min(50, 局数)` 局；种子只在 `evaluate_tasks` 开头设一次；输出只有 stdout 与 `results.json`（每任务成功率），**没有逐局日志、没有逐步日志**；视频只在给 `--video_dir` 时每任务各留 1 条成功、1 条失败。环境是它自带的 `robomme_sim/robomme`（与本仓库 `src/robomme` 逐字节相同，只少官方自带的一个杂散文件 `vqa_options copy.py`——该文件是官方仓库原有的，不是我们多出来的），`--dataset_split test`。

**原侧 = SimpleMemVLA 分支 `official-xhard0-0929` 提交 `4e0c04f`**（基于 `c564c17`，只多一个提交，+324／−1，3 个文件）。这就是 2026-09-29 产出官方历史成绩 E0 的代码。改动：

| 文件 | 改了什么 | 不给清单时 |
|---|---|---|
| `robomme_sim/eval_success.py` | `parse_args` 加 `--episode_manifest`（只评清单里的官方 test 原局）、`--shard`、`--episode_log`（逐局 jsonl）、`--resume`；`run_group` 加 `details`、`video_path_fn` 两个可选参数；新增 `evaluate_manifest`：组大小恒 1、开跑前用 `resolve_episode` 核对 seed、**每局开头重设 `torch.manual_seed(0)` 与 `np.random.seed(0)`**、每局必录像、每局追加一行终态到 `--episode_log`、error 局后重建 `InProcSimPool`；`main()` 只在给了清单时分叉 | 与上游逐行相同（新增参数默认 None，各分支有 None 保护） |
| `scripts/run_official_xhard0.sh` | `--dataset_split test --group_size 1 --execute_horizon 16 --max_steps 1300 --num_denoising_steps 10 --eval_temperature 1.0 --max_subtask_tokens 64 --compute_dtype bfloat16 --attn_implementation sdpa --num_gpus 1` | — |
| `scripts/gl_run_official_xhard0.sh` | 占位 job 内 srun，每遍带 `--resume`，最多 3 遍 | — |

**要点**：清单模式与上游默认路线有三处实质差异——组大小 1 vs 2、种子每局重设 vs 只设一次、每局录像 vs 抽样——所以「原侧」对应的是「E0 那套跑法」，不是「上游 README 一键跑」。原侧每局只写一行终态，**没有逐步记录**，这是 2.5 要外挂观测器的原因。E0 成绩 141/192（73.4%）；两遍官方重跑 O1、O2 与 E0 两两 0 翻转，说明这条路线本身可复现。

**新侧 = `scripts/eval-official/smvla_server.py` + `smvla_client.py`**：我们把上游 `eval_success.build_policy` 拆出来做成服务（按 E0 命令行解析参数，`EXECUTE_HORIZON=16`，每局第一次推理前 `reseed()` 同样 `torch.manual_seed(0)`，回包键 `actions`、`actions_full`、`subtask`，已逐字核对）；客户端用 `robomme_hard` 的 `EnvSession`，一批 16 步在环境里逐步执行完，才把这批帧一次 `observe` 回服务。与原侧的差别是进程拆分、环境包、以及**没有 `trace.jsonl`**（逐步数据只在录像器的 `events.jsonl`，`decision` 事件里有 `subtask`）。

#### 2.4 MME

**上游原版入口**：MME-VLA 官方 `ecf086c` 的 `examples/robomme/eval.py`。服务端 `scripts/serve_policy.py`（JAX）单独进程，客户端每局新建 websocket 连接，先 `client.reset()` 再环境 reset；`EnvRunner` 写死 `BenchmarkEnvBuilder(dataset="test")`；每任务 50 局；动作计划空了就 `add_buffer` + `infer` 取 16 步；`progress.json` 续跑、`log.json` 收尾；每局存叠字 mp4；**没有逐步日志**。

**原侧 = `robomme_policy_learning` 仓库分支 `official-xhard0-0929` 提交 `927c56d`**（直接父提交就是 `ecf086c`，+299 行，4 个文件）。这是 2026-09-29 产出 E0 的代码（E0 日志头显示 `ecf086c` 加当时未提交的工作树，源文件 mtime 早于起跑，`927c56d` 是其提交后形态；这一点 v7.5eval 已登记为盲区）。改动：

| 文件 | 改了什么 |
|---|---|
| `examples/robomme/eval.py` | `Args` 加 `episode_manifest`、`shard`、`video_dir`；新增 `evaluate_manifest`：断言 `robomme_hard` 未导入、按清单取本片、每局用 `resolve_episode` 核对 seed 且 `difficulty=="hard"`、`make_env(source_episode)` → `eval_each_episode`、逐局追加 `episodes.jsonl`（`task, source_episode, seed, status, task_success, steps, error, max_steps, attempt, shard, video`）、续评跳过已有终态；视频在终态之后另写 `{task}_xhard0_{source_episode}_{seed}.mp4`。`evaluate()` 开头 `if args.episode_manifest: return evaluate_manifest(args)`，官方全量循环不动 |
| `examples/robomme/xhard0_manifest.py` | 纯函数：`load_rows`、`check_seed`、`done_keys`、`video_name`；配 CPU 单测 |
| `scripts/gl_eval_official_xhard0.sh` | 占位 job 内同一张卡先起 server（守卫 server 代码相对 `ecf086c` 零 diff）再跑客户端；客户端 `PYTHONPATH` 把该仓库子模块 `third_party/robomme_benchmark/src` 置顶并断言 `robomme.__file__` 在其下；最多 3 遍重评 error 局，`episodes.jsonl` 30 分钟无进展即杀掉重起 |

环境来自该仓库子模块 `third_party/robomme_benchmark`（gitlink `856bc3a`，其 `src/robomme` 与本仓库相同）。E0 成绩 50/192（26.0%）；O1 49、O2 48；两两翻转 E0:O1 为 4+3=7 局、E0:O2 为 9+7=16 局、O1:O2 为 10+9=19 局——MME 官方路线本身每次重跑都有十几局翻转，v7.5eval 归因于 server 启动时的 JAX 编译与自动调优，本轮只把它当噪声带用。

**新侧 = `scripts/eval-official/mme_client.py`**：不 import 官方 `examples/`，而是逐行照抄官方 `utils.py`、`env_runner.py`、`eval.py` 加 `927c56d` 的 `evaluate_manifest` 的循环语义：`EnvRunnerShim` 照抄官方 `EnvRunner.step` 只把 `env.step` 换成 `EnvSession.step`；`RecordingClient` 与官方 websocket 客户端逐行相同只加 sha256；服务端同一条命令。**没有 `trace.jsonl`**，逐步数据只在 `events.jsonl`。

#### 2.5 为什么 SimpleMemVLA、MME 的原侧要外挂一层只读观测器，而 GroundSG、PonderPounce 不用

**根本差别在「原侧的驱动是谁写的」。**

- GroundSG、PonderPounce 的原侧驱动（`official_hard_runner.py`、`pp_official_runner.py`）是**我们写的**，它去调官方循环原文（GroundSG）或上游 runner（PonderPounce）。观测点（`TapRunner`、`EnvTap`、`TracingClient`、`EnvProxy`、`TracedConnection`）直接写在驱动里，所以它们的原侧天生就有 `trace.jsonl` 与帧。
- SimpleMemVLA、MME 的原侧是**模型自己仓库里的完整入口**（`eval_success.py`、`eval.py`），一个进程从头跑到尾，每局只写一行终态（`episode_log`／`episodes.jsonl`），没有任何逐步输出。口径 1 不许改这两份代码，口径 4 又要求逐步对比（「不接受只能对比success fail」）。唯一的办法是**从进程外面挂钩子**：
  - SimpleMemVLA：按模块本名执行 `robomme_sim.eval_success` 的模块体，在活模块命名空间里把 `run_group` 换成「先调原函数、顺便记局边界」的包装，再调同一个 `main()`；钩子挂 `InProcSimPool.reset`／`step`（在主线程、`fut.result()` 之后，从返回值复制演示帧、状态、执行动作、done／status）与 `BatchedEvalPolicy.generate_batch`（记输出动作块与子任务文本，GPU 张量只标记不搬运）。
  - MME：同进程 `runpy.run_path` 运行官方 `eval.py`，钩子挂 `EnvRunner.get_init_obs`／`step`（调用前复制 action，调用后复制返回的画面、状态、stop、status）与 `EpisodeEvaluator.eval_each_episode`（局边界）；客户端与 server 之间插一个透明 websocket 代理 `mme_proxy.py`，逐条记消息类型、长度、sha256，收尾 `transparency_check.py` 对账 → `OBSERVER_TRANSPARENT=PASS mismatch=0`。
  - 钩子铁律：只复制主机端 numpy、不调随机函数、不做 GPU 运算、不改参数与返回值；钩子内异常只打一行 `OBSERVER_HOOK_ERROR`，不影响原版逻辑；钩子都在目标模块首次导入完成后才挂，导入顺序不变。
- 这套观测器 v7.5eval 做过（`scripts/eval-official/official_observer/`，8 个文件），已在提交 `27d209d5` 整目录删除，当前目录只剩 `__pycache__`。S7 从 `27d209d5^` 恢复，并把写出格式改成与 GroundSG 原侧同布局的 `<key>.a<N>/{trace.jsonl,frames/}`（route `smvla/orig`、`mme/orig`），这样 `gate2_compare.py` 不用改读法就能逐步比。
- **观测器不改结果的证据**：v7.5eval 实测 SimpleMemVLA 同一局有无观测器官方 mp4 逐字节相同、816/816 帧；MME 代理 22 片 `OBSERVER_TRANSPARENT=PASS mismatch=0`。本轮再加两条：SimpleMemVLA 原侧重跑对 E0 逐局终态应 0 翻转（`ORIG_RERUN_VS_E0`）；MME 每片 `OBSERVER_TRANSPARENT=PASS`。

**开工时要注意的三个现场事实**（本次核实）：NFS 上 `SimpleMemVLA` 仓库工作区当前检出的是 `testhard-eval-v7-0929` 分支，不是原版分支，原版代码必须用 `git worktree add <新路径> 4e0c04f` 另检出；旧的三个工作树 `SimpleMemVLA-official-xhard0`、`robomme_policy_learning-official-xhard0`、`robomme_policy_learning-testhard-v7` 都已不存在；E0 当时 MME 客户端用的 venv（`testhard-v7/robomme_env`）随之删了，本轮改用 GL 执行副本的 client-env，并把原版子模块 `src` 置于 `PYTHONPATH` 最前、起跑断言 `robomme.__file__` 在原版子模块下且 `robomme_hard` 未导入。

#### 2.6 第二档逐模型完整对比表

两侧都是同一批 16 任务 × 1 档 × 12 局 = 192 个身份，全部 GL A40。

| 模型 | 原侧（原版 RoboMME hard + 模型原版代码） | 原侧与上游原版的差别 | 原侧已知成绩 | 新侧（xhard0 + 新接口） | 对比粒度 | 判差异的参照 | 开跑批次（原侧 / 新侧） |
|---|---|---|---|---|---|---|---|
| GroundSG Oracle | 上一轮 GL 192 局（`sgeval-20261004/gate2-oracle`），驱动 `official_hard_runner.py` 调官方 `eval_each_episode` 原文 | 只跑清单 192 局；加只读观测；`unknown` 不 abort；我们的重试调度；叠字 mp4 删除 | 144/192（75.0%） | 本轮 192 局 | 逐步 + 终态 | 上一轮 GL：终态 192/192、逐步 180 | 已有 / 2 |
| GroundSG QwenVL | 上一轮 GL 39 局 + 本轮补跑 153 局，同上驱动 | 同上 | 39 局中 9 成功；其余待补 | 本轮 192 局 | 逐步 + 终态 | 上一轮 GL 分片 00：37/37 逐步一致 | 1 / 2 |
| PonderPounce | 上一轮 GL 分片 0 共 96 局 + 本轮补跑分片 1 共 96 局，驱动 `pp_official_runner.py` 调 vla-eval 上游 runner | 只跑清单；GPU 渲染代替 docker CPU；固定 sid；加只读观测；我们的重试调度 | 96 局中 39 成功（40.6%）；其余待补 | 本轮 192 局 | 逐步 + 终态 | 上一轮 GL 分片 0：96/96 逐步一致 | 1 / 4 |
| SimpleMemVLA | **本轮重跑** 192 局：原版分支 `4e0c04f` 的 `eval_success.py --episode_manifest` + 外挂只读观测器 | 原版分支相对上游 `c564c17`：清单模式（组大小 1、每局重设种子、每局录像、逐局终态 jsonl）；观测器只加逐步记录 | E0 141/192（73.4%）；O1、O2 与 E0 0 翻转 | 本轮 192 局 | 逐步 + 终态（两侧每局都 `torch.manual_seed(0)`，每局都可逐步判） | 原侧重跑对 E0 应 0 翻转，不为 0 先查观测器 | 3 / 3 |
| MME | **本轮重跑** 192 局：原版分支 `927c56d` 的 `eval.py` 清单模式 + 外挂只读观测器 + 透明代理 | 原版分支相对上游 `ecf086c`：清单模式（seed 核对、逐局 `episodes.jsonl`、续评）；观测器只加逐步记录 | E0 50/192（26.0%）；官方三对两两翻转 7、16、19 局 | 本轮 192 局 | 逐步 + 终态（192 局全比；分叉按维度与量级报告为数值噪声，「只有首局可判」的旧假设已订正） | 两侧翻转数与官方噪声带 7～19 对照 | 3 / 3 |
| Astra | 不做第二档 | — | — | — | — | — | — |

#### 3.1 六条新侧路线的现状（为什么非改不可）

第一阶段的重绘工具 `scripts/eval-official/render_official_video.py` 从每局 `trace.jsonl` 画官方版式视频（用 `importlib` 加载官方 `RolloutRecorder` 原类画五条文字、黄点、红框）。它的 `load_trace` 要求 `route` 以 `/new` 或 `/orig` 结尾、演示段帧数等于 `demo_frames + 1`、`status` 与 `terminal_reason` 取规定值、每步有画面哈希与动作等。现状：

| 路线 | `route` 字串 | 有 `trace.jsonl` | 逐步数据在哪 | 现有视频 | 重绘工具能否读 |
|---|---|---|---|---|---|
| GroundSG 新侧 | `mmesg/<variant>/new` | 有 | trace | `episode.mp4`（无损帧转码）；官方叠字 mp4 局末被删 | 能（本机 V9 800 局重绘 `ok=800 fail=0`） |
| GroundSG 原侧 | `mmesg/<variant>/orig` | 有 | trace | rgb24 帧转码 `episode.mp4` | 能 |
| PonderPounce 新侧 | `pp-new` | 有 | trace，但 `subgoal` 是环境标准答案 | `episode.mp4` | 拒收（后缀不是 `new`） |
| PonderPounce 原侧 | `pp-orig` | 有 | 同上 | rgb24 帧转码 | 拒收 |
| SimpleMemVLA 新侧 | 无 | **无** | 录像器 `events.jsonl`（`decision` 事件含 `subtask`） | `episode.mp4` | 无对象 |
| MME 新侧 | 无 | **无** | 录像器 `events.jsonl` | `episode.mp4` | 无对象 |
| Astra 新侧 | `astra-new` | 有，但缺 `demo_frames`、演示段少初始帧、结束原因写 `env_done` | trace | 自存 `rollout.mp4`，漏演示帧、无文字条 | 拒收 |

结论：只有 GroundSG 一条路线现在能直出官方版式；其余五条要么格式不合、要么根本没有 trace；SimpleMemVLA、MME 的新侧没有 trace 也意味着 `gate2_compare.py` 读不到它们的逐步数据，第二档逐步对比做不了。

#### 3.4 SimpleMemVLA、MME 原侧观测器具体怎么挂（S7，原版代码一行不改）

**用哪份原版代码**（2.3、2.4 已讲，这里只列落点）：

| 模型 | 原版代码（仓库 · 分支 · 提交） | 本轮检出位置 | 原版环境 |
|---|---|---|---|
| SimpleMemVLA | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA` · `official-xhard0-0929` · `4e0c04f` | 主会话 `git worktree add /nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA-official-xhard0 4e0c04f`（该仓库工作区当前在别的分支） | 解释器 `SimpleMemVLA/.venv-robomme/bin/python`，权重 `SimpleMemVLA/checkpoints/simplememvla_robomme`，环境它自带的 `robomme_sim/robomme`，`--dataset_split test` |
| MME | `/data/hongzefu/robomme_policy_learning_MotionJEPA` · `official-xhard0-0929` · `927c56d` | 主会话克隆到 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-official-xhard0` 并初始化子模块 `third_party/robomme_benchmark`（`856bc3a`） | 服务端用本轮 `third_party/mme-vla/.venv`（同为 `ecf086c`），权重 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/eval-out/mmevla-ckpt/perceptual-framesamp-modul/79999`；客户端用 GL 执行副本 client-env + 原版子模块 `src` 置前 |

**清单**：`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v7-eval/eval-official-xhard0-192.jsonl`（16 任务 × 12 局 = 192，10 片），与上一轮 xhard0 分片身份逐个相同。

| 观测器文件（`scripts/eval-official/orig_observer/`，从 `27d209d5^:scripts/eval-official/official_observer/` 恢复后改写） | 挂在哪 | 记什么 | 这次要改的部分 |
|---|---|---|---|
| `smvla_wrap.py` | 按模块本名执行 `robomme_sim.eval_success`，替换活模块里的 `run_group` 为包装后调同一个 `main()`；钩子挂 `InProcSimPool.reset`／`step`、`BatchedEvalPolicy.generate_batch` | reset 的全部演示帧 + 初始帧、8 维状态、指令；每步实际执行的动作行、返回帧与状态、done／status；每次决策的动作块与子任务文本 | 原来写 v7.5 的 EpisodeRecorder 目录；改为用本仓库 `trace_writer.TraceWriter`（route `smvla/orig`）与 `mmesg_client.RawFrameWriter` 写出与 GroundSG 原侧同布局的 `<key>.a<N>/{trace.jsonl,frames/}` |
| `mme_client_wrap.py` | 同进程 runpy 运行原版 `eval.py`；钩子挂 `EnvRunner.get_init_obs`／`step`、`EpisodeEvaluator.eval_each_episode`（局边界） | 演示帧 + 初始帧、状态、task_goal；每步交给 env 的动作与返回的画面、状态、stop、status | 同上，改为写 route `mme/orig` |
| `mme_proxy.py` + `transparency_check.py` | 客户端与 policy server 之间的透明 websocket 代理 | 双向逐条消息的类型、长度、sha256；动作与状态数组 | 不改逻辑，只改输出目录；用于 `OBSERVER_TRANSPARENT=PASS … mismatch=0` |
| `_obs_common.py` | 公共：按路径加载、导入后挂钩、清单读取 | — | 只改模块名与路径 |
| `run_orig_smvla.sh`、`run_orig_mme.sh` | 单片启动器（照抄原版 `run_official_xhard0.sh`／`gl_eval_official_xhard0.sh` 的环境变量、守卫、server 命令、3 遍重评 error 局、无进展看门狗） | — | 输出目录改到本轮 stage；MME 客户端解释器改用本轮 client-env；起跑断言原版工作树提交为 `4e0c04f`／`927c56d` 且干净、`robomme.__file__` 在原版子模块下、`robomme_hard` 未导入 |

#### 3.5 GroundSG 补存视频的原理

官方 `eval_each_episode` 的录像器是 `self.init_episode(...)` 返回的局部对象，正常结束才 `save_video`。新侧适配器在本局开始前给 evaluator 实例包一层 `init_episode` 抓住它；遇到 `StepCapReached`、其他异常或 `unknown` 时，按官方文件名格式调用它自己的 `save_video`。`init_episode` 返回前就失败的局一帧未录，无视频，记原因。官方超时是先 break 后不 record，所以超时局的第 1301 步不进视频，记 `omitted_timeout_frames`。

#### 官方 repo `main` 比对（2026-10-06，四个只读子代理各在暂存目录克隆官方仓库后比对，未写入任何用户仓库）

用户要求「展开说四个模型原侧和官方的repo的main有什么区别注意是和官方的repo的main不是和我们fork的main」。结论：**四个官方仓库的 `main` 当日都没有越过我们钉的版本**，三个模型仓库的 `main` HEAD 就是我们钉的提交，环境仓库 `main` 之后只多文档提交。原侧与官方 `main` 的全部差别都是我们加的驱动、清单模式与观测，不是版本漂移。

| 官方仓库（上游，非 fork） | 官方 `main` HEAD（日期） | 我们钉的提交 | `main` 与钉死提交的差异 | 原侧相对官方 `main` 的全部差别 |
|---|---|---|---|---|
| `RoboMME/robomme_policy_learning`（GroundSG、MME 共用） | `ecf086c3`（2026-04-08） | GroundSG 原侧取 `ecf086c` 原文；MME 原侧分支 `927c56d`（父提交即 `ecf086c`） | `git diff --stat ecf086c main` 为空 | GroundSG：零代码差异，差别全在我们的驱动 `official_hard_runner.py`（只跑 192 局清单、`unknown` 不 abort、服务不可达 300 s 探测、`results.jsonl` + 重试调度、只读观测、叠字 mp4 局末删）。MME：`927c56d` 只增不删 4 文件 +299 行（`eval.py` +81 行清单模式，由 `--args.episode_manifest` 门控，不给即官方循环；`xhard0_manifest.py`、其测试、`gl_eval_official_xhard0.sh`），门控后与官方不同的只有逐局 `episodes.jsonl`、视频在终态后写、续评；脚本层 `XLA_PYTHON_CLIENT_MEM_FRACTION=0.75` |
| `OpenBMB/SimpleMemVLA` | `c564c17`（2026-09-24，整条历史 3 个提交） | 原侧分支 `4e0c04f`（父提交即 `c564c17`） | `git diff --stat c564c17 main` 为空 | `4e0c04f` 3 文件 +324／−1：`eval_success.py` 清单模式（组大小恒 1 vs 官方默认 2；每局重设种子 vs 官方只设一次；每局必录像 vs 官方每任务抽 1 成功 + 1 失败；逐局终态 jsonl；`run_group` 签名加两个默认 None 参数，−1 行即旧签名）、两个启动脚本；不给清单走官方路线。`robomme_sim/robomme`、`batched_policy.py`、`inproc_pool.py`、`robomme_env.py` 零差异 |
| `worv-ai/ponderpounce` | `723df357`（2026-09-29，3 个提交） | 子模块 gitlink `723df357` | 为空；vla-eval 官方 `uv.lock`、我们 client-env 锁与实装三处都是 0.7.0 | 代码零差异。差别全在运行方式：渲染本机 GPU vs 官方 docker 镜像 CPU lavapipe（最实质，像素不会逐位一致）；只跑 192 局清单 vs 每任务 50 局；固定 sid 的空操作 recorder；`EnvProxy`／`TracedConnection` 只读观测；我们的重试与重启服务；单连接串行 vs 官方多模拟器 `--shard-id` 分片 |
| `RoboMME/robomme_benchmark`（环境，四模型共用） | `016ac1c`（2026-10-03） | `src/robomme` = `1fadc0ec`；MME 子模块 `856bc3a` | `1fadc0ec..main` 4 个提交，只改 `doc/Wechat.jpg` 与新增 `doc/submission/ponderpounce.md`；`856bc3a..main` 约 80 个提交全是 README／doc／二维码、`challenge_interface/` 评测封装、`pyproject.toml` server 组加 flask | `src/robomme` 目录树 sha 在 `856bc3a`、`1fadc0ec`、`main` 三点相同（`4845da3b`），`diff -rq` 对本仓库 `src/robomme` 为空；`env_record_wrapper`、`robomme_env`、`env_metadata/test/*`、wrapper 链官方从未改过，hard 12 局起法与物理不受影响 |
