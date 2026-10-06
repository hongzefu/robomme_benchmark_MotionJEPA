# 1005-eval-video-official-overlay-plan.md — 评估视频对标官方 RolloutRecorder（本轮只做 GroundSG+Oracle）

> **权威性与边界**：本文件是计划，只规划不实施；每一步须用户单独说「开工」（`AGENTS.md` 第 2 条）。代码锚点 commit `c10f985c`（12.456），工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`；commit 编号接续 `12.457`。外部锚点：官方策略仓库 `RoboMME/robomme_policy_learning` HEAD `ecf086c`（2026-04-08，与本仓库 `third_party/mme-vla` 子模块同一 commit，`examples/robomme/utils.py` 自 `d1a6c90` 起未改过）；官方 benchmark 仓库 `RoboMME/robomme_benchmark` HEAD `016ac1c`；官方网站 `https://robomme.github.io/`（视频 `video/sim/<suite>/<task>/ep<N>_<model>.mp4`）。
> **落位**：获批后本文件按用户 2026-10-05 原话「在用户批准之后写入根目录」逐字复制到仓库根 `1005-eval-video-official-overlay-plan.md`（与 `AGENTS.md`「覆盖第 2 条」2026-10-02 起计划放 `docs/plans/` 的口径冲突，以用户本次指令为准；根目录现已有 `1003-*.md` 四份先例）。

# 第一部分（给人看）

## 一、总览

**一句话方案**：GroundSG+Oracle 两侧（原侧 / 新侧）都已经在跑官方的评估循环，官方 `RolloutRecorder` 每局都会把「Frame / Task Goal / Action / State / Subgoal 五条黑底白字 + 黄点 + 演示帧红框」的叠字 mp4 写出来，只是我们在局末 `shutil.rmtree` 删掉了它。本轮改成**原样保留并随每局目录发布**（`<局目录>/official/<官方文件名>.mp4`），这是「与官方一致」的最强保证——帧数、帧率、版式、字体、坐标画法全部由官方代码自己产出，我们一个像素都不重画。对已经跑完、官方 mp4 已删的 `sg-eval-gl-20261004-01` 存量批次，另写一个**离线重绘工具**，直接 `import` 官方 `RolloutRecorder` 类，用 `episode.mp4` 解码帧 + `trace.jsonl` 里的子目标 / 状态 / 动作重新喂一遍，输出同名文件。

**已定口径**（用户 2026-10-05 AskUserQuestion 裁决，原话逐字）：
1. 版式：「官方代码完整版」——所有帧叠 Frame / Task Goal / Action / State 四条，有子目标的再加 Subgoal 条（§二）。
2. 范围：「今天只改groundsg oracle 其他的记录待做后期再改」——QwenVL、Astra、SimpleMemVLA、PonderPounce 只记入 §六待做清单，本轮不改（用户同时勾选了四项「推荐」，以自由文本为准）。
3. 存量视频：「另加离线重绘工具」（§三）。
4. 计划位置：「仓库根目录」。
5. 用户最初指令原话：「调查官方文档中是怎么保存Evalue视频。我们需要和它保存的方式一致。帧数帧率要去一致的而且所有带LanguageReasony的需要把它画出来。就是sgo需要画出来所有有LanguageReasoning的需要有黑边然后用黄色点标出reasoning所带的这个位置然后还有subgo的这个文字的说明参考官方的网站去寻找他们实现的这个代码到底是怎么实现的然后一定要对标完整然后你告诉我你现在需要改哪些的代码就是这些模型里面哪些带有languagereasoning的哪些需要标注说清楚要告诉我怎么改。先给我一个计划在用户批准之后写入根目录」；追加「官方的代码库你也要找一下是不是有」。

## 二、官方到底怎么存评估视频（调查结论，代码级）

**层 1：官方代码 = `RolloutRecorder`，一帧一步、30 fps、front+wrist 横拼后往上叠文字区。** 文件 `third_party/mme-vla/examples/robomme/utils.py`（= 官方 `robomme_policy_learning/examples/robomme/utils.py`，逐字节同一 commit）：

```python
class RolloutRecorder:
    def __init__(self, save_dir, task_goal, fps: int = 30): ...
    def _extract_points(self, subgoal):            # 正则 r'<(\d+), (\d+)>'，逗号后恰一个空格
    def record(self, image, wrist_image, state, action=None, is_video_demo=False, subgoal=None):
        concat_image = np.concatenate([image, wrist_image], axis=1)          # 512×256
        if is_video_demo:  # 演示帧红框
            concat_image = cv2.rectangle(concat_image, (0, 0), (w, h), (255, 0, 0), 10)
        frame_text_area  = self.add_text_area("Frame: " + str(len(self.total_images)), ...)
        goal_text_area   = self.add_text_area("Task Goal: " + self.task_goal, ...)
        if subgoal is not None:
            subgoal_text_area = self.add_text_area("Subgoal: " + subgoal, ...)
            for point in self._extract_points(subgoal):
                concat_image = cv2.circle(concat_image, point[::-1], 5, (255, 255, 0), -1)   # 黄点：半径 5 实心
            concat_image = np.concatenate([subgoal_text_area, concat_image], axis=0)
        state_text_area  = self.add_text_area("State: " + ','.join(f"{i:.4f}" for i in state), ...)
        action_text_area = self.add_text_area('Action: ' + ','.join(f"{i:.4f}" for i in action) if action is not None else "Action:None", ...)
        concat_image = np.concatenate([frame_text_area, goal_text_area, action_text_area, state_text_area, concat_image], axis=0)
    def add_text_area(self, text, shape):   # FONT_HERSHEY_SIMPLEX 0.5 粗 1 白字；按词换行（先 text.replace(',', ' ')）；
                                             # 行高 20，区高 max(50, 行数*20+10)，首行基线 y=15，左边距 10
    def save_video(self, filename):          # imageio.mimsave(path, self.total_images, fps=self.fps)
```

