# 新值注入链路重构计划：两阶段、两个 jsonl、其余进 logs

> **权威性**：本文是新值注入链路（候选分布 → 真实 HDF5）重构的唯一计划，当前位于 `newtask-v2.1refractor` 分支。生产代码锚点为 `92e8152`（10.84），对抗审查锚点为 `956703e`（11.06）；工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`。commit 编号沿用「主序号.流水号」体例，接续当前 `git log`。
> **分支**：本计划与全部实施都在 **`newtask-v2.1refractor`** 上（用户 2026-09-17 原话「这个md计划 要从newtask-v2.1refractor开始」），该分支自 `newtask-v2` 的 `bf2c9ac`（11.04）切出；11.01 到 11.04 四条计划提交已在 `newtask-v2` 上，随切分支带入。
> **授权边界**：本文只规划不实施。第一部分第十节的每个阶段都须用户单独批准后才动手；「未来可做」不等于本轮授权。
> **当前授权更新（2026-09-18）**：用户后续原话「一口气全做完 不要再来问我了」，剩余阶段 3～9 已一次授权，覆盖前述逐阶段询问要求。按具名硬闸连续执行，保留环境冻结、数据完整性和恢复协议等技术约束。
> **口径来源**：现行 h5 生成流程 = `20260912-contract-v3-10`（每 env 400 条严格交付），其机制细节见 [scripts/NEW_VALUE_INJECTION_PIPELINE.md](scripts/NEW_VALUE_INJECTION_PIPELINE.md)；重构后该文档被 `scripts/INJECTION.md` 取代。
> **决策史**：契约 v1→v3、xhard、BinFill demo 直出等历史决策本轮**不整理、不搬运**（用户 2026-09-17 原话「决策史先不管」），全部留在 git 历史与 `newtask-v2` 分支。
> **本轮修订**：用户原话「有哪些需要用户注意 其他的你来决策修改md计划」「需要注意的 现在就让我决策」。依据 [九项对抗审查](docs/validation/newtask-v2/20260917-injection-refactor-audit.md) 修订设计与验收，不代表代码已经实现或实跑已经通过。
> **本轮范围再次确认**：用户原话「不要执行 只改计划md！」。本轮只修改本文；下列新文件、测试、命令、候选重算、reset 和迁移均为未来计划，不在本轮创建或执行，也不更新其他文档。

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
7. 「决策史先不管 这次重构需要从新branch开始」「我说的是修改开始后！你需要和用户确定分支名称」「这个md计划 要从newtask-v2.1refractor开始」——分支定为 `newtask-v2.1refractor`，计划与实施都在其上；历史文档删而不搬（引言块）。
8. 现有 run 10 的产物**不覆盖、不重跑本体**，目录原地按新拓扑移动；现有 h5、mp4、元数据逐文件清单与 SHA-256 核对，并改写活跃路径（第十节阶段 7）。
9. 「需要加入修改前后的对拍」「使用B 每组前 15」——候选、图表数据层、reset 核验三层全量对拍；h5 / mp4 对拍取**方案 B，每组 block 0 前 15 条共 210 条**（第九节 9.4）。
10. 「有一部分json配置是只处理不生成h5的是怎么回事 也要保留 在rollout/ 中要做reset验证」——`delivery_400.json` 的 `extra_candidates=50` 那 700 条只做 `make + reset + close` 的候选**保留**，核验代码放 `scripts/injection/rollout/reset_check.py`，结果作为 `kind="reset"` 的行并入 `rollout/results.jsonl`（第四节 4.3）。
11. 「需要作为test episode回写入candidates.jsonl 写入成功与否」「candidates.jsonl要作为启动环境的唯一入口」「unused不消灭」「run 10 迁移时……838 条也 reset 一遍 要做」「test 的 primary 仍是每组前 50 条通过者 不变」——每行候选带 `split ∈ {train, test}` 与 `role ∈ {pending, primary, spare, failed, unused}`，rollout 结束后回写 `role`；新 run 保留 `unused`，run 10 迁移时例外地把 838 条 unused 全部 reset（第五节）。
12. 「补入重算证据并标明来源（推荐）」——run 10 在 L1 重算 3400 条时采集逐条拒绝明细，标记 `reconstructed`；不能冒充 2026-09-12 当时保存的原始证据（第四节 4.1）。
13. 「只把 h5 一致作为硬条件，视频内容差异单列、不阻塞」——L3 的视频对拍单列诊断，不参与 `H5_PARITY`；有差异不得写成视频一致。该决定不取消迁移时保留既有视频的完整性要求（第九节 9.2）。

**用户需要知道的边界**：方案 B 只证明 210 条抽样的生成结果，剩余 1632 条不推断一致；838 条 unused 全部尝试后可能有失败，“全部检查过”不等于“全部通过”。慢条仍按原规则从数轴统计中剔除，不删除对应 h5、不改变正式交付角色。视频诊断与重算证据的解释按口径 12、13 执行；其余九项问题的技术处置由本计划定死，无待选实现方案。

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
│   ├── contract.py  sampling.py  specs.py  categories.py     搬迁；specs 另加只读过程采集
│   ├── io.py                     候选封套读取、旧 spec 校验和身份校验；只用标准库
│   ├── screen.py                  几何 / 碰撞 / 配额 / 可复现筛查，逐行写回 screening，组级进 logs
│   ├── figures.py                 三类跑前图，自 injection-before-2d/plot_injection_before_2d.py 搬入
│   └── report.py                  DISTRIBUTION.md，自 injection-before-2d/event_tables.py 搬入
└── rollout/                       第二阶段
    ├── __main__.py                python -m scripts.injection.rollout --run-id … 一次出全部：run → role → reset_check → windows → report
    ├── run.py                     进程池编排、清单、续跑、唯一结果表与 role；自 run.py + delivery.py 合并
    ├── reset_check.py             实跑区间之后的候选只 make + reset + close，每组攒够 50 条通过即停；自 scripts/injection/env_check.py 搬入
    ├── windows.py                 从 h5 抽 timeline 并出数轴图；自 window_timeline.py + plot_sampling_windows.py 合并
    ├── single_binfill.py          可选工具，不在主流程；自 plot_binfill_medium_single.py 搬入
    └── report.py                  ROLLOUT.md 与 WINDOWS.md
```

`scripts/generate_dataset_newseed.py` 留在原位，改动限定在候选输入适配、采样快照解析和 `close()` 后 h5 散列核验；具体函数范围见第二部分 R2。`scripts/INJECTION.md` 是唯一流程文档。

## 四、两个 jsonl 的行结构

### 4.1 `candidates.jsonl`

首行是 header 记录。候选封套格式 `candidate_schema_version=1` 与旧规格 `spec_schema_version=1`、采样配置 `schema_version=3` 是三个不同版本，不能混写。header 承接每组旧文档溯源信息，另保存启动环境所需的完整采样快照和交付配置快照；下面是字段示意，省略的完整快照仍须实际写入：

```json
{"record": "header", "run_id": "…", "candidate_schema_version": 1, "spec_schema_version": 1, "generator_seed": 20260909,
 "generator_version": "…", "contract": "scripts/configs/newtask-v2/injection_contract_v3.json",
 "contract_sha256": "…", "sampling_config_sha256": "…", "delivery_config": "…/delivery_400.json",
 "groups": 14, "candidates": 3400}
```

完整 header 还含 `group_provenance`（逐组原 `derived_seed / generator_version / blocks / sampling_config_sha256`）、`sampling_config`（原采样 JSON 的完整对象）、`delivery_config_snapshot`、`runtime`（`layout="train"` 与现有 `gym.make` 固定参数）、`identity_sha256`。后者覆盖这些不可变快照和按主键排序的候选身份/旧规格，排除 `run_id / role / error_type / roles / screening` 及派生运行的来源说明；回写角色不得改变它。旧 `sampling_config_sha256` 仍是 `operand_sha256` 的取值域口径，另用 `sampling_file_sha256` 记录原文件字节散列，不能偷换两者。

之后每行一条候选：**旧 `episodes[i]` 完整放进 `spec`，管理字段放在外层**。示意：

```json
{"record": "candidate", "task": "VideoRepick", "difficulty": "easy", "episode": 0, "block": 0,
 "seed": 9000, "spec_sha256": "…", "split": "train", "role": "pending", "error_type": null,
 "spec": {"episode": 0, "task": "VideoRepick", "difficulty": "easy",
          "layout": {…}, "objects": {…}, "actions": {…}, "sampling_cells": {…},
          "collision": {…}, "spec_sha256": "…"},
 "screening": {"geometry": "PASS",
               "collision_initial": "PASS", "collision_sweeps": ["PASS", "PASS"], "min_g_m": 0.0134,
               "evidence_origin": "reconstructed", "count_unit": "episode_proposal", "candidates_tried": 3,
               "rejected_before_accept": {"geometry": 2, "contact": 0, "numerical_boundary": 0, "uncertified": 0}}}
```

