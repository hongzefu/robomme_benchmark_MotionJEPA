# newtask v9 运行档案：result（验收后写）

计划：根目录 `1002-newtask-v9-movecube-region-800-plan.md`；起跑记录见同目录 `launch.md`；各阶段判定行原文见 `records/gates.txt`。双模型评估另见 `docs/validation/v9-two-policy-gl10-20261002-01/`。

## ① 一句话结论与指标速览

V9 交付集 800 局（16 任务 × 每任务 50 局，xhard1～5 共 43 格；另 xhard0 16 任务 × 1 档 × 12 局 = 192 沿用 V8）已生成、整合并进包（12.333 `820ca142`）：其中 720 局逐字节复用 V8（14 任务 700 局 + InsertPeg 20 局），新生成 80 局（MoveCube 1 任务 × 1 档 × 50 + InsertPeg 1 任务 × 1 档 × 30）。全部交付闸门 PASS；新 80 局的二次生成对拍 `PARITY_H_H2=FAIL`（72 逐字节相同、7 noise、1 h2_fail，超容差 8.75% 越过 5% 线），按计划不阻断交付、交用户裁决。

| 判定 | 结果 |
|---|---|
| `V9_MOVECUBE_REGION` | S1-A 定向 114 passed；区域三值 0.24／0.42／[0.31,0.80]；离线 2000 段见计划 §2 |
| `V9_CELLS` | PASS cells=43 total=800 per_task=50 |
| `XHARD0_RESET_PARITY`（1b／3b） | 两次 PASS shape=16x1x12 compared=192 det_diff=0 name_only=12 |
| `V9_INSERTPEG_EXTEND` | PASS imported_ok=20 imported_fail=9 spares=11 appended=35 quota=50 |
| `V9_MOVECUBE_LAYOUT` | PASS episodes=50 in_region=300 outside_old=300 region_mismatch=0 |
| `V9_MOVECUBE_WAYS` | PASS ways=17/17/16 |
| `V9_SUBSET` | PASS reused=720 spec_equal=720 h5_equal=720 video_equal=720（h5 全量重算） |
| `V9_ASSEMBLE` | PASS rows=800 reused=720 new=80 cells=43 |
| `V9_DELIVERY_SET` | PASS tasks=16 cells=43 total=800 new=80 reused=720 |
| `V9_STEP_CAP` | PASS max=1469 cap=1600 over=0；xhard0 最大 1074 ≤ 1300 |
| `V9_RESET_REPLAY` | PASS shape=cells43 resets=43 replay=43 injected_mismatch=0 layout_drift=0 spec_bound=43 |
| `UPSTREAM_GUARD`／录像器／四入口 | 每次合并与换包后 PASS／零 diff／4 |
| 核心短测 | 换包后 1754 passed、6 failed（6 个在 BASE `30f36e44` 即失败，见 ⑩） |
| `PARITY_H_H2` | **FAIL** compared=80 byte_equal=72 noise=7 h2_fail=1 flipped=0 structural=0 hard_line_5pct=HIT（交用户） |
| `V9_SEMANTIC` | PASS tasks=16 cells=43 changed=17 param_only=26 note_missing=0（`v8_semantic_diff.py` 行名 V8_SEMANTIC） |
| `V9_SITE` | PASS cells=59 missing=0 eval_reused=720 eval_new=80 eval_empty=0 port=8082；`V8_SITE=PASS cells=59 played=59 eval_played=118 semantic_mismatch=0 page_errors=0`；`V8_ORACLE_BROWSER=PASS cells=59`；8081 的 V8 站复检 `V8_SITE=PASS`、V8 site-eval 无新改动文件 |
| 双模型评估（另档） | `V9_EVAL_COVERAGE`／`V9_EVAL_REPORT total=800 new=80 reused=720`／`V9_EVAL_VIDEOS expected=160` 均 PASS；800 局 SimpleMemVLA 22.3%、MME-VLA 4.9% |

## ② 版本与代码状态

阶段 1：12.325 S1-A `8b9726c0`、12.326 S1-B `0ec11702`、12.327 主会话配合 `fa1d856c`。阶段 2：12.328 S1-E `33be4f8c`、12.329 S1-F `203399aa`、12.330 S1-D `e9f247b1`、12.331 S1-C `d121ee52`。阶段 3 冻结点 12.332 `b462e358`（生成全部在此 sha 上跑）。换包 12.333 `820ca142`。子代理提交均以 `sub/S1-X: ` 前缀经 `--no-ff` 合入、原样保留；每块合并前一轮只读审查 `PRE_MERGE_REVIEW=PASS`（S1-A 续改一次补守门测试，S1-F 续改一次补视频判定行），合并后 `POST_MERGE_REVIEW=PASS`。

## ③ 启动与配置还原

