# 1005-eval-video-official-overlay-plan.md — 评估视频对标官方 RolloutRecorder（两阶段）

> 只规划不实施，每个阶段须用户单独说「开工」（`AGENTS.md` 第 2 条）。代码锚点 `857867db`（12.457），工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`。外部锚点：官方 `RoboMME/robomme_policy_learning` HEAD `ecf086c`（与 `third_party/mme-vla` 同一 commit）、`RoboMME/robomme_benchmark` HEAD `016ac1c`、官方网站 `https://robomme.github.io/`。
> 用户原话（2026-10-05）：「调查官方文档中是怎么保存Evalue视频。我们需要和它保存的方式一致。帧数帧率要去一致的而且所有带LanguageReasony的需要把它画出来……参考官方的网站去寻找他们实现的这个代码到底是怎么实现的然后一定要对标完整……先给我一个计划在用户批准之后写入根目录」「官方的代码库你也要找一下是不是有」；裁决：版式「官方代码完整版」、存量「另加离线重绘工具」、位置「仓库根目录」；「计划写在根目录不执行」；「修改该计划第一阶段只做我想要的V9第三档+Oracle转码。第二阶段完成所有模型的视频修改 然后重新跑123阶段」；「第一部份……只说最高最hihlevel的一些特征比如说视频上面要有哪些字」。

# 第一部分（给人看）

## 官方视频长什么样（对齐目标）

官方 `robomme_policy_learning/examples/robomme/utils.py::RolloutRecorder` 产出的每一帧，自上而下是：

1. `Frame: <帧号>`（黑底白字，从 0 计）
2. `Task Goal: <任务目标原文>`
3. `Action: <8 个数，4 位小数>`；初始观测帧写 `Action:None`
4. `State: <8 个数，4 位小数>`
5. 有语言推理的模型多一条 `Subgoal: <子目标原文>`；初始观测帧写 `Subgoal: [initializing...]`；文字里的坐标显示成 `<113 146>`（逗号被官方换行函数去掉）
6. 画面：前视 + 腕部左右拼成 512×256；子目标里的 `<y, x>` 处画**半径 5 的黄色实心点**（只会在左半前视图）；视频演示类任务（VideoUnmask、VideoUnmaskSwap、VideoPlaceButton、VideoPlaceOrder、VideoRepick、MoveCube、InsertPeg、PatternLock、RouteStick）的演示帧画 **10 px 红框**

帧数 = 演示帧 + 1 个初始帧 + 每执行一步一帧；30 fps；`imageio.mimsave` 写 mp4；文件名 `<任务>_ep<局号>_<终态>_<任务目标>_<难度>.mp4`。网站上的视频是裁掉前四条文字只留 Subgoal 条的展示版，用户已选按官方代码完整版对齐。

## 第一阶段：只把本机 V9 第三档 GroundSG+Oracle 的 800 局转成官方版式

