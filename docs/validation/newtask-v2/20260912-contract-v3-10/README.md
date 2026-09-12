# 新值注入专项实测报告 · 20260912-contract-v3-10

生成时间（UTC）：2026-09-12T19:30:13Z

> 本报告由 `scripts.injection.campaign report` 从各阶段的原始产物汇总，
> 数字均为实测。重产物（HDF5、视频、PNG）留在 `artifacts/injection/` 原地，
> 这里只存路径、帧数与 SHA-256。

## 一、判定行

| 判定项 | 结果 | 关键数字 |
|---|---|---|
| `SPEC_SCOPE` | PASS | groups=14 specs=3400 blocks=2/3 excluded=VideoRepick-hard problems=0 |
| `CONTRACT_DERIVED` | PASS | fields=200 mismatches=6 overrides=2 version=v3 problems=0 |
| `COVERAGE_QUOTA` | PASS | groups=14 batches=10 blocks=2/3 quota_gaps=0 |
| `STATIC_GEOMETRY` | PASS | checked=3400 rejected=0 |
| `COLLISION_GEOMETRY` | PASS | bin_shapes=6 cube_shapes=1 four_object_pairs=6 note=真实-actor-对照在步骤2冒烟 |
| `COLLISION_SWEEP` | PASS | specs=1700 rejected=0 uncertified=0 min_g_m=1.4025e-05 |
| `SPEC_REPRODUCIBLE` | PASS | compared=3400 differences=0 |
| `FEASIBILITY` | PASS | unique=1842 executed=1842 unclassified=0 succeeded=1796 attempt=0 |
| `RESULT_COVERAGE` | PASS | all_recorded=1842 all_success=1796 |
| `VIDEO_INDEX` | PASS | rows=1842 complete=1818 frame_mismatch=3 missing=0 no_close=21 untraceable=0 |
| `COLLISION_RUNTIME` | PASS | unique=921 checked=900 missing_checks=0 rejected=1 scope=7_video_groups |
| `INJECTION_BINDING` | PASS | unique=1842 bound=1821 mismatches=0 |
| `VIDEO_DECODE` | PASS | success_rows=1796 decoded_eq_timesteps=1796 failed_videos=22 mismatches=0 |
| `ENV_RESET` | PASS | group=BinFill/easy start=155 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=BinFill/medium start=153 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=BinFill/hard start=153 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=RouteStick/easy start=115 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=RouteStick/medium start=115 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=RouteStick/hard start=115 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=VideoUnmaskSwap/easy start=115 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=VideoUnmaskSwap/medium start=115 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=VideoUnmaskSwap/hard start=115 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=VideoRepick/easy start=155 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=VideoRepick/medium start=153 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=RouteStick/xhard start=115 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=VideoUnmaskSwap/xhard start=115 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_RESET` | PASS | group=VideoRepick/xhard start=153 checked=50 passed=50 failed=0 delivered=50 |
| `ENV_CHECK` | PASS | groups=14 checked=700 passed=700 delivered=700 shortfall=0 |
| `DELIVERY_400` | PASS | env=BinFill target=400 delivered=400 spare=38 failed=23 groups=3 |
| `DELIVERY_400` | PASS | env=RouteStick target=400 delivered=400 spare=60 failed=0 groups=4 |
| `DELIVERY_400` | PASS | env=VideoUnmaskSwap target=400 delivered=400 spare=58 failed=2 groups=4 |
| `DELIVERY_400` | PASS | env=VideoRepick target=400 delivered=400 spare=40 failed=21 groups=3 |
| `DELIVERY_TOTAL` | PASS | envs=4 delivered=1600 spare=196 h5_missing=0 h5_sha_mismatch=0 |
| `DELIVERY` | PASS | specs=3400 result_rows=1842 missing=0 videos_on_disk=1821 videos_expected=1821 video_sha_mismatch=0 |

## 二、实跑 1842 条的七类结果

| 结果 | 条数 |
|---|---:|
| 通过 | 1796 |
| 规划失败 | 21 |
| 未运行 | 3 |
| 超时 | 21 |
| 碰撞拒绝 | 1 |

### 每组明细

| 组 | 通过 | 规划失败 | 未运行 | 超时 | 碰撞拒绝 |
|---|---|---|---|---|---|
| BinFill/easy | 150 | 3 | 2 | 0 | 0 |
| BinFill/medium | 149 | 4 | 0 | 0 | 0 |
| BinFill/hard | 139 | 13 | 1 | 0 | 0 |
| RouteStick/easy | 115 | 0 | 0 | 0 | 0 |
| RouteStick/medium | 115 | 0 | 0 | 0 | 0 |
| RouteStick/hard | 115 | 0 | 0 | 0 | 0 |
| VideoUnmaskSwap/easy | 115 | 0 | 0 | 0 | 0 |
| VideoUnmaskSwap/medium | 115 | 0 | 0 | 0 | 0 |
| VideoUnmaskSwap/hard | 115 | 0 | 0 | 0 | 0 |
| VideoRepick/easy | 150 | 0 | 0 | 5 | 0 |
| VideoRepick/medium | 146 | 0 | 0 | 7 | 0 |
| RouteStick/xhard | 115 | 0 | 0 | 0 | 0 |
| VideoUnmaskSwap/xhard | 113 | 0 | 0 | 2 | 0 |
| VideoRepick/xhard | 144 | 1 | 0 | 7 | 1 |

### 失败样本的 error_type 分布

> ⚠ 「规划失败」一类混装三种来源：`ScrewPlanFailure`／`PlannerExhausted`（规划无解）、
> `SceneGenerationError`（场景生成失败）、`DatasetGenerationError`（环境判定任务失败）。
> 七类状态按计划互斥、不加第八类，但这里把 `error_type` 分开列，避免一个数字掩盖三种失败。

| error_type | 条数 |
|---|---:|
| `DatasetGenerationError` | 21 |
| `EpisodeWallClockTimeout` | 21 |
| `BinFillDemoError` | 3 |
| `BinCollisionError` | 1 |

## 三、视频状态

| 状态 | 条数 |
|---|---:|
| `complete` | 1818 |
| `frame_mismatch` | 3 |
| `no_close` | 21 |

## 三·一、严格交付（每 env 400 条，按 episode 序取前 N 条通过为正式）

| env | 目标 | 交付 | spare | 失败 | 组数 |
|---|---:|---:|---:|---:|---:|
| BinFill | 400 | 400 | 38 | 23 | 3 |
| RouteStick | 400 | 400 | 60 | 0 | 4 |
| VideoUnmaskSwap | 400 | 400 | 58 | 2 | 4 |
| VideoRepick | 400 | 400 | 40 | 21 | 3 |

| 组 | 目标 | 实跑 | 结果行 | 通过 | 交付 | spare | 失败 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BinFill/easy | 134 | 155 | 155 | 150 | 134 | 16 | 5 |
| BinFill/medium | 133 | 153 | 153 | 149 | 133 | 16 | 4 |
| BinFill/hard | 133 | 153 | 153 | 139 | 133 | 6 | 14 |
| RouteStick/easy | 100 | 115 | 115 | 115 | 100 | 15 | 0 |
| RouteStick/medium | 100 | 115 | 115 | 115 | 100 | 15 | 0 |
| RouteStick/hard | 100 | 115 | 115 | 115 | 100 | 15 | 0 |
| VideoUnmaskSwap/easy | 100 | 115 | 115 | 115 | 100 | 15 | 0 |
| VideoUnmaskSwap/medium | 100 | 115 | 115 | 115 | 100 | 15 | 0 |
| VideoUnmaskSwap/hard | 100 | 115 | 115 | 115 | 100 | 15 | 0 |
| VideoRepick/easy | 134 | 155 | 155 | 150 | 134 | 16 | 5 |
| VideoRepick/medium | 133 | 153 | 153 | 146 | 133 | 13 | 7 |
| RouteStick/xhard | 100 | 115 | 115 | 115 | 100 | 15 | 0 |
| VideoUnmaskSwap/xhard | 100 | 115 | 115 | 113 | 100 | 13 | 2 |
| VideoRepick/xhard | 133 | 153 | 153 | 144 | 133 | 11 | 9 |

## 三·二、额外候选 env-check（只 make + reset + close，零产物）

> 本核验只覆盖 gym.make + 一次 env.reset()（即 _load_scene 与 _initialize_episode，含两个视频任务在 _initialize_episode 里对实际 actor 初态所做的碰撞复核）；不套 RobommeRecordWrapper、不建 planner、不 step，因此不覆盖 step 期的 SpecBindingError、规划可解性（螺旋／RRT* 能否解出轨迹）、录像器的步数保护与任务成功判定。结论只到「该候选能产生环境」为止：reset 通过 ≠ 能出 h5。

| 组 | 起点 | 核验 | 通过 | 失败 | 交付 | 缺口 |
|---|---:|---:|---:|---:|---:|---:|
| BinFill/easy | 155 | 50 | 50 | 0 | 50 | 0 |
| BinFill/medium | 153 | 50 | 50 | 0 | 50 | 0 |
| BinFill/hard | 153 | 50 | 50 | 0 | 50 | 0 |
| RouteStick/easy | 115 | 50 | 50 | 0 | 50 | 0 |
| RouteStick/medium | 115 | 50 | 50 | 0 | 50 | 0 |
| RouteStick/hard | 115 | 50 | 50 | 0 | 50 | 0 |
| VideoUnmaskSwap/easy | 115 | 50 | 50 | 0 | 50 | 0 |
| VideoUnmaskSwap/medium | 115 | 50 | 50 | 0 | 50 | 0 |
| VideoUnmaskSwap/hard | 115 | 50 | 50 | 0 | 50 | 0 |
| VideoRepick/easy | 155 | 50 | 50 | 0 | 50 | 0 |
| VideoRepick/medium | 153 | 50 | 50 | 0 | 50 | 0 |
| RouteStick/xhard | 115 | 50 | 50 | 0 | 50 | 0 |
| VideoUnmaskSwap/xhard | 115 | 50 | 50 | 0 | 50 | 0 |
| VideoRepick/xhard | 153 | 50 | 50 | 0 | 50 | 0 |

## 五、失败样本清单（保留在分母里，不换 seed、不补位）

| 组 | episode | 任务结果 | 执行状态 | error_type | 视频状态 |
|---|---:|---|---|---|---|
| BinFill/easy | 10 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/easy | 83 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/easy | 125 | 未运行 | code_error | `BinFillDemoError` | `frame_mismatch` |
| BinFill/easy | 146 | 未运行 | code_error | `BinFillDemoError` | `frame_mismatch` |
| BinFill/easy | 151 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 4 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 23 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 28 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 31 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 32 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 38 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 45 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 58 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 65 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 90 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 93 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 117 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 130 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/hard | 152 | 未运行 | code_error | `BinFillDemoError` | `frame_mismatch` |
| BinFill/medium | 30 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/medium | 32 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/medium | 128 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| BinFill/medium | 132 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| VideoRepick/easy | 0 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/easy | 26 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/easy | 46 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/easy | 125 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/easy | 148 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/medium | 26 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/medium | 39 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/medium | 44 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/medium | 76 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/medium | 91 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/medium | 114 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/medium | 137 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/xhard | 5 | 规划失败 | completed | `DatasetGenerationError` | `complete` |
| VideoRepick/xhard | 49 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/xhard | 50 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/xhard | 68 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/xhard | 70 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/xhard | 83 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/xhard | 100 | 碰撞拒绝 | completed | `BinCollisionError` | `complete` |
| VideoRepick/xhard | 106 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoRepick/xhard | 145 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoUnmaskSwap/xhard | 7 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |
| VideoUnmaskSwap/xhard | 26 | 超时 | timeout | `EpisodeWallClockTimeout` | `no_close` |

## 六、规格清单散列

| 组 | 条数 | 文件 SHA-256（前 16 位） | 与清单一致 |
|---|---:|---|---|
| BinFill/easy | 300 | `25c52a1405512b9f…` | 是 |
| BinFill/medium | 300 | `cdb3b769a268d648…` | 是 |
| BinFill/hard | 300 | `a19d2798e709202f…` | 是 |
| RouteStick/easy | 200 | `c04f78600c5dfd0f…` | 是 |
| RouteStick/medium | 200 | `d6899725fac49658…` | 是 |
| RouteStick/hard | 200 | `3fc4dfc93a3010d1…` | 是 |
| VideoUnmaskSwap/easy | 200 | `a8ed36e26c5ae331…` | 是 |
| VideoUnmaskSwap/medium | 200 | `3d34e62bb6335597…` | 是 |
| VideoUnmaskSwap/hard | 200 | `bb53c988510bb416…` | 是 |
| VideoRepick/easy | 300 | `c27c0f6459a0d5e7…` | 是 |
| VideoRepick/medium | 300 | `3566b84299134343…` | 是 |
| RouteStick/xhard | 200 | `aba58631cceffd2a…` | 是 |
| VideoUnmaskSwap/xhard | 200 | `484f5803e43f81eb…` | 是 |
| VideoRepick/xhard | 300 | `4e581d9bf458ebee…` | 是 |
