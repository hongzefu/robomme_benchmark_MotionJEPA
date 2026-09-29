# 0928 方案：test-hard v7 —— 接入 xhard0（原生 hard）+ xhard1～4 改为共用 20 个母布局（只规划不实施）

> **权威性与锚点**：本方案是 v7 的唯一现行计划，取代同日 [`0928-xhard0-native-hard-plan.md`](0928-xhard0-native-hard-plan.md) 里「xhard0 追加在旧四档之后」的编号建议，其余 xhard0 结论（身份来源、原生分支、零差验收）原样沿用、本文只引用不重抄。工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-v5`，代码锚点 `8dfd09cb`（12.222）。官方源码锚点 `1fadc0ec`（`src/robomme/` 逐字节相同），官方编排锚点 `d53f21a7`（`scripts/parity/official/` vendor）。commit 编号沿用 `12.<小版本> 中文描述`。**本轮只写方案，不改代码、不起环境、不提交占位 job；用户已对第二部分 §2 预算全表一次性批准（原话 12），阶段 0～11 按表连续执行，超出预算或判定 FAIL 才停下找用户。**
>
> **用户原话（2026-09-28，按时间顺序逐字保留）**：
> 1. 「给出方案 xhard现在有1-4 再加入xhard0 需要和原本的hard保持完全一致 每个task episode数量和以前一致 根目录写方案」
> 2. 「xhard1234改为同样reset布局 总共20个布局 只有现在的梯度区别不一样」（附四档梯度表，与 `scripts/README.md` 第 3 节逐字相同）
> 3. 「并且告诉我现在的多卡容差范围是多大 为什么」
> 4. 「保证接口和现在一致 /data/hongzefu/robomme_benchmark_MotionJEPANewTask/scripts/README.md」
> 5. 「修改完定为v7的task」
> 6. 「拍链路（parity/）只需要原三档 144 局清单（16 任务 × 3 档 × 3 局）和新的v7 两次生成一致」
> 7. 「需要修改parity机制 我要的是每次都和保存完的o对比 p读取之前的commit 来对比 给这个commit锚定要打上tag 每次都是oph o上传 p回到之前commit 以及h现在 不要以修改前后 每次都锚定固定的commit 以后都这么干」
> 8. 「对于v7 现在这个commit已经做完之前的v6 oph parity 修改后再做一次v6的oph parity 然后存档 之后都只以新的v7 打tag做parity」「验证过的commit就不用再次验证了」「另外这些都是基于a40 的容差标准？」
> 9. 细化方案经用户回复「同意」（2026-09-28）；三个待定项用户未另选，按推荐落定：v6 xhard 165 局纳入 v6 回归、O 以本机 `/data` + 逐局 sha 清单为准（bucket 被 HF 计费拒绝）、tag 名 `parity-anchor-v6`／`parity-anchor-v7`。
> 10. 「生成的job我已经query过了在排队」「也是直接用」（生成阶段直接用用户已提交排队的占位 job，不另提）。
> 11. 「评估的job你自己提交 但是参考framesample 的实测说明了两件事：1 CPU主要让启动阶段变慢。 第一次处理请求，1 CPU约183秒，4 CPU约61秒；等前期编译结束，每次取一组动作都约0.22秒，差别很小。保持模型常驻确实有收益。 两个任务分别启动，合计约6分钟；只启动一次、连续跑两个任务，约3分39秒。这次省了约2分19秒，但还不是完整三轮比较。」「模型常驻先不动 保持一致 cpu改为4个」
> 12. 待决项经 AskUserQuestion 定（2026-09-28）：P3 预算「全表一次批准」；xhard0「12 局」；四档同废「接受，30 个候选」；产物「gen2 比完即删」。
>
> 上一轮（12.222）关于 xhard0 数量的最后决定：「和test的hard数量一致」→ 每任务 12 局。本文对原话 1 里「每个task episode数量和以前一致」的解读：**xhard0 每任务 12 局（沿用 12.222 决定），xhard1～4 每格仍 20 局（与现在一致）**。用户 2026-09-28 已确认 xhard0 取 12 局（原话 12）。

# 第一部分（给人看）

## 1. 定好的决策

1. v7 的 `test-hard` 从 4 档变成 5 档：新增 **xhard0**，放在 xhard1 前面。
2. xhard0 就是原来官方 test 里的 hard，一局不改：16 任务 × 1 档 × 12 局 = 192。
3. xhard1～4 **四档共用同一批 20 个场景布局**。四档之间只有难度梯度不同（次数、数量、序列、演示选择）；梯度数值沿用现在的四档表，一个不改。
4. 局数：13 任务 × 4 档 × 20 局 + 3 任务（StopCube／InsertPeg／MoveCube，只有 xhard4）× 1 档 × 20 局 = 1100，加上 xhard0 的 192，共 1292。
5. 评估接口不变（`scripts/README.md` 第 1 节那 4 处）：只多一个档名 `xhard0`，它的步数上限是 1300。
6. parity 改为**固定 tag 锚点**，以后都这么做（§4）。
7. 容差只在 A40 + 同一驱动上成立；正式生成与对拍一律在 GL 的 A40 上跑（§4.3）。

## 2. xhard0

- **是什么**：官方 test 元数据里每个任务 `difficulty=="hard"` 的那 12 局（原 episode 号 3,7,…,47），seed 逐条照抄元数据。
- **怎么跑**：`difficulty="hard"`，走官方原生 hard 代码，不注入任何规格，所以和原来的 hard 完全一样。
- **为什么不和 xhard1～4 共用布局**：原生 hard 的场景是官方代码在 hard 配置下抽出来的；换成 xhard 的布局，它就不再是「原来的 hard」。

## 3. xhard1～4：改前 vs 改后

### 3.1 总的变化

| | 改前（v6，现在） | 改后（v7） |
|---|---|---|
| 场景布局 | 每档各抽各的，四档 seed 段不同（6e6／8e6／10e6／12e6），同一局号在四档里的场景没有关系 | 每任务先在 xhard4 配置下抽 20 个「母布局」，xhard1～3 直接沿用；四档同一 seed（`14e6 + 任务码×1e5 + 候选×100`） |
| 难度梯度 | 各档按自己的区间抽 | 不变：各档仍按自己的区间在环境里现场抽，数值表一个不改 |
| 低档物体更少 | 各档独立摆放 | 从母布局里取**前 k 个**（母布局按 xhard4 的最大数量摆，低档用得少就取前面几个，位置、颜色都不变） |
| 某档在某个布局上抽不出合法场景 | 该档单独换一局 | 这个布局在四档**同时作废**，四档一起换下一个候选 |
| 每格局数 | 20 | 20 |

「布局」指位置、颜色、朝向、槽位这类与难度无关的东西，四档完全相同；「梯度」指次数、数量、序列、演示选择，四档各自抽。

### 3.2 逐任务：四档的差别是怎么做出来的

格式 xhard1 → xhard2 → xhard3 → xhard4；`[a,b]` 表示在区间里均匀抽整数。数值与 `scripts/README.md` 第 3 节相同。

| 任务 | 四档共用的布局（来自母布局） | 梯度（每档现场抽） | 低档物体更少时怎么取 |
|---|---|---|---|
| BinFill | 按钮位置、托盘偏移、12 个块的颜色／槽位／生成顺序 | 投入块数 6 → 7 → 8 → 9（总块数固定 12） | 块不变少，12 个块四档完全相同，只是要投入的数量不同 |
| PickXtimes | 按钮、目标区、目标块、干扰块的位置与颜色 | 抓取次数 [6,7] → [8,9] → [10,12] → [13,15] | 干扰块 1 → 2 → 3 → 3：取母布局 3 个干扰块里的前 1／2／3 个 |
| SwingXtimes | 同 PickXtimes，另加摆动目标点 | 摆动轮数 [4,5] → [6,7] → [8,9] → [10,11] | 干扰块 1 → 2 → 3 → 3，同上取前 k 个 |
| PickHighlight | 按钮、10 个块的位置与颜色 | pick 数 4 → 5 → 6 → 7；高亮哪几个块每档重抽 | 总块数 7 → 8 → 9 → 10：取母布局 10 个块的前 7／8／9 个 |
| VideoUnmask | 主容器位置与颜色、15 个干扰容器位置 | pick 2 → 3 → 3 → 3；干扰容器里放不放块每档重抽 | 干扰容器 8 → 10 → 13 → 15：取前 8／10／13 个 |
| ButtonUnmask | 同上，另加按钮位置；干扰容器共 14 个 | 同上 | 干扰容器 8 → 10 → 12 → 14：取前 8／10／12 个 |
| VideoUnmaskSwap | 主容器位置与颜色、被选目标、发起交换的容器、外环 10 个干扰容器位置与颜色 | swap [4,5] → [6,7] → [8,9] → [10,12]；pick 2 → 3 → 3 → 3；交换路线与外环块分配每档重抽 | 外环干扰 4 → 6 → 8 → 10：取前 4／6／8 个 |
| ButtonUnmaskSwap | 同上 | swap 4 → 5 → [6,7] → [8,9]；pick 2 → 3 → 3 → 3 | 外环干扰 4 → 6 → 8 → 10，同上 |
| VideoRepick | 7 个块的位置与颜色（有按钮就含按钮） | swap [3,4] → [5,6] → [7,8] → [9,12]；repick 2 → 3 → 4 → [5,6]；目标块与交换顺序每档重抽 | 块数 4 → 5 → 6 → 7：取前 4／5／6 个 |
| VideoPlaceButton | 目标区、按钮、块的颜色与位置、放置台位置 | 放台次数 1 块 3 次 → 1 块 4 次 → 2 块 5 次 → 2 块 6 次；演示序列、答案每档重抽 | 1 块的档取第 1 个块；放置台按本档需要的数量取前 k 个 |
| VideoPlaceOrder | 同 VideoPlaceButton | 总放台次数 5 → 6 → 7 → 8（都是 2 块）；访问顺序、演示、答案每档重抽 | 放置台取前 k 个 |
| PatternLock | 一条 25 格不重访路径（母布局抽 21～25 个节点） | 节点数 [9,12] → [13,16] → [17,20] → [21,25] | 取母路径的前 L 个节点（不重访路径的前缀仍然不重访） |
| RouteStick | 旋转角、障碍颜色、完整路线（节点与方向） | 段数 L [8,10] → [11,13] → [14,16] → [17,21] | 取母路线的前 L 段 |
| StopCube／InsertPeg／MoveCube | 只有 xhard4 | — | — |

两个要点：
- **「取前 k 个」为什么合法**：物体是一个个依次摆的，每个新物体只和已摆好的物体检查距离，所以前 k 个本身就是一组合法摆放。另外，环境在回注时本来就会重新检查，真不合法会直接报错，不会悄悄放过。
- **梯度为什么不能也从母布局里截**：比如 VideoRepick 的交换计划要依赖块的数量，BinFill 投入块数一变，后面的分配就全变。所以梯度一律在环境里按本档配置重新抽；只有布局是注入的。

### 3.3 最高档 xhard4 和现在是否一致

- **一致的**：配置数值、代码路径、回注方式都和 v6 的 xhard4 相同：先抽签冻结规格，生成与评估时按规格全量回注。梯度表一个数不改；StopCube／InsertPeg／MoveCube 仍然只有 xhard4，数值不动。
- **不一致的**：**具体这 20 局是重新抽的**。seed 从 v6 的 6e6 段换成 v7 的 14e6 段，所以场景和取值都和 v6 的 xhard4 不同，v6 的 xhard4 规格不再发布（git 历史保留）。
- **一个细微差别**：v7 的母布局要同时让 xhard1～3 都派生成功才会入选，派生失败的布局四档一起作废。所以 xhard4 的 20 局是「对低档也可行」的布局，理论上比 v6 的 xhard4 略有筛选偏差。候选作废率会在阶段 4 实测，并写进留档。

## 4. 新的 parity

### 4.1 三侧是什么

| 侧 | 是什么 | 要不要重新生成 |
|---|---|---|
| O | 官方 `1fadc0ec` 的产物 | 不要。已在 A40 上生成过一次，存档后永久复用 |
| P | **打了 tag 的固定锚点 commit** 的产物（不再是「修改前」） | 不要。直接复用这个 commit 当年验证时作为 H 的产物（验证过的 commit 不再验证） |
| H | 当前代码 | 每次改完都重新生成 |

每次都比 O:P、P:H、O:H 三对。锚点不跟着修改走：tag 打上后不再移动，要换锚点就打新 tag。

### 4.2 v7 这一轮怎么做

1. 当前 commit `ce3843b4` 已经做完 v6 的 OPH，给它打 tag `parity-anchor-v6`。
2. 实施 v7。
3. 用 v7 的代码再做一次 v6 OPH。O、P 都复用，只生成 H：原三档 16 任务 × 3 档 × 3 局 = 144，加上 v6 xhard（xhard1/2/3 各 13 任务 × 3 局 + xhard4 16 任务 × 3 局 = 165）。结果存档。
4. v7 自己的正式局生成两次，比对一致性（gen1 对 gen2，1100 局）。
5. 全部通过后，给 v7 的 commit 打 tag `parity-anchor-v7`。以后所有 parity 都以它作 P。

### 4.3 多卡容差：多大、为什么只认 A40

现行容差文件是 `scripts/configs/hard-parity-tolerances.json`，本轮不重标：

| 指标 | 阈值 | 含义 |
|---|---:|---|
| 动作 `action_max_rad` | 0.0413（约 2.4°） | 两侧对应时间步的关节动作最大差 |
| 状态 `state_max` | 0.0411 | 关节与夹爪状态的最大差 |
| 图像 `image_mad` | 1.0 | RGB（0～255）逐像素差的平均值 |
| 帧数 `frames_max` | 5 | 两侧的步数之差 |

**怎么来的**：O、P 两侧各在一台 A40 上生成 144 局，驱动都是 595.71.05，但节点不同。其中 143 对逐字节相同，只有 `PickHighlight/hard/seed 12300` 一对从第 549 步起因 RRT 墙钟噪声分叉，动作差 0.0275。阈值取这个差的 1.5 倍；图像和帧数取下界。

**所以它是「同型号、同驱动、跨节点」的容差，不是跨型号容差**：同一局在本机 RTX 6000 Ada 与 A40 上跑，第 7 步起就全面分叉（关节差 0.029 rad、RGB 逐像素差达 200 以上），这个差异从未进过标定。因此：
- O、P、H 三侧与 v7 的两次生成都必须是 A40 + 驱动 595.71.05；
- P 侧的缓存如果是在不同型号或驱动上生成的，不能复用，必须重新生成；
- 本机 Ada 与 aspen A6000 只做冒烟和静态检查，不产正式对拍数据。

## 5. 两策略评估（SimpleMemVLA 与 FrameSamp+Modulation）

- **评哪两个**：与上一个计划（`docs/plans/0927-robomme-hard-layered-plan.md` §八，留档 `docs/validation/newtask-v6/hard-split/stage6-eval-prep.md`、`stage7-eval.md`）相同：官方 SimpleMemVLA（`checkpoints/simplememvla_robomme`），以及官方 MME-VLA 的 `perceptual-framesamp-modul` 79999（即 FrameSamp + Modulation）。
- **调用方法与上次一致**：沿用上次的两个策略分支、入口与分片脚本（SimpleMemVLA `testhard_eval.py` + `scripts/gl_run_testhard.sh`；MME-VLA `scripts/gl_eval_shard.sh` + `merge_eval_shards.py`），以及上次的去代理、显存 0.75、`--resume` 修复。只做两处改动：
  1. 子模块 gitlink 从 `31e61259` 改为 v7 的 benchmark commit（新切 `PolicyEvalThirdParty-{simplememvla,mmevla}-<MMDD>-<HHMM>`），两个策略仓库也从上次分支再切出新分支 `*-v7-<MMDD>-<HHMM>`，不在旧分支上改。
  2. 打开每局视频回放（见下）。
  评估代码本身不因 xhard0 而改：`resolve_episode` 返回档名，`TIER_MAX_STEPS["xhard0"]=1300`。
- **评多少**：每个策略评完 v7 全部 1292 局，分两轮，顺序同上次（先 SimpleMemVLA 第一轮 → MME-VLA 第一轮 → 两者第二轮）：
  - 第一轮：55 格 × 前 10 局 + xhard0 16 任务 × 前 6 局 = 646；
  - 第二轮：剩下的 646。
  - 两策略合计 2 × 1292 = 2584 局；GL 10 × A40 占位 job，每轮切 10 片。
- **评估占位 job（用户 2026-09-28 定）**：由 agent 自己提交 10 个，规格与上次（`stage6-eval-prep.md`）相同，只把 CPU 从 1 改为 4：`sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:1 --gpu_cmode=shared --cpus-per-task=4 --mem=32G --time=48:00:00 --wrap='sleep infinity'`。依据是 12.226 实测（`ae1cba1e`）：首个请求 1 CPU 约 183 秒、4 CPU 约 61 秒，编译结束后每取一组动作都约 0.22 秒。**模型常驻先不动**，分片与启动方式与上次保持一致（常驻两任务连跑约 3 分 39 秒、分别启动约 6 分钟，只是单次观察，不是三轮完整比较）。生成阶段不另提 job，直接用用户已提交排队的占位 job。
- **视频回放：每局都存，落在本机盘 `/data/hongzefu`**：
  - 评估进程把每局 mp4 写到 NFS 暂存目录 `<NFS>/v7-eval-stage/<策略>/<轮>/<片>/`，文件名带 `task_tier_episode_seed`。
  - 本机 sled-vail 另起一个搬运进程（tmux 会话 `v7-vmove-<策略>`），它和评估是两个独立进程：**评估不等搬运，搬运慢了或断了也不影响评估。**
  - 搬运只处理「已完成」的视频：以该局在 `episodes.jsonl` 里已有终态行、且文件大小 10 秒不变为准。搬运时 `rsync` 到 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v7/eval-videos/<策略>/<tier>/<task>/`，核对 sha256 一致后删掉 NFS 上的副本。
  - 搬运进程挂了就重启；它只看暂存目录的现状，天然可续。评估结束后再跑一遍全量对账。
  - 本机 `/data` 目前剩余 815G。视频大小以冒烟那一局实测外推；预计超过 400G 时先停下问你。
