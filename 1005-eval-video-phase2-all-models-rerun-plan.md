# 1005-eval-video-phase2-all-models-rerun-plan.md — 第二阶段：全部模型评估链路产出官方版式视频，然后重跑第一、二、三档

> 只规划不实施，须用户明确说「开工」，并在开工前一次性批准 §五的预算与资源（`AGENTS.md` 第 2 条、P3）。代码锚点 `6a23af54`（12.459，Codex 第一阶段实现已合入），工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`。第一阶段计划与官方版式定义见 [`1005-eval-video-official-overlay-plan.md`](1005-eval-video-official-overlay-plan.md)（第一阶段由 Codex 执行中：重绘工具 `scripts/eval-official/render_official_video.py` 与 16 个定向测试已合入，800 局重绘至本文件写就时 596/800、零失败）。上一轮三档评估的规模、流程与留档体例见 [`1003-oracle-subgoal-groundsg-eval-plan.md`](1003-oracle-subgoal-groundsg-eval-plan.md) 与 `docs/validation/sg-eval-gl-20261004-01/`。
> 用户原话（2026-10-05）：「修改该计划第一阶段只做我想要的V9第三档+Oracle转码。第二阶段完成所有模型的视频修改 然后重新跑123阶段」「第一阶段已经有Codex来执行了你检查一下然后你把第二阶段写入一个单独的计划然后细化。现在的一部分给人看的第二阶段也有点太少了稍微多一点告诉我你要大概要修改哪些部分然后需要重新跑这个第一第二第三阶段」。

# 第一部分（给人看）

## 一、目标与一句话方案

第一阶段只是把已经跑完的 Oracle 视频事后重绘成官方版式。第二阶段要做到：**以后每个模型评估跑出来的每一局，目录里都直接带一份官方版式视频**（上方 `Frame / Task Goal / Action / State` 四条黑底白字，有语言推理的模型再加 `Subgoal: …` 一条并在 `<y, x>` 处画黄点，演示帧红框，30 fps，帧数 = 演示帧 + 1 + 每步一帧），不再靠事后补。做法分两类：GroundSG 本来就在跑官方循环、官方自己会生成这份视频，只需不删；其余模型没有官方循环，统一改成「每步把子目标写进轨迹 `trace.jsonl`」，再由第一阶段的重绘工具在局末从本局原始帧 + 轨迹生成官方版式。改完之后把上一轮的三档评估从头重跑一遍，使正式交付的视频全部是官方版式。

## 二、各模型分别改哪些部分

| 模型 | 语言推理现状 | 要改的部分 | 改完后视频长什么样 |
|---|---|---|---|
| GroundSG + Oracle、GroundSG + QwenVL | 官方循环每局都生成叠字 mp4，被我们在局末删掉 | 两侧（原版接口 `official_hard_runner.py`、新接口 `mmesg_client.py`）局末把官方 mp4 搬到局目录 `official/`，其余不动 | 与官方逐字节同源：五条文字 + 黄点 + 红框 |
| Astra | 子目标 `<y, x>` 已逐步写进 `trace.jsonl`；但它自己写的 `rollout.mp4` 漏了演示帧、没有腕部以外的任何叠加 | 新侧 `astra_hard_runner.py` 接上本仓库的无损录像器（和其他路线一样录演示帧 + 每步帧 + 状态动作数组），局末转码出 `episode.mp4`，再调重绘工具出官方版式；原侧 Astra 自己的 `rollout.mp4` 保留作对照 | 五条文字 + 黄点 + 红框，帧数口径与其他路线一致 |
| SimpleMemVLA | 有无坐标的 sub-task 文本，只在 `events.jsonl` 的决策事件里；这条路线没有 `trace.jsonl` | `smvla_client.py` 每局写 `trace.jsonl`（演示段 + 每步，子目标 = 当前动作块的 sub-task 文本），局末调重绘工具 | 五条文字（Subgoal 条有文字、没有黄点，因为没有坐标），演示帧红框 |
| PonderPounce | Ponder 的子目标只打在服务端日志里，客户端拿不到；现在写进轨迹的是环境 oracle 标签，不是它的推理 | 服务端（`third_party/PonderPounce`，专用分支）把当前子目标随每个动作回传；客户端 `pp_client.py` 把它的 `at [x, y]`（0～1000，x 在前）换算成官方 `<y, x>`（0～255）写进轨迹，取代 oracle 标签；两侧（`pp_official_runner.py`、新侧）都走这条；局末调重绘工具 | 五条文字 + 黄点（点位经一次换算，可能偏 1 像素）+ 红框；reasoning 段服务端没保存，本阶段不画 |
| MME-VLA FrameSamp + Modul（无推理） | 没有语言推理，这条路线也没有 `trace.jsonl` | `mme_client.py` 写最小 `trace.jsonl`（子目标为空），局末调重绘工具 | 只有四条文字 + 红框，与官方 π0.5 视频一致 |

公共改动：重绘工具 `render_official_video.py` 增加「直接读录像器原始帧（`front.mkv`／`wrist.mkv`）」的输入模式，让局末在删原始帧之前就能用无损帧出官方版式（第一阶段是从有损 `episode.mp4` 重绘，第二阶段的新局不再有这层压缩差）；席位脚本 `run_seat.sh` 的转码步骤之后加一步「调重绘工具」，所有路线统一。`video_check.py` 与搬运工具的「每局恰一个 mp4」判定不变，官方版式文件放 `official/` 子目录不计数。

## 三、为什么要重跑第一、二、三档

改动落在评估的运行链路里（Astra 换录像器、SimpleMemVLA / MME 新增轨迹写入、PonderPounce 服务端回包变化、席位脚本多一步），上一轮已交付的局是改动前跑的。要让「正式交付的每一局都带官方版式视频」成立，并证明这些改动没有改变成绩，需要按上一轮同样的三档从头跑：

- **第一档 生成对拍**：旧码对新码各生成一遍（V9 每格 3 局 = 129 局，xhard0 每任务 3 局 = 48 局），证明生成链路没变。第二阶段不动生成侧，这一档预期 PASS，但照规矩跑。
- **第二档 xhard0 原版接口对新接口**：每个模型在 xhard0 上原侧、新侧各跑 16 任务 × 1 档 × 12 局 = 192 局（Astra 16 任务 × 1 局 = 16 局 × 两侧），证明新接线（含新录像、新轨迹、新回包）与原版接口行为一致，同时两侧都拿到官方版式视频。
- **第三档 V9 正式评估**：GroundSG Oracle、GroundSG QwenVL、PonderPounce 各 800 局（16 任务 × 50 局），正式成绩与正式视频以这一轮为准；Astra 只跑 1 局确认接口通（更多局数须用户另批）。
- 顺序与并行沿用上一轮：GL 每席先第二档后第三档自动衔接、第一档单占一席；本机两卡先跑第一档再跑第二档；第一、二档的结论只记录不阻塞。

## 四、规模与资源（开工前一次性批准）

| 项 | 数量 | 说明 |
|---|---|---|
| 第一档生成 | (129 + 48) × 2 遍 = 354 局 | GL 1 席 + 本机 |
| 第二档 | GroundSG Oracle / QwenVL / PonderPounce 各 192 × 2 侧 = 1152 局；Astra 16 × 2 = 32 局 | GL 全量；本机另跑一遍（除 Astra） |
| 第三档 | 3 模型 × 800 = 2400 局；Astra 1 局 | GL；本机可复刻 Oracle 800 局 |
| reset／轨迹预算 | 上述总局数 + 基础设施重试（每局 ≤3 次）+ 每路线 smoke 1 局 | 按 P3 一次性批 |
| GL 占位 job | 上一轮 9 个：`63188711`／`12`／`13` 在跑（48 h 限时，分别约 10-06 23:00、10-07 05:00、10-07 23:00 到期），其余 6 个 `PENDING (AssocGrpCpuLimit)` | 第二阶段开工时按 `greatlakes.md` 重新提交同规格 48 h 占位 job，数量按用户批 |
| Astra 付费接口 | 第二档 32 局 + 第三档 1 局 + smoke 2 局 | 用户 2026-10-04 明令逐项审批 |
| 本机 | 2 × RTX 6000 Ada，第一阶段重绘完成后空闲 | smoke、第一档、第二档复刻 |

## 五、步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 用户「开工」+ 一次性批预算与 job 数；提交占位 job；主检出 clean、记 `BASE` | `git status` 干净；JobID 记入 `launch.md` |
| 1 | 并行派 S1（GroundSG 保留官方 mp4）、S2（重绘工具原始帧模式 + 席位脚本接入）、S3（Astra 录像器）、S4（SimpleMemVLA / MME 轨迹）、S5（PonderPounce 回传与换算） | 各自定向测试 passed、`sub/` 提交 |
| 2 | 依次审查合并 S2 → S1 → S4 → S3 → S5，每次合并后核心短测 + push | `PRE_MERGE_REVIEW=PASS`、`POST_MERGE_REVIEW=PASS` ×5 |
| 3 | 本机每路线 smoke 1 局（含 Astra 两侧各 1 局，已含在 §四） | 每局 `official/` 下有官方版式 mp4：`OFFICIAL_VIDEO_KEPT=PASS`（GroundSG）／`OFFICIAL_RENDER=PASS`（其余），`VIDEO_SAVED=PASS multi_mp4=0` |
| 4 | GL 第一档 → 各席第二档 → 第三档；本机第一档 → 第二档 | 沿用 1003 计划判定行 + 每模型 `OFFICIAL_RENDER_SUMMARY=PASS fail=0` |
| 5 | 留档 `docs/validation/sg-eval-gl-<日期>-02/`、成绩表、视频索引、commit、push | `git status -sb` 无 `ahead` |

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1 不改 `src/robomme/`（P2）、`scripts/` 顶层四入口（P1）；`third_party/PonderPounce` 的改动按第 24 条：从锁定提交 `723df357` 建专用分支 `official-video-newtaskRelease-taskV9`，先在该分支 commit + push，主仓库再更新 gitlink；其他 `third_party/*` 不动。
- R2 官方 `RolloutRecorder` 不复制、不改写；一切官方版式输出要么是官方循环自己写的文件，要么是 `render_official_video.py` 用 `importlib` 加载官方类喂数据得到的。
- R3 `episode.mp4` 口径不变；`video_check.py`、`eval_video_mover.py` 判定逻辑不变；官方版式文件一律放局目录 `official/`。
- R4 预算按 §四一次性批准，不拆阶段再问；超出即停并合并补充授权。
- R5 第一阶段的 Codex 产物（`render_official_video.py`、站点 `official_overlay_*`、`docs/validation/sg-eval-gl-20261004-01/` 留档）不回滚、不重写；本阶段对重绘工具只做增量（新增输入模式），并保持 16 个既有测试通过。
- R6 子代理在 worktree 内只跑定向测试：`UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <定向> -q`，先打印 `robomme_hard.__file__`。

## 一、逐文件改动清单

**S1 GroundSG 两侧保留官方 mp4**
- `scripts/eval-official/mmesg_client.py`：新增 `OFFICIAL_VIDEO_SUBDIR = "official"`、`keep_official_videos(video_dir: Path, dst: Path | None) -> list[str]`（`sorted(video_dir.glob("*.mp4"))` → `dst.mkdir(parents=True, exist_ok=True)` → `shutil.move`，同名加 `.dupN`）；`run_official_episode` 的 `finally` 在 `shutil.rmtree(video_dir)` 前调用，目标 `archive_dir / OFFICIAL_VIDEO_SUBDIR`（`archive_dir` 为 None 时返回 `[]`）；返回字典加 `official_videos`。注释改为「官方叠字 mp4 保留到 `official/`」。
- `scripts/eval-official/official_hard_runner.py`：局末 `shutil.rmtree(video_dir, ignore_errors=True)` 前 `kept = mmesg.keep_official_videos(video_dir, ep_dir / mmesg.OFFICIAL_VIDEO_SUBDIR)`，写进 `res["official_videos"]` 与 `summary.json`。
- 测试：`tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py` 新增 `test_official_video_kept_in_official_subdir`（Oracle 与 QwenVL 各 1 局：`official/*.mp4` 恰 1 个、文件名含 `ep3a1_`、`official-video/` 不存在）；`test_groundsg_orig_runner.py` 同款。

**S2 重绘工具原始帧输入模式 + 席位脚本接入**
- `scripts/eval-official/render_official_video.py`：`decode_source(ep_dir)` 增加分支——若存在 `front.mkv`／`wrist.mkv` + `frames-<stream>.jsonl`（新侧录像器）或 `frames/{front,wrist}.rgb24` + `frames.json`（原侧），按 `run_seat.sh::transcode_episode_dir` 文档串的展开规则解码为逐帧原图（`enc` 索引展开），否则退回 `episode.mp4`；`render.json` 记 `source_kind=raw|mp4`。无 `trace.jsonl` 的目录打印 `OFFICIAL_RENDER=SKIP reason=no_trace` 并返回 0（供 `mme` 路线补轨迹前过渡）。
- `scripts/eval-official/run_seat.sh`：新增函数 `render_official_dir()`（`$1` = 局目录）：`"$BENCH_PY" "$HERE/render_official_video.py" "$1" --official-root "$REPO" --jobs 1`，打印其判定行；在 `transcode_episode_dir` 成功（`result=ok`）**之前**调用（原始帧尚在），失败只记 `OFFICIAL_RENDER=FAIL` 不阻塞转码与发布。`run_eval_gl.sh`、`run_official_hard.sh` 通过 `source run_seat.sh` 自动获得。开关 `SGEVAL_OFFICIAL_RENDER=0` 可关。
- 测试：`tests/pipeline/evalx/report/test_sgx_render_official_video.py` 新增 `test_raw_recorder_input_matches_mp4_input_text_and_count`（同一局用原始帧与 mp4 两种输入，帧数与文字区逐位相同、画面允许差）；`tests/pipeline/eval/test_seat_scripts.py` 的 GL 转码用例加断言：每局目录出现 `official/*.mp4` 且 `episode.mp4` 仍恰一个。

**S3 Astra 新侧录像器**
- `scripts/eval-official/astra_hard_runner.py`：`TraceContext` 增加 `recorder`（`recorder.EpisodeRecorder(ep_dir, meta)`，`meta` 照 `env_client.py` 第 1158 行处的构造）；`TracedEnv.reset` 在 `log_demo` 之外 `add_frames("front"/"wrist", np.stack(obs[...]), tag="reset")`、`add_array("reset_joint_state"/"reset_gripper_state", …)`；`TracedEnv.step` 后 `add_frames(..., tag=f"step{t}")`、`add_array("exec_action", action, step=t)`、`add_array("joint_state"/"gripper_state", …, step=t)`；`close` 时 `recorder.close(summary)`。局目录即 Astra `results/<task>/ep<NNN>/`，`trace.jsonl` 已在其中。
- `scripts/eval-official/run_astra.sh`：每局（或整批）结束后对每个 `ep<NNN>` 目录依次调 `render_official_dir`、`transcode_episode_dir`（`source run_seat.sh`，与原侧 `run_official_hard.sh` 同法）。Astra 自己的 `rollout.mp4` 改名保留为 `astra-rollout.mp4`？——**不改名**：它在 `results/` 下与 `episode.mp4` 同目录会触发 `multi_mp4`，因此录像器输出目录改为 `ep<NNN>/media/`（`episode.mp4`、`official/`、`trace.jsonl` 软链或复制一份），`video_check` 对 `media/` 目录核。
- 测试：`tests/pipeline/evalx/astra/test_astra_wiring.py` 加「`media/episode.mp4` 帧数 = 演示帧 + 1 + 步数」「`media/official/*.mp4` 存在」。

**S4 SimpleMemVLA 与 MME 最小轨迹**
- `scripts/eval-official/smvla_client.py::run_episode`：仿 `mmesg_client.run_episode` 建 `trace_writer.TraceWriter(trace_location(conn_info, recorder), route="smvla/new", identity=…, max_steps=…)`；reset 后 `log_demo(fronts[:-1], wrists[:-1], states, texts=[instruction])`；每个决策回包取 `reply["subtask"]` 存为 `cur_subtask`；`step_chunk` 的 `on_exec` 回调里每步 `log_step(step, front, wrist, state, action, subgoal=cur_subtask, …)`；局末 `close(status=…)`。
- `scripts/eval-official/mme_client.py::evaluate_one`／`run_loop`：同样写 `TraceWriter(route="mme/new")`，`subgoal=None`。
- `trace_writer.py` 不改（现有 `log_step(subgoal: str | None)` 已够）。
- 测试：`tests/pipeline/eval/test_policy_clients.py` 加两条：smvla 一局 `trace.jsonl` 的 `step` 行数 = 执行步数且 `subgoal` 非空；mme 一局 `subgoal` 全为 `None`。

**S5 PonderPounce 子目标回传与换算**
- `third_party/PonderPounce`（专用分支）`ponderpounce/eval/robomme_server.py::_dispense`：两处 `return {"actions": …}` 改为 `return {"actions": …, "subgoal": ep.active_subgoal or None}`；`_hold` 分支同。不改模型与推理路径。
- `scripts/eval-official/pp_client.py`：新增 `pp_subgoal_to_official(text: str | None) -> str | None`：正则 `at \[(\d+), (\d+)\]` → `at <{round(y*255/1000)}, {round(x*255/1000)}>`（PP 正向是 `round(px*1000/255)`，逆变换四舍五入，点位误差 ≤1 px，记入 `render.json`）；`TracedConnection.act` 捕获 `action.get("subgoal")` 存 `self.last_subgoal`；`trace_step(..., subgoal=pp_subgoal_to_official(conn.last_subgoal))`，不再读 `info["simple_subgoal_online"]`（oracle 标签改记到 `trace` 的 `history` 行 `note=oracle_simple_subgoal:<文本>` 以便对比，不进 `subgoal`）。
- `scripts/eval-official/pp_official_runner.py`：原侧同样经 `TracedConnection` 取得 `last_subgoal`。
- 主会话：更新 gitlink，`launch.md` 锁定表记新 sha。
- 测试：`tests/pipeline/evalx/pp/test_pp_protocol_wire.py` 加换算用例（`at [612, 247]` → `at <63, 156>`；无坐标文本原样；`None` → `None`）与假服务端回包含 `subgoal` 时 trace `subgoal` 字段来自回包而非 info。

**主会话**：`docs/1002-pending-decisions.md` P1 条追加「裁决」；三档重跑留档 `docs/validation/sg-eval-gl-<日期>-02/{launch.md,result.md,records/}`；`docs/validation/sg-eval-gl-20261004-01/result.md` 不改。

## 二、子代理分配表

| 子任务 | 目标 | 可写文件集合 | 禁触路径 | 接口契约与依赖 | 合并顺序 | 验收命令与判定行（worktree 内，R6 环境） | 资源 | 共享文件归属 |
|---|---|---|---|---|---|---|---|---|
| S2 | 重绘工具原始帧模式 + 席位脚本接入 | `scripts/eval-official/render_official_video.py`、`scripts/eval-official/run_seat.sh`（仅新增 `render_official_dir` 与调用点）、`tests/pipeline/evalx/report/test_sgx_render_official_video.py`、`tests/pipeline/eval/test_seat_scripts.py` | `src/`、`third_party/`、其余 `scripts/eval-official/*` | 导出 bash 函数 `render_official_dir`；工具 CLI 向后兼容第一阶段用法 | 1 | `… pytest tests/pipeline/evalx/report/test_sgx_render_official_video.py tests/pipeline/eval/test_seat_scripts.py -q` passed（原 16 个不变） | CPU ≤5 分钟 | `run_seat.sh` 唯一写者 S2 |
| S1 | GroundSG 保留官方 mp4 | `mmesg_client.py`、`official_hard_runner.py`、`tests/pipeline/evalx/groundsg/test_groundsg_official_adapter.py`、`test_groundsg_orig_runner.py` | 同上 + S2 集合 | 导出 `keep_official_videos`、`OFFICIAL_VIDEO_SUBDIR` | 2 | `… pytest tests/pipeline/evalx/groundsg -q` passed | CPU | 无 |
| S4 | SimpleMemVLA / MME 最小轨迹 | `smvla_client.py`、`mme_client.py`、`tests/pipeline/eval/test_policy_clients.py` | 同上 | 只读 `trace_writer.TraceWriter`、`mmesg_client.trace_location` | 3 | `… pytest tests/pipeline/eval/test_policy_clients.py -q` passed | CPU | 无 |
| S3 | Astra 新侧录像器 + 转码接入 | `astra_hard_runner.py`、`run_astra.sh`、`tests/pipeline/evalx/astra/test_astra_wiring.py` | 同上 | 依赖 S2 的 `render_official_dir`（合并后基于新 HEAD 派发或 rebase） | 4 | `… pytest tests/pipeline/evalx/astra -q` passed | CPU | 无 |
| S5 | PonderPounce 回传与换算 | `pp_client.py`、`pp_official_runner.py`、`tests/pipeline/evalx/pp/test_pp_protocol_wire.py`；`third_party/PonderPounce` 专用分支内 `ponderpounce/eval/robomme_server.py` | `src/`、其他 third_party | 回包键 `subgoal`；`pp_subgoal_to_official` | 5 | `… pytest tests/pipeline/evalx/pp -q` passed；PonderPounce 分支内 `uv run --no-sync python -m pytest tests -q -k server` 或等价冒烟 | CPU | gitlink 归主会话 |
| 运行型 R1～Rn | 提交占位 job 后在各席位启动 `run_eval_gl.sh`／`run_official_hard.sh`／`run_astra.sh`（命令原文照 1003 计划 runbook 与上一轮 `launch.md` ⑤⑩） | 无 | 一切代码 | 起跑判据 `SEAT_START`／`ROUTE_START` + 首局 `REC_TRANSCODE … result=ok` | 开工后 | 交回 tmux 名、JobID、日志路径 | GL 席位、本机两卡 | 账目归主会话 |

派发前核对：`worktree.baseRef=head`、`git check-ignore -q .claude/worktrees/probe`、现有 worktree（`.claude/worktrees/motionjepa-ckpt-branch-check-ffae44`、Codex 的 `artifacts/worktrees/official-overlay-*`）一律不动、主检出 clean（Codex 的 `docs/validation/sg-eval-gl-20261004-01/launch.md` 在途改动落地前不派）。

## 三、闸门总表

| 闸门 | 命令 | 判定行 |
|---|---|---|
| 核心短测 | `timeout 280s uv run --no-sync python -m pytest -m 'not slow' -q` | 末行 passed、`TEST_RESOURCE=`、`TEST_INVENTORY=PASS` |
| 项目闸门 | `ls -1 scripts/*.py`；`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`；`uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | 四入口；零 diff；`UPSTREAM_GUARD=PASS` |
| 每路线 smoke（本机） | `bash artifacts/sg-evaluation/sg-eval-gl-20261004-01/preflight/preflight_card.sh <卡> <路线>`（Astra 用 `run_astra.sh` 对应 1 局） | `OFFICIAL_VIDEO_KEPT=PASS side= files=1 frames= size=`（GroundSG）／`OFFICIAL_RENDER=PASS … source_kind=raw`（其余）；`VIDEO_SAVED=PASS … multi_mp4=0` |
| 帧数口径 | 对 smoke 局 `ffprobe -count_frames official/*.mp4` 与 `trace.end.demo_frames + 1 + exec_steps` 比 | 相等（超时局允许官方口径少 1 帧，记录） |
| 第一档 | 1003 计划 `GEN_REGRESS` | `GEN_REGRESS=PASS`（FAIL 只记录不阻塞） |
| 第二档 | 1003 计划 `gate2_compare` | 差异表 `INFO`；每模型两侧 `OFFICIAL_RENDER_SUMMARY=PASS fail=0` |
| 第三档 | 1003 计划成绩表 + `video_check.py` | 每模型 800 局唯一终态；`VIDEO_SAVED=PASS`；`OFFICIAL_RENDER_SUMMARY=PASS total=800 ok=800 fail=0` |

## 四、runbook（主会话）

1. 开工令 + 预算批准 → 按 `greatlakes.md` 提交占位 job（数量按批，`--time=48:00:00 --gres=gpu:1 --cpus-per-task=4 --mem=64G` 同上一轮；Astra 两卡一席）→ JobID 记 `launch.md`。
2. 同一消息派 S2、S1、S4、S5（opus、worktree）；S2 合入后派 S3。
3. 逐个：主检出 clean 核对 → `git diff --name-only BASE..TIP ⊆ 集合` → worktree 复跑验收 → sonnet 审查者（钉 `REVIEW_BASE`/`REVIEW_TIP`）→ `git merge --no-ff <TIP> -F <msg>` → 核心短测 → push。PonderPounce 分支先 push 再更新 gitlink。
4. 本机 smoke：每路线 1 局（tmux 前缀 `ovl2-`，Monitor 过滤 `ROUTE_END|VIDEO_SAVED|OFFICIAL_RENDER|OFFICIAL_VIDEO_KEPT|REC_TRANSCODE|Traceback|EXIT_CODE=|NO RECORD|reset 拒绝|svulkan2`），抽帧目视各一局。
5. GL：同步执行副本到新 HEAD（`robomme_benchmark-sgeval` 检出冻结提交）→ 第一档席 → 各席第二档接第三档；本机第一档 → 第二档（除 Astra）。运行型子代理只启动不盯；主会话逐日志挂 Monitor。
6. 留档 `docs/validation/sg-eval-gl-<日期>-02/`（launch.md 起跑即写，result.md 跑完写，records/ 判定行与差异表），commit、push，按清单 `scancel` 自己的占位 job。

## 五、风险与盲区

| 项 | 说明 | 处置 |
|---|---|---|
| PonderPounce 坐标逆换算 | `round(v*255/1000)` 不是精确逆，黄点可能偏 1 px | `render.json` 记原文与换算值；留档写明 |
| PonderPounce reasoning | 服务端未保存，不画 | 待用户另定是否改服务端保存 |
| Astra 目录布局 | 录像器产物与 `rollout.mp4` 同目录会触发 `multi_mp4`，改放 `media/` 子目录 | S3 实现时固定；`video_check` 对 `media/` 核 |
| 官方超时局少一帧 | 官方 `count > max_steps` 先 break 后 record | GroundSG 保留官方文件原样；重绘工具按第一阶段口径（Codex 已处理 timeout 局） |
| GL 占位 job 到期 | 在跑三席 48 h 内到期，6 席 PENDING | 开工时重新提交；数量与规格按用户批 |
| 第二阶段 smoke 与三档的 reset 总量 | 见 §四，远超 P3 阈值 | 开工前一次性批，不拆问 |
| Codex 第一阶段在途 | `launch.md` 有未提交改动、站点与 Playwright 未完 | 等其落地后再派本阶段写入型子代理；本计划不改其文件 |

## 六、留档与 commit 纪律

S1～S5 各经 `--no-ff` 合并占一个项目号；PonderPounce 专用分支提交在其仓库；三档重跑按第 12、13 条体例留档到 `docs/validation/sg-eval-gl-<日期>-02/`；commit body 按第 11 条六项，含文首用户原话；不归档 mp4。