命令逐字见 `launch.md` §五；env 覆盖：GL 脚本 `ROBOMME_ENV_PACKAGE=robomme_hard OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1`，解释器为 NFS 克隆 `robomme_benchmark-v9gen/.venv`；本机 InsertPeg extend 与 3b 闸门用主检出 `uv run --no-sync`，GPU 以 `CUDA_VISIBLE_DEVICES` 指定。

## ④ 数据集与划分口径

表 2（计划 §3）：每任务 50 局，在 V8 交付档里平分；子集任务取 V8 交付行候选号最小的 N 个（6 格因 V8 递补而与 `select_rule[:N]` 不同：BinFill xhard1／2、VideoPlaceOrder xhard1／2、VideoPlaceButton xhard2、InsertPeg）。seed 沿用 `seed_rule_for(tier, "v8")`；V9 MoveCube 与 V8 MoveCube 同 seed 不同布局，靠 `spec_sha256` 区分（R-3）。

## ⑤ 关键参数

MoveCube xhard4 区域 r_in 0.24、r_out 0.42、base_dist [0.31, 0.80]（圆心 (−0.06, 0)，其余键不变）；MoveCube 候选 80、逐方式硬配额 17／17／16、同方式递补；InsertPeg 配额 20→50、候选 29～74；执行步上限 1600。

## ⑥ 硬件与耗时

GL spgpu A40 × 4 席（63107829～63107832，gl1527／gl1512），每席 4 CPU／48 G／shared。MoveCube 冻结 80 候选约 2 分钟（16:54～16:57），生成 3 轮 474＋120＋54 s；InsertPeg extend 抽签 35 个约 1 分钟（本机 GPU 1），生成 4 轮 351＋138＋65＋53 s；H2 两片约 10 分钟。本机 3b：verify --rehash-h5 约 5 分钟，reset-replay 约 3 分钟（GPU 1），xhard0 对拍约 15 分钟（GPU 0），核心短测每次约 490 s。

## ⑦ 生成过程行为

| 片 | 尝试 | 成功 | 失败 | 失败率 | 交付 |
|---|---|---|---|---|---|
| MoveCube xhard4 | 63（首轮 50 + 同方式递补 13） | 50 | 13 | 20.6% | 50 |
| InsertPeg xhard4 新候选 | 46（29～74 全部） | 30 | 16 | 34.8% | 30（+ V8 20） |

MoveCube 失败率 20.6%，低于计划预留的 35%，也未出现贴边导致的候选耗尽；三种运动方式候选 27／25／28，交付 17／17／16。InsertPeg 新候选恰好全部用上（无剩余备用）。两片 exec_over_cap=0、infra_retries=0。InsertPeg 片收尾自动聚合打 `V8_DELIVERY_SET=FAIL bad_h5=20` 属预期（20 局 V8 已交付局的 NFS 旧路径已删），本机加 `--rebase` 重聚合后 PASS、bad_h5=0。

## ⑧ 二次生成对拍（阶段 4）

`PARITY_H_H2=FAIL tier=v9 compared=80 identity_equal=80 byte_equal=72 noise=7 h2_fail=1 flipped=0 structural=0 hard_line_5pct=HIT`（`PARITY_REFERENCE first_divergence_min=142 median=208`）。

| 任务 | 局数 | 逐字节相同 | noise | h2_fail |
|---|---|---|---|---|
| InsertPeg | 30 | 29 | 1（seed 23304700，第 142 步起分叉） | 0 |
| MoveCube | 50 | 43 | 6（seed 23401600／23402100／23403900／23404800／23404900／23405300，首次分叉第 174～425 步） | 1（候选 66，seed 23406600：gen1 成功、H2 失败） |

V8 同口径为 1070 局中 12 局 noise（1.1%）。V9 不一致集中在 MoveCube 新区域（7／50）。按计划 §2.4.5，交付闸门（`V9_DELIVERY_SET`／`V9_STEP_CAP`／`V9_RESET_REPLAY`）与对拍闸门独立：本 FAIL 不自动阻断交付、也不自动放行，逐局明细 `records/parity-hh2-pairs.jsonl`、摘要 `records/parity-hh2-summary.json`，交用户裁决（候选处置：保持现交付并记录；或把候选 66 换为同方式备用并重做 3b）。未重试。

## ⑨ 用户决策记录

1. 「1002-newtask-v9-movecube-region-800-plan.md 开始实施 有问题问用户但不要阻塞 应该可以执行到底 所有预算job都批准」（2026-10-02，开工指令）。
2. 此前计划阶段的全部原话见计划 §2.8（区域最终版、每任务 50、复用 V8、两模型评估、4／10 席、独立站点、预算上浮十倍、逐方式硬配额）。
3. `PARITY_H_H2=FAIL` 的处置：待用户裁决（已在会话中提出；H2 产物已整体搬回 `artifacts/newtask-v9/parity/h2-nfs/` 保留备查）。

## ⑩ 计划外事件与处置