- **判定行**（口径同上次）：`EVAL_SMOKE`（每策略 1 局 xhard0 + 1 局 xhard1）、`EVAL_ROUND1`／`EVAL_ROUND2`、`EVAL_IDENTITY_SET episodes=1292`、`EVAL_BINDING`（xhard0 局 `available=False`，其余局 `injected_mismatch=0`）、`EVAL_TIER_CAP`，新增 `EVAL_VIDEO=PASS policy=<名> episodes=1292 on_data=1292 sha_bad=0 nfs_left=0`。结果按 5 档分表，SimpleMemVLA 与 v6 同档的结果只作参考对照：v7 的布局都换了，不是同一批身份。

## 6. 实施步骤表

| 阶段 | 做什么 | 在哪 | 通过的判据 |
|---|---|---|---|
| 0 准备 | 取回原三档 144 局清单与官方 train 元数据；核对 xhard0 的 192 个身份；写布局白名单 | 本机 | `XHARD0_IDENTITY=PASS shape=16x1x12 identities=192` |
| 0′ 定 v6 锚点 | 确认阶段 4 生成 H 时的代码到 `ce3843b4` 之间没有行为改动；打 tag `parity-anchor-v6` 并推送；把已有的 H 产物（144 + 165）登记为它的 P 缓存 | 本机 | `ANCHOR_EQUIV=PASS`；`PARITY_ANCHOR=PASS tag=parity-anchor-v6 cached=144+165 sha_bad=0` |
| 1 改代码：xhard0 与规格模块 | builder 加 xhard0；新 seed 规则；`TIER_MAX_STEPS["xhard0"]=1300`；定向单测 | 本机 | `XHARD0_NATIVE=PASS`；`UPSTREAM_GUARD=PASS`；短测通过 |
| 2 改代码：母布局与派生 | 母布局抽签、派生到 xhard1～3、四档同步作废与递补；parity 锚点子命令 | 本机 | 无仿真单测通过 |
| 3 单格冒烟 | 1 任务 × 1 布局 × 4 档 | 本机 | 单格 `V7_LAYOUT_SHARED`、`V7_RESET_REPLAY` 通过 |
| 4 正式抽签与派生 | 16 任务 × 30 候选母布局；13 任务 × 3 档 × 30 派生 | GL A40 | `V7_LAYOUT_SHARED=PASS layouts=20 tiers=4`；`V7_TIER_MONOTONE=PASS` |
| 5 v6 回归 OPH | 只生成 H：144 + 165；O、P 复用 | GL A40 | `PARITY_O_P`／`P_H`／`O_H=PASS tier=native compared=144`；`PARITY_P_H=PASS tier=xhard compared=165` |
| 6 v7 生成两次 | gen1 1100 局；gen2 在另一个占位 job 上重放 | GL A40 | `PARITY_V7_TWICE=PASS compared=1100 tol_over=0` |
| 7 回放与入口冒烟 | 每格 1 局经评估链回放；xhard0 与 xhard1 各起 1 局 | 本机 | `V7_RESET_REPLAY=PASS injected_mismatch=0`；`HARD_EVAL_SMOKE=PASS episodes=2` |
| 8 发布与定 v7 锚点 | 替换包内规格、改 README、留档 `docs/validation/newtask-v7/`；打 tag `parity-anchor-v7` 并登记 | 本机 | `PARITY_ANCHOR=PASS tag=parity-anchor-v7`；`git diff --check` |
| 9 评估准备 | benchmark 切两个 `PolicyEvalThirdParty-*` 分支；两个策略仓库从上次分支切 v7 分支，改 gitlink 并打开视频；自行提交 10 个评估占位 job（每个 4 CPU、32G，模型常驻方式不变）；本机起搬运进程；每策略冒烟 2 局 | GL A40 + 本机 | `POLICY_DIFF` × 2、`SUBMODULE_PIN`、`EVAL_SMOKE` × 2、冒烟视频已到 `/data` |
| 10 评估两轮 | 每策略 646 + 646；边评边搬视频 | GL 10 × A40 | `EVAL_ROUND1/2`、`EVAL_IDENTITY_SET`、`EVAL_BINDING`、`EVAL_TIER_CAP`、`EVAL_VIDEO` × 2 |
| 11 收尾 | 5 档成功率表写入留档；NFS 暂存清空；按清单逐个 `scancel` 评估 job | 本机 | `EVAL_HOLD_RELEASE=PASS` |

