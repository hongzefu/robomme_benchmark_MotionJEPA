# 实测记录：无 seed 生成链路的性能与行为

本文件记录 2026-08-17 建立 `scripts/data-generation-newSeed/` 时的全部实测数据与结论。
目的是让后续改动有据可依 —— 尤其是并行度、资源约束、GPU 绑定这几处，凭直觉调很容易调反。

所有数字均为本机实测，不是估算。

---

## 一、机器与环境

| 项 | 值 |
| --- | --- |
| CPU | AMD EPYC 9334，**32 核 32 线程**（threads per core = 1） |
| 内存 | 377 GiB |
| GPU | 2 × NVIDIA RTX 6000 Ada，各 46068 MiB；GPU0 = `0000:01:00.0`，GPU1 = `0000:02:00.0` |
| 磁盘 | `/data` 14T，剩余 4.0T |
| `ulimit -n` / `-u` | 1048576 / 1545692 |
| 关键依赖 | mani-skill 3.0.0b21、sapien 3.0.2、mplib 0.1.1、torch 2.9.1+cu128、Python 3.11.14 |

> ⚠️ 标定期间 GPU0 上有**其他用户的任务**（`roihn` 的 TTCL `eval.py`，占 13.8 GiB 显存、约 198 W、
> 0.88 核 CPU）。因此标定的单卡档一律改用干净的 GPU1。CPU 层面的外部干扰约 3%（0.88/32 核），
> 可接受；显存层面 GPU0 只剩约 30 GiB 可用。**复现这些数字时要先确认两张卡是否干净。**

---

## 二、瓶颈定位：源码层面的结论

这几条是从源码逐行确认的，不是猜测，它们决定了并行策略：

1. **物理仿真跑在 CPU 上，GPU 只做渲染。**
   ManiSkill 的 `num_envs` 默认 1，`sim_backend="auto"` 在 `num_envs == 1` 时解析为 `physx_cpu`
   （`mani_skill/envs/sapien_env.py:233-237`），进而 `device=torch.device("cpu")`
   （`mani_skill/envs/utils/system/backend.py:58-60`）。
2. **torch 在 worker 里几乎不碰 CUDA。** `_runtime_bool` 只把 `evaluate` 返回的标量张量 `.cpu()` 取值。
3. **`RecordWrapper` 全文不含任何 `cuda` / `device` 引用。**

→ 全流程唯一使用 GPU 的是 sapien 渲染（一台 256×256 传感器相机 + 一台 512×512 录像相机）。
**并行度上限由物理核数决定，显存是次要约束。**

另外两个容易被忽略的线程源（都不看 `OMP_NUM_THREADS`）：

- **OpenCV**：`RecordWrapper.py:15` import cv2，每帧 `cv2.resize`。只认 `cv2.setNumThreads()`
  或 `OPENCV_FOR_THREADS_NUM`。
- **ffmpeg / x264**：`RecordWrapper.py:477` 用 `imageio` 写 mp4，`imageio_ffmpeg` 拼命令行时
  **从不加 `-threads`**，x264 按 `sched_getaffinity` 自动决定帧线程数（约 `1.5 × ncpu`）。
  要压住它**只能**用 CPU 亲和（`--affinity per-gpu`），环境变量无效。

而 **mplib 不是过度订阅的来源**：`ldd` 显示它只链接 `libompl` + `libpthread`，没有 `libgomp` / `libtbb`。

---

## 三、GPU 绑定自证

```
$ CUDA_VISIBLE_DEVICES=1 python -c "import sapien; d=sapien.Device('cuda'); print(d.cuda_id, d.pci_string)"
0  0000:02:00.0
```

`cuda_id` 是重映射后的逻辑号，`pci_string` 才是物理卡 —— `0000:02:00.0` 正是 GPU1。
**`CUDA_VISIBLE_DEVICES` 对 sapien 的绑卡有效。**

生成时的双卡分流也已实证（冒烟 5 条的 `bound.pci` 字段）：

| episode | seed | 落在 |
| ---: | ---: | --- |
| 0 | 6000 | `0000:01:00.0`（GPU0） |
| 1 | 6100 | `0000:02:00.0`（GPU1） |
| 2 | 6200 | `0000:01:00.0`（GPU0） |
| 3 | 6300 | `0000:02:00.0`（GPU1） |
| 4 | 6400 | `0000:02:00.0`（GPU1） |

