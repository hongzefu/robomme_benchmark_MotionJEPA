# newtask-v7 实施留档（xhard0 ＋ 共用母布局 ＋ 五档定值）

> 方案：仓库根 `0928-newtask-v7-xhard0-shared-layout-plan.md`。代码锚点：GL 生成段 HEAD `77fbe70a`（12.236，起跑到 gen2 完成期间 GL 克隆冻结）；换包与评估钉位 `4a36d505`（12.237）。工作副本 worktree `v7-run`，每次提交后主检出 `newtaskRelease-v5` 本地快进（推送被自动模式拒绝，留给用户）。GL 硬件：A40（driver 595.71.05），占位 job 内 `srun --overlap --gpu_cmode=shared`。本文件是导读，判定行一律内联原文；过程细节见 12.236／12.237 的 commit body。

## ① 一句话结论与指标速览

v7 生成链路（母布局抽签 → 派生 → 四档同步生成）在 GL 上跑通并交付 xhard1/2/3 各 13 任务 × 20 + xhard4 16 任务 × 20 = 1100 局，四档共用布局、定值、前缀几何、可见数量四道静态闸门与回注回放全部通过；v6 回归三对与 xhard0 O:H 192 局全部 PASS；按实测把 xhard2／3／4 的步数上限按 B4 上调为 2400／2900／3800。两策略两轮共 2 × 1292 局评估全部完成，身份、回注绑定与步数上限全部 PASS；SimpleMemVLA 73.4% → 32.7% → 18.1% → 12.7% → 14.1%（xhard0～4），MME-VLA 26.6% → 4.2% → 6.9% → 4.6% → 7.2%。未通过／待用户裁决三项：`PARITY_H_H2=FAIL`（唯一原因 InsertPeg/8 第二次生成规划失败，⑤）；MME `EVAL_ROUND1=FAIL`（2 局 error，其一为 benchmark 的 ButtonUnmaskSwap 评估期碰撞检查缺陷，⑥）；InsertPeg 递补超出每格上限 10（③ 第 3 条）。

| 项 | 判定 |
|---|---|
| 母布局抽签与派生 | `V7_LAYOUT_SHARED=PASS`、`V7_PREFIX_GEOMETRY=PASS`、`V7_TIER_FIXED=PASS`、`V7_VISUAL_COUNT=PASS` |
| gen1 交付 | `V7_DELIVERY_SET=PASS cells=55 per_cell=20`（InsertPeg 追加一轮后） |
| v6 回归 | `PARITY_O_P／P_H／O_H` native 与 `PARITY_P_H` xhard 全 PASS（P 侧 `parity-anchor-v6`） |
| xhard0 | `PARITY_O_H` xhard0 PASS sha_equal=192；`XHARD0_RESET_PARITY=PASS det_diff=0` |
| 回放与入口 | `V7_RESET_REPLAY=PASS resets=55`；`HARD_EVAL_SMOKE=PASS` × 2 |
| 步数余量 | xhard2／3／4 超上限 → B4 上调（③ 第 5 条） |
| 两次生成 | `PARITY_H_H2=FAIL`：1086 局逐字节相同、13 局噪声，唯一 FAIL 为 InsertPeg/8（⑤） |
| 评估 | 两策略 `EVAL_IDENTITY_SET／EVAL_BINDING／EVAL_TIER_CAP` 全 PASS；SimpleMemVLA 两轮 PASS，MME r1 因 2 局 error FAIL、r2 PASS（⑥） |
| xhard0 两入口 | SimpleMemVLA `status_diff=0`；MME `status_diff=11`（50 对 51，策略随机性）（⑥） |

## ② 用户指令原话（按时间，编号供引用）

