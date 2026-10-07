# xhard 新档：上次训练的参照与逐任务高层方案

> 本文是 [`1006-xhard12-env-plan.md`](1006-xhard12-env-plan.md) 的续篇。前篇只定了"子类继承 + 独立包 + 生成器一个开关"的接口，本文回答"每个任务到底改哪个键、改成多少、为什么"。全部内容为拟议，不构成开工令；文中新名字、新数值均未实施，长度与窗口数是估算值，实跑后要重算。
>
> 文档分两部分：**第一部分给人看**，只讲结论与取舍；**第二部分给 agent 看**，把调查到的细节、公式、数字出处和未核实项全部留档，后续实施直接取用。
>
> 调查日期 2026-10-06，分支 `newtask-v3-MotionJepa1006`，调查前 HEAD `d05c6ab7`。四路只读调查分别覆盖：origin/newtask-v2 的窗口口径与交付集、本分支 16 个任务源码、官方参考数据 hard 档统计、MotionJEPA 与 policy 仓库的训练/评估口径。仓库源码零改动。

---

# 第一部分：给人看的高层结论

## 一、先纠正三个前提

1. **上次训练的四任务不是 PatternLock、RouteStick、BinFill、PickXtimes。** MotionJEPA 最近一次正式训练（run `wan-full1600-filter2-b176x4-72ep-a`，2026-09-14，72 epoch 跑完）用的是 newtask-v2 交付集 `HongzeFu/robomme-4task-h5-20260912-v2`，四任务是 **BinFill、RouteStick、VideoUnmaskSwap、VideoRepick**，各 400 条。你给的 artifact《采样窗口与 eval 成功率》画的 PatternLock/RouteStick/BinFill/PickXtimes 是 policy eval 侧对官方 16 任务 test+val 的分析，不是训练集。
2. **newtask-v2 已经有一档 xhard。** RouteStick length 8–10（T 800–1000）、VideoUnmaskSwap swap 4–5（T 中位 558）、VideoRepick swap 4–5（T 中位 863）。BinFill 没有 xhard。本轮"长度对齐 NWTaskV2"按你的选择就是对齐这一档。
3. **"token"有两套口径，差 10 倍。** MotionJEPA 预训练自己切 33 帧、stride 1 的 chunk，上次过滤后 796,001 个；policy 侧 motion 记忆表切 33 帧、stride 16，全集约 69,716 窗。artifact 画的是后者。你最终选的落实方式是：**每条 episode 的 stride-16 窗口数对齐 newtask-v2 xhard，约 50–60 窗，即 T 约 900 帧**。

## 二、上次训练与评估的口径（够用版）

- **MotionJEPA 训练**：每个样本是 33 个原始帧 `[t, t+32]`，逐帧滑动（stride 1），一个 chunk 出 1 个 768 维 motion token；窗口不跨 demo/exec 段，demo 与 exec 是两个独立变体；BinFill 只保留 exec。每个变体 chunk 数 = 帧数 − 32。运动过滤丢掉约 2%。
- **policy 侧 motion 记忆表**：stride 16，demo 段从 0 起铺，exec 段从 exec 起点起铺，每段窗口数 `len(range(0, max(0, L-32), 16))`；`budget` 160 窗是上限，没有任何一档能填满它，它只是按最长那条留的余量。
- **eval 取帧**：`linspace(0, step, N)` 跨 demo 与 exec 整条等距取 N 帧；N=32 来自 `512 // 16`，N=8 来自 `512 // 64`（每帧 8×8 token），**不是**切分步长。
- **BinFill 带 video 是怎么来的**：不是环境里跑 demo，而是生成入口把成品"同一条重复两遍"，前半段标 `is_video_demo=True`，视频加红框。开关是生成器的 `--binfill-demo`，`src/robomme` 没动。MotionJEPA 侧又把这段假 demo 丢掉了。**本轮不传这个开关、不复用其统计模拟分支即可避开。**

## 三、本轮 xhard 的目标与判据（已和你确认）

1. 每条 episode 长度对齐 newtask-v2 xhard，目标 T 约 900，stride-16 窗口约 50–60。
2. **硬性**：8 帧帧路（Δ8 = (T−1)/7）必须有 subgoal 级遗漏，即 Δ8 大于该任务执行段里最短一类子任务的平均段长。32 帧"尽量"，不为它单独拉长（原 hard 下 32 帧在 16 个任务上一段都不漏，要漏得 T 超 1500）。
3. 每个任务只改一两个参数，优先改 `configs["hard"]` 里的键；次数写死在方法里的，子类重写那一个方法。
4. seed 沿用 train metadata 里 hard 记录的原 seed，失败不换 seed。
5. 不做 BinFill 假 demo。
6. 本轮接受总量缺口：只用现有 hard seed，11 个任务共 425 条，估算约 33 万帧，stride-1 chunk 约 31 万，是上次 80 万的四成；补齐要到每任务约 100 条，即 9 个任务各加约 75 条新 seed，留到下一轮。

## 四、任务范围

**纳入 11 个**：PickHighlight、PickXtimes、SwingXtimes、PatternLock、RouteStick、BinFill、ButtonUnmaskSwap、VideoUnmaskSwap（这 8 个换字典或小改方法）；StopCube、VideoRepick、VideoPlaceOrder（这 3 个必须在子类里重写一个方法）。

**不纳入 5 个**：ButtonUnmask、VideoUnmask（`pick` 只是一个 `>1` 的开关，hard 已到顶）；VideoPlaceButton（只有 before/after 二选一，没有数值型次数）；InsertPeg、MoveCube（源码完全不读 difficulty，hard 只是一组 seed）。给它们加难度要新增逻辑，不再是"少改参数"。

## 五、逐任务高层方案

下表每行一个任务：改什么、从多少改到多少、预计长度与窗口数、8 帧是否必漏、母布局是否逐项不变、改法类型。T 与窗口数按官方 hard 中位加每个子任务的平均段长线性外推，实跑后要重算。

| 任务 | 改的键 | hard → xhard | 预计 T（中位） | 预计窗口 | Δ8 对最短执行段 | 母布局 | 改法 |
|---|---|---|---|---|---|---|---|
| BinFill | `put_in_numbers` | [3,5] → [5,6] | 868 → 约 1140 | 53 → 约 69 | 162 > 71（投箱），必漏 | 变（共用 generator） | 换字典 |
| PickXtimes | `number_min/max` | 4/5 → 6/7 | 812 → 约 1120 | 49 → 约 68 | 160 > 70（放到 target），必漏 | 不变 | 换字典 |
| SwingXtimes | `number_min/max` | 3/3 → 7/8 | 488 → 约 840 | 29 → 约 50 | 120 > 40（摆到一侧），必漏 | 不变 | 换字典 |
| PickHighlight | `pickup` | 3 → 5 | 539 → 约 850 | 32 → 约 51 | 121 > 55（放回桌面），必漏 | 不变（目标是原排列前缀） | 换字典 |
| PatternLock | `length` | [4,8] → [10,14] | 324 → 约 810（666–960） | 18 → 约 49 | 116 > 25–40（每步 move），必漏 | 网格不变，路径变 | 换字典；接受率待验 |
| RouteStick | `length` | [4,7] → [8,10] | 500 → 800–1000 | 28 → 46–60 | 114–143 > 50（每步），必漏 | 障碍不变，路线前缀保留，方向变 | 换字典；与 newtask-v2 xhard 相同 |
| VideoUnmaskSwap | `swap_min/max` | [2,3] → [4,5] | 457 → 约 560 | 26 → 约 31 | 80 > 49（放下）、> 50（每次 swap），漏 | 不变 | 换字典 **并** 重写 `_refresh_swap_schedule`（原码只写到 3 次） |
| ButtonUnmaskSwap | `swap_min/max` | [2,3] → [4,5] | 461 → 约 520（待验） | 27 → 约 31 | 74 > 46（放下），漏 | 不变 | 同上；swap 结束是否晚于按钮完成待验 |
| StopCube | `stop_time`、`move_interval` | [2,5] → [8,10]；间隔随机 {60,80,120} → 钉 120 | 309 → 900–1140 | 18 → 54–69 | 128–163 > 100（remain static），必漏 | 不变（随机消耗量不变） | 重写 `_initialize_episode` 与 `step()`（原码写死 5 趟） |
| VideoRepick | `num_repeats` | [1,3] → [4,5] | 543 → 约 935 | 31 → 约 56 | 134 > 58（放下），必漏 | 不变 | 重写 `__init__` 中那一次 `randint` |
| VideoPlaceOrder | 放置数 P | [2,4] → 固定 4 | 1115 → 约 1300 | 67 → 约 78 | 185 > 全部，必漏 | 目标子集不变，正确序号与按钮插入位变 | 重写 `_load_scene` 中那一次 `randint`；**改动弱，可剔除** |