- **改什么**：新增一个离线重绘工具 `scripts/eval-official/render_official_video.py`。它不自己画任何东西：直接加载官方 `RolloutRecorder` 类，把每局已有的 `episode.mp4`（解码出前视 / 腕部帧）、`trace.jsonl`（每步子目标、状态、动作、演示帧数、任务目标、终态）按官方 `eval.py` 的顺序喂回去，由官方代码生成上面六项。
- **对哪些数据**：`artifacts/sg-evaluation/sg-eval-gl-20261004-01/local-g3/media/mmesg-ground-sg-oracle/test-hard/new/` 下 16 任务 × 50 局 = 800 局（已全部跑完、转码 ok、trace 齐全）。输出到每局目录 `official/official-rerender__<官方文件名>.mp4`，原 `episode.mp4` 不动。
- **怎么保证一致**：单测用同一组帧分别喂官方类与本工具，逐帧逐位相等；真实一局抽帧目视；全量 800 局末行 `OFFICIAL_RENDER_SUMMARY=PASS total=800 ok=800 fail=0`。纯 CPU，不占显卡、不做 reset。
- **已知差异**：画面像素来自 h264 解码（官方从原始帧直接合成），文字区逐位一致；文件名加 `official-rerender__` 前缀表明是重绘。
- **本轮追加交付（2026-10-05）**：用户原话「/data/hongzefu/robomme_benchmark_MotionJEPANewTask/1005-eval-video-official-overlay-plan.md实现第一阶段的转码转完之后host在一个网站上。host完网站做Playeright测试。」明确执行第一阶段，随后在本机新增独立视频浏览站点，按任务、难度和终态筛选并播放重绘视频；完成真实 Playwright 播放、跳转、筛选与截图核验。沿用已有白名单视频服务，端口起跑前探测，给用户完整域名链接。
- **网站追加要求**：用户随后明确「我只要分task的成功率。」「Task内部就不用再拆了。然后成功率要有百分比和分数。」「然后你的网页按照任务来分视频的栏目，不要堆砌在一个矩目录的列表里，并且所有的任务名字都用中文，啊，都用英文。」顶部表格固定 16 个 Task 行、V9 与 xhard0 两个结果列，每格百分比及成功局数／总局数；不按任务内难度拆分，不加总成功率行。视频改为英文任务名的独立栏目；原始／重绘视频切换继续保留。
- **最终可见列名**：用户再纠正为「V9／xhard0 这里改名为Xhard和原版hard」，页面采用 `Xhard` 与 `原版hard`，内部来源仍为本机 V9 与 xhard0，数据不重算或替换。
- **总体成功率追加**：用户随后明确「你这里还需要一个总合的成功率啊」，此要求覆盖前述不加汇总行的旧口径。保留 16 个 Task 行，在表尾另加一行总体：各列按全部成功局数之和／全部接受终态局数之和计算，显示百分比与分数，不对已四舍五入的 Task 百分比取平均。只改 HTML、浏览器检查和本轮证据，直接复用既有结果与站点。

## 第一阶段子代理分工与整合（简述）

重绘代理只负责离线工具与定向测试，网站代理只负责独立页面、目录构建和浏览器检查脚本；媒体核验与审查代理只读。主会话先审查并整合工具，执行真实一局冒烟，再完成全量重绘；随后构建站点、启动本机会话并执行 Playwright。每次整合核对文件边界与差异，原视频和第二阶段模型链路保持原样。

## 第二阶段：所有模型的评估链路直接产出官方版式，然后重跑第一、二、三档

- **GroundSG Oracle / QwenVL**：两侧本来就在跑官方循环，官方叠字 mp4 每局都生成、只是局末被删——改成保留到每局目录 `official/`。零重画。
- **Astra**：子目标 `<y, x>` 已在 trace 里；它自己写的 `rollout.mp4` 漏了演示帧。给 Astra 新侧接上本仓库录像器录全帧，再用第一阶段的工具出官方版式（黄点 + Subgoal 条都有）。
- **SimpleMemVLA**：有无坐标的 sub-task 文本（现在只在 `events.jsonl`），没有 trace。补一份每步子目标记录，用工具出官方版式：有 Subgoal 条、无黄点。
- **PonderPounce**：Ponder 的子目标现在只在服务端日志里，客户端拿不到；trace 里写的是环境 oracle 标签，不能当它的推理。改服务端把当前子目标随动作回传、客户端换算成官方 `<y, x>` 0～255 写进 trace，再用工具出官方版式。它的 reasoning 文本服务端没保存，本阶段不画。
- **MME-VLA FrameSamp+Modul**（无语言推理）：工具以 `subgoal=None` 出四条文字版式，与官方 π0.5 一致。
- **然后重跑三档**：第一档生成对拍、第二档 xhard0 原版接口对新接口、第三档 V9 正式评估，规模与顺序沿用 `1003-oracle-subgoal-groundsg-eval-plan.md`（第二档每模型 192 局 × 两侧，第三档每模型 800 局，Astra 第二档 32 局 + V9 1 局）。重跑的预算、GL 占位 job、Astra 局数都要在第二阶段开工前重新一次性获批。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1 不改 `src/robomme/`（P2），不改 `scripts/` 顶层四入口（P1）。第一阶段不改 `third_party/*`；第二阶段 PonderPounce 服务端改动按第 24 条走专用分支 + 新 gitlink。
- R2 官方 `RolloutRecorder` 一行不复制、不改写：以 `importlib.util.spec_from_file_location("official_robomme_utils", <repo>/third_party/mme-vla/examples/robomme/utils.py)` 加载后直接调用；机制上保留其产物时也原样不动。
- R3 不改 `run_seat.sh::transcode_episode_dir`、`video_check.py` 判定逻辑、`eval_video_mover.py`；`episode.mp4` 口径不变；官方版式文件一律放每局目录 `official/` 子目录（`video_check` 的 `d.glob("*.mp4")` 与 mover 的 `src.glob("*.mp4")` 都不递归，不触发 `multi_mp4`）。
- R4 第一阶段零 reset、零 GPU；第二阶段 smoke 与三档重跑按 P3 一次性汇总预算另批。
- R5 子代理在 worktree 内只跑定向测试：`UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <定向> -q`，先打印 `robomme_hard.__file__` 确认指向 worktree。

