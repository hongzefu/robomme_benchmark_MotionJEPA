# 录像流式写入与清单混跑实施计划：视频完整、不吃内存、失败不静默；双卡每卡 12／16／20 worker 对拍

> **权威与状态：**本文件按 [AGENTS.md](AGENTS.md) 强制规则第 10 条组织，是独立于 [NEW_VALUE_INJECTION_TEST_PLAN.md](NEW_VALUE_INJECTION_TEST_PLAN.md) 的实施计划；新值计划本轮不动，本计划落地后再由其引用。本文只规划不实施；每个阶段须单独获批，后续授权明确覆盖多个阶段时按该授权执行。
>
> **代码锚点：**只读核查基线 `504daee`（`10.30`），分支 `newtask-v2`，工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，工作区干净。改动前的串行参考产物固定为 `artifacts/parallel-calibration/20260909-schema3-parallel-v2/runs/S0a/`（生成代码 `91bacf9`，与当前 `src/`、`scripts/*.py`、`pyproject.toml`、`uv.lock` 逐文件散列一致，只有 `scripts/README.md`、`tests/_shared/parallel_calibration.py`、`tests/lightweight/test_parallel_calibration.py` 三个非生成路径文件不同）。提交编号沿用 `10.<小版本> <中文描述>`，实施时按当时最新 `git log` 递增。
>
> **依赖锚点：**[pyproject.toml](pyproject.toml)、[uv.lock](uv.lock)；`imageio 2.37.2`、`imageio-ffmpeg 0.6.0`（`mani-skill` 传递依赖，不新增声明）；`/usr/bin/ffprobe` 存在。不新增外部服务。
>
> **⚠ 两条用户指令冲突，本计划按最新一条执行并留开关：**较早指令为「`NO RECORD` 阶段的步骤就是要直接跳过的，把这条写入 AGENTS.md」；最新指令为「`reset()` 返回时补录第 0 帧；`step()` 里录像不再看 `NO RECORD`，只有 HDF5 采集还按原条件走」。本计划以最新指令为准（录全部步骤 + reset 帧），但把录像范围做成显式开关 `video_scope`（`all`／`recorded`），`recorded` 即现状口径，用于与旧视频帧数对拍；AGENTS.md 暂不新增「跳过 `NO RECORD`」规则，待用户裁定后再补。

## 第一部分（给人看）

### 一、要做的三件事

一句话方案：**录像器只换"帧怎么写到磁盘"——每帧到达即写 ffmpeg 管道、内存只留一帧、写失败进结果记录；生成入口加清单模式，一次调用把多个任务／难度组混进同一套双卡进程池；再用双卡每卡 12／16／20 worker 跑原值样本做对拍，口径与之前一致。**

```text
现状（RecordWrapper）                            改后
 reset() ──不录──▶                                reset() ──▶ 第 0 帧（video_scope=all）
 step ──▶ 合成帧 ──▶ video_frames.append           step ──▶ 合成帧（不变）──▶ writer.append_data ──▶ ffmpeg 管道 ──▶ videos/.partial/…pidN.mp4
   （NO RECORD 步跳过）                              （video_scope=all 时 NO RECORD 步也录；HDF5 采集条件不变）
 close() ──▶ 一次性编码 ~1000 帧（≈3 GB 缓存）     close() ──▶ 关写入器 ──▶ os.replace 到最终名 ──▶ video_report
          ──▶ 异常吞成 logger.debug                _worker ──▶ ffprobe 数帧 ──▶ episode_results.jsonl 的 video 字段

现状（生成入口）                                  改后
 一次调用 = 一个难度比例 × N 个任务 × M 条          --job-manifest：11 组各自 task／difficulty／output_dir／episodes
 校准每批 4 条 → 20 个槽位只有 4 个在跑             一次调用 4 组 × 40 条 = 160 job 轮转进同一套双卡池，40 个槽位填满
```

| 任务 | 本轮范围 | 判定 |
|---|---:|---|
| 录像器 `RecordWrapper.py` | 只改写入路径 + `video_scope` 开关 + `video_report` | `VIDEO_DECODE`、`VIDEO_OBSERVER_PARITY`、`VIDEO_SCOPE` |
| 生成入口 `generate_dataset_newseed.py` | 视频核验、残片打捞、清单模式 | `VIDEO_INDEX`、`MANIFEST_LAYOUT`、`DEFAULT_PARITY` |
| 并发测试 `parallel_calibration.py` | 三档 × 4 组 × 40 条 = 480 次 | `BASELINE_PARITY`、`CROSS_TIER_PARITY`、`PARALLEL_OVERLAP`、`PARALLEL_SCALE` |

#### 1.1 已定死的口径

1. 视频画面布局不动：主相机、腕部相机、原始分割、目标分割、目标标记，上下两排规划与在线判断，任务文字与示范红框；合成函数 `_video_prepare_step_frames`、`_video_compose_planner_online_rows`、`_video_apply_overlays`、`_video_build_filename_parts` 与四种最终命名逐字不动（第二节）。
2. `video_scope=all`：`reset()` 返回时补录第 0 帧，`step()` 里每一步都录，`NO RECORD` 步在画面上叠 `NO RECORD` 标注；HDF5 采集条件保持原判断 `_video_should_record(current_task)`，HDF5 内容一个字节不变（第二节、`VIDEO_OBSERVER_PARITY`）。`video_scope=recorded` 为现状口径，只用于对拍旧视频帧数。
3. 每帧同步写 ffmpeg 管道，管道自带反压、不丢帧，进程内只驻留一帧；分片 MP4（`-movflags +frag_keyframe+empty_moov+default_base_moof`），崩溃后已写帧可解码；`-threads 1`（第二节）。
4. 写入或关闭异常记入 `video_report`，`close()` 本身不抛（HDF5 落盘不能被视频异常打断）；生成器 `_worker` 用 `ffprobe -count_frames` 数帧核对，视频状态写进每条执行记录的 `video` 字段，不改变 `ok`（第三节）。
5. 成功和失败都存视频，失败带 `FAILED_` 前缀，仍落生成输出目录 `videos/`；池崩溃留下的残片由父进程改名为 `FAILED_PARTIAL_…`（第三节）。
6. 清单模式：`--job-manifest` 一次接收多个组，每个 job 自带 `difficulty` 与独立 `output_root`；组间轮转入队，同一套双卡池；每组目录布局与单组调用完全相同（第四节）。
7. 并发测试：双卡直接测每卡 12／16／20（总 24／32／40 worker），每档四个原值组各 episode 0～39 一次调用混跑；episode 0～3 与改动前 `S0a` 逐位比，4～39 三档互比；选「成功且视频完整的条数 / 墙钟」最高的稳定档（第五节）。
8. 对拍口径与之前一致：`tests/_shared/native_sampling_parity.py::compare_h5` 全字段逐位、`compare_evidence` 观察器证据、`rrt_fallback_count == 0`；失败不换 seed、不补样本、不放宽容差（第五节）。

