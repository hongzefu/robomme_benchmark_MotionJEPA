# 0929 评估链路「重载模型／重载环境」耗时调查与测试方案

> **权威性与锚点**：本文件只规划不实施；每一步实跑都须单独获批（局数按 `AGENTS.md` P3 一次性授权）。代码锚点：benchmark 主检出 `newtaskRelease-v5` HEAD `753aeb8f`（12.244）；SimpleMemVLA `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA` 分支 `testhard-eval-v7-0929` HEAD `1ca6d1e`；MME-VLA（代码里叫 framesample）`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning-testhard-v7` 分支 `testhard-eval-v7-0929` HEAD `4f9e40f`；两者子模块钉 benchmark `4a36d505`（12.237）。实测数据来源：NFS `v7-logs/eval-{smvla,mme}-v7-r{1,2}-s{0..9}.log` 与 `v7-eval/mme-v7-r*-s*/.../episodes.jsonl`（2026-09-29 两策略 2 × 1292 局正式评估）。commit 编号沿用 `<大>.<小>[.<修订>] <中文描述>`，从 12.245 接续。占位 job：`62268735`（v7-hold，16 CPU／192 G）、`62476695`、`62476699`（evperf-hold，16 CPU／192 G，清单 `gl-hold-logs/hold-jobs-evperf-20260929.txt`），三者都是 1 A40／48 h。
>
> **用户已定口径（原话逐字）**：①「不要作batch 推理」——SimpleMemVLA 保持 `InProcSimPool(1)` 与 `--group_size 1`，不碰 `--pipelined`；②「我只是看重载model和重载env的时间问题」——本方案只回答这一问，CPU／内存配额、跨硬件一致性、动态队列只在 §1.3 给已有数据的结论，不排测试。

# 第一部分（给人看）

## 1. 总览

**一句话方案**：先用已有 40 段日志算清「模型每段重载」的代价上限（约 3～4%），再给两个策略客户端各加一层进程内计时（不动 `src/robomme`、不动 `robomme_hard`），在 GL A40 上按正式配置各跑 16 任务 × 1 档 × 1 局，把「每局重建环境」拆成 gym.make／规划器初始化／演示在线执行／首次推理／收尾五段实测出来，最后用一组 A/A 对照回答「模型跨轮常驻会不会改评估结果」。

**已定口径**（依据小节）：

1. 不做 batch 推理（用户原话①；§2.1）。
2. 只测重载模型与重载环境的时间（用户原话②；§3）。
3. 环境常驻不在本轮实施：seed 与规格是环境构造参数，常驻要改 `src/robomme_hard`（P2 逐个批准）且演示段在线执行无法跳过（§2.3）；本轮只测出它值多少时间。
4. 模型常驻只考虑「同片两轮合一个进程／server 跨轮不重启」，收益上限按 §1.3 的实测给死，不预设一定要做。
5. 局数：全部实跑合计 2 策略 × 16 任务 × 1 档 × 1 局 = 32 局（T1）＋可选 T2 的 2 策略 × 16 任务 × 1 档 × 3 局 × 3 遍 = 288 局，按 P3 一次性授权（§4）。

### 1.1 现状：模型加载的频次与位置

| 策略 | 加载点（文件::函数） | 频次 | 每次做什么 |
|---|---|---|---|
| SimpleMemVLA | `robomme_sim/testhard_eval.py::main` 在逐局循环前调 `eval_success.py::build_policy` → `policy.py::get_vla` | **每进程一次** = 每片每轮一次（10 片 × 2 轮 = 20 次，重试遍数另计） | 从 NFS 读 15 GB safetensors、转 bf16、`.to("cuda:0")`、加载 `AutoProcessor`；无 compile、无预热 |
| MME-VLA | `scripts/gl_eval_shard.sh` 起 `serve_policy.py` → `policy_config.py::create_trained_policy` | **每片每轮一次 server**（20 次）；客户端最多 3 遍只重启 client，server 不重启 | orbax 恢复 6.4 GiB bf16 参数（约 13 s）、`module_jit` 懒编译；首次 `sample_actions` 编译一次，`vision_encode` 每遇新的演示长度重新编译并 cuDNN 自动调优，无持久编译缓存 |