## 一、第一阶段逐文件改动

**A-1 `scripts/eval-official/render_official_video.py`（新）**
- CLI：`render_official_video.py <局目录>… | --root <媒体根> [--label mmesg-ground-sg-oracle] [--ffmpeg <路径>] [--out-subdir official] [--prefix official-rerender__] [--overwrite] [--jobs N]`。
- `load_official(repo_root)`：按 R2 加载，取 `RolloutRecorder`、`TASK_WITH_VIDEO_DEMO`。
- `load_trace(path) -> TraceData`：`header`（`identity.task`、`identity.tier`、`route`）；`demo`（`frames`、`texts[0]`、`states[i]`）；`step` 按 `step` 升序（`subgoal`、`state`、`action`）；`end`（`terminal_reason`、`demo_frames`、`exec_steps`）。`f32_from_record(rec)`：`np.frombuffer(bytes.fromhex(rec["f32hex"]), "<f4")`，`rec["shape"] != [8]` 即 `SystemExit`（`f32hex` 只存前 8 个值，8 维状态 / 动作恰好完整）。
- `decode_mp4(ffmpeg, mp4)`：读 `W×H`，`-f rawvideo -pix_fmt rgb24` 全量解码；断言 512×256；front = `[:, :, :256]`，wrist = `[:, :, 256:]`。
- `feed_official_recorder(rec, front, wrist, trace, task)`：
  ```python
  n_init = trace.demo_frames + 1
  for i in range(n_init):
      rec.record(image=front[i].copy(), wrist_image=wrist[i].copy(), state=trace.init_states[i],
                 is_video_demo=(task in TASK_WITH_VIDEO_DEMO and i < n_init - 1), subgoal=trace.init_subgoal)
  for k, st in enumerate(trace.steps, start=1):
      rec.record(image=front[n_init+k-1].copy(), wrist_image=wrist[n_init+k-1].copy(),
                 state=st.state, action=st.action, subgoal=st.subgoal)
  ```
  `init_subgoal` = `"[initializing...]"`（有子目标的路线）或 `None`（无推理模型，第二阶段用）。帧数不等于 `n_init + len(steps)` 即 `OFFICIAL_RENDER=FAIL reason=frame_count`。
- 文件名 `f"{task}_ep{episode_id}_{success_flag}_{task_goal}_{difficulty}.mp4"`：`episode_id` 新侧取 `mmesg_client.official_episode_id(identity, dir.name)`、原侧取 `identity.source_episode`；`success_flag = end.terminal_reason`；`difficulty = identity.tier`。
- 判定行：每局 `OFFICIAL_RENDER=PASS|FAIL dir= frames= demo= steps= size=<W>x<H> out=`；批量末行 `OFFICIAL_RENDER_SUMMARY=PASS|FAIL total= ok= fail=`；`--jobs` 用进程池，每局独立。

**A-2 `tests/pipeline/evalx/report/test_sgx_render_official_video.py`（新）**
- `test_feed_matches_official_recorder_bitwise`：8×8 彩块帧 6 张（2 演示 + 1 初始 + 3 步），随机 8 维状态 / 动作，子目标含 `<3, 5>`；task 取 `VideoUnmask`（红框）与 `BinFill`（无）；一侧按官方 `eval.py` 顺序直接调 `RolloutRecorder.record`，另一侧调 `feed_official_recorder`；逐帧 `np.array_equal`；打印 `RENDER_PARITY=PASS frames=6 mismatch=0`。
- `test_f32hex_roundtrip_and_shape_guard`。
- `test_end_to_end_with_real_ffmpeg`：真 ffmpeg 编 4 帧 512×256 `episode.mp4` + 假 `trace.jsonl`，跑 `main`，`ffprobe` 数帧 = 4、`official/official-rerender__VideoUnmask_ep3a1_success_<goal>_xhard0.mp4` 存在；缺 ffmpeg 则 skip。

