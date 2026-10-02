# newtask v8 运行档案：result

计划：根目录 `1001-newtask-v8-xhard-gradient-plan.md`；起跑档案见同目录 `launch.md`。本文件记录实测判定行与结论，判定行一律原文内联。

## ① 一句话结论

v8 交付集 **1070 局**（16 任务 × 43 格；含 xhard0 共 1262 局）已生成、通过全部交付闸门并换入包内规格；执行步全集最大 1479（上限 1600，抽样阶段因超限被过滤的候选为 0）；正式逐局站点 http://sled-vail.eecs.umich.edu:8081/ 经 P4 严格链路建成；beta 站 http://sled-vail.eecs.umich.edu:8080/ 按用户要求保留原状。二次生成对拍 `PARITY_H_H2=PASS`（1070 局：逐字节相同 1058、噪声 12、H2 失败 0、成败相反 0）；xhard0 两路线评估 768 局全部取得终态（只报告：SimpleMemVLA 两路线成败逐局一致，MME-VLA 18 局翻转）。7 个 GL 占位 job 已按清单释放。

## ② 版本与代码状态

| 内容 | 提交 |
|---|---|
| 阶段 1（S1-A 改值环境、S1-B 删 V6） | 12.291 `2a6338ec`、12.292 `047fa395` |
| 阶段 1 闸门与 launch.md | 12.293 `e377f6c9` |
| 阶段 2（S2-A hard_specs v8、S2-B 抽签生成、S2-C 守卫、S4-A 站点、S2-D 接续链路） | 12.294 `28b76699`、12.295 `48857961`、12.296 `bcb6719b`、12.297 `348c5a38`、12.298 `ae5b8576` |
| 计划外追加 S3-SUP（BinFill xhard2 补抽工具） | 12.299 `1a7d1442`（另一会话的 `e7998958` 同号 12.299，撞号已记录） |
| 站点撤下任务页对比表 | 12.300 `f9ba91eb` |
| 阶段 3b 换包（S3b） | 12.301 `3d516a52` |
| 换包闸门与 README 修正 | 12.302 `7189d56e` |

- 生成与二次生成代码：NFS 冻结克隆 `robomme_benchmark-v8gen` @ `348c5a38`（工作区始终干净；`348c5a38..ae5b8576` 之间生成链路代码零 diff，只新增本机接续脚本）。
- xhard0 评估（3′）hard 路线代码：NFS 克隆 `robomme_benchmark-v8eval` @ `047fa395`（阶段 1 合入后）。
- 所有 gen1 launch 记录：`gpu_model=NVIDIA A40`、`driver=595.71.05`、`src_commit=348c5a38`（四片初跑 + 片 2 补抽续跑共 5 份，留证于 `artifacts/newtask-v8/parity/h5/H-v8/shard*-launch-*.json`）。

## ③ 判定行速览