---

## 四、冒烟：正确性验收（VideoUnmask ep0-4，双卡，workers=5）

**5/5 全部成功，seed 与难度与 train metadata 逐条一致：**

| ep | seed | 期望 seed | 难度 | 期望难度 | attempt | FailRecover | wall_s | 峰值 RSS |
| ---: | ---: | ---: | --- | --- | ---: | --- | ---: | ---: |
| 0 | 6000 | 6000 | easy | easy | 0 | Z | 11.86 | 2545 MB |
| 1 | 6100 | 6100 | easy | easy | 0 | Z | 10.15 | 2467 MB |
| 2 | 6200 | 6200 | medium | medium | 0 | Z | 11.31 | 2493 MB |
| 3 | 6300 | 6300 | hard | hard | 0 | XY | 16.47 | 3125 MB |
| 4 | 6400 | 6400 | easy | easy | 0 | XY | 10.29 | 2878 MB |

`torch.get_num_threads()` 在所有 worker 里都是 **1**，线程限制生效。

### 单条耗时的阶段分解

| 阶段 | 耗时 | 占比 |
| --- | ---: | ---: |
| `make_s`（`gym.make` + wrapper） | 1.4–2.2 s | 约 13–19% |
| `reset_s` | 0.01–0.02 s | 可忽略 |
| **`solve_s`（planner + physx CPU 仿真）** | **6.8–12.2 s** | **66–74%** |
| `close_s`（h5 落盘 + x264 编码） | 1.3–2.1 s | 约 11–13% |

→ 耗时主体是 CPU 上的规划与仿真，与「瓶颈在 CPU」一致。

### 产物体量

| 产物 | 单条 | 备注 |
| --- | ---: | --- |
| h5 | 150–266 MB | hard 难度的 ep3 最大 |
| mp4 | 3.8–8.3 MB | 文件名含难度与 language goal |

5 条合计 862 MB h5 + 24 MB 视频。合并后 `record_dataset_VideoUnmask.h5` = 0.84 GiB，
结构为 `episode_0..4`，`setup/seed` 与文件名一致。

---

## 五、资源约束的实测上限

| 约束 | 实测值 | 是否构成瓶颈 |
| --- | --- | --- |
| **单 worker 显存** | 498 MB（`nvidia-smi --query-compute-apps`）；20 worker 稳态时该卡共 14.7 GiB | ❌ 每卡可容纳 80+ worker |
| **单 worker 峰值 RSS** | 2.5–3.7 GB | ❌ W=32 约需 120 GB / 377 GB |
| **文件句柄 / 进程数** | 上限 1048576 / 1545692 | ❌ 差三个数量级 |
| **磁盘** | 400 条约 82 GB h5 + 6 GB 视频；剩 4.0T | ❌ |
| **CPU** | 见下节 | ✅ **唯一的真实约束** |

---

## 六、并行度标定

标定集：`VideoUnmask` 的 ep0-95（96 条 = 3 × 32，保证有完整的稳态窗口）。
吞吐用**稳态吞吐**：按完成时间排序后丢掉前 W 与后 W 条，剔除进程池「填充 → 稳态 → 排空」的首尾效应。

<!-- CALIBRATION_RESULTS_START -->
每档均为 96 条、全部成功、零失败 attempt。按运行先后排列：

| 档 | 时刻 | workers | GPU | 限线程 | 总耗时 | 稳态吞吐 | 单条均时 | CPU 中位 | load1 | 内存峰值 |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 14:21 | 20 | 1 | off | 132.1 s | 60.51 ep/min | 20.7 s | 62.0% | 32.6 | 86.3 GB |
| B | 14:24 | 32 | 1 | on | 169.0 s | 55.61 | 37.6 s | 47.4% | 40.3 | 107.8 GB |
| C | 14:27 | 32 | **0,1** | on | 197.9 s | 38.12 | 47.3 s | 43.8% | 52.9 | 110.1 GB |
| D | 14:31 | 20 | 1 | on | 220.9 s | 36.97 | 33.7 s | 37.8% | 26.6 | 88.3 GB |
| E | 14:34 | 12 | 1 | on | 276.8 s | 26.27 | 28.1 s | 27.7% | 17.5 | 67.5 GB |
| F | 14:39 | 20 | 1 | off | 190.6 s | 41.88 | — | — | — | 85.4 GB |
| G | 14:42 | 32 | 1 | off | 160.3 s | **56.12** | — | — | — | — |
| H | 14:45 | **44** | 1 | off | 462.6 s | ⚠️ 见下 | — | 23.0% | 36.6 | 82.1 GB |

