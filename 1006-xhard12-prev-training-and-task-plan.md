# xhard 新档的上次训练参照与官方 hard 档统计（留档）

> **本文是留档，不是计划。** 它只记录事实：上次 MotionJEPA 训练与 policy 评估是怎么做的、newtask-v2 交付集长什么样、官方参考数据 hard 档的统计、16 个任务 hard 配置的源码核查结果，以及尚未核实的项。xhard 新档「改什么、改成多少、怎么验收、怎么分工」全部在 [`1006-xhard12-env-plan.html`](1006-xhard12-env-plan.html)，本文不含任何方案或取值。文件名沿用首次创建时的名字（2026-10-06，`MMDD-<主题>-plan.md` 体例），内容在 2.32 改为纯留档。
>
> **数字分三类**：**[实测]** 来自读文件或跑脚本；**[文档]** 来自仓库内文档转引；**[估算]** 由公式算出。引用代码只写路径与函数名，不写行号。
>
> **调查口径**：2026-10-06，分支 `newtask-v3-MotionJepa1006`，调查前 HEAD `d05c6ab7`；四路只读子代理（均 opus）分别覆盖 origin/newtask-v2 的窗口口径与交付集、本分支 16 个任务源码、官方参考数据 hard 档统计、MotionJEPA 与 policy 仓库的训练/评估口径；同日另派三路只读子代理（均 sonnet）核实 ManiSkill `spec` 挂载与 reset 生命周期、生成器锚点与导入路径、11 个任务的覆写锚点，结论并入第五、六节。仓库源码零改动。

---

## 一、上次训练与评估的完整口径

### 1.1 先纠正三个容易弄错的前提

1. **上次训练的四任务不是 PatternLock、RouteStick、BinFill、PickXtimes。** MotionJEPA 最近一次正式训练（run `wan-full1600-filter2-b176x4-72ep-a`，2026-09-14，72 epoch 跑完）用的是 newtask-v2 交付集 `HongzeFu/robomme-4task-h5-20260912-v2`，四任务是 **BinFill、RouteStick、VideoUnmaskSwap、VideoRepick**，各 400 条。此前 artifact《采样窗口与 eval 成功率》画的 PatternLock/RouteStick/BinFill/PickXtimes 是 policy eval 侧对官方 16 任务 test+val 的分析，不是训练集。
2. **newtask-v2 已经有一档 xhard。** RouteStick length 8–10（T 800–1000）、VideoUnmaskSwap swap 4–5（T 中位 558）、VideoRepick swap 4–5（T 中位 863）。BinFill 没有 xhard。
3. **"token"有两套口径，差 10 倍。** MotionJEPA 预训练自己切 33 帧、stride 1 的 chunk，上次过滤后 796,001 个；policy 侧 motion 记忆表切 33 帧、stride 16，全集约 69,716 窗。artifact 画的是后者。

### 1.2 MotionJEPA 预训练（stride 1）

- run：`wan-full1600-filter2-b176x4-72ep-a`，2026-09-14，72 epoch，退出码 0。出处 [文档]：`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA/docs/training-doc/README.md` 的 run 一览表。之后的条目全是推理或可视化。本机 `/data/hongzefu/MotionJEPA` 是旧版主线，没有 full1600 的内容。
- 样本：33 帧 `[t, t+32]`、`data.stride: 1`、`data.max_horizon: 8`；Wan VAE 编成 `(9,16,32,32)` latent（1 锚帧 + 8 组×4 帧）；每个 chunk 1 个 token，`motion.num_tokens: 1`、`motion.dim: 768`。出处：`docs/DATASET.md` §2；`configs/default.yaml`；`src/motion_jepa/data/dataset_wan.py::WanChunkLatentDataset.__init__`（断言 stride==1）；冻结配置 `runs/wan-full1600-filter2-b176x4-72ep-a/config.yaml`。
- 分段：demo = `[0, D)`，D 为 `is_video_demo=True` 帧数；exec = `[D, first_completed + 2)`。窗口不跨 demo/exec 段，demo 与 exec 是两个独立变体；BinFill 只保留 exec（`scope.json::dup_variants_excluded = 400`，`segment_convention.json` 写明 "binfill: 只保留 exec"）。1600 条 episode、2800 个变体、901,970 帧。出处：`docs/DATASET.md` §1；`docs/dataset-build-doc/local-a100-4task-full1600/reports/scope.json`。每个变体 chunk 数 = 帧数 − 32。
- 数量（出处 `docs/training-doc/wan-full1600-filter2-b176x4-72ep-a/metrics/train.summary.log`）：

| 口径 | 数量 |
|---|---:|
| 未过滤 chunk | 812,370 |
| 运动过滤后保留（阈值 `rgb_mag >= 0.02711051143705845`） | 796,001 |
| 丢弃 | 16,369（2.015%） |
| 训练集（2,675 变体） | 763,499 |
| 验证集（125 变体 = 70 条 holdout，每任务×难度 5 条） | 32,502 |

- 按任务（未过滤 / 过滤后）：BinFill 229,540 / 223,327；RouteStick 187,300 / 187,300；VideoRepick 264,151 / 260,108；VideoUnmaskSwap 131,379 / 125,266。
- 按难度与段（未过滤，demo / exec）：BinFill 只有 exec，easy 53,539、medium 76,251、hard 99,750；RouteStick easy 9,300/8,800、medium 19,300/18,800、hard 24,300/23,800、xhard 41,750/41,250；VideoRepick easy 35,307/43,328、medium 41,837/43,958、xhard 56,484/43,237；VideoUnmaskSwap easy 10,900/14,759、medium 10,900/7,248、hard 16,000/22,456、xhard 25,900/23,216。
- 训练节奏：每卡 batch 176、4 卡、梯度累积 2、有效 batch 1,408；每 epoch 542 步（1,084 micro-batch，drop_last），72 epoch 共 39,024 步，lr 6e-4。出处同上日志与 `scripts/train-script-hongzefu/full1600_wan_local4gpu.sh`。
- 未取得：过滤后按任务×难度的拆分（需要 AWS 机器上的 `chunk_motion.npz`）。

### 1.3 policy 侧 motion 记忆表（stride 16）

