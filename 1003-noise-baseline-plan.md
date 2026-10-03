# 噪声基线与改码回归闸门计划（2026-10-03）

> **本文件的地位**：这是「把生成两次的噪声、评估重复的噪声到底有多大定下来，并写成以后可调阅的文档」这件事的唯一计划。只规划、不实施；第二部分的预算表与子代理分配表须经用户批准后才执行，批准前不改代码、不提交作业、不启动任何生成或评估。
>
> **锚点**：工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，规划依据 `6a8c1368`（12.350）。提交编号沿用 `12.<小版本>`。现有 `third_party/SimpleMemVLA` 的在途改动不动。
>
> **用户原话（2026-10-03，语音转写，按时间顺序）**：
> 1. 「之前我用户没有再去管生成和对拍时候的一致性或者说一致性检验现在看来还是不行就是我可能后面还会修改代码我需要保证修改后和修改前生成和valuation的时候噪声和以前是一样的在原来的噪声范围内」
> 2. 「写一个根目录文件确定下来与的这个噪声到底有多大就是生成两次然后EVUation的噪声有多大」
> 3. 「有一个根目录计划计划。」
> 4. 「就是我要写一个计划来确定下来这些东西然后把它写在文档里以后调阅」
>
> **与其他文件的关系**：生成侧已有事实见 [`docs/1003-generation-parity-reproducibility.md`](docs/1003-generation-parity-reproducibility.md)（数据集已冻结、现行容差不改）；评估侧已有事实见 `docs/validation/v7.5eval/`；未定事项 A1～A5 见 [`docs/1002-pending-decisions.md`](docs/1002-pending-decisions.md)。根目录 [`1003-oracle-subgoal-groundsg-eval-plan.md`](1003-oracle-subgoal-groundsg-eval-plan.md) 管的是两组 GroundSG 新模型的接入与「原 hard 入口完全一致」，本计划管的是现有两模型（SimpleMemVLA、MME-VLA FrameSamp + Modulation）与生成链路的噪声基线，两者互不替代；新模型接入后按本计划的同一流程补测，不在本计划预算内。

# 第一部分（给人看）

## 一、总览

**一句话方案**：把「代码不改、同一批局重复跑」本来会差多少量出来（噪声基线），定成冻结的整数线，写进一份长期文档；以后每次改代码后再跑一遍，差异不超过这条线算没改坏。

**一共五项噪声**。其中三项已经测清、不用再跑；两项有缺口，这次要实测：

| 编号 | 噪声 | 比的是什么 | 现在已知 | 这次要不要实测 |
|---|---|---|---|---|
| 1 | 环境 reset 噪声 | 同一个 seed 重置两次，场景和画面是否相同 | 0（逐字节相同） | 不用，已测清 |
| 2 | 生成噪声 | 同一局生成两次，两份 h5 是否相同 | 800 局里 18 局不同（2.25%），成败翻转 1 局 | **要**：补「是否固定落在某些局」「单 worker 是否为 0」 |
| 3 | 策略开环噪声 | 同一份输入喂给模型两次，输出动作是否相同 | SimpleMemVLA 为 0；MME 跨进程最大差 0.0096 | 不用，已测清 |
| 4 | SimpleMemVLA 闭环评估噪声 | 同一批局评估两次，每局成败与步数是否相同 | xhard0 的 192 局 0 翻转；V9 的局没测过 | **要**：补 V9 的局 |
| 5 | MME 闭环评估噪声 | 同上 | xhard0 的 192 局每次翻 7～19 局；V9 的局没测过 | **要**：补 V9 的局 |

**已定死口径**：