#### 1.2 本方案依据的用户原话

> 生成后的100episode尽可能保留完整视频
> 主诊断视频主相机、腕部相机、原始分割、目标分割、目标标记；上下两排分别显示规划与在线判断，附任务文字成功和失败都尝试保存；失败文件带 FAILED_ 前缀
> 使用这套机制由 RecordWrapper.py 保存到生成输出目录的 videos/
> 需要2gpu多worker尽可能多的并行

> 不要改动视频生成的逻辑！只能修改视频写的逻辑
> NO RECORD 阶段的步骤就是要直接跳过的！！！ 把这条写入agents md
> 双卡直接测大于10worker
> 修改完 生成入口 generate_dataset_newseed.py 录像器 RecordWrapper.py 你要做对拍测试 和之前一致

> 不改了 单独成一个plan 实现. 改录像器 RecordWrapper.py，让视频完整、不吃内存、失败不静默。
> 改法：reset() 返回时补录第 0 帧；step() 里录像不再看 NO RECORD，只有 HDF5 采集还按原条件走，HDF5 内容一个字节不变；每一帧直接写进 ffmpeg 管道，内存里只留一帧；close() 时把编码结果和错误交给生成器，生成器用 ffprobe 数帧核对，视频状态单独记录。视频画面布局（主相机、腕部相机、原始分割、目标分割、目标标记，上下两排规划与在线判断，任务文字）不动，成功和失败都存，失败带 FAILED_ 前缀，仍落 videos/。
> 2. 改生成入口 generate_dataset_newseed.py，让一次调用能把多个组混在一套双卡进程池里跑。
> 改法：新增规格清单模式，一次调用接收 11 个组的规格文件，每个 job 自带难度和独立输出目录。
> 并且测试并发
> NEW_VALUE_INJECTION_TEST_PLAN.md先不动
> 生成计划落到根目录

用户在提问中选定：每卡 12／16／20 三档、每批 40 条；只对 episode 0～3 与旧 `S0a` 逐位比，其余条只做档间互比；视频用分片 MP4。

### 二、录像器：只换写入路径

**现状的三个毛病（源码与实测核实）。** [RecordWrapper.py](src/robomme/env_record_wrapper/RecordWrapper.py)::`RobommeRecordWrapper`：
- `reset()` 不产帧；`step()` 里录像与 HDF5 缓冲同在 `if self._video_should_record(current_task)` 分支内，`_video_should_record` 返回 `save_video and current_task_name != "NO RECORD"`，所以 `NO RECORD` 步既不录像也不进 HDF5（`RouteStick` 3 处、`VideoRepick` 1 处产生 `NO RECORD`）。
- `_video_append_step_frame` 把帧 `append` 到 `video_frames`（目标丢失帧再复制一份到 `no_object_video_frames`），`close()` 里 `_video_flush_episode_files` 才 `imageio.get_writer(path, fps=30, codec="libx264", quality=8)` 一次性编码。帧 1280×768×3 约 2.95 MB，旧 `VideoRepick` 1005 帧一条帧缓存约 2.96 GB，失效上限 2000 步约 5.9 GB；旧 `P01` 档单 worker 峰值 RSS 3.5～5.8 GB，`close_s` 3.4～7.6 秒占墙钟 10～17%。
- `_video_flush_episode_files` 两处 `except Exception as e: logger.debug(...)` 吞掉编码异常；生成器 `_worker` 只用 `_raw_summary` 核 HDF5。

**定义。** 新增 `src/robomme/env_record_wrapper/video_stream.py::EpisodeVideoStream`（只依赖标准库，`imageio` 在函数内导入；`tests/lightweight/test_step_error_handling.py` 把空模块塞进 `sys.modules["imageio"]`，函数内导入在 mock 下走异常分支而不是导入期崩溃）：

```python
class EpisodeVideoStream:
    FFMPEG_PARAMS = ["-threads", "1", "-g", "30",
                     "-movflags", "+frag_keyframe+empty_moov+default_base_moof"]
    def append(self, frame) -> bool      # 首帧：mkdir(.partial) + imageio.get_writer(...)；之后 writer.append_data(frame)
    def finalize(self, final_path) -> dict   # 关写入器；已开流且残片在 → Path.replace(final_path)
    def abort(self) -> dict              # 只关写入器不改名（close 半路抛异常时兜底）
    def report(self) -> dict             # {kind, partial_path, path, frames_written, opened, finalized, size, error, error_type}
```

`append` 首帧才打开写入器，因此没有帧就不会留下 `.partial/` 空目录；写入异常 → `error` 记 `类型: 消息`，尽力关写入器，后续帧静默返回 `False` 并计数 `frames_dropped_after_error`，不重复开流、不抛到 `step()`。写入器打开后尺寸锁死，后续帧不符沿用现有 `cv2.resize(INTER_LINEAR)`。不显式传 `macro_block_size`（四任务帧 1280×768／1280×816 均为 16 倍数，与旧路径同一默认）。本机 imageio 2.37.2 已实测接受上述 `ffmpeg_params`，产物 `format_name=mov,mp4`。

**`RecordWrapper.py` 的改动点（锚点级）。**