- 配置：`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning_MotionJEPA/src/mme_vla_suite/models/config/robomme/perceptual-framesamp-modul-8frame-8x8-motion.yaml`：`motion.stride: 16`、`window_frames: 33`、`window_direction: forward`、`grid_origin: segment_start`、`budget: 160`、`demo_min_real_frames: 17`、`demo_tail_pad: repeat_last`；编码器 `source_run: wan-full1600-filter2-b176x4-72ep-a/checkpoint_epoch_72.pt#encoder`。
- 公式（`motion_store.py::segment_grid_starts`，转引自 MotionJEPA `docs/archive/evaluteVLAencode0914-plan-v1.md` 第九节）：demo=(0, exec_start)，exec=(exec_start, T)，`starts = range(0, max(0, L-32), 16)`；不跨段、不 padding、不强补末窗、不过滤。demo 不足 33 帧时按 `demo_min_real_frames=17` 重复末帧补齐。`budget` 160 窗是上限，没有任何一档能填满它，它只是按最长那条留的余量。
- 表规模 [文档]：71,316 行（demo 35,913 + exec 35,403，含 1,600 个补帧窗）。出处 `docs/dataset-build-doc/4task-v2-1600ep-motion-demopad17/launch.md`。
- 全集 stride-16 窗 [估算，subagent 按 scope.json 的 D/T 复算，holdout 70 条逐格复现 2,779]：BinFill 30,908（含假 demo）、RouteStick 12,226、VideoUnmaskSwap 8,777、VideoRepick 17,805，合计 69,716；按 MotionJEPA 截断口径再数是 52,148。
- 每条窗口数（最少/中位/最多）：BinFill hard 70/98/140（含假 demo，纯 exec 约一半）；RouteStick xhard 46/54/60；VideoUnmaskSwap xhard 28/31.5/79；VideoRepick xhard 39/51/67。
- 评估时取窗（`policies/framesamp_memory.py::visible_motion_frames`、`_prepare_motion`）：demo 段 s=0 起每 16 帧一个，条件 `s+16 ≤ es−1`；exec 段起点 `es+u`，条件 `u+32 ≤ step−es`；超 budget 默认报错，`MMEVLA_MOTION_OVERFLOW=resample` 时 demo 全留、exec 等距降采样。
- 注意：MotionJEPA 文档记录"当前新 1600 库没有 motion 缓存，policy 训练档案 `motion_enabled=false`"，policy 侧实际是否消费了这张表没有留档。

### 1.4 eval 取帧

- `src/mme_vla_suite/shared/sampling.py::even_sampling_indices(step_idx, N)`：`step_idx < N` 时取全部；否则 `np.linspace(0, step_idx, N, dtype=int32)`，含首帧与当前帧，跨 demo/exec 整条。训练与在线推理共用。
- N = `budget // (token_per_image × num_views)`：`perceptual-framesamp-modul.yaml` / `-context.yaml` 为 512 // 16 = 32；`*-8frame-8x8*.yaml` 为 512 // 64 = 8。训练侧只允许 (512,16,1) 与 (512,64,1)。`128 // 16 = 8` 只出现在假设性分析文档 `docs/dataset-build-doc/16task-h5-scan/result.md`。N **不是**切分步长。
- 本分支与 newtask-v2 的帧路取整差异：newtask-v2 `window_timeline.py::frame_path` 用 `floor(x+0.5)` 对齐 JS `Math.round`；本分支 `scripts/patternlock-routestick-params/plot_sampling_windows.py::frame_indices` 用 Python `round`（银行家舍入），恰逢 .5 时可能差 1 帧。

## 二、newtask-v2 交付集与 BinFill 假 demo 的历史做法

### 2.1 交付集

- 出处：origin/newtask-v2 的 `artifacts/injection/20260912-contract-v3-10/hf_release/{README.md, MANIFEST.json}`、`docs/validation/newtask-v2/20260912-contract-v3-10/README.md`、`scripts/README.md` §1.1、`scripts/NEW_VALUE_CONTRACT_CHANGELOG.md` 第四节、`XHARD_DIFFICULTY_PLAN.md`。
- 每任务 400 条 primary，共 1,600；另 spare 196、smoke 1；每个 h5 只含一条 `episode_0`。没有 train/test/val 字段，1,600 条全属 train；另有 700 条只做 env-check 不出 h5 的候选被定义为 test；没有 val。MotionJEPA holdout 70 条（每格 5 条）。seed = `env_code*1000 + ep*100 + attempt`，env_code BinFill=4、VideoUnmaskSwap=5、VideoRepick=9、RouteStick=16，难度不进 seed。
- 分档参数与长度（T 最短/中位/最长/均值；D 为 demo 长度）：

| 任务/难度 | n | 参数 | T | D |
|---|---:|---|---|---|
| BinFill/easy | 134 | 1 色；生成 4–6；投入 1–3 | 528/927/1530/935.6 | 264/463.5/765（假 demo = 原 T） |
| BinFill/medium | 133 | 2 色；生成 6–8（v2 改）；投入 2–4 | 790/1282/1762/1284.1 | 395/641/881 |
| BinFill/hard | 133 | 3 色；生成 8–10（v2 改）；投入 3–5 | 1156/1630/2304/1636.8 | 578/815/1152 |
| RouteStick/easy | 100 | length 2–3，不可折返 | 200/250/300 | T/2 |
| RouteStick/medium | 100 | length 4–5，不可折返 | 400/450/500 | T/2 |
| RouteStick/hard | 100 | length 4–7，可折返 | 400/550/700 | T/2 |
| RouteStick/xhard | 100 | length 8–10，可折返 | 800/900/1000 | T/2 |
| VideoUnmaskSwap/easy | 100 | 3 容器；swap 1–2；pick 1–2 | 214/342/517 | 114/141/168 |
| VideoUnmaskSwap/medium | 100 | 4 容器；swap 1–2；pick 1 | 211/266/365 | 114/141/168 |
| VideoUnmaskSwap/hard | 100 | 4 容器；swap 2–3；pick 2 | 406/452/552 | 168/192/216 |
| VideoUnmaskSwap/xhard | 100 | 4 容器；swap 4–5；pick 2 | 501/558/1312 | 264/291/318 |
| VideoRepick/easy | 134 | 3 块；swap 1–2 | 504/694/922 | 252/296/355 |
| VideoRepick/medium | 133 | 3 块；swap 2–3 | 559/755/968 | 306/343/398 |
| VideoRepick/xhard | 133 | 3 块；swap 4–5 | 674/863/1130 | 414/468/508 |

- 规律：RouteStick T = 100·L，每段固定 50 帧；VideoUnmaskSwap demo = `6·ceil((64+50n)/6)`，n=1–5 为 114/168/216/264/318。VideoUnmaskSwap/xhard 的 T=1312 是一条慢条（ep5、seed 5500，"抓红容"段 828 帧），仍在交付集里。
- 交付里没有 BinFill/xhard 与 VideoRepick/hard（后者被契约 `excluded_groups` 排除）。newtask-v2 的 VideoRepick xhard 是在 3 块 cube 的 easy/medium 分支上加 swap，不是本仓库 hard 的 15 块 cluster 分支。

