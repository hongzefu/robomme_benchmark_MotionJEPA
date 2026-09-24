# V5 总报告：xhard 档去扎堆、Unmask 外环加密并随内环交换、演示时长校准（2026-09-24 一夜实施）

> 计划：[NEWTASK_RELEASE_V5_PLAN.md](../../../NEWTASK_RELEASE_V5_PLAN.md)（L1～L54 全部已由用户答复）。分支 `newtaskRelease-v5`，提交 12.117～12.13x。
> 实施方式：主会话编排，opus subagent 在独立 git worktree 并行实现（未启动 workflow），主会话逐组审核、合并、复测、提交。
> 全部在本机（2× RTX 6000 Ada）跑；两个 GL 占位 job 未使用，收尾已释放。

## 一、结论先行

| 闸门 / 报告 | 判定行 | 结论 |
|---|---|---|
| V0 原三档定义 | 每步 `git diff` 中 `config_easy/medium/hard` 与原三档 `NATIVE_SAMPLING` 零改动；新快照剥掉全部 xhard 键后 16 环境与 V4 快照逐字相同 | PASS |
| LIGHTWEIGHT | 最终 46 failed / 1347 passed / 12 errors，失败集合与 S0 基线 58 条逐条相同 | PASS |
| SAMPLING_SNAPSHOT | `SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0` | PASS |
| **V1（唯一对拍）** | `NATIVE_REGRESSION=PASS`：`H5_PARITY pair=base.B\|v5.B compared=144 sha_equal=144 field_mismatch=0` | **PASS**（144/144 整文件 SHA-256 相同） |
| FROZEN_FILES | 录像器与 12.116 无差异；`scripts/*.py` 恰 5 个 | PASS |
| 生成报告 | `V5_GENERATION=REPORT tasks=16 draft_ok=160 rollout_ok=48 backfilled=2 selected_shortfall=0 demo_frames_out_of_band=0 outer_swap_mismatch=0 bin_collision=0 vr_min_participants=6` | 16 环境全部攒够 10 候选与 3 正式局 |

## 二、提交一览

| 提交 | 内容 | 逐步报告 |
|---|---|---|
| 12.117 | S2a 精确方块 OBB、`spawn_random_*` 显式中心规则参数、七环境异常类别名 | 20260924-s2a-shared-sampling-and-scenegen.md |
| 12.118 | S2b 多对联合扫掠证明与认证预筛 | 20260924-s2b-multi-swap-sweep.md |
| 12.119 | S2c Unmask 统一干扰采样器与独立停放点 | 20260924-s2c-unmask-distractor-sampler.md |
| 12.120 | 工具链：抽签多 worker、快照按 release 导出、一条命令流水线与生成报告 | 20260924-tools-draw-rollout-report.md |
| 12.121 | S3d InsertPeg | 20260924-s3d-insertpeg.md |
| 12.122 | S3b VideoUnmask / ButtonUnmask | 20260924-s3b-videounmask-buttonunmask.md |
| 12.123 | S3e BinFill | 20260924-s3e-binfill.md |
| 12.124 | S3i PickHighlight / VideoPlaceButton / VideoPlaceOrder（障碍框），StopCube 核对 | 20260924-s3i-obb-fix-pickhighlight-videoplace.md |
| 12.125 | S3c MoveCube | 20260924-s3c-movecube.md |
| 12.126 | S3a PatternLock / RouteStick | 20260924-s3a-patternlock-routestick.md |
| 12.127 | S3f PickXtimes / SwingXtimes | 20260924-s3f-pickxtimes-swingxtimes.md |
| 12.128 | S3h VideoUnmaskSwap / ButtonUnmaskSwap | 20260924-s3h-unmaskswap.md |
| 12.129 | S3g VideoRepick | 20260924-s3g-videorepick.md |
| 12.130 | S4 重导 newtask-v5 快照 | — |
| 12.131 | scripts/README.md 更新到 V5 | — |
| 12.132 | S6 一次生成 v5-01 | 20260924-s6-generation-v5-01.md |
| 12.133 | S5 V1 与本总报告 | 本文 |

## 三、逐环境：做了什么、实测如何

「本机演示」是各 S3 agent 用 `v4_demo_probe` 跑的调试证据（不设门槛）；「正式生成」是 S6 的一次运行（3 正式局 + 递补）。

