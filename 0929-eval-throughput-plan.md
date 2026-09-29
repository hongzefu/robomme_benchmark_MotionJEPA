# 0929 test-hard 评估提速全面测试方案（SimpleMemVLA ＋ MME-VLA，xhard0～xhard4）

> **权威性与锚点**：本文件只规划不实施；每个阶段实跑须按 `AGENTS.md` P3 一次性授权（§5 授权清单）。代码锚点：benchmark 主检出 `newtaskRelease-v5` HEAD `b869eb19`（12.246）；SimpleMemVLA `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA` 分支 `testhard-eval-v7-0929` HEAD `1ca6d1e`；MME-VLA（framesample）`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-testhard-v7` 分支 `testhard-eval-v7-0929` HEAD `4f9e40f`；两者子模块钉 benchmark `4a36d505`。实测来源：NFS `v7-logs/`、`v7-eval/`（2026-09-29 两策略 2 × 1292 局正式评估）；纯推理微基准四组见 [`0929-eval-reload-cost-plan.md`](0929-eval-reload-cost-plan.md) 实测子节（以下简称「重载方案」，本方案的 T1 即其 T1，执行以本方案为准）。commit 编号从 12.247 接续。占位 job：`62268735`、`62476695`、`62476699`（各 16 CPU／192 G／1 A40／48 h，清单 `gl-hold-logs/hold-jobs-evperf-20260929.txt`）。本机 2 × RTX 6000 Ada 可用；aspen 2 × A6000 当前一张被 daiyp 占用。
>
> **用户已定口径（原话逐字）**：①「不要作batch 推理」；②「我只是看重载model和重载env的时间问题」→ 已由重载方案与微基准回答；③「继续工作 给出全面测试的方案」→ 本文件回到原始五问：常驻收益与结果一致性、分发瓶颈、跨硬件一致性、CPU／内存配额。

# 第一部分（给人看）

## 1. 总览

**一句话方案**：先用零成本分析和已测数字定死「哪些提速手段值得测」（模型常驻上限 1.2%，动态队列 12～14%，两策略同卡并行理论上限约 25%，MME 编译缓存每局可省数十秒，CPU 对推理无影响），再按七个阶段实测：插桩剖面 → 同配置 A/A 噪声基线 → 并行形态吞吐 → 跨硬件 → CPU／内存扫描 → MME 编译缓存 → 组合终验；每个阶段有具名判定行，结果一致性只到「行为一致」层级。

### 1.1 已定口径（依据小节）

1. 不做 batch 推理：SimpleMemVLA 保持 `InProcSimPool(1)`、`--group_size 1`（用户原话①）。
2. 一切「结果一致」结论必须先有同硬件同配置的 A/A 噪声基线（§2.2、T2），否则不得下「一致／不一致」判断。
3. 提速手段只用不改推理形态的：进程级并行（两策略同卡、两片同卡）、加席位、动态队列、合并轮次、JAX 持久编译缓存、CPU／内存配额（§2.3～2.6）。
4. 不改 `src/robomme`／`src/robomme_hard`（P2）；插桩与编排全部在策略仓库客户端与 benchmark 仓库 `scripts/injection-dev/`。
5. 局数按乘式列在 §5，一次性授权；xhard0 作为统一样本集（16 任务 × 12 局 = 192，官方身份、已有 A40 两条路线结果可作对照）。

### 1.2 现状与已测数字（不再重测）

| 事实 | 数字 | 来源 |
|---|---|---|
| 整体墙钟 | 06:21 → 12:32（片 9 事故到 13:27），10 席、每片四段串行 | `v7-logs/eval-v7-shard*.log` |
| SimpleMemVLA | 每片每轮 100～147 min；1292 局 946,077 步、146,146 s、0.149～0.157 s/步；timeout 126 局占 33% | `EPISODE_END` 逐局 |
| MME-VLA | 每片每轮 40～58 min；0.080～0.108 s/步（含每局固定）；server 就绪 32～53 s | `eval-mme-*.log`、`episodes.jsonl` |
| 模型加载 | 每进程一次：A40 253～266 s、本机 168～304 s（NFS 冷热）；20 段合计 ≈ 1.4 h，关键路径每片 9 min（2.5%） | 微基准 + 每段固定开销 248～308 s |
| 推理（SimpleMemVLA） | A40 1.69 s／次决策 = 0.105 s/步（68%）；RTX 6000 Ada 0.93 s；与 CPU 数无关 | 微基准 |
| 环境重建 | 每局 `gym.make` + `mplib.Planner` + 在线演示（均值 362 帧、最长 1902）；与仿真渲染录像合计 ≈ 0.05 s/步（32%），内部份额未测 | 子代理梳理 + 反推 |
| MME 每局固定 | 演示长度每变一次 `vision_encode` 重新 jit + cuDNN 调优（`slow_operation_alarm`），无持久缓存；粗回归每局 ≈ 14 s + 首次 RPC 数十秒 | `server.log` |
| 分发 | 静态 LPT 按任务不分档，单轮片间 100～147 min；动态队列每轮省 0.26～0.32 h（12～14%）；席位 10→20 减半 | 调度模拟（实测逐局耗时） |
| 跨硬件 | 生成产物 A40 与 RTX 6000 Ada 不逐位相同；评估同硬件两入口 SimpleMemVLA `status_diff=0/192`、MME `status_diff=11/192` | `docs/greatlakes.md` 二节、v7 README ⑥ |