### 2.2 BinFill 假 demo 的改动范围（历史做法，本分支不再采用，见 `AGENTS.md` P4）

- 做法：h5 的 `timestep_0..N-1` 是原轨迹复制，`info/is_video_demo=True`、`info/is_completed=False`；`timestep_N..2N-1` 是原轨迹；视频前一遍加 10 px 红框后 libx264 重编。不是环境里跑 demo，而是生成入口把成品"同一条重复两遍"。
- 改动（`src/robomme` 零改动）：提交 `06139614`（10.64）在 `scripts/generate_dataset_newseed.py` 新增 `BinFillDemoError`、`_binfill_duplicate_h5`、`_binfill_duplicate_video`、`_binfill_demo_deliverable`，`EpisodeJob.binfill_demo` 字段，CLI `--binfill-demo`（默认关），`_worker` 在 `record_env.close()` 后调用；`scripts/injection/campaign.py::cmd_run` feasibility 分支显式传 `binfill_demo=True`；`scripts/injection/run.py::invoke_generator` 加参数；测试 `tests/lightweight/test_binfill_demo_duplicate.py`。统计层 `window_timeline.py::simulate_binfill_demo`（10.55）在旧数据上模拟翻倍，10.65 对生成器直出的 demo 做幂等。
- 动机只有用户一句话"binfill任务改为加入模拟的demo 即为把一个任务重复两遍"（2026-09-11，给数轴补 demo 段）；选"生成入口直接出 h5"是因为 BinFill 的 task_list 全是 `demonstration=False`，且真跑两遍会撞录像器 `fail_safe_limit = 2000`。训练层面动机无记录。
- 副作用：run 10 有 3 条 `BinFillDemoError`（ffmpeg Broken pipe）；mp4 不能逐位对拍；MotionJEPA 丢弃该 demo 而 policy 侧 stride-16 把它算进去，两侧不一致。
- **本分支现状 [实测，2026-10-06]**：`scripts/data-generation-newSeed/generate_dataset_newseed.py` 在 `scripts`、`src`、`tests` 内 grep `binfill`（不区分大小写）只命中任务名字符串，`--binfill-demo`、`BinFillDemoError`、`_binfill_duplicate_h5` 一个都没有。

## 三、「8 帧 / 32 帧遗漏 subgoal」的来龙去脉

- 所有分支与 MotionJEPA 仓库都没有把"让采样遗漏 subgoal"写成目标或判据的文档。相关表述只有：提交 `d83998c8`（2.18）用户原话"delta32 delta8 16窗口是为了对齐 <artifact f512d233>"；提交 `212595b8`（10.84）把单条图从 N=32 改成 N=8 以说明"帧预算不是切分步长"。
- subagent 用 newtask-v2 `windows_timeline.json`（07 实跑，每组 ep0–29）补算的漏段占比（分母含收尾段）：N=8 时 BinFill e/m/h 38%/51%/59%，RouteStick e/m/h/xh 0/20%/34%/58%，VideoUnmaskSwap 1%/0/0/13%，VideoRepick e/m/xh 32%/38%/42%；N=32 几乎全 0（BinFill hard 1%）。
- 官方 hard 档 32 帧帧路在 16 个任务上零漏段；要让 32 帧漏段，T 要超 1500（第四节 skip32 列）。xhard 计划据此只对 8 帧设硬性判据，判据本身写在计划里。

## 四、官方参考数据 hard 档统计

### 4.1 数据位置与口径

- 旧 AGENTS.md 规定的 `data/robomme_data_h5/` 在本工作副本不存在；`/data/hongzefu/robomme_benchmark-restore-DataGen/data/robomme_data_h5/` 与 `/data/hongzefu/robomme_data_h5/` 也不存在。实际使用 **`/data/hongzefu/data_0226/`**（16 个 `record_dataset_<Task>.h5` + 16 个 metadata + `videos/`，493 GB，文件日期 2026-02-28 至 03-01）。认定为官方集的依据：12 个任务的 metadata 与仓库 train metadata 逐字节相同，4 个 Unmask 系任务在 ep0–99 内 seed/难度一致；**未用 sha256 与 revision `a5e4e25…` 核对**。
- 4 个 Unmask 系任务的 train metadata 已扩到 ep0–399（hard 100 条，提交 `052841ae`），h5 只有 ep0–99，统计只取 h5 里存在的 25 条 hard；其余 12 个任务 hard 各 25 条。共 400 条，无抽样，全部 `is_completed=True`。
- `info` 键 7 个：`grounded_subgoal`、`grounded_subgoal_online`、`is_completed`、`is_subgoal_boundary`、`is_video_demo`、`simple_subgoal`、`simple_subgoal_online`。timestep 连续，第 0 步必是边界。
- 切段口径与本分支 `scripts/patternlock-routestick-params/extract_move_durations.py::extract_episode` 一致：`is_subgoal_boundary=True` 为段起点，段名取该步 `simple_subgoal`，段长到下一边界，demo 段与尾段 "All tasks completed" 都算段。按文本变化切会把相邻同名段并掉（93 条不同），以边界口径为准。帧路 `round(i*(T-1)/(N-1))`。
- 脚本与产物（scratchpad，会话结束即失，重跑约 17 秒）：`official_hard_stats.py`、`summarize.py`、`official_hard_stats.json`；命令 `uv run python $S/official_hard_stats.py /data/hongzefu/data_0226 src/robomme/env_metadata/train $S/official_hard_stats.json`（退出码 0）。首跑因 Unmask 系 metadata 含 h5 不存在的 ep 报 KeyError，改为只取存在的 episode 后通过。需要留档时按此口径重写脚本并落 `docs/`，不写入 `/data/hongzefu/data_0226/`。

### 4.2 每任务汇总（hard，n=25）

T 最小/中位/均值/最大；demo 长度最小/中位/最大；段数最小/中位/最大；执行段数（去 demo 与尾段）；Δ8、Δ32 取中位；skip8 为 8 帧帧路没有任何采样点落入的段数（执行段口径）均值/最大；skip32 全为 0；窗为 stride-16 窗口数（demo 窗 + exec 窗）最少/中位/最多。