第二部分 §2 预算已一次性批准，阶段按表连续执行；超出预算或判定 FAIL 即停该阶段及其后续并找用户。实施完成后，实测结果以子节追加在本表之后。

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

R1. `src/robomme/` 零改动（P2）；三个官方入口与录像器零 diff。xhard0 只在 `src/robomme_hard/` 侧新增条目与分派。
R2. 不把 `"xhard0"` 加进 `difficulty.py::NEWVALUE_DIFFICULTIES`／`VALID_DIFFICULTIES`；xhard0 传给 `gym.make` 的 `difficulty` 是 `"hard"`（`normalize_robomme_difficulty` 不认 `"xhard0"`，`spec_kind_for` 据此选原值类别）。
R3. 不改任何梯度取值（D-5）；`sampling_config` 由 `_extract.build_sampling(..., release="newtask-v6")` 提取的结果必须与 v7 xhard4 header 内嵌值相同（`tests/lightweight/test_sampling_config_split.py::test_v6_snapshot_matches_source` 继续钉死）。
R4. 派生失败四档同步作废，不许单档换布局；失败不换 seed、不重试到成功；基础设施失败每身份最多重跑 1 次。
R5. 对拍按 D-8／D-11～D-13；O 与已登记的 P 缓存不重新生成，tag 不移动不删除；`--calibrate` 仍只允许 `O:P`，v7 不重标、不改容差文件；两次生成必须同型号同驱动（A40），`generate` 的 A40 断言保留。
R6. reset／轨迹预算按 P3 一次性授权（§2 预算表，用户 2026-09-28 已全表批准），乘式写法（P5）；超出任一行上限先停下找用户。
R7. 主会话唯一整合与提交者；子代理只读或按互斥文件集合改动；子代理不 commit、不 push。
R8. `scripts/` 顶层四入口不变（P1）；新脚本落 `scripts/injection-dev/` 与 `scripts/parity/`。

## 1. 逐文件改动清单

### 1.1 `src/robomme_hard/env_record_wrapper/`

| 文件::锚点 | 改什么 | 关闭态／现有档 | v7 态 |
|---|---|---|---|
| `hard_specs.py::SCHEMA` → `SCHEMAS=("hard-specs/2","hard-specs/3")` | `validate_specs` 按 header schema 分支：`/2` 逻辑原样（读旧快照用），`/3` 增加 v7 校验 | V6 文件仍可读 | 包内四份为 `/3` |
| `hard_specs.py::SEED_PROFILES` 加 `"v7"`，新增 `V7_SEED_OFFSET=14_000_000`；`seed_rule_for(tier,"v7")` 四档同 offset；`_known_seed_rule` 遍历三族 | — | v6 规则族保持互斥断言 | v7 四档同 seed |
| `hard_specs.py::BUILDER_TIERS=("xhard0",*TIERS)`；`TIERS` 不变 | builder 档序与新值族分开（触点报告结论 1） | `TIERS` 仍四档 | builder 遍历五档 |
| `hard_specs.py::TIER_MAX_STEPS` 加 `"xhard0": 1300` | — | 四项不变 | 五项 |
| `hard_specs.py::XHARD0_CELLS`（16 任务）、`XHARD0_PER_TASK=12`、`XHARD0_EPISODES=(3,7,…,47)` 只作核对值，筛选仍按 `difficulty=="hard"` | — | — | 断言 12 条／任务 |
| `hard_specs.py` header 新键（`/3`，进 `IDENTITY_HEADER_KEYS`）：`layout_rule={"mode":"shared","parent_tier":"xhard4","whitelist_sha256":…}`；行新键（进 `IDENTITY_ROW_KEYS`）：`layout_parent`（xhard1～3 为 `{"tier":"xhard4","candidate":c,"spec_sha256":…}`，xhard4 为 `null`） | `validate_specs` 对 `/3`：四档 seed 同公式；派生行 `layout_parent.spec_sha256` 必须能在 xhard4 文件里找到同 candidate 行（跨文件校验放 `load_specs_v7(root)`，单文件校验只查形态） | — | — |
| `hard_specs.py::spec_binding` | 新增 `layout_injected`（L 点上 drawn≠frozen 且 drawn == `layout_drawn[path]` 的条数）与 `layout_drift`（drawn ≠ `layout_drawn` 的条数，计入 `injected_mismatch`） | 非 layered 规格两项为 0 | 派生局 `layout_injected>0`、`injected_mismatch==0` |
| `hard_builder.py::_xhard0_entries(env_id)` 新增 | 复用父类 `__init__` 以 `dataset="test"` 读到的元数据（清空 `metadata_index` 之前取出），筛 `difficulty=="hard"`，按原 episode 升序；校验源文件 sha256 在锁定清单内、12 条、seed 唯一 | — | 条目 `{tier:"xhard0", seed, source_episode, sampling_config:None, spec:None}` |
| `hard_builder.py::_test_hard_entries` | 先 xhard0 12 条，再 `for tier in TIERS` 原逻辑；每格断言 `delivery_per_cell==20` | — | 92／32 局 |
| `hard_builder.py::_hard_env_kwargs` | `tier=="xhard0"` 分支只返回 `seed, difficulty="hard"`；其余分支不变 | — | — |
| `hard_builder.py::resolve_identity` | xhard0 返回 `{episode, tier:"xhard0", source_dataset:"test", source_episode, seed, spec_sha256:None, source_run:None}`；派生行多返回 `layout_parent` | — | — |
| `__init__.py` | 导出 `BUILDER_TIERS` | — | — |

### 1.2 `src/robomme_hard/robomme_env/utils/episode_spec.py`