## 2. 机制与陷阱

### 2.1 时间去哪了（每片 6 h 11 min 的构成）

数轴：`[SimpleMemVLA r1 ≈ 2 h 03][MME r1 ≈ 45 min][SimpleMemVLA r2 ≈ 2 h 00][MME r2 ≈ 45 min]`，四段串行，GPU 任一时刻只被一个策略用；SimpleMemVLA 段内 68% 是 GPU 推理、32% 是 CPU 仿真＋渲染读回＋录像；MME 段内 GPU 大部分时间空转等 client 仿真与编译。**推论**：把 MME 段叠进 SimpleMemVLA 段（同卡并行）理论上限是每片省约 1.5 h（25%），实际取决于两者抢 GPU 与 CPU 的程度，必须实测（T3）。

### 2.2 为什么先做 A/A 噪声基线

- 锚点：RRT* `planning_time=1` 墙钟预算（`motionplanner.py::move_to_pose_with_RRTStar`），评估期 reset 的演示生成会触发；SimpleMemVLA bf16 + sdpa 无 deterministic 设置；MME XLA 自动调优按耗时选算法。
- 已知同硬件重复差异：SimpleMemVLA 两入口 `steps_diff=16/192`、`status_diff=0`；MME `status_diff=11/192`。
- ⚠ 陷阱：任何并行形态都会改变 RRT 的 1 s 内迭代次数，从而改变轨迹；如果没有「什么都不改、再跑一遍」的差异基线，就无法区分「并行改了结果」和「本来就随机」。因此 T2 是 T3／T4／T7 的前置。
- 判定层级只到「行为一致」：逐局 `status` 与 `steps`，比较对象是差异计数，不是字节。

### 2.3 同卡并行（两策略同卡、两片同卡）

- 锚点：`v7-scripts/eval_v7_shard_remote.sh` 的 `for R in 1 2` 串行；`gl_run_testhard.sh` 与 `gl_eval_shard.sh` 都只是 `srun --overlap` 一个步骤，天然可以在同一占位 job 里并排起两个步骤。
- 显存：SimpleMemVLA 11.9 GB；MME `XLA_PYTHON_CLIENT_MEM_FRACTION=0.75` 会预占 75% 显存，须降到 ≤0.4（`51c59b3` 曾从 0.4 提到 0.75，原因待查）才能同卡；A40 46 GB。
- CPU：每个步骤 4 CPU，同卡两步骤要 8 CPU；席位 16 CPU 足够。
- ⚠ 陷阱：(a) 同卡两个进程的 RRT 争抢会改轨迹（§2.2）；(b) `--exact` 下两个 `srun` 步骤各自独占 CPU 集合，不会互相踩；(c) GPU 利用率判读按正本第 16 条：500 ms 采样、均值与 0% 占比，不看中位数。

### 2.4 动态队列 + 合并轮次

- 锚点：清单 `eval-identities-1292.jsonl` 带 `round`／`shard` 字段；`select_rows` 只取本片。改为「每个 worker 从 NFS 上一份共享队列文件按行 claim（`flock` + 追加 claimed 记录）」，`round` 只作为排序键（先 r1 后 r2），不再切片；一个进程跑完整队列直到空。
- 收益上限（§1.2）：每轮 12～14%，另省一次模型加载（每片 4.5 min）。
- ⚠ 陷阱：NFS 上 `flock` 的语义要先验证（T0 夹具，两个进程并发 claim 200 行，无重复无遗漏）；断点续跑以 `episodes.jsonl` 终态为准，claim 记录只是租约。

