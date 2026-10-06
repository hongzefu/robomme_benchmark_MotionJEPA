# sg-eval-gl-20261004-01 四模型评估：result（收尾时点，部分完成）

计划：`1003-oracle-subgoal-groundsg-eval-plan.md`；起跑档案见同目录 `launch.md`。GL 执行副本冻结在 `a299fcdc`（12.453）；本机主检出运行时 `4b8b4636`（与冻结提交的运行路径零差异，见 `LG3_RUNTIME_DIFF`）。

**本轮在 2026-10-05 22:17 按用户指令中止**（原话：「现在立刻收尾。停止本机器和gl上所有任务 但是job不要关。」「Turbo上的资源先不动。只收尾不搬运。」）。本文件只记录到中止时点为止已经产出的结果；未跑完的部分逐项列在第七节。NFS（Turbo）上的结果与视频原地保留，没有搬回 `/data`，也没有删除；GL 占位 job 全部保留未取消。

逐表原文：`records/tables.md`（各档总表与按任务表）、`records/verdicts.md`（全部判定行原文）、`records/diff/`（逐局差异表与对照表）、`records/video-index.tsv`（视频目录索引）、`records/scripts/`（全部一次性脚本逐字归档）。

## 一、结论

1. **接线正确性（第二档）**：新接口与原版接口在 Oracle、PonderPounce 上等价。
   - PonderPounce：本机 192/192、GL 分片 0 96/96 逐步完全一致。
   - Oracle：GL 192 局终态 192/192 相同、逐步一致 180（其余 12 局是单独起服务的补跑局，服务端随机数不对齐，只比终态）；本机终态 189/192。
   - QwenVL：GL 分片 00 两侧都有终态的 37 局逐步完全一致；本机终态 176/192、逐步 141/192（分叉都在动作数值末位，未专门定性）。
2. **生成无回归（第一档）**：GL `GEN_REGRESS=PASS`（V9 129 局 match 127、jitter 2；xhard0 48/48）；本机旧码对新码两侧都生成成功的局全部逐字节相同。
3. **V9 第三档已有正式成绩**：Oracle 800 局 **52.9%**（423/800）；PonderPounce 分片 0（400 局）**16.8%**（67/400）。QwenVL 只跑了 9 局即中止，没有成绩。
4. **跨机器复刻（第三档 Oracle，不计正式成绩）**：本机 RTX 6000 Ada 复刻 800 局 51.75%，与 GL A40 的 52.9% 无显著差异（McNemar p=0.42，终态一致 84.4%）。

## 二、第一档（生成对拍）

| 站点 | 集合 | 判定 |
|---|---|---|
| GL（gl1525，A40） | V9 129 局 | `GEN_REGRESS=PASS`：match 127、jitter 2（MoveCube 23400200、BinFill 16400000）、flip/structural/missing 0 |
| GL | xhard0 48 局 | `GEN_REGRESS=PASS`：match 48 |
| 本机（旧码对新码） | V9 129 局 | byte_equal 128、gen_fail 1（BinFill xhard1 16400000，新码失败） |
| 本机 | xhard0 48 局 | byte_equal 47、gen_fail 1（VideoPlaceOrder xhard0 611101，两侧都失败） |

逐局定性：`records/diff/gate1-gl-v9-episodes.md`、`records/diff/gate1-gl-xhard0-episodes.md`。

## 三、第二档（xhard0，原版接口对新接口）

### 表 1：判定行摘要

| 站点 | 模型 | 比较局数 | 终态相同 | 逐步一致 | 判定 |
|---|---|---|---|---|---|
| 本机 | Oracle | 192 | 189 | 101 | INFO |
| 本机 | PonderPounce | 192 | 192 | 192 | INFO |
| 本机 | QwenVL | 192 | 176 | 141 | INFO |
| GL | Oracle | 192 | 192 | 180 | INFO |
| GL | PonderPounce 分片 0 | 96 | 96 | 96 | INFO |
| GL | QwenVL 分片 00 | 37（另 2 局新侧 error） | 37 | 37 | INCOMPLETE |

读法：GroundSG 服务端随机数跨局累积，只有每次起服务后的第一局逐步判别有效；服务重启（续跑、补跑）之后的局只比终态。

### 表 2：成功率

| 站点 | 模型 | 原版 | 新接口 |
|---|---|---|---|
| 本机 | Oracle | 140/192（72.9%） | 139/192（72.4%，含 12 局补跑） |
| 本机 | QwenVL | 47/192（24.5%） | 48/192（25.0%，含 5 局补跑） |
| 本机 | PonderPounce | 82/192（42.7%） | 82/192（42.7%） |
| GL | Oracle | 144/192（75.0%） | 144/192（75.0%，含 12 局补跑） |
| GL | PonderPounce 分片 0 | 39/96（40.6%） | 39/96（40.6%） |
| GL | QwenVL 分片 00 | 9/39 | 9/37 有终态（另 2 局 error） |

