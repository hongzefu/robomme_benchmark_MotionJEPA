# V5 生成报告

- 来源：drafts `/tmp/v6-gl-smoke-61890467-binf-xhard1-20260926T195419Z/xhard1/draft/drafts.jsonl`；specs `/tmp/v6-gl-smoke-61890467-binf-xhard1-20260926T195419Z/xhard1/specs.jsonl`；rollout `/tmp/v6-gl-smoke-61890467-binf-xhard1-20260926T195419Z/xhard1/rollout/run1`；run_id `/tmp/v6-gl-smoke-61890467-binf-xhard1-20260926T195419Z`
- 口径：每环境候选目标 1 条；正式局 index [0]；演示帧数合格带 750～1050（`info/is_video_demo` 为真的帧数）

```text
V5_GENERATION=REPORT tasks=1 draft_ok=1 rollout_ok=1 backfilled=0 selected_shortfall=0 demo_frames_out_of_band=N/A outer_swap_mismatch=N/A bin_collision=0 vr_min_participants=N/A
```

草稿尝试 1、成功 1、候选缺口 0；实跑 1 局、成功 1、递补成功 0、正式局缺口 0；抽签期 BinCollisionError 0。

## 逐环境

| 环境 | draft_attempted | draft_ok | candidate_shortfall | 抽签失败类别 | 正式局目标 | rollout_attempted | rollout_ok | backfilled | selected_shortfall | by_class |
|---|---|---|---|---|---|---|---|---|---|---|
| BinFill | 1 | 1 | 0 | — | 1 | 1 | 1 | 0 | 0 | — |

## PatternLock / RouteStick 演示帧数（合格带 750～1050）

| 环境 | episode | seed | 角色 | 演示帧数 | 秒（÷30） | 落在带内 |
|---|---|---|---|---|---|---|

## Swap 两环境外环交换窗口数 vs n_swaps

| 环境 | episode | seed | 演示成功 | n_swaps | 规划窗口数 | 运行时窗口数 | 相等 | 说明 |
|---|---|---|---|---|---|---|---|---|

## VideoRepick 每局参与交换的方块数

| episode | seed | 演示成功 | 交换次数 | 参与方块数 | 来源 | 说明 |
|---|---|---|---|---|---|---|