- `spec_sha256` 沿用 `specs.py::record_sha256` 与生成器 `spec_record_sha256` 的真实算法：只排除旧记录里的 `spec_sha256 / collision`，其余键全部参与，包括 `task / difficulty / episode / sampling_cells`。只对 `candidate["spec"]` 验旧散列，绝不把管理字段传进去；外层主键与 `spec` 必须一致，两处散列必须一致。L1 对 3400 条重算散列并比较完整旧记录，不能只比自报散列。
- `spec` 的有无键也原样保留：BinFill、RouteStick 没有旧 `collision` 时不补键。图表从 `spec` 读原字段，加载器只把深拷贝后的 `spec` 传给环境。这样 `role` 回写不会改变旧规格的规范化序列化字节或环境输入。
- 拒绝过程必须在生成循环中采集，不能从 `plan_stats` 总数反推。`specs.py::_place_binfill_cubes`、两个视频任务的候选循环、`_count_rejection` 增加独立观测输出；不额外采样、不改分支、循环次数和随机数消费。记录 `(task, difficulty, episode, object_id, trial, reason, proposal)`；方块摆放用 `count_unit="object_proposal"`，视频整体摆放用 `episode_proposal`，RouteStick 无拒绝重试则用 `not_applicable` 与 `null`。
- BinFill/medium 的旧 `5281` 是 300 个 episode 内的方块摆放尝试总数，其中几何拒绝 3184 次，不是 5281 条 episode。新候选每行聚合本 episode 的实际观测增量；全部拒绝事件写 `candidates/logs/rejections.jsonl`，不沿用旧的前 64 条截断。核对 `tried = accepted + rejected`，再按组/块汇总与旧统计对齐。
- 用户已选重算补证：run 10 的 L1 重算成功且逐条旧规格一致后，填 `evidence_origin="reconstructed"`，同时记录重算 commit、配置散列、时间与旧运行编号；新运行实时采集填 `generated`。旧日志原封保留；不能把重算值称为当时的观测。原资料缺失且重算未完成时留 `null / unavailable`，不能填零冒充证据。
- 不适用碰撞扫掠的任务填 `collision_initial / collision_sweeps / min_g_m = null`，不伪造 PASS；`geometry` 对四任务都按实际检查填写。
- 组级汇总（每组拒绝总数、配额覆盖、可复现对拍）不重复进每行，落 `candidates/logs/quota_report.json` 与 `check_result.json`。

### 4.2 `results.jsonl`

两种行共用一个文件，用 `kind` 区分；两种行都带 `split`（train / test）与 `role`，取值与回写到 `candidates.jsonl` 的完全一致（第五节 5.3）。

**`kind="h5"` 行**保留现在 `episode_results.jsonl` 的执行字段（`task / episode / attempt / seed / difficulty / ok / h5_path / timestep_count / binfill_demo / video / wall_s / phases / injection_evidence / runtime_checks / bound / …`，失败行另有 `failure_class / error_type`），增加外层 `spec_sha256 / split` 以及下列字段。`kind / split / role` 由编排层归并原始日志时写入，避免扩大生成器 worker 的职责：

| 字段 | 值 | 写入时机 |
|---|---|---|
| `kind` | `"h5"` | 编排层读取生成器结果时 |
| `h5_sha256` | 成品 h5 的 SHA-256；失败行 `null` | 生成器在 `close()` 后核验阶段顺手算，与现在算视频散列同处 |
| `h5_bytes` | 字节数；失败行 `null` | 同上 |
| `role` | `primary`：该组按 episode 升序前 `target_h5` 条通过；`spare`：其余通过；`failed`：未通过 | 实跑结束后 `rollout/run.py` 的收尾步原子重写整个文件 |

**`kind="reset"` 行**保留原 `env_check` 的 `task / difficulty / episode / seed / spec_sha256 / outcome / error_type / error / wall_s / phases / bound / injection_bound / counted`，增加 `kind="reset" / split="test" / h5_path=null / role`。`ok` 必须与 `outcome == "通过"` 一致，矛盾即拒绝迁移；不把 `outcome` 的中文分类误写进异常类名 `error_type`。正常运行中，按 episode 升序前 50 条通过者为 primary，其余通过者 spare，失败者 failed；run 10 的 unused 补查不改原 primary。

`results.jsonl` 是**每个键只有一个终态的当前结果表**，唯一键为 `(kind, task, difficulty, episode)`。生成器原始追加行进入 `rollout/logs/attempts/`，保留调用编号、执行范围和完成序；收尾归并唯一结果，再原子替换当前表。不能对当前表盲目追加，也不能先转字典掩盖输入重复。默认续跑复用成功和失败终态，强制复验用新 run；相同 run 的重复终态输入须逐字段一致，否则报冲突，不按 `attempt` 大小猜测新旧。

「只用 jsonl 和 h5 判断成功」的判法：`kind="h5"` 行要 `ok == true` 且 `h5_path` 存在且 `h5_sha256` 相符；`kind="reset"` 行本就无 h5，只看 `ok`。两种行的 `role` 各自决定是否计入交付（400 条 h5、700 条 reset 候选）。

### 4.3 只做 reset 不出 h5 的候选是怎么回事

这是 2026-09-12 用户口径「在此基础上给每个env每个难度再增加50个候选不生成数据集 只生成候选 可以产生环境」的落地，配置在 `delivery_400.json` 的 `extra_candidates: 50`：

- `plan` 铺候选时按 `blocks × 100 ≥ run_episodes + 50` 多铺一个 block，所以 3 档 env 每组 300 条、4 档 env 每组 200 条，合计 3400 条，而实跑只用前 1842 条。
- 实跑区间之后的候选（如 BinFill/easy 从 ep155 起）按 episode 序逐条只做 `gym.make(任务, episode_spec=规格) → env.reset() → env.close()`，不套录像器、不建 planner、不 step，零 h5 / mp4；每组攒够 50 条通过即停。run 10 实测 14 组各查 51 到 54 条、全部通过、交付 700 条，双卡 40 worker 共 492.7 秒，`make` 中位 20 秒、`reset` 中位 0.07 秒。
- 语义边界：只证明「该候选能产生环境」，不证明能出 h5（不覆盖 step 期绑定错误、规划可解性、录像器步数保护、任务成功判定）。
- 这 700 条已随 HF 发布进了 `meta/env_check/`，是交付物的一部分，所以保留。

重构后它是 `rollout/` 的一步：`reset_check.py` 对每组 `run_episodes` 之后的候选按序核验，结果按唯一键归并到 `results.jsonl`。恢复时先读已有终态，按相同批次顺序重建计数后再派缺失任务，重复执行不会重跑旧条或重复写行。组级判定写 `logs/reset_check_result.json`，正式全量判据为 `RESET_CHECK=PASS groups=14 checked=… passed=… delivered=700 shortfall=0`。

## 五、`candidates.jsonl` 的划分与回写：启动环境的唯一入口

用户 2026-09-17 原话：「只做 reset 不出 h5 的候选 需要作为test episode回写入candidates.jsonl 写入成功与否 results jsonl也需要体现」「candidates.jsonl要作为启动环境的唯一入口」；追问后拍板：「明白」（每档 50 条共 700 不改）「unused不消灭」「run 10 迁移时是否顺手把这 838 条也 reset 一遍 要做」「test 的 primary 仍是每组前 50 条通过者 不变」。

### 5.1 两个维度，不是并列的四类

每行候选在 4.1 的字段之外再带两个字段：

| 字段 | 取值 | 谁写、何时写 |
|---|---|---|
| `split` | `train`：episode < 该组 `run_episodes`；`test`：其余 | `candidates` 包冻结时按 `delivery_400.json` 写死，之后不变 |
| `role` | `pending` → `primary` / `spare` / `failed` / `unused` | 冻结时写 `pending`；`rollout` 结束后回写 |

**补查前：run 10 的已有状态。** 下表的 838 条尚未 reset，不是本计划补查完成后的最终数量：

| split | role | 含义 | run 10 补查前 |
|---|---|---|---:|
| train | primary | 出了 h5 且按 episode 升序进该组前 `target_h5` 条 | 1600 |
| train | spare | 出了 h5 但超出 `target_h5` 的余量，h5 保留 | 196 |
| train | failed | 未形成合格交付 h5；失败不能因存在残留文件改判成功 | 46 |
| test | primary | reset 通过且按 episode 升序进该组前 `extra_candidates=50` 条 | 700 |
| test | spare | reset 通过但超出 50 条 | 20 |
| test | failed | reset 失败 | 0 |
| test | unused | 该组攒够 50 条通过后停止，从未 reset 过 | 838 |

**补查后：按本计划将 838 条全部检查完，表格应如下。** 令 `X` 为这 838 条中 reset 通过的数量，`0 ≤ X ≤ 838`；原有 train 结果与 700 条 test primary 名单不变：

| split | role | 含义 | run 10 补查后 |
|---|---|---|---:|
| train | primary | 正式选用的 h5 | 1600 |
| train | spare | 成功生成的备用 h5 | 196 |
| train | failed | h5 生成失败，未形成合格交付 h5 | 46 |
| test | primary | 正式选用的测试候选，保持原名单 | 700 |
| test | spare | reset 通过的备用候选 | **20＋X** |
| test | failed | reset 失败的候选 | **838－X** |
| test | unused | 尚未检查的候选 | **0** |