| 锚点 | 改什么 | 不动什么 |
|---|---|---|
| `__init__(…, save_video=False, video_scope="all")` | 新参数 `video_scope`；`_video_streams={}`、`_video_stream_size=None`、`_video_finalized=False`、`self.video_report={"enabled", "scope", "main": None, "no_object": None, "errors": []}`；`video_frames`／`no_object_video_frames` 保留为恒空列表 | 构造签名其余参数、`hdf5_dir` 推导 |
| `reset(**kwargs)` | `super().reset` 返回后，若 `save_video and video_scope == "all"`，用返回 obs 的 `sensor_data.base_camera.rgb`／`hand_camera.rgb`／`base_camera.segmentation` 走 `_video_prepare_step_frames`（分割结果面板传空掩码）→ `_video_compose_planner_online_rows(subgoal_text="RESET", …, task_index=-1, is_completed=False)` → `_video_apply_overlays(is_demonstration=False, language_goal)` → `_video_append_step_frame(frame, False)`；帧索引记 `step=-1, phase="reset"` | `reset` 前半段全部缓存清理与 `_init_fk_planner` 顺序 |
| `step(action)` 录像分支 | 条件改为 `self.save_video and (self._video_scope == "all" or current_task != "NO RECORD")`；`NO RECORD` 步叠加 `NO RECORD` 文字（叠字函数不变，只是多一行文本） | **HDF5 缓冲分支单独保留原条件 `self._video_should_record(current_task)`**；`super().step` 之前的一切；合成函数五个 |
| `_video_append_step_frame(frame, no_object_flag)` | 帧写入 `self._video_stream("main")`；`no_object_flag == True` 时惰性开 `no_object` 流；同步一条帧索引 `{frame, step, phase, task, in_h5}` 到内存列表（每帧约 60 字节，不是图像） | 签名、`== True` 写法 |
| `_video_flush_episode_files(success, video_prefix, filename_suffix)` | 幂等；对已开流调 `finalize(_video_final_path(kind, success, …))`；写帧索引旁车 `<最终名>.frames.json`；刷新 `video_report`；本函数不抛 | 签名与 `close()` 里两个调用点、四种命名规则、HDF5 先于视频落盘 |
| 新增 `_video_partial_path/_video_stream/_video_final_path/_video_sync_report/_video_abort_streams` | 残片名 `videos/.partial/{env_id}_ep{episode}_seed{seed}.pid{pid}[.no_object].mp4`（只算路径不建目录） | — |
| `_video_write_mp4` | 删除（全仓无其他引用） | — |
| `close()` | 开头 `task_goal.get_language_goal`／`_video_build_filename_parts` 包一层 try：失败用 `no_goal` 后缀继续 finalize，错误记入 `video_report`；末尾两行 `clear()` 保留 | HDF5 写入分支、`reset/step/close` 名字与签名（`tests/_shared/parity_observer.py::_patch_record_wrapper` 按名包装） |

```text
video_scope=all 的一条视频：
 帧 0            帧 1 … k            NO RECORD 段            … 末帧
 [RESET]         [subgoal/online]    [NO RECORD 标注]        [success / FAILED]
 in_h5=false     in_h5=true          in_h5=false             in_h5=true
 frames_written = 1 + 全部 step 数 ；HDF5 timestep_count = 只数 in_h5=true 的步 ；二者关系由旁车 frames.json 逐帧给出
video_scope=recorded：与现状帧集合逐帧相同，frames_written == timestep_count（旧 BinFill hard ep0：943 == 943）
```

⚠ 陷阱：`close()` 开头 `get_language_goal` 现状没有 try，一旦抛出连 `_video_flush_episode_files` 都不执行，写入器悬空；对策是上表的 try 加生成器 `finally` 里的 `_video_abort_streams()`。`reset()` 现状把 `_video_target_frame_size` 置 `None` 而不清帧，写入器开流后尺寸必须以写入器为准，否则 imageio 抛 `All images in a movie should have same size`。分片 MP4 的 `ffprobe` `nb_frames` 恒为 N/A，一律 `-count_frames` 读 `nb_read_frames`；全仓 grep `nb_frames` 确认没有其他消费者。流式化把 x264 的 CPU 从 `close()` 期摊进 step 循环，每 worker 变成 Python 加 x264 两个常驻线程，`-threads 1` 必须保留。

**收益。** 单 worker 省 2.8～5.9 GB 帧缓存；视频写失败进结果记录；崩溃后残片可解码；视频覆盖 reset 帧与 `NO RECORD` 段。收益数字在冒烟条的 `peak_rss_mb`（旧基线 `BinFill hard ep0` 为 5302 MB）与三档校准的进程组 RSS 里留档。

### 三、生成入口：视频核验与残片打捞

[generate_dataset_newseed.py](scripts/generate_dataset_newseed.py)：
- 顶层加 `import shutil  # noqa: E402`；不加任何 torch／sapien／cv2／robomme 顶层导入（`tests/lightweight/test_native_sampling_config.py::test_generator_top_level_has_no_heavy_imports` 直接做字面量断言，`import h5py  # noqa: E402`、`import numpy as np  # noqa: E402` 两行不动）。
- 新纯函数：`_sha256_path`、`_ffprobe_bin()=shutil.which("ffprobe")`、`_probe_frame_count(path, ffprobe, timeout=120)`（固定 `ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0`）、`_video_stream_status`、`_video_summary(report, expected_frames, scope, mode)`、`_safe_video_summary(record_env, …)`（任何异常降级为 `status="check_error"`，绝不抛）、`_salvage_partial_videos(job)`。
- 状态口径：`none`（从未开流）／`complete`（`frames_decoded == frames_written`；`scope=recorded` 的成功局还须 `== timestep_count`；`scope=all` 的成功局须 `== 1 + 旁车帧索引条数` 且 `in_h5=true` 的条数 `== timestep_count`）／`partial`（少帧，或未 finalize 但残片在，就地改名 `videos/FAILED_PARTIAL_[NO_OBJECT_]{task}_ep{k}_seed{s}.mp4`）／`missing`／`encode_error`／`probe_unavailable`。记录结构 `{"status", "scope", "checked_at", "probe", "streams": {"main": {path, partial_path, frames_written, frames_decoded, frames_expected, bytes, sha256, error}, "no_object": {…}}}`。
- `_worker`：`finally` 里 `record_env.close()` 之后加 `_video_abort_streams()` 兜底（包 try，不改 `caught`）；三条返回路径都带 `base["video"]`；**`_raw_summary` 不沾视频**（它抛异常会判整条失败并删 HDF5），`ok` 完全不受视频影响。
- `EpisodeJob` 新增 `video_check: str = "full"`、`video_scope: str = "all"`（带默认值，`tests/lightweight/test_native_sampling_config.py` 与 `tests/_shared/parity_worker_isolation.py` 用全关键字构造）；CLI `--video-check {full,frames,none}` 默认 `full`、`--video-scope {all,recorded}` 默认 `all`（都有默认值，`test_cli_requires_output_dir_for_generation` 等不受影响）；写进 `run_parameters.json`。
- `_synth_failure` 返回值加 `"video": _salvage_partial_videos(job)`；glob `{task}_ep{ep}_seed{seed}.pid*[.no_object].mp4` 时按 `.no_object` 是否存在显式过滤，防 main 的 glob 吃掉 no_object 残片。
- `_run_jobs` 额外返回全部记录；`run_summary.json` 新增 `video: {check_mode, scope, status_counts, stream_status_counts, frame_mismatch_count, salvaged_partial_count, success_video_complete_count}`。`_write_metadata` 白名单不动。