| 锚点 | 改什么 |
|---|---|
| `SPEC_KIND_LAYERED="native-layered/3"`，`SPEC_KINDS` 加入 | 派生规格类别；`spec_kind_for` 不变（按难度只区分原值／新值），layered 由构造参数决定 |
| `SpecRecorder.__init__(spec, task, identity, *, mode, parent=None, layout_paths=None)` | 新增 `mode="derive"`：`parent` 为母规格，`layout_paths` 为白名单（精确路径 + 前缀路径两类） |
| `SpecRecorder.value` | `derive`：路径命中白名单 → 照常抽、记 `layout_drawn[path]=drawn`、返回母值（列表值返回 `parent[:len(drawn)]`；母规格缺该路径 → 抛 `EpisodeSpecError`，不静默回退到抽样值）；未命中 → 照常抽、照常用。`replay` 且 `spec_kind==layered`：命中白名单 → 比对对象为 `spec["layout_drawn"][path]`，使用值为 `spec` 树里的冻结值；未命中 → 原逻辑 |
| `SpecRecorder.to_dict` | layered 导出多写 `layout_parent`、`layout_drawn`、`layout_paths_hit`（命中的白名单路径集合，供 `V7_LAYOUT_SHARED` 静态核对） |
| `leaf_paths`／`consumed_paths` | 不变；母规格多出的逐项路径不进派生规格（派生规格只含本局实际使用值），所以 `unused` 在派生局应为 0 |

### 1.3 布局白名单（写成 `src/robomme_hard/env_metadata/test-hard/layout_whitelist.json`，随包发布，sha 进 header）

| 环境 | L（注入；`*` 为逐项路径，`[:n]` 为列表按抽到长度取前缀） | G（现场重抽） |
|---|---|---|
| PickXtimes | `layout.button_xy`、`objects.color_order`、`objects.target_color_idx`、`layout.goal_xy`、`layout.cubes.*`、`objects.target_cube_idx`、`layout.distractors.*` | `objects.num_repeats` |
| SwingXtimes | 同上，另 `layout.targets.*` | `objects.num_repeats` |
| BinFill | `layout.dynamic`、`layout.button_xy`、`layout.board.offsets`、`objects.color_pool`、`objects.put_in_color`、`objects.spawn_numbers`、`objects.spawn_order`、`layout.slots.*`、`objects.slot_assignment`、`initializations.*.color_order` | `objects.target_numbers` |
| VideoUnmaskSwap／ButtonUnmaskSwap | `layout.type_choice`、`layout.bins.*`、`objects.color_order`、`objects.selected`、`objects.target_choice`、`objects.swap_initiator_indices`、`objects.swap_initiator_third`、`objects.distractors.bins.*`、`objects.distractors.color_order` | `objects.n_swaps`、`objects.n_picks`、`objects.swap_plan_seed`、`actions.swap_pairs.*`、`objects.distractors.cube_count`、`objects.distractors.cube_bins`、`objects.distractors.label_perm`、`objects.distractors.swap_plan_seed` |
| VideoUnmask／ButtonUnmask | `layout.button_xy`（BU）、`layout.bins.*`、`objects.color_order`、`objects.distractors.bins.*`、`objects.distractors.color_order` | `objects.distractors.cube_count`、`objects.distractors.cube_bins`、`actions.sampling_trace.constructor_draw`（BU） |
| VideoRepick | `objects.color_rgb`、`layout.cubes.*`（含 `layout.button_xy` 若存在） | `objects.num_repeats`、`objects.n_swaps`、`objects.target`、`objects.swap_initiators_remaining`、`objects.swap_plan_seed`、`actions.swap_pairs.*` |
| VideoPlaceButton | `layout.goal_xy`、`layout.button_xy`、`objects.color_order`、`layout.cubes.*`、`layout.targets.*` | `objects.demo_ids`、`objects.swap_pair_ids`、`objects.task_flag`、`objects.answer_demo_index`、`objects.extra_place_owner_ids`、`objects.extra_place_target_ids.*` |
| VideoPlaceOrder | 同 VideoPlaceButton 的 L | `objects.visit_counts_by_object`、`objects.demo_ids`、`objects.swap_pair_ids`、`objects.visit_ids_by_object.*`、`objects.answer_demo_index`、`objects.which_in_subset`、`objects.button_after_visit_index` |
| PickHighlight | `layout.button_xy`、`objects.color_rgba.*`、`layout.cubes.*` | `objects.n_cubes`、`objects.highlight_count`、`objects.highlight_ids` |
| PatternLock | `actions.path_nodes[:n]` | （无） |
| RouteStick | `layout.rotation_deg`、`layout.obstacle_rgb.*`、`actions.nodes[:n]`、`actions.directions.*` | `objects.L` |
| StopCube／InsertPeg／MoveCube | 不派生（只有 xhard4） | — |

白名单以子代理静态审计为准，实施阶段 1 须用「导出模式跑一次 xhard4 单局，比对 trace 里的全部 value 路径」核对每个环境的路径拼写，漏一条即 `EpisodeSpecError`。记录点一律不进白名单。

### 1.4 `scripts/injection-dev/`

| 文件::锚点 | 改什么 |
|---|---|
| `freeze_specs.py::main` | 加 `--seed-profile {v6,v7}`（默认 v7）、`--select` 支持 `0..19` 区间写法；`--tier xhard4 --candidates-per-env 30 --select 0..19`；header 写 `layout_rule` |
| `_draw.py::draw_task`／`merge_task_rows` | 传 v7 规则；其余不变 |
| `_freeze.py::freeze` | `/3` 封签；`delivery_per_cell=len(select)=20`；MoveCube 的 `stratified_select` 只对 xhard4 生效（不变） |
| 新增 `derive_specs.py` | 输入 xhard4 v7 文件 + 白名单 + 目标档；对每个候选起环境 `gym.make(task, sampling_config=cfg[tier], native_episode_spec=None, seed=母 seed, difficulty=tier)` 并把 recorder 置为 `derive` 模式（通过新的 `native_layout_parent=` kwarg 传入母规格与白名单）→ `reset` → 导出派生规格 → 按目标档 header 封签写 `xhard{1..3}/specs.jsonl`；失败记 `derive_fail`，并在四档同步把该候选标 `selected=False`；多 worker、`--workers`、`--gpus`、`--dry-run` 打印 reset 预算 |
| `_rollout.py::plan_pending`／`apply_results` | 递补改为跨档同步：某档某候选 rollout 失败 → 四档该候选全部退选，递补同一个下一候选（要求该候选四档规格都存在且 `tried=False`）；单档文件锁升级为四档目录锁 |
| `generate_h5.py` | `--mode continue` 输入 `--specs-root <test-hard 目录>`（四档一起）；`--mode replay` 不变（gen2 用） |
| `_report.py` | 报告增加 `derive_fail`、`sync_dropped` 计数（显式零值） |
| 删除 `migrate_smvla_specs.py` | 见 §7.5 |
| `site/v6_tier_monotone.py` | 加 `--specs-root` 读 v7 四档实际值输出 `V7_TIER_MONOTONE` |

### 1.5 `scripts/parity/`

| 文件::锚点 | 改什么 |
|---|---|
| `train_split_worker.py::run_one` | payload 增加可选 `layout_parent`；有则以 `derive` 模式构造 recorder；`spec_replay.json` 多写 `layout_injected`／`layout_drift` |
| `train_split_runner.py` | 透传 `--layout-parents <jsonl>`；`--identity-source formula` 接受 v7 规则 |
| `hard_parity.py`（锚点机制） | 新增 `anchor` 子命令（`register --tag --h5-root` 写 `docs/validation/parity-anchors.json`、`check --tag` 输出 `PARITY_ANCHOR`）；`compare` 的 P 侧改为 `--p-anchor <tag>` 从登记表取目录并先跑 `check`；`--calibrate` 仍只许 O:P |
| `hard_parity.py` | `SIDES` 加 `H2`，`PAIRS` 加 `H:H2`，`TIERS` 加 `"v7"`（清单从 v7 四档 `delivered` 行导出，键 `task/tier/candidate/seed`，`xhard_rows` 同时接受 `tier` 与 `difficulty`）；`cmd_generate --tier native` 透传 `--metadata-root scripts/configs/newtask-v3/official_train`（取回后）；`cmd_compare` 的 `shape` 文案按 tier 取：native `16x3x3`、v7 `13x3x20+16x1x20`；`_binding_ok` 对 `H2` 与 `H` 同规则；`cmd_import_s4` 删除 |
| `hard_regression.py` | `s4-subset` 删除；`reset-replay` 改为从 v7 四档每格取 candidate 最小的正式局（55 局）经评估链回放，判定 `V7_RESET_REPLAY`；新增 `layout-shared`（静态，`V7_LAYOUT_SHARED`）；`eval-smoke` 的局数断言改 `32 if XHARD4_ONLY else 92`，并接受 episode 0 为 xhard0（`available=False`）、episode 12 为回注局 |
| `scripts/configs/newtask-v3/` | 从 `6e70c0bf` 取回 `subset_manifest.json` 与 `official_train/`（只读清单，不再删除；P1 允许 `configs/` 子目录） |

### 1.6 `scripts/evaluation_hard.py`、README 与测试

- `evaluation_hard.py`：不改逻辑；`diff scripts/evaluation.py scripts/evaluation_hard.py` 仍恰好 README 第 1 节那 4 处。
- README 三份（`scripts/README.md`、`src/robomme_hard/README.md`、`scripts/parity/README.md`）按第一部分 §4 改数字与链路说明；`readme.md` 不动。
- 测试：新增 `tests/lightweight/test_xhard0_native.py`（身份 16×1×12、分派实参、`TIER_MAX_STEPS` 五项）、`test_v7_layout_shared.py`（白名单形态、`derive`／layered 回注在无仿真夹具下的 `layout_injected`／`layout_drift` 行为、四档同步递补状态机）、`test_v7_seed_rule.py`（v7 四档同 seed、与 v5/v6 段互不重叠）；改 `test_v6_difficulty_tiers.py::test_v6_seed_rule_offsets_disjoint` 限定 v6 族；`test_hard_state_machine.py` 参数化 v6/v7；`test_hard_parity.py` 补 `H:H2`／`v7` 用例；`test_wrapper_chain.py`（gpu）对 test-hard episode 0（xhard0）与 episode 12（xhard1）各做一次。

