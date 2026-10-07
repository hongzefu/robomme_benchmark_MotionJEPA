# sg-eval-gl-20261006-03 起跑记录（launch.md）

> 计划：根目录 `1006-rename-official-names-and-stage3-eval-plan.md`（下称「计划」）第一部分三、第二部分四节 runbook、八.5 预算。接口：`docs/plans/1006-stage3-interface-freeze.md`。本文件起跑那一刻写，跑完另写 `result.md`。

## ① 目的与范围

两条线并行（计划第一部分三）：
1. **GL A40：五模型 OOD 第三档**（原 V9 `test-hard`，改名 `ood`）——FrameSamp+Modulation、SimpleMemVLA、PonderPounce、MemER、GroundSG+QwenVL，每模型 `1 模型种子（7）×（14 任务 × 2 档 × 2 局 + 7 任务 × 1 档 × 2 局 + 6 任务 × 1 档 × 2 局 + 2 任务 × 1 档 × 2 局）= 86` 局，共 `5 × 86 = 430` 局，1800 步 strict、模型 seed 7。GroundSG+Oracle 沿用 1004 轮 1600 步旧成绩不跑；3-tier Astra 只改代码不实跑；不跑 seed 0／42。
2. **本机 sled-vail：MemER hard-verify（原 `test-hard0`）原侧 vs 新侧对拍**——两侧同一批 `16 任务 × 1 档（xhard0）× 12 局 = 192` 局，1300 步，模型 seed 7，同一份 adapter；原侧 = 官方 `eval.py` MemER 分支经 `official_hard_runner.py` 驱动，新侧 = `groundsg_client.py` 走 `ground-sg-memer`；两侧共用同一兼容层（指纹 `105f05113a1e5f0b36ce5e4a7d050aff661694dbb770c4f88c5dbd35dd4e3814`）。产出差异报告 `GATE2=INFO`，不证明等价。

用户原话（2026-10-06）：「/data/hongzefu/robomme_benchmark_MotionJEPANewTask/1006-rename-official-names-and-stage3-eval-plan.md 开始实现 有问题问用户但不要阻塞」；计划内运行口径原话见计划引言（「三、这一版跑什么只跑这四个模型的V9。再加上memer的hard0对拍新老接口」「GroundSG+QwenVL也要跑每模型 43 格 × 2 局 = 86 局」「MemER 接入与 hard-verify 对拍在本机进行可以同步。其他不能在本机。」「345同意 4可以接续 2报告」「我授权你自己来管理J0B。尽可能让我少排队」「全局最多4张卡不是单个J0B。」等）。

## ② 版本与代码状态

| 项 | 值 |
|---|---|
| 冻结执行提交 | `0816c0a9fa5c2ca37b47bba07dd4c36334f2fb79`（12.524；功能 12.522 `852559f7`，改名 12.519 `41d199ab`） |
| GL 执行副本 | `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-sgeval3`（`EXEC_COPY=PASS head=0816c0a9 dirty=0`；子模块 mme-vla／PonderPounce／SimpleMemVLA 从本机副本初始化，主 `.venv` 共享解释器 3.11.14 + `uv sync --frozen --group eval-client`） |
| 本机对拍代码 | 主检出 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，起跑时 HEAD 见下方会话清单（代码与 `0816c0a9` 相同，其后只提交文档） |
| 三方服务 venv | `MME_VLA_PY`、`PP_PY` 指向上一轮执行副本 `robomme_benchmark-sgeval`（同锁定提交）；`SMVLA_PY` 指向 `robomme_benchmark-sgeval2-b34/artifacts/v8-two/venvs/smvla-env`（同锁定 gitlink）；`SGEVAL_CLIENT_PY=$N/sg-eval/venvs/client-env` |
| 第三方锁定 | mme-vla `ecf086c3`、SimpleMemVLA `c564c17d`、PonderPounce `723df357`（gitlink 零 diff） |

## ③ 启动与配置还原

公共参数：`--policy-seed 7 --budget-ledger $N/sgeval-20261006-03/budget-ledger.jsonl --trajectory-cap 870 --shared-infra-cap 50 --expired-cap 50 --planned-first-tries 821 --infra-retry-budget 1`（不给 `--reset-budget`，reset 只计量）。