| 环境 | 改动（均只在 xhard） | 关键实测 | 本机演示 | 正式生成（抽签尝试 / 实跑） |
|---|---|---|---|---|
| VideoUnmask | 干扰容器 3 → 15，贴身环带 [0.2425,0.3289]，含 cube [7,8]，三色平衡；独立停放点 | 15 个全在环带、全可见；内环与 V4 同 seed 6/6 逐位相同；揭示段每步 215 → 35 ms | 4/4 | 10 / 3 of 3 |
| ButtonUnmask | 同上，14 个，cube [7,7] | 同上；揭示段每步 238 → 55 ms | 4/4 | 10 / 3 of 3 |
| VideoUnmaskSwap | 干扰 3 → 10（V4 环带，cube [5,5]）；外环随内环同窗交换；两对联合碰撞证明；内环对内环 reset 预判；内环静默截断改抛错 | 离线首次布局可行 99.3%，16 次耗尽 0；外环终点误差 ≤0.106 mm | 4/4，V4 碰撞局 4500300 在 reset 被拒 | 11 / 3 of 3；外环窗口数 = n_swaps 3/3 |
| ButtonUnmaskSwap | 同上 + 外环离按钮 ≥0.122；静默截断改抛错 | 离线首次可行 95.5%，内环预判拒绝 11.0% | 4/4 | 12 / 3 of 3；外环窗口数 = n_swaps 3/3 |
| InsertPeg | 四根一个采样器、lazy yaw、轮廓间隔 >0.03、离孔板 >0.01、x 上界 0.1；删贴近带；回放复核 | 20 次真 reset 最小间隔 0.0315 / 0.0170；可达极限失败 0 | 4/10（插入不到位 5、复位弹飞 1） | 10 / 7 局成 3（递补 2） |
| MoveCube | 删净 corner_bias；杆/goal/方块离桌面中心 R=0.05 直接拒绝；执行段方块不避让演示段 | 5000 局禁区违例 0、布局失败 0；1000442/1000446 通过 | 11/13（两例任务类失败，P2 同样失败） | 10 / 3 of 3 |
| PatternLock | 节点固定 25，搜索预算 20000，耗尽抛错；布局不动 | 25 节点命中 1.000 | 4/4，818～872 帧 | 10 / 3 of 3，818/872/837 帧（27.3～29.1 s） |
| RouteStick | L [12,15] → [15,21]，冻进 header；布局不动 | 帧数恰为 50·L | 5/5，750～1050 帧 | 10 / 3 of 3，1050/850/800 帧 |
| BinFill | 精确 OBB（2 cm 真正生效）；槽位→配色→建 actor；同色团上限 T=3 | 最小间距 20.03 mm；团超限 0；重排 11/400 局 | 3/4（一例演示中途掉块） | 10 / 3 of 3 |
| PickXtimes | 取消 corner_bias 全部均匀；6 块两两 ≥0.08；精确 OBB；1024 次；半宽 0.25 | <8 cm 的局 69.7% → 0；10 cm 三块团 47.0% → 10.7%；reset 失败 0 | 5/5 | 10 / 3 of 3 |
| SwingXtimes | 共用循环加 xhard 分支；0.08；精确 OBB | <8 cm 的局 44.5% → 0；三块团 23.0% → 11.4%；reset 失败 1.97% → 3.13% | 4/4 | 10 / 3 of 3 |
| VideoRepick | 最小中心距 0.12；k%6 轮流发起；reset 规划搭档（3 个最近可行）；按钮底座纳入扫掠障碍 | 6 块全部参与 100%；规划失败 9.04% → 39.96%；单帧跳变 50～65 mm → ≤11.3 mm | 7/7（reset 7/8） | 14 / 3 of 3，每局 6 块全参与 |
| PickHighlight | xhard 方块障碍改精确 OBB | reset 成功率 97.0% → 87.0%（10 块局 69.6%）；间距违例 241/291 → 0 | 5/5 | 12 / 3 of 3 |
| VideoPlaceButton | 同上 | reset 87.7% → 81.7% | 5/5 | 16 / 3 of 3 |
| VideoPlaceOrder | 同上 | reset 59.3% → 48.3% | 5/7（两例 reset 失败） | 23 / 3 of 3 |
| StopCube | 异常类别名（文件内无 raise/except，无需其他改动） | — | — | 10 / 3 of 3 |