## 2. 预算（P3 一次性授权，乘式写法；用户 2026-09-28 全表批准）

| 项 | 乘式 | 上限 |
|---|---|---|
| 母布局 reset（阶段 4，xhard4 配置） | 16 任务 × 30 候选 = 480 次成功目标；`--max-reset-attempts` 每任务 50 | ≤ 16 × 50 = 800 次 reset |
| 派生 reset（阶段 4） | 13 任务 × 3 档 × 30 候选 = 1170 次，每候选只 1 次、失败不重抽 | ≤ 1170 次 reset |
| gen1 轨迹（阶段 6） | (13 任务 × 4 档 + 3 任务 × 1 档) × 20 局 = 1100 局；同步递补上限每格 10 → 55 格 × 10 = 550 | ≤ 1650 次轨迹 |
| gen2 轨迹（阶段 6） | 1100 正式局重放；基础设施失败每身份最多 1 次 | ≤ 1100 + 1100 |
| v6 回归 H 侧（阶段 5，O/P 复用不重跑） | 16 任务 × 3 档 × 3 局 = 144 + (13 任务 × 3 档 + 16 任务 × 1 档) × 3 局 = 165 | ≤ 309（+ 基础设施重跑 ≤ 309） |
| 回注回放（阶段 7） | 13 × 3 + 16 = 55 次 reset | 55 |
| 本机冒烟（阶段 3） | 1 任务 × (1 + 3) reset + 4 局 | 4 reset、4 轨迹 |
| 评估冒烟（阶段 9） | 2 策略 × 2 局（xhard0、xhard1 各 1） | 4 |
| 评估正式（阶段 10） | 2 策略 × (55 格 × 20 局 + 16 任务 × 12 局) = 2 × 1292 = 2584 | 2584 + 基础设施重评每策略每轮 ≤ 65 → ≤ 2844 |

worker：GL 每占位 job 16 worker（1 CPU + 12 G／worker）；预计耗时以阶段 3 单格实测外推后填入，不预先编数。停止条件：任一阶段判定行 FAIL 即停该阶段及其后续，保留产物与日志。

## 3. runbook（命令为拟定形态，参数名以实施时定稿为准）

```bash
# 阶段 0
git show 6e70c0bf:scripts/configs/newtask-v3/subset_manifest.json > scripts/configs/newtask-v3/subset_manifest.json
git archive 6e70c0bf scripts/configs/newtask-v3/official_train | tar -x
for f in src/robomme/env_metadata/test/*.json; do jq -c '{task:.env_id, hard_count:([.records[]|select(.difficulty=="hard")]|length), eps:[.records[]|select(.difficulty=="hard")|.episode]}' "$f"; done
uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream

# 阶段 3（本机，GPU 0）
uv run --no-sync python scripts/injection-dev/freeze_specs.py --tier xhard4 --tasks BinFill --seed-profile v7 --candidates-per-env 1 --select 0 --workers 1 --gpus 0 --out artifacts/newtask-v7/smoke/xhard4/specs.jsonl
uv run --no-sync python scripts/injection-dev/derive_specs.py --parent artifacts/newtask-v7/smoke/xhard4/specs.jsonl --tiers xhard1,xhard2,xhard3 --whitelist src/robomme_hard/env_metadata/test-hard/layout_whitelist.json --out-root artifacts/newtask-v7/smoke --workers 1 --gpus 0
uv run --no-sync python scripts/parity/hard_regression.py layout-shared --specs-root artifacts/newtask-v7/smoke
uv run --no-sync python scripts/injection-dev/generate_h5.py --mode continue --specs-root artifacts/newtask-v7/smoke --output artifacts/newtask-v7/smoke/rollout --workers 1 --gpu 0

# 阶段 4～6（GL 占位 job 内 srun --overlap --gpu_cmode=shared；先 --dry-run 打印预算再起 tmux）
uv run --frozen --no-sync python scripts/injection-dev/freeze_specs.py --tier xhard4 --tasks all --seed-profile v7 --candidates-per-env 30 --select 0..19 --max-reset-attempts 50 --workers 16 --gpus 0 --out <NFS>/v7/xhard4/specs.jsonl
uv run --frozen --no-sync python scripts/injection-dev/derive_specs.py --parent <NFS>/v7/xhard4/specs.jsonl --tiers xhard1,xhard2,xhard3 --out-root <NFS>/v7 --workers 16 --gpus 0
uv run --frozen --no-sync python scripts/injection-dev/generate_h5.py --mode continue --specs-root <NFS>/v7 --output <NFS>/v7/gen1 --workers 16 --gpu 0
uv run --frozen --no-sync python scripts/injection-dev/generate_h5.py --mode replay --identities <NFS>/v7/gen1/final-delivery.json --specs-root <NFS>/v7 --output <NFS>/v7/gen2 --workers 16 --gpu 0
uv run --frozen --no-sync python scripts/parity/hard_parity.py generate --side H --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json --workers 16 --gpu 0 --out /tmp/hs/H-native --stage <NFS>/hs-stage/H-native

# 本机比对
uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/hs-stage --dest artifacts/newtask-v7/parity --segments O-native,H-native,H-v7,H2-v7
uv run --no-sync python scripts/parity/hard_parity.py compare --pair O:H --tier native --manifest scripts/configs/newtask-v3/subset_manifest.json
uv run --no-sync python scripts/parity/hard_parity.py compare --pair H:H2 --tier v7 --manifest artifacts/newtask-v7/gen1/final-delivery.json
uv run --no-sync python scripts/parity/hard_regression.py reset-replay --out artifacts/newtask-v7/reset-replay
uv run --no-sync python scripts/parity/hard_regression.py eval-smoke --task BinFill --episode 0
uv run --no-sync python scripts/parity/hard_regression.py eval-smoke --task BinFill --episode 12
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q
```

长任务一律 detached tmux（会话名前缀 `v7-`，清单记入留档）+ Monitor 行缓冲过滤管道，过滤词含 `NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT|Traceback|EXIT_CODE=|全部完成`。集群操作按 `greatlakes.md`（48 h 占位 job、`--gpu_cmode=shared`、跑完按清单逐个 `scancel`）。

### 3.1 评估与视频搬运（阶段 9～10）

- 策略侧改动清单（新增在上次分支之上）：SimpleMemVLA 在 `testhard_eval.py` 里打开逐局 mp4 写出（若官方 `eval_success` 已有视频开关就只传参数；没有就在 `testhard_eval.py` 里用 `imageio` 写前视帧，不改官方文件）；MME-VLA 官方本来就逐局存视频，只把输出目录指到 NFS 暂存目录，并取消上次「每格只留 1 条」的删除步骤。
- 搬运脚本放在 `scripts/injection-dev/eval_video_mover.py`（P1：不进 `scripts/` 顶层）：`--stage <NFS 暂存> --dest artifacts/newtask-v7/eval-videos/<策略> --episodes-glob '<暂存>/**/episodes.jsonl' --stable-sec 10`，循环扫描 → rsync → 核对 sha256 → 删 NFS 副本 → 往 `moved.jsonl` 追加一行；每 60 秒打印 `VMOVE moved=<n> pending=<n> bytes=<n>`，结束时打印 `EXIT_CODE=`。在 tmux `v7-vmove-<策略>` 里运行，用 Monitor 盯 `VMOVE|Traceback|EXIT_CODE=`。
- 视频不进 git，也不进 bucket；留档只记清单与 sha256 的汇总。

## 4. 风险登记

| 风险 | 处置 |
|---|---|
| 白名单漏路径或拼错 | 阶段 1 用导出 trace 逐环境核对；`derive` 模式对母规格缺路径直接抛错，不静默回退 |
| 派生时外环交换／额外放台不可行（VUS/BUS/VPB） | 计入 `derive_fail`，四档同步作废该候选；候选留 10 个余量（用户定 30 候选）；余量耗尽即停并报用户，不追加抽签 |
| 前缀在低档下不合法（理论上不会） | 环境二次复核会抛错；出现即视为白名单分类错误，回到阶段 1 |
| 派生规格的 `layout_drawn` 与回放不等（随机流漂移） | `layout_drift>0` 计入 `injected_mismatch`，`V7_RESET_REPLAY` FAIL；不放宽 |
| `record()` 点在派生局与母局不同（如 `objects.distractor_count`） | 派生规格只含本局实际值，回放比对的是派生规格，不比母局 |
| 同步递补让四档目录锁竞争 | 目录锁 + 单写者；`--self-check` 核 identity 未变 |
| gen1/gen2 落在不同型号卡 | `generate` 保留 A40 断言；launch 记 GPU 名与驱动，`compare` 前核对相同，否则只报容差、不报 `sha_equal` |
| 144 清单来自官方 train 元数据，不含 test 的 hard seed | 它验证的是 `robomme_hard` 原生路径与官方路径一致，这正是 xhard0 所走的路径；xhard0 逐身份零差是 12.222 §5 的可选项，不在本文预算 |
| xhard0 走官方 `_worker` 时 `EpisodeJob.recovery_mode` 按 episode 号定（≤2 z、≤5 xy） | xhard0 不生成 h5，评估链 `make_env_for_episode` 不经 runner，此陷阱不触发；若日后生成须显式 `--no-recovery` 与官方 test 口径核对 |
| NFS 暂存被视频塞满或搬运进程挂掉 | 搬运与评估解耦；Monitor 盯 `VMOVE`，停更超过 10 分钟就重启搬运；暂存目录超过 200G 时通知用户 |
| 两个策略仓库读 `spec_binding` 字段 | 新增键只增不改；xhard0 返回 `available=False` 与现有 `None` 分支兼容，实施后各跑 1 局 smoke |