- 自上而下的顺序是 **Frame → Task Goal → Action → State → Subgoal → 画面**；无子目标模型没有 Subgoal 条（4×50 + 256 = 456 px 高），GroundSG 为 506 px 高（宽 512）。`imageio.mimsave` 默认 `macro_block_size=16`，456 / 506 不是 16 的倍数，imageio-ffmpeg 会打警告并缩放到 464 / 512——这是官方产物的真实尺寸，smoke 时实测记录（§四 判定行 `OFFICIAL_VIDEO_KEPT`）。
- **坐标约定**：字符串 `<y, x>`，先行后列、基于 256×256 front 图、0～255；画点时 `point[::-1]` 变成 cv2 的 `(x, y)`。黄点只会落在左半（front）。本仓库 Oracle 的 trace 实测 `'pick up the cube at <110, 148>'`，环境侧生成在 `src/robomme/robomme_env/utils/segmentation_utils.py::process_segmentation`（`f"<{center_y}, {center_x}>"`）。
- **文字里坐标没有逗号**：`add_text_area` 先 `text.replace(',', ' ')` 再按词换行，所以画面上显示 `<113 146>`——官方网站视频里的「`<71 86>`」正是这样来的，不是另一套格式。
- **帧数 / 帧率**（`examples/robomme/eval.py::EpisodeEvaluator`）：`init_episode` 把 `pre_traj` 的每一帧都 `record`（`is_video_demo = env_id in TASK_WITH_VIDEO_DEMO and i < len-1`，子目标写 `"[initializing...]"`，action 为 `None`）；之后每执行一步 `record` 一帧（子目标 = 产出该动作块时的子目标，约每 16 步换一次）；`fps=30`。`TASK_WITH_VIDEO_DEMO = [VideoUnmask, VideoUnmaskSwap, VideoPlaceButton, VideoPlaceOrder, VideoRepick, MoveCube, InsertPeg, PatternLock, RouteStick]`。文件名 `f"{env_id}_ep{episode_id}_{success_flag}_{task_goal}_{difficulty}.mp4"`，目录 `<save_dir>/videos/`。
- ⚠ 官方循环 `epstate.count > max_steps` 时先 `break` 再 `record`，所以**超时局官方少录最后一帧**；我们的 `episode.mp4` 口径是「演示帧 + 1 + 执行步」每步都录。本轮保留官方文件原样，不去「修」这一帧（§七盲区 1）。

**层 2：官方 benchmark 仓库的 `scripts/evaluation.py::VideoRecorder` 是不叠字的简版**（front+wrist 横拼、演示帧红框 10 px、`imageio.mimsave(fps=30)`），本仓库 `scripts/evaluation.py` 与之逐字节相同；挑战赛 `challenge_interface/scripts/phase1_eval.py` 同理。它们都没有 Subgoal / 黄点。

**层 3：官方网站的 mp4 是裁过的展示版**，不是上面任一代码的直接产物：实测 `ep1_pi05.mp4` 512×260、`ep1_groundsg_qwenvl.mp4` 512×320（只留一条约 60 px 的 Subgoal 黑边，Frame / Goal / Action / State 四条被裁掉），30 fps、h264 yuv420p；黄点中心实测 (x=146, y≈113) 对应字幕 `<113 146>`，与层 1 的 `point[::-1]` 一致；VideoUnmask 演示段红框实测 6 px（`cv2.rectangle` 粗 10 画在边界上只露一半）。用户已选层 1「完整版」，网站版不再对标。

**层 4：本仓库现状。** 交付的 `episode.mp4` 由 `scripts/eval-official/run_seat.sh::transcode_episode_dir` 从无损原始帧拼出：512×256、30 fps、帧数 = 演示帧 + 1 + 执行步（`video_check.py --frames-rule demo+exec --frame-offset 1`，上一轮 9 条路线 `VIDEO_SAVED=PASS frame_mismatch=0`），**不画红框、不叠字、不画点**。而 GroundSG 两侧跑的就是官方 `eval_each_episode`，官方叠字 mp4 每局都生成在 `scratch/official-video/`，随后被删：新侧 `scripts/eval-official/mmesg_client.py::run_official_episode` 的 `finally` 里 `shutil.rmtree(video_dir, ignore_errors=True)  # 官方叠字 mp4 不交付`；原侧 `scripts/eval-official/official_hard_runner.py` 第 302 行 `video_dir = ep_dir / "official-video"`、局末同样 `rmtree`。

## 三、方案：保留官方文件 + 存量离线重绘

