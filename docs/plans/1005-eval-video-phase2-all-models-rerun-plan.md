# 1005-eval-video-phase2-all-models-rerun-plan.md — 第二阶段：新接口直出官方版式视频，然后在 GL A40 上跑第一、二、三档

> **权威与授权**：只规划不实施。开工须用户明确说「开工」（`AGENTS.md` 第 2 条）。本版 2026-10-06 按用户「重构你的计划现在还是太乱了你把完整对比的表格说清楚了」整体重写，取代 12.463～12.466 各版；口径以本文为准。
> **代码锚点**：`bf7dddf3`（12.462，第一阶段重绘工具 `scripts/eval-official/render_official_video.py` 已合入）。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，提交编号 `12.<小版本>`。
> **外部锚点**：MME-VLA 子模块 `ecf086c3`、PonderPounce `723df357`、SimpleMemVLA `c564c17`（本阶段都不改）。上一轮三档见 `docs/validation/sg-eval-gl-20261004-01/`；SimpleMemVLA、MME 原侧来自 v7.5eval（`docs/validation/v7.5eval/official-rerun.md`）。
> **已批准**（2026-10-06）：第二部分六节预算；Astra 本机 smoke ≤2 局、5 美元；集群操作预授权；占位 job ≤10 卡自行提交／取消、48 h、尽早排队。**未批**：计划本身、开工令。

# 第一部分（给人看）

## 一、一句话方案

只改我们自己的**新接口**，让六条新接口路线（GroundSG Oracle、GroundSG QwenVL、PonderPounce、SimpleMemVLA、MME、Astra）每一局都直接带一份官方版式视频（局目录 `official/`）。改完后在 **GL A40** 上跑三档：第一档生成对拍；第二档 xhard0 上五个模型「原侧 vs 新侧」完整对拍（Astra 不做）；第三档 V9 五个模型各 800 局出新成绩。Astra 只做本机 smoke。

## 二、已定口径（用户原话与裁决，2026-10-05～06）

