# 步 5d 报告：144 条身份 × 五路完整验收（2026-09-22）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 5d，闸门 C1 及 P1～P7 在 144 条上的落地。运行目录 `artifacts/train-parity/gl-5d`，greatlakes A40 四个占位 job 按 `ALL_TASKS` 顺序分 4 片并行，**单 worker**。

## 一、为什么是单 worker

原计划用 4 worker（步 5c 在 4 个环境上验过等价）。5d 首轮用 4 worker 跑出 `PickHighlight/episode_3` 的非确定性，溯源确认是**墙钟时间预算 + 并行争抢**所致（详见 [专题](20260921-worker-nondeterminism.md)）。按方案「不一致回单 worker」改回单 worker 重跑；4 worker 那批保留为 `gl-5d-w4`，不进判据。

**同一片、同样 36 条身份、同样代码，只把 4 worker 换成 1 worker，非确定性即消失**：

| shard3 | 4 worker | 1 worker |
|---|---|---|
| `BASELINE_REPEAT` | FAIL `different=3064` | **PASS `different=0`** |
| `VIDEO_PARITY` | FAIL `pixels_mismatch=342` | **PASS `pixels_mismatch=0`** |

## 二、结果

**720 次生成全部成功，零失败。**

| 比较对 | 证明什么 | 结果 |
|---|---|---|
| `A1↔A2` | 官方基线自身可重复 | `compared=144 sha_equal=144 差异=0` |
| `A1↔B` | 原行为已恢复（P2） | `compared=144 sha_equal=144 差异=0` |
| `B↔C` | 显式传原值 `sampling_config` 不改数 | `compared=144 sha_equal=144 差异=0` |
| `C↔D` | 原值 `episode_spec` 回注不改数 | `compared=144 sha_equal=144 差异=0` |
| `A1↔D` | **端到端**：官方原链路 ≡ 完整注入链路 | `compared=144 sha_equal=144 差异=0` |

**合计 720 对比较，整文件 SHA-256 全部相同，字段与伴生文件（含 MP4）零差异。**

闸门判定行（四片各一组，此处合并表述）：

```text
BASELINE_REPEAT=PASS compared=180 different=0          ×4 片
SPEC_BINDING=PASS missing=0 unused=0 mismatch=0        ×4 片
VIDEO_PARITY=PASS frames_mismatch=0 pixels_mismatch=0  ×4 片（compared 180/180/230/185）
RECOVERY_PARITY=PASS configured=20 z=12 xy=8 off=16 mode_mismatch=0 event_mismatch=0  ×4 片
TRAIN_COVERAGE=PASS expected=144 terminal=144 missing=0
```

四片的恢复配置计数合计 **z=48／xy=32／关闭=64**，与方案口径 3 完全一致。

## 三、R1a：四片共 38 条帧数与历史不符

```text
shard1 detail_mismatch=10   shard2 detail_mismatch=9
shard3 detail_mismatch=16   shard4 detail_mismatch=3
outcome_mismatch=0（身份、恢复模式、成功标志全部对齐）
```

四片的 `detail_mismatch` 与 4 worker 那批**逐片相同**（10/9/16/3），进一步说明这与 worker 数无关。按用户决定「保留判据，逐条登记为硬件差异」：历史那轮跑在 `sled-vail`（RTX 6000 Ada，sm_89），本轮基线在 A40（sm_86），方案第四节本就登记了两者不逐位一致；而本轮 `A1↔A2`／`A1↔D` 在 A40 上全部逐字节相同，证明差异不来自接口改动。

## 四、耗时与存储

- 每片 180 次生成，单 worker 约 2.5 小时，四片并行。
- 产物约 200 GB（Turbo 余量 4.8 T）。

## 五、待办

- 正式 R1b：用本批 A1 路产物重跑合并与审计，替换 [预演数字](20260921-step5e-reference-audit.md)。
- 步 6 留档与使用说明。