**机制 A（今后的评估）：不删官方 mp4，搬进局目录 `official/` 子目录。**
- 新侧：`run_official_episode` 的 `finally` 改为——若 `ctx["variant"]` 在 `OFFICIAL_VIDEO_KEEP_VARIANTS = ("ground-sg-oracle",)` 且 `archive_dir` 非空，则把 `video_dir/*.mp4` 逐个 `shutil.move` 到 `archive_dir / "official" /`（`archive_dir` = 轨迹目录 = 录像器输出目录，`trace.jsonl`、`arrays.npz` 已在同一目录，随 `publish_dir` 原子发布），然后照旧 `rmtree(video_dir)`。原侧 `official_hard_runner.py` 的 `rmtree(video_dir)` 前同样搬到 `ep_dir / "official"`。
- 为什么放子目录：`video_check.py` 的「恰有一个 `*.mp4`」用 `d.glob("*.mp4")`、`eval_video_mover.py` 的 `multi_mp4` 跳过用 `src.glob("*.mp4")`，都不递归；`raw_files` 的 rglob 只匹配 `*.raw *.mkv *.png …` 与 `.spool`。所以 `official/x.mp4` 不触发 `multi_mp4`、不被当残留原始帧、随整目录搬运。
- 门控在 Oracle 变体：QwenVL 走同一段代码，但按用户口径本轮不改其交付物；以后放开只需把变体名加进元组（§六 P-1）。
- 返回字典新增 `official_video`（相对局目录的路径或 `None`），进 `summary.json`；`video_check.py` 不改判定逻辑，只在文档串写明 `official/` 子目录不计入 mp4 计数。

**机制 B（存量批次）：离线重绘工具 `scripts/eval-official/render_official_video.py`。**
- 输入一个局目录（新侧：`episode.mp4` + `trace.jsonl` [+ `meta.json`]；原侧：`episode.mp4` + `trace.jsonl`）；输出 `<局目录>/official/<官方文件名>.mp4`，末行 `OFFICIAL_RENDER=PASS dir=<名> frames=<n> demo=<d> steps=<k> size=<W>x<H>`。
- 做法：`ffmpeg -f rawvideo -pix_fmt rgb24` 解码 `episode.mp4` 为 (n,256,512,3)，切成 front / wrist；从 `trace.jsonl` 取 `header.identity`（task、tier）、`demo` 行（`frames`=演示帧数、`texts[0]`=task goal、`states[i].f32hex`=8 维状态）、`step` 行（`subgoal`、`state.f32hex`、`action.f32hex`）、`end.terminal_reason`（= 官方 `success_flag`）；**用 `importlib` 按路径加载 `third_party/mme-vla/examples/robomme/utils.py`，直接实例化官方 `RolloutRecorder`**，按 `eval.py` 的顺序逐帧 `record`（前 `demo+1` 帧 `is_video_demo = task in TASK_WITH_VIDEO_DEMO and i < demo`、`subgoal="[initializing...]"`、`action=None`；之后第 k 步 `subgoal=step_k.subgoal`、`action=step_k.action`），最后 `save_video(官方文件名)`。文字、黄点、红框、换行、`imageio.mimsave` 全是官方代码在跑，本工具只负责「把数据喂回去」。
- `f32hex` 是 `array_record` 为人读保存的「展平前 8 个值的 float32 hex」；状态 `pack_state` 本来就是 8 维 float32（精确），动作 8 维（trace 里 dtype `<f8`，经 float32 再 `.4f` 与官方直接 `.4f` 在第 4 位小数可能偶有 1 的差，§七盲区 2）。形状不是 `[8]` 即报错退出，不猜。
- 画面来源是 h264 有损解码帧，与官方「从原始帧直接合成」在像素上有压缩差；文字区逐位相同。工具输出的 mp4 标 `official-rerender` 前缀以示区别（文件名 `official-rerender__<官方文件名>.mp4`），不冒充原生产物。
- 存量范围：`docs/validation/sg-eval-gl-20261004-01/records/video-index.tsv` 里 Oracle 行（本机 `local-g2`/`local-g3` 与 GL `sgeval-20261004` 下 `mmesg-ground-sg-oracle` 目录）；批量入口 `--root <媒体根> --label mmesg-ground-sg-oracle`，逐局打印判定行，汇总 `OFFICIAL_RENDER_SUMMARY=PASS|FAIL total=<n> ok=<n> fail=<n>`。GL 侧那 1.1 GB 存量在 Turbo 上，重绘产物同样原地落 `official/`（第 14 条：比较在本机、产物不下载）。

**改动一览**

