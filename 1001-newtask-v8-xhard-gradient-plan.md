# 1001 newtask v8：xhard 梯度（三任务扩至 xhard1～5）与统一步数上限的配置调整方案

> **权威性**：本文件是 v8 配置调整的方案，同时记录本轮本机实测的结论与教训。它**只规划配置，不实施**：改 `src/robomme_hard` 的常量、改 `TIER_MAX_STEPS`、正式抽签和生成，每一步都要用户单独批准。
>
> **代码锚点**：HEAD `07d56981`（12.264），分支 `newtaskRelease-v5`，工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`。v7 交付规格是包内 `src/robomme_hard/env_metadata/test-hard/xhard{1..4}/specs.jsonl`，四份 header 的 `sampling_config_sha256` 都是 `4a308ee7…`，`seed_rule.offset=14000000`。
>
> **外部锚点**：官方环境源码 `1fadc0ec`，官方生成编排 `d53f21a7`（vendor 在 `scripts/parity/official/`）。两者都不改。
>
> **commit 编号**：本文件随 `12.277` 提交；2026-10-01 按用户「局数沿用 v7 总数、缺档平分」指令修订（§0.2 第 7 条）随 `12.278` 提交；同日按用户「三任务改为 xhard1～5 每档定值各 10 局」指令再修订（§0.2 第 8 条）随 `12.279` 提交。实施时从 12.280 接续。
>
> **授权边界**：本轮获准的只有「本机随便跑 reset 和 rollout」（用户原话见 §0.2 第 6 条）。
> - 全部探针都走仓库原有的 `scripts/parity/train_split_runner.py → train_split_worker.run_one`，只从外部传入改过的 `sampling_config`。**仓库里的代码一行没改。**
> - 探针脚本放在会话 scratchpad。产物在 `artifacts/v8-probe/`，不进 git；h5 与视频读完步数即删，现存约 6 MB 小文件。
>
> **术语**：
> - **执行步**：h5 的 `timestep_*` 个数，减去 `info/is_video_demo` 为真的帧数。口径同 `scripts/parity/hard_regression.py::cmd_step_headroom`。
> - **步数上限**：`TIER_MAX_STEPS` 只约束执行段，演示段不计入。
> - **d**：放置圆盘中心到机械臂底座 (−0.615, 0) 的水平距离，单位米。

# 第一部分（给人看）

## 0. 总览

### 0.1 一句话方案

按合作者给的表决定每个任务保留哪几档。**PickXtimes、SwingXtimes、StopCube 三个任务新增 xhard5 档，xhard1～5 每档一个定值、各 10 局**（用户 2026-10-01 指令，§0.2 第 8 条）；其余 13 个任务局数沿用 v7 总数（各 80 局或 20 局），被砍掉档位的局数平分到保留的档里（§0.2 第 7 条）。逐格表见 §4.3，全集 1070 局。

- **要改梯度数值的只有 3 个任务**：PickXtimes、SwingXtimes、StopCube，三者同时扩为 xhard1～5 五档、每档一个定值（§5）。其余 13 个任务的数值不动，只改交付哪几档、每档多少局。
- **会把执行步推过 1600 的只有 PickXtimes。**
  - 原区域下，抓 9～10 次常态超过 1600：本机实测抓 9 次最大 1973、抓 10 次最大 1919。
  - 抓 8 次在圆盘极近底座（d≈0.37）时也到过 1614。
  - 原因不是任务变难，而是圆盘离底座太近（d < 0.5）时，微分 IK 的零空间漂移让每一轮抓放越来越长。
- **推荐方案 A**：
  - 保留合作者的 6～10 次。
  - 只把 xhard 档的圆盘采样区域收紧到 d ≥ 0.505。
  - 本轮实测 80 局，0 失败：抓 6～10 次最大 1046／1143／1275／1421／1577。
  - 加上 v7 里本来就落在该区域内的 6 个布局：抓 7 次最大 1182，抓 10 次最大 **1591**。
  - 已知全集最大执行步约 1590，统一上限按「实测最大向上取整到百」定为 **1600**。余量只有约 10 步，见 §6。
- **备选方案 B**（严格只改梯度值）：
  - 把 PickXtimes 顶值压到 8 次。
  - 原区域下抓 8 次实测 21 局最大 1533，另有一局极近底座布局为 1614。
  - 按同一取整规则，上限是 1600～1700（看正式交付里是否抽到这类布局），而且要改合作者的次数表。

### 0.2 已定口径与用户原话（按时间）

1. **合作者的交付表**，用户转述，逐字照录：
   > 你有的档位设置的太离散了
   >
   > BinFill, xhard 1,2 即 put 6,7 个cube, 各 25 episodes
   > PickXtimes, pick times 改成 6, 7, 8, 9,10 各10 episode
   > SwingXtimes 摆动 4,5,6,7,8次 各10 episode
   > StopCube 次数 6,7,8,9,10 各10 episode
   >
   > VideoUnmask/ButtonUnmask xhard1-4 各 50/4 episodes
   > VideoUnmaskSwap/ButtonUnmaskSwap  保留xhard 1,2， 各 25 episodes
   >
   > VideoPlaceButton/VideoPlaceOrder 保留 xhard 1,2，各 25 episodes
   > PickHighlight  保留 xhard 1,2，各 25 episodes
   > VideoRepick 保留 xhard 1,2，各 25 episodes
   >
   > MoveCube xhard4 only
   > InsertPeg  xhard4 only
   > RouteStick xhard1,2,3  各 50/3 episodes
   > PatternLock  xhard1,2,3  各 50/3  episodes
   > 嗯嗯收到好的
   > 生成完data后，确定出expert demo 里面的最大execution step, 作为 max_step， 应该在 1600 附近
   > 现在的执行上限都是虚高
2. 「给出下一版的方案 只给出配置调整的方案 你可以实测 max step尽可能在1600左右这是你先统计一下现在超过一千600步的task然后你再调整一下这个配置然后实测一下然后尽可能给我一个完整的结论」
3. 「调整的内容只能是XHard。1234的这些梯度。」
   - 我的理解：xhard0（即官方 hard）和原三档 easy／medium／hard 一律不动，只调 xhard1～4（第 8 条之后含三任务新增的 xhard5）。
   - 方案 A 收紧的圆盘区域也在 xhard 子树里（`PickXtimes.py::XHARD_DECISION`），不影响 xhard0。但它不是「梯度值」，超出这句话的字面范围，所以列为待决项（§10）。
4. 「尽可能使用塞subagent」
5. 「结束之后把你的计画和所有的教训结论都写入一个根目录文档。」（即本文件）
6. /goal：「尽可能给我完整的结论和调整建议 我要吃饭去了 你可以自己在本机随便跑reset 和 rollout 单次配置调整尽可能先少跑一些先把各个配置都跑完了有一个全面的了解了在跑。单个配置更多的resetrout。并且你每次跑日晒汤乳酪的时候你要稍微测个速对于一次工作的时间要有一个认知不能跑太久了尽可能在两小时内收尾」
   - 「日晒汤乳酪」按语音转写理解为「reset 和 rollout」。
   - 本轮实际做法是：先每个配置 3～4 局全覆盖，再给关键配置加量；每轮都测速。13:14 开工，13:41 跑完第四轮（东部时间）。
7. 「episode数量先都不改都按照V7生成的总数量。然后如果档位XR的1234中有缺少这个档位比如说X2的只有12这种情况下就把数量平分。就是保证总数是一样的修改计划并且重新告诉我现在要改成什么样」（2026-10-01，本文件修订依据）
   - 我的理解：每任务总局数与 v7 相同（四档任务 80、仅 xhard4 任务 20）。四档齐全的任务仍每档 20；只保留部分档的任务把 80 平分到保留的档（两档各 40，三档 27／27／26，低档多一局）。
   - 本条对 PickXtimes、SwingXtimes、StopCube 的部分（原拟 xhard4 放两个值按值平分、StopCube 单档分层）已被第 8 条取代，这三个任务改为五档各 10 局。
8. 「PickXtimes, pick times 改成 6, 7, 8, 9,10 各10 episode／SwingXtimes 摆动 4,5,6,7,8次 各10 episode／StopCube 次数 6,7,8,9,10 各10 episode　这些都需要改为xhard12345 每一档都是确定的　其他都可以了」（2026-10-01，本文件第二次修订依据）
   - 我的理解：这三个任务新增 xhard5 档，xhard1～5 每档恰好一个取值（PickXtimes 6／7／8／9／10 次，SwingXtimes 4／5／6／7／8 轮，StopCube 6／7／8／9／10 次），每档 10 局，每任务 50 局；不再有「一档两个值」或「单档按值分层」。
   - 「其他都可以了」理解为其余 13 个任务按第 7 条（局数沿用 v7、缺档平分）不再改；其他任务不加 xhard5。
   - 全集总数：3 任务 × 5 档 × 10 + 4 任务 × 4 档 × 20 + 7 任务 × 2 档 × 40 + 2 任务 × (27 + 27 + 26) + 2 任务 × 1 档 × 20 = 150 + 320 + 560 + 160 + 40 = 1070；含 xhard0 则 1070 + 16 × 12 = 1262。

**已定口径**：

| 编号 | 口径 | 依据 |
|---|---|---|
| ① | 执行步口径同 `cmd_step_headroom` | 术语 |
| ② | xhard1～5 共用一个上限 N：取新交付集 expert demo 的最大执行步，再向上取整到百，目标约 1600；xhard0 保持官方 1300 | §6 |
| ③ | PickXtimes／SwingXtimes／StopCube 扩为 xhard1～5，每档一个定值、各 10 局；其他任务不加 xhard5 | §0.2 第 8 条、§5 |
| ④ | 干扰块数 xhard1～4 = 1／2／3／4 不动，xhard5 = 4（`BLOCK_DISTRACTOR_COLORS` 只有 4 色）；它不影响步数 | §3、§5 |
| ⑤ | 三任务之外的 13 个任务每任务总局数沿用 v7（80 或 20），缺档平分；全集 1070 局、含 xhard0 1262 局 | §0.2 第 7、8 条、§4.3 |

## 1. 现状：v7 有多少局超过 1600

数据来自 v7 gen1 交付的 1100 局。逐局重算的结果与 `artifacts/newtask-v7/step-headroom-gen1.json` 的 `per_cell_max`／`per_cell_mean` 在 55 格上全部一致。

| 格子（梯度值） | n | 执行步均值 | max | 超过 1600 的局数 |
|---|---|---|---|---|
| PickXtimes xhard2（抓 10 次） | 20 | 1588 | 1857 | 6 |
| PickXtimes xhard3（12 次） | 20 | 1889 | 2293 | 20 |
| PickXtimes xhard4（15 次） | 20 | 2354 | 2998 | 20 |
| BinFill xhard3（投 8 块） | 20 | 1518 | 1650 | 2 |
| BinFill xhard4（投 9 块） | 20 | 1689 | 1842 | 16 |

- **超限的局**：共 64 局超过 1600，全部是 PickXtimes 和 BinFill。xhard0 的最大值是 BinFill 1074。
  - 按含演示段的总步数算会有 204 局超过 1600，多出来的是 RouteStick、VideoPlaceButton、VideoPlaceOrder、VideoRepick 这类演示很长的任务。上限只约束执行段，所以与它们无关。
- **现行上限怎么来的**：`hard_specs.py::TIER_MAX_STEPS = {xhard0:1300, xhard1:1500, xhard2:2400, xhard3:2900, xhard4:3800}`。
  - xhard2～4 的值来自 B4 规则：取「实测最大执行步 × 1.25」，再向上取整到百；实测最大值来自 PickXtimes 的 1857／2293／2998。xhard1 的 1500 沿用 v6。
  - 同档其余任务全部继承这个上限。例如 InsertPeg 专家最多只要 277 步，却给了 3800 步。
- **评估侧证据**：
  - 两策略合计 2 × 1292 局里，成功局超过 1600 步的只有 2 局，都是 SimpleMemVLA：BinFill xhard2 一局 1823 步，MoveCube xhard4 一局 3120 步。
  - xhard1～4 中，timeout 局消耗的策略评估步数约占全部评估步数的 36%（SimpleMemVLA 307,500／860,944）。这里是策略侧步数，不是文首定义的专家执行步。
  - 所以「虚高」成立。

## 2. 按合作者的表直接套用：各任务最大执行步

| 任务 | 新表取值 | 执行步 max（n） | > 1600？ |
|---|---|---|---|
| **PickXtimes（原区域）** | 6／7／8／9／10 次 | 1282（4）／1304（v7 20）／1533（21）／**1973**（22）／**1919**（8） | **9、10 次超** |
| PickXtimes（近底座强化带，含原区域外位置） | 6～10 次 | 1301／1408／**1614**／**2002**／**1990**（各 2～3）；其中圆盘落在原区域内的只有 7 次 1408、8 次 1614、9 次 2002 | 原区域内 8、9 次也可能超 |
| BinFill | 6／7 块 | 1315（本轮 6 + v7 20）／1464（本轮 17 + v7 20） | 否 |
| SwingXtimes | 4～8 轮 | 618（4）／732（v7 20）／841（4）／913（v7 20）／983（9） | 否 |
| StopCube | 6～10 次 | 371／424／492／555／611（各 1～3） | 否 |
| PickHighlight | xhard1、2 | 960／1152（v7 各 20） | 否 |
| VideoRepick | xhard1、2 | 422／616 | 否 |
| ButtonUnmaskSwap／VideoUnmaskSwap | xhard1、2 | 494、648／273、429 | 否 |
| VideoUnmask／ButtonUnmask | xhard1～4 | ≤454／≤557 | 否 |
| VideoPlaceButton／VideoPlaceOrder | xhard1、2 | 执行段 ≤236／≤259；演示段逐局 868～1707 帧，不计入 | 否 |
| PatternLock | 12／15／18 节点 | 422／521／626 | 否 |
| RouteStick | 10／13／16 段 | 恒为 500／650／800（= 50·L） | 否 |
| MoveCube／InsertPeg | xhard4 | 300／277 | 否 |

**结论**：不调整的话，全集最大执行步由 PickXtimes 抓 9～10 次决定，约 1900～2000，不是 1600。排第二的是 BinFill 7 块，约 1460。

## 3. 机理：PickXtimes 的长尾来自圆盘近底座时的零空间漂移

**定义**：PickXtimes 的执行段由三部分组成。

| 段 | 内容 | 步数 |
|---|---|---|
| 首轮抓放 F | 从 home 出发，带水平运输 | 182～260，均值约 220 |
| 第 2～N 轮循环 Σc_k | 方块已在圆盘上，原地「抓起 → 放回」 | 正常每轮 123～158 |
| 按钮 B | 按下按钮结束 | 稳定布局 91～122，均值约 104 |

- 夹爪每次开合固定 6 步。
- 按 v7 交付 92 局做最小二乘：exec ≈ 121 + 148·N（只算粗略，同一 N 的波动由布局决定）。

**代码锚点**：
- 子目标表：`PickXtimes._load_scene`。
- 抓放：`subgoal_planner_func.py::solve_pickup`、`solve_putonto_whenhold`。
- 规划：mplib `Planner.plan_screw`。先用 pinv(J) 做微分 IK，再用 TOPPRA 做时间参数化，步数 = int(时长 / 0.05)。
- 圆盘区域：`PickXtimes.py::XHARD_DECISION["goal_position_policy"]`，现值中心 (−0.1, 0)、半宽 0.2。
  - `spawn_random_target` 要求圆盘完整落在方区内，所以圆盘中心范围是「中心 ± (半宽 − 半径 0.04)」，现值下 x ∈ [−0.26, 0.06]。
  - 按钮由 `build_button` 随机放在 x ∈ [−0.25, −0.15]、y ∈ [−0.2, 0.2]，圆盘还要避开它。

**漂移的过程**：
- d 小于约 0.5 时，手臂在圆盘上方是折叠姿态：第 4 关节约 −2.6～−2.8 rad，关节 0 与关节 2 接近同轴。
- pinv 微分 IK 每轮都沿零空间滑一点。末端走的笛卡尔路径不变（约 0.27 m），关节路程却越来越长。
- 例：v7 cand 17 共 14 轮循环，q0 累计 +0.84 rad，每轮关节路程从 1.95 rad 涨到 4.88 rad，每轮步数从 158 涨到 235。

**示意**（同为抓 10 次，执行步随 d 变化；数据来自 v7 xhard2 与本轮探针）：

```text
d:     0.37  0.39  0.40  0.44  0.45  0.46 | 0.49  0.51  0.52  0.58  0.64  0.66
执行步: 1919  1857  1802  1750  1647  1615 | 1580  1558  1585  1591  1471  1457
       └──────── 漂移带：每轮 +1～6 步 ────────┘└──── 稳定：每轮步数近似常数 ────┘
