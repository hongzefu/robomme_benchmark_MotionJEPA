# 未定事项清单（截至 2026-10-02）

本文件汇总 2026-09-28 以来尚未由用户拍板的全部事项。每条写明来源、现状（判定行原文）、证据位置、可选处置与对应命令或改动点，处理时不需要再检索。用户裁决后在该条末尾追加「**裁决**：<日期> <原话>」，不删原文。

- 取数时间：2026-10-02 约 20:30 EDT，分支 `newtaskRelease-taskV9`，HEAD `59e5474e`（12.336）。站点进程、磁盘余量等会变化，处理前请复核。
- 路径约定：不带前缀的路径相对仓库根 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`；`artifacts/` 不进 git，只在 sled-vail 本机有。NFS 根为 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu`。
- 本清单只记录，不执行任何处置；所有事项都**不阻断**已交付的 V9 数据集（V9 交付闸门全部 PASS）。

## 总表

| 编号 | 事项 | 来源 | 建议 |
|---|---|---|---|
| A1 | V9 新 80 局二次生成对拍 `PARITY_H_H2=FAIL` | 10-02 V9 | 先定 A5 容差口径，再决定 (a) 记录在案或 (b)(c) |
| A2 | V7 二次生成对拍 FAIL（InsertPeg/8），当时「暂时不管」 | 09-29 V7 | 结案 |
| A3 | V7.5 评估 MME 相对标准 `inside=no` | 09-30 V7.5 | 接受 |
| A4 | V8 xhard0 两入口评估 MME 18 局成败相反（只出 INFO） | 10-01 V8 | 认可「不判回归」 |
| A5 | 对拍容差阈值从未经用户审核 | 09-28 拆包 | 审核；可用 V8 1070 对重新标定 |
| A6 | 权重核对 `V8_EVAL_ASSETS=FAIL` 被放行 | 10-02 V8 评估 | 核对脚本收进仓库并与建锁过滤一致 |
| B1 | V9 站点缺 MoveCube 区域变化注记 | 10-02 V9 | 补注记 |
| B2 | V9 站点标题仍为「RoboMME v8」 | 10-02 V9 | 按 catalog 区分版本 |
| B3 | `scripts/README.md` 局数与长度表过时 | 10-02 V9 | 换成 V9 数据 |
| B4 | V9 交付树 hardlink 的删除责任 | 10-02 V9 | 与 F4 一并定 |
| B5 | `TIER_MAX_STEPS` 查表去留（入口已固定 1600） | 10-02 V9 | 保留不动，待裁决 |
| B6 | xhard0 已退出 test-hard（12.341，开关 `ROBOMME_HARD_XHARD0_IN_TEST_HARD=1` 可恢复）；`v8_site_catalog.py` 自带 `XHARD0_PER_TASK=12`、已有 992 身份文件与站点按历史口径工作，以后重导身份文件时需跟进 | 10-02 V9 | 已定；站点与重导待处理 |
| C1 | 核心短测 4 个既有失败 + 2 个连带失败 | 09-17 起 | 改测试对齐官方行为 |
| C2 | 核心短测整体未维护（耗时 477 s 超 280 s 预算、v7/v8 历史用例、monkeypatch 钉 V8 表、命名错位、重叠断言） | 10-02 | 先拆 ≤2 分钟定稿核心集，其余待裁决 |
| D1 | PickXtimes、StopCube、PickHighlight 两模型全 0 成功，未诊断 | 10-02 V8 评估 | 视需要立项诊断 |
| D2 | V7.5 预算超额事后追认 | 09-30 V7.5 | 追认 |
| D3 | V8 评估各轮审查遗留的小问题 | 10-02 V8 评估 | 视需要小修 |
| D4 | 挑战接口 `challenge_interface/scripts/phase1_eval.py` 四处缺陷（成功判定按子串、reset 等待不重询、异常不 close、IK 失败空观测崩溃） | 10-04 测试重构 T8a | 先不修（用户 10-04），测试锁定现状 |
| D5 | `hard_builder.make_env_for_episode` 交给 gym.make 的 sampling_config／native_episode_spec 与 builder 缓存共用对象 | 10-04 测试重构 P | 本轮不修（对拍进行中），测试锁定现状 |
| E1 | 「shared 步骤结束会把卡重置为独占」未写入规则 | 09-30 V7.5 | 写入正本与 `docs/greatlakes.md` |
| F1 | 本机 5 个站点服务的去留 | 09-28 起 | 只留 8081、8082 |
| F2 | 8081／8082 站紫色「语义调整」小标签留不留 | 10-02 V8 站点 | 由用户定 |
| F3 | NFS 上 5 份代码克隆删不删 | 10-01 起 | 视 A1 决定 |
| F4 | 本机大产物保留策略（V7 971 G 等） | 09-29 起 | 删 V7 对拍与冒烟 |
| F5 | 09-28 拆包会话遗留（已基本清理，仅剩 A5） | 09-28 | 结案 |
| F6 | 本地未推送分支与旧 worktree | 09-26 起 | 由用户定 |
| G1 | `_freeze.py` 的 /2、/3 档位预检读全局 `TIERS` | 10-01 V8 | 顺手修 |
| G2 | V8 补抽统计口径 35 与 44 不一致 | 10-02 V8 | 结案 |
| H1 | 本机测速结论是否转发到另一会话 | 10-01 | 结案 |
| H2 | 10 卡耗时估算的简化算式笔误 | 10-02 | 结案 |
| H3 | V8 评估冒烟缺包被记为非基础设施错误 | 10-02 V8 评估 | 结案或并入 D3 |

---

## A 类：对拍、回放或判据没过

### A1 V9 新 80 局 H:H2 二次生成对拍 FAIL（2026-10-02）

**判定行**（`artifacts/newtask-v9/logs/compare-hh2.log`）：

```
PARITY_H_H2=FAIL tier=v9 compared=80 cells=2 missing=0 extra=0 duplicate=0 identity_equal=80 byte_equal=72 noise=7 h2_fail=1 flipped=0 structural=0 expected=80 frozen=80 delivery=80 left_rows=80 right_rows=80 shape=cells43:272+272+92+144+20 setup_equal=79 schema_equal=79 success_equal=79 both_success=79 both_fail=0 noise_first_divergence_min=142 tol_over=0 tol_noise=7 over_total=7 hard_line_5pct=HIT action_max=3.63/0.0413 state_max=3.62/0.0411 image_mad=8.11/1 frames_max=8/5 sha_equal=72 frames_equal=73 binding_ok=80 recovery_mismatch=0 identities=80 manifest_rows_all=800
PARITY_REFERENCE=INFO pair=H:H2 tier=v9 first_divergence_n=7 first_divergence_median=208 first_divergence_min=142
```

**为什么 FAIL：两个独立原因**
1. `h2_fail=1`：MoveCube 候选 66 第一次生成（gen1）成功，第二次（H2）失败。
2. 5% 硬线：超容差局数 7 > 0.05 × 80 = 4。代码在 `scripts/parity/hard_parity.py::cmd_compare`：`hard_line = len(tol_hits) > 0.05 * n`；h2_fail 那局因 `m.error` 非空不计入 `tol_hits`。

**因此只换掉候选 66 仍然 FAIL**：7 局 noise 依旧超过 4 局。

**逐局明细**（tier 均为 xhard4；容差 action 0.041266、state 0.041137、image_mad 1.0、frames 5；H 执行步是 gen1 的值）：