| 文件 | 锚点 | 改什么 | 关闭态 | 开启态 |
|---|---|---|---|---|
| `scripts/eval-official/mmesg_client.py` | `run_official_episode` finally；新增常量 `OFFICIAL_VIDEO_KEEP_VARIANTS`；新增 `keep_official_videos(video_dir, dst)` | 删前先搬 `*.mp4` 到 `archive_dir/official/`；返回值加 `official_video` | 变体不在元组：行为同现在（删） | Oracle：局目录多一个 `official/*.mp4` |
| `scripts/eval-official/official_hard_runner.py` | 局末 `shutil.rmtree(video_dir)` 前 | 调同一个 `mmesg.keep_official_videos(video_dir, ep_dir / "official")` | 同上 | 同上 |
| `scripts/eval-official/render_official_video.py`（新） | `main` / `load_trace` / `decode_mp4` / `feed_official_recorder` | 存量重绘 | — | — |
| `scripts/eval-official/video_check.py` | 模块文档串第 2 条 | 注明 `official/` 子目录不计 | — | — |
| `tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py` | `test_unknown_is_error_and_does_not_stop_seat` 旁新增 `test_official_video_kept_for_oracle_only` | 断言 Oracle 局目录 `official/*.mp4` 恰 1 个、QwenVL 为 0、`official-video/` 不存在 | — | — |
| `tests/pipeline/evalx/groundsg/test_groundsg_orig_runner.py` | 新增同类断言 | 原侧 `official/` | — | — |
| `tests/pipeline/evalx/report/test_sgx_render_official_video.py`（新） | 三个测试（§四） | 工具单测 | — | — |
| `docs/validation/sg-eval-gl-20261004-01/result.md` | 末尾「存量重绘」小节 | 记 `OFFICIAL_RENDER_SUMMARY` 行与目录 | — | — |
| `docs/1002-pending-decisions.md` | 新增 P 组（P-1～P-4） | 其余四模型待做 | — | — |

不改 `src/robomme/`（P2 零 diff），不改 `third_party/*`（gitlink 不动），不改 `run_seat.sh` 转码段（`episode.mp4` 维持现口径，`video_check` 判定不变）。

## 四、验收

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| 官方 mp4 被保留且只对 Oracle | 核心短测里的新测试（假官方循环、8 px 小帧、真 imageio） | 搬运与门控正确、`official-video/` 仍清理 | `pytest … -q` 末行 passed |
| 重绘工具与官方类逐位一致 | 单测：同一组合成帧 / 状态 / 动作 / 子目标，分别喂官方 `RolloutRecorder` 与工具的 `feed_official_recorder`，`np.array_equal` 逐帧比 `total_images` | 工具没有自己「重画」任何东西 | `RENDER_PARITY=PASS frames=<n> mismatch=0` |
| 重绘工具端到端 | 单测：构造含 `demo` / `step` / `end` 行的假 trace + 真 ffmpeg 编的 4 帧 `episode.mp4`，跑 `main`，`ffprobe` 数帧与读尺寸 | 解码、切分、喂入、保存全链通 | `OFFICIAL_RENDER=PASS … frames=4` |
| 真实存量一局 | `uv run --no-sync python scripts/eval-official/render_official_video.py artifacts/sg-evaluation/sg-eval-gl-20261004-01/local-g3/media/mmesg-ground-sg-oracle/test-hard/new/VideoPlaceButton_xhard2_19002401.a1`（1082 演示 + 1 + 162 步 = 1245 帧，子目标 2 段） | 真数据格式吃得下；抽 4 帧拼图目视（演示段红框、`[initializing...]`、黄点在 `<y, x>`、五条文字区顺序） | `OFFICIAL_RENDER=PASS frames=1245` + 目视记录 |
| 机制 A 真跑一局（smoke） | 本机空闲卡，照 `preflight_card.sh` 的 `mmesg-oracle-new-hard0` 与 `mmesg-oracle-orig` 两条路线原文各跑 1 局（VideoUnmask xhard0 分片，各 1 次 reset，合计 2 ≤ P3 单 worker 阈值 10） | 官方文件真实落到 `official/`、`video_check` 仍 PASS、`publish_dir` 原子发布含子目录 | `OFFICIAL_VIDEO_KEPT=PASS side=<new|orig> files=1 frames=<n> size=<W>x<H>`（`ffprobe` 读官方文件）+ `VIDEO_SAVED=PASS … multi_mp4=0` |
| 帧数口径 | 对 smoke 局：官方文件帧数 = `trace.end.demo_frames + 1 + exec_steps`（非超时局） | 与官方 `eval.py` 录帧次数一致 | 上一行 `frames=` 与 `trace.jsonl` 对得上 |
| 存量批量 | 本机 `local-g2`/`local-g3` 的 Oracle 目录全量重绘（约 800+ 局，CPU，放 tmux） | 存量交付补齐 | `OFFICIAL_RENDER_SUMMARY=PASS total=<n> ok=<n> fail=0` |
| 项目闸门 | `ls -1 scripts/*.py` 仍四入口；`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`；`UPSTREAM_GUARD=PASS` | 没碰受保护目录 | 三条判定原文 |

## 五、子代理分工与合并（简述）

拆两块，互不重叠：S1 改两侧「保留官方 mp4」的接线与对应测试（`mmesg_client.py`、`official_hard_runner.py`、`video_check.py` 文档串、两份 groundsg 测试）；S2 写离线重绘工具与它的测试（`render_official_video.py`、新测试文件）。两块各在 worktree 里 `sub/S1`、`sub/S2` 前缀提交；主会话按 S1 → S2 顺序合并，每次合并前跑该块定向测试并派一个 sonnet 审查者看 diff 是否越界、有没有重画官方逻辑，合并后跑核心短测。GPU smoke、真实存量重绘、留档与待做清单由主会话自做（需要 `artifacts/`、显卡与 tmux）。