| 任务 | T | demo | 段数 | 执行段 | 最短段 | 中位段长 | Δ8 | Δ32 | skip8 执行段 | 窗 |
|---|---|---|---|---|---|---|---|---|---|---|
| BinFill | 584/868/851.8/1044 | 0 | 8/10/12 | 7/9/11 | 34 | 76.5 | 123.9 | 28.0 | 3.12/4 | 35/53/64 |
| PickXtimes | 686/812/796.2/1025 | 0 | 10/12/12 | 9/11/11 | 35 | 70.5 | 115.9 | 26.2 | 3.52/5 | 41/49/63 |
| SwingXtimes | 449/488/490.2/570 | 0 | 10/10/10 | 9 | 17 | 42 | 69.6 | 15.7 | 3.08/4 | 27/29/34 |
| StopCube | 122/309/286.8/459 | 0 | 4/6/7 | 3/5/6 | 6 | 48 | 44.0 | 9.9 | 0.36/1 | 6/18/27 |
| VideoUnmask | 309/329/331.0/399 | 66/66/66 | 5/5/5 | 3 | 7 | 66 | 46.9 | 10.6 | 0/0 | 17/18/22 |
| VideoUnmaskSwap | 407/457/455.8/586 | 168/168/216 | 5/5/5 | 3 | 6 | 96 | 65.1 | 14.7 | 0/0 | 22/26/34 |
| ButtonUnmask | 353/373/378.2/452 | 0 | 5/5/5 | 4 | 6 | 93 | 53.1 | 12.0 | 0.16/1 | 21/22/27 |
| ButtonUnmaskSwap | 443/461/465.7/555 | 0 | 6/6/6 | 5 | 6 | 93.5 | 65.7 | 14.8 | 0.12/1 | 26/27/33 |
| PickHighlight | 492/539/540.0/652 | 0 | 7/7/7 | 6 | 12 | 86 | 76.9 | 17.4 | 0.36/2 | 29/32/39 |
| VideoRepick | 405/543/562.8/1027 | 147/162/214 | 6/8/10 | 3/5/7 | 35 | 59.5 | 77.4 | 17.5 | 0.88/2 | 22/31/61 |
| VideoPlaceButton | 900/961/966.2/1041 | 703/757/818 | 12/12/12 | 2 | 12 | 83 | 137.1 | 31.0 | 1.00/1 | 53/57/62 |
| VideoPlaceOrder | 921/1115/1111.8/1408 | 724/917/1135 | 12/14/16 | 2 | 13 | 83.5 | 159.1 | 35.9 | 1.00/1 | 54/67/85 |
| MoveCube | 247/416/370.6/513 | 161/228/280 | 4/6/6 | 1/2/2 | 5 | 80.5 | 59.3 | 13.4 | 0/0 | 13/23/29 |
| InsertPeg | 414/464/470.9/560 | 207/232/280 | 5/5/5 | 2 | 1（尾段） | 110 | 66.1 | 14.9 | 0/0 | 22/26/32 |
| PatternLock | 186/324/350.0/568 | 93/162/284 | 7/11/15 | 3/5/7 | 6 | 31 | 46.1 | 10.4 | 2.08/4 | 8/18/32 |
| RouteStick | 400/500/552.0/700 | 200/250/350 | 9/11/15 | 4/5/7 | 7 | 50 | 71.3 | 16.1 | 2.52/4 | 22/28/40 |

### 4.3 各类 subgoal 平均段长（timestep；demo| 为演示段）

- BinFill：拿起 cube 108.5，放进 bin 70.6，按按钮 61.6，尾段 38.0。
- PickXtimes：拿起 84.2，放到 target 69.6，按按钮 63.0，尾段 38.2。
- SwingXtimes：到右侧 target 37.5，到左侧 40.6，拿起 118.6，放回桌面 36.5，按按钮 62.1，尾段 38.5。
- StopCube：remain static 63.7（最短 6），到按钮上方 56.0，按按钮 28.3，尾段 36.8。
- VideoUnmask / VideoUnmaskSwap：demo static 66 / 191，拿起容器约 103，放下约 49，尾段约 9。
- ButtonUnmask / ButtonUnmaskSwap：按按钮 117 / 104，拿起容器约 102–104，放下约 45–47，尾段约 8。
- PickHighlight：拿起高亮 cube 98.7，放回桌面 55.4，按按钮 117.6，尾段 15.7。
- VideoRepick：demo 拿起 112.6、放下 54.2；执行拿起 98.7、放下 58.3；按按钮 62.5；尾段 38.3。
- VideoPlaceButton / VideoPlaceOrder：demo 拿起约 88–95、放到 target 约 90–92、static 约 58；执行拿起约 118、放到正确 target 约 71–72；尾段约 16。
- MoveCube：demo static 50.4；推 cube 约 98–105，拿起 peg 约 120，用 peg 勾 cube 约 100–106，pick-place 约 65–110；尾段 6.9。
- InsertPeg：拿起 peg 117–122，插入 103–119，尾段 11.8。
- PatternLock：左右移动 24–27；前后与斜向 33–40；尾段 9.1。
- RouteStick：demo 每段固定 50；执行段 48.2–49.3（最短 43）；尾段固定 7。

### 4.4 本分支 artifact 四任务（官方 test+val 各 100 条，easy 52 / medium 24 / hard 24）

- PatternLock hard：T 184/353/516/351.9，窗 8/19/30；RouteStick hard：400/500/700/554.2，窗 22/28/40；BinFill hard（无 demo）：608/920/1097/870.0，窗 36/56/67；PickXtimes hard：677/794/1006/791.1，窗 41/48/61。出处 `scripts/patternlock-routestick-params/outputs/durations_{val,test}.json`、`counting_params_{val,test}.json`。
- 这四个任务的难度参数：PatternLock 路径长度 [2,4]/[3,5]/[4,8]；RouteStick steps [2,3]/[4,5]/[4,7]；BinFill 投入 [1,3]/[2,4]/[3,5]；PickXtimes 次数 [1,3]/[1,3]/[4,5]。

## 五、16 个任务的 hard 配置与约束（源码核查）

### 5.0 共用结论