| task / 候选 / seed | spec 前 12 位 | 终态 | 首次分叉步 | action_max | state_max | image_mad | 帧数 H/H2 | H 执行步 |
|---|---|---|---|---|---|---|---|---|
| InsertPeg / 47 / 23304700 | ccba1704fb9b | noise | 142 | 3.3027 | 3.2961 | 8.1105 | 494 / 487 | 247 |
| MoveCube / 16 / 23401600 | ddd3e8847631 | noise | 174 | 2.0 | 1.8264 | 4.0009 | 554 / 550 | 242 |
| MoveCube / 21 / 23402100 | 47f1d568ff95 | noise | 423 | 2.0 | 0.07879 | 1.1668 | 543 / 545 | 245 |
| MoveCube / 39 / 23403900 | 05362f0bb562 | noise | 186 | 2.0 | 0.42718 | 2.9352 | 290 / 296 | 111 |
| MoveCube / 48 / 23404800 | 0415900e7fce | noise | 422 | 3.6263 | 3.6208 | 2.4244 | 540 / 532 | 256 |
| MoveCube / 49 / 23404900 | b15bc272551f | noise | 208 | 3.1116 | 3.1116 | 3.9961 | 615 / 620 | 233 |
| MoveCube / 53 / 23405300 | 2ed590bc0d4d | noise | 425 | 0.06259 | 0.06233 | 0.4357 | 742 / 742 | 222 |
| MoveCube / 66 / 23406600 | 89183781e55a | h2_fail | — | — | — | — | 560 / 无 | 266 |

- 7 局 noise：两次都成功，setup 与 schema 相同，只是轨迹从首次分叉步起数值不同。MoveCube 有 3 局 `action_max` 恰为 2.0，推断是夹爪维从 ±1 翻转（未逐维核对）。
- 不一致集中在 MoveCube 新区域：50 局里 7 局（6 noise + 1 h2_fail）；InsertPeg 30 局里 1 局。
- 候选 66 的 H2 失败原因（`artifacts/newtask-v9/parity/h2-nfs/movecube/results.jsonl`）：`"error": "MoveCube/episode_66: did not succeed after the complete task_list", "error_type": "DatasetGenerationError"`，H2 的 h5 只有 800 字节，另有 `FAILED_MoveCube_ep66_…mp4`。gen1 侧是第 2 轮递补成功，执行 266 步、560 帧。

**证据**
- 摘要：`docs/validation/newtask-v9/records/parity-hh2-summary.json`
- 逐局：`docs/validation/newtask-v9/records/parity-hh2-pairs.jsonl`（与 `artifacts/newtask-v9/parity/compare/HH2-v9/h5_pairs.jsonl` 字节相同）
- H 侧 h5：`artifacts/newtask-v9/parity/h5/H-v9/episodes/xhard4/<Task>_episode_<候选>/hdf5_files/`（符号链接，实体在 `artifacts/newtask-v9/gen/shard-movecube/` 与 `artifacts/newtask-v9/gen/insertpeg-root/`）
- H2 侧 h5：`artifacts/newtask-v9/parity/h2-nfs/movecube/` 与 `artifacts/newtask-v9/parity/h2-nfs/insertpeg/`（NFS 原件已删，这是唯一副本）

**对照**
- V8：`PARITY_H_H2=PASS tier=v8 compared=1070 … byte_equal=1058 noise=12 h2_fail=0 … over_total=12 hard_line_5pct=ok`（12/1070 = 1.1%）。
- V7：见 A2，同样是一局第二次生成失败。

**可选处置**
- **(a) 保持现交付，记录在案**：认定为数值噪声加一次偶发回放失败，与 V7 InsertPeg/8 的处理一致。只需在本条写裁决。
- **(b) 换掉候选 66**（单做这一项仍是 FAIL，见上）：
  - MoveCube 按运动方式（`scripts/injection-dev/_freeze.py::_movecube_way`，取 `spec.initializations` 最后一项的 `way_idx`）分配 17／17／16。候选 66 属于 way 0；way 0 还没试过的备用只剩 69（seed 23406900，spec `f6fa7dcdddf5`）、73（23407300，`e1b31d7a2073`）、77（23407700，`4318a292be82`），按候选号先用 69。
  - 各方式现状：way 0 共 27 个候选，已交付 17、失败 7；way 1 共 25 个，已交付 17、失败 6、备用 78/79；way 2 共 28 个，已交付 16、失败 0、备用 12 个。
  - 现有工具不支持换掉一个已成功的候选：`scripts/injection-dev/generate_h5.py` 对 hard-specs/4 拒绝 `--redo`；`scripts/injection-dev/_rollout.py::apply_results` 只在失败时递补。需要手改 `artifacts/newtask-v9/gen/shard-movecube/specs/xhard4/specs.jsonl`（66 改 `selected=false`，69 改 `selected=true`），或新写一个 swap 工具，两种做法都要另立计划。
  - 之后的步骤：
    1. 在 GL A40 上 `generate_h5.py --mode continue --specs <片>/specs --cells v9shard1 --output <片> --resume`，聚合时加 `--rebase /nfs/turbo/coe-chaijy-unreplicated/hongzefu/v9gen-out/gen=$PWD/artifacts/newtask-v9/gen`；
    2. `scripts/parity/hard_regression.py movecube-layout`；
    3. 重做 3b：`scripts/injection-dev/v9_subset_specs.py assemble`（写新目录）、`link`（先删 V9 树内 66 的旧链接）、`verify --rehash-h5`，`hard_regression.py delivery-set --cells v9full --delivery …`、`step-headroom --xhard0 artifacts/newtask-v7/parity/h5/H-xhard0`、`reset-replay --out <新文件>`，换包 xhard4，核心短测，`UPSTREAM_GUARD`，`xhard0-reset-parity`；
    4. 新局做 H2 与 compare；
    5. 两模型重评该身份（`artifacts/v9-evaluation/v9-two-policy-gl10-20261002-01/manifest/shard-08.json` 中的 `MoveCube_xhard4_23406600`，`builder_episode` 60 不变，`reused.json` 不受影响），重出报告，重建 8082 站。
- **(c) 先审核容差（A5）再重判**：不动生成。若改为只数非 noise 的超容差局，V9 只剩 h2_fail 一项。

**2026-10-03 补记**：用户原话「我现在不能够再去改和 Main branch TestHard 一致的数据集了……就必须保持完全一致」，选项 (b) 因数据冻结作废。V9 交付集 16 任务 × 50 局 = 800 局的完整对拍事实（782 局逐字节可复现、17 局轨迹分叉、1 局第二次生成失败）与逐局明细见 [`1003-generation-parity-reproducibility.md`](1003-generation-parity-reproducibility.md)。是否正式结案仍待用户裁决。

### A2 V7 二次生成对拍 FAIL（2026-09-29，暂缓中）

- 判定行（`docs/validation/newtask-v7/README.md`）：`PARITY_H_H2=FAIL tier=v7 shape=13x3x20+16x1x20 compared=1100 identity_equal=1100 setup_equal=1099 schema_equal=1099 success_equal=1099 both_success=1099 both_fail=0 tol_over=0 noise=13 over_total=13 hard_line_5pct=ok … sha_equal=1086 frames_equal=1086 binding_ok=1100 recovery_mismatch=0`
- 唯一来源 `xhard4/InsertPeg/8`：H2 侧 `DatasetGenerationError`（800 字节 h5，`IndexError`），gen1 侧成功 505 帧。
- 当时给的选项：(a) 认定偶发、交付集不动；(b) 换备用候选。
- 用户 2026-09-29 原话：「1暂时不管 2暂时不管 3同意递补 4 没看懂详细讲」，即暂不处理，交付集不动，保留 H2 本地副本。
- 待定：是否正式结案。V7 交付已被 V8、V9 取代，建议结案。
- **现状更正（2026-10-03 资源清理）**：上面「保留 H2 本地副本」已不成立——V7 H2 实体 09-29 已删，V7 gen1（1100 局）与 P 侧拉回缓存在 2026-10-03 按 `1003-resource-cleanup-plan.md` 口径 2 删除；比对记录 `newtask-v7/parity/compare`、`newtask-v7/logs/cmp-h2.log` 原地保留（执行留档 `docs/validation/newtask-v9/cleanup-20261003.md`）。

### A3 V7.5 评估 MME 相对标准 inside=no（2026-09-30 跑完，10-01 晚再问，未定）