**若 838 条全部通过，即 `X=838`：test spare 为 858，test failed 为 0，test unused 为 0。** 这是条件示例，不是实测结果；补查尚未执行，不能提前把 X 写死。补查前后均为 3400 条候选，其中 train 1842 条、test 1558 条。

700 是 14 个 env × 难度组各 50 条之和（BinFill 150、RouteStick 200、VideoUnmaskSwap 200、VideoRepick 150），不是每 env 50 条；这是 2026-09-12「给每个env每个难度再增加50个候选」的口径，用户确认不改。

### 5.2 `unused` 不消灭

新 run 沿用「每组攒够 50 条 reset 通过即停」的规则，停点之后未执行的 test 候选成为 `unused`。未选入局部执行范围或因中断而尚未执行的候选仍是 `pending`，不能冒充 failed；train 永不标 unused。组配额尚未满足时，未执行的 test 也保持 pending。

**run 10 是唯一例外**：`--only-unused` 首次调用先把当时 838 个 unused 键冻结到 `logs/unused_scope.json`，逐一核验全部键，完全绕开“通过 50 条即停”；续跑始终复用该范围和已完成终态，不能每次重新筛剩余角色导致分母缩小。通过者变 spare，失败者变 failed；原 700 个 primary 键及其结果不变。判据 `UNUSED_RESET=PASS checked=838 passed=… failed=… unused_left=0 primary_changed=0` 只表示全部尝试完，另须 `passed + failed = 838`，不要求失败数为零。约 7 分钟只是无失败超时情况下的粗估。

### 5.3 回写规则

- `rollout` 收尾只改候选外层 `role / error_type` 和 header 的派生 `roles` 计数，`spec`、身份与筛查来源不动。唯一结果表是执行状态依据，候选角色由它派生。
- 每个 run 只允许一个写入者；先保存唯一结果表，再回写候选，各自使用临时文件加 `os.replace`。两次替换不是跨文件原子事务；恢复时先按调用编号与完成序归并 `logs/attempts/` 中已落盘但未归并的完整终态，核验同键重复/冲突，再从唯一结果表重建候选角色，最后才调度缺失项。日志尾部半行不算终态，保留并标记中断位置，不能伪造成功或失败；不能因为当前表尚未更新而重跑已完成项。
- `primary / spare / failed` 候选必须各有且仅有一条对应结果，主键、`spec_sha256 / split / role / error_type` 相同；`pending / unused` 必须没有结果。`ROLES_CONSISTENT=PASS rows=3400 mismatch=0 duplicates=0 pending=… unused=…` 只证明互指正确；正式交付另验每组配额和 1600/700 总数，不能把局部对拍当成全量交付。
- 方案 B 使用临时 run 的**独立候选副本**：`--candidates` 跨 run 时只读导入，重置角色为 pending、清空 error，保留旧规格与筛查来源，记录 `parent_run_id / parent_candidates_sha256`；任何后续回写只针对副本。正常完成 210 条 h5 与 720 条 reset 后，该副本有 930 条结果、1632 条 pending、838 条 unused。导入前后检查源候选字节散列，判定 `PARITY_SOURCE_INTACT=PASS`。
- `--label smoke` 使用 `rollout/logs/smoke/<label>/` 下的独立候选副本和结果表，不回写正式候选、不自动跑全量 reset；显式选 1 条 test reset 作为最小验证即可。

### 5.4 唯一入口

起环境的三处以 `candidates.jsonl` 为唯一数据入口：行里的 `spec` 提供旧规格，header 提供完整 `sampling_config / runtime`；仍依赖仓库环境源码与资产。冻结后不再从可变的外部配置取值，若 CLI 同时给配置，只能校验与内嵌快照一致，不能覆盖。统一读取器在启动前核验封套版本、完整键集合、外层与 spec 身份一致、旧散列和采样快照源码指纹。

用户补充要求：「起环境的三处以 `candidates.jsonl` 为唯一数据入口 需要进入git追踪」。候选快照及本仓库实现的统一读取器、生成与 reset 入口均须进入 Git；忽略规则必须放行新运行的 `candidates/candidates.jsonl`，不能只靠强制添加一份既有文件满足要求。第三处策略侧入口仍是接口约定，本仓库不实现。

| 谁 | 读哪些行 | 怎么起 |
|---|---|---|
| `generate_dataset_newseed.py` 出 h5 | `split="train"` 与清单选定范围的交集 | `gym.make(task, episode_spec=行["spec"], sampling_config=header中该任务配置, ...)` + `RobommeRecordWrapper` + planner |
| `rollout/reset_check.py` | `split="test"`；普通模式按配额停止，only-unused 模式遍历冻结集合 | 使用相同 seed、difficulty、sampling_config、固定 kwargs 与 `spec` → `reset()` → `close()` |
| 策略侧日后起 test 环境 | `split="test"` 且 `role="primary"` | 同上，本仓库不实现 |

`seed` 必须等于 `SeedLayout("train").seed(task, episode, 0)`，不相等在建池前报错。test 行与 train 行用同一 layout，只是 episode 号在实跑区间之后；这里的 test 是自定义候选划分，不是官方 test seed 区间。`LOADER_PARITY` 覆盖全部 3400 条记录、角色回写后的再次读取、header 配置解析及完整环境 kwargs，不只验一条 smoke。

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

追溯性成立需要以下约束通过实际验收：

1. **`logs/` 照常进 git**。放的不只是文本日志，还有判定 JSON、运行参数、实跑清单这些机器可读文件。「用户不看」不等于「不存」。
2. **两个 jsonl 靠主键互指**。候选与两类结果均有外层 `(task, difficulty, episode) / spec_sha256`；h5 结果若有 `injection_evidence.spec_sha256`，还须与外层相同。失败行也能回指候选，不能因为环境未启动就丢掉身份。结果另有 `h5_path / h5_sha256`，路径须在迁移后实际可达。
3. **候选行内嵌筛查证据并区分来源**。旧 `collision` 完整保留在 spec；新观测放在 screening。run 10 的详细尝试历史来自重新运行采样器，明确标 reconstructed，并以旧规格逐条一致为补证前提。

会变化的两处及处置：

- **正式 / 备用**：由 `delivery_manifest.json` 改为结果行 `role` 字段（口径 5）。HF 发布脚本 `scripts/hf_release.py` 目前读 `delivery_manifest.json`，本轮不改它，但在 `scripts/INJECTION.md` 记明「再次发布须先改 hf_release.py 读 `results.jsonl` 的 `role`」。
- **决策史**：四份计划 md 删除后只在 git 历史与 `newtask-v2` 分支可查（口径 7）。

## 八、删除清单

- **代码**：`scripts/injection/replay.py`、`contract_build.py`、`plots.py`、`campaign.py`（其 plan / check / run / env-check / delivery 逻辑迁入两个新包后整文件删）、`scripts/injection-before-2d/` 整个目录（含 `check_doc_links.py`、`windows_timeline.json`、`figures/`）。**不删**的两个：`h5_compare.py` 搬为 `scripts/injection/rollout/h5_compare.py`，只在对拍 SHA-256 不一致时用来定位差异（第九节 9.2）；`env_check.py` 搬为 `scripts/injection/rollout/reset_check.py`（第四节 4.3）。
- **删除时机**：旧的出图、事件表、timeline 脚本要先对 run 10 跑一遍留下基线（第十节阶段 3），之后才能删。
- **配置**：从生产配置目录删除 `injection_contract_v1.json / injection_contract_v2.json`；为保留差分断言，将原字节作为测试夹具移至 `tests/fixtures/injection_legacy/`，不进入生产流程。`contract_build.py` 仅保留构建器纯函数到测试辅助模块，删除 CLI，详见第二部分测试迁移表。
- **文档**：第六节表中标「删」与「重写」的六份；`scripts/README.md` 第四节改为指向 `scripts/INJECTION.md`。
- **轻量包**：`docs/validation/newtask-v2/` 下 `20260910-new-values-04`、`20260911-contract-v3-06`、`20260911-contract-v3-07`、`20260912-contract-v3-08`、`20260912-contract-v3-09`、`20260912-contract-v3-10` 六个目录。其余非 injection 轮次目录不动。
- **run 10 目录内**：不删只移（第十节阶段 7）。`env_check/*.jsonl` 的 720 行转成 `kind="reset"` 行并入 `rollout/results.jsonl`，原文件与 `env_check_result*.json`、`feasibility/P0x1/`、`manifests/`、四份 `feasibility_result*.json`、`delivery_manifest.json`、`manifest.json`、`plan_stats.json`、`check_result.json`、`logs/*` 全部进对应阶段的 `logs/`。
- **`.gitignore`**：`artifacts/injection` 段与 `scripts/injection-before-2d/figures` 段整体替换（第二部分二），必须验证嵌套 smoke 的大文件忽略与日志反选。
- **依赖条件**：阶段 1～7 所谓“搬迁”均先复制新实现、保留旧可执行模块；不能提前移走旧模块导致阶段 3 无法留基线。新实现不得转发调用旧实现来凑对拍通过。阶段 8 才删除旧路径，并同步调整测试和保留工具的导入；历史审查、账本和本计划中的旧符号说明不要求清零。

## 九、修改前后的对拍

### 9.1 修改前的生成花了多久（run 10 实测，2026-09-12，双卡各 20 worker）