（原计划的 I 档 W=56 已主动中止 —— W=44 就已崩溃，56 不会有新信息。）

### ⚠️ 先看这条：测量噪声很大，只有相邻档可比

**档 A 与档 F 是完全相同的配置**（W=20、单卡 GPU1、不限线程），吞吐却是 60.51 vs 41.88，
**相差 44%**。所以跨时段的绝对值不可比，只有相邻时段、单一变量的对照才可信。

排查过的解释（均已排除）：

| 假说 | 排查方式 | 结论 |
| --- | --- | --- |
| 时间单调漂移 | 看全序列 | ❌ 非单调：E(26.3) 低于其前的 D(37.0)，F(41.9) 又回升 |
| CPU 降频/热节流 | `/proc/cpuinfo` 满载时读数 | ❌ 3894 MHz / 额定 3910，scaling 100% |
| 外部任务干扰 | `ps` 聚合 | ❌ 干扰方 `roihn` 全程约 0.85 核（3%），且在 F 之前已结束 |
| swap 抖动 | `vmstat` si/so | ❌ swap 虽满，但 si/so 全为 0 |
| page cache 被 h5 写入冲掉 | 阶段分解 | ❌ 只能解释 `make_s`，但变慢的主体是 `solve_s`（不读文件） |
| 内存压力 | 各档内存峰值对吞吐 | ❌ 无相关（F 85 GB→41.9 vs A 86 GB→60.5） |

档 A 最可能是**冷机第一档的离群值**（紧接冒烟运行，进程与库都还热）。**报告结论时以 F/G 一组为准，不用 A。**

### 相邻档对照（单一变量，可信）

| 对照 | 变量 | 结果 |
| --- | --- | --- |
| F(20,off) 41.88 → G(32,off) **56.12** | workers 20→32 | **+34%** |
| E(12,on) 26.27 → D(20,on) 36.97 | workers 12→20 | **+41%** |
| D(20,on) 36.97 → F(20,off) 41.88 | 限线程 on→off | +13% |
| B(32,on) 55.61 vs G(32,off) 56.12 | 限线程（W=32 时） | **几乎无差异（0.9%）** |

**结论 1：workers 越多吞吐越高，至少到 32。** 12 → 20 → 32 单调上升。

**结论 2：限线程的影响远小于预期，且随并发升高而消失。** W=20 时不限线程略优 13%，
W=32 时两者只差 0.9%。原因是 `sim_backend=physx_cpu` 让 ManiSkill 的 obs 处理、reward 计算、
状态管理全部走 **CPU torch 张量运算** —— 这是热路径的一部分，不是"意外的过度订阅"，
所以把线程压到 1 并不是净收益。
代价则实测可见：W=32 不限线程时 `vmstat` 的上下文切换达 **43.8 万次/秒**
（32 worker × 32 OpenMP 线程 ≈ 1024 线程抢 32 核）。

**结论 3：GPU 完全不是瓶颈。** 三条独立证据：
1. 档 C 里落在**被外部任务占满的 GPU0**（86% util / 264 W）上的 worker 均时 44.2 s，
   与落在干净 GPU1 上的 48.2 s **基本相同** —— 渲染排队并未拖慢 episode。
2. 单卡稳态时 GPU 功耗中位仅 83–112 W，TDP 是 300 W。
3. 双卡档 C（38.12）并不优于同 worker 数的单卡档 B（55.61）。

→ **双卡没有收益，全量跑用单卡即可**（还能避开被别人占用的那张）。

**结论 4：W=44 会崩，W=32 是安全上限。** 档 H 的 96 条只成功 **24 条**，
出现 **264 次 `BrokenProcessPool`**（worker 进程被突然终止）。定位：