**判定行**（正本 `artifacts/v7.5eval/summary/verdicts.txt`，由 `step6_summary.py --final` 于 2026-09-30 08:10 EDT 生成）：

```
RELATIVE_ACCEPT=INFO policy=mme inside=no s2f=7 f2s=9 max_off_s2f=10 max_off_f2s=9 sr_diff_pp=1.0417 off_sr_range=[-1.0417,-0.5208] ci=[-3.125,5.208] off_ci=历史:重跑一[-3.125,2.083];历史:重跑二[-5.208,3.125];重跑一:重跑二[-5.208,4.167] extra_sample_trigger=no
RELATIVE_ACCEPT=INFO policy=smvla inside=n/a s2f=0 f2s=0 … note=官方重跑无翻转 prod_flips=none
OFFICIAL_NOISE=INFO pair=历史:重跑一 policy=mme compared=192 … s2f=4 f2s=3 … sr_diff_pp=-0.5208 ci=[-3.125,2.083] mcnemar_p=1
OFFICIAL_NOISE=INFO pair=历史:重跑二 policy=mme compared=192 … s2f=9 f2s=7 … sr_diff_pp=-1.0417 ci=[-5.208,3.125] mcnemar_p=0.8036
OFFICIAL_NOISE=INFO pair=重跑一:重跑二 policy=mme compared=192 … s2f=10 f2s=9 … sr_diff_pp=-0.5208 ci=[-5.208,4.167] mcnemar_p=1
POLICY_REPLAY=INFO cond=P1 policy=mme det=off mode=restart n=5 bitwise=2/5 max_abs=0.0039 first_diff_step_min=0 above_action_max=0
POLICY_REPLAY=INFO cond=P1 policy=mme det=on mode=restart n=5 bitwise=5/5 max_abs=0 …
```

（另：P3、P5、P7 关态重启逐位分别 0/5、0/5、0/5，最大差 0.0057、0.0096、0.005；SimpleMemVLA 三对官方重跑全部 0 翻转。）

**判据**（计划 `docs/plans/0929-v7.5eval-restructure-plan.md` §3.1）：`inside=yes` 当且仅当以下三条同时成立：
1. 主比较「成功→失败」数 ≤ 官方三对中该方向的最大值；
2. 「失败→成功」数 ≤ 官方三对最大值；
3. 成功率差的点估计落在官方三对成功率差的 [最小, 最大] 之间。

代码：`scripts/eval-official/compare.py::relative_accept`（`cond_s2f`、`cond_f2s`、`cond_sr`），打印在 `compare.py::cmd_relative_accept`。计划只写「输出 inside 交用户判断」，没有预定处置。

**没过的原因**：只有第 3 条没过。官方三对的成功率差恰好都 ≤ 0（区间只有 1 局宽），正式跑法 51 局，比三份官方结果（50、49、48）都多，点估计必然落在区间外。两条翻转数都满足。根源是 MME 同输入跨进程不逐位一致。

**证据**：`docs/validation/v7.5eval/summary.md`（§2、§6，§7「用户待决事项」第 1 条）、`docs/validation/v7.5eval/prod-vs-official.md`、`docs/validation/v7.5eval/official-rerun.md`。

**可选处置**：接受（认定为 MME 非确定性带来的 1 局级差异）／不接受（需追加样本或换判据口径，另立计划）。

- **2026-10-03 资源清理**：按用户「xhard0也都要保留」，`artifacts/v7.5eval` 除 `venvs/` 外全部原地保留（官方路线三份检出删除，重跑需从 origin 取回并重建 venv）；本条判定仍待用户裁决（执行留档 `docs/validation/newtask-v9/cleanup-20261003.md`）。

### A4 V8 xhard0 两入口评估 MME 18 局成败相反（2026-10-01，只出 INFO、从未判定）

**判定行**（`docs/validation/newtask-v8/result.md` ⑧）：

```
XHARD0_EVAL_PARITY=INFO policy=mmevla compared=192 status_diff=18 steps_diff=115
XHARD0_EVAL_PARITY=INFO policy=simplememvla compared=192 status_diff=0 steps_diff=15
```

- 成功率：MME 官方入口 48/192，hard 入口 50/192；SimpleMemVLA 两边都是 141/192。SimpleMemVLA 的 15 局步数差都是 timeout 对 timeout（官方 1301／1344 步对 hard 1300 步，是上限计法差）。
- 产出函数 `scripts/parity/hard_regression.py::cmd_xhard0_eval_parity`，无条件输出 INFO。依据是 V8 计划风险第 7 条「xhard0 评估只能出 INFO：策略层不可复现……『没改坏 xhard0』由 `XHARD0_RESET_PARITY` 判定」。

**18 局**（官方 → hard，终态/步数）：

| task | seed | 官方 | hard |
|---|---|---|---|
| ButtonUnmask | 582300 | fail/223 | success/398 |
| ButtonUnmaskSwap | 571100 | fail/587 | success/458 |
| InsertPeg | 634700 | timeout/1301 | fail/108 |
| MoveCube | 642300 | timeout/1301 | success/270 |
| MoveCube | 644700 | success/213 | timeout/1301 |
| PickHighlight | 620301 | timeout/1301 | fail/781 |
| PickHighlight | 621900 | success/694 | fail/392 |
| PickXtimes | 510700 | fail/747 | success/814 |
| PickXtimes | 512700 | fail/697 | success/690 |
| RouteStick | 661500 | fail/217 | success/298 |
| SwingXtimes | 532300 | success/537 | fail/437 |
| SwingXtimes | 532700 | fail/477 | success/477 |
| VideoPlaceButton | 601901 | fail/199 | success/173 |
| VideoPlaceOrder | 612701 | fail/178 | success/224 |
| VideoUnmask | 562300 | success/281 | fail/378 |
| VideoUnmask | 564700 | success/293 | fail/415 |
| VideoUnmaskSwap | 550700 | success/996 | timeout/1301 |
| VideoUnmaskSwap | 552300 | success/256 | fail/254 |

- 方向：成功→非成功 7 局，非成功→成功 9 局，timeout→fail 2 局，净多 2 局成功。其中 6 局在 V7「11 局同卡重跑」中也出现过翻转。
- 证据：`docs/validation/newtask-v8/records/xhard0-eval-parity-mmevla.jsonl`（116 行，只记有差异的局）、`docs/validation/newtask-v8/records/xhard0-eval-parity-simplememvla.jsonl`。V7 参考在 `docs/validation/newtask-v7/README.md`「11 局同卡重跑对照」：`RERUN11_PARITY=INFO shape=11x2 compared=11 missing=0 self_flip_off=5 self_flip_hard=4 …`，结论「归因 A（策略端数值不确定性），B 不成立」。

**可选处置**：认可「不判回归」（xhard0 环境的正确性已由两次 `XHARD0_RESET_PARITY=PASS det_diff=0` 证明）／要求进一步诊断。

- **2026-10-03 资源清理**：xhard0 两份 h5、V7 xhard0 评估录像、`v8eval-xhard0` 等全部保留；`robomme_benchmark-v8eval` 克隆删除（HEAD 已在 `origin/newtaskRelease-taskV8`）。本条判定仍待用户裁决（执行留档 `docs/validation/newtask-v9/cleanup-20261003.md`）。

### A5 对拍容差阈值从未经用户审核（2026-09-28 定，一直沿用到 V9）

- 文件：`scripts/configs/hard-parity-tolerances.json`（sha256 `9600a1ed6d8c…`，提交 `c0fa6f95`，12.209）。

  | 键 | 值 |
  |---|---|
  | `action_max_rad` | 0.041265913943240015 |
  | `state_max` | 0.04113650321960449 |
  | `image_mad` | 1.0 |
  | `frames_max` | 5 |
  | `n` / `calibrated_from` | 144 / `"O:P native"` |
  | `raw_max` | action 0.02751、state 0.02742、image_mad 0.14436、frames 0 |
  | `rule` | 最大值 × 1.5（帧数向上取整），下界 0.005/0.005/1.0/5，合理性上界 0.05/0.05/10/200 |

