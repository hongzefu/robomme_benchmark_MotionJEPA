# 1005-eval-video-phase2-all-models-rerun-plan.md — 第二阶段：新接口全部模型直出官方版式视频，然后在 GL 上重跑第一、二、三档

> **权威与授权**：只规划不实施。开工须用户明确说「开工」（`AGENTS.md` 第 2 条），并在开工前一次性批准第二部分「六、预算」与占位 job（P3）。本版（2026-10-06 重写）取代 2026-10-05 初稿（`1c66477d`，原位于仓库根目录），改写依据是同日两份对抗审计（本会话 workflow 与 Codex 静态审计，均判定初稿不可直接开工）和用户逐条裁决。
> **代码锚点**：`bf7dddf3`（12.462，第一阶段 Codex 产物已全部合入：重绘工具 `scripts/eval-official/render_official_video.py`、Oracle 800 局官方版式重绘、站点）。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，提交编号沿用 `12.<小版本>`。
> **外部锚点**：MME-VLA 子模块 `ecf086c3`、PonderPounce `723df357`（本阶段都不改）；上一轮三档的规模、流程与留档见 [`1003-oracle-subgoal-groundsg-eval-plan.md`](../../1003-oracle-subgoal-groundsg-eval-plan.md) 与 `docs/validation/sg-eval-gl-20261004-01/`；第一阶段见 [`1005-eval-video-official-overlay-plan.md`](../../1005-eval-video-official-overlay-plan.md)。

# 第一部分（给人看）

## 一、一句话方案

只改我们自己的**新接口**，让六条新接口路线（GroundSG Oracle、GroundSG QwenVL、PonderPounce、Astra、SimpleMemVLA、MME）跑出来的每一局都直接带一份官方版式视频（局目录 `official/` 下）；原版接口一行不改。改完后**第一、二、三档全部在 greatlakes 上跑**：第一档生成对拍提前跑，第二档 xhard0 只跑新接口、对照上一轮原版接口结果（缺的原版局在 GL 补跑），第三档 V9 五个模型各 800 局出新成绩。

## 二、已定口径（用户 2026-10-05～06 原话与裁决）

1. **只改新接口**：「我澄清一下所有的修改都是只对新接口对于我们自己的接口。原版接口你你尽可能保存就可以」。`official_hard_runner.py`、`pp_official_runner.py`、`run_official_hard.sh`、Astra 的 `run.sh` 与 `third_party/` 全部不改；共享函数里的新行为默认关闭、只由新侧打开。
2. **所有模型都改、都做三档**：「所有的模型都要改改完了之后都要做一二3阶段。的对拍」。
3. **第二档不重跑原版**：「不需要跑原版的接口啊你不是有Xhard0的对拍吗?还是做那个呀」——新接口只与上一轮 `sg-eval-gl-20261004-01` 的原版结果比。
4. **上一轮原版缺的部分在 GL 补跑**（用户选「GL 补跑原版」）：PonderPounce 分片 1 共 96 局、QwenVL 上一轮未跑的 153 局；补跑用上一轮的 GL 执行副本，与已有原版结果同码。
5. **SimpleMemVLA、MME 第二档只记录不对比**（用户选「可以，只记录」）：两者没有原版接口、上一轮也没跑过。
6. **三档全部在 GL**：「第一第二第三档全部在greatlace上进行」。本机只做每条新路线 1 局 smoke。
7. **排期**（用户选「第一档提前+按模型分批」）：第一档在改代码期间就跑；第二、三档哪个模型的依赖合完就先上 GL，各记各的冻结 sha。
8. **Astra 只做本机 smoke，其余一局不跑**：「Astra仍然是只跑smoke 其他不跑」（2026-10-06）。Astra 新侧照样改（S3），只用本机 smoke（≤2 局，付费）验证；第二档原版与新接口、第三档连通局全部取消。原侧不出官方版式视频（用户选「原侧不出」）。
9. **GroundSG 的视频全部由官方录像器自己写出**：用户问「能否实现？」——可以，见第三节 GroundSG 一段。
10. **上一轮 NFS 上约 11.9 GB 产物保留到本轮结束**（用户选「保留到本轮结束」），本轮要读它们当对照。
11. **第一、二档只出结论不阻塞**，一路跑到第三档结束（沿用 1003 口径）。
12. **禁止跨机器对比**：「不允许进行跨机的对比如果原版的上一轮的第二档没有的话那就需要重跑」。第二档的原版对照只用上一轮 **GL（A40）** 上的原版结果；上一轮本机（RTX 6000 Ada）的原版与新接口结果一律不进本轮比较；GL 上缺的原版局全部在 GL 补跑（第 4 条）。

## 三、要改什么（先讲共享部分，再分模型）

### 共享部分（所有模型都受益）

