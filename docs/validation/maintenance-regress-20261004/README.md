# 维护后生成对拍（第三步，2026-10-04）

计划：`1003-code-test-maintenance-todo.md` 第一部分第五节、第二部分「对拍细则 3.2～3.4」「预算」「runbook」。

## ① 一句话结论与判定速览

清理与测试重构后的代码在 GL A40 上重新生成同一批局，与噪声基线逐局比 sha：**xhard0 全部一致（PASS）；V9 没有代码回归，但有 1 局被闸门定性为「环境变了」，按闸门判 FAIL，交用户裁决。** 用户 2026-10-04 裁决「登记为环境敏感局。」后，该局写入参照 `jitter_observed`，重判 **V9 `GEN_REGRESS=PASS`**（见⑪末尾）。

| 集合 | 局数 | 判定行 |
|---|---|---|
| xhard0 | 16 任务 × 1 档 × 3 局 = 48 | `GEN_REGRESS=PASS set=xhard0 n=48 match=48 jitter=0 flip=0 structural=0 unknown=0 missing=0 invalid=0` |
| V9 | 43 格 × 3 局 = 129 | `GEN_REGRESS=FAIL set=v9 n=129 match=127 jitter=1 flip=1 structural=0 unknown=0 missing=0 invalid=0 rerun_rows=4 filler=3 noise=0 regression=0 env_changed=1 unstable=0 noise_max=2` |

V9 的唯一翻转局：**MoveCube xhard4 seed 23400200**。

| 跑次 | 代码 | 节点 | sha256 前缀 | 成败 |
|---|---|---|---|---|
| 噪声基线 a／b 两遍 | `f8f76fba` | gl1525／gl1527 | 与参照一致（两遍彼此相同） | 成功 |
| 首跑 rg-v9r | 改后 `a43110c2` | gl1525 | `6b85dd3239e0` | 成功 |
| 第二次 rg-v9-new2 | 改后 `a43110c2` | gl1525 | `6b85dd3239e0` | 成功 |
| 第二次 rg-v9-old2 | 旧代码 `f8f76fba` | gl1525 | `6b85dd3239e0` | 成功 |

本机细分（`--local-ref-root artifacts/noise-baseline/gen`）：类别 `diverge`（非结构差异），与基线 a 遍自**第 376 步**起不同，所在子目标「Hook the cube to the target with the peg」。**同一节点上新旧两份代码逐字节相同**，所以差异不来自本次代码改动；闸门四格表把这种情形定义为「环境变了」并要求交用户（计划细则 3.2／3.3），本次不改参照、不改判据。

已知抖动局 BinFill xhard1 seed 16400000：首跑 `jitter_info`，只报告。3 个陪跑局（StopCube xhard4 seed 22200000／22200100／22200200）在改后与旧代码两次中都与基线一致，说明节点当时负载正常。

## ② 版本与代码状态

- 改后代码：NFS 检出 `robomme_benchmark-maint`，首跑先钉 `062e646d`（12.398），因生成器竞态崩溃（见⑩）修复后前移到 `a43110c2`（12.403），rg-v9r／rg-x0／rg-v9-new2 均在 `a43110c2` 上跑；解释器借 `robomme_benchmark-noise/.venv`，`PYTHONPATH=<maint>/src`、`--src-root <maint>`，每遍起跑打印 `IMPORT_CHECK=PASS …/robomme_benchmark-maint/src/robomme_hard/__init__.py`。`uv.lock` 与 `f8f76fba` 零 diff，`pyproject.toml` 只差 pytest 配置段。
- 旧代码：`robomme_benchmark-noise` 原样 `f8f76fba`（工作区干净）。
- 参照：`scripts/configs/noise-ref-20261003.json`（12.387，`NOISE_REF=PASS … partial=0 sha=5119e2ac71ca`）。

## ③ 启动与配置还原

GL 侧脚本（逐字归档于 `records/*.sh.txt`）：`launch.sh <JobID> <new|old> <遍名> <V9|X0> <identities>` → 占位作业内 `srun --overlap --exact --cpus-per-task=4 --gpu_cmode=shared bash pass.sh …` → 各自代码里的 `noise_run_gl.sh`（preflight：`RUN_FRESH`、`BUDGET`；finish；`EXIT_CODE=`）→ `hard_parity.py generate --tier v9|xhard0 --workers 4 --gpu 0`（改后代码带 `--expect-ref`，Mover 边生成边判定：match 删节点文件不回传，flip 写 `flips.jsonl` 并打印 `EPISODE_FLIP`）→ `noise_run.py ship --finalize`。串行链：`chain_first2.sh`（rg-v9r → rg-x0）、`chain_rerun.sh`（rg-v9-new2 → rg-v9-old2）。判定在本机：`noise_gate.py gen-regress check`（读 NFS 暂存的 `identities.jsonl`）。

## ④ 数据与划分口径

身份集与噪声基线相同：`scripts/configs/gate-set-v9-129.json`（V9 43 格 × 3 局 = 129）、`gate-set-xhard0-48.json`（xhard0 16 任务 × 1 档 × 3 局 = 48）；冒烟各 1 局（V9 PickXtimes xhard1 seed 16100000、xhard0 PickXtimes seed 510300）。

## ⑤ 关键参数

每遍 4 worker（与基线同负载，闸门前提）；重试 0；每条 reset 上限 3。

## ⑥ 硬件与耗时

全部在 gl1525（job 63167696，1 A40／4 CPU／48G，`NVIDIA A40, 595.71.05` 与基线驱动相同）。冒烟各约 1 分钟；rg-v9r 约 35 分钟（02:06～02:41）；rg-x0 约 9 分钟；第二次跑两遍各约 1 分钟。第二席 63167697 一直排队（`AssocGrpGRES`／`AssocGrpCpuLimit`），全部改为单席串行。