**A-3 主会话**：真实一局 `VideoPlaceButton_xhard2_19002401.a1`（1082 演示 + 1 + 162 步 = 1245 帧）重绘并抽帧目视；tmux `ovl-rerender-g3` 全量 800 局（Monitor 过滤 `OFFICIAL_RENDER_SUMMARY|FAIL|Traceback|EXIT_CODE=`）；`docs/validation/sg-eval-gl-20261004-01/result.md` 追加「存量重绘」小节、`records/rerender-summary.jsonl`；`docs/1002-pending-decisions.md` 追加 P 组（第二阶段各项）。

## 二、第二阶段逐文件改动

**B-1 GroundSG 两侧保留官方 mp4**：`scripts/eval-official/mmesg_client.py` 新增 `OFFICIAL_VIDEO_SUBDIR = "official"`、`keep_official_videos(video_dir, dst) -> list[str]`（`glob("*.mp4")` → `shutil.move`，同名加 `.dupN`）；`run_official_episode` 的 `finally` 在 `rmtree(video_dir)` 前调用，目标 `archive_dir / "official"`，返回字典加 `official_videos`；`official_hard_runner.py` 局末同样处理到 `ep_dir / "official"`。Oracle 与 QwenVL 都保留。测试：`tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py`、`test_groundsg_orig_runner.py` 各加断言（`official/*.mp4` 恰 1 个、`official-video/` 不存在）。
**B-2 Astra 录全帧**：`scripts/eval-official/astra_hard_runner.py::TracedEnv.reset/step` 接 `recorder.EpisodeRecorder`（`add_frames("front"/"wrist", …, tag="reset"/"step<k>")`、`add_array`），局末 `close`；复用 `run_seat.sh::transcode_episode_dir` 的口径由 `run_astra.sh` 调转码；随后对局目录跑 A-1 工具。测试：`tests/pipeline/evalx/astra/test_astra_wiring.py` 加「`episode.mp4` 帧数 = 演示帧 + 1 + 步数」。
**B-3 SimpleMemVLA 子目标进轨迹**：`scripts/eval-official/smvla_client.py` 在每局写 `trace.jsonl`（复用 `trace_writer.TraceWriter`，`log_demo` 用 reset 帧，`log_step(subgoal=<当前 decision 的 subtask>)`，chunk 内 16 步共享同一文本），任务目标取 reset 的 `task_goal`；A-1 工具按 `route` 识别无坐标也照常出 Subgoal 条（官方正则匹配不到点就不画）。测试：`tests/pipeline/eval/test_policy_clients.py` 加 trace 行数断言。
**B-4 PonderPounce 子目标回传**：`third_party/PonderPounce` 专用分支：`ponderpounce/eval/robomme_server.py::_dispense` 回包加 `"subgoal": ep.active_subgoal`（`at [x, y]` 0～1000）；主仓库 `scripts/eval-official/pp_client.py::act`/`pp_official_runner.py` 读回包 `subgoal`，`pp_subgoal_to_official(text)`：`[x, y]` → `<round(y*255/1000), round(x*255/1000)>`，写进 `trace_step(... subgoal=...)` 取代环境 oracle 标签；gitlink 更新。测试：`tests/pipeline/evalx/pp/test_pp_protocol_wire.py` 加换算与回包断言。
**B-5 MME-VLA**：无代码改动；A-1 工具对 `mme` 路线以 `subgoal=None` 出四条版式（需要 B-3 同款最小 trace：`log_demo` + `log_step(subgoal=None)`，`mme_client.py` 同步补）。
**B-6 重跑三档**：沿用 `1003-oracle-subgoal-groundsg-eval-plan.md` 第二部分 runbook（`preflight_card.sh` 预检 → GL 占位 job → `run_eval_gl.sh` / `run_official_hard.sh` / `run_astra.sh`），每局目录多出 `official/` 文件；`eval_manifest`、`gate2_compare`、`video_check` 不变；留档新建 `docs/validation/sg-eval-gl-<日期>-02/`。规模：第一档 V9 129 局 + xhard0 48 局 × 旧新两遍；第二档 GroundSG Oracle / QwenVL / PonderPounce 各 192 局 × 两侧、Astra 16 局 × 两侧；第三档 Oracle / QwenVL / PonderPounce 各 800 局、Astra 1 局。**开工前须重新一次性获批**：reset / 轨迹预算（P3）、GL 占位 job 数量（第 8 条，上轮 9 个）、Astra 局数（用户 2026-10-04 明令逐项审批）。

