# P1 探针报告：PickXtimes 方块区域半宽 0.2 与 0.25 对比（V5 计划待决项 L46）

日期 2026-09-24。在 worktree `/data/hongzefu/robomme_v5_probe_wt`（提交 581efec）里用进程内 monkeypatch 与离线副本完成，未修改任何被 git 跟踪的文件。
本文由主会话根据本目录原始日志整理（探针 agent 在加量补跑时被主会话停止，其补跑结果一并计入）。

## 规则（V5 计划 1.4 的 L43～L45 结论）

xhard 下取消 `corner_bias`（全部均匀）、6 块两两中心距 ≥ 0.08、已放方块用精确 OBB 作障碍、`max_trials` 1024；圆盘区域与 G1「先放盘」不变。
比较方块区域半宽 0.2（现值）与 0.25。

## 校验（`validate_replica.log`）

离线副本在无新规则下与 v4-01 冻结规格逐位一致：`REPLICA_EXACT=20/20`（PickXtimes 与 SwingXtimes 各 10 行）。

## 离线副本（每组 3000 局，`offline_N3000.log`、`offline_failrate_xcheck.log`）

| 指标 | 半宽 0.2 | 半宽 0.25 |
|---|---|---|
| reset 失败率（1024 次） | 0/3000 | 0/3000 |
| 中心距 < 8 cm 的对 | 0 | 0 |
| 中心距 < 10 cm 的对（局占比） | 85.3% | 58.7% |
| 10 cm 三块团 | 33.5% | 10.2% |
| 目标圆盘离基座距离 中位 / p95 / 最大 | 0.556 / 0.693 / 0.715 m | 0.562 / 0.743 / 0.778 m |
| 目标 > 0.75 m 的局 | 0 | 3.1% |
| 任一方块 > 0.75 m 的局 | 0 | 18.5% |

对照：均匀 / corner_bias 0.5、精确 OBB / trimesh、256 / 1024 次的各种组合 reset 失败率都是 0/3000。

## 本机演示（`demo_hw0p20.log`、`demo_hw0p25.log`；seed 4100000～4100900 即 v4-01 的 10 个 seed，0.25 组另补 3 个远角 seed）

| 组 | 局数 | 成功 | 目标离基座最远 | 每局墙钟 |
|---|---|---|---|---|
| 半宽 0.2 | 10 | **10/10** | 0.657 m | 94～265 s |
| 半宽 0.25 | 13 | **13/13** | **0.765 m**（seed 4100003；4100009 / 4100020 为 0.753） | 93～265 s |

两组同 seed 的耗时几乎一致；补跑的 3 个远角 seed 专挑目标圆盘离基座 > 0.75 m 的布局，全部成功，说明 0.25 半宽下远角可达。

## 判定行

```
P1_PICK_REGION=REPORT hw0p20: reset_ok=3000/3000 demo_ok=10/10 | hw0p25: reset_ok=3000/3000 demo_ok=13/13 far_target_max=0.765
```

## 建议

取半宽 **0.25**：分散度明显更好（10 cm 三块团 33.5% → 10.2%），reset 与演示都没有代价。盲区：演示样本 13 局；目标 > 0.77 m 的布局（离线最大 0.778 m）没有实跑到。

## 文件索引

`patch_p1.py`、`demo_p1.py`、`pick_seeds.py/.log`、`offline_N3000.log`、`offline_failrate_xcheck.py/.log`、`validate_replica.log`、`selfcheck.log`、`demo_hw0p20/`、`demo_hw0p25/`（h5 与视频）。