## 5. 盲区诚实清单

- 白名单与「前缀合法」结论来自静态审计，未运行任何环境；阶段 3 单格冒烟是第一次动态证据。
- 派生失败率未知；30 候选是否够 20 局要看阶段 4 实测，不够即停。
- 两次生成的 `sha_equal` 期望值不承诺（V6 时 P:H xhard 165 对逐字节相同，但 RRT 噪声存在）；判定只看容差与判定层。
- 跨型号容差从未标定；本机 Ada 与 aspen A6000 的任何 v7 产物都不进正式对拍。
- 本文未估算耗时；以阶段 3 单格实测外推后补。

## 6. 留档与 commit 纪律

- 本轮只提交本方案：`git diff --check`、`grep -c '^# 第一部分\|^# 第二部分'` 等于 2、链接目标存在；逐路径 `git add`，中文 commit（`12.223 …`）后立即 push。
- 实施各阶段：阶段 1～2 各一个 commit；阶段 4～6 起跑前 HEAD 精确等于所跑代码（起跑到 gen2 完成之间不 commit）；留档 `docs/validation/newtask-v7/`（判定行内联原文、GPU／驱动／依赖指纹、真实尝试计数、首个差异、退出码、输出路径、tmux 会话与 JobID 清单）；gen1 正式局 h5 搬回本机 `/data` 保留；gen2 在 `PARITY_V7_TWICE=PASS` 并留档后删除（用户定「gen2 比完即删」）；NFS 与 `/tmp` 不留大文件。
- 不把本文写入规则文件、不追加历史账本；用户原话与判定行按第 22 条进 commit body 与留档。

## 7. 机制、接口、验收与 parity 细节

本文其它处的「§2～§6」「第一部分 §N」旧引用对应本节 7.2～7.6。

### 7.1 口径编号表（D-1～D-13，第二部分引用用）

| 编号 | 口径 | 依据 |
|---|---|---|
| D-1 | xhard0 = 官方 test 的 `difficulty=="hard"` 记录，seed 逐条照抄元数据（不套公式），运行难度传 `"hard"`，不进新值族、不回注 | 12.222 §2、§3；本文 §2 |
| D-2 | xhard0 每任务 12 局（官方 test 每任务 50 = easy 26 / medium 12 / hard 12，原 episode 号 3,7,…,47） | 12.222 用户决定「和test的hard数量一致」；本文引言 |
| D-3 | xhard1～4 每任务 20 个母布局，四档同一布局、同一 seed；13 个有梯度任务四档共用，StopCube／InsertPeg／MoveCube 只有 xhard4、母布局即自身 | 原话 2；§3 |
| D-4 | 「布局」= 各环境取值点里与梯度无关的位置／颜色／朝向／槽位／初始化类点（白名单见第二部分 §1.3）；「梯度」= 次数、数量、序列、演示选择类点，按档现场重抽 | 原话 2「只有现在的梯度区别不一样」；§3.2 |
| D-5 | 梯度维度与数值逐字沿用现行四档表（`scripts/README.md` 第 3 节），本轮不改任何梯度取值 | 原话 2 附表 |
| D-6 | 接口与 `scripts/README.md` 第 1 节四处差别完全一致：`dataset="test-hard"`、`resolve_episode → (seed, tier)`、`TIER_MAX_STEPS[tier]`、`make_env_for_episode(ep, max_steps=…)`；只多一个档名 `xhard0` 与一个步数项 `1300` | 原话 4；§4 |
| D-7 | 发布名 v7：包内规格换成 `hard-specs/3`（含 v7 seed 规则与母布局字段），产物落 `artifacts/newtask-v7/`，留档落 `docs/validation/newtask-v7/`；V6 规格文件由 git 历史保留 | 原话 5；§5 |
| D-8 | 对拍分两类：v6 回归 OPH（D-11/D-12，取代原「只做 `PARITY_O_H`」）与 `PARITY_V7_TWICE`（v7 全部正式局两次生成，同型号 A40、不同作业）；容差沿用现行 `hard-parity-tolerances.json`，不重标 | 原话 6；§6 |
| D-9 | 集群侧生成一律 A40@greatlakes 占位 job；两次生成必须同型号同驱动，否则只能做容差内一致、不能报 sha 相等数 | §7「多卡容差」 |
| D-11 | **parity 锚点机制（以后都这么做）**：O = 官方 `1fadc0ec` 的存档产物，只生成一次、永久复用；P = 打 tag 的**固定锚点 commit** 的产物（不再是「修改前」）；H = 当前 HEAD。每次对拍都比 O:P、P:H、O:H。产物按 commit sha 缓存，**已验证过的 commit 不再重新生成**，P 侧直接复用它当年作为 H 的产物 | 原话 7、8；§6.1 |
| D-12 | v7 顺序：`ce3843b4` 打 tag `parity-anchor-v6`（v6 OPH 已在其等价代码上完成）→ 实施 v7 → 以 `parity-anchor-v6` 为 P 再跑一次 v6 OPH（原三档 144 + v6 xhard 165）并存档 → v7 验收全过后打 tag `parity-anchor-v7`，此后 P 一律取 `parity-anchor-v7` | 原话 8、9；§6.1 |
| D-13 | 容差只在 A40 上成立：O/P/H 三侧与缓存复用都要求 A40 + 同驱动（595.71.05）；驱动或型号不同的缓存不得作 P，只能重新生成 | 原话 8；§7 |
| D-10 | 母布局候选数、递补规则、xhard0 是否另生成 h5 等取整类细节由 agent 自定并写进本文，不再逐项询问（用户 2026-09-24「以后四舍五入这种问题都不要来找我」） | 记忆规则 |

### 7.2 数量：v7 每任务多少局、编号怎么排

| 档 | 来源 | 任务数 × 局数 | 合计 |
|---|---|---|---|
| xhard0 | 官方 test hard 子集，原生 hard | 16 任务 × 1 档 × 12 局 | 192 |
| xhard1～3 | 母布局派生 | 13 任务 × 3 档 × 20 局 | 780 |
| xhard4 | 母布局本体 | 16 任务 × 1 档 × 20 局 | 320 |
| 合计 | — | 16×1×12 + 13×3×20 + 16×1×20 | **1292** |

builder 的 episode 号按「xhard0 → xhard1 → xhard2 → xhard3 → xhard4，档内按候选号升序」排：13 个有梯度任务 0～11 是 xhard0、12～31 xhard1、32～51 xhard2、52～71 xhard3、72～91 xhard4，共 92 局；三个只有 xhard4 的任务 0～11 xhard0、12～31 xhard4，共 32 局。**这与 12.222 的「xhard0 追加在末尾以保住旧编号」不同**：v7 的 xhard1～4 全部重抽，旧编号本来就保不住，所以直接按档序排、以后不再挪。

为什么 xhard0 不能同时是「与 hard 完全一致」又是「20 个母布局之一」：母布局是在 xhard4 配置下抽出来的场景（例如 VideoUnmask 15 个干扰容器、PatternLock 21～25 节点），而原生 hard 的场景由官方代码在 hard 配置下抽（0 个干扰容器、4～8 节点）；MoveCube 的 hard 是原生场景、xhard4 是圆环 U，VideoRepick 的 hard 甚至是另一种任务机制。要让 xhard0「和原本的 hard 完全一致」，它就只能走官方 hard 路径、用官方 test 的 seed，与母布局无关。**这是 D-1／D-3 并列而不合并的原因。**

xhard0 身份的静态核实（12.222 已用 `jq` 做过，本轮重跑一次原样）：16 个任务全部 hard 12 局、原 episode 号 `3,7,11,15,19,23,27,31,35,39,43,47`；seed 逐条来自元数据（例如 PickXtimes 原 episode 15 的 seed 是 `511501` 而非公式值 `511500`，BinFill 原 episode 3 的 seed 是 `540302`）。

### 7.3 机制：母布局怎么来、低档怎么共用

#### 7.3.1 现状为什么做不到共用

- 现在四档各有一套 seed 偏移（[`hard_specs.py`](src/robomme_hard/env_record_wrapper/hard_specs.py)::`V6_SEED_OFFSETS`：xhard4 6e6、xhard1 8e6、xhard2 10e6、xhard3 12e6），布局天然互不相同。
- 回注通道 [`episode_spec.py`](src/robomme_hard/robomme_env/utils/episode_spec.py)::`SpecRecorder.value` 在回注模式下**对每个取值点都先按本局 seed 真抽一次，再拿抽到的值与冻结值比对，最后返回冻结值**；`hard_specs.py::spec_binding` 把所有 value 点的不等都计入 `injected_mismatch`，而 [`hard_regression.py`](scripts/parity/hard_regression.py) 的 `reset-replay`／`eval-smoke` 要求它为 0。因此「把 xhard4 的规格改一改喂给 xhard1」会在每个布局点都记一条不等，直接触发闸门。
- 仓库里没有「给定母规格派生各档规格」的入口：[`generate_h5.py`](scripts/injection-dev/generate_h5.py) 的 `--mode replay` 只按 `(task, tier, seed)` 去已有规格行里查；`freeze_specs.py` 只会 reset 抽签。
- 纯 JSON 截断（xhard4 规格按低档数量取前缀）对 PickXtimes／SwingXtimes／PickHighlight／PatternLock／RouteStick 可行，但对 VideoRepick（`swap_initiators_remaining` 必须是 range(k−1) 的完整排列、`swap_pairs` 引用 ≥k 的块、可行图 G 随块集合变化）、VideoPlaceButton xhard1/2（台数 5→4、额外放台候选按占用表重算）、VideoUnmaskSwap／ButtonUnmaskSwap（`cube_bins`／`label_perm` 与 count 耦合、外环规划要重跑可行性）不可行，BinFill 的 `target_numbers` 是每色聚合值也没有「前缀」可取。**所以不能靠改 JSON，必须让梯度类取值点在环境里现场重抽。**