| 阶段 | 规模 | 墙钟 | 出处 |
|---|---|---|---|
| `plan` 冻结候选 | 14 组 3400 条 | 675.3 秒（11 分钟） | `logs/plan.log` `elapsed_s=675.3` |
| `check` 静态与碰撞筛查 | 3400 条，碰撞扫掠 1700 条 | 1338.5 秒（22 分钟） | `logs/check.log` `elapsed_s=1338.5` |
| 实跑 | 1842 条，通过 1796 | 6684.4 秒（1 小时 51 分），16.12 条/分 | `feasibility/P01x20/run_summary.json` `elapsed_s` |
| 成功条单条 | 1796 条 | 中位 126 秒、最大 241 秒；串行总和 63 小时 | `episode_results.jsonl` `wall_s` |
| 超时条单条 | 21 条 | 600 秒被终止（最长实测 626 秒） | 同上 |
| 产物体积 | h5 1796 个 | 880 GB，中位 424 MB | 旧 `delivery_manifest.json` 的 `bytes`（新结果表改名为 `h5_bytes`） |

历史记录中的磁盘余量为 1.9 TB、GPU 0/1 空闲；这些不是开跑时保证。每次启动前重新检查 `df -h /data` 与 `nvidia-smi`，方案 B 预计新增约 90 GB，额外预留图、诊断和临时文件空间。这里只保留资源检查要求，不授权扩大到方案 A。

### 9.2 逐字节判据、视频诊断与确定性的证据边界

run 10 里 RouteStick/easy ep0 被生成过两次：smoke 档 `P0x1`（单卡 1 worker，13:06）与正式档 `P01x20`（双卡 40 worker，13:29）。两次的成品：

| 文件 | 字节数 | SHA-256 前 16 位 | 结论 |
|---|---:|---|---|
| `RouteStick_ep0_seed16000.h5` | 200,071,952 | `27d7e1c62583025e` 两次相同 | 此样本两次 h5 逐字节相同 |
| `RouteStick_ep0_seed16000_easy_watch….mp4` | 6,648,548 | `468cf3b5c00344e3` 两次相同 | 此样本两次 mp4 逐字节相同 |

这只支持一个输入的重复结果，不能证明所有任务、所有 block 或新加载器都确定。L3 的硬条件是：固定 210 个键、seed、旧规格及环境配置；205 条预期成功 h5 的实际散列与 run 10 留存散列相等；5 条预期失败的 `ok / failure_class / error_type` 相同。任何成功变失败、失败变成功或失败类型变化都记失败，不换 seed、不补样本、不豁免。

h5 散列不等时调用 `h5_compare.py` 定位字段、结构、属性、dtype 与数值差异；如果只发现容器写入差异，也只报告“内容相同、字节判据未通过”，不得擅自改成容差验收。散列与内容一致分别报告。已有失败的可重复性不作为新运行必然重复的假设。

用户已决定**视频内容差异单列、不阻塞 L3**。全部样本视频先核文件存在、解码状态和散列；散列相同记字节一致，不同则比较完整解码后的帧数、尺寸、帧率、顺序与逐帧像素，并保留首个差异帧及原因。诊断写 `VIDEO_DIAGNOSTIC=PASS / DIFFERENT / NOT_RUN` 和计数，后两种不得显示成视频一致；不设置自动像素容差，也不参与 `H5_PARITY` 成败。BinFill 中 ep1/ep16 同为 1388 帧的已知反例必须被错配诊断识别。视频解码失败或预算不足如实列出未完成项，可在 h5 验收通过时保留视频差异/未验证结论。

以上宽松口径只适用于**重新生成视频的内容对拍**。阶段 7 只是移动既有文件，仍必须保持全部已有 mp4 字节不变、数量不减；不能用“视频不阻塞”作为丢失旧视频的豁免。

### 9.3 四层对拍

| 层 | 比什么 | 怎么比 | 规模与耗时 | 判定行 |
|---|---|---|---|---|
| L1 候选（**全量必做**） | 相同契约与配置重算 3400 个固定键 | 检查完整键集合，按旧算法重算 spec 散列并比完整旧记录含 collision；单独核验新增观测计数与来源 | 原 plan+check 约 35 分钟，新增过程采集耗时待测；新增轻量日志 | `CANDIDATES_EQUIVALENCE=PASS compared=3400 differences=0`、`SCREENING_EVIDENCE=PASS rows=3400 count_mismatch=0 origin_missing=0` |
| L2 图、表、数轴（**全量必做**） | 旧、新实现读同一批 1796 个成功 h5 | 113 张 PNG 比字节、事件表逐行比；timeline 比保留行及 excluded_slow 全记录，路径只按预先冻结映射归一化 | 旧 extract 未全量实测，估 10～30 分钟，另加出图；会生成两套图与轻量数据 | `FIGURES_EQUIVALENCE=PASS png=113 differences=0`、`TABLES_EQUIVALENCE=PASS drift=0`、`TIMELINE_EQUIVALENCE=PASS before=1796 kept=K excluded=E skipped=0 differences=0`，且 `K+E=1796` |
| L3 h5（**方案 B**），视频另作诊断 | 每组 block 0 的 ep0～14，14 组共 210 个固定键 | 205 成功比实际 h5 散列；5 失败比结果类型；视频按 9.2 单列，不参与此层硬条件 | 生成约 15～20 分钟，额外 h5 散列/视频解码耗时待测；约 90 GB | `H5_PARITY=PASS compared=210 success=205 failures=5 sha_mismatch=0 failure_mismatch=0`；另报 `VIDEO_DIAGNOSTIC` |
| L4 reset（**全量必做**） | 临时 run 使用旧组顺序、双卡各 20 worker，只执行一次正常配额核验 | 与旧 720 个键逐一比较 `ok / outcome / error_type / injection_bound / counted / role` 及每组停止 episode；耗时、PID 不比 | 旧运行 492.7 秒；不产 h5/mp4，会保存核验日志 | `RESET_PARITY=PASS compared=720 outcome_mismatch=0 stop_episode_mismatch=0 role_mismatch=0` |

每层先检查**预期键集合**、重复键、缺失键、额外键，记 `PARITY_KEYS=PASS layer=L1/L2/L3/L4 missing=0 extra=0 duplicates=0`，然后再比值；不能对两侧交集报 PASS。L3 左侧按方案 B 固定选择 210 键，右侧禁止多跑；L4 左侧用补查 unused 之前的 720 键快照，不把后续 838 条掺入比较。

L2 不把 1796 当成剔除后条数：旧 `apply_slow_exclusion` 会剔除最长段超过 400 帧或总长超过组中位两倍者。已实测 run 10 的 VideoUnmaskSwap/xhard/ep5 总长 1312、最长段 828，会被剔除；`K / E` 以阶段 3 全量旧基线为准，必须逐条核对剔除原因，不能为凑总数取消剔除。

### 9.4 L3 的四个方案（用户 2026-09-17 选定 B：「使用B 每组前 15」）

条数按「每组 block 0 的前 N 条」取，覆盖 14 组；耗时按双卡 40 worker、机器空闲估，含超时条封底（每组前 1 条里就有 VideoRepick/easy ep0 这条 626 秒超时）。

| 方案 | 条数 | 预计墙钟 | 临时磁盘 | 覆盖到的结果类型 | 能证明什么 |
|---|---:|---|---:|---|---|
| A 全量（未选） | 1842 | 生成约 1 小时 51 分，另加核验 | 约 880 GB，启动前查余量 | 1796 成功；21 环境报告失败、21 超时、3 BinFillDemoError、1 BinCollisionError | 可以逐条核验全量 h5；视频结论仍须独立列出 |
| **B 每组前 15（已选定）** | 210 | ≈ 15 到 20 分钟（理论下限 11.5 分钟） | ≈ 90 GB | 205 成功 + 3 规划失败 + 2 超时 | 四任务四档全覆盖、三类结果都有样本 |
| C 每组前 5 | 70 | ≈ 10 到 12 分钟（下限 4 分钟，被 626 秒超时封底） | ≈ 30 GB | 68 成功 + 1 规划失败 + 1 超时 | 四任务四档全覆盖 |
| D 每组前 1 | 14 | ≈ 10 分钟（被 626 秒超时封底） | ≈ 6 GB | 13 成功 + 1 超时 | 只证明链路能通 |

用户已选 B，不扩大样本范围。其结论只能是“固定 210 条的 h5/结果类型对拍通过”；其余 1632 条仍未做生成对拍，不能靠一个样本的确定性外推一致。这里的各方案时间只估生成，不含静态筛查、完整视频诊断、迁移散列和所有报告时间；没有全流程耗时承诺。

## 十、实施步骤