- 标定留档：`docs/validation/newtask-v6/hard-split/stage4.md` §二「容差标定」，判定行 `PARITY_TOL_CALIB=PASS pair=O:P n=144 action_p95=0 action_max=0.0275 state_max=0.0274 image_mad_max=0.144 frames_max=0 tol_file_sha=9600a1ed6d8c`。144 对中 143 对逐字节相同，**唯一的非零样本**是 PickHighlight seed 12300（第 549 步起分叉）。原始数据在 `docs/validation/newtask-v6/hard-split/records/stage4/compare-OP-native/`。当时用户原话 U-22：「你先定 全部结束后再来找我」。
- 判定逻辑（`scripts/parity/hard_parity.py`）：
  - `load_tolerances` 读文件；`pair_metrics` 只比两侧共同帧，算出 action/state 最大绝对差、两相机逐帧平均绝对差的均值、帧数差、首次分叉步；
  - `_classify_over`：setup、schema、成败都相同且首次分叉步 > 0 的记 noise，否则记 fail；
  - `cmd_compare`：`verdict = PASS` 需要 `fail_over == 0` 且不过 5% 硬线；硬线把 noise 也计算在内。
- 影响：V8 的 12 局、V9 的 7 局 noise 都是按它判为超容差；V9 的硬线 HIT 由它决定。
- 可选处置：维持现值／用 V8 1070 对（12 局 noise）重新标定／改硬线口径（例如只数非 noise 的超容差局）。
- **2026-10-03 补记**：数据冻结后修改容差不改变交付集，只改变判定行的 PASS／FAIL；现行标准的三个问题与实测见 [`1003-generation-parity-reproducibility.md`](1003-generation-parity-reproducibility.md) 第五节。容差文件未改动，是否结案待用户裁决。

### A6 权重核对判 FAIL 被放行（V8 评估 2026-10-02；V9 沿用放行口径）

- V8 日志 `artifacts/v8-evaluation/logs/verify_assets.log`：
  ```
  ASSET mme-gl root=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/eval-out/mmevla-ckpt/perceptual-framesamp-modul/79999 files=18 missing=0 extra=0 mismatch=0 ok=True
  ASSET smvla root=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/SimpleMemVLA/checkpoints/simplememvla_robomme files=33 missing=0 extra=24 mismatch=0 ok=False
  V8_EVAL_ASSETS=FAIL assets=2
  EXIT_CODE=1
  ```
  `docs/validation/v8-two-policy-gl10-20261002-01/launch.md` §三没有写这行 FAIL，§七「与计划的出入」也没有列。
- V9 日志 `artifacts/v9-evaluation/logs/verify_assets.log`：`ASSET smvla … locked=9 missing=0 extra=24 mismatch=0 ok=True`、`V9_EVAL_ASSETS=PASS assets=2 note=锁外文件只计数`。V9 的核对脚本只在临时目录（`/home/hongzefu/.claude/jobs/e9ec3ef8/tmp/verify_assets.py`），没有进仓库。
- 多出的 24 个文件：`./.cache/huggingface/` 下的 `CACHEDIR.TAG`、`.gitignore`、`trees/6bf72043….json`，`./.cache/huggingface/download/` 下 11 个文件各一份 `.lock` 与 `.metadata`，以及 `./.DS_Store`。
- 关键事实：资产锁 `artifacts/v7.5eval/assets-lock.json`（`smvla.files` 9 个）在建锁时就排除了这 24 个文件——建锁脚本 `artifacts/v7.5eval/preflight/hash_assets.sh` 用的是 `find -L . -type f ! -path './.cache/*' ! -name .DS_Store`。所以锁本身没错，V8 判 FAIL 是因为当时的核对脚本没用同样的过滤。
- 可选处置：
  - (甲) 把核对脚本收进仓库（例如作为 `scripts/eval-official/compare.py` 的子命令），过滤规则与 `hash_assets.sh` 完全一致，extra 自然为 0；
  - (乙) 给锁加 `exclude` 字段并改 `compare.py::cmd_assets`（要改已冻结的锁格式，动静较大）；
  - 另需决定是否在 V8 评估 `launch.md` §七补记这次 FAIL。

---

## B 类：V9 交付与站点

### B1 V9 站点缺 MoveCube 区域变化注记

- V9 计划 §5 要求「MoveCube xhard4 另注区域变化」，没有做。`artifacts/newtask-v9/site/semantic.json` 里 MoveCube xhard4 为 `changed=false`，说明是固定文本「仅参数变化」。
- 原因：`scripts/injection-dev/site/v8_semantic_diff.py::build` 只比较 goal／subgoal 的文本句式；`changed=False` 时 note 固定为通用文本，只往 `NOTES` 字典加条目不会生效。该脚本当时不在任何子代理的可写集合内，计划也列为不改。
- 改法候选：
  1. 改 `build` 中的 note 赋值（改为 `note if note else <固定文本>`），并在 `NOTES` 加 `("MoveCube", "xhard4")` 一条；
  2. 不动语义脚本，在 `scripts/injection-dev/site/v8_site_catalog.py` 的 v9 分支往 `catalog["notes"]` 加一条，页面会通过 `Object.values(S.cat.notes)` 显示在页脚。
- 注记原文可取 `docs/validation/newtask-v9/result.md`：「MoveCube xhard4 区域 r_in 0.24、r_out 0.42、base_dist [0.31, 0.80]（圆心 (−0.06, 0)，其余键不变）」。
- 改后重建 8082 站，复跑 `scripts/injection-dev/site/v8_site_browser_check.py` 与 `scripts/injection-dev/site/v8_oracle_browser_check.py`。注意前者的 `semantic_section` 要求合集卡片数等于 changed 格数。

### B2 V9 站点标题仍为「RoboMME v8」

- 写死的位置（`scripts/injection-dev/site/v8_site.html`）：`<title>`「RoboMME v8 · 逐局对照」；`div.brand-name`「RoboMME v8」；`header.topbar h1`「v8 逐局对照」及其下说明；`p.oracle-legend`「xhard1～5 来自 V8 双模型评估」；配置来源处「配置逐局取自 v8 冻结规格」两处。
- `scripts/injection-dev/site/v8_site.py` 把 `HTML_PATH` 写死、没有 `--html` 参数；`scripts/injection-dev/site/site_server.py` 的 `_serve` 直接返回 HTML，不做模板替换。
- 改法候选：在页面 JS 里按 `catalog.eval.mode == "v9-reuse"`（或 `catalog.eval.run`）设置 `document.title` 与 `.brand-name`，V8 站不受影响；或接受现状（计划要求「布局完全一样」）。

### B3 `scripts/README.md` 局数与长度表过时

- 所在节 `## 3. 六档配置对比、局数与 episode 长度`：
  - episode 长度表是 V7 的均值，没有 xhard5 列，段首自注「本节暂未换表」；
  - 局数表与入口说明仍写「合计 1262 局」，而 12.333 起 `EXPECTED_CELLS` 已切到 V9（800 局 + xhard0 192 局 = 992）；
  - 配置表里 MoveCube xhard4 仍写「圆环 U」，没写 V9 新区域。
- 替换数据源：`docs/validation/newtask-v9/records/step-headroom.json` 的 `per_cell_mean`（43 格，含 demo、exec、total、n）、`per_cell_max`、`max_exec=1469`；xhard0 列沿用原来源。
- 属于纯文档更新，用户点头即可直接改。
- **裁决**：2026-10-02 用户「我现在只需要保留最新版本的 task 就是 taskV9……每个 task 只要 50 个」「保留 xhard0，但它不算在 800 里」「不裁 jsonl，只加校验」「代码不改了」。12.338 已把 `scripts/README.md` 重写为 V9 口径（800 = 16 × 50、992 = 800 + 192、`TIER_MAX_STEPS` 固定表），长度均值表撤下、改引 `V9_STEP_CAP`；新测试 `tests/lightweight/test_v9_packaged_800.py` 钉死。方案 `docs/plans/1002-v9-final-cleanup-plan.md`。