## ⑦ 过程（生成）

| 遍 | 判定 | 说明 |
|---|---|---|
| smk-v9 | `match` | 冒烟 |
| smk-x0 | `match` | 冒烟 |
| rg-v9 | `GENERATE=FAIL recorded=84 runner_exit=1` | 竞态崩溃（见⑩），已完成 84 局：match 83、jitter_info 1，作补充证据，不入闸门 |
| rg-v9r | `GENERATE=PASS recorded=129 success=128` | 首跑正式遍 |
| rg-x0 | `GENERATE=PASS recorded=48 success=46` | 2 局为已知确定性失败局（VideoPlaceOrder seed 610701、611101），失败产物与基线逐字节相同（match） |
| rg-v9-new2 | `GENERATE=PASS recorded=4 success=4` | 翻转局 + 3 陪跑 |
| rg-v9-old2 | `GENERATE=PASS recorded=4 success=4` | 同上，旧代码 |

## ⑧ 评估

不适用（只测生成）。

## ⑨ 用户决策记录

1. 「参考最新的noise baseline做好对拍的设置你不再需要生成两次了而是和之前的生成的结果做对拍。」「你需要在改之后重新生成一次。还是这些episode然后和之前生成的做对比」
2. 「给我你现在的噪声闸门我用户订的是10不一致你能不能订一个更加准确的闸门。」（逐局 sha + 翻转重跑确认，四格定性表 2026-10-03 确认）
3. 「现在每次都要回传Turbo的Data能否不用回传?直接现场计算计算完了有问题的再回传。」「是否可以每次一边生成一边计算SHA256。」
4. AskUserQuestion（2026-10-04）：GL 两席「现在就提交」；对拍预案「噪声局写回参照、驱动不同照跑、FAIL 后修完重跑一次、PASS 后删新跑产物」全部预批。
5. 「不要再问我了尽可能一口气做到底做完了明天早上再来问我按照美国多亩时间来计算。」

## ⑩ 计划外事件与处置

- **生成器竞态崩溃**：rg-v9 第 84 局 `_rollout.run_batch` 回读 h5 时报 `FileNotFoundError`——Mover 在「列出 h5 之后、打开之前」按 match 删了文件（原 `_ship` 复制后删本地也有同样窗口，基线 354 局未触发）。12.403 修复（回读时文件已被搬走按「已不在」处理，不碰仿真与 h5 字节），12.409 加贯通用例与撤回保护的反向用例。修复后整遍重跑 rg-v9r。
- **预算**：rg-v9 在 preflight 登记 129 条后崩溃，按用户预批「FAIL 后修完按同预算再跑一轮」启用第二份额度，合计上限 398 条、reset 1194、重试 0（`records/budget-caps.json`）。登记合计 316 条（`records/budget-ledger.jsonl`）：冒烟 2 + rg-v9 129（实际约 85）+ rg-v9r 129 + rg-x0 48 + 第二次跑 4 + 4；实际生成约 272 条轨迹，均在第二份额度内。
- **V9 判 FAIL（env_changed=1）**：按计划不改判据、不改参照，交用户。未做第三次跑（计划「第三次默认不跑」）。

## ⑪ 结论与下一步（待用户裁决）

- 能下的结论：本次清理与测试重构**没有造成可检出的生成回归**——177 局中 175 局与噪声基线逐字节相同（V9 127 + xhard0 48），1 局为已知抖动局，剩下 1 局在同一节点上新旧代码产物逐字节相同（证明差异与代码改动无关）。
- 闸门字面结论：`GEN_REGRESS=FAIL`（V9，`env_changed=1`），需要用户裁决，可选：(a) 接受为环境差异、把该局登记为环境敏感局（写进参照的 `jitter_observed` 需用户确认）；(b) 换节点或另找时间重跑该局观察；(c) 维持 FAIL 并调查节点差异。
- 限制：只在 A40 成立；PASS／FAIL 都只覆盖这 177 局，不证明全部 800 局逐字节等价。
- **用户裁决（2026-10-04）**：「登记为环境敏感局。」即选 (a)。`noise_gate.py gen-regress mark-jitter` 写参照（`NOISE_REF_MARK=PASS set=v9 id=MoveCube|23400200 observed=1 sets_unchanged=1 sha=5119e2ac71ca->90c0ea527dd7`），用新参照对首跑 rg-v9r 重判：`GEN_REGRESS=PASS set=v9 n=129 match=127 jitter=2 flip=0 structural=0 unknown=0 missing=0 invalid=0`；xhard0 重判不变 `GEN_REGRESS=PASS set=xhard0 n=48 match=48 …`。记录 `records/rg-v9r.rejudge.*`、`records/rg-x0.rejudge.jsonl`。
- GL 占位作业 63167696、63167697 已按清单 `scancel`；NFS 暂存 `maint-regress/` 与 `robomme_benchmark-maint` 检出保留，待裁决后清理（「PASS 后删新跑产物」的预批不适用于 FAIL）。

## ⑫ 归档文件清单（`records/`）

`rg-*.regress.jsonl`／`.episodes.md`（逐局判定与报告）、`rg-v9-final-local.*`（本机细分，含分叉步）、`rg-v9r.rerun.jsonl`、`rg-v9r.flips.jsonl`、`budget-caps.json`、`budget-ledger.jsonl`、`launch/`（各遍 launch 与来源报告）、`*.summary.txt`（各遍包装层日志去进度行）、`pass.sh.txt`、`chain_first2.sh.txt`、`chain_rerun.sh.txt`。h5 不入库：翻转局三次产物在本机 `artifacts/maint-regress/pull/`。