### 2.5 CPU／内存

- 推理与 CPU 数无关（微基准 4 vs 16 CPU 一样），CPU 只影响 sapien 物理、渲染读回、`imageio` 编码与 MME client；`OMP_NUM_THREADS=1` 必须保留（不设时预处理 8 ms → 288 ms）。
- 内存：SimpleMemVLA RSS 25.2 GB，32 G 席位只剩 ~6 GB 给页缓存与录像缓冲；MME v6 冒烟 MaxRSS 17.8 GB。同卡并行时两者相加 43 GB，席位要 ≥64 G。
- 判据：CPU 从 N 到 2N，`env_step_s` 与 `reset_s` 改善 <5% 即饱和；内存从 32 G 到 64 G，`major_faults` 与模型加载秒数无改善即饱和。

### 2.6 MME 编译缓存

- 锚点：`policy.py::MME_VLA_Policy.__init__` 的 `module_jit`；`vision_encode` 输入 batch = 演示帧数 + 1，每个新长度都重编译；`jax_compilation_cache_dir` 全仓只在 `scripts/train.py` 出现。
- 改法：server 启动设 `JAX_COMPILATION_CACHE_DIR=<NFS 或本机目录>` 并 `jax.config.update("jax_persistent_cache_min_compile_time_secs", 0)`；同一 server 内不同局的相同长度已复用，缓存主要跨 server（跨轮、跨片、跨天）生效。
- ⚠ 陷阱：缓存的是编译产物，自动调优结果随之固定——这反而**减少**一种随机源；但缓存键含 GPU 型号，A40 与 RTX 6000 Ada 不通用。演示长度分布：xhard0 192 局里视频任务约 60 局、长度各异，缓存命中率靠 T6 实测。

### 2.7 跨硬件

- 生成层已证不逐位相同；评估层要问的是「成功率与逐局成败差异是否超过 A/A 基线」。RTX 6000 Ada 推理快 1.8 倍，本机 2 卡 = 约 3.6 个 A40 席位的吞吐，是否可用于正式评估取决于 T4。
- ⚠ 陷阱：本机驱动 570 vs GL 595，torch 同版；策略 venv 在 NFS 上本机可直接用（已验证 import），15 GB checkpoint 先 rsync 到 `/data`（正本第 14 条）。

## 3. 验收表

| 判定 | 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|---|
| G0 夹具 | 队列 claim 无重复无遗漏；插桩不改 benchmark | 两进程并发 claim 200 行夹具；`git diff --quiet HEAD -- src/` | 编排与插桩零侵入 | `QUEUE_FIXTURE=PASS rows=200 dup=0 missing=0`；`TIMING_PATCH=PASS bench_diff=0` |
| G1 剖面 | 每局 make_env／reset(demo)／首次推理／推理均值／env_step 均值／video_save／close | `timing.jsonl` 按任务 p50／max | 环境重建与每步各占多少 | `ENV_REBUILD=PASS policy=<p> episodes=16 make_env_p50=… reset_p50=… env_step_mean=… infer_mean=… fixed_share=…%` |
| G2 A/A 基线 | 同硬件同配置重跑 xhard0 192 局 vs 已有 v7 路线结果 | 逐局 `status`／`steps` 差异计数，按任务分布 | 后续一切「一致」判断的尺子 | `AA_BASELINE=PASS policy=<p> compared=192 status_diff=… steps_diff=… success_a=… success_b=…` |
| G3 并行吞吐 | 三种同卡形态的每步耗时、GPU util 均值／0% 占比、CPU 占用 | 固定 32 局集，各形态一遍；`nvidia-smi -lms 500` 单持久进程采样，先做有／无采样对照 | 哪种形态每席位吞吐最高、代价多大 | `PARALLEL_FORM=INFO form=<f> smvla_s_per_step=… mme_s_per_step=… gpu_util_mean=… gpu_zero_pct=… cpu_used=…` |
| G4 跨硬件 | 本机 RTX 6000 Ada 跑 xhard0 192 局 × 2 策略 vs A40 结果与 G2 基线 | `status_diff` 与成功率差；差异 ≤ G2 基线 + 二项 95% 区间 | 本机能否作为正式评估算力 | `XHW_PARITY=PASS|FAIL policy=<p> compared=192 status_diff=… baseline=… success_local=… success_a40=…` |
| G5 CPU／内存 | 1/2/4/8 CPU、32/64 G 下 `env_step_s`、`reset_s`、模型加载、major faults | 4 任务 × 1 局固定集，比较相位耗时 | 席位规格定多少不再是瓶颈 | `CPU_SWEEP=INFO policy=<p> cpus=<n> env_step_mean=… reset_p50=… saturated=<yes/no>`；`MEM_SWEEP=INFO …` |
| G6 编译缓存 | MME 开缓存前后每局首次 `add_buffer` 与首次 `infer` 秒数；逐局 status/steps | 同 16 局两遍 | 每局省多少秒；行为不变 | `JAX_CACHE=INFO episodes=16 first_add_buffer_before=… after=… hit=…/16 status_diff=…` |
| G7 终验 | 组合配置跑 xhard0 192 局 × 2 策略，墙钟与结果 | 三席位；与 §1.2 基线投影比 | 最终提速倍数与结果一致性 | `THROUGHPUT_FINAL=PASS wall_h=… baseline_proj_h=… speedup=… status_diff_vs_AA=…` |