- GL 分片任务：`$R/scripts/task_ood.sh <执行副本> <冻结 sha> <模型> <席号> <分片>`，经 `$R/scripts/launch_seat.sh <JobID> <名> <任务脚本> …`（`srun --jobid --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared`）在占位 job 内运行；`--dataset ood --max-steps 1800 --strict-cap`，stage `$R/ood-new-<模型>-seed7`，媒体根 `$R/media`；QwenVL `--episode-wall 3600`、MemER `--episode-wall 7200`，两者 `SEAT_XLA_MEM_FRACTION=0.65`。脚本留在 `$R/scripts/`（`R=$N/sgeval-20261006-03`）。
- 本机对拍：`artifacts/sg-evaluation/sg-eval-gl-20261006-03/compare/run_side.sh <new|orig> <卡>`，一侧 8 片串行；新侧 `run_eval_gl.sh`（席号 50～57），原侧 `run_official_hard.sh`（席号 60～67）；`--dataset hard-verify --max-steps 1300 --groundsg-variant ground-sg-memer --memer-adapter <本机 checkpoint-1300> --episode-wall 3600`。

## ④ 数据与划分

- OOD：`OOD86_MANIFEST=PASS cells=43 total=86 shards=2x43 identity_mismatch=0 keys_sha256=9004f63ad5d08ac37c37260ae75079f9b7f74b2a0d6de2168a19b6b1d07708de`（源 1004 轮 V9 全量 800 局清单，每格按 builder_episode 升序取前 2 局，当前 `ood` builder 逐局反查 tier／seed／spec_sha256）；五模型共用 `shard-00`／`shard-01`。
- hard-verify：`HV192_MANIFEST=PASS tasks=16 per_task=12 total=192 shards=8x24 identity_mismatch=0 keys_sha256=4b86ca9d7dca86bcffca683f0a148d7f38c68b683d745f530ce92936362dbf90`（源 1004 轮第二档 oracle/gate2 清单）；两侧共用 8 片。
- 资产：MemER adapter `ASSETS=PASS asset=memer-checkpoint-1300 files=19 mismatch=0`（HF `Yinpei/vlm_subgoal_predictor@a243356b`，zip sha256 `8483177b…`，本机 `artifacts/sg-eval/ckpt/memer/grounded_subgoal/checkpoint-1300` 与 NFS `$N/sg-eval/ckpt/memer/grounded_subgoal/checkpoint-1300` 逐文件一致）。

## ⑤ 预算（P3 乘式）

| 项 | 轨迹上限 |
|---|---|
| OOD 正式首试 | `5 模型 × 1 种子 × 86 = 430` |
| OOD smoke | `4 模型（GL）× 1 局 = 4`（MemER 的 smoke 在本机，见下） |
| 本机 MemER smoke | `首次 1 + 对拍新侧 1 + 对拍原侧 1 = 3`（首次 smoke 暴露两处缺陷后以新代码重跑新侧，计入 870） |
| 对拍正式首试 | `2 侧 × 16 任务 × 1 档 × 12 局 = 384` |
| 合计硬上限 | 870（首试 821 + 恢复 ≤49）；reset 只计量 |

## ⑥ 硬件、会话与 JobID 清单

- GL 占位 job（全局 ≤4 卡）：`63188714`（gl1518）、`63188715`（gl1503）、`63188716`（gl1527）、`63188719`（gl1525），各 1 × A40，48 h（起跑时剩约 26 h，到期前约 2 h 提交接替）。
- GL 登录节点 `gl-login3` tmux：`p3-smoke-framesamp`、`p3-smoke-smvla`、`p3-smoke-pp`、`p3-smoke-qwenvl`（smoke，均已结束）；正式 worker `p3-worker-14`（job 63188714，2026-10-06 21:25:46 起）、`p3-worker-16`（63188716，21:27:22）、`p3-worker-19`（63188719，21:29:56）、`p3-worker-15`（63188715，21:32 起），各经 `launch_seat.sh` 在占位 job 内跑 `seat_worker.sh`，从 `$R/queue/pending` 按文件名领取 `10/11-smvla`、`20/21-pp`、`30/31-framesamp`、`40/41-qwenvl`、`50/51-memer`（每模型过其 smoke 才入队）；日志 `$R/logs/p3-worker-NN.log`、`$R/logs/tasks/<任务>.log`。
- 本机 tmux：`p3-smoke-memer`、`p3-smoke-memer-new2`、`p3-smoke-memer-orig`、`p3-build-exec`（均已结束）；正式 `p3-local-new`（卡 0）、`p3-local-orig`（卡 1），2026-10-06 21:23:46 起，HEAD `a692d9d4`，日志 `artifacts/sg-evaluation/sg-eval-gl-20261006-03/compare/side-{new,orig}.log`。
- GL smoke（`0816c0a9` 执行副本，BinFill_xhard1_16400000，seed 7）：FrameSamp+Modulation fail 565 步；PonderPounce timeout 1800 步（自身循环退出，`cap_hit=False` 合法）；GroundSG+QwenVL success 1450 步；SimpleMemVLA timeout 1800 步（`cap_hit=True`，第 1801 步进环境前被拒）；四者 `effective_cap=1800 policy_seed=7 server_seed=7`、`OFFICIAL_MEDIA=PASS videos=1`、`LANG_IO=PASS server_text_empty=0`（`--require-server-text`）、`TRACE_ARRAYS=PASS`。