按任务表见 `records/tables.md`；逐局差异表见 `records/diff/gate2-*.md`。

### 补跑与合表

- SwingXtimes 叠字视频文件名超 255 字节（12.453 修复前）致新侧 error：本机 Oracle 12 局、本机 QwenVL 5 局、GL Oracle 12 局，都用修复后的代码补跑（GL 用 `a299fcdc`），补跑行按 key 替换原 error 行，合表文件在 `artifacts/sg-evaluation/sg-eval-gl-20261004-01/{local-g2,gl-g2}/gate2-*/new-merged.results.jsonl`，原结果文件未改。补跑结果：本机 Oracle 12/12 成功，本机 QwenVL 4 fail + 1 timeout，GL Oracle 12/12 成功。
- GL QwenVL 分片 00 新侧 InsertPeg_xhard0_631501、VideoPlaceOrder_xhard0_610701 两局各撞 30 分钟单局墙钟上限 2 次（截断在第 1120～1264 步，A40 上 QwenVL 每步约 1.5 s），infra 重试额度 3 耗尽记 error，未补跑。

## 四、第三档（V9 test-hard，1600 步 strict cap）

### 表 3：GL 正式结果

| 模型 | 计划局数 | 已有终态 | 成功 | 失败 | timeout | error | 成功率 |
|---|---|---|---|---|---|---|---|
| Oracle | 800 | 800 | 423 | 191 | 186 | 0 | **52.9%** |
| PonderPounce | 800 | 400（分片 0） | 67 | 260 | 72 | 1 | 16.8%（仅分片 0） |
| QwenVL | 800 | 9（分片 00，中断） | 0 | 3 | 6 | 0 | — |
| Astra | 1（连通） | 0 | | | | | 未开跑 |

PonderPounce 那 1 局 error：VideoPlaceOrder_xhard2_19100901，第 1541 步 `Ponder context overflow: S2 context length 16453 exceeds cap 16384`，3 次重试都在同一步失败，属模型自身上下文上限，不是基础设施故障。

### 表 4：按任务（成功／已跑）

| 任务 | GL Oracle | GL PonderPounce 分片 0 | 本机复刻 Oracle |
|---|---|---|---|
| BinFill | 19/50 | 1/25 | 20/50 |
| ButtonUnmask | 13/50 | 4/25 | 13/50 |
| ButtonUnmaskSwap | 21/50 | 3/25 | 20/50 |
| InsertPeg | 9/50 | 1/25 | 11/50 |
| MoveCube | 19/50 | 4/25 | 18/50 |
| PatternLock | 30/50 | 0/25 | 30/50 |
| PickHighlight | 0/50 | 0/25 | 0/50 |
| PickXtimes | 48/50 | 20/25 | 49/50 |
| RouteStick | 10/50 | 0/25 | 10/50 |
| StopCube | 10/50 | 0/25 | 13/50 |
| SwingXtimes | 44/50 | 5/25 | 38/50 |
| VideoPlaceButton | 42/50 | 5/25 | 40/50 |
| VideoPlaceOrder | 44/50 | 7/25 | 44/50 |
| VideoRepick | 50/50 | 10/25 | 49/50 |
| VideoUnmask | 17/50 | 7/25 | 16/50 |
| VideoUnmaskSwap | 47/50 | 0/25 | 43/50 |

中断分片（本机 PonderPounce 184 局、本机 QwenVL 137 局、GL QwenVL 9 局）的按任务表见 `records/tables.md`。

## 五、本机结果（不参与成绩标注）

- 预检：`PREFLIGHT_SUMMARY=PASS routes=13`；显存峰值 Oracle 35.3 GB、QwenVL 44.2 GB（预分配 0.75）、PonderPounce 27.4 GB；`STEP_CAP=PASS` ×3（xhard0 1300、V9 1600）；`VIDEO_SAVED=PASS` ×9。
- 第一档、第二档见上两节的「本机」行。
- Astra 本机预检两侧各 1 局（VideoUnmask），都成功，6 次规划调用共 **0.5149 美元**（每次未命中缓存约 0.10 美元）。

### 本机复刻 GL 第三档（2026-10-05 用户批准；不计正式成绩）

分片文件与 GL 逐字节相同（`LG3_SHARD_SHA=PASS n=8`），参数照抄 GL 席位链，2 张 RTX 6000 Ada。

| 模型 | 本机已跑 | 对齐局数 | GL 成功率 | 本机成功率 | 终态一致 | 只 GL 成功／只本机成功 | McNemar p |
|---|---|---|---|---|---|---|---|
| Oracle | 800/800 | 800 | 52.88% | 51.75% | 84.4% | 54／45 | 0.42 |
| PonderPounce 分片 00 | 184/400（中断） | 184 | 10.9% | 13.6% | 82.6% | 3／8 | 0.23 |
| QwenVL 分片 00 | 137/160（中断） | 9 | 0% | 0% | 77.8% | 0／0 | 1 |