## 四、V1 原三档回归（唯一对拍）

- **两侧**：基线 = `13e5151`（V4 V1 所用的改动前基线，即最原始基线），V5 = `17867d2`（12.130，全部 V5 代码 + 新快照）；各自在独立 worktree、本机、单 worker、B 路、默认 144 条身份（`scripts/configs/newtask-v3/subset_manifest.json`，16 任务 × easy/medium/hard × 3 局）。
- **判定**：`uv run --no-sync python scripts/parity/train_split_parity.py compare --run base=artifacts/newtask-v5/v1/base --run v5=artifacts/newtask-v5/v1/v5 --pair base/B:v5/B --output artifacts/newtask-v5/v1/compare`
  → `H5_PARITY pair=base.B|v5.B compared=144 sha_equal=144 field_mismatch=0`，无「仅一侧存在」与伴生文件散列提示行。
- **运行过程**：基线侧 04:27 起跑（与 S2/S3 各 agent 的测试和演示并行，负载较高），约 3 小时跑完。V5 侧 05:43 起跑，主进程按清单顺序跑完前 12 个任务（至 PickHighlight）；为缩短等待，RouteStick / PatternLock / MoveCube / InsertPeg 由同一 worktree、同一命令的 `--env` 单任务运行在 GPU 0 上分担，结果以符号链接并入 `v1/v5/B`。
- **一处插曲**：停主进程时 PickHighlight 第 11 局的 h5 已关闭、但视频尚未写完，这份 h5 与基线散列不同（`5d326e08…`）。已挪到 `v1/v5_PH11_killed_partial` 留档，并单独重跑该局，重跑结果 `cabc333c…` 与基线逐位相同，采用重跑结果。
- **意义**：原三档在全部 V5 改动下逐位不变，包括 L4(b) 在共用 `spawn_random_cube/target` 上新加的参数、SwingXtimes 共用循环的 xhard 分支、七个模块的异常类别名、Swap / VideoRepick 在 AST 锁定循环外新加的代码。此前一次中途比对（25 条）也全部相同。
- **负载**：两侧未严格同负载（V4 V1 报告已知 PickHighlight/3 这类 RRT 墙钟局会随负载变化），本次 144 条全部相同，未触发该现象。

## 五、待用户统一决策

未决之前，代码都按「当前」一栏运行，v5-01 也是按当前实现生成的。

### 5.1 需要拍板（影响难度 / 分布 / 设计意图）

| # | 环境 | 事项 | 当前 | 可选 |
|---|---|---|---|---|
| D1 | VideoRepick | L54 把按钮底座纳入扫掠障碍后，reset 规划失败率从 9.04% 升到 39.96%（离线 2400 局）。生成仍可行（v5-01 用 14 次尝试攒够 10 条），但通过的布局会偏向方块远离按钮 | (a) 接受 | (b) 方块对按钮不加 5 mm 余量，失败率 34.62%；(c) 摆放阶段就让方块避开按钮，会触及 L51「区域与按钮不动」 |
| D2 | InsertPeg | L53 是否重开：插入不到位是剩余的主要失败（S3d 演示 5/10，全是 obj=1 抓尾插头，插入端离孔板中心 0.0506～0.0749，判据 < 0.05）。v5-01 实跑 7 局只成 3 局，靠递补才凑齐 | 不修 | 只在 xhard 修 `insert_peg` 的插入末段 |
| D3 | InsertPeg | seed 5300300 复位后目标杆被弹飞约 13.6 m（推测原生 `step` 复位时 `set_pose` 没清根速度）。这段是三档共用代码，改动要重过 V1 | 未处理 | 另立事项排查 |
| D4 | PickHighlight | 障碍框修好后 xhard reset 成功率从 97.0% 降到 87.0%，10 块局只有 69.6%（V4 的「稳放 8～10」是在间距实际没生效时测的） | spawn_count [8,10] | 改 [8,9]；或缩小 min_gap_factor |
| D5 | VideoPlaceOrder | 障碍框修好后 reset 成功率从 59.3% 降到 48.3%（VideoPlaceButton 从 87.7% 降到 81.7%）；v5-01 抽签用了 23/30 次，余量最小。根因是目标台和半径 0.1 的 goal_site 挤在 0.4×0.4 区域里 | 接受 | 放宽布局（要改设计） |
| D6 | Swap 两环境 | 外环规划只把干扰容器外扩 5 mm 余量：保留时运行时更稳，但第一候选可行的窗口从 63%/48% 降到 54%/42%，reset 规划 p95 从 1.3 s 升到 2.8 s | 保留 | 去掉，回到 P5 口径 |
| D7 | Swap 两环境 | 外环来回撤销率（相邻两窗交换同一对）VUS 40%、BUS 57%，计划估计是 25～32%。这是最近邻规则镜像内环的结果 | 不处理 | 加「不立即重复上一对」之类的约束 |