- **统一的「每步记录」格式（S0，主会话）**：官方版式要从每局的 `trace.jsonl`（每步画面、动作、状态、子目标、结束方式）画出来。现在各路线写得不统一，第一阶段的重绘工具 `load_trace` 会拒收：Astra 写 `route=astra-new`、PonderPounce 写 `pp-new`（工具要求 `…/new`）；PonderPounce 的演示段少了初始帧、收尾缺 `demo_frames`、结束原因写成 `env_done`。S0 把格式写成一份契约（第二部分〇节 C1～C7），各模型照写，重绘工具不放宽。
- **重绘工具能直接读无损原始帧（S2a）**：现在 `render_episode` 写死从压缩后的 `episode.mp4` 读，而新局要在转码删原始帧之前就画。改成三种来源（mp4、新侧 `front.mkv`／`wrist.mkv`、原侧 `rgb24`），并加强核对：每路流和帧索引都算指纹、解码出的每一帧都与记录里的画面哈希比对，防止「换一局同尺寸同帧数的画面也通过」（Codex 反例）。
- **每局收尾多一步、失败不删原始帧（S2b）**：席位脚本在转码之前先出官方版式视频；出不来就保留原始帧供补救，成绩照常记。视频相关的两个函数抽成一个只含函数的小库 `seat_media_lib.sh`，Astra 也能安全地用。
- **单独的官方视频验收（S2b）**：新工具逐个已接受的局核对 `official/` 下恰好一份官方版式视频，按模型持久化 `kept／rendered／reused／skip／fail` 计数，判定行 `OFFICIAL_MEDIA=PASS … skip=0 fail=0`。它和成绩验收分开，原 `video_check.py` 不改。
- **原版接口保持不变的证明**：共享函数新行为默认关；CPU 测试证明关掉时原侧写出的记录与改动前逐字节相同。原版补跑另用上一轮执行副本，根本不跑新代码。

### 分模型

| 模型 | 现状 | 要改（只在新接口） | 改完后的视频 |
|---|---|---|---|
| GroundSG Oracle／QwenVL（S1） | 新接口跑的就是官方评估循环，官方每局生成叠字 mp4，被我们在局末删掉；而且官方只在正常结束时存，超时、报错、`unknown` 局不存 | 不删，搬进 `official/`；另在超时、报错、`unknown` 时，由我们调用**官方录像器自己的** `save_video` 补存（不改官方代码，见下段） | 五条文字、黄点、演示帧红框，全部是官方程序写的 |
| PonderPounce（S5） | 子目标只打在服务端日志里，客户端拿不到；现在写进记录的是环境给的标准答案 | 新侧服务端套一层外壳（不改 PonderPounce 代码），回传「产出当前这批动作的那个子目标」；客户端把它的坐标换算成官方格式写进记录，局末重绘 | 五条文字、黄点、红框；子目标出来前的帧显示官方占位文字 `[initializing...]` |
| Astra（S3） | 自己存的 `rollout.mp4` 漏了演示帧、没有文字条 | 新侧接上我们的无损录像器（写到 `media/`），记录格式按契约改，局末重绘；`rollout.mp4` 原样保留 | 五条文字、黄点、红框 |
| SimpleMemVLA（S4） | 有文字子任务（无坐标），没有每步记录；它一次执行一整批动作才返回画面 | 新写每步记录：每执行一步就留下这一步的画面与状态，子目标写当前这批动作的子任务文字；局末重绘 | 五条文字、无黄点、红框 |
| MME FrameSamp+Modul（S4） | 无语言推理、无每步记录 | 写最简每步记录（子目标为空），局末重绘 | 四条文字、红框，与官方 π0.5 视频一致 |

**GroundSG 为什么能做到每局都有官方视频**：官方 `eval_each_episode` 里，录像器是 `self.init_episode(...)` 返回的局部对象，正常结束才 `recorder.save_video(...)`。新接口适配器 `mmesg_client.run_official_episode` 在本局开始前给这个 evaluator 实例包一层 `init_episode`，把返回的官方录像器抓住；遇到 `StepCapReached`（V9 的 strict-cap 超时）、其他异常或 `unknown` 时，用官方同样的文件名格式（状态段写 `timeout`／`error`／`unknown`）调用这个录像器自己的 `save_video`。唯一拿不到视频的是 `init_episode` 返回前就失败的局（一帧都没录），记原因、计入 error。

## 四、在 GL 上跑什么

| 档 | 内容 | 规模（乘式） | 对照 |
|---|---|---|---|
| 第一档 生成对拍（提前跑） | 只测生成，与模型无关 | V9 43 格 × 3 局 + xhard0 16 任务 × 3 局 = 177 局 | 噪声基线 `scripts/configs/noise-ref-20261003.json` |
| 第二档 xhard0 新接口 | GroundSG Oracle、QwenVL、PonderPounce、SimpleMemVLA、MME | 5 模型 × 16 任务 × 1 档 × 12 局 = 960 局 | 前三个对上一轮原版结果；后两个只记录 |
| 第二档 原版补跑 | PonderPounce 分片 1、QwenVL 未跑部分 | 96 局 + (192 − 39) = 153 局，共 249 局 | 与上一轮已有原版结果合成完整对照 |
| 第三档 V9 正式评估 | 五个模型 | 5 模型 × 800 局 = 4000 局（800 的乘式见第二部分六） | 新成绩 |

本机只做 smoke：五条非 Astra 新路线各 1 局，Astra 新侧 1 局（失败可再 1 局）；Astra 在 GL 上一局不跑。