逐任务对照：`records/diff/gate3-compare-*.md`。

## 六、运行中的偏离与事故（均已处置或记录）

1. SwingXtimes 叠字视频文件名超 255 字节致 Broken pipe：12.453 修复 episode_id 为短编号；受影响的第二档局全部补跑（见第三节）。GL 第三档本就跑在修复后的 `a299fcdc` 上，SwingXtimes 50 局无 error，无需补跑。
2. GL 第三档 Oracle 分片局号整体错位 12：首局即被身份检查拦下（`IDENTITY_MISMATCH`），重出分片后重起；旧分片保留为 `*.bad-epoffset`；12.455 在清单工具里加了逐行核对。
3. GL QwenVL 客户端环境与 glibc 2.28 不兼容：重建 GL client-env，flash-attn 以 sysroot 2.17 编译；修好后席位 03 正常运行。
4. 本机第二档 Oracle 新侧 reset 额度按每局 1 次给错（应为 2N+20）：v2 续跑修正。
5. 预检时在运行中修改 `run_eval_gl.sh` 致一条路线 syntax error：在重跑额度内重跑；此后不改运行中的脚本。
6. 主会话监听两次漏报致 GL 卡空转数小时：加每分钟兜底巡检。
7. GL 上 QwenVL 单局墙钟上限 30 分钟不够（见第三节）：已备好 `seat_chain_v2.sh`／`launch_seat_v2.sh`（上限 3600 s，步数上限不变），因取消步骤 `63188711.3` 的操作被安全分类器拦下、等待用户授权期间本轮中止，v2 只在席位 04 起跑了约 7 分钟。
8. 第二档 `validate_trace` 行序约定与 GroundSG 实际轨迹不符（12.454 放宽校验方）；`gate2_compare` 遇失效节点本地路径退回身份索引（12.452）。

## 七、未完成清单（中止时点）

| 项目 | 状态 |
|---|---|
| GL 第二档 PonderPounce 分片 1（96 局） | 未开跑 |
| GL 第二档 QwenVL 分片 01～04（约 153 局） | 分片 01 原版侧起跑约 7 分钟后中止，其余未开跑 |
| GL 第二档 QwenVL 分片 00 新侧 2 局 error | 未补跑 |
| GL 第二档 Astra（32 局，已批） | 未开跑（两卡 job 一直排队） |
| GL 第三档 PonderPounce 分片 1（400 局） | 未开跑 |
| GL 第三档 QwenVL（800 局） | 分片 00 跑到 9/160 中止，其余未开跑 |
| GL 第三档 Astra 连通 1 局（已批） | 未开跑 |
| 本机复刻 PonderPounce（800 局） | 分片 00 跑到 184/400 中止 |
| 本机复刻 QwenVL（800 局） | 分片 00 跑到 137/160 中止 |

续跑方式：同一 `--stage` 重跑即续跑（按 results 与账本只补无终态的身份）；QwenVL 席位改用 `launch_seat_v2.sh`。Astra 已用 2 局、0.5149 美元。

## 八、用户决策项

1. **9 个 GL 占位 job 是否释放**：63188711、63188712 为 RUNNING 空占，63188713～16、63188719、63188720、63188721 为 PENDING；按用户指令未取消。释放用清单 `scancel`，不要 `scancel -u`。
2. **Turbo（NFS）上的产物**：用户令「先不动」。约 11.9 GB（`media` 5.6 GB、`gate2-qwenvl` 4.3 GB、`gate2-oracle` 1.1 GB 等）在 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/sgeval-20261004/`，是否搬回 `/data`、何时清理待定。若要续跑，必须保留（续跑读这些 stage 目录）。
3. **PonderPounce 上下文超限那 1 局如何计分**：建议按失败计（策略到第 1541 步仍未成功）；另一选项是单列「模型容量超限」、不进分母。
4. **GL QwenVL 第二档那 2 局**：若不补跑，GL QwenVL 分片 00 的 GATE2 保持 INCOMPLETE；补跑需 v2（单局上限 1 小时）。
5. **本机第二档 QwenVL 起服务后第一局也逐步分叉**（0/2），分叉在动作数值末位、子目标文本相同；GL 同模型 37/37 逐步一致。若需定性，需在同机同卡对同一局重跑两次比较。
6. **生成疑点 BinFill xhard1 16400000**：新码在本机与 A40 上都生成失败、本机旧码成功；闸门判抖动非回归。若要定性需新旧码同机对照。
7. **残留进程 PID 2961357**（`serve_policy.py --port=23310`，10-03 测试遗留，不占显卡）：未动，是否清理待定。
8. **中间产物**：本机第一档 h5（`local-g1`，实测 171 GB；整个本机产物目录 182 GB）等按「收尾只保留最终产物」应删除；本轮按「只收尾不搬运」未删，待用户确认。
