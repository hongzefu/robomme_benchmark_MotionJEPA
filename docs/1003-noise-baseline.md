# 生成噪声基线：同一份代码重新生成会差多少（长期文档，2026-10-03 起）

本文件是 [`1003-noise-baseline-plan.md`](../1003-noise-baseline-plan.md) 的长期产物。实施中用户把范围收窄为**只测生成噪声**（原话见第一节）：同一批局用同一份代码、与交付相同的条件（GL A40、4 worker）重新生成两遍，量出「本来就会差多少」，冻结成判定线；以后改了代码，同一批局再生成一遍，超出这条线才算「改动改变了生成结果」。

> **当前状态：初稿。** 代码已合入（12.358～12.363），GL 实测进行中。第五节「实测基线」与第六节「冻结的线」在实测完成后补写；在那之前本文件里的数字只有历史已知值，不能当作判定线使用。

- 判定工具：`scripts/parity/noise_gate.py`（逐局归类、算线冻结、回归判定）、`scripts/parity/gate_set.py`（固定检查集）、`scripts/parity/noise_run.py` 与 `noise_run_gl.sh`（GL 单遍运行包装）、`scripts/parity/hard_parity.py generate`（生成入口）。
- 冻结文件（实测后生成）：`scripts/configs/noise-baseline.json`。
- 运行留档：`docs/validation/noise-baseline-20261003/`。

## 一、范围与用户决定

用户 2026-10-03 原话（按时间）：

1. 「不要测试单Worker我永远都是多Wker生成的」
2. 「全面减少现在的规模把V9xhard0每个任务每个难度都只有3集」
3. 「此然后所有的事情都不要评3遍都只做两遍。」
4. 「去掉所有评估的噪声测试把生成测试完就收尾」
5. 「之后改代码也只测生成的噪声就可以。」

据此，原计划的环境九层摘要、SimpleMemVLA／MME 闭环评估噪声、单 worker 生成全部取消；以后改代码的回归也只测生成噪声。计划第一部分其余关于评估的判据（含裁决 1「净损失 5 局判改坏」）随之不再使用；`noise_gate.py` 里的评估闸门代码保留但不在基线中冻结。

## 二、固定检查集

| 名称 | 内容 | 规则 | 冻结文件与判定行 |
|---|---|---|---|
| V9 | V9 交付集 43 格 × 3 局 = 129 | 每个（任务, 难度档）交付格取 candidate 升序最小的 3 局（`gate_set.PER_CELL = 3`） | `scripts/configs/gate-set-v9-129.json`，`GATE_SET=PASS cells=43 per_cell=3 total=129 in_delivery=129 sha=5a869f0a69be` |
| xhard0 | 16 任务 × 1 档 × 3 局 = 48 | 沿用 v7.5 小样本 `identities-small48.json`（源 sha256 `a45c20d9…`） | `scripts/configs/gate-set-xhard0-48.json`，`GATE_SET_XHARD0=PASS tasks=16 per_task=3 total=48 sha=2dda3ecf5203` |

V9 的 43 格：StopCube、SwingXtimes 各 xhard1～5；ButtonUnmask、VideoUnmask 各 xhard1～4；PatternLock、PickXtimes、RouteStick 各 xhard1～3；BinFill、ButtonUnmaskSwap、PickHighlight、VideoPlaceButton、VideoPlaceOrder、VideoRepick、VideoUnmaskSwap 各 xhard1～2；InsertPeg、MoveCube 只有 xhard4。

## 三、怎么测、怎么判

**测法**：两批局各生成两遍，2 遍 × (129 + 48) = 354 条轨迹，GL A40、每遍一个占位席（4 CPU）、`--workers 4`。V9 走 `hard_parity.py generate --side H2 --tier v9 --identities <129 局清单> --specs-root <V9 规格根>`；xhard0 走 `hard_parity.py generate --side H --tier xhard0 --identities <48 局清单>`（需 `ROBOMME_HARD_XHARD0_IN_TEST_HARD=1`；`--identities` 对 xhard0 的支持为 12.363 新增，只筛作业，传给运行器的清单仍是完整 192 行）。每遍经 `noise_run_gl.sh`：输出根必须不存在、预算账本累计核上限、环境指纹（commit、驱动、GPU 型号）写来源报告。

**每局归入互斥五类**（`noise_gate.py gen-compare`）：