几点说明：

- **BinFill 与 PickXtimes 本来就在 900 附近**，再加次数会到 1100 以上、70 窗左右，超出 50–60 的目标。这是"必须比 hard 更难"和"长度对齐 900"之间的取舍，我选了前者，且区间下沿取 hard 上沿，和 newtask-v2 的分档习惯一致（hard 4–7 → xhard 8–10）。要压回 900 只能让区间和 hard 重叠（如 BinFill [4,5]），那就不像新档了。
- **两个 Swap 任务天生短**，加到 5 次 swap 也只有 560 帧、31 窗，和 newtask-v2 的 VideoUnmaskSwap xhard 一样短。这两个任务各有 100 条 hard seed，是总量的主力，长度上不去是结构问题，不是参数问题。
- **StopCube 改了两个量**。只改 `stop_time` 时，`move_interval` 抽到 60 的那三分之一 episode 只有 450–570 帧，Δ8 小于 100 帧的 static 段，8 帧漏不掉；钉住 120 才能保证硬性判据。两处都在重写的同一个方法里。
- **VideoPlaceOrder 的改动很弱**（P=4 本来就在 hard 区间里），它的上限被目标点数 4 卡死。列出来是因为它在你选的范围里，实施时可剔除。
- **母布局会变的只有 BinFill**（共用 generator，分配循环次数随目标数变）和 PatternLock/RouteStick 的路径部分。其余任务改键后场景逐项不变，新档是严格的"同一场景、更多次数"。
- **预计成功率会低于 hard**：原 hard seed 里 BinFill 11 条、VideoPlaceOrder 12 条、SwingXtimes 5 条、VideoRepick 6 条是重试后才成功的，xhard 不换 seed，这些任务更容易失败。

## 六、总量预估

| 任务 | 条数 | 预计 T | 预计帧数 | 预计 stride-16 窗 |
|---|---:|---:|---:|---:|
| BinFill | 25 | 1140 | 28,500 | 1,725 |
| PickXtimes | 25 | 1120 | 28,000 | 1,700 |
| SwingXtimes | 25 | 840 | 21,000 | 1,250 |
| PickHighlight | 25 | 850 | 21,250 | 1,275 |
| PatternLock | 25 | 810 | 20,250 | 1,225 |
| RouteStick | 25 | 900 | 22,500 | 1,350 |
| VideoUnmaskSwap | 100 | 560 | 56,000 | 3,100 |
| ButtonUnmaskSwap | 100 | 520 | 52,000 | 3,100 |
| StopCube | 25 | 1020 | 25,500 | 1,500 |
| VideoRepick | 25 | 935 | 23,375 | 1,400 |
| VideoPlaceOrder | 25 | 1300 | 32,500 | 1,950 |
| **合计** | **425** | | **约 33.1 万** | **约 19,600** |

对照上次：stride-1 chunk 约 31 万（上次 796,001）；stride-16 窗约 1.96 万（上次 69,716）。缺口已按你的决定接受，补齐路径是每任务凑到约 100 条。

## 七、实施前必须先验的五件事

1. `XHardMixin` 的 `spec` property 拦截是否生效（前篇已列为第一步）。
2. PatternLock `length` [10,14] 在 5×5 网格上的拒绝采样接受率；1000 次不中会退回最后一条路径，长度可能不在区间内。
3. ButtonUnmaskSwap swap 到 5 次时，交换动画结束（第 314 步）晚于两次按按钮完成（约 221 步），抓容器时交换可能还没结束；需要确认是否要加 hold。
4. BinFill 目标 6 个时，固定生成区域里方块生成失败会被静默吞掉，可能导致 IndexError 或目标数悄悄变少。
5. 每任务先用 3 个 hard seed 做 smoke，统计实际 T、窗口数、Δ8 与最短段，和本文估算对账后再放大。

## 八、建议的留档方式

实施后用本分支 `scripts/patternlock-routestick-params/plot_sampling_windows.py` 同一套口径（或 origin/newtask-v2 的 `scripts/injection-before-2d/window_timeline.py`）给 xhard 重出一张"采样窗口数轴"，每任务取最短/中位/最长三条，和原 hard 并排，直接核对 8 帧漏段与窗口数。

---

# 第二部分：给 agent 看的细节与出处

> 本部分的数字分三类：**[实测]** 来自读文件或跑脚本；**[文档]** 来自仓库内文档转引；**[估算]** 由本文公式算出。引用代码只写路径与函数名。

## A. 上次训练的完整口径

### A.1 MotionJEPA 预训练（stride 1）

- run：`wan-full1600-filter2-b176x4-72ep-a`，2026-09-14，72 epoch，退出码 0。出处 [文档]：`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/MotionJEPA/docs/training-doc/README.md` 的 run 一览表。之后的条目全是推理或可视化。本机 `/data/hongzefu/MotionJEPA` 是旧版主线，没有 full1600 的内容。
- 样本：33 帧 `[t, t+32]`、`data.stride: 1`、`data.max_horizon: 8`；Wan VAE 编成 `(9,16,32,32)` latent（1 锚帧 + 8 组×4 帧）；每个 chunk 1 个 token，`motion.num_tokens: 1`、`motion.dim: 768`。出处：`docs/DATASET.md` §2；`configs/default.yaml`；`src/motion_jepa/data/dataset_wan.py::WanChunkLatentDataset.__init__`（断言 stride==1）；冻结配置 `runs/wan-full1600-filter2-b176x4-72ep-a/config.yaml`。
- 分段：demo = `[0, D)`，D 为 `is_video_demo=True` 帧数；exec = `[D, first_completed + 2)`。BinFill 只保留 exec（`scope.json::dup_variants_excluded = 400`，`segment_convention.json` 写明 "binfill: 只保留 exec"）。1600 条 episode、2800 个变体、901,970 帧。出处：`docs/DATASET.md` §1；`docs/dataset-build-doc/local-a100-4task-full1600/reports/scope.json`。
- 数量（出处 `docs/training-doc/wan-full1600-filter2-b176x4-72ep-a/metrics/train.summary.log`）：