## 六、待做清单（本轮不改，记入 `docs/1002-pending-decisions.md` P 组）

- **P-1 GroundSG+QwenVL**：同一段官方代码、同一格式 `<y, x>`；放开只需把 `"ground-sg-qwenvl"` 加进 `OFFICIAL_VIDEO_KEEP_VARIANTS`，存量重绘工具可直接用（trace 已含 subgoal）。
- **P-2 Astra**：子目标 `<y, x>` 已在 `trace.jsonl` / `decisions.jsonl`，但 `rollout.mp4` 由 `third_party/Astra-on-RoboMME/examples/champ/runner.py::episode` 自己写，**漏录演示帧**（只有 1 个初始帧 + 执行帧），不走官方 `RolloutRecorder`。需要在 `scripts/eval-official/astra_hard_runner.py::TracedEnv` 接 `EpisodeRecorder` 录全帧，再用重绘工具（或转码叠加）出官方版式。
- **P-3 SimpleMemVLA**：有 simple sub-task 文本（`events.jsonl` 的 `decision.subtask`，如 `"Pick up the peg by grasping the near end"`），无坐标；`smvla_client.py` 未把它写进 trace 的 `subgoal`。需补字段后用重绘工具（只出 Subgoal 条、无黄点）。
- **P-4 PonderPounce**：Ponder 的 subgoal 格式 `at [x, y]`（0～1000，x 在前）只在服务端 INFO 日志（`robomme_server.py::_fire_s2`），回包只有 `actions`；`reasoning_text` 任何地方都没保存；`pp_client.py::trace_step` 写进 trace 的是环境 oracle 标签 `simple_subgoal_online`，**不能当它的推理画**。需改 `third_party/PonderPounce` 服务端回传并换算成 `<y, x>` 0～255（第 24 条：专用分支 + 新 gitlink），或解析服务端日志对齐时间戳。
- **P-5 MME-VLA FrameSamp+Modul**：无语言推理，官方版式只有四条文字区；若要出官方版式同样用重绘工具（`subgoal=None`）。

## 七、盲区诚实清单

1. 官方超时局少录最后一帧（§二 ⚠），我们的 `episode.mp4` 不少；本轮保留官方文件原样、不改 `episode.mp4`，两者在超时局帧数差 1 属已知口径差，记入留档。
2. 重绘的 Action 文字经 float64→float32 再 `.4f`，与官方直接 `.4f` 在极少数值的第 4 位小数可能差 1；State 为 float32 原值无差。
3. 重绘的画面像素来自 h264 解码，与官方原生产物有压缩差；只保证版式与文字逐位、画面「数值容差内一致」，文件名加 `official-rerender__` 前缀区分。
4. imageio 版本：`.venv` 2.37.2、`third_party/mme-vla/.venv` 2.37.0（官方循环实际用它）、imageio-ffmpeg 同为 0.6.0；重绘工具用 `.venv` 跑，编码参数由 imageio 版本决定，`macro_block_size` 缩放行为一致，码率细节不保证逐字节。
5. GL 存量（Turbo 上 Oracle 原侧 / 新侧约 1.1 GB）的重绘要在 GL 纯 CPU 作业里做还是本机挂 NFS 跑，本计划只给本机 `local-g2`/`local-g3` 全量；GL 侧按第 14 条「比较在本机」仅在用户另行要求时做。

## 八、实施步骤表

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 用户「开工」；主检出 clean、`BASE` 记入分配表；复制计划到根目录并 commit | `git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'` 为空 |
| 1 | 派 S1、S2 写入型子代理（opus、worktree） | 各自交回 `sub/` 提交与定向测试 passed |
| 2 | 合并 S1：审查 → `--no-ff` → 核心短测 → push | `PRE_MERGE_REVIEW=PASS`、`POST_MERGE_REVIEW=PASS` |
| 3 | 合并 S2：同上 | 同上 |
| 4 | 主会话：真实存量一局重绘 + 目视；两侧 smoke 各 1 局 | `OFFICIAL_RENDER=PASS frames=1245`；`OFFICIAL_VIDEO_KEPT=PASS` ×2；`VIDEO_SAVED=PASS` |
| 5 | 主会话：本机存量 Oracle 全量重绘（tmux + Monitor） | `OFFICIAL_RENDER_SUMMARY=PASS fail=0` |
| 6 | 留档（`result.md` 小节）、待做清单 P 组、commit `12.45x`、push | `git status -sb` 无 `ahead` |

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

- R1 不改 `src/robomme/`（P2），不改 `third_party/*` 内容与 gitlink，不改 `scripts/` 顶层四入口（P1）。
- R2 不改 `run_seat.sh::transcode_episode_dir`、`video_check.py` 判定逻辑、`eval_video_mover.py`；`episode.mp4` 口径不变。
- R3 官方 `RolloutRecorder` 一行不复制、不改写：机制 A 保留其产物，机制 B 以 `importlib.util.spec_from_file_location("official_robomme_utils", <repo>/third_party/mme-vla/examples/robomme/utils.py)` 加载后直接调用。
- R4 reset 预算：smoke 两侧各 1 局 = 2 次 reset（单 worker 阈值 10 内，P3）；重绘不涉及仿真。
- R5 GPU：smoke 用 `nvidia-smi` 查到空闲的一张卡（规划时两卡均 0%），两条路线串行；运行脚本 `preflight_card.sh` 不改内容。
- R6 子代理在 worktree 内只跑 `tests/pipeline/evalx/groundsg/` 与新测试文件，用 `UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <定向> -q`，先打印 `robomme_hard.__file__` 确认指向 worktree。

