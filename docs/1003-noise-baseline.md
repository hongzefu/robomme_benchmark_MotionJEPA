# 生成噪声基线：同一份代码重新生成会差多少（长期文档，2026-10-03 起）

本文件是 [`1003-noise-baseline-plan.md`](../1003-noise-baseline-plan.md) 的长期产物。实施中用户把范围收窄为**只测生成噪声**（原话见第一节）：同一批局用同一份代码、与交付相同的条件（GL A40、4 worker）重新生成两遍，量出「本来就会差多少」，冻结成判定线；以后改了代码，同一批局再生成一遍，超出这条线才算「改动改变了生成结果」。

> **当前状态：定稿（2026-10-03）。** 实测完成，判据由用户定为「翻转少于 10%」（第六节）。

- 判定工具：`scripts/parity/noise_gate.py`（逐局归类、算线冻结、回归判定）、`scripts/parity/gate_set.py`（固定检查集）、`scripts/parity/noise_run.py` 与 `noise_run_gl.sh`（GL 单遍运行包装）、`scripts/parity/hard_parity.py generate`（生成入口）。
- 运行留档：`docs/validation/noise-baseline-20261003/`。

## 一、范围与用户决定

用户 2026-10-03 原话（按时间）：

1. 「不要测试单Worker我永远都是多Wker生成的」
2. 「全面减少现在的规模把V9xhard0每个任务每个难度都只有3集」
3. 「此然后所有的事情都不要评3遍都只做两遍。」
4. 「去掉所有评估的噪声测试把生成测试完就收尾」
5. 「之后改代码也只测生成的噪声就可以。」
6. 「你测的这个噪声是在同一个机器上测的吗?我之后测和你现在的要对拍很有可能是不同机器你要测不同机器下同一局的噪声」
7. 「现在这样的有限翻转可以接受。就是只要翻转少于百分之10我觉得都然后你把这个写入docs」
8. 「就是并非逐字节相同的一定要是小于百分之10。其他的判断条件还有什么。」

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

**以后的判据**：见第六节（用户定的「翻转少于 10%」）。`noise_gate.py` 里按统计公式算线的 `freeze`／`check-gen` 本轮没有使用，不作为判据。

**两类比较的用途**：「同一份代码新跑两遍之间（跨节点）」量的是纯噪声；「新跑 vs 交付 h5／官方参照 h5」量的是「当前代码能否复现永久保留的参照」，混有跨时间、跨节点以及交付后代码改动的影响。以后回归直接拿新跑与永久保留的参照比（第六节），因此后一类就是回归时会看到的口径。

## 四、噪声从哪来、为什么单 worker 也不能保证一致（历史证据）

- **根源**：求解器先试 screw 3 次，全失败才回退 RRT*；RRT* 走第三方库 mplib，搜索预算是**墙钟 1 秒**（`mplib/planner.py` 默认 `planning_time=1`，本仓库未改），机器越忙 1 秒内采样越少，可能搜出另一条路径。只有回退到 RRT* 的局受影响。证据是间接的（[V3 诊断](validation/newtask-v3/20260921-worker-nondeterminism.md)、[多进程说明](maniskill-robomme-multiprocess.md)），没有做过「改成迭代数上限后分叉消失」的消融。
- **单 worker 的历史实测**：同一次运行内单 worker 144 局五路 720 对逐字节相同；同一局（PickHighlight 第 3 局）单 worker 换天、换节点出现过 647／641／648／652／653 帧五种结果；本机空闲与繁忙各自稳定但彼此不同；换 GPU 型号（RTX 6000 Ada 对 A40）108 对 0 对相同。所以单 worker 也只能在「同一次运行、同机同负载」下保证一致，不测单 worker 不损失判定能力。
- **已知大小**：V9 交付 800 局二次生成 782 局逐字节相同、17 局轨迹分叉、1 局第二次失败（2.25%），集中在 MoveCube、InsertPeg、BinFill（[生成可复现性](1003-generation-parity-reproducibility.md)）。

## 五、实测基线（2026-10-03，GL A40，驱动 595.71.05，锚点 `f8f76fba`）

两遍放在两台不同节点：V9 第 1 遍 gl1525（作业 63153922）、第 2 遍 gl1527（63153924）；xhard0 第 1 遍 gl1525（63153923）、第 2 遍 gl1527（63153925）。每遍一个 4 CPU 席位、`--workers 4`；V9 每遍约 36～38 分钟，xhard0 每遍约 10 分钟。生成结果：V9 第 1 遍 129/129 成功、第 2 遍 128/129；xhard0 两遍各 46/48。