1. 「/data/hongzefu/robomme_benchmark_MotionJEPANewTask/0928-newtask-v7-xhard0-shared-layout-plan.md 开始实施 有问题半小时内问用户 一口气跑完」
2. 「继续 注意有一个评估报告被清除了 作为不可靠结论 目前计划仍旧采用上一次v6生成的eval分法 只是增加4cpu档位 先和用户确认你收到理解该信息 然后继续执行」
3. 「用一个新的worktree 然后每次commit完同步主branch 是否可以」
4. 「还有什么问题 在半小时内问用户 然后一口气跑完」
5. AskUserQuestion：B3「按首个分叉步判（推荐）」；PatternLock「直接改 12/15/18/21」；阶段 1 补核对「批准 ≤16 次」；阶段 3「批准 ≤24」「批准增至 768 次」
6. 「批准增加Reset次数增加到原来的十倍都可以。」
7. 「不要再问我了尽可能一路做到东部时间明天早上10点。」

## ③ 生成链路（阶段 4～6）

1. **母布局抽签**（xhard4，16 任务 × 30 候选，`--select 0..19`）：`FREEZE rows=480`，抽签 reset 615 次。
2. **派生**（xhard1～3）：`DERIVE` 1170 次、ok 1150。静态闸门：
   ```text
   V7_LAYOUT_SHARED=PASS tasks=13 rows=1150 parent_mismatch=0 seed_mismatch=0 value_mismatch=0 missing_l=0
   V7_PREFIX_GEOMETRY=PASS rows=1150 violations=0
   V7_TIER_FIXED=PASS cells=52 layouts=377 violations=0
   V7_VISUAL_COUNT=PASS cells=24 mismatch=0
   ```
   VideoRepick 四档齐全的候选只有 18 个 → vr60 追加轮（`--candidates-per-env 60`，候选 0～29 与首轮同 seed）：`VR60_REPRO=PASS 102/102`，`MERGE_VR60=PASS`，并入 `v7/specs-final`（xhard1 402／xhard2 409／xhard3 412／xhard4 510 行）。
3. **gen1**（占位 job 62268734，16 worker，候选池四档同步作废与递补，每格递补上限 10）：首跑 `attempted=1130 delivered=1098 sync_dropped=27 backfills=25`，
   ```text
   V7_DELIVERY_SET=FAIL cells=55 per_cell=20 tier_set_equal=13 problems=['InsertPeg 交付 18/20']
   ```
   InsertPeg（只有 xhard4）12 个候选生成失败，递补上限用尽、30 候选全部用完。按 B2 精神追加一轮：`DRAW_TASK InsertPeg ok=60 attempted=60`（reset 60 次，在原话 6 授权内）；一次性合并 `IP60_REPRO=PASS equal=30/30`、`MERGE_IP60=PASS xhard4_rows=540 insertpeg_rows=60`；候选池手动补位候选 30、31（`manual_backfill` 留原因）；`--resume` 续跑 `ROUND xhard4/0 jobs=2 ok=2`：
   ```text
   V7_DELIVERY_SET=PASS cells=55 per_cell=20 tier_set_equal=13
   GENERATE_CONTINUE_DONE attempted=2 rounds=1 infra_retries=0 delivered=1100 sync_dropped=27 backfills=25
   ```
4. **换包**：`v7/specs-final` 四档 `specs.jsonl` 换入 `src/robomme_hard/env_metadata/test-hard/`，`load_specs_v7` 通过，选中数 xhard1/2/3 各 260、xhard4 320。
5. **步数余量（B4）**：执行步 = 总帧 − 演示帧。gen1 交付各档最长执行步都是无演示段的 PickXtimes：xhard1 1304／1500（0.869）、xhard2 1857／1700、xhard3 2293／2000、xhard4 2998／2600。按用户预定的 B4（超 90% 不回调抓取次数，上限上调为实测最大执行步数 × 1.25 向上取整到百）：`TIER_MAX_STEPS` xhard2 2400、xhard3 2900、xhard4 3800，xhard0 1300、xhard1 1500 不动。逐局正式判定在 NFS 上逐步读 h5 超时（25 分钟），gen1 回传本机（4802 文件、828,434,639,410 字节两侧相同）后补跑，按上调后的上限复核：
   ```text
   V7_STEP_HEADROOM=PASS cells=55 over_90pct=0 worst={'xhard1': '1304/1500', 'xhard2': '1857/2400', 'xhard3': '2293/2900', 'xhard4': '2998/3800'}
   ```
   逐局最长执行步与上面的上界速判一致（有演示段的任务执行段都更短）。每格长度均值写进 `scripts/README.md` 第 3 节（`artifacts/newtask-v7/v7-lengths.json`）。