## 一、逐文件改动清单

**S1-a `scripts/eval-official/mmesg_client.py`**
- 新增模块常量 `OFFICIAL_VIDEO_KEEP_VARIANTS: tuple[str, ...] = ("ground-sg-oracle",)` 与 `OFFICIAL_VIDEO_SUBDIR = "official"`。
- 新增函数：
  ```python
  def keep_official_videos(video_dir: Path, dst: Path | None) -> list[str]:
      """把官方 RolloutRecorder 写在 video_dir 下的 *.mp4 搬到 dst（局目录/official/），返回相对局目录的路径列表；dst 为 None 或无 mp4 返回 []。"""
  ```
  实现：`sorted(video_dir.glob("*.mp4"))` → `dst.mkdir(parents=True, exist_ok=True)` → `shutil.move`；同名已存在时加 `.dupN` 后缀（与 `publish_dir` 的习惯一致）。
- `run_official_episode` 的 `finally`：在 `rmtree(video_dir)` 之前
  ```python
  kept = keep_official_videos(video_dir, (archive_dir / OFFICIAL_VIDEO_SUBDIR) if (archive_dir is not None and ctx["variant"] in OFFICIAL_VIDEO_KEEP_VARIANTS) else None)
  ```
  返回字典加 `"official_video": kept[0] if kept else None, "official_videos": kept`。注释改为「官方叠字 mp4：Oracle 变体保留到 `official/`，其余不交付」。

**S1-b `scripts/eval-official/official_hard_runner.py`**
- 局末 `shutil.rmtree(video_dir, ignore_errors=True)` 前插入 `kept = mmesg.keep_official_videos(video_dir, (ep_dir / mmesg.OFFICIAL_VIDEO_SUBDIR) if variant in mmesg.OFFICIAL_VIDEO_KEEP_VARIANTS else None)`，并把 `kept` 写进该局 `res`（`official_videos`）与 `summary.json`。

**S1-c `scripts/eval-official/video_check.py`**：模块文档串第 2 条后加一句「`official/` 子目录里的官方叠字 mp4 不计入（`glob` 不递归）」。不改代码。

**S1-d 测试**
- `tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py` 新增 `test_official_video_kept_for_oracle_only`：用现有 `F.NewSide(variant, …)` 分别跑 Oracle 与 QwenVL 各 1 局（假官方循环、8 px 帧，夹具注释已说明真 `imageio.mimsave` 可用）；Oracle 断言 `sorted((tdir/"official").glob("*.mp4"))` 长度 1、文件名以 `ep3a1_` 片段匹配官方模板、`r["official_video"]` 指向它、`official-video/` 不存在；QwenVL 断言 `official/` 不存在。
- `tests/pipeline/evalx/groundsg/test_groundsg_orig_runner.py` 新增原侧同款断言。

**S2-a `scripts/eval-official/render_official_video.py`（新）**
- CLI：`render_official_video.py <局目录>… [--root <媒体根> --label mmesg-ground-sg-oracle] [--ffmpeg <路径>] [--out-subdir official] [--prefix official-rerender__] [--overwrite]`。
- `load_official(repo_root) -> module`：按 R3 加载，暴露 `RolloutRecorder`、`TASK_WITH_VIDEO_DEMO`。
- `load_trace(path) -> TraceData`：解析 `header`（`identity.task`、`identity.tier`、`route`）、`demo`（`frames`、`texts[0]`、`states`）、`step`（按 `step` 升序；`subgoal`、`state`、`action`）、`end`（`terminal_reason`、`demo_frames`、`exec_steps`）。`f32_from_record(rec)`：`np.frombuffer(bytes.fromhex(rec["f32hex"]), "<f4")`，断言 `rec["shape"] == [8]`，否则 `raise SystemExit("...f32hex 不能还原 8 维")`。
- `decode_mp4(ffmpeg, mp4) -> np.ndarray[(n,H,W,3)]`：`ffprobe`/`ffmpeg -i` 读 `W×H`，`-f rawvideo -pix_fmt rgb24` 读全量；断言 `W == 512`、`H == 256`（现口径），front = `[:, :, :256]`、wrist = `[:, :, 256:]`。
- `feed_official_recorder(rec, frames_front, frames_wrist, trace, task) -> None`：
  ```python
  n_init = trace.demo_frames + 1
  for i in range(n_init):
      rec.record(image=front[i].copy(), wrist_image=wrist[i].copy(), state=trace.init_states[i],
                 is_video_demo=(task in TASK_WITH_VIDEO_DEMO and i < n_init - 1), subgoal="[initializing...]")
  for k, st in enumerate(trace.steps, start=1):
      rec.record(image=front[n_init+k-1].copy(), wrist_image=wrist[n_init+k-1].copy(),
                 state=st.state, action=st.action, subgoal=st.subgoal)
  ```
  帧数断言：`len(front) == n_init + len(trace.steps)`，不等即 `OFFICIAL_RENDER=FAIL reason=frame_count`。