| 比较 | n | 逐字节相同 | 走了另一条轨迹 | 生成失败 | 结构不同／原因不明 | 翻转（第六节口径） |
|---|---|---|---|---|---|---|
| V9 第 1 遍 vs 第 2 遍（跨节点） | 129 | 128 | 0 | 1（第 2 遍失败） | 0／0 | 1（0.8%） |
| 交付 h5 vs V9 第 1 遍 | 129 | 127 | 2 | 0 | 0／0 | 2（1.6%） |
| 交付 h5 vs V9 第 2 遍 | 129 | 127 | 1 | 1（新侧失败） | 0／0 | 2（1.6%） |
| xhard0 第 1 遍 vs 第 2 遍（跨节点） | 48 | 46 | 0 | 2（两侧都失败） | 0／0 | 0 |
| 官方参照 vs xhard0 第 1 遍 | 48 | 46 | 0 | 2（两侧都失败） | 0／0 | 0 |
| 官方参照 vs xhard0 第 2 遍 | 48 | 46 | 0 | 2（两侧都失败） | 0／0 | 0 |

判定行原文：

```text
GEN_PAIR=INFO ref=v9-a new=v9-b n=129 byte_equal=128 diverge=0 gen_fail=1 structural=0 unknown=0
GEN_PAIR=INFO ref=delivery.local.json new=v9-a n=129 byte_equal=127 diverge=2 gen_fail=0 structural=0 unknown=0
GEN_PAIR=INFO ref=delivery.local.json new=v9-b n=129 byte_equal=127 diverge=1 gen_fail=1 structural=0 unknown=0
GEN_PAIR=INFO ref=x0-a new=x0-b n=48 byte_equal=46 diverge=0 gen_fail=2 structural=0 unknown=0
GEN_PAIR=INFO ref=O-xhard0-bucket new=x0-a n=48 byte_equal=46 diverge=0 gen_fail=2 structural=0 unknown=0
GEN_PAIR=INFO ref=O-xhard0-bucket new=x0-b n=48 byte_equal=46 diverge=0 gen_fail=2 structural=0 unknown=0
```

逐局：

- **BinFill xhard1 候选 0（seed 16400000）**：V9 里唯一真正会抖的局，本就在交付集 18 局不可复现名单里（当年二次生成在第 1068 步分叉）。任务「两红一蓝三绿方块放进桶再按按钮」，交付 1430 步。
  - **第一次分叉在第 819 步**：两遍新跑一起偏离交付，子目标「pick up the third green cube」中途（`is_subgoal_boundary=False`）；第 818 步前三方逐字节相同，第 819 步动作最大差 2.8e-5、第 839 步 1.1e-2，最终第 1 遍 1427 步成功。两遍新跑在这里走的是**同一条新轨迹**（录像第 818～1060 帧逐像素相同）。
  - **第二次分叉在约第 1090 帧**（±20 帧，只有录像可比，视频编码会让差异提前露头）：第 2 遍与第 1 遍分开，两遍此时都在任务第 11 步「put it into the bin」，正把蓝方块放进桶（第 1095 帧两遍画面几乎相同）。
  - **第 2 遍的失败点**：之后一直卡在第 11 步——第 1200 帧第 1 遍已放下蓝方块、机械臂离开，第 2 遍机械臂仍压在桶上方、蓝方块在夹爪里；第 1 遍随后进入第 12 步按按钮、第 1426 帧「All tasks completed」；第 2 遍到最后一帧（1430）仍是第 11 步、`is_completed=False`，手腕相机里桶边桌面上多出一个红方块，生成器报 `DatasetGenerationError: environment reported failure`，只留下 800 字节占位 h5 与 `FAILED_` 录像。
  - 录像逐像素比较时交付对新跑最早在第 792 帧就有极小差异（平均差 0.04/255），早于 h5 的第 819 步，属于视频编码的前向参考效应；分叉位置以 h5 为准。