| 口径 | 数量 |
|---|---:|
| 未过滤 chunk | 812,370 |
| 运动过滤后保留（阈值 `rgb_mag >= 0.02711051143705845`） | 796,001 |
| 丢弃 | 16,369（2.015%） |
| 训练集（2,675 变体） | 763,499 |
| 验证集（125 变体 = 70 条 holdout，每任务×难度 5 条） | 32,502 |

- 按任务（未过滤 / 过滤后）：BinFill 229,540 / 223,327；RouteStick 187,300 / 187,300；VideoRepick 264,151 / 260,108；VideoUnmaskSwap 131,379 / 125,266。
- 按难度与段（未过滤，demo / exec）：BinFill 只有 exec，easy 53,539、medium 76,251、hard 99,750；RouteStick easy 9,300/8,800、medium 19,300/18,800、hard 24,300/23,800、xhard 41,750/41,250；VideoRepick easy 35,307/43,328、medium 41,837/43,958、xhard 56,484/43,237；VideoUnmaskSwap easy 10,900/14,759、medium 10,900/7,248、hard 16,000/22,456、xhard 25,900/23,216。
- 训练节奏：每卡 batch 176、4 卡、梯度累积 2、有效 batch 1,408；每 epoch 542 步（1,084 micro-batch，drop_last），72 epoch 共 39,024 步，lr 6e-4。出处同上日志与 `scripts/train-script-hongzefu/full1600_wan_local4gpu.sh`。
- 未取得：过滤后按任务×难度的拆分（需要 AWS 机器上的 `chunk_motion.npz`）。

### A.2 policy 侧 motion 记忆表（stride 16）

- 配置：`/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_policy_learning_MotionJEPA/src/mme_vla_suite/models/config/robomme/perceptual-framesamp-modul-8frame-8x8-motion.yaml`：`motion.stride: 16`、`window_frames: 33`、`window_direction: forward`、`grid_origin: segment_start`、`budget: 160`、`demo_min_real_frames: 17`、`demo_tail_pad: repeat_last`；编码器 `source_run: wan-full1600-filter2-b176x4-72ep-a/checkpoint_epoch_72.pt#encoder`。
- 公式（`motion_store.py::segment_grid_starts`，转引自 MotionJEPA `docs/archive/evaluteVLAencode0914-plan-v1.md` 第九节）：demo=(0, exec_start)，exec=(exec_start, T)，`starts = range(0, max(0, L-32), 16)`；不跨段、不 padding、不强补末窗、不过滤。demo 不足 33 帧时按 `demo_min_real_frames=17` 重复末帧补齐。
- 表规模 [文档]：71,316 行（demo 35,913 + exec 35,403，含 1,600 个补帧窗）。出处 `docs/dataset-build-doc/4task-v2-1600ep-motion-demopad17/launch.md`。
- 全集 stride-16 窗 [估算，subagent 按 scope.json 的 D/T 复算，holdout 70 条逐格复现 2,779]：BinFill 30,908（含假 demo）、RouteStick 12,226、VideoUnmaskSwap 8,777、VideoRepick 17,805，合计 69,716；按 MotionJEPA 截断口径再数是 52,148。
- 每条窗口数（最少/中位/最多）：BinFill hard 70/98/140（含假 demo，纯 exec 约一半）；RouteStick xhard 46/54/60；VideoUnmaskSwap xhard 28/31.5/79；VideoRepick xhard 39/51/67。
- 评估时取窗（`policies/framesamp_memory.py::visible_motion_frames`、`_prepare_motion`）：demo 段 s=0 起每 16 帧一个，条件 `s+16 ≤ es−1`；exec 段起点 `es+u`，条件 `u+32 ≤ step−es`；超 budget 默认报错，`MMEVLA_MOTION_OVERFLOW=resample` 时 demo 全留、exec 等距降采样。
- 注意：MotionJEPA 文档记录"当前新 1600 库没有 motion 缓存，policy 训练档案 `motion_enabled=false`"，policy 侧实际是否消费了这张表没有留档。

### A.3 eval 取帧

- `src/mme_vla_suite/shared/sampling.py::even_sampling_indices(step_idx, N)`：`step_idx < N` 时取全部；否则 `np.linspace(0, step_idx, N, dtype=int32)`，含首帧与当前帧，跨 demo/exec 整条。训练与在线推理共用。
- N = `budget // (token_per_image × num_views)`：`perceptual-framesamp-modul.yaml` / `-context.yaml` 为 512 // 16 = 32；`*-8frame-8x8*.yaml` 为 512 // 64 = 8。训练侧只允许 (512,16,1) 与 (512,64,1)。`128 // 16 = 8` 只出现在假设性分析文档 `docs/dataset-build-doc/16task-h5-scan/result.md`。
- 本分支与 newtask-v2 的帧路取整差异：newtask-v2 `window_timeline.py::frame_path` 用 `floor(x+0.5)` 对齐 JS `Math.round`；本分支 `plot_sampling_windows.py::frame_indices` 用 Python `round`（银行家舍入），恰逢 .5 时可能差 1 帧。

### A.4 newtask-v2 交付集

- 出处：origin/newtask-v2 的 `artifacts/injection/20260912-contract-v3-10/hf_release/{README.md, MANIFEST.json}`、`docs/validation/newtask-v2/20260912-contract-v3-10/README.md`、`scripts/README.md` §1.1、`scripts/NEW_VALUE_CONTRACT_CHANGELOG.md` 第四节、`XHARD_DIFFICULTY_PLAN.md`。
- 每任务 400 条 primary，共 1,600；另 spare 196、smoke 1；每个 h5 只含一条 `episode_0`。没有 train/test/val 字段，1,600 条全属 train；另有 700 条只做 env-check 不出 h5 的候选被定义为 test；没有 val。MotionJEPA holdout 70 条（每格 5 条）。seed = `env_code*1000 + ep*100 + attempt`，env_code BinFill=4、VideoUnmaskSwap=5、VideoRepick=9、RouteStick=16，难度不进 seed。
- 分档参数与长度（T 最短/中位/最长/均值；D 为 demo 长度）：

| 任务/难度 | n | 参数 | T | D |
|---|---:|---|---|---|
| BinFill/easy | 134 | 1 色；生成 4–6；投入 1–3 | 528/927/1530/935.6 | 264/463.5/765（假 demo = 原 T） |
| BinFill/medium | 133 | 2 色；生成 6–8（v2 改）；投入 2–4 | 790/1282/1762/1284.1 | 395/641/881 |
| BinFill/hard | 133 | 3 色；生成 8–10（v2 改）；投入 3–5 | 1156/1630/2304/1636.8 | 578/815/1152 |
| RouteStick/easy | 100 | length 2–3，不可折返 | 200/250/300 | T/2 |
| RouteStick/medium | 100 | length 4–5，不可折返 | 400/450/500 | T/2 |
| RouteStick/hard | 100 | length 4–7，可折返 | 400/550/700 | T/2 |
| RouteStick/xhard | 100 | length 8–10，可折返 | 800/900/1000 | T/2 |
| VideoUnmaskSwap/easy | 100 | 3 容器；swap 1–2；pick 1–2 | 214/342/517 | 114/141/168 |
| VideoUnmaskSwap/medium | 100 | 4 容器；swap 1–2；pick 1 | 211/266/365 | 114/141/168 |
| VideoUnmaskSwap/hard | 100 | 4 容器；swap 2–3；pick 2 | 406/452/552 | 168/192/216 |
| VideoUnmaskSwap/xhard | 100 | 4 容器；swap 4–5；pick 2 | 501/558/1312 | 264/291/318 |
| VideoRepick/easy | 134 | 3 块；swap 1–2 | 504/694/922 | 252/296/355 |
| VideoRepick/medium | 133 | 3 块；swap 2–3 | 559/755/968 | 306/343/398 |
| VideoRepick/xhard | 133 | 3 块；swap 4–5 | 674/863/1130 | 414/468/508 |