每阶段单独获批、单独 commit；下面均为未来实施，不因本轮修订而获得执行授权。硬判据不过不进下一阶段；视频诊断按用户决定单列，不混入硬判据。

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 计划在指定分支完成修订，冻结代码、配置、依赖锁和运行 10 的旧清单 | 文档核验通过；各实施阶段仍未启动 |
| 1 | 复制四个核心模块到 candidates 包，保留旧入口；新增只读观测、io、screen 与入口；L1 重算 run 10 并补入 reconstructed 证据 | `CANDIDATES_EQUIVALENCE`、`SCREENING_EVIDENCE`、L1 `PARITY_KEYS` 全 PASS；元数据变动不影响旧规格 |
| 2 | 生成器接封套与 header 快照，close 后加 h5 散列；全部候选加载等价，再跑单任务/单 episode/单 worker 的 RouteStick/easy/ep0 | `LOADER_PARITY=PASS compared=3400 kwargs_mismatch=0 role_rewrite_mismatch=0`；`SMOKE_H5_PARITY=PASS compared=1 sha_mismatch=0`；旧 JSON 与无规格路径定向回归通过 |
| 3 | 用保留的旧 plot、event_tables、window_timeline extract 及 plot_sampling_windows 对 run 10 留完整基线；仅调整输入/输出路径，不改算法 | `BASELINE_CAPTURED=PASS png=113 tables=14 before=1796 kept=K excluded=E skipped=0`，`K+E=1796`；输出清单散列冻结 |
| 4 | 建 rollout 包和幂等状态归并；用旧结果、交付清单、env_check 迁出新结果表；保留当前有效旧路径，冻结迁移映射及 L4 原 720 键 | `RESULTS_EQUIVALENCE=PASS h5_rows=1842 primary=1600 spare=196 failed=46 reset_rows=720 reset_primary=700`；`ROLES_CONSISTENT=PASS rows=3400 mismatch=0 duplicates=0 pending=0 unused=838` |
| 5 | 临时 run 独立副本跑 B 的 210 条，并由同一次主命令执行 L4；核对源候选未变；留档后处理临时大产物。随后另对正式 run10 的 838 个冻结 unused 键全部尝试 | L3/L4 `PARITY_KEYS`、`H5_PARITY`、`RESET_PARITY`、`PARITY_SOURCE_INTACT` 全 PASS；`VIDEO_DIAGNOSTIC` 单列；`UNUSED_RESET checked=838 unused_left=0 primary_changed=0`；正式结果 3400 个唯一键，角色复核 pending=0、unused=0 |
| 6 | 新图表读取 results 中当前仍有效的旧路径，对运行 10 出图与报告，完成 L2；不提前硬拼尚未存在的 rollout 组目录 | `FIGURES_EQUIVALENCE`、`TABLES_EQUIVALENCE`、`TIMELINE_EQUIVALENCE` 与 L2 `PARITY_KEYS` 全 PASS |
| 7 | 按冻结映射迁移全部现有产物；改写结果、timeline、活跃清单和报告路径；保留 journal、恢复副本与旧日志 | `H5_INTACT=PASS count=1796 sha_mismatch=0 missing=0`；`ARTIFACTS_INTACT`、`ACTIVE_PATHS`、`MIGRATION_METADATA`、`MIGRATION_RECOVERY` 全 PASS（第二部分一） |
| 8 | 删除旧生产路径，保留测试夹具并适配具名测试/共享工具；改忽略规则与流程文档；审查报告、账本留存 | `IMPORT_CLOSURE=PASS missing=0`、`TEST_COLLECTION=PASS errors=0`、`TEST_SCOPE=PASS new_unexplained_skips=0`、`IGNORE_RULES=PASS logs_visible=1 media_ignored=1`；活跃文档链接 PASS；跟踪文件集合与批准清单一致 |
| 9 | 独立 smoke run：RouteStick/easy 组2个 block（200 候选）、1 条 train h5、1 条 test reset，全部单 worker；再调用同一 reset 验幂等 | 总耗时 <5 分钟；两个 jsonl、h5、图、报告齐全；`RESET_IDEMPOTENT=PASS rerun=0 duplicates=0`，主 run 角色不变。选2个 block 是因为正式 split 边界 run_episodes=115，单 block 没有 test 行；不增加仿真实跑条数 |

实施完成后实测结果以子节追加在本表之后，不把上述预期判定行改写为已测结果。每次代码改动后另执行 5 分钟内的相关测试；本表中 35 分钟的候选验证、仿真对拍等属于获批后的独立长任务，必须 tmux 启动，不拿它们代替短测试。

### 10.1 阶段 0～1 实施记录（2026-09-17）

用户后续指令原话「开始实现」。在指定分支 `newtask-v2.1refractor` 从 `2bcd9cc` 开始推进阶段 0～1；本节是新增实施记录，不改写上面的预期判据，也不把其余阶段标记为获批或完成。

- 阶段 0：提交 `41f5fa2`（11.09），冻结 221 个代码、配置、依赖锁、运行 10 小产物及计划文件的 SHA-256。追加本节前，221 文件全部复验通过；追加后计划文件为唯一登记的文档差异，旧代码和输入均未改。
- 阶段 1：新增 `scripts/injection/candidates/`，复制四个核心模块并保留旧入口；新增独立观测、纯标准库封套读取、筛查与冻结入口。3400 条旧完整规格与旧统计零差异；逆组序再生 `SPEC_REPRODUCIBLE=PASS compared=3400 differences=0`，`CANDIDATES_EQUIVALENCE`、`SCREENING_EVIDENCE`、L1 `PARITY_KEYS` 全 PASS。连续碰撞检查 1700 条、拒绝 0、未认证 0，最小间隙 `1.4025e-05 m`。
- 重算证据：完整拒绝事件 11514 条，与旧统计总数相同；候选均标记 `reconstructed`。运行 10 的 `candidates/candidates.jsonl` 共 3400 条候选加一行 header；train 1842、test 1558，初始角色均 pending，未迁移旧结果角色。
- 验证：定向测试 60 passed / 9 skipped，93.41 秒；筛查字段补测 14 passed / 4 deselected，3.16 秒。全量任务使用 tmux，1986.59 秒、`EXIT_CODE=0`、11 项判定全 PASS；落盘后 3400 条角色改写的内存核验保持旧规格与身份不变，旧输入和实测实现文件指纹复验通过。
- 当前边界：阶段 2～9 未执行，图表和报告尚未接入新入口；生成器、`src/robomme/`、已有 HDF5/视频没有改动。复现命令、测试意外、代码指纹说明及证据见[实施留档](docs/validation/newtask-v2/20260917-injection-refactor/README.md)。

### 10.2 阶段 2 实施记录（2026-09-17）

用户对阶段 2 的明确报批答复原话「同意」。实施起点 `c336390`（11.10），修改限定在第二部分 R2 的五处锚点，旧 JSON 与无规格路径保留原行为；源候选、环境源码、录像器和旧 HDF5/视频不改。

- 新 JSONL 入口验证封套、旧散列、seed 与完整采样快照，生成只选 train 与请求范围交集；外部配置仅做一致性断言。JSONL 要求 `max_attempts=1`，保持冻结 seed；旧重试调度代码未改。
- `LOADER_PARITY=PASS compared=3400 kwargs_mismatch=0 role_rewrite_mismatch=0`：旧入口取自固定提交，新旧完整环境参数直接执行各自 worker 的实际构造语句，包含恢复参数；全部角色在内存副本回写后再读，仍零差异。
- `SMOKE_H5_PARITY=PASS compared=1 sha_mismatch=0`：RouteStick/easy/ep0，seed 16000，单卡、单 worker；新旧 HDF5 均 300 帧、200071952 字节，SHA-256 为 `27d7e1c62583025e7f6a18610749e6e3990cfe85c00219e80fbf1d1b086c203b`。生成 18.2 秒，新增散列读取 0.121 秒，退出 0。
- 定向回归 73 passed / 4 skipped，19.46 秒；仓库内测试夹具修订后补测 11 passed，10.28 秒。未进行跨次视频内容对拍，未实跑其他任务；阶段 3～9 待后续批准。完整命令、基线歧义核实及轻量产物见[实施留档](docs/validation/newtask-v2/20260917-injection-refactor/README.md)。

### 10.3 阶段 3 实施记录（2026-09-18）

用户已一次授权剩余阶段。旧工具源码不改，通过独立采集入口只指定运行编号和输出路径：98 张跑前图、15 张数轴图、14 组事件表（156 行）均已冻结。`BASELINE_CAPTURED=PASS png=113 tables=14 before=1796 kept=1795 excluded=1 skipped=0`，977.79 秒、退出 0。旧数轴定向测试 34 passed，2.79 秒。完整清单、逐文件散列、原始 timeline 与表见运行 10 的 `rollout/logs/baseline/`；图片留在本地，散列和轻量数据入库。后续 L2 须严格比较这 1795 条保留记录及 1 条完整剔除记录。

### 10.4 阶段 4 实施记录（2026-09-18）

`RESULTS_EQUIVALENCE=PASS h5_rows=1842 primary=1600 spare=196 failed=46 reset_rows=720 reset_primary=700`；`ROLES_CONSISTENT=PASS rows=3400 mismatch=0 duplicates=0 pending=0 unused=838`。3820 个文件的迁移映射、L4 原 720 键与停止位置已冻结，尚未移动数据；候选身份不变。独立新入口完成 1 条 HDF5 与 1 条 reset，重复执行零重跑；HDF5 与原 RouteStick/easy/ep0 同散列。17 项短测通过（31.18 秒），新旧 reset 模拟批次 720 键一致，含失败的 unused 测试仍完整覆盖 838 条。进入阶段五，不再重复报批。

