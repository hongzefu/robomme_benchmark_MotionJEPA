# 最终验收汇总（2026-09-22）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第四节的完成条件。
分支 `newtaskRelease-v3`，从 `ce72b04` 切出。

## 一、第一轮目标达成情况

方案第一轮的目标是：**十六个环境都能显式传入 `sampling_config` 与 `episode_spec`，
从官方 train 的 1600 条实际身份中按每 task 每难度约 3 条抽 144 条重放，证明注入前后保持一致。**

**达成。** 144 条身份 × 五路 = 720 次生成全部成功，720 对逐位比较零差异：

| 比较对 | 证明什么 | 结果 |
|---|---|---|
| `A1↔A2` | 官方基线自身可重复 | 144/144 散列相同 |
| `A1↔B` | 原行为已恢复 | 144/144 散列相同 |
| `B↔C` | 显式传原值配置不改数 | 144/144 散列相同 |
| `C↔D` | 原值规格回注不改数 | 144/144 散列相同 |
| `A1↔D` | **端到端**：官方原链路 ≡ 完整注入链路 | 144/144 散列相同 |

整文件 SHA-256 相同，字段与伴生文件（含 MP4）零差异。

## 二、判据总表

| # | 判定行 | 结果 |
|---|---|---|
| G1 | `TRAIN_IDENTITY=PASS tasks=16 rows=1600 mismatch=0` ＋ `TRAIN_SUBSET=PASS rows=144` | ✅ |
| G2 | `SAMPLING_ORIGINAL=PASS tasks=16 value_mismatch=0 unmapped=0` | ✅ |
| G3 | `FIELD_OWNERSHIP=PASS tasks=16 unmapped=0 native_rule_overrides=0` | ✅ |
| G4 | `SPEC_BINDING=PASS missing=0 unused=0 mismatch=0`（四片） | ✅ |
| G5 | `COMPARATOR_SCOPE=PASS contiguous_mismatch=0 sparse_mismatch=0 invalid_accepts=0` | ✅ |
| P0 | `NODE_PARITY=PASS identities=1 jobs=4 mismatch=0` | ✅ |
| P1 | `BASELINE_REPEAT=PASS compared=180 different=0`（四片） | ✅ |
| P2 | `A1↔B` 144/144 逐字节相同 | ✅ |
| P3 | `RNG_PARITY=PASS calls_mismatch=0 state_mismatch=0` | ✅ |
| P4 | `B↔C`／`C↔D`／`A1↔D` 各 144/144 | ✅ |
| P5 | `VIDEO_PARITY=PASS frames_mismatch=0 pixels_mismatch=0`（四片） | ✅ |
| P6 | `WORKER_ISOLATION=PASS tasks=2 mismatch=0 input_mutation=0` | ✅ |
| P7 | `RECOVERY_PARITY=PASS z=48 xy=32 off=64 mode_mismatch=0 event_mismatch=0` | ✅ |
| C1 | `TRAIN_COVERAGE=PASS expected=144 terminal=144 missing=0` | ✅ |
| 5b | `SUBSET_BRANCH_COVERAGE=PASS cells=48/48 gaps=0` | ✅ |
| 6b | `FOUR_ENV_RESYNC_PARITY=PASS compared=108 sha_equal=108 field_mismatch=0` | ✅ |
| R1a | `DATASET_GEN_REPORT_PARITY=FAIL detail_mismatch=38 outcome_mismatch=0` | ⚠ 见第三节 |
| R1b | `REFERENCE_AUDIT_COMPLETE=PASS compared=144 contract_errors=0 missing=0`；动作数值 `passed=False` | ⚠ 见第三节 |
| R1c | `HISTORICAL_ACTION_PARITY=NOT_RUN reason=historical_per_episode_evidence_missing blocking=0` | 📋 |
| R2 | `HISTORICAL_ARTIFACT_PARITY=NOT_RUN reason=historical_files_missing` | 📋 |

## 二·五、12.23 的欠账已补（判据 6b）

步 5d 开跑之后，12.23 改过四个环境的源码（SwingXtimes／PickHighlight／VideoPlaceButton／
VideoPlaceOrder），当时承诺「跑完再复验」。已补：用 `git worktree` 拉出改动前的 `a38a614`，
与当前提交在**同机同卡、严格串行**下各跑一遍这四个环境的 B／C／D × 9 条，
216 次生成零失败、108 对比较零差异。两个 Video 环境的 C／D 两路是**用各自结构不同的配置文件**
跑的（`color` 旧在 decision、新在 native），仍逐位相同。

详见 [四环境同步复验](20260922-step6b-four-env-resync.md)。同一份报告里还记了一件事：
**greatlakes 全分区 GPU 在 09-22 00:17～01:13 之间转为 `Exclusive_Process`，sapien 渲染器
自此起不来**，在恢复前挡住一切集群上的生成（包括可选的步 7）。

## 三、三条必须写进结论、不能淡化的边界

### 1. 多 worker 不可逐位复现

`mplib` 的 RRT 用**墙钟时间预算**（`planning_time=1`），并行争抢下同样 1 秒内迭代次数不同 →
搜出不同路径。实测：同一片 36 条身份，4 worker 时 `BASELINE_REPEAT=FAIL different=3064`、
`VIDEO_PARITY=FAIL pixels_mismatch=342`；换单 worker 后全部 PASS。

**所有进判据的数据都是单 worker 跑的。** 与之互补：进程复用（甲→乙→甲 同 PID）没问题（P6 PASS）。

### 2. R1a 有 38 条帧数与历史不符（跨 GPU 架构）

四片 `detail_mismatch` 分别 10／9／16／3，`outcome_mismatch=0`（身份、恢复模式、成功全部对齐）。
历史那轮跑在 `sled-vail`（RTX 6000 Ada，sm_89），本轮基线在 A40（sm_86）。
**这与接口改动无关**：同样这些环境的 `A1↔A2`、`A1↔D` 在 A40 上全部逐字节相同。
按用户 2026-09-21 决定：保留判据、逐条登记为硬件差异，不放宽字段范围。

### 3. R1b 的动作数值是 failed，且历史自己也是 failed

```
vectors=50228 elements=401824 different_elements=291961
max_abs_diff=0.019696838469699163 errors=39（全为 timestep sets do not match）
```

对照历史那轮对同一发布集的全集比较：`status=failed`、`different=217242`、`max_abs_diff=0.0078579`。
同源同量级，来源同样是跨 GPU 架构差异经求解器放大。
方案要求「审计完整 ≠ 数值相等，原 `1e-8` 失败照记、不改写成 PASS」，本轮照此执行。

## 四、结论

**本次 144 条子集的严格对拍通过**：注入前后逐位一致，两个接口在十六个环境上都已就位且被真正消费。

**不能外推的部分**：
- 结论只覆盖 144 条子集，不外推全集 1600 条（可选步 7 未启动）。
- 子集不含每环境 episode 5，共 16 条配置 xy 恢复的身份未验证。
- 与官方发布集的数值差异（R1a／R1b）属外部对照线，历史缺证的 R1c／R2 仍为 `NOT_RUN`。

## 五、待用户决策的一项

`RouteStick` 的白球尾迹已按方案恢复官方的 **40 步**（用户 2026-09-12 曾定为 10 步）。
它会渲进 `front/wrist` 的 rgb 与 depth，写死任一值都让「原值对拍」与「产品想要的短尾迹」二选一，
因此外提为 `sampling_config.positions.tcp_trail.end_offset_steps`，默认 40。
**要切回 10 步，传配置即可，不必改源码。** 建议等新值模式启动时作为 `decision` 打开。