| 阶段 | 判定行 |
|---|---|
| 1 | `XHARD0_IDENTITY=PASS shape=16x1x12 identities=192 missing=0 extra=0` |
| 1 | `XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0 name_only=12 first_det_diff=- name_only_tasks=['ButtonUnmaskSwap']` |
| 2b | `V8_DELIVERY_SET=PASS tasks=6 cells=7 total=7 expected=7 failed=0 exec_over_cap=0 backfills=0 infra_retries=0 exhausted_cells=0 pending_cells=0 bad_h5=0` |
| 3 | `V8_DELIVERY_SET=PASS tasks=16 cells=43 total=1070 expected_cells=43 expected_total=1070 cell_mismatch=0 extra_cells=0 selected_not_ok=0 delivered_over_cap=0 failed=44 exec_over_cap=0 backfills=35 missing_files=0 load_errors=0` |
| 3 | `V8_SEED_DISJOINT=PASS tasks=16 tier_pairs=48 shared=0` |
| 3 | `V8_LAYOUT_INDEPENDENT=PASS files=5 delivered=1070 parent_non_null=0 layout_equal_pairs=0 mode_bad=0 no_position=0 load_errors=0` |
| 3 | `V8_TIER_VALUES=PASS tasks=14 cells=41 mismatches=0 rows=1030 missing_files=0 source=delivered` |
| 3 | `V8_STEP_CAP=PASS max=1479 cap=1600 over=0 filtered=0 xhard0_max=1074 xhard0_cap=1300 rows=1070 cells=43 missing_h5=0 exec_steps_mismatch=0` |
| 3b | `V8_RESET_REPLAY=PASS shape=cells43 resets=43 replay=43 injected_mismatch=0 layout_drift=0 unused=0 layout_hit_bad=0 errors=0` |
| 3b | `XHARD0_RESET_PARITY=PASS shape=16x1x12 compared=192 det_diff=0 name_only=12 first_det_diff=-`；`XHARD0_IDENTITY=PASS shape=16x1x12 identities=192` |
| 3b | `HARD_EVAL_SMOKE=PASS task=SwingXtimes episode=0 tier=xhard0 seed=530300 episodes=62 max_steps=1300`；`HARD_EVAL_SMOKE=PASS task=SwingXtimes episode=52 tier=xhard5 seed=24300001 episodes=62 max_steps=1600` |
| 每阶段 | `UPSTREAM_GUARD=PASS`；录像器零 diff；`scripts/*.py` 恰 4 个；核心短测失败集合恒等于 BASE 既有 4 个 |
| 4 | `V8_SITE=PASS sections=15 eval_placeholders=150 eval_filter_hits=0 eval_media_requests=0 subgoal_missing=0 config_mismatch=0 cells=59 played=59 fail_badges=0 page_errors=0` |
| 4 | `V8_ORACLE_BROWSER=PASS cells=59 missing=0 mismatch=0 page_errors=0` |
| 4 | `V8_CONTINUE=PASS step=done steps=12 site=built delivered=1070 filtered=0 exec_over_cap=0 backfills=44 infra_retries=0`；`P4_WATCHDOG=DONE verdict=PASS` |
| 4 | `PARITY_H_H2=PASS tier=v8 compared=1070 cells=43 missing=0 extra=0 duplicate=0 identity_equal=1070 byte_equal=1058 noise=12 h2_fail=0 flipped=0 structural=0`（全行见 ⑦） |
| 3′ | `XHARD0_EVAL_PARITY=INFO policy=simplememvla compared=192 status_diff=0 steps_diff=15`；`XHARD0_EVAL_PARITY=INFO policy=mmevla compared=192 status_diff=18 steps_diff=115` |

`backfills` 两个口径：`delivery-set` 按规格行角色统计为 35，聚合行按账本统计为 44（含补抽新候选与跨轮递补），不影响判定。

## ④ gen1 逐片结果（16 任务 × 43 格；4 席 × 4 worker）

| 片 | 任务 | 交付／配额 | 试跑 | 生成失败（已递补） | 判定 |
|---|---|---|---|---|---|
| 1 | VideoPlaceButton、PickHighlight、MoveCube | 180/180 | 185 | 5 | PASS（82 分钟） |
| 2 | BinFill、VideoUnmaskSwap、VideoPlaceOrder | 240/240 | 268 | 28 | 首跑 239/240 FAIL（BinFill xhard2 备用耗尽）→ 补抽后 PASS |
| 3 | PickXtimes、ButtonUnmask、VideoRepick、InsertPeg、RouteStick | 310/310 | 319 | 9 | PASS（135 分钟） |
| 4 | StopCube、SwingXtimes、VideoUnmask、ButtonUnmaskSwap、PatternLock | 340/340 | 342 | 2 | PASS（103 分钟） |
| 合计 | | **1070/1070** | **1114** | **44** | 超限（> 1600）过滤 **0**；基础设施重试 0 |

失败明细：BinFill xhard2 18/57、BinFill xhard1 7/47（全部 `DatasetGenerationError: environment reported failure`）；InsertPeg xhard4 9/29、MoveCube xhard4 3/23（`did not succeed after the complete task_list`）；VideoPlaceButton xhard2 2/42、VideoPlaceOrder 2/42 + 1/41（任务未成功与 `PlannerExhausted`）；ButtonUnmaskSwap xhard1/2 各 1/41（`BinCollisionError`）；其余 32 格 0 失败。