每局对策略侧只做 `buffer.reset()`／`policy.reset()`（清缓冲、重设种子），**不重载权重**。所以「每次都会重新加载模型」不成立；成立的是「每片每轮重新加载一次」。

### 1.2 现状：环境重建的频次与内容（两策略相同）

每局一次，全在 benchmark 侧：

1. `hard_builder.py::BenchmarkEnvBuilder.make_env_for_episode` → `gym.make(env_id, seed=…, difficulty=tier, sampling_config=…, native_episode_spec=…)`：ManiSkill `sapien_env.py` 在 `__init__` 里就 `reset(options=dict(reconfigure=True))`，新建 `PhysxCpuSystem`、`RenderSystem`、加载机器人 URDF、桌面与物体、两个 256² 相机。
2. `DemonstrationWrapper.reset`：每局新建 `mplib.Planner`（解析 URDF/SRDF），然后把演示段**在线逐步执行**（每帧物理＋渲染），screw 失败退 RRT*（1 s 墙钟预算、最多 3 次）。评估期不读任何演示 h5。MME 1296 行记录里 `demo_frames` 均值 362，最长 1902（VideoPlaceOrder/78）。
3. 局末 `env.close()` → `_clear()` + `gc.collect()`；robomme 层没有跨局缓存。

这三段的耗时**现在没有任何单独计时**：SimpleMemVLA 只有整局 `elapsed_s`（含 reset、推理、仿真步、写 mp4）；MME 连整局耗时都没记，server 回包里的 `reset_time_ms`／`add_buffer_time_ms`／`infer_time_ms` 被客户端丢弃。

### 1.3 已有日志能算出的数字

**SimpleMemVLA 每段固定开销**（每片每轮墙钟 − 该段逐局 `elapsed` 之和；含 srun、NFS import、模型加载、逐任务身份核对、收尾）：

| 段 | r1 s0 | s1 | s2 | s3 | s4 | s5 | s6 | s7 | s8 | r2 s0 | s1 | s2 | s3 | s4 | s5 | s6 | s7 | s8 | s9 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 秒 | 262 | 259 | 306 | 304 | 308 | 305 | 303 | 308 | 306 | 261 | 265 | 253 | 248 | 274 | 249 | 250 | 251 | 253 | 265 |

（r1 s9 的 8763 s 是 ControlMaster 事故等待，不计。）20 段均值约 275 s，合计约 1.5 h GPU 时间；SimpleMemVLA 逐局合计 146,146 s = 40.6 h，**固定开销占 3.6%**；落到每片关键路径是 2 × 275 s ≈ 9 min，占每片 6 h 11 min 的 2.5%。

**MME server 就绪**：20 段各 32～53 s（`LAUNCH` 到 `端口就绪`），加首次 `sample_actions` 编译（未单独计时）。每片每轮墙钟 2376～3463 s，折合 0.080～0.108 s/步（含每局固定开销与演示段）。按片间「步数差 → 墙钟差」粗回归，每局固定开销约 14 s，但这是估算，不进判定。

**逐步开销才是大头**：SimpleMemVLA 五档一致 0.149～0.157 s/步；126 局 timeout 合计 13.5 h（33%）。**结论：即使把模型重载压到零，SimpleMemVLA 也只快 3～4%；环境重建的真实占比要靠 §3 的插桩测出来。**

（顺带，非本方案范围）分发层：静态 LPT 分片按任务均值、不分档，SimpleMemVLA 单轮片间 100～147 min；用实测逐局耗时模拟，动态队列每轮省 0.26～0.32 h（12～14%），席位 10 → 20 减半。跨硬件：`docs/greatlakes.md` 第二节已证 RTX 6000 Ada 与 A40 产物不逐位相同。

## 2. 机制与陷阱

### 2.1 模型常驻能做到哪一步