## ④ 对拍（阶段 5／5′／7）

v6 回归（P 侧 `--p-anchor parity-anchor-v6`；native 16 任务 × 3 档 × 3 局 = 144，xhard 为 xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165）：

```text
PARITY_ANCHOR=PASS tag=parity-anchor-v6 commit=ce3843b4fbe9 cached=144 sha_bad=0 gpu=NVIDIA A40 driver=595.71.05
PARITY_O_P=PASS tier=native shape=16x3x3 compared=144 identity_equal=144 setup_equal=144 schema_equal=144 success_equal=144 both_success=144 both_fail=0 tol_over=0 noise=0 over_total=0 hard_line_5pct=ok action_max=0/0.0413 state_max=0/0.0411 image_mad=0/1 frames_max=0/5 sha_equal=144 frames_equal=144
PARITY_P_H=PASS tier=native shape=16x3x3 compared=144 ... action_max=0.0275/0.0413 state_max=0.0274/0.0411 image_mad=0.144/1 frames_max=0/5 sha_equal=143 frames_equal=144
PARITY_O_H=PASS tier=native shape=16x3x3 compared=144 ... action_max=0.0275/0.0413 state_max=0.0274/0.0411 image_mad=0.144/1 frames_max=0/5 sha_equal=143 frames_equal=144
PARITY_P_H tier=xhard verdict=PASS identity_equal=165 success_equal=165 both_success=165 sha_equal=165 frames_equal=165 binding_ok=165（summary.json）
```

native 三对首跑 O:P、O:H 判 FAIL（`binding_ok=82`）：bucket 拉回的 O 侧没有 `_runner/results.json`，`side_lines` 缺 `robomme_module`；改为从 launch 记录补齐（`robomme_module_source="launch"`）后在 `r2` 子目录重跑，三对全 PASS。唯一 sha 不等的一对是 RRT 噪声，首个分叉步 549（`PARITY_REFERENCE=INFO first_divergence_n=1 first_divergence_median=549`），在容差内。

xhard0（16 任务 × 1 档 × 12 局 = 192，同一官方身份 O／H 各生成一次）：

```text
GENERATE=PASS side=O tier=xhard0 rows=192 recorded=192 success=190 runner_exit=1 gpu=NVIDIA A40 mover_errors=0
GENERATE=PASS side=H tier=xhard0 rows=192 recorded=192 success=190 runner_exit=1 gpu=NVIDIA A40 mover_errors=0
PARITY_O_H tier=xhard0 verdict=PASS identity_equal=192 setup_equal=190 success_equal=192 both_success=190 both_fail=2 sha_equal=192 binding_ok=192（summary.json）
BUCKET_SYNC=PASS side=O tier=xhard0 objects=192 readback_sha_equal=192 mismatch=0 remote=hf://buckets/HongzeFu/robomme-hard-parity/O-1fadc0e-a40/xhard0
XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0 name_only=12 first_det_diff=- name_only_tasks=['ButtonUnmaskSwap']
XHARD0_DEMO_DIFF=INFO frames_equal=192 max_frame_diff=0 demo_equal=192 post_equal=144
```

- `both_fail=2`：VideoPlaceOrder seed 610701、611101，两侧都是 `DatasetGenerationError`（官方原版在这两个 seed 上就生成失败），按原话 7 不再询问，只留档。
- reset 层首跑 `XHARD0_RESET_PARITY=FAIL det_diff=12`，全部是 ButtonUnmaskSwap：F3 左右按钮实体命名在两侧对调，状态数值相同。加 `name_only` 判据（只差实体命名单列）后只重跑该任务并合并，PASS。

回放与入口（阶段 7，本机 GPU1，读 `v7/specs-final`）：