### 10.5 阶段 5 实施记录（2026-09-18）

L3/L4 与源完整性全通过：210 条 HDF5 尝试中 205 成功、5 失败，实际散列与失败类型零差异；720 条 reset 的结果、停止位置和角色零差异，完整键无缺失/额外/重复。视频 221 对通过，2 条超时没有可比视频，整体记 NOT_RUN；同为 1388 帧的真实 BinFill/medium ep1/ep16 错配已完整解码识别并留存证据。

硬闸后先逐文件归档 38 份证据，再按核验清单清理临时 426 个媒体文件（101712029329 字节），原运行大文件未删。随后 `UNUSED_RESET=PASS checked=838 passed=838 failed=0 unused_left=0 primary_changed=0`。正式唯一结果现在共 3400 条，train 角色不变，test 700 primary、858 spare，失败和 unused 都为 0；普通新运行的 unused 停点机制仍保留。

---

### 10.6 阶段 6 实施记录（2026-09-18）

新图表与旧冻结基线全量对拍通过：`FIGURES_EQUIVALENCE=PASS png=113 differences=0`、`TABLES_EQUIVALENCE=PASS drift=0`、`TIMELINE_EQUIVALENCE=PASS before=1796 kept=1795 excluded=1 skipped=0 differences=0`。正式报告实际读取 1796 个 HDF5 核对大小与 SHA-256，`REPORT=PASS purpose=delivery rows=3400 pending=0 unused=0`，流水线退出 0。首轮发现规范序列化改变展示字典顺序及交换规格漏投影，均按旧展示算法修复，失败日志保留；定向回归 37 项通过。候选快照及本仓库两个环境启动入口纳入 Git；第三处策略侧仍仅定义契约。

### 10.7 阶段 7 实施记录（2026-09-18）

迁移退出 0：3820 个文件迁前、迁后实际散列全相同，集合零缺失、零额外；1796 个成功 HDF5 与结果中的大小和 SHA-256 一致。活动路径全部可达、旧前缀零残留，活动元数据只改冻结允许字段；迁移状态已置 complete。5 项中断恢复、拒绝覆盖和读取守卫反例通过，0.89 秒。逐文件清单、恢复日志、小文件原版/新版及验证 JSON 均保留并纳入 Git。

### 10.8 阶段 8 实施记录（2026-09-18）

已清理计划指定的旧生产入口、六份文档与六个轻量包；v1/v2 契约按原字节迁为夹具，纯构建器迁入测试。保留 delivery 唯一格式化函数以兼容冻结发布工具。现行说明为 scripts/INJECTION.md；候选、结果、轻量日志与恢复证据进 Git，嵌套重媒体忽略。

25 个生产模块导入成功、623 项测试收集无错误；26 个忽略规则探针与 114 个现行文档链接通过。核心回归 490 passed、4 项既有失败、22 项既有历史缺失跳过、74 项预算排除，146.83 秒；新增失败与新增无法解释的跳过均为 0。原全量 GPU 轻量测试到 280 秒按预算中止，不宣称全套通过；加载器路径修正后 11 项通过，图表补读图说明后 37 项通过。真实单条端到端验收由阶段九执行。

### 10.9 阶段 9 与整体完成记录（2026-09-18）

最终独立运行 `refactor-final-smoke` 在 60 秒内完成（timeout 280 秒，退出 0）：RouteStick/easy 冻结 200 候选，单 worker/GPU 0 生成 ep0 的 1 个 HDF5 并 reset ep115；9 张图、3 份报告和两条影子结果齐全。HDF5 300 帧，与原基线 SHA-256 相同；重复 reset 零重跑、零重复键，正式运行候选字节不变。迁移和清理后重验 L2 仍为 113 PNG、表与 1796 条完整数轴零差异。

阶段 0～9 全部实施完成，输入快照与消费代码均纳入 Git；策略侧第三处仅为既定消费契约。最终核心回归 490 项通过，保留 4 项既有失败、22 项历史缺失跳过与 74 项预算排除；全量 GPU 测试 280 秒中止，视频诊断中两条超时缺视频仍为 NOT_RUN，不宣称全套测试或全视频对拍通过。现行命令、证据和限制见 scripts/INJECTION.md 及实施 README。

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

- R1 `src/robomme/` 不动（AGENTS.md 强制规则第 11 条，录像器冻结）。
- R2 生成器允许的改动锚点仅为：`load_episode_specs` 的封套读取与旧 spec 投影；从 `load_sampling_config` 提取复用的对象校验 helper（旧文件调用语义不变）；`generate_dataset_newseed` 的 JSONL 输入分支注入 header 配置并核验 seed/固定 kwargs；`EpisodeJob` 新增默认 False 的 `emit_h5_digest` 标志，仅新 JSONL 分支置 True；`_worker` 在该标志开启时于 close 后新增 `h5_sha256 / h5_bytes`。不能从投影后相同的 spec 猜测来源。不改采样、planner、step、重试和录像逻辑；旧 JSON 与无规格路径保持原行为。
- R3 run 10 的 h5 / mp4 只 `mv` 不重跑、不删；迁移前后逐文件 SHA-256 核对。
- R4 `spec_sha256` 只对嵌入的旧 spec 使用原算法，旧字节与键集合不变。封套身份、管理状态、观测结果分别校验，不能靠重封旧散列、丢弃未知字段或伪造筛查值让测试通过。
- R5 不 `git push --force`；分支 `newtask-v2.1refractor` 首次推送前先问用户是否 `git push -u origin newtask-v2.1refractor`，之后每次 commit 后照常 `git push`。
- R6 `hf_release/` 与 `scripts/hf_release.py` 本轮不动。
- R7 旧模块和配置在阶段 1～7 保持可执行，供旧基线使用；阶段 8 获批且前置硬闸全部通过后才删除。测试夹具、审查账本属于保留边界，不在历史生产入口的删除范围。
- R8 L3/L4 仿真只写独立临时 run，源候选只读。硬闸完成后先把结果表、范围、散列、诊断及失败证据留到正式 run 的 `rollout/logs/parity/`；没有诊断需求且清单核对后才清理临时大文件。存在视频差异时保留差异证据及对应视频对，不自动销毁定位材料；不能笼统 `rm -rf` 尚未留档的整个 run。
- R9 `results.jsonl` 按键唯一、日志追加、单写者；两个 jsonl 的更新不是跨文件原子事务。先恢复一致状态再继续运行；未完成的目录迁移同样禁止被普通入口消费。

## 一、逐文件改动清单

