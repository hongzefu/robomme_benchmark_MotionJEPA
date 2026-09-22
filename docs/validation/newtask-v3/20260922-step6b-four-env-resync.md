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

## 三·五、集群侧复核（2026-09-22，原定做法）

`--gpu_cmode=shared` 把集群恢复可用之后，把原定做法也补做了：当前 HEAD 在四个 spgpu 占位 job 上
跑同样的 B／C／D × 9 条，与**步 5d 存档的 A40 产物**逐位对拍。这比本机那轮更进一步——
证的是「改完之后仍能一字不差复现已经进了判据的那批数据」。

108 次生成零失败，108 对比较里 **107 对逐位相同**：

| 环境 | B | C | D |
|---|---|---|---|
| SwingXtimes | 9/9 | 9/9 | 9/9 |
| VideoPlaceButton | 9/9 | 9/9 | 9/9 |
| VideoPlaceOrder | 9/9 | 9/9 | 9/9 |
| PickHighlight | **8/9** | **8/9** | **8/9** |

### 唯一的例外：`PickHighlight/episode_3`

5d 是 647 帧，本次是 641 帧，从 `timestep_549` 起分叉，三路差法完全一致
（各 `field_mismatch=1161`）。

**与本次改动无关**，两条独立证据：

1. **本次运行内三路两两逐位相同**：`rc.B|rc.C`、`rc.C|rc.D`、`rc.B|rc.D`
   各 `compared=9 sha_equal=9 field_mismatch=0`；
2. 本机新旧代码对比里这条身份三路全同（见上一节）。

真正的原因是这条身份对**时序**敏感：它是 `FailRecoverXY` + hard，失败恢复要重规划，
而 `mplib` 的 RRT 用墙钟预算（`planning_time=1`），卡在临界点上。它正是 5d 首轮 4 worker 时
暴露非确定性的同一条（当时 641 vs 643）。5d 跑在 gl1517、本次跑在 gl1508，机器与时间都变了。

**由此要修正一个说法**：「单 worker 可逐位复现」只在**同一次运行内**成立，跨运行、跨节点不保证。
`NODE_PARITY=PASS`（步 P0）只验过一条身份，撑不起「任意身份跨节点可复现」。
详见 [多 worker 专题的第六节补记](20260921-worker-nondeterminism.md)。

**对判据无影响**：所有判据比的都是同一次运行内五路之间的关系，这些路背靠背产出、共享同一段机器时间。

## 四、顺带踩到的坑：GPU compute mode 与 `--gpu_cmode`

集群路线第一步失败：B 路九条全部报
`vk::PhysicalDevice::createDeviceUnique: ErrorInitializationFailed`，日志里新出现
`CUDA device 0 is in EXCLUSIVE or EXCLUSIVE_PROCESS mode` 警告。

### 原因与解法

greatlakes 的 sbatch／srun 有一个选项：

```
--gpu_cmode=<shared|exclusive|prohibited>
        Set the GPU compute mode on the allocated GPUs to
        shared, exclusive or prohibited. Default is exclusive
```

**默认是 `exclusive`。** 而本链路在一个进程里需要两个独立的 GPU context——torch 的 CUDA
context，加上 svulkan2 建 Vulkan logical device 时为 CUDA-Vulkan 互操作开的那个。
`Exclusive_Process` 只给一个名额，torch 先拿到，Vulkan 再要就被拒。

**解法是提交时显式写 `--gpu_cmode=shared`。** 实测在既有的占位 job 上：

```
srun --jobid=<hold> --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared ...
MODE=Default
RUN_PATH path=B identities=1 ok=1 failed=0 exit=0 elapsed_s=35.336
VULKAN_FAILS=0
```

compute mode 变回 `Default`，生成正常。5a／5c／5d 当时跑的就是 `Default`，所以加这个参数是
**回到原状态**，不影响逐位可比。

### 仍未解释清楚的部分

日志能把时间点卡死：gl-5a／5c／5d／5d-w4 共 152 份日志（09-21 19:08 ～ 09-22 00:17）零警告，
01:13 之后写的每一份都有。也就是说**同样不带 `--gpu_cmode` 的提交，00:17 之前是 `Default`、
01:13 之后是 `Exclusive_Process`**——这个开关是什么时候、因为什么生效的，从用户侧查不出来
（`Prolog` 脚本与 `gres.conf` 在登录节点不可读，节点 BootTime 都是一两个月前、期间没重启）。
结论上不重要：**以后所有提交都显式带 `--gpu_cmode=shared` 即可**，不要依赖默认值。

### 记一笔教训

我一度据此判断「全集群阻塞、只能报 ARC-TS」，并按这个判断往 `gpu`／`gpu-rtx6000`／`gpu_mig40`
几个分区提了探针 job。这个判断是错的——**`sbatch --help` 里就写着解法**，代价是几个不该提交的
job。排查外部环境问题时应先把命令自带的帮助与选项读完，再下"无解"的结论。
（另：用户已明令 greatlakes 上只许用 `spgpu` 分区。）