```text
V7_RESET_REPLAY=PASS shape=13x3+16 resets=55 replay=55 injected_mismatch=0 layout_drift=0 unused=0 layout_hit_bad=0 errors=0
HARD_EVAL_SMOKE=PASS task=BinFill episode=0 tier=xhard0 seed=540302 episodes=92 max_steps=1300 mode=export status=smoke_cut steps=50 injected_mismatch=0
HARD_EVAL_SMOKE=PASS task=BinFill episode=12 tier=xhard1 seed=14400000 episodes=92 max_steps=1500 mode=replay status=smoke_cut steps=50 injected_mismatch=0
```

## ⑤ 两次生成对拍（H:H2，阶段 6）

gen2 在占位 job 62268735 上按 gen1 `delivery.json` 重放 1100 局（05:57～08:42）：

```text
GENERATE=PASS side=H2 tier=v7 rows=1100 recorded=1100 success=1099 runner_exit=0 gpu=NVIDIA A40 mover_errors=0
```

唯一失败局 `xhard4/InsertPeg/8`（gen1 同身份成功）。H2 逐局拉回本机 `PULL_SEGMENT=PASS segment=H2-v7 identities=1100 h5=1100 sha_bad=0 nfs_leftover_media=0`；gen1 登记为 H 侧 `IMPORT_DELIVERY=PASS tier=v7 rows=1100 sha_mismatch=0`。比对：

```text
PARITY_H_H2=FAIL tier=v7 shape=13x3x20+16x1x20 compared=1100 identity_equal=1100 setup_equal=1099 schema_equal=1099 success_equal=1099 both_success=1099 both_fail=0 tol_over=0 noise=13 over_total=13 hard_line_5pct=ok action_max=5.16/0.0413 state_max=5.15/0.0411 image_mad=10.8/1 frames_max=116/5 sha_equal=1086 frames_equal=1086 binding_ok=1100 recovery_mismatch=0
PARITY_REFERENCE=INFO pair=H:H2 tier=v7 first_divergence_n=13 first_divergence_median=399 first_divergence_min=118
```

- 1086 局两次生成逐字节相同；回注绑定 1100/1100 正确。
- 13 局 sha 不同但身份／setup／结构／成功都相等、首个分叉步 ≥118，按 B3 口径记 noise（1.2%，5% 硬线内）；例如 InsertPeg/29 在第 121 步分叉、两侧都成功。
- **FAIL 的唯一来源是 `xhard4/InsertPeg/8`**：H2 侧 `DatasetGenerationError`（h5 仅 800 字节、`IndexError: list index out of range`），gen1 侧成功 505 帧——是第二次生成在规划阶段失败，不是回放行为偏差。InsertPeg 在 16 worker 并发下对 RRT 墙钟预算敏感（gen1 首跑 30 候选中 12 个生成失败）。
- 按证据纪律不改判据、不放宽，候选处置交用户裁决：(a) 认定为生成端 RRT 随机性偶发失败，交付集不动；(b) InsertPeg/8 换备用候选（需重生成该局并重评两策略该局）。

## ⑥ 评估（阶段 9～10）

- 评估清单 `artifacts/newtask-v7/eval-identities-1292.jsonl`（sha256 `ad3db77d…`，NFS 副本 `v7-eval/eval-identities-1292.jsonl`）：
  ```text
  EVAL_IDENTITY_EXPORT=PASS episodes=1292 round1=646 round2=646 shards=10 official=192 tiers={'xhard0': 192, 'xhard1': 260, 'xhard2': 260, 'xhard3': 260, 'xhard4': 320}
  ```
  分轮沿用 v6（原话 2）：每格按 `candidate` 升序前 10 局第一轮、后 10 局第二轮；xhard0 每任务按原 episode 升序前 6 局第一轮、后 6 局第二轮；每轮按 v6 实测单局用时贪心均衡切 10 片。官方路线清单与已跑的 `eval-official-xhard0-192.jsonl` 逐字节相同。