1. 五项噪声分开测、分开判，不混用（第二节）。
2. 噪声为 0 的项（1、3 的 SimpleMemVLA、4）：改码后要求完全相同，有差即改坏，不设线。
3. 噪声不为 0 的项（2、5）：只数「有几局不同」，不看差多大；线在基线阶段一次算成整数并冻结（第三节）。
4. 测基线和以后每次回归都用同一批固定的局：从 V9 交付集每任务取 12 局，16 任务 × 12 局 = 192，记 **G9**；xhard0 的 16 任务 × 1 档 × 12 局 = 192 记 **D0**。
5. 噪声只在固定条件下成立：GL A40、驱动 595.71.05；换 GPU 型号不可比（RTX 与 A40 之间 44/48 局 reset 就不同）。
6. 交付的 800 局 h5、现行容差文件 `scripts/configs/hard-parity-tolerances.json`、`hard_parity.py` 判定逻辑、`src/robomme/` 全部不动。

## 二、五项噪声逐项说明

每项按同一顺序写：比什么 → 具体看哪些字段 → 现在的判法 → 已知多大 → 这次怎么测 → 以后的判据。

### 噪声 1：环境 reset

- **比什么**：同一个 seed 和规格，把环境重置两次，看摆出来的场景是否相同。不涉及机械臂执行，也不涉及模型。
- **看哪些字段**：场景状态（每个物体的位姿）、演示帧、reset 后的观测；每一层算 sha256 逐层比。入口 `scripts/parity/hard_regression.py::cmd_xhard0_reset_parity`（xhard0，对官方）与 `cmd_reset_replay`（V9 每格 1 局）。
- **现在的判法**：`det_diff=0` 才 PASS，即一层都不能有差。唯一放行的是「物体名字不同但场景逐位相同」，单列为 `name_only`。
- **已知多大**：0。`XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0`（V8、V9 各两次）；同型号换卡、换机器、同卡复跑 48/48 全等（`docs/validation/v7.5eval/env-parity.md`）。
- **这次怎么测**：不测。
- **以后的判据**：改码后 `det_diff=0`，不设线。

### 噪声 2：生成（同一局生成两次）

- **比什么**：同一个 seed 和规格，让求解器把整局重新生成一遍，比两份 h5。第一份是交付品，第二份只用于对照。
- **看哪些字段**（`scripts/parity/hard_parity.py::pair_metrics`，逐帧比两份 h5 的共同帧）：

  | 字段 | 含义 |
  |---|---|
  | 文件 sha256 | 两份 h5 是否逐字节相同 |
  | `setup` | seed、难度、任务目标、多选项、相机内参是否相同 |
  | 文件结构 | 数据集名、dtype、shape 是否相同 |
  | 成败 | 两次是否都生成成功 |
  | `action/joint_action` | 每帧关节动作的最大绝对差（弧度） |
  | `obs/joint_state`、`obs/gripper_state` | 每帧关节状态、夹爪状态的最大绝对差 |
  | `obs/front_rgb`、`obs/wrist_rgb` | 两个相机每帧的平均像素差 |
  | 帧数 | 两份的帧数差 |
  | 首次分叉步 | 第一个出现任何差异的帧号 |

- **现在的判法**：动作差 > 0.0413、状态差 > 0.0411、图像差 > 1.0、帧数差 > 5 任一成立记「超容差」；超容差局里，`setup`、结构、成败都相同且首次分叉步 > 0 的记 noise，否则记 fail。整批 PASS 需要：没有 fail、超容差局不超过 5%、没有第二次生成失败的局。
- **现在判法的问题**：动作／状态／图像这三条幅度线实际不起作用。三批共 2250 局里只出现两种局——逐字节相同，或者从某一步起走了另一条轨迹（动作差全部在 0.06 以上，多数 2.0 以上）；「有差但在幅度线内」的局一局都没有。所以看 action 差多大没有区分力，真正有信息的是「有几局不同」和「成败有没有翻」。
- **已知多大**：V9 交付 16 任务 × 50 局 = 800：不同 18 局（2.25%），其中成败翻转 1 局；V8 1070 局 1.12%；V7 1100 局 1.27%。集中在 MoveCube 8.9%、InsertPeg 8.6%、BinFill 4.4%，另有 8 个任务为 0。首次分叉步最早是第 63 步（`docs/1003-generation-parity-reproducibility.md`）。
- **缺口**：每批只重复过一次，不知道分叉是固定落在某些局、还是每次换一批；已有诊断指向规划器的墙钟时间预算在多 worker 抢 CPU 时结果不同（`docs/validation/newtask-v3/20260921-worker-nondeterminism.md`），但没验证过「单 worker 就没有噪声」。
- **这次怎么测**：在 G9 上再生成四遍，每遍都与交付 h5 比、遍与遍之间也比。
  - 4 worker 两遍（与交付时条件相同）：2 遍 × 16 任务 × 12 局 = 384。回答「不同的局数每次波动多大、是否总是同几局」。
  - 1 worker 两遍：2 遍 × 16 任务 × 12 局 = 384。回答「单 worker 是否逐字节可复现」。
