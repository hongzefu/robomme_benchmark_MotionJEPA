# 步 5a 报告：十六环境各一条身份走五路（2026-09-21）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 5a，闸门 P1／P5／P7（另带 G4、R1a）。运行目录 `artifacts/train-parity/gl-5a`，A40 上 4 个占位 job 并行，每环境取 `episode 0` 跑 A1／A2／B／C／D 五路。

## 一、结果

| 闸门 | 判定行 | 结果 |
|---|---|---|
| P1 官方基线自身可重复 | `BASELINE_REPEAT` | **16/16 PASS**（每环境 5 对比较 `different=0`） |
| G4 规格真正被消费 | `SPEC_BINDING` | **16/16 PASS**（`missing=0 unused=0 mismatch=0`） |
| P5 图像与录像事件 | `VIDEO_PARITY` | **16/16 PASS**（`frames_mismatch=0 pixels_mismatch=0`，容器散列即已相同） |
| P7 fail recover 原样 | `RECOVERY_PARITY` | **16/16 PASS**（`mode_mismatch=0 event_mismatch=0`） |
| R1a 历史可投影字段 | `DATASET_GEN_REPORT_PARITY` | **12 PASS / 4 FAIL**（见下节） |

HDF5 比较：16 环境 × 5 对（A1↔A2、A1↔B、B↔C、C↔D、A1↔D）＝ **80 对全部 `sha_equal=1 field_mismatch=0`**，伴生文件（含 MP4）散列相同，无仅单侧存在的身份。

## 二、R1a 的四条帧数差异

四条全部是 `timestep_count` 一项不符，身份、恢复模式与成功标志都一致（`outcome_mismatch=0`）：

| 身份 | 历史报告（sled-vail，sm_89） | 本次 A1（A40，sm_86） | 差 |
|---|---|---|---|
| InsertPeg/episode_0 | 475 | 476 | +1 |
| ButtonUnmaskSwap/episode_0 | 514 | 513 | −1 |
| VideoPlaceButton/episode_0 | 1048 | 1054 | +6 |
| VideoPlaceOrder/episode_0 | 1200 | 1006 | **−194** |

**这四条与本轮接口改动无关**，理由有三：

1. 比较的是 **A1 路**，即官方固定源码 `d53f21a…` 加官方 `_worker`，本轮一行未改；
2. 这四个环境的 `A1↔A2` 在 A40 上逐字节相同（`BASELINE_REPEAT=PASS`），说明 A40 上是确定性的；
3. 同样这四个环境的 `A1↔B↔C↔D` 四对比较全部逐字节相同，接口拆分与原值回注没有引入任何差异。

差值有正有负、量级不一，符合「不同 GPU 架构的数值差异经求解器（三次 screw 后回退 RRTStar）放大」的特征；方案第四节本来就登记了「A40 与本机 Ada 不逐位一致」这一前提，并据此要求五路全部在 A40 上跑。VideoPlaceOrder 的 −194 帧量级远大于其余三条，历史值 1200 看起来像撞上了步数上限，需要单独核实后再定性。

**按方案红线「不放宽判据」，本报告不修改 R1a 的字段范围，四条差异原样登记，处置交用户决定。**

## 三、覆盖边界

- 每环境仅 `episode 0` 一条：全是 `recovery_mode=z`，因此 P7 这一轮只覆盖 z 与「配置了恢复」这一种组合（`configured=1 z=1 xy=0 off=0`）。xy 恢复已在本机用 `BinFill/episode 4` 单独验过（规格里记下 `xy_signs=[-1,1]`、`seed_anchor=4401`、拒绝轨迹为空），集群侧的 xy 与关闭两种模式随步 5b 的 48 格子集覆盖。
- 未覆盖：48 个 task／难度格、`BinFill` 两种 dynamic、单双拾取、零／非零交换、连续 worker 污染（P6）、多 worker（5c）。