### B4 V9 交付树 hardlink 的删除责任

- `artifacts/newtask-v9/delivery`（名义 436 G）中有 720 局是指向 `artifacts/newtask-v8/gen1` 的 hardlink。单删 V8 gen1 不会释放空间，必须同时删 V9 delivery 才行，反之亦然。
- 待定：V8、V9 产物的保留策略，与 F4 一并决定。
- **执行（2026-10-03）**：V9 的 720 局两个名字（`newtask-v9/delivery` 与 `newtask-v8/gen1` 的 720 个局目录）都原地保留，`delivery/` 1601 个文件三次 sha 不变；`newtask-v8/gen1` 只删 349 个非 V9 局（执行留档 `docs/validation/newtask-v9/cleanup-20261003.md`）。

---

### B5 `TIER_MAX_STEPS` 查表去留（2026-10-02 新增，待定）

- **现状**：入口 `scripts/evaluation_hard.py` 自 12.339 起构造时固定 `max_steps=1600`、逐局不传，不再引用包内常量表 `TIER_MAX_STEPS = {xhard0: 1300, xhard1～xhard5: 1600}`（用户原话：「max_steps 应该是一个固定的数值……不需要再从 episode 里面读」「可以，全部 1600」「第二个问题我只要改 evaluation_hard」「查表问题设为待定写入 Docs 里面」）。
- **仍在用这张表的地方**：`scripts/eval-official/env_client.py::tier_max_steps` 与 `scripts/eval-official/v8_manifest.py`（清单每局写 `effective_max_steps = TIER_MAX_STEPS[tier]`，客户端起环境前核对相等并以 `step_cap` 截断）——已跑完的 V9 800 局双模型评估（`docs/validation/v9-two-policy-gl10-20261002-01/`）与 xhard0 192 局评估就是按它执行的（xhard1～5 1600、xhard0 1300）；`scripts/parity/hard_regression.py`（reset-replay、eval-smoke、step-headroom 的 xhard0 按 1300 查）；`scripts/injection-dev/site/v8_subgoal_lengths.py`；测试 `test_xhard0_native.py::test_TIER_MAX_STEPS六档且xhard0为1300`、`test_v8_specs_schema.py`、`test_v9_packaged_800.py`（只记录现值）。
- **选项**：(a) 保留不动——表只描述评估流水线与历史评估口径，与入口「全部 1600」并存，README 已写明两者关系；(b) 拉平成全 1600——改 `hard_specs.py` 一行与 3 个测试、评估客户端的 xhard0 校验，但已跑的 xhard0 评估记录（1300）与表不再一致；(c) 删表改单常量 `EXEC_CAP=1600`——动包代码与上述全部使用者。
- **影响面**：(a) 零改动；(b)(c) 触及 `src/robomme_hard`（P2 逐个批准）与评估清单校验，须重跑 eval-official 冒烟。
- **建议**：(a)，待用户裁决。

## C 类：测试
- **裁决**：2026-10-02 用户认可按清单删除 V6/V7/V8 产物（`newtask-v8/gen1` 整删，V9 delivery 的硬链接随之成为唯一引用，空间由 V9 独占）。阶段 A（12.338）已先把 8082 站引用的小件搬入 `newtask-v9/`、拼出 `v9-evaluation/final/`；删除在阶段 B（12.339）执行。

### C1 核心短测 4 个既有失败 + 2 个连带失败

| 测试 | 断言什么 | 为什么失败 |
|---|---|---|
| `tests/lightweight/test_TaskGoal.py::test_unknown_env_returns_single_goal_when_equal` | 未知环境返回 `[""]` | `src/robomme/robomme_env/utils/task_goal.py::get_language_goal` 对未知环境返回 `[]`（日志：`assert [] == ['']`） |
| `tests/lightweight/test_TaskGoal.py::test_swingxtimes_multiple` | 文本含 `back and forth` | 源码写的是 `back-and-forth` |
| `tests/lightweight/test_step_error_handling.py::test_step_error_returns_status_error` | `DemonstrationWrapper.step` 含 try | `src/robomme/env_record_wrapper/DemonstrationWrapper.py` 的 `step` 没有 try（docstring 声称会捕获） |
| `tests/lightweight/test_step_error_handling.py::test_scripts_use_status_check_not_bare_try_except` | `scripts/dataset_replay.py` 有 `info.get("status")` 或 `status==`，且没有裸 try 包 `env.step` | 只有 `info.get("status", "unknown")`（不匹配精确子串），且有 `try: env.step … except Exception` |

- 连带失败：`tests/lightweight/test_v8_eval_report.py::test_zz_summary_line` 与 `tests/lightweight/test_v8_eval_video_mover.py::test_zz_summary_line` 断言**整个 pytest 会话**的失败数为 0（日志 `assert 4 == 0`、`assert 5 == 0`）。前 4 个修掉后它们自然通过，单独跑这两个文件本来就通过。
- 被测源码与官方 `1fadc0ec` 逐字节相同（`git diff --stat 1fadc0ec HEAD -- src/robomme scripts/dataset_replay.py scripts/run_example.py` 为空）。改源码同时受三条约束：AGENTS.md P1（`scripts/dataset_replay.py` 不得改动）、P2（`src/robomme/` 改动须逐个批准）、`UPSTREAM_GUARD`（要求与官方逐字节相同）。
- 这 4 个失败早有记录：`docs/validation/newtask-v6/records/legacy/s0/lightweight-shards/v6-failed.txt`、`docs/validation/newtask-v2/20260917-injection-refactor/existing-failures.log`。
- 可选处置：改测试、对齐官方行为（推荐，`tests/` 不受 P1、P2 约束：未知环境改断言 `[]`、改为 `back-and-forth`、对官方没有实现的两项标 `xfail` 并注明原因）／维持现状，继续在留档里写「既有失败」。

---

### C2 核心短测整体未维护（2026-10-02 新增，待定）

用户原话：「现在的短测问题非常多，没有维护过。把所有短测维护问题也写入待定。」「不要再每次都跑核心短测了，时间太长了。」以下为 2026-10-02 只读盘点（`tests/lightweight/` 98 个 `.py`，`pytest --collect-only` 1874 条）得到的问题清单，全部待定、本轮不改：