- 文件名：`f"{task}_ep{episode_id}_{success_flag}_{task_goal}_{difficulty}.mp4"`，`episode_id` 取 `mmesg_client.official_episode_id(identity, dir.name)`（新侧）或 `identity.source_episode`（原侧 `route` 以 `/orig` 结尾），`success_flag = end.terminal_reason`，`difficulty = identity.tier`；加 `--prefix`。
- 判定行：每局 `OFFICIAL_RENDER=PASS|FAIL dir=<名> frames=<n> demo=<d> steps=<k> size=<W>x<H> out=<相对路径>`；批量末行 `OFFICIAL_RENDER_SUMMARY=PASS|FAIL total= ok= fail=`。

**S2-b `tests/pipeline/evalx/report/test_sgx_render_official_video.py`（新）**
- `test_feed_matches_official_recorder_bitwise`：随机 8×8 彩块帧 6 张（2 演示 + 1 初始 + 3 步）、状态 / 动作随机 8 维、子目标 `["pick up the cube at <3, 5>", …]`，task 取 `VideoUnmask`（有红框）与 `BinFill`（无）各一组；一侧按 `eval.py` 原顺序直接调官方 `RolloutRecorder.record`，另一侧调 `feed_official_recorder`；`np.array_equal` 逐帧比 `total_images`；打印 `RENDER_PARITY=PASS frames=6 mismatch=0`。
- `test_f32hex_roundtrip_and_shape_guard`：`array_record(np.arange(8, dtype="<f4"))` → 还原相等；shape `[7]` 触发 `SystemExit`。
- `test_end_to_end_with_real_ffmpeg`：真 ffmpeg 编 4 帧 512×256 的 `episode.mp4`，写假 `trace.jsonl`（1 演示 + 1 初始 + 2 步），跑 `main`，`ffprobe` 数帧 = 4，`official/official-rerender__VideoUnmask_ep3a1_success_<goal>_xhard0.mp4` 存在；缺 ffmpeg 则 skip。

**主会话自做**
- 计划复制到根目录；`docs/1002-pending-decisions.md` 追加「P 组：评估视频官方版式」P-1～P-5；`docs/validation/sg-eval-gl-20261004-01/result.md` 追加「存量重绘（12.45x）」小节，内联 `OFFICIAL_RENDER_SUMMARY` 行与目视结论；`records/` 归档重绘汇总 jsonl。

## 二、子代理分配表

| 子任务 | 目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖 | 合并顺序 | 验收命令与判定行（worktree 内，R6 环境） | 资源 | 共享文件归属 |
|---|---|---|---|---|---|---|---|---|
| S1 | 两侧保留官方 mp4 到 `official/`，Oracle 门控 | `scripts/eval-official/mmesg_client.py`、`scripts/eval-official/official_hard_runner.py`、`scripts/eval-official/video_check.py`（仅文档串）、`tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py`、`tests/pipeline/evalx/groundsg/test_groundsg_orig_runner.py` | `src/`、`third_party/`、`run_seat.sh`、`render_official_video.py` | 导出 `keep_official_videos`、`OFFICIAL_VIDEO_KEEP_VARIANTS`、`OFFICIAL_VIDEO_SUBDIR`；返回字典键 `official_video` / `official_videos` | 1 | `… pytest tests/pipeline/evalx/groundsg -q` 末行 `passed`，新增两个测试名出现在 `-v` 输出 | CPU，≤3 分钟 | 无共享 |
| S2 | 离线重绘工具与测试 | `scripts/eval-official/render_official_video.py`、`tests/pipeline/evalx/report/test_sgx_render_official_video.py` | 同上 + S1 的全部文件 | 只读 `mmesg_client.official_episode_id`（已存在，签名 `(identity: dict, episode_tag: str) -> str`）、`trace_writer.array_record` 格式；按 R3 加载官方 utils | 2 | `… pytest tests/pipeline/evalx/report/test_sgx_render_official_video.py -q` 末行 `passed`；stdout 含 `RENDER_PARITY=PASS frames=6 mismatch=0` | CPU，≤3 分钟（真 ffmpeg） | 无共享 |
| 主会话 | 根目录计划、待做清单、留档、smoke、存量重绘、合并与 push | 上述 docs 与根目录计划 | — | 依赖 S1、S2 合入 | 3 | §四各判定行 | GPU 1 张（smoke 两局串行）、tmux 前缀 `ovl-` | — |

派发前核对：`worktree.baseRef=head`（已核 `~/.claude/settings.json` 第 19 行）、`git check-ignore -q .claude/worktrees/probe` 成功（已核）、现有 worktree `.claude/worktrees/motionjepa-ckpt-branch-check-ffae44` 不动、主检出 clean（已核）。

## 三、闸门总表