- 规律：RouteStick T = 100·L，每段固定 50 帧；VideoUnmaskSwap demo = `6·ceil((64+50n)/6)`，n=1–5 为 114/168/216/264/318。VideoUnmaskSwap/xhard 的 T=1312 是一条慢条（ep5、seed 5500，"抓红容"段 828 帧），仍在交付集里。
- 交付里没有 BinFill/xhard 与 VideoRepick/hard（后者被契约 `excluded_groups` 排除）。newtask-v2 的 VideoRepick xhard 是在 3 块 cube 的 easy/medium 分支上加 swap，不是本仓库 hard 的 15 块 cluster 分支。

### A.5 BinFill 假 demo 的改动范围（本轮要避开）

- 做法：h5 的 `timestep_0..N-1` 是原轨迹复制，`info/is_video_demo=True`、`info/is_completed=False`；`timestep_N..2N-1` 是原轨迹；视频前一遍加 10 px 红框后 libx264 重编。
- 改动（`src/robomme` 零改动）：提交 `06139614`（10.64）在 `scripts/generate_dataset_newseed.py` 新增 `BinFillDemoError`、`_binfill_duplicate_h5`、`_binfill_duplicate_video`、`_binfill_demo_deliverable`，`EpisodeJob.binfill_demo` 字段，CLI `--binfill-demo`（默认关），`_worker` 在 `record_env.close()` 后调用；`scripts/injection/campaign.py::cmd_run` feasibility 分支显式传 `binfill_demo=True`；`scripts/injection/run.py::invoke_generator` 加参数；测试 `tests/lightweight/test_binfill_demo_duplicate.py`。统计层 `window_timeline.py::simulate_binfill_demo`（10.55）在旧数据上模拟翻倍，10.65 对生成器直出的 demo 做幂等。
- 动机只有用户一句话"binfill任务改为加入模拟的demo 即为把一个任务重复两遍"（2026-09-11，给数轴补 demo 段）；选"生成入口直接出 h5"是因为 BinFill 的 task_list 全是 `demonstration=False`，且真跑两遍会撞录像器 `fail_safe_limit = 2000`。训练层面动机无记录。
- 副作用：run 10 有 3 条 `BinFillDemoError`（ffmpeg Broken pipe）；mp4 不能逐位对拍；MotionJEPA 丢弃该 demo 而 policy 侧 stride-16 把它算进去，两侧不一致。
- 本分支的 `scripts/data-generation-newSeed/generate_dataset_newseed.py` 以 `3a5951a8` 为起点，是否已含上述 `--binfill-demo` 代码，实施时先 grep 确认；含则不传，不含则不移植。

### A.6 "8 帧/32 帧遗漏 subgoal"的来龙去脉

- 所有分支与 MotionJEPA 仓库都没有把"让采样遗漏 subgoal"写成目标或判据的文档。相关表述只有：提交 `d83998c8`（2.18）用户原话"delta32 delta8 16窗口是为了对齐 <artifact f512d233>"；提交 `212595b8`（10.84）把单条图从 N=32 改成 N=8 以说明"帧预算不是切分步长"。
- subagent 用 newtask-v2 `windows_timeline.json`（07 实跑，每组 ep0–29）补算的漏段占比（分母含收尾段）：N=8 时 BinFill e/m/h 38%/51%/59%，RouteStick e/m/h/xh 0/20%/34%/58%，VideoUnmaskSwap 1%/0/0/13%，VideoRepick e/m/xh 32%/38%/42%；N=32 几乎全 0（BinFill hard 1%）。
- 本文采用的判据（第一部分第三节第 2 条）是本轮新定的：Δ8 > 执行段最短一类子任务的平均段长。

## B. 官方参考数据 hard 档统计

### B.1 数据位置与口径

- AGENTS.md 规定的 `data/robomme_data_h5/` 在本工作副本不存在；`/data/hongzefu/robomme_benchmark-restore-DataGen/data/robomme_data_h5/` 与 `/data/hongzefu/robomme_data_h5/` 也不存在。实际使用 **`/data/hongzefu/data_0226/`**（16 个 `record_dataset_<Task>.h5` + 16 个 metadata + `videos/`，493 GB，文件日期 2026-02-28 至 03-01）。认定为官方集的依据：12 个任务的 metadata 与仓库 train metadata 逐字节相同，4 个 Unmask 系任务在 ep0–99 内 seed/难度一致；**未用 sha256 与 revision `a5e4e25…` 核对**。
- 4 个 Unmask 系任务的 train metadata 已扩到 ep0–399（hard 100 条，提交 `052841ae`），h5 只有 ep0–99，统计只取 h5 里存在的 25 条 hard；其余 12 个任务 hard 各 25 条。共 400 条，无抽样，全部 `is_completed=True`。
- `info` 键 7 个：`grounded_subgoal`、`grounded_subgoal_online`、`is_completed`、`is_subgoal_boundary`、`is_video_demo`、`simple_subgoal`、`simple_subgoal_online`。timestep 连续，第 0 步必是边界。
- 切段口径与本分支 `scripts/patternlock-routestick-params/extract_move_durations.py::extract_episode` 一致：`is_subgoal_boundary=True` 为段起点，段名取该步 `simple_subgoal`，段长到下一边界，demo 段与尾段 "All tasks completed" 都算段。按文本变化切会把相邻同名段并掉（93 条不同），以边界口径为准。帧路 `round(i*(T-1)/(N-1))`。
- 脚本与产物（scratchpad，会话结束即失，重跑约 17 秒）：`official_hard_stats.py`、`summarize.py`、`official_hard_stats.json`；命令 `uv run python $S/official_hard_stats.py /data/hongzefu/data_0226 src/robomme/env_metadata/train $S/official_hard_stats.json`（退出码 0）。首跑因 Unmask 系 metadata 含 h5 不存在的 ep 报 KeyError，改为只取存在的 episode 后通过。

### B.2 每任务汇总（hard，n=25）

T 最小/中位/均值/最大；demo 长度最小/中位/最大；段数最小/中位/最大；执行段数（去 demo 与尾段）；Δ8、Δ32 取中位；skip8 为 8 帧帧路没有任何采样点落入的段数（执行段口径）均值/最大；skip32 全为 0；窗为 stride-16 窗口数（demo 窗 + exec 窗）最少/中位/最多。

