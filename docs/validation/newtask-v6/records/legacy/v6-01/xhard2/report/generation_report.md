# V5 生成报告

- 来源：drafts `/tmp/v6-s4-v6-01/xhard2/draft/drafts.jsonl`；specs `/tmp/v6-s4-v6-01/xhard2/specs.jsonl`；rollout `/tmp/v6-s4-v6-01/xhard2/rollout/run1`；run_id `/tmp/v6-s4-v6-01`
- 口径：每环境候选目标 10 条；正式局 index [0, 3, 6]；演示帧数合格带 750～1050（`info/is_video_demo` 为真的帧数）

```text
V5_GENERATION=REPORT tasks=13 draft_ok=130 rollout_ok=39 backfilled=0 selected_shortfall=0 demo_frames_out_of_band=6 outer_swap_mismatch=0 bin_collision=0 vr_min_participants=5
```

草稿尝试 152、成功 130、候选缺口 0；实跑 39 局、成功 39、递补成功 0、正式局缺口 0；抽签期 BinCollisionError 0。

## 逐环境

| 环境 | draft_attempted | draft_ok | candidate_shortfall | 抽签失败类别 | 正式局目标 | rollout_attempted | rollout_ok | backfilled | selected_shortfall | by_class |
|---|---|---|---|---|---|---|---|---|---|---|
| PickXtimes | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| SwingXtimes | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| BinFill | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| VideoUnmaskSwap | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| VideoUnmask | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| ButtonUnmaskSwap | 16 | 10 | 0 | SceneGenerationError×6 | 3 | 3 | 3 | 0 | 0 | — |
| ButtonUnmask | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| VideoRepick | 13 | 10 | 0 | SceneGenerationError×3 | 3 | 3 | 3 | 0 | 0 | — |
| VideoPlaceButton | 12 | 10 | 0 | SceneGenerationError×2 | 3 | 3 | 3 | 0 | 0 | — |
| VideoPlaceOrder | 21 | 10 | 0 | SceneGenerationError×11 | 3 | 3 | 3 | 0 | 0 | — |
| PickHighlight | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| PatternLock | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| RouteStick | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |

## PatternLock / RouteStick 演示帧数（合格带 750～1050）

| 环境 | episode | seed | 角色 | 演示帧数 | 秒（÷30） | 落在带内 |
|---|---|---|---|---|---|---|
| PatternLock | 0 | 11500000 | selected | 430 | 14.3 | False |
| PatternLock | 3 | 11500300 | selected | 470 | 15.7 | False |
| PatternLock | 6 | 11500600 | selected | 528 | 17.6 | False |
| RouteStick | 0 | 11600000 | selected | 650 | 21.7 | False |
| RouteStick | 3 | 11600300 | selected | 550 | 18.3 | False |
| RouteStick | 6 | 11600600 | selected | 650 | 21.7 | False |

## Swap 两环境外环交换窗口数 vs n_swaps

| 环境 | episode | seed | 演示成功 | n_swaps | 规划窗口数 | 运行时窗口数 | 相等 | 说明 |
|---|---|---|---|---|---|---|---|---|
| VideoUnmaskSwap | 0 | 10500000 | True | 7 | 7 | 7 | True |  |
| VideoUnmaskSwap | 3 | 10500300 | True | 7 | 7 | 7 | True |  |
| VideoUnmaskSwap | 6 | 10500600 | True | 7 | 7 | 7 | True |  |
| ButtonUnmaskSwap | 0 | 10700001 | True | 5 | 5 | 5 | True |  |
| ButtonUnmaskSwap | 3 | 10700300 | True | 5 | 5 | 5 | True |  |
| ButtonUnmaskSwap | 6 | 10700600 | True | 5 | 5 | 5 | True |  |

## VideoRepick 每局参与交换的方块数

| episode | seed | 演示成功 | 交换次数 | 参与方块数 | 来源 | 说明 |
|---|---|---|---|---|---|---|
| 0 | 10900000 | True | 6 | 5 | spec |  |
| 3 | 10900301 | True | 6 | 5 | spec |  |
| 6 | 10900601 | True | 6 | 5 | spec |  |