## 4. 实施步骤

| 阶段 | 内容 | 局数（乘式） | 判据 |
|---|---|---|---|
| 0 | 零成本：调度模拟、常驻上限、MME 每局固定回归（已完成，见 §1.2）；队列夹具与插桩零侵入 | 0 | G0 |
| T0 | 插桩后本机冒烟 | 2 策略 × 1 任务 × 1 档 × 1 局 = 2 | `timing.jsonl` 七段齐全 |
| T1 | 剖面（GL A40，4 CPU／32 G，与正式一致；含模型加载冷热两次） | 2 策略 × 16 任务 × 1 档（xhard0）× 1 局 = 32 | G1 |
| T2 | A/A 噪声基线（GL A40，v7 路线不改任何配置，重跑一遍） | 2 策略 × 16 任务 × 1 档（xhard0）× 12 局 = 384 | G2 |
| T3 | 并行形态：(a) SimpleMemVLA＋MME 同卡 8 CPU；(b) SimpleMemVLA × 2 片同卡 8 CPU；(c) MME 1 server + 2 client 同卡 | 3 形态 × 2 策略 × 16 任务 × 1 档 × 1 局 = 96 | G3 |
| T4 | 跨硬件：本机 RTX 6000 Ada（GPU0／GPU1 各一策略） | 2 策略 × 16 任务 × 1 档（xhard0）× 12 局 = 384 | G4 |
| T5 | CPU 1/2/4/8 与内存 32/64 G（`srun --cpus-per-task` / `--mem` 步骤内限制） | CPU：4 档 × 2 策略 × 4 任务 × 1 档 × 1 局 = 32；内存：1 档（64 G）× 2 策略 × 4 任务 × 1 局 = 8 | G5 |
| T6 | MME 持久编译缓存前后 | 2 遍 × 1 策略 × 16 任务 × 1 档 × 1 局 = 32 | G6 |
| T7 | 组合终验：动态队列 + 合并轮次 + T3 选出的同卡形态 + T5 规格 + T6 缓存，三席位 | 2 策略 × 16 任务 × 1 档（xhard0）× 12 局 = 384 | G7 |
| 8 | 留档 `docs/validation/eval-throughput-20260929/`、commit、push、按清单释放三个占位 job | 0 | 第二部分 §七 |

合计 2 + 32 + 384 + 96 + 384 + 40 + 32 + 384 = **1354 局**（全部 xhard0 官方身份，不新增任何 reset 抽样；xhard4 长演示局未覆盖，见盲区）。预计墙钟：T2 三席位并行约 2 h，T4 本机约 3.5 h（与 T2 同时），T3＋T5＋T6 约 4 h，T7 约 2 h；全程约 1.5 天，多数时段无人值守（Monitor + tmux）。

## 5. 一次性授权清单（P3）