- 工具文件在 `src/robomme/robomme_env/utils/`（`difficulty.py`、`subgoal_language.py`、`task_goal.py`、`vqa_options.py`）；`src/robomme/utils/` **不存在**（前版文档写错）。
- 序数词：`utils/subgoal_language.py::get_subgoal_with_index` 只认 idx 0–9，≥10 抛 ValueError；用到它的是 BinFill（每色各自从 0 编号）、PickHighlight（目标数>1 时）、PickXtimes。SwingXtimes 与 VideoRepick 自带 10 个词的序数表，超出退回 `f"{i+1}th"`。
- `utils/task_goal.py::num2words`、`num2words_2` 覆盖 1–20，`.get(n, str(n))` 查不到退回数字。`utils/vqa_options.py` 各任务选项只是动作种类，与次数无关。`get_language_goal` 按 `if env == "BinFill": … elif …` 字符串分支，`get_vqa_options` 用 `OPTION_BUILDERS.get(env_id, _options_default)` 查表；**未知名字都静默返回 `[]`，不报错**。
- 随机数消耗 [实测，torch 2.9.1 CPU Generator，2000 个 seed]：`torch.randint(lo, hi)` 不论区间多大只消耗固定一份随机量，之后的随机数完全一致；同宽区间整体平移结果严格平移（(4,6)→(6,8) 恒 +2）；拓宽区间时新值只会是原值或原值+偏移；`randperm(n)[:k]` 改 k 不影响随机流，改 n 影响。
- 固定帧数：ManiSkill `follow_path` 每个 position 1 步；`open_gripper`/`close_gripper` 默认各 6 步；`solve_hold_obj(static_steps=N)` 按 6 向上取整；`solve_strong_reset` 默认 30 步。
- seed 规律：`env_code*1000 + ep*100 + attempt`；hard 记录全部 `ep ≡ 3 (mod 4)`；4 个 Unmask 系任务各 100 条 hard（ep 3,7,…,399），其余 12 个各 25 条（ep 3,7,…,99）。
- 16 个 `@register_env("<名>")` 全是单参数形式，没有 `max_episode_steps`；`robomme_env/__init__.py` 逐个 `from .X import *` 共 16 行。`normalize_robomme_difficulty(value)` 去空白转小写后只接受 `easy`/`medium`/`hard`，其余抛 ValueError。
- 13 个任务有 `config_easy/medium/hard` 类属性与 `configs = {'hard': config_hard, 'easy': config_easy, 'medium': config_medium}`（显式字典）；StopCube、InsertPeg、MoveCube 没有 `configs`。
- **ManiSkill 生命周期 [实测，`.venv` gymnasium 0.29.1]**：`BaseEnv.__init__` 末尾 `reset(options=dict(reconfigure=True))` 已跑一次 `_load_scene` + `_initialize_episode`；默认 `reconfiguration_freq=0`，之后用户调用的 `reset()` 只重跑 `_initialize_episode`，不重跑 `_load_scene`。`gym.make` 在实例化之后、套 `PassiveEnvChecker`/`OrderEnforcing`/`MSTimeLimit` 之前执行 `env.unwrapped.spec = EnvSpec(...)`（gymnasium `EnvSpec` 是 dataclass）；ManiSkill `registration.py::make` 自己不碰 `spec`；`BaseEnv` 不写 `spec`、只在 `print_sim_details` 读。四个 wrapper 读 `spec.id` 共 10 处，全部经 `unwrapped`（RecordWrapper 三处兜底 `self.env_id`）。
- 前版文档的错项订正：VideoRepick hard 的 swap 为 0 且 hard 分支不支持交换，次数 `num_repeats` 写死在 `__init__`；VideoPlaceOrder 不读 `pick`，抽取的变量名是 `num_targets_to_pick`（不叫 `P`）；VideoUnmask/ButtonUnmask 的 `pick` 只是 `>1` 开关；VideoPlaceButton 没有数值型次数键；两个 Swap 任务 swap 写死最多 3 次、bin 只能 3 或 4、pick 只有 `==2` 分支；PatternLock `length` 是拒绝采样过滤条件；StopCube `step()` 写死 5 趟；StopCube/InsertPeg/MoveCube 完全不读 difficulty；示例文件名 `PickHighlight_ep3_seed620301.h5` 与 metadata 不符，实际 ep3 seed 12300。

### 5.1 逐任务（env_code、configs 原文、键语义与条数公式、时长结构、随机流、语言上限、metadata）

**BinFill（4）**
- configs：easy `{'color':1,'spawn_cubes':[4,6],'put_in_color':[1,1],'put_in_numbers':[1,3]}`；medium `{'color':2,'spawn_cubes':[8,10],'put_in_color':[1,2],'put_in_numbers':[2,4]}`；hard `{'color':3,'spawn_cubes':[10,12],'put_in_color':[2,3],'put_in_numbers':[3,5]}`。类里另有几段被注释掉的旧 config。
- `_load_scene` 读取：`color` 颜色数（`randperm(3)[:color]`）；`put_in_color` 有目标的颜色数（截到 ≤ color）；`put_in_numbers` 总目标数 T（多色时抽 T 后循环 T 次逐个分配）；`spawn_cubes` 总生成数（每色至少 max(目标,1)，剩余逐个分配，总数可能超过上限）。`_initialize_episode` 先 `randperm(3)` 打乱颜色顺序，每个有目标的颜色做 [pick up the {第 i 个} {color} cube → put it into the bin] × 目标数，最后 press the button。条数 2T+1，hard 7–11。
- 时长：无 demo；`__init__` 的 `dynamic = randint(0,2)`（`self.generator` 的第一次抽取）一半概率为真，为真时 `step()` 把每色第 k 个方块在 [0, k×100] 步内移走、中点放回。
- 随机流：用 `__init__` 建的 `self.generator`，`_load_scene` 不重设。按钮与 bin 板位置在读 config 之前抽，不变；改 `put_in_numbers` 后分配循环次数变，之后的 total_spawn、剩余分配、生成顺序、方块坐标、颜色顺序全部偏移。母布局不能逐项不变。
- 上限与风险：任一颜色目标 ≥11 触发 ValueError；`_load_scene` 里 `spawn_random_cube` 失败被 `except RuntimeError` 吞成 `logger.debug`，不抛 `SceneGenerationError`；某色实际数少于目标数会在 `_initialize_episode` 的 `cube_collection[i]` 抛 IndexError。
- metadata：hard 25 条；attempt>0 共 11 条：ep3=4301、ep7=4701、ep15=5501、ep31=7101、ep35=7501、ep47=8703、ep51=9102、ep71=11102、ep83=12301、ep91=13101、ep99=13902。

**ButtonUnmask（8）**：configs easy `{'bin':3,'pick':1}`、medium `{'bin':5,'pick':1}`、hard `{'bin':15,'pick':2}`；`__init__` 的 `num_repeats = randint(1,6)` 抽了未用；`step()` 只给前 15 个 bin 做抬放动画。`pick` 只用作 `>1` 判断；hard 模板 press → pick bin_0 → put down → pick bin_1，条数 2+2×(pick>1)，已到顶。`_load_scene` 新建 generator：按钮 → 逐个容器 → `randperm(3)` 颜色；改 `bin` 容器坐标前缀一致但颜色可能重排。hard 100 条，seed 基数 8000，全 attempt 0。

