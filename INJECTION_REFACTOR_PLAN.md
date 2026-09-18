# 新值注入链路重构计划：两阶段、两个 jsonl、其余进 logs

> **权威性**：本文是新值注入链路（候选分布 → 真实 HDF5）重构的唯一计划，提交在 `newtask-v2` 分支。代码锚点一律以 `92e8152`（10.84）为准；工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`。commit 编号沿用「主序号.流水号」体例，从 **11.01** 起。
> **分支**：实施（第一部分第十节阶段 1）开始时从 `newtask-v2` 另开新分支，**分支名由用户在批准阶段 1 时指定**，本文不预设；计划文档本身留在 `newtask-v2`。
> **授权边界**：本文只规划不实施。第一部分第十节的每个阶段都须用户单独批准后才动手；「未来可做」不等于本轮授权。
> **口径来源**：现行 h5 生成流程 = `20260912-contract-v3-10`（每 env 400 条严格交付），其机制细节见 [scripts/NEW_VALUE_INJECTION_PIPELINE.md](scripts/NEW_VALUE_INJECTION_PIPELINE.md)；重构后该文档被 `scripts/INJECTION.md` 取代。
> **决策史**：契约 v1→v3、xhard、BinFill demo 直出等历史决策本轮**不整理、不搬运**（用户 2026-09-17 原话「决策史先不管」），全部留在 git 历史与 `newtask-v2` 分支。

---

# 第一部分（给人看）

## 一、总览

**一句话方案**：把现在 11 个子命令、6 个独立脚本、7 份判定 JSON、6 份报告 md 的链路收成两个阶段目录——`candidates/` 出一份 `candidates.jsonl` 加图加报告，`rollout/` 出 h5、mp4、一份 `results.jsonl` 加数轴图加报告——其余一切机器产物进各自的 `logs/`，用户只看两个 jsonl、h5 和图。

**已定死口径**（用户拍板原话逐字保留，依据小节在括号内）：

1. 「我只在乎现在的h5生成流程」——范围只覆盖 10 轮实际走的链路，校准、并行对拍、碰撞回放等一次性验证分支不再是流程的一部分（第二节、第八节）。
2. 「候选分布产生只保留一个json 碰撞筛查和其他候选筛查 也增加写入这个json」「如果json需要改为jsonl你来自己决定」——定为 `candidates.jsonl`，每行一条候选并内嵌 `screening` 块（第四节 4.1）。
3. 「保留所有的出图和报告」「其他的放入logs文件夹 用户都不看」——第一阶段的三类跑前图与分布报告全留，判定 JSON、拒绝明细、配额报表进 `candidates/logs/`（第六节）。
4. 「第二阶段rollout保留h5 mp4 回放 和一个jsonl记录结果 成功/失败的都要记录 剩下的放入log 用户都不看 只用jsonl和h5判断成功」——定为 `results.jsonl`，成功与失败同表；运行参数、清单、生成器日志、timeline JSON 进 `rollout/logs/`（第四节 4.2）。
5. 「正式 / 备用的区分并入结果行」——`results.jsonl` 每行带 `role ∈ {primary, spare, failed}`，不再单独出 `delivery_manifest.json`（第四节 4.2、第七节）。
6. 「对应的script也分为这两个阶段单独建文件夹」——`scripts/injection/candidates/` 与 `scripts/injection/rollout/`（第三节 3.3）。
7. 「决策史先不管 这次重构需要从新branch开始」「我说的是修改开始后！你需要和用户确定分支名称」——实施开始时另开分支、分支名届时由用户指定，计划文档留在 `newtask-v2`；历史文档删而不搬（引言块）。
8. 现有 run 10 的 844 GB 产物**不重跑**，目录原地按新拓扑移动，h5 逐文件 SHA-256 核对（第十节阶段 7）。
9. 「需要加入修改前后的对拍」「使用B 每组前 15」——候选、图表数据层、reset 核验三层全量对拍；h5 / mp4 对拍取**方案 B，每组 block 0 前 15 条共 210 条**（第九节 9.4）。
10. 「有一部分json配置是只处理不生成h5的是怎么回事 也要保留 在rollout/ 中要做reset验证」——`delivery_400.json` 的 `extra_candidates=50` 那 700 条只做 `make + reset + close` 的候选**保留**，核验代码放 `scripts/injection/rollout/reset_check.py`，结果作为 `kind="reset"` 的行并入 `rollout/results.jsonl`（第四节 4.3）。
11. 「需要作为test episode回写入candidates.jsonl 写入成功与否」「candidates.jsonl要作为启动环境的唯一入口」「unused不消灭」「run 10 迁移时……838 条也 reset 一遍 要做」「test 的 primary 仍是每组前 50 条通过者 不变」——每行候选带 `split ∈ {train, test}` 与 `role ∈ {pending, primary, spare, failed, unused}`，rollout 结束后回写 `role`；新 run 保留 `unused`，run 10 迁移时例外地把 838 条 unused 全部 reset（第五节）。

## 二、现状：机制与产物

### 2.1 三套并列的工具链

| 工具链 | 入口 | 内容 | 10 轮实际用到 |
|---|---|---|---|
| 主链 `scripts/injection/`，13 文件 6.6k 行 | `python -m scripts.injection.campaign` | plan、check、plot、run(calibration / feasibility)、env-check、delivery、summarize、report、collision-reproduce、specs-diff、compare 共 11 个子命令 | plan、check、run feasibility、env-check、delivery、report |
| 跑前 2D 图与数轴 `scripts/injection-before-2d/`，6 脚本 2.25k 行 | 各自独立 | `plot_injection_before_2d.py`、`window_timeline.py`（extract / tables）、`plot_sampling_windows.py`、`event_tables.py`、`check_doc_links.py`、`plot_binfill_medium_single.py` | 产物仍基于 07，未按 10 重出 |
| HF 发布 `scripts/hf_release.py` | 独立 | pack / stage / manifest / upload / verify | 已完成，本轮不动 |

### 2.2 真实依赖链：生成器只读两样

```
injection_contract_v3.json ─┐
native_sampling.json ───────┼─ campaign plan ─→ specs/<task>/<diff>.json ×14（候选，h5 之前）
delivery_400.json ──────────┘                        │
delivery_400.json ──── campaign run ─→ manifests/feasibility_all_1842.json
                                                     ▼
native_sampling.json ── generate_dataset_newseed.py --episode-specs <清单> --sampling-config
                                                     ▼
                                     h5 / mp4 / episode_results.jsonl