- **以后的判据**（`GEN_NOISE_GATE`）：改码后把 G9 重新生成一遍，与交付 h5 比，三条同时满足才 PASS：
  1. 结构硬线：每一局的 `setup`、文件结构相同，且首次分叉步 > 0（第 0 步就不同说明初始场景变了，不是噪声）。
  2. 不逐字节相同的局数 ≤ 冻结的线（整体一条，分任务各一条）。
  3. 成败翻转局数 ≤ 冻结的线。

  动作差、状态差、图像差照旧算出来写进报告，只作参考，不参与判定。若实测单 worker 为 0，再加一条零噪声判据：单 worker 重跑与冻结的 sha256 清单全等。

### 噪声 3：策略开环（同一份输入重放）

- **比什么**：把一局录下来的观测原样喂给模型两次，比输出的动作。不跑仿真，所以没有误差累积。
- **看哪些字段**：模型输入字节是否全等、输出动作逐位是否相同、最大绝对差。入口 `scripts/eval-official/policy_replay.py`。
- **现在的判法**：只报告（`POLICY_REPLAY=INFO bitwise=k/n max_abs=…`）。
- **已知多大**：SimpleMemVLA 为 0（四种条件 16 次比较全部逐位）。MME 同一个 server 内为 0；每次重启 server 后从第 0 次推理起就有差，最大 0.0034～0.0096（`docs/validation/v7.5eval/policy-replay.md`）。这就是噪声 5 的源头。
- **这次怎么测**：不测。
- **以后的判据**：动到评估接口或打包时，要求模型输入字节全等；SimpleMemVLA 的动作逐位相同；MME 的动作最大差 ≤ 0.0096（已观测最大值）。

### 噪声 4：SimpleMemVLA 闭环评估

- **比什么**：同一批局完整评估两次（模型看画面出动作、仿真执行、循环到结束），比每一局的结果。
- **看哪些字段**：每局终态（成功／失败／超时）与执行步数。入口 `scripts/eval-official/compare.py::cmd_eval_parity`，输出成功→失败局数 `s2f`、失败→成功局数 `f2s`、步数相同局数 `steps_equal`。
- **现在的判法**：只报告，没有判定。
- **已知多大**：D0（xhard0 192 局）上为 0：官方历史、重跑一、重跑二、正式跑法四份结果的终态和步数 192/192 全同（141 局成功）。
- **缺口**：V9 的局只评过一遍（178/800），没有重复；V9 的局更长（步数上限 1600），不能直接假设也是 0。
- **这次怎么测**：G9 上重跑两遍：1 模型 × 2 遍 × 16 任务 × 12 局 = 384。连同已有的一遍共三份，两两比。
- **以后的判据**（`EVAL_NOISE_GATE`）：若 G9 实测也是 0，则改码后要求 G9 与 D0 上每局终态和步数完全相同；若实测有翻转，则改用噪声 5 的数个数判法。

### 噪声 5：MME 闭环评估