## 五、验收（查什么／怎么查／判定行）

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| 记录格式 | 每条新路线的真实 writer 写出夹具 → 读回 → `load_trace` → 官方录像器 | 重绘工具对六条路线都能出片 | `TRACE_CONTRACT=PASS routes=6` |
| 原版不变 | 共享函数关开关时，原侧夹具输出与 `bf7dddf3` 逐字节比 | 原版接口行为未受影响 | `ORIG_SIDE_UNCHANGED=PASS` |
| 每局一份官方视频 | `official_media_check.py` 以已接受身份为分母 | 无缺失、无重复、无失败 | `OFFICIAL_MEDIA=PASS total=<n> kept=<a> rendered=<b> reused=<c> skip=0 fail=0` |
| 帧数口径 | 官方视频帧数 vs `demo_frames + 1 + exec_steps − omitted` | 没有丢帧或多帧；只有执行到 `max_steps+1` 的官方超时少 1 帧，strict-cap 局不少 | 并入 `OFFICIAL_MEDIA` 的 `frame_mismatch=0` |
| 第一档 | `noise_gate.py gen-regress check` | 生成链路没变 | `GEN_REGRESS=PASS|FAIL`（不阻塞） |
| 第二档 | `gate2_compare.py`（新接口 vs 上一轮及补跑原版） | 只是接口差异报告，不证明成绩等价 | 每模型 `GATE2=INFO compared=<乘式>` |
| 第三档 | `eval_report.py` 唯一终态 + `video_check.py` + `OFFICIAL_MEDIA` | 每模型 800 局成绩与视频齐 | `VIDEO_SAVED=PASS`、`OFFICIAL_MEDIA=PASS total=800 … skip=0 fail=0` |
| 接线不改策略行为 | CPU 固定回包回放：同一组固定观测与服务回包，比较改前（`bf7dddf3`）、改后客户端发出的请求与执行的动作 | 录像与记录只旁路、不改请求与动作 | `CLIENT_REPLAY_EQ=PASS routes=6 mismatches=0` |

结论边界：第二档是差异报告、第三档是新成绩；在线成绩是否与改前等价写「未验证」。

## 六、步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 用户「开工」+ 一次性批预算与占位 job；提交占位 job；主检出 clean，记 `BASE` | JobID 记 `launch.md` |
| 1a | 第一档：占位 job 排到即在 GL 起跑（不等改代码） | `GEN_REGRESS=` 行 |
| 1b | 原版补跑：PonderPounce 96 + QwenVL 153，用上一轮执行副本 | 每路线 `EPISODE_DONE` 计数齐 |
| 1c | 主会话写 S0 契约与共享测试助手并提交；同批派 S1、S2a、S2b、S3、S4、S5 | 各子任务定向测试 passed |
| 2 | 依次审查合并 S2a → S2b → S1 → S4 → S5 → S3，每次合并后核心短测 + push | `PRE_MERGE_REVIEW=PASS`、`POST_MERGE_REVIEW=PASS` ×6 |
| 3 | 每条路线依赖合完即本机 smoke 1 局 → GL 冻结执行副本 → 第二档接第三档 | smoke：`OFFICIAL_MEDIA=PASS total=1`；GL 各档判定行 |
| 4 | 全部跑完：汇总、留档 `docs/validation/sg-eval-gl-<日期>-02/`、commit、push、按清单 `scancel` | `git status -sb` 无 `ahead` |

## 七、子代理分工与合并（简述）

改代码切成七块：S0 契约由主会话先写好提交，作为所有人的共同依据；其余六块各管互不重叠的文件——S1 只动 GroundSG 新侧适配器，S2a 只动重绘工具，S2b 只动席位脚本与新验收工具，S3 只动 Astra 新侧，S4 只动 SimpleMemVLA 与 MME 客户端，S5 只动 PonderPounce 客户端与新外壳。六块在同一时刻派出、各在自己的 worktree 里写。合回顺序按依赖：先重绘工具（S2a），再席位脚本（S2b），然后 GroundSG（S1）、SimpleMemVLA/MME（S4）、PonderPounce（S5）、Astra（S3）。每次合并前：核对改动只在它的文件范围内、在它的 worktree 复跑测试、派一个只读审查者看差异；合并后：跑核心短测与项目闸门、立即 push。GroundSG 合完就可以上 GL，不等后面几块。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线与共享契约

**红线**