| 任务 | T | demo | 段数 | 执行段 | 最短段 | 中位段长 | Δ8 | Δ32 | skip8 执行段 | 窗 |
|---|---|---|---|---|---|---|---|---|---|---|
| BinFill | 584/868/851.8/1044 | 0 | 8/10/12 | 7/9/11 | 34 | 76.5 | 123.9 | 28.0 | 3.12/4 | 35/53/64 |
| PickXtimes | 686/812/796.2/1025 | 0 | 10/12/12 | 9/11/11 | 35 | 70.5 | 115.9 | 26.2 | 3.52/5 | 41/49/63 |
| SwingXtimes | 449/488/490.2/570 | 0 | 10/10/10 | 9 | 17 | 42 | 69.6 | 15.7 | 3.08/4 | 27/29/34 |
| StopCube | 122/309/286.8/459 | 0 | 4/6/7 | 3/5/6 | 6 | 48 | 44.0 | 9.9 | 0.36/1 | 6/18/27 |
| VideoUnmask | 309/329/331.0/399 | 66/66/66 | 5/5/5 | 3 | 7 | 66 | 46.9 | 10.6 | 0/0 | 17/18/22 |
| VideoUnmaskSwap | 407/457/455.8/586 | 168/168/216 | 5/5/5 | 3 | 6 | 96 | 65.1 | 14.7 | 0/0 | 22/26/34 |
| ButtonUnmask | 353/373/378.2/452 | 0 | 5/5/5 | 4 | 6 | 93 | 53.1 | 12.0 | 0.16/1 | 21/22/27 |
| ButtonUnmaskSwap | 443/461/465.7/555 | 0 | 6/6/6 | 5 | 6 | 93.5 | 65.7 | 14.8 | 0.12/1 | 26/27/33 |
| PickHighlight | 492/539/540.0/652 | 0 | 7/7/7 | 6 | 12 | 86 | 76.9 | 17.4 | 0.36/2 | 29/32/39 |
| VideoRepick | 405/543/562.8/1027 | 147/162/214 | 6/8/10 | 3/5/7 | 35 | 59.5 | 77.4 | 17.5 | 0.88/2 | 22/31/61 |
| VideoPlaceButton | 900/961/966.2/1041 | 703/757/818 | 12/12/12 | 2 | 12 | 83 | 137.1 | 31.0 | 1.00/1 | 53/57/62 |
| VideoPlaceOrder | 921/1115/1111.8/1408 | 724/917/1135 | 12/14/16 | 2 | 13 | 83.5 | 159.1 | 35.9 | 1.00/1 | 54/67/85 |
| MoveCube | 247/416/370.6/513 | 161/228/280 | 4/6/6 | 1/2/2 | 5 | 80.5 | 59.3 | 13.4 | 0/0 | 13/23/29 |
| InsertPeg | 414/464/470.9/560 | 207/232/280 | 5/5/5 | 2 | 1（尾段） | 110 | 66.1 | 14.9 | 0/0 | 22/26/32 |
| PatternLock | 186/324/350.0/568 | 93/162/284 | 7/11/15 | 3/5/7 | 6 | 31 | 46.1 | 10.4 | 2.08/4 | 8/18/32 |
| RouteStick | 400/500/552.0/700 | 200/250/350 | 9/11/15 | 4/5/7 | 7 | 50 | 71.3 | 16.1 | 2.52/4 | 22/28/40 |

### B.3 各类 subgoal 平均段长（timestep；demo| 为演示段）

- BinFill：拿起 cube 108.5，放进 bin 70.6，按按钮 61.6，尾段 38.0。
- PickXtimes：拿起 84.2，放到 target 69.6，按按钮 63.0，尾段 38.2。
- SwingXtimes：到右侧 target 37.5，到左侧 40.6，拿起 118.6，放回桌面 36.5，按按钮 62.1，尾段 38.5。
- StopCube：remain static 63.7（最短 6），到按钮上方 56.0，按按钮 28.3，尾段 36.8。
- VideoUnmask / VideoUnmaskSwap：demo static 66 / 191，拿起容器约 103，放下约 49，尾段约 9。
- ButtonUnmask / ButtonUnmaskSwap：按按钮 117 / 104，拿起容器约 102–104，放下约 45–47，尾段约 8。
- PickHighlight：拿起高亮 cube 98.7，放回桌面 55.4，按按钮 117.6，尾段 15.7。
- VideoRepick：demo 拿起 112.6、放下 54.2；执行拿起 98.7、放下 58.3；按按钮 62.5；尾段 38.3。
- VideoPlaceButton / VideoPlaceOrder：demo 拿起约 88–95、放到 target 约 90–92、static 约 58；执行拿起约 118、放到正确 target 约 71–72；尾段约 16。
- MoveCube：demo static 50.4；推 cube 约 98–105，拿起 peg 约 120，用 peg 勾 cube 约 100–106，pick-place 约 65–110；尾段 6.9。
- InsertPeg：拿起 peg 117–122，插入 103–119，尾段 11.8。
- PatternLock：左右移动 24–27；前后与斜向 33–40；尾段 9.1。
- RouteStick：demo 每段固定 50；执行段 48.2–49.3（最短 43）；尾段固定 7。

### B.4 本分支 artifact 四任务（官方 test+val 各 100 条，easy 52 / medium 24 / hard 24）

- PatternLock hard：T 184/353/516/351.9，窗 8/19/30；RouteStick hard：400/500/700/554.2，窗 22/28/40；BinFill hard（无 demo）：608/920/1097/870.0，窗 36/56/67；PickXtimes hard：677/794/1006/791.1，窗 41/48/61。出处 `scripts/patternlock-routestick-params/outputs/durations_{val,test}.json`、`counting_params_{val,test}.json`。
- 这四个任务的难度参数：PatternLock 路径长度 [2,4]/[3,5]/[4,8]；RouteStick steps [2,3]/[4,5]/[4,7]；BinFill 投入 [1,3]/[2,4]/[3,5]；PickXtimes 次数 [1,3]/[1,3]/[4,5]。

## C. 16 个任务的 hard 配置与约束（源码核查）

### C.0 共用结论

- 序数词：`utils/subgoal_language.py::get_subgoal_with_index` 只认 idx 0–9，≥10 抛 ValueError；用到它的是 BinFill（每色各自从 0 编号）、PickHighlight（目标数>1 时）、PickXtimes。SwingXtimes 与 VideoRepick 自带 10 个词的序数表，超出退回 `f"{i+1}th"`。
- `utils/task_goal.py::num2words`、`num2words_2` 覆盖 1–20，`.get(n, str(n))` 查不到退回数字。`utils/vqa_options.py` 各任务选项只是动作种类，与次数无关。
- 随机数消耗 [实测，torch 2.9.1 CPU Generator，2000 个 seed]：`torch.randint(lo, hi)` 不论区间多大只消耗固定一份随机量，之后的随机数完全一致；同宽区间整体平移结果严格平移（(4,6)→(6,8) 恒 +2）；拓宽区间时新值只会是原值或原值+偏移；`randperm(n)[:k]` 改 k 不影响随机流，改 n 影响。
- 固定帧数：ManiSkill `follow_path` 每个 position 1 步；`open_gripper`/`close_gripper` 默认各 6 步；`solve_hold_obj(static_steps=N)` 按 6 向上取整；`solve_strong_reset` 默认 30 步。
- seed 规律：`env_code*1000 + ep*100 + attempt`；hard 记录全部 `ep ≡ 3 (mod 4)`；4 个 Unmask 系任务各 100 条 hard（ep 3,7,…,399），其余 12 个各 25 条（ep 3,7,…,99）。
- 前篇"13 个有 configs、3 个没有"数量准确，但细节有误：VideoRepick hard 的 swap 为 0 且 hard 分支不支持交换，次数 `num_repeats` 写死在 `__init__`；VideoPlaceOrder 不读 `pick`，P 写死在 `_load_scene`；VideoUnmask/ButtonUnmask 的 `pick` 只是 `>1` 开关；VideoPlaceButton 没有数值型次数键；两个 Swap 任务 swap 写死最多 3 次、bin 只能 3 或 4、pick 只有 `==2` 分支；PatternLock `length` 是拒绝采样过滤条件；StopCube `step()` 写死 5 趟；StopCube/InsertPeg/MoveCube 完全不读 difficulty；前篇示例文件名 `PickHighlight_ep3_seed620301.h5` 与 metadata 不符，实际 ep3 seed 12300。