```

d ≥ 0.5 之后已经没有漂移。剩下 1457～1591 的差别来自方块与圆盘的相对位置：每轮循环本身长短不同，但不再逐轮变长。

**⚠ 陷阱**：
- 这条长尾**不是** RRT 重试，也**不是** fail-safe。
  - v7 有 80 局 PickXtimes、共 5520 段运动，按 `eef_action` 查直线度，偏离弦线最多 3.8 cm，看不到绕行。
  - `--no-recovery` 下，夹爪重抓段数为 0。
- **干扰块数不影响步数**：screw 规划不带点云避障（`use_point_cloud=False`）。同一 seed 下干扰从 1 块到 4 块，前缀步数差 ≤ 15 步。
  - 本轮第一轮里，抓 10 次配 1 块干扰最大 1647、配 4 块干扰最大 1919，差别全来自 d（0.452 对 0.368），不是来自干扰块。
- **只看少量样本会严重低估尾部**：
  - v6 同一格，3 局的最大值约 2215，20 局的最大值是 3384。
  - 本轮原区域抓 9 次，前 12 局最大 1676，再加 10 局就到了 1973。
- **0.45 附近仍然漂移**：d = 0.451 的一局抓 9 次 1676，d = 0.452 的一局抓 10 次 1647。所以阈值要取 0.5，不能取 0.45。

**收益**：
- 圆盘中心收进 x、y ∈ [−0.11, 0.11] 后，d ≥ 0.505（实测最小 0.5097）。
- 本轮探针抓 6～10 次的最大值是 1046／1143／1275／1421／1577。
- v7 里本来就落在这个区域内的 6 个布局：抓 7 次最大 1182，抓 10 次最大 1591。
- 抓 10 次合计 44 局的极差为 1424～1591。同档波动从原区域的 1424～1919 收窄到约 170 步以内。

## 4. 推荐的配置调整

### 4.1 PickXtimes（唯一需要权衡的任务）

| 方案 | 抓取次数（xhard1／2／3／4／5） | 圆盘区域（xhard1～5 共用 `XHARD_DECISION.goal_position_policy`） | 本轮实测最大执行步 | 评价 |
|---|---|---|---|---|
| **A（推荐）** | 6／7／8／9／10 | 中心 (−0.1, 0)、半宽 0.2 → **中心 (0, 0)、半宽 0.15**；圆盘中心 x、y ∈ [−0.11, 0.11]，d ≥ 0.505 | 本轮 1046／1143／1275／1421／1577（n = 10／10／10／12／38，0 失败）；加上 v7 区域内布局后，7 次 1182、10 次 **1591** | 保留合作者的 6～10 次（五档各 10 局），已知全集最大约 1590，上限 1600。代价是改了一个布局参数，不是梯度值 |
| B（只改梯度） | 4／5／6／7／8 | 不动 | 8 次 1533（21 局），极近底座布局 1614 | 完全符合「只改梯度」，上限 1600～1700。但最难档从 10 次降到 8 次，且 xhard1 的 4 次、xhard2 的 5 次与 xhard0（[4,5]）同难度 |
| 不调整 | 6／7／8／9／10 | 不动 | 9 次 1973、10 次 1919；原区域内近底座布局 9 次可达 2002 | max_step 会在 1900～2000，达不到「1600 附近」 |

方案 A 的几点说明：
- **区域改动只落在 xhard 子树**：`_newvalue_decision` 深拷贝 `XHARD_DECISION`，`_native_decision` 的原值 `goal_position_policy` 不动。`sampling_config.py::assert_native_decision` 剥掉新值键后与原值逐键比对，所以 xhard0 和原三档不受影响。
  - 本轮探针把同样的覆盖值从外部传进环境，这道守卫逐局放行，说明结构相符。
- **reset 代价**：半宽 0.15 的区域在 80 局里圆盘放置失败 0 次。区域收得更窄时会出现 `SceneGenerationError`（报错为 Region crowded or constraints too tight，圆盘与按钮、方块挤不下）：半宽 0.12 的近底座强化带 2/15，半宽 0.08 的内侧带 1/4。
- **对视觉分布的影响**：圆盘离开桌面靠近底座的那一侧，集中到桌面中部。方块区域（中心 (−0.1, 0)、半宽 0.25）不变。

### 4.2 其余 15 个任务

| 任务 | 交付档 × 每档局数 | 梯度值（只列要改的） | 预计最大执行步 |
|---|---|---|---|
| BinFill | xhard1、xhard2 各 40 | 不改（6／7 块） | 约 1470～1500 |
| SwingXtimes | xhard1～5 各 10 | `number_range` 5／7／9／11 → **4／5／6／7／8**（新增 xhard5） | 约 1000 |
| StopCube | xhard1～5 各 10 | 由「仅 xhard4、`stop_time_range` {6,16} 随机」改为 **五档各一个定值 6／7／8／9／10**；`move_interval` 仍为 [60]；去掉 `require_xhard4_only` 闸门 | 约 615 |
| VideoUnmask／ButtonUnmask | xhard1～4 各 20（与 v7 同） | 不改 | ≤ 557 |
| VideoUnmaskSwap／ButtonUnmaskSwap | xhard1、xhard2 各 40 | 不改 | ≤ 648 |
| VideoPlaceButton／VideoPlaceOrder | xhard1、xhard2 各 40 | 不改 | 执行段 ≤ 259 |
| PickHighlight | xhard1、xhard2 各 40 | 不改 | ≤ 1152 |
| VideoRepick | xhard1、xhard2 各 40 | 不改 | ≤ 616 |
| PatternLock | xhard1～3 = 27／27／26 | 不改（12／15／18） | ≤ 626 |
| RouteStick | xhard1～3 = 27／27／26 | 不改（10／13／16） | 800 |
| MoveCube／InsertPeg | 仅 xhard4，20 局（与 v7 同） | 不改 | ≤ 300 |

**交付规模**（P5 乘式）：
- 新值档：3 个五档任务 × 5 档 × 10 = 150；4 个四档任务 × 4 档 × 20 = 320；7 个两档任务 × 2 档 × 40 = 560；2 个三档任务 × (27 + 27 + 26) = 160；2 个单档任务 × 1 档 × 20 = 40。合计 1070（v7 为 1100：PickXtimes、SwingXtimes 各减 30，StopCube 加 30）。
- 若保留 xhard0：再加 16 任务 × 12 = 192，共 1262。

### 4.3 逐格局数表（口径 ⑤）

三任务五档各 10 局；其余任务每任务总数等于 v7，只保留部分档的任务把 80 平分，三档取 27／27／26（低档多一局）。

| 任务 | xhard1 | xhard2 | xhard3 | xhard4 | xhard5 | v8 合计 | v7 合计 |
|---|---|---|---|---|---|---|---|
| PickXtimes | 10（6 次） | 10（7 次） | 10（8 次） | 10（9 次） | 10（10 次） | 50 | 80 |
| SwingXtimes | 10（4 轮） | 10（5 轮） | 10（6 轮） | 10（7 轮） | 10（8 轮） | 50 | 80 |
| StopCube | 10（6 次） | 10（7 次） | 10（8 次） | 10（9 次） | 10（10 次） | 50 | 20 |
| VideoUnmask | 20 | 20 | 20 | 20 | — | 80 | 80 |
| ButtonUnmask | 20 | 20 | 20 | 20 | — | 80 | 80 |
| BinFill | 40 | 40 | — | — | — | 80 | 80 |
| VideoUnmaskSwap | 40 | 40 | — | — | — | 80 | 80 |
| ButtonUnmaskSwap | 40 | 40 | — | — | — | 80 | 80 |
| VideoPlaceButton | 40 | 40 | — | — | — | 80 | 80 |
| VideoPlaceOrder | 40 | 40 | — | — | — | 80 | 80 |
| PickHighlight | 40 | 40 | — | — | — | 80 | 80 |
| VideoRepick | 40 | 40 | — | — | — | 80 | 80 |
| RouteStick | 27 | 27 | 26 | — | — | 80 | 80 |
| PatternLock | 27 | 27 | 26 | — | — | 80 | 80 |
| MoveCube | — | — | — | 20 | — | 20 | 20 |
| InsertPeg | — | — | — | 20 | — | 20 | 20 |
| **合计** | 404 | 404 | 122 | 110 | 30 | **1070** | **1100** |

格子数从 v7 的 55 变为 45（3 × 5 + 2 × 4 + 7 × 2 + 2 × 3 + 2 × 1）。xhard5 只有三任务有格子，其他 13 个任务没有 xhard5 配置。xhard0 不在此表内，去留见 §10 第 3 条。

## 5. 三任务扩为 xhard1～5，每档一个定值

用户 2026-10-01 定（§0.2 第 8 条）：PickXtimes、SwingXtimes、StopCube 各加一个 xhard5 档，五档各放一个取值、各 10 局。此前的 M-A（顶档放两个值）与 S1（StopCube 单档分层）两个方案作废。

**五档取值**

| 任务 | 维度 | xhard1 | xhard2 | xhard3 | xhard4 | xhard5 |
|---|---|---|---|---|---|---|
| PickXtimes | 抓放次数 | 6 | 7 | 8 | 9 | 10 |
| PickXtimes | 干扰块数 | 1 | 2 | 3 | 4 | 4 |
| SwingXtimes | 摆动轮数 | 4 | 5 | 6 | 7 | 8 |
| SwingXtimes | 干扰块数 | 1 | 2 | 3 | 4 | 4 |
| StopCube | 停止序号 `stop_time` | 6 | 7 | 8 | 9 | 10 |
| StopCube | 方块速度 `move_interval` | 60 | 60 | 60 | 60 | 60 |

- xhard5 的干扰块数取 4，与 xhard4 相同：`utils/xhard.py::BLOCK_DISTRACTOR_COLORS` 只有黄／青／品红／橙 4 色，`_newvalue_decision(n)` 按前 n 色截取，第 5 块没有颜色可用；加第 5 色属于视觉改动，不在本轮。这样 xhard5 与 xhard4 的物体集合相同，xhard5 可以直接当母布局档。
- 每档单值意味着工具链「每档一个定数」的假设**继续成立**：`tests/_shared/v7_tier_values.py::_point`、`v6_tier_monotone.check_fixed` 不需要支持区间；`_freeze.stratified_select` 也不需要按值分层。

**结构改动（只有这三个任务加档，其他 13 个任务没有 xhard5）**
- `utils/difficulty.py::NEWVALUE_DIFFICULTIES` 加 `xhard5`；`newvalue_tier` 到 5。没有 xhard5 配置的任务收到 `xhard5` 时明确报错（`configs` 里没有该键），不静默映射。
- `hard_specs.TIERS` 加 `xhard5`；`BUILDER_TIERS` 随之为 xhard0～5；逐格局数表只给三任务填 xhard5；包内新增 `env_metadata/test-hard/xhard5/specs.jsonl`，只含三任务。
- 三任务各加 `config_xhard5` 与 `NEWVALUE_DECISION["xhard5"]`；StopCube 从「仅 xhard4」改为 xhard1～5 五份 `configs`（`stop_time_range` 写成 `{low:k, high_exclusive:k+1}`），`_native_decision` 暴露五个子键，`__init__` 去掉 `require_xhard4_only`，`hard_specs.XHARD4_ONLY` 只剩 InsertPeg、MoveCube。
- 母布局档从固定的 `xhard4` 改为「该任务的最高交付档」：三任务为 xhard5，其余为 xhard4。`freeze_specs.py`、`derive_specs.py`（`parent_header["difficulty"]`、`layout_parent.tier`、`seed_rule_for`）、`_rollout.py::_task_tiers`、`hard_specs.validate_specs` 里写死的 `"xhard4"` 改为按任务查表。
- StopCube 要进 `layout_whitelist.json`：L = 母值全部照抄（路线端点、速度），G = `stop_time`。
- `TIER_MAX_STEPS` 加 `xhard5: N`。

**机制前提**：环境层按区间抽样，区间两端相等就是定值。`PickXtimes`／`SwingXtimes` 用 `torch.randint(number_range[0], number_range[1]+1)`；`StopCube._initialize_episode` 用 `torch.randint(low, high_exclusive)`。所以每档定值只需改常量，不改抽样代码。

## 6. 统一步数上限

**口径**
- `TIER_MAX_STEPS` 里 xhard1～5 都设成同一个 N，xhard0 保持 1300。
- 这样 `scripts/evaluation_hard.py` 不用改，P1 写明的「与 `evaluation.py` 只差 4 处」照旧成立。

**N 的取法**
- N = 新交付集（正式生成后）逐局执行步的最大值，再向上取整到百。不再乘 1.25。
- 方案 A 下已知最大值是 1591（v7 区域内布局；本轮探针最大 1577），**预计 N = 1600**。
- 正式交付的最大值若超过 1600（例如 1612），就取 1700。

**零余量的代价**
- **专家侧几乎没有余量**：1591 离 1600 只差 9 步。另外，同一份规格的两次生成本身也有噪声——v7 H:H2 的 1100 局里有 13 局判为 RRT 噪声，帧数最多差 116。所以正式交付的最大值落在 1600 以上的可能性不能排除。
- **策略侧会被截掉一些成功**：策略的成功局可以比专家长不少。BinFill 约 1.25～1.4 倍（例：一局成功用了 1455 步，同一局专家 1049 步）；短任务可达 2～3 倍（VideoUnmask xhard2 一局成功用了 1552 步，MoveCube 一局 3120 对专家 470）。
  - N = 1600 时，v7 评估里会被截掉的成功局只有 2 局：BinFill xhard2 的 1823 步、MoveCube xhard4 的 3120 步。其余成功局都在 1600 以内。
- 要不要留余量（例如取 1700 或 1800）由用户定（§10 第 5 条）。

**判据要改写**
- `hard_regression.py::cmd_step_headroom` 现在是「90% 判据 + B4 ×1.25 提议」。上限等于实测最大值时，这个判据按定义必然 FAIL。
- 要改成「全集最大执行步 ≤ N」，并报出全局最大值。

## 7. 验收

| 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|
| 交付形态 | `validate_specs` 按逐格局数表核对选中数 | 每格局数符合 §4.3 表（三任务五档各 10，其余每任务总数等于 v7） | `V8_DELIVERY_SET=PASS tasks=16 cells=45 total=1070` |
| 五档定值 | `v6_tier_monotone.py --fixed` 读 spec 的 `objects.num_repeats`／`actions.stop_time` | 三任务每档 10 局的取值全部等于 §5 表，无区间 | `V8_TIER_FIXED=PASS tasks=3 tiers=5 mismatches=0` |
| 圆盘区域（方案 A） | 读每局 `layout.goal_xy`，算 d | 没有 d < 0.5 的局 | `V8_GOAL_CLEARANCE=PASS n=50 min_d=<值>` |
| 步数上限 | 改写后的 `cmd_step_headroom` 逐局读 h5 | 全集最大执行步 ≤ N，且 N = 实测最大值向上取整到百 | `V8_STEP_CAP=PASS max=<实测> cap=<N> over=0` |
| xhard0 与原三档不变 | `test_v4_xhard_pickxtimes.py::test_decision_visible_part_unchanged`（Swing、InsertPeg 同名测试）；`hard_regression.py xhard0-reset-parity` | 剥掉新值键后的 decision 与原值逐键相同；xhard0 的 reset 状态与官方逐局一致 | 测试无 failed；`XHARD0_RESET_PARITY=PASS det_diff=0` |
| 官方源码不变 | `upstream_guard.py check --require-upstream` | `src/robomme` 与官方 `1fadc0ec` 逐字节相同 | `UPSTREAM_GUARD=PASS` |
| 核心短测 | `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q` | 改值后同步的测试与守卫都对上 | 末行 `passed` 且无 failed |

**为什么这些判据能成立**：执行步主要由布局和梯度值决定——screw 规划是确定的，夹爪步数固定。同一份规格回注后步数基本可以复现：v7 两次生成 H:H2 的 1100 局里有 1086 局逐字节相同；另外 13 局判为 RRT 噪声，帧数最多差 116；还有 1 局（InsertPeg/8）第二次生成失败（`PARITY_H_H2` 行：`frames_equal=1086 noise=13 frames_max=116/5`）。所以 `V8_STEP_CAP` 必须在正式交付的那一份 h5 上判，不能拿探针数字代替。

## 8. 实施步骤（每步须单独获批）

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 用户拍板 §10 的 6 个待决项 | 全部有答复 |
| 1 | 新增 xhard5 档位结构（§5「结构改动」）并改常量（第二部分 §2.1），同步测试副本与站点守卫 | 核心短测通过；`UPSTREAM_GUARD=PASS`；`XHARD0_RESET_PARITY=PASS` |
| 2 | 交付形态：逐格局数表、按值分层选签与递补、builder 查表（第二部分 §2.2） | 纯 CPU 夹具测试通过，覆盖「写 JSON → 读 JSON」之后的形态 |
| 3 | 母布局抽签 → 派生 → 生成；先按 P3／P5 一次性报预算（第二部分 §2.4） | `V8_DELIVERY_SET`、`V8_TIER_FIXED`、`V8_GOAL_CLEARANCE` |
| 4 | 量全集最大执行步，定 N，写回 `TIER_MAX_STEPS` | `V8_STEP_CAP=PASS` |

## 9. 本轮本机实测

**环境**：2026-10-01，sled-vail，2 × RTX 6000 Ada，32 核，HEAD `07d56981`。工作区 clean，只有 `third_party/SimpleMemVLA` 子模块内容有改动（git status 显示 ` m`），属于他人在途工作，未碰。

**做法**
- 从 v7 header 取 `sampling_config`，只覆盖 decision 里的几个键：`number_range.xhardK`、`xhardK.goal_position_policy`、`xhard4.stop_time_range`。
- 不传规格，走现场抽样（导出模式），再交给 `train_split_runner.py --identity-source formula --no-recovery`。
  - 起环境、跑 oracle、录 h5 的入口与 v7 生成相同（`train_split_worker.run_one`）。
  - 但没有走 v7 的「母布局 → 派生」链路：每局各自独立抽布局。
- seed = 14000000 + env_code × 100000 + episode × 100，episode 取 500～999，与 v7 的候选（< 100）不重叠。

### 9.1 规模与测速（P5 乘式）

| 轮次 | 内容 | 局数 | 成功 | 墙钟 | 单局秒（并发下） |
|---|---|---|---|---|---|
| 冒烟 | PickXtimes 8 次 × 1 | 1 | 1 | 59 s | 58 |
| 第一轮（广覆盖） | PickXtimes 5 配置 × 4 + SwingXtimes 3 × 4 + StopCube 3 × 3 | 41 | 41 | 221 s | 48～109 |
| 第二轮（PickXtimes 定向） | 最坏区域 5 × 3 + 边界 1 × 4（这 19 局区域写错，见 §11 第 3 条）+ 收紧区域 6／8／10 局 + 原区域 6／8 局 | 57 | 38 | 482 s | 122～143 |
| 第二轮补跑（与第二轮并行） | 近底座强化带 5 次数 × 3 + 收紧区域内侧 1 × 4 | 19 | 15 | 226 s | 144～225 |
| 第三轮（加量） | PickXtimes 收紧区域 10＋10＋4＋4＋8、原区域 10；SwingXtimes 6；StopCube 2 × 2；BinFill 10＋6 | 72 | 69 | 413 s | 47～170 |
| 第四轮（尾部） | PickXtimes 收紧区域 10 次 × 20 + 原区域 9 次 × 10 + BinFill 7 块 × 10 | 40 | 38 | 281 s | 137～212 |
| **合计** | | **230** | **202** | 各轮相加 28 分钟；因第二轮补跑、第三轮与第二轮重叠，实际墙钟 13:17～13:41 约 24 分钟 | |

- **失败构成**：230 局里失败 28 局。
  - 19 局是我把区域写错，开局即 `ValueError`：第二轮最坏区域 5 配置 × 3 = 15 局，加边界 1 配置 × 4 = 4 局。
  - 4 局 `SceneGenerationError`：PickXtimes 收窄区域内圆盘放不下 3 局（近底座强化带 2 局、内侧带 1 局，报错 Region crowded or constraints too tight），SwingXtimes 第一个目标采样失败 1 局。
  - 4 局 `environment reported failure`：BinFill 3 局、StopCube 1 局。
  - 1 局 `Fail to parameterize path`：近底座强化带。
- 每个 worker 约占 3.4 GB 内存。20～33 个进程并发时，机器负载 20～38，GPU 利用率很低（瓶颈在 CPU）。

### 9.2 PickXtimes（全部探针，按区域口径 × 抓取次数）

| 区域口径 | 抓取次数 | 尝试 | 成功 | 执行步均值 | max | 其中 d < 0.45 的局 | 失败 |
|---|---|---|---|---|---|---|---|
| 原区域（v7 现值） | 6 | 4 | 4 | 1081 | 1282 | 2 | — |
| 原区域 | 7（v7 gen1） | 20 | 20 | 1154 | 1304 | 5 | — |
| 原区域 | 8 | 21 | 21 | 1249 | 1533 | 2 | — |
| 原区域 | 9 | 22 | 22 | 1451 | **1973** | 4 | — |
| 原区域 | 10 | 8 | 8 | 1576 | **1919** | 1 | — |
| 近底座强化带（中心 (−0.25,0)、半宽 0.12；圆盘中心 x ∈ [−0.33,−0.17]，比原区域的 −0.26 更靠近底座，12 个成功局里 6 局落在原区域外，d = 0.29～0.36） | 6／7／8／9／10 | 3／3／3／3／3 | 3／2／2／3／2 | 1280／1372／1498／1840／1970 | 1301／1408／1614／2002／1990（原区域内可达的只有 7 次 1408、8 次 1614、9 次 2002） | 全部 | 场景 2、规划 1 |
| **收紧区域（方案 A）** | 6 | 10 | 10 | 971 | 1046 | 0 | — |
| 收紧区域 | 7 | 10 | 10 | 1101 | 1143 | 0 | — |
| 收紧区域 | 8 | 10 | 10 | 1232 | 1275 | 0 | — |
| 收紧区域 | 9 | 12 | 12 | 1367 | 1421 | 0 | — |
| 收紧区域 | 10 | 38 | 38 | 1493 | **1577** | 0 | — |
| 收紧区域内离底座最近的一侧（中心 (−0.07,0)、半宽 0.08） | 10 | 4 | 3 | 1509 | 1525 | 0 | 场景 1 |
| v7 gen1 里圆盘本来就落在方案 A 区域内的布局（6 个，跨档同布局） | 7／10／12／15 | 各 6 | 各 6 | — | 1182／**1591**／1863／2281 | 0 | — |

### 9.3 其余任务

| 配置 | 尝试 | 成功 | 执行步均值 | max | 失败 |
|---|---|---|---|---|---|
| SwingXtimes 4 轮（xhard1） | 4 | 4 | 596 | 618 | — |
| SwingXtimes 6 轮（xhard2） | 4 | 4 | 738 | 841 | — |
| SwingXtimes 8 轮（xhard3） | 10 | 9 | 928 | 983 | `SceneGenerationError` 1（First target sampling failed） |
| StopCube 6／7／8／9／10 次 | 3／2／3／2／3 | 3／1／3／2／3 | 367／424／489／552／608 | 371／424／492／555／611 | 7 次 1 局 `environment reported failure` |
| BinFill 6 块（xhard1，v7 配置） | 6 | 6 | 1202 | 1315 | — |
| BinFill 7 块（xhard2，v7 配置） | 20 | 17 | 1336 | 1434 | `environment reported failure` 3（15%） |

StopCube 的执行步 ≈ 60·次数 + 6，与公式 `steps_press = 60·k − 30` 加上按钮动作的长度吻合。

## 10. 待用户拍板

1. **PickXtimes 走哪个方案**：方案 A（6～10 次 + 收紧圆盘区域，推荐），还是方案 B（只改梯度，顶值 8 次）。
2. **取值映射**：已按 §0.2 第 8 条定为三任务扩至 xhard1～5、每档一个定值各 10 局，M-A 与 S1 作废，不再待决；保留编号。
3. **xhard0 去留**：xhard0 还留不留在 test-hard 里。留就是 1070 + 16 × 12 = 1262 局（三任务各 62，其余 92 或 32）；去掉就是 1070。
   - 留的话，13 个任务的局数与 v7 相同，三任务变为 62；下游写死的 1292／646／92／32 要按 1262 与逐任务数重算。
   - 去掉的话，builder 的 episode 编号整体平移，v7.5eval 只跑 xhard0 的那条链会受影响。
4. **MoveCube／InsertPeg 局数**：已按 §0.2 第 7 条定为 20 局（与 v7 同），不再待决；保留编号是为了不打乱其他小节的引用。
5. **统一上限的余量**：零余量取 1600，还是留余量（例如 1800）。
6. **各档布局关系**：各档共用前缀布局（v7 做法：每任务不同布局数 = 最大档局数，三任务为 10 个、两档任务 40 个），还是各档互不重叠（每任务 50 或 80 个不同布局）。

## 11. 教训与结论

1. **最大执行步看的是尾部，尾部由布局决定。**
   - PickXtimes 的尾部来自 d < 0.5 时的零空间漂移，是规划器的伪影，不是任务难度。
   - 定上限、选取值都要看 max 和最坏布局，不能看均值，也不能只看 3～8 局。本轮原区域抓 9 次，12 局最大 1676，22 局最大 1973。
2. **用「强制布局带」做探针能很快看清机理，但要核对它是否落在真实区域内。**
   - 把圆盘区域强制放到近底座带，每个次数 3 局，就看到了 6～10 次的 1301～2002。
   - 但这条带（圆盘中心 x ∈ [−0.33, −0.17]）比原区域（x ≥ −0.26）更靠近底座，一半成功局落在原区域根本抽不到的位置。所以它只是「强化带」的取值，不是原区域的上界；原区域内可达的只有 7 次 1408、8 次 1614、9 次 2002。
   - 下次做强制带探针，先按真实区域的边界截取，再谈上界。
3. **强制区域时，半宽必须大于圆盘半径 0.04。**
   - `spawn_random_target` 要求「中心 ± (半宽 − 半径)」非空，否则 100% 报 `ValueError`。
   - 本轮第二轮把半宽写成 0.02 和 0.01，19 局开局即报错，白做了。
   - 圆盘还要给按钮让位（按钮随机在 x ∈ [−0.25, −0.15]、y ∈ [−0.2, 0.2]）。区域收窄后会出现 `SceneGenerationError`：半宽 0.12 的近底座带 2/15，半宽 0.08 的内侧带 1/4。
4. **干扰块不影响执行步**（screw 不带点云避障）。所以干扰块可以只当视觉梯度用，与步数上限无关。
5. **「按档一个上限 × 1.25」会把单个任务的伪影放大到全档。** 改成「全集一个上限 = 实测最大向上取整到百」时，要同时改写 `cmd_step_headroom` 的判据，否则它按定义必然 FAIL。
6. **探针不必改代码。**
   - runner 的 `--sampling-config` 能直接传 decision 覆盖值，区间语义仍在。
   - `assert_native_decision` 会挡住结构不符的覆盖，所以覆盖只能改值，不能加键。
7. **测速与规模感**：
   - 本机 32 核下 20～33 个进程并发，单局约 0.8～3.7 分钟。PickXtimes 抓 10 次约 2～2.5 分钟一局。
   - 一轮 40～72 局约 4～8 分钟；230 局各轮相加 28 分钟，因为几轮有重叠，实际墙钟约 24 分钟。
   - 每个 worker 约 3.4 GB 内存，瓶颈在 CPU，GPU 几乎空闲。
   - PickXtimes 的 h5 每局约 700 MB，读完步数要立刻删。
8. **即使配置不变，生成失败也要留递补额度。**
   - BinFill 7 块失败 3/20（v7 6 块失败 6/28）。
   - StopCube 失败 1/13（`environment reported failure`，原因未查）。
   - SwingXtimes 失败 1/18（第一个目标采样失败）。
   - 本轮没测、但 v7 记录在案的：InsertPeg xhard4 失败 12/32（37.5%），MoveCube xhard4 失败 5/25（20%）。这两个任务在 v8 仍各交付 20 局（与 v7 同），递补预算仍要按这个比例留；BinFill 两档各 40 局，比 v7 每格 20 多一倍，递补也要翻倍。
9. **子代理分工有效。** 5 个只读子代理分别统计 v7 逐局步数、还原 v6 旧数据、梳理代码落点、推导步长模型、汇总历史教训。它们并行跑了 11～17 分钟，主会话同时做探针，两边互不阻塞。

   v6 的 h5 已删，只能从留档小文件还原，每个取值只有 0～5 局，参考价值有限。v6 的档级统计 `v6_gt_lengths.json` 在 165 局重叠样本上与 h5 口径的 demo／exec／total 逐局相等，可以用。

   历史留档里有一句「这份文件的 exec 按视频帧计、比 h5 大」，没有找到证据，本轮核对也不成立。
10. **StopCube 拆档的代价要如实列出。** 原建议 S1（单档分层）只改一个区间常量；用户 2026-10-01 决定拆成 xhard1～5 五档定值后，须动 `require_xhard4_only` 闸门、`XHARD4_ONLY`、白名单 L／G 表和 4 个测试（§5「结构改动」），这是用户知情后的选择，不再作为「不推荐」。

# 第二部分（技术细节，供 agent 追踪）

## 〇 前置声明与红线

- **R1**：`src/robomme/**` 是官方 `1fadc0ec` 原样，不改（P2）。本方案的改动全部在 `src/robomme_hard/` 与 `scripts/`、`tests/`。
- **R2**：xhard0 与原三档的 decision 不变；以 `assert_native_decision` 和 `UPSTREAM_GUARD=PASS` 为准。
- **R3**：录像器 `RecordWrapper.py` 冻结，零 diff（`git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py`）。
- **R4**：正式抽签和生成属于大规模 reset／rollout，开跑前必须按 P3 一次性报完整预算，计数按 P5 写乘式。本轮「本机随便跑」的授权**只覆盖探针**，不延伸到正式生成。
- **R5**：`scripts/` 顶层仍然恰好四个入口（P1）。新脚本放进 `scripts/injection-dev/`。
- **R6**：`identity_sha256`／`delivery_sha256` 的覆盖范围一旦改变（逐格局数、值配额进 header），要升 `schema`（例如 `hard-specs/4`），并重跑身份类闸门（`src/robomme_hard/README.md` ⑥ R3）。
- **R7**：对拍只在 A40@greatlakes 上生成（R11）。本轮 Ada 上的探针数字只用于定配置，不进 `PARITY_*`。
- **R8**：新增 xhard5 只落在 `src/robomme_hard/` 新值子树与 `scripts/`、`tests/`；官方 `src/robomme`、xhard0 与原三档不感知该档（`assert_native_decision` 剥掉 `xhard5` 子键后仍逐键相同）。

## 2.1 逐文件改动清单（配置值）

| 文件 | 锚点 | 现值 | 新值 | 方案 |
|---|---|---|---|---|
| `src/robomme_hard/robomme_env/PickXtimes.py` | `PickXtimes.config_xhard1..4` 的 `number_min`／`number_max`，新增 `config_xhard5`；`NEWVALUE_DECISION` 加 `"xhard5": _newvalue_decision(4)` | 7／10／12／15 | A：6／7／8／9／10；B：4／5／6／7／8 | A／B |
| 同上 | `XHARD_DECISION["goal_position_policy"]` | 中心 [−0.1, 0]、半宽 0.2 | 中心 [0.0, 0]、半宽 0.15 | 仅 A |
| 同上 | 注释「V7 定值（0928 方案 §3.2.2）」 | — | 改写为 v8 口径 | A／B |
| `src/robomme_hard/robomme_env/SwingXtimes.py` | `SwingXtimes.config_xhard1..4`，新增 `config_xhard5`；`NEWVALUE_DECISION` 加 `xhard5`（干扰 4） | 5／7／9／11 | 4／5／6／7／8 | 都改 |
| `src/robomme_hard/robomme_env/StopCube.py` | `_CONFIG_XHARD` 拆为五份（`configs["xhard1".."xhard5"]`）；`_native_decision` 暴露五个子键；`__init__` 去掉 `require_xhard4_only` | 仅 xhard4，`stop_time_range` `{low:6, high_exclusive:16}` | xhard1～5 各 `{low:k, high_exclusive:k+1}`，k = 6／7／8／9／10；`move_interval_choices` 仍 `[60]` | 都改 |
| `src/robomme_hard/robomme_env/utils/vqa_options.py` | `_options_stopcube` | 复刻 StopCube 公式 | 公式不变，但要按五档各自的 `stop_time` 定值核对；须跑 `test_vqa_checkpoints_match_env` 确认 | 都改 |
| `src/robomme_hard/robomme_env/utils/difficulty.py` | `NEWVALUE_DIFFICULTIES`、`newvalue_tier`、`require_xhard4_only` 的文案 | xhard1～4 | 加 `xhard5`；闸门只剩 InsertPeg、MoveCube 调用 | 都改 |
| `src/robomme_hard/env_record_wrapper/hard_specs.py` | `TIERS`、`BUILDER_TIERS`、`XHARD4_ONLY`、`EXPECTED_CELLS`、`validate_specs` 里的 `parent_tier == "xhard4"` | 四档；`XHARD4_ONLY` 含 StopCube | 五档；`XHARD4_ONLY = ("InsertPeg", "MoveCube")`；逐格表（§4.3）；母布局档按任务查表 | 都改 |
| 同上 | `TIER_MAX_STEPS` | 1300／1500／2400／2900／3800 | 1300／N／N／N／N／N（加 xhard5；N 建议 1600） | 都改 |
| `src/robomme_hard/env_metadata/test-hard/layout_whitelist.json` | `tasks.StopCube` | 无（`note` 写明 StopCube 不派生） | 新增 L＝路线端点与速度、G＝`stop_time`；`note` 同步 | 都改 |
| `src/robomme_hard/env_metadata/test-hard/xhard5/` | 新目录 `specs.jsonl` | 无 | 只含三任务各 10 局 | 都改 |
| `scripts/injection-dev/freeze_specs.py`、`derive_specs.py`、`_rollout.py` | 写死的 `"xhard4"`（`layout_rule.parent_tier`、`parent_header["difficulty"]`、`layout_parent.tier`、`seed_rule_for("xhard4", "v7")`、`_task_tiers`） | 母布局固定 xhard4 | 母布局 = 该任务最高交付档（三任务 xhard5，其余 xhard4） | 都改 |
| `scripts/evaluation_hard.py` | `TIER_MAX_STEPS[tier]` | 读包内常量 | 不改（P1「只差 4 处」照旧） | — |
| `tests/_shared/v7_tier_values.py` | `V7_TIER_VALUES`、`TIERS`、`_point`（遇区间抛 `NotFixedValue`） | v7 定值、四档 | 同步新值：三任务五档、StopCube 入表；`_point` 保持严格单值 | 都改 |
| `scripts/injection-dev/site/v6_tier_monotone.py` | `GATE_CHAIN`／`NEWVALUE_TIERS`、`_V7_NEW`、`XHARD4_EXTRA_TASKS`、`check_fixed`、`V7_VISUAL_COUNT` | 四档；Pick 7／10／12／15、Swing 5／7／9／11 | 加 xhard5；三任务五档定值；StopCube 移出「仅 xhard4」集合；`check_fixed` 保持单值 | 都改 |
| `tests/lightweight/test_v4_xhard_pickxtimes.py` | `V6_NUMBER_RANGE`、`test_v6_newvalue_config_values`、`test_xhard_config_values`、`test_decision_xhard_entries` | 钉 7／10／12／15、四档 | 同步新次数，加 xhard5 | 都改 |
| 同上 | 模块级 xhard decision 期望值字典与断言 `xhard["goal_position_policy"] == {"region_center": [-0.1, 0], "region_half_size": 0.2}` | 钉原圆盘区域 | 改为方案 A 的区域 | 仅 A |
| `tests/lightweight/test_v5_xhard_pickswing.py` | `test_pick_xhard_decision_v5`（无 slow／gpu 标记，核心短测会跑） | 钉原圆盘区域 | 改为方案 A 的区域 | 仅 A |
| `tests/lightweight/test_v4_xhard_swingxtimes.py` | `V6_NUMBER_RANGE`、`test_v6_newvalue_config_values` | 钉 5／7／9／11、四档 | 4／5／6／7／8，加 xhard5 | 都改 |
| `tests/lightweight/test_v4_xhard_stopcube.py` | `XHARD`、`test_xhard_segments_cover_stop_pass`（`range(6,16)`）、「xhard1～3 必报错」类断言 | 仅 xhard4，[6,15] | 五档各一个定值；原「拒绝 xhard1～3」的断言反转为「五档都接受、值正确」 | 都改 |
| `tests/lightweight/test_xhard0_native.py` | `test_TIER_MAX_STEPS五档且xhard0为1300` | 精确字典（五档） | 新字典六档（仍非递减），测试名同步 | 都改 |
| `tests/lightweight/test_sampling_config_split.py` | `test_v7_snapshot_matches_source` | v7 快照 | 换成 v8 快照或改名 | 都改 |
| `scripts/parity/hard_regression.py` | `cmd_step_headroom` | 90% + B4 ×1.25 | 「全集最大 ≤ N」，报全局最大值 | 都改 |
| `scripts/README.md`、`src/robomme_hard/README.md` | 第 1、3、4 节；② | v7 定值与上限 | 同步 | 都改 |

## 2.2 交付形态改动（合作者的表要求的，不属于数值配置）

**现行假设**：
- 全局只有一个 `--select 0..19` 和一个 `delivery_per_cell=20`。
- 55 格表 `EXPECTED_CELLS` = `XHARD4_ONLY` 推出来的格子。
- 四档必须交付同一组 20 个候选。
- builder 里写死 `!= 20`。

**要改的地方**：
1. `hard_specs.py`：把 `EXPECTED_CELLS` 换成逐格局数表 `{task: {tier: count}}`（取值即 §4.3，45 格）；header 的 `delivery_per_cell` 改成逐任务字典（升 schema）；`validate_specs` 按表核对。
2. `hard_builder.py::_test_hard_entries`：去掉写死的 20，改为查表；按 `hard_specs.TIERS`（含 xhard5）依次读 `env_metadata/test-hard/<tier>/specs.jsonl`，xhard5 文件里没有的任务跳过。xhard0 的去留看 §10 第 3 条，涉及 `_xhard0_entries`、`XHARD0_PER_TASK`、`BUILDER_TIERS`。
3. `_freeze.py::freeze` 与 `stratified_select`：加逐格配额；冻结的母布局档按任务取（三任务 xhard5，其余 xhard4）。不再需要按值分层（每档单值）。
4. `derive_specs.py::derive`：派生按「母布局档以下全部档」全派（三任务从 xhard5 派生 xhard1～4，其余从 xhard4 派生 xhard1～3；不交付的档也派生，便于沿用 `_check_layout_parent`），交付时只选要交付的档。母布局数 = 该任务各档局数的最大值（三任务 10、两档任务 40、三档任务 27、四档任务 20），所以 BinFill 等两档任务要抽 40 个 xhard4 母布局，虽然 xhard4 本身不交付。StopCube 新进派生链路，白名单 L／G 见 §5。
   - 另一条路是只派生要交付的档：省 reset，但要改 `layout_rule.parent_tier=="xhard4"` 的一串断言，不推荐。
5. `_rollout.py`：`_task_tiers`、`initial_pool`、`sync_drop_and_backfill`（按值配额递补）、`delivery_rows`、`V7_BACKFILL_CAP` 都改为逐格。判定行改名为 `V8_DELIVERY_SET`。
6. **下游写死的数**：三任务每任务 50（含 xhard0 62），其余与 v7 相同（92／32）；全集 1070（含 xhard0 1262）。
   - `hard_parity.py::SHAPES`（`13x3x20+16x1x20`）要改成逐格表（按档 404／404／122／110／30）。
   - `hard_regression.py` 的 `delivery_index`、`_replay_targets`、`cmd_eval_smoke`（92／32）：改为按任务查表（62／92／32）。
   - `export_eval_identities.py`（1292、646）、`site/v7_site_catalog.py`（1292）：按 1262 与逐任务数重算。
7. **每格局数取整**：
   - 三任务：50 ÷ 5 = 10，整除。
   - VideoUnmask／ButtonUnmask：四档各 20，不需要取整。
   - RouteStick／PatternLock：80 ÷ 3，取 27／27／26。
   - 取整按「低档多一局」，已按「取整等细节自己定」的长期指示决定。

## 2.3 闸门总表

| 闸门 | 命令 | 判定行 |
|---|---|---|
| 官方源码与借用闭包 | `uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` | `UPSTREAM_GUARD=PASS` |
| 录像器冻结 | `git diff --quiet HEAD -- src/robomme/env_record_wrapper/RecordWrapper.py` | 退出码 0 |
| 四入口 | `ls -1 scripts/*.py` | 恰好四个 |
| 核心短测 | `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q` | 无 failed |
| 白名单完备（StopCube 新进派生链路，必跑） | `derive_specs.py --whitelist-check` | `LAYOUT_WHITELIST_COMPLETE=PASS` |
| 共用布局、前缀几何、定值 | `hard_regression.py layout-shared`／`prefix-geometry`；`v6_tier_monotone.py --fixed` | `V8_LAYOUT_SHARED`／`V8_PREFIX_GEOMETRY`／`V8_TIER_FIXED`（由 V7_* 改名） |
| 交付、配额、区域、上限 | 见 §7 | `V8_DELIVERY_SET`／`V8_TIER_FIXED`／`V8_GOAL_CLEARANCE`／`V8_STEP_CAP` |
| 回注回放 | `hard_regression.py reset-replay` | `V8_RESET_REPLAY=PASS` |

## 2.4 runbook

### 2.4.1 复现本轮探针（只读仓库，产物落 `artifacts/v8-probe/`）

`jobs.json` 每行：

```json
{"task": "PickXtimes", "episode": 840, "seed": 14184000, "attempt": 0, "difficulty": "xhard4",
 "seed_rule": {"env_block": 100000, "episode_stride": 100, "formula": "offset + env_code*env_block + episode*100 + attempt", "offset": 14000000},
 "worker_dir": "artifacts/v8-probe/<轮>/<标签>/episodes/PickXtimes_episode_840"}
```

`sampling.json` 的取法：
- 形如 `{"tasks": {"PickXtimes": <cfg>}}`。
- `<cfg>` = v7 xhard4 header 的 `sampling_config["PickXtimes"]`，再改 decision 里的键，例如：

```json
"number_range": {"xhard4": [10, 10]},
"xhard4": {"goal_position_policy": {"region_center": [0.0, 0.0], "region_half_size": 0.15}}
```

运行：

```bash
ROBOMME_ENV_PACKAGE=robomme_hard OMP_NUM_THREADS=1 uv run --no-sync python scripts/parity/train_split_runner.py --src-root . --jobs-json jobs.json --results-json results.json --workers 10 --gpu 0 --sampling-config sampling.json --identity-source formula --no-recovery
```

每局跑完后读 `worker_dir/hdf5_files/*.h5`：执行步 = `timestep_*` 个数 − `info/is_video_demo` 为真的帧数。读完即删 h5 与 mp4。逐局结果在 `artifacts/v8-probe/{smoke,r1,r2,r2b,r3,r4}/results.jsonl`，PickXtimes 合并表在 `artifacts/v8-probe/px_rows.json`（含每局 d）。

### 2.4.2 正式生成（阶段 3，须先获批）

- **先打印预算**：`freeze_specs.py --dry-run`、`derive_specs.py --dry-run`。按 P5 写成乘式后一次性报给用户。
- **母布局抽签**：母布局档（三任务 xhard5，其余 xhard4）每任务候选数约为「最大档局数 × 1.3」，加上抽签拒绝率。
  - v7 的 xhard4 抽签接受率：VideoPlaceButton／VideoPlaceOrder 约 46%、VideoRepick 约 54%、ButtonUnmaskSwap 57%、PickHighlight 65%，其余 97～100%。
- **生成**：交付 rollout 共 3 任务 × 5 档 × 10 + 4 任务 × 4 档 × 20 + 7 任务 × 2 档 × 40 + 2 任务 × (27 + 27 + 26) + 2 任务 × 1 档 × 20 = 1070 局（逐格见 §4.3），另加失败递补。v7 与本轮的失败率：
  - InsertPeg 37.5%、MoveCube 20%、BinFill 15～21%。
  - StopCube、SwingXtimes 约 7%。
  - 其余多为 0～5%。
  - 预算要按这些比例逐任务留，并写成乘式。
- **seed 偏移**：建议新开一个 offset（例如 16e6），与 v7 的 14e6 和本轮探针（14e6 + episode ≥ 500）都不重叠。

## 2.5 风险登记

1. **方案 A 改变了圆盘位置分布**（离开近底座带，集中到桌面中部）。视觉上 PickXtimes 与 v7 不可直接对比；策略成功率会不会因此变化，本轮没测。
2. **零余量上限**：N = 1600，而方案 A 下 PickXtimes 抓 10 次的已知专家最大值是 1591（v7 cand 16）。
   - 专家侧只剩 9 步余量；同规格重生成的 RRT 噪声最大可达 116 帧，正式交付的最大值有可能超过 1600，那时 N 取 1700。
   - 策略在这一格几乎没有超出专家长度的余地（§6）。
3. **生成失败**：InsertPeg 37.5%、MoveCube 20%、BinFill 15～21%、StopCube／SwingXtimes 约 7%。v8 里 InsertPeg 和 MoveCube 仍各交付 20 局，与 v7 相同，但 v7 的 InsertPeg 已经用满每格 10 的递补上限、追加一轮才补齐，v8 的递补额度至少按 v7 实际消耗留。BinFill 两档各 40 局，比 v7 每格 20 多一倍，按 15～21% 失败率每档要留约 8～10 局递补。
4. **硬件差异**：本轮在 Ada 上测，正式生成在 A40 上。screw 规划是确定的，步数应一致；但 RRT 兜底（`ScrewThenRRT`）带随机性，可能有个别局不同。
5. **共享布局派生**：正式链路里，低档从母布局档（PickXtimes 为 xhard5）按 L 表照抄圆盘位置。方案 A 下母布局本身已在收紧区域内，低档跟着收紧，不会额外产生近底座布局。
6. **新增档位的结构改动面**：xhard5 牵动 `difficulty.py`、`hard_specs.TIERS`、builder、派生链路的母布局档、白名单、站点与约 27 个测试文件里钉四档的断言（§2.1）。这是 v6 以来第一次改档位枚举，核心短测与 `XHARD0_RESET_PARITY` 必须全绿才能进阶段 2。StopCube 新进派生链路，`reset-replay` 回注回放要覆盖它。

## 2.6 盲区诚实清单

- 方案 A 的抓 6～9 次，本轮各只有 10～12 局；抓 10 次本轮 38 局，加 v7 区域内 6 局共 44 局，已知最大 1591。
  - 正式交付里抓 10 次是 10 局，最大值预计在 1520～1600。没有逐局证明，也不能排除 RRT 噪声把个别局推过 1600。
- 「近底座强化带」有一半成功局落在原区域外，它的数字不是原区域的上界。
- 探针走的是现场抽样，不是 v7 的「母布局 → 派生」链路；也没在 A40 上跑。
- xhard5 档没有在任何链路上跑过：本轮探针是把取值从外部传给 xhard4 的 decision（§2.4.1），等价于「xhard5 = 10 次、干扰 4 块」，但档位枚举、builder、派生都没经过。
- 方案 B 的 4、5 次没测（参考 xhard0：4／5 次最大 929）；也没测 6／7／8 三值方案的局数分配。
- SwingXtimes 5、7 轮与 PickHighlight、VideoRepick、Unmask、Swap、Place、PatternLock、RouteStick 都直接沿用 v7 每格 20 局的数据，本轮没有重测。
- StopCube 每个值只有 1～3 局（执行步由时钟决定，波动 ≤ 10 步）；1/13 的生成失败是小样本。
- 没有测新配置下的策略成功率。「收紧区域不改变任务难度」只是推断。
- 230 局里有 19 局是我把区域写错（开局即 `ValueError`），不是环境问题；在 §9.1 单列，不计入任何失败率。

## 2.7 留档与 commit 纪律

- 本文件随 `12.277` 提交，只 `git add` 这一个文件。工作区里 `third_party/SimpleMemVLA` 的子模块内容改动（` m`）是他人在途工作，不动。
- 探针产物 `artifacts/v8-probe/` 不进 git。探针脚本在会话 scratchpad 不保留，方法按 §2.4.1 可以复现。
- 实施时每个阶段单独 commit，从 12.280 接续。commit body 按第 11 条写用户原话、计划、过程、意外、实测与下一步。正式生成的留档写到 `docs/validation/newtask-v8/`。