### 四、生成入口：清单模式，一次调用混跑多个组

**现状。** `generate_dataset_newseed()` 用 `parse_difficulty_ratio(difficulty_ratio)` 得到难度循环，`jobs` 是 `tasks × range(episode_start, episode_start+episodes)` 的笛卡尔积，所有 job 共享一个 `output_root`；难度由 `difficulty_for(episode, cycle)` 按 episode 号取。要"每组一个难度"只能一组一次调用，校准工具因此每批只有 4 条，`--workers 20` 时最多 4 个 worker 在干活。`EpisodeJob` 已经逐 job 携带 `difficulty`、`output_root`、`sampling_config`，`_h5_path(output_root, job)` 与 `RobommeRecordWrapper(dataset=str(output_root))` 都按 job 取目录——混跑的底座已经在，缺的只是入口。

**定义。** 新 CLI `--job-manifest <json>`，与 `--env/--episodes/--episode-start/--difficulty/--output-dir` 互斥（`mode` 互斥组之外另设校验：给了清单就不许再给这五个）。清单格式：

```json
{ "manifest_schema_version": 1,
  "groups": [
    { "task": "BinFill", "difficulty": "hard", "output_dir": "artifacts/…/runs/P01x20/BinFill",
      "episodes": 40, "episode_start": 0, "episode_specs": null },
    { "task": "VideoRepick", "difficulty": "medium", "output_dir": "artifacts/…/runs/P01x20/VideoRepick",
      "episodes": 40, "episode_start": 0, "episode_specs": null } ] }
```

- 校验：`task ∈ ALL_TASKS`、`difficulty ∈ {easy, medium, hard}`、`output_dir` 逐个过 `_prepare_output`（仓库内、非符号链接、互不相同）、`episodes ≥ 1`、`episode_start ≥ 0`、seed 越界护栏按组分别算；`episode_specs` 字段预留给新值计划（本轮只接受 `null`，非 `null` 直接拒绝，不实现消费）。
- 入队顺序：**按 episode 号轮转各组**（组 1 ep0、组 2 ep0、…、组 1 ep1、…），保证每一波里四个任务都在；`_run_jobs` 的 `per_gpu = workers // len(gpus)` 与动态派发不变。
- 产物：每组 `output_dir` 下与单组调用完全相同——`hdf5_files/`、`videos/`、`episode_results.jsonl`（该组的行）、`record_dataset_<task>_metadata.json`、`run_summary.json`、`sampling_config_used.json`；清单根目录（`--manifest-root`，默认清单文件所在目录）另写 `run_parameters.json`（含整份清单与共享参数）、合并的 `episode_results.jsonl` 与 `run_summary.json`。`record()` 按 `job.output_root` 分发到各组 sink，行内容一致。
- 共享参数：`--gpus`、`--workers`、`--layout`、`--max-attempts`、`--max-tasks-per-child`、`--affinity`、`--sampling-config`、`--video-check`、`--video-scope` 对所有组相同并写入根 `run_parameters.json`。
- 关闭态：不传 `--job-manifest` 时入口逐字走原路径，`jobs` 构造与 `parameters` 不变（`DEFAULT_PARITY`）。

```text
--job-manifest 一次调用（每卡 20 worker）：
 队列：B0 R0 U0 P0 B1 R1 U1 P1 … B39 R39 U39 P39   （B=BinFill R=RouteStick U=VideoUnmaskSwap P=VideoRepick）
 GPU0 池 20 槽 ─┐                                  第 1 波 40 个 job 同时在跑 → 40 个不同 PID 同时在 step
 GPU1 池 20 槽 ─┘  按剩余容量动态派发
 落盘：runs/<档>/BinFill/…  runs/<档>/RouteStick/…  …（与单组调用布局相同，校准工具 collect_batch 按任务目录照常读）
```

⚠ 陷阱：`SeedLayout` 的 seed 只由 `(task, episode, attempt)` 决定，同任务不同难度的 episode 0 会撞出同名 `.h5`——所以每组必须独立 `output_dir`，清单校验里 `output_dir` 互不相同是硬性项。train 布局 episode ≥ 10 的 seed 会落进相邻任务的块（`env_block=1000`、`EPISODE_STRIDE=100`），产物与证据按任务分目录，功能上安全，但报告 scope 必须声明。

### 五、并发测试：双卡每卡 12／16／20，对拍与之前一致

**参考是什么。** 改动前的串行参考取 5.8 节已留档的 `20260909-schema3-parallel-v2/runs/S0a/<task>/hdf5_files/`（四任务各 episode 0～3，`BinFill hard ep3` 五轮固定失败，可比 15 条），对应视频在同目录 `videos/`（标准 MP4，`nb_frames` 可读；`BinFill hard ep0` 943 帧）。不再新跑 `S0/S1/P0/P01` 与每卡 2～10 的低档（用户裁定）。

**三档。** `P01x12`／`P01x16`／`P01x20`：`--gpus 0,1 --workers 24／32／40`，每档一次 `--job-manifest` 调用，四组各 episode 0～39（前三任务 hard、`VideoRepick` medium），共 160 job，同一份清单；从低到高跑，某档不通过即停在该档；`P01x20` 排最后，跑前核 `free -g` 与 `df -h /data`。