delivery_400.json ──── campaign delivery ─→ delivery_manifest.json（primary / spare / failures）
delivery_400.json ──── campaign env-check ─→ env_check/<task>/<diff>.jsonl（实跑区间之后的候选只 make + reset + close，每组攒够 50 条通过即停）
```

契约与交付配置只被编排层读；`generate_dataset_newseed.py::load_episode_specs` 读的是清单指向的候选 JSON，`--sampling-config` 读 `native_sampling.json`。

### 2.3 五堆产物

| 堆 | 位置 | 内容 | 问题 |
|---|---|---|---|
| 配置 | `scripts/configs/newtask-v2/` | `native_sampling.json`、契约 v1 / v2 / v3、`delivery_400.json` | v1 / v2 只剩历史意义 |
| 运行目录 | `artifacts/injection/20260912-contract-v3-10/`，磁盘 844 GB、入库 85 文件 | `specs/` 14 份、`manifest.json`、`plan_stats.json`、`check_result.json`；`feasibility/P01x20/` 正式档与 `feasibility/P0x1/` smoke 档；`manifests/` 2 份；`feasibility_result*.json` 4 份；`env_check/` 15 份加 2 份判定；`delivery_manifest.json`；`logs/` 10 份；`hf_release/` | 各阶段混放一层，判定 JSON 四份，smoke 与正式并列 |
| 跑前图 | `scripts/injection-before-2d/figures/` | 每组 7 张跑前图加 1 张数轴共 114 张不入库；`windows_overview.png` 与 `windows_timeline.json`（576 KB）入库 | 放在脚本目录而非运行目录；基于 07 |
| 报告 md | 根目录与 `scripts/` | `NEW_VALUE_INJECTION_PIPELINE.md`（414 行）、`NEW_VALUE_CONTRACT_CHANGELOG.md`、`NEW_VALUE_INJECTION_TEST_PLAN.md`（1415 行）、`XHARD_DIFFICULTY_PLAN.md`、`NEW_VALUE_DISTRIBUTION_BEFORE.md`、`SAMPLING_WINDOWS.md`，共 3234 行 | 六成篇幅是 04 到 09 的历史 |
| 轻量包 | `docs/validation/newtask-v2/` | 04、06、07、08、09、10 六轮各 README + report + result_rows，08 / 09 另带尾迹核验脚本与 12 份 JSON | 与运行目录内容重复 |

## 三、重构后的拓扑

### 3.1 输入不变

`scripts/configs/newtask-v2/` 只留三份：`native_sampling.json`、`injection_contract_v3.json`、`delivery_400.json`。

### 3.2 产物：每个 run 一个目录、两个阶段

```
artifacts/injection/<run-id>/
├── candidates/                                   第一阶段：h5 之前
│   ├── candidates.jsonl                          首行 header，随后 3400 行候选，每行内嵌 screening；入库
│   ├── figures/<task>/<diff>/1_positions.png     初始位置分面板；不入库
│   ├── figures/<task>/<diff>/2_events.png        随机事件分面板；不入库
│   ├── figures/<task>/<diff>/3_episodes_p1..p5.png   前 30 条逐条俯视图加数值；不入库
│   ├── DISTRIBUTION.md                           14 组「事件 / 取值域 / 分配 / 结果分布」表加读图说明；入库
│   └── logs/                                     plan.log、check.log、plan_meta.json、rejections.jsonl、
│                                                 quota_report.json、check_result.json；入库
└── rollout/                                      第二阶段：全量 h5
    ├── <task>/<diff>/hdf5_files/*.h5             不入库
    ├── <task>/<diff>/videos/*.mp4                不入库
    ├── <task>/<diff>/record_dataset_<task>_metadata.json   录像器自行落盘，位置不由我们定；入库
    ├── results.jsonl                             实跑每条一行（kind=h5，带 h5 路径、SHA-256、role）+ reset 核验每条一行（kind=reset，无 h5）；成功失败同表；入库
    ├── figures/windows_overview.png              14 组各取最短 / 中位 / 最长；入库
    ├── figures/<task>/<diff>/4_windows.png       该组逐条数轴；不入库
    ├── ROLLOUT.md                                每组通过表、失败清单、视频状态；入库
    ├── WINDOWS.md                                数轴公式、汇总表、慢条剔除表；入库
    └── logs/                                     run_parameters.json、manifest.json、生成器日志、
                                                  windows_timeline.json、result.json、reset_check_result.json、smoke/；入库
```

`hf_release/` 留在 run 根目录原样不动。

### 3.3 脚本：两个阶段各一个文件夹

```
scripts/injection/
├── candidates/                    第一阶段
│   ├── __main__.py                python -m scripts.injection.candidates --run-id … 一次出全部
│   ├── contract.py  sampling.py  specs.py  categories.py     自 scripts/injection/ 原样搬入
│   ├── screen.py                  几何 / 碰撞 / 配额 / 可复现筛查，逐行写回 screening，组级进 logs
│   ├── figures.py                 三类跑前图，自 injection-before-2d/plot_injection_before_2d.py 搬入
│   └── report.py                  DISTRIBUTION.md，自 injection-before-2d/event_tables.py 搬入
└── rollout/                       第二阶段
    ├── __main__.py                python -m scripts.injection.rollout --run-id … 一次出全部：run → role → reset_check → windows → report
    ├── run.py                     进程池编排、清单、续跑、role 判定；自 scripts/injection/run.py + delivery.py 合并
    ├── reset_check.py             实跑区间之后的候选只 make + reset + close，每组攒够 50 条通过即停；自 scripts/injection/env_check.py 搬入
    ├── windows.py                 从 h5 抽 timeline 并出数轴图；自 window_timeline.py + plot_sampling_windows.py 合并
    ├── single_binfill.py          可选工具，不在主流程；自 plot_binfill_medium_single.py 搬入
    └── report.py                  ROLLOUT.md 与 WINDOWS.md
```

`scripts/generate_dataset_newseed.py` 留在原位，唯一改动是 `load_episode_specs` 学会从 `candidates.jsonl` 按 (task, difficulty, episode) 取行。`scripts/INJECTION.md` 是唯一流程文档。

## 四、两个 jsonl 的行结构

### 4.1 `candidates.jsonl`

首行是 header 记录，承接现在每组 JSON 顶层的溯源字段：

```json
{"record": "header", "run_id": "…", "spec_schema_version": 3, "generator_seed": 20260909,
 "generator_version": "…", "contract": "scripts/configs/newtask-v2/injection_contract_v3.json",
 "contract_sha256": "…", "sampling_config_sha256": "…", "delivery_config": "…/delivery_400.json",
 "groups": 14, "candidates": 3400}
```

之后每行一条候选，字段 = 现在 `specs/<task>/<diff>.json` 的 `episodes[i]` 原样，再加 `split / role`（第五节）与下面两块：

```json
{"record": "candidate", "task": "VideoRepick", "difficulty": "easy", "episode": 0, "block": 0,
 "seed": 9000, "spec_sha256": "…", "split": "train", "role": "pending", "error_type": null,
 "layout": {…}, "objects": {…}, "actions": {…}, "sampling_cells": {…},
 "screening": {"geometry": "PASS",
               "collision_initial": "PASS", "collision_sweeps": ["PASS", "PASS"], "min_g_m": 0.0134,
               "candidates_tried": 3,
               "rejected_before_accept": {"geometry": 2, "contact": 0, "numerical_boundary": 0, "uncertified": 0}}}
```

- `spec_sha256` 的作用域不变，仍只对 `layout / objects / actions` 算，所以新链路产的 3400 行必须与 run 10 的 `specs/` 逐条同散列，这是阶段 1 的判据。
- 被拒绝的候选本身不进这个文件，只在 `screening.candidates_tried` 与 `rejected_before_accept` 记「通过前试了几个、各因什么拒」；拒绝明细逐条落 `candidates/logs/rejections.jsonl`。原因：BinFill/medium 一组试了 5281 个候选，全写会让文件膨胀三倍且没人看。
- BinFill 没有碰撞扫掠，`collision_initial / collision_sweeps / min_g_m` 写 `null`；`geometry` 对四任务都写。
- 组级汇总（每组拒绝总数、配额覆盖、可复现对拍）不重复进每行，落 `candidates/logs/quota_report.json` 与 `check_result.json`。

### 4.2 `results.jsonl`

两种行共用一个文件，用 `kind` 区分；两种行都带 `split`（train / test）与 `role`，取值与回写到 `candidates.jsonl` 的完全一致（第五节 5.3）。

**`kind="h5"` 行**（每条实跑一行）= 现在 `episode_results.jsonl` 的一行原样（`task / episode / attempt / seed / difficulty / ok / h5_path / timestep_count / binfill_demo / video / wall_s / phases / injection_evidence / runtime_checks / bound / …`，失败行另有 `failure_class / error_type`），再加四个字段：

| 字段 | 值 | 写入时机 |
|---|---|---|
| `kind` | `"h5"` | 生成器写行时 |
| `h5_sha256` | 成品 h5 的 SHA-256；失败行 `null` | 生成器在 `close()` 后核验阶段顺手算，与现在算视频散列同处 |
| `h5_bytes` | 字节数；失败行 `null` | 同上 |
| `role` | `primary`：该组按 episode 升序前 `target_h5` 条通过；`spare`：其余通过；`failed`：未通过 | 实跑结束后 `rollout/run.py` 的收尾步原子重写整个文件 |

**`kind="reset"` 行**（每条 reset 核验一行）= 现在 `env_check/<task>/<diff>.jsonl` 的一行原样（`task / difficulty / episode / seed / spec_sha256 / outcome / error_type / error / wall_s / phases{make_s, reset_s, close_s} / bound / injection_bound / counted`），再加 `kind="reset"`、`ok`（`outcome` 是否通过）、`h5_path: null`、`role`（`primary`：该组按 episode 升序前 `extra_candidates=50` 条通过；`spare`：其余通过；`failed`：未通过）。原 `delivered` 字段由 `role == "primary"` 取代。

「只用 jsonl 和 h5 判断成功」的判法：`kind="h5"` 行要 `ok == true` 且 `h5_path` 存在且 `h5_sha256` 相符；`kind="reset"` 行本就无 h5，只看 `ok`。两种行的 `role` 各自决定是否计入交付（400 条 h5、700 条 reset 候选）。

### 4.3 只做 reset 不出 h5 的候选是怎么回事

这是 2026-09-12 用户口径「在此基础上给每个env每个难度再增加50个候选不生成数据集 只生成候选 可以产生环境」的落地，配置在 `delivery_400.json` 的 `extra_candidates: 50`：

- `plan` 铺候选时按 `blocks × 100 ≥ run_episodes + 50` 多铺一个 block，所以 3 档 env 每组 300 条、4 档 env 每组 200 条，合计 3400 条，而实跑只用前 1842 条。
- 实跑区间之后的候选（如 BinFill/easy 从 ep155 起）按 episode 序逐条只做 `gym.make(任务, episode_spec=规格) → env.reset() → env.close()`，不套录像器、不建 planner、不 step，零 h5 / mp4；每组攒够 50 条通过即停。run 10 实测 14 组各查 51 到 54 条、全部通过、交付 700 条，双卡 40 worker 共 492.7 秒，`make` 中位 20 秒、`reset` 中位 0.07 秒。
- 语义边界：只证明「该候选能产生环境」，不证明能出 h5（不覆盖 step 期绑定错误、规划可解性、录像器步数保护、任务成功判定）。
- 这 700 条已随 HF 发布进了 `meta/env_check/`，是交付物的一部分，所以保留。

重构后它是 `rollout/` 的一步：`run.py` 实跑完、算完 `role` 之后，`reset_check.py` 对每组 `run_episodes` 之后的候选按序核验，结果作为 `kind="reset"` 行追加进同一份 `results.jsonl`，组级判定写 `logs/reset_check_result.json`，判定行 `RESET_CHECK=PASS groups=14 checked=… passed=… delivered=700 shortfall=0`。

## 五、`candidates.jsonl` 的划分与回写：启动环境的唯一入口

用户 2026-09-17 原话：「只做 reset 不出 h5 的候选 需要作为test episode回写入candidates.jsonl 写入成功与否 results jsonl也需要体现」「candidates.jsonl要作为启动环境的唯一入口」；追问后拍板：「明白」（每档 50 条共 700 不改）「unused不消灭」「run 10 迁移时是否顺手把这 838 条也 reset 一遍 要做」「test 的 primary 仍是每组前 50 条通过者 不变」。

### 5.1 两个维度，不是并列的四类

每行候选在 4.1 的字段之外再带两个字段：

| 字段 | 取值 | 谁写、何时写 |
|---|---|---|
| `split` | `train`：episode < 该组 `run_episodes`；`test`：其余 | `candidates` 包冻结时按 `delivery_400.json` 写死，之后不变 |
| `role` | `pending` → `primary` / `spare` / `failed` / `unused` | 冻结时写 `pending`；`rollout` 结束后回写 |

两维交叉后的含义与 run 10 的实际条数：

| split | role | 含义 | run 10 |
|---|---|---|---:|
| train | primary | 出了 h5 且按 episode 升序进该组前 `target_h5` 条 | 1600 |
| train | spare | 出了 h5 但超出 `target_h5` 的余量，h5 保留 | 196 |
| train | failed | 实跑失败，无 h5 | 46 |
| test | primary | reset 通过且按 episode 升序进该组前 `extra_candidates=50` 条 | 700 |
| test | spare | reset 通过但超出 50 条 | 20 |
| test | failed | reset 失败 | 0 |
| test | unused | 该组攒够 50 条通过后停止，从未 reset 过 | 838 |

700 是 14 个 env × 难度组各 50 条之和（BinFill 150、RouteStick 200、VideoUnmaskSwap 200、VideoRepick 150），不是每 env 50 条；这是 2026-09-12「给每个env每个难度再增加50个候选」的口径，用户确认不改。

### 5.2 `unused` 不消灭

新 run 沿用「每组攒够 50 条 reset 通过即停」的规则，停点之后的 test 候选保持 `role="unused"`，不为消灭它们而把全部 test 候选 reset 一遍。**run 10 是唯一例外**：迁移时把它的 838 条 `unused` 也 reset 一遍（约 838 × 20 秒 ÷ 40 worker ≈ 7 分钟），结果按同一规则回写为 `spare` 或 `failed`；700 条 `primary` 不变，h5 与已发布的 HF 内容不动。

### 5.3 回写规则

- `rollout` 收尾步只改 `candidates.jsonl` 每行的 `role` 与 `error_type`（失败时记 `error_type`，否则 `null`）两个字段，其余字段与 `spec_sha256` 逐字不动；写临时文件后 `os.replace` 原子覆盖。header 行追加 `roles` 计数（按 split × role）。
- 同一结果在 `results.jsonl` 也有一行：train 行 `kind="h5"`、test 行 `kind="reset"`，都带 `split` 与同值的 `role`。两文件靠 (task, difficulty, episode) 互指；`unused` 在 `results.jsonl` 里没有对应行。
- 判据：`ROLES_CONSISTENT=PASS rows=3400 mismatch=0`——`candidates.jsonl` 每条非 `unused` 行的 `role` 与 `results.jsonl` 对应行一致，`unused` 行在 `results.jsonl` 无对应。

### 5.4 唯一入口

起环境的三处都只读 `candidates.jsonl`，每行自带 `task / difficulty / episode / seed / layout / objects / actions`，不依赖别的文件：

| 谁 | 读哪些行 | 怎么起 |
|---|---|---|
| `generate_dataset_newseed.py` 出 h5 | `split="train"` | `gym.make(task, episode_spec=行)` + `RobommeRecordWrapper` + planner |
| `rollout/reset_check.py` | `split="test"`，按 episode 序直到攒够 50 条通过 | `gym.make(task, episode_spec=行)` → `reset()` → `close()` |
| 策略侧日后起 test 环境 | `split="test"` 且 `role="primary"` | 同上，本仓库不实现 |

`seed` 字段是 `SeedLayout("train").seed(task, episode, 0)` 的值，test 行与 train 行用同一 layout（run 10 的 env-check 就是这么起的），只是 episode 号在实跑区间之后。

## 六、出图与报告：各出哪些、删哪些

**出图**：

| 套 | 每组产出 | 处置 |
|---|---|---|
| `campaign plot`（`scripts/injection/plots.py`）：10×10 缩略总览、XY 散点加占用格、字段条形，跑前跑后各一套 | 3 张 × 2 | **删**。10 轮没出过，按 100 条排版已不适配 3400 条 |
| 跑前 2D：`1_positions`、`2_events`、`3_episodes_p1..p5` | 7 张 | **保留**，迁入 `candidates/figures/`，按 10 重出 |
| 数轴：`4_windows` 每组逐条、`windows_overview` 总览 | 1 张 + 1 张 | **保留**，迁入 `rollout/figures/`，按 10 重出 |
| BinFill/medium 单条两轴图两张，英文文案 | 2 张 | **删出主流程**，脚本作可选工具留在 `rollout/single_binfill.py` |

**报告**：

| 报告 | 现在内容 | 处置 |
|---|---|---|
| `scripts/injection-before-2d/NEW_VALUE_DISTRIBUTION_BEFORE.md` | 一节机制、二节 14 组四列表、三节读图说明 | **保留二、三节** → `candidates/DISTRIBUTION.md`；一节并入 `scripts/INJECTION.md` |
| `scripts/injection-before-2d/SAMPLING_WINDOWS.md` | 公式、图、每组逐条数字表、慢条剔除表 | **保留公式、汇总表、剔除表** → `rollout/WINDOWS.md`；逐条数字表删，1796 条会有约 2000 行，数据在 `logs/windows_timeline.json` |
| `docs/validation/newtask-v2/<run>/README.md`（`campaign report`） | 判定行、七类结果、error_type 分布、视频状态、交付、env-check、失败清单、散列清单 | **换成 `rollout/ROLLOUT.md`**：只留每组通过表、失败清单带 error_type、视频状态；判定行进 `logs/result.json`，env-check 与散列清单不再出 |
| `scripts/NEW_VALUE_INJECTION_PIPELINE.md` | 04 到 10 七轮全史 | **重写为 `scripts/INJECTION.md`**：只写现行口径与复现命令 |
| `scripts/NEW_VALUE_CONTRACT_CHANGELOG.md`、`NEW_VALUE_INJECTION_TEST_PLAN.md`、`XHARD_DIFFICULTY_PLAN.md` | 决策记录与验收计划 | **删**，不搬运（口径 7） |
| `hf_release/README.md` | 发布说明 | 不动 |

## 七、追溯性：守住三条，处理两处

设计合理且比现在更易追溯，前提是：

1. **`logs/` 照常进 git**。放的不只是文本日志，还有判定 JSON、运行参数、实跑清单这些机器可读文件。「用户不看」不等于「不存」。
2. **两个 jsonl 靠主键互指**。候选行与结果行都带 `(task, difficulty, episode)` 与 `spec_sha256`（结果行在 `injection_evidence.spec_sha256`），结果行再带 `h5_path / h5_sha256`。任一 h5 都能反查到候选、候选的筛查证据、当时的运行参数。
3. **候选行内嵌筛查证据**。现在只有视频任务候选带 `collision`，BinFill 只有 `sampling_cells`；合并后四任务统一带 `screening`，比现在只在 `plan_stats.json` 记组级总数更细。

会变化的两处及处置：

- **正式 / 备用**：由 `delivery_manifest.json` 改为结果行 `role` 字段（口径 5）。HF 发布脚本 `scripts/hf_release.py` 目前读 `delivery_manifest.json`，本轮不改它，但在 `scripts/INJECTION.md` 记明「再次发布须先改 hf_release.py 读 `results.jsonl` 的 `role`」。
- **决策史**：四份计划 md 删除后只在 git 历史与 `newtask-v2` 分支可查（口径 7）。

## 八、删除清单

- **代码**：`scripts/injection/replay.py`、`contract_build.py`、`plots.py`、`campaign.py`（其 plan / check / run / env-check / delivery 逻辑迁入两个新包后整文件删）、`scripts/injection-before-2d/` 整个目录（含 `check_doc_links.py`、`windows_timeline.json`、`figures/`）。**不删**的两个：`h5_compare.py` 搬为 `scripts/injection/rollout/h5_compare.py`，只在对拍 SHA-256 不一致时用来定位差异（第九节 9.2）；`env_check.py` 搬为 `scripts/injection/rollout/reset_check.py`（第四节 4.3）。
- **删除时机**：旧的出图、事件表、timeline 脚本要先对 run 10 跑一遍留下基线（第十节阶段 3），之后才能删。
- **配置**：`injection_contract_v1.json`、`injection_contract_v2.json`。
- **文档**：第六节表中标「删」与「重写」的六份；`scripts/README.md` 第四节改为指向 `scripts/INJECTION.md`。
- **轻量包**：`docs/validation/newtask-v2/` 下 `20260910-new-values-04`、`20260911-contract-v3-06`、`20260911-contract-v3-07`、`20260912-contract-v3-08`、`20260912-contract-v3-09`、`20260912-contract-v3-10` 六个目录。其余非 injection 轮次目录不动。
- **run 10 目录内**：不删只移（第十节阶段 7）。`env_check/*.jsonl` 的 720 行转成 `kind="reset"` 行并入 `rollout/results.jsonl`，原文件与 `env_check_result*.json`、`feasibility/P0x1/`、`manifests/`、四份 `feasibility_result*.json`、`delivery_manifest.json`、`manifest.json`、`plan_stats.json`、`check_result.json`、`logs/*` 全部进对应阶段的 `logs/`。
- **`.gitignore`**：`artifacts/injection` 段与 `scripts/injection-before-2d/figures` 段整体替换（第二部分三）。

## 九、修改前后的对拍

### 9.1 修改前的生成花了多久（run 10 实测，2026-09-12，双卡各 20 worker）

| 阶段 | 规模 | 墙钟 | 出处 |
|---|---|---|---|
| `plan` 冻结候选 | 14 组 3400 条 | 675.3 秒（11 分钟） | `logs/plan.log` `elapsed_s=675.3` |
| `check` 静态与碰撞筛查 | 3400 条，碰撞扫掠 1700 条 | 1338.5 秒（22 分钟） | `logs/check.log` `elapsed_s=1338.5` |
| 实跑 | 1842 条，通过 1796 | 6684.4 秒（1 小时 51 分），16.12 条/分 | `feasibility/P01x20/run_summary.json` `elapsed_s` |
| 成功条单条 | 1796 条 | 中位 126 秒、最大 241 秒；串行总和 63 小时 | `episode_results.jsonl` `wall_s` |
| 超时条单条 | 21 条 | 600 秒被终止（最长实测 626 秒） | 同上 |
| 产物体积 | h5 1796 个 | 880 GB，中位 424 MB | `delivery_manifest.json` `h5_bytes` |

磁盘：`/data` 总 14 TB，已用 12 TB，**余 1.9 TB**（2026-09-17 `df`）；全量重跑一份 880 GB 放得下，但跑完必须删一份。GPU 0 / 1 当前空闲（利用率 0%）。

### 9.2 关键前提：h5 与 mp4 都是逐字节确定的，对拍只比 SHA-256

run 10 里 RouteStick/easy ep0 被生成过两次：smoke 档 `P0x1`（单卡 1 worker，13:06）与正式档 `P01x20`（双卡 40 worker，13:29）。两次的成品：

| 文件 | 字节数 | SHA-256 前 16 位 | 结论 |
|---|---:|---|---|
| `RouteStick_ep0_seed16000.h5` | 200,071,952 | `27d7e1c62583025e` 两次相同 | h5 逐字节确定 |
| `RouteStick_ep0_seed16000_easy_watch….mp4` | 6,648,548 | `468cf3b5c00344e3` 两次相同 | 录像器直出的 mp4 逐字节确定 |

因此**对拍不需要逐 dataset 遍历**：新链路生成时在 `close()` 后算的 `h5_sha256` 直接与 `delivery_manifest.json` 里 run 10 的 1796 个散列比即可，旧文件零额外读取。`h5_compare.py` 只在散列不一致时用来定位是哪个 dataset 变了。两个例外：BinFill 的 mp4 经 `imageio` 二次 libx264 编码，逐字节是否确定未验证，**只比帧数**，其 h5 照比；21 条超时与 25 条规划失败比 `failure_class / error_type`（10 轮已证明超时 seed 三轮复现，是确定性的）。

### 9.3 三层对拍

| 层 | 比什么 | 怎么比 | 规模与耗时 | 判定行 |
|---|---|---|---|---|
| L1 候选（**全量必做**） | 新 `candidates` 包对 run 10 的契约与配置重算 3400 行 | 逐行 `spec_sha256` 与 `specs/<task>/<diff>.json` 比；`screening` 里的碰撞结论与旧 `collision` 字段比 | plan 11 分钟 + screen 22 分钟 ≈ 35 分钟，零磁盘 | `CANDIDATES_EQUIVALENCE=PASS compared=3400 differences=0` |
| L2 图与报告数据层（**全量必做**） | 旧脚本与新脚本对**同一份 run 10** 各出一套 | 删旧脚本前先用 `plot_injection_before_2d.py`、`event_tables.py`、`window_timeline.py extract` 对 run 10 跑出基线（三者此前只对 07 跑过）；新 `figures.py / report.py / windows.py` 出的 98 + 15 张 PNG 逐字节比、事件表逐行比、`windows_timeline.json` 逐键比 | 旧 extract 要打开 1796 个 h5 读 T 与分段，**未实测**，估 10 到 30 分钟；出图数分钟；零额外磁盘 | `FIGURES_EQUIVALENCE=PASS png=113 differences=0`、`TABLES_EQUIVALENCE=PASS rows=… drift=0`、`TIMELINE_EQUIVALENCE=PASS episodes=1796 differences=0` |
| L3 h5 / mp4（**方案 B，用户已选**） | 新 `rollout` 包按 `candidates.jsonl` 重新生成每组 block 0 前 15 条 | 成功条比 `h5_sha256`（BinFill 另比 mp4 帧数，其余任务 mp4 也比 SHA-256）；失败条比 `failure_class / error_type` | 210 条，见 9.4 | `H5_PARITY=PASS compared=210 sha_mismatch=0 mp4_mismatch=0 failure_mismatch=0` |
| L4 reset 核验（**全量必做**） | 新 `reset_check.py` 对 run 10 的 14 组从各自 `run_episodes` 起重新核验到攒够 50 条通过 | 与 `env_check/<task>/<diff>.jsonl` 按 (task, difficulty, episode) 配对，比 `outcome / error_type / injection_bound` 与「攒够 50 条时停在哪一条」；`phases` 耗时不比 | 720 条，run 10 实测 492.7 秒，零磁盘 | `RESET_PARITY=PASS compared=720 outcome_mismatch=0 stop_episode_mismatch=0` |

### 9.4 L3 的四个方案（用户 2026-09-17 选定 B：「使用B 每组前 15」）

条数按「每组 block 0 的前 N 条」取，覆盖 14 组；耗时按双卡 40 worker、机器空闲估，含超时条封底（每组前 1 条里就有 VideoRepick/easy ep0 这条 626 秒超时）。

| 方案 | 条数 | 预计墙钟 | 临时磁盘 | 覆盖到的结果类型 | 能证明什么 |
|---|---:|---|---:|---|---|
| A 全量 | 1842 | ≈ 1 小时 51 分（与 run 10 相同） | 880 GB，余 1.9 TB 可容 | 1796 成功 + 21 超时 + 25 规划失败 | 新链路**逐条**复现已交付数据集；PASS 后新旧两份逐字节相同，删一份即可 |
| **B 每组前 15（已选定）** | 210 | ≈ 15 到 20 分钟（理论下限 11.5 分钟） | ≈ 90 GB | 205 成功 + 3 规划失败 + 2 超时 | 四任务四档全覆盖、三类结果都有样本 |
| C 每组前 5 | 70 | ≈ 10 到 12 分钟（下限 4 分钟，被 626 秒超时封底） | ≈ 30 GB | 68 成功 + 1 规划失败 + 1 超时 | 四任务四档全覆盖 |
| D 每组前 1 | 14 | ≈ 10 分钟（被 626 秒超时封底） | ≈ 6 GB | 13 成功 + 1 超时 | 只证明链路能通 |

本会话原推荐 A（只有全量能宣称与已发布数据集逐字节一致），用户选定 B。B 的结论边界写明：210 条抽样一致 + 生成确定性（9.2 的两次同散列证据）⇒ 推断其余 1632 条一致；不是逐条实证。

## 十、实施步骤

每阶段单独获批、单独 commit（11.01 起），判据不过不进下一阶段。

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 本计划写入 `newtask-v2` | 本文入库；`git status -sb` 无遗留 |
| 1 | 先与用户确定分支名并从 `newtask-v2` 切出；建 `scripts/injection/candidates/`：搬四个核心模块，写 `screen.py` 与 `__main__.py`，产 `candidates.jsonl`；对 run 10 重算（L1 对拍） | `CANDIDATES_EQUIVALENCE=PASS compared=3400 differences=0`；`SCREENING_FILLED=PASS rows=3400 null_geometry=0` |
| 2 | 生成器 `load_episode_specs` 读 jsonl，`close()` 后加 `h5_sha256 / h5_bytes`；跑 1 条 smoke（RouteStick/easy ep0） | `LOADER_PARITY=PASS`（同一条从 jsonl 与从旧 json 加载的 dict 相等）；`SMOKE_H5_PARITY=PASS compared=1 sha_mismatch=0`（与 run 10 的 `27d7e1c6…` 相同） |
| 3 | 删旧脚本前用旧 `plot_injection_before_2d.py`、`event_tables.py`、`window_timeline.py extract` 对 run 10 出一套基线到 `candidates/logs/baseline/` 与 `rollout/logs/baseline/` | `BASELINE_CAPTURED=PASS png=113 tables=14 timeline_episodes=1796` |
| 4 | 建 `scripts/injection/rollout/`：合并 run + delivery，搬 env_check 为 `reset_check.py`，写 `kind / split / role / h5_sha256 / h5_bytes` 并回写 `candidates.jsonl` 的 `role`；用 run 10 的 `episode_results.jsonl + delivery_manifest.json + env_check/*.jsonl` 迁移出 `results.jsonl`，同时回写 run 10 的 `candidates.jsonl` | `RESULTS_EQUIVALENCE=PASS h5_rows=1842 primary=1600 spare=196 failed=46 reset_rows=720 reset_primary=700`；`ROLES_CONSISTENT=PASS rows=3400 mismatch=0 unused=838` |
| 5 | L3 + L4 对拍：新 `rollout` 包按方案 B 重新生成每组前 15 条到临时 run-id，与 run 10 比散列与失败类型；新 `reset_check.py` 对 run 10 已核验的 720 条重新核验并与旧结果比；PASS 后删临时产物。**随后**对 run 10 的 838 条 `unused` 做一次 reset（约 7 分钟），结果追加进 run 10 的 `results.jsonl` 并回写 `candidates.jsonl` | `H5_PARITY=PASS compared=210 sha_mismatch=0 mp4_mismatch=0 failure_mismatch=0`；`RESET_PARITY=PASS compared=720 outcome_mismatch=0 stop_episode_mismatch=0`；`UNUSED_RESET=PASS checked=838 unused_left=0`，之后 `ROLES_CONSISTENT` 复判 `unused=0` |
| 6 | 新 `windows.py / figures.py / report.py` 对 run 10 出图与报告，与阶段 3 基线比（L2 对拍） | `FIGURES_EQUIVALENCE=PASS png=113 differences=0`、`TABLES_EQUIVALENCE=PASS drift=0`、`TIMELINE_EQUIVALENCE=PASS episodes=1796 differences=0` |
| 7 | run 10 目录原地迁移：`feasibility/P01x20/<task>/<diff>` → `rollout/<task>/<diff>`，其余进 `logs/` | `H5_INTACT=PASS count=1796 sha_mismatch=0 missing=0` |
| 8 | 删旧代码、旧配置、旧文档、轻量包；改 `.gitignore`；写 `scripts/INJECTION.md`；改 `scripts/README.md` 第四节 | `DOC_LINKS=PASS broken=0`；`git ls-files artifacts/injection/20260912-contract-v3-10 \| wc -l` 与阶段 7 清单一致；`grep -rn "injection-before-2d\|campaign\b" scripts docs *.md` 零命中 |
| 9 | 新链路端到端冒烟：新 run-id 出 1 组 1 block 候选、实跑 1 条 | `plan + run` 总耗时 < 5 分钟；两个 jsonl、h5、图、报告齐全 |

实施完成后实测结果以子节追加在本表之后，不改写原计划。

---

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

- R1 `src/robomme/` 不动（AGENTS.md 强制规则第 11 条，录像器冻结）。
- R2 `scripts/generate_dataset_newseed.py` 只改 `load_episode_specs`（jsonl 读法）与 `close()` 后核验段（加 `h5_sha256 / h5_bytes`）；不传 `--episode-specs` 时链路逐字不变。
- R3 run 10 的 h5 / mp4 只 `mv` 不重跑、不删；迁移前后逐文件 SHA-256 核对。
- R4 `spec_sha256` 的算法与作用域不改，否则阶段 1 判据失去意义。
- R5 不 `git push --force`；实施分支的名称先问用户，首次推送前再问是否 `git push -u origin <分支名>`。
- R6 `hf_release/` 与 `scripts/hf_release.py` 本轮不动。
- R7 删除只在阶段 8 做，且在阶段 1 到 7 全部 PASS 之后；旧出图 / 事件表 / timeline 脚本在阶段 3 留下基线之前不得删。
- R8 L3 对拍写到独立的临时 run-id（如 `<run10>-parity`），绝不写进 run 10 目录；PASS 后临时产物整目录删除，磁盘回到对拍前水位。

## 一、逐文件改动清单

| 新文件 | 来源 | 改什么 |
|---|---|---|
| `scripts/injection/candidates/contract.py` `sampling.py` `specs.py` `categories.py` | `scripts/injection/` 同名文件 | 只改 import 路径 |
| `scripts/injection/candidates/screen.py` | `campaign.py` 的 `cmd_check` 六项判定 + `plan_stats` 采集 | 判定按组算完后把每条的几何 / 碰撞 / 试用候选数写回该行 `screening`；组级写 `logs/quota_report.json`、`logs/check_result.json`；拒绝明细写 `logs/rejections.jsonl` |
| `scripts/injection/candidates/figures.py` | `injection-before-2d/plot_injection_before_2d.py` | 输入改读 `candidates.jsonl`；输出根改 `candidates/figures/` |
| `scripts/injection/candidates/report.py` | `injection-before-2d/event_tables.py` + `NEW_VALUE_DISTRIBUTION_BEFORE.md` 二、三节模板 | 输出 `candidates/DISTRIBUTION.md`；保留 `--check` 零漂移模式 |
| `scripts/injection/candidates/__main__.py` | `campaign.py` 的 `cmd_plan` | 顺序：派生 → screen → 写 jsonl → figures → report；`--run-id` 已存在则拒绝 |
| `scripts/injection/rollout/run.py` | `scripts/injection/run.py` + `delivery.py::build_delivery_manifest` | 清单写 `rollout/logs/manifest.json`，`spec_path` 指向 `candidates.jsonl`；实跑结束后按 `delivery_400.json` 算 `role` 并原子重写 `results.jsonl`；保留 `--skip-done`、`--episode-range`、`--wall-limit-h`、`--label smoke`（smoke 产物落 `rollout/logs/smoke/`） |
| `scripts/injection/rollout/windows.py` | `window_timeline.py` + `plot_sampling_windows.py` | 输入改读 `results.jsonl` 与 `rollout/<task>/<diff>/hdf5_files/`；timeline 写 `rollout/logs/windows_timeline.json`；图写 `rollout/figures/` |
| `scripts/injection/rollout/report.py` | `campaign.py::cmd_report` 的结果表部分 + `window_timeline.py tables` | 输出 `ROLLOUT.md`（通过表、失败清单、视频状态）与 `WINDOWS.md`（公式、汇总表、剔除表） |
| `scripts/injection/rollout/single_binfill.py` | `plot_binfill_medium_single.py` | 只改输入路径；不被 `__main__` 调用 |
| `scripts/injection/rollout/h5_compare.py` | `scripts/injection/h5_compare.py` | 原样搬入；只在 `H5_PARITY` 散列不一致时手动调用定位差异 |
| `scripts/injection/rollout/reset_check.py` | `scripts/injection/env_check.py`（`check_one` / `run_env_check` / `EnvCheckPlan`） | 输入改读 `candidates.jsonl` 的 `split="test"` 行；输出改为向 `results.jsonl` 追加 `kind="reset"` 行（`ok / split / role` 替代 `outcome / delivered`）并回写 `candidates.jsonl` 的 `role`，组级判定写 `logs/reset_check_result.json`；加 `--only-unused`（只跑 `role="unused"` 的行，不改停点规则，供 run 10 例外用）；`gym.make` kwargs 与 `_worker` 逐字一致、单条 120 秒超时、pebble 池复用 `_pool_init` 与 `_cpu_plan` 三点不动 |
| `scripts/injection/rollout/parity.py` | 新写 | 读两个 run 的 `results.jsonl`（旧 run 用迁移后的），按 (kind, task, difficulty, episode) 配对：h5 行比 `h5_sha256`、mp4 SHA-256 或帧数、`failure_class / error_type`，打 `H5_PARITY`；reset 行比 `ok / error_type / injection_bound` 与每组停止 episode，打 `RESET_PARITY` |
| `scripts/injection/rollout/__main__.py` | `campaign.py` 的 `cmd_run` feasibility 分支 | 顺序：run → role → reset_check → windows → report |
| `scripts/generate_dataset_newseed.py` | 现有 | `load_episode_specs`：清单 `spec_path` 以 `.jsonl` 结尾时按 `(task, difficulty)` 过滤行、跳过 header；`_worker` 的 `close()` 后核验段加 `h5_sha256 / h5_bytes` |
| `scripts/INJECTION.md` | 新写 | 现行口径、两阶段命令、两个 jsonl 字段表、追溯链、「再次 HF 发布须改 hf_release.py」 |
| 一次性迁移脚本 `scripts/injection/_migrate_run10.py` | 新写，阶段 7 用完即删 | `specs/*.json + plan_stats + check_result` → `candidates.jsonl`；`episode_results.jsonl + delivery_manifest.json` → `kind="h5"` 行、`env_check/*.jsonl` → `kind="reset"` 行，合并为 `results.jsonl`；目录 `mv`；SHA-256 核对 |

## 二、`.gitignore` 替换段

```
/artifacts/*
!/artifacts/injection/
/artifacts/injection/*
!/artifacts/injection/*/
/artifacts/injection/*/*
!/artifacts/injection/*/candidates/
/artifacts/injection/*/candidates/figures/
!/artifacts/injection/*/rollout/
/artifacts/injection/*/rollout/*/*/hdf5_files/
/artifacts/injection/*/rollout/*/*/videos/
/artifacts/injection/*/rollout/figures/*
!/artifacts/injection/*/rollout/figures/windows_overview.png
!/artifacts/injection/*/hf_release/
```

删除 `scripts/injection-before-2d/figures/*` 两行。

## 三、runbook（阶段 5 对拍与阶段 9 冒烟的新链路命令）

阶段 5（方案 B：每组 block 0 前 15 条；reset 核验全量）：

```bash
RID=20260912-contract-v3-10; PID=$RID-parity; CFG=scripts/configs/newtask-v2/delivery_400.json
# 用 run 10 的 candidates.jsonl 重跑每组前 15 条（约 15 到 20 分钟，tmux 起，日志落 artifacts/injection/$PID/rollout/logs/）
uv run --no-sync python -m scripts.injection.rollout --run-id $PID --candidates artifacts/injection/$RID/candidates/candidates.jsonl \
  --delivery-config $CFG --tier 20 --gpus 0,1 --episodes 15 --no-figures
# reset 核验全量重做（约 8 分钟，同一临时 run-id）
uv run --no-sync python -m scripts.injection.rollout.reset_check --run-id $PID --candidates artifacts/injection/$RID/candidates/candidates.jsonl \
  --delivery-config $CFG --tier 20 --gpus 0,1
uv run --no-sync python -m scripts.injection.rollout.parity --left $RID --right $PID   # H5_PARITY=PASS compared=210 … / RESET_PARITY=PASS compared=720 …
rm -rf artifacts/injection/$PID   # PASS 后
# run 10 例外：把 838 条 unused 全部 reset 一遍，结果写回 run 10 本体（约 7 分钟）
uv run --no-sync python -m scripts.injection.rollout.reset_check --run-id $RID --only-unused --tier 20 --gpus 0,1   # UNUSED_RESET=PASS checked=838 unused_left=0
```

阶段 9：

```bash
RID=<新编号>; CFG=scripts/configs/newtask-v2/delivery_400.json
# 第一阶段：候选 + 图 + 报告（约 35 分钟，tmux 起）
uv run --no-sync python -m scripts.injection.candidates --run-id $RID \
  --contract scripts/configs/newtask-v2/injection_contract_v3.json --delivery-config $CFG
# 第二阶段：h5 + mp4 + results.jsonl + 数轴图 + 报告（约 2 小时，tmux 起）
uv run --no-sync python -m scripts.injection.rollout --run-id $RID --delivery-config $CFG --tier 20 --gpus 0,1
```

冒烟用 `--groups RouteStick/easy --blocks 1` 与 `--groups RouteStick/easy --episodes 1 --label smoke`。

## 四、风险登记

| 风险 | 处置 |
|---|---|
| run 10 的 `feasibility/P0x1/` smoke 档与 `P01x20` 都有 RouteStick/easy ep0，`delivery_manifest.json` 去重时取的是哪一份未查 | 阶段 4 迁移时按 `delivery_manifest.json` 记录的 `h5_path` 选取，另一份进 `logs/smoke/` |
| `record_dataset_<task>_metadata.json` 由录像器落在组目录，位置不受控 | 保持原位随组目录一起 `mv`，`.gitignore` 反选其入库 |
| `results.jsonl` 由生成器追加写、收尾步整文件重写，中断在重写期间会损坏 | 写临时文件后 `os.replace` |
| BinFill h5 单条 900 MB，算 `h5_sha256` 在 `close()` 后串行做会拖慢 worker | 与现在 `delivery --hash full --workers 8` 同量级，10 轮实测可接受；若拖慢改为收尾步并行算 |
| `hf_release.py` 仍读 `delivery_manifest.json` | R6 不改，`INJECTION.md` 记明 |

## 五、盲区诚实清单

- 「逐字节确定」的证据只有 RouteStick/easy ep0 一条（h5 与 mp4 各一次两两相同），BinFill demo 直出的 h5 与 VideoRepick / VideoUnmaskSwap 的 h5 尚无跨次对照；阶段 5 若出现散列不一致，先用 `h5_compare.py` 判断是内容差异还是写入层非确定，不能直接判新链路有 bug。
- BinFill 的 mp4 经 `imageio` 二次编码，逐字节是否确定未验证，L3 只比帧数。
- 3 条 `BinFillDemoError`（ffmpeg `Broken pipe`）根因未查，属偶发，重跑时可能变成成功；L3 的 `failure_mismatch` 对这 3 条只记不判。
- L2 的旧 `window_timeline.py extract` 从未对 run 10 跑过，耗时未实测。
- 阶段 6 重出的图与报告基于 run 10 的 1796 条，与 07 版本不可逐图对照。
- 方案 B 只实证 210 条，其余 1632 条的一致性是由确定性推断的；若日后要宣称「逐条一致」须补跑 A。
- reset 核验的 `outcome` 现在是中文字符串「通过」，迁移为 `ok` 布尔值时按 `outcome == "通过"` 判，其余七类归 `error_type`；VideoRepick/xhard 与 VideoUnmaskSwap/xhard 各查了 54 条而非 51 条，说明有在飞批次 `counted=false` 的行，迁移时原样保留 `counted`。
- 删除轻量包后 08 / 09 的尾迹核验脚本随之消失，只在 git 历史可查。

## 六、留档与 commit 纪律

每阶段一个 commit，subject 体例 `11.0N <一句话>`，body 按 `~/.claude/CLAUDE.md` 的六项写；只 `git add` 本阶段明确路径。阶段 0 在 `newtask-v2` 上提交并照常 `git push`；阶段 1 起在用户指定的新分支上提交，首次推送前先问用户是否 `git push -u`，获准后每次 commit 后照常 `git push`。