- **MoveCube xhard4 候选 2（seed 23400200）**：两遍新跑彼此逐字节相同，但都与交付 h5 从**第 376 步**起不同（全程 489 步），子目标「Hook the cube to the target with the peg」中途；差值第 376 步 4.9e-4 → 第 381 步 1.7e-2 → 第 396 步 0.21 → 第 426 步 0.56，两边都成功，新跑第 480 步完成（早 9 步）。同一份代码下稳定，只是与交付那次（V9 生成克隆 `b462e358`）结果不同；是当时节点负载还是 `b462e358` 之后的代码差异所致，现有数据分不清。
- 共同特征：分叉都从一个动作中途、几乎为零的差值开始逐步放大，与 RRT* 在 1 秒墙钟预算内搜出略有不同路径的机制吻合；生成日志未记录每段运动用的是 screw 还是 RRT，这一点是推断、未直接证实。
- **xhard0 VideoPlaceOrder 第 7、11 局（seed 610701、611101）**：官方原版就生成失败的已知局（v7 留档 `docs/validation/newtask-v7/README.md`：H、O 两侧 190/192 成功、`both_fail=2`），本轮两遍与官方三方都失败、失败产物逐字节相同，属确定性失败，不是噪声。
- 冒烟两局：xhard0 PickXtimes seed 510300 与官方参照、V9 PickXtimes xhard1 seed 16100000 与交付 h5 均逐字节相同。

结论：跨节点重复时，xhard0 能成功的 46 局零噪声；V9 129 局里只有 1 局会抖。与永久参照相比翻转最多 2/129（1.6%），远低于 10%。

## 六、判据：逐局 sha + 翻转重跑确认（2026-10-03 用户选定，2026-10-04 首次实用）

用户原话：「给我你现在的噪声闸门我用户订的是10不一致你能不能订一个更加准确的闸门。」四格定性表与预算经 AskUserQuestion 确认（计划 `1003-code-test-maintenance-todo.md` 对拍细则 3.2～3.4）。旧的「翻转少于 10%」判据原文保留在本节末尾，作为历史记录。

以后改了代码（只测生成噪声，第一节），按下面判：

1. **参照**：`scripts/configs/noise-ref-20261003.json`（由 `noise_gate.py gen-regress build-ref` 从本轮四遍 h5 重算生成，`NOISE_REF=PASS v9=stable:128,known_fail:0,jitter:1 xhard0=stable:46,known_fail:2,jitter:0 records_checked=708 mismatches=0 partial=0`）。每局一类期望：
   - **稳定局**（V9 128、xhard0 46）：新跑 sha ∈ 基线两遍 sha；
   - **确定性失败局**（xhard0 VideoPlaceOrder seed 610701、611101）：新跑也失败且失败产物 sha 相同；
   - **已知抖动局**（V9 BinFill xhard1 seed 16400000）：只报告，不判定。
2. **跑什么**：GL A40、每遍 `--workers 4`，用改后代码把 V9 `43 格 × 3 局 = 129`、xhard0 `16 任务 × 1 档 × 3 局 = 48` 各生成一遍（第七节命令），`generate --expect-ref <参照>` 边生成边判定（match 的局在节点上删掉、不回传；翻转局写 `flips.jsonl` 并打印 `EPISODE_FLIP`）。跑之前把局数与预算报给用户获准（P3）。
3. **首跑判定**：`noise_gate.py gen-regress check --ref <参照> --set {v9,xhard0} --new <首跑根> --out <jsonl> --rerun-identities-out <jsonl>`。无翻转直接 `GEN_REGRESS=PASS`；有翻转（≤10 局）输出 `GEN_REGRESS=NEED_RERUN` 与重跑清单（不足 4 局按同档优先补陪跑局，`filler=true`，陪跑只报告）；翻转 >10 局直接 FAIL 交用户。
4. **第二次跑与四格定性**：在**同一节点**上用改后代码与旧代码（噪声基线锚点 `f8f76fba`）各跑一次重跑清单，再 `gen-regress check … --rerun-new <根> --rerun-old <根>`：

   | 改后代码第二次 | 旧代码这一次 | 定性 |
   |---|---|---|
   | 回到基线 | 不看 | 噪声 |
   | 与第一次相同、不同于基线 | 回到基线 | 回归（代码改坏了） |
   | 与第一次相同、不同于基线 | 也不同于基线 | 环境变了，交用户 |
   | 与第一次也不同 | — | 每次都不同，交用户 |

