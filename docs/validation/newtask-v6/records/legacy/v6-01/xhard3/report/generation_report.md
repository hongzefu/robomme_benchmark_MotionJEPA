# V5 生成报告

- 来源：drafts `/tmp/v6-s4-v6-01/xhard3/draft/drafts.jsonl`；specs `/tmp/v6-s4-v6-01/xhard3/specs.jsonl`；rollout `/tmp/v6-s4-v6-01/xhard3/rollout/run1`；run_id `/tmp/v6-s4-v6-01`
- 口径：每环境候选目标 10 条；正式局 index [0, 3, 6]；演示帧数合格带 750～1050（`info/is_video_demo` 为真的帧数）

```text
V5_GENERATION=REPORT tasks=13 draft_ok=130 rollout_ok=39 backfilled=0 selected_shortfall=0 demo_frames_out_of_band=4 outer_swap_mismatch=0 bin_collision=0 vr_min_participants=6
```

草稿尝试 152、成功 130、候选缺口 0；实跑 39 局、成功 39、递补成功 0、正式局缺口 0；抽签期 BinCollisionError 0。

## 逐环境

| 环境 | draft_attempted | draft_ok | candidate_shortfall | 抽签失败类别 | 正式局目标 | rollout_attempted | rollout_ok | backfilled | selected_shortfall | by_class |
|---|---|---|---|---|---|---|---|---|---|---|
| PickXtimes | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| SwingXtimes | 11 | 10 | 0 | SceneGenerationError×1 | 3 | 3 | 3 | 0 | 0 | — |
| BinFill | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| VideoUnmaskSwap | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| VideoUnmask | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| ButtonUnmaskSwap | 11 | 10 | 0 | SceneGenerationError×1 | 3 | 3 | 3 | 0 | 0 | — |
| ButtonUnmask | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| VideoRepick | 20 | 10 | 0 | SceneGenerationError×10 | 3 | 3 | 3 | 0 | 0 | — |
| VideoPlaceButton | 11 | 10 | 0 | SceneGenerationError×1 | 3 | 3 | 3 | 0 | 0 | — |
| VideoPlaceOrder | 17 | 10 | 0 | SceneGenerationError×7 | 3 | 3 | 3 | 0 | 0 | — |
| PickHighlight | 12 | 10 | 0 | SceneGenerationError×2 | 3 | 3 | 3 | 0 | 0 | — |
| PatternLock | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |
| RouteStick | 10 | 10 | 0 | — | 3 | 3 | 3 | 0 | 0 | — |

## PatternLock / RouteStick 演示帧数（合格带 750～1050）

| 环境 | episode | seed | 角色 | 演示帧数 | 秒（÷30） | 落在带内 |
|---|---|---|---|---|---|---|
| PatternLock | 0 | 13500000 | selected | 571 | 19.0 | False |
| PatternLock | 3 | 13500300 | selected | 518 | 17.3 | False |
| PatternLock | 6 | 13500600 | selected | 549 | 18.3 | False |
| RouteStick | 0 | 13600000 | selected | 800 | 26.7 | True |
| RouteStick | 3 | 13600300 | selected | 700 | 23.3 | False |
| RouteStick | 6 | 13600600 | selected | 750 | 25.0 | True |

## Swap 两环境外环交换窗口数 vs n_swaps

| 环境 | episode | seed | 演示成功 | n_swaps | 规划窗口数 | 运行时窗口数 | 相等 | 说明 |
|---|---|---|---|---|---|---|---|---|
| VideoUnmaskSwap | 0 | 12500000 | True | 9 | 9 | 9 | True |  |
| VideoUnmaskSwap | 3 | 12500300 | True | 8 | 8 | 8 | True |  |
| VideoUnmaskSwap | 6 | 12500600 | True | 8 | 8 | 8 | True |  |
| ButtonUnmaskSwap | 0 | 12700000 | True | 6 | 6 | 6 | True |  |
| ButtonUnmaskSwap | 3 | 12700300 | True | 6 | 6 | 6 | True |  |
| ButtonUnmaskSwap | 6 | 12700600 | True | 7 | 7 | 7 | True |  |

## VideoRepick 每局参与交换的方块数

| episode | seed | 演示成功 | 交换次数 | 参与方块数 | 来源 | 说明 |
|---|---|---|---|---|---|---|
| 0 | 12900002 | True | 7 | 6 | spec |  |
| 3 | 12900302 | True | 8 | 6 | spec |  |
| 6 | 12900600 | True | 7 | 6 | spec |  |