### C.1 逐任务（env_code、configs 原文、键语义与条数公式、时长结构、随机流、语言上限、metadata）

**BinFill（4）**
- configs：easy `{'color':1,'spawn_cubes':[4,6],'put_in_color':[1,1],'put_in_numbers':[1,3]}`；medium `{'color':2,'spawn_cubes':[8,10],'put_in_color':[1,2],'put_in_numbers':[2,4]}`；hard `{'color':3,'spawn_cubes':[10,12],'put_in_color':[2,3],'put_in_numbers':[3,5]}`。
- `_load_scene` 读取：`color` 颜色数（`randperm(3)[:color]`）；`put_in_color` 有目标的颜色数（截到 ≤ color）；`put_in_numbers` 总目标数 T（多色时抽 T 后循环 T 次逐个分配）；`spawn_cubes` 总生成数（每色至少 max(目标,1)，剩余逐个分配）。`_initialize_episode` 先 `randperm(3)` 打乱颜色顺序，每个有目标的颜色做 [pick up the {第 i 个} {color} cube → put it into the bin] × 目标数，最后 press the button。条数 2T+1，hard 7–11。
- 时长：无 demo；`__init__` 的 `dynamic = randint(0,2)` 一半概率为真，为真时 `step()` 把每色第 k 个方块在 [0, k×100] 步内移走、中点放回。
- 随机流：用 `__init__` 建的 `self.generator`，`_load_scene` 不重设。按钮与 bin 板位置在读 config 之前抽，不变；改 `put_in_numbers` 后分配循环次数变，之后的 total_spawn、剩余分配、生成顺序、方块坐标、颜色顺序全部偏移。母布局不能逐项不变。
- 上限与风险：任一颜色目标 ≥11 触发 ValueError；生成失败只记 debug 日志被吞，某色实际数少于目标数会在 `_initialize_episode` 的 `cube_collection[i]` 抛 IndexError。
- metadata：hard 25 条；attempt>0 共 11 条：ep3=4301、ep7=4701、ep15=5501、ep31=7101、ep35=7501、ep47=8703、ep51=9102、ep71=11102、ep83=12301、ep91=13101、ep99=13902。

**ButtonUnmask（8）**：configs easy `{'bin':3,'pick':1}`、medium `{'bin':5,'pick':1}`、hard `{'bin':15,'pick':2}`；`__init__` 的 `num_repeats = randint(1,6)` 抽了未用；`step()` 只给前 15 个 bin 做抬放动画。`pick` 只用作 `>1` 判断；hard 模板 press → pick bin_0 → put down → pick bin_1，条数 2+2×(pick>1)，已到顶。`_load_scene` 新建 generator：按钮 → 逐个容器 → `randperm(3)` 颜色；改 `bin` 容器坐标前缀一致但颜色可能重排。hard 100 条，seed 基数 8000，全 attempt 0。**不纳入。**

**ButtonUnmaskSwap（7）**
- configs：easy `{"bin":3,"swap_min":1,"swap_max":2,"pick_min":1,"pick_max":2}`；medium `{"bin":4,"swap_min":1,"swap_max":2,"pick_min":1,"pick_max":1}`；hard `{"bin":4,"swap_min":2,"swap_max":3,"pick_min":2,"pick_max":2}`。
- `__init__` 用独立 generator 先抽 `swap_times` 再抽 `pick_times`；`_refresh_swap_schedule` 只写了 swap_times=1/2/3 三个分支，第 k 次交换占第 64+50(k−1) 到 64+50k 步，只有 `swap_pair1..3`；**swap_times ≥4 或 0 时 `swap_schedule` 不被赋值，`step()` 抛 AttributeError**。`pick_times` 只判 `==2`，3 退化成 1。`bin==4` 用 `region4`，否则 `region3`（3 元素），**bin ≥5 抛 IndexError**。hard 模板 press 右键 → press 左键 → pick selected_bins[0] → put down → pick selected_bins[1]，5 条；交换次数不改条数。
- 时长：容器 0–64 步抬放；交换 64 起每次 50 步（S=3 到 214）；方块 64 步到最后一次交换结束都在抬放；与按按钮同时进行。
- 随机流：swap/pick 独立 generator，场景另一 generator；三组交换的第一个容器在场景生成时算好，第二个运行时取最近；改 swap 区间只在末尾追加交换，母布局逐项不变。
- hard 100 条，seed 基数 7000，全 attempt 0。

**InsertPeg（13）**：无 configs，difficulty 未被使用；`random_peg_idx` 抽后写死 0；`obj_flag`、`direction` 各一次 `randint(0,2)`。固定 6 条：演示抓 → 演示插 → strong reset 30（NO RECORD）→ 静止 100（NO RECORD）→ 执行抓 → 执行插。hard 25 条，seed 基数 13000，attempt>0 共 9 条：ep23=15301、ep27=15704、ep39=16901、ep43=17307、ep63=19301、ep71=20101、ep75=20502、ep79=20902、ep87=21702。**不纳入。**

**MoveCube（14）**：无 configs，difficulty 未用；`_initialize_episode` 用 `randint(3)` 选 peg_push / gripper_push / grasp_putdown；task_list 在 `evaluate()` 构建，6/4/6 条，含静止 30 或 60、strong reset 30。hard 25 条，seed 基数 14000，全 attempt 0。**不纳入。**

**PatternLock（15）**
- configs：easy `{"grid":3,"length":[2,4]}`、medium `{"grid":4,"length":[3,5]}`、hard `{"grid":5,"length":[4,8]}`。
- `_load_scene`：`grid` 为 grid×grid 目标点网格，间距 0.1，无随机；`length` 是拒绝采样过滤条件：最多 1000 次，每次 `randperm(N)[:2]` 选起终点，`find_path_0_to_8` 做 8 连通随机 DFS（每访问一节点 randperm 一次），节点数 L 落区间即接受，1000 次不中用最后一条。模板：demo 段 swingonto 起点（NO RECORD）→ (L−1) 条 "move {方向}" → strong reset 30（NO RECORD）；执行段 strong reset 回 swing_qpos 30（NO RECORD）→ (L−1) 条 move。条数 2L+1，hard 9–17。
- 时长：每步 `solve_swingonto` 两次 `move_to_pose_with_screw`，步数不固定；按官方 test+val hard 最长 516 帧对 L=8 反推，每个 move 约 37 帧（含开销）。
- 随机流：网格不变；改 `length` 改变拒绝采样循环次数，路径一般会变。
- 语言：8 个方向，无次数上限。hard 25 条，seed 基数 15000，attempt>0 仅 ep91=24101。