**ButtonUnmaskSwap（7）**
- configs：easy `{"bin":3,"swap_min":1,"swap_max":2,"pick_min":1,"pick_max":2}`；medium `{"bin":4,"swap_min":1,"swap_max":2,"pick_min":1,"pick_max":1}`；hard `{"bin":4,"swap_min":2,"swap_max":3,"pick_min":2,"pick_max":2}`。
- `__init__` 用独立 generator 先抽 `swap_times` 再抽 `pick_times`；`_refresh_swap_schedule` 只写了 swap_times=1/2/3 三个分支且没有 else，第 k 次交换占第 64+50(k−1) 到 64+50k 步，只有 `swap_pair1..3`（`idx1` 取自 `swap_indices`——两个目标 bin 加一个随机 bin，共 3 个；`idx2` 初始 None、在 `step()` 里动态取最近的 bin 后重新 `_refresh_swap_schedule()`）；**swap_times ≥4 或 0 时 `swap_schedule` 不被赋值，`step()` 的 `self.swap_schedule[-1][3]` 抛 AttributeError**。`step()` 用 `for i in range(len(self.swap_schedule))` 与 `getattr(self, f'swap_pair{i+1}_idx2')` 泛化遍历。`pick_times` 只判 `==2`，3 退化成 1。`bin==4` 用 `region4`（带 `y_offset` 随机，`rotate_points_random` 被注释），否则 `region3`（3 元素），**bin ≥5 抛 IndexError**。hard 模板 press 右键 → press 左键 → pick selected_bins[0] → put down → pick selected_bins[1]，5 条；交换次数不改条数。
- 时长：容器 0–64 步抬放；交换 64 起每次 50 步（S=3 到 214）；方块 64 步到最后一次交换结束都在抬放（盖回 `start_step=64`）；与按按钮同时进行。
- 随机流：swap/pick 独立 generator，场景另一 generator；三组交换的第一个容器在场景生成时算好，第二个运行时取最近；改 swap 区间只在末尾追加交换，母布局逐项不变。
- hard 100 条，seed 基数 7000，全 attempt 0。

**InsertPeg（13）**：无 configs，difficulty 未被使用；`random_peg_idx` 抽后写死 0；`obj_flag`、`direction` 各一次 `randint(0,2)`。固定 6 条：演示抓 → 演示插 → strong reset 30（NO RECORD）→ 静止 100（NO RECORD）→ 执行抓 → 执行插。hard 25 条，seed 基数 13000，attempt>0 共 9 条：ep23=15301、ep27=15704、ep39=16901、ep43=17307、ep63=19301、ep71=20101、ep75=20502、ep79=20902、ep87=21702。

**MoveCube（14）**：无 configs，difficulty 未用；`_initialize_episode` 用 `randint(3)` 选 peg_push / gripper_push / grasp_putdown；task_list 在 `evaluate()` 构建，6/4/6 条，含静止 30 或 60、strong reset 30。hard 25 条，seed 基数 14000，全 attempt 0。

**PatternLock（15）**
- configs：easy `{"grid":3,"length":[2,4]}`、medium `{"grid":4,"length":[3,5]}`、hard `{"grid":5,"length":[4,8]}`。
- `_load_scene`：`grid` 为 grid×grid 目标点网格，间距 0.1，无随机；`length` 是拒绝采样过滤条件：`max_attempts = 1000`，每次 `randperm(N)[:2]` 选起终点，`find_path_0_to_8(..., diagonals=True, generator=generator)` 做 8 连通随机 DFS（每访问一节点 randperm 一次），节点数 L 落区间即 break，1000 次不中只 `logger.debug` 警告并用最后一条。模板：demo 段 swingonto 起点（NO RECORD）→ (L−1) 条 "move {方向}" → strong reset 30（NO RECORD）；执行段 strong reset 回 swing_qpos 30（NO RECORD）→ (L−1) 条 move。条数 2L+1，hard 9–17。
- 时长：每步 `solve_swingonto` 两次 `move_to_pose_with_screw`，步数不固定；按官方 test+val hard 最长 516 帧对 L=8 反推，每个 move 约 37 帧（含开销）。
- 随机流：网格不变；改 `length` 改变拒绝采样循环次数，路径一般会变。
- 语言：8 个方向，无次数上限。hard 25 条，seed 基数 15000，attempt>0 仅 ep91=24101。

**PickHighlight（12）**
- configs：easy `{'spawn':3,'pickup':1}`、medium `{'spawn':4,'pickup':2}`、hard `{'spawn':6,'pickup':3}`；`config_hard` 是类属性。
- `_load_scene` 先重设 generator 种子 → 按钮 → 循环 spawn 次生成方块（失败只记日志 `Failed to spawn cube`，`len(all_cubes)` 可能小于 `spawn`）→ 目标 `randperm(len(all_cubes))[:pickup]`；`step()` 第 10–100 步高亮 `min(pickup, len(target_cubes))` 个。模板 press → [pick up the {第 i 个} highlighted cube → place onto the table]，最后一个只抓不放；条数 2k，hard 6。成功条件每个目标被抓起过至少一次，`_execute_tasks` 成功即提前返回。
- 随机流：改 `pickup` 母布局逐项不变，新目标是同一排列前缀；k ≤ 实际生成数（≤6），超出截断；改 `spawn` 目标集合整体改变。语言 pickup ≤ 10。hard 25 条，seed 基数 12000，全 attempt 0。

**PickXtimes（1）**
- configs：easy `{'color':1,'number_min':1,'number_max':3}`、medium `{'color':3,'number_min':1,'number_max':3}`、hard `{'color':3,'number_min':4,'number_max':5}`。
- `__init__` 用局部新建 generator（`manual_seed(seed)`）`randint(configs[difficulty]['number_min'], ['number_max']+1)` 抽 `num_repeats`，在 `super().__init__` 之前；`color` 每色 1 块。模板（`_load_scene` 构建）[pick up the {color} cube for the {第 i} time → place onto the target] × N → press the button to stop；条数 2N+1，hard 9 或 11。无 demo、无固定段。随机流：独立 generator，母布局不变，同宽平移严格 +k。语言 N ≤ 10（`get_subgoal_with_index`），目标文本 `num2words` ≤ 20。hard 25 条，seed 基数 1000，全 attempt 0。