- **比什么、看哪些字段**：同噪声 4。
- **现在的判法**：只报告。V7.5 用过一条「相对标准」（翻转数不超过官方三对最大值，且成功率差落在官方三对的最小最大值之间），结果因为三对的成功率差区间只有 1 局宽，正常波动也被判出界（未定事项 A3）。
- **已知多大**：D0 上官方三份结果两两比，翻转 7、16、19 局（成功→失败／失败→成功为 4／3、9／7、10／9），成功数 50、49、48；正式跑法 51；V8 两入口 18 局状态不同。即每次约 4%～10% 的局翻转，但总成功数只差 1～3 局。
- **缺口**：V9 的局只评过一遍（39/800），没有重复。
- **这次怎么测**：G9 上重跑两遍：1 模型 × 2 遍 × 16 任务 × 12 局 = 384。连同已有的一遍共三份，两两比。D0 直接用已有的官方三对，不新跑。
- **以后的判据**（`EVAL_NOISE_GATE`）：改码后在 G9 与 D0 上各评一遍，与基线那一遍比，两条同时满足才 PASS：
  1. 翻转局数（两个方向之和）≤ 冻结的线。
  2. 两个方向的翻转大致对称：McNemar 配对检验 p ≥ 0.05（成功→失败远多于失败→成功，说明是系统性变差，不是噪声）。

  不再使用「成功率差落在基线最小最大值之间」这一条。

## 三、线怎么算

只用于噪声 2 和噪声 5（以及噪声 4 若实测不为 0）。

设基线里有 m 对重复比较，每对 n 局，第 i 对有 x_i 局不同。

1. 合并比例 p̂ = Σx_i ÷ (m·n)。
2. 取它的单侧 95% Clopper–Pearson 上界 p_U（比例本身估得不准，往大处取）。
3. 线 K_max = 二项分布 Binomial(n, p_U) 的 99% 分位数（单次抽样还会波动，再留余量），且不小于已观测到的最大 x_i。

线算出来是一个整数，写进 `scripts/configs/noise-baseline.json` 冻结；以后回归只做「个数 ≤ 线」的整数比较。同一份代码重跑被误判为改坏的概率约 1%；真正的改坏（某任务成片分叉、成败成片翻转）会让个数远超这条线。

示意（最终以脚本输出为准）：噪声 5 在 D0 上按 7／16／19 计，p̂ = 42 ÷ 576 = 7.3%，192 局的线约 28 局；噪声 2 按交付集 18 ÷ 800 计，192 局的整体线约 13 局。

## 四、这次实测的规模

| 对应噪声 | 内容 | 乘式 | 轨迹数 |
|---|---|---|---|
| 2 | 生成，4 worker | 2 遍 × 16 任务 × 12 局 | 384 |
| 2 | 生成，1 worker | 2 遍 × 16 任务 × 12 局 | 384 |
| 4 | SimpleMemVLA 评估 G9 | 1 模型 × 2 遍 × 16 任务 × 12 局 | 384 |
| 5 | MME 评估 G9 | 1 模型 × 2 遍 × 16 任务 × 12 局 | 384 |
| — | 冒烟 | 生成 1 局 + 评估 2 模型 × 1 局 | 3 |
| — | 基础设施重试上限 | 生成 20 + 评估 20 | 40 |
| | **合计上限** | | **1579** |

噪声 1、3 和 D0 上的噪声 4、5 不新跑，直接取已有留档。固定条件：GL A40、驱动 595.71.05；生成每席 4 CPU、`OMP_NUM_THREADS=1`；评估每席串行、MME server `--seed=7`、确定性标志关、步数上限 1600（xhard0 为 1300）。

## 五、以后改代码怎么用

| 改动范围 | 必查的噪声项 | 每次预算 |
|---|---|---|
| 任何代码改动 | 核心短测 + `UPSTREAM_GUARD` | 0 |
| 动到环境、规格、builder、评估入口 | 噪声 1：xhard0 16 × 1 × 12 = 192 次 reset + V9 43 格 × 1 = 43 次 reset，要求全等 | 235 次 reset |
| 动到生成链路（`scripts/injection-dev/`、`src/robomme_hard/` 的求解与录制） | 噪声 2：G9 重生成一遍 | 16 × 12 × 1 = 192 条轨迹 |
| 动到评估接口、客户端、打包 | 噪声 3（0 局）+ 噪声 4、5：两模型在 G9 与 D0 上各一遍 | 2 模型 × (192 + 192) = 768 条轨迹 |