- R1 不改原版接口：`scripts/eval-official/{official_hard_runner.py,pp_official_runner.py,run_official_hard.sh,pair_seat.sh}`、`third_party/**`（含 PonderPounce、mme-vla、Astra-on-RoboMME）零 diff；`src/robomme/`（P2）、`scripts/` 顶层四入口（P1）零 diff。闸门：`git diff --quiet <BASE> HEAD -- <上列路径>`。
- R2 共享代码（`mmesg_client.py`、`pp_client.py`、`trace_writer.py`、`recorder.py`、`run_seat.sh`）的新行为一律由显式参数或环境变量打开，默认值保持 `BASE` 行为；原侧入口不传这些参数。
- R3 官方 `RolloutRecorder` 不复制、不改写；GroundSG 只调用官方实例的 `save_video`；其他路线一律经 `render_official_video.py` 以 `importlib` 加载官方类。
- R4 `episode.mp4` 口径、`video_check.py`、`eval_video_mover.py` 不改；官方版式文件一律放局目录 `official/`。
- R5 第一阶段产物（重绘工具既有 16 个用例、站点、`sg-eval-gl-20261004-01/` 留档）不回滚；重绘工具只做向后兼容的重构。
- R6 预算按六节一次性批准，不拆阶段再问；超出即停，合并补充授权。Astra 只许本机 smoke ≤2 局，GL 上一局不跑；局数与金额逐项审批，已批范围外一局不跑。
- R7 上一轮 NFS 产物 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/sgeval-20261004/` 本轮只读，到本轮结束不删不移。
- R9 第二档对照只取同为 GL A40 的结果：上一轮 GL 原版已有 Oracle 192/192、PonderPounce 分片 0 共 96、QwenVL 分片 00 共 39（`docs/validation/sg-eval-gl-20261004-01/result.md` 第三节表 1），其余在 GL 补跑；`gate2_compare.py` 的输入清单只列 GL 路径，合表时逐行核对来源节点在 GL，出现本机路径即 `GATE2=INVALID reason=cross_machine`。
- R8 子代理 worktree 内只跑 CPU 定向测试：`UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <定向> -q`，先打印 `robomme_hard.__file__` 确认在 `<worktree>/src/`。

**共享契约 C1～C7（S0 写入 `scripts/eval-official/trace_writer.py` 模块文档串与测试助手；字段名以 `render_official_video.load_trace` 现行要求为准）**

- C1 `route` 一律 `<模型>/new`：`mmesg/<variant>/new`（已符合）、`pp/new`、`astra/new`、`smvla/new`、`mme/new`；原侧写者不动（原侧不重绘）。
- C2 演示段 `log_demo` 记全部 reset 帧（含最后一帧初始画面），`len(states) == frames`；收尾 `close(..., demo_frames=<演示帧数，不含初始帧>)`，满足 `demo.frames == end.demo_frames + 1`。
- C3 `terminal_reason` 与 `status` 只取 `success`／`fail`／`timeout`／`error` 的规定组合；strict-cap 命中（`StepCapReached` 或客户端 `cap_hit`）一律 `timeout`。
- C4 每步 `log_step` 记执行后的画面、状态、动作与当步子目标；动作的 float64 原值写入同目录 `arrays.npz`（录像器 `_write_arrays`）。
- C5 `trace.jsonl`、`arrays.npz`、原始帧（或 `episode.mp4`）同一目录。
- C6 identity 含 `source_episode` 或 `builder_episode`，以及与局目录名 `<key>.a<N>` 一致的 `key`。
- C7 子目标为 `None` 的等待帧在官方录像时以 `[initializing...]` 占位（保证逐帧高度一致）；轨迹里保留原始 `None`。

S0 同时提交测试助手 `tests/pipeline/evalx/report/trace_contract.py::assert_renderable(ep_dir)`（写出 → 读回 → `load_trace` → `feed_official_recorder`），各子任务测试调用它。

## 一、逐文件改动清单

**S1 GroundSG 新侧**（`scripts/eval-official/mmesg_client.py`）
- 新增 `OFFICIAL_VIDEO_SUBDIR = "official"`、`keep_official_videos(video_dir, dst) -> list[str]`（`sorted(glob("*.mp4"))` 移入 `dst`，同名加 `.dupN`）。
- `run_official_episode` 新增关键字参数 `keep_official: bool = False`（R2）：为真时，调用前把 `evaluator.init_episode` 包一层，捕获 `(task_goal, recorder)`；`except` 分支与 `flag == "unknown"` 时，若已捕获录像器且 `video_dir` 下无 mp4，按 `f"{runner.env_id}_ep{runner.episode_id}_{flag}_{task_goal}_{runner.difficulty}.mp4"`（`flag` 取 `timeout`／`error`／`unknown`，文件名经 `render_official_video.safe_filename` 同款截断）调用 `recorder.save_video`，失败只记 `official_save_error`；`finally` 在 `rmtree(video_dir)` 前 `keep_official_videos(video_dir, archive_dir / OFFICIAL_VIDEO_SUBDIR)`；返回字典加 `official_videos`、`official_source`（`official`／`official-salvaged`／`none`）。包装在 `finally` 里还原。
- `run_episode`（新侧）传 `keep_official=True`；`official_hard_runner.py` 不改（R1），因此原侧行为不变。
- 测试 `tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py` 新增：正常局 `official/*.mp4` 恰 1 个且文件名含 `ep3a1_`；strict-cap、异常、`unknown` 三类各 1 个且 `official_source=official-salvaged`；`init_episode` 前失败 `official_videos=[]`；`keep_official=False` 时与 `BASE` 输出逐字节一致（`ORIG_SIDE_UNCHANGED`）。

**S2a 重绘工具**（`scripts/eval-official/render_official_video.py`）
- `render_episode` 重构为「来源选择 → 解码 → 核验 → 录像 → 复核」：来源 `mp4`／`raw-new`（`front.mkv`、`wrist.mkv` + `frames-<stream>.jsonl` 的 `enc` 展开）／`raw-orig`（`frames/{front,wrist}.rgb24` + `frames.json`），展开规则照 `run_seat.sh::transcode_episode_dir` 文档串；CLI 新增 `--source {auto,mp4,raw}`，正式运行由席位传 `raw`，`raw` 模式下缺流、索引损坏、重复索引、有损降级一律失败、不退回 mp4。
- 指纹：每路流与索引文件各算 sha256，进 `render.json` 与复用上下文；逐帧把解码画面哈希与 `trace` 记录的画面哈希比对，不一致即失败。
- `PASS` 行加 `source_kind=`；文件名经现有 `safe_filename`。
- 测试 `tests/pipeline/evalx/report/test_sgx_render_official_video.py` 新增：无 mp4 的真实无损夹具通过；调包流、错 `enc`、缺帧、重复索引、改 raw 后复用五个反例失败；raw 删除后重入走复用、不出第二份；既有 16 个用例不变。

**S2b 席位与官方视频验收**
- 新文件 `scripts/eval-official/seat_media_lib.sh`：只含函数，无顶层赋值；从 `run_seat.sh` 移入 `transcode_episode_dir`，新增 `render_official_dir`（`$1` 局目录：`"$(tool_py)" "$HERE/render_official_video.py" "$1" --official-root "$REPO" --source raw --jobs 1 --ffmpeg "<与转码同源解析的 ffmpeg>"`；GroundSG 局已有 `official/*.mp4` 时跳过并打印 `OFFICIAL_RENDER=KEPT`）。
- `scripts/eval-official/run_seat.sh`：`source seat_media_lib.sh`；在 `publish_dir` 内、`transcode_episode_dir` 调用之前，仅当 `SGEVAL_OFFICIAL_RENDER=1`（新侧 `run_eval_gl.sh` 设置）时调 `render_official_dir`；失败则跳过本局 raw 删除、写 `official-render.failed` 标记、照常发布成绩。`start_server` 的 pp 分支在 `SGEVAL_PP_SERVER_WRAP=1` 时改起 `scripts/eval-official/pp_server_wrap.py`（参数与原命令相同），否则原样。
- `scripts/eval-official/run_eval_gl.sh`：导出 `SGEVAL_OFFICIAL_RENDER=1`、`SGEVAL_PP_SERVER_WRAP=1`。
- 新文件 `scripts/eval-official/official_media_check.py`：读 `eval_report.py` 的已接受身份（`accepted_attempt_id`）为分母，逐局查 `official/*.mp4` 恰 1、可解码、帧数口径，输出 `OFFICIAL_MEDIA=` 行与持久化 `official-media.jsonl`。
- 测试：`tests/pipeline/eval/test_seat_scripts.py` 加 GL 转码用例（`official/*.mp4` 出现、`episode.mp4` 仍恰一个、渲染失败时 raw 保留）；新文件 `tests/pipeline/eval/test_official_media_check.py`（缺失、重复、失败、帧数不符四反例）。

**S3 Astra 新侧**（`scripts/eval-official/astra_hard_runner.py`、`run_astra.sh`）
- `TraceWriter` 的 route 改 `astra/new`（C1），identity 补 `builder_episode` 与 `key`（C6），演示段与收尾按 C2、C3。
- 录像器：`run_one` 在首次 reset 时建 `recorder.EpisodeRecorder(<ep>/media, meta)`（`media/` 必须新建且为空，禁止 `overwrite=True`），meta 取 `env_client.SeatRunner` 构造 meta 的同款字段并写 `never_degrade=True`；`TracedEnv.reset`／`step` 只 `add_frames`／`add_array`；录像器在 `run_one` 的 `try/finally` 统一 `close(summary)`。`trace.jsonl` 也写进 `media/`（C5）。
- 发布：每局把 `media/` 以 `<key>.a1` 发布到规范身份目录（与 `run_eval_gl.sh` 同布局），使 `video_check.py`、`official_media_check.py` 可直接核；Astra 的 `rollout.mp4` 留在原 `results/` 下不动。
- `run_astra.sh`：只 `source seat_media_lib.sh`（不 source `run_seat.sh`，避免清空 `MAX_STEPS`、覆盖 `cleanup`）；显式设 `BENCH_PY`／`TOOL_PY`。
- 测试 `tests/pipeline/evalx/astra/test_astra_wiring.py`：`media/episode.mp4` 帧数 = 演示帧 + 1 + 步数；`assert_renderable`；source 后 `MAX_STEPS` 与 `trap` 不变。

**S4 SimpleMemVLA 与 MME**
- `smvla_client.py`：`step_chunk` 新增 `on_obs(step, front, wrist, state, terminated, truncated)` 回调，按步保留帧与状态（一步多帧取最后一帧）；`run_episode` 建 `TraceWriter(route="smvla/new", …)`，演示按 C2，每个决策回包的子任务文本（键名以 `smvla_server.py` 实际回包为准，实施时先核）存为当前子目标，`on_obs` 里 `log_step`；strict-cap（`StepCapReached` 或 `session.cap_hit`）按 `timeout` 关闭（C3）。
- `mme_client.py`：在 `run_episode` 内包一层 `session.step` 的钩子拿到完整五元组，`reset_fn` 外包一层记演示；`TraceWriter(route="mme/new")`，`subgoal=None`；`EnvRunnerShim` 返回 `(None, None, None)` 的异常步不 `log_step`；收尾按 C2、C3。
- 测试 `tests/pipeline/eval/test_policy_clients.py`：两路线各 `assert_renderable`；smvla `step` 行数 = 执行步数且子目标非空；mme 子目标全 `None`；strict-cap 局 `status=timeout`。

**S5 PonderPounce 新侧**
- 新文件 `scripts/eval-official/pp_server_wrap.py`：子类化 `ponderpounce.eval.robomme_server.PonderPounceRoboMMEServer`（不改原文件）。覆写 `_fire_s1`：调用父类前取 `_visible_cognition(ep, now)`，维护本局「最近一个已可见且非空的子目标」，父类生成 `ep.chunk` 后把它挂到 chunk 上；覆写 `_dispense`：父类结果加 `"subgoal": <chunk 上挂的子目标> or None`（hold 分支为 `None`）。入口 `run_server(<子类>)`，参数与原 `-m ponderpounce.eval.robomme_server` 相同。
- `scripts/eval-official/pp_client.py`：新增 `pp_subgoal_to_official(text)`：`re.sub(r"at \[(\d+), (\d+)\]", …)` 把每组 `[x, y]`（0～1000）换成 `<round(y*255/1000), round(x*255/1000)>`，结果夹到 0～255；服务端由整数像素正向换算的值往返精确（误差 ≤0.1275 px），非网格值就近取整。`TracedConnection.act` 存 `last_subgoal`；新侧 `trace_step` 增加 `subgoal` 关键字（默认 `None`，R2），oracle 标签改记 `history` 行 `note=oracle_simple_subgoal:<文本>`。新侧 route、演示、收尾、终态按 C1～C3；原侧调用路径不传新参数。
- 测试：`tests/pipeline/evalx/pp/test_pp_protocol_wire.py` 加换算（`at [612, 247]` → `at <63, 156>`；0～255 全量往返精确；多组坐标；越界夹取；`None`）、假服务端回包 `subgoal` 进轨迹、`assert_renderable`；新文件 `tests/pipeline/evalx/pp/test_pp_server_wrap.py` 用假 S1/S2 验证：子目标产生到 `ready_at_ns` 之前，回包仍是旧子目标；chunk 耗尽重复末行时子目标不变；首个子目标前为 `None`。

**主会话**：S0；新增测试文件如需登记 `tests/contract/benchmark_contracts.json` 由主会话改；`CLIENT_REPLAY_EQ` 回放脚本（一次性，`scripts/eval-official/client_replay_eq.py`，合并后跑）；`launch.md`、`result.md`、`records/`。

## 二、子代理分配表

`BASE` 在派发前由主会话记录（S0 提交之后的 HEAD）。

| 子任务 | 目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖 | 合并顺序 | 验收命令与判定行（worktree 内，R8 环境） | 资源 | 共享文件归属 |
|---|---|---|---|---|---|---|---|---|
| S0 | 共享契约与测试助手 | `trace_writer.py`（仅文档串）、`tests/pipeline/evalx/report/trace_contract.py` | — | C1～C7 | 派发前 | 主会话自做：`pytest tests/pipeline/evalx/report -q` | CPU | 主会话 |
| S2a | 重绘工具重构 | `render_official_video.py`、`tests/pipeline/evalx/report/test_sgx_render_official_video.py` | R1 全部、其余 `scripts/eval-official/*` | CLI 向后兼容；新增 `--source`、`source_kind` | 1 | `pytest tests/pipeline/evalx/report -q` passed | CPU ≤5 分钟 | 无 |
| S2b | 席位函数库与官方视频验收 | `seat_media_lib.sh`（新）、`run_seat.sh`、`run_eval_gl.sh`、`official_media_check.py`（新）、`tests/pipeline/eval/test_seat_scripts.py`、`tests/pipeline/eval/test_official_media_check.py`（新） | 同上 | 导出 `render_official_dir`、`transcode_episode_dir`；环境变量 `SGEVAL_OFFICIAL_RENDER`、`SGEVAL_PP_SERVER_WRAP`；调用 S2a 的 `--source raw` | 2 | `pytest tests/pipeline/eval/test_seat_scripts.py tests/pipeline/eval/test_official_media_check.py -q` passed | CPU | `run_seat.sh` 唯一写者 |
| S1 | GroundSG 新侧 | `mmesg_client.py`、`tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py` | 同上 | 新参数 `keep_official`（默认 False） | 3 | `pytest tests/pipeline/evalx/groundsg -q` passed | CPU | 无 |
| S4 | SimpleMemVLA、MME | `smvla_client.py`、`mme_client.py`、`tests/pipeline/eval/test_policy_clients.py` | 同上 | 只读 `trace_writer`、`mmesg_client.trace_location` | 4 | `pytest tests/pipeline/eval/test_policy_clients.py -q` passed | CPU | 无 |
| S5 | PonderPounce 新侧 | `pp_client.py`、`pp_server_wrap.py`（新）、`tests/pipeline/evalx/pp/test_pp_protocol_wire.py`、`tests/pipeline/evalx/pp/test_pp_server_wrap.py`（新） | 同上 + `third_party/PonderPounce/**` | 回包键 `subgoal`；`pp_subgoal_to_official` | 5 | `pytest tests/pipeline/evalx/pp -q` passed（真服务端用例不在 worktree 跑） | CPU | 无 |
| S3 | Astra 新侧 | `astra_hard_runner.py`、`run_astra.sh`、`tests/pipeline/evalx/astra/test_astra_wiring.py` | 同上 | 只 source `seat_media_lib.sh`（S2b 定义；派发时以接口说明为准，合并在 S2b 之后） | 6 | `pytest tests/pipeline/evalx/astra -q` passed | CPU | 无 |
| 运行型 R1～Rn | 按六节分片在 GL 席位启动 `run_eval_gl.sh`／`run_official_hard.sh`／`run_astra.sh` | 无 | 一切代码 | 命令原文照第四节 runbook | 开工后 | 起跑判据 `SEAT_START`／`ROUTE_START` + 首局 `REC_TRANSCODE … result=ok` + 首局 `OFFICIAL_RENDER=` | GL 席位 | 账目归主会话 |

派发前核对：`worktree.baseRef=head`；`git check-ignore -q .claude/worktrees/probe`；`git worktree list` 存档，既有 worktree 一律不动；`git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'` 为空。

## 三、闸门总表

| 闸门 | 命令 | 判定行 |
|---|---|---|
| 核心短测（每次合并后） | `timeout 280s uv run --no-sync python -m pytest -m 'not slow' -q` | passed、`TEST_RESOURCE=PASS`、`TEST_INVENTORY=PASS` |
| 项目闸门 | `ls -1 scripts/*.py`；`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`；`uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | 四入口；零 diff；`UPSTREAM_GUARD=PASS` |
| 原版零改动 | `git diff --quiet <BASE> HEAD -- scripts/eval-official/{official_hard_runner.py,pp_official_runner.py,run_official_hard.sh,pair_seat.sh} third_party` | 退出 0 → `ORIG_FILES_UNCHANGED=PASS` |
| 记录契约 | 各子任务测试里的 `assert_renderable` | 汇总 `TRACE_CONTRACT=PASS routes=6` |
| 客户端回放 | `client_replay_eq.py --base <BASE> --head HEAD` | `CLIENT_REPLAY_EQ=PASS routes=6 mismatches=0` |
| 本机 smoke | 每路线 1 局（新 run 名、新 preflight 目录） | `OFFICIAL_MEDIA=PASS total=1 skip=0 fail=0`、`VIDEO_SAVED=PASS multi_mp4=0` |
| 第一档 | `noise_gate.py gen-regress check --set {v9,xhard0}` | `GEN_REGRESS=` 如实记录 |
| 第二档 | `gate2_compare.py`（新接口 vs 原版合表） | 每模型 `GATE2=INFO`；SimpleMemVLA、MME 记 `GATE2=RECORD_ONLY` |
| 第三档 | `eval_report.py`、`video_check.py`、`official_media_check.py` | 每模型 800 唯一终态、`VIDEO_SAVED=PASS`、`OFFICIAL_MEDIA=PASS total=800 skip=0 fail=0` |

## 四、runbook（主会话）

1. **占位 job**（用户 2026-10-06 授权：「我授权你最多要求10张卡你现在自行启动和kill job那还是我说的必须要4十八小时然后尽可能早占用排队」；这不是开工令）：同时请求（RUNNING + PENDING）≤10 张卡，全部单卡 `--account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:a40:1 --gpu_cmode=shared --cpus-per-task=4 --mem=64G --time=48:00:00 --wrap='sleep infinity'`，到期立即同规格续交。2026-10-06 00:52 起的 10 张：`sgev-hold-00～07` = 63188711～16、63188719、63188720，`sgev-hold-08`、`09` = 63325534、63325535（Astra 两卡 63188721 因 Astra 只跑 smoke 已取消）；清单 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/gl-hold-logs/hold-jobs-sgeval-20261004.txt`。JobID 同时记 `launch.md`，收尾按清单逐个 `scancel`。
2. **第一档（提前）**：沿用 1003 第五节第一档做法，执行副本为 `robomme_benchmark-noise`，检出开工时的 HEAD；`--attempts n --resets 3n --retries 0`；1 个单卡席位。
3. **原版补跑**：用上一轮 GL 执行副本 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-sgeval`（不同步、不改动，起跑前记录其 HEAD）；`run_official_hard.sh` 跑 PonderPounce 分片 1 与 QwenVL 未跑分片（QwenVL 单局墙钟 3600 s，用上一轮 `launch_seat_v2.sh` 体例）。结果写入本轮新 stage，合表时与上一轮原版结果按身份并起来。
4. **改代码**：S0 提交 → 同一消息派 S2a、S2b、S1、S4、S5、S3（`model: "opus"`、`isolation: "worktree"`）→ 按顺序逐个第一次审查、`git merge --no-ff <TIP sha> -F <消息文件>`、第二次审查、push。
5. **按模型分批上 GL**：某模型依赖的子任务全部合入后：本机 smoke 1 局（tmux 前缀 `ovl2-`）→ 在 NFS 新建执行副本 `robomme_benchmark-sgeval2-<批次>`（`git clone --no-hardlinks` + `git submodule update --init`，检出冻结 sha，主 `.venv` 用 `UV_LINK_MODE=copy uv sync --frozen --group eval-client`；三方服务 venv 经 `MME_PY`／`PP_PY`／`SMVLA_PY` 指向上一轮执行副本中的对应 venv，第三方代码未变）→ 各席位链「第二档分片 → 第三档分片」。批次：A = GroundSG（S2a、S2b、S1 后），B = SimpleMemVLA／MME（+S4），C = PonderPounce（+S5）。Astra（S3）合入后只做本机 smoke，不上 GL。
6. **本轮全新目录**：run 名 `sg-eval-gl-<开工日期>-02`；stage、账本、media、trace、日志全部新建，命令逐条写进 `launch.md`，不复用上一轮 stage（防 `resume_skip`）；未知路线即报错退出。起跑后核对每条路线首局确有新 attempt。
7. **监听**：每份日志一个 Monitor，过滤 `EXIT_CODE=|RUN_BLOCKED|INFRA|OFFICIAL_RENDER=FAIL|OFFICIAL_MEDIA=|Traceback|CUDA|svulkan2|EXCLUSIVE|NO RECORD|reset 拒绝`；开工后按 1003 第五节挂「排到卡即唤醒」。
8. **收尾**：各模型 `OFFICIAL_MEDIA` 汇总、成绩表、第二档差异表、视频索引；留档 `docs/validation/sg-eval-gl-<日期>-02/{launch.md,result.md,records/}`；commit、push；按清单逐个 `scancel`。

## 五、风险与盲区

| 项 | 说明 | 处置 |
|---|---|---|
| GroundSG 补存的视频与官方正常路径的差异 | 官方超时（`count > max_steps`）先 break 后 record，补存路径帧数口径不同 | 帧数口径按 `omitted` 字段区分，`official_source` 记来源 |
| PonderPounce 外壳依赖内部方法名 | `_fire_s1`、`_dispense`、`_visible_cognition` 是锁定提交 `723df357` 的私有方法 | 锁定提交不变即稳定；`test_pp_server_wrap.py` 钉死；改不通即停交用户 |
| SimpleMemVLA 回包子任务键名 | 未在本计划内逐字核对 `smvla_server.py` | S4 实施第一步核对，不符先改计划 |
| 跨时间对照 | 第二档新接口与上一轮原版不是同时跑的 | 第二档只出差异报告；留档写明 |
| QwenVL 墙钟 | A40 上每步约 1.5 s，V9 1600 步单局最长约 40 分钟；800 局占卡时长大 | 单局墙钟 3600 s；48 h 到期按 1003「到期与续交」 |
| 原始帧保留占盘 | 重绘失败的局保留 raw | `official_media_check` 列出，修复后统一清理 |
| GL 配额 | 上一轮 9 个 job 长期 PENDING（`AssocGrpGRES`） | 第一档与原版补跑先占先跑；按模型分批减少空等 |
| 第一档锚点早于最终代码 | 第一档在改代码期间跑 | 留档附 `git diff --stat <第一档冻结>..<各批冻结> -- src scripts/parity scripts/injection-dev` 证明生成侧零 diff |
| 本计划判定行 | 全部待实施，没有任何一项已运行 | — |

## 六、预算（开工前一次性批准）

评估每局按 build 与 reset 各 1 次计 2 次 reset；生成每条轨迹 reset 上限 3 次。V9 每模型 800 局 = `3任务×2档×17 + 3任务×1档×16 + 2任务×5档×10 + 2任务×2档×13 + 2任务×2档×12 + 7任务×2档×25 + 2任务×1档×50`（`hard_specs.py::_v9_cells`）。

| 用途 | 乘式 | 轨迹 | reset 上限 |
|---|---|---:|---:|
| GL 第一档首跑 | V9 43 格 × 3 局 + xhard0 16 任务 × 3 局 | 177 | 531 |
| GL 第一档 smoke 与重跑 | 2 + ≤20（两集合共用，V9 优先） | 22 | 66 |
| 本机 smoke（非 Astra） | 5 路线 × 1 局 | 5 | 10 |
| 本机 smoke 修复后重跑 | 5 路线 × ≤2 局 | 10 | 20 |
| 本机 smoke（Astra 新侧，付费） | ≤2 局 | 2 | 4 |
| GL smoke（非 Astra 新侧） | 5 路线 × 1 局 | 5 | 10 |
| GL 第二档新接口 | 5 模型 × 16 任务 × 1 档 × 12 局 | 960 | 1920 |
| GL 第二档原版补跑 | PonderPounce 分片 1 共 96 局 + QwenVL（16 任务 × 1 档 × 12 局 − 已有 39）= 153 局 | 249 | 498 |
| GL 第三档 | 5 模型 × 800 局 | 4000 | 8000 |
| 基础设施重试 | 非 Astra 5 模型 × ≤10 次（整批共享，原版补跑计入所属模型）；Astra 0 | 50 | 100 |
| 到期续跑 | 非 Astra 5 模型 × ≤100 局 | 500 | 1000 |
| **合计** | | **5980** | **12159** |

正常 fail／timeout 不重试；smoke 不进正式分母；账本持久化，重启不重新获得额度。**Astra**：本轮付费局只有本机 smoke ≤2 局（上一轮 2 局花费 0.5149 美元），金额上限待用户定（建议 5 美元，到线即停）。**占位 job**：见第四节第 1 条，已获授权。

## 七、留档与 commit 纪律

- S1～S5 各经 `--no-ff` 合并占一个项目号（`12.<n>`），子代理提交前缀 `sub/<编号>: `；S0、回放脚本、留档由主会话按第 11 条六项 body 提交，含本文件文首与第一部分二节的用户原话。
- 三档留档 `docs/validation/sg-eval-gl-<日期>-02/`：`launch.md` 起跑即写（执行副本 sha、各批冻结 sha、JobID、tmux 会话清单、完整命令）；`result.md` 跑完写（成绩表、第二档差异表、`OFFICIAL_MEDIA` 汇总、结论边界）；`records/` 只归档判定行、差异表、视频索引与一次性脚本逐字副本；不归档 mp4。
- `docs/validation/sg-eval-gl-20261004-01/` 不改；上一轮 NFS 产物到本轮结束前不动（R7）。
