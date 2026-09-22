# 四环境同步复验（2026-09-22）

12.23 的欠账收口。那次提交在**步 5d 正式验收已经开跑之后**改了四个环境的源码，当时写明
「未同步到集群……取值全部不变，预期不影响产物，但仍须实跑确认」。本文是那次「实跑确认」。

判定行：

```
FOUR_ENV_RESYNC_PARITY=PASS compared=108 sha_equal=108 field_mismatch=0 sidecar_mismatch=0
```

## 一、要验什么：12.23 动过的每一处

改动集中在四个环境，性质分两类。

**（甲）快照记了值、代码还在用内联字面量 —— 改成真的去读快照，取值照抄。**

| 环境 | 位置 | 原字面量 → 现读取 |
|---|---|---|
| SwingXtimes | `_load_scene` | `cubes_per_color = 1` → `parameters.cubes_per_color` |
| SwingXtimes | `_load_scene` | 颜色池 `(1,0,0,1)/(0,0,1,1)/(0,1,0,1)` → `parameters.color_pool`（顺序仍是红、蓝、绿） |
| SwingXtimes | 子目标表 | `distance_threshold=0.03`、`z_threshold=0.12`、`height=0.1` → `parameters.swing_thresholds` 的 `distance`／`z`／`height`，四处 lambda 与两处注释一并改 |
| PickHighlight | `_load_scene` | 同样的三色池 → `parameters.color_pool` |
| PickHighlight | `_load_scene` | `torch.randint(0, ...)` 的下界 → `parameters.color_draw.low` |

**（乙）归属修正 —— `color` 从 `decision` 移到 `native.parameters`。**

VideoPlaceButton／VideoPlaceOrder 两个环境，方案 2.11／2.12 把 `color` 列在 native
（「规则不改，只外部生成本局值」），我原先放进了 decision。`native_blocks()` 与消费点
（`if idx < ...["color"][self.difficulty]`）同步改。

这一类改动的特殊之处：**它改了配置文件的结构**。实测两版 `native_sampling.json`：

```
VideoPlaceButton 旧 decision 有 color: True | 旧 native.parameters 有 color: False
VideoPlaceButton 新 decision 有 color: False | 新 native.parameters 有 color: True
  取值相同: True
VideoPlaceOrder  同上
```

## 二、怎么验：同机同卡的新旧对比，不跟 5d 老产物比

原计划是把集群克隆同步到最新提交，重跑这四个环境，跟 5d 存的 A40 产物对。这条路走不通
（见第四节），改成本机方案，而且这个方案其实更干净：

- 用 `git worktree` 拉出 12.23 之前的 `a38a614`，与当前 `460c996` 各跑一遍这四个环境的
  **B／C／D 三路 × 9 条身份**（子集里每环境的全部 9 条）。
- **两侧各用自己那一版的 `native_sampling.json`** —— 这是关键。乙类改动的配置结构不同，
  只有让两边各读各的配置，才真正验到「归属换了、数值没换」。
- A1／A2 不跑：它们走 `git archive` 出来的官方隔离源码树（`d53f21a`），与工作区 `src`
  无关，12.23 碰不到。
- **严格串行，单进程，锁 `CUDA_VISIBLE_DEVICES=0`。** 本机有两张卡，但 5c／5d 已证明
  并行争抢会破坏逐位可复现（`mplib` 的 RRT 用墙钟预算），这里宁可慢也不引入该变量。

这样问的是「这次改动改没改输出」，同机同卡自相对照即可回答，**不掺 GPU 架构差异**——
比拿 sm_89 的新产物去对 A40 的老产物更少一层噪声。

## 三、结果

216 次生成（4 环境 × 2 版本 × 3 路 × 9 条）零失败，108 对比较零差异：

| 环境 | old↔new B | old↔new C | old↔new D | 单路耗时 |
|---|---|---|---|---|
| SwingXtimes | 9/9 | 9/9 | 9/9 | 169 s |
| PickHighlight | 9/9 | 9/9 | 9/9 | 162 s |
| VideoPlaceButton | 9/9 | 9/9 | 9/9 | 330 s |
| VideoPlaceOrder | 9/9 | 9/9 | 9/9 | 407 s |

每对都是整文件 SHA-256 相同、h5py 递归逐字段零差异、伴生文件（含 MP4）零差异。

**结论：12.23 的改动确为等值重构，5d／5e 的验收结论不因它失效。** 其中 SwingXtimes 一个环境
就占五处改动，它在默认配置（B 路）下逐位不变；两个 Video 环境则在**配置结构不同**的
C／D 两路下逐位不变。

产物：`artifacts/train-parity/local-recheck/{old,new}/<环境>/`，
比较明细 `artifacts/train-parity/local-recheck/compare/<环境>/h5_pairs.jsonl`。

## 四、顺带查出的阻塞：greatlakes 全分区 GPU 转为 Exclusive_Process

集群路线第一步就失败了：B 路九条全部报
`vk::PhysicalDevice::createDeviceUnique: ErrorInitializationFailed`，日志里新出现
`CUDA device 0 is in EXCLUSIVE or EXCLUSIVE_PROCESS mode` 警告。

日志能把时间点卡死：

| 批次 | 含 EXCLUSIVE 警告 | 日志最后写入 |
|---|---|---|
| gl-5a / 5c / 5d / 5d-w4 | **0 / 152** | 09-21 19:08 ～ 09-22 00:17 |
| gl-recheck | 6 / 12 | 09-22 01:14 |
| gl-vktest（新 job，spgpu A40） | 1 / 1 | 09-22 01:17 |

152 份日志一次没出现过，01:13 之后写的每份都有。**变更发生在 09-22 00:17～01:13 之间。**

排查过的（都不是原因）：

- 不是占位 job 的问题——新提交的独立 job 61705841（gl1508）同样失败。
- 不是分区的问题——`gpu` 分区的 V100（job 61705900）同样 `Exclusive_Process`、同样失败。
- 不是 srun 参数的问题——加 `--gres=gpu:1`、去掉 `--exact` 都试过。
- 不是残留进程——`nvidia-smi` 显存 0 MiB、无任何 compute app。
- 不是驱动变更——前后都是 595.71.05。

唯一已知绕法是 `SAPIEN_DISABLE_RAY_TRACING=1`，但它换的是渲染路径，产物必然不再逐位相同，
**对拍任务不能用**。这条在恢复前挡住一切集群上的生成，包括可选的步 7 全集 1600 条。
四个占位 job 仍在跑（约剩 40 h），暂时留着；NFS 克隆已同步到 `460c996`。