1. **耗时超预算**：`timeout 280s … -m 'not gpu and not slow'` 这条「核心短测」实跑 476.7 s（12.338 实测，1758 passed / 6 failed / 3 skipped / 80 deselected），280 s 限时在 85% 处被截断、拿不到汇总行；AGENTS.md 第 4 条「5 分钟内」的口径已不成立。候选：拆出一个 ≤ 2 分钟的「定稿核心集」（`test_v9_packaged_800`、`test_hard_builder_xhard0`、`test_xhard0_native`、`test_v9_*`、`test_upstream_*`）作日常门禁，其余标 `slow`。
2. **6 个长期失败未处理**（C1）：`test_TaskGoal.py` 2 条、`test_step_error_handling.py` 2 条、`test_v8_eval_report.py::test_zz_summary_line`、`test_v8_eval_video_mover.py::test_zz_summary_line`；自 `30f36e44` 起每次都失败，靠「与基线相同」放行。
3. **历史口径测试仍在跑**：`test_v7_*.py` 8 个文件（母布局派生、白名单语义、v7 seed 规则、v7 候选池、layered 录制、外环弧、BinFill 嵌套、v7 站点目录）测的是 V9 不再调用的 v7 链路；`tests/_shared/v7_specs_fixture.py`、`tests/fixtures/v7_specs_sample/` 只服务它们。
4. **用 monkeypatch 钉回 V8 格表才能过的用例**：`test_v8_delivery_flow.py::test_四片生成合并聚合43格`、`test_v8_eval_manifest.py` 三条（`test_夹具规模` 等）、`test_v8_regression_cmds.py::test_delivery_set三种格表往返[full]`——断言的是 1070／1262 的 V8 数字，与包内 V9（800／992）不符，靠 `monkeypatch.setattr(EXPECTED_CELLS, V8_CELLS)` 维持。
5. **文件名与内容错位**：`tests/_shared/v7_tier_values.py` 名字叫 v7、内容是 v8/v9 取值表，被 `test_v7_tier_values.py`、`test_v8_regression_cmds.py`、`test_sampling_config_split.py` 引用；`test_hard_builder_xhard0.py::test_逐任务局数常量合计1262` 函数名仍写 1262、实断 992。
6. **重叠断言**：`TIER_MAX_STEPS` 六档值在 `test_xhard0_native.py`、`test_v8_specs_schema.py`、`test_v9_packaged_800.py` 三处各断一遍；`EXPECTED_CELLS` 合计在 `test_xhard0_native.py`（`in (1070, 800)`）、`test_v8_specs_schema.py`、`test_hard_builder_xhard0.py`、`test_v9_packaged_800.py` 重复。
7. **收集范围**：不带 `tests` 参数时 pytest 会扫到 `third_party/` 并报 53 个收集错误（1932 条）；`tests/dataset/` 需要 MuJoCo／数据集，从未纳入日常口径。
8. **未验证的引用**：`tests/fixtures/injection_legacy/*.json` 在 `tests/` 内无引用方（`scripts/`、`src/` 未查）；`test_hard_state_machine.py`、`test_v4_xhard_stopcube.py`、`test_v5_xhard_patternlock_routestick.py`、`test_v5_xhard_videounmask_buttonunmask.py` 含 v7 字样、未逐条核对。

9. **12.341 新增的小缺口**（S2 审查 findings）：`hard_regression.py::cmd_xhard0_reset_parity` 关档时的 `SystemExit`、`export_eval_identities.py` 关档时 `official=skipped` 路径没有测试覆盖；`export_eval_identities.py` docstring／`--official-out` help 仍有「192 局」「V9 必须显式给」旧叙述。

**建议处置顺序**：先定 1（拆核心集、改 AGENTS.md 第 4 条覆盖项的命令），再清 2（修或删 6 个失败），3～5 随「旧代码去留」（用户 2026-10-02 已定本轮「代码不改了」）一并决定，6～8 顺手。全部待用户裁决。

## D 类：评估结果与预算

### D1 PickXtimes、StopCube、PickHighlight 两模型全 0 成功，未诊断

- V8（`artifacts/v8-evaluation/v8-two-policy-gl10-20261002-01/report/report.json` 的 `per_policy[*].cells`）：

  | 格 | 局数 | SimpleMemVLA 失败/timeout | MME-VLA 失败/timeout |
  |---|---|---|---|
  | PickXtimes xhard1 / 2 / 3 | 17 / 17 / 16 | 全失败 / 0 | 全失败 / 0 |
  | StopCube xhard1～5 | 各 10 | 全失败 / 0 | 全失败 / 0 |
  | PickHighlight xhard1 | 40 | 7 / 33 | 16 / 24 |
  | PickHighlight xhard2 | 40 | 4 / 36 | 12 / 28 |

- 失败局的步数（最小/中位/最大）：PickXtimes SimpleMemVLA 626/808/1031、MME 99/612/813；StopCube SimpleMemVLA 275/360/540、MME 215/276/480；PickHighlight SimpleMemVLA 319/634/1581、MME 215/459/1428。可见 PickXtimes 与 StopCube 是环境提前判失败，不是撞 1600 步上限；PickHighlight 多为跑满 1600 步。
- V9 这三个任务全部复用 V8 的局，结果相同（PickHighlight 每档 25 局）。V8 评估 `result.md`「遗留与说明」第 3 条已记录「未做额外诊断」。
- 诊断素材：无损录像 `artifacts/v8-evaluation/v8-two-policy-gl10-20261002-01/videos/<smvla|mme>/<tier>/<Task>/<Task>_<tier>_<seed>.a1/`（`front.mkv`、`wrist.mkv`、`summary.json`、`events.jsonl`）；网页用 mp4 在同运行目录的 `site-media/`。
- 待定：是否立项诊断（例如抽样查看失败时刻的事件与视频）。

### D2 V7.5 预算超额事后追认（2026-09-30）

- 判定行（`artifacts/v7.5eval/summary/verdicts.txt`）：`BUDGET_TOTAL=INFO trajectory_attempts=2151 cap=2271 over=no incident_infra_attempts=347 all_attempts=2498 attempts_over_items=5.2_金丝雀 retry_over_items=2.2_录制器验证,2.3_官方重跑两遍,3.1_跑通,5.1_换条件评估,5.2_正式跑法,5.2_金丝雀,其他_杀server测试 shared_retries=6 shared_retry_cap=2`

  | 项 | 实际 | 计划上限 |
  |---|---|---|
  | 全部尝试（含 0 步失败） | 2498 | 2271 |
  | 2.3 官方重跑 基础设施重试 | 93 | 12 |
  | 5.1 换条件评估 基础设施重试 | 156 | 12 |
  | 5.2 正式跑法 基础设施重试 | 108 | 8 |
  | 5.2 金丝雀 尝试 | 22 | 16 |
  | 共用重试 | 6 | 2 |

- 347 次 0 步失败来自 GPU 计算模式事故（`docs/validation/v7.5eval/incidents.md` 事故 6）。计划 §3.4 要求额度用完即标 `INFRA_EXHAUSTED` 停格，实际一直补跑到身份齐全。
- 出处：`docs/validation/v7.5eval/summary.md` §6、§7 第 2 条。待定：追认／不追认。

### D3 V8 评估各轮审查遗留的小问题（2026-10-02，均不阻断）

- E-B（`scripts/eval-official/run_v8_gl.sh` 与 `run_seat.sh`）：收尾时长可能超过 Slurm KillWait；重启计数只在内存里，不受持久账本约束。
- E-A（`scripts/eval-official/v8_manifest.py`）：模块 docstring 措辞未改；`write_outputs` 中途出错时不清理半成品。
- 计划写的收尾判定行 `V8_EVAL_CLEANUP=` 没有实现，实际输出的是 `V8_SEAT_DONE`。
- 证据：12.309～12.312 各合并提交 body 中的审查 findings。待定：是否开一个小修计划。

---

### D4 挑战接口 phase1_eval.py 四处缺陷（2026-10-04 测试重构 T8a 发现，先不修）

来源：维护计划第二步 T8a 写挑战接口测试（`tests/pipeline/challenge/`）时实测发现；T8a 在隔离副本里按下列修法改后 81 个非慢用例全过，说明缺陷可修、测试本身无误。

- **D4-1 成功判定按子串**：`_is_success` 写作 `s == "success" or ("success" in s and "fail" not in s)`，`unsuccessful`、`not_success`、`success_pending`、`partial_success` 都计为成功，成功率可能虚高。修法：`return s == "success"`（只会让成功数变少）。
- **D4-2 reset 等待永不重询**：`run_episode` 中 `while not resp.get("reset_finished"): time.sleep(0.1)` 从不重新调用 `client.reset()`，服务端首次回复未就绪即永久空转。修法：循环内重询并设次数上限，超限报错。
- **D4-3 异常时不 close**：单局抛异常时 `env.close()` 不执行（无 try/finally）。
- **D4-4 IK 失败崩溃**：`EndeffectorDemonstrationWrapper` IK 失败返回空观测 `{}` 加 `status=error`，`phase1_eval` 取 `obs["front_rgb_list"]` 报 KeyError，整个评估中止，而不是把该局记为 error。
- 另记（未立用例）：WebSocket 客户端 `PolicyClient.infer`／`reset` 无应用层超时，服务端挂住时只能等 `ping_timeout=100` s；`deploy.py` 顶层导入 `server_http`，缺 flask 时 websocket 模式也起不来。