- **定义**：同一片两轮合并到一个进程（SimpleMemVLA）／同一片两轮共用一个 server（MME）。
- **锚点**：SimpleMemVLA `gl_run_testhard.sh` 每轮调一次 `srun … run_testhard.sh --round R`；`testhard_eval.py::select_rows` 只取 `round==r`。MME `gl_eval_shard.sh` 每次调用起一个 server、`trap cleanup EXIT` 收掉。
- **数轴**：每片现在 4 段 = 2 次 SimpleMemVLA 加载 + 2 次 server 启动；合并后 = 1 + 1，省 1 × 275 s + 1 × ~45 s ≈ 5.3 min/片。
- ⚠ **陷阱**：(a) 进程常驻更久，SimpleMemVLA RSS 26.6 GB 在 32 G 席位下留给页缓存不到 6 GB，两轮 130 局的 mp4 缓冲与 NFS 读会挤；(b) MME server 常驻会累积 `vision_encode` 的各种演示长度编译体，显存 `XLA_PYTHON_CLIENT_MEM_FRACTION=0.75` 之内；(c) 不做 batch，所以两轮合并仍是串行，不省逐局时间。
- **收益**：上限就是 §1.3 的 5.3 min/片（1.4%）。

### 2.2 环境重建为什么每局都得做

- **锚点**：`hard_builder.py::_hard_env_kwargs` 把 `seed`、`difficulty`、`sampling_config`、`native_episode_spec` 作为 **构造参数** 传给 `gym.make`；环境 `__init__` 里 `self.generator.manual_seed(seed)`（如 `BinFill.py`），`env.reset()` 不接 seed。要换局就得换对象。
- ManiSkill 的 `reconfiguration_freq` 只管同一 env 对象的后续 reset，robomme_hard 各环境没用它。
- ⚠ **陷阱**：把 reset 改成可换 seed／规格，就是改 `src/robomme_hard`（P2 逐个批准），而且要证明与「重建对象」逐位等价（生成期已证 `WORKER_ISOLATION=PASS` 只覆盖「同进程连续重建」，不覆盖「同对象换 seed」）。本轮不做。

### 2.3 演示段在线执行不可跳过

- 策略在 reset 后拿到的是演示帧序列（`front_rgb_list` 含全部演示帧），必须由环境跑出来；替换成回放 h5 会改变策略看到的像素（gen1 h5 是 A40 上另一次运行的产物）且引入 828 GB 数据依赖。**只列为后续选项，不推荐。**
- ⚠ RRT* 的 1 s 墙钟预算让触发回退的局不可逐位复现（`docs/validation/newtask-v2/README.md`；v6 `EVAL_DEMO_FRAMES=INFO exact=1054/1100`）。因此 §3 的 A/A 对照必须先测同配置重复的基线噪声，再看常驻有没有额外偏差。

## 3. 验收表

| 判定 | 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|---|
| G1 插桩零侵入 | 计时只加在策略客户端，benchmark 不动 | `git diff --quiet HEAD -- src/` 在 benchmark 为空；两策略仓库 diff 只含 `timing` 相关行 | 测出的数字就是正式链路的数字 | `TIMING_PATCH=PASS bench_diff=0 files=<n>` |
| G2 模型加载实测 | 每进程 import／权重加载／首次推理三段 | 每个进程写 `timing.jsonl` 首条 `phase=process` | 得到 SimpleMemVLA 与 MME 各自的「重载模型」真实秒数（含 NFS 冷／热两遍） | `MODEL_LOAD=PASS policy=<p> runs=2 import_s=… load_s=… first_infer_s=…` |
| G3 环境重建实测 | 每局 make_env／planner_init／demo_exec／first_infer／video_save／close 六段 | 逐局 `timing.jsonl`，按任务出 p50／max；`demo_exec` 与 `demo_frames` 回归 | 得到「每局重建环境」真实秒数及其在整局里的占比 | `ENV_REBUILD=PASS policy=<p> episodes=16 make_env_p50=… demo_exec_p50=… fixed_share=…%` |
| G4 常驻收益上限 | 用 G2／G3 数字 × 正式评估的段数与局数 | 脚本 `reload_budget.py` 读两份 `timing.jsonl` 与 v7 逐局记录 | 回答「保持常驻能提升多大」——给的是上限，不是承诺 | `RESIDENT_GAIN=INFO model_resident_pct=… env_resident_pct=… per_shard_min=…` |
| G5（可选）A/A 一致性 | 同一 48 局：两进程按轮拆 vs 一进程合并 vs 一进程再跑一遍 | 逐局比 `status`／`steps`；先算「同配置重跑」的基线差异 | 常驻的逐局差异不超过基线差异 → 「结果一致」只能到这个层级 | `RESIDENT_AA=PASS policy=<p> compared=48 split_vs_merged_status_diff=… baseline_status_diff=…` |

