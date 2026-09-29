# newtask-v7 实施留档（xhard0 ＋ 共用母布局 ＋ 五档定值）

> 方案：仓库根 `0928-newtask-v7-xhard0-shared-layout-plan.md`。代码锚点：GL 生成段 HEAD `77fbe70a`（12.236，起跑到 gen2 完成期间 GL 克隆冻结）；换包与评估钉位 `4a36d505`（12.237）。工作副本 worktree `v7-run`，每次提交后主检出 `newtaskRelease-v5` 本地快进（推送被自动模式拒绝，留给用户）。GL 硬件：A40（driver 595.71.05），占位 job 内 `srun --overlap --gpu_cmode=shared`。本文件是导读，判定行一律内联原文；过程细节见 12.236／12.237 的 commit body。

## ① 一句话结论与指标速览

v7 生成链路（母布局抽签 → 派生 → 四档同步生成）在 GL 上跑通并交付 xhard1/2/3 各 13 任务 × 20 + xhard4 16 任务 × 20 = 1100 局，四档共用布局、定值、前缀几何、可见数量四道静态闸门与回注回放全部通过；v6 回归三对与 xhard0 O:H 192 局全部 PASS；按实测把 xhard2／3／4 的步数上限按 B4 上调为 2400／2900／3800。两次生成对拍（H:H2）与两策略评估见 ⑤、⑥（进行中时标注）。

| 项 | 判定 |
|---|---|
| 母布局抽签与派生 | `V7_LAYOUT_SHARED=PASS`、`V7_PREFIX_GEOMETRY=PASS`、`V7_TIER_FIXED=PASS`、`V7_VISUAL_COUNT=PASS` |
| gen1 交付 | `V7_DELIVERY_SET=PASS cells=55 per_cell=20`（InsertPeg 追加一轮后） |
| v6 回归 | `PARITY_O_P／P_H／O_H` native 与 `PARITY_P_H` xhard 全 PASS（P 侧 `parity-anchor-v6`） |
| xhard0 | `PARITY_O_H` xhard0 PASS sha_equal=192；`XHARD0_RESET_PARITY=PASS det_diff=0` |
| 回放与入口 | `V7_RESET_REPLAY=PASS resets=55`；`HARD_EVAL_SMOKE=PASS` × 2 |
| 步数余量 | xhard2／3／4 超上限 → B4 上调（③ 第 5 条） |

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
5. **步数余量（B4）**：执行步 = 总帧 − 演示帧。gen1 交付各档最长执行步都是无演示段的 PickXtimes：xhard1 1304／1500（0.869）、xhard2 1857／1700、xhard3 2293／2000、xhard4 2998／2600。按用户预定的 B4（超 90% 不回调抓取次数，上限上调为实测最大执行步数 × 1.25 向上取整到百）：`TIER_MAX_STEPS` xhard2 2400、xhard3 2900、xhard4 3800，xhard0 1300、xhard1 1500 不动。逐局正式判定 `V7_STEP_HEADROOM` 在 NFS 上逐步读 h5 超时（25 分钟），改在 gen1 回传本机后补跑（⑦）。

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

gen2 在占位 job 62268735 上按 gen1 `delivery.json` 重放 1100 局（进行中，结论补记）。

## ⑥ 评估（阶段 9～10）

- 评估清单 `artifacts/newtask-v7/eval-identities-1292.jsonl`（sha256 `ad3db77d…`，NFS 副本 `v7-eval/eval-identities-1292.jsonl`）：
  ```text
  EVAL_IDENTITY_EXPORT=PASS episodes=1292 round1=646 round2=646 shards=10 official=192 tiers={'xhard0': 192, 'xhard1': 260, 'xhard2': 260, 'xhard3': 260, 'xhard4': 320}
  ```
  分轮沿用 v6（原话 2）：每格按 `candidate` 升序前 10 局第一轮、后 10 局第二轮；xhard0 每任务按原 episode 升序前 6 局第一轮、后 6 局第二轮；每轮按 v6 实测单局用时贪心均衡切 10 片。官方路线清单与已跑的 `eval-official-xhard0-192.jsonl` 逐字节相同。
- 官方路线对照（xhard0 192 局，官方 `robomme` + `dataset="test"`）：`EVAL_OFFICIAL_XHARD0=PASS` simplememvla 141/192、mmevla 50/192。
- 两策略仓库分支 `testhard-eval-v7-0929`（SimpleMemVLA `1ca6d1e`、MME-VLA `4f9e40f`），子模块钉 `4a36d505`（`SUBMODULE_PIN=PASS`），benchmark 分支 `PolicyEvalThirdParty-{simplememvla,mmevla}-0929-0608`。
- 冒烟（xhard0 VideoUnmaskSwap ep2 ＋ xhard1 VideoRepick ep14）：SimpleMemVLA `TESTHARD_DONE identities=2 valid=2 success=2 unresolved_errors=0`；MME-VLA 2 局均有终态（fail）、`EVAL_PASS_END rc=0 unresolved_errors=0`；两策略视频经 `eval_video_mover.py` 搬到 `/data`（sha256 核对后删 NFS 副本）。
- 正式评估 2026-09-29 06:21 起跑：10 个评估占位 job（62315065～62315074，各 4 CPU／32G／1 A40）每片严格串行 SimpleMemVLA r1 → MME-VLA r1 → SimpleMemVLA r2 → MME-VLA r2（结论补记）。

## ⑦ 待补

- `V7_STEP_HEADROOM` 逐局正式判定与每格长度均值（gen1 回传本机后跑；长度表写进 `scripts/README.md` 第 3 节）。
- ⑤ H:H2 结论、gen2 删除、`GEN_HOLD_RELEASE`（取消 62268734，只留 62268735）。
- `parity-anchor-v7` 打 tag 并登记 native／xhard0／v7 三段。
- ⑥ 两轮评估结果、`xhard0-eval-parity`、视频全量对账、10 个评估 job 逐个取消。