| 闸门 | 命令 | 判定行 |
|---|---|---|
| 核心短测 | `timeout 280s uv run --no-sync python -m pytest -m 'not slow' -q` | 末行 passed、`TEST_RESOURCE=` 行 |
| 重绘逐位 | S2 单测 | `RENDER_PARITY=PASS frames=6 mismatch=0` |
| 真实存量一局 | §四第 4 行命令 | `OFFICIAL_RENDER=PASS dir=VideoPlaceButton_xhard2_19002401.a1 frames=1245 demo=1082 steps=162 size=512x512`（高度为 imageio 缩放后实测，预期 506→512） |
| smoke 新侧 | `bash artifacts/sg-evaluation/sg-eval-gl-20261004-01/preflight/preflight_card.sh <卡> mmesg-oracle-new-hard0`（原文不改） | `OFFICIAL_VIDEO_KEPT=PASS side=new files=1 frames=<n> size=<W>x<H>`（主会话 `ffprobe` 读 `official/*.mp4` 后手写）、`VIDEO_SAVED=PASS … multi_mp4=0` |
| smoke 原侧 | 同上 `mmesg-oracle-orig` | `OFFICIAL_VIDEO_KEPT=PASS side=orig …` |
| 存量全量 | `render_official_video.py --root artifacts/sg-evaluation/sg-eval-gl-20261004-01/local-g3/media --label mmesg-ground-sg-oracle`（及 `local-g2` 各 stage/media 根） | `OFFICIAL_RENDER_SUMMARY=PASS total=<n> ok=<n> fail=0` |
| 项目闸门 | `ls -1 scripts/*.py`；`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`；`uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | 四入口；零 diff；`UPSTREAM_GUARD=PASS` |

## 四、runbook（主会话）

1. 开工后：复制计划到根目录 → `git add 1005-eval-video-official-overlay-plan.md` → commit `12.457 计划：评估视频对标官方 RolloutRecorder（GroundSG+Oracle）` → push。`BASE=$(git rev-parse HEAD)`。
2. 同一消息派 S1、S2（`isolation: "worktree"`、`model: "opus"`，提示含分配表全部要素、R1～R6、commit 规约 `sub/S1: …`）。
3. 收 S1：主检出 clean 核对 → `git diff --name-only BASE..TIP ⊆ 集合` → worktree 内复跑验收 → 派 sonnet 审查者（钉 `REVIEW_BASE`/`REVIEW_TIP`）→ `git merge --no-ff <TIP> -F <msg>` → 核心短测 → `POST_MERGE_REVIEW` → push。S2 同。
4. 真实存量一局重绘 → `ffmpeg … tile=4x1` 抽 4 帧 → `Read` 目视 → 记录。
5. smoke：`nvidia-smi` 选空闲卡 → tmux `ovl-smoke-new` 跑 `preflight_card.sh <卡> mmesg-oracle-new-hard0`，Monitor 过滤 `ROUTE_END|VIDEO_SAVED|REC_TRANSCODE|Traceback|EXIT_CODE=|NO RECORD|reset 拒绝|svulkan2`；完成后 `ovl-smoke-orig`。读 `official/*.mp4` 的 `ffprobe`，写判定行。
6. 存量全量：tmux `ovl-rerender-g3` / `ovl-rerender-g2`，日志 `artifacts/sg-evaluation/sg-eval-gl-20261004-01/rerender/<名>.log`，Monitor 过滤 `OFFICIAL_RENDER_SUMMARY|FAIL|Traceback|EXIT_CODE=`。
7. 留档 + 待做清单 + commit `12.45x` + push；清理 S1/S2 worktree 与分支（只删分配表登记的）。

## 五、风险登记

| 风险 | 影响 | 处置 |
|---|---|---|
| 官方 `imageio.mimsave` 对 506 px 高打 `macro_block_size` 警告并缩放 | 官方产物高度 512 而非 506，字体略糊 | 这是官方行为，原样保留；判定行记实测尺寸 |
| 新侧 `archive_dir` 为 None（无轨迹目录的调试模式） | 官方 mp4 仍被删 | `keep_official_videos(…, None)` 返回 `[]`，`official_video=None`，不报错 |
| 官方文件名含 task_goal 长文本 | 曾致 SwingXtimes 超 255 字节（12.453 已用短 `episode_id` 修） | 保留现有 `official_episode_id`，不改 |
| 存量 h264 解码帧与官方原生像素差 | 重绘不是逐位复刻 | 文件名前缀 `official-rerender__` 区分，留档写明 |
| `publish_dir` 的 rsync + 逐文件 sha 包含子目录 | 发布时间略增（每局 +1 个 ~1 MB 文件） | 可忽略；smoke 核对 `.incoming` → 正式目录含 `official/` |

## 六、盲区诚实清单

同第一部分 §七。另：GL 侧 Turbo 上的 Oracle 存量未列入本轮重绘范围，需要时另起纯 CPU 作业（第 8 条 standard 分区例外仅限 HF 校验，需用户另批）。

## 七、留档与 commit 纪律

- 计划 commit 单独一个（12.457）；S1/S2 经 `--no-ff` 合并各占一个项目号；收尾留档一个。body 按第 11 条六项写，含本文件 §一的用户原话。
- `docs/validation/sg-eval-gl-20261004-01/result.md` 只追加小节，不改既有判定行；`records/` 新增 `rerender-summary.jsonl`（逐局判定行）。
- 不归档 mp4；存量重绘产物留在 `artifacts/`。