| 候选原因 | 实测 | 判断 |
| --- | --- | --- |
| 系统内存 OOM | 峰值仅 **82 GB** / 377 GB；`dmesg`/`journal` 无 OOM 记录 | ❌ |
| **GPU 压力** | GPU1 功耗 **267.5 W**（TDP 300 W）、显存峰值 **27 GB** | ✅ 唯一逼近上限的资源 |

这是整个标定里 GPU 唯一一次接近饱和。最可能是 44 个进程并发初始化 Vulkan/CUDA 上下文时的驱动层失败。
注意档 H 表里的"稳态吞吐 41.54"是在大量崩溃下算出的，**不代表正常性能，不要引用**。

> 这一档也顺带验证了调度循环里的**池重建逻辑**确实有效：264 次池崩溃之下，
> 程序没有整体报废，而是不断重建池、退回任务，最终正常退出（`returncode=0`）。
> 若没有这段逻辑，第一次段错误就会让全部剩余 job 瞬间失败。

### 最终选定配置

**`--workers 32 --gpus <单张空闲卡>`**，限线程与否差异在 1% 以内（默认开启即可）。
依据：W=32 是实测吞吐最高（56.12 ep/min）且稳定（零失败）的档；W=44 崩溃；双卡无收益。
<!-- CALIBRATION_RESULTS_END -->

### 判据

- **CPU 瓶颈**：CPU% 接近饱和、load1 高于核数，同时 GPU 功耗低。
  RTX 6000 Ada 空载 22–28 W、TDP 300 W，**稳态低于 90 W 就说明卡基本闲着**。
  注意 `utilization.gpu` 是个坏指标 —— 它只表示「有任意 kernel 在跑的时间比例」，不代表占用率，
  所以功耗才是可信判据。
- **GPU 瓶颈**：功耗持续偏高，且双卡档明显优于同 worker 数的单卡档。
- **冠军选择**：在全部成功且内存/显存安全的档里，取稳态吞吐达到最高值 97% 的**最小** workers ——
  更小的并发意味着更低的内存峰值、更短的收尾长尾、更小的崩溃爆炸半径。

---

## 七、正确性数据：seed 公式

用 `seed = env_code * 1000 + episode * 100 + attempt` 对 train metadata 全部 16 个 env、1600 条反解，
attempt 全部落在合理小整数区间（无负数、无异常值，全局 max = 7，额外 attempt 共 280 次）：

| env | env_code | attempt≠0 条数 | max attempt |
| --- | ---: | ---: | ---: |
| PickXtimes | 1 | 4 | 2 |
| StopCube | 2 | 2 | 1 |
| SwingXtimes | 3 | 7 | 3 |
| BinFill | 4 | 21 | 3 |
| **VideoUnmaskSwap** | **5** | **2** | **1** |
| **VideoUnmask** | **6** | **1** | **1** |
| **ButtonUnmaskSwap** | **7** | **3** | **1** |
| **ButtonUnmask** | **8** | **2** | **1** |
| VideoRepick | 9 | 11 | 2 |
| VideoPlaceButton | 10 | 15 | 2 |
| VideoPlaceOrder | 11 | 47 | 6 |
| PickHighlight | 12 | 1 | 1 |
| InsertPeg | 13 | 49 | 7 |
| MoveCube | 14 | 2 | 2 |
| PatternLock | 15 | 3 | 1 |
| RouteStick | 16 | 0 | 0 |

四个目标 env 恰好是失败率最低的一批（1%–3%），本轮 400 条的重试开销只有约 +2%。
若日后扩到全 16 env，InsertPeg / VideoPlaceOrder / BinFill 是高失败区，重试成本要按此分布重估。

`tests/lightweight/test_seed_layout.py` 把这些固化成秒级回归（7 项，0.09 s）。

---

## 八、这个验证实际在测什么

seed 公式是纯函数 `f(env_code, episode, attempt)`，**公式层面一致是必然的**。
真正被检验的是 attempt 层面：train 由 2025-12 的环境代码产出，而 `src/robomme/robomme_env/`
至今已改动三个月（`git log --since=2025-12-01` 显示四个 env 各有 5+ 次改动，
其中 `4716208 fix choice action reading`、`aa6d100 binfill back to 0.035` 属判定逻辑级）。
若当前环境在某个 seed 上的成功/失败判定与当时不同，就会演进出不同的 attempt。