- 官方路线对照（xhard0 192 局，官方 `robomme` + `dataset="test"`）：`EVAL_OFFICIAL_XHARD0=PASS` simplememvla 141/192、mmevla 50/192。
- 两策略仓库分支 `testhard-eval-v7-0929`（SimpleMemVLA `1ca6d1e`、MME-VLA `4f9e40f`），子模块钉 `4a36d505`（`SUBMODULE_PIN=PASS`），benchmark 分支 `PolicyEvalThirdParty-{simplememvla,mmevla}-0929-0608`。
- 冒烟（xhard0 VideoUnmaskSwap ep2 ＋ xhard1 VideoRepick ep14）：SimpleMemVLA `TESTHARD_DONE identities=2 valid=2 success=2 unresolved_errors=0`；MME-VLA 2 局均有终态（fail）、`EVAL_PASS_END rc=0 unresolved_errors=0`；两策略视频经 `eval_video_mover.py` 搬到 `/data`（sha256 核对后删 NFS 副本）。
- 评估中出现的两类 error（MME-VLA 三遍重评均失败，终态 `error`，不计入成功率分母，单列）：
  - `VideoPlaceOrder/78`（xhard4，演示段 1902 帧）：MME 服务端 `mem_buffer._load_emb` 报 `ValueError: all input arrays must have the same shape`——策略侧对超长演示的限制，未改策略代码。
  - `ButtonUnmaskSwap/81`（xhard4，seed 14700902）：**benchmark 侧缺陷**。三遍都在第 295 步崩溃（error 录像均 295 帧），恰是 xhard4 独有的第 8 个交换窗口起点；`robomme_hard` 的 ButtonUnmaskSwap 在每个交换窗口起点按容器实际位姿做碰撞扫描（`utils/unmask_swap_xhard.py::joint_sweep_from_actual`），被拒即抛 `BinCollisionError`。这道本为生成期拒样的检查在评估期仍生效，策略把容器碰偏后该局被判 error 而非正常成败。官方 `FailAwareWrapper` 把异常转成 `obs=None`＋`status=error`，MME 客户端未检查而表现为 `'NoneType' object is not subscriptable`（SimpleMemVLA 客户端会检查，同局它的轨迹未触发）。截至两策略第一轮全部与第二轮大部分完成，只有这 1 局触发。候选修法（未实施，待用户裁决）：评估／回放模式下该检查只记录不抛异常（`robomme_hard/robomme_env/ButtonUnmaskSwap.py`，VideoUnmaskSwap 同查），改后需重钉两策略子模块并重评受影响局；另建议 MME 客户端 `env_runner.py::step` 对 `obs is None or info["status"]=="error"` 显式记 error 并打印真实原因。
- 正式评估 2026-09-29 06:21 起跑，13:25 全部结束：10 个评估占位 job（62315065～62315074，各 4 CPU／32G／1 A40）每片严格串行 SimpleMemVLA r1 → MME-VLA r1 → SimpleMemVLA r2 → MME-VLA r2。片 9 因 ControlMaster 会话超限晚起 2 小时（08:42 改在登录节点 tmux 起跑，见 12.239），其 MME r2 于 11:38 挪到片 6 空出的 62315071 与其 SimpleMemVLA r2 并行（`OFFLOAD_DONE`，登录节点脚本随后按 `episodes.jsonl` 已有终态跳过）。各片整片完成后按清单逐个释放占位 job。
- 合并判定（`robomme_policy_learning-testhard-v7/scripts/merge_eval_shards.py`，以 benchmark worktree venv 运行，上限取 `robomme_hard`）：
  ```text
  EVAL_ROUND1=PASS policy=simplememvla episodes=646/646 normal=646 error_left=0 retries=0 shards=10/10 missing=0 extra=0
  EVAL_ROUND2=PASS policy=simplememvla episodes=646/646 normal=646 error_left=0 retries=0 shards=10/10 missing=0 extra=0
  EVAL_IDENTITY_SET=PASS policy=simplememvla episodes=1292/1292 missing=0 extra=0 dup=0
  EVAL_BINDING=PASS policy=simplememvla replay=1100/1100 export=192/192 injected_mismatch=0 recorded_drift=0 layout_drift=0
  EVAL_TIER_CAP=PASS policy=simplememvla mismatch=0 caps=robomme_hard
  EVAL_ROUND1=FAIL policy=mmevla episodes=646/646 normal=644 error_left=2 retries=4 shards=10/10 missing=0 extra=0
  EVAL_ROUND2=PASS policy=mmevla episodes=646/646 normal=646 error_left=0 retries=0 shards=10/10 missing=0 extra=0
  EVAL_IDENTITY_SET=PASS policy=mmevla episodes=1292/1292 missing=0 extra=0 dup=0
  EVAL_BINDING=PASS policy=mmevla replay=1100/1100 export=192/192 injected_mismatch=0 recorded_drift=0 layout_drift=0
  EVAL_TIER_CAP=PASS policy=mmevla mismatch=0 caps=robomme_hard
  ```
  MME `EVAL_ROUND1=FAIL` 的唯一原因是上面两局 error（按判据如实记，不改判据）。