**RouteStick（16）**
- configs：easy `{'length':[2,3],'backtrack':False}`、medium `{'length':[4,5],'backtrack':False}`、hard `{'length':[4,7],'backtrack':True}`。`__init__` 不传 difficulty 时强制 easy（else 分支末尾 `self.difficulty = "easy"`），生成器总会显式传。
- `_load_scene` 用 `self.configs.get(getattr(self, "difficulty", "easy"), self.config_easy)`；抽取顺序：theta → 4 根障碍物颜色（每根 3 个随机数）→ `steps = randint(lmin, lmax+1)` → 在 5 个按钮 [0,2,4,6,8] 上 `generate_dynamic_walk`（起点 1 次 + 每步 1 次）→ S 次方向。模板：demo 段 swingonto 起点（NO RECORD）→ S 条 "move to the nearest {left/right} target by circling around the stick {cw/ccw}" → strong reset 200（NO RECORD）；执行段 strong reset 30（NO RECORD）→ S 条执行。条数 2S+3，hard 11–17。
- 时长：每步 45 个 Bezier 点 + 5 个停留点共 50 个 waypoint，约 50 步；录制长度 T = 100·S（reset 不录）。
- 随机流：theta 与障碍物颜色不变；游走路线前 min(S,S′) 步不变；方向序列整体改变；同宽平移 S 严格 +k。无次数上限。hard 25 条，seed 基数 16000，全 attempt 0。

**StopCube（2）**
- 无 configs，difficulty 只被读进 `self.difficulty`、从未使用。`_initialize_episode`（新建 generator，`manual_seed(self.seed)`）抽取顺序：`interval = randint(27,33)` 抽完覆盖成 30（抽取不能删，否则后续序列变）→ `move_interval = [60,80,120][randint(0,3)]` → **`stop_time = randint(2,6)` 即 2–5** → `rotation_angle = uniform(-30,30)`；`steps_press = mi·k − mi/2`；停止窗口 (mi(k−1), mi·k]。**`step()` 写死 `for segment in range(5)`，方块只走 5 趟**，k>5 时方块停在终点必失败。`evaluate` 超过 `move_interval * stop_time` 步未完成判失败。
- 模板：移到按钮上方 → 若干条 "remain static"（检查点 `range(100, final, 100)` 再补 final，final = steps_press − 30）→ 按按钮。条数 2+C，C = len(range(100, final, 100)) + 1。
- 时长：约 mi(k−0.5) + 按按钮步数。随机流：只改 stop_time 母布局逐项不变（mi 在其前、rotation 在其后，消耗量固定；`_load_scene` 用另一 generator）。语言 `num2words_2` ≤ 20。hard 25 条，seed 基数 2000，全 attempt 0。

**SwingXtimes（3）**
- configs：easy `{'color':1,'number_min':1,'number_max':3}`、medium `{'color':3,'number_min':1,'number_max':2}`、hard `{'color':3,'number_min':3,'number_max':3}`。
- `__init__` 局部 generator 抽 `num_repeats`（同 PickXtimes 写法），hard 固定 3。模板 pick up → [move to the top of the right-side target for the {第 i} time → left-side] × N → put on the table → press；条数 2N+3，hard 9；`_initialize_episode` 里 `max_swings = num_repeats * 2`，`evaluate` 里 `swing_count > max_swings` 判失败。目标高亮 20 步。随机流不变。序数表 10 个超出有回退。hard 25 条，seed 基数 3000，attempt>0 共 5 条：ep3=3301、ep11=4101、ep19=4903、ep31=6101、ep39=6902。

**VideoPlaceButton（10）**：configs easy `{'color':1,'additional_place':False,'swap':False,'targets':3}`、medium `{'color':3,'additional_place':False,'swap':False,'targets':4}`、hard `{'color':3,'additional_place':False,'swap':True,'targets':4}`。目标点循环写死 `range(4)`。hard 12 条（demo 9 条 + 静止 20、60（含 50 步交换）、strong reset 30 + 执行 2 条）；`additional_place=True` 时 pre/post 各 50% 加 2 条，但会在 task_flag 之前多抽 2 个随机数，before/after 重新抽。没有数值型次数键。hard 25 条，seed 基数 10000，attempt>0 共 6 条：ep3=10301、ep7=10701、ep27=12701、ep39=13901、ep75=17501、ep83=18301。

**VideoPlaceOrder（11）**
- configs：easy `{'color':1,'swap':False,'targets':4}`、medium `{'color':3,'swap':False,'targets':4}`、hard `{'color':3,'swap':True,'targets':4}`；`"place"` 键已注释。
- `_load_scene`（用 `__init__` 的 `self.generator`，不重设）：**`num_targets_to_pick = randint(2, len(self.targets)+1)` 即 2–4**；`indices = randperm(len(targets))[:num_targets_to_pick]`；`which_in_subset = randint(1, len(which_targets_to_pick)+1)`；`k = randint(0, len(which_targets_to_pick))`，`button_task_index = k*2+2`（假设每个目标贡献 pickup+drop 两项）。模板：demo 段 P 组 [pick → 放到目标 j]（按钮插在其中）→ pick → 放到 goal_site → 静止 20 → 静止 60（含 50 步交换）→ strong reset 30；执行段 pick → 放到第 {which_in_subset} 个目标。条数 2P+8，hard 12–16。
- 随机流：改 randint 区间时 `indices` 是同一排列前缀，但 `which_in_subset` 与 k 值变。P ≤ 4。
- **源码缺陷 [实测]**：`evaluate` 写的是 `self.current_task_specialflags`（带 s），`step` 读 `self.current_task_specialflag`（不带 s），swap 分支可能 AttributeError，除非别处另有赋值；现有 hard 数据能生成说明实际路径未触发或另有赋值，未逐行确认。
- hard 25 条，seed 基数 11000，attempt>0 共 12 条：ep3=11305、ep7=11705、ep15=12501、ep23=13301、ep31=14101、ep39=14903、ep47=15702、ep55=16503、ep75=18501、ep79=18901、ep83=19301、ep99=20903。