| 类别 | 条件 |
|---|---|
| byte_equal | 文件 sha256 相同 |
| diverge | 两侧成功；非时间步内容全同；逐帧键集合、dtype、shape 全同（白名单字段除外）；第 0 帧全数据集全同；首次分叉步 ≥ 1 |
| gen_fail | 求解器失败（`DatasetGenerationError`、`PlannerExhausted`），标明哪侧失败 |
| structural | `setup` 不同、任一帧结构不同、第 0 帧不同、白名单字段出现允许集合外签名 |
| unknown | 打不开、缺文件、sha 与记录不符、内容全同但字节不同、其他失败类型 |

**多态字段白名单**：`action/waypoint_action` 在录像器没有待执行路点时写 float32 (7,) 的 NaN 占位、有路点时写 float64 (7,) 实值，分叉后各帧占位状态随轨迹变化。只读扫描 23 个真实 h5 全部时间步，多签名字段只有这一个（float32 276 帧全 NaN、float64 11728 帧），故以 `noise_gate.POLYMORPHIC_KEYS` 显式放行这一个键的这两种签名；其余字段须每帧签名恒定且两侧相同。

**以后的判据**（`GEN_NOISE_GATE`，`noise_gate.py check-gen`）：改码后两批局各重新生成一遍，与基线参照比：structural 与 unknown 必须为 0；diverge + gen_fail ≤ 冻结的线；gen_fail ≤ 冻结的线。分任务的个数只用于定位。线 = 合并比例的单侧 95% Clopper–Pearson 上界 p_U 下 Binomial(n, p_U) 的 99% 分位数，且不小于基线观测最大值（纯 Python 精确计算）。**每次回归运行须先把项目与预算报给用户，获准后才跑**（计划裁决 4）。

**线只用「同一份代码的新跑两遍之间」的个数算**：交付集 800 局中 720 局是 V8 当年用 V8 代码生成，「新跑 vs 交付 h5」混有 V8→HEAD 的代码差异，只作「当前代码能否复现交付集」的核对单独报告，不参与算线。

## 四、噪声从哪来、为什么单 worker 也不能保证一致（历史证据）

- **根源**：求解器先试 screw 3 次，全失败才回退 RRT*；RRT* 走第三方库 mplib，搜索预算是**墙钟 1 秒**（`mplib/planner.py` 默认 `planning_time=1`，本仓库未改），机器越忙 1 秒内采样越少，可能搜出另一条路径。只有回退到 RRT* 的局受影响。证据是间接的（[V3 诊断](validation/newtask-v3/20260921-worker-nondeterminism.md)、[多进程说明](maniskill-robomme-multiprocess.md)），没有做过「改成迭代数上限后分叉消失」的消融。
- **单 worker 的历史实测**：同一次运行内单 worker 144 局五路 720 对逐字节相同；同一局（PickHighlight 第 3 局）单 worker 换天、换节点出现过 647／641／648／652／653 帧五种结果；本机空闲与繁忙各自稳定但彼此不同；换 GPU 型号（RTX 6000 Ada 对 A40）108 对 0 对相同。所以单 worker 也只能在「同一次运行、同机同负载」下保证一致，不测单 worker 不损失判定能力。
- **已知大小**：V9 交付 800 局二次生成 782 局逐字节相同、17 局轨迹分叉、1 局第二次失败（2.25%），集中在 MoveCube、InsertPeg、BinFill（[生成可复现性](1003-generation-parity-reproducibility.md)）。

## 五、实测基线（待补）

## 六、冻结的线（待补）

## 七、实施记录

| 项 | 内容 |
|---|---|
| 代码 | 12.358 G9 清单（后被 12.363 缩为 129／48）、12.359 GL 运行包装、12.361 比较器与闸门、12.363 缩规模与 xhard0 生成子集；每次合并前只读审查 PASS、合并后核心短测只剩 [`1002-pending-decisions.md`](1002-pending-decisions.md) C1 登记的 6 个长期失败 |
| GL 执行副本 | 新建独立克隆 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-noise`（只建 bench venv）；不动 V9 评估克隆 `robomme_benchmark-v9two`（资源清理方案闸门 G8 要求其 HEAD 前后不变） |
| 占位席 | `nb-hold-1～4` = 63153922～63153925（1 A40／4 CPU／48G／48 h，shared） |
| 预算 | 2 遍 × (129 + 48) = 354 + 冒烟 2 + 基础设施重试 20 = 376 条轨迹，reset 上限 1128（每条 3） |
| v7.5 依赖 | 资源清理方案保留整个 `artifacts/v7.5eval`（只删其 `venvs/`）；本轮用到的 xhard0 48 局已冻结进 git，GL 侧不用 `v7.5eval/venvs` |