- 分档成功率（分母为该档全部局，error 计入分母；`EVAL_TIER_SUCCESS` 原文在 `artifacts/newtask-v7/eval/*-merge.log`，逐格表 `*-table.json`）：

  | 策略 | xhard0（16 × 12） | xhard1（13 × 20） | xhard2（13 × 20） | xhard3（13 × 20） | xhard4（16 × 20） |
  |---|---|---|---|---|---|
  | SimpleMemVLA | 141/192（73.4%） | 85/260（32.7%） | 47/260（18.1%） | 33/260（12.7%） | 45/320（14.1%） |
  | MME-VLA | 51/192（26.6%） | 11/260（4.2%） | 18/260（6.9%） | 12/260（4.6%） | 23/320（7.2%，含 2 error） |

  SimpleMemVLA 逐档下降到 xhard3，xhard4 与 xhard3 持平（xhard4 多 MoveCube 10/20、InsertPeg 5/20 两个较易任务）；MME 在 xhard1 起落到地板，只有 VideoPlaceButton／VideoPlaceOrder 两任务在新值档有分。按任务：xhard1 起即为 0 的有 PickHighlight、PickXtimes（两策略）、SwingXtimes（SimpleMemVLA 自 xhard2 起）、VideoUnmaskSwap；ButtonUnmask 在 SimpleMemVLA 上 xhard1／xhard2 都是 16/20，高于 xhard0 的 10/12（每格 20 局，噪声范围内）。
- xhard0 新旧两个入口的策略层对照（只报告，D-16；环境层已由 xhard0 O:H 192 局逐字节相同证明一致）：
  ```text
  XHARD0_EVAL_PARITY=INFO policy=simplememvla compared=192 status_diff=0 steps_diff=16
  XHARD0_EVAL_PARITY=INFO policy=mmevla compared=192 status_diff=11 steps_diff=71
  ```
  SimpleMemVLA 两入口成败逐局相同（官方路线 141/192 = v7 路线 141/192，按任务也逐项相同）；MME 50 对 51、11 局翻转且方向对称（5 成→败、5 败→成、1 超时→成），原因未坐实。更正：MME 服务端每局 `reset` 把采样随机数重置为固定种子（`policy.py::reset`，`jax.random.key(seed)`），「随机数跨局消耗」不成立。候选：(A) GPU 渲染／JAX 数值在不同节点上的微小不确定性被 MME 放大（SimpleMemVLA 也有 16 局步数不同，说明链路存在数值不确定性）；(B) 两个 MME 分支（`official-xhard0` 与 `testhard-eval-v7`）客户端代码不同，喂给策略的输入有系统差别。区分办法：两入口各把这 11 局重跑一次（22 局，官方路线重评预算内），同入口重跑即翻转为 A，同入口稳定复现而两入口仍不同为 B。`hard_regression.py xhard0-eval-parity` 本轮按两策略实际结果文件名与官方记录无 `episode` 字段的事实改写了读入（`--official`／`--hard` 可给多个文件或目录）。
- 视频（`eval_video_mover.py`，sha256 核对后删 NFS 副本）：SimpleMemVLA 1292/1292、MME-VLA 1290/1290 终态局视频在 `artifacts/newtask-v7/eval-videos/<策略>/<tier>/<task>/`；MME 两局 error 的 6 段重试录像在 `eval-videos/mmevla/_errors/`（sha256 逐个核对 OK）；NFS 视频暂存已清空。冒烟 2 局视频与正式评估同名，已被正式评估的版本覆盖。