1. **只改新接口**：「所有的修改都是只对新接口对于我们自己的接口。原版接口你你尽可能保存就可以」。原侧代码（`official_hard_runner.py`、`official_defs.py`、`pp_official_runner.py`、`run_official_hard.sh`、`pair_seat.sh`）与 `third_party/` 一律不改。
2. **所有模型都改、都做三档**：「所有的模型都要改改完了之后都要做一二3阶段。的对拍」；「所有的模型都要跑新接口老接口的对拍。都是GreatLakeA40。」——「所有模型」不含 Astra（用户选定）。
3. **第二档两侧的定义**（用户选「原版环境 + 模型原版代码」）：两侧跑同一批 16 任务 × 1 档 × 12 局 = 192 个身份（原版 RoboMME hard 难度的局）。**原侧** = 原版 RoboMME 环境 + 模型自己的原版评估代码；**新侧** = 我们修改后的 xhard0（`robomme_hard` 的 `test-hard0`）+ 我们的新接口。用户原话：「我说的原版是原版robomme 只跑hard 和修改后的xhard0对拍」。
4. **已有原侧不重跑**：「不需要跑原版的接口啊你不是有Xhard0的对拍吗?还是做那个呀」。GroundSG、PonderPounce 用上一轮 GL 原侧结果；SimpleMemVLA、MME 用 v7.5eval 在 GL A40 上已跑的官方结果（用户选「A」，不新写原侧驱动）。
5. **缺的原侧在 GL 补跑**（用户选「GL 补跑原版」）：PonderPounce 96 局、QwenVL 153 局。
6. **禁止跨机器对比**：「不允许进行跨机的对比如果原版的上一轮的第二档没有的话那就需要重跑」。原侧只取 GL A40 结果。
7. **三档全部在 GL**：「第一第二第三档全部在greatlace上进行」。本机只做 smoke。
8. **Astra 只跑本机 smoke**：「Astra仍然是只跑smoke 其他不跑」。
9. **排期**：第一档提前跑；按模型分批，依赖合完即上 GL；表格里用数字标开跑批次，同号并行（用户选定）。
10. **GroundSG 每局都是官方录像器写的视频**：超时、报错、`unknown` 局由新侧适配器补调官方录像器自己的 `save_video`（用户问「能否实现？」，答可以，见五节）。
11. **第一、二档只出结论不阻塞**，一路跑到第三档结束。
12. **只读输入保留到本轮结束**：上一轮 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/sgeval-20261004/`（用户选「保留到本轮结束」），以及 v7.5eval 的原侧结果。

## 三、全部运行一览（开跑批次：数字相同 = 同时并行）

| 开跑批次 | 前提 | 档 | 模型 | 侧 | 规模 | 机器 |
|---|---|---|---|---|---|---|
| **1** | 开工、有卡即跑，不等改代码 | 第一档 生成对拍 | 全部共用 | — | V9 43 格 × 3 局 + xhard0 16 任务 × 3 局 = 177 局 | GL A40 |
| **1** | 同上 | 第二档 | GroundSG QwenVL | 原侧补跑 | 16 任务 × 1 档 × 12 局 − 已有 39 = 153 局 | GL A40 |
| **1** | 同上 | 第二档 | PonderPounce | 原侧补跑 | 分片 1 共 96 局 | GL A40 |
| **2** | S0、S2a、S2b、S1 合入 + 本机 smoke 通过 | 第二档 | GroundSG Oracle、QwenVL | 新侧 | 2 模型 × 16 任务 × 1 档 × 12 局 = 384 局 | GL A40 |
| **2** | 同上 | 第三档 | GroundSG Oracle、QwenVL | 新侧 | 2 模型 × 800 局 = 1600 局 | GL A40 |
| **3** | 再加 S4、S6 合入 + 本机 smoke 通过 | 第二档 | SimpleMemVLA、MME | 新侧 | 2 模型 × 16 任务 × 1 档 × 12 局 = 384 局 | GL A40 |
| **3** | 同上 | 第三档 | SimpleMemVLA、MME | 新侧 | 2 模型 × 800 局 = 1600 局 | GL A40 |
| **4** | 再加 S5 合入 + 本机 smoke 通过 | 第二档 | PonderPounce | 新侧 | 16 任务 × 1 档 × 12 局 = 192 局 | GL A40 |
| **4** | 同上 | 第三档 | PonderPounce | 新侧 | 800 局 | GL A40 |
| **5** | S3 合入 | smoke | Astra | 新侧 | ≤2 局（付费） | 本机 |

- 同一批内各项各占席位、同时跑；第二档与第三档互不等待。批次 2、3、4 之间也不互相等待，哪批先满足前提就先开。
- 卡数上限 10（单卡席位）；每批开跑时按「剩余局数 × 单局耗时」把空闲席位分给该批，QwenVL 单局最慢（A40 上每步约 1.5 s），分得最多。
- 每批上 GL 前，本机先对该批每条新路线跑 1 局 smoke。

## 四、第二档逐模型完整对比表

两侧都是同一批 16 任务 × 1 档 × 12 局 = 192 个身份（与 `artifacts/v7.5eval/identities-full192.json` 逐个相同，已核对差集为 0），全部 GL A40。

| 模型 | 原侧来源（原版 RoboMME hard + 模型原版代码） | 原侧已知成绩 | 新侧（xhard0 + 新接口） | 对比粒度 | 判差异的参照 | 开跑批次（原侧 / 新侧） |
|---|---|---|---|---|---|---|
| GroundSG Oracle | 上一轮 GL 原侧 192 局，齐全（`sgeval-20261004/gate2-oracle`） | 144/192（75.0%） | 本轮 192 局 | 逐步 + 终态 | 上一轮 GL 同模型原侧 vs 新侧：终态相同 192/192、逐步一致 180 | 已有 / 2 |
| GroundSG QwenVL | 上一轮 GL 原侧 39 局 + 本轮补跑 153 局 | 已有 39 局中 9 局成功；其余待补跑 | 本轮 192 局 | 逐步 + 终态 | 上一轮 GL 分片 00：37/37 逐步一致 | 1 / 2 |
| PonderPounce | 上一轮 GL 原侧分片 0 共 96 局 + 本轮补跑分片 1 共 96 局 | 已有 96 局中 39 局成功（40.6%）；其余待补跑 | 本轮 192 局 | 逐步 + 终态 | 上一轮 GL 分片 0：96/96 逐步一致 | 1 / 4 |
| SimpleMemVLA | v7.5eval「官方历史成绩」E0：2026-09-29 GL A40，模型自带评估代码，192 局（`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v7-eval`，sha256 冻结在 `artifacts/v7.5eval/input-manifest.json`） | 141/192（73.4%） | 本轮 192 局 | **只到终态**（原侧无逐步记录） | 官方自己重跑两遍（O1、O2）与 E0 三对两两：全部 0 翻转 | 已有 / 3 |
| MME | 同上 E0，192 局 | 50/192（26.0%） | 本轮 192 局 | **只到终态** | 官方三对两两：翻转 7、16、19 局，成功率差 −0.5～−1.0 个百分点 | 已有 / 3 |
| Astra | 不做第二档 | — | — | — | — | — |

**每个模型最后交出的结果**（`result.md` 一行一模型）：比较局数（应为 192）、终态相同局数、成功→失败与失败→成功局数、两侧成功率与差、McNemar p。GroundSG、PonderPounce 另给逐步一致局数（GroundSG 只有每次起服务后的第一局逐步可判）；SimpleMemVLA、MME 另给新侧翻转数与官方噪声带的对照。判定行：`GATE2=INFO policy=<模型> compared=192 same_terminal=<n> s2f=<n> f2s=<n> sr_orig=<x> sr_new=<y> …`；缺对即 `GATE2=INCOMPLETE`。第二档是差异报告，不证明成绩等价。

## 五、要改的代码

### 共享部分

- **统一的每步记录格式（S0，主会话）**：重绘工具从每局 `trace.jsonl` 画官方版式。现在 Astra 写 `route=astra-new`、PonderPounce 写 `pp-new`，演示段少初始帧、缺 `demo_frames`、结束原因写成 `env_done`，第一阶段的 `load_trace` 都会拒收。S0 定一份契约 C1～C7，各路线照写，重绘工具不放宽。
- **重绘工具读无损原始帧（S2a）**：`render_episode` 现在写死读 `episode.mp4`；改成可读录像器原始帧，并逐帧核对画面哈希，防止调包。
- **每局收尾多一步（S2b）**：转码删原始帧之前先出官方版式视频；失败保留原始帧，成绩照记。视频函数抽成只含函数的小库 `seat_media_lib.sh`。
- **官方视频独立验收（S2b）**：逐个已接受的局核对 `official/` 下恰好一份，判定行 `OFFICIAL_MEDIA=PASS … skip=0 fail=0`。
- **第二档对比工具扩展（S6）**：`gate2_compare.py` 能读 v7.5eval 的 E0 逐局文件，按身份与新侧比终态，并附官方噪声带。
- **原侧不变的证明**：共享函数的新行为默认关闭，CPU 测试证明关闭时原侧输出与改动前逐字节相同；原侧补跑用上一轮执行副本，不跑新代码。

### 分模型

| 模型 | 现状 | 要改（只在新侧） | 改完后视频 |
|---|---|---|---|
| GroundSG Oracle／QwenVL（S1） | 官方循环每局生成叠字 mp4，被我们删掉；超时、报错、`unknown` 局官方不存 | 不删，搬进 `official/`；超时、报错、`unknown` 时调用官方录像器自己的 `save_video` 补存 | 五条文字、黄点、红框，全由官方程序写 |
| PonderPounce（S5） | 子目标只在服务端日志；记录里是环境标准答案 | 新侧服务端套外壳（不改 PonderPounce 代码）回传「产出当前这批动作的子目标」；客户端换算坐标写进记录，局末重绘 | 五条文字、黄点、红框；子目标出来前显示 `[initializing...]` |
| SimpleMemVLA（S4） | 有文字子任务、无坐标、无每步记录；一次执行一整批动作才返回画面 | 每执行一步留下画面与状态，子目标写当前子任务文字；局末重绘 | 五条文字、无黄点、红框 |
| MME（S4） | 无语言推理、无每步记录 | 写最简每步记录（子目标为空）；局末重绘 | 四条文字、红框 |
| Astra（S3） | 自存 `rollout.mp4` 漏演示帧、无文字条 | 接我们的无损录像器（写 `media/`），记录按契约改，局末重绘；`rollout.mp4` 保留 | 五条文字、黄点、红框 |

GroundSG 补存的原理：官方 `eval_each_episode` 的录像器是 `self.init_episode(...)` 返回的局部对象，正常结束才 `save_video`。新侧适配器在本局开始前给 evaluator 实例包一层 `init_episode` 抓住它；遇到 `StepCapReached`、其他异常或 `unknown` 时，按官方文件名格式调用它自己的 `save_video`。`init_episode` 返回前就失败的局一帧未录，无视频，记原因。

## 六、验收

| 查什么 | 怎么查 | 判定行 |
|---|---|---|
| 记录格式 | 每条新路线真实 writer 写出夹具 → 读回 → `load_trace` → 官方录像器 | `TRACE_CONTRACT=PASS routes=6` |
| 原侧不变 | 共享函数关闭时原侧夹具输出与 `bf7dddf3` 逐字节比；原侧文件零 diff | `ORIG_SIDE_UNCHANGED=PASS`、`ORIG_FILES_UNCHANGED=PASS` |
| 接线不改策略行为 | 固定观测与固定服务回包下，改前、改后客户端的请求与动作逐个比 | `CLIENT_REPLAY_EQ=PASS routes=6 mismatches=0` |
| 每局一份官方视频 | `official_media_check.py`，分母为已接受身份 | `OFFICIAL_MEDIA=PASS total=<n> skip=0 fail=0 frame_mismatch=0` |
| 第一档 | `noise_gate.py gen-regress check` | `GEN_REGRESS=PASS|FAIL`（不阻塞） |
| 第二档 | 四节对比表 | 每模型 `GATE2=INFO compared=192 …` |
| 第三档 | `eval_report.py` + `video_check.py` + `official_media_check.py` | 每模型 800 唯一终态、`VIDEO_SAVED=PASS`、`OFFICIAL_MEDIA=PASS total=800 skip=0 fail=0` |

结论边界：第二档是差异报告，第三档是新成绩；在线成绩是否与改前等价写「未验证」。

## 七、子代理分工与合并（简述）

主会话先写 S0 契约并提交。然后同一时刻派出七块：S2a 重绘工具、S2b 席位脚本与视频验收、S1 GroundSG、S6 第二档对比工具、S4 SimpleMemVLA 与 MME、S5 PonderPounce、S3 Astra，各管互不重叠的文件，各在自己的 worktree 写。合回顺序 S2a → S2b → S1 → S6 → S4 → S5 → S3；每次合并前核对改动范围、复跑测试、派一个只读审查者看差异；合并后跑核心短测与项目闸门、立即 push。S1 合完即可开批次 2，不等后面几块。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线与共享契约

**红线**

- R1 原侧零改动：`scripts/eval-official/{official_hard_runner.py,official_defs.py,pp_official_runner.py,run_official_hard.sh,pair_seat.sh}`、`third_party/**`、`src/robomme/`（P2）、`scripts/` 顶层四入口（P1）零 diff。
- R2 共享代码（`mmesg_client.py`、`pp_client.py`、`trace_writer.py`、`recorder.py`、`run_seat.sh`）的新行为一律由显式参数或环境变量打开，默认保持 `BASE` 行为。
- R3 官方 `RolloutRecorder` 不复制、不改写；GroundSG 只调用官方实例的 `save_video`；其余路线经 `render_official_video.py` 以 `importlib` 加载官方类。
- R4 `episode.mp4` 口径、`video_check.py`、`eval_video_mover.py` 不改；官方版式文件一律放 `official/`。
- R5 第一阶段产物（重绘工具既有 16 个用例、站点、`sg-eval-gl-20261004-01/` 留档）不回滚；重绘工具只做向后兼容的重构。
- R6 预算按六节，超出即停并合并补充授权；Astra 只许本机 smoke ≤2 局、5 美元。
- R7 只读输入，到本轮结束不删不移：`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/sgeval-20261004/`、`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v7-eval/`（E0）、`artifacts/v7.5eval/`（O1、O2 与身份清单）。
- R8 第二档原侧只取 GL A40 结果；合表逐行核来源节点，出现非 GL 来源即 `GATE2=INVALID reason=cross_machine`。
- R9 子代理 worktree 内只跑 CPU 定向测试：`UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <定向> -q`，先打印 `robomme_hard.__file__` 确认在 `<worktree>/src/`。

**共享契约 C1～C7**（S0 写进 `trace_writer.py` 文档串与测试助手；字段以 `render_official_video.load_trace` 现行要求为准）

- C1 新侧 `route` 一律 `<模型>/new`：`mmesg/<variant>/new`（已符合）、`pp/new`、`astra/new`、`smvla/new`、`mme/new`。
- C2 演示段记全部 reset 帧（含最后一帧初始画面），`len(states) == frames`；收尾 `close(..., demo_frames=<演示帧数，不含初始帧>)`，满足 `demo.frames == end.demo_frames + 1`。
- C3 `status` 与 `terminal_reason` 只取 `success`／`fail`／`timeout`／`error` 的规定组合；strict-cap 命中一律 `timeout`。
- C4 每步记执行后的画面、状态、动作与当步子目标；动作 float64 原值写同目录 `arrays.npz`。
- C5 `trace.jsonl`、`arrays.npz`、原始帧同一目录。
- C6 identity 含 `source_episode` 或 `builder_episode`，以及与局目录名 `<key>.a<N>` 一致的 `key`。
- C7 子目标为 `None` 的等待帧在官方录像时以 `[initializing...]` 占位；轨迹里保留原始 `None`。

S0 同时提交测试助手 `tests/pipeline/evalx/report/trace_contract.py::assert_renderable(ep_dir)`。

## 一、逐文件改动清单

**S1 GroundSG 新侧**（`scripts/eval-official/mmesg_client.py`）
- 新增 `OFFICIAL_VIDEO_SUBDIR = "official"`、`keep_official_videos(video_dir, dst) -> list[str]`。
- `run_official_episode` 新增 `keep_official: bool = False`：为真时调用前包一层 `evaluator.init_episode` 捕获 `(task_goal, recorder)`；`except` 分支与 `flag == "unknown"` 时若 `video_dir` 无 mp4，按 `f"{runner.env_id}_ep{runner.episode_id}_{flag}_{task_goal}_{runner.difficulty}.mp4"`（`safe_filename` 同款截断）调用 `recorder.save_video`，失败只记 `official_save_error`；`finally` 在 `rmtree(video_dir)` 前搬入 `archive_dir/official/`；返回加 `official_videos`、`official_source`（`official`／`official-salvaged`／`none`）；包装在 `finally` 还原。
- 新侧 `run_episode` 传 `keep_official=True`；原侧不传（R1）。
- 测试 `tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py`：正常局 1 个 mp4 含 `ep3a1_`；strict-cap、异常、`unknown` 各 1 个且 `official-salvaged`；`init_episode` 前失败为空；`keep_official=False` 与 `BASE` 逐字节一致。

**S2a 重绘工具**（`scripts/eval-official/render_official_video.py`）
- `render_episode` 重构为「来源选择 → 解码 → 核验 → 录像 → 复核」：来源 `mp4`／`raw-new`（`front.mkv`、`wrist.mkv` + `frames-<stream>.jsonl` 的 `enc` 展开）／`raw-orig`（`frames/{front,wrist}.rgb24` + `frames.json`），展开规则照 `run_seat.sh::transcode_episode_dir` 文档串；CLI 新增 `--source {auto,mp4,raw}`；`raw` 模式下缺流、索引损坏、重复索引、有损降级一律失败、不退回 mp4。
- 每路流与索引文件算 sha256 进 `render.json` 与复用上下文；逐帧比对解码画面哈希与 `trace` 记录哈希；`PASS` 行加 `source_kind=`。
- 测试 `tests/pipeline/evalx/report/test_sgx_render_official_video.py`：无 mp4 的无损夹具通过；调包流、错 `enc`、缺帧、重复索引、改 raw 后复用五个反例失败；raw 删除后重入走复用；既有 16 个用例不变。

**S2b 席位与官方视频验收**
- 新文件 `scripts/eval-official/seat_media_lib.sh`（只含函数）：从 `run_seat.sh` 移入 `transcode_episode_dir`；新增 `render_official_dir`（`--source raw --jobs 1`，ffmpeg 与转码同源解析；GroundSG 局已有 `official/*.mp4` 则打印 `OFFICIAL_RENDER=KEPT`）。
- `run_seat.sh`：`source seat_media_lib.sh`；在 `publish_dir` 内、`transcode_episode_dir` 之前，仅当 `SGEVAL_OFFICIAL_RENDER=1` 调 `render_official_dir`；失败则保留本局 raw、写 `official-render.failed`、照常发布成绩；`start_server` 的 pp 分支在 `SGEVAL_PP_SERVER_WRAP=1` 时起 `scripts/eval-official/pp_server_wrap.py`（参数与原命令相同）。
- `run_eval_gl.sh`：导出 `SGEVAL_OFFICIAL_RENDER=1`、`SGEVAL_PP_SERVER_WRAP=1`。
- 新文件 `scripts/eval-official/official_media_check.py`：以 `eval_report.py` 的已接受身份为分母，查 `official/*.mp4` 恰 1、可解码、帧数口径（`demo_frames + 1 + exec_steps − omitted`），输出 `OFFICIAL_MEDIA=` 与 `official-media.jsonl`。
- 测试：`tests/pipeline/eval/test_seat_scripts.py`（`official/*.mp4` 出现、`episode.mp4` 仍恰一个、失败保留 raw）；新文件 `tests/pipeline/eval/test_official_media_check.py`（缺失、重复、失败、帧数不符）。

**S3 Astra 新侧**（`scripts/eval-official/astra_hard_runner.py`、`run_astra.sh`）
- route `astra/new`，identity 补 `builder_episode`、`key`，演示与收尾按 C2、C3。
- `run_one` 首次 reset 时建 `recorder.EpisodeRecorder(<ep>/media, meta)`（`media/` 新建且为空，禁止 `overwrite=True`；meta 取 `env_client.SeatRunner` 同款字段并 `never_degrade=True`）；`TracedEnv` 只 `add_frames`／`add_array`；`run_one` 的 `try/finally` 统一 `close(summary)`；`trace.jsonl` 写进 `media/`。
- `run_astra.sh` 只 `source seat_media_lib.sh`，显式设 `BENCH_PY`／`TOOL_PY`。
- 测试 `tests/pipeline/evalx/astra/test_astra_wiring.py`：帧数口径、`assert_renderable`、source 后 `MAX_STEPS` 与 `trap` 不变。

**S4 SimpleMemVLA 与 MME 新侧**
- `smvla_client.py`：`step_chunk` 新增 `on_obs(step, front, wrist, state, terminated, truncated)` 回调（一步多帧取最后一帧）；`run_episode` 建 `TraceWriter(route="smvla/new")`，演示按 C2；决策回包的子任务文本（键名以 `smvla_server.py` 回包为准，实施第一步核对）作当前子目标，在 `on_obs` 里 `log_step`；strict-cap 按 `timeout` 关闭。
- `mme_client.py`：在 `run_episode` 内包一层 `session.step` 钩子拿完整五元组，`reset_fn` 外包一层记演示；`TraceWriter(route="mme/new")`、`subgoal=None`；`EnvRunnerShim` 返回 `(None, None, None)` 的步不记；收尾按 C2、C3。
- 测试 `tests/pipeline/eval/test_policy_clients.py`：两路线 `assert_renderable`；smvla 步数行 = 执行步数且子目标非空；mme 子目标全 `None`；strict-cap 局 `timeout`。

**S5 PonderPounce 新侧**
- 新文件 `scripts/eval-official/pp_server_wrap.py`：子类化 `ponderpounce.eval.robomme_server.PonderPounceRoboMMEServer`（不改原文件）；覆写 `_fire_s1`：调用父类前取 `_visible_cognition(ep, now)`，维护本局「最近一个已可见且非空的子目标」，父类生成 `ep.chunk` 后挂到 chunk 上；覆写 `_dispense`：结果加 `"subgoal": <chunk 上的子目标> or None`（hold 为 `None`）；入口 `run_server(<子类>)`。
- `pp_client.py`：新增 `pp_subgoal_to_official(text)`：每组 `at [x, y]`（0～1000）→ `at <round(y*255/1000), round(x*255/1000)>`，夹到 0～255（整数像素正向换算的值往返精确）；`TracedConnection.act` 存 `last_subgoal`；新侧 `trace_step` 加 `subgoal` 关键字（默认 `None`）；oracle 标签改记 `history` 行 `note=oracle_simple_subgoal:<文本>`；route、演示、收尾按 C1～C3；原侧不传新参数。
- 测试：`tests/pipeline/evalx/pp/test_pp_protocol_wire.py`（`at [612, 247]` → `at <63, 156>`、0～255 全量往返、多组坐标、越界、`None`、回包 `subgoal` 进轨迹、`assert_renderable`）；新文件 `tests/pipeline/evalx/pp/test_pp_server_wrap.py`（`ready_at_ns` 之前回旧子目标、chunk 耗尽时不变、首个子目标前 `None`）。

**S6 第二档对比工具扩展**（`scripts/eval-official/gate2_compare.py`）
- 新增 `--orig-format {sgeval,v75}`（默认 `sgeval`，现行为不变）：`v75` 读 E0 逐局文件（`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/v7-eval` 下 `mme-episodes`／`smvla-episodes`，读前按 `artifacts/v7.5eval/input-manifest.json` 核 sha256），按 `(task, source_episode, seed)` 与新侧结果对齐，只比终态（复用 `--mode astra` 的终态路径）。
- 新增 `--noise-runs <O1> <O2>`（`artifacts/v7.5eval/nfs-archive/official/{O1,O2}`）：E0、O1、O2 三对两两翻转数与新侧对 E0 的翻转数同行输出，判定行加 `noise_flips=<a>,<b>,<c>`。
- 测试新文件 `tests/pipeline/eval/test_gate2_v75.py`（假 E0／O1／O2 与新侧：对齐、缺对 `INCOMPLETE`、sha 不符报错、默认格式输出与 `BASE` 逐字节相同）。

**主会话**：S0；新增测试文件如需登记 `tests/contract/benchmark_contracts.json` 由主会话改；回放脚本 `scripts/eval-official/client_replay_eq.py`（一次性，合并后跑）；留档。

## 二、子代理分配表

`BASE` = S0 提交后的 HEAD。

| 子任务 | 目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖 | 合并顺序 | 验收命令与判定行（worktree 内，R9 环境） | 资源 | 共享文件归属 |
|---|---|---|---|---|---|---|---|---|
| S0 | 共享契约与测试助手 | `trace_writer.py`（仅文档串）、`tests/pipeline/evalx/report/trace_contract.py` | R1 | C1～C7 | 派发前 | 主会话自做：`pytest tests/pipeline/evalx/report -q` | CPU | 主会话 |
| S2a | 重绘工具重构 | `render_official_video.py`、`tests/pipeline/evalx/report/test_sgx_render_official_video.py` | R1、其余 `scripts/eval-official/*` | CLI 向后兼容；`--source`、`source_kind` | 1 | `pytest tests/pipeline/evalx/report -q` passed | CPU ≤5 分钟 | 无 |
| S2b | 席位函数库与视频验收 | `seat_media_lib.sh`（新）、`run_seat.sh`、`run_eval_gl.sh`、`official_media_check.py`（新）、`tests/pipeline/eval/test_seat_scripts.py`、`tests/pipeline/eval/test_official_media_check.py`（新） | 同上 | `render_official_dir`、`transcode_episode_dir`；`SGEVAL_OFFICIAL_RENDER`、`SGEVAL_PP_SERVER_WRAP` | 2 | `pytest tests/pipeline/eval/test_seat_scripts.py tests/pipeline/eval/test_official_media_check.py -q` passed | CPU | `run_seat.sh` 唯一写者 |
| S1 | GroundSG 新侧 | `mmesg_client.py`、`tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py` | 同上 | `keep_official`（默认 False） | 3 | `pytest tests/pipeline/evalx/groundsg -q` passed | CPU | 无 |
| S6 | 第二档对比工具 | `gate2_compare.py`、`tests/pipeline/eval/test_gate2_v75.py`（新） | 同上 | `--orig-format`、`--noise-runs` | 4 | `pytest tests/pipeline/eval/test_gate2_v75.py -q` passed | CPU | 无 |
| S4 | SimpleMemVLA、MME 新侧 | `smvla_client.py`、`mme_client.py`、`tests/pipeline/eval/test_policy_clients.py` | 同上 | 只读 `trace_writer`、`mmesg_client.trace_location` | 5 | `pytest tests/pipeline/eval/test_policy_clients.py -q` passed | CPU | 无 |
| S5 | PonderPounce 新侧 | `pp_client.py`、`pp_server_wrap.py`（新）、`tests/pipeline/evalx/pp/test_pp_protocol_wire.py`、`tests/pipeline/evalx/pp/test_pp_server_wrap.py`（新） | 同上 | 回包键 `subgoal`；`pp_subgoal_to_official` | 6 | `pytest tests/pipeline/evalx/pp -q` passed | CPU | 无 |
| S3 | Astra 新侧 | `astra_hard_runner.py`、`run_astra.sh`、`tests/pipeline/evalx/astra/test_astra_wiring.py` | 同上 | 只 source `seat_media_lib.sh` | 7 | `pytest tests/pipeline/evalx/astra -q` passed | CPU | 无 |
| 运行型 R1～Rn | 按三节批次在 GL 席位启动 `run_eval_gl.sh`／`run_official_hard.sh` | 无 | 一切代码 | 命令原文照四节 runbook | 开工后 | 起跑判据 `SEAT_START`／`ROUTE_START` + 首局 `REC_TRANSCODE … result=ok` + 首局 `OFFICIAL_RENDER=` | GL 席位 | 账目归主会话 |

派发前核对：`worktree.baseRef=head`；`git check-ignore -q .claude/worktrees/probe`；`git worktree list` 存档，既有 worktree 不动；`git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'` 为空。

## 三、闸门总表

| 闸门 | 命令 | 判定行 |
|---|---|---|
| 核心短测（每次合并后） | `timeout 280s uv run --no-sync python -m pytest -m 'not slow' -q` | passed、`TEST_RESOURCE=PASS`、`TEST_INVENTORY=PASS` |
| 项目闸门 | `ls -1 scripts/*.py`；`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`；`uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | 四入口；零 diff；`UPSTREAM_GUARD=PASS` |
| 原侧零改动 | `git diff --quiet <BASE> HEAD -- scripts/eval-official/{official_hard_runner.py,official_defs.py,pp_official_runner.py,run_official_hard.sh,pair_seat.sh} third_party` | `ORIG_FILES_UNCHANGED=PASS` |
| 记录契约 | 各子任务测试的 `assert_renderable` | `TRACE_CONTRACT=PASS routes=6` |
| 客户端回放 | `client_replay_eq.py --base <BASE> --head HEAD` | `CLIENT_REPLAY_EQ=PASS routes=6 mismatches=0` |
| 本机 smoke | 每批每路线 1 局（新 run 名、新 preflight 目录） | `OFFICIAL_MEDIA=PASS total=1 skip=0 fail=0`、`VIDEO_SAVED=PASS multi_mp4=0` |
| 第一档 | `noise_gate.py gen-regress check --set {v9,xhard0}` | `GEN_REGRESS=` 如实记录 |
| 第二档 | GroundSG、PonderPounce：`gate2_compare.py --orig-results <原侧合表> --new-results … --orig-traces … --new-traces …`（GroundSG 加 `--groundsg`）；SimpleMemVLA、MME：`gate2_compare.py --orig-format v75 --noise-runs <O1> <O2> …` | 5 模型各 `GATE2=INFO compared=192 …` |
| 第三档 | `eval_report.py`、`video_check.py`、`official_media_check.py` | 每模型 800 唯一终态、`VIDEO_SAVED=PASS`、`OFFICIAL_MEDIA=PASS total=800 skip=0 fail=0` |

## 四、runbook（主会话）

1. **占位 job**（已获授权，不是开工令）：同时请求 ≤10 张单卡 `--account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:a40:1 --gpu_cmode=shared --cpus-per-task=4 --mem=64G --time=48:00:00 --wrap='sleep infinity'`，到期立即同规格续交。现有：`sgev-hold-00～07` = 63188711～16、63188719、63188720，`sgev-hold-08`、`09` = 63325534、63325535；清单 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/gl-hold-logs/hold-jobs-sgeval-20261004.txt`；收尾按清单逐个 `scancel`。
2. **批次 1**：第一档沿用 1003 第五节第一档做法（执行副本 `robomme_benchmark-noise` 检出开工时 HEAD；`--attempts n --resets 3n --retries 0`）；原侧补跑用上一轮执行副本 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-sgeval`（不同步、不改，起跑记录其 HEAD），`run_official_hard.sh` 跑 PonderPounce 分片 1 与 QwenVL 未跑分片（QwenVL 单局墙钟 3600 s，用上一轮 `launch_seat_v2.sh` 体例），结果写本轮新 stage，合表时与上一轮原侧按身份并起。
3. **改代码**：S0 提交 → 同一消息派 S2a、S2b、S1、S6、S4、S5、S3（`model: "opus"`、`isolation: "worktree"`）→ 按合并顺序逐个第一次审查、`git merge --no-ff <TIP sha> -F <消息文件>`、第二次审查、push。
4. **批次 2、3、4**：前提满足即本机 smoke（tmux 前缀 `ovl2-`）→ NFS 新建执行副本 `robomme_benchmark-sgeval2-<批次>`（`git clone --no-hardlinks` + `git submodule update --init`，检出冻结 sha；主 `.venv` 用 `UV_LINK_MODE=copy uv sync --frozen --group eval-client`；三方服务 venv 经 `MME_PY`／`PP_PY`／`SMVLA_PY` 指向上一轮执行副本中的对应 venv）→ 第二档与第三档分片各占席位同时起 `run_eval_gl.sh`（`--dataset test-hard0 --max-steps 1300`／`--dataset test-hard --max-steps 1600 --strict-cap`）。
5. **批次 5**：S3 合入后本机 Astra smoke ≤2 局，`astra_cost_guard.py` 同时起，5 美元到线即停。
6. **本轮全新目录**：run 名 `sg-eval-gl-<开工日期>-02`；stage、账本、media、trace、日志全部新建，命令逐条写进 `launch.md`，不复用上一轮 stage；起跑后核对每条路线首局确有新 attempt。
7. **监听**：每份日志一个 Monitor，过滤 `EXIT_CODE=|RUN_BLOCKED|INFRA|OFFICIAL_RENDER=FAIL|OFFICIAL_MEDIA=|Traceback|CUDA|svulkan2|EXCLUSIVE|NO RECORD|reset 拒绝`；开工后按 1003 第五节挂「排到卡即唤醒」。
8. **收尾**：各模型第二档对比表（四节格式）、第三档成绩表、`OFFICIAL_MEDIA` 汇总、视频索引；留档 `docs/validation/sg-eval-gl-<日期>-02/{launch.md,result.md,records/}`；commit、push；按清单 `scancel`。

## 五、风险与盲区

| 项 | 说明 | 处置 |
|---|---|---|
| SimpleMemVLA、MME 第二档只到终态 | E0 只有逐局终态，没有逐步记录 | 只比终态与成功率，用官方噪声带判差异是否正常；不宣称逐步一致 |
| MME 官方本身不可复现 | 官方三对两两翻转 7～19 局 | 新侧翻转数落在噪声带内只记「与官方噪声相当」，不写「一致」 |
| E0 与本轮跨时间 | E0 为 2026-09-29，驱动、节点与本轮可能不同 | 留档写明 E0 的运行条件（v7.5eval 留档）；不重跑 |
| GroundSG 补存视频的帧数口径 | 官方超时先 break 后 record | 按 `omitted` 字段区分，`official_source` 记来源 |
| PonderPounce 外壳依赖私有方法 | `_fire_s1`、`_dispense`、`_visible_cognition` 属锁定提交 `723df357` | 测试钉死；改不通即停交用户 |
| SimpleMemVLA 回包子任务键名 | 未逐字核对 `smvla_server.py` | S4 第一步核对，不符先改计划 |
| 跨时间对照 | GroundSG、PonderPounce 新侧与上一轮原侧不同时跑 | 只出差异报告，留档写明 |
| QwenVL 墙钟 | V9 1600 步单局最长约 40 分钟 | 单局墙钟 3600 s；48 h 到期按 1003「到期与续交」 |
| GL 配额 | 账户 GPU 20 张已满，cokite 12 张到 10-13 后 | 现有 7 张 RUNNING 先用；批次按前提自动排开 |
| 第一档锚点早于最终代码 | 第一档在改代码期间跑 | 留档附 `git diff --stat <第一档冻结>..<各批冻结> -- src scripts/parity scripts/injection-dev` 为空 |
| 本计划判定行 | 全部待实施 | — |

## 六、预算（2026-10-06 已批，合计在批准额度内）

评估每局 build 与 reset 各 1 次计 2 次 reset；生成每条轨迹 reset 上限 3 次。V9 每模型 800 局 = `3任务×2档×17 + 3任务×1档×16 + 2任务×5档×10 + 2任务×2档×13 + 2任务×2档×12 + 7任务×2档×25 + 2任务×1档×50`（`hard_specs.py::_v9_cells`）。

| 用途 | 乘式 | 轨迹 | reset 上限 |
|---|---|---:|---:|
| GL 第一档首跑 | V9 43 格 × 3 局 + xhard0 16 任务 × 3 局 | 177 | 531 |
| GL 第一档 smoke 与重跑 | 2 + ≤20（两集合共用，V9 优先） | 22 | 66 |
| 本机 smoke（非 Astra） | 5 路线 × 1 局 | 5 | 10 |
| 本机 smoke 修复后重跑 | 5 路线 × ≤2 局 | 10 | 20 |
| 本机 smoke（Astra，付费） | ≤2 局 | 2 | 4 |
| GL smoke（新侧） | 5 路线 × 1 局 | 5 | 10 |
| GL 第二档新侧 | 5 模型 × 16 任务 × 1 档 × 12 局 | 960 | 1920 |
| GL 第二档原侧补跑 | PonderPounce 分片 1 共 96 局 + QwenVL（16 任务 × 1 档 × 12 局 − 已有 39）= 153 局 | 249 | 498 |
| GL 第三档 | 5 模型 × 800 局 | 4000 | 8000 |
| 基础设施重试 | 非 Astra 5 模型 × ≤10 次（整批共享，补跑计入所属模型） | 50 | 100 |
| 到期续跑 | 5 模型 × ≤100 局 | 500 | 1000 |
| **合计** | | **5980** | **12159** |

审批记录：用户 2026-10-06「234都同意 计划我在看」批准预算、Astra 本机 smoke ≤2 局与 5 美元、集群操作预授权（清理自己 job 内卡死的 `srun` 步骤、按清单精确 JobID 取消自己的 job）；随后批准过 SimpleMemVLA、MME 新原侧 384 局增量（合计 6364／12927），用户改选「A：复用已有原侧」后该增量不再使用，合计回到 5980／12159。正常 fail／timeout 不重试；smoke 不进正式分母；账本持久化。

## 七、留档与 commit 纪律

- S2a、S2b、S1、S6、S4、S5、S3 各经 `--no-ff` 合并占一个项目号，子代理提交前缀 `sub/<编号>: `；S0、回放脚本、留档由主会话按第 11 条六项 body 提交，含第一部分二节的用户原话。
- 留档 `docs/validation/sg-eval-gl-<日期>-02/`：`launch.md` 起跑即写（执行副本 sha、各批冻结 sha、JobID、tmux 会话清单、完整命令）；`result.md` 跑完写（四节格式的第二档对比表、第三档成绩表、`OFFICIAL_MEDIA` 汇总、结论边界）；`records/` 只归档判定行、差异表、视频索引与一次性脚本逐字副本；不归档 mp4。
- `docs/validation/sg-eval-gl-20261004-01/`、`docs/validation/v7.5eval/` 不改；R7 所列输入到本轮结束前不动。