现状：测试以 `known_defect_D<n>` 命名的用例锁定上述现状行为，契约清单对应条目（C14-10、C14-12、C14-13）记 `blocked` 并注明「用户 2026-10-04 裁决不修」。以后决定修时，改生产代码并把这些用例的断言反转即可。

**裁决**：2026-10-04「都不修」「先不休把这个作为之后的代定项。」

### D5 hard_builder 交出的 kwargs 与 builder 缓存共用对象（2026-10-04 测试重构收尾块 P 发现，本轮不修）

- 现象：`src/robomme_hard/env_record_wrapper/hard_builder.py::make_env_for_episode` 把 `lru_cache`（`_root_specs`）里的 `header["sampling_config"][task]` 与 `row["spec"]` 原对象直接作为 `sampling_config`、`native_episode_spec` 交给 `gym.make`。调用方（或环境）原地改动这两个对象，会污染同进程后续构建的同一局。规格侧环境内 `SpecRecorder` 会 deepcopy，有保护；`sampling_config` 没有。
- 影响面：生成与评估都是「每进程按身份构建」，现有产物未见受影响的证据；风险在于未来若有代码原地改 `sampling_config`，会造成同一 worker 内跨局串扰、且难以察觉。
- 修法：`make_env_for_episode` 交出 `copy.deepcopy(...)`。改 `src/robomme_hard` 属生成路径，修后需重跑第三步 GL 对拍（43 格 × 3 局 + 16 任务 × 1 档 × 3 局 = 177）确认生成字节不变。
- 现状：`tests/contract/test_builder_800.py::test_known_defect_builder_kwargs_aliased_to_builder_state` 锁定共用现状（改坏缓存后原地复原，不影响其他用例）；修复时反转断言。
- 裁决：2026-10-04 主会话按用户「不要再问我了尽可能一口气做到底」自行裁决本轮不修——GL 对拍正以当前生成代码运行，改动会使第三步结论不再对应最终代码。待用户早上决定是否修与是否随之重跑对拍。

## E 类：规则

### E1 「GL 上带 `--gpu_cmode=shared` 的步骤结束会把卡重置为独占」未写入规则（2026-09-30）

- 实测（gl1527）记在记忆 `/home/hongzefu/.claude/projects/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/memory/gl-gpu-cmode-step-end-reset.md`：
  - 带 `--gpu_cmode=shared` 的 srun 步骤开始时把卡设成 Default，结束时重置回 Exclusive_Process，即使同卡还有别的步骤在跑；
  - 后果：同卡任务下次建 CUDA／Vulkan 上下文时报 `createDeviceUnique: ErrorInitializationFailed`；
  - 做法：每席同一时刻只让干活的那个步骤带 shared，等待放在 srun 外；辅助 srun（查询、补暂存、rsync）一律不带 `--gpu_cmode`；急救用 `srun --overlap --gpu_cmode=shared sleep infinity` 保持步骤。
- 现状：规则正本 `/data/hongzefu/AgentMetaRules-hongzefu/greatlakes.md`、本仓库 `greatlakes.md`（`common-greatlakes` 副本块）、`docs/greatlakes.md` 都只有「需要第二个 CUDA context 时要带 shared」，没有上面几条。
- 建议写入位置：
  - 正本 `## job array、依赖链与节点排除（通用技巧）` 中「任何需要第二个 CUDA context……」那条之后；可选在 `## 算力使用规则` 的占位 job 条加一句「辅助 srun 不带 `--gpu_cmode`」。改正本后按 AGENTS.md 第 25 条用 `sync_rules.py` 回流，本仓库副本块不得手改；
  - 本仓库实测证据写入 `docs/greatlakes.md` 的 `## 一、GPU compute mode` 新子节与 `## 九、教训清单`，素材取 `docs/validation/v7.5eval/incidents.md` 事故 6。
- 出处：`docs/validation/v7.5eval/summary.md` §7 第 3 条。待定：是否写入。

---

## F 类：资源与清理

### F1 本机 5 个站点服务的去留

| tmux 会话 | 端口 | 服务 | 站点目录 | 说明 |
|---|---|---|---|---|
| `site-v12-8060` | 8060 | `v6_site.py` | `artifacts/newtask-v6/site-v12` | V6；启动脚本在已删除的临时目录，停掉后无法用原脚本重起 |
| `site-v7-8070` | 8070 | `v7_site.py` | `artifacts/newtask-v7/site-r11` | V7；启动脚本 `artifacts/newtask-v7/site-r11/launch.sh` |
| `site-v8beta-8080` | 8080 | `v8_site.py` | `artifacts/newtask-v8/beta/site` | V8 beta，BinFill xhard2 只有 39 局 |
| `site-v8-8081` | 8081 | `v8_site.py` | `artifacts/newtask-v8/site-eval` | V8 正式站（含评估） |
| `site-v9-8082` | 8082 | `v8_site.py --host 0.0.0.0 --port 8082 --site-dir artifacts/newtask-v9/site` | `artifacts/newtask-v9/site` | V9 站，日志 `artifacts/newtask-v9/logs/site-v9-8082.log` |

- 另有 `corlvis-site`（8051）不属于本仓库，不在本清单范围。
- 停服务只用 `tmux kill-session -t '=<会话名>'`，删前删后各 `tmux ls` 一次（AGENTS.md 第 7 条）。
- 依赖提醒：站点目录只放 JSON，媒体文件引用别处——8081 与 8082 依赖 `artifacts/v8-evaluation/v8-two-policy-gl10-20261002-01/site-media`、`artifacts/newtask-v7/site-media/xhard0-gen`、`artifacts/newtask-v8/gen1`、`artifacts/newtask-v8/xhard0-eval`；8082 另依赖 `artifacts/v9-evaluation/v9-two-policy-gl10-20261002-01/site-media`；8070 依赖 `artifacts/newtask-v7/` 下的 `gen1`、`eval-videos`、`eval-videos-official`、`site-media`。删这些产物会让对应站点失效。
- **裁决**：2026-10-02 用户「website 8082 是错的，它写的还是 V8，应该是 V9」→ 12.338 把 `v8_site.html` 可见文案改为 V9 口径并重启 8082（`V8_ORACLE_BROWSER=PASS cells=59`）。8080／8081 两个 V8 站的数据随 `newtask-v8` 在阶段 B 删除，届时停掉；只留 8082。
- **执行（2026-10-03）**：`site-v12-8060`、`site-v7-8070`、`site-v8beta-8080`、`site-v8-8081` 四个会话已逐个精确停掉，端口释放；8082 照常（`V9_SITE=PASS cells=59 eval_reused=720 eval_new=80`）（执行留档 `docs/validation/newtask-v9/cleanup-20261003.md`）。

### F2 8081／8082 站紫色「语义调整」小标签留不留

- 实现位置：`scripts/injection-dev/site/v8_site.html` 的 `.sem-tag` 样式（紫底白字）及整行淡紫底；逐局页 goal 列表与 subgoal 表里按 `semEp(...)` 结果追加 `node('span', 'sem-tag', '语义调整')`。
- 「语义调整合集」页（`renderSemanticAll()`）不受影响。8081 与 8082 共用同一页面，改动两站同时生效。

### F3 NFS 上 5 份代码克隆删不删

| 目录 | 体积 | HEAD | 用途 |
|---|---|---|---|
| `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-v8gen` | 9.5 G | 348c5a38 | V8 生成 |
| `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-v8eval` | 9.5 G | 047fa395 | V8 xhard0 评估 hard 路线 |
| `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-v8two` | 24 G | 6039a7af | V8 两模型评估（含三套 venv，可复跑） |
| `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-v9gen` | 9.5 G | b462e358 | V9 生成 |
| `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-v9two` | 24 G | 820ca142 | V9 两模型评估 |