这些回归运行都超过 P3 的 50 条阈值，是否给一次性长期授权列在第七节待拍板项。

## 六、验收

| 判定行 | 查什么 | 怎么查 | 过了说明什么 |
|---|---|---|---|
| `GATE_SET=PASS tasks=16 per_task=12 total=192 in_delivery=192 sha=<…>` | G9 确定、可重算、全部属于交付集 | `noise_gate.py gate-set --check` 重算清单与冻结文件逐字节比 | 以后每次比的是同一批局 |
| `GEN_BASELINE=INFO pairs=<m> n=192 byte_diff=<x_1,…> flip=<…> single_worker_byte_equal=<a>/192 same_identity_overlap=<…>` | 噪声 2 的个数、是否固定在某些局、单 worker 是否为 0 | `noise_gate.py baseline-gen` 读各遍 `hard_parity.py compare` 的逐局结果 | 噪声 2 的缺口补上 |
| `EVAL_BASELINE=INFO policy=<p> set=<G9\|D0> pairs=<m> flips=<x_1,…> success=<…>` | 噪声 4、5 的翻转个数 | `noise_gate.py baseline-eval` 读逐局终态 | 噪声 4、5 的缺口补上 |
| `NOISE_BASELINE=PASS thresholds=<k> file_sha=<…>` | 冻结文件自洽 | 按第三节公式重算与文件值比；顶层 sha256 = 去掉该键后的规范 JSON 哈希 | 线不会被悄悄改动 |
| `GATE_SELFTEST=PASS same_code=PASS injected=FAIL` | 闸门本身有效 | 基线里一对「同代码重跑」喂闸门须 PASS；测试夹具人为加翻转须 FAIL | 闸门不误报也不漏报 |

两行 `*_BASELINE` 只报告、不判 PASS／FAIL——噪声多大是测出来的事实，不预设。

## 七、实施步骤与待拍板项

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 用现有留档写出基线文档 `docs/1003-noise-baseline.md` 初稿（五项噪声的全部已知值），0 算力 | `git diff --check` |
| 1 | 写 G9 清单与闸门脚本、测试（子代理） | `GATE_SET=PASS`；定向测试通过 |
| 2 | 冒烟：生成 1 局、两模型评估各 1 局 | 三局均取得终态 |
| 3 | GL 实测：生成四遍、评估两模型各两遍 | 每遍 192 局齐全 |
| 4 | 算线、冻结文件、补全基线文档、提交 | `GEN_BASELINE`、`EVAL_BASELINE`、`NOISE_BASELINE=PASS`、`GATE_SELFTEST=PASS` |

**交付物**：基线文档 `docs/1003-noise-baseline.md`（以后调阅）；冻结的线 `scripts/configs/noise-baseline.json`；G9 清单 `scripts/configs/gate-set-v9-192.json` 与闸门脚本 `scripts/parity/noise_gate.py`。

**需要用户拍板的三项**（批准本计划即视为同意下列推荐值）：

1. **实测预算**：上限 1579 条轨迹、3158 次 reset，GL 4 个占位 job（各 1 A40／4 CPU／48 G／48 h）。
2. **评估只测现有两模型**（SimpleMemVLA、MME-VLA FrameSamp + Modulation）；两组 GroundSG 新模型接入后另按同流程补测。
3. **以后回归运行的长期授权**：第五节表里的每次预算（生成 192、评估 768、reset 235）是否一次性授权，以后改码后直接跑、不再逐次申请。

## 八、子代理分工与合并（简述）