**校准工具改法** [parallel_calibration.py](tests/_shared/parallel_calibration.py)：
- `MODES` 改为具名结构 `Mode(gpus, workers_per_gpu, role)`，`workers = len(gpus) × workers_per_gpu`；`REFERENCE_MODE="S0a"` 只供 `smoke-off/smoke-on` 退化，保留 `MODES.get` 兜底；`LADDER_MODES` 三档为正式矩阵；`EPISODES=40`、`CASE_COUNT=160`。
- `command_for(root, mode)` 改为生成清单文件 `root/manifests/<mode>.json`（四组 `output_dir=root/runs/<mode>/<task>`）并调用 `--job-manifest`，追加 `--video-check full --video-scope all`；`batch()` 一档一批，`PARITY_EVIDENCE_DIR=root/evidence/<mode>`（观察器证据按 `<task>_seed<seed>/` 分目录，混跑不串）。
- `concurrency()` 从写死"每卡 2、4 条窗口、`itertools.combinations` 穷举"改为按 `first_step_ns`／`last_step_ns` 事件扫描时间线（同一时刻先 end 后 start，相切不算重叠）：产出 `peak_distinct_pids`、`peak_per_gpu`、`peak_overlapping_windows`、`max_common_overlap_s`；判定不同 PID 峰值 ≥ 总 worker、每卡峰值 ≥ 每卡 worker、双卡共同窗口 > 0；窗口条数 = 160。24 条取 20 的组合数会把 `compare` 挂死，扫描是必须项，轻量测试里加 40 条窗口 < 50 ms 的闸门。
- 新增 `compare-baseline --run-id --baseline-run-id 20260909-schema3-parallel-v2 --baseline-mode S0a --episodes 4`：对每个 ladder 档的 episode 0～3 与基线同名 HDF5 `compare_h5` + `compare_evidence`；两侧同缺记 `both_missing`（不计通过）；视频只比帧数（基线 `nb_frames` 对新侧 `video_scope=recorded` 冒烟条；`scope=all` 的档只比 `in_h5=true` 帧数 == `timestep_count`），不比视频散列（编码参数已变）。
- `compare` 三层：`baseline`（15 条 × 3 档）、`cross_tier`（episode 4～39：P01x12↔P01x16、P01x16↔P01x20、P01x12↔P01x20；先比文件 SHA-256，相同即逐位一致，不同才 `compare_h5` 定位首个差异，避免 3 档 × 160 × 0.6 GB 重复读）、`concurrency`。每行新增视频校验：`video.status != complete` 或帧数关系不成立进 `row["errors"]`。`decide` 分母改为 `CASE_COUNT`／基线可比数，模式列表为 `LADDER_MODES`，`passed` 仍严格。`collect_batch` 白名单加 `"video"`，`required` 加 `episodes/video_check/video_scope`。超时 `timeout_for(mode) = 300 + ceil(160/总worker) × 120 × (1 + 0.25×(总worker−2))` 秒（三档约 4500／3800／2400 秒，`--timeout` 显式给值可覆盖）。
- `timeline()` 子图数 = 实跑档数，左泳道按 PID、右侧并发数阶梯图；README 新增"跨 run 基线""档间互比""视频状态计数""吞吐""每档峰值 RSS／显存"表，scope 写明编码路径已变、吞吐不与旧 `P01` 直接比、seed 跨任务不唯一。

**选档。** 在通过 `BASELINE_PARITY`、`CROSS_TIER_PARITY`、`PARALLEL_OVERLAP`、`VIDEO_INDEX`、无 OOM／超时、主机内存峰值低于 300 GB 的档里，取「成功且视频完整的条数 / 批次墙钟」最高的档，另报最大稳定档；三档都不合格就如实报告"双 GPU 要求尚未满足"，不自动改单卡。

资源口径（本机实测）：32 逻辑核、377 GB 内存（swap 7 GB 已满）、两张 46 GB 显卡、`/data` 剩余 2.6 TB；旧 `P01` 每 worker 约 5.2 GB 内存（含将被省掉的帧缓存）、显存约 0.8 GB；40 worker 按旧口径约 209 GB 内存、每卡约 16 GB 显存；每卡 20 时 Python 加 x264 约 80 个可运行线程对 32 核约 2.5 倍超订，吞吐可能在 16 档平台化，实测决定。磁盘：单条 HDF5 0.32～0.72 GB，480 条约 290 GB。

### 六、改动前后链路

```text
关闭态（不传 --job-manifest，--video-scope recorded）：入口 jobs 构造、kwargs、RNG 调用逐字不变；HDF5 逐位相同；视频帧集合与旧路径逐帧相同（帧数 943 == 943），只是编码参数（-threads 1 / -g 30 / 分片）改变了码流字节
开启态（--video-scope all）：视频多出 reset 帧与 NO RECORD 段；HDF5 仍逐位相同（采集条件未动）
清单态（--job-manifest）：jobs 来自清单、按 episode 轮转；每组产物目录与单组调用相同；根目录多一份合并记录
```

| 文件 | 锚点 | 改什么 | 关闭态 | 开启态 |
|---|---|---|---|---|
| `src/robomme/env_record_wrapper/video_stream.py`（新增） | `EpisodeVideoStream.append/finalize/abort/report` | 首帧开流、逐帧写管道、原子改名、错误进状态 | 不被调用 | 残片 `videos/.partial/…pid{pid}.mp4`，分片 MP4 |
| `src/robomme/env_record_wrapper/RecordWrapper.py` | `__init__`、`reset`、`step` 录像分支、`_video_append_step_frame`、`_video_flush_episode_files`、`close` 开头 try、新增五个私有方法、删 `_video_write_mp4` | 第二节表 | `save_video=False` 不开流；`video_scope=recorded` 帧集合同现状 | reset 帧 + 全部步骤 |
| `scripts/generate_dataset_newseed.py` | `_video_summary` 等新函数、`_worker` 尾部、`_synth_failure`、`EpisodeJob` 两字段、`--video-check/--video-scope/--job-manifest`、`_load_job_manifest`、`_run_jobs` 多 sink、`run_summary.json` | 第三、四节 | 不传新 flag 时 jobs 与 parameters 逐字不变 | 视频核验、残片打捞、多组混跑 |
| `tests/_shared/parallel_calibration.py`、`tests/lightweight/test_parallel_calibration.py` | `Mode`、`EPISODES`、`cases`、`command_for`（清单）、`concurrency`（扫描）、`decide`、`timeline`、`collect_batch`、`compare-baseline`、`timeout_for` | 第五节 | — | 三档 × 160 |
| `scripts/README.md`、`AGENTS.md` 账本、`docs/validation/newtask-v2/<编号>/` | 用法、进度表与日志、实测报告 | 实施后更新 | — | — |

### 七、验收判定表