## 三、子代理分配表

| 阶段 | 子任务 | 目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖 | 合并顺序 | 验收命令与判定行（worktree 内，R5 环境） | 资源 | 共享文件归属 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | S2 | 离线重绘工具与测试 | `scripts/eval-official/render_official_video.py`、`tests/pipeline/evalx/report/test_sgx_render_official_video.py` | `src/`、`third_party/`、其余 `scripts/eval-official/*` | 只读 `mmesg_client.official_episode_id`、`trace_writer.array_record` 格式；按 R2 加载官方 utils | 1 | `… pytest tests/pipeline/evalx/report/test_sgx_render_official_video.py -q` 末行 passed；stdout 含 `RENDER_PARITY=PASS frames=6 mismatch=0` | CPU ≤3 分钟 | 无 |
| 1 | S6 | 独立视频浏览站点与 Playwright 检查 | `scripts/injection-dev/site/official_overlay_site.py`、`scripts/injection-dev/site/official_overlay.html`、`scripts/injection-dev/site/official_overlay_browser_check.py`；在 `artifacts/sg-evaluation/sg-eval-gl-20261004-01/official-overlay/` 生成本站目录与检查产物 | `src/`、`third_party/`、现有站点页面与服务器、其余评估代码 | 复用 `site_server.py` 白名单与 Range；仅展示本机第三档 Oracle 重绘视频，依赖全量重绘；主会话启动服务器与执行浏览器检查 | 3 | `OFFICIAL_SITE=PASS episodes=800`；`OFFICIAL_BROWSER=PASS`，截图与 JSON 报告落本站产物目录 | CPU，独立空闲端口优先 8083，tmux `ovl-site-g3-8083`，零 GPU/reset | 三个源码文件归 S6；运行、留档、共享目录归主会话 |
| 1 | 主会话 | 真实一局 + 800 局全量重绘、留档、待做清单、登记新增测试契约 | 本计划；`docs/validation/sg-eval-gl-20261004-01/launch.md`、`result.md`、`records/`；`docs/1002-pending-decisions.md`；`tests/contract/benchmark_contracts.json` | `src/`、`third_party/`、其他在途文件 | 依赖 S2 合入；测试总表按 `tests/static/test_inventory.py::check_inventory` 登记新增源码与真实验证边界 | 2 | `OFFICIAL_RENDER=PASS … frames=1245`；`OFFICIAL_RENDER_SUMMARY=PASS total=800 ok=800 fail=0`；核心短测含 `TEST_INVENTORY=PASS` | CPU，tmux `ovl-rerender-g3` | 测试总表、留档与版本提交均由主会话负责 |
| 2 | S1 | GroundSG 保留官方 mp4 | `mmesg_client.py`、`official_hard_runner.py`、`video_check.py`（仅文档串）、两份 groundsg 测试 | `src/`、`third_party/`、`run_seat.sh` | 导出 `keep_official_videos`、`OFFICIAL_VIDEO_SUBDIR` | 1 | `… pytest tests/pipeline/evalx/groundsg -q` passed | CPU | 无 |
| 2 | S3 | Astra 录全帧 + 转码 | `astra_hard_runner.py`、`run_astra.sh`、`tests/pipeline/evalx/astra/test_astra_wiring.py` | 同上 + S1 集合 | 只读 `recorder.EpisodeRecorder` 接口 | 2 | `… pytest tests/pipeline/evalx/astra -q` passed | CPU | 无 |
| 2 | S4 | SimpleMemVLA / MME 最小 trace | `smvla_client.py`、`mme_client.py`、`tests/pipeline/eval/test_policy_clients.py` | 同上 | 只读 `trace_writer.TraceWriter` | 3 | `… pytest tests/pipeline/eval/test_policy_clients.py -q` passed | CPU | 无 |
| 2 | S5 | PonderPounce 子目标回传与换算 | `pp_client.py`、`pp_official_runner.py`、`tests/pipeline/evalx/pp/test_pp_protocol_wire.py`；`third_party/PonderPounce` 专用分支（服务端一处） | `src/`、其他 third_party | 回包键 `subgoal`；`pp_subgoal_to_official` | 4 | `… pytest tests/pipeline/evalx/pp -q` passed | CPU | gitlink 归主会话 |
| 2 | 主会话 | 三档重跑（运行型子代理可按 `CLAUDE.md` 列入另批的分配表）、留档 | `docs/validation/sg-eval-gl-<日期>-02/` | — | 依赖 S1～S5 合入 | 5 | 沿用 1003 计划判定行 + 每模型 `OFFICIAL_RENDER_SUMMARY=PASS` | GL 占位 job、本机两卡 | — |