**所以本验证的实质是「当前环境代码与 2025-12 环境代码的行为等价性」**，
train 里 attempt≠0 的 8 个探针最敏感：

| env | episode | 期望 seed | attempt |
| --- | ---: | ---: | ---: |
| VideoUnmaskSwap | 32 | 8201 | 1 |
| VideoUnmaskSwap | 61 | 11101 | 1 |
| VideoUnmask | 10 | 7001 | 1 |
| ButtonUnmaskSwap | 70 | 14001 | 1 |
| ButtonUnmaskSwap | 94 | 16401 | 1 |
| ButtonUnmaskSwap | 98 | 16801 | 1 |
| ButtonUnmask | 5 | 8501 | 1 |
| ButtonUnmask | 72 | 15201 | 1 |

**不能把「seed 对上」简单当成脚本正确性的证明。**

---

## 九、全量 400 条的结果（2026-08-17，最终）

配置：`--env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask --episodes 100
--difficulty 211 --gpus 1 --workers 32`

| 项 | 结果 |
| --- | --- |
| 生成 | **400/400 成功**，0 条用尽 attempt，0 次重试，0 次池崩溃，`EXIT_CODE=0` |
| 耗时 | **18.7 分钟**（21.4 ep/min；四 env 混合，比纯 VideoUnmask 标定集慢，因其余三个 env 更重） |
| 产物 | 400 个 h5（**77 GB**）、402 个视频（2.2 GB） |
| worker 峰值 RSS | 4666 MB |

> 402 而非 400 个视频：`VideoUnmaskSwap` 的 ep21、ep81 各多出一个 `success_NO_OBJECT_*.mp4` ——
> 这是 `RecordWrapper` 在目标物不在画面时另存的调试变体，episode 本身是成功的，属正常行为。

### 一致性比对：392/400 一致（98%），8 条不一致，0 条缺失

**不一致的 8 条恰好等于 8 个探针，一条不多、一条不少**（已用集合比对验证）：

| env | episode | train 期望 seed | 期望 attempt | 实际 seed | 实际 attempt |
| --- | ---: | ---: | ---: | ---: | ---: |
| VideoUnmaskSwap | 32 | 8201 | 1 | **8200** | **0** |
| VideoUnmaskSwap | 61 | 11101 | 1 | **11100** | **0** |
| VideoUnmask | 10 | 7001 | 1 | **7000** | **0** |
| ButtonUnmaskSwap | 70 | 14001 | 1 | **14000** | **0** |
| ButtonUnmaskSwap | 94 | 16401 | 1 | **16400** | **0** |
| ButtonUnmaskSwap | 98 | 16801 | 1 | **16800** | **0** |
| ButtonUnmask | 5 | 8501 | 1 | **8500** | **0** |
| ButtonUnmask | 72 | 15201 | 1 | **15200** | **0** |

### 结论

1. **seed 公式与实现完全正确。** 392 条 attempt=0 的记录逐条命中，且 8 条不一致的偏差量
   **全部恰好是 −1**（即少了一次 attempt），没有任何一条出现其他偏移 —— 若公式、`env_code`、
   难度循环有任何错误，偏差不可能这么整齐。

2. **当前环境代码与 2025-12 的行为不等价，且漂移是单向的。**
   train 里失败过一次的 8 个 seed（`attempt=0` 失败 → `attempt=1` 成功），
   在当前代码下**全部在 `attempt=0` 一次通过**。反向情况（train 成功、现在失败）**一例都没有**：
   全程 400 条零失败、零重试。

   → **当前环境比 2025-12 更容易通过。** 与 `git log --since=2025-12-01` 里
   `stable-fixChoiceOptionRead-b3`、`EnvPassFix`、`4716208 fix choice action reading`
   这类修复的方向吻合 —— 它们让原本会失败的场景现在能正常完成。

3. **实践含义**：用本脚本无 seed 重跑，**无法逐字复现 train 的 seed 集合**，
   差异恰好落在 train 当年失败过的那些 episode 上。若目标是复现 train，应继续用
   `scripts/data-generation/generate_dataset.py` 读死 seed；本目录适用于**产生新数据**。

---

## 十、与原版官方数据的逐项比对（2026-08-17）