**BinFill xhard2 补抽（计划外，用户当场批准）**：冻结 57 候选、配额 40，失败 18、备用耗尽交付 39。计划 §2.4.5 预定动作是「不补抽、该格 FAIL」；运行中向用户提问，用户选择「补抽到 40（推荐）」（reset ≤ 30、rollout ≤ 10）。新写 `scripts/injection-dev/append_candidates.py`（S3-SUP，审查 PASS），在 GL 上以冻结克隆代码追加 10 个候选：`APPEND_DRAW tried=10 ok=10 shortfall=0`、`APPEND_CANDIDATES=PASS cell=BinFill@xhard2 extra=10 per_env=57→67 frozen_identity=35fb643d3805 backfill_selected=1 shards_updated=4`；片 2 续跑 1 局即成功：`V8_DELIVERY_SET=PASS tasks=3 cells=6 total=240`。

## ⑤ 档位取值与分布

`V8_TIER_VALUES=PASS tasks=14 cells=41 mismatches=0`。区间任务的逐格分布（计划 §2.8 第 23 条要求 PatternLock 生成后报分布）：

| 格 | 区间 | 分布（值:局数） |
|---|---|---|
| PatternLock xhard1 | [9,12] | 9:7、10:3、11:6、12:11 |
| PatternLock xhard2 | [13,15] | 13:6、14:11、15:10 |
| PatternLock xhard3 | [16,18] | 16:9、17:6、18:11 |
| RouteStick xhard1 | [8,10] | 8:5、9:10、10:12 |
| RouteStick xhard2 | [11,13] | 11:11、12:5、13:11 |
| RouteStick xhard3 | [14,16] | 14:4、15:12、16:10 |

Task goal 逐局核对（PickXtimes／SwingXtimes／StopCube 全部交付局、每局 2 种措辞）：goal 中的次数／序数词与规格 `num_repeats`／`stop_time` 全部一致，`TASKGOAL_COUNT_CHECK=PASS bad=0`。

## ⑥ 执行步

全集最大 1479（BinFill xhard2），上限 1600，余量 121；xhard0 最大 1074（上限 1300）。执行步最长的格：BinFill xhard2 max 1479／mean 1350、PickXtimes xhard2 max 1449、PickXtimes xhard3（抓 8 次）max 1430／mean 1248、BinFill xhard1 max 1430、PickXtimes xhard1 max 1262、PickHighlight xhard2 max 1145。计划盲区「PickXtimes 8 次原区域内超限比例未知」：本次 16 局 0 超限。

## ⑦ 二次生成对拍（阶段 4）

H2 与 gen1 同码（冻结克隆 `348c5a38`）、同卡型（A40，驱动 595.71.05），只回放 gen1 已交付的 1070 个身份、不递补。按用户「先完成的片把席位让给后续工作」的要求，每片 gen1 一结束就在本席位起该片 H2（片 1 22:09、片 4 22:19、片 2 前 239 局 22:49、片 3 22:51；BinFill xhard2 补出的 1 局另起 `shard2b` 回放）：

| 子目录 | 判定 |
|---|---|
| shard1 | `GENERATE=PASS side=H2 tier=v8 rows=180 recorded=180 success=180 runner_exit=0 gpu=NVIDIA A40 mover_errors=0` |
| shard2 | `GENERATE=PASS … rows=239 recorded=239 success=239` |
| shard2b | `H2_SHARD_DONE shard=2b rc=0`（1 局） |
| shard3 | `GENERATE=PASS … rows=310 recorded=310 success=310` |
| shard4 | `GENERATE=PASS … rows=340 recorded=340 success=340` |

合并身份：`H2_COMBINE=PASS rows=1070 dup_dropped=0 missing=0 extra=0 no_path=0`。H 侧登记（本机 delivery.local.json）：`IMPORT_DELIVERY=PASS tier=v8 rows=1070 sha_mismatch=0`；两侧自检 `SIDE_SELF_CHECK=PASS side=H/H2 tier=v8 problems=0`。比对（本机读 H，NFS 读 H2，16 worker）：