1. 局数：上表 1354 局；若只批核心，最小集为 T0＋T1＋T2＋T3＋T7 = 898 局（跨硬件 T4、CPU／内存 T5、缓存 T6 可单独勾选）。
2. 席位：现有三个占位 job（62268735、62476695、62476699）继续使用到阶段 8 释放；不再新增。
3. 本机：GPU0／GPU1 用于 T0、T4；15 GB checkpoint rsync 到 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/eval-throughput-20260929/ckpt/`（结束后删）。
4. 策略仓库改动：插桩、队列 worker、`ROUNDS` 合并、JAX 缓存开关，各自新分支 `eval-throughput-0929`，不推 GitHub（沿用 v7 口径）。
5. T2 的 A/A 重跑结果与 v7 路线原结果都保留，不覆盖 `v7-eval/`。

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

- R1 不改 `src/robomme/`、`src/robomme_hard/`；benchmark 仓库只新增 `scripts/injection-dev/eval_queue.py`、`scripts/injection-dev/eval_timing_report.py`、留档目录。
- R2 不做 batch 推理、不用 `--pipelined`、不改 `execute_horizon`、不改 `TIER_MAX_STEPS`。
- R3 产物落 NFS `v7-eval-stage/eval-throughput/` 与本机 `artifacts/eval-throughput-20260929/`；不写 `v7-eval/`、`SimpleMemVLA/logs/testhard/v7/`。
- R4 `srun` 步骤严格按阶段串行；同卡并行只在 T3／T7 的形态里发生且有采样对照。
- R5 GPU 采样按正本第 16 条：单个持久 `nvidia-smi --query-gpu=... -lms 500` 进程只查本席位 GPU，先在 T1 做有／无采样的步时对照并记录开销。
- R6 超出 §5 授权的任何补跑先停再问；单局 error 只按现有 3 遍重试，不为成功率重试。

## 一 现有能力与拟新增

| 项 | 现有 | 拟新增 |
|---|---|---|
| 逐局计时 | SimpleMemVLA 整局 `elapsed_s`；MME 无 | 两客户端 `timing.jsonl`：`process`（import、model_load、first_infer）＋逐局 `make_env`、`reset_total`、`demo_frames`、`first_infer`、`infer_n/infer_total`、`env_step_n/env_step_total`、`video_save`、`close`；MME 保留 server 回包 `reset_time_ms`／`add_buffer_time_ms`／`infer_time_ms` |
| 分片 | 静态 `round`／`shard` | `eval_queue.py`：`init`（从清单生成队列文件）、`claim`（`flock` 追加租约，返回下一行）、`status`；两策略 `select_rows` 增加 `--queue <文件>` 模式 |
| 轮次 | 每轮一进程／一 server | SimpleMemVLA `--round 1,2`；MME `ROUNDS="1 2"` 复用 server |
| 同卡并行 | 无 | `eval_v7_shard_remote.sh` 派生 `eval_parallel_form.sh <form>`：在同一 `JOBID` 并排起两个 `srun --overlap --exact --cpus-per-task=4`，MME `XLA_PYTHON_CLIENT_MEM_FRACTION=0.4` |
| JAX 缓存 | 无 | `gl_eval_shard.sh` 传 `JAX_COMPILATION_CACHE_DIR`；`serve_policy.py` 启动时 `jax.config.update` 三项 |
| 采样 | 无 | `gpu_sampler.sh`：`nvidia-smi -i $GPU --query-gpu=utilization.gpu,memory.used --format=csv -lms 500 > <log>`；`pidstat -p <pid> 1` |
| 报告 | 无 | `eval_timing_report.py`：读 `timing.jsonl`、`episodes.jsonl`／`results-*.jsonl`、采样日志，输出 G1～G7 判定行 |

## 二 逐文件改动清单

1. `SimpleMemVLA/robomme_sim/testhard_eval.py`：`perf_counter` 打点（`build_policy`、`pool.reset`、`generate_batch`、`pool.step`、`save_video`、`close`），进程级与逐局写 `timing-*.jsonl`；`--round` 多值；`--queue` 模式（调用 `eval_queue.claim`）。不改 `InProcSimPool`、`eval_success.py`。
2. `SimpleMemVLA/scripts/run_testhard.sh`、`gl_run_testhard.sh`：透传新参数，`--cpus-per-task` 与 `--mem` 从环境变量取（T5）。
3. `robomme_policy_learning-testhard-v7/examples/robomme/eval.py`、`env_runner.py`：同样打点；保留 server 三个 `*_time_ms`；`--queue` 模式。
4. `robomme_policy_learning-testhard-v7/scripts/gl_eval_shard.sh`、`serve_policy.py`：`ROUNDS` 循环、`JAX_COMPILATION_CACHE_DIR`、`XLA_PYTHON_CLIENT_MEM_FRACTION` 可配。
5. benchmark `scripts/injection-dev/eval_queue.py`（`flock` 租约队列，附 `tests/lightweight/test_eval_queue.py` 两进程并发夹具）、`scripts/injection-dev/eval_timing_report.py`。
6. NFS `v7-scripts/eval_parallel_form.sh`、`gpu_sampler.sh`（编排脚本留档时逐字抄进 `launch.md`，不放 `.sh` 到 `docs/`）。

## 三 闸门总表

G0～G7 见第一部分 §3。串行依赖：G0 → T0 → T1 → T2 →（T3、T4、T5、T6 可并行）→ T7。任何 G 为 FAIL 只记证据与候选修法，不放宽阈值。

## 四 runbook

```bash
# 席位：62268735 gl1518 / 62476695 gl1525 / 62476699 gl1513（16 CPU／192 G／A40）
# 统一样本集：xhard0 官方身份，取自 v7-eval/eval-identities-1292.jsonl 的 tier==xhard0（192 行）
# T1（每策略一个进程，4 CPU／32 G，登录节点 tmux，会话名 evtp-t1-<policy>）
srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=4 --mem=32G --gpu_cmode=shared \
  /usr/bin/env OUT=<NFS>/v7-eval-stage/eval-throughput/t1/smvla IDENTITIES=<NFS>/v7-eval-stage/eval-throughput/ids-xhard0-16.jsonl ROUND=1 SHARD=0 \
  bash scripts/run_testhard.sh