**PickHighlight（12）**
- configs：easy `{'spawn':3,'pickup':1}`、medium `{'spawn':4,'pickup':2}`、hard `{'spawn':6,'pickup':3}`。
- `_load_scene` 先重设 generator 种子 → 按钮 → 循环 spawn 次生成方块 → 目标 `randperm(len(all_cubes))[:pickup]`；`step()` 第 10–100 步高亮前 min(pickup, 目标数) 个。模板 press → [pick up the {第 i 个} highlighted cube → place onto the table]，最后一个只抓不放；条数 2k，hard 6。成功条件每个目标被抓起过至少一次，`_execute_tasks` 成功即提前返回。
- 随机流：改 `pickup` 母布局逐项不变，新目标是同一排列前缀；k ≤ 实际生成数（≤6），超出截断；改 `spawn` 目标集合整体改变。语言 pickup ≤ 10。hard 25 条，seed 基数 12000，全 attempt 0。

**PickXtimes（1）**
- configs：easy `{'color':1,'number_min':1,'number_max':3}`、medium `{'color':3,'number_min':1,'number_max':3}`、hard `{'color':3,'number_min':4,'number_max':5}`。
- `__init__` 用独立 generator `randint(min, max+1)` 抽 `num_repeats`；`color` 每色 1 块。模板（`_load_scene` 构建）[pick up the {color} cube for the {第 i} time → place onto the target] × N → press the button to stop；条数 2N+1，hard 9 或 11。无 demo、无固定段。随机流：独立 generator，母布局不变，同宽平移严格 +k。语言 N ≤ 10。hard 25 条，seed 基数 1000，全 attempt 0。

**RouteStick（16）**
- configs：easy `{'length':[2,3],'backtrack':False}`、medium `{'length':[4,5],'backtrack':False}`、hard `{'length':[4,7],'backtrack':True}`。`__init__` 不传 difficulty 时强制 easy，生成器总会传。
- `_load_scene` 抽取顺序：theta → 4 根障碍物颜色（每根 3 个随机数）→ `steps = randint(lmin, lmax+1)` → 在 5 个按钮 [0,2,4,6,8] 上随机游走（起点 1 次 + 每步 1 次）→ S 次方向。模板：demo 段 swingonto 起点（NO RECORD）→ S 条 "move to the nearest {left/right} target by circling around the stick {cw/ccw}" → strong reset 200（NO RECORD）；执行段 strong reset 30（NO RECORD）→ S 条执行。条数 2S+3，hard 11–17。
- 时长：每步 45 个 Bezier 点 + 5 个停留点共 50 个 waypoint，约 50 步；录制长度 T = 100·S（reset 不录）。
- 随机流：theta 与障碍物颜色不变；游走路线前 min(S,S′) 步不变；方向序列整体改变；同宽平移 S 严格 +k。无次数上限。hard 25 条，seed 基数 16000，全 attempt 0。

**StopCube（2）**
- 无 configs，difficulty 未用。`_initialize_episode`（新建 generator）：`interval = randint(27,33)` 抽完覆盖成 30；`move_interval = [60,80,120][randint(0,3)]`；**`stop_time = randint(2,6)` 即 2–5**；再抽 `rotation_angle`；`steps_press = mi·k − mi/2`；停止窗口 (mi(k−1), mi·k]。**`step()` 写死 `for segment in range(5)`，方块只走 5 趟**，k>5 时方块停在终点必失败。`evaluate` 超过 mi·k 步未完成判失败。
- 模板：移到按钮上方 → 若干条 "remain static"（检查点 `range(100, final, 100)` 再补 final，final = steps_press − 30）→ 按按钮。条数 2+C，C = len(range(100, final, 100)) + 1。
- 时长：约 mi(k−0.5) + 按按钮步数。随机流：只改 stop_time 母布局逐项不变（mi 在其前、rotation 在其后，消耗量固定；`_load_scene` 用另一 generator）。语言 `num2words_2` ≤ 20。hard 25 条，seed 基数 2000，全 attempt 0。

**SwingXtimes（3）**
- configs：easy `{'color':1,'number_min':1,'number_max':3}`、medium `{'color':3,'number_min':1,'number_max':2}`、hard `{'color':3,'number_min':3,'number_max':3}`。
- `__init__` 独立 generator 抽 `num_repeats`，hard 固定 3。模板 pick up → [move to the top of the right-side target for the {第 i} time → left-side] × N → put on the table → press；条数 2N+3，hard 9；`max_swings = 2N`。目标高亮 20 步。随机流不变。序数表 10 个超出有回退。hard 25 条，seed 基数 3000，attempt>0 共 5 条：ep3=3301、ep11=4101、ep19=4903、ep31=6101、ep39=6902。

**VideoPlaceButton（10）**：configs easy `{'color':1,'additional_place':False,'swap':False,'targets':3}`、medium `{'color':3,'additional_place':False,'swap':False,'targets':4}`、hard `{'color':3,'additional_place':False,'swap':True,'targets':4}`。目标点循环写死 `range(4)`。hard 12 条（demo 9 条 + 静止 20、60（含 50 步交换）、strong reset 30 + 执行 2 条）；`additional_place=True` 时 pre/post 各 50% 加 2 条，但会在 task_flag 之前多抽 2 个随机数，before/after 重新抽。没有数值型次数键。hard 25 条，seed 基数 10000，attempt>0 共 6 条：ep3=10301、ep7=10701、ep27=12701、ep39=13901、ep75=17501、ep83=18301。**不纳入。**

**VideoPlaceOrder（11）**
- configs：easy `{'color':1,'swap':False,'targets':4}`、medium `{'color':3,'swap':False,'targets':4}`、hard `{'color':3,'swap':True,'targets':4}`；`"place"` 键已注释。
- `_load_scene`（用 `__init__` 的 `self.generator`，不重设）：**`P = randint(2, len(targets)+1)` 即 2–4**；`indices = randperm(4)[:P]`；`which_in_subset = randint(1, P+1)`；`k = randint(0, P)` 按钮插在第 2k+2 位。模板：demo 段 P 组 [pick → 放到目标 j]（按钮插在其中）→ pick → 放到 goal_site → 静止 20 → 静止 60（含 50 步交换）→ strong reset 30；执行段 pick → 放到第 {which_in_subset} 个目标。条数 2P+8，hard 12–16。
- 随机流：改 randint 区间时 `indices` 是同一排列前缀，但 `which_in_subset` 与 k 值变。P ≤ 4。hard 25 条，seed 基数 11000，attempt>0 共 12 条：ep3=11305、ep7=11705、ep15=12501、ep23=13301、ep31=14101、ep39=14903、ep47=15702、ep55=16503、ep75=18501、ep79=18901、ep83=19301、ep99=20903。

**VideoRepick（9）**
- configs：easy `{"cube":3,"swap_min":1,"swap_max":2}`、medium `{"cube":3,"swap_min":2,"swap_max":3}`、hard `{"cluster":True,"swap":None,"swap_min":0,"swap_max":0}`；`cluster`、`swap` 无处读取。
- `__init__`：`num_repeats = randint(1,4)` 即 1–3，之后抽 `swap_times`（hard 为 0），同一 `self.generator` 接着给 `_load_scene` 用。hard 走 `if self.difficulty == "hard"` 分支：5 轮 × 3 色共 15 块，随机抽一个目标；**该分支不设 swap_pair/swap_schedule，hard 的 swap 改成 >0 会在 `step()` 抛 AttributeError**。模板（`_initialize_episode`）demo pick → demo drop → strong reset 30（NO RECORD）→ [pick up the correct cube for the {第 i} time → put it down] × N → press；条数 2N+4，hard 6–10。
- 随机流：randint 消耗固定，改区间或强制赋值不动随机流，15 块与目标逐项不变。语言有回退（"two"→"twice"）。hard 25 条，seed 基数 9000，attempt>0 共 6 条：ep3=9301、ep11=10102、ep19=10902、ep35=12501、ep51=14101、ep75=16501。