## ⑦ 起跑前 smoke 与闸门（已过）

- 本机 MemER（HEAD `852559f7`）首次：success 325 步、`OFFICIAL_MEDIA=PASS`、`TRACE_ARRAYS=PASS`；暴露 GroundSG 审计文字丢失与 `LANG_IO` 初始帧误报，FIX-1 修复（12.524）。
- 本机 MemER（HEAD `0816c0a9`）新侧：fail 243 步，`OFFICIAL_MEDIA=PASS total=1 videos=1 accepted=1 policy_seed=7`、`LANG_IO=PASS … server_text_empty=0`（`--require-server-text`）、`TRACE_ARRAYS=PASS`，分词通道 task 16／symbolic 16；原侧：success 325 步、官方视频保留于 `official/`、`LANG_IO=PASS`、`TRACE_ARRAYS=PASS`。同局两侧终态不同属 GPU 推理非逐位可复现，计划已注明不据同 seed 宣称逐位一致。
- 代码闸门（12.524 合并后）：核心短测 3253 passed；`UPSTREAM_GUARD=PASS`；`POLICY_SEEDS=PASS models=7 seeds=0,7,42 cases=21`；`EVAL_CAP=PASS models=7 max_steps=1800 rejected_step=1801`；`OBS_EQ=PASS routes=5 mutants_rejected=6/6`；`CLIENT_REPLAY_EQ_SUMMARY=PASS routes=4`（12.522 候选）。

## ⑧ 运行中变更：本机对拍缩减为每任务 3 局（2026-10-06 22:00 EDT）

- 起因：首局实测新侧 977 步耗时 992 s（每次子目标提问约 17 s），按原口径每侧 `16 任务 × 12 局 = 192` 局需 50～65 小时。
- 用户原话（2026-10-06）：「先把Greatlakes跑完再说」→「本机的对拍缩减规模。先给我方案」；主会话给出每任务 2／3／4 局三案（16 任务全保留、两侧同一批、每任务按 builder_episode 升序取前 k 局），用户选「每任务 3 局（推荐）」。
- 新规模：`16 任务 × 1 档（xhard0）× 3 局 = 48`／侧（`HV48_MANIFEST=PASS tasks=16 per_task=3 total=48 keys_sha256=3b4d628dd2355aa702d9aaeadedfac797a2fe49b5c8e4f52cb729393182a4b45`，源 hv192 清单）；对拍轨迹上限由 384 降为 `2 侧 × 48 = 96`。
- 切换：21:58 按清单精确 `tmux kill-session` 停 `p3-local-new`、`p3-local-orig`（删前删后 `tmux ls` 差集恰为二者，显存释放、无残留进程）；被打断的在跑局 BinFill_xhard0_543501（该任务第 9 局，不在新清单）留悬空 attempt、不重跑。21:59:19 以 `compare/run_side48.sh <new|orig> <卡>`（单片、沿用席号 50／60）重启，HEAD `5c8bb233`；已接受的 BinFill_xhard0_540302 两侧复用：新侧 `RUN_PLAN total=48 resume_skip=1 accepted=1 todo=47`、原侧 `ORIG_PLAN total=48 final=1 missing=47`。
- 对拍定位不变：`GATE2=INFO compared=48`，差异报告、不证明等价；报告注明由 192 缩减为 48 的原因。

## ⑨ 运行中裁决：PonderPounce S2 上下文超限按基础设施错误重试（2026-10-06 22:40 EDT）

- 现象：`ood-new-pp-seed7/s20`（PonderPounce 第一片）`VideoPlaceOrder_xhard1_17100000` 第 1 次尝试在第 1661 步服务端报 `observation_failed: RuntimeError: Ponder context overflow at step 1661: S2 context length 16439 exceeds cap 16384`，客户端记 `status=error infra=True infra_reason=pp_server_error`，按基础设施错误领共享重试名额重跑；第 2 次 1057 步 `fail`，账本接受第 2 次。第 1 次局目录的官方重绘失败（`OFFICIAL_RENDER=FAIL … reason=renderer_rc_1`，原始帧照常发布），不影响被接受的第 2 次。该片 `SEAT_DONE done=43 errors=0 infra=1`、`OFFICIAL_RENDER_TALLY ok=43 fail=1`、`SEAT_REC_SYNC=PASS n=44`。截至此时全部 OOD 结果中仅此 1 例。
- 定性：PonderPounce 自身 S2 上下文 16384 token 上限在 1800 步下可被触及（1600 步口径未见），属模型长度上限而非基础设施故障。
- 主会话给出三案（记模型失败不重试／沿用现状当基础设施重试／记 timeout），用户选「沿用现状当基础设施重试」。据此不改代码；`result.md` 单列此类局的个数、身份与两次尝试终态，注明成绩含这些重跑。