#### 7.3.2 分层回注：布局注入、梯度重抽、记录点重导出

定义：每个环境的取值点分两类（白名单在第二部分 §1.3）。**布局类** `L`：位置、颜色、朝向、槽位、初始化、type_choice 之类，与档位无关或只随数量变长；**梯度类** `G`：`num_repeats`、`n_swaps`、`n_picks`、`target_numbers`、`cube_count`、`cube_bins`、`label_perm`、`swap_plan_seed`、`swap_pairs.k`、`highlight_*`、`demo_ids`、`visit_*`、`L` 等。记录点（`record()`）全部视为派生量，由派生运行重新导出。

```text
阶段 A  母布局抽签（每任务 30 个候选，xhard4 配置，v7 seed 规则，只 reset）
        ├─ 13 个有梯度任务：母布局规格 = xhard4 规格本体（spec_kind native-newvalue/2，mismatch=0）
        └─ StopCube / InsertPeg / MoveCube：同上，只此一档
阶段 B  派生（13 任务 × 3 档 × 每候选 1 次 reset，「layered」模式）
        SpecRecorder(mode="derive", parent=母规格, layout_paths=白名单)
        ├─ 路径 ∈ L：照常抽一次（随机流不漂移），返回母值；列表值按 len(抽到值) 取前缀；
        │            逐项路径（layout.distractors.<color>_0、layout.cubes.i、layout.targets.i、
        │            objects.distractors.bins.i、actions.directions.i）低档只访问前 k 个，多出的自动 unused
        ├─ 路径 ∈ G：照常抽、照常用（本档 config 决定范围）
        ├─ record()：照常记本档实际值
        └─ 导出：spec_kind="native-layered/3"，spec 树 = 本局实际使用值；
                  另存 layout_parent{sha256, tier="xhard4", candidate}、layout_drawn{path: 本档抽到的值}
阶段 C  生成 h5（55 格 × 20 局，回注模式）
        └─ 回注 native-layered/3：L 点比对对象改为 layout_drawn（核随机流），使用值 = 冻结值；
           G 点与原来一样比冻结值；spec_binding 新增 layout_injected 计数，injected_mismatch 仍须 0
```

⚠ 陷阱与反例：
- **不能用「四档同 seed、让 RNG 自己碰」代替注入**。同 seed 下 PickXtimes／SwingXtimes／VideoUnmask／PickHighlight／RouteStick 节点的布局前缀按代码顺序推断会逐位相同，但 BinFill（`target_numbers` 逐单位抽样次数随 put_in 变，后面 spawn 分配、槽位整体平移）、VideoPlaceOrder（`count_order` 只在 xhard1/3 抽）、PatternLock（搜索循环停在不同尝试次数）都不会相同；而且「天然相同」是推断不是保证。v7 用注入保证，同 seed 只是顺带（D-3 四档同 seed 便于身份对齐）。
- **前缀合法性靠什么保证**：依序放置的对象只对已放对象做中心距／OBB 检查，前缀天然合法；四档的区域、最小中心距、内环 bin 数（VU/BU 8 个、VUS/BUS 4 个）、BinFill 12 槽相同，母布局在 xhard4 下合法 ⇒ 前缀在低档下合法。回注时环境里的二次复核（`object_generation.py::_assert_center_rules_hold`、`unmask_distractor_sampler.py::verify_distractor_layout`、`swap_uniform.verify_swap_sequence`、`BinFill._spawn_cubes_xhard` 槽位复核、`PatternLock._check_xhard_path`）照常执行，不合法会响亮失败而不是静默通过。
- **派生仍可能失败**：梯度点现场重抽可能撞上 `SceneGenerationError`（外环交换某窗不可行、额外放台无候选），这时该候选在**四档同步作废**，按候选号顺延，不允许某档单独换布局（否则「同一布局」不成立）。
- **PatternLock 没有布局**：它唯一的取值点是 `actions.path_nodes`，v7 把它当作可取前缀的布局点（xhard4 的 21～25 节点路径，低档取前 L 个节点，8 邻接不重访的前缀仍合法）；RouteStick 的 `actions.nodes` 同理。这是 D-10 范围内的自定细节。
- **只把 `objects.num_repeats` 之类标量留给现场重抽**，不把 xhard4 的 14 次硬塞给 xhard1（不在 [6,7] 区间会被 `_assert_*` 拒绝）。

收益（静态盘点，未实测）：16 个环境全部落入「可行」——PickXtimes／SwingXtimes／PickHighlight／VideoUnmask／ButtonUnmask／RouteStick／PatternLock 只需白名单；BinFill／VideoPlaceOrder／VideoPlaceButton／VideoRepick／VideoUnmaskSwap／ButtonUnmaskSwap 由「梯度点现场重抽」消掉全部耦合问题；三个 xhard4 独有任务不涉及派生。

#### 7.3.3 seed 与身份

v7 seed 规则（`hard_specs.py` 新增 profile `"v7"`）：`seed = 14_000_000 + env_code × 100_000 + candidate × 100 + attempt`，**四档同一 offset**，同一候选号在四档里 seed 相同；与 V5 段（4e6）、V6 四段（6e6～12e6）互不重叠。`validate_specs` 对 v7 文件要求：四档 header 的 `seed_rule` 相同；每行 `seed` 等于公式；派生行的 `layout_parent.sha256` 等于 xhard4 同候选行的 `spec_sha256`。

身份键仍是 `(task, tier, seed)`（[`hard_parity.py`](scripts/parity/hard_parity.py)::`ident`），同 seed 跨档靠 tier 区分。`resolve_identity` 对派生行多返回 `layout_parent`，对 xhard0 返回 `source_dataset="test"`、`source_episode`、`spec_sha256=None`。

#### 7.3.4 改动前后链路

```text
改动前：
  官方 test 元数据 → (seed, hard) ────────────────────────────→ 官方 robomme 环境（无 xhard0）
  test-hard/xhard{1..4}/specs.jsonl（V6，四段 seed）→ 条目 → gym.make(sampling_config, native_episode_spec) → robomme_hard 环境

改动后：
  官方 test 元数据 hard 子集 → xhard0 条目（seed 原值，difficulty="hard"，无 sampling_config、无 spec）→ robomme_hard 原生 hard 分支
  test-hard/xhard4/specs.jsonl（v7 母布局）→ 条目 → gym.make(sampling_config[xhard4], native_episode_spec)      → 全量回注（同现在）
  test-hard/xhard{1..3}/specs.jsonl（v7 派生）→ 条目 → gym.make(sampling_config[tier], native_episode_spec=layered) → L 点注入 + G 点冻结值
```

每一跳的观测键集合、形状、dtype 与现在完全相同（本方案不改任何观测、动作、控制模式；`RUNTIME` 四项不变）；xhard0 局的观测与官方同局逐字段相同是 12.222 §5 的零差验收对象，不由本文重复宣称。本链路无可训练参数。

### 7.4 接口：与 `scripts/README.md` 第 1 节逐条对照

| README 第 1 节的四处差别 | v7 |
|---|---|
| 换包 `robomme_hard.env_record_wrapper.BenchmarkEnvBuilder` | 不变 |
| `dataset="test-hard"` | 不变；每任务局数由 80 → 92（xhard4 独有三任务 20 → 32），16 任务合计 1100 → 1292 |
| `resolve_episode(ep) → (seed, tier)` | 不变；`tier` 取值多一个 `"xhard0"` |
| `make_env_for_episode(ep, max_steps=TIER_MAX_STEPS[tier])` | 不变；`TIER_MAX_STEPS` 增加 `"xhard0": 1300`（与官方 `evaluation.py` 默认相同，12.222 §3.2） |

`spec_binding(env)` 对 xhard0 局返回 `{"available": False}`（没有 recorder），对派生局多返回 `layout_injected`；两个策略仓库（SimpleMemVLA、MME-VLA）现有接法只是把返回字典写进 info，不用改。`scripts/evaluation_hard.py` 的查表循环不改逻辑。

README 要改的只有数字与说明：第 1 节「换数据集」的局数、「多拿一个档位」加 xhard0、「步数上限按档给」加 1300；第 3 节表加 xhard0 列（与 hard 列逐字相同）；第 4 节链路改为「母布局抽签 → 派生 → 生成」三阶段与 v7 seed 规则；第 5 节对拍改为两条。

### 7.5 版本、文件与发布

- 包内 `src/robomme_hard/env_metadata/test-hard/xhard{1..4}/specs.jsonl` 整体替换为 v7（schema `hard-specs/3`）；xhard0 不打包规格，builder 直接读官方 test 元数据（12.222 §3.1，读取时校验源文件摘要与 12 条／任务）。
- V6 的 `s4-setup-manifest.json`、`s4-to-delivery.json` 与 `scripts/configs/newtask-v6/v6-02/` 快照：v7 后失效，从工作树删除、git 历史保留（P1 允许删子目录内容；`configs/` 保留 `hard-parity-tolerances.json`）。`hard_regression.py` 的 `s4-subset`／`reset-replay` 子命令换成 v7 版（第二部分 §1.5）。
- `migrate_smvla_specs.py` 的 `check` 在 v7 后必然 FAIL（钉死 1100 与 `13x3x20+16x20`），删除该文件（历史迁移已完成、git 可取回）。
- h5 产物：v7 两次生成各 1100 局，落 `artifacts/newtask-v7/gen1/`、`gen2/`（bucket 被 HF 计费拒绝，不上传）；gen1 正式局保留在本机 `/data`，gen2 在 `PARITY_V7_TWICE=PASS` 留档后删除，只留逐局 sha 清单；v6 旧产物不动；xhard0 不生成 h5（它是评估身份，不是生成产物；12.222 §5 的轨迹比较是可选项，本文不列入预算）。