## 4. 实施步骤（局数按 P3 写乘式，等一次性授权）

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 用现有 40 段日志出 §1.3 的表（已完成，零局数） | 本文件 §1.3 |
| 1 | 两策略客户端加计时（第二部分 §二），本机各跑 1 任务 × 1 档 × 1 局冒烟（2 局） | G1、`timing.jsonl` 六段齐全 |
| 2 | **T1**：GL A40、`srun` 步骤内 4 CPU／32 G（与正式一致），每策略一个进程跑 16 任务 × 1 档（xhard0）× 1 局 = 16 局；模型加载的 NFS 冷／热差异用「同席位紧接着再起一次进程、只加载模型即退出（0 局）」取第二次数字；共 2 策略 × 16 × 1 × 1 = **32 局** | G2、G3、G4 |
| 3 | **T2（可选）**：每策略取 16 任务 × 1 档（xhard0）× 3 局 = 48 局，跑三遍：按轮拆两进程、合并一进程、合并再跑；2 策略 × 48 × 3 = **288 局** | G5 |
| 4 | 留档 `docs/validation/eval-reload-20260929/`，commit、push，按清单 `scancel` 三个占位 job | 第二部分 §七 |

授权项（一口气）：T1 32 局＋冒烟 2 局＝34 局（单 worker，超过 10 需授权）；T2 288 局（可选，请明确要不要）；三个占位 job 的使用与释放时点。

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

- R1 不改 `src/robomme/`、`src/robomme_hard/`（P2）；计时全部在策略仓库客户端用包装函数打点。
- R2 不做 batch 推理、不启用 `--pipelined`（用户原话①）。
- R3 T1／T2 的产物只落 NFS `v7-eval-stage/eval-reload/` 与本机 `artifacts/eval-reload-20260929/`，不覆盖 v7 正式结果（`v7-eval/`、`SimpleMemVLA/logs/testhard/v7/`）。
- R4 每次 `srun` 步骤严格串行，不与探针重叠（v6 已踩过 compute mode 异常）。
- R5 局数一律写乘式；超出 §4 授权的任何补跑先停再问。

## 一 现有能力与拟新增

| 项 | 现有 | 拟新增 |
|---|---|---|
| SimpleMemVLA 计时 | 整局 `elapsed_s`、`max_rss_kib` | `timing.jsonl`：`process`（t_import、t_model_load、t_first_infer）、逐局 `make_env`、`reset_total`、`planner_init`（从 `DemonstrationWrapper` 外侧无法拆，改用 reset 前后 `demo_frames` 回归）、`first_infer`、`infer_total/n`、`env_step_total/n`、`video_save`、`close` |
| MME 计时 | server 回包 `reset_time_ms`／`add_buffer_time_ms`／`infer_time_ms`（客户端丢弃） | 客户端保留三者并累计；加 `make_env`、`reset_total`、`first_add_buffer`（含 `vision_encode` 重编译）、`video_save`、`close`；server 启动到端口就绪、首次 `sample_actions` 编译 |
| 轮次合并 | 每轮一进程／一 server | SimpleMemVLA `--round` 允许 `1,2`；MME `gl_eval_shard.sh` 允许 `ROUNDS="1 2"` 复用 server（仅 T2 用） |
| 预算脚本 | 无 | `scripts/injection-dev/reload_budget.py`（读 `timing.jsonl` 与 v7 `results-*.jsonl`／`episodes.jsonl`，输出 G4 判定行） |

## 二 逐文件改动清单