## ⑩ 运行中事件：MemER 第一片分片锁撞名、SimpleMemVLA 上限误报（2026-10-06 23:10～23:20 EDT）

- **分片锁撞名**：`50-memer-s00`（GL OOD MemER 第一片）起跑即 `RUN_BLOCKED reason=lease_held … shard=groundsg_ground-sg-memer_seed7_new--shard-00`，0 局执行、零预算消耗。原因：共享账本分片 lease 名由「路线 + 分片文件名」拼成，路线 `groundsg/ground-sg-memer/seed7/new` 不含数据集，本机对拍新侧（`hv48/shard-00.json`）与 GL OOD（`ood86/shard-00.json`）同名而撞锁；保护本身正确（防同分片重复启动），缺陷是 lease 名不区分数据集。处置（不改代码）：`ood86/ood-memer-shard-00.json` 为 `shard-00.json` 的逐字节副本（`cmp` 相同），新任务 `52-memer-s00b`（沿用席号 50）入队，原任务文件留 `queue/failed/` 作记录；23:14:46 由 w14 领取。MemER 第二片 `shard-01.json` 不撞名。
- **SimpleMemVLA 上限误报**：组验收 `EVAL_REPORT=FAIL … cap_mismatch=86`，86 条问题全是 `trace.header.max_steps=1840`（SimpleMemVLA 客户端理论动作上界 115 × 16）；结果行与 trace header 的 `effective_cap=1800`、`exec_over_cap=0`，smoke 实测第 1801 步进环境前被拒。计划八.3 明写该 1840 合法、验收应区分理论循环上界与实际执行 cap。主会话给出两案（按计划修检查器／不改代码留档注明），用户选「按计划修检查器」：子代理 FIX-2 改 `eval_report.py` 的上限核对（trace header 写了 `effective_cap` 时以它为准、不比 header `max_steps`），按审查流程合入后重跑 SimpleMemVLA 组验收；运行中的 GL 与本机任务不受影响（不读该文件）。
- 截至 23:15：FrameSamp+Modulation、PonderPounce 两组七项验收全过（`EVAL_COVERAGE`、`EVAL_REPORT`、`EVAL_VIDEOS`、`OFFICIAL_MEDIA`、`TRACE_ARRAYS`、`LANG_IO`、`VIDEO_LAYOUT` 均 PASS，各 86）；SimpleMemVLA 除上述误报外六项 PASS。

## ⑪ 运行中调度：MemER OOD 由 2 片换为 4 片（2026-10-07 02:13 EDT）

- 起因：MemER 1800 步在 A40 上每局 46～56 分钟（超时局 113 次子目标提问，约 24～30 s／次），两片各 43 局只占 2 席需 22～32 小时，超过 4 个占位 job 剩余约 23 小时；用户「先把Greatlakes跑完再说」。按用户「我授权你自己来管理J0B。尽可能让我少排队」自行调度，不改规模、预算、口径。
- 做法：QwenVL 第一片 02:11 收尾空出一席后，经 `srun --jobid --overlap` 只向两个 MemER 任务的 `run_eval_gl.sh` 主进程（gl1518 PID 2356901、gl1503 PID 4105462，先以父进程号核实）发 TERM，任务自带收尾把已跑完的局全量同步后退出（`V8_SEAT_DONE outcome=aborted rc=143`，`SEAT_REC_SYNC … left=0`；各 1 个 `transcode_fail` 为被打断的半局原始帧，照常发布、未被接受）；worker 不受影响。`scripts/memer_rebalance.py 4` 从各席尝试账本取已接受 8 局（第一片 5、第二片 3），余 78 局按行序交替均分为 `ood86/ood-memer-rb-00..03.json`（20／20／19／19），入队 `60..63-memer-rb*`（席号 53～56，同一 stage）；02:14 起 w15／w19／w14 领 rb0／rb1／rb2（`RUN_PLAN todo=20/20/19`），rb3 待 w16 跑完 QwenVL 第二片后领。被打断的身份在新席从第 1 次尝试开始，共享账本同 token 幂等。
- 截至 02:41：QwenVL 第一片 43／43 完成（`done=43 errors=0 infra=0`）；共享基础设施重试已用 1（PonderPounce 上下文超限那次）。
