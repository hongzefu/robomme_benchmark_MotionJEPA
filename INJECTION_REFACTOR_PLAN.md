# 新值注入链路重构计划：两阶段、两个 jsonl、其余进 logs

> **权威性**：本文是新值注入链路（候选分布 → 真实 HDF5）重构的唯一计划，提交在 `newtask-v2` 分支。代码锚点一律以 `92e8152`（10.84）为准；工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`。commit 编号沿用「主序号.流水号」体例，从 **11.01** 起。
> **分支**：实施（第一部分第九节阶段 1）开始时从 `newtask-v2` 另开新分支，**分支名由用户在批准阶段 1 时指定**，本文不预设；计划文档本身留在 `newtask-v2`。
> **授权边界**：本文只规划不实施。第一部分第九节的每个阶段都须用户单独批准后才动手；「未来可做」不等于本轮授权。
> **口径来源**：现行 h5 生成流程 = `20260912-contract-v3-10`（每 env 400 条严格交付），其机制细节见 [scripts/NEW_VALUE_INJECTION_PIPELINE.md](scripts/NEW_VALUE_INJECTION_PIPELINE.md)；重构后该文档被 `scripts/INJECTION.md` 取代。
> **决策史**：契约 v1→v3、xhard、BinFill demo 直出等历史决策本轮**不整理、不搬运**（用户 2026-09-17 原话「决策史先不管」），全部留在 git 历史与 `newtask-v2` 分支。

---

# 第一部分（给人看）

## 一、总览

**一句话方案**：把现在 11 个子命令、6 个独立脚本、7 份判定 JSON、6 份报告 md 的链路收成两个阶段目录——`candidates/` 出一份 `candidates.jsonl` 加图加报告，`rollout/` 出 h5、mp4、一份 `results.jsonl` 加数轴图加报告——其余一切机器产物进各自的 `logs/`，用户只看两个 jsonl、h5 和图。

**已定死口径**（用户拍板原话逐字保留，依据小节在括号内）：

1. 「我只在乎现在的h5生成流程」——范围只覆盖 10 轮实际走的链路，校准、对拍、回放、env-check 等验证性分支不再是流程的一部分（第二节、第七节）。
2. 「候选分布产生只保留一个json 碰撞筛查和其他候选筛查 也增加写入这个json」「如果json需要改为jsonl你来自己决定」——定为 `candidates.jsonl`，每行一条候选并内嵌 `screening` 块（第四节 4.1）。
3. 「保留所有的出图和报告」「其他的放入logs文件夹 用户都不看」——第一阶段的三类跑前图与分布报告全留，判定 JSON、拒绝明细、配额报表进 `candidates/logs/`（第五节）。
4. 「第二阶段rollout保留h5 mp4 回放 和一个jsonl记录结果 成功/失败的都要记录 剩下的放入log 用户都不看 只用jsonl和h5判断成功」——定为 `results.jsonl`，成功与失败同表；运行参数、清单、生成器日志、timeline JSON 进 `rollout/logs/`（第四节 4.2）。
5. 「正式 / 备用的区分并入结果行」——`results.jsonl` 每行带 `role ∈ {primary, spare, failed}`，不再单独出 `delivery_manifest.json`（第四节 4.2、第六节）。
6. 「对应的script也分为这两个阶段单独建文件夹」——`scripts/injection/candidates/` 与 `scripts/injection/rollout/`（第三节 3.3）。
7. 「决策史先不管 这次重构需要从新branch开始」「我说的是修改开始后！你需要和用户确定分支名称」——实施开始时另开分支、分支名届时由用户指定，计划文档留在 `newtask-v2`；历史文档删而不搬（引言块）。
8. 现有 run 10 的 844 GB 产物**不重跑**，目录原地按新拓扑移动，h5 逐文件 SHA-256 核对（第九节阶段 7）。
9. 「需要加入修改前后的对拍」——候选、图表数据层两层对拍全量必做；h5 / mp4 对拍全量或抽样**待用户在第八节四个方案里选定**，选定后再批阶段 5。

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
    ├── results.jsonl                             每条实跑一行，成功失败同表，带 h5 路径、SHA-256、role；入库
    ├── figures/windows_overview.png              14 组各取最短 / 中位 / 最长；入库
    ├── figures/<task>/<diff>/4_windows.png       该组逐条数轴；不入库
    ├── ROLLOUT.md                                每组通过表、失败清单、视频状态；入库
    ├── WINDOWS.md                                数轴公式、汇总表、慢条剔除表；入库
    └── logs/                                     run_parameters.json、manifest.json、生成器日志、
                                                  windows_timeline.json、result.json、smoke/；入库
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
    ├── __main__.py                python -m scripts.injection.rollout --run-id … 一次出全部
    ├── run.py                     进程池编排、清单、续跑、role 判定；自 scripts/injection/run.py + delivery.py 合并
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

之后每行一条候选，字段 = 现在 `specs/<task>/<diff>.json` 的 `episodes[i]` 原样，再加两块：

```json
{"record": "candidate", "task": "VideoRepick", "difficulty": "easy", "episode": 0, "block": 0,
 "seed": 9000, "spec_sha256": "…",
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

每行 = 现在 `episode_results.jsonl` 的一行原样（`task / episode / attempt / seed / difficulty / ok / h5_path / timestep_count / binfill_demo / video / wall_s / phases / injection_evidence / runtime_checks / bound / …`，失败行另有 `failure_class / error_type`），再加三个字段：

| 字段 | 值 | 写入时机 |
|---|---|---|
| `h5_sha256` | 成品 h5 的 SHA-256；失败行 `null` | 生成器在 `close()` 后核验阶段顺手算，与现在算视频散列同处 |
| `h5_bytes` | 字节数；失败行 `null` | 同上 |
| `role` | `primary`：该组按 episode 升序前 `target_h5` 条通过；`spare`：其余通过；`failed`：未通过 | 实跑结束后 `rollout/run.py` 的收尾步原子重写整个文件 |

「只用 jsonl 和 h5 判断成功」的判法：`ok == true` 且 `h5_path` 存在且 `h5_sha256` 相符 ⇒ 成功；`role` 决定是否计入 400 条交付。

## 五、出图与报告：各出哪些、删哪些

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

## 六、追溯性：守住三条，处理两处

设计合理且比现在更易追溯，前提是：

1. **`logs/` 照常进 git**。放的不只是文本日志，还有判定 JSON、运行参数、实跑清单这些机器可读文件。「用户不看」不等于「不存」。
2. **两个 jsonl 靠主键互指**。候选行与结果行都带 `(task, difficulty, episode)` 与 `spec_sha256`（结果行在 `injection_evidence.spec_sha256`），结果行再带 `h5_path / h5_sha256`。任一 h5 都能反查到候选、候选的筛查证据、当时的运行参数。
3. **候选行内嵌筛查证据**。现在只有视频任务候选带 `collision`，BinFill 只有 `sampling_cells`；合并后四任务统一带 `screening`，比现在只在 `plan_stats.json` 记组级总数更细。

会变化的两处及处置：

- **正式 / 备用**：由 `delivery_manifest.json` 改为结果行 `role` 字段（口径 5）。HF 发布脚本 `scripts/hf_release.py` 目前读 `delivery_manifest.json`，本轮不改它，但在 `scripts/INJECTION.md` 记明「再次发布须先改 hf_release.py 读 `results.jsonl` 的 `role`」。
- **决策史**：四份计划 md 删除后只在 git 历史与 `newtask-v2` 分支可查（口径 7）。

## 七、删除清单

- **代码**：`scripts/injection/env_check.py`、`replay.py`、`contract_build.py`、`plots.py`、`campaign.py`（其 plan / check / run / delivery 逻辑迁入两个新包后整文件删）、`scripts/injection-before-2d/` 整个目录（含 `check_doc_links.py`、`windows_timeline.json`、`figures/`）。`h5_compare.py` **不删**，搬为 `scripts/injection/rollout/h5_compare.py`，只在对拍 SHA-256 不一致时用来定位差异（第八节 8.2）。
- **删除时机**：旧的出图、事件表、timeline 脚本要先对 run 10 跑一遍留下基线（第九节阶段 3），之后才能删。
- **配置**：`injection_contract_v1.json`、`injection_contract_v2.json`。
- **文档**：第五节表中标「删」与「重写」的六份；`scripts/README.md` 第四节改为指向 `scripts/INJECTION.md`。
- **轻量包**：`docs/validation/newtask-v2/` 下 `20260910-new-values-04`、`20260911-contract-v3-06`、`20260911-contract-v3-07`、`20260912-contract-v3-08`、`20260912-contract-v3-09`、`20260912-contract-v3-10` 六个目录。其余非 injection 轮次目录不动。
- **run 10 目录内**：不删只移（第九节阶段 7）。`env_check/`、`env_check_result*.json`、`feasibility/P0x1/`、`manifests/`、四份 `feasibility_result*.json`、`delivery_manifest.json`、`manifest.json`、`plan_stats.json`、`check_result.json`、`logs/*` 全部进对应阶段的 `logs/`。
- **`.gitignore`**：`artifacts/injection` 段与 `scripts/injection-before-2d/figures` 段整体替换（第二部分三）。

## 八、修改前后的对拍

### 8.1 修改前的生成花了多久（run 10 实测，2026-09-12，双卡各 20 worker）

| 阶段 | 规模 | 墙钟 | 出处 |
|---|---|---|---|
| `plan` 冻结候选 | 14 组 3400 条 | 675.3 秒（11 分钟） | `logs/plan.log` `elapsed_s=675.3` |
| `check` 静态与碰撞筛查 | 3400 条，碰撞扫掠 1700 条 | 1338.5 秒（22 分钟） | `logs/check.log` `elapsed_s=1338.5` |
| 实跑 | 1842 条，通过 1796 | 6684.4 秒（1 小时 51 分），16.12 条/分 | `feasibility/P01x20/run_summary.json` `elapsed_s` |
| 成功条单条 | 1796 条 | 中位 126 秒、最大 241 秒；串行总和 63 小时 | `episode_results.jsonl` `wall_s` |
| 超时条单条 | 21 条 | 600 秒被终止（最长实测 626 秒） | 同上 |
| 产物体积 | h5 1796 个 | 880 GB，中位 424 MB | `delivery_manifest.json` `h5_bytes` |

磁盘：`/data` 总 14 TB，已用 12 TB，**余 1.9 TB**（2026-09-17 `df`）；全量重跑一份 880 GB 放得下，但跑完必须删一份。GPU 0 / 1 当前空闲（利用率 0%）。

### 8.2 关键前提：h5 与 mp4 都是逐字节确定的，对拍只比 SHA-256

run 10 里 RouteStick/easy ep0 被生成过两次：smoke 档 `P0x1`（单卡 1 worker，13:06）与正式档 `P01x20`（双卡 40 worker，13:29）。两次的成品：

| 文件 | 字节数 | SHA-256 前 16 位 | 结论 |
|---|---:|---|---|
| `RouteStick_ep0_seed16000.h5` | 200,071,952 | `27d7e1c62583025e` 两次相同 | h5 逐字节确定 |
| `RouteStick_ep0_seed16000_easy_watch….mp4` | 6,648,548 | `468cf3b5c00344e3` 两次相同 | 录像器直出的 mp4 逐字节确定 |

因此**对拍不需要逐 dataset 遍历**：新链路生成时在 `close()` 后算的 `h5_sha256` 直接与 `delivery_manifest.json` 里 run 10 的 1796 个散列比即可，旧文件零额外读取。`h5_compare.py` 只在散列不一致时用来定位是哪个 dataset 变了。两个例外：BinFill 的 mp4 经 `imageio` 二次 libx264 编码，逐字节是否确定未验证，**只比帧数**，其 h5 照比；21 条超时与 25 条规划失败比 `failure_class / error_type`（10 轮已证明超时 seed 三轮复现，是确定性的）。

### 8.3 三层对拍

| 层 | 比什么 | 怎么比 | 规模与耗时 | 判定行 |
|---|---|---|---|---|
| L1 候选（**全量必做**） | 新 `candidates` 包对 run 10 的契约与配置重算 3400 行 | 逐行 `spec_sha256` 与 `specs/<task>/<diff>.json` 比；`screening` 里的碰撞结论与旧 `collision` 字段比 | plan 11 分钟 + screen 22 分钟 ≈ 35 分钟，零磁盘 | `CANDIDATES_EQUIVALENCE=PASS compared=3400 differences=0` |
| L2 图与报告数据层（**全量必做**） | 旧脚本与新脚本对**同一份 run 10** 各出一套 | 删旧脚本前先用 `plot_injection_before_2d.py`、`event_tables.py`、`window_timeline.py extract` 对 run 10 跑出基线（三者此前只对 07 跑过）；新 `figures.py / report.py / windows.py` 出的 98 + 15 张 PNG 逐字节比、事件表逐行比、`windows_timeline.json` 逐键比 | 旧 extract 要打开 1796 个 h5 读 T 与分段，**未实测**，估 10 到 30 分钟；出图数分钟；零额外磁盘 | `FIGURES_EQUIVALENCE=PASS png=113 differences=0`、`TABLES_EQUIVALENCE=PASS rows=… drift=0`、`TIMELINE_EQUIVALENCE=PASS episodes=1796 differences=0` |
| L3 h5 / mp4（**全量或抽样，待用户选**） | 新 `rollout` 包按 `candidates.jsonl` 重新生成 | 成功条比 `h5_sha256`（BinFill 另比 mp4 帧数，其余任务 mp4 也比 SHA-256）；失败条比 `failure_class / error_type` | 见 8.4 | `H5_PARITY=PASS compared=N sha_mismatch=0 mp4_mismatch=0 failure_mismatch=0` |

### 8.4 L3 的四个方案（待用户确认）

条数按「每组 block 0 的前 N 条」取，覆盖 14 组；耗时按双卡 40 worker、机器空闲估，含超时条封底（每组前 1 条里就有 VideoRepick/easy ep0 这条 626 秒超时）。

| 方案 | 条数 | 预计墙钟 | 临时磁盘 | 覆盖到的结果类型 | 能证明什么 |
|---|---:|---|---:|---|---|
| **A 全量（推荐）** | 1842 | ≈ 1 小时 51 分（与 run 10 相同） | 880 GB，余 1.9 TB 可容 | 1796 成功 + 21 超时 + 25 规划失败 | 新链路**逐条**复现已交付数据集；PASS 后新旧两份逐字节相同，删一份即可 |
| B 每组前 15 | 210 | ≈ 15 到 20 分钟（理论下限 11.5 分钟） | ≈ 90 GB | 205 成功 + 3 规划失败 + 2 超时 | 四任务四档全覆盖、三类结果都有样本 |
| C 每组前 5 | 70 | ≈ 10 到 12 分钟（下限 4 分钟，被 626 秒超时封底） | ≈ 30 GB | 68 成功 + 1 规划失败 + 1 超时 | 四任务四档全覆盖 |
| D 每组前 1 | 14 | ≈ 10 分钟（被 626 秒超时封底） | ≈ 6 GB | 13 成功 + 1 超时 | 只证明链路能通 |

推荐 A 的理由：生成是确定性的，任何一条散列不同都是真 bug；两小时 GPU 与 880 GB 临时盘都付得起；只有全量能宣称「重构后的链路产出与已发布到 HF 的数据集逐字节一致」。B 到 D 都只能证明「抽到的条一致」，剩余条的等价性靠确定性推断。

## 九、实施步骤

每阶段单独获批、单独 commit（11.01 起），判据不过不进下一阶段。

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 本计划写入 `newtask-v2` | 本文入库；`git status -sb` 无遗留 |
| 1 | 先与用户确定分支名并从 `newtask-v2` 切出；建 `scripts/injection/candidates/`：搬四个核心模块，写 `screen.py` 与 `__main__.py`，产 `candidates.jsonl`；对 run 10 重算（L1 对拍） | `CANDIDATES_EQUIVALENCE=PASS compared=3400 differences=0`；`SCREENING_FILLED=PASS rows=3400 null_geometry=0` |
| 2 | 生成器 `load_episode_specs` 读 jsonl，`close()` 后加 `h5_sha256 / h5_bytes`；跑 1 条 smoke（RouteStick/easy ep0） | `LOADER_PARITY=PASS`（同一条从 jsonl 与从旧 json 加载的 dict 相等）；`SMOKE_H5_PARITY=PASS compared=1 sha_mismatch=0`（与 run 10 的 `27d7e1c6…` 相同） |
| 3 | 删旧脚本前用旧 `plot_injection_before_2d.py`、`event_tables.py`、`window_timeline.py extract` 对 run 10 出一套基线到 `candidates/logs/baseline/` 与 `rollout/logs/baseline/` | `BASELINE_CAPTURED=PASS png=113 tables=14 timeline_episodes=1796` |
| 4 | 建 `scripts/injection/rollout/`：合并 run + delivery，写 `role / h5_sha256 / h5_bytes`；用 run 10 的 `episode_results.jsonl + delivery_manifest.json` 迁移出 `results.jsonl` | `RESULTS_EQUIVALENCE=PASS rows=1842 primary=1600 spare=196 failed=46` |
| 5 | L3 对拍：按用户选定的方案用新 `rollout` 包重新生成到临时 run-id，与 run 10 比散列与失败类型；PASS 后删临时产物 | `H5_PARITY=PASS compared=N sha_mismatch=0 mp4_mismatch=0 failure_mismatch=0` |
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
| `scripts/injection/rollout/parity.py` | 新写 | 读两个 run 的 `results.jsonl`（旧 run 用迁移后的），按 (task, difficulty, episode) 配对，比 `h5_sha256`、mp4 SHA-256 或帧数、`failure_class / error_type`，打 `H5_PARITY` 判定行 |
| `scripts/injection/rollout/__main__.py` | `campaign.py` 的 `cmd_run` feasibility 分支 | 顺序：run → role → windows → report |
| `scripts/generate_dataset_newseed.py` | 现有 | `load_episode_specs`：清单 `spec_path` 以 `.jsonl` 结尾时按 `(task, difficulty)` 过滤行、跳过 header；`_worker` 的 `close()` 后核验段加 `h5_sha256 / h5_bytes` |
| `scripts/INJECTION.md` | 新写 | 现行口径、两阶段命令、两个 jsonl 字段表、追溯链、「再次 HF 发布须改 hf_release.py」 |
| 一次性迁移脚本 `scripts/injection/_migrate_run10.py` | 新写，阶段 7 用完即删 | `specs/*.json + plan_stats + check_result` → `candidates.jsonl`；`episode_results.jsonl + delivery_manifest.json` → `results.jsonl`；目录 `mv`；SHA-256 核对 |

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

阶段 5（以方案 A 为例；B 到 D 加 `--episodes N` 只跑每组前 N 条）：

```bash
RID=20260912-contract-v3-10; PID=$RID-parity; CFG=scripts/configs/newtask-v2/delivery_400.json
# 用 run 10 的 candidates.jsonl 原样重跑（约 1 小时 51 分，tmux 起，日志落 artifacts/injection/$PID/rollout/logs/）
uv run --no-sync python -m scripts.injection.rollout --run-id $PID --candidates artifacts/injection/$RID/candidates/candidates.jsonl \
  --delivery-config $CFG --tier 20 --gpus 0,1 --no-figures
uv run --no-sync python -m scripts.injection.rollout.parity --left $RID --right $PID   # H5_PARITY=PASS compared=1842 …
rm -rf artifacts/injection/$PID   # PASS 后
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
- 删除轻量包后 08 / 09 的尾迹核验脚本随之消失，只在 git 历史可查。

## 六、留档与 commit 纪律

每阶段一个 commit，subject 体例 `11.0N <一句话>`，body 按 `~/.claude/CLAUDE.md` 的六项写；只 `git add` 本阶段明确路径。阶段 0 在 `newtask-v2` 上提交并照常 `git push`；阶段 1 起在用户指定的新分支上提交，首次推送前先问用户是否 `git push -u`，获准后每次 commit 后照常 `git push`。