代码只有两块，互不碰对方文件：一块是 G9 清单的生成脚本、冻结清单和它的测试；另一块是闸门判定脚本（算基线、算线、做回归判定）和它的测试。两块各交一个 worktree 子代理，先合清单、再合判定脚本；每次合并前由一个只读审查子代理核对改动范围与计划条目，合并后主会话跑核心短测。基线文档、GL 实跑、冻结线由主会话自己做，因为它们依赖 GPU 与 `artifacts/`。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1：不改 `src/robomme/`、不改交付 h5 与规格、不改 `scripts/configs/hard-parity-tolerances.json`、不改 `hard_parity.py` 的判定逻辑（只读调用其 `compare`）。
- R2：`scripts/` 顶层不新增文件（P1）；新脚本落 `scripts/parity/`，冻结配置落 `scripts/configs/`。
- R3：预算以 §四 为唯一上限；成功、失败、重试、冒烟全部计入；超出即停并一次性补充申请（P3）。
- R4：`*_BASELINE` 只出 INFO；阈值公式写死在脚本，冻结后不因某次回归没过而改阈值，裁决交用户（第 22 条）。
- R5：不为挑结果重试；重试只用于 0 步基础设施失败，记原因与次数。
- R6：补测期间冻结 HEAD（阶段 3 起跑到全部身份齐全之间不提交）；GL 执行副本用独立克隆并记 commit。

## 一、逐文件改动清单

| 文件 | 性质 | 内容 |
|---|---|---|
| `scripts/parity/noise_gate.py` | 新增 | 子命令：`gate-set`（`--build`／`--check`，从包内 V9 规格按任务、档位比例、候选号升序取每任务 12 局）、`baseline-gen`、`baseline-eval`、`freeze`（按第一部分第三节「线怎么算」的公式算阈值写 JSON，顶层 `sha256`）、`check-gen`（输出 `GEN_NOISE_GATE=PASS\|FAIL n= byte_diff=/K_max flip=/F_max structural= per_task_over=`）、`check-eval`（输出 `EVAL_NOISE_GATE=PASS\|FAIL policy= set= flips=/T_max s2f= f2s= mcnemar_p= exact_required=`）、`selftest` |
| `scripts/configs/gate-set-v9-192.json` | 新增 | 192 个身份（task、tier、候选号、seed、spec_sha256）与清单 sha256 |
| `scripts/configs/noise-baseline.json` | 新增（阶段 4） | 固定条件、各层基线原始个数、阈值整数、公式说明、来源 commit 与留档路径、顶层 sha256 |
| `tests/lightweight/test_noise_gate.py` | 新增 | 纯 CPU：阈值公式的手算对照、Clopper–Pearson 与二项分位的边界（x=0、x=n）、McNemar 精确检验、结构硬线、sha 防改、同代码对 PASS／注入翻转 FAIL |
| `tests/lightweight/test_gate_set.py` | 新增 | 清单确定性（两次构建字节相同）、16 × 12、全部属于交付集、档位比例 |
| `docs/1003-noise-baseline.md` | 新增 | 长期基线文档（阶段 0 初稿、阶段 4 补全） |
| `scripts/parity/README.md` | 修改 | 表格加 `noise_gate.py` 一行 |
| `docs/validation/noise-baseline-20261003/` | 新增 | `launch.md`、`result.md`、`records/`（各遍 compare 摘要与逐局 jsonl、评估逐局终态、判定行原文） |

现有能力（直接复用）：`hard_parity.py generate／compare`、`hard_regression.py xhard0-reset-parity／reset-replay`、`scripts/eval-official/compare.py eval-parity`、`run_v8_gl.sh` 与 `v8_manifest.py` 的评估编排。拟新增：上表。待验证：`generate_h5.py`／`hard_parity.py generate` 能否直接吃 G9 子集清单与 `--workers 1`；V8／V9 正式评估的逐局终态文件位置（预期在 `artifacts/v8-evaluation/`、`artifacts/v9-evaluation/`）——两项在阶段 1 开头只读核实，核实不通过时把具体缺口并入一次补充说明。

## 二、子代理分配表