S6 追加范围仍限上述三个文件：目录构建和浏览器检查增加 `--v9-results`、`--xhard0-results`，独立读取本机 Oracle 同一新接口的正式结果。V9 为 `local-g3/stage-oracle-00/s90/mmesg-ground-sg-oracle/results.jsonl`；xhard0 为 `local-g2/gate2-oracle/new-merged.results.jsonl`（已含接受的补跑），即 `16 任务 × 1 档 xhard0 × 12 局 = 192 局`。每 Task 成功率定义为 `100 × task_success=true 的终态局数 / 全部接受终态局数`；核对唯一身份、每任务分母、策略、数据集、status 与成功字段，不把基础设施重试算成额外评估。来源指纹写私有记录；公开表只含 Task、计数与比率。网站更新另跑真实 Playwright，旧截图与旧报告保留在第一版检查目录。

派发前核对：`worktree.baseRef=head`（已核）、`git check-ignore -q .claude/worktrees/probe`（已核）、现有 worktree `.claude/worktrees/motionjepa-ckpt-branch-check-ffae44` 不动、主检出 clean。

## 四、闸门总表

| 阶段 | 闸门 | 命令 | 判定行 |
|---|---|---|---|
| 1 | 重绘逐位 | S2 单测 | `RENDER_PARITY=PASS frames=6 mismatch=0` |
| 1 | 真实一局 | `uv run --no-sync python scripts/eval-official/render_official_video.py artifacts/sg-evaluation/sg-eval-gl-20261004-01/local-g3/media/mmesg-ground-sg-oracle/test-hard/new/VideoPlaceButton_xhard2_19002401.a1` | `OFFICIAL_RENDER=PASS dir=VideoPlaceButton_xhard2_19002401.a1 frames=1245 demo=1082 steps=162 size=512x512`（506 经 imageio `macro_block_size=16` 缩放为 512，以实测为准）+ 抽帧目视记录 |
| 1 | 全量 | `… render_official_video.py --root artifacts/sg-evaluation/sg-eval-gl-20261004-01/local-g3/media --label mmesg-ground-sg-oracle --jobs 16` | `OFFICIAL_RENDER_SUMMARY=PASS total=800 ok=800 fail=0` |
| 1、2 | 核心短测 | `timeout 280s uv run --no-sync python -m pytest -m 'not slow' -q` | 末行 passed、`TEST_RESOURCE=` |
| 1、2 | 项目闸门 | `ls -1 scripts/*.py`；`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`；`uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | 四入口；零 diff；`UPSTREAM_GUARD=PASS` |
| 2 | 每模型 smoke | `preflight_card.sh <卡> <路线>` 各 1 局 | `OFFICIAL_VIDEO_KEPT=PASS side= files=1 frames= size=`（GroundSG）／`OFFICIAL_RENDER=PASS`（其余）+ `VIDEO_SAVED=PASS … multi_mp4=0` |
| 2 | 三档 | 1003 计划第二部分闸门表 | `GEN_REGRESS=`、`GATE2_*`、第三档成绩表 + `OFFICIAL_RENDER_SUMMARY=PASS` |

## 五、runbook

**第一阶段**：用户「开工」→ 主检出 clean、`BASE` 记录 → 派 S2（opus、worktree）→ 合并前审查（sonnet）→ `--no-ff` 合并 → 核心短测 → push → 真实一局重绘 + `ffmpeg tile=4x1` 抽帧 `Read` 目视 → tmux `ovl-rerender-g3` 全量 800 局 + Monitor → 留档、待做清单 → commit `12.45x` → push → 清理 S2 worktree。
**第二阶段**：用户再次「开工」并一次性批预算 → 同一消息派 S1、S3、S4、S5 → 逐个审查合并 → 每模型本机 smoke 1 局 → 按 1003 计划 runbook 重跑三档（GL 占位 job 先占、本机两卡并行）→ 留档 `docs/validation/sg-eval-gl-<日期>-02/`。

## 六、风险与盲区

| 项 | 说明 | 处置 |
|---|---|---|
| imageio 缩放 | 506 px 高不是 16 的倍数，`imageio.mimsave` 缩放到 512 并打警告 | 官方行为，原样；判定行记实测尺寸 |
| 重绘像素 | h264 解码帧 ≠ 官方原始帧，文字区逐位同 | 前缀 `official-rerender__`，留档写明 |
| 动作精度 | trace 动作 dtype `<f8`，经 float32 再 `.4f` 与官方 `.4f` 第 4 位可能差 1 | 盲区记录 |
| 超时局帧数 | 官方 `count > max_steps` 先 break 后 record，少最后一帧；`episode.mp4` 不少 | 不修，留档 |
| PonderPounce reasoning | 服务端未保存，第二阶段不画 | 待用户另定 |
| Astra 局数 | 用户 2026-10-04 明令逐项审批，第二阶段重跑前再批 | 不预设 |
| GL 存量 | Turbo 上 Oracle 800 局未列入第一阶段 | 需要时另起纯 CPU 作业或本机挂 NFS 跑 |

## 七、留档与 commit 纪律

第一阶段：S2 `--no-ff` 合并一个项目号，收尾留档一个；第二阶段 S1～S5 各一个，三档重跑按 1003 计划留档体例。body 按第 11 条六项，含文首用户原话。不归档 mp4。

## 八、第一阶段实施前核验与必要修正（2026-10-05）

本轮只实施第一阶段和用户追加的视频站点、Playwright。Codex 按 `AGENTS.md` 第 26 条使用隔离 worktree 交付文件，子代理不提交；主会话审查、逐文件整合后提交，不执行 Claude 专属的模型档位和子代理合并提交机制。主检出已有 `third_party/SimpleMemVLA` 在途修改，既不提交也不清理；正式重绘从本轮提交建立干净运行 worktree，以 `--official-root` 只读加载主检出锁定的官方代码，媒体仍写本轮已批准的本机目录。

预检确认 `16 任务 × 1 个 V9 正式评估集合 × 每任务 50 局 = 800 局`，与本机 manifest 和 results 身份全集一致，总帧 848318、执行步 600820，最长 2616 帧。`demo.frames` 已包含初始帧，等于 `end.demo_frames + 1`。194 局 `end.status=timeout`、`terminal_reason=error`，原结果的 `success_flag` 同样是 `error`；这些局恰执行 1600 步，与 `max_steps` 相等，保留全部已有帧，文件名沿用 `error`，网站按 `timeout` 展示。

原动作在 `arrays.npz` 的 `exec_action__<五位编号>` 中保留 float64，所有 600820 步索引齐全。真实反例 `VideoPlaceButton_xhard1_17000000.a1` 第 233 步：`0.8404500172406898` 应显示 `0.8405`，转 float32 后会显示 `0.8404`。因此优先读取原动作，逐步核对 dtype、shape 和 trace 的 sha256，并把 NPZ 指纹记入来源记录；不能用 float32 近似声称原动作文字逐位一致。

17 局加前缀后的完整官方文件名为 256～257 字节，超过 255 字节上限：仅超限时按 UTF-8 边界截短并追加摘要，完整原名和目标文本写入每局来源记录。官方 Task Goal 条高度随文本变化，输出尺寸允许实测的 `512×512`、`512×528`、`512×560`，不强制统一裁切。既有 `episode.mp4`、trace、NPZ 与第二阶段模型链路均不改动。