**VideoRepick（9）**
- configs：easy `{"cube":3,"swap_min":1,"swap_max":2}`、medium `{"cube":3,"swap_min":2,"swap_max":3}`、hard `{"cluster":True,"swap":None,"swap_min":0,"swap_max":0}`；`cluster`、`swap` 无处读取。
- `__init__`：`self.generator.manual_seed(seed)` 后 `num_repeats = randint(1,4)` 即 1–3（不读 configs），紧接着抽 `swap_times`（读 configs，hard 为 0），同一 `self.generator` 接着给 `_load_scene` 用。hard 走 `if self.difficulty == "hard"` 分支（按难度名字符串判断）：5 轮 × 3 色共 15 块，随机抽一个目标，生成失败抛 `SceneGenerationError`；**该分支不设 swap_pair/swap_schedule，hard 的 swap 改成 >0 会在 `_refresh_swap_schedule` 访问 `swap_pair1_idx1` 时抛 AttributeError**。模板（`_initialize_episode`，用 `self.num_repeats` 建）demo pick → demo drop → strong reset 30（NO RECORD）→ [pick up the correct cube for the {第 i} time → put it down] × N → press；条数 2N+4，hard 6–10。
- 随机流：randint 消耗固定，改区间或强制赋值不动随机流，15 块与目标逐项不变。语言有回退（"two"→"twice"）。hard 25 条，seed 基数 9000，attempt>0 共 6 条：ep3=9301、ep11=10102、ep19=10902、ep35=12501、ep51=14101、ep75=16501。

**VideoUnmask（6）**：configs 同 ButtonUnmask；模板静止 64（demo，容器 0–64 抬放）→ pick bin_0 → put down → pick bin_1，4 条，pick 已到顶。hard 100 条，seed 基数 6000，全 attempt 0。

**VideoUnmaskSwap（5）**：configs 三档与 ButtonUnmaskSwap 相同；`region4` 固定四个角点、带 `rotate_points_random`。模板静止演示 `static_steps = swap_schedule[-1][3]`（S=2 为 164，S=3 为 214）→ pick → put down → pick，4 条；S 只影响 demo 时长；盖回 `start_step=32*2`。约束同 ButtonUnmaskSwap（swap ≤3、bin 3 或 4、pick 1 或 2）；改 swap 母布局逐项不变。hard 100 条，seed 基数 5000，全 attempt 0。

### 5.2 生成器与导入路径 [实测，2026-10-06]

- `scripts/data-generation-newSeed/generate_dataset_newseed.py`：`EpisodeJob` 为 `@dataclass(frozen=True)`，字段 `task, episode, attempt, seed, difficulty, output_root, repo_root`，`recovery_mode` 属性按 episode 分 `z`/`xy`/None，`bump(seed)` 用 `dataclasses.replace` 加 attempt；`_args` 参数：`--output-dir`（必填）、`--env`/`--environment`（all）、`--episodes`（100）、`--episode-start`（0）、`--workers`/`--max-workers`（20）、`--gpus`/`--gpu`（"0"）、`--difficulty`（"211"，dest `difficulty_ratio`）、`--layout`（train）、`--max-attempts`（100）、`--no-limit-threads`、`--max-tasks-per-child`（8）、`--affinity`（none）。seed 护栏在 `generate_dataset_newseed` 函数体内（下一代布局 offset 上限）。`_run_jobs`：`failure_class` 为 `task` 清零 strikes、否则累加，`strikes ≥ 3` 放弃，否则 `bump(layout.seed(task, episode, attempt+1))`；池损坏时 in-flight job 也 `bump` 后 `appendleft` 退回并重建池。`_pool_init` 设 `CUDA_VISIBLE_DEVICES` 后才 `import torch` / `import robomme.robomme_env`；`_worker` 把 `repo_root/src` 插入 `sys.path`，`gym.make(job.task, **kwargs)`（`obs_mode="rgb+depth+segmentation"`、`control_mode="pd_joint_pos"`、`render_mode="rgb_array"`、`reward_mode="dense"`、`seed`、`difficulty`，recovery 时加 `robomme_failure_recovery*`），`RobommeRecordWrapper(base_env, dataset=..., env_id=job.task, episode=job.episode, seed=job.seed, save_video=True)`，`STICK_TASKS = frozenset(("PatternLock","RouteStick"))`；`_write_metadata` 写 `env_id`、`record_count`、`records[{task, episode, seed, difficulty}]`；`run_parameters.json`/`run_summary.json` 由 `write_text_atomic` 写出。
- 导入路径：`.venv/lib/python3.11/site-packages/_editable_impl_robomme.pth` 内容是 `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006/src` 一行（path-style editable，整个 `src` 进 `sys.path`）；`tests/_shared/repo_paths.py::ensure_src_on_path` 同样插入 `src`。`pyproject.toml` 的 `packages = ["src/robomme"]` 只影响 wheel。
- 并行实测（`scripts/data-generation-newSeed/CLAUDE.md`）：`--workers 32` 稳态 56.12 ep/min，44 崩（264 次 `BrokenProcessPool`）；双卡 38.12 低于单卡 55.61；单 worker RSS 2.5–3.7 GB、全量峰值 4666 MB、显存约 498 MB。
- 测试：`tests/lightweight/` 里真正 `gym.make` 的只有 `test_TaskGoalI_isList.py`（`slow, gpu`）；`gpu` marker 无自动 skip。

## 六、未核实清单

1. `/data/hongzefu/data_0226/` 是否就是 HF revision `a5e4e25…`，未用 sha256 核对；`plot_persistent_length_dist.py` 默认 `--h5-dir /data/hongzefu/robomme_data_h5` 在本机不存在。
2. 各子任务 `move_to_pose_with_screw` 实际步数未实测；本文所有 T 是按段长均值线性外推（外推公式在计划里）。
3. ButtonUnmaskSwap 两次按按钮是否一定晚于交换动画结束，未验证。
4. ~~ManiSkill `BaseEnv.__init__` 期间是否已调用 `_load_scene`/`_initialize_episode`~~ **已核实**（5.0 节「ManiSkill 生命周期」）。
5. "randint 消耗量与区间无关"只在本 venv torch 2.9.1 CPU Generator 上实测；`randperm` 消耗随 n 变只是推断。
6. 更多方块/更长路径在固定区域内能否生成成功未验证；BinFill 与 PickHighlight 的生成失败被静默吞掉。
7. policy 仓库源码本机不存在，stride-16 公式与 eval 取帧均为 NFS 原件与 MotionJEPA 文档转引，holdout 2,779 窗由 subagent 数值复现。
8. 过滤后按任务×难度的 chunk 拆分、W&B 在线 summary 未取得。
9. ~~本分支生成器是否已含 `--binfill-demo` 代码~~ **已核实**：不含（2.2 节末）。
10. subagent 统计脚本与 JSON 在 scratchpad，会话结束即失；需要留档时按 4.1 的命令重跑。
11. VideoPlaceOrder `current_task_specialflag(s)` 命名不一致是否影响 hard 下的 swap 行为，未逐行确认（5.1 节）。
12. `make_vec` 路径下 `_env.spec = spec_` 也会走 property setter，本仓库未走该路径，未验证。