### 5.2 实施方已自决、请复核

| # | 事项 | 决定与理由 |
|---|---|---|
| R1 | L14 停放点范围 | xhard 下**内环容器与被藏 cube 也用独立停放点**（L14 原文只点名干扰容器与被藏 cube）。停放点在画面外，窗口与落回步不变；只停干扰容器时揭示段每步 p95 仍约 290 ms，内环也停后约 11 ms |
| R2 | VUS 内环静默截断 | L15 只点名 BUS。VUS 有同样的 `except RuntimeError: break`，已在 xhard 下改为抛真 `SceneGenerationError`，原三档仍 `break` |
| R3 | MoveCube 杆线段 | 取碰撞外形 [−0.145,+0.045] 与可视外形 [−0.15,+0.05] 的并集；每次建杆后按真实几何复核，不写死 |
| R4 | PatternLock 节点数 | 固定为 [25,25]（P3 后决定；计划部分表格仍写 [24,25]） |
| R5 | 其他细节 | PickXtimes 的 1024 次写成模块常量、不进 decision；BinFill 同色连通判据用 ≤0.09；VideoRepick 按钮底座用真实尺寸、不加余量；预筛放行余量 1 mm |

### 5.3 仅报告

| # | 事项 |
|---|---|
| I1 | 每 15～20 步一次、约 300 ms 的周期性慢步来自传感器渲染管线：原三档、其他任务、换 GPU 都有，`obs_mode="state"` 下 p95 只有 2.9 ms，与 V5 无关。是否另立事项由你定 |
| I2 | BinFill 本机演示 3/4：4400100 在演示中途掉块判失败，开局布局合规，只凭视频判断 |
| I3 | BUS 的 L20 内环预判拒绝 11.0%，首次布局可行 95.5%；抽签用 12 次，无压力 |
| I4 | 计划风险 11/13 要求 VideoRepick 冻结前人工看片（路径更长、速度更快），本轮未做人工看片。v5-01 的视频在 `artifacts/newtask-v5/v5-01/rollout/run1/episodes/VideoRepick_episode_{0,3,6}/videos/` |
| I5 | v5-01 只跑一遍（口径 12），可重放性没有证据；是本机单次产物 |

## 六、产物与清理

- 进 Git：代码与测试（12.117～12.13x）、`scripts/configs/newtask-v5/sampling_config.json`、`v5-01/specs.jsonl`、`v5-01/specs.selected.jsonl`、`docs/validation/newtask-v5/*.md`。
- 本机留档（不进 Git，2026-09-24 按用户「worktree … 和对拍两侧的 h5 以后都删除 只保留最终的产物16*3 h5 demo和j16*10sonl」清理后）：
  - **最终产物**：`artifacts/newtask-v5/v5-01/rollout/run1/episodes/<环境>_episode_<n>/`，48 局正式局（16 环境 × 3），各含 `hdf5_files/*.h5` 与 `videos/*.mp4`，约 32 GB；
    对应规格 `scripts/configs/newtask-v5/v5-01/specs.jsonl`（16 × 10 候选）与 `specs.selected.jsonl`（进 Git）。
  - 小体积证据保留：`v5-01/rollout/run1/results.jsonl`、`summary.json`、`v5-01/draft/drafts.jsonl`、`v5-01/report/`、`v1/compare/`（144 对散列与判定）。
  - **已删除**：`/data/hongzefu/robomme_v5_wt/` 下全部 worktree 与本地分支 `v5wt-*`（约 56 GB，含各组本机演示）；V1 两侧 h5 `v1/base`、`v1/v5` 及分担目录（约 98 GB）；
    实跑中失败的 InsertPeg 4 局（episode 2/3/4/6）。
- GL 占位 job 61776866 / 61776867：本轮未使用，已按用户答复 scancel 释放。
