# 新值注入专项实测报告 · 20260912-contract-v3-09

生成时间（UTC）：2026-09-12T16:08:23Z

> 本报告由 `scripts.injection.campaign report` 从各阶段的原始产物汇总，
> 数字均为实测。重产物（HDF5、视频、PNG）留在 `artifacts/injection/` 原地，
> 这里只存路径、帧数与 SHA-256。

## 一、判定行

| 判定项 | 结果 | 关键数字 |
|---|---|---|
| `SPEC_SCOPE` | PASS | groups=14 specs=1400 excluded=VideoRepick-hard problems=0 |
| `CONTRACT_DERIVED` | PASS | fields=200 mismatches=6 overrides=2 version=v3 problems=0 |
| `COVERAGE_QUOTA` | PASS | groups=14 batches=10 quota_gaps=0 |
| `STATIC_GEOMETRY` | PASS | checked=1400 rejected=0 |
| `COLLISION_GEOMETRY` | PASS | bin_shapes=6 cube_shapes=1 four_object_pairs=6 note=真实-actor-对照在步骤2冒烟 |
| `COLLISION_SWEEP` | PASS | specs=700 rejected=0 uncertified=0 min_g_m=0.000141418 |
| `SPEC_REPRODUCIBLE` | PASS | compared=1400 differences=0 |
| `FEASIBILITY` | PASS | unique=20 executed=20 unclassified=0 succeeded=20 attempt=0 |
| `RESULT_COVERAGE` | PASS | all_recorded=20 all_success=20 |
| `VIDEO_INDEX` | PASS | rows=20 complete=20 frame_mismatch=0 missing=0 no_close=0 untraceable=0 |
| `COLLISION_RUNTIME` | PASS | unique=0 checked=0 missing_checks=0 rejected=0 scope=0_video_groups |
| `INJECTION_BINDING` | PASS | unique=20 bound=20 mismatches=0 |
| `VIDEO_DECODE` | PASS | success_rows=20 decoded_eq_timesteps=20 failed_videos=0 mismatches=0 |
| `DELIVERY` | PASS | specs=1400 result_rows=20 missing=0 videos_on_disk=20 videos_expected=20 video_sha_mismatch=0 |

## 二、实跑 20 条的七类结果

| 结果 | 条数 |
|---|---:|
| 通过 | 20 |

### 每组明细

| 组 | 通过 |
|---|---|
| RouteStick/easy | 5 |
| RouteStick/medium | 5 |
| RouteStick/hard | 5 |
| RouteStick/xhard | 5 |

## 三、视频状态

| 状态 | 条数 |
|---|---:|
| `complete` | 20 |

## 六、规格清单散列

| 组 | 条数 | 文件 SHA-256（前 16 位） | 与清单一致 |
|---|---:|---|---|
| BinFill/easy | 100 | `7e37c47a66d41e1d…` | 是 |
| BinFill/medium | 100 | `21d641425ce488c3…` | 是 |
| BinFill/hard | 100 | `3e5e2f4b0b2f8b23…` | 是 |
| RouteStick/easy | 100 | `0326ac3985d16643…` | 是 |
| RouteStick/medium | 100 | `20b2357135a7eaf9…` | 是 |
| RouteStick/hard | 100 | `d4a58a7cc52fdb6c…` | 是 |
| VideoUnmaskSwap/easy | 100 | `f8762b6a314e01e0…` | 是 |
| VideoUnmaskSwap/medium | 100 | `99d9dd1a1c8e3f82…` | 是 |
| VideoUnmaskSwap/hard | 100 | `d75cf35a19b25dad…` | 是 |
| VideoRepick/easy | 100 | `df6dc1ca7e7929fa…` | 是 |
| VideoRepick/medium | 100 | `13377394012728e4…` | 是 |
| RouteStick/xhard | 100 | `8f458b81d8550ace…` | 是 |
| VideoUnmaskSwap/xhard | 100 | `20f68f87abf0a864…` | 是 |
| VideoRepick/xhard | 100 | `ed0ee3bbcefa187d…` | 是 |