| 编号 | 目标 | 可写文件集合 | 禁触 | 接口契约与依赖 | 合并顺序 | 验收（worktree 内，CPU） | 资源 |
|---|---|---|---|---|---|---|---|
| S1 | 闸门身份集 | `scripts/configs/gate-set-v9-192.json`、`tests/lightweight/test_gate_set.py`、`scripts/parity/gate_set.py`（纯函数库，供 S2 的 `gate-set` 子命令导入） | `src/robomme/`、其余全部 | 导出 `build_gate_set() -> list[dict]`、`load_gate_set(path)`；只读包内 V9 规格 | 1 | `UV_PROJECT_ENVIRONMENT=<主 .venv> PYTHONPATH=<wt>/src uv run --no-sync python -m pytest tests/lightweight/test_gate_set.py -q`；判定行 `GATE_SET=PASS` | 无 GPU |
| S2 | 闸门判定脚本 | `scripts/parity/noise_gate.py`、`tests/lightweight/test_noise_gate.py` | 同上；不改 `gate_set.py` | 依赖 S1 的两个函数签名（分配表即契约，S1 合入后派发）；输入为 `hard_parity.py compare` 的逐局 jsonl 与评估逐局终态 jsonl | 2 | 同上取法跑 `test_noise_gate.py` | 无 GPU |
| M | 文档、README、GL 实跑、阈值冻结、留档 | 其余全部 | — | 主会话自做：依赖 GPU、`artifacts/` 与集群 | 3 | 见 §三 | GL 4 席 |

共享文件归属：`scripts/parity/README.md` 归主会话。S2 依赖 S1，串行派发。模型：写入型 opus，审查 sonnet。

## 三、闸门总表

| 时点 | 判定行 |
|---|---|
| 阶段 1 每次合并前 | `PRE_MERGE_REVIEW=PASS …` |
| 阶段 1 每次合并后 | `POST_MERGE_REVIEW=PASS …`（核心短测 `timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q`；`test_scripts_do_not_import_tests.py`；`ls -1 scripts/*.py` 仍四个入口；`UPSTREAM_GUARD=PASS`） |
| 阶段 3 起跑前 | `GATE_SET=PASS`；GL 克隆 HEAD 与本机一致；A40 与驱动断言；`ASSETS` 资产锁（沿用 `artifacts/v7.5eval/assets-lock.json`，过滤规则与 `hash_assets.sh` 一致） |
| 阶段 3 每遍结束 | 身份齐全 192/192、0 条未解决 error |
| 阶段 4 | `GEN_BASELINE`、`EVAL_BASELINE`、`NOISE_BASELINE=PASS`、`GATE_SELFTEST=PASS` |

## 四、预算表（P3 一次性授权，P5 乘式）

| 项 | 乘式 | 轨迹上限 |
|---|---|---|
| 生成，4 worker | 2 遍 × 16 任务 × 12 局 | 384 |
| 生成，1 worker | 2 遍 × 16 任务 × 12 局 | 384 |
| 评估，G9 | 2 模型 × 2 遍 × 16 任务 × 12 局 | 768 |
| 冒烟 | 生成 1 任务 × 1 局 + 评估 2 模型 × 1 任务 × 1 局 | 3 |
| 基础设施重试 | 生成 20 + 评估 20 | 40 |
| **合计** | | **1579 条轨迹；reset 上限按每条 2 次计 3158** |

xhard0（D0）基线：0 条新轨迹，全部取自 V7.5 留档。停止条件：任一遍 0 步失败超过 20 局即停该遍查因；合计触上限即停。预计耗时：生成 4 worker 每遍约 1～2 h、1 worker 每遍约 4～6 h；评估四遍分 4 席约 3 h。占位 job 4 个，开工先提交，JobID 记入 `launch.md`，跑完按清单逐个 `scancel`。

## 五、runbook

