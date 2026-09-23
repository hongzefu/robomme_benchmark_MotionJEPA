# V1 原值回归（本机）：结论与一条负载敏感样本

> 口径 10 例外（用户 2026-09-22「原值回归只需要在本机器跑」）：本机改动前基线 `13e5151` 与改动后代码各跑 V3 的
> 144 条子集（easy/medium/hard，B 路、单 worker），HDF5 全字段逐位比。比较器 `train_split_parity.py compare`
> （先整文件 SHA-256，不同再逐路径比 dtype/shape/attr/字节）。

## 一、判定

| 对比 | 代码 | 判定行 |
|---|---|---|
| 全量 | 基线 `13e5151` vs 改动后 `6cc656f`（含录像器 5000 步上限 I1） | `H5_PARITY pair=base.B\|after.B compared=144 sha_equal=144 field_mismatch=0` |
| 补跑 | 基线 vs 当前 `00a94de`（6cc656f 之后只动 xhard 分支的 7 个环境，63 条） | `compared=63 sha_equal=62`，差 1 条：PickHighlight/3 |
| 负载对照 | PickHighlight/3 在**空闲机器**上：`13e5151`、`6cc656f`、`00a94de`×3、`3a7caaa`、`76e0fcd` | 全部 `8b62e873…`（彼此逐位相同） |
| 负载对照 | PickHighlight/3 在**繁忙机器**上：`13e5151`（基线运行时）、`6cc656f`（与 V6 14 worker 并行时） | 均为 `6e13e618…` |

⇒ **`NATIVE_REGRESSION=PASS`**：所有差异都能用运行负载解释，**同负载下改动前后逐位相同**；没有任何一条差异由代码改动引起。

## 二、PickHighlight/3 为什么随负载变

这局是 hard + `FailRecoverXY`，前 558 步逐位相同，第 559 步起动作分叉、总步数 655 vs 652。
同一份代码在空闲/繁忙两种负载下给出两个不同但各自可重复的结果，与 V3 已记录的现象一致：
`mplib` 的 RRT 回退用**墙钟时间**作搜索预算，负载改变单位时间内的搜索量，从而改变搜到的路径。
这也是口径 10「正式验收单 worker、同机型」的原因；V1 比较时两侧应处于相近负载（建议以后 V1 两侧都在空闲机器上跑）。

## 三、产物

- 基线：`artifacts/newtask-v4/v1-base-13e/`；改动后：`v1-after-6cc/`；补跑：`v1-sup-00a94de/`；
  对照：`v1-ph3-r1/`、`v1-ph3-r2/`、`ph3-6cc-idle/`、`ph3-13e-idle/`、`bisect-3a7caaa/`、`bisect-76e0fcd/`。
- 比较明细：`artifacts/newtask-v4/v1-compare/`、`v1-compare-sup/`、`v1-compare-ph3-r*/`。