5. **通过条件**（两集合各自）：回归、环境变了、每次都不同都为 0；确认为噪声的翻转 V9 ≤ 2、xhard0 ≤ 1；结构不同与原因不明为 0（一局即 FAIL）。
6. **跑法前提**（不满足判 INVALID、重跑）：GL A40、`--workers 4`、每局都有结果、启动记录含 host（缺 host 判 INVALID，12.407）、第二次跑与首跑同节点、`RUN_FRESH=PASS`、`BUDGET=PASS`。
7. 不通过时把逐局明细（`<out>.episodes.md`；本机 `--local-ref-root artifacts/noise-baseline/gen` 可细分 structural／diverge／gen_fail 并给分叉步）交用户裁决，不改参照、不改判据。第三次跑默认不跑。

**首次实用（维护计划第三步，2026-10-04）**：xhard0 `GEN_REGRESS=PASS n=48 match=48`；V9 `GEN_REGRESS=FAIL … match=127 jitter=1 flip=1 regression=0 env_changed=1`——唯一翻转局 MoveCube xhard4 seed 23400200 在 gl1525 上改后与旧代码逐字节相同、与基线不同（第 376 步分叉），待用户裁决（`docs/1002-pending-decisions.md` D7；留档 `docs/validation/maintenance-regress-20261004/README.md`）。

**限制**：只在 GL A40 上成立；PASS 只说明这 177 局没有检出超出噪声的变化，不证明全部 800 局逐字节等价。

### 历史判据（2026-10-03，已被上文取代）


用户原话：「现在这样的有限翻转可以接受。就是只要翻转少于百分之10我觉得都然后你把这个写入docs」。

以后改了代码（只测生成噪声，第一节），按下面判：

1. **参照**：V9 用永久保留的交付 h5（`artifacts/newtask-v9/delivery/delivery.local.json` 所指 h5），xhard0 用官方参照（`artifacts/newtask-v7/parity/h5/O-xhard0-bucket/`）。本轮新跑的 h5 不作参照。
2. **跑什么**：在 GL A40 上用改后的代码把 V9 129 局、xhard0 48 局各生成一遍（4 worker，与本轮相同的 `hard_parity.py generate` 命令，见第七节）。跑之前把局数与预算报给用户，获准后才跑（P3、计划裁决 4）。
3. **比**：`noise_gate.py gen-compare --ref <参照> --new <新跑输出根> --identities <冻结清单>`，读 `GEN_PAIR` 行与逐局 jsonl。
4. **翻转的定义**（用户原话第 8 条）：与参照相比**文件不是逐字节相同**（sha256 不同）的局，即 `GEN_PAIR` 的 n − byte_equal 再扣除「两侧失败产物 sha 相同」的局（`gen_fail` 里 `fail_side=both` 且两侧文件 sha 相同；目前只有 xhard0 VideoPlaceOrder seed 610701、611101：本轮两遍与官方参照三方都是同一份 800 字节文件，sha256 前缀 `26c4d449632ea072`，按文件 sha 本就逐字节相同）。走了另一条轨迹、一侧生成失败都算翻转。
5. **通过条件**：
   - **非逐字节相同的局少于 n 的 10%**：V9 129 局 → 不超过 12 局；xhard0 48 局 → 不超过 4 局；
   - **结构不同必须为 0**：字段缺失、dtype／shape 变化、第 0 帧不同、`setup` 组不同——说明代码改变了数据格式或初始场景，通常波及全部局，不是噪声；
   - **原因不明必须为 0**：文件打不开、缺文件、sha 与记录不符——是数据损坏或搬运错误。
6. **跑法前提**（不满足即本遍无效、重跑，不判通过或失败）：GL A40、`--workers 4`、每局都有结果、`noise_run_gl.sh` 的 `RUN_FRESH=PASS`（输出根全新）与 `BUDGET=PASS`。
7. **只报告、不判定**：参照成功而新跑失败的局数单列；翻转按任务列出个数（某一任务集中出现翻转时由用户目视裁决）。
8. 不通过时把逐局明细交用户裁决，不自行改判据。

本轮基线下的值：V9 翻转 2/129（上限 12），xhard0 翻转 0/48（上限 4）。

**限制**：只在 GL A40 上成立（换 GPU 型号整文件不再一致，历史上 RTX 6000 Ada 对 A40 是 0/108）；驱动版本以来源报告为准，换驱动后先在同一批局上复跑确认。PASS 只说明翻转在可接受范围内，不证明行为完全不变。

## 七、回归命令（以本轮为模板）