| 新文件 | 来源 | 改什么 |
|---|---|---|
| `scripts/injection/candidates/contract.py` `sampling.py` `categories.py` | 原同名文件 | 先复制、只改包内 import；阶段8才删除旧路径 |
| `scripts/injection/candidates/specs.py` | 原 `specs.py` | 原规格生成逻辑不变；在 `_place_binfill_cubes`、视频候选循环、`_count_rejection` 增加独立观测通道，采集 trial、物体键、拒绝原因及提案；按 4.1 区分计数单位；不把诊断写入旧 spec，不再截断新日志 |
| `scripts/injection/candidates/io.py` | 新写，纯标准库 | `load_candidates / project_spec` 统一核验封套、主键、外内身份、旧 spec 散列及快照身份；header 与旧规格分离返回；禁止静默丢键；可复用原散列函数等价实现，由定向测试锁住 |
| `scripts/injection/candidates/screen.py` | `campaign.py::cmd_check` 六项判定 | 四任务几何、碰撞和配额结果合入封套；消费生成时的逐条观测，不从聚合表反推；组级进 logs；run10 标 reconstructed，并在 L1 成功后才发布补证结果 |
| `scripts/injection/candidates/figures.py` | 原 2D 出图脚本 | 通过 io 读取旧 spec；重定位 REPO_ROOT 与输出根，旧裸模块导入改包导入；前30条逐条图及全量分布口径不变 |
| `scripts/injection/candidates/report.py` | `injection-before-2d/event_tables.py` + `NEW_VALUE_DISTRIBUTION_BEFORE.md` 二、三节模板 | 输出 `candidates/DISTRIBUTION.md`；保留 `--check` 零漂移模式 |
| `scripts/injection/candidates/__main__.py` | `campaign.py::cmd_plan` | 派生→采集→screen→写封套/快照→图→报告；同名候选或运行状态已存在即拒绝覆盖，预建空 logs 不算已冻结运行；`--purpose smoke` 允许候选规模小于正式交付需求，但保持原 split 边界和分层机制 |
| `scripts/injection/rollout/run.py` | 原 `run.py + delivery.py` | 原始尝试日志与唯一结果表分离；副本归属、单写者、恢复、scope、角色与幂等合并按 4.2/5.3；保留范围/续跑/墙钟限制；`--purpose delivery/parity/smoke` 显式决定是否验完整交付；`invoke_generator` 用 REPO_ROOT 拼生成器绝对路径 |
| `scripts/injection/rollout/windows.py` | `window_timeline.py + plot_sampling_windows.py` | 按 results 的有效 h5_path 读取，不假设迁移已完成；保留慢条规则，输出 before/kept/excluded 和 skipped；timeline 与图落新目录；重定位 REPO_ROOT、默认路径及所有裸导入 |
| `scripts/injection/rollout/report.py` | `campaign.py::cmd_report` 的结果表部分 + `window_timeline.py tables` | 输出 `ROLLOUT.md`（通过表、失败清单、视频状态）与 `WINDOWS.md`（公式、汇总表、剔除表） |
| `scripts/injection/rollout/single_binfill.py` | `plot_binfill_medium_single.py` | 改输入路径及旧 window_timeline/plot_sampling_windows 的包导入；不被主入口调用，但其导入及 `--help` 必须纳入 IMPORT_CLOSURE |
| `scripts/injection/rollout/h5_compare.py` | 原同名文件 | 原算法迁入，保留原共享工具所需导出符号；h5 散列不同时定位差异，不自动放宽硬闸 |
| `scripts/injection/rollout/reset_check.py` | 原 `env_check.py::check_one / run_env_check / EnvCheckPlan` | 输入只读所属 run 的候选副本及 header 配置；普通模式复用终态并按旧组序/批序完成配额；only-unused 模式遍历冻结集合，不按50停止；结果走 run.py 统一合并；固定 kwargs、120秒单条超时、池初始化及 CPU/GPU 绑定不变；修正新目录 REPO_ROOT |
| `scripts/injection/rollout/parity.py` | 新写 | 从冻结 scope 取预期键，先检查重复/缺失/额外，再执行 L3/L4；h5 SHA/失败类型为硬闸，视频诊断单列；`--scheme B` 固定14组各ep0～14；返回码只取硬闸；核验源候选前后字节不变 |
| `scripts/injection/rollout/__main__.py` | 原 feasibility 编排 | 导入独立候选副本→恢复状态→run→role→reset_check一次→windows→report；`--no-figures` 只跳图；smoke 用 `--reset-limit 1`、不验完整交付；作用域在执行前冻结到 logs |
| `scripts/generate_dataset_newseed.py` | 现有 | 只改 R2 所列五个锚点；JSONL 候选经 io 返回旧 spec，header 采样对象走与旧文件同一校验函数；显式标志控制散列结果字段；外部配置只能做一致性断言；不在 worker 里写候选管理状态 |
| `scripts/INJECTION.md` | 新写 | 现行口径、两阶段命令、两个 jsonl 字段表、追溯链、「再次 HF 发布须改 hf_release.py」 |
| `scripts/injection/_migrate_run10.py` | 新写，保留到迁移及恢复演练通过 | 分 `prepare / move / verify / resume`；prepare 用旧 specs 加 L1 重算诊断写候选、按旧主键和清单写结果；move 基于清单逐项移动并改写有效路径；禁止覆盖；verify 守恒和可达性；resume 按 journal 继续；工具与报告至少保留到阶段8审查后 |

### 测试与保留工具的逐项适配

以下都是未来实施清单，本轮不改这些文件。每阶段的新接口测试与当阶段代码一起加入，阶段8才完成旧路径删除后的整体收集检查；不能用删测试、增加 skip 代替迁移。

| 文件 | 保留断言与改动 |
|---|---|
| `tests/lightweight/test_episode_specs.py` | 导入新 specs；旧 JSON 校验不变；补3400条封套投影、角色回写、身份/快照篡改拒绝与完整 kwargs 等价 |
| `tests/lightweight/test_injection_contract.py`、`test_operand_scope.py` | 改导入新核心与纯测试构建器；保留 v1/v2/v3 的取值域差分、override、作用域散列与14组约束 |
| `tests/lightweight/test_injection_campaign.py`、`test_injection_blocks.py` | 分别迁到 screen/run 接口；保留配额、block 独立性、范围守卫、失败分类、结果去重；新增观测开关不改规格或随机流的对拍 |
| `tests/lightweight/test_injection_delivery.py` | 适配 results/role；验证完整交付与 partial scope 分离，失败和 spare 不丢；覆盖两个文件更新中断后恢复 |
| `tests/lightweight/test_env_check.py`、`test_episode_timeout.py` | 导入 rollout；保留池初始化、失败、超时；覆盖普通停点与 only-unused 不同终止条件、幂等、pending/unused 与 primary 冻结 |
| `tests/lightweight/test_window_timeline.py` | 改为新 windows/figures；保留分段、swap、慢条和 BinFill demo 断言，核 before=kept+excluded，错配/遗漏必须失败 |
| `tests/lightweight/test_scripts_do_not_import_tests.py` | 旧平铺文件集合改成两包拓扑；保留生产代码不得导入 tests 的 AST 检查 |
| `tests/_shared/native_sampling_parity.py` | 从新 h5_compare 导入同名比较符号，原值对拍调用方式与断言不变；对应 dataset 测试至少能正常收集 |
| `tests/lightweight/test_hf_release.py` | 真实历史清单改从迁移后 logs 读取；测试侧按映射提供有效路径，发布脚本不改；不因旧目录消失把当前用例改为 skip |
| `tests/fixtures/injection_legacy/` 与 `tests/_shared/contract_builder_fixture.py` | v1/v2 原 JSON 逐字保留为测试夹具；仅保留 build_v1/v2/v3 的纯函数及依赖常量，去掉写文件/CLI；测试保留逐字重建与版本差分；生产不得依赖这些夹具 |

源码导入用 AST/实际模块收集查，不按文档字符串做零命中。旧历史产物确实缺失的既有 skip 单列；新增 skip 必须有原因，不能掩盖本次搬迁失败。通过 `uv run --no-sync python -m pytest tests/lightweight/ --collect-only -q`，再在5分钟预算内执行全部受影响定向测试；如现有4条全量失败仍出现，先同基线确认，不能改成跳过或报全量通过。

### 阶段4、6、7的路径和恢复协议

1. 阶段4先生成结果与 `rollout/logs/migration/path_map.json`，每个源文件/小文件引用与目标一一对应，路径必须在当前 run 内；当前结果仍用真实存在的旧绝对路径。清单覆盖正式、失败残留视频、附加视频、metadata、smoke 和小文件，不只由1796条成功行推导。
2. 阶段6按当前结果路径读取，原、新 timeline 对拍只对已列明的 `source / h5_path` 做映射归一化，其他字段不豁免；数字、分段、剔除记录和图片照比。
3. 阶段7取得该 run 独占锁，写 `migration_state=in_progress`；普通消费入口遇到该状态拒绝运行。先备份将改写的小文件并生成新版本，再逐项移动目录、更新 journal，最后替换结果/timeline/报告/活跃清单；所有闸门通过后置 complete。多次 `os.replace` 不称作整体原子。
4. 恢复只接受“源有目标无”继续移动，或“源无目标有且大小/散列匹配”继续后续步骤；两边都有、都没有、散列不匹配立即停下，不覆盖不删除。小文件替换失败用 journal 中备份与预生成版本恢复；恢复完成前保持消费阻断。
5. 活跃引用包括 `h5_path / video.path / video.no_object_paths / binfill_demo.video_path`、timeline、报告链接和续跑清单；全部按映射改写。原始 logs、归档交付清单、discarded 里的历史已删路径保留原文，不要求存在，但不得拿它们当新运行入口。
6. 最终查 `H5_INTACT=PASS count=1796 sha_mismatch=0 missing=0`（只统计正式档1600 primary+196 spare，smoke及任何失败残留另入完整清单）；`ARTIFACTS_INTACT=PASS missing=0 extra=0 sha_mismatch=0` 检查冻结的旧产物集合经路径映射后的守恒，含全部旧视频和metadata，阶段5/6新增图表、诊断等另有允许清单，不能把它们误判为 extra；`ACTIVE_PATHS=PASS missing=0 old_prefix=0`；`MIGRATION_METADATA=PASS unexpected_field_changes=0`（只允许登记路径改写，不改角色/帧数/失败信息）；`MIGRATION_RECOVERY=PASS duplicate_moves=0 overwritten=0`。恢复中断用小夹具演练，不故意破坏真实 run10。

## 二、`.gitignore` 替换段

```
/artifacts/*
!/artifacts/injection/
/artifacts/injection/*
!/artifacts/injection/*/
/artifacts/injection/*/*
!/artifacts/injection/*/candidates/
/artifacts/injection/*/candidates/figures/
!/artifacts/injection/*/candidates/logs/**/*.log
/artifacts/injection/*/candidates/**/*.png
/artifacts/injection/*/candidates/**/*.jpg
/artifacts/injection/*/candidates/**/*.jpeg
/artifacts/injection/*/candidates/**/*.svg
!/artifacts/injection/*/rollout/
!/artifacts/injection/*/rollout/logs/**/*.log
/artifacts/injection/*/rollout/**/hdf5_files/
/artifacts/injection/*/rollout/**/videos/
/artifacts/injection/*/rollout/**/*.h5
/artifacts/injection/*/rollout/**/*.mp4
/artifacts/injection/*/rollout/**/*.png
/artifacts/injection/*/rollout/**/*.jpg
/artifacts/injection/*/rollout/**/*.jpeg
/artifacts/injection/*/rollout/**/*.svg
/artifacts/injection/*/rollout/figures/*
!/artifacts/injection/*/rollout/figures/windows_overview.png
!/artifacts/injection/*/hf_release/
```