# T2（三席位各跑 64 局队列，会话名 evtp-t2-<k>）：IDENTITIES=ids-xhard0-192.jsonl QUEUE=<NFS>/.../t2/queue.jsonl
# T3（形态 a）：同一 JOBID 并排两个 srun，各 --cpus-per-task=4；MME 侧 XLA_PYTHON_CLIENT_MEM_FRACTION=0.4 PORT=8500
# T4（本机）：tmux evtp-t4-<policy>，CUDA_VISIBLE_DEVICES=0|1，OMP_NUM_THREADS=1，taskset -c 4 核，ckpt 用 /data 副本
# T5：srun --cpus-per-task=<1|2|4|8> [--mem=64G]，同 4 任务清单 ids-xhard0-4.jsonl
# T6：JAX_COMPILATION_CACHE_DIR=<NFS>/v7-eval-stage/eval-throughput/jax-cache，同 16 局跑两遍
# Monitor 过滤：EPISODE_END|TESTHARD_DONE|EVAL_RC|EXIT_CODE=|Traceback|NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT|RETRY_CAP_HIT
```

样本清单：`ids-xhard0-192.jsonl`（全部 xhard0）、`ids-xhard0-16.jsonl`（每任务 `episode` 最小的一局）、`ids-xhard0-4.jsonl`（PickXtimes、VideoPlaceButton、ButtonUnmaskSwap、BinFill 各一局，覆盖无演示长局／长演示／碰撞检查／多目标）。

## 五 风险登记

- NFS `flock` 语义：T0 夹具不过则改为「每 worker 预分配 + 完成后从共享余量取」的两级方案。
- MME 显存分数降到 0.4 可能触发 OOM（`51c59b3` 曾上调）：T3(a) 先用 16 局试，OOM 即记 FAIL 并回 0.75 单卡独占。
- 同卡并行改变 RRT 结果：由 G2 基线量化；若 T3 的 `status_diff` 超基线，则该形态只用于非正式评估。
- 本机页缓存与 NFS：T4 模型加载走 `/data` 副本；MME 权重 6.4 GiB 同样复制。
- 采样干扰：R5 的有／无对照；超过 2% 步时差即改为 5 s 间隔。
- 4096 步位置编码上限（MME）：xhard0 不触发；xhard4 长演示局另立项。

## 六 盲区诚实清单

- 全部样本是 xhard0；xhard1～4 的回注与更长步数上限未覆盖，终验倍数外推到五档时按步数比例估算，不作实测承诺。
- `planner_init` 与 `demo_exec` 无法从 `DemonstrationWrapper` 外侧拆开，只能靠 `demo_frames` 回归。
- 一致性只到行为层级；RRT 回退局天然不可逐位复现。
- daiyp 的 0.436 s／次配置未取得，与其对齐（flash-attn、代码版本）不在本方案内。

## 七 留档与 commit 纪律

- 留档 `docs/validation/eval-throughput-20260929/{launch.md,result.md,records/}`：records 只放 `timing.jsonl`、清洗后日志、采样统计、判定行；不放 sh／yaml／视频／权重。
- 策略仓库：分支 `eval-throughput-0929`，不推送。benchmark：本方案 12.247；实测结果以子节追加在 §4 之后。
- 收尾：`tmux ls` 删前删后各一次，只按会话名清单 `kill-session -t '=名'`；占位 job 按 `hold-jobs-evperf-20260929.txt` 逐个 `scancel`（62268735 属 v7 清单，同样列出后释放）。
