# 专题：多 worker 并行会破坏逐位可复现（2026-09-21）

这条发现改变了步 5d 的跑法，单独成文。相关闸门：P1（`BASELINE_REPEAT`）、P5（`VIDEO_PARITY`）、P6（`WORKER_ISOLATION`）。

## 一、怎么撞上的

步 5c 用 4 个环境（`BinFill`／`VideoUnmaskSwap`／`VideoPlaceOrder`／`InsertPeg`）各 9 条身份验证「单 worker 与 4 worker 产物逐位相同」，144 对比较全部通过，于是步 5d 放开用 4 worker 跑 144 条五路。

5d 的第 3 片（`VideoRepick`／`VideoPlaceButton`／`VideoPlaceOrder`／`PickHighlight`）报出：

```text
[shard3/4] BASELINE_REPEAT=FAIL compared=180 different=3064
[shard3/4] VIDEO_PARITY=FAIL compared=230 frames_mismatch=3 pixels_mismatch=342
```

拆开逐对看，问题集中在**一条身份**上：

| 比较对 | 36 条中散列相同 | 差异 |
|---|---|---|
| A1↔A2 | 35 | 1 条（1016 处字段） |
| A1↔B | 35 | 1 条（1024 处） |
| B↔C | 35 | 1 条（1024 处） |
| **C↔D** | **36** | **0** |
| **A1↔D** | **36** | **0** |

那条身份是 `PickHighlight/episode_3`，帧数在 **641 与 643** 之间跳：A1=641、A2=643、B=643、C=641、D=641。

## 二、溯源实验

两种可能必须分清：求解器本身非确定（方案预见过的 RRTStar 回退），还是 4 worker 并行引入的。做法是同一条身份重复跑：

| 条件 | 重复 | 帧数 |
|---|---|---|
| `--workers 1`，单身份 | 4 次 | 643, 643, 643, 643 ← **完全稳定** |
| `--workers 4`，9 条身份同批（复现 5d 条件） | 2 次 | 641, 643 ← **不稳定** |

**结论：非确定性由多 worker 并行引入，不是求解器固有的。**

## 三、机制

`mplib` 的 RRT 规划用**墙钟时间预算**：

```text
.venv/lib/python3.11/site-packages/mplib/planner.py:517   planning_time=1
.venv/lib/python3.11/site-packages/mplib/planner.py:539   planning_time: time limit for RRT
```

多 worker 争抢 CPU／GPU 时，同样 1 秒内的采样迭代次数不同 → 搜出不同路径 → 轨迹长度与全部下游观测都不同。这解释了三件事：

1. 只有少数身份受影响——只有三次 screw 失败、回退到 RRTStar 的那些才受时间预算影响；
2. 单 worker 稳定——没有争抢，1 秒内的迭代次数稳定；
3. 5c 的四个环境没暴露——它们那 36 条身份没有触发 RRT 回退，或触发后结果仍稳定。

即：**这不是本轮接口改动的问题，而是「带墙钟预算的规划器 + 并行争抢」的固有性质**；任何要求逐位复现的跑法都不能用多 worker。

## 四、处置

按方案步 5c 的失败处置「不一致回单 worker，不改 seed 与恢复」：

- 正式验收（5d）改回 `--workers 1` 重跑；4 worker 那批保留为 `artifacts/train-parity/gl-5d-w4`，作为争抢效应的证据，不进判据。
- 5c 的结论要按覆盖面重述：**它只证明了那 4 个环境的 36 条身份在两种 worker 数下相同，不能推广到十六环境**——反例正是 5c 未覆盖的 `PickHighlight`。

## 五、这条发现没有动摇的部分

4 worker 那批里，**`C↔D` 与 `A1↔D` 在四片共 144 条身份上全部逐字节相同**，包括那条不稳定身份。也就是说「显式传原值配置 + 回注冻结规格不改数」在并行争抢的条件下依然成立——因为 D 消费的是 C 冻结下来的规格，规格里已经钉死了那次规划的结果。

`SPEC_BINDING` 与 `RECOVERY_PARITY` 在四片上也全部 PASS（`missing=0 unused=0 mismatch=0`；恢复配置计数 z48／xy32／关闭64 与方案口径一致）。

---

## 六、补记（2026-09-22）：单 worker 也只在同一次运行内可复现

步 6b 的集群侧复核提供了一个更强的数据点：**同一条身份 `PickHighlight/episode_3`，两次都用单 worker，跨运行、跨节点，结果不同。**

| | 5d 正式验收 | 6b 集群复核 |
|---|---|---|
| 时间 | 2026-09-21 22:05 起 | 2026-09-22 10:09 起 |
| 节点 | gl1517（shard3） | gl1508 |
| worker | 1 | 1 |
| 帧数 | **647** | **641** |
| 分叉点 | — | `timestep_549` 起 |

三路 B／C／D 的差法完全一致（各 `sha_equal=8/9 field_mismatch=1161`）。

### 这说明什么

`planning_time=1` 是**墙钟**预算，所以影响它的不只是「有没有并行争抢」，还有**机器本身快慢与当时负载**。
`PickHighlight/episode_3` 是 `FailRecoverXY` + hard，失败恢复要重规划，是全集里规划最重的身份之一，
恰好卡在 1 秒预算的临界点上，机器状态一变，1 秒内搜到的路径就变。

### 这不说明什么

**不是代码改动造成的**，两条独立证据：

1. 本次运行内 B／C／D 两两逐位相同——`rc.B|rc.C`、`rc.C|rc.D`、`rc.B|rc.D` 各 `compared=9 sha_equal=9 field_mismatch=0`；
2. 本机新旧代码对比里，PickHighlight 九条（含 ep3）三路 27／27 全同。

### 要修正的说法

原先「单 worker 可逐位复现」应改为：**单 worker 在同一次运行内可逐位复现；跨运行、跨节点不保证。**

`NODE_PARITY=PASS`（步 P0）只验了一条身份，覆盖不到这种临界情况，**不能用它支撑「跨节点任意身份都可复现」。**

### 对判据的影响

**没有影响。** 所有判据比的都是**同一次运行内**五路之间的关系（A1↔A2、A1↔B、B↔C、C↔D、A1↔D），
这些路是背靠背产出的，共享同一台机器的同一段时间。6b 这次也一样：本次运行内三路两两相同。

**但有一条不能再说**：不能承诺「拿同一份清单换台机器重跑能得到同样的字节」。要复现 5d 的确切产物，
只能用 5d 存档本身。