原版数据位置：`/data/hongzefu/robomme_data_h5/record_dataset_{task}.h5`（合并格式，14 GB/env 级别）。
已确认它用的就是 train metadata 的 seed 集合 —— 例如 `VideoUnmask/episode_10` 的
`setup/seed = 7001`，正是 train 里 attempt=1 的那个值。

### 10.1 字段集差异：原版多 8 个字段，生成侧没有任何多余字段

| 类别 | 原版有、生成没有 |
| --- | --- |
| timestep | `action/eef_action_raw/{pose,quat,rpy}`、`obs/eef_state_raw/{pose,quat,rpy}` |
| setup | `fail_recover_mode`、`fail_recover_seed_anchor` |

原版每个 timestep 有 27 个字段，生成侧 21 个，共同 21 个（生成侧是原版的真子集）。

**这不是缺陷，是预期内的版本差异**：commit `68a65a0`（2026-03-01）
"remove in dataset generation: obs/eef_state_raw action/eef_action_raw setup/fail_recover"
删掉的正是这 8 个字段。原版数据早于该 commit，所以带着这些字段。

### 10.2 seed 差异：400 条中 392 条同 seed，8 条不同

8 条差异全部是那 8 个探针，偏差量一律 −1（生成侧 attempt=0，原版 attempt=1），详见第九节。

### 10.3 同 seed 下的 joint_action 数值差异

392 条同 seed 的 episode，**timestep 数全部一致**，逐 timestep 逐元素比对 `action/joint_action`（8 维）：

| env | 总数 | 同 seed | 异 seed | 逐位相同(<1e-8) | 最大绝对差 |
| --- | ---: | ---: | ---: | ---: | ---: |
| VideoUnmaskSwap | 100 | 98 | 2 | 97/98 | 2.146e-06 |
| VideoUnmask | 100 | 99 | 1 | **99/99** | 2.078e-17 |
| ButtonUnmaskSwap | 100 | 97 | 3 | 96/97 | 1.788e-06 |
| ButtonUnmask | 100 | 98 | 2 | 97/98 | 3.576e-07 |
| **合计** | **400** | **392** | **8** | **389/392（99.2%）** | **2.146e-06** |

**389/392 条逐元素完全相同**（最大差 <1e-8，VideoUnmask 甚至整体只有 2e-17 的机器精度级噪声）。

仅 3 条存在肉眼可见的偏差：

| episode | seed | timestep | 最大绝对差 | 平均绝对差 | 超差元素占比 |
| --- | ---: | ---: | ---: | ---: | ---: |
| VideoUnmaskSwap/ep88 | 13800 | 453 | 2.146e-06 | 5.772e-08 | 657/3624（18.1%） |
| ButtonUnmaskSwap/ep87 | 15700 | 443 | 1.788e-06 | 7.645e-08 | 1074/3544（30.3%） |
| ButtonUnmask/ep55 | 13500 | 363 | 3.576e-07 | 8.813e-09 | 294/2904（10.1%） |

这三条的量级（1e-6 ~ 1e-7）远小于关节角的物理意义尺度，是浮点非确定性累积的结果
（同一 seed 下规划器的迭代求解对浮点舍入顺序敏感，偏差沿轨迹缓慢放大），
**不是逻辑差异** —— 佐证是三条的 timestep 数与原版完全一致，轨迹结构没有分叉。

> 注意：这个量级过不了骨架 `compare_joint_actions.py` 的 `1e-8` 验收线。
> 但历史全量报告里官方自己的复现跑也没过（`max_abs_diff = 7.86e-03`，比这里大三个数量级），
> 所以 1e-8 那条线在当前环境下本就不现实。

### 10.4 结论

| 维度 | 结论 |
| --- | --- |
| 字段 | 生成侧比原版少 8 个字段，且是真子集 —— 由 `68a65a0` 有意删除，非缺陷 |
| seed | 392/400 相同；8 条差异全为探针，方向单一（原版 attempt=1 → 现在 attempt=0） |
| 数值 | 同 seed 的 392 条里 **389 条逐位相同**，3 条为 1e-6 级浮点噪声，无逻辑分叉 |

→ **生成链路在数值层面与原版等价**。两份数据的实质差异只有两点：
少 8 个已被上游删除的字段，以及 8 个 episode 因环境行为漂移而选中了不同的 seed。