1. `SimpleMemVLA/robomme_sim/testhard_eval.py::main`：用 `time.perf_counter()` 包住 `build_policy`、`pool.reset`、`batched.generate_batch`、`pool.step`、`save_video`、`pool.services[0].close()`；进程级三段写一次，逐局写一行到 `$OUT/timing-r{round}-shard{i:02d}of{n:02d}.jsonl`。不改 `InProcSimPool` 与 `eval_success.py`。
2. `SimpleMemVLA/scripts/run_testhard.sh`：透传 `--round` 多值；无其他改动。
3. `robomme_policy_learning-testhard-v7/examples/robomme/eval.py::evaluate` 与 `env_runner.py`：`make_env`、`get_init_obs`、`step`、`save_video`、`close_env` 打点；`EpisodeEvaluator` 保留 server 回包三个 `*_time_ms`；逐局写 `<SAVE_ROOT>/.../timing.jsonl`。
4. `robomme_policy_learning-testhard-v7/scripts/gl_eval_shard.sh`：打印 `SERVER_START`／`SERVER_READY` 的秒级时间戳（已有 `端口就绪`，补 epoch 秒）；T2 用的 `ROUNDS` 循环。
5. benchmark 仓库：新增 `scripts/injection-dev/reload_budget.py`（只读分析）与留档目录；不改 `scripts/` 顶层（P1）。

## 三 闸门总表

G1～G5 见第一部分 §3；每条判定行原文进留档 `result.md`。G5 的「一致」层级只到「行为一致（status/steps 逐局）」，不声称字节级。

## 四 runbook

```bash
# 席位（已 RUNNING）：62268735 gl1518、62476695 gl1525、62476699 gl1513
# T1 SimpleMemVLA（登录节点 tmux，会话名 evreload-smvla-<k>）
srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=4 --mem=32G --gpu_cmode=shared \
  /usr/bin/env OUT=<NFS>/v7-eval-stage/eval-reload/smvla ROUND=1 SHARD=0 IDENTITIES=<NFS>/v7-eval-stage/eval-reload/ids-xhard0-16.jsonl \
  bash scripts/run_testhard.sh
# T1 MME：同上改 gl_eval_shard.sh，PORT=8500，SAVE_ROOT=<NFS>/v7-eval-stage/eval-reload/mme
# Monitor 过滤：EPISODE_END|TESTHARD_DONE|EVAL_RC|EXIT_CODE=|Traceback|NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT
```

身份清单 `ids-xhard0-16.jsonl`：每任务取 v7 清单里 xhard0 的第一局（`episode` 最小），`round=1 shard=0`。

## 五 风险登记

- 计时本身有开销（`perf_counter` 调用与逐局写 NFS 小文件）：进程内缓存、局末一次写；不做零干扰声明。
- NFS 冷缓存会让第一次模型加载偏大：T1 每策略连起两个进程，报两次数字。
- 4096 步位置编码上限（MME `mem_buffer.py` 默认 `max_steps=4096`）：xhard0 演示最长不超此限，T1 不触发；正式评估里 VideoPlaceOrder/78 的 error 由此而来，另立项。

## 六 盲区诚实清单

- `planner_init` 与 `demo_exec` 在 `DemonstrationWrapper.reset` 内部，外侧只能测 `reset_total`；拆分靠 `demo_frames` 回归，非直接测量。
- T1 只覆盖 xhard0，演示最长的 xhard4 局（1902 帧）未测；要测须再加 16 任务 × 1 档（xhard4）× 1 局 = 16 局，另行授权。
- 结果一致性只能到「行为一致」层级；RRT 回退局天然不可逐位复现。

## 七 留档与 commit 纪律

- 留档 `docs/validation/eval-reload-20260929/{launch.md,result.md,records/}`，records 只放 `timing.jsonl`、清洗后日志与判定行；不放 sh／yaml、不放视频。
- 策略仓库改动各自 commit 到 `testhard-eval-v7-0929` 之上的新分支 `eval-reload-0929`，不推送到 GitHub（沿用 v7 口径，留用户决定）。
- benchmark 仓库：本方案 12.245；实测结果以子节追加到本文件 §4 之后，不改写原计划。