```
PARITY_H_H2=PASS tier=v8 compared=1070 cells=43 missing=0 extra=0 duplicate=0 identity_equal=1070 byte_equal=1058 noise=12 h2_fail=0 flipped=0 structural=0 expected=1070 frozen=1070 delivery=1070 left_rows=1070 right_rows=1070 shape=cells43:411+411+128+100+20 setup_equal=1070 schema_equal=1070 success_equal=1070 both_success=1070 both_fail=0 noise_first_divergence_min=63 tol_over=0 tol_noise=12 over_total=12 hard_line_5pct=ok action_max=3.44/0.0413 state_max=3.43/0.0411 image_mad=8.3/1 frames_max=33/5 sha_equal=1058 frames_equal=1058 binding_ok=1070 recovery_mismatch=0
```

五个互斥终态（§2.2 第 11 条）：逐字节相同 1058、噪声 12（身份、setup、schema、成败相同，最早分叉第 63 步，超容差 12 局 ≤ 5% 硬线）、H2 失败 0、成败相反 0、结构错误 0，合计 1070。对照 v7（1100 局中 1086 逐字节、13 噪声、1 局 H2 失败致 FAIL），v8 无 H2 失败。

## ⑧ xhard0 评估（3′，只报告）

16 任务 × 1 档 × 12 局 × 2 策略 × 2 路线 = 768 局，评估席 63003486／63003487，编排器 `ORCH_DONE verdict=PASS total=40 blocking_fail=0 done=40 fail=0`（2026-10-01 19:13 → 2026-10-02 02:00）；40 步报告全部 `final=expect`，基础设施续跑 0 次。

| 策略 | 官方路线（1fadc0ec） | hard 路线（v8eval 047fa395） | 对拍（只报告） |
|---|---|---|---|
| SimpleMemVLA | 141/192 = 73.4%（fail 36、timeout 15） | 141/192 = 73.4%（fail 36、timeout 15） | `XHARD0_EVAL_PARITY=INFO policy=simplememvla compared=192 status_diff=0 steps_diff=15` |
| MME-VLA | 48/192 = 25.0% | 50/192 = 26.0% | `XHARD0_EVAL_PARITY=INFO policy=mmevla compared=192 status_diff=18 steps_diff=115` |

v7 参考：SimpleMemVLA 0／16，MME-VLA 11／71。MME 同入口同卡重跑即有翻转（v7 11 局 5 翻），差异不判回归；「v8 没改坏 xhard0」由确定性的 `XHARD0_RESET_PARITY=PASS det_diff=0`（阶段 1 与 3b 各一次）证明。逐局差异：`records/xhard0-eval-parity-{simplememvla,mmevla}.jsonl`；原始结果拷回 `artifacts/newtask-v8/xhard0-eval/`。

## ⑨ 用户决策记录（本轮实施期间，按时间）

1. 「…1001-newtask-v8-xhard-gradient-plan.md 开始实施 可以问用户问题但不得中断 一路跑到底」
2. 「如果reset预算不够可以在10倍内扩张」——冻结 reset 停止上限逐格合计 2,899（预算表「约 2,850」），按此授权照用；实际 1,683 次。
3. 「现在坐到哪里了」「（阶段表）这些什么时候开跑」「跑完大概需要多久第一次生成和第二次生成。」——进度询问，已答。
4. 「生成的ground truth的回放视频会保存吗?」「或者通过H5的派生也可以。」「好的保留的视频继续保留视频是否可以做到一边生成一边传回本机或者说在传回本机的过程中不阻扰后面的工作」——视频随 h5 保留；起 4 路并行增量回传，不阻塞 H2 与换包。
5. 「第一次完成，开始建网站还需要多久」「gen1 完成后、开始建站还要多久 查清楚了吗？？？？」——已答（瓶颈是 NFS 回传，改 4 路并行）。
6. 「分片完成了有部分片完成了之后你可以把其他片的内容分担给另外的片码。」——在跑的 gen1 片无法中途迁移；改为先完成的片在自己席位上立即起该片 H2。
7. BinFill xhard2 39/40 时提问，用户选择「补抽到 40（推荐）」。
8. 「先不管增量 先建一个beta网站」「暂时停止所有其他的工作正在进行的后台就不用管了先把网站给我」——beta 站 http://sled-vail.eecs.umich.edu:8080/（1069 局，BinFill xhard2 39 局，只在 beta 启动包装中放宽该格校验）。
9. 「你现在的4片是什么情况各生成了多少有哪些生成失败」——已答（④）。
10. 「你的Taskgoal都更新了吗?」——已逐局核对（⑤）。
11. 「每个页面的这个表格不要再显示了。太占位置」——任务页撤下各档对比表（12.300），只在「各档总表」页保留。
12. 「你可以继续工作了一口气把所有工作都做完。贝塔站保留原状之后的站用之后的域名来实现。」——正式站挂 8081，beta 8080 不动。