- 分配表漏列 `test_v8_native_blocks_unchanged.py` 的归属：主会话裁决补进 S1-A 可写集合，改为「MoveCube 只许 xhard4.region 子树变化」。
- S1-B 交回的集合外配合项（`freeze_specs.py` dry-run 打印配额、`generate_h5.py`／`_report.py` 按 header 推格表）由主会话在 12.327 自改。
- 阶段 2 合并顺序由 C→D→E→F 改为 E→F→D→C（四块文件集合互不重叠、无相互依赖，S1-C 实现较慢，先合已审完的）。
- runbook 修正（据子代理报告）：derive 写 `subset-root`、assemble 再写 `specs-root`；InsertPeg 片 continue 带 `--resume`；本机聚合加 V8 前缀映射；delivery-set 用 `--cells v9full --delivery`；step-headroom 带 `--xhard0`。
- 3b 切 `EXPECTED_CELLS` 后 5 个 V8 夹具测试隐式依赖 V8 表而失败，用 monkeypatch 在用例内钉回 V8 表（不改生产代码）。
- 核心短测的 6 个既有失败：`test_TaskGoal` 两条、`test_step_error_handling` 两条（官方 `src/robomme` 任务文案与上游脚本结构，BASE 上即失败），以及两个 `test_zz_summary_line`（前面有用例失败的连带）。
- 核心短测全量实测约 490 s，超过 AGENTS 覆盖第 4 条的 280 s 口径，每次均后台跑完。
- GL tmux 内联命令的 EXIT_CODE 转义（冒烟）写成空值，后改用 `launch.sh` 包装。

## ⑩′ 站点（阶段 4c）

V9 独立站：目录 `artifacts/newtask-v9/site/`、端口 8082（tmux `site-v9-8082`，`v8_site.py --host 0.0.0.0`），链接 http://sled-vail.eecs.umich.edu:8082/ 。构建 `v8_continue_after_gen.py --site-only --cells v9 … --eval-reuse artifacts/newtask-v8/site-eval --reused <reused.json> --eval-new <V9 评估运行目录>`：`V8_SITE_CATALOG=PASS identities=992 gen_v8=800 eval_reused=720 eval_new=80 eval_empty=0 eval_x0_reused=192 reuse_sha_mismatch=0 new_sha_mismatch=0`（`gen_xhard0_new=190 gen_failed=4` 与 V8 站相同）、`V8_SUBGOALS=PASS h5=1184 cells=59`。接续脚本自带的 site_check 因语义文件尚未生成而 FAIL（`semantic_mismatch=43`，「语义调整合集」等待超时）；补跑 `v8_semantic_diff.py --site-dir artifacts/newtask-v9/site`（`V8_SEMANTIC=PASS changed=17 param_only=26`）后起常驻服务，两个浏览器检查均 PASS（见 ①）。

与计划的出入：① 计划 §5 写「MoveCube xhard4 另注区域变化」，但 `v8_semantic_diff.py` 只比 goal／subgoal 文本、不在任何子代理可写集合内且计划列为不改，区域变化目前没有自动注记；② 页面沿用 `v8_site.html`／`v8_site.py` 不改（计划「布局完全一样」），标题仍显示「RoboMME v8」「v8 逐局对照」，数据已是 V9。

## ⑪ P3 预算实耗（上限 × 10 获批）

| 项目 | reset | rollout |
|---|---|---|
| xhard0 对拍 1b + 3b | 16 任务 × 1 档 × 12 局 × 2 侧 × 2 次 × 2 轮 = 1536 | 0 |
| 冒烟 2b | ≤ 2 任务 × 1 档 × 5 = 10（冻结上限） | 2 任务 × 1 档 × 1 局 = 2 |
| 抽签 MoveCube | 80 | 0 |
| 抽签 InsertPeg 追加 | 35 | 0 |
| 生成新局 | 63 + 46 = 109 | MoveCube 63 + InsertPeg 46 = 109 |
| 回注回放 3b | 43 格 × 1 = 43 | 0 |
| 二次生成 H2 | 80 | 80 |
| 合计 | 1893 | 191 |

均在计划表上限（reset 2,294、rollout 370）之内，未动用上浮额度；基础设施重试 0。

## ⑫ 结论与下一步、归档

V9 800 局交付集就绪并进包；下一步为双模型评估新 80 局（另档）与 V9 独立站点。归档：`records/gates.txt`（判定行原文）、`records/parity-hh2-{summary.json,pairs.jsonl}`、`records/{movecube-layout,delivery-set,step-headroom}.json`。产物（不进 git）：`artifacts/newtask-v9/{specs-root,subset-root,delivery,gen,gates,parity,logs}`；`delivery/` 的 720 局为指向 V8 `artifacts/newtask-v8/gen1` 的 hardlink（R-4：V8 产物以后若清理，hardlink 仍保住数据，两边 inode 删除需一并考虑）。
