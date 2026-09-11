# 新值注入专项实测报告 · 20260910-new-values-04

生成时间（UTC）：2026-09-11T03:53:44Z

> 本报告由 `tests._shared.injection_campaign report` 从各阶段的原始产物汇总，
> 数字均为实测。重产物（HDF5、视频、PNG）留在 `artifacts/injection/` 原地，
> 这里只存路径、帧数与 SHA-256。

## 一、判定行

| 判定项 | 结果 | 关键数字 |
|---|---|---|
| `SPEC_SCOPE` | PASS | groups=11 specs=1100 excluded=VideoRepick-hard problems=0 |
| `COVERAGE_QUOTA` | PASS | groups=11 batches=10 quota_gaps=0 |
| `STATIC_GEOMETRY` | PASS | checked=1100 rejected=0 |
| `COLLISION_GEOMETRY` | PASS | bin_shapes=6 cube_shapes=1 four_object_pairs=6 note=真实-actor-对照在步骤2冒烟 |
| `COLLISION_SWEEP` | PASS | specs=500 rejected=0 uncertified=0 min_g_m=0.00042638 |
| `SPEC_REPRODUCIBLE` | PASS | compared=1100 differences=0 |
| `SERIAL_REFERENCE` | PASS | unique=16 comparable=16 both_failed=0 differences=0 |
| `PARALLEL_SCALE` | NOT_RUN | reason=档位校准被跳过 |
| `FEASIBILITY` | PASS | unique=330 executed=330 unclassified=0 succeeded=322 attempt=0 |
| `RESULT_COVERAGE` | PASS | all_recorded=330 all_success=322 |
| `VIDEO_INDEX` | PASS | rows=330 complete=327 frame_mismatch=0 missing=0 no_close=3 untraceable=0 |
| `COLLISION_RUNTIME` | PASS | unique=150 checked=147 missing_checks=0 rejected=0 |
| `INJECTION_BINDING` | PASS | unique=330 bound=327 mismatches=0 |
| `VIDEO_DECODE` | PASS | success_rows=322 decoded_eq_timesteps=322 failed_videos=5 mismatches=0 |
| `DEFAULT_PARITY` | PASS | cases=8 differences=0 note=关闭注入·基线446455b对b1dd02a·4任务各easy+medium evidence=artifacts/injection/20260910-new-values-02/parity/default_parity.json |
| `SMOKE` | PASS | episodes=4 attempt=0 observer_differences=0 note=BinFill98.6s/RouteStick47.0s/VideoRepick37.4s/VideoUnmaskSwap42.4s·视频帧数全等于timestep数 evidence=artifacts/injection/20260910-new-values-02/smoke 与 smoke-video；04/evidence-smoke |
| `COLLISION_REPRODUCE` | PASS | cases=9 accepted=6 rejected=3 original_unchanged=1 max_pose_diff_m=6.32e-09 mode=trajectory evidence=artifacts/collision-replay/20260910-bin-contact-replay-01/replay_result.json |
| `COLLISION_RERENDER` | NOT_RUN | reason=从保存轨迹重渲染需要SAPIEN渲染·本轮未做 |
| `PLOT_EVIDENCE` | PASS | groups=11 before=11 after=11 thumbnails=1100 font=Noto Sans CJK JP |
| `PARALLEL_CONTENT` | PASS | unique=16 differences=0 note=实跑12worker对S0a单worker |
| `PARALLEL_OVERLAP` | FAIL | mode=P0x12 gpus=1 workers_per_gpu=12 peak_distinct_pids=11 samples=322 |
| `DELIVERY` | PASS | specs=1100 result_rows=330 missing=0 videos_on_disk=327 videos_expected=327 video_sha_mismatch=0 |

## 二、实跑 330 条的七类结果

| 结果 | 条数 |
|---|---:|
| 通过 | 322 |
| 规划失败 | 5 |
| 未运行 | 3 |

### 每组明细

| 组 | 通过 | 规划失败 | 未运行 |
|---|---|---|---|
| BinFill/easy | 29 | 1 | 0 |
| BinFill/medium | 28 | 2 | 0 |
| BinFill/hard | 28 | 2 | 0 |
| RouteStick/easy | 30 | 0 | 0 |
| RouteStick/medium | 30 | 0 | 0 |
| RouteStick/hard | 30 | 0 | 0 |
| VideoUnmaskSwap/easy | 30 | 0 | 0 |
| VideoUnmaskSwap/medium | 30 | 0 | 0 |
| VideoUnmaskSwap/hard | 30 | 0 | 0 |
| VideoRepick/easy | 28 | 0 | 2 |
| VideoRepick/medium | 29 | 0 | 1 |

### 失败样本的 error_type 分布

> ⚠ 「规划失败」一类混装三种来源：`ScrewPlanFailure`／`PlannerExhausted`（规划无解）、
> `SceneGenerationError`（场景生成失败）、`DatasetGenerationError`（环境判定任务失败）。
> 七类状态按计划互斥、不加第八类，但这里把 `error_type` 分开列，避免一个数字掩盖三种失败。

| error_type | 条数 |
|---|---:|
| `DatasetGenerationError` | 5 |
| `BrokenProcessPool` | 3 |

## 三、视频状态

| 状态 | 条数 |
|---|---:|
| `complete` | 327 |
| `no_close` | 3 |

## 五、失败样本清单（保留在分母里，不换 seed、不补位）

| 组 | episode | 任务结果 | 执行状态 | error_type | 视频状态 |
|---|---:|---|---|---|---|
| BinFill/easy | 10 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 5 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 10 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/medium | 14 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/medium | 15 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| VideoRepick/easy | 0 | 未运行 | infra_error | `BrokenProcessPool` | `no_close` |
| VideoRepick/easy | 26 | 未运行 | infra_error | `BrokenProcessPool` | `no_close` |
| VideoRepick/medium | 26 | 未运行 | infra_error | `BrokenProcessPool` | `no_close` |

## 六、规格清单散列

| 组 | 条数 | 文件 SHA-256（前 16 位） | 与清单一致 |
|---|---:|---|---|
| BinFill/easy | 100 | `dcf3c632641ca9fe…` | 是 |
| BinFill/medium | 100 | `63e57fb547228d5e…` | 是 |
| BinFill/hard | 100 | `173263863b5fa222…` | 是 |
| RouteStick/easy | 100 | `8314da95d6614ad5…` | 是 |
| RouteStick/medium | 100 | `fa9549212f2d430b…` | 是 |
| RouteStick/hard | 100 | `8d4e9b599f088c99…` | 是 |
| VideoUnmaskSwap/easy | 100 | `fa6ead0a1cc47bcc…` | 是 |
| VideoUnmaskSwap/medium | 100 | `4f55c70b11a7b95c…` | 是 |
| VideoUnmaskSwap/hard | 100 | `11abe394c3a16abf…` | 是 |
| VideoRepick/easy | 100 | `6d374fd6148ff5ab…` | 是 |
| VideoRepick/medium | 100 | `904fd666ac0cb04e…` | 是 |