| 判定项 | 查什么 | 判定行 |
|---|---|---|
| `VIDEO_OBSERVER_PARITY` | 冒烟条（`BinFill hard ep0`，单卡单 worker，`--video-scope recorded`）HDF5 与旧 `S0a/BinFill/hdf5_files/BinFill_ep0_seed4000.h5` 用 `compare_h5` 逐位比；视频 `nb_read_frames` 与旧视频 `nb_frames` 相等（943）；再以 `--video-scope all` 跑一次，HDF5 仍逐位相同 | `VIDEO_OBSERVER_PARITY=PASS cases=2 h5_differences=0 recorded_frames=943 baseline_frames=943` |
| `VIDEO_SCOPE` | `scope=all` 冒烟条：帧 0 的旁车 `phase=reset`；`in_h5=false` 帧数 = 1 + `NO RECORD` 步数；`in_h5=true` 帧数 == `timestep_count`；`RouteStick hard ep0` 另跑一条验证 `NO RECORD` 段确实入视频 | `VIDEO_SCOPE=PASS reset_frame=1 no_record_frames=<n> in_h5_frames=<timestep_count>` |
| `VIDEO_DECODE` | 每个交付视频 `ffprobe -count_frames`：`nb_read_frames == frames_written`；`.partial/` 收尾为空；`kill -9` 一条 worker 后残片 `nb_read_frames > 0` | `VIDEO_DECODE=PASS videos=<n> mismatches=0 partial_left=0 crash_partial_decodable=1` |
| `VIDEO_INDEX` | 每条执行记录（成功、失败、合成失败）都有 `video.status`，缺失原因可追溯 | `VIDEO_INDEX=PASS rows=<n> complete=<n> partial=<n> missing=<n> encode_error=<n>` |
| `DEFAULT_PARITY` | 不传 `--job-manifest`、`--video-scope recorded`：`run_parameters.json` 除新增键外逐键相同；jobs 顺序与 seed 相同 | `DEFAULT_PARITY=PASS parameters_diff=0 jobs_diff=0` |
| `MANIFEST_LAYOUT` | 清单模式下每组目录产物集合与单组调用相同；根目录合并记录行数 = 各组之和；`output_dir` 重复、难度非法、`episode_specs` 非空均被拒绝 | `MANIFEST_LAYOUT=PASS groups=4 rows=160 rejected_cases=3` |
| `BASELINE_PARITY` | 每档 episode 0～3 对旧 `S0a`：`compare_h5` 差异 0、`compare_evidence` 通过、`rrt_fallback_count == 0`；`both_missing` 单列 | `BASELINE_PARITY=PASS modes=3 comparable=15 both_missing=1 differences=0`，每档一行 |
| `CROSS_TIER_PARITY` | episode 4～39 三档两两互比 | `CROSS_TIER_PARITY=PASS pairs=<n> comparable=<n> differences=0` |
| `PARALLEL_OVERLAP` | 时间线扫描：不同 PID 峰值 ≥ 总 worker、每卡峰值 ≥ 每卡 worker、双卡共同窗口 > 0、PCI 与卡号一致 | `PARALLEL_OVERLAP=PASS mode=P01x20 peak_distinct_pids=40 per_gpu=20/20 common_overlap_s=<秒>`，每档一行 |
| `PARALLEL_SCALE` | 第五节选档规则 | `PARALLEL_SCALE=PASS chosen=<档> workers_per_gpu=<n> throughput_ep_per_min=<值> peak_rss_gb=<值> highest_stable=<档> highest_failed=<档或 none>` |

为什么能逐位：录像路径不触碰随机流与 HDF5 缓冲；`compare_h5` 遍历全部 group／dataset／attribute，浮点按位模式比、无容差；观察器只包装 `reset/step/close` 三个名字不变的方法。任何样本不得移出分母；某档失败即如实记 `FAIL`，不改写整体通过。

### 八、阶段安排

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 核对授权、`git status` 干净、基线目录 21 个文件与 `context.json` 散列在 | 第二部分红线满足 |
| 1 录像器 | `video_stream.py`、`RecordWrapper.py`、生成入口视频核验与两个 flag；新增轻量测试；短测 ≤ 5 分钟；两条冒烟 | `VIDEO_OBSERVER_PARITY`、`VIDEO_SCOPE`、`VIDEO_DECODE`、`VIDEO_INDEX` |
| 2 清单模式 | `--job-manifest`、`_run_jobs` 多 sink、根目录合并记录；轻量测试；单卡 2 worker 两组各 2 条的最小清单冒烟 | `DEFAULT_PARITY`、`MANIFEST_LAYOUT` |
| 3 并发测试 | 校准工具参数化、时间线扫描、`compare-baseline`；tmux 起三档 480 次；`compare`；报告落 `docs/validation/newtask-v2/<编号>/` | `BASELINE_PARITY`、`CROSS_TIER_PARITY`、`PARALLEL_OVERLAP`、`PARALLEL_SCALE` |
| 4 留档 | `scripts/README.md` 2.6 节、`AGENTS.md` 账本、本文第 8.1 实测追加区；提交并推送 | `git diff --check`、链接与命令核对 |

耗时：阶段 1～2 各约半天代码加 5 分钟内短测与 1～2 分钟冒烟；阶段 3 三档预计 1.5～2.5 小时（每档 160 条 / 24～40 worker 为 4～7 波，旧 `P01` 单条 19～71 秒，编码摊入 step 后单条变慢）加 `compare` 10～30 分钟。执行次数：冒烟 4 + 清单冒烟 4 + 校准 480 = 488 次。

#### 8.1 实施后实测追加区

**尚未执行。** 后续在此追加运行编号、命令、退出码、每档墙钟／吞吐／峰值 RSS／显存／并发峰值、`baseline_comparison.json` 摘要与视频状态计数；不改写上面的目标判据。

## 第二部分（技术细节，供 agent 追踪）

### 〇、前置声明与红线

1. **授权：**本文只规划；阶段 1～4 逐个获批后实施。不启动 workflow。
2. **范围：**录像器只改写入路径与 `video_scope` 开关；帧合成五个函数、四种命名、`reset/step/close` 签名、HDF5 采集条件与写入分支不得改动。生成入口新增项都带默认值，关闭态逐字不变。`NEW_VALUE_INJECTION_TEST_PLAN.md` 本轮不动。
3. **参考：**`artifacts/parallel-calibration/20260909-schema3-parallel-v2/` 只读；不对该编号重跑 `compare`（会覆盖 `docs/validation/newtask-v2/20260909-schema3-parallel-v2/`）；新运行用新编号。
4. **失败：**`--max-attempts 1`，不换 seed、不补样本、不放宽容差；视频失败不改变 `ok`，但进入 `VIDEO_INDEX` 分母。
5. **存储：**全部产物落仓库内 `artifacts/`；HDF5、视频（含 `.partial/` 残片与 `FAILED_PARTIAL_` 打捞件）、日志不入 git。
6. **环境：**`command -v uv`，全部 Python 入口 `uv run --no-sync`；不新增依赖声明（imageio 已随 mani-skill 锁定）。
7. **协作：**提交前 `git status --short`，只 `git add` 本轮明确路径；他人在途文件绕开。
8. **冲突裁定：**第一部分引言块的两条指令冲突按最新指令执行；`AGENTS.md` 不新增「跳过 `NO RECORD`」规则，实施汇报时再次向用户点名。