- 五份工作区都干净。另有 V7 期的小目录：`v7`、`v7-eval`、`v7-eval-stage`、`v7-logs`、`v7-scripts`、`v7-stage`（1.4 G）、`SimpleMemVLA-official-xhard0`（111 M）、`robomme_policy_learning-official-xhard0`（27 M）、`robomme_policy_learning-testhard-v7`。
- 建议：若 A1 选 (b) 需要在 GL 上重新生成和评估，保留 `v9gen`、`v9two`；其余可删。删除按显式路径，先 `ls -ld` 核对。
- **裁决（部分）**：2026-10-02 用户选「删除 `robomme_benchmark-newtask-gl/artifacts/train-parity` 651 GB」；克隆的源码与在途改动不动，其余克隆仍待定。执行在阶段 B。
- **执行（2026-10-03）**：`robomme_benchmark-v8gen`、`-v8eval`、`-v8two`、`v7`、三份官方检出、`newtask-v4-gl`、`slurm-holds`、`hs-scripts`、`hs-xhw-probe-20260927`（4 个结果文件先抄进 `docs/validation/newtask-v6/hard-split/records/xhw-probe/`）、`hs-logs`，以及 `train-parity` 非 compare 子树等共 747 条移入隔离区后删除；`v9gen`、`v9two` 及 xhard0 相关目录保留（执行留档 `docs/validation/newtask-v9/cleanup-20261003.md`）。

### F4 本机大产物保留策略（`/data` 共 14 T，剩 3.2 T）

| 目录 | 体积 | 组成 |
|---|---|---|
| `artifacts/newtask-v7` | 971 G | gen1 772 G、parity 180 G、smoke 9.1 G、eval-videos 5.6 G、smoke-swap 3.6 G |
| `artifacts/newtask-v8` | 618 G | gen1 618 G（V9 delivery 有 720 局 hardlink 指向它，见 B4） |
| `artifacts/v8-evaluation` | 257 G | 两模型无损录像 |
| `artifacts/v7.5eval` | 120 G | v7.5 评估 |
| `artifacts/newtask-v9` | 实占 47 G | delivery 名义 436 G（多为 hardlink）、parity 23 G（含 A1 的 H2 副本） |
| `artifacts/newtask-v6` | 35 G | v6-02 29 G、v1 4.8 G |
| `artifacts/v9-evaluation` | 29 G | 新 80 局录像 |

- 用户 2026-09-24 定的规则是「收尾只保留最终产物」：对拍 h5（如 `artifacts/newtask-v7/parity` 180 G）与冒烟产物属可删。但 A1、A2 未定前，V9、V7 的对拍 h5 是证据，建议裁决后再删。8070 站依赖 V7 的 gen1 与 eval-videos。
- **裁决**：2026-10-02 用户「历史的产物也要清理……只需要保留最新版本 V9 的生成的 H5 文件和评估的文件，需要上传 HuggingFace」；清单（`newtask-v6`、`newtask-v7`、`newtask-v8`、`v7.5eval`、`v8-evaluation`、`branch-alignment`、`v8-probe`、`eval-reload-20260929`、`train-parity`）已认可，`newtask-v9/parity` 23 G 保留，HF 上传下轮单独做。执行在阶段 B。
- **执行（2026-10-03）**：按 `1003-resource-cleanup-plan.md` 终版（V9 及其来源、xhard0、全部比对记录原地保留）本机移走 2190 条后删除；HF 只删 `_probe/bucket-probe.txt`。V9 交付集与评估在本机仍是唯一副本（执行留档 `docs/validation/newtask-v9/cleanup-20261003.md`）。
- **HF 上传（2026-10-03 晚）**：按 `1003-hf-v9-publish-plan.md`，V9 交付集（`16 任务 × 50 局 = 800` 局的 h5、mp4 与索引，外加三份清单，共 1604 个对象）已上传到公开 bucket `HongzeFu/robomme-hard-v9`，逐对象读回 sha 全等；旧 bucket `HongzeFu/robomme-hard-parity` 已整删，其他 16 个 bucket 不变（执行留档 `docs/validation/newtask-v9/hf-20261003.md`）。V9 评估录像与报告仍只在本机。

### F5 09-28 拆包（hard-split）会话遗留（已基本清理）

- 当时留给用户的三件事：本机三侧 h5（258 G，已备份到公开 bucket `HongzeFu/robomme-hard-parity`，762 个对象 383 G）删不删；NFS `robomme_benchmark-hs-gl`（8.4 G）与 MME 官方检出（18 G）删不删；容差阈值审核。
- 2026-10-02 复核：本机 `artifacts/newtask-v6/hard-split` 只剩 3.2 M，未见三侧 h5；NFS 上未见 `robomme_benchmark-hs-gl`。前两件已不存在，第三件即 A5。建议本条结案。

### F6 本地未推送分支与旧 worktree

- 只在本地、没有远端的分支：
  - `newtaskRelease-v6`：10-01 由助手自建，内容是 V8 方案草稿，名字与内容不符；
  - `v7-impl`：V7 实施时的 worktree 分支。
- worktree：
  - `.claude/worktrees/v7`（分支 `v7-impl`）与 `/data/hongzefu/v6-draft/` 下的 `movecube`、`pipeline`、`swap`、`vp`（分支 `v6-draft-*`）——仓库 `CLAUDE.md` 把它们列为「在用 worktree，不动」，需用户确认是否仍在用；
  - `/tmp/claude-114466650/` 下的 `baseline-wt`（detached `504daee5`），由另一会话建立。
- 待定：推送、删除还是保留。删除 worktree 用 `git worktree remove`，删分支只用 `git branch -d`。
- **执行（2026-10-03）**：`.claude/worktrees/v7` 在关闭其中的闲置进程（PID 2006672，用户同意关闭）后被宿主连同 `v7-impl` 分支自动清掉，分支已按原 sha `cd09b014` 补回；`v6-draft/{swap,vp}` 与 `baseline-wt` 已删；`v6-draft/{movecube,pipeline}` 经用户授权后补删；分支全部保留（执行留档 `docs/validation/newtask-v9/cleanup-20261003.md`）。

---

## G 类：代码小遗留

### G1 `_freeze.py` 的 /2、/3 档位预检读全局 `TIERS`

- 位置：`scripts/injection-dev/_freeze.py::freeze` 中 `if difficulty not in (hard_specs.V8_TIERS if v8 else hard_specs.TIERS)`（提交 `1fa5f15e` 引入，注释写「与其校验分支一致」）。
- 3b 换包后全局 `TIERS` 含 xhard5，/2、/3（V6、V7 格式）的预检会放行 xhard5；之后 `validate_specs` 用冻结的 `V7_TIERS` 再拒绝，所以不会产出错误规格，只是报错时机晚、文案不同。V8、V9（/4）不受影响。
- 修法：把 `hard_specs.TIERS` 改为 `hard_specs.V7_TIERS` 并同步改注释。待定：是否顺手修。

### G2 V8 补抽统计口径 35 与 44 不一致

- `delivery-set` 按规格行角色统计为 `backfills=35`，聚合行按账本统计为 44（含补抽新候选与跨轮递补）。`docs/validation/newtask-v8/result.md` ③已注明「不影响判定」。
- 建议结案。

---

## H 类：其他（建议直接结案）

- **H1** 10-01 本机测速：本机比 GL 快约 1.9 倍，稳态约 2.5 倍（样本 8 局）。当时问是否转发到「CladeAgent 子任务分解与合并策略」会话，未答复；该会话已结束，建议结案。
- **H2** 10-02 上午「10 卡评 xhard1～4 每格 10 局」耗时估算的简化算式有笔误：「410 × 96 ≈ 39250」实为 39360，「410 × 29 ≈ 12060」实为 11890；最终约 1 小时 40 分的结论不变。记录更正即可。
- **H3** V8 评估第一次冒烟有两局 `ModuleNotFoundError: openpi_client`（执行副本漏装依赖组），被记为非基础设施错误；按口径应属基础设施，但未改分类逻辑，只留档（`docs/validation/v8-two-policy-gl10-20261002-01/result.md`「遗留与说明」第 2 条）。建议结案或并入 D3。
