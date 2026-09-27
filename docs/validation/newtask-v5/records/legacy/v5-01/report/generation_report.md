# V5 生成报告

- 来源：drafts `artifacts/newtask-v5/v5-01/draft/drafts.jsonl`；specs `scripts/configs/newtask-v5/v5-01/specs.jsonl`；rollout `artifacts/newtask-v5/v5-01/rollout/run1`；run_id `v5-01`
- 口径：每环境候选目标 10 条；正式局 index [0, 3, 6]；演示帧数合格带 750～1050（`info/is_video_demo` 为真的帧数）

```text
V5_GENERATION=REPORT tasks=16 draft_ok=160 rollout_ok=48 backfilled=2 selected_shortfall=0 demo_frames_out_of_band=0 outer_swap_mismatch=0 bin_collision=0 vr_min_participants=6
```

草稿尝试 188、成功 160、候选缺口 0；实跑 52 局、成功 48、递补成功 2、正式局缺口 0；抽签期 BinCollisionError 0。

## 逐环境

| 环境 | draft_attempted | draft_ok | candidate_shortfall | 抽签失败类别 | 正式局目标 | rollout_attempted | rollout_ok | backfilled | selected_shortfall | by_class |
|---|---|---|---|---|---|---|---|---|---|---|
| PickXtimes | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| StopCube | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| SwingXtimes | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| BinFill | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| VideoUnmaskSwap | 11 | 10 | 0 | SceneGenerationError×1 | 3 | 3 | 3 | 0 | 0 | — |
| VideoUnmask | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| ButtonUnmaskSwap | 12 | 10 | 0 | SceneGenerationError×2 | 3 | 3 | 3 | 0 | 0 | — |
| ButtonUnmask | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| VideoRepick | 14 | 10 | 0 | SceneGenerationError×4 | 3 | 3 | 3 | 0 | 0 | — |
| VideoPlaceButton | 16 | 10 | 0 | SceneGenerationError×6 | 3 | 3 | 3 | 0 | 0 | — |
| VideoPlaceOrder | 23 | 10 | 0 | SceneGenerationError×13 | 3 | 3 | 3 | 0 | 0 | — |
| PickHighlight | 12 | 10 | 0 | SceneGenerationError×2 | 3 | 3 | 3 | 0 | 0 | — |
| InsertPeg | 10 | 10 | 0 | — | 3 | 7 | 3 | 2 | 0 | DatasetGenerationError×3；PlannerExhausted×1 |
| MoveCube | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| PatternLock | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| RouteStick | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |

## PatternLock / RouteStick 演示帧数（合格带 750～1050）

| 环境 | episode | seed | 角色 | 演示帧数 | 秒（÷30） | 落在带内 |
|---|---|---|---|---|---|---|
| PatternLock | 0 | 5500000 | selected | 818 | 27.3 | True |
| PatternLock | 3 | 5500300 | selected | 872 | 29.1 | True |
| PatternLock | 6 | 5500600 | selected | 837 | 27.9 | True |
| RouteStick | 0 | 5600000 | selected | 1050 | 35.0 | True |
| RouteStick | 3 | 5600300 | selected | 850 | 28.3 | True |
| RouteStick | 6 | 5600600 | selected | 800 | 26.7 | True |

## Swap 两环境外环交换窗口数 vs n_swaps

| 环境 | episode | seed | 演示成功 | n_swaps | 规划窗口数 | 运行时窗口数 | 相等 | 说明 |
|---|---|---|---|---|---|---|---|---|
| VideoUnmaskSwap | 0 | 4500000 | True | 10 | 10 | 10 | True |  |
| VideoUnmaskSwap | 3 | 4500301 | True | 10 | 10 | 10 | True |  |
| VideoUnmaskSwap | 6 | 4500600 | True | 9 | 9 | 9 | True |  |
| ButtonUnmaskSwap | 0 | 4700000 | True | 8 | 8 | 8 | True |  |
| ButtonUnmaskSwap | 3 | 4700300 | True | 7 | 7 | 7 | True |  |
| ButtonUnmaskSwap | 6 | 4700600 | True | 8 | 8 | 8 | True |  |

## VideoRepick 每局参与交换的方块数

| episode | seed | 演示成功 | 交换次数 | 参与方块数 | 来源 | 说明 |
|---|---|---|---|---|---|---|
| 0 | 4900001 | True | 8 | 6 | spec |  |
| 3 | 4900300 | True | 12 | 6 | spec |  |
| 6 | 4900601 | True | 9 | 6 | spec |  |
