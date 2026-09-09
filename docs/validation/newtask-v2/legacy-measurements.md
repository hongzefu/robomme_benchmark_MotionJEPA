# 旧链路退出前的历史实测数字摘录

`newtask-v2` 第五步按方案第七节清理了若干旧脚本目录。方案要求：这些目录退出工作树之前，
把其中两份报告里的实测数字摘录出来留档。本文件即该摘录。

**这是历史记录，不是本轮结论。** 原文可从固定 Git 历史追溯（例如
`git show 94449db:scripts/data-generation-newSeed/reports/joint_action_diff_full.md`）；
它们跑的是**旧链路、旧对象、旧判据**，与 newtask-v2 三路对拍的
[逐位、不设容差、全字段](20260908T2255Z-parity15-3804e87/README.md) 判据不是一回事，
不能互相替代，也不能拿来充抵本轮的对拍结论。

## 一、`scripts/data-generation-newSeed/reports/joint_action_diff_full.md`

对比对象：`/data/hongzefu/robomme_data_h5/record_dataset_{task}.h5`（原版官方数据）
与本仓库无 seed 链路的生成产物。比对字段只有 `action/joint_action`（8 维 float64），
逐 timestep 逐元素取绝对差，**判定阈值 `1e-08`**（不超过即视为逐位相同）。

| env | 总数 | 同 seed | 异 seed | 已比对 | 逐位相同 | 有差异 | 最大绝对差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| VideoUnmaskSwap | 100 | 98 | 2 | 98 | 97 | 1 | 2.146e-06 |
| VideoUnmask | 100 | 99 | 1 | 99 | 99 | 0 | 2.078e-17 |
| ButtonUnmaskSwap | 100 | 97 | 3 | 97 | 96 | 1 | 1.788e-06 |
| ButtonUnmask | 100 | 98 | 2 | 98 | 97 | 1 | 3.576e-07 |
| **合计** | **400** | **392** | **8** | **392** | **389** | **3** | **2.146e-06** |

即 **389/392 条（99.2%）逐元素完全相同**，3 条有差异：

| env | ep | seed | timestep 数 | 最大绝对差 | 平均绝对差 | 超差元素 | 占比 | 最大差位置 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| VideoUnmaskSwap | 88 | 13800 | 453 | 2.146e-06 | 5.772e-08 | 657/3624 | 18.13% | t=452, j=3 |
| ButtonUnmaskSwap | 87 | 15700 | 443 | 1.788e-06 | 7.645e-08 | 1074/3544 | 30.30% | t=442, j=3 |
| ButtonUnmask | 55 | 13500 | 363 | 3.576e-07 | 8.813e-09 | 294/2904 | 10.12% | t=333, j=3 |

三条的差异都集中在轨迹末段、夹爪维 j7 恒为 0，量级 1e-06 以下。

**与本轮的关系：** 这份报告用的是 `1e-08` 容差、只比一个字段、比的是「本仓库 vs 官方数据」。
newtask-v2 的三路对拍比的是「本仓库原版 vs 本仓库新版」，**全字段、逐元素、按浮点位模式、
不设任何容差**，15 格差异数全部为 0。两者的对象和判据都不同。

## 二、`scripts/400ep-dataset/run-log.md`

四个 Unmask 系 env 从 ep0–99 扩到 ep0–399 的实测记录（2026-08-18）：

| 项目 | 值 |
| --- | --- |
| 冒烟（2 条） | 2/2 成功，13.8 s（单条 8.3 / 8.6 s，attempt 均为 0），worker 峰值 RSS 2285 MB |
| 官方 h5 拆分 | 4 env × 100 = 400 条全部写出，256.7 s，`EXIT_CODE=0`，合计 77 GB |
| ep100–399 正式生成 | **1200/1200 成功**，`exhausted_count=0`，`EXIT_CODE=0` |
| attempt | 全部 1200 条 **attempt=0 一次通过**，零 seed 演进 |
| 耗时与吞吐 | 2500.6 s（41.7 分钟），稳态 **28.79 ep/min** |
| worker 峰值 RSS | 4357 MB |
| 产物 | 1200 个 h5（约 224 GB）+ 视频 |
| 当时的轻量测试 | 129 passed + 4 failed，239.4 s |

日志里的 `screw plan failed` 行是 planner 内部 screw→RRT\* 的正常降级重试，不是 episode 失败。

当时的 4 项轻量测试失败（`test_TaskGoal` 2 个、`test_step_error_handling` 2 个）被判为
与该轮无关的存量失败；**newtask-v2 在固定基线 worktree 上复测确认这 4 项在
`94449db` 上同样失败**，与本轮改动无关。

**与本轮的关系：** 上表的耗时与吞吐是**多 worker、多 GPU、100 条量级**的批量生成口径；
newtask-v2 三路对拍固定 `--workers 1 --gpus 0 --max-attempts 1`、每格单条，
两者的耗时不可直接比较。本轮实测耗时见
[实测报告第 3 节](20260908T2255Z-parity15-3804e87/README.md)。