### 一、按阶段与文件的改动清单

**阶段 1**
- `src/robomme/env_record_wrapper/video_stream.py`（新增）：`EpisodeVideoStream`；`_imageio_factory(path)` 在函数内 `import imageio` 并传 `fps=30, codec="libx264", quality=8, ffmpeg_params=FFMPEG_PARAMS`；测试可注入 `writer_factory`。
- `src/robomme/env_record_wrapper/RecordWrapper.py`：第二节表；`import os`、`from .video_stream import EpisodeVideoStream`；帧索引旁车 `<最终名>.frames.json`（字段 `frame, step, phase ∈ {reset, step, no_record}, task, in_h5`）。
- `scripts/generate_dataset_newseed.py`：第三节；`_worker` 里 `RobommeRecordWrapper(..., save_video=True, video_scope=job.video_scope)`。
- `tests/lightweight/test_record_video_stream.py`（新增，假写入器）：首帧才开流且才建 `.partial/`；无帧不留文件；四种最终名改名；append 异常不吞且后续短路；close 异常保留残片；空 `imageio` 模块优雅降级；对象上无帧列表。
- `tests/lightweight/test_record_video_stream_wiring.py`（新增，AST）：五个冻结方法源码与 `git show HEAD:` 逐字相同；`_video_append_step_frame`／`_video_flush_episode_files` 签名不变；`close()` 里 flush 仍两次且晚于最后一个 `create_dataset`；HDF5 缓冲分支条件仍为 `_video_should_record(current_task)`；不再出现 `video_frames.append`；`_refresh_pending_waypoint` 仍早于 `super().step`。
- `tests/lightweight/test_generator_video_check.py`（新增）：假 ffprobe 六态；`_safe_video_summary` 不抛；打捞改名与 glob 隔离；AST 断言 `ok` 表达式不含 `video`；两个 flag 默认值；`EpisodeJob` 默认字段。

**阶段 2**
- `scripts/generate_dataset_newseed.py`：`_load_job_manifest(path) -> list[GroupSpec]`、`_jobs_from_manifest(groups, layout, task_configs, video_check, video_scope)`（按 episode 轮转）、`_run_jobs(..., sinks: Mapping[str, TextIO])`、`generate_dataset_newseed(job_manifest=None, manifest_root=None)`；`_args` 新增 `--job-manifest`、`--manifest-root`，与 `--env/--episodes/--episode-start/--difficulty/--output-dir` 互斥校验。
- `tests/lightweight/test_job_manifest.py`（新增）：合法清单解析与轮转顺序；`output_dir` 重复／越出仓库／符号链接、难度非法、`episode_specs` 非空、与 `--env` 同给均拒绝；关闭态 `jobs` 与 `parameters` 逐字不变（对照 `git show HEAD:` 版本构造的期望）。

**阶段 3**
- `tests/_shared/parallel_calibration.py`：第五节；`compare-baseline` 子命令；`main()` `choices=("run","compare","compare-baseline")`，`--baseline-run-id` 默认 `20260909-schema3-parallel-v2`，`--timeout` 默认 `None` 走 `timeout_for`。
- `tests/lightweight/test_parallel_calibration.py`：`16/4/{0..3}/("S1","P0","P01")` 改由模块常量推导并 `monkeypatch` `EPISODES=4`；`windows()` 按 `(workers_per_gpu, gpus)` 生成；新增时间线扫描（峰值精确值、相切不算重叠、40 条窗口 < 50 ms）、`timeout_for`、清单命令生成、`compare-baseline` 分桶与 `nb_read_frames`、视频状态使行 `valid=False` 的用例。

**阶段 4**
- `scripts/README.md` 2.6 节命令模板；`AGENTS.md` 当前进度表与执行日志；本文 8.1 节。

### 二、对拍闸门总表

| 闸门 | 输入与比较双方 | 必须覆盖的反例 | 判定 |
|---|---|---|---|
| 录像写入 | 冒烟条对旧 `S0a` 同名 HDF5；视频帧数对旁车与 `timestep_count` | 帧合成被改、`NO RECORD` 条件误入 HDF5 分支、编码异常被吞、`nb_frames` N/A 当 0、残片未打捞、跨 reset 尺寸变化 | `VIDEO_OBSERVER_PARITY`、`VIDEO_SCOPE`、`VIDEO_DECODE`、`VIDEO_INDEX` |
| 清单模式 | 清单调用对单组调用的目录产物；关闭态对 HEAD 版本 | 同名 `.h5` 覆盖、组目录重复、难度串组、轮转顺序被打乱、根记录漏行 | `DEFAULT_PARITY`、`MANIFEST_LAYOUT` |
| 三档并发 | 每档 0～3 对旧 `S0a`；4～39 档间；时间线扫描 | 少产物、不同 timestep、数值差异、规划回退、只有排队／编码重叠、OOM 记成通过、组合穷举挂死 | `BASELINE_PARITY`、`CROSS_TIER_PARITY`、`PARALLEL_OVERLAP`、`PARALLEL_SCALE` |

### 三、运行手册

短测（阶段 1、2 各自 ≤ 5 分钟）：

```bash
command -v uv
uv run --no-sync python -m pytest tests/lightweight/test_record_video_stream.py tests/lightweight/test_record_video_stream_wiring.py tests/lightweight/test_generator_video_check.py tests/lightweight/test_job_manifest.py tests/lightweight/test_parallel_calibration.py tests/lightweight/test_record_video_metadata_fields.py tests/lightweight/test_record_waypoint_pending_flow.py tests/lightweight/test_record_info_is_completed.py tests/lightweight/test_step_error_handling.py tests/lightweight/test_native_sampling_config.py -q
git diff -U0 src/robomme/env_record_wrapper/RecordWrapper.py | grep -n "_video_should_record\|_video_prepare_step_frames\|_video_compose_planner_online_rows\|_video_apply_overlays\|_video_build_filename_parts"
```