```bash
# GL 登录节点 tmux 内（席位 = 1 A40／4 CPU／48G 占位 job），每遍一个席位
srun --jobid=<占位作业> --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared \
  bash <克隆>/scripts/parity/noise_run_gl.sh --pass <遍名> --kind gen --out-root <NFS>/gen/<遍名> \
    --log <NFS>/logs/<遍名>.log --provenance-out <NFS>/prov/<遍名>.json \
    --budget-ledger <NFS>/budget-ledger.jsonl --budget-caps <NFS>/budget-caps.json \
    --attempts 129 --resets 387 --retries 0 -- \
  <克隆>/.venv/bin/python <克隆>/scripts/parity/hard_parity.py generate --side H2 --tier v9 \
    --manifest delivery.local.json --identities v9-129-generate.jsonl --specs-root <V9 规格根> \
    --src-root <克隆> --workers 4 --gpu 0 --out /tmp/<遍名> --stage <NFS>/gen/<遍名> \
    --expect-ref <克隆>/scripts/configs/noise-ref-20261003.json   # 边生成边判定（改后代码；旧代码 f8f76fba 无此参数）
# xhard0：另设 ROBOMME_HARD_XHARD0_IN_TEST_HARD=1，--side H --tier xhard0 --manifest scripts/configs/xhard0/xhard0_manifest.json --identities x0-48-generate.jsonl（不给 --specs-root）
# 身份清单：uv run --no-sync python scripts/parity/gate_set.py export --set {v9,xhard0} --kind generate --out <文件>
# 收尾（辅助步骤不带 --gpu_cmode=shared）：srun --jobid=<占位作业> --overlap --ntasks=1 <克隆>/.venv/bin/python <克隆>/scripts/parity/noise_run.py ship --src /tmp/<遍名> --stage <NFS>/gen/<遍名> --finalize
# 首跑判定（读 NFS 暂存的 identities.jsonl，秒级）：
#   uv run --no-sync python scripts/parity/noise_gate.py gen-regress check --ref scripts/configs/noise-ref-20261003.json \
#     --set v9 --new <NFS>/gen/<首跑> --out <jsonl> --rerun-identities-out <重跑清单>
# NEED_RERUN 时同一席位串行：改后代码与旧代码各跑一遍重跑清单（--identities <重跑清单>），再
#   gen-regress check … --rerun-new <NFS>/gen/<改后第二次> --rerun-old <NFS>/gen/<旧代码>
# 只回传翻转局：uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/gen --dest artifacts/<目录> \
#     --segments <首跑,改后第二次,旧代码> --identities <flips.jsonl>（空清单只拉报告）
# 本机细分（分叉步）：gen-regress check … --local-ref-root artifacts/noise-baseline/gen
# 与 V9 交付 h5 的附带比较（只报告）：noise_gate.py gen-compare --ref <参照> --new <根> --identities scripts/configs/gate-set-v9-129.json --out <jsonl>
```

本轮的 GL 侧脚本（`launch.sh`、`pass.sh`）与逐字命令留档在 `docs/validation/noise-baseline-20261003/README.md`；按新闸门的首次实用（含改后／旧代码两份检出的单遍脚本、串行链、第二次跑）留档在 `docs/validation/maintenance-regress-20261004/README.md`。

## 八、实施记录

| 项 | 内容 |
|---|---|
| 代码 | 12.358 G9 清单（后被 12.363 缩为 129／48）、12.359 GL 运行包装、12.361 比较器与闸门、12.363 缩规模与 xhard0 生成子集；每次合并前只读审查 PASS、合并后核心短测只剩 [`1002-pending-decisions.md`](1002-pending-decisions.md) C1 登记的 6 个长期失败 |
| GL 执行副本 | 新建独立克隆 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-noise`（只建 bench venv）；不动 V9 评估克隆 `robomme_benchmark-v9two`（资源清理方案闸门 G8 要求其 HEAD 前后不变） |
| 占位席 | `nb-hold-1～4` = 63153922～63153925（1 A40／4 CPU／48G／48 h，shared） |
| 预算 | 上限 2 遍 × (129 + 48) = 354 + 冒烟 2 + 基础设施重试 20 = 376 条轨迹、reset 1128（每条 3）；实际 356 条（四遍 354 + 冒烟 2），基础设施重试 0 |
| v7.5 依赖 | 资源清理方案保留整个 `artifacts/v7.5eval`（只删其 `venvs/`）；本轮用到的 xhard0 48 局已冻结进 git，GL 侧不用 `v7.5eval/venvs` |