## ⑦ 收尾状态与待用户裁决

- 资源：`GEN_HOLD_RELEASE=PASS`（08:45 gen2 结束后 `scancel 62268734`）；评估占位 62315065～62315074 按片整片完成逐个释放（62315069、62315071 手动，其余由 `auto_release` 按清单 JobID 释放；取消前核对该 job 只剩 batch／extern 步骤），片 9 的 62315074 在登录节点脚本写出 `SHARD_DONE` 后释放。按 A6 名下最终只留 62268735。
- NFS：gen1（828 GB）在本机副本两侧文件数／字节数相同且 1100 局逐局 sha 核对后删除；gen2 由 `hard_pull` 逐局 sha 核对后删除；评估视频暂存清空。`v7/specs*`、`v7-stage/` 各段清单与日志、`v7-eval/` 结果文件体积小，保留。
- 本机与 NFS 清理（用户 2026-09-29 原话「这些都删除 eval结果视频本地要保留」）：删除 `artifacts/newtask-v7/parity/h5/` 下全部对拍 h5——H2-v7（768 GB）、H-native、H-xhard、H-xhard0、O-native、O-xhard0、P-native、P-xhard、H-v7（仅 1100 个指向 gen1 的符号链接，删链接不穿透）；删除 GL 侧克隆 `robomme_benchmark-v7-gl` 及其 worktree `-v7-gl-o`（均无未提交改动，HEAD 77fbe70 已在推送的主分支）。保留：gen1 正式 1100 局 h5（删后复核文件数与字节数不变）、两策略评估视频、包内规格与候选池。
  - 影响：`parity-anchor-v6` 登记的 P 缓存本地副本已删，公开 bucket `HongzeFu/robomme-hard-parity` 仍有 `H-34a1cea-a40/native`（144）与 `H-b1afc80-a40/xhard`（165）；以后以该锚点做对拍前须先 `hard_pull`／`hf buckets sync` 拉回到 `docs/validation/parity-anchors.json` 登记的目录名，否则 `PARITY_ANCHOR` 报缺目录。第 1 项若日后选「换候选重生成」，GL 克隆需重新检出。
- **未做（按方案须等条件满足）**：`parity-anchor-v7`。方案第一部分第 6 步要求「全部通过后」才打 tag，现 `PARITY_H_H2=FAIL`；且等价核验须逐文件判定 `77fbe70..HEAD` 的改动（含 `TIER_MAX_STEPS` 上调）是否触及产物字节，不自行越过。
- **待用户裁决**：
  1. `PARITY_H_H2=FAIL`：InsertPeg/8 取 (a) 认定偶发、交付集不动，或 (b) 换备用候选重生成并重评该局。
  2. ButtonUnmaskSwap 评估期碰撞检查缺陷（⑥）：是否修（改 `robomme_hard`，重钉两策略子模块，重评受影响局）。
  3. InsertPeg 追加轮后手动补位 2 局、超出每格递补上限 10（③ 第 3 条）是否追认。
  4. MME xhard0 两入口 11 局翻转是否要做同入口重跑对照（11 局 × 1 策略）坐实为策略随机性。
- **用户裁决（2026-09-29，原话「1暂时不管 2暂时不管 3同意递补 4 没看懂详细讲」）**：第 1、2 项暂时不处理（交付集与 benchmark 代码保持现状，H2 本地副本继续保留）；第 3 项追认 InsertPeg 追加轮与手动补位 2 局；第 4 项经解释后用户原话「先把项目4设置为待定 收尾这次任务 推送」——**待定**（22 局两入口重跑对照未做，⑥ 的 A／B 两种原因均未排除）。
- **推送**（自动模式拒绝，留用户手动）：benchmark `newtaskRelease-v5`、`PolicyEvalThirdParty-{simplememvla,mmevla}-0929-0608`、tag `parity-anchor-v6`；两策略仓库 `testhard-eval-v7-0929`（子模块指向 `4a36d505`，benchmark 推送后 GitHub 上才取得到）。