删除 `scripts/injection-before-2d/figures/*` 两行。

基线图和差异帧保留在磁盘，但同样不误入 git；原始图片/视频诊断路径、散列、说明进轻量日志。实施时使用 `git check-ignore --no-index -v` 检查以下代表路径；另外检查已跟踪文件清单，防止已有跟踪绕过忽略规则：

| 应入库 | 应忽略 |
|---|---|
| `candidates/candidates.jsonl`、`candidates/logs/plan.log` | `candidates/figures/.../*.png`、`candidates/logs/baseline/*.png` |
| `rollout/results.jsonl`、`rollout/logs/parity/check.log` | `rollout/<task>/<diff>/hdf5_files/*.h5`、`videos/*.mp4` |
| `rollout/<task>/<diff>/record_dataset_<task>_metadata.json` | `rollout/logs/smoke/smoke/<task>/<diff>/hdf5_files/*.h5`、同级 `videos/*.mp4` |
| `rollout/figures/windows_overview.png` | `rollout/figures/<task>/<diff>/4_windows.png` |

## 三、runbook（阶段 5 对拍与阶段 9 冒烟的新链路命令）

**以下均为未来 CLI 契约与命令模板；本轮不执行。** 参数及模块须在相应阶段实现并通过短测后才能使用。阶段5使用原运行配置、依赖锁和 GPU 型号；新进程不要继承未记录的运行时覆盖。

阶段 5（方案 B：每组 block 0 前 15 条；reset 只由主命令执行一次）：

```bash
command -v uv
RID=20260912-contract-v3-10
PARITY_RUN=20260912-contract-v3-10-parity
mkdir -p "artifacts/injection/$PARITY_RUN/rollout/logs"
# --candidates 只读导入到临时 run，重置副本执行状态；主命令包含唯一一次 L4。
tmux new-session -d -s injection-parity -c "$PWD" \
  "set -o pipefail; export PYTHONUNBUFFERED=1; { \
uv run --no-sync python -m scripts.injection.rollout --run-id '$PARITY_RUN' \
  --candidates 'artifacts/injection/$RID/candidates/candidates.jsonl' \
  --purpose parity --tier 20 --gpus 0,1 --episodes 15 --no-figures && \
uv run --no-sync python -m scripts.injection.rollout.parity \
  --left '$RID' --right '$PARITY_RUN' --scheme B; \
} 2>&1 | tee 'artifacts/injection/$PARITY_RUN/rollout/logs/parity.log'; \
echo \"EXIT_CODE=\$?\" >> 'artifacts/injection/$PARITY_RUN/rollout/logs/parity.log'"
# 围观：tmux attach -t injection-parity；只在硬闸和源文件完整性确认后开始下一步。
```

`parity` 在全部硬闸通过时退出0，即使 `VIDEO_DIAGNOSTIC=DIFFERENT/NOT_RUN`；报告必须同时显示视频状态。先留档轻量证据及有差异的视频对，再按 R8 清理临时大文件。不要把已退出的 tmux 会话或出现了日志当成通过，必须检查 `EXIT_CODE=0` 和各具名硬判定。

随后对原 run10 进行已授权范围内的 unused 补查（阶段5获批后才可执行）：

```bash
command -v uv
tmux new-session -d -s injection-unused -c "$PWD" \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.injection.rollout.reset_check \
  --run-id 20260912-contract-v3-10 --only-unused --tier 20 --gpus 0,1 \
  2>&1 | tee artifacts/injection/20260912-contract-v3-10/rollout/logs/unused.log; \
echo \"EXIT_CODE=\$?\" >> artifacts/injection/20260912-contract-v3-10/rollout/logs/unused.log"
```

`--only-unused` 冻结并遍历全部838键，复用终态；核对 checked=passed+failed=838、unused_left=0、primary_changed=0。不能因为已有700条 primary 就直接停工。

阶段 9（不足5分钟的独立 smoke；此处不附全量运行命令）：

```bash
command -v uv
timeout 280s bash <<'SMOKE'
set -euo pipefail
SMOKE_RUN=refactor-final-smoke
uv run --no-sync python -m scripts.injection.candidates --run-id "$SMOKE_RUN" \
  --contract scripts/configs/newtask-v2/injection_contract_v3.json \
  --delivery-config scripts/configs/newtask-v2/delivery_400.json \
  --purpose smoke --groups RouteStick/easy --blocks 2
uv run --no-sync python -m scripts.injection.rollout --run-id "$SMOKE_RUN" \
  --purpose smoke --groups RouteStick/easy --episodes 1 --reset-limit 1 \
  --tier 1 --gpus 0 --label smoke
# 同一 smoke 状态重复调用，不再启动已完成的 reset。
uv run --no-sync python -m scripts.injection.rollout.reset_check --run-id "$SMOKE_RUN" \
  --purpose smoke --groups RouteStick/easy --limit 1 --tier 1 --gpus 0 --label smoke
SMOKE
```

两条执行入口的 `--label smoke` 必须解析到相同的 `rollout/logs/smoke/smoke/` 状态目录，里面保存该次候选副本、唯一结果表、图和报告，不能回写正式候选。只查1条test，不执行每组50条配额。超时或首条失败直接停止，不扩大到全量；重复试跑换独立 run-id，保留失败证据。

## 四、风险登记

| 风险 | 处置 |
|---|---|
| run 10 的 `feasibility/P0x1/` smoke 档与 `P01x20` 都有 RouteStick/easy ep0，`delivery_manifest.json` 去重时取的是哪一份未查 | 阶段 4 迁移时按 `delivery_manifest.json` 记录的 `h5_path` 选取，另一份进 `logs/smoke/` |
| `record_dataset_<task>_metadata.json` 由录像器落在组目录，位置不受控 | 保持原位随组目录一起 `mv`，`.gitignore` 反选其入库 |
| 两个 jsonl 之间中断或被并发写入 | run 级独占写锁，唯一结果表为依据，恢复先重建候选角色；单文件原子替换不冒充整体事务 |
| 跨 run 对拍误改正式状态，重复 reset | 首次只读导入独立副本、记录源散列；主命令只含一次 reset，复用终态；PARITY_KEYS 检查重复而非覆盖 |
| 多目录移动中断或有效路径仍指旧位置 | 显式映射、journal、备份与消费阻断，按状态恢复；ACTIVE_PATHS 与文件清单共同验收 |
| BinFill 大 h5 的散列核验拖慢 worker | 先测量新增开销；必要时由收尾步并行读文件计算，但文件关闭/成品检查必须先完成，散列完成前不交付 |
| 视频不阻塞被误写成视频通过 | VIDEO_DIAGNOSTIC 单列差异/未执行计数，h5 PASS 文案不包含视频等价；迁移视频完整性仍必验 |
| 生成循环增加诊断改变采样 | 观测只读已得到的值，不调用 RNG；3400条 spec 和 block 独立性对拍；reconstructed 不冒充原始证据 |
| `hf_release.py` 仍读 `delivery_manifest.json` | R6 不改，`INJECTION.md` 记明 |

## 五、盲区诚实清单

- 「逐字节确定」的证据只有 RouteStick/easy ep0 一条（h5 与 mp4 各一次两两相同），BinFill demo 直出的 h5 与 VideoRepick / VideoUnmaskSwap 的 h5 尚无跨次对照；阶段 5 若出现散列不一致，先用 `h5_compare.py` 判断是内容差异还是写入层非确定，不能直接判新链路有 bug。
- BinFill 的 mp4 经 `imageio` 二次编码，跨次确定性未证明；视频按用户决定只诊断，不阻塞 h5 对拍，但不能只凭帧数相同报内容相同。
- 3 条 `BinFillDemoError` 根因未查，不能预判必然复现；它们不在方案 B 的210键内。若今后另批全量对拍，成功/失败类型变化必须如实判差异，没有“只记不判”的失败豁免。
- L2 的旧 `window_timeline.py extract` 从未对 run 10 跑过，耗时未实测。
- 阶段6从运行10的1796条成功结果读入，剔除后条数待阶段3确定；与07不可逐图对照，须与新捕获的同输入旧实现基线比较。
- 方案 B 只实证210条，其余1632条未验证，不能推断一致；block≥1及部分执行恢复由静态全量/定向测试补覆盖，不冒充生成对拍。
- reset 原 `outcome / ok / error_type` 分别是结果分类、布尔成功和异常类型，迁移保留并校验相容性；720条中的20条在飞余量仍保留 counted=false，不被丢弃。
- run10 拒绝明细将来自未来 L1 重算，记录届时环境与 commit；不能恢复历史上未保存的观测时间或基础设施状态。
- 删除轻量包后 08 / 09 的尾迹核验脚本随之消失，只在 git 历史可查。

## 六、留档与 commit 纪律

每阶段一个 commit，subject 接续最新版本号，body 按仓库 `AGENTS.md` 规则7记录用户原话、计划、过程、意外、验证和当前状态；只 `git add` 本阶段明确路径。11.01～11.04 的计划提交在 `newtask-v2`，11.05起在 `newtask-v2.1refractor`；首次推送仍遵守 R5。本轮仅提交本文，不改审查报告和账本，不执行本文任何实施步骤，不推送。