预期第二条只命中上下文行；余下预算补 `tests/lightweight/` 全量，旧 4 个固定失败单列。

阶段 1 冒烟（单卡单 worker，两条各约 1 分钟）：

```bash
command -v uv
SMOKE="artifacts/parallel-calibration/video-stream-smoke-$(date -u +%Y%m%dT%H%M%SZ)"
uv run --no-sync python scripts/generate_dataset_newseed.py --output-dir "$SMOKE/recorded" --env BinFill --episodes 1 --episode-start 0 --difficulty 001 --gpus 0 --workers 1 --layout train --max-attempts 1 --max-tasks-per-child 8 --affinity none --sampling-config scripts/configs/newtask-v2/native_sampling.json --video-check full --video-scope recorded
uv run --no-sync python scripts/generate_dataset_newseed.py --output-dir "$SMOKE/all" --env BinFill --episodes 1 --episode-start 0 --difficulty 001 --gpus 0 --workers 1 --layout train --max-attempts 1 --max-tasks-per-child 8 --affinity none --sampling-config scripts/configs/newtask-v2/native_sampling.json --video-check full --video-scope all
for d in recorded all; do uv run --no-sync python -m tests._shared.native_sampling_parity compare --reference artifacts/parallel-calibration/20260909-schema3-parallel-v2/runs/S0a/BinFill --candidate "$SMOKE/$d"; done
ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$SMOKE"/recorded/videos/BinFill_ep0_seed4000_*.mp4
```

判定：两次 `compare` 差异均为 0；`recorded` 帧数 943；`all` 的旁车 `in_h5=true` 帧数 943、帧 0 `phase=reset`；两目录 `videos/.partial/` 为空；`episode_results.jsonl` 的 `video.status` 为 `complete`；`peak_rss_mb` 不高于旧基线同条 5302。崩溃残片：另起一条，在 solve 阶段对 worker `kill -9`，`ffprobe -count_frames` 残片读出大于 0 帧。

阶段 3 三档校准（tmux 起、Monitor 只挂一份日志）：

```bash
command -v uv
mkdir -p artifacts/logs
df -h /data; free -g
PARALLEL_RUN_ID="schema3-parallel-v3-$(date -u +%Y%m%dT%H%M%SZ)"
tmux new-session -d -s "$PARALLEL_RUN_ID" \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m tests._shared.parallel_calibration run --run-id $PARALLEL_RUN_ID --baseline-run-id 20260909-schema3-parallel-v2 2>&1 | tee artifacts/logs/$PARALLEL_RUN_ID.log; code=\$?; echo EXIT_CODE=\$code | tee -a artifacts/logs/$PARALLEL_RUN_ID.log; exit \$code"
tmux has-session -t "$PARALLEL_RUN_ID"
```

Monitor：`tail -n +1 -F artifacts/logs/$PARALLEL_RUN_ID.log | stdbuf -oL tr '\r' '\n' | grep --line-buffered -E "EXIT_CODE=|Traceback|Error|out of memory|批次|passed"`。`run` 顺序固定 `smoke-off → smoke-on → P01x12 → P01x16 → P01x20`；`P01x20` 开跑前 `free -g` 可用低于 60 GB 或 `/data` 余量低于 150 GB 即不起该档。结束后：

```bash
uv run --no-sync python -m tests._shared.parallel_calibration compare-baseline --run-id "$PARALLEL_RUN_ID" --baseline-run-id 20260909-schema3-parallel-v2 --baseline-mode S0a --episodes 4
uv run --no-sync python -m tests._shared.parallel_calibration compare --run-id "$PARALLEL_RUN_ID"
```

### 四、风险登记

| 风险 | 识别方式 | 处置 |
|---|---|---|
| 录像改动误伤帧合成或 HDF5 采集条件 | AST 测试逐字比对五个方法与 HDF5 分支条件；冒烟对旧 `S0a` 逐位比 | 任何差异即回退 |
| reset 帧合成时分割结果为空导致合成函数报错 | 阶段 1 冒烟第一步就会暴露 | 传空掩码与 `-1` 任务索引；仍报错则 reset 帧只放主相机与腕部相机两块并记入旁车，不改合成函数 |
| 分片 MP4 的 `nb_frames` 为 N/A | 全仓 grep `nb_frames` | 新代码一律 `-count_frames`；读不到记 `probe_unavailable` |
| 每卡 20 worker 时 CPU 超订、内存逼近 209 GB、swap 已满 | 每档进程组 RSS、`free -g`、显存采样；OOM 触发 `BrokenProcessPool` 重建 | `-threads 1` 保留；`P01x20` 最后跑、跑前核余量；OOM 档记失败，退回已通过档 |
| ffprobe 数帧收尾拖慢下一波 | 每档 `close_s` 与墙钟对比 | 可把校准 `--video-check` 降为 `frames` |
| 清单模式同名 `.h5` 覆盖 | 清单校验 `output_dir` 互不相同 | 拒绝启动 |
| 参考只覆盖 15/160 | `BASELINE_PARITY` 分母写 15 | 4～39 只证明三档互相一致，报告限定语必须写 |
| 用户两条指令冲突 | 引言块已点名 | `video_scope` 开关两种口径都可跑；AGENTS.md 规则待裁定 |

### 五、盲区诚实清单

- 视频「完整」指 reset 帧、每个 step（含 `NO RECORD`）各一帧、写入一帧不丢、崩溃后已写帧可解码；不含规划器内部子步与物理子步图像。
- 串行参考只有 episode 0～3 的 15 条；4～39 没有串行参考；改动后吞吐与旧 `P01` 不能直接比。
- 未跑的规划回退、其他硬件／驱动组合不算已覆盖；视频文件存在不等于已人工观看。
- 本文未执行任何命令，第 8.1 节为空。

### 六、留档与提交纪律

重产物按 `artifacts/parallel-calibration/<运行编号>/`（`manifests/`、`runs/<档>/<任务>/`、`evidence/<档>/`、`logs/`、`baseline_comparison.json`、`comparison.json`）；轻量包 `docs/validation/newtask-v2/<运行编号>/`（中文 README、`parallel_result.json`、`baseline_comparison.json`、时间线图、视频状态计数、命令与退出码、环境指纹）。提交按 `AGENTS.md` 规则 7：只 `git add` 本轮明确路径，中文 subject 沿用 `10.<小版本>` 体例，body 含用户原话、完整计划、过程、意外、实测与下一步；每次提交后 `git push`。