## ⑩ 计划外事件与处置

- BinFill xhard2 备用耗尽 → 用户批准补抽（④）。
- 首次 beta catalog 被 S2-A 的严格配额绑定拒绝 → beta 专用启动包装 `artifacts/newtask-v8/beta-scripts/beta_relaxed.py`（不进 git）只放宽该格。
- 单路回传实测仅约 27 MB/s（NFS 同时被 4 席写入）→ 改 4 路并行，每路限速 40 MB/s，合计约 100 MB/s。
- 回注回放首次把 `--out` 给成目录（`IsADirectoryError`，0 次 reset 消耗）→ 改文件路径重跑通过。
- 版本号撞号：另一会话提交 `e7998958`（12.299 规划 V8 收尾后的双模型十卡评估）与本会话 `1a7d1442` 同为 12.299，均已推送不改历史，之后从 12.300 接续。
- 核心短测全量超过 290 s → 按文件对半两进程并行（墙钟约 212 s），失败集合合并后核对。
- 审查 FAIL 后续改：S2-A（配额未与格表绑定）、S2-C（位置指纹查不出前缀照抄）、S2-D（续行旧心跳误判、孤儿进程组），均一轮修好。

## ⑪ 结论与下一步

- 计划 §3 验收表全部判定行达成：阶段 1、2b、3、3b、4 的闸门全 PASS，3′ 两条 INFO 已出。
- 预算实耗（P3 / P5 乘式）：
  - reset：xhard0 环境层对拍 16 任务 × 1 档 × 12 局 × 2 侧 × 2 次运行 = 768；冒烟冻结 8 次抽签；阶段 3 冻结抽签 1,683（停止上限 2,899，按用户 10 倍扩张授权）；补抽 10；回注回放 43 格 × 1 = 43；评估冒烟 2；gen1 / H2 / 3′ 每局各含 1 次 reset（1114 + 1070 + 768）。
  - rollout：冒烟 7 格 × 1 = 7；gen1 1114（首轮 1070 + 递补 44，含补抽 1）；H2 1070；评估冒烟 2；3′ 768。均在批准上限内（rollout 上限 3,272）。
- 收尾清理：NFS 上 gen1（481 GB，本机副本已逐个核 sha256）、H2 对拍副本（480 GB）、冒烟（2.9 GB）、评估结果目录按显式路径删除；评估结果先拷回本机。本机保留正式局 h5 + 视频 + 规格（`artifacts/newtask-v8/gen1`、`specs-root`）、正式站与 beta 站、闸门日志。
- 7 个 GL 占位 job 已于 2026-10-02 02:33 按清单逐个 scancel（R11）。
- 站点：正式站 http://sled-vail.eecs.umich.edu:8081/（tmux `site-v8-8081`）；beta 站 http://sled-vail.eecs.umich.edu:8080/（tmux `site-v8beta-8080`，用户要求保留原状）。
- 遗留：`scripts/injection-dev/_freeze.py` 的 /2、/3 档位预检仍读全局 `TIERS`（S3b 报告未解决事项 1，现由 validate_specs 兜底）；`scripts/README.md` 第 3 节长度表仍是 v7 数值（已标注）；`test_TaskGoal.py` 2 个与 `test_step_error_handling.py` 2 个测试在 BASE 就失败，未处理。

## ⑫ 归档文件清单

- 运行产物（不进 git）：`artifacts/newtask-v8/`（gen1 h5+视频、规格根、delivery.local.json、站点、beta、闸门日志、parity 登记）。
- 判定行均已内联于本文件；接续链路逐步报告 `artifacts/newtask-v8/continue/work/report.json`。