### 7.6 验收（查什么 / 怎么查 / 过了说明什么 / 判定行）

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| xhard0 身份 | 官方 test 元数据 hard 子集 vs builder 条目：任务、原 episode、seed、源文件 sha256 逐条相等 | 引入的恰好是原来的 192 个身份 | `XHARD0_IDENTITY=PASS shape=16x1x12 identities=192 missing=0 extra=0` |
| xhard0 原生分支 | 捕获 `gym.make` 实参：`difficulty=="hard"`、无 `sampling_config`、无 `native_episode_spec`；`spec_binding` 返回 `available=False` | 没有误入新值路径 | `XHARD0_NATIVE=PASS runtime_difficulty=hard injected=0 tasks=16` |
| 母布局共用 | 静态：xhard1～3 每行 `layout_parent.sha256 == xhard4 同候选 spec_sha256`，且该行 spec 里每个白名单路径的值等于母值（列表取前缀、逐项路径取子集）；四档 `seed` 相同 | 四档确实是同一批 20 个布局 | `V7_LAYOUT_SHARED=PASS tasks=13 layouts=20 tiers=4 rows=780 parent_mismatch=0 seed_mismatch=0` |
| 梯度单调 | 对每任务每布局，四档在用户指定维度的实际值按档非降且落在各档区间（沿用 `site/v6_tier_monotone.py` 口径） | 只有梯度不同，且梯度确实分档 | `V7_TIER_MONOTONE=PASS cells=55 violations=0` |
| 回注零差 | 每格取 1 局经评估链 `make_env_for_episode` + `reset` 后 `spec_binding`：`injected_mismatch==0`，派生局 `layout_injected==|L 白名单命中数|`，`unused` 只含母布局多出的逐项路径 | 评估时建出的场景与生成时同一局 | `V7_RESET_REPLAY=PASS shape=13x3+16 injected_mismatch=0 layout_drift=0` |
| v6 回归 OPH | O 存档、P = `parity-anchor-v6` 缓存、H = v7 HEAD 新生成（A40），§6.1 | v7 没改变官方原生路径与 v6 回注行为 | `PARITY_ANCHOR=PASS`；`PARITY_O_P`/`P_H`/`O_H=PASS tier=native shape=16x3x3 compared=144 tol_over=0`；`PARITY_P_H=PASS tier=xhard shape=13x3x3+16x3 compared=165 tol_over=0` |
| v7 两次生成一致 | gen1 用 `generate_h5 --mode continue` 出正式 1100 局；gen2 用 `--mode replay --identities <gen1 交付清单>` 在另一占位 job（同型号 A40、同驱动）重放；`compare --pair H:H2 --tier v7` | 规格 → h5 的映射确定，只剩 RRT 墙钟噪声 | `PARITY_V7_TWICE=PASS shape=13x3x20+16x1x20 compared=1100 tol_over=0`（`sha_equal` 作参考） |
| 官方冻结 | `upstream_guard.py check --require-upstream`；三入口与录像器零 diff | 基线没被改写 | `UPSTREAM_GUARD=PASS` |
| 入口冒烟 | `hard_regression.py eval-smoke --task BinFill --episode 0`（xhard0 局）与 `--episode 12`（xhard1 局） | 评估入口两类局都能起 | `HARD_EVAL_SMOKE=PASS episodes=2` |

为什么这些判据能成立：身份类判据是纯静态集合比对；`V7_LAYOUT_SHARED` 比的是规格文件里的值树，不依赖运行；回注零差靠 `SpecRecorder` 的「抽一次核随机流、用冻结值」机制（第 3.2 节）；两条对拍在同型号同驱动 A40 上做，这是 §7 说明的逐位边界，所以才允许把 `sha_equal` 当参考数、把容差当判定。

### 7.7 parity 锚点实现细节（D-11～D-13）

**三侧定义**（`hard_parity.py` 的 `SIDES` 不变，含义改）：

| 侧 | 来源 | 生成频率 | 存放 |
|---|---|---|---|
| O | 官方 `1fadc0ec` worktree + vendor `_worker` | 只生成一次（阶段 4 已有 O-native 144 局，A40/595.71.05） | 本机 `artifacts/newtask-v6/hard-split/h5/O-native`，逐局 sha 清单；bucket 续传待 HF 计费恢复，不阻塞 |
| P | `git tag parity-anchor-*` 指向的 commit | **不重跑**：复用该 commit 作为 H 时的已验证产物 | 缓存登记表 `docs/validation/parity-anchors.json`（新文件） |
| H | 当前 HEAD | 每次修改后生成 | `artifacts/<版本>/parity/H-<短sha>-<tier>` |

**缓存登记表** 每条：`tag`、`commit`、`tier`、`h5_root`、`identities_sha256`（逐局 sha 清单的哈希）、`gpu_model`、`driver`、`generated_at_commit`（产物实际生成时的 src_commit）、`equivalence`（若 tag commit ≠ 生成 commit，记 `git diff --stat <生成> <tag> -- src/robomme_hard scripts/parity scripts/injection-dev` 为空或仅文档的核验结论）、判定行原文。`hard_parity.py compare` 取 P 侧前先核：tag 解析出的 sha == 登记 `commit`、逐局 sha 重算相等、GPU/驱动与 H 侧相同；任一不符 → `PARITY_ANCHOR=FAIL`，不比。

**「验证过就不再验证」的边界**：只省去重新生成 O 与 P；每次改动后的 H 必须新生成并比三对。锚点 tag 一经打上不移动、不删除（tag push 到远端）。

**判定行**：`PARITY_ANCHOR=PASS tag=parity-anchor-v6 commit=<sha> cached=144+165 sha_bad=0 gpu=A40 driver=595.71.05`；`PARITY_O_P`／`PARITY_P_H`／`PARITY_O_H tier=native shape=16x3x3 compared=144 tol_over=0`；`PARITY_P_H tier=xhard shape=13x3x3+16x3 compared=165 tol_over=0`。

### 7.8 容差数值与跨卡探针原文

**结论先说**：现行容差只有一套，标定自**同型号（A40）、同驱动、不同节点**的 O:P 144 对，**不是跨 GPU 型号的容差**；跨型号只做过 1 条身份的逐位探针，结论是「逐位一致只在同型号 + 同驱动内成立」，跨型号的容差判据至今没有标定。

权威配置 [`scripts/configs/hard-parity-tolerances.json`](scripts/configs/hard-parity-tolerances.json)，消费者 `hard_parity.py::pair_metrics`／`calibrate`／`cmd_compare`：

| 指标 | 阈值 | 比较的量 |
|---|---:|---|
| `action_max_rad` | 0.041265913943240015（≈2.36°） | 共同时间步内 `action/joint_action` 全分量最大绝对差 |
| `state_max` | 0.04113650321960449 | `obs/joint_state` 与 `obs/gripper_state` 最大绝对差（混合字段，不能统一称米或弧度） |
| `image_mad` | 1.0 | 0～255 RGB 逐像素绝对差先逐画面平均、再两相机与共同时间步平均（不是逐像素上限） |
| `frames_max` | 5 | 两侧时间步数之差 |

公式 `阈值 = max(观测最大差 × 1.5, 下界)`，帧数先向上取整；下界 0.005／0.005／1.0／5；「合理性上界」0.05／0.05／10／200 检查的是**原始最大差**、超了只让标定 FAIL，不截断阈值。标定数据：O（gl1517，job 62126060）与 P（gl1504，job 62126061），均 A40、驱动 595.71.05、16 worker；144 对里 143 对逐字节相同，唯一非零的一对是 `PickHighlight/hard/seed 12300` 从第 549 步起分叉（动作最大差 0.0275、图像平均差 0.144、帧数相同），O 与 H 在该身份上逐字节相同，报告归因为 P 侧那次运行的 RRT 墙钟噪声（`docs/validation/newtask-v6/hard-split/stage4.md`「容差标定」）。所以：阈值 = 0.0275×1.5、0.0274×1.5，图像与帧数取下界。

**为什么它不是「多卡」容差**：[`20260927-cross-hardware-probe.md`](docs/validation/newtask-v6/hard-split/20260927-cross-hardware-probe.md) 用同一条身份（BinFill/ep0/seed 4000/easy）在四张卡上跑官方 A 路：A40 两个节点 sha 相同；RTX 6000 Ada（本机）vs RTX A6000（aspen）只有 16 个 `joint_action` 值差 ≤ 2.24e-18；**Ada vs A40 从第 7 步起全面分叉**：`joint_state` 最大 0.029 rad、`eef_state` 0.0377、`front_depth` 最大 2.67e3、RGB 逐像素最大 211～235。这说明 0.029 rad 的跨型号状态差已接近 0.041 的阈值，且图像逐像素差远超 1（`image_mad` 是平均值，单局是否超 1.0 未算），跨型号数据没有进过任何标定。因此 D-9 要求 v7 两次生成都在 A40 上做；本机 Ada 与 aspen A6000 只用于冒烟与静态验收，不产正式对拍数据。

另有一个容易混淆的数：`hard_specs.py::RECORDED_FLOAT_TOL = 1e-5` 是回注校验里「只记录不回注」的浮点观测点允许的漂移，与轨迹对拍容差无关；派生局的 `layout_drawn` 核随机流也用它。