**VideoUnmask（6）**：configs 同 ButtonUnmask；模板静止 64（demo，容器 0–64 抬放）→ pick bin_0 → put down → pick bin_1，4 条，pick 已到顶。hard 100 条，seed 基数 6000，全 attempt 0。**不纳入。**

**VideoUnmaskSwap（5）**：configs 三档与 ButtonUnmaskSwap 相同；`region4` 固定坐标无偏移。模板静止演示 64+50S 步（S=2 为 164，S=3 为 214）→ pick → put down → pick，4 条；S 只影响 demo 时长。约束同 ButtonUnmaskSwap（swap ≤3、bin 3 或 4、pick 1 或 2）；改 swap 母布局逐项不变。hard 100 条，seed 基数 5000，全 attempt 0。

## D. 逐任务 xhard 实施细节与估算

估算公式统一为：T_xhard ≈ T_hard 中位 + Δ次数 × 该次数对应的子任务段长之和（B.3 的均值）；窗口 ≈ demo 窗 + exec 窗，各按 `len(range(0, max(0, L-32), 16))`；Δ8 = (T−1)/7。

1. **BinFill**：子类 `configs["hard"] = {**hard, "put_in_numbers": [5, 6]}`。每多 1 个目标约 +179 帧（108.5+70.6）；hard 均值 4 → 5.5，T ≈ 868 + 1.5×179 ≈ 1137；窗 ≈ 69。`spawn_cubes` [10,12] ≥ 6 不必改。`dynamic` 模式的移走窗口随每色方块数变长。需验：目标 6 时生成成功率；每色目标 ≤10 自然满足。母布局会变，记入对拍预期。
2. **PickXtimes**：`{"number_min": 6, "number_max": 7}`。每次 +154 帧（84.2+69.6）；4.5 → 6.5，T ≈ 812 + 2×154 ≈ 1120；窗 ≈ 68。同宽平移，抽到的 N 恒为原值 +2。
3. **SwingXtimes**：`{"number_min": 7, "number_max": 8}`。每次 +78 帧（37.5+40.6）；3 → 7.5，T ≈ 488 + 4.5×78 ≈ 839；窗 ≈ 50。`max_swings` 自动 = 2N。区间从单值变双值会多消耗吗：不会，randint 消耗量固定。
4. **PickHighlight**：`{"pickup": 5}`。每个 +154 帧（98.7+55.4）；T ≈ 539 + 2×154 ≈ 847；窗 ≈ 51。不取 6 是因为 6/6 全高亮会让"记住哪些被高亮"失去意义。
5. **PatternLock**：`{"length": [10, 14]}`。每个 move 约 37 帧 × 2（demo+exec）；T ≈ 74×(L−1)：L=10 → 666，12 → 814，14 → 962；窗 ≈ 37–55。需验接受率；备选 [12,16] 或加 `grid: 6`（后者母布局全变）。
6. **RouteStick**：`{"length": [8, 10]}`，与 newtask-v2 xhard 相同。T = 100·S = 800–1000；窗 = 2×wins(50S) = 46/54/60。
7. **VideoUnmaskSwap / ButtonUnmaskSwap**：`{"swap_min": 4, "swap_max": 5}` 并在子类重写 `_refresh_swap_schedule`（补 4、5 两个分支，第 k 次占 64+50(k−1) 到 64+50k 步，`swap_pair4/5` 按同样规则取最近容器）。VideoUnmaskSwap demo = 6·ceil((64+50S)/6) = 264/318，exec ≈ 263，T ≈ 527–581，窗 ≈ 15–18 + 14 ≈ 31。ButtonUnmaskSwap 交换结束在 264/314 步，两次按钮约 221 步，抓容器时交换可能未完，需验；若失败率高，备选在子类加"等到交换结束"的 hold（但那就不是少改参数）。origin/newtask-v2 已实现过 swap 4–5，可参考其 diff（`git log origin/newtask-v2 -- src/robomme/robomme_env/VideoUnmaskSwap.py`）。
8. **StopCube**：子类重写 `_initialize_episode`：照原顺序抽 interval、move_interval、stop_time、rotation_angle（保持消耗量），然后把 `move_interval` 覆盖为 120、`stop_time` 用 `randint(8, 11)`；重写 `step()` 把 `range(5)` 改为 `range(self.stop_time)`（或 `max(5, stop_time)`）。T ≈ 120×(k−0.5) + 28 ≈ 928/1048/1168；窗 ≈ 56/63/71；static 段 100 帧，Δ8 ≥ 132 必漏。若不钉 mi：mi=60 时 T 450–570，Δ8 64–81 < 100，不满足硬性判据。
9. **VideoRepick**：子类重写 `__init__`：调用父类前无法拦截，可在父类 `__init__` 后把 `self.num_repeats` 改写为按同一 generator 规则映射的值（原值 1–3 映射到 4–5），或完整复制 `__init__` 把 `randint(1,4)` 换成 `randint(4,6)`；两种都不动随机流。每次 +157 帧（98.7+58.3）；2 → 4.5，T ≈ 543 + 2.5×157 ≈ 935；窗 ≈ 9（demo 162）+ 47 ≈ 56。需验 task_list 在 `_initialize_episode` 重建时读的是改写后的值（前篇未核实项 3）。
10. **VideoPlaceOrder**：子类重写 `_load_scene` 把 `randint(2, 5)` 换成 `randint(4, 5)`（固定 P=4）。每组 +181 帧（约 90+91）；3 → 4，T ≈ 1115 + 181 ≈ 1296；窗 ≈ 67 + 11 ≈ 78。改动弱，上限被 `range(4)` 卡死；可剔除。

## E. 未核实与遗留

1. `/data/hongzefu/data_0226/` 是否就是 HF revision `a5e4e25…`，未用 sha256 核对；`plot_persistent_length_dist.py` 默认 `--h5-dir /data/hongzefu/robomme_data_h5` 在本机不存在。
2. 各子任务 `move_to_pose_with_screw` 实际步数未实测；本文所有 T 是按段长均值线性外推。
3. ButtonUnmaskSwap 两次按按钮是否一定晚于交换动画结束，未验证。
4. ManiSkill `BaseEnv.__init__` 期间是否已调用 `_load_scene`/`_initialize_episode`、reset 是否再触发 reconfigure，未逐行确认；影响 BinFill/VideoRepick/VideoPlaceOrder 共用 generator 的随机流状态与 VideoRepick 改写 `num_repeats` 的时机。
5. "randint 消耗量与区间无关"只在本 venv torch 2.9.1 CPU Generator 上实测；`randperm` 消耗随 n 变只是推断。
6. 更多方块/更长路径在固定区域内能否生成成功未验证；BinFill 与 PickHighlight 的生成失败被静默吞掉。
7. policy 仓库源码本机不存在，stride-16 公式与 eval 取帧均为 NFS 原件与 MotionJEPA 文档转引，holdout 2,779 窗由 subagent 数值复现。
8. 过滤后按任务×难度的 chunk 拆分、W&B 在线 summary 未取得。
9. 本分支生成器是否已含 `--binfill-demo` 代码未 grep。
10. subagent 统计脚本与 JSON 在 scratchpad，会话结束即失；需要留档时按 B.1 的命令重跑。