1. 阶段 0：主会话写 `docs/1003-noise-baseline.md` 初稿，提交。
2. 阶段 1：派发前四项核对（`worktree.baseRef`、主检出 clean、`check-ignore`、`git worktree list`）→ S1 → 审查 → `--no-ff` 合并 → 短测 → push → S2 同流程。
3. 阶段 2：本机或 GL 冒烟三局。
4. 阶段 3：GL 独立克隆到锚点 commit；席 1、2 各跑一遍 4 worker 生成（`OMP_NUM_THREADS=1`、`--workers 4 --gpu 0`、`--gpu_cmode=shared`），随后席 1、2 各跑一遍 1 worker 生成；席 3、4 跑评估四遍（每席串行，SimpleMemVLA 与 MME 分席）。全部在登录节点 tmux 内 `srun --jobid=<hold> --overlap --exact --ntasks=1 --gpu_cmode=shared`，会话前缀 `nb-`，每份日志挂一个监听，过滤词含 `EXIT_CODE=`、`NO RECORD`、`svulkan2`、`EXCLUSIVE`、`RRT`、`Traceback`。逐局产物先落节点 `/tmp`、核 sha 后搬回 `/data`，NFS 不留大文件。
5. 每遍生成后在本机跑 `hard_parity.py compare`（对交付 H，及遍与遍之间），逐局 jsonl 归档到 `docs/validation/noise-baseline-20261003/records/`。
6. 阶段 4：`noise_gate.py baseline-gen／baseline-eval／freeze／selftest`；补全基线文档；提交并 push；`scancel` 四席；删除对拍用 h5 与 worktree，只留摘要与逐局 jsonl。

## 六、风险登记

| # | 风险 | 处置 |
|---|---|---|
| 1 | G9 每任务只有 12 局，分任务阈值很松（基线为 0 的任务阈值约 2） | 以整体个数为主判据，分任务只作定位；需要更严时扩大身份集另行申请 |
| 2 | 基线的多对比较共用同几遍结果，并不独立，阈值的统计含义是近似 | 阈值另取「不小于已观测最大值」兜底；文档写明 |
| 3 | 生成噪声随节点负载变化（墙钟预算），不同节点、不同时段的比例可能不同 | 记录每遍节点名与同节点并发；条件写进基线文件；回归须同条件 |
| 4 | SimpleMemVLA 在 V9 test-hard 上未必零翻转（执行步上限 1600、任务更长） | 实测为准；非零则该模型在 G9 上改用个数阈值 |
| 5 | V8／V9 首遍评估与补测两遍相隔数日，节点组成不同 | 与 V7.5 官方噪声带同样处理：节点效应计入噪声带并写明 |
| 6 | GL 带 `shared` 的步骤结束后整卡被重置为独占 | 同席只让干活步骤带 `shared`，辅助 `srun` 不带 |

## 七、盲区诚实清单

- 生成分叉的根因只有 V3 时期的诊断（RRT 墙钟预算），V8／V9 的 32 个分叉局没有逐局归因；本计划只量大小，不做根因诊断。
- 噪声基线只对 A40 成立；本机 RTX 6000 Ada 上的回归不能与它比。
- MME 的翻转来自 server 每次启动的编译／自动调优，本计划不消除它（确定性标志减速约五成，已按规则关）。
- 闸门只能发现「个数明显超出噪声」的改坏；被噪声淹没的小幅退化（例如个别局成败变化）检不出，这类改动靠噪声 1、噪声 3 的逐字节判据把关。
- 两组 GroundSG 新模型、xhard1～5 的全量 800 局重复评估不在本计划内。

## 八、留档与 commit 纪律

- 留档目录 `docs/validation/noise-baseline-20261003/`：`launch.md` 在阶段 3 起跑时写（commit、席位、tmux 会话清单、完整命令、env 覆盖项），`result.md` 在阶段 4 写；`records/` 只放 git 还原不出来的逐局结果与判定行。
- 子代理提交前缀 `sub/S1: `、`sub/S2: `；合并提交与主会话提交按 `12.<小版本> <中文描述>`，body 按第 11 条六项；每次提交后立即 push。
- 局数一律写乘式（P5）；判定行内联原文。
